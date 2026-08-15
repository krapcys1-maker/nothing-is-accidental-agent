"""Jedyne miejsce ze stałymi.

Zasada nadrzędna tego pliku: **jeden limit, jedno miejsce**. Jeśli jakaś liczba
ma trafić także do promptu, prompt składa się z tej stałej (f-string), a nie
powtarza jej słownie. Poprzedni agent miał 22 pary liczb "stała w kodzie kontra
zdanie w prompcie" i nikt ich nigdy nie porównał — patrz
`archiwum/app/research/output_contract.py`.

Sufity tokenów są WYLICZANE z kontraktów, a nie wpisywane obok nich. Sufit
wpisany ręcznie obok promptu proszącego o więcej, niż się w nim mieści, uciął
odpowiedź DeepSeeka w połowie JSON-a przy pierwszym teście seryjnym.

Sekrety wyłącznie ze zmiennych środowiskowych. Wszystko inne tutaj, bo ten plik
jest w gicie, czyli jest identyczny na tym komputerze i na serwerze.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --- ścieżki -----------------------------------------------------------------
# Wszystko względem tego pliku. Żadnych ścieżek absolutnych, żadnych backslashy.

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent

ENV_PATH = AGENT_DIR / ".env"
DATA_DIR = AGENT_DIR / "data"
DB_PATH = DATA_DIR / "agent-v2.db"
PROMPTS_DIR = AGENT_DIR / "prompts"
ARTICLES_DIR = DATA_DIR / "articles"

# Korpus stylu. Przypięty hashem, bo to jedyna rzecz odróżniająca to konto od
# tysiąca innych — loader ma odmówić, jeśli ktoś po cichu podmieni głos, na
# który właściciel się zgodził.
STYLE_CORPUS = PROMPTS_DIR / "styl" / "article_style_samples_v1.txt"
STYLE_CORPUS_SHA256 = "0b05cefa6701e6447c44810b686828a83c19ca7ffb29066778a13c24207acb1d"
STYLE_PROFILES_DIR = REPO_ROOT / "instrukcja dla pisania artykulow"

load_dotenv(ENV_PATH)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- sekrety -----------------------------------------------------------------

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")

# --- tryby -------------------------------------------------------------------

DRY_RUN = _env("DRY_RUN", "false").lower() in {"1", "true", "yes"}
KILL_SWITCH = _env("KILL_SWITCH", "false").lower() in {"1", "true", "yes"}
NO_LIMIT = _env("AGENT_V2_NO_LIMIT", "0").lower() in {"1", "true", "yes"}

# --- modele ------------------------------------------------------------------
# Podział z briefu: DeepSeek tam, gdzie błąd kosztuje jedno tanie wywołanie;
# Claude tam, gdzie błąd kosztuje cały łańcuch albo jakość tekstu.

CLAUDE = "claude-opus-5"
SONNET = "claude-sonnet-5"
DEEPSEEK = "deepseek-v4-flash"
DEEPSEEK_PRO = "deepseek-v4-pro"  # ma server-side web_search przez /responses

# Decyzja właściciela 2026-08-15: DeepSeek do wszystkiego poza pisaniem.
# Pisanie zostaje u Opusa 5, bo to jest produkt.
MODEL_FOR = {
    "scout": DEEPSEEK_PRO,
    "feasibility": DEEPSEEK,  # tani odsiew przed drogim krokiem
    # Dyskoveria MUSI być u Anthropic (DeepSeek nie ma wyszukiwania), ale nie
    # musi być u Opusa: wybór adresów to praca mechaniczna, nie ocena. Każda
    # runda przesyła całą rozmowę od nowa, więc wejście rośnie do ~146 tys.
    # tokenów — na Opusie $0,73 za samo wejście, na Sonnecie $0,29.
    # Dyskoveria u Opusa, bo TYLKO ona działa od początku do końca.
    #
    # Sprawdzone na żywo, żeby nie powtarzać:
    #  - Haiku 4.5, Sonnet 5: NIE wywołują wyszukiwania w ogóle, wypisują adresy
    #    z pamięci (977 i 1073 tokeny wejścia, zero wyników). Także po jawnym
    #    nakazie szukania w prompcie.
    #  - DeepSeek v4-pro przez /responses: szuka NAPRAWDĘ i tanio ($0,05 wobec
    #    $0,46 u Opusa, dziewięć razy taniej), zwraca prawdziwe adresy (OSHA,
    #    Cornell Law, NFPA). ALE przy tym prompcie nie kończy: robi 11-22
    #    wyszukiwań, zużywa cały budżet wyjścia na rozumowanie i nigdy nie tworzy
    #    bloku `message`. Przy krótkim prompcie kończy poprawnie, więc droga
    #    prowadzi przez uproszczenie promptu dyskoverii, nie przez model.
    #    Po skróceniu promptu do ~250 słów kończy poprawnie — i tak zostaje.
    #  - Opus jest NIEPRZEWIDYWALNY kosztowo: te same 8 wyszukiwań dały raz
    #    52 767 tokenów wejścia ($0,46), a raz 285 759 ($1,65), bo wielkość
    #    wyników zależy od tematu. To dyskwalifikuje go z etapu, który biegnie
    #    codziennie bez nadzoru.
    "discovery": DEEPSEEK_PRO,
    "classify": DEEPSEEK,  # mechaniczne, wysokowolumenowe
    "synthesis": DEEPSEEK_PRO,
    "write": CLAUDE,  # TO JEST PRODUKT — zostaje u Opusa 5
    "review": DEEPSEEK_PRO,
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Głębokość rozumowania DeepSeeka na /responses. Tokeny rozumowania liczą się
# do sufitu wyjścia, więc przy `high` model kończy budżet na szukaniu i nie
# zdąża napisać odpowiedzi.
DEEPSEEK_EFFORT = "low"

# Tryb tani: wszystko na DeepSeeku. Do testowania HYDRAULIKI — czy łańcuch
# przechodzi, czy JSON się parsuje, czy zapis działa. Przebieg kosztuje wtedy
# grosze zamiast ~1 USD. NIE służy do oceny jakości tekstu, bo produktem jest
# to, co napisze Opus. Dyskoveria zostaje u Claude'a nawet tutaj: DeepSeek nie
# ma wyszukiwania po stronie dostawcy, więc bez niej nie ma czego pobierać.
CHEAP_MODE = _env("AGENT_V2_CHEAP", "0").lower() in {"1", "true", "yes"}

if CHEAP_MODE:
    MODEL_FOR = {k: (CLAUDE if k == "discovery" else DEEPSEEK) for k in MODEL_FOR}

# --- cennik ------------------------------------------------------------------
# USD za milion tokenów. `verified` mówi, czy stawka została potwierdzona realnym
# rozliczeniem. Niepotwierdzonej ceny nie wolno podawać jako faktu — koszt liczony
# taką stawką jest oznaczany w bazie (`calls.price_verified = 0`).

PRICING = {
    CLAUDE: {"in": 5.00, "out": 25.00, "verified": True},
    SONNET: {"in": 3.00, "out": 15.00, "verified": True},
    DEEPSEEK: {"in": 0.28, "out": 0.42, "verified": False},
    DEEPSEEK_PRO: {"in": 0.28, "out": 0.42, "verified": False},
}

# Filtrowanie dynamiczne (`_20260209`) jest na Opusie i Sonnecie 5.
WEB_SEARCH_TOOL = {
    CLAUDE: "web_search_20260209",
    SONNET: "web_search_20260209",
}

# Wyszukiwanie po stronie Anthropic: USD za 1000 zapytań.
WEB_SEARCH_USD_PER_1K = 10.00

# --- limity pieniężne --------------------------------------------------------

DAILY_LIMIT_USD = 5.00
MONTHLY_LIMIT_USD = 40.00

# Sufit na JEDEN przebieg. Działa ZAWSZE, także przy AGENT_V2_NO_LIMIT=1.
# „Bez limitu na budowę" miało znaczyć „nie blokuj eksperymentów", a nie
# „pozwól jednemu przebiegowi kosztować 2 USD". Przebieg 16 kosztował $1,92,
# z czego $1,33 poszło na 31 niepotrzebnych rund wyszukiwania.
RUN_LIMIT_USD = 1.60

# =============================================================================
# KONTRAKTY — ile czego prosimy. Sufity tokenów liczą się z tych liczb niżej.
# =============================================================================

# --- skaut i różnorodność ----------------------------------------------------
TOPIC_COUNT = 6
DIVERSITY_LOOKBACK = 5

# --- dyskoveria --------------------------------------------------------------
DISCOVERY_MAX_RESULTS = 6
# Zmierzone na jednym trudnym temacie (szpara pod drzwiami kabiny):
#   31 rund -> 7 organizacji, 6 pierwotnych, $1,33  (bez limitu, przeciek)
#    6 rund -> 1 organizacja,  0 pierwotnych, $0,53  (za mało, temat nie wyszedł)
# Koszt krańcowy ~$0,09 za rundę, bo każda przesyła całą rozmowę od nowa.
# Przy suficie $1,60 na przebieg dyskoveria może wziąć ~$0,8.
DISCOVERY_MAX_SEARCHES = 8
MIN_PRIMARY_SOURCES = 2  # wymóg właściciela: w korpusie ≥2 dokumenty pierwotne
MIN_WHY_SOURCES = 2  # ≥2 źródła mówiące DLACZEGO, nie tylko treść reguły

# Hosty, które serwują automatom CAPTCHA albo są płatne. Nie omijamy blokad —
# wykrywamy je i nie marnujemy na nie zapytań.
BLOCKED_HOSTS = (
    "federalregister.gov", "regulations.gov", "congress.gov", "ecfr.gov",
    "sciencedirect.com", "tandfonline.com", "academia.edu", "researchgate.net",
)

# --- klasyfikacja ------------------------------------------------------------
CLASSIFY_MAX_INPUT_CHARS = 90_000
CLASSIFY_MAX_EXCERPTS = 12
CLASSIFY_MAX_EXCERPT_CHARS = 700

# --- karta dowodowa ----------------------------------------------------------
CARD_MIN_CONFIRMED = 5
CARD_MAX_CONFIRMED = 8
CARD_MAX_UNCERTAIN = 3
CARD_MAX_CONTRADICTIONS = 3
CARD_MIN_NUMBERS = 3
CARD_MAX_NUMBERS = 8
CARD_MAX_CLAIM_CHARS = 240

# --- długość artykułu --------------------------------------------------------
# Wyprowadzone z dwóch tekstów, które właściciel uznał za dobre:
# ARTYKUL_DRAFT.md = 1048 słów / 62 zdania, ARTYKUL_DRAFT_2.md = 1101 słów / 58 zdań.
# Cel idzie do promptu pisarza. Długość NIE blokuje artykułu — jest notatką,
# bo na starym agencie nie złapała nic, a blokowała.

TARGET_WORDS = 1075
MIN_WORDS = 950
MAX_WORDS = 1250

# Artykuł powstaje po angielsku — konto jest anglojęzyczne.
ARTICLE_LANGUAGE = "English"

# =============================================================================
# SUFITY TOKENÓW — wyliczane z kontraktów powyżej
# =============================================================================

# Zachowawczo, żeby sufit był raczej za duży niż za mały. Zmierzone na starym
# agencie: CJK 2,19x, cyrylica 1,41x; dla angielskiego 3,5 znaku na token
# z zapasem.
CHARS_PER_TOKEN = 3.5

# Ile tokenów zajmuje rusztowanie JSON-a, klucze i pola opisowe poza samą treścią.
JSON_OVERHEAD_TOKENS = 1200


# Myślenie na Opusie 5 jest domyślnie włączone, liczy się jak tokeny wyjściowe
# i NIE jest częścią kontraktu — więc sufit wyliczony z samego kontraktu potrafi
# uciąć odpowiedź w połowie mimo poprawnej arytmetyki.
# 16 tys., bo modele DeepSeek v4 rozumują znacznie obficiej niż Claude i przy
# 6 tys. ucinało syntezę. Sufit nic nie kosztuje, dopóki nie zostanie zużyty —
# płacimy za tokeny, nie za limit.
THINKING_HEADROOM_TOKENS = 16000

# Głębokość myślenia. Jawnie, bo domyślne `high` na Opusie 5 potrafi podwoić
# rachunek za wyjście bez pytania.
EFFORT = {
    "scout": "medium",
    "discovery": "medium",
    "synthesis": "high",
    "write": "high",
    "review": "high",
}


def _tokens_for(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN) + JSON_OVERHEAD_TOKENS


MAX_TOKENS = {
    # 6 tematów: tytuł, pytanie, siedem ocen liczbowych
    "scout": _tokens_for(TOPIC_COUNT * 900),
    # jedna ocena na temat, każda z uzasadnieniem
    "feasibility": _tokens_for(TOPIC_COUNT * 500),
    # Dyskoveria dostaje budżet z zapasem, bo DeepSeek liczy do niego tokeny
    # rozumowania KAŻDEJ rundy wyszukiwania. Przy ciasnym budżecie kończył
    # szukanie i nigdy nie tworzył bloku `message`: 26 wyszukiwań, status
    # "completed", zero tekstu.
    "discovery": 32000,
    # DOKŁADNIE tyle, ile prosi prompt: 12 fragmentów po 700 znaków plus liczby
    "classify": _tokens_for(
        CLASSIFY_MAX_EXCERPTS * CLASSIFY_MAX_EXCERPT_CHARS + 2000
    ),
    # karta: twierdzenia z cytatami, liczby, sprzeczności, granice
    "synthesis": _tokens_for(
        CARD_MAX_CONFIRMED * (CARD_MAX_CLAIM_CHARS + CLASSIFY_MAX_EXCERPT_CHARS)
        + CARD_MAX_NUMBERS * 200
        + 4000
    ),
    # artykuł plus zapas na myślenie
    "write": _tokens_for(MAX_WORDS * 7) + 6000,
    # recenzja rozlicza KAŻDE zdanie: ~118 tokenów na segment (zmierzone),
    # 49-65 segmentów przy 1000-1250 słowach
    "review": int(70 * 118 * 1.4) + JSON_OVERHEAD_TOKENS,
}

# Zapas na myślenie dostają WSZYSTKIE etapy, nie tylko Claude'owe: modele
# DeepSeek v4 też rozumują, a tokeny rozumowania liczą się do sufitu wyjścia.
# Odsiew ucięło na 2057 tokenach dokładnie z tego powodu.
MAX_TOKENS = {
    purpose: ceiling + THINKING_HEADROOM_TOKENS
    for purpose, ceiling in MAX_TOKENS.items()
}

# --- terminy -----------------------------------------------------------------
# Termin musi pokryć własny sufit tokenów. Zmierzone: mediana 16,08 ms na token
# wyjściowy (19 rozliczonych przebiegów, R² 0,98). Poprzedni agent ustawił 60 s
# przy suficie 4096 tokenów, co jest arytmetycznie niemożliwe (65,9 s potrzebne).

MS_PER_OUTPUT_TOKEN = 16.08
TIMEOUT_MARGIN = 1.5


def timeout_for(max_tokens: int) -> float:
    """Termin w sekundach, który realnie pokrywa podany sufit tokenów."""
    return round(max_tokens * MS_PER_OUTPUT_TOKEN / 1000 * TIMEOUT_MARGIN, 1)


# --- pobieranie --------------------------------------------------------------
# Odpowiedź 200 bywa nie dokumentem, tylko wyzwaniem. Te frazy złapały trzy realne
# odmowy przy pierwszym przebiegu starego agenta. Blokadę wykrywamy i zapisujemy
# jako nieudane pobranie — NIGDY jej nie omijamy.

REFUSAL_PHRASES = (
    "you have been blocked",
    "access denied",
    "are you a robot",
    "verify you are human",
    "enable javascript and cookies",
    "unusual traffic",
    "captcha",
    "request has been flagged",
    "programmatic access to these sites is limited",
)

FETCH_TIMEOUT_S = 30.0
FETCH_MIN_CHARS = 400  # krótszy tekst to zwykle strona-zajawka, nie dokument
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; NothingIsAccidental/1.0; +editorial research)"

# --- bramki jakości ----------------------------------------------------------
# NIC NIE BLOKUJE. Te cztery są zgłaszane właścicielowi jako uwagi do
# przeczytania; artykuł powstaje zawsze i trafia do szuflady.

FLAGGED_GATES = (
    "FAKT_BEZ_POKRYCIA",  # rdzeń ochrony
    "LICZBA_SPOZA_KORPUSU",  # 5 zmyślonych statystyk na starym agencie
    "ZMYSLONE_PRZEZYCIE",  # 4 przypadki
    "NIEISTNIEJACE_BADANIE",  # 3 przypadki
)

# Jedno podejście. Bez przepisywania — to tam paliły się pieniądze i tam dwie
# bramki starego agenta odpowiedziały różnie na to samo pytanie.
ATTEMPTS = 1
