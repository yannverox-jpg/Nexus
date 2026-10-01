import unittest
import os
import tempfile
from fastapi.testclient import TestClient

# Use temp database for test
temp_fd, temp_db_path = tempfile.mkstemp(suffix=".db")

from task_persistence_db import NexusDatabaseManager
import nexus_api_server

# Patch db in api_server with temp db
nexus_api_server.db = NexusDatabaseManager(db_path=temp_db_path)

class TestNexusAPIServer(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(nexus_api_server.app)

    def tearDown(self):
        pass

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ONLINE")

    def test_submit_goal(self):
        payload = {
            "goal": "Test Goal API",
            "budget_usdc": 10.0,
            "provider_address": "0x12345"
        }
        response = self.client.post("/api/v1/goals/submit", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(len(data["task_ids"]), 3)

    def test_get_tasks(self):
        response = self.client.get("/api/v1/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertIn("tasks", response.json())

    def test_marketplace_services(self):
        res_list = self.client.get("/api/v1/marketplace/services")
        self.assertEqual(res_list.status_code, 200)
        self.assertIn("CONTRACT_VERIFIER", res_list.json()["services"])

        reg_payload = {
            "name": "TEST_SVC",
            "endpoint": "https://api.test.com",
            "cost_usdc": 1.5,
            "method": "POST"
        }
        res_reg = self.client.post("/api/v1/marketplace/services", json=reg_payload)
        self.assertEqual(res_reg.status_code, 200)
        self.assertEqual(res_reg.json()["status"], "REGISTERED")

    def test_generate_wallet(self):
        nexus_api_server.wallet_mgr = nexus_api_server.NexusWeb3WalletManager()
        response = self.client.post("/api/v1/wallet/generate")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "CREATED")
        self.assertTrue(data["address"].startswith("0x"))

if __name__ == "__main__":
    unittest.main()
