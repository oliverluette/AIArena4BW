"""SQLite-Datenbank: Schema, Migrationen, kleine Zugriffshelfer.

Bezeichner sind englisch, die Bedeutung der Statuswerte steht in den Kommentaren. Das Schema ist
versioniert (meta.schema_version); connect() zieht es nach und sichert die Datei vorher.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import paths

# Jede Migration ist eine Liste von SQL-Anweisungen; Index + 1 = Schemaversion.
MIGRATIONS: list[str] = [
    # ------------------------------------------------------------------ Version 1
    """
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL                  -- JSON
    );
    CREATE TABLE bw_systems (
        id TEXT PRIMARY KEY,                 -- Kennung, z. B. A4H
        url TEXT NOT NULL,
        client TEXT NOT NULL DEFAULT '',
        user TEXT NOT NULL DEFAULT '',
        language TEXT NOT NULL DEFAULT 'DE',
        parent_area TEXT NOT NULL DEFAULT 'ZBENCH_AI',
        area_pattern TEXT NOT NULL DEFAULT 'ZBENCH_{RUN}',
        prefix TEXT NOT NULL DEFAULT 'ZB',
        is_default INTEGER NOT NULL DEFAULT 0,
        retired INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL
    );
    CREATE TABLE mcp_servers (
        name TEXT PRIMARY KEY,
        definition TEXT NOT NULL,            -- JSON: {command,args,env} oder {url,headers}
        is_default INTEGER NOT NULL DEFAULT 0,
        tool_overrides TEXT NOT NULL DEFAULT '{}',   -- JSON: {werkzeug: "read" | "write"}
        verify_env TEXT NOT NULL DEFAULT '{}',       -- JSON: abweichende Umgebungswerte der Prüfung
        last_test TEXT,                      -- JSON
        position INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL
    );
    CREATE TABLE platforms (
        id TEXT PRIMARY KEY,                 -- Kennung, z. B. openrouter
        type TEXT NOT NULL,                  -- anthropic | openrouter | sapaicore | openai
        name TEXT NOT NULL,
        base_url TEXT NOT NULL DEFAULT '',
        options TEXT NOT NULL DEFAULT '{}',  -- JSON: caching, resource_group, select_all …
        active INTEGER NOT NULL DEFAULT 1,
        last_test TEXT,                      -- JSON
        catalog_fetched TEXT,
        created TEXT NOT NULL
    );
    CREATE TABLE models (
        id TEXT PRIMARY KEY,                 -- plattform:modell-id
        platform_id TEXT NOT NULL,
        model_id TEXT NOT NULL,
        name TEXT NOT NULL,
        vendor TEXT NOT NULL DEFAULT '',
        selected INTEGER NOT NULL DEFAULT 0,
        manual INTEGER NOT NULL DEFAULT 0,
        in_catalog INTEGER NOT NULL DEFAULT 0,
        price_in REAL,                       -- $ je 1 Mio. Tokens; NULL = kein Preis
        price_out REAL,
        price_cache_read REAL,
        price_cache_write REAL,
        price_edited INTEGER NOT NULL DEFAULT 0,
        context_window INTEGER,
        max_tools INTEGER,
        supports_tools INTEGER,
        supports_reasoning INTEGER,
        released TEXT,
        first_seen TEXT,
        note TEXT NOT NULL DEFAULT '',
        quicktest TEXT                       -- JSON
    );
    CREATE INDEX idx_models_platform ON models(platform_id);
    CREATE TABLE tasks (
        id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        prompt TEXT NOT NULL,
        verify_prompt TEXT NOT NULL,
        requirements TEXT NOT NULL DEFAULT '[]',   -- JSON
        checkpoints INTEGER,
        timeout_s INTEGER,
        recorded TEXT NOT NULL,
        PRIMARY KEY (id, version)
    );
    CREATE TABLE batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,           -- AAA … ZZZ (übernommene Durchgänge: ein Buchstabe)
        created TEXT NOT NULL,
        started TEXT,
        finished TEXT,
        status TEXT NOT NULL,                -- planned | running | done | cancelled | error
        status_message TEXT,
        bw_system TEXT NOT NULL DEFAULT '',
        mcp_server TEXT NOT NULL DEFAULT '',
        repeats INTEGER NOT NULL DEFAULT 1,
        thinking TEXT NOT NULL DEFAULT '',   -- Anzeige: "low, medium"
        verifier TEXT NOT NULL DEFAULT '',
        fallback_verifier TEXT NOT NULL DEFAULT '',
        cost_limit REAL,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        runner_pid INTEGER,
        note TEXT NOT NULL DEFAULT '',
        hidden TEXT,                         -- Grund, wenn ausgeblendet
        agent TEXT NOT NULL DEFAULT 'AIArena4BW',
        agent_version TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE batch_items (
        batch_id INTEGER NOT NULL REFERENCES batches(id),
        position INTEGER NOT NULL,
        task_id TEXT NOT NULL,
        task_version INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        thinking TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (batch_id, position)
    );
    CREATE TABLE runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES batches(id),
        position INTEGER NOT NULL,
        repeat INTEGER NOT NULL,
        run_code TEXT NOT NULL,              -- Laufkennung, z. B. AAA01
        task_id TEXT NOT NULL,
        task_version INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        thinking TEXT NOT NULL DEFAULT '',
        thinking_sent TEXT,                  -- JSON: tatsächlich gesendete Parameter
        status TEXT NOT NULL,                -- planned | running | finished | error | timeout |
                                             -- step_limit | cancelled | skipped
                                             -- (übernommene Läufe: mcp_missing | no_result)
        phase TEXT,                          -- task | verify | done
        action TEXT,
        finish_reason TEXT,
        started TEXT,
        finished TEXT,
        seconds REAL,
        model_seconds REAL,
        tool_seconds REAL,
        steps INTEGER,
        tool_calls INTEGER,
        tool_errors INTEGER,
        api_retries INTEGER,
        last_requirement TEXT,
        tokens_input INTEGER,                -- gesamt, einschließlich Cache
        tokens_output INTEGER,
        tokens_cache_read INTEGER,
        tokens_cache_write INTEGER,
        tokens_reasoning INTEGER,
        cost_usd REAL,
        cost_source TEXT,                    -- billed | computed | NULL (kein Preis)
        error TEXT,
        error_kind TEXT,
        answer TEXT,
        invalid TEXT,                        -- Grund, wenn der Lauf nicht zählt
        retry_of INTEGER,
        log_path TEXT,
        extra TEXT,                          -- JSON: Zusatzangaben (z. B. übernommener Läufe)
        UNIQUE (batch_id, run_code)
    );
    CREATE INDEX idx_runs_batch ON runs(batch_id);
    CREATE TABLE run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL REFERENCES runs(id),
        phase TEXT NOT NULL,                 -- task | verify
        ts TEXT NOT NULL,
        seconds REAL,                        -- seit Start der Phase
        duration REAL,
        step INTEGER,
        kind TEXT NOT NULL,                  -- step | tool | usage | error
        tool TEXT,
        requirement TEXT,
        tokens_input INTEGER,
        tokens_output INTEGER,
        is_error INTEGER NOT NULL DEFAULT 0,
        text TEXT
    );
    CREATE INDEX idx_events_run ON run_events(run_id);
    CREATE TABLE verifications (
        run_id INTEGER PRIMARY KEY REFERENCES runs(id),
        verifier TEXT,
        status TEXT NOT NULL,                -- pass | fail | unclear | invalid | not_verified | error
        reason TEXT,
        points TEXT,                         -- JSON: [{nr, ok, text}]
        write_attempts TEXT,                 -- JSON-Liste schreibender Werkzeuge
        seconds REAL,
        tokens_input INTEGER,
        tokens_output INTEGER,
        cost_usd REAL,
        cost_source TEXT,
        answer TEXT,
        log_path TEXT,
        attempts INTEGER NOT NULL DEFAULT 1,
        earlier_cost REAL
    );
    CREATE TABLE environments (
        batch_id INTEGER PRIMARY KEY REFERENCES batches(id),
        recorded TEXT NOT NULL,
        data TEXT NOT NULL                   -- JSON
    );
    CREATE TABLE cleanup_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL,
        started TEXT,
        finished TEXT,
        status TEXT NOT NULL,                -- planned | running | done | error | cancelled
        bw_system TEXT NOT NULL,
        mcp_server TEXT NOT NULL,
        scope TEXT NOT NULL,                 -- JSON: {codes: [...], runs: [...]}
        objects TEXT NOT NULL,               -- JSON
        rest TEXT,                           -- JSON: danach noch im BW gefunden
        pid INTEGER,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        message TEXT
    );
    CREATE TABLE saved_views (
        name TEXT PRIMARY KEY,
        saved TEXT NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0,
        settings TEXT NOT NULL               -- JSON
    );
    """,
    # 2: Das Kostenlimit, wie es geplant wurde. cost_limit steigt bei jeder Wiederholung um das bis
    # dahin Verbrauchte; als Vorlage für einen neuen Durchgang taugt nur der ursprüngliche Wert.
    # Für Durchgänge, die schon Wiederholungen hatten, ist er nicht mehr bekannt und bleibt leer.
    """
    ALTER TABLE batches ADD COLUMN cost_limit_planned REAL;
    UPDATE batches SET cost_limit_planned = cost_limit
     WHERE id NOT IN (SELECT batch_id FROM runs WHERE retry_of IS NOT NULL);
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def connect(path: Path | None = None, *, migrate: bool = True) -> sqlite3.Connection:
    path = Path(path) if path else paths.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)  # Autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    if migrate:
        _migrate(conn, path)
    return conn


def connect_readonly(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else paths.db_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    has_meta = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    if not has_meta:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else 0


def _migrate(conn: sqlite3.Connection, path: Path) -> None:
    current = schema_version(conn)
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Die Datenbank {path} hat Schema {current}, diese Version der App kennt nur "
            f"{SCHEMA_VERSION}. Bitte die App aktualisieren."
        )
    if current == SCHEMA_VERSION:
        return
    if current > 0:
        # Sicherung vor jeder Schemaänderung.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.name}.schema{current}-{stamp}.bak"))
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    for version in range(current + 1, SCHEMA_VERSION + 1):
        conn.execute("BEGIN")
        try:
            for statement in _split(MIGRATIONS[version - 1]):
                conn.execute(statement)
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)", (str(version),))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _split(script: str) -> list[str]:
    """Teilt ein Skript an Semikolons am Zeilenende (Kommentare dürfen Semikolons enthalten)."""
    statements, current = [], []
    for line in script.splitlines():
        code = line.split("--", 1)[0].rstrip()
        current.append(line)
        if code.endswith(";"):
            statements.append("\n".join(current))
            current = []
    rest = "\n".join(current).strip()
    if rest:
        statements.append(rest)
    return [s for s in statements if s.strip()]


# --------------------------------------------------------------------------- Helfer


def insert(conn: sqlite3.Connection, table: str, **values: Any) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table}({cols}) VALUES ({marks})", tuple(values.values()))
    return int(cur.lastrowid or 0)


def update(conn: sqlite3.Connection, table: str, key: dict[str, Any], **values: Any) -> None:
    if not values:
        return
    sets = ", ".join(f"{k}=?" for k in values)
    where = " AND ".join(f"{k}=?" for k in key)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {where}", (*values.values(), *key.values()))


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True
