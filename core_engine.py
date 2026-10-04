import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "nexus-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "nexus_services"))

from orchestrator import RobustOrchestrator
from database.memory_manager import PersistentMemoryManager
from utils.logger import logger

async def main():
    logger.log("INFO", "🚀 [CORE ENGINE] Démarrage du moteur principal Nexus...")
    db_mgr = PersistentMemoryManager()
    orchestrator = RobustOrchestrator(db_manager=db_mgr)

    # Lancement de la boucle de supervision
    asyncio.create_task(orchestrator.start_loop())

    while True:
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.log("INFO", "Arrêt du moteur principal Nexus.")
