"""Forward-only offline checks for the isolated REVIEW-ONLY authority."""
from __future__ import annotations

import sqlite3

from app.storage.db import (
    ARTICLE_REVIEW_RESUME_SCHEMA_VERSION,
    CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0038_to_0039,
)


def test_0039_is_additive_transactional_and_keeps_0038_data(tmp_path):
    path = tmp_path / "review-resume.db"
    initialize_database(path, through=CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION)
    before = sqlite3.connect(path)
    try:
        before_counts = {
            table: before.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "content_items", "content_drafts", "role_provider_executions",
                "model_usage",
            )
        }
    finally:
        before.close()

    result = migrate_0038_to_0039(path)
    assert result.applied_migrations == (ARTICLE_REVIEW_RESUME_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == ARTICLE_REVIEW_RESUME_SCHEMA_VERSION
    connection = sqlite3.connect(path)
    try:
        names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "content_review_resume_approvals",
            "content_review_resume_sessions",
            "content_review_resume_executions",
        } <= names
        for table, count in before_counts.items():
            assert connection.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0] == count
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_0039_schema_closes_third_review_and_third_writer(tmp_path):
    path = tmp_path / "review-resume-bounds.db"
    initialize_database(path)
    connection = sqlite3.connect(path)
    try:
        review_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='content_review_resume_executions'"
        ).fetchone()[0].replace(" ", "")
        writer_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='content_writer_attempts'"
        ).fetchone()[0].replace(" ", "")
        trigger_names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert "writer_attempt_noINTEGERNOTNULLCHECK(writer_attempt_noIN(1,2))" in review_sql
        assert "review_noINTEGERNOTNULLCHECK(review_noIN(1,2))" in review_sql
        assert "attempt_noINTEGERNOTNULLCHECK(attempt_noIN(1,2))" in writer_sql
        assert "content_review_resume_executions_contract" in trigger_names
        assert "provider_attempts_no_retry_without_resolver" in trigger_names
    finally:
        connection.close()


def test_0039_is_idempotent(tmp_path):
    path = tmp_path / "review-resume-current.db"
    initialize_database(path, through=ARTICLE_REVIEW_RESUME_SCHEMA_VERSION)
    result = migrate_0038_to_0039(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()


def test_0039_cli_requires_exact_confirmation(tmp_path):
    from scripts.migrate_schema_0039 import main

    path = tmp_path / "review-resume-cli.db"
    initialize_database(path, through=CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION)
    assert main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == CONTENT_PROVIDER_TIMEOUT_SCHEMA_VERSION
    assert main([
        "--db-path", str(path), "--confirm-0038-to-0039",
    ]) == 0
    assert database_schema_versions(path)[-1] == ARTICLE_REVIEW_RESUME_SCHEMA_VERSION
