import os
import tempfile
import unittest

from nexus_services.operational_dashboard import (
    dashboard_overview,
    mission_detail,
    task_detail,
)
from nexus_services.runtime_contracts import OperationalJournal, RuntimeStatus, TaskStatus


class OperationalDashboardTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.journal = OperationalJournal(os.path.join(self.temp_dir.name, "journal.db"))
        self.session_id = self.journal.create_session(source="dashboard-test")
        self.journal.update_runtime_session(self.session_id, RuntimeStatus.RUNNING)
        self.mission_id = self.journal.create_mission(
            "Confirm the requested external outcome",
            session_id=self.session_id,
            metadata={"success_criteria": ["external response is accepted"]},
        )

    def tearDown(self):
        self.journal.close()
        self.temp_dir.cleanup()

    def _verified_task(self):
        task = self.journal.create_task(
            "HTTP_CHECK",
            mission_id=self.mission_id,
            session_id=self.session_id,
            metadata={
                "agent": "Verifier",
                "success_criteria": ["response body contains accepted"],
            },
        )
        self.journal.queue_task(task.task_id)
        self.journal.start_task(task.task_id)
        attempt_id = self.journal.start_attempt(task.task_id, "REAL")
        tool_call_id = self.journal.record_tool_call(
            task.task_id,
            attempt_id,
            "http",
            "GET",
            execution_mode="REAL",
            request={"url": "https://example.test"},
            response={"status": 200},
        )
        self.journal.complete_execution(task.task_id, {"response": "accepted"})
        proof_id = self.journal.record_proof(
            task.task_id,
            "http_response",
            execution_mode="REAL",
            value="accepted",
            attempt_id=attempt_id,
            tool_call_id=tool_call_id,
        )
        self.journal.verify_proof(
            proof_id,
            "dashboard-test",
            {"criteria_met": True},
            valid=True,
        )
        self.journal.verify_task(task.task_id, proof_id)
        self.journal.record_outcome(
            task.task_id, "VERIFIED", {"result": "accepted"}, proof_id=proof_id
        )
        return task.task_id

    def test_overview_uses_canonical_statuses_and_real_progress(self):
        queued = self.journal.create_task(
            "QUEUED_TASK", mission_id=self.mission_id, session_id=self.session_id
        )
        self.journal.queue_task(queued.task_id)
        verified_task_id = self._verified_task()
        simulated = self.journal.create_task(
            "SIMULATED_TASK",
            mission_id=self.mission_id,
            session_id=self.session_id,
            execution_mode="SIMULATED",
        )
        self.journal.queue_task(simulated.task_id)
        self.journal.start_task(simulated.task_id)
        self.journal.start_attempt(simulated.task_id, "SIMULATED")
        self.journal.complete_execution(
            simulated.task_id,
            {"simulation": "finished"},
            execution_mode="SIMULATED",
        )

        overview = dashboard_overview(self.journal)

        self.assertEqual(overview["runtime"]["active_session"]["session_id"], self.session_id)
        mission = next(item for item in overview["missions"] if item["mission_id"] == self.mission_id)
        self.assertEqual(mission["progress"]["verified_tasks"], 1)
        self.assertEqual(mission["progress"]["total_tasks"], 3)
        statuses = {task["task_id"]: task["status"] for task in overview["tasks"]}
        self.assertEqual(statuses[queued.task_id], TaskStatus.QUEUED.value)
        self.assertEqual(statuses[verified_task_id], TaskStatus.VERIFIED.value)
        self.assertEqual(statuses[simulated.task_id], TaskStatus.EXECUTED.value)
        self.assertNotIn("COMPLETED", statuses.values())
        self.assertTrue(overview["timeline"])

    def test_detail_views_return_persisted_execution_and_proof_relations(self):
        task_id = self._verified_task()

        mission = mission_detail(self.journal, self.mission_id)
        task = task_detail(self.journal, task_id)

        self.assertEqual(mission["tasks"][0]["status"], TaskStatus.VERIFIED.value)
        self.assertEqual(len(mission["tool_calls"]), 1)
        self.assertEqual(len(mission["execution_attempts"]), 1)
        self.assertEqual(task["status"], TaskStatus.VERIFIED.value)
        self.assertEqual(task["tool_calls"][0]["attempt_id"], task["execution_attempts"][0]["attempt_id"])
        self.assertEqual(task["proofs"][0]["task_id"], task_id)
        self.assertEqual(task["proofs"][0]["tool_call_id"], task["tool_calls"][0]["tool_call_id"])

    def test_missing_records_are_not_fabricated(self):
        self.assertIsNone(mission_detail(self.journal, "missing-mission"))
        self.assertIsNone(task_detail(self.journal, "missing-task"))


if __name__ == "__main__":
    unittest.main()
