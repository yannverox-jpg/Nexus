import sqlite3
import json
import time
from typing import Dict, Any, List, Optional

class NexusDatabaseManager:
    """
    Gestionnaire de persistance locale GHOST DB :
    - Registres court terme (Hot Cache / WAL SQLite)
    - Archives long terme (market_events, ai_decisions, historical_shocks)
    """
    def __init__(self, db_path: str = "nexus_tasks_state.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
            # Tables Archives Institutionnelles Long Terme
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_events (
                    event_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    vector_v_d TEXT NOT NULL,
                    spread_s_d TEXT NOT NULL,
                    residual_r_e REAL,
                    timestamp REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_decisions (
                    decision_id TEXT PRIMARY KEY,
                    gemini_intel TEXT,
                    gpt_topology TEXT,
                    claude_report TEXT,
                    readiness_m_global REAL,
                    timestamp REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_shocks (
                    shock_id TEXT PRIMARY KEY,
                    shock_type TEXT NOT NULL,
                    affected_assets TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp REAL NOT NULL
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

    def save_market_event(self, event_id: str, symbol: str, v_d: dict, s_d: dict, r_e: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conn.execute("""
                INSERT OR REPLACE INTO market_events (event_id, symbol, vector_v_d, spread_s_d, residual_r_e, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_id, symbol, json.dumps(v_d), json.dumps(s_d), r_e, time.time()))
            conn.commit()

    def save_ai_decision(self, decision_id: str, gemini_intel: dict, gpt_topology: dict, claude_report: dict, m_global: float):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conn.execute("""
                INSERT OR REPLACE INTO ai_decisions (decision_id, gemini_intel, gpt_topology, claude_report, readiness_m_global, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (decision_id, json.dumps(gemini_intel), json.dumps(gpt_topology), json.dumps(claude_report), m_global, time.time()))
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

    def get_recent_market_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT event_id, symbol, vector_v_d, spread_s_d, residual_r_e, timestamp FROM market_events ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [{
                "event_id": r[0],
                "symbol": r[1],
                "vector_v_d": json.loads(r[2]),
                "spread_s_d": json.loads(r[3]),
                "residual_r_e": r[4],
                "timestamp": r[5]
            } for r in rows]

    def get_recent_ai_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT decision_id, gemini_intel, gpt_topology, claude_report, readiness_m_global, timestamp FROM ai_decisions ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [{
                "decision_id": r[0],
                "gemini_intel": json.loads(r[1]),
                "gpt_topology": json.loads(r[2]),
                "claude_report": json.loads(r[3]),
                "readiness_m_global": r[4],
                "timestamp": r[5]
            } for r in rows]
