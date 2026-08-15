"""Focused operator-path tests for the explicit 0033 -> 0034 migration."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

import pytest

from app.storage.db import (
    END_TO_END_CONNECTION_SCHEMA_VERSION,
    ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION,
    ROLE_EXECUTION_LIFECYCLE_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
)
import scripts.migrate_schema_0034 as migration_cli


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_schema_state(path: Path) -> tuple[tuple[str, str, str | None], ...]:
    connection = sqlite3.connect(path)
    try:
        return tuple(
            connection.execute(
                "SELECT type,name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        )
    finally:
        connection.close()


def test_cli_requires_explicit_database_path(capsys):
    with pytest.raises(SystemExit) as caught:
        migration_cli.main(["--confirm-0033-to-0034"])

    assert caught.value.code == 2
    assert "--db-path" in capsys.readouterr().err


def test_cli_refuses_missing_database_without_creating_it(tmp_path, capsys):
    path = tmp_path / "does-not-exist.db"

    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0033-to-0034",
    ]) == 2

    assert "SCHEMA_VERSION_UNAVAILABLE" in capsys.readouterr().err
    assert not path.exists()


def test_cli_requires_confirmation_without_mutating_0033(tmp_path, capsys):
    path = tmp_path / "confirmation-required.db"
    initialize_database(path, through=ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION)
    before_hash = _sha256(path)

    assert migration_cli.main(["--db-path", str(path)]) == 2

    assert "--confirm-0033-to-0034 is required" in capsys.readouterr().err
    assert _sha256(path) == before_hash
    assert database_schema_versions(path)[-1] == ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION


def test_cli_migrates_exact_0033_to_0034_and_preserves_invariants(tmp_path, capsys):
    path = tmp_path / "success.db"
    initialize_database(path, through=ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION)
    connection = sqlite3.connect(path)
    try:
        before_policy = connection.execute(
            "SELECT allowed_family FROM model_role_policies "
            "WHERE role='TOPIC_GENERATION'"
        ).fetchone()[0]
        before_policy_count = connection.execute(
            "SELECT COUNT(*) FROM model_role_policies"
        ).fetchone()[0]
    finally:
        connection.close()
    assert before_policy == "SONNET"

    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0033-to-0034",
    ]) == 0

    output = capsys.readouterr().out
    assert END_TO_END_CONNECTION_SCHEMA_VERSION in output
    assert "idempotent=false" in output
    versions = database_schema_versions(path)
    assert versions[-1] == END_TO_END_CONNECTION_SCHEMA_VERSION
    assert versions.count(END_TO_END_CONNECTION_SCHEMA_VERSION) == 1

    connection = sqlite3.connect(path)
    try:
        topic_policy = connection.execute(
            "SELECT allowed_family,policy_fingerprint,allowed_provider,"
            "allowed_technical_model_id,require_source_discovery "
            "FROM model_role_policies WHERE role='TOPIC_GENERATION'"
        ).fetchone()
        policy_count = connection.execute(
            "SELECT COUNT(*) FROM model_role_policies"
        ).fetchone()[0]
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        capability_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(model_capability_declarations)"
            )
        }
        candidate_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(research_source_candidates)"
            )
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()

    assert topic_policy == (
        "OPUS",
        "d81a5fe6a8c737632cce9606889b7c52d0a929e79940b0dc243dc9e1edc6332b",
        None,
        None,
        None,
    )
    assert policy_count == before_policy_count == 7
    assert {
        "source_discovery_approvals",
        "source_candidate_fetch_approvals",
    } <= tables
    assert "source_discovery" in capability_columns
    assert {
        "canonical_source_identity",
        "discovery_result_identity",
        "discovery_port",
        "discovery_job_id",
    } <= candidate_columns
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_cli_rejects_unexpected_0032_without_any_database_change(tmp_path, capsys):
    path = tmp_path / "unexpected-version.db"
    initialize_database(path, through=ROLE_EXECUTION_LIFECYCLE_SCHEMA_VERSION)
    before_hash = _sha256(path)
    before_schema = _read_schema_state(path)

    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0033-to-0034",
    ]) == 2

    error = capsys.readouterr().err
    assert "requires exact 0033_role_execution_global_ledger" in error
    assert "observed 0032_role_execution_lifecycle" in error
    assert _sha256(path) == before_hash
    assert _read_schema_state(path) == before_schema
    assert database_schema_versions(path)[-1] == ROLE_EXECUTION_LIFECYCLE_SCHEMA_VERSION


def test_cli_is_idempotent_when_database_is_already_at_0034(tmp_path, capsys):
    path = tmp_path / "already-0034.db"
    initialize_database(path, through=END_TO_END_CONNECTION_SCHEMA_VERSION)
    before_hash = _sha256(path)

    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0033-to-0034",
    ]) == 0

    output = capsys.readouterr().out
    assert END_TO_END_CONNECTION_SCHEMA_VERSION in output
    assert "applied=[]" in output
    assert "idempotent=true" in output
    assert _sha256(path) == before_hash


def test_controlled_sql_failure_rolls_back_entire_0034_step(tmp_path, capsys):
    path = tmp_path / "transaction-rollback.db"
    initialize_database(path, through=ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE source_discovery_approvals (sentinel TEXT)")
        connection.commit()
    finally:
        connection.close()
    before_schema = _read_schema_state(path)

    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0033-to-0034",
    ]) == 2

    assert "already exists" in capsys.readouterr().err
    assert database_schema_versions(path)[-1] == ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION
    assert _read_schema_state(path) == before_schema
    connection = sqlite3.connect(path)
    try:
        topic_family = connection.execute(
            "SELECT allowed_family FROM model_role_policies "
            "WHERE role='TOPIC_GENERATION'"
        ).fetchone()[0]
        capability_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(model_capability_declarations)"
            )
        }
        candidate_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(research_source_candidates)"
            )
        }
    finally:
        connection.close()
    assert topic_family == "SONNET"
    assert "source_discovery" not in capability_columns
    assert "canonical_source_identity" not in candidate_columns
