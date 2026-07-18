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
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    BudgetReservationError,
    JobConflictError,
    JobRunConflictError,
    JobRunRelationError,
    LifecycleTransitionError,
    SystemFlagError,
)
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect, initialize_database
from app.storage.repositories import SqliteStorage
from tests.conftest import seed_historical_real_usage


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
        payload=payload or {"contract": "queue-v1"}, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=earliest, deadline_at=deadline, max_attempts=max_attempts,
        created_at=NOW,
    )


def _worker_research_run(
    storage: SqliteStorage,
    account,
    topic: Topic,
    run_id: str,
    *,
    run_status: RunStatus = RunStatus.DRY_RUN,
    research_status: ResearchRunStatus = ResearchRunStatus.PENDING,
    flow: ResearchFlow = ResearchFlow.SINGLE,
    research_account=None,
    started_at: datetime = NOW,
) -> str:
    """Creates the exact run/research_run pair the offline worker binds."""
    research_account = research_account or account
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=run_status, started_at=started_at,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=research_account.id, topic_id=int(topic.id),
        flow=flow, status=research_status,
    ))
    return run_id


def _orphaned_running_run(
    storage: SqliteStorage, account, run_id: str, *, started_at: datetime,
) -> str:
    storage.ensure_account(account)
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING, started_at=started_at,
    ))
    return run_id


def _claim(storage: SqliteStorage, job: Job, *, owner: str = "worker-a", lease_seconds: int = 5) -> Job:
    enqueued = storage.enqueue_job(job)
    lease = storage.claim_next_job(owner, lease_seconds, now=NOW)
    assert lease is not None and lease.job.id == enqueued.id
    return enqueued


def _reopen_job(settings, storage: SqliteStorage, job_id: str):
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    job = reopened.get_job(job_id)
    assert job is not None
    return reopened, job


def _copy_migrations_through_0008(destination: Path) -> None:
    destination.mkdir()
    for source in sorted(MIGRATIONS_DIR.glob("000[1-8]_*.sql")):
        copy2(source, destination / source.name)


def test_0009_fresh_schema_and_upgrade_from_0008_are_repeatable(tmp_path, account):
    fresh_path = tmp_path / "fresh-0009.db"
    initialize_database(fresh_path)
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
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
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


def test_attach_job_run_accepts_matching_research_relation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-matching", "attach-matching", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "attach-matching-run")

    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.status is JobStatus.LEASED
    assert persisted.run_id == run_id
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_attach_job_run_is_idempotent_for_same_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-idempotent", "attach-idempotent", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "attach-idempotent-run")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    first = storage.get_job(job.id)

    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW + timedelta(seconds=1))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id == run_id
    assert persisted.updated_at == first.updated_at
    reopened.close()


def test_attach_job_run_rejects_non_research_job(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    local = _claim(storage, _job(account, "attach-local", "attach-local"))
    run_id = _worker_research_run(storage, account, topic, "attach-local-run")

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(local.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "JOB_KIND_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, local.id)
    assert persisted.run_id is None and persisted.status is JobStatus.LEASED
    reopened.close()


def test_attach_job_run_rejects_non_research_workflow(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    malformed = _job(
        account, "attach-wrong-workflow", "attach-wrong-workflow",
        kind=JobKind.RESEARCH, topic_id=topic.id,
    ).model_copy(update={"workflow": WorkflowType.ANALYTICS})
    job = _claim(storage, malformed)
    run_id = _worker_research_run(storage, account, topic, "attach-wrong-workflow-run")

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "JOB_WORKFLOW_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_run_workflow_mismatch(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-run-workflow", "attach-run-workflow", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.create_run(Run(
        id="attach-run-workflow-run", account_id=account.id,
        workflow=WorkflowType.TOPIC, status=RunStatus.DRY_RUN,
    ))

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", "attach-run-workflow-run", now=NOW)
    assert exc.value.code == "RUN_WORKFLOW_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_account_mismatch(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    other = account.model_copy(update={"id": "other-attach-account"})
    other_topic = _topic(storage, other)
    job = _claim(storage, _job(
        account, "attach-account", "attach-account", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, other, other_topic, "attach-account-run")

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "JOB_RUN_ACCOUNT_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_research_run_account_mismatch(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    other = account.model_copy(update={"id": "other-research-run-account"})
    storage.ensure_account(other)
    job = _claim(storage, _job(
        account, "attach-research-account", "attach-research-account",
        kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(
        storage, account, topic, "attach-research-account-run", research_account=other,
    )

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "JOB_RESEARCH_RUN_ACCOUNT_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_topic_mismatch(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    other_topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Different research topic", score=91, status=TopicStatus.SELECTED,
    ))
    job = _claim(storage, _job(
        account, "attach-topic", "attach-topic", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, other_topic, "attach-topic-run")

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "JOB_RUN_TOPIC_MISMATCH"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_missing_research_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-missing-research", "attach-missing-research",
        kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.create_run(Run(
        id="attach-missing-research-run", account_id=account.id,
        workflow=WorkflowType.RESEARCH, status=RunStatus.DRY_RUN,
    ))

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", "attach-missing-research-run", now=NOW)
    assert exc.value.code == "RESEARCH_RUN_MISSING"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_disallowed_research_flow(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-staged-flow", "attach-staged-flow", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(
        storage, account, topic, "attach-staged-flow-run", flow=ResearchFlow.STAGED,
        research_status=ResearchRunStatus.DISCOVERY_PENDING,
    )

    with pytest.raises(JobRunRelationError) as exc:
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    assert exc.value.code == "RESEARCH_RUN_FLOW_UNSUPPORTED"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_different_existing_run_id(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-different", "attach-different", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    first_run = _worker_research_run(storage, account, topic, "attach-different-first")
    second_run = _worker_research_run(storage, account, topic, "attach-different-second")
    storage.attach_job_run(job.id, "worker-a", first_run, now=NOW)

    with pytest.raises(JobRunConflictError) as exc:
        storage.attach_job_run(job.id, "worker-a", second_run, now=NOW + timedelta(seconds=1))
    assert exc.value.code == "JOB_RUN_ALREADY_ATTACHED"

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id == first_run
    reopened.close()


def test_attach_job_run_rejects_foreign_lease_owner(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-foreign-owner", "attach-foreign-owner", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "attach-foreign-owner-run")

    with pytest.raises(LifecycleTransitionError):
        storage.attach_job_run(job.id, "worker-b", run_id, now=NOW)

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None and persisted.lease_owner == "worker-a"
    reopened.close()


def test_attach_job_run_rejects_expired_lease(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-expired", "attach-expired", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "attach-expired-run")

    with pytest.raises(LifecycleTransitionError):
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.run_id is None
    reopened.close()


def test_attach_job_run_rejects_terminal_job(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "attach-terminal", "attach-terminal", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "attach-terminal-run")
    storage.complete_job(job.id, "worker-a", now=NOW + timedelta(seconds=1))

    with pytest.raises(LifecycleTransitionError):
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW + timedelta(seconds=2))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.status is JobStatus.DONE and persisted.run_id is None
    reopened.close()


def test_research_job_without_run_id_recovers_to_queued(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "recovery-no-run", "recovery-no-run", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.mark_job_running(job.id, "worker-a", now=NOW)

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert result.model_dump() == {
        "requeued_count": 1, "needs_verification_count": 0, "failed_count": 0,
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
    }
    assert persisted.status is JobStatus.QUEUED and persisted.run_id is None
    reopened.close()


def test_research_job_with_run_id_recovers_to_needs_verification(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = storage.enqueue_job(_job(
        account, "recovery-attached", "recovery-attached", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.reserve_job_budget(job.id, 0.25, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-a", 5, now=NOW).job.id == job.id
    storage.mark_job_running(job.id, "worker-a", now=NOW)
    run_id = _worker_research_run(storage, account, topic, "recovery-attached-run")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert result.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 1, "failed_count": 0,
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
    }
    assert persisted.status is JobStatus.NEEDS_VERIFICATION
    assert persisted.run_id == run_id
    assert persisted.reserved_cost_usd == 0.25 and persisted.budget_reserved_at is not None
    assert persisted.last_error.startswith("RESEARCH_RUN_RECONCILIATION_REQUIRED:")
    reopened.close()


def test_research_job_with_external_effect_keeps_existing_behavior(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = storage.enqueue_job(_job(
        account, "recovery-external", "recovery-external", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.reserve_job_budget(job.id, 0.25, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-a", 5, now=NOW).job.id == job.id
    storage.mark_job_running(job.id, "worker-a", now=NOW)
    run_id = _worker_research_run(storage, account, topic, "recovery-external-run")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    storage.mark_job_external_effect_started(job.id, "worker-a", now=NOW + timedelta(seconds=1))

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert result.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 1, "failed_count": 0,
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
    }
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    assert persisted.reserved_cost_usd == 0.25 and persisted.budget_reserved_at is not None
    assert persisted.last_error == "Lease expired; external effect requires verification."
    reopened.close()


def test_research_job_with_terminal_success_run_reconciles_safely(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "recovery-terminal", "recovery-terminal", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.mark_job_running(job.id, "worker-a", now=NOW)
    run_id = _worker_research_run(storage, account, topic, "recovery-terminal-run")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    storage.conn.execute("UPDATE runs SET status='SUCCESS' WHERE id=?", (run_id,))
    storage.conn.execute("UPDATE research_runs SET status='COMPLETE' WHERE id=?", (run_id,))
    storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert result.needs_verification_count == 1
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    assert reopened.get_run(run_id).status is RunStatus.SUCCESS
    assert reopened.get_research_run(run_id).status is ResearchRunStatus.COMPLETE
    reopened.close()


def test_research_job_with_failed_or_partial_run_is_not_restarted_from_scratch(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    for suffix, run_status, research_status in (
        ("failed", RunStatus.FAILED, ResearchRunStatus.FAILED),
        ("partial", RunStatus.DRY_RUN, ResearchRunStatus.PARTIAL),
    ):
        topic = storage.add_topic(account.id, Topic(
            account_id=account.id, title=f"Recovery {suffix} topic", score=90,
            status=TopicStatus.SELECTED,
        ))
        job = _claim(storage, _job(
            account, f"recovery-{suffix}", f"recovery-{suffix}",
            kind=JobKind.RESEARCH, topic_id=topic.id,
        ))
        storage.mark_job_running(job.id, "worker-a", now=NOW)
        run_id = _worker_research_run(storage, account, topic, f"recovery-{suffix}-run")
        storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
        storage.conn.execute("UPDATE runs SET status=? WHERE id=?", (run_status.value, run_id))
        storage.conn.execute("UPDATE research_runs SET status=? WHERE id=?", (research_status.value, run_id))
        storage.conn.commit()

    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    assert result.model_dump() == {
        "requeued_count": 0, "needs_verification_count": 2, "failed_count": 0,
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
    }
    for suffix in ("failed", "partial"):
        persisted = reopened.get_job(f"recovery-{suffix}")
        assert persisted.status is JobStatus.NEEDS_VERIFICATION
        assert persisted.run_id == f"recovery-{suffix}-run"
    reopened.close()


def test_recovery_does_not_clear_existing_run_id(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "recovery-keeps-run", "recovery-keeps-run", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(storage, account, topic, "recovery-keeps-run-id")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    reopened.close()


def test_recovery_with_run_id_preserves_budget_reservation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = storage.enqueue_job(_job(
        account, "recovery-keeps-budget", "recovery-keeps-budget",
        kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.reserve_job_budget(job.id, 0.40, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-a", 5, now=NOW).job.id == job.id
    run_id = _worker_research_run(storage, account, topic, "recovery-keeps-budget-run")
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    reopened, persisted = _reopen_job(settings, storage, job.id)
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    assert persisted.reserved_cost_usd == 0.40 and persisted.budget_reserved_at is not None
    with pytest.raises(LifecycleTransitionError):
        reopened.release_job_budget(job.id, now=NOW + timedelta(seconds=6))
    reopened.close()


def test_two_recovery_workers_do_not_reconcile_same_job_twice(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    topic = _topic(setup, account)
    job = _claim(setup, _job(
        account, "recovery-concurrent", "recovery-concurrent", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(setup, account, topic, "recovery-concurrent-run")
    setup.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    setup.close()

    barrier = threading.Barrier(2)
    results: list = []
    failures: list[BaseException] = []

    def recover() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6)))
        except BaseException as exc:
            failures.append(exc)
        finally:
            storage.close()

    threads = [threading.Thread(target=recover) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reopened = SqliteStorage.open(settings.db_path)
    persisted = reopened.get_job(job.id)
    assert failures == []
    assert sum(result.needs_verification_count for result in results) == 1
    assert persisted.status is JobStatus.NEEDS_VERIFICATION and persisted.run_id == run_id
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_reaper_stops_orphaned_stale_running_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        storage, account, "reaper-orphan", started_at=NOW - timedelta(seconds=10),
    )

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    stopped = storage.get_run(run_id)
    assert result.model_dump() == {"checked_count": 1, "stopped_count": 1}
    assert stopped.status is RunStatus.STOPPED
    assert stopped.finished_at == NOW.replace(tzinfo=None)
    assert stopped.error == "STALE_RUN_REAPER: stale RUNNING run has no executable job lease."
    storage.close()


def test_reaper_does_not_stop_recent_running_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(storage, account, "reaper-recent", started_at=NOW)

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 0, "stopped_count": 0}
    assert storage.get_run(run_id).status is RunStatus.RUNNING
    storage.close()


def test_reaper_does_not_stop_run_with_fresh_active_lease(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "reaper-fresh-job", "reaper-fresh-job", kind=JobKind.RESEARCH, topic_id=topic.id,
    ), lease_seconds=30)
    run_id = _worker_research_run(
        storage, account, topic, "reaper-fresh-run", run_status=RunStatus.RUNNING,
        started_at=NOW - timedelta(seconds=10),
    )
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 1, "stopped_count": 0}
    assert storage.get_run(run_id).status is RunStatus.RUNNING
    assert storage.get_job(job.id).status is JobStatus.LEASED
    storage.close()


def test_reaper_waits_for_job_recovery_before_stopping_expired_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "reaper-expired-job", "reaper-expired-job", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(
        storage, account, topic, "reaper-expired-run", run_status=RunStatus.RUNNING,
        started_at=NOW - timedelta(seconds=10),
    )
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    result = storage.reap_orphaned_stale_runs(
        NOW - timedelta(seconds=1), now=NOW + timedelta(seconds=6),
    )

    assert result.model_dump() == {"checked_count": 1, "stopped_count": 0}
    assert storage.get_job(job.id).status is JobStatus.LEASED
    assert storage.get_run(run_id).status is RunStatus.RUNNING
    storage.close()


def test_reaper_can_stop_run_after_lease_expiry_and_job_reconciliation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = _claim(storage, _job(
        account, "reaper-reconcile-job", "reaper-reconcile-job",
        kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(
        storage, account, topic, "reaper-reconcile-run", run_status=RunStatus.RUNNING,
        started_at=NOW - timedelta(seconds=10),
    )
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    recovery = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))
    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW + timedelta(seconds=6))

    assert recovery.needs_verification_count == 1
    assert result.model_dump() == {"checked_count": 1, "stopped_count": 1}
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.get_run(run_id).status is RunStatus.STOPPED
    storage.close()


def test_reaper_does_not_change_success_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        storage, account, "reaper-success", started_at=NOW - timedelta(seconds=10),
    )
    storage.finish_run(run_id, RunStatus.SUCCESS.value, 0.0)

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 0, "stopped_count": 0}
    assert storage.get_run(run_id).status is RunStatus.SUCCESS
    storage.close()


def test_reaper_does_not_change_failed_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        storage, account, "reaper-failed", started_at=NOW - timedelta(seconds=10),
    )
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.0, error="existing failure")

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 0, "stopped_count": 0}
    failed = storage.get_run(run_id)
    assert failed.status is RunStatus.FAILED and failed.error == "existing failure"
    storage.close()


def test_reaper_does_not_change_dry_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    run_id = "reaper-dry-run"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.DRY_RUN, started_at=NOW - timedelta(seconds=10),
    ))

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 0, "stopped_count": 0}
    assert storage.get_run(run_id).status is RunStatus.DRY_RUN
    storage.close()


def test_reaper_is_idempotent_for_already_stopped_run(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        storage, account, "reaper-stopped", started_at=NOW - timedelta(seconds=10),
    )
    storage.finish_run(run_id, RunStatus.STOPPED.value, 0.0, error="prior stale stop")

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)

    assert result.model_dump() == {"checked_count": 0, "stopped_count": 0}
    stopped = storage.get_run(run_id)
    assert stopped.status is RunStatus.STOPPED and stopped.error == "prior stale stop"
    storage.close()


def _assert_reaper_loses_terminal_race(settings, account, target: RunStatus) -> None:
    setup = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        setup, account, f"reaper-race-{target.value.lower()}", started_at=NOW - timedelta(seconds=10),
    )
    setup.close()
    lock_held = threading.Event()
    release_terminalizer = threading.Event()
    reaper_entered = threading.Event()
    barrier = threading.Barrier(2)
    results: list = []
    failures: list[BaseException] = []

    def terminalize() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            storage.conn.execute("BEGIN IMMEDIATE")
            cursor = storage.conn.execute(
                "UPDATE runs SET status=?, error=?, finished_at=? "
                "WHERE id=? AND status='RUNNING' AND finished_at IS NULL",
                (
                    target.value,
                    f"terminal {target.value}",
                    NOW.replace(tzinfo=None).isoformat(sep=" "),
                    run_id,
                ),
            )
            assert cursor.rowcount == 1
            lock_held.set()
            barrier.wait()
            assert release_terminalizer.wait(timeout=2)
            storage.conn.commit()
        except BaseException as exc:
            failures.append(exc)
            if storage.conn.in_transaction:
                storage.conn.rollback()
        finally:
            storage.close()

    def reap() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            assert lock_held.wait(timeout=2)
            barrier.wait()
            reaper_entered.set()
            results.append(storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW))
        except BaseException as exc:
            failures.append(exc)
        finally:
            storage.close()

    terminal_thread = threading.Thread(target=terminalize)
    reaper_thread = threading.Thread(target=reap)
    terminal_thread.start()
    assert lock_held.wait(timeout=2)
    reaper_thread.start()
    assert reaper_entered.wait(timeout=2)
    release_terminalizer.set()
    terminal_thread.join()
    reaper_thread.join()

    reopened = SqliteStorage.open(settings.db_path)
    terminal = reopened.get_run(run_id)
    assert failures == []
    assert [result.stopped_count for result in results] == [0]
    assert terminal.status is target and terminal.error == f"terminal {target.value}"
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_reaper_loses_race_to_success_terminalization(settings, account):
    _assert_reaper_loses_terminal_race(settings, account, RunStatus.SUCCESS)


def test_reaper_loses_race_to_failed_terminalization(settings, account):
    _assert_reaper_loses_terminal_race(settings, account, RunStatus.FAILED)


def test_two_reapers_stop_run_exactly_once(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        setup, account, "reaper-two-workers", started_at=NOW - timedelta(seconds=10),
    )
    setup.close()
    barrier = threading.Barrier(2)
    results: list = []
    failures: list[BaseException] = []

    def reap() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW))
        except BaseException as exc:
            failures.append(exc)
        finally:
            storage.close()

    threads = [threading.Thread(target=reap) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reopened = SqliteStorage.open(settings.db_path)
    assert failures == []
    assert sum(result.stopped_count for result in results) == 1
    assert reopened.get_run(run_id).status is RunStatus.STOPPED
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_reaper_preserves_job_needs_verification(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    job = storage.enqueue_job(_job(
        account, "reaper-needs-job", "reaper-needs-job", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    storage.reserve_job_budget(job.id, 0.25, daily_limit_usd=2.0, monthly_limit_usd=40.0, now=NOW)
    assert storage.claim_next_job("worker-a", 5, now=NOW).job.id == job.id
    run_id = _worker_research_run(
        storage, account, topic, "reaper-needs-run", run_status=RunStatus.RUNNING,
        started_at=NOW - timedelta(seconds=10),
    )
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)
    storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    result = storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW + timedelta(seconds=6))

    persisted = storage.get_job(job.id)
    assert result.stopped_count == 1
    assert persisted.status is JobStatus.NEEDS_VERIFICATION
    assert persisted.run_id == run_id
    assert persisted.reserved_cost_usd == 0.25 and persisted.budget_reserved_at is not None
    storage.close()


def test_reaper_integrity_check_after_reopen(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _orphaned_running_run(
        storage, account, "reaper-reopen", started_at=NOW - timedelta(seconds=10),
    )
    storage.reap_orphaned_stale_runs(NOW - timedelta(seconds=1), now=NOW)
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    stopped = reopened.get_run(run_id)
    assert stopped.status is RunStatus.STOPPED and stopped.finished_at == NOW.replace(tzinfo=None)
    assert stopped.error == "STALE_RUN_REAPER: stale RUNNING run has no executable job lease."
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_job_run_reconciliation_error_is_sanitized_and_bounded(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    unsafe_job_id = "job\nBearer sk-test-token-should-not-persist\r" + ("x" * 1000)
    job = _claim(storage, _job(
        account, unsafe_job_id, "safe-reconciliation-key", kind=JobKind.RESEARCH, topic_id=topic.id,
    ))
    run_id = _worker_research_run(
        storage, account, topic, "reaper-sanitized-run", run_status=RunStatus.RUNNING,
        started_at=NOW - timedelta(seconds=10),
    )
    storage.attach_job_run(job.id, "worker-a", run_id, now=NOW)

    storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=6))

    error = storage.get_job(job.id).last_error
    assert error is not None and len(error) <= 240
    assert "\n" not in error and "\r" not in error
    assert "sk-test-token-should-not-persist" not in error
    assert unsafe_job_id not in error
    storage.close()


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
        "escalated_reconciliation_count": 0,
        "settled_execution_recovery_count": 0, "settled_execution_blocked_count": 0,
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
    seed_historical_real_usage(storage, ModelUsage(
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
    with pytest.raises(SystemFlagError):
        second.set_system_flag(
            "paid_actions_enabled", True,
            updated_by="owner",
            reason="single opening forbidden",
            now=NOW,
        )
    changed = second.apply_security_flag_profile([
        ("kill_switch", True),
        ("worker_enabled", False),
        ("safe_mode", True),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
    ], updated_by="owner", reason="offline contract", now=NOW)
    assert changed["paid_actions_enabled"] is True
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
