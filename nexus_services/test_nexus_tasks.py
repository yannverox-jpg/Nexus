import unittest
import asyncio
from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from web3_escrow_billing import NexusWeb3EscrowBilling
from nexus_services.legacy_runtime_adapter import NexusOrchestrator

class TestNexusServices(unittest.IsolatedAsyncioTestCase):

    async def test_auto_task_generator(self):
        orchestrator = NexusOrchestrator()
        engine = NexusAutoTaskEngine(orchestrator)
        executor_names = {executor.name for executor in orchestrator.runtime.executors}
        self.assertTrue({
            "CAPABILITY_ASSESSMENT",
            "WORKFLOW_PLAN_REVIEW",
            "PLATFORM_ACCOUNT_RECONCILIATION",
        }.issubset(executor_names))
        task_ids = await engine.decompose_and_enqueue_goal("Test Goal", {"budget_usdc": 10.0, "provider_address": "0x123"})
        self.assertEqual(len(task_ids), 3)
        tasks = orchestrator.runtime.operational_journal.list_tasks(limit=10)
        task_types = {task.task_type for task in tasks}
        self.assertIn("CAPABILITY_ASSESSMENT", task_types)
        self.assertIn("WORKFLOW_PLAN_REVIEW", task_types)
        self.assertIn("PLATFORM_ACCOUNT_RECONCILIATION", task_types)
        self.assertNotIn("WEB3_EXECUTION", task_types)
        self.assertNotIn("LOCK_ESCROW_FUNDS", {task.payload.get("action") for task in tasks})

    def test_service_catalog_registry(self):
        catalog = ServiceCatalogRegistry()
        service = catalog.get_service("CONTRACT_VERIFIER")
        self.assertIsNotNone(service)
        self.assertEqual(service["cost_per_call_usdc"], 0.5)

        catalog.register_service("NEW_SERVICE", "https://api.example.com", 1.0)
        new_svc = catalog.get_service("NEW_SERVICE")
        self.assertIsNotNone(new_svc)
        self.assertEqual(new_svc["cost_per_call_usdc"], 1.0)

    async def test_escrow_cannot_custody_or_transfer_funds(self):
        escrow = NexusWeb3EscrowBilling()
        with self.assertRaises(PermissionError):
            escrow.create_escrow_lock("escrow_1", "external-client", "external-provider", 10.0)
        with self.assertRaises(PermissionError):
            await escrow.release_escrow_payment(
                "escrow_1", "token-reference", "not-used", {"is_valid": True}
            )


if __name__ == "__main__":
    unittest.main()
