"""Gemeinsame Testausstattung: eigener Datenordner, nachgebaute Plattform, nachgebauter MCP-Server.

Tests laufen ohne Netz, ohne BW-System und ohne Schlüssel. Der Schlüsselbund ist
abgeschaltet; Geheimnisse kommen aus Umgebungsvariablen, damit auch der Runner-Prozess sie sieht.
"""

from __future__ import annotations

import json

import pytest

from aiarena4bw import bwcheck, db, vault

from .fakes.fake_platform import FakePlatform
from .fakes.seed import seed, write_task  # noqa: F401 - write_task wird von Tests importiert


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Jeder Test bekommt einen eigenen Datenordner und nie den echten Schlüsselbund."""
    monkeypatch.setenv("AIARENA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AIARENA_TASKS_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("AIARENA_KEYRING", "off")
    monkeypatch.setattr(bwcheck, "PATIENT_PAUSE_S", 0.01)  # die geduldige BW-Prüfung wartet im Test nicht
    vault._memory.clear()
    yield


@pytest.fixture
def secret(monkeypatch):
    def _set(name: str, value: str) -> None:
        monkeypatch.setenv(vault.env_name(name), value)

    return _set


@pytest.fixture
def platform():
    fake = FakePlatform()
    yield fake
    fake.close()


@pytest.fixture
def conn():
    connection = db.connect()
    yield connection
    connection.close()


@pytest.fixture
def arena(conn, platform, secret, tmp_path):
    """Eingerichtete Arena: BW-System TST, MCP-Server fake, vier Plattformen, Modelle, Aufgabe mini."""
    state = tmp_path / "bw-state.json"
    seed(conn, platform.url, state, tmp_path / "tasks", secret)

    class Arena:
        pass

    a = Arena()
    a.conn, a.platform, a.state, a.tmp = conn, platform, state, tmp_path
    a.spec = lambda **kw: {
        "bw_system": "TST",
        "mcp_server": "fake",
        "tasks": ["mini"],
        "models": ["or:anthropic/claude-good"],
        **kw,
    }
    a.bw_objects = lambda: json.loads(state.read_text())["objects"] if state.exists() else {}
    a.bw_calls = lambda: json.loads(state.read_text())["calls"] if state.exists() else []
    return a
