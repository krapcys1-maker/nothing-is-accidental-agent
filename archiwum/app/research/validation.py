"""Bramka jakości Research Card (deterministyczna).

Artykuł nie przechodzi dalej, jeśli spełniona jest któraś twarda reguła odrzucenia.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.models import ResearchRecommendation, SourceVerification
from app.research.base import ResearchDraft

# Kody powodów odrzucenia
TOO_FEW_SOURCES = "TOO_FEW_SOURCES"
TOO_FEW_VERIFIED_SOURCES = "TOO_FEW_VERIFIED_SOURCES"
THESIS_UNSUPPORTED = "THESIS_UNSUPPORTED"
CLAIMS_WITHOUT_SOURCES = "CLAIMS_WITHOUT_SOURCES"
WEAK_SOURCES = "WEAK_SOURCES"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
REQUIRES_PERSONAL_EXPERIENCE = "REQUIRES_PERSONAL_EXPERIENCE"
IRRECONCILABLE_CONTRADICTIONS = "IRRECONCILABLE_CONTRADICTIONS"


@dataclass
class ValidationOutcome:
    recommendation: ResearchRecommendation
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.recommendation == ResearchRecommendation.PROCEED


def count_distinct_verified_evidence_sources(
    sources: Iterable[object],
    corpus_retrievals: Iterable[object],
) -> int:
    """E3: liczba źródeł evidence research = odrębne ZATWIERDZONE retrievale.

    Unikalna tożsamość źródła jest wyprowadzana z trwałego lineage —
    `evidence_retrieval_id` zatwierdzonego korpusu, NIE z liczby rekordów
    `sources` ani liczby excerptów. Reguły (zgodne z kontraktem E3):
    - liczą się WYŁĄCZNIE źródła `VERIFIED` (UNVERIFIED/FAILED poza count);
    - źródło musi mapować się (po `requested_url` lub `final_url`) na retrieval
      zatwierdzonego korpusu — URL spoza korpusu nie tworzy nowego źródła;
    - wiele rekordów/fragmentów wskazujących ten sam retrieval = jedno źródło;
    - różne URL-e wskazujące ten sam retrieval nie zwiększają count.
    """
    identity_by_url: dict[str, int] = {}
    for retrieval in corpus_retrievals:
        retrieval_id = getattr(retrieval, "id", None)
        if retrieval_id is None:
            continue
        for url in (
            getattr(retrieval, "requested_url", None),
            getattr(retrieval, "final_url", None),
        ):
            if isinstance(url, str) and url:
                identity_by_url[url] = int(retrieval_id)
    identities: set[int] = set()
    for source in sources:
        if getattr(source, "verification", None) != SourceVerification.VERIFIED:
            continue
        retrieval_id = identity_by_url.get(getattr(source, "url", None))
        if retrieval_id is None:
            continue
        identities.add(retrieval_id)
    return len(identities)


def validate_draft(
    draft: ResearchDraft,
    *,
    min_sources: int,
    min_confidence: float,
    min_source_quality: float,
    min_verified_sources: int = 0,
    evidence_source_count: int | None = None,
) -> ValidationOutcome:
    """`min_verified_sources` (P0-2b, docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): domyślnie 0
    (nieaktywne — zachowuje dotychczasowe zachowanie dla wywołujących, którzy tego nie
    przekazują). Gdy > 0, UNVERIFIED przestaje wystarczać do PROCEED razem z VERIFIED —
    liczą się WYŁĄCZNIE źródła faktycznie zweryfikowane (verification == VERIFIED).
    Powód: etap A2 może zwrócić UNVERIFIED, gdy nie miał dostępu do narzędzia weryfikacji
    (patrz P0-2a w pipeline.py) — bez tego progu taka karta i tak przechodziłaby bramkę."""
    reasons: list[str] = []

    sensible_sources = [s for s in draft.sources
                        if s.verification != SourceVerification.FAILED]
    # E3: dla evidence research wywołujący podaje liczbę ODRĘBNYCH zatwierdzonych
    # retrievali (evidence_source_count), bo trwały lineage source→retrieval jest
    # znany tylko tam; wiele rekordów jednego retrievalu = jedno źródło. Bez tego
    # (legacy web-search/offline) count = liczba sensownych rekordów — bez zmian.
    effective_source_count = (
        len(sensible_sources) if evidence_source_count is None
        else evidence_source_count
    )
    if effective_source_count < min_sources:
        reasons.append(TOO_FEW_SOURCES)

    if min_verified_sources > 0:
        verified_sources = [s for s in draft.sources
                            if s.verification == SourceVerification.VERIFIED]
        if len(verified_sources) < min_verified_sources:
            reasons.append(TOO_FEW_VERIFIED_SOURCES)

    if draft.requires_personal_experience:
        reasons.append(REQUIRES_PERSONAL_EXPERIENCE)

    if draft.contradictions_block:
        reasons.append(IRRECONCILABLE_CONTRADICTIONS)

    claims_with_sources = {s.supports_claim for s in sensible_sources if s.supports_claim}

    # Teza bez poparcia: brak potwierdzonych twierdzeń albo żadne potwierdzone nie ma źródła.
    if not draft.confirmed_claims:
        reasons.append(THESIS_UNSUPPORTED)
    elif not (set(draft.confirmed_claims) & claims_with_sources):
        reasons.append(THESIS_UNSUPPORTED)

    # Ważne twierdzenia bez przypisanych źródeł.
    if draft.confirmed_claims:
        missing = [c for c in draft.confirmed_claims if c not in claims_with_sources]
        if missing:
            reasons.append(CLAIMS_WITHOUT_SOURCES)

    if draft.source_quality_score < min_source_quality:
        reasons.append(WEAK_SOURCES)

    if draft.confidence_score < min_confidence:
        reasons.append(LOW_CONFIDENCE)

    recommendation = (ResearchRecommendation.PROCEED if not reasons
                      else ResearchRecommendation.REJECT)
    # Deduplikacja powodów z zachowaniem kolejności.
    seen: dict[str, None] = {}
    ordered = [r for r in reasons if not (r in seen or seen.setdefault(r, None))]
    return ValidationOutcome(recommendation=recommendation, reasons=ordered)
