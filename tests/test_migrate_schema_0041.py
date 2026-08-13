"""Forward-only checks for the reviewer document quality gate schema."""
from __future__ import annotations

import sqlite3

import pytest

from app.storage.db import (
    CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION,
    REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0040_to_0041,
)


def _objects(conn, kind: str) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,),
        )
    }


def test_0040_to_0041_replaces_reviewer_triggers_and_preserves_all_data(tmp_path):
    path = tmp_path / "document-gate.db"
    initialize_database(path, through=CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION)
    before = sqlite3.connect(path)
    try:
        tables = _objects(before, "table")
        triggers = _objects(before, "trigger")
        counts = {
            table: before.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        old_sql = before.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='content_c2_pending_approval_contract'"
        ).fetchone()[0]
        old_role_sql = before.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='role_provider_executions_settle'"
        ).fetchone()[0]
    finally:
        before.close()
    assert "document_review" not in old_sql

    result = migrate_0040_to_0041(path)
    assert result.applied_migrations == (REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION

    after = sqlite3.connect(path)
    try:
        assert _objects(after, "table") == tables
        assert _objects(after, "trigger") == triggers
        for table, count in counts.items():
            if table == "schema_migrations":
                continue  # gains exactly the 0041 ledger row
            assert after.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == count
        assert after.execute(
            "SELECT count(*) FROM schema_migrations"
        ).fetchone()[0] == counts["schema_migrations"] + 1
        new_sql = after.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='content_c2_pending_approval_contract'"
        ).fetchone()[0]
        assert "document_review.approved" in new_sql
        new_role_sql = after.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='role_provider_executions_settle'"
        ).fetchone()[0]
        assert new_role_sql != old_role_sql
        assert "production_article_reviewer_opus_v3" in new_role_sql
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()


def test_0041_is_idempotent_and_forward_only(tmp_path):
    path = tmp_path / "idempotent.db"
    initialize_database(path, through=REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION)
    result = migrate_0040_to_0041(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()

    too_old = tmp_path / "too-old.db"
    initialize_database(too_old, through="0039_article_review_resume")
    with pytest.raises(Exception) as exc:
        migrate_0040_to_0041(too_old)
    assert "0040" in str(exc.value)
    assert database_schema_versions(too_old)[-1] == "0039_article_review_resume"


def test_0041_failure_rolls_back_triggers_and_ledger_to_0040(tmp_path):
    path = tmp_path / "rollback.db"
    initialize_database(path, through=CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION)
    conn = connect(path)
    try:
        before = {
            name: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (name,),
            ).fetchone()[0]
            for name in (
                "content_c2_pending_approval_contract",
                "content_review_resume_executions_settle",
                "role_provider_executions_settle",
            )
        }

        def fail(version):
            if version == REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION:
                raise RuntimeError("controlled rollback probe")

        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION,
                transaction_failpoint=fail,
            )
        assert conn.in_transaction is False
        assert database_schema_versions(path)[-1] == CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION
        for name, sql in before.items():
            assert conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (name,),
            ).fetchone()[0] == sql
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_fresh_database_reaches_the_document_gate_runtime_floor(tmp_path):
    """0041 stays on a fresh install; the runtime floor itself moved on to 0042."""
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION in applied
    assert applied.index(REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION) == 40
    assert RUNTIME_SCHEMA_VERSION >= REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION
    assert applied[-1] == RUNTIME_SCHEMA_VERSION
    assert len(applied) == 42


def test_durable_floor_rejects_an_approve_without_a_passing_document_review(tmp_path):
    """The SQL predicate itself, evaluated by SQLite on both result shapes."""
    condition = (
        "json_type(?1,'$.document_review')='object' "
        " AND json_extract(?1,'$.document_review.approved')=1 "
        " AND (SELECT count(*) FROM json_each("
        "      json_extract(?1,'$.document_review.checks')))=6 "
        " AND NOT EXISTS (SELECT 1 FROM json_each("
        "      json_extract(?1,'$.document_review.checks')) c WHERE c.value!=1) "
        " AND json_array_length(json_extract(?1,'$.document_review.findings'))=0"
    )
    checks = {
        "TITLE_REFLECTS_BODY": True, "TITLE_PROMISE_FULFILLED": True,
        "TITLE_MECHANISM_EXPLAINED": True, "BRIEF_QUESTION_ANSWERED": True,
        "THESIS_CONSISTENT": True, "CONCLUSIONS_WITHIN_EVIDENCE": True,
    }
    import json

    conn = sqlite3.connect(":memory:")
    try:
        approved = json.dumps({"document_review": {
            "approved": True, "checks": checks, "failed_checks": [], "findings": []}})
        assert conn.execute(f"SELECT ({condition})", (approved,)).fetchone()[0] == 1

        failing = json.dumps({"document_review": {
            "approved": False,
            "checks": {**checks, "TITLE_MECHANISM_EXPLAINED": False},
            "failed_checks": ["TITLE_MECHANISM_EXPLAINED"],
            "findings": ["explain the arithmetic the title promises"]}})
        assert conn.execute(f"SELECT ({condition})", (failing,)).fetchone()[0] == 0

        # The exact live shape: no whole-article verdict at all.
        legacy = json.dumps({"decision": "APPROVE", "entries": []})
        assert conn.execute(f"SELECT ({condition})", (legacy,)).fetchone()[0] == 0
    finally:
        conn.close()
