"""Kalibrowany estymator pesymistycznego kosztu wywołania z web search.

Dlaczego ten moduł istnieje: pierwotny estymator (scripts/run_capped_research.py,
wersja sprzed 2026-07-11) zakładał płaski, niezależny od liczby wyszukiwań bufor
input_tokens=20000 i oszacował sufit 0.095 USD dla max_uses=6/max_tokens=3000.
Rzeczywisty koszt pierwszego realnego runu (2026-07-11, run
1b649314-27cf-4b29-857e-287175664a3f) wyniósł **0.25 USD** (0.21 USD tokeny +
0.04 USD web search, potwierdzone w konsoli Anthropic) — **~163% więcej** niż
estymowany sufit. Przyczyna: treść wyników wyszukiwania zwracana do modelu jako
kontekst rośnie z LICZBĄ wyszukiwań, nie jest stałym buforem — przy wywołaniach
z server-side tool use narasta szybciej, niż sugerowałaby intuicja z pojedynczego
zapytania. Pełny opis incydentu: docs/ERRORS_AND_FAILURES.md.

Ten moduł kalibruje estymację z tej JEDNEJ realnej obserwacji (n=1) — to wciąż
przybliżenie, jawnie oznaczone jako takie, do doprecyzowania po kolejnych realnych
runach. Domyślny margines bezpieczeństwa >=50% jest wymagany właśnie dlatego,
że kalibracja jest słaba (jedna próbka).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


def estimate_with_retries(base_estimate: float, max_retries: int) -> float:
    """Worst-case cost for the first attempt plus all technical retries."""
    if base_estimate < 0:
        raise ValueError("base_estimate musi być >= 0.")
    if max_retries < 0:
        raise ValueError("max_retries musi być >= 0.")
    return round(base_estimate * (1 + max_retries), 6)

# --- Kalibracja z jedynej znanej realnej obserwacji (2026-07-11, run 1b649314) ---
# Konfiguracja tamtego runu: max_uses=6 (limit), ~4 realnie wykonane wyszukiwania
# (wywnioskowane z 0.04 USD / 0.01 USD za wyszukiwanie), max_tokens=3000 (padło na
# limicie -> ucięty JSON, więc output prawdopodobnie ~= max_tokens).
_CALIBRATION_REAL_TOKEN_COST_USD = 0.21   # z konsoli Anthropic (token-related, input+output)
_CALIBRATION_ACTUAL_SEARCHES = 4
_CALIBRATION_MAX_OUTPUT_TOKENS = 3000

MIN_SAFETY_MARGIN = 0.50  # wymagane od 2026-07-11 (patrz ERRORS_AND_FAILURES.md)


def _reconstructed_input_cost_per_search_usd(settings: Settings) -> float:
    """Rekonstrukcja, NIE pomiar wprost — konsola Anthropic dała tylko sumy
    kategorii (tokeny / web search), nie rozbicie input/output per wywołanie.
    Zakładamy output ~= max_tokens tamtego runu (uzasadnione uciętym JSON-em),
    resztę token-cost przypisujemy do inputu napędzanego wynikami wyszukiwania,
    rozłożonego równo na faktycznie wykonane wyszukiwania.
    """
    price_output_per_mtok = settings.pricing.get("output_per_mtok", 5.0)
    reconstructed_output_cost = (
        _CALIBRATION_MAX_OUTPUT_TOKENS / 1_000_000 * price_output_per_mtok
    )
    reconstructed_input_cost = max(
        0.0, _CALIBRATION_REAL_TOKEN_COST_USD - reconstructed_output_cost
    )
    return reconstructed_input_cost / _CALIBRATION_ACTUAL_SEARCHES


@dataclass
class WorstCaseEstimate:
    search_fee_usd: float
    search_driven_token_cost_usd: float
    output_cost_usd: float
    subtotal_usd: float
    safety_margin: float
    total_usd: float


def estimate_worst_case_search_call_usd(
    settings: Settings,
    max_web_searches: int,
    max_output_tokens: int = 3000,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> WorstCaseEstimate:
    """Pesymistyczny sufit kosztu JEDNEGO wywołania UŻYWAJĄCEGO web search.

    Skalowany z realnej obserwacji (patrz docstring modułu), nie tylko z cennika
    per-token — to właśnie "policz z cennika ile POWINNO kosztować" zawiodło
    2026-07-11 (błąd ~+163%). `safety_margin` domyślnie >= MIN_SAFETY_MARGIN.
    """
    if max_web_searches < 0 or max_output_tokens < 0:
        raise ValueError("max_web_searches i max_output_tokens muszą być >= 0.")
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError(
            f"safety_margin ({safety_margin}) poniżej wymaganego minimum "
            f"({MIN_SAFETY_MARGIN}) — patrz docs/ERRORS_AND_FAILURES.md."
        )

    p = settings.pricing
    search_fee = max_web_searches / 1_000 * p.get("web_search_per_1k", 0.0)

    input_cost_per_search = _reconstructed_input_cost_per_search_usd(settings)
    search_driven_token_cost = max_web_searches * input_cost_per_search

    output_cost = max_output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)

    subtotal = search_fee + search_driven_token_cost + output_cost
    total = subtotal * (1 + safety_margin)

    return WorstCaseEstimate(
        search_fee_usd=round(search_fee, 6),
        search_driven_token_cost_usd=round(search_driven_token_cost, 6),
        output_cost_usd=round(output_cost, 6),
        subtotal_usd=round(subtotal, 6),
        safety_margin=safety_margin,
        total_usd=round(total, 6),
    )


# ============================================================================
# Etapowy research A1/A2/B (od 2026-07-12, ADR-020) — kalibracja z DWIE realne
# obserwacje, nie jedną. Patrz docs/ERRORS_AND_FAILURES.md dla obu incydentów.
#
# Incydent 1 (2026-07-11, run 1b649314, STARY jednoetapowy `run_research`):
#   4 wyszukiwania; token cost (input+output RAZEM) = 0.21 USD z konsoli Anthropic.
#   Input/output NIE były rozbite osobno w konsoli -> output ZAŁOŻONY = max_tokens
#   (3000), bo JSON się uciął (prawdopodobnie wyczerpał limit). To REKONSTRUKCJA,
#   nie pomiar wprost -> per-search (tylko input, po odjęciu zrekonstruowanego
#   outputu): ~0.04875 USD/search.
#
# Incydent 2 (2026-07-12, run 2a3b4bb9, `gather_sources` / stary etap A dwuetapowego):
#   4 wyszukiwania; input_tokens=75728, output_tokens=1619 -- DOKŁADNE liczby
#   odczytane wprost z model_usage (nie rekonstrukcja). Token cost razem (input+
#   output) = 0.083823 USD -> per-search: ~0.020956 USD/search.
#
# Rozbieżność (incydent 1 jest ~2.3x wyższy per-search niż incydent 2) pokazuje,
# że nawet n=2 to wciąż przybliżenie -- różne tematy/zapytania mogą zwracać różną
# ilość treści z wyszukiwania. Dlatego POKAZUJEMY OBA:
#   - CONSERVATIVE (sufit): wyższa z dwóch obserwacji (incydent 1) + margines
#     bezpieczeństwa >=50% -- do bramki budżetowej (musi być bezpieczny, nawet
#     jeśli przez to pesymistyczny).
#   - EXPECTED (środkowy szacunek): incydent 2 (dokładny pomiar) BEZ marginesu --
#     "ile prawdopodobnie wyjdzie", pokazywane człowiekowi OBOK sufitu, nigdy jako
#     zamiennik sufitu w bramce (patrz incydent "Nie traktuj estymacji jako
#     przewidywanego kosztu" w ERRORS_AND_FAILURES.md).
# ============================================================================

CONSERVATIVE_PER_SEARCH_TOKEN_COST_USD = 0.04875     # incydent 1 (rekonstrukcja, 2026-07-11)
EXPECTED_PER_SEARCH_TOKEN_COST_USD = 0.083823 / 4     # incydent 2 (pomiar wprost, 2026-07-12)

HISTORICAL_REAL_RUNS = [
    {"date": "2026-07-11", "run_id": "1b649314-27cf-4b29-857e-287175664a3f",
     "stage": "single-call (legacy)", "searches": 4, "total_cost_usd": 0.25,
     "confidence": "reconstructed"},
    {"date": "2026-07-12", "run_id": "2a3b4bb9-772e-4340-808a-2bc61b28aacf",
     "stage": "gather_sources (stary etap A)", "searches": 4,
     "total_cost_usd": 0.123823, "input_tokens": 75728, "output_tokens": 1619,
     "confidence": "exact"},
]


@dataclass
class CostEstimate:
    label: str
    search_fee_usd: float
    output_cost_usd: float
    conservative_usd: float   # sufit: (search_fee + CONSERVATIVE*n + output) * (1+margin)
    expected_usd: float       # środkowy szacunek: search_fee + EXPECTED*n + output, BEZ marginesu
    safety_margin: float


def estimate_discovery_cost_usd(
    settings: Settings, max_searches: int, max_output_tokens: int,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> CostEstimate:
    """Etap A1 (discover_sources): TYLKO web search + lista URL, zero analizy —
    najlżejszy schemat, więc `max_output_tokens` powinno być małe (patrz
    docs/DECISIONS.md ADR-020 dla uzasadnienia konkretnej domyślnej wartości)."""
    return _estimate_search_driven(settings, max_searches, max_output_tokens,
                                   safety_margin, label="A1 discovery")


def estimate_extraction_cost_per_source_usd(
    settings: Settings, max_web_searches_per_source: int, max_output_tokens: int,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> CostEstimate:
    """Etap A2 (extract_source): JEDNO źródło na wywołanie. Pomnóż `.conservative_usd`/
    `.expected_usd` przez liczbę źródeł, które faktycznie planujesz ekstrahować, żeby
    dostać projekcję całego etapu A2 (patrz `estimate_staged_research_cost_usd`)."""
    return _estimate_search_driven(settings, max_web_searches_per_source, max_output_tokens,
                                   safety_margin, label="A2 extraction (per source)")


def _estimate_search_driven(settings: Settings, searches: int, max_output_tokens: int,
                            safety_margin: float, label: str) -> CostEstimate:
    if searches < 0 or max_output_tokens < 0:
        raise ValueError("searches i max_output_tokens muszą być >= 0.")
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError(
            f"safety_margin ({safety_margin}) poniżej wymaganego minimum "
            f"({MIN_SAFETY_MARGIN}) — patrz docs/ERRORS_AND_FAILURES.md.")

    p = settings.pricing
    search_fee = searches / 1_000 * p.get("web_search_per_1k", 0.0)
    output_cost = max_output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)

    conservative_subtotal = search_fee + searches * CONSERVATIVE_PER_SEARCH_TOKEN_COST_USD + output_cost
    expected_subtotal = search_fee + searches * EXPECTED_PER_SEARCH_TOKEN_COST_USD + output_cost

    return CostEstimate(
        label=label,
        search_fee_usd=round(search_fee, 6),
        output_cost_usd=round(output_cost, 6),
        conservative_usd=round(conservative_subtotal * (1 + safety_margin), 6),
        expected_usd=round(expected_subtotal, 6),
        safety_margin=safety_margin,
    )


def estimate_synthesis_cost_usd(
    settings: Settings, max_output_tokens: int, forwarded_context_tokens: int,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> CostEstimate:
    """Etap B (synthesize_from_cards): zero web search — input pod naszą kontrolą
    (własny, ograniczony kontekst z już wyekstrahowanych kart), więc CONSERVATIVE i
    EXPECTED różnią się TYLKO marginesem bezpieczeństwa, nie kalibracją wyszukiwań."""
    if max_output_tokens < 0 or forwarded_context_tokens < 0:
        raise ValueError("max_output_tokens i forwarded_context_tokens muszą być >= 0.")
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError(
            f"safety_margin ({safety_margin}) poniżej wymaganego minimum "
            f"({MIN_SAFETY_MARGIN}) — patrz docs/ERRORS_AND_FAILURES.md.")

    p = settings.pricing
    input_cost = forwarded_context_tokens / 1_000_000 * p.get("input_per_mtok", 0.0)
    output_cost = max_output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)
    subtotal = input_cost + output_cost

    return CostEstimate(
        label="B synthesis", search_fee_usd=0.0, output_cost_usd=round(output_cost, 6),
        conservative_usd=round(subtotal * (1 + safety_margin), 6),
        expected_usd=round(subtotal, 6), safety_margin=safety_margin,
    )


def estimate_staged_research_cost_usd(
    settings: Settings, *, discovery_max_searches: int, discovery_max_tokens: int,
    expected_source_count: int, max_web_searches_per_source: int, extraction_max_tokens: int,
    synthesize_max_tokens: int, forwarded_context_tokens: int,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> dict[str, CostEstimate]:
    """Projekcja PEŁNEGO etapowego researchu (A1 + N x A2 + B). `expected_source_count`
    to ile źródeł PLANUJEMY wyekstrahować (ile faktycznie zapłacimy za A2), nie ile A1
    może znaleźć — to jest właśnie dźwignia kosztu, którą kontroluje `--max-sources`
    w scripts/run_capped_research.py."""
    discovery = estimate_discovery_cost_usd(
        settings, discovery_max_searches, discovery_max_tokens, safety_margin)
    per_source = estimate_extraction_cost_per_source_usd(
        settings, max_web_searches_per_source, extraction_max_tokens, safety_margin)
    synthesis = estimate_synthesis_cost_usd(
        settings, synthesize_max_tokens, forwarded_context_tokens, safety_margin)

    extraction_total = CostEstimate(
        label=f"A2 extraction (x{expected_source_count} źródeł)",
        search_fee_usd=round(per_source.search_fee_usd * expected_source_count, 6),
        output_cost_usd=round(per_source.output_cost_usd * expected_source_count, 6),
        conservative_usd=round(per_source.conservative_usd * expected_source_count, 6),
        expected_usd=round(per_source.expected_usd * expected_source_count, 6),
        safety_margin=safety_margin,
    )
    total = CostEstimate(
        label="TOTAL (A1 + A2 + B)",
        search_fee_usd=round(discovery.search_fee_usd + extraction_total.search_fee_usd, 6),
        output_cost_usd=round(
            discovery.output_cost_usd + extraction_total.output_cost_usd + synthesis.output_cost_usd, 6),
        conservative_usd=round(
            discovery.conservative_usd + extraction_total.conservative_usd + synthesis.conservative_usd, 6),
        expected_usd=round(
            discovery.expected_usd + extraction_total.expected_usd + synthesis.expected_usd, 6),
        safety_margin=safety_margin,
    )
    return {
        "discovery": discovery, "extraction_per_source": per_source,
        "extraction_total": extraction_total, "synthesis": synthesis, "total": total,
    }


def estimate_no_search_call_usd(
    settings: Settings,
    max_output_tokens: int,
    forwarded_context_tokens: int = 0,
    safety_margin: float = MIN_SAFETY_MARGIN,
) -> WorstCaseEstimate:
    """Sufit kosztu wywołania BEZ web search (np. etap 2 dwuetapowego researchu:
    synteza karty z już zebranych źródeł). Tu input jest pod naszą kontrolą
    (własny, ograniczony kontekst, nie surowe wyniki wyszukiwania) — zwykła
    kalkulacja z cennika jest wystarczająca, bez czynnika rekonstrukcji.
    """
    if max_output_tokens < 0 or forwarded_context_tokens < 0:
        raise ValueError("max_output_tokens i forwarded_context_tokens muszą być >= 0.")
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError(
            f"safety_margin ({safety_margin}) poniżej wymaganego minimum "
            f"({MIN_SAFETY_MARGIN}) — patrz docs/ERRORS_AND_FAILURES.md."
        )

    p = settings.pricing
    input_cost = forwarded_context_tokens / 1_000_000 * p.get("input_per_mtok", 0.0)
    output_cost = max_output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)
    subtotal = input_cost + output_cost
    total = subtotal * (1 + safety_margin)

    return WorstCaseEstimate(
        search_fee_usd=0.0,
        search_driven_token_cost_usd=round(input_cost, 6),
        output_cost_usd=round(output_cost, 6),
        subtotal_usd=round(subtotal, 6),
        safety_margin=safety_margin,
        total_usd=round(total, 6),
    )
