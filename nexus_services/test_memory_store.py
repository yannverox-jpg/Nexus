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

            reopened = ConversationMemory(path)
            messages = reopened.recent_messages("conversation-1")
            self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
            self.assertIn("[REDACTED]", messages[0]["content"])
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz012345", messages[0]["content"])
            self.assertNotIn("Bearer abcdefghijklmnop", messages[0]["content"])
            self.assertEqual(messages[1]["content"], "I found one configuration issue.")


if __name__ == "__main__":
    unittest.main()
