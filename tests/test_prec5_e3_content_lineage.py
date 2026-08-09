"""PRE-C5: the E3 -> CONTENT gap, paid-usage terminalization and CONTENT lease.

All execution is offline on temporary SQLite databases: a fake evidence caller,
a fake writer, synthetic usage and cost.  No network, no SDK, no real provider
and no production database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app.content.contracts import (
    WriterCallMode,
    WriterFailure,
    WriterFailureKind,
    WriterLimits,
    WriterSuccess,
    WriterUsage,
)
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline as _run_offline_content_pipeline
from app.content.style_examples import (
    default_style_corpus_path,
    load_article_style_examples,
)
from app.content.writer import FakeContentWriter
from app.core.clock import FixedClock
from app.models import (
    JobExecutionContext,
    JobKind,
    JobStatus,
    ProviderAttemptStatus,
    SourceVerification,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.fetch import FetchedDocument
from app.ports.storage import StaleJobExecutionError
from app.scheduler.worker import WorkerIterationStatus
from tests.claim_accounting_fakes import FakeClaimAccountingReviewer
from tests.test_e3_evidence_research import (
    NOW as E3_NOW,
    _approve,
    _evidence_payload,
    _install_fake_client,
    _job,
    _open_flags,
    _pricing_profile,
    _real_settings,
    _topic,
    _worker,
    _FakeEvidenceCaller,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = E3_NOW


def run_offline_content_pipeline(*args, **kwargs):
    kwargs.setdefault("claim_reviewer", FakeClaimAccountingReviewer())
    return _run_offline_content_pipeline(*args, **kwargs)

CLAIM = "Gate assignment follows contractual priority."
EXCERPT = "gate assignment follows contractual priority"
BODIES = (
    "The regulator filing states that gate assignment follows contractual "
    "priority agreed with each carrier before the season opens.",
    "Trade reporting confirms that gate assignment follows contractual "
    "priority, with pier access negotiated years in advance.",
    "An academic review records that gate assignment follows contractual "
    "priority rather than passenger convenience at large hubs.",
)
URLS = (
    "https://regulator.example/filing",
    "https://press.example/report",
    "https://journal.example/paper",
)


def _seed_corpus(storage, account):
    storage.ensure_account(account)
    retrievals = []
    for url, body in zip(URLS, BODIES):
        retrievals.append(
            storage.record_evidence_retrieval(
                FetchedDocument(
                    requested_url=url, final_url=url, fetched_at=NOW,
                    http_status=200, content_type="text/plain; charset=utf-8",
                    body=body.encode("utf-8"), error=None,
                ),
                account_id=account.id,
                now=NOW,
            )
        )
    return retrievals


def _proceed_response(_url=None):
    return json.dumps({
        "question": "Who decides the gate?",
        "working_thesis": "Contracts decide the gate.",
        "main_mechanism": "Carrier agreements allocate pier access.",
        "confirmed_claims": [CLAIM],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "Weather still overrides contracts.",
        "citable_numbers": [],
        "visual_idea": "A pier map.",
        "confidence_score": 0.92,
        "source_quality_score": 0.9,
        "sources": [
            {
                "url": url,
                "title": f"Source {index}",
                "author_or_org": "Example Org",
                "published_at": None,
                "source_type": "PRIMARY" if index == 0 else "SECONDARY",
                "supports_claim": CLAIM,
                "supporting_excerpt": EXCERPT,
            }
            for index, url in enumerate(URLS)
        ],
    })


def _card_id(storage, job):
    """The run is created by the worker, so read the persisted relation."""
    run_id = storage.get_job(job.id).run_id
    row = storage.conn.execute(
        "SELECT research_card_id FROM research_runs WHERE id=?", (run_id,),
    ).fetchone()
    return None if row is None else row["research_card_id"]


def _run_e3(monkeypatch, settings, storage, account, *, key):
    real_settings = _real_settings(settings)
    profile = _pricing_profile(real_settings)
    topic = _topic(storage, account, key)
    retrievals = _seed_corpus(storage, account)
    payload, _ = _evidence_payload(
        real_settings, account, topic, retrievals, cap=1.0,
        pricing_profile=profile,
    )
    job = storage.enqueue_job(_job(account, topic, key, payload))
    _open_flags(storage)
    _approve(storage, job.id, account)
    _install_fake_client(monkeypatch, _FakeEvidenceCaller(_proceed_response()))
    result = _worker(real_settings, storage).run_once()
    return real_settings, topic, job, result


# ---------------------------------------------------------------------------
# PRE5-MAJ-03 — a correct E3 PROCEED now produces the lineage CONTENT needs
# ---------------------------------------------------------------------------

def test_e3_proceed_writes_authoritative_lineage(
    monkeypatch, settings, storage, account,
):
    _, topic, job, result = _run_e3(
        monkeypatch, settings, storage, account, key="lineage",
    )
    assert result.status is WorkerIterationStatus.DONE

    card_id = _card_id(storage, job)
    assert card_id is not None
    card = storage.get_research_card(int(card_id))
    assert card.publication_recommendation.value == "PROCEED"
    assert len({source.url for source in card.sources}) == 3
    assert all(
        source.verification_status is SourceVerification.VERIFIED
        for source in card.sources
    )

    lineage = storage.conn.execute(
        "SELECT * FROM evidence_source_lineage WHERE research_card_id=? "
        "ORDER BY confirmed_claim_ordinal, source_id",
        (int(card_id),),
    ).fetchall()
    assert len(lineage) == 3
    for row in lineage:
        assert row["confirmed_claim_id"] == (
            f"research-card:{int(card_id)}:confirmed-claim:0"
        )
        assert row["research_job_id"] == job.id
        assert row["topic_id"] == int(topic.id)
        assert len(row["lineage_fingerprint"]) == 64
    # Distinct retrievals, excerpts and candidates: one retrieval, one source.
    assert len({row["retrieval_id"] for row in lineage}) == 3
    assert len({row["excerpt_id"] for row in lineage}) == 3
    assert len({row["candidate_id"] for row in lineage}) == 3


def test_e3_proceed_reaches_prepare_content_job_end_to_end(
    monkeypatch, settings, storage, account,
):
    """The exact gap PRE5-MAJ-03 described: PROCEED -> lineage -> CONTENT."""
    _, _, job, result = _run_e3(
        monkeypatch, settings, storage, account, key="to-content",
    )
    assert result.status is WorkerIterationStatus.DONE
    card_id = int(_card_id(storage, job))

    request = ContentPreparationRequest(
        job_id="prec5-content-from-e3",
        idempotency_key="prec5-content-from-e3",
        account_id=account.id,
        research_card_id=card_id,
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    prepared = storage.prepare_content_job(request, clock=FixedClock(NOW))
    frozen = prepared.frozen_input
    assert len(frozen.evidence_items) == 3
    assert {item.confirmed_claim_id for item in frozen.evidence_items} == {
        f"research-card:{card_id}:confirmed-claim:0"
    }
    assert {item.claim_text for item in frozen.evidence_items} == {CLAIM}


def test_full_offline_chain_from_evidence_to_content_decision(
    monkeypatch, settings, storage, account,
):
    """3 admitted retrievals -> card -> lineage -> content -> C4 -> terminal."""
    _, _, job, result = _run_e3(
        monkeypatch, settings, storage, account, key="full-chain",
    )
    assert result.status is WorkerIterationStatus.DONE
    card_id = int(_card_id(storage, job))

    request = ContentPreparationRequest(
        job_id="prec5-full-chain",
        idempotency_key="prec5-full-chain",
        account_id=account.id,
        research_card_id=card_id,
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = "prec5-full-chain-owner"
    lease = storage.claim_specific_job(
        request.job_id, owner, 120, clock=FixedClock(NOW),
    )
    assert lease is not None
    writer = FakeContentWriter()
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=writer,
    )

    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.cost_usd == 0.0
    assert summary.evaluation_count == 9
    assert len(writer.requests) == 1

    state = storage.get_content_pipeline_state(request.job_id)
    assert state["job"]["status"] == JobStatus.DONE.value
    assert len(state["decisions"]) == 1
    assert state["decisions"][0]["applied"] == 1
    assert state["decisions"][0]["lifecycle_status"] == "PENDING_APPROVAL"

    # Every evaluation is PASS and none of them was granted by self-report.
    assert {row["result"] for row in state["evaluations"]} == {"PASS"}

    # The ARTICLE attempt carries the auditable style examples.
    examples = load_article_style_examples(default_style_corpus_path(ROOT))
    intent = json.loads(state["intents"][0]["intent_json"])
    assert intent["style_example_ids"] == list(examples.example_ids)
    assert intent["style_example_set_fingerprint"] == examples.fingerprint()

    # Zero real provider effect anywhere in the content half of the chain.
    usage = storage.conn.execute(
        "SELECT dry_run, estimated_cost_usd FROM model_usage WHERE run_id=?",
        (summary.run_id,),
    ).fetchall()
    assert [row["dry_run"] for row in usage] == [1]
    assert [row["estimated_cost_usd"] for row in usage] == [0.0]


def test_unsourced_claim_never_reaches_content_as_a_proceed_card(
    monkeypatch, settings, storage, account,
):
    """First layer: an unsourced confirmed claim cannot become PROCEED."""
    real_settings = _real_settings(settings)
    profile = _pricing_profile(real_settings)
    topic = _topic(storage, account, "incomplete")
    retrievals = _seed_corpus(storage, account)
    payload, _ = _evidence_payload(
        real_settings, account, topic, retrievals, cap=1.0,
        pricing_profile=profile,
    )
    job = storage.enqueue_job(_job(account, topic, "incomplete", payload))
    _open_flags(storage)
    _approve(storage, job.id, account)

    # A second confirmed claim that no source and no excerpt supports.
    response = json.loads(_proceed_response())
    response["confirmed_claims"] = [CLAIM, "Nobody sourced this second claim."]
    _install_fake_client(
        monkeypatch, _FakeEvidenceCaller(json.dumps(response)),
    )
    _worker(real_settings, storage).run_once()

    card_id = _card_id(storage, job)
    assert card_id is not None
    card = storage.get_research_card(int(card_id))
    assert card.publication_recommendation.value == "REJECT"
    assert "CLAIMS_WITHOUT_SOURCES" in (card.rejection_reason or "")
    # Only the claim that has verified evidence carries lineage.
    ordinals = {
        row["confirmed_claim_ordinal"] for row in storage.conn.execute(
            "SELECT confirmed_claim_ordinal FROM evidence_source_lineage "
            "WHERE research_card_id=?", (int(card_id),),
        ).fetchall()
    }
    assert ordinals == {0}


def test_forced_proceed_without_complete_lineage_is_refused(
    settings, storage, account,
):
    """Backstop: a PROCEED card CONTENT would reject is never finalized."""
    from app.models import RunStatus, Source, SourceType
    from app.models import ResearchCard, ResearchRecommendation
    from app.storage.repositories import ResearchTopicIntegrityError
    from tests.test_e3_evidence_research import _manual_walk

    _real, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="forced-proceed", request_started=True,
    )
    storage.settle_provider_attempt_without_usage(
        execution, attempt.request_id, error_code="NO_USAGE",
    )
    topic_id = storage.get_job(job.id).topic_id
    card = ResearchCard(
        topic_id=int(topic_id),
        question="Who decides the gate?",
        working_thesis="Contracts decide the gate.",
        main_mechanism="Carrier agreements allocate pier access.",
        confirmed_claims=[CLAIM],
        confidence_score=0.92,
        source_quality_score=0.9,
        publication_recommendation=ResearchRecommendation.PROCEED,
        sources=[Source(
            url=URLS[0], title="Filing", source_type=SourceType.PRIMARY,
            supports_claim=CLAIM,
            # No verified excerpt was ever recorded for this source.
            verification_status=SourceVerification.UNVERIFIED,
        )],
    )
    # Two independent fail-closed floors guard this: source admission and
    # lineage completeness. Either refusal proves the invariant, so the test
    # accepts whichever fires first rather than pinning one message.
    with pytest.raises(
        ResearchTopicIntegrityError,
        match="authoritative lineage|source admission",
    ):
        storage.finalize_job_research_execution(
            execution, card, total_cost_usd=0.0,
            terminal_run_status=RunStatus.SUCCESS,
        )

    # Nothing partial survived the refusal.
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_source_lineage"
    ).fetchone()[0] == 0
    run = storage.get_research_run(execution.run_id)
    assert run.status.value != "COMPLETE"
    assert run.research_card_id is None


# ---------------------------------------------------------------------------
# Paid usage terminalization: cost > 0, then a failure after the paid call
#
# CONTENT is structurally zero-cost (the storage boundary refuses a
# CONTROLLED_PROVIDER attempt and rejects non-zero offline content usage), so
# the paid boundary that can actually book cost > 0 is the durable provider
# attempt used by evidence research.  Everything below is a fake caller with
# synthetic usage and synthetic cost; no real provider is reachable.
# ---------------------------------------------------------------------------

PAID_COST = 0.004321


def _paid_usage(execution, attempt, *, cost=PAID_COST):
    from app.models import ModelUsage

    return ModelUsage(
        run_id=execution.run_id, provider="anthropic",
        model="evidence-test-model", task="research",
        input_tokens=1200, output_tokens=800,
        estimated_cost_usd=cost, dry_run=False,
        request_id=attempt.request_id, created_at=NOW,
    )


def test_paid_usage_and_cost_survive_a_failure_after_the_paid_call(
    monkeypatch, settings, storage, account,
):
    """usage > 0 and cost > 0 stay durable when the flow fails afterwards."""
    from tests.test_e3_evidence_research import _manual_walk

    real_settings, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="paid-fail", request_started=True,
    )
    booked = storage.add_job_model_usage(
        execution, _paid_usage(execution, attempt),
    )
    assert booked.id is not None

    # The paid operation is settled the moment its usage is booked.
    settled = storage.conn.execute(
        "SELECT status, actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert settled["status"] == ProviderAttemptStatus.SETTLED.value
    assert settled["actual_cost_usd"] == pytest.approx(PAID_COST)

    # Now the flow fails after that paid call.
    storage.fail_job_research_execution(
        execution, PAID_COST, "simulated failure after a paid provider call",
        terminalize_job=True,
    )

    # 1. Cost is durable and booked exactly once.
    rows = storage.conn.execute(
        "SELECT count(*), COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0", (execution.run_id,),
    ).fetchone()
    assert rows[0] == 1
    assert rows[1] == pytest.approx(PAID_COST)

    # 2. The lifecycle is unambiguously terminal, not RUNNING/PENDING.
    research_run = storage.get_research_run(execution.run_id)
    assert research_run.status.value == "FAILED"
    assert research_run.research_card_id is None
    assert float(research_run.total_cost_usd) == pytest.approx(PAID_COST)
    assert storage.get_job(job.id).status is JobStatus.FAILED
    run = storage.get_run(execution.run_id)
    assert run.status.value == "FAILED"
    assert float(run.cost_usd) == pytest.approx(PAID_COST)

    # 3. The attempt stays settled exactly once; no second settlement.
    attempts = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchall()
    assert [row["status"] for row in attempts] == [
        ProviderAttemptStatus.SETTLED.value
    ]


def test_recovery_after_a_paid_call_never_books_the_cost_twice(
    settings, storage, account,
):
    from tests.test_e3_evidence_research import _manual_walk

    real_settings, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="paid-recover", request_started=True,
    )
    storage.add_job_model_usage(execution, _paid_usage(execution, attempt))

    # The exact same usage cannot be booked again: the attempt is no longer an
    # active REQUEST_STARTED, so a replay is refused rather than double counted.
    with pytest.raises(StaleJobExecutionError):
        storage.add_job_model_usage(execution, _paid_usage(execution, attempt))

    # The process dies; lease-expiry recovery resolves it without a second call.
    later = FixedClock(NOW + timedelta(minutes=10))
    recovery = storage.release_or_requeue_expired_leases(clock=later)
    assert recovery.settled_execution_recovery_count == 1

    rows = storage.conn.execute(
        "SELECT count(*), COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0", (execution.run_id,),
    ).fetchone()
    assert rows[0] == 1
    assert rows[1] == pytest.approx(PAID_COST)
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.get_research_run(execution.run_id).status.value == "FAILED"
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()["status"] == ProviderAttemptStatus.SETTLED.value


def test_worker_exception_after_a_paid_call_terminalizes_once(
    monkeypatch, settings, storage, account,
):
    """A live worker crash after the paid call keeps the cost and terminalizes."""
    real_settings, topic, job, _result = _run_e3_paid_crash(
        monkeypatch, settings, storage, account,
    )
    attempt = storage.conn.execute(
        "SELECT status, actual_cost_usd FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.SETTLED.value
    assert float(attempt["actual_cost_usd"]) > 0.0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 1
    run_id = storage.get_job(job.id).run_id
    research_run = storage.get_research_run(run_id)
    assert research_run.status.value == "FAILED"
    assert research_run.research_card_id is None
    assert float(research_run.total_cost_usd) == pytest.approx(
        float(attempt["actual_cost_usd"])
    )
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_source_lineage"
    ).fetchone()[0] == 0


def _run_e3_paid_crash(monkeypatch, settings, storage, account):
    from app.llm.base import Usage
    from app.storage.repositories import SqliteStorage as _Storage

    real_settings = _real_settings(settings)
    profile = _pricing_profile(real_settings)
    topic = _topic(storage, account, "paid-crash")
    retrievals = _seed_corpus(storage, account)
    payload, _ = _evidence_payload(
        real_settings, account, topic, retrievals, cap=1.0,
        pricing_profile=profile,
    )
    job = storage.enqueue_job(_job(account, topic, "paid-crash", payload))
    _open_flags(storage)
    _approve(storage, job.id, account)
    _install_fake_client(
        monkeypatch,
        _FakeEvidenceCaller(
            _proceed_response(),
            usage=Usage(input_tokens=1200, output_tokens=800),
        ),
    )

    def crashing_finalize(self, *args, **kwargs):
        raise RuntimeError("simulated failure after the paid provider call")

    monkeypatch.setattr(
        _Storage, "finalize_job_research_execution", crashing_finalize,
    )
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.FAILED
    return real_settings, topic, job, result


# ---------------------------------------------------------------------------
# CONTENT heartbeat / lease
# ---------------------------------------------------------------------------

def _prepare_content(storage, account, *, suffix):
    from tests.c2_fixtures import seed_c2_research

    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id=f"prec5-lease-{suffix}",
        idempotency_key=f"prec5-lease-{suffix}",
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"prec5-lease-owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, 120, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, lease, owner


def _execution(storage, request, owner, lease):
    state = storage.get_content_pipeline_state(request.job_id)
    return JobExecutionContext(
        job_id=request.job_id,
        lease_owner=owner,
        run_id=str(state["job"]["run_id"]),
        clock=FixedClock(NOW),
        fence_token=lease.job.execution_generation,
        kind=JobKind.CONTENT,
        workflow=WorkflowType.ARTICLE,
    )


def test_content_lease_is_extended_during_the_pipeline(
    storage, settings, account,
):
    request, lease, owner = _prepare_content(storage, account, suffix="beat")
    beats: list[str] = []
    before = storage.conn.execute(
        "SELECT lease_expires_at FROM jobs WHERE id=?", (request.job_id,),
    ).fetchone()["lease_expires_at"]
    observed: list[str] = []

    def record_beat() -> None:
        beats.append("beat")
        row = storage.conn.execute(
            "SELECT lease_expires_at FROM jobs WHERE id=?", (request.job_id,),
        ).fetchone()
        observed.append(row["lease_expires_at"])

    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=FakeContentWriter(),
        lease_seconds=600,
        heartbeat=record_beat,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    # The pipeline refreshed ownership more than once during the run.
    assert len(beats) >= 3
    # Each observed expiry is the extended 600s one, strictly beyond the
    # original 120s claim: the lease really moved, it was not just called.
    assert observed and all(value > before for value in observed)


def test_pipeline_without_the_typed_heartbeat_leaves_the_lease_untouched(
    storage, settings, account,
):
    """Control case proving the previous test observes a real extension."""
    request, lease, owner = _prepare_content(storage, account, suffix="nobeat")
    before = storage.conn.execute(
        "SELECT lease_expires_at FROM jobs WHERE id=?", (request.job_id,),
    ).fetchone()["lease_expires_at"]
    observed: list[str] = []
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=FakeContentWriter(),
        lease_seconds=0,
        heartbeat=lambda: observed.append(
            storage.conn.execute(
                "SELECT lease_expires_at FROM jobs WHERE id=?",
                (request.job_id,),
            ).fetchone()["lease_expires_at"]
        ),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert observed and all(value == before for value in observed)


def test_content_heartbeat_refuses_a_lost_or_stale_lease(
    storage, settings, account,
):
    request, lease, owner = _prepare_content(storage, account, suffix="stale")
    # Initialize the run so a typed execution context exists.
    run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=FakeContentWriter(),
    )
    execution = _execution(storage, request, owner, lease)

    # A foreign owner can never extend this lease.
    foreign = JobExecutionContext(
        job_id=execution.job_id, lease_owner="someone-else",
        run_id=execution.run_id, clock=FixedClock(NOW),
        fence_token=execution.fence_token, kind=JobKind.CONTENT,
        workflow=WorkflowType.ARTICLE,
    )
    with pytest.raises(StaleJobExecutionError):
        storage.heartbeat_content_execution(foreign, 60)

    # Neither can an outdated execution generation.
    stale_generation = JobExecutionContext(
        job_id=execution.job_id, lease_owner=owner, run_id=execution.run_id,
        clock=FixedClock(NOW), fence_token=execution.fence_token + 7,
        kind=JobKind.CONTENT, workflow=WorkflowType.ARTICLE,
    )
    with pytest.raises(StaleJobExecutionError):
        storage.heartbeat_content_execution(stale_generation, 60)


def test_generic_heartbeat_still_refuses_content_jobs(storage, account):
    from tests.c2_fixtures import seed_c2_research
    from app.ports.storage import ContentFoundationError

    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id="prec5-generic-beat",
        idempotency_key="prec5-generic-beat",
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    storage.claim_specific_job(
        request.job_id, "generic-owner", 60, clock=FixedClock(NOW),
    )
    with pytest.raises(ContentFoundationError):
        storage.heartbeat_job_lease(
            request.job_id, "generic-owner", 60, clock=FixedClock(NOW),
        )


def test_lost_lease_stops_the_pipeline_before_any_further_write(
    storage, settings, account,
):
    """A pipeline whose lease was taken over cannot keep writing."""
    request, lease, owner = _prepare_content(storage, account, suffix="lost")

    class LeaseStealingWriter(FakeContentWriter):
        """Steals the lease at exactly the moment the writer is invoked."""

        def __init__(self, storage, job_id):
            super().__init__()
            self._storage = storage
            self._job_id = job_id

        def write(self, request):
            self._storage.conn.execute(
                "UPDATE jobs SET lease_owner='thief' WHERE id=?", (self._job_id,),
            )
            self._storage.conn.commit()
            return super().write(request)

    writer = LeaseStealingWriter(storage, request.job_id)
    with pytest.raises(StaleJobExecutionError):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=writer,
            lease_seconds=600,
        )
    # No decision and no terminal content status were produced under the
    # lost lease.
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["decisions"] == []
    assert state["content"]["status"] not in {
        ContentStatus.PENDING_APPROVAL.value,
        ContentStatus.APPROVED.value,
        ContentStatus.REJECTED.value,
    }


def test_recovery_after_a_persisted_result_does_not_call_the_writer_again(
    storage, settings, account,
):
    request, lease, owner = _prepare_content(storage, account, suffix="resume")

    class CountingWriter(FakeContentWriter):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def write(self, request):
            self.calls += 1
            return super().write(request)

    class Stop(RuntimeError):
        pass

    first = CountingWriter()
    with pytest.raises(Stop):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=first,
            fault_point=lambda point: (
                (_ for _ in ()).throw(Stop(point))
                if point == "WRITER_RESULT_PERSISTED" else None
            ),
        )
    assert first.calls == 1

    state = storage.get_content_pipeline_state(request.job_id)
    resumed_job = storage.get_job(request.job_id)
    second = CountingWriter()
    summary = run_offline_content_pipeline(
        resumed_job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=second,
    )
    # The persisted result was reused; the writer was never called twice.
    assert second.calls == 0
    assert summary.status is ContentStatus.PENDING_APPROVAL
    attempts = storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0]
    assert attempts == 1
