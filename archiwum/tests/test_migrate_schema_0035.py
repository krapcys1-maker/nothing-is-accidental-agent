from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import (
    ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,
    ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION,
    END_TO_END_CONNECTION_SCHEMA_VERSION,
    RESEARCH_QUALIFICATION_SCHEMA_VERSION,
    initialize_database,
    migrate_0034_to_0035,
    migrate_0030_to_0031,
    migrate_0031_to_0032,
    migrate_0032_to_0033,
    migrate_0033_to_0034,
)
from tests.test_article_writer_opus_switch import _seed_fable_history_and_binding


def test_0035_preserves_history_and_adds_approved_search_dimension(tmp_path: Path):
    path = tmp_path / "0034.db"
    _seed_fable_history_and_binding(path)
    assert migrate_0030_to_0031(path).applied_migrations == (
        ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION,
    )
    migrate_0031_to_0032(path)
    migrate_0032_to_0033(path)
    migrate_0033_to_0034(path)
    before = sqlite3.connect(path)
    try:
        before_rows = before.execute(
            "SELECT * FROM model_qualification_runs ORDER BY request_id"
        ).fetchall()
        assert before_rows
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
        after_rows = connection.execute(
            "SELECT " + ",".join(
                column[1] for column in connection.execute(
                    "pragma table_info(model_qualification_runs)"
                ) if column[1] != "require_source_discovery"
            ) + " FROM model_qualification_runs ORDER BY request_id"
        ).fetchall()
        assert after_rows == before_rows
        assert connection.execute(
            "SELECT count(*) FROM model_qualification_runs"
        ).fetchone()[0] == len(before_rows)
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
