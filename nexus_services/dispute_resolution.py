"""Dispute tracking without custody or automatic refunds.

Nexus records workflow decisions only. Refunds and payout reversals must be
performed and confirmed by the external platform that holds the funds.
"""
from typing import Any, Dict


class NexusDisputeResolutionEngine:
    def __init__(self, escrow_system: Any = None, db_manager: Any = None, max_retries: int = 2):
        self.escrow_system = escrow_system
        self.db = db_manager
        self.max_retries = max(0, int(max_retries))
        self.retry_counters: dict[str, int] = {}

    def evaluate_and_handle_failure(
        self, escrow_id: str, reason: str, task_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        attempts = self.retry_counters.get(escrow_id, 0)
        if attempts < self.max_retries:
            self.retry_counters[escrow_id] = attempts + 1
            return {
                "action": "RETRY",
                "escrow_id": escrow_id,
                "attempt": attempts + 1,
                "reason": reason,
                "funds_moved": False,
            }
        return {
            "action": "REVIEW_REQUIRED",
            "status": "EXTERNAL_PROVIDER_REVIEW_REQUIRED",
            "escrow_id": escrow_id,
            "reason": reason,
            "funds_moved": False,
            "refund_status": "NOT_EXECUTED",
            "message": "Nexus cannot refund or reverse external platform funds.",
        }
