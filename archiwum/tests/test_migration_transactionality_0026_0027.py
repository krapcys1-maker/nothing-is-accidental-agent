"""Atomic schema-and-ledger regressions for migrations 0026 and 0027."""
from __future__ import annotations

import sqlite3

import pytest

from app.storage.db import (
    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0025_to_0026,
    migrate_0026_to_0027,
)


_0026_TRIGGER_NAMES = (
    "jobs_content_contract",
    "content_plans_contract",
    "content_c2_pending_approval_contract",
)


def _schema_sql(conn: sqlite3.Connection, names: tuple[str, ...]) -> dict[str, str]:
    placeholders = ",".join("?" for _ in names)
    return {
        str(row["name"]): str(row["sql"])
        for row in conn.execute(
            f"SELECT name,sql FROM sqlite_schema WHERE name IN ({placeholders})",
            names,
        )
    }


def _assert_clean_database(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def _raise_for(target: str):
    def failpoint(version: str) -> None:
        if version == target:
            raise RuntimeError(f"forced {target[:4]} failure")

    return failpoint


def test_0026_happy_path_commits_schema_and_ledger_together_and_reopens(tmp_path):
    path = tmp_path / "0026-happy.db"
    initialize_database(path, through=EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION)

    before = connect(path)
    try:
        old_triggers = _schema_sql(before, _0026_TRIGGER_NAMES)
    finally:
        before.close()

    result = migrate_0025_to_0026(path)
    assert result.applied_migrations == (CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,)

    reopened = connect(path)
    try:
        assert database_schema_versions(path)[-1] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION
        assert _schema_sql(reopened, _0026_TRIGGER_NAMES) != old_triggers
        assert reopened.execute(
            "SELECT count(*) FROM schema_migrations WHERE version=?",
            (CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,),
        ).fetchone()[0] == 1
        _assert_clean_database(reopened)
    finally:
        reopened.close()


def test_0026_failpoint_rolls_back_schema_and_ledger_then_retry_succeeds(tmp_path):
    path = tmp_path / "0026-failpoint.db"
    initialize_database(path, through=EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION)
    before = connect(path)
    try:
        old_triggers = _schema_sql(before, _0026_TRIGGER_NAMES)
    finally:
        before.close()

    conn = connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
                transaction_failpoint=_raise_for(
                    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
                ),
            )
        assert conn.in_transaction is False
    finally:
        conn.close()

    reopened = connect(path)
    try:
        assert database_schema_versions(path)[-1] == EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION
        assert _schema_sql(reopened, _0026_TRIGGER_NAMES) == old_triggers
        assert reopened.execute(
            "SELECT count(*) FROM schema_migrations WHERE version=?",
            (CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,),
        ).fetchone()[0] == 0
        _assert_clean_database(reopened)
    finally:
        reopened.close()

    retry = migrate_0025_to_0026(path)
    assert retry.applied_migrations == (CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,)
    final = connect(path)
    try:
        assert database_schema_versions(path)[-1] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION
        assert _schema_sql(final, _0026_TRIGGER_NAMES) != old_triggers
        _assert_clean_database(final)
    finally:
        final.close()


def test_0027_happy_path_commits_schema_policies_and_ledger_and_reopens(tmp_path):
    path = tmp_path / "0027-happy.db"
    initialize_database(path, through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION)

    result = migrate_0026_to_0027(path)
    assert result.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)

    reopened = connect(path)
    try:
        assert database_schema_versions(path)[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
        assert reopened.execute(
            "SELECT count(*) FROM sqlite_schema WHERE type='table' AND name='model_registry'"
        ).fetchone()[0] == 1
        assert reopened.execute("SELECT count(*) FROM model_role_policies").fetchone()[0] == 7
        assert reopened.execute(
            "SELECT count(*) FROM schema_migrations WHERE version=?",
            (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,),
        ).fetchone()[0] == 1
        _assert_clean_database(reopened)
    finally:
        reopened.close()


def test_0027_failpoint_rolls_back_schema_and_ledger_then_retry_succeeds(tmp_path):
    path = tmp_path / "0027-failpoint.db"
    initialize_database(path, through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION)

    conn = connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
                transaction_failpoint=_raise_for(MODEL_FAMILY_ROUTING_SCHEMA_VERSION),
            )
        assert conn.in_transaction is False
    finally:
        conn.close()

    reopened = connect(path)
    try:
        assert database_schema_versions(path)[-1] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION
        assert reopened.execute(
            "SELECT count(*) FROM sqlite_schema WHERE name IN "
            "('model_registry','model_role_policies','model_intent_bindings')"
        ).fetchone()[0] == 0
        assert reopened.execute(
            "SELECT count(*) FROM schema_migrations WHERE version=?",
            (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,),
        ).fetchone()[0] == 0
        _assert_clean_database(reopened)
    finally:
        reopened.close()

    retry = migrate_0026_to_0027(path)
    assert retry.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)
    final = connect(path)
    try:
        assert database_schema_versions(path)[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
        assert final.execute("SELECT count(*) FROM model_role_policies").fetchone()[0] == 7
        _assert_clean_database(final)
    finally:
        final.close()
