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

from cryptography.fernet import Fernet, InvalidToken
from web3 import Web3

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
    """Real wallet address generation; transfer execution remains fail-closed."""

    def __init__(self, evm_rpc_url: str = ""):
        self.evm_rpc_url = evm_rpc_url or os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
        self.web3 = Web3(Web3.HTTPProvider(self.evm_rpc_url, request_kwargs={"timeout": 10}))

    @staticmethod
    def _fernet() -> Fernet:
        key = os.getenv("NEXUS_WALLET_ENCRYPTION_KEY", "").strip()
        if not key:
            raise RuntimeError("NEXUS_WALLET_ENCRYPTION_KEY is required to encrypt wallet keys")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("NEXUS_WALLET_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def generate_encrypted_keypair(self) -> Dict[str, str]:
        account = self.web3.eth.account.create()
        encrypted = self._fernet().encrypt(bytes.fromhex(account.key.hex().removeprefix("0x")))
        return {
            "address": account.address,
            "encrypted_private_key": encrypted.decode("ascii"),
        }

    async def transfer_stablecoin(
        self, encrypted_private_key: str, to_address: str,
        token_contract_address: str, amount: float,
    ) -> Dict[str, Any]:
        # Do not mimic a transfer or broadcast a financial transaction without
        # transaction-scoped human approval, limits, idempotency and receipt checks.
        raise PermissionError(
            "Real transfers are disabled until transaction approval and on-chain receipt verification are implemented"
        )


class NexusMicroserviceBridge:
    """Explicitly unavailable bridge instead of a no-op pretending to call services."""

    def __init__(self):
        self.closed = False

    async def call(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("No real microservice connector is registered for this operation")

    async def close(self) -> None:
        self.closed = True
