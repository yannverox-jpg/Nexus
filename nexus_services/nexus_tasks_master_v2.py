"""Legacy v2 CLI entrypoint for external account reconciliation only.

No Nexus-owned wallet, blockchain escrow, or automatic money movement is used.
"""
import asyncio

from legacy_runtime_adapter import NexusOrchestrator
from auto_task_generator import NexusAutoTaskEngine
from task_persistence_db import NexusDatabaseManager
from nexus_cli_dashboard import NexusCLIDashboard


async def main():
    db = NexusDatabaseManager()
    orchestrator = NexusOrchestrator(max_agents=10, db_manager=db)
    orchestrator.spawn_agent("Worker-Alpha", "PLATFORM_ACCOUNT_RECONCILIATION")
    orchestrator.spawn_agent("Worker-Beta", "PAYOUT_STATUS_RECONCILIATION")

    auto_engine = NexusAutoTaskEngine(orchestrator)
    dashboard = NexusCLIDashboard(db_manager=db)
    goal = (
        "Rapprocher les soldes des comptes des plateformes externes et préparer "
        "un retrait vers la carte Visa prépayée externe, sans exécuter de transfert."
    )
    context = {
        "financial_model": "EXTERNAL_PLATFORM_ACCOUNTS",
        "payout_destination": "EXTERNAL_PREPAID_VISA",
        "execution_mode": "RECONCILIATION_ONLY",
    }
    task_ids = await auto_engine.decompose_and_enqueue_goal(goal, context)
    for task_id in task_ids:
        db.save_task(
            task_id=task_id,
            task_type="PLATFORM_ACCOUNT_RECONCILIATION",
            priority="HIGH",
            status="ENQUEUED",
            payload=context,
        )
    dashboard.render()
    print("Rapprochement préparé; aucun fonds n'a été transféré.")
    orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
