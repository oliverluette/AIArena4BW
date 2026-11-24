"""BW bereinigen: Objekte der Läufe suchen und löschen – ohne Modell, über den MCP-Server.

Gelöscht wird nur, was genau der Namenskonvention des BW-Systems und der Laufkennung folgt:

    Lauf AAA03, Präfix ZB, Muster ZBENCH_{RUN}:  InfoArea ZBENCH_AAA03, sonstige ZBAAA03…

Transformationen, DTPs und Objekte an DataSources bekommen ihre Namen vom System; sie werden über
den Verwendungsnachweis der Objekte des Laufs gefunden.

Das Bereinigen nutzt die Werkzeuge von coBWeb (bw_search, bw_context, bw_write). Für Server ohne
diese Werkzeuge ist die Funktion gesperrt.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from typing import Any

from . import db, mcpclient, store
from .mcpclient import McpConnection, McpError
from .runs import codes

REQUIRED_TOOLS = ("bw_search", "bw_context", "bw_write")

# Löschreihenfolge: abhängige Objekte zuerst, InfoArea zuletzt (muss leer sein).
TYPE_ORDER = ["QUERY", "ELEM", "CKF", "RKF", "VARIABLE", "STRUCTURE", "FILTER", "DTPA", "TRFN", "HCPR",
              "ALVL", "ADSO", "RSDS", "TRCS", "IOBJ", "AREA"]  # fmt: skip
TYPES = set(TYPE_ORDER) | {"LSYS", "RSPC", "PLSE", "PLSQ", "HIER", "DEST", "ROLE"}
FLOW_TYPES = ("TRFN", "DTPA")  # Namen vom System vergeben
FLOW_OWNERS = ("ADSO", "RSDS")  # an diesen Objekten hängen Transformationen und DTPs

# Trefferzeile von coBWeb (bw_search, bw_context):
#   "ADSO   ZBAAD01B1     active    Bestellungen"
#   "RSDS  ZBAAD10CP (SELF)  unknown   Einkauf …"            (DataSource mit Quellsystem)
#   "  DTPA DTP_0UAX…     active    ADSO ZBAAD01E1 -> ADSO ZBAAD01B1"
LINE = re.compile(
    r"^\s*(?P<type>[A-Z]{3,9})\s+(?P<name>\S+)(?:\s+\((?P<src>[^)]*)\))?"
    r"\s+(?P<status>\S+)(?:\s+(?P<title>.*?))?\s*$"
)


class CleanupUnsupported(Exception):
    """Der MCP-Server hat nicht die Werkzeuge, die das Bereinigen braucht."""


def parse_hits(text: str) -> list[dict[str, str]]:
    """Treffer aus der Textausgabe von bw_search bzw. bw_context."""
    hits = []
    for line in text.splitlines():
        match = LINE.match(line)
        if match and match["type"] in TYPES:
            hits.append({
                "name": match["name"], "type": match["type"], "bw_status": match["status"],
                "source_system": match["src"] or "", "title": (match["title"] or "").strip(),
            })  # fmt: skip
    return hits


def patterns(system: dict[str, Any], run_part: str) -> tuple[re.Pattern, re.Pattern]:
    """(InfoArea-Muster, Objekt-Muster); run_part ist ein regulärer Ausdruck für die Laufkennung."""
    area = re.escape(str(system["area_pattern"])).replace(re.escape("{RUN}"), run_part)
    prefix = re.escape(str(system["prefix"]))
    return re.compile(rf"^{area}$"), re.compile(rf"^{prefix}{run_part}(?!\d)[A-Z0-9_]*$")


def code_run_part(code: str) -> str:
    codes.check_code(code)
    return rf"{code}\d{{{codes.digits(code)}}}"


def sort_for_delete(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {t: i for i, t in enumerate(TYPE_ORDER)}
    return sorted(objects, key=lambda o: (rank.get(o["type"], len(TYPE_ORDER) - 1), o["name"]))


def follows_convention(obj: dict[str, Any], system: dict[str, Any], run_part: str) -> bool:
    area_re, obj_re = patterns(system, run_part)
    if obj["type"] in FLOW_TYPES:
        return bool(obj_re.match(obj.get("via") or ""))
    return bool(area_re.match(obj["name"]) if obj["type"] == "AREA" else obj_re.match(obj["name"]))


async def _tool_text(mcp: McpConnection, tool: str, arguments: dict[str, Any], timeout_s: float = 120) -> str:
    result = await mcp.call_tool(tool, arguments, timeout_s)
    if result.is_error:
        raise McpError(result.text.strip()[:500] or f"{tool} meldet einen Fehler")
    return result.text


async def _search(mcp: McpConnection, query: str, types: list[str] | None = None) -> list[dict[str, str]]:
    arguments: dict[str, Any] = {"query": query, "limit": 500}
    if types:
        arguments["types"] = types
    return parse_hits(await _tool_text(mcp, "bw_search", arguments))


async def _add_flows(mcp: McpConnection, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ergänzt Transformationen und DTPs, die an gefundenen aDSOs und DataSources hängen."""
    found = {(o["type"], o["name"]): o for o in objects}
    for owner in [o for o in objects if o["type"] in FLOW_OWNERS]:
        arguments = {"type": owner["type"], "name": owner["name"], "relation": "where_used"}
        if owner.get("source_system"):
            arguments["source_system"] = owner["source_system"]
        try:
            text = await _tool_text(mcp, "bw_context", arguments)
        except McpError:
            continue
        for hit in parse_hits(text):
            if hit["type"] in FLOW_TYPES:
                found.setdefault((hit["type"], hit["name"]), {
                    **hit, "code": owner["code"], "run": owner.get("run", ""), "via": owner["name"],
                    "title": hit["title"] or f"an {owner['name']}",
                })  # fmt: skip
    return sort_for_delete(list(found.values()))


async def ensure_supported(mcp: McpConnection) -> None:
    names = {t.name for t in await mcp.list_tools()}
    missing = [t for t in REQUIRED_TOOLS if t not in names]
    if missing:
        raise CleanupUnsupported(
            "Bereinigen braucht die Werkzeuge bw_search, bw_context und bw_write (coBWeb). "
            f"Dieser Server hat {', '.join(missing)} nicht."
        )


def _run_of(name: str, system: dict[str, Any], code: str) -> str:
    """Laufkennung aus einem Objektnamen (für die Anzeige)."""
    part = code_run_part(code)
    area = re.escape(str(system["area_pattern"])).replace(re.escape("{RUN}"), f"({part})")
    match = re.match(rf"^{area}$", name) or re.match(rf"^{re.escape(system['prefix'])}({part})", name)
    return match.group(1) if match else ""


async def find(mcp: McpConnection, system: dict[str, Any], batch_codes: list[str]) -> list[dict[str, Any]]:
    """Objekte aller Läufe der genannten Durchgänge, in Löschreihenfolge, ohne Doppelte."""
    found: dict[tuple, dict[str, Any]] = {}
    for code in batch_codes:
        part = code_run_part(code)
        area_query = str(system["area_pattern"]).replace("{RUN}", f"{code}*")
        hits = await _search(mcp, area_query, ["AREA"]) + await _search(mcp, f"{system['prefix']}{code}*")
        for hit in hits:
            obj = {**hit, "code": code, "run": _run_of(hit["name"], system, code)}
            if hit["type"] not in FLOW_TYPES and follows_convention(obj, system, part):
                found.setdefault((hit["type"], hit["name"]), obj)
    return await _add_flows(mcp, list(found.values()))


async def find_runs(mcp: McpConnection, system: dict[str, Any], run_codes: list[str]) -> list[dict[str, Any]]:
    """Objekte einzelner Läufe, z. B. ["AAA03"]."""
    found: dict[tuple, dict[str, Any]] = {}
    for run in run_codes:
        code = codes.code_of(run)
        part = re.escape(run)
        area_query = str(system["area_pattern"]).replace("{RUN}", run)
        hits = await _search(mcp, area_query, ["AREA"]) + await _search(mcp, f"{system['prefix']}{run}*")
        for hit in hits:
            obj = {**hit, "code": code, "run": run}
            if hit["type"] not in FLOW_TYPES and follows_convention(obj, system, part):
                found.setdefault((hit["type"], hit["name"]), obj)
    return await _add_flows(mcp, list(found.values()))


async def delete_one(mcp: McpConnection, obj: dict[str, Any]) -> None:
    item: dict[str, Any] = {"action": "delete", "type": "QUERY" if obj["type"] == "ELEM" else obj["type"],
                            "name": obj["name"]}  # fmt: skip
    if obj.get("source_system"):
        item["source_system"] = obj["source_system"]
    text = await _tool_text(mcp, "bw_write", {"objects": [item], "activate": False})
    if not re.search(r"^\s*deleted\b", text, re.M | re.I):
        raise McpError(text.strip()[:500] or "nicht gelöscht")


async def clean_runs(
    conn: sqlite3.Connection, system: dict[str, Any], server: str, run_codes: list[str]
) -> tuple[int, list[str]]:
    """Löscht die Objekte einzelner Läufe (vor einer Wiederholung). (gelöscht, Fehlermeldungen)."""
    errors, deleted = [], 0
    resolved = mcpclient.resolve_server(conn, server, system)
    async with McpConnection(resolved) as mcp:
        await ensure_supported(mcp)
        for obj in await find_runs(mcp, system, run_codes):
            try:
                await delete_one(mcp, obj)
                deleted += 1
            except McpError as err:
                errors.append(f"{obj['type']} {obj['name']}: {str(err)[:200]}")
    return deleted, errors


# --------------------------------------------------------------------------- Aufträge


async def search(
    conn: sqlite3.Connection, system_id: str, server: str, *, batch_codes: list[str], run_codes: list[str]
) -> list[dict[str, Any]]:
    system = store.get_bw_system(conn, system_id)
    if not system:
        raise ValueError(f"BW-System „{system_id}“ gibt es nicht.")
    resolved = mcpclient.resolve_server(conn, server, system)
    async with McpConnection(resolved) as mcp:
        await ensure_supported(mcp)
        objects = await find(mcp, system, batch_codes) if batch_codes else []
        if run_codes:
            known = {(o["type"], o["name"]) for o in objects}
            objects += [o for o in await find_runs(mcp, system, run_codes) if (o["type"], o["name"]) not in known]
    return sort_for_delete(objects)


def plan(
    conn: sqlite3.Connection, system_id: str, server: str, objects: list[dict[str, Any]], scope: dict[str, Any]
) -> int:
    """Legt einen Löschauftrag an. Nimmt nur an, was der Namenskonvention folgt."""
    system = store.get_bw_system(conn, system_id)
    if not system:
        raise ValueError(f"BW-System „{system_id}“ gibt es nicht.")
    rows = []
    for obj in sort_for_delete(objects):
        part = re.escape(obj["run"]) if obj.get("run") else code_run_part(str(obj.get("code") or ""))
        if not follows_convention(obj, system, part):
            raise ValueError(f"{obj['name']} folgt nicht der Namenskonvention des BW-Systems {system_id}.")
        rows.append({k: obj.get(k, "") for k in ("code", "run", "type", "name", "bw_status", "title", "via",
                                                 "source_system")} | {"result": "open", "message": ""})  # fmt: skip
    if not rows:
        raise ValueError("Keine Objekte zum Löschen gewählt.")
    return db.insert(conn, "cleanup_jobs", created=db.now(), status="planned", bw_system=system_id,
                     mcp_server=server, scope=db.dumps(scope), objects=db.dumps(rows))  # fmt: skip


async def execute(conn: sqlite3.Connection, job_id: int) -> str:
    """Arbeitet einen Auftrag ab. Fehler einzelner Objekte brechen ihn nicht ab."""
    row = db.one(conn, "SELECT * FROM cleanup_jobs WHERE id=?", (job_id,))
    if not row or row["status"] != "planned":
        raise RuntimeError(f"Auftrag {job_id} ist nicht geplant.")
    objects = db.loads(row["objects"], [])
    system = store.get_bw_system(conn, row["bw_system"])
    db.update(conn, "cleanup_jobs", {"id": job_id}, status="running", started=db.now())

    def save(**extra: Any) -> None:
        db.update(conn, "cleanup_jobs", {"id": job_id}, objects=db.dumps(objects), **extra)

    try:
        if not system:
            raise McpError(f"BW-System „{row['bw_system']}“ gibt es nicht mehr.")
        resolved = mcpclient.resolve_server(conn, row["mcp_server"], system)
        async with McpConnection(resolved) as mcp:
            await ensure_supported(mcp)
            for obj in objects:
                cancel = conn.execute("SELECT cancel_requested FROM cleanup_jobs WHERE id=?", (job_id,)).fetchone()
                if cancel and cancel[0]:
                    save(status="cancelled", finished=db.now(), message="abgebrochen")
                    return "cancelled"
                try:
                    await delete_one(mcp, obj)
                    obj["result"], obj["message"] = "deleted", ""
                except McpError as err:
                    obj["result"], obj["message"] = "error", str(err)[:500]
                print(f"{obj['type']:5} {obj['name']:16} {obj['result']} {obj['message'][:120]}", flush=True)
                save()
            scope = db.loads(row["scope"], {})
            rest = await find(mcp, system, scope.get("codes") or []) if scope.get("codes") else []
            if scope.get("runs"):
                rest += await find_runs(mcp, system, scope["runs"])
    except (McpError, mcpclient.McpConfigError, CleanupUnsupported) as err:
        save(status="error", finished=db.now(), message=str(err)[:500])
        return "error"
    failed = sum(o["result"] == "error" for o in objects)
    message = f"{len(objects) - failed} gelöscht, {failed} Fehler, danach noch {len(rest)} im BW"
    status = "done" if not failed else "error"
    save(status=status, finished=db.now(), message=message, rest=db.dumps(rest))
    print(message, flush=True)
    return status


def main(job_id: int) -> int:
    conn = db.connect()
    return 0 if asyncio.run(execute(conn, job_id)) == "done" else 1
