"""Nachgebauter BW-MCP-Server (stdio, JSON-RPC) für Tests – ohne BW-System.

Verhält sich in den Punkten, die die App nutzt, wie coBWeb: bw_search, bw_read und bw_context
lesen, bw_write legt an, löscht und aktiviert. Der "Systemzustand" liegt in einer JSON-Datei
(FAKE_MCP_STATE), damit er frisch gestartete Serverinstanzen überdauert.

Steuerung über Umgebungsvariablen:
  FAKE_MCP_STATE          Pfad der Zustandsdatei
  FAKE_MCP_FAIL_START=1   Server beendet sich sofort (nicht startbar)
  FAKE_MCP_SLOW=name:sek  Werkzeug antwortet erst nach sek Sekunden
  FAKE_MCP_DIE_ON=name    Server beendet sich beim Aufruf dieses Werkzeugs (Verbindung verloren)
  COBWEB_ALLOW_WRITES=false   bw_write wird abgelehnt
  FAKE_MCP_NO_HINTS=1     Werkzeuge ohne readOnlyHint (Einstufung über Namensmuster)
  FAKE_MCP_TOOLS=a,b      nur diese Werkzeuge anbieten
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import time

STATE = os.environ.get("FAKE_MCP_STATE", "")


def load() -> dict:
    try:
        with open(STATE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        # Die Eltern-InfoArea gibt es im frischen "System" schon.
        return {
            "objects": {"AREA:ZBENCH_AI": {"type": "AREA", "name": "ZBENCH_AI", "status": "active", "title": "Eltern"}},
            "calls": [],
        }


def save(state: dict) -> None:
    if STATE:
        with open(STATE, "w", encoding="utf-8") as handle:
            json.dump(state, handle)


TOOLS = [
    {
        "name": "bw_search",
        "description": "Find BW objects by technical name. Wildcard * is allowed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "types": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "bw_read",
        "description": "Read the definition of one BW object.",
        "inputSchema": {
            "type": "object",
            "properties": {"type": {"type": "string"}, "name": {"type": "string"}},
            "required": ["type", "name"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "bw_context",
        "description": "Data flow and where-used of one BW object.",
        "inputSchema": {
            "type": "object",
            "properties": {"type": {"type": "string"}, "name": {"type": "string"}, "relation": {"type": "string"}},
            "required": ["type", "name"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "bw_write",
        "description": "Create, update or delete BW objects and activate them.",
        "inputSchema": {
            "type": "object",
            "properties": {"objects": {"type": "array", "items": {"type": "object"}}, "activate": {"type": "boolean"}},
            "required": ["objects"],
        },
        "annotations": {"readOnlyHint": False},
    },
]


def tool_list() -> list[dict]:
    tools = TOOLS
    only = [t for t in os.environ.get("FAKE_MCP_TOOLS", "").split(",") if t]
    if only:
        tools = [t for t in tools if t["name"] in only]
    if os.environ.get("FAKE_MCP_NO_HINTS"):
        tools = [{k: v for k, v in t.items() if k != "annotations"} for t in tools]
    return tools


def line(obj: dict) -> str:
    return f"{obj['type']:<6} {obj['name']:<16} {obj.get('status', 'active'):<9} {obj.get('title', '')}".rstrip()


def call(name: str, args: dict) -> tuple[str, bool]:
    state = load()
    state["calls"].append({"tool": name, "args": args})
    objects = state["objects"]
    try:
        if name == "bw_search":
            query = str(args.get("query") or "*")
            types = args.get("types") or []
            hits = [
                o
                for o in objects.values()
                if fnmatch.fnmatchcase(o["name"], query) and (not types or o["type"] in types)
            ]
            hits.sort(key=lambda o: (o["type"], o["name"]))
            return f'Search "{query}": {len(hits)} hits\n' + "\n".join(line(o) for o in hits), False
        if name == "bw_read":
            key = f"{args.get('type')}:{args.get('name')}"
            if key not in objects:
                return f"{args.get('type')} {args.get('name')} does not exist.", True
            obj = objects[key]
            return f"{line(obj)}\nStatus: {obj.get('status', 'active')}\nInfoArea: {obj.get('area', '')}", False
        if name == "bw_context":
            owner = str(args.get("name"))
            flows = [o for o in objects.values() if o.get("owner") == owner]
            return f"Where-used of {owner}\n" + "\n".join("  " + line(o) for o in flows), False
        if name == "bw_write":
            if os.environ.get("COBWEB_ALLOW_WRITES", "true").lower() == "false":
                return "not_allowed: this server may not write.", True
            out = []
            for item in args.get("objects") or []:
                action, typ, obj_name = item.get("action"), item.get("type"), item.get("name")
                key = f"{typ}:{obj_name}"
                if action == "delete":
                    if key in objects:
                        del objects[key]
                        out.append(f"deleted {typ} {obj_name}")
                    else:
                        out.append(f"failed {typ} {obj_name}: does not exist")
                elif action in ("create", "update"):
                    spec = item.get("spec") or {}
                    objects[key] = {
                        "type": typ,
                        "name": obj_name,
                        "status": "active" if args.get("activate", True) else "inactive",
                        "title": spec.get("description", ""),
                        "area": spec.get("info_area", ""),
                        "owner": spec.get("owner", ""),
                    }
                    out.append(f"{'created' if action == 'create' else 'changed'} {typ} {obj_name}")
                else:
                    return f"unknown action {action}", True
            return "\n".join(out), any(o.startswith("failed") for o in out)
        return f"Unknown tool {name}", True
    finally:
        save(state)


def respond(message_id, result=None, error=None) -> None:
    message = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    if os.environ.get("FAKE_MCP_FAIL_START"):
        sys.stderr.write("fake-bw: cannot reach BW system\n")
        sys.exit(3)
    slow_name, _, slow_s = os.environ.get("FAKE_MCP_SLOW", "").partition(":")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        method, message_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        if message_id is None:
            continue  # Benachrichtigung
        if method == "initialize":
            respond(
                message_id,
                {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-bw", "version": "0.1.0"},
                },
            )
        elif method == "ping":
            respond(message_id, {})
        elif method == "tools/list":
            respond(message_id, {"tools": tool_list()})
        elif method == "tools/call":
            name = params.get("name")
            if name == os.environ.get("FAKE_MCP_DIE_ON"):
                sys.exit(4)
            if name == slow_name and slow_s:
                time.sleep(float(slow_s))
            text, is_error = call(str(name), params.get("arguments") or {})
            respond(message_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
        else:
            respond(message_id, error={"code": -32601, "message": f"Method not found: {method}"})


if __name__ == "__main__":
    main()
