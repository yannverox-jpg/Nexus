import os
import tempfile
import unittest

from nexus_services.memory_store import ConversationMemory


class ConversationMemoryTests(unittest.TestCase):
    def test_history_survives_store_recreation_and_redacts_common_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "persistent-memory.db")
            first = ConversationMemory(path)
            first.add_message(
                "conversation-1", "user",
                "Review this config sk-abcdefghijklmnopqrstuvwxyz012345 Bearer abcdefghijklmnop",
                "codex_gpt", "test-model",
            )
            first.add_message(
                "conversation-1", "assistant", "I found one configuration issue.",
                "codex_gpt", "test-model",
            )
            first.add_message(
                "conversation-1", "user", "Card 4111 1111 1111 1111 CVV=123",
                "codex_gpt", "test-model",
            )

            reopened = ConversationMemory(path)
            messages = reopened.recent_messages("conversation-1")
            self.assertEqual([item["role"] for item in messages], ["user", "assistant", "user"])
            self.assertIn("[REDACTED]", messages[0]["content"])
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz012345", messages[0]["content"])
            self.assertNotIn("Bearer abcdefghijklmnop", messages[0]["content"])
            self.assertEqual(messages[1]["content"], "I found one configuration issue.")
            self.assertNotIn("4111 1111 1111 1111", messages[2]["content"])
            self.assertNotIn("CVV=123", messages[2]["content"])
            self.assertIn("[REDACTED]", messages[2]["content"])

    def test_long_term_facts_survive_reopen_and_reject_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "memory.db")
            first = ConversationMemory(path)
            first.set_fact(
                "wallet_model",
                "Nexus ne possède pas de portefeuille; les soldes restent sur les plateformes.",
                category="constraint",
            )
            reopened = ConversationMemory(path)
            facts = reopened.list_facts(category="constraint")
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0]["fact_key"], "wallet_model")
            self.assertIn("ne possède pas", facts[0]["content"])
            with self.assertRaises(ValueError):
                reopened.set_fact("bad_secret", "sk-abcdefghijklmnopqrstuvwxyz012345")
            self.assertTrue(reopened.delete_fact("wallet_model"))
            self.assertEqual(reopened.list_facts(), [])


if __name__ == "__main__":
    unittest.main()
