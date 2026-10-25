"""Canonical self-description and truthful capability reporting for Nexus.

Readiness is derived from configured integrations. This module never reports
unconfigured providers, executors, or code-editing permissions as operational.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from .agent_roles import get_role_assignments
    from .ai_connectors import get_connector_status
    from .code_change_manager import code_change_status
except ImportError:
    from agent_roles import get_role_assignments
    from ai_connectors import get_connector_status
    from code_change_manager import code_change_status


NEXUS_IDENTITY: dict[str, Any] = {
    "name": "Nexus",
    "identity": "Agent logiciel autonome orchestrant des tâches autorisées via des intégrations explicites.",
    "mission": (
        "Comprendre l'objectif de l'utilisateur, préparer un plan, appeler les intégrations "
        "configurées, conserver la mémoire utile et rapporter des résultats vérifiables."
    ),
    "domains": ["microservices", "ecommerce", "trading_analysis", "sports_analysis", "ghost"],
    "financial_architecture": {
        "owns_wallet": False,
        "custodies_funds": False,
        "platform_balances_are_external": True,
        "payout_destination": "external_prepaid_visa_when_supported_by_the_platform",
    },
    "operating_rules": [
        "Nexus reste le coordinateur et la source de vérité de ses tâches et de sa mémoire.",
        "GPT vérifie le raisonnement et les incohérences.",
        "Gemini recherche les éléments probants et indique leur provenance.",
        "Claude propose des améliorations d'architecture et d'e-commerce.",
        "Les fournisseurs IA conseillent; ils ne constituent pas une autorisation d'action.",
        "Les modifications de code doivent être testées et passer par une approbation avant application.",
        "Aucun résultat, revenu, paiement ou exécution ne doit être déclaré sans preuve.",
    ],
}


def get_identity() -> dict[str, Any]:
    """Return a copy of Nexus's stable identity and mission."""
    return {
        **NEXUS_IDENTITY,
        "domains": list(NEXUS_IDENTITY["domains"]),
        "financial_architecture": dict(NEXUS_IDENTITY["financial_architecture"]),
        "operating_rules": list(NEXUS_IDENTITY["operating_rules"]),
        "provider_roles": get_role_assignments(),
    }


def get_capability_status() -> dict[str, Any]:
    """Return observed configuration, not aspirational readiness percentages."""
    database_path = os.getenv("NEXUS_OPERATIONAL_DB_PATH", "nexus_operational.db")
    path = Path(database_path).expanduser() if not database_path.startswith("file:") else None
    persistent_memory = (
        database_path != ":memory:"
        and "mode=memory" not in database_path.casefold()
        and not (path is not None and str(path) == ":memory:")
    )
    providers = get_connector_status()
    configured = [item["provider_id"] for item in providers if item["connector_available"]]
    try:
        from .stealth_browser_agent import async_playwright
    except ImportError:
        try:
            from stealth_browser_agent import async_playwright
        except Exception:
            async_playwright = None
    except Exception:
        async_playwright = None
    browser_package = async_playwright is not None

    code_status = code_change_status()
    code_mode = code_status["mode"]

    return {
        "identity_loaded": True,
        "chat_api_available": True,
        "persistent_memory_configured": persistent_memory,
        "memory_database_path_configured": bool(database_path),
        "providers": providers,
        "providers_configured": configured,
        "provider_count_configured": len(configured),
        "browser": {
            "playwright_package_available": browser_package,
            "allowed_hosts_configured": bool(os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "").strip()),
            "actions_enabled": False,
            "note": "Navigation is limited to configured hosts; sensitive login, payments, CAPTCHA and form submission remain human-controlled.",
        },
        "code_adaptation": {
            "mode": code_mode,
            "can_propose_changes": True,
            "github_pr_workflow_configured": code_status["configured"],
            "can_apply_changes_automatically": False,
            "requires_tests_and_human_approval": True,
            "note": "When GitHub credentials are configured, Nexus can open a draft pull request on a separate branch. It never edits the running process, bypasses CI, or merges its own changes.",
            "github": code_status,
        },
        "execution": {
            "can_plan_tasks": True,
            "safe_internal_executors": [
                "CAPABILITY_ASSESSMENT",
                "WORKFLOW_PLAN_REVIEW",
                "PLATFORM_ACCOUNT_RECONCILIATION",
            ],
            "can_execute_registered_integrations_only": True,
            "unsupported_tasks_fail_closed": True,
            "external_platform_execution_configured": False,
            "financial_transfers_enabled": False,
            "ready_status": "READY_FOR_INTERNAL_PLANNING",
            "external_integration_status": (
                "PARTIAL" if len(configured) < 3 or not browser_package
                or not os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "").strip()
                else "CONFIGURED_WITH_GUARDS"
            ),
        },
    }
