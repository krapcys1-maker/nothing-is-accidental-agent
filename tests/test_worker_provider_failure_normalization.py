"""Offline E2E contracts for W1A-R4-01 worker failure normalization."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
import threading
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
    ProviderAttemptStatus,
    ReconciliationEventType,
    ResearchExecutionFailureOutcome,
    ResearchRunStatus,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import (
    BudgetReservationError,
    ProviderAttemptReconciliationError,
    ReconciliationPreviewStaleError,
    StaleJobExecutionError,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.scheduler.dispatcher import DispatchResult, UncertainExternalEffectError
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)


def _enable_worker(storage: SqliteStorage) -> None:
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", False),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="offline", now=NOW)


def _enqueue_durable_job(storage: SqliteStorage, account, suffix: str) -> Job:
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=f"Failure normalization {suffix}",
        question="Why must a provider boundary stay visible?",
        score=90,
        status=TopicStatus.SELECTED,
    ))
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="offline-reconciliation-model",
            research_timeout_seconds=60,
        ),
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd=0.2,
        max_web_searches=1,
        question=topic.question,
        niche=account.niche,
    )
    return storage.enqueue_job(Job(
        id=f"failure-normalization-{suffix}",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"failure-normalization-key-{suffix}",
        topic_id=int(topic.id),
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
        max_attempts=1,
        created_at=NOW,
    ))


def _claimed_execution(
    storage: SqliteStorage, account, suffix: str,
) -> JobExecutionContext:
    job = _enqueue_durable_job(storage, account, suffix)
    lease = storage.claim_next_job(f"owner-{suffix}", 120, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(
        job.id, lease.lease_owner, f"failure-normalization-run-{suffix}", now=NOW,
    )
    return JobExecutionContext(
        job_id=job.id,
        lease_owner=lease.lease_owner,
        run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )


class BoundaryDispatcher:
    """Creates durable boundaries directly; it never owns or calls a provider."""

    def __init__(
        self,
        storage: SqliteStorage,
        *,
        boundary: str,
        exception_type: type[Exception] = RuntimeError,
    ) -> None:
        self.storage = storage
        self.boundary = boundary
        self.exception_type = exception_type
        self.execution: JobExecutionContext | None = None
        self.request_id: str | None = None
        self.provider_calls = 0

    def dispatch(self, job: Job, *, lease_owner: str, heartbeat) -> object:
        del heartbeat
        initialized = self.storage.initialize_research_run_for_job(
            job.id, lease_owner, f"{job.id}-run", now=NOW,
        )
        self.execution = JobExecutionContext(
            job_id=job.id,
            lease_owner=lease_owner,
            run_id=initialized.run.id,
            clock=FixedClock(NOW),
        )
        if self.boundary == "BEFORE_BEGIN":
            raise self.exception_type("forced failure before provider reservation")
        attempt = self.storage.begin_provider_attempt(
            self.execution,
            stage="research",
            attempt_no=1,
            max_cost_usd=0.2,
            daily_limit_usd=2.0,
            monthly_limit_usd=40.0,
        )
        self.request_id = attempt.request_id
        if self.boundary == "RESERVED":
            raise self.exception_type("forced failure after reservation")
        self.storage.mark_provider_attempt_request_started(
            self.execution, attempt.request_id,
        )
        if self.boundary == "NEEDS_RECONCILIATION":
            self.storage.mark_provider_attempt_needs_reconciliation(
                self.execution, attempt.request_id, error_code="FIRST_ESCALATION",
            )
        raise self.exception_type("forced failure after request boundary")


def _worker(
    settings, storage: SqliteStorage, dispatcher, *,
    heartbeat_storage_factory=None, heartbeat_waiter_factory=None,
) -> Worker:
    return Worker(
        storage=storage,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        dispatcher=dispatcher,
        lease_owner="failure-normalization-worker",
        lease_seconds=120,
        heartbeat_interval_seconds=30,
        heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=(
            heartbeat_storage_factory or (lambda: SqliteStorage.open(settings.db_path))
        ),
        **(
            {"heartbeat_waiter_factory": heartbeat_waiter_factory}
            if heartbeat_waiter_factory is not None else {}
        ),
        clock=FixedClock(NOW),
        sleeper=lambda _: None,
    )


@pytest.mark.parametrize(
    ("boundary", "exception_type", "expected_worker", "expected_attempt", "expected_reason"),
    [
        ("BEFORE_BEGIN", RuntimeError, WorkerIterationStatus.FAILED, None, None),
        (
            "RESERVED", RuntimeError, WorkerIterationStatus.NEEDS_VERIFICATION,
            ProviderAttemptStatus.NEEDS_RECONCILIATION,
            "UNEXPECTED_EXECUTION_FAILURE_BEFORE_REQUEST_STARTED",
        ),
        (
            "REQUEST_STARTED", sqlite3.OperationalError,
            WorkerIterationStatus.NEEDS_VERIFICATION,
            ProviderAttemptStatus.NEEDS_RECONCILIATION,
            "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED",
        ),
        (
            "REQUEST_STARTED", RuntimeError, WorkerIterationStatus.NEEDS_VERIFICATION,
            ProviderAttemptStatus.NEEDS_RECONCILIATION,
            "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED",
        ),
        (
            "REQUEST_STARTED", OSError, WorkerIterationStatus.NEEDS_VERIFICATION,
            ProviderAttemptStatus.NEEDS_RECONCILIATION,
            "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED",
        ),
        (
            "REQUEST_STARTED", UncertainExternalEffectError,
            WorkerIterationStatus.NEEDS_VERIFICATION,
            ProviderAttemptStatus.NEEDS_RECONCILIATION,
            "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED",
        ),
    ],
)
def test_worker_run_once_normalizes_every_provider_boundary(
    settings, storage, account, boundary, exception_type, expected_worker,
    expected_attempt, expected_reason,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, f"e2e-{boundary}-{exception_type.__name__}")
    dispatcher = BoundaryDispatcher(
        storage, boundary=boundary, exception_type=exception_type,
    )

    result = _worker(settings, storage, dispatcher).run_once()

    assert result.status is expected_worker
    durable_job = storage.get_job(job.id)
    assert durable_job is not None
    assert dispatcher.provider_calls == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] in (0, 1)
    if expected_attempt is None:
        assert durable_job.status is JobStatus.FAILED
        assert storage.get_run(dispatcher.execution.run_id).status is RunStatus.FAILED
        assert storage.get_research_run(dispatcher.execution.run_id).status is ResearchRunStatus.FAILED
        return

    assert durable_job.status is JobStatus.NEEDS_VERIFICATION
    assert durable_job.lease_owner is None and durable_job.finished_at is None
    assert storage.get_run(dispatcher.execution.run_id).status is RunStatus.RUNNING
    assert storage.get_research_run(dispatcher.execution.run_id).status is ResearchRunStatus.PENDING
    row = storage.conn.execute(
        "SELECT status,error_code FROM provider_attempts WHERE request_id=?",
        (dispatcher.request_id,),
    ).fetchone()
    assert tuple(row) == (expected_attempt.value, expected_reason)
    events = storage.list_reconciliation_events(
        request_id=dispatcher.request_id, account_id=account.id,
    )
    assert len(events) == 1
    assert events[0].event_type is ReconciliationEventType.AUTO_ESCALATION
    assert storage.list_provider_attempts_needing_reconciliation(
        account_id=account.id,
    )[0].request_id == dispatcher.request_id
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=dispatcher.request_id, account_id=account.id,
    )
    assert preview.reservation_active and preview.reserved_amount_usd == pytest.approx(0.2)
    assert preview.event_count == 1


def test_failure_while_marking_reconciliation_is_caught_by_shared_boundary(
    settings, storage, account, monkeypatch,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "mark-failure")
    dispatcher = BoundaryDispatcher(storage, boundary="NEEDS_RECONCILIATION")

    def broken_mark(*_args, **_kwargs):
        raise sqlite3.OperationalError("forced mark failure")

    monkeypatch.setattr(storage, "mark_provider_attempt_needs_reconciliation", broken_mark)
    result = _worker(settings, storage, dispatcher).run_once()

    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    attempt = storage.list_provider_attempts_needing_reconciliation(account_id=account.id)
    assert len(attempt) == 1
    assert attempt[0].request_id == dispatcher.request_id
    assert attempt[0].error_code == "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED"
    assert dispatcher.provider_calls == 0


def test_heartbeat_failure_after_request_started_uses_same_normalization(
    settings, storage, account,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "heartbeat-after-request")
    trigger = threading.Event()
    waiter_ready = threading.Event()
    heartbeat_failed = threading.Event()

    class TriggeredWaiter:
        def wait(self, stop_event, _timeout_seconds):
            waiter_ready.set()
            while not stop_event.is_set() and not trigger.wait(timeout=0.01):
                pass
            return stop_event.is_set()

        def wake(self):
            trigger.set()

    class FailingHeartbeatStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            heartbeat_failed.set()
            raise sqlite3.OperationalError("forced heartbeat storage failure")

        def close(self):
            pass

    class HeartbeatBoundaryDispatcher(BoundaryDispatcher):
        def dispatch(self, job: Job, *, lease_owner: str, heartbeat) -> object:
            del heartbeat
            initialized = self.storage.initialize_research_run_for_job(
                job.id, lease_owner, f"{job.id}-run", now=NOW,
            )
            self.execution = JobExecutionContext(
                job_id=job.id,
                lease_owner=lease_owner,
                run_id=initialized.run.id,
                clock=FixedClock(NOW),
            )
            attempt = self.storage.begin_provider_attempt(
                self.execution,
                stage="research",
                attempt_no=1,
                max_cost_usd=0.2,
                daily_limit_usd=2.0,
                monthly_limit_usd=40.0,
            )
            self.request_id = attempt.request_id
            self.storage.mark_provider_attempt_request_started(
                self.execution, attempt.request_id,
            )
            assert waiter_ready.wait(timeout=1)
            trigger.set()
            assert heartbeat_failed.wait(timeout=1)
            return DispatchResult.worker_must_complete()

    dispatcher = HeartbeatBoundaryDispatcher(storage, boundary="REQUEST_STARTED")
    result = _worker(
        settings,
        storage,
        dispatcher,
        heartbeat_storage_factory=FailingHeartbeatStorage,
        heartbeat_waiter_factory=TriggeredWaiter,
    ).run_once()

    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    assert tuple(storage.conn.execute(
        "SELECT status,error_code FROM provider_attempts WHERE request_id=?",
        (dispatcher.request_id,),
    ).fetchone()) == (
        "NEEDS_RECONCILIATION",
        "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED",
    )
    assert dispatcher.provider_calls == 0


def test_already_needing_reconciliation_is_idempotent_without_second_event(
    settings, storage, account,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "already-needs")
    dispatcher = BoundaryDispatcher(storage, boundary="NEEDS_RECONCILIATION")

    result = _worker(settings, storage, dispatcher).run_once()

    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (dispatcher.request_id,),
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1


def test_reopen_recovery_preview_and_not_charged_resolution(
    settings, storage, account,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "reopen-release")
    dispatcher = BoundaryDispatcher(storage, boundary="REQUEST_STARTED", exception_type=OSError)
    assert _worker(settings, storage, dispatcher).run_once().status is WorkerIterationStatus.NEEDS_VERIFICATION

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
        recovery = reopened.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
        assert recovery.escalated_reconciliation_count == 0
        assert reopened.conn.execute(
            "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
            (dispatcher.request_id,),
        ).fetchone()[0] == 1
        preview = reopened.preview_provider_attempt_reconciliation(
            request_id=dispatcher.request_id, account_id=account.id,
        )
        resolved = reopened.resolve_provider_attempt_reconciliation(
            request_id=dispatcher.request_id,
            account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None,
            reconciled_by="offline-operator",
            note="Provider confirmed no charge.",
            expected_version_token=preview.version_token,
        )
        assert resolved.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
        assert reopened.get_job(job.id).status is JobStatus.FAILED
        assert reopened.get_job(job.id).reserved_cost_usd == 0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reopened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()


def test_request_started_supports_unknown_then_charged_known_and_stale_token(
    settings, storage, account,
):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "charged-known")
    dispatcher = BoundaryDispatcher(storage, boundary="REQUEST_STARTED")
    assert _worker(settings, storage, dispatcher).run_once().status is WorkerIterationStatus.NEEDS_VERIFICATION
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=dispatcher.request_id, account_id=account.id,
    )

    observed = storage.resolve_provider_attempt_reconciliation(
        request_id=dispatcher.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None,
        reconciled_by="offline-operator",
        note="Invoice is not available yet.",
        expected_version_token=preview.version_token,
    )
    assert observed.attempt.status is ProviderAttemptStatus.NEEDS_RECONCILIATION
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    assert len(storage.list_provider_attempts_needing_reconciliation(account_id=account.id)) == 1
    with pytest.raises(ReconciliationPreviewStaleError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=dispatcher.request_id,
            account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.05",
            reconciled_by="offline-operator",
            note="Invoice later confirmed the charge.",
            expected_version_token=preview.version_token,
        )
    fresh = storage.preview_provider_attempt_reconciliation(
        request_id=dispatcher.request_id, account_id=account.id,
    )
    resolved = storage.resolve_provider_attempt_reconciliation(
        request_id=dispatcher.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.05",
        reconciled_by="offline-operator",
        note="Invoice later confirmed the charge.",
        expected_version_token=fresh.version_token,
    )
    assert resolved.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert storage.get_job(job.id).reserved_cost_usd == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?", (dispatcher.request_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1


def test_reserved_resolution_allows_only_not_charged(settings, storage, account):
    _enable_worker(storage)
    job = _enqueue_durable_job(storage, account, "reserved-release")
    dispatcher = BoundaryDispatcher(storage, boundary="RESERVED")
    assert _worker(settings, storage, dispatcher).run_once().status is WorkerIterationStatus.NEEDS_VERIFICATION

    with pytest.raises(ProviderAttemptReconciliationError, match="only be resolved NOT_CHARGED"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=dispatcher.request_id,
            account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.01",
            reconciled_by="offline-operator",
            note="Forbidden charged outcome.",
        )
    resolved = storage.resolve_provider_attempt_reconciliation(
        request_id=dispatcher.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None,
        reconciled_by="offline-operator",
        note="No request crossed the provider boundary.",
    )
    assert resolved.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert storage.get_job(job.id).status is JobStatus.FAILED


def test_active_reservation_blocks_budget_until_operator_resolution(
    settings, storage, account,
):
    _enable_worker(storage)
    first = _enqueue_durable_job(storage, account, "budget-first")
    dispatcher = BoundaryDispatcher(storage, boundary="REQUEST_STARTED")
    assert _worker(settings, storage, dispatcher).run_once().status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert storage.preview_provider_attempt_reconciliation(
        request_id=dispatcher.request_id, account_id=account.id,
    ).reservation_active

    second_execution = _claimed_execution(storage, account, "budget-second")
    with pytest.raises(BudgetReservationError):
        storage.begin_provider_attempt(
            second_execution,
            stage="research",
            attempt_no=1,
            max_cost_usd=0.2,
            daily_limit_usd=0.3,
            monthly_limit_usd=40.0,
        )
    storage.resolve_provider_attempt_reconciliation(
        request_id=dispatcher.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None,
        reconciled_by="offline-operator",
        note="No provider charge.",
    )
    second = storage.begin_provider_attempt(
        second_execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=0.3,
        monthly_limit_usd=40.0,
    )
    assert second.status is ProviderAttemptStatus.RESERVED


@pytest.mark.parametrize("attempt_status", ["RESERVED", "REQUEST_STARTED"])
@pytest.mark.parametrize(
    ("table", "status"),
    [("jobs", "FAILED"), ("runs", "FAILED"), ("research_runs", "FAILED")],
)
def test_sqlite_blocks_raw_terminal_state_until_attempt_is_normalized(
    storage, account, attempt_status, table, status,
):
    execution = _claimed_execution(
        storage, account, f"raw-{attempt_status}-{table}",
    )
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    if attempt_status == "REQUEST_STARTED":
        storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    identifier = execution.job_id if table == "jobs" else execution.run_id

    with pytest.raises(sqlite3.IntegrityError, match="provider_attempt normalization"):
        storage.conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status, identifier))
    storage.conn.rollback()

    assert storage.get_job(execution.job_id).status is JobStatus.RUNNING
    assert storage.get_run(execution.run_id).status is RunStatus.RUNNING
    assert storage.get_research_run(execution.run_id).status is ResearchRunStatus.PENDING
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == attempt_status


def test_storage_failure_without_attempt_keeps_legacy_failed_semantics(storage, account):
    execution = _claimed_execution(storage, account, "no-attempt")

    outcome = storage.fail_or_escalate_job_research_execution(
        execution, 0.0, "NO_PROVIDER_ATTEMPT", terminalize_job=True,
    )

    assert outcome is ResearchExecutionFailureOutcome.TERMINALIZED_FAILED
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert storage.get_run(execution.run_id).status is RunStatus.FAILED
    assert storage.get_research_run(execution.run_id).status is ResearchRunStatus.FAILED


def test_terminal_attempt_allows_normal_failure_and_repeat_is_idempotent(storage, account):
    execution = _claimed_execution(storage, account, "terminal-attempt")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.release_provider_attempt_before_request(
        execution, attempt.request_id, error_code="LOCAL_PRE_REQUEST_FAILURE",
    )

    first = storage.fail_or_escalate_job_research_execution(
        execution, 0.0, "TERMINAL_ATTEMPT_FAILURE", terminalize_job=True,
    )
    second = storage.fail_or_escalate_job_research_execution(
        execution, 0.0, "TERMINAL_ATTEMPT_FAILURE", terminalize_job=True,
    )

    assert first is ResearchExecutionFailureOutcome.TERMINALIZED_FAILED
    assert second is ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == "RELEASED"


def test_expired_fence_with_request_started_rolls_back_without_hiding_attempt(
    storage, account,
):
    execution = _claimed_execution(storage, account, "expired-fence")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    expired = JobExecutionContext(
        job_id=execution.job_id,
        lease_owner=execution.lease_owner,
        run_id=execution.run_id,
        clock=FixedClock(NOW + timedelta(seconds=121)),
    )

    with pytest.raises(StaleJobExecutionError):
        storage.fail_or_escalate_job_research_execution(
            expired, None, "EXPIRED_FENCE", terminalize_job=True,
        )

    assert storage.get_job(execution.job_id).status is JobStatus.RUNNING
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == "REQUEST_STARTED"
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("started", "expected"),
    [
        (False, ResearchExecutionFailureOutcome.ESCALATED_RESERVED),
        (True, ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED),
    ],
)
def test_storage_failure_returns_explicit_escalation_outcome(
    storage, account, started, expected,
):
    execution = _claimed_execution(storage, account, f"explicit-{started}")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    if started:
        storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    outcome = storage.fail_or_escalate_job_research_execution(
        execution, None, "EXPLICIT_OUTCOME", terminalize_job=True,
    )

    assert outcome is expected
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION


def test_two_failure_connections_commit_one_escalation_and_one_idempotent_result(
    settings, storage, account,
):
    execution = _claimed_execution(storage, account, "concurrent-failure")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    def normalize(_: int) -> ResearchExecutionFailureOutcome:
        local = SqliteStorage.open(settings.db_path)
        try:
            return local.fail_or_escalate_job_research_execution(
                execution, None, "CONCURRENT_FAILURE", terminalize_job=True,
            )
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = set(pool.map(normalize, range(2)))
    assert outcomes == {
        ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED,
        ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION,
    }
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()[0] == 1


def test_failure_and_recovery_race_converge_on_one_reviewable_attempt(
    settings, storage, account,
):
    execution = _claimed_execution(storage, account, "recovery-race")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    def normalize():
        local = SqliteStorage.open(settings.db_path)
        try:
            return local.fail_or_escalate_job_research_execution(
                execution, None, "FAILURE_RECOVERY_RACE", terminalize_job=True,
            )
        finally:
            local.close()

    def recover():
        local = SqliteStorage.open(settings.db_path)
        try:
            return local.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        normalized = pool.submit(normalize)
        recovered = pool.submit(recover)
        normalized.result()
        recovered.result()

    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()[0] == 1


def test_reaper_then_repeat_failure_and_resolver_converge(storage, account):
    execution = _claimed_execution(storage, account, "reaper-convergence")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    assert storage.fail_or_escalate_job_research_execution(
        execution, None, "FIRST_FAILURE", terminalize_job=True,
    ) is ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED

    reaped = storage.reap_orphaned_stale_runs(
        NOW + timedelta(hours=1), now=NOW + timedelta(days=1),
    )
    assert reaped.stopped_count == 1
    assert storage.get_run(execution.run_id).status is RunStatus.STOPPED
    assert storage.fail_or_escalate_job_research_execution(
        execution, None, "REPEATED_FAILURE", terminalize_job=True,
    ) is ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION
    resolved = storage.resolve_provider_attempt_reconciliation(
        request_id=attempt.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None,
        reconciled_by="offline-operator",
        note="Reaper state and provider invoice were checked.",
    )
    assert resolved.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert storage.get_run(execution.run_id).status is RunStatus.FAILED


def test_fingerprint_mismatch_stays_visible_reserved_and_resolver_fail_closed(
    storage, account,
):
    execution = _claimed_execution(storage, account, "fail-closed")
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research",
        attempt_no=1,
        max_cost_usd=0.2,
        daily_limit_usd=2.0,
        monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    row = storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
    ).fetchone()
    storage.conn.execute(
        "UPDATE jobs SET payload_json=json_set(payload_json,'$.execution_intent.model','tampered') "
        "WHERE id=?",
        (execution.job_id,),
    )
    storage.conn.commit()

    outcome = storage.fail_or_escalate_job_research_execution(
        execution, None, "MUST_NOT_TERMINALIZE", terminalize_job=True,
    )
    assert outcome is ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED
    assert storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
    ).fetchone()[0] != row[0]
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"
    assert storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0] == 1
    assert storage.list_provider_attempts_needing_reconciliation(
        account_id=account.id,
    )[0].request_id == attempt.request_id
    assert storage.preview_provider_attempt_reconciliation(
        request_id=attempt.request_id, account_id=account.id,
    ).reservation_active
    with pytest.raises(
        ProviderAttemptReconciliationError,
        match="fingerprint|identity",
    ):
        storage.resolve_provider_attempt_reconciliation(
            request_id=attempt.request_id,
            account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None,
            reconciled_by="offline-operator",
            note="The mismatched durable intent requires owner repair.",
        )


def test_wrong_fence_without_attempt_is_rejected(storage, account):
    execution = _claimed_execution(storage, account, "wrong-fence")
    wrong = JobExecutionContext(
        job_id=execution.job_id,
        lease_owner="wrong-owner",
        run_id=execution.run_id,
        clock=FixedClock(NOW),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.fail_or_escalate_job_research_execution(
            wrong, None, "WRONG_FENCE", terminalize_job=True,
        )
    assert storage.get_job(execution.job_id).status is JobStatus.RUNNING
