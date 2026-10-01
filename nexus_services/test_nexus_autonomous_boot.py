import unittest
import os
import tempfile
from auto_task_generator import NexusAutoTaskEngine
from task_persistence_db import NexusDatabaseManager
from nexus_autonomous_boot import NexusM2MProtocolHandler, NexusAutonomousBootDaemon
from module_mocks import NexusOrchestrator

class TestNexusAutonomousBoot(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db = NexusDatabaseManager(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_m2m_protocol_handler(self):
        handler = NexusM2MProtocolHandler(agent_id="AGENT_TEST")
        handshake = handler.create_m2m_handshake("https://ai.example.com", "DATA_FEED", 5.0)

        self.assertEqual(handshake["protocol_version"], "NEXUS-M2M-v1")
        self.assertEqual(handshake["sender_agent"], "AGENT_TEST")
        self.assertEqual(handshake["payload"]["offer_amount_usdc"], 5.0)

        valid_res = {"protocol_version": "NEXUS-M2M-v1", "status": "ACCEPTED"}
        invalid_res = {"protocol_version": "NEXUS-M2M-v1", "status": "REJECTED"}

        self.assertTrue(handler.parse_and_validate_m2m_response(valid_res))
        self.assertFalse(handler.parse_and_validate_m2m_response(invalid_res))

    async def test_autonomous_boot_sequence(self):
        orchestrator = NexusOrchestrator()
        auto_engine = NexusAutoTaskEngine(orchestrator)
        daemon = NexusAutonomousBootDaemon(auto_engine, self.db)

        await daemon.boot_sequence()
        tasks = self.db.get_all_tasks()
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0]["task_type"], "BOOTSTRAP_GOAL")

if __name__ == "__main__":
    unittest.main()
