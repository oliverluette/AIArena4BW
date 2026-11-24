"""Einstellungen in der Datenbank: Vorgaben, BW-Systeme, MCP-Server, Plattformen, Modelle.

Geheimnisse liegen nie hier, sondern im Schlüsselbund (vault.py); die Funktionen geben nur an,
ob ein Geheimnis gesetzt ist.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from typing import Any

from . import db, vault, vendors

THINKING_LEVELS = ["", "none", "low", "medium", "high", "xhigh"]
PLATFORM_TYPES = {
    "anthropic": {"name": "Anthropic", "base_url": "https://api.anthropic.com", "external": True},
    "openrouter": {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "external": True},
    "sapaicore": {"name": "SAP AI Core", "base_url": "", "external": True},
    "openai": {"name": "OpenAI-kompatibel", "base_url": "http://localhost:1234/v1", "external": False},
}

DEFAULTS: dict[str, Any] = {
    "verify": {
        "model": "",
        "fallback": "",
        "timeout_s": 600,
        "thinking": "",
    },
    "run": {
        "timeout_s": 900,
        "thinking": "",
        "cost_limit": 5.0,
        "max_steps": 200,
        "tool_timeout_s": 120,
        "max_output_tokens": 16000,
        "api_retries": 4,
        "blocked_codes": [],
    },
}


class StoreError(ValueError):
    """Eingabe passt nicht; die Meldung sagt, was zu ändern ist."""


# --------------------------------------------------------------------------- Vorgaben


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM settings"):
        stored = db.loads(row["value"], {})
        if row["key"] in out and isinstance(stored, dict):
            out[row["key"]].update({k: v for k, v in stored.items() if k in out[row["key"]]})
    return out


def save_settings(conn: sqlite3.Connection, values: dict[str, Any]) -> dict[str, Any]:
    current = get_settings(conn)
    for section, content in values.items():
        if section not in DEFAULTS or not isinstance(content, dict):
            continue
        for key, value in content.items():
            if key in DEFAULTS[section]:
                current[section][key] = _check_setting(section, key, value)
    for section, content in current.items():
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (section, db.dumps(content)),
        )
    return current


def _check_setting(section: str, key: str, value: Any) -> Any:
    default = DEFAULTS[section][key]
    if key == "thinking":
        if value not in THINKING_LEVELS:
            raise StoreError(f"Unbekannte Denkstufe „{value}“.")
        return value
    if key == "blocked_codes":
        codes = value if isinstance(value, list) else re.split(r"[,\s]+", str(value or ""))
        codes = sorted({str(c).strip().upper() for c in codes if str(c).strip()})
        bad = [c for c in codes if not re.fullmatch(r"[A-Z]|[A-Z]{3}", c)]
        if bad:
            raise StoreError(f"Ungültige Durchgangscodes: {', '.join(bad)} (ein oder drei Buchstaben).")
        return codes
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int | float):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise StoreError(f"„{key}“ muss eine Zahl sein.") from None
        if number < 0:
            raise StoreError(f"„{key}“ darf nicht negativ sein.")
        return int(number) if isinstance(default, int) else number
    return str(value or "")


# --------------------------------------------------------------------------- BW-Systeme

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")


def _check_id(value: str, what: str) -> str:
    value = (value or "").strip()
    if not _ID.fullmatch(value):
        raise StoreError(f"{what}: 1–32 Zeichen aus Buchstaben, Ziffern, Punkt, Binde- und Unterstrich.")
    return value


def check_prefix(prefix: str) -> str:
    prefix = (prefix or "").strip().upper()
    if not re.fullmatch(r"[YZ][A-Z0-9]?", prefix):
        raise StoreError(
            "Das Objektpräfix hat ein oder zwei Zeichen und beginnt mit Y oder Z, damit "
            "Objektnamen aus Präfix + Laufkennung + zwei Zeichen höchstens neun Zeichen lang sind."
        )
    return prefix


def check_area_pattern(pattern: str) -> str:
    pattern = (pattern or "").strip().upper().replace("{RUN}", "{RUN}")
    if "{RUN}" not in pattern:
        raise StoreError("Das Muster der Lauf-InfoArea muss {RUN} enthalten, z. B. ZBENCH_{RUN}.")
    rest = pattern.replace("{RUN}", "")
    if not re.fullmatch(r"[A-Z0-9_/]*", rest) or len(rest) + 5 > 30:
        raise StoreError("Das Muster der Lauf-InfoArea darf nur Buchstaben, Ziffern und _ enthalten.")
    return pattern


def bw_public(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["is_default"] = bool(row["is_default"])
    row["retired"] = bool(row["retired"])
    row["password_set"] = vault.has(vault.bw_password(row["id"]))
    return row


def list_bw_systems(conn: sqlite3.Connection, include_retired: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM bw_systems" + ("" if include_retired else " WHERE retired=0")
    return [bw_public(r) for r in db.rows(conn, sql + " ORDER BY retired, id")]


def get_bw_system(conn: sqlite3.Connection, system_id: str) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM bw_systems WHERE id=?", (system_id,))
    return bw_public(row) if row else None


def default_bw_system(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM bw_systems WHERE retired=0 ORDER BY is_default DESC, id LIMIT 1")
    return bw_public(row) if row else None


def save_bw_system(conn: sqlite3.Connection, data: dict[str, Any], *, create: bool) -> dict[str, Any]:
    system_id = _check_id(data.get("id", ""), "Kennung des BW-Systems")
    existing = db.one(conn, "SELECT * FROM bw_systems WHERE id=?", (system_id,))
    if create and existing:
        raise StoreError(f"Ein BW-System „{system_id}“ gibt es schon.")
    if not create and not existing:
        raise StoreError(f"BW-System „{system_id}“ gibt es nicht.")
    url = (data.get("url") or "").strip().rstrip("/")
    if not re.match(r"^https?://[^/\s]+", url):
        raise StoreError("Die URL beginnt mit http:// oder https:// und nennt Host und Port.")
    parent = (data.get("parent_area") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_/]{1,30}", parent):
        raise StoreError("Die Eltern-InfoArea ist ein BW-Name, z. B. ZBENCH_AI.")
    values = {
        "url": url,
        "client": str(data.get("client") or "").strip(),
        "user": str(data.get("user") or "").strip(),
        "language": (str(data.get("language") or "DE").strip() or "DE").upper()[:2],
        "parent_area": parent,
        "area_pattern": check_area_pattern(data.get("area_pattern") or "ZBENCH_{RUN}"),
        "prefix": check_prefix(data.get("prefix") or "ZB"),
        "note": str(data.get("note") or ""),
        "retired": int(bool(data.get("retired", existing["retired"] if existing else False))),
    }
    if existing:
        db.update(conn, "bw_systems", {"id": system_id}, **values)
    else:
        db.insert(conn, "bw_systems", id=system_id, created=db.now(), **values)
    password = data.get("password")
    if password:
        vault.put(vault.bw_password(system_id), str(password))
    has_default = db.one(conn, "SELECT 1 AS x FROM bw_systems WHERE is_default=1 AND retired=0")
    if data.get("is_default") or not has_default:
        set_default_bw_system(conn, system_id)
    return get_bw_system(conn, system_id)  # type: ignore[return-value]


def set_default_bw_system(conn: sqlite3.Connection, system_id: str) -> None:
    conn.execute("UPDATE bw_systems SET is_default = (id = ?)", (system_id,))


def delete_bw_system(conn: sqlite3.Connection, system_id: str) -> str:
    """Löscht ein System ohne Durchgänge; mit Durchgängen wird es stillgelegt."""
    used = db.one(conn, "SELECT COUNT(*) AS n FROM batches WHERE bw_system=?", (system_id,))
    if used and used["n"]:
        conn.execute("UPDATE bw_systems SET retired=1, is_default=0 WHERE id=?", (system_id,))
        return "retired"
    conn.execute("DELETE FROM bw_systems WHERE id=?", (system_id,))
    vault.delete(vault.bw_password(system_id))
    return "deleted"


def run_area(system: dict[str, Any], run_code: str) -> str:
    return str(system["area_pattern"]).replace("{RUN}", run_code)


# --------------------------------------------------------------------------- Plattformen


def platform_public(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["active"] = bool(row["active"])
    row["options"] = db.loads(row["options"], {})
    row["last_test"] = db.loads(row["last_test"])
    row["credentials_set"] = vault.has(vault.platform_key(row["id"]))
    info = PLATFORM_TYPES.get(row["type"], {})
    row["type_name"] = info.get("name", row["type"])
    row["external"] = _is_external(row)
    return row


def _is_external(row: dict[str, Any]) -> bool:
    """Externe Plattform = Daten verlassen den Rechner."""
    if row["type"] != "openai":
        return True
    return not re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\]|[^/]*\.local)([:/]|$)", row["base_url"])


def list_platforms(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for row in db.rows(conn, "SELECT * FROM platforms ORDER BY created, id"):
        item = platform_public(row)
        counts = db.one(
            conn,
            "SELECT COUNT(*) AS total, COALESCE(SUM(selected), 0) AS selected FROM models WHERE platform_id=?",
            (row["id"],),
        )
        item["models_total"] = counts["total"] if counts else 0
        item["models_selected"] = counts["selected"] if counts else 0
        out.append(item)
    return out


def get_platform(conn: sqlite3.Connection, platform_id: str) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM platforms WHERE id=?", (platform_id,))
    return platform_public(row) if row else None


def save_platform(conn: sqlite3.Connection, data: dict[str, Any], *, create: bool) -> dict[str, Any]:
    platform_id = _check_id(data.get("id", ""), "Kennung der Plattform").lower()
    if ":" in platform_id or "/" in platform_id:
        raise StoreError("Die Kennung der Plattform darf weder Doppelpunkt noch Schrägstrich enthalten.")
    existing = db.one(conn, "SELECT * FROM platforms WHERE id=?", (platform_id,))
    if create and existing:
        raise StoreError(f"Eine Plattform „{platform_id}“ gibt es schon.")
    if not create and not existing:
        raise StoreError(f"Plattform „{platform_id}“ gibt es nicht.")
    ptype = existing["type"] if existing else data.get("type")
    if ptype not in PLATFORM_TYPES:
        raise StoreError("Unbekannter Plattformtyp.")
    base_url = (data.get("base_url") or "").strip().rstrip("/") or PLATFORM_TYPES[ptype]["base_url"]
    if base_url and not re.match(r"^https?://", base_url):
        raise StoreError("Die Basis-URL beginnt mit http:// oder https://.")
    options = db.loads(existing["options"], {}) if existing else {"caching": True, "select_all": False}
    for key in ("caching", "select_all"):
        if key in (data.get("options") or {}):
            options[key] = bool(data["options"][key])
    if "resource_group" in (data.get("options") or {}):
        options["resource_group"] = str(data["options"]["resource_group"] or "default").strip()
    values = {
        "name": (data.get("name") or "").strip() or PLATFORM_TYPES[ptype]["name"],
        "base_url": base_url,
        "options": db.dumps(options),
        "active": int(bool(data.get("active", True))),
    }
    if existing:
        db.update(conn, "platforms", {"id": platform_id}, **values)
    else:
        db.insert(conn, "platforms", id=platform_id, type=ptype, created=db.now(), **values)
    credentials = data.get("credentials")
    if credentials:
        vault.put(vault.platform_key(platform_id), str(credentials).strip())
    return get_platform(conn, platform_id)  # type: ignore[return-value]


def delete_platform(conn: sqlite3.Connection, platform_id: str) -> str:
    used = db.one(conn, "SELECT COUNT(*) AS n FROM runs WHERE model_id LIKE ?", (platform_id + ":%",))
    if used and used["n"]:
        conn.execute("UPDATE platforms SET active=0 WHERE id=?", (platform_id,))
        conn.execute("UPDATE models SET selected=0 WHERE platform_id=?", (platform_id,))
        return "deactivated"
    conn.execute("DELETE FROM models WHERE platform_id=?", (platform_id,))
    conn.execute("DELETE FROM platforms WHERE id=?", (platform_id,))
    vault.delete(vault.platform_key(platform_id))
    return "deleted"


def set_platform_test(conn: sqlite3.Connection, platform_id: str, ok: bool, message: str) -> dict:
    result = {"ok": ok, "message": message, "at": db.now()}
    db.update(conn, "platforms", {"id": platform_id}, last_test=db.dumps(result))
    return result


# --------------------------------------------------------------------------- Modelle


def model_public(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    for key in ("selected", "manual", "in_catalog", "price_edited"):
        row[key] = bool(row[key])
    for key in ("supports_tools", "supports_reasoning"):
        row[key] = None if row[key] is None else bool(row[key])
    row["quicktest"] = db.loads(row["quicktest"])
    row["vendor_name"] = vendors.vendor_name(row["vendor"] or "unknown")
    return row


def list_models(
    conn: sqlite3.Connection, platform_id: str | None = None, *, selectable: bool = False
) -> list[dict[str, Any]]:
    """selectable=True: nur vorausgewählte Modelle aktiver Plattformen."""
    sql = "SELECT m.* FROM models m JOIN platforms p ON p.id = m.platform_id WHERE 1=1"
    params: list[Any] = []
    if platform_id:
        sql += " AND m.platform_id=?"
        params.append(platform_id)
    if selectable:
        sql += " AND p.active=1 AND m.selected=1"
    return [model_public(r) for r in db.rows(conn, sql + " ORDER BY m.vendor, m.name", tuple(params))]


def get_model(conn: sqlite3.Connection, model_id: str) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM models WHERE id=?", (model_id,))
    return model_public(row) if row else None


def model_display(conn: sqlite3.Connection, model_id: str) -> str:
    row = db.one(conn, "SELECT name FROM models WHERE id=?", (model_id,))
    return row["name"] if row and row["name"] else vendors.split_model_id(model_id)[1]


def upsert_catalog(conn: sqlite3.Connection, platform_id: str, entries: list[dict[str, Any]]) -> int:
    """Übernimmt den Katalog einer Plattform. Von Hand gepflegte Preise und Namen bleiben."""
    platform = get_platform(conn, platform_id)
    if not platform:
        raise StoreError(f"Plattform „{platform_id}“ gibt es nicht.")
    select_all = bool(platform["options"].get("select_all"))
    now = db.now()
    seen = set()
    for entry in entries:
        model_id = str(entry["model_id"])
        full_id = f"{platform_id}:{model_id}"
        seen.add(full_id)
        existing = db.one(conn, "SELECT * FROM models WHERE id=?", (full_id,))
        catalog = {
            "context_window": entry.get("context_window"),
            "supports_tools": _tri(entry.get("supports_tools")),
            "supports_reasoning": _tri(entry.get("supports_reasoning")),
            "released": entry.get("released"),
            "in_catalog": 1,
        }
        prices = {k: entry.get(k) for k in ("price_in", "price_out", "price_cache_read", "price_cache_write")}
        if existing:
            if not existing["price_edited"]:
                catalog.update(prices)
            if not existing["max_tools"] and entry.get("max_tools"):
                catalog["max_tools"] = entry["max_tools"]
            if existing["name"] == existing["model_id"] and entry.get("name"):
                catalog["name"] = entry["name"]  # von Hand ergänzt, Name nie angepasst
            db.update(conn, "models", {"id": full_id}, **catalog)
        else:
            db.insert(
                conn,
                "models",
                id=full_id,
                platform_id=platform_id,
                model_id=model_id,
                name=entry.get("name") or model_id,
                vendor=vendors.vendor_key(full_id),
                selected=int(select_all),
                first_seen=now,
                max_tools=entry.get("max_tools"),
                **catalog,
                **prices,
            )
    for row in db.rows(conn, "SELECT id FROM models WHERE platform_id=? AND manual=0", (platform_id,)):
        if row["id"] not in seen:
            conn.execute("UPDATE models SET in_catalog=0 WHERE id=?", (row["id"],))
    db.update(conn, "platforms", {"id": platform_id}, catalog_fetched=now)
    return len(seen)


def _tri(value: Any) -> int | None:
    return None if value is None else int(bool(value))


def add_manual_model(conn: sqlite3.Connection, platform_id: str, model_id: str, name: str = "") -> dict:
    model_id = (model_id or "").strip()
    if not model_id or re.search(r"\s", model_id):
        raise StoreError("Die Modell-ID darf nicht leer sein und keine Leerzeichen enthalten.")
    if not get_platform(conn, platform_id):
        raise StoreError(f"Plattform „{platform_id}“ gibt es nicht.")
    full_id = f"{platform_id}:{model_id}"
    if db.one(conn, "SELECT 1 AS x FROM models WHERE id=?", (full_id,)):
        raise StoreError(f"Das Modell „{full_id}“ gibt es schon.")
    db.insert(
        conn,
        "models",
        id=full_id,
        platform_id=platform_id,
        model_id=model_id,
        name=name.strip() or model_id,
        vendor=vendors.vendor_key(full_id),
        selected=1,
        manual=1,
        first_seen=db.now(),
    )
    return get_model(conn, full_id)  # type: ignore[return-value]


def update_model(conn: sqlite3.Connection, model_id: str, data: dict[str, Any]) -> dict[str, Any]:
    existing = db.one(conn, "SELECT * FROM models WHERE id=?", (model_id,))
    if not existing:
        raise StoreError(f"Modell „{model_id}“ gibt es nicht.")
    values: dict[str, Any] = {}
    if "name" in data:
        values["name"] = str(data["name"]).strip() or existing["model_id"]
    if "note" in data:
        values["note"] = str(data["note"] or "")
    if "selected" in data:
        values["selected"] = int(bool(data["selected"]))
    if "max_tools" in data:
        values["max_tools"] = _number(data["max_tools"], "Werkzeuggrenze", integer=True)
    price_keys = ("price_in", "price_out", "price_cache_read", "price_cache_write")
    if any(k in data for k in price_keys):
        for key in price_keys:
            if key in data:
                values[key] = _number(data[key], "Preis")
        values["price_edited"] = 1
    db.update(conn, "models", {"id": model_id}, **values)
    return get_model(conn, model_id)  # type: ignore[return-value]


def _number(value: Any, what: str, integer: bool = False) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        raise StoreError(f"{what} muss eine Zahl sein (oder leer).") from None
    if number < 0:
        raise StoreError(f"{what} darf nicht negativ sein.")
    return int(number) if integer else number


def set_selection(
    conn: sqlite3.Connection,
    platform_id: str,
    *,
    select_all: bool | None = None,
    selected: list[str] | None = None,
) -> None:
    """Modellvorauswahl: „alle“ (auch künftige) oder genau die genannten Modelle."""
    platform = get_platform(conn, platform_id)
    if not platform:
        raise StoreError(f"Plattform „{platform_id}“ gibt es nicht.")
    options = platform["options"]
    if select_all is not None:
        options["select_all"] = bool(select_all)
        db.update(conn, "platforms", {"id": platform_id}, options=db.dumps(options))
        if select_all:
            conn.execute("UPDATE models SET selected=1 WHERE platform_id=?", (platform_id,))
    if selected is not None:
        conn.execute("UPDATE models SET selected=0 WHERE platform_id=?", (platform_id,))
        for model_id in selected:
            conn.execute("UPDATE models SET selected=1 WHERE id=? AND platform_id=?", (model_id, platform_id))


def delete_model(conn: sqlite3.Connection, model_id: str) -> str:
    """Löscht ein Modell ohne Läufe; mit Läufen wird es nur aus der Vorauswahl genommen."""
    used = db.one(conn, "SELECT COUNT(*) AS n FROM runs WHERE model_id=?", (model_id,))
    if used and used["n"]:
        conn.execute("UPDATE models SET selected=0 WHERE id=?", (model_id,))
        return "deselected"
    conn.execute("DELETE FROM models WHERE id=?", (model_id,))
    return "deleted"


# --------------------------------------------------------------------------- Nutzungshinweis

# Steigt, wenn sich der Hinweis inhaltlich ändert; dann ist er erneut zu bestätigen.
NOTICE_VERSION = 1


def notice_accepted(conn: sqlite3.Connection) -> str | None:
    """Zeitpunkt, zu dem der Nutzungshinweis in der aktuellen Fassung bestätigt wurde, sonst None."""
    row = db.one(conn, "SELECT value FROM meta WHERE key='notice_accepted'")
    value = db.loads(row["value"], {}) if row else {}
    if isinstance(value, dict) and value.get("version") == NOTICE_VERSION:
        return str(value.get("at") or "") or None
    return None


def accept_notice(conn: sqlite3.Connection) -> str:
    at = db.now()
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('notice_accepted', ?)",
        (db.dumps({"version": NOTICE_VERSION, "at": at}),),
    )
    return at


# --------------------------------------------------------------------------- Bereitschaft


def readiness(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Was für einen ersten Durchgang noch fehlt."""
    settings = get_settings(conn)
    systems = [s for s in list_bw_systems(conn, include_retired=False)]
    # Ein Eintrag, in dem noch der Platzhalter-Pfad steht, startet nicht und zählt deshalb nicht.
    servers = [
        r for r in db.rows(conn, "SELECT name, definition FROM mcp_servers") if "/Pfad/zu/" not in r["definition"]
    ]
    selectable = list_models(conn, selectable=True)
    return [
        {"key": "bw_system", "ok": bool(systems), "detail": ", ".join(s["id"] for s in systems)},
        {
            "key": "bw_password",
            "ok": bool(systems) and all(s["password_set"] for s in systems),
            "detail": "",
        },
        {"key": "mcp_server", "ok": bool(servers), "detail": ", ".join(s["name"] for s in servers)},
        {"key": "models", "ok": bool(selectable), "detail": str(len(selectable))},
        {"key": "verifier", "ok": bool(settings["verify"]["model"]), "detail": settings["verify"]["model"]},
    ]
