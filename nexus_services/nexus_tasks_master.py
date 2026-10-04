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

async def main():
    print("=" * 65)
    print("🚀 NEXUS DEPARTMENT - SYSTÈME DE TÂCHES AUTONOME COMPLET")
    print("=" * 65)

    config_path = os.path.join(os.path.dirname(__file__), "config_nexus.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    # Core
    orchestrator = NexusOrchestrator(max_agents=10)
    wallet_mgr = NexusWeb3WalletManager(evm_rpc_url=config["web3_wallet"]["evm_rpc_url"])
    bridge = NexusMicroserviceBridge()

    # Nouveaux Modules (1, 2, 3)
    auto_engine = NexusAutoTaskEngine(orchestrator)
    catalog = ServiceCatalogRegistry()
    escrow = NexusWeb3EscrowBilling(wallet_mgr)

    # Enregistrement des agents
    orchestrator.spawn_agent("Worker-1", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-2", "WEB3_EXECUTION")

    # Démarrage du dispatcher de tâches
    asyncio.create_task(orchestrator.start_dispatcher())

    # Exemple d'objectif soumis à Nexus
    goal = "Traiter le contrat de données externes et effectuer le règlement de 5 USDC"
    ctx = {
        "budget_usdc": 5.0,
        "provider_address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    }

    # Génération et enfilement autonome
    task_ids = await auto_engine.decompose_and_enqueue_goal(goal, ctx)
    print(f"\n✅ {len(task_ids)} tâches autonomes injectées dans la file d'attente.")

    await bridge.close()

if __name__ == "__main__":
    asyncio.run(main())
