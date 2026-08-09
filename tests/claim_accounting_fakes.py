"""Explicit fake independent reviewers used only by offline tests."""
from __future__ import annotations

from collections.abc import Callable

from app.content.quality_gate import (
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    DraftClaimSegment,
)


class FakeClaimAccountingReviewer:
    """Account for every segment, with optional per-text test decisions."""

    reviewer_version = "fake_claim_accounting_reviewer_v1"

    def __init__(
        self,
        *,
        decide: Callable[[DraftClaimSegment, tuple[str, ...]], ClaimAccountingEntry]
        | None = None,
        omit_texts: tuple[str, ...] = (),
    ) -> None:
        self._decide = decide
        self._omit_texts = set(omit_texts)

    @staticmethod
    def _default(
        segment: DraftClaimSegment,
        evidence_ids: tuple[str, ...],
    ) -> ClaimAccountingEntry:
        text = segment.text.lower()
        if segment.text.endswith("?"):
            classification = ClaimClassification.NON_FACTUAL_PROSE
            ids: tuple[str, ...] = ()
            external = False
        elif any(marker in text for marker in (
            "i think", "i would argue", "this suggests", "the point is",
            "seen this way", "it is tempting", "perhaps", "arguably",
        )):
            classification = ClaimClassification.ARGUMENT_OR_INFERENCE
            ids = ()
            external = False
        else:
            classification = ClaimClassification.EVIDENCE_GROUNDED_FACT
            ids = evidence_ids[:1]
            external = True
        return ClaimAccountingEntry(
            segment_id=segment.segment_id,
            segment_fingerprint=segment.fingerprint,
            classification=classification,
            evidence_ids=ids,
            reason="fake reviewer confirms the selected class and scope",
            outcome=ClaimReviewOutcome.PASS,
            contains_external_fact=external,
        )

    def review(self, *, draft, brief, evidence, segments):
        del draft, brief
        evidence_ids = tuple(item.confirmed_claim_id for item in evidence)
        entries = []
        for segment in segments:
            if segment.text in self._omit_texts:
                continue
            entries.append(
                self._decide(segment, evidence_ids)
                if self._decide is not None
                else self._default(segment, evidence_ids)
            )
        return tuple(entries)

