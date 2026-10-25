import unittest
import os
import tempfile
from task_persistence_db import NexusDatabaseManager
from dispute_resolution import NexusDisputeResolutionEngine
from web3_escrow_billing import NexusWeb3EscrowBilling

class TestNexusServicesV2(unittest.TestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db = NexusDatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_database_persistence(self):
        self.db.save_task("t1", "TYPE_A", "HIGH", "PENDING", {"key": "val"})
        tasks = self.db.get_all_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "t1")

        self.db.save_escrow("e1", "0xClient", "0xProvider", 50.0, "LOCKED")
        self.db.update_service_reputation("SERVICE_A", True, 0.2)
        self.db.update_service_reputation("SERVICE_A", False, 0.4)

    def test_dispute_resolution_never_claims_automatic_refund(self):
        dispute_engine = NexusDisputeResolutionEngine(max_retries=1)
        res1 = dispute_engine.evaluate_and_handle_failure("case-1", "Timeout", {})
        self.assertEqual(res1["action"], "RETRY")
        self.assertFalse(res1["funds_moved"])

        res2 = dispute_engine.evaluate_and_handle_failure("case-1", "Quality fail", {})
        self.assertEqual(res2["action"], "REVIEW_REQUIRED")
        self.assertEqual(res2["refund_status"], "NOT_EXECUTED")
        self.assertFalse(res2["funds_moved"])


if __name__ == "__main__":
    unittest.main()
