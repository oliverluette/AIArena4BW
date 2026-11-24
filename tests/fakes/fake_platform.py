"""Nachgebaute Plattform für Tests: ein lokaler HTTP-Server, der die vier API-Formate spricht.

  OpenAI-kompatibel  GET /v1/models, POST /v1/chat/completions
  OpenRouter         GET /api/v1/models, GET /api/v1/key, POST /api/v1/chat/completions
  Anthropic          GET /v1/models (mit Kopf anthropic-version), POST /v1/messages
  SAP AI Core        POST /oauth/token, GET /v2/lm/deployments, GET /v2/lm/scenarios/…/models,
                     POST /deploy/v2/completion
  BW-Ping            GET /sap/public/ping

Das Verhalten folgt dem Modellnamen (siehe SCRIPTS). Der Schritt eines Laufs ergibt sich aus der
Zahl der Werkzeugergebnisse im Verlauf – so ist der Nachbau zustandslos.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _values(prompt: str) -> dict[str, str]:
    return dict(re.findall(r"\b(RUN|AREA|PREFIX|PARENT|MODEL|MCP|SYSTEM)=(\S+)", prompt))


def script(model: str, step: int, prompt: str, last_result: str) -> dict[str, Any]:
    """Antwort des Modells für einen Schritt: {"calls": [(name, args)], "text": str}."""
    v = _values(prompt)
    run, area, prefix = v.get("RUN", "AAA01"), v.get("AREA", "ZBENCH_AAA01"), v.get("PREFIX", "ZB")
    create = (
        "bw_write",
        {
            "objects": [
                {"action": "create", "type": "AREA", "name": area, "spec": {"description": f"Lauf {run}"}},
                {"action": "create", "type": "IOBJ", "name": f"{prefix}{run}CU", "spec": {"info_area": area}},
            ],
            "activate": True,
        },
    )
    search = ("bw_search", {"query": f"{prefix}{run}*"})
    if "Prüfe" in prompt:  # Prüfauftrag: lesen und urteilen; "writer" versucht vorher zu schreiben
        if step == 0:
            return {"calls": [create] if "writer" in model else [search], "text": ""}
        if "writer" in model and step == 1:
            return {"calls": [search], "text": ""}
        ok = "IOBJ" in last_result
        return {
            "calls": [],
            "text": f"1. OK – InfoArea {area} existiert.\n2. {'OK' if ok else 'FEHLER'} – Merkmal "
            f"{prefix}{run}CU {'ist aktiv' if ok else 'fehlt'}.\n\nVERDICT: {'PASS' if ok else 'FAIL'}",
        }
    if "lazy" in model:
        return {"calls": [], "text": "Ich habe nichts getan."}
    if "looper" in model or "slow" in model:
        return {"calls": [search], "text": ""}
    if "badjson" in model:
        return {"calls": [("bw_write", "{not json")], "text": ""}
    if "multi" in model:
        if step == 0:
            return {"calls": [create, search], "text": "Ich lege an und prüfe."}
        return {"calls": [], "text": f"Fertig: {area} und {prefix}{run}CU sind aktiv."}
    if "halfway" in model:  # legt nur die InfoArea an
        if step == 0:
            only = {"objects": [create[1]["objects"][0]], "activate": True}
            return {"calls": [("bw_write", only)], "text": ""}
        return {"calls": [], "text": "Fertig."}
    # Standard ("good", "flaky", "nothink", …): anlegen, prüfen, antworten
    if step == 0:
        return {"calls": [create], "text": "Ich lege die Objekte an."}
    if step == 1:
        return {"calls": [search], "text": ""}
    return {"calls": [], "text": f"Fertig: {area} und {prefix}{run}CU sind aktiv."}


class FakePlatform:
    """Startet den Server in einem Thread. `requests` enthält alle Modellanfragen."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.counters: dict[str, int] = {}
        self.bw_up = True
        self.pings = 0  # Zahl der BW-Pings bisher
        self.bw_fail_pings: set[int] = set()  # diese Pings (gezählt ab 1) beantwortet das BW mit 503
        self.ping_delay_s = 0.0  # so lange lässt das BW jeden Ping warten
        self.delay_s = 0.0
        platform = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # still
                return

            def _send(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    return json.loads(raw) if raw else {}
                except ValueError:
                    return {}

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?")[0]
                if path == "/sap/public/ping":
                    platform.pings += 1
                    if platform.ping_delay_s:
                        time.sleep(platform.ping_delay_s)
                    up = platform.bw_up and platform.pings not in platform.bw_fail_pings
                    return self._send(200 if up else 503, b"Server reached.")
                if path == "/v2/lm/deployments":
                    return self._send(
                        200,
                        {"resources": [{"id": "d1", "deploymentUrl": f"{platform.url}/deploy", "status": "RUNNING"}]},
                    )
                if path == "/v2/lm/scenarios/foundation-models/models":
                    return self._send(
                        200,
                        {
                            "resources": [
                                {
                                    "model": "anthropic--claude-good",
                                    "versions": [
                                        {
                                            "name": "1",
                                            "isLatest": True,
                                            "capabilities": ["text-generation"],
                                            "contextLength": 200000,
                                        }
                                    ],
                                },
                                {
                                    "model": "text-embedding-3",
                                    "versions": [{"name": "1", "isLatest": True, "capabilities": ["embeddings"]}],
                                },
                            ]
                        },
                    )
                if path == "/api/v1/key":
                    if self.headers.get("Authorization") != "Bearer or-key":
                        return self._send(401, {"error": {"message": "No auth credentials found", "code": 401}})
                    return self._send(200, {"data": {"label": "test", "limit_remaining": 12.5}})
                if path == "/api/v1/models":
                    return self._send(
                        200,
                        {
                            "data": [
                                {
                                    "id": "anthropic/claude-good",
                                    "name": "Anthropic: Claude Good",
                                    "created": 1760000000,
                                    "context_length": 200000,
                                    "pricing": {
                                        "prompt": "0.000001",
                                        "completion": "0.000005",
                                        "input_cache_read": "0.0000001",
                                    },
                                    "supported_parameters": ["tools", "reasoning"],
                                },
                                {
                                    "id": "openai/gpt-verifier",
                                    "name": "OpenAI: GPT Verifier",
                                    "created": 1750000000,
                                    "context_length": 128000,
                                    "pricing": {"prompt": "0.000002", "completion": "0.000008"},
                                    "supported_parameters": ["tools"],
                                },
                                {"id": "some/embedder", "name": "Embedder", "pricing": {}, "supported_parameters": []},
                                {"id": "openrouter/auto", "name": "Auto Router", "supported_parameters": ["tools"]},
                            ]
                        },
                    )
                if path == "/v1/models" and self.headers.get("anthropic-version"):
                    if "ant-key" not in (self.headers.get("x-api-key"), (self.headers.get("Authorization") or "")[7:]):
                        return self._send(
                            401,
                            {
                                "type": "error",
                                "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                            },
                        )
                    return self._send(
                        200,
                        {
                            "data": [
                                {
                                    "type": "model",
                                    "id": "claude-haiku-5-5",
                                    "display_name": "Claude Haiku 5.5",
                                    "created_at": "2026-09-01T00:00:00Z",
                                    "max_input_tokens": 1000000,
                                },
                                {
                                    "type": "model",
                                    "id": "claude-good-1",
                                    "display_name": "Claude Good",
                                    "created_at": "2026-01-01T00:00:00Z",
                                },
                            ],
                            "has_more": False,
                            "first_id": "claude-haiku-5-5",
                            "last_id": "claude-good-1",
                        },
                    )
                if path == "/v1/models":
                    return self._send(200, {"data": [{"id": "local-good"}, {"id": "nomic-embed-text"}]})
                return self._send(404, {"error": {"message": f"not found: {path}"}})

            def do_POST(self) -> None:  # noqa: N802
                path = self.path.split("?")[0]
                body = self._body()
                if path == "/oauth/token":
                    return self._send(200, {"access_token": "sap-token", "expires_in": 3600})
                if platform.delay_s:
                    time.sleep(platform.delay_s)
                if path in ("/v1/chat/completions", "/api/v1/chat/completions"):
                    kind = "openrouter" if path.startswith("/api") else "openai"
                    return platform._openai(self, body, kind)
                if path == "/deploy/v2/completion":
                    return platform._sap(self, body)
                if path == "/v1/messages":
                    return platform._anthropic(self, body)
                return self._send(404, {"error": {"message": f"not found: {path}"}})

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request: Any, client_address: Any) -> None:  # abgebrochene Anfragen sind gewollt
                return

        self._server = QuietServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ------------------------------------------------------------------ Fehlerfälle

    def _failure(self, model: str, body: dict[str, Any]) -> tuple[int, str] | None:
        count = self.counters[model] = self.counters.get(model, 0) + 1
        if "flaky" in model and count <= 1:
            return 429, "Rate limit exceeded, too many requests"
        if "broke" in model:
            return 402, "This request requires more credits"
        if "down" in model:
            return 503, "Service unavailable"
        if "missing" in model:
            return 404, "No endpoints found for this model"
        if "bigctx" in model:
            return 400, "This model's maximum context length is 1000 tokens, prompt is too long"
        if "nothink" in model and (
            body.get("reasoning") or body.get("reasoning_effort") or body.get("thinking") or body.get("output_config")
            or (body.get("config", {}).get("modules", {}).get("prompt_templating", {}).get("model", {}).get("params", {}).get("reasoning_effort"))
        ):  # fmt: skip
            return 400, "reasoning_effort is not supported for this model"
        if "slow" in model:
            time.sleep(1.5)
        return None

    # ------------------------------------------------------------------ OpenAI-Format

    def _openai_reply(self, model: str, messages: list[dict[str, Any]], kind: str) -> dict[str, Any]:
        step = sum(1 for m in messages if m.get("role") == "tool")
        prompt = next((str(m.get("content")) for m in messages if m.get("role") == "user"), "")
        last = next((str(m.get("content")) for m in reversed(messages) if m.get("role") == "tool"), "")
        result = script(model, step, prompt, last)
        message: dict[str, Any] = {"role": "assistant", "content": result["text"] or None}
        if result["calls"]:
            message["tool_calls"] = [
                {
                    "id": f"call_{step}_{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)},
                }
                for i, (name, args) in enumerate(result["calls"])
            ]
        if "reasoner" in model:
            message["reasoning_details"] = [{"type": "reasoning.encrypted", "data": f"blob-{step}"}]
        usage: dict[str, Any] = {
            "prompt_tokens": 1000 * (step + 1),
            "completion_tokens": 50,
            "total_tokens": 1000 * (step + 1) + 50,
            "prompt_tokens_details": {"cached_tokens": 800 * step},
            "completion_tokens_details": {"reasoning_tokens": 10},
        }
        if kind == "openrouter":
            usage["cost"] = 0.01
        return {
            "id": f"gen-{step}",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if result["calls"] else "stop"}],
            "usage": usage,
        }

    def _openai(self, handler: Any, body: dict[str, Any], kind: str) -> None:
        model = str(body.get("model") or "")
        self.requests.append({"kind": kind, "model": model, "body": body, "headers": dict(handler.headers)})
        failure = self._failure(model, body)
        if failure:
            return handler._send(failure[0], {"error": {"message": failure[1], "code": failure[0]}})
        handler._send(200, self._openai_reply(model, body.get("messages") or [], kind))

    def _sap(self, handler: Any, body: dict[str, Any]) -> None:
        module = body.get("config", {}).get("modules", {}).get("prompt_templating", {})
        model = str(module.get("model", {}).get("name") or "")
        self.requests.append({"kind": "sapaicore", "model": model, "body": body, "headers": dict(handler.headers)})
        if handler.headers.get("Authorization") != "Bearer sap-token" or not handler.headers.get("AI-Resource-Group"):
            return handler._send(401, {"error": {"message": "unauthorized"}})
        failure = self._failure(model, body)
        if failure:
            return handler._send(failure[0], {"error": {"message": failure[1], "code": failure[0]}})
        messages = (body.get("messages_history") or []) + (module.get("prompt", {}).get("template") or [])
        handler._send(200, {"request_id": "r1", "final_result": self._openai_reply(model, messages, "sapaicore")})

    # ------------------------------------------------------------------ Anthropic-Format

    def _anthropic(self, handler: Any, body: dict[str, Any]) -> None:
        model = str(body.get("model") or "")
        self.requests.append({"kind": "anthropic", "model": model, "body": body, "headers": dict(handler.headers)})
        if "ant-key" not in (handler.headers.get("x-api-key"), (handler.headers.get("Authorization") or "")[7:]):
            return handler._send(
                401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
            )
        failure = self._failure(model, body)
        if failure:
            kind = {429: "rate_limit_error", 400: "invalid_request_error", 404: "not_found_error"}.get(
                failure[0], "api_error"
            )
            return handler._send(failure[0], {"type": "error", "error": {"type": kind, "message": failure[1]}})
        messages = body.get("messages") or []
        step, last, prompt = 0, "", ""
        for message in messages:
            content = message.get("content")
            if message.get("role") == "user" and isinstance(content, str) and not prompt:
                prompt = content
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        step += 1
                        inner = block.get("content")
                        last = inner if isinstance(inner, str) else json.dumps(inner)
        result = script(model, step, prompt, last)
        content: list[dict[str, Any]] = []
        if body.get("thinking", {}).get("type") in ("adaptive", "enabled"):
            content.append({"type": "thinking", "thinking": "", "signature": f"sig-{step}"})
        if result["text"]:
            content.append({"type": "text", "text": result["text"]})
        for i, (name, args) in enumerate(result["calls"]):
            content.append({"type": "tool_use", "id": f"toolu_{step}_{i}", "name": name, "input": args})
        handler._send(
            200,
            {
                "id": f"msg_{step}",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": content,
                "stop_reason": "tool_use" if result["calls"] else "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 200,
                    "cache_read_input_tokens": 800 * step,
                    "cache_creation_input_tokens": 800 if step == 0 else 0,
                    "output_tokens": 50,
                },
            },
        )
