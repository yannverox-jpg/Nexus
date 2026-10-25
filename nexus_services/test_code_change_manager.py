import unittest
from unittest.mock import patch

from nexus_services.code_change_manager import CodeChangeManager, code_change_status


class CodeChangeManagerTests(unittest.TestCase):
    def test_code_change_is_draft_pr_only_and_requires_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            status = code_change_status()
        self.assertFalse(status["configured"])
        self.assertFalse(status["live_self_editing"])
        self.assertTrue(status["requires_ci_and_human_review"])

    def test_path_scope_rejects_secrets_and_repository_metadata(self):
        for path in (".env", ".env.example", "../README.md", "nexus_services/../../secret.py", "requirements.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                CodeChangeManager._validate_path(path)
        self.assertEqual(CodeChangeManager._validate_path("nexus_services/new_module.py"), "nexus_services/new_module.py")

    def test_content_scanner_rejects_realistic_secrets(self):
        with self.assertRaises(ValueError):
            CodeChangeManager._validate_content('API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"')
        with self.assertRaises(ValueError):
            CodeChangeManager._validate_content("card=4111 1111 1111 1111")
        self.assertEqual(CodeChangeManager._validate_content("def hello():\n    return 'safe'\n"), "def hello():\n    return 'safe'\n")


if __name__ == "__main__":
    unittest.main()
