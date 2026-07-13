"""Offline contracts for the minimal durable worker runtime (Stage 1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading

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
from app.scheduler.dispatcher import JobDispatcher
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
        schedule_reason="worker-test", earliest_run_at=NOW, created_at=NOW,
        max_attempts=max_attempts,
    )


def _research_job(account, topic: Topic, job_id: str, *, dry_run: bool = True) -> Job:
    return Job(
        id=job_id, account_id=account.id, kind=JobKind.RESEARCH, workflow=WorkflowType.RESEARCH,
        idempotency_key=f"key-{job_id}", topic_id=topic.id,
        payload={"account_id": account.id, "topic_id": topic.id, "dry_run": dry_run},
        schedule_reason="worker-test", earliest_run_at=NOW, created_at=NOW, max_attempts=2,
    )


def _worker(settings, storage: SqliteStorage, clock: Clock, *, owner: str = "worker-a", dispatcher=None,
            lease_seconds: int = 30) -> Worker:
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = dispatcher or JobDispatcher(
        settings=settings, storage=storage, policy=policy, clock=clock,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher, lease_owner=owner,
        lease_seconds=lease_seconds, clock=clock, sleeper=lambda _: None,
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
        schedule_reason="test", earliest_run_at=NOW, created_at=NOW, max_attempts=2,
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
