import sqlite3
import json
import time
import uuid
from typing import Dict, Any, List, Optional

class PersistentMemoryManager:
    """
    Base SQLite persistante en mode WAL (Write-Ahead Logging) pour la cohérence ACID.
    Tables : 'tasks' (état, retry_count, payload), 'audit_logs' (correlation_id, timestamp, level, trace).
    Verrouillage transactionnel pour éviter les race conditions entre sous-agents.
    """
    def __init__(self, db_path: str = "nexus_audit_journal.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    priority TEXT,
                    status TEXT,
                    retry_count INTEGER DEFAULT 0,
                    payload TEXT,
                    result TEXT,
                    error TEXT,
                    correlation_id TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    correlation_id TEXT,
                    timestamp REAL,
                    level TEXT,
                    message TEXT,
                    trace TEXT
                )
            """)
            conn.commit()

    def save_task(
        self,
        task_id: str,
        task_type: str,
        priority: str,
        status: str,
        payload: dict,
        retry_count: int = 0,
        result: dict = None,
        error: str = None,
        correlation_id: str = None
    ):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                INSERT OR REPLACE INTO tasks
                (task_id, task_type, priority, status, retry_count, payload, result, error, correlation_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task_type, priority, status, retry_count,
                json.dumps(payload),
                json.dumps(result) if result else None,
                error, correlation_id, now, now
            ))
            conn.commit()

    def log_audit(self, correlation_id: str, level: str, message: str, trace: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            log_id = f"log_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
                INSERT INTO audit_logs (log_id, correlation_id, timestamp, level, message, trace)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (log_id, correlation_id, time.time(), level, message, trace))
            conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_id, task_type, priority, status, retry_count, payload, result, error, correlation_id FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "task_id": row[0],
                    "task_type": row[1],
                    "priority": row[2],
                    "status": row[3],
                    "retry_count": row[4],
                    "payload": json.loads(row[5]) if row[5] else {},
                    "result": json.loads(row[6]) if row[6] else None,
                    "error": row[7],
                    "correlation_id": row[8]
                }
            return None
