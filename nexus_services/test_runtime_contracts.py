import asyncio
import json
import os
import sqlite3
import tempfile
import unittest

from nexus_services.runtime_contracts import (
    EventStatus,
    NexusRuntime,
    SQLiteEventRepository,
    TaskPersistenceAdapter,
    TaskRecord,
    TaskStatus,
)
from nexus_services.task_persistence_db import NexusDatabaseManager
from orchestrator import RobustOrchestrator


class RuntimeContractsTest(unittest.IsolatedAsyncioTestCase):
    def test_task_records_follow_canonical_states(self):
        task = TaskRecord(
            task_id="task-1",
            task_type="EXECUTION",
            status=TaskStatus.PLANNED,
            payload={"symbol": "BTCUSD"},
        )
        self.assertEqual(task.status, TaskStatus.PLANNED)
        self.assertEqual(task.task_type, "EXECUTION")

    async def test_default_runtime_uses_canonical_journal_and_fails_closed_without_executor(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            journal = __import__(
                "nexus_services.runtime_contracts", fromlist=["OperationalJournal"]
            ).OperationalJournal(os.path.join(tmp_dir, "runtime.db"))
            runtime = NexusRuntime(operational_journal=journal, name="default-runtime")
            boot_result = runtime.boot()
            self.assertEqual(boot_result["status"], "BOOT_COMPLETED")
            self.assertIs(runtime.initialize_orchestrator().journal, journal)

            task = await runtime.submit_task_async("UNSUPPORTED_ACTION", {"action": "must-not-fake"})
            self.assertEqual(task.status, TaskStatus.QUEUED)
            self.assertIsNotNone(journal.get_task(task.task_id))

            await runtime.start_dispatcher()
            try:
                for _ in range(100):
                    persisted = journal.get_task(task.task_id)
                    if persisted is not None and persisted.status == TaskStatus.FAILED:
                        break
                    await asyncio.sleep(0.02)
                else:
                    self.fail("Task without a registered executor did not fail closed")
            finally:
                await runtime.stop_dispatcher()

            persisted = journal.get_task(task.task_id)
            self.assertEqual(persisted.status, TaskStatus.FAILED)
            self.assertIn("No real executor is registered", persisted.error)
            self.assertNotEqual(persisted.status, TaskStatus.EXECUTED)
            self.assertNotEqual(persisted.status, TaskStatus.VERIFIED)

    async def test_execution_is_persisted_and_emits_observed_transition_events(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            task_db_path = os.path.join(tmp_dir, "nexus_tasks_state.db")
            event_db_path = os.path.join(tmp_dir, "nexus_runtime_events.db")
            db_manager = NexusDatabaseManager(db_path=task_db_path)
            task_repository = TaskPersistenceAdapter(db_manager)
            event_repository = SQLiteEventRepository(db_path=event_db_path)
            orchestrator = RobustOrchestrator(db_manager=task_repository, max_retries=1)
            worker = orchestrator.workers["EXECUTION"]
            original_execute_task = worker.execute_task
            worker_calls = []
            worker_statuses = []
            worker_results = []
            worker_finished = asyncio.Event()

            async def track_execution(task_data):
                worker_calls.append(task_data["task_id"])
                persisted = next(
                    row for row in db_manager.get_all_tasks()
                    if row["task_id"] == task_data["task_id"]
                )
                worker_statuses.append(persisted["status"])
                result = await original_execute_task(task_data)
                worker_results.append(result)
                worker_finished.set()
                return result

            worker.execute_task = track_execution
            runtime = NexusRuntime(
                task_repository=task_repository,
                event_repository=event_repository,
                name="NexusRuntime",
                legacy_orchestrator=orchestrator,
            )
            runtime.boot()

            task = await runtime.submit_task_async(
                "EXECUTION", {"symbol": "BTCUSD"}, "HIGH"
            )
            self.assertEqual(task.status, TaskStatus.QUEUED)
            queued_row = next(
                row for row in db_manager.get_all_tasks()
                if row["task_id"] == task.task_id
            )
            self.assertEqual(queued_row["status"], "ENQUEUED")

            loop_task = asyncio.create_task(orchestrator.start_loop())
            try:
                await asyncio.wait_for(worker_finished.wait(), timeout=5)
                for _ in range(100):
                    persisted_rows = db_manager.get_all_tasks()
                    persisted = next(
                        row for row in persisted_rows
                        if row["task_id"] == task.task_id
                    )
                    if persisted["status"] == "COMPLETED":
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("EXECUTION task was not persisted as COMPLETED")
            finally:
                orchestrator.stop()
                await asyncio.wait_for(loop_task, timeout=2)

            self.assertEqual(worker_calls, [task.task_id])
            self.assertEqual(worker_statuses, ["PROCESSING"])
            self.assertEqual(worker_results[0]["status"], "SIMULATED")
            self.assertEqual(
                worker_results[0]["result"]["execution_mode"], "SIMULATED"
            )

            with sqlite3.connect(task_db_path) as connection:
                row = connection.execute(
                    "SELECT task_type, status, payload, result FROM tasks WHERE task_id = ?",
                    (task.task_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "EXECUTION")
            self.assertEqual(row[1], "COMPLETED")
            self.assertEqual(json.loads(row[2]), {"symbol": "BTCUSD"})
            self.assertEqual(json.loads(row[3])["execution_mode"], "SIMULATED")

            persisted_task = task_repository.get_task(task.task_id)
            self.assertEqual(persisted_task.status, TaskStatus.EXECUTED)
            self.assertEqual(persisted_task.result["execution_mode"], "SIMULATED")
            self.assertNotEqual(persisted_task.status, TaskStatus.VERIFIED)

            events = list(reversed(event_repository.list_events()))
            task_events = [event for event in events if event.task_id == task.task_id]
            statuses = [event.status for event in task_events]
            self.assertIn(EventStatus.TASK_QUEUED, statuses)
            self.assertIn(EventStatus.TASK_STARTED, statuses)
            self.assertIn(EventStatus.EXECUTION_COMPLETED, statuses)
            self.assertLess(
                statuses.index(EventStatus.TASK_QUEUED),
                statuses.index(EventStatus.TASK_STARTED),
            )
            self.assertLess(
                statuses.index(EventStatus.TASK_STARTED),
                statuses.index(EventStatus.EXECUTION_COMPLETED),
            )
            self.assertFalse(
                any(event.status == EventStatus.VERIFICATION_PASSED for event in task_events)
            )
            self.assertEqual(
                task_events[statuses.index(EventStatus.EXECUTION_COMPLETED)].result[
                    "execution_mode"
                ],
                "SIMULATED",
            )


if __name__ == "__main__":
    unittest.main()
