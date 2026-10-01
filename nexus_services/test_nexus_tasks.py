import unittest
import asyncio
from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from web3_escrow_billing import NexusWeb3EscrowBilling
from module_mocks import NexusOrchestrator, NexusWeb3WalletManager

class TestNexusServices(unittest.IsolatedAsyncioTestCase):

    async def test_auto_task_generator(self):
        orchestrator = NexusOrchestrator()
        engine = NexusAutoTaskEngine(orchestrator)
        task_ids = await engine.decompose_and_enqueue_goal("Test Goal", {"budget_usdc": 10.0, "provider_address": "0x123"})
        self.assertEqual(len(task_ids), 3)

    def test_service_catalog_registry(self):
        catalog = ServiceCatalogRegistry()
        service = catalog.get_service("CONTRACT_VERIFIER")
        self.assertIsNotNone(service)
        self.assertEqual(service["cost_per_call_usdc"], 0.5)

        catalog.register_service("NEW_SERVICE", "https://api.example.com", 1.0)
        new_svc = catalog.get_service("NEW_SERVICE")
        self.assertIsNotNone(new_svc)
        self.assertEqual(new_svc["cost_per_call_usdc"], 1.0)

    async def test_web3_escrow_billing(self):
        wallet_mgr = NexusWeb3WalletManager()
        escrow = NexusWeb3EscrowBilling(wallet_mgr)

        lock = escrow.create_escrow_lock("escrow_1", "0xClient", "0xProvider", 10.0)
        self.assertEqual(lock["status"], "LOCKED")

        res_invalid = await escrow.release_escrow_payment("escrow_1", "0xToken", "enc_key", {"is_valid": False})
        self.assertEqual(res_invalid["status"], "REJECTED")

        lock2 = escrow.create_escrow_lock("escrow_2", "0xClient", "0xProvider", 20.0)
        res_valid = await escrow.release_escrow_payment("escrow_2", "0xToken", "enc_key", {"is_valid": True})
        self.assertEqual(res_valid["status"], "RELEASED")
        self.assertEqual(res_valid["amount_paid"], 20.0)

if __name__ == "__main__":
    unittest.main()
