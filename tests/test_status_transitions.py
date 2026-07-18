"""Etap 0 / Task 8: literal lifecycle guards for persisted status changes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.models import (
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    ResearchSourceRecord,
    Run,
    RunStatus,
    SourceCandidateRecord,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import LifecycleTransitionError
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage


def _topic(storage, account, title: str = "Lifecycle topic") -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=title,
        question=f"Why {title}?",
        status=TopicStatus.SELECTED,
    ))


def _research_run(storage, account, flow: ResearchFlow,
                  status: ResearchRunStatus, suffix: str) -> str:
    topic = _topic(storage, account, f"{flow.value}-{status.value}-{suffix}")
    run_id = f"lifecycle-{flow.value}-{status.value}-{suffix}"
    storage.create_run(Run(
        id=run_id,
        account_id=account.id,
        workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id,
        account_id=account.id,
        topic_id=int(topic.id),
        flow=flow,
        status=status,
    ))
    return run_id


def _candidate(storage, run_id: str) -> SourceCandidateRecord:
    candidate = SourceCandidateRecord(
        research_run_id=run_id,
        url=f"https://example.org/{run_id}",
        title="Candidate",
    )
    storage.create_source_candidates(run_id, [candidate])
    return candidate


@pytest.mark.parametrize("target", [RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.STOPPED])
def test_finish_run_allows_each_running_terminal_transition(storage, account, target):
    storage.ensure_account(account)
    run_id = f"run-to-{target.value.lower()}"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
    ))

    storage.finish_run(run_id, target.value, 0.25, error="failed" if target == RunStatus.FAILED else None)

    row = storage.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == target.value
    assert row["finished_at"] is not None


@pytest.mark.parametrize(
    ("initial", "target"),
    [
        (RunStatus.SUCCESS, RunStatus.FAILED),
        (RunStatus.FAILED, RunStatus.SUCCESS),
        (RunStatus.STOPPED, RunStatus.FAILED),
    ],
)
def test_finish_run_rejects_terminal_to_different_terminal_without_mutation(
        storage, account, initial, target):
    storage.ensure_account(account)
    run_id = f"illegal-{initial.value}-{target.value}"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
    ))
    storage.finish_run(run_id, initial.value, 0.1)
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError) as exc_info:
        storage.finish_run(run_id, target.value, 9.9, error="must not persist")

    assert exc_info.value.current_status == initial.value
    assert tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()) == before


def test_finish_run_missing_record_is_a_typed_transition_error(storage):
    with pytest.raises(LifecycleTransitionError) as exc_info:
        storage.finish_run("missing-run", RunStatus.SUCCESS.value, 0.0)
    assert exc_info.value.current_status is None
    assert exc_info.value.entity == "run"


def test_finish_run_rejects_failed_rewrite_for_non_research_run_after_reopen(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    run_id = "ordinary-failed-is-immutable"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.TOPIC,
    ))
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="attempt one")
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.finish_run(run_id, RunStatus.FAILED.value, 0.2, error="attempt two")
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert tuple(reopened.conn.execute(
            "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
        ).fetchone()) == before
    finally:
        reopened.close()


def test_explicit_research_resume_can_update_failed_audit(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.PARTIAL,
        "explicit-resume",
    )
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="attempt one")
    snapshot = storage.get_run(run_id)

    storage.finish_resumed_research_run(
        run_id, account.id, ResearchFlow.STAGED, snapshot.finished_at,
        0.2, "attempt two",
    )

    row = storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()
    assert tuple(row[:3]) == (RunStatus.FAILED.value, 0.2, "attempt two")
    assert row["finished_at"] != snapshot.finished_at.strftime("%Y-%m-%d %H:%M:%S")


def test_explicit_resume_rejects_missing_research_run_without_mutation(storage, account):
    storage.ensure_account(account)
    run_id = "missing-research-row"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
    ))
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="initial")
    snapshot = storage.get_run(run_id)
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.finish_resumed_research_run(
            run_id, account.id, ResearchFlow.STAGED, snapshot.finished_at,
            0.2, "must not persist",
        )

    assert tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()) == before


@pytest.mark.parametrize(
    ("stored_flow", "stored_status", "expected_flow"),
    [
        (ResearchFlow.SINGLE, ResearchRunStatus.PARTIAL, ResearchFlow.SINGLE),
        (ResearchFlow.TWO_STAGE, ResearchRunStatus.PARTIAL, ResearchFlow.STAGED),
        (ResearchFlow.STAGED, ResearchRunStatus.COMPLETE, ResearchFlow.STAGED),
    ],
)
def test_explicit_resume_rejects_single_wrong_flow_or_nonresumable_status(
        storage, account, stored_flow, stored_status, expected_flow):
    run_id = _research_run(storage, account, stored_flow, stored_status, expected_flow.value)
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="initial")
    snapshot = storage.get_run(run_id)
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.finish_resumed_research_run(
            run_id, account.id, expected_flow, snapshot.finished_at,
            0.2, "must not persist",
        )

    assert tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()) == before


def test_explicit_resume_rejects_account_mismatch_without_mutation(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.TWO_STAGE, ResearchRunStatus.PARTIAL,
        "account-mismatch",
    )
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="initial")
    snapshot = storage.get_run(run_id)
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.finish_resumed_research_run(
            run_id, "other-account", ResearchFlow.TWO_STAGE,
            snapshot.finished_at, 0.2, "must not persist",
        )

    assert tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()) == before


def test_dry_run_can_finish_as_dry_run_and_identical_repeat_is_no_op(storage, account):
    storage.ensure_account(account)
    run_id = "dry-run-terminal"
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.DRY_RUN,
    ))
    storage.finish_run(run_id, RunStatus.DRY_RUN.value, 0.0)
    before = tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone())

    storage.finish_run(run_id, RunStatus.DRY_RUN.value, 0.0)

    assert tuple(storage.conn.execute(
        "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
    ).fetchone()) == before


def test_competing_terminal_run_transitions_only_one_wins(tmp_path, account):
    db_path = tmp_path / "run-race.db"
    initialize_database(db_path)
    seed = SqliteStorage.open(db_path)
    seed.ensure_account(account)
    seed.create_run(Run(
        id="race-run", account_id=account.id, workflow=WorkflowType.RESEARCH,
    ))
    seed.close()
    barrier = Barrier(2)

    def finish(target: RunStatus) -> str:
        local = SqliteStorage.open(db_path)
        try:
            barrier.wait()
            local.finish_run("race-run", target.value, 0.0)
            return "won"
        except LifecycleTransitionError:
            return "lost"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, (RunStatus.SUCCESS, RunStatus.STOPPED)))

    assert sorted(results) == ["lost", "won"]


def test_competing_failed_resume_finalizations_use_compare_and_swap(tmp_path, account):
    db_path = tmp_path / "failed-resume-race.db"
    initialize_database(db_path)
    seed = SqliteStorage.open(db_path)
    run_id = _research_run(
        seed, account, ResearchFlow.STAGED, ResearchRunStatus.PARTIAL,
        "failed-resume-race",
    )
    seed.finish_run(run_id, RunStatus.FAILED.value, 0.1, error="initial")
    snapshot = seed.get_run(run_id)
    seed.conn.executescript(
        "CREATE TABLE run_update_audit (id INTEGER PRIMARY KEY);"
        "CREATE TRIGGER audit_failed_resume AFTER UPDATE ON runs "
        f"WHEN NEW.id='{run_id}' BEGIN "
        "INSERT INTO run_update_audit VALUES (NULL); END;"
    )
    seed.conn.commit()
    seed.close()
    barrier = Barrier(2)

    def finish(error: str) -> str:
        local = SqliteStorage.open(db_path)
        try:
            barrier.wait()
            local.finish_resumed_research_run(
                run_id, account.id, ResearchFlow.STAGED,
                snapshot.finished_at, 0.2, error,
            )
            return "won"
        except LifecycleTransitionError:
            return "lost"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, ("resume-a", "resume-b")))

    check = SqliteStorage.open(db_path)
    try:
        assert sorted(results) == ["lost", "won"]
        assert check.conn.execute("SELECT count(*) FROM run_update_audit").fetchone()[0] == 1
    finally:
        check.close()


@pytest.mark.parametrize(
    ("flow", "source", "method", "target"),
    [
        (ResearchFlow.SINGLE, ResearchRunStatus.PENDING,
         "mark_research_run_failed", ResearchRunStatus.FAILED),
        (ResearchFlow.TWO_STAGE, ResearchRunStatus.PENDING,
         "mark_research_run_failed", ResearchRunStatus.FAILED),
        (ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_PENDING,
         "mark_research_run_failed", ResearchRunStatus.FAILED),
        (ResearchFlow.TWO_STAGE, ResearchRunStatus.SOURCE_COLLECTED,
         "mark_research_run_partial", ResearchRunStatus.PARTIAL),
        (ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_COMPLETE,
         "mark_research_run_partial", ResearchRunStatus.PARTIAL),
        (ResearchFlow.STAGED, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
         "mark_research_run_partial", ResearchRunStatus.PARTIAL),
        (ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_COMPLETE,
         "mark_extraction_in_progress", ResearchRunStatus.EXTRACTION_IN_PROGRESS),
        (ResearchFlow.STAGED, ResearchRunStatus.PARTIAL,
         "mark_extraction_in_progress", ResearchRunStatus.EXTRACTION_IN_PROGRESS),
        (ResearchFlow.STAGED, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
         "mark_sources_complete", ResearchRunStatus.SOURCES_COMPLETE),
        (ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_COMPLETE,
         "mark_research_run_partial_exhausted", ResearchRunStatus.PARTIAL_EXHAUSTED),
        (ResearchFlow.STAGED, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
         "mark_research_run_partial_exhausted", ResearchRunStatus.PARTIAL_EXHAUSTED),
        (ResearchFlow.STAGED, ResearchRunStatus.PARTIAL,
         "mark_research_run_partial_exhausted", ResearchRunStatus.PARTIAL_EXHAUSTED),
        (ResearchFlow.STAGED, ResearchRunStatus.SOURCES_COMPLETE,
         "mark_synthesis_pending", ResearchRunStatus.SYNTHESIS_PENDING),
        (ResearchFlow.STAGED, ResearchRunStatus.SYNTHESIS_PENDING,
         "revert_to_sources_complete", ResearchRunStatus.SOURCES_COMPLETE),
    ],
)
def test_research_run_transition_matrix_allows_legal_edges(
        storage, account, flow, source, method, target):
    run_id = _research_run(storage, account, flow, source, method)
    call = getattr(storage, method)
    if method in {
        "mark_research_run_failed", "mark_research_run_partial",
        "mark_research_run_partial_exhausted", "revert_to_sources_complete",
    }:
        call(run_id, "expected test transition")
    else:
        call(run_id)
    assert storage.get_research_run(run_id).status == target


@pytest.mark.parametrize(
    "method",
    [
        "mark_research_run_failed",
        "mark_research_run_partial",
        "mark_extraction_in_progress",
        "mark_sources_complete",
        "mark_research_run_partial_exhausted",
        "mark_synthesis_pending",
        "revert_to_sources_complete",
    ],
)
def test_research_run_status_helpers_reject_missing_records(storage, method):
    call = getattr(storage, method)
    args = ("missing-research-run", "error") if method in {
        "mark_research_run_failed", "mark_research_run_partial",
        "mark_research_run_partial_exhausted", "revert_to_sources_complete",
    } else ("missing-research-run",)
    with pytest.raises(LifecycleTransitionError) as exc_info:
        call(*args)
    assert exc_info.value.current_status is None


def test_complete_to_partial_and_cross_flow_are_rejected_without_field_changes(storage, account):
    complete_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.COMPLETE, "complete",
    )
    cross_flow_id = _research_run(
        storage, account, ResearchFlow.TWO_STAGE,
        ResearchRunStatus.EXTRACTION_IN_PROGRESS, "cross-flow",
    )
    before = tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (complete_id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.mark_research_run_partial(complete_id, "must not persist")
    with pytest.raises(LifecycleTransitionError) as exc_info:
        storage.mark_sources_complete(cross_flow_id)

    assert exc_info.value.current_status == "two_stage:EXTRACTION_IN_PROGRESS"
    assert tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (complete_id,),
    ).fetchone()) == before


def test_stage_a_transition_and_source_inserts_are_one_atomic_unit(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _research_run(
        storage, account, ResearchFlow.TWO_STAGE, ResearchRunStatus.COMPLETE, "stage-a-illegal",
    )
    source = ResearchSourceRecord(
        research_run_id=run_id, url="https://example.org/source",
    )

    with pytest.raises(LifecycleTransitionError):
        storage.mark_research_stage_a_success(run_id, [source])
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.list_research_sources(run_id) == []
        assert reopened.get_research_run(run_id).status == ResearchRunStatus.COMPLETE
    finally:
        reopened.close()


def test_stage_a_transition_allows_two_stage_pending_and_rejects_missing(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.TWO_STAGE, ResearchRunStatus.PENDING, "stage-a-legal",
    )
    source = ResearchSourceRecord(
        research_run_id=run_id, url="https://example.org/legal-source",
    )

    storage.mark_research_stage_a_success(run_id, [source])

    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCE_COLLECTED
    assert len(storage.list_research_sources(run_id)) == 1
    with pytest.raises(LifecycleTransitionError) as exc_info:
        storage.mark_research_stage_a_success("missing-stage-a", [])
    assert exc_info.value.current_status is None


def test_discovery_transition_and_candidate_inserts_are_one_atomic_unit(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.COMPLETE, "a1-illegal",
    )
    candidate = SourceCandidateRecord(
        research_run_id=run_id, url="https://example.org/candidate",
    )

    with pytest.raises(LifecycleTransitionError):
        storage.create_source_candidates(run_id, [candidate])
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.list_source_candidates(run_id) == []
        assert reopened.get_research_run(run_id).status == ResearchRunStatus.COMPLETE
    finally:
        reopened.close()


def test_extraction_in_progress_identical_repeat_is_explicitly_idempotent(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED,
        ResearchRunStatus.EXTRACTION_IN_PROGRESS, "idempotent",
    )
    before = tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (run_id,),
    ).fetchone())
    storage.mark_extraction_in_progress(run_id)
    assert tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (run_id,),
    ).fetchone()) == before


def test_partial_identical_repeat_is_no_op_but_new_resume_error_is_recorded(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.PARTIAL, "partial-repeat",
    )
    storage.mark_research_run_partial(run_id, "attempt one")
    before = tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (run_id,),
    ).fetchone())
    storage.mark_research_run_partial(run_id, "attempt one")
    assert tuple(storage.conn.execute(
        "SELECT status, error, updated_at FROM research_runs WHERE id=?", (run_id,),
    ).fetchone()) == before

    storage.mark_research_run_partial(run_id, "attempt two")
    assert storage.get_research_run(run_id).error == "attempt two"


def test_candidate_lifecycle_allows_claim_success_and_failure(storage, account):
    success_run = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_PENDING, "candidate-ok",
    )
    success = _candidate(storage, success_run)
    assert storage.claim_source_candidate_attempt(int(success.id), max_attempts=2) == 1
    storage.update_source_candidate_extracted(
        int(success.id), title="Extracted", author_or_org=None, published_at=None,
        source_type=SourceType.OTHER, supported_claims=["claim"], numeric_facts=[],
        verification_status=SourceVerification.UNVERIFIED, source_quality_score=0.5,
    )
    assert storage.list_source_candidates(success_run)[0].status == SourceCandidateStatus.EXTRACTED

    failed_run = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_PENDING, "candidate-fail",
    )
    failed = _candidate(storage, failed_run)
    storage.claim_source_candidate_attempt(int(failed.id), max_attempts=2)
    storage.mark_source_candidate_failed(int(failed.id), "expected")
    assert storage.list_source_candidates(failed_run)[0].status == SourceCandidateStatus.EXTRACTION_FAILED


@pytest.mark.parametrize(
    "method",
    ["claim_source_candidate_attempt", "update_source_candidate_extracted", "mark_source_candidate_failed"],
)
def test_candidate_status_helpers_reject_missing_records(storage, method):
    with pytest.raises(LifecycleTransitionError) as exc_info:
        if method == "claim_source_candidate_attempt":
            storage.claim_source_candidate_attempt(999999, max_attempts=2)
        elif method == "mark_source_candidate_failed":
            storage.mark_source_candidate_failed(999999, "missing")
        else:
            storage.update_source_candidate_extracted(
                999999, title=None, author_or_org=None, published_at=None,
                source_type=SourceType.OTHER, supported_claims=[], numeric_facts=[],
                verification_status=SourceVerification.UNVERIFIED,
                source_quality_score=0.0,
            )
    assert exc_info.value.current_status is None


def test_pending_to_extracted_is_rejected_without_partial_candidate_mutation(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_PENDING, "candidate-illegal",
    )
    candidate = _candidate(storage, run_id)
    before = tuple(storage.conn.execute(
        "SELECT * FROM research_source_candidates WHERE id=?", (candidate.id,),
    ).fetchone())

    with pytest.raises(LifecycleTransitionError):
        storage.update_source_candidate_extracted(
            int(candidate.id), title="must not persist", author_or_org="no",
            published_at="2026-01-01", source_type=SourceType.PRIMARY,
            supported_claims=["no"], numeric_facts=["no"],
            verification_status=SourceVerification.VERIFIED, source_quality_score=1.0,
        )

    assert tuple(storage.conn.execute(
        "SELECT * FROM research_source_candidates WHERE id=?", (candidate.id,),
    ).fetchone()) == before


def test_failed_candidate_reopens_only_through_explicit_retry_contract(storage, account):
    run_id = _research_run(
        storage, account, ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_PENDING, "candidate-retry",
    )
    candidate = _candidate(storage, run_id)
    storage.claim_source_candidate_attempt(int(candidate.id), max_attempts=2)
    storage.mark_source_candidate_failed(int(candidate.id), "retry me")
    storage.mark_research_run_partial(run_id, "retryable")

    with pytest.raises(LifecycleTransitionError):
        storage.claim_source_candidate_attempt(int(candidate.id), max_attempts=2)
    result = storage.retry_failed_source_candidates(run_id, max_attempts=2)

    assert result.reset_count == 1
    assert storage.list_source_candidates(run_id)[0].status == SourceCandidateStatus.PENDING_EXTRACTION
