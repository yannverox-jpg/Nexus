import unittest

from nexus_services.stablecoin_liquidation_engine import NexusStablecoinLiquidationEngine


class TestDisabledStablecoinLiquidationEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = NexusStablecoinLiquidationEngine()

    async def test_swap_is_disabled_without_nexus_wallet(self):
        with self.assertRaises(PermissionError):
            await self.engine.execute_automated_swap(
                from_token_contract="token-a",
                to_token_contract="token-b",
                amount=100,
            )

    def test_vault_withdrawal_is_disabled(self):
        with self.assertRaises(PermissionError):
            self.engine.stage_funds_for_human_withdrawal(
                available_balance_usdc=200,
            )


if __name__ == "__main__":
    unittest.main()
