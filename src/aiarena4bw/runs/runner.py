"""Runner: führt einen geplanten Durchgang aus – Läufe nacheinander, jeder mit Prüfung.

Läuft als eigener Prozess (`aiarena4bw runner --batch N`), damit weder das Schließen des Browsers
noch ein Neustart des Webservers einen Lauf abbricht. Webserver und Runner tauschen sich nur über
die Datenbank aus (Fortschritt, Abbruchwunsch).
"""

from __future__ import annotations

import asyncio
import os
import platform as py_platform
import signal
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .. import __version__, bwcheck, db, mcpclient, paths, store, tasks, vault, vendors
from ..agent import AGENT_NAME, AGENT_VERSION, SYSTEM_PROMPT, Limits, Outcome, RunLog, run_agent
from ..mcpclient import McpConfigError, McpConnection, McpError
from ..platforms import PlatformError, adapter_for_model
from . import validity
from .verify import choose_verifier, parse_verdict

FINAL_RUN_STATES = {"finished", "error", "timeout", "step_limit", "cancelled", "skipped", "mcp_missing",
                    "no_result"}  # fmt: skip


class RunnerError(Exception):
    pass


# --------------------------------------------------------------------------- Helfer


def running_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.rows(conn, "SELECT * FROM batches WHERE status='running'")
    for row in rows:
        row["alive"] = db.pid_alive(row["runner_pid"])
    return rows


def cancel_requested(conn: sqlite3.Connection, batch_id: int) -> bool:
    row = conn.execute("SELECT cancel_requested FROM batches WHERE id=?", (batch_id,)).fetchone()
    return bool(row and row[0])


def batch_cost(conn: sqlite3.Connection, batch_id: int) -> float:
    """Kosten eines Durchgangs: Läufe, Prüfungen und frühere Prüfversuche."""
    row = conn.execute(
        "SELECT COALESCE(SUM(r.cost_usd), 0) + COALESCE(SUM(v.cost_usd), 0) + "
        "COALESCE(SUM(v.earlier_cost), 0) FROM runs r LEFT JOIN verifications v ON v.run_id = r.id "
        "WHERE r.batch_id=?",
        (batch_id,),
    ).fetchone()
    return float(row[0] or 0.0)


def log_dir(batch: dict[str, Any]) -> Path:
    path = paths.logs_dir() / f"{batch['code']}_{batch['id']}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _redactor(resolved: mcpclient.Resolved, *adapters: Any) -> vault.Redactor:
    values = list(resolved.secrets)
    for adapter in adapters:
        values += adapter.secrets()
    return vault.Redactor(values, resolved.users)


def _limits(settings: dict[str, Any], timeout_s: float) -> Limits:
    run = settings["run"]
    return Limits(
        timeout_s=float(timeout_s), max_steps=int(run["max_steps"]),
        tool_timeout_s=float(run["tool_timeout_s"]), max_output_tokens=int(run["max_output_tokens"]),
        api_retries=int(run["api_retries"]),
    )  # fmt: skip


class _Recorder:
    """Schreibt Ereignisse und Fortschritt eines Laufs in die Datenbank."""

    def __init__(self, conn: sqlite3.Connection, run_id: int, phase: str):
        self.conn, self.run_id, self.phase = conn, run_id, phase
        self.steps = self.tool_calls = self.tool_errors = 0
        self.requirement = ""

    def __call__(self, kind: str, data: dict[str, Any]) -> None:
        progress: dict[str, Any] = {}
        if kind == "step":
            self.steps = int(data.get("step") or self.steps)
            progress["action"] = "Modell denkt"
        elif kind == "tool_start":
            self.tool_calls += 1
            self.requirement = data.get("requirement") or self.requirement
            progress["action"] = data.get("tool")
        elif kind == "tool" and data.get("is_error"):
            self.tool_errors += 1
        elif kind == "error":
            progress["action"] = "Fehler" if not data.get("retry") else "wartet auf Plattform"
        if kind in ("step", "usage", "tool", "error"):
            db.insert(
                self.conn, "run_events", run_id=self.run_id, phase=self.phase, ts=db.now(),
                seconds=data.get("seconds"), duration=data.get("duration"), step=data.get("step"),
                kind=kind, tool=data.get("tool"), requirement=data.get("requirement"),
                tokens_input=data.get("tokens_input"), tokens_output=data.get("tokens_output"),
                is_error=int(bool(data.get("is_error"))), text=data.get("text"),
            )  # fmt: skip
        if self.phase == "task":
            progress.update(steps=self.steps, tool_calls=self.tool_calls, tool_errors=self.tool_errors,
                            last_requirement=self.requirement or None)  # fmt: skip
        if progress:
            db.update(self.conn, "runs", {"id": self.run_id}, **progress)


# --------------------------------------------------------------------------- Vorabprüfung


async def _bw_ready(conn: sqlite3.Connection, batch: dict[str, Any], system: dict[str, Any]) -> bwcheck.Status:
    """Geduldige BW-Prüfung (bwcheck.probe_patient). Solange sie wartet, steht das am Durchgang."""
    loop = asyncio.get_running_loop()
    before = db.one(conn, "SELECT status_message FROM batches WHERE id=?", (batch["id"],))["status_message"]
    waited = False

    def note(text: str | None) -> None:
        db.update(conn, "batches", {"id": batch["id"]}, status_message=text)

    def report(attempt: int, of: int, status: bwcheck.Status) -> None:  # läuft im Prüf-Thread
        nonlocal waited
        waited = True
        print(f"  BW {system['id']} antwortet nicht (Versuch {attempt} von {of}: {status.detail}), "
              f"nächster Versuch in {bwcheck.PATIENT_PAUSE_S:.0f} s", flush=True)  # fmt: skip
        loop.call_soon_threadsafe(
            note, f"Das BW-System {system['id']} antwortet gerade nicht ({status.detail}). "
                  f"Der Durchgang wartet: Versuch {attempt + 1} von {of}.")  # fmt: skip

    status = await asyncio.to_thread(bwcheck.probe_patient, system["url"], report)
    if waited:
        await asyncio.sleep(0)  # ausstehende Meldung zuerst schreiben, dann zurücksetzen
        note(before)
        if status.state == bwcheck.OK:
            print(f"  BW {system['id']} antwortet wieder", flush=True)
    return status


async def preflight(conn: sqlite3.Connection, batch: dict[str, Any]) -> dict[str, Any]:
    """Prüft vor dem Start, ob der Durchgang laufen kann. Wirft RunnerError mit Abhilfe."""
    system = store.get_bw_system(conn, batch["bw_system"])
    if not system:
        raise RunnerError(f"Das BW-System „{batch['bw_system']}“ ist nicht mehr eingerichtet.")
    status = await _bw_ready(conn, batch, system)
    if status.state != bwcheck.OK:
        raise RunnerError(f"Das BW-System {system['id']} ist nicht bereit: {status.detail}. "
                          "Bitte das System starten und den Durchgang erneut ausführen.")  # fmt: skip
    try:
        resolved = mcpclient.resolve_server(conn, batch["mcp_server"], system)
        async with McpConnection(resolved) as mcp:
            tools = await mcp.list_tools()
            server_info = {"server_name": mcp.server_name, "server_version": mcp.server_version}
            parent_missing = await _parent_area_missing(mcp, tools, system)
    except (McpError, McpConfigError) as err:
        raise RunnerError(f"MCP-Server: {err}") from None
    if not tools:
        raise RunnerError(f"Der MCP-Server {batch['mcp_server']} stellt keine Werkzeuge bereit.")
    if parent_missing:
        raise RunnerError(
            f"Die Eltern-InfoArea {system['parent_area']} gibt es im BW-System {system['id']} nicht. Bitte im BW "
            "anlegen oder in den Einstellungen des BW-Systems eine vorhandene InfoArea eintragen."
        )
    model_ids = {r["model_id"] for r in db.rows(
        conn, "SELECT DISTINCT model_id FROM runs WHERE batch_id=? AND status='planned'", (batch["id"],))}  # fmt: skip
    for extra in (batch["verifier"], batch["fallback_verifier"]):
        if extra:
            model_ids.add(extra)
    platforms: dict[str, Any] = {}
    for model_id in sorted(model_ids):
        try:
            adapter, _mid, platform = adapter_for_model(conn, model_id)
            await adapter.aclose()
        except PlatformError as err:
            raise RunnerError(str(err)) from None
        platforms[platform["id"]] = {
            "type": platform["type"], "base_url": platform["base_url"],
            "caching": bool(platform["options"].get("caching", True)),
        }  # fmt: skip
    for row in db.rows(conn, "SELECT DISTINCT task_id, task_version FROM runs WHERE batch_id=?",
                       (batch["id"],)):  # fmt: skip
        if not tasks.stored_task(conn, row["task_id"], row["task_version"]):
            raise RunnerError(f"Aufgabe {row['task_id']} v{row['task_version']} fehlt in der Datenbank.")
    overrides = (mcpclient.get_server(conn, batch["mcp_server"]) or {}).get("tool_overrides") or {}
    return {
        "system": system,
        "tools": tools,
        "environment": {
            "app_version": __version__,
            "agent": AGENT_NAME,
            "agent_version": AGENT_VERSION,
            "system_prompt": SYSTEM_PROMPT,
            "bw_system": {k: system[k] for k in ("id", "url", "client", "language", "parent_area",
                                                 "area_pattern", "prefix")},
            "mcp_server": {
                "name": batch["mcp_server"], **server_info, **resolved.public(),
                "tool_count": len(tools), "tools_hash": mcpclient.tools_hash(tools),
                "token_estimate": mcpclient.estimate_tokens(tools),
                "tools": [{"name": t.name, "access": mcpclient.classify(t, overrides)} for t in tools],
            },
            "platforms": platforms,
            "limits": store.get_settings(conn)["run"],
            "python": sys.version.split()[0],
            "os": f"{py_platform.system()} {py_platform.release()}",
        },
    }  # fmt: skip


async def _parent_area_missing(mcp: McpConnection, tools: list[Any], system: dict[str, Any]) -> bool:
    """Prüft die Eltern-InfoArea, soweit der Server die Suche von coBWeb kennt. Im Zweifel: nicht fehlend."""
    if not any(t.name == "bw_search" for t in tools):
        return False
    from ..cleanup import parse_hits

    try:
        result = await mcp.call_tool("bw_search", {"query": system["parent_area"], "types": ["AREA"], "limit": 5}, 60)
    except McpError:
        return False
    if result.is_error:
        return False
    return not any(h["name"] == system["parent_area"] for h in parse_hits(result.text))


# --------------------------------------------------------------------------- Lauf und Prüfung


async def _run_phase(
    conn: sqlite3.Connection,
    *,
    batch: dict[str, Any],
    run: dict[str, Any],
    system: dict[str, Any],
    model_full_id: str,
    prompt: str,
    phase: str,
    limits: Limits,
    thinking: str,
    verify: bool,
    requirement_for: Any,
    log_path: Path,
) -> tuple[Outcome, str]:
    """Ein Aufruf des Agenten mit frischem MCP-Server. Liefert (Ergebnis, Hinweis)."""
    try:
        adapter, model_id, platform = adapter_for_model(conn, model_full_id)
    except PlatformError as err:
        return Outcome(status="error", error=str(err), error_kind=err.kind, finish_reason="platform_error"), ""
    recorder = _Recorder(conn, run["id"], phase)
    log = None
    try:
        resolved = mcpclient.resolve_server(conn, batch["mcp_server"], system, verify=verify)
        log = RunLog(log_path, _redactor(resolved, adapter))
        overrides = (mcpclient.get_server(conn, batch["mcp_server"]) or {}).get("tool_overrides") or {}
        async with McpConnection(resolved) as mcp:
            tools = await mcp.list_tools()
            offered = None
            if verify:
                offered = {t.name for t in tools if mcpclient.classify(t, overrides) == "read"}
            outcome = await run_agent(
                adapter=adapter, model=model_id, prompt=prompt, mcp=mcp, tools=tools, offered=offered,
                limits=limits, thinking=thinking, caching=bool(platform["options"].get("caching", True)),
                prices=store.get_model(conn, model_full_id), requirement_for=requirement_for,
                on_event=recorder, should_cancel=lambda: cancel_requested(conn, batch["id"]), log=log,
            )  # fmt: skip
    except (McpError, McpConfigError) as err:
        outcome = Outcome(status="error", error=str(err)[:1000], error_kind="mcp", finish_reason="mcp_error")
        if log:
            log.write("error", kind="mcp", message=str(err))
    finally:
        if log:
            log.close()
        await adapter.aclose()
    return outcome, ""


def _save_run(conn: sqlite3.Connection, run_id: int, outcome: Outcome, log_path: Path) -> None:
    u = outcome.usage
    redact = vault.Redactor()
    db.update(
        conn, "runs", {"id": run_id},
        status=outcome.status, finish_reason=outcome.finish_reason, seconds=outcome.seconds,
        model_seconds=outcome.model_seconds, tool_seconds=outcome.tool_seconds, steps=outcome.steps,
        tool_calls=outcome.tool_calls, tool_errors=outcome.tool_errors, api_retries=outcome.api_retries,
        last_requirement=outcome.last_requirement or None, tokens_input=u.input_total,
        tokens_output=u.output, tokens_cache_read=u.cache_read, tokens_cache_write=u.cache_write,
        tokens_reasoning=u.reasoning, cost_usd=outcome.cost, cost_source=outcome.cost_source,
        error=redact(outcome.error[:1000]) if outcome.error else None, error_kind=outcome.error_kind or None,
        answer=redact(outcome.text[:20000]), log_path=str(log_path),
        thinking_sent=db.dumps({"sent": outcome.thinking_sent, "effective": outcome.thinking_effective}),
        invalid=validity.classify(outcome.status, outcome.error_kind, outcome.error),
    )  # fmt: skip


async def _verify(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    batch: dict[str, Any],
    run: dict[str, Any],
    system: dict[str, Any],
    *,
    tool_calls: int,
    status: str,
    log_path: Path,
) -> dict[str, Any]:
    """Prüft einen Lauf mit dem Prüfmodell; liefert die Spalten für verifications."""
    if tool_calls == 0:
        return {"status": "not_verified", "reason": "Lauf ohne Werkzeugaufrufe"}
    if status == "cancelled":
        return {"status": "not_verified", "reason": "Lauf abgebrochen"}
    choice = choose_verifier(run["model_id"], batch["verifier"], batch["fallback_verifier"])
    if not choice.model_id:
        return {"status": "not_verified", "reason": choice.reason}
    task_row = tasks.stored_task(conn, run["task_id"], run["task_version"])
    assert task_row
    values = tasks.placeholder_values(
        run_code=run["run_code"], model=vendors.split_model_id(run["model_id"])[1],
        mcp_server=batch["mcp_server"], system=system,
    )  # fmt: skip
    db.update(conn, "runs", {"id": run["id"]}, phase="verify", action="Prüfung startet")
    outcome, _ = await _run_phase(
        conn, batch=batch, run=run, system=system, model_full_id=choice.model_id,
        prompt=tasks.fill(task_row["verify_prompt"], values), phase="verify",
        limits=_limits(settings, settings["verify"]["timeout_s"]), thinking=settings["verify"]["thinking"],
        verify=True, requirement_for=None, log_path=log_path,
    )  # fmt: skip
    verdict = parse_verdict(outcome.text)
    reasons = [choice.reason] if choice.reason else []
    status_v = verdict.status
    if outcome.write_attempts:
        status_v = "invalid"
        reasons.append("Prüfmodell wollte schreibende Werkzeuge aufrufen")
    elif outcome.status != "finished" and verdict.status == "unclear":
        status_v = "error"
        reasons.append(f"Prüflauf: {outcome.status} {outcome.error}".strip())
    redact = vault.Redactor()
    return {
        "status": status_v,
        "reason": "; ".join(r for r in reasons if r) or None,
        "verifier": choice.model_id,
        "points": db.dumps(verdict.points),
        "write_attempts": db.dumps(sorted(set(outcome.write_attempts))) if outcome.write_attempts else None,
        "seconds": outcome.seconds,
        "tokens_input": outcome.usage.input_total,
        "tokens_output": outcome.usage.output,
        "cost_usd": outcome.cost,
        "cost_source": outcome.cost_source,
        "answer": redact(outcome.text[:20000]),
        "log_path": str(log_path),
    }


def _store_verification(conn: sqlite3.Connection, run_id: int, values: dict[str, Any]) -> None:
    cols = ["run_id", *values.keys()]
    conn.execute(
        f"INSERT OR REPLACE INTO verifications({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        (run_id, *values.values()),
    )


async def _cleanup_before_retry(
    conn: sqlite3.Connection, batch: dict[str, Any], system: dict[str, Any], old_code: str
) -> None:
    """Entfernt die BW-Objekte des ersetzten Laufs. Fehler halten den Lauf nicht auf."""
    from .. import cleanup

    try:
        deleted, errors = await cleanup.clean_runs(conn, system, batch["mcp_server"], [old_code])
        print(f"  Bereinigen {old_code}: {deleted} Objekte gelöscht"
              + (f", {len(errors)} Fehler" if errors else ""), flush=True)  # fmt: skip
    except Exception as err:  # noqa: BLE001
        print(f"  Bereinigen {old_code} nicht möglich: {err}", flush=True)


# --------------------------------------------------------------------------- Durchgang


async def run_batch(conn: sqlite3.Connection, batch_id: int) -> str:
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        raise RunnerError(f"Durchgang {batch_id} gibt es nicht.")
    if batch["status"] != "planned":
        raise RunnerError(f"Durchgang {batch['code']} hat den Status „{batch['status']}“, nicht „geplant“.")
    busy = [b for b in running_batches(conn) if b["alive"] and b["id"] != batch_id]
    if busy:
        raise RunnerError(
            f"Durchgang {busy[0]['code']} läuft noch. Es läuft immer nur ein Durchgang, damit sich die "
            "Läufe im BW nicht stören."
        )
    settings = store.get_settings(conn)
    db.update(conn, "batches", {"id": batch_id}, status="running", started=db.now(), runner_pid=os.getpid(),
              status_message="Vorabprüfung")  # fmt: skip
    final, message = "done", ""
    try:
        try:
            pre = await preflight(conn, batch)
        except RunnerError as err:
            final, message = "error", str(err)
            print(f"Durchgang {batch['code']} startet nicht: {message}", flush=True)
            return final
        system = pre["system"]
        conn.execute("INSERT OR REPLACE INTO environments(batch_id, recorded, data) VALUES (?,?,?)",
                     (batch_id, db.now(), db.dumps(pre["environment"])))  # fmt: skip
        db.update(conn, "batches", {"id": batch_id}, status_message=None)
        runs = db.rows(conn, "SELECT * FROM runs WHERE batch_id=? AND status='planned' ORDER BY repeat, "
                             "position, id", (batch_id,))  # fmt: skip
        logs = log_dir(batch)
        print(f"Durchgang {batch['code']}: {len(runs)} Läufe, BW {system['id']}, MCP {batch['mcp_server']}, "
              f"Prüfmodell {batch['verifier'] or '-'}, Kostenlimit {batch['cost_limit']} $", flush=True)  # fmt: skip
        for index, run in enumerate(runs, start=1):
            if cancel_requested(conn, batch_id):
                final, message = "cancelled", "Abbruch angefordert"
                break
            spent, limit = batch_cost(conn, batch_id), batch["cost_limit"]
            if limit and spent >= limit:
                final, message = "cancelled", f"Kostenlimit erreicht ({spent:.2f} $ von {limit:.2f} $)"
                break
            # BW kann zwischen zwei Läufen ausfallen (z. B. pausiertes Demo-System, REQ F-D9). Ein einzelner
            # langsamer Ping ist kein Ausfall: Erst mehrere Fehlversuche halten den Durchgang an.
            state = await _bw_ready(conn, batch, system)
            if state.state != bwcheck.OK:
                final = "error"
                message = (f"Das BW-System {system['id']} ist nicht mehr erreichbar ({state.detail}). "
                           "Die übrigen Läufe wurden übersprungen und lassen sich später wiederholen.")  # fmt: skip
                break
            task_row = tasks.stored_task(conn, run["task_id"], run["task_version"])
            assert task_row
            model_id = vendors.split_model_id(run["model_id"])[1]
            print(f"\n[{index}/{len(runs)}] {run['run_code']} {run['model_id']} ({run['task_id']})", flush=True)
            if run["retry_of"]:
                old = db.one(conn, "SELECT run_code, status FROM runs WHERE id=?", (run["retry_of"],))
                if old and old["status"] != "skipped":  # ein übersprungener Lauf hat nichts angelegt
                    await _cleanup_before_retry(conn, batch, system, old["run_code"])
            db.update(conn, "runs", {"id": run["id"]}, status="running", phase="task", started=db.now(),
                      action="startet")  # fmt: skip
            values = tasks.placeholder_values(run_code=run["run_code"], model=model_id,
                                              mcp_server=batch["mcp_server"], system=system)  # fmt: skip
            requirements = task_row["requirements"]
            log_path = logs / f"{run['run_code']}_run.jsonl"
            outcome, _ = await _run_phase(
                conn, batch=batch, run=run, system=system, model_full_id=run["model_id"],
                prompt=tasks.fill(task_row["prompt"], values), phase="task",
                limits=_limits(settings, task_row["timeout_s"] or settings["run"]["timeout_s"]),
                thinking=run["thinking"] or "", verify=False,
                requirement_for=lambda tool, args, reqs=requirements: tasks.match_requirements(reqs, tool, args),
                log_path=log_path,
            )  # fmt: skip
            _save_run(conn, run["id"], outcome, log_path)
            verification = await _verify(
                conn, settings, batch, run, system, tool_calls=outcome.tool_calls, status=outcome.status,
                log_path=logs / f"{run['run_code']}_verify.jsonl",
            )  # fmt: skip
            _store_verification(conn, run["id"], verification)
            db.update(conn, "runs", {"id": run["id"]}, phase="done", finished=db.now(), action="fertig")
            cost = f"{outcome.cost:.3f} $" if outcome.cost is not None else "kein Preis"
            print(f"  {outcome.status} ({outcome.finish_reason or '-'}), {outcome.seconds:.0f} s, "
                  f"{outcome.steps} Schritte, {outcome.tool_calls} Werkzeugaufrufe, {cost}, "
                  f"Prüfung: {verification['status']}"
                  + (f" – {verification['reason']}" if verification.get("reason") else ""), flush=True)  # fmt: skip
            if outcome.status == "cancelled":
                final, message = "cancelled", "Abbruch angefordert"
                break
            if outcome.error_kind == "mcp":
                final = "error"
                message = (f"BW-System oder MCP-Server nicht erreichbar: {outcome.error[:300]} "
                           "Die übrigen Läufe wurden übersprungen und lassen sich später wiederholen.")  # fmt: skip
                break
    except asyncio.CancelledError:
        final, message = "cancelled", "Runner beendet"
        raise
    except Exception as err:
        final, message = "error", f"{type(err).__name__}: {err}"
        raise
    finally:
        _finalize(conn, batch_id, final, message)
    if message:
        print(f"\nDurchgang endet mit Status „{final}“: {message}", flush=True)
    return final


def _finalize(conn: sqlite3.Connection, batch_id: int, final: str, message: str) -> None:
    """Hinterlässt keinen Lauf im Status „läuft“."""
    conn.execute(
        "UPDATE runs SET status='cancelled', phase='done', finished=?, invalid=COALESCE(invalid, ?) "
        "WHERE batch_id=? AND status='running' AND phase='task'",
        (db.now(), validity.classify("cancelled", None, None), batch_id),
    )
    conn.execute("UPDATE runs SET phase='done', finished=COALESCE(finished, ?) WHERE batch_id=? AND "
                 "status<>'planned' AND phase<>'done'", (db.now(), batch_id))  # fmt: skip
    conn.execute("UPDATE runs SET status='skipped', phase='done', error=? WHERE batch_id=? AND status='planned'",
                 (message or None, batch_id))  # fmt: skip
    db.update(conn, "batches", {"id": batch_id}, status=final, finished=db.now(),
              status_message=message or None, runner_pid=None)  # fmt: skip


async def reverify(conn: sqlite3.Connection, batch_id: int, run_ids: list[int]) -> str:
    """Wiederholt nur die Prüfung der gewählten Läufe; die Läufe selbst bleiben unverändert."""
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        raise RunnerError(f"Durchgang {batch_id} gibt es nicht.")
    busy = [b for b in running_batches(conn) if b["alive"] and b["runner_pid"] != os.getpid()]
    if busy:
        raise RunnerError(f"Durchgang {busy[0]['code']} läuft noch.")
    runs = [db.one(conn, "SELECT * FROM runs WHERE id=? AND batch_id=?", (rid, batch_id)) for rid in run_ids]
    runs = [r for r in runs if r and r["status"] not in ("planned", "running", "skipped")]
    if not runs:
        raise RunnerError("Keine abgeschlossenen Läufe zum Prüfen gewählt.")
    system = store.get_bw_system(conn, batch["bw_system"])
    if not system:
        raise RunnerError(f"Das BW-System „{batch['bw_system']}“ ist nicht mehr eingerichtet.")
    settings = store.get_settings(conn)
    previous = batch["status"]
    logs = log_dir(batch)
    db.update(conn, "batches", {"id": batch_id}, status="running", runner_pid=os.getpid(), cancel_requested=0,
              status_message=f"Prüfung von {len(runs)} Läufen wird wiederholt")  # fmt: skip
    done = 0
    try:
        for run in runs:
            if cancel_requested(conn, batch_id):
                break
            log_path = logs / f"{run['run_code']}_verify.jsonl"
            if log_path.exists():
                n = 1
                while (logs / f"{run['run_code']}_verify_{n}.jsonl").exists():
                    n += 1
                log_path.rename(logs / f"{run['run_code']}_verify_{n}.jsonl")
            old = db.one(conn, "SELECT * FROM verifications WHERE run_id=?", (run["id"],))
            print(f"{run['run_code']}: Prüfung", flush=True)
            verification = await _verify(conn, settings, batch, run, system,
                                         tool_calls=int(run["tool_calls"] or 0), status=run["status"],
                                         log_path=log_path)  # fmt: skip
            verification["attempts"] = (int(old["attempts"] or 1) + 1) if old else 1
            verification["earlier_cost"] = ((old["earlier_cost"] or 0) + (old["cost_usd"] or 0)) if old else None
            _store_verification(conn, run["id"], verification)
            db.update(conn, "runs", {"id": run["id"]}, phase="done", action="fertig")
            print(f"  Prüfung: {verification['status']}", flush=True)
            done += 1
    finally:
        conn.execute("UPDATE runs SET phase='done' WHERE batch_id=? AND phase='verify'", (batch_id,))
        db.update(conn, "batches", {"id": batch_id}, status=previous, runner_pid=None, cancel_requested=0,
                  status_message=f"Prüfung von {done} Läufen wiederholt ({db.now()[:16]})")  # fmt: skip
    return "done"


def main(batch_id: int, verify_runs: list[int] | None = None) -> int:
    """Einstieg des Runner-Prozesses."""
    conn = db.connect()

    async def _go() -> str:
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()

        def _stop() -> None:  # SIGTERM/SIGINT: geordnet abbrechen, Läufe sauber markieren
            db.update(conn, "batches", {"id": batch_id}, cancel_requested=1)
            loop.call_later(20, task.cancel)  # type: ignore[union-attr]

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _stop)
            except (NotImplementedError, RuntimeError):
                pass
        if verify_runs:
            return await reverify(conn, batch_id, verify_runs)
        return await run_batch(conn, batch_id)

    try:
        final = asyncio.run(_go())
    except RunnerError as err:
        print(f"Fehler: {err}", file=sys.stderr, flush=True)
        return 1
    except asyncio.CancelledError:
        return 2
    return 0 if final == "done" else 2
