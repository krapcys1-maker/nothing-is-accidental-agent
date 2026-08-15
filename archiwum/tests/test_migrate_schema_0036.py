from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import (
    RESEARCH_QUALIFICATION_SCHEMA_VERSION,
    SOURCE_DISCOVERY_RECONCILIATION_SCHEMA_VERSION,
    initialize_database,
    migrate_0035_to_0036,
)


def test_0036_widens_only_the_reconciliation_lineage_trigger(tmp_path: Path):
    path = tmp_path / "0035.db"
    initialize_database(path, through=RESEARCH_QUALIFICATION_SCHEMA_VERSION)

    result = migrate_0035_to_0036(path)

    assert result.applied_migrations == (
        SOURCE_DISCOVERY_RECONCILIATION_SCHEMA_VERSION,
    )
    connection = sqlite3.connect(path)
    try:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='provider_attempts_reconcile_requires_consistent_lineage'"
        ).fetchone()[0]
        assert "article_research_source_discovery_v1" in sql
        assert "source_discovery_approvals" in sql
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0036_is_idempotent(tmp_path: Path):
    path = tmp_path / "0036.db"
    initialize_database(path, through=SOURCE_DISCOVERY_RECONCILIATION_SCHEMA_VERSION)
    result = migrate_0035_to_0036(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()
