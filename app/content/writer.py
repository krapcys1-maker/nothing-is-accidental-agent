"""Deterministic fake writer and its narrow, auditable input contract."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.content.contracts import ArticleBrief, ContentBrief, FakeDraft, WriterIntent
from app.content.foundation import FrozenEvidenceItem


class FakeWriterScenario(str, Enum):
    PASS = "PASS"
    REWRITE_THEN_PASS = "REWRITE_THEN_PASS"
    ALWAYS_REWRITE = "ALWAYS_REWRITE"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    PERSONAL_EXPERIENCE = "PERSONAL_EXPERIENCE"


@dataclass(frozen=True)
class WriterRequest:
    intent: WriterIntent
    brief: ContentBrief
    frozen_evidence: tuple[FrozenEvidenceItem, ...]
    style_profile: str
    negative_style_profile: str
    brand_policy: str
    max_words: int
    max_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_cost_usd != 0.0:
            raise ValueError("Fake writer cost limit must be zero.")
        allowed_ids = set(self.brief.evidence_ids)
        if any(item.confirmed_claim_id not in allowed_ids for item in self.frozen_evidence):
            raise ValueError("Writer request contains evidence outside the durable brief.")


class WriterPort(Protocol):
    def write(self, request: WriterRequest) -> FakeDraft: ...


class FakeContentWriter:
    """Technical fixture only; it is not a real article or model-quality sample."""

    def __init__(self, scenario: FakeWriterScenario = FakeWriterScenario.PASS) -> None:
        self.scenario = scenario
        self.requests: list[WriterRequest] = []

    def write(self, request: WriterRequest) -> FakeDraft:
        self.requests.append(request)
        attempt_no = request.intent.attempt_no
        needs_rewrite = (
            self.scenario is FakeWriterScenario.ALWAYS_REWRITE
            or (
                self.scenario is FakeWriterScenario.REWRITE_THEN_PASS
                and attempt_no == 1
            )
        )
        evidence_ids = tuple(item.confirmed_claim_id for item in request.frozen_evidence)
        facts = [item.claim_text.rstrip(".") for item in request.frozen_evidence]
        if isinstance(request.brief, ArticleBrief):
            title = request.brief.working_title
            paragraphs = [
                f"A small visible outcome raises a larger question: {request.brief.answer_question}",
                f"The durable research card points to this thesis: {request.brief.central_thesis}",
            ]
            for index in range(6):
                fact = facts[index % len(facts)]
                paragraphs.append(
                    f"Frozen evidence {index + 1} supports a bounded part of the mechanism: "
                    f"{fact}. The point is not that one fact explains everything, but that "
                    "the same decision path keeps shaping the ordinary result."
                )
            paragraphs.extend([
                f"A serious limit remains: {request.brief.counterargument_or_limitation}",
                "Seen this way, the ordinary result is not accidental. It is the visible "
                "edge of a system of incentives, constraints, and prior choices.",
            ])
            body = "\n\n".join(paragraphs)
        else:
            title = request.brief.hook
            fact = facts[0]
            body = (
                f"{request.brief.hook}\n\n"
                f"The frozen evidence records one useful fact: {fact}. "
                f"{request.brief.main_point} That does not prove a universal rule; "
                "it identifies the specific mechanism worth noticing. The visible "
                "price is therefore the end of a decision chain, not a complete "
                "description of what the buyer must pay."
            )
        style_ok = not needs_rewrite
        brief_compliant = not needs_rewrite
        if needs_rewrite:
            body = "A vague system did something important. More detail is needed."
        unsupported: tuple[str, ...] = ()
        personal = False
        if self.scenario is FakeWriterScenario.UNSUPPORTED_CLAIM:
            unsupported = ("An unsupported invented market statistic.",)
            body += " An invented market statistic proves the conclusion."
        if self.scenario is FakeWriterScenario.PERSONAL_EXPERIENCE:
            personal = True
            body += " I remember discussing this with my family on a trip."
        return FakeDraft(
            attempt_no=attempt_no,
            route_key=request.intent.route.route_key,
            title=title,
            body=body,
            evidence_ids_used=evidence_ids if not needs_rewrite else (),
            unsupported_claims=unsupported,
            personal_experience=personal,
            style_ok=style_ok,
            brief_compliant=brief_compliant,
            rewrite_of_draft_fingerprint=request.intent.rewrite_of_draft_fingerprint,
        )
