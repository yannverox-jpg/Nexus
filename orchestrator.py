import asyncio
import uuid
import sys
import os
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import logger
from database.memory_manager import PersistentMemoryManager
from workers.base_worker import BaseWorker, AnalysisWorker, ExecutionWorker, AuditWorker
from nexus_services.advanced_resilience import CircuitBreaker, CircuitBreakerOpenException

class RobustOrchestrator:
    """
    Orchestrateur Core :
    - Boucle d'exécution asynchrone (asyncio).
    - Gestionnaire de files d'attente (Task Queue) avec attribution dynamique aux sous-agents.
    - Isolation des pannes avec Circuit Breaker et mécanisme de Retry (exponential backoff).
    """
    def __init__(self, db_manager: PersistentMemoryManager, max_retries: int = 3):
        self.db = db_manager
        self.max_retries = max_retries
        self.task_queue = asyncio.Queue()
        self.workers: Dict[str, BaseWorker] = {
            "ANALYSIS": AnalysisWorker("AnalysisWorker-1", self.db),
            "EXECUTION": ExecutionWorker("ExecutionWorker-1", self.db),
            "AUDIT": AuditWorker("AuditWorker-1", self.db)
        }
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=10.0)
        self.is_running = False

    async def submit_task(self, task_type: str, payload: Dict[str, Any], priority: str = "MEDIUM") -> str:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        cid = f"corr_{uuid.uuid4().hex[:8]}"
        task_data = {
            "task_id": task_id,
            "task_type": task_type,
            "priority": priority,
            "payload": payload,
            "correlation_id": cid,
            "retry_count": 0
        }
        self.db.save_task(task_id, task_type, priority, "ENQUEUED", payload, correlation_id=cid)
        await self.task_queue.put(task_data)
        logger.log("INFO", f"Tâche {task_id} [{task_type}] enfilée.", correlation_id=cid)
        return task_id

    async def start_loop(self):
        self.is_running = True
        logger.log("INFO", "🚀 [ORCHESTRATOR CORE] Démarrage de la boucle asynchrone de supervision.")
        while self.is_running:
            if not self.task_queue.empty():
                task = await self.task_queue.get()
                asyncio.create_task(self._dispatch_and_execute(task))
            else:
                await asyncio.sleep(0.05)

    async def _dispatch_and_execute(self, task: Dict[str, Any]):
        task_id = task["task_id"]
        task_type = task["task_type"]
        cid = task["correlation_id"]
        retries = task["retry_count"]

        worker = self.workers.get(task_type)
        if not worker:
            err_msg = f"Aucun worker trouvé pour le type: {task_type}"
            logger.log("ERROR", err_msg, correlation_id=cid)
            self.db.save_task(task_id, task_type, task["priority"], "FAILED", task["payload"], retry_count=retries, error=err_msg, correlation_id=cid)
            return

        self.db.save_task(task_id, task_type, task["priority"], "PROCESSING", task["payload"], retry_count=retries, correlation_id=cid)

        try:
            # Wrap execution with Circuit Breaker
            res = await self.circuit_breaker(worker.execute_task, task)
            self.db.save_task(task_id, task_type, task["priority"], "COMPLETED", task["payload"], retry_count=retries, result=res.get("result"), correlation_id=cid)
        except CircuitBreakerOpenException as cb_err:
            logger.log("WARNING", f"Circuit Breaker ouvert pour {task_id}. Re-queuing...", correlation_id=cid)
            await asyncio.sleep(2.0)
            await self.task_queue.put(task)
        except Exception as e:
            retries += 1
            task["retry_count"] = retries
            if retries <= self.max_retries:
                backoff_delay = (2 ** retries) * 0.1  # Exponential backoff
                logger.log("WARNING", f"Échec tâche {task_id}. Retry {retries}/{self.max_retries} dans {backoff_delay:.2f}s", correlation_id=cid)
                await asyncio.sleep(backoff_delay)
                await self.task_queue.put(task)
            else:
                logger.log("ERROR", f"Tâche {task_id} abandonnée après {self.max_retries} tentatives.", correlation_id=cid)
                self.db.save_task(task_id, task_type, task["priority"], "FAILED", task["payload"], retry_count=retries, error=str(e), correlation_id=cid)

    def stop(self):
        self.is_running = False
