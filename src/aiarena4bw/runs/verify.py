"""Prüfung eines Laufs durch ein festgelegtes Prüfmodell."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import vendors


@dataclass
class VerifierChoice:
    model_id: str | None  # volle ID plattform:modell, oder None
    reason: str = ""  # warum nicht geprüft wird bzw. warum das Ersatzmodell prüft


def choose_verifier(tested_model: str, primary: str | None, fallback: str | None) -> VerifierChoice:
    """Wählt das Prüfmodell. Ein Modell prüft nie sich selbst – auch nicht über eine andere
    Plattform."""
    primary = (primary or "").strip() or None
    fallback = (fallback or "").strip() or None
    if not primary and not fallback:
        return VerifierChoice(None, "kein Prüfmodell eingestellt")
    if primary and not vendors.same_model(primary, tested_model):
        return VerifierChoice(primary)
    if fallback and not vendors.same_model(fallback, tested_model):
        return VerifierChoice(fallback, "Prüfmodell = Testmodell, Ersatzmodell prüft" if primary else "")
    return VerifierChoice(None, "Prüfmodell = Testmodell und kein anderes Ersatzmodell")


@dataclass
class Verdict:
    status: str  # pass | fail | unclear
    points: list[dict] = field(default_factory=list)


_HEADER = re.compile(
    r"^\s*(?:[-*]\s+)?(?:#+\s*)?(?:\*\*)?(?:Prüfpunkt\s+|Punkt\s+)?(\d{1,2})[.):](?!\d)"  # 1.  **1.**  - 1)
    r"|^\s*\|\s*(?:\*\*)?(\d{1,2})[.)]?(?:\*\*)?\s*\|"  # | 1 | … |
)
_RESULT = re.compile(r"\b(OK|FEHLER)\b", re.IGNORECASE)
_SYMBOL_OK, _SYMBOL_FAIL = ("✅", "✓", "✔"), ("❌", "✗", "✘")
_END = re.compile(r"^\s*(?:\*\*)?\s*VERDICT|^\s*-{3,}\s*$|^\s*#", re.IGNORECASE)


def _clean(text: str) -> str:
    text = re.sub(r"[*`]|[✅✓✔❌✗✘]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?:\s*–){2,}", " –", text)  # leere Tabellenzelle
    text = re.sub(r"\s*([:–-])\s*[.:]\s+", r"\1 ", text)  # Rest nach entferntem OK
    text = re.sub(r":\s*[-–]\s+", ": ", text)
    return text.strip(" -–—:|").lstrip(". ")  # Rest nach entferntem "OK." am Anfang


def parse_verdict(text: str | None) -> Verdict:
    """Liest 'VERDICT: PASS|FAIL' (letztes Vorkommen) und das Ergebnis je Prüfpunkt.

    Ein Prüfpunkt beginnt mit seiner Nummer ("1.", "**1.**", "- 1)", Tabellenzeile) und reicht bis
    zur nächsten Nummer, einer Trennlinie oder der VERDICT-Zeile. Das Ergebnis darf in derselben
    oder einer folgenden Zeile stehen ("OK"/"FEHLER", ersatzweise Haken/Kreuz).
    """
    text = text or ""
    hits = re.findall(r"VERDICT:\s*\**\s*(PASS|FAIL)", text, re.IGNORECASE)
    status = hits[-1].lower() if hits else "unclear"

    blocks: list[tuple[int, list[str]]] = []
    for line in text.splitlines():
        match = _HEADER.match(line)
        if match:
            nr = int(match.group(1) or match.group(2))
            rest = line[match.end() :]
            if match.group(2):  # Tabellenzeile: ein Block aus genau dieser Zeile
                blocks.append((nr, [rest.replace("|", " – ")]))
                blocks.append((-1, []))
            else:
                blocks.append((nr, [rest]))
        elif blocks and _END.match(line):
            blocks.append((-1, []))  # Block abschließen
        elif blocks and blocks[-1][0] >= 0:
            blocks[-1][1].append(line)

    points, seen = [], set()
    for nr, lines in blocks:
        if nr < 0 or nr in seen:
            continue
        body = "\n".join(lines)
        match = _RESULT.search(body)
        if match:
            ok = match.group(1).upper() == "OK"
            body = body[: match.start()] + body[match.end() :]
        elif any(s in body for s in _SYMBOL_FAIL):
            ok = False
        elif any(s in body for s in _SYMBOL_OK):
            ok = True
        else:
            continue
        seen.add(nr)
        points.append({"nr": nr, "ok": ok, "text": _clean(body)[:1000]})
    return Verdict(status=status, points=points)
