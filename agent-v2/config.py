"""Jedyne miejsce ze stałymi.

Zasada nadrzędna tego pliku: **jeden limit, jedno miejsce**. Jeśli jakaś liczba
ma trafić także do promptu, prompt składa się z tej stałej (f-string), a nie
powtarza jej słownie. Poprzedni agent miał 22 pary liczb "stała w kodzie kontra
zdanie w prompcie" i nikt ich nigdy nie porównał — patrz
`archiwum/app/research/output_contract.py`.

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
DEEPSEEK = "deepseek-chat"

MODEL_FOR = {
    "scout": CLAUDE,  # zły temat psuje cały łańcuch
    "feasibility": DEEPSEEK,  # tani odsiew przed drogim krokiem
    "discovery": CLAUDE,  # wymaga wyszukiwania po stronie dostawcy
    "classify": DEEPSEEK,  # mechaniczne, wysokowolumenowe
    "synthesis": CLAUDE,  # ocena, co dowody potwierdzają
    "write": CLAUDE,  # to jest produkt
    "review": CLAUDE,  # to jest bramka jakości
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# --- cennik ------------------------------------------------------------------
# USD za milion tokenów. `verified` mówi, czy stawka została potwierdzona realnym
# rozliczeniem. Niepotwierdzonej ceny nie wolno podawać jako faktu — koszt liczony
# taką stawką jest oznaczany w bazie (`calls.price_verified = 0`).

PRICING = {
    CLAUDE: {"in": 5.00, "out": 25.00, "verified": True},
    DEEPSEEK: {"in": 0.28, "out": 0.42, "verified": False},
}

# Wyszukiwanie po stronie Anthropic: USD za 1000 zapytań.
WEB_SEARCH_USD_PER_1K = 10.00

# --- limity pieniężne --------------------------------------------------------

DAILY_LIMIT_USD = 5.00
MONTHLY_LIMIT_USD = 40.00

# --- limity wywołań ----------------------------------------------------------
# Termin musi pokryć własny sufit tokenów. Zmierzone na starym agencie:
# mediana 16,08 ms na token wyjściowy (19 rozliczonych przebiegów, R² 0,98).
# Stąd TIMEOUT_S wyliczamy, a nie zgadujemy — poprzedni agent ustawił 60 s przy
# suficie 4096 tokenów, co jest arytmetycznie niemożliwe (65,9 s potrzebne).

MS_PER_OUTPUT_TOKEN = 16.08
TIMEOUT_MARGIN = 1.5


def timeout_for(max_tokens: int) -> float:
    """Termin w sekundach, który realnie pokrywa podany sufit tokenów."""
    return round(max_tokens * MS_PER_OUTPUT_TOKEN / 1000 * TIMEOUT_MARGIN, 1)


# Sufity wyjścia per etap. Myślenie na Opus 5 jest włączone domyślnie i liczy się
# jak tokeny wyjściowe, więc sufit musi objąć jedno i drugie.
MAX_TOKENS = {
    "scout": 6000,
    "feasibility": 1500,
    "discovery": 12000,
    "classify": 1500,
    "synthesis": 8000,
    "write": 12000,
    "review": 16000,
}

# Głębokość myślenia. Jawnie, bo domyślne `high` na Opusie 5 potrafi podwoić
# rachunek za wyjście bez pytania.
EFFORT = {
    "scout": "medium",
    "discovery": "medium",
    "synthesis": "high",
    "write": "high",
    "review": "high",
}

# --- reguła różnorodności ----------------------------------------------------
# Skaut nie nazywa już serwisu, więc domena powstaje dopiero w dyskoverii.
# Lista domen z ostatnich N artykułów idzie do dyskoverii jako wykluczenie.

DIVERSITY_LOOKBACK = 5

# --- dyskoveria --------------------------------------------------------------
# Te liczby wchodzą do promptu przez f-string, więc nie mogą się z nim rozjechać.

DISCOVERY_MAX_RESULTS = 10
DISCOVERY_MAX_SEARCHES = 6
MIN_PRIMARY_SOURCES = 2  # wymóg właściciela: w korpusie ≥2 dokumenty pierwotne
MIN_WHY_SOURCES = 2  # ≥2 źródła mówiące DLACZEGO, nie tylko treść reguły

# Hosty, które serwują automatom CAPTCHA albo są płatne. Nie omijamy blokad —
# wykrywamy je i nie marnujemy na nie zapytań.
BLOCKED_HOSTS = (
    "federalregister.gov", "regulations.gov", "congress.gov", "ecfr.gov",
    "sciencedirect.com", "tandfonline.com", "academia.edu", "researchgate.net",
)

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
# Ile znaków jednego dokumentu trafia do klasyfikacji. DeepSeek jest tani, więc
# przemiela cały korpus; do drogiego Opusa idą już tylko wybrane fragmenty.
CLASSIFY_MAX_INPUT_CHARS = 90_000
CLASSIFY_MAX_EXCERPTS = 12
CLASSIFY_MAX_EXCERPT_CHARS = 700
# --- karta dowodowa ----------------------------------------------------------
# Kontrakt rozmiaru. Te liczby wchodzą do promptu przez f-string i są sprawdzane
# przez ten sam plik — nie mogą się rozjechać. Poprzedni agent trzymał je
# w dwóch miejscach (stała + zdanie w prompcie) i model posłuszny instrukcji
# niszczył opłaconą kartę, bo walidator przyjmował mniej, niż prompt prosił.

CARD_MIN_CONFIRMED = 5
CARD_MAX_CONFIRMED = 8
CARD_MAX_UNCERTAIN = 3
CARD_MAX_CONTRADICTIONS = 3
CARD_MIN_NUMBERS = 3
CARD_MAX_NUMBERS = 8
CARD_MAX_CLAIM_CHARS = 240
FETCH_MIN_CHARS = 400  # krótszy tekst to zwykle strona-zajawka, nie dokument
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; NothingIsAccidental/1.0; +editorial research)"

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

# --- bramki jakości ----------------------------------------------------------
# Blokują tylko te cztery. Każda ma udokumentowane trafienie na starym agencie.
# Reszta (styl, tytuł, brief, długość, myślniki) jest zapisywana jako notatka
# i NIE blokuje — decyzja właściciela z 2026-08-15.

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
