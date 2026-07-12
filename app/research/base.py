"""Kontrakt researchu i typy danych (draft przed walidacją)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.llm.base import Usage
from app.models import SourceType, SourceVerification


class ResearchError(RuntimeError):
    """Ogólny błąd researchu.

    Może nieść realne `usage`/`model`, jeśli błąd wystąpił PO udanym wywołaniu API
    (np. odpowiedź przyszła, ale JSON był niepoprawny/ucięty) — dzięki temu pipeline
    może zaksięgować rzeczywisty koszt, nawet gdy research się nie powiódł.

    `raw_text`/`stop_reason` (od 2026-07-12, stabilizacja Stage A1/A2/B) niosą
    analogicznie surową odpowiedź modelu i powód zatrzymania generacji — bez tego
    dwa dotychczasowe incydenty ucięcia JSON-a dawały tylko HIPOTEZĘ przyczyny
    (np. "prawdopodobnie max_tokens"), bo surowa odpowiedź nigdzie się nie zapisywała.
    Patrz app/research/diagnostics.py.
    """

    def __init__(self, message: str, *, usage: Usage | None = None,
                 model: str | None = None, raw_text: str | None = None,
                 stop_reason: str | None = None) -> None:
        super().__init__(message)
        self.usage = usage
        self.model = model
        self.raw_text = raw_text
        self.stop_reason = stop_reason


class ResearchTimeout(ResearchError):
    """Przekroczono czas wywołania (transient — podlega ograniczonemu retry)."""


class ResearchParseError(ResearchError):
    """Model zwrócił niepoprawny JSON (NIE ponawiamy — to nie jest błąd transient)."""


@dataclass
class ResearchPlan:
    topic_id: int
    account_id: str
    question: str
    niche: list[str] = field(default_factory=list)
    required_depth: str = "standard"
    guidance: str = ""


@dataclass
class SourceDraft:
    url: str
    title: str
    author_or_org: str | None = None
    published_at: str | None = None
    source_type: SourceType = SourceType.OTHER
    supports_claim: str | None = None
    verification: SourceVerification = SourceVerification.UNVERIFIED


@dataclass
class ResearchDraft:
    question: str
    working_thesis: str
    main_mechanism: str | None = None
    confirmed_claims: list[str] = field(default_factory=list)
    uncertain_claims: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    strongest_counterargument: str | None = None
    citable_numbers: list[str] = field(default_factory=list)
    visual_idea: str | None = None
    confidence_score: float = 0.0
    source_quality_score: float = 0.0
    requires_personal_experience: bool = False
    contradictions_block: bool = False      # źródła poważnie sobie przeczą i nie da się uczciwie opisać
    sources: list[SourceDraft] = field(default_factory=list)


@dataclass
class ResearchResult:
    draft: ResearchDraft
    usage: Usage
    model: str
    raw_text: str = ""              # surowa odpowiedź modelu, dla diagnostyki (puste w Fake/dry_run)
    stop_reason: str | None = None


# --- Dwuetapowy research (od 2026-07-11, patrz docs/DECISIONS.md ADR-016) ---
# Etap 1: gather_sources — TYLKO web search + wyodrębnienie źródeł i krótkich,
#   surowych faktów (bez analizy). Lekki schemat -> mniejsze ryzyko ucięcia JSON-a,
#   tańsza kontrola jakości PRZED opłaceniem syntezy (etap 2).
# Etap 2: synthesize_card — TYLKO synteza (teza, mechanizm, sprzeczności,
#   confidence) na bazie już zebranych źródeł. Zero web search -> input pod naszą
#   kontrolą, nie surowe wyniki wyszukiwania.

@dataclass
class GatheredSource:
    url: str
    title: str
    author_or_org: str | None = None
    published_at: str | None = None
    source_type: SourceType = SourceType.OTHER
    key_facts: list[str] = field(default_factory=list)   # surowe fakty, jeszcze bez analizy
    verification: SourceVerification = SourceVerification.UNVERIFIED


@dataclass
class SourceGatheringResult:
    sources: list[GatheredSource]
    usage: Usage
    model: str


# --- Etapowy research A1/A2/B (od 2026-07-12, patrz docs/DECISIONS.md ADR-020) ---
# Powód: gather_sources (etap "A" powyżej) nadal zwracał JEDEN duży JSON obejmujący
# WSZYSTKIE źródła naraz — drugi realny test (2026-07-12) pokazał, że to wciąż za
# kruche (ucięcie przy 4 źródłach, mimo lekkiego schematu). Nowy podział:
#   A1 (discover_sources): TYLKO web search + lista kandydatów URL (url+title,
#     JSONL — jeden kandydat na linię, bez analizy). Najlżejszy możliwy schemat.
#   A2 (extract_source): JEDNO źródło na wywołanie — pełna analiza (autor, data,
#     2-4 twierdzenia, fakty liczbowe, ocena jakości). Zapisywane do bazy
#     NATYCHMIAST po każdym źródle — awaria na źródle N nie kasuje 1..N-1.
#   B (synthesize_from_cards): jak dawniej `synthesize_card`, ale na bazie
#     bogatszych SourceCardDraft zamiast surowych GatheredSource. Zero web search.

@dataclass
class SourceCandidate:
    """Wynik etapu A1 — jeszcze NIE jest Source Card, tylko wskazówka do sprawdzenia."""
    url: str
    title: str | None = None


@dataclass
class DiscoveryResult:
    candidates: list[SourceCandidate]
    usage: Usage
    model: str
    raw_text: str = ""
    stop_reason: str | None = None


@dataclass
class SourceCardDraft:
    """Pełny wynik etapu A2 dla JEDNEGO źródła — wzbogacony SourceCandidate."""
    url: str
    title: str | None = None
    author_or_org: str | None = None
    published_at: str | None = None
    source_type: SourceType = SourceType.OTHER
    supported_claims: list[str] = field(default_factory=list)
    numeric_facts: list[str] = field(default_factory=list)   # liczba WRAZ z kontekstem, nie sama liczba
    verification: SourceVerification = SourceVerification.UNVERIFIED
    source_quality_score: float = 0.0
    extraction_error: str | None = None


@dataclass
class ExtractionResult:
    card: SourceCardDraft
    usage: Usage
    model: str
    raw_text: str = ""
    stop_reason: str | None = None


class ResearchClient(Protocol):
    model: str

    def run_research(self, plan: ResearchPlan) -> ResearchResult: ...
    def gather_sources(self, plan: ResearchPlan) -> SourceGatheringResult: ...
    def synthesize_card(self, plan: ResearchPlan,
                        gathered: SourceGatheringResult) -> ResearchResult: ...

    # --- etapowy A1/A2/B ---
    def discover_sources(self, plan: ResearchPlan, max_searches: int) -> DiscoveryResult: ...
    def extract_source(self, plan: ResearchPlan,
                       candidate: SourceCandidate) -> ExtractionResult: ...
    def synthesize_from_cards(self, plan: ResearchPlan,
                              cards: list[SourceCardDraft]) -> ResearchResult: ...
