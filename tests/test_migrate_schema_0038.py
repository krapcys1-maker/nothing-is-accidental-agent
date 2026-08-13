from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.storage.db import (
    CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION,
    EVIDENCE_RERESEARCH_LINEAGE_SCHEMA_VERSION,
    initialize_database,
    migrate_0037_to_0038,
    connect_existing_writable,
)
from app.content.foundation import ContentType
from app.storage.repositories import SqliteStorage
from tests.test_content_pipeline_c3 import run_provider


def test_0038_widens_only_writer_intent_timeout_and_preserves_guards(
    tmp_path: Path, account,
):
    path = tmp_path / "0037.db"
    initialize_database(path, through=EVIDENCE_RERESEARCH_LINEAGE_SCHEMA_VERSION)
    storage = SqliteStorage(connect_existing_writable(path))
    run_provider(
        storage, account, ContentType.ARTICLE, suffix="migration-0038-nonempty",
    )
    before = [tuple(row) for row in storage.conn.execute(
        "SELECT * FROM content_writer_intents ORDER BY intent_id"
    ).fetchall()]
    assert before
    storage.close()

    result = migrate_0037_to_0038(path)

    assert result.applied_migrations == (CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION,)
    connection = sqlite3.connect(path)
    try:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='content_writer_intents'"
        ).fetchone()[0]
        assert "timeout_seconds<=300.0" in table_sql
        assert "timeout_seconds<=30.0" not in table_sql
        trigger_names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='content_writer_intents'"
            )
        }
        assert trigger_names == {
            "content_writer_intents_contract",
            "content_writer_intents_controlled_provider_binding",
            "content_writer_intents_stable_role_contract",
            "content_writer_intents_no_update",
            "content_writer_intents_no_delete",
        }
        assert connection.execute(
            "SELECT * FROM content_writer_intents ORDER BY intent_id"
        ).fetchall() == before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0038_is_idempotent_and_cli_guard_is_explicit(tmp_path: Path):
    path = tmp_path / "0038.db"
    initialize_database(path, through=CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION)
    result = migrate_0037_to_0038(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()

    from scripts.migrate_schema_0038 import main

    assert main(["--db-path", str(path)]) == 2
