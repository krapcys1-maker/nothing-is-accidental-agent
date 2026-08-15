"""Nine deterministic, local and durable C2 draft evaluations.

Five of the nine used to read a boolean the writer set about its own work.
They now read the independent assessment of the actual draft text against the
frozen Research Package; the writer's flags survive only as telemetry inside
the findings, where a divergence is itself recorded.
"""
from __future__ import annotations

from typing import Any

from app.content.contracts import (
    ArticleBrief,
    ContentBrief,
    DraftEvaluation,
    EvaluationType,
    FakeDraft,
    PipelineDecision,
)
from app.content.foundation import FrozenEvidenceItem
from app.content.quality_gate import (
    ClaimAccountingReviewPort,
    DraftQualityAssessment,
    QualityCheck,
    assess_draft,
)


_NEGATIVE_PHRASES = (
    "in today's fast-paced world",
    "here's the thing",
)


def _evaluation(
    kind: EvaluationType,
    passed: bool,
    draft: FakeDraft,
    *,
    failure_decision: PipelineDecision,
    code: str,
    findings: tuple[dict[str, Any], ...] = (),
    persist_findings_on_pass: bool = False,
) -> DraftEvaluation:
    resolved = findings if findings else ({"code": code},)
    return DraftEvaluation(
        evaluation_type=kind,
        result="PASS" if passed else "FAIL",
        score=1.0 if passed else 0.0,
        findings=(findings if passed and persist_findings_on_pass else ()) if passed else resolved,
        draft_fingerprint=draft.fingerprint(),
        decision=PipelineDecision.PASS if passed else failure_decision,
    )


def evaluate_draft(
    draft: FakeDraft,
    brief: ContentBrief,
    *,
    evidence: tuple[FrozenEvidenceItem, ...] = (),
    research_card: dict[str, Any] | None = None,
    claim_reviewer: ClaimAccountingReviewPort | None = None,
    assessment: DraftQualityAssessment | None = None,
    require_independent_review: bool | None = None,
    propagate_reviewer_errors: bool = False,
    rewrite_available: bool = False,
) -> tuple[DraftEvaluation, ...]:
    """Evaluate one draft; quality verdicts come from the text, not the writer.

    ``rewrite_available`` says whether this draft can still be rewritten, which
    is true only of attempt 1.  It never changes whether a check fails, only
    whether an unsupported claim ends the article outright or earns the single
    rewrite reviewer v3 itself asks for in that situation, and only when the
    reviewer returned a complete accounting to ask it with.  It defaults to
    ``False`` so a caller that does not reason about attempts keeps the strict
    terminal behaviour.
    """
    mandatory = (
        isinstance(brief, ArticleBrief)
        if require_independent_review is None
        else require_independent_review
    )
    verdict = assessment or assess_draft(
        draft,
        brief,
        evidence=evidence,
        research_card=research_card,
        claim_reviewer=claim_reviewer,
        require_independent_review=mandatory,
        propagate_reviewer_errors=propagate_reviewer_errors,
    )
    words = len(draft.body.split())
    required = set(brief.evidence_ids)
    observed = set(draft.evidence_ids_used)

    # Coverage still requires the brief's evidence to be declared, but a
    # declaration now only counts when the assessor found the material used.
    evidence_ok = (
        bool(required)
        and required.issubset(observed)
        and verdict.passed(QualityCheck.EVIDENCE_ID_CORRESPONDENCE)
    )
    unsupported_ok = (
        not draft.unsupported_claims
        and verdict.passed(QualityCheck.FACTUAL_CLAIM_SUPPORT)
        and verdict.passed(QualityCheck.NO_OUT_OF_CORPUS_CLAIMS)
    )
    brand_ok = brief.brand_topic_policy == "PASS"
    negative_ok = (
        not any(phrase in draft.body.lower() for phrase in _NEGATIVE_PHRASES)
        and draft.body.count("—") <= 4
    )
    # A writer asserting style_ok can no longer be the whole test; the
    # deterministic negative-profile evidence has to agree with it.
    style_ok = draft.style_ok and negative_ok
    length_ok = brief.min_words <= words <= brief.max_words
    # A writer admitting invented experience still blocks; denying it does not
    # clear anything, because only the assessment can grant this PASS.
    personal_ok = not draft.personal_experience and verdict.passed(
        QualityCheck.NO_FABRICATED_EXPERIENCE
    )
    alignment_text = (
        brief.working_title if isinstance(brief, ArticleBrief) else brief.hook
    )
    alignment_terms = {
        term.lower().strip(".,:;!?")
        for term in alignment_text.split()
        if len(term.strip(".,:;!?")) >= 5
    }
    title_terms = {term.lower().strip(".,:;!?") for term in draft.title.split()}
    alignment_ok = bool(alignment_terms & title_terms)
    compliance_ok = draft.brief_compliant and verdict.passed(
        QualityCheck.BRIEF_COMPLIANCE
    )

    telemetry = ({
        "code": "WRITER_SELF_REPORT",
        "self_report": dict(verdict.self_report),
        "divergences": list(verdict.self_report_divergences),
        "assessor_version": verdict.assessor_version,
    },)
    claim_audit = ({
        "code": "ARTICLE_CLAIM_ACCOUNTING_AUDIT",
        "reviewer_version": verdict.claim_reviewer_version,
        "coverage_complete": verdict.claim_coverage_complete,
        "claims": [dict(item) for item in verdict.claim_accounting],
    },)
    return (
        _evaluation(
            EvaluationType.EVIDENCE_COVERAGE, evidence_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="FROZEN_EVIDENCE_NOT_COVERED",
            findings=verdict.findings_for(QualityCheck.EVIDENCE_ID_CORRESPONDENCE)
            or ({"code": "FROZEN_EVIDENCE_NOT_COVERED"},),
        ),
        # Reviewer v3 answers this same question with REWRITE_ONCE on attempt 1
        # and only hardens later.  Answering it with BLOCK here made the two
        # disagree on identical evidence, so a draft the reviewer wanted
        # rewritten died instead, and the rewrite had to be driven by hand
        # through the review-only path.  The bar is unchanged: the draft still
        # fails, it just gets the attempt the reviewer already granted it.
        #
        # The rewrite is offered only when the reviewer actually delivered a
        # verdict.  An incomplete accounting means it failed, refused or never
        # answered — an unreadable answer is not an editorial opinion, and a
        # second attempt on one would be an auto-retry of a paid call after a
        # provider failure, which this project forbids outright.
        _evaluation(
            EvaluationType.UNSUPPORTED_CLAIMS, unsupported_ok, draft,
            failure_decision=(
                PipelineDecision.REWRITE_ONCE
                if rewrite_available and verdict.claim_coverage_complete
                else PipelineDecision.BLOCK
            ),
            code="UNSUPPORTED_CLAIM",
            findings=(
                verdict.findings_for(QualityCheck.FACTUAL_CLAIM_SUPPORT)
                + verdict.findings_for(QualityCheck.NO_OUT_OF_CORPUS_CLAIMS)
                + claim_audit
                + telemetry
            ),
            persist_findings_on_pass=True,
        ),
        _evaluation(
            EvaluationType.BRAND_TOPIC_POLICY, brand_ok, draft,
            failure_decision=PipelineDecision.BLOCK,
            code="BRAND_TOPIC_POLICY_FAILED",
        ),
        _evaluation(
            EvaluationType.STYLE_PROFILE, style_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="STYLE_PROFILE_FAILED",
        ),
        _evaluation(
            EvaluationType.NEGATIVE_STYLE_PROFILE, negative_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="NEGATIVE_STYLE_PATTERN",
        ),
        _evaluation(
            EvaluationType.CONTENT_TYPE_LENGTH, length_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="CONTENT_LENGTH_OUTSIDE_BRIEF",
        ),
        _evaluation(
            EvaluationType.FAKE_PERSONAL_EXPERIENCE, personal_ok, draft,
            failure_decision=PipelineDecision.BLOCK,
            code="FAKE_PERSONAL_EXPERIENCE",
            findings=(
                verdict.findings_for(QualityCheck.NO_FABRICATED_EXPERIENCE) + telemetry
            ),
        ),
        _evaluation(
            EvaluationType.TITLE_HOOK_ALIGNMENT, alignment_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="TITLE_HOOK_MISALIGNED",
        ),
        _evaluation(
            EvaluationType.BRIEF_COMPLIANCE, compliance_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="BRIEF_NONCOMPLIANCE",
            findings=verdict.findings_for(QualityCheck.BRIEF_COMPLIANCE)
            or ({"code": "BRIEF_NONCOMPLIANCE"},),
        ),
    )


def aggregate_decision(evaluations: tuple[DraftEvaluation, ...]) -> PipelineDecision:
    if len(evaluations) != len(EvaluationType) or {
        item.evaluation_type for item in evaluations
    } != set(EvaluationType):
        raise ValueError("C2 requires exactly one result for each of nine evaluations.")
    if any(item.decision is PipelineDecision.BLOCK for item in evaluations):
        return PipelineDecision.BLOCK
    if any(item.decision is PipelineDecision.REWRITE_ONCE for item in evaluations):
        return PipelineDecision.REWRITE_ONCE
    return PipelineDecision.PASS
