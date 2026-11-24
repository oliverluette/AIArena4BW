"""Schnittstelle: Schutz vor fremden Anfragen, Einstellungen, Start aus der App, Auswertung, Bereinigen."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from aiarena4bw import analysis, cleanup, db, mcpclient, store, vault
from aiarena4bw.api import create_app
from aiarena4bw.runs import planning, runner

H = {"X-AIArena": "1"}


@pytest.fixture
def client():
    app = create_app(port=8321, monitor=False, extra_hosts=("testserver",))
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- Schutz


def test_foreign_host_origin_and_missing_header_are_rejected(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 403
    assert client.get("/api/health", headers={"Origin": "https://evil.example.com"}).status_code == 403
    assert client.put("/api/settings", json={}).status_code == 403  # ohne X-AIArena
    assert client.put("/api/settings", json={}, headers=H).status_code == 200
    assert client.put("/api/settings", json={}, headers={**H, "Origin": "https://evil.example.com"}).status_code == 403


def test_spa_serves_index_or_explains_missing_build(client):
    response = client.get("/einstellungen/bw")
    assert response.status_code in (200, 503)
    assert client.get("/api/gibt-es-nicht").status_code == 404


# --------------------------------------------------------------------------- Einstellungen


def test_settings_flow_never_returns_secrets(client):
    r = client.post(
        "/api/bw-systems",
        headers=H,
        json={
            "id": "A4H",
            "url": "https://bw:44300",
            "user": "DEV",
            "password": "pw-geheim-77",
            "parent_area": "ZBENCH_AI",
        },
    )
    assert r.status_code == 200 and r.json()["password_set"] is True
    assert "pw-geheim-77" not in r.text and "pw-geheim-77" not in client.get("/api/bw-systems").text
    r = client.post("/api/bw-systems", headers=H, json={"id": "A4H", "url": "https://bw:44300", "parent_area": "X"})
    assert r.status_code == 400 and "gibt es schon" in r.json()["detail"]
    r = client.put(
        "/api/bw-systems/A4H", headers=H, json={"url": "https://bw:44300", "parent_area": "ZBENCH_AI", "prefix": "ZX"}
    )
    assert r.json()["prefix"] == "ZX" and r.json()["password_set"] is True  # leeres Passwort = unverändert

    r = client.post(
        "/api/platforms", headers=H, json={"id": "or", "type": "openrouter", "credentials": "sk-or-geheim-1"}
    )
    assert r.json()["credentials_set"] is True and "sk-or-geheim-1" not in r.text
    assert "sk-or-geheim-1" not in client.get("/api/platforms").text
    assert vault.get(vault.platform_key("or")) == "sk-or-geheim-1"

    r = client.put("/api/secrets/token", headers=H, json={"value": "tok-geheim-2"})
    assert r.json() == {"name": "token", "set": True}
    assert client.get("/api/secrets").json() == [{"name": "token", "set": True}]
    dump = json.dumps(db.rows(db.connect(), "SELECT * FROM settings")) + json.dumps(
        db.rows(db.connect(), "SELECT * FROM platforms")
    )
    assert "geheim" not in dump


def test_mcp_editor_validation_and_default_entry(client):
    data = client.get("/api/mcp").json()
    assert data["servers"][0]["name"] == "coBWeb-mcp" and data["servers"][0]["needs_path"]
    assert "${BW_PASSWORD}" in data["text"]
    bad = client.post("/api/mcp/validate", headers=H, json={"text": '{"mcpServers": {"x": {"command": 1}}}'}).json()
    assert bad["ok"] is False and "command" in bad["message"]
    warn = client.post(
        "/api/mcp/validate",
        headers=H,
        json={"text": '{"mcpServers": {"x": {"command": "n", "env": {"BW_PASSWORD": "klartext"}}}}'},
    ).json()
    assert warn["ok"] is True and "Klartext" in warn["warnings"][0]
    assert client.put("/api/mcp", headers=H, json={"text": "{"}).status_code == 400
    test = client.post("/api/mcp/coBWeb-mcp/test", headers=H, json={}).json()
    assert test["ok"] is False and "Platzhalter-Pfad" in test["message"]


def test_platform_test_catalog_and_selection(client, arena):
    tested = client.post("/api/platforms/or/test", headers=H).json()
    assert tested["ok"] is True and tested["message"] == "Schlüssel gültig, Restlimit 12.50 $"
    assert client.post("/api/platforms/or/catalog", headers=H).json() == {"count": 2}  # Embedder und Router fehlen
    models = {m["model_id"]: m for m in client.get("/api/platforms/or/models").json()}
    good = models["anthropic/claude-good"]
    assert good["name"] == "Claude Good" and good["price_in"] == 1.0 and good["price_cache_read"] == 0.1
    assert good["supports_reasoning"] is True and good["released"] == "2025-10-09"
    assert models["openai/gpt-verifier"]["max_tools"] == 128
    assert client.post("/api/platforms/ant/catalog", headers=H).json() == {"count": 2}
    haiku = next(m for m in client.get("/api/platforms/ant/models").json() if m["model_id"] == "claude-haiku-5-5")
    assert haiku["price_in"] == 0.1 and haiku["context_window"] == 1000000
    assert client.post("/api/platforms/sap/catalog", headers=H).json() == {"count": 1}
    assert client.post("/api/platforms/lms/catalog", headers=H).json() == {"count": 1}
    assert client.post("/api/platforms/sap/test", headers=H).json()["ok"] is True
    client.patch("/api/model", headers=H, json={"id": "or:x/lazy", "selected": False})
    assert "or:x/lazy" not in [m["id"] for m in client.get("/api/models?selectable=true").json()]
    quick = client.post("/api/model/quicktest", headers=H, json={"id": "or:anthropic/claude-good"}).json()
    assert quick["ok"] is False and "ohne Werkzeugaufruf" in quick["message"]  # der Nachbau kennt echo nicht


def test_mcp_test_against_bw_system(client, arena):
    result = client.post("/api/mcp/fake/test", headers=H, json={"bw_system": "TST"}).json()
    assert result["ok"] and result["server_name"] == "fake-bw" and result["tool_count"] == 4
    assert {t["name"]: t["access"] for t in result["tools"]} == {
        "bw_search": "read",
        "bw_read": "read",
        "bw_context": "read",
        "bw_write": "write",
    }
    assert result["token_estimate"] > 100
    client.put("/api/mcp/fake/options", headers=H, json={"tool_overrides": {"bw_context": "write"}})
    again = client.post("/api/mcp/fake/test", headers=H, json={"bw_system": "TST"}).json()
    assert {t["name"]: t["access"] for t in again["tools"]}["bw_context"] == "write"


# --------------------------------------------------------------------------- Start aus der App


def wait_for(client, batch_id, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/batches/{batch_id}").json()
        if state["batch"]["status"] not in ("planned", "running"):
            return state
        time.sleep(0.3)
    raise AssertionError("Durchgang wurde nicht fertig: " + client.get(f"/api/batches/{batch_id}/output").text[-800:])


def test_preview_start_runner_process_and_live_state(client, arena):
    """Ohne Browser: Start aus der App, der Runner läuft als eigener Prozess."""
    spec = arena.spec(models=["or:anthropic/claude-good", "or:openai/gpt-verifier"], thinking=["", "high"])
    preview = client.post("/api/batches/preview", headers=H, json=spec).json()
    assert preview["code"] == "AAA" and preview["runs"] == 4 and preview["levels"] == ["", "high"]
    kinds = {w["kind"] for w in preview["warnings"]}
    assert {"data", "verifier_fallback", "mcp_untested"} <= kinds and "no_price" not in kinds
    assert preview["estimate"]["usd"] is None
    too_many = client.post(
        "/api/batches/preview",
        headers=H,
        json={
            **spec,
            "models": [*spec["models"], "or:x/lazy"],
            "repeats": 9,
            "thinking": ["", "low", "medium", "high", "xhigh"],
        },
    )
    assert too_many.status_code == 400 and "höchstens 99" in too_many.json()["detail"]

    started = client.post("/api/batches", headers=H, json=spec).json()
    assert started["code"] == "AAA"
    busy = client.post("/api/batches", headers=H, json=spec)
    assert busy.status_code == 400 and "läuft noch" in busy.json()["detail"]
    state = wait_for(client, started["id"])
    assert state["batch"]["status"] == "done" and state["progress"] == {
        "total": 4,
        "done": 4,
        "passed": 4,
        "failed": 0,
        "invalid": 0,
    }
    assert [r["thinking"] for r in state["runs"]] == ["", "high", "", "high"]
    assert "Durchgang AAA" in client.get(f"/api/batches/{started['id']}/output").text
    overview = client.get("/api/batches").json()[0]
    assert overview["passed"] == 4 and overview["verified"] == 4 and overview["cost"] == pytest.approx(4 * 0.05)
    # Danach gibt es Erfahrungswerte für die Kostenschätzung.
    again = client.post("/api/batches/preview", headers=H, json=spec).json()
    assert (
        again["code"] == "AAB"
        and again["estimate"]["usd"] == pytest.approx(4 * 0.05)
        and again["estimate"]["known"] == 4
    )


def test_earlier_batch_as_template(client, arena):
    """REQ F-D11: Ein früherer Durchgang liefert seine Auswahl als Vorlage für einen neuen."""
    spec = arena.spec(
        models=["or:anthropic/claude-good", "or:x/lazy"], thinking=["high", ""], repeats=3,
        verifier="or:x/slow", cost_limit=7.5, note="Vergleich vor dem Update", start=False,
    )  # fmt: skip
    planned = client.post("/api/batches", headers=H, json=spec).json()
    listed = client.get("/api/start-options").json()["templates"]
    assert [(t["code"], t["tasks"], t["models"], t["repeats"], t["note"]) for t in listed] == [
        ("AAA", 1, 2, 3, "Vergleich vor dem Update")
    ]
    template = client.get(f"/api/batches/{planned['id']}/template").json()
    assert template["code"] == "AAA" and template["notes"] == []
    assert template["spec"] == {
        "bw_system": "TST",
        "mcp_server": "fake",
        "tasks": ["mini"],
        "models": ["or:anthropic/claude-good", "or:x/lazy"],
        "thinking": ["", "high"],
        "repeats": 3,
        "verifier": "or:x/slow",
        "fallback": "or:anthropic/claude-good",
        "cost_limit": 7.5,
        "note": "Vergleich vor dem Update",
    }
    # Die Vorlage ergibt denselben Plan wie die ursprüngliche Auswahl.
    preview = client.post("/api/batches/preview", headers=H, json=template["spec"]).json()
    assert (preview["runs"], preview["levels"], preview["cost_limit"]) == (12, ["", "high"], 7.5)
    assert client.get("/api/batches/999/template").status_code == 404


def test_template_says_what_is_gone_or_changed(client, arena):
    """REQ F-D11: Was es nicht mehr gibt, fehlt in der Vorlage und wird genannt."""
    spec = arena.spec(models=["or:anthropic/claude-good", "or:x/lazy"], start=False)
    batch_id = client.post("/api/batches", headers=H, json=spec).json()["id"]
    conn = arena.conn
    conn.execute("UPDATE models SET selected=0 WHERE id='or:x/lazy'")
    conn.execute("UPDATE batch_items SET task_version=task_version+1 WHERE batch_id=?", (batch_id,))
    conn.execute("UPDATE bw_systems SET retired=1 WHERE id='TST'")
    conn.execute(
        "UPDATE batches SET mcp_server='alt', verifier='or:gone/model', fallback_verifier='', "
        "cost_limit=57.19, cost_limit_planned=NULL WHERE id=?",
        (batch_id,),
    )
    template = client.get(f"/api/batches/{batch_id}/template").json()
    assert template["spec"] == {
        "bw_system": None,
        "mcp_server": None,
        "tasks": ["mini"],
        "models": ["or:anthropic/claude-good"],
        "thinking": [""],
        "repeats": 1,
        "verifier": "",
        "fallback": "",
        "cost_limit": None,
        "note": "",
    }
    notes = {n["kind"]: n["text"] for n in template["notes"]}
    assert set(notes) == {"bw_system", "mcp_server", "task_version", "models", "verifier", "cost_limit"}
    assert "TST" in notes["bw_system"] and "alt" in notes["mcp_server"] and "lazy" in notes["models"]
    assert "inzwischen in Version" in notes["task_version"] and "AAA lief mit Version" in notes["task_version"]
    assert [n["text"] for n in template["notes"] if n["kind"] == "verifier"] == [
        "Das Prüfmodell or:gone/model ist nicht mehr eingerichtet; es gilt die Einstellung.",
        "AAA lief ohne Ersatzmodell; jetzt gilt die Einstellung.",
    ]
    # Eine gelöschte Aufgabe fällt heraus.
    conn.execute("UPDATE batch_items SET task_id='weg' WHERE batch_id=?", (batch_id,))
    gone = client.get(f"/api/batches/{batch_id}/template").json()
    assert gone["spec"]["tasks"] == [] and "„weg“" in gone["notes"][2]["text"]


def test_cancel_from_app_stops_runner_within_seconds(client, arena):
    started = client.post("/api/batches", headers=H, json=arena.spec(models=["or:x/slow"], repeats=3)).json()
    deadline = time.time() + 20
    while time.time() < deadline and not client.get("/api/live").json().get("current"):
        time.sleep(0.2)
    live = client.get("/api/live").json()
    assert live["batch"]["alive"] and live["current"] and live["runs"][0]["status"] == "running"
    began = time.time()
    client.post(f"/api/batches/{started['id']}/cancel", headers=H)
    state = wait_for(client, started["id"])
    assert time.time() - began < 10
    assert state["batch"]["status"] == "cancelled"
    assert [r["status"] for r in state["runs"]] == ["cancelled", "skipped", "skipped"]


def test_stale_batch_can_be_cleaned_up(client, arena):
    batch_id = planning.plan_batch(arena.conn, arena.spec())
    db.update(arena.conn, "batches", {"id": batch_id}, status="running", runner_pid=999999)
    db.update(arena.conn, "runs", {"batch_id": batch_id}, status="running", phase="task")
    assert client.get(f"/api/batches/{batch_id}").json()["batch"]["stale"] is True
    assert client.post(f"/api/batches/{batch_id}/stale", headers=H).json() == {"runs": 1}
    state = client.get(f"/api/batches/{batch_id}").json()
    assert state["batch"]["status"] == "error" and state["runs"][0]["status"] == "cancelled"


# --------------------------------------------------------------------------- Auswertung


async def seeded(arena):
    """Fester Datensatz: good (2× bestanden), halfway (2× nicht bestanden), broke (ungültig), lazy (ungeprüft)."""
    store.save_settings(arena.conn, {"run": {"api_retries": 0}})
    batch_id = planning.plan_batch(
        arena.conn,
        arena.spec(models=["or:anthropic/claude-good", "or:x/halfway", "or:x/broke", "or:x/lazy"], repeats=2),
    )
    await runner.run_batch(arena.conn, batch_id)
    return batch_id


async def test_analysis_matches_precomputed_values(client, arena):
    """Kennzahlen für einen festen Datensatz."""
    await seeded(arena)
    data = client.post("/api/analysis", headers=H, json={}).json()
    assert data["counts"] == {"all": 8, "shown": 6, "invalid": 2, "hidden": 0}
    summary = {s["label"]: s for s in data["summary"]}
    good, half, lazy = summary["Good"], summary["x/halfway"], summary["x/lazy"]
    assert (good["runs"], good["verified"], good["passed"], good["pass_rate"]) == (2, 2, 2, 1.0)
    assert good["tokens_input"] == 6000 and good["tokens_new"] == 3600 and good["tokens_cache_read"] == 2400
    assert (
        good["cost"] == pytest.approx(0.03)
        and good["cost_sum"] == pytest.approx(0.06)
        and good["cost_per_pass"] == pytest.approx(0.03)
    )
    assert good["cost_source"] == "billed" and good["vendor"] == "Anthropic" and good["steps"] == 3
    assert (half["verified"], half["passed"], half["pass_rate"], half["cost_per_pass"]) == (2, 0, 0.0, None)
    assert (lazy["verified"], lazy["pass_rate"]) == (0, None)
    assert "x/broke" not in summary
    with_invalid = client.post("/api/analysis", headers=H, json={"include_invalid": True}).json()
    assert with_invalid["counts"]["shown"] == 8 and any(not r["valid"] for r in with_invalid["runs"])
    only = client.post("/api/analysis", headers=H, json={"vendors": ["Anthropic"]}).json()
    assert {r["label"] for r in only["runs"]} == {"Good"} and only["options"]["models"] == ["Good"]
    assert set(only["options"]["vendors"]) == {"Anthropic", "X"}  # Auswahl folgt nur den Filtern davor
    hidden = client.post("/api/analysis", headers=H, json={"excluded": ["Good"]}).json()
    assert "Good" not in {s["label"] for s in hidden["summary"]} and "Good" in hidden["options"]["excluded"]
    board = client.get("/api/leaderboard").json()[0]
    assert board["task"] == "mini v1" and [(e["label"], e["rank"]) for e in board["entries"]] == [
        ("Good", 1),
        ("x/halfway", 2),
    ]
    # Formkurve: ein Eintrag je gewertetem Lauf, in zeitlicher Folge, mit Urteil und Laufkennung.
    for entry in board["entries"]:
        assert len(entry["form"]) == entry["runs"]
        assert sum(f["verdict"] == "pass" for f in entry["form"]) == entry["passed"]
        assert all(set(f) == {"id", "run_code", "verdict"} for f in entry["form"])
        assert [f["id"] for f in entry["form"]] == sorted(f["id"] for f in entry["form"])
    csv = client.post("/api/analysis/csv", headers=H, json={}).text.splitlines()
    assert csv[0].startswith("Lauf;Durchgang;Aufgabe") and len(csv) == 7 and "kein Preis" not in csv[1]


async def test_labels_separate_thinking_mcp_and_agent(arena):
    batch_id = planning.plan_batch(arena.conn, arena.spec(thinking=["", "high"]))
    await runner.run_batch(arena.conn, batch_id)
    other = db.insert(
        arena.conn,
        "batches",
        code="T",
        created=db.now(),
        status="done",
        bw_system="TST",
        mcp_server="anderer-mcp",
        agent="OtherAgent",
        agent_version="2.1",
    )
    db.insert(
        arena.conn,
        "runs",
        batch_id=other,
        position=1,
        repeat=1,
        run_code="T011",
        task_id="mini",
        task_version=1,
        model_id="or:anthropic/claude-good",
        status="finished",
        seconds=100,
        tokens_input=50000,
        cost_usd=1.0,
    )
    labels = sorted({r["label"] for r in analysis.load_runs(arena.conn)})
    assert labels == ["Good", "Good/anderer-mcp/OtherAgent", "Good/high"]
    runs = analysis.load_runs(arena.conn)
    assert {r["agent_label"] for r in runs} == {"AIArena4BW", "OtherAgent 2.1"}
    assert {r["thinking_label"] for r in runs} == {"ohne Vorgabe", "high"}


async def test_run_detail_log_invalid_and_hide(client, arena):
    batch_id = await seeded(arena)
    run_id = db.one(arena.conn, "SELECT id FROM runs WHERE run_code='AAA01'")["id"]
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run_code"] == "AAA01" and detail["verification"]["status"] == "pass"
    assert [r["reached"] for r in detail["requirements"]] == [True, True, True]
    assert detail["environment"]["agent"] == "AIArena4BW" and len(detail["verification"]["points"]) == 2
    log = client.get(f"/api/runs/{run_id}/log").json()
    assert log["available"] and log["format"] == "jsonl" and log["entries"][0]["type"] == "meta"
    assert client.get(f"/api/runs/{run_id}/log?phase=verify").json()["entries"][-1]["type"] == "end"
    assert "bw-geheim-123" not in json.dumps(log)
    assert client.get("/api/runs/99999").status_code == 404

    client.post(f"/api/runs/{run_id}/invalid", headers=H, json={"reason": "BW war instabil"})
    assert client.post("/api/analysis", headers=H, json={}).json()["counts"]["invalid"] == 3
    client.post(f"/api/runs/{run_id}/invalid", headers=H, json={"reason": ""})
    client.post(f"/api/batches/{batch_id}/hidden", headers=H, json={"reason": "Probelauf"})
    assert client.post("/api/analysis", headers=H, json={}).json()["counts"] == {
        "all": 8,
        "shown": 0,
        "invalid": 2,
        "hidden": 8,
    }
    assert client.post("/api/analysis", headers=H, json={"include_hidden": True}).json()["counts"]["shown"] == 6
    assert client.get("/api/leaderboard").json() == []


def test_saved_views(client):
    client.put("/api/views/Artikel", headers=H, json={"settings": {"chart": {"x": "seconds"}}, "is_default": True})
    client.put("/api/views/Zweite", headers=H, json={"settings": {}, "is_default": True})
    views = client.get("/api/views").json()
    assert [(v["name"], v["is_default"]) for v in views] == [("Zweite", True), ("Artikel", False)]
    client.post("/api/views/Artikel/default", headers=H, json={})
    assert client.get("/api/views").json()[0]["name"] == "Artikel"
    client.delete("/api/views/Zweite", headers=H)
    assert len(client.get("/api/views").json()) == 1


# --------------------------------------------------------------------------- Aufgaben


def test_task_editor_protects_used_versions(client, arena):
    task = client.get("/api/tasks/mini").json()
    assert task["version"] == 1 and task["used_runs"] == 0
    draft = {**task, "title": "Neuer Titel"}
    assert (
        client.post("/api/tasks", headers=H, json=draft).json()["title"] == "Neuer Titel"
    )  # unbenutzt: gleiche Version
    batch = planning.plan_batch(arena.conn, arena.spec())
    db.update(arena.conn, "runs", {"batch_id": batch}, status="finished")
    changed = {**draft, "prompt": draft["prompt"] + "\nZusatz {RUN}"}
    refused = client.post("/api/tasks", headers=H, json=changed)
    assert refused.status_code == 400 and "verfälscht den Vergleich" in refused.json()["detail"]
    saved = client.post("/api/tasks", headers=H, json={**changed, "confirm_new_version": True, "note": "Zusatz"}).json()
    assert saved["version"] == 2 and saved["history"][-1]["notiz"] == "Zusatz" and saved["used_versions"] == {"1": 1}
    old = client.get("/api/tasks/mini?version=1").json()
    assert old["stored_only"] and "Zusatz" not in old["prompt"]
    preview = client.post(
        "/api/tasks/preview", headers=H, json={**changed, "bw_system": "TST", "run_code": "AAB07"}
    ).json()
    assert "RUN=AAB07 AREA=ZBENCH_AAB07 PREFIX=ZB" in preview["prompt"] and preview["errors"] == []


# --------------------------------------------------------------------------- BW bereinigen


async def test_cleanup_finds_and_deletes_only_matching_objects(client, arena):
    await runner.run_batch(arena.conn, planning.plan_batch(arena.conn, arena.spec(repeats=2)))
    # Fremde Objekte und ein am aDSO hängender DTP mit vom System vergebenem Namen.
    state = json.loads(arena.state.read_text())
    state["objects"].update({
        "ADSO:ZBAAA01D1": {"type": "ADSO", "name": "ZBAAA01D1", "status": "active", "title": "aDSO"},
        "DTPA:DTP_0XYZ": {"type": "DTPA", "name": "DTP_0XYZ", "status": "active", "title": "", "owner": "ZBAAA01D1"},
        "IOBJ:ZBAAA011X": {"type": "IOBJ", "name": "ZBAAA011X", "status": "active", "title": "fremd: andere Laufnummer"},
        "IOBJ:ZBOTHER": {"type": "IOBJ", "name": "ZBOTHER", "status": "active", "title": "fremd"},
        "AREA:ZBENCH_AI": {"type": "AREA", "name": "ZBENCH_AI", "status": "active", "title": "Eltern-InfoArea"},
    })  # fmt: skip
    arena.state.write_text(json.dumps(state))
    found = client.post(
        "/api/cleanup/search", headers=H, json={"bw_system": "TST", "mcp_server": "fake", "codes": ["AAA"]}
    ).json()["objects"]
    assert [(o["type"], o["name"]) for o in found] == [
        ("DTPA", "DTP_0XYZ"), ("ADSO", "ZBAAA01D1"), ("IOBJ", "ZBAAA01CU"), ("IOBJ", "ZBAAA02CU"),
        ("AREA", "ZBENCH_AAA01"), ("AREA", "ZBENCH_AAA02"),
    ]  # fmt: skip
    assert next(o for o in found if o["type"] == "DTPA")["via"] == "ZBAAA01D1"
    one_run = client.post(
        "/api/cleanup/search", headers=H, json={"bw_system": "TST", "mcp_server": "fake", "runs": ["AAA02"]}
    ).json()["objects"]
    assert [o["name"] for o in one_run] == ["ZBAAA02CU", "ZBENCH_AAA02"]
    foreign = client.post(
        "/api/cleanup/jobs",
        headers=H,
        json={
            "bw_system": "TST",
            "mcp_server": "fake",
            "objects": [{"type": "IOBJ", "name": "ZBOTHER", "code": "AAA", "run": "AAA01"}],
            "scope": {},
        },
    )
    assert foreign.status_code == 400 and "Namenskonvention" in foreign.json()["detail"]

    job_id = cleanup.plan(arena.conn, "TST", "fake", found, {"codes": ["AAA"]})
    assert await cleanup.execute(arena.conn, job_id) == "done"
    job = client.get("/api/cleanup").json()["jobs"][0]
    assert job["status"] == "done" and job["message"] == "6 gelöscht, 0 Fehler, danach noch 0 im BW"
    assert {o["result"] for o in job["objects"]} == {"deleted"}
    assert set(arena.bw_objects()) == {"IOBJ:ZBAAA011X", "IOBJ:ZBOTHER", "AREA:ZBENCH_AI"}


def test_cleanup_is_blocked_for_servers_without_cobweb_tools(client, arena):
    text = json.loads(mcpclient.definition_text(arena.conn))
    text["mcpServers"]["fake"]["env"]["FAKE_MCP_TOOLS"] = "bw_search,bw_read"
    mcpclient.save_definition_text(arena.conn, json.dumps(text))
    r = client.post("/api/cleanup/search", headers=H, json={"bw_system": "TST", "mcp_server": "fake", "codes": ["AAA"]})
    assert r.status_code == 400 and "bw_context" in r.json()["detail"]
    client.post("/api/mcp/fake/test", headers=H, json={"bw_system": "TST"})
    assert client.get("/api/cleanup").json()["servers"][0]["supported"] is False


# --------------------------------------------------------------------------- Nutzungshinweis


def test_start_needs_accepted_notice(client, arena):
    arena.conn.execute("DELETE FROM meta WHERE key='notice_accepted'")
    assert client.get("/api/status").json()["notice_accepted"] is None
    assert client.get("/api/start-options").json()["notice_accepted"] is False
    with pytest.raises(planning.PlanError, match="Nutzungshinweis"):
        planning.plan_batch(arena.conn, arena.spec())
    assert client.post("/api/notice").status_code == 403  # ohne X-AIArena
    assert client.post("/api/notice", headers=H).json()["accepted"]
    assert client.get("/api/status").json()["notice_accepted"]
    assert planning.plan_batch(arena.conn, arena.spec())


def test_newer_notice_must_be_accepted_again(conn, monkeypatch):
    store.accept_notice(conn)
    assert store.notice_accepted(conn)
    monkeypatch.setattr(store, "NOTICE_VERSION", store.NOTICE_VERSION + 1)
    assert store.notice_accepted(conn) is None


def test_cli_run_shows_notice_until_accepted(arena, capsys):
    from aiarena4bw import cli

    arena.conn.execute("DELETE FROM meta WHERE key='notice_accepted'")
    argv = ["run", "--tasks", "mini", "--models", "or:anthropic/claude-good", "--plan-only"]
    assert cli.main(argv) == 1
    assert "Nur mit Test- und Demosystemen" in capsys.readouterr().err
    assert not store.notice_accepted(arena.conn)
    assert cli.main([*argv, "--accept-notice"]) == 0
    assert store.notice_accepted(arena.conn)


def test_preview_warns_about_mcp_safety(client, arena):
    preview = planning.preview(arena.conn, arena.spec())
    texts = [w["text"] for w in preview["warnings"] if w["kind"] == "mcp_safety"]
    assert texts and "nicht prüfen" in texts[0]  # der Nachbau ist kein coBWeb
    assert [f"fake: {t}" for t in client.get("/api/mcp").json()["servers"][0]["safety"]] == texts
