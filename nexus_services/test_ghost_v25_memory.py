import unittest
import os
import tempfile
from fastapi.testclient import TestClient

temp_fd, temp_db_path = tempfile.mkstemp(suffix=".db")

from task_persistence_db import NexusDatabaseManager
import nexus_api_server

nexus_api_server.db = NexusDatabaseManager(db_path=temp_db_path)

class TestGhostV25MemoryAndChat(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(nexus_api_server.app)

    def test_memory_and_readiness_endpoints(self):
        # Save a market event
        nexus_api_server.db.save_market_event("EVT-10", "XAUUSD", {"delta_p": 0.1}, {"spread": 0.0002}, 0.85)
        nexus_api_server.db.save_ai_decision("DEC-10", {"gemini": "ok"}, {"gpt": "ok"}, {"claude": "ok"}, 100.0)

        res_short = self.client.get("/api/v1/memory/short")
        self.assertEqual(res_short.status_code, 200)
        self.assertEqual(len(res_short.json()["market_events"]), 1)

        res_long = self.client.get("/api/v1/memory/long")
        self.assertEqual(res_long.status_code, 200)
        self.assertEqual(len(res_long.json()["ai_decisions"]), 1)

        res_readiness = self.client.get("/api/v1/readiness-status")
        self.assertEqual(res_readiness.status_code, 200)
        self.assertEqual(res_readiness.json()["m_global_pct"], 100.0)

    def test_agent_chat_channels(self):
        res_gemini = self.client.post("/api/v1/ghost/chat/gemini", json={"message": "Federal Reserve Rate Update"})
        self.assertEqual(res_gemini.status_code, 200)
        self.assertEqual(res_gemini.json()["agent"], "Gemini")

        res_gpt = self.client.post("/api/v1/ghost/chat/gpt", json={"message": "FX Matrix Signal"})
        self.assertEqual(res_gpt.status_code, 200)
        self.assertEqual(res_gpt.json()["agent"], "GPT")

        res_claude = self.client.post("/api/v1/ghost/chat/claude", json={"message": "Audit & Strategy"})
        self.assertEqual(res_claude.status_code, 200)
        self.assertEqual(res_claude.json()["agent"], "Claude")

if __name__ == "__main__":
    unittest.main()
