"""Durchgänge gegen die Nachbauten: Planung, Ausführung, Prüfung, Grenzen, Störungen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiarena4bw import bwcheck, db, store
from aiarena4bw.runs import control, planning, runner


def runs_of(conn, batch_id):
    return db.rows(conn, "SELECT * FROM runs WHERE batch_id=? ORDER BY id", (batch_id,))


def verification(conn, run_id):
    return db.one(conn, "SELECT * FROM verifications WHERE run_id=?", (run_id,))


async def go(arena, **spec):
    batch_id = planning.plan_batch(arena.conn, arena.spec(**spec))
    final = await runner.run_batch(arena.conn, batch_id)
    return batch_id, final


async def test_batch_two_models_two_repeats(arena):
    """2 Modelle × 2 Wiederholungen, jedes Urteil von einem anderen Modell."""
    batch_id, final = await go(arena, models=["or:anthropic/claude-good", "or:openai/gpt-verifier"], repeats=2)
    assert final == "done"
    runs = runs_of(arena.conn, batch_id)
    assert [r["run_code"] for r in runs] == ["AAA01", "AAA02", "AAA03", "AAA04"]
    # Wiederholung außen: die Modelle wechseln sich ab.
    assert [r["model_id"] for r in runs] == ["or:anthropic/claude-good", "or:openai/gpt-verifier"] * 2
    for run in runs:
        assert run["status"] == "finished" and run["phase"] == "done"
        assert run["steps"] == 3 and run["tool_calls"] == 2 and run["tool_errors"] == 0
        assert run["invalid"] is None
        v = verification(arena.conn, run["id"])
        assert v["status"] == "pass"
        assert v["verifier"] != run["model_id"]
    # Das Prüfmodell selbst wird vom Ersatzmodell geprüft.
    assert verification(arena.conn, runs[1]["id"])["verifier"] == "or:anthropic/claude-good"
    assert "Ersatzmodell" in verification(arena.conn, runs[1]["id"])["reason"]
    objects = arena.bw_objects()
    assert {"AREA:ZBENCH_AAA01", "IOBJ:ZBAAA01CU", "AREA:ZBENCH_AAA04", "IOBJ:ZBAAA04CU"} <= set(objects)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert batch["status"] == "done" and batch["runner_pid"] is None
    env = json.loads(db.one(arena.conn, "SELECT data FROM environments WHERE batch_id=?", (batch_id,))["data"])
    assert env["mcp_server"]["tool_count"] == 4 and env["mcp_server"]["server_name"] == "fake-bw"
    assert "env" not in env["mcp_server"] and "bw-geheim-123" not in json.dumps(env)


async def test_usage_cost_and_events(arena):
    batch_id, _ = await go(arena)
    run = runs_of(arena.conn, batch_id)[0]
    # Drei Schritte: 1000 + 2000 + 3000 Eingabe-Tokens, davon 0 + 800 + 1600 aus dem Cache.
    assert run["tokens_input"] == 6000 and run["tokens_cache_read"] == 2400 and run["tokens_output"] == 150
    assert run["tokens_reasoning"] == 30
    assert run["cost_usd"] == pytest.approx(0.03) and run["cost_source"] == "billed"
    assert run["last_requirement"] == "3 Aktivieren"
    events = db.rows(arena.conn, "SELECT * FROM run_events WHERE run_id=? ORDER BY id", (run["id"],))
    kinds = [(e["phase"], e["kind"]) for e in events]
    assert kinds.count(("task", "step")) == 3 and kinds.count(("task", "tool")) == 2
    first_tool = next(e for e in events if e["kind"] == "tool")
    # Ein bw_write bedient mehrere Anforderungen (Aktion + Objekttyp + Aktivieren).
    assert first_tool["requirement"] == "1 InfoArea | 2 InfoObjects | 3 Aktivieren"
    assert any(e["phase"] == "verify" for e in events)
    v = verification(arena.conn, run["id"])
    assert v["cost_usd"] == pytest.approx(0.02) and json.loads(v["points"])[1]["ok"] is True


async def test_placeholders_and_log_redaction(arena):
    batch_id, _ = await go(arena)
    run = runs_of(arena.conn, batch_id)[0]
    request = next(r for r in arena.platform.requests if r["model"] == "anthropic/claude-good")
    prompt = request["body"]["messages"][1]["content"]
    assert (
        "RUN=AAA01 AREA=ZBENCH_AAA01 PREFIX=ZB PARENT=ZBENCH_AI MODEL=anthropic/claude-good MCP=fake SYSTEM=TST"
        in prompt
    )
    log = Path(run["log_path"]).read_text(encoding="utf-8")
    assert "bw-geheim-123" not in log and "or-key" not in log
    entries = [json.loads(line) for line in log.splitlines()]
    assert entries[0]["type"] == "meta" and entries[-1]["type"] == "end"
    assert sum(e["type"] == "tool_result" for e in entries) == 2


async def test_verifier_gets_only_read_tools(arena):
    """Schreibversuch im Prüflauf: abgelehnt, Urteil ungültig, nichts im BW verändert."""
    store.save_settings(arena.conn, {"verify": {"model": "or:x/writer"}})
    batch_id, _ = await go(arena, models=["or:x/halfway"])
    run = runs_of(arena.conn, batch_id)[0]
    v = verification(arena.conn, run["id"])
    assert v["status"] == "invalid" and json.loads(v["write_attempts"]) == ["bw_write"]
    offered = [r for r in arena.platform.requests if r["model"] == "x/writer"][0]["body"]["tools"]
    assert sorted(t["function"]["name"] for t in offered) == ["bw_context", "bw_read", "bw_search"]
    # halfway legt nur die InfoArea an; der Schreibversuch des Prüfmodells hat das Merkmal nicht ergänzt.
    assert "IOBJ:ZBAAA01CU" not in arena.bw_objects()


async def test_failed_task_gets_fail_verdict(arena):
    batch_id, _ = await go(arena, models=["or:x/halfway"])
    run = runs_of(arena.conn, batch_id)[0]
    v = verification(arena.conn, run["id"])
    assert run["status"] == "finished" and v["status"] == "fail"
    assert [p["ok"] for p in json.loads(v["points"])] == [True, False]


async def test_run_without_tool_calls_is_not_verified(arena):
    batch_id, _ = await go(arena, models=["or:x/lazy"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "finished" and run["tool_calls"] == 0
    assert verification(arena.conn, run["id"])["status"] == "not_verified"


async def test_verifier_equals_tested_model_without_fallback(arena):
    store.save_settings(arena.conn, {"verify": {"model": "or:anthropic/claude-good", "fallback": ""}})
    batch_id, _ = await go(arena)
    v = verification(arena.conn, runs_of(arena.conn, batch_id)[0]["id"])
    assert v["status"] == "not_verified" and "Prüfmodell = Testmodell" in v["reason"]


async def test_timeout_is_a_model_result(arena):
    (arena.tmp / "tasks" / "mini" / "task.yaml").write_text(
        (arena.tmp / "tasks" / "mini" / "task.yaml").read_text().replace("zeitlimit_s: 30", "zeitlimit_s: 3")
    )
    batch_id, final = await go(arena, models=["or:x/slow"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "timeout" and run["invalid"] is None and final == "done"
    assert run["seconds"] < 8


async def test_step_limit(arena):
    store.save_settings(arena.conn, {"run": {"max_steps": 4}})
    batch_id, _ = await go(arena, models=["or:x/looper"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "step_limit" and run["steps"] == 4 and run["invalid"] is None


async def test_platform_retry_then_success(arena):
    batch_id, _ = await go(arena, models=["or:x/flaky"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "finished" and run["api_retries"] == 1 and run["invalid"] is None


@pytest.mark.parametrize(
    ("model", "reason"),
    [("or:x/broke", "Guthaben"), ("or:x/down", "Plattform gestört")],
)
async def test_platform_failure_makes_run_invalid(arena, model, reason):
    store.save_settings(arena.conn, {"run": {"api_retries": 0}})
    batch_id, final = await go(arena, models=[model])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "error" and reason in run["invalid"]
    assert final == "done"  # die Störung einer Plattform hält den Durchgang nicht an


async def test_context_overflow_counts_as_model_result(arena):
    batch_id, _ = await go(arena, models=["or:x/bigctx"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "error" and run["error_kind"] == "context" and run["invalid"] is None


async def test_unreadable_tool_calls_end_the_run(arena):
    batch_id, _ = await go(arena, models=["or:x/badjson"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["status"] == "error" and run["error_kind"] == "bad_tool_calls"
    assert run["tool_errors"] == 3 and "nicht lesbar" in run["invalid"]


async def test_multiple_tool_calls_in_one_step_run_in_order(arena):
    batch_id, _ = await go(arena, models=["or:x/multi"])
    run = runs_of(arena.conn, batch_id)[0]
    assert run["steps"] == 2 and run["tool_calls"] == 2
    # Der erste Aufruf im BW ist die Vorabprüfung der Eltern-InfoArea.
    assert [c["tool"] for c in arena.bw_calls()][:3] == ["bw_search", "bw_write", "bw_search"]
    second = [r for r in arena.platform.requests if r["model"] == "x/multi"][1]["body"]["messages"]
    assert [m["role"] for m in second][-3:] == ["assistant", "tool", "tool"]


async def test_thinking_levels_and_fallback_when_unsupported(arena):
    batch_id, _ = await go(arena, models=["or:x/nothink", "or:anthropic/claude-good"], thinking=["high"])
    by_model = {r["model_id"]: r for r in runs_of(arena.conn, batch_id)}
    sent = json.loads(by_model["or:anthropic/claude-good"]["thinking_sent"])
    assert sent == {"sent": {"reasoning": {"effort": "high"}}, "effective": True}
    rejected = json.loads(by_model["or:x/nothink"]["thinking_sent"])
    assert rejected == {"sent": None, "effective": False}
    assert by_model["or:x/nothink"]["status"] == "finished"


async def test_reasoning_details_are_passed_back(arena):
    await go(arena, models=["or:x/reasoner"])
    second = [r for r in arena.platform.requests if r["model"] == "x/reasoner"][1]["body"]["messages"]
    assistant = next(m for m in second if m["role"] == "assistant")
    assert assistant["reasoning_details"] == [{"type": "reasoning.encrypted", "data": "blob-0"}]


async def test_cost_limit_stops_further_runs(arena):
    batch_id, final = await go(arena, repeats=3, cost_limit=0.04)
    runs = runs_of(arena.conn, batch_id)
    assert final == "cancelled"
    assert [r["status"] for r in runs] == ["finished", "skipped", "skipped"]
    assert (
        "Kostenlimit"
        in db.one(arena.conn, "SELECT status_message FROM batches WHERE id=?", (batch_id,))["status_message"]
    )


async def test_preflight_bw_down(arena):
    arena.platform.bw_up = False
    batch_id, final = await go(arena)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert final == "error" and "nicht bereit" in batch["status_message"]
    assert [r["status"] for r in runs_of(arena.conn, batch_id)] == ["skipped"]
    assert not arena.platform.requests  # kein Modell wurde angefragt
    assert arena.platform.pings == bwcheck.PATIENT_ATTEMPTS  # erst nach mehreren Versuchen aufgegeben
    assert f"{bwcheck.PATIENT_ATTEMPTS} Versuche" in batch["status_message"]


async def test_single_failed_bw_ping_does_not_stop_batch(arena, capsys):
    """Ein einzelner Fehlversuch zwischen zwei Läufen hält den Durchgang nicht an (Durchgang AAN, 17.11.2026)."""
    arena.platform.bw_fail_pings = {3}  # 1 Vorabprüfung, 2 vor dem ersten Lauf, 3 vor dem zweiten
    batch_id, final = await go(arena, repeats=2)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert final == "done" and not batch["status_message"]
    assert [r["status"] for r in runs_of(arena.conn, batch_id)] == ["finished", "finished"]
    assert arena.platform.pings == 4  # der vierte Ping ist der zweite Versuch vor dem zweiten Lauf
    out = capsys.readouterr().out
    assert "antwortet nicht (Versuch 1 von" in out and "antwortet wieder" in out


async def test_bw_gone_between_runs_stops_batch_after_all_attempts(arena):
    """F-D9: Antwortet das BW auch nach allen Versuchen nicht, hält der Durchgang an; der Rest ist nachholbar."""
    arena.platform.bw_fail_pings = set(range(3, 50))
    batch_id, final = await go(arena, repeats=2)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert final == "error"
    assert "nicht mehr erreichbar" in batch["status_message"]
    assert f"{bwcheck.PATIENT_ATTEMPTS} Versuche" in batch["status_message"]
    assert [r["status"] for r in runs_of(arena.conn, batch_id)] == ["finished", "skipped"]
    assert arena.platform.pings == 2 + bwcheck.PATIENT_ATTEMPTS


async def test_preflight_parent_area_missing(arena):
    store.save_bw_system(
        arena.conn, {"id": "TST", "url": arena.platform.url, "parent_area": "ZGIBTSNICHT"}, create=False
    )
    batch_id, final = await go(arena)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert final == "error" and "Eltern-InfoArea ZGIBTSNICHT" in batch["status_message"]
    assert not arena.platform.requests


async def test_preflight_mcp_not_startable(arena, monkeypatch):
    monkeypatch.setenv("FAKE_MCP_FAIL_START", "1")
    # Der Server erbt nur die Umgebung aus seiner Definition: dort eintragen.
    text = json.loads(mcpclient_text(arena.conn))
    text["mcpServers"]["fake"]["env"]["FAKE_MCP_FAIL_START"] = "1"
    from aiarena4bw import mcpclient

    mcpclient.save_definition_text(arena.conn, json.dumps(text))
    batch_id, final = await go(arena)
    batch = db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))
    assert final == "error" and "MCP-Server" in batch["status_message"]
    assert "bw-geheim-123" not in batch["status_message"]


def mcpclient_text(conn):
    from aiarena4bw import mcpclient

    return mcpclient.definition_text(conn)


async def test_bw_outage_stops_batch_and_keeps_rest_retryable(arena):
    """REQ F-D9: Der MCP-Server verliert mitten im Lauf die Verbindung."""
    from aiarena4bw import mcpclient

    text = json.loads(mcpclient_text(arena.conn))
    text["mcpServers"]["fake"]["env"]["FAKE_MCP_DIE_ON"] = "bw_search"
    mcpclient.save_definition_text(arena.conn, json.dumps(text))
    batch_id, final = await go(arena, repeats=2)
    runs = runs_of(arena.conn, batch_id)
    assert final == "error"
    assert runs[0]["status"] == "error" and runs[0]["error_kind"] == "mcp" and "nicht erreichbar" in runs[0]["invalid"]
    assert runs[1]["status"] == "skipped"
    # Später nachholen: beide Läufe im selben Durchgang neu einplanen.
    text["mcpServers"]["fake"]["env"].pop("FAKE_MCP_DIE_ON")
    mcpclient.save_definition_text(arena.conn, json.dumps(text))
    new = control.retry_runs(arena.conn, [r["id"] for r in runs])
    assert new == ["AAA03", "AAA04"]
    # Das geplante Kostenlimit bleibt als Vorlage erhalten, auch wenn Wiederholungen das Limit anheben.
    limits = db.one(arena.conn, "SELECT cost_limit, cost_limit_planned FROM batches WHERE id=?", (batch_id,))
    assert limits["cost_limit_planned"] == 5.0 and limits["cost_limit"] >= 5.0
    assert await runner.run_batch(arena.conn, batch_id) == "done"
    runs = runs_of(arena.conn, batch_id)
    assert [r["status"] for r in runs] == ["error", "skipped", "finished", "finished"]
    assert runs[0]["invalid"] == "wiederholt als AAA03" and runs[2]["retry_of"] == runs[0]["id"]


async def test_cancel_during_run(arena):
    import asyncio

    batch_id = planning.plan_batch(arena.conn, arena.spec(models=["or:x/slow"], repeats=2))

    async def cancel_soon():
        await asyncio.sleep(1.0)
        control.request_cancel(db.connect(), batch_id)

    task = asyncio.create_task(cancel_soon())
    final = await runner.run_batch(arena.conn, batch_id)
    await task
    runs = runs_of(arena.conn, batch_id)
    assert final == "cancelled"
    assert [r["status"] for r in runs] == ["cancelled", "skipped"]
    assert "abgebrochen" in runs[0]["invalid"]
    assert verification(arena.conn, runs[0]["id"])["status"] == "not_verified"
    assert not db.rows(arena.conn, "SELECT 1 FROM runs WHERE status='running'")


async def test_only_one_batch_at_a_time(arena):
    import os

    first = planning.plan_batch(arena.conn, arena.spec())
    db.update(arena.conn, "batches", {"id": first}, status="running", runner_pid=os.getpid())
    second = planning.plan_batch(arena.conn, arena.spec())
    with pytest.raises(runner.RunnerError, match="läuft noch"):
        await runner.run_batch(arena.conn, second)


@pytest.mark.parametrize("model", ["ant:claude-good-1", "sap:anthropic--claude-good", "lms:local-good"])
async def test_every_platform_type_completes_a_run(arena, model):
    """Jeder Plattformtyp besteht denselben Fall gegen seinen Nachbau."""
    batch_id, final = await go(arena, models=[model])
    run = runs_of(arena.conn, batch_id)[0]
    assert final == "done" and run["status"] == "finished", run["error"]
    assert run["steps"] == 3 and run["tool_calls"] == 2
    assert verification(arena.conn, run["id"])["status"] == "pass"
    assert "AREA:ZBENCH_AAA01" in arena.bw_objects()
    if model.startswith("ant:"):
        # 200 neu + Cache je Schritt; Kosten aus der Preisliste berechnet.
        assert run["tokens_input"] == 200 * 3 + 800 + 800 + 1600 and run["tokens_cache_read"] == 2400
        assert run["cost_source"] == "computed" and run["cost_usd"] > 0
    elif model.startswith("sap:"):
        assert run["cost_usd"] is None and run["cost_source"] is None  # kein Preis, nie 0 $
    else:
        assert run["cost_usd"] == 0 and run["cost_source"] == "computed"  # ausdrücklich kostenfrei


async def test_reverify_keeps_run_and_counts_earlier_cost(arena):
    batch_id, _ = await go(arena)
    run = runs_of(arena.conn, batch_id)[0]
    await runner.reverify(arena.conn, batch_id, [run["id"]])
    v = verification(arena.conn, run["id"])
    assert v["attempts"] == 2 and v["earlier_cost"] == pytest.approx(0.02) and v["status"] == "pass"
    after = runs_of(arena.conn, batch_id)[0]
    assert after["seconds"] == run["seconds"] and after["steps"] == run["steps"]
    assert runner.batch_cost(arena.conn, batch_id) == pytest.approx(0.03 + 0.02 + 0.02)
    logs = sorted(
        p.name for p in runner.log_dir(db.one(arena.conn, "SELECT * FROM batches WHERE id=?", (batch_id,))).iterdir()
    )
    assert "AAA01_verify_1.jsonl" in logs and "AAA01_verify.jsonl" in logs
