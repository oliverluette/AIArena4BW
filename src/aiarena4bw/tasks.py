"""Aufgaben: Ordner mit task.yaml, prompt.md und verify.md.

Die Schlüssel in task.yaml sind deutsch, weil Nutzer die Datei von Hand pflegen:
id, version, titel, zeitlimit_s, pruefpunkte, anforderungen (name, werkzeuge), historie.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import db, paths

PLACEHOLDERS = {
    "RUN": "Laufkennung, z. B. AAA01",
    "MODEL": "Modell-ID des getesteten Modells",
    "MCP": "Name des MCP-Servers",
    "SYSTEM": "Kennung des BW-Systems",
    "PREFIX": "Objektpräfix des BW-Systems, z. B. ZB",
    "AREA": "InfoArea des Laufs, z. B. ZBENCH_AAA01",
    "PARENT_AREA": "Eltern-InfoArea des BW-Systems",
}
_PLACEHOLDER = re.compile(r"\{([A-Z_]+)\}")
JOIN = " | "

# coBWeb hat ein Werkzeug bw_write für alle Objekttypen; so zählt ein Aufruf nach Aktion und Typ.
TYPE_WORDS = {
    "AREA": "infoarea", "IOBJ": "infoobject", "ADSO": "adso", "TRFN": "transformation",
    "DTPA": "dtp", "HCPR": "composite_provider", "QUERY": "query", "RSDS": "datasource",
    "TRCS": "infosource", "CKF": "calculated_key_figure", "RKF": "restricted_key_figure",
    "VARIABLE": "variable", "STRUCTURE": "structure", "RSPC": "process_chain",
    "ALVL": "aggregation_level", "FILTER": "filter", "PLSE": "planning_function",
    "PLSQ": "planning_sequence", "HIER": "hierarchy", "DEST": "destination",
}  # fmt: skip


class TaskError(ValueError):
    pass


class TaskVersionError(TaskError):
    """Der Inhalt einer benutzten Version hat sich geändert, ohne dass die Version erhöht wurde."""


@dataclass
class Task:
    id: str
    version: int
    title: str
    prompt: str
    verify_prompt: str
    requirements: list[dict[str, Any]] = field(default_factory=list)  # [{name, tools: [...]}]
    checkpoints: int | None = None
    timeout_s: int = 900
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            [self.title, self.prompt, self.verify_prompt, self.requirements, self.checkpoints,
             self.timeout_s],
            ensure_ascii=False, sort_keys=True,
        )  # fmt: skip
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "version": self.version, "title": self.title, "prompt": self.prompt,
            "verify_prompt": self.verify_prompt, "requirements": self.requirements,
            "checkpoints": self.checkpoints, "timeout_s": self.timeout_s, "history": self.history,
            "content_hash": self.content_hash,
        }  # fmt: skip


# --------------------------------------------------------------------------- Laden


def load_task(folder: Path, default_timeout: int = 900) -> Task:
    meta_file = folder / "task.yaml"
    try:
        meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as err:
        raise TaskError(f"{meta_file}: nicht lesbar ({err}).") from None
    if not isinstance(meta, dict):
        raise TaskError(f"{meta_file}: erwartet wird eine Zuordnung aus Schlüssel und Wert.")
    task_id = str(meta.get("id") or folder.name)
    if task_id != folder.name:
        raise TaskError(f"{meta_file}: id „{task_id}“ entspricht nicht dem Ordnernamen „{folder.name}“.")
    try:
        prompt = (folder / "prompt.md").read_text(encoding="utf-8").strip()
        verify = (folder / "verify.md").read_text(encoding="utf-8").strip()
    except OSError as err:
        raise TaskError(f"Aufgabe {task_id}: {err.filename} fehlt.") from None
    requirements = []
    for item in meta.get("anforderungen") or []:
        if not isinstance(item, dict) or not item.get("name"):
            raise TaskError(f"{meta_file}: jede Anforderung braucht einen Namen.")
        requirements.append({"name": str(item["name"]), "tools": [str(t) for t in item.get("werkzeuge") or []]})
    try:
        version = int(meta.get("version") or 1)
        timeout = int(meta.get("zeitlimit_s") or default_timeout)
        checkpoints = int(meta["pruefpunkte"]) if meta.get("pruefpunkte") is not None else None
    except (TypeError, ValueError):
        raise TaskError(f"{meta_file}: version, zeitlimit_s und pruefpunkte sind ganze Zahlen.") from None
    return Task(
        id=task_id, version=version, title=str(meta.get("titel") or task_id), prompt=prompt,
        verify_prompt=verify, requirements=requirements, checkpoints=checkpoints, timeout_s=timeout,
        history=[h for h in meta.get("historie") or [] if isinstance(h, dict)],
    )  # fmt: skip


def load_tasks(folder: Path | None = None, default_timeout: int = 900) -> list[Task]:
    folder = folder or paths.tasks_dir()
    if not folder.exists():
        return []
    tasks = []
    for sub in sorted(folder.iterdir()):
        if sub.is_dir() and (sub / "task.yaml").exists():
            tasks.append(load_task(sub, default_timeout))
    return tasks


def get_task(task_id: str, folder: Path | None = None) -> Task | None:
    sub = (folder or paths.tasks_dir()) / task_id
    return load_task(sub) if (sub / "task.yaml").exists() else None


# --------------------------------------------------------------------------- Platzhalter


def fill(template: str, values: dict[str, str]) -> str:
    """Setzt {RUN}, {MODEL}, … ein. Unbekannte Platzhalter bleiben stehen."""
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


def unknown_placeholders(text: str) -> list[str]:
    return sorted({m.group(1) for m in _PLACEHOLDER.finditer(text)} - set(PLACEHOLDERS))


def placeholder_values(*, run_code: str, model: str, mcp_server: str, system: dict[str, Any]) -> dict[str, str]:
    return {
        "RUN": run_code,
        "MODEL": model,
        "MCP": mcp_server,
        "SYSTEM": system["id"],
        "PREFIX": system["prefix"],
        "AREA": str(system["area_pattern"]).replace("{RUN}", run_code),
        "PARENT_AREA": system["parent_area"],
    }


# --------------------------------------------------------------------------- Anforderungen


def aliases(tool: str, arguments: Any) -> list[str]:
    """Namen, unter denen ein Aufruf für die Anforderungen zählt (der echte zuerst)."""
    names = [tool]
    short = tool.split("__")[-1].lower()
    if short == "bw_write" and isinstance(arguments, dict):
        objects = [o for o in (arguments.get("objects") or []) if isinstance(o, dict)]
        for obj in objects:
            action = str(obj.get("action") or "").lower()
            typ = str(obj.get("type") or "").upper()
            if action and typ:
                names.append(f"bw_{action}_{TYPE_WORDS.get(typ, typ.lower())}")
        activate = arguments.get("activate", True)
        if activate not in (False, "false", "False", 0) and any(
            str(o.get("action") or "").lower() != "delete" for o in objects
        ):
            names.append("bw_activate")
    return names


def match_requirements(requirements: list[dict[str, Any]], tool: str, arguments: Any = None) -> list[str]:
    """Anforderungen (in ihrer Reihenfolge), zu denen der Aufruf passt."""
    names = [n.lower() for n in aliases(tool, arguments)]
    hits = []
    for req in requirements or []:
        parts = [str(p).lower() for p in req.get("tools") or [] if p]
        if any(part in name for part in parts for name in names):
            hits.append(str(req.get("name") or ""))
    return hits


# --------------------------------------------------------------------------- Datenbank


def sync_task(conn: sqlite3.Connection, task: Task) -> None:
    """Hält die Version in der Datenbank fest. Geänderter Inhalt bei gleicher Version ist ein Fehler,
    sobald die Version schon in einem Lauf benutzt wurde."""
    row = db.one(conn, "SELECT content_hash FROM tasks WHERE id=? AND version=?", (task.id, task.version))
    values = {
        "content_hash": task.content_hash, "title": task.title, "prompt": task.prompt,
        "verify_prompt": task.verify_prompt, "requirements": db.dumps(task.requirements),
        "checkpoints": task.checkpoints, "timeout_s": task.timeout_s,
    }  # fmt: skip
    if not row:
        db.insert(conn, "tasks", id=task.id, version=task.version, recorded=db.now(), **values)
        return
    if row["content_hash"] == task.content_hash:
        return
    used = db.one(conn, "SELECT COUNT(*) AS n FROM runs WHERE task_id=? AND task_version=?",
                  (task.id, task.version))  # fmt: skip
    if used and used["n"]:
        raise TaskVersionError(
            f"Aufgabe {task.id} v{task.version} wurde geändert, ist aber schon in {used['n']} Läufen "
            "benutzt. Bitte die Version in task.yaml erhöhen (oder in der App unter „Aufgaben“ als "
            "neue Version speichern), damit alte Ergebnisse ihrer Fassung zugeordnet bleiben."
        )
    db.update(conn, "tasks", {"id": task.id, "version": task.version}, recorded=db.now(), **values)


def stored_task(conn: sqlite3.Connection, task_id: str, version: int) -> dict[str, Any] | None:
    row = db.one(conn, "SELECT * FROM tasks WHERE id=? AND version=?", (task_id, version))
    if row:
        row["requirements"] = db.loads(row["requirements"], [])
    return row


def used_versions(conn: sqlite3.Connection, task_id: str) -> dict[int, int]:
    """Version -> Zahl der Läufe."""
    rows = db.rows(
        conn, "SELECT task_version AS v, COUNT(*) AS n FROM runs WHERE task_id=? GROUP BY task_version",
        (task_id,),
    )  # fmt: skip
    return {int(r["v"]): int(r["n"]) for r in rows}


# --------------------------------------------------------------------------- Bearbeiten

_TASK_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,48}[a-z0-9]")


def check_draft(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(Fehler, Hinweise) zu einem Entwurf aus der App."""
    errors, hints = [], []
    if not _TASK_ID.fullmatch(str(data.get("id") or "")):
        errors.append("Die ID besteht aus Kleinbuchstaben, Ziffern und Bindestrichen (3–50 Zeichen).")
    if not str(data.get("title") or "").strip():
        errors.append("Der Titel fehlt.")
    prompt, verify = str(data.get("prompt") or ""), str(data.get("verify_prompt") or "")
    if not prompt.strip():
        errors.append("Der Aufgabentext fehlt.")
    if not verify.strip():
        errors.append("Der Prüfauftrag fehlt.")
    for label, text in (("Aufgabentext", prompt), ("Prüfauftrag", verify)):
        unknown = unknown_placeholders(text)
        if unknown:
            errors.append(f"{label}: unbekannte Platzhalter {', '.join('{%s}' % u for u in unknown)}.")
    if prompt.strip() and "{RUN}" not in prompt:
        hints.append("Der Aufgabentext nennt {RUN} nicht: Objekte verschiedener Läufe würden kollidieren.")
    if prompt.strip() and "{PREFIX}{RUN}" not in prompt and "{AREA}" not in prompt:
        hints.append("Objektnamen sollten mit {PREFIX}{RUN} beginnen bzw. in {AREA} liegen, "
                     "sonst findet „BW bereinigen“ sie nicht.")  # fmt: skip
    if verify.strip() and "VERDICT" not in verify:
        hints.append("Der Prüfauftrag verlangt keine Zeile „VERDICT: PASS“ bzw. „VERDICT: FAIL“; "
                     "ohne sie bleibt das Urteil unklar.")  # fmt: skip
    try:
        timeout = int(data.get("timeout_s") or 0)
        if not 30 <= timeout <= 14400:
            errors.append("Das Zeitlimit liegt zwischen 30 und 14.400 Sekunden.")
    except (TypeError, ValueError):
        errors.append("Das Zeitlimit ist eine ganze Zahl in Sekunden.")
    checkpoints = data.get("checkpoints")
    if checkpoints not in (None, ""):
        try:
            if int(checkpoints) < 1:
                errors.append("Die Zahl der Prüfpunkte ist mindestens 1.")
        except (TypeError, ValueError):
            errors.append("Die Zahl der Prüfpunkte ist eine ganze Zahl.")
    for req in data.get("requirements") or []:
        if not str(req.get("name") or "").strip():
            errors.append("Jede Anforderung braucht einen Namen.")
            break
    return errors, hints


def draft_to_task(data: dict[str, Any], version: int, history: list[dict[str, Any]] | None = None) -> Task:
    requirements = [
        {"name": str(r["name"]).strip(), "tools": [str(t).strip() for t in r.get("tools") or [] if str(t).strip()]}
        for r in data.get("requirements") or []
    ]
    checkpoints = data.get("checkpoints")
    return Task(
        id=str(data["id"]), version=version, title=str(data["title"]).strip(),
        prompt=str(data["prompt"]).strip(), verify_prompt=str(data["verify_prompt"]).strip(),
        requirements=requirements,
        checkpoints=int(checkpoints) if checkpoints not in (None, "") else None,
        timeout_s=int(data["timeout_s"]), history=list(history or []),
    )  # fmt: skip


def save_task(task: Task, *, note: str = "", folder: Path | None = None) -> Path:
    """Schreibt die Aufgabe in ihren Ordner (task.yaml, prompt.md, verify.md)."""
    target = (folder or paths.tasks_dir()) / task.id
    target.mkdir(parents=True, exist_ok=True)
    history = list(task.history)
    if note or not history or history[-1].get("version") != task.version:
        history.append({"version": task.version, "datum": date.today().isoformat(),
                        "notiz": note or "gespeichert"})  # fmt: skip
    task.history = history
    meta = {
        "id": task.id,
        "version": task.version,
        "titel": task.title,
        "zeitlimit_s": task.timeout_s,
        **({"pruefpunkte": task.checkpoints} if task.checkpoints is not None else {}),
        "anforderungen": [{"name": r["name"], "werkzeuge": r["tools"]} for r in task.requirements],
        "historie": history,
    }
    header = (
        "# Eine Aufgabe = ein Ordner mit task.yaml, prompt.md (Aufgabe) und verify.md (Prüfauftrag).\n"
        "# Platzhalter: " + ", ".join("{%s}" % p for p in PLACEHOLDERS) + ".\n"
        "# Bei jeder inhaltlichen Änderung einer benutzten Fassung 'version' erhöhen.\n"
    )
    (target / "task.yaml").write_text(
        header + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )
    (target / "prompt.md").write_text(task.prompt + "\n", encoding="utf-8")
    (target / "verify.md").write_text(task.verify_prompt + "\n", encoding="utf-8")
    return target
