import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [NEXUS-ORCHESTRATOR] - %(message)s")

class TaskSpecification(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:10]}")
    service_type: str
    estimated_payout_usdc: float
    estimated_cost_usdc: float
    payload: Dict[str, Any]

class SubAgentWorker:
    """Unité d'exécution dédiée à une seule tâche."""
    def __init__(self, agent_id: str, spec: TaskSpecification):
        self.agent_id = agent_id
        self.spec = spec

    async def run(self) -> Dict[str, Any]:
        logging.info(f"Agent [{self.agent_id}] actif pour la tâche '{self.spec.service_type}' ({self.spec.task_id})")

        # --- LOGIQUE D'EXÉCUTION DE LA TÂCHE ---
        # C'est ici que l'agent réalise le travail réel (API, scraping, parsing, etc.)
        # Exécution asynchrone non-bloquante
        try:
            # Traitement dynamique selon le type de service
            result_data = await self._process_service(self.spec.service_type, self.spec.payload)

            profit = self.spec.estimated_payout_usdc - self.spec.estimated_cost_usdc
            logging.info(f"Agent [{self.agent_id}] terminé avec succès. Profit net : +{profit:.2f} USDC")

            return {
                "status": "COMPLETED",
                "task_id": self.spec.task_id,
                "agent_id": self.agent_id,
                "net_profit_usdc": profit,
                "output": result_data
            }
        except Exception as e:
            logging.error(f"Agent [{self.agent_id}] en échec sur la tâche {self.spec.task_id} : {e}")
            return {
                "status": "FAILED",
                "task_id": self.spec.task_id,
                "agent_id": self.agent_id,
                "error": str(e)
            }

    async def _process_service(self, service_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode de traitement interne des requêtes."""
        # Simulation du temps de traitement réseau
        await asyncio.sleep(1.0)
        return {"processed": True, "type": service_type, "input_keys": list(payload.keys())}


class NexusOrchestrator:
    """Noyau décisionnel de Nexus."""
    def __init__(self):
        self.active_workers: Dict[str, asyncio.Task] = {}
        self.total_net_profit_usdc: float = 0.0

    def evaluate_roi(self, spec: TaskSpecification) -> bool:
        """Filtre strict de rentabilité avant de dépenser des ressources/tokens."""
        if spec.estimated_cost_usdc <= 0:
            return True

        roi_ratio = spec.estimated_payout_usdc / spec.estimated_cost_usdc
        if roi_ratio >= Config.MIN_ROI_RATIO:
            return True

        logging.warning(f"Tâche {spec.task_id} rejetée : ROI insuffisant ({roi_ratio:.2f} < {Config.MIN_ROI_RATIO})")
        return False

    async def dispatch_task(self, spec: TaskSpecification) -> Optional[str]:
        """Évalue et déploie un sous-agent si la tâche est valide."""
        if len(self.active_workers) >= Config.MAX_CONCURRENT_WORKERS:
            logging.warning("Capacité maximale de sous-agents atteinte. Attente de libération de ressources...")
            return None

        if not self.evaluate_roi(spec):
            return None

        agent_id = f"nexus_agent_{uuid.uuid4().hex[:6]}"
        worker = SubAgentWorker(agent_id, spec)

        # Instanciation de la tâche en arrière-plan sans bloquer l'orchestrateur
        task = asyncio.create_task(worker.run())
        self.active_workers[agent_id] = task

        # Callback automatique à la fin du travail
        task.add_done_callback(lambda t: self._handle_worker_completion(agent_id, t))
        return agent_id

    def _handle_worker_completion(self, agent_id: str, task: asyncio.Task):
        try:
            res = task.result()
            if res.get("status") == "COMPLETED":
                self.total_net_profit_usdc += res.get("net_profit_usdc", 0.0)
                logging.info(f"Cumul des bénéfices Nexus : {self.total_net_profit_usdc:.2f} USDC")
        except Exception as e:
            logging.error(f"Erreur lors du nettoyage de l'agent {agent_id} : {e}")
        finally:
            if agent_id in self.active_workers:
                del self.active_workers[agent_id]
