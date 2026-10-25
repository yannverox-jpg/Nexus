"""Deterministic, non-custodial task planning for Nexus.

This planner does not claim to be an LLM and never fabricates a blockchain,
wallet, provider account, budget, or successful external execution.
"""
from __future__ import annotations

from typing import Any, Dict, List
import uuid

try:
    from .legacy_runtime_adapter import NexusOrchestrator, TaskPriority
except ImportError:
    from legacy_runtime_adapter import NexusOrchestrator, TaskPriority


class NexusAutoTaskEngine:
    """Convert an objective into auditable planning and reconciliation tasks."""

    def __init__(self, orchestrator: NexusOrchestrator):
        self.orchestrator = orchestrator

    async def decompose_and_enqueue_goal(
        self, high_level_goal: str, context: Dict[str, Any]
    ) -> List[str]:
        if not isinstance(high_level_goal, str) or not high_level_goal.strip():
            raise ValueError("L'objectif Nexus ne peut pas être vide")
        # This is deterministic planning, not a claim that an LLM generated a plan.
        # A stable mission ID lets the API reconcile every task belonging to this goal.
        goal_id = str(context.get("goal_id") or uuid.uuid4())
        safe_context = {
            key: context[key]
            for key in ("budget_usdc", "target_amount", "target_currency", "deadline_at")
            if key in context
        }
        task_specs = [
            (
                "CAPABILITY_ASSESSMENT",
                TaskPriority.HIGH,
                {
                    "action": "ASSESS_CONFIGURED_CAPABILITIES",
                    "goal_context": high_level_goal.strip(),
                    "execution_mode": "PLAN_ONLY",
                },
            ),
            (
                "WORKFLOW_PLAN_REVIEW",
                TaskPriority.HIGH,
                {
                    "action": "PREPARE_CONSTRAINT_AWARE_PLAN",
                    "goal_context": high_level_goal.strip(),
                    "execution_mode": "PLAN_ONLY",
                },
            ),
            (
                "PLATFORM_ACCOUNT_RECONCILIATION",
                TaskPriority.MEDIUM,
                {
                    "action": "RECONCILE_AUTHORIZED_EXTERNAL_SNAPSHOTS",
                    "financial_model": "EXTERNAL_PLATFORM_ACCOUNTS",
                    "payout_destination": "EXTERNAL_PREPAID_VISA_WHEN_SUPPORTED",
                    "execution_mode": "RECONCILIATION_ONLY",
                },
            ),
        ]
        submitted_ids: List[str] = []
        for task_type, priority, payload in task_specs:
            task_payload = {
                **payload,
                "goal_id": goal_id,
                "goal_context": high_level_goal.strip(),
                "goal_constraints": safe_context,
            }
            task_id = await self.orchestrator.submit_task(
                task_type=task_type,
                payload=task_payload,
                priority=priority,
            )
            submitted_ids.append(task_id)
        self.last_goal_id = goal_id
        return submitted_ids
