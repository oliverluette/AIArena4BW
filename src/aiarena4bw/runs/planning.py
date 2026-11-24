"""Durchgänge planen: Auswahl prüfen, Code vergeben, Läufe anlegen, Kosten schätzen."""

from __future__ import annotations

import sqlite3
import statistics
from typing import Any

from .. import db, mcpclient, store, tasks
from ..agent import AGENT_NAME, AGENT_VERSION
from . import codes

THINKING_ORDER = ["", "none", "low", "medium", "high", "xhigh"]
THINKING_LABEL = {"": "ohne Vorgabe", "none": "aus"}


class PlanError(ValueError):
    """Die Auswahl passt nicht; die Meldung sagt, was zu ändern ist."""


def used_codes(conn: sqlite3.Connection) -> set[str]:
    used = {r["code"] for r in db.rows(conn, "SELECT code FROM batches")}
    return used | set(store.get_settings(conn)["run"]["blocked_codes"])


def thinking_levels(value: Any) -> list[str]:
    """Denkstufen eines Durchgangs, ohne Doppelte, in fester Reihenfolge; leer = ohne Vorgabe."""
    if value is None or value == "":
        items = [""]
    elif isinstance(value, str):
        items = [v.strip().lower() for v in value.split(",")]
    else:
        items = [str(v or "").strip().lower() for v in value]
    items = ["" if v in ("-", "ohne", "ohne vorgabe", "standard") else v for v in items]
    bad = [v for v in items if v not in THINKING_ORDER]
    if bad:
        raise PlanError(f"Unbekannte Denkstufe {', '.join(bad)} (erlaubt: none, low, medium, high, xhigh "
                        "oder leer).")  # fmt: skip
    return sorted(dict.fromkeys(items) or [""], key=THINKING_ORDER.index)


def levels_text(levels: list[str]) -> str:
    if levels == [""]:
        return ""
    return ", ".join(THINKING_LABEL.get(lv, lv) for lv in levels)


def _resolve(conn: sqlite3.Connection, spec: dict[str, Any]) -> dict[str, Any]:
    """Prüft die Auswahl und liefert die aufgelösten Bestandteile."""
    settings = store.get_settings(conn)
    system = store.get_bw_system(conn, str(spec.get("bw_system") or ""))
    if not system or system["retired"]:
        raise PlanError("Bitte ein BW-System wählen (Einstellungen > BW-Systeme).")
    server = str(spec.get("mcp_server") or "")
    if not mcpclient.get_server(conn, server):
        raise PlanError("Bitte einen MCP-Server wählen (Einstellungen > MCP-Server).")
    chosen_tasks = []
    for task_id in spec.get("tasks") or []:
        task = tasks.get_task(str(task_id))
        if not task:
            raise PlanError(f"Aufgabe „{task_id}“ gibt es nicht.")
        chosen_tasks.append(task)
    if not chosen_tasks:
        raise PlanError("Bitte mindestens eine Aufgabe wählen.")
    models = []
    for model_id in dict.fromkeys(spec.get("models") or []):
        model = store.get_model(conn, str(model_id))
        if not model:
            raise PlanError(f"Modell „{model_id}“ ist nicht eingerichtet (Einstellungen > LLM-Plattformen).")
        models.append(model)
    if not models:
        raise PlanError("Bitte mindestens ein Modell wählen.")
    try:
        repeats = int(spec.get("repeats") or 1)
    except (TypeError, ValueError):
        raise PlanError("Wiederholungen müssen eine Zahl zwischen 1 und 9 sein.") from None
    if not 1 <= repeats <= 9:
        raise PlanError("Wiederholungen müssen zwischen 1 und 9 liegen.")
    levels = thinking_levels(spec["thinking"] if "thinking" in spec else settings["run"]["thinking"])
    combos = [(t, m, lv) for t in chosen_tasks for m in models for lv in levels]
    if len(combos) * repeats > codes.MAX_RUNS:
        raise PlanError(
            f"{len(combos)} Kombinationen aus Aufgabe, Modell und Denkstufe × {repeats} Wiederholungen "
            f"= {len(combos) * repeats} Läufe; höchstens {codes.MAX_RUNS} je Durchgang."
        )
    cost_limit = spec.get("cost_limit")
    if cost_limit in (None, ""):
        cost_limit = settings["run"]["cost_limit"]
    try:
        cost_limit = float(cost_limit)
    except (TypeError, ValueError):
        raise PlanError("Das Kostenlimit ist eine Zahl in Dollar (0 = kein Limit).") from None
    if cost_limit < 0:
        raise PlanError("Das Kostenlimit darf nicht negativ sein (0 = kein Limit).")
    return {
        "system": system,
        "server": server,
        "tasks": chosen_tasks,
        "models": models,
        "levels": levels,
        "repeats": repeats,
        "combos": combos,
        "verifier": str(spec.get("verifier") or settings["verify"]["model"] or ""),
        "fallback": str(spec.get("fallback") or settings["verify"]["fallback"] or ""),
        "cost_limit": cost_limit,
        "note": str(spec.get("note") or ""),
    }


def plan_batch(conn: sqlite3.Connection, spec: dict[str, Any]) -> int:
    """Legt einen Durchgang mit allen Läufen an (Status geplant) und gibt seine Nummer zurück."""
    r = _resolve(conn, spec)
    if not store.notice_accepted(conn):
        raise PlanError(
            "Bitte zuerst den Nutzungshinweis bestätigen (oben auf jeder Seite der App, "
            "oder `aiarena4bw run --accept-notice`)."
        )
    for task in r["tasks"]:
        tasks.sync_task(conn, task)
    try:
        code = codes.next_code(used_codes(conn))
    except codes.CodeError as err:
        raise PlanError(str(err)) from None
    conn.execute("BEGIN IMMEDIATE")
    try:
        batch_id = db.insert(
            conn, "batches", code=code, created=db.now(), status="planned", bw_system=r["system"]["id"],
            mcp_server=r["server"], repeats=r["repeats"], thinking=levels_text(r["levels"]),
            verifier=r["verifier"], fallback_verifier=r["fallback"], cost_limit=r["cost_limit"],
            cost_limit_planned=r["cost_limit"], note=r["note"], agent=AGENT_NAME, agent_version=AGENT_VERSION,
        )  # fmt: skip
        for pos, (task, model, level) in enumerate(r["combos"], start=1):
            db.insert(conn, "batch_items", batch_id=batch_id, position=pos, task_id=task.id,
                      task_version=task.version, model_id=model["id"], thinking=level)  # fmt: skip
        # Wiederholung außen, damit sich die Modelle zeitlich abwechseln.
        number = 0
        for repeat in range(1, r["repeats"] + 1):
            for pos, (task, model, level) in enumerate(r["combos"], start=1):
                number += 1
                db.insert(conn, "runs", batch_id=batch_id, position=pos, repeat=repeat,
                          run_code=codes.run_code(code, number), task_id=task.id, task_version=task.version,
                          model_id=model["id"], thinking=level, status="planned")  # fmt: skip
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return batch_id


def templates(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    """Frühere Durchgänge, die sich als Vorlage wählen lassen, neueste zuerst."""
    return db.rows(
        conn,
        """
        SELECT b.id, b.code, b.created, b.note, b.repeats,
               COUNT(DISTINCT i.task_id) AS tasks, COUNT(DISTINCT i.model_id) AS models
        FROM batches b JOIN batch_items i ON i.batch_id = b.id
        GROUP BY b.id ORDER BY b.created DESC, b.id DESC LIMIT ?
        """,
        (limit,),
    )


def template(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    """Die Auswahl eines früheren Durchgangs als Vorlage für einen neuen.

    `spec` enthält nur, was sich heute noch wählen lässt; `notes` nennt, was fehlt oder sich geändert hat.
    """
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        return None
    code = batch["code"]
    items = db.rows(
        conn, "SELECT task_id, task_version, model_id, thinking FROM batch_items WHERE batch_id=? ORDER BY position",
        (batch_id,))  # fmt: skip
    notes: list[dict[str, str]] = []

    def note(kind: str, text: str) -> None:
        notes.append({"kind": kind, "text": text})

    system = store.get_bw_system(conn, batch["bw_system"])
    if not system or system["retired"]:
        system = None
        note("bw_system", f"Das BW-System {batch['bw_system'] or '(ohne Angabe)'} ist nicht mehr wählbar. "
                          "Bitte die Auswahl prüfen.")  # fmt: skip
    server = batch["mcp_server"] if mcpclient.get_server(conn, batch["mcp_server"]) else None
    if not server:
        note("mcp_server", f"Den MCP-Server {batch['mcp_server'] or '(ohne Angabe)'} gibt es nicht mehr. "
                           "Bitte die Auswahl prüfen.")  # fmt: skip

    versions: dict[str, int] = {}
    for item in items:
        versions.setdefault(item["task_id"], item["task_version"])
    task_ids = []
    for task_id, version in versions.items():
        task = tasks.get_task(task_id)
        if not task:
            note("task_missing", f"Die Aufgabe „{task_id}“ gibt es nicht mehr.")
            continue
        task_ids.append(task_id)
        if task.version != version:
            note("task_version", f"Die Aufgabe „{task.title or task_id}“ liegt inzwischen in Version {task.version} "
                                 f"vor; {code} lief mit Version {version}.")  # fmt: skip

    selectable = {m["id"] for m in store.list_models(conn, selectable=True)}
    wanted = list(dict.fromkeys(item["model_id"] for item in items))
    gone = [store.model_display(conn, m) for m in wanted if m not in selectable]
    if gone:
        note("models", f"Nicht mehr wählbar und deshalb nicht übernommen: {', '.join(gone)} "
                       "(Einstellungen > LLM-Plattformen).")  # fmt: skip

    levels = [lv for lv in dict.fromkeys(item["thinking"] for item in items) if lv in THINKING_ORDER]
    settings = store.get_settings(conn)

    def verifier(model_id: str, label: str, setting: str) -> str:
        if not model_id:
            if setting:
                note("verifier", f"{code} lief ohne {label}; jetzt gilt die Einstellung.")
            return ""
        if not store.get_model(conn, model_id):
            note("verifier", f"Das {label} {model_id} ist nicht mehr eingerichtet; es gilt die Einstellung.")
            return ""
        return model_id

    if batch["cost_limit_planned"] is None and batch["cost_limit"] is not None:
        note("cost_limit", f"Das Kostenlimit von {code} ist nicht mehr bekannt: Es wurde bei Wiederholungen "
                           "angehoben, der ursprüngliche Wert ist nicht gespeichert. Es gilt die Vorgabe.")  # fmt: skip
    return {
        "id": batch["id"],
        "code": code,
        "spec": {
            "bw_system": system["id"] if system else None,
            "mcp_server": server,
            "tasks": task_ids,
            "models": [m for m in wanted if m in selectable],
            "thinking": sorted(levels or [""], key=THINKING_ORDER.index),
            "repeats": min(max(int(batch["repeats"] or 1), 1), 9),
            "verifier": verifier(batch["verifier"], "Prüfmodell", settings["verify"]["model"]),
            "fallback": verifier(batch["fallback_verifier"], "Ersatzmodell", settings["verify"]["fallback"]),
            "cost_limit": batch["cost_limit_planned"],
            "note": batch["note"],
        },
        "notes": notes,
    }


def preview(conn: sqlite3.Connection, spec: dict[str, Any]) -> dict[str, Any]:
    """Vorschau für „Durchgang starten“: Code, Laufzahl, Kostenschätzung, Hinweise."""
    r = _resolve(conn, spec)
    warnings: list[dict[str, str]] = []
    server = mcpclient.get_server(conn, r["server"]) or {}
    tool_count = (server.get("last_test") or {}).get("tool_count")
    for model in r["models"]:
        if model["max_tools"] and tool_count and model["max_tools"] < tool_count:
            warnings.append({"kind": "tool_limit", "text":
                             f"{model['name']} erlaubt höchstens {model['max_tools']} Werkzeuge, der "
                             f"MCP-Server stellt {tool_count} bereit."})  # fmt: skip
    if not server.get("last_test") or not (server.get("last_test") or {}).get("ok"):
        warnings.append({"kind": "mcp_untested", "text":
                         f"Der MCP-Server {r['server']} wurde noch nicht erfolgreich getestet "
                         "(Einstellungen > MCP-Server)."})  # fmt: skip
    for text in server.get("safety") or []:
        warnings.append({"kind": "mcp_safety", "text": f"{r['server']}: {text}"})
    if not r["verifier"]:
        warnings.append({"kind": "no_verifier", "text":
                         "Es ist kein Prüfmodell eingestellt; die Läufe bleiben ungeprüft."})  # fmt: skip
    else:
        from .verify import choose_verifier

        for model in r["models"]:
            choice = choose_verifier(model["id"], r["verifier"], r["fallback"])
            if not choice.model_id:
                warnings.append({"kind": "verifier_same", "text":
                                 f"{model['name']} ist das Prüfmodell und es gibt kein anderes "
                                 "Ersatzmodell: Diese Läufe bleiben ungeprüft."})  # fmt: skip
            elif choice.reason:
                warnings.append({"kind": "verifier_fallback", "text":
                                 f"{model['name']} ist das Prüfmodell; das Ersatzmodell prüft diese Läufe."})  # fmt: skip
    platforms = {p["id"]: p for p in store.list_platforms(conn)}
    external = sorted({platforms[m["platform_id"]]["name"] for m in r["models"]
                       if m["platform_id"] in platforms and platforms[m["platform_id"]]["external"]})  # fmt: skip
    if external:
        warnings.append({"kind": "data", "text":
                         "Aufgabentext, Werkzeugbeschreibungen und Antworten des BW-Systems gehen an "
                         f"{', '.join(external)} und die Modellanbieter. Nur mit Test- und Demosystemen "
                         "arbeiten."})  # fmt: skip
    no_price = [m["name"] for m in r["models"]
                if m["price_in"] is None and platforms.get(m["platform_id"], {}).get("type") != "openrouter"]  # fmt: skip
    if no_price:
        warnings.append({"kind": "no_price", "text":
                         f"Ohne Preis: {', '.join(no_price)}. Das Kostenlimit erfasst diese Läufe nicht."})  # fmt: skip
    if any(r["levels"]) and (silent := [m["name"] for m in r["models"] if m["supports_reasoning"] is False]):
        warnings.append({"kind": "no_reasoning", "text":
                         f"Laut Katalog ohne Denkstufen: {', '.join(silent)}. Die gewählte Stufe bleibt dort "
                         "voraussichtlich ohne Wirkung; die App vermerkt das am Lauf."})  # fmt: skip
    if not r["system"]["password_set"]:
        warnings.append({"kind": "bw_password", "text":
                         f"Für das BW-System {r['system']['id']} ist kein Passwort hinterlegt."})  # fmt: skip
    try:
        code = codes.next_code(used_codes(conn))
    except codes.CodeError as err:
        raise PlanError(str(err)) from None
    estimate = estimate_cost(conn, [(t.id, m["id"]) for t, m, _ in r["combos"]], r["repeats"])
    return {
        "code": code,
        "runs": len(r["combos"]) * r["repeats"],
        "combinations": len(r["combos"]),
        "repeats": r["repeats"],
        "levels": r["levels"],
        "cost_limit": r["cost_limit"],
        "verifier": r["verifier"],
        "fallback": r["fallback"],
        "estimate": estimate,
        "warnings": warnings,
    }


def estimate_cost(conn: sqlite3.Connection, pairs: list[tuple[str, str]], repeats: int) -> dict[str, Any]:
    """Schätzung aus früheren gültigen Läufen: Median je Aufgabe und Modell plus Median einer Prüfung."""
    total, known = 0.0, 0
    verify_costs = [r["c"] for r in db.rows(
        conn, "SELECT cost_usd AS c FROM verifications WHERE cost_usd IS NOT NULL AND cost_usd > 0")]  # fmt: skip
    verify_median = statistics.median(verify_costs) if verify_costs else None
    for task_id, model_id in pairs:
        costs = [r["c"] for r in db.rows(
            conn,
            "SELECT cost_usd AS c FROM runs WHERE task_id=? AND model_id=? AND cost_usd IS NOT NULL "
            "AND invalid IS NULL AND status IN ('finished', 'timeout', 'step_limit', 'error')",
            (task_id, model_id),
        )]  # fmt: skip
        if costs:
            known += 1
            total += statistics.median(costs) + (verify_median or 0.0)
    return {
        "usd": round(total * repeats, 4) if known else None,
        "known": known,
        "total": len(pairs),
        "verify_median": verify_median,
    }
