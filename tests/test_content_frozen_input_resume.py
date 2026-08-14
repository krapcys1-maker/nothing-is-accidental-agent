"""Schema 0043 against the 0039 review-resume authority.

0039 lets an owner reopen a FAILED content item (FAILED -> RUNNING under an
ACTIVE resume session).  0043 supersedes the frozen input the moment that item
terminalises, which would otherwise open a double-pay hole: a retry takes the
live slot, the owner then resumes the old item, and two live content items sit
on one paid Research Card.  The revive trigger re-takes the slot, and if a
retry already holds it the whole resume fails closed on the partial unique
index before any job, run or content run is mutated.

Every transport here is an in-memory fake of the installed SDK surface; no
network, provider request or production database is touched.
"""
from __future__ import annotations

from dataclasses import replace
import json
import sqlite3

import pytest

from app.content.foundation import (
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.review_only import run_controlled_article_review_only
from app.core.clock import FixedClock
from app.models import JobExecutionContext, JobKind, WorkflowType
from tests.test_b3_production_reviewer import NOW
from tests.test_pr46_review_only_resume import (
    _SdkFactory,
    _authority,
    _failed_article,
)


def _frozen(storage, content_id):
    return storage.conn.execute(
        "SELECT * FROM content_frozen_inputs WHERE content_id=?", (content_id,),
    ).fetchone()


def _retry_request(storage, content_id, *, job: str) -> ContentPreparationRequest:
    """A second preparation whose frozen input hashes to the same value."""
    row = _frozen(storage, content_id)
    return ContentPreparationRequest(
        job_id=job,
        idempotency_key=job,
        account_id=row["account_id"],
        research_card_id=int(row["research_card_id"]),
        content_type=ContentType(row["content_type"]),
        input_schema_version=row["input_schema_version"],
        output_schema_version=row["output_schema_version"],
        prompt_version=row["prompt_version"],
        style_guide_version=row["style_guide_version"],
        article_brief_placeholder=json.loads(
            row["article_brief_placeholder_json"]
        ),
    )


def test_failed_article_supersedes_and_a_review_resume_revives_the_slot(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-0043-revive")
    content_id = int(state["content"]["id"])
    assert state["content"]["status"] == "FAILED"
    stamped = _frozen(storage, content_id)["superseded_at"]
    assert stamped is not None

    result = run_controlled_article_review_only(
        settings=replace(settings, db_path=settings.db_path),
        authority=_authority(state, suffix="revive"),
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_SdkFactory(),
        clock=FixedClock(NOW),
    )
    assert result.final_status is ContentStatus.PENDING_APPROVAL
    # The resumed item took the live slot back; the article it produced is the
    # one that may be published, so its frozen input must block duplicates.
    assert _frozen(storage, content_id)["superseded_at"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_sessions WHERE content_id=?",
        (content_id,),
    ).fetchone()[0] == 1


def test_a_retry_that_holds_the_live_slot_fails_the_resume_closed(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-0043-conflict")
    content_id = int(state["content"]["id"])
    assert _frozen(storage, content_id)["superseded_at"] is not None

    retry_job = "pr46-0043-retry"
    retry = storage.prepare_content_job(
        _retry_request(storage, content_id, job=retry_job),
        clock=FixedClock(NOW),
    )
    assert retry.frozen_input.input_sha256 == _frozen(
        storage, content_id,
    )["input_sha256"]
    assert retry.frozen_input.superseded_at is None
    # Take the retry all the way to its own success, so the live slot is held
    # by a finished article and no other job is active.
    lease = storage.claim_specific_job(
        retry_job, "worker-retry", 600, clock=FixedClock(NOW),
    )
    assert lease is not None
    storage.initialize_content_run_for_job(
        retry_job, "worker-retry", lease.job.execution_generation,
        "content-run-retry", clock=FixedClock(NOW),
    )
    storage.transition_content_execution(
        JobExecutionContext(
            job_id=retry_job,
            lease_owner="worker-retry",
            run_id="content-run-retry",
            clock=FixedClock(NOW),
            fence_token=lease.job.execution_generation,
            kind=JobKind.CONTENT,
            workflow=WorkflowType.ARTICLE,
        ),
        ContentStatus.PENDING_APPROVAL,
        final_result={"audits": ["FACT", "STYLE", "GROWTH"]},
        score=0.9,
    )
    assert _frozen(storage, retry.content.id)["superseded_at"] is None

    before = {
        table: storage.conn.execute(
            f"SELECT count(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "jobs", "runs", "content_runs", "content_items",
            "content_review_resume_sessions",
        )
    }
    job_status = storage.conn.execute(
        "SELECT status,execution_generation FROM jobs WHERE id=?",
        (state["job"]["id"],),
    ).fetchone()
    factory = _SdkFactory()
    with pytest.raises(sqlite3.IntegrityError):
        run_controlled_article_review_only(
            settings=replace(settings, db_path=settings.db_path),
            authority=_authority(state, suffix="conflict"),
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=factory,
            clock=FixedClock(NOW),
        )
    # The refusal lands on the session INSERT, so no job, run, content run,
    # content item or session was mutated and the retry keeps the live slot.
    assert {
        table: storage.conn.execute(
            f"SELECT count(*) FROM {table}"
        ).fetchone()[0]
        for table in before
    } == before
    assert dict(storage.conn.execute(
        "SELECT status,execution_generation FROM jobs WHERE id=?",
        (state["job"]["id"],),
    ).fetchone()) == dict(job_status)
    assert _frozen(storage, content_id)["superseded_at"] is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM content_frozen_inputs WHERE superseded_at IS NULL"
    ).fetchone()[0] == 1
    # Known and deliberate cost boundary: run_controlled_article_review_only
    # performs reviewer #1 BEFORE begin_content_review_resume_session, so the
    # conflict is detected only after that one settled review.  The operator
    # path normally never reaches here, because the same entrypoint refuses
    # earlier with REVIEW_ONLY_ACTIVE_WORK_PRESENT while the retry job is still
    # active; this test forces the narrow window where the retry has already
    # finished.  Nothing beyond that first review is spent, and the lifecycle
    # stays exactly where it was.
    assert len(factory.messages.stream_calls) == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_executions "
        "WHERE review_no=1 AND outcome='SUCCESS'"
    ).fetchone()[0] == 1
