"""Geheimnisse: Ablage im Schlüsselbund des Betriebssystems und Schwärzung in Texten.

Die Datenbank kennt nur die Namen der Einträge. Ersatz ohne Schlüsselbund (Server, Tests):
Umgebungsvariablen AIARENA_SECRET_<NAME>. AIARENA_KEYRING=off schaltet den Schlüsselbund ganz ab,
damit Tests nie den echten Schlüsselbund berühren.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Iterable

SERVICE = "aiarena4bw"
_memory: dict[str, str] = {}


def _keyring_enabled() -> bool:
    return os.environ.get("AIARENA_KEYRING", "on").lower() not in ("off", "0", "false", "memory")


def env_name(name: str) -> str:
    return "AIARENA_SECRET_" + re.sub(r"[^A-Za-z0-9]+", "_", name).upper().strip("_")


def get(name: str) -> str | None:
    """Wert eines Geheimnisses oder None. Reihenfolge: Umgebung, Schlüsselbund."""
    value = os.environ.get(env_name(name))
    if value:
        return value
    if not _keyring_enabled():
        return _memory.get(name)
    import keyring
    import keyring.errors

    try:
        return keyring.get_password(SERVICE, name)
    except keyring.errors.KeyringError:
        return None


def put(name: str, value: str) -> None:
    if not _keyring_enabled():
        _memory[name] = value
        return
    import keyring

    keyring.set_password(SERVICE, name, value)


def delete(name: str) -> None:
    if not _keyring_enabled():
        _memory.pop(name, None)
        return
    import keyring
    import keyring.errors

    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.KeyringError:
        pass


def has(name: str) -> bool:
    return bool(get(name))


# Namen der Einträge
def platform_key(platform_id: str) -> str:
    return f"platform/{platform_id}/credentials"


def bw_password(system_id: str) -> str:
    return f"bw/{system_id}/password"


def named(name: str) -> str:
    return f"secret/{name}"


# --------------------------------------------------------------------------- Schwärzung

_SECRET = re.compile(
    r"(?i)((?:password|passwd|pwd|\bpass\b|secret|api[_-]?key|access[_-]?token|bearer|"
    r"client[_-]?secret)[\\\"']*\s*[:=]\s*[\\\"']*)(?!\d+[,}\s])([^\\\"'\s,}]+)"
)
_BASIC = re.compile(r"(?i)(authorization\W{0,6}(?:basic|bearer)\s+)([A-Za-z0-9+/=._-]+)")
_CURL_USER = re.compile(r"((?:-u|--user)\s+['\"]?[^:'\"\s]+:)([^'\"\s]+)")
MASK = "***"


class Redactor:
    """Schwärzt bekannte Geheimwerte und allgemeine Muster."""

    def __init__(self, values: Iterable[str] = (), users: Iterable[str] = ()):
        found = {v for v in values if isinstance(v, str) and len(v) >= 6}
        for user in users:
            for value in list(found):
                b64 = base64.b64encode(f"{user}:{value}".encode()).decode()
                found.update({b64, b64.rstrip("=")})
        # Lange Werte zuerst, damit Teilwerte keine Reste hinterlassen.
        self.values = sorted(found, key=len, reverse=True)

    def __call__(self, text: str | None) -> str | None:
        if not text:
            return text
        for value in self.values:
            if value in text:
                text = text.replace(value, MASK)
        text = _SECRET.sub(rf"\1{MASK}", text)
        text = _BASIC.sub(rf"\1{MASK}", text)
        return _CURL_USER.sub(rf"\1{MASK}", text)


_LOOKS_SECRET_KEY = re.compile(r"(?i)pass|secret|token|api[_-]?key|authorization")


def looks_like_secret(key: str, value: object) -> bool:
    """Für die Warnung im MCP-Editor: Klartextwert unter einem verdächtigen Schlüssel."""
    if not isinstance(value, str) or not value or "${" in value:
        return False
    return bool(_LOOKS_SECRET_KEY.search(key))
