"""Regression tests for Nexus's non-custodial financial architecture."""

import tempfile
import unittest
from pathlib import Path

from nexus_services.payout_ledger import PayoutLedger


class FinancialArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = PayoutLedger(str(Path(self.temp_dir.name) / "finance.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_platform_accounts_are_consolidated_as_external_snapshots(self):
        account = self.ledger.register_platform_account(
            platform="ExamplePlatform",
            account_reference="account-123",
            currency="EUR",
            balance="27.40",
            evidence_reference="statement-2026-10-25",
        )
        overview = self.ledger.overview()
        self.assertEqual(account["ownership"], "EXTERNAL_PLATFORM_ACCOUNT")
        self.assertEqual(overview["consolidated_platform_balances"]["EUR"], "27.40")
        self.assertFalse(overview["architecture"]["nexus_owned_wallet"])
        self.assertFalse(overview["architecture"]["funds_custodied_by_nexus"])

    def test_external_prepaid_visa_is_supported_payout_destination(self):
        destination = self.ledger.add_destination(
            provider="Prepaid Visa issuer",
            destination_type="CARD",
            label="Prepaid Visa ending 1234",
            last4="1234",
            currency="EUR",
        )
        self.assertEqual(destination["destination_type"], "CARD")
        self.assertEqual(destination["last4"], "1234")
        self.assertFalse(self.ledger.overview()["capabilities"]["card_pan_or_cvv_stored"])

    def test_nexus_wallet_destination_is_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.add_destination(
                provider="Nexus",
                destination_type="WALLET",
                label="Nexus wallet",
                currency="EUR",
            )

    def test_full_card_number_is_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.add_destination(
                provider="Prepaid Visa issuer",
                destination_type="CARD",
                label="4111 1111 1111 1111",
                last4="1234",
                currency="EUR",
            )


if __name__ == "__main__":
    unittest.main()
