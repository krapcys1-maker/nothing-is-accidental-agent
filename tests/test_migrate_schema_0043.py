"""Forward-only checks for the per-chunk reviewer execution ledger."""
from __future__ import annotations

import sqlite3

import pytest

from app.storage.db import (
    RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0042_to_0043,
)


def _objects(conn, kind: str) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,),
        )
    }


def test_0042_to_0043_only_adds_the_chunk_ledger_and_preserves_all_data(tmp_path):
    path = tmp_path / "chunking.db"
    initialize_database(
        path, through=RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    )
    before = sqlite3.connect(path)
    try:
        tables = _objects(before, "table")
        triggers = _objects(before, "trigger")
        counts = {
            table: before.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        role_sql = before.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='role_provider_executions_settle'"
        ).fetchone()[0]
    finally:
        before.close()
    assert "content_review_chunk_executions" not in tables

    result = migrate_0042_to_0043(path)
    assert result.applied_migrations == (REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION

    after = sqlite3.connect(path)
    try:
        assert _objects(after, "table") - tables == {"content_review_chunk_executions"}
        assert _objects(after, "trigger") - triggers == {
            "content_review_chunk_executions_contract",
            "content_review_chunk_executions_settle",
            "content_review_chunk_executions_no_delete",
        }
        # Nothing that already enforced the review contract is touched: the
        # umbrella still settles the whole accounting under the same rule.
        assert triggers <= _objects(after, "trigger")
        assert after.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='role_provider_executions_settle'"
        ).fetchone()[0] == role_sql
        for table, count in counts.items():
            if table == "schema_migrations":
                continue  # gains exactly the 0043 ledger row
            assert after.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0] == count
        assert after.execute(
            "SELECT count(*) FROM schema_migrations"
        ).fetchone()[0] == counts["schema_migrations"] + 1
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()


def test_0043_is_idempotent_and_forward_only(tmp_path):
    path = tmp_path / "idempotent.db"
    initialize_database(path, through=REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION)
    result = migrate_0042_to_0043(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()

    too_old = tmp_path / "too-old.db"
    initialize_database(too_old, through="0041_reviewer_document_quality_gate")
    with pytest.raises(Exception) as exc:
        migrate_0042_to_0043(too_old)
    assert "0042" in str(exc.value)
    assert database_schema_versions(too_old)[-1] == (
        "0041_reviewer_document_quality_gate"
    )


def test_0043_failure_rolls_back_the_table_and_the_ledger_to_0042(tmp_path):
    path = tmp_path / "rollback.db"
    initialize_database(
        path, through=RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    )
    conn = connect(path)
    try:
        def fail(version):
            if version == REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION:
                raise RuntimeError("controlled rollback probe")

        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION,
                transaction_failpoint=fail,
            )
        assert conn.in_transaction is False
        assert database_schema_versions(path)[-1] == (
            RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION
        )
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE name LIKE 'content_review_chunk_executions%'"
        ).fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_fresh_database_reaches_the_chunking_runtime_floor(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert applied[-1] == REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION
    assert RUNTIME_SCHEMA_VERSION == REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION
    assert len(applied) == 43


def test_the_operator_entrypoint_fails_closed_without_its_confirmation(tmp_path):
    from scripts import migrate_schema_0043

    path = tmp_path / "cli.db"
    initialize_database(
        path, through=RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    )
    assert migrate_schema_0043.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == (
        RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION
    )
    assert migrate_schema_0043.main(
        ["--db-path", str(path), "--confirm-0042-to-0043"],
    ) == 0
    assert database_schema_versions(path)[-1] == REVIEWER_SEGMENT_CHUNKING_SCHEMA_VERSION

    too_old = tmp_path / "cli-too-old.db"
    initialize_database(too_old, through="0041_reviewer_document_quality_gate")
    assert migrate_schema_0043.main(
        ["--db-path", str(too_old), "--confirm-0042-to-0043"],
    ) == 2
    assert database_schema_versions(too_old)[-1] == (
        "0041_reviewer_document_quality_gate"
    )


def test_a_single_call_review_can_never_appear_in_the_chunk_ledger(tmp_path):
    """``chunk_count >= 2`` is the durable form of "an unsplit review is one row"."""
    path = tmp_path / "shape.db"
    initialize_database(path)
    conn = sqlite3.connect(path)
    try:
        definition = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='content_review_chunk_executions'"
        ).fetchone()[0]
        assert "chunk_count INTEGER NOT NULL CHECK (chunk_count >= 2)" in definition
        assert "UNIQUE (content_id, attempt_no, chunk_no)" in definition
        assert (
            "CHECK (requests_document_review = "
            "(CASE WHEN chunk_no=1 THEN 1 ELSE 0 END))"
        ) in definition
    finally:
        conn.close()
