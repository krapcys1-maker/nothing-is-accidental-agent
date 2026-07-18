"""Jawny kontrakt rozmiaru odpowiedzi Research Card (single research, prompt v3).

Powstał po trzech kontrolowanych realnych próbach (2026-07-17, docs/ERRORS_AND_FAILURES.md):

1. run 8bcf15e4, max_tokens=1500 -> stop_reason=max_tokens (usage output 1667 > 1500),
2. run 65841541, max_tokens=3000 -> end_turn, 2727 output, kompletny JSON 6697 znaków,
3. run 08aa35eb, max_tokens=3000 -> stop_reason=max_tokens (usage output 3155 > 3000),
   widoczny JSON tylko 4038 znaków.

Dwa fakty zmierzone z tych prób, na których stoi ten moduł:

- `max_tokens` ogranicza KAŻDY segment generacji osobno, a `usage.output_tokens`
  jest sumą wszystkich segmentów (SDK: "inclusive, authoritative total used for
  billing") — przy web search istnieje krótki segment przed wyszukiwaniem
  (~155-167 tokenów w obu uciętych próbach), więc usage może legalnie przekroczyć
  `max_tokens`. To korekta interpretacji diagnostyki, nie bug rozliczeń.
- Zafakturowany output zawiera NIEWIDOCZNE tokeny (wewnętrzne rozumowanie —
  `usage.output_tokens_details.thinking_tokens` w SDK — oraz bloki tool-use /
  cytowań), które NIE trafiają do `text`, a liczą się do limitu segmentu.
  Zmierzone: próba #2 ~715-1237 tokenów narzutu, próba #3 ~1963-2232 tokenów
  narzutu w segmencie finalnym. Ten narzut ma dużą wariancję przy identycznym
  prompcie — dlatego stały limit 3000 nie dawał stabilnego zakończenia.

Kontrakt: model dostaje jawne limity słowne per pole (prompt v3), a parser
egzekwuje deterministycznie limity znakowe (słowa * ~8 znaków, z zapasem) oraz
liczności. Przekroczenie = typowany `ResearchCardSizeContractError` (podklasa
`ResearchSchemaError`): fail-closed, usage i settlement zachowane, terminalny
FAILED, zero retry, zero cichego obcinania. Minima jakościowe (np. >=4 claims)
pozostają domeną bramki `validate_draft` (REJECT karty, nie błąd parsera) —
deterministyczny kontrakt rozmiaru chroni wyłącznie górną granicę.
"""
from __future__ import annotations

import math

from app.research.base import ResearchCardSizeContractError, ResearchDraft

# --- Budżet treści (górne granice; prompt v3 podaje odpowiadające limity słowne).
# Mapowanie: limit znaków ~= limit słów * 8 (realne odpowiedzi: ~7.2-7.6 znaka
# na słowo ze spacją), z zapasem, żeby lokalna walidacja nie odrzucała odpowiedzi,
# które uczciwie trzymają się limitu słownego.
MAX_QUESTION_CHARS = 300          # prompt: <= 30 słów (zapas na echo dłuższego pytania)
MAX_WORKING_THESIS_CHARS = 480    # prompt: <= 60 słów
MAX_MAIN_MECHANISM_CHARS = 800    # prompt: <= 100 słów
MAX_CONFIRMED_CLAIMS = 6          # prompt: 4-6
MAX_CLAIM_CHARS = 240             # prompt: <= 30 słów na claim
MAX_UNCERTAIN_CLAIMS = 3
MAX_CONTRADICTIONS = 3
MAX_CONTRADICTION_CHARS = 280     # prompt: <= 35 słów
MAX_COUNTERARGUMENT_CHARS = 480   # prompt: <= 60 słów
MAX_CITABLE_NUMBERS = 6           # prompt: 3-6
MAX_CITABLE_NUMBER_CHARS = 120    # prompt: <= 15 słów, krótkie stringi
MAX_VISUAL_IDEA_CHARS = 400       # prompt: <= 50 słów
MAX_SOURCES = 6                   # prompt: 4-6
MAX_SOURCE_URL_CHARS = 200        # realne maksimum z prób: 106
MAX_SOURCE_TITLE_CHARS = 120      # prompt: <= 15 słów
MAX_SOURCE_AUTHOR_CHARS = 80      # prompt: <= 10 słów
MAX_SOURCE_PUBLISHED_AT_CHARS = 40
MAX_SUPPORTS_CLAIM_CHARS = MAX_CLAIM_CHARS  # dokładny tekst jednego confirmed claim

# Twardy sufit całej zserializowanej odpowiedzi (surowy tekst, przed dekodowaniem).
# Suma budżetów pól na granicach = ~10.5k znaków + struktura JSON; 16000 zostawia
# jawny zapas na escapowanie (np. \" i \uXXXX potrafią zwielokrotnić znaki).
MAX_RESPONSE_CHARS = 16000

# --- Profil tokenowy Research Card (jawny profil TEJ operacji, nie globalny).
# Kanoniczny payload z KAŻDYM polem dokładnie na granicy kontraktu (ASCII)
# serializuje się do dokładnie 11192 znaków (pinowane testem). Konserwatywna
# estymacja tokenów: znaki / 3.5 (zmierzone cl100k dla realnego kompaktowego
# JSON-a: 4.49 znaka/token; 3.5 dodaje zapas na różnice tokenizera Claude
# i segmenty z URL-ami). Lokalny dokładny tokenizer Claude nie istnieje —
# to ESTYMACJA z jawnym, konserwatywnym marginesem.
MAX_CORRECT_PAYLOAD_CHARS = 11192
CONSERVATIVE_CHARS_PER_TOKEN = 3.5
ESTIMATED_MAX_PAYLOAD_TOKENS = math.ceil(
    MAX_CORRECT_PAYLOAD_CHARS / CONSERVATIVE_CHARS_PER_TOKEN
)  # = 3198

# Empiryczny najgorszy zmierzony niewidoczny narzut outputu (rozumowanie + tool-use
# + cytowania) w segmencie finalnym: ~2232 tokenów (próba #3), zaokrąglone w górę.
HIDDEN_OUTPUT_OVERHEAD_TOKENS = 2300

# Wybrany profil: 6000 >= 3198 (payload na granicach, konserwatywnie) + 2300
# (najgorszy zmierzony narzut) + 502 jawnego marginesu (~9%). Kandydaci odrzuceni:
# 3500/4000 — mniejsze niż suma dwóch REALNYCH obserwacji (narzut 2232 + dobry
# JSON ~2000 tokenów); 5000 — poniżej sumy 3198+2300=5498, czyli ujemny margines.
# Mieści się w zatwierdzonym paśmie providera [256, 8192] (durable_intent).
RESEARCH_CARD_MAX_TOKENS = 6000
RESEARCH_CARD_TOKEN_SAFETY_MARGIN = (
    RESEARCH_CARD_MAX_TOKENS - ESTIMATED_MAX_PAYLOAD_TOKENS - HIDDEN_OUTPUT_OVERHEAD_TOKENS
)  # = 502

# --- Jawny profil operacyjny działania "Research Card" (nie globalny limit).
# max_web_searches=1: wszystkie trzy realne próby wykonały dokładnie 1 wyszukiwanie,
# a HIDDEN_OUTPUT_OVERHEAD_TOKENS zmierzono właśnie przy 1 wyszukiwaniu — każde
# dodatkowe dodaje kolejny segment pre-search (~155-167 tokenów) i destabilizuje
# budżet. Cap kosztu: pesymistyczny sufit estymatora dla (6000 tokenów, 1 search,
# profil anthropic-sonnet-5-intro-2026-07) = 0.172500 USD; rekomendowany
# max_cost_usd = 0.20 (zaokrąglony w górę, nadal << miesięcznego limitu 40 USD).
# Operator przekazuje te wartości jawnie w CLI; ten profil jest kanonicznym
# źródłem rekomendacji dla następnej kontrolowanej próby.
RESEARCH_CARD_MAX_WEB_SEARCHES = 1
RESEARCH_CARD_RECOMMENDED_MAX_COST_USD = "0.20"


def _size_error(field: str, requirement: str) -> ResearchCardSizeContractError:
    return ResearchCardSizeContractError(
        f"Research response classification=size_contract; field={field}; "
        f"expected={requirement}."
    )


def enforce_single_research_response_size(text: str) -> None:
    """Sufit całej surowej odpowiedzi — zanim cokolwiek zostanie zdekodowane."""
    if isinstance(text, str) and len(text) > MAX_RESPONSE_CHARS:
        raise _size_error("response", f"at_most_{MAX_RESPONSE_CHARS}_chars")


def _check_string(value: str | None, *, field: str, max_chars: int) -> None:
    if value is not None and len(value) > max_chars:
        raise _size_error(field, f"at_most_{max_chars}_chars")


def _check_string_list(
    values: list[str], *, field: str, max_items: int, max_chars: int,
) -> None:
    if len(values) > max_items:
        raise _size_error(field, f"at_most_{max_items}_items")
    for index, value in enumerate(values):
        _check_string(value, field=f"{field}[{index}]", max_chars=max_chars)


def enforce_single_research_draft_budget(draft: ResearchDraft) -> None:
    """Deterministyczna górna granica każdego pola Research Card (fail-closed).

    Wywoływane po pełnej walidacji typów w parserze — tu każde pole ma już
    właściwy typ, sprawdzamy wyłącznie rozmiary i liczności.
    """
    _check_string(draft.question, field="question", max_chars=MAX_QUESTION_CHARS)
    _check_string(
        draft.working_thesis, field="working_thesis",
        max_chars=MAX_WORKING_THESIS_CHARS,
    )
    _check_string(
        draft.main_mechanism, field="main_mechanism",
        max_chars=MAX_MAIN_MECHANISM_CHARS,
    )
    _check_string_list(
        draft.confirmed_claims, field="confirmed_claims",
        max_items=MAX_CONFIRMED_CLAIMS, max_chars=MAX_CLAIM_CHARS,
    )
    _check_string_list(
        draft.uncertain_claims, field="uncertain_claims",
        max_items=MAX_UNCERTAIN_CLAIMS, max_chars=MAX_CLAIM_CHARS,
    )
    _check_string_list(
        draft.contradictions, field="contradictions",
        max_items=MAX_CONTRADICTIONS, max_chars=MAX_CONTRADICTION_CHARS,
    )
    _check_string(
        draft.strongest_counterargument, field="strongest_counterargument",
        max_chars=MAX_COUNTERARGUMENT_CHARS,
    )
    _check_string_list(
        draft.citable_numbers, field="citable_numbers",
        max_items=MAX_CITABLE_NUMBERS, max_chars=MAX_CITABLE_NUMBER_CHARS,
    )
    _check_string(
        draft.visual_idea, field="visual_idea", max_chars=MAX_VISUAL_IDEA_CHARS,
    )
    if len(draft.sources) > MAX_SOURCES:
        raise _size_error("sources", f"at_most_{MAX_SOURCES}_items")
    for index, source in enumerate(draft.sources):
        prefix = f"sources[{index}]"
        _check_string(source.url, field=f"{prefix}.url", max_chars=MAX_SOURCE_URL_CHARS)
        _check_string(
            source.title, field=f"{prefix}.title", max_chars=MAX_SOURCE_TITLE_CHARS,
        )
        _check_string(
            source.author_or_org, field=f"{prefix}.author_or_org",
            max_chars=MAX_SOURCE_AUTHOR_CHARS,
        )
        _check_string(
            source.published_at, field=f"{prefix}.published_at",
            max_chars=MAX_SOURCE_PUBLISHED_AT_CHARS,
        )
        _check_string(
            source.supports_claim, field=f"{prefix}.supports_claim",
            max_chars=MAX_SUPPORTS_CLAIM_CHARS,
        )
