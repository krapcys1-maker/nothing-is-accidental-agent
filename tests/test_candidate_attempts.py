"""Regresje Etapu 0 / Task 3: jawny, capowany retry kandydatów A2."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.core.ids import new_run_id
from app.llm.usage_tracker import UsageTracker
from app.models import (
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    SourceCandidateRecord,
    SourceCandidateStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.ports.storage import LifecycleTransitionError
from app.research.base import ResearchError
from app.research.fake_client import FakeResearchClient
from app.storage.repositories import SqliteStorage
from app.workflows.research.pipeline import (
    resume_staged_research,
    retry_failed_source_candidates,
    run_source_extraction,
)


def _topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Candidate attempts", question="How many?",
        score=90, status=TopicStatus.SELECTED,
    ))


def _staged_run(storage, account, topic, count: int = 1) -> str:
    run_id = new_run_id()
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_PENDING,
    ))
    storage.create_source_candidates(run_id, [
        SourceCandidateRecord(
            research_run_id=run_id, url=f"https://example.org/{index}", title=f"{index}",
        )
        for index in range(count)
    ])
    return run_id


def _extract(settings, storage, account, run_id, client, **kwargs):
    return run_source_extraction(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs,
    )


def _retry(settings, storage, account, run_id, **kwargs):
    return retry_failed_source_candidates(
        run_id, settings=settings, storage=storage, account_id=account.id, **kwargs,
    )


class _FailExtractionClient(FakeResearchClient):
    def extract_source(self, plan, candidate):
        raise ResearchError("planned A2 failure")


class _ForbiddenExtractionClient(FakeResearchClient):
    def extract_source(self, plan, candidate):  # pragma: no cover - test must fail first
        raise AssertionError("ordinary resume must not reset failed candidates")


def test_first_a2_attempt_is_preserved_on_success(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))

    _extract(settings, storage, account, run_id, FakeResearchClient("good"))

    candidate = storage.list_source_candidates(run_id)[0]
    assert candidate.status == SourceCandidateStatus.EXTRACTED
    assert candidate.attempts == 1


def test_first_a2_attempt_is_preserved_on_error(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))

    _extract(settings, storage, account, run_id, _FailExtractionClient("good"))

    candidate = storage.list_source_candidates(run_id)[0]
    assert candidate.status == SourceCandidateStatus.EXTRACTION_FAILED
    assert candidate.attempts == 1


def test_explicit_retry_resets_only_eligible_failed_and_second_attempt_is_two(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)

    result = _retry(settings, storage, account, run_id, max_attempts=2)
    candidate = storage.list_source_candidates(run_id)[0]
    assert result.reset_count == 1
    assert candidate.status == SourceCandidateStatus.PENDING_EXTRACTION
    assert candidate.attempts == 1

    _extract(
        settings, storage, account, run_id, FakeResearchClient("good"),
        max_attempts=2, explicit_resume=True,
    )
    candidate = storage.list_source_candidates(run_id)[0]
    assert candidate.status == SourceCandidateStatus.EXTRACTED
    assert candidate.attempts == 2


def test_retry_cap_and_idempotence_leave_pending_and_extracted_unchanged(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account), count=4)
    candidates = storage.list_source_candidates(run_id)
    storage.conn.execute(
        "UPDATE research_source_candidates SET status=?, attempts=? WHERE id=?",
        (SourceCandidateStatus.EXTRACTION_FAILED.value, 1, candidates[0].id),
    )
    storage.conn.execute(
        "UPDATE research_source_candidates SET status=?, attempts=? WHERE id=?",
        (SourceCandidateStatus.EXTRACTION_FAILED.value, 2, candidates[1].id),
    )
    storage.conn.execute(
        "UPDATE research_source_candidates SET status=?, attempts=? WHERE id=?",
        (SourceCandidateStatus.EXTRACTED.value, 1, candidates[2].id),
    )
    storage.conn.commit()
    storage.mark_research_run_partial(run_id, "fixture")

    first = _retry(settings, storage, account, run_id, max_attempts=2)
    second = _retry(settings, storage, account, run_id, max_attempts=2)
    after = storage.list_source_candidates(run_id)

    assert (first.reset_count, first.skipped_cap_count, first.already_pending_count) == (1, 1, 1)
    assert (second.reset_count, second.skipped_cap_count, second.already_pending_count) == (0, 1, 2)
    assert [candidate.status for candidate in after] == [
        SourceCandidateStatus.PENDING_EXTRACTION,
        SourceCandidateStatus.EXTRACTION_FAILED,
        SourceCandidateStatus.EXTRACTED,
        SourceCandidateStatus.PENDING_EXTRACTION,
    ]
    assert [candidate.attempts for candidate in after] == [1, 2, 1, 0]


def test_partial_exhausted_only_after_no_pending_or_eligible_failed(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account), count=2)

    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=1)

    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL_EXHAUSTED


def test_partial_with_eligible_failed_is_not_exhausted_and_normal_resume_does_not_retry(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account), count=1)
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)
    usage_before = list(storage.get_research_usage(run_id))

    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL
    summary = resume_staged_research(
        run_id, account, settings=settings, storage=storage,
        research_client=_ForbiddenExtractionClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), max_attempts=2,
    )

    assert summary.sources_extracted == 0
    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL
    assert storage.get_research_usage(run_id) == usage_before
    assert storage.list_source_candidates(run_id)[0].attempts == 1


def test_resume_partial_exhausted_refuses_before_model_call_or_usage(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account), count=1)
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=1)
    usage_before = list(storage.get_research_usage(run_id))

    with pytest.raises(ValueError, match="PARTIAL_EXHAUSTED"):
        resume_staged_research(
            run_id, account, settings=settings, storage=storage,
            research_client=_ForbiddenExtractionClient("good"),
            usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
            policy=PolicyEngine(settings, storage), notifier=LogNotification(), max_attempts=1,
        )

    assert storage.get_research_usage(run_id) == usage_before


@pytest.mark.parametrize("flow", [ResearchFlow.SINGLE, ResearchFlow.TWO_STAGE])
def test_retry_failed_candidates_rejects_non_staged_flow(settings, storage, account, flow):
    topic = _topic(storage, account)
    run_id = new_run_id()
    storage.create_run(Run(id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id), flow=flow,
        status=ResearchRunStatus.PARTIAL,
    ))

    with pytest.raises(ValueError, match="expected flow 'staged'"):
        _retry(settings, storage, account, run_id)


def test_retry_reset_has_zero_cost_and_creates_no_usage(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)
    before_usage = list(storage.get_research_usage(run_id))
    before_cost = storage.get_run(run_id).cost_usd

    _retry(settings, storage, account, run_id, max_attempts=2)

    assert storage.get_research_usage(run_id) == before_usage
    assert storage.get_run(run_id).cost_usd == before_cost


def test_cli_retry_is_explicit_reports_counts_and_never_constructs_model_client(
        settings, storage, account, monkeypatch, capsys):
    import scripts.run_capped_research as capped_script

    run_id = _staged_run(storage, account, _topic(storage, account))
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)
    usage_before = list(storage.get_research_usage(run_id))
    cost_before = storage.get_run(run_id).cost_usd
    monkeypatch.setattr(capped_script, "load_settings", lambda: settings)

    assert capped_script.main([
        "--resume", run_id, "--retry-failed-candidates", "--max-extraction-attempts", "2",
    ]) == 0

    output = capsys.readouterr().out
    assert "API nie zostało wywołane" in output
    assert "reset=1" in output
    assert storage.list_source_candidates(run_id)[0].status == SourceCandidateStatus.PENDING_EXTRACTION
    assert storage.list_source_candidates(run_id)[0].attempts == 1
    assert storage.get_research_usage(run_id) == usage_before
    assert storage.get_run(run_id).cost_usd == cost_before


def test_cli_retry_requires_explicit_resume(capsys):
    import scripts.run_capped_research as capped_script

    assert capped_script.main(["--retry-failed-candidates"]) == 1
    assert "wymaga --resume" in capsys.readouterr().out


def test_cli_retry_rejects_estimate_only_without_opening_storage(monkeypatch, capsys):
    import scripts.run_capped_research as capped_script

    monkeypatch.setattr(
        capped_script.SqliteStorage, "open",
        lambda path: pytest.fail("estimate-only retry must not open storage"),
    )

    assert capped_script.main([
        "--resume", "run-id", "--retry-failed-candidates", "--estimate-only",
    ]) == 1
    assert "nie łączy się z --estimate-only" in capsys.readouterr().out


def test_historical_failed_lower_bound_allows_only_one_new_retry(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    storage.conn.execute(
        "UPDATE research_source_candidates SET status=?, attempts=1 WHERE id=?",
        (SourceCandidateStatus.EXTRACTION_FAILED.value, candidate.id),
    )
    storage.conn.commit()
    storage.mark_research_run_partial(run_id, "historical lower bound")

    assert _retry(settings, storage, account, run_id, max_attempts=2).reset_count == 1
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)
    candidate = storage.list_source_candidates(run_id)[0]
    assert (candidate.status, candidate.attempts) == (
        SourceCandidateStatus.EXTRACTION_FAILED, 2,
    )
    result = _retry(settings, storage, account, run_id, max_attempts=2)
    assert (result.reset_count, result.skipped_cap_count) == (0, 1)


def test_claim_is_atomic_and_transitions_candidate_to_in_progress(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]

    assert storage.claim_source_candidate_attempt(candidate.id, max_attempts=2) == 1
    claimed = storage.list_source_candidates(run_id)[0]
    assert claimed.status == SourceCandidateStatus.EXTRACTION_IN_PROGRESS
    with pytest.raises(ValueError, match="not claimable"):
        storage.claim_source_candidate_attempt(candidate.id, max_attempts=2)
    assert storage.list_source_candidates(run_id)[0].attempts == 1


@pytest.mark.parametrize("attempts", [2, 3])
def test_claim_rejects_pending_candidate_at_or_above_cap(settings, storage, account, attempts):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    storage.conn.execute(
        "UPDATE research_source_candidates SET attempts=? WHERE id=?", (attempts, candidate.id),
    )
    storage.conn.commit()

    with pytest.raises(ValueError, match="not claimable"):
        storage.claim_source_candidate_attempt(candidate.id, max_attempts=2)
    unchanged = storage.list_source_candidates(run_id)[0]
    assert (unchanged.status, unchanged.attempts) == (
        SourceCandidateStatus.PENDING_EXTRACTION, attempts,
    )


def test_extraction_does_not_call_client_when_pending_candidate_is_at_cap(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    storage.conn.execute(
        "UPDATE research_source_candidates SET attempts=2 WHERE id=?", (candidate.id,),
    )
    storage.conn.commit()

    _extract(settings, storage, account, run_id, _ForbiddenExtractionClient("good"), max_attempts=2)
    unchanged = storage.list_source_candidates(run_id)[0]
    assert (unchanged.status, unchanged.attempts) == (
        SourceCandidateStatus.PENDING_EXTRACTION, 2,
    )
    assert storage.get_research_usage(run_id) == []


def test_two_concurrent_sqlite_connections_only_allow_one_candidate_claim(
        settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    barrier = Barrier(2)

    def claim() -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            local.claim_source_candidate_attempt(candidate.id, max_attempts=2)
            return "won"
        except LifecycleTransitionError:
            return "lost"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))

    assert sorted(results) == ["lost", "won"]
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.list_source_candidates(run_id)[0]
        assert persisted.attempts == 1
        assert persisted.status == SourceCandidateStatus.EXTRACTION_IN_PROGRESS
    finally:
        reopened.close()


def test_uncertain_claim_blocks_ordinary_resume_before_model_or_usage(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    storage.claim_source_candidate_attempt(candidate.id, max_attempts=2)
    usage_before = list(storage.get_research_usage(run_id))

    with pytest.raises(ValueError, match="EXTRACTION_IN_PROGRESS"):
        resume_staged_research(
            run_id, account, settings=settings, storage=storage,
            research_client=_ForbiddenExtractionClient("good"),
            usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
            policy=PolicyEngine(settings, storage), notifier=LogNotification(), max_attempts=2,
        )
    uncertain = storage.list_source_candidates(run_id)[0]
    assert uncertain.status == SourceCandidateStatus.EXTRACTION_IN_PROGRESS
    assert storage.get_research_usage(run_id) == usage_before


def test_partial_exhausted_reopens_only_with_explicit_higher_cap(settings, storage, account):
    run_id = _staged_run(storage, account, _topic(storage, account))
    candidate = storage.list_source_candidates(run_id)[0]
    storage.conn.execute(
        "UPDATE research_source_candidates SET status=?, attempts=2 WHERE id=?",
        (SourceCandidateStatus.EXTRACTION_FAILED.value, candidate.id),
    )
    storage.conn.commit()
    storage.mark_research_run_partial_exhausted(run_id, "fixture exhausted")
    usage_before = list(storage.get_research_usage(run_id))

    unchanged = _retry(settings, storage, account, run_id, max_attempts=2)
    assert unchanged.reset_count == 0
    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL_EXHAUSTED

    reopened = _retry(settings, storage, account, run_id, max_attempts=3)
    assert (reopened.reset_count, reopened.reopened_run) == (1, True)
    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL
    assert storage.list_source_candidates(run_id)[0].status == SourceCandidateStatus.PENDING_EXTRACTION
    assert storage.get_research_usage(run_id) == usage_before

    again = _retry(settings, storage, account, run_id, max_attempts=3)
    assert (again.reset_count, again.reopened_run) == (0, False)
    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL

    _extract(settings, storage, account, run_id, FakeResearchClient("good"), max_attempts=3)
    assert storage.list_source_candidates(run_id)[0].attempts == 3


def test_cli_retry_rejects_other_account_without_mutation(settings, storage, account, monkeypatch, capsys):
    import scripts.run_capped_research as capped_script

    run_id = _staged_run(storage, account, _topic(storage, account))
    _extract(settings, storage, account, run_id, _FailExtractionClient("good"), max_attempts=2)
    monkeypatch.setattr(capped_script, "load_settings", lambda: settings)

    assert capped_script.main([
        "--resume", run_id, "--retry-failed-candidates", "--account", "other-account",
    ]) == 1
    assert "nie do wybranego konta" in capsys.readouterr().out
    assert storage.list_source_candidates(run_id)[0].status == SourceCandidateStatus.EXTRACTION_FAILED
