"""Testy bramki jakości Research Card (walidacja)."""
from __future__ import annotations

from app.models import ResearchRecommendation, SourceType, SourceVerification
from app.research.base import ResearchPlan, SourceDraft
from app.research.fake_client import FakeResearchClient
from app.research.validation import (
    CLAIMS_WITHOUT_SOURCES,
    IRRECONCILABLE_CONTRADICTIONS,
    LOW_CONFIDENCE,
    REQUIRES_PERSONAL_EXPERIENCE,
    THESIS_UNSUPPORTED,
    TOO_FEW_SOURCES,
    TOO_FEW_VERIFIED_SOURCES,
    WEAK_SOURCES,
    validate_draft,
)

_PLAN = ResearchPlan(topic_id=1, account_id="acc", question="Why?", niche=["x"])
_THRESHOLDS = dict(min_sources=3, min_confidence=0.60, min_source_quality=0.50)


def _draft(scenario: str):
    return FakeResearchClient(scenario=scenario).run_research(_PLAN).draft


def test_good_draft_proceeds():
    outcome = validate_draft(_draft("good"), **_THRESHOLDS)
    assert outcome.passed
    assert outcome.recommendation == ResearchRecommendation.PROCEED
    assert outcome.reasons == []


def test_too_few_sources():
    outcome = validate_draft(_draft("few_sources"), **_THRESHOLDS)
    assert not outcome.passed
    assert TOO_FEW_SOURCES in outcome.reasons


def test_weak_sources():
    outcome = validate_draft(_draft("weak"), **_THRESHOLDS)
    assert WEAK_SOURCES in outcome.reasons


def test_low_confidence():
    outcome = validate_draft(_draft("low_confidence"), **_THRESHOLDS)
    assert LOW_CONFIDENCE in outcome.reasons


def test_contradictory_sources():
    outcome = validate_draft(_draft("contradictory"), **_THRESHOLDS)
    assert IRRECONCILABLE_CONTRADICTIONS in outcome.reasons


def test_thesis_unsupported():
    outcome = validate_draft(_draft("thesis_unsupported"), **_THRESHOLDS)
    assert THESIS_UNSUPPORTED in outcome.reasons


def test_requires_personal_experience():
    outcome = validate_draft(_draft("personal"), **_THRESHOLDS)
    assert REQUIRES_PERSONAL_EXPERIENCE in outcome.reasons


def test_claims_without_sources():
    draft = _draft("good")
    draft.confirmed_claims = draft.confirmed_claims + ["An unsupported extra claim"]
    outcome = validate_draft(draft, **_THRESHOLDS)
    assert CLAIMS_WITHOUT_SOURCES in outcome.reasons
    assert not outcome.passed


def test_too_few_verified_sources_rejected_even_when_not_failed():
    """P0-2b (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): UNVERIFIED (nie FAILED) źródła nie
    mogą same wystarczyć do PROCEED, gdy min_verified_sources > 0 — inaczej samoocena
    modelu (etap A2 bez dostępu do wyszukiwania) mogłaby zastąpić prawdziwy dowód."""
    draft = _draft("good")
    for s in draft.sources:
        s.verification = SourceVerification.UNVERIFIED
    outcome = validate_draft(draft, **_THRESHOLDS, min_verified_sources=3)
    assert not outcome.passed
    assert TOO_FEW_VERIFIED_SOURCES in outcome.reasons


def test_min_verified_sources_default_is_backward_compatible():
    """Domyślne zachowanie (min_verified_sources=0, jak przed naprawą) — UNVERIFIED nie
    blokuje PROCEED, gdy wywołujący jawnie nie poprosił o ten próg."""
    draft = _draft("good")
    for s in draft.sources:
        s.verification = SourceVerification.UNVERIFIED
    outcome = validate_draft(draft, **_THRESHOLDS)  # bez min_verified_sources
    assert outcome.passed
    assert TOO_FEW_VERIFIED_SOURCES not in outcome.reasons
