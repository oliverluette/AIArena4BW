"""Vorführmodus: erzeugt eine Beispiel-Datenbank, mit der sich die Oberfläche ohne BW-System und
ohne Schlüssel ansehen lässt.

Alle Werte sind erfunden, aber in sich stimmig (fester Zufallsstartwert). Die Modellnamen stehen
für typische Klassen von Modellen, nicht für gemessene Ergebnisse.
"""

from __future__ import annotations

import json
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import db, mcpclient, paths, store, tasks
from .agent import AGENT_NAME, AGENT_VERSION, SYSTEM_PROMPT
from .runs import validity

DEMO_NOTE = "Beispieldaten des Vorführmodus – keine gemessenen Ergebnisse"

# (Plattform, Modell-ID, Name, Preis ein/aus je Mio., Können 0–1, Tempo-Faktor, Tokens-Faktor)
MODELS = [
    ("openrouter", "anthropic/claude-haiku-5.5", "Claude Haiku 5.5", 0.10, 0.50, 0.88, 0.7, 0.9),
    ("openrouter", "anthropic/claude-sonnet-5.5", "Claude Sonnet 5.5", 2.0, 10.0, 0.96, 1.0, 1.0),
    ("openrouter", "anthropic/claude-opus-5.5", "Claude Opus 5.5", 4.0, 20.0, 0.99, 1.3, 1.1),
    ("openrouter", "openai/gpt-6-luna", "GPT-6 Luna", 0.25, 2.0, 0.84, 0.9, 1.2),
    ("openrouter", "openai/gpt-6-sol", "GPT-6 Sol", 1.75, 14.0, 0.95, 1.4, 1.3),
    ("openrouter", "google/gemini-3.8-flash", "Gemini 3.8 Flash", 0.30, 2.5, 0.80, 0.6, 1.1),
    ("openrouter", "google/gemini-3.1-pro-preview", "Gemini 3.1 Pro Preview", 2.0, 12.0, 0.92, 1.5, 1.4),
    ("openrouter", "qwen/qwen3.8-27b", "Qwen 3.8 27B", 0.04, 0.20, 0.55, 1.8, 1.6),
    ("openrouter", "deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", 0.14, 0.28, 0.72, 1.2, 1.3),
    ("openrouter", "mistralai/mistral-medium-3-5", "Mistral Medium 3.5", 0.40, 2.0, 0.68, 1.1, 1.2),
    ("lmstudio", "qwen3.8-27b-mlx", "Qwen 3.8 27B (lokal)", 0.0, 0.0, 0.50, 3.2, 1.6),
]
VERIFIER = "openrouter:anthropic/claude-haiku-5.5"
FALLBACK = "openrouter:anthropic/claude-sonnet-5.5"

# Durchgänge: (Code, Tage zurück, Aufgabe, Modelle (Index), Denkstufen, Wiederholungen, Notiz)
BATCHES: list[tuple[str, int, str, list[int], list[str], int, str]] = [
    ("AAA", 21, "bw-datenmodell-basis", [0, 1, 3, 5, 7], [""], 1, "erster Vergleich"),
    ("AAB", 18, "bw-datenmodell-basis", list(range(10)), ["medium"], 2, ""),
    ("AAC", 14, "bw-einkauf-datenfluss", [0, 1, 2, 4, 6, 8], ["medium"], 2, ""),
    ("AAD", 10, "bw-datenmodell-basis", [1, 4], ["low", "medium", "high"], 2, "Denkstufen im Vergleich"),
    ("AAE", 7, "bw-einkauf-datenfluss", [3, 5, 7, 9], ["medium"], 2, ""),
    ("AAF", 3, "bw-datenmodell-basis", [10, 7], [""], 3, "lokal gegen gehostet"),
    ("AAG", 1, "bw-einkauf-datenfluss", [0, 1, 2], ["high"], 1, ""),
]
TASK_SCALE = {"bw-datenmodell-basis": (1.0, 5), "bw-einkauf-datenfluss": (4.2, 14)}  # (Aufwand, Schritte)


def demo_dir() -> Path:
    return paths.data_dir() / "demo"


def create(target: Path | None = None) -> Path:
    """Legt die Beispiel-Datenbank neu an und gibt ihren Pfad zurück."""
    folder = target or demo_dir()
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    path = folder / "arena.db"
    conn = db.connect(path)
    rng = random.Random(4711)
    mcpclient.seed_default(conn)
    # Im Vorführmodus steht ein Beispielpfad im Eintrag, damit die Einrichtung vollständig wirkt.
    conn.execute(
        "UPDATE mcp_servers SET definition = replace(definition, ?, ?)",
        (mcpclient.COBWEB_PATH_HINT, "/opt/cobweb-mcp/dist/transport/stdio.js"),
    )
    conn.execute(
        "INSERT INTO bw_systems(id, url, client, user, language, parent_area, area_pattern, prefix, is_default, "
        "note, created) VALUES ('DEMO', 'https://bw.example.com:44300', '100', 'DEVELOPER', 'DE', 'ZBENCH_AI', "
        "'ZBENCH_{RUN}', 'ZB', 1, ?, ?)",
        (DEMO_NOTE, db.now()),
    )
    for pid, ptype, name, url in (
        ("openrouter", "openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
        ("lmstudio", "openai", "LM Studio", "http://localhost:1234/v1"),
    ):
        db.insert(conn, "platforms", id=pid, type=ptype, name=name, base_url=url, options='{"caching": true}',
                  created=db.now())  # fmt: skip
    for platform, model_id, name, price_in, price_out, *_ in MODELS:
        db.insert(
            conn, "models", id=f"{platform}:{model_id}", platform_id=platform, model_id=model_id, name=name,
            vendor=store.vendors.vendor_key(f"{platform}:{model_id}"), selected=1, in_catalog=1,
            price_in=price_in, price_out=price_out, price_cache_read=round(price_in * 0.1, 4),
            context_window=200000, supports_tools=1, supports_reasoning=1, first_seen=db.now(),
            max_tools=128 if model_id.startswith("openai/") else None,
        )  # fmt: skip
    store.save_settings(conn, {"verify": {"model": VERIFIER, "fallback": FALLBACK}})
    store.accept_notice(conn)  # Der Vorführmodus startet keine Läufe; der Hinweis würde nur die Bilder verdecken.
    task_by_id = {t.id: t for t in tasks.load_tasks()}
    for task in task_by_id.values():
        tasks.sync_task(conn, task)
    for code, days, task_id, model_idx, levels, repeats, note in BATCHES:
        if task_id in task_by_id:
            _batch(conn, rng, code, days, task_by_id[task_id], [MODELS[i] for i in model_idx], levels, repeats, note,
                   folder)  # fmt: skip
    conn.execute(
        "INSERT INTO saved_views(name, saved, is_default, settings) VALUES (?,?,1,?)",
        ("Kosten gegen Laufzeit", db.now(), json.dumps({
            "filters": {"tasks": ["bw-datenmodell-basis v4"]},
            "chart": {"x": "seconds", "y": "cost", "size": "", "color": "vendor", "level": "model", "labels": True},
        })),
    )  # fmt: skip
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


def _batch(
    conn: Any,
    rng: random.Random,
    code: str,
    days: int,
    task: tasks.Task,
    models: list[tuple],
    levels: list[str],
    repeats: int,
    note: str,
    folder: Path,
) -> None:
    created = datetime.now().astimezone() - timedelta(days=days, hours=rng.randint(0, 6))
    stamp = created.isoformat(timespec="seconds")
    batch_id = db.insert(
        conn, "batches", code=code, created=stamp, started=stamp, status="done", bw_system="DEMO",
        mcp_server=mcpclient.DEFAULT_SERVER, repeats=repeats, thinking=", ".join(lv for lv in levels if lv),
        verifier=VERIFIER, fallback_verifier=FALLBACK, cost_limit=50.0, cost_limit_planned=50.0,
        note=note or DEMO_NOTE,
        agent=AGENT_NAME, agent_version=AGENT_VERSION,
    )  # fmt: skip
    conn.execute(
        "INSERT INTO environments(batch_id, recorded, data) VALUES (?,?,?)",
        (batch_id, stamp, json.dumps({
            "app_version": "0.1.0", "agent": AGENT_NAME, "agent_version": AGENT_VERSION,
            "system_prompt": SYSTEM_PROMPT,
            "bw_system": {"id": "DEMO", "url": "https://bw.example.com:44300", "parent_area": "ZBENCH_AI",
                          "area_pattern": "ZBENCH_{RUN}", "prefix": "ZB"},
            "mcp_server": {"name": mcpclient.DEFAULT_SERVER, "server_name": "cobweb-mcp", "server_version": "1.3.0",
                           "transport": "stdio", "tool_count": 10, "token_estimate": 6400,
                           "tools": [{"name": n, "access": a} for n, a in (
                               ("bw_search", "read"), ("bw_read", "read"), ("bw_context", "read"),
                               ("bw_describe", "read"), ("bw_write", "write"), ("bw_activate", "write"))]},
            "platforms": {"openrouter": {"type": "openrouter", "caching": True}},
        }, ensure_ascii=False)),
    )  # fmt: skip
    combos = [(m, lv) for m in models for lv in levels]
    for pos, (model, level) in enumerate(combos, start=1):
        db.insert(conn, "batch_items", batch_id=batch_id, position=pos, task_id=task.id, task_version=task.version,
                  model_id=f"{model[0]}:{model[1]}", thinking=level)  # fmt: skip
    number, clock = 0, created
    for repeat in range(1, repeats + 1):
        for pos, (model, level) in enumerate(combos, start=1):
            number += 1
            clock = _run(conn, rng, batch_id, code, number, pos, repeat, task, model, level, clock, folder)
    db.update(conn, "batches", {"id": batch_id}, finished=clock.isoformat(timespec="seconds"))


def _run(
    conn: Any,
    rng: random.Random,
    batch_id: int,
    code: str,
    number: int,
    pos: int,
    repeat: int,
    task: tasks.Task,
    model: tuple,
    level: str,
    clock: datetime,
    folder: Path,
) -> datetime:
    platform, model_id, _name, price_in, price_out, skill, tempo, token_factor = model
    full_id = f"{platform}:{model_id}"
    effort, base_steps = TASK_SCALE.get(task.id, (1.0, 6))
    level_gain = {"": 0.0, "low": -0.05, "medium": 0.0, "high": 0.04, "xhigh": 0.06}.get(level, 0.0)
    level_cost = {"": 1.0, "low": 0.8, "medium": 1.0, "high": 1.35, "xhigh": 1.8}.get(level, 1.0)
    chance = max(0.03, min(0.995, skill + level_gain - (0.22 if effort > 2 else 0.0) * (1.25 - skill) * 2))
    run_code = f"{code}{number:02d}"
    roll = rng.random()
    status, error, error_kind = "finished", None, None
    if roll < 0.03:
        status, error, error_kind = "error", "Rate limit exceeded: too many requests", "rate_limit"
    elif roll < 0.06 and skill < 0.7:
        status, error = "timeout", f"Zeitlimit von {task.timeout_s} s erreicht"
    passed = status == "finished" and rng.random() < chance
    steps = max(2, round(base_steps * rng.uniform(0.8, 1.5) * (1.0 if passed else 1.3)))
    if status == "error":
        steps = rng.randint(1, 3)
    seconds = round(steps * rng.uniform(9, 16) * tempo * level_cost, 1)
    if status == "timeout":
        seconds = float(task.timeout_s)
    per_step_in = 6800 * token_factor
    tokens_input = round(sum(per_step_in + i * 900 * token_factor for i in range(steps)))
    cache_share = (
        rng.uniform(0.78, 0.93) if platform == "openrouter" and "claude" in model_id else rng.uniform(0.0, 0.55)
    )
    cache_read = round(tokens_input * cache_share)
    tokens_output = round(steps * rng.uniform(180, 420) * level_cost)
    reasoning = round(tokens_output * rng.uniform(0.2, 0.6)) if level else None
    cost = ((tokens_input - cache_read) * price_in + cache_read * price_in * 0.1 + tokens_output * price_out) / 1e6
    tool_calls = steps - 1 if status != "error" else max(0, steps - 1)
    tool_errors = rng.randint(0, 2) if not passed else rng.choice([0, 0, 0, 1])
    started = clock + timedelta(seconds=rng.randint(4, 12))
    finished = started + timedelta(seconds=seconds + 40)
    reqs = [r["name"] for r in task.requirements]
    reached = len(reqs) if passed or status == "finished" else max(1, len(reqs) // 2)
    log_dir = folder / "logs" / f"{code}_{batch_id}"
    log_path = log_dir / f"{run_code}_run.jsonl"
    run_id = db.insert(
        conn, "runs", batch_id=batch_id, position=pos, repeat=repeat, run_code=run_code, task_id=task.id,
        task_version=task.version, model_id=full_id, thinking=level,
        thinking_sent=json.dumps({"sent": {"reasoning": {"effort": level}} if level else None, "effective": True}),
        status=status, phase="done", action="fertig", finish_reason="end" if status == "finished" else status,
        started=started.isoformat(timespec="seconds"), finished=finished.isoformat(timespec="seconds"),
        seconds=seconds, model_seconds=round(seconds * 0.7, 1), tool_seconds=round(seconds * 0.28, 1), steps=steps,
        tool_calls=tool_calls, tool_errors=tool_errors, api_retries=0, last_requirement=reqs[reached - 1] if reqs else None,
        tokens_input=tokens_input, tokens_output=tokens_output, tokens_cache_read=cache_read, tokens_cache_write=0,
        tokens_reasoning=reasoning, cost_usd=round(cost, 5), cost_source="billed" if platform == "openrouter" else "computed",
        error=error, error_kind=error_kind,
        answer=("Alle Objekte sind angelegt und aktiv." if status == "finished" else ""),
        invalid=validity.classify(status, error_kind, error), log_path=str(log_path),
    )  # fmt: skip
    events, t = [], 0.0
    for step in range(1, steps + 1):
        t += seconds / steps * 0.6
        events.append(("task", t, None, step, "step", None, None, None, None, 0, None))
        events.append(("task", t, None, step, "usage", None, None, round(per_step_in + step * 900 * token_factor),
                       round(tokens_output / steps), 0, None))  # fmt: skip
        if step <= tool_calls:
            req = reqs[min(reached - 1, round((step - 1) * (reached - 1) / max(1, tool_calls - 1)))] if reqs else ""
            bad = step <= tool_errors
            t += seconds / steps * 0.4
            events.append(("task", t, round(seconds / steps * 0.4, 2), step, "tool", "bw_write" if step % 3 else "bw_read",
                           req, None, None, int(bad), "Activation failed: check log" if bad else None))  # fmt: skip
    if error:
        events.append(("task", seconds, None, steps, "error", None, None, None, None, 1, error))
    verify_status, points, verify_cost = "not_verified", [], None
    if status == "finished" and tool_calls:
        checkpoints = task.checkpoints or 6
        failing = (
            set() if passed else set(rng.sample(range(1, checkpoints + 1), rng.randint(1, max(1, checkpoints // 4))))
        )
        points = [{"nr": i, "ok": i not in failing,
                   "text": "vorhanden und aktiv" if i not in failing else "Objekt fehlt oder ist nicht aktiv"}
                  for i in range(1, checkpoints + 1)]  # fmt: skip
        verify_status = "pass" if passed else "fail"
        verify_cost = round(rng.uniform(0.004, 0.012) * (checkpoints / 6), 5)
        for step in range(1, 4):
            events.append(("verify", step * 6.0, 1.2, step, "tool", "bw_read", "", None, None, 0, None))
    for phase, sec, duration, step, kind, tool, req, tin, tout, is_error, text in events:
        db.insert(conn, "run_events", run_id=run_id, phase=phase, ts=started.isoformat(timespec="seconds"),
                  seconds=round(sec, 1), duration=duration, step=step, kind=kind, tool=tool, requirement=req,
                  tokens_input=tin, tokens_output=tout, is_error=is_error, text=text)  # fmt: skip
    verifier = FALLBACK if full_id == VERIFIER else VERIFIER
    db.insert(
        conn, "verifications", run_id=run_id, verifier=verifier if verify_status != "not_verified" else None,
        status=verify_status,
        reason=("Prüfmodell = Testmodell, Ersatzmodell prüft" if full_id == VERIFIER and points else None)
        if verify_status != "not_verified" else "Lauf ohne Ergebnis",
        points=json.dumps(points, ensure_ascii=False), seconds=24.0 if points else None,
        tokens_input=21000 if points else None, tokens_output=600 if points else None, cost_usd=verify_cost,
        cost_source="billed" if points else None,
        answer="\n".join(f"{p['nr']}. {'OK' if p['ok'] else 'FEHLER'} – {p['text']}" for p in points)
        + (f"\n\nVERDICT: {'PASS' if passed else 'FAIL'}" if points else ""),
    )  # fmt: skip
    if number <= 2:  # wenige Beispielprotokolle genügen
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as handle:
            for entry in (
                {"type": "meta", "s": 0, "model": model_id, "thinking": level, "tools": ["bw_search", "bw_read", "bw_write"],
                 "prompt": task.prompt[:400] + " …", "system": SYSTEM_PROMPT},
                {"type": "response", "s": 3.1, "step": 1, "text": "Ich lege zuerst die InfoArea an.",
                 "tool_calls": [{"id": "call_1", "name": "bw_write", "arguments": {"objects": [
                     {"action": "create", "type": "AREA", "name": f"ZBENCH_{run_code}"}], "activate": True}}],
                 "usage": {"input_total": round(per_step_in), "cache_read": 0, "output": 210}},
                {"type": "tool_result", "s": 5.4, "step": 1, "id": "call_1", "name": "bw_write", "is_error": False,
                 "duration": 2.3, "text": f"created AREA ZBENCH_{run_code}"},
                {"type": "response", "s": 9.8, "step": 2, "text": "Alle Objekte sind angelegt und aktiv.",
                 "tool_calls": [], "usage": {"input_total": round(per_step_in + 900), "cache_read": 5200, "output": 90}},
                {"type": "end", "s": 9.9, "status": status, "steps": steps},
            ):  # fmt: skip
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return finished
