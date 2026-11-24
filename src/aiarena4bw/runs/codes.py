"""Durchgangscodes und Laufkennungen.

Neue Durchgänge: Code aus drei Buchstaben (AAA … ZZZ), Laufkennung = Code + Laufnummer 01–99
(AAA01). Damit bleiben BW-Namen aus Präfix (2) + Laufkennung (5) + 2 Zeichen bei neun Zeichen.
Durchgänge anderer Agenten, die in die Datenbank übernommen wurden, können einen Code aus einem
Buchstaben tragen: ein Buchstabe + Position (2) + Wiederholung (1), z. B. T021. Die App vergibt
solche Codes nie selbst.
"""

from __future__ import annotations

import itertools
import re
import string

CODE_RE = re.compile(r"[A-Z]|[A-Z]{3}")
RUN_RE = re.compile(r"(?P<code1>[A-Z])\d{3}|(?P<code3>[A-Z]{3})\d{2}")
MAX_RUNS = 99


class CodeError(RuntimeError):
    pass


def is_imported(code: str) -> bool:
    return len(code) == 1


def check_code(code: str) -> str:
    if not CODE_RE.fullmatch(code or ""):
        raise ValueError(f"Ungültiger Durchgangscode: {code!r} (ein oder drei Großbuchstaben)")
    return code


def next_code(used: set[str]) -> str:
    """Nächster freier dreistelliger Code: AAA, AAB, … ZZZ."""
    for chars in itertools.product(string.ascii_uppercase, repeat=3):
        code = "".join(chars)
        if code not in used:
            return code
    raise CodeError("Alle Durchgangscodes AAA–ZZZ sind belegt.")


def run_code(code: str, number: int) -> str:
    """Laufkennung eines neuen Durchgangs: Code + Laufnummer."""
    if is_imported(code):
        raise CodeError(f"Durchgang {code} wurde übernommen und bekommt keine neuen Läufe.")
    if not 1 <= number <= MAX_RUNS:
        raise CodeError(f"Durchgang {code}: höchstens {MAX_RUNS} Läufe.")
    return f"{code}{number:02d}"


def check_run(run: str) -> str:
    if not RUN_RE.fullmatch(run or ""):
        raise ValueError(f"Ungültige Laufkennung: {run!r}")
    return run


def code_of(run: str) -> str:
    match = RUN_RE.fullmatch(check_run(run))
    assert match
    return match["code1"] or match["code3"]


def number_of(run: str) -> int:
    """Laufnummer einer neuen Kennung (AAA07 -> 7); 0 für alte Kennungen."""
    match = RUN_RE.fullmatch(run or "")
    return int(run[3:]) if match and match["code3"] else 0


def digits(code: str) -> int:
    """Zahl der Ziffern nach dem Code in Laufkennung und Objektnamen."""
    return 3 if is_imported(code) else 2


def sort_key(code: str) -> tuple[int, str]:
    return (len(code), code)
