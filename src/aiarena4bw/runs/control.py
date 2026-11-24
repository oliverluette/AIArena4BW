"""Steuerung aus App und Kommandozeile: Prozesse starten, abbrechen, wiederholen, ausblenden."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import db, paths
from ..agent import AGENT_NAME
from . import codes
from .runner import FINAL_RUN_STATES, batch_cost, log_dir, running_batches


class ControlError(ValueError):
    pass


def _spawn(args: list[str], output: Path) -> int:
    """Startet einen Hintergrundprozess in eigener Sitzung; seine Ausgabe geht in eine Datei."""
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    with open(output, "ab") as out:
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "aiarena4bw", *args], stdout=out, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True, env=env, cwd=str(paths.data_dir()),
        )  # fmt: skip
    return proc.pid


def ensure_idle(conn: sqlite3.Connection) -> None:
    # Auch ein eben gestarteter Runner zählt, dessen Durchgang noch als geplant gilt.
    starting = [
        {**b, "alive": db.pid_alive(b["runner_pid"])}
        for b in db.rows(conn, "SELECT * FROM batches WHERE status='planned' AND runner_pid IS NOT NULL")
    ]
    for batch in [*running_batches(conn), *starting]:
        if batch["alive"]:
            raise ControlError(
                f"Durchgang {batch['code']} läuft noch. Es läuft immer nur ein Durchgang, damit sich die "
                "Läufe im BW nicht stören."
            )
    row = db.one(conn, "SELECT id, pid FROM cleanup_jobs WHERE status='running'")
    if row and db.pid_alive(row["pid"]):
        raise ControlError("Im BW wird gerade bereinigt. Bitte warten, bis der Auftrag fertig ist.")


def start_runner(conn: sqlite3.Connection, batch_id: int) -> int:
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        raise ControlError(f"Durchgang {batch_id} gibt es nicht.")
    if batch["status"] != "planned":
        raise ControlError(f"Durchgang {batch['code']} ist nicht geplant (Status {batch['status']}).")
    ensure_idle(conn)
    pid = _spawn(["runner", "--batch", str(batch_id)], log_dir(batch) / "runner.out")
    db.update(conn, "batches", {"id": batch_id}, runner_pid=pid)
    return pid


def start_reverify(conn: sqlite3.Connection, batch_id: int, run_ids: list[int]) -> int:
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        raise ControlError(f"Durchgang {batch_id} gibt es nicht.")
    if not run_ids:
        raise ControlError("Bitte mindestens einen Lauf wählen.")
    ensure_idle(conn)
    return _spawn(["runner", "--batch", str(batch_id), "--verify", ",".join(str(i) for i in run_ids)],
                  log_dir(batch) / "runner.out")  # fmt: skip


def start_cleanup(conn: sqlite3.Connection, job_id: int) -> int:
    ensure_idle(conn)
    pid = _spawn(["cleanup-job", "--job", str(job_id)], paths.logs_dir() / "cleanup" / f"job_{job_id}.out")
    db.update(conn, "cleanup_jobs", {"id": job_id}, pid=pid)
    return pid


def request_cancel(conn: sqlite3.Connection, batch_id: int) -> None:
    db.update(conn, "batches", {"id": batch_id}, cancel_requested=1)


def mark_stale(conn: sqlite3.Connection, batch_id: int) -> int:
    """Räumt einen Durchgang auf, dessen Runner beendet ist, der aber noch als laufend gilt (F-O4)."""
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch or batch["status"] != "running" or db.pid_alive(batch["runner_pid"]):
        return 0
    from . import validity
    from .runner import _finalize

    cur = conn.execute(
        "UPDATE runs SET status='cancelled', phase='done', finished=?, invalid=COALESCE(invalid, ?), "
        "error=COALESCE(error, 'Runner unerwartet beendet') WHERE batch_id=? AND status='running'",
        (db.now(), validity.classify("cancelled", None, None), batch_id),
    )
    _finalize(conn, batch_id, "error", "Runner unerwartet beendet; in der App bereinigt")
    return cur.rowcount


def mark_stale_cleanup(conn: sqlite3.Connection, job_id: int) -> None:
    row = db.one(conn, "SELECT * FROM cleanup_jobs WHERE id=?", (job_id,))
    # Auch ein Auftrag, dessen Prozess nie angelaufen ist, soll nicht ewig als geplant stehen bleiben.
    started = row and (row["status"] == "running" or (row["status"] == "planned" and row["pid"]))
    if row and started and not db.pid_alive(row["pid"]):
        db.update(conn, "cleanup_jobs", {"id": job_id}, status="error", finished=db.now(),
                  message="Prozess unerwartet beendet")  # fmt: skip


def set_invalid(conn: sqlite3.Connection, run_id: int, reason: str | None) -> None:
    """Markiert einen Lauf von Hand als ungültig bzw. gibt ihn wieder frei."""
    run = db.one(conn, "SELECT id, retry_of FROM runs WHERE id=?", (run_id,))
    if not run:
        raise ControlError(f"Lauf {run_id} gibt es nicht.")
    reason = (reason or "").strip() or None
    if reason is None and db.one(conn, "SELECT 1 AS x FROM runs WHERE retry_of=?", (run_id,)):
        raise ControlError("Dieser Lauf wurde wiederholt und zählt deshalb nicht.")
    db.update(conn, "runs", {"id": run_id}, invalid=reason)


def set_hidden(conn: sqlite3.Connection, batch_id: int, reason: str | None) -> None:
    """Blendet einen Durchgang mit Grund aus bzw. wieder ein."""
    db.update(conn, "batches", {"id": batch_id}, hidden=(reason or "").strip() or None)


def retry_runs(conn: sqlite3.Connection, run_ids: list[int]) -> list[str]:
    """Plant gewählte Läufe im selben Durchgang neu ein. Gibt die neuen Kennungen zurück."""
    if not run_ids:
        raise ControlError("Bitte mindestens einen Lauf wählen.")
    runs = [db.one(conn, "SELECT * FROM runs WHERE id=?", (rid,)) for rid in run_ids]
    runs = [r for r in runs if r]
    batch_ids = {r["batch_id"] for r in runs}
    if len(batch_ids) != 1:
        raise ControlError("Bitte Läufe eines einzigen Durchgangs wählen.")
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_ids.pop(),))
    assert batch
    if codes.is_imported(batch["code"]) or batch["agent"] != AGENT_NAME:
        raise ControlError(
            f"Durchgang {batch['code']} stammt von einem anderen Agenten ({batch['agent']}); seine Läufe "
            "lassen sich nicht mit dem Agenten der App wiederholen. Bitte einen neuen Durchgang starten."
        )
    ensure_idle(conn)
    not_final = [r["run_code"] for r in runs if r["status"] not in FINAL_RUN_STATES]
    if not_final:
        raise ControlError(f"Noch nicht abgeschlossen: {', '.join(not_final)}.")
    already = [r["run_code"] for r in runs
               if db.one(conn, "SELECT 1 AS x FROM runs WHERE retry_of=?", (r["id"],))]  # fmt: skip
    if already:
        raise ControlError(f"Schon wiederholt: {', '.join(already)}.")
    used = {codes.number_of(r["run_code"]) for r in db.rows(
        conn, "SELECT run_code FROM runs WHERE batch_id=?", (batch["id"],))}  # fmt: skip
    free = [n for n in range(1, codes.MAX_RUNS + 1) if n > max(used, default=0)]
    if len(free) < len(runs):
        raise ControlError(
            f"Durchgang {batch['code']} hat nur noch {len(free)} freie Laufnummern (höchstens "
            f"{codes.MAX_RUNS} Läufe). Bitte einen neuen Durchgang starten."
        )
    new_codes = []
    spent = batch_cost(conn, batch["id"])
    conn.execute("BEGIN IMMEDIATE")
    try:
        for run, number in zip(runs, free, strict=False):
            new_code = codes.run_code(batch["code"], number)
            db.insert(conn, "runs", batch_id=batch["id"], position=run["position"], repeat=run["repeat"],
                      run_code=new_code, task_id=run["task_id"], task_version=run["task_version"],
                      model_id=run["model_id"], thinking=run["thinking"], status="planned",
                      retry_of=run["id"])  # fmt: skip
            # Übersprungene Läufe sind nie gelaufen: Sie werden ersetzt, ohne als ungültig zu zählen.
            db.update(conn, "runs", {"id": run["id"]}, invalid=f"wiederholt als {new_code}")
            new_codes.append(new_code)
        values: dict[str, Any] = {"status": "planned", "cancel_requested": 0, "status_message": None,
                                  "finished": None}  # fmt: skip
        if batch["cost_limit"]:
            # Das Limit gilt für die neuen Läufe: um das bisher Verbrauchte anheben.
            values["cost_limit"] = round(float(batch["cost_limit"]) + spent, 4)
        db.update(conn, "batches", {"id": batch["id"]}, **values)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return new_codes


def runner_output(batch: dict[str, Any], max_bytes: int = 20000) -> str:
    path = log_dir(batch) / "runner.out"
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-max_bytes:].decode("utf-8", errors="replace")
