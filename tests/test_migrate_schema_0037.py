from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import (
    EVIDENCE_RERESEARCH_LINEAGE_SCHEMA_VERSION,
    SOURCE_DISCOVERY_RECONCILIATION_SCHEMA_VERSION,
    initialize_database,
    migrate_0036_to_0037,
)


def _unique_columns(connection: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for index in connection.execute(f"PRAGMA index_list({table})"):
        if int(index[2]) == 1:
            result.add(tuple(
                row[2] for row in connection.execute(f"PRAGMA index_info('{index[1]}')")
            ))
    return result


def test_0037_scopes_immutable_evidence_links_to_each_research_run(tmp_path: Path):
    path = tmp_path / "0036.db"
    initialize_database(path, through=SOURCE_DISCOVERY_RECONCILIATION_SCHEMA_VERSION)

    result = migrate_0036_to_0037(path)

    assert result.applied_migrations == (EVIDENCE_RERESEARCH_LINEAGE_SCHEMA_VERSION,)
    connection = sqlite3.connect(path)
    try:
        assert ("research_run_id", "retrieval_id") in _unique_columns(
            connection, "evidence_candidate_retrievals"
        )
        assert ("research_run_id", "retrieval_id") in _unique_columns(
            connection, "evidence_candidate_excerpts"
        )
        assert ("research_run_id", "excerpt_id") in _unique_columns(
            connection, "evidence_source_lineage"
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0037_is_idempotent(tmp_path: Path):
    path = tmp_path / "0037.db"
    initialize_database(path, through=EVIDENCE_RERESEARCH_LINEAGE_SCHEMA_VERSION)
    result = migrate_0036_to_0037(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()
