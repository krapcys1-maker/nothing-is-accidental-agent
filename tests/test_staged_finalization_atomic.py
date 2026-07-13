"""Regresje F4: staged B zapisuje kartę i lifecycle jako jedną transakcję."""
from __future__ import annotations

import threading
import sqlite3
from datetime import timedelta

import pytest

from app.core.ids import new_run_id
from app.models import (
    ModelUsage,
    ResearchCard,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    RunStatus,
    Source,
    SourceCandidateRecord,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    StagedFinalizationContext,
    StagedFinalizationFaultPoint,
    StagedFinalizationMode,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import ResearchTopicIntegrityError
from app.storage.repositories import SqliteStorage


def _prepared_staged_run(
    storage, account, *, sources: int = 2, force_reresearch: bool = False,
) -> tuple[str, Topic]:
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Atomic staged card", question="Why atomic?",
        score=91.0, status=TopicStatus.SELECTED,
    ))
    run_id = new_run_id()
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id), flow=ResearchFlow.STAGED,
        status=ResearchRunStatus.DISCOVERY_PENDING,
        is_force_reresearch=force_reresearch,
    ))
    candidates = storage.create_source_candidates(run_id, [
        SourceCandidateRecord(research_run_id=run_id, url=f"https://example.test/{index}")
        for index in range(sources)
    ])
    storage.mark_extraction_in_progress(run_id)
    for candidate in candidates:
        storage.claim_source_candidate_attempt(int(candidate.id), max_attempts=1)
        storage.update_source_candidate_extracted(
            int(candidate.id), title=f"Source {candidate.id}", author_or_org="Org",
            published_at="2026-01-01", source_type=SourceType.PRIMARY,
            supported_claims=["Claim"], numeric_facts=[],
            verification_status=SourceVerification.VERIFIED, source_quality_score=0.9,
        )
    storage.mark_sources_complete(run_id)
    storage.mark_synthesis_pending(run_id)
    storage.add_model_usage(ModelUsage(
        run_id=run_id, provider="fake", model="fake", task="research_synthesize_cards",
        input_tokens=10, output_tokens=10, estimated_cost_usd=0.123,
    ))
    return run_id, topic


def _card(topic: Topic, *, sources: int = 2, thesis: str = "Atomic thesis") -> ResearchCard:
    return ResearchCard(
        topic_id=int(topic.id), question=topic.question or "Why atomic?", working_thesis=thesis,
        confirmed_claims=["Claim"], sources=[
            Source(
                url=f"https://example.test/{index}", title=f"Source {index + 1}",
                author_or_org="Org", published_at="2026-01-01", source_type=SourceType.PRIMARY,
                supports_claim="Claim", verification_status=SourceVerification.VERIFIED,
            )
            for index in range(sources)
        ],
    )


def _fresh_context(*, force_reresearch: bool = False) -> StagedFinalizationContext:
    return StagedFinalizationContext(
        mode=(
            StagedFinalizationMode.FORCE_RERESEARCH
            if force_reresearch else StagedFinalizationMode.FRESH
        ),
        expected_run_status=RunStatus.RUNNING,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
    )


def _resume_context(failed: Run, marker: str, *, force_reresearch: bool = False) -> StagedFinalizationContext:
    assert failed.finished_at is not None
    return StagedFinalizationContext(
        mode=(
            StagedFinalizationMode.FORCE_RERESEARCH_RESUME_B
            if force_reresearch else StagedFinalizationMode.RESUME_B
        ),
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=failed.finished_at,
        expected_failure_marker=marker,
    )


def _finalize(
    storage, run_id: str, card: ResearchCard,
    *, context: StagedFinalizationContext | None = None, total_cost: float = 0.123,
) -> ResearchCard:
    return storage.finalize_staged_research_with_card(
        run_id, card, total_cost, terminal_run_status=RunStatus.SUCCESS,
        min_sources=2, min_verified_sources=2, context=context or _fresh_context(),
    )


def _state(storage, run_id: str, topic_id: int) -> tuple:
    return tuple(storage.conn.execute(
        "SELECT rr.status, rr.research_card_id, rr.total_cost_usd, rr.stage_b_completed_at, "
        "r.status, r.cost_usd, r.error, r.finished_at, t.status "
        "FROM research_runs rr JOIN runs r ON r.id=rr.id JOIN topics t ON t.id=rr.topic_id "
        "WHERE rr.id=? AND t.id=?", (run_id, topic_id),
    ).fetchone())


def _counts(storage, run_id: str) -> tuple[int, int, int]:
    return (
        storage.conn.execute("SELECT COUNT(*) FROM research_cards").fetchone()[0],
        storage.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        storage.conn.execute(
            "SELECT COUNT(*) FROM research_stage_results WHERE research_run_id=? AND stage='B' AND status='SUCCESS'",
            (run_id,),
        ).fetchone()[0],
    )


def _terminal_snapshot(storage, run_id: str, topic_id: int) -> tuple:
    return (
        _state(storage, run_id, topic_id),
        _counts(storage, run_id),
        tuple(storage.conn.execute(
            "SELECT status, finished_at, error FROM research_stage_results "
            "WHERE research_run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()),
        tuple(storage.conn.execute(
            "SELECT is_force_reresearch, error, updated_at FROM research_runs WHERE id=?",
            (run_id,),
        ).fetchone()),
    )


def _assert_terminal_conflict_reopens(
    settings, storage, run_id: str, topic: Topic, card: ResearchCard,
    context: StagedFinalizationContext,
) -> SqliteStorage:
    before = _terminal_snapshot(storage, run_id, int(topic.id))
    with pytest.raises(ResearchTopicIntegrityError):
        _finalize(storage, run_id, card, context=context)
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    assert _terminal_snapshot(reopened, run_id, int(topic.id)) == before
    return reopened


def _completed_resume(
    storage, account, *, force_reresearch: bool = False,
) -> tuple[str, Topic, ResearchCard, StagedFinalizationContext]:
    run_id, topic = _prepared_staged_run(
        storage, account, force_reresearch=force_reresearch,
    )
    marker = "[synthesize_from_cards] ResearchParseError: prior B failure"
    storage.revert_to_sources_complete(run_id, error=marker)
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.123, error=marker)
    failed = storage.get_run(run_id)
    assert failed is not None and failed.finished_at is not None
    context = _resume_context(failed, marker, force_reresearch=force_reresearch)
    storage.add_research_stage_result(
        run_id, ResearchStageName.B, ResearchStageStatus.FAILED,
        error=marker, finished_at=failed.finished_at,
    )
    storage.preflight_staged_finalization(
        run_id, terminal_run_status=RunStatus.SUCCESS, context=context,
    )
    storage.mark_synthesis_pending(run_id)
    return run_id, topic, _finalize(storage, run_id, _card(topic), context=context), context


def test_staged_finalization_commits_card_sources_stage_and_lifecycle_together(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)

    card = _finalize(storage, run_id, _card(topic))
    storage.close()
    storage = SqliteStorage.open(settings.db_path)

    assert card.id is not None
    assert _counts(storage, run_id) == (1, 2, 1)
    state = _state(storage, run_id, int(topic.id))
    assert state[0] == ResearchRunStatus.COMPLETE.value
    assert state[1] == card.id
    assert state[2] == pytest.approx(0.123)
    assert state[3] is not None
    assert state[4] == RunStatus.SUCCESS.value
    assert state[5] == pytest.approx(0.123)
    assert state[6] is None and state[7] is not None
    assert state[8] == TopicStatus.USED.value
    assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    storage.close()


@pytest.mark.parametrize("fault", ["card", "source", "stage", "lifecycle"])
def test_staged_finalization_rolls_back_every_crash_point(settings, account, monkeypatch, fault):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    card = _card(topic)
    before = _state(storage, run_id, int(topic.id))

    if fault == "card":
        monkeypatch.setattr(storage, "_insert_finalization_card", lambda _card: (_ for _ in ()).throw(RuntimeError("card")))
    elif fault == "source":
        original = storage._insert_finalization_source
        calls = 0

        def fail_second_source(source):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second source")
            original(source)

        monkeypatch.setattr(storage, "_insert_finalization_source", fail_second_source)
    elif fault == "stage":
        monkeypatch.setattr(storage, "_insert_finalization_stage_b_success", lambda _run_id: (_ for _ in ()).throw(RuntimeError("stage")))
    else:
        storage.conn.execute(
            "CREATE TRIGGER fail_final_runs BEFORE UPDATE ON runs "
            "BEGIN SELECT RAISE(FAIL, 'lifecycle'); END"
        )
        storage.conn.commit()

    with pytest.raises((RuntimeError, sqlite3.IntegrityError)):
        _finalize(storage, run_id, card)

    assert _counts(storage, run_id) == (0, 0, 0)
    assert _state(storage, run_id, int(topic.id)) == before
    assert card.id is None
    assert all(source.id is None and source.research_card_id is None for source in card.sources)
    storage.close()


def test_staged_finalization_identical_repeat_is_noop_and_conflict_fails_closed(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    first = _finalize(storage, run_id, _card(topic))
    before_state, before_counts = _state(storage, run_id, int(topic.id)), _counts(storage, run_id)

    repeated = _finalize(storage, run_id, first)
    assert repeated.id == first.id
    assert _state(storage, run_id, int(topic.id)) == before_state
    assert _counts(storage, run_id) == before_counts

    with pytest.raises(ResearchTopicIntegrityError, match="Sprzeczna"):
        _finalize(storage, run_id, _card(topic, thesis="Different thesis"))
    assert _state(storage, run_id, int(topic.id)) == before_state
    assert _counts(storage, run_id) == before_counts
    storage.close()


def test_terminal_complete_noop_rejects_conflicting_fresh_force_and_resume_modes(
        settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    first = _finalize(storage, run_id, _card(topic))
    before = _terminal_snapshot(storage, run_id, int(topic.id))

    repeated = _finalize(storage, run_id, first, context=_fresh_context())
    assert repeated.id == first.id
    assert _terminal_snapshot(storage, run_id, int(topic.id)) == before

    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, first,
        _fresh_context(force_reresearch=True),
    )
    terminal = storage.get_run(run_id)
    assert terminal is not None and terminal.finished_at is not None
    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, first,
        _resume_context(terminal, "not-a-durable-failure"),
    )
    storage.close()


def test_terminal_complete_noop_rejects_conflicting_force_and_force_resume_modes(
        settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account, force_reresearch=True)
    first = _finalize(storage, run_id, _card(topic), context=_fresh_context(force_reresearch=True))
    before = _terminal_snapshot(storage, run_id, int(topic.id))

    repeated = _finalize(
        storage, run_id, first, context=_fresh_context(force_reresearch=True),
    )
    assert repeated.id == first.id
    assert _terminal_snapshot(storage, run_id, int(topic.id)) == before

    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, first, _fresh_context(),
    )
    terminal = storage.get_run(run_id)
    assert terminal is not None and terminal.finished_at is not None
    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, first,
        _resume_context(
            terminal, "not-a-durable-failure", force_reresearch=True,
        ),
    )
    storage.close()


def test_terminal_resume_noop_requires_matching_durable_cas_snapshot(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic, card, context = _completed_resume(storage, account)
    before = _terminal_snapshot(storage, run_id, int(topic.id))

    repeated = _finalize(storage, run_id, card, context=context)
    assert repeated.id == card.id
    assert _terminal_snapshot(storage, run_id, int(topic.id)) == before

    assert context.expected_finished_at is not None
    stale_timestamp = StagedFinalizationContext(
        mode=StagedFinalizationMode.RESUME_B,
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=context.expected_finished_at + timedelta(seconds=1),
        expected_failure_marker=context.expected_failure_marker,
    )
    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, card, stale_timestamp,
    )
    wrong_marker = StagedFinalizationContext(
        mode=StagedFinalizationMode.RESUME_B,
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=context.expected_finished_at,
        expected_failure_marker="different-failure-marker",
    )
    storage = _assert_terminal_conflict_reopens(
        settings, storage, run_id, topic, card, wrong_marker,
    )
    storage.close()


def test_two_sqlite_connections_finalize_once_without_partial_duplicate(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(setup, account)
    setup.close()
    barrier = threading.Barrier(2)
    results: list[int] = []
    failures: list[BaseException] = []

    def worker() -> None:
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            results.append(int(_finalize(storage, run_id, _card(topic)).id))
        except BaseException as exc:  # assertion below reports unexpected sqlite failures
            failures.append(exc)
        finally:
            storage.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    storage = SqliteStorage.open(settings.db_path)
    assert failures == []
    assert len(results) == 2 and results[0] == results[1]
    assert _counts(storage, run_id) == (1, 2, 1)
    assert _state(storage, run_id, int(topic.id))[0] == ResearchRunStatus.COMPLETE.value
    storage.close()


def test_staged_finalization_rejects_noncanonical_cost_without_mutation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    before = _state(storage, run_id, int(topic.id))

    with pytest.raises(ResearchTopicIntegrityError, match="kanoniczną sumą"):
        storage.finalize_staged_research_with_card(
            run_id, _card(topic), 0.124, terminal_run_status=RunStatus.SUCCESS,
            min_sources=2, min_verified_sources=2, context=_fresh_context(),
        )
    assert _counts(storage, run_id) == (0, 0, 0)
    assert _state(storage, run_id, int(topic.id)) == before
    storage.close()


def test_failed_run_cannot_be_promoted_by_a_forged_finalization_context(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.123, error="prior B failure")

    with pytest.raises(ResearchTopicIntegrityError):
        _finalize(storage, run_id, _card(topic))
    assert _counts(storage, run_id) == (0, 0, 0)

    failed = storage.get_run(run_id)
    assert failed is not None and failed.finished_at is not None and failed.error is not None
    forged = StagedFinalizationContext(
        mode=StagedFinalizationMode.RESUME_B,
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=failed.finished_at,
        expected_failure_marker=failed.error,
    )
    with pytest.raises(ResearchTopicIntegrityError):
        _finalize(storage, run_id, _card(topic), context=forged)
    assert _counts(storage, run_id) == (0, 0, 0)
    assert _state(storage, run_id, int(topic.id))[4] == RunStatus.FAILED.value
    storage.close()


def test_staged_finalization_resume_requires_matching_failed_snapshot(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    failure_marker = "[synthesize_from_cards] ResearchParseError: prior B failure"
    storage.revert_to_sources_complete(run_id, error=failure_marker)
    storage.finish_run(run_id, RunStatus.FAILED.value, 0.123, error=failure_marker)
    failed = storage.get_run(run_id)
    assert failed is not None and failed.finished_at is not None
    storage.add_research_stage_result(
        run_id, ResearchStageName.B, ResearchStageStatus.FAILED,
        error=failure_marker, finished_at=failed.finished_at,
    )
    context = StagedFinalizationContext(
        mode=StagedFinalizationMode.RESUME_B,
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=failed.finished_at,
        expected_failure_marker=failure_marker,
    )
    stale_timestamp_context = StagedFinalizationContext(
        mode=StagedFinalizationMode.RESUME_B,
        expected_run_status=RunStatus.FAILED,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        expected_finished_at=failed.finished_at + timedelta(seconds=1),
        expected_failure_marker=failure_marker,
    )
    with pytest.raises(ResearchTopicIntegrityError, match="FAILED/CAS snapshot"):
        storage.preflight_staged_finalization(
            run_id, terminal_run_status=RunStatus.SUCCESS,
            context=stale_timestamp_context,
        )

    storage.preflight_staged_finalization(
        run_id, terminal_run_status=RunStatus.SUCCESS, context=context,
    )
    storage.mark_synthesis_pending(run_id)
    card = _finalize(storage, run_id, _card(topic), context=context)

    assert card.id is not None
    assert _state(storage, run_id, int(topic.id))[4] == RunStatus.SUCCESS.value
    storage.close()


def test_generic_stage_audit_cannot_bypass_staged_b_atomic_finalizer(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)

    with pytest.raises(ResearchTopicIntegrityError, match="atomic finalization helper"):
        storage.add_research_stage_result(
            run_id, ResearchStageName.B, ResearchStageStatus.SUCCESS,
        )

    assert _counts(storage, run_id) == (0, 0, 0)
    assert _state(storage, run_id, int(topic.id))[0] == ResearchRunStatus.SYNTHESIS_PENDING.value
    storage.close()


@pytest.mark.parametrize(
    ("point", "source_index"),
    [
        (StagedFinalizationFaultPoint.BEFORE_CARD_INSERT, None),
        (StagedFinalizationFaultPoint.AFTER_CARD_INSERT, None),
        (StagedFinalizationFaultPoint.AFTER_FIRST_SOURCE_INSERT, None),
        (StagedFinalizationFaultPoint.BEFORE_SOURCE_INSERT, 1),
        (StagedFinalizationFaultPoint.AFTER_ALL_SOURCE_INSERTS, None),
        (StagedFinalizationFaultPoint.BEFORE_STAGE_B_SUCCESS_INSERT, None),
        (StagedFinalizationFaultPoint.AFTER_STAGE_B_SUCCESS_INSERT, None),
        (StagedFinalizationFaultPoint.BEFORE_RESEARCH_RUN_UPDATE, None),
        (StagedFinalizationFaultPoint.AFTER_RESEARCH_RUN_UPDATE, None),
        (StagedFinalizationFaultPoint.BEFORE_RUN_UPDATE, None),
        (StagedFinalizationFaultPoint.AFTER_RUN_UPDATE, None),
        (StagedFinalizationFaultPoint.BEFORE_TOPIC_USED_UPDATE, None),
        (StagedFinalizationFaultPoint.AFTER_TOPIC_USED_UPDATE, None),
    ],
)
def test_every_staged_finalization_fault_rolls_back_after_reopen(
        settings, account, monkeypatch, point, source_index):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    card = _card(topic)
    before_state = _state(storage, run_id, int(topic.id))
    before_usage = tuple(storage.conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(estimated_cost_usd), 0.0) FROM model_usage WHERE run_id=?",
        (run_id,),
    ).fetchone())

    def inject(current_point, current_source_index=None):
        if current_point == point and (
            source_index is None or current_source_index == source_index
        ):
            raise RuntimeError(f"fault:{point.value}")

    monkeypatch.setattr(storage, "_finalization_fault_point", inject)
    with pytest.raises(RuntimeError, match=f"fault:{point.value}"):
        _finalize(storage, run_id, card)
    assert card.id is None
    assert all(source.id is None and source.research_card_id is None for source in card.sources)
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    assert _counts(reopened, run_id) == (0, 0, 0)
    assert _state(reopened, run_id, int(topic.id)) == before_state
    assert tuple(reopened.conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(estimated_cost_usd), 0.0) FROM model_usage WHERE run_id=?",
        (run_id,),
    ).fetchone()) == before_usage
    assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


@pytest.mark.parametrize("case", ["account", "topic", "flow", "status", "verified", "unknown_run"])
def test_staged_finalizer_integrity_preconditions_leave_no_partial_records(settings, account, case):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    card = _card(topic)
    if case == "account":
        other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
        storage.ensure_account(other)
        storage.conn.execute("UPDATE research_runs SET account_id=? WHERE id=?", (other.id, run_id))
    elif case == "topic":
        other_topic = storage.add_topic(account.id, Topic(
            account_id=account.id, title="Other", question="Other?", score=90,
            status=TopicStatus.SELECTED,
        ))
        storage.conn.execute("UPDATE research_runs SET topic_id=? WHERE id=?", (other_topic.id, run_id))
    elif case == "flow":
        storage.conn.execute("UPDATE research_runs SET flow=? WHERE id=?", (ResearchFlow.SINGLE.value, run_id))
    elif case == "status":
        storage.conn.execute(
            "UPDATE research_runs SET status=? WHERE id=?",
            (ResearchRunStatus.DISCOVERY_COMPLETE.value, run_id),
        )
    elif case == "verified":
        storage.conn.execute(
            "UPDATE research_source_candidates SET verification_status='UNVERIFIED' "
            "WHERE research_run_id=? AND url=?",
            (run_id, card.sources[0].url),
        )
        card.sources[0].verification_status = SourceVerification.UNVERIFIED
    storage.conn.commit()

    target_run_id = "missing-run" if case == "unknown_run" else run_id
    with pytest.raises(ResearchTopicIntegrityError):
        _finalize(storage, target_run_id, card)
    assert _counts(storage, run_id) == (0, 0, 0)
    assert storage.get_run(run_id).status == RunStatus.RUNNING
    assert storage.get_research_run(run_id).status != ResearchRunStatus.COMPLETE
    storage.close()


def test_idempotency_ignores_source_order_and_rejects_source_topic_and_cost_conflicts(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    run_id, topic = _prepared_staged_run(storage, account)
    first = _finalize(storage, run_id, _card(topic))
    before_state, before_counts = _state(storage, run_id, int(topic.id)), _counts(storage, run_id)

    reordered = first.model_copy(deep=True)
    reordered.sources.reverse()
    repeated = _finalize(storage, run_id, reordered)
    assert repeated.id == first.id
    assert _state(storage, run_id, int(topic.id)) == before_state
    assert _counts(storage, run_id) == before_counts

    source_conflict = first.model_copy(deep=True)
    source_conflict.sources[0].supports_claim = "Different support"
    topic_conflict = first.model_copy(deep=True)
    topic_conflict.topic_id += 1
    for conflicting_card, total_cost in ((source_conflict, 0.123), (topic_conflict, 0.123), (first, 0.124)):
        with pytest.raises(ResearchTopicIntegrityError):
            _finalize(storage, run_id, conflicting_card, total_cost=total_cost)
        assert _state(storage, run_id, int(topic.id)) == before_state
        assert _counts(storage, run_id) == before_counts
    storage.close()


def test_two_sqlite_connections_finalize_two_different_runs_without_false_conflict(settings, account):
    setup = SqliteStorage.open(settings.db_path)
    first_run, first_topic = _prepared_staged_run(setup, account)
    second_run, second_topic = _prepared_staged_run(setup, account)
    setup.close()
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def worker(run_id, topic):
        storage = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            _finalize(storage, run_id, _card(topic))
        except BaseException as exc:
            failures.append(exc)
        finally:
            storage.close()

    threads = [
        threading.Thread(target=worker, args=(first_run, first_topic)),
        threading.Thread(target=worker, args=(second_run, second_topic)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    storage = SqliteStorage.open(settings.db_path)
    assert failures == []
    for run_id, topic in ((first_run, first_topic), (second_run, second_topic)):
        assert _counts(storage, run_id) == (2, 4, 1)
        state = _state(storage, run_id, int(topic.id))
        assert state[0] == ResearchRunStatus.COMPLETE.value
        assert state[4] == RunStatus.SUCCESS.value
        assert state[8] == TopicStatus.USED.value
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE research_card_id=?", (state[1],),
        ).fetchone()[0] == 2
    storage.close()
