"""Połączenie SQLite i uruchamianie migracji."""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def connect(db_path: Path | str) -> sqlite3.Connection:
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
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        conn.commit()
        newly.append(version)
    return newly
