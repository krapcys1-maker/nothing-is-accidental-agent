"""Forward-only checks for owner conservative CONTENT/role reconciliation."""
from __future__ import annotations

import sqlite3

from app.storage.db import (
    ARTICLE_REVIEW_RESUME_SCHEMA_VERSION,
    CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0039_to_0040,
)


def test_0039_to_0040_is_additive_and_preserves_existing_data(tmp_path):
    path = tmp_path / "content-role-reconciliation.db"
    initialize_database(path, through=ARTICLE_REVIEW_RESUME_SCHEMA_VERSION)
    before = sqlite3.connect(path)
    try:
        counts = {
            table: before.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "jobs", "content_items", "provider_attempts",
                "role_provider_executions", "model_usage",
            )
        }
    finally:
        before.close()

    result = migrate_0039_to_0040(path)
    assert result.applied_migrations == (CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT count(*) FROM conservative_content_reconciliations"
        ).fetchone()[0] == 0
        for table, count in counts.items():
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_fresh_database_reaches_0040_and_has_immutable_ledger(tmp_path):
    path = tmp_path / "fresh-0040.db"
    initialize_database(path)
    assert database_schema_versions(path)[-1] == CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION
    connection = sqlite3.connect(path)
    try:
        triggers = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert {
            "conservative_content_reconciliations_contract",
            "conservative_content_reconciliations_provider_source",
            "conservative_content_reconciliations_role_source",
            "conservative_content_reconciliations_no_update",
            "conservative_content_reconciliations_no_delete",
        } <= triggers
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0040_is_idempotent_and_cli_requires_exact_confirmation(tmp_path):
    from scripts.migrate_schema_0040 import main

    current = tmp_path / "current.db"
    initialize_database(current)
    result = migrate_0039_to_0040(current)
    assert result.idempotent is True and result.applied_migrations == ()

    older = tmp_path / "cli.db"
    initialize_database(older, through=ARTICLE_REVIEW_RESUME_SCHEMA_VERSION)
    assert main(["--db-path", str(older)]) == 2
    assert database_schema_versions(older)[-1] == ARTICLE_REVIEW_RESUME_SCHEMA_VERSION
    assert main([
        "--db-path", str(older), "--confirm-0039-to-0040",
    ]) == 0
    assert database_schema_versions(older)[-1] == CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION
