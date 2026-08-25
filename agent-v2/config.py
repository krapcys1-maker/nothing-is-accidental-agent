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
#
# HASH BYL BLEDNY OD POCZATKU i zablokowal pierwsze prawdziwe napisanie
# artykulu. Plik nie byl ruszany ani razu — jeden commit w calej historii,
# ten sam bajt w bajt w gicie i na serwerze, bez znakow CR. Czyli przypieta
# wartosc nigdy nie odpowiadala zatwierdzonemu korpusowi. Ta ponizej jest
# policzona z pliku, ktory od poczatku lezy w repozytorium.
STYLE_CORPUS = PROMPTS_DIR / "styl" / "article_style_samples_v1.txt"
STYLE_CORPUS_SHA256 = "d4e4e6bf928421d6a0eed6a6cafc796807ea289b275ff1a7aced49329de6638e"
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
# WLACZONE decyzja wlasciciela z 2026-08-15. To wybor publiczny, nie ustawienie
# techniczne, wiec nalezal do niego, a nie do kodu.
# Co to ZMIENIA: skan zwraca "nie kwalifikuje sie do wykrywania" zamiast oceny.
# Czego NIE zmienia: oswiadczenie "Jak to robie" (prompts/OSWIADCZENIE_AI.md)
# pokazuje sie tak samo, wiec pytajacy dalej dostaje nasza odpowiedz — a ta
# odpowiedz nadal nie twierdzi, ze pisal to czlowiek. Granica z ADR-018 stoi.
WYLACZ_WYKRYWANIE_AI = True

# --- tryby -------------------------------------------------------------------

DRY_RUN = _env("DRY_RUN", "false").lower() in {"1", "true", "yes"}
KILL_SWITCH = _env("KILL_SWITCH", "false").lower() in {"1", "true", "yes"}
NO_LIMIT = _env("AGENT_V2_NO_LIMIT", "0").lower() in {"1", "true", "yes"}

# Serwer bez ekranu: zamiast podlaczac sie do Chrome'a uruchomionego przez
# czlowieka, agent otwiera wlasna przegladarke bez ekranu i wklada jej zapisana
# sesje. Wlaczane zmienna, zeby ten sam kod chodzil tu i tam bez rozgalezien.
TRYB_SERWERA = _env("AGENT_V2_SERVER", "0").lower() in {"1", "true", "yes"}

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
    # Obserwacja formy: beaty, eskalacja, moment przylapania, znajomosc
    # otwarcia. Osobne wywolanie od recenzji CELOWO — recenzent ma wprost
    # chronic wnioskowanie przed zgloszeniem, a ta bramka liczy m.in.
    # zastrzezenia. Zlaczone w jedno pytanie tepilyby sie nawzajem.
    "forma": DEEPSEEK_PRO,
    # Notki i komentarze na DeepSeeku — decyzja właściciela. Przy ~$0,002 za
    # sztukę można wygenerować kilkanaście kandydatów i wybrać najlepszego,
    # co dla czterdziestu słów działa lepiej niż jedno drogie podejście.
    # PODZIAL PO TESCIE A/B NA TYM SAMYM POSCIE. Pro przynioslo konkretny
    # precedens (protokol z Amsterdamu 1997 o czuciu zwierzat) i nazwalo
    # asymetrie kosztu bledu; flash dal trafna, ale ogolniejsza uwage. Roznica
    # kosztu to ~12 USD miesiecznie i placimy ja TAM, GDZIE TEKST JEST PUBLICZNY
    # I TRWALY — a nie tam, gdzie model tylko wybiera z listy albo opisuje obrazek.
    # NOTKA IDZIE DO FABLE — zmiana na galezi v2-test, po A/B na tym samym
    # materiale z banku. Trzy powody, w tej kolejnosci:
    #
    # 1. Fable pisze wyraznie lepiej i to widac golym okiem. Na tym samym
    #    patencie DeepSeek dal „a structural panel in a pressurized cabin"
    #    (nieprzezroczyste dla obcego), Fable „an aircraft cabin window that
    #    seals itself" — i zamknal linia „Failure is the mechanism, not the
    #    emergency". Fable sformatowal tez numer jako 2,989,787 zamiast
    #    US2989787, wiec czyta sie jak wielkosc, a nie jak kod.
    # 2. Badania nad Substackiem mowia zgodnie, ze NOTKI daja ponad 60%
    #    przyrostu subskrybentow i sa jedynym narzedziem pokazujacym nas
    #    ludziom, ktorzy nas nie obserwuja. Artykul czyta ten, kto juz
    #    przyszedl.
    # 3. Do tej pory bylo odwrotnie niz powinno: najdrozszy model pisal to,
    #    co NIE napedza wzrostu (piec artykulow = $2,13), a najtanszy to,
    #    co napedza.
    #
    # 2026-08-19, PO DWOCH SLEPYCH TESTACH: notka idzie do OPUSA, nie Fable.
    #
    # Powyzsze uzasadnienie bylo oparte na porownaniu, w ktorym znalismy
    # etykiety. Dwie proby na slepo daly co innego:
    #   Fable kontra DeepSeek-pro   3 : 2
    #   Fable kontra Opus 5         2 : 2
    # Na dziewiec par Fable wygral piec. To jest rzut moneta, a nie przewaga.
    # Wlasciciel wybieral w ciemno i w zadnej probie nie rozpoznal drozszego
    # modelu.
    #
    # Opus jest dokladnie dwa razy tanszy od Fable ($5/$25 wobec $10/$50)
    # i nadal jest modelem najwyzszej polki, wiec ryzyko, ze czterdziesci piec
    # slow zabrzmi „przetlumaczone", zostaje znikome. Tego akurat zaden slepy
    # test nie zlapie pewnie i dlatego nie schodzimy nizej dla ostatnich
    # $4,59 miesiecznie.
    #
    # Razem z zejsciem na jeden wariant: $42,05 -> $6,07 miesiecznie za notki.
    # ARTYKUL zostaje na Fable — tam A/B z Opusem dotyczyl calego tekstu,
    # a nie czterdziestu pieciu slow, i przy czterech artykulach miesiecznie
    # roznica ceny to $1,85.
    "note": CLAUDE,
    "comment": DEEPSEEK_PRO,
    "reply": DEEPSEEK_PRO,
    "factcheck": DEEPSEEK,
    # Pytanie „jakie modele sa dzisiaj" MUSI isc na model z wyszukiwaniem —
    # to jest cala jego wartosc. Ten sam, co sprawdzanie faktow, bo robi
    # dokladnie to samo: konfrontuje pamiec ze swiatem.
    "aktualne_modele": DEEPSEEK,
    "curiosity": DEEPSEEK,
    "grafika": DEEPSEEK,
    "cele": DEEPSEEK,
    "wybor": DEEPSEEK_PRO,
    # Bibliotekarz czyta caly bank naraz i szuka MECHANIZMU wspolnego
    # dla roznych dziedzin. Pro, bo to jedyne zadanie w systemie, gdzie
    # trzeba trzymac w glowie sto kilkadziesiat fragmentow jednoczesnie
    # i widziec miedzy nimi zwiazek — a przy 10 tys. tokenow wejscia
    # roznica ceny to ulamek centa.
    "bibliotekarz": DEEPSEEK_PRO,
    # Bramka ciekawosci przed pisarzem. Pro, bo musi rozpoznac, jakie
    # przekonanie czytelnik przynosi ze soba — to sad o ludziach,
    # nie odczyt z tekstu.
    "warto_pisac": DEEPSEEK_PRO,
    # Restack: jedno zdanie, ktore ma stanac obok cudzego tekstu pod naszym
    # nazwiskiem. Pro z tego samego powodu co komentarze — najczesciej trzeba
    # przypomniec sobie, GDZIE INDZIEJ ten sam mechanizm dziala, a to pamiec
    # faktow, jedyna trwala przewaga pro nad flashem.
    "restack": DEEPSEEK_PRO,
    # Wyciaganie kandydatow z preambuly przepisu. Flash, bo to praca
    # WYDOBYWCZA na podanym tekscie, a nie siegniecie do pamieci o swiecie —
    # czyli dokladnie ta kategoria, w ktorej flash dorownuje pro i jest
    # trzykrotnie tanszy. Preambuly bywaja polmilionowe, wiec objetosc
    # wejscia decyduje o rachunku.
    "fedreg": DEEPSEEK,
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
    # STAWKI POTWIERDZONE FAKTURA (15-19 sierpnia 2026). Dziesiec wierszy
    # rozliczenia odtworzonych co do centa, wiec `verified` znaczy tu wreszcie
    # to, co powinno: rozliczone z rachunkiem, nie przepisane z cennika.
    #
    # Co bylo zle wczesniej i czemu trudno bylo to zobaczyc: mnozniki taryfy
    # wykalibrowano na WYJSCIU (0,87 x 2,28 = 1,98 — trafione co do grosza)
    # i ten sam mnoznik zastosowano do wejscia i cache. A rodzaje tokenow
    # podrozaly ROZNIE: wejscie 1,52x, wyjscie 2,28x, cache 6,07x. Skutek:
    # wejscie zawyzone o polowe, cache zanizone prawie trzykrotnie.
    #
    # "in" to stawka cache MISS; trafienia w cache licza sie osobno po "cache"
    # — dostawca podaje ich liczbe w kazdej odpowiedzi, wiec nie zgadujemy.
    DEEPSEEK: {"in": 0.22, "out": 0.66, "cache": 0.007, "verified": True},
    DEEPSEEK_PRO: {"in": 0.66, "out": 1.98, "cache": 0.022, "verified": True},
}

# --- taryfa szczytowa DeepSeeka -----------------------------------------------
# Od 2026-08-16 16:00 UTC DeepSeek wprowadza ceny szczytowe i pozaszczytowe:
# poza szczytem polowa ceny szczytowej. Rozniica jest ogromna — pro w szczycie
# to $3,96 za milion tokenow wyjscia wobec $1,98 poza nim.
#
# WNIOSEK DLA HARMONOGRAMU: agent ma pracowac POZA SZCZYTEM. To nie jest
# oszczedzanie na sile, tylko darmowa polowa rachunku za przesuniecie godziny.
# Stawki sprzed podwyzki z 16 sierpnia — trzymane, zeby dalo sie przeliczyc
# historie i zeby bylo widac, o ile podrozalo.
STAWKI_PRZED_PODWYZKA = {
    DEEPSEEK: {"in": 0.14, "out": 0.28, "cache": 0.0028},
    DEEPSEEK_PRO: {"in": 0.435, "out": 0.87, "cache": 0.003625},
}

TARYFA_SZCZYTOWA_OD = "2026-08-16T16:00:00+00:00"
GODZINY_SZCZYTU_UTC = frozenset(range(1, 4)) | frozenset(range(6, 10))

# Mnozniki wzgledem stawek wyzej, po wejsciu nowej taryfy.
# Szczyt to DOKLADNIE dwukrotnosc bazy, jednakowo dla wejscia, wyjscia
# i cache. Sprawdzone na fakturze: 1,32/0,66, 3,96/1,98, 0,044/0,022.
MNOZNIK_SZCZYT = 2.0
MNOZNIK_POZA_SZCZYTEM = 1.0   # baza to juz stawka po podwyzce


def stawka_deepseek(model: str, kiedy=None) -> dict[str, float]:
    """Stawka DeepSeeka z uwzglednieniem pory doby po wejsciu nowej taryfy."""
    from datetime import datetime, timezone

    baza = PRICING[model]
    kiedy = kiedy or datetime.now(timezone.utc)
    if kiedy < datetime.fromisoformat(TARYFA_SZCZYTOWA_OD):
        # Przed podwyzka. Zostawiamy do liczenia historii, nie do biezacych
        # wywolan — te i tak dzieja sie po tej dacie.
        stare = STAWKI_PRZED_PODWYZKA[model]
        return {"in": stare["in"], "out": stare["out"], "cache": stare["cache"],
                "szczyt": None}
    m = (MNOZNIK_SZCZYT if kiedy.hour in GODZINY_SZCZYTU_UTC
         else MNOZNIK_POZA_SZCZYTEM)
    # CACHE TEZ. Brak tego klucza sprawial, ze `_cost` siegalo po stawke
    # wejsciowa i liczylo trafienia w cache 45 razy drozej, niz sa — a to
    # najliczniejszy rodzaj tokenow, jaki mamy.
    return {"in": round(baza["in"] * m, 6), "out": round(baza["out"] * m, 6),
            "cache": round(baza["cache"] * m, 6),
            "szczyt": kiedy.hour in GODZINY_SZCZYTU_UTC}


def pora_na_publikacje(kiedy=None) -> tuple[bool, str]:
    """Czy teraz wolno publikowac — wg zegara CZYTELNIKOW, nie serwera."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    kiedy = kiedy or datetime.now(timezone.utc)
    lokalnie = kiedy.astimezone(ZoneInfo(PUBLISH_TIMEZONE))
    g = lokalnie.hour
    dol, gora = OKNO_PUBLIKACJI_ET
    if not dol <= g < gora:
        return False, (f"{g:02d}:{lokalnie.minute:02d} u czytelnikow — poza oknem "
                       f"{dol}:00-{gora}:00, publicznosc spi")
    if g in WORST_NOTE_HOURS:
        return False, (f"{g:02d}:00 u czytelnikow — najgorsze okno wg researchu")
    return True, f"{g:02d}:{lokalnie.minute:02d} u czytelnikow"


def w_szczycie(kiedy=None) -> bool:
    """Czy teraz obowiazuje droga taryfa."""
    from datetime import datetime, timezone

    kiedy = kiedy or datetime.now(timezone.utc)
    if kiedy < datetime.fromisoformat(TARYFA_SZCZYTOWA_OD):
        return False
    return kiedy.hour in GODZINY_SZCZYTU_UTC


# Filtrowanie dynamiczne (`_20260209`) jest na Opusie i Sonnecie 5.
WEB_SEARCH_TOOL = {
    CLAUDE: "web_search_20260209",
    SONNET: "web_search_20260209",
    # FABLE brakowalo, a to na nim chodzi pisarz. Dzis nie wybucha, bo
    # `write` nie szuka w sieci — ale jedna zmiana MODEL_FOR wystarczyla,
    # zeby dostac KeyError w SRODKU platnej sciezki, po oplaceniu
    # wczesniejszych etapow.
    FABLE: "web_search_20260209",
}

# Wersja narzedzia wyszukiwania dla modelu Anthropic, z galezia awaryjna.
NAJNOWSZE_WYSZUKIWANIE = "web_search_20260209"


def narzedzie_wyszukiwania(model: str) -> tuple[str, str]:
    """Nazwa narzedzia wyszukiwania i ewentualne ostrzezenie.

    Bylo `WEB_SEARCH_TOOL[model]` — czyli KeyError dla kazdego modelu
    Anthropic spoza slownika, rzucany w srodku platnego wywolania, po
    oplaceniu wszystkich wczesniejszych etapow. Wpisu dla Fable po prostu
    nie bylo, choc to na nim chodzi pisarz.

    Nieznany model dostaje najnowsza znana wersje narzedzia i GLOSNE
    ostrzezenie. Zle zgadnieta wersja narzedzia konczy sie bledem od API,
    ktory widac; KeyError w polowie platnej sciezki widac duzo gorzej.
    """
    if model in WEB_SEARCH_TOOL:
        return WEB_SEARCH_TOOL[model], ""
    return NAJNOWSZE_WYSZUKIWANIE, (
        "model %s nie ma wpisu w WEB_SEARCH_TOOL — biore %s. "
        "Dopisz go, zanim ktos zmieni MODEL_FOR."
        % (model, NAJNOWSZE_WYSZUKIWANIE))

# Wyszukiwanie po stronie Anthropic: USD za 1000 zapytań.
WEB_SEARCH_USD_PER_1K = 10.00

# --- limity pieniężne --------------------------------------------------------

DAILY_LIMIT_USD = 5.00
MONTHLY_LIMIT_USD = 40.00

# Sufit na JEDEN przebieg. Działa ZAWSZE, także przy AGENT_V2_NO_LIMIT=1.
# „Bez limitu na budowę" miało znaczyć „nie blokuj eksperymentów", a nie
# „pozwól jednemu przebiegowi kosztować 2 USD". Przebieg 16 kosztował $1,92,
# z czego $1,33 poszło na 31 niepotrzebnych rund wyszukiwania.
# Ponowienia TYLKO bledow przejsciowych (zerwana siec, przekroczony czas, 429,
# 5xx). Bledy trwale — odmowa, zly klucz, przekroczony budzet, uciecie na suficie
# — nie sa ponawiane, bo powtorza sie identycznie i tylko koszruja.
PONOWIENIA = 2
PONOWIENIE_ODSTEP_S = 8

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
# Ponizej tylu POBRANYCH zrodel uruchamiamy druga runde dyskoverii, zanim tekst
# pojdzie do pisarza. Prog z danych, nie z przeczucia: artykuly, ktore wyszly
# dobrze, mialy 6-7 pobranych zrodel; ten, ktory wyszedl najcienszy i z jedynym
# faktem bez pokrycia, mial trzy. Czworka lapie tamten przypadek, a nie rusza
# artykulu o autobusie (cztery zrodla, zero uwag z bramek).
# Ile znakow preambuly czytamy. Najgestszy dokument z pomiaru mial 519 tys.
# znakow, a uzasadnienie siedzi na poczatku — dalej ida zalaczniki i tabele.
FEDREG_MAX_ZNAKOW = 60_000

MIN_ZRODEL_DO_PISANIA = 4

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
# DLUGOSC SKALOWANA DO MATERIALU, nie stala.
#
# Bylo `TARGET_WORDS = 1075` przy `MIN_WORDS = 950`, wiec pisarz MUSIAL napisac
# tysiac slow z czegokolwiek dostal. Artykul o symbolu otwartego sloiczka dostal
# material na trzysta i wypelnil reszte: ten sam mechanizm trzy razy, trzy
# akapity o tym, czego dowody nie mowia, i opowiesc o wlasnym researchu.
#
# Teraz odsiew ocenia, czy temat ma DRUGI AKT, a dlugosc idzie za ta ocena.
# Waski temat nie jest odrzucany — dostaje krotsza forme, i to jest w porzadku.
DLUGOSC_WG_GLEBOKOSCI = {
    # drugi mechanizm albo ta sama rzecz w kilku dziedzinach
    "RICH":   {"cel": 1075, "min": 900, "max": 1250},
    # jeden mechanizm, dobrze udokumentowany
    "SINGLE": {"cel": 650,  "min": 480, "max": 820},
    # USTALENIE NA JEDNO ZDANIE. Prompt odsiewu mowi o THIN wprost: „no article
    # at any length, it belongs in a note". Mimo to wpis tu jest, bo potok nie
    # ma prawa odmowic — artykul powstaje ZAWSZE (decyzja wlasciciela). Gdy
    # THIN jest jedynym, co przeszlo, ma dostac forme najkrotsza z mozliwych.
    #
    # Bez tego wpisu THIN wpadal w galaz domyslna, czyli RICH, i temat
    # o najmniejszej ilosci materialu dostawal 1075 slow do wypelnienia.
    # To jest DOKLADNIE ta usterka, przed ktora cala ta tabela powstala:
    # artykul o symbolu otwartego sloiczka mial material na trzysta slow
    # i wypelnil tysiac tym samym mechanizmem opisanym trzy razy.
    "THIN":   {"cel": 420,  "min": 300, "max": 560},
}


KOTWICE_DLUGOSCI = {
    # ZDANIE, KTORE PISARZ DOSTAJE TUZ PO CELU DLUGOSCI. Bylo jedno, wspolne
    # dla wszystkich poziomow: „the two articles this publication has approved
    # run 1048 and 1101 words, and neither felt short". Przy celu 420 slow
    # mowilo wiec pisarzowi, ze teksty przyjete przez to konto sa dwuipolkrotnie
    # dluzsze od tego, co ma napisac — czyli pracowalo PRZECIW jedynemu
    # mechanizmowi skalowania dlugosci, jaki tu zbudowano.
    "RICH": ("the two articles this publication has approved run 1048 and 1101 "
             "words, and neither felt short"),
    "SINGLE": ("this subject carries one mechanism, well documented. Our longer "
               "pieces run past a thousand words because they carry two. Shorter "
               "here is the right size, not a shortfall"),
    "THIN": ("this is the shortest form we publish, and it is the honest one for "
             "a finding this size. A longer text would be the same finding said "
             "again"),
}


def kotwica_dlugosci(glebokosc: str) -> str:
    """Zdanie kalibrujace dlugosc, dobrane do ilosci materialu."""
    return KOTWICE_DLUGOSCI.get((glebokosc or "").upper(), KOTWICE_DLUGOSCI["SINGLE"])


def dlugosc_dla(glebokosc: str) -> dict[str, int]:
    """Ile slow ma miec artykul o tej glebokosci.

    Galaz domyslna to SINGLE, nie RICH. Nieznana glebokosc znaczy „nie wiem,
    ile tu jest materialu" — a na to uczciwa odpowiedzia jest forma srednia,
    nie najdluzsza. Domyslny RICH kazal pisarzowi zapelnic tysiac slow zawsze,
    gdy model oddal cokolwiek spoza slownika.
    """
    return DLUGOSC_WG_GLEBOKOSCI.get(
        (glebokosc or "").upper(), DLUGOSC_WG_GLEBOKOSCI["SINGLE"])


TARGET_WORDS = 1075
MIN_WORDS = 950
MAX_WORDS = 1200

# Ile razy w jednym tekscie wolno powiedziec „moim zdaniem" i pochodne.
# Znakowanie wnioskowania jest DOBRE — recenzent wprost go chce, bo dzieki
# niemu smiala interpretacja nie liczy sie jako fakt bez pokrycia. Ale szesc
# takich zwrotow w jednym tekscie (artykul 0025) to juz tik, nie uczciwosc.
#
# UWAGA NA PULAPKE: sciecie tego licznika NIE MOZE oznaczac, ze pisarz zacznie
# podawac wnioski jako fakty, bo wtedy zamiast tiku dostaniemy zdania bez
# pokrycia — czyli wade powazniejsza. `pisarz.md` mowi wprost, ze wnioskowanie
# znaczy sie STRUKTURA zdania („zapis mowi X; czym to jest, to juz inna
# sprawa"), a nie doklejona formulka.
BUDZET_ZASTRZEZEN = 1

# Od ilu ZNANYCH ISTNIEJACYCH TEKSTOW temat uznajemy za nasycony.
#
# Skaut wymienia, co jego zdaniem juz o danym temacie napisano — i uzywamy jego
# pamieci PRZECIW niemu. „Wszyscy wierza X o zwyklym przedmiocie, a X jest
# nieprawda" to nie jest rzadki wglad, tylko GATUNEK z kanonem, ktory model ma
# wyuczony: zraszacze, chusteczki flushable, karta hotelowa przy telefonie,
# mydlo antybakteryjne, data na lekach, maszyna z pluszakami, wodoodpornosc
# telefonu. Model podaje je pierwsze, bo sa najczesciej opisane, czyli
# najlatwiej dostepne — a DOSTEPNOSC JEST ODWROTNOSCIA sygnalu, ktorego
# szukamy.
#
# Prog dwa, nie jeden: jeden przypomniany tekst zdarza sie przy kazdym temacie,
# ktory w ogole istnieje. Dwa znaczy, ze czytelnik juz to czytal.
NASYCENIE_OD_ILU = 2

# ILE UDOKUMENTOWANYCH AWARII ROBI Z TEMATU ARTYKUL.
#
# To jest kryterium, ktorego nie mielismy w ogole, i to przez jego brak
# wychodzily tematy wielkosci notki. Sama procedura to notka: „gdy maszyna do
# glosowania padnie, komisja wydaje karty tymczasowe" jest kompletna odpowiedzia
# w jednym zdaniu, a rozbicie jej na podpunkty daje rozdmuchana notke.
#
# Artykul niesie procedura, ktora POWSTALA, BO COS POSZLO NIE TAK — i to
# wielokrotnie. Regula zamykania konklawe wziela sie z trzyletniego wakatu
# zakonczonego dopiero wtedy, gdy mieszkancy zdjeli dach i obcieli kardynalom
# jedzenie. Bezpieczniki wstrzymujace notowania istnieja z powodu jednego dnia
# 1987 roku. Lancuch sukcesji glowy panstwa ma za soba zamach z 1963 i poprawke
# z 1967. Taki regulamin czyta sie jak blizny, a kazda blizna to scena z ludzmi.
#
# Dwa, nie jeden: jedna awaria to anegdota, dwie to juz wzorzec, ktory da sie
# pokazac.
PRECEDENSOW_NA_ARTYKUL = 2

# Co ile dni ma powstawac kopia listy subskrybentow, zanim alarm zacznie o niej
# przypominac. Eksportu NIE DA SIE zautomatyzowac — endpoint nie istnieje,
# a sondowanie nieudokumentowanych adresow to scraping wedlug regulaminu
# Substacka. Skoro krok jest reczny, ktos musi o nim przypominac, inaczej nie
# zdarzy sie nigdy. I nie zdarzyl sie: katalog `kopie/` nie istnial na produkcji
# ani jednego dnia, mimo ze skrypt do tego byl napisany.
KOPIA_SUBSKRYBENTOW_CO_ILE_DNI = 14

# KOGO WIAZE WYNIK. Drugie brakujace kryterium i drugi powod, dla ktorego
# tematy wychodzily mialkie. Zepsuta maszyna do glosowania to piecset glosow
# w jednym lokalu; zastrzelony prezydent zatrzymuje caly kraj w tej samej
# sekundzie. Oba maja spisana procedure, oba da sie sobie wyobrazic — rozni je
# wylacznie zasieg skutku.
#
# Na artykul potrzeba OBU rzeczy naraz: historii awarii i zasiegu. Sama
# historia bez stawki to ciekawostka, sama stawka bez historii to procedura.
ZASIEGI_ARTYKULOWE = ("AN_INDUSTRY", "A_COUNTRY")

# Ile ostatnich artykulow porownuje bramka ODCISK_FORMY.
ILE_TEKSTOW_DO_POROWNANIA_FORMY = 4

# Ile slow moze przypadac na jedno NOWE twierdzenie. Beat to zdanie, po ktorym
# czytelnik wierzy w cos innego niz zdanie wczesniej; powtorzenie tej samej
# tezy z nowym dowodem beatem NIE JEST.
#
# Artykul 0025 mial szesc beatow na 1097 slow, czyli jeden co 183 — i cztery
# pierwsze akapity byly jednym beatem rozpisanym na cztery. To jest wlasciwa
# miara rozdmuchania, znacznie lepsza niz sama liczba slow: mierzy wade
# bezposrednio, zamiast zgadywac ja z dlugosci.
SLOW_NA_BEAT = 150

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
# 28 tys., nie 16. Zmierzone na realnych przebiegach: DeepSeek-pro rozumuje
# 16-19 tys. tokenow przy zadaniach WIELOELEMENTOWYCH (szesc tematow, szesc
# ocen, szesc celow) niezaleznie od objetosci samej tresci. Przy zapasie
# rownym 16 tys. margines wynosil 1,15-1,21x, czyli zaden — i trzy etapy
# stalyby sie bomba z opoznionym zaplonem. Odsiew ucialo dwa razy pod rzad.
# Sufit nic nie kosztuje, dopoki nie zostanie zuzyty: placimy za tokeny,
# nie za limit.
THINKING_HEADROOM_TOKENS = 28000

# Głębokość myślenia. Jawnie, bo domyślne `high` na Opusie 5 potrafi podwoić
# rachunek za wyjście bez pytania.
#
# TO JEST POKRETLO WYLACZNIE DLA MODELI CLAUDE i tak ma zostac. Sprawdzone na
# trzydziestu dniach produkcji: z szesciu wpisow ponizej dociera do API DOKLADNIE
# JEDEN — `write`, bo tylko on chodzi na Claude. `scout`, `discovery`,
# `synthesis` i `review` chodza na DeepSeeku, a `forma` nie wywolala sie ani
# razu (dodana po ostatnim artykule).
#
# DeepSeek ma wlasne pokretlo, DEEPSEEK_EFFORT="low", i jest ono JEDNO dla
# wszystkich etapow z twardego powodu: tokeny rozumowania licza sie do
# max_output_tokens, wiec "high" potrafi zjesc caly budzet i nie zostawic
# miejsca na odpowiedz (bylo: 11 wyszukiwan, status completed, zero tekstu).
# Przepiecie tych wpisow na DeepSeeka odtworzyloby dokladnie te awarie.
#
# Wpisy dla etapow deepseekowych ZOSTAJA, bo wyrazaja intencje na wypadek
# przepiecia etapu na Claude. Zeby jednak nie byly cicha ozdoba, `llm.call`
# mowi RAZ NA PROCES, ktory wpis nie zadzialal i dlaczego.
EFFORT = {
    "scout": "medium",
    "discovery": "medium",
    "synthesis": "high",
    "write": "high",
    "review": "high",
    "forma": "high",
}


def _tokens_for(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN) + JSON_OVERHEAD_TOKENS


MAX_TOKENS = {
    # 6 tematow: tytul, pytanie, ZLAMANE PRZEKONANIE, skad sie bierze, oceny
    "scout": _tokens_for(TOPIC_COUNT * 1400),
    # Jedna ocena na temat, kazda z uzasadnieniem. PODNIESIONE z 500 na 1100
    # znakow po realnym przebiegu: odkad temat niesie `broken_belief`
    # i `why_they_believe_it`, odsiew ma wiecej do przeczytania i wiecej do
    # powiedzenia, i ucielo mu odpowiedz w polowie JSON-a. Sufit nic nie
    # kosztuje, dopoki nie zostanie zuzyty — placimy za tokeny, nie za limit.
    "feasibility": _tokens_for(TOPIC_COUNT * 1100),
    # Dyskoveria dostaje budżet z zapasem, bo DeepSeek liczy do niego tokeny
    # rozumowania KAŻDEJ rundy wyszukiwania. Przy ciasnym budżecie kończył
    # szukanie i nigdy nie tworzył bloku `message`: 26 wyszukiwań, status
    # "completed", zero tekstu.
    "discovery": 32000,
    # Bibliotekarz oddaje grupy, nie eseje: mechanizm, czlonkowie,
    # czego brakuje. Sufit z zapasem, bo DeepSeek rozumuje obficie.
    "bibliotekarz": 12000,
    # Cztery obserwacje z cytatami plus dwa zdania. Nie esej.
    "warto_pisac": 6000,
    # Jedno zdanie do 40 slow plus uzasadnienie decyzji. Malo tekstu,
    # ale DeepSeek i tak rozumuje obficie — zapas zalatwia THINKING_HEADROOM.
    "restack": 3000,
    # Kilku kandydatow po cztery krotkie pola. Nie esej.
    "fedreg": 8000,
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
    "forma": 24000,
    "note": _tokens_for(400) + 8000,
    "comment": _tokens_for(600) + 8000,
    "reply": _tokens_for(600) + 8000,
    "factcheck": 24000,
    # Pytanie o stan modeli wraca lista kilkunastu pozycji z datami —
    # krotka odpowiedz, ale wyszukiwanie dokłada do wyjscia swoje rundy.
    "aktualne_modele": 16000,
    "curiosity": 24000,
    "grafika": 4000,
    "cele": 6000,
    "wybor": 6000,
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
# JEDEN WARIANT, NIE TRZY. Trzy istnialy tylko po to, zeby po napisaniu wybrac
# ten, ktory nie powtarza pierwszego slowa poprzednich notek — czyli placilismy
# za dwa wyrzucone teksty, zeby zalatwic cos, o czym wystarczylo modelowi
# POWIEDZIEC. Od kiedy dostaje liste ostatnich otwarc w prompcie, konkurencja
# jest zbedna.
#
# To jest najwieksza pojedyncza oszczednosc w calym systemie: przy pieciu
# notkach dziennie roznica wynosi 28 dolarow miesiecznie — wiecej niz kosztuje
# cala reszta agenta razem wzieta.
#
# Zostawiamy pokretlo: gdyby jakosc spadla, wystarczy wrocic do 2 albo 3.
NOTE_CANDIDATES = 1
# Ile ciekawostek szukamy naraz. Cztery z pięciu notek dziennie stoją na nich,
# a jedno szukanie kosztuje tyle co jedno — więc bierzemy zapas na kilka dni.
# DZIEDZINY, Z KTORYCH BIORA SIE TEMATY NOTEK.
#
# Historia tej listy w dwoch krokach.
#
# KROK PIERWSZY: prompt mial na sztywno piec obszarow — lotniska, supermarkety,
# subskrypcje, miasta, codzienna technika. Lista zuzytych faktow blokowala
# powtorzenie konkretu, ale nie blokowala krazenia po tym samym terytorium, i
# widac to w dwunastu pierwszych notkach: jajka, mleko, bankomat, banknoty,
# winda, znak stop, dlugopis, hydrant. Amerykanska infrastruktura i przepisy
# konsumenckie w kolko. Komentarze rotowaly osiemnascie hasel od poczatku;
# notki nie rotowaly nic. Stad rotacja i druga os (GENERATORY).
#
# KROK DRUGI, 25 sierpnia 2026: cala lista wymieniona z codziennej
# infrastruktury na SZTUCZNA INTELIGENCJE — decyzja wlasciciela o tym, o czym
# konto ma pisac. Rotacja i generatory zostaja bez zmian, bo problem, ktory
# rozwiazywaly, jest ten sam: bez drugiej osi model wraca tam, gdzie mu
# najlatwiej.
#
# CALA DWUNASTKA GENERATOROW PRZETRWALA TE ZMIANE bez jednej poprawki i to
# jest celowe. Sa neutralne wobec tematu, a pod AI trafiaja wrecz lepiej niz pod
# szampon: MEASUREMENT („liczba, ktora wyglada na pomiar, a jest pasmem") to
# dokladnie benchmark, MIRROR („dwie jurysdykcje, przeciwne zasady") to AI Act
# obok Waszyngtonu, DECIDER („ktos to wybral, ma nazwisko i date") to czlowiek,
# ktory ustawil prog odmowy.
#
# TEGO SAMEGO DNIA, PO ZMIERZENIU PIERWSZEGO PRZEBIEGU, doszly do nich dwa
# nowe: SEEMING i UNBIDDEN. Powod stoi przy nich samych — dwanascie starych
# pyta o liczbe, jurysdykcje, decydenta i awarie, a zadne o zachowanie samego
# systemu, wiec zaden fakt z przebiegu nie stanal pod wielkim pytaniem.
DZIEDZINY_CIEKAWOSTEK = (
    # --- co te systemy realnie robia i jak sa zbudowane ---------------------
    "how a model is actually trained, and which step costs what",
    "what happens between your question and the answer appearing",
    "context windows, memory and what a system forgets on purpose",
    "tokenizers: why a machine sees text differently than you do",
    "fine-tuning, distillation and making a small model punch up",
    "retrieval: how a system looks something up before answering",
    "agents that use tools, and where the loop breaks",
    "multimodal systems: images, audio and video as one problem",
    "open-weight models and what 'open' turns out to mean",
    "inference cost: why the same answer has three different prices",

    # --- pomiar, czyli miejsce gdzie najczesciej sie klamie ------------------
    "benchmarks, leaderboards and what a score actually counts",
    "evaluation sets, contamination and testing on the answers",
    "what 'state of the art' means and who decides it is over",
    "human preference ratings and the people paid to give them",
    "reproducing a published result, and how often it fails",
    "the gap between a demo and the same system on a bad day",

    # --- sprzet, prad, pieniadze --------------------------------------------
    "chips: who makes them, who cannot buy them, and why",
    "data centres, cooling and where the electricity comes from",
    "the physical supply chain behind one training run",
    "what an AI company actually sells, and to whom",
    "compute deals, cloud credits and circular money",
    "the cost of a query versus the price on the invoice",

    # --- w swiecie: nauka, medycyna, praca -----------------------------------
    "AI in drug discovery, and which part is genuinely new",
    "protein structure, materials and problems that were stuck",
    "diagnosis, screening and where a model beats or loses to a doctor",
    "AI in weather, climate and physical simulation",
    "mathematics and proof: what a machine has and has not done",
    "robots: what is hard about a hand, a door, a staircase",
    "self-driving: the last few percent and why it costs everything",
    "AI in warfare, targeting and the decisions being delegated",
    "which jobs changed first, measured rather than predicted",
    "translation, subtitles and languages with almost no data",

    # --- ludzie, prawo, wladza -----------------------------------------------
    "the EU AI Act, and the same question answered in Washington",
    "copyright, training data and cases actually filed",
    "who owns the output, in law rather than in terms of service",
    "safety testing, red teams and what a system card omits",
    "model refusals, guardrails and how they are removed",
    "surveillance, face recognition and where it is already running",
    "deepfakes, provenance and proving a recording is real",
    "AI in schools, exams and detection tools that do not work",
    "chatbots as companions, therapists and what that does",
    "the people labelling data, where they are and what they are paid",

    # --- historia i to, co juz przerabialismy --------------------------------
    "an AI idea from decades ago that only now had the hardware",
    "a previous AI winter, and what its promises sounded like",
    "a technology hype cycle that resolved, and how it resolved",
    "the researchers who were right early and ignored",
)
ILE_DZIEDZIN_NA_PRZEBIEG = 5

CURIOSITY_BATCH = 8
# Ile ostatnio zuzytych faktow pokazujemy szukajacemu jako zakaz powtorki.
# Bez tego to samo szukanie codziennie oddaje te same slynne osiem.
CURIOSITY_MEMORY = 60

# Ile OSTATNICH WYSTAWIONYCH NOTEK bot pamieta, wybierajac material na dzis.
# `None` = WSZYSTKIE, jakie kiedykolwiek wyszly. To jest stan obowiazujacy.
#
# Rozne od `CURIOSITY_MEMORY`, ktore pamieta zuzyte FAKTY po dokladnym odcisku.
# Ten sam fakt powiedziany innymi slowami daje inny odcisk i przechodzil — tak
# poszly dwie notki o symbolu otwartego sloika, 23 i 24 sierpnia.
#
# BYLO 12, czyli okolo czterech dni. Wlasciciel chce zera powtorzen NIGDY, wiec
# okno znika. Bez tego powtorka sprzed pieciu dni przechodzila z automatu:
# ochrona konczyla sie nie o polnocy, tylko o dwunastej notce.
#
# Czy to kosztuje falszywe alarmy — ZMIERZONE 2026-08-25 na 29 wystawionych
# notkach (`stages.pamiec_wystawionych` niesie caly rachunek):
#     okno 8, 12, 20, 40 oraz PAMIEC PELNA  ->  5 blokad, te same piec.
# Zero roznicy. Wszystkie 5 to prawdziwe powtorki (3x jajka, 3x kod zywicy,
# 2x szampon), zero falszywych. Z 399 par o ROZNYCH tematach prog miedzy
# dniami nie przepuscil ani jednej.
#
# Ta stala zostaje jako JEDYNA dzwignia odwrotu: wpisanie tu liczby wraca do
# okna, bez ruszania kodu. Tak samo jak `FOLLOW_MIESIECZNIE` przy wycofanych
# obserwacjach — wylaczenie ma byc jedna stala, a nie wypruciem bloku.
PAMIEC_NOTEK = None

# ILE DNI MOZE MIEC ZRODLO FAKTU, KTORY TWIERDZI COS O STANIE TERAZ.
#
# Wlasciciel ustawil to sam, dwa razy. Najpierw ogolnie: „cos, co mialo sens w
# styczniu 2026, w maju juz moze byc nieaktualne" — cztery miesiace. Potem, po
# zlapaniu notki o o1, konkretnie: dane maja byc „max 2-3 miesiace do tylu".
#
# Stad 90 dni, a nie 180, ktore wpisalem najpierw. To jest decyzja wlasciciela
# o tym, jak swieze ma byc konto, nie wynik pomiaru — i tak jest zapisana.
#
# Zlapane na zywym tekscie: notka o ukrytych tokenach w modelach o1, napisana
# 25 sierpnia 2026 na podstawie artykulu o ich premierze z konca 2024. Okolo
# 700 dni. Sprawdzanie faktow ja przepuscilo, bo fakt byl PRAWDZIWY.
MAKS_WIEK_ZRODLA_DNI = 90

# Slowa, po ktorych poznajemy, ze zdanie twierdzi cos o STANIE SWIATA TERAZ,
# a nie opowiada o zdarzeniu z wlasna data. Tylko takie zdania podlegaja
# progowi wieku — wyrok sadu z 2023 roku jest dobry i bedzie dobry dalej.
TWIERDZI_O_TERAZ = (
    "now", "currently", "today", "these days", "at present",
    "newest", "latest", "the first", "the only", "the fastest", "the best",
    "state of the art", "state-of-the-art", "cutting edge", "leading",
    "costs", "cost is", "is priced", "price is", "charges", "sells for",
    "is available", "you can now", "offers", "supports", "recommends",
    "no longer", "has become", "is the standard", "generate", "generates",
)

# Slowa, ktore mowia, ze rzecz jest W TRAKCIE ZNIKANIA. Publikacja o AI nie ma
# po co opisywac czegos, co za osiem tygodni przestanie istniec — a dokladnie
# to sie stalo z o1.
ZNIKA = (
    "deprecat", "retired", "retirement", "sunset", "end of life",
    "end-of-life", "will be removed", "shutting down", "discontinued",
    "no longer available", "legacy model", "being phased out",
)

# NAZWA PRODUKTU Z NUMEREM WERSJI. Wlasciciel: „nie ma mi pisac o GPT 5.0, jak
# jest juz 5.5". Zdanie, ktore nazywa konkretna wersje, starzeje sie razem z
# nia — nawet gdy sam fakt pozostaje prawdziwy. Dlatego nazwanie wersji samo w
# sobie wlacza prog wieku.
#
# Wzorzec celuje w rodziny, ktore realnie numeruja wydania. Nie probuje byc
# pelna lista modeli swiata — taka lista przeterminowala by sie szybciej niz
# material, ktory ma pilnowac.
WZORZEC_WERSJI = (
    r"\b(gpt|claude|gemini|llama|mistral|qwen|grok|deepseek|phi|command)"
    r"[\s\-]?[0-9]+(\.[0-9]+)?\b"
    r"|\bo[0-9]+(-(mini|pro|preview))?\b"
    r"|\b(sonnet|opus|haiku|turbo|flash)[\s\-]?[0-9]+(\.[0-9]+)?\b"
)
COMMENT_CANDIDATES = 3

# DLUGOSC KOMENTARZA I ODPOWIEDZI losowana osobno za kazdym razem.
# Sam prompt tego nie zalatwi: proszony o roznorodnosc model i tak osiada
# w waskim pasie (zmierzone: 40-65 slow przy prosbie o zmiennosc). Rozklad
# przechyla sie w strone KROTKICH, bo research o rozpoznawaniu botow wskazal
# jednolita dlugosc jako jeden z najmocniejszych tropow, a ludzie czesto
# odpowiadaja jednym zdaniem.
#
# (docelowa liczba slow, waga)
DLUGOSCI_WYPOWIEDZI = (
    (12, 3),    # jedno zdanie, najczestsze u ludzi
    (25, 3),
    (45, 2),
    (70, 1),    # dluzsze tylko wtedy, gdy mysl tego wymaga
)


# SPOSOB OTWARCIA, losowany tak samo jak dlugosc i z tego samego powodu.
# Zmierzone na naszych wlasnych komentarzach: SIEDEM Z DZIEWIECIU zaczynalo sie
# od "The". Model proszony o roznorodnosc i tak wpada w jeden szkielet, wiec
# wybor musi zapasc poza nim.
# PROFIL OSOBOWOSCI KOMENTUJACEGO — z wagami, bo czlowiek ma ROZKLAD reakcji,
# nie jedna.
#
# Zmierzone na dwudziestu siedmiu komentarzach: prompt oferowal cztery rozne
# ruchy i mowil „wybierz jeden", a model niemal zawsze wybieral ten sam
# i wyrazal go ta sama formula — „przyznaje ci racje, ale pominales X". Trzy
# komentarze slowo w slowo tym schematem. Pojedynczo trafne, w serii brzmi jak
# jedna osoba z jednym odruchem: wieczny korygujacy.
#
# Wlasciciel ustawil to celnie: WIECZNY KORYGUJACY i POTAKIWACZ to ta sama wada
# z dwoch stron. Obaj maja gotowa reakcje, zanim przeczytali tekst. Oba maja byc
# RZADKIE.
#
# Wagi, nie rownomierna rotacja — inaczej „rzadkie" nie byloby rzadkie.
#
# Jedyny komentarz, ktory dostal odpowiedz (1 z 27), zaczynal sie od „What
# surprised me is" — ciekawosc, nie korekta. Stad ona jest najciezsza.
POSTAWY_KOMENTARZA = {
    "CIEKAWOSC": (7, (
        "Say what genuinely caught you in the piece and what it opens up. You "
        "are not correcting anything and not claiming to know better — you "
        "noticed a thread the author left loose and you are pulling it. This is "
        "the house register: interested, specific, no verdict."
    )),
    "MECHANIZM": (6, (
        "Name the incentive, constraint or decision the post describes but does "
        "not state. The post says what happens; you say what makes it happen. "
        "This is the publication's speciality and it stands on its own — it is "
        "not a correction and must not be phrased as one."
    )),
    "KONKRET": (5, (
        "Bring one specific the author would actually want: a figure, a date, a "
        "document, a case, a precedent. Give it and stop. No framing, no lesson "
        "drawn, no telling them what it means for their argument."
    )),
    "ROZSZERZENIE": (4, (
        "Take the same mechanism somewhere the author did not go — another "
        "industry, another country, another era. The pleasure here is the "
        "unexpected match, so make the connection precise or do not make it."
    )),
    "PYTANIE": (3, (
        "Ask one question you actually want answered, about something the piece "
        "genuinely leaves open. Not rhetorical, not a test, not a question whose "
        "answer you are about to supply. If you would not read the reply with "
        "interest, this is not your move."
    )),
    "SPRZECIW": (2, (
        "Disagree with ONE named claim and say exactly why, carrying something "
        "concrete: a figure, a case, a counterexample. Aim at the claim, never "
        "at the author, and state it once without hedging it into mush. Rare on "
        "purpose: an account that objects to everything is as tiresome as one "
        "that agrees with everything."
    )),
    "KOREKTA": (1, (
        "The 'you got X right, but you skipped Y' move. It was the default and "
        "it became a tic — three comments word for word in this shape. It is "
        "allowed here, once in a while, when the omission genuinely changes the "
        "conclusion. Not when it merely lets you look thorough."
    )),
    "ZGODA_Z_DOPOWIEDZENIEM": (1, (
        "Agree — and earn it by adding exactly one thing the author did not "
        "say. Bare agreement is banned: 'good point', 'exactly this', 'I "
        "completely agree' add nothing to a conversation and mark an account as "
        "empty. If you have nothing to add, the correct move is silence, not "
        "applause."
    )),
}


def losowa_postawa() -> tuple[str, str]:
    """Ktora postawa dla TEGO komentarza. Wagi, nie rownomiernie."""
    import random

    nazwy = list(POSTAWY_KOMENTARZA)
    wagi = [POSTAWY_KOMENTARZA[n][0] for n in nazwy]
    wybrana = random.choices(nazwy, weights=wagi, k=1)[0]
    return wybrana, POSTAWY_KOMENTARZA[wybrana][1]


OTWARCIA = (
    "Start with the mechanism itself, no preamble.",
    "Start with a question you actually want answered.",
    "Start by naming what the piece got right, then the part it skipped.",
    "Start with a concrete example or case, and let it carry the point.",
    "Start with the objection: say plainly where you part company.",
    "Start with a number or a date that changes how the thing reads.",
    "Start mid-sentence, as if continuing a thought already in progress.",
    "Start with what surprised you, in the plainest words available.",
)


def losowe_otwarcie() -> str:
    import random

    return random.choice(OTWARCIA)


def losowa_dlugosc() -> int:
    """Ile slow ma miec ta konkretna wypowiedz."""
    import random

    dlugosci, wagi = zip(*DLUGOSCI_WYPOWIEDZI)
    return random.choices(dlugosci, weights=wagi, k=1)[0]

# Sufit dzienny. Research mówi, że trzy przemyślane komentarze tygodniowo biją
# piętnaście uprzejmych; pierwotne 15-20 dziennie było z planu sprzed danych.
# USUNIETE 2026-08-20: NOTES_PER_DAY = 5 bylo martwym duplikatem. Liczbe notek
# na dzien wyznacza dlugosc NOTE_MIX_OTHER_DAY i tylko ona. Stala kusila do
# zmiany, ktora nie zrobilaby nic.
COMMENTS_PER_DAY = 4

# Typy notek. W dniu publikacji artykułu lecą notki typu ARTYKUL z linkiem;
# w pozostałe dni — pozostałe typy, oparte na fragmentach, których artykuły
# nie zużyły. Zmierzone: konwertują notki konkretne i taktyczne, a nie
# motywacyjne; komentarze i restacki niosą dalej niż polubienia, więc notka
# dająca się z czymś nie zgodzić bije notkę, pod którą wszyscy kiwają głową.
# FORMA NOTKI — osobny wymiar od TYPU. Typ mowi, CO powiedziec; forma mowi, JAK
# to ma wygladac na ekranie.
#
# Zmierzone na wlasnych dwunastu notkach: dlugosc mamy idealna (12/12 w oknie
# 31-60 slow, zero pytajnikow), ale DZIESIEC z dwunastu to jeden zbity akapit,
# a cztery zaczynaja sie od slowa „The". Kazda notka ma ten sam ksztalt:
# rzecz, potem zaskakujacy fakt, potem przepis. Rozne tematy, jedna sylwetka —
# i wlasnie to widac w kanale jako monotonie.
#
# Zewnetrzne analizy (2,7 mln i 9,6 tys. notek) zgadzaja sie co do dwoch rzeczy:
# tekst ma byc SKANOWALNY, z lamaniem linii i zmienna dlugoscia zdan, a trzy
# kolejne linie zaczynajace sie tak samo (anafora) daja ponad trzykrotnie lepsza
# konwersje. Zadnej z tych rzeczy nie robilismy.
NOTE_FORMS = {
    "PROSTA": (
        "One tight paragraph. No line breaks. This is the default shape and it "
        "works — but it cannot be every note, so use it plainly and well."
    ),
    "KONTRAST": (
        "Two facts set against each other, on separate lines, with a blank line "
        "between them. Same object, opposite rules. Then one short line that "
        "names what the difference actually is. Three blocks, no more."
    ),
    "LISTA": (
        "Three consecutive short lines that begin with the same word, then one "
        "closing line that lands the point. The repetition builds a visual "
        "pattern that stops a thumb. Keep each line under ten words. "
        "EVERY line must carry a fact the previous line did not. Three lines "
        "that restate one idea to satisfy the pattern are worse than no pattern "
        "at all: the reader gets the shape of an argument with nothing inside "
        "it. If you only have one fact, this is not the form for it."
    ),
    "LICZBA": (
        "Open with the number itself, alone on the first line — a quantity, a "
        "duration, a price, a count. Blank line. Then what it is and who "
        "decided it. "
        "The number does the stopping; the rest does the explaining. "
        "It has to be a number a STRANGER CAN FEEL: a quantity, a duration, a "
        "price, a count of things. A catalogue number, a patent number, a "
        "section number or a docket reference is not a number in this sense — "
        "it is a label that happens to be made of digits, and it stops nobody. "
        "A BARE YEAR is not a magnitude either — it is a label for a point in "
        "time. '2009.' alone on a line stops nobody; 'six weeks' or '$175' or "
        "'one drop' does. A year may appear later in the note, never as the hook. "
        "This went wrong live twice: notes opened with 'US2989787' and with "
        "'2009.', where the good version of the same form opened with '1 drop'. "
        "If the only figures in the material are identifiers or dates, this is "
        "the wrong form for that material."
    ),
    "SCENA": (
        "Start with the object in front of the reader, in the second person: "
        "the thing they are holding, walking past, standing in. One line. Blank "
        "line. Then the rule hiding inside it. Never a question, and no "
        "invented experience of your own."
    ),
    "PYTANIE": (
        "Deliver the whole fact first, in two or three lines. Then, on its own "
        "line, one short question the reader can answer from their own life "
        "without looking anything up. "
        "This form is an experiment and it has a cost. Notes containing a "
        "question mark convert 35 percent fewer subscribers — but direct, "
        "easy questions are what actually pulls comments, and a young account "
        "needs conversation more than it needs a clean conversion rate. So: "
        "never a question INSTEAD of the fact, only after it. Never a question "
        "whose answer is in the note. Never a request for engagement."
    ),
    "ODWROCENIE": (
        "First line: the thing everyone believes, stated fairly and without "
        "mockery. Blank line. Then the record that contradicts it, and why the "
        "belief was reasonable in the first place. Break that second half too — "
        "four sentences crammed into one block undoes the whole point of the "
        "shape."
    ),
    # Struktura wskazywana zgodnie przez dwie niezalezne analizy duzych prob
    # notek (setki tysiecy sztuk): zaczep w pierwszej linii, dwie-cztery linie
    # tresci, konkret na koncu. Wersja dla NAS: zamiast osobistego wyniku,
    # ktorego anonimowa marka nie ma, konczymy rzecza do sprawdzenia u siebie.
    "ZACZEP_I_KONKRET": (
        "Three moves, in order. One: a hook line that works on somebody who "
        "has never heard of us and is scrolling — specific and surprising, "
        "never a category label. Two: two to four lines saying what the "
        "arrangement actually is and who decided it. Three: one closing line "
        "handing the reader something they can look at, count or compare "
        "themselves, today, without our help. Do not promise what they will "
        "find. No personal anecdote — we do not have one and must not invent it. "
        "THE THING MUST ALREADY BE IN THEIR LIFE: a bottle in their bathroom, "
        "the pending charges in their banking app, the light at their own "
        "junction. Sending them to read a regulation, open a standards document "
        "or look up an agency circular is homework, and nobody does homework "
        "from a feed. This went wrong live: a note ended with 'pull up any FAA "
        "advisory circular and count how many open with that phrase'."
    ),
}

NOTE_FORM_MIX = ("SCENA", "KONTRAST", "ZACZEP_I_KONKRET", "PROSTA", "LISTA",
                 "PYTANIE", "ODWROCENIE", "LICZBA")

NOTE_TYPES = {
    # MYSL — jedyny typ ZWOLNIONY z karty dowodowej, i jedyny, ktoremu nie
    # wolno niesc faktu.
    #
    # Wlasciciel pokazal cztery notki z kont, ktore chce nasladowac. Zadna nie
    # miala ani jednego udokumentowanego faktu — zero zrodel, zero liczb, zero
    # nazwisk — a ta zlozona z samych pytan ("Should AI have its own universal
    # language?") zebrala pietnascie komentarzy. Wiecej niz cokolwiek, co dotad
    # wystawilismy przy naszych 26 polubieniach na dwanascie notek.
    #
    # Nasze pozostale cztery typy wymagaja dowodu, wiec takiej notki nie da sie
    # u nas napisac. Ten typ to naprawia, placac twarda cena: bez faktu znaczy
    # BEZ FAKTU. Dzieki temu sprawdzanie faktow jest tu EGZEKUTOREM, a nie
    # przeszkoda — notka bez sprawdzalnego twierdzenia nie ma czego oblac,
    # a notka, ktora fakt przemyci, oblewa sie sama.
    "MYSL": (
        "A thought, a question, or an observation about what it is like to "
        "live alongside these systems. NO EVIDENCE CARD, and therefore NO "
        "FACTS: no number, no date, no named company doing a named thing, no "
        "study, no percentage, nothing a reader could look up and find false. "
        "If your idea needs a fact to stand up, it is a different note type "
        "and you should say so instead of inventing one.\n\n"
        "What is left is the part people actually answer: a question nobody "
        "can settle, an observation about the shared experience of using this "
        "stuff, a position you would defend out loud. It may be openly "
        "uncertain. It may be funny. It may admit that you are behind, "
        "confused, or annoyed — those read as human because they are the "
        "things a person says and an account never does.\n\n"
        "Two shapes work. FIRST: the open question, asked in earnest, with "
        "the two or three ways it could go named underneath — not a rhetorical "
        "question whose answer you are holding. SECOND: the observation that "
        "names something everyone has felt and nobody has said, followed by "
        "what you think it means.\n\n"
        "Speak in the first person and mean it. 'I think', 'I just realised', "
        "'maybe' are allowed here and nowhere else in this publication. The "
        "reader is being invited to disagree, so give them a specific thing "
        "to disagree with, not a mood."
    ),
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

# NAJGORSZE OKNO — I TO JEST STALA EGZEKWOWANA, nie zapis ustalen.
# `pora_na_publikacje` odmawia publikacji w tych godzinach, wiec miedzy 12:00
# a 13:59 u czytelnikow agent nie wystawia ANI notek, ANI komentarzy. To dwie
# z szesnastu godzin okna, codziennie.
#
# Stala stala wczesniej w bloku opisanym jako „NIE SA UZYWANE PRZEZ ZADNA LINIE
# KODU" i to bylo grozne w konkretny sposob: kto uwierzylby temu komentarzowi
# i skasowal ja jako martwa, dostalby NameError w `pora_na_publikacje`, czyli
# w funkcji wolanej na poczatku KAZDEGO przebiegu dnia. Komentarz mowil tez
# „agent wystawia notki rownomiernie w calym oknie 6-22 ET" — nieprawda
# wlasnie z powodu tej stalej.
WORST_NOTE_HOURS = (12, 13)  # ET, zwłaszcza w piątek — EGZEKWOWANE

# UWAGA: DWIE PONIZSZE STALE NIE SA UZYWANE PRZEZ ZADNA LINIE KODU.
# Agent nie wazy notek wedlug tych godzin ani dni — rozklada je losowo
# w oknie OKNO_PUBLIKACJI_ET z pominieciem WORST_NOTE_HOURS wyzej.
#
# To nie jest usterka do cichego naprawienia, bo NASZE WLASNE ZRODLA SIE NIE
# ZGADZAJA: ponizsze dane mowia, ze najlepsze jest 6-8 rano czasu nowojorskiego,
# a research z 18 sierpnia wskazywal 19:00-22:00 UTC, czyli 15:00-18:00 ET.
# Zanim cokolwiek zacznie wazyc godziny, trzeba rozstrzygnac ktore z tych
# dwoch. Do tego czasu stale zostaja jako ZAPIS USTALEN, wyraznie oznaczony
# jako nieuzywany — patrz `test_martwe_sygnaly.py`.
BEST_NOTE_HOURS = (6, 7, 8)  # ET — NIEUZYWANE
BEST_NOTE_DAYS = ("sunday", "saturday")  # NIEUZYWANE

# TWARDE OKNO PUBLIKACJI, w czasie CZYTELNIKOW. Agent wystawil notki o 03:57
# i 04:00 UTC — czyli 23:57 i polnoc w Nowym Jorku. Tekst wrzucony, gdy
# publicznosc spi, nie znika, ale traci pierwsze godziny widocznosci, a wlasnie
# one decyduja o zasiegu w kanale.
#
# Zegar mozna przestawic i reczne uruchomienie i tak by go ominelo, wiec zasada
# siedzi w KODZIE, nie w harmonogramie.
OKNO_PUBLIKACJI_ET = (6, 22)        # wolno od 6:00 do 21:59 czasu nowojorskiego
WORST_NOTE_DAYS = ("monday", "friday")

# Rozkład na tydzień: pięć notek dziennie, dzień publikacji artykułu ma własny.
# Ile notek promuje jeden artykul i przez ile dni. Decyzja wlasciciela z 20
# sierpnia: TRZY, po jednej dziennie, trzy dni z rzedu ZARAZ po artykule.
# Kilka linkow w jeden dzien to nie promocja, tylko natret; trzy przez trzy dni
# to trzy osobne szanse na trafienie kogos, kto akurat patrzy w kanal.
#
# Bylo piec. Zeszlo do trzech razem ze zmiana kolejnosci: promujemy NAJSWIEZSZY
# artykul, nie najdawniej wstawiony (patrz `artykul_do_promocji`). Przy pieciu
# dniach i artykule tygodniowo kolejka nie nadazala i swiezy tekst czekal za
# starszymi z zimnym juz linkiem.
NOTEK_PROMUJACYCH = 3

# MIESZANKA DNIA. Ostatnia pozycja to MYSL — notka bez zadnego dowodu.
#
# Powod jest w NOTE_TYPES przy samym typie: wszystkie pozostale wymagaja karty
# dowodowej, a konta, ktore wlasciciel wskazal jako wzor, zbieraja rozmowe
# notkami bez ani jednego faktu. Jedna na dzien, nie wiecej — wlasciciel
# powiedzial wprost "nie maja byc wszystkie takie", i ma racje: feed samych
# rozmyslan bez pokrycia to inne konto, nie nasze.
NOTE_MIX_ARTICLE_DAY = ("ARTYKUL", "ARTYKUL", "CIEKAWOSTKA", "SPROSTOWANIE", "MYSL")

# KSZTALTY NOTKI TYPU MYSL. Losowane w kodzie i podawane jako PRZYDZIAL.
#
# Powod jest zmierzony: opis typu wymienial pytanie i obserwacje jako dwie
# mozliwosci, a model wybral obserwacje SZESC RAZY NA SZESC i szesc razy
# zaczal od slowa "I". Notki byly dobre, ksztalt byl jeden.
#
# To ta sama choroba, co samooceny wracajace zawsze 1.0 i watki zawsze po
# szesc — postawiony przed wyborem, model zbiega do stalej. I to samo
# lekarstwo, co przy ruchu koncowym artykulu i formie notki: losowac w kodzie.
#
# Notka wlasciciela z pietnastoma komentarzami — najwiecej ze wszystkiego, co
# pokazal — byla PYTANIEM. Czyli ksztaltem, ktorego model nie wybral ani razu.
KSZTALTY_MYSLI = {
    "PYTANIE": (
        "Ask something nobody can settle, in earnest, and mean the question. "
        "Name two or three ways it could go underneath — that is the part "
        "people answer. You are not holding a hidden answer: if you know how "
        "it comes out, this is the wrong shape. End on the open end, not on a "
        "resolution. Do NOT open with the question and then quietly answer it."
    ),
    "OBSERWACJA": (
        "Name something everyone who uses these systems has felt and nobody "
        "has said out loud, then say what you think it means. First person, "
        "specific, about a habit or a moment rather than about the industry."
    ),
    "TEZA": (
        "State a position you would defend out loud, then the reasoning that "
        "got you there, then the part of it you are least sure about. Give "
        "the reader something precise to disagree with. No hedging into "
        "mush — a clearly stated wrong opinion is better than a safe one."
    ),
    "CUDZE_ZDANIE": (
        "Somebody else's take that you keep turning over — argued with, not "
        "reported. Say what it gets right, then where you come off it. Do not "
        "name or quote anyone: you have no evidence card, so the position is "
        "described in your own words as a position, never attributed."
    ),
}


def losowy_ksztalt_mysli() -> str:
    """Ktory ksztalt dostaje ta MYSL. Losowany, bo wybor zbiega do stalej."""
    import random
    return random.choice(list(KSZTALTY_MYSLI))
NOTE_MIX_OTHER_DAY = ("CIEKAWOSTKA", "CIEKAWOSTKA", "DYSKUSJA", "SPROSTOWANIE", "MYSL")

# --- zachowanie spoleczne: widelki, nie stale liczby -------------------------
# Stala liczba dziennie wyglada jak robot, bo czlowiek nie ma normy. Losujemy
# w tych granicach, osobno na kazdy dzien.
#
# UCZCIWIE O POCHODZENIU TYCH LICZB: Substack nie publikuje swoich limitow.
# To NIE sa zmierzone progi, tylko tempo aktywnego czlowieka. Sa celowo niskie,
# bo kosztem przesady nie jest ostrzezenie, tylko utrata konta, na ktorym stoi
# caly projekt. Podniesiemy je dopiero, gdy zobaczymy wlasne dane.
# PRZEJRZANE NA WLASNYCH DANYCH 2026-08-20 (piec dni dziennika). Do tej pory
# byly to liczby wziete z wyobrazenia o tempie czlowieka. Teraz wiemy, ile
# agent NAPRAWDE robi, i widelki maja to opisywac, a nie zyczyc sobie tego.
#
# Budzet, ktorego nigdy nie da sie wydac, nie jest budzetem: klamie w logu,
# psuje dzielenie normy na przebiegi i ukrywa, ze jakis blok w ogole nie chodzi.
#
#   zmierzone (srednia z 5 dni)   bylo w konfiguracji   ustawiam
#   lajki        9,6              12-20                 10-16
#   komentarze   7,0              15-20                 8-12
#   obserwacje   0,0 (!)          30-44/mies            0 (nie ma przycisku)
#   subskrypcje  ~0,8/dzien       6-12/mies             6-12/mies (bez zmian)
#   restacki     0,4              2-4/dzien             1-2/dzien
LAJKI_DZIENNIE = (10, 16)
# Osiemnascie komentarzy dziennie pod cudzymi tekstami to nie jest tempo
# czytelnika, tylko podpis bota — i kosztuje najwiecej po pisaniu, bo kazdy to
# trzy warianty plus sprawdzenie faktow, okolo trzech centow. Przy dwunastu
# dziennie wychodzi ~11 USD miesiecznie samych komentarzy.
KOMENTARZE_DZIENNIE = (8, 12)     # 0 jest dozwolone: milczenie bije slaby komentarz
# ZERO, BO PRZYCISKA NIE MA. Obserwacje nie wykonaly sie ANI RAZU i przez
# tygodnie wygladalo to na blad kolejnosci blokow albo za waski budzet.
# Sprawdzone 2026-08-23 na szesciu profilach: Substack zdjal „Follow" ze stron
# profilowych. Zostaly „Subscribe" i „Message", a samo slowo „Follow" nie
# wystepuje w HTML tych stron ani razu — i nie ma go tez na `/@kto/notes`.
# Przetrwal wylacznie w widgetach „kogo obserwowac", czyli w liscie podpowiedzi.
#
# Zero jest tu UCZCIWSZE niz mala liczba: budzetu nie rezerwujemy na zdolnosc,
# ktorej nie mamy, a licznik wolumenow nie pokazuje wiecznego zera, ktore
# czytaloby sie jak awaria. Wrocic to jedna zmiana w tym wierszu.
FOLLOW_MIESIECZNIE = (0, 0)       # patrz wyzej: nie ma czego kliknac
SUBSKRYPCJE_MIESIECZNIE = (6, 12)  # laduje w skrzynce wlasciciela, wiec waskie


def normy_dzienne() -> dict[str, float]:
    """Ile czego POWINNO wychodzic dziennie — srodek widelek.

    Liczone z tych samych stalych, ktore rozdzielaja budzet, zeby nie powstala
    druga lista liczb do rozjechania. Klucze sa takie, jak `rodzaj` w dzienniku
    dzialan — inaczej licznik porownywalby normy z niczym.

    PO CO. Przez osiem dni agent wystawil 23 notki przy normie 5 dziennie,
    czyli 58 procent, komentarzy 55, restackow 33 — i nikt tego nie wiedzial,
    bo nikt nie liczyl. Licznik `zrobione` zyl w pamieci jednego przebiegu,
    drukowal sie na koncu i ginal. Norma bez pomiaru jest zyczeniem.
    """
    return {
        "notka": float(len(NOTE_MIX_OTHER_DAY)),
        "polubienie": sum(LAJKI_DZIENNIE) / 2,
        "komentarz": sum(KOMENTARZE_DZIENNIE) / 2,
        "restack": sum(RESTACK_DZIENNIE) / 2,
        "subskrypcja": sum(SUBSKRYPCJE_MIESIECZNIE) / 2 / 30,
        # NAZWA MUSI BYC TAKA, JAK `rodzaj` W DZIENNIKU. Bylo tu "follow",
        # a `browser.obserwuj_profil` zapisuje "obserwacja" — licznik
        # porownywal wiec norme z niczym i zglaszal 0% przy dzialajacym
        # bloku. Dokladnie ta klasa bledu, ktora ten licznik ma lapac.
        "obserwacja": sum(FOLLOW_MIESIECZNIE) / 2 / 30,
    }


# Ponizej ilu procent normy uznajemy, ze cos jest zepsute, a nie po prostu
# chudsze. Prog jest niski celowo: budzety sa LOSOWANE z widelek i dzielone
# na przebiegi, wiec wahania rzedu kilkunastu procent to normalna praca.
# Polowa normy utrzymujaca sie przez tydzien to juz nie wahanie.
PROG_ALARMU_WOLUMENU = 60
# ODBLOKOWANE decyzja wlasciciela 2026-08-19. Restack cudzej notki z wlasnym
# zdaniem trafia do kanalu NASZYCH obserwujacych, powiadamia autora oryginalu
# i stawia nasze zdanie obok jego — za cene jednego zdania, nie calej notki.
#
# Wask0 celowo. Restack jest publicznym aktem na cudzej tresci: przy dziesieciu
# dziennie konto wyglada jak wzmacniacz, a nie jak ktos, kto czyta. Dwa-cztery
# to tyle, ile czlowiek naprawde uzna za warte podania dalej.
# --- ciche dni ---------------------------------------------------------------
# Publikacja nadajaca identycznie codziennie czyta sie jak kanal, a nie jak
# ktos, kto mysli. To byl ostatni wyrazny podpis automatu na tym profilu:
# siedem dni z rzedu, ten sam rytm, zadnej przerwy.
#
# Ale cichy dzien wycisza NADAWANIE, nigdy ODPOWIADANIE. Nieodpisanie komus,
# kto sie do nas odezwal, nie jest cisza tylko lekcewazeniem — i akurat to
# widac natychmiast.
#
# Decyzja musi byc TA SAMA dla wszystkich przebiegow tego samego dnia. Losowanie
# per przebieg dalo by dzien, w ktorym rano jest cicho, a wieczorem nie — czyli
# gorzej niz brak ciszy. Dlatego liczymy ja z daty, deterministycznie.
CICHY_DZIEN_NA_ILE = 8          # srednio jeden na osiem dni
CICHE_DNI_WLACZONE = True


def _cisza_z_hasza(dzien: str) -> bool:
    import hashlib

    liczba = int(hashlib.sha256(("%s|cisza" % dzien).encode("utf-8")).hexdigest()[:8], 16)
    return liczba % CICHY_DZIEN_NA_ILE == 0


def cichy_dzien(kiedy=None) -> bool:
    """Czy dzis nie nadajemy. Ta sama odpowiedz przez caly dzien.

    Sam hasz daje SKUPISKA: na dwoch latach wypadly cztery ciche dni z rzedu,
    a to juz nie jest przerwa na myslenie, tylko porzucone konto. Wiec dzien
    jest cichy tylko wtedy, gdy poprzedni nie byl — deterministycznie, bez
    zadnego stanu do zapamietania, i nadal identycznie dla wszystkich
    przebiegow tej samej doby.
    """
    from datetime import datetime, timedelta, timezone

    if not CICHE_DNI_WLACZONE or CICHY_DZIEN_NA_ILE < 2:
        return False
    kiedy = kiedy or datetime.now(timezone.utc)
    dzis = kiedy.strftime("%Y-%m-%d")
    wczoraj = (kiedy - timedelta(days=1)).strftime("%Y-%m-%d")
    return _cisza_z_hasza(dzis) and not _cisza_z_hasza(wczoraj)


# Zjechane z 2-4 na 1-2 (2026-08-20). Restack stawia NASZE nazwisko obok
# cudzego tekstu — to najmocniejszy gest w calym repertuarze i jedyny, ktory
# firmuje czyjes zdanie. Cztery dziennie to nie czytanie, tylko rozdawanie
# poparcia. Zmierzone wykonanie i tak wynosilo 0,4 dziennie.
RESTACK_DZIENNIE = (1, 2)

# Dopisek do cudzej notki. Powyzej tego to juz nie dopisek, tylko wlasna notka
# doczepiona do czyjegos tekstu — a wtedy lepiej napisac wlasna notke.
RESTACK_MAX_SLOW = 40

# Pierwszy miesiac na dolnej polowie widelek. Nowe konto z jednym artykulem,
# ktore nagle obserwuje dwadziescia osob, wyglada dokladnie jak farma.
# Ile razy dziennie odpala sie agent. Dzienny przydzial dzieli sie na tyle
# przebiegow, zeby notki rozkladaly sie na GODZINY, a nie wychodzily jedna po
# drugiej w odstepie trzech minut — to wlasciciel zauwazyl na profilu.
PRZEBIEGOW_DZIENNIE = 3

# ILE CZASU MA PRZEBIEG. Musi zgadzac sie z `TimeoutStartSec` w pliku uslugi —
# to jedyne miejsce, gdzie ta sama liczba stoi dwa razy, i pilnuje tego test,
# bo rozjazd wychodzilby dopiero przy realnym przebiegu.
#
# 16 sierpnia systemd ubil przebieg po 2,5 h, bo mial do wystawienia szesnascie
# komentarzy przy odstepach 3-8 minut. Zabity SIGTERM-em proces nic nie zapisal,
# wiec wiersz wisial w bazie jako RUNNING do najblizszej kontroli zdrowia.
# Agent ma teraz konczyc SAM, zanim zegar go zetnie w polowie zdania.
LIMIT_CZASU_PRZEBIEGU_S = 9000
# Zapas na domkniecie: ostatnia publikacja, zamkniecie przebiegu, alarm.
ZAPAS_CZASU_S = 900

ROZBIEG_DNI = 30

# Odstepy miedzy dzialaniami, w sekundach. Pietnascie polubien w dziewiecdziesiat
# sekund to nie jest czytanie i kazdy system to widzi.
# Odstepy ROZNE dla roznych czynnosci, bo czlowiekowi roznie dlugo zajmuja.
# Jeden wspolny odstep 45-180 s dawal notke po notce w trzy minuty — a nikt tak
# nie publikuje. Polubienie co minute jest za to zupelnie naturalne.
#
# W sekundach, losowane w tych granicach osobno przy kazdym dzialaniu.
ODSTEPY = {
    # 45-90 MIN, nie 10-25. Zmierzone na profilu: notki wychodzily PARAMI
    # kilkanascie minut po sobie, potem cisza na trzy i pol godziny, i tak trzy
    # razy dziennie. To nie byl rytm czlowieka, tylko ksztalt PRZEBIEGU widoczny
    # na osi czasu: zegar budzil agenta, ten robil swoje dwie notki jedna po
    # drugiej i zasypial. Nikt nie musial analizowac stylu — wystarczylo
    # spojrzec na profil.
    #
    # Gorna granica jest przycieta do przebiegu: dwie notki po 90 minut mieszcza
    # sie w limicie czasu, trzy juz nie — i wtedy `zostal_czas` uczciwie konczy
    # dzien krocej, zamiast dac sie przeciac w polowie.
    "notka":      (2700, 5400),  # 45-90 min
    "komentarz":  (180, 480),    #  3-8 min: przeczytac cudzy tekst i odpowiedziec
    "odpowiedz":  (120, 420),    #  2-7 min
    "lajk":       (30, 90),      # 0,5-1,5 min: przewijanie kanalu
    # Restack wymaga PRZECZYTANIA cudzej notki i napisania wlasnego zdania.
    # Kilkanascie sekund miedzy jednym a drugim znaczyloby, ze nie czytalismy
    # zadnej — a to widac na profilu tak samo, jak widac bylo notki parami.
    "restack":    (600, 1800),   # 10-30 min
}
ODSTEP_MIEDZY_DZIALANIAMI = (45, 180)   # zapas dla czynnosci bez wlasnego wpisu

# ZWLOKA PRZED PIERWSZA NOTKA PRZEBIEGU. Bez niej pierwsza notka wychodzila
# zawsze kilka minut po starcie zegara, wiec trzy razy dziennie o tej samej
# porze co do kwadransa. Losowa zwloka rozmywa sam moment startu — godziny
# zostaja te, ktore wybralismy, ale minuty przestaja byc przewidywalne.
ZWLOKA_PRZED_NOTKAMI = (0, 2400)        # 0-40 min

# ILE CZASU PRZEBIEGU WOLNO ZJESC SAMYM NOTKOM.
#
# Rozdzielnik dzienny nie wiedzial nic o czasie: dzielil norme tak, jakby
# dzialania byly natychmiastowe. Po wydluzeniu odstepow do 45-90 minut wieczorna
# rutyna dostala CZTERY notki, czyli od trzech do szesciu godzin samego czekania
# przy budzecie dwoch godzin pietnastu minut. Po 2h17 miala jedna notke i spala,
# a do czternastu zaplanowanych komentarzy nie doszla wcale.
#
# Notki maja pierwszenstwo, bo sa rzadsze i wazniejsze — ale nie caly przebieg.
UDZIAL_CZASU_NA_NOTKI = 0.60

# Ile trwa samo dzialanie poza przerwa: napisanie, sprawdzenie faktow,
# wystawienie i potwierdzenie u zrodla. Z realnych przebiegow.
CZAS_DZIALANIA_S = 240
# USUNIETE 2026-08-20: MAX_DZIALAN_NA_GODZINE = 12 nie bylo egzekwowane nigdzie.
# Tempo wyznaczaja ODSTEPY miedzy dzialaniami i nic poza nimi. Nie dopisuje
# limitu godzinowego przy okazji audytu — nowy, nieprzetestowany ogranicznik
# w srodku przegladu to gorszy pomysl niz uczciwe przyznanie, ze go nie ma.

# USUNIETE 2026-08-20: MAX_KOMENTARZY_NA_PUBLIKACJE = 2 nie bylo egzekwowane
# przez ZADNA linie kodu. Sam powolalem sie na nie tego samego dnia jako na
# istniejace zabezpieczenie — i to jest cala szkoda, jaka robi martwa stala:
# czyta sie ja jak gwarancje, ktorej nie ma.
#
# Zabezpieczenie istnieje i jest OSTRZEJSZE: `_za_niedawno_u_nich` w kanal.py
# odsiewa publikacje, u ktorych komentowalismy w ostatnich
# ODSTEP_DNI_NA_PUBLIKACJE dniach — czyli raz na cztery dni, nie dwa razy
# dziennie.

# NIE KOMENTUJEMY SWIEZYCH POSTOW. Wlasciciel opisal to najlepiej: napisal notke
# i piec sekund pozniej ktos odpisal ogolnikowa zgoda — i to zdradza bota
# natychmiast, zanim ktokolwiek przeczyta tresc odpowiedzi. Czlowiek najpierw
# musi tekst ZOBACZYC i PRZECZYTAC.
#
# Losujemy prog dla kazdego posta osobno, w minutach.
MIN_WIEK_POSTA_MIN = (90, 900)      # od poltorej godziny do pietnastu

# NOTKA TO NIE ARTYKUL i zyje godziny, nie dni. Ten sam prog co dla artykulow
# oznaczal, ze pod notki wchodzilismy zawsze PO koncu rozmowy: przeglad pokazal
# dwa cele na przebieg, oba z zerem odpowiedzi, i trzy odrzucone jako za swieze.
# Nadal czekamy — bo odpowiedz piec sekund po notce zdradza automat, i to
# wlasciciel zauwazyl pierwszy — ale tyle, ile trwa przeczytanie, nie pol dnia.
MIN_WIEK_NOTKI_MIN = (20, 90)       # od dwudziestu minut do poltorej godziny

# ILU KOMENTARZY POD CELEM JESZCZE NIE UWAZAMY ZA TLOK. Wyszukiwarka oddawala
# posty ze srednio 45 komentarzami, jeden ze 126 — a komentarz sto dwudziesty
# siodmy jest niewidoczny. Swieze konto nie wygrywa glosnoscia, tylko byciem
# wczesnie tam, gdzie rozmowa dopiero sie zaczyna.
KOMFORTOWO_KOMENTARZY = 25

# Ile dni odstepu przed kolejnym komentarzem pod TA SAMA publikacja. Komentarz
# pod kazdym kolejnym tekstem tej samej osoby to drugi najczytelniejszy sygnal
# automatu — czlowiek nie czyta wszystkiego, co ktos wypuszcza.
ODSTEP_DNI_NA_PUBLIKACJE = 4

# HASLA, KTORYMI AGENT SZUKA NOWYCH KONT. Kanal czytelnika pokazuje tylko to,
# co juz znamy, wiec sam z siebie nie przyprowadzi nikogo nowego — a wlasnie
# o nowych ludzi chodzi. Wyszukiwarka Substacka oddaje konta spoza naszego kregu.
#
# Hasla opisuja NASZ rewir: ukryte systemy, przepisy, bodzce i decyzje za
# rzeczami codziennymi. Losujemy kilka przy kazdym przebiegu, zeby nie wracac
# ciagle do tej samej niszy.
HASLA_SZUKANIA = (
    "building codes regulation", "food labeling rules", "safety standards history",
    "why prices are set", "infrastructure decisions", "product recall",
    "packaging regulation", "transport standards", "consumer protection rule",
    "why this design exists", "hidden fees", "zoning", "supply chain incentives",
    "medical device rules", "aviation regulation", "energy efficiency standard",
    "why companies do this", "unintended consequences policy",
)
ILE_HASEL_NA_PRZEBIEG = 3

# Odpowiedzi POD WLASNYMI tresciami sa poza limitami dziennymi. Decyzja
# wlasciciela i jest sluszna: limit chroni przed wygladaniem na spamera u obcych,
# a u siebie jest sie gospodarzem. Pytanie bez odpowiedzi pod wlasnym artykulem
# szkodzi bardziej niz dziesiec komentarzy za duzo — czytelnik, ktory poswiecil
# czas i nie dostal odpowiedzi, nie wraca.
ODPOWIEDZI_POZA_LIMITEM = True

# Do ilu komentarzy odpowiadamy BEZ wybierania. Przy dwoch odpowiada sie obu.
# Przy dwustu odpowiedz pod kazdym wyglada jak maszyna — nawet gdy kazda jest
# dobra — wiec powyzej tego progu agent wybiera najwazniejsze, z pierwszenstwem
# dla niezgody: nieodpowiedziany zarzut zostaje ostatnim slowem.
# POLITYKA ZALEZNA OD SKALI, decyzja wlasciciela.
#
# Swieze konto zyje z rozmowy: ktos komentuje, my odpowiadamy, watek rosnie
# i algorytm to lubi. Przy pieciu komentarzach odpowiada sie WSZYSTKIM i to jest
# najtansza rzecz, jaka male konto moze zrobic dla swojego zasiegu.
#
# Przy pieciudziesieciu odpowiedz pod kazdym wyglada jak maszyna i przestaje byc
# rozmowa. Wtedy bierzemy te NAJBARDZIEJ ZYWE: najwiecej polubien i najwiecej
# odpowiedzi pod soba, bo tam siedzi dyskusja, ktora warto ciagnac.
ODPOWIADAJ_WSZYSTKIM_DO = 5      # male konto: kazdemu, bez wyjatku
WYBIERAJ_POWYZEJ = 20            # powyzej tego liczy sie juz popularnosc watku
MAX_ODPOWIEDZI_MALE = 6
MAX_ODPOWIEDZI_DUZE = 8


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


# Twardy sufit na JEDNO wywolanie. Bez niego wyliczenie z sufitu tokenow dawalo
# 965 sekund, a przy wyszukiwaniu razy trzy — 48 MINUT. Jedno zawieszone
# wywolanie blokowaloby caly dzien, a systemd ubilby przebieg po godzinie
# w polowie roboty, zostawiajac dzien zrobiony do polowy.
MAX_TIMEOUT_S = 300


def timeout_for(max_tokens: int) -> float:
    """Termin w sekundach, który realnie pokrywa podany sufit tokenów.

    Ograniczony twardo: wyliczenie z sufitu dawało 965 sekund, a przy
    wyszukiwaniu razy trzy — 48 minut na JEDNO wywołanie. Jedno zawieszenie
    blokowałoby cały dzień, a `systemd` ubiłby przebieg po godzinie w połowie
    roboty. Lepiej stracić jedną notkę niż resztę dnia.
    """
    return min(round(max_tokens * MS_PER_OUTPUT_TOKEN / 1000 * TIMEOUT_MARGIN, 1),
               MAX_TIMEOUT_S)


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
# ILE ZNAKOW MUSI ODDAC STRONA, ZEBY LICZYC SIE JAKO ZRODLO.
#
# Bylo 400 i to bylo za malo w sposob, ktory widac dopiero na przebiegu.
# Zmierzone 25 sierpnia 2026 na artykule o automatycznym wykrywaniu naduzyc
# w zasilkach, dziewiec zrodel:
#
#     amnesty.nl                      146038 znakow   12 fragmentow   2 liczby
#     hrw.org                          81669           11             10
#     documents.uow.edu.au              7891
#     cdn.greens.org.au                 3275
#     autoriteitpersoonsgegevens.nl      716            3              0
#     openresearch-repository.anu.edu.au 483            2              0
#
# Obie strony ponizej tysiaca znakow oddaly ZERO liczb, a mimo to weszly do
# bilansu jako pelnoprawne zrodla pierwotne — jedna z nich dostala nawet
# trafnosc 0.80. To sa banery zgody i strony tytulowe repozytoriow, z ktorych
# klasyfikator wyciaga "fragmenty" ze stopki.
#
# Prog 1500 lezy w przerwie: odrzuca obie zajawki, przepuszcza najmniejsze
# realne zrodlo z tego przebiegu (3275). Nie stawiam go wyzej, bo krotkie
# dokumenty urzedowe — zawiadomienie, postanowienie, nota — bywaja prawdziwe.
FETCH_MIN_CHARS = 1500
FETCH_USER_AGENT = "Mozilla/5.0 (compatible; NothingIsAccidental/1.0; +editorial research)"

# --- bramki jakości ----------------------------------------------------------
# NIC NIE BLOKUJE. Te cztery są zgłaszane właścicielowi jako uwagi do
# przeczytania; artykuł powstaje zawsze i trafia do szuflady.

# USUNIETA 2026-08-20 lista FLAGGED_GATES. Wymieniala CZTERY bramki, nie byla
# przez nic czytana, a bramek jest dzis dwanascie deterministycznych i cztery
# obserwacyjne. Nieaktualna lista, ktorej nikt nie uzywa, jest gorsza niz jej
# brak: opisuje system, ktory przestal istniec. Zrodlem prawdy jest
# `gates.deterministic_floors`.

# Jedno podejście. Bez przepisywania — to tam paliły się pieniądze i tam dwie
# bramki starego agenta odpowiedziały różnie na to samo pytanie. Zasada zostaje,
# stala ATTEMPTS = 1 usunieta 2026-08-20: nic nie petlilo, wiec nie bylo czego
# ograniczac, a liczba sugerowala mechanizm, ktorego nie ma.


# --- ruch koncowy i szerokosc drugiego aktu --------------------------------
# Dwa artykuly napisane PO naprawie szamponu (0017 "The Gas You Didn't Buy",
# 0019 "The Yellow Light...") wyszly z identycznym szkieletem: ten sam
# drogowskaz przed paralelami ("once you see this shape, it turns up
# everywhere"), dokladnie trzy paralele, akapit o granicach zapowiedziany
# meta-zdaniem, zamkniecie "sprawdz to u siebie". Zaden z tych ruchow nie jest
# bledem osobno; bledem jest to, ze wypadaja za kazdym razem tak samo, bo
# pisarz.md je zamowil. Powtarzalna forma jest sygnalem maszyny dokladnie tak
# samo jak powtarzany mechanizm w szamponie. Wiec losujemy — tak jak przy
# notkach z NOTE_FORM.
RUCHY_KONCOWE = {
    "DO_SPRAWDZENIA": (
        "Close by handing the reader something observable in their own life — "
        "a thing to look at, count or compare, where the mechanism will show "
        "through. Do not promise what they will find."
    ),
    "GDZIE_KONCZY_SIE_ZAPIS": (
        "Close on the boundary of what is documented: name the one question "
        "the record does not answer and say plainly why nobody answering it "
        "publicly is a fact about the arrangement, not an accident."
    ),
    "KTO_NA_TYM_STOI": (
        "Close on the party the arrangement serves. Not an accusation — just "
        "the plain sentence naming who carries the cost and who is spared it, "
        "left standing without commentary."
    ),
    "GDYBY_INACZEJ": (
        "Close by describing the version of this that could have been built "
        "instead, and what it would have cost whom. Make the current design "
        "visible as a choice by putting one alternative next to it."
    ),
    "POWROT_DO_ZACZEPU": (
        "Close by returning to the exact image or belief you opened with and "
        "showing it changed — same object, different thing to look at now. No "
        "summary of the argument in between."
    ),
    "CENA_MECHANIZMU": (
        "Close on what this costs when it fails or when it is applied to "
        "someone it was not designed for. One case, concrete, then stop."
    ),
}

RUCH_KONCOWY_MIX = ("DO_SPRAWDZENIA", "KTO_NA_TYM_STOI", "POWROT_DO_ZACZEPU",
                    "GDZIE_KONCZY_SIE_ZAPIS", "CENA_MECHANIZMU", "GDYBY_INACZEJ")

# Ile paraleli w drugim akcie. Trzy wyliczone po kolei czytaja sie jak lista;
# jedna rozwinieta na dwa akapity czyta sie jak mysl. Chcemy obu, na zmiane.
ILE_PARALELI_WAGI = {1: 4, 2: 4, 3: 3}

OPIS_LICZBY_PARALELI = {
    1: ("ONE parallel, developed properly — two paragraphs on a single other "
        "domain where this logic runs, close enough to follow all the way "
        "down. One thought, not a catalogue."),
    2: ("TWO parallels, a paragraph each. Pick two that fail differently, so "
        "the pair says something a single example could not."),
    3: ("THREE parallels, briskly — but they must escalate. If the third is "
        "interchangeable with the first, you have written a list; cut it to "
        "two."),
}


def losowy_ruch_koncowy() -> tuple[str, str]:
    """Czym konczy sie TEN artykul. Rowne szanse, bez powtarzania formuly."""
    import random

    nazwa = random.choice(RUCH_KONCOWY_MIX)
    return nazwa, RUCHY_KONCOWE[nazwa]


def losowa_liczba_paraleli(glebokosc: str = "RICH") -> tuple[int, str]:
    """Ile paraleli w drugim akcie. Krotki artykul nigdy nie bierze trzech."""
    import random

    wagi = dict(ILE_PARALELI_WAGI)
    if (glebokosc or "").upper() != "RICH":
        wagi = {1: 5, 2: 3}
    ile = random.choices(list(wagi), weights=list(wagi.values()), k=1)[0]
    return ile, OPIS_LICZBY_PARALELI[ile]


# --- generatory tematow ------------------------------------------------------
# Mielismy 52 DZIEDZINY, czyli odpowiedz na pytanie GDZIE szukac, i zero
# wzorcow, czyli zadnej odpowiedzi na pytanie CZEGO. Model dostawal „przyroda,
# finanse, prawo" i sam musial zgadnac, co w tych obszarach jest ciekawe.
#
# Sprawdzone na wlasnych tekstach: szesc naszych artykulow trafia w PIEC
# roznych wzorcow ponizej, wiec siatka pokrywa to, co juz umiemy, i nazywa
# kilka, ktorych nie tknelismy. Generator x dziedzina to kilkaset komorek,
# a kazda produkuje kandydatow.
GENERATORY = {
    "MEASUREMENT": "A number that looks like a measurement but is a ratio, a band "
                   "or marketing. Probe: what number does this domain print on "
                   "things, and what is it actually the ratio of?",
    "MIRROR": "Two jurisdictions, opposite rules, each internally correct. Probe: "
              "where does another country do the exact opposite, and why is each "
              "one right at home?",
    "FAILURE": "An incident where the system behaved exactly as designed, and that "
               "is why it broke. Probe: what is the famous outage or accident here, "
               "and what did it reveal that was always true?",
    "DECIDER": "Someone chose this. They have a name and a date. Nobody knows "
               "either. Probe: who signed this off, in what year, and what were "
               "they optimising for?",
    "FOSSIL": "The constraint disappeared, the shape stayed. Probe: what is here "
              "only because of a machine or a law that no longer exists?",
    "MARGIN": "A limit that reads as stinginess is exactly what the calculation "
              "requires. Probe: what looks under-provisioned, and what calculation "
              "makes it precisely enough?",
    "FRAUD": "The feature is a fossil of one specific crime. Probe: what does this "
             "defend against, and who was the criminal that caused it to exist?",
    "QUEUE": "An order you did not know was designed. Probe: what is the invisible "
             "ordering here, and what is it optimising that is not your convenience?",
    "CONFESSION": "The standard admits its own imprecision, in writing. Probe: "
                  "where does the rulebook say 'this is approximate', and why did "
                  "it have to?",
    "SUBSIDY": "One price hides a transfer between groups. Probe: who is overpaying "
               "so that someone else can be served at all?",
    "ROUND_NUMBER": "The threshold is round because a committee rounded it. Probe: "
                    "is this a natural break or a negotiated one, and who was in "
                    "the room?",
    "BOUNDARY": "The system must rule on a moment that does not exist. Probe: what "
                "happens exactly at the edge — midnight, the date line, the instant "
                "of payment?",
    # DWA WZORCE POD WIELKIE PYTANIA, dopisane 25 sierpnia 2026.
    #
    # POMIAR, KTORY TO WYMUSIL. Ostatni przebieg ciekawostek oddal cztery dobre
    # fakty: ukryte tokeny rozumowania w o1 rozliczane jak wyjscie, cztery ceny
    # tego samego modelu Gemini, AlphaFold i miejsca wiazania, radiolodzy przy
    # mammografii. Kazdy z nazwanym decydentem i data. I ZERO z czterech stoi
    # pod pytaniem, ktore czytelnik zadaje sam z siebie („czy to rozumie", „czy
    # potrafi klamac") — a wlasnie takich pyta wlasciciel, wskazujac AI
    # Revolution, Wesa Rotha i „This Is IT".
    #
    # Przyczyna jest w siatce, nie w modelu: dwanascie wzorcow powyzej pyta
    # o LICZBE, JURYSDYKCJE, DECYDENTA i AWARIE. Zaden nie pyta o ZACHOWANIE
    # SAMEGO SYSTEMU, wiec model nie mial jak trafic tam nawet przypadkiem.
    #
    # DLACZEGO TO NIE SA DUPLIKATY — sprawdzone po kolei wobec calej dwunastki:
    #   SEEMING vs MEASUREMENT: MEASUREMENT startuje z liczby wydrukowanej na
    #     rzeczy i pyta, czego jest ilorazem. SEEMING startuje z ZACHOWANIA
    #     i pyta, czy w ogole istnieje liczba, ktora je rozstrzyga. Przeciwne
    #     kierunki, a druga polowa przypadkow nie ma zadnej liczby na wejsciu.
    #   UNBIDDEN vs FAILURE: FAILURE to „zachowal sie DOKLADNIE jak
    #     zaprojektowano i dlatego pekl". UNBIDDEN to dokladnie odwrotnie —
    #     nikt tego nie zaprojektowal. Wspolny jest tylko incydent.
    #   UNBIDDEN vs CONFESSION: CONFESSION wymaga, zeby regulamin sam sie
    #     przyznal NA PISMIE. UNBIDDEN obejmuje takze przypadek, w ktorym nikt
    #     sie nie przyznal i zachowanie znalazl ktos z zewnatrz.
    # Trzeciego nie dokladam: DECIDER („kto ustawil prog odmowy, nazwisko
    # i rok") juz obsluguje pytanie „czy model ma wlasne cele" od strony
    # czlowieka, ktory te cele wpisal, i nie potrzebuje blizniaka.
    # KONCOWKA PRZEPISANA PO KRYTYCE. Stalo tu „— or is there no such test yet,
    # and who says so?", czyli sonda zamawiala doslownie to, czego akapit obok
    # w prompcie zabrania: „jesli najmocniejsze, co masz pod spodem, to ze
    # ludzie sie nie zgadzaja, znalazles spor, a spory sa za darmo".
    # Brak testu jest dobrym znaleziskiem, ale musi byc UDOKUMENTOWANY brakiem
    # w dokumencie — pusta rubryka w karcie systemowej, zestaw ewaluacji, ktory
    # tego nie mierzy — a nie czyjas opinia, ze testu nie ma.
    "SEEMING": "A behaviour that reads as thinking, and the measurement that "
               "says what it is. Probe: what here looks like a mind at work, "
               "and which published test tells the appearance from the thing — "
               "or which evaluation suite, system card or audit visibly leaves "
               "that box empty?",
    "UNBIDDEN": "The system does something nobody specified, and its builders "
                "found out afterwards. Probe: what behaviour appeared that was "
                "not designed, who noticed it first, and what did they change "
                "once they had?",
}

ILE_GENERATOROW_NA_PRZEBIEG = 4

# Ile kandydatow-jednolinijkowcow zamawiamy, zanim cokolwiek napiszemy.
# Nadprodukcja jest obowiazkowa: piec notek z piatki pomyslow to mediana,
# piec z dwudziestu piatki to wybor.
KANDYDATOW_NA_PRZEBIEG = 25


def losowe_generatory(ile: int = 0) -> list[str]:
    """Ktore wzorce w tym przebiegu. Ten sam generator dwa dni z rzedu daje
    jednolity ksztalt, a jednolity ksztalt to podpis maszyny."""
    import random

    return random.sample(list(GENERATORY), k=min(ile or ILE_GENERATOROW_NA_PRZEBIEG,
                                                 len(GENERATORY)))


# --- co czytelnik trzyma w reku W TYM MIESIACU -------------------------------
# Najtansza dzwignia, jaka mamy, i nie mielismy jej wcale. Zwykla rzecz,
# ktorej ktos WLASNIE dotyka, bije zwykla rzecz w ogole: artykul o SPF
# w sierpniu to nie przypadek.
#
# Miesiace wg polkuli polnocnej, bo tam jest wiekszosc czytelnikow anglojezycznych.
# RYTM ROKU W TEJ DZIEDZINIE.
#
# Bylo tu dwanascie hasel konsumenckich: opony zimowe, filtry UV, rozliczenie
# podatku. Pod publikacje o AI to martwy balast — czytelnik nie „trzyma w reku"
# niczego, co zalezy od pory roku.
#
# Ale rok w tej dziedzinie MA rytm i jest on realny: konferencje, kwartalne
# wyniki producentow sprzetu, terminy w przepisach, cykl akademicki. To sa
# okresy WZMOZONEJ UWAGI, nie fakty do zacytowania — i tak sa opisane, bo
# terminy sie przesuwaja, a model tego nie czuje. Kazde haslo mowi GDZIE
# patrzec, a nie CO jest prawda.
W_TYM_MIESIACU = {
    1: "year-ahead predictions everywhere, CES hardware claims, budget and "
       "hiring plans set for the year",
    2: "earnings calls from chip and cloud companies, EU rules with dates "
       "attached, conference paper decisions",
    3: "GPU and hardware announcements, spring model releases, university "
       "admissions and what students are told about AI",
    4: "quarterly results, compute spending disclosed to investors, "
       "regulatory consultations closing",
    5: "big developer conferences and the demos shown at them, exam season "
       "and detection tools, summer internships",
    6: "developer conferences continuing, mid-year model releases, summer "
       "school and research internships beginning",
    7: "conference season in machine learning, half-year retrospectives, "
       "quiet-period releases",
    8: "back-to-school procurement, autumn model releases being trailed, "
       "energy and cooling under summer peak load",
    9: "school and university year starting with new AI policies, autumn "
       "launches, quarterly hardware results",
    10: "earnings season, year-end model releases, compliance deadlines "
        "arriving, safety reports published",
    11: "end-of-year launches, conference pre-prints, annual safety and "
        "transparency reporting",
    12: "year in review everywhere, December conferences, budgets and "
        "compute contracts signed for next year",
}


def co_teraz_w_reku(kiedy=None) -> str:
    """Rzeczy, ktorych czytelnik dotyka wlasnie teraz."""
    from datetime import datetime, timezone

    kiedy = kiedy or datetime.now(timezone.utc)
    return W_TYM_MIESIACU.get(kiedy.month, "")
