"""Real multi-provider advisory coordination for the canonical Nexus API.

Providers produce recommendations only. This module never executes tools, trades,
payments, withdrawals, browser actions, or code changes.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

try:
    from .ai_connectors import CONNECTORS
    from .agent_roles import build_agent_system_context
except ImportError:
    from ai_connectors import CONNECTORS
    from agent_roles import build_agent_system_context


async def _ask_provider(provider_id: str, prompt: str, domain: str) -> dict[str, Any]:
    connector = CONNECTORS[provider_id]
    system = build_agent_system_context(provider_id, domain)
    try:
        result = await asyncio.to_thread(
            connector.complete,
            prompt,
            system=system,
            google_search=(provider_id == "gemini"),
        )
        return {"provider_id": provider_id, **result}
    except Exception as exc:
        # Avoid returning exception text: provider errors can contain sensitive details.
        return {
            "provider_id": provider_id,
            "status": "UNAVAILABLE",
            "execution_mode": "NOT_EXECUTED",
            "can_execute_actions": False,
            "error_type": type(exc).__name__,
        }


async def coordinate_advisors(
    prompt: str,
    *,
    domain: str = "general",
    db_manager: Any = None,
    readiness_pct: float = 0.0,
) -> dict[str, Any]:
    """Ask GPT, Gemini and Claude concurrently and persist the observed outcome."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must not be empty")
    if domain not in {"general", "microservices", "ecommerce", "trading", "sports", "ghost"}:
        raise ValueError("unsupported Nexus domain")

    run_id = "ai-review-" + uuid.uuid4().hex
    provider_ids = ("codex_gpt", "gemini", "claude")
    results = await asyncio.gather(
        *(_ask_provider(provider_id, prompt.strip(), domain) for provider_id in provider_ids)
    )
    available = [item for item in results if item.get("status") == "ADVISORY"]
    outcome = {
        "run_id": run_id,
        "status": "COMPLETED" if len(available) == 3 else ("PARTIAL" if available else "FAILED"),
        "execution_mode": "REAL_PROVIDER_CALLS",
        "action_execution": "NOT_PERFORMED",
        "providers_expected": list(provider_ids),
        "providers_available": [item["provider_id"] for item in available],
        "providers": results,
        "persisted": False,
    }

    if db_manager is not None:
        by_provider = {item["provider_id"]: item for item in results}
        db_manager.save_ai_decision(
            run_id,
            by_provider.get("gemini", {}),
            by_provider.get("codex_gpt", {}),
            by_provider.get("claude", {}),
            float(readiness_pct),
        )
        outcome["persisted"] = True
    return outcome
