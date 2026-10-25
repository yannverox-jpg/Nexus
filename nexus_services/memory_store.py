"""Small SQLite-backed conversation memory shared with OperationalJournal."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from contextlib import contextmanager
from .sqlite_storage import connect_sqlite


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
