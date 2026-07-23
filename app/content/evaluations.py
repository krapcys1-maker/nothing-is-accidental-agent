"""Nine deterministic, local and durable C2 draft evaluations."""
from __future__ import annotations

import re

from app.content.contracts import (
    ArticleBrief,
    ContentBrief,
    DraftEvaluation,
    EvaluationType,
    FakeDraft,
    PipelineDecision,
)


_PERSONAL_EXPERIENCE = re.compile(
    r"(?i)\b(i remember|my family|my childhood|when i (?:travelled|traveled|visited)|"
    r"i spoke with|a friend told me)\b"
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
) -> DraftEvaluation:
    return DraftEvaluation(
        evaluation_type=kind,
        result="PASS" if passed else "FAIL",
        score=1.0 if passed else 0.0,
        findings=() if passed else ({"code": code},),
        draft_fingerprint=draft.fingerprint(),
        decision=PipelineDecision.PASS if passed else failure_decision,
    )


def evaluate_draft(draft: FakeDraft, brief: ContentBrief) -> tuple[DraftEvaluation, ...]:
    words = len(draft.body.split())
    required = set(brief.evidence_ids)
    observed = set(draft.evidence_ids_used)
    evidence_ok = bool(required) and required.issubset(observed)
    unsupported_ok = not draft.unsupported_claims
    brand_ok = brief.brand_topic_policy == "PASS"
    style_ok = draft.style_ok
    negative_ok = (
        not any(phrase in draft.body.lower() for phrase in _NEGATIVE_PHRASES)
        and draft.body.count("—") <= 4
    )
    length_ok = brief.min_words <= words <= brief.max_words
    personal_ok = not draft.personal_experience and _PERSONAL_EXPERIENCE.search(draft.body) is None
    alignment_text = (
        brief.working_title if isinstance(brief, ArticleBrief) else brief.hook
    )
    alignment_terms = {
        term.lower().strip(".,:;!?")
        for term in alignment_text.split()
        if len(term.strip(".,:;!?")) >= 5
    }
    title_terms = {
        term.lower().strip(".,:;!?")
        for term in draft.title.split()
    }
    alignment_ok = bool(alignment_terms & title_terms)
    compliance_ok = draft.brief_compliant
    return (
        _evaluation(
            EvaluationType.EVIDENCE_COVERAGE, evidence_ok, draft,
            failure_decision=PipelineDecision.REWRITE_ONCE,
            code="FROZEN_EVIDENCE_NOT_COVERED",
        ),
        _evaluation(
            EvaluationType.UNSUPPORTED_CLAIMS, unsupported_ok, draft,
            failure_decision=PipelineDecision.BLOCK,
            code="UNSUPPORTED_CLAIM",
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
