"""Końcowe, offline testy restart acceptance dla Etapu 1.

Każdy restart odrzuca poprzedni runtime i ponownie otwiera plikową SQLite.
Kontrolowane ``ProcessCrash`` dziedziczy bezpośrednio po ``BaseException``, więc
symuluje utratę procesu bez wejścia w zwykłą terminalizację błędu workera.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import threading

import pytest

from app.core.clock import Clock
from app.llm.base import Usage
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    ResearchCard,
    Topic,
    TopicStatus,
    ResearchJobExecution,
    RunStatus,
    Source,
    WorkflowType,
)
from app.orchestrator import runner
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import DispatchContractError, DispatchResult, JobDispatcher
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.maintenance import MaintenanceRunner
from app.scheduler.scheduling import EditorialWindow, SchedulingPolicy
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from app.ports.storage import (
    JobRunRelationError,
    LifecycleTransitionError,
    StaleJobExecutionError,
)
from app.research.fake_client import FakeResearchClient
from app.research.base import ResearchError


UTC = timezone.utc
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class ProcessCrash(BaseException):
    """Test-only odpowiednik nagłej utraty procesu."""


class MutableUtcClock(Clock):
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class FailpointConnection:
    """Testowy proxy SQLite: awaria jest wewnątrz jednej transakcji adaptera."""

    def __init__(
        self,
        delegate,
        *,
        sql_fragment: str | None = None,
        crash_after_commit: bool = False,
        arm_commit_after_sql_fragment: str | None = None,
        crash_after_sql_fragment: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._sql_fragment = sql_fragment
        self._crash_after_commit = crash_after_commit
        self._arm_commit_after_sql_fragment = arm_commit_after_sql_fragment
        self._crash_after_sql_fragment = crash_after_sql_fragment
        self.trigger_count = 0

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def execute(self, sql, parameters=()):
        normalized_sql = " ".join(sql.split())
        if self._sql_fragment is not None and self._sql_fragment in " ".join(sql.split()):
            self._sql_fragment = None
            self.trigger_count += 1
            raise ProcessCrash("process lost inside atomic research initialization")
        if (
            self._arm_commit_after_sql_fragment is not None
            and self._arm_commit_after_sql_fragment in normalized_sql
        ):
            self._arm_commit_after_sql_fragment = None
            self._crash_after_commit = True
        result = self._delegate.execute(sql, parameters)
        if (
            self._crash_after_sql_fragment is not None
            and self._crash_after_sql_fragment in normalized_sql
        ):
            self._crash_after_sql_fragment = None
            self.trigger_count += 1
            raise ProcessCrash("process lost after research job CAS before commit")
        return result

    def commit(self) -> None:
        self._delegate.commit()
        if self._crash_after_commit:
            self._crash_after_commit = False
            self.trigger_count += 1
            raise ProcessCrash("process lost immediately after atomic research initialization commit")


class RollbackFailingConnection(FailpointConnection):
    def rollback(self) -> None:
        self._delegate.rollback()
        raise RuntimeError("secondary rollback failure")


class BeginObservedConnection:
    """Signals exactly when a competing operation enters ``BEGIN IMMEDIATE``."""

    def __init__(self, delegate, begun: threading.Event) -> None:
        self._delegate = delegate
        self._begun = begun

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def execute(self, sql, parameters=()):
        if " ".join(sql.split()) == "BEGIN IMMEDIATE":
            self._begun.set()
        return self._delegate.execute(sql, parameters)


def _enable_offline_worker(storage: SqliteStorage, clock: Clock) -> None:
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", False),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="restart-acceptance", reason="offline", now=clock.now())


def _selected_topic(storage: SqliteStorage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Can durable research survive a restart?",
        question="Can durable research survive a restart without duplication?",
        score=95,
        status=TopicStatus.SELECTED,
    ))


def _scheduling_policy() -> SchedulingPolicy:
    return SchedulingPolicy(
        timezone_name="UTC",
        windows=(EditorialWindow(
            weekdays=frozenset(range(7)),
            start=datetime.strptime("00:00", "%H:%M").time(),
            end=datetime.strptime("23:59", "%H:%M").time(),
        ),),
    )


def _enqueue_research(
    storage: SqliteStorage,
    account,
    topic: Topic,
    clock: Clock,
    *,
    job_id: str,
    requested_at: datetime | None = None,
) -> str:
    result = ScheduledJobEnqueuer(
        storage=storage,
        scheduling_policy=_scheduling_policy(),
        clock=clock,
    ).enqueue(ScheduledJobRequest(
        id=job_id,
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"restart-acceptance:{job_id}",
        topic_id=int(topic.id),
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": True,
        },
        max_attempts=2,
        requested_at=requested_at,
    ))
    return result.job.id


def _worker(settings, storage, clock: Clock, *, owner: str, dispatcher=None) -> Worker:
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = dispatcher or JobDispatcher(
        settings=settings,
        storage=storage,
        policy=policy,
        clock=clock,
    )
    return Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner=owner,
        lease_seconds=5,
        heartbeat_interval_seconds=1.0,
        heartbeat_startup_timeout_seconds=1.0,
        heartbeat_shutdown_timeout_seconds=1.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
        sleeper=lambda _seconds: None,
    )


def _claim_and_start_research(
    storage: SqliteStorage,
    account,
    clock: Clock,
    *,
    job_id: str,
    owner: str,
) -> tuple[Topic, str]:
    topic = _selected_topic(storage, account)
    persisted_job_id = _enqueue_research(
        storage, account, topic, clock, job_id=job_id,
    )
    lease = storage.claim_next_job(owner, 5, now=clock.now())
    assert lease is not None and lease.job.id == persisted_job_id
    storage.mark_job_running(persisted_job_id, owner, now=clock.now())
    return topic, persisted_job_id


def _execution_counts(storage: SqliteStorage) -> tuple[int, int]:
    return tuple(storage.conn.execute(
        "SELECT (SELECT count(*) FROM runs), (SELECT count(*) FROM research_runs)"
    ).fetchone())


def _semantic_research_snapshot(storage: SqliteStorage, account, topic_id: int) -> dict[str, object]:
    topic = next(topic for topic in storage.list_topics(account.id) if topic.id == topic_id)
    rows = storage.conn.execute(
        "SELECT r.id FROM runs r JOIN research_runs rr ON rr.id=r.id "
        "WHERE r.account_id=? AND rr.topic_id=? ORDER BY r.id",
        (account.id, topic_id),
    ).fetchall()
    assert len(rows) == 1
    run = storage.get_run(rows[0]["id"])
    research_run = storage.get_research_run(rows[0]["id"])
    cards = storage.list_research_cards(account.id)
    assert run is not None and research_run is not None and len(cards) == 1
    card_payload = cards[0].model_dump(mode="json")
    for field in ("id", "topic_id", "created_at"):
        card_payload.pop(field, None)
    for source in card_payload["sources"]:
        source.pop("id", None)
        source.pop("research_card_id", None)
    return {
        "topic_status": topic.status.value,
        "run": {
            "workflow": run.workflow.value,
            "status": run.status.value,
            "cost_usd": run.cost_usd,
            "error": run.error,
        },
        "research_run": {
            "flow": research_run.flow.value,
            "status": research_run.status.value,
            "total_cost_usd": research_run.total_cost_usd,
            "error": research_run.error,
        },
        "card": card_payload,
        "real_cost_usd": storage.sum_real_cost_usd("2026-07"),
    }


def _failure_state(storage: SqliteStorage) -> dict[str, object]:
    return {
        "integrity": storage.conn.execute("PRAGMA integrity_check").fetchone()[0],
        "jobs": [tuple(row) for row in storage.conn.execute(
            "SELECT id,status,attempts,run_id,reserved_cost_usd,"
            "lease_owner,lease_expires_at,last_error FROM jobs ORDER BY id"
        ).fetchall()],
        "runs": [tuple(row) for row in storage.conn.execute(
            "SELECT id,status,cost_usd,finished_at,error FROM runs ORDER BY started_at,id"
        ).fetchall()],
        "research_runs": [tuple(row) for row in storage.conn.execute(
            "SELECT id,flow,status,research_card_id,total_cost_usd,error "
            "FROM research_runs ORDER BY id"
        ).fetchall()],
        "model_usage": storage.conn.execute(
            "SELECT count(*),COALESCE(SUM(estimated_cost_usd),0) FROM model_usage"
        ).fetchone(),
    }


def _full_execution_snapshot(storage: SqliteStorage) -> dict[str, list[tuple]]:
    queries = {
        "topics": "SELECT * FROM topics ORDER BY id",
        "jobs": "SELECT * FROM jobs ORDER BY id",
        "runs": "SELECT * FROM runs ORDER BY id",
        "research_runs": "SELECT * FROM research_runs ORDER BY id",
        "model_usage": "SELECT * FROM model_usage ORDER BY id",
        "research_cards": "SELECT * FROM research_cards ORDER BY id",
        "sources": "SELECT * FROM sources ORDER BY id",
    }
    return {
        name: [tuple(row) for row in storage.conn.execute(sql).fetchall()]
        for name, sql in queries.items()
    }


def _job_execution_card(topic_id: int) -> ResearchCard:
    return ResearchCard(
        topic_id=topic_id,
        question="Can an expired owner finalize?",
        working_thesis="Only a fresh SQLite-fenced owner may finalize.",
        confirmed_claims=["Lease ownership is checked inside the transaction."],
        confidence_score=0.9,
        source_quality_score=0.9,
        sources=[Source(url="https://example.com/fenced")],
    )


def _delayed_lease_write_after_expiry(
    settings,
    account,
    *,
    job_id: str,
    prepare_running: bool,
    operation,
) -> None:
    """Start before expiry, block on SQLite, then prove post-lock fencing wins."""
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(seed, account)
    persisted_job_id = _enqueue_research(seed, account, topic, clock, job_id=job_id)
    assert seed.claim_next_job("worker-delayed", 5, clock=clock) is not None
    if prepare_running:
        seed.mark_job_running(persisted_job_id, "worker-delayed", clock=clock)
    before = _full_execution_snapshot(seed)

    holder = SqliteStorage.open(settings.db_path)
    begun = threading.Event()
    holder.conn.execute("BEGIN IMMEDIATE")
    outcome: list[BaseException] = []

    def write_after_wait() -> None:
        contender = SqliteStorage.open(settings.db_path)
        contender.conn = BeginObservedConnection(contender.conn, begun)
        try:
            operation(contender, persisted_job_id, clock)
        except BaseException as exc:
            outcome.append(exc)
        finally:
            contender.close()

    thread = threading.Thread(target=write_after_wait)
    thread.start()
    assert begun.wait(timeout=2), "contender did not start BEGIN IMMEDIATE"
    clock.advance(6)
    holder.conn.commit()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], LifecycleTransitionError)
    holder.close()
    seed.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == before
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_initialization_started_before_expiry_fails_after_waiting_for_lock(
    settings, account,
):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-init",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.initialize_research_run_for_job(
            job_id, "worker-delayed", "post-lock-init-run", clock=clock,
        ),
    )


def test_mark_job_running_cannot_commit_after_expiry_while_waiting_for_lock(settings, account):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-running",
        prepare_running=False,
        operation=lambda storage, job_id, clock: storage.mark_job_running(
            job_id, "worker-delayed", clock=clock,
        ),
    )


def test_claim_started_before_eligibility_change_uses_time_after_write_lock(settings, account):
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(seed, account)
    job_id = _enqueue_research(
        seed,
        account,
        topic,
        clock,
        job_id="claim-after-eligibility-change",
        requested_at=clock.now() + timedelta(seconds=5),
    )
    before = seed.get_job(job_id)
    assert before is not None and before.status is JobStatus.QUEUED
    assert _as_utc(before.earliest_run_at) > clock.now()

    holder = SqliteStorage.open(settings.db_path)
    holder.conn.execute("BEGIN IMMEDIATE")
    begun = threading.Event()
    claimed: list[object] = []
    failures: list[BaseException] = []

    def claim_after_wait() -> None:
        contender = SqliteStorage.open(settings.db_path)
        contender.conn = BeginObservedConnection(contender.conn, begun)
        try:
            claimed.append(contender.claim_next_job("post-lock-claimer", 5, clock=clock))
        except BaseException as exc:
            failures.append(exc)
        finally:
            contender.close()

    thread = threading.Thread(target=claim_after_wait)
    thread.start()
    assert begun.wait(timeout=2), "contender did not start BEGIN IMMEDIATE"
    clock.advance(6)
    holder.conn.commit()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert failures == []
    assert len(claimed) == 1 and claimed[0] is not None
    assert claimed[0].job.id == job_id
    assert _as_utc(claimed[0].lease_expires_at) == clock.now() + timedelta(seconds=5)
    holder.close()
    seed.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.LEASED
        assert job.lease_owner == "post-lock-claimer"
        assert _as_utc(job.lease_expires_at) == clock.now() + timedelta(seconds=5)
        assert _as_utc(job.earliest_run_at) <= clock.now()
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_heartbeat_cannot_revive_expired_lease_after_waiting_for_lock(settings, account):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-heartbeat",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.heartbeat_job_lease(
            job_id, "worker-delayed", 5, clock=clock,
        ),
    )


def test_complete_job_cannot_commit_after_expiry_while_waiting_for_lock(settings, account):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-complete",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.complete_job(
            job_id, "worker-delayed", clock=clock,
        ),
    )


def test_fail_job_cannot_commit_after_expiry_while_waiting_for_lock(settings, account):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-fail",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.fail_job(
            job_id, "worker-delayed", "delayed failure", clock=clock,
        ),
    )


def test_external_effect_marker_cannot_commit_after_expiry_while_waiting_for_lock(
    settings, account,
):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-external",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.mark_job_external_effect_started(
            job_id, "worker-delayed", clock=clock,
        ),
    )


def test_needs_verification_cannot_commit_after_expiry_while_waiting_for_lock(
    settings, account,
):
    _delayed_lease_write_after_expiry(
        settings,
        account,
        job_id="post-lock-needs-verification",
        prepare_running=True,
        operation=lambda storage, job_id, clock: storage.mark_job_needs_verification(
            job_id, "worker-delayed", "delayed uncertainty", clock=clock,
        ),
    )


def test_expired_heartbeat_and_recovery_cannot_both_succeed(settings, account):
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(seed, account)
    job_id = _enqueue_research(seed, account, topic, clock, job_id="heartbeat-recovery-race")
    assert seed.claim_next_job("worker-race", 5, clock=clock) is not None
    seed.close()
    clock.advance(6)

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def heartbeat() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            storage.heartbeat_job_lease(job_id, "worker-race", 5, clock=clock)
            outcomes["heartbeat"] = "committed"
        except LifecycleTransitionError as exc:
            outcomes["heartbeat"] = exc
        finally:
            storage.close()

    def recover() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            outcomes["recovery"] = storage.release_or_requeue_expired_leases(clock=clock)
        finally:
            storage.close()

    threads = [threading.Thread(target=heartbeat), threading.Thread(target=recover)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert isinstance(outcomes.get("heartbeat"), LifecycleTransitionError)
    assert outcomes["recovery"].requeued_count == 1
    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.QUEUED
        assert job.lease_owner is None and job.lease_expires_at is None
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def _delayed_fenced_execution_write_after_expiry(
    settings,
    account,
    *,
    job_id: str,
    prepare,
    operation,
) -> None:
    """The post-initialization fence must also sample time after the lock."""
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    topic, persisted_job_id = _claim_and_start_research(
        seed, account, clock, job_id=job_id, owner="worker-fenced-delay",
    )
    initialized = seed.initialize_research_run_for_job(
        persisted_job_id, "worker-fenced-delay", f"{job_id}-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=persisted_job_id,
        lease_owner="worker-fenced-delay",
        run_id=initialized.run.id,
        clock=clock,
    )
    prepare(seed, execution, topic)
    before = _full_execution_snapshot(seed)

    holder = SqliteStorage.open(settings.db_path)
    begun = threading.Event()
    holder.conn.execute("BEGIN IMMEDIATE")
    outcome: list[BaseException] = []

    def write_after_wait() -> None:
        storage = SqliteStorage.open(settings.db_path)
        storage.conn = BeginObservedConnection(storage.conn, begun)
        try:
            operation(storage, execution, topic)
        except BaseException as exc:
            outcome.append(exc)
        finally:
            storage.close()

    thread = threading.Thread(target=write_after_wait)
    thread.start()
    assert begun.wait(timeout=2)
    clock.advance(6)
    holder.conn.commit()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], StaleJobExecutionError)
    holder.close()
    seed.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == before
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("suffix", "prepare", "operation"),
    [
        (
            "usage",
            lambda _storage, _execution, _topic: None,
            lambda storage, execution, _topic: storage.add_job_model_usage(execution, ModelUsage(
                run_id=execution.run_id,
                model="post-lock-fenced",
                task="research",
                input_tokens=1,
                output_tokens=1,
                estimated_cost_usd=0.001,
                dry_run=True,
            )),
        ),
        (
            "failure",
            lambda _storage, _execution, _topic: None,
            lambda storage, execution, _topic: storage.fail_job_research_execution(
                execution, 0.0, "delayed fenced failure",
            ),
        ),
        (
            "success",
            lambda _storage, _execution, _topic: None,
            lambda storage, execution, topic: storage.finalize_job_research_execution(
                execution,
                _job_execution_card(int(topic.id)),
                0.0,
                terminal_run_status=RunStatus.DRY_RUN,
            ),
        ),
        (
            "reserve",
            lambda _storage, _execution, _topic: None,
            lambda storage, execution, _topic: storage.reserve_job_budget_for_execution(
                execution, 0.1, daily_limit_usd=2.0, monthly_limit_usd=40.0,
            ),
        ),
        (
            "release",
            lambda storage, execution, _topic: storage.reserve_job_budget_for_execution(
                execution, 0.1, daily_limit_usd=2.0, monthly_limit_usd=40.0,
            ),
            lambda storage, execution, _topic: storage.release_job_budget_for_execution(execution),
        ),
    ],
    ids=("usage", "failure", "success", "reserve", "release"),
)
def test_fenced_research_writes_cannot_commit_after_expiry_while_waiting_for_lock(
    settings, account, suffix, prepare, operation,
):
    _delayed_fenced_execution_write_after_expiry(
        settings,
        account,
        job_id=f"post-lock-fenced-{suffix}",
        prepare=prepare,
        operation=operation,
    )


def test_restart_during_dispatch_before_run_attachment_loses_nothing(
    settings, account,
):
    """Failpoint po utworzeniu runu nie może prowadzić do drugiego runu."""
    clock = MutableUtcClock()

    old_primary = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(old_primary, account)
    _enable_offline_worker(old_primary, clock)
    job_id = _enqueue_research(
        old_primary, account, topic, clock, job_id="crash-before-run-attachment",
    )
    failing_connection = FailpointConnection(
        old_primary.conn, sql_fragment="UPDATE jobs SET run_id=?",
    )
    old_primary.conn = failing_connection
    old_worker = _worker(settings, old_primary, clock, owner="worker-before-restart")

    with pytest.raises(ProcessCrash, match="inside atomic research initialization"):
        old_worker.run_once()

    crashed_job = old_primary.get_job(job_id)
    assert failing_connection.trigger_count == 1
    assert crashed_job is not None
    assert crashed_job.status is JobStatus.RUNNING
    assert crashed_job.run_id is None
    assert crashed_job.attempts == 1
    assert old_primary.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert old_primary.conn.execute("SELECT count(*) FROM research_runs").fetchone()[0] == 0
    old_primary.close()

    clock.advance(6)
    maintenance = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    )
    cycle = maintenance.run_once()
    assert cycle.recovery.requeued_count == 1
    assert cycle.recovery.needs_verification_count == 0

    new_primary = SqliteStorage.open(settings.db_path)
    try:
        new_worker = _worker(
            settings, new_primary, clock, owner="worker-after-restart",
        )
        result = new_worker.run_once()
        assert result.status is WorkerIterationStatus.DONE
    finally:
        new_primary.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        state = _failure_state(reopened)
        counts = {
            "jobs": len(state["jobs"]),
            "runs": len(state["runs"]),
            "research_runs": len(state["research_runs"]),
        }
        assert counts == {"jobs": 1, "runs": 1, "research_runs": 1}, state
        assert state["integrity"] == "ok"
    finally:
        reopened.close()


def test_atomic_research_initialization_rolls_back_when_crash_follows_run_insert(
    settings, account,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-crash-after-run", owner="worker-a",
    )
    failing_connection = FailpointConnection(
        storage.conn, sql_fragment="INSERT INTO research_runs",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="inside atomic research initialization"):
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-crash-after-run-id", now=clock.now(),
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.run_id is None
        assert _execution_counts(reopened) == (0, 0)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_initialization_rolls_back_before_job_attachment(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-crash-before-attach", owner="worker-a",
    )
    failing_connection = FailpointConnection(
        storage.conn, sql_fragment="UPDATE jobs SET run_id=?",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="inside atomic research initialization"):
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-crash-before-attach-id", now=clock.now(),
        )
    assert failing_connection.trigger_count == 1
    assert _execution_counts(storage) == (0, 0)
    job = storage.get_job(job_id)
    assert job is not None and job.run_id is None and job.status is JobStatus.RUNNING
    assert storage.sum_real_cost_usd("2026-07") == 0.0
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _execution_counts(reopened) == (0, 0)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_initialization_rolls_back_after_cas_before_commit(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-crash-after-cas", owner="worker-a",
    )
    failing_connection = FailpointConnection(
        storage.conn, crash_after_sql_fragment="UPDATE jobs SET run_id=?",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="after research job CAS before commit"):
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-crash-after-cas-run", now=clock.now(),
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.run_id is None
        assert _execution_counts(reopened) == (0, 0)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_initialization_preserves_primary_error_when_rollback_fails(
    settings, account,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-primary-error", owner="worker-a",
    )
    storage.conn = RollbackFailingConnection(
        storage.conn, sql_fragment="INSERT INTO research_runs",
    )

    with pytest.raises(ProcessCrash, match="inside atomic research initialization") as caught:
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-primary-error-run", now=clock.now(),
        )
    assert any(
        "Secondary SQLite rollback failure" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job_id).run_id is None
        assert _execution_counts(reopened) == (0, 0)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_restart_after_atomic_run_attachment_does_not_create_second_run(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _enable_offline_worker(storage, clock)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-crash-after-commit", owner="worker-a",
    )
    failing_connection = FailpointConnection(storage.conn, crash_after_commit=True)
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="immediately after atomic research initialization commit"):
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-crash-after-commit-id", now=clock.now(),
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    clock.advance(6)
    cycle = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    ).run_once()
    assert cycle.recovery.requeued_count == 0
    assert cycle.recovery.needs_verification_count == 1

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None
        assert job.status is JobStatus.NEEDS_VERIFICATION
        assert job.run_id == "atomic-crash-after-commit-id"
        assert _execution_counts(reopened) == (1, 1)
        assert _worker(settings, reopened, clock, owner="worker-after-restart").run_once().status is (
            WorkerIterationStatus.IDLE
        )
        assert reopened.get_job(job_id).status is JobStatus.NEEDS_VERIFICATION
        assert _execution_counts(reopened) == (1, 1)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_initialization_returns_existing_attached_run(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-idempotent", owner="worker-a",
    )
    try:
        first = storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-idempotent-first", now=clock.now(),
        )
        second = storage.initialize_research_run_for_job(
            job_id, "worker-a", "atomic-idempotent-second", now=clock.now(),
        )
        assert first.created is True
        assert second.created is False
        assert first.run.id == second.run.id == "atomic-idempotent-first"
        assert first.research_run.id == second.research_run.id
        assert storage.get_job(job_id).run_id == first.run.id
        assert _execution_counts(storage) == (1, 1)
        assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("run_status", "research_status"),
    [
        ("SUCCESS", "PENDING"),
        ("DRY_RUN", "COMPLETE"),
        ("FAILED", "FAILED"),
    ],
)
def test_existing_research_initialization_rejects_incompatible_statuses(
    settings, account, run_status, research_status,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock,
        job_id=f"existing-state-{run_status}-{research_status}", owner="worker-a",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-a", f"existing-state-run-{run_status}-{research_status}",
        now=clock.now(),
    )
    storage.conn.execute(
        "UPDATE runs SET status=?,finished_at=? WHERE id=?",
        (
            run_status,
            None if run_status == "DRY_RUN" else "2026-07-13 12:00:01",
            initialized.run.id,
        ),
    )
    storage.conn.execute(
        "UPDATE research_runs SET status=? WHERE id=?",
        (research_status, initialized.run.id),
    )
    storage.conn.commit()
    before = _full_execution_snapshot(storage)

    with pytest.raises(JobRunRelationError) as caught:
        storage.initialize_research_run_for_job(
            job_id, "worker-a", "must-not-replace-existing", now=clock.now(),
        )
    assert caught.value.code == "ATTACHED_RESEARCH_RUN_STATE_INVALID"
    assert _full_execution_snapshot(storage) == before
    storage.close()


def test_old_owner_cannot_initialize_research_run_after_lease_loss(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="atomic-old-owner", owner="worker-old",
    )
    clock.advance(6)
    recovery = storage.release_or_requeue_expired_leases(now=clock.now())
    assert recovery.requeued_count == 1
    lease = storage.claim_next_job("worker-new", 5, now=clock.now())
    assert lease is not None and lease.job.id == job_id
    storage.mark_job_running(job_id, "worker-new", now=clock.now())

    with pytest.raises(LifecycleTransitionError):
        storage.initialize_research_run_for_job(
            job_id, "worker-old", "atomic-old-owner-run", now=clock.now(),
        )
    assert storage.get_job(job_id).lease_owner == "worker-new"
    assert storage.get_job(job_id).run_id is None
    assert _execution_counts(storage) == (0, 0)
    assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    storage.close()


def test_expired_owner_cannot_mutate_research_before_recovery(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="expired-owner-write", owner="worker-old",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-old", "expired-owner-write-run", now=clock.now(),
    )
    execution = JobExecutionContext(
        job_id=job_id,
        lease_owner="worker-old",
        run_id=initialized.run.id,
        clock=clock,
    )
    before = _failure_state(storage)

    clock.advance(6)
    with pytest.raises(StaleJobExecutionError):
        storage.add_job_model_usage(execution, ModelUsage(
            run_id=initialized.run.id,
            model="offline-expired-owner",
            task="research",
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.001,
            dry_run=True,
        ))

    assert _failure_state(storage) == before
    assert storage.get_job(job_id).lease_owner == "worker-old"
    assert storage.get_job(job_id).status is JobStatus.RUNNING
    storage.close()


def test_expired_owner_pre_recovery_rejects_full_lifecycle_matrix(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="pre-recovery-matrix", owner="worker-old",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-old", "pre-recovery-matrix-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-old", run_id=initialized.run.id, clock=clock,
    )
    running_job_id = _enqueue_research(
        storage, account, _selected_topic(storage, account), clock,
        job_id="pre-recovery-running",
    )
    assert storage.claim_next_job("worker-old", 5, clock=clock).job.id == running_job_id

    clock.advance(6)
    before = _full_execution_snapshot(storage)
    operations = {
        "initialization": lambda: storage.initialize_research_run_for_job(
            job_id, "worker-old", "must-not-initialize-after-expiry", clock=clock,
        ),
        "mark running": lambda: storage.mark_job_running(
            running_job_id, "worker-old", clock=clock,
        ),
        "heartbeat": lambda: storage.heartbeat_job_lease(
            job_id, "worker-old", 5, clock=clock,
        ),
        "usage and cost": lambda: storage.add_job_model_usage(execution, ModelUsage(
            run_id=initialized.run.id,
            model="expired-owner",
            task="research",
            input_tokens=1,
            output_tokens=1,
            estimated_cost_usd=0.001,
            dry_run=True,
        )),
        "success": lambda: storage.finalize_job_research_execution(
            execution,
            _job_execution_card(int(topic.id)),
            0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        ),
        "failure": lambda: storage.fail_job_research_execution(
            execution, 0.0, "expired owner failure", terminalize_job=True,
        ),
        "budget reserve": lambda: storage.reserve_job_budget_for_execution(
            execution, 0.1, daily_limit_usd=2.0, monthly_limit_usd=40.0,
        ),
        "budget release": lambda: storage.release_job_budget_for_execution(execution),
        "external effect": lambda: storage.mark_job_external_effect_started(
            job_id, "worker-old", clock=clock,
        ),
        "complete": lambda: storage.complete_job(job_id, "worker-old", clock=clock),
        "fail": lambda: storage.fail_job(
            job_id, "worker-old", "expired owner job failure", clock=clock,
        ),
        "needs verification": lambda: storage.mark_job_needs_verification(
            job_id, "worker-old", "expired owner verification", clock=clock,
        ),
    }
    for label, operation in operations.items():
        with pytest.raises((LifecycleTransitionError, StaleJobExecutionError)):
            operation()
        assert _full_execution_snapshot(storage) == before, label

    expired = storage.get_job(job_id)
    assert expired is not None and expired.status is JobStatus.RUNNING
    assert expired.lease_owner == "worker-old" and _as_utc(expired.lease_expires_at) < clock.now()
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == before
        persisted = reopened.get_job(job_id)
        assert persisted is not None and persisted.lease_owner == "worker-old"
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_old_worker_cannot_mutate_research_after_lease_loss(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="old-worker-mutation-matrix", owner="worker-old",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-old", "old-worker-mutation-matrix-run", now=clock.now(),
    )
    execution = JobExecutionContext(
        job_id=job_id,
        lease_owner="worker-old",
        run_id=initialized.run.id,
        clock=clock,
    )
    clock.advance(6)
    recovery = storage.release_or_requeue_expired_leases(now=clock.now())
    assert recovery.needs_verification_count == 1
    assert storage.get_job(job_id).status is JobStatus.NEEDS_VERIFICATION
    before = _full_execution_snapshot(storage)

    stale_operations = {
        "fence checkpoint": lambda: storage.assert_job_execution_active(execution),
        "model usage and run cost": lambda: storage.add_job_model_usage(
            execution,
            ModelUsage(
                run_id=initialized.run.id,
                model="offline-old-owner",
                task="research",
                input_tokens=50,
                output_tokens=20,
                estimated_cost_usd=0.002,
                dry_run=True,
            ),
        ),
        "run and research failure": lambda: storage.fail_job_research_execution(
            execution, 0.0, "old owner must not fail",
        ),
        "card and final result": lambda: storage.finalize_job_research_execution(
            execution,
            _job_execution_card(int(topic.id)),
            0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        ),
        "budget reservation": lambda: storage.reserve_job_budget_for_execution(
            execution, 0.1, daily_limit_usd=2.0, monthly_limit_usd=40.0,
        ),
        "budget release": lambda: storage.release_job_budget_for_execution(execution),
    }
    for label, operation in stale_operations.items():
        with pytest.raises(StaleJobExecutionError):
            operation()
        assert _full_execution_snapshot(storage) == before, label

    lifecycle_operations = {
        "external effect": lambda: storage.mark_job_external_effect_started(
            job_id, "worker-old", now=clock.now(),
        ),
        "job complete": lambda: storage.complete_job(job_id, "worker-old", now=clock.now()),
        "job fail": lambda: storage.fail_job(
            job_id, "worker-old", "old owner must not fail job", now=clock.now(),
        ),
    }
    for label, operation in lifecycle_operations.items():
        with pytest.raises(LifecycleTransitionError):
            operation()
        assert _full_execution_snapshot(storage) == before, label
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == before
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_pipeline_stops_without_failure_writes_when_lease_is_lost(
    settings, account, monkeypatch,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="pipeline-lease-loss", owner="worker-old",
    )

    class LeaseLosingResearchClient(FakeResearchClient):
        def run_research(self, plan):
            result = super().run_research(plan)
            clock.advance(6)
            return result

    client = LeaseLosingResearchClient()
    monkeypatch.setattr(runner, "_build_research_client", lambda *_args, **_kwargs: client)
    write_counts = {
        name: 0
        for name in (
            "add_job_model_usage",
            "fail_job_research_execution",
            "finalize_job_research_execution",
            "add_model_usage",
            "finish_run",
            "mark_research_run_failed",
            "add_research_card",
            "finalize_research_success",
        )
    }
    for name in write_counts:
        original = getattr(storage, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            write_counts[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(storage, name, counted)

    with pytest.raises(StaleJobExecutionError):
        runner.run_research_dry_run(
            account,
            topic,
            settings=settings,
            storage=storage,
            policy=PolicyEngine(settings, storage, clock),
            clock=clock,
            job_execution=ResearchJobExecution(job_id=job_id, lease_owner="worker-old"),
        )

    assert write_counts == {name: 0 for name in write_counts}
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.RUNNING and job.run_id is not None
    assert storage.get_run(job.run_id).status is RunStatus.DRY_RUN
    assert storage.get_research_run(job.run_id).status.value == "PENDING"
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
    assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    storage.close()


def test_recovery_and_stale_research_write_cannot_both_succeed(settings, account):
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        seed, account, clock, job_id="recovery-stale-write-race", owner="worker-old",
    )
    initialized = seed.initialize_research_run_for_job(
        job_id, "worker-old", "recovery-stale-write-race-run", now=clock.now(),
    )
    seed.close()
    clock.advance(6)

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def stale_write() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            execution = JobExecutionContext(
                job_id=job_id,
                lease_owner="worker-old",
                run_id=initialized.run.id,
                clock=clock,
            )
            try:
                storage.add_job_model_usage(execution, ModelUsage(
                    run_id=initialized.run.id,
                    model="offline-race",
                    task="research",
                    input_tokens=1,
                    output_tokens=1,
                    estimated_cost_usd=0.001,
                    dry_run=True,
                ))
                outcomes["write"] = "committed"
            except StaleJobExecutionError as exc:
                outcomes["write"] = exc
        finally:
            storage.close()

    def recover() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            outcomes["recovery"] = storage.release_or_requeue_expired_leases(now=clock.now())
        finally:
            storage.close()

    threads = [threading.Thread(target=stale_write), threading.Thread(target=recover)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert isinstance(outcomes.get("write"), StaleJobExecutionError)
    assert outcomes["recovery"].needs_verification_count == 1
    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.NEEDS_VERIFICATION
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_job_now_normalizes_non_utc_aware_datetime(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    job_id = _enqueue_research(
        storage, account, topic, clock, job_id="non-utc-job-now",
    )
    local = NOW.astimezone(timezone(timedelta(hours=3)))
    lease = storage.claim_next_job("worker-local-zone", 5, now=local)
    assert lease is not None and lease.job.id == job_id
    raw = storage.conn.execute(
        "SELECT lease_expires_at FROM jobs WHERE id=?", (job_id,),
    ).fetchone()["lease_expires_at"]
    assert raw == "2026-07-13 12:00:05"
    storage.close()


def test_job_now_rejects_naive_datetime_without_mutation(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enqueue_research(storage, account, topic, clock, job_id="naive-job-now")
    before = _full_execution_snapshot(storage)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        storage.claim_next_job("worker-naive", 5, now=NOW.replace(tzinfo=None))
    assert _full_execution_snapshot(storage) == before
    storage.close()


def test_fenced_lease_comparison_uses_normalized_utc(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="utc-lease-boundary", owner="worker-a",
    )
    local_zone = timezone(timedelta(hours=3))
    clock.value = (NOW + timedelta(seconds=5)).astimezone(local_zone)
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-a", "utc-lease-boundary-run", now=clock.now(),
    )
    execution = JobExecutionContext(
        job_id=job_id,
        lease_owner="worker-a",
        run_id=initialized.run.id,
        clock=clock,
    )
    storage.assert_job_execution_active(execution)
    clock.value += timedelta(microseconds=1)
    with pytest.raises(StaleJobExecutionError):
        storage.assert_job_execution_active(execution)
    storage.close()


def test_concurrent_research_initialization_creates_single_attached_run(settings, account):
    clock = MutableUtcClock()
    seed = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        seed, account, clock, job_id="atomic-concurrent", owner="shared-owner",
    )
    seed.close()

    start = threading.Barrier(2)
    results = []
    failures = []

    def initialize(run_id: str) -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            start.wait()
            results.append(storage.initialize_research_run_for_job(
                job_id, "shared-owner", run_id, now=clock.now(),
            ))
        except BaseException as exc:
            failures.append(exc)
        finally:
            storage.close()

    threads = [
        threading.Thread(target=initialize, args=("atomic-concurrent-a",)),
        threading.Thread(target=initialize, args=("atomic-concurrent-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert failures == []
    assert len(results) == 2
    assert sum(result.created for result in results) == 1
    assert {result.run.id for result in results} in (
        {"atomic-concurrent-a"}, {"atomic-concurrent-b"},
    )
    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.run_id in {result.run.id for result in results}
        assert _execution_counts(reopened) == (1, 1)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_worker_dry_run_baseline_survives_reopen(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="baseline")
    result = _worker(settings, storage, clock, owner="baseline-worker").run_once()
    assert result.status is WorkerIterationStatus.DONE
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None
        assert job.status is JobStatus.DONE
        assert job.kind is JobKind.RESEARCH and job.workflow is WorkflowType.RESEARCH
        assert job.payload["dry_run"] is True
        assert job.idempotency_key == "restart-acceptance:baseline"
        assert job.schedule_reason == "WITHIN_EDITORIAL_WINDOW"
        assert job.attempts == 1 and job.run_id is not None
        assert job.reserved_cost_usd == 0.0 and job.external_effect_started_at is None
        assert _execution_counts(reopened) == (1, 1)
        snapshot = _semantic_research_snapshot(reopened, account, int(topic.id))
        assert snapshot["run"]["status"] == "DRY_RUN"
        assert snapshot["research_run"]["status"] == "COMPLETE"
        assert snapshot["real_cost_usd"] == 0.0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_final_heartbeat_failure_after_research_success_cannot_partially_fail_job(
    settings, account, monkeypatch,
):
    """RESEARCH terminalizes itself; a fourth worker heartbeat is forbidden."""
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="no-post-success-heartbeat")
    heartbeat_calls = 0
    original_heartbeat = storage.heartbeat_job_lease

    def heartbeat_spy(*args, **kwargs):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls == 4:
            raise RuntimeError("forbidden post-dispatch heartbeat")
        return original_heartbeat(*args, **kwargs)

    monkeypatch.setattr(storage, "heartbeat_job_lease", heartbeat_spy)
    result = _worker(settings, storage, clock, owner="no-post-success-heartbeat").run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert heartbeat_calls == 2
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.run_id is not None
    assert job.last_error is None and job.lease_owner is None and job.lease_expires_at is None
    assert storage.get_run(job.run_id).status is RunStatus.DRY_RUN
    research_run = storage.get_research_run(job.run_id)
    assert research_run.status.value == "COMPLETE" and research_run.research_card_id is not None
    persisted_card = storage.get_research_card(research_run.research_card_id)
    assert persisted_card is not None
    expected_sources = len(persisted_card.sources)
    assert next(item for item in storage.list_topics(account.id) if item.id == topic.id).status is TopicStatus.USED
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job_id).status is JobStatus.DONE
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 1
        assert reopened.conn.execute("SELECT count(*) FROM sources").fetchone()[0] == expected_sources
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_success_does_not_call_generic_complete_job(settings, account, monkeypatch):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="no-generic-complete")
    complete_calls = 0
    original_complete = storage.complete_job

    def complete_spy(*args, **kwargs):
        nonlocal complete_calls
        complete_calls += 1
        return original_complete(*args, **kwargs)

    monkeypatch.setattr(storage, "complete_job", complete_spy)
    result = _worker(settings, storage, clock, owner="no-generic-complete").run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert complete_calls == 0
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.run_id is not None
    assert storage.get_run(job.run_id).status is RunStatus.DRY_RUN
    assert storage.get_research_run(job.run_id).status.value == "COMPLETE"
    assert job.lease_owner is None and job.lease_expires_at is None
    assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    storage.close()


def test_exception_after_workflow_terminalization_does_not_overwrite_success(
    settings, account, monkeypatch, caplog,
):
    class FailingNotifier:
        def notify(self, *_args, **_kwargs) -> None:
            raise RuntimeError("post-terminal notification failure")

    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="post-terminal-diagnostic")
    monkeypatch.setattr(runner, "LogNotification", FailingNotifier)

    with caplog.at_level("WARNING"):
        result = _worker(settings, storage, clock, owner="post-terminal-diagnostic").run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert "WORKER_TERMINAL_DIAGNOSTIC_FAILED" in caplog.text
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.last_error is None
    assert job.run_id is not None and storage.get_run(job.run_id).status is RunStatus.DRY_RUN
    assert storage.get_research_run(job.run_id).status.value == "COMPLETE"
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(job_id)
        assert persisted is not None and persisted.status is JobStatus.DONE
        assert reopened.get_run(persisted.run_id).error is None
        assert reopened.get_research_run(persisted.run_id).error is None
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_success_rolls_back_before_job_terminalization(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="success-before-job", owner="worker-success",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-success", "success-before-job-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-success", run_id=initialized.run.id, clock=clock,
    )
    failing_connection = FailpointConnection(
        storage.conn, sql_fragment="UPDATE jobs SET status='DONE'",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="inside atomic research initialization"):
        storage.finalize_job_research_execution(
            execution, _job_execution_card(int(topic.id)), 0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.run_id == initialized.run.id
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert next(item for item in reopened.list_topics(account.id) if item.id == topic.id).status is TopicStatus.SELECTED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_success_rolls_back_after_job_update_before_commit(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="success-after-job", owner="worker-success",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-success", "success-after-job-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-success", run_id=initialized.run.id, clock=clock,
    )
    failing_connection = FailpointConnection(
        storage.conn, crash_after_sql_fragment="UPDATE jobs SET status='DONE'",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="after research job CAS before commit"):
        storage.finalize_job_research_execution(
            execution, _job_execution_card(int(topic.id)), 0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.lease_owner == "worker-success"
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert next(item for item in reopened.list_topics(account.id) if item.id == topic.id).status is TopicStatus.SELECTED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_success_commit_then_process_loss_remains_fully_terminal(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="success-after-commit", owner="worker-success",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-success", "success-after-commit-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-success", run_id=initialized.run.id, clock=clock,
    )
    failing_connection = FailpointConnection(storage.conn, crash_after_commit=True)
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="immediately after atomic research initialization commit"):
        storage.finalize_job_research_execution(
            execution, _job_execution_card(int(topic.id)), 0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.DONE and job.run_id == initialized.run.id
        assert job.lease_owner is None and job.lease_expires_at is None and job.last_error is None
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        research_run = reopened.get_research_run(initialized.run.id)
        assert research_run.status.value == "COMPLETE" and research_run.research_card_id is not None
        assert reopened.get_research_card(research_run.research_card_id) is not None
        assert next(item for item in reopened.list_topics(account.id) if item.id == topic.id).status is TopicStatus.USED
        with pytest.raises(LifecycleTransitionError):
            reopened.complete_job(job_id, "worker-success", clock=clock)
        assert reopened.claim_next_job("retry-owner", 5, clock=clock) is None
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_failure_preserves_primary_error_when_rollback_fails(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="failure-primary-error", owner="worker-failure",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-failure", "failure-primary-error-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-failure", run_id=initialized.run.id, clock=clock,
    )
    storage.conn = RollbackFailingConnection(
        storage.conn, sql_fragment="UPDATE jobs SET status='FAILED'",
    )

    with pytest.raises(ProcessCrash, match="inside atomic research initialization") as caught:
        storage.fail_job_research_execution(
            execution, 0.0, "primary failure must survive rollback failure", terminalize_job=True,
        )
    assert any(
        "Secondary SQLite rollback failure" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.lease_owner == "worker-failure"
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_failure_rolls_back_after_job_update_before_commit(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    _topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="failure-after-job", owner="worker-failure",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-failure", "failure-after-job-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-failure", run_id=initialized.run.id, clock=clock,
    )
    failing_connection = FailpointConnection(
        storage.conn, crash_after_sql_fragment="UPDATE jobs SET status='FAILED'",
    )
    storage.conn = failing_connection

    with pytest.raises(ProcessCrash, match="after research job CAS before commit"):
        storage.fail_job_research_execution(
            execution, 0.0, "rollback all failed states", terminalize_job=True,
        )
    assert failing_connection.trigger_count == 1
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.lease_owner == "worker-failure"
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_research_worker_dry_run_matches_direct_cli_semantics(settings, account):
    (settings.project_root / "docs").mkdir(parents=True, exist_ok=True)
    direct_store = SqliteStorage.open(settings.db_path)
    direct_topic = _selected_topic(direct_store, account)
    direct_store.close()
    direct_summary = runner.run_research(topic_id=int(direct_topic.id), settings=settings)
    assert direct_summary.passed and direct_summary.dry_run

    direct_inspection = SqliteStorage.open(settings.db_path)
    try:
        direct_snapshot = _semantic_research_snapshot(
            direct_inspection, account, int(direct_topic.id),
        )
        assert _execution_counts(direct_inspection) == (1, 1)
        assert direct_inspection.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        direct_inspection.close()

    worker_root = settings.project_root / "worker-parity"
    worker_settings = replace(
        settings,
        project_root=worker_root,
        data_dir=worker_root / "data",
        db_path=worker_root / "data" / "agent.db",
        costs_csv_path=worker_root / "COSTS.csv",
    )
    clock = MutableUtcClock()
    initialize_database(worker_settings.db_path)
    worker_store = SqliteStorage.open(worker_settings.db_path)
    worker_topic = _selected_topic(worker_store, account)
    _enable_offline_worker(worker_store, clock)
    worker_job_id = _enqueue_research(
        worker_store, account, worker_topic, clock, job_id="worker-parity",
    )
    try:
        result = _worker(
            worker_settings, worker_store, clock, owner="worker-parity-owner",
        ).run_once()
        assert result.status is WorkerIterationStatus.DONE
        worker_job = worker_store.get_job(worker_job_id)
        assert worker_job is not None and worker_job.status is JobStatus.DONE
        assert worker_job.reserved_cost_usd == 0.0
        assert worker_job.external_effect_started_at is None
        assert _semantic_research_snapshot(
            worker_store, account, int(worker_topic.id),
        ) == direct_snapshot
        assert _execution_counts(worker_store) == (1, 1)
        assert worker_store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        worker_store.close()


def test_restart_after_claim_before_dispatch_recovers_without_duplicate(settings, account):
    clock = MutableUtcClock()
    old_primary = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(old_primary, account)
    _enable_offline_worker(old_primary, clock)
    job_id = _enqueue_research(old_primary, account, topic, clock, job_id="restart-after-claim")
    lease = old_primary.claim_next_job("worker-before-restart", 5, now=clock.now())
    assert lease is not None and lease.job.id == job_id
    assert old_primary.get_job(job_id).status is JobStatus.LEASED
    old_primary.close()

    clock.advance(6)
    cycle = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    ).run_once()
    assert cycle.recovery.requeued_count == 1
    assert cycle.recovery.needs_verification_count == 0

    new_primary = SqliteStorage.open(settings.db_path)
    try:
        result = _worker(
            settings, new_primary, clock, owner="worker-after-restart",
        ).run_once()
        assert result.status is WorkerIterationStatus.DONE
    finally:
        new_primary.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.DONE
        assert job.attempts == 2 and job.run_id is not None
        assert job.reserved_cost_usd == 0.0 and job.external_effect_started_at is None
        assert _execution_counts(reopened) == (1, 1)
        assert _semantic_research_snapshot(reopened, account, int(topic.id))["real_cost_usd"] == 0.0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_restart_after_run_attachment_preserves_single_run_and_budget(settings, account):
    clock = MutableUtcClock()
    old_primary = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(old_primary, account)
    _enable_offline_worker(old_primary, clock)
    job_id = _enqueue_research(old_primary, account, topic, clock, job_id="restart-after-attach")
    failing_connection = FailpointConnection(
        old_primary.conn, arm_commit_after_sql_fragment="UPDATE jobs SET run_id=?",
    )
    old_primary.conn = failing_connection

    with pytest.raises(ProcessCrash, match="immediately after atomic research initialization commit"):
        _worker(settings, old_primary, clock, owner="worker-before-restart").run_once()
    assert failing_connection.trigger_count == 1
    attached = old_primary.get_job(job_id)
    assert attached is not None and attached.run_id is not None
    assert _execution_counts(old_primary) == (1, 1)
    old_primary.close()

    clock.advance(6)
    cycle = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    ).run_once()
    assert cycle.recovery.requeued_count == 0
    assert cycle.recovery.needs_verification_count == 1

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.NEEDS_VERIFICATION
        assert job.run_id == attached.run_id
        assert job.reserved_cost_usd == 0.0 and job.external_effect_started_at is None
        assert _worker(settings, reopened, clock, owner="worker-after-restart").run_once().status is (
            WorkerIterationStatus.IDLE
        )
        assert _execution_counts(reopened) == (1, 1)
        assert reopened.get_run(job.run_id).status.value == "DRY_RUN"
        assert reopened.get_research_run(job.run_id).status.value == "PENDING"
        assert reopened.sum_real_cost_usd("2026-07") == 0.0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_old_worker_cannot_finalize_after_lease_loss(settings, account):
    clock = MutableUtcClock()
    old_primary = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(old_primary, account)
    _enable_offline_worker(old_primary, clock)
    job_id = _enqueue_research(old_primary, account, topic, clock, job_id="old-owner-fencing")
    lease = old_primary.claim_next_job("worker-old", 5, now=clock.now())
    assert lease is not None and lease.job.id == job_id
    old_primary.close()

    clock.advance(6)
    MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    ).run_once()
    new_primary = SqliteStorage.open(settings.db_path)
    try:
        assert _worker(settings, new_primary, clock, owner="worker-new").run_once().status is (
            WorkerIterationStatus.DONE
        )
        before = _failure_state(new_primary)
        with pytest.raises(LifecycleTransitionError):
            new_primary.complete_job(job_id, "worker-old", now=clock.now())
        assert _failure_state(new_primary) == before
        assert new_primary.get_job(job_id).status is JobStatus.DONE
        assert _execution_counts(new_primary) == (1, 1)
        assert new_primary.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        new_primary.close()


def test_future_research_job_survives_restart_and_runs_at_boundary(settings, account):
    clock = MutableUtcClock()
    old_primary = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(old_primary, account)
    _enable_offline_worker(old_primary, clock)
    future_requested_at = clock.now() + timedelta(hours=1)
    job_id = _enqueue_research(
        old_primary, account, topic, clock, job_id="future-restart",
        requested_at=future_requested_at,
    )
    before_restart = old_primary.get_job(job_id)
    assert before_restart is not None
    earliest = before_restart.earliest_run_at
    old_primary.close()

    MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=1,
        clock=clock,
    ).run_once()
    before_boundary = SqliteStorage.open(settings.db_path)
    try:
        result = _worker(settings, before_boundary, clock, owner="worker-too-early").run_once()
        job = before_boundary.get_job(job_id)
        assert result.status is WorkerIterationStatus.IDLE
        assert job is not None and job.status is JobStatus.QUEUED
        assert job.attempts == 0 and job.run_id is None
        assert job.lease_owner is None and job.reserved_cost_usd == 0.0
        assert job.schedule_reason == before_restart.schedule_reason
        assert job.earliest_run_at == earliest
        assert _execution_counts(before_boundary) == (0, 0)
    finally:
        before_boundary.close()

    clock.value = earliest if earliest.tzinfo is not None else earliest.replace(tzinfo=UTC)
    at_boundary = SqliteStorage.open(settings.db_path)
    try:
        assert _worker(settings, at_boundary, clock, owner="worker-at-boundary").run_once().status is (
            WorkerIterationStatus.DONE
        )
        job = at_boundary.get_job(job_id)
        assert job is not None and job.status is JobStatus.DONE and job.attempts == 1
        assert _execution_counts(at_boundary) == (1, 1)
        assert _semantic_research_snapshot(at_boundary, account, int(topic.id))["real_cost_usd"] == 0.0
        assert at_boundary.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        at_boundary.close()


def test_restart_acceptance_keeps_sqlite_integrity(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="integrity")
    assert _worker(settings, storage, clock, owner="integrity-worker").run_once().status is (
        WorkerIterationStatus.DONE
    )
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job_id).status is JobStatus.DONE
        assert _execution_counts(reopened) == (1, 1)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_costs_csv_directory_path_is_best_effort(settings, account, caplog):
    csv_directory = settings.project_root / "costs-csv-directory"
    csv_directory.mkdir(parents=True)
    worker_settings = replace(settings, costs_csv_path=csv_directory)
    clock = MutableUtcClock()
    storage = SqliteStorage.open(worker_settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="costs-csv-directory")

    with caplog.at_level("WARNING"):
        result = _worker(worker_settings, storage, clock, owner="costs-csv-directory").run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert "COSTS_CSV_DERIVED_EXPORT_FAILED" in caplog.text
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.run_id is not None
    assert storage.get_run(job.run_id).status is RunStatus.DRY_RUN
    assert storage.get_research_run(job.run_id).status.value == "COMPLETE"
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE run_id=?", (job.run_id,)).fetchone()[0] == 1
    storage.close()

    reopened = SqliteStorage.open(worker_settings.db_path)
    try:
        persisted = reopened.get_job(job_id)
        assert persisted is not None and persisted.status is JobStatus.DONE
        assert reopened.conn.execute(
            "SELECT count(*) FROM model_usage WHERE run_id=?", (persisted.run_id,),
        ).fetchone()[0] == 1
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_costs_csv_failure_does_not_fail_research_job(settings, account, monkeypatch, caplog):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="costs-csv-derived-success")

    def fail_csv_export(_tracker, _row) -> None:
        raise OSError("controlled CSV export failure")

    monkeypatch.setattr("app.llm.usage_tracker.UsageTracker._append_csv", fail_csv_export)
    with caplog.at_level("WARNING"):
        result = _worker(settings, storage, clock, owner="costs-csv-success").run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert "COSTS_CSV_DERIVED_EXPORT_FAILED" in caplog.text
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.run_id is not None
    run = storage.get_run(job.run_id)
    research_run = storage.get_research_run(job.run_id)
    usage_rows = storage.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage WHERE run_id=?", (job.run_id,),
    ).fetchall()
    assert run is not None and run.status is RunStatus.DRY_RUN and run.error is None
    assert research_run is not None and research_run.status.value == "COMPLETE"
    assert research_run.error is None and research_run.research_card_id is not None
    assert len(usage_rows) == 1
    assert run.cost_usd == pytest.approx(float(usage_rows[0]["estimated_cost_usd"]))
    assert research_run.total_cost_usd == pytest.approx(run.cost_usd)
    assert storage.get_research_card(research_run.research_card_id) is not None
    assert next(item for item in storage.list_topics(account.id) if item.id == topic.id).status is TopicStatus.USED
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(job_id)
        assert persisted is not None and persisted.status is JobStatus.DONE
        assert reopened.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 1
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_costs_csv_failure_does_not_mask_research_failure(settings, account, monkeypatch, caplog):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="costs-csv-derived-failure")

    class ExpectedResearchFailure(FakeResearchClient):
        def run_research(self, plan):
            raise ResearchError(
                "expected research failure",
                usage=Usage(input_tokens=10, output_tokens=2, web_search_requests=1),
                model="controlled-failure-model",
            )

    def fail_csv_export(_tracker, _row) -> None:
        raise OSError("controlled CSV export failure")

    monkeypatch.setattr(runner, "_build_research_client", lambda *_args, **_kwargs: ExpectedResearchFailure())
    monkeypatch.setattr("app.llm.usage_tracker.UsageTracker._append_csv", fail_csv_export)
    with caplog.at_level("WARNING"):
        result = _worker(settings, storage, clock, owner="costs-csv-failure").run_once()
    assert result.status is WorkerIterationStatus.FAILED
    assert "COSTS_CSV_DERIVED_EXPORT_FAILED" in caplog.text
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.FAILED and job.run_id is not None
    run = storage.get_run(job.run_id)
    research_run = storage.get_research_run(job.run_id)
    assert run is not None and run.status is RunStatus.FAILED
    assert research_run is not None and research_run.status.value == "FAILED"
    assert "run_research" in (run.error or "")
    assert run.error == research_run.error
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE run_id=?", (job.run_id,)).fetchone()[0] == 1
    assert storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job_id).status is JobStatus.FAILED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_unexpected_pipeline_error_after_run_initialization_fails_job_and_research_atomically(
    settings, account, monkeypatch,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="unexpected-after-init")

    class UnexpectedPipelineFailure(FakeResearchClient):
        def run_research(self, plan):
            raise RuntimeError("controlled unexpected pipeline exception")

    monkeypatch.setattr(
        runner, "_build_research_client", lambda *_args, **_kwargs: UnexpectedPipelineFailure(),
    )
    result = _worker(settings, storage, clock, owner="unexpected-after-init").run_once()
    assert result.status is WorkerIterationStatus.FAILED
    assert result.detail.startswith("UNEXPECTED_RESEARCH_PIPELINE_EXCEPTION")
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.FAILED and job.run_id is not None
    run = storage.get_run(job.run_id)
    research_run = storage.get_research_run(job.run_id)
    expected_error = "UNEXPECTED_RESEARCH_PIPELINE_EXCEPTION"
    assert run is not None and run.status is RunStatus.FAILED and run.error.startswith(expected_error)
    assert research_run is not None and research_run.status.value == "FAILED"
    assert research_run.error.startswith(expected_error)
    assert job.last_error.startswith(expected_error)
    assert storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    assert next(item for item in storage.list_topics(account.id) if item.id == topic.id).status is TopicStatus.SELECTED
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(job_id)
        assert persisted is not None and persisted.status is JobStatus.FAILED
        assert reopened.get_run(persisted.run_id).error.startswith(expected_error)
        assert reopened.get_research_run(persisted.run_id).error.startswith(expected_error)
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomically_failed_research_does_not_call_generic_fail_job(settings, account, monkeypatch):
    """WORKFLOW_FAILED owns a complete atomic failure and forbids worker cleanup writes."""
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="no-generic-fail")

    class ExpectedResearchFailure(FakeResearchClient):
        def run_research(self, plan):
            raise ResearchError(
                "controlled terminal research failure",
                usage=Usage(input_tokens=10, output_tokens=2, web_search_requests=1),
                model="controlled-failure-model",
            )

    heartbeat_calls = 0
    generic_fail_calls = 0
    original_heartbeat = storage.heartbeat_job_lease
    original_fail_job = storage.fail_job

    def heartbeat_spy(*args, **kwargs):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls > 2:
            raise AssertionError("forbidden heartbeat after workflow terminalization")
        return original_heartbeat(*args, **kwargs)

    def generic_fail_spy(*args, **kwargs):
        nonlocal generic_fail_calls
        generic_fail_calls += 1
        return original_fail_job(*args, **kwargs)

    monkeypatch.setattr(runner, "_build_research_client", lambda *_args, **_kwargs: ExpectedResearchFailure())
    monkeypatch.setattr(storage, "heartbeat_job_lease", heartbeat_spy)
    monkeypatch.setattr(storage, "fail_job", generic_fail_spy)

    result = _worker(settings, storage, clock, owner="no-generic-fail").run_once()
    assert result.status is WorkerIterationStatus.FAILED
    assert result.detail == "Research dry-run failed."
    assert generic_fail_calls == 0
    assert heartbeat_calls == 2

    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.FAILED and job.run_id is not None
    run = storage.get_run(job.run_id)
    research_run = storage.get_research_run(job.run_id)
    assert run is not None and run.status is RunStatus.FAILED
    assert research_run is not None and research_run.status.value == "FAILED"
    assert job.last_error == run.error == research_run.error
    assert "run_research" in (job.last_error or "")
    terminal_snapshot = _full_execution_snapshot(storage)
    terminal_timestamps = (job.updated_at, job.finished_at, run.finished_at, research_run.updated_at)
    assert all(value is not None for value in terminal_timestamps)
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted_job = reopened.get_job(job_id)
        assert persisted_job is not None and persisted_job.status is JobStatus.FAILED
        assert _full_execution_snapshot(reopened) == terminal_snapshot
        persisted_run = reopened.get_run(persisted_job.run_id)
        persisted_research = reopened.get_research_run(persisted_job.run_id)
        assert persisted_run is not None and persisted_research is not None
        assert (
            persisted_job.updated_at,
            persisted_job.finished_at,
            persisted_run.finished_at,
            persisted_research.updated_at,
        ) == terminal_timestamps
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_dispatch_result_rejects_non_enum_terminalization():
    class ForeignTerminalization(Enum):
        TERMINAL = "WORKFLOW_TERMINALIZED"

    for invalid_mode in (
        "WORKFLOW_TERMINALIZED",
        "WORKFLOW_FAILED",
        None,
        ForeignTerminalization.TERMINAL,
        1,
    ):
        with pytest.raises(TypeError):
            DispatchResult(terminalization=invalid_mode)
    with pytest.raises(TypeError):
        DispatchResult()


def test_worker_rejects_malformed_dispatch_terminalization_without_canonical_write(
    settings, account, monkeypatch,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    _enable_offline_worker(storage, clock)
    job = storage.enqueue_job(Job(
        id="malformed-dispatch-local",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="restart-acceptance:malformed-dispatch-local",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=clock.now(),
        created_at=clock.now(),
        max_attempts=2,
    ))
    snapshot_at_dispatch_return: list[dict[str, list[tuple]]] = []

    class MalformedDispatcher:
        def dispatch(self, _job, *, lease_owner, heartbeat):
            result = DispatchResult.worker_must_complete()
            object.__setattr__(result, "terminalization", "WORKFLOW_TERMINALIZED")
            snapshot_at_dispatch_return.append(_full_execution_snapshot(storage))
            return result

    heartbeat_calls = 0
    complete_calls = 0
    fail_calls = 0
    original_heartbeat = storage.heartbeat_job_lease
    original_complete = storage.complete_job
    original_fail = storage.fail_job

    def heartbeat_spy(*args, **kwargs):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        return original_heartbeat(*args, **kwargs)

    def complete_spy(*args, **kwargs):
        nonlocal complete_calls
        complete_calls += 1
        return original_complete(*args, **kwargs)

    def fail_spy(*args, **kwargs):
        nonlocal fail_calls
        fail_calls += 1
        return original_fail(*args, **kwargs)

    monkeypatch.setattr(storage, "heartbeat_job_lease", heartbeat_spy)
    monkeypatch.setattr(storage, "complete_job", complete_spy)
    monkeypatch.setattr(storage, "fail_job", fail_spy)

    with pytest.raises(DispatchContractError, match="invalid terminalization"):
        _worker(
            settings, storage, clock, owner="malformed-dispatch-local",
            dispatcher=MalformedDispatcher(),
        ).run_once()

    assert heartbeat_calls == 1
    assert complete_calls == 0
    assert fail_calls == 0
    assert len(snapshot_at_dispatch_return) == 1
    assert _full_execution_snapshot(storage) == snapshot_at_dispatch_return[0]
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == snapshot_at_dispatch_return[0]
        persisted_job = reopened.get_job(job.id)
        assert persisted_job is not None and persisted_job.status is JobStatus.RUNNING
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_malformed_dispatch_result_cannot_overwrite_atomically_terminalized_success(
    settings, account, monkeypatch,
):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic = _selected_topic(storage, account)
    _enable_offline_worker(storage, clock)
    job_id = _enqueue_research(storage, account, topic, clock, job_id="malformed-after-success")
    policy = PolicyEngine(settings, storage, clock)
    delegated = JobDispatcher(settings=settings, storage=storage, policy=policy, clock=clock)
    snapshot_after_terminalization: list[dict[str, list[tuple]]] = []

    class MalformedAfterSuccessDispatcher:
        def dispatch(self, job, *, lease_owner, heartbeat):
            result = delegated.dispatch(job, lease_owner=lease_owner, heartbeat=heartbeat)
            object.__setattr__(result, "terminalization", "WORKFLOW_TERMINALIZED")
            snapshot_after_terminalization.append(_full_execution_snapshot(storage))
            return result

    heartbeat_calls = 0
    complete_calls = 0
    fail_calls = 0
    original_heartbeat = storage.heartbeat_job_lease
    original_complete = storage.complete_job
    original_fail = storage.fail_job

    def heartbeat_spy(*args, **kwargs):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls > 2:
            raise AssertionError("forbidden heartbeat after atomically terminalized success")
        return original_heartbeat(*args, **kwargs)

    def complete_spy(*args, **kwargs):
        nonlocal complete_calls
        complete_calls += 1
        return original_complete(*args, **kwargs)

    def fail_spy(*args, **kwargs):
        nonlocal fail_calls
        fail_calls += 1
        return original_fail(*args, **kwargs)

    monkeypatch.setattr(storage, "heartbeat_job_lease", heartbeat_spy)
    monkeypatch.setattr(storage, "complete_job", complete_spy)
    monkeypatch.setattr(storage, "fail_job", fail_spy)

    with pytest.raises(DispatchContractError, match="invalid terminalization"):
        _worker(
            settings, storage, clock, owner="malformed-after-success",
            dispatcher=MalformedAfterSuccessDispatcher(),
        ).run_once()

    assert heartbeat_calls == 2
    assert complete_calls == 0
    assert fail_calls == 0
    assert len(snapshot_after_terminalization) == 1
    assert _full_execution_snapshot(storage) == snapshot_after_terminalization[0]
    job = storage.get_job(job_id)
    assert job is not None and job.status is JobStatus.DONE and job.run_id is not None
    run = storage.get_run(job.run_id)
    research_run = storage.get_research_run(job.run_id)
    assert run is not None and run.status is RunStatus.DRY_RUN
    assert research_run is not None and research_run.status.value == "COMPLETE"
    assert research_run.research_card_id is not None
    assert storage.get_research_card(research_run.research_card_id) is not None
    assert next(item for item in storage.list_topics(account.id) if item.id == topic.id).status is TopicStatus.USED
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _full_execution_snapshot(reopened) == snapshot_after_terminalization[0]
        persisted_job = reopened.get_job(job_id)
        assert persisted_job is not None and persisted_job.status is JobStatus.DONE
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_atomic_research_success_preserves_primary_error_when_rollback_fails(settings, account):
    clock = MutableUtcClock()
    storage = SqliteStorage.open(settings.db_path)
    topic, job_id = _claim_and_start_research(
        storage, account, clock, job_id="success-primary-error", owner="worker-success",
    )
    initialized = storage.initialize_research_run_for_job(
        job_id, "worker-success", "success-primary-error-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_id, lease_owner="worker-success", run_id=initialized.run.id, clock=clock,
    )
    storage.conn = RollbackFailingConnection(
        storage.conn, sql_fragment="UPDATE jobs SET status='DONE'",
    )

    with pytest.raises(ProcessCrash, match="inside atomic research initialization") as caught:
        storage.finalize_job_research_execution(
            execution, _job_execution_card(int(topic.id)), 0.0,
            terminal_run_status=RunStatus.DRY_RUN,
        )
    assert any(
        "Secondary SQLite rollback failure" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.RUNNING and job.lease_owner == "worker-success"
        assert reopened.get_run(initialized.run.id).status is RunStatus.DRY_RUN
        assert reopened.get_research_run(initialized.run.id).status.value == "PENDING"
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert next(item for item in reopened.list_topics(account.id) if item.id == topic.id).status is TopicStatus.SELECTED
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()
