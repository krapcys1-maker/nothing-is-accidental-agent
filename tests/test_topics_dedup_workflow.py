"""Test deduplikacji na poziomie workflow: powtórny run oznacza duplikaty; izolacja kont."""
from __future__ import annotations

from app.llm.fake_client import FakeLLMClient
from app.llm.usage_tracker import UsageTracker
from app.models import TopicStatus
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.workflows.topics.discover import run_topic_discovery


def _run(settings, storage, account):
    return run_topic_discovery(
        account, 6,
        settings=settings, storage=storage,
        llm=FakeLLMClient(model="dry-run-fake"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage),
        notifier=LogNotification(),
    )


def test_second_run_marks_all_duplicates(settings, storage, account):
    storage.ensure_account(account)
    first = _run(settings, storage, account)
    assert first.duplicates == 0
    assert first.selected + first.scored + first.rejected == 6

    second = _run(settings, storage, account)
    assert second.duplicates == 6
    assert second.selected == 0 and second.scored == 0 and second.rejected == 0

    all_topics = storage.list_topics(account.id)
    assert len(all_topics) == 12
    dups = [t for t in all_topics if t.status == TopicStatus.DUPLICATE]
    assert len(dups) == 6
    assert all(d.duplicate_of is not None and d.rejection_reason for d in dups)


def test_same_topic_on_other_account_is_not_duplicate(settings, storage, account):
    storage.ensure_account(account)
    _run(settings, storage, account)

    other = account.model_copy(update={"id": "other_account", "display_name": "Other"})
    storage.ensure_account(other)
    summary = _run(settings, storage, other)
    # Na innym koncie te same tematy są nowe (dedup jest per account_id).
    assert summary.duplicates == 0
    assert len(storage.list_topics("other_account")) == 6
