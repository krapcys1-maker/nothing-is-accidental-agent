"""Test end-to-end walking skeleton (dry_run, klient zastępczy)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.llm.base import LLMParseError, LLMProviderError, Usage
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
    """P0-1 (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): przed naprawą KAŻDY realny
    (dry_run=False) sukces kończył się terminalnym RUNNING — RunStatus.SUCCESS nie był
    zapisywany nigdzie w kodzie (potwierdzone też w produkcyjnej bazie: 0 wierszy SUCCESS)."""
    real_settings = replace(settings, dry_run=False)
    summary = _run(real_settings, storage, account)

    assert not summary.blocked
    run = storage.get_run(summary.run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.status != RunStatus.RUNNING


class _FailingLLM:
    model = "topics-model"

    def __init__(self, error):
        self.error = error
        self.calls = 0

    def generate_and_score_topics(self, account, count):
        self.calls += 1
        raise self.error


class _CountingLLM(FakeLLMClient):
    def __init__(self):
        super().__init__(model="counting-fake")
        self.calls = 0

    def generate_and_score_topics(self, account, count):
        self.calls += 1
        return super().generate_and_score_topics(account, count)


def _run_with_llm(settings, storage, account, llm):
    storage.ensure_account(account)
    return run_topic_discovery(
        account, 2,
        settings=settings, storage=storage, llm=llm,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def test_parse_error_with_usage_is_recorded_once_and_run_fails(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    usage = Usage(input_tokens=1000, output_tokens=200)
    llm = _FailingLLM(LLMParseError(
        "truncated topics JSON", usage=usage, model="topics-model"))

    with pytest.raises(LLMParseError, match="truncated"):
        _run_with_llm(real_settings, storage, account, llm)

    assert llm.calls == 1
    assert storage.list_topics(account.id) == []
    rows = storage.conn.execute(
        "SELECT * FROM model_usage WHERE task='topics'"
    ).fetchall()
    assert len(rows) == 1
    run = storage.conn.execute("SELECT * FROM runs").fetchone()
    assert run["account_id"] == account.id
    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] == "truncated topics JSON"
    assert run["cost_usd"] == pytest.approx(rows[0]["estimated_cost_usd"])
    assert rows[0]["dry_run"] == 0


def test_parse_error_without_usage_creates_no_artificial_cost(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    llm = _FailingLLM(LLMParseError("missing response usage", model="topics-model"))

    with pytest.raises(LLMParseError, match="missing response usage"):
        _run_with_llm(real_settings, storage, account, llm)

    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    run = storage.conn.execute("SELECT * FROM runs").fetchone()
    assert run["status"] == RunStatus.FAILED.value
    assert run["cost_usd"] == 0.0
    assert storage.list_topics(account.id) == []


def test_provider_error_before_response_fails_run_without_usage(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    llm = _FailingLLM(LLMProviderError("provider unavailable", model="topics-model"))

    with pytest.raises(LLMProviderError, match="provider unavailable"):
        _run_with_llm(real_settings, storage, account, llm)

    assert llm.calls == 1
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    assert storage.conn.execute("SELECT status FROM runs").fetchone()[0] == \
        RunStatus.FAILED.value
    assert storage.list_topics(account.id) == []


def test_success_paths_keep_exactly_one_usage_row(settings, storage, account):
    dry_summary = _run(settings, storage, account)
    dry_row = storage.conn.execute(
        "SELECT * FROM model_usage WHERE run_id=?", (dry_summary.run_id,)
    ).fetchone()
    assert dry_row["dry_run"] == 1
    assert storage.get_run(dry_summary.run_id).status == RunStatus.DRY_RUN

    real_settings = replace(settings, dry_run=False)
    real_summary = _run(real_settings, storage, account)
    real_rows = storage.conn.execute(
        "SELECT * FROM model_usage WHERE run_id=?", (real_summary.run_id,)
    ).fetchall()
    assert len(real_rows) == 1
    assert real_rows[0]["dry_run"] == 0
    assert storage.get_run(real_summary.run_id).status == RunStatus.SUCCESS


@pytest.mark.parametrize("blocked_settings", [
    lambda s: replace(s, kill_switch=True),
    lambda s: replace(s, max_monthly_cost_usd=0.0),
])
def test_policy_denial_precedes_client_run_and_usage(
        blocked_settings, settings, storage, account):
    llm = _CountingLLM()
    summary = _run_with_llm(blocked_settings(settings), storage, account, llm)

    assert summary.blocked
    assert llm.calls == 0
    assert storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0


def test_topic_workflow_keeps_run_usage_and_topics_in_selected_account(
        settings, storage, account):
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    other_settings = replace(
        settings, dry_run=False, accounts={account.id: account, other.id: other},
    )

    summary = _run_with_llm(other_settings, storage, other, FakeLLMClient("account-fake"))

    run = storage.get_run(summary.run_id)
    usage_run = storage.conn.execute(
        "SELECT r.account_id FROM model_usage u JOIN runs r ON r.id=u.run_id "
        "WHERE u.run_id=?", (summary.run_id,),
    ).fetchone()
    assert run.account_id == other.id
    assert usage_run["account_id"] == other.id
    assert len(storage.list_topics(other.id)) == 2
    assert storage.list_topics(account.id) == []
