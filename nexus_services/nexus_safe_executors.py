"""Built-in safe executors for internal planning and external-account reconciliation.

These executors perform real local reads and produce auditable results. They do
not log into external platforms, spend money, place bets/trades, or transfer funds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

try:
    from .runtime_contracts import Executor, TaskRecord
    from .nexus_identity import get_capability_status, get_identity
    from .memory_store import configured_database_path
    from .payout_ledger import PayoutLedger
except ImportError:
    from runtime_contracts import Executor, TaskRecord
    from nexus_identity import get_capability_status, get_identity
    from memory_store import configured_database_path
    from payout_ledger import PayoutLedger


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityAssessmentExecutor(Executor):
    name = "CAPABILITY_ASSESSMENT"

    async def execute(self, task: TaskRecord, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return {
            "status": "ASSESSED",
            "execution_mode": "REAL_INTERNAL_OPERATION",
            "timestamp": _timestamp(),
            "identity": get_identity(),
            "capabilities": get_capability_status(),
            "task_id": task.task_id,
            "external_action_performed": False,
        }


class WorkflowPlanReviewExecutor(Executor):
    name = "WORKFLOW_PLAN_REVIEW"

    async def execute(self, task: TaskRecord, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        goal = str(task.payload.get("goal_context", "")).strip()
        if not goal:
            raise ValueError("Workflow plan requires a goal_context")
        return {
            "status": "PLAN_PREPARED",
            "execution_mode": "REAL_INTERNAL_OPERATION",
            "timestamp": _timestamp(),
            "goal": goal,
            "steps": [
                {"step": 1, "action": "ASSESS_CAPABILITIES_AND_REQUIRED_ACCESS"},
                {"step": 2, "action": "CHECK_PLATFORM_RULES_AND_USER_CONSTRAINTS"},
                {"step": 3, "action": "PREPARE_MINIMUM_REVERSIBLE_WORKFLOW"},
                {"step": 4, "action": "RUN_CONFIGURED_SAFE_INTEGRATIONS_ONLY"},
                {"step": 5, "action": "VERIFY_EVIDENCE_AND_PERSIST_OUTCOME"},
            ],
            "blocked_without_authorization": [
                "account login or credential submission",
                "financial transfer, purchase, bet or live trade",
                "code change without tests and human review",
            ],
            "external_action_performed": False,
        }


class PlatformAccountReconciliationExecutor(Executor):
    name = "PLATFORM_ACCOUNT_RECONCILIATION"

    async def execute(self, task: TaskRecord, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        ledger = PayoutLedger(configured_database_path())
        accounts = ledger.list_platform_accounts()
        totals: dict[str, float] = {}
        for account in accounts:
            currency = account["currency"]
            totals[currency] = round(totals.get(currency, 0.0) + float(account["balance"]), 2)
        return {
            "status": "RECONCILIATION_COMPLETED",
            "execution_mode": "REAL_INTERNAL_OPERATION",
            "timestamp": _timestamp(),
            "account_count": len(accounts),
            "accounts": accounts,
            "consolidated_external_balances": {
                currency: f"{amount:.2f}" for currency, amount in sorted(totals.items())
            },
            "financial_model": "EXTERNAL_PLATFORM_ACCOUNTS",
            "payout_destination": "EXTERNAL_PREPAID_VISA_WHEN_SUPPORTED",
            "funds_moved": False,
            "external_action_performed": False,
        }
