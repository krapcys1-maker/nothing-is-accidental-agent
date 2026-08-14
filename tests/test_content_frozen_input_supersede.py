"""Schema 0043: a terminal attempt releases its paid Research Card.

Before 0043 the frozen input of a dead attempt kept the card locked forever,
because ``content_frozen_inputs.input_sha256`` was globally UNIQUE and its
preimage contains no job, content or attempt identity.  These probes state the
invariant that was actually meant instead: at most one LIVE content item may
hold a given frozen input.

Every write here goes to a fresh temporary SQLite file created by the shared
fixtures.  No provider, planner, browser or publication path is constructed.
"""
from __future__ import annotations

import sqlite3

import pytest

from app.content.foundation import ContentStatus
from app.core.clock import FixedClock
from app.ports.storage import ContentFoundationError
from tests.test_content_foundation import (  # noqa: F401  (fixture import)
    _NOW,
    _request,
    _start,
    content_seed,
)


def _frozen_row(storage, content_id):
    return storage.conn.execute(
        "SELECT * FROM content_frozen_inputs WHERE content_id=?", (content_id,),
    ).fetchone()


def test_terminal_failure_supersedes_the_frozen_input_and_a_retry_succeeds(
    storage, content_seed,
):
    """The money test: one technical failure must not destroy a paid card."""
    _, prepared, _, execution = _start(storage, content_seed, "first")
    assert prepared.frozen_input.superseded_at is None
    storage.transition_content_execution(
        execution, ContentStatus.FAILED, reason_code="CONTENT_PIPELINE_ERROR",
    )
    failed = storage.get_frozen_content_input(
        content_seed["account_id"], prepared.content.id,
    )
    assert failed.superseded_at is not None
    assert _frozen_row(storage, prepared.content.id)["superseded_at"] == (
        storage.conn.execute(
            "SELECT created_at FROM content_transition_commands "
            "WHERE content_id=? AND target_content_status='FAILED'",
            (prepared.content.id,),
        ).fetchone()[0]
    )

    retry = storage.prepare_content_job(
        _request(content_seed, "retry"), clock=FixedClock(_NOW),
    )
    assert retry.job_created is True
    assert retry.content.id != prepared.content.id
    # The exact same model input is frozen again - nothing was faked to buy the
    # retry - and only the new row holds the live slot.
    assert retry.frozen_input.input_sha256 == prepared.frozen_input.input_sha256
    assert retry.frozen_input.superseded_at is None
    keys = [
        row[0] for row in storage.conn.execute(
            "SELECT intent_key FROM content_items ORDER BY id"
        )
    ]
    assert len(keys) == 2 and keys[0] != keys[1]


def test_a_second_live_attempt_on_one_frozen_input_is_still_refused(
    storage, content_seed,
):
    _, _, _, execution = _start(storage, content_seed, "first")
    storage.transition_content_execution(
        execution, ContentStatus.FAILED, reason_code="CONTENT_PIPELINE_ERROR",
    )
    storage.prepare_content_job(
        _request(content_seed, "retry"), clock=FixedClock(_NOW),
    )
    with pytest.raises(ContentFoundationError, match="CONTENT_DURABLE_CONFLICT"):
        storage.prepare_content_job(
            _request(content_seed, "third"), clock=FixedClock(_NOW),
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM content_items"
    ).fetchone()[0] == 2
    assert storage.conn.execute(
        "SELECT count(*) FROM content_frozen_inputs WHERE superseded_at IS NULL"
    ).fetchone()[0] == 1


def test_pending_approval_keeps_blocking_a_duplicate_preparation(
    storage, content_seed,
):
    _, prepared, _, execution = _start(storage, content_seed, "success")
    storage.transition_content_execution(
        execution, ContentStatus.PENDING_APPROVAL,
        final_result={"audits": ["FACT", "STYLE", "GROWTH"]}, score=0.9,
    )
    assert _frozen_row(storage, prepared.content.id)["superseded_at"] is None
    with pytest.raises(ContentFoundationError, match="CONTENT_DURABLE_CONFLICT"):
        storage.prepare_content_job(
            _request(content_seed, "duplicate"), clock=FixedClock(_NOW),
        )


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (ContentStatus.NEEDS_VERIFICATION, "AMBIGUOUS_EXECUTION"),
        (ContentStatus.SKIPPED, "NO_DEFENSIBLE_ANGLE"),
    ],
)
def test_ambiguous_terminal_states_are_deliberately_not_released(
    storage, content_seed, target, reason,
):
    """NEEDS_VERIFICATION and SKIPPED may already have been produced and paid
    for, so 0043 deliberately keeps blocking them: releasing that bucket is a
    money decision with its own owner-approval ledger, not a schema decision."""
    _, prepared, _, execution = _start(storage, content_seed, target.value.lower())
    storage.transition_content_execution(execution, target, reason_code=reason)
    assert _frozen_row(storage, prepared.content.id)["superseded_at"] is None
    with pytest.raises(ContentFoundationError, match="CONTENT_DURABLE_CONFLICT"):
        storage.prepare_content_job(
            _request(content_seed, "blocked"), clock=FixedClock(_NOW),
        )


def test_supersede_marker_is_the_only_writable_field_at_the_sql_floor(
    storage, content_seed,
):
    _, prepared, _, execution = _start(storage, content_seed, "floor")
    content_id = prepared.content.id
    live = dict(_frozen_row(storage, content_id))

    # A live row cannot be superseded by hand: there is no terminal command.
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE content_frozen_inputs SET superseded_at=? WHERE content_id=?",
            ("2026-07-23 13:00:00", content_id),
        )
    storage.conn.rollback()

    storage.transition_content_execution(
        execution, ContentStatus.FAILED, reason_code="CONTENT_PIPELINE_ERROR",
    )
    stamped = _frozen_row(storage, content_id)["superseded_at"]
    assert stamped is not None

    for column, value in (
        ("prompt_version", "tampered"),
        ("input_snapshot_json", '{"tampered":true}'),
        ("input_sha256", "0" * 64),
        ("created_at", "2026-07-23 09:00:00"),
        ("evidence_manifest_sha256", "1" * 64),
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            storage.conn.execute(
                f"UPDATE content_frozen_inputs SET {column}=? WHERE content_id=?",
                (value, content_id),
            )
        storage.conn.rollback()

    # Clearing the marker by hand needs an ACTIVE review resume session.
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE content_frozen_inputs SET superseded_at=NULL WHERE content_id=?",
            (content_id,),
        )
    storage.conn.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "DELETE FROM content_frozen_inputs WHERE content_id=?", (content_id,),
        )
    storage.conn.rollback()

    assert dict(_frozen_row(storage, content_id)) == {
        **live, "superseded_at": stamped,
    }


def test_a_frozen_input_can_never_be_born_superseded(storage, content_seed):
    _, prepared, _, _ = _start(storage, content_seed, "born")
    template = _frozen_row(storage, prepared.content.id)
    fresh = storage.conn.execute(
        "INSERT INTO content_items (account_id,type,status,research_card_id,"
        "created_at,updated_at) VALUES (?,?, 'DRAFT', ?,?,?)",
        (
            content_seed["account_id"], "ARTICLE", content_seed["card_id"],
            "2026-07-23 12:00:00", "2026-07-23 12:00:00",
        ),
    )
    new_id = int(fresh.lastrowid)
    columns = [key for key in template.keys() if key != "content_id"]
    assert columns[-1] == "superseded_at"
    values = [template[key] for key in columns[:-1]]
    placeholders = ",".join("?" for _ in range(len(columns) + 1))
    with pytest.raises(sqlite3.IntegrityError, match="born superseded"):
        storage.conn.execute(
            f"INSERT INTO content_frozen_inputs (content_id,{','.join(columns)}) "
            f"VALUES ({placeholders})",
            [new_id, *values, "2026-07-23 12:30:00"],
        )
    storage.conn.rollback()


def test_terminal_failed_must_supersede_exactly_one_frozen_input(
    storage, content_seed,
):
    """The arithmetic guard: a FAILED command that releases nothing aborts."""
    _, prepared, _, execution = _start(storage, content_seed, "arithmetic")
    storage.transition_content_execution(
        execution, ContentStatus.FAILED, reason_code="CONTENT_PIPELINE_ERROR",
    )
    command = storage.conn.execute(
        "SELECT * FROM content_transition_commands "
        "WHERE content_id=? AND target_content_status='FAILED'",
        (prepared.content.id,),
    ).fetchone()
    storage.conn.execute("BEGIN IMMEDIATE")
    # This state is unreachable through any legitimate path - which is exactly
    # why the guard exists.  The two sibling triggers on the same table would
    # refuse the hand-built duplicate first (and SQLite does not specify which
    # AFTER INSERT trigger runs first), so both are dropped inside the probe
    # transaction to leave the 0043 arithmetic alone.  The ROLLBACK restores
    # them, which the assertions below verify.
    storage.conn.execute("DROP TRIGGER content_transition_commands_contract")
    storage.conn.execute("DROP TRIGGER content_transition_commands_apply")
    with pytest.raises(
        sqlite3.IntegrityError, match="must supersede exactly one frozen input",
    ):
        storage.conn.execute(
            "INSERT INTO content_transition_commands (command_id,mode,job_id,"
            "run_id,content_id,account_id,workflow,source_content_status,"
            "target_content_status,target_run_status,target_job_status,"
            "lease_owner,execution_generation,lease_expires_at,reason_code,"
            "final_result_json,score,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "f" * 64, command["mode"], command["job_id"], command["run_id"],
                command["content_id"], command["account_id"],
                command["workflow"], "RUNNING", "FAILED", "FAILED", "FAILED",
                command["lease_owner"], int(command["execution_generation"]) + 1,
                command["lease_expires_at"], "SECOND_FAILURE", None, None,
                command["created_at"],
            ),
        )
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name IN "
        "('content_transition_commands_apply','content_transition_commands_contract')"
    ).fetchone()[0] == 2
    assert storage.conn.execute(
        "SELECT count(*) FROM content_transition_commands"
    ).fetchone()[0] == 1
