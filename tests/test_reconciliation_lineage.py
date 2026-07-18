"""W1A-VERIFY-02: full durable-lineage validation for the reconciliation resolver.

Independent review found a fail-open: the resolver terminalized an attempt whose
``runs.account_id`` belonged to a foreign account and whose ``runs.workflow`` was
ANALYTICS, because only the research_run account/topic were checked.  These offline
tests exercise every lineage divergence and every preview->confirm change, and each
negative test asserts a complete absence of mutation (attempt, job, run,
research_run, reservation, usage count/sum, event count, no attempt #2).

Offline only: temporary SQLite, fake callers, no network/SDK/cost.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.models import (
    Account, AccountMode, AutonomyLevel, ExecutionResolution, FinancialResolution, Job,
    JobExecutionContext, JobKind, JobStatus, ProviderAttemptStatus, ResearchCard, RunStatus,
    Topic, TopicStatus, WorkflowType,
)
from app.ports.storage import (
    ProviderAttemptReconciliationError, ReconciliationPreviewStaleError,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.storage.repositories import SqliteStorage

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
FOREIGN_ACCOUNT_ID = "foreign_account"


def _foreign_account() -> Account:
    return Account(
        id=FOREIGN_ACCOUNT_ID, display_name="Foreign", mode=AccountMode.FULL_PUBLICATION,
        autonomy_level=AutonomyLevel.LEVEL_1, active=True, niche=["other"], languages=["en"],
        browser_profile_path="./pf", writing_profile_path="./wf.md", allowed_actions=["research"],
    )


def _new_topic(storage, account, title: str) -> int:
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title=title, question="Why?", score=90, status=TopicStatus.SELECTED,
    ))
    return int(topic.id)


def _build_attempt(storage, account, suffix: str, *, topic_id: int | None = None):
    """Build a NEEDS_RECONCILIATION durable research attempt with a full lineage."""
    storage.ensure_account(account)
    if topic_id is None:
        topic_id = _new_topic(storage, account, f"Lineage {suffix}")
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="reconciliation-model", research_timeout_seconds=60,
        ),
        account_id=account.id, topic_id=topic_id, cap_usd=0.2, max_web_searches=1,
        question="Why?", niche=account.niche,
    )
    job = storage.enqueue_job(Job(
        id=f"lin-job-{suffix}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"lin-key-{suffix}", topic_id=topic_id,
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW, max_attempts=1,
        payload={
            "account_id": account.id, "topic_id": topic_id, "dry_run": False,
            "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
    ))
    lease = storage.claim_next_job(f"lin-owner-{suffix}", 120, now=NOW)
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(job.id, lease.lease_owner, f"lin-run-{suffix}", now=NOW)
    execution = JobExecutionContext(
        job_id=job.id, lease_owner=lease.lease_owner, run_id=initialized.run.id, clock=FixedClock(NOW),
    )
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.mark_provider_attempt_needs_reconciliation(execution, attempt.request_id, error_code="UNKNOWN")
    storage.mark_job_needs_verification(execution.job_id, execution.lease_owner, "UNKNOWN", now=NOW)
    return execution, attempt.request_id


def _snapshot(storage, execution, request_id) -> dict:
    """Every durable field a reconciliation could mutate, for no-mutation assertions."""
    job = storage.conn.execute(
        "SELECT status, reserved_cost_usd, budget_reserved_at FROM jobs WHERE id=?", (execution.job_id,),
    ).fetchone()
    return {
        "attempt_status": storage.conn.execute(
            "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,)).fetchone()[0],
        "attempt_count": storage.conn.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (execution.job_id,)).fetchone()[0],
        "job_status": job["status"],
        "job_reserved": float(job["reserved_cost_usd"]),
        "job_budget_reserved_at": job["budget_reserved_at"],
        "run_status": storage.conn.execute(
            "SELECT status FROM runs WHERE id=?", (execution.run_id,)).fetchone()[0],
        "research_status": storage.conn.execute(
            "SELECT status FROM research_runs WHERE id=?", (execution.run_id,)).fetchone()[0],
        "usage_count": storage.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE run_id=? AND dry_run=0 AND is_legacy_usage=0",
            (execution.run_id,)).fetchone()[0],
        "usage_sum": storage.conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
            "WHERE run_id=? AND dry_run=0 AND is_legacy_usage=0", (execution.run_id,)).fetchone()[0],
        "event_count": storage.conn.execute(
            "SELECT COUNT(*) FROM reconciliation_events WHERE request_id=?", (request_id,)).fetchone()[0],
    }


def _resolve_not_charged_execution_failed(storage, request_id, account_id, **kw):
    return storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account_id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="lineage negative test", **kw,
    )


def _tamper_payload(storage, job_id, mutate):
    payload = json.loads(storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (job_id,)).fetchone()[0])
    mutate(payload)
    storage.conn.execute("UPDATE jobs SET payload_json=? WHERE id=?", (json.dumps(payload), job_id))
    storage.conn.commit()


# ---------------------------------------------------------------------------
# Negative lineage matrix — each divergence must fail closed with zero mutation.
# ---------------------------------------------------------------------------

def _assert_fails_closed(storage, execution, request_id, account, call, *, exc=ProviderAttemptReconciliationError):
    before = _snapshot(storage, execution, request_id)
    with pytest.raises(exc):
        call()
    after = _snapshot(storage, execution, request_id)
    assert before == after, f"mutation leaked: {before} -> {after}"
    # Explicit: nothing terminalized, no attempt #2, no usage, no event added.
    assert after["attempt_status"] == "NEEDS_RECONCILIATION"
    assert after["job_status"] == JobStatus.NEEDS_VERIFICATION.value
    assert after["attempt_count"] == 1


def test_lineage_01_job_account_differs_from_run_account(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "01")
    storage.conn.execute("UPDATE runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_02_run_account_differs_from_research_run_account(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "02")
    storage.conn.execute("UPDATE research_runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_03_run_and_research_agree_but_differ_from_job_and_intent(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "03")
    storage.conn.execute("UPDATE runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.execute("UPDATE research_runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_04_run_workflow_analytics(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "04")
    storage.conn.execute("UPDATE runs SET workflow='ANALYTICS' WHERE id=?", (execution.run_id,))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_05_run_workflow_other_non_research(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "05")
    storage.conn.execute("UPDATE runs SET workflow='PUBLICATION' WHERE id=?", (execution.run_id,))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_06a_job_wrong_kind(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "06a")
    storage.conn.execute("UPDATE jobs SET kind='LOCAL' WHERE id=?", (execution.job_id,))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_06b_job_wrong_workflow(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "06b")
    storage.conn.execute("UPDATE jobs SET workflow='ANALYTICS' WHERE id=?", (execution.job_id,))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_07_job_run_id_points_at_bare_foreign_run(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "07")
    # A run row with no research_run (analytics run) owned by a foreign account.
    storage.conn.execute(
        "INSERT INTO runs (id, account_id, workflow, status, started_at) VALUES (?,?,?,?,?)",
        ("bare-foreign-run", FOREIGN_ACCOUNT_ID, "ANALYTICS", "RUNNING", "2026-07-15 12:00:00"))
    storage.conn.execute("UPDATE jobs SET run_id='bare-foreign-run' WHERE id=?", (execution.job_id,))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_08_job_run_id_points_at_foreign_full_run(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "08")
    other, _other_req = _build_attempt(storage, _foreign_account(), "08-foreign")
    storage.conn.execute("UPDATE jobs SET run_id=? WHERE id=?", (other.run_id, execution.job_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_09_research_run_topic_differs_from_intent(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "09")
    other_topic = _new_topic(storage, account, "Other topic 09")
    storage.conn.execute("UPDATE research_runs SET topic_id=? WHERE id=?", (other_topic, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_10_job_topic_differs_from_research_run_topic(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "10")
    other_topic = _new_topic(storage, account, "Other topic 10")
    storage.conn.execute("UPDATE jobs SET topic_id=? WHERE id=?", (other_topic, execution.job_id))
    storage.conn.commit()
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_11_tampered_intent_account_id(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "11")
    _tamper_payload(storage, execution.job_id,
                    lambda p: p["execution_intent"].__setitem__("account_id", FOREIGN_ACCOUNT_ID))
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_12_tampered_intent_topic_id(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "12")
    _tamper_payload(storage, execution.job_id,
                    lambda p: p["execution_intent"].__setitem__("topic_id", 999999))
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


def test_lineage_13_tampered_outer_payload_identity_vs_intent(settings, storage, account):
    # The durable intent carries no run_id; run identity is structural (jobs.run_id ==
    # runs.id == research_runs.id), covered by 07/08/16.  This exercises the payload<->intent
    # identity binding: a changed outer account_id must not be accepted.
    execution, request_id = _build_attempt(storage, account, "13")
    _tamper_payload(storage, execution.job_id,
                    lambda p: p.__setitem__("account_id", FOREIGN_ACCOUNT_ID))
    _assert_fails_closed(storage, execution, request_id, account,
                         lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id))


# ---- preview -> confirm stale-state protection --------------------------------

def _preview_token(storage, request_id, account_id):
    return storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account_id).version_token


def test_lineage_14_run_account_changes_between_preview_and_confirm(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "14")
    token = _preview_token(storage, request_id, account.id)
    storage.conn.execute("UPDATE runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(
        storage, execution, request_id, account,
        lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token),
        exc=ReconciliationPreviewStaleError)


def test_lineage_15_run_workflow_changes_between_preview_and_confirm(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "15")
    token = _preview_token(storage, request_id, account.id)
    storage.conn.execute("UPDATE runs SET workflow='ANALYTICS' WHERE id=?", (execution.run_id,))
    storage.conn.commit()
    _assert_fails_closed(
        storage, execution, request_id, account,
        lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token),
        exc=ReconciliationPreviewStaleError)


def test_lineage_16_job_run_id_changes_between_preview_and_confirm(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "16")
    other, _r = _build_attempt(storage, account, "16-other")
    token = _preview_token(storage, request_id, account.id)
    storage.conn.execute("UPDATE jobs SET run_id=? WHERE id=?", (other.run_id, execution.job_id))
    storage.conn.commit()
    _assert_fails_closed(
        storage, execution, request_id, account,
        lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token),
        exc=ReconciliationPreviewStaleError)


def test_lineage_17_research_account_changes_between_preview_and_confirm(settings, storage, account):
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "17")
    token = _preview_token(storage, request_id, account.id)
    storage.conn.execute("UPDATE research_runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    _assert_fails_closed(
        storage, execution, request_id, account,
        lambda: _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token),
        exc=ReconciliationPreviewStaleError)


# ---- SQLite defense-in-depth: the trigger blocks a raw terminal UPDATE ----------

def test_lineage_sqlite_trigger_blocks_raw_terminalization_on_foreign_run(settings, storage, account):
    """Even if the application layer were bypassed, the 0014 trigger fails closed."""
    import sqlite3 as _sqlite3
    storage.ensure_account(_foreign_account())
    execution, request_id = _build_attempt(storage, account, "trig")
    storage.conn.execute("UPDATE runs SET account_id=? WHERE id=?", (FOREIGN_ACCOUNT_ID, execution.run_id))
    storage.conn.commit()
    before = _snapshot(storage, execution, request_id)
    with pytest.raises(_sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at=?,reconciled_at=?,"
            "reconciled_by=?,reconciliation_note=?,reconciliation_resolution=? "
            "WHERE request_id=? AND status='NEEDS_RECONCILIATION'",
            ("2026-07-15 12:00:00", "2026-07-15 12:00:00", "op", "note",
             "NOT_CHARGED:EXECUTION_FAILED", request_id))
    storage.conn.rollback()
    assert _snapshot(storage, execution, request_id) == before


# ---------------------------------------------------------------------------
# Positive lineage — a consistent lineage still reconciles on every path.
# ---------------------------------------------------------------------------

def test_positive_consistent_lineage_not_charged(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "pos-nc")
    result = _resolve_not_charged_execution_failed(storage, request_id, account.id)
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert storage.conn.execute("SELECT status FROM runs WHERE id=?", (execution.run_id,)).fetchone()[0] == "FAILED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED


def test_positive_consistent_lineage_charged_known(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "pos-ck")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator", note="charged",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert result.usage_id is not None


def test_positive_consistent_lineage_charge_unknown_observation(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "pos-cu")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="operator", note="still investigating",
    )
    assert result.observed is True
    assert _snapshot(storage, execution, request_id)["attempt_status"] == "NEEDS_RECONCILIATION"


def test_positive_preview_confirm_with_valid_token(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "pos-token")
    token = _preview_token(storage, request_id, account.id)
    result = _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token)
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED


def test_charge_unknown_observation_makes_prior_token_stale(settings, storage, account):
    # An appended observation changes event history, so a token issued before it is stale
    # (documents that event history is part of the lineage token).
    execution, request_id = _build_attempt(storage, account, "pos-obs-token")
    token = _preview_token(storage, request_id, account.id)
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="operator", note="note",
    )
    with pytest.raises(ReconciliationPreviewStaleError):
        _resolve_not_charged_execution_failed(storage, request_id, account.id, expected_version_token=token)


def test_positive_concurrent_confirms_only_one_wins(settings, storage, account):
    execution, request_id = _build_attempt(storage, account, "pos-race")
    barrier = Barrier(2)

    def confirm(note: str) -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            local.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id,
                financial_resolution=FinancialResolution.NOT_CHARGED,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=None, reconciled_by="op", note=note,
            )
            return "ok"
        except ProviderAttemptReconciliationError:
            return "rejected"
        finally:
            local.close()

    # Different notes: exactly one terminalizes; the loser sees a terminal attempt
    # whose parameters differ from its own and is rejected (not a silent idempotent win).
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda note: confirm(note), ["race-a", "race-b"]))
    assert outcomes == ["ok", "rejected"]
    assert _snapshot(storage, execution, request_id)["attempt_status"] == "RECONCILED_RELEASED"
    assert _snapshot(storage, execution, request_id)["attempt_count"] == 1
