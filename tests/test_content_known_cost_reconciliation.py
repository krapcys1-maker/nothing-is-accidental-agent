"""Known-cost operator reconciliation for CONTENT provider attempts.

The gap this closes: a CONTENT writer attempt whose EXACT cost is already in
``model_usage`` could not be terminalized at all.  The WAVE 1 resolver required a
``jobs -> runs -> research_runs`` lineage, and the 0040 conservative ledger can
only charge the reservation - which understates a known larger cost.

Every test drives the REAL public storage API and the REAL applied triggers on a
fresh temporary database.  No provider, no network, no production database.
"""
from __future__ import annotations

from decimal import Decimal
import sqlite3

import pytest

from app.llm.anthropic_controlled_adapter import ControlledProviderRawResponse
from app.models import (
    ExecutionResolution,
    FinancialResolution,
    JobStatus,
    ModelUsage,
    ReconciliationFaultPoint,
)
from app.ports.storage import ProviderAttemptReconciliationError
from scripts.reconcile_content_known_cost import main as known_cost_main
from tests.test_b3_production_reviewer import (
    NOW,
    ReviewerTransport,
    WriterTransport,
    _run,
)

# 11029 input / 13000 output at the frozen 5/25 per-Mtok profile.  The writer
# reservation for the same envelope is 0.323840, so the settled charge overshoots
# it exactly the way the first real ARTICLE run did.
KNOWN_COST = Decimal("0.380145")
RESERVED = Decimal("0.323840")
DIFFERENCE = KNOWN_COST - RESERVED
ACCOUNT = "nothing_is_accidental"


class OverspendingWriter(WriterTransport):
    """A FINAL writer whose real usage exceeds its frozen reservation."""

    def __init__(self, *, output_tokens: int = 13000, **kwargs) -> None:
        super().__init__(**kwargs)
        self.output_tokens = output_tokens

    def __call__(self, client, request):
        resp = super().__call__(client, request)
        return ControlledProviderRawResponse(
            returned_model_id=resp.returned_model_id, text=resp.text,
            input_tokens=11029, output_tokens=self.output_tokens,
            cache_read_tokens=0, cache_write_tokens=0, web_search_requests=0,
            stop_reason=resp.stop_reason,
            provider_request_id=resp.provider_request_id,
        )


def _blocked_content_attempt(storage, settings, account, *, job, output_tokens=13000):
    """Produce the exact durable shape: NEEDS_RECONCILIATION with known usage."""
    try:
        _run(storage, settings, account, job=job,
             writer=OverspendingWriter(output_tokens=output_tokens),
             reviewer=ReviewerTransport())
    except BaseException:  # noqa: BLE001 - the pipeline stops itself
        pass
    request_id = f"{job}:content_draft:1"
    row = storage.conn.execute(
        "SELECT status,error_code,reserved_amount_usd,actual_cost_usd "
        "FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()
    assert row is not None, "fixture did not create the attempt"
    assert row["status"] == "NEEDS_RECONCILIATION"
    assert row["error_code"] == "PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION"
    assert row["actual_cost_usd"] is None
    return request_id


def _resolve(storage, request_id, *, cost=None, operator="owner:test",
             note="Exact provider usage was durably recorded.",
             financial=FinancialResolution.CHARGED_KNOWN,
             execution=ExecutionResolution.EXECUTION_FAILED, token=None):
    return storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=ACCOUNT,
        financial_resolution=financial, execution_resolution=execution,
        actual_cost_usd=format(KNOWN_COST, ".6f") if cost is None else cost,
        reconciled_by=operator, note=note, expected_version_token=token,
    )


# --- 1: preview -------------------------------------------------------------

def test_1_preview_shows_known_cost_reserve_and_difference(storage, settings, account):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-preview")
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=ACCOUNT)
    assert preview.attempt_status.value == "NEEDS_RECONCILIATION"
    assert preview.usage_count == 1
    assert Decimal(str(preview.reserved_amount_usd)).quantize(Decimal("0.000001")) == RESERVED
    usage_cost = Decimal(str(storage.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0])).quantize(Decimal("0.000001"))
    assert usage_cost == KNOWN_COST
    assert usage_cost - RESERVED == DIFFERENCE
    # Read-only: the preview never mutates.
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"


# --- 2, 3, 14: the happy path and what it must NOT do -----------------------

def test_2_3_14_known_cost_settles_without_second_cost_or_approval(
    storage, settings, account,
):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-happy")
    usage_before = storage.conn.execute(
        "SELECT id,estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()
    total_before = storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage").fetchone()[0]

    result = _resolve(storage, request_id)

    assert result.attempt.status.value == "RECONCILED_SETTLED"
    assert result.financial_resolution is FinancialResolution.CHARGED_KNOWN
    assert result.execution_resolution is ExecutionResolution.EXECUTION_FAILED
    assert result.usage_id == usage_before["id"], "must bind the pre-existing usage"

    row = storage.conn.execute(
        "SELECT status,actual_cost_usd,reconciliation_resolution,reconciled_by "
        "FROM provider_attempts WHERE request_id=?", (request_id,)).fetchone()
    assert row["status"] == "RECONCILED_SETTLED"
    assert row["reconciliation_resolution"] == "CHARGED_KNOWN:EXECUTION_FAILED"
    # A1: the canonical charge stays in model_usage, never on the attempt.
    assert row["actual_cost_usd"] is None

    # 3: no second usage row and no double cost anywhere.
    usage_rows = storage.conn.execute(
        "SELECT id,estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchall()
    assert len(usage_rows) == 1
    assert usage_rows[0]["id"] == usage_before["id"]
    assert usage_rows[0]["estimated_cost_usd"] == usage_before["estimated_cost_usd"]
    assert storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage"
    ).fetchone()[0] == total_before

    # exactly one FINAL_RESOLUTION audit event
    events = storage.conn.execute(
        "SELECT event_type,financial_resolution,execution_resolution "
        "FROM reconciliation_events WHERE request_id=?", (request_id,)).fetchall()
    assert [tuple(e) for e in events] == [
        ("FINAL_RESOLUTION", "CHARGED_KNOWN", "EXECUTION_FAILED")]

    # 14: the failed outcome is preserved, never upgraded.
    job = storage.conn.execute(
        "SELECT status FROM jobs WHERE id=?", ("ckc-happy",)).fetchone()[0]
    run = storage.conn.execute(
        "SELECT status FROM runs WHERE id=?",
        ("content-run:ckc-happy",)).fetchone()[0]
    # A CONTENT job and run are owned by the content transition command
    # contract, so the financial reconciliation asserts their already-failed,
    # unleased state rather than rewriting it.  Neither is a success state.
    assert (job, run) == ("NEEDS_VERIFICATION", "STOPPED")
    content_run = storage.conn.execute(
        "SELECT status FROM content_runs WHERE run_id=?",
        ("content-run:ckc-happy",)).fetchone()[0]
    assert content_run == "NEEDS_VERIFICATION", "content_run must stay untouched"
    statuses = {r[0] for r in storage.conn.execute("SELECT status FROM content_items")}
    assert not statuses & {"PENDING_APPROVAL", "APPROVED", "PUBLISHED", "DONE"}
    assert storage.conn.execute(
        "SELECT count(*) FROM content_transition_commands "
        "WHERE target_content_status='PENDING_APPROVAL'").fetchone()[0] == 0


# --- 4, 5, 6: canonical usage must be exactly one, real row -----------------

def test_4_missing_usage_is_refused(storage, settings, account):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-nousage")
    storage.conn.execute("PRAGMA foreign_keys=OFF")
    storage.conn.execute("DELETE FROM model_usage WHERE request_id=?", (request_id,))
    storage.conn.commit()
    storage.conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(ProviderAttemptReconciliationError, match="exactly one"):
        _resolve(storage, request_id)
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"


def test_5_a_second_canonical_usage_is_unrepresentable(storage, settings, account):
    """Defense in depth: the ledger itself refuses a duplicate canonical charge.

    The resolver still carries its own ``exactly one`` guard (test 4 drives it),
    but a second row for the same request cannot be created in the first place.
    """
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-twousage")
    with pytest.raises((sqlite3.IntegrityError, Exception)):
        storage.add_model_usage(ModelUsage(
            run_id="content-run:ckc-twousage", model="claude-opus-5",
            task="content_draft", estimated_cost_usd=0.01, dry_run=False,
            request_id=request_id, created_at=NOW,
        ))
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=? "
        "AND dry_run=0 AND is_legacy_usage=0", (request_id,)).fetchone()[0] == 1


@pytest.mark.parametrize("column", ["dry_run", "is_legacy_usage"])
def test_6_legacy_or_dry_run_usage_is_never_canonical(
    column, storage, settings, account,
):
    """A dry-run or legacy row is excluded, and cannot be retro-flagged either."""
    request_id = _blocked_content_attempt(
        storage, settings, account, job=f"ckc-{column}")
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            f"UPDATE model_usage SET {column}=1 WHERE request_id=?", (request_id,))
    storage.conn.rollback()
    # The canonical selector is exactly the one the resolver uses.
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=? "
        "AND dry_run=0 AND is_legacy_usage=0", (request_id,)).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"


# --- 7: identity mismatches -------------------------------------------------

def test_7_foreign_account_is_refused(storage, settings, account):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-account")
    with pytest.raises(ProviderAttemptReconciliationError, match="does not belong"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id="someone-else",
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=format(KNOWN_COST, ".6f"),
            reconciled_by="owner:test", note="Foreign account.",
        )


def test_7b_usage_cannot_be_repointed_at_a_foreign_run(storage, settings, account):
    """The request->job->run relation of a canonical row is immutable."""
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-runmix")
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE model_usage SET run_id='content-run:not-this-one' "
            "WHERE request_id=?", (request_id,))
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT run_id FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0] == "content-run:ckc-runmix"


def test_7c_cost_that_disagrees_with_the_usage_row_is_refused(
    storage, settings, account,
):
    """The charge comes from model_usage; a different number is never accepted."""
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-costmix")
    with pytest.raises(ProviderAttemptReconciliationError, match="cost"):
        _resolve(storage, request_id, cost="0.111111")
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"


# --- 9, 11, 12: state machine and conflicting decisions ---------------------

def test_9_only_needs_reconciliation_may_be_resolved(storage, settings, account):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-state")
    _resolve(storage, request_id)
    # Now terminal: a *different* decision must be refused (11).
    with pytest.raises(ProviderAttemptReconciliationError, match="different parameters"):
        _resolve(storage, request_id, operator="someone-else")
    with pytest.raises(ProviderAttemptReconciliationError, match="different parameters"):
        _resolve(storage, request_id, note="A contradictory note.")


def test_10_11_identical_repeat_is_an_exact_idempotent_no_op(
    storage, settings, account,
):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-idem")
    first = _resolve(storage, request_id)
    events_before = storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (request_id,)).fetchone()[0]
    usage_before = storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0]

    second = _resolve(storage, request_id)
    assert second.idempotent is True
    assert second.attempt.status.value == "RECONCILED_SETTLED"
    assert second.usage_id == first.usage_id
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (request_id,)).fetchone()[0] == events_before
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0] == usage_before


def test_11b_not_charged_and_result_already_finalized_are_refused(
    storage, settings, account,
):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-wrongres")
    with pytest.raises(
        ProviderAttemptReconciliationError,
        match="Only CHARGED_KNOWN accepts actual_cost_usd",
    ):
        _resolve(storage, request_id, financial=FinancialResolution.NOT_CHARGED)
    with pytest.raises(ProviderAttemptReconciliationError, match="CHARGED_KNOWN only"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=ACCOUNT,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="owner:test",
            note="NOT_CHARGED contradicts the durable usage.",
        )
    with pytest.raises(ProviderAttemptReconciliationError, match="EXECUTION_FAILED only"):
        _resolve(storage, request_id,
                 execution=ExecutionResolution.RESULT_ALREADY_FINALIZED)
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"


@pytest.mark.parametrize("output_tokens", [13000, 20000])
def test_12_known_cost_greater_than_reserve_settles_at_the_ledger_amount(
    output_tokens, storage, settings, account,
):
    """Any known cost above the reservation settles at the ledger amount."""
    job = f"ckc-amount-{output_tokens}"
    request_id = _blocked_content_attempt(
        storage, settings, account, job=job, output_tokens=output_tokens)
    ledger = Decimal(str(storage.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0])).quantize(Decimal("0.000001"))
    reserved = Decimal(str(storage.conn.execute(
        "SELECT reserved_amount_usd FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0])).quantize(Decimal("0.000001"))
    assert ledger > reserved
    result = _resolve(storage, request_id, cost=format(ledger, ".6f"))
    assert result.attempt.status.value == "RECONCILED_SETTLED"
    assert Decimal(str(storage.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()[0])).quantize(Decimal("0.000001")) == ledger


def test_12b_a_settled_attempt_within_reserve_is_not_reconcilable(
    storage, settings, account,
):
    """Cost <= reserve settles normally and never enters this path at all."""
    try:
        _run(storage, settings, account, job="ckc-within",
             writer=OverspendingWriter(output_tokens=2048),
             reviewer=ReviewerTransport())
    except BaseException:  # noqa: BLE001
        pass
    row = storage.conn.execute(
        "SELECT status,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        ("ckc-within:content_draft:1",)).fetchone()
    assert row["status"] == "SETTLED"
    assert row["actual_cost_usd"] is not None
    with pytest.raises(ProviderAttemptReconciliationError):
        _resolve(storage, "ckc-within:content_draft:1",
                 cost=format(Decimal(str(row["actual_cost_usd"])), ".6f"))


# --- 13: atomicity ----------------------------------------------------------

@pytest.mark.parametrize("fault", list(ReconciliationFaultPoint))
def test_13_every_fault_point_rolls_the_whole_decision_back(
    fault, storage, settings, account, monkeypatch,
):
    request_id = _blocked_content_attempt(
        storage, settings, account, job=f"ckc-fault-{fault.value}")
    usage_before = storage.conn.execute(
        "SELECT id,estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()

    def interrupt(point):
        if point is fault:
            raise RuntimeError(f"forced reconciliation fault: {point.value}")

    monkeypatch.setattr(storage, "_reconciliation_fault_point", interrupt)
    with pytest.raises(RuntimeError, match="forced reconciliation fault"):
        _resolve(storage, request_id)

    attempt = storage.conn.execute(
        "SELECT status,reconciled_at,reconciliation_resolution "
        "FROM provider_attempts WHERE request_id=?", (request_id,)).fetchone()
    assert tuple(attempt) == ("NEEDS_RECONCILIATION", None, None)
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (request_id,)).fetchone()[0] == 0
    usage_after = storage.conn.execute(
        "SELECT id,estimated_cost_usd FROM model_usage WHERE request_id=?",
        (request_id,)).fetchone()
    assert tuple(usage_after) == tuple(usage_before)
    job_id = f"ckc-fault-{fault.value}"
    assert storage.get_job(job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.conn.execute(
        "SELECT status FROM runs WHERE id=?",
        (f"content-run:{job_id}",)).fetchone()[0] == "STOPPED"


# --- 8, 15: no regression for the other supported paths ---------------------

def test_8_15_research_and_conservative_paths_are_untouched(storage, account):
    """The research resolver still owns its own lineage rules."""
    from tests.test_provider_attempt_reconciliation import _needs_reconciliation

    execution, request_id = _needs_reconciliation(storage, account, "ckc-research")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator-research",
        note="Unchanged research semantics.",
    )
    assert result.attempt.status.value == "RECONCILED_SETTLED"
    assert storage.get_research_run(execution.run_id).status.value == "FAILED"


# --- operator entrypoint: preview, then explicit confirmation ---------------

def test_cli_previews_without_mutating_then_confirms_once(
    storage, settings, account, capsys,
):
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-cli")
    storage.conn.commit()
    args = [
        "--db-path", str(settings.db_path), "--request-id", request_id,
        "--account-id", ACCOUNT, "--reconciled-by", "owner:test",
        "--note", "Exact provider usage was durably recorded.",
        "--financial-resolution", "CHARGED_KNOWN",
    ]

    assert known_cost_main(args) == 0
    out = capsys.readouterr().out
    assert "CONTENT KNOWN-COST RECONCILIATION PLAN" in out
    assert f"known_cost_usd={KNOWN_COST:.6f}" in out
    assert f"reserved_amount_usd={RESERVED:.6f}" in out
    assert f"difference_usd={DIFFERENCE:+.6f}" in out
    assert "PREVIEW ONLY" in out
    assert "provider_call=false" in out
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (request_id,)).fetchone()[0] == "NEEDS_RECONCILIATION"

    assert known_cost_main(args + ["--confirm-charged-known"]) == 0
    out = capsys.readouterr().out
    assert "attempt_status=RECONCILED_SETTLED" in out
    assert f"charged_usd={KNOWN_COST:.6f}" in out
    fresh = sqlite3.connect(settings.db_path)
    try:
        assert fresh.execute(
            "SELECT status FROM provider_attempts WHERE request_id=?",
            (request_id,)).fetchone()[0] == "RECONCILED_SETTLED"
        assert fresh.execute(
            "SELECT count(*) FROM model_usage WHERE request_id=?",
            (request_id,)).fetchone()[0] == 1
    finally:
        fresh.close()


def test_cli_requires_an_explicit_resolution_choice(storage, settings, account):
    """No default decision: omitting the resolution is a parser failure."""
    request_id = _blocked_content_attempt(storage, settings, account, job="ckc-nodefault")
    with pytest.raises(SystemExit):
        known_cost_main([
            "--db-path", str(settings.db_path), "--request-id", request_id,
            "--account-id", ACCOUNT, "--reconciled-by", "owner:test",
            "--note", "No resolution supplied.",
        ])
