"""Eingerichtete Arena für Tests und für den Oberflächentest: BW-System TST, MCP-Server fake,
vier Plattformen gegen die nachgebaute Plattform, Modelle, Aufgabe mini."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from aiarena4bw import mcpclient, store, vault

FAKE_MCP = Path(__file__).parent / "fake_mcp.py"

TASK_YAML = """id: mini
version: 1
titel: InfoArea und Merkmal
zeitlimit_s: 30
pruefpunkte: 2
anforderungen:
- name: 1 InfoArea
  werkzeuge: [create_infoarea]
- name: 2 InfoObjects
  werkzeuge: [create_infoobject]
- name: 3 Aktivieren
  werkzeuge: [activate]
"""
TASK_PROMPT = (
    "RUN={RUN} AREA={AREA} PREFIX={PREFIX} PARENT={PARENT_AREA} MODEL={MODEL} MCP={MCP} SYSTEM={SYSTEM}\n"
    "Lege die InfoArea und das Merkmal an."
)
TASK_VERIFY = (
    "RUN={RUN} AREA={AREA} PREFIX={PREFIX}\nPrüfe InfoArea und Merkmal. Letzte Zeile: VERDICT: PASS oder FAIL."
)


def write_task(folder: Path, task_id: str = "mini", yaml_text: str = TASK_YAML) -> None:
    target = folder / task_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "task.yaml").write_text(yaml_text.replace("id: mini", f"id: {task_id}"), encoding="utf-8")
    (target / "prompt.md").write_text(TASK_PROMPT, encoding="utf-8")
    (target / "verify.md").write_text(TASK_VERIFY, encoding="utf-8")


MODELS = [
    # (Plattform, Modell-ID, Preis ein, Preis aus)
    ("or", "anthropic/claude-good", None, None),
    ("or", "openai/gpt-verifier", None, None),
    ("or", "x/writer", None, None),
    ("or", "x/lazy", None, None),
    ("or", "x/flaky", None, None),
    ("or", "x/broke", None, None),
    ("or", "x/down", None, None),
    ("or", "x/looper", None, None),
    ("or", "x/slow", None, None),
    ("or", "x/badjson", None, None),
    ("or", "x/multi", None, None),
    ("or", "x/halfway", None, None),
    ("or", "x/bigctx", None, None),
    ("or", "x/nothink", None, None),
    ("or", "x/reasoner", None, None),
    ("ant", "claude-good-1", 1.0, 5.0),
    ("ant", "claude-verifier-1", 1.0, 5.0),
    ("sap", "anthropic--claude-good", None, None),
    ("lms", "local-good", 0.0, 0.0),
]


def seed(conn, platform_url: str, state: Path, tasks_dir: Path, secret: Callable[[str, str], None]) -> None:
    store.accept_notice(conn)
    secret(vault.bw_password("TST"), "bw-geheim-123")
    store.save_bw_system(
        conn,
        {
            "id": "TST",
            "url": platform_url,
            "client": "100",
            "user": "DEVELOPER",
            "language": "DE",
            "parent_area": "ZBENCH_AI",
        },
        create=True,
    )
    definition = {
        "mcpServers": {
            "fake": {
                "command": sys.executable,
                "args": [str(FAKE_MCP)],
                "env": {
                    "BW_URL": "${BW_URL}",
                    "BW_USER": "${BW_USER}",
                    "BW_PASSWORD": "${BW_PASSWORD}",
                    "FAKE_MCP_STATE": str(state),
                },
            }
        }
    }
    mcpclient.save_definition_text(conn, json.dumps(definition))
    mcpclient.save_server_options(conn, "fake", verify_env={"COBWEB_ALLOW_WRITES": "false"})
    secret(vault.platform_key("or"), "or-key")
    secret(vault.platform_key("ant"), "ant-key")
    secret(
        vault.platform_key("sap"),
        json.dumps(
            {
                "clientid": "cid",
                "clientsecret": "sap-secret-xyz",
                "url": platform_url,
                "serviceurls": {"AI_API_URL": platform_url},
            }
        ),
    )
    store.save_platform(conn, {"id": "or", "type": "openrouter", "base_url": platform_url + "/api/v1"}, create=True)
    store.save_platform(conn, {"id": "ant", "type": "anthropic", "base_url": platform_url}, create=True)
    store.save_platform(conn, {"id": "sap", "type": "sapaicore", "base_url": platform_url}, create=True)
    store.save_platform(conn, {"id": "lms", "type": "openai", "base_url": platform_url + "/v1"}, create=True)
    for platform_id, model_id, price_in, price_out in MODELS:
        store.add_manual_model(
            conn, platform_id, model_id, "Claude Good" if model_id == "anthropic/claude-good" else ""
        )
        if price_in is not None:
            store.update_model(conn, f"{platform_id}:{model_id}", {"price_in": price_in, "price_out": price_out})
    store.save_settings(
        conn,
        {
            "verify": {"model": "or:openai/gpt-verifier", "fallback": "or:anthropic/claude-good", "timeout_s": 30},
            "run": {"api_retries": 2},
        },
    )
    write_task(tasks_dir)
