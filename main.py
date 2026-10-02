import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database.memory_manager import PersistentMemoryManager
from orchestrator import RobustOrchestrator
from utils.logger import logger

async def main():
    logger.log("INFO", "=== INITIALISATION DU SYSTÈME AUTONOME NEXUS ===")

    db_mgr = PersistentMemoryManager()
    orchestrator = RobustOrchestrator(db_manager=db_mgr)

    # Lancement de la boucle de l'orchestrateur en arrière-plan
    loop_task = asyncio.create_task(orchestrator.start_loop())

    # Soumission de tâches de démonstration
    t1 = await orchestrator.submit_task("ANALYSIS", {"market": "CRYPTO", "pair": "ETHUSD"})
    t2 = await orchestrator.submit_task("EXECUTION", {"action": "BUY", "symbol": "BTCUSD", "amount": 1.0})
    t3 = await orchestrator.submit_task("AUDIT", {"transaction_id": t2})

    logger.log("INFO", f"Tâches soumises: {t1}, {t2}, {t3}")

    # Attendre l'exécution des tâches
    await asyncio.sleep(1.0)

    orchestrator.stop()
    await loop_task
    logger.log("INFO", "=== NAYAU ARCHITECTURAL EXÉCUTÉ ET ARRÊTÉ AVEC SUCCÈS ===")

if __name__ == "__main__":
    asyncio.run(main())
