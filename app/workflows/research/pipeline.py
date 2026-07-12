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
from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import (
    Account,
    ResearchCard,
    ResearchFlow,
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
    SourceCandidateStatus,
    SourceVerification,
    Topic,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import NotificationPort
from app.ports.storage import StoragePort
from app.research import injection_guard
from app.research.base import (
    GatheredSource,
    ResearchClient,
    ResearchError,
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
    estimate_worst_case_search_call_usd,
)
from app.research.diagnostics import ResponseDiagnostics, write_diagnostics
from app.research.validation import TOO_FEW_SOURCES, validate_draft


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


def _validate_resume_flow(research_run: ResearchRun, expected: ResearchFlow) -> None:
    """Reject cross-flow resume before status checks or any paid work."""
    if research_run.flow != expected:
        raise ValueError(
            f"research_run #{research_run.id}: expected flow '{expected.value}', "
            f"stored flow '{research_run.flow.value}'."
        )


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
) -> ResearchRunSummary:
    clock = clock or SystemClock()
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)

    # 1. Bramka: czy wolno działać?
    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Research zablokowany", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    # 2. Plan researchu (lokalny, bez kosztu).
    plan = build_research_plan(topic, account)

    # 3. Bramka budżetu PRZED web search — pesymistyczny, KALIBROWANY szacunek
    # (ADR-016). Poprzedni płaski szacunek (Usage 3500/1500/5) zaniżył realny koszt
    # o ~163% na pierwszym realnym runie (docs/ERRORS_AND_FAILURES.md, 2026-07-11).
    # Uwaga: ta ścieżka (jednoetapowa) jest zachowana, ale NIEZALECANA dla realnych
    # runów — patrz run_two_stage_research_pipeline() niżej.
    worst_case = estimate_worst_case_search_call_usd(
        settings, max_web_searches=6, max_output_tokens=3000)
    budget = policy.check_budget(worst_case.total_usd)
    if not budget.allowed:
        notifier.notify("warning", "Budżet — stop (research)", budget.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget.code, budget.reason
        return summary

    # 4. Run.
    run_id = new_run_id()
    summary.run_id = run_id
    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING
    storage.create_run(Run(id=run_id, account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=run_status,
                           current_state="research"))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.SINGLE, status=ResearchRunStatus.PENDING,
    ))

    # 5. Wywołanie klienta (web search). Błędy: timeout/parse -> run FAILED.
    try:
        result = research_client.run_research(plan)
    except ResearchError as exc:
        # Nawet gdy research się nie powiódł (np. ucięty/niepoprawny JSON), wywołanie
        # API mogło być realne i kosztować — jeśli wyjątek niesie `usage`, zaksięguj je,
        # żeby rzeczywisty koszt nigdy nie zniknął z model_usage/COSTS.csv.
        cost = 0.0
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research", dry_run=settings.dry_run,
            )
            cost = usage_row.estimated_cost_usd
            summary.cost_usd = cost
            summary.model = getattr(exc, "model", None) or ""
            summary.input_tokens = usage_row.input_tokens
            summary.output_tokens = usage_row.output_tokens
            summary.web_search_requests = usage_row.web_search_requests
        storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=str(exc))
        storage.mark_research_run_failed(run_id, error=str(exc))
        notifier.notify("error", "Research nieudany", str(exc), account.id)
        summary.error = str(exc)
        return summary

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
    usage_row = usage_tracker.record(run_id, result.model, result.usage,
                                     task="research", dry_run=settings.dry_run)
    summary.cost_usd = usage_row.estimated_cost_usd
    summary.model = result.model
    summary.input_tokens = usage_row.input_tokens
    summary.output_tokens = usage_row.output_tokens
    summary.web_search_requests = usage_row.web_search_requests

    # 8. Walidacja jakości (bramka).
    outcome = validate_draft(
        draft,
        min_sources=settings.research_min_sources,
        min_confidence=settings.research_min_confidence,
        min_source_quality=settings.research_min_source_quality,
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
    card = storage.add_research_card(card)
    summary.card = card
    summary.sources_count = len(card.sources)

    # 10. Zamknięcie runu. P0-1 (AUDYT 2026-07-12): terminal statusu sukcesu musi być
    # SUCCESS dla realnych runów — run_status (RUNNING/DRY_RUN) jest poprawny tylko
    # jako stan POCZĄTKOWY (create_run wyżej), nie końcowy.
    terminal_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    storage.finish_run(run_id, terminal_status.value, usage_row.estimated_cost_usd)
    storage.mark_single_research_run_complete(
        run_id, research_card_id=int(card.id),
        total_cost_usd=usage_row.estimated_cost_usd,
    )

    # 11. Aktualizacja dokumentacji (opcjonalna — realny run dopisuje do RESEARCH_LOG.md).
    if research_log is not None:
        research_log(card, topic, summary)

    notifier.notify(
        "info", "Research zakończony",
        f"rekomendacja={summary.recommendation}, źródła={summary.sources_count}, "
        f"koszt~{summary.cost_usd:.6f} USD (dry_run={settings.dry_run})", account.id)
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
    synthesize_max_tokens: int = 2200,
    forwarded_context_tokens: int = 2500,
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
    clock = clock or SystemClock()
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)

    # 1. Bramka: czy wolno działać?
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
    budget_a = policy.check_budget(stage_a_estimate.total_usd)
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

    # 5. Etap 1: gather_sources. Błąd -> run FAILED, ale realny koszt (jeśli był) zaksięgowany.
    #    Brak trwałych źródeł -> nie ma czego wznawiać (research_runs.status=FAILED).
    try:
        gathered = research_client.gather_sources(plan)
    except ResearchError as exc:
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
        summary.cost_usd = cost
        storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=f"[gather_sources] {exc}")
        storage.mark_research_run_failed(run_id, error=f"[gather_sources] {exc}")
        storage.add_research_stage_result(run_id, ResearchStageName.A,
                                          ResearchStageStatus.FAILED, error=str(exc))
        notifier.notify("error", "Zbieranie źródeł nieudane", str(exc), account.id)
        summary.error = str(exc)
        return summary

    gather_usage_row = usage_tracker.record(run_id, gathered.model, gathered.usage,
                                            task="research_gather", dry_run=settings.dry_run)
    total_cost += gather_usage_row.estimated_cost_usd
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
    budget_b = policy.check_budget(stage_b_estimate.total_usd)
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
    try:
        synthesized = research_client.synthesize_card(plan, gathered)
    except ResearchError as exc:
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize", dry_run=settings.dry_run,
            )
            total_cost += usage_row.estimated_cost_usd
        summary.cost_usd = total_cost
        summary.sources_count = len(gathered.sources)
        storage.finish_run(run_id, RunStatus.FAILED.value, total_cost,
                           error=f"[synthesize_card] {exc}")
        storage.mark_research_run_partial(run_id, error=f"[synthesize_card] {exc}")
        storage.add_research_stage_result(run_id, ResearchStageName.B,
                                          ResearchStageStatus.FAILED, error=str(exc))
        notifier.notify("error", "Synteza karty nieudana — źródła zachowane, można wznowić "
                        "wyłącznie etap 2", str(exc), account.id)
        summary.error = str(exc)
        return summary

    synth_usage_row = usage_tracker.record(run_id, synthesized.model, synthesized.usage,
                                           task="research_synthesize", dry_run=settings.dry_run)
    total_cost += synth_usage_row.estimated_cost_usd
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

    # 13. Zamknięcie runu (koszt = suma obu etapów). P0-1: SUCCESS dla realnych runów.
    terminal_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    storage.finish_run(run_id, terminal_status.value, total_cost)
    storage.mark_research_run_complete(run_id, research_card_id=card.id,
                                       total_cost_usd=total_cost)

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
    synthesize_max_tokens: int = 2200,
    forwarded_context_tokens: int = 2500,
) -> ResearchRunSummary:
    """Wznawia WYŁĄCZNIE etap 2 dla już istniejącego `research_run_id` w stanie
    SOURCE_COLLECTED lub PARTIAL. NIGDY nie woła `gather_sources` / web search —
    źródła są odczytywane z `research_sources` (baza), nie z pamięci procesu, więc
    to działa również po pełnym restarcie procesu (prawdziwa odporność na awarię,
    nie tylko "w ramach jednego wywołania funkcji").
    """
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_resume_flow(research_run, ResearchFlow.TWO_STAGE)
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
    prior_usage = storage.get_research_usage(research_run_id)
    total_cost = sum(u.estimated_cost_usd for u in prior_usage)

    # Bramka budżetu PRZED (ponowną) próbą etapu 2.
    stage_b_estimate = estimate_no_search_call_usd(
        settings, max_output_tokens=synthesize_max_tokens,
        forwarded_context_tokens=forwarded_context_tokens)
    budget_b = policy.check_budget(stage_b_estimate.total_usd)
    if not budget_b.allowed:
        summary.cost_usd = total_cost
        notifier.notify("warning", "Budżet — stop (wznowienie etapu 2)",
                        budget_b.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget_b.code, budget_b.reason
        return summary

    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING

    try:
        synthesized = research_client.synthesize_card(plan, gathered)
    except ResearchError as exc:
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = usage_tracker.record(
                research_run_id, getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize", dry_run=settings.dry_run,
            )
            total_cost += usage_row.estimated_cost_usd
        summary.cost_usd = total_cost
        storage.mark_research_run_partial(research_run_id, error=f"[synthesize_card] {exc}")
        storage.add_research_stage_result(research_run_id, ResearchStageName.B,
                                          ResearchStageStatus.FAILED, error=str(exc))
        notifier.notify("error", "Wznowienie: synteza karty nadal nieudana "
                        "(źródła pozostają zachowane, można spróbować ponownie)",
                        str(exc), account.id)
        summary.error = str(exc)
        return summary

    synth_usage_row = usage_tracker.record(research_run_id, synthesized.model, synthesized.usage,
                                           task="research_synthesize", dry_run=settings.dry_run)
    total_cost += synth_usage_row.estimated_cost_usd
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

    # P0-1: SUCCESS dla realnych runów (nie tylko RUNNING).
    terminal_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    storage.finish_run(research_run_id, terminal_status.value, total_cost)
    storage.mark_research_run_complete(research_run_id, research_card_id=card.id,
                                       total_cost_usd=total_cost)

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
) -> ResearchRunSummary:
    """Etap A1: TYLKO web search + krótka lista kandydatów URL (JSONL, url+title).
    Zero analizy — najlżejszy możliwy ładunek (patrz app/research/base.py). Kandydaci
    zapisywani ATOMOWO natychmiast po sukcesie (jak dawny etap A, ADR-019) — to
    dopiero PIERWSZY z trzech etapów, nie jedyny. Błąd -> FAILED, nic do wznowienia
    (bez trwałych kandydatów nie ma czego ekstrahować)."""
    clock = clock or SystemClock()
    summary = ResearchRunSummary(run_id=None, account_id=account.id,
                                 topic_id=int(topic.id), dry_run=settings.dry_run)

    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Odkrywanie źródeł zablokowane", can_run.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = can_run.code, can_run.reason
        return summary

    plan = build_research_plan(topic, account)

    estimate = estimate_discovery_cost_usd(settings, max_searches, max_output_tokens)
    budget = policy.check_budget(estimate.conservative_usd)
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
    ))
    _sync_staged_run_cost(storage, run_id)

    try:
        discovered = research_client.discover_sources(plan, max_searches)
    except ResearchError as exc:
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
        summary.cost_usd = cost
        _record_diagnostics(settings, run_id, "A1", usage=exc_usage or Usage(),
                            raw_text=getattr(exc, "raw_text", "") or "",
                            stop_reason=getattr(exc, "stop_reason", None),
                            parse_error_location=str(exc))
        storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=f"[discover_sources] {exc}")
        storage.mark_research_run_failed(run_id, error=f"[discover_sources] {exc}")
        storage.add_research_stage_result(run_id, ResearchStageName.A1,
                                          ResearchStageStatus.FAILED, error=str(exc))
        notifier.notify("error", "Odkrywanie źródeł nieudane", str(exc), account.id)
        summary.error = str(exc)
        return _finish_staged_summary(storage, run_id, summary)

    usage_row = _record_staged_usage(
        usage_tracker, storage, run_id, discovered.model, discovered.usage,
        task="research_discover", dry_run=settings.dry_run)
    summary.cost_usd = usage_row.estimated_cost_usd
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
) -> ResearchRunSummary:
    """Etap A2: JEDNO źródło na wywołanie API. Zapisywane do bazy NATYCHMIAST po
    KAŻDYM źródle (sukces LUB błąd) — awaria źródła N nie ma wpływu na 1..N-1, i
    wznowienie po restarcie kontynuuje dokładnie tam, gdzie się skończyło (czyta
    kandydatów PENDING_EXTRACTION z BAZY, nie z pamięci procesu). Wołalne zarówno
    świeżo (zaraz po A1) jak i jako wznowienie (osobne wywołanie, później)."""
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_resume_flow(research_run, ResearchFlow.STAGED)
    clock = clock or SystemClock()
    if research_run.status not in (
        ResearchRunStatus.DISCOVERY_COMPLETE, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
        ResearchRunStatus.PARTIAL,
    ):
        raise ValueError(
            f"research_run #{research_run_id} ma status {research_run.status.value} — "
            "ekstrakcja wymaga DISCOVERY_COMPLETE, EXTRACTION_IN_PROGRESS lub PARTIAL.")

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

    prior_usage = storage.get_research_usage(research_run_id)
    total_cost = sum(u.estimated_cost_usd for u in prior_usage)
    per_source_estimate = estimate_extraction_cost_per_source_usd(
        settings, max_web_searches_per_source, max_output_tokens)

    extracted_now = 0
    failed_now = 0
    call_model = ""
    call_input_tokens = 0
    call_output_tokens = 0
    call_web_search_requests = 0
    call_cost = 0.0
    for candidate_record in pending:
        budget = policy.check_budget(per_source_estimate.conservative_usd)
        if not budget.allowed:
            notifier.notify(
                "warning", "Budżet — stop w trakcie etapu A2 (extract_source)",
                f"{budget.reason} — pozostali kandydaci zostają PENDING_EXTRACTION "
                "(nietknięci, można wznowić później).", account.id)
            summary.blocked = True
            summary.block_code, summary.block_reason = budget.code, budget.reason
            break

        candidate = SourceCandidate(url=candidate_record.url, title=candidate_record.title)
        try:
            extraction = research_client.extract_source(plan, candidate)
        except ResearchError as exc:
            exc_usage = getattr(exc, "usage", None)
            if exc_usage is not None:
                usage_row = _record_staged_usage(
                    usage_tracker, storage, research_run_id,
                    getattr(exc, "model", None) or "unknown", exc_usage,
                    task="research_extract", dry_run=settings.dry_run)
                total_cost += usage_row.estimated_cost_usd
                call_cost += usage_row.estimated_cost_usd
                call_model = getattr(exc, "model", None) or call_model
                call_input_tokens += usage_row.input_tokens
                call_output_tokens += usage_row.output_tokens
                call_web_search_requests += usage_row.web_search_requests
            _record_diagnostics(
                settings, research_run_id, f"A2_source_{candidate_record.id}",
                usage=exc_usage or Usage(), raw_text=getattr(exc, "raw_text", "") or "",
                stop_reason=getattr(exc, "stop_reason", None), parse_error_location=str(exc))
            storage.mark_source_candidate_failed(candidate_record.id, error=str(exc))
            storage.add_research_stage_result(research_run_id, ResearchStageName.A2,
                                              ResearchStageStatus.FAILED, error=str(exc))
            notifier.notify("warning", f"Ekstrakcja źródła nieudana ({candidate_record.url})",
                            str(exc), account.id)
            failed_now += 1
            continue

        usage_row = _record_staged_usage(
            usage_tracker, storage, research_run_id, extraction.model, extraction.usage,
            task="research_extract", dry_run=settings.dry_run)
        total_cost += usage_row.estimated_cost_usd
        call_cost += usage_row.estimated_cost_usd
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
    summary.cost_usd = round(call_cost, 6)

    if len(all_extracted) >= settings.research_min_sources:
        storage.mark_sources_complete(research_run_id)
        notifier.notify(
            "info", "Ekstrakcja źródeł (A2) zakończona — gotowe do syntezy",
            f"wyekstrahowano={len(all_extracted)}, nieudane={failed_now}, "
            f"koszt dotąd~{total_cost:.6f} USD", account.id)
    else:
        error_msg = (f"Za mało wyekstrahowanych źródeł ({len(all_extracted)} < "
                     f"{settings.research_min_sources}) po etapie A2.")
        storage.mark_research_run_partial(research_run_id, error=error_msg)
        summary.recommendation = ResearchRecommendation.REJECT.value
        summary.reasons = [TOO_FEW_SOURCES]
        storage.finish_run(research_run_id, RunStatus.FAILED.value, total_cost, error=error_msg)
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
    synthesize_max_tokens: int = 2200,
    forwarded_context_tokens: int = 2500,
) -> ResearchRunSummary:
    """Etap B: synteza WYŁĄCZNIE z już wyekstrahowanych Source Cards (etap A2). Zero
    web search. Błąd -> status WRACA do SOURCES_COMPLETE (źródła nietknięte) — można
    ponowić WYŁĄCZNIE ten etap, dowolną liczbę razy, bez powtarzania A1/A2."""
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_resume_flow(research_run, ResearchFlow.STAGED)
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

    prior_usage = storage.get_research_usage(research_run_id)
    total_cost = sum(u.estimated_cost_usd for u in prior_usage)

    estimate = estimate_synthesis_cost_usd(settings, synthesize_max_tokens, forwarded_context_tokens)
    budget = policy.check_budget(estimate.conservative_usd)
    if not budget.allowed:
        summary.cost_usd = total_cost
        notifier.notify("warning", "Budżet — stop (etap B: synthesize_from_cards)",
                        budget.reason, account.id)
        summary.blocked = True
        summary.block_code, summary.block_reason = budget.code, budget.reason
        return _finish_staged_summary(storage, research_run_id, summary)

    storage.mark_synthesis_pending(research_run_id)
    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING

    try:
        synthesized = research_client.synthesize_from_cards(plan, cards)
    except ResearchError as exc:
        exc_usage = getattr(exc, "usage", None)
        if exc_usage is not None:
            usage_row = _record_staged_usage(
                usage_tracker, storage, research_run_id,
                getattr(exc, "model", None) or "unknown", exc_usage,
                task="research_synthesize_cards", dry_run=settings.dry_run)
            total_cost += usage_row.estimated_cost_usd
        _record_diagnostics(settings, research_run_id, "B", usage=exc_usage or Usage(),
                            raw_text=getattr(exc, "raw_text", "") or "",
                            stop_reason=getattr(exc, "stop_reason", None),
                            parse_error_location=str(exc))
        summary.cost_usd = total_cost
        storage.revert_to_sources_complete(research_run_id, error=f"[synthesize_from_cards] {exc}")
        storage.add_research_stage_result(research_run_id, ResearchStageName.B,
                                          ResearchStageStatus.FAILED, error=str(exc))
        notifier.notify("error", "Synteza karty nieudana — źródła zachowane, można ponowić "
                        "wyłącznie etap B", str(exc), account.id)
        summary.error = str(exc)
        return _finish_staged_summary(storage, research_run_id, summary)

    usage_row = _record_staged_usage(
        usage_tracker, storage, research_run_id, synthesized.model, synthesized.usage,
        task="research_synthesize_cards", dry_run=settings.dry_run)
    total_cost += usage_row.estimated_cost_usd
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
    storage.add_research_card(card)
    summary.card = card
    summary.sources_count = len(card.sources)
    storage.add_research_stage_result(research_run_id, ResearchStageName.B, ResearchStageStatus.SUCCESS)

    # P0-1: SUCCESS dla realnych runów (nie tylko RUNNING).
    terminal_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    storage.finish_run(research_run_id, terminal_status.value, total_cost)
    storage.mark_research_run_complete(research_run_id, research_card_id=card.id,
                                       total_cost_usd=total_cost)

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
    synthesize_max_tokens: int = 2200,
    forwarded_context_tokens: int = 2500,
) -> ResearchRunSummary:
    """Świeży, pełny etapowy research: A1 (discovery) -> A2 (extraction, per źródło)
    -> B (synthesis). Zatrzymuje się BEZ przechodzenia dalej, jeśli poprzedni etap
    się nie powiódł/zablokował lub dał za mało źródeł — zero synthesis, jeśli source
    collection się nie powiodła (ta sama zasada co w starym dwuetapowym przepływie)."""
    discovery_summary = run_source_discovery(
        account, topic, settings=settings, storage=storage, research_client=research_client,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier, clock=clock,
        max_searches=discovery_max_searches, max_output_tokens=discovery_max_tokens)
    if discovery_summary.blocked or discovery_summary.error or discovery_summary.run_id is None:
        return discovery_summary

    extraction_summary = run_source_extraction(
        discovery_summary.run_id, account, settings=settings, storage=storage,
        research_client=research_client, usage_tracker=usage_tracker, policy=policy,
        notifier=notifier, clock=clock, max_sources=max_sources,
        max_web_searches_per_source=max_web_searches_per_source,
        max_output_tokens=extraction_max_tokens)
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
        forwarded_context_tokens=forwarded_context_tokens)
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
    synthesize_max_tokens: int = 2200,
    forwarded_context_tokens: int = 2500,
) -> ResearchRunSummary:
    """Wznawia DOKŁADNIE JEDEN kolejny etap — nigdy nie kaskaduje automatycznie do
    następnego płatnego etapu (jedno wywołanie = zero automatycznych ponowień, ta
    sama zasada co wszędzie indziej w tym projekcie):
    - DISCOVERY_COMPLETE / EXTRACTION_IN_PROGRESS / PARTIAL -> wznawia WYŁĄCZNIE A2
      (ekstrakcję pozostałych kandydatów PENDING_EXTRACTION), NIGDY nie woła A1.
    - SOURCES_COMPLETE -> wznawia WYŁĄCZNIE B (synteza), NIGDY nie woła A1/A2.
    - inne statusy (DISCOVERY_PENDING/COMPLETE/FAILED oraz statusy starego
      przepływu) -> ValueError, nic do wznowienia tą funkcją."""
    research_run = storage.get_research_run(research_run_id)
    if research_run is None:
        raise ValueError(f"Nie znaleziono research_run #{research_run_id}.")
    _validate_resume_flow(research_run, ResearchFlow.STAGED)

    if research_run.status in (
        ResearchRunStatus.DISCOVERY_COMPLETE, ResearchRunStatus.EXTRACTION_IN_PROGRESS,
        ResearchRunStatus.PARTIAL,
    ):
        return run_source_extraction(
            research_run_id, account, settings=settings, storage=storage,
            research_client=research_client, usage_tracker=usage_tracker, policy=policy,
            notifier=notifier, clock=clock, max_sources=max_sources,
            max_web_searches_per_source=max_web_searches_per_source,
            max_output_tokens=extraction_max_tokens)

    if research_run.status == ResearchRunStatus.SOURCES_COMPLETE:
        return run_synthesis_from_cards(
            research_run_id, account, settings=settings, storage=storage,
            research_client=research_client, usage_tracker=usage_tracker, policy=policy,
            notifier=notifier, clock=clock, research_log=research_log,
            synthesize_max_tokens=synthesize_max_tokens,
            forwarded_context_tokens=forwarded_context_tokens)

    raise ValueError(
        f"research_run #{research_run_id} ma status {research_run.status.value} — "
        "nic do wznowienia (wymagany DISCOVERY_COMPLETE/EXTRACTION_IN_PROGRESS/PARTIAL "
        "dla ekstrakcji, albo SOURCES_COMPLETE dla syntezy).")
