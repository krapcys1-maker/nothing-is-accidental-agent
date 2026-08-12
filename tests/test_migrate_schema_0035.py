from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import (
    END_TO_END_CONNECTION_SCHEMA_VERSION,
    RESEARCH_QUALIFICATION_SCHEMA_VERSION,
    initialize_database,
    migrate_0034_to_0035,
)


def test_0035_preserves_history_and_adds_approved_search_dimension(tmp_path: Path):
    path = tmp_path / "0034.db"
    initialize_database(path, through=END_TO_END_CONNECTION_SCHEMA_VERSION)
    before = sqlite3.connect(path)
    try:
        before_count = before.execute(
            "SELECT count(*) FROM model_qualification_runs"
        ).fetchone()[0]
    finally:
        before.close()

    result = migrate_0034_to_0035(path)
    assert result.applied_migrations == (RESEARCH_QUALIFICATION_SCHEMA_VERSION,)

    connection = sqlite3.connect(path)
    try:
        columns = {
            row[1] for row in connection.execute("pragma table_info(model_qualification_runs)")
        }
        assert "require_source_discovery" in columns
        assert connection.execute(
            "SELECT count(*) FROM model_qualification_runs"
        ).fetchone()[0] == before_count
        assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert connection.execute("pragma foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()[0] == RESEARCH_QUALIFICATION_SCHEMA_VERSION
    finally:
        connection.close()


def test_0035_is_idempotent(tmp_path: Path):
    path = tmp_path / "0035.db"
    initialize_database(path, through=RESEARCH_QUALIFICATION_SCHEMA_VERSION)
    result = migrate_0034_to_0035(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()
