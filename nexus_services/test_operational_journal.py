import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from nexus_services.runtime_contracts import (
    EventStatus,
    EventRecord,
    InvalidTransitionError,
    JournalError,
    OperationalJournal,
    SQLiteEventRepository,
    SQLiteTaskRepository,
    TaskRecord,
    TaskStatus,
)


class OperationalJournalTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "operational.db")
        self.journal = OperationalJournal(self.db_path)
        self.session_id = self.journal.create_session(metadata={"host": "test"})
        self.mission_id = self.journal.create_mission(
            "Exercise the operational journal", session_id=self.session_id
        )

    def tearDown(self):
        self.journal.close()
        self.temp_dir.cleanup()

    def create_task(self, **kwargs):
        return self.journal.create_task(
            "TEST", mission_id=self.mission_id, session_id=self.session_id, **kwargs
        )

    def run_to_running(self, **task_kwargs):
        task = self.create_task(**task_kwargs)
        self.journal.queue_task(task.task_id)
        return self.journal.start_task(task.task_id)

    def run_to_executed(self, execution_mode="REAL", **task_kwargs):
        task = self.run_to_running(**task_kwargs)
        attempt_id = self.journal.start_attempt(task.task_id, execution_mode)
        executed = self.journal.complete_execution(
            task.task_id,
            {"result": "observed", "execution_mode": execution_mode},
            execution_mode=execution_mode,
        )
        return executed, attempt_id

    def test_mission_task_and_canonical_schema_are_created(self):
        task = self.create_task(payload={"scope": "test"})
        self.assertEqual(task.status, TaskStatus.PLANNED)
        self.assertEqual(task.run_id, self.session_id)
        self.assertEqual(task.metadata, {})
        mission = self.journal.get_record("missions", self.mission_id)
        self.assertEqual(mission["objective"], "Exercise the operational journal")
        self.assertEqual(mission["status"], "PLANNED")

        with sqlite3.connect(self.db_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertTrue(
            {
                "runtime_sessions", "missions", "tasks", "task_steps", "task_events",
                "agent_actions", "decisions", "tool_calls", "execution_attempts",
                "failures", "recovery_actions", "approvals", "proofs", "observations",
                "outcomes",
            }.issubset(tables)
        )

    def test_planned_queued_running_executed_transitions(self):
        task = self.create_task()
        self.assertEqual(self.journal.queue_task(task.task_id).status, TaskStatus.QUEUED)
        self.assertEqual(self.journal.start_task(task.task_id).status, TaskStatus.RUNNING)
        attempt_id = self.journal.start_attempt(task.task_id, "REAL")
        self.assertTrue(self.journal.get_record("execution_attempts", attempt_id))
        self.assertEqual(
            self.journal.complete_execution(task.task_id, {"ok": True}).status,
            TaskStatus.EXECUTED,
        )

    def test_verified_requires_real_proof_and_verification(self):
        task = self.run_to_running()
        step_id = self.journal.create_task_step(task.task_id, 1, "verify API result")
        attempt_id = self.journal.start_attempt(task.task_id, "REAL", step_id=step_id)
        self.journal.complete_execution(task.task_id, {"result": "observed"})
        proof_id = self.journal.record_proof(
            task.task_id,
            "api_response",
            execution_mode="REAL",
            value='{"status":"accepted"}',
            attempt_id=attempt_id,
        )
        self.assertEqual(self.journal.get_record("proofs", proof_id)["step_id"], step_id)
        self.assertTrue(
            self.journal.verify_proof(
                proof_id, "api-verifier", {"response_status": 200}, valid=True
            )
        )
        self.assertEqual(
            self.journal.verify_task(task.task_id, proof_id).status, TaskStatus.VERIFIED
        )
        outcome_id = self.journal.record_outcome(
            task.task_id, "VERIFIED", {"effect": "confirmed"}, proof_id=proof_id
        )
        self.assertTrue(self.journal.get_record("outcomes", outcome_id))

    def test_success_outcome_without_verified_real_proof_is_rejected(self):
        task, _ = self.run_to_executed()
        with self.assertRaises(JournalError):
            self.journal.record_outcome(task.task_id, "SUCCESS", {"claimed": True})

    def test_execution_cannot_be_verified_without_proof(self):
        task, _ = self.run_to_executed()
        with self.assertRaises(InvalidTransitionError):
            self.journal.verify_task(task.task_id, "missing-proof")
        self.assertEqual(self.journal.get_task(task.task_id).status, TaskStatus.EXECUTED)

    def test_queued_and_planned_tasks_cannot_be_verified(self):
        task = self.create_task()
        with self.assertRaises(InvalidTransitionError):
            self.journal.verify_task(task.task_id, "no-proof")
        with self.assertRaises(InvalidTransitionError):
            self.journal.complete_execution(task.task_id, {"ok": True})
        self.journal.queue_task(task.task_id)
        with self.assertRaises(InvalidTransitionError):
            self.journal.verify_task(task.task_id, "no-proof")
        with self.assertRaises(InvalidTransitionError):
            self.journal.complete_execution(task.task_id, {"ok": True})
        self.assertEqual(self.journal.get_task(task.task_id).status, TaskStatus.QUEUED)

    def test_waiting_human_requires_explicit_resume(self):
        task = self.run_to_running()
        attempt_id = self.journal.start_attempt(task.task_id, "REAL")
        waiting = self.journal.wait_for_human(task.task_id, "Operator input required")
        self.assertEqual(waiting.status, TaskStatus.WAITING_HUMAN)
        with self.assertRaises(InvalidTransitionError):
            self.journal.complete_execution(task.task_id, {"ok": True})
        with sqlite3.connect(self.db_path) as connection:
            attempt = connection.execute(
                "SELECT status, ended_at FROM execution_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        self.assertEqual(attempt[0], TaskStatus.WAITING_HUMAN.value)
        self.assertIsNotNone(attempt[1])
        self.assertEqual(
            self.journal.resume_task(task.task_id).status, TaskStatus.QUEUED
        )

    def test_failed_recovery_retry_records_failure_and_new_attempt(self):
        task = self.run_to_running()
        first_attempt = self.journal.start_attempt(task.task_id, "REAL")
        failed = self.journal.fail_task(
            task.task_id, "network unavailable", attempt_id=first_attempt
        )
        self.assertEqual(failed.status, TaskStatus.FAILED)
        with self.assertRaises(InvalidTransitionError):
            self.journal.verify_task(task.task_id, "unverified-proof")
        failure_rows = self._rows("failures")
        self.assertEqual(len(failure_rows), 1)
        recovery_id = self.journal.record_recovery(
            task.task_id, "RETRY", failure_id=failure_rows[0]["failure_id"]
        )
        self.assertEqual(
            self.journal.queue_task(task.task_id, recovery_id=recovery_id).status,
            TaskStatus.QUEUED,
        )
        self.journal.start_task(task.task_id)
        second_attempt = self.journal.start_attempt(task.task_id, "REAL")
        self.assertNotEqual(first_attempt, second_attempt)
        attempts = self._rows("execution_attempts")
        self.assertEqual([row["attempt_number"] for row in attempts], [1, 2])
        self.assertEqual(self.journal.get_record("recovery_actions", recovery_id)["status"], "APPLIED")

    def test_created_at_is_immutable_across_transitions(self):
        task = self.create_task()
        created_at = task.created_at
        self.journal.queue_task(task.task_id)
        self.journal.start_task(task.task_id)
        self.journal.start_attempt(task.task_id, "REAL")
        self.journal.complete_execution(task.task_id, {"ok": True})
        self.assertEqual(self.journal.get_task(task.task_id).created_at, created_at)

    def test_repository_restart_restores_session_mission_task_and_events(self):
        task = self.create_task()
        self.journal.queue_task(task.task_id)
        restarted = OperationalJournal(self.db_path)
        try:
            self.assertTrue(restarted.get_record("runtime_sessions", self.session_id))
            self.assertTrue(restarted.get_record("missions", self.mission_id))
            self.assertEqual(restarted.get_task(task.task_id).status, TaskStatus.QUEUED)
            self.assertGreaterEqual(len(restarted.list_events()), 3)
        finally:
            restarted.close()

    def test_tool_call_and_attempt_are_persisted(self):
        task = self.run_to_running()
        step_id = self.journal.create_task_step(task.task_id, 1, "call API")
        attempt_id = self.journal.start_attempt(task.task_id, "REAL", step_id=step_id)
        call_id = self.journal.record_tool_call(
            task.task_id,
            attempt_id,
            "http",
            "GET",
            execution_mode="REAL",
            request={"url": "https://example.test"},
            response={"status": 200},
            external_id="request-123",
        )
        call = self.journal.get_record("tool_calls", call_id)
        self.assertEqual(call["attempt_id"], attempt_id)
        self.assertEqual(call["step_id"], step_id)
        self.assertEqual(json.loads(call["response_json"])["status"], 200)
        self.assertEqual(self.journal.get_record("execution_attempts", attempt_id)["status"], "RUNNING")

    def test_simulated_execution_and_proof_never_become_real_verified_evidence(self):
        task, attempt_id = self.run_to_executed(execution_mode="SIMULATED")
        proof_id = self.journal.record_proof(
            task.task_id, "result", execution_mode="REAL",
            value="simulated output", attempt_id=attempt_id,
        )
        proof = self.journal.get_record("proofs", proof_id)
        self.assertEqual(proof["execution_mode"], "SIMULATED")
        with self.assertRaises(JournalError):
            self.journal.verify_proof(
                proof_id, "verifier", {"checked": True}, valid=True
            )
        self.assertEqual(self.journal.get_task(task.task_id).status, TaskStatus.EXECUTED)

    def test_sensitive_metadata_and_embedded_secrets_are_redacted(self):
        task = self.create_task(
            payload={
                "nested": {"password": "secret-value", "safe": "visible"},
                "endpoint": "https://example.test/?token=secret-token",
                "auth_header": "Bearer secret-bearer-token",
                "credential_url": "https://user:secret-password@example.test/",
            },
            metadata={"api_token": "metadata-secret", "label": "public"},
        )
        payload = self.journal.get_task(task.task_id).payload
        self.assertEqual(payload["nested"]["password"], "[REDACTED]")
        self.assertEqual(payload["nested"]["safe"], "visible")
        self.assertNotIn("secret-token", payload["endpoint"])
        self.assertNotIn("secret-bearer-token", payload["auth_header"])
        self.assertNotIn("secret-password", payload["credential_url"])
        self.assertEqual(self.journal.get_task(task.task_id).metadata["api_token"], "[REDACTED]")

    def test_approval_and_observation_are_persisted(self):
        task = self.journal.queue_task(self.create_task().task_id)
        approval_id = self.journal.request_approval(
            task.task_id, "release payment", requested_by="runtime"
        )
        self.assertEqual(
            self.journal.get_task(task.task_id).status, TaskStatus.WAITING_APPROVAL
        )
        resumed = self.journal.resolve_approval(
            approval_id, approved=True, resolved_by="operator"
        )
        self.assertEqual(resumed.status, TaskStatus.QUEUED)
        self.assertEqual(self.journal.get_record("approvals", approval_id)["status"], "APPROVED")
        observation_id = self.journal.record_observation(
            "http_response", {"status": 202},
            mission_id=self.mission_id, task_id=task.task_id,
            session_id=self.session_id, target="https://example.test",
        )
        self.assertEqual(
            json.loads(self.journal.get_record("observations", observation_id)["data_json"])["status"],
            202,
        )

    def test_append_only_events_and_decisions_store_only_operational_fields(self):
        task = self.create_task()
        step_id = self.journal.create_task_step(task.task_id, 1, "inspect")
        action_id = self.journal.record_agent_action(
            task.task_id, "research-agent", "inspect",
            execution_mode="REAL", step_id=step_id,
        )
        decision_id = self.journal.record_decision(
            question="Which endpoint should be checked?",
            context_summary="Two candidate endpoints are configured.",
            options=["A", "B"],
            decision="A",
            justification_summary="A is the configured endpoint.",
            confidence=0.9,
            risk="LOW",
            expected_outcome="HTTP response",
            mission_id=self.mission_id,
            task_id=task.task_id,
            session_id=self.session_id,
        )
        self.assertTrue(self.journal.get_record("agent_actions", action_id))
        decision = self.journal.get_record("decisions", decision_id)
        self.assertNotIn("chain_of_thought", decision.keys())
        with sqlite3.connect(self.db_path) as connection:
            event_id = connection.execute(
                "SELECT event_id FROM task_events LIMIT 1"
            ).fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE task_events SET event_type = 'CHANGED' WHERE event_id = ?",
                    (event_id,),
                )

    def test_transition_and_event_are_atomic(self):
        task = self.create_task()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """CREATE TRIGGER reject_queue_event BEFORE INSERT ON task_events
                   WHEN NEW.event_type = 'TASK_QUEUED'
                   BEGIN SELECT RAISE(ABORT, 'forced event failure'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.journal.queue_task(task.task_id)
        self.assertEqual(self.journal.get_task(task.task_id).status, TaskStatus.PLANNED)
        self.assertFalse(
            any(event.status == EventStatus.TASK_QUEUED for event in self.journal.list_events())
        )

    def test_concurrent_starts_allow_only_one_transition(self):
        task = self.create_task()
        self.journal.queue_task(task.task_id)

        def start():
            try:
                return self.journal.start_task(task.task_id).status
            except InvalidTransitionError:
                return "REJECTED"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: start(), range(2)))
        self.assertEqual(results.count(TaskStatus.RUNNING), 1)
        self.assertEqual(results.count("REJECTED"), 1)
        self.assertEqual(self.journal.get_task(task.task_id).status, TaskStatus.RUNNING)
        rejected = [
            event for event in self.journal.list_events()
            if event.status == EventStatus.OPERATION_REJECTED
        ]
        self.assertEqual(len(rejected), 1)

    def test_environment_variable_configures_default_journal_database(self):
        configured_path = os.path.join(self.temp_dir.name, "configured.db")
        with patch.dict(os.environ, {"NEXUS_OPERATIONAL_DB_PATH": configured_path}):
            configured = OperationalJournal()
        try:
            self.assertEqual(configured.db_path, configured_path)
            self.assertTrue(os.path.exists(configured_path))
        finally:
            configured.close()

    def test_existing_sqlite_task_repository_preserves_created_at(self):
        repository = SQLiteTaskRepository(self.db_path + ".legacy")
        original = TaskRecord(task_id="legacy-1", task_type="TEST", created_at=100.0)
        repository.save_task(original)
        repository.save_task(replace(original, status=TaskStatus.QUEUED, created_at=200.0))
        self.assertEqual(repository.get_task("legacy-1").created_at, 100.0)

    def test_existing_sqlite_event_repository_does_not_replace_event_history(self):
        repository = SQLiteEventRepository(self.db_path + ".events")
        event = EventRecord(
            event_id="event-1",
            run_id="session",
            task_id=None,
            status=EventStatus.BOOT_STARTED,
        )
        repository.append_event(event)
        changed = replace(event, status=EventStatus.BOOT_COMPLETED)
        with self.assertRaises(sqlite3.IntegrityError):
            repository.append_event(changed)
        self.assertEqual(repository.list_events()[0].status, EventStatus.BOOT_STARTED)

    def _rows(self, table):
        with self.journal._connect() as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


if __name__ == "__main__":
    unittest.main()
