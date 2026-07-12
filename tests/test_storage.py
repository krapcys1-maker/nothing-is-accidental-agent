"""Testy warstwy storage: migracje, konta, tematy, sumowanie kosztów (real vs dry_run)."""
from __future__ import annotations

from app.models import (
    ModelUsage,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)


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
    storage.add_model_usage(ModelUsage(run_id=run.id, model="m", estimated_cost_usd=0.50,
                                       dry_run=False))
    storage.add_model_usage(ModelUsage(run_id=run.id, model="m", estimated_cost_usd=99.0,
                                       dry_run=True))
    from datetime import datetime, timezone
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    assert storage.sum_real_cost_usd(month_prefix) == 0.50
