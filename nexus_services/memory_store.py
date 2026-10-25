"""Small SQLite-backed conversation memory shared with OperationalJournal."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from contextlib import contextmanager
try:
    from .sqlite_storage import connect_sqlite
except ImportError:
    from sqlite_storage import connect_sqlite


def configured_database_path() -> str:
    return os.getenv("NEXUS_OPERATIONAL_DB_PATH", "nexus_operational.db")


class ConversationMemory:
    """Persist chat history in the operational SQLite database with secret redaction."""

    _SECRET_PATTERNS = (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key)\s*[:=]\s*[^\s,;]+"),
    )

    @classmethod
    def redact_sensitive_text(cls, content: str) -> str:
        """Remove common credential formats before writing text to persistent storage."""
        result = str(content)
        for pattern in cls._SECRET_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result

    def __init__(self, db_path: Optional[str] = None, timeout: float = 30.0):
        self.db_path = db_path or configured_database_path()
        self.timeout = timeout
        self._memory_uri = None
        self._keeper = None
        if self.db_path == ":memory:":
            self._memory_uri = f"file:nexus_chat_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._keeper = sqlite3.connect(self._memory_uri, uri=True, check_same_thread=False)
        elif not self.db_path.startswith("file:"):
            Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._memory_uri or self.db_path, timeout=self.timeout)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nexus_chat_created ON nexus_chat_messages(conversation_id, id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_memory_facts (
                    fact_key TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'user',
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
            """)

    def add_message(self, conversation_id: str, role: str, content: str,
                    provider: str, model: str) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported chat role")
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO nexus_chat_messages(conversation_id,role,content,provider,model) VALUES(?,?,?,?,?)",
                (conversation_id, role, self.redact_sensitive_text(content), provider, model),
            )
            return int(cursor.lastrowid)

    def recent_messages(self, conversation_id: str, limit: int = 40) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id,conversation_id,role,content,provider,model,created_at "
                "FROM nexus_chat_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                (conversation_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]


    def set_fact(
        self, fact_key: str, content: str, *, category: str = "project",
        source: str = "user",
    ) -> Dict[str, Any]:
        """Upsert a durable user-approved constraint or project fact, rejecting secrets."""
        key = str(fact_key).strip()
        category = str(category).strip()
        value = str(content).strip()
        if not key or len(key) > 100:
            raise ValueError("fact_key must contain 1 to 100 characters")
        if not category or len(category) > 60:
            raise ValueError("category must contain 1 to 60 characters")
        if not value or len(value) > 4000:
            raise ValueError("content must contain 1 to 4000 characters")
        redacted = self.redact_sensitive_text(value)
        if redacted != value:
            raise ValueError("Memory cannot store content that resembles a credential or secret")
        now_source = str(source).strip()[:80] or "user"
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO nexus_memory_facts(fact_key,category,content,source,active)
                VALUES(?,?,?,?,1)
                ON CONFLICT(fact_key) DO UPDATE SET
                    category=excluded.category, content=excluded.content,
                    source=excluded.source, active=1,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (key, category, value, now_source),
            )
            row = conn.execute(
                "SELECT fact_key,category,content,source,active,created_at,updated_at "
                "FROM nexus_memory_facts WHERE fact_key=?", (key,),
            ).fetchone()
        return dict(row)

    def list_facts(self, *, category: str | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT fact_key,category,content,source,active,created_at,updated_at "
                    "FROM nexus_memory_facts WHERE active=1 AND category=? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (category, max(1, min(int(limit), 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT fact_key,category,content,source,active,created_at,updated_at "
                    "FROM nexus_memory_facts WHERE active=1 ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(int(limit), 200)),),
                ).fetchall()
        return [dict(row) for row in rows]

    def delete_fact(self, fact_key: str) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE nexus_memory_facts SET active=0, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE fact_key=? AND active=1",
                (str(fact_key).strip(),),
            )
            return cursor.rowcount > 0
