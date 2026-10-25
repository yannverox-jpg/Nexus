import unittest

import nexus_services.nexus_api_server as nexus_api_server


class TestNexusAPIServer(unittest.TestCase):
    def test_health_is_liveness_only(self):
        from fastapi.testclient import TestClient
        client = TestClient(nexus_api_server.app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "online")
        self.assertNotIn("wallet", response.json())

    def test_proprietary_wallet_and_treasury_routes_are_absent(self):
        paths = {
            getattr(route, "path", "")
            for route in nexus_api_server.app.routes
        }
        self.assertNotIn("/api/v1/wallet/generate", paths)
        self.assertNotIn("/api/v1/treasury/withdraw", paths)

    def test_legacy_adapter_has_no_wallet_manager(self):
        import nexus_services.legacy_runtime_adapter as adapter
        self.assertFalse(hasattr(adapter, "NexusWeb3WalletManager"))


if __name__ == "__main__":
    unittest.main()
