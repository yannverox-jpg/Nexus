import asyncio
import logging
from task_manager import NexusOrchestrator, TaskSpecification

async def main():
    logging.info("=== DÉMARRAGE DU NOYAU AUTONOME NEXUS (MODULE 1) ===")
    orchestrator = NexusOrchestrator()

    # Boucle d'écoute infinie du serveur
    while True:
        # Ici, l'orchestrateur reste en attente de nouvelles opportunités entrantes (Webhooks/API)
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Arrêt du serveur Nexus.")
