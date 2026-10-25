"""Deterministic, non-custodial task planning for Nexus.

This planner does not claim to be an LLM and never fabricates a blockchain,
wallet, provider account, budget, or successful external execution.
"""
from __future__ import annotations

from typing import Any, Dict, List

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
            task_id = await self.orchestrator.submit_task(
                task_type=task_type,
                payload=payload,
                priority=priority,
            )
            submitted_ids.append(task_id)
        return submitted_ids
