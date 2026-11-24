"""Bausteine ohne Durchgang: Prüfurteil, Gültigkeit, Codes, Anbieter, Schwärzung, Aufgaben, Kosten."""

from __future__ import annotations

import base64
import json

import pytest

from aiarena4bw import bwcheck, db, mcpclient, store, tasks, vault, vendors
from aiarena4bw.agent import compute_cost
from aiarena4bw.platforms.anthropic_api import list_price, thinking_params
from aiarena4bw.platforms.base import Usage, classify_status, mentions_thinking, parse_arguments
from aiarena4bw.runs import codes, validity
from aiarena4bw.runs.verify import choose_verifier, parse_verdict

from .conftest import write_task

# --------------------------------------------------------------------------- Prüfurteil


def test_verdict_plain_lines():
    v = parse_verdict("1. OK – InfoArea existiert.\n2. FEHLER – Typ ist DEC statt CURR.\n\nVERDICT: FAIL")
    assert v.status == "fail"
    assert v.points == [
        {"nr": 1, "ok": True, "text": "InfoArea existiert."},
        {"nr": 2, "ok": False, "text": "Typ ist DEC statt CURR."},
    ]


def test_verdict_markdown_bold_and_result_on_next_line():
    text = "**1.** InfoArea `ZBENCH_AAA01`\n   **OK** – vorhanden\n\n**2.** Merkmal\n   ✅ aktiv, CHAR 10\n\n**VERDICT: PASS**"
    v = parse_verdict(text)
    assert v.status == "pass" and [p["ok"] for p in v.points] == [True, True]
    assert v.points[0]["text"].startswith("InfoArea ZBENCH_AAA01")


def test_verdict_table_and_symbols():
    text = "| Nr | Punkt | Ergebnis | Begründung |\n|---|---|---|---|\n| 1 | InfoArea | OK | existiert |\n| 2 | aDSO | ❌ | fehlt |\n\nVERDICT: FAIL"
    v = parse_verdict(text)
    assert [(p["nr"], p["ok"]) for p in v.points] == [(1, True), (2, False)]


def test_verdict_result_first_then_sentence():
    v = parse_verdict("1. **OK**. Die InfoArea existiert und ist aktiv.\n2. FEHLER: aDSO fehlt.\nVERDICT: FAIL")
    assert [p["text"] for p in v.points] == ["Die InfoArea existiert und ist aktiv.", "aDSO fehlt."]


def test_verdict_uses_last_occurrence_and_is_unclear_without_line():
    assert parse_verdict("Vorläufig VERDICT: FAIL … nach erneuter Prüfung\nVERDICT: PASS").status == "pass"
    assert parse_verdict("Alles sieht gut aus.").status == "unclear"
    assert parse_verdict(None).status == "unclear"


def test_verdict_heading_style_and_stops_at_verdict_line():
    text = "### 1. InfoArea\nOK, vorhanden.\n### 2) aDSO\nFEHLER: nicht aktiv\nVERDICT: FAIL\n3. OK – gehört nicht mehr dazu"
    v = parse_verdict(text)
    assert [(p["nr"], p["ok"]) for p in v.points][:2] == [(1, True), (2, False)]


def test_verifier_never_checks_itself_even_across_platforms():
    choice = choose_verifier(
        "openrouter:anthropic/claude-haiku-5.5", "anthropic:claude-haiku-5-5", "openrouter:anthropic/claude-sonnet-5.5"
    )
    assert choice.model_id == "openrouter:anthropic/claude-sonnet-5.5" and "Ersatzmodell" in choice.reason
    assert choose_verifier("or:a/x", "or:b/y", None).model_id == "or:b/y"
    assert choose_verifier("or:a/x", "or:a/x", "or:a/x").model_id is None
    assert choose_verifier("or:a/x", "", "").reason == "kein Prüfmodell eingestellt"


# --------------------------------------------------------------------------- Gültigkeit, Codes, Anbieter


@pytest.mark.parametrize(
    ("status", "kind", "error", "invalid"),
    [
        ("finished", None, None, False),
        ("timeout", None, "Zeitlimit von 900 s erreicht", False),
        ("step_limit", None, None, False),
        ("error", "context", "prompt is too long", False),
        ("cancelled", None, None, True),
        ("error", "credits", "requires more credits", True),
        ("error", "rate_limit", "429", True),
        ("error", "mcp", "Verbindung verloren", True),
        ("error", "bad_tool_calls", "Werkzeugaufrufe nicht lesbar", True),
        ("error", None, "upstream error from provider", True),  # ohne Einordnung: nur der Text
        ("mcp_missing", None, None, True),
        ("skipped", None, None, False),
    ],
)
def test_validity(status, kind, error, invalid):
    assert bool(validity.classify(status, kind, error)) is invalid


def test_error_classification_by_status_and_text():
    assert classify_status(402, "payment required").kind == "credits"
    assert classify_status(429, "Too many requests").kind == "rate_limit"
    assert classify_status(429, "insufficient credits").kind == "credits"
    assert classify_status(502, "Could not verify the available credits, retry shortly").kind == "unavailable"
    assert classify_status(404, "No endpoints found").kind == "model_not_found"
    assert classify_status(400, "'tools': array too long, maximum length 128").kind == "tool_limit"
    assert classify_status(400, "This model's maximum context length is 8192 tokens").kind == "context"
    assert classify_status(529, "Overloaded").retryable
    assert not classify_status(401, "bad key").retryable
    assert mentions_thinking(classify_status(400, "reasoning_effort is not supported"))
    assert not mentions_thinking(classify_status(400, "messages: field required"))


def test_tool_arguments():
    assert parse_arguments('{"a": 1}')[0] == {"a": 1}
    assert parse_arguments("")[0] == {}
    assert parse_arguments("{not json")[0] is None and "kein gültiges JSON" in parse_arguments("{not json")[2]
    assert parse_arguments("[1]")[0] is None


def test_codes():
    assert codes.next_code(set()) == "AAA"
    assert codes.next_code({"AAA", "AAB", "K"}) == "AAC"
    assert codes.run_code("AAC", 7) == "AAC07"
    with pytest.raises(codes.CodeError):
        codes.run_code("AAC", 100)
    assert codes.code_of("AAC07") == "AAC" and codes.code_of("T021") == "T"
    assert codes.number_of("AAC07") == 7 and codes.number_of("T021") == 0
    with pytest.raises(ValueError):
        codes.check_run("AAC7")


def test_vendors_and_same_model():
    assert vendors.split_model_id("openrouter:qwen/x:free") == ("openrouter", "qwen/x:free")
    assert vendors.vendor_of("openrouter:anthropic/claude-haiku-5.5") == "Anthropic"
    assert vendors.vendor_of("sapaicore:anthropic--claude-4.5-haiku") == "Anthropic"
    assert vendors.vendor_of("sapaicore:gemini-2.5-pro") == "Google"
    assert vendors.vendor_of("lms:irgendwas") == "unbekannt"
    assert vendors.same_model("openrouter:anthropic/claude-opus-4.8", "sapaicore:anthropic--claude-4.8-opus")
    assert vendors.same_model("anthropic:claude-haiku-5-5", "openrouter:anthropic/claude-haiku-5.5")
    assert not vendors.same_model("openrouter:anthropic/claude-haiku-5.5", "openrouter:anthropic/claude-sonnet-5.5")


# --------------------------------------------------------------------------- Geheimnisse


def test_redaction_of_known_values_and_patterns():
    redact = vault.Redactor(["s3cr3t-pass", "sk-or-12345678"], users=["DEVELOPER"])
    b64 = base64.b64encode(b"DEVELOPER:s3cr3t-pass").decode()
    text = f'curl -u DEVELOPER:s3cr3t-pass https://bw … Authorization: Basic {b64} … key sk-or-12345678 … "password": "anderes"'
    out = redact(text)
    assert "s3cr3t-pass" not in out and b64 not in out and "sk-or-12345678" not in out and "anderes" not in out
    assert redact("Schritt 3 von 5") == "Schritt 3 von 5"
    assert redact(None) is None


def test_secrets_fall_back_to_environment(secret):
    assert vault.get("platform/x/credentials") is None
    secret("platform/x/credentials", "aus-umgebung")
    assert vault.get("platform/x/credentials") == "aus-umgebung"
    vault.put("bw/T/password", "nur-im-speicher")  # Schlüsselbund ist in Tests abgeschaltet
    assert vault.has("bw/T/password")
    vault.delete("bw/T/password")
    assert not vault.has("bw/T/password")


# --------------------------------------------------------------------------- Aufgaben


def test_task_placeholders_and_requirements(tmp_path, conn):
    write_task(tmp_path / "tasks")
    task = tasks.get_task("mini")
    system = {"id": "A4H", "prefix": "ZB", "area_pattern": "ZBENCH_{RUN}", "parent_area": "ZBENCH_AI"}
    values = tasks.placeholder_values(run_code="AAA01", model="m", mcp_server="coBWeb-mcp", system=system)
    assert (
        tasks.fill("{AREA} {PREFIX}{RUN}CU unter {PARENT_AREA}, {UNBEKANNT}", values)
        == "ZBENCH_AAA01 ZBAAA01CU unter ZBENCH_AI, {UNBEKANNT}"
    )
    assert tasks.unknown_placeholders("{RUN} {FOO}") == ["FOO"]
    write = {"objects": [{"action": "create", "type": "AREA"}, {"action": "create", "type": "IOBJ"}], "activate": True}
    assert tasks.match_requirements(task.requirements, "bw_write", write) == [
        "1 InfoArea",
        "2 InfoObjects",
        "3 Aktivieren",
    ]
    assert tasks.match_requirements(task.requirements, "bw_write", {**write, "activate": False}) == [
        "1 InfoArea",
        "2 InfoObjects",
    ]
    assert (
        tasks.match_requirements(task.requirements, "bw_write", {"objects": [{"action": "delete", "type": "AREA"}]})
        == []
    )
    assert tasks.match_requirements(task.requirements, "anderer-mcp__bw_create_infoarea") == ["1 InfoArea"]
    assert tasks.match_requirements(task.requirements, "bw_search", {"query": "x"}) == []


def test_changed_task_needs_new_version_once_used(tmp_path, conn):
    write_task(tmp_path / "tasks")
    task = tasks.get_task("mini")
    tasks.sync_task(conn, task)
    (tmp_path / "tasks" / "mini" / "prompt.md").write_text("anderer Text {RUN}")
    tasks.sync_task(conn, tasks.get_task("mini"))  # noch unbenutzt: darf sich ändern
    batch = db.insert(conn, "batches", code="AAA", created=db.now(), status="done")
    db.insert(
        conn,
        "runs",
        batch_id=batch,
        position=1,
        repeat=1,
        run_code="AAA01",
        task_id="mini",
        task_version=1,
        model_id="or:x",
        status="finished",
    )
    (tmp_path / "tasks" / "mini" / "prompt.md").write_text("wieder anders {RUN}")
    with pytest.raises(tasks.TaskVersionError, match="Version"):
        tasks.sync_task(conn, tasks.get_task("mini"))
    assert tasks.stored_task(conn, "mini", 1)["prompt"] == "anderer Text {RUN}"


def test_draft_checks_and_save_roundtrip(tmp_path):
    draft = {
        "id": "neue-aufgabe",
        "title": "Test",
        "timeout_s": 600,
        "checkpoints": 3,
        "prompt": "Lege {PREFIX}{RUN}X in {AREA} an. {FALSCH}",
        "verify_prompt": "Prüfe.",
        "requirements": [{"name": "1 Objekt", "tools": ["create_adso"]}],
    }
    errors, hints = tasks.check_draft(draft)
    assert any("{FALSCH}" in e for e in errors) and any("VERDICT" in h for h in hints)
    draft["prompt"] = draft["prompt"].replace(" {FALSCH}", "")
    assert tasks.check_draft(draft)[0] == []
    tasks.save_task(tasks.draft_to_task(draft, 1), note="angelegt", folder=tmp_path / "tasks")
    loaded = tasks.get_task("neue-aufgabe", tmp_path / "tasks")
    assert loaded.title == "Test" and loaded.requirements == [{"name": "1 Objekt", "tools": ["create_adso"]}]
    assert loaded.history[-1]["notiz"] == "angelegt" and loaded.timeout_s == 600


# --------------------------------------------------------------------------- Kosten, Denkstufen


def test_cost_from_tokens_and_prices():
    usage = Usage(input_total=1_000_000, cache_read=600_000, cache_write=100_000, output=10_000)
    prices = {"price_in": 2.0, "price_out": 10.0, "price_cache_read": 0.2, "price_cache_write": 2.5}
    # 300.000 neu × 2 + 600.000 × 0,2 + 100.000 × 2,5 + 10.000 × 10, je Mio.
    assert compute_cost(usage, prices) == pytest.approx(0.6 + 0.12 + 0.25 + 0.1)
    assert compute_cost(usage, {"price_in": None, "price_out": 1.0}) is None
    assert compute_cost(usage, None) is None
    assert compute_cost(usage, {"price_in": 0.0, "price_out": 0.0}) == 0.0


def test_anthropic_thinking_parameters_by_model():
    assert thinking_params("claude-opus-5-5", "high", 16000) == (
        {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}},
        True,
    )
    assert thinking_params("claude-opus-5-5", "none", 16000) == ({}, False)  # lässt sich nicht abschalten
    assert thinking_params("claude-sonnet-5-5", "none", 16000) == ({"thinking": {"type": "between_tools"}}, True)
    assert thinking_params("claude-sonnet-4-6", "none", 16000) == ({"thinking": {"type": "disabled"}}, True)
    assert thinking_params("claude-haiku-4-5", "medium", 16000) == (
        {"thinking": {"type": "enabled", "budget_tokens": 6000}},
        True,
    )
    assert thinking_params("claude-haiku-4-5", "none", 16000) == ({}, True)
    assert thinking_params("claude-opus-5-5", "", 16000) == ({}, True)
    assert list_price("claude-haiku-5-5")["price_in"] == 0.10 and list_price("unbekannt")["price_in"] is None


# --------------------------------------------------------------------------- Einstellungen


def test_bw_system_validation(conn):
    base = {"id": "A4H", "url": "https://bw.example.com:44300", "parent_area": "ZBENCH_AI"}
    saved = store.save_bw_system(conn, {**base, "password": "geheim-1234"}, create=True)
    assert (
        saved["is_default"]
        and saved["password_set"]
        and saved["prefix"] == "ZB"
        and saved["area_pattern"] == "ZBENCH_{RUN}"
    )
    assert "geheim" not in json.dumps(db.rows(conn, "SELECT * FROM bw_systems"))
    with pytest.raises(store.StoreError, match="Präfix"):
        store.save_bw_system(conn, {**base, "prefix": "ZBX"}, create=False)
    with pytest.raises(store.StoreError, match="Präfix"):
        store.save_bw_system(conn, {**base, "prefix": "AB"}, create=False)
    with pytest.raises(store.StoreError, match="RUN"):
        store.save_bw_system(conn, {**base, "area_pattern": "ZBENCH"}, create=False)
    with pytest.raises(store.StoreError, match="URL"):
        store.save_bw_system(conn, {**base, "id": "B", "url": "bw.example.com"}, create=True)
    assert store.delete_bw_system(conn, "A4H") == "deleted" and not vault.has(vault.bw_password("A4H"))


def test_bw_system_with_batches_is_retired_not_deleted(conn):
    store.save_bw_system(conn, {"id": "A4H", "url": "https://x:1", "parent_area": "ZB"}, create=True)
    db.insert(conn, "batches", code="AAA", created=db.now(), status="done", bw_system="A4H")
    assert store.delete_bw_system(conn, "A4H") == "retired"
    assert store.get_bw_system(conn, "A4H")["retired"] and store.default_bw_system(conn) is None


def test_settings_defaults_and_validation(conn):
    assert store.get_settings(conn)["run"]["max_steps"] == 200
    saved = store.save_settings(conn, {"run": {"cost_limit": "12.5", "blocked_codes": "k, aab,AAA", "unbekannt": 1}})
    assert saved["run"]["cost_limit"] == 12.5 and saved["run"]["blocked_codes"] == ["AAA", "AAB", "K"]
    with pytest.raises(store.StoreError):
        store.save_settings(conn, {"run": {"thinking": "ultra"}})
    with pytest.raises(store.StoreError):
        store.save_settings(conn, {"run": {"blocked_codes": "AB"}})


def test_model_catalog_keeps_manual_prices_and_selection(conn):
    store.save_platform(conn, {"id": "or", "type": "openrouter"}, create=True)
    entry = {"model_id": "a/b", "name": "B", "price_in": 1.0, "price_out": 2.0, "supports_tools": True}
    assert store.upsert_catalog(conn, "or", [entry, {"model_id": "a/c", "name": "C"}]) == 2
    assert not store.get_model(conn, "or:a/b")["selected"]  # Vorauswahl ist bewusst leer
    store.update_model(conn, "or:a/b", {"price_in": "0,5", "selected": True, "name": "Mein B"})
    store.upsert_catalog(conn, "or", [{**entry, "price_in": 9.0}])
    model = store.get_model(conn, "or:a/b")
    assert model["price_in"] == 0.5 and model["selected"] and model["name"] == "Mein B" and model["in_catalog"]
    assert not store.get_model(conn, "or:a/c")["in_catalog"]  # nicht mehr im Katalog, bleibt aber erhalten
    store.set_selection(conn, "or", select_all=True)
    store.upsert_catalog(conn, "or", [entry, {"model_id": "a/neu", "name": "Neu"}])
    assert store.get_model(conn, "or:a/neu")["selected"]  # „alle“ gilt auch für künftige Modelle
    assert sorted(m["id"] for m in store.list_models(conn, selectable=True)) == ["or:a/b", "or:a/c", "or:a/neu"]
    store.save_platform(conn, {"id": "or", "active": False}, create=False)
    assert store.list_models(conn, selectable=True) == []


# --------------------------------------------------------------------------- MCP-Definition


def test_mcp_definition_errors_name_the_place():
    with pytest.raises(mcpclient.McpConfigError, match="Zeile 2"):
        mcpclient.parse_definition('{"mcpServers": {\n  "a": }')
    with pytest.raises(mcpclient.McpConfigError, match="mcpServers"):
        mcpclient.parse_definition('{"a": {"command": "x"}}')
    with pytest.raises(mcpclient.McpConfigError, match="Genau eines"):
        mcpclient.parse_definition('{"mcpServers": {"a": {"command": "x", "url": "http://y"}}}')
    with pytest.raises(mcpclient.McpConfigError, match="Unbekannter Platzhalter"):
        mcpclient.parse_definition('{"mcpServers": {"a": {"command": "x", "env": {"A": "${BW_FOO}"}}}}')
    servers = mcpclient.parse_definition(
        '{"mcpServers": {"a": {"url": "https://x/mcp", "headers": {"Authorization": "Bearer ${SECRET:tok}"}}}}'
    )
    assert list(servers) == ["a"]


def test_mcp_placeholders_are_filled_from_bw_system_and_keyring(conn, secret):
    secret(vault.bw_password("A4H"), "bw-pass-999")
    secret(vault.named("tok"), "token-abcdef")
    system = store.save_bw_system(
        conn,
        {
            "id": "A4H",
            "url": "https://bw:44300",
            "client": "100",
            "user": "DEV",
            "language": "EN",
            "parent_area": "ZBENCH_AI",
        },
        create=True,
    )
    entry = {
        "command": "node",
        "args": ["server.js", "--url=${BW_URL}"],
        "env": {
            "BW_PASSWORD": "${BW_PASSWORD}",
            "AREAS": "${BW_PARENT_AREA},${BW_AREA_GLOB}",
            "TOKEN": "${SECRET:tok}",
            "API_KEY": "klartext-key-1",
        },
    }
    resolved = mcpclient.resolve("srv", entry, system, {"COBWEB_ALLOW_WRITES": "false"})
    assert resolved.args == ["server.js", "--url=https://bw:44300"]
    assert resolved.env == {
        "BW_PASSWORD": "bw-pass-999",
        "AREAS": "ZBENCH_AI,ZBENCH_*",
        "TOKEN": "token-abcdef",
        "API_KEY": "klartext-key-1",
        "COBWEB_ALLOW_WRITES": "false",
    }
    assert {"bw-pass-999", "token-abcdef", "klartext-key-1"} <= set(resolved.secrets)
    assert resolved.public() == {
        "transport": "stdio",
        "command": "node",
        "args": ["server.js", "--url=https://bw:44300"],
    }
    assert mcpclient.plaintext_secrets(entry) == ["env.API_KEY"]
    with pytest.raises(mcpclient.McpConfigError, match="nicht im Schlüsselbund"):
        mcpclient.resolve("srv", {"command": "x", "env": {"T": "${SECRET:fehlt}"}}, system)
    with pytest.raises(mcpclient.McpConfigError, match="braucht ein BW-System"):
        mcpclient.resolve("srv", entry, None)


def test_tool_classification_prefers_override_then_hint_then_name():
    tool = lambda name, hint=None: mcpclient.Tool(name, "", {}, hint)  # noqa: E731
    assert mcpclient.classify(tool("bw_search", True)) == "read"
    assert mcpclient.classify(tool("bw_system", False)) == "write"
    assert mcpclient.classify(tool("bw_get_adso")) == "read"
    assert mcpclient.classify(tool("bw_create_adso")) == "write"
    assert mcpclient.classify(tool("bw_activate")) == "write"
    assert mcpclient.classify(tool("bw_search", True), {"bw_search": "write"}) == "write"
    assert mcpclient.classify(tool("bw_system", False), {"bw_system": "read"}) == "read"


def test_default_server_is_seeded_once_and_needs_path(conn):
    mcpclient.seed_default(conn)
    server = mcpclient.get_server(conn, "coBWeb-mcp")
    assert server["is_default"] and server["needs_path"] and server["verify_env"] == {"COBWEB_ALLOW_WRITES": "false"}
    with pytest.raises(mcpclient.McpConfigError, match="Platzhalter-Pfad"):
        mcpclient.resolve_server(conn, "coBWeb-mcp", None)
    mcpclient.save_definition_text(conn, '{"mcpServers": {}}')
    mcpclient.seed_default(conn)  # der Nutzer hat ihn entfernt: nicht wieder eintragen
    assert mcpclient.list_servers(conn) == []


# --------------------------------------------------------------------------- BW-Erreichbarkeit


def test_probe_gives_the_answer_more_time_than_the_connection(platform):
    platform.ping_delay_s = 0.4
    slow = bwcheck.probe(platform.url, timeout_s=0.1)
    assert slow.state == bwcheck.PARTLY and "antwortet nicht" in slow.detail
    assert bwcheck.probe(platform.url, timeout_s=0.1, response_timeout_s=5).state == bwcheck.OK


def test_patient_probe_retries_and_reports(platform):
    platform.bw_fail_pings = {1, 2}
    seen = []
    status = bwcheck.probe_patient(platform.url, lambda attempt, of, s: seen.append((attempt, of, s.state)))
    assert status.state == bwcheck.OK and platform.pings == 3
    assert seen == [(1, bwcheck.PATIENT_ATTEMPTS, bwcheck.PARTLY), (2, bwcheck.PATIENT_ATTEMPTS, bwcheck.PARTLY)]


def test_patient_probe_gives_up_after_all_attempts_and_says_so(platform):
    platform.bw_up = False
    status = bwcheck.probe_patient(platform.url)
    assert status.state == bwcheck.PARTLY and platform.pings == bwcheck.PATIENT_ATTEMPTS
    assert "HTTP 503" in status.detail and f"{bwcheck.PATIENT_ATTEMPTS} Versuche" in status.detail


def test_patient_probe_does_not_retry_an_unknown_name():
    status = bwcheck.probe_patient("https://gibt-es-nicht.invalid:44300")
    assert status.state == bwcheck.DOWN and "nicht auflösbar" in status.detail and "Versuche" not in status.detail


def test_monitor_needs_two_failures_in_a_row_before_ready_turns_not_ready(platform):
    monitor = bwcheck.Monitor(lambda: [{"id": "TST", "url": platform.url}], start=False)
    state = lambda: monitor.get("TST").state  # noqa: E731
    monitor.check_all()
    assert state() == bwcheck.OK
    platform.bw_fail_pings = {2}
    monitor.check_all()  # ein Fehlversuch: der Stand bleibt
    assert state() == bwcheck.OK
    monitor.check_all()  # wieder bereit: der Zähler beginnt neu
    platform.bw_up = False
    monitor.check_all()
    assert state() == bwcheck.OK
    monitor.check_all()  # zweiter Fehlversuch in Folge
    assert state() == bwcheck.PARTLY
    platform.bw_up = True
    monitor.check_all()
    assert state() == bwcheck.OK


def test_monitor_shows_a_system_that_was_never_ready_at_once(platform):
    platform.bw_up = False
    monitor = bwcheck.Monitor(lambda: [{"id": "TST", "url": platform.url}], start=False)
    monitor.check_all()
    assert monitor.get("TST").state == bwcheck.PARTLY


def test_check_on_request_applies_at_once(platform):
    monitor = bwcheck.Monitor(lambda: [{"id": "TST", "url": platform.url}], start=False)
    monitor.check_all()
    platform.bw_up = False
    assert monitor.check_now({"id": "TST", "url": platform.url}).state == bwcheck.PARTLY
    assert monitor.get("TST").state == bwcheck.PARTLY
    monitor.check_all()  # bleibt nicht bereit, statt wieder einen Fehlversuch zu verzeihen
    assert monitor.get("TST").state == bwcheck.PARTLY


# --------------------------------------------------------------------------- Schema


def test_migration_keeps_planned_cost_limit_only_where_known(tmp_path):
    """Schema 2: Durchgänge mit Wiederholungen haben ein angehobenes Limit; ihr geplanter Wert bleibt leer."""
    import sqlite3

    path = tmp_path / "alt.db"
    old = sqlite3.connect(path, isolation_level=None)
    for statement in db._split(db.MIGRATIONS[0]):
        old.execute(statement)
    old.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    old.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    for batch_id, code, limit in ((1, "AAA", 50.0), (2, "AAB", 57.19)):
        old.execute(
            "INSERT INTO batches(id, code, created, status, cost_limit) VALUES (?,?,?,?,?)",
            (batch_id, code, db.now(), "done", limit),
        )
        for number, retry_of in ((1, None), (2, 3 if batch_id == 2 else None)):
            old.execute(
                "INSERT INTO runs(id, batch_id, position, repeat, run_code, task_id, task_version, model_id, "
                "status, retry_of) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    batch_id * 2 + number,
                    batch_id,
                    number,
                    1,
                    f"{code}0{number}",
                    "mini",
                    1,
                    "or:x",
                    "finished",
                    retry_of,
                ),
            )
    old.close()
    conn = db.connect(path)
    assert db.schema_version(conn) == db.SCHEMA_VERSION
    assert db.rows(conn, "SELECT code, cost_limit, cost_limit_planned FROM batches ORDER BY id") == [
        {"code": "AAA", "cost_limit": 50.0, "cost_limit_planned": 50.0},
        {"code": "AAB", "cost_limit": 57.19, "cost_limit_planned": None},
    ]
    assert list(tmp_path.glob("alt.db.schema1-*.bak"))  # Sicherung vor der Schemaänderung
    conn.close()


# --------------------------------------------------------------------------- Sicherheit des MCP-Servers


def test_default_cobweb_definition_needs_no_safety_note():
    assert mcpclient.safety(mcpclient.DEFAULT_DEFINITION, mcpclient.DEFAULT_VERIFY_ENV) == []


def test_safety_names_what_a_cobweb_server_may_do_too_much():
    def notes(env: dict, verify_env: dict | None = None) -> str:
        return " | ".join(mcpclient.safety({"command": "node", "args": ["/x/stdio.js"], "env": env}, verify_env))

    writes = {"COBWEB_ALLOW_WRITES": "true"}
    wide = notes(writes, {"COBWEB_ALLOW_WRITES": "false"})
    assert "jeder InfoArea" in wide and "bw_transport" in wide and "Prüfmodell" not in wide
    assert "jeder InfoArea" in notes({**writes, "COBWEB_ALLOWED_INFOAREAS": "*"})
    narrow = {**writes, "COBWEB_ALLOWED_INFOAREAS": "ZBENCH*", "COBWEB_TOOLS": mcpclient.COBWEB_TOOLS}
    assert notes(narrow, {"COBWEB_ALLOW_WRITES": "false"}) == ""
    assert "Prüfmodell" in notes(narrow)  # ohne abweichende Umgebung schreibt auch die Prüfung
    assert "Z*" in notes({**narrow, "COBWEB_ALLOWED_PACKAGES": "$TMP,Z*"}, {"COBWEB_ALLOW_WRITES": "false"})
    assert "Geschäftsdaten" in notes({"COBWEB_PROFILE": "full", "COBWEB_ALLOW_DATA": "yes"})
    # Ohne Schreibrecht ist bw_transport harmlos; ein Server ohne COBWEB_-Variablen ist nicht prüfbar.
    assert notes({"COBWEB_PROFILE": "modeling"}) == ""
    other = mcpclient.safety({"command": "npx", "args": ["some-bw-server"], "env": {}})
    assert len(other) == 1 and "nicht prüfen" in other[0]
