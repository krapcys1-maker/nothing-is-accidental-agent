"""C1 migration 0021 — only temporary file-backed SQLite databases."""
from __future__ import annotations

import sqlite3

import pytest

from app.storage.db import (
    CONTENT_FOUNDATION_SCHEMA_VERSION,
    CONTENT_PIPELINE_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    CONTENT_DECISION_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    TOPIC_GENERATION_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0020_to_0021,
)


def _at_0020(tmp_path, name: str = "upgrade.db"):
    path = tmp_path / name
    initialize_database(path, through=TOPIC_GENERATION_SCHEMA_VERSION)
    return path


def _objects(conn) -> dict[str, str]:
    return {
        row[0]: row[1] or ""
        for row in conn.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    }


def test_0021_remains_the_exact_content_foundation_floor():
    from app.storage.db import ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION

    assert RUNTIME_SCHEMA_VERSION == ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION
    assert CONTENT_DECISION_SCHEMA_VERSION == "0024_autonomous_content_decision"
    assert CONTENT_WRITER_SCHEMA_VERSION == "0023_provider_ready_writer"
    assert CONTENT_PIPELINE_SCHEMA_VERSION == "0022_offline_content_pipeline"
    assert CONTENT_FOUNDATION_SCHEMA_VERSION == "0021_durable_content_foundation"


def test_fresh_0001_to_0021_has_content_contract_and_clean_integrity(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path, through=CONTENT_FOUNDATION_SCHEMA_VERSION)
    assert applied[-1] == CONTENT_FOUNDATION_SCHEMA_VERSION
    assert len(applied) == 21

    conn = connect(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        objects = _objects(conn)
        assert {
            "content_frozen_inputs",
            "content_evidence_items",
            "content_runs",
            "content_article_briefs",
            "content_call_intents",
            "content_provider_attempts",
            "content_transition_commands",
            "evaluations",
        } <= set(objects)
        assert "'CONTENT'" in objects["jobs"]
        assert "provider_attempts_content_requires_extension" in objects
        assert "content_provider_attempts_contract" in objects
        assert "content_transition_commands_contract" in objects
        assert conn.execute(
            "SELECT count(*) FROM schema_migrations "
            "WHERE version='0021_durable_content_foundation'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_upgrade_0020_to_0021_preserves_old_rows_and_objects(tmp_path):
    path = _at_0020(tmp_path)
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO accounts (id,name,mode,autonomy_level,active,"
            "browser_profile_path,writing_profile_path) "
            "VALUES ('acct','A','DRAFT_ONLY','LEVEL_1',1,'','')"
        )
        conn.execute(
            "INSERT INTO topics (id,account_id,title,status,created_at) "
            "VALUES (1,'acct','Topic','SELECTED','2026-07-23 10:00:00')"
        )
        conn.execute(
            "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
            "topic_id,payload_json,schedule_reason,earliest_run_at,attempts,"
            "max_attempts,created_at,updated_at) VALUES "
            "('old-job','acct','RESEARCH','RESEARCH','DONE','old-key',1,"
            "'{\"dry_run\":true}','WITHIN_EDITORIAL_WINDOW',"
            "'2026-07-23 10:00:00',1,1,'2026-07-23 10:00:00',"
            "'2026-07-23 10:00:00')"
        )
        conn.execute(
            "INSERT INTO content_items (id,account_id,type,title,body,status,"
            "created_at) VALUES (7,'acct','ARTICLE','Legacy','','DRAFT',"
            "'2026-07-23 10:00:00')"
        )
        conn.commit()
        before_objects = _objects(conn)
        old_job = tuple(conn.execute(
            "SELECT id,account_id,kind,workflow,status,idempotency_key,topic_id,"
            "run_id,payload_json,attempts,max_attempts FROM jobs WHERE id='old-job'"
        ).fetchone())
    finally:
        conn.close()

    result = migrate_0020_to_0021(path)
    assert result.applied_migrations == (CONTENT_FOUNDATION_SCHEMA_VERSION,)
    assert result.idempotent is False

    conn = connect(path)
    try:
        after_objects = _objects(conn)
        assert set(before_objects) - set(after_objects) == set()
        assert tuple(conn.execute(
            "SELECT id,account_id,kind,workflow,status,idempotency_key,topic_id,"
            "run_id,payload_json,attempts,max_attempts FROM jobs WHERE id='old-job'"
        ).fetchone()) == old_job
        assert conn.execute(
            "SELECT execution_generation FROM jobs WHERE id='old-job'"
        ).fetchone()[0] == 0
        legacy = conn.execute(
            "SELECT id,title,status,job_id,input_sha256,updated_at "
            "FROM content_items WHERE id=7"
        ).fetchone()
        assert tuple(legacy[:5]) == (7, "Legacy", "DRAFT", None, None)
        assert legacy["updated_at"] == "2026-07-23 10:00:00"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_fresh_and_upgrade_schema_objects_are_identical(tmp_path):
    fresh = tmp_path / "fresh.db"
    initialize_database(fresh, through=CONTENT_FOUNDATION_SCHEMA_VERSION)
    upgraded = _at_0020(tmp_path, "upgraded.db")
    migrate_0020_to_0021(upgraded)
    a, b = connect(fresh), connect(upgraded)
    try:
        assert _objects(a) == _objects(b)
    finally:
        a.close()
        b.close()


def test_0021_rerun_is_idempotent(tmp_path):
    path = _at_0020(tmp_path)
    migrate_0020_to_0021(path)
    repeated = migrate_0020_to_0021(path)
    assert repeated.idempotent is True
    assert repeated.applied_migrations == ()
    conn = connect(path)
    try:
        assert tuple(apply_migrations(
            conn, through=CONTENT_FOUNDATION_SCHEMA_VERSION,
        )) == ()
    finally:
        conn.close()


def test_0021_failpoint_rolls_back_schema_and_ledger_together(tmp_path):
    path = _at_0020(tmp_path, "fault.db")
    conn = connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                transaction_failpoint=lambda version: (
                    (_ for _ in ()).throw(RuntimeError("forced 0021 failure"))
                    if version == CONTENT_FOUNDATION_SCHEMA_VERSION else None
                ),
            )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA legacy_alter_table").fetchone()[0] == 0
    finally:
        conn.close()

    assert database_schema_versions(path)[-1] == TOPIC_GENERATION_SCHEMA_VERSION
    conn = connect(path)
    try:
        objects = _objects(conn)
        assert "content_frozen_inputs" not in objects
        assert "CONTENT" not in objects["jobs"]
        assert conn.execute(
            "SELECT count(*) FROM schema_migrations "
            "WHERE version='0021_durable_content_foundation'"
        ).fetchone()[0] == 0
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_0021_mid_migration_sql_error_rolls_back_rename_and_content_rebuild(tmp_path):
    path = _at_0020(tmp_path, "sql-fault.db")
    conn = connect(path)
    try:
        conn.execute("CREATE TABLE jobs_0020_old (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(Exception):
        migrate_0020_to_0021(path)
    assert database_schema_versions(path)[-1] == TOPIC_GENERATION_SCHEMA_VERSION
    conn = connect(path)
    try:
        assert "CONTENT" not in _objects(conn)["jobs"]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_0021_raw_and_uri_file_connections_observe_same_schema(tmp_path):
    path = _at_0020(tmp_path, "uri.db")
    migrate_0020_to_0021(path)
    raw = sqlite3.connect(path)
    uri = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        assert raw.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()[0] == CONTENT_FOUNDATION_SCHEMA_VERSION
        assert uri.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()[0] == CONTENT_FOUNDATION_SCHEMA_VERSION
    finally:
        raw.close()
        uri.close()
