import unittest
import os
import tempfile
from database.event_sourcing_outbox import EnterpriseEventEngine

class TestEventSourcingOutbox(unittest.TestCase):

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.engine = EnterpriseEventEngine(db_path=self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_atomic_commit_and_outbox_processing(self):
        self.engine.commit_transaction_with_outbox(
            aggregate_id="AGG-TEST-1",
            event_type="ORDER_PLACED",
            event_data={"symbol": "EURUSD", "volume": 0.1, "simulate_network_drop": False}
        )

        conn = self.engine._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM event_store WHERE aggregate_id = 'AGG-TEST-1'")
        events = cursor.fetchall()
        self.assertEqual(len(events), 1)

        cursor.execute("SELECT * FROM outbox_queue WHERE status = 'PENDING'")
        pending_outbox = cursor.fetchall()
        self.assertEqual(len(pending_outbox), 1)
        conn.close()

        self.engine.process_outbox_batch()

        conn = self.engine._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM outbox_queue WHERE status = 'PROCESSED'")
        processed_outbox = cursor.fetchall()
        self.assertEqual(len(processed_outbox), 1)
        conn.close()

if __name__ == "__main__":
    unittest.main()
