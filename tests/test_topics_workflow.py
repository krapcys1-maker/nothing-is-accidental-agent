"""Test end-to-end walking skeleton (dry_run, klient zastępczy)."""
from __future__ import annotations

from dataclasses import replace

from app.llm.fake_client import FakeLLMClient
from app.llm.usage_tracker import UsageTracker
from app.models import RunStatus
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.workflows.topics.discover import run_topic_discovery


def _run(settings, storage, account):
    storage.ensure_account(account)
    return run_topic_discovery(
        account, 6,
        settings=settings, storage=storage,
        llm=FakeLLMClient(model="dry-run-fake"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage),
        notifier=LogNotification(),
    )


def test_walking_skeleton_scores_and_persists(settings, storage, account):
    summary = _run(settings, storage, account)

    assert not summary.blocked
    assert summary.total == 6
    assert summary.selected == 3   # tematy >= 75
    assert summary.scored == 2     # 65 <= score < 75
    assert summary.rejected == 1   # < 65
    assert summary.cost_usd == 0.0126
    assert summary.run_id is not None

    # zapisano do bazy
    assert len(storage.list_topics(account.id)) == 6
    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.DRY_RUN


def test_kill_switch_stops_workflow(settings, storage, account):
    summary = _run(replace(settings, kill_switch=True), storage, account)
    assert summary.blocked
    assert summary.block_code == "KILL_SWITCH"
    assert summary.run_id is None
    assert len(storage.list_topics(account.id)) == 0


def test_inactive_account_stops_workflow(settings, storage, account):
    inactive = account.model_copy(update={"active": False})
    summary = _run(settings, storage, inactive)
    assert summary.blocked
    assert summary.block_code == "ACCOUNT_INACTIVE"


def test_real_mode_reaches_success_not_running(settings, storage, account):
    """P0-1 (docs/AUDYT_ARCHITEKTURY_2026-07-12.md): przed naprawą KAŻDY realny
    (dry_run=False) sukces kończył się terminalnym RUNNING — RunStatus.SUCCESS nie był
    zapisywany nigdzie w kodzie (potwierdzone też w produkcyjnej bazie: 0 wierszy SUCCESS)."""
    real_settings = replace(settings, dry_run=False)
    summary = _run(real_settings, storage, account)

    assert not summary.blocked
    run = storage.get_run(summary.run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.status != RunStatus.RUNNING
