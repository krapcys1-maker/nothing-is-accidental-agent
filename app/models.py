"""Modele domenowe (Pydantic v2) używane przez walking skeleton.

Podzbiór modeli z archiwalnego IMPLEMENTATION_PLAN.md §B.3 (docs/archive/superseded_plans/) — tylko to, czego potrzebuje
pierwszy etap (konta, tematy, run, zużycie modelu).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any

from pydantic import BaseModel, Field

from app.core.clock import Clock


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountMode(str, Enum):
    FULL_PUBLICATION = "FULL_PUBLICATION"
    COMMENT_ONLY = "COMMENT_ONLY"
    DRAFT_ONLY = "DRAFT_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class AutonomyLevel(str, Enum):
    LEVEL_0 = "LEVEL_0"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


class WorkflowType(str, Enum):
    TOPIC = "TOPIC"
    RESEARCH = "RESEARCH"
    ARTICLE = "ARTICLE"
    NOTE = "NOTE"
    COMMENT = "COMMENT"
    ANALYTICS = "ANALYTICS"


class JobStatus(str, Enum):
    """Trwały lifecycle zadania kolejki Etapu 1."""

    QUEUED = "QUEUED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    CANCELLED = "CANCELLED"


class JobKind(str, Enum):
    """Klasa bezpieczeństwa zadania, niezależna od jego workflow.

    ``BROWSER`` obejmuje przyszłe publikacje i inne akcje o niepewnym efekcie
    zewnętrznym. Wygasły lease takiego joba nigdy nie wraca automatycznie do
    kolejki.
    """

    LOCAL = "LOCAL"
    RESEARCH = "RESEARCH"
    BROWSER = "BROWSER"


class Job(BaseModel):
    """Jedno trwałe zadanie kolejki; utworzenie zawsze zaczyna lifecycle od QUEUED."""

    id: str
    account_id: str
    kind: JobKind
    workflow: WorkflowType
    idempotency_key: str
    priority: int = 0
    topic_id: int | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schedule_reason: str = ""
    earliest_run_at: datetime = Field(default_factory=_utcnow)
    deadline_at: datetime | None = None
    status: JobStatus = JobStatus.QUEUED
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempts: int = 0
    max_attempts: int = 1
    reserved_cost_usd: float = 0.0
    budget_reserved_at: datetime | None = None
    external_effect_started_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_utcnow)


@dataclass(frozen=True)
class JobEnqueueContext:
    """Trwała intencja requestu używana do idempotentnego enqueue.

    Harmonogram (`earliest_run_at`, `schedule_reason`) jest wynikiem pierwszego
    udanego enqueue, a nie częścią tożsamości requestu. `requested_at` i
    `immediate_contract` także nie są tu przechowywane: wpływają wyłącznie na
    pierwszą decyzję harmonogramu; ponowne planowanie wymaga nowego klucza.
    """

    idempotency_key: str
    account_id: str
    kind: str
    workflow: str
    priority: int
    topic_id: int | None
    run_id: str | None
    payload_json: str
    deadline_at: str | None
    max_attempts: int

    @staticmethod
    def _payload_json(payload: dict[str, Any]) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Job payload must be JSON-serializable.") from exc

    @staticmethod
    def _timestamp(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.strftime("%Y-%m-%d %H:%M:%S.%f") if value.microsecond else value.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def from_values(
        cls,
        *,
        idempotency_key: str,
        account_id: str,
        kind: JobKind,
        workflow: WorkflowType,
        priority: int,
        topic_id: int | None,
        run_id: str | None,
        payload: dict[str, Any],
        deadline_at: datetime | None,
        max_attempts: int,
    ) -> "JobEnqueueContext":
        return cls(
            idempotency_key=idempotency_key,
            account_id=account_id,
            kind=kind.value,
            workflow=workflow.value,
            priority=priority,
            topic_id=topic_id,
            run_id=run_id,
            payload_json=cls._payload_json(payload),
            deadline_at=cls._timestamp(deadline_at),
            max_attempts=max_attempts,
        )

    @classmethod
    def from_job(cls, job: Job) -> "JobEnqueueContext":
        return cls.from_values(
            idempotency_key=job.idempotency_key,
            account_id=job.account_id,
            kind=job.kind,
            workflow=job.workflow,
            priority=job.priority,
            topic_id=job.topic_id,
            run_id=job.run_id,
            payload=job.payload,
            deadline_at=job.deadline_at,
            max_attempts=job.max_attempts,
        )

    @classmethod
    def from_row(cls, row: Any) -> "JobEnqueueContext":
        return cls(
            idempotency_key=row["idempotency_key"],
            account_id=row["account_id"],
            kind=row["kind"],
            workflow=row["workflow"],
            priority=int(row["priority"]),
            topic_id=row["topic_id"],
            run_id=row["run_id"],
            payload_json=row["payload_json"],
            deadline_at=row["deadline_at"],
            max_attempts=int(row["max_attempts"]),
        )


class JobLease(BaseModel):
    """Wynik atomowego claimu: konkretny job i lease należący do workera."""

    job: Job
    lease_owner: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class JobEnqueueResult:
    """Atomowy wynik enqueue rozróżniający nowy i już zapisany intent."""

    job: Job
    created: bool


@dataclass(frozen=True)
class ResearchJobExecution:
    """Uprawnienie workera do jednorazowej atomowej inicjalizacji researchu."""

    job_id: str
    lease_owner: str


@dataclass(frozen=True)
class JobExecutionContext:
    """Zamknięte uprawnienie do mutacji jednego runu pod aktywnym lease.

    Powstaje dopiero z wyniku atomowej inicjalizacji. Zegar jest zależnością
    procesu, nie wartością z payloadu; każda mutacja pobiera z niego świeży czas.
    """

    job_id: str
    lease_owner: str
    run_id: str
    clock: Clock
    kind: JobKind = JobKind.RESEARCH
    workflow: WorkflowType = WorkflowType.RESEARCH

    def now(self) -> datetime:
        return self.clock.now()


@dataclass(frozen=True)
class DurableProviderAttemptContext:
    """Niemutowalny kontrakt wymagany bezpośrednio przed płatnym callerem.

    To nie jest payload joba ani luźny zestaw argumentów.  Callback klienta musi
    potwierdzić ten konkretny context w SQLite tuż przed przekroczeniem granicy SDK.
    """

    job_id: str
    run_id: str
    stage: str
    attempt_no: int
    request_id: str
    lease_owner: str
    fence_token: str
    # Wyłącznie ślad diagnostyczny chwili zbudowania contextu. Nie autoryzuje
    # lease: storage pobiera świeży czas z execution clock w swojej transakcji.
    checked_at: datetime | None = None


class JobReservation(BaseModel):
    """Aktywna, konserwatywna rezerwacja budżetu — nie jest realnym wydatkiem."""

    job_id: str
    amount_usd: float
    reserved_at: datetime


class ProviderAttemptStatus(str, Enum):
    """Trwały stan jednej logicznej próby odpłatnego dostawcy.

    Nie jest to retry SDK: WAVE 0B celowo wykonuje najwyżej jedno wywołanie
    providera dla takiej próby.  Stan ``NEEDS_RECONCILIATION`` zachowuje
    rezerwację po niejednoznacznym wyniku transportowym.
    """

    RESERVED = "RESERVED"
    REQUEST_STARTED = "REQUEST_STARTED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    RECONCILED_SETTLED = "RECONCILED_SETTLED"
    RECONCILED_RELEASED = "RECONCILED_RELEASED"


class FinancialResolution(str, Enum):
    """Manual, auditable resolution of the financial provider outcome."""

    CHARGED_KNOWN = "CHARGED_KNOWN"
    NOT_CHARGED = "NOT_CHARGED"
    CHARGE_UNKNOWN = "CHARGE_UNKNOWN"


class ExecutionResolution(str, Enum):
    """Manual resolution of the already-persisted job/run lifecycle."""

    EXECUTION_FAILED = "EXECUTION_FAILED"
    RESULT_ALREADY_FINALIZED = "RESULT_ALREADY_FINALIZED"
    MANUAL_REVIEW_REMAINS_REQUIRED = "MANUAL_REVIEW_REMAINS_REQUIRED"


class ReconciliationEventType(str, Enum):
    """Append-only durable audit entry kinds for one provider attempt.

    ``UNRESOLVED_OBSERVATION`` is the first operator note on an ambiguous attempt,
    ``FOLLOW_UP`` any later note while it stays unresolved, ``FINAL_RESOLUTION``
    the single terminal settlement/release decision, and ``AUTO_ESCALATION`` the
    durable audit record written when maintenance or the worker failure boundary
    escalates a RESERVED/REQUEST_STARTED attempt into the operator queue.
    """

    UNRESOLVED_OBSERVATION = "UNRESOLVED_OBSERVATION"
    FOLLOW_UP = "FOLLOW_UP"
    FINAL_RESOLUTION = "FINAL_RESOLUTION"
    AUTO_ESCALATION = "AUTO_ESCALATION"


class ReconciliationFaultPoint(str, Enum):
    """Test-only checkpoints inside the resolver's one SQLite transaction."""

    AFTER_USAGE_WRITE = "AFTER_USAGE_WRITE"
    AFTER_ATTEMPT_UPDATE = "AFTER_ATTEMPT_UPDATE"
    AFTER_EVENT_INSERT = "AFTER_EVENT_INSERT"
    AFTER_CACHE_REFRESH = "AFTER_CACHE_REFRESH"
    AFTER_JOB_UPDATE = "AFTER_JOB_UPDATE"
    AFTER_RUN_UPDATE = "AFTER_RUN_UPDATE"
    AFTER_RESEARCH_RUN_UPDATE = "AFTER_RESEARCH_RUN_UPDATE"
    BEFORE_COMMIT = "BEFORE_COMMIT"


class ResearchExecutionFailureOutcome(str, Enum):
    """Durable result of the shared worker research failure boundary.

    The caller must not infer a terminal job from an exception class.  Storage
    first inspects the linked provider attempt in the same transaction and then
    reports which durable branch was committed.
    """

    TERMINALIZED_FAILED = "TERMINALIZED_FAILED"
    ESCALATED_RESERVED = "ESCALATED_RESERVED"
    ESCALATED_REQUEST_STARTED = "ESCALATED_REQUEST_STARTED"
    ALREADY_NEEDS_RECONCILIATION = "ALREADY_NEEDS_RECONCILIATION"
    PRESERVED_NEEDS_VERIFICATION = "PRESERVED_NEEDS_VERIFICATION"
    ALREADY_TERMINALIZED = "ALREADY_TERMINALIZED"


class ProviderAttempt(BaseModel):
    """Jedna trwała tożsamość wywołania dostawcy w ramach joba."""

    job_id: str
    stage: str
    attempt_no: int
    request_id: str
    execution_intent_fingerprint: str | None = None
    status: ProviderAttemptStatus
    reserved_amount_usd: float
    reserved_at: datetime
    request_started_at: datetime | None = None
    settled_at: datetime | None = None
    released_at: datetime | None = None
    actual_cost_usd: float | None = None
    error_code: str | None = None
    reconciled_at: datetime | None = None
    reconciled_by: str | None = None
    reconciliation_note: str | None = None
    reconciliation_resolution: str | None = None


class ReconciliationEvent(BaseModel):
    """One append-only entry in the durable operator reconciliation history."""

    id: int
    request_id: str
    sequence_number: int
    event_type: ReconciliationEventType
    financial_resolution: FinancialResolution
    execution_resolution: ExecutionResolution
    operator: str
    note: str
    previous_attempt_status: ProviderAttemptStatus
    resulting_attempt_status: ProviderAttemptStatus
    created_at: datetime
    idempotency_key: str


class ProviderAttemptReconciliationResult(BaseModel):
    """Stable result returned by an operator reconciliation transaction."""

    attempt: ProviderAttempt
    financial_resolution: FinancialResolution
    execution_resolution: ExecutionResolution
    usage_id: int | None = None
    idempotent: bool = False
    observed: bool = False
    event: ReconciliationEvent | None = None


class ReconciliationPreview(BaseModel):
    """Read-only durable snapshot returned before an operator confirms.

    ``version_token`` is a fingerprint of the exact durable state the preview
    observed; confirm re-reads under ``BEGIN IMMEDIATE`` and fails closed if the
    token no longer matches.
    """

    request_id: str
    account_id: str
    attempt_status: ProviderAttemptStatus
    job_status: str | None = None
    run_status: str | None = None
    research_run_status: str | None = None
    usage_count: int = 0
    canonical_cost_usd: str = "0.000000"
    reserved_amount_usd: float = 0.0
    reservation_active: bool = False
    research_card_id: int | None = None
    event_count: int = 0
    latest_event: ReconciliationEvent | None = None
    version_token: str


class JobRecoveryResult(BaseModel):
    """Deterministyczny wynik jednego przebiegu recovery wygasłych lease."""

    requeued_count: int = 0
    needs_verification_count: int = 0
    failed_count: int = 0
    escalated_reconciliation_count: int = 0


class RunReaperResult(BaseModel):
    """Wynik jednego, jawnie uruchomionego przebiegu reapera runów."""

    checked_count: int = 0
    stopped_count: int = 0


class SystemFlag(BaseModel):
    """Runtime flaga bezpieczeństwa odczytywana z bazy przy każdym checku."""

    key: str
    value: bool
    updated_at: datetime = Field(default_factory=_utcnow)
    updated_by: str | None = None
    reason: str | None = None
    is_valid: bool = True


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    DRY_RUN = "DRY_RUN"


class TopicStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    SCORED = "SCORED"        # kwalifikuje się na Note (>= note_min, < article_min)
    SELECTED = "SELECTED"    # kwalifikuje się na artykuł (>= article_min)
    REJECTED = "REJECTED"    # poniżej progu Note
    DUPLICATE = "DUPLICATE"  # duplikat istniejącego tematu (nieaktywny)
    USED = "USED"


class SourceType(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    DATA = "DATA"
    OTHER = "OTHER"


class SourceVerification(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


class ResearchRecommendation(str, Enum):
    PROCEED = "PROCEED"
    REVISE = "REVISE"
    REJECT = "REJECT"


class AccountPolicy(BaseModel):
    require_article_approval: bool = True
    require_note_approval: bool = True
    require_comment_approval: bool = True
    require_restack_approval: bool = True
    daily_comment_limit: int = 5
    daily_note_limit: int = 2
    weekly_article_limit: int = 2
    max_per_author_per_day: int = 1
    allow_links: bool = True
    link_ratio_limit: float = 0.10


class Account(BaseModel):
    id: str
    display_name: str
    mode: AccountMode
    autonomy_level: AutonomyLevel = AutonomyLevel.LEVEL_1
    active: bool = False
    niche: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    browser_profile_path: str = ""
    writing_profile_path: str = ""
    allowed_actions: list[str] = Field(default_factory=list)
    policies: AccountPolicy = Field(default_factory=AccountPolicy)


class Topic(BaseModel):
    id: int | None = None
    account_id: str
    title: str
    question: str | None = None
    score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    status: TopicStatus = TopicStatus.DISCOVERED
    source: str | None = None
    duplicate_of: int | None = None
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Run(BaseModel):
    id: str
    account_id: str
    workflow: WorkflowType
    status: RunStatus = RunStatus.RUNNING
    current_state: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    cost_usd: float = 0.0
    error: str | None = None
    human_intervention_count: int = 0


class ModelUsage(BaseModel):
    id: int | None = None
    run_id: str
    provider: str = "anthropic"
    model: str
    task: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_search_requests: int = 0
    estimated_cost_usd: float = 0.0
    dry_run: bool = False
    request_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Source(BaseModel):
    id: int | None = None
    research_card_id: int | None = None
    url: str
    title: str | None = None
    author_or_org: str | None = None
    published_at: str | None = None      # ISO string lub None (może być nieznana)
    source_type: SourceType = SourceType.OTHER
    supports_claim: str | None = None    # które twierdzenie potwierdza
    verification_status: SourceVerification = SourceVerification.UNVERIFIED


class ResearchCard(BaseModel):
    id: int | None = None
    topic_id: int
    question: str
    working_thesis: str
    main_mechanism: str | None = None
    confirmed_claims: list[str] = Field(default_factory=list)
    uncertain_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    strongest_counterargument: str | None = None
    citable_numbers: list[str] = Field(default_factory=list)
    visual_idea: str | None = None
    confidence_score: float = 0.0
    source_quality_score: float = 0.0
    publication_recommendation: ResearchRecommendation = ResearchRecommendation.REJECT
    rejection_reason: str | None = None
    sources: list[Source] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


# --- Wznawialny dwuetapowy research (od 2026-07-11, stabilizacja Research Pipeline) ---

class ResearchRunStatus(str, Enum):
    # --- stary dwuetapowy przepływ (gather_sources+synthesize_card, ADR-016/019) ---
    PENDING = "PENDING"                    # utworzony, etap A jeszcze nie próbowany
    SOURCE_COLLECTED = "SOURCE_COLLECTED"   # etap A udany, źródła trwale zapisane
    # --- nowy etapowy przepływ A1/A2/B (discover/extract/synthesize, ADR-020) ---
    DISCOVERY_PENDING = "DISCOVERY_PENDING"         # utworzony, etap A1 jeszcze nie próbowany
    DISCOVERY_COMPLETE = "DISCOVERY_COMPLETE"       # etap A1 udany, kandydaci trwale zapisani
    EXTRACTION_IN_PROGRESS = "EXTRACTION_IN_PROGRESS"  # etap A2 w toku/wznawialny (część źródeł już wyekstrahowana)
    SOURCES_COMPLETE = "SOURCES_COMPLETE"           # etap A2 dał >= min_sources kart — gotowe do etapu B
    SYNTHESIS_PENDING = "SYNTHESIS_PENDING"         # etap B właśnie w trakcie próby
    PARTIAL_EXHAUSTED = "PARTIAL_EXHAUSTED"          # za mało źródeł i brak legalnego retry A2
    # --- wspólne dla obu przepływów ---
    PARTIAL = "PARTIAL"                    # za mało źródeł/wyników — zachowane, ale poniżej progu
    COMPLETE = "COMPLETE"                  # etap B udany, pełna Research Card istnieje
    FAILED = "FAILED"                      # nic trwałego nie powstało — nie ma czego wznawiać


class ResearchFlow(str, Enum):
    SINGLE = "single"
    TWO_STAGE = "two_stage"
    STAGED = "staged"


class StagedFinalizationMode(str, Enum):
    """Trwały kontrakt uprawnienia dla atomowego zakończenia staged B."""

    FRESH = "fresh"
    RESUME_B = "resume_b"
    FORCE_RERESEARCH = "force_reresearch"
    FORCE_RERESEARCH_RESUME_B = "force_reresearch_resume_b"


class StagedFinalizationFaultPoint(str, Enum):
    """Test-only controlled interruption points inside staged B transaction."""

    BEFORE_CARD_INSERT = "before_card_insert"
    AFTER_CARD_INSERT = "after_card_insert"
    BEFORE_SOURCE_INSERT = "before_source_insert"
    AFTER_FIRST_SOURCE_INSERT = "after_first_source_insert"
    AFTER_ALL_SOURCE_INSERTS = "after_all_source_inserts"
    BEFORE_STAGE_B_SUCCESS_INSERT = "before_stage_b_success_insert"
    AFTER_STAGE_B_SUCCESS_INSERT = "after_stage_b_success_insert"
    BEFORE_RESEARCH_RUN_UPDATE = "before_research_run_update"
    AFTER_RESEARCH_RUN_UPDATE = "after_research_run_update"
    BEFORE_RUN_UPDATE = "before_run_update"
    AFTER_RUN_UPDATE = "after_run_update"
    BEFORE_TOPIC_USED_UPDATE = "before_topic_used_update"
    AFTER_TOPIC_USED_UPDATE = "after_topic_used_update"


@dataclass(frozen=True)
class StagedFinalizationContext:
    """Snapshot wymagany przez preflight i atomową finalizację staged B.

    `expected_research_status` opisuje stan przed wywołaniem B
    (`SOURCES_COMPLETE`). Finalizer ponownie sprawdza, że po preflight stan
    przeszedł wyłącznie do `SYNTHESIS_PENDING`.
    """

    mode: StagedFinalizationMode
    expected_run_status: RunStatus
    expected_research_status: ResearchRunStatus
    expected_finished_at: datetime | None = None
    expected_failure_marker: str | None = None


class SourceCandidateStatus(str, Enum):
    PENDING_EXTRACTION = "PENDING_EXTRACTION"   # z etapu A1, jeszcze nie próbowano A2
    EXTRACTION_IN_PROGRESS = "EXTRACTION_IN_PROGRESS"  # A2 reserved; durable result not yet saved
    EXTRACTED = "EXTRACTED"                     # etap A2 udany dla TEGO źródła
    EXTRACTION_FAILED = "EXTRACTION_FAILED"     # etap A2 nieudany dla TEGO źródła (inne nietknięte)


class ResearchStageName(str, Enum):
    A = "A"     # gather_sources (stary dwuetapowy przepływ)
    A1 = "A1"   # discover_sources (nowy etapowy przepływ)
    A2 = "A2"   # extract_source (nowy etapowy przepływ, per źródło)
    B = "B"     # synthesize_card / synthesize_from_cards (wspólne dla obu przepływów)


class ResearchStageStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ResearchRun(BaseModel):
    """Stan maszyny stanów dla jednej próby researchu. `id` = to samo id co w `Run`
    (rozszerzenie 1:1) — model_usage.run_id już na nie wskazuje, więc koszt obu
    etapów jest naturalnie powiązany bez osobnej tabeli kosztów."""
    id: str
    account_id: str
    topic_id: int
    flow: ResearchFlow
    status: ResearchRunStatus = ResearchRunStatus.PENDING
    stage_a_completed_at: datetime | None = None
    stage_b_completed_at: datetime | None = None
    research_card_id: int | None = None
    # Trwały ślad jawnego --force-re-research. Nie jest to zgoda przekazywana
    # przez pamięć procesu: dispatcher resume odczytuje go ponownie z SQLite.
    is_force_reresearch: bool = False
    total_cost_usd: float = 0.0
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


@dataclass(frozen=True)
class ResearchRunInitialization:
    """Wynik atomowego utworzenia albo odczytu runu przypiętego do joba."""

    job: Job
    run: Run
    research_run: ResearchRun
    created: bool


class ResearchSourceRecord(BaseModel):
    """Trwały wynik etapu A — jedno źródło, zapisane NIEZALEŻNIE od tego, czy etap B
    kiedykolwiek się wykona. To jest mechanizm "nie trać wyników wyszukiwania".
    Należy do STAREGO dwuetapowego przepływu (gather_sources+synthesize_card) —
    nowy, etapowy przepływ używa `SourceCandidateRecord` poniżej."""
    id: int | None = None
    research_run_id: str
    url: str
    title: str | None = None
    author_or_org: str | None = None
    published_at: str | None = None
    source_type: SourceType = SourceType.OTHER
    key_facts: list[str] = Field(default_factory=list)
    verification_status: SourceVerification = SourceVerification.UNVERIFIED
    created_at: datetime = Field(default_factory=_utcnow)


# --- Etapowy research A1/A2/B (od 2026-07-12, ADR-020) ---

class SourceCandidateRecord(BaseModel):
    """Wynik etapu A1 (url+title), wzbogacany W MIEJSCU przez etap A2 (autor, data,
    twierdzenia, fakty liczbowe, ocena jakości) — jeden wiersz na źródło, ewoluujący
    od "kandydata" do pełnej "Source Card" w tej samej tabeli/rekordzie. Zapisywany
    do bazy NATYCHMIAST po A1 (jako PENDING_EXTRACTION) i aktualizowany NATYCHMIAST
    po każdej (udanej lub nieudanej) próbie A2 dla TEGO źródła — źródła 1..N-1 nigdy
    nie czekają na wynik źródła N."""
    id: int | None = None
    research_run_id: str
    url: str
    title: str | None = None
    author_or_org: str | None = None
    published_at: str | None = None
    source_type: SourceType = SourceType.OTHER
    supported_claims: list[str] = Field(default_factory=list)
    numeric_facts: list[str] = Field(default_factory=list)
    verification_status: SourceVerification = SourceVerification.UNVERIFIED
    source_quality_score: float = 0.0
    status: SourceCandidateStatus = SourceCandidateStatus.PENDING_EXTRACTION
    extraction_error: str | None = None
    # Atomically reserved/started A2 attempts. It does not prove a provider call
    # completed: a crash leaves the candidate EXTRACTION_IN_PROGRESS for recovery.
    attempts: int = 0
    discovered_at: datetime = Field(default_factory=_utcnow)
    extracted_at: datetime | None = None


class SourceCandidateRetryResult(BaseModel):
    """Wynik idempotentnego, jawnego resetu nieudanych kandydatów A2."""

    reset_count: int = 0
    skipped_cap_count: int = 0
    already_pending_count: int = 0
    in_progress_count: int = 0
    remaining_failed_count: int = 0
    reopened_run: bool = False
