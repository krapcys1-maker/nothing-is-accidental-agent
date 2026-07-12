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
from app.core.config import load_settings  # noqa: E402
from app.llm.usage_tracker import UsageTracker  # noqa: E402
from app.models import ResearchFlow, ResearchRunStatus, SourceCandidateStatus  # noqa: E402
from app.orchestrator.runner import DEFAULT_ACCOUNT  # noqa: E402
from app.policies.policy_engine import PolicyEngine  # noqa: E402
from app.ports.notification import LogNotification  # noqa: E402
from app.research.anthropic_client import AnthropicResearchClient  # noqa: E402
from app.research.cost_estimator import (  # noqa: E402
    CostEstimate,
    estimate_extraction_cost_per_source_usd,
    estimate_no_search_call_usd,
    estimate_staged_research_cost_usd,
    estimate_synthesis_cost_usd,
    estimate_worst_case_search_call_usd,
)
from app.storage.repositories import SqliteStorage  # noqa: E402
from app.workflows.research.docs_writer import make_research_log_writer  # noqa: E402
from app.workflows.research.pipeline import (  # noqa: E402
    resume_research_stage_b,
    resume_staged_research,
    retry_failed_source_candidates,
    run_research_pipeline,
    run_staged_research_pipeline,
    run_two_stage_research_pipeline,
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


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = argparse.ArgumentParser(
        description="Ściśle ograniczone realne wywołanie researchu (domyślnie trzyetapowe: "
                    "A1 discovery + A2 per-source extraction + B synthesis, ADR-020).")
    parser.add_argument("--topic-id", type=int, default=None,
                        help="ID tematu (wymagane, chyba że --resume).")
    parser.add_argument("--resume", default=None, metavar="RESEARCH_RUN_ID",
                        help="Wznów DOKŁADNIE JEDEN kolejny etap dla istniejącego "
                             "research_run_id — status w bazie decyduje który (A2/B dla "
                             "three-stage, etap 2 dla starszych runów). Nigdy nie powtarza "
                              "już wykonanych płatnych etapów.")
    parser.add_argument("--retry-failed-candidates", action="store_true",
                        help="Wyłącznie z --resume: jawnie resetuje eligible EXTRACTION_FAILED "
                             "do PENDING_EXTRACTION. Nie wykonuje API ani A2; po nim potrzebne "
                             "jest osobne --resume.")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--mode", choices=["three-stage", "two-stage", "single"],
                        default="three-stage",
                        help="three-stage (ZALECANE od 2026-07-12, ADR-020: A1 discovery + "
                             "A2 per-source extraction + B synthesis) / two-stage (starsze, "
                             "ADR-016/019, NIEZALECANE) / single (najstarsze, NIEZALECANE); "
                             "ignorowane przy --resume (status runu decyduje, który etap wznowić).")
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="Cap pesymistycznego (conservative) szacunku uruchomienia "
                             "(domyślnie 0.45 three-stage / 0.45 two-stage / 0.60 single / "
                             "0.05 --resume samego etapu B).")
    parser.add_argument("--max-web-searches", type=int, default=4,
                        help="[two-stage/single] Cap liczby web searchy w etapie zbierania "
                             "źródeł (API max_uses).")
    parser.add_argument("--max-retries", type=int, default=1,
                        help="Retry tylko dla błędów technicznych/timeout, max N prób dodatkowych.")
    parser.add_argument("--gather-max-tokens", type=int, default=1200,
                        help="[two-stage] max_tokens dla etapu gather_sources.")
    parser.add_argument("--synthesize-max-tokens", type=int, default=2200,
                        help="max_tokens dla etapu syntezy (B, wspólne dla three-stage/two-stage).")
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
    if args.retry_failed_candidates and args.resume is None:
        print("STOP: --retry-failed-candidates wymaga --resume RESEARCH_RUN_ID.")
        return 1
    if args.retry_failed_candidates and args.estimate_only:
        print("STOP: --retry-failed-candidates nie łączy się z --estimate-only.")
        return 1
    if args.resume is None and args.topic_id is None:
        print("STOP: podaj --topic-id (nowy research) lub --resume RESEARCH_RUN_ID "
              "(wznowienie dokładnie jednego kolejnego etapu).")
        return 1

    if args.retry_failed_candidates:
        return _run_retry_failed_candidates(args)
    if args.resume is not None:
        return _run_resume(args)
    return _run_fresh(args)


def _run_fresh(args: argparse.Namespace) -> int:
    max_cost_usd = args.max_cost_usd if args.max_cost_usd is not None else _DEFAULT_MAX_COST[args.mode]

    settings = load_settings()
    settings = replace(settings, dry_run=False)  # to jest REALNE, płatne wywołanie (gdy nie --estimate-only)

    print("=" * 70)
    print("PRE-FLIGHT CHECKS (przed jakimkolwiek wywołaniem API)")
    print("=" * 70)
    print(f"tryb:                         {args.mode}")
    print(f"ANTHROPIC_API_KEY ustawiony:  {bool(settings.anthropic_api_key)}  (wartość NIE jest wypisywana)")
    print(f"model (research/quality):     {settings.model_quality!r}")
    print(f"kill_switch:                  {settings.kill_switch}")

    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    now = datetime.now(timezone.utc)
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
        worst_case = est["total"].conservative_usd
    elif args.mode == "two-stage":
        stage_a = estimate_worst_case_search_call_usd(
            settings, max_web_searches=args.max_web_searches,
            max_output_tokens=args.gather_max_tokens)
        stage_b = estimate_no_search_call_usd(
            settings, max_output_tokens=args.synthesize_max_tokens,
            forwarded_context_tokens=args.forwarded_context_tokens)
        _print_estimate("ETAP 1 (gather_sources, TYLKO search)", stage_a)
        _print_estimate("ETAP 2 (synthesize_card, ZERO search)", stage_b)
        worst_case = stage_a.total_usd + stage_b.total_usd
        print(f"  COMBINED (etap1 + etap2):                    {worst_case:.4f} USD")
    else:
        single = estimate_worst_case_search_call_usd(
            settings, max_web_searches=args.max_web_searches, max_output_tokens=3000)
        _print_estimate("SINGLE-CALL (search + analiza naraz, NIEZALECANE)", single)
        worst_case = single.total_usd

    print(f"\ncap tego uruchomienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0

    if not settings.anthropic_api_key:
        print("STOP: brak ANTHROPIC_API_KEY w .env. Nie wołam API.")
        return 1
    if settings.kill_switch:
        print("STOP: KILL_SWITCH aktywny. Nie wołam API.")
        return 1
    if worst_case > max_cost_usd:
        print(f"STOP: pesymistyczny szacunek ({worst_case:.4f} USD) przekracza cap tego "
              f"uruchomienia ({max_cost_usd:.2f} USD). Nie wołam API.")
        return 1
    if month_spent + worst_case > settings.max_monthly_cost_usd or \
            day_spent + worst_case > settings.max_daily_cost_usd:
        print("STOP: nawet pesymistyczny szacunek przekroczyłby dzienny/miesięczny budżet.")
        return 1
    print(f"OK: pesymistyczny szacunek ({worst_case:.4f} USD) mieści się w capie "
          f"({max_cost_usd:.2f} USD) i w budżecie dziennym/miesięcznym.")

    account = settings.get_account(args.account)
    storage.ensure_account(account)
    topic = next((t for t in storage.list_topics(account.id) if t.id == args.topic_id), None)
    if topic is None:
        print(f"STOP: nie znaleziono tematu #{args.topic_id} dla konta {account.id}.")
        return 1
    print(f"\ntemat: #{topic.id} [{topic.status.value}] score={topic.score} — {topic.title!r}")

    research_client = AnthropicResearchClient(
        settings.anthropic_api_key, settings.model_quality,
        max_retries=args.max_retries,
        timeout_seconds=settings.research_timeout_seconds,
        max_web_searches=args.max_web_searches,
        gather_max_tokens=args.gather_max_tokens,
        synthesize_max_tokens=args.synthesize_max_tokens,
        discover_max_tokens=args.discovery_max_tokens,
        extract_max_tokens=args.extraction_max_tokens,
        max_web_searches_per_source=args.max_web_searches_per_source,
    )
    usage_tracker = UsageTracker(settings, storage)
    policy = PolicyEngine(settings, storage, clock)
    notifier = LogNotification()
    research_log = make_research_log_writer(settings.project_root / "docs" / "RESEARCH_LOG.md")

    search_desc = (f"max {args.discovery_max_searches} discovery + "
                  f"max {args.max_web_searches_per_source}/źródło extraction (x{args.max_sources})"
                  if args.mode == "three-stage" else f"max {args.max_web_searches} web searchy")
    print("\n" + "=" * 70)
    print(f"URUCHAMIAM REALNE WYWOŁANIE(A) — tryb={args.mode}, {search_desc}, "
          f"max {args.max_retries} retry (tylko błąd techniczny), cap {max_cost_usd:.2f} USD")
    print("Nie publikuję nic. Nie generuję artykułu. Nie dotykam przeglądarki.")
    print("=" * 70)

    if args.mode == "three-stage":
        summary = run_staged_research_pipeline(
            account, topic,
            settings=settings, storage=storage, research_client=research_client,
            usage_tracker=usage_tracker, policy=policy, notifier=notifier,
            clock=clock, research_log=research_log,
            discovery_max_searches=args.discovery_max_searches,
            discovery_max_tokens=args.discovery_max_tokens,
            max_sources=args.max_sources,
            max_web_searches_per_source=args.max_web_searches_per_source,
            extraction_max_tokens=args.extraction_max_tokens,
            max_attempts=args.max_extraction_attempts,
            synthesize_max_tokens=args.synthesize_max_tokens,
            forwarded_context_tokens=args.forwarded_context_tokens,
        )
    elif args.mode == "two-stage":
        summary = run_two_stage_research_pipeline(
            account, topic,
            settings=settings, storage=storage, research_client=research_client,
            usage_tracker=usage_tracker, policy=policy, notifier=notifier,
            clock=clock, research_log=research_log,
            max_web_searches=args.max_web_searches,
            gather_max_tokens=args.gather_max_tokens,
            synthesize_max_tokens=args.synthesize_max_tokens,
            forwarded_context_tokens=args.forwarded_context_tokens,
        )
    else:
        summary = run_research_pipeline(
            account, topic,
            settings=settings, storage=storage, research_client=research_client,
            usage_tracker=usage_tracker, policy=policy, notifier=notifier,
            clock=clock, research_log=research_log,
        )

    _print_result(summary, max_cost_usd, worst_case, args.max_web_searches)
    return 0


def _run_resume(args: argparse.Namespace) -> int:
    """Wznawia dokładnie JEDEN kolejny etap dla istniejącego research_run_id — bez
    ponownego web search tam, gdzie to już zostało wykonane. Wybór funkcji resume
    opiera się wyłącznie na zapisanym `research_runs.flow`; status ani obecność
    rekordów w tabelach źródeł nie służą już do rozpoznawania przepływu."""
    settings = load_settings()
    settings = replace(settings, dry_run=False)

    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    research_run = storage.get_research_run(args.resume)
    if research_run is None:
        print(f"STOP: nie znaleziono research_run #{args.resume}.")
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
    prior_cost = sum(u.estimated_cost_usd for u in prior_usage)
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
    worst_case = stage_b.total_usd
    print(f"\ncap tego wznowienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0
    stop = _preflight_stop(settings, worst_case, max_cost_usd, month_spent, day_spent)
    if stop:
        return stop

    account = settings.get_account(args.account)
    storage.ensure_account(account)
    research_client = AnthropicResearchClient(
        settings.anthropic_api_key, settings.model_quality, max_retries=args.max_retries,
        timeout_seconds=settings.research_timeout_seconds,
        synthesize_max_tokens=args.synthesize_max_tokens,
    )
    usage_tracker = UsageTracker(settings, storage)
    policy = PolicyEngine(settings, storage, clock)
    notifier = LogNotification()
    research_log = make_research_log_writer(settings.project_root / "docs" / "RESEARCH_LOG.md")

    print("\n" + "=" * 70)
    print(f"WZNAWIAM WYŁĄCZNIE ETAP 2 (legacy) — ZERO web search, max {args.max_retries} retry "
          f"(tylko błąd techniczny), cap {max_cost_usd:.2f} USD")
    print("Nie publikuję nic. Nie generuję artykułu. Nie dotykam przeglądarki.")
    print("=" * 70)

    summary = resume_research_stage_b(
        args.resume, account,
        settings=settings, storage=storage, research_client=research_client,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier,
        clock=clock, research_log=research_log,
        synthesize_max_tokens=args.synthesize_max_tokens,
        forwarded_context_tokens=args.forwarded_context_tokens,
    )
    _print_result(summary, max_cost_usd, worst_case, max_web_searches=0)
    return 0


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
        per_source = estimate_extraction_cost_per_source_usd(
            settings, args.max_web_searches_per_source, args.extraction_max_tokens)
        _print_staged_estimate(f"A2 extraction (x{n} pozostałych)", CostEstimate(
            label="", search_fee_usd=per_source.search_fee_usd * n,
            output_cost_usd=per_source.output_cost_usd * n,
            conservative_usd=per_source.conservative_usd * n,
            expected_usd=per_source.expected_usd * n, safety_margin=per_source.safety_margin))
        worst_case = per_source.conservative_usd * n
    else:
        print("\n--- KALIBROWANA ESTYMACJA (wznowienie etapu B — zero web search) ---")
        synth = estimate_synthesis_cost_usd(
            settings, args.synthesize_max_tokens, args.forwarded_context_tokens)
        _print_staged_estimate("B synthesis", synth)
        worst_case = synth.conservative_usd

    print(f"\ncap tego wznowienia (--max-cost-usd): {max_cost_usd:.2f} USD")

    if args.estimate_only:
        print("\n--estimate-only: kończę tutaj. ZERO wywołań API, ZERO kosztu.")
        return 0
    stop = _preflight_stop(settings, worst_case, max_cost_usd, month_spent, day_spent)
    if stop:
        return stop

    account = settings.get_account(args.account)
    storage.ensure_account(account)
    research_client = AnthropicResearchClient(
        settings.anthropic_api_key, settings.model_quality, max_retries=args.max_retries,
        timeout_seconds=settings.research_timeout_seconds,
        synthesize_max_tokens=args.synthesize_max_tokens,
        discover_max_tokens=args.discovery_max_tokens,
        extract_max_tokens=args.extraction_max_tokens,
        max_web_searches_per_source=args.max_web_searches_per_source,
    )
    usage_tracker = UsageTracker(settings, storage)
    policy = PolicyEngine(settings, storage, clock)
    notifier = LogNotification()
    research_log = make_research_log_writer(settings.project_root / "docs" / "RESEARCH_LOG.md")

    stage_label = "A2 (extraction)" if resuming_extraction else "B (synthesis)"
    print("\n" + "=" * 70)
    print(f"WZNAWIAM WYŁĄCZNIE ETAP {stage_label} — max {args.max_retries} retry "
          f"(tylko błąd techniczny), cap {max_cost_usd:.2f} USD")
    print("Nie publikuję nic. Nie generuję artykułu. Nie dotykam przeglądarki.")
    print("=" * 70)

    summary = resume_staged_research(
        args.resume, account,
        settings=settings, storage=storage, research_client=research_client,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier,
        clock=clock, research_log=research_log, max_sources=args.max_sources,
        max_web_searches_per_source=args.max_web_searches_per_source,
        extraction_max_tokens=args.extraction_max_tokens,
        max_attempts=getattr(args, "max_extraction_attempts", 2),
        synthesize_max_tokens=args.synthesize_max_tokens,
        forwarded_context_tokens=args.forwarded_context_tokens,
    )
    _print_result(summary, max_cost_usd, worst_case, max_web_searches=0)
    return 0


def _preflight_stop(settings, worst_case: float, max_cost_usd: float,
                    month_spent: float, day_spent: float) -> int | None:
    """Wspólne bramki PRZED wywołaniem API. Zwraca kod wyjścia, jeśli trzeba się
    zatrzymać, albo None, jeśli wolno kontynuować."""
    if not settings.anthropic_api_key:
        print("STOP: brak ANTHROPIC_API_KEY w .env. Nie wołam API.")
        return 1
    if settings.kill_switch:
        print("STOP: KILL_SWITCH aktywny. Nie wołam API.")
        return 1
    if worst_case > max_cost_usd:
        print(f"STOP: pesymistyczny szacunek ({worst_case:.4f} USD) przekracza cap "
              f"({max_cost_usd:.2f} USD). Nie wołam API.")
        return 1
    if month_spent + worst_case > settings.max_monthly_cost_usd or \
            day_spent + worst_case > settings.max_daily_cost_usd:
        print("STOP: nawet pesymistyczny szacunek przekroczyłby dzienny/miesięczny budżet.")
        return 1
    print(f"OK: pesymistyczny szacunek ({worst_case:.4f} USD) mieści się w capie "
          f"({max_cost_usd:.2f} USD) i w budżecie dziennym/miesięcznym.")
    return None


def _print_result(summary, max_cost_usd: float, worst_case: float, max_web_searches: int) -> None:
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
    print(f"koszt RZECZYWISTY:   {summary.cost_usd:.6f} USD")
    print(f"pesymistyczny szacunek: {worst_case:.4f} USD")
    print(f"cap tego runu:       {max_cost_usd:.2f} USD  "
          f"-> {'PRZEKROCZONY!!!' if summary.cost_usd > max_cost_usd else 'OK, w limicie'}")
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
