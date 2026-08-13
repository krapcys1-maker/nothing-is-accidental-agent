"""Pełny przepływ researchu dla wybranego (SELECTED) tematu.

Jednoetapowy (`run_research_pipeline`):
[POLICY can_run] -> [research plan] -> [POLICY budget] -> [LLM web search]
-> [ochrona przed injection] -> [koszt] -> [walidacja jakości] -> [zapis SQLite]
-> [aktualizacja dokumentacji]. Treść źródeł jest NIEZAUFANA — nigdy nie jest instrukcją.

Dwuetapowy (`run_two_stage_research_pipeline`, ZALECANY od 2026-07-11, ADR-016):
[POLICY can_run] -> [plan] -> [POLICY budget etap1] -> [gather_sources: TYLKO search]
-> [injection guard] -> [koszt etap1] -> [za mało źródeł? STOP, bez płacenia za etap2]
-> [POLICY budget etap2] -> [synthesize_card: TYLKO analiza, zero search]
-> [koszt etap2] -> [walidacja jakości] -> [zapis SQLite] -> [dokumentacja].
Powód: pierwsze realne wywołanie jednoetapowe kosztowało 0.25 USD przy szacunku
0.095 USD (błąd ~+163%) i zakończyło się uciętym JSON-em — patrz
docs/ERRORS_AND_FAILURES.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import sys
from typing import Callable

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.ids import new_run_id
from app.core.money import decimal_from, sum_usd, usd_float
from app.core.sanitization import sanitize_persistent_text
from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import (
    Account,
    DurableProviderAttemptContext,
    JobExecutionContext,
    ResearchExecutionFailureOutcome,
    ResearchCard,
    ResearchFlow,
    ResearchJobExecution,
    ResearchRecommendation,
    ResearchRun,
    ResearchRunStatus,
    ResearchSourceRecord,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    RunStatus,
    Source,
    SourceCandidateRecord,
    SourceCandidateRetryResult,
    SourceCandidateStatus,
    SourceVerification,
    StagedFinalizationContext,
    StagedFinalizationMode,
    Topic,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import NotificationPort
from app.ports.storage import (
    BudgetReservationError,
    EvidenceResearchAuthorizationError,
    ProviderAttemptOverReservationError,
    ProviderAttemptReconciliationRequired,
    StoragePort,
)
from app.research import injection_guard
from app.research.durable_intent import (
    DEFAULT_REQUEST_MAX_TOKENS,
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    canonicalize_durable_research_payload,
)
from app.research.evidence import EvidenceVerificationError
from app.research.base import (
    AttemptBudgetContext,
    DEFAULT_SYNTHESIS_MAX_TOKENS,
    DurableProviderAttemptContextError,
    GatheredSource,
    ResearchClient,
    ResearchBudgetError,
    ResearchConnectionError,
    ResearchError,
    ResearchTimeout,
    ResearchUnknownProviderError,
    ResearchPlan,
    SourceCandidate,
    SourceCardDraft,
    SourceGatheringResult,
)
from app.research.cost_estimator import (
    estimate_discovery_cost_usd,
    estimate_extraction_cost_per_source_usd,
    estimate_no_search_call_usd,
    estimate_synthesis_cost_usd,
    estimate_with_retries,
    estimate_worst_case_search_call_usd,
)
from app.research.diagnostics import ResponseDiagnostics, write_diagnostics
from app.research.source_admission import (
    descriptors_from_research_card,
    evaluate_source_admission,
)
from app.research.validation import (
    TOO_FEW_SOURCES,
    ValidationOutcome,
    count_distinct_verified_evidence_sources,
    validate_draft,
)


@dataclass
class ResearchRunSummary:
    run_id: str | None
    account_id: str
    topic_id: int
    dry_run: bool
    model: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0
    passed: bool = False
    recommendation: str = "REJECT"
    reasons: list[str] = field(default_factory=list)
    sources_count: int = 0
    injection_flags: int = 0
    error: str | None = None
    blocked: bool = False
    block_code: str | None = None
    block_reason: str | None = None
    card: ResearchCard | None = None
    # --- etapowy A1/A2/B (2026-07-12) ---
    candidates_discovered: int = 0
    sources_extracted: int = 0
    sources_failed: int = 0


ResearchLogWriter = Callable[[ResearchCard, Topic, "ResearchRunSummary"], None]
_LOGGER = logging.getLogger(__name__)
_AUDIT_ERROR_MESSAGE_LIMIT = 500
class ResearchExecutionAlreadyInitialized(RuntimeError):
    """Worker znalazł już trwały run; kontynuacja wymaga jawnej weryfikacji."""


class ResearchExecutionNeedsReconciliation(RuntimeError):
    """Wynik requestu jest niejednoznaczny; automatyczne wznowienie jest zakazane."""


class ResearchExecutionRequiresDurableJob(RuntimeError):
    """Fresh real research cannot bypass the durable job/lease/fence boundary."""


class ResearchResumeRequiresDurableJob(RuntimeError):
    """Real A2/B resume is deferred until it has its own durable job flow."""


class DurablePromptSourceSnapshotMismatch(DurableProviderAttemptContextError):
    """Mutable dispatch input diverged from the frozen durable prompt input."""


def _reject_non_durable_real_resume(settings: Settings, research_client: ResearchClient) -> None:
    """Fail before any workflow mutation for unsupported real A2/B resumes."""
    if (
        not settings.dry_run
        and bool(getattr(research_client, "requires_durable_provider_context", False))
    ):
        raise ResearchResumeRequiresDurableJob(
            "Real A2/B resume requires a durable job; WAVE 1A has not implemented "
            "that scheduler flow. No workflow state was changed."
        )


def _best_effort_worker_terminal_diagnostic(effect: Callable[[], None], *, label: str) -> None:
    """Keep post-commit diagnostics from rewriting a worker's canonical result."""
    try:
        effect()
    except Exception as exc:
        _LOGGER.warning(
            "WORKER_TERMINAL_DIAGNOSTIC_FAILED label=%s error=%s",
            label,
            type(exc).__name__,
        )


def _sanitize_audit_error_text(value: object, *, limit: int) -> str:
    text = " ".join(
        sanitize_persistent_text(value, preserve_safe_labels=True).split()
    )
    if len(text) > limit:
        text = f"{text[:limit - 3]}..."
    return text


def _format_audit_error(stage: str, exc: Exception) -> str:
    """Return a deterministic, bounded audit string without provider payloads.

    Only the exception message and selected scalar metadata are used.  In
    particular, ``raw_text``, the SDK exception object/cause, request headers
    and response objects are never serialized into persistent audit fields.
    """
    metadata = []
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        metadata.append(f"status_code={status_code}")
    retryable = getattr(exc, "retryable", None)
    if retryable is not None:
        metadata.append(f"retryable={retryable}")
    stop_reason = getattr(exc, "stop_reason", None)
    if stop_reason is not None:
        safe_stop_reason = _sanitize_audit_error_text(stop_reason, limit=80)
        metadata.append(f"stop_reason={safe_stop_reason}")

    type_and_metadata = type(exc).__name__
    if metadata:
        type_and_metadata = f"{type_and_metadata}({', '.join(metadata)})"
    message = _sanitize_audit_error_text(exc, limit=_AUDIT_ERROR_MESSAGE_LIMIT)
    suffix = f": {message}" if message else ""
    return f"[{stage}] {type_and_metadata}{suffix}"


def _current_run_cost(storage: StoragePort, run_id: str | None) -> float:
    if run_id is None:
        return 0.0
    return float(sum_usd(
        (row.estimated_cost_usd for row in storage.get_research_usage(run_id)),
        label="research usage total",
    ))


def _resolve_max_retries(
    research_client: ResearchClient,
    configured_max_retries: int | None,
) -> int:
    client_max_retries = getattr(research_client, "max_retries", None)
    if configured_max_retries is None:
        return int(client_max_retries) if client_max_retries is not None else 0
    if client_max_retries is not None and configured_max_retries != client_max_retries:
        raise ValueError(
            "max_retries workflowu musi być zgodne z max_retries klienta; "
            "rozbieżność mogłaby zaniżyć estymatę budżetu."
        )
    return configured_max_retries


def _check_stage_budget(
    settings: Settings,
    policy: PolicyEngine,
    account: Account,
    storage: StoragePort,
    run_id: str | None,
    *,
    base_estimate: float,
    max_retries: int,
    run_cap_usd: float | None,
):
    if not settings.dry_run and run_cap_usd is None:
        raise ValueError(
            "Realny research wymaga jawnego run_cap_usd; brak capu jest fail-closed."
        )
    current = _current_run_cost(storage, run_id)
    projected = float(sum_usd(
        (current, estimate_with_retries(base_estimate, max_retries)),
        label="projected research cost",
    ))
    return policy.check_run_budget(
        projected,
        run_cap_usd,
        current_run_cost=current,
        account=account,
    )


def _configure_attempt_control(
    research_client: ResearchClient,
    *,
    policy: PolicyEngine,
    account: Account,
    storage: StoragePort,
    usage_tracker: UsageTracker,
    run_id: str,
    run_cap_usd: float | None,
    estimated_attempt_cost: float,
    task: str,
    dry_run: bool,
    job_execution: JobExecutionContext | None = None,
    before_provider_assertion: Callable[[], None] | None = None,
) -> None:
    """Connect a client retry loop to workflow-owned policy and persistence."""
    if (
        not dry_run
        and job_execution is None
        and bool(getattr(research_client, "requires_durable_provider_context", False))
    ):
        # This is the common last gate before every legacy/two-stage/staged
        # caller. WAVE 0B has a durable implementation only for single flow.
        raise ResearchExecutionRequiresDurableJob(
            "Real two-stage and staged execution require a durable provider "
            "context and are deferred to WAVE 1A."
        )

    requires_durable = bool(getattr(research_client, "requires_durable_provider_context", False))
    configure_durable = getattr(research_client, "configure_durable_attempt_control", None)
    if requires_durable and not callable(configure_durable):
        raise DurableProviderAttemptContextError(
            "Real research client does not expose the required durable-attempt contract."
        )
    if not requires_durable:
        return

    assert callable(configure_durable)

    def assert_prompt_source_snapshot(context: DurableProviderAttemptContext) -> None:
        if before_provider_assertion is None:
            return
        try:
            before_provider_assertion()
        except DurablePromptSourceSnapshotMismatch:
            # REQUEST_STARTED is committed before this final gate. Preserve its
            # identity for explicit reconciliation; never auto-release or retry.
            storage.mark_provider_attempt_needs_reconciliation(
                job_execution, context.request_id,
                error_code="PROMPT_SOURCE_SNAPSHOT_MISMATCH",
            )
            raise

    def context_callback(context: AttemptBudgetContext) -> DurableProviderAttemptContext:
        if job_execution is None:
            raise DurableProviderAttemptContextError(
                "Real Anthropic research requires a durable job execution context."
            )
        if job_execution is not None:
            storage.assert_job_execution_active(job_execution)
        current = _current_run_cost(storage, run_id)
        projected = float(sum_usd(
            (current, context.estimated_attempt_cost),
            label="projected provider attempt cost",
        ))
        decision = policy.check_run_budget(
            projected,
            run_cap_usd,
            current_run_cost=current,
            account=account,
        )
        if not decision.allowed:
            raise ResearchBudgetError(decision.reason, code=decision.code)
        try:
            attempt = storage.begin_provider_attempt(
                job_execution,
                stage=context.stage,
                attempt_no=context.attempt_number,
                max_cost_usd=context.estimated_attempt_cost,
                daily_limit_usd=policy.daily_limit_usd,
                monthly_limit_usd=policy.monthly_limit_usd,
            )
        except BudgetReservationError as exc:
            raise ResearchBudgetError(
                "Atomic provider reservation rejected the request.",
                code="BUDGET_RESERVATION_DENIED",
            ) from exc
        except ProviderAttemptReconciliationRequired as exc:
            raise ResearchExecutionNeedsReconciliation(
                "Provider attempt requires explicit reconciliation before another request."
            ) from exc
        return DurableProviderAttemptContext(
            job_id=job_execution.job_id,
            run_id=job_execution.run_id,
            stage=attempt.stage,
            attempt_no=attempt.attempt_no,
            request_id=attempt.request_id,
            lease_owner=job_execution.lease_owner,
            fence_token=(
                f"{job_execution.job_id}:{job_execution.run_id}:{job_execution.lease_owner}"
            ),
            checked_at=job_execution.now(),
        )

    def activation_callback(context: DurableProviderAttemptContext):
        if context.fence_token != (
            f"{job_execution.job_id}:{job_execution.run_id}:{job_execution.lease_owner}"
        ):
            raise DurableProviderAttemptContextError(
                "Durable provider context fence token does not match the active execution."
            )
        storage.mark_provider_attempt_request_started(job_execution, context.request_id)
        assert_prompt_source_snapshot(context)
        return storage.assert_durable_provider_attempt_active(
            context, clock=job_execution.clock,
        )

    def assertion_callback(context: DurableProviderAttemptContext):
        assert_prompt_source_snapshot(context)
        return storage.assert_durable_provider_attempt_active(
            context, clock=job_execution.clock,
        )

    configure_durable(
        context_callback=context_callback,
        activation_callback=activation_callback,
        assertion_callback=assertion_callback,
        estimated_attempt_cost=estimated_attempt_cost,
    )


def _load_evidence_intent(
    storage: StoragePort, job_id: str,
) -> DurableResearchExecutionIntent | None:
    """Read the persisted durable intent and return it only for evidence mode.

    E3: tryb evidence jest wykrywany WYŁĄCZNIE z trwałego payloadu joba (nigdy
    z pamięci ani ENV), tym samym wzorcem co dispatcher.
    """
    job = storage.get_job(job_id)
    if job is None:
        raise ResearchExecutionRequiresDurableJob(
            "Durable research job disappeared before execution."
        )
    try:
        canonical = canonicalize_durable_research_payload(job.payload)
        intent_raw = canonical["execution_intent"]
        assert isinstance(intent_raw, dict)
        intent = DurableResearchExecutionIntent.from_payload(intent_raw)
    except DurableExecutionIntentError as exc:
        raise ResearchExecutionRequiresDurableJob(
            "Durable research payload is invalid for evidence-mode detection."
        ) from exc
    return intent if intent.evidence_input is not None else None


def _persist_verified_evidence_excerpts(
    storage: StoragePort,
    execution: JobExecutionContext,
    draft,
    corpus,
) -> int:
    """E1-verify and persist model-proposed excerpts; only they grant VERIFIED.

    Provider output nigdy samodzielnie nie nadaje statusu VERIFIED: źródło
    zostaje VERIFIED wyłącznie wtedy, gdy deterministyczny weryfikator E1
    zatwierdził dokładny zakres kanonu i excerpt został trwale zapisany.
    Odrzucony excerpt jest pomijany (źródło zostaje UNVERIFIED) — to decyzja
    editorial, nie awaria pipeline'u.
    """
    excerpts = getattr(draft, "evidence_supporting_excerpts", None) or {}
    by_url = {retrieval.requested_url: retrieval for retrieval in corpus.retrievals}
    verified_urls: set[str] = set()
    for source in draft.sources:
        retrieval = by_url.get(source.url)
        excerpt = excerpts.get(source.url)
        claim = source.supports_claim
        if retrieval is None or not excerpt or not claim or not claim.strip():
            continue
        start = retrieval.canonical_text.find(excerpt)
        if start < 0:
            continue
        try:
            storage.record_job_verified_evidence_excerpt(
                execution,
                int(retrieval.id),
                claim_text=claim,
                excerpt_text=excerpt,
                start_offset=start,
                end_offset=start + len(excerpt),
            )
        except EvidenceVerificationError:
            continue
        verified_urls.add(source.url)
    for source in draft.sources:
        source.verification = (
            SourceVerification.VERIFIED
            if source.url in verified_urls
            else SourceVerification.UNVERIFIED
        )
    return len(verified_urls)


def _mark_budget_block(summary: "ResearchRunSummary", exc: ResearchError) -> None:
    if isinstance(exc, ResearchBudgetError):
        summary.blocked = True
        summary.block_code = exc.code
        summary.block_reason = str(exc)


class CompletedResearchExistsError(RuntimeError):
    """Świeży research wymaga jawnego potwierdzenia, gdy karta już istnieje."""


def ensure_topic_can_start_research(
    storage: StoragePort, account: Account, topic: Topic, force_re_research: bool,
) -> None:
    """Jedyna bramka świeżego researchu: integralność zawsze, force tylko dla re-researchu."""
    has_completed_card = storage.has_valid_completed_research_card_for_topic(
        account.id, int(topic.id),
    )
    if has_completed_card and not force_re_research:
        raise CompletedResearchExistsError(
            f"Temat #{topic.id} ma już kompletną kartę researchu. "
            "Aby rozpocząć nowy, potencjalnie płatny research, podaj --force-re-research."
        )


def _validate_resume_flow(research_run: ResearchRun, expected: ResearchFlow) -> None:
    """Reject cross-flow resume before status checks or any paid work."""
    if research_run.flow != expected:
        raise ValueError(
            f"research_run #{research_run.id}: expected flow '{expected.value}', "
            f"stored flow '{research_run.flow.value}'."
        )


def _validate_research_run_account(research_run: ResearchRun, account: Account) -> None:
    if research_run.account_id != account.id:
        raise ValueError(
            f"research_run #{research_run.id} należy do konta {research_run.account_id}, "
            f"nie do wybranego konta {account.id}."
        )


def _explicit_resume_run_snapshot(
    storage: StoragePort, research_run_id: str, account: Account,
) -> Run:
    run = storage.get_run(research_run_id)
    if run is None:
        raise ValueError(f"Nie znaleziono run #{research_run_id} dla jawnego resume.")
    if run.account_id != account.id:
        raise ValueError(
            f"run #{research_run_id} należy do konta {run.account_id}, "
            f"nie do wybranego konta {account.id}."
        )
    if run.status not in (RunStatus.RUNNING, RunStatus.DRY_RUN, RunStatus.FAILED):
        raise ValueError(
            f"run #{research_run_id} ma terminalny status {run.status.value}; "
            "jawne resume wymaga RUNNING, DRY_RUN albo FAILED."
        )
    if run.status == RunStatus.FAILED and run.finished_at is None:
        raise ValueError(f"run #{research_run_id} ma FAILED bez finished_at.")
    return run


def _staged_finalization_context(
    research_run: ResearchRun,
    run_snapshot: Run,
    *,
    explicit_resume: bool,
) -> StagedFinalizationContext:
    """Build the only legal staged-B mode from durable state, never loose flags."""
    if explicit_resume:
        if run_snapshot.status != RunStatus.FAILED or \
                run_snapshot.finished_at is None or not run_snapshot.error:
            raise ValueError(
                "Resume staged B wymaga trwałego FAILED z finished_at i markerem błędu."
            )
        return StagedFinalizationContext(
            mode=(
                StagedFinalizationMode.FORCE_RERESEARCH_RESUME_B
                if research_run.is_force_reresearch else StagedFinalizationMode.RESUME_B
            ),
            expected_run_status=RunStatus.FAILED,
            expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
            expected_finished_at=run_snapshot.finished_at,
            expected_failure_marker=run_snapshot.error,
        )

    if run_snapshot.status not in (RunStatus.RUNNING, RunStatus.DRY_RUN) or \
            run_snapshot.finished_at is not None or run_snapshot.error is not None:
        raise ValueError(
            "Świeże staged B wymaga trwałego RUNNING/DRY_RUN bez finished_at i błędu."
        )
    return StagedFinalizationContext(
        mode=(
            StagedFinalizationMode.FORCE_RERESEARCH
            if research_run.is_force_reresearch else StagedFinalizationMode.FRESH
        ),
        # Offline dry runs are created as DRY_RUN; real fresh runs are RUNNING.
        # The exact durable status becomes part of the CAS context.
        expected_run_status=run_snapshot.status,
        expected_research_status=ResearchRunStatus.SOURCES_COMPLETE,
    )


def _finish_explicit_resume_failure(
    storage: StoragePort, snapshot: Run, expected_flow: ResearchFlow,
    cost_usd: float, error: str,
) -> None:
    if snapshot.status == RunStatus.FAILED:
        assert snapshot.finished_at is not None
        storage.finish_resumed_research_run(
            snapshot.id, snapshot.account_id, expected_flow,
            snapshot.finished_at, cost_usd, error,
        )
        return
    storage.finish_run(snapshot.id, RunStatus.FAILED.value, cost_usd, error=error)


def _sync_staged_run_cost(
    storage: StoragePort,
    research_run_id: str,
    *,
    preserve_original_error: bool = False,
) -> float | None:
    """Odświeża cache kosztu bez zmiany statusu workflow.

    Gdy pierwotny wyjątek jest już propagowany, błąd synchronizacji trafia do logu,
    aby nie zastępować przyczyny biznesowej mniej istotnym błędem cache'a.
    """
    try:
        return storage.sync_run_cost_from_research_usage(research_run_id)
    except Exception:
        if preserve_original_error:
            _LOGGER.exception(
                "Nie udało się zsynchronizować runs.cost_usd dla research_run %s; "
                "zachowuję pierwotny wyjątek.",
                research_run_id,
            )
            return None
        raise


def _extraction_is_exhausted(
    candidates: list[SourceCandidateRecord], *, min_sources: int, max_attempts: int,
) -> bool:
    """Czy A2 nie ma już legalnego ruchu bez nowego discovery lub podniesienia capu?"""
    extracted = sum(c.status == SourceCandidateStatus.EXTRACTED for c in candidates)
    if extracted >= min_sources:
        return False
    return not any(
        (c.status == SourceCandidateStatus.PENDING_EXTRACTION and c.attempts < max_attempts)
        or c.status == SourceCandidateStatus.EXTRACTION_IN_PROGRESS
        or (c.status == SourceCandidateStatus.EXTRACTION_FAILED and c.attempts < max_attempts)
        for c in candidates
    )


def retry_failed_source_candidates(
    research_run_id: str,
    *,
    settings: Settings,
    storage: StoragePort,
    account_id: str,
    max_attempts: int = 2,
) -> SourceCandidateRetryResult:
    """Jawna, bezpłatna operacja przygotowania capped retry A2.

    Nie tworzy klienta modelu, nie zapisuje usage i nie uruchamia ekstrakcji. Zwykłe
    resume nadal czyta wyłącznie kandydatów PENDING_EXTRACTION. PARTIAL_EXHAUSTED
    może zostać odblokowany wyłącznie tą operacją i wyłącznie po jawnym podniesieniu capu.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts musi być dodatnie.")
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    if research_run.account_id != account_id:
        raise ValueError(
            f"research_run #{research_run_id} należy do konta {research_run.account_id}, "
            f"nie do wybranego konta {account_id}."
        )
    _validate_resume_flow(research_run, ResearchFlow.STAGED)
    if research_run.status not in (
        ResearchRunStatus.PARTIAL, ResearchRunStatus.PARTIAL_EXHAUSTED,
    ):
        raise ValueError(
            f"research_run #{research_run_id} ma status {research_run.status.value} — "
            "retry-failed-candidates wymaga statusu PARTIAL lub PARTIAL_EXHAUSTED."
        )
    result = storage.retry_failed_source_candidates(
        research_run_id, max_attempts=max_attempts,
    )
    candidates = storage.list_source_candidates(research_run_id)
    if research_run.status == ResearchRunStatus.PARTIAL and _extraction_is_exhausted(
        candidates, min_sources=settings.research_min_sources, max_attempts=max_attempts,
    ):
        storage.mark_research_run_partial_exhausted(
            research_run_id,
            error=("Za mało wyekstrahowanych źródeł i brak kandydatów kwalifikujących się "
                   "do retry w aktualnym limicie attempts."),
        )
    return result


def _record_staged_usage(
    usage_tracker: UsageTracker,
    storage: StoragePort,
    research_run_id: str,
    model: str,
    usage: Usage,
    *,
    task: str,
    dry_run: bool,
):
    """Księguje usage i w finally odświeża cache po zapisie model_usage."""
    try:
        return usage_tracker.record(research_run_id, model, usage, task=task, dry_run=dry_run)
    finally:
        _sync_staged_run_cost(
            storage,
            research_run_id,
            preserve_original_error=sys.exc_info()[0] is not None,
        )


def _finish_staged_summary(
    storage: StoragePort,
    research_run_id: str,
    summary: "ResearchRunSummary",
) -> "ResearchRunSummary":
    """Synchronizuje także bezpłatne/idempotentne wyjścia etapu przed zwrotem."""
    _sync_staged_run_cost(storage, research_run_id)
    return summary


def _record_diagnostics(settings: Settings, run_id: str, stage: str, *, usage: Usage,
                        raw_text: str, stop_reason: str | None,
                        parse_error_location: str | None = None) -> None:
    """Zapisuje surową odpowiedź TYLKO dla realnych wywołań (dry_run=False) i tylko
    gdy faktycznie jest coś do zapisania (FakeResearchClient zostawia raw_text puste
    — nie ma prawdziwej odpowiedzi do zdiagnozowania). Patrz app/research/diagnostics.py."""
    if settings.dry_run or not raw_text:
        return
    write_diagnostics(settings.data_dir, ResponseDiagnostics(
        run_id=run_id, stage=stage, stop_reason=stop_reason,
        input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens, cache_write_tokens=usage.cache_write_tokens,
        web_search_requests=usage.web_search_requests, raw_response=raw_text,
        parse_error_location=parse_error_location,
        thinking_tokens=getattr(usage, "thinking_tokens", 0),
    ))


def build_research_plan(topic: Topic, account: Account) -> ResearchPlan:
    question = topic.question or f"Why does '{topic.title}' work the way it does?"
    return ResearchPlan(
        topic_id=int(topic.id), account_id=account.id, question=question,
        niche=list(account.niche), required_depth="standard",
        guidance="Prefer primary sources; separate fact from interpretation; flag uncertainty.",
    )


def run_research_pipeline(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    job_execution: ResearchJobExecution | None = None,
    force_re_research: bool = False,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
    max_web_searches: int = 6,
    request_max_tokens: int | None = None,
    durable_plan: ResearchPlan | None = None,
) -> ResearchRunSummary:
    max_retries = _resolve_max_retries(research_client, max_retries)
    if isinstance(max_web_searches, bool) or not isinstance(max_web_searches, int) or max_web_searches < 0:
        raise ValueError("max_web_searches musi być liczbą całkowitą >= 0.")
    if request_max_tokens is None:
        if durable_plan is not None and not settings.dry_run:
            raise ResearchExecutionRequiresDurableJob(
                "Durable real research requires its persisted request_max_tokens."
            )
        request_max_tokens = DEFAULT_REQUEST_MAX_TOKENS
    if isinstance(request_max_tokens, bool) or not isinstance(request_max_tokens, int) or request_max_tokens < 1:
        raise ValueError("request_max_tokens must be a positive integer.")
    clock = clock or SystemClock()
    if not settings.dry_run and job_execution is None:
        raise ResearchExecutionRequiresDurableJob(
            "Fresh real research requires a durable leased job execution."
        )
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)
    execution_context: JobExecutionContext | None = None

    # 1. Bramka idempotencji przed polityką, budżetem, runem i klientem.
    ensure_topic_can_start_research(storage, account, topic, force_re_research)

    # 2. Bramka: czy wolno działać?
    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Research zablokowany", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    # 3. Plan researchu (lokalny, bez kosztu).  Durable paid work supplies a
    # canonical plan reconstructed from its persisted execution_intent; it must
    # never be rebuilt from mutable topic/account prompt fields after enqueue.
    if durable_plan is None:
        plan = build_research_plan(topic, account)
        prompt_source_validator = None
    else:
        if durable_plan.topic_id != int(topic.id) or durable_plan.account_id != account.id:
            raise ResearchExecutionRequiresDurableJob(
                "Durable prompt snapshot identity does not match the dispatched account/topic."
            )
        plan = durable_plan

        def prompt_source_validator() -> None:
            current = build_research_plan(topic, account)
            if (
                current.question != plan.question
                or current.niche != plan.niche
                or current.required_depth != plan.required_depth
                or current.guidance != plan.guidance
            ):
                raise DurablePromptSourceSnapshotMismatch(
                    "Current topic/account prompt inputs diverged from the durable snapshot."
                )

    # E3: tryb evidence jest wykrywany z trwałego payloadu joba; jego jedyną
    # projekcją kosztu jest ZAMROŻONA pesymistyczna projekcja intentu — ta sama
    # liczba zasila intent, bramkę Policy Engine i rezerwację (zero osobnych,
    # rozjeżdżających się kalkulacji).
    evidence_intent: DurableResearchExecutionIntent | None = None
    if durable_plan is not None and not settings.dry_run and job_execution is not None:
        evidence_intent = _load_evidence_intent(storage, job_execution.job_id)

    # 3. Bramka budżetu PRZED web search — pesymistyczny, KALIBROWANY szacunek
    # (ADR-016). Poprzedni płaski szacunek (Usage 3500/1500/5) zaniżył realny koszt
    # o ~163% na pierwszym realnym runie (docs/ERRORS_AND_FAILURES.md, 2026-07-11).
    # Uwaga: ta ścieżka (jednoetapowa) jest zachowana, ale NIEZALECANA dla realnych
    # runów — patrz run_two_stage_research_pipeline() niżej.
    if evidence_intent is not None:
        from app.research.durable_intent import evidence_full_envelope_cost_usd

        attempt_cost_ceiling = float(evidence_full_envelope_cost_usd(
            pricing_profile=evidence_intent.pricing_profile,
            max_output_tokens=evidence_intent.max_tokens,
        ))
    else:
        worst_case = estimate_worst_case_search_call_usd(
            settings, max_web_searches=max_web_searches, max_output_tokens=request_max_tokens)
        attempt_cost_ceiling = worst_case.total_usd
    budget = _check_stage_budget(
        settings, policy, account, storage, None, base_estimate=attempt_cost_ceiling,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    if not budget.allowed:
        notifier.notify("warning", "Budżet — stop (research)", budget.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget.code, budget.reason
        return summary

    # 4. Run. Worker Etapu 1 przekazuje trwałe uprawnienie lease; wtedy trzy
    # rekordy (run, research_run, jobs.run_id) muszą powstać w jednej transakcji.
    if job_execution is None:
        run_id = new_run_id()
        run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING
        storage.create_run(Run(id=run_id, account_id=account.id,
                               workflow=WorkflowType.RESEARCH, status=run_status,
                               current_state="research"))
        storage.create_research_run(ResearchRun(
            id=run_id, account_id=account.id, topic_id=int(topic.id),
            flow=ResearchFlow.SINGLE, status=ResearchRunStatus.PENDING,
        ))
    else:
        initialized = storage.initialize_research_run_for_job(
            job_execution.job_id, job_execution.lease_owner, new_run_id(),
            clock=clock,
        )
        run_id = initialized.run.id
        if not initialized.created:
            raise ResearchExecutionAlreadyInitialized(
                "A durable research run is already attached to this active job."
            )
        execution_context = JobExecutionContext(
            job_id=job_execution.job_id,
            lease_owner=job_execution.lease_owner,
            run_id=run_id,
            clock=clock,
        )
        # Pierwszy authoritative checkpoint po atomowym związaniu job→run.
        storage.assert_job_execution_active(execution_context)
    summary.run_id = run_id

    # E3: fail-closed walidacja approvalu i corpusu PRZED rezerwacją attemptu.
    evidence_corpus = None
    before_provider_assertion = prompt_source_validator
    if evidence_intent is not None:
        assert execution_context is not None

        def _fail_evidence_before_reservation(code: str) -> ResearchRunSummary:
            # Rozjazd przed rezerwacją: zero konsumpcji zgody, zero provider
            # attemptu, zero requestu, zero usage, zero kosztu.
            audit_error = f"EVIDENCE_RESEARCH_REFUSED:{code}"
            failure_outcome = storage.fail_or_escalate_job_research_execution(
                execution_context,
                _current_run_cost(storage, run_id),
                error=audit_error,
                terminalize_job=True,
            )
            if failure_outcome is not ResearchExecutionFailureOutcome.TERMINALIZED_FAILED:
                raise ResearchExecutionNeedsReconciliation(
                    "Evidence refusal retained an active reservation for explicit reconciliation."
                )
            summary.error = audit_error
            return summary

        try:
            # Ta walidacja jest zarazem produkcyjnym preflightem finalizacji:
            # temat, jego status i możliwość dopisania ODRĘBNEJ nowej karty są
            # potwierdzane przed rezerwacją, więc niemożliwa finalizacja nigdy
            # nie kosztuje requestu.
            evidence_corpus = storage.load_evidence_research_corpus(execution_context)
        except EvidenceResearchAuthorizationError as exc:
            return _fail_evidence_before_reservation(exc.code)
        if bool(evidence_corpus.force_re_research) != bool(force_re_research):
            # Autorytetem trybu jest wyłącznie zamrożony, zatwierdzony intent.
            return _fail_evidence_before_reservation("RE_RESEARCH_FLAG_MISMATCH")
        configure_evidence = getattr(
            research_client, "configure_evidence_synthesis", None,
        )
        if not callable(configure_evidence):
            return _fail_evidence_before_reservation("EVIDENCE_CLIENT_UNSUPPORTED")
        from app.research.anthropic_client import EvidenceSynthesisDocument

        configure_evidence([
            EvidenceSynthesisDocument(
                retrieval_id=int(retrieval.id),
                url=retrieval.requested_url,
                canonical_text=retrieval.canonical_text,
            )
            for retrieval in evidence_corpus.retrievals
        ])
        base_validator = prompt_source_validator
        expected_fingerprint = evidence_corpus.intent_fingerprint

        def evidence_snapshot_validator() -> None:
            # Ponowna kontrola intentu/approvalu/evidence przy granicy providera
            # (aktualny wzorzec snapshotu): rozjazd po REQUEST_STARTED trafia w
            # istniejący kontrakt NEEDS_RECONCILIATION, nigdy w drugi request.
            if base_validator is not None:
                base_validator()
            try:
                storage.assert_evidence_research_snapshot(
                    execution_context,
                    expected_intent_fingerprint=expected_fingerprint,
                )
            except EvidenceResearchAuthorizationError as snapshot_exc:
                raise DurablePromptSourceSnapshotMismatch(
                    f"evidence snapshot diverged: {snapshot_exc.code}"
                ) from snapshot_exc

        before_provider_assertion = evidence_snapshot_validator

    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=attempt_cost_ceiling, task="research",
        dry_run=settings.dry_run, job_execution=execution_context,
        before_provider_assertion=before_provider_assertion)

    # 5. Wywołanie klienta (web search). Błędy: timeout/parse -> run FAILED.
    try:
        if execution_context is not None:
            storage.assert_job_execution_active(execution_context)
        result = research_client.run_research(plan)
    except ResearchError as exc:
        if execution_context is not None and not settings.dry_run and not isinstance(exc, ResearchBudgetError):
            request_id = getattr(exc, "request_id", None)
            if not request_id:
                raise ResearchExecutionNeedsReconciliation(
                    "Real provider failure has no durable request identity."
                ) from exc
            if isinstance(exc, (ResearchTimeout, ResearchConnectionError, ResearchUnknownProviderError)):
                storage.mark_provider_attempt_needs_reconciliation(
                    execution_context, request_id, error_code=type(exc).__name__,
                )
                raise ResearchExecutionNeedsReconciliation(
                    "Provider outcome is unknown; reservation and request identity were retained."
                ) from exc
            if getattr(exc, "usage", None) is None:
                storage.settle_provider_attempt_without_usage(
                    execution_context, request_id, error_code=type(exc).__name__,
                )
        if execution_context is not None:
            # Utrata lease ma pierwszeństwo: nie wolno utrwalić ani usage, ani FAILED.
            storage.assert_job_execution_active(execution_context)
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("run_research", exc)
        # Nawet gdy research się nie powiódł (np. ucięty/niepoprawny JSON), wywołanie
        # API mogło być realne i kosztować — jeśli wyjątek niesie `usage`, zaksięguj je,
        # żeby rzeczywisty koszt nigdy nie zniknął z model_usage/COSTS.csv.
        cost = 0.0
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            try:
                if execution_context is None:
                    usage_row = usage_tracker.record(
                        run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                        task="research", dry_run=settings.dry_run,
                    )
                else:
                    usage_row = usage_tracker.record_job(
                        execution_context, getattr(exc, "model", None) or "unknown",
                        exc_usage, task="research", dry_run=settings.dry_run,
                        request_id=getattr(exc, "request_id", None),
                    )
            except ProviderAttemptOverReservationError as over_reservation:
                raise ResearchExecutionNeedsReconciliation(
                    "Recorded provider usage exceeded its durable reservation."
                ) from over_reservation
            cost = usage_row.estimated_cost_usd
            summary.cost_usd = cost
            summary.model = getattr(exc, "model", None) or ""
            summary.input_tokens = usage_row.input_tokens
            summary.output_tokens = usage_row.output_tokens
            summary.web_search_requests = usage_row.web_search_requests
        cost = _current_run_cost(storage, run_id)
        summary.cost_usd = cost
        if execution_context is None:
            storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=audit_error)
            storage.mark_research_run_failed(run_id, error=audit_error)
        else:
            failure_outcome = storage.fail_or_escalate_job_research_execution(
                execution_context, cost, error=audit_error, terminalize_job=True,
            )
            if failure_outcome is not ResearchExecutionFailureOutcome.TERMINALIZED_FAILED:
                raise ResearchExecutionNeedsReconciliation(
                    "Research failure retained an active reservation for explicit reconciliation."
                ) from exc
        diagnostic = lambda: _record_diagnostics(
            settings,
            run_id,
            "SINGLE",
            usage=exc_usage or Usage(),
            raw_text=getattr(exc, "raw_text", None) or "",
            stop_reason=getattr(exc, "stop_reason", None),
            parse_error_location=str(exc),
        )
        if execution_context is None:
            diagnostic()
        else:
            _best_effort_worker_terminal_diagnostic(
                diagnostic, label="research_single_failure_diagnostic",
            )
        if execution_context is None:
            notifier.notify("error", "Research nieudany", str(exc), account.id)
        else:
            _best_effort_worker_terminal_diagnostic(
                lambda: notifier.notify("error", "Research nieudany", str(exc), account.id),
                label="research_failure_notification",
            )
        summary.error = str(exc)
        return summary

    if execution_context is not None:
        # Długie wywołanie mogło zakończyć się po expiry/recovery.
        storage.assert_job_execution_active(execution_context)

    draft = result.draft

    # 6. Ochrona przed prompt injection — treść źródeł to niezaufany materiał.
    for src in draft.sources:
        if injection_guard.contains_injection(src.title) or \
                injection_guard.contains_injection(src.supports_claim):
            summary.injection_flags += 1
            src.title = injection_guard.neutralize(src.title)
            if src.supports_claim:
                src.supports_claim = injection_guard.neutralize(src.supports_claim)
    if summary.injection_flags:
        notifier.notify("warning", "Wykryto próbę prompt injection w źródle",
                        f"{summary.injection_flags} źródeł zneutralizowano (treść = dane, nie polecenia).",
                        account.id)

    # 7. Koszt.
    try:
        if execution_context is None:
            usage_row = usage_tracker.record(
                run_id, result.model, result.usage,
                task="research", dry_run=settings.dry_run,
            )
        else:
            usage_row = usage_tracker.record_job(
                execution_context, result.model, result.usage,
                task="research", dry_run=settings.dry_run,
                request_id=getattr(result, "request_id", None),
            )
    except ProviderAttemptOverReservationError as exc:
        raise ResearchExecutionNeedsReconciliation(
            "Recorded provider usage exceeded its durable reservation."
        ) from exc
    summary.cost_usd = _current_run_cost(storage, run_id)
    summary.model = result.model
    summary.input_tokens = usage_row.input_tokens
    summary.output_tokens = usage_row.output_tokens
    summary.web_search_requests = usage_row.web_search_requests

    # 7b. E3: weryfikator E1 kontroluje excerpty i JAKO JEDYNY nadaje VERIFIED;
    # provider output nigdy nie nadaje tego statusu samodzielnie.
    if (
        evidence_intent is not None
        and evidence_corpus is not None
        and execution_context is not None
    ):
        summary.sources_extracted = _persist_verified_evidence_excerpts(
            storage, execution_context, draft, evidence_corpus,
        )

    # 8. Walidacja jakości (bramka). E3: dla evidence research liczba źródeł to
    # liczba ODRĘBNYCH zatwierdzonych retrievali (lineage source→retrieval), nie
    # liczba rekordów source — jeden retrieval zacytowany kilkukrotnie = jedno
    # źródło i przy min_sources musi dać TOO_FEW_SOURCES.
    evidence_source_count = None
    if evidence_intent is not None and evidence_corpus is not None:
        evidence_source_count = count_distinct_verified_evidence_sources(
            draft.sources, evidence_corpus.retrievals,
        )
    outcome = validate_draft(
        draft,
        min_sources=settings.research_min_sources,
        min_confidence=settings.research_min_confidence,
        min_source_quality=settings.research_min_source_quality,
        evidence_source_count=evidence_source_count,
    )
    # 8b. E3 source admission. Holding three retrieval IDs is not evidence:
    # a PROCEED recommendation additionally needs independent, deduplicated,
    # correctly classified sources for this exact approved corpus. The same
    # policy is re-evaluated as a non-bypassable floor inside the finalization
    # transaction; running it here turns a failing corpus into an ordinary
    # editorial REJECT with reason codes instead of a technical failure.
    if (
        evidence_intent is not None
        and evidence_corpus is not None
        and outcome.recommendation is ResearchRecommendation.PROCEED
    ):
        retrieval_ids_by_url = {}
        canonical_by_url = {}
        for retrieval in evidence_corpus.retrievals:
            for url in (retrieval.requested_url, retrieval.final_url):
                if isinstance(url, str) and url:
                    retrieval_ids_by_url[url] = int(retrieval.id)
                    canonical_by_url[url] = str(retrieval.canonical_sha256)
        admission = evaluate_source_admission(
            descriptors_from_research_card(
                [
                    source for source in draft.sources
                    if source.verification is SourceVerification.VERIFIED
                ],
                retrieval_ids_by_url=retrieval_ids_by_url,
                canonical_sha256_by_url=canonical_by_url,
            ),
            confirmed_claims=list(draft.confirmed_claims),
        )
        if not admission.admitted:
            outcome = ValidationOutcome(
                recommendation=ResearchRecommendation.REJECT,
                reasons=list(outcome.reasons) + list(admission.reasons),
            )

    summary.passed = outcome.passed
    summary.recommendation = outcome.recommendation.value
    summary.reasons = list(outcome.reasons)

    # 9. Budowa Research Card + zapis.
    card = ResearchCard(
        topic_id=int(topic.id), question=draft.question, working_thesis=draft.working_thesis,
        main_mechanism=draft.main_mechanism, confirmed_claims=draft.confirmed_claims,
        uncertain_claims=draft.uncertain_claims, contradictions=draft.contradictions,
        strongest_counterargument=draft.strongest_counterargument,
        citable_numbers=draft.citable_numbers, visual_idea=draft.visual_idea,
        confidence_score=draft.confidence_score, source_quality_score=draft.source_quality_score,
        publication_recommendation=outcome.recommendation,
        rejection_reason="; ".join(outcome.reasons) if outcome.reasons else None,
        sources=[
            Source(url=s.url, title=s.title, author_or_org=s.author_or_org,
                   published_at=s.published_at, source_type=s.source_type,
                   supports_claim=s.supports_claim, verification_status=s.verification)
            for s in draft.sources
        ],
    )
    if execution_context is None:
        card = storage.add_research_card(card)
    else:
        storage.assert_job_execution_active(execution_context)
        card = storage.finalize_job_research_execution(
            execution_context, card, total_cost_usd=summary.cost_usd,
            terminal_run_status=(
                RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
            ),
        )
    summary.card = card
    summary.sources_count = len(card.sources)

    # 10. Jedna granica transakcji: COMPLETE + terminalny runs + USED.
    if execution_context is None:
        storage.finalize_research_success(
            run_id, research_card_id=int(card.id), total_cost_usd=summary.cost_usd,
            stage_b_completed=False,
            terminal_run_status=RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS,
        )

    diagnostic = lambda: _record_diagnostics(
        settings,
        run_id,
        "SINGLE",
        usage=result.usage,
        raw_text=getattr(result, "raw_text", ""),
        stop_reason=getattr(result, "stop_reason", None),
    )
    if execution_context is None:
        diagnostic()
    else:
        _best_effort_worker_terminal_diagnostic(
            diagnostic, label="research_single_success_diagnostic",
        )

    # 11. Aktualizacja dokumentacji (opcjonalna — realny run dopisuje do RESEARCH_LOG.md).
    if research_log is not None:
        if execution_context is None:
            research_log(card, topic, summary)
        else:
            _best_effort_worker_terminal_diagnostic(
                lambda: research_log(card, topic, summary), label="research_success_log",
            )

    success_notification = lambda: notifier.notify(
        "info", "Research zakończony",
        f"rekomendacja={summary.recommendation}, źródła={summary.sources_count}, "
        f"koszt~{summary.cost_usd:.6f} USD (dry_run={settings.dry_run})", account.id)
    if execution_context is None:
        success_notification()
    else:
        _best_effort_worker_terminal_diagnostic(
            success_notification, label="research_success_notification",
        )
    return summary


def run_two_stage_research_pipeline(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    max_web_searches: int = 4,
    gather_max_tokens: int = 1200,
    synthesize_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    forwarded_context_tokens: int = 2500,
    force_re_research: bool = False,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
) -> ResearchRunSummary:
    """Dwuetapowy research (ZALECANY od 2026-07-11, ADR-016, docs/ERRORS_AND_FAILURES.md).

    Etap 1 (`gather_sources`): TYLKO web search + zbieranie źródeł/faktów, bez analizy —
    lekki schemat, mniejsze ryzyko ucięcia JSON-a. Jeśli źródeł jest za mało, kończymy
    TU i NIE płacimy za etap 2.
    Etap 2 (`synthesize_card`): TYLKO synteza karty z już zebranych danych, zero web
    search — koszt inputu pod naszą kontrolą (własny, ograniczony kontekst).

    Budżet sprawdzany PRZED KAŻDYM etapem osobno, każdym z osobnym, kalibrowanym
    pesymistycznym szacunkiem (app/research/cost_estimator.py). `max_web_searches`,
    `gather_max_tokens`, `synthesize_max_tokens` muszą odpowiadać wartościom, z jakimi
    zbudowano `research_client` (patrz AnthropicResearchClient) — inaczej szacunek nie
    będzie pasował do realnie stosowanych capów.
    """
    max_retries = _resolve_max_retries(research_client, max_retries)
    clock = clock or SystemClock()
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)

    # 1. Bramka idempotencji przed polityką, budżetem, runem i klientem.
    ensure_topic_can_start_research(storage, account, topic, force_re_research)

    # 2. Bramka: czy wolno działać?
    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Research zablokowany", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    # 2. Plan researchu (lokalny, bez kosztu).
    plan = build_research_plan(topic, account)

    # 3. Bramka budżetu PRZED etapem 1 (kalibrowany pesymistyczny szacunek).
    stage_a_estimate = estimate_worst_case_search_call_usd(
        settings, max_web_searches=max_web_searches, max_output_tokens=gather_max_tokens)
    budget_a = _check_stage_budget(
        settings, policy, account, storage, None, base_estimate=stage_a_estimate.total_usd,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    if not budget_a.allowed:
        notifier.notify("warning", "Budżet — stop (etap 1: gather_sources)",
                        budget_a.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget_a.code, budget_a.reason
        return summary

    # 4. Run (jeden rekord obejmujący oba etapy) + research_runs (stan maszyny stanów).
    run_id = new_run_id()
    summary.run_id = run_id
    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING
    storage.create_run(Run(id=run_id, account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=run_status,
                           current_state="gather_sources"))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.TWO_STAGE, status=ResearchRunStatus.PENDING,
    ))
    total_cost = 0.0

    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=stage_a_estimate.total_usd, task="research_gather",
        dry_run=settings.dry_run)

    # 5. Etap 1: gather_sources. Błąd -> run FAILED, ale realny koszt (jeśli był) zaksięgowany.
    #    Brak trwałych źródeł -> nie ma czego wznawiać (research_runs.status=FAILED).
    try:
        gathered = research_client.gather_sources(plan)
    except ResearchError as exc:
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("gather_sources", exc)
        cost = 0.0
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_gather", dry_run=settings.dry_run,
            )
            cost = usage_row.estimated_cost_usd
            summary.model = getattr(exc, "model", None) or ""
            summary.input_tokens = usage_row.input_tokens
            summary.output_tokens = usage_row.output_tokens
            summary.web_search_requests = usage_row.web_search_requests
        total_cost = _current_run_cost(storage, run_id)
        summary.cost_usd = total_cost
        storage.finish_run(run_id, RunStatus.FAILED.value, total_cost, error=audit_error)
        storage.mark_research_run_failed(run_id, error=audit_error)
        storage.add_research_stage_result(run_id, ResearchStageName.A,
                                          ResearchStageStatus.FAILED, error=audit_error)
        notifier.notify("error", "Zbieranie źródeł nieudane", str(exc), account.id)
        summary.error = str(exc)
        return summary

    gather_usage_row = usage_tracker.record(run_id, gathered.model, gathered.usage,
                                            task="research_gather", dry_run=settings.dry_run)
    total_cost = _current_run_cost(storage, run_id)
    summary.model = gathered.model

    # 6. Ochrona przed prompt injection — treść źródeł to niezaufany materiał (już tu,
    # bo to pierwszy punkt, w którym surowa treść z internetu wchodzi do systemu).
    for src in gathered.sources:
        if injection_guard.contains_injection(src.title) or \
                any(injection_guard.contains_injection(f) for f in src.key_facts):
            summary.injection_flags += 1
            src.title = injection_guard.neutralize(src.title)
            src.key_facts = [injection_guard.neutralize(f) for f in src.key_facts]
    if summary.injection_flags:
        notifier.notify("warning", "Wykryto próbę prompt injection w źródle (etap 1)",
                        f"{summary.injection_flags} źródeł zneutralizowano.", account.id)

    # 6a. TRWAŁY zapis wyników etapu 1 — sedno odporności: od tego momentu wyniki
    # wyszukiwania przeżyją awarię etapu 2 albo restart procesu (jeden atomowy zapis:
    # źródła + status=SOURCE_COLLECTED, patrz mark_research_stage_a_success).
    storage.mark_research_stage_a_success(run_id, [
        ResearchSourceRecord(
            research_run_id=run_id, url=s.url, title=s.title, author_or_org=s.author_or_org,
            published_at=s.published_at, source_type=s.source_type,
            key_facts=list(s.key_facts), verification_status=s.verification,
        )
        for s in gathered.sources
    ])
    storage.add_research_stage_result(run_id, ResearchStageName.A, ResearchStageStatus.SUCCESS)

    # 7. Tania bramka wczesnego wyjścia: za mało źródeł -> STOP, NIE płacimy za etap 2.
    # Źródła (i tak) już trwałe od kroku 6a — status zostaje PARTIAL: technicznie
    # "resumable", ale resume_research_stage_b() sam odmówi, bo źródeł nadal będzie
    # za mało (etap 2 nie szuka, więc nie może tego naprawić).
    if len(gathered.sources) < settings.research_min_sources:
        summary.sources_count = len(gathered.sources)
        summary.cost_usd = total_cost
        summary.input_tokens = gather_usage_row.input_tokens
        summary.output_tokens = gather_usage_row.output_tokens
        summary.web_search_requests = gather_usage_row.web_search_requests
        summary.recommendation = ResearchRecommendation.REJECT.value
        summary.reasons = [TOO_FEW_SOURCES]
        error_msg = (f"Za mało źródeł po etapie 1 ({len(gathered.sources)} < "
                     f"{settings.research_min_sources}) — pomijam płatny etap 2.")
        storage.finish_run(run_id, RunStatus.FAILED.value, total_cost, error=error_msg)
        storage.mark_research_run_partial(run_id, error=error_msg)
        notifier.notify(
            "info", "Research zatrzymany po etapie 1 (za mało źródeł)",
            f"{len(gathered.sources)} < {settings.research_min_sources} wymaganych, "
            f"koszt etapu 1: {total_cost:.6f} USD, etap 2 POMINIĘTY.", account.id)
        return summary

    # 8. Bramka budżetu PRZED etapem 2.
    stage_b_estimate = estimate_no_search_call_usd(
        settings, max_output_tokens=synthesize_max_tokens,
        forwarded_context_tokens=forwarded_context_tokens)
    budget_b = _check_stage_budget(
        settings, policy, account, storage, run_id, base_estimate=stage_b_estimate.total_usd,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    if not budget_b.allowed:
        summary.cost_usd = total_cost
        summary.sources_count = len(gathered.sources)
        storage.finish_run(run_id, RunStatus.FAILED.value, total_cost,
                           error=f"Budżet zablokował etap 2 (synthesize_card): {budget_b.reason}")
        notifier.notify("warning", "Budżet — stop (etap 2: synthesize_card)",
                        budget_b.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget_b.code, budget_b.reason
        return summary

    # 9. Etap 2: synthesize_card. Błąd -> run PARTIAL (nie FAILED!) — źródła z etapu 1
    # zostają nietknięte w research_sources, można wznowić WYŁĄCZNIE etap 2
    # (resume_research_stage_b), bez ponownego web search.
    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=stage_b_estimate.total_usd, task="research_synthesize",
        dry_run=settings.dry_run)
    try:
        synthesized = research_client.synthesize_card(plan, gathered)
    except ResearchError as exc:
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("synthesize_card", exc)
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize", dry_run=settings.dry_run,
            )
            total_cost = _current_run_cost(storage, run_id)
        summary.cost_usd = total_cost
        summary.sources_count = len(gathered.sources)
        storage.finish_run(run_id, RunStatus.FAILED.value, total_cost,
                           error=audit_error)
        storage.mark_research_run_partial(run_id, error=audit_error)
        storage.add_research_stage_result(run_id, ResearchStageName.B,
                                          ResearchStageStatus.FAILED, error=audit_error)
        notifier.notify("error", "Synteza karty nieudana — źródła zachowane, można wznowić "
                        "wyłącznie etap 2", str(exc), account.id)
        summary.error = str(exc)
        return summary

    synth_usage_row = usage_tracker.record(run_id, synthesized.model, synthesized.usage,
                                           task="research_synthesize", dry_run=settings.dry_run)
    total_cost = _current_run_cost(storage, run_id)
    summary.cost_usd = total_cost
    summary.input_tokens = gather_usage_row.input_tokens + synth_usage_row.input_tokens
    summary.output_tokens = gather_usage_row.output_tokens + synth_usage_row.output_tokens
    summary.web_search_requests = (
        gather_usage_row.web_search_requests + synth_usage_row.web_search_requests)

    draft = synthesized.draft

    # 10. Ochrona przed injection również na wyjściu etapu 2 (na wypadek, gdyby model
    # przepisał coś z niezaufanej treści źródeł do pól analitycznych).
    if injection_guard.contains_injection(draft.working_thesis) or \
            injection_guard.contains_injection(draft.strongest_counterargument):
        summary.injection_flags += 1
        draft.working_thesis = injection_guard.neutralize(draft.working_thesis)
        if draft.strongest_counterargument:
            draft.strongest_counterargument = injection_guard.neutralize(
                draft.strongest_counterargument)

    # 11. Walidacja jakości (ta sama, deterministyczna bramka co w wersji jednoetapowej).
    outcome = validate_draft(
        draft,
        min_sources=settings.research_min_sources,
        min_confidence=settings.research_min_confidence,
        min_source_quality=settings.research_min_source_quality,
    )
    summary.passed = outcome.passed
    summary.recommendation = outcome.recommendation.value
    summary.reasons = list(outcome.reasons)

    # 12. Budowa Research Card + zapis.
    card = ResearchCard(
        topic_id=int(topic.id), question=draft.question, working_thesis=draft.working_thesis,
        main_mechanism=draft.main_mechanism, confirmed_claims=draft.confirmed_claims,
        uncertain_claims=draft.uncertain_claims, contradictions=draft.contradictions,
        strongest_counterargument=draft.strongest_counterargument,
        citable_numbers=draft.citable_numbers, visual_idea=draft.visual_idea,
        confidence_score=draft.confidence_score, source_quality_score=draft.source_quality_score,
        publication_recommendation=outcome.recommendation,
        rejection_reason="; ".join(outcome.reasons) if outcome.reasons else None,
        sources=[
            Source(url=s.url, title=s.title, author_or_org=s.author_or_org,
                   published_at=s.published_at, source_type=s.source_type,
                   supports_claim=s.supports_claim, verification_status=s.verification)
            for s in draft.sources
        ],
    )
    storage.add_research_card(card)
    summary.card = card
    summary.sources_count = len(card.sources)
    storage.add_research_stage_result(run_id, ResearchStageName.B, ResearchStageStatus.SUCCESS)

    # 13. Jedna granica transakcji: COMPLETE + terminalny runs + USED.
    storage.finalize_research_success(
        run_id, research_card_id=card.id, total_cost_usd=total_cost, stage_b_completed=True,
        terminal_run_status=RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS,
    )

    # 14. Aktualizacja dokumentacji.
    if research_log is not None:
        research_log(card, topic, summary)

    notifier.notify(
        "info", "Research dwuetapowy zakończony",
        f"rekomendacja={summary.recommendation}, źródła={summary.sources_count}, "
        f"koszt~{summary.cost_usd:.6f} USD (etap1+etap2, dry_run={settings.dry_run})",
        account.id)
    return summary


def resume_research_stage_b(
    research_run_id: str,
    account: Account,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    synthesize_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    forwarded_context_tokens: int = 2500,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
) -> ResearchRunSummary:
    """Wznawia WYŁĄCZNIE etap 2 dla już istniejącego `research_run_id` w stanie
    SOURCE_COLLECTED lub PARTIAL. NIGDY nie woła `gather_sources` / web search —
    źródła są odczytywane z `research_sources` (baza), nie z pamięci procesu, więc
    to działa również po pełnym restarcie procesu (prawdziwa odporność na awarię,
    nie tylko "w ramach jednego wywołania funkcji").
    """
    _reject_non_durable_real_resume(settings, research_client)
    max_retries = _resolve_max_retries(research_client, max_retries)
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_research_run_account(research_run, account)
    _validate_resume_flow(research_run, ResearchFlow.TWO_STAGE)
    resume_run_snapshot = _explicit_resume_run_snapshot(storage, research_run_id, account)
    clock = clock or SystemClock()
    if research_run.status not in (ResearchRunStatus.SOURCE_COLLECTED, ResearchRunStatus.PARTIAL):
        raise ValueError(
            f"research_run #{research_run_id} ma status {research_run.status.value} — "
            "wznowienie etapu 2 wymaga statusu SOURCE_COLLECTED lub PARTIAL."
        )

    summary = ResearchRunSummary(run_id=research_run_id, account_id=account.id,
                                 topic_id=research_run.topic_id, dry_run=settings.dry_run)

    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Wznowienie researchu zablokowane", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    topic = next((t for t in storage.list_topics(account.id) if t.id == research_run.topic_id), None)
    if topic is None:
        raise ValueError(f"Nie znaleziono topic #{research_run.topic_id} dla konta {account.id}.")
    plan = build_research_plan(topic, account)

    # Źródła z BAZY, nie z pamięci — to jest sedno wznawialności.
    source_records = storage.list_research_sources(research_run_id)
    if not source_records:
        raise ValueError(
            f"research_run #{research_run_id} nie ma zapisanych źródeł w research_sources "
            "— nie da się wznowić etapu 2 (etap 1 nigdy się nie powiódł?)."
        )

    # Defensywna bramka: jeśli źródeł nadal jest za mało, etap 2 (bez web search)
    # tego nie naprawi — nie płacimy za syntezę, która i tak zostanie odrzucona.
    if len(source_records) < settings.research_min_sources:
        summary.sources_count = len(source_records)
        summary.recommendation = ResearchRecommendation.REJECT.value
        summary.reasons = [TOO_FEW_SOURCES]
        notifier.notify(
            "info", "Wznowienie odrzucone — nadal za mało źródeł",
            f"{len(source_records)} < {settings.research_min_sources}; etap 2 nie szuka, "
            "więc nie może tego naprawić — nie wołam API.", account.id)
        return summary

    gathered = SourceGatheringResult(
        sources=[
            GatheredSource(url=s.url, title=s.title or "", author_or_org=s.author_or_org,
                           published_at=s.published_at, source_type=s.source_type,
                           key_facts=list(s.key_facts), verification=s.verification_status)
            for s in source_records
        ],
        usage=Usage(),  # nieużywane przez synthesize_card — koszt etapu A już w model_usage
        model="",
    )
    summary.sources_count = len(gathered.sources)

    # Koszt dotychczasowy (etap A + ewentualne wcześniejsze nieudane próby etapu B).
    total_cost = _current_run_cost(storage, research_run_id)

    # Bramka budżetu PRZED (ponowną) próbą etapu 2.
    stage_b_estimate = estimate_no_search_call_usd(
        settings, max_output_tokens=synthesize_max_tokens,
        forwarded_context_tokens=forwarded_context_tokens)
    budget_b = _check_stage_budget(
        settings, policy, account, storage, research_run_id,
        base_estimate=stage_b_estimate.total_usd, max_retries=max_retries,
        run_cap_usd=run_cap_usd)
    if not budget_b.allowed:
        summary.cost_usd = total_cost
        notifier.notify("warning", "Budżet — stop (wznowienie etapu 2)",
                        budget_b.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget_b.code, budget_b.reason
        return summary

    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING

    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=research_run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=stage_b_estimate.total_usd, task="research_synthesize",
        dry_run=settings.dry_run)
    try:
        synthesized = research_client.synthesize_card(plan, gathered)
    except ResearchError as exc:
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("synthesize_card", exc)
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                research_run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize", dry_run=settings.dry_run,
            )
            total_cost = _current_run_cost(storage, research_run_id)
        summary.cost_usd = total_cost
        resume_error = audit_error
        storage.mark_research_run_partial(research_run_id, error=resume_error)
        _finish_explicit_resume_failure(
            storage, resume_run_snapshot, ResearchFlow.TWO_STAGE,
            total_cost, resume_error,
        )
        failed_snapshot = storage.get_run(research_run_id)
        if failed_snapshot is None or failed_snapshot.finished_at is None:
            raise RuntimeError(
                f"Staged B failure for {research_run_id} lacks durable finished_at snapshot."
            )
        storage.add_research_stage_result(
            research_run_id, ResearchStageName.B, ResearchStageStatus.FAILED,
            error=audit_error, finished_at=failed_snapshot.finished_at,
        )
        notifier.notify("error", "Wznowienie: synteza karty nadal nieudana "
                        "(źródła pozostają zachowane, można spróbować ponownie)",
                        str(exc), account.id)
        summary.error = str(exc)
        return summary

    synth_usage_row = usage_tracker.record(research_run_id, synthesized.model, synthesized.usage,
                                           task="research_synthesize", dry_run=settings.dry_run)
    total_cost = _current_run_cost(storage, research_run_id)
    summary.cost_usd = total_cost
    summary.model = synthesized.model
    summary.input_tokens = synth_usage_row.input_tokens
    summary.output_tokens = synth_usage_row.output_tokens
    summary.web_search_requests = synth_usage_row.web_search_requests

    draft = synthesized.draft
    if injection_guard.contains_injection(draft.working_thesis) or \
            injection_guard.contains_injection(draft.strongest_counterargument):
        summary.injection_flags += 1
        draft.working_thesis = injection_guard.neutralize(draft.working_thesis)
        if draft.strongest_counterargument:
            draft.strongest_counterargument = injection_guard.neutralize(
                draft.strongest_counterargument)

    outcome = validate_draft(
        draft, min_sources=settings.research_min_sources,
        min_confidence=settings.research_min_confidence,
        min_source_quality=settings.research_min_source_quality,
    )
    summary.passed = outcome.passed
    summary.recommendation = outcome.recommendation.value
    summary.reasons = list(outcome.reasons)

    card = ResearchCard(
        topic_id=int(topic.id), question=draft.question, working_thesis=draft.working_thesis,
        main_mechanism=draft.main_mechanism, confirmed_claims=draft.confirmed_claims,
        uncertain_claims=draft.uncertain_claims, contradictions=draft.contradictions,
        strongest_counterargument=draft.strongest_counterargument,
        citable_numbers=draft.citable_numbers, visual_idea=draft.visual_idea,
        confidence_score=draft.confidence_score, source_quality_score=draft.source_quality_score,
        publication_recommendation=outcome.recommendation,
        rejection_reason="; ".join(outcome.reasons) if outcome.reasons else None,
        sources=[
            Source(url=s.url, title=s.title, author_or_org=s.author_or_org,
                   published_at=s.published_at, source_type=s.source_type,
                   supports_claim=s.supports_claim, verification_status=s.verification)
            for s in draft.sources
        ],
    )
    storage.add_research_card(card)
    summary.card = card
    summary.sources_count = len(card.sources)
    storage.add_research_stage_result(research_run_id, ResearchStageName.B,
                                      ResearchStageStatus.SUCCESS)

    storage.finalize_research_success(
        research_run_id, research_card_id=card.id, total_cost_usd=total_cost,
        stage_b_completed=True,
        terminal_run_status=RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS,
    )

    if research_log is not None:
        research_log(card, topic, summary)

    notifier.notify(
        "info", "Wznowienie researchu zakończone (etap 2)",
        f"rekomendacja={summary.recommendation}, źródła={summary.sources_count}, "
        f"koszt całkowity~{summary.cost_usd:.6f} USD (dry_run={settings.dry_run})", account.id)
    return summary


# ============================================================================
# Etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis)
# (od 2026-07-12, docs/DECISIONS.md ADR-020).
#
# Powód: drugi realny test dwuetapowego researchu (2026-07-12, run 2a3b4bb9) pokazał,
# że nawet lekki schemat gather_sources wciąż jest zbyt kruchy — JEDEN duży JSON
# obejmujący WSZYSTKIE źródła naraz ucina się, i wtedy WSZYSTKIE źródła giną razem,
# nie tylko ostatnie. Ten podział idzie o krok dalej niż ADR-016/019: każde źródło
# to OSOBNE wywołanie API (etap A2), zapisywane do bazy NATYCHMIAST, więc awaria
# źródła N nie ma żadnego wpływu na źródła 1..N-1.
#
# [POLICY can_run] -> [plan] -> [POLICY budżet A1] -> [discover_sources: TYLKO
# search, JSONL url+title] -> [zapis atomowy: kandydaci + DISCOVERY_COMPLETE]
#   -> [POLICY budżet A2, PER ŹRÓDŁO] -> [extract_source x N, PER ŹRÓDŁO, zapis
#      NATYCHMIAST po każdym — sukces LUB błąd, pętla NIE przerywa się na błędzie
#      jednego źródła] -> [próg: >= min_sources? SOURCES_COMPLETE : PARTIAL, STOP]
#     -> [POLICY budżet B] -> [synthesize_from_cards: zero search, z zapisanych kart]
#        -> [walidacja jakości] -> [zapis SQLite] -> [dokumentacja]
# ============================================================================

def run_source_discovery(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    max_searches: int = 3,
    max_output_tokens: int = 600,
    force_re_research: bool = False,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
) -> ResearchRunSummary:
    """Etap A1: TYLKO web search + krótka lista kandydatów URL (JSONL, url+title).
    Zero analizy — najlżejszy możliwy ładunek (patrz app/research/base.py). Kandydaci
    zapisywani ATOMOWO natychmiast po sukcesie (jak dawny etap A, ADR-019) — to
    dopiero PIERWSZY z trzech etapów, nie jedyny. Błąd -> FAILED, nic do wznowienia
    (bez trwałych kandydatów nie ma czego ekstrahować)."""
    max_retries = _resolve_max_retries(research_client, max_retries)
    clock = clock or SystemClock()
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)

    ensure_topic_can_start_research(storage, account, topic, force_re_research)

    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Odkrywanie źródeł zablokowane", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    plan = build_research_plan(topic, account)

    estimate = estimate_discovery_cost_usd(settings, max_searches, max_output_tokens)
    budget = _check_stage_budget(
        settings, policy, account, storage, None, base_estimate=estimate.conservative_usd,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    if not budget.allowed:
        notifier.notify("warning", "Budżet — stop (etap A1: discover_sources)",
                        budget.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget.code, budget.reason
        return summary

    run_id = new_run_id()
    summary.run_id = run_id
    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING
    storage.create_run(Run(id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
                           status=run_status, current_state="discover_sources"))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_PENDING,
        is_force_reresearch=force_re_research,
    ))
    _sync_staged_run_cost(storage, run_id)

    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=estimate.conservative_usd, task="research_discover",
        dry_run=settings.dry_run)

    try:
        discovered = research_client.discover_sources(plan, max_searches)
    except ResearchError as exc:
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("discover_sources", exc)
        cost = 0.0
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = _record_staged_usage(
                usage_tracker, storage, run_id, getattr(exc, "model", None) or "unknown",
                exc_usage, task="research_discover", dry_run=settings.dry_run)
            cost = usage_row.estimated_cost_usd
            summary.model = getattr(exc, "model", None) or ""
            summary.input_tokens = usage_row.input_tokens
            summary.output_tokens = usage_row.output_tokens
            summary.web_search_requests = usage_row.web_search_requests
        summary.cost_usd = _current_run_cost(storage, run_id)
        _record_diagnostics(settings, run_id, "A1", usage=exc_usage or Usage(),
                            raw_text=getattr(exc, "raw_text", "") or "",
                            stop_reason=getattr(exc, "stop_reason", None),
                            parse_error_location=str(exc))
        storage.finish_run(run_id, RunStatus.FAILED.value, summary.cost_usd,
                           error=audit_error)
        storage.mark_research_run_failed(run_id, error=audit_error)
        storage.add_research_stage_result(run_id, ResearchStageName.A1,
                                          ResearchStageStatus.FAILED, error=audit_error)
        notifier.notify("error", "Odkrywanie źródeł nieudane", str(exc), account.id)
        summary.error = str(exc)
        return _finish_staged_summary(storage, run_id, summary)

    usage_row = _record_staged_usage(
        usage_tracker, storage, run_id, discovered.model, discovered.usage,
        task="research_discover", dry_run=settings.dry_run)
    summary.cost_usd = _current_run_cost(storage, run_id)
    summary.model = discovered.model
    summary.input_tokens = usage_row.input_tokens
    summary.output_tokens = usage_row.output_tokens
    summary.web_search_requests = usage_row.web_search_requests
    _record_diagnostics(settings, run_id, "A1", usage=discovered.usage,
                        raw_text=discovered.raw_text, stop_reason=discovered.stop_reason)

    # Ochrona przed prompt injection w tytułach kandydatów — to pierwszy punkt, w
    # którym surowa treść z internetu wchodzi do systemu.
    for c in discovered.candidates:
        if injection_guard.contains_injection(c.title):
            summary.injection_flags += 1
            c.title = injection_guard.neutralize(c.title)
    if summary.injection_flags:
        notifier.notify("warning", "Wykryto próbę prompt injection w tytule kandydata (A1)",
                        f"{summary.injection_flags} tytułów zneutralizowano.", account.id)

    storage.create_source_candidates(run_id, [
        SourceCandidateRecord(research_run_id=run_id, url=c.url, title=c.title)
        for c in discovered.candidates
    ])
    storage.add_research_stage_result(run_id, ResearchStageName.A1, ResearchStageStatus.SUCCESS)
    summary.candidates_discovered = len(discovered.candidates)

    notifier.notify(
        "info", "Odkrywanie źródeł (A1) zakończone",
        f"kandydaci={summary.candidates_discovered}, koszt~{summary.cost_usd:.6f} USD "
        f"(dry_run={settings.dry_run})", account.id)
    return _finish_staged_summary(storage, run_id, summary)


def run_source_extraction(
    research_run_id: str,
    account: Account,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    max_sources: int | None = None,
    max_web_searches_per_source: int = 1,
    max_output_tokens: int = 1500,
    max_attempts: int = 2,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
    explicit_resume: bool = False,
) -> ResearchRunSummary:
    """Etap A2: JEDNO źródło na wywołanie API. Zapisywane do bazy NATYCHMIAST po
    KAŻDYM źródle (sukces LUB błąd) — awaria źródła N nie ma wpływu na 1..N-1, i
    wznowienie po restarcie kontynuuje dokładnie tam, gdzie się skończyło (czyta
    kandydatów PENDING_EXTRACTION z BAZY, nie z pamięci procesu). Wołalne zarówno
    świeżo (zaraz po A1), jak i jawnie jako wznowienie z `explicit_resume=True`."""
    if explicit_resume:
        _reject_non_durable_real_resume(settings, research_client)
    max_retries = _resolve_max_retries(research_client, max_retries)
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_research_run_account(research_run, account)
    _validate_resume_flow(research_run, ResearchFlow.STAGED)
    resume_run_snapshot = (
        _explicit_resume_run_snapshot(storage, research_run_id, account)
        if explicit_resume else None
    )
    if max_attempts < 1:
        raise ValueError("max_attempts musi być dodatnie.")
    clock = clock or SystemClock()
    if research_run.status == ResearchRunStatus.PARTIAL_EXHAUSTED:
        raise ValueError(
            f"research_run #{research_run_id} is PARTIAL_EXHAUSTED; no candidates are eligible "
            "for retry under the current attempts cap."
        )
    if research_run.status not in (
        ResearchRunStatus.DISCOVERY_COMPLETE, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
        ResearchRunStatus.PARTIAL,
    ):
        raise ValueError(
            f"research_run #{research_run_id} ma status {research_run.status.value} — "
            "ekstrakcja wymaga DISCOVERY_COMPLETE, EXTRACTION_IN_PROGRESS lub PARTIAL.")

    uncertain = storage.list_source_candidates(
        research_run_id, SourceCandidateStatus.EXTRACTION_IN_PROGRESS,
    )
    if uncertain:
        raise ValueError(
            f"research_run #{research_run_id} has {len(uncertain)} candidate(s) in "
            "EXTRACTION_IN_PROGRESS; ordinary resume refuses uncertain A2 attempts and "
            "requires explicit recovery."
        )

    summary = ResearchRunSummary(run_id=research_run_id, account_id=account.id,
                                 topic_id=research_run.topic_id, dry_run=settings.dry_run)
    _sync_staged_run_cost(storage, research_run_id)

    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Ekstrakcja źródeł zablokowana", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return _finish_staged_summary(storage, research_run_id, summary)

    topic = next((t for t in storage.list_topics(account.id)
                  if t.id == research_run.topic_id), None)
    if topic is None:
        raise ValueError(f"Nie znaleziono topic #{research_run.topic_id} dla konta {account.id}.")
    plan = build_research_plan(topic, account)

    storage.mark_extraction_in_progress(research_run_id)

    pending = storage.list_source_candidates(
        research_run_id, SourceCandidateStatus.PENDING_EXTRACTION)
    if max_sources is not None:
        pending = pending[:max_sources]

    total_cost = _current_run_cost(storage, research_run_id)
    per_source_estimate = estimate_extraction_cost_per_source_usd(
        settings, max_web_searches_per_source, max_output_tokens)

    extracted_now = 0
    failed_now = 0
    call_model = ""
    call_input_tokens = 0
    call_output_tokens = 0
    call_web_search_requests = 0
    call_cost = decimal_from("0", label="extraction call cost")
    for candidate_record in pending:
        budget = _check_stage_budget(
            settings, policy, account, storage, research_run_id,
            base_estimate=per_source_estimate.conservative_usd,
            max_retries=max_retries, run_cap_usd=run_cap_usd)
        if not budget.allowed:
            notifier.notify(
                "warning", "Budżet — stop w trakcie etapu A2 (extract_source)",
                f"{budget.reason} — pozostali kandydaci zostają PENDING_EXTRACTION "
                "(nietknięci, można wznowić później).", account.id)
            summary.blocked = True
            summary.block_code, summary.block_reason = budget.code, budget.reason
            break

        try:
            storage.claim_source_candidate_attempt(
                candidate_record.id, max_attempts=max_attempts,
            )
        except ValueError:
            # Another executor may have claimed this snapshot row first, or a stale
            # PENDING row may already be at cap. In both cases this process must not call.
            continue
        candidate = SourceCandidate(url=candidate_record.url, title=candidate_record.title)
        _configure_attempt_control(
            research_client, policy=policy, account=account, storage=storage,
            usage_tracker=usage_tracker, run_id=research_run_id, run_cap_usd=run_cap_usd,
            estimated_attempt_cost=per_source_estimate.conservative_usd,
            task="research_extract", dry_run=settings.dry_run)
        try:
            extraction = research_client.extract_source(plan, candidate)
        except ResearchError as exc:
            _mark_budget_block(summary, exc)
            audit_error = _format_audit_error("extract_source", exc)
            exc_usage = getattr(exc, "usage", None)
            if exc_usage is not None:
                usage_row = _record_staged_usage(
                    usage_tracker, storage, research_run_id,
                    getattr(exc, "model", None) or "unknown", exc_usage,
                    task="research_extract", dry_run=settings.dry_run)
                total_cost = _current_run_cost(storage, research_run_id)
                call_cost += decimal_from(
                    usage_row.estimated_cost_usd, label="extraction call cost",
                )
                call_model = getattr(exc, "model", None) or call_model
                call_input_tokens += usage_row.input_tokens
                call_output_tokens += usage_row.output_tokens
                call_web_search_requests += usage_row.web_search_requests
            _record_diagnostics(
                settings, research_run_id, f"A2_source_{candidate_record.id}",
                usage=exc_usage or Usage(), raw_text=getattr(exc, "raw_text", "") or "",
                stop_reason=getattr(exc, "stop_reason", None), parse_error_location=str(exc))
            storage.mark_source_candidate_failed(candidate_record.id, error=audit_error)
            storage.add_research_stage_result(research_run_id, ResearchStageName.A2,
                                              ResearchStageStatus.FAILED, error=audit_error)
            notifier.notify("warning", f"Ekstrakcja źródła nieudana ({candidate_record.url})",
                            str(exc), account.id)
            failed_now += 1
            if isinstance(exc, ResearchBudgetError):
                break
            continue

        usage_row = _record_staged_usage(
            usage_tracker, storage, research_run_id, extraction.model, extraction.usage,
            task="research_extract", dry_run=settings.dry_run)
        total_cost = _current_run_cost(storage, research_run_id)
        call_cost += decimal_from(
            usage_row.estimated_cost_usd, label="extraction call cost",
        )
        call_model = extraction.model or call_model
        call_input_tokens += usage_row.input_tokens
        call_output_tokens += usage_row.output_tokens
        call_web_search_requests += usage_row.web_search_requests
        _record_diagnostics(settings, research_run_id, f"A2_source_{candidate_record.id}",
                            usage=extraction.usage, raw_text=extraction.raw_text,
                            stop_reason=extraction.stop_reason)

        card = extraction.card
        # P0-2a (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): gdy etap A2 nie miał dostępu do
        # narzędzia wyszukiwania (max_web_searches_per_source<=0), model nie miał jak
        # NAPRAWDĘ zweryfikować źródła — samoocena "VERIFIED" w tej sytuacji byłaby
        # dokładnie tym, przed czym projekt ma chronić (wiedza modelu zastępująca dowód).
        # Wymuszamy UNVERIFIED deterministycznie, niezależnie od tego, co zwrócił model.
        if max_web_searches_per_source <= 0:
            card.verification = SourceVerification.UNVERIFIED

        # Ochrona przed prompt injection — treść wyekstrahowana z internetu to dane.
        if injection_guard.contains_injection(card.title) or \
                any(injection_guard.contains_injection(c) for c in card.supported_claims) or \
                any(injection_guard.contains_injection(f) for f in card.numeric_facts):
            summary.injection_flags += 1
            card.title = injection_guard.neutralize(card.title)
            card.supported_claims = [injection_guard.neutralize(c) for c in card.supported_claims]
            card.numeric_facts = [injection_guard.neutralize(f) for f in card.numeric_facts]

        storage.update_source_candidate_extracted(
            candidate_record.id, title=card.title, author_or_org=card.author_or_org,
            published_at=card.published_at, source_type=card.source_type,
            supported_claims=card.supported_claims, numeric_facts=card.numeric_facts,
            verification_status=card.verification, source_quality_score=card.source_quality_score,
        )
        storage.add_research_stage_result(research_run_id, ResearchStageName.A2,
                                          ResearchStageStatus.SUCCESS)
        extracted_now += 1

    if summary.injection_flags:
        notifier.notify(
            "warning", "Wykryto próbę prompt injection w wyekstrahowanym źródle (A2)",
            f"{summary.injection_flags} kart zneutralizowano.", account.id)

    all_extracted = storage.list_source_candidates(research_run_id, SourceCandidateStatus.EXTRACTED)
    summary.candidates_discovered = len(storage.list_source_candidates(research_run_id))
    summary.sources_extracted = extracted_now
    summary.sources_failed = failed_now
    summary.sources_count = len(all_extracted)
    # Naprawa błędu wyświetlania CLI (docs/BUILD_LOG.md Etap 1L): agregacja z WSZYSTKICH
    # wywołań A2 wykonanych w TYM wywołaniu funkcji (nie z prior_usage — to samo rozróżnienie
    # co "koszt tego wywołania" vs "koszt całego runu dotąd"). Pełny koszt runu
    # pozostaje kanonicznie zapisany w model_usage/runs; summary opisuje bieżącą A2.
    summary.model = call_model
    summary.input_tokens = call_input_tokens
    summary.output_tokens = call_output_tokens
    summary.web_search_requests = call_web_search_requests
    summary.cost_usd = usd_float(call_cost, label="extraction call cost")

    all_candidates = storage.list_source_candidates(research_run_id)
    if len(all_extracted) >= settings.research_min_sources:
        storage.mark_sources_complete(research_run_id)
        notifier.notify(
            "info", "Ekstrakcja źródeł (A2) zakończona — gotowe do syntezy",
            f"wyekstrahowano={len(all_extracted)}, nieudane={failed_now}, "
            f"koszt dotąd~{total_cost:.6f} USD", account.id)
    else:
        error_msg = (f"Za mało wyekstrahowanych źródeł ({len(all_extracted)} < "
                     f"{settings.research_min_sources}) po etapie A2.")
        if _extraction_is_exhausted(
            all_candidates, min_sources=settings.research_min_sources,
            max_attempts=max_attempts,
        ):
            error_msg += " Brak kandydatów legalnych w aktualnym attempts cap."
            storage.mark_research_run_partial_exhausted(research_run_id, error=error_msg)
        else:
            storage.mark_research_run_partial(research_run_id, error=error_msg)
        summary.recommendation = ResearchRecommendation.REJECT.value
        summary.reasons = [TOO_FEW_SOURCES]
        if resume_run_snapshot is None:
            storage.finish_run(
                research_run_id, RunStatus.FAILED.value, total_cost, error=error_msg,
            )
        else:
            _finish_explicit_resume_failure(
                storage, resume_run_snapshot, ResearchFlow.STAGED,
                total_cost, error_msg,
            )
        notifier.notify(
            "info", "Ekstrakcja zatrzymana (za mało źródeł) — etap B pominięty",
            f"{len(all_extracted)} < {settings.research_min_sources}, "
            f"koszt dotąd~{total_cost:.6f} USD.", account.id)

    return _finish_staged_summary(storage, research_run_id, summary)


def run_synthesis_from_cards(
    research_run_id: str,
    account: Account,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    synthesize_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    forwarded_context_tokens: int = 2500,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
    explicit_resume: bool = False,
) -> ResearchRunSummary:
    """Etap B: synteza WYŁĄCZNIE z już wyekstrahowanych Source Cards (etap A2). Zero
    web search. Błąd -> status WRACA do SOURCES_COMPLETE (źródła nietknięte) — można
    ponowić WYŁĄCZNIE ten etap z `explicit_resume=True`, bez powtarzania A1/A2."""
    if explicit_resume:
        _reject_non_durable_real_resume(settings, research_client)
    max_retries = _resolve_max_retries(research_client, max_retries)
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_research_run_account(research_run, account)
    _validate_resume_flow(research_run, ResearchFlow.STAGED)
    resume_run_snapshot = (
        _explicit_resume_run_snapshot(storage, research_run_id, account)
        if explicit_resume else None
    )
    current_run_snapshot = resume_run_snapshot or storage.get_run(research_run_id)
    if current_run_snapshot is None:
        raise ValueError(f"Nie znaleziono run #{research_run_id} dla staged B.")

    uncertain = storage.list_source_candidates(
        research_run_id, SourceCandidateStatus.EXTRACTION_IN_PROGRESS,
    )
    if uncertain:
        raise ValueError(
            f"research_run #{research_run_id} has {len(uncertain)} candidate(s) in "
            "EXTRACTION_IN_PROGRESS; ordinary resume requires explicit recovery."
        )
    clock = clock or SystemClock()
    if research_run.status != ResearchRunStatus.SOURCES_COMPLETE:
        raise ValueError(
            f"research_run #{research_run_id} ma status {research_run.status.value} — "
            "synteza wymaga statusu SOURCES_COMPLETE.")

    summary = ResearchRunSummary(run_id=research_run_id, account_id=account.id,
                                 topic_id=research_run.topic_id, dry_run=settings.dry_run)
    _sync_staged_run_cost(storage, research_run_id)

    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Synteza zablokowana", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return _finish_staged_summary(storage, research_run_id, summary)

    topic = next((t for t in storage.list_topics(account.id)
                  if t.id == research_run.topic_id), None)
    if topic is None:
        raise ValueError(f"Nie znaleziono topic #{research_run.topic_id} dla konta {account.id}.")
    plan = build_research_plan(topic, account)

    extracted = storage.list_source_candidates(research_run_id, SourceCandidateStatus.EXTRACTED)
    if len(extracted) < settings.research_min_sources:
        # Nie powinno się zdarzyć (mark_sources_complete już to gwarantuje), ale
        # defensywnie: etap B nie ekstrahuje, więc nie naprawi tego samodzielnie.
        summary.sources_count = len(extracted)
        summary.recommendation = ResearchRecommendation.REJECT.value
        summary.reasons = [TOO_FEW_SOURCES]
        notifier.notify(
            "info", "Synteza odrzucona — nadal za mało wyekstrahowanych źródeł",
            f"{len(extracted)} < {settings.research_min_sources}; nie wołam API.", account.id)
        return _finish_staged_summary(storage, research_run_id, summary)

    terminal_run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    finalization_context = _staged_finalization_context(
        research_run, current_run_snapshot, explicit_resume=explicit_resume,
    )
    # Before the budget/provider path, prove that B can later commit legally.
    storage.preflight_staged_finalization(
        research_run_id, terminal_run_status=terminal_run_status,
        context=finalization_context,
    )

    cards = [
        SourceCardDraft(
            url=r.url, title=r.title, author_or_org=r.author_or_org,
            published_at=r.published_at, source_type=r.source_type,
            supported_claims=list(r.supported_claims), numeric_facts=list(r.numeric_facts),
            verification=r.verification_status, source_quality_score=r.source_quality_score,
        )
        for r in extracted
    ]
    summary.sources_count = len(cards)

    total_cost = _current_run_cost(storage, research_run_id)

    estimate = estimate_synthesis_cost_usd(settings, synthesize_max_tokens, forwarded_context_tokens)
    budget = _check_stage_budget(
        settings, policy, account, storage, research_run_id,
        base_estimate=estimate.conservative_usd, max_retries=max_retries,
        run_cap_usd=run_cap_usd)
    if not budget.allowed:
        summary.cost_usd = total_cost
        notifier.notify("warning", "Budżet — stop (etap B: synthesize_from_cards)",
                        budget.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget.code, budget.reason
        return _finish_staged_summary(storage, research_run_id, summary)

    storage.mark_synthesis_pending(research_run_id)

    _configure_attempt_control(
        research_client, policy=policy, account=account, storage=storage,
        usage_tracker=usage_tracker, run_id=research_run_id, run_cap_usd=run_cap_usd,
        estimated_attempt_cost=estimate.conservative_usd,
        task="research_synthesize_cards", dry_run=settings.dry_run)
    try:
        synthesized = research_client.synthesize_from_cards(plan, cards)
    except ResearchError as exc:
        _mark_budget_block(summary, exc)
        audit_error = _format_audit_error("synthesize_from_cards", exc)
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = _record_staged_usage(
                usage_tracker, storage, research_run_id,
                getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize_cards", dry_run=settings.dry_run)
            total_cost = _current_run_cost(storage, research_run_id)
        _record_diagnostics(settings, research_run_id, "B", usage=exc_usage or Usage(),
                            raw_text=getattr(exc, "raw_text", "") or "",
                            stop_reason=getattr(exc, "stop_reason", None),
                            parse_error_location=str(exc))
        summary.cost_usd = total_cost
        resume_error = audit_error
        storage.revert_to_sources_complete(research_run_id, error=resume_error)
        if resume_run_snapshot is None:
            storage.finish_run(
                research_run_id, RunStatus.FAILED.value,
                total_cost, error=resume_error,
            )
        else:
            _finish_explicit_resume_failure(
                storage, resume_run_snapshot, ResearchFlow.STAGED,
                total_cost, resume_error,
            )
        failed_snapshot = storage.get_run(research_run_id)
        if failed_snapshot is None or failed_snapshot.finished_at is None:
            raise RuntimeError(
                f"Staged B failure for {research_run_id} lacks durable finished_at snapshot."
            )
        storage.add_research_stage_result(
            research_run_id, ResearchStageName.B, ResearchStageStatus.FAILED,
            error=audit_error, finished_at=failed_snapshot.finished_at,
        )
        notifier.notify("error", "Synteza karty nieudana — źródła zachowane, można ponowić "
                        "wyłącznie etap B", str(exc), account.id)
        summary.error = str(exc)
        return _finish_staged_summary(storage, research_run_id, summary)

    usage_row = _record_staged_usage(
        usage_tracker, storage, research_run_id, synthesized.model, synthesized.usage,
        task="research_synthesize_cards", dry_run=settings.dry_run)
    total_cost = _current_run_cost(storage, research_run_id)
    _record_diagnostics(settings, research_run_id, "B", usage=synthesized.usage,
                        raw_text=synthesized.raw_text, stop_reason=synthesized.stop_reason)

    summary.cost_usd = total_cost
    summary.model = synthesized.model
    summary.input_tokens = usage_row.input_tokens
    summary.output_tokens = usage_row.output_tokens
    summary.web_search_requests = usage_row.web_search_requests

    draft = synthesized.draft
    if injection_guard.contains_injection(draft.working_thesis) or \
            injection_guard.contains_injection(draft.strongest_counterargument):
        summary.injection_flags += 1
        draft.working_thesis = injection_guard.neutralize(draft.working_thesis)
        if draft.strongest_counterargument:
            draft.strongest_counterargument = injection_guard.neutralize(
                draft.strongest_counterargument)

    # P0-2b (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): dla REALNYCH runów wymagamy, żeby
    # co najmniej `research_min_sources` źródeł było faktycznie VERIFIED, nie tylko
    # nie-FAILED — inaczej karta zbudowana z samych UNVERIFIED (np. etap A2 bez dostępu
    # do wyszukiwania, patrz run_source_extraction niżej) przechodziłaby bramkę. W
    # dry_run zostaje 0 (nieaktywne) — zero wpływu na dotychczasowe testy/demo.
    min_verified = settings.research_min_sources if not settings.dry_run else 0
    outcome = validate_draft(
        draft, min_sources=settings.research_min_sources,
        min_confidence=settings.research_min_confidence,
        min_source_quality=settings.research_min_source_quality,
        min_verified_sources=min_verified,
    )
    summary.passed = outcome.passed
    summary.recommendation = outcome.recommendation.value
    summary.reasons = list(outcome.reasons)

    card = ResearchCard(
        topic_id=int(topic.id), question=draft.question, working_thesis=draft.working_thesis,
        main_mechanism=draft.main_mechanism, confirmed_claims=draft.confirmed_claims,
        uncertain_claims=draft.uncertain_claims, contradictions=draft.contradictions,
        strongest_counterargument=draft.strongest_counterargument,
        citable_numbers=draft.citable_numbers, visual_idea=draft.visual_idea,
        confidence_score=draft.confidence_score, source_quality_score=draft.source_quality_score,
        publication_recommendation=outcome.recommendation,
        rejection_reason="; ".join(outcome.reasons) if outcome.reasons else None,
        sources=[
            Source(url=s.url, title=s.title, author_or_org=s.author_or_org,
                   published_at=s.published_at, source_type=s.source_type,
                   supports_claim=s.supports_claim, verification_status=s.verification)
            for s in draft.sources
        ],
    )
    card = storage.finalize_staged_research_with_card(
        research_run_id, card, total_cost,
        terminal_run_status=RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS,
        min_sources=settings.research_min_sources,
        # REJECT nadal jest kompletną kartą audytową. Wymóg VERIFIED jest więc
        # twardym precondition zapisu tylko dla jakościowo pozytywnego wyniku;
        # inaczej brak search w A2 nie mógłby zostać trwale udokumentowany.
        min_verified_sources=(
            min_verified if outcome.recommendation != ResearchRecommendation.REJECT else 0
        ),
        context=finalization_context,
    )
    summary.card = card
    summary.sources_count = len(card.sources)

    if research_log is not None:
        research_log(card, topic, summary)

    notifier.notify(
        "info", "Synteza (etap B) zakończona",
        f"rekomendacja={summary.recommendation}, źródła={summary.sources_count}, "
        f"koszt całkowity~{summary.cost_usd:.6f} USD (dry_run={settings.dry_run})", account.id)
    return _finish_staged_summary(storage, research_run_id, summary)


def run_staged_research_pipeline(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    discovery_max_searches: int = 3,
    discovery_max_tokens: int = 600,
    max_sources: int | None = None,
    max_web_searches_per_source: int = 1,
    extraction_max_tokens: int = 1500,
    max_attempts: int = 2,
    synthesize_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    forwarded_context_tokens: int = 2500,
    force_re_research: bool = False,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
) -> ResearchRunSummary:
    """Świeży, pełny etapowy research: A1 (discovery) -> A2 (extraction, per źródło)
    -> B (synthesis). Zatrzymuje się BEZ przechodzenia dalej, jeśli poprzedni etap
    się nie powiódł/zablokował lub dał za mało źródeł — zero synthesis, jeśli source
    collection się nie powiodła (ta sama zasada co w starym dwuetapowym przepływie)."""
    max_retries = _resolve_max_retries(research_client, max_retries)
    discovery_summary = run_source_discovery(
        account, topic, settings=settings, storage=storage, research_client=research_client,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier, clock=clock,
        max_searches=discovery_max_searches, max_output_tokens=discovery_max_tokens,
        force_re_research=force_re_research, max_retries=max_retries,
        run_cap_usd=run_cap_usd)
    if discovery_summary.blocked or discovery_summary.error or discovery_summary.run_id is None:
        return discovery_summary

    extraction_summary = run_source_extraction(
        discovery_summary.run_id, account, settings=settings, storage=storage,
        research_client=research_client, usage_tracker=usage_tracker, policy=policy,
        notifier=notifier, clock=clock, max_sources=max_sources,
        max_web_searches_per_source=max_web_searches_per_source,
        max_output_tokens=extraction_max_tokens, max_attempts=max_attempts,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    extraction_summary.candidates_discovered = discovery_summary.candidates_discovered

    research_run = storage.get_research_run(discovery_summary.run_id)
    if extraction_summary.blocked or research_run is None or \
            research_run.status != ResearchRunStatus.SOURCES_COMPLETE:
        return extraction_summary

    synthesis_summary = run_synthesis_from_cards(
        discovery_summary.run_id, account, settings=settings, storage=storage,
        research_client=research_client, usage_tracker=usage_tracker, policy=policy,
        notifier=notifier, clock=clock, research_log=research_log,
        synthesize_max_tokens=synthesize_max_tokens,
        forwarded_context_tokens=forwarded_context_tokens,
        max_retries=max_retries, run_cap_usd=run_cap_usd)
    synthesis_summary.candidates_discovered = discovery_summary.candidates_discovered
    synthesis_summary.sources_extracted = extraction_summary.sources_extracted
    synthesis_summary.sources_failed = extraction_summary.sources_failed
    return synthesis_summary


def resume_staged_research(
    research_run_id: str,
    account: Account,
    *,
    settings: Settings,
    storage: StoragePort,
    research_client: ResearchClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
    research_log: ResearchLogWriter | None = None,
    max_sources: int | None = None,
    max_web_searches_per_source: int = 1,
    extraction_max_tokens: int = 1500,
    max_attempts: int = 2,
    synthesize_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    forwarded_context_tokens: int = 2500,
    max_retries: int | None = None,
    run_cap_usd: float | None = None,
) -> ResearchRunSummary:
    """Wznawia DOKŁADNIE JEDEN kolejny etap — nigdy nie kaskaduje automatycznie do
    następnego płatnego etapu (jedno wywołanie = zero automatycznych ponowień, ta
    sama zasada co wszędzie indziej w tym projekcie):
    - DISCOVERY_COMPLETE / EXTRACTION_IN_PROGRESS / PARTIAL -> wznawia WYŁĄCZNIE A2
      (ekstrakcję pozostałych kandydatów PENDING_EXTRACTION), NIGDY nie woła A1.
    - SOURCES_COMPLETE -> wznawia WYŁĄCZNIE B (synteza), NIGDY nie woła A1/A2.
    - inne statusy (DISCOVERY_PENDING/COMPLETE/FAILED oraz statusy starego
      przepływu) -> ValueError, nic do wznowienia tą funkcją."""
    _reject_non_durable_real_resume(settings, research_client)
    max_retries = _resolve_max_retries(research_client, max_retries)
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_research_run_account(research_run, account)
    _validate_resume_flow(research_run, ResearchFlow.STAGED)

    if research_run.status == ResearchRunStatus.PARTIAL_EXHAUSTED:
        raise ValueError(
            f"research_run #{research_run_id} is PARTIAL_EXHAUSTED; no candidates are eligible "
            "for retry under the current attempts cap."
        )

    uncertain = storage.list_source_candidates(
        research_run_id, SourceCandidateStatus.EXTRACTION_IN_PROGRESS,
    )
    if uncertain:
        raise ValueError(
            f"research_run #{research_run_id} has {len(uncertain)} candidate(s) in "
            "EXTRACTION_IN_PROGRESS; ordinary resume requires explicit recovery."
        )

    if research_run.status in (
        ResearchRunStatus.DISCOVERY_COMPLETE, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
        ResearchRunStatus.PARTIAL,
    ):
        return run_source_extraction(
            research_run_id, account, settings=settings, storage=storage,
            research_client=research_client, usage_tracker=usage_tracker, policy=policy,
            notifier=notifier, clock=clock, max_sources=max_sources,
            max_web_searches_per_source=max_web_searches_per_source,
            max_output_tokens=extraction_max_tokens, max_attempts=max_attempts,
            max_retries=max_retries, run_cap_usd=run_cap_usd,
            explicit_resume=True)

    if research_run.status == ResearchRunStatus.SOURCES_COMPLETE:
        return run_synthesis_from_cards(
            research_run_id, account, settings=settings, storage=storage,
            research_client=research_client, usage_tracker=usage_tracker, policy=policy,
            notifier=notifier, clock=clock, research_log=research_log,
            synthesize_max_tokens=synthesize_max_tokens,
            forwarded_context_tokens=forwarded_context_tokens,
            max_retries=max_retries, run_cap_usd=run_cap_usd,
            explicit_resume=True)

    raise ValueError(
        f"research_run #{research_run_id} ma status {research_run.status.value} — "
        "nic do wznowienia (wymagany DISCOVERY_COMPLETE/EXTRACTION_IN_PROGRESS/PARTIAL "
        "dla ekstrakcji, albo SOURCES_COMPLETE dla syntezy).")
