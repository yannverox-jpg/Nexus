import sys
import os
import unittest
import asyncio

# Ensure nexus-engine directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from task_manager import TaskSpecification, SubAgentWorker, NexusOrchestrator
from config import Config

class TestTaskManager(unittest.IsolatedAsyncioTestCase):

    def test_task_specification_default(self):
        spec = TaskSpecification(
            service_type="data_scraping",
            estimated_payout_usdc=10.0,
            estimated_cost_usdc=2.0,
            payload={"url": "https://example.com"}
        )
        self.assertTrue(spec.task_id.startswith("task_"))
        self.assertEqual(spec.service_type, "data_scraping")
        self.assertEqual(spec.estimated_payout_usdc, 10.0)
        self.assertEqual(spec.estimated_cost_usdc, 2.0)

    def test_evaluate_roi(self):
        orchestrator = NexusOrchestrator()

        # High ROI task (10 / 2 = 5 >= 1.5)
        spec_good = TaskSpecification(
            service_type="test",
            estimated_payout_usdc=10.0,
            estimated_cost_usdc=2.0,
            payload={}
        )
        self.assertTrue(orchestrator.evaluate_roi(spec_good))

        # Low ROI task (10 / 8 = 1.25 < 1.5)
        spec_bad = TaskSpecification(
            service_type="test",
            estimated_payout_usdc=10.0,
            estimated_cost_usdc=8.0,
            payload={}
        )
        self.assertFalse(orchestrator.evaluate_roi(spec_bad))

        # Zero cost task
        spec_zero_cost = TaskSpecification(
            service_type="test",
            estimated_payout_usdc=10.0,
            estimated_cost_usdc=0.0,
            payload={}
        )
        self.assertTrue(orchestrator.evaluate_roi(spec_zero_cost))

    async def test_sub_agent_worker_run(self):
        spec = TaskSpecification(
            service_type="parsing",
            estimated_payout_usdc=5.0,
            estimated_cost_usdc=1.0,
            payload={"key": "value"}
        )
        worker = SubAgentWorker("agent_test_1", spec)
        res = await worker.run()

        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["task_id"], spec.task_id)
        self.assertEqual(res["agent_id"], "agent_test_1")
        self.assertEqual(res["net_profit_usdc"], 4.0)
        self.assertTrue(res["output"]["processed"])
        self.assertEqual(res["output"]["type"], "parsing")

    async def test_dispatch_task(self):
        orchestrator = NexusOrchestrator()
        spec = TaskSpecification(
            service_type="api_call",
            estimated_payout_usdc=20.0,
            estimated_cost_usdc=5.0,
            payload={"param": 123}
        )
        agent_id = await orchestrator.dispatch_task(spec)
        self.assertIsNotNone(agent_id)
        self.assertIn(agent_id, orchestrator.active_workers)

        # Wait for the task to finish execution and callback to execute
        task = orchestrator.active_workers[agent_id]
        await task
        # Give asyncio event loop a small tick for done_callback
        await asyncio.sleep(0.1)

        self.assertNotIn(agent_id, orchestrator.active_workers)
        self.assertEqual(orchestrator.total_net_profit_usdc, 15.0)

if __name__ == "__main__":
    unittest.main()
