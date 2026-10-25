import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from nexus_services.legacy_runtime_adapter import (
    NexusOrchestrator,
    NexusWeb3WalletManager,
    TaskPriority,
)
from nexus_services.runtime_contracts import TaskStatus


class LegacyRuntimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_historical_submit_api_uses_canonical_journal_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"NEXUS_OPERATIONAL_DB_PATH": os.path.join(tmp, "runtime.db")}):
                orchestrator = NexusOrchestrator(max_agents=2)
                orchestrator.spawn_agent("worker-a", "API_CONTRACT")
                task_id = await orchestrator.submit_task(
                    "UNREGISTERED_EXTERNAL_ACTION", {"action": "must-not-be-faked"},
                    TaskPriority.HIGH,
                )
                self.assertIsNotNone(orchestrator.runtime.operational_journal.get_task(task_id))
                await orchestrator.start_dispatcher()
                try:
                    for _ in range(150):
                        task = orchestrator.runtime.operational_journal.get_task(task_id)
                        if task and task.status == TaskStatus.FAILED:
                            break
                        await asyncio.sleep(0.02)
                    else:
                        self.fail("Task without a real executor did not fail closed")
                finally:
                    orchestrator.stop()
                task = orchestrator.runtime.operational_journal.get_task(task_id)
                self.assertEqual(task.status, TaskStatus.FAILED)
                self.assertIn("No real executor is registered", task.error)
                self.assertNotEqual(task.status, TaskStatus.EXECUTED)
                self.assertNotEqual(task.status, TaskStatus.VERIFIED)

    async def test_wallet_adapter_never_fabricates_transfer_success(self):
        wallet = NexusWeb3WalletManager(evm_rpc_url="http://127.0.0.1:1")
        with self.assertRaises(PermissionError):
            await wallet.transfer_stablecoin(
                encrypted_private_key="not-used",
                to_address="0x0000000000000000000000000000000000000001",
                token_contract_address="0x0000000000000000000000000000000000000002",
                amount=1.0,
            )


if __name__ == "__main__":
    unittest.main()
