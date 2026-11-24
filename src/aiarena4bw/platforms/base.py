"""Inneres Format für Nachrichten, Werkzeugaufrufe und Nutzung sowie die Adapter-Schnittstelle.

Die Agent-Schleife kennt nur diese Typen. Jeder Adapter übersetzt sie in das Format seiner
Plattform und zurück.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

THINKING_LEVELS = ("", "none", "low", "medium", "high", "xhigh")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None  # None, wenn die Argumente nicht lesbar waren
    raw: str = ""  # Argumente, wie die Plattform sie lieferte
    error: str = ""


@dataclass
class ToolOutput:
    call_id: str
    name: str
    text: str
    is_error: bool = False


@dataclass
class Usage:
    """Einheitliche Zählung: input_total schließt die Cache-Anteile ein."""

    input_total: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int | None = None
    cost: float | None = None  # von der Plattform gemeldet ("abgerechnet")

    def add(self, other: Usage) -> None:
        self.input_total += other.input_total
        self.cache_read += other.cache_read
        self.cache_write += other.cache_write
        self.output += other.output
        if other.reasoning is not None:
            self.reasoning = (self.reasoning or 0) + other.reasoning
        if other.cost is not None:
            self.cost = (self.cost or 0.0) + other.cost


@dataclass
class Turn:
    """Eine Nachricht des Verlaufs."""

    role: str  # user | assistant | tool
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    outputs: list[ToolOutput] = field(default_factory=list)  # nur role == "tool"
    raw: Any = None  # Nachricht der Plattform, unverändert zurückzugeben


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop: str  # end | tool | length | refusal | other
    raw: Any = None
    thinking_sent: dict[str, Any] | None = None  # tatsächlich gesendete Parameter
    thinking_effective: bool = True  # False: Stufe ohne Wirkung
    model: str = ""


@dataclass
class Request:
    model: str
    system: str
    turns: list[Turn]
    tools: list[dict[str, Any]]  # [{name, description, input_schema}]
    thinking: str = ""
    max_output_tokens: int = 16000
    caching: bool = True
    timeout_s: float = 600.0


class PlatformError(Exception):
    """Fehler einer Plattform, eingeordnet für Wiederholung und Gültigkeit.

    kind: auth | credits | rate_limit | unavailable | network | model_not_found | tool_limit |
          context | bad_request | other
    """

    def __init__(self, kind: str, message: str, *, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.kind in ("rate_limit", "unavailable", "network")


_CREDITS = re.compile(
    r"more credits|can only afford|insufficient (credits|funds|balance|quota)|payment required|"
    r"quota exceeded|credit limit|credit balance|billing", re.I)  # fmt: skip
_TRANSIENT_CREDITS = re.compile(r"could not verify (the )?available credits|retry shortly", re.I)
_MODEL = re.compile(
    r"model .{0,80}(not found|does not exist|not available|is not supported)|no endpoints found|"
    r"model_not_found|is not a valid model|unknown model|no allowed providers", re.I)  # fmt: skip
_TOOL_LIMIT = re.compile(r"'tools': array too long|maximum length 128|too many tools|max.{0,20}tools", re.I)
_CONTEXT = re.compile(
    r"context (length|window)|maximum context|too many tokens|prompt is too long|"
    r"exceeds? the (model'?s? )?(maximum|max) (context|input|token)|context_length_exceeded|"
    r"input is too long|reduce the length", re.I)  # fmt: skip
_THINKING = re.compile(r"thinking|reasoning|effort|budget_tokens|output_config", re.I)


def classify_status(status: int | None, text: str, retry_after: float | None = None) -> PlatformError:
    """Ordnet eine Fehlerantwort ein; Grundlage sind Statuscode und Text."""
    message = (text or "").strip()[:1000] or f"HTTP {status}"
    if _TRANSIENT_CREDITS.search(message):
        kind = "unavailable"
    elif status == 402 or _CREDITS.search(message):
        kind = "credits"
    elif status in (401, 403):
        kind = "auth"
    elif _CONTEXT.search(message) and status in (400, 413, 422, None):
        kind = "context"
    elif _TOOL_LIMIT.search(message):
        kind = "tool_limit"
    elif status == 404 or _MODEL.search(message):
        kind = "model_not_found"
    elif status == 429:
        kind = "rate_limit"
    elif status in (408, 409, 425) or (status is not None and status >= 500):
        kind = "unavailable"
    elif status in (400, 413, 422):
        kind = "bad_request"
    else:
        kind = "other"
    return PlatformError(kind, message, status=status, retry_after=retry_after)


def mentions_thinking(error: PlatformError) -> bool:
    """Lehnt die Plattform die Denk-Parameter ab? Dann wird ohne sie wiederholt."""
    return error.kind == "bad_request" and bool(_THINKING.search(str(error)))


def parse_arguments(raw: Any) -> tuple[dict[str, Any] | None, str, str]:
    """(argumente, rohtext, fehler) aus den Argumenten eines Werkzeugaufrufs."""
    if isinstance(raw, dict):
        return raw, json.dumps(raw, ensure_ascii=False), ""
    text = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    if not text.strip():
        return {}, text, ""
    try:
        value = json.loads(text)
    except ValueError as err:
        return None, text, f"Argumente sind kein gültiges JSON: {err}"
    if not isinstance(value, dict):
        return None, text, "Argumente sind kein JSON-Objekt"
    return value, text, ""


def retry_after_seconds(value: str | None) -> float | None:
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None


class Adapter:
    """Schnittstelle eines Plattformtyps."""

    type = ""

    def __init__(self, platform: dict[str, Any], credentials: str | None):
        self.platform = platform
        self.credentials = credentials or ""
        self.base_url = str(platform.get("base_url") or "").rstrip("/")
        self.options = platform.get("options") or {}

    async def aclose(self) -> None:  # pragma: no cover - Standard: nichts zu schließen
        return None

    async def list_models(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def check(self) -> str:
        """Verbindungstest; liefert eine kurze Erfolgsmeldung oder wirft PlatformError."""
        models = await self.list_models()
        return f"{len(models)} Modelle abrufbar"

    async def complete(self, request: Request) -> Reply:
        raise NotImplementedError

    def secrets(self) -> list[str]:
        return [self.credentials] if self.credentials else []
