"""Kommandozeile der AIArena4BW.

aiarena4bw                      App starten (http://127.0.0.1:8321)
aiarena4bw serve --reload       Backend mit automatischem Neuladen
aiarena4bw run --tasks … --models …   Durchgang ohne Oberfläche planen und ausführen
aiarena4bw cancel --batch AAB   laufenden Durchgang abbrechen
aiarena4bw list batches|tasks|models|systems
aiarena4bw demo                 Beispiel-Datenbank erzeugen und App damit starten
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

from . import __version__

DEFAULT_PORT = 8321

# Gleicher Inhalt wie der Hinweis in der Oberfläche (frontend/src/texts/common.ts, notice).
NOTICE = """Nutzungshinweis
- Nur mit Test- und Demosystemen arbeiten, nie mit einem Produktivsystem. Die Modelle legen im BW
  Objekte an, ändern und aktivieren sie.
- Schreibrechte doppelt begrenzen: im MCP-Server auf die Test-InfoArea und das Paket $TMP, im BW
  über einen eigenen Benutzer mit passenden Berechtigungen (siehe README).
- Über externe Plattformen gehen Aufgabentext, Werkzeugbeschreibungen und Antworten des BW-Systems
  an die Plattform und den Modellanbieter.
- Jeder Lauf kostet Geld. Das Kostenlimit hält einen Durchgang an, ersetzt aber keine Ausgabegrenze
  bei der Plattform.
- Die App kommt ohne Gewähr (MIT-Lizenz). Für System, Daten und Kosten bist du selbst verantwortlich.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aiarena4bw", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    parser.add_argument("--version", action="version", version=f"AIArena4BW {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="App starten")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--no-browser", action="store_true", help="Browser nicht öffnen")
    serve.add_argument("--reload", action="store_true", help="bei Änderungen am Code neu laden")

    run = sub.add_parser("run", help="Durchgang planen und ausführen")
    run.add_argument("--tasks", required=True, help="Aufgaben, kommagetrennt, oder „alle“")
    run.add_argument("--models", required=True, help="Modell-IDs oder Namensteile, kommagetrennt")
    run.add_argument("--system", default=None, help="BW-System (Vorgabe: Standardsystem)")
    run.add_argument("--mcp", default=None, help="MCP-Server (Vorgabe: Standardserver)")
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--thinking", default=None, help="eine oder mehrere Stufen, z. B. low,high")
    run.add_argument("--verifier", default=None)
    run.add_argument("--fallback", default=None)
    run.add_argument("--cost-limit", type=float, default=None)
    run.add_argument("--note", default="")
    run.add_argument("--plan-only", action="store_true", help="nur planen, nicht ausführen")
    run.add_argument("--accept-notice", action="store_true", help="Nutzungshinweis bestätigen (einmalig)")

    cancel = sub.add_parser("cancel", help="laufenden Durchgang abbrechen")
    cancel.add_argument("--batch", required=True, help="Code (AAB) oder Nummer des Durchgangs")

    lst = sub.add_parser("list", help="Durchgänge, Aufgaben, Modelle oder BW-Systeme anzeigen")
    lst.add_argument("what", choices=["batches", "tasks", "models", "systems"])

    demo = sub.add_parser("demo", help="Beispiel-Datenbank erzeugen und App damit starten")
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.add_argument("--no-browser", action="store_true")
    demo.add_argument("--only-create", action="store_true", help="nur die Datenbank erzeugen")

    runner = sub.add_parser("runner", help=argparse.SUPPRESS)
    runner.add_argument("--batch", type=int, required=True)
    runner.add_argument("--verify", default=None)

    job = sub.add_parser("cleanup-job", help=argparse.SUPPRESS)
    job.add_argument("--job", type=int, required=True)
    return parser


def cmd_serve(port: int, open_browser: bool, reload: bool) -> int:
    import uvicorn

    os.environ["AIARENA_PORT"] = str(port)
    url = f"http://127.0.0.1:{port}"
    print(f"AIArena4BW {__version__} – {url}", flush=True)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("aiarena4bw.cli:app_factory", factory=True, host="127.0.0.1", port=port, reload=reload,
                log_level="warning")  # fmt: skip
    return 0


def app_factory():  # noqa: ANN201 - Einstieg für uvicorn
    from .api import create_app

    return create_app(port=int(os.environ.get("AIARENA_PORT", DEFAULT_PORT)))


def _select(items: list[dict], wanted: str, keys: tuple[str, ...], label: str) -> list[dict]:
    """Wählt Einträge per exakter ID, Namensteil oder „alle“."""
    wanted = (wanted or "").strip()
    if wanted.lower() in ("alle", "all"):
        return list(items)
    chosen: list[dict] = []
    for part in [w.strip().lower() for w in wanted.split(",") if w.strip()]:
        exact = [i for i in items if str(i[keys[0]]).lower() == part]
        hits = exact or [i for i in items if any(part in str(i[k]).lower() for k in keys)]
        if not hits:
            raise SystemExit(f"Fehler: Keine {label} passt zu „{part}“.")
        chosen += [h for h in hits if h not in chosen]
    return chosen


def cmd_run(args: argparse.Namespace) -> int:
    from . import db, mcpclient, store, tasks
    from .runs import control, planning, runner

    conn = db.connect()
    mcpclient.seed_default(conn)
    if not store.notice_accepted(conn):
        print(NOTICE, file=sys.stderr)
        if not args.accept_notice:
            print("Zum Bestätigen den Aufruf mit --accept-notice wiederholen.", file=sys.stderr)
            return 1
        store.accept_notice(conn)
        print("Nutzungshinweis bestätigt.\n", file=sys.stderr)
    system = args.system or (store.default_bw_system(conn) or {}).get("id")
    all_tasks = [t.public() for t in tasks.load_tasks()]
    chosen_tasks = _select(all_tasks, args.tasks, ("id", "title"), "Aufgabe")
    selectable = store.list_models(conn, selectable=True)
    chosen_models = []
    for part in [p.strip() for p in args.models.split(",") if p.strip()]:
        exact = store.get_model(conn, part)  # volle ID wählt jedes eingerichtete Modell
        chosen_models += [exact] if exact else _select(selectable, part, ("id", "name"), "Modell")
    spec = {
        "bw_system": system, "mcp_server": args.mcp or mcpclient.default_server(conn),
        "tasks": [t["id"] for t in chosen_tasks], "models": [m["id"] for m in chosen_models],
        "repeats": args.repeats, "verifier": args.verifier, "fallback": args.fallback,
        "cost_limit": args.cost_limit, "note": args.note,
    }  # fmt: skip
    if args.thinking is not None:
        spec["thinking"] = args.thinking
    try:
        control.ensure_idle(conn)
        batch_id = planning.plan_batch(conn, spec)
    except (planning.PlanError, control.ControlError, tasks.TaskError) as err:
        print(f"Fehler: {err}", file=sys.stderr)
        return 1
    batch = db.one(conn, "SELECT code FROM batches WHERE id=?", (batch_id,))
    rows = db.rows(conn, "SELECT run_code, model_id, task_id, thinking FROM runs WHERE batch_id=? "
                         "ORDER BY repeat, position", (batch_id,))  # fmt: skip
    print(f"Durchgang {batch['code']} (Nr. {batch_id}) geplant mit {len(rows)} Läufen:")
    for row in rows:
        print(f"  {row['run_code']}  {row['model_id']}  {row['task_id']}  {row['thinking'] or ''}")
    if args.plan_only:
        return 0
    conn.close()
    return runner.main(batch_id)


def cmd_cancel(value: str) -> int:
    from . import db
    from .runs import control

    conn = db.connect()
    row = db.one(conn, "SELECT id, code, status FROM batches WHERE code=? OR CAST(id AS TEXT)=?",
                 (value.upper(), value))  # fmt: skip
    if not row:
        print(f"Fehler: Durchgang „{value}“ gibt es nicht.", file=sys.stderr)
        return 1
    control.request_cancel(conn, row["id"])
    print(f"Abbruch für Durchgang {row['code']} angefordert. Der Runner beendet den laufenden Lauf "
          "innerhalb von Sekunden.")  # fmt: skip
    return 0


def cmd_list(what: str) -> int:
    from . import analysis, db, store, tasks

    conn = db.connect()
    if what == "batches":
        for b in analysis.batch_overview(conn, 50):
            print(f"  {b['code']:<4} Nr. {b['id']:<4} {b['status']:<10} {str(b['created'])[:16]}  "
                  f"{b['run_count']:>2} Läufe  {b['passed'] or 0}/{b['verified'] or 0} bestanden  "
                  f"{b['cost']:.2f} $  {b['status_message'] or ''}")  # fmt: skip
    elif what == "tasks":
        for t in tasks.load_tasks():
            print(f"  {t.id:<28} v{t.version}  {t.title}  ({len(t.requirements)} Anforderungen, {t.timeout_s} s)")
    elif what == "models":
        for m in store.list_models(conn, selectable=True):
            price = f"{m['price_in']:.2f}/{m['price_out']:.2f} $" if m["price_in"] is not None else "kein Preis"
            print(f"  {m['id']:<52} {m['name']:<28} {price}")
    elif what == "systems":
        for s in store.list_bw_systems(conn):
            flags = ", ".join(f for f, on in (("Standard", s["is_default"]), ("stillgelegt", s["retired"]),
                                              ("ohne Passwort", not s["password_set"])) if on)  # fmt: skip
            print(f"  {s['id']:<8} {s['url']:<44} {s['parent_area']:<16} {s['prefix']}  {flags}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd in (None, "serve"):
        return cmd_serve(getattr(args, "port", DEFAULT_PORT), not getattr(args, "no_browser", False),
                         getattr(args, "reload", False))  # fmt: skip
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "cancel":
        return cmd_cancel(args.batch)
    if args.cmd == "list":
        return cmd_list(args.what)
    if args.cmd == "runner":
        from .runs import runner

        verify = [int(x) for x in args.verify.split(",") if x.strip()] if args.verify else None
        return runner.main(args.batch, verify)
    if args.cmd == "cleanup-job":
        from . import cleanup

        return cleanup.main(args.job)
    if args.cmd == "demo":
        from . import demo

        path = demo.create()
        print(f"Beispiel-Datenbank: {path}")
        if args.only_create:
            return 0
        os.environ["AIARENA_DATA_DIR"] = str(path.parent)
        os.environ["AIARENA_KEYRING"] = "off"
        os.environ["AIARENA_DEMO"] = "1"
        os.environ["AIARENA_SECRET_BW_DEMO_PASSWORD"] = "demo"  # nur damit die Beispieldaten vollständig wirken
        return cmd_serve(args.port, not args.no_browser, False)
    return 1


if __name__ == "__main__":
    sys.exit(main())
