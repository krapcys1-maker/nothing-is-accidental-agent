"""Deterministyczne testy planowania jobów Etapu 1, bez API i bez sleep()."""
from __future__ import annotations

import threading
from datetime import datetime, time, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.main import main
from app.models import Job, JobKind, JobStatus, Topic, TopicStatus, WorkflowType
from app.ports.storage import JobConflictError
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
from app.storage.repositories import SqliteStorage


UTC = timezone.utc
NOW = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)  # Monday, 11:00 in Europe/Bucharest.


def _window(days: set[int] | frozenset[int], start: str = "09:00", end: str = "17:00") -> EditorialWindow:
    return EditorialWindow(frozenset(days), time.fromisoformat(start), time.fromisoformat(end))


def _policy(*windows: EditorialWindow, timezone_name: str = "Europe/Bucharest") -> SchedulingPolicy:
    return SchedulingPolicy(timezone_name=timezone_name, windows=tuple(windows or (_window(set(range(5))),)))


def _topic(storage: SqliteStorage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Scheduling topic",
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


def _enqueuer(storage: SqliteStorage, now: datetime = NOW) -> ScheduledJobEnqueuer:
    return ScheduledJobEnqueuer(
        storage=storage,
        scheduling_policy=_policy(),
        clock=FixedClock(now),
    )


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
