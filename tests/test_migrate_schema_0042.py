"""Forward-only checks for the CONTENT known-cost reconciliation schema."""
from __future__ import annotations

import sqlite3

import pytest

from app.storage.db import (
    CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION,
    REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0041_to_0042,
)

REPLACED = (
    "provider_attempts_reconcile_requires_consistent_lineage",
    "provider_attempts_terminal_requires_terminal_lifecycle",
    "provider_attempts_terminal_requires_consistent_cost_cache",
)
ADDED = "provider_attempts_content_reconcile_requires_usage_identity"


def _objects(conn, kind: str) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,),
        )
    }


def _trigger(conn, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,),
    ).fetchone()
    return None if row is None else row[0]


def test_0041_to_0042_adds_the_content_branch_and_preserves_all_data(tmp_path):
    path = tmp_path / "known-cost.db"
    initialize_database(path, through=REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION)
    before = sqlite3.connect(path)
    try:
        tables = _objects(before, "table")
        triggers = _objects(before, "trigger")
        counts = {
            table: before.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        old_sql = {name: _trigger(before, name) for name in REPLACED}
        assert _trigger(before, ADDED) is None
        for sql in old_sql.values():
            assert "j.kind='CONTENT'" not in sql
    finally:
        before.close()

    result = migrate_0041_to_0042(path)
    assert result.applied_migrations == (
        CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION,
    )
    assert database_schema_versions(path)[-1] == (
        CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION
    )

    after = sqlite3.connect(path)
    try:
        assert _objects(after, "table") == tables
        assert _objects(after, "trigger") == triggers | {ADDED}
        for table, count in counts.items():
            if table == "schema_migrations":
                continue  # gains exactly the 0042 ledger row
            assert after.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == count
        assert after.execute(
            "SELECT count(*) FROM schema_migrations"
        ).fetchone()[0] == counts["schema_migrations"] + 1
        for name in REPLACED:
            new_sql = _trigger(after, name)
            assert new_sql != old_sql[name]
            assert "j.kind='CONTENT'" in new_sql
            # The pre-existing branches must survive verbatim.
            assert "j.kind='RESEARCH'" in new_sql
            assert "j.kind='TOPIC_GENERATION'" in new_sql
        assert "content_writer_results" in _trigger(after, ADDED)
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()


def test_0042_is_idempotent_and_forward_only(tmp_path):
    path = tmp_path / "idempotent.db"
    initialize_database(path, through=CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION)
    result = migrate_0041_to_0042(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()

    too_old = tmp_path / "too-old.db"
    initialize_database(too_old, through="0040_content_role_reconciliation")
    with pytest.raises(Exception) as exc:
        migrate_0041_to_0042(too_old)
    assert "0041" in str(exc.value)
    assert database_schema_versions(too_old)[-1] == "0040_content_role_reconciliation"


def test_0042_failure_rolls_back_triggers_and_ledger_to_0041(tmp_path):
    path = tmp_path / "rollback.db"
    initialize_database(path, through=REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION)
    conn = connect(path)
    try:
        before = {name: _trigger(conn, name) for name in REPLACED}

        def fail(version):
            if version == CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION:
                raise RuntimeError("controlled rollback probe")

        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION,
                transaction_failpoint=fail,
            )
        assert conn.in_transaction is False
        assert database_schema_versions(path)[-1] == REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION
        for name, sql in before.items():
            assert _trigger(conn, name) == sql
        assert _trigger(conn, ADDED) is None
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_fresh_database_reaches_the_known_cost_runtime_floor(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert applied[-1] == CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION
    assert RUNTIME_SCHEMA_VERSION == CONTENT_KNOWN_COST_RECONCILIATION_SCHEMA_VERSION
    assert len(applied) == 42


def test_upgrade_path_equals_a_fresh_install(tmp_path):
    """An upgraded 0041 database is indistinguishable from a fresh 0042 one."""
    upgraded = tmp_path / "upgraded.db"
    initialize_database(upgraded, through=REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION)
    migrate_0041_to_0042(upgraded)
    fresh = tmp_path / "fresh.db"
    initialize_database(fresh)

    a, b = sqlite3.connect(upgraded), sqlite3.connect(fresh)
    try:
        for name in (*REPLACED, ADDED):
            assert _trigger(a, name) == _trigger(b, name), name
        assert _objects(a, "trigger") == _objects(b, "trigger")
    finally:
        a.close()
        b.close()
