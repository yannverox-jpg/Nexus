"""Shared durable SQLite connection and migration primitives for Nexus.

SQLite is suitable for a durable single-node deployment. Multi-instance and
high-write deployments should use a PostgreSQL-backed repository instead.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Iterable

Migration = tuple[int, Callable[[sqlite3.Connection], None]]


def connect_sqlite(
    database_path: str,
    *,
    timeout: float = 30.0,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Open a consistently configured connection with durable file settings."""
    path = str(database_path)
    memory_database = (
        path == ":memory:" or "mode=memory" in path or path.startswith("file::memory:")
    )
    if path != ":memory:" and not path.startswith("file:"):
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    bounded_timeout = max(0.1, float(timeout))
    conn = sqlite3.connect(
        path,
        timeout=bounded_timeout,
        uri=path.startswith("file:"),
        check_same_thread=check_same_thread,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(bounded_timeout * 1000)}")
    conn.execute("PRAGMA foreign_keys = ON")
    if not memory_database:
        # WAL mode persists in the database; avoid attempting to reset it on
        # every connection, which can create unnecessary lock contention.
        try:
            current_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if current_mode != "wal":
                conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                conn.close()
                raise
        conn.execute("PRAGMA synchronous = FULL")
    return conn


def apply_migrations(
    conn: sqlite3.Connection,
    component: str,
    migrations: Iterable[Migration],
) -> int:
    """Apply ordered, component-scoped schema migrations once, atomically."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_schema_migrations (
            component TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY (component, version)
        )
        """
    )
    current_row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS version "
        "FROM nexus_schema_migrations WHERE component = ?",
        (component,),
    ).fetchone()
    current = int(current_row["version"])
    for version, upgrade in sorted(migrations, key=lambda item: item[0]):
        if version <= current:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            upgrade(conn)
            conn.execute(
                "INSERT INTO nexus_schema_migrations(component, version) VALUES (?, ?)",
                (component, version),
            )
            conn.commit()
            current = version
        except Exception:
            conn.rollback()
            raise
    return current
