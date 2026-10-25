import os
import tempfile
import unittest
from unittest.mock import patch

from nexus_services.multi_agent_orchestrator import coordinate_advisors
from nexus_services.task_persistence_db import NexusDatabaseManager


class MultiAgentCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_three_providers_are_called_and_outcome_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = NexusDatabaseManager(db_path=os.path.join(tmp, "nexus.db"))

            captured_systems = {}
            def fake_complete(provider_id):
                def complete(prompt, *, system="", google_search=False):
                    captured_systems[provider_id] = system
                    return {
                        "provider": provider_id,
                        "model": "test-model",
                        "status": "ADVISORY",
                        "execution_mode": "REAL",
                        "can_execute_actions": False,
                        "text": f"review from {provider_id}",
                    }
                return complete

            with patch.dict(
                "nexus_services.multi_agent_orchestrator.CONNECTORS",
                {
                    "codex_gpt": type("C", (), {"complete": staticmethod(fake_complete("codex_gpt"))})(),
                    "gemini": type("C", (), {"complete": staticmethod(fake_complete("gemini"))})(),
                    "claude": type("C", (), {"complete": staticmethod(fake_complete("claude"))})(),
                },
            ):
                result = await coordinate_advisors(
                    "Review runtime contracts", domain="microservices",
                    db_manager=db, readiness_pct=25.0,
                    additional_context="persistent constraint: no Nexus-owned wallet",
                )

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(len(result["providers_available"]), 3)
            self.assertTrue(result["persisted"])
            self.assertEqual(result["action_execution"], "NOT_PERFORMED")
            for provider_id in ("codex_gpt", "gemini", "claude"):
                self.assertIn("persistent constraint: no Nexus-owned wallet", captured_systems[provider_id])
            rows = db.get_recent_ai_decisions(limit=10)
            self.assertTrue(any(row.get("decision_id") == result["run_id"] for row in rows))

    async def test_missing_provider_is_reported_not_fabricated_as_success(self):
        def good(prompt, *, system="", google_search=False):
            return {"status": "ADVISORY", "text": "review", "can_execute_actions": False}

        def unavailable(prompt, *, system="", google_search=False):
            raise RuntimeError("provider not configured")

        with patch.dict(
            "nexus_services.multi_agent_orchestrator.CONNECTORS",
            {
                "codex_gpt": type("C", (), {"complete": staticmethod(good)})(),
                "gemini": type("C", (), {"complete": staticmethod(unavailable)})(),
                "claude": type("C", (), {"complete": staticmethod(good)})(),
            },
        ):
            result = await coordinate_advisors("Review this")

        self.assertEqual(result["status"], "PARTIAL")
        self.assertNotIn("gemini", result["providers_available"])
        self.assertEqual(result["action_execution"], "NOT_PERFORMED")


if __name__ == "__main__":
    unittest.main()
