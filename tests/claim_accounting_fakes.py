"""Explicit fake independent reviewers used only by offline tests.

The fake never infers semantics from segment text.  Every PASS-producing
decision is selected explicitly by the test; an omitted profile yields an
UNKNOWN/BLOCK entry.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Mapping

from app.content.quality_gate import (
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    DraftClaimSegment,
    SegmentKind,
)


@dataclass(frozen=True)
class SegmentDecision:
    """A semantic decision selected explicitly by an offline test."""

    classification: ClaimClassification
    evidence_ids: tuple[str, ...]
    reason: str
    outcome: ClaimReviewOutcome
    contains_external_fact: bool | None

    def bind(self, segment: DraftClaimSegment) -> ClaimAccountingEntry:
        return ClaimAccountingEntry(
            segment_id=segment.segment_id,
            segment_fingerprint=segment.fingerprint,
            classification=self.classification,
            evidence_ids=self.evidence_ids,
            reason=self.reason,
            outcome=self.outcome,
            contains_external_fact=self.contains_external_fact,
        )


def grounded_fact(*evidence_ids: str) -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
        evidence_ids=tuple(evidence_ids),
        reason="reviewer bound this fact to the frozen evidence package",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=True,
    )


def title_framing() -> SegmentDecision:
    """A heading that names the article's subject without asserting a new fact."""
    return SegmentDecision(
        classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
        evidence_ids=(),
        reason="heading names the article's subject",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=False,
    )


def external_fact_without_evidence() -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
        evidence_ids=(),
        reason="reviewer found an external fact without supporting evidence",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=True,
    )


def external_fact_as_inference() -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
        evidence_ids=(),
        reason="reviewer found an external fact inside an inference",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=True,
    )


def honest_inference() -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
        evidence_ids=(),
        reason="reviewer confirmed an inference without an external fact",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=False,
    )


def real_prose() -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.NON_FACTUAL_PROSE,
        evidence_ids=(),
        reason="reviewer confirmed non-factual prose",
        outcome=ClaimReviewOutcome.PASS,
        contains_external_fact=False,
    )


def _unknown_blocked() -> SegmentDecision:
    return SegmentDecision(
        classification=ClaimClassification.UNKNOWN,
        evidence_ids=(),
        reason="no explicit fake semantic profile was supplied",
        outcome=ClaimReviewOutcome.BLOCK,
        contains_external_fact=None,
    )


def ground_every_segment_in_package(
    segment: DraftClaimSegment,
    evidence_ids: tuple[str, ...],
) -> ClaimAccountingEntry:
    """Explicit compatibility profile for tests about non-semantic machinery."""
    return grounded_fact(*evidence_ids).bind(segment)


class FakeClaimAccountingReviewer:
    """Bind explicit per-text decisions; missing decisions fail closed."""

    reviewer_version = "fake_claim_accounting_reviewer_v2"

    def __init__(
        self,
        *,
        decide: Callable[[DraftClaimSegment, tuple[str, ...]], ClaimAccountingEntry]
        | None = None,
        profile: Mapping[str, SegmentDecision] | None = None,
        default: SegmentDecision | None = None,
        omit_texts: tuple[str, ...] = (),
    ) -> None:
        if decide is not None and (profile is not None or default is not None):
            raise ValueError("decide cannot be combined with profile/default")
        self._decide = decide
        self._profile = dict(profile or {})
        self._default = default
        self._omit_texts = set(omit_texts)

    def review(self, *, draft, brief, evidence, segments):
        del draft, brief
        evidence_ids = tuple(item.confirmed_claim_id for item in evidence)
        entries = []
        for segment in segments:
            if segment.text in self._omit_texts:
                continue
            explicit = self._profile.get(segment.text)
            if explicit is not None:
                entries.append(explicit.bind(segment))
                continue
            # Title and subtitle became reviewable segments after the first
            # REVIEW-ONLY live.  A test that drives body-sentence semantics
            # (via decide or a text profile) gets a neutral passing heading so
            # its assertions stay about the body.  A fake with neither still
            # fails closed on every segment, headings included.
            if segment.kind is not SegmentKind.BODY and (
                self._decide is not None or self._profile
            ):
                entries.append(title_framing().bind(segment))
                continue
            if self._decide is not None:
                entries.append(self._decide(segment, evidence_ids))
                continue
            entries.append((self._default or _unknown_blocked()).bind(segment))
        return tuple(entries)

