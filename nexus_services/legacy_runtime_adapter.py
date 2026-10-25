"""Compatibility bridge from historical service APIs to the canonical runtime.

No placeholder worker reports successful execution. Unsupported tasks are recorded
and fail closed by NexusRuntime until a real executor is explicitly registered.
Real asset transfers are deliberately disabled until per-transaction approval and
receipt verification are implemented.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict


try:
    from .runtime_contracts import NexusRuntime, OperationalJournal
except ImportError:
    from runtime_contracts import NexusRuntime, OperationalJournal


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class NexusOrchestrator:
    """Expose the old spawn_agent/submit_task/start_dispatcher API over NexusRuntime."""

    def __init__(self, max_agents: int = 10, db_manager: Any = None):
        self.max_agents = max_agents
        self.agents: dict[str, str] = {}
        db_path = (
            getattr(db_manager, "db_path", None)
            or os.getenv("NEXUS_OPERATIONAL_DB_PATH", "nexus_operational.db")
        )
        self.runtime = NexusRuntime(
            operational_journal=OperationalJournal(db_path),
            name="NexusCanonicalRuntime",
        )
        try:
            from .nexus_safe_executors import (
                CapabilityAssessmentExecutor,
                WorkflowPlanReviewExecutor,
                PlatformAccountReconciliationExecutor,
            )
        except ImportError:
            from nexus_safe_executors import (
                CapabilityAssessmentExecutor,
                WorkflowPlanReviewExecutor,
                PlatformAccountReconciliationExecutor,
            )
        for executor in (
            CapabilityAssessmentExecutor(),
            WorkflowPlanReviewExecutor(),
            PlatformAccountReconciliationExecutor(),
        ):
            self.runtime.register_executor(executor)
        self.runtime.boot()

    def spawn_agent(self, agent_id: str, capability: str) -> None:
        if len(self.agents) >= self.max_agents and agent_id not in self.agents:
            raise RuntimeError("Nexus agent capacity reached")
        # Registration is metadata only; it does not claim a worker is executable.
        self.agents[agent_id] = capability

    async def submit_task(
        self, task_type: str, payload: Dict[str, Any],
        priority: TaskPriority | str = TaskPriority.MEDIUM,
    ) -> str:
        if isinstance(priority, TaskPriority):
            priority_name = priority.name
        else:
            priority_name = str(priority).upper()
            if priority_name not in TaskPriority.__members__:
                priority_name = "MEDIUM"
        task = await self.runtime.submit_task_async(task_type, payload, priority_name)
        return task.task_id

    async def start_dispatcher(self) -> None:
        await self.runtime.start_dispatcher()

    def stop(self) -> None:
        self.runtime.stop()


class NexusMicroserviceBridge:
    """Explicitly unavailable bridge instead of a no-op pretending to call services."""

    def __init__(self):
        self.closed = False

    async def call(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("No real microservice connector is registered for this operation")

    async def close(self) -> None:
        self.closed = True
