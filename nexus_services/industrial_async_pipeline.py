import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional, Set
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("IndustrialPipeline")

class CircuitState(Enum):
    CLOSED = "CLOSED"       # Fonctionnement nominal
    OPEN = "OPEN"           # Coupure d'urgence suite à des échecs en cascade
    HALF_OPEN = "HALF_OPEN" # Phase de test de rétablissement

class IndustrialCircuitBreaker:
    """
    Protège les connexions réseau sortantes (API tierces / exchanges)
    contre l'effet d'avalanche en cas de panne distante.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 5.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = 0.0

    async def __aenter__(self):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.warning("[CIRCUIT BREAKER] Passage en mode HALF-OPEN (Test de reconnexion)...")
                self.state = CircuitState.HALF_OPEN
            else:
                raise ConnectionError("[CIRCUIT BREAKER OPEN] Requête rejetée en amont. Protection réseau active.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.failures += 1
            self.last_failure_time = time.time()
            logger.error(f"[CIRCUIT BREAKER] Échec détecté ({self.failures}/{self.failure_threshold}).")

            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.critical("[CIRCUIT BREAKER] Seuil d'échec atteint ! Circuit OUVERT.")
            return False # Propage l'exception pour traitement
        else:
            if self.state == CircuitState.HALF_OPEN:
                logger.info("[CIRCUIT BREAKER] Rétablissement confirmé. Circuit FERMÉ.")
            self.failures = 0
            self.state = CircuitState.CLOSED
            return True


class HighThroughputAsyncEngine:
    """
    Moteur de traitement asynchrone simulant un consommateur Kafka haut débit
    avec gestion d'idempotence et routage DLQ.
    """
    def __init__(self, worker_count: int = 4):
        self.worker_count = worker_count
        self.ingress_queue: asyncio.Queue = asyncio.Queue()
        self.dlq_queue: asyncio.Queue = asyncio.Queue()

        # Simulation d'un cache distribué (Redis) pour l'idempotence
        self.processed_event_ids: Set[str] = set()

        # Instance du Circuit Breaker pour les appels réseau sortants
        self.api_circuit_breaker = IndustrialCircuitBreaker(failure_threshold=2, recovery_timeout=3.0)

    async def ingest_webhook(self, payload: Dict[str, Any]):
        """Point d'entrée asynchrone non bloquant (Ingress Buffer)."""
        event_id = payload.get("event_id", str(uuid.uuid4()))
        correlation_id = payload.get("correlation_id", f"CORR-{uuid.uuid4().hex[:8]}")

        wrapped_message = {
            "event_id": event_id,
            "correlation_id": correlation_id,
            "payload": payload,
            "retry_count": 0
        }

        await self.ingress_queue.put(wrapped_message)
        logger.info(f"[INGRESS] Webhook injecté dans le buffer | CorrelationID: {correlation_id}")

    async def worker(self, worker_name: str):
        """Worker permanent traitant les flux en concurrence contrôlée."""
        logger.info(f"[{worker_name}] Démarré et en écoute...")

        while True:
            message = await self.ingress_queue.get()
            event_id = message["event_id"]
            correlation_id = message["correlation_id"]

            try:
                # 1. Contrôle d'Idempotence (Anti-Duplication stricte)
                if event_id in self.processed_event_ids:
                    logger.warning(f"[{worker_name}] Doublon détecté pour l'événement {event_id}. Ignoré.")
                    self.ingress_queue.task_done()
                    continue

                # 2. Simulation du traitement métier / inférence ou appel réseau protégé
                await self._process_critical_task(message, worker_name)

                # 3. Validation de l'idempotence après succès
                self.processed_event_ids.add(event_id)
                logger.info(f"[{worker_name}] Tâche {event_id} traitée avec succès.")

            except Exception as e:
                logger.error(f"[{worker_name}] Erreur critique sur le message {event_id}: {e}")
                # Routage automatique vers la Dead-Letter Queue (DLQ)
                await self._route_to_dlq(message, str(e))

            finally:
                self.ingress_queue.task_done()

    async def _process_critical_task(self, message: dict, worker_name: str):
        """Exécute l'action protégée par le Circuit Breaker."""
        correlation_id = message["correlation_id"]

        async with self.api_circuit_breaker:
            # Simulation d'un appel réseau instable (provoque une erreur si simuler_panne est actif)
            await asyncio.sleep(0.01) # Latence asynchrone
            if message["payload"].get("simulate_failure", False):
                raise ConnectionError("Timeout de la passerelle distante ou API indisponible.")

            logger.info(f"[{worker_name}] [API SYNC] Transmission validée pour CorrelationID: {correlation_id}")

    async def _route_to_dlq(self, message: dict, error_reason: str):
        """Isole les messages corrompus ou en échec permanent sans bloquer la queue principale."""
        message["error_reason"] = error_reason
        await self.dlq_queue.put(message)
        logger.critical(f"[DLQ ROUTING] Message {message['event_id']} isolé dans la Dead-Letter Queue. Motif : {error_reason}")

    async def start_system(self):
        """Lance le pool de workers asynchrones."""
        workers = [asyncio.create_task(self.worker(f"Worker-{i+1}")) for i in range(self.worker_count)]
        return workers


async def main():
    engine = HighThroughputAsyncEngine(worker_count=3)
    workers = await engine.start_system()

    await engine.ingest_webhook({"event_id": "EVT-001", "action": "EXEC_TRADE", "simulate_failure": False})
    await engine.ingest_webhook({"event_id": "EVT-001", "action": "EXEC_TRADE", "simulate_failure": False})
    await engine.ingest_webhook({"event_id": "EVT-002", "action": "BAD_REQUEST", "simulate_failure": True})

    await engine.ingress_queue.join()

    for w in workers:
        w.cancel()

if __name__ == "__main__":
    asyncio.run(main())
