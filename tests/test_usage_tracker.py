"""Testy trackingu kosztów: liczenie kosztu z cennika + zapis do model_usage i CSV."""
from __future__ import annotations

from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import Run, RunStatus, WorkflowType


def test_estimate_cost_matches_pricing(settings, storage):
    tracker = UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path)
    # 1M input * 3.0 + 1M output * 15.0 = 18.0
    assert tracker.estimate_cost(Usage(input_tokens=1_000_000, output_tokens=1_000_000)) == 18.0
    # 1200 in, 600 out -> 0.0036 + 0.009 = 0.0126
    assert tracker.estimate_cost(Usage(input_tokens=1200, output_tokens=600)) == 0.0126


def test_record_writes_db_and_csv(settings, storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(id="run-x", account_id=account.id,
                           workflow=WorkflowType.TOPIC, status=RunStatus.DRY_RUN))
    tracker = UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path)
    row = tracker.record("run-x", "dry-run-fake", Usage(input_tokens=1200, output_tokens=600),
                         task="topics", dry_run=True)
    assert row.estimated_cost_usd == 0.0126
    assert row.id is not None
    # CSV zapisany z wierszem dla run-x
    content = settings.costs_csv_path.read_text(encoding="utf-8")
    assert "run-x" in content
    assert "topics" in content
    assert "dry_run estimate" in content
