import os
import tempfile
import unittest
from unittest.mock import patch

from nexus_services.runtime_contracts import TaskRecord
from nexus_services.nexus_safe_executors import (
    CapabilityAssessmentExecutor,
    WorkflowPlanReviewExecutor,
    PlatformAccountReconciliationExecutor,
)


class NexusSafeExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_capability_assessment_reports_real_internal_result(self):
        task = TaskRecord(task_id="cap-1", task_type="CAPABILITY_ASSESSMENT")
        result = await CapabilityAssessmentExecutor().execute(task)
        self.assertEqual(result["status"], "ASSESSED")
        self.assertFalse(result["external_action_performed"])
        self.assertFalse(result["identity"]["financial_architecture"]["owns_wallet"])

    async def test_workflow_plan_preserves_constraints(self):
        task = TaskRecord(
            task_id="plan-1",
            task_type="WORKFLOW_PLAN_REVIEW",
            payload={"goal_context": "Prepare a compliant workflow"},
        )
        result = await WorkflowPlanReviewExecutor().execute(task)
        self.assertEqual(result["status"], "PLAN_PREPARED")
        self.assertFalse(result["external_action_performed"])
        self.assertIn("code change without tests and human review", result["blocked_without_authorization"])

    async def test_platform_reconciliation_reads_external_accounts_without_moving_funds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nexus.db")
            from nexus_services.payout_ledger import PayoutLedger
            ledger = PayoutLedger(path)
            ledger.register_platform_account(
                platform="Example",
                account_reference="acct-1",
                currency="EUR",
                balance="12.50",
                evidence_reference="statement-1",
            )
            task = TaskRecord(
                task_id="reconcile-1",
                task_type="PLATFORM_ACCOUNT_RECONCILIATION",
                payload={},
            )
            with patch.dict(os.environ, {"NEXUS_OPERATIONAL_DB_PATH": path}):
                result = await PlatformAccountReconciliationExecutor().execute(task)
            self.assertEqual(result["account_count"], 1)
            self.assertEqual(result["consolidated_external_balances"]["EUR"], "12.50")
            self.assertFalse(result["funds_moved"])


if __name__ == "__main__":
    unittest.main()
