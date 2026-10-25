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


class NexusWeb3WalletManager:
    """Deprecated compatibility shim; Nexus does not own or generate wallets.

    Legacy escrow code may still import this name, but no keys, addresses, or
    balances are created or managed here. External platform accounts and the
    user's prepaid Visa remain outside Nexus custody.
    """

    def __init__(self, evm_rpc_url: str = ""):
        self.evm_rpc_url = ""

    def generate_encrypted_keypair(self) -> Dict[str, str]:
        raise RuntimeError(
            "Nexus does not own a wallet. Register external platform accounts instead."
        )

    async def transfer_stablecoin(
        self, encrypted_private_key: str, to_address: str,
        token_contract_address: str, amount: float,
    ) -> Dict[str, Any]:
        raise PermissionError(
            "Nexus does not custody funds or execute wallet transfers; use the external platform payout flow."
        )


class NexusMicroserviceBridge:
    """Explicitly unavailable bridge instead of a no-op pretending to call services."""

    def __init__(self):
        self.closed = False

    async def call(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("No real microservice connector is registered for this operation")

    async def close(self) -> None:
        self.closed = True
