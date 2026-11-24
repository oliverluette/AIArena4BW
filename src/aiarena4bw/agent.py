"""Agent-Schleife: Modellanfrage, Werkzeugaufrufe über MCP, Ergebnisse zurück.

Alle Modelle erhalten denselben Systemtext und dieselben Werkzeugdefinitionen, unverändert vom
MCP-Server. Der Verlauf wird nie gekürzt. Es gibt keine lokalen Werkzeuge.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db, vault
from .mcpclient import McpConnection, McpError, McpTimeout, Tool
from .platforms.base import Adapter, PlatformError, Reply, Request, ToolOutput, Turn, Usage

AGENT_NAME = "AIArena4BW"
AGENT_VERSION = "1"

# Teil der Agent-Version: Jede Änderung am Text ist eine neue Version.
SYSTEM_PROMPT = (
    "Du arbeitest als Entwickler in einem SAP-BW/4HANA-System. Auf das System greifst du "
    "ausschließlich über die bereitgestellten Werkzeuge zu.\n\n"
    "Arbeite selbstständig, bis die Aufgabe vollständig erledigt ist, und stelle keine Rückfragen. "
    "Lies die Ergebnisse deiner Werkzeugaufrufe und behebe Fehler, bevor du weitermachst. "
    "Antworte erst dann ohne Werkzeugaufruf, wenn du fertig bist; diese Antwort beendet deine Arbeit."
)

BAD_ARGS_LIMIT = 3


@dataclass
class Limits:
    timeout_s: float = 900
    max_steps: int = 200
    tool_timeout_s: float = 120
    max_output_tokens: int = 16000
    api_retries: int = 4


@dataclass
class Outcome:
    status: str = "finished"  # finished | error | timeout | step_limit | cancelled
    finish_reason: str = ""
    text: str = ""
    steps: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    api_retries: int = 0
    usage: Usage = field(default_factory=Usage)
    cost: float | None = None
    cost_source: str | None = None  # billed | computed | None
    seconds: float = 0.0
    model_seconds: float = 0.0
    tool_seconds: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    write_attempts: list[str] = field(default_factory=list)
    error: str = ""
    error_kind: str = ""
    last_requirement: str = ""
    thinking_sent: dict[str, Any] | None = None
    thinking_effective: bool = True


class RunLog:
    """Vollständiges Protokoll als JSON-Zeilen; Geheimnisse werden beim Schreiben geschwärzt."""

    def __init__(self, path: Path | None, redact: vault.Redactor | None = None):
        self.path = path
        self.redact = redact or vault.Redactor()
        self._start = time.monotonic()
        self._file = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8")  # noqa: SIM115

    def write(self, entry_type: str, /, **data: Any) -> None:
        if not self._file:
            return
        entry = {"ts": db.now(), "s": round(time.monotonic() - self._start, 2), "type": entry_type, **data}
        try:
            line = json.dumps(entry, ensure_ascii=False, default=_jsonable)
            self._file.write((self.redact(line) or "") + "\n")
            self._file.flush()
        except (OSError, TypeError, ValueError):
            pass  # ein Protokollfehler darf keinen Lauf abbrechen

    def close(self) -> None:
        if self._file:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None


def _jsonable(value: Any) -> Any:
    for attr in ("to_dict", "model_dump"):
        if hasattr(value, attr):
            return getattr(value, attr)()
    return str(value)


def compute_cost(usage: Usage, prices: dict[str, Any] | None) -> float | None:
    """Kosten aus Tokens × Preis je 1 Mio. Tokens; None ohne Preis."""
    if not prices or prices.get("price_in") is None or prices.get("price_out") is None:
        return None
    price_in = float(prices["price_in"])
    read = prices.get("price_cache_read")
    write = prices.get("price_cache_write")
    fresh = max(0, usage.input_total - usage.cache_read - usage.cache_write)
    total = (
        fresh * price_in
        + usage.cache_read * (float(read) if read is not None else price_in)
        + usage.cache_write * (float(write) if write is not None else price_in)
        + usage.output * float(prices["price_out"])
    )
    return total / 1_000_000


class _Cancelled(Exception):
    pass


class _TimeUp(Exception):
    pass


class _Stop(Exception):
    """Der Lauf ist zu Ende; das Ergebnis steht schon in Outcome."""


async def run_agent(
    *,
    adapter: Adapter,
    model: str,
    prompt: str,
    mcp: McpConnection,
    tools: list[Tool],
    offered: set[str] | None = None,
    limits: Limits | None = None,
    thinking: str = "",
    caching: bool = True,
    prices: dict[str, Any] | None = None,
    system: str = SYSTEM_PROMPT,
    requirement_for: Callable[[str, Any], list[str]] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    should_cancel: Callable[[], bool] = lambda: False,
    log: RunLog | None = None,
) -> Outcome:
    """Führt einen Lauf (oder eine Prüfung) aus.

    offered: Namen der Werkzeuge, die das Modell sehen darf (None = alle). Verlangt das Modell ein
    vorhandenes, aber nicht angebotenes Werkzeug, wird der Aufruf abgelehnt und vermerkt
    (write_attempts) – so bleibt die Prüfung lesend.
    """
    limits = limits or Limits()
    log = log or RunLog(None)
    out = Outcome()
    started = time.monotonic()
    deadline = started + limits.timeout_s
    known = {t.name for t in tools}
    visible = [t for t in tools if offered is None or t.name in offered]
    tool_defs = [t.definition() for t in visible]
    visible_names = {t.name for t in visible}
    turns: list[Turn] = [Turn(role="user", text=prompt)]
    billed_any = computed_any = missing_price = False
    bad_streak = 0

    def emit(kind: str, **data: Any) -> None:
        if on_event:
            try:
                on_event(kind, {"seconds": round(time.monotonic() - started, 1), **data})
            except Exception:  # noqa: BLE001 - Speichern darf den Lauf nie abbrechen
                pass

    async def guard(coro: Any) -> Any:
        """Wartet auf coro, bricht aber bei Abbruchwunsch oder Zeitlimit ab."""
        task = asyncio.ensure_future(coro)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _TimeUp
                done, _ = await asyncio.wait({task}, timeout=min(0.5, remaining))
                if done:
                    return task.result()
                if should_cancel():
                    raise _Cancelled
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001
                    pass

    log.write("meta", agent=AGENT_NAME, agent_version=AGENT_VERSION, model=model, thinking=thinking,
              caching=caching, system=system, prompt=prompt, tools=[t.name for t in visible],
              limits=limits.__dict__)  # fmt: skip
    try:
        while True:
            if should_cancel():
                raise _Cancelled
            if out.steps >= limits.max_steps:
                out.status, out.finish_reason = "step_limit", "step_limit"
                out.error = f"Schrittlimit von {limits.max_steps} erreicht"
                break
            out.steps += 1
            emit("step", step=out.steps)

            # ---------------------------------------------------------- Modellanfrage
            reply: Reply | None = None
            attempt = 0
            while reply is None:
                request = Request(
                    model=model, system=system, turns=turns, tools=tool_defs, thinking=thinking,
                    max_output_tokens=limits.max_output_tokens, caching=caching,
                    timeout_s=max(5.0, deadline - time.monotonic()),
                )  # fmt: skip
                t0 = time.monotonic()
                try:
                    reply = await guard(adapter.complete(request))
                except PlatformError as err:
                    out.model_seconds += time.monotonic() - t0
                    log.write("error", step=out.steps, kind=err.kind, status=err.status, message=str(err))
                    if err.retryable and attempt < limits.api_retries:
                        attempt += 1
                        out.api_retries += 1
                        wait = err.retry_after if err.retry_after is not None else min(2.0**attempt, 30.0)
                        emit(
                            "error",
                            step=out.steps,
                            retry=attempt,
                            text=f"Plattform: {str(err)[:300]} – Wiederholung {attempt} in {wait:.0f} s",
                        )
                        await guard(asyncio.sleep(min(wait, 120.0)))
                        continue
                    out.status, out.finish_reason = "error", "platform_error"
                    out.error, out.error_kind = str(err)[:1000], err.kind
                    emit("error", step=out.steps, text=out.error[:500])
                    raise _Stop from None
                out.model_seconds += time.monotonic() - t0

            out.usage.add(reply.usage)
            step_cost = reply.usage.cost
            if step_cost is not None:
                billed_any = True
            else:
                step_cost = compute_cost(reply.usage, prices)
                if step_cost is None:
                    missing_price = True
                else:
                    computed_any = True
            if step_cost is not None:
                out.cost = (out.cost or 0.0) + step_cost
            if out.steps == 1:
                out.thinking_sent, out.thinking_effective = reply.thinking_sent, reply.thinking_effective
            log.write("response", step=out.steps, text=reply.text, stop=reply.stop,
                      tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments, "raw": c.raw
                                   if c.arguments is None else None} for c in reply.tool_calls],
                      usage=reply.usage.__dict__, content=reply.raw)  # fmt: skip
            emit("usage", step=out.steps, tokens_input=reply.usage.input_total, tokens_output=reply.usage.output)
            turns.append(Turn(role="assistant", text=reply.text, tool_calls=reply.tool_calls, raw=reply.raw))

            if not reply.tool_calls:
                out.text = reply.text
                out.finish_reason = {"end": "end", "length": "max_tokens", "refusal": "refusal"}.get(
                    reply.stop, reply.stop
                )
                break

            # ---------------------------------------------------------- Werkzeuge
            outputs: list[ToolOutput] = []
            for call in reply.tool_calls:  # nacheinander, in gegebener Reihenfolge (F-H12)
                out.tool_calls += 1
                out.tools_used.append(call.name)
                hits = requirement_for(call.name, call.arguments) if requirement_for else []
                if hits:
                    out.last_requirement = hits[-1]
                requirement = " | ".join(hits) if hits else out.last_requirement
                emit("tool_start", step=out.steps, tool=call.name, requirement=requirement)
                t0 = time.monotonic()
                is_error, text = False, ""
                if call.arguments is None:
                    bad_streak += 1
                    is_error = True
                    text = (f"Fehler: {call.error or 'Argumente nicht lesbar'}. Bitte die Argumente als "
                            "gültiges JSON-Objekt senden.")  # fmt: skip
                elif call.name not in visible_names:
                    bad_streak = 0
                    is_error = True
                    if call.name in known:
                        out.write_attempts.append(call.name)
                        text = (f"Fehler: Das Werkzeug {call.name} steht hier nicht zur Verfügung. "
                                "Diese Prüfung arbeitet ausschließlich lesend.")  # fmt: skip
                    else:
                        text = f"Fehler: Ein Werkzeug namens {call.name} gibt es nicht."
                else:
                    bad_streak = 0
                    try:
                        result = await guard(mcp.call_tool(call.name, call.arguments, limits.tool_timeout_s))
                        text, is_error = result.text, result.is_error
                    except McpTimeout as err:
                        text, is_error = f"Fehler: {err}", True
                    except McpError as err:
                        out.tool_seconds += time.monotonic() - t0
                        out.status, out.finish_reason = "error", "mcp_error"
                        out.error, out.error_kind = str(err)[:1000], "mcp"
                        emit(
                            "tool",
                            step=out.steps,
                            tool=call.name,
                            requirement=requirement,
                            duration=round(time.monotonic() - t0, 2),
                            is_error=True,
                            text=out.error[:500],
                        )
                        log.write("error", step=out.steps, kind="mcp", message=str(err))
                        raise _Stop from None
                duration = time.monotonic() - t0
                out.tool_seconds += duration
                if is_error:
                    out.tool_errors += 1
                outputs.append(ToolOutput(call_id=call.id, name=call.name, text=text, is_error=is_error))
                log.write("tool_result", step=out.steps, id=call.id, name=call.name, is_error=is_error,
                          duration=round(duration, 2), text=text)  # fmt: skip
                emit("tool", step=out.steps, tool=call.name, requirement=requirement,
                     duration=round(duration, 2), is_error=is_error,
                     text=text[:300] if is_error else None)  # fmt: skip
            turns.append(Turn(role="tool", outputs=outputs))
            if bad_streak >= BAD_ARGS_LIMIT:
                out.status, out.finish_reason = "error", "bad_tool_calls"
                out.error_kind = "bad_tool_calls"
                out.error = (f"Werkzeugaufrufe nicht lesbar: {bad_streak} Aufrufe in Folge mit "
                             "ungültigen JSON-Argumenten")  # fmt: skip
                emit("error", step=out.steps, text=out.error)
                break
    except _Stop:
        pass
    except _Cancelled:
        out.status, out.finish_reason = "cancelled", "cancelled"
    except _TimeUp:
        out.status, out.finish_reason = "timeout", "timeout"
        out.error = f"Zeitlimit von {limits.timeout_s:.0f} s erreicht"
        emit("error", step=out.steps, text=out.error)
    out.seconds = round(time.monotonic() - started, 1)
    out.model_seconds = round(out.model_seconds, 1)
    out.tool_seconds = round(out.tool_seconds, 1)
    if out.cost is not None and not missing_price:
        out.cost_source = "billed" if billed_any and not computed_any else "computed"
    else:
        out.cost, out.cost_source = None, None  # ein fehlender Preis wird nie als 0 $ gezeigt
    if out.steps == 0 and out.status == "finished":
        out.status = "error"
    log.write("end", status=out.status, finish_reason=out.finish_reason, error=out.error, steps=out.steps,
              tool_calls=out.tool_calls, usage=out.usage.__dict__, cost=out.cost, cost_source=out.cost_source,
              seconds=out.seconds)  # fmt: skip
    return out
