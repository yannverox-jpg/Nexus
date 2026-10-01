import sqlite3
import json
import time
from typing import Dict, Any, List, Optional

class NexusDatabaseManager:
    """
    Gestionnaire de persistance locale : enregistre l'état des tâches,
    l'historique des paiements Web3/Escrows et la réputation des micro-services.
    """
    def __init__(self, db_path: str = "nexus_tasks_state.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Table des tâches
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    priority TEXT,
                    status TEXT,
                    payload TEXT,
                    result TEXT,
                    error TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            # Table des escrows
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS escrows (
                    escrow_id TEXT PRIMARY KEY,
                    client_address TEXT,
                    provider_address TEXT,
                    amount_usdc REAL,
                    status TEXT,
                    tx_hash TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            # Table de réputation des micro-services
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_reputation (
                    service_name TEXT PRIMARY KEY,
                    total_calls INTEGER,
                    successful_calls INTEGER,
                    failed_calls INTEGER,
                    success_rate REAL,
                    avg_latency_sec REAL
                )
            """)
            conn.commit()

    def save_task(self, task_id: str, task_type: str, priority: str, status: str, payload: dict, result: dict = None, error: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                INSERT OR REPLACE INTO tasks (task_id, task_type, priority, status, payload, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_type, priority, status,
                json.dumps(payload),
                json.dumps(result) if result else None,
                error, now, now
            ))
            conn.commit()

    def save_escrow(self, escrow_id: str, client: str, provider: str, amount: float, status: str, tx_hash: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                INSERT OR REPLACE INTO escrows (escrow_id, client_address, provider_address, amount_usdc, status, tx_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (escrow_id, client, provider, amount, status, tx_hash, now, now))
            conn.commit()

    def update_service_reputation(self, service_name: str, success: bool, latency: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT total_calls, successful_calls, failed_calls, avg_latency_sec FROM service_reputation WHERE service_name = ?", (service_name,))
            row = cursor.fetchone()
            if row:
                tot, succ, fail, avg_lat = row
                tot += 1
                if success:
                    succ += 1
                else:
                    fail += 1
                new_lat = ((avg_lat * (tot - 1)) + latency) / tot
            else:
                tot = 1
                succ = 1 if success else 0
                fail = 0 if success else 1
                new_lat = latency

            succ_rate = (succ / tot) * 100.0
            cursor.execute("""
                INSERT OR REPLACE INTO service_reputation (service_name, total_calls, successful_calls, failed_calls, success_rate, avg_latency_sec)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (service_name, tot, succ, fail, succ_rate, new_lat))
            conn.commit()

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_id, task_type, priority, status, created_at FROM tasks ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [{"task_id": r[0], "task_type": r[1], "priority": r[2], "status": r[3], "created_at": r[4]} for r in rows]
