"""Testy warstwy storage: migracje, konta, tematy, sumowanie kosztów (real vs dry_run)."""
from __future__ import annotations

import sqlite3

import pytest

from app.models import (
    ModelUsage,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.storage.db import connect, initialize_database
from app.storage.repositories import SqliteStorage
from tests.conftest import seed_historical_real_usage


def _create_research_run(storage, account, run_id: str) -> Run:
    storage.ensure_account(account)
    return storage.create_run(Run(
        id=run_id, account_id=account.id,
        workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING,
    ))


def test_migrations_create_tables(storage):
    rows = storage.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    for expected in {"accounts", "topics", "runs", "model_usage", "schema_migrations"}:
        assert expected in names


def test_ensure_account_and_add_topic(storage, account):
    storage.ensure_account(account)
    saved = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Why queues slow down", question="?",
        score=70.0, status=TopicStatus.SCORED,
    ))
    assert saved.id is not None
    topics = storage.list_topics(account.id)
    assert len(topics) == 1
    assert topics[0].title == "Why queues slow down"
    assert topics[0].status == TopicStatus.SCORED


def test_account_isolation(storage, account):
    """Temat konta A nie pojawia się w odczycie konta B."""
    storage.ensure_account(account)
    other = account.model_copy(update={"id": "other_account", "display_name": "Other"})
    storage.ensure_account(other)
    storage.add_topic(account.id, Topic(account_id=account.id, title="A-topic"))
    assert len(storage.list_topics(account.id)) == 1
    assert len(storage.list_topics("other_account")) == 0


def test_sum_real_cost_excludes_dry_run(storage, account):
    storage.ensure_account(account)
    run = storage.create_run(Run(id="run-1", account_id=account.id,
                                 workflow=WorkflowType.TOPIC, status=RunStatus.DRY_RUN))
    seed_historical_real_usage(storage, ModelUsage(run_id=run.id, model="m", estimated_cost_usd=0.50,
                                                    dry_run=False))
    storage.add_model_usage(ModelUsage(run_id=run.id, model="m", estimated_cost_usd=99.0,
                                       dry_run=True))
    from datetime import datetime, timezone
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    assert storage.sum_real_cost_usd(month_prefix) == 0.50


def test_connect_enables_wal_and_busy_timeout(tmp_path):
    conn = connect(tmp_path / "sqlite-settings.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_connect_keeps_memory_database_supported_without_wal_requirement():
    conn = connect(":memory:")
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_sync_run_cost_uses_research_usage_and_is_idempotent(storage, account):
    storage.ensure_account(account)
    run = storage.create_run(Run(id="research-cost-sync", account_id=account.id,
                                 workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING))
    storage.add_model_usage(ModelUsage(run_id=run.id, model="m", task="research_discover",
                                       estimated_cost_usd=0.12, dry_run=True))
    seed_historical_real_usage(storage, ModelUsage(run_id=run.id, model="m", task="research_extract",
                                                    estimated_cost_usd=0.34, dry_run=False))
    seed_historical_real_usage(storage, ModelUsage(run_id=run.id, model="m", task="topics",
                                                    estimated_cost_usd=9.99, dry_run=False))
    storage.finish_run(run.id, RunStatus.FAILED.value, cost_usd=99.0, error="keep me")

    assert storage.sync_run_cost_from_research_usage(run.id) == 0.46
    assert storage.sync_run_cost_from_research_usage(run.id) == 0.46
    synced = storage.get_run(run.id)
    assert synced is not None
    assert synced.cost_usd == 0.46
    assert synced.status == RunStatus.FAILED
    assert synced.error == "keep me"


def test_research_usage_write_and_cache_persist_in_one_transaction(tmp_path, account):
    db_path = tmp_path / "atomic-research-usage.db"
    initialize_database(db_path)
    storage = SqliteStorage.open(db_path)
    run = _create_research_run(storage, account, "atomic-research-usage")
    seed_historical_real_usage(storage, ModelUsage(
        run_id=run.id, model="m", task="research_extract", estimated_cost_usd=0.123456,
    ))
    storage.close()

    reopened = SqliteStorage.open(db_path)
    try:
        assert sum(row.estimated_cost_usd for row in reopened.get_research_usage(run.id)) == \
            pytest.approx(0.123456)
        persisted = reopened.get_run(run.id)
        assert persisted is not None
        assert persisted.cost_usd == pytest.approx(0.123456)
    finally:
        reopened.close()


def test_research_usage_write_rolls_back_when_cache_update_fails(tmp_path, account):
    db_path = tmp_path / "atomic-research-rollback.db"
    initialize_database(db_path)
    storage = SqliteStorage.open(db_path)
    run = _create_research_run(storage, account, "atomic-research-rollback")
    storage.conn.execute(
        "CREATE TRIGGER fail_research_cost_sync BEFORE UPDATE OF cost_usd ON runs "
        "WHEN NEW.id='atomic-research-rollback' "
        "BEGIN SELECT RAISE(ABORT, 'forced cache update failure'); END;"
    )
    storage.conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced cache update failure"):
        seed_historical_real_usage(storage, ModelUsage(
            run_id=run.id, model="m", task="research_extract", estimated_cost_usd=0.123456,
        ))
    storage.close()

    reopened = SqliteStorage.open(db_path)
    try:
        assert reopened.get_research_usage(run.id) == []
        persisted = reopened.get_run(run.id)
        assert persisted is not None
        assert persisted.cost_usd == 0.0
    finally:
        reopened.close()


def test_research_usage_atomic_writes_rebuild_cache_from_all_rows(storage, account):
    run = _create_research_run(storage, account, "atomic-research-several")
    seed_historical_real_usage(storage, ModelUsage(
        run_id=run.id, model="m", task="research_discover", estimated_cost_usd=0.10,
    ))
    storage.finish_run(run.id, RunStatus.FAILED.value, cost_usd=99.0, error="stale cache")
    seed_historical_real_usage(storage, ModelUsage(
        run_id=run.id, model="m", task="research_extract", estimated_cost_usd=0.20,
    ))

    assert len(storage.get_research_usage(run.id)) == 2
    persisted = storage.get_run(run.id)
    assert persisted is not None
    assert persisted.cost_usd == pytest.approx(0.30)
    assert persisted.status == RunStatus.FAILED
    assert persisted.error == "stale cache"


def test_research_usage_dry_run_is_cached_but_excluded_from_budget(storage, account):
    run = _create_research_run(storage, account, "atomic-research-dry-run")
    storage.add_model_usage(ModelUsage(
        run_id=run.id, model="m", task="research_discover",
        estimated_cost_usd=0.12, dry_run=True,
    ))
    seed_historical_real_usage(storage, ModelUsage(
        run_id=run.id, model="m", task="research_extract",
        estimated_cost_usd=0.34, dry_run=False,
    ))

    persisted = storage.get_run(run.id)
    assert persisted is not None
    assert persisted.cost_usd == pytest.approx(0.46)
    assert storage.sum_real_cost_usd("") == pytest.approx(0.34)


def test_sync_zeroes_stale_cache_when_research_usage_is_empty(storage, account):
    run = _create_research_run(storage, account, "research-cost-empty")
    storage.finish_run(run.id, RunStatus.FAILED.value, cost_usd=99.0, error="stale cache")

    assert storage.sync_run_cost_from_research_usage(run.id) == 0.0
    persisted = storage.get_run(run.id)
    assert persisted is not None
    assert persisted.cost_usd == 0.0
    assert persisted.status == RunStatus.FAILED
