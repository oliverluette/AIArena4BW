"""Erreichbarkeit eines BW-Systems, für Statusanzeige und Vorabprüfung.

Der Hostname allein sagt wenig: Er löst über /etc/hosts auch dann auf, wenn das System pausiert
ist. Geprüft wird deshalb in zwei Stufen:

1. TCP-Verbindung zu Host und Port der URL.
2. HTTP-Anfrage an /sap/public/ping, ohne Anmeldung. Jede Antwort unter 500 heißt: ICM und ABAP
   antworten. 5xx oder keine Antwort heißt: Rechner erreichbar, BW aber nicht bereit.

Es werden keine Zugangsdaten gesendet. Selbst ausgestellte Zertifikate sind zulässig, weil nur die
Erreichbarkeit zählt.

Ein einzelner Fehlversuch sagt wenig: Unter Last beantwortet ein BW einzelne Anfragen erst nach bis
zu 20 s, obwohl es läuft (gemessen am 17.11.2026, Durchgang AAN). Deshalb gibt es zwei Arten zu
prüfen:

- `probe`: ein Versuch mit kurzem Zeitlimit, für die Statusanzeige. Die Anzeige wechselt erst nach
  zwei Fehlversuchen in Folge auf „nicht bereit“.
- `probe_patient`: mehrere Versuche mit langem Zeitlimit für die Antwort, für den Runner. Ein
  Durchgang hält erst an, wenn das BW über ein bis zwei Minuten nicht antwortet.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from . import db

OK, PARTLY, DOWN, UNKNOWN = "ok", "partly", "down", "unknown"

# Geduldige Prüfung des Runners: Der Verbindungsaufbau bleibt kurz (ein abgeschaltetes System fällt
# schnell auf), die Antwort darf länger dauern als die beobachteten Hänger von bis zu 20 s.
PATIENT_ATTEMPTS = 4
PATIENT_CONNECT_TIMEOUT_S = 5.0
PATIENT_RESPONSE_TIMEOUT_S = 25.0
PATIENT_PAUSE_S = 10.0
# Statusanzeige: so viele Fehlversuche in Folge, bis ein bereites System als nicht bereit gilt.
MONITOR_FAILS = 2


@dataclass
class Status:
    state: str = UNKNOWN
    detail: str = "noch nicht geprüft"
    host: str = ""
    ms: float | None = None
    checked: str | None = None

    def public(self) -> dict:
        return asdict(self)


def probe(url: str, timeout_s: float = 3.0, response_timeout_s: float | None = None) -> Status:
    """Ein Versuch. `timeout_s` gilt für den Verbindungsaufbau, `response_timeout_s` für die Antwort
    auf den Ping (ohne Angabe ebenfalls `timeout_s`)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    status = Status(host=f"{host}:{port}", checked=db.now())
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
    except socket.gaierror:
        status.state, status.detail = DOWN, f"Name {host} nicht auflösbar"
        return status
    except OSError as err:
        reason = "keine Antwort" if isinstance(err, TimeoutError) else (err.strerror or str(err))
        status.state, status.detail = DOWN, f"{host}:{port}: {reason}"
        return status
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    base = f"{parts.scheme}://{parts.netloc}"
    request = urllib.request.Request(f"{base}/sap/public/ping", headers={"User-Agent": "aiarena4bw"})
    try:
        with urllib.request.urlopen(request, timeout=response_timeout_s or timeout_s, context=ctx) as response:  # noqa: S310
            code = response.status
    except urllib.error.HTTPError as err:
        code = err.code
    except (OSError, ValueError) as err:
        status.state = PARTLY
        status.detail = f"Port offen, BW antwortet nicht ({getattr(err, 'reason', err)})"
        return status
    status.ms = round((time.monotonic() - start) * 1000)
    if code < 500:
        status.state, status.detail = OK, f"{host}:{port} antwortet (HTTP {code}, {status.ms:.0f} ms)"
    else:
        status.state, status.detail = PARTLY, f"Rechner erreichbar, BW meldet HTTP {code}"
    return status


def probe_patient(url: str, on_retry: Callable[[int, int, Status], None] | None = None) -> Status:
    """Mehrere Versuche, bevor das BW als nicht bereit gilt (Runner: Vorabprüfung und vor jedem Lauf).

    Gibt den ersten Stand „bereit“ zurück, sonst den Stand des letzten Versuchs; dessen `detail`
    nennt dann Zahl und Dauer der Versuche. `on_retry(versuch, von, stand)` wird nach jedem
    Fehlversuch gerufen, dem ein weiterer folgt. Ein nicht auflösbarer Name wird nicht wiederholt.
    """
    start = time.monotonic()
    status = Status()
    for attempt in range(1, PATIENT_ATTEMPTS + 1):
        status = probe(url, timeout_s=PATIENT_CONNECT_TIMEOUT_S, response_timeout_s=PATIENT_RESPONSE_TIMEOUT_S)
        if status.state == OK or "nicht auflösbar" in status.detail:
            return status
        if attempt < PATIENT_ATTEMPTS:
            if on_retry:
                on_retry(attempt, PATIENT_ATTEMPTS, status)
            time.sleep(PATIENT_PAUSE_S)
    status.detail = f"{status.detail}; {PATIENT_ATTEMPTS} Versuche in {time.monotonic() - start:.0f} s"
    return status


class Monitor:
    """Prüft im Hintergrund alle `interval_s` Sekunden alle Systeme; die App liest nur den Stand.

    Ein bereites System gilt erst nach `MONITOR_FAILS` Fehlversuchen in Folge als nicht bereit:
    Ein einzelner langsamer Ping ist kein Ausfall.
    """

    def __init__(self, systems: Callable[[], list[dict]], interval_s: float = 20.0, start: bool = True):
        self._systems = systems
        self.interval_s = interval_s
        self.status: dict[str, Status] = {}
        self._fails: dict[str, int] = {}
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bw-check")
        if start:
            self._thread.start()

    def refresh(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def get(self, system_id: str) -> Status:
        return self.status.get(system_id, Status())

    def check_now(self, system: dict) -> Status:
        """Prüfung auf Wunsch des Nutzers: ein Versuch mit Geduld für die Antwort, das Ergebnis gilt sofort."""
        status = probe(system["url"], response_timeout_s=PATIENT_RESPONSE_TIMEOUT_S)
        self.status[system["id"]] = status
        self._fails[system["id"]] = 0 if status.state == OK else MONITOR_FAILS
        return status

    def check_all(self) -> None:
        """Ein Umlauf über alle Systeme."""
        current: dict[str, Status] = {}
        fails: dict[str, int] = {}
        for system in self._systems():
            key = system["id"]
            try:
                status = probe(system["url"])
            except Exception as err:  # noqa: BLE001 - die Anzeige darf die App nie stören
                status = Status(state=UNKNOWN, detail=f"Prüfung fehlgeschlagen: {err}", checked=db.now())
            fails[key] = 0 if status.state == OK else self._fails.get(key, 0) + 1
            previous = self.status.get(key)
            if status.state != OK and previous and previous.state == OK and fails[key] < MONITOR_FAILS:
                status = previous  # erster Fehlversuch nach „bereit“: Stand bleibt, der nächste Umlauf entscheidet
            current[key] = status
        self.status, self._fails = current, fails

    def _loop(self) -> None:
        while not self._stop:
            try:
                self.check_all()
            except Exception:  # noqa: BLE001
                pass
            self._wake.wait(self.interval_s)
            self._wake.clear()
