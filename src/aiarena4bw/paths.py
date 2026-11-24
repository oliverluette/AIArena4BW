"""Orte für Daten, Protokolle und Aufgaben.

Reihenfolge: Umgebungsvariable, sonst der Projektordner (wenn die App aus einem Klon läuft),
sonst ein Ordner im Benutzerverzeichnis.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"


def project_root() -> Path | None:
    """Wurzel des Klons (dort liegt pyproject.toml) oder None bei installiertem Paket."""
    for parent in PACKAGE_DIR.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "aiarena4bw").exists():
            return parent
    return None


def data_dir() -> Path:
    env = os.environ.get("AIARENA_DATA_DIR")
    if env:
        path = Path(env).expanduser()
    else:
        root = project_root()
        path = (root / "data") if root else Path.home() / ".aiarena4bw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "arena.db"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tasks_dir() -> Path:
    env = os.environ.get("AIARENA_TASKS_DIR")
    if env:
        return Path(env).expanduser()
    root = project_root()
    return (root / "tasks") if root else data_dir() / "tasks"
