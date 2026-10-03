import unittest
import asyncio
import os
import tempfile
from database.memory_manager import PersistentMemoryManager
from orchestrator import RobustOrchestrator

class TestMainOrchestrator(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db_mgr = PersistentMemoryManager(db_path=self.temp_db_path)
        self.orchestrator = RobustOrchestrator(db_manager=self.db_mgr)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    async def test_orchestrator_execution(self):
        loop_task = asyncio.create_task(self.orchestrator.start_loop())

        task_id = await self.orchestrator.submit_task("ANALYSIS", {"pair": "BTCUSD"})
        await asyncio.sleep(0.3)

        saved_task = self.db_mgr.get_task(task_id)
        self.assertIsNotNone(saved_task)
        self.assertEqual(saved_task["status"], "COMPLETED")
        self.assertEqual(saved_task["result"]["analysis"], "COMPLETE")

        self.orchestrator.stop()
        await loop_task

if __name__ == "__main__":
    unittest.main()
