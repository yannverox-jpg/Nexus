import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

try:
    from module1_orchestrator import NexusOrchestrator
    from module2_web3_wallet import NexusWeb3WalletManager
    from module3_microservices import NexusMicroserviceBridge
except ImportError:
    from module_mocks import NexusOrchestrator, NexusWeb3WalletManager, NexusMicroserviceBridge

from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from web3_escrow_billing import NexusWeb3EscrowBilling

# Nouveaux modules v2
from task_persistence_db import NexusDatabaseManager
from dispute_resolution import NexusDisputeResolutionEngine
from nexus_cli_dashboard import NexusCLIDashboard

async def main():
    print("=" * 70)
    print("🚀 NEXUS TASK DEPARTMENT V2 - ARCHITECTURE FINALE OPÉRATIONNELLE")
    print("=" * 70)

    config_path = os.path.join(os.path.dirname(__file__), "config_nexus.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    # 1. Base & Persistance
    db = NexusDatabaseManager()

    # 2. Noyau de départ
    orchestrator = NexusOrchestrator(max_agents=10)
    wallet_mgr = NexusWeb3WalletManager(evm_rpc_url=config["web3_wallet"]["evm_rpc_url"])
    bridge = NexusMicroserviceBridge()

    # 3. Services d'escrow & Marketplace
    auto_engine = NexusAutoTaskEngine(orchestrator)
    catalog = ServiceCatalogRegistry()
    escrow = NexusWeb3EscrowBilling(wallet_mgr)

    # 4. Litiges & Dashboard
    dispute_engine = NexusDisputeResolutionEngine(escrow_system=escrow, db_manager=db)
    dashboard = NexusCLIDashboard(db_manager=db)

    # Démarrage des agents
    orchestrator.spawn_agent("Worker-Alpha", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-Beta", "WEB3_EXECUTION")
    asyncio.create_task(orchestrator.start_dispatcher())

    # Exemple de scénario avec enregistrement DB
    goal = "Exécuter la vérification du contrat et sécuriser l'escrow USDC"
    ctx = {"budget_usdc": 10.0, "provider_address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"}

    task_ids = await auto_engine.decompose_and_enqueue_goal(goal, ctx)

    # Enregistrement initial dans la base SQLite
    for tid in task_ids:
        db.save_task(task_id=tid, task_type="AUTONOMOUS_GOAL", priority="HIGH", status="ENQUEUED", payload=ctx)

    # Création d'un escrow de test
    escrow_id = "escrow-test-001"
    escrow.create_escrow_lock(escrow_id, "0xClientAddress", ctx["provider_address"], ctx["budget_usdc"])
    db.save_escrow(escrow_id, "0xClientAddress", ctx["provider_address"], ctx["budget_usdc"], "LOCKED")

    # Simulation d'un échec de qualité -> arbitrage automatique
    print("\n⚠️ Simulation d'une livraison défectueuse pour test d'arbitrage...")
    arbitration = dispute_engine.evaluate_and_handle_failure(
        escrow_id=escrow_id,
        reason="Quality verification failed (Timeout)",
        task_payload=ctx
    )

    # Premier échec -> déclenche un Retry
    if arbitration["action"] == "RETRY":
        # Force le second échec pour valider le remboursement
        dispute_engine.evaluate_and_handle_failure(escrow_id, "Retry failed", ctx)
        dispute_engine.evaluate_and_handle_failure(escrow_id, "Final failure", ctx)

    # Affichage du dashboard CLI
    dashboard.render()

    await bridge.close()
    print("\n✅ Département Tâches v2 déployé et prêt.")

if __name__ == "__main__":
    asyncio.run(main())
