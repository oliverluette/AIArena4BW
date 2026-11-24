"""Adapter für OpenAI-kompatible Chat-Completions: LM Studio, Ollama, vLLM, … und – mit
Erweiterungen – OpenRouter.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .. import vendors
from .base import (
    Adapter,
    PlatformError,
    Reply,
    Request,
    ToolCall,
    Turn,
    Usage,
    classify_status,
    mentions_thinking,
    parse_arguments,
    retry_after_seconds,
)

_STOP = {"stop": "end", "tool_calls": "tool", "function_call": "tool", "length": "length",
         "content_filter": "refusal"}  # fmt: skip


class OpenAICompatAdapter(Adapter):
    type = "openai"

    def __init__(
        self, platform: dict[str, Any], credentials: str | None, transport: httpx.AsyncBaseTransport | None = None
    ):
        super().__init__(platform, credentials)
        self._client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(600.0, connect=15.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ HTTP
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.credentials:
            headers["Authorization"] = f"Bearer {self.credentials}"
        return headers

    async def _send(
        self, method: str, path: str, *, body: dict | None = None, timeout_s: float | None = None
    ) -> dict[str, Any]:
        url = self.base_url + path
        try:
            response = await self._client.request(
                method, url, headers=self._headers(), json=body,
                timeout=httpx.Timeout(timeout_s, connect=15.0) if timeout_s else httpx.USE_CLIENT_DEFAULT,
            )  # fmt: skip
        except httpx.TimeoutException:
            raise PlatformError("network", f"Keine Antwort von {self.base_url} (Zeitüberschreitung).") from None
        except httpx.HTTPError as err:
            raise PlatformError("network", f"{self.base_url} nicht erreichbar: {err}") from None
        text = response.text
        if response.status_code >= 400:
            raise classify_status(
                response.status_code, _error_text(text), retry_after_seconds(response.headers.get("retry-after"))
            )
        try:
            data = response.json()
        except ValueError:
            raise PlatformError(
                "unavailable", f"Antwort ist kein JSON: {text[:200]}", status=response.status_code
            ) from None
        # Manche Plattformen melden Fehler mit Status 200 im Rumpf (OpenRouter: Fehler des Hosters).
        if isinstance(data, dict) and data.get("error") and not data.get("choices"):
            err = data["error"]
            code = err.get("code") if isinstance(err, dict) else None
            raise classify_status(code if isinstance(code, int) else 502, _error_text(json.dumps(data)))
        return data

    # ------------------------------------------------------------------ Katalog
    async def list_models(self) -> list[dict[str, Any]]:
        data = await self._send("GET", "/models", timeout_s=30)
        out = []
        for item in data.get("data") or []:
            model_id = str(item.get("id") or "")
            if not model_id or "embed" in model_id.lower():
                continue
            out.append({"model_id": model_id, "name": model_id})
        return out

    # ------------------------------------------------------------------ Anfrage
    def _messages(self, request: Request) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for turn in request.turns:
            if turn.role == "user":
                messages.append({"role": "user", "content": turn.text})
            elif turn.role == "assistant":
                if isinstance(turn.raw, dict):
                    messages.append(turn.raw)
                else:
                    messages.append(_assistant_message(turn))
            elif turn.role == "tool":
                for output in turn.outputs:
                    messages.append({"role": "tool", "tool_call_id": output.call_id, "content": output.text})
        return messages

    def _thinking(self, request: Request) -> dict[str, Any]:
        """Parameter für die Denkstufe; leer = ohne Vorgabe."""
        return {"reasoning_effort": request.thinking} if request.thinking else {}

    def _body(self, request: Request, thinking: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": self._messages(request),
            "max_tokens": request.max_output_tokens,
        }
        if request.tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}}
                for t in request.tools
            ]  # fmt: skip
        body.update(thinking)
        return body

    async def complete(self, request: Request) -> Reply:
        thinking = self._thinking(request)
        effective = True
        try:
            data = await self._send(
                "POST", "/chat/completions", body=self._body(request, thinking), timeout_s=request.timeout_s
            )
        except PlatformError as err:
            if not thinking or not mentions_thinking(err):
                raise
            # Die Plattform kennt die Stufe für dieses Modell nicht: ohne sie wiederholen.
            thinking, effective = {}, False
            data = await self._send(
                "POST", "/chat/completions", body=self._body(request, {}), timeout_s=request.timeout_s
            )
        return self._reply(data, thinking, effective)

    def _reply(self, data: dict[str, Any], thinking: dict[str, Any], effective: bool) -> Reply:
        choices = data.get("choices") or []
        if not choices:
            raise PlatformError("unavailable", "Antwort ohne Ergebnis (choices leer).")
        choice = choices[0]
        message = choice.get("message") or {}
        calls = []
        for index, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function") or {}
            arguments, raw, error = parse_arguments(fn.get("arguments"))
            calls.append(ToolCall(id=str(call.get("id") or f"call_{index}"), name=str(fn.get("name") or ""),
                                  arguments=arguments, raw=raw, error=error))  # fmt: skip
        finish = str(choice.get("finish_reason") or "")
        stop = "tool" if calls else _STOP.get(finish, "end" if finish in ("", "eos") else "other")
        if choice.get("error"):
            raise classify_status(502, _error_text(json.dumps(choice["error"])))
        return Reply(
            text=_content_text(message.get("content")),
            tool_calls=calls,
            usage=self._usage(data.get("usage") or {}),
            stop=stop,
            raw=_clean_assistant(message),
            thinking_sent=thinking or None,
            thinking_effective=effective,
            model=str(data.get("model") or ""),
        )

    def _usage(self, usage: dict[str, Any]) -> Usage:
        prompt_details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        reasoning = completion_details.get("reasoning_tokens")
        cost = usage.get("cost")
        return Usage(
            input_total=int(usage.get("prompt_tokens") or 0),
            cache_read=int(prompt_details.get("cached_tokens") or 0),
            cache_write=int(prompt_details.get("cache_write_tokens") or 0),
            output=int(usage.get("completion_tokens") or 0),
            reasoning=int(reasoning) if isinstance(reasoning, int | float) else None,
            cost=float(cost) if isinstance(cost, int | float) else None,
        )


def _assistant_message(turn: Turn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.text or None}
    if turn.tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw or "{}"}}
            for c in turn.tool_calls
        ]
    return message


def _clean_assistant(message: dict[str, Any]) -> dict[str, Any]:
    """Assistenten-Nachricht zum unveränderten Zurücksenden: mit Werkzeugaufrufen und den
    Denk-Angaben, die manche Modelle für den nächsten Schritt brauchen (reasoning_details)."""
    keep = ("role", "content", "tool_calls", "reasoning", "reasoning_details", "reasoning_content")
    out = {k: message[k] for k in keep if message.get(k) is not None}
    out.setdefault("role", "assistant")
    out.setdefault("content", None)
    return out


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _error_text(text: str) -> str:
    """Fehlermeldung aus einem JSON-Rumpf, einschließlich der Angaben des Hosters."""
    try:
        data = json.loads(text)
    except ValueError:
        return text[:1000]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        parts = [str(err.get("message") or "")]
        meta = err.get("metadata")
        if isinstance(meta, dict):
            for key in ("raw", "provider_name"):
                if meta.get(key):
                    parts.append(str(meta[key]) if isinstance(meta[key], str) else json.dumps(meta[key]))
        if err.get("code") and not isinstance(err.get("code"), int):
            parts.append(str(err["code"]))
        return " | ".join(p for p in parts if p)[:1000]
    if isinstance(err, str):
        return err[:1000]
    if isinstance(data, dict) and data.get("message"):
        return str(data["message"])[:1000]
    return text[:1000]


class OpenRouterAdapter(OpenAICompatAdapter):
    type = "openrouter"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["X-Title"] = "AIArena4BW"
        return headers

    def _thinking(self, request: Request) -> dict[str, Any]:
        return {"reasoning": {"effort": request.thinking}} if request.thinking else {}

    def _body(self, request: Request, thinking: dict[str, Any]) -> dict[str, Any]:
        body = super()._body(request, thinking)
        body["usage"] = {"include": True}  # abgerechnete Kosten in der Antwort
        # Anthropic-Modelle cachen nur auf Anforderung; andere Anbieter cachen von selbst.
        if request.caching and vendors.vendor_key(request.model) == "anthropic":
            body["cache_control"] = {"type": "ephemeral"}
        return body

    async def list_models(self) -> list[dict[str, Any]]:
        data = await self._send("GET", "/models", timeout_s=30)
        out = []
        for item in data.get("data") or []:
            model_id = str(item.get("id") or "")
            params = item.get("supported_parameters") or []
            if not model_id or model_id.startswith(("openrouter/", "~")):
                continue  # Router und Aliase sind keine Modelle
            if "tools" not in params:
                continue
            pricing = item.get("pricing") or {}
            created = item.get("created")
            out.append({
                "model_id": model_id,
                "name": _short_name(str(item.get("name") or model_id)),
                "context_window": item.get("context_length"),
                "supports_tools": True,
                "supports_reasoning": "reasoning" in params,
                "released": _date(created),
                "price_in": _per_million(pricing.get("prompt")),
                "price_out": _per_million(pricing.get("completion")),
                "price_cache_read": _per_million(pricing.get("input_cache_read")),
                "price_cache_write": _per_million(pricing.get("input_cache_write")),
                "max_tools": 128 if model_id.startswith("openai/") else None,
            })  # fmt: skip
        return out

    async def check(self) -> str:
        # Die Modellliste ist öffentlich; der Schlüssel wird gesondert geprüft.
        data = await self._send("GET", "/key", timeout_s=30)
        info = data.get("data") or {}
        label = "Schlüssel gültig"
        remaining = info.get("limit_remaining")
        if isinstance(remaining, int | float):
            label += f", Restlimit {remaining:.2f} $"
        return label


def _per_million(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number < 0 else round(number * 1_000_000, 6)


def _date(created: Any) -> str | None:
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(float(created), tz=UTC).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _short_name(name: str) -> str:
    """'Anthropic: Claude Haiku 5.5' -> 'Claude Haiku 5.5'."""
    return name.split(": ", 1)[1] if ": " in name else name
