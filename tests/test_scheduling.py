"""Deterministyczne testy planowania jobów Etapu 1, bez API i bez sleep()."""
from __future__ import annotations

from dataclasses import replace
import threading
from datetime import datetime, time, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.main import main
from app.models import Job, JobKind, JobStatus, Run, Topic, TopicStatus, WorkflowType
from app.orchestrator import runner
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import JobConflictError
from app.research.fake_client import FakeResearchClient
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.scheduling import (
    MAX_SCHEDULE_REASON_LENGTH,
    EditorialWindow,
    ImmediateSchedulingContract,
    ScheduleReason,
    SchedulingPolicy,
    SchedulingValidationError,
    calculate_schedule,
)
import app.scheduler.worker as worker_module
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage


UTC = timezone.utc
NOW = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)  # Monday, 11:00 in Europe/Bucharest.


def _window(days: set[int] | frozenset[int], start: str = "09:00", end: str = "17:00") -> EditorialWindow:
    return EditorialWindow(frozenset(days), time.fromisoformat(start), time.fromisoformat(end))


def _policy(*windows: EditorialWindow, timezone_name: str = "Europe/Bucharest") -> SchedulingPolicy:
    return SchedulingPolicy(timezone_name=timezone_name, windows=tuple(windows or (_window(set(range(5))),)))


def _topic(storage: SqliteStorage, account, *, title: str = "Scheduling topic") -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=title,
        question="When should dry-run work begin?",
        score=90,
        status=TopicStatus.SELECTED,
    ))


def _request(account, topic_id: int, *, job_id: str = "scheduled-job", key: str = "scheduled-key",
             requested_at: datetime | None = None) -> ScheduledJobRequest:
    return ScheduledJobRequest(
        id=job_id,
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=key,
        topic_id=topic_id,
        payload={"account_id": account.id, "topic_id": topic_id, "dry_run": True},
        requested_at=requested_at,
    )


def _enqueuer(
    storage: SqliteStorage,
    now: datetime = NOW,
    policy: SchedulingPolicy | None = None,
) -> ScheduledJobEnqueuer:
    return ScheduledJobEnqueuer(
        storage=storage,
        scheduling_policy=policy or _policy(),
        clock=FixedClock(now),
    )


class DispatchSpy:
    def __init__(self, delegate=None) -> None:
        self._delegate = delegate
        self.calls = 0
        self.local_calls = 0
        self.research_calls = 0

    def dispatch(self, job: Job, *, lease_owner: str, heartbeat):
        self.calls += 1
        if self._delegate is None:
            return None
        if job.kind is JobKind.LOCAL:
            self.local_calls += 1
        if job.kind is JobKind.RESEARCH:
            self.research_calls += 1
        return self._delegate.dispatch(job, lease_owner=lease_owner, heartbeat=heartbeat)


class StorageCallSpy:
    def __init__(self, delegate: SqliteStorage) -> None:
        self._delegate = delegate
        self.create_run_calls = 0
        self.create_research_run_calls = 0
        self.reserve_job_budget_calls = 0

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def create_run(self, *args, **kwargs):
        self.create_run_calls += 1
        return self._delegate.create_run(*args, **kwargs)

    def create_research_run(self, *args, **kwargs):
        self.create_research_run_calls += 1
        return self._delegate.create_research_run(*args, **kwargs)

    def reserve_job_budget(self, *args, **kwargs):
        self.reserve_job_budget_calls += 1
        return self._delegate.reserve_job_budget(*args, **kwargs)


class PolicyEngineSpy:
    def __init__(self, delegate: PolicyEngine) -> None:
        self._delegate = delegate
        self.worker_runtime_calls = 0

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    @property
    def post_claim_calls(self) -> int:
        return max(0, self.worker_runtime_calls - 1)

    def check_worker_runtime(self, *args, **kwargs):
        self.worker_runtime_calls += 1
        return self._delegate.check_worker_runtime(*args, **kwargs)


class ResearchExecutionSpy:
    def __init__(self) -> None:
        self.pipeline_calls = 0
        self.client_factory_calls = 0
        self.client_calls = 0

    def pipeline(self, *args, **kwargs):
        self.pipeline_calls += 1
        return runner.run_research_dry_run(*args, **kwargs)

    def build_client(self, *_args, **_kwargs):
        self.client_factory_calls += 1
        owner = self

        class CountingFakeResearchClient(FakeResearchClient):
            def run_research(self, plan):
                owner.client_calls += 1
                return super().run_research(plan)

        return CountingFakeResearchClient("good")


class HeartbeatStorageFactorySpy:
    def __init__(self, db_path) -> None:
        self._db_path = db_path
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return SqliteStorage.open(self._db_path)


def _enable_offline_worker(storage: SqliteStorage, now: datetime) -> None:
    for key, value in {
        "kill_switch": False,
        "worker_enabled": True,
        "safe_mode": False,
        "paid_actions_enabled": False,
        "browser_actions_enabled": False,
    }.items():
        storage.set_system_flag(key, value, updated_by="test", reason="scheduling", now=now)


def _worker(
    settings,
    storage,
    now: datetime,
    dispatcher: DispatchSpy,
    *,
    policy=None,
    heartbeat_storage_factory=None,
) -> Worker:
    clock = FixedClock(now)
    return Worker(
        storage=storage,
        policy=policy or PolicyEngine(settings, storage, clock),
        dispatcher=dispatcher,
        lease_owner="scheduling-worker",
        lease_seconds=30,
        heartbeat_interval_seconds=5.0,
        heartbeat_startup_timeout_seconds=1.0,
        heartbeat_shutdown_timeout_seconds=1.0,
        heartbeat_storage_factory=heartbeat_storage_factory or (
            lambda: SqliteStorage.open(settings.db_path)
        ),
        clock=clock,
        sleeper=lambda _: None,
    )


def _job_snapshot(storage: SqliteStorage, job_id: str) -> dict:
    job = storage.get_job(job_id)
    assert job is not None
    return job.model_dump(mode="python")


def _execution_counts(storage: SqliteStorage) -> dict[str, int]:
    return {
        "jobs": int(storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0]),
        "runs": int(storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0]),
        "research_runs": int(
            storage.conn.execute("SELECT count(*) FROM research_runs").fetchone()[0]
        ),
    }


def _assert_conflict_preserves_job(settings, storage, original_job: Job, conflicting_request) -> None:
    before_job = _job_snapshot(storage, original_job.id)
    before_counts = _execution_counts(storage)
    assert before_job["reserved_cost_usd"] == 0.0
    assert before_job["budget_reserved_at"] is None

    with pytest.raises(JobConflictError, match="idempotency_key"):
        _enqueuer(storage).enqueue(conflicting_request)

    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _execution_counts(reopened) == before_counts
        assert before_counts["jobs"] == 1
        assert _job_snapshot(reopened, original_job.id) == before_job
        assert reopened.conn.execute("SELECT id FROM jobs").fetchone()[0] == original_job.id
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_schedule_inside_editorial_window_runs_immediately():
    decision = calculate_schedule(_policy(), now=NOW)

    assert decision.earliest_run_at == NOW
    assert decision.reason is ScheduleReason.WITHIN_EDITORIAL_WINDOW


def test_schedule_before_window_moves_to_window_start():
    decision = calculate_schedule(_policy(), now=datetime(2026, 7, 13, 5, 0, tzinfo=UTC))

    assert decision.earliest_run_at == datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
    assert decision.reason is ScheduleReason.DEFERRED_TO_WINDOW_START


def test_schedule_after_window_moves_to_next_window():
    decision = calculate_schedule(_policy(), now=datetime(2026, 7, 13, 15, 0, tzinfo=UTC))

    assert decision.earliest_run_at == datetime(2026, 7, 14, 6, 0, tzinfo=UTC)


def test_schedule_on_weekend_moves_to_next_allowed_day():
    decision = calculate_schedule(_policy(), now=datetime(2026, 7, 17, 15, 0, tzinfo=UTC))

    assert decision.earliest_run_at == datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


def test_schedule_requested_future_time_inside_window_is_respected():
    requested = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)  # 12:30 local.
    decision = calculate_schedule(_policy(), now=NOW, requested_at=requested)

    assert decision.earliest_run_at == requested
    assert decision.reason is ScheduleReason.REQUESTED_FUTURE_TIME


def test_schedule_requested_time_outside_window_is_deferred():
    requested = datetime(2026, 7, 14, 15, 30, tzinfo=UTC)  # 18:30 local.
    decision = calculate_schedule(_policy(), now=NOW, requested_at=requested)

    assert decision.earliest_run_at == datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
    assert decision.reason is ScheduleReason.REQUESTED_TIME_DEFERRED_TO_WINDOW


def test_requested_time_in_the_past_fails_closed():
    with pytest.raises(SchedulingValidationError, match="past"):
        calculate_schedule(_policy(), now=NOW, requested_at=NOW - timedelta(seconds=1))


def test_schedule_is_persisted_as_utc(storage, account):
    topic = _topic(storage, account)
    result = _enqueuer(storage, datetime(2026, 7, 13, 5, 0, tzinfo=UTC)).enqueue(
        _request(account, int(topic.id)),
    )
    stored = storage.conn.execute(
        "SELECT earliest_run_at FROM jobs WHERE id=?", (result.job.id,),
    ).fetchone()["earliest_run_at"]

    assert result.decision.earliest_run_at.tzinfo is UTC
    assert stored == "2026-07-13 06:00:00"


def test_schedule_uses_explicit_timezone():
    bucharest = calculate_schedule(_policy(timezone_name="Europe/Bucharest"), now=datetime(2026, 7, 13, 6, 0, tzinfo=UTC))
    london = calculate_schedule(_policy(timezone_name="Europe/London"), now=datetime(2026, 7, 13, 6, 0, tzinfo=UTC))

    assert bucharest.earliest_run_at == datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
    assert london.earliest_run_at == datetime(2026, 7, 13, 8, 0, tzinfo=UTC)


def test_schedule_handles_spring_dst_boundary_deterministically():
    policy = _policy(_window({6}, "03:00", "05:00"))
    decision = calculate_schedule(policy, now=datetime(2026, 3, 28, 21, 0, tzinfo=UTC))

    assert decision.earliest_run_at == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)


def test_schedule_handles_fall_dst_boundary_deterministically():
    policy = _policy(_window({6}, "03:00", "05:00"))
    decision = calculate_schedule(policy, now=datetime(2026, 10, 24, 20, 0, tzinfo=UTC))

    assert decision.earliest_run_at == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)


def test_invalid_timezone_fails_closed():
    with pytest.raises(SchedulingValidationError, match="unknown"):
        _policy(timezone_name="Europe/Not-A-Timezone")


@pytest.mark.parametrize("window", [
    lambda: EditorialWindow(frozenset(), time(9), time(10)),
    lambda: EditorialWindow(frozenset({0}), time(9), time(9)),
])
def test_invalid_editorial_window_fails_closed(window):
    with pytest.raises(SchedulingValidationError):
        window()


def test_overlapping_editorial_windows_fail_closed():
    with pytest.raises(SchedulingValidationError, match="overlap"):
        _policy(_window({0}, "09:00", "12:00"), _window({0}, "11:00", "14:00"))


def test_cross_midnight_window_is_rejected_if_unsupported():
    with pytest.raises(SchedulingValidationError, match="cross-midnight"):
        _window({0}, "22:00", "02:00")


def test_schedule_reason_persists_after_reopen(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    result = _enqueuer(storage).enqueue(_request(account, int(topic.id)))
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(result.job.id)
        assert persisted is not None
        assert persisted.schedule_reason == ScheduleReason.WITHIN_EDITORIAL_WINDOW.value
    finally:
        reopened.close()


def test_worker_does_not_claim_job_before_earliest_run_at(storage, account):
    topic = _topic(storage, account)
    job = _enqueuer(storage).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    )).job

    assert storage.claim_next_job("worker", 30, now=NOW) is None
    persisted = storage.get_job(job.id)
    assert persisted is not None and persisted.status is JobStatus.QUEUED


def test_worker_claims_job_at_earliest_run_at_boundary(storage, account):
    topic = _topic(storage, account)
    job = _enqueuer(storage).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    )).job

    lease = storage.claim_next_job("worker", 30, now=job.earliest_run_at)
    assert lease is not None and lease.job.id == job.id


def test_future_job_does_not_increment_attempts(storage, account):
    topic = _topic(storage, account)
    job = _enqueuer(storage).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    )).job

    assert storage.claim_next_job("worker", 30, now=NOW) is None
    assert storage.get_job(job.id).attempts == 0


def test_future_job_does_not_receive_lease(storage, account):
    topic = _topic(storage, account)
    job = _enqueuer(storage).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    )).job

    assert storage.claim_next_job("worker", 30, now=NOW) is None
    persisted = storage.get_job(job.id)
    assert persisted.lease_owner is None and persisted.lease_expires_at is None


def test_worker_run_once_does_not_dispatch_future_job(settings, storage, account):
    _enable_offline_worker(storage, NOW)
    topic = _topic(storage, account)
    _enqueuer(storage).enqueue(_request(account, int(topic.id), requested_at=NOW + timedelta(days=1)))
    dispatcher = DispatchSpy()

    result = _worker(settings, storage, NOW, dispatcher).run_once()

    assert result.status is WorkerIterationStatus.IDLE
    assert dispatcher.calls == 0
    assert dispatcher.research_calls == 0


def test_future_job_full_snapshot_is_unchanged_after_worker_run_once(
    settings, account, monkeypatch,
):
    store = SqliteStorage.open(settings.db_path)
    try:
        _enable_offline_worker(store, NOW)
        topic = _topic(store, account)
        job = _enqueuer(store).enqueue(_request(
            account, int(topic.id), requested_at=NOW + timedelta(days=1),
        )).job
        before_job = _job_snapshot(store, job.id)
        before_counts = _execution_counts(store)
        storage_spy = StorageCallSpy(store)
        clock = FixedClock(NOW)
        policy_spy = PolicyEngineSpy(PolicyEngine(settings, storage_spy, clock))
        research_spy = ResearchExecutionSpy()
        monkeypatch.setattr(runner, "_build_research_client", research_spy.build_client)
        dispatcher = DispatchSpy(JobDispatcher(
            settings=settings,
            storage=storage_spy,
            policy=policy_spy,
            clock=clock,
            research_dry_run=research_spy.pipeline,
        ))
        heartbeat_factory = HeartbeatStorageFactorySpy(settings.db_path)
        original_guard = worker_module.HeartbeatGuard

        class HeartbeatGuardSpy(original_guard):
            instances = 0
            starts = 0

            def __init__(self, *args, **kwargs):
                type(self).instances += 1
                super().__init__(*args, **kwargs)

            def start(self):
                type(self).starts += 1
                return super().start()

        monkeypatch.setattr(worker_module, "HeartbeatGuard", HeartbeatGuardSpy)

        result = _worker(
            settings,
            storage_spy,
            NOW,
            dispatcher,
            policy=policy_spy,
            heartbeat_storage_factory=heartbeat_factory,
        ).run_once()
        assert result.status is WorkerIterationStatus.IDLE
        assert dispatcher.calls == 0
        assert dispatcher.local_calls == 0
        assert dispatcher.research_calls == 0
        assert research_spy.pipeline_calls == 0
        assert research_spy.client_factory_calls == 0
        assert research_spy.client_calls == 0
        assert heartbeat_factory.calls == 0
        assert HeartbeatGuardSpy.instances == 0
        assert HeartbeatGuardSpy.starts == 0
        assert policy_spy.worker_runtime_calls == 1
        assert policy_spy.post_claim_calls == 0
        assert storage_spy.create_run_calls == 0
        assert storage_spy.create_research_run_calls == 0
        assert storage_spy.reserve_job_budget_calls == 0
        assert _job_snapshot(store, job.id) == before_job
        assert _execution_counts(store) == before_counts
        assert before_job["reserved_cost_usd"] == 0.0
        assert before_job["budget_reserved_at"] is None
        assert before_job["external_effect_started_at"] is None
    finally:
        store.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert _job_snapshot(reopened, job.id) == before_job
        assert _execution_counts(reopened) == before_counts
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_worker_run_once_claims_job_at_schedule_boundary(settings, storage, account):
    _enable_offline_worker(storage, NOW)
    topic = _topic(storage, account)
    scheduled = _enqueuer(storage).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    ))
    boundary = scheduled.decision.earliest_run_at
    worker_now = boundary
    persisted_timestamp = storage.conn.execute(
        "SELECT earliest_run_at FROM jobs WHERE id=?", (scheduled.job.id,),
    ).fetchone()["earliest_run_at"]
    dispatcher = DispatchSpy()

    assert boundary.tzinfo is not None
    assert boundary.utcoffset() == timedelta(0)
    assert worker_now == scheduled.decision.earliest_run_at
    assert persisted_timestamp == boundary.strftime("%Y-%m-%d %H:%M:%S")

    result = _worker(settings, storage, worker_now, dispatcher).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert dispatcher.calls == 1
    assert dispatcher.research_calls == 0


def test_two_workers_do_not_claim_future_job(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    job = _enqueuer(setup).enqueue(_request(
        account, int(topic.id), requested_at=NOW + timedelta(days=1),
    )).job
    setup.close()

    barrier = threading.Barrier(2)
    results: list[object] = []

    def claim(owner: str) -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(store.claim_next_job(owner, 30, now=NOW))
        finally:
            store.close()

    threads = [threading.Thread(target=claim, args=(owner,)) for owner in ("worker-a", "worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert results == [None, None]
        persisted = reopened.get_job(job.id)
        assert persisted.status is JobStatus.QUEUED and persisted.attempts == 0
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_scheduling_does_not_change_system_flags(storage, account):
    storage.set_system_flag("kill_switch", True, updated_by="test", reason="unchanged", now=NOW)
    storage.set_system_flag("worker_enabled", False, updated_by="test", reason="unchanged", now=NOW)
    before = storage.conn.execute("SELECT key,value_json FROM system_flags ORDER BY key").fetchall()
    topic = _topic(storage, account)

    _enqueuer(storage).enqueue(_request(account, int(topic.id)))

    after = storage.conn.execute("SELECT key,value_json FROM system_flags ORDER BY key").fetchall()
    assert [(row["key"], row["value_json"]) for row in after] == [
        (row["key"], row["value_json"]) for row in before
    ]


def test_idempotent_enqueue_preserves_original_schedule(storage, account):
    topic = _topic(storage, account)
    first = _enqueuer(storage).enqueue(_request(account, int(topic.id), job_id="first", key="same-key"))
    repeated = _enqueuer(storage).enqueue(_request(account, int(topic.id), job_id="second", key="same-key"))

    assert repeated.job.id == first.job.id
    assert repeated.job.earliest_run_at == first.job.earliest_run_at
    assert repeated.job.schedule_reason == first.job.schedule_reason
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_idempotent_enqueue_after_time_change_returns_original_job(storage, account):
    topic = _topic(storage, account)
    first = _enqueuer(storage, NOW).enqueue(_request(account, int(topic.id), job_id="first", key="same-key"))
    retried = _enqueuer(storage, NOW + timedelta(hours=8)).enqueue(
        _request(account, int(topic.id), job_id="retry", key="same-key"),
    )

    assert retried.job.id == first.job.id
    assert retried.job.earliest_run_at == first.job.earliest_run_at
    assert retried.job.schedule_reason == first.job.schedule_reason
    assert retried.decision.earliest_run_at == first.decision.earliest_run_at
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_idempotent_enqueue_after_policy_change_preserves_original_schedule(storage, account):
    topic = _topic(storage, account)
    first = _enqueuer(storage).enqueue(_request(account, int(topic.id), job_id="first", key="same-key"))
    changed_policy = _policy(_window({0}, "10:00", "11:00"), timezone_name="Europe/London")

    retried = _enqueuer(storage, NOW, changed_policy).enqueue(
        _request(account, int(topic.id), job_id="retry", key="same-key"),
    )

    assert retried.job.id == first.job.id
    assert retried.job.earliest_run_at == first.job.earliest_run_at
    assert retried.job.schedule_reason == first.job.schedule_reason
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_idempotent_enqueue_conflicts_on_different_topic(settings, storage, account):
    first_topic = _topic(storage, account, title="First scheduling topic")
    other_topic = _topic(storage, account, title="Second scheduling topic")
    original = _request(account, int(first_topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-topic", topic_id=int(other_topic.id)),
    )


def test_idempotent_enqueue_conflicts_on_different_account(settings, storage, account):
    first_topic = _topic(storage, account, title="First account topic")
    other_account = account.model_copy(update={"id": "other-scheduling-account"})
    storage.ensure_account(other_account)
    original = _request(account, int(first_topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-account", account_id=other_account.id),
    )


def test_idempotent_enqueue_conflicts_on_different_payload(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-payload", payload={**original.payload, "variant": "different"}),
    )


def test_idempotent_enqueue_conflicts_on_different_kind(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-kind", kind=JobKind.LOCAL),
    )


def test_idempotent_enqueue_conflicts_on_different_workflow(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-workflow", workflow=WorkflowType.ARTICLE),
    )


def test_idempotent_enqueue_conflicts_on_different_priority(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-priority", priority=1),
    )


def test_idempotent_enqueue_conflicts_on_different_deadline(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-deadline", deadline_at=NOW + timedelta(days=2)),
    )


def test_idempotent_enqueue_conflicts_on_different_max_attempts(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-max-attempts", max_attempts=2),
    )


def test_idempotent_enqueue_conflicts_on_different_run_id(settings, storage, account):
    topic = _topic(storage, account)
    # A distinct valid run_id must refer to a persisted run.  The right
    # invariant is therefore no growth from 1 -> 1, not an artificial 0 -> 0.
    prepared_run = storage.create_run(Run(
        id="existing-conflict-run",
        account_id=account.id,
        workflow=WorkflowType.RESEARCH,
        started_at=NOW,
    ))
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job
    runs_before = _execution_counts(storage)["runs"]
    prepared_run_before = storage.get_run(prepared_run.id)
    job_before = _job_snapshot(storage, first.id)

    assert runs_before == 1
    assert prepared_run_before is not None
    assert first.run_id is None

    with pytest.raises(JobConflictError, match="idempotency_key"):
        _enqueuer(storage).enqueue(
            replace(original, id="different-run", run_id=prepared_run.id),
        )

    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        counts_after = _execution_counts(reopened)
        persisted_job = reopened.get_job(first.id)
        persisted_run = reopened.get_run(prepared_run.id)

        assert counts_after["jobs"] == 1
        assert counts_after["runs"] == runs_before == 1
        assert counts_after["research_runs"] == 0
        assert persisted_job is not None
        assert persisted_job.run_id == first.run_id is None
        assert _job_snapshot(reopened, first.id) == job_before
        assert persisted_run is not None
        assert persisted_run.model_dump(mode="python") == prepared_run_before.model_dump(mode="python")
        assert job_before["reserved_cost_usd"] == 0.0
        assert job_before["budget_reserved_at"] is None
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_idempotent_enqueue_conflicts_on_different_dry_run_payload(settings, storage, account):
    topic = _topic(storage, account)
    original = _request(account, int(topic.id), key="same-key")
    first = _enqueuer(storage).enqueue(original).job
    conflicting_payload = {**original.payload, "dry_run": False}

    _assert_conflict_preserves_job(
        settings, storage, first,
        replace(original, id="different-dry-run", payload=conflicting_payload),
    )


def test_idempotent_enqueue_with_changed_requested_at_returns_original_schedule(storage, account):
    topic = _topic(storage, account)
    first = _enqueuer(storage).enqueue(_request(account, int(topic.id), key="same-key"))

    retried = _enqueuer(storage).enqueue(
        _request(account, int(topic.id), key="same-key", requested_at=NOW + timedelta(days=1)),
    )

    assert retried.job.id == first.job.id
    assert retried.job.earliest_run_at == first.job.earliest_run_at
    assert retried.job.schedule_reason == first.job.schedule_reason


def test_concurrent_idempotent_enqueue_creates_one_job(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    setup.close()
    barrier = threading.Barrier(2)
    results: list[object] = []
    failures: list[BaseException] = []

    def enqueue(job_id: str) -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(_enqueuer(store).enqueue(_request(
                account, int(topic.id), job_id=job_id, key="concurrent-key",
            )))
        except BaseException as exc:
            failures.append(exc)
        finally:
            store.close()

    threads = [threading.Thread(target=enqueue, args=(job_id,)) for job_id in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert failures == []
        assert len({result.job.id for result in results}) == 1
        assert reopened.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_concurrent_idempotent_enqueue_with_different_now_creates_one_job(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    setup.close()
    first_now = NOW
    second_now = NOW + timedelta(hours=8)
    expected_decisions = {
        calculate_schedule(_policy(), now=first_now),
        calculate_schedule(_policy(), now=second_now),
    }
    barrier = threading.Barrier(2)
    results: list[object] = []
    failures: list[BaseException] = []

    def enqueue(job_id: str, now: datetime) -> None:
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(_enqueuer(store, now).enqueue(_request(
                account, int(topic.id), job_id=job_id, key="concurrent-different-now",
            )))
        except BaseException as exc:
            failures.append(exc)
        finally:
            store.close()

    threads = [
        threading.Thread(target=enqueue, args=("first", first_now)),
        threading.Thread(target=enqueue, args=("second", second_now)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert failures == []
        assert len(results) == 2
        persisted = reopened.get_job(results[0].job.id)
        assert persisted is not None
        assert len({result.job.id for result in results}) == 1
        persisted_schedule = (results[0].decision.earliest_run_at, results[0].decision.reason)
        assert persisted_schedule in {
            (decision.earliest_run_at, decision.reason) for decision in expected_decisions
        }
        assert all(result.decision.earliest_run_at == persisted_schedule[0] for result in results)
        assert all(result.decision.reason.value == persisted.schedule_reason for result in results)
        assert reopened.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_concurrent_idempotent_enqueue_with_conflicting_payload_accepts_one_and_rejects_one(
    settings, account,
):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    setup.close()
    barrier = threading.Barrier(2)
    successes: list[tuple[dict, object]] = []
    failures: list[tuple[dict, BaseException]] = []

    def enqueue(job_id: str, dry_run: bool) -> None:
        store = SqliteStorage.open(settings.db_path)
        request = _request(
            account, int(topic.id), job_id=job_id, key="concurrent-conflicting-payload",
        )
        payload = {**request.payload, "dry_run": dry_run}
        try:
            barrier.wait(timeout=5)
            result = _enqueuer(store).enqueue(replace(request, payload=payload))
            successes.append((payload, result))
        except BaseException as exc:
            failures.append((payload, exc))
        finally:
            store.close()

    threads = [
        threading.Thread(target=enqueue, args=("dry-run-true", True)),
        threading.Thread(target=enqueue, args=("dry-run-false", False)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert len(successes) == 1
    assert len(failures) == 1
    winner_payload, winner = successes[0]
    loser_payload, failure = failures[0]
    assert isinstance(failure, JobConflictError)
    assert "idempotency_key" in str(failure)

    reopened = SqliteStorage.open(settings.db_path)
    try:
        counts = _execution_counts(reopened)
        assert counts == {"jobs": 1, "runs": 0, "research_runs": 0}
        persisted = reopened.get_job(winner.job.id)
        assert persisted is not None
        assert persisted.id == winner.job.id
        assert persisted.payload == winner_payload
        assert persisted.payload != loser_payload
        assert persisted.earliest_run_at == winner.job.earliest_run_at
        assert persisted.schedule_reason == winner.job.schedule_reason
        assert persisted.status is JobStatus.QUEUED
        assert persisted.attempts == 0
        assert persisted.lease_owner is None
        assert persisted.lease_expires_at is None
        assert persisted.last_error is None
        assert persisted.external_effect_started_at is None
        assert persisted.run_id is None
        assert persisted.reserved_cost_usd == 0.0
        assert persisted.budget_reserved_at is None
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_schedule_reason_is_controlled_and_bounded(storage, account):
    assert all(len(reason.value) <= MAX_SCHEDULE_REASON_LENGTH and "\n" not in reason.value
               for reason in ScheduleReason)
    storage.ensure_account(account)
    invalid = Job(
        id="invalid-reason",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="invalid-reason",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="uncontrolled reason",
        earliest_run_at=NOW,
        created_at=NOW,
    )

    with pytest.raises(JobConflictError, match="schedule_reason"):
        storage.enqueue_job(invalid)


def test_research_dry_run_is_scheduled_without_execution(storage, account):
    topic = _topic(storage, account)
    result = _enqueuer(storage).enqueue(_request(account, int(topic.id)))

    assert result.job.status is JobStatus.QUEUED
    assert result.job.payload == {"account_id": account.id, "topic_id": topic.id, "dry_run": True}
    assert storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0


def test_enqueue_research_cli_only_creates_dry_run_job(settings, account, monkeypatch, capsys):
    settings.editorial_schedule = {
        "timezone": "Europe/Bucharest",
        "windows": [{"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}],
    }
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    assert main(["enqueue-research", "--account-id", account.id, "--topic-id", str(topic.id)]) == 0

    verify = SqliteStorage.open(settings.db_path)
    try:
        job = verify.conn.execute("SELECT * FROM jobs").fetchone()
        assert job["kind"] == "RESEARCH"
        assert job["payload_json"] == f'{{"account_id":"{account.id}","dry_run":true,"topic_id":{topic.id}}}'
        assert "earliest_run_at_utc=" in capsys.readouterr().out
    finally:
        verify.close()


def test_enqueue_research_cli_does_not_start_worker_or_research(settings, account, monkeypatch):
    settings.editorial_schedule = {
        "timezone": "Europe/Bucharest",
        "windows": [{"weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}],
    }
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    setup.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    monkeypatch.setattr("app.main._build_worker", lambda *_: (_ for _ in ()).throw(AssertionError("worker")))
    monkeypatch.setattr("app.main.run_research", lambda **_: (_ for _ in ()).throw(AssertionError("research")))

    assert main(["enqueue-research", "--account-id", account.id, "--topic-id", str(topic.id)]) == 0


def test_enqueue_research_cli_rejects_unknown_real_mode():
    with pytest.raises(SystemExit) as captured:
        main(["enqueue-research", "--account-id", "x", "--topic-id", "1", "--real"])
    assert captured.value.code == 2


def test_immediate_requires_named_safety_contract():
    with pytest.raises(SchedulingValidationError):
        calculate_schedule(_policy(), now=NOW, immediate_contract="arbitrary")  # type: ignore[arg-type]

    decision = calculate_schedule(
        _policy(), now=datetime(2026, 7, 13, 5, 0, tzinfo=UTC),
        immediate_contract=ImmediateSchedulingContract.SAFETY_OPERATION,
    )
    assert decision.reason is ScheduleReason.SAFETY_OPERATION_IMMEDIATE
    assert decision.earliest_run_at == datetime(2026, 7, 13, 5, 0, tzinfo=UTC)
