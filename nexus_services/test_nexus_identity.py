import unittest

from nexus_services.nexus_identity import get_identity, get_capability_status
from nexus_services.agent_roles import build_agent_system_context


class NexusIdentityTests(unittest.TestCase):
    def test_identity_declares_non_custodial_finance_and_real_constraints(self):
        identity = get_identity()
        self.assertEqual(identity["name"], "Nexus")
        self.assertFalse(identity["financial_architecture"]["owns_wallet"])
        self.assertFalse(identity["financial_architecture"]["custodies_funds"])
        self.assertIn("claude", str(identity["provider_roles"]).lower())
        self.assertIn("gemini", str(identity["provider_roles"]).lower())

    def test_provider_roles_are_distinct_and_do_not_grant_execution_authority(self):
        gpt = build_agent_system_context("codex_gpt", "ghost")
        gemini = build_agent_system_context("gemini", "ghost")
        claude = build_agent_system_context("claude", "ghost")
        self.assertIn("reasoning", gpt.lower())
        self.assertIn("research", gemini.lower())
        self.assertIn("architecture", claude.lower())
        for context in (gpt, gemini, claude):
            self.assertIn("does not own a wallet", context.lower())
            self.assertIn("must pass repository review", context.lower())

    def test_capabilities_do_not_claim_automatic_self_editing_or_transfers(self):
        capabilities = get_capability_status()
        self.assertFalse(capabilities["code_adaptation"]["can_apply_changes_automatically"])
        self.assertFalse(capabilities["execution"]["financial_transfers_enabled"])
        self.assertTrue(capabilities["code_adaptation"]["requires_tests_and_human_approval"])


if __name__ == "__main__":
    unittest.main()
