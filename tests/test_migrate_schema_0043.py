"""Forward-only checks for the retryable frozen-input schema 0043.

0043 rebuilds ``content_frozen_inputs`` to drop the global UNIQUE on
``input_sha256`` and to carry a nullable liveness marker instead.  Every probe
here runs against a temporary SQLite file; the project database is never opened.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.content.foundation import ContentStatus
from app.storage.db import (
    RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    ExplicitMigrationError,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0042_to_0043,
)
from app.storage.repositories import SqliteStorage
from tests.conftest import make_account
from tests.test_content_foundation import _start, build_content_seed

ROOT = Path(__file__).resolve().parents[1]

_ORIGINAL_COLUMNS = (
    "content_id", "account_id", "research_card_id", "content_type",
    "input_schema_version", "output_schema_version", "prompt_version",
    "style_guide_version", "article_brief_placeholder_json",
    "article_brief_placeholder_sha256", "research_card_snapshot_json",
    "evidence_manifest_json", "evidence_manifest_sha256", "evidence_item_count",
    "input_snapshot_json", "input_sha256", "created_at",
)


def _objects(conn, kind: str) -> set[str]:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type=?", (kind,),
        )
    }


def _columns(conn, table: str) -> list[tuple]:
    return [
        (row[1], row[2], row[3], row[4], row[5])
        for row in conn.execute(f"PRAGMA table_info({table})")
    ]


def _at_0042(tmp_path, name="frozen-inputs.db") -> Path:
    path = tmp_path / name
    initialize_database(
        path, through=RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION,
    )
    return path


def _seed_terminal_and_live_content(path: Path):
    """Drive two complete CONTENT lifecycles on a database still at 0042.

    ``SqliteStorage.open`` deliberately refuses anything but the exact runtime
    schema, so the pre-migration state is built on a raw connection.  That is
    the only way to observe what the backfill actually does to real rows; a
    pre-0043 row simply has no liveness marker, which reads as live.
    """
    conn = connect(path)
    storage = SqliteStorage(conn)
    try:
        account = make_account(active=True)
        dead = build_content_seed(storage, account, suffix="dead-card")
        live = build_content_seed(storage, account, suffix="live-card")
        _, failed, _, failed_execution = _start(storage, dead, "dead")
        storage.transition_content_execution(
            failed_execution, ContentStatus.FAILED,
            reason_code="CONTENT_PIPELINE_ERROR",
        )
        _, approved, _, approved_execution = _start(storage, live, "live")
        storage.transition_content_execution(
            approved_execution, ContentStatus.PENDING_APPROVAL,
            final_result={"audits": ["FACT", "STYLE", "GROWTH"]}, score=0.9,
        )
        failed_row = storage.conn.execute(
            "SELECT status,updated_at FROM content_items WHERE id=?",
            (failed.content.id,),
        ).fetchone()
        assert failed_row["status"] == "FAILED"
        return {
            "failed_id": failed.content.id,
            "failed_updated_at": failed_row["updated_at"],
            "approved_id": approved.content.id,
        }
    finally:
        conn.close()


def test_0042_to_0043_rebuilds_frozen_inputs_and_preserves_every_row(tmp_path):
    path = _at_0042(tmp_path)
    before = sqlite3.connect(path)
    try:
        tables = _objects(before, "table")
        triggers = _objects(before, "trigger")
        indexes = _objects(before, "index")
        counts = {
            table: before.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        old_columns = _columns(before, "content_frozen_inputs")
        old_ddl = before.execute(
            "SELECT sql FROM sqlite_master WHERE name='content_frozen_inputs'"
        ).fetchone()[0]
    finally:
        before.close()
    assert "input_sha256 TEXT NOT NULL UNIQUE" in old_ddl

    result = migrate_0042_to_0043(path)
    assert result.applied_migrations == (RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION,)
    assert result.idempotent is False
    assert database_schema_versions(path)[-1] == RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION

    after = sqlite3.connect(path)
    try:
        assert _objects(after, "table") == tables
        assert _objects(after, "trigger") - triggers == {
            "content_frozen_inputs_supersede_only",
            "content_frozen_inputs_supersede_on_terminal",
            "content_frozen_inputs_revive_on_resume",
        }
        assert triggers - _objects(after, "trigger") == {
            "content_frozen_inputs_no_update",
        }
        assert len(_objects(after, "trigger")) == len(triggers) + 2
        # The dropped inline UNIQUE takes its autoindex with it and the partial
        # unique index takes its place.
        assert _objects(after, "index") - indexes == {
            "ux_content_frozen_inputs_live",
        }
        for table, count in counts.items():
            if table == "schema_migrations":
                continue  # gains exactly the 0043 ledger row
            assert after.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0] == count
        assert after.execute(
            "SELECT count(*) FROM schema_migrations"
        ).fetchone()[0] == counts["schema_migrations"] + 1

        new_ddl = after.execute(
            "SELECT sql FROM sqlite_master WHERE name='content_frozen_inputs'"
        ).fetchone()[0]
        assert "input_sha256 TEXT NOT NULL UNIQUE" not in new_ddl
        assert "input_sha256 TEXT NOT NULL CHECK" in new_ddl
        # Every original column keeps its order, type, NOT NULL, default and
        # primary-key position; superseded_at is appended and nullable.
        assert _columns(after, "content_frozen_inputs")[:-1] == old_columns
        assert [row[1] for row in after.execute(
            "PRAGMA table_info(content_frozen_inputs)"
        )] == [*_ORIGINAL_COLUMNS, "superseded_at"]
        assert after.execute(
            "SELECT sql FROM sqlite_master WHERE name='ux_content_frozen_inputs_live'"
        ).fetchone()[0].replace("\n", " ").split("ON")[1].strip().startswith(
            "content_frozen_inputs(input_sha256) WHERE superseded_at IS NULL"
        )
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()


def test_0043_backfill_supersedes_exactly_the_failed_attempts(tmp_path):
    path = _at_0042(tmp_path, "backfill.db")
    seeded = _seed_terminal_and_live_content(path)

    before = sqlite3.connect(path)
    before.row_factory = sqlite3.Row
    try:
        frozen_before = {
            row["content_id"]: dict(row)
            for row in before.execute("SELECT * FROM content_frozen_inputs")
        }
        evidence_before = before.execute(
            "SELECT count(*) FROM content_evidence_items"
        ).fetchone()[0]
    finally:
        before.close()
    assert len(frozen_before) == 2 and evidence_before > 0

    migrate_0042_to_0043(path)

    after = sqlite3.connect(path)
    after.row_factory = sqlite3.Row
    try:
        rows = {
            row["content_id"]: dict(row)
            for row in after.execute("SELECT * FROM content_frozen_inputs")
        }
        # Byte-for-byte preservation of every pre-existing column.
        for content_id, old in frozen_before.items():
            assert {
                key: rows[content_id][key] for key in old
            } == old
        assert rows[seeded["failed_id"]]["superseded_at"] == (
            seeded["failed_updated_at"]
        )
        assert rows[seeded["approved_id"]]["superseded_at"] is None
        assert after.execute(
            "SELECT count(*) FROM content_frozen_inputs WHERE superseded_at IS NOT NULL"
        ).fetchone()[0] == after.execute(
            "SELECT count(*) FROM content_items WHERE status='FAILED'"
        ).fetchone()[0]
        assert after.execute(
            "SELECT count(*) FROM content_evidence_items"
        ).fetchone()[0] == evidence_before
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()


def test_migrated_database_opens_through_the_runtime_gate(tmp_path):
    path = _at_0042(tmp_path, "runtime-gate.db")
    _seed_terminal_and_live_content(path)
    with pytest.raises(Exception):
        SqliteStorage.open(path)  # 0042 is below the runtime floor
    migrate_0042_to_0043(path)
    storage = SqliteStorage.open(path)
    try:
        assert storage.conn.execute(
            "EXPLAIN QUERY PLAN SELECT 1 FROM content_frozen_inputs "
            "WHERE input_sha256=? AND superseded_at IS NULL", ("0" * 64,),
        ).fetchall()[0]["detail"].endswith(
            "USING INDEX ux_content_frozen_inputs_live (input_sha256=?)"
        )
    finally:
        storage.close()


def test_0043_is_idempotent_and_forward_only(tmp_path):
    path = tmp_path / "idempotent.db"
    initialize_database(path, through=RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION)
    result = migrate_0042_to_0043(path)
    assert result.idempotent is True
    assert result.applied_migrations == ()

    too_old = tmp_path / "too-old.db"
    initialize_database(too_old, through="0041_reviewer_document_quality_gate")
    with pytest.raises(ExplicitMigrationError) as exc:
        migrate_0042_to_0043(too_old)
    assert "0042" in str(exc.value)
    assert database_schema_versions(too_old)[-1] == (
        "0041_reviewer_document_quality_gate"
    )


def test_0043_row_guard_fails_closed_and_rolls_back_to_0042(tmp_path):
    """The guard tables are the only thing standing between foreign_keys=OFF
    and a silently orphaned content_evidence_items row, so prove one fires."""
    path = _at_0042(tmp_path, "rollback.db")
    _seed_terminal_and_live_content(path)
    conn = connect(path)
    try:
        before_ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='content_frozen_inputs'"
        ).fetchone()[0]
        before_triggers = _objects(conn, "trigger")
        before_rows = conn.execute(
            "SELECT count(*) FROM content_frozen_inputs"
        ).fetchone()[0]

        # 0043 is self-ledgered: it owns BEGIN IMMEDIATE, so the runner's
        # failpoint hook cannot reach inside it.  Instead run the ladder from a
        # copy whose first row-count guard is off by one, which is exactly the
        # shape of a copy that lost a row.
        broken_dir = Path(tmp_path) / "broken-migrations"
        broken_dir.mkdir()
        source = ROOT / "app" / "storage" / "migrations"
        for sql_file in sorted(source.glob("*.sql")):
            text = sql_file.read_text(encoding="utf-8")
            if sql_file.stem == RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION:
                original = (
                    "SELECT (SELECT count(*) FROM content_frozen_inputs)\n"
                    "     - (SELECT count(*) FROM content_frozen_inputs_0043_new);"
                )
                assert original in text
                text = text.replace(original, (
                    "SELECT 1 + (SELECT count(*) FROM content_frozen_inputs)\n"
                    "     - (SELECT count(*) FROM content_frozen_inputs_0043_new);"
                ))
            (broken_dir / sql_file.name).write_text(text, encoding="utf-8")

        with pytest.raises(sqlite3.IntegrityError):
            apply_migrations(
                conn, broken_dir,
                through=RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION,
            )
        assert conn.in_transaction is False
        assert database_schema_versions(path)[-1] == (
            RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION
        )
        assert conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='content_frozen_inputs'"
        ).fetchone()[0] == before_ddl
        assert _objects(conn, "trigger") == before_triggers
        assert conn.execute(
            "SELECT count(*) FROM content_frozen_inputs"
        ).fetchone()[0] == before_rows
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()
    # The unmodified ladder still applies cleanly afterwards.
    assert migrate_0042_to_0043(path).applied_migrations == (
        RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION,
    )


def test_operator_cli_fails_closed_without_the_explicit_confirmation(tmp_path):
    path = _at_0042(tmp_path, "cli.db")
    refused = subprocess.run(
        [sys.executable, "scripts/migrate_schema_0043.py", "--db-path", str(path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert refused.returncode == 2
    assert "--confirm-0042-to-0043 is required" in refused.stderr
    assert database_schema_versions(path)[-1] == (
        RESEARCH_CONSERVATIVE_ADJUDICATION_SCHEMA_VERSION
    )

    applied = subprocess.run(
        [
            sys.executable, "scripts/migrate_schema_0043.py",
            "--db-path", str(path), "--confirm-0042-to-0043",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert applied.returncode == 0
    assert RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION in applied.stdout
    assert database_schema_versions(path)[-1] == RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION

    wrong_step = subprocess.run(
        [
            sys.executable, "scripts/migrate_schema_0043.py",
            "--db-path", str(tmp_path / "missing.db"), "--confirm-0042-to-0043",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert wrong_step.returncode == 2
    assert "failed closed" in wrong_step.stderr


def test_fresh_database_reaches_the_retryable_frozen_input_floor(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert applied[-1] == RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION
    assert RUNTIME_SCHEMA_VERSION == RETRYABLE_FROZEN_INPUTS_SCHEMA_VERSION
    assert len(applied) == 43
