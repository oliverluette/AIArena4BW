"""Adapter für SAP AI Core über den Orchestration Service (v2).

Stand 12.11.2026: nach der Dokumentation umgesetzt und gegen einen Nachbau geprüft, **nicht im
Echtbetrieb**. Ablauf:

1. Token: POST {url}/oauth/token (client_credentials) mit clientid/clientsecret des Service-Keys.
2. Deployment: GET {AI_API_URL}/v2/lm/deployments?scenarioId=orchestration&status=RUNNING.
3. Anfrage: POST {deploymentUrl}/v2/completion; Modell, Parameter, Werkzeuge und die letzte
   Nachricht stehen unter config.modules.prompt_templating, der Verlauf davor in messages_history.

Die Antwort (final_result) hat das Format der OpenAI-Chat-Completions.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .base import PlatformError, Reply, Request, classify_status, mentions_thinking, retry_after_seconds
from .openai_compat import OpenAICompatAdapter, _error_text

_EFFORT = {"none": "none", "low": "low", "medium": "medium", "high": "high", "xhigh": "high"}


class SapAiCoreAdapter(OpenAICompatAdapter):
    type = "sapaicore"

    def __init__(
        self, platform: dict[str, Any], credentials: str | None, transport: httpx.AsyncBaseTransport | None = None
    ):
        super().__init__(platform, credentials, transport)
        self._key: dict[str, Any] = {}
        if self.credentials:
            try:
                key = json.loads(self.credentials)
                self._key = key.get("credentials", key) if isinstance(key, dict) else {}
            except ValueError:
                self._key = {}
        api = self.base_url or str((self._key.get("serviceurls") or {}).get("AI_API_URL") or "")
        self._api = api.rstrip("/")
        self._group = str(self.options.get("resource_group") or "default")
        self._token = ""
        self._token_until = 0.0
        self._deployment = ""

    def secrets(self) -> list[str]:
        return [str(v) for v in (self._key.get("clientsecret"), self._token) if v]

    def _require_key(self) -> None:
        missing = [k for k in ("clientid", "clientsecret", "url") if not self._key.get(k)]
        if missing or not self._api:
            raise PlatformError(
                "auth",
                "Der Service-Key ist unvollständig (benötigt: clientid, clientsecret, url, "
                "serviceurls.AI_API_URL). Bitte in den Einstellungen als JSON einfügen.",
            )

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_until:
            return self._token
        self._require_key()
        url = str(self._key["url"]).rstrip("/") + "/oauth/token"
        try:
            response = await self._client.post(
                url, data={"grant_type": "client_credentials"},
                auth=(str(self._key["clientid"]), str(self._key["clientsecret"])), timeout=30,
            )  # fmt: skip
        except httpx.HTTPError as err:
            raise PlatformError("network", f"Anmeldung bei SAP AI Core nicht erreichbar: {err}") from None
        if response.status_code >= 400:
            kind = "auth" if response.status_code in (400, 401, 403) else "unavailable"
            raise PlatformError(
                kind,
                f"Anmeldung bei SAP AI Core abgelehnt (HTTP {response.status_code}). Ist der Service-Key noch gültig?",
                status=response.status_code,
            )
        data = response.json()
        self._token = str(data.get("access_token") or "")
        self._token_until = time.monotonic() + max(60.0, float(data.get("expires_in") or 600) - 60.0)
        return self._token

    async def _call(self, method: str, url: str, body: dict | None = None, timeout_s: float = 60) -> dict[str, Any]:
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}", "AI-Resource-Group": self._group,
                   "Content-Type": "application/json"}  # fmt: skip
        try:
            response = await self._client.request(
                method, url, headers=headers, json=body, timeout=httpx.Timeout(timeout_s, connect=15.0)
            )
        except httpx.TimeoutException:
            raise PlatformError("network", "Keine Antwort von SAP AI Core (Zeitüberschreitung).") from None
        except httpx.HTTPError as err:
            raise PlatformError("network", f"SAP AI Core nicht erreichbar: {err}") from None
        if response.status_code >= 400:
            if response.status_code == 401:
                self._token = ""
            raise classify_status(
                response.status_code,
                _error_text(response.text),
                retry_after_seconds(response.headers.get("retry-after")),
            )
        try:
            return response.json()
        except ValueError:
            raise PlatformError("unavailable", f"Antwort ist kein JSON: {response.text[:200]}") from None

    async def _deployment_url(self) -> str:
        if self._deployment:
            return self._deployment
        data = await self._call("GET", f"{self._api}/v2/lm/deployments?scenarioId=orchestration&status=RUNNING")
        for item in data.get("resources") or []:
            if item.get("deploymentUrl"):
                self._deployment = str(item["deploymentUrl"]).rstrip("/")
                return self._deployment
        raise PlatformError(
            "model_not_found",
            f"In der Resource Group „{self._group}“ läuft kein Deployment des Orchestration Service.",
        )

    async def list_models(self) -> list[dict[str, Any]]:
        data = await self._call("GET", f"{self._api}/v2/lm/scenarios/foundation-models/models")
        out = []
        for item in data.get("resources") or []:
            model_id = str(item.get("model") or "")
            versions = [v for v in item.get("versions") or [] if isinstance(v, dict)]
            current = next((v for v in versions if v.get("isLatest")), versions[-1] if versions else {})
            capabilities = [str(c).lower() for c in current.get("capabilities") or []]
            if not model_id or (capabilities and "text-generation" not in capabilities):
                continue
            if current.get("deprecated") and current.get("retirementDate", "9") < time.strftime("%Y-%m-%d"):
                continue
            out.append({
                "model_id": model_id,
                "name": model_id.split("--", 1)[-1],
                "context_window": current.get("contextLength"),
                "supports_tools": True if not capabilities else None,
                "max_tools": 128 if model_id.startswith(("gpt", "o1", "o3", "o4")) else None,
            })  # fmt: skip
        return out

    async def check(self) -> str:
        await self._deployment_url()
        return f"Orchestration Service erreichbar (Resource Group {self._group})"

    def _orchestration_body(self, request: Request, thinking: dict[str, Any]) -> dict[str, Any]:
        messages = self._messages(request)
        # Die Vorlage braucht mindestens eine Nachricht: die jüngsten (Nutzer bzw. Werkzeug-
        # ergebnisse); alles davor ist Verlauf. Platzhalter der Vorlage ({{?name}}) entschärfen.
        split = len(messages)
        while split > 1 and messages[split - 1].get("role") == "tool":
            split -= 1
        if split == len(messages):
            split -= 1
        template = [_escape(m) for m in messages[split:]]
        params: dict[str, Any] = {"max_tokens": request.max_output_tokens, **thinking}
        prompt: dict[str, Any] = {"template": template}
        if request.tools:
            prompt["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}}
                for t in request.tools
            ]  # fmt: skip
        return {
            "config": {"modules": {"prompt_templating": {
                "prompt": prompt,
                "model": {"name": request.model, "version": "latest", "params": params},
            }}},
            "messages_history": messages[:split],
        }  # fmt: skip

    def _thinking(self, request: Request) -> dict[str, Any]:
        return {"reasoning_effort": _EFFORT[request.thinking]} if request.thinking else {}

    async def complete(self, request: Request) -> Reply:
        url = await self._deployment_url() + "/v2/completion"
        thinking = self._thinking(request)
        effective = request.thinking != "xhigh"  # xhigh kennt der Dienst nicht: als high gesendet
        try:
            data = await self._call("POST", url, self._orchestration_body(request, thinking), request.timeout_s)
        except PlatformError as err:
            if not thinking or not mentions_thinking(err):
                raise
            thinking, effective = {}, False
            data = await self._call("POST", url, self._orchestration_body(request, {}), request.timeout_s)
        result = data.get("final_result") or data.get("orchestration_result") or data
        return self._reply(result, thinking, effective)


def _escape(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, str) and "{{" in content:
        message = {**message, "content": content.replace("{{", "{ {")}
    return message
