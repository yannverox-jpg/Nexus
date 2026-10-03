import unittest
import asyncio
from industrial_async_pipeline import HighThroughputAsyncEngine, CircuitState

class TestIndustrialAsyncPipeline(unittest.IsolatedAsyncioTestCase):

    async def test_idempotency_and_dlq_routing(self):
        engine = HighThroughputAsyncEngine(worker_count=2)
        workers = await engine.start_system()

        # Ingest first event
        await engine.ingest_webhook({"event_id": "EVT-TEST-1", "simulate_failure": False})
        # Ingest duplicate event
        await engine.ingest_webhook({"event_id": "EVT-TEST-1", "simulate_failure": False})
        # Ingest failing event
        await engine.ingest_webhook({"event_id": "EVT-TEST-2", "simulate_failure": True})

        await engine.ingress_queue.join()

        # Check idempotency set
        self.assertIn("EVT-TEST-1", engine.processed_event_ids)

        # Check DLQ routing
        self.assertEqual(engine.dlq_queue.qsize(), 1)
        dlq_msg = await engine.dlq_queue.get()
        self.assertEqual(dlq_msg["event_id"], "EVT-TEST-2")

        for w in workers:
            w.cancel()

if __name__ == "__main__":
    unittest.main()
