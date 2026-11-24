"""Gültigkeit von Läufen: Was nicht am Modell lag, zählt nicht in der Auswertung.

Ein Lauf ist ungültig, wenn runs.invalid einen Grund enthält. Gesetzt wird er automatisch, wenn
ein Lauf an der Umgebung scheiterte, von Hand im Lauf-Detail oder beim Wiederholen. Zeitlimit,
Schrittlimit und ein überschrittenes Kontextfenster sind Ergebnisse des Modells und bleiben gültig.
"""

from __future__ import annotations

import re

BY_KIND = {
    "credits": "Guthaben bzw. Limit der Plattform erschöpft",
    "rate_limit": "Ratenlimit der Plattform",
    "unavailable": "Plattform gestört",
    "network": "Plattform oder Netz nicht erreichbar",
    "model_not_found": "Modell auf der Plattform nicht verfügbar",
    "tool_limit": "Werkzeuggrenze der Plattform überschritten (Konfiguration)",
    "auth": "Zugangsdaten der Plattform abgelehnt (Konfiguration)",
    "bad_request": "Anfrage von der Plattform abgelehnt (Konfiguration)",
    "mcp": "BW-System oder MCP-Server nicht erreichbar",
    "bad_tool_calls": "Werkzeugaufrufe nicht lesbar (Übergabe Modell → Plattform, nicht die Aufgabe)",
}

# Für Fehler ohne Einordnung (Läufe anderer Agenten, unbekannte Plattformen): Textmuster.
_PATTERNS = [
    (re.compile(r"could not verify (the )?available credits|retry shortly", re.I), "unavailable"),
    (re.compile(r"more credits|can only afford|available credits|insufficient (credits|funds|"
                r"balance|quota)|payment required|\b402\b|quota exceeded|credit limit", re.I), "credits"),
    (re.compile(r"rate.?limit|\b429\b|too many requests", re.I), "rate_limit"),
    (re.compile(r"model .* not found|no endpoints found|model_not_found|is not a valid model", re.I),
     "model_not_found"),
    (re.compile(r"'tools': array too long|maximum length 128", re.I), "tool_limit"),
    (re.compile(r"Werkzeugaufrufe nicht lesbar|emitted invalid JSON arguments", re.I), "bad_tool_calls"),
    (re.compile(r"upstream error|inference generation failed|provider returned error|"
                r"no healthy upstream|overloaded|service unavailable|bad gateway|gateway time-?out|"
                r"\b50[234]\b", re.I), "unavailable"),
    (re.compile(r"ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|fetch failed|socket hang up", re.I), "network"),
]  # fmt: skip

VALID_KINDS = {"context"}


def classify(status: str | None, error_kind: str | None, error: str | None) -> str | None:
    """Grund, warum ein Lauf nicht gewertet wird – oder None, wenn er zählt."""
    if status == "cancelled":
        return "abgebrochen (Abbruch oder Kostenlimit, nicht vom Modell)"
    if status == "mcp_missing":
        return "BW-Werkzeuge fehlten (Konfiguration)"
    if status in ("timeout", "step_limit", "finished"):
        if status == "timeout" and error_kind in BY_KIND:
            return BY_KIND[error_kind]
        return None
    if status not in ("error", "no_result"):
        return None
    if error_kind in VALID_KINDS:
        return None
    if error_kind in BY_KIND:
        return BY_KIND[error_kind]
    for pattern, kind in _PATTERNS:
        if error and pattern.search(error):
            return BY_KIND[kind]
    return None
