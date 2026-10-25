"""Test-only doubles. Never import this module from production runtime code."""
import asyncio
import uuid
from enum import Enum
from typing import Any, Dict


class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class NexusOrchestrator:
    def __init__(self, max_agents: int = 10):
        self.max_agents = max_agents
        self.agents = {}
        self.task_queue = asyncio.Queue()

    def spawn_agent(self, agent_id: str, capability: str):
        self.agents[agent_id] = capability

    async def submit_task(self, task_type: str, payload: Dict[str, Any], priority: TaskPriority = TaskPriority.MEDIUM) -> str:
        task_id = f"test_task_{uuid.uuid4().hex[:8]}"
        await self.task_queue.put({"task_id": task_id, "task_type": task_type, "payload": payload, "priority": priority})
        return task_id

    async def start_dispatcher(self):
        while True:
            task = await self.task_queue.get()
            self.task_queue.task_done()


class NexusWeb3WalletManager:
    def __init__(self, evm_rpc_url: str = ""):
        self.evm_rpc_url = evm_rpc_url

    async def transfer_stablecoin(self, encrypted_private_key: str, to_address: str, token_contract_address: str, amount: float) -> Dict[str, Any]:
        return {"status": "TEST_ONLY", "tx_hash": "test_tx", "amount": amount, "to": to_address}

    def generate_encrypted_keypair(self) -> Dict[str, str]:
        return {"address": "0x" + uuid.uuid4().hex[:40], "encrypted_private_key": "test-only-encrypted-key"}


class NexusMicroserviceBridge:
    def __init__(self):
        pass

    async def close(self):
        pass
