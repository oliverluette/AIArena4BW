"""Webserver: JSON-Schnittstelle für die Oberfläche, Live-Daten per SSE, Auslieferung der Oberfläche.

Die Schnittstelle nimmt nur Anfragen der eigenen Oberfläche an: Der Host-Kopf muss auf
den lokalen Server zeigen, eine mitgesendete Herkunft (Origin) ebenfalls, und schreibende Anfragen
brauchen den Kopf X-AIArena. Fremde Webseiten können so keine Befehle auslösen.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from . import __version__, analysis, bwcheck, cleanup, db, mcpclient, paths, store, tasks, vault, vendors
from .agent import AGENT_NAME, AGENT_VERSION, SYSTEM_PROMPT
from .platforms import LIVE_VERIFIED, PlatformError, adapter_for_model, create_adapter
from .platforms.base import Request as ModelRequest
from .platforms.base import Turn
from .runs import codes, control, planning, runner

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(*, port: int = 8321, monitor: bool = True, extra_hosts: tuple[str, ...] = ()) -> FastAPI:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", *extra_hosts}
    dev_origins = {o.strip() for o in os.environ.get("AIARENA_DEV_ORIGINS", "").split(",") if o.strip()}
    for origin in dev_origins:
        allowed_hosts.add(origin.split("://", 1)[-1])

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = db.connect()
        mcpclient.seed_default(conn)
        conn.close()
        app.state.monitor = None
        if monitor:

            def systems() -> list[dict]:
                c = db.connect(migrate=False)
                try:
                    return store.list_bw_systems(c, include_retired=False)
                finally:
                    c.close()

            app.state.monitor = bwcheck.Monitor(systems)
        yield
        if app.state.monitor:
            app.state.monitor.stop()

    app = FastAPI(title="AIArena4BW", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)  # fmt: skip

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Any:
        if request.url.path.startswith("/api/"):
            host = request.headers.get("host", "")
            if host not in allowed_hosts:
                return JSONResponse({"detail": "Anfrage von unbekanntem Host abgelehnt."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] not in allowed_hosts:
                return JSONResponse({"detail": "Anfrage fremder Herkunft abgelehnt."}, status_code=403)
            if request.method in UNSAFE and request.headers.get("x-aiarena") != "1":
                return JSONResponse({"detail": "Kopf X-AIArena fehlt."}, status_code=403)
        return await call_next(request)

    for exc_type in (store.StoreError, mcpclient.McpConfigError, planning.PlanError, control.ControlError,
                     tasks.TaskError, cleanup.CleanupUnsupported):  # fmt: skip

        @app.exception_handler(exc_type)
        async def _bad_request(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(PlatformError)
    async def _platform(_request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "kind": exc.kind}, status_code=400)

    @app.exception_handler(mcpclient.McpError)
    async def _mcp(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = db.connect(migrate=False)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Depends(get_conn)  # noqa: N806

    def bw_status(system_id: str) -> dict[str, Any]:
        mon = app.state.monitor
        return (mon.get(system_id) if mon else bwcheck.Status()).public()

    # ------------------------------------------------------------------ Allgemein

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "agent": AGENT_NAME, "agent_version": AGENT_VERSION}

    @app.get("/api/status")
    def status(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        """Kopfzeile: BW-Status des Standardsystems, laufender Durchgang, Bereitschaft."""
        system = store.default_bw_system(conn)
        running = [b for b in runner.running_batches(conn)]
        current = running[0] if running else None
        return {
            "version": __version__,
            "bw": {"system": system["id"], **bw_status(system["id"])} if system else None,
            "running": {"id": current["id"], "code": current["code"], "alive": current["alive"]}
            if current else None,
            "demo": bool(os.environ.get("AIARENA_DEMO")),
            "notice_accepted": store.notice_accepted(conn),
            "readiness": store.readiness(conn),
            "ready": all(item["ok"] for item in store.readiness(conn)),
        }  # fmt: skip

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {
            "version": __version__, "agent": AGENT_NAME, "agent_version": AGENT_VERSION,
            "system_prompt": SYSTEM_PROMPT, "thinking_levels": store.THINKING_LEVELS,
            "platform_types": [{"type": k, **v, "live_verified": LIVE_VERIFIED.get(k, False)}
                               for k, v in store.PLATFORM_TYPES.items()],
            "placeholders": tasks.PLACEHOLDERS, "bw_placeholders": list(mcpclient.BW_PLACEHOLDERS),
            "data_dir": str(paths.data_dir()), "tasks_dir": str(paths.tasks_dir()),
        }  # fmt: skip

    # ------------------------------------------------------------------ Einstellungen: Vorgaben

    @app.get("/api/settings")
    def get_settings(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.get_settings(conn)

    @app.put("/api/settings")
    def put_settings(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.save_settings(conn, body)

    @app.post("/api/notice")
    def accept_notice(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"accepted": store.accept_notice(conn)}

    # ------------------------------------------------------------------ BW-Systeme

    def with_status(system: dict[str, Any]) -> dict[str, Any]:
        return {**system, "status": bw_status(system["id"])}

    @app.get("/api/bw-systems")
    def bw_systems(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        return [with_status(s) for s in store.list_bw_systems(conn)]

    @app.post("/api/bw-systems")
    def bw_create(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        system = store.save_bw_system(conn, body, create=True)
        if app.state.monitor:
            app.state.monitor.refresh()
        return with_status(system)

    @app.put("/api/bw-systems/{system_id}")
    def bw_update(system_id: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        system = store.save_bw_system(conn, {**body, "id": system_id}, create=False)
        if app.state.monitor:
            app.state.monitor.refresh()
        return with_status(system)

    @app.delete("/api/bw-systems/{system_id}")
    def bw_delete(system_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"result": store.delete_bw_system(conn, system_id)}

    @app.post("/api/bw-systems/{system_id}/default")
    def bw_default(system_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        store.set_default_bw_system(conn, system_id)
        return {"ok": True}

    @app.post("/api/bw-systems/{system_id}/check")
    async def bw_check(system_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        system = store.get_bw_system(conn, system_id)
        if not system:
            raise HTTPException(404, "BW-System nicht gefunden.")
        if app.state.monitor:
            result = await asyncio.to_thread(app.state.monitor.check_now, system)
        else:
            result = await asyncio.to_thread(bwcheck.probe, system["url"])
        return result.public()

    # ------------------------------------------------------------------ MCP-Server

    @app.get("/api/mcp")
    def mcp_get(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"text": mcpclient.definition_text(conn), "servers": mcpclient.list_servers(conn),
                "path_hint": mcpclient.COBWEB_PATH_HINT}  # fmt: skip

    @app.put("/api/mcp")
    def mcp_put(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        servers = mcpclient.save_definition_text(conn, str(body.get("text") or ""))
        return {"text": mcpclient.definition_text(conn), "servers": servers}

    @app.post("/api/mcp/validate")
    def mcp_validate(body: dict = Body(...)) -> dict[str, Any]:
        try:
            servers = mcpclient.parse_definition(str(body.get("text") or ""))
        except mcpclient.McpConfigError as err:
            return {"ok": False, "message": str(err)}
        warnings = [f'Server "{name}": {", ".join(found)} steht im Klartext. Besser ${{SECRET:name}} oder '
                    "einen BW-Platzhalter verwenden."
                    for name, entry in servers.items() if (found := mcpclient.plaintext_secrets(entry))]  # fmt: skip
        return {"ok": True, "servers": list(servers), "warnings": warnings}

    @app.post("/api/mcp/{name}/default")
    def mcp_default(name: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        mcpclient.set_default_server(conn, name)
        return {"ok": True}

    @app.put("/api/mcp/{name}/options")
    def mcp_options(name: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return mcpclient.save_server_options(conn, name, tool_overrides=body.get("tool_overrides"),
                                             verify_env=body.get("verify_env"))  # fmt: skip

    @app.post("/api/mcp/{name}/test")
    async def mcp_test(name: str, body: dict = Body(default={}), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        system_id = body.get("bw_system")
        system = store.get_bw_system(conn, system_id) if system_id else store.default_bw_system(conn)
        return await mcpclient.test_server(conn, name, system)

    @app.get("/api/secrets")
    def secrets_list(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        names = db.loads((db.one(conn, "SELECT value FROM settings WHERE key='secret_names'") or {}).get("value"), [])
        return [{"name": n, "set": vault.has(vault.named(n))} for n in names]

    @app.put("/api/secrets/{name}")
    def secrets_put(name: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        if not name.replace("_", "").replace("-", "").isalnum():
            raise store.StoreError("Der Name eines Geheimnisses besteht aus Buchstaben, Ziffern, - und _.")
        if not body.get("value"):
            raise store.StoreError("Der Wert fehlt.")
        vault.put(vault.named(name), str(body["value"]))
        names = db.loads((db.one(conn, "SELECT value FROM settings WHERE key='secret_names'") or {}).get("value"), [])
        if name not in names:
            names.append(name)
        conn.execute("INSERT INTO settings(key, value) VALUES ('secret_names', ?) ON CONFLICT(key) DO UPDATE "
                     "SET value=excluded.value", (db.dumps(sorted(names)),))  # fmt: skip
        return {"name": name, "set": True}

    @app.delete("/api/secrets/{name}")
    def secrets_delete(name: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        vault.delete(vault.named(name))
        names = db.loads((db.one(conn, "SELECT value FROM settings WHERE key='secret_names'") or {}).get("value"), [])
        conn.execute("INSERT INTO settings(key, value) VALUES ('secret_names', ?) ON CONFLICT(key) DO UPDATE "
                     "SET value=excluded.value", (db.dumps([n for n in names if n != name]),))  # fmt: skip
        return {"ok": True}

    # ------------------------------------------------------------------ Plattformen und Modelle

    @app.get("/api/platforms")
    def platforms(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        return [{**p, "live_verified": LIVE_VERIFIED.get(p["type"], False)} for p in store.list_platforms(conn)]

    @app.post("/api/platforms")
    def platform_create(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.save_platform(conn, body, create=True)

    @app.put("/api/platforms/{platform_id}")
    def platform_update(platform_id: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.save_platform(conn, {**body, "id": platform_id}, create=False)

    @app.delete("/api/platforms/{platform_id}")
    def platform_delete(platform_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"result": store.delete_platform(conn, platform_id)}

    @app.post("/api/platforms/{platform_id}/test")
    async def platform_test(platform_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        platform = store.get_platform(conn, platform_id)
        if not platform:
            raise HTTPException(404, "Plattform nicht gefunden.")
        adapter = create_adapter(platform)
        try:
            message = await adapter.check()
            return store.set_platform_test(conn, platform_id, True, message)
        except PlatformError as err:
            return store.set_platform_test(conn, platform_id, False, vault.Redactor(adapter.secrets())(str(err)) or "")
        finally:
            await adapter.aclose()

    @app.post("/api/platforms/{platform_id}/catalog")
    async def platform_catalog(platform_id: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        platform = store.get_platform(conn, platform_id)
        if not platform:
            raise HTTPException(404, "Plattform nicht gefunden.")
        adapter = create_adapter(platform)
        try:
            entries = await adapter.list_models()
        finally:
            await adapter.aclose()
        return {"count": store.upsert_catalog(conn, platform_id, entries)}

    @app.get("/api/platforms/{platform_id}/models")
    def platform_models(platform_id: str, conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        return store.list_models(conn, platform_id)

    @app.put("/api/platforms/{platform_id}/selection")
    def platform_selection(platform_id: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        store.set_selection(conn, platform_id, select_all=body.get("select_all"), selected=body.get("selected"))
        return {"ok": True}

    @app.post("/api/platforms/{platform_id}/models")
    def model_add(platform_id: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.add_manual_model(conn, platform_id, str(body.get("model_id") or ""), str(body.get("name") or ""))

    @app.get("/api/models")
    def models(selectable: bool = False, conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        platforms_by_id = {p["id"]: p for p in store.list_platforms(conn)}
        out = []
        for model in store.list_models(conn, selectable=selectable):
            platform = platforms_by_id.get(model["platform_id"], {})
            out.append({**model, "platform_name": platform.get("name", model["platform_id"]),
                        "platform_type": platform.get("type", ""), "external": platform.get("external", True)})  # fmt: skip
        return out

    @app.patch("/api/model")
    def model_update(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return store.update_model(conn, str(body.get("id") or ""), body)

    @app.post("/api/model/delete")
    def model_delete(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"ok": True, "result": store.delete_model(conn, str(body.get("id") or ""))}

    @app.post("/api/model/quicktest")
    async def model_quicktest(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return await quicktest(conn, str(body.get("id") or ""))

    # ------------------------------------------------------------------ Aufgaben

    def task_public(task: tasks.Task, conn: sqlite3.Connection) -> dict[str, Any]:
        used = tasks.used_versions(conn, task.id)
        return {**task.public(), "used_runs": used.get(task.version, 0),
                "versions": sorted({task.version, *used}), "used_versions": used}  # fmt: skip

    @app.get("/api/tasks")
    def task_list(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        return [task_public(t, conn) for t in tasks.load_tasks()]

    @app.get("/api/tasks/{task_id}")
    def task_get(task_id: str, version: int | None = None, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        task = tasks.get_task(task_id)
        if version is not None and (not task or task.version != version):
            stored = tasks.stored_task(conn, task_id, version)
            if not stored:
                raise HTTPException(404, "Diese Version der Aufgabe ist nicht gespeichert.")
            return {"id": task_id, "version": version, "title": stored["title"], "prompt": stored["prompt"],
                    "verify_prompt": stored["verify_prompt"], "requirements": stored["requirements"],
                    "checkpoints": stored["checkpoints"], "timeout_s": stored["timeout_s"], "history": [],
                    "stored_only": True, "used_runs": tasks.used_versions(conn, task_id).get(version, 0)}  # fmt: skip
        if not task:
            raise HTTPException(404, "Aufgabe nicht gefunden.")
        return task_public(task, conn)

    @app.post("/api/tasks/preview")
    def task_preview(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        system = store.get_bw_system(conn, str(body.get("bw_system") or "")) or store.default_bw_system(conn) or {
            "id": "A4H", "prefix": "ZB", "area_pattern": "ZBENCH_{RUN}", "parent_area": "ZBENCH_AI"}  # fmt: skip
        values = tasks.placeholder_values(
            run_code=str(body.get("run_code") or "AAA01"), model=str(body.get("model") or "modell-id"),
            mcp_server=str(body.get("mcp_server") or mcpclient.default_server(conn) or mcpclient.DEFAULT_SERVER),
            system=system,
        )  # fmt: skip
        errors, hints = tasks.check_draft(body)
        return {"prompt": tasks.fill(str(body.get("prompt") or ""), values),
                "verify_prompt": tasks.fill(str(body.get("verify_prompt") or ""), values),
                "values": values, "errors": errors, "hints": hints}  # fmt: skip

    @app.post("/api/tasks")
    def task_save(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        """Speichert eine Aufgabe. Eine benutzte Version wird nie überschrieben: Mit Freigabe
        (confirm_new_version) entsteht eine neue Version."""
        errors, _hints = tasks.check_draft(body)
        if errors:
            raise tasks.TaskError(" ".join(errors))
        task_id = str(body["id"])
        existing = tasks.get_task(task_id)
        if body.get("create") and existing:
            raise tasks.TaskError(f"Eine Aufgabe „{task_id}“ gibt es schon.")
        used = tasks.used_versions(conn, task_id)
        version = existing.version if existing else 1
        draft = tasks.draft_to_task(body, version, existing.history if existing else [])
        changed = not existing or draft.content_hash != existing.content_hash
        if existing and not changed:
            return task_public(existing, conn)  # nichts geändert: keine neue Version, kein Historieneintrag
        if existing and changed and used.get(version):
            if not body.get("confirm_new_version"):
                raise tasks.TaskError(
                    f"Version {version} wurde schon in {used[version]} Läufen benutzt. Eine Änderung "
                    "verfälscht den Vergleich. Zum Speichern als neue Version bitte ausdrücklich freigeben."
                )
            version = max([version, *used]) + 1
            draft = tasks.draft_to_task(body, version, existing.history)
        tasks.save_task(draft, note=str(body.get("note") or ("angelegt" if not existing else "")))
        saved = tasks.get_task(task_id)
        assert saved
        return task_public(saved, conn)

    # ------------------------------------------------------------------ Durchgänge

    @app.get("/api/batches")
    def batches(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        return analysis.batch_overview(conn)

    @app.get("/api/start-options")
    def start_options(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        settings = store.get_settings(conn)
        default_system = store.default_bw_system(conn)
        return {
            "bw_systems": [with_status(s) for s in store.list_bw_systems(conn, include_retired=False)],
            "default_bw_system": default_system["id"] if default_system else None,
            "mcp_servers": mcpclient.list_servers(conn),
            "default_mcp_server": mcpclient.default_server(conn),
            "tasks": [t.public() for t in tasks.load_tasks()],
            "models": models(selectable=True, conn=conn),
            "all_models": [{"id": m["id"], "name": m["name"]} for m in store.list_models(conn)],
            "settings": settings,
            "thinking_levels": store.THINKING_LEVELS,
            "templates": planning.templates(conn),
            "notice_accepted": bool(store.notice_accepted(conn)),
            "busy": bool([b for b in runner.running_batches(conn) if b["alive"]]),
        }

    @app.post("/api/batches/preview")
    def batch_preview(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        result = planning.preview(conn, body)
        state = bw_status(str(body.get("bw_system") or ""))
        if state["state"] in (bwcheck.DOWN, bwcheck.PARTLY):
            result["warnings"].insert(0, {"kind": "bw_down", "text":
                                          f"Das BW-System {body.get('bw_system')} ist nicht bereit: {state['detail']}."})  # fmt: skip
        return result

    @app.post("/api/batches")
    def batch_start(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        control.ensure_idle(conn)
        batch_id = planning.plan_batch(conn, body)
        if body.get("start", True):
            control.start_runner(conn, batch_id)
        return db.one(conn, "SELECT id, code, status FROM batches WHERE id=?", (batch_id,)) or {}

    @app.get("/api/batches/{batch_id}")
    def batch_get(batch_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        state = live_state(conn, batch_id)
        if not state:
            raise HTTPException(404, "Durchgang nicht gefunden.")
        return state

    @app.get("/api/batches/{batch_id}/template")
    def batch_template(batch_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        result = planning.template(conn, batch_id)
        if not result:
            raise HTTPException(404, "Durchgang nicht gefunden.")
        return result

    @app.post("/api/batches/{batch_id}/start")
    def batch_run(batch_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"pid": control.start_runner(conn, batch_id)}

    @app.post("/api/batches/{batch_id}/cancel")
    def batch_cancel(batch_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        control.request_cancel(conn, batch_id)
        return {"ok": True}

    @app.post("/api/batches/{batch_id}/stale")
    def batch_stale(batch_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        batch = db.one(conn, "SELECT status, runner_pid FROM batches WHERE id=?", (batch_id,))
        if not batch or batch["status"] != "running" or db.pid_alive(batch["runner_pid"]):
            raise control.ControlError(
                "Dieser Durchgang hängt nicht: Sein Prozess läuft noch oder er ist schon beendet."
            )
        return {"runs": control.mark_stale(conn, batch_id)}

    @app.post("/api/batches/{batch_id}/hidden")
    def batch_hidden(batch_id: int, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        control.set_hidden(conn, batch_id, body.get("reason"))
        return {"ok": True}

    @app.post("/api/batches/{batch_id}/retry")
    def batch_retry(batch_id: int, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        new_codes = control.retry_runs(conn, [int(i) for i in body.get("runs") or []])
        control.start_runner(conn, batch_id)
        return {"runs": new_codes}

    @app.post("/api/batches/{batch_id}/reverify")
    def batch_reverify(batch_id: int, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return {"pid": control.start_reverify(conn, batch_id, [int(i) for i in body.get("runs") or []])}

    @app.get("/api/batches/{batch_id}/output")
    def batch_output(batch_id: int, conn: sqlite3.Connection = Conn) -> PlainTextResponse:
        batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
        if not batch:
            raise HTTPException(404, "Durchgang nicht gefunden.")
        return PlainTextResponse(control.runner_output(batch))

    @app.get("/api/live")
    def live(batch: int | None = None, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return live_state(conn, batch) or {"batch": None}

    @app.get("/api/live/stream")
    async def live_stream(request: Request, batch: int | None = None) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            last, last_sent = "", time.monotonic()
            while not await request.is_disconnected():
                conn = db.connect(migrate=False)
                try:
                    payload = json.dumps(live_state(conn, batch) or {"batch": None}, ensure_ascii=False)
                finally:
                    conn.close()
                if payload != last:
                    last, last_sent = payload, time.monotonic()
                    yield f"data: {payload}\n\n"
                elif time.monotonic() - last_sent > 15:
                    last_sent = time.monotonic()
                    yield ": ping\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})  # fmt: skip

    # ------------------------------------------------------------------ Läufe und Auswertung

    @app.get("/api/runs/{run_id}")
    def run_get(run_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        run = analysis.load_run(conn, run_id)
        if not run:
            raise HTTPException(404, "Lauf nicht gefunden.")
        return run

    @app.get("/api/runs")
    def run_index(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        """Knappe Liste aller abgeschlossenen Läufe für die Laufauswahl im Lauf-Detail."""
        keys = ("id", "run_code", "code", "label", "vendor", "task", "verify_status", "status", "valid", "started")
        return [{k: r[k] for k in keys} for r in reversed(analysis.load_runs(conn))]

    @app.get("/api/runs/{run_id}/log")
    def run_log(run_id: int, phase: str = "task", conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return read_log(conn, run_id, phase)

    @app.post("/api/runs/{run_id}/invalid")
    def run_invalid(run_id: int, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        control.set_invalid(conn, run_id, body.get("reason"))
        return {"ok": True}

    @app.post("/api/analysis")
    def analysis_post(body: dict = Body(default={}), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        return analysis.analyse(conn, body)

    @app.post("/api/analysis/csv")
    def analysis_csv(body: dict = Body(default={}), conn: sqlite3.Connection = Conn) -> PlainTextResponse:
        runs, _ = analysis.apply_filters(analysis.load_runs(conn), body)
        return PlainTextResponse(analysis.to_csv(runs), media_type="text/csv; charset=utf-8")

    @app.get("/api/leaderboard")
    def leaderboard(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        runs, _ = analysis.apply_filters(analysis.load_runs(conn), {})
        return analysis.leaderboard(runs)

    @app.get("/api/views")
    def views(conn: sqlite3.Connection = Conn) -> list[dict[str, Any]]:
        rows = db.rows(conn, "SELECT * FROM saved_views ORDER BY is_default DESC, name")
        return [{"name": r["name"], "saved": r["saved"], "is_default": bool(r["is_default"]),
                 "settings": db.loads(r["settings"], {})} for r in rows]  # fmt: skip

    @app.put("/api/views/{name}")
    def view_save(name: str, body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise store.StoreError("Die Ansicht braucht einen Namen.")
        if body.get("is_default"):
            conn.execute("UPDATE saved_views SET is_default=0")
        conn.execute(
            "INSERT INTO saved_views(name, saved, is_default, settings) VALUES (?,?,?,?) ON CONFLICT(name) "
            "DO UPDATE SET saved=excluded.saved, is_default=excluded.is_default, settings=excluded.settings",
            (name, db.now(), int(bool(body.get("is_default"))), db.dumps(body.get("settings") or {})),
        )
        return {"ok": True}

    @app.post("/api/views/{name}/default")
    def view_default(name: str, body: dict = Body(default={}), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        conn.execute("UPDATE saved_views SET is_default=0")
        if body.get("is_default", True):
            conn.execute("UPDATE saved_views SET is_default=1 WHERE name=?", (name,))
        return {"ok": True}

    @app.delete("/api/views/{name}")
    def view_delete(name: str, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        conn.execute("DELETE FROM saved_views WHERE name=?", (name,))
        return {"ok": True}

    # ------------------------------------------------------------------ BW bereinigen

    @app.get("/api/cleanup")
    def cleanup_state(conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        jobs = db.rows(conn, "SELECT * FROM cleanup_jobs ORDER BY id DESC LIMIT 20")
        for job in jobs:
            if job["status"] in ("running", "planned") and job["pid"] and not db.pid_alive(job["pid"]):
                control.mark_stale_cleanup(conn, job["id"])
                job.update(db.one(conn, "SELECT * FROM cleanup_jobs WHERE id=?", (job["id"],)) or {})
            for key in ("objects", "rest", "scope"):
                job[key] = db.loads(job[key], [] if key != "scope" else {})
        batches_ = db.rows(conn, "SELECT b.id, b.code, b.bw_system, b.mcp_server, b.created, b.agent, "
                                 "COUNT(r.id) AS runs FROM batches b LEFT JOIN runs r ON r.batch_id=b.id "
                                 "GROUP BY b.id ORDER BY b.created DESC")  # fmt: skip
        servers = []
        for server in mcpclient.list_servers(conn):
            names = {t["name"] for t in (server.get("last_test") or {}).get("tools") or []}
            servers.append({"name": server["name"], "is_default": server["is_default"], "tested": bool(names),
                            "supported": all(t in names for t in cleanup.REQUIRED_TOOLS) if names else None})  # fmt: skip
        return {
            "jobs": jobs, "batches": batches_, "servers": servers,
            "bw_systems": [with_status(s) for s in store.list_bw_systems(conn, include_retired=False)],
            "busy": bool([b for b in runner.running_batches(conn) if b["alive"]]),
            "blocked_codes": store.get_settings(conn)["run"]["blocked_codes"],
        }  # fmt: skip

    @app.post("/api/cleanup/search")
    async def cleanup_search(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        batch_codes = [codes.check_code(str(c).strip().upper()) for c in body.get("codes") or []]
        run_codes = [codes.check_run(str(c).strip().upper()) for c in body.get("runs") or []]
        if not batch_codes and not run_codes:
            raise store.StoreError("Bitte mindestens einen Durchgang oder Lauf wählen.")
        control.ensure_idle(conn)  # nicht während eines Durchgangs im BW suchen
        objects = await cleanup.search(conn, str(body.get("bw_system") or ""), str(body.get("mcp_server") or ""),
                                       batch_codes=batch_codes, run_codes=run_codes)  # fmt: skip
        return {"objects": objects}

    @app.post("/api/cleanup/jobs")
    def cleanup_start(body: dict = Body(...), conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        control.ensure_idle(conn)
        try:
            job_id = cleanup.plan(conn, str(body.get("bw_system") or ""), str(body.get("mcp_server") or ""),
                                  body.get("objects") or [], body.get("scope") or {})  # fmt: skip
        except ValueError as err:
            raise store.StoreError(str(err)) from None
        control.start_cleanup(conn, job_id)
        return {"id": job_id}

    @app.post("/api/cleanup/jobs/{job_id}/cancel")
    def cleanup_cancel(job_id: int, conn: sqlite3.Connection = Conn) -> dict[str, Any]:
        db.update(conn, "cleanup_jobs", {"id": job_id}, cancel_requested=1)
        return {"ok": True}

    # ------------------------------------------------------------------ Oberfläche

    web = paths.WEB_DIR

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Any:
        if path.startswith("api/"):
            raise HTTPException(404, "Nicht gefunden.")
        target = (web / path).resolve()
        if path and target.is_file() and web.resolve() in target.parents:
            return FileResponse(target)
        index = web / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return PlainTextResponse(
            "Die Oberfläche ist noch nicht gebaut. Bitte `npm --prefix frontend install` und "
            "`npm --prefix frontend run build` ausführen.", status_code=503)  # fmt: skip

    return app


# --------------------------------------------------------------------------- Live-Zustand


def live_state(conn: sqlite3.Connection, batch_id: int | None = None) -> dict[str, Any] | None:
    """Zustand eines Durchgangs für Live-Seite und Detail: ohne Angabe der laufende, sonst der jüngste."""
    if batch_id is None:
        row = db.one(conn, "SELECT id FROM batches WHERE status IN ('running', 'planned') ORDER BY "
                           "status='running' DESC, id DESC LIMIT 1")  # fmt: skip
        row = row or db.one(conn, "SELECT id FROM batches WHERE agent=? ORDER BY id DESC LIMIT 1", (AGENT_NAME,))
        row = row or db.one(conn, "SELECT id FROM batches ORDER BY created DESC, id DESC LIMIT 1")
        if not row:
            return None
        batch_id = row["id"]
    batch = db.one(conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    if not batch:
        return None
    alive = db.pid_alive(batch["runner_pid"]) if batch["status"] == "running" else False
    runs = db.rows(
        conn,
        "SELECT r.id, r.run_code, r.position, r.repeat, r.task_id, r.task_version, r.model_id, r.thinking, "
        "r.status, r.phase, r.action, r.started, r.finished, r.seconds, r.steps, r.tool_calls, r.tool_errors, "
        "r.last_requirement, r.cost_usd AS cost, r.cost_source, r.invalid, r.retry_of, r.error, "
        "r.tokens_input, r.tokens_output, m.name AS model_name, v.status AS verify_status, "
        "v.cost_usd AS verify_cost, v.verifier, v.reason AS verify_reason, t.title AS task_title, "
        "(SELECT x.run_code FROM runs x WHERE x.retry_of = r.id LIMIT 1) AS retried_as, "
        "(SELECT x.run_code FROM runs x WHERE x.id = r.retry_of) AS retry_of_code "
        "FROM runs r LEFT JOIN models m ON m.id=r.model_id LEFT JOIN verifications v ON v.run_id=r.id "
        "LEFT JOIN tasks t ON t.id=r.task_id AND t.version=r.task_version "
        "WHERE r.batch_id=? ORDER BY r.repeat, r.position, r.id",
        (batch_id,),
    )
    current = None
    for run in runs:
        run["model_name"] = run["model_name"] or vendors.split_model_id(run["model_id"])[1]
        run["vendor"] = vendors.vendor_of(run["model_id"])
        if run["status"] == "running" or (run["phase"] in ("task", "verify") and run["status"] != "planned"
                                          and batch["status"] == "running"):  # fmt: skip
            current = run
    detail = None
    if current:
        task = db.one(conn, "SELECT requirements, timeout_s, title FROM tasks WHERE id=? AND version=?",
                      (current["task_id"], current["task_version"]))  # fmt: skip
        events = db.rows(conn, "SELECT phase, seconds, step, kind, tool, requirement, is_error, text, duration "
                               "FROM run_events WHERE run_id=? ORDER BY id", (current["id"],))  # fmt: skip
        names = [r["name"] for r in db.loads(task["requirements"], [])] if task else []
        verify_started = db.one(
            conn, "SELECT ts FROM run_events WHERE run_id=? AND phase='verify' ORDER BY id LIMIT 1", (current["id"],)
        )
        detail = {
            "id": current["id"],
            "requirements": analysis.requirement_progress(events, names),
            "timeout_s": task["timeout_s"] if task else None,
            "task_title": task["title"] if task else "",
            "recent": [e for e in events if e["kind"] in ("tool", "error")][-12:],
            "verify_steps": sum(1 for e in events if e["phase"] == "verify" and e["kind"] == "step"),
            "verify_started": verify_started["ts"] if verify_started else None,
            "verify_timeout_s": store.get_settings(conn)["verify"]["timeout_s"],
        }
    done = [r for r in runs if r["status"] not in ("planned", "running")]
    return {
        "batch": {**{k: batch[k] for k in ("id", "code", "status", "status_message", "created", "started",
                                           "finished", "bw_system", "mcp_server", "repeats", "thinking",
                                           "verifier", "fallback_verifier", "cost_limit", "note", "hidden",
                                           "agent", "agent_version", "cancel_requested")},
                  "alive": alive, "stale": batch["status"] == "running" and not alive,
            "other_agent": batch["agent"] != AGENT_NAME,
            "verifier_name": store.model_display(conn, batch["verifier"]) if batch["verifier"] else "",
            "fallback_name": store.model_display(conn, batch["fallback_verifier"]) if batch["fallback_verifier"] else "",
                  "cost": runner.batch_cost(conn, batch_id)},
        "runs": runs,
        "current": detail,
        "progress": {"total": len(runs), "done": len(done),
                     "passed": sum(r["verify_status"] == "pass" and not r["invalid"] for r in runs),
                     "failed": sum(r["verify_status"] == "fail" and not r["invalid"] for r in runs),
                     "invalid": sum(bool(r["invalid"]) for r in runs)},
        "now": db.now(),
    }  # fmt: skip


# --------------------------------------------------------------------------- Protokoll


def read_log(conn: sqlite3.Connection, run_id: int, phase: str, max_bytes: int = 6_000_000) -> dict[str, Any]:
    """Protokoll eines Laufs oder seiner Prüfung, geschwärzt."""
    if phase == "verify":
        row = db.one(conn, "SELECT log_path FROM verifications WHERE run_id=?", (run_id,))
    else:
        row = db.one(conn, "SELECT log_path FROM runs WHERE id=?", (run_id,))
    path = _resolve_log(row["log_path"] if row else None)
    if not path:
        return {"available": False, "entries": [], "text": "", "truncated": False}
    redact = _display_redactor(conn)
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        raw = handle.read().decode("utf-8", errors="replace")
    raw = redact(raw) or ""
    if path.suffix != ".jsonl":
        return {"available": True, "format": "text", "entries": [], "text": raw, "truncated": size > max_bytes}
    entries = []
    for line in raw.splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return {"available": True, "format": "jsonl", "entries": entries, "text": "", "truncated": size > max_bytes}


def _resolve_log(stored: str | None) -> Path | None:
    """Findet ein Protokoll auch, wenn der Datenordner verschoben wurde; nie außerhalb davon."""
    if not stored:
        return None
    logs = paths.logs_dir().resolve()
    candidates = [Path(stored)]
    parts = Path(stored).parts
    if "logs" in parts:
        index = len(parts) - 1 - parts[::-1].index("logs")
        candidates.append(logs.joinpath(*parts[index + 1 :]))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and logs in resolved.parents:
            return resolved
    return None


def _display_redactor(conn: sqlite3.Connection) -> vault.Redactor:
    values, users = [], []
    for system in store.list_bw_systems(conn):
        value = vault.get(vault.bw_password(system["id"]))
        if value:
            values.append(value)
        if system["user"]:
            users.append(system["user"])
    for platform in store.list_platforms(conn):
        value = vault.get(vault.platform_key(platform["id"]))
        if value:
            values.append(value)
            try:
                key = json.loads(value)
                if isinstance(key, dict):
                    values += [str(v) for k, v in key.items() if "secret" in k.lower() and isinstance(v, str)]
            except ValueError:
                pass
    return vault.Redactor(values, users)


# --------------------------------------------------------------------------- Kurztest


async def quicktest(conn: sqlite3.Connection, model_id: str) -> dict[str, Any]:
    """Kurze Anfrage mit einem Werkzeugaufruf; Ergebnis und Datum werden gespeichert."""
    if not store.get_model(conn, model_id):
        raise store.StoreError(f"Modell „{model_id}“ gibt es nicht.")
    started = time.monotonic()
    result: dict[str, Any]
    adapter = None
    try:
        adapter, platform_model, platform = adapter_for_model(conn, model_id)
        reply = await adapter.complete(ModelRequest(
            model=platform_model,
            system="Du testest eine Verbindung. Halte dich genau an die Anweisung.",
            turns=[Turn(role="user", text="Rufe das Werkzeug echo mit dem Text „hallo“ auf.")],
            tools=[{"name": "echo", "description": "Gibt den übergebenen Text zurück.",
                    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                                     "required": ["text"]}}],
            max_output_tokens=2000, caching=False, timeout_s=90,
        ))  # fmt: skip
        called = any(c.name == "echo" for c in reply.tool_calls)
        result = {"ok": called,
                  "message": "Werkzeugaufruf erhalten" if called else "Antwort ohne Werkzeugaufruf: "
                  + (reply.text[:200] or "(leer)")}  # fmt: skip
    except PlatformError as err:
        secrets = adapter.secrets() if adapter else []
        result = {"ok": False, "message": vault.Redactor(secrets)(str(err)[:400]), "kind": err.kind}
    finally:
        if adapter:
            await adapter.aclose()
    result.update(at=db.now(), seconds=round(time.monotonic() - started, 1))
    db.update(conn, "models", {"id": model_id}, quicktest=db.dumps(result))
    return result
