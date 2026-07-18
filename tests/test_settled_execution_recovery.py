"""Offline regression tests for PR1-MAJ-001 SETTLED execution recovery."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.models import (
    ExecutionResolution,
    FinancialResolution,
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    ProviderAttemptStatus,
    ResearchCard,
    ResearchRunStatus,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import ProviderAttemptReconciliationError
from app.research.durable_intent import DurableResearchExecutionIntent
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
EXPIRED = NOW + timedelta(seconds=121)
ACTUAL_COST = "0.010000"


def _settled_crash(
    storage, account, suffix: str, *, with_card: bool = False, settled: bool = True,
):
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=f"Settled recovery {suffix}",
        question="Why?",
        score=90,
        status=TopicStatus.SELECTED,
    ))
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="settled-recovery-model",
            research_timeout_seconds=60,
        ),
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd=0.2,
        max_web_searches=1,
        question="Why?",
        niche=account.niche,
    )
    job = storage.enqueue_job(Job(
        id=f"settled-recovery-job-{suffix}",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"settled-recovery-key-{suffix}",
        topic_id=int(topic.id),
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
        max_attempts=1,
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
    ))
    lease = storage.claim_next_job(f"settled-recovery-worker-{suffix}", 120, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(
        job.id, lease.lease_owner, f"settled-recovery-run-{suffix}", now=NOW,
    )
    execution = JobExecutionContext(
        job_id=job.id,
        lease_owner=lease.lease_owner,
        run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    usage = None
    if settled:
        usage = storage.add_job_model_usage(execution, ModelUsage(
            run_id=execution.run_id,
            provider=intent.provider,
            model=intent.model,
            task="research",
            estimated_cost_usd=float(ACTUAL_COST),
            dry_run=False,
            request_id=attempt.request_id,
        ))
    card = None
    if with_card:
        card = storage.add_research_card(ResearchCard(
            topic_id=int(topic.id),
            question="Why?",
            working_thesis="The durable result exists before lifecycle finalization.",
        ))
        storage.conn.execute(
            "UPDATE research_runs SET research_card_id=? WHERE id=?",
            (card.id, execution.run_id),
        )
        storage.conn.commit()
    return {
        "job": job,
        "topic": topic,
        "execution": execution,
        "request_id": attempt.request_id,
        "usage_id": None if usage is None else usage.id,
        "card": card,
    }


def _state(storage, crash):
    request_id = crash["request_id"]
    run_id = crash["execution"].run_id
    return {
        "job": storage.get_job(crash["job"].id),
        "run": storage.get_run(run_id),
        "research": storage.get_research_run(run_id),
        "attempt": storage._provider_attempt_from_row(storage.conn.execute(
            "SELECT * FROM provider_attempts WHERE request_id=?", (request_id,),
        ).fetchone()),
        "usage_count": storage.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
        ).fetchone()[0],
        "event_count": storage.conn.execute(
            "SELECT COUNT(*) FROM reconciliation_events "
            "WHERE request_id=? AND event_type='EXECUTION_RECOVERY'", (request_id,),
        ).fetchone()[0],
    }


def test_maintenance_closes_settled_crash_without_card_as_failure(storage, account):
    crash = _settled_crash(storage, account, "maintenance-failure")

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)

    assert result.needs_verification_count == 1
    assert result.settled_execution_recovery_count == 1
    assert result.settled_execution_blocked_count == 0
    assert state["job"].status is JobStatus.FAILED
    assert state["run"].status is RunStatus.FAILED
    assert state["research"].status is ResearchRunStatus.FAILED
    assert state["attempt"].status is ProviderAttemptStatus.SETTLED
    assert state["attempt"].actual_cost_usd == pytest.approx(float(ACTUAL_COST))
    assert state["usage_count"] == 1
    assert state["event_count"] == 1


def test_maintenance_closes_settled_crash_with_card_as_success(storage, account):
    crash = _settled_crash(storage, account, "maintenance-success", with_card=True)

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)

    assert result.settled_execution_recovery_count == 1
    assert state["job"].status is JobStatus.DONE
    assert state["run"].status is RunStatus.SUCCESS
    assert state["research"].status is ResearchRunStatus.COMPLETE
    assert state["research"].research_card_id == crash["card"].id
    assert storage.conn.execute(
        "SELECT status FROM topics WHERE id=?", (crash["topic"].id,),
    ).fetchone()[0] == TopicStatus.USED.value
    assert state["attempt"].status is ProviderAttemptStatus.SETTLED
    assert state["usage_count"] == 1
    assert state["event_count"] == 1


@pytest.mark.parametrize(
    ("with_card", "resolution", "job_status"),
    [
        (False, ExecutionResolution.EXECUTION_FAILED, JobStatus.FAILED),
        (True, ExecutionResolution.RESULT_ALREADY_FINALIZED, JobStatus.DONE),
    ],
)
def test_public_resolver_handles_expired_settled_attempt_idempotently(
    storage, account, with_card, resolution, job_status,
):
    crash = _settled_crash(
        storage, account, f"resolver-{with_card}", with_card=with_card,
    )
    kwargs = dict(
        request_id=crash["request_id"],
        account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=resolution,
        actual_cost_usd=ACTUAL_COST,
        reconciled_by="owner",
        note="Resolve the known-cost execution crash.",
        now=EXPIRED,
    )

    first = storage.resolve_provider_attempt_reconciliation(**kwargs)
    second = storage.resolve_provider_attempt_reconciliation(**kwargs)
    state = _state(storage, crash)

    assert first.idempotent is False
    assert second.idempotent is True
    assert state["job"].status is job_status
    assert state["attempt"].status is ProviderAttemptStatus.SETTLED
    assert state["usage_count"] == 1
    assert state["event_count"] == 1


def test_live_fence_cannot_be_resolved(storage, account):
    crash = _settled_crash(storage, account, "live-fence")
    with pytest.raises(ProviderAttemptReconciliationError, match="live execution fence"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=crash["request_id"],
            account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=ACTUAL_COST,
            reconciled_by="owner",
            note="Must not cross a live fence.",
            now=NOW,
        )
    assert _state(storage, crash)["job"].status is JobStatus.RUNNING


def test_maintenance_blocks_tampered_cache_fail_closed(storage, account):
    crash = _settled_crash(storage, account, "cache-drift")
    storage.conn.execute(
        "UPDATE runs SET cost_usd=cost_usd+1 WHERE id=?", (crash["execution"].run_id,),
    )
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)

    assert result.settled_execution_recovery_count == 0
    assert result.settled_execution_blocked_count == 1
    assert state["job"].status is JobStatus.NEEDS_VERIFICATION
    assert state["run"].status is RunStatus.RUNNING
    assert state["attempt"].status is ProviderAttemptStatus.SETTLED
    assert state["event_count"] == 0


def test_raw_terminalization_and_post_recovery_mutation_are_blocked(storage, account):
    crash = _settled_crash(storage, account, "sqlite-guards")
    storage.release_or_requeue_expired_leases(now=EXPIRED)

    with pytest.raises(Exception, match="immutable"):
        storage.conn.execute(
            "UPDATE model_usage SET estimated_cost_usd=0.02 WHERE id=?",
            (crash["usage_id"],),
        )
    storage.conn.rollback()
    with pytest.raises(Exception, match="immutable"):
        storage.conn.execute(
            "UPDATE runs SET cost_usd=0.02 WHERE id=?", (crash["execution"].run_id,),
        )
    storage.conn.rollback()


def test_concurrent_maintenance_creates_one_recovery_event(tmp_path, account):
    db_path = tmp_path / "concurrent-settled.db"
    seed = SqliteStorage.open(db_path)
    crash = _settled_crash(seed, account, "concurrent")
    seed.close()

    def recover():
        store = SqliteStorage.open(db_path)
        try:
            return store.release_or_requeue_expired_leases(now=EXPIRED)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: recover(), range(2)))

    check = SqliteStorage.open(db_path)
    try:
        state = _state(check, crash)
        assert sum(item.settled_execution_recovery_count for item in results) == 1
        assert state["job"].status is JobStatus.FAILED
        assert state["usage_count"] == 1
        assert state["event_count"] == 1
    finally:
        check.close()


def test_reaper_before_resolver_accepts_stopped_prestate(storage, account):
    crash = _settled_crash(storage, account, "reaper-first")
    storage.mark_job_needs_verification(
        crash["job"].id, crash["execution"].lease_owner,
        "Simulated post-settlement worker boundary.", now=NOW,
    )
    reaped = storage.reap_orphaned_stale_runs(
        NOW + timedelta(seconds=1), now=EXPIRED,
    )
    assert reaped.stopped_count == 1

    storage.resolve_provider_attempt_reconciliation(
        request_id=crash["request_id"], account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=ACTUAL_COST, reconciled_by="owner",
        note="Resolve after the stale-run reaper.", now=EXPIRED,
    )

    state = _state(storage, crash)
    assert state["job"].status is JobStatus.FAILED
    assert state["run"].status is RunStatus.FAILED
    assert state["event_count"] == 1


def test_resolver_before_reaper_is_terminal_and_reaper_is_noop(storage, account):
    crash = _settled_crash(storage, account, "resolver-first")
    storage.resolve_provider_attempt_reconciliation(
        request_id=crash["request_id"], account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=ACTUAL_COST, reconciled_by="owner",
        note="Resolve before the stale-run reaper.", now=EXPIRED,
    )
    reaped = storage.reap_orphaned_stale_runs(
        NOW + timedelta(seconds=1), now=EXPIRED + timedelta(seconds=1),
    )
    assert reaped.stopped_count == 0
    assert _state(storage, crash)["run"].status is RunStatus.FAILED


def test_two_concurrent_resolvers_are_one_idempotent_operation(tmp_path, account):
    db_path = tmp_path / "concurrent-resolvers.db"
    seed = SqliteStorage.open(db_path)
    crash = _settled_crash(seed, account, "two-resolvers")
    seed.close()
    barrier = Barrier(2)

    def resolve(index: int):
        store = SqliteStorage.open(db_path)
        try:
            barrier.wait(timeout=5)
            return store.resolve_provider_attempt_reconciliation(
                request_id=crash["request_id"], account_id=account.id,
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=ACTUAL_COST, reconciled_by=f"owner-{index}",
                note=f"Concurrent resolver {index}.", now=EXPIRED,
            )
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resolve, range(2)))

    check = SqliteStorage.open(db_path)
    try:
        state = _state(check, crash)
        assert sum(item.idempotent for item in results) == 1
        assert state["event_count"] == 1
        assert state["usage_count"] == 1
        assert state["job"].status is JobStatus.FAILED
    finally:
        check.close()


def test_concurrent_maintenance_and_resolver_converge(tmp_path, account):
    db_path = tmp_path / "maintenance-resolver.db"
    seed = SqliteStorage.open(db_path)
    crash = _settled_crash(seed, account, "maintenance-resolver")
    seed.close()
    barrier = Barrier(2)

    def maintain():
        store = SqliteStorage.open(db_path)
        try:
            barrier.wait(timeout=5)
            return store.release_or_requeue_expired_leases(now=EXPIRED)
        finally:
            store.close()

    def resolve():
        store = SqliteStorage.open(db_path)
        try:
            barrier.wait(timeout=5)
            return store.resolve_provider_attempt_reconciliation(
                request_id=crash["request_id"], account_id=account.id,
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=ACTUAL_COST, reconciled_by="owner",
                note="Race maintenance with resolver.", now=EXPIRED,
            )
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(maintain), pool.submit(resolve)]
        for outcome in outcomes:
            outcome.result(timeout=10)

    check = SqliteStorage.open(db_path)
    try:
        state = _state(check, crash)
        assert state["event_count"] == 1
        assert state["usage_count"] == 1
        assert state["job"].status is JobStatus.FAILED
    finally:
        check.close()


def test_card_cannot_be_reinterpreted_as_execution_failure(storage, account):
    crash = _settled_crash(storage, account, "conflicting-card", with_card=True)
    with pytest.raises(ProviderAttemptReconciliationError, match="cannot coexist"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=crash["request_id"], account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=ACTUAL_COST, reconciled_by="owner",
            note="Contradict the durable card.", now=EXPIRED,
        )
    assert _state(storage, crash)["event_count"] == 0


def test_foreign_topic_card_is_blocked_fail_closed(storage, account):
    crash = _settled_crash(storage, account, "foreign-topic", with_card=True)
    other = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Other", question="Other?", score=90,
        status=TopicStatus.SELECTED,
    ))
    storage.conn.execute(
        "UPDATE research_cards SET topic_id=? WHERE id=?",
        (other.id, crash["card"].id),
    )
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)
    assert result.settled_execution_blocked_count == 1
    assert state["job"].status is JobStatus.NEEDS_VERIFICATION
    assert state["event_count"] == 0


def test_foreign_account_lineage_is_blocked_fail_closed(storage, account):
    crash = _settled_crash(storage, account, "foreign-account", with_card=True)
    foreign = account.model_copy(update={
        "id": "foreign-account", "display_name": "Foreign Account",
    })
    storage.ensure_account(foreign)
    storage.conn.execute(
        "UPDATE topics SET account_id=? WHERE id=?",
        (foreign.id, crash["topic"].id),
    )
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    assert result.settled_execution_blocked_count == 1
    assert _state(storage, crash)["event_count"] == 0


def test_research_card_has_exclusive_run_ownership_at_sqlite_layer(storage, account):
    first = _settled_crash(storage, account, "card-owner", with_card=True)
    second = _settled_crash(storage, account, "card-foreign-run")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        storage.conn.execute(
            "UPDATE research_runs SET research_card_id=? WHERE id=?",
            (first["card"].id, second["execution"].run_id),
        )
    storage.conn.rollback()


def test_missing_usage_is_reviewable_not_terminalized(storage, account):
    crash = _settled_crash(storage, account, "missing-usage")
    storage.conn.execute("DELETE FROM model_usage WHERE id=?", (crash["usage_id"],))
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)
    assert result.settled_execution_blocked_count == 1
    assert state["job"].status is JobStatus.NEEDS_VERIFICATION
    assert state["usage_count"] == 0
    assert state["event_count"] == 0


def test_second_usage_is_unrepresentable(storage, account):
    crash = _settled_crash(storage, account, "second-usage")
    row = storage.conn.execute(
        "SELECT run_id,provider,model,task,estimated_cost_usd,dry_run,request_id,created_at "
        "FROM model_usage WHERE id=?", (crash["usage_id"],),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        storage.conn.execute(
            "INSERT INTO model_usage "
            "(run_id,provider,model,task,estimated_cost_usd,dry_run,request_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", tuple(row),
        )
    storage.conn.rollback()
    assert _state(storage, crash)["usage_count"] == 1


def test_non_settled_attempt_never_uses_execution_recovery(storage, account):
    crash = _settled_crash(storage, account, "not-settled", settled=False)
    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    assert result.settled_execution_recovery_count == 0
    assert result.escalated_reconciliation_count == 1
    assert _state(storage, crash)["event_count"] == 0


def test_active_reservation_blocks_settled_execution_recovery(storage, account):
    crash = _settled_crash(storage, account, "active-reservation")
    storage.conn.execute(
        "UPDATE jobs SET reserved_cost_usd=0.1,budget_reserved_at=? WHERE id=?",
        (NOW.isoformat(), crash["job"].id),
    )
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=EXPIRED)
    state = _state(storage, crash)
    assert result.settled_execution_blocked_count == 1
    assert state["job"].status is JobStatus.NEEDS_VERIFICATION
    assert state["event_count"] == 0


def test_raw_sqlite_cannot_terminalize_before_authorizing_event(storage, account):
    crash = _settled_crash(storage, account, "raw-before-event")
    storage.mark_job_needs_verification(
        crash["job"].id, crash["execution"].lease_owner,
        "Simulated crash boundary.", now=NOW,
    )
    with pytest.raises(sqlite3.IntegrityError, match="EXECUTION_RECOVERY"):
        storage.conn.execute(
            "UPDATE jobs SET status='FAILED' WHERE id=?", (crash["job"].id,),
        )
    storage.conn.rollback()
    assert _state(storage, crash)["job"].status is JobStatus.NEEDS_VERIFICATION


def test_recovery_rolls_back_event_and_lifecycle_on_fault(storage, account, monkeypatch):
    crash = _settled_crash(storage, account, "fault-rollback")

    def interrupt(point):
        if str(getattr(point, "value", point)) == "AFTER_EVENT_INSERT":
            raise RuntimeError("injected recovery interruption")

    monkeypatch.setattr(storage, "_reconciliation_fault_point", interrupt)
    with pytest.raises(RuntimeError, match="injected recovery interruption"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=crash["request_id"], account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=ACTUAL_COST, reconciled_by="owner",
            note="Interrupt after event insert.", now=EXPIRED,
        )
    state = _state(storage, crash)
    assert state["job"].status is JobStatus.RUNNING
    assert state["run"].status is RunStatus.RUNNING
    assert state["event_count"] == 0
    assert state["usage_count"] == 1


def test_terminal_recovery_survives_reopen_without_duplicates(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    crash = _settled_crash(storage, account, "reopen-terminal", with_card=True)
    storage.release_or_requeue_expired_leases(now=EXPIRED)
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        state = _state(reopened, crash)
        assert state["job"].status is JobStatus.DONE
        assert state["attempt"].status is ProviderAttemptStatus.SETTLED
        assert state["usage_count"] == 1
        assert state["event_count"] == 1
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?",
            (crash["job"].id,),
        ).fetchone()[0] == 1
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM research_cards WHERE id=?",
            (crash["card"].id,),
        ).fetchone()[0] == 1
        repeated = reopened.release_or_requeue_expired_leases(
            now=EXPIRED + timedelta(days=1),
        )
        assert repeated.settled_execution_recovery_count == 0
    finally:
        reopened.close()
