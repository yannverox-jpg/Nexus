import sqlite3
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

class DistributedTaskManager:
    """
    Moteur de concurrence distribuée :
    - Verrouillage par bail (Lease-Based Task Locking) avec expiration TTL & Heartbeats.
    - Contrôle de Concurrence Optimiste (OCC) via numérotation de version pour empêcher les doubles exécutions.
    """
    def __init__(self, db_path: str = "nexus_distributed.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS distributed_tasks (
                task_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                status TEXT NOT NULL, -- PENDING, LEASED, COMPLETED, FAILED
                worker_id TEXT,
                lease_expires_at REAL DEFAULT 0,
                version INTEGER DEFAULT 1,
                updated_at REAL NOT NULL
            )
            """)
            conn.commit()

    def create_task(self, task_id: str, payload: Dict[str, Any]):
        """Enregistre une nouvelle tâche dans le registre distribué."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO distributed_tasks
                (task_id, payload, status, version, updated_at)
                VALUES (?, ?, 'PENDING', 1, ?)
                """,
                (task_id, json.dumps(payload), now)
            )
            conn.commit()

    def acquire_task_lease(self, worker_id: str, lease_duration: int = 15) -> Optional[Dict[str, Any]]:
        """
        Tente d'acquérir un bail exclusif sur une tâche en attente
        ou sur une tâche dont le bail d'un ancien worker a expiré.
        """
        now = time.time()
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            conn.execute("BEGIN TRANSACTION;")

            # Recherche d'une tâche PENDING ou dont le bail a expiré (Crash recovery automatique)
            cursor.execute(
                """
                SELECT * FROM distributed_tasks
                WHERE status = 'PENDING'
                   OR (status = 'LEASED' AND lease_expires_at < ?)
                LIMIT 1
                """,
                (now,)
            )
            row = cursor.fetchone()

            if not row:
                conn.commit()
                return None

            task_id = row["task_id"]
            current_version = row["version"]
            new_expires = now + lease_duration

            # Attribution atomique du bail avec OCC (Vérification de la version)
            cursor.execute(
                """
                UPDATE distributed_tasks
                SET status = 'LEASED',
                    worker_id = ?,
                    lease_expires_at = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE task_id = ? AND version = ?
                """,
                (worker_id, new_expires, now, task_id, current_version)
            )

            if cursor.rowcount == 0:
                # Conflit de concurrence détecté, abandon de la tentative pour ce cycle
                conn.rollback()
                return None

            conn.commit()
            return dict(row)

        except Exception as e:
            conn.rollback()
            logging.error(f"[LEASE ERROR] Échec de l'acquisition du bail : {e}")
            return None
        finally:
            conn.close()

    def heartbeat(self, task_id: str, worker_id: str, extension: int = 15) -> bool:
        """Permet à un sous-agent en cours de traitement de prolonger son bail."""
        now = time.time()
        new_expires = now + extension
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE distributed_tasks
                SET lease_expires_at = ?, updated_at = ?
                WHERE task_id = ? AND worker_id = ? AND status = 'LEASED'
                """,
                (new_expires, now, task_id, worker_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def complete_task(self, task_id: str, worker_id: str):
        """Marque la tâche comme terminée avec succès."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE distributed_tasks
                SET status = 'COMPLETED', worker_id = NULL, lease_expires_at = 0, updated_at = ?
                WHERE task_id = ? AND worker_id = ?
                """,
                (now, task_id, worker_id)
            )
            conn.commit()
            logging.info(f"[TASK FINISHED] Tâche {task_id} clôturée par le worker {worker_id}.")


if __name__ == "__main__":
    manager = DistributedTaskManager()

    # 1. Injection d'une tâche critique
    manager.create_task("TASK-EXEC-992", {"target": "API_GATEWAY", "action": "SYNC"})

    # 2. Le sous-agent tente de s'approprier la tâche via un bail de 10 secondes
    worker_node = "SubAgent-Worker-Alpha"
    task = manager.acquire_task_lease(worker_id=worker_node, lease_duration=10)

    if task:
        logging.info(f"[WORKER] Bail accordé pour la tâche {task['task_id']}. Traitement en cours...")

        # Simulation d'un battement de cœur (le worker indique qu'il est toujours vivant)
        manager.heartbeat(task['task_id'], worker_node)

        # Fin du traitement
        manager.complete_task(task['task_id'], worker_node)
    else:
        logging.info("[WORKER] Aucune tâche disponible ou bail en cours de validité ailleurs.")
