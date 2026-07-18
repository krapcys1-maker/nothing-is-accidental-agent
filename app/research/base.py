"""Kontrakt researchu i typy danych (draft przed walidacją)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from app.llm.base import Usage
from app.models import (
    DurableProviderAttemptContext,
    ProviderAttempt,
    ProviderAttemptStatus,
    SourceType,
    SourceVerification,
)


# Realny staged B z 2026-07-13 wyczerpał 2200 tokenów i urwał JSON. 3000 daje
# 36% zapasu, a przy aktualnym estymatorze nadal mieści fresh run w 0.55 USD oraz
# resume B (prior=0.170050 USD) w absolutnym capie 0.20 USD.
DEFAULT_SYNTHESIS_MAX_TOKENS = 3000


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
                 stop_reason: str | None = None, request_id: str | None = None) -> None:
        super().__init__(message)
        self.usage = usage
        self.model = model
        self.raw_text = raw_text
        self.stop_reason = stop_reason
        self.request_id = request_id


class DurableProviderAttemptContextError(ResearchError):
    """Realny client nie otrzymał kompletnego, potwierdzonego contextu durable."""


class ProviderRequestIdentityMismatch(DurableProviderAttemptContextError):
    """Durable request_id is not the exact identity derived from the attempt."""


def expected_provider_request_id(job_id: str, stage: str, attempt_no: int) -> str:
    """Derive the immutable request identity without normalizing components."""
    if not isinstance(job_id, str) or not job_id or not job_id.strip():
        raise ProviderRequestIdentityMismatch("Provider request job_id must be non-empty.")
    if not isinstance(stage, str) or not stage or not stage.strip() or ":" in stage:
        raise ProviderRequestIdentityMismatch(
            "Provider request stage must be non-empty and cannot contain ':'."
        )
    if not isinstance(attempt_no, int) or isinstance(attempt_no, bool) or attempt_no < 1:
        raise ProviderRequestIdentityMismatch(
            "Provider request attempt_no must be a positive integer."
        )
    return f"{job_id}:{stage}:{attempt_no}"


class ResearchProviderError(ResearchError):
    """Typed failure raised by the provider call itself.

    ``retryable`` is explicit and fail-closed.  Callers must not infer retry
    eligibility merely from this base class or from the presence of an HTTP
    status.  ``usage`` remains optional because Anthropic error responses do
    not normally expose message usage; when it is present, the existing retry
    usage callback owns persisting it exactly once.
    """

    default_retryable = False

    def __init__(self, message: str, *, status_code: int | None = None,
                 retryable: bool | None = None, usage: Usage | None = None,
                 model: str | None = None, raw_text: str | None = None,
                 stop_reason: str | None = None, request_id: str | None = None) -> None:
        super().__init__(message, usage=usage, model=model, raw_text=raw_text,
                         stop_reason=stop_reason, request_id=request_id)
        self.status_code = status_code
        self.retryable = self.default_retryable if retryable is None else retryable


class ResearchTimeout(ResearchProviderError):
    """Provider timeout (transient — eligible for bounded retry)."""

    default_retryable = True


class ResearchConnectionError(ResearchProviderError):
    """SDK-classified connection/network failure eligible for bounded retry."""

    default_retryable = True


class ResearchRateLimitError(ResearchProviderError):
    """Provider rate limit (HTTP 429) eligible for bounded retry."""

    default_retryable = True


class ResearchServerError(ResearchProviderError):
    """Provider 5xx response; only explicitly selected statuses are retryable."""


class ResearchAuthenticationError(ResearchProviderError):
    """Provider authentication failure (HTTP 401); never retried."""


class ResearchPermissionError(ResearchProviderError):
    """Provider permission failure (HTTP 403); never retried."""


class ResearchInvalidRequestError(ResearchProviderError):
    """Invalid provider request (HTTP 400/422); never retried."""


class ResearchNotFoundError(ResearchProviderError):
    """Provider resource/model not found (HTTP 404); never retried."""


class ResearchUnknownProviderError(ResearchProviderError):
    """Unclassified provider/SDK failure; fail closed without automatic retry."""


class ResearchParseError(ResearchError):
    """Model zwrócił niepoprawny format (NIE ponawiamy — to nie jest transient)."""

    def __init__(self, message: str, *, classification: str = "json_syntax",
                 usage: Usage | None = None, model: str | None = None,
                 raw_text: str | None = None, stop_reason: str | None = None,
                 request_id: str | None = None) -> None:
        super().__init__(message, usage=usage, model=model, raw_text=raw_text,
                         stop_reason=stop_reason, request_id=request_id)
        self.classification = classification


class ResearchSchemaError(ResearchParseError):
    """JSON jest kompletny, ale nie spełnia zamkniętego kontraktu ResearchDraft."""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("classification", "schema")
        super().__init__(message, **kwargs)


class ResearchCardSizeContractError(ResearchSchemaError):
    """Kompletny JSON przekracza jawny kontrakt rozmiaru Research Card.

    Podklasa `ResearchSchemaError`, więc dziedziczy w całości udowodnioną na
    żywo ścieżkę fail-closed: usage/settlement zachowane, terminalny FAILED,
    zero retry (patrz app/research/output_contract.py). Nigdy nie obcinamy
    treści po cichu — przekroczenie budżetu to zawsze jawny, typowany błąd.
    """

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("classification", "size_contract")
        super().__init__(message, **kwargs)


class ResearchTruncatedError(ResearchParseError):
    """Provider zakończył generację przez limit outputu; nigdy nie retry'ujemy."""

    def __init__(self, message: str, **kwargs) -> None:
        kwargs.setdefault("classification", "truncation")
        super().__init__(message, **kwargs)


class ResearchBudgetError(ResearchError):
    """A budget gate rejected an attempt; this error is never retried."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AttemptBudgetContext:
    """Context emitted immediately before each technical client attempt."""

    attempt_number: int
    max_attempts: int
    estimated_attempt_cost: float
    stage: str = "research"


AttemptBudgetCallback = Callable[[AttemptBudgetContext], object | None]
DurableAttemptContextCallback = Callable[[AttemptBudgetContext], DurableProviderAttemptContext]
DurableAttemptActivationCallback = Callable[[DurableProviderAttemptContext], ProviderAttempt]
DurableAttemptAssertionCallback = Callable[[DurableProviderAttemptContext], ProviderAttempt]
RetryUsageCallback = Callable[[Usage, str], None]


class DurableProviderBoundary:
    """One shared, fail-closed boundary immediately before a paid caller.

    Both Anthropic adapters use this object.  It owns the complete lifecycle of
    the in-memory request context, but it deliberately delegates the durable
    assertion to storage: SQLite is the authority for job, run, lease, fence,
    attempt and reservation state.  ``checked_at`` is never consumed here as
    authorization evidence.
    """

    def __init__(self, *, provider_label: str) -> None:
        self._provider_label = provider_label
        self._context_callback: DurableAttemptContextCallback | None = None
        self._activation_callback: DurableAttemptActivationCallback | None = None
        self._assertion_callback: DurableAttemptAssertionCallback | None = None
        self._active_context: DurableProviderAttemptContext | None = None
        self._active_request_id: str | None = None

    def configure(
        self,
        *,
        context_callback: DurableAttemptContextCallback | None,
        activation_callback: DurableAttemptActivationCallback | None,
        assertion_callback: DurableAttemptAssertionCallback | None,
    ) -> None:
        self._context_callback = context_callback
        self._activation_callback = activation_callback
        self._assertion_callback = assertion_callback
        self.clear()

    def activate(self, *, stage: str, attempt_no: int, estimated_attempt_cost: float) -> str:
        if not callable(self._context_callback) or not callable(self._activation_callback):
            raise DurableProviderAttemptContextError(
                f"{self._provider_label} request requires a durable provider attempt context."
            )
        context = self._context_callback(AttemptBudgetContext(
            attempt_number=attempt_no,
            max_attempts=1,
            estimated_attempt_cost=estimated_attempt_cost,
            stage=stage,
        ))
        expected_request_id = self._validate_context(
            context, stage=stage, attempt_no=attempt_no,
        )
        confirmation = self._activation_callback(context)
        self._require_matching_attempt(
            confirmation, context, expected_request_id=expected_request_id,
        )
        self._active_context = context
        self._active_request_id = expected_request_id
        return expected_request_id

    def assert_immediately_before_provider_call(self) -> str:
        """Revalidate state after SDK construction, at the request boundary."""
        context = self._active_context
        if context is None or self._active_request_id is None:
            raise DurableProviderAttemptContextError(
                "messages.create requires an active durable provider attempt context."
            )
        expected_request_id = self._validate_context(
            context, stage=context.stage, attempt_no=context.attempt_no,
        )
        if self._active_request_id != expected_request_id:
            raise ProviderRequestIdentityMismatch(
                "Active Idempotency-Key differs from the derived provider identity."
            )
        if not callable(self._assertion_callback):
            raise DurableProviderAttemptContextError(
                "messages.create requires a fresh durable provider assertion callback."
            )
        confirmation = self._assertion_callback(context)
        self._require_matching_attempt(
            confirmation, context, expected_request_id=expected_request_id,
        )
        return expected_request_id

    def clear(self) -> None:
        self._active_context = None
        self._active_request_id = None

    @staticmethod
    def _validate_context(
        context: object, *, stage: str, attempt_no: int,
    ) -> str:
        if not isinstance(context, DurableProviderAttemptContext):
            raise DurableProviderAttemptContextError(
                "Durable context callback must return DurableProviderAttemptContext."
            )
        if (
            not isinstance(context.job_id, str) or not context.job_id.strip()
            or not isinstance(context.run_id, str) or not context.run_id.strip()
            or not isinstance(context.lease_owner, str) or not context.lease_owner.strip()
            or not isinstance(context.fence_token, str) or not context.fence_token.strip()
            or isinstance(context.attempt_no, bool)
            or not isinstance(context.attempt_no, int)
            or context.attempt_no != attempt_no
            or context.stage != stage
        ):
            raise DurableProviderAttemptContextError(
                "Durable provider attempt context is incomplete or mismatched."
            )
        expected_request_id = expected_provider_request_id(
            context.job_id, context.stage, context.attempt_no,
        )
        if context.request_id != expected_request_id:
            raise ProviderRequestIdentityMismatch(
                "Durable context request_id does not match its derived identity."
            )
        return expected_request_id

    @staticmethod
    def _require_matching_attempt(
        confirmation: object,
        context: DurableProviderAttemptContext,
        *,
        expected_request_id: str,
    ) -> None:
        if not isinstance(confirmation, ProviderAttempt):
            raise DurableProviderAttemptContextError(
                "Durable callback must confirm a ProviderAttempt."
            )
        confirmation_expected = expected_provider_request_id(
            confirmation.job_id, confirmation.stage, confirmation.attempt_no,
        )
        if (
            confirmation.status is not ProviderAttemptStatus.REQUEST_STARTED
            or confirmation_expected != expected_request_id
            or confirmation.request_id != expected_request_id
            or confirmation.job_id != context.job_id
            or confirmation.stage != context.stage
            or confirmation.attempt_no != context.attempt_no
        ):
            raise ProviderRequestIdentityMismatch(
                "Durable callback confirmation does not match the derived provider identity."
            )


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
    request_id: str | None = None


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
    request_id: str | None = None


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
    request_id: str | None = None


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
    request_id: str | None = None


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
