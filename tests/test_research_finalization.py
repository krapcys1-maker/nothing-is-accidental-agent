"""Trwałe regresje atomowej finalizacji researchu (Etap 0 / Task 4)."""
from __future__ import annotations

import pytest

from app.core.ids import new_run_id
from app.models import (
    ResearchCard,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import ResearchTopicIntegrityError
from app.storage.repositories import SqliteStorage
from app.workflows.research.pipeline import (
    CompletedResearchExistsError,
    ensure_topic_can_start_research,
)


def _topic(storage, account, title: str = "Topic") -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title=title, question=f"Why {title}?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _card(storage, topic: Topic) -> ResearchCard:
    return storage.add_research_card(ResearchCard(
        topic_id=int(topic.id), question=topic.question or "Question", working_thesis="Thesis",
    ))


def _pending_run(storage, account, topic: Topic, flow: ResearchFlow) -> str:
    run_id = new_run_id()
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id), flow=flow,
        status={
            ResearchFlow.SINGLE: ResearchRunStatus.PENDING,
            ResearchFlow.TWO_STAGE: ResearchRunStatus.SOURCE_COLLECTED,
            ResearchFlow.STAGED: ResearchRunStatus.SYNTHESIS_PENDING,
        }[flow],
    ))
    return run_id


def _reopen(settings, storage) -> SqliteStorage:
    storage.close()
    return SqliteStorage.open(settings.db_path)


def _final_state(storage, run_id: str, topic_id: int) -> tuple:
    return tuple(storage.conn.execute(
        "SELECT rr.status, rr.research_card_id, rr.total_cost_usd, rr.error, "
        "rr.stage_b_completed_at, rr.updated_at, r.status, r.cost_usd, r.error, "
        "r.finished_at, t.status FROM research_runs rr JOIN runs r ON r.id=rr.id "
        "JOIN topics t ON t.id=rr.topic_id WHERE rr.id=? AND t.id=?",
        (run_id, topic_id),
    ).fetchone())


def _table_counts(storage) -> dict[str, int]:
    return {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage", "research_cards")
    }


@pytest.mark.parametrize(
    ("flow", "stage_b_completed"),
    [
        (ResearchFlow.SINGLE, False),
        (ResearchFlow.TWO_STAGE, True),
        (ResearchFlow.STAGED, True),
    ],
)
def test_finalization_is_durable_and_atomic_for_each_flow(
        settings, account, flow, stage_b_completed):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, flow.value)
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, flow)

    storage.finalize_research_success(
        run_id, int(card.id), 0.123, stage_b_completed=stage_b_completed,
        terminal_run_status=RunStatus.SUCCESS,
    )
    storage = _reopen(settings, storage)

    research_run = storage.get_research_run(run_id)
    run = storage.get_run(run_id)
    persisted_topic = next(t for t in storage.list_topics(account.id) if t.id == topic.id)
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.research_card_id == card.id
    assert (research_run.stage_b_completed_at is not None) is stage_b_completed
    assert run.status == RunStatus.SUCCESS
    assert run.cost_usd == pytest.approx(0.123)
    assert persisted_topic.status == TopicStatus.USED
    assert storage.has_valid_completed_research_card_for_topic(account.id, int(topic.id))
    storage.close()


@pytest.mark.parametrize(
    ("flow", "stage_b_completed"),
    [
        (ResearchFlow.SINGLE, False),
        (ResearchFlow.TWO_STAGE, True),
        (ResearchFlow.STAGED, True),
    ],
)
def test_identical_repeated_finalization_is_durable_no_op(
        settings, account, flow, stage_b_completed):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"repeat-{flow.value}")
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, flow)
    kwargs = {
        "stage_b_completed": stage_b_completed,
        "terminal_run_status": RunStatus.SUCCESS,
    }
    storage.finalize_research_success(run_id, int(card.id), 0.1, **kwargs)

    storage.conn.execute(
        "UPDATE research_runs SET updated_at=?, stage_b_completed_at=? WHERE id=?",
        ("2002-02-02 02:02:02", "2001-01-01 01:01:01" if stage_b_completed else None,
         run_id),
    )
    storage.conn.execute(
        "UPDATE runs SET finished_at=? WHERE id=?", ("2003-03-03 03:03:03", run_id),
    )
    storage.conn.commit()
    before = _final_state(storage, run_id, int(topic.id))
    counts_before = _table_counts(storage)

    storage.finalize_research_success(run_id, int(card.id), 0.1, **kwargs)
    storage = _reopen(settings, storage)

    assert _final_state(storage, run_id, int(topic.id)) == before
    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize("conflict", ["card", "cost", "terminal_status"])
def test_conflicting_repeated_finalization_is_rejected_without_mutation(
        settings, account, conflict):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"conflict-{conflict}")
    card = _card(storage, topic)
    other_card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.STAGED)
    storage.finalize_research_success(
        run_id, int(card.id), 0.1, stage_b_completed=True,
        terminal_run_status=RunStatus.SUCCESS,
    )
    before = _final_state(storage, run_id, int(topic.id))
    counts_before = _table_counts(storage)
    requested_card = int(other_card.id) if conflict == "card" else int(card.id)
    requested_cost = 0.9 if conflict == "cost" else 0.1
    requested_status = RunStatus.DRY_RUN if conflict == "terminal_status" else RunStatus.SUCCESS

    with pytest.raises(ResearchTopicIntegrityError, match="Sprzeczna ponowna finalizacja"):
        storage.finalize_research_success(
            run_id, requested_card, requested_cost, stage_b_completed=True,
            terminal_run_status=requested_status,
        )
    storage = _reopen(settings, storage)

    assert _final_state(storage, run_id, int(topic.id)) == before
    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize(
    ("flow", "initial_stage_b", "conflicting_stage_b"),
    [
        (ResearchFlow.SINGLE, False, True),
        (ResearchFlow.TWO_STAGE, True, False),
    ],
)
def test_repeated_finalization_with_conflicting_stage_b_semantics_is_rejected(
        settings, account, flow, initial_stage_b, conflicting_stage_b):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"stage-conflict-{flow.value}")
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, flow)
    storage.finalize_research_success(
        run_id, int(card.id), 0.1, stage_b_completed=initial_stage_b,
        terminal_run_status=RunStatus.SUCCESS,
    )
    before = _final_state(storage, run_id, int(topic.id))
    counts_before = _table_counts(storage)

    with pytest.raises(ResearchTopicIntegrityError, match="Niezgodna semantyka etapu B"):
        storage.finalize_research_success(
            run_id, int(card.id), 0.1, stage_b_completed=conflicting_stage_b,
            terminal_run_status=RunStatus.SUCCESS,
        )
    storage = _reopen(settings, storage)

    assert _final_state(storage, run_id, int(topic.id)) == before
    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize(
    ("flow", "stage_b_completed", "corrupt_timestamp"),
    [
        (ResearchFlow.SINGLE, False, "2001-01-01 01:01:01"),
        (ResearchFlow.STAGED, True, None),
    ],
)
def test_complete_with_stage_b_timestamp_inconsistent_with_flow_fails_closed(
        settings, account, flow, stage_b_completed, corrupt_timestamp):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"stage-corrupt-{flow.value}")
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, flow)
    storage.finalize_research_success(
        run_id, int(card.id), 0.1, stage_b_completed=stage_b_completed,
        terminal_run_status=RunStatus.SUCCESS,
    )
    storage.conn.execute(
        "UPDATE research_runs SET stage_b_completed_at=? WHERE id=?",
        (corrupt_timestamp, run_id),
    )
    storage.conn.commit()
    before = _final_state(storage, run_id, int(topic.id))
    counts_before = _table_counts(storage)

    with pytest.raises(ResearchTopicIntegrityError, match="Sprzeczna ponowna finalizacja"):
        storage.finalize_research_success(
            run_id, int(card.id), 0.1, stage_b_completed=stage_b_completed,
            terminal_run_status=RunStatus.SUCCESS,
        )
    storage = _reopen(settings, storage)

    assert _final_state(storage, run_id, int(topic.id)) == before
    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize("other_account", [False, True])
def test_repeated_finalization_with_card_from_other_topic_or_account_is_rejected(
        settings, account, other_account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, "completed-target")
    original_card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.STAGED)
    storage.finalize_research_success(
        run_id, int(original_card.id), 0.1, stage_b_completed=True,
        terminal_run_status=RunStatus.SUCCESS,
    )
    card_account = account
    if other_account:
        card_account = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    wrong_topic = _topic(storage, card_account, f"wrong-repeat-{other_account}")
    wrong_card = _card(storage, wrong_topic)
    before = _final_state(storage, run_id, int(topic.id))
    counts_before = _table_counts(storage)

    with pytest.raises(ResearchTopicIntegrityError, match="nie należy"):
        storage.finalize_research_success(
            run_id, int(wrong_card.id), 0.1, stage_b_completed=True,
            terminal_run_status=RunStatus.SUCCESS,
        )
    storage = _reopen(settings, storage)

    assert _final_state(storage, run_id, int(topic.id)) == before
    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize("corruption", ["missing_card", "wrong_card", "run_status", "topic_status"])
def test_corrupt_complete_is_not_accepted_as_idempotent_repetition(
        settings, account, corruption):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"corrupt-{corruption}")
    card = _card(storage, topic)
    wrong_topic = _topic(storage, account, f"wrong-{corruption}")
    wrong_card = _card(storage, wrong_topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.SINGLE)
    storage.finalize_research_success(
        run_id, int(card.id), 0.1, stage_b_completed=False,
        terminal_run_status=RunStatus.SUCCESS,
    )
    if corruption == "missing_card":
        storage.conn.execute("UPDATE research_runs SET research_card_id=NULL WHERE id=?", (run_id,))
    elif corruption == "wrong_card":
        storage.conn.execute(
            "UPDATE research_runs SET research_card_id=? WHERE id=?", (wrong_card.id, run_id),
        )
    elif corruption == "run_status":
        storage.conn.execute("UPDATE runs SET status=? WHERE id=?", (RunStatus.RUNNING.value, run_id))
    else:
        storage.conn.execute(
            "UPDATE topics SET status=? WHERE id=?", (TopicStatus.SELECTED.value, topic.id),
        )
    storage.conn.commit()
    before = _final_state(storage, run_id, int(topic.id))

    with pytest.raises(ResearchTopicIntegrityError):
        storage.finalize_research_success(
            run_id, int(card.id), 0.1, stage_b_completed=False,
            terminal_run_status=RunStatus.SUCCESS,
        )
    storage = _reopen(settings, storage)
    assert _final_state(storage, run_id, int(topic.id)) == before
    storage.close()


@pytest.mark.parametrize("other_account", [False, True])
def test_wrong_card_rolls_back_every_final_status_after_reopen(
        settings, account, other_account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, "target")
    run_id = _pending_run(storage, account, topic, ResearchFlow.TWO_STAGE)
    card_account = account
    if other_account:
        card_account = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    wrong_topic = _topic(storage, card_account, "wrong")
    wrong_card = _card(storage, wrong_topic)

    with pytest.raises(ResearchTopicIntegrityError, match="nie należy"):
        storage.finalize_research_success(
            run_id, int(wrong_card.id), 0.123, stage_b_completed=True,
            terminal_run_status=RunStatus.SUCCESS,
        )

    storage = _reopen(settings, storage)
    research_run = storage.get_research_run(run_id)
    run = storage.get_run(run_id)
    persisted_topic = next(t for t in storage.list_topics(account.id) if t.id == topic.id)
    assert research_run.status == ResearchRunStatus.SOURCE_COLLECTED
    assert research_run.research_card_id is None
    assert run.status == RunStatus.RUNNING
    assert persisted_topic.status == TopicStatus.SELECTED
    storage.close()


@pytest.mark.parametrize("target", ["topics", "runs"])
def test_finalization_rolls_back_when_any_terminal_update_fails_after_reopen(
        settings, account, target):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.STAGED)
    if target == "topics":
        storage.conn.execute(
            "CREATE TRIGGER fail_used BEFORE UPDATE OF status ON topics "
            "WHEN NEW.status='USED' BEGIN SELECT RAISE(ABORT, 'forced topic failure'); END"
        )
    else:
        storage.conn.execute(
            "CREATE TRIGGER fail_success BEFORE UPDATE OF status ON runs "
            "WHEN NEW.status='SUCCESS' BEGIN SELECT RAISE(ABORT, 'forced run failure'); END"
        )
    storage.conn.commit()

    with pytest.raises(Exception, match="forced"):
        storage.finalize_research_success(
            run_id, int(card.id), 0.123, stage_b_completed=True,
            terminal_run_status=RunStatus.SUCCESS,
        )

    storage = _reopen(settings, storage)
    research_run = storage.get_research_run(run_id)
    run = storage.get_run(run_id)
    persisted_topic = next(t for t in storage.list_topics(account.id) if t.id == topic.id)
    assert research_run.status == ResearchRunStatus.SYNTHESIS_PENDING
    assert research_run.research_card_id is None
    assert run.status == RunStatus.RUNNING
    assert persisted_topic.status == TopicStatus.SELECTED
    storage.close()


def test_guard_fails_closed_for_corrupt_complete_card_relation(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, "target")
    wrong_topic = _topic(storage, account, "wrong")
    wrong_card = _card(storage, wrong_topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.SINGLE)
    storage.conn.execute(
        "UPDATE research_runs SET status=?, research_card_id=? WHERE id=?",
        (ResearchRunStatus.COMPLETE.value, wrong_card.id, run_id),
    )
    storage.conn.commit()

    with pytest.raises(ResearchTopicIntegrityError, match="niepoprawną relację"):
        storage.has_valid_completed_research_card_for_topic(account.id, int(topic.id))
    storage.close()


def test_guard_fails_closed_for_used_topic_without_valid_completed_card(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    storage.conn.execute("UPDATE topics SET status=? WHERE id=?", (TopicStatus.USED.value, topic.id))
    storage.conn.commit()

    with pytest.raises(ResearchTopicIntegrityError, match="USED bez poprawnej"):
        storage.has_valid_completed_research_card_for_topic(account.id, int(topic.id))
    storage.close()


def test_guard_rejects_topic_from_other_account(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    storage.ensure_account(other)

    with pytest.raises(ResearchTopicIntegrityError, match="nie należy"):
        ensure_topic_can_start_research(storage, other, topic, force_re_research=False)
    storage.close()


def test_guard_fails_closed_for_complete_run_with_mismatched_run_account(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account)
    card = _card(storage, topic)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    storage.ensure_account(other)
    run_id = new_run_id()
    storage.create_run(Run(
        id=run_id, account_id=other.id, workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING,
    ))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id), flow=ResearchFlow.SINGLE,
    ))
    storage.conn.execute(
        "UPDATE research_runs SET status=?, research_card_id=? WHERE id=?",
        (ResearchRunStatus.COMPLETE.value, card.id, run_id),
    )
    storage.conn.commit()

    with pytest.raises(ResearchTopicIntegrityError, match="niepoprawną relację"):
        storage.has_valid_completed_research_card_for_topic(account.id, int(topic.id))
    storage.close()


def test_selected_topic_with_valid_complete_run_is_still_blocked_without_force(settings, account):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, "selected-complete")
    card = _card(storage, topic)
    run_id = _pending_run(storage, account, topic, ResearchFlow.SINGLE)
    storage.finalize_research_success(
        run_id, int(card.id), 0.1, stage_b_completed=False,
        terminal_run_status=RunStatus.SUCCESS,
    )
    storage.conn.execute(
        "UPDATE topics SET status=? WHERE id=?", (TopicStatus.SELECTED.value, topic.id),
    )
    storage.conn.commit()
    counts_before = _table_counts(storage)

    with pytest.raises(CompletedResearchExistsError, match="--force-re-research"):
        ensure_topic_can_start_research(storage, account, topic, force_re_research=False)

    assert _table_counts(storage) == counts_before
    storage.close()


@pytest.mark.parametrize("complete_first", [False, True])
def test_complete_run_blocks_despite_failed_and_partial_history_order(
        settings, account, complete_first):
    storage = SqliteStorage.open(settings.db_path)
    topic = _topic(storage, account, f"history-{complete_first}")

    def add_history(status: ResearchRunStatus) -> None:
        history_id = _pending_run(storage, account, topic, ResearchFlow.TWO_STAGE)
        storage.conn.execute(
            "UPDATE research_runs SET status=? WHERE id=?", (status.value, history_id),
        )
        storage.conn.execute(
            "UPDATE runs SET status=? WHERE id=?", (RunStatus.FAILED.value, history_id),
        )
        storage.conn.commit()

    if not complete_first:
        add_history(ResearchRunStatus.FAILED)
        add_history(ResearchRunStatus.PARTIAL)
    card = _card(storage, topic)
    complete_id = _pending_run(storage, account, topic, ResearchFlow.SINGLE)
    storage.finalize_research_success(
        complete_id, int(card.id), 0.1, stage_b_completed=False,
        terminal_run_status=RunStatus.SUCCESS,
    )
    if complete_first:
        add_history(ResearchRunStatus.FAILED)
        add_history(ResearchRunStatus.PARTIAL)

    assert storage.has_valid_completed_research_card_for_topic(account.id, int(topic.id))
    with pytest.raises(CompletedResearchExistsError):
        ensure_topic_can_start_research(storage, account, topic, force_re_research=False)
    storage.close()
