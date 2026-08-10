"""PRE-C5 repair: qualification lifecycle after independent REQUEST CHANGES.

Three blocking findings are covered here and nothing else.

MAJOR 1 — a controlled qualification consumed its approval, then called the
provider with no durable record of the attempt.  A timeout left a consumed
approval, zero runs and no state anyone could reconcile.

MAJOR 2 — once an approval had been consumed, a plain LOCAL_FIXTURE PASS could
give an owner-verified paid model real qualification authority, with zero
controlled runs behind it.

MAJOR 3 — the approved input ceiling was never compared, so usage of
ceiling + 1 still produced PASS.

Everything is offline: fake callers, temporary file-backed SQLite, no network,
no real SDK, no cost.
"""
from __future__ import annotations

from decimal import Decimal
import sqlite3
import threading

import pytest

from app.content.cost_estimate import ROLE_ENVELOPES
from app.model_routing import (
    CapabilityDeclaration,
    CapabilityVerificationState,
    LogicalModelRole,
    ModelFamily,
    QualificationReport,
    QualificationState,
)
from app.model_routing.qualification import (
    ControlledQualificationError,
    QualificationApproval,
    QualificationProbeResponse,
    QualificationProbeUsage,
)
from app.model_routing.role_bootstrap import owner_approved_role_policy
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from tests.controlled_provider_fixtures import seed_model
from tests.test_prec5_verified_catalogue_live_root import (
    APPROVED_AT,
    EXPIRES_AT,
    CountingQualificationCaller,
    _approval,
    _entry_for,
    _probe,
    _register,
)


WRITER = LogicalModelRole.ARTICLE_WRITER
ENVELOPE = ROLE_ENVELOPES[WRITER]


@pytest.fixture
def db_path(tmp_path):
    """A file-backed database, so a second connection sees the same rows."""
    path = tmp_path / "qualification-repair.db"
    initialize_database(path)
    return path


@pytest.fixture
def storage(db_path):
    value = SqliteStorage.open(db_path)
    try:
        yield value
    finally:
        value.close()


def _ready(storage, *, request_id="repair-1"):
    """Owner-verified catalogue plus a verified writer policy."""
    _register(storage)
    storage.upsert_model_role_policy(owner_approved_role_policy(WRITER))
    return _approval(
        storage, role=WRITER, family=ModelFamily.OPUS, request_id=request_id,
    )


def _run_row(storage, request_id):
    return storage.conn.execute(
        "SELECT * FROM model_qualification_runs WHERE request_id=?",
        (request_id,),
    ).fetchone()


def _registry(storage):
    return _entry_for(storage, ModelFamily.OPUS)


class Boom(RuntimeError):
    """Stands in for a timeout or any other ambiguous provider failure."""


# ---------------------------------------------------------------------------
# MAJOR 1 — durable lifecycle around the provider boundary
# ---------------------------------------------------------------------------

def test_major1_timeout_leaves_a_durable_execution_and_no_pass(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(
        lambda _a: (_ for _ in ()).throw(Boom("provider timed out"))
    )

    with pytest.raises(Boom):
        storage.execute_controlled_qualification(approval, caller=caller)

    assert caller.calls == 1
    row = _run_row(storage, approval.request_id)
    assert row is not None, "a timeout must still leave a durable execution"
    assert row["outcome"] == "NEEDS_VERIFICATION"
    assert row["failure_kind"] == "CALLER_RESULT_UNKNOWN"
    assert row["external_effect_started_at"] is not None
    assert row["settled_at"] is not None
    # The request identity and everything needed to audit it survived.
    assert row["approval_ref"] == approval.approval_ref
    assert row["model_registry_id"] == approval.model_registry_id
    assert row["logical_role"] == WRITER.value
    assert row["provider"] == "ANTHROPIC"
    assert row["technical_model_id"] == "claude-opus-5"
    assert row["pricing_ref"] == approval.pricing_ref
    # No usage came back, so no usage and no cost are asserted. Not zero.
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["cost_usd"] is None
    assert row["qualification_ref"] is None
    # The approval stays consumed and the registry stays unqualified.
    approval_row = storage.conn.execute(
        "SELECT consumed_at FROM model_qualification_approvals WHERE approval_ref=?",
        (approval.approval_ref,),
    ).fetchone()
    assert approval_row["consumed_at"] is not None
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"


def test_major1_replay_after_the_external_effect_marker_is_refused(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    first = CountingQualificationCaller(
        lambda _a: (_ for _ in ()).throw(Boom("timeout"))
    )
    with pytest.raises(Boom):
        storage.execute_controlled_qualification(approval, caller=first)

    second = CountingQualificationCaller(lambda a: _probe(a.technical_model_id))
    with pytest.raises(ControlledQualificationError) as excinfo:
        storage.execute_controlled_qualification(approval, caller=second)
    assert excinfo.value.code == "QUALIFICATION_RUN_ALREADY_EXISTS"
    assert second.calls == 0


def test_major1_reopen_sees_exactly_the_same_unknown_state(db_path):
    opened = SqliteStorage.open(db_path)
    try:
        approval = _ready(opened)
        opened.record_model_qualification_approval(approval)
        caller = CountingQualificationCaller(
            lambda _a: (_ for _ in ()).throw(Boom("timeout"))
        )
        with pytest.raises(Boom):
            opened.execute_controlled_qualification(approval, caller=caller)
        before = dict(_run_row(opened, approval.request_id))
    finally:
        opened.close()

    reopened = SqliteStorage.open(db_path)
    try:
        after = dict(_run_row(reopened, approval.request_id))
        assert after == before
        assert after["outcome"] == "NEEDS_VERIFICATION"
        replay = CountingQualificationCaller(
            lambda a: _probe(a.technical_model_id)
        )
        with pytest.raises(ControlledQualificationError):
            reopened.execute_controlled_qualification(approval, caller=replay)
        assert replay.calls == 0
        assert reopened.conn.execute(
            "SELECT count(*) FROM model_qualification_results"
        ).fetchone()[0] == 0
    finally:
        reopened.close()


def test_major1_crash_between_marker_and_result_stays_in_flight(db_path):
    """A process that dies mid-request leaves an explicit reconciliation item."""
    opened = SqliteStorage.open(db_path)
    try:
        approval = _ready(opened)
        opened.record_model_qualification_approval(approval)

        class Crash(BaseException):
            """Not an Exception: models the process going away."""

        caller = CountingQualificationCaller(
            lambda _a: (_ for _ in ()).throw(Crash())
        )
        with pytest.raises(BaseException):
            opened.execute_controlled_qualification(approval, caller=caller)
    finally:
        opened.close()

    reopened = SqliteStorage.open(db_path)
    try:
        row = _run_row(reopened, approval.request_id)
        assert row is not None
        assert row["external_effect_started_at"] is not None
        # Whatever state the settle attempt reached, no PASS and no replay.
        assert row["outcome"] in {"IN_FLIGHT", "NEEDS_VERIFICATION"}
        assert row["qualification_ref"] is None
        again = CountingQualificationCaller(
            lambda a: _probe(a.technical_model_id)
        )
        with pytest.raises(ControlledQualificationError):
            reopened.execute_controlled_qualification(approval, caller=again)
        assert again.calls == 0
    finally:
        reopened.close()


def test_major1_an_in_flight_run_is_reconciled_explicitly_never_retried(db_path):
    opened = SqliteStorage.open(db_path)
    try:
        approval = _ready(opened)
        opened.record_model_qualification_approval(approval)
        # Reserve exactly as the executor does, then stop before the caller.
        from app.model_routing.qualification import reservation_payload
        from app.content.foundation import canonical_json, sha256_text

        pricing = opened._model_pricing_from_row(
            opened.conn.execute(
                "SELECT * FROM model_pricing_profiles WHERE pricing_ref=?",
                (approval.pricing_ref,),
            ).fetchone()
        )
        payload = canonical_json(
            reservation_payload(approval, external_effect_started_at=APPROVED_AT)
        )
        opened.conn.execute("BEGIN IMMEDIATE")
        opened._consume_model_qualification_approval(
            approval, current_ts=APPROVED_AT,
        )
        opened.conn.execute(
            "INSERT INTO model_qualification_runs (request_id,approval_ref,"
            "model_registry_id,logical_role,provider,technical_model_id,"
            "pricing_ref,pricing_profile_fingerprint,outcome,result_json,"
            "result_fingerprint,external_effect_started_at,reserved_at,"
            "executed_at) VALUES (?,?,?,?,?,?,?,?,'IN_FLIGHT',?,?,?,?,?)",
            (
                approval.request_id, approval.approval_ref,
                approval.model_registry_id, WRITER.value, "ANTHROPIC",
                "claude-opus-5", approval.pricing_ref,
                pricing.contract_fingerprint(), payload, sha256_text(payload),
                APPROVED_AT, APPROVED_AT, APPROVED_AT,
            ),
        )
        opened.conn.commit()
    finally:
        opened.close()

    reopened = SqliteStorage.open(db_path)
    try:
        assert _run_row(reopened, approval.request_id)["outcome"] == "IN_FLIGHT"
        outcome = reopened.reconcile_in_flight_qualification(approval.request_id)
        assert outcome.outcome == "NEEDS_VERIFICATION"
        assert outcome.failure_kind == "RESTART_AFTER_EXTERNAL_EFFECT"
        assert outcome.cost_usd is None
        row = _run_row(reopened, approval.request_id)
        assert row["outcome"] == "NEEDS_VERIFICATION"
        assert row["cost_usd"] is None
        # A run settles exactly once.
        with pytest.raises(ControlledQualificationError) as excinfo:
            reopened.reconcile_in_flight_qualification(approval.request_id)
        assert excinfo.value.code == "QUALIFICATION_RUN_ALREADY_SETTLED"
    finally:
        reopened.close()


def test_major1_concurrent_executions_reach_at_most_one_caller(db_path):
    setup = SqliteStorage.open(db_path)
    try:
        approval = _ready(setup)
        setup.record_model_qualification_approval(approval)
    finally:
        setup.close()

    reached: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        local = SqliteStorage.open(db_path)
        try:
            barrier.wait(timeout=10)
            local.execute_controlled_qualification(
                approval,
                caller=lambda a: (
                    reached.append(a.request_id)
                    or _probe(a.technical_model_id)
                ),
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            local.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(reached) <= 1, "at most one execution may reach the provider"
    assert len(errors) >= 3
    verify = SqliteStorage.open(db_path)
    try:
        assert verify.conn.execute(
            "SELECT count(*) FROM model_qualification_runs"
        ).fetchone()[0] == 1
    finally:
        verify.close()


# ---------------------------------------------------------------------------
# MAJOR 2 — a consumed approval is not a result
# ---------------------------------------------------------------------------

def _fixture_report(storage, *, state=QualificationState.PASS, ref="hand-written"):
    return QualificationReport(
        qualification_ref=ref,
        model_registry_id=str(_registry(storage)["registry_id"]),
        state=state,
        suite_version="local-suite",
        fixture_set_ref="local-fixtures",
        result_payload={"outcome": state.value},
        evaluated_at=APPROVED_AT,
        source="LOCAL_FIXTURE",
    )


def test_major2_local_fixture_pass_after_consume_is_refused(storage):
    """The exact counter-example the reviewer demonstrated."""
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    storage.conn.execute("BEGIN IMMEDIATE")
    storage._consume_model_qualification_approval(
        approval, current_ts=APPROVED_AT,
    )
    storage.conn.commit()
    assert storage.conn.execute(
        "SELECT count(*) FROM model_qualification_runs"
    ).fetchone()[0] == 0

    with pytest.raises(sqlite3.IntegrityError, match="settled controlled qualification run"):
        storage.record_model_qualification(_fixture_report(storage))
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"


def test_major2_local_fixture_pass_after_a_timeout_is_refused(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    with pytest.raises(Boom):
        storage.execute_controlled_qualification(
            approval,
            caller=lambda _a: (_ for _ in ()).throw(Boom("timeout")),
        )
    with pytest.raises(sqlite3.IntegrityError):
        storage.record_model_qualification(_fixture_report(storage))
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"


def test_major2_controlled_live_pass_without_a_matching_run_is_refused(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    storage.conn.execute("BEGIN IMMEDIATE")
    storage._consume_model_qualification_approval(
        approval, current_ts=APPROVED_AT,
    )
    storage.conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        storage.record_model_qualification(
            QualificationReport(
                qualification_ref="invented-controlled-ref",
                model_registry_id=str(_registry(storage)["registry_id"]),
                state=QualificationState.PASS,
                suite_version="controlled_live_qualification_v1",
                fixture_set_ref=approval.approval_ref,
                result_payload={"outcome": "PASS"},
                evaluated_at=APPROVED_AT,
                source="CONTROLLED_LIVE",
            )
        )
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"


def test_major2_controlled_live_pass_naming_another_registry_run_is_refused(storage):
    """A real PASS run for Opus cannot qualify the Fable entry."""
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    outcome = storage.execute_controlled_qualification(
        approval, caller=lambda a: _probe(a.technical_model_id),
    )
    assert outcome.outcome == "PASS"
    fable = _entry_for(storage, ModelFamily.FABLE)

    # The public storage path refuses to reuse one run's reference for another
    # registry entry...
    from app.model_routing import RoutingError

    with pytest.raises(RoutingError, match="QUALIFICATION_REFERENCE_COLLISION"):
        storage.record_model_qualification(
            QualificationReport(
                qualification_ref=outcome.qualification_ref,
                model_registry_id=str(fable["registry_id"]),
                state=QualificationState.PASS,
                suite_version="controlled_live_qualification_v1",
                fixture_set_ref=approval.approval_ref,
                result_payload={"outcome": "PASS"},
                evaluated_at=APPROVED_AT,
                source="CONTROLLED_LIVE",
            )
        )

    # ...and so does SQL, for a raw insert that bypasses that guard entirely by
    # inventing a fresh reference for the Opus entry.
    with pytest.raises(sqlite3.IntegrityError, match="settled controlled qualification run"):
        storage.conn.execute(
            "INSERT INTO model_qualification_results (qualification_ref,"
            "model_registry_id,state,suite_version,fixture_set_ref,source,"
            "result_json,result_fingerprint,evaluated_at,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "borrowed-from-opus", str(fable["registry_id"]), "PASS",
                "controlled_live_qualification_v1", approval.approval_ref,
                "CONTROLLED_LIVE", "{}", "c" * 64, APPROVED_AT, APPROVED_AT,
            ),
        )
    storage.conn.rollback()
    assert _entry_for(
        storage, ModelFamily.FABLE,
    )["current_qualification_state"] == "UNQUALIFIED"


def test_major2_controlled_live_pass_from_a_needs_verification_run_is_refused(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    outcome = storage.execute_controlled_qualification(
        approval,
        caller=lambda a: QualificationProbeResponse(
            returned_model_id="claude-fable-5",  # mismatch -> NEEDS_VERIFICATION
            structured_response_ok=True,
            usage=QualificationProbeUsage(input_tokens=10, output_tokens=5),
        ),
    )
    assert outcome.outcome == "NEEDS_VERIFICATION"
    with pytest.raises(sqlite3.IntegrityError):
        storage.record_model_qualification(
            QualificationReport(
                qualification_ref=f"controlled-qual-{approval.request_id}",
                model_registry_id=str(_registry(storage)["registry_id"]),
                state=QualificationState.PASS,
                suite_version="controlled_live_qualification_v1",
                fixture_set_ref=approval.approval_ref,
                result_payload={"outcome": "PASS"},
                evaluated_at=APPROVED_AT,
                source="CONTROLLED_LIVE",
            )
        )
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"


def test_major2_verified_capability_also_requires_the_settled_pass_run(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    with pytest.raises(Boom):
        storage.execute_controlled_qualification(
            approval, caller=lambda _a: (_ for _ in ()).throw(Boom("timeout")),
        )
    with pytest.raises(sqlite3.IntegrityError, match="settled PASS run"):
        storage.record_model_capabilities(
            str(_registry(storage)["registry_id"]),
            CapabilityDeclaration(
                capability_ref="hand-written-caps",
                verification_state=CapabilityVerificationState.VERIFIED,
                structured_response=True,
                max_context_tokens=16_000,
                max_output_tokens=2_048,
                verified_at=APPROVED_AT,
            ),
        )


def test_major2_local_fixture_remains_legal_for_a_non_catalogue_model(storage):
    """The boundary, not a blanket ban: offline fixtures still work."""
    _register(storage)
    storage.upsert_model_role_policy(owner_approved_role_policy(WRITER))
    fake = seed_model(storage, version="99", family=ModelFamily.FABLE)
    row = storage.conn.execute(
        "SELECT current_qualification_state FROM model_registry WHERE registry_id=?",
        (fake.registry_id,),
    ).fetchone()
    assert row["current_qualification_state"] == "PASS"
    assert storage.conn.execute(
        "SELECT source FROM model_qualification_results WHERE qualification_ref=?",
        (fake.qualification_ref,),
    ).fetchone()["source"] == "LOCAL_FIXTURE"
    # ...and it carries no owner-verified catalogue evidence.
    assert storage.conn.execute(
        "SELECT count(*) FROM model_catalogue_evidence WHERE model_registry_id=?",
        (fake.registry_id,),
    ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# MAJOR 3 — the approved token envelope is actually enforced
# ---------------------------------------------------------------------------

def _probe_with(**usage):
    def factory(approval):
        return QualificationProbeResponse(
            returned_model_id=approval.technical_model_id,
            structured_response_ok=True,
            usage=QualificationProbeUsage(**usage),
        )
    return factory


@pytest.mark.parametrize("usage,expected,kind", [
    (
        {"input_tokens": ENVELOPE.qualification_input_tokens, "output_tokens": 1},
        "PASS", None,
    ),
    (
        {"input_tokens": ENVELOPE.qualification_input_tokens + 1, "output_tokens": 1},
        "NEEDS_VERIFICATION", "INPUT_CEILING_EXCEEDED",
    ),
    (
        {"input_tokens": 1, "output_tokens": ENVELOPE.max_output_tokens},
        "PASS", None,
    ),
    (
        {"input_tokens": 1, "output_tokens": ENVELOPE.max_output_tokens + 1},
        "NEEDS_VERIFICATION", "OUTPUT_CEILING_EXCEEDED",
    ),
    ({"input_tokens": 0, "output_tokens": 0}, "PASS", None),
])
def test_major3_token_ceiling_boundaries(storage, usage, expected, kind):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    outcome = storage.execute_controlled_qualification(
        approval, caller=_probe_with(**usage),
    )
    assert outcome.outcome == expected
    assert outcome.failure_kind == kind
    row = _run_row(storage, approval.request_id)
    assert row["outcome"] == expected
    # Whatever happened, the usage that came back is preserved and priced.
    assert row["input_tokens"] == usage["input_tokens"]
    assert row["output_tokens"] == usage["output_tokens"]
    assert row["cost_usd"] is not None
    assert outcome.cost_usd == Decimal(str(row["cost_usd"]))
    state = _registry(storage)["current_qualification_state"]
    assert state == ("PASS" if expected == "PASS" else "UNQUALIFIED")


def test_major3_ceiling_violation_keeps_usage_cost_and_blocks_capability(storage):
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    over = ENVELOPE.qualification_input_tokens + 1
    caller = CountingQualificationCaller(
        _probe_with(input_tokens=over, output_tokens=100)
    )
    outcome = storage.execute_controlled_qualification(approval, caller=caller)

    assert caller.calls == 1, "the request already happened; it is not repeated"
    assert outcome.outcome == "NEEDS_VERIFICATION"
    assert outcome.failure_kind == "INPUT_CEILING_EXCEEDED"
    # 13953 input at 5/MTok + 100 output at 25/MTok
    assert outcome.cost_usd == Decimal("0.072265")
    row = _run_row(storage, approval.request_id)
    assert row["input_tokens"] == over
    assert row["cost_usd"] == "0.072265"
    assert row["qualification_ref"] is None
    assert _registry(storage)["current_qualification_state"] == "UNQUALIFIED"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_capability_declarations "
        "WHERE model_registry_id=? AND verification_state='VERIFIED'",
        (str(_registry(storage)["registry_id"]),),
    ).fetchone()[0] == 0


@pytest.mark.parametrize("bad", [
    {"input_tokens": -1, "output_tokens": 0},
    {"input_tokens": 0, "output_tokens": -1},
    {"input_tokens": True, "output_tokens": 0},
    {"input_tokens": "8", "output_tokens": 0},
    {"input_tokens": 1.5, "output_tokens": 0},
])
def test_major3_invalid_token_counts_are_refused_by_the_contract(bad):
    with pytest.raises(ControlledQualificationError) as excinfo:
        QualificationProbeUsage(**bad)
    assert excinfo.value.code == "QUALIFICATION_USAGE_INVALID"


def test_major3_sql_refuses_a_settled_pass_outside_the_envelope(storage):
    """Even a direct UPDATE cannot settle a PASS above the approved ceiling."""
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    outcome = storage.execute_controlled_qualification(
        approval, caller=_probe_with(input_tokens=10, output_tokens=5),
    )
    assert outcome.outcome == "PASS"
    # Either floor may fire first; both refuse the same write.
    with pytest.raises(
        sqlite3.IntegrityError,
        match="settles exactly once|approved token envelope",
    ):
        storage.conn.execute(
            "UPDATE model_qualification_runs SET input_tokens=? WHERE request_id=?",
            (ENVELOPE.qualification_input_tokens + 1, approval.request_id),
        )
    storage.conn.rollback()


def test_major3_a_matching_controlled_pass_still_qualifies_and_activates(storage):
    """The repair must not break the legitimate path."""
    approval = _ready(storage)
    storage.record_model_qualification_approval(approval)
    outcome = storage.execute_controlled_qualification(
        approval,
        caller=_probe_with(
            input_tokens=ENVELOPE.qualification_input_tokens,
            output_tokens=ENVELOPE.max_output_tokens,
        ),
    )
    assert outcome.outcome == "PASS"
    row = _run_row(storage, approval.request_id)
    assert row["settled_at"] is not None
    assert row["qualification_ref"] == outcome.qualification_ref
    assert _registry(storage)["current_qualification_state"] == "PASS"
    assert storage.promote_best_model(
        WRITER, reason="controlled qualification pass",
    ).status.value == "PROMOTED"
    binding = storage.freeze_content_writer_model_binding(
        job_id="repair-job", content_type=__import__(
            "app.content.foundation", fromlist=["ContentType"],
        ).ContentType.ARTICLE,
    )
    assert binding.technical_model_id == "claude-opus-5"
