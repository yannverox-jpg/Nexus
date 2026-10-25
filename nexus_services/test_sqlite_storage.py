"""Regression tests for durable SQLite settings and versioned schema migrations."""
from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from nexus_services.sqlite_storage import apply_migrations, connect_sqlite


class SQLiteStorageTests(unittest.TestCase):
    def test_file_database_uses_wal_foreign_keys_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "nexus.db")
            with connect_sqlite(path, timeout=7) as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 7000)
                connection.execute("CREATE TABLE IF NOT EXISTS durable (id INTEGER PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO durable(value) VALUES (?)", ("persisted",))

            # Reopening the database proves the data lives on disk, not in a process cache.
            with connect_sqlite(path) as reopened:
                self.assertEqual(reopened.execute("SELECT value FROM durable").fetchone()[0], "persisted")

    def test_migrations_apply_once_and_record_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "migration.db")
            calls = []

            def migration_one(connection):
                calls.append(1)
                connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")

            def migration_two(connection):
                calls.append(2)
                connection.execute("ALTER TABLE records ADD COLUMN source TEXT NOT NULL DEFAULT 'nexus'")

            migrations = [(1, migration_one), (2, migration_two)]
            with connect_sqlite(path) as connection:
                self.assertEqual(apply_migrations(connection, "test_store", migrations), 2)
                self.assertEqual(apply_migrations(connection, "test_store", migrations), 2)
                versions = connection.execute(
                    "SELECT version FROM nexus_schema_migrations WHERE component = ? ORDER BY version",
                    ("test_store",),
                ).fetchall()
                self.assertEqual([row[0] for row in versions], [1, 2])
            self.assertEqual(calls, [1, 2])

    def test_concurrent_writers_do_not_lose_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "concurrent.db")
            with connect_sqlite(path) as connection:
                connection.execute("CREATE TABLE entries (id TEXT PRIMARY KEY, value INTEGER NOT NULL)")

            def write_batch(batch_number):
                with connect_sqlite(path, timeout=15) as connection:
                    for item in range(25):
                        connection.execute(
                            "INSERT INTO entries(id, value) VALUES (?, ?)",
                            (f"{batch_number}:{item}", item),
                        )

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write_batch, range(4)))

            with connect_sqlite(path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            self.assertEqual(count, 100)


if __name__ == "__main__":
    unittest.main()
