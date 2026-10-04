import unittest
from fastapi.testclient import TestClient
import nexus_api_server

class TestWebSocketMCPProxy(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(nexus_api_server.app)

    def test_websocket_mcp_chat_gemini(self):
        with self.client.websocket_connect("/ws/v1/nexus-stream") as websocket:
            websocket.send_json({
                "target": "gemini",
                "payload": {"message": "FOMC Macro Outlook"}
            })
            data = websocket.receive_json()
            self.assertEqual(data["channel"], "GEMINI_RADAR")
            self.assertIn("response", data)

    def test_websocket_mcp_tool_calling(self):
        with self.client.websocket_connect("/ws/v1/nexus-stream") as websocket:
            websocket.send_json({
                "mcp_tool": "evaluate_readiness_status"
            })
            data = websocket.receive_json()
            self.assertEqual(data["status"], "TOOL_RESPONSE")
            self.assertEqual(data["tool"], "evaluate_readiness_status")
            self.assertEqual(data["data"]["m_global_pct"], 100.0)

if __name__ == "__main__":
    unittest.main()
