"""PRE-C5 repair: the four reviewer counter-examples plus the paid CONTENT gate.

Every test here is offline: fake evidence callers, fake writers, synthetic
usage and cost, temporary SQLite databases only.  No network, no SDK, no real
provider, no production database.
"""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import pytest

from app.content.contracts import (
    ArticleBrief,
    FakeDraft,
    RouteContract,
    WriterCallMode,
    WriterFailure,
    WriterFailureKind,
    WriterLimits,
    WriterSuccess,
    WriterUsage,
)
from app.content.evaluations import aggregate_decision, evaluate_draft
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
    FrozenEvidenceItem,
    sha256_text,
)
from app.content.pipeline import run_offline_content_pipeline
from app.content.quality_gate import (
    CLAIM_ACCOUNTING_REVIEW_MISSING,
    FACTUAL_CLAIM_EVIDENCE_MISSING,
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    QualityCheck,
    assess_draft,
)
from app.content.writer import FakeContentWriter
from app.core.clock import FixedClock
from app.models import JobStatus, ProviderAttemptStatus, SourceVerification
from app.policies.policy_engine import PolicyEngine
from app.ports.fetch import FetchedDocument
from app.ports.storage import ContentFoundationError, StaleJobExecutionError
from app.research.source_admission import (
    INSUFFICIENT_SOURCE_INDEPENDENCE,
    SYNDICATION_METADATA_INVALID,
    SourceClass,
    SourceDescriptor,
    evaluate_source_admission,
    resolve_independence_keys,
)
from app.scheduler.worker import WorkerIterationStatus
from tests.c2_fixtures import seed_c2_research
from tests.controlled_provider_fixtures import (
    approve_content_provider_execution,
    seed_active_article_writer,
)
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    ground_every_segment_in_package,
)
from tests.test_e3_evidence_research import (
    NOW,
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


# ---------------------------------------------------------------------------
# RV1 — a plain, non-numeric factual claim from outside the Research Package
# ---------------------------------------------------------------------------

CLAIM = "Gate assignment follows contractual priority, not passenger convenience."
EXCERPT = (
    "Gate assignment at large hubs follows contractual priority agreed with "
    "carriers, not passenger convenience."
)
_FILLER = (
    " The carrier agreement decides which airline reaches which pier and the "
    "boarding queue is the visible end of that contractual arrangement, which "
    "is why the ordinary result looks arbitrary to the passenger standing in it."
)
GROUNDED_BODY = (
    "Gate assignment follows contractual priority, not passenger convenience. "
    "Weather still overrides contracts, so it is a tendency." + _FILLER * 3
)


def _evidence(claim: str = CLAIM, excerpt: str = EXCERPT, ordinal: int = 0):
    url = f"https://primary.example/{ordinal}"
    return FrozenEvidenceItem(
        ordinal=ordinal, account_id="nothing_is_accidental", topic_id=1,
        research_run_id="run-1", research_job_id="job-1", research_card_id=1,
        confirmed_claim_id=f"research-card:1:confirmed-claim:{ordinal}",
        confirmed_claim_ordinal=ordinal, claim_text=claim,
        claim_sha256=sha256_text(claim), candidate_id=ordinal + 1,
        source_id=ordinal + 1, source_url=url,
        source_url_sha256=sha256_text(url), source_claim_text=claim,
        source_claim_sha256=sha256_text(claim), excerpt_id=ordinal + 1,
        excerpt_text=excerpt, excerpt_sha256=sha256_text(excerpt),
        retrieval_id=ordinal + 1, requested_url_sha256=sha256_text(url),
        final_url_sha256=sha256_text(url), canonical_sha256=sha256_text(excerpt),
        lineage_fingerprint=sha256_text(f"lineage-{ordinal}"),
    )


def _brief() -> ArticleBrief:
    return ArticleBrief(
        working_title="Why gate assignment shapes the boarding queue",
        central_thesis="Gate assignment follows contractual priority.",
        answer_question="Who decides the gate?",
        narrative_angle="A visible outcome with an invisible cause.",
        target_reader="A curious traveller.",
        concrete_opening="The gate changes before boarding.",
        argument_structure=("observation", "mechanism"),
        required_facts=("contractual priority",),
        evidence_ids=("research-card:1:confirmed-claim:0",),
        counterargument_or_limitation="Weather overrides contracts.",
        ending="The ordinary result is not accidental.",
        min_words=100, max_words=1200,
        forbidden_claims=("airlines never publish gate rules",),
    )


def _draft(body: str, **overrides) -> FakeDraft:
    payload = {
        "attempt_no": 1, "route_key": "FABLE_5_ARTICLE",
        "title": "Why gate assignment shapes the boarding queue", "body": body,
        "evidence_ids_used": ("research-card:1:confirmed-claim:0",),
        "unsupported_claims": (), "personal_experience": False,
        "style_ok": True, "brief_compliant": True,
    }
    payload.update(overrides)
    return FakeDraft(**payload)


def _strict_review(segment, evidence_ids):
    text = segment.text.lower()
    if any(marker in text for marker in (
        "i think", "i would argue", "this suggests", "the point is",
    )):
        classification = ClaimClassification.ARGUMENT_OR_INFERENCE
        ids = ()
        outcome = ClaimReviewOutcome.PASS
        external = False
    elif (
        segment.text in GROUNDED_BODY.replace(_FILLER * 3, _FILLER * 3).split(". ")
        or "gate assignment follows contractual priority" in text
        or "carrier agreement decides" in text
        or "weather still overrides" in text
    ):
        classification = ClaimClassification.EVIDENCE_GROUNDED_FACT
        ids = evidence_ids[:1]
        outcome = ClaimReviewOutcome.PASS
        external = True
    else:
        classification = ClaimClassification.EVIDENCE_GROUNDED_FACT
        ids = ()
        outcome = ClaimReviewOutcome.BLOCK
        external = True
    return ClaimAccountingEntry(
        segment_id=segment.segment_id,
        segment_fingerprint=segment.fingerprint,
        classification=classification,
        evidence_ids=ids,
        reason="strict fake reviewer checked the complete segment",
        outcome=outcome,
        contains_external_fact=external,
    )


def _decide(body: str, reviewer=None, *, with_reviewer: bool = True):
    resolved = reviewer or (
        FakeClaimAccountingReviewer(decide=_strict_review)
        if with_reviewer else None
    )
    return aggregate_decision(
        evaluate_draft(
            _draft(body), _brief(), evidence=(_evidence(),),
            claim_reviewer=resolved,
        )
    )


def test_rv1_non_numeric_unsupported_factual_claim_is_blocked():
    """The reviewer's example: a mayor's action, no number, no attribution."""
    body = GROUNDED_BODY + (
        " The mayor cancelled the terminal modernisation programme after the "
        "council vote."
    )
    verdict = assess_draft(
        _draft(body), _brief(), evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(decide=_strict_review),
        require_independent_review=True,
    )
    assert verdict.passed(QualityCheck.NO_OUT_OF_CORPUS_CLAIMS) is False
    assert FACTUAL_CLAIM_EVIDENCE_MISSING in {
        item["code"] for item in verdict.findings
    }
    assert _decide(body).value == "BLOCK"


def test_rv1_unsupported_named_person_role_and_institutional_decision():
    body = GROUNDED_BODY + (
        " Commissioner Alvarez ordered the regulator to reopen the licensing "
        "inquiry."
    )
    assert _decide(body).value == "BLOCK"
    named = GROUNDED_BODY + (
        " Helena Ortiz Ramirez signed the concession for the northern pier."
    )
    assert _decide(named).value == "BLOCK"


def test_rv1_unsupported_causal_factual_claim_without_any_number():
    body = GROUNDED_BODY + (
        " The ministry scrapped the subsidy, which closed three regional "
        "airports."
    )
    assert _decide(body).value == "BLOCK"


def test_rv1_legitimate_opinion_and_inference_are_never_auto_blocked():
    body = GROUNDED_BODY + (
        " I think the contractual reading is the stronger one. This suggests "
        "convenience plays no part. I would argue the queue is a symptom."
    )
    assert _decide(body).value == "PASS"


def test_rv1_factual_claim_tied_to_admitted_evidence_passes():
    body = GROUNDED_BODY + (
        " Gate assignment follows contractual priority agreed with carriers, "
        "not passenger convenience."
    )
    assert _decide(body).value == "PASS"


def test_rv1_fake_semantic_evaluator_blocker_reaches_the_lifecycle():
    class BlockingReviewer:
        reviewer_version = "fake-blocking-reviewer-v1"

        def review(self, *, draft, brief, evidence, segments):
            base = FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ).review(
                draft=draft, brief=brief, evidence=evidence, segments=segments,
            )
            first = base[0]
            return (
                ClaimAccountingEntry(
                    segment_id=first.segment_id,
                    segment_fingerprint=first.segment_fingerprint,
                    classification=first.classification,
                    evidence_ids=first.evidence_ids,
                    reason="fake evaluator refused this draft",
                    outcome=ClaimReviewOutcome.BLOCK,
                    contains_external_fact=first.contains_external_fact,
                ),
                *base[1:],
            )

    assert _decide(GROUNDED_BODY, BlockingReviewer()).value == "BLOCK"


def test_rv1_semantic_evaluator_cannot_clear_a_deterministic_blocker():
    class PermissiveReviewer:
        reviewer_version = "fake-permissive-reviewer-v1"

        def review(self, *, draft, brief, evidence, segments):
            return FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ).review(
                draft=draft, brief=brief, evidence=evidence, segments=segments,
            )

    body = GROUNDED_BODY + " The report proves that 99% of gates are reassigned."
    assert _decide(body, PermissiveReviewer()).value == "BLOCK"


def test_rv1_article_without_independent_evaluator_is_fail_closed():
    verdict = assess_draft(
        _draft(GROUNDED_BODY), _brief(), evidence=(_evidence(),),
        claim_reviewer=None, require_independent_review=True,
    )
    assert CLAIM_ACCOUNTING_REVIEW_MISSING in {
        item["code"] for item in verdict.findings
    }
    assert _decide(GROUNDED_BODY, with_reviewer=False).value == "BLOCK"


def test_rv1_pipeline_fails_closed_when_no_reviewer_can_be_composed(
    storage, settings, account,
):
    request, lease, owner = _prepare_content(storage, account, suffix="no-reviewer")
    summary = run_offline_content_pipeline(
        lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
        project_root=ROOT, policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=FakeContentWriter(), reviewer_factory=lambda: None,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == "CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE"


# ---------------------------------------------------------------------------
# RV2 — source admission inside the real E3 runtime
# ---------------------------------------------------------------------------

SAME_DOMAIN_URLS = (
    "https://news.same.example/a",
    "https://blog.same.example/b",
    "https://www.same.example/c",
)
INDEPENDENT_URLS = (
    "https://regulator.example/filing",
    "https://press.example/report",
    "https://journal.example/paper",
)
E3_CLAIM = "Gate assignment follows contractual priority."
E3_EXCERPT = "gate assignment follows contractual priority"
_BODIES = (
    "The regulator filing states that gate assignment follows contractual "
    "priority agreed with each carrier before the season opens.",
    "Trade reporting confirms that gate assignment follows contractual "
    "priority, with pier access negotiated years in advance.",
    "An academic review records that gate assignment follows contractual "
    "priority rather than passenger convenience at large hubs.",
)


def _seed(storage, account, urls):
    storage.ensure_account(account)
    return [
        storage.record_evidence_retrieval(
            FetchedDocument(
                requested_url=url, final_url=url, fetched_at=NOW, http_status=200,
                content_type="text/plain; charset=utf-8",
                body=body.encode("utf-8"), error=None,
            ),
            account_id=account.id, now=NOW,
        )
        for url, body in zip(urls, _BODIES)
    ]


def _response(urls):
    return json.dumps({
        "question": "Who decides the gate?",
        "working_thesis": "Contracts decide the gate.",
        "main_mechanism": "Carrier agreements allocate pier access.",
        "confirmed_claims": [E3_CLAIM], "uncertain_claims": [],
        "contradictions": [], "strongest_counterargument": "Weather overrides.",
        "citable_numbers": [], "visual_idea": "A pier map.",
        "confidence_score": 0.92, "source_quality_score": 0.9,
        "sources": [
            {
                "url": url, "title": f"Source {index}",
                "author_or_org": "Example Org", "published_at": None,
                "source_type": "PRIMARY" if index == 0 else "SECONDARY",
                "supports_claim": E3_CLAIM, "supporting_excerpt": E3_EXCERPT,
            }
            for index, url in enumerate(urls)
        ],
    })


def _run_e3(monkeypatch, settings, storage, account, *, key, urls):
    real_settings = _real_settings(settings)
    profile = _pricing_profile(real_settings)
    topic = _topic(storage, account, key)
    retrievals = _seed(storage, account, urls)
    payload, _ = _evidence_payload(
        real_settings, account, topic, retrievals, cap=1.0, pricing_profile=profile,
    )
    job = storage.enqueue_job(_job(account, topic, key, payload))
    _open_flags(storage)
    _approve(storage, job.id, account)
    _install_fake_client(monkeypatch, _FakeEvidenceCaller(_response(urls)))
    result = _worker(real_settings, storage).run_once()
    return job, result


def _card(storage, job):
    run_id = storage.get_job(job.id).run_id
    row = storage.conn.execute(
        "SELECT research_card_id FROM research_runs WHERE id=?", (run_id,),
    ).fetchone()
    if row is None or row["research_card_id"] is None:
        return None
    return storage.get_research_card(int(row["research_card_id"]))


def test_rv2_three_same_domain_sources_cannot_proceed_in_real_runtime(
    monkeypatch, settings, storage, account,
):
    """The exact reviewer scenario, driven through the real worker."""
    job, result = _run_e3(
        monkeypatch, settings, storage, account,
        key="rv2-same-domain", urls=SAME_DOMAIN_URLS,
    )
    card = _card(storage, job)
    assert card is not None
    assert card.publication_recommendation.value != "PROCEED"
    assert INSUFFICIENT_SOURCE_INDEPENDENCE in (card.rejection_reason or "")
    # A rejected card can never become content, whatever lineage it carries.
    from app.ports.storage import ContentSnapshotError

    with pytest.raises(ContentSnapshotError, match="CONTENT_CARD_NOT_PROCEED"):
        storage.prepare_content_job(
            ContentPreparationRequest(
                job_id="rv2-content", idempotency_key="rv2-content",
                account_id=account.id, research_card_id=int(card.id),
                content_type=ContentType.ARTICLE,
                execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
                prompt_version="offline_content_prompt_v1",
                style_guide_version="ARTICLE_STYLE_PROFILE_V1",
            ),
            clock=FixedClock(NOW),
        )


def test_rv2_independent_sources_still_proceed_in_real_runtime(
    monkeypatch, settings, storage, account,
):
    job, result = _run_e3(
        monkeypatch, settings, storage, account,
        key="rv2-independent", urls=INDEPENDENT_URLS,
    )
    assert result.status is WorkerIterationStatus.DONE
    card = _card(storage, job)
    assert card.publication_recommendation.value == "PROCEED"
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_source_lineage WHERE research_card_id=?",
        (int(card.id),),
    ).fetchone()[0] == 3


def test_rv2_admission_floor_cannot_be_bypassed_by_calling_finalization(
    settings, storage, account,
):
    """The gate lives in the finalization transaction, not only in a pre-check."""
    from app.models import ResearchCard, ResearchRecommendation, RunStatus, Source, SourceType
    from app.storage.repositories import ResearchTopicIntegrityError
    from tests.test_e3_evidence_research import _manual_walk

    _real, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="rv2-bypass", request_started=True,
    )
    storage.settle_provider_attempt_without_usage(
        execution, attempt.request_id, error_code="NO_USAGE",
    )
    topic_id = storage.get_job(job.id).topic_id
    card = ResearchCard(
        topic_id=int(topic_id), question="q", working_thesis="t",
        main_mechanism="m", confirmed_claims=[E3_CLAIM],
        confidence_score=0.9, source_quality_score=0.9,
        publication_recommendation=ResearchRecommendation.PROCEED,
        sources=[
            Source(url=url, title="s", source_type=SourceType.SECONDARY,
                   supports_claim=E3_CLAIM,
                   verification_status=SourceVerification.VERIFIED)
            for url in SAME_DOMAIN_URLS
        ],
    )
    with pytest.raises(ResearchTopicIntegrityError, match="source admission"):
        storage.finalize_job_research_execution(
            execution, card, total_cost_usd=0.0,
            terminal_run_status=RunStatus.SUCCESS,
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_source_lineage"
    ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# RV3 — syndication cannot manufacture an independent owner
# ---------------------------------------------------------------------------

def _descriptor(url, retrieval_id, *, klass=SourceClass.SUPPORTING, syn=None,
                digest=None):
    return SourceDescriptor(
        url=url, retrieval_id=retrieval_id, source_class=klass,
        content_sha256=digest or f"{retrieval_id}" * 64,
        syndication_of=syn, supports_claim=E3_CLAIM,
    )


def test_rv3_syndicated_copy_does_not_add_an_independent_owner():
    outcome = evaluate_source_admission(
        [
            _descriptor("https://origin.com/story", 1, klass=SourceClass.PRIMARY),
            _descriptor("https://reprint.example/story", 2,
                        syn="https://www.origin.com/story/"),
            _descriptor("https://third.example/story", 3),
        ],
        confirmed_claims=[E3_CLAIM],
    )
    assert outcome.independent_owner_count == 2
    assert {item.independence_key for item in outcome.admitted_sources} == {
        "origin.com", "third.example",
    }


@pytest.mark.parametrize(
    "declared",
    [
        "https://www.origin.com/story",
        "http://origin.com/story/",
        "origin.com",
        "https://news.origin.com/other?ref=1",
        "https://origin.com",
    ],
)
def test_rv3_syndication_url_variants_all_collapse_to_one_owner(declared):
    keys = resolve_independence_keys([
        _descriptor("https://origin.com/story", 1, klass=SourceClass.PRIMARY),
        _descriptor("https://reprint.example/story", 2, syn=declared),
    ])
    assert keys[1] == keys[2] == "origin.com"


def test_rv3_chained_syndication_collapses_onto_the_ultimate_origin():
    outcome = evaluate_source_admission(
        [
            _descriptor("https://c.example/1", 1, klass=SourceClass.PRIMARY),
            _descriptor("https://b.example/1", 2, syn="https://c.example/"),
            _descriptor("https://a.example/1", 3, syn="http://www.b.example/1"),
        ],
        confirmed_claims=[E3_CLAIM],
    )
    assert outcome.independent_owner_count == 1
    assert INSUFFICIENT_SOURCE_INDEPENDENCE in outcome.reasons


def test_rv3_malformed_syndication_metadata_is_fail_closed():
    outcome = evaluate_source_admission(
        [
            _descriptor("https://origin.com/1", 1, klass=SourceClass.PRIMARY),
            _descriptor("https://x.example/1", 2, syn="   :::not a url:::   "),
            _descriptor("https://y.example/1", 3),
        ],
        confirmed_claims=[E3_CLAIM],
    )
    assert outcome.admitted is False
    assert SYNDICATION_METADATA_INVALID in outcome.reasons


def test_rv3_two_genuinely_independent_domains_still_count_separately():
    outcome = evaluate_source_admission(
        [
            _descriptor("https://alpha.example/1", 1, klass=SourceClass.PRIMARY),
            _descriptor("https://beta.example/1", 2),
            _descriptor("https://gamma.example/1", 3),
        ],
        confirmed_claims=[E3_CLAIM],
    )
    assert outcome.admitted is True
    assert outcome.independent_owner_count == 3


# ---------------------------------------------------------------------------
# Shared CONTENT helpers
# ---------------------------------------------------------------------------

def _prepare_content(
    storage, account, *, suffix,
    mode=ContentExecutionMode.OFFLINE_PIPELINE, lease_seconds=120,
):
    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id=f"prec5r-{suffix}", idempotency_key=f"prec5r-{suffix}",
        account_id=account.id, research_card_id=int(seed["card_id"]),
        content_type=ContentType.ARTICLE, execution_mode=mode,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"prec5r-owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, lease_seconds, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, lease, owner


def _paid_route() -> RouteContract:
    """A technically complete route with no registry provenance at all.

    Since the provenance wave this is exactly what a paid execution may not
    use, so it survives only as the negative fixture for that refusal.
    """
    return RouteContract(
        content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
        logical_model_name="Fable 5", config_version="prec5-repair-v1",
        config_fingerprint="a" * 64, provider="fake-paid-provider",
        api_model_id="fake-paid-model", availability="CONFIGURED",
        pricing_profile="prec5-repair-pricing",
    )


class PaidFakeWriter:
    """Fake CONTROLLED_PROVIDER writer: real usage shape, no self-priced cost.

    A controlled provider reports tokens; the cost of those tokens is decided
    by the frozen pricing authority, never by the caller.
    """

    call_mode = WriterCallMode.CONTROLLED_PROVIDER

    def __init__(self, *, cost_usd=0.0, fail=False, uncertain=False,
                 before_call=None):
        self.cost_usd = cost_usd
        self.fail = fail
        self.uncertain = uncertain
        self.before_call = before_call
        self.calls = 0

    def limits_for(self, content_type):
        return WriterLimits(
            max_input_tokens=8_000, max_context_tokens=16_000,
            max_output_tokens=2_048, max_cost_usd=0.05, timeout_seconds=5.0,
        )

    def preflight(self, _request):
        return None

    def write(self, request):
        self.calls += 1
        if self.before_call is not None:
            self.before_call()
        usage = WriterUsage(
            input_tokens=1200, output_tokens=800,
            estimated_cost_usd=self.cost_usd,
        )
        if self.fail:
            return WriterFailure(
                kind=WriterFailureKind.PROVIDER_5XX,
                provider=request.intent.route.provider,
                route_key=request.intent.route.route_key,
                api_model_id=request.intent.route.api_model_id,
                usage=usage, stop_reason=None,
                provider_request_id="fake-paid-request",
                detail="Provider failed after returning usage.",
                uncertain=self.uncertain,
            )
        draft = FakeContentWriter().write(request).draft
        return WriterSuccess(
            draft=draft, provider=request.intent.route.provider,
            route_key=request.intent.route.route_key,
            api_model_id=request.intent.route.api_model_id,
            usage=usage, stop_reason="end_turn",
            provider_request_id="fake-paid-request",
        )


# 1200 input tokens at 2/Mtok plus 800 output tokens at 7/Mtok, priced from the
# frozen fake registry profile rather than from anything the caller reported.
EXPECTED_PAID_COST = 0.008
# A deliberately expensive fake price list: the same 1200/800 tokens settle at
# 0.060000, above the 0.05 cap the paid writer declares, so the over-cap path is
# now driven by the authoritative pricing profile instead of a self-reported
# number the provider is no longer allowed to send.
OVER_CAP_PRICES = {"input_per_mtok": "20", "output_per_mtok": "45"}
EXPECTED_OVER_CAP_COST = 0.06


def _run_paid(storage, settings, account, *, suffix, writer, lease_seconds=120,
              pipeline_lease_seconds=600, seed_registry=True,
              price_overrides=None):
    model = None
    if seed_registry:
        model = seed_active_article_writer(
            storage, price_overrides=price_overrides,
        )
    request, lease, owner = _prepare_content(
        storage, account, suffix=suffix,
        mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
        lease_seconds=lease_seconds,
    )
    if model is not None:
        approve_content_provider_execution(
            storage, job_id=request.job_id, model=model,
            account_id=account.id,
        )
    summary = run_offline_content_pipeline(
        lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
        project_root=ROOT, policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=writer,
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
        lease_seconds=pipeline_lease_seconds,
    )
    return request, lease, owner, summary


# ---------------------------------------------------------------------------
# Paid CONTENT-specific usage gate
# ---------------------------------------------------------------------------

def test_paid_content_success_books_the_cost_exactly_once(
    storage, settings, account,
):
    writer = PaidFakeWriter()
    request, _, _, summary = _run_paid(
        storage, settings, account, suffix="paid-ok", writer=writer,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert writer.calls == 1
    usage = storage.conn.execute(
        "SELECT request_id,estimated_cost_usd,dry_run FROM model_usage "
        "WHERE run_id=?", (summary.run_id,),
    ).fetchall()
    assert len(usage) == 1
    assert usage[0]["dry_run"] == 0
    assert usage[0]["estimated_cost_usd"] == pytest.approx(EXPECTED_PAID_COST)
    assert summary.cost_usd == pytest.approx(EXPECTED_PAID_COST)
    attempt = storage.conn.execute(
        "SELECT status,actual_cost_usd,reserved_amount_usd FROM provider_attempts "
        "WHERE job_id=?", (request.job_id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.SETTLED.value
    assert attempt["actual_cost_usd"] == pytest.approx(EXPECTED_PAID_COST)
    assert float(attempt["reserved_amount_usd"]) > 0.0


def test_paid_content_failure_after_usage_keeps_the_cost(
    storage, settings, account,
):
    writer = PaidFakeWriter(fail=True)
    request, _, _, summary = _run_paid(
        storage, settings, account, suffix="paid-fail", writer=writer,
    )
    assert summary.status is ContentStatus.FAILED
    assert writer.calls == 1
    usage = storage.conn.execute(
        "SELECT count(*),COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0", (summary.run_id,),
    ).fetchone()
    assert usage[0] == 1
    assert usage[1] == pytest.approx(EXPECTED_PAID_COST)
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (request.job_id,),
    ).fetchone()["status"] == ProviderAttemptStatus.SETTLED.value
    job = storage.get_job(request.job_id)
    assert job.status in (JobStatus.DONE, JobStatus.FAILED)
    assert job.lease_owner is None


def test_paid_content_recovery_does_not_settle_or_charge_twice(
    storage, settings, account,
):
    writer = PaidFakeWriter()
    request, lease, owner, summary = _run_paid(
        storage, settings, account, suffix="paid-recover", writer=writer,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    later = FixedClock(NOW + timedelta(hours=2))
    storage.release_or_requeue_expired_leases(clock=later)
    assert storage.claim_specific_job(
        request.job_id, owner, 120, clock=later,
    ) is None
    usage = storage.conn.execute(
        "SELECT count(*),COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=?", (summary.run_id,),
    ).fetchone()
    assert usage[0] == 1
    assert usage[1] == pytest.approx(EXPECTED_PAID_COST)
    assert writer.calls == 1
    settled = storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=? AND status=?",
        (request.job_id, ProviderAttemptStatus.SETTLED.value),
    ).fetchone()[0]
    assert settled == 1


def test_offline_content_still_refuses_a_non_zero_cost(
    storage, settings, account,
):
    """The offline protection is intact: OFFLINE_PIPELINE cannot spend."""
    seed_active_article_writer(storage)
    request, lease, owner = _prepare_content(
        storage, account, suffix="offline-nonzero",
        mode=ContentExecutionMode.OFFLINE_PIPELINE,
    )
    with pytest.raises(ContentFoundationError, match="CONTENT_CONTROLLED_PROVIDER_NOT_AUTHORIZED"):
        run_offline_content_pipeline(
            lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=PaidFakeWriter(),
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0


def test_paid_content_requires_a_provider_enabled_execution_mode(
    storage, settings, account,
):
    """Declaring the paid writer is not enough without the paid job contract."""
    seed_active_article_writer(storage)
    request, lease, owner = _prepare_content(
        storage, account, suffix="paid-unauthorized",
        mode=ContentExecutionMode.OFFLINE_PIPELINE,
    )
    with pytest.raises(ContentFoundationError) as excinfo:
        run_offline_content_pipeline(
            lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=PaidFakeWriter(),
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
        )
    assert "CONTENT_CONTROLLED_PROVIDER_NOT_AUTHORIZED" in str(excinfo.value)


def test_paid_content_result_is_not_written_after_ownership_is_lost(
    storage, settings, account,
):
    """A paid result returning under a stale generation cannot be persisted."""
    def steal():
        storage.conn.execute(
            "UPDATE jobs SET lease_owner='thief' WHERE id=?",
            ("prec5r-paid-stale",),
        )
        storage.conn.commit()

    writer = PaidFakeWriter(before_call=steal)
    with pytest.raises(StaleJobExecutionError):
        _run_paid(
            storage, settings, account, suffix="paid-stale", writer=writer,
        )
    state = storage.get_content_pipeline_state("prec5r-paid-stale")
    assert state["decisions"] == []
    assert state["content"]["status"] not in {
        ContentStatus.PENDING_APPROVAL.value, ContentStatus.APPROVED.value,
    }


# ---------------------------------------------------------------------------
# RV4 — a call outliving its lease must not produce a second paid call
# ---------------------------------------------------------------------------

def test_rv4_call_longer_than_lease_never_yields_a_second_writer_call(
    storage, settings, account,
):
    """Reviewer scenario: recovery runs while the first paid call is in flight."""
    recovery: dict[str, object] = {}

    def expire_and_recover():
        # The call is still running; its lease expires and recovery sweeps.
        later = FixedClock(NOW + timedelta(hours=3))
        recovery["result"] = storage.release_or_requeue_expired_leases(clock=later)

    first = PaidFakeWriter(before_call=expire_and_recover)
    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare_content(
        storage, account, suffix="rv4",
        mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE, lease_seconds=1,
    )
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )
    try:
        run_offline_content_pipeline(
            lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=first, lease_seconds=0,
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
        )
    except (StaleJobExecutionError, ContentFoundationError):
        pass
    assert first.calls == 1
    assert recovery["result"] is not None

    # The durable in-flight barrier was raised BEFORE the call, so recovery
    # could not hand this job back for a second potentially paid attempt. It
    # terminalized into an explicit reconciliation state instead of requeuing.
    # (That the stamp itself is written pre-call is proved by the companion
    # test below, which inspects it before recovery terminalizes the job.)
    job = storage.get_job(request.job_id)
    assert job.status is not JobStatus.QUEUED
    assert job.status is JobStatus.NEEDS_VERIFICATION

    # Even a deliberate second execution refuses to call the writer again.
    second = PaidFakeWriter()
    retry = storage.claim_specific_job(
        request.job_id, "second-worker", 120,
        clock=FixedClock(NOW + timedelta(hours=4)),
    )
    if retry is not None:
        try:
            run_offline_content_pipeline(
                retry.job, storage=storage,
                clock=FixedClock(NOW + timedelta(hours=4)),
                lease_owner="second-worker", project_root=ROOT,
                policy=PolicyEngine(settings, storage, FixedClock(NOW)),
                writer=second, lease_seconds=0,
                claim_reviewer=FakeClaimAccountingReviewer(
                    decide=ground_every_segment_in_package
                ),
            )
        except (StaleJobExecutionError, ContentFoundationError):
            pass
    assert second.calls == 0
    assert first.calls + second.calls == 1


def test_rv4_in_flight_paid_attempt_blocks_automatic_recovery_requeue(
    storage, settings, account,
):
    """A stamped external effect removes the safe zero-cost requeue path."""
    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare_content(
        storage, account, suffix="rv4-barrier",
        mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE, lease_seconds=1,
    )
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )

    class AbortingWriter(PaidFakeWriter):
        def write(self, request):
            self.calls += 1
            raise RuntimeError("process died mid-call")

    writer = AbortingWriter()
    with pytest.raises(RuntimeError):
        run_offline_content_pipeline(
            lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
            project_root=ROOT,
            policy=PolicyEngine(settings, storage, FixedClock(NOW)),
            writer=writer, lease_seconds=0,
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
        )
    assert writer.calls == 1
    job = storage.get_job(request.job_id)
    assert job.external_effect_started_at is not None

    later = FixedClock(NOW + timedelta(hours=3))
    storage.release_or_requeue_expired_leases(clock=later)
    assert storage.get_job(request.job_id).status is not JobStatus.QUEUED
    # Recovery normalized the in-flight attempt into an explicit
    # reconciliation item; it never handed the job back for a second call.
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (request.job_id,),
    ).fetchone()["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value
    assert storage.get_job(request.job_id).status is JobStatus.NEEDS_VERIFICATION


# ---------------------------------------------------------------------------
# Migration 0026 rehearsal — temp databases only, explicit confirmation
# ---------------------------------------------------------------------------

def test_migration_0026_is_forward_only_explicit_and_idempotent(tmp_path, capsys):
    import scripts.migrate_schema_0026 as migration_cli_0026
    from app.storage.db import (
        CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
        CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
        MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
        EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
        SchemaVersionTooOld,
        database_schema_versions,
        initialize_database,
        migrate_0025_to_0026,
        migrate_0026_to_0027,
        migrate_0027_to_0028,
        migrate_0028_to_0029,
        VERIFIED_CATALOGUE_SCHEMA_VERSION,
    )
    from app.storage.repositories import SqliteStorage

    fresh = tmp_path / "fresh-0026.db"
    applied = initialize_database(
        fresh, through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    )
    assert applied[-1] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION

    upgrade = tmp_path / "upgrade-0026.db"
    initialize_database(upgrade, through=EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION)
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(upgrade)

    # The CLI refuses without the explicit single-step confirmation.
    assert migration_cli_0026.main(["--db-path", str(upgrade)]) == 2
    assert database_schema_versions(upgrade)[-1] == (
        EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION
    )

    result = migrate_0025_to_0026(upgrade)
    assert result.applied_migrations == (
        CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    )
    assert migrate_0025_to_0026(upgrade).idempotent is True
    assert migration_cli_0026.main([
        "--db-path", str(upgrade), "--confirm-0025-to-0026",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out

    routing = migrate_0026_to_0027(upgrade)
    assert routing.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)
    provenance = migrate_0027_to_0028(upgrade)
    assert provenance.applied_migrations == (
        CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    )
    catalogue = migrate_0028_to_0029(upgrade)
    assert catalogue.applied_migrations == (VERIFIED_CATALOGUE_SCHEMA_VERSION,)

    opened = SqliteStorage.open(upgrade)
    try:
        assert opened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert opened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # The widened floors exist and the offline contract is unchanged.
        triggers = {
            row[0] for row in opened.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        assert {"jobs_content_contract", "content_plans_contract",
                "content_c2_pending_approval_contract"} <= triggers
    finally:
        opened.close()


# ---------------------------------------------------------------------------
# Step 7 — one full offline chain, exercised through the paid boundary
# ---------------------------------------------------------------------------

def test_full_chain_evidence_to_paid_content_decision(
    monkeypatch, settings, storage, account,
):
    """3 admitted retrievals -> card -> lineage -> CONTENT -> paid usage."""
    job, result = _run_e3(
        monkeypatch, settings, storage, account,
        key="full-paid", urls=INDEPENDENT_URLS,
    )
    assert result.status is WorkerIterationStatus.DONE
    card = _card(storage, job)
    assert card.publication_recommendation.value == "PROCEED"

    request = ContentPreparationRequest(
        job_id="prec5r-full-paid", idempotency_key="prec5r-full-paid",
        account_id=account.id, research_card_id=int(card.id),
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    model = seed_active_article_writer(storage)
    prepared = storage.prepare_content_job(request, clock=FixedClock(NOW))
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )
    assert len(prepared.frozen_input.evidence_items) == 3
    owner = "prec5r-full-paid-owner"
    lease = storage.claim_specific_job(
        request.job_id, owner, 300, clock=FixedClock(NOW),
    )
    assert lease is not None

    writer = PaidFakeWriter()
    summary = run_offline_content_pipeline(
        lease.job, storage=storage, clock=FixedClock(NOW), lease_owner=owner,
        project_root=ROOT, policy=PolicyEngine(settings, storage, FixedClock(NOW)),
        writer=writer, lease_seconds=300,
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )

    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert writer.calls == 1
    assert summary.cost_usd == pytest.approx(EXPECTED_PAID_COST)
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["job"]["status"] == JobStatus.DONE.value
    assert len(state["decisions"]) == 1
    assert state["decisions"][0]["applied"] == 1
    assert {row["result"] for row in state["evaluations"]} == {"PASS"}
    # The ARTICLE prompt still carried the five auditable style examples.
    intent = json.loads(state["intents"][0]["intent_json"])
    assert len(intent["style_example_ids"]) == 5
    assert intent["style_example_set_fingerprint"] is not None
    # Exactly one paid usage row, settled once.
    usage = storage.conn.execute(
        "SELECT count(*),COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0", (summary.run_id,),
    ).fetchone()
    assert usage[0] == 1
    assert usage[1] == pytest.approx(EXPECTED_PAID_COST)
