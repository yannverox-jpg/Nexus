"""Conservative runtime readiness checks; no synthetic bootstrap transactions."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict


class NexusM2MProtocolHandler:
    """Build an unsigned proposal envelope; this is not authentication or payment."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def create_m2m_handshake(
        self, target_ai_endpoint: str, requested_resource: str, offer_usdc: float
    ) -> Dict[str, Any]:
        return {
            "protocol_version": "NEXUS-M2M-v1",
            "sender_agent": self.agent_id,
            "timestamp": time.time(),
            "request_type": "RESOURCE_ACQUISITION_PROPOSAL",
            "payload": {
                "resource": requested_resource,
                "offer_amount_usdc": offer_usdc,
                "target_endpoint": target_ai_endpoint,
            },
            "nonce": str(uuid.uuid4()),
            "security_mode": "UNSIGNED_PROPOSAL_ONLY",
            "funds_moved": False,
        }

    def parse_and_validate_m2m_response(self, response: Dict[str, Any]) -> bool:
        return (
            response.get("protocol_version") == "NEXUS-M2M-v1"
            and response.get("status") == "ACCEPTED"
            and response.get("security_mode") == "UNSIGNED_PROPOSAL_ONLY"
            and response.get("funds_moved") is False
        )


class NexusAutonomousBootDaemon:
    """Compatibility service that checks readiness without inventing startup work."""

    def __init__(self, auto_engine: Any, db: Any):
        self.auto_engine = auto_engine
        self.db = db
        self.m2m_handler = NexusM2MProtocolHandler("NEXUS-ORCHESTRATOR")
        self.is_running = False

    async def boot_sequence(self) -> Dict[str, Any]:
        tasks = self.db.get_all_tasks() if hasattr(self.db, "get_all_tasks") else []
        result = {
            "status": "READY_FOR_CONFIGURED_WORKFLOWS",
            "existing_task_count": len(tasks),
            "tasks_created": 0,
            "external_actions_executed": 0,
            "financial_actions_executed": 0,
            "note": "Startup performs no synthetic wallet, liquidity, M2M purchase, or escrow operation.",
        }
        print(f"[NEXUS BOOT] {result}")
        return result

    async def start_m2m_continuous_loop(self) -> None:
        self.is_running = True
        await self.boot_sequence()
        while self.is_running:
            await asyncio.sleep(30)

    def stop(self) -> None:
        self.is_running = False
