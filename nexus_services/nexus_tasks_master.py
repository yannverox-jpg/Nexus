"""Legacy CLI entrypoint for external-platform reconciliation only.

This script does not create a Nexus wallet, custody funds, or execute payouts.
"""
import asyncio

from legacy_runtime_adapter import NexusOrchestrator
from auto_task_generator import NexusAutoTaskEngine


async def main():
    orchestrator = NexusOrchestrator(max_agents=10)
    orchestrator.spawn_agent("Worker-1", "PLATFORM_ACCOUNT_RECONCILIATION")
    orchestrator.spawn_agent("Worker-2", "PAYOUT_STATUS_RECONCILIATION")

    auto_engine = NexusAutoTaskEngine(orchestrator)
    goal = (
        "Consolider les soldes observés des comptes des plateformes externes, "
        "puis préparer le rapprochement vers la carte Visa prépayée externe. "
        "Ne jamais déplacer, détenir ou simuler le transfert de fonds."
    )
    context = {
        "financial_model": "EXTERNAL_PLATFORM_ACCOUNTS",
        "payout_destination": "EXTERNAL_PREPAID_VISA",
        "execution_mode": "RECONCILIATION_ONLY",
    }
    task_ids = await auto_engine.decompose_and_enqueue_goal(goal, context)
    print(f"{len(task_ids)} tâches de rapprochement externe mises en file; aucun paiement exécuté.")
    orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
