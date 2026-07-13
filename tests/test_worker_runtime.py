"""Offline contracts for the minimal durable worker runtime (Stage 1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading
from typing import Callable

import pytest

from app.orchestrator import runner
from app.core.clock import Clock
from app.main import main
from app.models import (
    Job,
    JobKind,
    JobStatus,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.research.fake_client import FakeResearchClient
from app.scheduler.dispatcher import DispatchError, JobDispatcher
from app.scheduler.heartbeat import HeartbeatGuard, HeartbeatWaiter
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


class MutableClock(Clock):
    def __init__(self, moment: datetime = NOW) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment

    def advance(self, seconds: int) -> None:
        self.moment += timedelta(seconds=seconds)


class ManualHeartbeatWaiter(HeartbeatWaiter):
    """Test-only trigger for a background heartbeat, without wall-clock sleep."""

    def __init__(self) -> None:
        self.waiting = threading.Event()
        self._condition = threading.Condition()
        self._triggers = 0

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool:
        del timeout_seconds
        with self._condition:
            self.waiting.set()
            while not stop_event.is_set() and self._triggers == 0:
                self._condition.wait()
            if stop_event.is_set():
                return True
            self._triggers -= 1
            return False

    def trigger(self) -> None:
        with self._condition:
            self._triggers += 1
            self._condition.notify_all()

    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()


class TrackingHeartbeatStorage:
    def __init__(self, storage: SqliteStorage, factory: "TrackingHeartbeatFactory") -> None:
        self._storage = storage
        self._factory = factory

    def heartbeat_job_lease(self, *args, **kwargs) -> None:
        self._factory.record_heartbeat()
        self._storage.heartbeat_job_lease(*args, **kwargs)
        self._factory.record_successful_heartbeat()

    def close(self) -> None:
        self._storage.close()
        self._factory.record_close()


class TrackingHeartbeatFactory:
    def __init__(self, db_path) -> None:
        self._db_path = db_path
        self._condition = threading.Condition()
        self.calls = 0
        self.successful_calls = 0
        self.closes = 0

    def __call__(self) -> TrackingHeartbeatStorage:
        return TrackingHeartbeatStorage(SqliteStorage.open(self._db_path), self)

    def record_heartbeat(self) -> None:
        with self._condition:
            self.calls += 1
            self._condition.notify_all()

    def record_close(self) -> None:
        with self._condition:
            self.closes += 1
            self._condition.notify_all()

    def record_successful_heartbeat(self) -> None:
        with self._condition:
            self.successful_calls += 1
            self._condition.notify_all()

    def wait_for_calls(self, count: int) -> bool:
        with self._condition:
            while self.calls < count:
                if not self._condition.wait(timeout=1):
                    return False
            return True

    def wait_for_successful_calls(self, count: int) -> bool:
        with self._condition:
            while self.successful_calls < count:
                if not self._condition.wait(timeout=1):
                    return False
            return True

    def wait_for_closes(self, count: int) -> bool:
        with self._condition:
            while self.closes < count:
                if not self._condition.wait(timeout=1):
                    return False
            return True


def _enable_offline_worker(storage: SqliteStorage, clock: Clock) -> None:
    for key, value in {
        "kill_switch": False,
        "worker_enabled": True,
        "safe_mode": False,
        "paid_actions_enabled": False,
        "browser_actions_enabled": False,
    }.items():
        storage.set_system_flag(key, value, updated_by="test", reason="offline", now=clock.now())


def _local_job(account, job_id: str, *, payload: dict | None = None, max_attempts: int = 2) -> Job:
    return Job(
        id=job_id, account_id=account.id, kind=JobKind.LOCAL, workflow=WorkflowType.ANALYTICS,
        idempotency_key=f"key-{job_id}", payload=payload or {"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW, created_at=NOW,
        max_attempts=max_attempts,
    )


def _research_job(account, topic: Topic, job_id: str, *, dry_run: bool = True) -> Job:
    return Job(
        id=job_id, account_id=account.id, kind=JobKind.RESEARCH, workflow=WorkflowType.RESEARCH,
        idempotency_key=f"key-{job_id}", topic_id=topic.id,
        payload={"account_id": account.id, "topic_id": topic.id, "dry_run": dry_run},
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW, created_at=NOW, max_attempts=2,
    )


def _worker(settings, storage: SqliteStorage, clock: Clock, *, owner: str = "worker-a", dispatcher=None,
            lease_seconds: int = 30, heartbeat_interval_seconds: float = 5.0,
            heartbeat_startup_timeout_seconds: float = 1.0,
            heartbeat_shutdown_timeout_seconds: float = 1.0,
            heartbeat_storage_factory=None, heartbeat_waiter_factory=None,
            heartbeat_ready_waiter=None, heartbeat_thread_joiner=None) -> Worker:
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = dispatcher or JobDispatcher(
        settings=settings, storage=storage, policy=policy, clock=clock,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher, lease_owner=owner,
        lease_seconds=lease_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_startup_timeout_seconds=heartbeat_startup_timeout_seconds,
        heartbeat_shutdown_timeout_seconds=heartbeat_shutdown_timeout_seconds,
        heartbeat_storage_factory=heartbeat_storage_factory or (
            lambda: SqliteStorage.open(settings.db_path)
        ),
        heartbeat_waiter_factory=heartbeat_waiter_factory or ManualHeartbeatWaiter,
        heartbeat_ready_waiter=heartbeat_ready_waiter or (
            lambda event, timeout: event.wait(timeout)
        ),
        heartbeat_thread_joiner=heartbeat_thread_joiner or (
            lambda thread, timeout: thread.join(timeout=timeout)
        ),
        clock=clock, sleeper=lambda _: None,
    )


def _selected_topic(storage: SqliteStorage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Why durable queues?", question="Why durable queues?",
        score=90, status=TopicStatus.SELECTED,
    ))


def test_worker_once_no_job(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)

    result = _worker(settings, storage, clock).run_once()

    assert result.status is WorkerIterationStatus.IDLE
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_worker_run_forever_sleeps_when_queue_is_empty(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    sleeps: list[float] = []
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = JobDispatcher(settings=settings, storage=storage, policy=policy, clock=clock)
    worker = Worker(
        storage=storage, policy=policy, dispatcher=dispatcher, lease_owner="loop-worker",
        lease_seconds=60, heartbeat_interval_seconds=20.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock, sleeper=sleeps.append,
    )

    worker.run_forever(poll_seconds=2.5, should_stop=lambda: bool(sleeps))

    assert sleeps == [2.5]


def test_worker_executes_local_job_once(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "local-once"))

    result = _worker(settings, storage, clock).run_once()

    assert result.status is WorkerIterationStatus.DONE
    completed = storage.get_job(job.id)
    assert completed.status is JobStatus.DONE
    assert completed.attempts == 1
    assert completed.started_at is not None and completed.finished_at is not None


def test_worker_executes_research_dry_run(settings, storage, account):
    clock = MutableClock()
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_research_job(account, topic, "research-dry"))

    result = _worker(settings, storage, clock).run_once()

    completed = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.DONE
    assert completed.status is JobStatus.DONE and completed.run_id is not None
    assert storage.get_run(completed.run_id).status is RunStatus.DRY_RUN
    assert storage.get_research_run(completed.run_id) is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=? AND dry_run=1", (completed.run_id,)
    ).fetchone()[0] == 1
    assert storage.list_topics(account.id)[0].status is TopicStatus.USED


def test_worker_rejects_research_real_mode(settings, storage, account):
    clock = MutableClock()
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_research_job(account, topic, "research-real", dry_run=False))

    result = _worker(settings, storage, clock).run_once()

    failed = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.FAILED
    assert failed.status is JobStatus.FAILED
    assert failed.run_id is None and failed.last_error == "Policy denied: PAID_ACTIONS_BLOCKED"
    assert storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_worker_fails_closed_when_worker_flag_missing(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    for key, value in {
        "kill_switch": False, "safe_mode": False,
        "paid_actions_enabled": False, "browser_actions_enabled": False,
    }.items():
        storage.set_system_flag(key, value, now=clock.now())
    job = storage.enqueue_job(_local_job(account, "missing-worker-flag"))

    result = _worker(settings, storage, clock).run_once()

    assert result.status is WorkerIterationStatus.BLOCKED
    assert result.detail == "RUNTIME_FLAG_INVALID"
    assert storage.get_job(job.id).status is JobStatus.QUEUED


def test_worker_fails_closed_when_flag_json_invalid(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.conn.execute(
        "UPDATE system_flags SET value_json='\"not-a-boolean\"' WHERE key='safe_mode'"
    )
    storage.conn.commit()
    job = storage.enqueue_job(_local_job(account, "invalid-json-flag"))

    result = _worker(settings, storage, clock).run_once()

    assert result.status is WorkerIterationStatus.BLOCKED
    assert storage.get_job(job.id).status is JobStatus.QUEUED


def test_worker_stops_when_kill_switch_enabled(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.set_system_flag("kill_switch", True, now=clock.now())
    job = storage.enqueue_job(_local_job(account, "kill-switch"))

    assert _worker(settings, storage, clock).run_once().status is WorkerIterationStatus.BLOCKED
    assert storage.get_job(job.id).status is JobStatus.QUEUED


def test_worker_stops_in_safe_mode(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.set_system_flag("safe_mode", True, now=clock.now())
    job = storage.enqueue_job(_local_job(account, "safe-mode"))

    assert _worker(settings, storage, clock).run_once().status is WorkerIterationStatus.BLOCKED
    assert storage.get_job(job.id).status is JobStatus.QUEUED


def test_worker_reads_flags_each_iteration(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    first = storage.enqueue_job(_local_job(account, "flag-first"))
    second = storage.enqueue_job(_local_job(account, "flag-second"))
    worker = _worker(settings, storage, clock)

    assert worker.run_once().status is WorkerIterationStatus.DONE
    storage.set_system_flag("worker_enabled", False, now=clock.now())
    assert worker.run_once().status is WorkerIterationStatus.BLOCKED
    assert storage.get_job(first.id).status is JobStatus.DONE
    assert storage.get_job(second.id).status is JobStatus.QUEUED


def test_unsupported_job_fails_without_retry(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = Job(
        id="unsupported", account_id=account.id, kind=JobKind.LOCAL, workflow=WorkflowType.TOPIC,
        idempotency_key="unsupported", payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW, created_at=NOW, max_attempts=2,
    )
    storage.enqueue_job(job)

    result = _worker(settings, storage, clock).run_once()

    failed = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.FAILED
    assert failed.status is JobStatus.FAILED and failed.attempts == 1
    assert failed.last_error == "LOCAL jobs support only the ANALYTICS workflow."


def test_invalid_payload_fails_without_execution(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(
        account, "invalid-payload", payload={"dry_run": True, "action": "anything"},
    ))

    result = _worker(settings, storage, clock).run_once()

    failed = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.FAILED
    assert failed.status is JobStatus.FAILED and failed.run_id is None
    assert failed.last_error == "LOCAL job payload does not match the offline noop contract."


def test_two_workers_do_not_execute_same_job(settings, account):
    seed = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    seed.ensure_account(account)
    _enable_offline_worker(seed, clock)
    job = seed.enqueue_job(_local_job(account, "two-workers"))
    seed.close()

    barrier = threading.Barrier(2)
    dispatch_count = 0
    count_lock = threading.Lock()
    results: list[WorkerIterationStatus] = []
    failures: list[BaseException] = []

    class CountingDispatcher:
        def __init__(self, delegate: JobDispatcher) -> None:
            self.delegate = delegate

        def dispatch(self, *args, **kwargs):
            nonlocal dispatch_count
            with count_lock:
                dispatch_count += 1
            return self.delegate.dispatch(*args, **kwargs)

    def run(owner: str) -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            policy = PolicyEngine(settings, store, clock)
            delegate = JobDispatcher(settings=settings, storage=store, policy=policy, clock=clock)
            worker = _worker(settings, store, clock, owner=owner, dispatcher=CountingDispatcher(delegate))
            barrier.wait()
            results.append(worker.run_once().status)
        except BaseException as exc:
            failures.append(exc)
        finally:
            store.close()

    threads = [threading.Thread(target=run, args=(owner,)) for owner in ("worker-1", "worker-2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verify = SqliteStorage.open(settings.db_path)
    assert failures == []
    assert results.count(WorkerIterationStatus.DONE) == 1
    assert results.count(WorkerIterationStatus.IDLE) == 1
    assert dispatch_count == 1
    assert verify.get_job(job.id).status is JobStatus.DONE
    assert verify.get_job(job.id).attempts == 1
    assert verify.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


def test_worker_restart_recovers_safe_expired_job(settings, account):
    initial = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    initial.ensure_account(account)
    _enable_offline_worker(initial, clock)
    job = initial.enqueue_job(_local_job(account, "restart-safe"))
    lease = initial.claim_next_job("crashed-worker", 5, now=clock.now())
    assert lease is not None
    initial.mark_job_running(job.id, "crashed-worker", now=clock.now())
    initial.close()

    clock.advance(6)
    recovered = SqliteStorage.open(settings.db_path)
    assert recovered.release_or_requeue_expired_leases(now=clock.now()).requeued_count == 1
    result = _worker(settings, recovered, clock, owner="restarted-worker").run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert recovered.get_job(job.id).status is JobStatus.DONE
    assert recovered.get_job(job.id).attempts == 2
    assert recovered.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    recovered.close()


def test_research_job_with_run_id_is_not_dispatched_again(settings, account):
    initial = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    topic = _selected_topic(initial, account)
    _enable_offline_worker(initial, clock)
    job = initial.enqueue_job(_research_job(account, topic, "research-recovery-attached"))
    assert initial.claim_next_job("crashed-worker", 5, now=clock.now()) is not None
    initial.mark_job_running(job.id, "crashed-worker", now=clock.now())
    run_id = "research-recovery-attached-run"
    initial.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.DRY_RUN,
    ))
    initial.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.SINGLE, status=ResearchRunStatus.PENDING,
    ))
    initial.attach_job_run(job.id, "crashed-worker", run_id, now=clock.now())
    initial.close()

    clock.advance(6)
    recovered = SqliteStorage.open(settings.db_path)
    assert recovered.release_or_requeue_expired_leases(now=clock.now()).needs_verification_count == 1
    dispatches = 0

    class CountingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatches
            dispatches += 1

    result = _worker(
        settings, recovered, clock, owner="restarted-worker", dispatcher=CountingDispatcher(),
    ).run_once()

    persisted = recovered.get_job(job.id)
    assert result.status is WorkerIterationStatus.IDLE
    assert dispatches == 0
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    assert persisted.last_error.startswith("RESEARCH_RUN_RECONCILIATION_REQUIRED:")
    assert recovered.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    recovered.close()


def test_reaper_does_not_dispatch_or_resume_research(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_research_job(account, topic, "reaper-no-resume"))
    assert storage.claim_next_job("crashed-worker", 5, now=clock.now()) is not None
    run_id = "reaper-no-resume-run"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=clock.now() - timedelta(seconds=10),
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.SINGLE, status=ResearchRunStatus.PENDING,
    ))
    storage.attach_job_run(job.id, "crashed-worker", run_id, now=clock.now())
    clock.advance(6)
    storage.release_or_requeue_expired_leases(now=clock.now())
    storage.reap_orphaned_stale_runs(clock.now() - timedelta(seconds=1), now=clock.now())
    dispatches = 0

    class CountingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatches
            dispatches += 1

    result = _worker(
        settings, storage, clock, owner="restarted-worker", dispatcher=CountingDispatcher(),
    ).run_once()

    assert result.status is WorkerIterationStatus.IDLE
    assert dispatches == 0
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.get_run(run_id).status is RunStatus.STOPPED
    storage.close()


def test_reaper_cli_uses_temp_database(settings, account, monkeypatch, capsys):
    setup = SqliteStorage.open(settings.db_path)
    setup.ensure_account(account)
    setup.create_run(Run(
        id="reaper-cli-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    ))
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    assert main(["reap-runs", "--once", "--stale-after-seconds", "1"]) == 0

    output = capsys.readouterr().out
    verify = SqliteStorage.open(settings.db_path)
    assert "REAPER: checked=1 stopped=1" in output
    assert verify.get_run("reaper-cli-run").status is RunStatus.STOPPED
    assert verify.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


def test_worker_does_not_retry_external_effect_job(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "external-effect"))
    assert storage.claim_next_job("crashed-worker", 5, now=clock.now()) is not None
    storage.mark_job_running(job.id, "crashed-worker", now=clock.now())
    storage.mark_job_external_effect_started(job.id, "crashed-worker", now=clock.now())
    clock.advance(6)
    assert storage.release_or_requeue_expired_leases(now=clock.now()).needs_verification_count == 1

    result = _worker(settings, storage, clock, owner="restarted-worker").run_once()

    assert result.status is WorkerIterationStatus.IDLE
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION


def test_worker_heartbeat_keeps_lease_alive(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "heartbeat"))

    class LongLocalDispatcher:
        def dispatch(self, _job, *, lease_owner, heartbeat):
            clock.advance(6)
            heartbeat()
            clock.advance(6)
            heartbeat()

    result = _worker(
        settings, storage, clock, dispatcher=LongLocalDispatcher(), lease_seconds=10,
    ).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert storage.get_job(job.id).status is JobStatus.DONE


def test_lost_lease_prevents_terminal_success(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "lost-lease"))

    class LeaseLosingDispatcher:
        def dispatch(self, _job, *, lease_owner, heartbeat):
            clock.advance(11)

    result = _worker(
        settings, storage, clock, dispatcher=LeaseLosingDispatcher(), lease_seconds=10,
    ).run_once()

    persisted = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert persisted.status is JobStatus.RUNNING
    assert persisted.finished_at is None


def test_terminal_job_is_not_dispatched_again(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "terminal-once"))
    calls = 0

    class CountingDispatcher:
        def dispatch(self, _job, *, lease_owner, heartbeat):
            nonlocal calls
            calls += 1
            heartbeat()

    worker = _worker(settings, storage, clock, dispatcher=CountingDispatcher())
    assert worker.run_once().status is WorkerIterationStatus.DONE
    assert worker.run_once().status is WorkerIterationStatus.IDLE
    assert storage.get_job(job.id).status is JobStatus.DONE
    assert calls == 1


def test_worker_cli_once_uses_temp_database(settings, account, monkeypatch):
    setup = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    setup.ensure_account(account)
    _enable_offline_worker(setup, clock)
    job = setup.enqueue_job(_local_job(account, "cli-once"))
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    assert main(["worker", "--once"]) == 0

    verify = SqliteStorage.open(settings.db_path)
    assert verify.get_job(job.id).status is JobStatus.DONE
    assert verify.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


def _run_worker_async(worker_factory: Callable[[], Worker]):
    results = []
    failures: list[BaseException] = []

    def run() -> None:
        worker = worker_factory()
        try:
            results.append(worker.run_once())
        except BaseException as exc:
            failures.append(exc)
        finally:
            worker._storage.close()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, results, failures


def _thread_worker_factory(settings, clock: Clock, **kwargs) -> Callable[[], Worker]:
    """Open the primary SQLite connection inside the worker's owning thread."""

    return lambda: _worker(settings, SqliteStorage.open(settings.db_path), clock, **kwargs)


def _join_worker(thread, results, failures):
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert failures == []
    assert len(results) == 1
    return results[0]


def test_periodic_heartbeat_extends_lease_during_dispatch(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "periodic-extends"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=2)

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=2)
    assert waiter.waiting.wait(timeout=2)
    initial_expiry = storage.get_job(job.id).lease_expires_at

    clock.advance(3)
    waiter.trigger()
    assert factory.wait_for_successful_calls(1)
    first_expiry = storage.get_job(job.id).lease_expires_at
    clock.advance(3)
    waiter.trigger()
    assert factory.wait_for_successful_calls(2)
    assert storage.get_job(job.id).lease_expires_at > first_expiry > initial_expiry

    release_dispatch.set()
    result = _join_worker(thread, results, failures)
    assert result.status is WorkerIterationStatus.DONE
    assert storage.get_job(job.id).status is JobStatus.DONE
    assert factory.wait_for_closes(1)


def test_periodic_heartbeat_prevents_recovery_during_long_dispatch(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "periodic-prevents-recovery"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()
    dispatches = 0

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatches
            dispatches += 1
            dispatch_started.set()
            assert release_dispatch.wait(timeout=2)

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=2)
    assert waiter.waiting.wait(timeout=2)
    clock.advance(8)
    waiter.trigger()
    assert factory.wait_for_successful_calls(1)
    clock.advance(3)  # past the original 10-second lease, before the renewed expiry

    recovery = SqliteStorage.open(settings.db_path)
    assert recovery.release_or_requeue_expired_leases(now=clock.now()).model_dump() == {
        "requeued_count": 0, "needs_verification_count": 0, "failed_count": 0,
    }
    recovery.close()
    assert storage.get_job(job.id).status is JobStatus.RUNNING

    release_dispatch.set()
    result = _join_worker(thread, results, failures)
    assert result.status is WorkerIterationStatus.DONE
    assert dispatches == 1
    assert storage.get_job(job.id).status is JobStatus.DONE


def test_lost_lease_during_dispatch_prevents_done(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "periodic-lost-lease"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=2)

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=2)
    assert waiter.waiting.wait(timeout=2)
    clock.advance(11)
    recovery = SqliteStorage.open(settings.db_path)
    assert recovery.release_or_requeue_expired_leases(now=clock.now()).requeued_count == 1
    recovery.close()
    waiter.trigger()
    assert factory.wait_for_calls(1)

    release_dispatch.set()
    result = _join_worker(thread, results, failures)
    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert storage.get_job(job.id).status is JobStatus.QUEUED
    assert storage.get_job(job.id).finished_at is None


def test_foreign_owner_heartbeat_is_rejected(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "foreign-heartbeat"))
    assert storage.claim_next_job("owner-a", 10, now=clock.now()) is not None
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    guard = HeartbeatGuard(
        job_id=job.id, lease_owner="owner-b", lease_seconds=10, interval_seconds=3.0,
        startup_timeout_seconds=1.0, shutdown_timeout_seconds=1.0,
        storage_factory=factory, now=clock.now, waiter=waiter,
    )

    guard.start()
    assert waiter.waiting.wait(timeout=2)
    waiter.trigger()
    assert factory.wait_for_calls(1)
    guard.stop()

    assert guard.lost_lease is not None
    assert not guard.thread_is_alive
    assert storage.get_job(job.id).status is JobStatus.LEASED


def test_expired_lease_is_not_revived_by_guard(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    job = storage.enqueue_job(_local_job(account, "expired-heartbeat"))
    assert storage.claim_next_job("owner-a", 10, now=clock.now()) is not None
    original_expiry = storage.get_job(job.id).lease_expires_at
    clock.advance(11)
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    guard = HeartbeatGuard(
        job_id=job.id, lease_owner="owner-a", lease_seconds=10, interval_seconds=3.0,
        startup_timeout_seconds=1.0, shutdown_timeout_seconds=1.0,
        storage_factory=factory, now=clock.now, waiter=waiter,
    )

    guard.start()
    assert waiter.waiting.wait(timeout=2)
    waiter.trigger()
    assert factory.wait_for_calls(1)
    guard.stop()

    assert guard.lost_lease is not None
    persisted = storage.get_job(job.id)
    assert persisted.status is JobStatus.LEASED
    assert persisted.lease_expires_at == original_expiry


def test_heartbeat_guard_stops_after_success(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.enqueue_job(_local_job(account, "guard-stops-success"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)

    result = _worker(
        settings, storage, clock, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    ).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert factory.wait_for_closes(1)
    assert factory.calls == 0


def test_heartbeat_guard_stops_after_dispatch_failure(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-stops-failure"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)

    class FailingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            raise DispatchError("planned failure")

    result = _worker(
        settings, storage, clock, dispatcher=FailingDispatcher(),
        heartbeat_storage_factory=factory, heartbeat_waiter_factory=lambda: waiter,
    ).run_once()

    assert result.status is WorkerIterationStatus.FAILED
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert factory.wait_for_closes(1)


def test_heartbeat_guard_stops_after_lost_lease(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-stops-lost"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=2)

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=2)
    clock.advance(11)
    recovery = SqliteStorage.open(settings.db_path)
    recovery.release_or_requeue_expired_leases(now=clock.now())
    recovery.close()
    waiter.trigger()
    assert factory.wait_for_calls(1)
    release_dispatch.set()

    assert _join_worker(thread, results, failures).status is WorkerIterationStatus.LOST_LEASE
    assert factory.wait_for_closes(1)


def test_dispatch_exception_and_heartbeat_failure_do_not_mask_lost_lease(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.enqueue_job(_local_job(account, "lost-lease-priority"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class FailingAfterReleaseDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=2)
            raise DispatchError("dispatch also failed")

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=FailingAfterReleaseDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=2)
    clock.advance(11)
    recovery = SqliteStorage.open(settings.db_path)
    recovery.release_or_requeue_expired_leases(now=clock.now())
    recovery.close()
    waiter.trigger()
    assert factory.wait_for_calls(1)
    release_dispatch.set()

    assert _join_worker(thread, results, failures).status is WorkerIterationStatus.LOST_LEASE


def test_two_workers_still_execute_job_exactly_once_with_periodic_heartbeat(settings, account):
    seed = SqliteStorage.open(settings.db_path)
    clock = MutableClock()
    seed.ensure_account(account)
    _enable_offline_worker(seed, clock)
    job = seed.enqueue_job(_local_job(account, "two-workers-periodic"))
    seed.close()

    barrier = threading.Barrier(2)
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()
    count_lock = threading.Lock()
    dispatch_count = 0
    results: list[WorkerIterationStatus] = []
    failures: list[BaseException] = []

    class FirstDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatch_count
            with count_lock:
                dispatch_count += 1
            dispatch_started.set()
            barrier.wait()
            assert release_dispatch.wait(timeout=2)

    def first_worker() -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            worker = _worker(
                settings, store, clock, owner="worker-1", dispatcher=FirstDispatcher(),
                lease_seconds=10, heartbeat_interval_seconds=3.0,
                heartbeat_storage_factory=factory, heartbeat_waiter_factory=lambda: waiter,
            )
            results.append(worker.run_once().status)
        except BaseException as exc:
            failures.append(exc)
        finally:
            store.close()

    def second_worker() -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(_worker(settings, store, clock, owner="worker-2").run_once().status)
        except BaseException as exc:
            failures.append(exc)
        finally:
            store.close()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    assert dispatch_started.wait(timeout=2)
    second.start()
    assert waiter.waiting.wait(timeout=2)
    clock.advance(3)
    waiter.trigger()
    assert factory.wait_for_successful_calls(1)
    release_dispatch.set()
    first.join(timeout=2)
    second.join(timeout=2)

    verify = SqliteStorage.open(settings.db_path)
    assert not first.is_alive() and not second.is_alive()
    assert failures == []
    assert results.count(WorkerIterationStatus.DONE) == 1
    assert results.count(WorkerIterationStatus.IDLE) == 1
    assert dispatch_count == 1
    assert verify.get_job(job.id).status is JobStatus.DONE
    assert verify.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


def test_no_heartbeat_after_terminalization(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.enqueue_job(_local_job(account, "no-heartbeat-terminal"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)

    assert _worker(
        settings, storage, clock, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    ).run_once().status is WorkerIterationStatus.DONE
    assert factory.wait_for_closes(1)
    calls_before = factory.calls
    waiter.trigger()
    assert factory.calls == calls_before


@pytest.mark.parametrize(
    ("lease_seconds", "heartbeat_interval_seconds"),
    [(0, 1.0), (10, 0.0), (10, -1.0), (10, 10.0), (10, 11.0)],
)
def test_invalid_heartbeat_configuration_fails_closed(
    settings, storage, account, lease_seconds, heartbeat_interval_seconds,
):
    clock = MutableClock()
    with pytest.raises(ValueError):
        _worker(
            settings, storage, clock, lease_seconds=lease_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )


def test_worker_no_job_does_not_start_heartbeat_guard(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    factory_calls = 0

    def forbidden_factory():
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("heartbeat guard must not start without a job")

    result = _worker(
        settings, storage, clock, heartbeat_storage_factory=forbidden_factory,
    ).run_once()

    assert result.status is WorkerIterationStatus.IDLE
    assert factory_calls == 0


def test_worker_policy_denial_does_not_start_heartbeat_guard(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    storage.set_system_flag("kill_switch", True, updated_by="test", reason="deny", now=clock.now())
    job = storage.enqueue_job(_local_job(account, "policy-denial-no-guard"))
    factory_calls = 0

    def forbidden_factory():
        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("heartbeat guard must not start after policy denial")

    result = _worker(
        settings, storage, clock, heartbeat_storage_factory=forbidden_factory,
    ).run_once()

    assert result.status is WorkerIterationStatus.BLOCKED
    assert storage.get_job(job.id).status is JobStatus.QUEUED
    assert factory_calls == 0


def test_research_dry_run_uses_periodic_heartbeat(settings, storage, account, monkeypatch):
    clock = MutableClock()
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_research_job(account, topic, "research-periodic"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    client_entered = threading.Event()
    release_client = threading.Event()

    class BlockingFakeResearchClient(FakeResearchClient):
        def run_research(self, plan):
            client_entered.set()
            assert release_client.wait(timeout=2)
            return super().run_research(plan)

    fake_client = BlockingFakeResearchClient("good")
    monkeypatch.setattr(runner, "_build_research_client", lambda *_args, **_kwargs: fake_client)
    def worker_factory() -> Worker:
        worker_storage = SqliteStorage.open(settings.db_path)
        policy = PolicyEngine(settings, worker_storage, clock)
        dispatcher = JobDispatcher(
            settings=settings, storage=worker_storage, policy=policy, clock=clock,
        )
        return _worker(
            settings, worker_storage, clock, dispatcher=dispatcher, lease_seconds=10,
            heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
            heartbeat_waiter_factory=lambda: waiter,
        )

    thread, results, failures = _run_worker_async(worker_factory)
    assert client_entered.wait(timeout=2)
    assert waiter.waiting.wait(timeout=2)
    clock.advance(3)
    waiter.trigger()
    assert factory.wait_for_successful_calls(1)
    release_client.set()

    result = _join_worker(thread, results, failures)
    completed = storage.get_job(job.id)
    assert result.status is WorkerIterationStatus.DONE
    assert completed.status is JobStatus.DONE and completed.run_id is not None
    assert storage.get_run(completed.run_id).status is RunStatus.DRY_RUN


def test_heartbeat_guard_start_timeout_fails_closed(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-start-timeout"))
    factory_started = threading.Event()
    release_factory = threading.Event()
    factory_closed = threading.Event()
    join_timeouts: list[float] = []
    dispatches = 0

    class DelayedStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            raise AssertionError("a released start-timeout guard must not heartbeat")

        def close(self):
            factory_closed.set()

    def blocked_factory():
        factory_started.set()
        assert release_factory.wait(timeout=1)
        return DelayedStorage()

    class CountingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatches
            dispatches += 1

    def timeout_ready_waiter(_event, _timeout):
        assert factory_started.wait(timeout=1)
        return False

    result = _worker(
        settings, storage, clock, dispatcher=CountingDispatcher(),
        heartbeat_storage_factory=blocked_factory,
        heartbeat_ready_waiter=timeout_ready_waiter,
        heartbeat_thread_joiner=lambda _thread, timeout: join_timeouts.append(timeout),
    ).run_once()

    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_START_TIMEOUT"
    assert dispatches == 0
    assert join_timeouts and all(timeout > 0 for timeout in join_timeouts)
    release_factory.set()
    assert factory_closed.wait(timeout=1)
    assert storage.get_job(job.id).status is JobStatus.RUNNING


def test_start_timeout_thread_exits_after_factory_is_released():
    factory_started = threading.Event()
    release_factory = threading.Event()
    factory_closed = threading.Event()
    heartbeat_calls = 0
    join_timeouts: list[float] = []

    class DelayedStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            nonlocal heartbeat_calls
            heartbeat_calls += 1

        def close(self):
            factory_closed.set()

    def blocked_factory():
        factory_started.set()
        assert release_factory.wait(timeout=1)
        return DelayedStorage()

    def timeout_ready_waiter(_event, _timeout):
        assert factory_started.wait(timeout=1)
        return False

    guard = HeartbeatGuard(
        job_id="released-start-timeout", lease_owner="worker-a", lease_seconds=10,
        interval_seconds=3.0, startup_timeout_seconds=1.0, shutdown_timeout_seconds=1.0,
        storage_factory=blocked_factory, now=lambda: NOW, waiter=ManualHeartbeatWaiter(),
        ready_waiter=timeout_ready_waiter,
        thread_joiner=lambda _thread, timeout: join_timeouts.append(timeout),
    )

    guard.start()
    assert guard.failure_code == "HEARTBEAT_GUARD_START_TIMEOUT"
    assert guard.thread_is_alive
    release_factory.set()
    assert factory_closed.wait(timeout=1)
    assert not guard.thread_is_alive
    assert heartbeat_calls == 0
    assert join_timeouts and all(timeout > 0 for timeout in join_timeouts)


def _shutdown_timeout_result(settings, storage, account, *, dispatch_error: Exception | None = None):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, f"shutdown-timeout-{dispatch_error is not None}"))
    waiter = ManualHeartbeatWaiter()
    heartbeat_entered = threading.Event()
    release_heartbeat = threading.Event()
    storage_closed = threading.Event()
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()
    join_timeouts: list[float] = []

    class BlockingStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            heartbeat_entered.set()
            assert release_heartbeat.wait(timeout=1)

        def close(self):
            storage_closed.set()

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=1)
            if dispatch_error is not None:
                raise dispatch_error

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=BlockingStorage,
        heartbeat_waiter_factory=lambda: waiter,
        heartbeat_thread_joiner=lambda _thread, timeout: join_timeouts.append(timeout),
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=1)
    assert waiter.waiting.wait(timeout=1)
    waiter.trigger()
    assert heartbeat_entered.wait(timeout=1)
    release_dispatch.set()
    result = _join_worker(thread, results, failures)
    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_SHUTDOWN_TIMEOUT"
    assert storage.get_job(job.id).status is JobStatus.RUNNING
    assert join_timeouts and all(timeout > 0 for timeout in join_timeouts)
    release_heartbeat.set()
    assert storage_closed.wait(timeout=1)
    return result


def test_heartbeat_guard_shutdown_timeout_prevents_done(settings, storage, account):
    _shutdown_timeout_result(settings, storage, account)


def test_dispatch_success_does_not_mask_guard_shutdown_timeout(settings, storage, account):
    _shutdown_timeout_result(settings, storage, account)


def test_heartbeat_storage_factory_exception_blocks_dispatch(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-factory-error"))
    dispatches = 0

    class CountingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            nonlocal dispatches
            dispatches += 1

    def broken_factory():
        raise RuntimeError("factory failure")

    result = _worker(
        settings, storage, clock, dispatcher=CountingDispatcher(),
        heartbeat_storage_factory=broken_factory,
    ).run_once()

    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_START_FAILURE"
    assert dispatches == 0
    assert storage.get_job(job.id).status is JobStatus.RUNNING


def test_unexpected_heartbeat_storage_error_prevents_done(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-heartbeat-error"))
    waiter = ManualHeartbeatWaiter()
    heartbeat_called = threading.Event()
    storage_closed = threading.Event()
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class FailingStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            heartbeat_called.set()
            raise RuntimeError("heartbeat storage failure")

        def close(self):
            storage_closed.set()

    class BlockingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=1)

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=BlockingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=FailingStorage,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=1)
    assert waiter.waiting.wait(timeout=1)
    waiter.trigger()
    assert heartbeat_called.wait(timeout=1)
    assert storage_closed.wait(timeout=1)
    release_dispatch.set()

    result = _join_worker(thread, results, failures)
    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_HEARTBEAT_FAILURE"
    assert storage.get_job(job.id).status is JobStatus.RUNNING


def test_heartbeat_storage_close_error_is_fail_closed(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-close-error"))

    class CloseFailingStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            raise AssertionError("no periodic heartbeat is needed in this scenario")

        def close(self):
            raise RuntimeError("close failure")

    result = _worker(
        settings, storage, clock, heartbeat_storage_factory=CloseFailingStorage,
    ).run_once()

    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_CLEANUP_FAILURE"
    assert storage.get_job(job.id).status is JobStatus.RUNNING


def test_heartbeat_waiter_wake_error_does_not_block_shutdown(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "guard-wake-error"))
    release_waiter = threading.Event()
    storage_closed = threading.Event()
    join_timeouts: list[float] = []

    class WakeFailingWaiter:
        def __init__(self) -> None:
            self.waiting = threading.Event()

        def wait(self, _stop_event, _timeout_seconds):
            self.waiting.set()
            assert release_waiter.wait(timeout=1)
            return True

        def wake(self):
            raise RuntimeError("wake failure")

    class NoopStorage:
        def heartbeat_job_lease(self, *_args, **_kwargs):
            raise AssertionError("blocked waiter must prevent heartbeat")

        def close(self):
            storage_closed.set()

    waiter = WakeFailingWaiter()

    class WaitingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            assert waiter.waiting.wait(timeout=1)

    result = _worker(
        settings, storage, clock, dispatcher=WaitingDispatcher(),
        heartbeat_storage_factory=NoopStorage, heartbeat_waiter_factory=lambda: waiter,
        heartbeat_thread_joiner=lambda _thread, timeout: join_timeouts.append(timeout),
    ).run_once()

    assert result.status is WorkerIterationStatus.LOST_LEASE
    assert result.detail == "HEARTBEAT_GUARD_SHUTDOWN_TIMEOUT"
    assert join_timeouts and all(timeout > 0 for timeout in join_timeouts)
    assert storage.get_job(job.id).status is JobStatus.RUNNING
    release_waiter.set()
    assert storage_closed.wait(timeout=1)


def test_dispatch_failure_does_not_mask_lost_lease(settings, storage, account):
    clock = MutableClock()
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(_local_job(account, "lost-lease-dispatch-failure"))
    waiter = ManualHeartbeatWaiter()
    factory = TrackingHeartbeatFactory(settings.db_path)
    dispatch_started = threading.Event()
    release_dispatch = threading.Event()

    class FailingDispatcher:
        def dispatch(self, *_args, **_kwargs):
            dispatch_started.set()
            assert release_dispatch.wait(timeout=1)
            raise DispatchError("dispatch failure")

    worker_factory = _thread_worker_factory(
        settings, clock, dispatcher=FailingDispatcher(), lease_seconds=10,
        heartbeat_interval_seconds=3.0, heartbeat_storage_factory=factory,
        heartbeat_waiter_factory=lambda: waiter,
    )
    thread, results, failures = _run_worker_async(worker_factory)
    assert dispatch_started.wait(timeout=1)
    assert waiter.waiting.wait(timeout=1)
    clock.advance(11)
    recovery = SqliteStorage.open(settings.db_path)
    assert recovery.release_or_requeue_expired_leases(now=clock.now()).requeued_count == 1
    recovery.close()
    waiter.trigger()
    assert factory.wait_for_calls(1)
    release_dispatch.set()

    assert _join_worker(thread, results, failures).status is WorkerIterationStatus.LOST_LEASE
    assert storage.get_job(job.id).status is JobStatus.QUEUED


def test_no_unbounded_join_on_any_guard_exit():
    join_timeouts: list[float] = []
    guard = HeartbeatGuard(
        job_id="bounded-join", lease_owner="worker-a", lease_seconds=10,
        interval_seconds=3.0, startup_timeout_seconds=1.0, shutdown_timeout_seconds=1.0,
        storage_factory=lambda: type("Storage", (), {
            "heartbeat_job_lease": lambda *_args, **_kwargs: None,
            "close": lambda _self: None,
        })(),
        now=lambda: NOW, waiter=ManualHeartbeatWaiter(),
        thread_joiner=lambda thread, timeout: (
            join_timeouts.append(timeout), thread.join(timeout=timeout)
        )[1],
    )

    guard.start()
    guard.stop()

    assert not guard.thread_is_alive
    assert join_timeouts and all(timeout > 0 for timeout in join_timeouts)


@pytest.mark.parametrize(
    ("startup_timeout_seconds", "shutdown_timeout_seconds"),
    [
        (0.0, 1.0), (-1.0, 1.0), (float("nan"), 1.0), (float("inf"), 1.0),
        (1.0, 0.0), (1.0, -1.0), (1.0, float("nan")), (1.0, float("inf")),
    ],
)
def test_invalid_guard_timeouts_fail_closed(
    settings, storage, startup_timeout_seconds, shutdown_timeout_seconds,
):
    with pytest.raises(ValueError):
        _worker(
            settings, storage, MutableClock(),
            heartbeat_startup_timeout_seconds=startup_timeout_seconds,
            heartbeat_shutdown_timeout_seconds=shutdown_timeout_seconds,
        )
