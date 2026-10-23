from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Iterator, List, Optional


class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_HUMAN = "WAITING_HUMAN"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventStatus(str, Enum):
    SESSION_CREATED = "SESSION_CREATED"
    RUNTIME_STATE_CHANGED = "RUNTIME_STATE_CHANGED"
    RECOVERY_SCAN_COMPLETED = "RECOVERY_SCAN_COMPLETED"
    MISSION_CREATED = "MISSION_CREATED"
    MISSION_PLAN_RECORDED = "MISSION_PLAN_RECORDED"
    MISSION_STATUS_CHANGED = "MISSION_STATUS_CHANGED"
    TASK_CREATED = "TASK_CREATED"
    TASK_QUEUED = "TASK_QUEUED"
    TASK_REQUEUED = "TASK_REQUEUED"
    TASK_STARTED = "TASK_STARTED"
    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    TOOL_CALL_RECORDED = "TOOL_CALL_RECORDED"
    TOOL_CALL_STARTED = "TOOL_CALL_STARTED"
    TOOL_CALL_FINISHED = "TOOL_CALL_FINISHED"
    FAILURE_RECORDED = "FAILURE_RECORDED"
    RECOVERY_RECORDED = "RECOVERY_RECORDED"
    PROOF_RECORDED = "PROOF_RECORDED"
    PROOF_VERIFIED = "PROOF_VERIFIED"
    TASK_WAITING_APPROVAL = "TASK_WAITING_APPROVAL"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    TASK_WAITING_HUMAN = "TASK_WAITING_HUMAN"
    TASK_RESUMED = "TASK_RESUMED"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    TASK_STEP_RECORDED = "TASK_STEP_RECORDED"
    AGENT_ACTION_RECORDED = "AGENT_ACTION_RECORDED"
    DECISION_RECORDED = "DECISION_RECORDED"
    OPERATION_REJECTED = "OPERATION_REJECTED"
    CIRCUIT_BREAKER_CHANGED = "CIRCUIT_BREAKER_CHANGED"
    WORKER_AUDIT_LOGGED = "WORKER_AUDIT_LOGGED"
    BROWSER_OPENED = "BROWSER_OPENED"
    PAGE_NAVIGATED = "PAGE_NAVIGATED"
    CONTENT_EXTRACTED = "CONTENT_EXTRACTED"
    AI_REQUEST_STARTED = "AI_REQUEST_STARTED"
    AI_RESPONSE_RECEIVED = "AI_RESPONSE_RECEIVED"
    DECISION_MADE = "DECISION_MADE"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_PASSED = "VERIFICATION_PASSED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    BOOT_STARTED = "BOOT_STARTED"
    BOOT_COMPLETED = "BOOT_COMPLETED"


class RuntimeStatus(str, Enum):
    STARTING = "STARTING"
    BOOTING = "BOOTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class ProofState(str, Enum):
    NO_PROOF = "NO_PROOF"
    CLAIMED = "CLAIMED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"


@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    source: str = "NEXUS"
    agent: str = "runtime"
    priority: str = "MEDIUM"
    status: TaskStatus = TaskStatus.PLANNED
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    verified_at: Optional[float] = None
    run_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    correlation_id: Optional[str] = None
    proof: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    mission_id: Optional[str] = None
    execution_mode: str = "UNDECLARED"


@dataclass
class EventRecord:
    event_id: str
    run_id: str
    task_id: Optional[str]
    timestamp: float = field(default_factory=time.time)
    source: str = "nexus"
    agent: str = "runtime"
    stage: str = "BOOT"
    status: EventStatus = EventStatus.TASK_CREATED
    action: str = "CREATE"
    target: str = "runtime"
    proof: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskRepository(ABC):
    @abstractmethod
    def save_task(self, task: TaskRecord) -> TaskRecord:
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_tasks(self, limit: int = 100) -> List[TaskRecord]:
        raise NotImplementedError


class EventRepository(ABC):
    @abstractmethod
    def append_event(self, event: EventRecord) -> EventRecord:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, limit: int = 100) -> List[EventRecord]:
        raise NotImplementedError


class AIProvider(ABC):
    provider: str
    model: str
    status: str = "CONFIGURED"

    @abstractmethod
    async def request(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class Executor(ABC):
    name: str

    @abstractmethod
    async def execute(self, task: TaskRecord, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class Verifier(ABC):
    name: str

    @abstractmethod
    async def verify(self, task: TaskRecord, proof: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class TaskPersistenceAdapter(TaskRepository):
    """Compatibility adapter over the existing NexusDatabaseManager without creating a second task source of truth."""

    def __init__(self, db_manager: Any):
        self.db_manager = db_manager
        self._transition_observer = None

    def set_transition_observer(self, observer: Any) -> None:
        self._transition_observer = observer

    def _notify_transition(
        self,
        task_id: str,
        task_type: str,
        priority: str,
        status: Any,
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        if self._transition_observer is not None:
            self._transition_observer(
                task_id,
                task_type,
                priority,
                self._normalize_status(status),
                result,
                error,
            )

    @staticmethod
    def _normalize_status(status: Any) -> str:
        if isinstance(status, TaskStatus):
            return status.value
        legacy = {
            "ENQUEUED": "QUEUED",
            "PROCESSING": "RUNNING",
            "EXECUTED": "EXECUTED",
            "COMPLETED": "EXECUTED",
            "VERIFIED": "VERIFIED",
            "FAILED": "FAILED",
            "CANCELLED": "CANCELLED",
        }
        value = str(status or TaskStatus.PLANNED.value).upper()
        return legacy.get(value, value)

    def save_task(self, *args, **kwargs) -> Any:
        if args and isinstance(args[0], TaskRecord):
            task = args[0]
            self.db_manager.save_task(
                task.task_id,
                task.task_type,
                task.priority,
                self._normalize_status(task.status),
                task.payload or {},
                result=task.result,
                error=task.error,
            )
            self._notify_transition(
                task.task_id,
                task.task_type,
                task.priority,
                task.status,
                task.result,
                task.error,
            )
            return task

        task_id, task_type, priority, status, payload = args[:5]
        result = kwargs.get("result")
        error = kwargs.get("error")
        if len(args) > 5:
            result = args[5]
        if len(args) > 6:
            error = args[6]
        self.db_manager.save_task(
            task_id,
            task_type,
            priority,
            status,
            payload or {},
            result=result,
            error=error,
        )
        self._notify_transition(task_id, task_type, priority, status, result, error)
        return task_id

    def save_task_legacy(
        self,
        task_id: str,
        task_type: str,
        priority: str,
        status: str,
        payload: Dict[str, Any],
        retry_count: int = 0,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        self.db_manager.save_task(
            task_id,
            task_type,
            priority,
            status,
            payload or {},
            result=result,
            error=error,
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        rows = self.db_manager.get_all_tasks() if hasattr(self.db_manager, "get_all_tasks") else []
        for row in rows:
            if row.get("task_id") == task_id:
                legacy_status = row.get("status", "PLANNED")
                status = {
                    "ENQUEUED": TaskStatus.QUEUED,
                    "PROCESSING": TaskStatus.RUNNING,
                    "COMPLETED": TaskStatus.EXECUTED,
                    "EXECUTED": TaskStatus.EXECUTED,
                    "VERIFIED": TaskStatus.VERIFIED,
                    "FAILED": TaskStatus.FAILED,
                    "CANCELLED": TaskStatus.CANCELLED,
                }.get(str(legacy_status).upper(), TaskStatus.PLANNED)
                return TaskRecord(
                    task_id=row.get("task_id", task_id),
                    task_type=row.get("task_type", "UNKNOWN"),
                    source="NEXUS",
                    agent="runtime",
                    priority=row.get("priority", "MEDIUM"),
                    status=status,
                    payload=row.get("payload", {}) or {},
                    result=row.get("result"),
                    error=row.get("error"),
                    created_at=float(row.get("created_at", time.time())),
                    updated_at=float(row.get("updated_at", time.time())),
                    proof={},
                    metadata={},
                )
        return None

    def list_tasks(self, limit: int = 100) -> List[TaskRecord]:
        rows = self.db_manager.get_all_tasks() if hasattr(self.db_manager, "get_all_tasks") else []
        tasks: List[TaskRecord] = []
        for row in rows[:limit]:
            task = self.get_task(row.get("task_id"))
            if task is not None:
                tasks.append(task)
        return tasks

    def log_audit(self, correlation_id: str, level: str, message: str, trace: Optional[str] = None):
        if hasattr(self.db_manager, "log_audit"):
            self.db_manager.log_audit(correlation_id, level, message, trace)


class SQLiteTaskRepository(TaskRepository):
    def __init__(self, db_path: str = "nexus_tasks_state.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db_path = self.db_path
        if db_path == ":memory:":
            db_path = "file::memory:?cache=shared"
        conn = sqlite3.connect(db_path, uri=db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    source TEXT,
                    agent TEXT,
                    priority TEXT,
                    status TEXT,
                    payload TEXT,
                    result TEXT,
                    error TEXT,
                    created_at REAL,
                    updated_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    verified_at REAL,
                    run_id TEXT,
                    parent_task_id TEXT,
                    correlation_id TEXT,
                    proof TEXT,
                    metadata TEXT
                )
                """
            )
            conn.commit()

    def save_task(self, task: TaskRecord) -> TaskRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, source, agent, priority, status, payload, result, error,
                    created_at, updated_at, started_at, completed_at, verified_at, run_id,
                    parent_task_id, correlation_id, proof, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type = excluded.task_type,
                    source = excluded.source,
                    agent = excluded.agent,
                    priority = excluded.priority,
                    status = excluded.status,
                    payload = excluded.payload,
                    result = excluded.result,
                    error = excluded.error,
                    updated_at = excluded.updated_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    verified_at = excluded.verified_at,
                    run_id = excluded.run_id,
                    parent_task_id = excluded.parent_task_id,
                    correlation_id = excluded.correlation_id,
                    proof = excluded.proof,
                    metadata = excluded.metadata
                """,
                (
                    task.task_id,
                    task.task_type,
                    task.source,
                    task.agent,
                    task.priority,
                    task.status.value,
                    json.dumps(task.payload),
                    json.dumps(task.result) if task.result is not None else None,
                    task.error,
                    task.created_at,
                    task.updated_at,
                    task.started_at,
                    task.completed_at,
                    task.verified_at,
                    task.run_id,
                    task.parent_task_id,
                    task.correlation_id,
                    json.dumps(task.proof),
                    json.dumps(task.metadata),
                ),
            )
            conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskRecord(
            task_id=row["task_id"],
            task_type=row["task_type"],
            source=row["source"],
            agent=row["agent"],
            priority=row["priority"],
            status=TaskStatus(row["status"]),
            payload=json.loads(row["payload"]) if row["payload"] else {},
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            verified_at=row["verified_at"],
            run_id=row["run_id"],
            parent_task_id=row["parent_task_id"],
            correlation_id=row["correlation_id"],
            proof=json.loads(row["proof"]) if row["proof"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def list_tasks(self, limit: int = 100) -> List[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.get_task(row["task_id"]) for row in rows]


class InMemoryEventRepository(EventRepository):
    """Temporary compatibility layer for runtime events without creating a separate SQLite event database."""

    def __init__(self):
        self._events: List[EventRecord] = []

    def append_event(self, event: EventRecord) -> EventRecord:
        self._events.append(event)
        return event

    def list_events(self, limit: int = 100) -> List[EventRecord]:
        return list(reversed(self._events))[:limit]


class JournalError(RuntimeError):
    """Base error for rejected or invalid operational journal operations."""


class InvalidTransitionError(JournalError):
    """Raised when a task state transition is not allowed."""


class OperationalJournal(TaskRepository, EventRepository):
    """Transactional SQLite journal implementing the existing task/event contracts."""

    STATUSES = tuple(status.value for status in TaskStatus)
    SENSITIVE_KEY_PARTS = (
        "password",
        "passwd",
        "secret",
        "privatekey",
        "private_key",
        "token",
        "authorization",
        "credential",
        "api_key",
        "apikey",
    )
    SECRET_VALUE_PATTERN = re.compile(
        r"(?i)\b(password|passwd|secret|private[_ -]?key|access[_ -]?token|token|authorization|api[_ -]?key)"
        r"(\s*[:=]\s*)([^,\s;]+)"
    )
    URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(https?://)[^/@:\s]+:[^/@\s]+@")
    URL_SECRET_QUERY_PATTERN = re.compile(
        r"(?i)([?&](?:token|access_token|api_key|apikey|secret|password|"
        r"authorization|session|cookie|credential|code)=)[^&#\s]+"
    )
    BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")

    def __init__(self, db_path: Optional[str] = None, timeout: float = 30.0):
        self.db_path = db_path or os.getenv(
            "NEXUS_OPERATIONAL_DB_PATH", "nexus_operational.db"
        )
        self.timeout = timeout
        self._memory_uri: Optional[str] = None
        self._keeper: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._memory_uri = f"file:nexus_journal_{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._keeper = sqlite3.connect(
                self._memory_uri, uri=True, timeout=self.timeout, check_same_thread=False
            )
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_uri:
            conn = sqlite3.connect(
                self._memory_uri,
                uri=True,
                timeout=self.timeout,
                check_same_thread=False,
            )
        else:
            conn = sqlite3.connect(
                self.db_path, timeout=self.timeout, check_same_thread=False
            )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)}")
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._memory_uri:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    @classmethod
    def _redact(cls, value: Any, key: str = "") -> Any:
        normalized_key = re.sub(r"[^a-z0-9_]", "", key.lower())
        if any(part in normalized_key for part in cls.SENSITIVE_KEY_PARTS):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(k): cls._redact(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._redact(item) for item in value]
        if isinstance(value, str):
            value = cls.SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED]", value)
            value = cls.URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]@", value)
            value = cls.URL_SECRET_QUERY_PATTERN.sub(
                lambda match: match.group(1) + "[REDACTED]", value
            )
            return cls.BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        if isinstance(value, (bytes, bytearray)):
            return f"[BINARY {len(value)} bytes]"
        return value

    @classmethod
    def _json(cls, value: Any) -> str:
        return json.dumps(cls._redact(value), ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _decode(value: Optional[str], default: Any = None) -> Any:
        if value is None:
            return default
        return json.loads(value)

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    correlation_id TEXT,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    mission_id TEXT REFERENCES missions(mission_id),
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    parent_task_id TEXT REFERENCES tasks(task_id),
                    task_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'PLANNED', 'QUEUED', 'RUNNING', 'WAITING_APPROVAL',
                        'WAITING_HUMAN', 'EXECUTED', 'VERIFIED', 'FAILED', 'CANCELLED'
                    )),
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    source TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'REAL',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    executed_at REAL,
                    verified_at REAL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_mission_status
                    ON tasks(mission_id, status);
                CREATE INDEX IF NOT EXISTS idx_tasks_correlation
                    ON tasks(correlation_id);
                CREATE TABLE IF NOT EXISTS task_steps (
                    step_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    sequence INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    ended_at REAL,
                    result_json TEXT,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(task_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT REFERENCES tasks(task_id),
                    step_id TEXT REFERENCES task_steps(step_id),
                    correlation_id TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at REAL NOT NULL,
                    details_json TEXT NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_task_events_task_time
                    ON task_events(task_id, occurred_at);
                CREATE INDEX IF NOT EXISTS idx_task_events_correlation
                    ON task_events(correlation_id);
                CREATE TRIGGER IF NOT EXISTS task_events_no_update
                    BEFORE UPDATE ON task_events BEGIN
                        SELECT RAISE(ABORT, 'task_events are append-only');
                    END;
                CREATE TRIGGER IF NOT EXISTS task_events_no_delete
                    BEFORE DELETE ON task_events BEGIN
                        SELECT RAISE(ABORT, 'task_events are append-only');
                    END;
                CREATE TABLE IF NOT EXISTS agent_actions (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT REFERENCES tasks(task_id),
                    step_id TEXT REFERENCES task_steps(step_id),
                    agent TEXT NOT NULL,
                    action TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    input_json TEXT NOT NULL,
                    result_json TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT REFERENCES tasks(task_id),
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    question TEXT NOT NULL,
                    context_summary TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    justification_summary TEXT NOT NULL,
                    confidence REAL,
                    risk TEXT,
                    expected_outcome TEXT
                );
                CREATE TABLE IF NOT EXISTS execution_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    step_id TEXT REFERENCES task_steps(step_id),
                    correlation_id TEXT,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    worker TEXT,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    result_json TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(task_id, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS tool_calls (
                    tool_call_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    attempt_id TEXT NOT NULL REFERENCES execution_attempts(attempt_id),
                    correlation_id TEXT,
                    step_id TEXT REFERENCES task_steps(step_id),
                    tool_name TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    target TEXT,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    external_id TEXT,
                    request_json TEXT NOT NULL,
                    response_json TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS failures (
                    failure_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    attempt_id TEXT REFERENCES execution_attempts(attempt_id),
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    recoverable INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recovery_actions (
                    recovery_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    failure_id TEXT REFERENCES failures(failure_id),
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    applied_at REAL,
                    result_json TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    resolved_by TEXT,
                    reason TEXT,
                    source TEXT NOT NULL,
                    requested_at REAL NOT NULL,
                    resolved_at REAL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proofs (
                    proof_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    step_id TEXT REFERENCES task_steps(step_id),
                    attempt_id TEXT REFERENCES execution_attempts(attempt_id),
                    tool_call_id TEXT REFERENCES tool_calls(tool_call_id),
                    proof_type TEXT NOT NULL,
                    value TEXT,
                    uri TEXT,
                    sha256 TEXT,
                    execution_mode TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    collected_at REAL,
                    reference TEXT,
                    evidence_hash TEXT,
                    verified INTEGER NOT NULL DEFAULT 0,
                    verification_status TEXT NOT NULL DEFAULT 'PENDING',
                    verification_reason TEXT,
                    verifier TEXT,
                    verification_json TEXT,
                    verified_at REAL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT REFERENCES tasks(task_id),
                    step_id TEXT REFERENCES task_steps(step_id),
                    kind TEXT NOT NULL,
                    target TEXT,
                    source TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    data_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES runtime_sessions(session_id),
                    mission_id TEXT REFERENCES missions(mission_id),
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    proof_id TEXT REFERENCES proofs(proof_id),
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                """
            )
            mission_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(missions)")
            }
            if "correlation_id" not in mission_columns:
                conn.execute("ALTER TABLE missions ADD COLUMN correlation_id TEXT")
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_missions_correlation
                   ON missions(correlation_id) WHERE correlation_id IS NOT NULL"""
            )
            attempt_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(execution_attempts)")
            }
            for column, definition in (
                ("correlation_id", "TEXT"),
                ("worker", "TEXT"),
                ("result_json", "TEXT"),
            ):
                if column not in attempt_columns:
                    conn.execute(
                        f"ALTER TABLE execution_attempts ADD COLUMN {column} {definition}"
                    )
            tool_call_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(tool_calls)")
            }
            if "target" not in tool_call_columns:
                conn.execute("ALTER TABLE tool_calls ADD COLUMN target TEXT")
            if "correlation_id" not in tool_call_columns:
                conn.execute("ALTER TABLE tool_calls ADD COLUMN correlation_id TEXT")
            proof_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(proofs)")
            }
            for column, definition in (
                ("collected_at", "REAL"),
                ("reference", "TEXT"),
                ("evidence_hash", "TEXT"),
                ("verification_status", "TEXT NOT NULL DEFAULT 'PENDING'"),
                ("verification_reason", "TEXT"),
            ):
                if column not in proof_columns:
                    conn.execute(f"ALTER TABLE proofs ADD COLUMN {column} {definition}")
            conn.execute(
                """UPDATE proofs SET collected_at = created_at
                   WHERE collected_at IS NULL"""
            )
            conn.execute(
                """UPDATE proofs SET reference = uri
                   WHERE reference IS NULL AND uri IS NOT NULL"""
            )
            conn.execute(
                """UPDATE proofs SET evidence_hash = sha256
                   WHERE evidence_hash IS NULL AND sha256 IS NOT NULL"""
            )

    @classmethod
    def _event(
        cls,
        conn: sqlite3.Connection,
        *,
        event_id: Optional[str] = None,
        event_type: str,
        status: EventStatus,
        session_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        task_id: Optional[str] = None,
        step_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        source: str = "nexus",
        actor: str = "runtime",
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        occurred_at: Optional[float] = None,
    ) -> str:
        event_id = event_id or cls._new_id("evt")
        conn.execute(
            """
            INSERT INTO task_events (
                event_id, session_id, mission_id, task_id, step_id, correlation_id,
                event_type, status, source, actor, occurred_at, details_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, session_id, mission_id, task_id, step_id, correlation_id,
                event_type, status.value, source, actor, occurred_at or time.time(),
                cls._json(details or {}), cls._redact(error) if error else None,
            ),
        )
        return event_id

    def _reject(self, task_id: Optional[str], operation: str, error: str) -> None:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT mission_id, session_id, correlation_id FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone() if task_id else None
            self._event(
                conn,
                event_type="OPERATION_REJECTED",
                status=EventStatus.OPERATION_REJECTED,
                task_id=task_id,
                mission_id=row["mission_id"] if row else None,
                session_id=row["session_id"] if row else None,
                correlation_id=row["correlation_id"] if row else None,
                details={"operation": operation},
                error=error,
            )

    def _task(self, conn: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise JournalError(f"Unknown task: {task_id}")
        return row

    @classmethod
    def _to_task(cls, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            task_type=row["task_type"],
            source=row["source"],
            agent="runtime",
            priority=row["priority"],
            status=TaskStatus(row["status"]),
            payload=cls._decode(row["payload_json"], {}),
            result=cls._decode(row["result_json"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["executed_at"],
            verified_at=row["verified_at"],
            run_id=row["session_id"],
            parent_task_id=row["parent_task_id"],
            correlation_id=row["correlation_id"],
            proof={},
            metadata=cls._decode(row["metadata_json"], {}),
            mission_id=row["mission_id"],
            execution_mode=row["execution_mode"],
        )

    def create_session(
        self, session_id: Optional[str] = None, source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        session_id = session_id or self._new_id("session")
        now = time.time()
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO runtime_sessions
                   (session_id, started_at, status, source, metadata_json)
                   VALUES (?, ?, 'STARTING', ?, ?)""",
                (session_id, now, self._redact(source), self._json(metadata or {})),
            )
            self._event(
                conn, event_type="SESSION_CREATED", status=EventStatus.SESSION_CREATED,
                session_id=session_id, source=source, details={"session_id": session_id},
                occurred_at=now,
            )
        return session_id

    def get_runtime_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.get_record("runtime_sessions", session_id)

    def list_runtime_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM runtime_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_runtime_session(
        self, session_id: str, status: RuntimeStatus, *,
        source: str = "nexus_runtime", metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        now = time.time()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise JournalError(f"Unknown runtime session: {session_id}")
            if row["status"] == RuntimeStatus.STOPPED.value:
                raise InvalidTransitionError("A stopped runtime session cannot be restarted")
            terminal_time = now if status in (RuntimeStatus.STOPPED, RuntimeStatus.ERROR) else None
            conn.execute(
                """UPDATE runtime_sessions SET status = ?, ended_at = ?
                   WHERE session_id = ?""",
                (status.value, terminal_time, session_id),
            )
            self._event(
                conn, event_type="RUNTIME_STATE_CHANGED",
                status=EventStatus.RUNTIME_STATE_CHANGED, session_id=session_id,
                source=source,
                details={"from": row["status"], "to": status.value, **(metadata or {})},
                occurred_at=now,
            )
            updated = conn.execute(
                "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(updated)

    def create_mission(
        self, objective: str, *, session_id: Optional[str] = None,
        mission_id: Optional[str] = None, source: str = "nexus",
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        mission_id = mission_id or self._new_id("mission")
        now = time.time()
        with self._transaction() as conn:
            self._validate_session(conn, session_id)
            conn.execute(
                """INSERT INTO missions
                   (mission_id, session_id, correlation_id, objective, status, source,
                    created_at, updated_at, metadata_json)
                   VALUES (?, ?, ?, ?, 'PLANNED', ?, ?, ?, ?)""",
                (mission_id, session_id, correlation_id, self._redact(objective),
                 self._redact(source), now, now, self._json(metadata or {})),
            )
            self._event(
                conn, event_type="MISSION_CREATED", status=EventStatus.MISSION_CREATED,
                session_id=session_id, mission_id=mission_id, source=source,
                correlation_id=correlation_id,
                details={
                    "stage": "RECEIVE",
                    "objective": self._redact(objective),
                },
                occurred_at=now,
            )
        return mission_id

    def record_mission_plan(
        self, mission_id: str, *, source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._transaction() as conn:
            mission = conn.execute(
                "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
            ).fetchone()
            if mission is None:
                raise JournalError(f"Unknown mission: {mission_id}")
            tasks = conn.execute(
                """SELECT task_id, task_type, priority, status FROM tasks
                   WHERE mission_id = ? ORDER BY created_at, rowid""",
                (mission_id,),
            ).fetchall()
            self._event(
                conn,
                event_type="MISSION_PLAN_RECORDED",
                status=EventStatus.MISSION_PLAN_RECORDED,
                session_id=mission["session_id"],
                mission_id=mission_id,
                correlation_id=mission["correlation_id"],
                source=source,
                details={
                    "stage": "PLAN",
                    "task_count": len(tasks),
                    "tasks": [
                        {
                            "task_id": task["task_id"],
                            "task_type": task["task_type"],
                            "priority": task["priority"],
                            "status": task["status"],
                        }
                        for task in tasks
                    ],
                    **(metadata or {}),
                },
            )

    def get_mission_by_correlation(self, correlation_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM missions WHERE correlation_id = ?", (correlation_id,)
            ).fetchone()
            return dict(row) if row else None

    def _refresh_mission_status(
        self, conn: sqlite3.Connection, mission_id: Optional[str],
        *, source: str, occurred_at: Optional[float] = None,
    ) -> None:
        if mission_id is None:
            return
        mission = conn.execute(
            "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if mission is None:
            return
        statuses = [
            TaskStatus(row["status"])
            for row in conn.execute(
                "SELECT status FROM tasks WHERE mission_id = ?", (mission_id,)
            ).fetchall()
        ]
        if not statuses:
            next_status = "PLANNED"
        elif TaskStatus.WAITING_APPROVAL in statuses:
            next_status = TaskStatus.WAITING_APPROVAL.value
        elif TaskStatus.WAITING_HUMAN in statuses:
            next_status = TaskStatus.WAITING_HUMAN.value
        elif TaskStatus.RUNNING in statuses:
            next_status = TaskStatus.RUNNING.value
        elif TaskStatus.QUEUED in statuses:
            next_status = TaskStatus.QUEUED.value
        elif TaskStatus.PLANNED in statuses:
            next_status = TaskStatus.PLANNED.value
        elif all(
            status in (
                TaskStatus.EXECUTED, TaskStatus.VERIFIED,
                TaskStatus.FAILED, TaskStatus.CANCELLED,
            )
            for status in statuses
        ):
            if all(status == TaskStatus.VERIFIED for status in statuses):
                next_status = TaskStatus.VERIFIED.value
            elif TaskStatus.FAILED in statuses:
                next_status = TaskStatus.FAILED.value
            elif all(status == TaskStatus.CANCELLED for status in statuses):
                next_status = TaskStatus.CANCELLED.value
            else:
                next_status = TaskStatus.EXECUTED.value
        else:
            next_status = "PLANNED"

        previous_status = mission["status"]
        if previous_status == next_status:
            return
        now = occurred_at or time.time()
        conn.execute(
            "UPDATE missions SET status = ?, updated_at = ? WHERE mission_id = ?",
            (next_status, now, mission_id),
        )
        self._event(
            conn,
            event_type="MISSION_STATUS_CHANGED",
            status=EventStatus.MISSION_STATUS_CHANGED,
            session_id=mission["session_id"],
            mission_id=mission_id,
            correlation_id=mission["correlation_id"],
            source=source,
            details={
                "stage": "MISSION_LIFECYCLE",
                "from": previous_status,
                "to": next_status,
            },
            occurred_at=now,
        )

    def list_tasks_for_mission(self, mission_id: str) -> List[TaskRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks WHERE mission_id = ?
                   ORDER BY created_at ASC, rowid ASC""",
                (mission_id,),
            ).fetchall()
            return [self._to_task(row) for row in rows]

    @staticmethod
    def _validate_session(conn: sqlite3.Connection, session_id: Optional[str]) -> None:
        if session_id and not conn.execute(
            "SELECT 1 FROM runtime_sessions WHERE session_id = ?", (session_id,)
        ).fetchone():
            raise JournalError(f"Unknown runtime session: {session_id}")

    def create_task(
        self, task_type: str, payload: Optional[Dict[str, Any]] = None, *,
        mission_id: Optional[str] = None, session_id: Optional[str] = None,
        parent_task_id: Optional[str] = None, task_id: Optional[str] = None,
        priority: str = "MEDIUM", source: str = "nexus",
        correlation_id: Optional[str] = None, execution_mode: str = "REAL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> TaskRecord:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED", "UNDECLARED"):
            raise ValueError("execution_mode must be REAL, SIMULATED, or UNDECLARED")
        task_id = task_id or self._new_id("task")
        correlation_id = correlation_id or self._new_id("corr")
        now = time.time()
        with self._transaction() as conn:
            self._validate_session(conn, session_id)
            if mission_id and not conn.execute(
                "SELECT 1 FROM missions WHERE mission_id = ?", (mission_id,)
            ).fetchone():
                raise JournalError(f"Unknown mission: {mission_id}")
            conn.execute(
                """INSERT INTO tasks (
                    task_id, mission_id, session_id, parent_task_id, task_type, priority,
                    status, payload_json, source, correlation_id, execution_mode,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'PLANNED', ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, mission_id, session_id, parent_task_id, task_type, priority,
                 self._json(payload or {}), self._redact(source), correlation_id,
                 execution_mode.upper(), now, now, self._json(metadata or {})),
            )
            self._event(
                conn, event_type="TASK_CREATED", status=EventStatus.TASK_CREATED,
                session_id=session_id, mission_id=mission_id, task_id=task_id,
                correlation_id=correlation_id, source=source,
                details={"task_type": task_type, "status": TaskStatus.PLANNED.value},
                occurred_at=now,
            )
            return self._to_task(self._task(conn, task_id))

    def save_task(self, task: TaskRecord) -> TaskRecord:
        if task.status != TaskStatus.PLANNED:
            raise JournalError("OperationalJournal.save_task only creates PLANNED tasks; use transition methods.")
        return self.create_task(
            task.task_type, task.payload, mission_id=task.metadata.get("mission_id"),
            session_id=task.run_id, parent_task_id=task.parent_task_id,
            task_id=task.task_id, priority=task.priority, source=task.source,
            correlation_id=task.correlation_id, execution_mode=task.execution_mode,
            metadata=task.metadata,
        )

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return self._to_task(row) if row else None

    def get_task_by_correlation(self, correlation_id: str) -> Optional[TaskRecord]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE correlation_id = ?",
                (correlation_id,),
            ).fetchone()
            return self._to_task(row) if row else None

    def list_tasks(self, limit: Optional[int] = 100) -> List[TaskRecord]:
        with self._connection() as conn:
            query = "SELECT * FROM tasks ORDER BY created_at DESC"
            rows = (
                conn.execute(query).fetchall()
                if limit is None else
                conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
            )
            return [self._to_task(row) for row in rows]

    def list_tasks_by_status(
        self, statuses: Iterable[TaskStatus], limit: int = 1000
    ) -> List[TaskRecord]:
        values = tuple(status.value for status in statuses)
        if not values:
            return []
        placeholders = ", ".join("?" for _ in values)
        with self._connection() as conn:
            rows = conn.execute(
                f"""SELECT * FROM tasks WHERE status IN ({placeholders})
                    ORDER BY created_at ASC LIMIT ?""",
                (*values, limit),
            ).fetchall()
            return [self._to_task(row) for row in rows]

    def list_missions(self, limit: Optional[int] = 1000) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            query = "SELECT * FROM missions ORDER BY created_at ASC"
            rows = (
                conn.execute(query).fetchall()
                if limit is None else
                conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
            )
            return [dict(row) for row in rows]

    def get_recovery_snapshot(self) -> Dict[str, Any]:
        non_terminal = self.list_tasks_by_status(
            (
                TaskStatus.PLANNED,
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
                TaskStatus.WAITING_APPROVAL,
                TaskStatus.WAITING_HUMAN,
                TaskStatus.EXECUTED,
            )
        )
        ambiguous_running = [
            task for task in non_terminal if task.status == TaskStatus.RUNNING
        ]
        failed = self.list_tasks_by_status((TaskStatus.FAILED,))
        relevant_mission_ids = {
            task.mission_id for task in non_terminal + failed if task.mission_id
        }
        missions = [
            mission for mission in self.list_missions()
            if mission["mission_id"] in relevant_mission_ids
        ]
        return {
            "missions": missions,
            "non_terminal_tasks": non_terminal,
            "running_tasks_requiring_reconciliation": ambiguous_running,
            "failed_tasks_requiring_recovery_decision": failed,
        }

    def _transition(
        self, task_id: str, target: TaskStatus, *, allowed: Iterable[TaskStatus],
        event_status: EventStatus, event_type: str, actor: str = "runtime",
        source: str = "nexus", details: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None, error: Optional[str] = None,
        recovery_id: Optional[str] = None
    ) -> TaskRecord:
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                current = TaskStatus(task["status"])
                if current not in allowed:
                    raise InvalidTransitionError(
                        f"Cannot transition task {task_id} from {current.value} to {target.value}"
                    )
                if target == TaskStatus.QUEUED and current == TaskStatus.FAILED:
                    recovery = conn.execute(
                        """SELECT recovery_id FROM recovery_actions
                           WHERE recovery_id = ? AND task_id = ? AND action = 'RETRY'
                           AND status = 'RECORDED'""",
                        (recovery_id, task_id),
                    ).fetchone()
                    if recovery is None:
                        raise InvalidTransitionError(
                            "FAILED tasks require a recorded RETRY recovery action before re-queueing"
                        )
                    conn.execute(
                        "UPDATE recovery_actions SET status = 'APPLIED', applied_at = ? WHERE recovery_id = ?",
                        (time.time(), recovery_id),
                    )
                now = time.time()
                updates = ["status = ?", "updated_at = ?"]
                values: List[Any] = [target.value, now]
                if target == TaskStatus.RUNNING:
                    updates.append("started_at = COALESCE(started_at, ?)")
                    values.append(now)
                elif target == TaskStatus.EXECUTED:
                    updates.append("executed_at = ?")
                    values.append(now)
                    updates.append("result_json = ?")
                    values.append(self._json(result or {}))
                    updates.append("execution_mode = ?")
                    values.append(str((details or {}).get("execution_mode", task["execution_mode"])).upper())
                elif target == TaskStatus.VERIFIED:
                    updates.append("verified_at = ?")
                    values.append(now)
                elif target == TaskStatus.FAILED:
                    updates.append("error = ?")
                    values.append(self._redact(error or "Task failed"))
                values.append(task_id)
                conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", values)
                if target in (TaskStatus.WAITING_HUMAN, TaskStatus.WAITING_APPROVAL):
                    conn.execute(
                        """UPDATE execution_attempts SET status = ?, ended_at = ?
                           WHERE task_id = ? AND ended_at IS NULL""",
                        (target.value, now, task_id),
                    )
                transition_details = {
                    "from": current.value,
                    "to": target.value,
                    **(details or {}),
                }
                if target in (
                    TaskStatus.VERIFIED, TaskStatus.FAILED, TaskStatus.CANCELLED,
                ):
                    transition_details["stage"] = "FINALIZE"
                self._event(
                    conn, event_type=event_type, status=event_status,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source, actor=actor,
                    details=transition_details,
                    error=error, occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task_id))
        except InvalidTransitionError as exc:
            self._reject(task_id, event_type, str(exc))
            raise

    def queue_task(self, task_id: str, *, recovery_id: Optional[str] = None,
                   source: str = "nexus") -> TaskRecord:
        return self._transition(
            task_id, TaskStatus.QUEUED,
            allowed=(TaskStatus.PLANNED, TaskStatus.FAILED),
            event_status=EventStatus.TASK_QUEUED if recovery_id is None else EventStatus.TASK_REQUEUED,
            event_type="TASK_QUEUED" if recovery_id is None else "TASK_REQUEUED",
            source=source, recovery_id=recovery_id,
        )

    def start_task(self, task_id: str, *, source: str = "nexus") -> TaskRecord:
        return self._transition(
            task_id, TaskStatus.RUNNING, allowed=(TaskStatus.QUEUED,),
            event_status=EventStatus.TASK_STARTED, event_type="TASK_STARTED", source=source,
        )

    def start_task_attempt(
        self, task_id: str, execution_mode: str, *, worker: Optional[str] = None,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[TaskRecord, str]:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED", "UNDECLARED"):
            raise ValueError("execution_mode must be REAL, SIMULATED, or UNDECLARED")
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                if TaskStatus(task["status"]) != TaskStatus.QUEUED:
                    raise InvalidTransitionError(
                        f"Cannot start task {task_id} from {task['status']}"
                    )
                now = time.time()
                conn.execute(
                    """UPDATE tasks SET status = 'RUNNING', started_at = COALESCE(started_at, ?),
                       updated_at = ?, execution_mode = ? WHERE task_id = ?""",
                    (now, now, execution_mode, task_id),
                )
                number = conn.execute(
                    """SELECT COALESCE(MAX(attempt_number), 0) + 1
                       FROM execution_attempts WHERE task_id = ?""",
                    (task_id,),
                ).fetchone()[0]
                attempt_id = self._new_id("attempt")
                conn.execute(
                    """INSERT INTO execution_attempts (
                        attempt_id, session_id, mission_id, task_id, correlation_id,
                        attempt_number, status, execution_mode, source, worker,
                        started_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?)""",
                    (
                        attempt_id, task["session_id"], task["mission_id"], task_id,
                        task["correlation_id"], number, execution_mode, source,
                        worker, now, self._json(metadata or {}),
                    ),
                )
                self._event(
                    conn, event_type="TASK_STARTED", status=EventStatus.TASK_STARTED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source, details={"from": TaskStatus.QUEUED.value,
                                            "to": TaskStatus.RUNNING.value},
                    occurred_at=now,
                )
                self._event(
                    conn, event_type="ATTEMPT_STARTED", status=EventStatus.ATTEMPT_STARTED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source,
                    details={"stage": "EXECUTE",
                             "attempt_id": attempt_id, "attempt_number": number,
                             "execution_mode": execution_mode, "worker": worker},
                    occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task_id)), attempt_id
        except InvalidTransitionError as exc:
            self._reject(task_id, "TASK_STARTED", str(exc))
            raise

    def start_attempt(
        self, task_id: str, execution_mode: str, *, source: str = "nexus",
        step_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED"):
            raise ValueError("execution_mode must be REAL or SIMULATED")
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                if TaskStatus(task["status"]) != TaskStatus.RUNNING:
                    raise InvalidTransitionError("An attempt can start only for a RUNNING task")
                if step_id and not conn.execute(
                    "SELECT 1 FROM task_steps WHERE step_id = ? AND task_id = ?",
                    (step_id, task_id),
                ).fetchone():
                    raise JournalError("Attempt step does not belong to the task")
                active = conn.execute(
                    "SELECT 1 FROM execution_attempts WHERE task_id = ? AND ended_at IS NULL",
                    (task_id,),
                ).fetchone()
                if active:
                    raise InvalidTransitionError("Task already has an active execution attempt")
                number = conn.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM execution_attempts WHERE task_id = ?",
                    (task_id,),
                ).fetchone()[0]
                attempt_id, now = self._new_id("attempt"), time.time()
                conn.execute(
                    """INSERT INTO execution_attempts (
                        attempt_id, session_id, mission_id, task_id, step_id, correlation_id,
                        attempt_number, status, execution_mode, source, worker, started_at,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?)""",
                    (attempt_id, task["session_id"], task["mission_id"], task_id,
                     step_id, task["correlation_id"], number, execution_mode, source,
                     (metadata or {}).get("worker"), now, self._json(metadata or {})),
                )
                conn.execute(
                    "UPDATE tasks SET execution_mode = ?, updated_at = ? WHERE task_id = ?",
                    (execution_mode, now, task_id),
                )
                self._event(
                    conn, event_type="ATTEMPT_STARTED", status=EventStatus.ATTEMPT_STARTED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"], source=source,
                    details={"attempt_id": attempt_id, "attempt_number": number,
                             "execution_mode": execution_mode}, occurred_at=now,
                )
                return attempt_id
        except InvalidTransitionError as exc:
            self._reject(task_id, "ATTEMPT_STARTED", str(exc))
            raise

    def record_tool_call(
        self, task_id: str, attempt_id: str, tool_name: str, operation: str, *,
        execution_mode: str, status: str = "COMPLETED",
        request: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        external_id: Optional[str] = None, error: Optional[str] = None,
        step_id: Optional[str] = None, target: Optional[str] = None,
        source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED", "UNDECLARED"):
            raise ValueError("execution_mode must be REAL, SIMULATED, or UNDECLARED")
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                attempt = conn.execute(
                    "SELECT * FROM execution_attempts WHERE attempt_id = ? AND task_id = ?",
                    (attempt_id, task_id),
                ).fetchone()
                if attempt is None or attempt["ended_at"] is not None:
                    raise InvalidTransitionError("Tool call requires an active task attempt")
                if step_id and attempt["step_id"] and step_id != attempt["step_id"]:
                    raise JournalError("Tool-call step does not match its attempt")
                step_id = step_id or attempt["step_id"]
                if attempt["execution_mode"] == "SIMULATED":
                    execution_mode = "SIMULATED"
                call_id, now = self._new_id("tool"), time.time()
                conn.execute(
                    """INSERT INTO tool_calls (
                        tool_call_id, session_id, mission_id, task_id, attempt_id,
                        correlation_id, step_id,
                        tool_name, operation, status, execution_mode, source, target, started_at,
                        completed_at, external_id, request_json, response_json, error, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (call_id, task["session_id"], task["mission_id"], task_id, attempt_id,
                     task["correlation_id"], step_id, tool_name, operation, status,
                     execution_mode, source,
                     self._redact(target), now, now, self._redact(external_id), self._json(request or {}),
                     self._json(response) if response is not None else None,
                     self._redact(error) if error else None, self._json(metadata or {})),
                )
                self._event(
                    conn, event_type="TOOL_CALL_RECORDED",
                    status=EventStatus.TOOL_CALL_RECORDED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, step_id=step_id,
                    correlation_id=task["correlation_id"], source=source,
                    details={"tool_call_id": call_id, "tool": tool_name,
                             "operation": operation, "target": target, "status": status,
                             "execution_mode": execution_mode}, error=error,
                    occurred_at=now,
                )
                return call_id
        except InvalidTransitionError as exc:
            self._reject(task_id, "TOOL_CALL_RECORDED", str(exc))
            raise

    def start_tool_call(
        self, task_id: str, attempt_id: str, tool_name: str, operation: str, *,
        execution_mode: str, request: Optional[Dict[str, Any]] = None,
        step_id: Optional[str] = None, target: Optional[str] = None,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED"):
            raise ValueError("execution_mode must be REAL or SIMULATED")
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            attempt = conn.execute(
                """SELECT * FROM execution_attempts
                   WHERE attempt_id = ? AND task_id = ?""",
                (attempt_id, task_id),
            ).fetchone()
            if attempt is None or attempt["ended_at"] is not None:
                raise InvalidTransitionError("Tool call requires an active task attempt")
            if attempt["execution_mode"] == "SIMULATED":
                execution_mode = "SIMULATED"
            now, call_id = time.time(), self._new_id("tool")
            conn.execute(
                """INSERT INTO tool_calls (
                    tool_call_id, session_id, mission_id, task_id, attempt_id,
                    correlation_id, step_id,
                    tool_name, operation, status, execution_mode, source, target,
                    started_at, request_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?, ?)""",
                (
                    call_id, task["session_id"], task["mission_id"], task_id,
                    attempt_id, task["correlation_id"], step_id or attempt["step_id"],
                    tool_name, operation,
                    execution_mode, source, self._redact(target), now,
                    self._json(request or {}), self._json(metadata or {}),
                ),
            )
            self._event(
                conn, event_type="TOOL_CALL_STARTED",
                status=EventStatus.TOOL_CALL_STARTED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, step_id=step_id or attempt["step_id"],
                correlation_id=task["correlation_id"], source=source,
                details={"tool_call_id": call_id, "tool": tool_name,
                         "operation": operation, "target": target,
                         "execution_mode": execution_mode},
                occurred_at=now,
            )
            return call_id

    def finish_tool_call(
        self, tool_call_id: str, *, status: str,
        response: Optional[Dict[str, Any]] = None, error: Optional[str] = None,
        external_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        execution_mode: Optional[str] = None,
        source: str = "nexus",
    ) -> None:
        normalized_status = status.upper()
        if normalized_status not in ("COMPLETED", "FAILED"):
            raise ValueError("Tool-call status must be COMPLETED or FAILED")
        if execution_mode is not None:
            execution_mode = execution_mode.upper()
            if execution_mode not in ("REAL", "SIMULATED"):
                raise ValueError("execution_mode must be REAL or SIMULATED")
        with self._transaction() as conn:
            call = conn.execute(
                "SELECT * FROM tool_calls WHERE tool_call_id = ?",
                (tool_call_id,),
            ).fetchone()
            if call is None:
                raise JournalError(f"Unknown tool call: {tool_call_id}")
            if call["status"] != "RUNNING" or call["completed_at"] is not None:
                raise InvalidTransitionError("Tool call has already been finalized")
            now = time.time()
            current_metadata = self._decode(call["metadata_json"], {})
            current_metadata.update(metadata or {})
            finalized_mode = (
                "SIMULATED"
                if call["execution_mode"] == "SIMULATED"
                else execution_mode or call["execution_mode"]
            )
            conn.execute(
                """UPDATE tool_calls SET status = ?, completed_at = ?, external_id = ?,
                   response_json = ?, error = ?, metadata_json = ?, execution_mode = ?
                   WHERE tool_call_id = ? AND status = 'RUNNING'""",
                (
                    normalized_status, now, self._redact(external_id),
                    self._json(response) if response is not None else None,
                    self._redact(error) if error else None,
                    self._json(current_metadata), finalized_mode, tool_call_id,
                ),
            )
            self._event(
                conn, event_type="TOOL_CALL_FINISHED",
                status=EventStatus.TOOL_CALL_FINISHED,
                session_id=call["session_id"], mission_id=call["mission_id"],
                task_id=call["task_id"], step_id=call["step_id"],
                correlation_id=conn.execute(
                    "SELECT correlation_id FROM tasks WHERE task_id = ?",
                    (call["task_id"],),
                ).fetchone()["correlation_id"],
                source=source,
                details={"tool_call_id": tool_call_id, "tool": call["tool_name"],
                         "operation": call["operation"], "target": call["target"],
                         "status": normalized_status,
                         "execution_mode": finalized_mode},
                error=error, occurred_at=now,
            )

    def record_failure(
        self, task_id: str, category: str, message: str, *,
        attempt_id: Optional[str] = None, recoverable: bool = True,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            failure_id, now = self._new_id("failure"), time.time()
            conn.execute(
                """INSERT INTO failures (
                    failure_id, session_id, mission_id, task_id, attempt_id, category,
                    message, recoverable, source, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (failure_id, task["session_id"], task["mission_id"], task_id,
                 attempt_id, category, self._redact(message), int(recoverable),
                 source, now, self._json(metadata or {})),
            )
            self._event(
                conn, event_type="FAILURE_RECORDED", status=EventStatus.FAILURE_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, correlation_id=task["correlation_id"], source=source,
                details={"failure_id": failure_id, "category": category,
                         "recoverable": recoverable}, error=message, occurred_at=now,
            )
            return failure_id

    def record_recovery(
        self, task_id: str, action: str, *, failure_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None, source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        action = action.upper()
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            if TaskStatus(task["status"]) != TaskStatus.FAILED:
                raise InvalidTransitionError("Recovery actions require a FAILED task")
            if failure_id is None:
                latest_failure = conn.execute(
                    "SELECT failure_id FROM failures WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                ).fetchone()
                failure_id = latest_failure["failure_id"] if latest_failure else None
            if failure_id is None:
                raise JournalError("Recovery requires a recorded task failure")
            if failure_id and not conn.execute(
                "SELECT 1 FROM failures WHERE failure_id = ? AND task_id = ?",
                (failure_id, task_id),
            ).fetchone():
                raise JournalError("Failure does not belong to the task")
            recovery_id, now = self._new_id("recovery"), time.time()
            conn.execute(
                """INSERT INTO recovery_actions (
                    recovery_id, session_id, mission_id, task_id, failure_id, action,
                    status, source, created_at, result_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'RECORDED', ?, ?, ?, ?)""",
                (recovery_id, task["session_id"], task["mission_id"], task_id,
                 failure_id, action, source, now,
                 self._json(result) if result is not None else None,
                 self._json(metadata or {})),
            )
            self._event(
                conn, event_type="RECOVERY_RECORDED",
                status=EventStatus.RECOVERY_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, correlation_id=task["correlation_id"], source=source,
                details={
                    "stage": "RECOVER_IF_NEEDED",
                    "recovery_id": recovery_id,
                    "action": action,
                },
                occurred_at=now,
            )
            return recovery_id

    def apply_recovery_decision(
        self,
        task_id: str,
        action: str,
        *,
        reason: str,
        idempotency_key: str,
        attempt_id: Optional[str] = None,
        decision: Optional[str] = None,
        source: str = "NexusRuntime",
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a recovery decision and any safe state transition atomically."""
        action = action.upper()
        allowed_actions = {
            "RECONCILE", "RESUME", "WAIT_HUMAN", "VERIFY_EXISTING_EFFECT",
            "MARK_FAILED",
        }
        if action not in allowed_actions:
            raise ValueError(f"Unsupported recovery action: {action}")
        if not idempotency_key:
            raise ValueError("Recovery decisions require an idempotency key")
        safe_reason = self._redact(reason)
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                existing_rows = conn.execute(
                    "SELECT * FROM recovery_actions WHERE task_id = ? ORDER BY created_at",
                    (task_id,),
                ).fetchall()
                for existing in existing_rows:
                    metadata = self._decode(existing["metadata_json"], {})
                    if metadata.get("idempotency_key") == idempotency_key:
                        return {
                            "recovery_id": existing["recovery_id"],
                            "action": existing["action"],
                            "decision": metadata.get("decision"),
                            "before_state": metadata.get("before_state"),
                            "after_state": metadata.get("after_state"),
                            "replayed": True,
                        }

                before = TaskStatus(task["status"])
                after = before
                active_attempt_id = attempt_id
                if active_attempt_id is None:
                    active = conn.execute(
                        """SELECT attempt_id FROM execution_attempts
                           WHERE task_id = ? AND ended_at IS NULL
                           ORDER BY attempt_number DESC LIMIT 1""",
                        (task_id,),
                    ).fetchone()
                    active_attempt_id = active["attempt_id"] if active else None
                if action == "RESUME":
                    if before not in (TaskStatus.PLANNED, TaskStatus.QUEUED, TaskStatus.RUNNING):
                        raise InvalidTransitionError(
                            f"Cannot resume task in {before.value} state"
                        )
                    after = TaskStatus.QUEUED
                    if active_attempt_id and before == TaskStatus.RUNNING:
                        conn.execute(
                            """UPDATE execution_attempts
                               SET status = 'INTERRUPTED', ended_at = ?,
                                   error = 'Process interrupted; recovery reconciliation'
                               WHERE attempt_id = ? AND task_id = ? AND ended_at IS NULL""",
                            (time.time(), active_attempt_id, task_id),
                        )
                elif action == "WAIT_HUMAN":
                    if before not in (
                        TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.EXECUTED,
                    ):
                        raise InvalidTransitionError(
                            f"Cannot wait for human from {before.value} state"
                        )
                    after = TaskStatus.WAITING_HUMAN
                    if active_attempt_id and before == TaskStatus.RUNNING:
                        conn.execute(
                            """UPDATE execution_attempts SET status = 'WAITING_HUMAN',
                               ended_at = ?, error = ?
                               WHERE attempt_id = ? AND task_id = ? AND ended_at IS NULL""",
                            (time.time(), safe_reason, active_attempt_id, task_id),
                        )
                elif action == "VERIFY_EXISTING_EFFECT" and before != TaskStatus.EXECUTED:
                    raise InvalidTransitionError(
                        "Existing effects can be verified only after execution"
                    )
                elif action == "MARK_FAILED":
                    if before not in (
                        TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.PLANNED,
                    ):
                        raise InvalidTransitionError(
                            f"Cannot mark task failed from {before.value} state"
                        )
                    after = TaskStatus.FAILED
                    if active_attempt_id and before == TaskStatus.RUNNING:
                        conn.execute(
                            """UPDATE execution_attempts SET status = 'FAILED',
                               ended_at = ?, error = ?
                               WHERE attempt_id = ? AND task_id = ? AND ended_at IS NULL""",
                            (time.time(), safe_reason, active_attempt_id, task_id),
                        )

                now = time.time()
                failure_id = None
                if action == "MARK_FAILED":
                    failure_id = self._new_id("failure")
                    conn.execute(
                        """INSERT INTO failures (
                            failure_id, session_id, mission_id, task_id, attempt_id,
                            category, message, recoverable, source, created_at,
                            metadata_json
                        ) VALUES (?, ?, ?, ?, ?, 'RECOVERY', ?, 0, ?, ?, ?)""",
                        (
                            failure_id, task["session_id"], task["mission_id"],
                            task_id, active_attempt_id, safe_reason, source, now,
                            self._json({"recovery": True}),
                        ),
                    )
                if after != before:
                    conn.execute(
                        "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                        (after.value, now, task_id),
                    )
                recovery_id = self._new_id("recovery")
                metadata = {
                    "idempotency_key": idempotency_key,
                    "reason": safe_reason,
                    "decision": decision or action,
                    "before_state": before.value,
                    "after_state": after.value,
                    "attempt_id": active_attempt_id,
                    "correlation_id": task["correlation_id"],
                }
                conn.execute(
                    """INSERT INTO recovery_actions (
                        recovery_id, session_id, mission_id, task_id, failure_id,
                        action, status, source, created_at, applied_at,
                        result_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'APPLIED', ?, ?, ?, ?, ?)""",
                    (
                        recovery_id, task["session_id"], task["mission_id"],
                        task_id, failure_id, action, source, now, now,
                        self._json(result or {"reason": safe_reason}),
                        self._json(metadata),
                    ),
                )
                event_type = "RECOVERY_DECISION"
                self._event(
                    conn, event_type=event_type,
                    status=EventStatus.RECOVERY_RECORDED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source,
                    details={
                        "stage": "RECOVER_IF_NEEDED",
                        "recovery_id": recovery_id,
                        "action": action,
                        **metadata,
                    },
                    occurred_at=now,
                )
                if after != before:
                    transition_status = {
                        TaskStatus.QUEUED: EventStatus.TASK_REQUEUED,
                        TaskStatus.WAITING_HUMAN: EventStatus.TASK_WAITING_HUMAN,
                        TaskStatus.FAILED: EventStatus.TASK_FAILED,
                    }[after]
                    self._event(
                        conn,
                        event_type=f"TASK_{after.value}",
                        status=transition_status,
                        session_id=task["session_id"],
                        mission_id=task["mission_id"],
                        task_id=task_id,
                        correlation_id=task["correlation_id"],
                        source=source,
                        details={
                            "stage": "RECOVER_IF_NEEDED",
                            "from": before.value,
                            "to": after.value,
                            "recovery_id": recovery_id,
                            "reason": safe_reason,
                        },
                        occurred_at=now,
                    )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return {
                    "recovery_id": recovery_id,
                    "action": action,
                    "decision": metadata["decision"],
                    "before_state": before.value,
                    "after_state": after.value,
                    "replayed": False,
                }
        except InvalidTransitionError as exc:
            self._reject(task_id, "RECOVERY_DECISION", str(exc))
            raise

    def record_proof(
        self, task_id: str, proof_type: str, *, execution_mode: str,
        value: Optional[str] = None, uri: Optional[str] = None,
        sha256: Optional[str] = None, step_id: Optional[str] = None,
        attempt_id: Optional[str] = None, tool_call_id: Optional[str] = None,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None,
        reference: Optional[str] = None, evidence_hash: Optional[str] = None,
    ) -> str:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED"):
            raise ValueError("execution_mode must be REAL or SIMULATED")
        reference = reference or uri
        evidence_hash = evidence_hash or sha256
        if not (value or reference or evidence_hash):
            raise ValueError("A proof requires a concrete value, URI, or SHA-256")
        if not attempt_id and not tool_call_id:
            raise ValueError("A proof must reference an execution attempt or tool call")
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            if attempt_id:
                attempt = conn.execute(
                    "SELECT task_id, step_id, execution_mode FROM execution_attempts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchone()
                if attempt is None or attempt["task_id"] != task_id:
                    raise JournalError("Proof attempt does not belong to the task")
                if attempt["execution_mode"] == "SIMULATED":
                    execution_mode = "SIMULATED"
                if step_id and attempt["step_id"] and step_id != attempt["step_id"]:
                    raise JournalError("Proof step does not match its attempt")
                step_id = step_id or attempt["step_id"]
            if tool_call_id:
                call = conn.execute(
                    "SELECT task_id, step_id, execution_mode FROM tool_calls WHERE tool_call_id = ?",
                    (tool_call_id,),
                ).fetchone()
                if call is None or call["task_id"] != task_id:
                    raise JournalError("Proof tool call does not belong to the task")
                if call["execution_mode"] == "SIMULATED":
                    execution_mode = "SIMULATED"
                if step_id and call["step_id"] and step_id != call["step_id"]:
                    raise JournalError("Proof step does not match its tool call")
                step_id = step_id or call["step_id"]
            existing = conn.execute(
                """SELECT proof_id FROM proofs
                   WHERE task_id = ? AND proof_type = ?
                     AND attempt_id IS ? AND tool_call_id IS ?
                     AND evidence_hash IS ? AND reference IS ?""",
                (task_id, proof_type, attempt_id, tool_call_id,
                 evidence_hash, self._redact(reference) if reference else None),
            ).fetchone()
            if existing:
                return existing["proof_id"]
            proof_id, now = self._new_id("proof"), time.time()
            conn.execute(
                """INSERT INTO proofs (
                    proof_id, session_id, mission_id, task_id, step_id, attempt_id,
                    tool_call_id, proof_type, value, uri, sha256, execution_mode,
                    source, created_at, collected_at, reference, evidence_hash,
                    verification_status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                (proof_id, task["session_id"], task["mission_id"], task_id,
                 step_id, attempt_id, tool_call_id, proof_type,
                 self._redact(value) if value else None,
                 self._redact(reference) if reference else None, evidence_hash, execution_mode,
                 source, now, now, self._redact(reference) if reference else None,
                 evidence_hash, self._json(metadata or {})),
            )
            self._event(
                conn, event_type="PROOF_RECORDED", status=EventStatus.PROOF_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, step_id=step_id, correlation_id=task["correlation_id"],
                source=source, details={"proof_id": proof_id, "proof_type": proof_type,
                                        "execution_mode": execution_mode}, occurred_at=now,
            )
            return proof_id

    def verify_proof(
        self, proof_id: str, verifier: str, verification: Dict[str, Any], *,
        valid: bool, source: str = "nexus"
    ) -> bool:
        if valid and (not verifier.strip() or not verification):
            raise ValueError("A valid proof requires a verifier and verification details")
        try:
            with self._transaction() as conn:
                proof = conn.execute(
                    "SELECT * FROM proofs WHERE proof_id = ?", (proof_id,)
                ).fetchone()
                if proof is None:
                    raise JournalError(f"Unknown proof: {proof_id}")
                if proof["execution_mode"] == "SIMULATED" and valid:
                    raise JournalError("A SIMULATED proof cannot be verified as real evidence")
                if proof["verification_status"] != "PENDING":
                    prior_valid = proof["verification_status"] == "VERIFIED"
                    if prior_valid != valid:
                        raise JournalError("Proof verification is already finalized")
                    return prior_valid
                now = time.time()
                conn.execute(
                    """UPDATE proofs SET verified = ?, verifier = ?, verification_json = ?,
                       verified_at = ? WHERE proof_id = ?""",
                    (int(valid), verifier, self._json(verification), now, proof_id),
                )
                task = self._task(conn, proof["task_id"])
                self._event(
                    conn, event_type="PROOF_VERIFIED" if valid else "PROOF_VERIFICATION_FAILED",
                    status=EventStatus.PROOF_VERIFIED if valid else EventStatus.VERIFICATION_FAILED,
                    session_id=proof["session_id"], mission_id=proof["mission_id"],
                    task_id=proof["task_id"], step_id=proof["step_id"],
                    correlation_id=task["correlation_id"], source=source, actor=verifier,
                    details={"proof_id": proof_id, "valid": valid,
                             "verification": verification}, occurred_at=now,
                )
                conn.execute(
                    """UPDATE proofs SET verification_status = ?, verification_reason = ?
                       WHERE proof_id = ?""",
                    ("VERIFIED" if valid else "FAILED",
                     self._redact(verification.get("reason")) if verification.get("reason") else None,
                     proof_id),
                )
                return valid
        except JournalError as exc:
            with self._connection() as conn:
                proof = conn.execute(
                    "SELECT task_id FROM proofs WHERE proof_id = ?", (proof_id,)
                ).fetchone()
            self._reject(proof["task_id"] if proof else None, "PROOF_VERIFICATION", str(exc))
            raise

    def defer_proof_verification(
        self, proof_id: str, reason: str, *, source: str = "nexus"
    ) -> None:
        with self._transaction() as conn:
            proof = conn.execute(
                "SELECT * FROM proofs WHERE proof_id = ?", (proof_id,)
            ).fetchone()
            if proof is None:
                raise JournalError(f"Unknown proof: {proof_id}")
            if proof["verification_status"] != "PENDING":
                if proof["verification_status"] == "WAITING_HUMAN":
                    return
                raise InvalidTransitionError("Proof verification is already finalized")
            now = time.time()
            safe_reason = self._redact(reason)
            conn.execute(
                """UPDATE proofs SET verification_status = 'WAITING_HUMAN',
                   verification_reason = ?, verified_at = ? WHERE proof_id = ?""",
                (safe_reason, now, proof_id),
            )
            task = self._task(conn, proof["task_id"])
            self._event(
                conn, event_type="PROOF_VERIFICATION_DEFERRED",
                status=EventStatus.VERIFICATION_STARTED,
                session_id=proof["session_id"], mission_id=proof["mission_id"],
                task_id=proof["task_id"], step_id=proof["step_id"],
                correlation_id=task["correlation_id"], source=source,
                details={"proof_id": proof_id, "reason": safe_reason},
                occurred_at=now,
            )

    def complete_execution(
        self, task_id: str, result: Dict[str, Any], *,
        execution_mode: Optional[str] = None, source: str = "nexus"
    ) -> TaskRecord:
        with self._connection() as conn:
            active = conn.execute(
                """SELECT * FROM execution_attempts WHERE task_id = ? AND ended_at IS NULL
                   ORDER BY attempt_number DESC LIMIT 1""", (task_id,)
            ).fetchone()
        if active is None:
            error = "Execution requires a recorded active attempt"
            self._reject(task_id, "EXECUTION_COMPLETED", error)
            raise InvalidTransitionError(error)
        mode = (execution_mode or active["execution_mode"]).upper()
        if mode not in ("REAL", "SIMULATED", "UNDECLARED"):
            raise ValueError("execution_mode must be REAL, SIMULATED, or UNDECLARED")
        attempt_mode = active["execution_mode"]
        if attempt_mode == "SIMULATED":
            mode = "SIMULATED"
        elif attempt_mode == "UNDECLARED" and mode == "UNDECLARED":
            mode = "UNDECLARED"
        elif attempt_mode == "REAL" and mode == "UNDECLARED":
            mode = "REAL"
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                if TaskStatus(task["status"]) != TaskStatus.RUNNING:
                    raise InvalidTransitionError("Only a RUNNING task can complete execution")
                now = time.time()
                conn.execute(
                    """UPDATE execution_attempts SET status = 'EXECUTED', ended_at = ?,
                       execution_mode = ?, result_json = ?
                       WHERE attempt_id = ? AND ended_at IS NULL""",
                    (now, mode, self._json(result), active["attempt_id"]),
                )
                conn.execute(
                    """UPDATE tasks SET status = 'EXECUTED', execution_mode = ?,
                       result_json = ?, executed_at = ?, updated_at = ? WHERE task_id = ?""",
                    (mode, self._json(result), now, now, task_id),
                )
                self._event(
                    conn, event_type="EXECUTION_COMPLETED",
                    status=EventStatus.EXECUTION_COMPLETED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"], source=source,
                    details={"stage": "EXECUTE",
                             "attempt_id": active["attempt_id"], "execution_mode": mode},
                    occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task_id))
        except InvalidTransitionError as exc:
            self._reject(task_id, "EXECUTION_COMPLETED", str(exc))
            raise

    def verify_task(self, task_id: str, proof_id: str, *, source: str = "nexus") -> TaskRecord:
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                proof = conn.execute(
                    """SELECT verified, execution_mode FROM proofs
                       WHERE proof_id = ? AND task_id = ?""",
                    (proof_id, task_id),
                ).fetchone()
                if TaskStatus(task["status"]) != TaskStatus.EXECUTED:
                    raise InvalidTransitionError(
                        f"Cannot verify task in {task['status']} state"
                    )
                if proof is None or not proof["verified"] or proof["execution_mode"] == "SIMULATED":
                    raise InvalidTransitionError(
                        "Task verification requires a verified, non-simulated proof"
                    )
                now = time.time()
                conn.execute(
                    """UPDATE tasks SET status = 'VERIFIED', verified_at = ?,
                       updated_at = ? WHERE task_id = ?""",
                    (now, now, task_id),
                )
                self._event(
                    conn, event_type="TASK_VERIFIED",
                    status=EventStatus.VERIFICATION_PASSED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source,
                    details={"from": TaskStatus.EXECUTED.value,
                             "to": TaskStatus.VERIFIED.value, "proof_id": proof_id,
                             "stage": "FINALIZE"},
                    occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task_id))
        except InvalidTransitionError as exc:
            self._reject(task_id, "TASK_VERIFIED", str(exc))
            raise

    def fail_task(
        self, task_id: str, message: str, *, category: str = "EXECUTION",
        attempt_id: Optional[str] = None, recoverable: bool = True,
        source: str = "nexus"
    ) -> TaskRecord:
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                allowed = (TaskStatus.PLANNED, TaskStatus.QUEUED, TaskStatus.RUNNING,
                           TaskStatus.WAITING_APPROVAL, TaskStatus.WAITING_HUMAN,
                           TaskStatus.EXECUTED)
                current = TaskStatus(task["status"])
                if current not in allowed:
                    raise InvalidTransitionError(f"Cannot fail task in {current.value}")
                now, failure_id = time.time(), self._new_id("failure")
                if attempt_id is None:
                    active_attempt = conn.execute(
                        """SELECT attempt_id FROM execution_attempts
                           WHERE task_id = ? AND ended_at IS NULL""",
                        (task_id,),
                    ).fetchone()
                    attempt_id = active_attempt["attempt_id"] if active_attempt else None
                conn.execute(
                    """INSERT INTO failures (
                        failure_id, session_id, mission_id, task_id, attempt_id, category,
                        message, recoverable, source, created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
                    (failure_id, task["session_id"], task["mission_id"], task_id,
                     attempt_id, category, self._redact(message), int(recoverable), source, now),
                )
                if attempt_id:
                    attempt_update = conn.execute(
                        """UPDATE execution_attempts SET status = 'FAILED', ended_at = ?, error = ?
                           WHERE attempt_id = ? AND task_id = ? AND ended_at IS NULL""",
                        (now, self._redact(message), attempt_id, task_id),
                    )
                    if attempt_update.rowcount != 1:
                        raise JournalError("Failure attempt is not active for this task")
                conn.execute(
                    "UPDATE tasks SET status = 'FAILED', error = ?, updated_at = ? WHERE task_id = ?",
                    (self._redact(message), now, task_id),
                )
                self._event(
                    conn, event_type="TASK_FAILED", status=EventStatus.TASK_FAILED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source, details={"failure_id": failure_id, "category": category,
                                            "from": current.value, "to": "FAILED",
                                            "stage": "FINALIZE"},
                    error=message, occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task_id))
        except InvalidTransitionError as exc:
            self._reject(task_id, "TASK_FAILED", str(exc))
            raise

    def cancel_task(self, task_id: str, *, reason: Optional[str] = None,
                    source: str = "nexus") -> TaskRecord:
        with self._connection() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise JournalError(f"Unknown task: {task_id}")
        return self._transition(
            task_id, TaskStatus.CANCELLED,
            allowed=tuple(status for status in TaskStatus if status not in (
                TaskStatus.EXECUTED, TaskStatus.VERIFIED, TaskStatus.FAILED, TaskStatus.CANCELLED
            )),
            event_status=EventStatus.TASK_CANCELLED, event_type="TASK_CANCELLED",
            source=source, details={"reason": reason} if reason else {},
        )

    def wait_for_human(self, task_id: str, reason: str, *,
                       source: str = "nexus") -> TaskRecord:
        return self._transition(
            task_id, TaskStatus.WAITING_HUMAN,
            allowed=(TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.EXECUTED),
            event_status=EventStatus.TASK_WAITING_HUMAN,
            event_type="TASK_WAITING_HUMAN", source=source,
            details={"reason": reason},
        )

    def resume_task(self, task_id: str, *, source: str = "nexus") -> TaskRecord:
        return self._transition(
            task_id, TaskStatus.QUEUED, allowed=(TaskStatus.WAITING_HUMAN,),
            event_status=EventStatus.TASK_RESUMED, event_type="TASK_RESUMED",
            source=source,
        )

    def request_approval(
        self, task_id: str, action: str, *, requested_by: str = "runtime",
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        try:
            with self._transaction() as conn:
                task = self._task(conn, task_id)
                if TaskStatus(task["status"]) not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    raise InvalidTransitionError("Approval can be requested only for QUEUED or RUNNING tasks")
                approval_id, now = self._new_id("approval"), time.time()
                conn.execute(
                    """INSERT INTO approvals (
                        approval_id, session_id, mission_id, task_id, action, status,
                        requested_by, source, requested_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)""",
                    (approval_id, task["session_id"], task["mission_id"], task_id,
                     action, requested_by, source, now, self._json(metadata or {})),
                )
                conn.execute(
                    "UPDATE tasks SET status = 'WAITING_APPROVAL', updated_at = ? WHERE task_id = ?",
                    (now, task_id),
                )
                conn.execute(
                    """UPDATE execution_attempts SET status = 'WAITING_APPROVAL', ended_at = ?
                       WHERE task_id = ? AND ended_at IS NULL""",
                    (now, task_id),
                )
                self._event(
                    conn, event_type="APPROVAL_REQUESTED",
                    status=EventStatus.TASK_WAITING_APPROVAL,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task_id, correlation_id=task["correlation_id"],
                    source=source, actor=requested_by,
                    details={"approval_id": approval_id, "action": action},
                    occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return approval_id
        except InvalidTransitionError as exc:
            self._reject(task_id, "APPROVAL_REQUESTED", str(exc))
            raise

    def resolve_approval(
        self, approval_id: str, *, approved: bool, resolved_by: str,
        reason: Optional[str] = None, source: str = "nexus"
    ) -> TaskRecord:
        try:
            with self._transaction() as conn:
                approval = conn.execute(
                    "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
                ).fetchone()
                if approval is None or approval["status"] != "PENDING":
                    raise InvalidTransitionError("Approval is unknown or already resolved")
                task = self._task(conn, approval["task_id"])
                if TaskStatus(task["status"]) != TaskStatus.WAITING_APPROVAL:
                    raise InvalidTransitionError("Approval task is not WAITING_APPROVAL")
                now = time.time()
                new_status = "APPROVED" if approved else "REJECTED"
                task_status = TaskStatus.QUEUED if approved else TaskStatus.CANCELLED
                conn.execute(
                    """UPDATE approvals SET status = ?, resolved_by = ?, reason = ?, resolved_at = ?
                       WHERE approval_id = ?""",
                    (new_status, resolved_by, self._redact(reason) if reason else None,
                     now, approval_id),
                )
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                    (task_status.value, now, task["task_id"]),
                )
                self._event(
                    conn, event_type="APPROVAL_RESOLVED",
                    status=EventStatus.APPROVAL_RESOLVED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task["task_id"], correlation_id=task["correlation_id"],
                    source=source, actor=resolved_by,
                    details={"approval_id": approval_id, "approved": approved,
                             "task_status": task_status.value, "reason": reason},
                    occurred_at=now,
                )
                self._event(
                    conn,
                    event_type="TASK_QUEUED" if approved else "TASK_CANCELLED",
                    status=EventStatus.TASK_QUEUED if approved else EventStatus.TASK_CANCELLED,
                    session_id=task["session_id"], mission_id=task["mission_id"],
                    task_id=task["task_id"], correlation_id=task["correlation_id"],
                    source=source, actor=resolved_by,
                    details={"from": TaskStatus.WAITING_APPROVAL.value,
                             "to": task_status.value, "approval_id": approval_id},
                    occurred_at=now,
                )
                self._refresh_mission_status(
                    conn, task["mission_id"], source=source, occurred_at=now
                )
                return self._to_task(self._task(conn, task["task_id"]))
        except InvalidTransitionError as exc:
            self._reject(
                approval["task_id"] if approval is not None else None,
                "APPROVAL_RESOLVED",
                str(exc),
            )
            raise

    def record_observation(
        self, kind: str, data: Dict[str, Any], *, mission_id: Optional[str] = None,
        task_id: Optional[str] = None, session_id: Optional[str] = None,
        step_id: Optional[str] = None, target: Optional[str] = None,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        observation_id, now = self._new_id("observation"), time.time()
        with self._transaction() as conn:
            self._validate_session(conn, session_id)
            self._validate_task_links(conn, task_id, mission_id, session_id)
            conn.execute(
                """INSERT INTO observations (
                    observation_id, session_id, mission_id, task_id, step_id, kind,
                    target, source, observed_at, data_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (observation_id, session_id, mission_id, task_id, step_id, kind,
                 self._redact(target) if target else None, source, now,
                 self._json(data), self._json(metadata or {})),
            )
            self._event(
                conn, event_type="OBSERVATION_RECORDED",
                status=EventStatus.OBSERVATION_RECORDED, session_id=session_id,
                mission_id=mission_id, task_id=task_id, step_id=step_id,
                source=source, details={
                    "stage": "OBSERVE",
                    "observation_id": observation_id,
                    "kind": kind,
                },
                occurred_at=now,
            )
        return observation_id

    def record_outcome(
        self, task_id: str, status: str, result: Dict[str, Any], *,
        proof_id: Optional[str] = None, source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        outcome_id, now = self._new_id("outcome"), time.time()
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            if status.upper() in ("SUCCESS", "COMPLETED", "VERIFIED") and not proof_id:
                raise JournalError("Successful outcomes require verified real proof")
            if proof_id:
                proof = conn.execute(
                    "SELECT task_id, verified, execution_mode FROM proofs WHERE proof_id = ?",
                    (proof_id,),
                ).fetchone()
                if proof is None or proof["task_id"] != task_id:
                    raise JournalError("Outcome proof does not belong to the task")
                if status.upper() in ("SUCCESS", "VERIFIED") and (
                    not proof["verified"] or proof["execution_mode"] == "SIMULATED"
                ):
                    raise JournalError("Successful outcome requires verified real proof")
            conn.execute(
                """INSERT INTO outcomes (
                    outcome_id, session_id, mission_id, task_id, proof_id, status,
                    source, created_at, result_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (outcome_id, task["session_id"], task["mission_id"], task_id,
                 proof_id, status.upper(), source, now,
                 self._json(result), self._json(metadata or {})),
            )
            self._event(
                conn, event_type="OUTCOME_RECORDED",
                status=EventStatus.OUTCOME_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, correlation_id=task["correlation_id"],
                source=source, details={
                    "stage": "FINALIZE",
                    "outcome_id": outcome_id,
                    "status": status,
                },
                occurred_at=now,
            )
        return outcome_id

    def create_task_step(
        self, task_id: str, sequence: int, name: str, *,
        status: str = "PLANNED", source: str = "nexus",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        step_id, now = self._new_id("step"), time.time()
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            conn.execute(
                """INSERT INTO task_steps (
                    step_id, session_id, mission_id, task_id, sequence, name, status,
                    source, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, task["session_id"], task["mission_id"], task_id,
                 sequence, name, status.upper(), source, now, now, self._json(metadata or {})),
            )
            self._event(
                conn, event_type="TASK_STEP_RECORDED",
                status=EventStatus.TASK_STEP_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, step_id=step_id,
                correlation_id=task["correlation_id"], source=source,
                details={"step_id": step_id, "name": name, "status": status},
                occurred_at=now,
            )
        return step_id

    def record_agent_action(
        self, task_id: str, agent: str, action: str, *,
        execution_mode: str, input_data: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None, step_id: Optional[str] = None,
        source: str = "nexus", metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        execution_mode = execution_mode.upper()
        if execution_mode not in ("REAL", "SIMULATED", "UNDECLARED"):
            raise ValueError("execution_mode must be REAL, SIMULATED, or UNDECLARED")
        action_id, now = self._new_id("action"), time.time()
        with self._transaction() as conn:
            task = self._task(conn, task_id)
            conn.execute(
                """INSERT INTO agent_actions (
                    action_id, session_id, mission_id, task_id, step_id, agent, action,
                    execution_mode, source, created_at, input_json, result_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (action_id, task["session_id"], task["mission_id"], task_id,
                 step_id, agent, action, execution_mode.upper(), source, now,
                 self._json(input_data or {}),
                 self._json(result) if result is not None else None,
                 self._json(metadata or {})),
            )
            self._event(
                conn, event_type="AGENT_ACTION_RECORDED",
                status=EventStatus.AGENT_ACTION_RECORDED,
                session_id=task["session_id"], mission_id=task["mission_id"],
                task_id=task_id, step_id=step_id,
                correlation_id=task["correlation_id"], source=source, actor=agent,
                details={"action_id": action_id, "action": action,
                         "execution_mode": execution_mode.upper()}, occurred_at=now,
            )
        return action_id

    def record_decision(
        self, *, question: str, context_summary: str, options: Any,
        decision: str, justification_summary: str,
        confidence: Optional[float] = None, risk: Optional[str] = None,
        expected_outcome: Optional[str] = None,
        mission_id: Optional[str] = None, task_id: Optional[str] = None,
        session_id: Optional[str] = None, source: str = "nexus"
    ) -> str:
        decision_id, now = self._new_id("decision"), time.time()
        with self._transaction() as conn:
            self._validate_session(conn, session_id)
            self._validate_task_links(conn, task_id, mission_id, session_id)
            conn.execute(
                """INSERT INTO decisions (
                    decision_id, session_id, mission_id, task_id, source, created_at,
                    question, context_summary, options_json, decision,
                    justification_summary, confidence, risk, expected_outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, session_id, mission_id, task_id, source, now,
                 self._redact(question), self._redact(context_summary),
                 self._json(options), self._redact(decision),
                 self._redact(justification_summary), confidence,
                 self._redact(risk) if risk else None,
                 self._redact(expected_outcome) if expected_outcome else None),
            )
            self._event(
                conn, event_type="DECISION_RECORDED",
                status=EventStatus.DECISION_RECORDED, session_id=session_id,
                mission_id=mission_id, task_id=task_id, source=source,
                details={"decision_id": decision_id, "decision": decision},
                occurred_at=now,
            )
        return decision_id

    def _validate_task_links(
        self, conn: sqlite3.Connection, task_id: Optional[str],
        mission_id: Optional[str], session_id: Optional[str]
    ) -> None:
        if task_id:
            task = self._task(conn, task_id)
            if mission_id and task["mission_id"] != mission_id:
                raise JournalError("Mission does not match task")
            if session_id and task["session_id"] != session_id:
                raise JournalError("Session does not match task")

    def append_event(self, event: EventRecord) -> EventRecord:
        with self._transaction() as conn:
            session_id = event.run_id or None
            if session_id and not conn.execute(
                "SELECT 1 FROM runtime_sessions WHERE session_id = ?", (session_id,)
            ).fetchone():
                session_id = None
            task_id = event.task_id
            if task_id and not conn.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone():
                task_id = None
            details = {
                "stage": event.stage, "action": event.action, "target": event.target,
                "proof": event.proof, "result": event.result, "metadata": event.metadata,
            }
            if event.task_id and task_id is None:
                details["external_task_id"] = event.task_id
            if event.run_id and session_id is None:
                details["external_run_id"] = event.run_id
            self._event(
                conn, event_type=event.status.value, status=event.status,
                event_id=event.event_id,
                session_id=session_id, task_id=task_id,
                correlation_id=event.metadata.get("correlation_id"),
                source=event.source, actor=event.agent, details={
                    **details,
                }, error=event.error, occurred_at=event.timestamp,
            )
        return event

    def list_events(self, limit: int = 100) -> List[EventRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_events ORDER BY occurred_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            EventRecord(
                event_id=row["event_id"], run_id=row["session_id"] or "",
                task_id=row["task_id"], timestamp=row["occurred_at"],
                source=row["source"], agent=row["actor"], stage=row["event_type"],
                status=EventStatus(row["status"]), action=row["event_type"],
                target="runtime", proof={}, result=self._decode(row["details_json"], {}),
                error=row["error"], metadata={"correlation_id": row["correlation_id"]},
            )
            for row in rows
        ]

    def get_record(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Read a single journal record by its stable ID."""
        id_columns = {
            "runtime_sessions": "session_id", "missions": "mission_id", "tasks": "task_id",
            "task_steps": "step_id", "task_events": "event_id", "agent_actions": "action_id",
            "decisions": "decision_id", "tool_calls": "tool_call_id",
            "execution_attempts": "attempt_id", "failures": "failure_id",
            "recovery_actions": "recovery_id", "approvals": "approval_id",
            "proofs": "proof_id", "observations": "observation_id", "outcomes": "outcome_id",
        }
        if table not in id_columns:
            raise ValueError(f"Unknown journal table: {table}")
        with self._connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {table} WHERE {id_columns[table]} = ?", (record_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_records(
        self,
        table: str,
        *,
        task_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        limit: int = 1000,
        newest_first: bool = False,
    ) -> List[Dict[str, Any]]:
        """List journal rows from a bounded set of operational tables."""
        allowed = {
            "runtime_sessions", "missions", "tasks", "task_steps", "task_events",
            "agent_actions", "decisions", "tool_calls", "execution_attempts",
            "failures", "recovery_actions", "approvals", "proofs",
            "observations", "outcomes",
        }
        if table not in allowed:
            raise ValueError(f"Unknown journal table: {table}")
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as conn:
            if table == "runtime_sessions" and (task_id or mission_id):
                raise ValueError("Runtime sessions cannot be filtered by task or mission")
            filters = []
            parameters: List[Any] = []
            if task_id is not None:
                if table == "missions":
                    raise ValueError("Missions cannot be filtered by task_id")
                filters.append("task_id = ?")
                parameters.append(task_id)
            if mission_id is not None:
                if table == "missions":
                    filters.append("mission_id = ?")
                else:
                    if table == "runtime_sessions":
                        raise ValueError("Runtime sessions cannot be filtered by mission_id")
                    filters.append("mission_id = ?")
                parameters.append(mission_id)
            where = f" WHERE {' AND '.join(filters)}" if filters else ""
            order = "rowid ASC"
            if newest_first:
                    order = (
                        "occurred_at DESC, rowid DESC"
                        if table == "task_events" else "rowid DESC"
                    )
            rows = conn.execute(
                    f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT ?",
                    (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None


class SQLiteEventRepository(EventRepository):
    def __init__(self, db_path: str = "nexus_runtime_events.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db_path = self.db_path
        if db_path == ":memory:":
            db_path = "file::memory:?cache=shared"
        conn = sqlite3.connect(db_path, uri=db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    task_id TEXT,
                    timestamp REAL,
                    source TEXT,
                    agent TEXT,
                    stage TEXT,
                    status TEXT,
                    action TEXT,
                    target TEXT,
                    proof TEXT,
                    result TEXT,
                    error TEXT,
                    metadata TEXT
                )
                """
            )
            conn.commit()

    def append_event(self, event: EventRecord) -> EventRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, run_id, task_id, timestamp, source, agent, stage, status, action,
                    target, proof, result, error, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.task_id,
                    event.timestamp,
                    event.source,
                    event.agent,
                    event.stage,
                    event.status.value,
                    event.action,
                    event.target,
                    json.dumps(event.proof),
                    json.dumps(event.result) if event.result is not None else None,
                    event.error,
                    json.dumps(event.metadata),
                ),
            )
            conn.commit()
        return event

    def list_events(self, limit: int = 100) -> List[EventRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            EventRecord(
                event_id=row["event_id"],
                run_id=row["run_id"],
                task_id=row["task_id"],
                timestamp=row["timestamp"],
                source=row["source"],
                agent=row["agent"],
                stage=row["stage"],
                status=EventStatus(row["status"]),
                action=row["action"],
                target=row["target"],
                proof=json.loads(row["proof"]) if row["proof"] else {},
                result=json.loads(row["result"]) if row["result"] else None,
                error=row["error"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )
            for row in rows
        ]


class LegacyOrchestratorAdapter:
    """Small adapter around the current orchestrator implementations without replacing them."""

    def __init__(self, orchestrator: Any):
        self._orchestrator = orchestrator

    async def submit_task(self, task_type: str, payload: Dict[str, Any], priority: str = "MEDIUM") -> str:
        if hasattr(self._orchestrator, "submit_task"):
            return await self._orchestrator.submit_task(task_type, payload, priority)
        raise AttributeError("Legacy orchestrator does not implement submit_task")

    async def start(self) -> None:
        if hasattr(self._orchestrator, "start_loop"):
            await self._orchestrator.start_loop()
        elif hasattr(self._orchestrator, "start_dispatcher"):
            await self._orchestrator.start_dispatcher()

    def stop(self) -> None:
        if hasattr(self._orchestrator, "stop"):
            self._orchestrator.stop()


class ProofVerificationEngine:
   """Verifies persisted, real execution evidence against explicit task criteria."""

   def __init__(self, journal: OperationalJournal):
       self.journal = journal

   def _task_records(self, table: str, task_id: str) -> List[Dict[str, Any]]:
       if table not in {"execution_attempts", "proofs"}:
           raise ValueError("Unsupported verification journal table")
       with self.journal._connection() as conn:
           rows = conn.execute(
               f"SELECT * FROM {table} WHERE task_id = ? ORDER BY rowid",
               (task_id,),
           ).fetchall()
       return [dict(row) for row in rows]

   @staticmethod
   def _field(evidence: Dict[str, Any], path: str) -> tuple[bool, Any]:
       current: Any = evidence
       for component in path.split("."):
           if not isinstance(current, dict) or component not in current:
               return False, None
           current = current[component]
       return True, current

   @classmethod
   def _evaluate(cls, criteria: Any, evidence: Dict[str, Any]) -> Optional[bool]:
       if isinstance(criteria, str):
           return None
       if not isinstance(criteria, dict) or not criteria:
           return None
       if "all" in criteria:
           if not isinstance(criteria["all"], list) or not criteria["all"]:
               return None
           values = [cls._evaluate(item, evidence) for item in criteria["all"]]
           return False if False in values else (True if all(v is True for v in values) else None)
       if "any" in criteria:
           if not isinstance(criteria["any"], list) or not criteria["any"]:
               return None
           values = [cls._evaluate(item, evidence) for item in criteria["any"]]
           return True if True in values else (False if all(v is False for v in values) else None)
       if "field" in criteria:
           present, actual = cls._field(evidence, str(criteria["field"]))
           if not present:
               return None
           if "equals" in criteria:
               return actual == criteria["equals"]
           if "contains" in criteria:
               expected = criteria["contains"]
               return expected in actual if isinstance(actual, (str, list, tuple, dict)) else False
           if "exists" in criteria:
               return bool(actual) is bool(criteria["exists"])
           return None
       values = []
       for path, expected in criteria.items():
           present, actual = cls._field(evidence, str(path))
           if not present:
               values.append(None)
           else:
               values.append(actual == expected)
       return False if False in values else (True if all(v is True for v in values) else None)

   def _event(self, task: TaskRecord, status: EventStatus, action: str,
              details: Dict[str, Any]) -> None:
       self.journal.append_event(EventRecord(
           event_id=self.journal._new_id("event"),
           run_id=task.run_id or "",
           task_id=task.task_id,
           source="ProofVerificationEngine",
           agent="ProofVerificationEngine",
           stage="VERIFY",
           status=status,
           action=action,
           target=task.task_id,
           metadata={
               **details,
               "mission_id": task.mission_id,
               "correlation_id": task.correlation_id,
           },
       ))

   def verify_task(self, task_id: str) -> TaskRecord:
       task = self.journal.get_task(task_id)
       if task is None:
           raise JournalError(f"Unknown task: {task_id}")
       if task.status != TaskStatus.EXECUTED:
           return task
       attempts = self._task_records("execution_attempts", task_id)
       current_attempt = attempts[-1] if attempts else None
       proofs = self._task_records("proofs", task_id)
       current_proofs = [
           proof for proof in proofs
           if current_attempt and proof.get("attempt_id") == current_attempt["attempt_id"]
       ]
       self._event(task, EventStatus.VERIFICATION_STARTED, "verification_started", {
           "attempt_id": current_attempt["attempt_id"] if current_attempt else None,
           "proof_count": len(current_proofs),
       })
       if task.execution_mode == "SIMULATED" or (
           current_attempt and current_attempt.get("execution_mode") == "SIMULATED"
       ):
           self._event(task, EventStatus.VERIFICATION_FAILED, "verification_not_applicable", {
               "reason": "Simulation cannot establish real business proof",
           })
           return task
       if task.execution_mode != "REAL" or (
           current_attempt and current_attempt.get("execution_mode") != "REAL"
       ):
           reason = "SIMULATED or undeclared execution cannot establish business proof"
           self._event(task, EventStatus.VERIFICATION_FAILED, "verification_waiting_human", {
               "reason": reason,
           })
           return self.journal.wait_for_human(task_id, reason, source="ProofVerificationEngine")

       if any(proof["proof_type"] == "web3_broadcast" for proof in current_proofs) and not any(
           proof["proof_type"] == "web3_receipt" for proof in current_proofs
       ):
           reason = "Transaction broadcast is not confirmation; receipt reconciliation is required"
           for proof in current_proofs:
               if proof["verification_status"] == "PENDING":
                   self.journal.defer_proof_verification(
                       proof["proof_id"], reason, source="ProofVerificationEngine"
                   )
           self._event(task, EventStatus.VERIFICATION_FAILED, "verification_waiting_human", {
               "reason": reason,
           })
           return self.journal.wait_for_human(task_id, reason, source="ProofVerificationEngine")

       criteria = task.metadata.get("success_criteria")
       if not current_proofs or criteria is None:
           reason = "Concrete proof or explicit success criteria are missing"
           for proof in current_proofs:
               self.journal.defer_proof_verification(
                   proof["proof_id"], reason, source="ProofVerificationEngine"
               )
           self._event(task, EventStatus.VERIFICATION_FAILED, "verification_waiting_human", {
               "reason": reason, "proof_count": len(current_proofs),
           })
           return self.journal.wait_for_human(task_id, reason, source="ProofVerificationEngine")

       evidence: Dict[str, Any] = {}
       for proof in current_proofs:
           evidence.update(self.journal._decode(proof.get("metadata_json"), {}).get("evidence", {}))
       decision = self._evaluate(criteria, evidence)
       selected = current_proofs[-1]
       if decision is True:
           self.journal.verify_proof(
               selected["proof_id"], "ProofVerificationEngine",
               {"criteria": criteria, "evidence": evidence, "reason": "Success criteria satisfied"},
               valid=True, source="ProofVerificationEngine",
           )
           verified = self.journal.verify_task(
               task_id, selected["proof_id"], source="ProofVerificationEngine"
           )
           self.journal.record_outcome(
               task_id, "VERIFIED", {"criteria_satisfied": True},
               proof_id=selected["proof_id"], source="ProofVerificationEngine",
           )
           self._event(task, EventStatus.VERIFICATION_PASSED, "verification_passed", {
               "proof_id": selected["proof_id"],
           })
           return verified
       if decision is False:
           reason = "Collected proof contradicts the success criteria"
           self.journal.verify_proof(
               selected["proof_id"], "ProofVerificationEngine",
               {"criteria": criteria, "evidence": evidence, "reason": reason},
               valid=False, source="ProofVerificationEngine",
           )
           failed = self.journal.fail_task(
               task_id, reason, category="VERIFICATION",
               source="ProofVerificationEngine",
           )
           self.journal.record_outcome(
               task_id, "FAILED", {"reason": reason},
               proof_id=selected["proof_id"], source="ProofVerificationEngine",
           )
           self._event(task, EventStatus.VERIFICATION_FAILED, "verification_failed", {
               "proof_id": selected["proof_id"], "reason": reason,
           })
           return failed

       reason = "Proof does not contain enough observable data to evaluate the criteria"
       for proof in current_proofs:
           self.journal.defer_proof_verification(
               proof["proof_id"], reason, source="ProofVerificationEngine"
           )
       self._event(task, EventStatus.VERIFICATION_FAILED, "verification_waiting_human", {
           "reason": reason,
       })
       return self.journal.wait_for_human(task_id, reason, source="ProofVerificationEngine")


class NexusRuntime:
    """Runtime lifecycle and persistence authority over the operational journal."""

    def __init__(
        self,
        name: str = "NexusRuntime",
        operational_journal: Optional[OperationalJournal] = None,
        task_repository: Optional[TaskRepository] = None,
        event_repository: Optional[EventRepository] = None,
        ai_providers: Optional[List[AIProvider]] = None,
        executors: Optional[List[Executor]] = None,
        verifiers: Optional[List[Verifier]] = None,
        legacy_orchestrator: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
    ):
        from orchestrator import RobustOrchestrator

        self.name = name
        self.status = RuntimeStatus.STARTING
        canonical_repository_requested = (
            operational_journal is not None
            or task_repository is None
            or isinstance(task_repository, OperationalJournal)
        )
        if operational_journal is not None and task_repository not in (
            None, operational_journal
        ):
            raise ValueError(
                "OperationalJournal must be the task repository when explicitly provided"
            )
        if isinstance(task_repository, OperationalJournal):
            if operational_journal not in (None, task_repository):
                raise ValueError("Conflicting OperationalJournal repositories")
            operational_journal = task_repository
        if operational_journal is None:
            journal_path = None
            if (
                not canonical_repository_requested
                and event_repository is not None
                and hasattr(event_repository, "db_path")
            ):
                journal_path = event_repository.db_path
            operational_journal = OperationalJournal(journal_path)
        self.operational_journal = operational_journal
        self.task_repository = task_repository or self.operational_journal
        if event_repository is not None:
            if (
                canonical_repository_requested
                and event_repository is not self.operational_journal
            ):
                raise ValueError(
                    "A canonical runtime must persist runtime events in its OperationalJournal"
                )
            self.event_repository = event_repository
        else:
            self.event_repository = self.operational_journal
        self.ai_providers = ai_providers or []
        self.executors = executors or []
        self.verifiers = verifiers or []
        self.orchestrator = legacy_orchestrator
        self.tool_registry = tool_registry
        self.verification_engine = ProofVerificationEngine(self.operational_journal)
        self._recovery_snapshot = self.operational_journal.get_recovery_snapshot()
        self._run_id = self.operational_journal.create_session(
            source=self.name,
            metadata={"runtime": self.name},
        )
        self._dispatcher_task: Optional[asyncio.Task[Any]] = None
        self._dispatcher_error: Optional[BaseException] = None
        if self.orchestrator is None:
            if canonical_repository_requested:
                self.orchestrator = RobustOrchestrator(
                    journal=self.operational_journal,
                    session_id=self._run_id,
                    tool_registry=self.tool_registry,
                )
            elif hasattr(self.task_repository, "db_manager"):
                try:
                    self.orchestrator = RobustOrchestrator(self.task_repository)
                except TypeError:
                    self.orchestrator = None
        if hasattr(self.task_repository, "set_transition_observer"):
            self.task_repository.set_transition_observer(self._record_persisted_transition)
        self._record_event(
            task_id=None,
            stage="RUNTIME",
            status=EventStatus.RUNTIME_STATE_CHANGED,
            action="runtime_initialized",
            target="runtime",
            metadata={"state": self.status.value},
        )

    def register_ai_provider(self, provider: AIProvider) -> None:
        self.ai_providers.append(provider)

    def register_executor(self, executor: Executor) -> None:
        self.executors.append(executor)

    def register_verifier(self, verifier: Verifier) -> None:
        self.verifiers.append(verifier)

    def _record_event(
        self,
        task_id: Optional[str],
        stage: str,
        status: EventStatus,
        action: str,
        target: str,
        proof: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EventRecord:
        event = EventRecord(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            run_id=self._run_id,
            task_id=task_id,
            source="nexus_runtime",
            agent=self.name,
            stage=stage,
            status=status,
            action=action,
            target=target,
            proof=proof or {},
            result=result,
            error=error,
            metadata=metadata or {},
        )
        self.event_repository.append_event(event)
        return event

    def _record_persisted_transition(
        self,
        task_id: str,
        task_type: str,
        priority: str,
        status: str,
        result: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        event_status = {
            "QUEUED": EventStatus.TASK_QUEUED,
            "RUNNING": EventStatus.TASK_STARTED,
            "EXECUTED": EventStatus.EXECUTION_COMPLETED,
            "FAILED": EventStatus.TASK_FAILED,
            "CANCELLED": EventStatus.TASK_CANCELLED,
        }.get(status)
        if event_status is None:
            return
        self._record_event(
            task_id=task_id,
            stage="TASK",
            status=event_status,
            action="persisted_transition",
            target=task_type,
            proof={"observed_status": status},
            result=result,
            error=error,
            metadata={"priority": priority},
        )

    def initialize_orchestrator(self) -> Any:
        if self.orchestrator is None and isinstance(
            self.task_repository, OperationalJournal
        ):
            from orchestrator import RobustOrchestrator
            self.orchestrator = RobustOrchestrator(
                journal=self.operational_journal,
                session_id=self._run_id,
                tool_registry=self.tool_registry,
            )
        elif self.orchestrator is None and hasattr(self.task_repository, "db_manager"):
            from orchestrator import RobustOrchestrator
            self.orchestrator = RobustOrchestrator(self.task_repository)
        return self.orchestrator

    def boot(self) -> Dict[str, Any]:
        if self.status == RuntimeStatus.STOPPED:
            raise InvalidTransitionError("A stopped NexusRuntime instance cannot boot again")
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.BOOTING, source=self.name
        )
        self.status = RuntimeStatus.BOOTING
        self._record_event(
            task_id=None, stage="BOOT", status=EventStatus.BOOT_STARTED,
            action="bootstrap", target="runtime",
            metadata={"state": self.status.value},
        )
        recovery = self.recover()
        self.initialize_orchestrator()
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.RUNNING, source=self.name
        )
        self.status = RuntimeStatus.RUNNING
        self._record_event(
            task_id=None, stage="BOOT", status=EventStatus.BOOT_COMPLETED,
            action="boot_complete", target="runtime",
            metadata={"state": self.status.value},
        )
        return {
            "status": "BOOT_COMPLETED",
            "runtime": self.name,
            "run_id": self._run_id,
            "recovery": recovery,
        }

    async def start_dispatcher(self) -> None:
        if self.status != RuntimeStatus.RUNNING:
            raise InvalidTransitionError(
                "NexusRuntime must be booted before starting its task dispatcher"
            )
        if self._dispatcher_error is not None:
            raise RuntimeError("The Nexus task dispatcher previously failed") from self._dispatcher_error
        if self._dispatcher_task is not None and not self._dispatcher_task.done():
            return

        orchestrator = self.initialize_orchestrator()
        start_loop = getattr(orchestrator, "start_loop", None)
        if not callable(start_loop):
            raise JournalError("Canonical task dispatcher does not implement start_loop")

        self._dispatcher_task = asyncio.create_task(
            start_loop(), name=f"{self.name}-task-dispatcher"
        )
        self._dispatcher_task.add_done_callback(self._record_dispatcher_failure)
        await asyncio.sleep(0)
        if self._dispatcher_error is not None:
            raise RuntimeError("The Nexus task dispatcher failed to start") from self._dispatcher_error

    def _record_dispatcher_failure(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is None:
            return
        self._dispatcher_error = error
        self.status = RuntimeStatus.ERROR
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.ERROR, source=self.name
        )
        self._record_event(
            task_id=None,
            stage="RUNTIME",
            status=EventStatus.RUNTIME_STATE_CHANGED,
            action="task_dispatcher_failed",
            target="runtime",
            error=str(error),
            metadata={"state": self.status.value},
        )

    async def stop_dispatcher(self) -> None:
        orchestrator = self.initialize_orchestrator()
        stop = getattr(orchestrator, "stop", None)
        if callable(stop):
            stop()
        task = self._dispatcher_task
        if task is not None:
            await task
            self._dispatcher_task = None

    def start(self) -> Dict[str, Any]:
        if self.status == RuntimeStatus.STOPPED:
            raise InvalidTransitionError("A stopped NexusRuntime instance cannot be restarted")
        if self.status == RuntimeStatus.RUNNING:
            return {"status": self.status.value, "runtime": self.name, "run_id": self._run_id}
        recovery = self.recover()
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.RUNNING, source=self.name
        )
        self.status = RuntimeStatus.RUNNING
        return {
            "status": self.status.value,
            "runtime": self.name,
            "run_id": self._run_id,
            "recovery": recovery,
        }

    def stop(self) -> Dict[str, Any]:
        if self.status == RuntimeStatus.STOPPED:
            return {"status": self.status.value, "runtime": self.name, "run_id": self._run_id}
        stop_dispatcher = getattr(self.orchestrator, "stop", None)
        if callable(stop_dispatcher):
            stop_dispatcher()
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.STOPPING, source=self.name
        )
        self.status = RuntimeStatus.STOPPING
        self.operational_journal.update_runtime_session(
            self._run_id, RuntimeStatus.STOPPED, source=self.name
        )
        self.status = RuntimeStatus.STOPPED
        return {"status": self.status.value, "runtime": self.name, "run_id": self._run_id}

    def get_runtime_session(self) -> Optional[Dict[str, Any]]:
        return self.operational_journal.get_runtime_session(self._run_id)

    def get_active_tasks(self) -> List[TaskRecord]:
        return self.operational_journal.list_tasks_by_status(
            (
                TaskStatus.PLANNED,
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
                TaskStatus.WAITING_APPROVAL,
                TaskStatus.WAITING_HUMAN,
                TaskStatus.EXECUTED,
            )
        )

    def get_recovery_candidates(self) -> List[Dict[str, Any]]:
        return [
            {
                "task": task,
                "reason": "RUNNING_AT_LAST_RUNTIME_SCAN",
                "requires_reconciliation": True,
                "automatic_retry_allowed": False,
            }
            for task in self._recovery_snapshot[
                "running_tasks_requiring_reconciliation"
            ]
            if task.run_id != self._run_id
        ]

    def _recovery_key(self, task: TaskRecord, attempt_id: Optional[str], action: str) -> str:
        return f"boot:{task.task_id}:{attempt_id or 'no-attempt'}:{action.upper()}"

    def _recovery_calls_are_read_only(
        self, task: TaskRecord, attempt_id: Optional[str]
    ) -> bool:
        if task.execution_mode == "SIMULATED":
            return True
        if attempt_id is None:
            return task.metadata.get("recovery_safe_to_resume") is True
        calls = [
            call for call in self.operational_journal.list_records(
                "tool_calls", task_id=task.task_id
            )
            if call["attempt_id"] == attempt_id
        ]
        if not calls:
            if task.metadata.get("recovery_safe_to_resume") is True:
                return True
            payload = task.payload
            operation = payload.get("operation") if isinstance(payload, dict) else None
            parameters = payload.get("parameters", {}) if isinstance(payload, dict) else {}
            if task.task_type.upper() in {"HTTP"} and operation == "request":
                return str(parameters.get("method", "GET")).upper() in {
                    "GET", "HEAD", "OPTIONS",
                }
            if task.task_type.upper() in {"PLAYWRIGHT", "BROWSER"}:
                return operation in {"navigate", "extract", "initialize"}
            return False
        for call in calls:
            if call["execution_mode"] == "SIMULATED":
                continue
            tool = call["tool_name"].lower()
            operation = call["operation"].lower()
            request = self.operational_journal._decode(call["request_json"], {})
            if tool == "http" and str(request.get("method", "GET")).upper() in {
                "GET", "HEAD", "OPTIONS",
            }:
                continue
            if tool in {"playwright", "browser"} and operation in {
                "navigate", "extract", "initialize",
            }:
                continue
            return False
        return True

    def _enqueue_recovered_task(self, task: TaskRecord) -> bool:
        orchestrator = self.initialize_orchestrator()
        enqueue = getattr(orchestrator, "enqueue_recovered_task", None)
        if not callable(enqueue):
            return False
        return bool(enqueue(task.task_id))

    def _recover_previous_task(self, task: TaskRecord) -> Dict[str, Any]:
        attempts = self.operational_journal.list_records(
            "execution_attempts", task_id=task.task_id
        )
        latest_attempt = attempts[-1] if attempts else None
        attempt_id = latest_attempt["attempt_id"] if latest_attempt else None
        before = task.status

        if before == TaskStatus.VERIFIED:
            return {"task_id": task.task_id, "decision": "NO_ACTION", "status": before.value}
        if before == TaskStatus.FAILED:
            action = self.operational_journal.apply_recovery_decision(
                task.task_id, "RECONCILE", reason="FAILED tasks are terminal; no automatic retry",
                idempotency_key=self._recovery_key(task, attempt_id, "failed-terminal"),
                attempt_id=attempt_id, decision="RETRY_FORBIDDEN",
            )
            return {"task_id": task.task_id, "decision": "RETRY_FORBIDDEN", **action}
        if before == TaskStatus.CANCELLED:
            return {"task_id": task.task_id, "decision": "RETRY_FORBIDDEN", "status": before.value}

        if before == TaskStatus.EXECUTED:
            decision = self.operational_journal.apply_recovery_decision(
                task.task_id, "VERIFY_EXISTING_EFFECT",
                reason="Execution was persisted before shutdown; verify existing proof without rerunning",
                idempotency_key=self._recovery_key(task, attempt_id, "verify-existing-effect"),
                attempt_id=attempt_id, decision="VERIFY_EXISTING_EFFECT",
            )
            verified = self.verification_engine.verify_task(task.task_id)
            return {
                "task_id": task.task_id,
                "decision": "VERIFY_EXISTING_EFFECT",
                "status": verified.status.value,
                **decision,
            }

        if before == TaskStatus.RUNNING:
            if self._recovery_calls_are_read_only(task, attempt_id):
                decision = self.operational_journal.apply_recovery_decision(
                    task.task_id, "RESUME",
                    reason="No unconfirmed external side-effecting tool call was journaled",
                    idempotency_key=self._recovery_key(task, attempt_id, "resume"),
                    attempt_id=attempt_id, decision="SAFE_TO_RESUME",
                )
                resumed = self.operational_journal.get_task(task.task_id)
                queued = self._enqueue_recovered_task(resumed)
                if not queued and resumed.task_type not in getattr(
                    self.initialize_orchestrator(), "workers", {}
                ):
                    reason = f"No worker is registered for recovered task type {resumed.task_type}"
                    waiting = self.operational_journal.apply_recovery_decision(
                        task.task_id, "WAIT_HUMAN", reason=reason,
                        idempotency_key=self._recovery_key(
                            task, attempt_id, "worker-unavailable"
                        ),
                        attempt_id=attempt_id, decision="WORKER_UNAVAILABLE",
                    )
                    return {
                        "task_id": task.task_id,
                        "decision": "WAIT_HUMAN",
                        "status": waiting["after_state"],
                        **waiting,
                    }
                return {
                    "task_id": task.task_id,
                    "decision": "SAFE_TO_RESUME",
                    "status": resumed.status.value,
                    "enqueued": queued,
                    **decision,
                }
            reason = "A tool call may have produced an external effect; reconcile before retry"
            decision = self.operational_journal.apply_recovery_decision(
                task.task_id, "WAIT_HUMAN", reason=reason,
                idempotency_key=self._recovery_key(task, attempt_id, "ambiguous-effect"),
                attempt_id=attempt_id, decision="AMBIGUOUS",
            )
            return {
                "task_id": task.task_id,
                "decision": "AMBIGUOUS",
                "status": decision["after_state"],
                **decision,
            }

        if before in (TaskStatus.PLANNED, TaskStatus.QUEUED):
            decision = self.operational_journal.apply_recovery_decision(
                task.task_id, "RESUME",
                reason="Task had not started execution before shutdown",
                idempotency_key=self._recovery_key(task, attempt_id, "resume"),
                attempt_id=attempt_id, decision="SAFE_TO_RESUME",
            )
            queued_task = self.operational_journal.get_task(task.task_id)
            queued = self._enqueue_recovered_task(queued_task)
            if not queued and queued_task.task_type not in getattr(
                self.initialize_orchestrator(), "workers", {}
            ):
                reason = f"No worker is registered for recovered task type {queued_task.task_type}"
                waiting = self.operational_journal.apply_recovery_decision(
                    task.task_id, "WAIT_HUMAN", reason=reason,
                    idempotency_key=self._recovery_key(
                        task, attempt_id, "worker-unavailable"
                    ),
                    attempt_id=attempt_id, decision="WORKER_UNAVAILABLE",
                )
                return {
                    "task_id": task.task_id,
                    "decision": "WAIT_HUMAN",
                    "status": waiting["after_state"],
                    **waiting,
                }
            return {
                "task_id": task.task_id,
                "decision": "SAFE_TO_RESUME",
                "status": queued_task.status.value,
                "enqueued": queued,
                **decision,
            }

        # Approval- and human-waiting tasks are deliberately left for explicit input.
        decision = self.operational_journal.apply_recovery_decision(
            task.task_id, "RECONCILE",
            reason=f"Preserving existing {before.value} state for explicit resolution",
            idempotency_key=self._recovery_key(task, attempt_id, "preserve-waiting"),
            attempt_id=attempt_id, decision="PRESERVE_WAITING_STATE",
        )
        return {
            "task_id": task.task_id,
            "decision": "PRESERVE_WAITING_STATE",
            "status": before.value,
            **decision,
        }

    def load_state(self) -> Dict[str, Any]:
        tasks = self.task_repository.list_tasks(limit=100) if self.task_repository is not None else []
        events = self.event_repository.list_events(limit=100) if self.event_repository is not None else []
        return {
            "session_id": self._run_id,
            "tasks": len(tasks),
            "events": len(events),
            "status": self.status.value,
        }

    async def submit_mission(
        self,
        objective: str,
        tasks: List[Dict[str, Any]],
        *,
        correlation_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        source: str = "NexusRuntime",
        strategy: Optional[str] = None,
        success_criteria: Optional[Any] = None,
        failure_policy: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(self.operational_journal, OperationalJournal):
            raise JournalError("Mission submission requires OperationalJournal")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("Mission objective must be a non-empty string")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("A mission must contain at least one task")
        orchestrator = self.initialize_orchestrator()
        if getattr(orchestrator, "journal", None) is not self.operational_journal:
            raise JournalError(
                "Mission submission requires RobustOrchestrator using this OperationalJournal"
            )

        correlation_id = correlation_id or f"corr_{uuid.uuid4().hex}"
        mission_metadata = dict(metadata or {})
        mission_metadata.update({
            "strategy": strategy,
            "success_criteria": success_criteria,
            "failure_policy": failure_policy,
        })
        normalized_tasks = []
        for index, task_spec in enumerate(tasks):
            if not isinstance(task_spec, dict):
                raise ValueError(f"Task definition {index} must be a mapping")
            task_type = task_spec.get("task_type")
            payload = task_spec.get("payload", {})
            if not isinstance(task_type, str) or not task_type.strip():
                raise ValueError(f"Task definition {index} requires task_type")
            if task_type not in getattr(orchestrator, "workers", {}):
                raise ValueError(
                    f"No worker is registered for task type {task_type}"
                )
            if not isinstance(payload, dict):
                raise ValueError(f"Task definition {index} payload must be a mapping")
            priority = task_spec.get("priority", "MEDIUM")
            priority = getattr(priority, "name", priority)
            task_metadata = dict(task_spec.get("metadata") or {})
            for key in (
                "agent", "success_criteria", "risk", "requires_approval",
                "requires_human", "execution_mode",
            ):
                if key in task_spec:
                    task_metadata[key] = task_spec[key]
            execution_mode = str(task_metadata.get("execution_mode", "UNDECLARED")).upper()
            if execution_mode not in ("REAL", "SIMULATED", "UNDECLARED"):
                raise ValueError(f"Unsupported execution_mode for task {index}")
            task_metadata.pop("execution_mode", None)
            normalized_tasks.append({
                "task_type": task_type,
                "payload": self.operational_journal._redact(payload),
                "priority": str(priority),
                "metadata": self.operational_journal._redact(task_metadata),
                "execution_mode": execution_mode,
            })

        submission = {
            "objective": self.operational_journal._redact(objective.strip()),
            "mission_metadata": self.operational_journal._redact(mission_metadata),
            "tasks": normalized_tasks,
        }
        fingerprint = hashlib.sha256(
            json.dumps(submission, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing_mission = self.operational_journal.get_mission_by_correlation(correlation_id)
        if existing_mission:
            stored_metadata = self.operational_journal._decode(
                existing_mission["metadata_json"], {}
            )
            if (
                existing_mission["objective"] != submission["objective"]
                or stored_metadata.get("submission_fingerprint") != fingerprint
                or (mission_id is not None and existing_mission["mission_id"] != mission_id)
            ):
                raise JournalError(
                    "Mission correlation_id already belongs to different submission data"
                )
            mission_id = existing_mission["mission_id"]
            records = self.operational_journal.list_tasks_for_mission(mission_id)
            if len(records) != len(normalized_tasks):
                raise JournalError("Persisted mission task set does not match its submission")
        else:
            stored_metadata = dict(mission_metadata)
            stored_metadata["submission_fingerprint"] = fingerprint
            try:
                mission_id = self.operational_journal.create_mission(
                    objective.strip(),
                    session_id=self._run_id,
                    mission_id=mission_id,
                    source=source,
                    correlation_id=correlation_id,
                    metadata=stored_metadata,
                )
            except sqlite3.IntegrityError as exc:
                raise JournalError(
                    "Mission identifier or correlation_id already exists"
                ) from exc
            records = []
            for index, spec in enumerate(normalized_tasks):
                task_correlation = f"{correlation_id}:task:{index + 1}"
                record = self.operational_journal.create_task(
                    spec["task_type"],
                    spec["payload"],
                    mission_id=mission_id,
                    session_id=self._run_id,
                    priority=spec["priority"],
                    source=source,
                    correlation_id=task_correlation,
                    execution_mode=spec["execution_mode"],
                    metadata=spec["metadata"],
                )
                records.append(record)

        if existing_mission is None:
            self.operational_journal.record_mission_plan(
                mission_id,
                source=source,
                metadata={
                    "strategy": strategy,
                    "success_criteria": success_criteria,
                },
            )
            for record, spec in zip(records, normalized_tasks):
                self.operational_journal.create_task_step(
                    record.task_id,
                    1,
                    "UNDERSTAND",
                    status="SKIPPED",
                    source=source,
                    metadata={
                        "reason": "No semantic understanding stage is configured; "
                        "the deterministic planner consumes the submitted objective",
                    },
                )
                self.operational_journal.create_task_step(
                    record.task_id,
                    2,
                    "PLAN",
                    status="RECORDED",
                    source=source,
                    metadata={
                        "planner": "NexusAutoTaskEngine" if source == "nexus_api_server" else source,
                        "task_type": spec["task_type"],
                        "priority": spec["priority"],
                    },
                )

        queued_records = []
        for record, spec in zip(records, normalized_tasks):
            task_id = await orchestrator.submit_task(
                spec["task_type"],
                spec["payload"],
                spec["priority"],
                mission_id=mission_id,
                task_id=record.task_id,
                correlation_id=record.correlation_id,
                session_id=record.run_id or self._run_id,
            )
            queued_records.append(self.operational_journal.get_task(task_id))
        persisted_mission = self.operational_journal.get_mission_by_correlation(
            correlation_id
        )
        if persisted_mission is None:
            raise JournalError("Submitted mission is missing from OperationalJournal")
        return {
            "mission_id": mission_id,
            "session_id": existing_mission["session_id"] if existing_mission else self._run_id,
            "correlation_id": correlation_id,
            "status": persisted_mission["status"],
            "tasks": queued_records,
        }

    async def submit_task_async(
        self, task_type: str, payload: Dict[str, Any],
        priority: str = "MEDIUM",
    ) -> TaskRecord:
        if isinstance(self.task_repository, OperationalJournal):
            orchestrator = self.initialize_orchestrator()
            if getattr(orchestrator, "journal", None) is not self.operational_journal:
                raise JournalError(
                    "Task submission requires RobustOrchestrator using OperationalJournal"
                )
            task_id = await orchestrator.submit_task(
                task_type,
                payload,
                priority,
                session_id=self._run_id,
            )
            return self.operational_journal.get_task(task_id)
        if self.orchestrator is not None:
            task_id = await self.orchestrator.submit_task(task_type, payload, priority)
            task = self.task_repository.get_task(task_id)
            if task is None:
                task = TaskRecord(
                    task_id=task_id,
                    task_type=task_type,
                    source="NEXUS",
                    agent=self.name,
                    priority=priority,
                    status=TaskStatus.QUEUED,
                    payload=payload,
                    run_id=self._run_id,
                    correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
                )
                self.task_repository.save_task(task)
            self._record_event(
                task_id=task.task_id,
                stage="TASK",
                status=EventStatus.TASK_CREATED,
                action="CREATE",
                target=task_type,
                proof={"task_id": task.task_id},
                result={"task_id": task.task_id},
                metadata={"priority": priority},
            )
            return task

        task = TaskRecord(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            task_type=task_type,
            source="NEXUS",
            agent=self.name,
            priority=priority,
            status=TaskStatus.PLANNED,
            payload=payload,
            run_id=self._run_id,
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
        )
        if self.task_repository is not None:
            self.task_repository.save_task(task)
        self._record_event(
            task_id=task.task_id,
            stage="TASK",
            status=EventStatus.TASK_CREATED,
            action="CREATE",
            target=task_type,
            proof={"task_id": task.task_id},
            result={"task_id": task.task_id},
            metadata={"priority": priority},
        )
        return task

    def submit_task(self, task_type: str, payload: Dict[str, Any], priority: str = "MEDIUM") -> TaskRecord:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError("Use submit_task_async from an async context.")
        return asyncio.run(self.submit_task_async(task_type, payload, priority))

    def recover(self) -> Dict[str, Any]:
        self._record_event(
            task_id=None,
            stage="RECOVERY",
            status=EventStatus.BOOT_STARTED,
            action="recovery_started",
            target="operational_journal",
            metadata={"session_id": self._run_id},
        )
        snapshot = self.operational_journal.get_recovery_snapshot()
        orchestrator = self.initialize_orchestrator()
        active_task_ids = getattr(orchestrator, "_queued_or_active_task_ids", set())
        previous_tasks = [
            task for task in snapshot["non_terminal_tasks"]
            if task.run_id != self._run_id and task.task_id not in active_task_ids
        ]
        previous_tasks.extend(
            task for task in snapshot["failed_tasks_requiring_recovery_decision"]
            if task.run_id != self._run_id and task.task_id not in active_task_ids
        )
        # Include terminal failures exactly once in recovery decision history.
        tasks_by_id = {task.task_id: task for task in previous_tasks}
        decisions = [
            self._recover_previous_task(task)
            for task in tasks_by_id.values()
        ]
        refreshed = self.operational_journal.get_recovery_snapshot()
        candidates = [
            {
                "task": task,
                "reason": "RUNNING_AT_LAST_RUNTIME_SCAN",
                "requires_reconciliation": True,
                "automatic_retry_allowed": False,
            }
            for task in refreshed["running_tasks_requiring_reconciliation"]
            if task.run_id != self._run_id
        ]
        self._record_event(
            task_id=None,
            stage="RECOVERY",
            status=EventStatus.RECOVERY_SCAN_COMPLETED,
            action="recovery_completed",
            target="operational_journal",
            metadata={
                "non_terminal_tasks": len(refreshed["non_terminal_tasks"]),
                "running_tasks_requiring_reconciliation": len(candidates),
                "decisions": len(decisions),
            },
        )
        previous_sessions = [
            session for session in self.operational_journal.list_runtime_sessions()
            if session["session_id"] != self._run_id
        ]
        if any(item["decision"] == "AMBIGUOUS" for item in decisions):
            recovery_status = "RECONCILIATION_REQUIRED"
        elif decisions:
            recovery_status = "RECOVERY_DECISIONS_APPLIED"
        else:
            recovery_status = "NO_NON_TERMINAL_TASKS"
        self._recovery_snapshot = refreshed
        return {
            "recovery_status": recovery_status,
            "automatic_resume": any(
                item.get("decision") == "SAFE_TO_RESUME" and item.get("enqueued")
                for item in decisions
            ),
            "session": self.get_runtime_session(),
            "previous_sessions": previous_sessions,
            "missions": refreshed["missions"],
            "non_terminal_tasks": refreshed["non_terminal_tasks"],
            "running_tasks_requiring_reconciliation": candidates,
            "failed_tasks_requiring_recovery_decision": refreshed[
                "failed_tasks_requiring_recovery_decision"
            ],
            "tasks_loaded": len(refreshed["non_terminal_tasks"]),
            "decisions": decisions,
        }


__all__ = [
    "TaskStatus",
    "EventStatus",
    "RuntimeStatus",
    "ProofState",
    "TaskRecord",
    "EventRecord",
    "TaskRepository",
    "EventRepository",
    "JournalError",
    "InvalidTransitionError",
    "OperationalJournal",
    "AIProvider",
    "Executor",
    "Verifier",
    "SQLiteTaskRepository",
    "SQLiteEventRepository",
    "LegacyOrchestratorAdapter",
    "TaskPersistenceAdapter",
    "InMemoryEventRepository",
    "NexusRuntime",
]
