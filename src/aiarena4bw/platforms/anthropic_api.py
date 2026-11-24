"""Adapter für die Anthropic-API (Messages) über das offizielle SDK.

Besonderheiten:
- Denkblöcke und Werkzeugaufrufe gehen unverändert zurück an das Modell (Turn.raw).
- Prompt-Caching über `cache_control` auf oberster Ebene: der Haltepunkt wandert mit dem Verlauf.
- Keine serverseitigen Ausweichmodelle (`fallbacks`): Ein Benchmark darf einen Lauf nie
  unbemerkt von einem anderen Modell beantworten lassen. Eine Ablehnung endet als „refusal“.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import (
    Adapter,
    PlatformError,
    Reply,
    Request,
    ToolCall,
    Usage,
    classify_status,
    mentions_thinking,
    retry_after_seconds,
)

_STOP = {"end_turn": "end", "stop_sequence": "end", "tool_use": "tool", "max_tokens": "length",
         "refusal": "refusal"}  # fmt: skip

# Modelle mit adaptivem Denken (Stufe über output_config.effort).
_ADAPTIVE = re.compile(r"(fable|mythos|opus-(5|4-[678])|sonnet-(5|4-6)|haiku-5)")
# Denken lässt sich nicht abschalten.
_ALWAYS_ON = re.compile(r"(fable|mythos|opus-5-5)")
_BETWEEN_TOOLS = re.compile(r"sonnet-5-5")
_BUDGETS = {"low": 2000, "medium": 6000, "high": 12000, "xhigh": 15000}

# Listenpreise in $ je 1 Mio. Tokens (Eingabe, Ausgabe, Cache lesen); Stand 03.11.2026.
# Die Models-API liefert keine Preise; in den Einstellungen lassen sie sich überschreiben.
PRICES: list[tuple[str, float, float, float | None]] = [
    ("claude-fable-5-2", 8.0, 40.0, 0.20),
    ("claude-mythos-5-2", 8.0, 40.0, 0.20),
    ("claude-fable-5-1", 10.0, 50.0, None),
    ("claude-fable-5", 10.0, 50.0, None),
    ("claude-opus-5-5", 4.0, 20.0, 0.20),
    ("claude-opus-5", 5.0, 25.0, None),
    ("claude-opus-4-8", 5.0, 25.0, None),
    ("claude-opus-4-7", 5.0, 25.0, None),
    ("claude-opus-4-6", 5.0, 25.0, None),
    ("claude-opus-4-5", 5.0, 25.0, None),
    ("claude-sonnet-5-5", 2.0, 10.0, 0.10),
    ("claude-sonnet-5", 2.0, 10.0, None),
    ("claude-sonnet-4-6", 3.0, 15.0, None),
    ("claude-sonnet-4-5", 3.0, 15.0, None),
    ("claude-haiku-5-5", 0.10, 0.50, None),
    ("claude-haiku-4-5", 1.0, 5.0, None),
]


def list_price(model_id: str) -> dict[str, float | None]:
    for prefix, price_in, price_out, cache_read in PRICES:
        if model_id == prefix or model_id.startswith(prefix + "-2"):  # mit Datumsanhang
            return {
                "price_in": price_in,
                "price_out": price_out,
                "price_cache_read": cache_read if cache_read is not None else round(price_in * 0.1, 4),
                "price_cache_write": round(price_in * 1.25, 4),
            }
    return {"price_in": None, "price_out": None, "price_cache_read": None, "price_cache_write": None}


def thinking_params(model: str, level: str, max_tokens: int) -> tuple[dict[str, Any], bool]:
    """(Parameter, wirksam) für eine Denkstufe."""
    name = model.lower()
    if not level:
        return {}, True
    if _ADAPTIVE.search(name):
        if level == "none":
            if _ALWAYS_ON.search(name):
                return {}, False  # Denken ist bei diesen Modellen immer an
            if _BETWEEN_TOOLS.search(name):
                return {"thinking": {"type": "between_tools"}}, True
            return {"thinking": {"type": "disabled"}}, True
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": level}}, True
    if level == "none":
        return {}, True  # ältere Modelle denken nur auf Anforderung
    budget = min(_BUDGETS[level], max(1024, max_tokens - 1024))
    return {"thinking": {"type": "enabled", "budget_tokens": budget}}, True


class AnthropicAdapter(Adapter):
    type = "anthropic"

    def __init__(self, platform: dict[str, Any], credentials: str | None):
        super().__init__(platform, credentials)
        import anthropic

        self._sdk = anthropic
        kwargs: dict[str, Any] = {"api_key": self.credentials or "missing", "max_retries": 0}
        if self.base_url and self.base_url != "https://api.anthropic.com":
            kwargs["base_url"] = self.base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)

    async def aclose(self) -> None:
        await self._client.close()

    def _error(self, err: Exception) -> PlatformError:
        sdk = self._sdk
        if isinstance(err, sdk.APITimeoutError):
            return PlatformError("network", "Keine Antwort von der Anthropic-API (Zeitüberschreitung).")
        if isinstance(err, sdk.APIConnectionError):
            return PlatformError("network", f"Anthropic-API nicht erreichbar: {err}")
        if isinstance(err, sdk.APIStatusError):
            retry_after = retry_after_seconds(err.response.headers.get("retry-after"))
            return classify_status(err.status_code, getattr(err, "message", str(err)), retry_after)
        return PlatformError("other", str(err))

    async def list_models(self) -> list[dict[str, Any]]:
        out = []
        try:
            async for model in self._client.models.list(limit=1000):
                data = model.to_dict()
                created = str(data.get("created_at") or "")[:10] or None
                out.append({
                    "model_id": data["id"],
                    "name": data.get("display_name") or data["id"],
                    "context_window": data.get("max_input_tokens"),
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "released": created,
                    **list_price(data["id"]),
                })  # fmt: skip
        except Exception as err:
            raise self._error(err) from None
        return out

    def _messages(self, request: Request) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in request.turns:
            if turn.role == "user":
                messages.append({"role": "user", "content": turn.text})
            elif turn.role == "assistant":
                if isinstance(turn.raw, list):
                    content = turn.raw
                else:
                    content = [{"type": "text", "text": turn.text}] if turn.text else []
                    content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments or {}}
                                for c in turn.tool_calls]  # fmt: skip
                messages.append({"role": "assistant", "content": content})
            elif turn.role == "tool":
                # Alle Ergebnisse eines Schritts in einer Nachricht, sonst verlernt das Modell
                # parallele Aufrufe.
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": o.call_id, "content": o.text or "(leer)",
                     **({"is_error": True} if o.is_error else {})}
                    for o in turn.outputs
                ]})  # fmt: skip
        return messages

    async def complete(self, request: Request) -> Reply:
        params, effective = thinking_params(request.model, request.thinking, request.max_output_tokens)
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": self._messages(request),
            "timeout": request.timeout_s,
        }
        if request.system:
            kwargs["system"] = request.system
        if request.tools:
            kwargs["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in request.tools
            ]
        if request.caching:
            kwargs["cache_control"] = {"type": "ephemeral"}
        try:
            response = await self._client.messages.create(**kwargs, **params)
        except Exception as err:
            error = self._error(err)
            if not params or not mentions_thinking(error):
                raise error from None
            params, effective = {}, False  # Stufe für dieses Modell unbekannt: ohne sie
            try:
                response = await self._client.messages.create(**kwargs)
            except Exception as err2:
                raise self._error(err2) from None
        return self._reply(response, params, effective)

    def _reply(self, response: Any, params: dict[str, Any], effective: bool) -> Reply:
        data = response.to_dict()
        text, calls = [], []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use":
                arguments = block.get("input")
                ok = isinstance(arguments, dict)
                calls.append(ToolCall(
                    id=str(block.get("id") or ""), name=str(block.get("name") or ""),
                    arguments=arguments if ok else None, raw=json.dumps(arguments, ensure_ascii=False),
                    error="" if ok else "Argumente sind kein JSON-Objekt",
                ))  # fmt: skip
        usage = data.get("usage") or {}
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        stop_reason = str(data.get("stop_reason") or "")
        return Reply(
            text="".join(text),
            tool_calls=calls,
            usage=Usage(
                input_total=int(usage.get("input_tokens") or 0) + cache_read + cache_write,
                cache_read=cache_read,
                cache_write=cache_write,
                output=int(usage.get("output_tokens") or 0),
            ),
            stop="tool" if calls and stop_reason in ("tool_use", "") else _STOP.get(stop_reason, "other"),
            raw=data.get("content") or [],
            thinking_sent=params or None,
            thinking_effective=effective,
            model=str(data.get("model") or ""),
        )
