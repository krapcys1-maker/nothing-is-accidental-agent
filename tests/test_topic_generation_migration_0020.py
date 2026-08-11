"""Migracja 0020: rebuild `jobs`, zgoda L1 tematów i lineage generated_topics.

Wyłącznie NOWE bazy tymczasowe — produkcja nie jest migrowana ani otwierana.
Pokrycie: fresh 0001->0020, upgrade 0019->0020 bez utraty ani jednego obiektu,
równoważność fresh/upgrade, idempotentne ponowne uruchomienie, kontrolowany
fault z rollbackiem schematu i ledgeru, konto z wieloma legalnymi tematami
SELECTED, integrity/foreign_keys po ponownym otwarciu bazy.
"""
from __future__ import annotations

import pytest

from app.storage.db import (
    CONTENT_FOUNDATION_SCHEMA_VERSION,
    CONTENT_PIPELINE_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    CONTENT_DECISION_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    TOPIC_GENERATION_SCHEMA_VERSION,
    ExplicitMigrationError,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0019_to_0020,
)

_ACCOUNT = (
    "INSERT INTO accounts (id,name,mode,autonomy_level,active,"
    "browser_profile_path,writing_profile_path) "
    "VALUES ('acct','A','RESEARCH_ONLY','LEVEL_1',1,'','')"
)
_TOPIC = (
    "INSERT INTO topics (id,account_id,title,status,created_at) "
    "VALUES (?,'acct',?,'SELECTED','2026-07-21 10:00:00')"
)

# The six triggers and three indexes `jobs` owned before 0020; every one of them
# must exist again after the rebuild.
_JOBS_TRIGGERS = {
    "jobs_terminal_requires_provider_attempt_normalized",
    "jobs_settled_recovery_requires_event",
    "jobs_execution_recovery_terminal_is_immutable",
    "jobs_controlled_fetch_payload_frozen",
    "jobs_controlled_fetch_terminal_requires_resolved_attempt",
    "jobs_controlled_fetch_done_requires_succeeded_attempt",
}
_JOBS_INDEXES = {
    "ix_jobs_active_reservations",
    "ix_jobs_claimable",
    "ux_jobs_active_research_topic",
}


def _objects(conn) -> dict[str, str]:
    return {
        row[0]: (row[1] or "")
        for row in conn.execute("SELECT name,sql FROM sqlite_master")
    }


def _at_0019(tmp_path, name="ladder.db"):
    path = tmp_path / name
    initialize_database(path, through=EVIDENCE_RESEARCH_SCHEMA_VERSION)
    return path


def test_topic_generation_schema_is_0020_below_runtime_0024():
    assert RUNTIME_SCHEMA_VERSION != CONTENT_DECISION_SCHEMA_VERSION
    assert RUNTIME_SCHEMA_VERSION == "0033_role_execution_global_ledger"
    assert CONTENT_WRITER_SCHEMA_VERSION == "0023_provider_ready_writer"
    assert CONTENT_PIPELINE_SCHEMA_VERSION == "0022_offline_content_pipeline"
    assert TOPIC_GENERATION_SCHEMA_VERSION == "0020_topic_generation_lifecycle"


def test_fresh_initialization_reaches_0020_with_clean_integrity(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path, through=TOPIC_GENERATION_SCHEMA_VERSION)
    assert applied[-1] == TOPIC_GENERATION_SCHEMA_VERSION

    conn = connect(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"topic_generation_approvals", "generated_topics"} <= names
        kinds = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='jobs'"
        ).fetchone()[0]
        assert "TOPIC_GENERATION" in kinds
        assert "kind != 'TOPIC_GENERATION' OR topic_id IS NULL" in kinds
    finally:
        conn.close()


def test_upgrade_0019_to_0020_loses_no_object_and_changes_only_jobs(tmp_path):
    path = _at_0019(tmp_path)
    conn = connect(path)
    try:
        before = _objects(conn)
    finally:
        conn.close()

    result = migrate_0019_to_0020(path)
    assert result.applied_migrations == (TOPIC_GENERATION_SCHEMA_VERSION,)
    assert result.idempotent is False

    conn = connect(path)
    try:
        after = _objects(conn)
        assert set(before) - set(after) == set(), "0020 dropped a pre-existing object"
        changed = [n for n in before if n in after and before[n] != after[n]]
        assert changed == [
            "jobs",
            "provider_attempts_terminal_requires_terminal_lifecycle",
            "provider_attempts_terminal_requires_consistent_cost_cache",
            "provider_attempts_reconcile_requires_consistent_lineage",
            "settled_execution_recovery_requires_consistent_prestate",
            "settled_execution_recovery_terminalizes_lifecycle",
            "jobs_execution_recovery_terminal_is_immutable",
        ], changed
        assert {
            "provider_attempts_topic_generation_reconcile_requires_usage_identity",
            "reconciliation_events_topic_generation_requires_consistent_lineage",
        } <= set(after)
        assert _JOBS_TRIGGERS <= set(after)
        assert _JOBS_INDEXES <= set(after)
        assert "ux_jobs_active_topic_generation_account" in after
        assert "ux_generated_topics_one_selected_per_run" in after
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_fresh_and_upgraded_schemas_are_identical(tmp_path):
    fresh = tmp_path / "fresh.db"
    initialize_database(fresh, through=TOPIC_GENERATION_SCHEMA_VERSION)
    upgraded = _at_0019(tmp_path, "upgraded.db")
    migrate_0019_to_0020(upgraded)

    fresh_conn, up_conn = connect(fresh), connect(upgraded)
    try:
        fresh_objects, up_objects = _objects(fresh_conn), _objects(up_conn)
    finally:
        fresh_conn.close()
        up_conn.close()
    assert set(fresh_objects) == set(up_objects)
    assert [n for n in fresh_objects if fresh_objects[n] != up_objects[n]] == []


def test_rerunning_the_migrator_is_idempotent(tmp_path):
    path = _at_0019(tmp_path)
    migrate_0019_to_0020(path)
    repeat = migrate_0019_to_0020(path)
    assert repeat.idempotent is True
    assert repeat.applied_migrations == ()

    conn = connect(path)
    try:
        assert tuple(
            apply_migrations(conn, through=TOPIC_GENERATION_SCHEMA_VERSION)
        ) == ()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()
    assert database_schema_versions(path)[-1] == TOPIC_GENERATION_SCHEMA_VERSION


def test_migration_fault_rolls_back_schema_ledger_and_data(tmp_path):
    path = _at_0019(tmp_path, "fault.db")
    conn = connect(path)
    try:
        conn.execute(_ACCOUNT)
        conn.execute(_TOPIC, (1, "First selected"))
        conn.execute(_TOPIC, (2, "Second selected"))
        # Forced fault INSIDE the migration transaction: the rename target
        # already exists, so ALTER TABLE ... RENAME aborts mid-script.
        conn.execute("CREATE TABLE jobs_0019_old (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ExplicitMigrationError):
        migrate_0019_to_0020(path)

    assert database_schema_versions(path)[-1] == EVIDENCE_RESEARCH_SCHEMA_VERSION
    conn = connect(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        objects = _objects(conn)
        # Everything the script touches came back with the rollback.
        assert _JOBS_TRIGGERS <= set(objects)
        assert _JOBS_INDEXES <= set(objects)
        assert "topic_generation_approvals" not in objects
        assert "generated_topics" not in objects
        assert "TOPIC_GENERATION" not in objects["jobs"]
        assert conn.execute(
            "SELECT COUNT(*) FROM topics WHERE status='SELECTED'"
        ).fetchone()[0] == 2
    finally:
        conn.close()


def test_account_with_several_selected_topics_migrates_cleanly(tmp_path):
    """Production legitimately holds >1 SELECTED per account; 0020 must not care."""
    path = _at_0019(tmp_path, "multiselected.db")
    conn = connect(path)
    try:
        conn.execute(_ACCOUNT)
        for index in range(3):
            conn.execute(_TOPIC, (index + 1, f"Selected topic {index}"))
        conn.commit()
    finally:
        conn.close()

    migrate_0019_to_0020(path)

    conn = connect(path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM topics WHERE account_id='acct' AND status='SELECTED'"
        ).fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        # No global uniqueness was introduced over topics.status.
        indexes = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='topics'"
        ).fetchall()
        assert not any("SELECTED" in (row[0] or "") for row in indexes)
    finally:
        conn.close()


def test_existing_job_rows_survive_the_rebuild_unchanged(tmp_path):
    path = _at_0019(tmp_path, "jobrows.db")
    conn = connect(path)
    try:
        conn.execute(_ACCOUNT)
        conn.execute(_TOPIC, (1, "Existing topic"))
        conn.execute(
            "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
            "topic_id,payload_json,schedule_reason,earliest_run_at,attempts,"
            "max_attempts,created_at,updated_at) VALUES "
            "('legacy-job','acct','RESEARCH','RESEARCH','DONE','legacy-key',1,"
            "'{\"dry_run\": true}','WITHIN_EDITORIAL_WINDOW','2026-07-21 10:00:00',"
            "1,1,'2026-07-21 10:00:00','2026-07-21 10:00:00')"
        )
        conn.commit()
        before = conn.execute("SELECT * FROM jobs WHERE id='legacy-job'").fetchone()
        before_values = tuple(before)
        columns_before = [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
    finally:
        conn.close()

    migrate_0019_to_0020(path)

    conn = connect(path)
    try:
        after = conn.execute("SELECT * FROM jobs WHERE id='legacy-job'").fetchone()
        assert tuple(after) == before_values
        columns_after = [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
        assert columns_after == columns_before
    finally:
        conn.close()


def test_reopening_after_upgrade_keeps_integrity_and_no_sidecars(tmp_path):
    path = _at_0019(tmp_path, "reopen.db")
    migrate_0019_to_0020(path)
    for _ in range(2):
        conn = connect(path)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()
    assert not (path.parent / (path.name + "-wal")).exists()
    assert not (path.parent / (path.name + "-shm")).exists()
    assert not (path.parent / (path.name + "-journal")).exists()
