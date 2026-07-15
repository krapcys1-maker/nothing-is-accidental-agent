"""Połączenie SQLite i uruchamianie migracji."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_RUNNER_TRANSACTIONAL_MIGRATIONS = frozenset({
    "0007_candidate_attempts",
    "0008_staged_force_reresearch",
    "0009_jobs_system_flags",
    "0010_provider_attempts",
    "0011_provider_attempt_invariants",
    "0012_provider_ledger_hardening",
    "0013_provider_attempt_usage_integrity",
})


def _is_test_protected_database(db_path: Path | str) -> bool:
    """Reject the production DB for pytest collection, setup and subprocesses."""
    if not os.environ.get("NIA_TEST_MODE"):
        return False
    from app.testing.safety_kernel import is_protected_sqlite_database

    return is_protected_sqlite_database(db_path)


def connect(db_path: Path | str) -> sqlite3.Connection:
    if _is_test_protected_database(db_path):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        if str(db_path) != ":memory:":
            journal_mode = conn.execute("PRAGMA journal_mode=WAL;").fetchone()[0].lower()
            if journal_mode != "wal":
                raise RuntimeError(
                    f"SQLite database {db_path} did not enable WAL (active mode: {journal_mode})."
                )
        return conn
    except Exception:
        conn.close()
        raise


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Stosuje niezaaplikowane pliki .sql w kolejności nazw. Zwraca listę zastosowanych wersji."""
    _ensure_migrations_table(conn)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    for sql_file in sorted(Path(migrations_dir).glob("*.sql")):
        version = sql_file.stem
        if version in applied:
            continue
        sql = sql_file.read_text(encoding="utf-8")
        if version in _RUNNER_TRANSACTIONAL_MIGRATIONS:
            quoted_version = conn.execute("SELECT quote(?)", (version,)).fetchone()[0]
            try:
                conn.executescript(
                    "BEGIN IMMEDIATE;\n"
                    f"{sql}\n"
                    f"INSERT INTO schema_migrations(version) VALUES ({quoted_version});\n"
                    "COMMIT;"
                )
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
        else:
            # 0001-0006 retain their historical migration contract; 0006 has its
            # own BEGIN IMMEDIATE/COMMIT and must not be nested here.
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            conn.commit()
        newly.append(version)
    return newly
