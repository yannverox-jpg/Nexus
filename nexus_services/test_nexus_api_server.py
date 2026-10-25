import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import nexus_services.nexus_api_server as nexus_api_server
from nexus_services.memory_store import ConversationMemory


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

    def test_identity_chat_memory_and_code_change_routes_are_registered(self):
        paths = {getattr(route, "path", "") for route in nexus_api_server.app.routes}
        for path in (
            "/api/v1/identity", "/api/v1/capabilities", "/api/v1/providers",
            "/api/v1/ghost/chat/{agent_name}", "/api/v1/memory/facts",
            "/api/v1/memory/conversations/{conversation_id}",
            "/api/v1/code-change/status", "/api/v1/code-change/proposals",
        ):
            self.assertIn(path, paths)

    def test_chat_persists_redacted_history_with_configured_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ConversationMemory(os.path.join(tmp, "chat.db"))
            original_memory = nexus_api_server.conversation_memory
            nexus_api_server.conversation_memory = memory
            connector = type("Connector", (), {
                "api_key_env": "TEST_PROVIDER_KEY",
                "model_env": "TEST_PROVIDER_MODEL",
                "default_model": "test-model",
                "status": staticmethod(lambda: {"connector_available": True}),
                "complete": staticmethod(lambda prompt, **kwargs: {
                    "provider": "codex_gpt", "model": "test-model",
                    "status": "ADVISORY", "text": "Réponse test",
                    "can_execute_actions": False,
                }),
            })()
            try:
                with patch.dict(os.environ, {"NEXUS_API_BEARER_TOKEN": "test-token", "TEST_PROVIDER_MODEL": "test-model"}):
                    with patch.dict(nexus_api_server.CONNECTORS, {"codex_gpt": connector}):
                        client = TestClient(nexus_api_server.app)
                        response = client.post(
                            "/api/v1/ghost/chat/gpt",
                            headers={"Authorization": "Bearer test-token"},
                            json={"message": "Bonjour", "conversation_id": "test-conversation", "domain": "general"},
                        )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["memory_persisted"])
                messages = memory.recent_messages("test-conversation")
                self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
                self.assertEqual(messages[1]["content"], "Réponse test")
            finally:
                nexus_api_server.conversation_memory = original_memory


if __name__ == "__main__":
    unittest.main()
