import unittest
import os
import tempfile
from stablecoin_liquidation_engine import NexusStablecoinLiquidationEngine
from task_persistence_db import NexusDatabaseManager
from module_mocks import NexusWeb3WalletManager

class TestStablecoinLiquidationEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db = NexusDatabaseManager(db_path=self.temp_db_path)
        self.wallet_mgr = NexusWeb3WalletManager()
        self.engine = NexusStablecoinLiquidationEngine(self.wallet_mgr, self.db)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    async def test_execute_automated_swap(self):
        swap_res = await self.engine.execute_automated_swap(
            encrypted_private_key="enc_key",
            from_token_contract="0xUSDT",
            to_token_contract="0xUSDC",
            amount=100.0
        )
        self.assertEqual(swap_res["status"], "COMPLETED")
        self.assertEqual(swap_res["amount_swapped"], 100.0)
        self.assertTrue(swap_res["tx_hash"].startswith("0x"))

    def test_stage_funds_for_human_withdrawal_hold(self):
        res = self.engine.stage_funds_for_human_withdrawal(
            vault_address="0xVaultAddress",
            available_balance_usdc=40.0,
            reserve_threshold_usdc=50.0
        )
        self.assertEqual(res["status"], "HOLD")

    def test_stage_funds_for_human_withdrawal_ready(self):
        res = self.engine.stage_funds_for_human_withdrawal(
            vault_address="0xVaultAddress",
            available_balance_usdc=200.0,
            reserve_threshold_usdc=50.0
        )
        self.assertEqual(res["status"], "READY_FOR_WITHDRAWAL")
        self.assertEqual(res["withdrawable_amount_usdc"], 150.0)
        self.assertEqual(res["retained_operational_reserve"], 50.0)

if __name__ == "__main__":
    unittest.main()
