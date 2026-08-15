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
# Zapasowo .env z katalogu głównego repozytorium: właściciel dopisał klucz
# OpenAI tam, a agent szukał go tylko u siebie i widział "BRAK". Sekret ma leżeć
# w jednym miejscu, więc zamiast kopiować go w dwa pliki, czytamy oba. Bez
# `override` — plik agenta zawsze wygrywa.
load_dotenv(REPO_ROOT / ".env", override=False)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- sekrety -----------------------------------------------------------------

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
OPENAI_API_KEY = _env("OPENAI_API_KEY")   # wylacznie do grafik

# Grafika do artykulu. Wybor NIE jest podyktowany cena: przy jednym obrazie na
# artykul nawet najdrozsza opcja to grosze miesiecznie, a taniej znaczy tu
# gorzej i mniej powtarzalnie. Rozmiar 1536x1024 mniej-wiecej odpowiada
# proporcjom naglowka na Substacku.
IMAGE_MODEL = "gpt-image-1.5"
IMAGE_SIZE = "1536x1024"
IMAGE_QUALITY = "high"
IMAGE_PRICE_USD = 0.04   # cennik sierpien 2026, NIEPOTWIERDZONY na fakturze
IMAGE_TIMEOUT_S = 300

# Konto na Substacku.
SUBSTACK_HANDLE = "nothingisaccidental"

# Czy agent ma klikac "Wylacz wykrywanie AI" przy kazdej publikacji.
# ZOSTAWIONE NA NIE i to jest decyzja wlasciciela, nie kodu: to jest wybor
# publiczny, widoczny dla czytelnikow, a nie ustawienie techniczne. Oswiadczenie
# "Jak to robie" (prompts/OSWIADCZENIE_AI.md) pokazuje sie NIEZALEZNIE od tego
# przelacznika, wiec wylaczenie wykrywania niczego nie zaslania — zmienia tylko
# to, czy skan zwraca wynik, czy "nie kwalifikuje sie".
WYLACZ_WYKRYWANIE_AI = False

# --- tryby -------------------------------------------------------------------

DRY_RUN = _env("DRY_RUN", "false").lower() in {"1", "true", "yes"}
KILL_SWITCH = _env("KILL_SWITCH", "false").lower() in {"1", "true", "yes"}
NO_LIMIT = _env("AGENT_V2_NO_LIMIT", "0").lower() in {"1", "true", "yes"}

# --- modele ------------------------------------------------------------------
# Podział z briefu: DeepSeek tam, gdzie błąd kosztuje jedno tanie wywołanie;
# Claude tam, gdzie błąd kosztuje cały łańcuch albo jakość tekstu.

CLAUDE = "claude-opus-5"
SONNET = "claude-sonnet-5"
FABLE = "claude-fable-5"  # najmocniejszy, dwa razy droższy od Opusa
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
    # TO JEST PRODUKT. Fable 5 po porównaniu A/B na identycznej karcie: krótszy
    # i bliższy celu długości (1127 wobec 1204 słów), ale przede wszystkim
    # dokładniejszy — wyłapał, że przepis o przywiązanych nakrętkach jest węższy
    # niż jego popularne streszczenie, i skorygował omówienie RTÉ. Opus tego nie
    # zauważył. Kosztuje 3,5x więcej, co przy 4 artykułach miesięcznie znaczy
    # $2,12 zamiast $0,61.
    "write": FABLE,
    "review": DEEPSEEK_PRO,
    # Notki i komentarze na DeepSeeku — decyzja właściciela. Przy ~$0,002 za
    # sztukę można wygenerować kilkanaście kandydatów i wybrać najlepszego,
    # co dla czterdziestu słów działa lepiej niż jedno drogie podejście.
    "note": DEEPSEEK_PRO,
    "comment": DEEPSEEK_PRO,
    "reply": DEEPSEEK_PRO,
    "factcheck": DEEPSEEK_PRO,
    "curiosity": DEEPSEEK_PRO,
    "grafika": DEEPSEEK_PRO,
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

# Podmiana samego pisarza, do porównań A/B na tej samej karcie dowodowej:
#   AGENT_V2_WRITER=claude-fable-5 python agent-v2/run.py --use-cache
_writer = _env("AGENT_V2_WRITER")
if _writer:
    MODEL_FOR["write"] = _writer

# Rysowanie nie ma nic wspolnego z trybem taniego tekstu, wiec dopisujemy je PO
# podmianach powyzej — inaczej CHEAP_MODE przestawilby generator obrazow na
# model jezykowy. Etapy bez tokenow nie maja sufitu tokenow: wpisanie tam liczby
# byloby zmyslona wartoscia w pliku, ktory ma byc jedynym zrodlem prawdy.
MODEL_FOR["obraz"] = IMAGE_MODEL
BEZ_TOKENOW = {"obraz"}

# --- cennik ------------------------------------------------------------------
# USD za milion tokenów. `verified` mówi, czy stawka została potwierdzona realnym
# rozliczeniem. Niepotwierdzonej ceny nie wolno podawać jako faktu — koszt liczony
# taką stawką jest oznaczany w bazie (`calls.price_verified = 0`).

PRICING = {
    CLAUDE: {"in": 5.00, "out": 25.00, "verified": True},
    SONNET: {"in": 3.00, "out": 15.00, "verified": True},
    FABLE: {"in": 10.00, "out": 50.00, "verified": True},
    # Skalibrowane fakturą DeepSeeka z 2026-08-15: 138 wywołań, 3 968 825
    # tokenów, $0,49. Mój wcześniejszy szacunek ($0,28/$0,42) dawał $0,8366 —
    # przeszacowanie o 70%, bo duża część wejścia idzie z cache'a taniej.
    # Te stawki odtwarzają fakturę z dokładnością do centa.
    DEEPSEEK: {"in": 0.10, "out": 0.25, "verified": True},
    DEEPSEEK_PRO: {"in": 0.10, "out": 0.25, "verified": True},
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
# 10, nie 6. Odsiew przy pobieraniu jest brutalny: martwe adresy (404), blokady
# botów i strony bez treści potrafią zjeść pięć z sześciu źródeł. Przy sześciu
# znalezionych został raz jeden użyteczny dokument i artykuł stanął na nim
# samym. DeepSeek jest tani, więc szukamy szerzej.
DISCOVERY_MAX_RESULTS = 10
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

# Zmierzone na dziewięciu artykułach: przy „cel 1075, zakres 950-1250" model
# kotwiczył się przy górnej granicy (średnia 1212). Sufit obniżony, a prompt
# mówi teraz wprost, że 1075 to cel, nie podłoga.
TARGET_WORDS = 1075
MIN_WORDS = 950
MAX_WORDS = 1200

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
    # Recenzja rozlicza KAŻDE zdanie i jest najdroższa w tokenach wyjścia:
    # DeepSeek dawał tu 19-22 tys. tokenów, a przy 28 764 ucięło go na żywo
    # i straciliśmy główny sygnał jakości. Sufit nic nie kosztuje, dopóki nie
    # zostanie zużyty.
    "review": 48000,
    "note": _tokens_for(400) + 8000,
    "comment": _tokens_for(600) + 8000,
    "reply": _tokens_for(600) + 8000,
    "factcheck": 24000,
    "curiosity": 24000,
    "grafika": 4000,
}

# --- notki i komentarze ------------------------------------------------------
# Zmierzone na publicznych analizach Substacka: 33-64 słowa dają najwyższe
# zaangażowanie (449 średnich reakcji), 65-256 słów wyraźnie spada. Środek jest
# najgorszy, a to właśnie tam ląduje instynkt "napiszę akapit".
NOTE_MIN_WORDS = 33
NOTE_MAX_WORDS = 64

# Ilu kandydatów generujemy, żeby wybrać jednego. Sensowne tylko dlatego, że
# DeepSeek kosztuje grosze — u Fable'a byłoby to nie do obronienia.
# Trzech kandydatow, nie pieciu: odkad kazda notka dostaje WLASNY fakt,
# piaty wariant tego samego zdania niczego nie dokladal, a placilismy za
# niego i za jego weryfikacje.
NOTE_CANDIDATES = 3
# Ile ciekawostek szukamy naraz. Cztery z pięciu notek dziennie stoją na nich,
# a jedno szukanie kosztuje tyle co jedno — więc bierzemy zapas na kilka dni.
CURIOSITY_BATCH = 8
# Ile ostatnio zuzytych faktow pokazujemy szukajacemu jako zakaz powtorki.
# Bez tego to samo szukanie codziennie oddaje te same slynne osiem.
CURIOSITY_MEMORY = 60
COMMENT_CANDIDATES = 3

# Sufit dzienny. Research mówi, że trzy przemyślane komentarze tygodniowo biją
# piętnaście uprzejmych; pierwotne 15-20 dziennie było z planu sprzed danych.
NOTES_PER_DAY = 5
COMMENTS_PER_DAY = 4

# Typy notek. W dniu publikacji artykułu lecą notki typu ARTYKUL z linkiem;
# w pozostałe dni — pozostałe typy, oparte na fragmentach, których artykuły
# nie zużyły. Zmierzone: konwertują notki konkretne i taktyczne, a nie
# motywacyjne; komentarze i restacki niosą dalej niż polubienia, więc notka
# dająca się z czymś nie zgodzić bije notkę, pod którą wszyscy kiwają głową.
NOTE_TYPES = {
    "ARTYKUL": (
        "A fact from an article published today. State the fact so it stands on "
        "its own, then let the link do the rest. Do not summarise the article "
        "and do not tease it — the note has to be worth reading by someone who "
        "never clicks."
    ),
    "CIEKAWOSTKA": (
        "A single documented fact, surprising on its own, with no link and "
        "nothing to sell. The test: a reader who knows nothing about this "
        "publication stops scrolling and wants to know who found that out."
    ),
    "DYSKUSJA": (
        "A statement someone could reasonably disagree with, backed by a "
        "specific from the evidence. Not a question, and never a request for "
        "opinions — take a position and leave the obvious objection visible so "
        "a reader can pick it up. Comments carry more reach than likes."
    ),
    "SPROSTOWANIE": (
        "Name a thing widely believed, then the record that contradicts it. "
        "This is the house speciality: the gap between what people assume and "
        "what the document says. Do not mock the belief — explain why it is "
        "reasonable and where it goes wrong."
    ),
}

# Strefa czasowa publikacji. Liczy się strefa CZYTELNIKÓW, nie właściciela:
# konto jest anglojęzyczne, więc publiczność jest głównie amerykańska, a dane
# o godzinach pochodzą z czasu wschodnioamerykańskiego. Właściciel mieszka
# w Rumunii (EET/EEST), czyli najlepsze okno — niedziela 6:00 ET — wypada
# u niego w niedzielę o 13:00. Agent i tak chodzi z harmonogramu.
PUBLISH_TIMEZONE = "America/New_York"
BEST_NOTE_HOURS = (6, 7, 8)  # ET
WORST_NOTE_HOURS = (12, 13)  # ET, zwłaszcza w piątek
BEST_NOTE_DAYS = ("sunday", "saturday")
WORST_NOTE_DAYS = ("monday", "friday")

# Rozkład na tydzień: pięć notek dziennie, dzień publikacji artykułu ma własny.
NOTE_MIX_ARTICLE_DAY = ("ARTYKUL", "ARTYKUL", "CIEKAWOSTKA", "DYSKUSJA", "SPROSTOWANIE")
NOTE_MIX_OTHER_DAY = ("CIEKAWOSTKA", "CIEKAWOSTKA", "DYSKUSJA", "SPROSTOWANIE", "CIEKAWOSTKA")

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
