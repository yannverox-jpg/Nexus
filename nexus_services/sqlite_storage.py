"""Shared durable SQLite connection and migration primitives for Nexus.

SQLite is appropriate for one durable application instance. For multi-instance,
high-write production deployments, use a PostgreSQL-backed repository instead.
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
    """Open a consistently configured SQLite connection.

    File-backed databases use WAL, FULL synchronous commits, foreign keys, and
    a bounded busy timeout. Parent directories are created with normal OS
    permissions; credentials and payment-card data must never be stored here.
    """
    path = str(database_path)
    if path != ":memory:" and not path.startswith("file:"):
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path,
        timeout=max(0.1, float(timeout)),
        uri=path.startswith("file:"),
        check_same_thread=check_same_thread,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(max(0.1, float(timeout)) * 1000)}")
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:" and "mode=memory" not in path:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
    return conn


def apply_migrations(
    conn: sqlite3.Connection,
    component: str,
    migrations: Iterable[Migration],
) -> int:
    """Apply ordered, component-scoped migrations once, atomically per migration."""
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
        "SELECT COALESCE(MAX(version), 0) AS version FROM nexus_schema_migrations WHERE component = ?",
        (component,),
    ).fetchone()
    current = int(current_row["version"])
    for version, upgrade in sorted(migrations, key=lambda item: item[0]):
        if version <= current:
            continue
        # Explicit transaction makes each schema upgrade all-or-nothing.
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
