"""StoragePort — kontrakt trwałego stanu.

Każda metoda per-konto przyjmuje account_id jako obowiązkowy parametr (izolacja kont).
Lokalny adapter: app/storage/repositories.py (SQLite). Później: Postgres.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from app.core.clock import Clock
from app.models import (
    Account,
    Job,
    JobEnqueueResult,
    JobExecutionContext,
    JobLease,
    JobRecoveryResult,
    JobReservation,
    DurableProviderAttemptContext,
    ExecutionResolution,
    FinancialResolution,
    ProviderAttempt,
    ProviderAttemptReconciliationResult,
    ReconciliationEvent,
    ReconciliationPreview,
    ResearchExecutionFailureOutcome,
    ModelUsage,
    ResearchCard,
    ResearchFlow,
    ResearchRunInitialization,
    ResearchRun,
    StagedFinalizationContext,
    SystemFlag,
    ResearchSourceRecord,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    RunReaperResult,
    RunStatus,
    SourceCandidateRecord,
    SourceCandidateRetryResult,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    Topic,
    TopicStatus,
)


class ResearchTopicIntegrityError(RuntimeError):
    """Stan researchu tematu przeczy jego trwałej semantyce."""


class JobConflictError(RuntimeError):
    """Idempotency albo aktywna blokada topicu nie pozwala utworzyć joba."""


class JobPayloadValidationError(JobConflictError):
    """Typed enqueue rejection for a durable execution contract."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ModelUsageRequestIdError(ValueError):
    """Nowy realny usage nie ma durable request_id powiązanego z attemptem."""


class ProviderAttemptReconciliationRequired(RuntimeError):
    """Poprzednia próba ma niejednoznaczny skutek i blokuje nowy request."""


class ProviderAttemptOverReservationError(ProviderAttemptReconciliationRequired):
    """Persisted actual usage exceeded its pre-request durable reservation."""

    code = "PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION"

    def __init__(self, *, reserved_amount_usd: float, actual_cost_usd: float) -> None:
        self.reserved_amount_usd = reserved_amount_usd
        self.actual_cost_usd = actual_cost_usd
        super().__init__(
            "Provider usage exceeded the durable reservation; reconciliation is required."
        )


class ProviderAttemptReconciliationError(ProviderAttemptReconciliationRequired):
    """Operator resolution conflicts with the durable attempt or lifecycle."""


class ReconciliationPreviewStaleError(ProviderAttemptReconciliationError):
    """The durable state changed since the preview token was issued."""


class JobRunRelationError(RuntimeError):
    """Research job nie może zostać bezpiecznie powiązany z podanym runem."""

    _MAX_AUDIT_MESSAGE_LENGTH = 240

    def __init__(self, code: str, job_id: str, detail: str) -> None:
        self.code = code
        self.job_id = job_id
        # ``job_id`` is retained as structured exception data, but never rendered
        # into an audit string. Jobs can originate in persisted input, so including
        # their raw identifier could leak a token-like value or a newline into
        # ``jobs.last_error``.
        normalized_detail = " ".join(detail.split())
        message = f"{code}: {normalized_detail}"
        super().__init__(message[:self._MAX_AUDIT_MESSAGE_LENGTH])


class JobRunConflictError(JobRunRelationError):
    """Job ma już trwałe powiązanie z innym runem."""

    def __init__(self, job_id: str, existing_run_id: str, requested_run_id: str) -> None:
        super().__init__(
            "JOB_RUN_ALREADY_ATTACHED",
            job_id,
            "a different run_id is already attached.",
        )


class JobRunReconciliationRequired(JobRunRelationError):
    """Wygasły job z przypiętym runem wymaga jawnej, przyszłej reconciliacji."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            "RESEARCH_RUN_RECONCILIATION_REQUIRED",
            job_id,
            "attached research run is not automatically restarted after lease expiry.",
        )


class StaleJobExecutionError(JobRunRelationError):
    """Mutacja workera została odrzucona przez autorytatywny fence SQLite."""

    def __init__(self, job_id: str, detail: str = "job execution lease is no longer active.") -> None:
        super().__init__("STALE_JOB_EXECUTION", job_id, detail)


class BudgetReservationError(RuntimeError):
    """Rezerwacja przekracza limit lub przeczy istniejącej rezerwacji joba."""


class AmountBelowMinimumPrecisionError(BudgetReservationError):
    """Dodatnia kwota znikałaby po canonicalizacji do sześciu miejsc USD."""


class SystemFlagError(ValueError):
    """Nieprawidłowa wartość runtime flagi bezpieczeństwa."""


class LifecycleTransitionError(ValueError):
    """A persisted entity cannot make the requested lifecycle transition."""

    def __init__(
        self,
        entity: str,
        identifier: str | int,
        target_status: str,
        allowed_source_statuses: Sequence[str],
        current_status: str | None,
        *,
        detail: str | None = None,
    ) -> None:
        self.entity = entity
        self.identifier = identifier
        self.target_status = target_status
        self.allowed_source_statuses = tuple(allowed_source_statuses)
        self.current_status = current_status
        current = current_status if current_status is not None else "<missing>"
        allowed = ", ".join(self.allowed_source_statuses) or "<none>"
        prefix = f"{detail} " if detail else ""
        super().__init__(
            f"{prefix}{entity} #{identifier} cannot transition to {target_status}; "
            f"allowed source statuses: [{allowed}]; current status: {current}."
        )


class StoragePort(Protocol):
    def ensure_account(self, account: Account) -> None: ...

    def add_topic(self, account_id: str, topic: Topic) -> Topic: ...

    def list_topics(self, account_id: str) -> Sequence[Topic]: ...

    def list_topic_titles_for_dedup(self, account_id: str) -> list[tuple[int, str]]: ...

    def list_topics_by_status(self, account_id: str, status: TopicStatus) -> Sequence[Topic]: ...

    def create_run(self, run: Run) -> Run: ...

    def finish_run(self, run_id: str, status: str, cost_usd: float,
                   error: str | None = None) -> None:
        """Kończy ogólny run; nie może oznaczyć staged research jako sukcesu."""
        ...

    def get_run(self, run_id: str) -> Run | None: ...

    def finish_resumed_research_run(
        self, run_id: str, account_id: str, expected_flow: ResearchFlow,
        expected_finished_at: datetime, cost_usd: float, error: str,
    ) -> None:
        """CAS-updates FAILED audit fields for one explicitly resumed research attempt."""
        ...

    def add_model_usage(self, usage: ModelUsage) -> ModelUsage: ...

    def sum_real_cost_usd(self, since_prefix: str) -> float:
        """Suma estimated_cost_usd dla realnych (nie dry_run) wpisów, których
        created_at zaczyna się od podanego prefiksu (np. '2026-07' dla miesiąca)."""
        ...

    # --- Etap 1: trwała kolejka, lease i runtime flags (bez worker loop) ---

    def enqueue_job(self, job: Job) -> Job:
        """Atomowo zapisuje QUEUED job lub zwraca identyczny idempotentny rekord."""
        ...

    def enqueue_job_result(self, job: Job) -> JobEnqueueResult:
        """Atomowo zapisuje intent i jawnie wskazuje, czy utworzył nowy rekord."""
        ...

    def get_job(self, job_id: str) -> Job | None: ...

    def get_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        """Zwraca trwały job dla klucza bez przeliczania jego harmonogramu."""
        ...

    def claim_next_job(
        self, lease_owner: str, lease_seconds: int, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> JobLease | None:
        """Atomowo przydziela najwyżej jeden eligible QUEUED job."""
        ...

    def mark_job_running(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None: ...

    def attach_job_run(
        self, job_id: str, lease_owner: str, run_id: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        """CAS-links a compatible worker RESEARCH job with its newly created run."""
        ...

    def initialize_research_run_for_job(
        self, job_id: str, lease_owner: str, run_id: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> ResearchRunInitialization:
        """Atomowo tworzy run, jego rozszerzenie research i wiąże je z aktywnym jobem."""
        ...

    def assert_job_execution_active(self, execution: JobExecutionContext) -> None:
        """Sprawdza zamknięty job→run→lease fence w krótkiej transakcji SQLite."""
        ...

    def add_job_model_usage(
        self, execution: JobExecutionContext, usage: ModelUsage,
    ) -> ModelUsage:
        """Atomowo zapisuje usage i koszt wyłącznie pod świeżym fence workera."""
        ...

    def begin_provider_attempt(
        self, execution: JobExecutionContext, *, stage: str, attempt_no: int,
        max_cost_usd: float, daily_limit_usd: float, monthly_limit_usd: float,
    ) -> ProviderAttempt:
        """Atomowo odzyskuje/tworzy próbę i rezerwuje jej maksymalny koszt."""
        ...

    def mark_provider_attempt_request_started(
        self, execution: JobExecutionContext, request_id: str,
    ) -> ProviderAttempt:
        """Utrwala granicę tuż przed przekazaniem requestu do SDK."""
        ...

    def assert_durable_provider_attempt_active(
        self, context: DurableProviderAttemptContext, *, clock: Clock,
    ) -> ProviderAttempt:
        """Potwierdza request→job→run→lease dla realnego callera tuż przed SDK."""
        ...

    def release_provider_attempt_before_request(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        """Zwalnia rezerwację tylko gdy request nie przekroczył granicy SDK."""
        ...

    def mark_provider_attempt_needs_reconciliation(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        """Zachowuje rezerwację po timeout/connection/nieznanym wyniku."""
        ...

    def settle_provider_attempt_without_usage(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        """Zamyka potwierdzony błąd dostawcy, gdy nie zwrócił usage."""
        ...

    def list_provider_attempts_needing_reconciliation(
        self, *, account_id: str | None = None,
    ) -> list[ProviderAttempt]:
        """Read-only L1 queue; it never creates a provider or worker action."""
        ...

    def preview_provider_attempt_reconciliation(
        self, *, request_id: str, account_id: str,
    ) -> ReconciliationPreview:
        """Read-only durable snapshot and version token; performs no mutation."""
        ...

    def list_reconciliation_events(
        self, *, request_id: str, account_id: str,
    ) -> list[ReconciliationEvent]:
        """Read-only, ordered append-only reconciliation history for one attempt."""
        ...

    def resolve_provider_attempt_reconciliation(
        self,
        *,
        request_id: str,
        account_id: str,
        financial_resolution: FinancialResolution,
        execution_resolution: ExecutionResolution,
        actual_cost_usd: float | str | None,
        reconciled_by: str,
        note: str,
        expected_version_token: str | None = None,
    ) -> ProviderAttemptReconciliationResult:
        """Atomically resolves or observes an existing NEEDS_RECONCILIATION attempt.

        ``expected_version_token`` (from a prior preview) fails closed if the
        durable state changed since the preview.
        """
        ...

    def fail_or_escalate_job_research_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False, preserve_for_verification: bool = False,
    ) -> ResearchExecutionFailureOutcome:
        """Atomically fail a safe execution or escalate its active provider attempt."""
        ...

    def fail_job_research_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False,
    ) -> ResearchExecutionFailureOutcome:
        """Compatibility alias for the centralized fail-or-escalate operation."""
        ...

    def finalize_job_research_execution(
        self, execution: JobExecutionContext, card: ResearchCard, total_cost_usd: float,
        *, terminal_run_status: RunStatus,
    ) -> ResearchCard:
        """Atomowo zapisuje sukces single flow oraz terminalny job pod fence."""
        ...

    def reserve_job_budget_for_execution(
        self, execution: JobExecutionContext, amount_usd: float, *,
        daily_limit_usd: float, monthly_limit_usd: float,
    ) -> JobReservation:
        """Wariant rezerwacji dostępny dla aktywnego execution workera."""
        ...

    def release_job_budget_for_execution(self, execution: JobExecutionContext) -> None:
        """Wariant zwolnienia dostępny dla aktywnego execution workera."""
        ...

    def mark_job_external_effect_started(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Trwale zaznacza granicę, po której expiry nie może auto-retry'ować joba."""
        ...

    def complete_job(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None: ...

    def fail_job(
        self, job_id: str, lease_owner: str, error: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None: ...

    def mark_job_needs_verification(
        self, job_id: str, lease_owner: str, error: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None: ...

    def release_or_requeue_expired_leases(
        self, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> JobRecoveryResult: ...

    def reap_orphaned_stale_runs(
        self, stale_before: datetime, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> RunReaperResult:
        """Fail-closed RUNNING→STOPPED reaper after job recovery/reconciliation."""
        ...

    def heartbeat_job_lease(
        self, job_id: str, lease_owner: str, lease_seconds: int,
        *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None: ...

    def cancel_job(
        self, job_id: str, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None: ...

    def reserve_job_budget(
        self, job_id: str, amount_usd: float, *, daily_limit_usd: float,
        monthly_limit_usd: float, now: datetime | None = None, clock: Clock | None = None,
    ) -> JobReservation:
        """Jedna transakcja: realne usage + aktywne rezerwacje + nowa rezerwacja."""
        ...

    def release_job_budget(
        self, job_id: str, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None: ...

    def get_system_flag(self, key: str) -> SystemFlag | None:
        """Brak/uszkodzenie flag bezpieczeństwa zwraca bezpieczną wartość runtime."""
        ...

    def set_system_flag(
        self, key: str, value: bool, *, updated_by: str | None = None,
        reason: str | None = None, now: datetime | None = None,
    ) -> SystemFlag: ...

    def add_research_card(self, card: ResearchCard) -> ResearchCard: ...

    def get_research_card(self, card_id: int) -> ResearchCard | None: ...

    def list_research_cards(self, account_id: str) -> list[ResearchCard]: ...

    # --- wznawialny dwuetapowy research ---

    def create_research_run(self, research_run: ResearchRun) -> ResearchRun: ...

    def get_research_run(self, research_run_id: str) -> ResearchRun | None: ...

    def has_valid_completed_research_card_for_topic(
        self, account_id: str, topic_id: int,
    ) -> bool: ...

    def finalize_research_success(
        self, research_run_id: str, research_card_id: int, total_cost_usd: float,
        *, stage_b_completed: bool, terminal_run_status: RunStatus,
    ) -> None:
        """Finalizuje wyłącznie legacy `single`/`two_stage`; `staged` jest odrzucany."""
        ...

    def finalize_staged_research_with_card(
        self, research_run_id: str, card: ResearchCard, total_cost_usd: float,
        *, terminal_run_status: RunStatus, min_sources: int, min_verified_sources: int,
        context: StagedFinalizationContext,
    ) -> ResearchCard:
        """Jedyna publiczna ścieżka sukcesu staged B: karta, B SUCCESS i lifecycle razem."""
        ...

    def preflight_staged_finalization(
        self, research_run_id: str, *, terminal_run_status: RunStatus,
        context: StagedFinalizationContext,
    ) -> None:
        """Fail-closed sprawdzenie legalności finalizacji przed płatnym B."""
        ...

    def mark_single_research_run_complete(
        self, research_run_id: str, research_card_id: int, total_cost_usd: float,
    ) -> None: ...

    def add_research_sources(self, research_run_id: str,
                             sources: list[ResearchSourceRecord]) -> list[ResearchSourceRecord]: ...

    def list_research_sources(self, research_run_id: str) -> list[ResearchSourceRecord]: ...

    def mark_research_stage_a_success(
        self, research_run_id: str, sources: list[ResearchSourceRecord],
    ) -> list[ResearchSourceRecord]: ...

    def mark_research_run_failed(self, research_run_id: str, error: str) -> None: ...

    def mark_research_run_partial(self, research_run_id: str, error: str) -> None: ...

    def mark_research_run_complete(self, research_run_id: str, research_card_id: int,
                                   total_cost_usd: float) -> None:
        """Alias legacy `two_stage`; delegacja zachowuje odmowę dla `staged`."""
        ...

    def add_research_stage_result(
        self, research_run_id: str, stage: ResearchStageName,
        status: ResearchStageStatus, error: str | None = None,
        *, finished_at: datetime | None = None,
    ) -> None: ...

    def get_research_usage(self, research_run_id: str) -> list[ModelUsage]: ...

    def sync_run_cost_from_research_usage(self, research_run_id: str) -> float:
        """Idempotentnie ustawia runs.cost_usd na kanoniczną sumę model_usage runu."""
        ...

    # --- etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis) ---

    def create_source_candidates(
        self, research_run_id: str, candidates: list[SourceCandidateRecord],
    ) -> list[SourceCandidateRecord]: ...

    def list_source_candidates(
        self, research_run_id: str, status: SourceCandidateStatus | None = None,
    ) -> list[SourceCandidateRecord]: ...

    def mark_extraction_in_progress(self, research_run_id: str) -> None: ...

    def update_source_candidate_extracted(
        self, candidate_id: int, *, title: str | None, author_or_org: str | None,
        published_at: str | None, source_type: SourceType, supported_claims: list[str],
        numeric_facts: list[str], verification_status: SourceVerification,
        source_quality_score: float,
    ) -> None: ...

    def mark_source_candidate_failed(self, candidate_id: int, error: str) -> None: ...

    def claim_source_candidate_attempt(self, candidate_id: int, *, max_attempts: int) -> int:
        """Atomically claims PENDING below cap: attempts+1 and EXTRACTION_IN_PROGRESS."""
        ...

    def retry_failed_source_candidates(
        self, research_run_id: str, *, max_attempts: int,
    ) -> SourceCandidateRetryResult:
        """Jawnie resetuje tylko EXTRACTION_FAILED z attempts < max_attempts."""
        ...

    def mark_research_run_partial_exhausted(self, research_run_id: str, error: str) -> None: ...

    def mark_sources_complete(self, research_run_id: str) -> None: ...

    def mark_synthesis_pending(self, research_run_id: str) -> None: ...

    def revert_to_sources_complete(self, research_run_id: str, error: str) -> None: ...
