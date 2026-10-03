import abc
import traceback
import asyncio
import sys
import os
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.logger import logger
from database.memory_manager import PersistentMemoryManager

class BaseWorker(abc.ABC):
    """
    Classe abstraite 'BaseWorker' encapsulant l'exécution sécurisée (try/except/traceback).
    Sous-agents spécialisés (Analyse, Exécution, Audit) héritent de cette classe.
    """
    def __init__(self, worker_id: str, memory_manager: PersistentMemoryManager):
        self.worker_id = worker_id
        self.db = memory_manager

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task.get("task_id")
        cid = task.get("correlation_id")

        logger.log("INFO", f"Worker [{self.worker_id}] démarre la tâche {task_id}", correlation_id=cid)
        self.db.log_audit(cid, "INFO", f"Worker [{self.worker_id}] started task {task_id}")

        try:
            result = await self.process(task["payload"])
            logger.log("INFO", f"Worker [{self.worker_id}] a terminé la tâche {task_id} avec succès.", correlation_id=cid)
            self.db.log_audit(cid, "INFO", f"Worker [{self.worker_id}] completed task {task_id}")
            return {"status": "SUCCESS", "result": result}
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.log("ERROR", f"Worker [{self.worker_id}] échec sur tâche {task_id}: {str(e)}", correlation_id=cid, extra={"trace": tb_str})
            self.db.log_audit(cid, "ERROR", f"Failed task {task_id}: {str(e)}", trace=tb_str)
            raise e

    @abc.abstractmethod
    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode à implémenter par chaque sous-agent spécialisé."""
        pass


class AnalysisWorker(BaseWorker):
    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"analysis": "COMPLETE", "score": 98.5, "data": payload}


class ExecutionWorker(BaseWorker):
    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"execution": "EXECUTED", "symbol": payload.get("symbol", "BTCUSD")}


class AuditWorker(BaseWorker):
    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.02)
        return {"audit": "VERIFIED", "status": "COMPLIANT"}
