"""Deterministic offline contracts for the Stage 1 maintenance runner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading

import pytest

import app.orchestrator.runner as orchestrator_runner
import app.scheduler.dispatcher as dispatcher_module
import app.workflows.research.pipeline as research_pipeline
from app.main import main
from app.models import (
    Job,
    JobKind,
    JobRecoveryResult,
    JobStatus,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunReaperResult,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.browser import DisabledBrowser
from app.research.fake_client import FakeResearchClient
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.maintenance import EventMaintenanceWaiter, MaintenanceCycleError, MaintenanceRunner
from app.scheduler.worker import Worker
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, moment: datetime = NOW) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment


class RecordingStorage:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def release_or_requeue_expired_leases(self, *, now=None, clock=None) -> JobRecoveryResult:
        assert (clock.now() if clock is not None else now) is NOW
        self.events.append("recovery")
        return JobRecoveryResult(requeued_count=1)

    def reap_orphaned_stale_runs(self, stale_before, *, now=None, clock=None) -> RunReaperResult:
        assert (clock.now() if clock is not None else now) is NOW
        assert stale_before == NOW - timedelta(seconds=5)
        self.events.append("reaper")
        return RunReaperResult(checked_count=1, stopped_count=1)

    def close(self) -> None:
        self.events.append("close")


class SequenceWaiter:
    def __init__(self, events: list[str], *, stop_after: int) -> None:
        self.events = events
        self.stop_after = stop_after
        self.calls = 0

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool:
        self.calls += 1
        self.events.append(f"wait:{timeout_seconds}")
        if self.calls >= self.stop_after:
            stop_event.set()
            return True
        return False


def _local_job(account, job_id: str, *, created_at: datetime = NOW) -> Job:
    return Job(
        id=job_id,
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key=f"maintenance-{job_id}",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=created_at,
        created_at=created_at,
        max_attempts=2,
    )


def _research_job(account, topic: Topic, job_id: str, *, created_at: datetime) -> Job:
    return Job(
        id=job_id,
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"maintenance-{job_id}",
        topic_id=topic.id,
        payload={"account_id": account.id, "topic_id": topic.id, "dry_run": True},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=created_at,
        created_at=created_at,
        max_attempts=2,
    )


def _selected_topic(storage: SqliteStorage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Maintenance needs evidence",
        question="What must maintenance preserve?",
        score=90,
        status=TopicStatus.SELECTED,
    ))


def _runner(settings, clock: MutableClock, *, stale_after_seconds: float = 5.0,
            waiter=None, storage_factory=None) -> MaintenanceRunner:
    return MaintenanceRunner(
        storage_factory=storage_factory or (lambda: SqliteStorage.open(settings.db_path)),
        stale_after_seconds=stale_after_seconds,
        clock=clock,
        waiter=waiter,
    )


def _expired_research_with_run(storage: SqliteStorage, account, *, job_id: str = "expired-research"):
    old = NOW - timedelta(seconds=10)
    topic = _selected_topic(storage, account)
    job = storage.enqueue_job(_research_job(account, topic, job_id, created_at=old))
    storage.reserve_job_budget(
        job.id, 0.25, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=old,
    )
    assert storage.claim_next_job("crashed-worker", 5, now=old) is not None
    run_id = f"{job_id}-run"
    storage.create_run(Run(
        id=run_id,
        account_id=account.id,
        workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
        started_at=old,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id,
        account_id=account.id,
        topic_id=int(topic.id),
        flow=ResearchFlow.SINGLE,
        status=ResearchRunStatus.PENDING,
    ))
    storage.attach_job_run(job.id, "crashed-worker", run_id, now=old)
    return job, run_id


def _install_forbidden_execution_spies(monkeypatch) -> dict[str, int]:
    """Instrument every execution boundary that maintenance must never reach."""
    calls = {
        "claim": 0,
        "worker": 0,
        "dispatcher": 0,
        "local_execution": 0,
        "research_execution": 0,
        "fake_research_client": 0,
        "research_pipeline": 0,
        "research_resume": 0,
        "api_client_factory": 0,
        "browser_public": 0,
    }

    def forbidden(name: str):
        def record(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"maintenance reached forbidden boundary: {name}")
        return record

    monkeypatch.setattr(SqliteStorage, "claim_next_job", forbidden("claim"))
    monkeypatch.setattr(Worker, "run_once", forbidden("worker"))
    monkeypatch.setattr(JobDispatcher, "dispatch", forbidden("dispatcher"))
    monkeypatch.setattr(
        JobDispatcher, "_validate_local", staticmethod(forbidden("local_execution")),
    )
    monkeypatch.setattr(
        JobDispatcher, "_dispatch_research_dry_run", forbidden("research_execution"),
    )
    monkeypatch.setattr(FakeResearchClient, "__init__", forbidden("fake_research_client"))
    monkeypatch.setattr(research_pipeline, "run_research_pipeline", forbidden("research_pipeline"))
    monkeypatch.setattr(research_pipeline, "resume_research_stage_b", forbidden("research_resume"))
    monkeypatch.setattr(research_pipeline, "resume_staged_research", forbidden("research_resume"))
    monkeypatch.setattr(orchestrator_runner, "_build_research_client", forbidden("api_client_factory"))
    monkeypatch.setattr(DisabledBrowser, "publish_note", forbidden("browser_public"))
    monkeypatch.setattr(DisabledBrowser, "publish_comment", forbidden("browser_public"))
    return calls


def _assert_no_execution_calls(calls: dict[str, int]) -> None:
    assert calls == {
        "claim": 0,
        "worker": 0,
        "dispatcher": 0,
        "local_execution": 0,
        "research_execution": 0,
        "fake_research_client": 0,
        "research_pipeline": 0,
        "research_resume": 0,
        "api_client_factory": 0,
        "browser_public": 0,
    }


def _system_flag_rows(storage: SqliteStorage) -> list[tuple[object, ...]]:
    rows = storage.conn.execute(
        "SELECT key, value_json, updated_at, updated_by, reason "
        "FROM system_flags ORDER BY key"
    ).fetchall()
    return [tuple(row) for row in rows]


def test_maintenance_cycle_runs_recovery_before_reaper():
    events: list[str] = []
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
    )

    result = runner.run_once()

    assert events == ["recovery", "reaper", "close"]
    assert result.recovery.requeued_count == 1
    assert result.reaper.stopped_count == 1


def test_maintenance_once_runs_exactly_one_cycle():
    events: list[str] = []
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
    )

    runner.run_once()

    assert events == ["recovery", "reaper", "close"]


def test_maintenance_poll_runs_first_cycle_immediately():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=1)
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    runner.run_forever(interval_seconds=60)

    assert events == ["recovery", "reaper", "close", "wait:60"]


def test_maintenance_poll_waits_between_completed_cycles():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=2)
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    runner.run_forever(interval_seconds=30)

    assert events == [
        "recovery", "reaper", "close", "wait:30",
        "recovery", "reaper", "close", "wait:30",
    ]


def test_maintenance_poll_stops_on_stop_event():
    events: list[str] = []
    stop_event = threading.Event()
    stop_event.set()
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
    )

    runner.run_forever(interval_seconds=60, stop_event=stop_event)

    assert events == []


def test_maintenance_poll_stop_event_interrupts_active_wait():
    """The production EventMaintenanceWaiter returns from a live wait on stop."""
    events: list[str] = []

    class ActiveWaitEvent(threading.Event):
        def __init__(self) -> None:
            super().__init__()
            self.wait_entered = threading.Event()

        def wait(self, timeout=None) -> bool:
            # This mirrors threading.Event.wait while signalling only after the
            # flag check and immediately before the real condition wait.
            with self._cond:
                signaled = self._flag
                if not signaled:
                    self.wait_entered.set()
                    signaled = self._cond.wait(timeout)
                return signaled

    stop_event = ActiveWaitEvent()
    failures: list[BaseException] = []
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=EventMaintenanceWaiter(),
    )

    def poll() -> None:
        try:
            runner.run_forever(interval_seconds=60, stop_event=stop_event)
        except BaseException as exc:
            failures.append(exc)

    def stop_during_active_wait() -> None:
        assert stop_event.wait_entered.wait(timeout=1)
        stop_event.set()

    poll_thread = threading.Thread(target=poll)
    stopper_thread = threading.Thread(target=stop_during_active_wait)
    poll_thread.start()
    stopper_thread.start()
    poll_thread.join(timeout=2)
    stopper_thread.join(timeout=2)

    assert not poll_thread.is_alive()
    assert not stopper_thread.is_alive()
    assert failures == []
    assert events == ["recovery", "reaper", "close"]


def test_maintenance_does_not_dispatch_or_run_research(settings, storage, account, monkeypatch):
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "no-dispatch"))
    calls = _install_forbidden_execution_spies(monkeypatch)

    result = _runner(settings, MutableClock()).run_once()

    assert result.recovery.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 0, "failed_count": 0,
        "escalated_reconciliation_count": 0,
    }
    assert storage.get_job(job.id).status is JobStatus.QUEUED
    assert storage.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM research_runs").fetchone()[0] == 0
    _assert_no_execution_calls(calls)


def test_maintenance_recovers_research_job_before_reaping_run(
    settings, storage, account, monkeypatch,
):
    job, run_id = _expired_research_with_run(storage, account)
    before = storage.get_job(job.id)
    assert before.status is JobStatus.LEASED
    assert before.run_id == run_id
    assert before.reserved_cost_usd == 0.25
    assert before.budget_reserved_at is not None
    calls = _install_forbidden_execution_spies(monkeypatch)

    result = _runner(settings, MutableClock(), stale_after_seconds=1).run_once()

    assert result.recovery.needs_verification_count == 1
    assert result.reaper.stopped_count == 1
    recovered = storage.get_job(job.id)
    assert recovered.status is JobStatus.NEEDS_VERIFICATION
    assert recovered.run_id == before.run_id == run_id
    assert recovered.reserved_cost_usd == before.reserved_cost_usd == 0.25
    assert recovered.budget_reserved_at == before.budget_reserved_at
    assert storage.get_run(run_id).status is RunStatus.STOPPED
    assert recovered.status is not JobStatus.DONE
    _assert_no_execution_calls(calls)

    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(job.id)
        assert persisted.status is JobStatus.NEEDS_VERIFICATION
        assert persisted.run_id == run_id
        assert persisted.reserved_cost_usd == 0.25
        assert persisted.budget_reserved_at == before.budget_reserved_at
        assert reopened.get_run(run_id).status is RunStatus.STOPPED
    finally:
        reopened.close()


def test_maintenance_keeps_fresh_active_job_and_run_untouched(settings, storage, account):
    topic = _selected_topic(storage, account)
    job = storage.enqueue_job(_research_job(account, topic, "fresh-research", created_at=NOW))
    assert storage.claim_next_job("fresh-worker", 60, now=NOW) is not None
    run_id = "fresh-research-run"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=NOW,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.SINGLE, status=ResearchRunStatus.PENDING,
    ))
    storage.attach_job_run(job.id, "fresh-worker", run_id, now=NOW)

    result = _runner(settings, MutableClock(), stale_after_seconds=1).run_once()

    assert result.recovery.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 0, "failed_count": 0,
        "escalated_reconciliation_count": 0,
    }
    assert result.reaper.model_dump() == {"checked_count": 0, "stopped_count": 0}
    assert storage.get_job(job.id).status is JobStatus.LEASED
    assert storage.get_run(run_id).status is RunStatus.RUNNING


def test_maintenance_requeues_recoverable_job_without_run_id(settings, storage, account):
    old = NOW - timedelta(seconds=10)
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "requeue-without-run", created_at=old))
    assert storage.claim_next_job("crashed-worker", 5, now=old) is not None

    result = _runner(settings, MutableClock()).run_once()

    assert result.recovery.requeued_count == 1
    assert storage.get_job(job.id).status is JobStatus.QUEUED


class BarrierStorage:
    def __init__(self, storage: SqliteStorage, barrier: threading.Barrier, *, barrier_method: str) -> None:
        self._storage = storage
        self._barrier = barrier
        self._barrier_method = barrier_method

    def release_or_requeue_expired_leases(self, *, now=None, clock=None):
        if self._barrier_method == "recovery":
            self._barrier.wait()
        if clock is not None:
            return self._storage.release_or_requeue_expired_leases(clock=clock)
        return self._storage.release_or_requeue_expired_leases(now=now)

    def reap_orphaned_stale_runs(self, stale_before, *, now=None, clock=None):
        if self._barrier_method == "reaper":
            self._barrier.wait()
        if clock is not None:
            return self._storage.reap_orphaned_stale_runs(stale_before, clock=clock)
        return self._storage.reap_orphaned_stale_runs(stale_before, now=now)

    def close(self) -> None:
        self._storage.close()


def _run_two_runners(runners: list[MaintenanceRunner]):
    results = []
    failures: list[BaseException] = []

    def run(runner: MaintenanceRunner) -> None:
        try:
            results.append(runner.run_once())
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=run, args=(runner,)) for runner in runners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert failures == []
    return results


def test_two_maintenance_runners_recover_job_exactly_once(settings, storage, account):
    old = NOW - timedelta(seconds=10)
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "concurrent-recovery", created_at=old))
    assert storage.claim_next_job("crashed-worker", 5, now=old) is not None
    barrier = threading.Barrier(2)
    runners = [
        _runner(
            settings, MutableClock(),
            storage_factory=lambda: BarrierStorage(
                SqliteStorage.open(settings.db_path), barrier, barrier_method="recovery",
            ),
        )
        for _ in range(2)
    ]

    results = _run_two_runners(runners)
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert sum(result.recovery.requeued_count for result in results) == 1
        assert reopened.get_job(job.id).status is JobStatus.QUEUED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_two_maintenance_runners_reap_run_exactly_once(settings, storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(
        id="concurrent-reaper-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=NOW - timedelta(seconds=10),
    ))
    barrier = threading.Barrier(2)
    runners = [
        _runner(
            settings, MutableClock(), stale_after_seconds=1,
            storage_factory=lambda: BarrierStorage(
                SqliteStorage.open(settings.db_path), barrier, barrier_method="reaper",
            ),
        )
        for _ in range(2)
    ]

    results = _run_two_runners(runners)
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert sum(result.reaper.stopped_count for result in results) == 1
        assert reopened.get_run("concurrent-reaper-run").status is RunStatus.STOPPED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_maintenance_concurrency_preserves_sqlite_integrity(settings, storage, account):
    old = NOW - timedelta(seconds=10)
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "concurrent-integrity", created_at=old))
    assert storage.claim_next_job("crashed-worker", 5, now=old) is not None
    storage.create_run(Run(
        id="concurrent-integrity-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=old,
    ))
    barrier = threading.Barrier(2)
    runners = [
        _runner(
            settings, MutableClock(), stale_after_seconds=1,
            storage_factory=lambda: BarrierStorage(
                SqliteStorage.open(settings.db_path), barrier, barrier_method="recovery",
            ),
        )
        for _ in range(2)
    ]

    results = _run_two_runners(runners)
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert sum(result.recovery.requeued_count for result in results) == 1
        assert sum(result.reaper.stopped_count for result in results) == 1
        assert reopened.get_job(job.id).status is JobStatus.QUEUED
        assert reopened.get_run("concurrent-integrity-run").status is RunStatus.STOPPED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


class FailingRecoveryStorage(RecordingStorage):
    def release_or_requeue_expired_leases(self, *, now=None, clock=None):
        raise RuntimeError("recovery failed")


class FailingReaperStorage(RecordingStorage):
    def reap_orphaned_stale_runs(self, stale_before, *, now=None, clock=None):
        raise RuntimeError("reaper failed")


class FailingCloseStorage(RecordingStorage):
    def close(self) -> None:
        self.events.append("close")
        raise RuntimeError("close failed")


class FailingRecoveryAndCloseStorage(FailingRecoveryStorage):
    def close(self) -> None:
        self.events.append("close")
        raise RuntimeError("close failed")


class FailingReaperAndCloseStorage(FailingReaperStorage):
    def close(self) -> None:
        self.events.append("close")
        raise RuntimeError("close failed")


class FailingWaiter:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool:
        self.calls += 1
        raise RuntimeError("wait failed")


def test_maintenance_stops_poll_after_recovery_error():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=99)
    runner = MaintenanceRunner(
        storage_factory=lambda: FailingRecoveryStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(RuntimeError, match="recovery failed"):
        runner.run_forever(interval_seconds=60)

    assert events == ["close"]
    assert waiter.calls == 0


def test_maintenance_stops_poll_after_reaper_error():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=99)
    runner = MaintenanceRunner(
        storage_factory=lambda: FailingReaperStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(RuntimeError, match="reaper failed"):
        runner.run_forever(interval_seconds=60)

    assert events == ["recovery", "close"]
    assert waiter.calls == 0


def test_maintenance_storage_factory_error_is_fail_closed():
    waiter = FailingWaiter()
    runner = MaintenanceRunner(
        storage_factory=lambda: (_ for _ in ()).throw(RuntimeError("factory failed")),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(RuntimeError, match="factory failed"):
        runner.run_forever(interval_seconds=60)

    assert waiter.calls == 0


def test_recovery_error_is_not_masked_by_storage_close_error():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=99)
    runner = MaintenanceRunner(
        storage_factory=lambda: FailingRecoveryAndCloseStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(MaintenanceCycleError) as captured:
        runner.run_forever(interval_seconds=60)

    error = captured.value
    assert isinstance(error.primary_error, RuntimeError)
    assert str(error.primary_error) == "recovery failed"
    assert isinstance(error.cleanup_error, RuntimeError)
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert "primary_error=RuntimeError: recovery failed" in str(error)
    assert "cleanup_error=RuntimeError: close failed" in str(error)
    assert events == ["close"]
    assert waiter.calls == 0


def test_reaper_error_is_not_masked_by_storage_close_error():
    events: list[str] = []
    waiter = SequenceWaiter(events, stop_after=99)
    runner = MaintenanceRunner(
        storage_factory=lambda: FailingReaperAndCloseStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(MaintenanceCycleError) as captured:
        runner.run_forever(interval_seconds=60)

    error = captured.value
    assert isinstance(error.primary_error, RuntimeError)
    assert str(error.primary_error) == "reaper failed"
    assert isinstance(error.cleanup_error, RuntimeError)
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert "primary_error=RuntimeError: reaper failed" in str(error)
    assert "cleanup_error=RuntimeError: close failed" in str(error)
    assert events == ["recovery", "close"]
    assert waiter.calls == 0


def test_successful_cycle_with_storage_close_error_is_failed():
    events: list[str] = []
    waiter = FailingWaiter()
    runner = MaintenanceRunner(
        storage_factory=lambda: FailingCloseStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(MaintenanceCycleError) as captured:
        runner.run_forever(interval_seconds=60)

    error = captured.value
    assert error.primary_error is None
    assert isinstance(error.cleanup_error, RuntimeError)
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.cleanup_error
    assert "Maintenance cleanup failed" in str(error)
    assert "cleanup_error=RuntimeError: close failed" in str(error)
    assert events == ["recovery", "reaper", "close"]
    assert waiter.calls == 0


def test_maintenance_waiter_error_stops_poll():
    events: list[str] = []
    waiter = FailingWaiter()
    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage(events),
        stale_after_seconds=5,
        clock=MutableClock(),
        waiter=waiter,
    )

    with pytest.raises(RuntimeError, match="wait failed"):
        runner.run_forever(interval_seconds=60)

    assert events == ["recovery", "reaper", "close"]
    assert waiter.calls == 1


def test_invalid_maintenance_configuration_fails_closed():
    for invalid in (0.0, -1.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            MaintenanceRunner(
                storage_factory=lambda: RecordingStorage([]),
                stale_after_seconds=invalid,
                clock=MutableClock(),
            )

    runner = MaintenanceRunner(
        storage_factory=lambda: RecordingStorage([]),
        stale_after_seconds=5,
        clock=MutableClock(),
    )
    for invalid in (0.0, -1.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            runner.run_forever(interval_seconds=invalid)

    with pytest.raises(SystemExit) as missing_interval:
        main(["maintain", "--poll", "--stale-after-seconds", "1"])
    assert missing_interval.value.code == 2
    with pytest.raises(SystemExit) as unexpected_interval:
        main([
            "maintain", "--once", "--interval-seconds", "1", "--stale-after-seconds", "1",
        ])
    assert unexpected_interval.value.code == 2


def test_maintenance_cli_once_uses_temp_database(settings, account, monkeypatch, capsys):
    setup = SqliteStorage.open(settings.db_path)
    setup.ensure_account(account)
    setup.create_run(Run(
        id="maintenance-cli-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    ))
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    assert main(["maintain", "--once", "--stale-after-seconds", "1"]) == 0

    verify = SqliteStorage.open(settings.db_path)
    assert "MAINTENANCE: checked=1 stopped=1" in capsys.readouterr().out
    assert verify.get_run("maintenance-cli-run").status is RunStatus.STOPPED
    assert verify.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


def test_maintenance_cli_poll_can_be_stopped_without_real_sleep(settings, monkeypatch, capsys):
    calls: list[float] = []

    class InterruptingMaintenanceRunner:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_forever(self, *, interval_seconds: float) -> None:
            calls.append(interval_seconds)
            raise KeyboardInterrupt

    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr("app.main.MaintenanceRunner", InterruptingMaintenanceRunner)

    assert main([
        "maintain", "--poll", "--interval-seconds", "60", "--stale-after-seconds", "1",
    ]) == 130

    assert calls == [60.0]
    assert "MAINTENANCE: interrupted; polling stopped." in capsys.readouterr().err


def test_maintenance_keyboard_interrupt_closes_open_storage(settings, monkeypatch, capsys):
    events: list[str] = []

    class InterruptingRecoveryStorage(RecordingStorage):
        def release_or_requeue_expired_leases(self, *, now=None, clock=None):
            self.events.append("recovery")
            raise KeyboardInterrupt("sk-ant-maintenance-test-secret")

    opened: list[InterruptingRecoveryStorage] = []

    def open_interrupting_storage(_db_path):
        storage = InterruptingRecoveryStorage(events)
        opened.append(storage)
        return storage

    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr("app.main.SqliteStorage.open", open_interrupting_storage)

    assert main([
        "maintain", "--poll", "--interval-seconds", "60", "--stale-after-seconds", "1",
    ]) == 130

    output = capsys.readouterr()
    assert len(opened) == 1
    assert events == ["recovery", "close"]
    assert "MAINTENANCE: interrupted; polling stopped." in output.err
    assert "Traceback" not in output.err
    assert "sk-ant-maintenance-test-secret" not in output.err


def test_reap_runs_cli_remains_backward_compatible(settings, account, monkeypatch, capsys):
    setup = SqliteStorage.open(settings.db_path)
    setup.ensure_account(account)
    setup.create_run(Run(
        id="legacy-reaper-cli-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    ))
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    assert main(["reap-runs", "--once", "--stale-after-seconds", "1"]) == 0

    verify = SqliteStorage.open(settings.db_path)
    assert "REAPER: checked=1 stopped=1" in capsys.readouterr().out
    assert verify.get_run("legacy-reaper-cli-run").status is RunStatus.STOPPED
    verify.close()


def test_maintenance_runs_with_worker_disabled_and_kill_switch(
    settings, storage, account, monkeypatch,
):
    old = NOW - timedelta(seconds=10)
    storage.ensure_account(account)
    for key, value in {
        "kill_switch": True,
        "worker_enabled": False,
        "safe_mode": True,
        "paid_actions_enabled": False,
        "browser_actions_enabled": False,
    }.items():
        storage.set_system_flag(key, value, updated_by="test", reason="maintenance", now=NOW)
    flags_before = _system_flag_rows(storage)
    job = storage.enqueue_job(_local_job(account, "flags-disabled", created_at=old))
    assert storage.claim_next_job("crashed-worker", 5, now=old) is not None
    storage.create_run(Run(
        id="flags-disabled-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=old,
    ))
    calls = _install_forbidden_execution_spies(monkeypatch)

    result = _runner(settings, MutableClock(), stale_after_seconds=1).run_once()

    assert result.recovery.requeued_count == 1
    assert result.reaper.stopped_count == 1
    assert storage.get_job(job.id).status is JobStatus.QUEUED
    assert storage.get_run("flags-disabled-run").status is RunStatus.STOPPED
    assert _system_flag_rows(storage) == flags_before
    _assert_no_execution_calls(calls)

    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _system_flag_rows(reopened) == flags_before
        assert reopened.get_job(job.id).status is JobStatus.QUEUED
        assert reopened.get_run("flags-disabled-run").status is RunStatus.STOPPED
    finally:
        reopened.close()
