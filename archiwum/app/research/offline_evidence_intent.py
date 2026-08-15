"""Versioned, deterministic input contract for the E2-A offline spine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.llm.base import Usage
from app.models import SourceType, SourceVerification
from app.ports.fetch import FakeFetch, FetchedDocument
from app.research.base import (
    DiscoveryResult,
    ExtractionResult,
    ResearchDraft,
    ResearchPlan,
    ResearchResult,
    SourceCandidate,
    SourceCardDraft,
    SourceDraft,
)

OFFLINE_EVIDENCE_EXECUTION = "offline_evidence_v1"
OFFLINE_EVIDENCE_INTENT_VERSION = "offline_evidence_intent_v1"


class OfflineEvidenceIntentError(ValueError):
    pass


def _exact_mapping(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise OfflineEvidenceIntentError(
            f"{label} must contain exactly: {', '.join(sorted(keys))}."
        )
    return value


@dataclass(frozen=True)
class OfflineEvidenceSource:
    url: str
    title: str
    body_utf8: str
    excerpt: str
    claim: str
    final_url: str
    http_status: int | None
    content_type: str | None
    fetch_error: str | None
    author_or_org: str | None
    published_at: str | None
    source_type: SourceType
    source_quality_score: float
    model_verification_status: SourceVerification

    @classmethod
    def from_payload(cls, raw: Any) -> "OfflineEvidenceSource":
        data = _exact_mapping(raw, {
            "url", "title", "body_utf8", "excerpt", "claim", "final_url",
            "http_status", "content_type", "fetch_error", "author_or_org",
            "published_at", "source_type", "source_quality_score",
            "model_verification_status",
        }, "offline source")
        for key in ("url", "title", "final_url", "claim", "excerpt"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise OfflineEvidenceIntentError(f"offline source {key} must be non-empty text.")
        if not isinstance(data["body_utf8"], str):
            raise OfflineEvidenceIntentError("offline source body_utf8 must be text.")
        status = data["http_status"]
        if status is not None and (
            isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599
        ):
            raise OfflineEvidenceIntentError("offline source http_status is invalid.")
        quality = data["source_quality_score"]
        if isinstance(quality, bool) or not isinstance(quality, (int, float)) or not 0 <= quality <= 1:
            raise OfflineEvidenceIntentError("offline source quality must be in [0,1].")
        try:
            source_type = SourceType(data["source_type"])
            model_status = SourceVerification(data["model_verification_status"])
        except (ValueError, TypeError) as exc:
            raise OfflineEvidenceIntentError("offline source enum is invalid.") from exc
        return cls(
            url=data["url"], title=data["title"], body_utf8=data["body_utf8"],
            excerpt=data["excerpt"], claim=data["claim"], final_url=data["final_url"],
            http_status=status, content_type=data["content_type"],
            fetch_error=data["fetch_error"], author_or_org=data["author_or_org"],
            published_at=data["published_at"], source_type=source_type,
            source_quality_score=float(quality), model_verification_status=model_status,
        )


@dataclass(frozen=True)
class OfflineEvidenceIntent:
    version: str
    sources: tuple[OfflineEvidenceSource, ...]
    synthesis: dict[str, Any]

    @classmethod
    def from_payload(cls, raw: Any) -> "OfflineEvidenceIntent":
        data = _exact_mapping(raw, {"version", "sources", "synthesis"}, "offline intent")
        if data["version"] != OFFLINE_EVIDENCE_INTENT_VERSION:
            raise OfflineEvidenceIntentError("unsupported offline evidence intent version.")
        if not isinstance(data["sources"], list) or not data["sources"]:
            raise OfflineEvidenceIntentError("offline intent requires at least one source.")
        sources = tuple(OfflineEvidenceSource.from_payload(item) for item in data["sources"])
        if len({source.url for source in sources}) != len(sources):
            raise OfflineEvidenceIntentError("offline source URLs must be unique.")
        synthesis = _exact_mapping(data["synthesis"], {
            "question", "working_thesis", "main_mechanism", "confirmed_claims",
            "uncertain_claims", "contradictions", "strongest_counterargument",
            "citable_numbers", "visual_idea", "confidence_score", "source_quality_score",
        }, "offline synthesis")
        for key in ("question", "working_thesis", "main_mechanism",
                    "strongest_counterargument", "visual_idea"):
            if not isinstance(synthesis[key], str) or not synthesis[key].strip():
                raise OfflineEvidenceIntentError(f"offline synthesis {key} must be non-empty text.")
        for key in ("confirmed_claims", "uncertain_claims", "contradictions", "citable_numbers"):
            if not isinstance(synthesis[key], list) or not all(
                isinstance(item, str) for item in synthesis[key]
            ):
                raise OfflineEvidenceIntentError(f"offline synthesis {key} must be a text list.")
        for key in ("confidence_score", "source_quality_score"):
            value = synthesis[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise OfflineEvidenceIntentError(f"offline synthesis {key} must be in [0,1].")
        return cls(version=data["version"], sources=sources, synthesis=dict(synthesis))

    def fake_fetch(self, fetched_at: datetime) -> FakeFetch:
        return FakeFetch({
            source.url: FetchedDocument(
                requested_url=source.url, final_url=source.final_url,
                fetched_at=fetched_at, http_status=source.http_status,
                content_type=source.content_type, body=source.body_utf8.encode("utf-8"),
                error=source.fetch_error,
            )
            for source in self.sources
        })


class OfflineEvidenceResearchClient:
    """Zero-token fake A1/A2/B caller backed only by the frozen job intent."""

    model = "offline-evidence-fixture"

    def __init__(self, intent: OfflineEvidenceIntent) -> None:
        self.intent = intent
        self.calls: list[str] = []
        self._by_url = {source.url: source for source in intent.sources}

    def discover_sources(self, plan: ResearchPlan, max_searches: int) -> DiscoveryResult:
        self.calls.append("A1")
        return DiscoveryResult(
            candidates=[SourceCandidate(url=s.url, title=s.title) for s in self.intent.sources],
            usage=Usage(), model=self.model,
        )

    def extract_source(
        self, plan: ResearchPlan, candidate: SourceCandidate,
    ) -> ExtractionResult:
        self.calls.append(f"A2:{candidate.url}")
        source = self._by_url[candidate.url]
        return ExtractionResult(
            card=SourceCardDraft(
                url=source.url, title=source.title,
                author_or_org=source.author_or_org, published_at=source.published_at,
                source_type=source.source_type, supported_claims=[source.claim],
                numeric_facts=[], verification=source.model_verification_status,
                source_quality_score=source.source_quality_score,
            ),
            usage=Usage(), model=self.model,
        )

    def synthesize_from_cards(
        self, plan: ResearchPlan, cards: list[SourceCardDraft],
    ) -> ResearchResult:
        self.calls.append("B")
        data = self.intent.synthesis
        return ResearchResult(
            draft=ResearchDraft(
                question=data["question"], working_thesis=data["working_thesis"],
                main_mechanism=data["main_mechanism"],
                confirmed_claims=list(data["confirmed_claims"]),
                uncertain_claims=list(data["uncertain_claims"]),
                contradictions=list(data["contradictions"]),
                strongest_counterargument=data["strongest_counterargument"],
                citable_numbers=list(data["citable_numbers"]),
                visual_idea=data["visual_idea"],
                confidence_score=float(data["confidence_score"]),
                source_quality_score=float(data["source_quality_score"]),
                sources=[
                    SourceDraft(
                        url=card.url, title=card.title or card.url,
                        author_or_org=card.author_or_org, published_at=card.published_at,
                        source_type=card.source_type,
                        supports_claim=card.supported_claims[0],
                        verification=card.verification,
                    )
                    for card in cards
                ],
            ),
            usage=Usage(), model=self.model,
        )


def canonicalize_offline_evidence_payload(payload: Any) -> dict[str, Any]:
    data = _exact_mapping(payload, {
        "account_id", "topic_id", "dry_run", "execution", "execution_intent",
    }, "offline evidence payload")
    if data["dry_run"] is not True or data["execution"] != OFFLINE_EVIDENCE_EXECUTION:
        raise OfflineEvidenceIntentError("offline evidence execution must be dry_run=true.")
    if not isinstance(data["account_id"], str) or not data["account_id"].strip():
        raise OfflineEvidenceIntentError("offline evidence account_id is invalid.")
    if isinstance(data["topic_id"], bool) or not isinstance(data["topic_id"], int):
        raise OfflineEvidenceIntentError("offline evidence topic_id is invalid.")
    OfflineEvidenceIntent.from_payload(data["execution_intent"])
    return data
