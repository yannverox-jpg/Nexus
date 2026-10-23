"""Explicit, provider-owned AI connectors for Nexus advisory roles.

Connectors are disabled unless the corresponding official API key and model are
configured in the environment. They never execute payments, trades, bets,
browser actions, or withdrawals; callers receive text recommendations only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProviderConnector:
    provider_id: str
    label: str
    role: str
    api_key_env: str
    model_env: str
    default_model: str
    endpoint_env: str
    default_endpoint: str

    def status(self) -> dict[str, Any]:
        configured = bool(os.getenv(self.api_key_env, "").strip())
        return {
            "provider_id": self.provider_id,
            "label": self.label,
            "role": self.role,
            "status": "CONFIGURED" if configured else "NOT_CONNECTED",
            "status_scope": "role_agent_connectors",
            "connection_scope": "official_provider_api",
            "connector_available": configured,
            "authenticated": False,
            "can_execute_actions": False,
            "api_key_env": self.api_key_env,
            "model": os.getenv(self.model_env, self.default_model),
        }

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        google_search: bool = False,
    ) -> dict[str, Any]:
        """Call the configured official API and return advisory text only."""
        api_key = os.getenv(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"{self.provider_id} provider is not configured")
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        endpoint = os.getenv(self.endpoint_env, self.default_endpoint).strip()
        model = os.getenv(self.model_env, self.default_model).strip()
        payload, response_path = self._request_payload(
            prompt, system, model, google_search=google_search,
        )
        if self.provider_id == "gemini":
            endpoint = f"{endpoint.format(model=model)}?key={api_key}"
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(api_key),
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"{self.provider_id} API returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{self.provider_id} API is unavailable") from exc

        text = self._extract_text(data, response_path)
        result = {
            "provider": self.provider_id,
            "model": model,
            "status": "ADVISORY",
            "execution_mode": "REAL",
            "can_execute_actions": False,
            "text": text,
        }
        if self.provider_id == "gemini" and google_search:
            result["sources"] = self._gemini_sources(data)
            result["grounding"] = "google_search"
        return result

    def _request_payload(
        self,
        prompt: str,
        system: str,
        model: str,
        *,
        google_search: bool = False,
    ) -> tuple[dict[str, Any], str]:
        if self.provider_id == "gemini":
            payload = {
                "systemInstruction": {"parts": [{"text": system}]} if system else None,
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            }
            if google_search:
                payload["tools"] = [{"google_search": {}}]
            return payload, "candidates.0.content.parts.0.text"
        if self.provider_id == "claude":
            return {
                "model": model,
                "max_tokens": 1200,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }, "content.0.text"
        return {
            "model": model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
        }, "choices.0.message.content"

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Nexus/official-ai-connector",
        }
        if self.provider_id == "claude":
            headers.update({
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            })
        elif self.provider_id != "gemini":
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _extract_text(data: dict[str, Any], path: str) -> str:
        value: Any = data
        for segment in path.split("."):
            value = value[int(segment)] if segment.isdigit() else value[segment]
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("Provider returned no advisory text")
        return value.strip()

    @staticmethod
    def _gemini_sources(data: dict[str, Any]) -> list[dict[str, str]]:
        candidates = data.get("candidates", [])
        if not candidates or not isinstance(candidates[0], dict):
            return []
        metadata = candidates[0].get("groundingMetadata", {})
        chunks = metadata.get("groundingChunks", []) if isinstance(metadata, dict) else []
        sources: list[dict[str, str]] = []
        seen: set[str] = set()
        for chunk in chunks:
            web = chunk.get("web", {}) if isinstance(chunk, dict) else {}
            uri = web.get("uri") if isinstance(web, dict) else None
            if isinstance(uri, str) and uri.startswith("https://") and uri not in seen:
                sources.append({"title": str(web.get("title") or uri), "url": uri})
                seen.add(uri)
        return sources

CONNECTORS = {
    "codex_gpt": ProviderConnector(
        "codex_gpt", "Codex / GPT", "reasoning and coordination",
        "NEXUS_OPENAI_API_KEY", "NEXUS_OPENAI_MODEL", "gpt-4o-mini",
        "NEXUS_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions",
    ),
    "gemini": ProviderConnector(
        "gemini", "Gemini", "research and evidence review",
        "NEXUS_GEMINI_API_KEY", "NEXUS_GEMINI_MODEL", "gemini-3.8-flash",
        "NEXUS_GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ),
    "claude": ProviderConnector(
        "claude", "Claude", "architecture and e-commerce design proposals",
        "NEXUS_ANTHROPIC_API_KEY", "NEXUS_ANTHROPIC_MODEL", "claude-3-5-haiku-latest",
        "NEXUS_ANTHROPIC_ENDPOINT", "https://api.anthropic.com/v1/messages",
    ),
}


def get_connector_status() -> list[dict[str, Any]]:
    return [connector.status() for connector in CONNECTORS.values()]
