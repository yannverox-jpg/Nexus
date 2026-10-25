import unittest
from fastapi.testclient import TestClient

from nexus_services import nexus_api_server


class TestRuntimeDashboard(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(nexus_api_server.app)

    def test_health_check_does_not_expose_broker_account_state(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "online")
        self.assertNotIn("broker_connected", payload)
        self.assertNotIn("login", payload)
        self.assertNotIn("balance", payload)

    def test_broker_routes_are_removed(self):
        route_paths = {
            getattr(route, "path", "")
            for route in nexus_api_server.app.routes
        }
        self.assertNotIn("/api/v1/broker/account", route_paths)
        self.assertNotIn("/api/v1/broker/positions", route_paths)
        self.assertNotIn("/api/v1/broker/history", route_paths)
        self.assertNotIn("/api/v1/broker/withdraw", route_paths)

    def test_dashboard_is_read_only_and_does_not_call_broker_endpoints(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nexus Runtime Status", response.text)
        self.assertNotIn("/api/v1/broker/account", response.text)
        self.assertNotIn("/api/v1/broker/positions", response.text)
        self.assertNotIn("/api/v1/broker/withdraw", response.text)
        self.assertNotIn("MetaTrader5", response.text)


if __name__ == "__main__":
    unittest.main()
