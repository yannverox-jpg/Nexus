import unittest
import os
import tempfile
from fastapi.testclient import TestClient

temp_fd, temp_db_path = tempfile.mkstemp(suffix=".db")

from task_persistence_db import NexusDatabaseManager
import nexus_api_server

nexus_api_server.db = NexusDatabaseManager(db_path=temp_db_path)

class TestBrokerDashboard(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(nexus_api_server.app)

    def test_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "online")
        self.assertEqual(res.json()["department"], "TRADING_AND_PLATFORM")

    def test_broker_account_endpoint(self):
        res = self.client.get("/api/v1/broker/account")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("balance", data)
        self.assertIn("equity", data)
        self.assertIn("margin", data)

    def test_broker_positions_endpoint(self):
        res = self.client.get("/api/v1/broker/positions")
        self.assertEqual(res.status_code, 200)
        self.assertIn("positions", res.json())

    def test_broker_withdraw_endpoint(self):
        payload = {"to_address": "0xPlatformVaultAddress", "amount_usd": 150.0}
        res = self.client.post("/api/v1/broker/withdraw", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "REQUESTED")
        self.assertEqual(data["amount_usd"], 150.0)

    def test_dashboard_static_serving(self):
        res = self.client.get("/dashboard/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("NEXUS PILOT DASHBOARD", res.text)

if __name__ == "__main__":
    unittest.main()
