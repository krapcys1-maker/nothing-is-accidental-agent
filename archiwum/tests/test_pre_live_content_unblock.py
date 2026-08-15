from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.content.controlled_entrypoint import (
    ControlledArticleAuthority,
    run_controlled_article,
)
from app.content.contracts import WriterLimits
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline
from app.content.writer import (
    ProductionArticleWriter,
)
from app.core.clock import FixedClock
from app.llm.anthropic_client import AnthropicLLMClient, _build_prompt
from app.models import Job, JobKind, Topic, TopicStatus, WorkflowType
from app.policies.policy_engine import PolicyEngine
from app.research.durable_intent import DurableResearchExecutionIntent
from app.scheduler.dispatcher import JobDispatcher, PolicyDeniedError
from app.topics.novelty import (
    EditorialMemoryRecord,
    bounded_history_snapshot,
    find_editorial_duplicate,
)
from tests.c2_fixtures import seed_c2_research
from tests.test_prec5_verified_catalogue_live_root import _activate_article_roles


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)


def _open_paid_flags(storage) -> None:
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test-owner", reason="controlled article test", now=NOW)


def test_production_root_now_supplies_its_own_semantic_reviewer(
    storage, settings, account,
):
    """B3 part B closed this gap: the root composes the production reviewer.

    The pipeline-level fail-closed contract (no reviewer for an ARTICLE means
    ``CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE``) is unchanged and still covered
    where a reviewer can actually be absent; it simply cannot be reached
    through this root any more.
    """
    seeded = seed_c2_research(storage, account)
    _activate_article_roles(storage)
    _open_paid_flags(storage)
    calls: list[object] = []

    def sdk_factory(**kwargs):
        calls.append(("sdk", kwargs))
        return object()

    def caller(*_args):
        raise AssertionError("stop at the writer transport for this assertion")

    outcome = run_controlled_article(
        settings=replace(settings, project_root=ROOT),
        account_id=account.id,
        research_card_id=int(seeded["card_id"]),
        idempotency_key="pre-live-root",
        authority=ControlledArticleAuthority(
            job_id="pre-live-root",
            approval_ref="approval-pre-live-root",
            approved_by="owner",
            approved_at="2026-08-11T09:00:00.000000+00:00",
            expires_at="2026-08-12T09:00:00.000000+00:00",
            cost_ceiling_usd="0.500000",
        ),
        api_key_provider=lambda: "fake-key-at-final-boundary",
        sdk_factory=sdk_factory,
        caller=caller,
        clock=FixedClock(NOW),
    )

    state = storage.get_content_pipeline_state(outcome.job_id)
    # The reviewer is present, so the root no longer stops before the writer;
    # it now stops exactly where this test's fake writer transport refuses.
    assert outcome.worker.detail != "CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE"
    assert state["content"]["reason_code"] != "CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE"
    assert calls, "the writer transport boundary was reached"
    assert "FakeContentWriter" not in inspect.getsource(run_controlled_article)
    assert "ProductionArticleReviewer" in inspect.getsource(run_controlled_article)


def test_ordinary_dispatcher_cannot_enable_paid_content(storage, settings, account):
    seeded = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id="ordinary-paid-block",
        idempotency_key="ordinary-paid-block",
        account_id=account.id,
        research_card_id=int(seeded["card_id"]),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
        prompt_version="controlled_article_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    lease = storage.claim_specific_job(request.job_id, "ordinary", 60, clock=FixedClock(NOW))
    writer = ProductionArticleWriter(
        api_key_provider=lambda: "unused",
        article_limits=WriterLimits(
            max_input_tokens=8000, max_context_tokens=16000,
            max_output_tokens=2048, max_cost_usd=0.5, timeout_seconds=30,
        ),
        sdk_factory=lambda **_kwargs: pytest.fail("SDK boundary must not be reached"),
    )
    dispatcher = JobDispatcher(
        settings=replace(settings, project_root=ROOT),
        storage=storage,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        clock=FixedClock(NOW),
        content_writer=writer,
    )
    with pytest.raises(PolicyDeniedError, match="CONTENT_PAID_PROVIDER_NOT_AUTHORIZED"):
        dispatcher._dispatch_content(lease.job, "ordinary", lambda: None)
    assert writer.caller_calls == 0


def _candidate(title: str, question: str) -> EditorialMemoryRecord:
    return EditorialMemoryRecord(
        "CANDIDATE", -1, -1, None, None, title, question, question, "",
        "CANDIDATE", "",
    )


def test_six_semantic_dedup_counterexamples_use_durable_account_memory(
    storage, account,
):
    seeded = seed_c2_research(
        storage, account, topic_title="Why airline ticket prices change every few hours",
    )
    storage.conn.execute(
        "UPDATE topics SET question=?,status='USED' WHERE id=?",
        (
            "How airline revenue management repeatedly changes ticket prices as demand updates",
            seeded["topic_id"],
        ),
    )
    storage.conn.execute(
        "UPDATE research_cards SET working_thesis=?,thesis=? WHERE id=?",
        (
            "Airline revenue management repeatedly changes ticket prices as demand updates",
            "Airline revenue management repeatedly changes ticket prices as demand updates",
            seeded["card_id"],
        ),
    )
    storage.conn.commit()
    storage.prepare_content_job(ContentPreparationRequest(
        job_id="old-content", idempotency_key="old-content", account_id=account.id,
        research_card_id=int(seeded["card_id"]), content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline", style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    ), clock=FixedClock(NOW))
    storage.conn.execute(
        "UPDATE content_items SET body=? WHERE job_id='old-content'",
        ("Airline revenue management repeatedly changes ticket prices as demand updates.",),
    )
    storage.conn.commit()
    memory = storage.list_editorial_novelty_memory(account.id)
    content_only = tuple(row for row in memory if row.source_kind == "CONTENT")

    probes = {
        "identical": find_editorial_duplicate(_candidate(
            "Why airline ticket prices change every few hours",
            "How airline revenue management repeatedly changes ticket prices as demand updates",
        ), memory),
        "strong_paraphrase": find_editorial_duplicate(_candidate(
            "The system that makes airfares move throughout the day",
            "How airline revenue management repeatedly changes ticket prices",
        ), memory),
        "different_title_same_thesis": find_editorial_duplicate(_candidate(
            "Your seat has no stable price",
            "Airline revenue management repeatedly changes ticket prices as demand updates",
        ), memory),
        "same_area_new_thesis": find_editorial_duplicate(_candidate(
            "Why airlines charge for checked bags",
            "How baggage unbundling changes airline incentives and advertised base fares",
        ), memory),
        "old_used_same_thesis": find_editorial_duplicate(_candidate(
            "Demand updates keep changing the fare you see",
            "Airline revenue management repeatedly changes ticket prices as demand updates",
        ), tuple(row for row in memory if row.status == "USED")),
        "prior_content_same_thesis": find_editorial_duplicate(_candidate(
            "A renamed version of the airfare mechanism",
            "Airline revenue management repeatedly changes ticket prices as demand updates",
        ), content_only),
    }
    assert probes["same_area_new_thesis"] is None
    for name, match in probes.items():
        if name != "same_area_new_thesis":
            assert match is not None, name


def test_topic_prompt_history_is_bounded_and_never_contains_article_body(
    storage, account, monkeypatch,
):
    seeded = seed_c2_research(storage, account, topic_title="Historical angle")
    storage.prepare_content_job(ContentPreparationRequest(
        job_id="history-content", idempotency_key="history-content",
        account_id=account.id, research_card_id=int(seeded["card_id"]),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline", style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    ), clock=FixedClock(NOW))
    storage.conn.execute(
        "UPDATE content_items SET body='FULL ARTICLE SECRET BODY MUST NOT ENTER PROMPT' "
        "WHERE job_id='history-content'"
    )
    storage.conn.commit()
    snapshot = bounded_history_snapshot(storage.list_editorial_novelty_memory(account.id))
    prompt = _build_prompt(account, 5, snapshot)
    assert len(snapshot) <= 40
    assert "Historical angle" in prompt
    assert "Fees hide the mechanism" in prompt
    assert "FULL ARTICLE SECRET BODY" not in prompt
    assert set(snapshot[0]) == {"title", "question", "central_thesis", "status"}

    final_request: dict[str, object] = {}

    class FakeMessages:
        @staticmethod
        def create(**kwargs):
            final_request.update(kwargs)
            return SimpleNamespace(
                model="topic-model",
                id="fake-topic-history",
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text='{"topics": []}')],
                usage=SimpleNamespace(
                    input_tokens=10, output_tokens=2,
                    cache_read_input_tokens=0, cache_creation_input_tokens=0,
                    inference_geo="global", service_tier="standard",
                ),
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(
        Anthropic=FakeAnthropic,
        APIError=RuntimeError,
    ))
    client = AnthropicLLMClient("offline-key", "topic-model")
    client.set_editorial_history(snapshot)
    monkeypatch.setattr(
        client, "_assert_active_durable_provider_attempt", lambda: "request-id",
    )
    client._default_caller(account, 5)
    final_prompt = final_request["messages"][0]["content"]
    assert "Historical angle" in final_prompt
    assert "Fees hide the mechanism" in final_prompt
    assert "FULL ARTICLE SECRET BODY" not in final_prompt


def test_content_novelty_gate_runs_before_writer(storage, settings, account):
    first = seed_c2_research(storage, account, topic_title="Original fee mechanism")
    storage.prepare_content_job(ContentPreparationRequest(
        job_id="prior-version", idempotency_key="prior-version", account_id=account.id,
        research_card_id=int(first["card_id"]), content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline", style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    ), clock=FixedClock(NOW))
    storage.conn.execute(
        "UPDATE content_items SET body='Fees hide the mechanism behind the price.' "
        "WHERE job_id='prior-version'"
    )
    storage.conn.commit()
    second = seed_c2_research(storage, account, topic_title="A renamed fee story")
    _activate_article_roles(storage)
    request = ContentPreparationRequest(
        job_id="duplicate-version", idempotency_key="duplicate-version",
        account_id=account.id, research_card_id=int(second["card_id"]),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
        prompt_version="controlled_article_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    lease = storage.claim_specific_job(request.job_id, "novelty", 60, clock=FixedClock(NOW))

    class CountingWriter:
        call_mode = __import__(
            "app.content.contracts", fromlist=["WriterCallMode"]
        ).WriterCallMode.CONTROLLED_PROVIDER
        requires_editorial_novelty = True
        calls = 0

        def limits_for(self, _content_type):
            return WriterLimits(
                max_input_tokens=8000, max_context_tokens=16000,
                max_output_tokens=2048, max_cost_usd=0, timeout_seconds=1,
            )

        def preflight(self, _request):
            return None

        def write(self, _request):
            self.calls += 1
            raise AssertionError("duplicate reached writer")

    writer = CountingWriter()

    class NeverReviewer:
        reviewer_version = "never-called-semantic-reviewer"

        def review(self, **_kwargs):
            raise AssertionError("duplicate reached reviewer")

    summary = run_offline_content_pipeline(
        lease.job, storage=storage, clock=FixedClock(NOW), lease_owner="novelty",
        project_root=ROOT, policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=writer, claim_reviewer=NeverReviewer(),
        lease_seconds=0,
    )
    assert summary.block_code == "EDITORIAL_NOVELTY_DUPLICATE"
    assert writer.calls == 0


def test_research_novelty_gate_runs_before_real_runner(storage, settings, account):
    seeded = seed_c2_research(storage, account, topic_title="Original fee mechanism")
    storage.conn.execute(
        "UPDATE topics SET question=?,status='USED' WHERE id=?",
        ("Fees hide the mechanism", seeded["topic_id"]),
    )
    candidate = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="The renamed mechanism behind the final price",
        question="How fees hide the mechanism behind the final price",
        status=TopicStatus.SELECTED,
    ))
    assert candidate.id is not None
    intent = DurableResearchExecutionIntent.from_settings(
        settings=settings,
        account_id=account.id,
        topic_id=candidate.id,
        cap_usd="0.100000",
        max_web_searches=0,
        question=candidate.question,
        niche=account.niche,
        max_tokens=3000,
    )
    job = storage.enqueue_job(Job(
        id="duplicate-before-research",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key="duplicate-before-research",
        topic_id=candidate.id,
        payload={
            "account_id": account.id,
            "topic_id": candidate.id,
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
        max_attempts=1,
    ))
    lease = storage.claim_specific_job(job.id, "research-novelty", 60, clock=FixedClock(NOW))
    calls = 0

    def real_runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("duplicate reached paid research runner")

    _open_paid_flags(storage)
    dispatcher = JobDispatcher(
        settings=settings,
        storage=storage,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        clock=FixedClock(NOW),
        research_real=real_runner,
        allow_real_research=True,
    )
    with pytest.raises(PolicyDeniedError) as error:
        dispatcher.dispatch(
            lease.job,
            lease_owner="research-novelty",
            heartbeat=lambda: None,
        )
    assert error.value.decision.code == "EDITORIAL_NOVELTY_DUPLICATE"
    assert calls == 0
