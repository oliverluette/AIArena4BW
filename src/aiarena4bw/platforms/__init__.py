"""Plattform-Adapter: ein Adapter je Plattformtyp."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import store, vault
from .base import Adapter, PlatformError, Reply, Request, ToolCall, ToolOutput, Turn, Usage

__all__ = [
    "Adapter", "PlatformError", "Reply", "Request", "ToolCall", "ToolOutput", "Turn", "Usage",
    "create_adapter", "adapter_for_model", "LIVE_VERIFIED",
]  # fmt: skip

# Welche Plattformtypen im Echtbetrieb geprüft sind.
LIVE_VERIFIED = {"openrouter": True, "anthropic": False, "sapaicore": False, "openai": False}


def create_adapter(platform: dict[str, Any], credentials: str | None = None) -> Adapter:
    """Adapter für eine eingerichtete Plattform. credentials=None: aus dem Schlüsselbund."""
    if credentials is None:
        credentials = vault.get(vault.platform_key(platform["id"]))
    ptype = platform["type"]
    if ptype == "anthropic":
        from .anthropic_api import AnthropicAdapter

        return AnthropicAdapter(platform, credentials)
    if ptype == "openrouter":
        from .openai_compat import OpenRouterAdapter

        return OpenRouterAdapter(platform, credentials)
    if ptype == "sapaicore":
        from .sapaicore import SapAiCoreAdapter

        return SapAiCoreAdapter(platform, credentials)
    if ptype == "openai":
        from .openai_compat import OpenAICompatAdapter

        return OpenAICompatAdapter(platform, credentials)
    raise PlatformError("other", f"Unbekannter Plattformtyp „{ptype}“.")


def adapter_for_model(conn: sqlite3.Connection, full_model_id: str) -> tuple[Adapter, str, dict[str, Any]]:
    """(Adapter, Modell-ID der Plattform, Plattform) für 'plattform:modell-id'."""
    from .. import vendors

    platform_id, model_id = vendors.split_model_id(full_model_id)
    platform = store.get_platform(conn, platform_id)
    if not platform:
        raise PlatformError(
            "other", f"Die Plattform „{platform_id}“ des Modells {full_model_id} ist nicht eingerichtet."
        )
    if platform["type"] != "openai" and not platform["credentials_set"]:
        raise PlatformError(
            "auth",
            f"Für die Plattform „{platform_id}“ sind keine Zugangsdaten hinterlegt (Einstellungen > LLM-Plattformen).",
        )
    return create_adapter(platform), model_id, platform
