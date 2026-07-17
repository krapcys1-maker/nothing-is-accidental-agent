"""Ściśle ograniczone REALNE uruchomienie research pipeline (Anthropic + web search).

Domyślnie TRZYETAPOWE (--mode three-stage, ZALECANE od 2026-07-12, docs/DECISIONS.md
ADR-020): etap A1 (discover_sources) TYLKO szuka i zwraca krótką listę kandydatów
URL (JSONL, najlżejszy możliwy ładunek); etap A2 (extract_source) analizuje KAŻDE
źródło OSOBNYM wywołaniem API, zapisując je do bazy NATYCHMIAST — awaria źródła N
nie ma wpływu na źródła 1..N-1 (w przeciwieństwie do poprzednich trybów, gdzie
WSZYSTKIE źródła były w jednym wywołaniu i ucięcie kasowało je wszystkie razem);
etap B (synthesize_from_cards) syntetyzuje kartę z już wyekstrahowanych kart, zero
web search. Powód zmiany: drugi realny test dwuetapowego trybu (2026-07-12, temat
#2) pokazał, że nawet lekki schemat etapu 1 wciąż był zbyt kruchy (ucięcie przy
4 źródłach) — patrz docs/ERRORS_AND_FAILURES.md.

Tryb dwuetapowy (--mode two-stage, ADR-016/019) i jednoetapowy (--mode single)
zostają dostępne dla porównania/wznowienia starszych runów, ale są NIEZALECANE dla
nowych runów: pierwsza próba jednoetapowa (2026-07-11, temat #2) kosztowała
REALNIE 0.25 USD przy ówczesnym szacunku 0.095 USD (błąd ~+163%); druga próba,
dwuetapowa (2026-07-12, ten sam temat) kosztowała REALNIE 0.123823 USD i również
skończyła się uciętym JSON-em (etap 1/gather_sources). Żadna z dwóch dotychczasowych
realnych prób nie dała jeszcze udanej Research Card. Pełny opis obu incydentów:
docs/ERRORS_AND_FAILURES.md.

WAŻNE: `--max-cost-usd` to pesymistyczny PRE-RUN cap sprawdzany PRZED wywołaniem —
NIE jest to limit egzekwowany W TRAKCIE pojedynczego żądania API (Anthropic nie
oferuje przerwania pojedynczego, niestreamowanego wywołania w połowie po
osiągnięciu kwoty). Rzeczywistą górną granicę per-wywołanie wyznaczają WYŁĄCZNIE
`max_tokens` (output) i `max_uses` (web search) przekazane do API — `--max-cost-usd`
jest strażnikiem PRZED startem, opartym na estymacji, nie twardym limitem w locie.

Twarde parametry:
  - --max-cost-usd: cap CAŁKOWITEGO pesymistycznego (conservative) szacunku (wszystkie
    etapy razem), z kalibrowanego estymatora (app/research/cost_estimator.py,
    margines bezpieczeństwa >=50%) — PRZERYWA bez wołania API, jeśli przekroczony.
  - --discovery-max-searches / --max-sources / --max-web-searches-per-source:
    [three-stage] dźwignie kosztu etapu A1 (ile szuka) i A2 (ile źródeł ekstrahować,
    ile szuka PER źródło — 0 = ekstrakcja bez wyszukiwania, tylko z URL/tytułu).
  - --max-web-searches: [two-stage/single] cap liczby web searchy w etapie 1.
  - --max-retries: retry tylko dla błędów technicznych/timeout; błąd parsowania
    JSON NIGDY nie jest ponawiany (patrz app/research/anthropic_client.py).
  - --estimate-only: pokaż pełną estymację (wszystkie etapy) i ZAKOŃCZ — zero wywołań API.
  - --resume <research_run_id>: wznów DOKŁADNIE JEDEN kolejny etap (status runu w
    bazie decyduje, który — A2/extraction, B/synthesis dla three-stage, albo etap 2
    dla starszych, legacy runów). NIGDY nie powtarza już wykonanych, płatnych etapów
    — dane wczytywane z bazy. Działa nawet po pełnym restarcie procesu (--topic-id
    nie jest wtedy potrzebny).

Nic nie publikuje, nie generuje artykułu, nie dotyka przeglądarki/Playwrighta —
wyłącznie research jednego, konkretnego tematu (po --topic-id lub wznowienie po --resume).

Użycie:
    python scripts/run_capped_research.py --topic-id 2 --estimate-only
    python scripts/run_capped_research.py --topic-id 2 --max-cost-usd 0.45   # three-stage (domyślne)
    python scripts/run_capped_research.py --topic-id 2 --mode two-stage --max-cost-usd 0.45  # NIEZALECANE
    python scripts/run_capped_research.py --topic-id 2 --mode single --max-cost-usd 0.60     # NIEZALECANE
    python scripts/run_capped_research.py --resume <research_run_id>  # dokładnie jeden kolejny etap
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.clock import SystemClock  # noqa: E402
from app.core.config import (  # noqa: E402
    ConfigError,
    load_settings,
    require_valid_real_provider_pricing,
)
from app.core.money import quantize_usd, sum_usd  # noqa: E402
from app.core.pricing import (  # noqa: E402
    PricingConfigError,
    default_pricing_profiles_path,
    load_pricing_profiles,
    resolve_real_pricing_profile,
)
from app.models import (  # noqa: E402
    Job, JobKind, ResearchFlow, ResearchRunStatus, SourceCandidateStatus, WorkflowType,
)
from app.orchestrator.runner import DEFAULT_ACCOUNT  # noqa: E402
from app.policies.policy_engine import PolicyEngine  # noqa: E402
from app.ports.storage import JobConflictError, ResearchTopicIntegrityError  # noqa: E402
from app.research.base import DEFAULT_SYNTHESIS_MAX_TOKENS  # noqa: E402
from app.research.cost_estimator import (  # noqa: E402
    estimate_extraction_cost_for_sources_usd,
    estimate_no_search_call_usd,
    estimate_staged_research_cost_usd,
    estimate_synthesis_cost_usd,
    estimate_with_retries,
    estimate_worst_case_search_call_usd,
)
from app.research.durable_intent import (  # noqa: E402
    DEFAULT_REQUEST_MAX_TOKENS,
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    controlled_research_job_id,
    controlled_session_contract,
    validate_cli_max_tokens,
)
from app.storage.repositories import SqliteStorage  # noqa: E402
from app.workflows.research.pipeline import (  # noqa: E402
    CompletedResearchExistsError,
    ensure_topic_can_start_research,
    retry_failed_source_candidates,
)

_DEFAULT_MAX_COST = {"three-stage": 0.45, "two-stage": 0.45, "single": 0.60}
_RESUMABLE_STATUSES = {
    ResearchFlow.TWO_STAGE: frozenset({
        ResearchRunStatus.SOURCE_COLLECTED,
        ResearchRunStatus.PARTIAL,
    }),
    ResearchFlow.STAGED: frozenset({
        ResearchRunStatus.DISCOVERY_COMPLETE,
        ResearchRunStatus.EXTRACTION_IN_PROGRESS,
        ResearchRunStatus.PARTIAL,
        ResearchRunStatus.SOURCES_COMPLETE,
    }),
}


def _configure_output() -> None:
    # Wymuś UTF-8 na wyjściu, by polskie znaki nie były zniekształcane w konsoli Windows.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _print_estimate(label: str, e) -> None:
    print(f"  {label}: search_fee={e.search_fee_usd:.4f}  "
          f"search_driven_tokens={e.search_driven_token_cost_usd:.4f}  "
          f"output={e.output_cost_usd:.4f}  subtotal={e.subtotal_usd:.4f}  "
          f"margin=+{e.safety_margin*100:.0f}%  TOTAL={e.total_usd:.4f} USD")


def _print_staged_estimate(label: str, e) -> None:
    """Dla CostEstimate (three-stage, ADR-020) — pokazuje CONSERVATIVE (sufit, z
    marginesem) OBOK expected (środkowy szacunek z realnej obserwacji, bez marginesu)
    -- świadomie NIE jedną liczbę, patrz docs/ERRORS_AND_FAILURES.md:
    "Nie traktuj estymacji jako przewidywanego kosztu"."""
    print(f"  {label}: search_fee={e.search_fee_usd:.4f}  output={e.output_cost_usd:.4f}  "
          f"conservative(+{e.safety_margin*100:.0f}%)={e.conservative_usd:.4f} USD  "
          f"expected={e.expected_usd:.4f} USD")


def _activate_explicit_real_mode(args: argparse.Namespace, settings):
    """Return paid settings only after the explicit root and pricing gate.

    This is deliberately called after an estimate-only exit, so offline
    estimation remains useful even when the price table is incomplete.
    """
    if not getattr(args, "real", False):
        print("STOP: brak --real. Pozostaję w trybie offline/estimate; nie tworzę klienta API.")
        return None, 0
    try:
        require_valid_real_provider_pricing(settings)
    except ConfigError as exc:
        print(f"STOP: {exc}")
        return None, 1
    return replace(settings, dry_run=False), None


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = argparse.ArgumentParser(
        description="Ściśle ograniczone realne wywołanie researchu (domyślnie trzyetapowe: "
                    "A1 discovery + A2 per-source extraction + B synthesis, ADR-020).")
    parser.add_argument("--topic-id", type=int, default=None,
                        help="ID tematu (wymagane, chyba że --resume).")
    parser.add_argument(
        "--real", action="store_true",
        help="Jawnie zezwól na capowane wywołania providera. Bez flagi skrypt działa "
             "wyłącznie offline/pre-flight i nie tworzy klienta API.",
    )
    parser.add_argument("--resume", default=None, metavar="RESEARCH_RUN_ID",
                        help="Wznów DOKŁADNIE JEDEN kolejny etap dla istniejącego "
                             "research_run_id — status w bazie decyduje który (A2/B dla "
                             "three-stage, etap 2 dla starszych runów). Nigdy nie powtarza "
                              "już wykonanych płatnych etapów.")
    parser.add_argument("--retry-failed-candidates", action="store_true",
                        help="Wyłącznie z --resume: jawnie resetuje eligible EXTRACTION_FAILED "
                              "do PENDING_EXTRACTION. Nie wykonuje API ani A2; po nim potrzebne "
                              "jest osobne --resume.")
    parser.add_argument("--force-re-research", action="store_true",
                        help="Tylko dla świeżego researchu: jawnie zezwala na nowy, potencjalnie "
                             "płatny run tematu z istniejącą kompletną kartą. Nie omija capu, "
                             "budżetu, kill switcha ani innych bramek.")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--mode", choices=["three-stage", "two-stage", "single"],
                        default="single",
                        help="three-stage (ZALECANE od 2026-07-12, ADR-020: A1 discovery + "
                             "A2 per-source extraction + B synthesis) / two-stage (starsze, "
                             "ADR-016/019, NIEZALECANE) / single (najstarsze, NIEZALECANE); "
                             "ignorowane przy --resume (status runu decyduje, który etap wznowić).")
    parser.add_argument(
        "--operation-key", default=None,
        help="Required for fresh --real: durable intent key; same key and parameters return the same job.",
    )
    parser.add_argument(
        "--pricing-profile", default=None,
        help="Required for fresh --real: id of an APPROVED, versioned pricing profile in "
             "config/pricing_profiles.yaml (LA-01-A). Example/unversioned/mismatched profiles are refused.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=None,
        help=f"Durable request output cap persisted in the job (LA-01-C). Integer within "
             f"the approved provider bound; default {DEFAULT_REQUEST_MAX_TOKENS} when omitted. "
             "A controlled acceptance may freeze a lower value explicitly.",
    )
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="Cap pesymistycznego (conservative) szacunku uruchomienia "
                             "(domyślnie 0.45 three-stage / 0.45 two-stage / 0.60 single / "
                             "0.05 --resume samego etapu B).")
    parser.add_argument("--max-web-searches", type=int, default=4,
                        help="[two-stage/single] Cap liczby web searchy w etapie zbierania "
                             "źródeł (API max_uses).")
    parser.add_argument("--max-retries", type=int, default=0,
                        help="Musi wynosić 0: realny provider nie wykonuje auto-retry.")
    parser.add_argument("--gather-max-tokens", type=int, default=1200,
                        help="[two-stage] max_tokens dla etapu gather_sources.")
    parser.add_argument(
        "--synthesize-max-tokens", type=int, default=DEFAULT_SYNTHESIS_MAX_TOKENS,
        help=("max_tokens dla etapu syntezy B (domyślnie 3000 po realnym "
              "stop_reason=max_tokens przy 2200; uwzględniane w estymacie)."),
    )
    parser.add_argument("--forwarded-context-tokens", type=int, default=2500,
                        help="szacowany rozmiar kontekstu przekazywanego do etapu B (syntezy).")
    # --- three-stage (A1/A2/B, ADR-020) ---
    parser.add_argument("--discovery-max-searches", type=int, default=1,
                        help="[three-stage] Cap liczby web searchy w etapie A1 (discovery). "
                             "Domyślnie 1 (nie 2-4) tak, żeby domyślny --max-cost-usd 0.45 "
                             "faktycznie pokrywał domyślną kombinację parametrów — patrz "
                             "docs/DECISIONS.md ADR-020 dla uzasadnienia liczb.")
    parser.add_argument("--discovery-max-tokens", type=int, default=600,
                        help="[three-stage] max_tokens dla etapu A1 (lista kandydatów, JSONL).")
    parser.add_argument("--max-sources", type=int, default=3,
                        help="[three-stage] Ile kandydatów NAJWYŻEJ ekstrahować w etapie A2 "
                             "(każdy to OSOBNE, płatne wywołanie API) — dźwignia kosztu. "
                             "Domyślnie = research_min_sources (3): dokładnie tyle, ile "
                             "potrzeba do bramki jakości, nie więcej.")
    parser.add_argument("--max-web-searches-per-source", type=int, default=1,
                        help="[three-stage] Cap web searchy PER ŹRÓDŁO w etapie A2 (0 = "
                             "ekstrakcja bez wyszukiwania, tylko z URL/tytułu i wiedzy modelu).")
    parser.add_argument("--extraction-max-tokens", type=int, default=1500,
                        help="[three-stage] max_tokens dla etapu A2, PER ŹRÓDŁO. Domyślnie "
                             "1500 (podniesione ze starego 500 po diagnostyce 2026-07-12 — "
                             "udana diagnostyka kandydata id=3 zwróciła 915 tokenów; "
                             "jednorazowe 5000 nie jest defaultem produkcyjnym, "
                              "patrz docs/ERRORS_AND_FAILURES.md).")
    parser.add_argument("--max-extraction-attempts", type=int, default=2,
                        help="[three-stage] Łączny cap rozpoczętych prób A2 na kandydata: "
                             "domyślnie 2 (pierwsza próba + najwyżej jedno jawne retry). "
                             "To nie jest --max-retries transportowego klienta.")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Pokaż pełną estymację i zakończ — ZERO wywołań API.")
    args = parser.parse_args(argv)

    if args.max_extraction_attempts < 1:
        print("STOP: --max-extraction-attempts musi być dodatnie.")
        return 1
    if args.max_retries != 0:
        print("STOP: --max-retries musi wynosić 0; auto-retry realnego providera jest zablokowany.")
        return 1
    if args.retry_failed_candidates and args.resume is None:
        print("STOP: --retry-failed-candidates wymaga --resume RESEARCH_RUN_ID.")
        return 1
    if args.retry_failed_candidates and args.estimate_only:
        print("STOP: --retry-failed-candidates nie łączy się z --estimate-only.")
        return 1
    if args.force_re_research and args.resume is not None:
        print("STOP: --force-re-research dotyczy wyłącznie świeżego researchu, nie --resume.")
        return 1
    if args.resume is None and args.topic_id is None:
        print("STOP: podaj --topic-id (nowy research) lub --resume RESEARCH_RUN_ID "
              "(wznowienie dokładnie jednego kolejnego etapu).")
        return 1
    # WAVE 0B has a durable fresh-enqueue path only.  A legacy A2/B resume has
    # no durable job/attempt identity, so refuse it before settings, SQLite,
    # account policy, client, log or usage construction can mutate anything.
    if args.resume is not None and args.real and not args.estimate_only:
        print(
            "STOP: real resume requires a durable job; legacy A2/B resume is "
            "refused before any database mutation."
        )
        return 2

    if args.retry_failed_candidates:
        return _run_retry_failed_candidates(args)
    if args.resume is not None:
        return _run_resume(args)
    return _run_fresh(args)


def _enqueue_durable_real_job(args: argparse.Namespace, storage: SqliteStorage, account, topic,
                              settings, *, max_cost_usd: float, request_max_tokens: int,
                              approved_profile=None,
                              now: datetime | None = None) -> int:
    """Persist fresh paid intent only; this process never creates a provider client."""
    if args.mode != "single" or args.force_re_research:
        print("INVALID_CONFIGURATION: WAVE 0B durable real jobs support only fresh --mode single.")
        return 2
    if not isinstance(args.operation_key, str) or not args.operation_key.strip():
        print("INVALID_CONFIGURATION: fresh --real requires a non-empty --operation-key.")
        return 2
    operation_key = args.operation_key.strip()
    if len(operation_key) > 96 or not operation_key.replace("-", "").replace("_", "").isalnum():
        print("INVALID_CONFIGURATION: --operation-key accepts only letters, digits, - and _ (max 96).")
        return 2
    # LA-01-A: a fresh real paid job may only be persisted against an explicitly
    # approved, versioned, model-matched authoritative pricing profile.  The
    # example/unversioned config only ever blocks; there is no ENV-authoritative path.
    profile = approved_profile
    if profile is None:
        try:
            profiles = load_pricing_profiles(default_pricing_profiles_path(settings.project_root))
            profile = resolve_real_pricing_profile(
                profiles, profile_id=args.pricing_profile, model=settings.model_quality,
            )
        except PricingConfigError as exc:
            print(f"STOP: {exc}")
            return 2
    # WAVE 0B namespace is global per durable real-research workflow: the
    # operation key identifies the logical enqueue request, never a topic-local retry.
    idempotency_key = f"real-research:{operation_key}"
    job_id = controlled_research_job_id(operation_key)
    session_contract = controlled_session_contract(operation_key, job_id=job_id)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=settings,
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd=max_cost_usd,
        max_web_searches=args.max_web_searches,
        question=topic.question or f"Why does '{topic.title}' work the way it does?",
        niche=account.niche,
        max_tokens=request_max_tokens,
        pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )
    enqueue_time = now if now is not None else datetime.now(timezone.utc)
    job = Job(
        id=job_id,
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=idempotency_key,
        topic_id=int(topic.id),
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
            "controlled_session": session_contract,
        },
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=enqueue_time,
        max_attempts=1,
    )
    try:
        enqueue_result = storage.enqueue_job_result(job)
    except JobConflictError as exc:
        print(f"OPERATION_KEY_CONFLICT: {exc}")
        return 2
    marker = "JOB_ENQUEUED" if enqueue_result.created else "JOB_ALREADY_EXISTS"
    print(f"{marker}: job_id={enqueue_result.job.id}")
    print("No provider request was made. A leased worker is required for execution.")
    return 0


def _run_fresh(args: argparse.Namespace) -> int:
    max_cost_usd = args.max_cost_usd if args.max_cost_usd is not None else _DEFAULT_MAX_COST[args.mode]

    # LA-01-C: the single durable request output cap is validated once and reused
    # by both the pre-flight cost projection and the persisted job, so CLI ==
    # projection == persisted == provider max_tokens can never diverge.
    try:
        request_max_tokens = validate_cli_max_tokens(
            DEFAULT_REQUEST_MAX_TOKENS if args.max_tokens is None else args.max_tokens
        )
    except DurableExecutionIntentError as exc:
        print(f"STOP: {exc}")
        return 2

    settings = load_settings()
    if getattr(args, "real", False) and not args.estimate_only:
        settings, stop_code = _activate_explicit_real_mode(args, settings)
        if stop_code is not None:
            return stop_code
    approved_profile = None
    if getattr(args, "real", False):
        try:
            profiles = load_pricing_profiles(
                default_pricing_profiles_path(settings.project_root)
            )
            approved_profile = resolve_real_pricing_profile(
                profiles,
                profile_id=args.pricing_profile,
                model=settings.model_quality,
            )
        except PricingConfigError as exc:
            print(f"STOP: {exc}")
            return 2
        # Every real preflight projection below now uses the exact profile that
        # will be persisted; ambient settings pricing is excluded.
        settings = replace(
            settings,
            pricing={key: float(value) for key, value in approved_profile.prices.items()},
        )

    print("=" * 70)
    print("PRE-FLIGHT CHECKS (przed jakimkolwiek wywołaniem API)")
    print("=" * 70)
    print(f"tryb:                         {args.mode}")
    print(f"ANTHROPIC_API_KEY ustawiony:  {bool(settings.anthropic_api_key)}  (wartość NIE jest wypisywana)")
    print(f"model (research/quality):     {settings.model_quality!r}")
    print(f"kill_switch:                  {settings.kill_switch}")

    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    account = settings.get_account(args.account)
    topic = next((t for t in storage.list_topics(account.id) if t.id == args.topic_id), None)
    if topic is None:
        print(f"STOP: nie znaleziono tematu #{args.topic_id} dla konta {account.id}.")
        return 1
    try:
        ensure_topic_can_start_research(storage, account, topic, args.force_re_research)
    except CompletedResearchExistsError as exc:
        print(f"STOP: {exc}")
        return 1
    except ResearchTopicIntegrityError as exc:
        print(f"STOP: błąd integralności researchu tematu: {exc}")
        return 1
    print(f"\ntemat: #{topic.id} [{topic.status.value}] score={topic.score} — {topic.title!r}")
    if args.force_re_research:
        print("UWAGA: --force-re-research jest jawnie włączone; pozostałe bramki bezpieczeństwa działają.")

    now = clock.now()
    month_spent = storage.sum_real_cost_usd(now.strftime("%Y-%m"))
    day_spent = storage.sum_real_cost_usd(now.strftime("%Y-%m-%d"))
    print(f"budżet miesięczny: wydano dotąd {month_spent:.6f} / limit {settings.max_monthly_cost_usd:.2f} USD")
    print(f"budżet dzienny:    wydano dotąd {day_spent:.6f} / limit {settings.max_daily_cost_usd:.2f} USD")

    print(f"\n--- KALIBROWANA ESTYMACJA (margines bezpieczeństwa >= 50%, patrz ERRORS_AND_FAILURES.md) ---")
    if args.mode == "three-stage":
        est = estimate_staged_research_cost_usd(
            settings, discovery_max_searches=args.discovery_max_searches,
            discovery_max_tokens=args.discovery_max_tokens,
            expected_source_count=args.max_sources,
            max_web_searches_per_source=args.max_web_searches_per_source,
            extraction_max_tokens=args.extraction_max_tokens,
            synthesize_max_tokens=args.synthesize_max_tokens,
            forwarded_context_tokens=args.forwarded_context_tokens)
        _print_staged_estimate("A1 discovery", est["discovery"])
        _print_staged_estimate(f"A2 extraction (x{args.max_sources} źródeł, per-source poniżej)",
                               est["extraction_total"])
        _print_staged_estimate("  ...per source", est["extraction_per_source"])
        _print_staged_estimate("B synthesis", est["synthesis"])
        print(f"  TOTAL (conservative sufit):  {est['total'].conservative_usd:.4f} USD")
        print(f"  TOTAL (expected, z 2 realnych obserwacji, BEZ marginesu): "
              f"{est['total'].expected_usd:.4f} USD")
        base_worst_case = est["total"].conservative_usd
    elif args.mode == "two-stage":
        stage_a = estimate_worst_case_search_call_usd(
            settings, max_web_searches=args.max_web_searches,
            max_output_tokens=args.gather_max_tokens)
        stage_b = estimate_no_search_call_usd(
            settings, max_output_tokens=args.synthesize_max_tokens,
            forwarded_context_tokens=args.forwarded_context_tokens)
        _print_estimate("ETAP 1 (gather_sources, TYLKO search)", stage_a)
        _print_estimate("ETAP 2 (synthesize_card, ZERO search)", stage_b)
        base_worst_case = float(sum_usd((stage_a.total_usd, stage_b.total_usd)))
        print(f"  COMBINED (etap1 + etap2, jedna próba/call): {base_worst_case:.4f} USD")
    else:
        single = estimate_worst_case_search_call_usd(
            settings, max_web_searches=args.max_web_searches, max_output_tokens=request_max_tokens)
        _print_estimate("SINGLE-CALL (search + analiza naraz, NIEZALECANE)", single)
        base_worst_case = single.total_usd

    worst_case = estimate_with_retries(base_worst_case, args.max_retries)
    print(f"  WORST-CASE z retry x(1+{args.max_retries}): {worst_case:.4f} USD")

    print(f"\ncap tego uruchomienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0

    if not getattr(args, "real", False):
        _offline_settings, stop_code = _activate_explicit_real_mode(args, settings)
        del _offline_settings
        if stop_code is not None:
            return stop_code

    policy = PolicyEngine(settings, storage, clock)
    stop = _preflight_stop(
        settings, policy, account, worst_case, max_cost_usd, current_run_cost=0.0)
    if stop:
        return stop

    storage.ensure_account(account)

    if getattr(args, "real", False):
        try:
            return _enqueue_durable_real_job(
                args, storage, account, topic, settings,
                max_cost_usd=max_cost_usd, request_max_tokens=request_max_tokens,
                approved_profile=approved_profile,
                now=now,
            )
        finally:
            storage.close()

    # Every supported fresh branch returned above: dry mode stopped before
    # pre-flight and real mode persisted a job.  Keep a defensive hard stop
    # here so a future control-flow change cannot revive a direct
    # fresh-provider path without an explicit architectural change.
    storage.close()
    print("INVALID_CONFIGURATION: fresh research execution requires a durable job.")
    return 2


def _run_resume(args: argparse.Namespace) -> int:
    """Wznawia dokładnie JEDEN kolejny etap dla istniejącego research_run_id — bez
    ponownego web search tam, gdzie to już zostało wykonane. Wybór funkcji resume
    opiera się wyłącznie na zapisanym `research_runs.flow`; status ani obecność
    rekordów w tabelach źródeł nie służą już do rozpoznawania przepływu."""
    settings = load_settings()

    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    research_run = storage.get_research_run(args.resume)
    if research_run is None:
        print(f"STOP: nie znaleziono research_run #{args.resume}.")
        return 1
    selected_account_id = getattr(args, "account", DEFAULT_ACCOUNT)
    if research_run.account_id != selected_account_id:
        print(
            f"STOP: research_run #{args.resume} należy do konta "
            f"{research_run.account_id}, nie do wybranego konta {selected_account_id}."
        )
        return 1
    status = research_run.status.value
    print(f"status research_run:          {status}")
    flow = research_run.flow
    print(f"zapisany flow:                 {flow.value}")

    allowed_statuses = _RESUMABLE_STATUSES.get(flow, frozenset())
    if research_run.status not in allowed_statuses:
        allowed_values = sorted(item.value for item in allowed_statuses)
        allowed_description = allowed_values or ["brak — ten flow nie ma trwałego resume"]
        print(
            f"STOP: research_run #{args.resume}: flow={flow.value}, status={status}; "
            f"dozwolone statusy dla tego flow: {allowed_description}."
        )
        return 1
    if flow == ResearchFlow.STAGED:
        uncertain = storage.list_source_candidates(
            args.resume, SourceCandidateStatus.EXTRACTION_IN_PROGRESS,
        )
        if uncertain:
            print(
                f"STOP: research_run #{args.resume} ma {len(uncertain)} kandydatÃ³w "
                "EXTRACTION_IN_PROGRESS; zwykÅ‚e resume wymaga jawnej decyzji recovery "
                "i nie tworzy klienta API."
            )
            return 1

    print("=" * 70)
    print("PRE-FLIGHT CHECKS — WZNOWIENIE (przed jakimkolwiek wywołaniem API)")
    print("=" * 70)
    print(f"research_run_id:              {args.resume}")
    print(f"ANTHROPIC_API_KEY ustawiony:  {bool(settings.anthropic_api_key)}  (wartość NIE jest wypisywana)")
    print(f"model (research/quality):     {settings.model_quality!r}")
    print(f"kill_switch:                  {settings.kill_switch}")

    prior_usage = storage.get_research_usage(args.resume)
    prior_cost = float(sum_usd(
        (u.estimated_cost_usd for u in prior_usage), label="persisted prior research cost",
    ))
    print(f"koszt już poniesiony:          {prior_cost:.6f} USD")

    now = datetime.now(timezone.utc)
    month_spent = storage.sum_real_cost_usd(now.strftime("%Y-%m"))
    day_spent = storage.sum_real_cost_usd(now.strftime("%Y-%m-%d"))
    print(f"budżet miesięczny: wydano dotąd {month_spent:.6f} / limit {settings.max_monthly_cost_usd:.2f} USD")
    print(f"budżet dzienny:    wydano dotąd {day_spent:.6f} / limit {settings.max_daily_cost_usd:.2f} USD")

    if flow == ResearchFlow.TWO_STAGE:
        return _run_resume_legacy(args, settings, storage, clock, research_run, prior_cost,
                                  month_spent, day_spent)
    if flow == ResearchFlow.STAGED:
        return _run_resume_staged(args, settings, storage, clock, research_run, prior_cost,
                                  month_spent, day_spent)
    raise ValueError(
        f"research_run #{args.resume}: unsupported stored flow '{flow.value}'."
    )


def _run_retry_failed_candidates(args: argparse.Namespace) -> int:
    """Bezpłatna, jawna mutacja kandydatów; celowo bez preflightu i bez klienta API."""
    settings = load_settings()
    storage = SqliteStorage.open(settings.db_path)
    try:
        result = retry_failed_source_candidates(
            args.resume, settings=settings, storage=storage,
            account_id=args.account,
            max_attempts=args.max_extraction_attempts,
        )
    except ValueError as exc:
        print(f"STOP: {exc}")
        return 1
    research_run = storage.get_research_run(args.resume)
    print("retry-failed-candidates: API nie zostało wywołane; A2 nie zostało uruchomione.")
    print(f"reset={result.reset_count} skipped_cap={result.skipped_cap_count} "
          f"already_pending={result.already_pending_count} "
          f"in_progress={result.in_progress_count} reopened={int(result.reopened_run)} "
          f"remaining_failed={result.remaining_failed_count}")
    print(f"status research_run: {research_run.status.value}")
    return 0


def _run_resume_legacy(args, settings, storage, clock, research_run, prior_cost,
                       month_spent, day_spent) -> int:
    max_cost_usd = args.max_cost_usd if args.max_cost_usd is not None else 0.05

    sources = storage.list_research_sources(args.resume)
    print(f"źródła zapisane w bazie:       {len(sources)} (research_sources, legacy)")

    print("\n--- KALIBROWANA ESTYMACJA (tylko etap B — zero web search) ---")
    stage_b = estimate_no_search_call_usd(
        settings, max_output_tokens=args.synthesize_max_tokens,
        forwarded_context_tokens=args.forwarded_context_tokens)
    _print_estimate("ETAP 2 (synthesize_card, ZERO search)", stage_b)
    worst_case = estimate_with_retries(stage_b.total_usd, args.max_retries)
    print(f"  WORST-CASE z retry x(1+{args.max_retries}): {worst_case:.4f} USD")
    print(f"\ncap tego wznowienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0
    settings, stop_code = _activate_explicit_real_mode(args, settings)
    if stop_code is not None:
        return stop_code
    print(
        "STOP: real resume requires its own durable job flow; no provider client "
        "or runtime is constructed by this legacy helper."
    )
    return 2


def _run_resume_staged(args, settings, storage, clock, research_run, prior_cost,
                       month_spent, day_spent) -> int:
    max_cost_usd = args.max_cost_usd if args.max_cost_usd is not None else 0.20

    pending = storage.list_source_candidates(args.resume)
    counts = {}
    for c in pending:
        counts[c.status.value] = counts.get(c.status.value, 0) + 1
    print(f"kandydaci w bazie:             {len(pending)}  ({counts})")

    resuming_extraction = research_run.status.value != ResearchRunStatus.SOURCES_COMPLETE.value
    if resuming_extraction:
        remaining = sum(1 for c in pending
                        if c.status == SourceCandidateStatus.PENDING_EXTRACTION)
        n = min(remaining, args.max_sources) if args.max_sources else remaining
        print(f"\n--- KALIBROWANA ESTYMACJA (wznowienie etapu A2 — do {n} pozostałych źródeł) ---")
        extraction_total = estimate_extraction_cost_for_sources_usd(
            settings, n, args.max_web_searches_per_source, args.extraction_max_tokens,
        )
        _print_staged_estimate(f"A2 extraction (x{n} pozostałych)", extraction_total)
        base_worst_case = extraction_total.conservative_usd
    else:
        print("\n--- KALIBROWANA ESTYMACJA (wznowienie etapu B — zero web search) ---")
        synth = estimate_synthesis_cost_usd(
            settings, args.synthesize_max_tokens, args.forwarded_context_tokens)
        _print_staged_estimate("B synthesis", synth)
        base_worst_case = synth.conservative_usd

    worst_case = estimate_with_retries(base_worst_case, args.max_retries)
    print(f"  WORST-CASE z retry x(1+{args.max_retries}): {worst_case:.4f} USD")

    print(f"\ncap tego wznowienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0
    settings, stop_code = _activate_explicit_real_mode(args, settings)
    if stop_code is not None:
        return stop_code
    print(
        "STOP: real resume requires its own durable job flow; no provider client "
        "or runtime is constructed by this staged helper."
    )
    return 2


def _preflight_stop(settings, policy: PolicyEngine, account, estimated_total: float,
                    max_cost_usd: float, *, current_run_cost: float) -> int | None:
    """Wspólne bramki PRZED wywołaniem API. Zwraca kod wyjścia, jeśli trzeba się
    zatrzymać, albo None, jeśli wolno kontynuować."""
    if not settings.anthropic_api_key:
        print("INVALID_CONFIGURATION: missing ANTHROPIC_API_KEY. No provider request was made.")
        return 2
    decision = policy.check_run_budget(
        estimated_total,
        max_cost_usd,
        current_run_cost=current_run_cost,
        account=account,
    )
    if not decision.allowed:
        marker = "BLOCKED_BY_BUDGET" if decision.code.startswith(("BUDGET_", "RUN_CAP_")) else "INVALID_CONFIGURATION"
        print(f"{marker} [{decision.code}]: {decision.reason} No provider request was made.")
        return 1
    print(f"OK: projekcja kosztu runu ({estimated_total:.4f} USD) mieści się w capie "
          f"({max_cost_usd:.2f} USD) i w budżecie dziennym/miesięcznym.")
    return None


def _print_result(summary, max_cost_usd: float, worst_case: float, max_web_searches: int) -> None:
    actual_cost = quantize_usd(summary.cost_usd, label="CLI summary cost")
    run_cap = quantize_usd(max_cost_usd, label="CLI run cap")
    print("\n" + "=" * 70)
    print("WYNIK")
    print("=" * 70)
    print(f"run_id:              {summary.run_id}")
    print(f"blocked:             {summary.blocked}  ({summary.block_code}: {summary.block_reason})")
    print(f"error:               {summary.error}")
    print(f"model:               {summary.model}")
    print(f"input_tokens:        {summary.input_tokens}")
    print(f"output_tokens:       {summary.output_tokens}")
    print(f"web_search_requests: {summary.web_search_requests}  (cap był {max_web_searches})")
    print(f"koszt RZECZYWISTY:   {actual_cost:.6f} USD")
    print(f"pesymistyczny szacunek: {worst_case:.4f} USD")
    print(f"cap tego runu:       {run_cap:.2f} USD  "
          f"-> {'PRZEKROCZONY!!!' if actual_cost > run_cap else 'OK, w limicie'}")
    print(f"injection_flags:     {summary.injection_flags}")
    print(f"recommendation:      {summary.recommendation}  reasons={summary.reasons}")
    print(f"sources_count:       {summary.sources_count}")
    if summary.candidates_discovered or summary.sources_extracted or summary.sources_failed:
        print(f"candidates_discovered: {summary.candidates_discovered}")
        print(f"sources_extracted:     {summary.sources_extracted}")
        print(f"sources_failed:        {summary.sources_failed}")

    card = summary.card
    if card is not None:
        print("\n--- RESEARCH CARD ---")
        print(f"question:                  {card.question}")
        print(f"working_thesis:            {card.working_thesis}")
        print(f"main_mechanism:            {card.main_mechanism}")
        print(f"confirmed_claims:          {card.confirmed_claims}")
        print(f"uncertain_claims:          {card.uncertain_claims}")
        print(f"contradictions:            {card.contradictions}")
        print(f"strongest_counterargument: {card.strongest_counterargument}")
        print(f"citable_numbers:           {card.citable_numbers}")
        print(f"visual_idea:               {card.visual_idea}")
        print(f"confidence_score:          {card.confidence_score}")
        print(f"source_quality_score:      {card.source_quality_score}")
        print(f"\nsources ({len(card.sources)}):")
        for i, s in enumerate(card.sources, 1):
            print(f"  {i}. url={s.url}")
            print(f"     title={s.title!r}")
            print(f"     author_or_org={s.author_or_org!r}  published_at={s.published_at!r}")
            print(f"     source_type={s.source_type.value}  verification={s.verification_status.value}")
            print(f"     supports_claim={s.supports_claim!r}")

    print("\n" + "=" * 70)
    print("STOP — uruchomienie zakończone. Skrypt niczego nie ponawia sam.")
    print("=" * 70)


if __name__ == "__main__":
    raise SystemExit(main())
