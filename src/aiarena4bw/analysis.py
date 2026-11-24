"""Auswertung der Läufe: Kennzahlen, Bezeichnungen, Filter, Rangliste.

Begriffe:
  tokens_input   alle Eingabe-Tokens, einschließlich der aus dem Cache gelesenen
  tokens_new     tokens_input - tokens_cache_read (voll berechnete Eingabe)
  cost           Kosten des Laufs; None, wenn es keinen Preis gibt (nie 0 $)
  verified       Lauf hat ein verwertbares Urteil (pass oder fail)
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import statistics
from collections import defaultdict
from typing import Any

from . import db, mcpclient, store, vendors

FINISHED = {"finished", "error", "timeout", "step_limit", "cancelled", "mcp_missing", "no_result"}
THINKING_ORDER = ["aus", "low", "medium", "high", "xhigh", "ohne Vorgabe", "unbekannt"]
OWN_AGENT = "AIArena4BW"

RUN_QUERY = """
SELECT r.id, r.run_code, r.batch_id, b.code, b.created AS batch_created, b.hidden, b.bw_system,
       b.mcp_server, b.agent, b.agent_version, b.note AS batch_note,
       r.task_id, r.task_version, r.model_id, m.name AS model_name, r.repeat, r.position, r.status,
       r.finish_reason, r.started, r.finished, r.seconds, r.model_seconds, r.tool_seconds, r.steps,
       r.tool_calls, r.tool_errors, r.api_retries, r.last_requirement, r.tokens_input, r.tokens_output,
       r.tokens_cache_read, r.tokens_cache_write, r.tokens_reasoning, r.cost_usd, r.cost_source,
       r.thinking, r.thinking_sent, r.error, r.error_kind, r.invalid, r.retry_of, r.extra,
       COALESCE(v.status, 'not_verified') AS verify_status, v.verifier, v.reason AS verify_reason,
       v.cost_usd AS verify_cost, v.earlier_cost AS verify_earlier_cost
FROM runs r
JOIN batches b ON b.id = r.batch_id
LEFT JOIN models m ON m.id = r.model_id
LEFT JOIN verifications v ON v.run_id = r.id
"""

# Kennzahl -> (Feld, Beschriftung, Nachkommastellen); je Lauf und, als Median, je Modell.
METRICS: dict[str, tuple[str, str, int]] = {
    "seconds": ("seconds", "Laufzeit (s)", 0),
    "cost": ("cost", "Kosten ($)", 3),
    "tokens_input": ("tokens_input", "Eingabe-Tokens", 0),
    "tokens_new": ("tokens_new", "Eingabe-Tokens neu berechnet", 0),
    "tokens_cache": ("tokens_cache_read", "Eingabe-Tokens aus Cache", 0),
    "tokens_output": ("tokens_output", "Ausgabe-Tokens", 0),
    "tokens_reasoning": ("tokens_reasoning", "Denk-Tokens", 0),
    "steps": ("steps", "Schritte", 0),
    "tool_calls": ("tool_calls", "Werkzeugaufrufe", 0),
    "tool_errors": ("tool_errors", "Werkzeugfehler", 0),
    "verify_cost": ("verify_cost", "Prüfkosten ($)", 3),
}
MODEL_METRICS = {"pass_rate": ("pass_percent", "PASS-Quote (%)", 0)}


def short_name(name: str) -> str:
    """Knapper Modellname: "Claude Opus 5.5" -> "Opus 5.5", "Claude 4.5 Haiku" -> "Haiku 4.5"."""
    name = str(name).strip()
    match = re.match(r"^Claude\s+(.+)$", name)
    if not match:
        return name
    rest = match.group(1)
    swapped = re.match(r"^(\d[\d.]*)\s+(.+)$", rest)
    return f"{swapped.group(2)} {swapped.group(1)}" if swapped else rest


def thinking_label(run: dict[str, Any]) -> str:
    """Wirksame Denkstufe eines Laufs für Anzeige und Gruppierung."""
    extra = run.get("extra") or {}
    if extra.get("thinking_label"):  # von einem anderen Agenten gemeldete wirksame Stufe
        return str(extra["thinking_label"])
    level = (run.get("thinking") or "").strip()
    if not level:
        return "ohne Vorgabe"
    return "aus" if level == "none" else level


def load_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Alle abgeschlossenen Läufe mit Durchgang, Modell, Prüfung und abgeleiteten Feldern."""
    platforms = {p["id"]: p for p in store.list_platforms(conn)}
    reference_mcp = mcpclient.default_server(conn) or mcpclient.DEFAULT_SERVER
    runs = []
    for row in db.rows(conn, RUN_QUERY + " ORDER BY b.created, r.repeat, r.position, r.id"):
        if row["status"] not in FINISHED:
            continue
        platform_id, model_part = vendors.split_model_id(row["model_id"])
        platform = platforms.get(platform_id, {})
        row["extra"] = db.loads(row["extra"], {})
        row["platform"] = platform_id
        row["platform_name"] = platform.get("name") or platform_id
        row["platform_type"] = platform.get("type") or platform_id
        row["vendor"] = vendors.vendor_of(row["model_id"])
        row["model_name"] = row["model_name"] or model_part
        row["task"] = f"{row['task_id']} v{row['task_version']}"
        row["thinking"] = (row["thinking"] or "").strip()
        row["thinking_label"] = thinking_label(row)
        sent = db.loads(row.pop("thinking_sent"), {}) or {}
        row["thinking_effective"] = sent.get("effective", True) if isinstance(sent, dict) else True
        row["tokens_cache_read"] = row["tokens_cache_read"] or 0
        row["tokens_new"] = (
            max(0, row["tokens_input"] - row["tokens_cache_read"]) if row["tokens_input"] is not None else None
        )
        row["cost"] = row.pop("cost_usd")
        row["verified"] = row["verify_status"] in ("pass", "fail")
        row["passed"] = row["verify_status"] == "pass"
        row["valid"] = not row["invalid"]
        row["hidden"] = row["hidden"] or None
        row["agent_label"] = row["agent"] if row["agent"] == OWN_AGENT else (
            f"{row['agent']} {row['agent_version']}".strip())  # fmt: skip
        row["mcp_server"] = row["mcp_server"] or "unbekannt"
        row["reference_mcp"] = reference_mcp
        runs.append(row)
    _add_labels(runs, reference_mcp)
    return runs


def _add_labels(runs: list[dict[str, Any]], reference_mcp: str) -> None:
    """Bezeichnung je Lauf, so knapp wie möglich: "Opus 5.5", "Opus 5.5/xhigh",
    "Opus 5.5/xhigh/anderer-mcp", "Opus 5.5/<Agent>". Gleicher Name auf zwei Plattformen bekommt die
    Plattform dazu. So werden unterschiedliche Bedingungen nie gemittelt."""
    for run in runs:
        label = short_name(run["model_name"])
        if run["thinking"]:
            label += "/" + ("aus" if run["thinking"] == "none" else run["thinking"])
        if run["mcp_server"] != reference_mcp:
            label += "/" + run["mcp_server"]
        if run["agent"] != OWN_AGENT:
            label += "/" + run["agent"]
        run["label"] = label
    models_by_label: dict[str, set[str]] = defaultdict(set)
    for run in runs:
        models_by_label[run["label"]].add(run["model_id"])
    for run in runs:
        if len(models_by_label[run["label"]]) > 1:
            run["label"] += f" ({run['platform_name']})"


# --------------------------------------------------------------------------- Filter

FILTER_FIELDS = [
    ("tasks", "task"), ("systems", "bw_system"), ("batches", "code"), ("thinking", "thinking_label"),
    ("vendors", "vendor"), ("platforms", "platform_name"), ("mcp", "mcp_server"), ("agents", "agent_label"),
    ("models", "label"),
]  # fmt: skip


def _sorted_options(key: str, values: set[Any]) -> list[Any]:
    if key == "thinking":
        return sorted(values, key=lambda v: THINKING_ORDER.index(v) if v in THINKING_ORDER else 99)
    if key == "batches":
        return sorted(values, key=lambda c: (len(c), c), reverse=True)
    return sorted(values, key=lambda v: str(v).lower())


def apply_filters(runs: list[dict[str, Any]], spec: dict[str, Any] | None) -> tuple[list[dict], dict[str, list]]:
    """Filtert die Läufe. Die Auswahlliste jedes Filters folgt den Filtern davor."""
    spec = spec or {}
    current = runs
    if not spec.get("include_hidden"):
        current = [r for r in current if not r["hidden"]]
    if not spec.get("include_invalid"):
        current = [r for r in current if r["valid"]]
    only_platform = spec.get("only_platform")
    if only_platform:
        keys = {vendors.model_key(r["model_id"]) for r in runs if r["platform"] == only_platform}
        current = [r for r in current if vendors.model_key(r["model_id"]) in keys]
    options: dict[str, list] = {}
    for key, fld in FILTER_FIELDS:
        options[key] = _sorted_options(key, {r[fld] for r in current})
        chosen = [v for v in spec.get(key) or [] if v in options[key]]
        if chosen:
            current = [r for r in current if r[fld] in chosen]
    options["excluded"] = sorted({r["label"] for r in current})
    excluded = set(spec.get("excluded") or [])
    if excluded:
        current = [r for r in current if r["label"] not in excluded]
    return current, options


# --------------------------------------------------------------------------- Kennzahlen


def _median(values: list[Any]) -> float | None:
    numbers = [float(v) for v in values if v is not None]
    return statistics.median(numbers) if numbers else None


def summary_by_model(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kennzahlen je Eintrag (Modell + Denkstufe + MCP-Server + Agent). Mediane, damit Ausreißer
    nicht dominieren."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        groups[run["label"]].append(run)
    out = []
    for label, group in groups.items():
        first = group[0]
        finished = [r for r in group if r["status"] == "finished"]
        priced = [r for r in group if r["cost"] is not None]
        all_priced = len(priced) == len(group)
        passes = sum(r["passed"] for r in group)
        verified = sum(r["verified"] for r in group)
        cost_sum = sum(r["cost"] for r in priced) if priced else None
        seconds = [r["seconds"] for r in group if r["seconds"] is not None]
        out.append({
            "label": label,
            "model_id": first["model_id"],
            "model_name": first["model_name"],
            "vendor": first["vendor"],
            "platform_name": first["platform_name"],
            "thinking_label": first["thinking_label"],
            "mcp_server": first["mcp_server"],
            "agent_label": first["agent_label"],
            "runs": len(group),
            "finished": len(finished),
            "verified": verified,
            "passed": passes,
            "pass_rate": passes / verified if verified else None,
            "pass_percent": passes / verified * 100 if verified else None,
            "seconds": _median(seconds),
            # Laufzeit nur aus technisch beendeten Läufen: Abbrüche nach 2 s verzerren sonst.
            "seconds_finished": _median([r["seconds"] for r in finished]),
            "seconds_min": min(seconds) if seconds else None,
            "seconds_max": max(seconds) if seconds else None,
            "steps": _median([r["steps"] for r in group]),
            "tool_calls": _median([r["tool_calls"] for r in group]),
            "tool_errors": _median([r["tool_errors"] for r in group]),
            "tokens_input": _median([r["tokens_input"] for r in group]),
            "tokens_new": _median([r["tokens_new"] for r in group]),
            "tokens_cache_read": _median([r["tokens_cache_read"] for r in group if r["tokens_input"] is not None]),
            "tokens_output": _median([r["tokens_output"] for r in group]),
            "tokens_reasoning": _median([r["tokens_reasoning"] for r in group]),
            "price_known": all_priced,
            "cost": _median([r["cost"] for r in priced]) if all_priced else None,
            "cost_min": min((r["cost"] for r in priced), default=None) if all_priced else None,
            "cost_max": max((r["cost"] for r in priced), default=None) if all_priced else None,
            "cost_sum": cost_sum if all_priced else None,
            "cost_per_pass": (cost_sum / passes) if passes and cost_sum is not None and all_priced else None,
            "cost_source": "/".join(sorted({r["cost_source"] for r in priced if r["cost_source"]})) or None,
            "verify_cost": _median([r["verify_cost"] for r in group]),
            "verify_cost_sum": sum((r["verify_cost"] or 0) + (r["verify_earlier_cost"] or 0) for r in group),
        })  # fmt: skip
    # Feste Reihenfolge für alle Diagramme: nach Laufzeit der beendeten Läufe, Rest danach.
    out.sort(key=lambda s: (s["seconds_finished"] is None, s["seconds_finished"] or 0, s["label"]))
    return out


def leaderboard(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rangliste je Aufgabe: PASS-Quote, bei Gleichstand Kosten je erfolgreichem Lauf, dann Laufzeit."""
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_task[run["task"]].append(run)
    boards = []
    for task, group in by_task.items():
        entries = [e for e in summary_by_model(group) if e["verified"]]
        # Formkurve: die Läufe jedes Eintrags in zeitlicher Folge mit ihrem Urteil.
        form: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in sorted(group, key=lambda r: (r["started"] or "", r["id"])):
            verdict = run["verify_status"] if run["verify_status"] in ("pass", "fail") else "open"
            form[run["label"]].append({"id": run["id"], "run_code": run["run_code"], "verdict": verdict})
        entries.sort(key=lambda e: (
            -(e["pass_rate"] or 0),
            e["cost_per_pass"] is None, e["cost_per_pass"] or 0,
            e["seconds_finished"] is None, e["seconds_finished"] or 0, e["label"],
        ))  # fmt: skip
        rank, previous = 0, None
        for index, entry in enumerate(entries, start=1):
            key = (entry["pass_rate"], entry["cost_per_pass"], entry["seconds_finished"])
            if key != previous:
                rank, previous = index, key
            entry["rank"] = rank
            entry["form"] = form[entry["label"]]
        boards.append({"task": task, "task_id": group[0]["task_id"], "task_version": group[0]["task_version"],
                       "runs": len(group), "entries": entries})  # fmt: skip
    boards.sort(key=lambda b: (b["task_id"], -b["task_version"]))
    return boards


def analyse(conn: sqlite3.Connection, spec: dict[str, Any] | None) -> dict[str, Any]:
    all_runs = load_runs(conn)
    runs, options = apply_filters(all_runs, spec)
    return {
        "runs": [public_run(r) for r in runs],
        "summary": summary_by_model(runs),
        # Für das Vergleichsdiagramm mit „nur bestandene Läufe“: Mediane allein aus bestandenen Läufen.
        "summary_passed": summary_by_model([r for r in runs if r["passed"]]),
        "options": options,
        "counts": {
            "all": len(all_runs),
            "shown": len(runs),
            "invalid": sum(not r["valid"] for r in all_runs),
            "hidden": sum(bool(r["hidden"]) for r in all_runs),
        },
        "metrics": {k: {"field": f, "label": lab, "digits": d} for k, (f, lab, d) in METRICS.items()},
        "model_metrics": {k: {"field": f, "label": lab, "digits": d} for k, (f, lab, d) in MODEL_METRICS.items()},
        "platforms": [{"id": p["id"], "name": p["name"]} for p in store.list_platforms(conn)],
    }


_PUBLIC = [
    "id", "run_code", "batch_id", "code", "bw_system", "mcp_server", "agent_label", "task", "task_id",
    "task_version", "model_id", "model_name", "label", "vendor", "platform", "platform_name", "thinking",
    "thinking_label", "thinking_effective", "repeat", "status", "finish_reason", "started", "seconds",
    "model_seconds", "tool_seconds", "steps", "tool_calls", "tool_errors", "tokens_input", "tokens_new",
    "tokens_cache_read", "tokens_cache_write", "tokens_output", "tokens_reasoning", "cost", "cost_source",
    "verify_status", "verifier", "verify_cost", "verified", "passed", "valid", "invalid", "hidden",
    "retry_of", "error",
]  # fmt: skip


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {k: run.get(k) for k in _PUBLIC}


CSV_COLUMNS = [
    ("run_code", "Lauf"), ("code", "Durchgang"), ("task", "Aufgabe"), ("label", "Eintrag"),
    ("model_id", "Modell-ID"), ("vendor", "Anbieter"), ("platform_name", "Plattform"),
    ("thinking_label", "Denkstufe"), ("bw_system", "BW-System"), ("mcp_server", "MCP-Server"),
    ("agent_label", "Agent"), ("status", "Status"), ("verify_status", "Prüfung"), ("verifier", "Prüfmodell"),
    ("seconds", "Laufzeit (s)"), ("steps", "Schritte"), ("tool_calls", "Werkzeugaufrufe"),
    ("tool_errors", "Werkzeugfehler"), ("tokens_input", "Eingabe-Tokens"),
    ("tokens_new", "davon neu berechnet"), ("tokens_cache_read", "davon aus Cache"),
    ("tokens_output", "Ausgabe-Tokens"), ("tokens_reasoning", "Denk-Tokens"), ("cost", "Kosten ($)"),
    ("cost_source", "Kostenherkunft"), ("verify_cost", "Prüfkosten ($)"), ("invalid", "ungültig, weil"),
    ("started", "Start"),
]  # fmt: skip


def to_csv(runs: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([title for _, title in CSV_COLUMNS])
    for run in runs:
        row = []
        for key, _ in CSV_COLUMNS:
            value = run.get(key)
            if key == "cost" and value is None:
                value = "kein Preis"
            elif isinstance(value, float):
                value = f"{value:.4f}".replace(".", ",")
            row.append("" if value is None else value)
        writer.writerow(row)
    return buffer.getvalue()


# --------------------------------------------------------------------------- Lauf-Detail


def load_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    runs = [r for r in load_runs_any_status(conn, run_id)]
    if not runs:
        return None
    run = runs[0]
    verification = db.one(conn, "SELECT * FROM verifications WHERE run_id=?", (run_id,))
    if verification:
        verification["points"] = db.loads(verification["points"], [])
        verification["write_attempts"] = db.loads(verification["write_attempts"], [])
    task = db.one(conn, "SELECT requirements, checkpoints, title, timeout_s FROM tasks WHERE id=? AND version=?",
                  (run["task_id"], run["task_version"]))  # fmt: skip
    requirements = [r["name"] for r in db.loads(task["requirements"], [])] if task else []
    events = db.rows(conn, "SELECT phase, ts, seconds, duration, step, kind, tool, requirement, tokens_input, "
                           "tokens_output, is_error, text FROM run_events WHERE run_id=? ORDER BY id", (run_id,))  # fmt: skip
    retried_as = db.one(conn, "SELECT id, run_code FROM runs WHERE retry_of=?", (run_id,))
    retry_of = db.one(conn, "SELECT id, run_code FROM runs WHERE id=?", (run["retry_of"],)) if run["retry_of"] else None
    environment = db.one(conn, "SELECT data FROM environments WHERE batch_id=?", (run["batch_id"],))
    return {
        **public_run(run),
        "answer": run.get("answer"),
        "error_kind": run.get("error_kind"),
        "finished": run.get("finished"),
        "api_retries": run.get("api_retries"),
        "last_requirement": run.get("last_requirement"),
        "batch_note": run.get("batch_note"),
        "phase": run.get("phase"),
        "action": run.get("action"),
        "extra": run.get("extra"),
        "verification": verification,
        "task_title": task["title"] if task else "",
        "checkpoints": task["checkpoints"] if task else None,
        "timeout_s": task["timeout_s"] if task else None,
        "requirements": requirement_progress(events, requirements),
        "events": events,
        "retried_as": retried_as,
        "retry_of_run": retry_of,
        "environment": db.loads(environment["data"], {}) if environment else {},
    }


def load_runs_any_status(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Ein Lauf mit denselben abgeleiteten Feldern wie in der Auswertung, auch wenn er noch läuft."""
    row = db.one(conn, RUN_QUERY.replace("FROM runs r", ", r.answer, r.phase, r.action FROM runs r")
                 + " WHERE r.id=?", (run_id,))  # fmt: skip
    if not row:
        return []
    everything = load_runs(conn)
    match = next((r for r in everything if r["id"] == run_id), None)
    if match:
        match.update({k: row[k] for k in ("answer", "phase", "action")})
        return [match]
    # Noch nicht abgeschlossen: Minimalfelder ergänzen.
    platform_id, model_part = vendors.split_model_id(row["model_id"])
    row.update({
        "extra": db.loads(row["extra"], {}), "platform": platform_id, "platform_name": platform_id,
        "vendor": vendors.vendor_of(row["model_id"]), "model_name": row["model_name"] or model_part,
        "task": f"{row['task_id']} v{row['task_version']}", "label": short_name(row["model_name"] or model_part),
        "cost": row.pop("cost_usd"), "verified": False, "passed": False, "valid": not row["invalid"],
        "tokens_new": None, "agent_label": row["agent"], "thinking_effective": True,
    })  # fmt: skip
    row["thinking_label"] = thinking_label(row)
    return [row]


def requirement_progress(events: list[dict[str, Any]], requirements: list[str]) -> list[dict[str, Any]]:
    """Je Anforderung: erreicht ja/nein, erste Sekunde, Zahl der Werkzeugaufrufe."""
    tools = [e for e in events if e["kind"] == "tool" and e["phase"] == "task"]
    out = []
    for req in requirements:
        # Ein Aufruf kann mehrere Anforderungen bedienen ("1 InfoArea | 2 InfoObjects").
        hits = [e for e in tools if req in (e["requirement"] or "").split(" | ")]
        seconds = [e["seconds"] for e in hits if e["seconds"] is not None]
        out.append({"name": req, "reached": bool(hits), "first_second": min(seconds) if seconds else None,
                    "calls": len(hits), "errors": sum(bool(e["is_error"]) for e in hits)})  # fmt: skip
    return out


# --------------------------------------------------------------------------- Übersicht


def batch_overview(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.rows(
        conn,
        """
        SELECT b.*, COUNT(r.id) AS run_count,
               SUM(CASE WHEN r.status NOT IN ('planned', 'running') THEN 1 ELSE 0 END) AS runs_done,
               SUM(CASE WHEN v.status = 'pass' AND r.invalid IS NULL THEN 1 ELSE 0 END) AS passed,
               SUM(CASE WHEN v.status IN ('pass', 'fail') AND r.invalid IS NULL THEN 1 ELSE 0 END) AS verified,
               SUM(CASE WHEN r.invalid IS NOT NULL THEN 1 ELSE 0 END) AS invalid_runs,
               COALESCE(SUM(r.cost_usd), 0) AS run_cost,
               COALESCE(SUM(v.cost_usd), 0) + COALESCE(SUM(v.earlier_cost), 0) AS verify_cost,
               SUM(CASE WHEN r.cost_usd IS NULL AND r.status IN ('finished', 'error', 'timeout', 'step_limit')
                        THEN 1 ELSE 0 END) AS unpriced
        FROM batches b
        LEFT JOIN runs r ON r.batch_id = b.id
        LEFT JOIN verifications v ON v.run_id = r.id
        GROUP BY b.id ORDER BY b.created DESC, b.id DESC LIMIT ?
        """,
        (limit,),
    )
    for row in rows:
        row["alive"] = db.pid_alive(row["runner_pid"]) if row["status"] == "running" else False
        row["cost"] = (row.pop("run_cost") or 0) + (row.pop("verify_cost") or 0)
        row["other_agent"] = row["agent"] != OWN_AGENT
        tasks_models = db.one(
            conn, "SELECT COUNT(DISTINCT task_id) AS tasks, COUNT(DISTINCT model_id) AS models FROM runs "
                  "WHERE batch_id=?", (row["id"],))  # fmt: skip
        row["task_count"] = tasks_models["tasks"] if tasks_models else 0
        row["model_count"] = tasks_models["models"] if tasks_models else 0
    return rows
