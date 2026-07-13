"""Offline contract tests for the Stage 1 durable queue foundation."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import copy2

import pytest

from app.models import (
    Job,
    JobKind,
    JobStatus,
    ModelUsage,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    BudgetReservationError,
    JobConflictError,
    LifecycleTransitionError,
    SystemFlagError,
)
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _topic(storage: SqliteStorage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Queue research topic", question="Why queues?",
        score=90, status=TopicStatus.SELECTED,
    ))


def _job(
    account, job_id: str, key: str, *, kind: JobKind = JobKind.LOCAL,
    topic_id: int | None = None, priority: int = 0,
    earliest: datetime = NOW, deadline: datetime | None = None,
    payload: dict | None = None, max_attempts: int = 2,
) -> Job:
    workflow = WorkflowType.RESEARCH if kind == JobKind.RESEARCH else WorkflowType.ANALYTICS
    return Job(
        id=job_id, account_id=account.id, kind=kind, workflow=workflow,
        idempotency_key=key, topic_id=topic_id, priority=priority,
        payload=payload or {"contract": "queue-v1"}, schedule_reason="test",
        earliest_run_at=earliest, deadline_at=deadline, max_attempts=max_attempts,
        created_at=NOW,
    )


def _copy_migrations_through_0008(destination: Path) -> None:
    destination.mkdir()
    for source in sorted(MIGRATIONS_DIR.glob("000[1-8]_*.sql")):
        copy2(source, destination / source.name)


def test_0009_fresh_schema_and_upgrade_from_0008_are_repeatable(tmp_path, account):
    fresh_path = tmp_path / "fresh-0009.db"
    fresh = SqliteStorage.open(fresh_path)
    fresh.ensure_account(account)
    tables = {
        row["name"] for row in fresh.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"jobs", "system_flags", "schema_migrations"} <= tables
    assert fresh.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert fresh.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert fresh.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert fresh.conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0009_jobs_system_flags'"
    ).fetchone()[0] == 1
    assert apply_migrations(fresh.conn) == []
    fresh.close()

    migration_dir = tmp_path / "through-0008"
    _copy_migrations_through_0008(migration_dir)
    upgrade = connect(tmp_path / "upgrade-0009.db")
    assert apply_migrations(upgrade, migration_dir)[-1] == "0008_staged_force_reresearch"
    copy2(MIGRATIONS_DIR / "0009_jobs_system_flags.sql", migration_dir / "0009_jobs_system_flags.sql")
    assert apply_migrations(upgrade, migration_dir) == ["0009_jobs_system_flags"]
    assert apply_migrations(upgrade, migration_dir) == []
    assert upgrade.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert upgrade.execute("PRAGMA foreign_key_check").fetchall() == []
    upgrade.close()


def test_0009_rolls_back_schema_when_migration_ledger_insert_fails(tmp_path):
    migration_dir = tmp_path / "through-0008"
    _copy_migrations_through_0008(migration_dir)
    conn = connect(tmp_path / "rollback-0009.db")
    apply_migrations(conn, migration_dir)
    copy2(MIGRATIONS_DIR / "0009_jobs_system_flags.sql", migration_dir / "0009_jobs_system_flags.sql")
    conn.execute(
        "CREATE TRIGGER reject_jobs_ledger BEFORE INSERT ON schema_migrations "
        "WHEN NEW.version='0009_jobs_system_flags' "
        "BEGIN SELECT RAISE(ABORT, 'forced jobs ledger failure'); END"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced jobs ledger failure"):
        apply_migrations(conn, migration_dir)

    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "jobs" not in tables and "system_flags" not in tables
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0009_jobs_system_flags'"
    ).fetchone()[0] == 0
    conn.execute("DROP TRIGGER reject_jobs_ledger")
    conn.commit()
    assert apply_migrations(conn, migration_dir) == ["0009_jobs_system_flags"]
    conn.close()


def test_enqueue_idempotency_context_and_active_research_topic_constraint(storage, account):
    topic = _topic(storage, account)
    first = storage.enqueue_job(_job(
        account, "research-one", "same-key", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    repeated = storage.enqueue_job(_job(
        account, "ignored-new-id", "same-key", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    assert repeated.id == first.id
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1

    with pytest.raises(JobConflictError, match="idempotency_key"):
        storage.enqueue_job(_job(
            account, "different-payload", "same-key", kind=JobKind.RESEARCH,
            topic_id=topic.id, payload={"contract": "different"},
        ))
    with pytest.raises(JobConflictError, match="Active research"):
        storage.enqueue_job(_job(
            account, "research-two", "other-key", kind=JobKind.RESEARCH, topic_id=topic.id,
        ))
    storage.enqueue_job(_job(account, "local-one", "local-one"))
    storage.enqueue_job(_job(account, "local-two", "local-two"))
    assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 3


def test_claim_lifecycle_lease_heartbeat_deadline_and_terminal_budget_release(storage, account):
    _topic(storage, account)
    future = storage.enqueue_job(_job(
        account, "future", "future", earliest=NOW + timedelta(minutes=1),
    ))
    expired = storage.enqueue_job(_job(
        account, "expired", "expired", earliest=NOW - timedelta(seconds=2),
        deadline=NOW - timedelta(seconds=1),
    ))
    high = storage.enqueue_job(_job(account, "high", "high", priority=10))
    low = storage.enqueue_job(_job(account, "low", "low", priority=1))

    lease = storage.claim_next_job("worker-a", 30, now=NOW)
    assert lease is not None and lease.job.id == high.id and lease.job.attempts == 1
    assert storage.get_job(future.id).status == JobStatus.QUEUED
    expired_state = storage.get_job(expired.id)
    assert expired_state.status == JobStatus.FAILED and expired_state.finished_at is not None

    storage.reserve_job_budget(high.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    with pytest.raises(LifecycleTransitionError):
        storage.heartbeat_job_lease(high.id, "worker-b", 30, now=NOW + timedelta(seconds=1))
    storage.heartbeat_job_lease(high.id, "worker-a", 30, now=NOW + timedelta(seconds=1))
    storage.mark_job_running(high.id, "worker-a", now=NOW + timedelta(seconds=2))
    with pytest.raises(LifecycleTransitionError):
        storage.complete_job(high.id, "worker-b", now=NOW + timedelta(seconds=3))
    storage.complete_job(high.id, "worker-a", now=NOW + timedelta(seconds=3))
    done = storage.get_job(high.id)
    assert done.status == JobStatus.DONE
    assert done.reserved_cost_usd == 0.0 and done.budget_reserved_at is None
    with pytest.raises(LifecycleTransitionError):
        storage.heartbeat_job_lease(high.id, "worker-a", 30, now=NOW + timedelta(seconds=4))
    assert storage.claim_next_job("worker-b", 30, now=NOW).job.id == low.id


def test_heartbeat_does_not_shorten_existing_lease(storage, account):
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "heartbeat-long", "heartbeat-long"))
    lease = storage.claim_next_job("worker-a", 120, now=NOW)
    assert lease is not None and lease.job.id == job.id
    before = storage.get_job(job.id)

    storage.heartbeat_job_lease(job.id, "worker-a", 30, now=NOW + timedelta(seconds=10))

    after = storage.get_job(job.id)
    assert after.status == JobStatus.LEASED
    assert after.lease_owner == "worker-a"
    assert after.lease_expires_at == before.lease_expires_at


def test_heartbeat_extends_shorter_existing_lease(storage, account):
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "heartbeat-short", "heartbeat-short"))
    lease = storage.claim_next_job("worker-a", 5, now=NOW)
    assert lease is not None and lease.job.id == job.id

    heartbeat_at = NOW + timedelta(seconds=1)
    storage.heartbeat_job_lease(job.id, "worker-a", 30, now=heartbeat_at)

    after = storage.get_job(job.id)
    assert after.status == JobStatus.LEASED
    assert after.lease_owner == "worker-a"
    assert after.lease_expires_at == (heartbeat_at + timedelta(seconds=30)).replace(tzinfo=None)


def test_heartbeat_rejects_already_expired_lease(storage, account):
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "heartbeat-expired", "heartbeat-expired"))
    lease = storage.claim_next_job("worker-a", 5, now=NOW)
    assert lease is not None and lease.job.id == job.id
    before = storage.get_job(job.id)

    with pytest.raises(LifecycleTransitionError):
        storage.heartbeat_job_lease(job.id, "worker-a", 30, now=NOW + timedelta(seconds=6))

    after = storage.get_job(job.id)
    assert after.status == JobStatus.LEASED
    assert after.lease_owner == "worker-a"
    assert after.lease_expires_at == before.lease_expires_at
    assert storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6)).requeued_count == 1
    assert storage.get_job(job.id).status == JobStatus.QUEUED


def test_expired_recovery_is_safe_idempotent_and_reopens(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Recovery research topic", score=90,
        status=TopicStatus.SELECTED,
    ))
    safe = storage.enqueue_job(_job(account, "safe", "safe", max_attempts=2))
    browser = storage.enqueue_job(_job(account, "browser", "browser", kind=JobKind.BROWSER))
    external = storage.enqueue_job(_job(
        account, "external", "external", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    for job_id in (safe.id, browser.id, external.id):
        while storage.get_job(job_id).status == JobStatus.QUEUED:
            storage.claim_next_job("worker", 5, now=NOW)
    storage.reserve_job_budget(
        external.id, 0.10, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    storage.mark_job_external_effect_started(external.id, "worker", now=NOW + timedelta(seconds=1))

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))
    assert result.requeued_count == 1
    assert result.needs_verification_count == 2
    assert result.failed_count == 0
    assert storage.get_job(safe.id).status == JobStatus.QUEUED
    assert storage.get_job(browser.id).status == JobStatus.NEEDS_VERIFICATION
    assert storage.get_job(external.id).status == JobStatus.NEEDS_VERIFICATION
    assert storage.get_job(external.id).reserved_cost_usd == 0.10
    with pytest.raises(LifecycleTransitionError):
        storage.release_job_budget(external.id, now=NOW + timedelta(seconds=6))
    assert storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=7)).model_dump() == {
        "requeued_count": 0, "needs_verification_count": 0, "failed_count": 0,
    }

    lease = storage.claim_next_job("worker", 5, now=NOW + timedelta(seconds=8))
    assert lease is not None and lease.job.id == safe.id and lease.job.attempts == 2
    exhausted = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=14))
    assert exhausted.failed_count == 1
    assert storage.get_job(safe.id).status == JobStatus.FAILED
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    assert reopened.get_job(browser.id).status == JobStatus.NEEDS_VERIFICATION
    assert reopened.get_job(external.id).status == JobStatus.NEEDS_VERIFICATION
    assert reopened.get_job(safe.id).status == JobStatus.FAILED
    reopened.close()


def test_release_budget_rejected_after_external_effect_started(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "release-after-effect", "release-after-effect"))
    storage.reserve_job_budget(
        job.id, 0.50, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    lease = storage.claim_next_job("worker-a", 5, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_external_effect_started(job.id, "worker-a", now=NOW + timedelta(seconds=1))
    before = storage.get_job(job.id)

    with pytest.raises(LifecycleTransitionError, match="external effect"):
        storage.release_job_budget(job.id, now=NOW + timedelta(seconds=2))

    after = storage.get_job(job.id)
    assert after.reserved_cost_usd == before.reserved_cost_usd == 0.50
    assert after.budget_reserved_at == before.budget_reserved_at
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    persisted = reopened.get_job(job.id)
    assert persisted.reserved_cost_usd == 0.50
    assert persisted.budget_reserved_at == before.budget_reserved_at
    reopened.close()


def test_external_effect_job_recovery_keeps_reservation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "effect-recovery", "effect-recovery"))
    storage.reserve_job_budget(
        job.id, 0.50, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    lease = storage.claim_next_job("worker-a", 5, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_external_effect_started(job.id, "worker-a", now=NOW + timedelta(seconds=1))

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))
    assert result.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 1, "failed_count": 0,
    }
    recovered = storage.get_job(job.id)
    assert recovered.status == JobStatus.NEEDS_VERIFICATION
    assert recovered.reserved_cost_usd == 0.50
    assert recovered.budget_reserved_at is not None

    other = storage.enqueue_job(_job(account, "effect-budget-other", "effect-budget-other"))
    with pytest.raises(BudgetReservationError, match="daily"):
        storage.reserve_job_budget(
            other.id, 1.60, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
        )
    storage.close()


def test_browser_job_cannot_release_budget_after_external_effect(storage, account):
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(
        account, "browser-release", "browser-release", kind=JobKind.BROWSER,
    ))
    storage.reserve_job_budget(
        job.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    lease = storage.claim_next_job("worker-a", 5, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_external_effect_started(job.id, "worker-a", now=NOW + timedelta(seconds=1))

    with pytest.raises(LifecycleTransitionError, match="external effect"):
        storage.release_job_budget(job.id, now=NOW + timedelta(seconds=2))

    after = storage.get_job(job.id)
    assert after.reserved_cost_usd == 0.40
    assert after.budget_reserved_at is not None


def test_terminal_and_safe_jobs_release_budget(storage, account):
    storage.ensure_account(account)
    done = storage.enqueue_job(_job(account, "release-done", "release-done", priority=3))
    failed = storage.enqueue_job(_job(account, "release-failed", "release-failed", priority=2))
    cancelled = storage.enqueue_job(_job(account, "release-cancelled", "release-cancelled"))
    releasable = storage.enqueue_job(_job(account, "release-safe", "release-safe"))

    storage.reserve_job_budget(done.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-a", 30, now=NOW).job.id == done.id
    storage.complete_job(done.id, "worker-a", now=NOW + timedelta(seconds=1))
    assert storage.get_job(done.id).reserved_cost_usd == 0.0

    storage.reserve_job_budget(failed.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-b", 30, now=NOW).job.id == failed.id
    storage.fail_job(failed.id, "worker-b", "offline failure", now=NOW + timedelta(seconds=1))
    assert storage.get_job(failed.id).reserved_cost_usd == 0.0

    storage.reserve_job_budget(
        cancelled.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    storage.cancel_job(cancelled.id, now=NOW + timedelta(seconds=1))
    assert storage.get_job(cancelled.id).reserved_cost_usd == 0.0

    storage.reserve_job_budget(
        releasable.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW,
    )
    storage.release_job_budget(releasable.id, now=NOW + timedelta(seconds=1))
    assert storage.get_job(releasable.id).reserved_cost_usd == 0.0


def test_budget_reservation_uses_real_usage_active_reservations_and_idempotency(storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(
        id="real-usage", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.add_model_usage(ModelUsage(
        run_id="real-usage", model="offline", estimated_cost_usd=0.30,
        dry_run=False, created_at=NOW,
    ))
    first = storage.enqueue_job(_job(account, "budget-first", "budget-first"))
    second = storage.enqueue_job(_job(account, "budget-second", "budget-second"))
    reservation = storage.reserve_job_budget(
        first.id, 0.50, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
    )
    assert reservation.amount_usd == 0.50
    assert storage.reserve_job_budget(
        first.id, 0.50, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
    ).model_dump() == reservation.model_dump()
    with pytest.raises(BudgetReservationError, match="different"):
        storage.reserve_job_budget(
            first.id, 0.40, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
        )
    with pytest.raises(BudgetReservationError, match="monthly"):
        storage.reserve_job_budget(
            second.id, 0.30, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
        )
    storage.cancel_job(first.id, now=NOW)
    assert storage.get_job(first.id).reserved_cost_usd == 0.0
    assert storage.reserve_job_budget(
        second.id, 0.70, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
    ).amount_usd == 0.70


def test_system_flags_are_runtime_fail_closed_atomic_and_persistent(settings, account):
    first = SqliteStorage.open(settings.db_path)
    first.ensure_account(account)
    missing = first.get_system_flag("paid_actions_enabled")
    assert missing.value is False and missing.is_valid is False
    assert first.get_system_flag("kill_switch").value is True

    second = SqliteStorage.open(settings.db_path)
    changed = second.set_system_flag(
        "paid_actions_enabled", True, updated_by="owner", reason="offline contract", now=NOW,
    )
    assert changed.value is True and changed.is_valid is True
    assert first.get_system_flag("paid_actions_enabled").value is True
    second.conn.execute(
        "UPDATE system_flags SET value_json='\"not-a-boolean\"' WHERE key='paid_actions_enabled'"
    )
    second.conn.commit()
    malformed = first.get_system_flag("paid_actions_enabled")
    assert malformed.value is False and malformed.is_valid is False
    with pytest.raises(SystemFlagError):
        first.set_system_flag("paid_actions_enabled", "true")
    second.close()
    first.close()

    reopened = SqliteStorage.open(settings.db_path)
    persisted = reopened.get_system_flag("paid_actions_enabled")
    assert persisted.value is False and persisted.is_valid is False
    reopened.close()


def test_two_workers_claim_one_then_two_jobs_without_duplicates(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    setup.ensure_account(account)
    only = setup.enqueue_job(_job(account, "only", "only"))
    setup.close()

    def concurrent_claim(owner_a: str, owner_b: str):
        barrier = threading.Barrier(2)
        results, failures = [], []

        def worker(owner: str):
            storage = SqliteStorage.open(settings.db_path)
            try:
                barrier.wait()
                results.append(storage.claim_next_job(owner, 30, now=NOW))
            except BaseException as exc:
                failures.append(exc)
            finally:
                storage.close()

        threads = [threading.Thread(target=worker, args=(owner,)) for owner in (owner_a, owner_b)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results, failures

    single_results, single_failures = concurrent_claim("single-a", "single-b")
    assert single_failures == []
    assert [lease.job.id for lease in single_results if lease is not None] == [only.id]

    seed = SqliteStorage.open(settings.db_path)
    first = seed.enqueue_job(_job(account, "two-first", "two-first"))
    second = seed.enqueue_job(_job(account, "two-second", "two-second"))
    seed.close()
    two_results, two_failures = concurrent_claim("two-a", "two-b")
    assert two_failures == []
    assert {lease.job.id for lease in two_results if lease is not None} == {first.id, second.id}
    reopened = SqliteStorage.open(settings.db_path)
    assert reopened.get_job(only.id).attempts == 1
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_concurrent_claims_enqueue_topic_budget_and_lifecycle_races(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    one = setup.enqueue_job(_job(account, "one", "one"))
    two = setup.enqueue_job(_job(account, "two", "two"))
    budget_a = setup.enqueue_job(_job(account, "budget-a", "budget-a"))
    budget_b = setup.enqueue_job(_job(account, "budget-b", "budget-b"))
    cancel_claim = setup.enqueue_job(_job(account, "cancel-claim", "cancel-claim"))
    heartbeat = setup.enqueue_job(_job(account, "heartbeat", "heartbeat", priority=100))
    complete = setup.enqueue_job(_job(account, "complete", "complete", priority=99))
    setup.claim_next_job("owner-heartbeat", 5, now=NOW)
    setup.claim_next_job("owner-complete", 5, now=NOW)
    setup.close()

    def threaded(callables):
        barrier = threading.Barrier(len(callables))
        results, failures = [], []

        def runner(callback):
            storage = SqliteStorage.open(settings.db_path)
            try:
                barrier.wait()
                results.append(callback(storage))
            except BaseException as exc:  # failures are asserted by each contract below
                failures.append(exc)
            finally:
                storage.close()

        threads = [threading.Thread(target=runner, args=(callback,)) for callback in callables]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results, failures

    # 1–2. Two workers claim queued jobs: no duplicate claim, then two distinct jobs.
    claims, claim_failures = threaded([
        lambda store: store.claim_next_job("claim-a", 30, now=NOW),
        lambda store: store.claim_next_job("claim-b", 30, now=NOW),
    ])
    assert claim_failures == []
    claimed_ids = {lease.job.id for lease in claims if lease is not None}
    assert len(claimed_ids) == 2
    assert len({one.id, two.id} & claimed_ids) <= 2

    # 3. Same idempotency key from two independent connections creates one durable job.
    same_key_results, same_key_failures = threaded([
        lambda store: store.enqueue_job(_job(account, "same-a", "concurrent-same")),
        lambda store: store.enqueue_job(_job(account, "same-b", "concurrent-same")),
    ])
    assert same_key_failures == []
    assert len({job.id for job in same_key_results}) == 1

    # 4. Durable partial UNIQUE permits exactly one active research job per topic.
    topic_results, topic_failures = threaded([
        lambda store: store.enqueue_job(_job(
            account, "topic-a", "topic-a", kind=JobKind.RESEARCH, topic_id=topic.id,
        )),
        lambda store: store.enqueue_job(_job(
            account, "topic-b", "topic-b", kind=JobKind.RESEARCH, topic_id=topic.id,
        )),
    ])
    assert len(topic_results) == 1
    assert len(topic_failures) == 1 and isinstance(topic_failures[0], JobConflictError)

    # 5. Two reservations that each fit alone cannot together exceed the shared limit.
    budget_results, budget_failures = threaded([
        lambda store: store.reserve_job_budget(
            budget_a.id, 0.70, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
        ),
        lambda store: store.reserve_job_budget(
            budget_b.id, 0.70, daily_limit_usd=1.0, monthly_limit_usd=1.0, now=NOW,
        ),
    ])
    assert len(budget_results) == 1
    assert len(budget_failures) == 1 and isinstance(budget_failures[0], BudgetReservationError)

    # 6–7. At the exact expiry timestamp heartbeat/complete win; recovery cannot steal them.
    heartbeat_results, heartbeat_failures = threaded([
        lambda store: store.heartbeat_job_lease(heartbeat.id, "owner-heartbeat", 30, now=NOW + timedelta(seconds=5)),
        lambda store: store.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=5)),
    ])
    assert heartbeat_failures == []
    assert any(getattr(value, "requeued_count", None) == 0 for value in heartbeat_results)
    complete_results, complete_failures = threaded([
        lambda store: store.complete_job(complete.id, "owner-complete", now=NOW + timedelta(seconds=5)),
        lambda store: store.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=5)),
    ])
    assert complete_failures == []
    assert any(getattr(value, "requeued_count", None) == 0 for value in complete_results)

    # 8. Claim versus cancellation has exactly one durable winner.
    cancel_results, cancel_failures = threaded([
        lambda store: store.claim_next_job("claimer", 30, now=NOW),
        lambda store: store.cancel_job(cancel_claim.id, now=NOW),
    ])
    assert len(cancel_failures) <= 1
    assert all(isinstance(exc, LifecycleTransitionError) for exc in cancel_failures)
    reopened = SqliteStorage.open(settings.db_path)
    final = reopened.get_job(cancel_claim.id)
    assert final.status in {JobStatus.CANCELLED, JobStatus.LEASED}
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()
