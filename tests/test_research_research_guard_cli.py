"""Regresje CLI dla jawnego ponownego researchu (Etap 0 / Task 4)."""
from __future__ import annotations

from dataclasses import replace
import inspect

from app.llm.usage_tracker import UsageTracker
from app.models import Topic, TopicStatus
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.fake_client import FakeResearchClient
from app.workflows.research.pipeline import run_research_pipeline


def _selected_topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Why airline ticket prices change every few hours",
        question="What pricing system makes fares move so often?",
        score=89.5,
        status=TopicStatus.SELECTED,
    ))


def _complete_research(settings, storage, account, topic) -> None:
    run_research_pipeline(
        account, topic,
        settings=settings, storage=storage, research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def test_cli_refuses_completed_topic_before_constructing_api_client(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    _complete_research(settings, storage, account, topic)
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: settings)

    assert run_capped_research.main(["--topic-id", str(topic.id)]) == 1
    assert "--force-re-research" in capsys.readouterr().out


def test_cli_parses_explicit_re_research_override(monkeypatch):
    from scripts import run_capped_research

    captured = {}

    def fake_run_fresh(args):
        captured["force_re_research"] = args.force_re_research
        return 0

    monkeypatch.setattr(run_capped_research, "_run_fresh", fake_run_fresh)

    assert run_capped_research.main(["--topic-id", "1", "--force-re-research"]) == 0
    assert captured["force_re_research"] is True


def test_cli_rejects_re_research_override_with_resume(monkeypatch, capsys):
    from scripts import run_capped_research

    def forbidden_resume(args):
        raise AssertionError("invalid flag combination reached resume path")

    monkeypatch.setattr(run_capped_research, "_run_resume", forbidden_resume)

    assert run_capped_research.main([
        "--resume", "existing-run", "--force-re-research",
    ]) == 1
    assert "wyłącznie świeżego researchu" in capsys.readouterr().out


def test_capped_cli_force_cannot_bypass_corrupt_used_state_before_client_or_mutation(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    storage.conn.execute(
        "UPDATE topics SET status=? WHERE id=?", (TopicStatus.USED.value, topic.id),
    )
    storage.conn.commit()
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage", "research_cards")
    }
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: settings)

    assert run_capped_research.main([
        "--topic-id", str(topic.id), "--force-re-research",
    ]) == 1
    assert "błąd integralności" in capsys.readouterr().out
    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before


def test_capped_cli_force_cannot_cross_account_before_client_or_mutation(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    other_settings = replace(settings, accounts={account.id: account, other.id: other})
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: other_settings)

    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage", "research_cards")
    }
    assert run_capped_research.main([
        "--topic-id", str(topic.id), "--account", other.id, "--force-re-research",
    ]) == 1
    assert "nie znaleziono tematu" in capsys.readouterr().out
    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before


def test_private_resume_helpers_never_construct_a_real_provider_client():
    from scripts import run_capped_research

    assert "AnthropicResearchClient" not in inspect.getsource(
        run_capped_research._run_resume_legacy,
    )
    assert "AnthropicResearchClient" not in inspect.getsource(
        run_capped_research._run_resume_staged,
    )
    assert "AnthropicResearchClient" not in inspect.getsource(run_capped_research)
