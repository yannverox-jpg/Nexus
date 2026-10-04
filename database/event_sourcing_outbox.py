import sqlite3
import json
import uuid
import time
import logging
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

class EnterpriseEventEngine:
    """
    Moteur Event-Sourced avec Outbox Transactionnel.
    - Event Store append-only pour la traçabilité et l'audit immuable.
    - Outbox queue transactionnelle pour garantir l'atomicité des actions distantes.
    """
    def __init__(self, db_path: str = "nexus_enterprise.db"):
        self.db_path = db_path
        self._init_storage()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_storage(self):
        """Initialise le stockage avec Event Store et Outbox Transactionnel."""
        with self._get_connection() as conn:
            # Table des événements immuables (Event Sourcing)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS event_store (
                event_id TEXT PRIMARY KEY,
                aggregate_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """)
            # Table Outbox pour synchroniser les actions externes de manière atomique
            conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox_queue (
                outbox_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                created_at REAL NOT NULL
            )
            """)
            conn.commit()

    def commit_transaction_with_outbox(self, aggregate_id: str, event_type: str, event_data: Dict[str, Any]):
        """
        Garantit l'atomicité ACID : l'événement et l'ordre sortant sont écrits
        exactement en même temps. Si l'un échoue, tout est annulé (Rollback).
        """
        event_id = str(uuid.uuid4())
        outbox_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_connection()
        try:
            conn.execute("BEGIN TRANSACTION;")

            # 1. Enregistrement dans l'Event Store
            conn.execute(
                "INSERT INTO event_store (event_id, aggregate_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_id, aggregate_id, event_type, json.dumps(event_data), now)
            )

            # 2. Enregistrement dans l'Outbox pour dispatching asynchrone
            conn.execute(
                "INSERT INTO outbox_queue (outbox_id, event_type, payload, status, created_at) VALUES (?, ?, ?, 'PENDING', ?)",
                (outbox_id, event_type, json.dumps(event_data), now)
            )

            conn.commit()
            logging.info(f"[ATOMIC COMMIT] Événement {event_type} validé pour l'agrégat {aggregate_id}")

        except Exception as e:
            conn.rollback()
            logging.critical(f"[TRANSACTION FAILED] Rollback effectué suite à : {e}")
            raise e
        finally:
            conn.close()

    def process_outbox_batch(self):
        """
        Traite les messages de l'outbox de manière isolée pour l'envoi vers les API externes.
        Empêche la perte de données en cas de coupure réseau.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM outbox_queue WHERE status = 'PENDING' LIMIT 10")
        rows = cursor.fetchall()

        for row in rows:
            outbox_id = row["outbox_id"]
            event_type = row["event_type"]
            payload = json.loads(row["payload"])

            try:
                logging.info(f"[OUTBOX DISPATCH] Envoi de l'action {event_type} vers l'API externe...")
                self._mock_external_api_call(payload)

                # Marquer comme traité
                conn.execute("UPDATE outbox_queue SET status = 'PROCESSED' WHERE outbox_id = ?", (outbox_id,))
                conn.commit()
                logging.info(f"[OUTBOX SUCCESS] Message {outbox_id} synchronisé.")

            except Exception as e:
                logging.warning(f"[OUTBOX RETRY] Échec de transmission pour {outbox_id}: {e}")

        conn.close()

    def _mock_external_api_call(self, payload: dict):
        if payload.get("simulate_network_drop"):
            raise ConnectionError("Timeout de la passerelle distante.")
        time.sleep(0.05)


if __name__ == "__main__":
    engine = EnterpriseEventEngine()

    try:
        engine.commit_transaction_with_outbox(
            aggregate_id="AGG-TRADE-8841",
            event_type="ASSET_LIQUIDATION_REQUESTED",
            event_data={"symbol": "BTCUSD", "amount": 0.5, "simulate_network_drop": False}
        )
    except Exception:
        pass

    engine.process_outbox_batch()
