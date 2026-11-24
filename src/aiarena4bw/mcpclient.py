"""MCP-Server: Definition als JSON, Platzhalter, Verbindung, Einstufung der Werkzeuge.

Die Definition folgt dem Aufbau von LM Studio bzw. Claude Desktop:

    {"mcpServers": {"<name>": {"command": "...", "args": [...], "env": {...}}}}      (stdio)
    {"mcpServers": {"<name>": {"url": "https://…", "headers": {...}}}}               (HTTP)

Platzhalter ${BW_URL}, ${BW_USER}, … werden erst beim Start mit den Werten des gewählten
BW-Systems gefüllt; ${SECRET:name} holt einen benannten Eintrag aus dem Schlüsselbund.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db, store, vault

DEFAULT_SERVER = "coBWeb-mcp"
COBWEB_PATH_HINT = "/Pfad/zu/coBWeb-mcp/dist/transport/stdio.js"
# Werkzeuge, die die Aufgaben und das Aufräumen brauchen; ohne bw_transport (Transporte,
# Verschieben zwischen InfoAreas), bw_data und bw_run.
COBWEB_TOOLS = "bw_search,bw_read,bw_context,bw_describe,bw_write,bw_activate,bw_system"
DEFAULT_DEFINITION: dict[str, Any] = {
    "command": "node",
    "args": [COBWEB_PATH_HINT],
    "env": {
        "BW_URL": "${BW_URL}",
        "BW_CLIENT": "${BW_CLIENT}",
        "BW_USER": "${BW_USER}",
        "BW_PASSWORD": "${BW_PASSWORD}",
        "BW_LANGUAGE": "${BW_LANGUAGE}",
        "COBWEB_TOOLS": COBWEB_TOOLS,
        "COBWEB_ALLOW_WRITES": "true",
        "COBWEB_ALLOWED_INFOAREAS": "${BW_PARENT_AREA},${BW_AREA_GLOB}",
        "COBWEB_ALLOWED_PACKAGES": "$TMP",
    },
}
DEFAULT_VERIFY_ENV = {"COBWEB_ALLOW_WRITES": "false"}

# Werkzeugsätze der coBWeb-Profile (COBWEB_PROFILE), wie in coBWeb dokumentiert.
COBWEB_PROFILES = {
    "modeling": {"bw_search", "bw_read", "bw_context", "bw_describe", "bw_write", "bw_activate", "bw_transport",
                 "bw_system"},
    "analysis": {"bw_search", "bw_read", "bw_context", "bw_data"},
    "operations": {"bw_search", "bw_read", "bw_monitor", "bw_run", "bw_system"},
    "full": {"bw_search", "bw_read", "bw_context", "bw_describe", "bw_write", "bw_activate", "bw_data",
             "bw_monitor", "bw_run", "bw_transport", "bw_system"},
}  # fmt: skip

PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]+))?\}")
BW_PLACEHOLDERS = (
    "BW_URL", "BW_CLIENT", "BW_USER", "BW_PASSWORD", "BW_LANGUAGE", "BW_PARENT_AREA", "BW_PREFIX",
    "BW_AREA_GLOB", "BW_SYSTEM",
)  # fmt: skip

# Namensteile, die ein Werkzeug als schreibend ausweisen, wenn der Server nichts dazu sagt.
WRITE_WORDS = {
    "create", "update", "activate", "delete", "write", "run", "set", "unlock", "lock", "move",
    "change", "push", "remove", "append", "add", "swap", "transport", "execute", "start", "load",
    "save", "copy", "rename", "release", "import", "edit", "insert", "drop", "trigger",
}  # fmt: skip


class McpConfigError(ValueError):
    """Die Definition passt nicht; die Meldung nennt Stelle und Ursache."""


class McpError(Exception):
    """Server nicht startbar, Protokollfehler oder Verbindung verloren."""


class McpTimeout(McpError):
    """Ein Werkzeug hat nicht rechtzeitig geantwortet; die Verbindung besteht weiter."""


# --------------------------------------------------------------------------- Definition


def parse_definition(text: str) -> dict[str, dict[str, Any]]:
    """Prüft den JSON-Text und liefert {name: eintrag}."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise McpConfigError(f"Kein gültiges JSON: Zeile {err.lineno}, Spalte {err.colno}: {err.msg}.") from None
    if not isinstance(data, dict):
        raise McpConfigError('Erwartet wird ein Objekt der Form {"mcpServers": {…}}.')
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        raise McpConfigError('Der Schlüssel "mcpServers" fehlt. Aufbau: {"mcpServers": {"name": {…}}}.')
    out: dict[str, dict[str, Any]] = {}
    for name, entry in servers.items():
        where = f'Server "{name}"'
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", str(name)):
            raise McpConfigError(f"{where}: Der Name darf nur Buchstaben, Ziffern, Punkt, - und _ enthalten.")
        if not isinstance(entry, dict):
            raise McpConfigError(f"{where}: Erwartet wird ein Objekt.")
        has_cmd, has_url = bool(entry.get("command")), bool(entry.get("url"))
        if has_cmd == has_url:
            raise McpConfigError(f'{where}: Genau eines von "command" (stdio) oder "url" (HTTP) angeben.')
        if has_cmd:
            if not isinstance(entry["command"], str):
                raise McpConfigError(f'{where}: "command" ist ein Text.')
            args = entry.get("args", [])
            if not isinstance(args, list) or not all(isinstance(a, str | int | float) for a in args):
                raise McpConfigError(f'{where}: "args" ist eine Liste von Texten.')
            _check_map(entry.get("env", {}), f'{where}: "env"')
        else:
            if not isinstance(entry["url"], str) or not re.match(r"^(https?://|\$\{)", entry["url"]):
                raise McpConfigError(f'{where}: "url" beginnt mit http:// oder https://.')
            _check_map(entry.get("headers", {}), f'{where}: "headers"')
        for value in _strings(entry):
            for match in PLACEHOLDER.finditer(value):
                key, arg = match.group(1), match.group(2)
                if key == "SECRET" and arg:
                    continue
                if key not in BW_PLACEHOLDERS or arg:
                    raise McpConfigError(
                        f"{where}: Unbekannter Platzhalter {match.group(0)}. Erlaubt: "
                        + ", ".join("${%s}" % p for p in BW_PLACEHOLDERS)
                        + ", ${SECRET:name}."
                    )
        out[str(name)] = entry
    return out


def _check_map(value: Any, where: str) -> None:
    if not isinstance(value, dict) or not all(isinstance(v, str | int | float | bool) for v in value.values()):
        raise McpConfigError(f"{where} ist ein Objekt aus Name und Wert.")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def plaintext_secrets(entry: dict[str, Any]) -> list[str]:
    """Schlüssel in env/headers, deren Wert wie ein Geheimnis im Klartext aussieht."""
    found = []
    for block in ("env", "headers"):
        for key, value in (entry.get(block) or {}).items():
            if vault.looks_like_secret(key, value):
                found.append(f"{block}.{key}")
    return found


def _flag(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _items(value: Any) -> list[str]:
    return [p.strip() for p in str(value or "").split(",") if p.strip()]


def is_cobweb(entry: dict[str, Any]) -> bool:
    env = entry.get("env") or {}
    text = " ".join([str(entry.get("command") or ""), *map(str, entry.get("args") or []), str(entry.get("url") or "")])
    return any(str(k).startswith("COBWEB_") for k in env) or "cobweb" in text.lower()


def safety(entry: dict[str, Any], verify_env: dict[str, Any] | None = None) -> list[str]:
    """Hinweise, wo ein MCP-Server mehr darf als nötig. Die App warnt nur, sie sperrt nichts.

    Bei coBWeb lässt sich das an den Umgebungsvariablen ablesen; bei anderen Servern nicht."""
    if not is_cobweb(entry):
        return [
            "Die App kann bei diesem Server nicht prüfen, ob er Schreibzugriffe begrenzt. Stelle im Server "
            "selbst ein, dass nur in der Test-InfoArea und im Paket $TMP geschrieben werden darf."
        ]
    env = entry.get("env") or {}
    notes = []
    if _flag(env.get("COBWEB_ALLOW_WRITES")):
        areas = _items(env.get("COBWEB_ALLOWED_INFOAREAS"))
        if not areas or "*" in areas:
            notes.append(
                "Der Server darf in jeder InfoArea schreiben. Setze COBWEB_ALLOWED_INFOAREAS auf "
                "${BW_PARENT_AREA},${BW_AREA_GLOB}."
            )
        packages = [p.upper() for p in _items(env.get("COBWEB_ALLOWED_PACKAGES"))] or ["$TMP"]
        other = [p for p in packages if p != "$TMP"]
        if other:
            notes.append(
                f"Der Server darf auch in die Pakete {', '.join(other)} schreiben, nicht nur in $TMP. "
                "Setze COBWEB_ALLOWED_PACKAGES auf $TMP."
            )
    explicit = set(_items(env.get("COBWEB_TOOLS")))
    profile = str(env.get("COBWEB_PROFILE") or "modeling").strip().lower()
    tools = explicit or COBWEB_PROFILES.get(profile, COBWEB_PROFILES["full"])
    if "bw_transport" in tools and _flag(env.get("COBWEB_ALLOW_WRITES")):
        notes.append(
            "Der Server bietet bw_transport an: Damit kann ein Modell Transportaufträge anlegen und Objekte "
            f"zwischen InfoAreas verschieben. Die Aufgaben brauchen das nicht; COBWEB_TOOLS={COBWEB_TOOLS} "
            "lässt es weg."
        )
    if "bw_run" in tools and _flag(env.get("COBWEB_ALLOW_EXECUTE")):
        notes.append("Der Server darf Ladeprozesse und Prozessketten ausführen (COBWEB_ALLOW_EXECUTE).")
    if "bw_data" in tools and _flag(env.get("COBWEB_ALLOW_DATA")):
        notes.append(
            "Der Server liest Geschäftsdaten (COBWEB_ALLOW_DATA). Sie gehen dann an die Plattform und den "
            "Modellanbieter."
        )
    verify = {**env, **(verify_env or {})}
    if _flag(verify.get("COBWEB_ALLOW_WRITES")):
        notes.append(
            "Für das Prüfmodell sind Schreibzugriffe nicht abgeschaltet. Trage unter „Abweichende "
            "Umgebungswerte für die Prüfung“ COBWEB_ALLOW_WRITES=false ein."
        )
    return notes


@dataclass
class Resolved:
    """Startbereite Definition; enthält Geheimnisse und wird nie gespeichert oder ausgegeben."""

    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        """Für die Umgebung eines Durchgangs: ohne Umgebungswerte und Header."""
        if self.url:
            return {"transport": "http", "url": self.url}
        return {"transport": "stdio", "command": self.command, "args": self.args}


def bw_values(system: dict[str, Any]) -> dict[str, str]:
    password = vault.get(vault.bw_password(system["id"])) or ""
    return {
        "BW_SYSTEM": system["id"],
        "BW_URL": system["url"],
        "BW_CLIENT": system["client"],
        "BW_USER": system["user"],
        "BW_PASSWORD": password,
        "BW_LANGUAGE": system["language"],
        "BW_PARENT_AREA": system["parent_area"],
        "BW_PREFIX": system["prefix"],
        "BW_AREA_GLOB": str(system["area_pattern"]).replace("{RUN}", "*"),
    }


def resolve(
    name: str, entry: dict[str, Any], system: dict[str, Any] | None, extra_env: dict[str, str] | None = None
) -> Resolved:
    """Setzt Platzhalter ein. Fehlende Werte führen zu einer Meldung mit Abhilfe."""
    values = bw_values(system) if system else {}
    secrets: list[str] = []
    if values.get("BW_PASSWORD"):
        secrets.append(values["BW_PASSWORD"])

    def fill(text: Any) -> str:
        def repl(match: re.Match) -> str:
            key, arg = match.group(1), match.group(2)
            if key == "SECRET":
                value = vault.get(vault.named(arg or ""))
                if not value:
                    raise McpConfigError(
                        f'Server "{name}": Das Geheimnis „{arg}“ ist nicht im Schlüsselbund hinterlegt '
                        "(Einstellungen > MCP-Server > Geheimnisse)."
                    )
                secrets.append(value)
                return value
            if not system:
                raise McpConfigError(f'Server "{name}" braucht ein BW-System für {match.group(0)}.')
            if key == "BW_PASSWORD" and not values[key]:
                raise McpConfigError(
                    f"Für das BW-System „{system['id']}“ ist kein Passwort hinterlegt (Einstellungen > BW-Systeme)."
                )
            return values[key]

        return PLACEHOLDER.sub(repl, str(text))

    resolved = Resolved(name=name, secrets=secrets, users=[values["BW_USER"]] if values.get("BW_USER") else [])
    if entry.get("url"):
        resolved.url = fill(entry["url"])
        resolved.headers = {k: fill(v) for k, v in (entry.get("headers") or {}).items()}
    else:
        resolved.command = fill(entry["command"])
        resolved.args = [fill(a) for a in entry.get("args", [])]
        resolved.env = {k: fill(v) for k, v in (entry.get("env") or {}).items()}
        resolved.env.update({k: fill(v) for k, v in (extra_env or {}).items()})
    for block in ("env", "headers"):
        for key, value in (entry.get(block) or {}).items():
            if vault.looks_like_secret(key, value):
                secrets.append(str(value))
    return resolved


# --------------------------------------------------------------------------- Werkzeuge


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only_hint: bool | None = None

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def classify(tool: Tool, overrides: dict[str, str] | None = None) -> str:
    """'read' oder 'write': Überschreibung, sonst Angabe des Servers, sonst Namensmuster."""
    override = (overrides or {}).get(tool.name)
    if override in ("read", "write"):
        return override
    if tool.read_only_hint is not None:
        return "read" if tool.read_only_hint else "write"
    words = {w for w in re.split(r"[^a-z]+", tool.name.lower()) if w}
    return "write" if words & WRITE_WORDS else "read"


def tools_hash(tools: list[Tool]) -> str:
    payload = json.dumps([t.definition() for t in tools], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def estimate_tokens(tools: list[Tool]) -> int:
    """Grobe Token-Last der Werkzeugdefinitionen je Anfrage (rund 4 Zeichen je Token)."""
    payload = json.dumps([t.definition() for t in tools], ensure_ascii=False)
    return round(len(payload) / 4)


@dataclass
class ToolResult:
    text: str
    is_error: bool = False


# --------------------------------------------------------------------------- Verbindung


def find_command(command: str) -> str:
    if os.path.sep in command:
        return os.path.expanduser(command)
    found = shutil.which(command)
    if found:
        return found
    # Aus einer App gestartet fehlt oft der PATH der Shell (Homebrew, Volta, nvm).
    for folder in ("/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".volta/bin")):
        candidate = Path(folder) / command
        if candidate.exists():
            return str(candidate)
    raise McpError(f"Befehl „{command}“ nicht gefunden (PATH).")


class McpConnection:
    """Verbindung zu einem MCP-Server. Verwendung: `async with McpConnection(resolved) as mcp:`.

    Ein stdio-Server läuft in einem leeren Arbeitsordner außerhalb des Projekts.
    """

    def __init__(self, resolved: Resolved, *, start_timeout_s: float = 60):
        self.resolved = resolved
        self.start_timeout_s = start_timeout_s
        self.server_name = ""
        self.server_version = ""
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._workdir: str | None = None
        self._errlog: Any = None

    async def __aenter__(self) -> McpConnection:
        try:
            await asyncio.wait_for(self._open(), timeout=self.start_timeout_s)
        except TimeoutError:
            await self._close()
            raise McpError(
                f"MCP-Server „{self.resolved.name}“ antwortet nicht innerhalb von {self.start_timeout_s:.0f} s."
            ) from None
        except McpError:
            await self._close()
            raise
        except BaseException as err:
            detail = self._stderr_tail()
            await self._close()
            if isinstance(err, asyncio.CancelledError | KeyboardInterrupt):
                raise
            message = _flatten(err)
            raise McpError(
                f"MCP-Server „{self.resolved.name}“ nicht startbar: {message}" + (f" – {detail}" if detail else "")
            ) from None
        return self

    async def _open(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        r = self.resolved
        if r.url:
            from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

            http_client = create_mcp_http_client(headers=r.headers or None)
            streams = await self._stack.enter_async_context(streamable_http_client(r.url, http_client=http_client))
        else:
            self._workdir = tempfile.mkdtemp(prefix="aiarena4bw-mcp-")
            self._errlog = open(Path(self._workdir) / "stderr.log", "w+", encoding="utf-8")  # noqa: SIM115
            params = StdioServerParameters(
                command=find_command(r.command or ""), args=r.args, env=r.env or None, cwd=self._workdir
            )
            streams = await self._stack.enter_async_context(stdio_client(params, errlog=self._errlog))
        session = await self._stack.enter_async_context(ClientSession(streams[0], streams[1]))
        init = await session.initialize()
        info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
        self.server_name = getattr(info, "name", "") or ""
        self.server_version = getattr(info, "version", "") or ""
        self._session = session

    async def __aexit__(self, *exc: Any) -> None:
        await self._close()

    async def _close(self) -> None:
        stack, self._stack, self._session = self._stack, None, None
        if stack:
            try:
                await asyncio.wait_for(stack.aclose(), timeout=15)
            except BaseException as err:  # Aufräumen darf nie einen Lauf abbrechen
                if isinstance(err, KeyboardInterrupt):
                    raise
        if self._errlog:
            try:
                self._errlog.close()
            except OSError:
                pass
            self._errlog = None
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    def _stderr_tail(self) -> str:
        if not self._errlog:
            return ""
        try:
            self._errlog.flush()
            self._errlog.seek(0)
            lines = [ln.strip() for ln in self._errlog.read().splitlines() if ln.strip()]
        except (OSError, ValueError):
            return ""
        redact = vault.Redactor(self.resolved.secrets, self.resolved.users)
        return redact(" | ".join(lines[-3:])[:400]) or ""

    async def list_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        cursor = None
        for _ in range(50):
            if cursor:
                from mcp import types

                result = await self._session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
            else:
                result = await self._session.list_tools()
            for tool in result.tools:
                data = tool.model_dump(by_alias=True, exclude_none=True)
                schema = data.get("inputSchema") or data.get("input_schema") or {"type": "object"}
                annotations = data.get("annotations") or {}
                hint = annotations.get("readOnlyHint", annotations.get("read_only_hint"))
                tools.append(Tool(
                    name=data["name"], description=data.get("description") or "", input_schema=schema,
                    read_only_hint=hint if isinstance(hint, bool) else None,
                ))  # fmt: skip
            cursor = getattr(result, "next_cursor", None) or getattr(result, "nextCursor", None)
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any], timeout_s: float = 120) -> ToolResult:
        """Ruft ein Werkzeug auf. Fehler des Werkzeugs kommen als ToolResult(is_error=True);
        Zeitüberschreitung und Verbindungsabbruch als McpError."""
        try:
            result = await asyncio.wait_for(self._session.call_tool(name, arguments), timeout=timeout_s)
        except TimeoutError:
            raise McpTimeout(f"Werkzeug {name}: keine Antwort nach {timeout_s:.0f} s.") from None
        except asyncio.CancelledError:
            raise
        except Exception as err:
            message = _flatten(err)
            if _is_protocol_error(err):
                return ToolResult(text=message, is_error=True)
            raise McpError(f"Werkzeug {name}: Verbindung zum MCP-Server verloren ({message}).") from None
        data = result.model_dump(by_alias=True, exclude_none=True)
        parts = []
        for block in data.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict):
                parts.append(f"[{block.get('type', 'Inhalt')}]")
        text = "\n".join(parts)
        if not text and data.get("structuredContent") is not None:
            text = json.dumps(data["structuredContent"], ensure_ascii=False)
        return ToolResult(text=text, is_error=bool(data.get("isError") or data.get("is_error")))


def _is_protocol_error(err: Exception) -> bool:
    """Fehlerantwort des Servers (JSON-RPC error) im Unterschied zu einer toten Verbindung."""
    detail = getattr(err, "error", None)
    if detail is None and type(err).__name__ not in ("McpError", "MCPError"):
        return False
    code = getattr(detail, "code", None)
    message = str(getattr(detail, "message", "") or err).lower()
    return code != -32000 and "connection closed" not in message


def _flatten(err: BaseException) -> str:
    """Text einer Ausnahme; bei Ausnahmegruppen der erste eigentliche Fehler."""
    inner = getattr(err, "exceptions", None)
    while inner:
        err = inner[0]
        inner = getattr(err, "exceptions", None)
    return (str(err) or type(err).__name__)[:400]


# --------------------------------------------------------------------------- Ablage


def seed_default(conn: sqlite3.Connection) -> None:
    """Trägt coBWeb als Standard ein, wenn noch nie ein Server gespeichert wurde."""
    if db.one(conn, "SELECT value FROM meta WHERE key='mcp_seeded'"):
        return
    if not db.one(conn, "SELECT 1 AS x FROM mcp_servers"):
        db.insert(
            conn, "mcp_servers", name=DEFAULT_SERVER, definition=db.dumps(DEFAULT_DEFINITION),
            is_default=1, verify_env=db.dumps(DEFAULT_VERIFY_ENV), created=db.now(),
        )  # fmt: skip
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('mcp_seeded', '1')")


def server_public(row: dict[str, Any]) -> dict[str, Any]:
    entry = db.loads(row["definition"], {})
    return {
        "name": row["name"],
        "is_default": bool(row["is_default"]),
        "transport": "http" if entry.get("url") else "stdio",
        "needs_path": COBWEB_PATH_HINT in json.dumps(entry),
        "tool_overrides": db.loads(row["tool_overrides"], {}),
        "verify_env": db.loads(row["verify_env"], {}),
        "last_test": db.loads(row["last_test"]),
        "plaintext_secrets": plaintext_secrets(entry),
        "safety": safety(entry, db.loads(row["verify_env"], {})),
    }


def list_servers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [server_public(r) for r in db.rows(conn, "SELECT * FROM mcp_servers ORDER BY position, created, name")]


def get_entry(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT definition FROM mcp_servers WHERE name=?", (name,))
    return db.loads(row["definition"], {}) if row else None


def get_server(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM mcp_servers WHERE name=?", (name,))
    return server_public(row) if row else None


def default_server(conn: sqlite3.Connection) -> str | None:
    row = db.one(conn, "SELECT name FROM mcp_servers ORDER BY is_default DESC, position, created LIMIT 1")
    return row["name"] if row else None


def definition_text(conn: sqlite3.Connection) -> str:
    servers = {
        r["name"]: db.loads(r["definition"], {})
        for r in db.rows(conn, "SELECT name, definition FROM mcp_servers ORDER BY position, created, name")
    }
    return json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False)


def save_definition_text(conn: sqlite3.Connection, text: str) -> list[dict[str, Any]]:
    """Ersetzt alle Server durch den JSON-Text. Einstufungen und Testergebnisse gleichnamiger
    Server bleiben erhalten."""
    servers = parse_definition(text)
    existing = {r["name"]: r for r in db.rows(conn, "SELECT * FROM mcp_servers")}
    for position, (name, entry) in enumerate(servers.items()):
        if name in existing:
            changed = db.loads(existing[name]["definition"], {}) != entry
            db.update(
                conn, "mcp_servers", {"name": name}, definition=db.dumps(entry), position=position,
                **({"last_test": None} if changed else {}),
            )  # fmt: skip
        else:
            db.insert(conn, "mcp_servers", name=name, definition=db.dumps(entry), position=position,
                      created=db.now())  # fmt: skip
    for name in existing:
        if name not in servers:
            conn.execute("DELETE FROM mcp_servers WHERE name=?", (name,))
    if servers and not db.one(conn, "SELECT 1 AS x FROM mcp_servers WHERE is_default=1"):
        set_default_server(conn, next(iter(servers)))
    return list_servers(conn)


def set_default_server(conn: sqlite3.Connection, name: str) -> None:
    conn.execute("UPDATE mcp_servers SET is_default = (name = ?)", (name,))


def save_server_options(
    conn: sqlite3.Connection, name: str, *, tool_overrides: dict | None = None, verify_env: dict | None = None
) -> dict[str, Any]:
    if not db.one(conn, "SELECT 1 AS x FROM mcp_servers WHERE name=?", (name,)):
        raise store.StoreError(f"MCP-Server „{name}“ gibt es nicht.")
    values: dict[str, Any] = {}
    if tool_overrides is not None:
        clean = {str(k): v for k, v in tool_overrides.items() if v in ("read", "write")}
        values["tool_overrides"] = db.dumps(clean)
    if verify_env is not None:
        values["verify_env"] = db.dumps({str(k): str(v) for k, v in verify_env.items() if str(k).strip()})
    db.update(conn, "mcp_servers", {"name": name}, **values)
    return get_server(conn, name)  # type: ignore[return-value]


def resolve_server(
    conn: sqlite3.Connection, name: str, system: dict[str, Any] | None, *, verify: bool = False
) -> Resolved:
    row = db.one(conn, "SELECT * FROM mcp_servers WHERE name=?", (name,))
    if not row:
        raise McpConfigError(f"MCP-Server „{name}“ ist nicht eingerichtet (Einstellungen > MCP-Server).")
    entry = db.loads(row["definition"], {})
    if COBWEB_PATH_HINT in json.dumps(entry):
        raise McpConfigError(
            f"Im Eintrag „{name}“ steht noch der Platzhalter-Pfad. Bitte in den Einstellungen den "
            "tatsächlichen Pfad zu dist/transport/stdio.js eintragen."
        )
    extra = db.loads(row["verify_env"], {}) if verify else None
    return resolve(name, entry, system, extra)


async def test_server(conn: sqlite3.Connection, name: str, system: dict[str, Any] | None) -> dict[str, Any]:
    """Startet den Server, ruft die Werkzeugliste ab und speichert das Ergebnis."""
    row = db.one(conn, "SELECT * FROM mcp_servers WHERE name=?", (name,))
    overrides = db.loads(row["tool_overrides"], {}) if row else {}
    try:
        resolved = resolve_server(conn, name, system)
        async with McpConnection(resolved) as mcp:
            tools = await mcp.list_tools()
            result = {
                "ok": True,
                "at": db.now(),
                "bw_system": system["id"] if system else "",
                "server_name": mcp.server_name,
                "server_version": mcp.server_version,
                "tool_count": len(tools),
                "token_estimate": estimate_tokens(tools),
                "tools_hash": tools_hash(tools),
                "tools": [
                    {
                        "name": t.name,
                        "description": (t.description or "").strip().split("\n")[0][:200],
                        "hint": t.read_only_hint,
                        "access": classify(t, overrides),
                        "default_access": classify(t),
                        "tokens": estimate_tokens([t]),
                    }
                    for t in tools
                ],
            }
    except (McpError, McpConfigError) as err:
        result = {"ok": False, "at": db.now(), "bw_system": system["id"] if system else "", "message": str(err)}
    if row:
        db.update(conn, "mcp_servers", {"name": name}, last_test=db.dumps(result))
    return result
