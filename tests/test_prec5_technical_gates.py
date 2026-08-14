"""PRE-C5 technical gates: independent draft quality, source admission,
E3->CONTENT lineage, paid-usage terminalization, CONTENT lease and auditable
ARTICLE style examples.

Everything here is offline: fake writers, fake callers, temporary SQLite
databases only.  No network, no SDK, no real provider, no production database.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app.content.contracts import (
    ArticleBrief,
    EvaluationType,
    FakeDraft,
    ProviderDraftPayload,
    WriterIntent,
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
from app.content.prompt import assemble_writer_prompt
from app.content.quality_gate import (
    FABRICATED_PERSONAL_EXPERIENCE,
    DraftQualityAssessment,
    QualityCheck,
    UNATTRIBUTED_SOURCE_APPEAL,
    UNSUPPORTED_FACTUAL_CLAIM,
    assess_draft,
)
from app.content.style_examples import (
    APPROVED_ARTICLE_EXAMPLES,
    STYLE_CORPUS_SHA256,
    RhetoricalFunction,
    StyleExampleError,
    default_style_corpus_path,
    load_article_style_examples,
    split_corpus_paragraphs,
)
from app.content.writer import FakeContentWriter, FakeWriterScenario
from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import (
    JobExecutionContext,
    JobKind,
    JobStatus,
    ProviderAttemptStatus,
    SourceVerification,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import StaleJobExecutionError
from app.research.source_admission import (
    CLAIM_WITHOUT_ADMITTED_EVIDENCE,
    INSUFFICIENT_SOURCE_INDEPENDENCE,
    NO_PRIMARY_SOURCE,
    ORIENTATION_ONLY_CORPUS,
    SOURCE_CLASSIFICATION_UNKNOWN,
    STALE_TIME_SENSITIVE_CORPUS,
    SYNDICATED_DUPLICATE_SOURCES,
    TOO_FEW_ADMITTED_SOURCES,
    SourceAdmissionPolicy,
    SourceClass,
    SourceDescriptor,
    evaluate_source_admission,
    is_time_sensitive,
    registrable_host,
)
from app.storage.repositories import SqliteStorage
from tests.c2_fixtures import seed_c2_research
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    ground_every_segment_in_package,
)


NOW = datetime(2026, 7, 24, 9, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shared offline helpers
# ---------------------------------------------------------------------------

def _policy(settings, storage):
    return PolicyEngine(settings, storage, FixedClock(NOW))


def _prepare_content(storage, account, *, suffix, content_type=ContentType.ARTICLE):
    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id=f"prec5-job-{suffix}",
        idempotency_key=f"prec5-intent-{suffix}",
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=content_type,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version=(
            "ARTICLE_STYLE_PROFILE_V1"
            if content_type is ContentType.ARTICLE
            else "NOTES_STYLE_PROFILE_V1_PROVISIONAL"
        ),
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"prec5-owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, 60, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, lease, owner


def _run_content(storage, settings, account, *, suffix, writer=None, **kwargs):
    request, lease, owner = _prepare_content(storage, account, suffix=suffix)
    kwargs.setdefault(
        "claim_reviewer",
        FakeClaimAccountingReviewer(decide=ground_every_segment_in_package),
    )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=_policy(settings, storage),
        writer=writer or FakeContentWriter(),
        **kwargs,
    )
    return request, lease, owner, summary


def _evidence_item(claim: str, excerpt: str, *, ordinal: int = 0) -> FrozenEvidenceItem:
    url = f"https://primary.example/{ordinal}"
    return FrozenEvidenceItem(
        ordinal=ordinal,
        account_id="nothing_is_accidental",
        topic_id=1,
        research_run_id="run-1",
        research_job_id="job-1",
        research_card_id=1,
        confirmed_claim_id=f"research-card:1:confirmed-claim:{ordinal}",
        confirmed_claim_ordinal=ordinal,
        claim_text=claim,
        claim_sha256=sha256_text(claim),
        candidate_id=ordinal + 1,
        source_id=ordinal + 1,
        source_url=url,
        source_url_sha256=sha256_text(url),
        source_claim_text=claim,
        source_claim_sha256=sha256_text(claim),
        excerpt_id=ordinal + 1,
        excerpt_text=excerpt,
        excerpt_sha256=sha256_text(excerpt),
        retrieval_id=ordinal + 1,
        requested_url_sha256=sha256_text(url),
        final_url_sha256=sha256_text(url),
        canonical_sha256=sha256_text(excerpt),
        lineage_fingerprint=sha256_text(f"lineage-{ordinal}"),
    )


def _article_brief(**overrides) -> ArticleBrief:
    payload = {
        "working_title": "Why gate assignment shapes the boarding queue",
        "central_thesis": "Gate assignment follows contractual priority.",
        "answer_question": "Who actually decides the gate?",
        "narrative_angle": "A visible outcome with an invisible cause.",
        "target_reader": "A curious traveller.",
        "concrete_opening": "The gate changes twenty minutes before boarding.",
        "argument_structure": ("observation", "mechanism", "limit"),
        "required_facts": ("contractual priority",),
        "evidence_ids": ("research-card:1:confirmed-claim:0",),
        "counterargument_or_limitation": "Weather still overrides contracts.",
        "ending": "The ordinary result is not accidental.",
        "min_words": 100,
        "max_words": 1200,
        "forbidden_claims": ("airlines never publish gate rules",),
    }
    payload.update(overrides)
    return ArticleBrief(**payload)


def _draft(body: str, **overrides) -> FakeDraft:
    payload = {
        "attempt_no": 1,
        "route_key": "FABLE_5_ARTICLE",
        "title": "Why gate assignment shapes the boarding queue",
        "body": body,
        "evidence_ids_used": ("research-card:1:confirmed-claim:0",),
        "unsupported_claims": (),
        "personal_experience": False,
        "style_ok": True,
        "brief_compliant": True,
    }
    payload.update(overrides)
    return FakeDraft(**payload)


CLAIM = "Airport gate assignment follows contractual priority, not convenience."
EXCERPT = (
    "Gate assignment at large hubs follows contractual priority agreed with "
    "carriers, not passenger convenience."
)
GOOD_BODY = (
    "The gate changes twenty minutes before boarding and nobody explains why.\n\n"
    "Airport gate assignment follows contractual priority, not convenience. "
    "The carrier agreement decides which airline reaches which pier, and the "
    "boarding queue is the visible end of that arrangement.\n\n"
    "Weather still overrides contracts, so the rule is a tendency rather than "
    "a guarantee. The ordinary result is not accidental."
)


# ---------------------------------------------------------------------------
# PRE5-MAJ-01 — the writer's self-report can no longer grant a PASS
# ---------------------------------------------------------------------------

def test_clean_draft_still_passes_the_independent_assessment():
    verdict = assess_draft(
        _draft(GOOD_BODY),
        _article_brief(),
        evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert all(verdict.checks.values())
    assert verdict.self_report_divergences == ()


def test_unsupported_statistic_is_rejected_despite_empty_self_report():
    body = GOOD_BODY + (
        "\n\nGate reassignment raises missed connections by 37 percent across "
        "the industry, according to a recent study of boarding data."
    )
    draft = _draft(body, unsupported_claims=())
    verdict = assess_draft(
        draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert verdict.passed(QualityCheck.FACTUAL_CLAIM_SUPPORT) is False
    codes = {item["code"] for item in verdict.findings}
    assert UNSUPPORTED_FACTUAL_CLAIM in codes
    assert UNATTRIBUTED_SOURCE_APPEAL in codes
    assert "unsupported_claims" in verdict.self_report_divergences

    evaluations = evaluate_draft(
        draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    unsupported = next(
        item for item in evaluations
        if item.evaluation_type is EvaluationType.UNSUPPORTED_CLAIMS
    )
    assert unsupported.result == "FAIL"
    assert aggregate_decision(evaluations).value == "BLOCK"


def test_unsupported_claim_earns_one_rewrite_before_it_blocks():
    """One draft, two answers, decided only by whether a rewrite is left.

    Reviewer v3 answers this question with REWRITE_ONCE on attempt 1 while the
    C2 aggregate used to answer BLOCK on identical evidence.  That disagreement
    ended articles the reviewer had explicitly asked to rewrite, and forced the
    rewrite through the manual review-only path instead.
    """
    body = GOOD_BODY + (
        "\n\nGate reassignment raises missed connections by 37 percent across "
        "the industry, according to a recent study of boarding data."
    )
    draft = _draft(body, unsupported_claims=())

    def _evaluate(*, rewrite_available: bool):
        return evaluate_draft(
            draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
            rewrite_available=rewrite_available,
        )

    first_attempt = _evaluate(rewrite_available=True)
    later_attempt = _evaluate(rewrite_available=False)

    decisions = {}
    for label, evaluations in (
        ("first", first_attempt), ("later", later_attempt),
    ):
        unsupported = next(
            item for item in evaluations
            if item.evaluation_type is EvaluationType.UNSUPPORTED_CLAIMS
        )
        # The bar never moves: the draft fails the check either way.
        assert unsupported.result == "FAIL"
        decisions[label] = unsupported.decision.value

    assert decisions == {"first": "REWRITE_ONCE", "later": "BLOCK"}
    assert aggregate_decision(first_attempt).value == "REWRITE_ONCE"
    assert aggregate_decision(later_attempt).value == "BLOCK"


@pytest.mark.parametrize("coverage_complete", [True, False])
def test_rewrite_is_never_granted_on_an_unreadable_review(coverage_complete):
    """A reviewer that did not answer must not buy the draft a second call.

    An incomplete claim accounting is what a refused, malformed or failed
    review looks like from here.  Treating it as an editorial "rewrite this"
    would turn a provider failure into an automatic retry of a paid call, on
    attempt 1, with no human in the loop.
    """
    draft = _draft(GOOD_BODY, unsupported_claims=())
    assessment = DraftQualityAssessment(
        assessor_version="test_assessor",
        draft_fingerprint=draft.fingerprint(),
        checks={check: True for check in QualityCheck}
        | {QualityCheck.NO_OUT_OF_CORPUS_CLAIMS: False},
        findings=(),
        self_report={},
        self_report_divergences=(),
        claim_coverage_complete=coverage_complete,
    )
    evaluations = evaluate_draft(
        draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
        assessment=assessment,
        rewrite_available=True,
    )
    unsupported = next(
        item for item in evaluations
        if item.evaluation_type is EvaluationType.UNSUPPORTED_CLAIMS
    )
    assert unsupported.result == "FAIL"
    # Same failing check, same attempt number; only the reviewer's ability to
    # answer differs, and only a real answer earns the rewrite.
    assert unsupported.decision.value == (
        "REWRITE_ONCE" if coverage_complete else "BLOCK"
    )


def test_invented_personal_story_is_rejected_despite_false_self_report():
    body = GOOD_BODY + (
        "\n\nI remember waiting at that pier with my family last summer, and "
        "a friend told me the gate had been swapped twice."
    )
    draft = _draft(body, personal_experience=False)
    verdict = assess_draft(
        draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert verdict.passed(QualityCheck.NO_FABRICATED_EXPERIENCE) is False
    assert FABRICATED_PERSONAL_EXPERIENCE in {
        item["code"] for item in verdict.findings
    }
    assert "personal_experience" in verdict.self_report_divergences

    evaluations = evaluate_draft(
        draft, _article_brief(), evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    personal = next(
        item for item in evaluations
        if item.evaluation_type is EvaluationType.FAKE_PERSONAL_EXPERIENCE
    )
    assert personal.result == "FAIL"
    assert aggregate_decision(evaluations).value == "BLOCK"


def test_first_person_reasoning_is_not_treated_as_lived_experience():
    body = GOOD_BODY + (
        "\n\nI think the contractual explanation is the more plausible one, "
        "and I doubt convenience plays any part."
    )
    verdict = assess_draft(
        _draft(body), _article_brief(),
        evidence=(_evidence_item(CLAIM, EXCERPT),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert verdict.passed(QualityCheck.NO_FABRICATED_EXPERIENCE) is True


@pytest.mark.parametrize(
    "missing",
    ["unsupported_claims", "personal_experience", "style_ok", "brief_compliant"],
)
def test_missing_quality_output_field_is_fail_closed(missing):
    payload = {
        "title": "A title",
        "body": "A body.",
        "evidence_ids_used": [],
        "unsupported_claims": [],
        "personal_experience": False,
        "style_ok": True,
        "brief_compliant": True,
    }
    payload.pop(missing)
    with pytest.raises(Exception) as excinfo:
        ProviderDraftPayload.model_validate(payload)
    assert "missing" in str(excinfo.value).lower()

    draft_payload = dict(payload)
    draft_payload.update({"attempt_no": 1, "route_key": "FABLE_5_ARTICLE"})
    with pytest.raises(Exception):
        FakeDraft(**draft_payload)


def test_declared_evidence_id_absent_from_the_draft_is_rejected():
    unrelated = _evidence_item(
        "Municipal recycling contracts are renegotiated every seven years.",
        "Municipal recycling contracts run on a seven-year renegotiation cycle.",
    )
    brief = _article_brief(evidence_ids=(unrelated.confirmed_claim_id,))
    draft = _draft(GOOD_BODY, evidence_ids_used=(unrelated.confirmed_claim_id,))
    verdict = assess_draft(
        draft, brief, evidence=(unrelated,),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert verdict.passed(QualityCheck.EVIDENCE_ID_CORRESPONDENCE) is False

    evaluations = evaluate_draft(
        draft, brief, evidence=(unrelated,),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    coverage = next(
        item for item in evaluations
        if item.evaluation_type is EvaluationType.EVIDENCE_COVERAGE
    )
    assert coverage.result == "FAIL"


def test_writer_scenarios_are_blocked_end_to_end(storage, settings, account):
    # Both end the article, and the reason code says which kind of failure it
    # was. An unsupported claim is fixable in principle, so the pipeline buys
    # rewrites until the reviewer's list stops getting shorter - this writer
    # repeats itself, so it stalls and exhausts. Fabricated experience is not
    # fixable by rewriting and is blocked outright on the first look.
    for suffix, scenario, block_code in (
        ("unsupported", FakeWriterScenario.UNSUPPORTED_CLAIM,
         "CONTENT_REWRITE_LIMIT_EXHAUSTED"),
        ("personal", FakeWriterScenario.PERSONAL_EXPERIENCE,
         "CONTENT_EVALUATION_BLOCKED"),
    ):
        _, _, _, summary = _run_content(
            storage, settings, account, suffix=suffix,
            writer=FakeContentWriter(scenario),
        )
        assert summary.status is ContentStatus.FAILED
        assert summary.block_code == block_code


# ---------------------------------------------------------------------------
# PRE5-MAJ-02 — deterministic source admission
# ---------------------------------------------------------------------------

def _source(url, *, klass=SourceClass.SUPPORTING, retrieval_id=1, claim=CLAIM,
            digest=None, published=None, syndication=None):
    return SourceDescriptor(
        url=url,
        retrieval_id=retrieval_id,
        source_class=klass,
        content_sha256=digest,
        published_at=published,
        syndication_of=syndication,
        supports_claim=claim,
    )


def test_registrable_host_collapses_subdomains_and_public_suffixes():
    assert registrable_host("https://www.example.com/a") == "example.com"
    assert registrable_host("https://news.example.com/b") == "example.com"
    assert registrable_host("https://a.example.co.uk/c") == "example.co.uk"


def test_admitted_corpus_with_independent_owners_and_a_primary_source():
    outcome = evaluate_source_admission(
        [
            _source("https://regulator.example/filing", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest="a" * 64),
            _source("https://press.example/report", retrieval_id=2, digest="b" * 64),
            _source("https://journal.example/paper", retrieval_id=3, digest="c" * 64),
        ],
        confirmed_claims=[CLAIM],
    )
    assert outcome.admitted is True
    assert outcome.reasons == ()
    assert outcome.independent_owner_count == 3
    assert len(outcome.policy_fingerprint) == 64


def test_three_retrievals_from_one_domain_are_not_three_independent_sources():
    outcome = evaluate_source_admission(
        [
            _source("https://news.example.com/a", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest="a" * 64),
            _source("https://www.example.com/b", retrieval_id=2, digest="b" * 64),
            _source("https://blog.example.com/c", retrieval_id=3, digest="c" * 64),
        ],
        confirmed_claims=[CLAIM],
    )
    assert outcome.admitted is False
    assert INSUFFICIENT_SOURCE_INDEPENDENCE in outcome.reasons
    assert outcome.independent_owner_count == 1


def test_syndicated_and_duplicate_material_cannot_inflate_the_evidence_count():
    shared = "d" * 64
    outcome = evaluate_source_admission(
        [
            _source("https://origin.example/story", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest=shared),
            # Identical canonical text under a different owner.
            _source("https://reprint.example/story", retrieval_id=2, digest=shared),
            # Declared syndication of the first owner.
            _source("https://partner.example/story", retrieval_id=3,
                    digest="e" * 64, syndication="origin.example"),
        ],
        confirmed_claims=[CLAIM],
    )
    # A duplicate is collapsed and recorded, not held against the corpus: what
    # must not happen is it counting towards the evidence, and it does not.
    assert outcome.admitted is False
    assert TOO_FEW_ADMITTED_SOURCES in outcome.reasons
    assert SYNDICATED_DUPLICATE_SOURCES not in outcome.reasons
    assert any(
        item.get("code") == SYNDICATED_DUPLICATE_SOURCES
        and item.get("url") == "https://reprint.example/story"
        for item in outcome.findings
    )
    # The reprint collapsed into the origin; the partner kept the origin's key.
    assert outcome.independent_owner_count == 1
    assert len(outcome.admitted_sources) == 2


def test_wikipedia_only_corpus_cannot_satisfy_independent_evidence():
    outcome = evaluate_source_admission(
        [
            _source("https://en.wikipedia.org/wiki/Gate", retrieval_id=1,
                    klass=SourceClass.PRIMARY, digest="a" * 64),
            _source("https://simple.wikipedia.org/wiki/Airport", retrieval_id=2,
                    klass=SourceClass.SUPPORTING, digest="b" * 64),
            _source("https://britannica.com/airport", retrieval_id=3,
                    klass=SourceClass.PRIMARY, digest="c" * 64),
        ],
        confirmed_claims=[CLAIM],
    )
    assert outcome.admitted is False
    assert ORIENTATION_ONLY_CORPUS in outcome.reasons
    assert NO_PRIMARY_SOURCE in outcome.reasons
    # A declared PRIMARY class never survives the orientation host cap.
    assert {item.source_class for item in outcome.admitted_sources} == {
        SourceClass.ORIENTATION
    }


def test_time_sensitive_claims_require_at_least_one_fresh_source():
    stale = NOW - timedelta(days=2000)
    descriptors = [
        _source("https://regulator.example/filing", klass=SourceClass.PRIMARY,
                retrieval_id=1, digest="a" * 64, published=stale,
                claim="Gate delays are currently at a record high."),
        _source("https://press.example/report", retrieval_id=2, digest="b" * 64,
                published=stale,
                claim="Gate delays are currently at a record high."),
        _source("https://journal.example/paper", retrieval_id=3, digest="c" * 64,
                published=stale,
                claim="Gate delays are currently at a record high."),
    ]
    claims = ["Gate delays are currently at a record high."]
    assert is_time_sensitive(claims) is True
    stale_outcome = evaluate_source_admission(
        descriptors, confirmed_claims=claims, now=NOW,
    )
    assert stale_outcome.admitted is False
    assert STALE_TIME_SENSITIVE_CORPUS in stale_outcome.reasons

    fresh = [
        replace(descriptors[0], published_at=NOW - timedelta(days=30)),
        descriptors[1],
        descriptors[2],
    ]
    fresh_outcome = evaluate_source_admission(
        fresh, confirmed_claims=claims, now=NOW,
    )
    assert fresh_outcome.admitted is True

    # The same stale corpus is fine for a claim that does not decay.
    timeless = evaluate_source_admission(
        [replace(item, supports_claim=CLAIM) for item in descriptors],
        confirmed_claims=[CLAIM], now=NOW,
    )
    assert timeless.admitted is True


def test_unknown_source_classification_fails_closed():
    outcome = evaluate_source_admission(
        [
            _source("https://regulator.example/filing", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest="a" * 64),
            _source("https://press.example/report", retrieval_id=2, digest="b" * 64),
            _source("https://mystery.example/page", klass=None, retrieval_id=3,
                    digest="c" * 64),
        ],
        confirmed_claims=[CLAIM],
    )
    # An unclassified source is dropped rather than counted, so this corpus
    # still fails - on the source floor, which is the honest reason. It does not
    # condemn a corpus that has enough admitted sources without it.
    assert outcome.admitted is False
    assert TOO_FEW_ADMITTED_SOURCES in outcome.reasons
    assert SOURCE_CLASSIFICATION_UNKNOWN not in outcome.reasons
    assert any(
        item.get("code") == SOURCE_CLASSIFICATION_UNKNOWN
        and item.get("url") == "https://mystery.example/page"
        for item in outcome.findings
    )

    # The same unclassified source alongside a sufficient corpus is admitted.
    survives = evaluate_source_admission(
        [
            _source("https://regulator.example/filing", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest="a" * 64),
            _source("https://press.example/report", retrieval_id=2, digest="b" * 64),
            _source("https://journal.example/paper", retrieval_id=3, digest="c" * 64),
            _source("https://mystery.example/page", klass=None, retrieval_id=4,
                    digest="d" * 64),
        ],
        confirmed_claims=[CLAIM],
    )
    assert survives.admitted is True
    assert all(item.url != "https://mystery.example/page" for item in survives.admitted_sources)


def test_every_confirmed_claim_needs_admitted_evidence():
    outcome = evaluate_source_admission(
        [
            _source("https://regulator.example/filing", klass=SourceClass.PRIMARY,
                    retrieval_id=1, digest="a" * 64),
            _source("https://press.example/report", retrieval_id=2, digest="b" * 64),
            _source("https://journal.example/paper", retrieval_id=3, digest="c" * 64),
        ],
        confirmed_claims=[CLAIM, "A second claim nobody sourced."],
    )
    assert outcome.admitted is False
    assert CLAIM_WITHOUT_ADMITTED_EVIDENCE in outcome.reasons


def test_holding_three_retrieval_ids_alone_is_not_admission():
    policy = SourceAdmissionPolicy()
    outcome = evaluate_source_admission(
        [
            _source("https://example.com/a", retrieval_id=1, digest="a" * 64),
            _source("https://example.com/b", retrieval_id=2, digest="b" * 64),
            _source("https://example.com/c", retrieval_id=3, digest="c" * 64),
        ],
        confirmed_claims=[CLAIM],
        policy=policy,
    )
    assert len(outcome.admitted_sources) == 3
    assert outcome.admitted is False
    assert NO_PRIMARY_SOURCE in outcome.reasons
    assert INSUFFICIENT_SOURCE_INDEPENDENCE in outcome.reasons


# ---------------------------------------------------------------------------
# ARTICLE style examples
# ---------------------------------------------------------------------------

def test_approved_examples_resolve_against_the_reviewed_corpus():
    corpus = default_style_corpus_path(ROOT)
    examples = load_article_style_examples(corpus)
    assert examples.corpus_sha256 == STYLE_CORPUS_SHA256
    assert examples.corpus_bytes == 57561
    assert 3 <= len(examples.examples) <= 5
    assert [item.rhetorical_function for item in examples.examples] == [
        RhetoricalFunction.OPENING,
        RhetoricalFunction.CONCRETE_TO_SYSTEM,
        RhetoricalFunction.MECHANISM,
        RhetoricalFunction.COUNTERARGUMENT,
        RhetoricalFunction.ENDING,
    ]
    for example in examples.examples:
        assert example.example_id.startswith("ASV1-P")
        assert example.text_sha256 == sha256_text(example.text)
        assert 150 <= example.chars <= 900
    assert len(examples.fingerprint()) == 64
    # The fingerprint is stable across reads of the same corpus.
    assert load_article_style_examples(corpus).fingerprint() == examples.fingerprint()


def test_example_ids_are_reproducible_from_the_corpus_bytes():
    raw = default_style_corpus_path(ROOT).read_bytes()
    paragraphs = split_corpus_paragraphs(raw)
    for _, ordinal, digest_prefix in APPROVED_ARTICLE_EXAMPLES:
        assert sha256_text(paragraphs[ordinal])[:10] == digest_prefix


def test_drifted_corpus_or_ordinal_fails_closed(tmp_path):
    forged = tmp_path / "forged.txt"
    forged.write_bytes(b"a paragraph\n\nanother paragraph\n")
    with pytest.raises(StyleExampleError) as excinfo:
        load_article_style_examples(forged)
    assert excinfo.value.code == "STYLE_CORPUS_UNAPPROVED"

    corpus = default_style_corpus_path(ROOT)
    with pytest.raises(StyleExampleError) as drifted:
        load_article_style_examples(
            corpus,
            selection=(
                (RhetoricalFunction.OPENING, 65, "0000000000"),
                (RhetoricalFunction.MECHANISM, 60, "39432e9c97"),
                (RhetoricalFunction.ENDING, 76, "17d1efd98e"),
            ),
        )
    assert drifted.value.code == "STYLE_EXAMPLE_CONTENT_DRIFTED"

    with pytest.raises(StyleExampleError) as too_few:
        load_article_style_examples(
            corpus, selection=((RhetoricalFunction.OPENING, 65, "974f069d90"),),
        )
    assert too_few.value.code == "STYLE_EXAMPLE_COUNT_INVALID"


def test_raw_corpus_never_reaches_the_prompt(storage, settings, account):
    request, _, _, summary = _run_content(
        storage, settings, account, suffix="style-prompt",
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    state = storage.get_content_pipeline_state(request.job_id)
    intent = json.loads(state["intents"][0]["intent_json"])

    examples = load_article_style_examples(default_style_corpus_path(ROOT))
    assert intent["style_corpus_id"] == examples.corpus_id
    assert intent["style_corpus_sha256"] == examples.corpus_sha256
    assert intent["style_example_ids"] == list(examples.example_ids)
    assert intent["style_example_set_fingerprint"] == examples.fingerprint()

    raw = default_style_corpus_path(ROOT).read_text(encoding="utf-8")
    paragraphs = split_corpus_paragraphs(raw.encode("utf-8"))
    selected = {item.text for item in examples.examples}
    unselected = [text for text in paragraphs if text not in selected]

    persisted = json.dumps(
        {
            "intent": intent,
            "result": json.loads(state["results"][0]["result_json"]),
            "draft": json.loads(state["drafts"][0]["draft_json"]),
        }
    )
    assert raw not in persisted
    for text in unselected:
        assert text not in persisted
    # Only the five short reviewed fragments are shareable at all.
    assert sum(len(item.text) for item in examples.examples) < 2600


def test_note_attempts_carry_no_style_examples(storage, settings, account):
    request, lease, owner = _prepare_content(
        storage, account, suffix="note-style", content_type=ContentType.NOTE,
    )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        policy=_policy(settings, storage),
        writer=FakeContentWriter(),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    state = storage.get_content_pipeline_state(request.job_id)
    intent = json.loads(state["intents"][0]["intent_json"])
    assert intent["style_example_ids"] == []
    assert intent["style_corpus_sha256"] is None


def test_note_intent_cannot_declare_article_style_examples():
    from app.llm.anthropic_provider_contract import NOTE_WRITER_INFERENCE_CONFIG

    with pytest.raises(ValueError, match="ARTICLE"):
        WriterIntent(
            intent_id="x", job_id="j", run_id="r", content_id=1,
            account_id="a", content_type=ContentType.NOTE, attempt_no=1,
            route=_route_note(), plan_fingerprint="a" * 64,
            brief_sha256="b" * 64, frozen_input_sha256="c" * 64,
            evidence_manifest_sha256="d" * 64,
            style_profile_id="NOTES_STYLE_PROFILE_V1_PROVISIONAL",
            negative_style_profile_id="ARTICLE_NEGATIVE_STYLE_PROFILE_V1",
            prompt_fingerprint="e" * 64,
            inference_config=NOTE_WRITER_INFERENCE_CONFIG,
            limits=_zero_limits(),
            style_corpus_id="article_style_samples_v1",
            style_corpus_sha256="f" * 64,
            style_example_ids=("ASV1-P065-974f069d90", "ASV1-P060-39432e9c97",
                               "ASV1-P076-17d1efd98e"),
            style_example_set_fingerprint="0" * 64,
        )


def _route_note():
    from app.content.contracts import RouteContract

    return RouteContract(
        content_type=ContentType.NOTE,
        route_key="SONNET_5_NOTE",
        logical_model_name="Sonnet 5",
        config_version="v1",
        config_fingerprint="a" * 64,
    )


def _zero_limits():
    from app.content.contracts import WriterLimits

    return WriterLimits(
        max_input_tokens=100, max_context_tokens=200, max_output_tokens=50,
        max_cost_usd=0.0, timeout_seconds=1.0,
    )
