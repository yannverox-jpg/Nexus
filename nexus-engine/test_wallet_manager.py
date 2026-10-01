import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from wallet_manager import NexusWalletManager, get_wallet_info

class TestWalletManager(unittest.TestCase):

    def test_nexus_wallet_manager_init(self):
        manager = NexusWalletManager()
        self.assertIsNotNone(manager.get_public_address())
        self.assertEqual(len(manager.get_public_address()), 44)

    @patch("wallet_manager.Client")
    def test_get_sol_balance(self, mock_client_cls):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.value = 2_000_000_000 # 2 SOL
        mock_client.get_balance.return_value = mock_response
        mock_client_cls.return_value = mock_client

        manager = NexusWalletManager()
        manager.rpc_client = mock_client

        balance = manager.get_sol_balance()
        self.assertEqual(balance, 2.0)

    @patch("wallet_manager.wallet_manager")
    def test_get_wallet_info(self, mock_wallet_mgr):
        mock_wallet_mgr.get_public_address.return_value = "MockedPublicAddress12345678901234567890123"
        mock_wallet_mgr.get_sol_balance.return_value = 1.5

        info = get_wallet_info()
        self.assertEqual(info["public_address"], "MockedPublicAddress12345678901234567890123")
        self.assertEqual(info["sol_balance"], 1.5)

if __name__ == "__main__":
    unittest.main()
