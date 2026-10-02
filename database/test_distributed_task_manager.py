import unittest
import os
import time
import tempfile
from database.distributed_task_manager import DistributedTaskManager

class TestDistributedTaskManager(unittest.TestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.manager = DistributedTaskManager(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_lease_acquisition_and_completion(self):
        self.manager.create_task("T-100", {"action": "RUN"})

        task = self.manager.acquire_task_lease("Worker-A", lease_duration=5)
        self.assertIsNotNone(task)
        self.assertEqual(task["task_id"], "T-100")

        # Second worker cannot acquire valid lease
        task_b = self.manager.acquire_task_lease("Worker-B", lease_duration=5)
        self.assertIsNone(task_b)

        # Heartbeat extension
        hb_res = self.manager.heartbeat("T-100", "Worker-A", extension=10)
        self.assertTrue(hb_res)

        # Complete task
        self.manager.complete_task("T-100", "Worker-A")

    def test_expired_lease_recovery(self):
        self.manager.create_task("T-200", {"action": "CRASH_RECOVERY_TEST"})

        # Worker A acquires lease for 0.1s
        task = self.manager.acquire_task_lease("Worker-A", lease_duration=0.1)
        self.assertIsNotNone(task)

        # Wait for lease to expire
        time.sleep(0.15)

        # Worker B acquires expired lease
        task_b = self.manager.acquire_task_lease("Worker-B", lease_duration=5)
        self.assertIsNotNone(task_b)
        self.assertEqual(task_b["task_id"], "T-200")

if __name__ == "__main__":
    unittest.main()
