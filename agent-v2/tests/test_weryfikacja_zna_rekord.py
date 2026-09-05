# -*- coding: utf-8 -*-
"""Weryfikator dostaje rekord, na ktorym notka stoi — zamiast szukac od zera.

CO SIE STALO (M1 z przegladu zewnetrznego, potwierdzone na naszym kodzie).
Do 5 wrzesnia 2026 do `zweryfikuj` szlo z notki samo „Substack note, type
CIEKAWOSTKA". Fakt niesie `url`, `source_date`, `control_url`,
`control_verdict` i `control_fact` — wszystko sprawdzone i OPLACONE wczesniej,
przy dobieraniu do banku. Weryfikator tego nie widzial i szukal wszystkiego od
nowa, a kazda runda wyszukiwania to 10-19 tys. tokenow wejscia.

ZMIERZONE 29 sierpnia - 4 wrzesnia 2026: 161 wywolan `factcheck`, 900
wyszukiwan (5,6 na wywolanie), 7,11 mln tokenow wejscia, 2,55 USD.

TO NIE JEST WYLACZENIE BRAMKI i ten test tego pilnuje. Weryfikator ma nadal
prawo obalic rekord, bo bramka zarabia na siebie: 14 z 87 tekstow w tym
tygodniu mialo blad faktyczny (8 poprawionych, 6 zablokowanych), a wsrod nich
zmyslona szesciomiesieczna przerwa miedzy wlamaniami i praca naukowa, ktora
„nigdy nie twierdzi" tego, co jej przypisano.

DRUGA SPRAWA W TYM PLIKU (Q4). Notka MYSL z zalozenia NIE stoi na fakcie:
`weryfikacja.md` sprawdza przy niej ksztalt tekstu, nie prawdziwosc
zewnetrznego twierdzenia, i kaze oznaczyc kazda liczbe jako `refuted`.
`napraw_obalone` z zasady nie usuwa zdania, tylko poprawia je Z MATERIALU —
a materialu tam nie ma. Model wymyslal wiec liczbe albo naprawa odpadala, a
drugie sprawdzenie i tak bylo zaplacone.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_weryfikacja_zna_rekord.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import stages   # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


FAKT = {
    "fact": "OpenAI cut the price of the mini tier by half",
    "actually": "the cut applies only to cached input",
    "url": "https://openai.com/news/pricing",
    "source_date": "2026-09-04",
    "control_url": "https://openai.com/api/pricing",
    "control_date": "2026-09-05",
    "control_verdict": "CONFIRMS",
    "control_fact": "the published price table still shows the halved rate",
    # PONIZEJ: ksiegowosc banku, ktora NIE MA prawa dojsc do weryfikatora.
    "status": "nowy",
    "ranga": 3,
    "powod": "bank: mocny mechanizm",
    "dlaczego_mocny": "sedzia uznal, ze to najlepszy fakt partii",
    "zielone_swiatlo": True,
    "podobne_do": "inny fakt",
}

print("=== 1. REKORD NAPRAWDE DOCHODZI DO WERYFIKATORA ===")
k = stages._rekord_do_weryfikacji("CIEKAWOSTKA", {"fact": FAKT})
for pole in ("url", "source_date", "control_url", "control_verdict",
             "control_fact"):
    sprawdz("rekord niesie %s" % pole, str(FAKT[pole]) in k, k[:80])
sprawdz("i mowi, ze to punkt startu, nie wyrok",
        "search only for what the record does not settle" in k)
sprawdz("oraz zostawia prawo do obalenia rekordu",
        "not above doubt" in k, k[:120])

print()
print("=== 2. OCENY SEDZIEGO BANKU NIE PRZECIEKAJA ===")
# Q7 z przegladu: `ranga: 3` i „sedzia uznal, ze to najlepszy fakt" to zdania
# NASZEGO modelu, nie dowody. Podane weryfikatorowi wygladalyby jak ustalenia.
for pole in ("ranga", "dlaczego_mocny", "powod", "status", "podobne_do"):
    sprawdz("%s NIE idzie do weryfikatora" % pole, pole not in k, pole)
sprawdz("zdanie sedziego nie przecieklo trescia",
        "najlepszy fakt partii" not in k)

print()
print("=== 3. BEZ REKORDU ZOSTAJE SAM OPIS TYPU ===")
sprawdz("MYSL bez faktu — kontekst jak dotad",
        stages._rekord_do_weryfikacji("MYSL", {}) == "Substack note, type MYSL",
        stages._rekord_do_weryfikacji("MYSL", {}))
sprawdz("pusty rekord tez nie psuje niczego",
        stages._rekord_do_weryfikacji("ARTYKUL", {"fact": {}})
        == "Substack note, type ARTYKUL")
sprawdz("fakt podany plasko (bez zagniezdzenia) tez dziala",
        "https://openai.com/news/pricing"
        in stages._rekord_do_weryfikacji("CIEKAWOSTKA", dict(FAKT)))

print()
print("=== 4. WERYFIKATOR NADAL MOZE SZUKAC — BRAMKA NIE ZNIKA ===")
# Gdyby `szukaj` bylo na stale wylaczone, bramka przestalaby lapac to, czego
# rekord nie obejmuje: zdania dopisane przez pisarza od siebie.
import inspect   # noqa: E402

_zr = inspect.getsource(stages.zweryfikuj)
sprawdz("szukanie jest parametrem, nie zdjete na stale",
        "web_search=szukaj" in _zr, "web_search" in _zr)
sprawdz("i domyslnie jest WLACZONE",
        inspect.signature(stages.zweryfikuj).parameters["szukaj"].default is True)

print()
print("=== 5. MYSL: BEZ SZUKANIA I BEZ NAPRAWY (Q4) ===")
_note = inspect.getsource(stages.note)
sprawdz("MYSL nie wola wyszukiwania",
        'szukaj=(note_type != "MYSL")' in _note)
sprawdz("MYSL nie idzie do naprawy",
        'None if note_type == "MYSL" else napraw_obalone' in _note)
# KONTRDOWOD SFORMULOWANY WPROST: pozostale typy naprawiane byc MAJA.
sprawdz("a pozostale typy nadal sa naprawiane",
        "napraw_obalone(" in _note)

print()
print("=== 6. SEDZIA BANKU NIE RANKUJE TEGO SAMEGO PIEC RAZY (M3) ===")
# ZMIERZONE NA PRODUKCJI 4 wrzesnia 2026: CZTERNASCIE wywolan etapu `bank`
# w jednej dobie, przy banku, ktory zmienia sie najwyzej RAZ na dobe
# (`SZUKANIE_BANKU_NA_DOBE = 1`). `notki_dnia` wolalo `posortuj_bank`
# bezwarunkowo przy kazdym z pieciu przebiegow.
#
# Pieniadze sa tu drugorzedne. Wazniejsze, ze werdykt `wyrzuc` jest TRWALY:
# kazde losowanie to osobna szansa, ze graniczny fakt wypadnie z banku na
# zawsze, a zapory chronia PARTIE, nie pojedynczy wpis.
_wolania = []


def _bank_call(purpose, system, user, **kw):
    _wolania.append(purpose)
    raise RuntimeError("model nie powinien byc wolany")


_stary = stages.llm.call
_stary_indeks = stages.wczytaj_indeks
try:
    stages.llm.call = _bank_call
    # WSZYSTKIE MAJA RANGE -> nie ma po co pytac modelu.
    stages.wczytaj_indeks = lambda: [
        {"status": "nowy", "kiedy": "2099-01-01", "fact": "f%d" % i,
         "ranga": i + 1} for i in range(6)]
    _wolania.clear()
    _w = stages.posortuj_bank(None, None)
    sprawdz("bank bez nowego materialu NIE wola modelu",
            _wolania == [], _wolania)
    sprawdz("i melduje, ze pominal", _w.get("pominiete") == 6, _w)

    # RANGA ZERO TO TEZ RANGA. `ranga` liczy sie od zera, wiec czolowy wpis
    # partii ma 0 — a `not 0` jest prawdziwe. Pierwsza wersja tego warunku
    # sprawdzala falszywosc i uznawala najlepszego kandydata za
    # nierankowanego, wiec wolala sedziego przy KAZDYM przebiegu i nie
    # oszczedzala niczego. Zlapane zywym przebiegiem, nie odczytem kodu.
    stages.wczytaj_indeks = lambda: [
        {"status": "nowy", "kiedy": "2099-01-01", "fact": "f%d" % i,
         "ranga": i} for i in range(6)]          # <- pierwszy ma range 0
    _wolania.clear()
    _w0 = stages.posortuj_bank(None, None)
    sprawdz("ranga 0 liczy sie jako nadana", _wolania == [], _wolania)
    sprawdz("i partia jest pominieta", _w0.get("pominiete") == 6, _w0)

    # KONTRDOWOD: dolozenie JEDNEGO wpisu bez rangi ma ranking wlaczyc.
    stages.wczytaj_indeks = lambda: [
        {"status": "nowy", "kiedy": "2099-01-01", "fact": "f%d" % i,
         "ranga": i + 1} for i in range(5)] + [
        {"status": "nowy", "kiedy": "2099-01-01", "fact": "nowy"}]
    _wolania.clear()
    try:
        stages.posortuj_bank(None, None)
    except RuntimeError:
        pass
    sprawdz("ale JEDEN nowy wpis ranking wlacza",
            _wolania == ["bank"], _wolania)
finally:
    stages.llm.call = _stary
    stages.wczytaj_indeks = _stary_indeks

# SUFIT PARTII PRZED PYTANIEM O RANGE. Ranking obejmuje tylko pierwsze `ile`
# wolnych; liczac range z CALEJ listy, nadwyzka powyzej sufitu nigdy jej nie
# dostaje i warunek bylby prawdziwy zawsze — czyli nie robilby nic.
_zr_bank = inspect.getsource(stages.posortuj_bank)
sprawdz("sufit partii stosowany PRZED pytaniem o range",
        _zr_bank.index("wolni = wolni[:ile]") < _zr_bank.index("bez_rangi = "))

print()
print("=== 7. OPUBLIKOWANY FAKT PRZESTAJE BYC 'NOWY' W INDEKSIE (Q1) ===")
# DWIE KSIEGOWOSCI, KTORE SIE NIE WIDZIALY. Notka bierze fakt dwiema drogami:
# z indeksu (`wez_kandydatow` — ta nadaje status „uzyty") albo ze SWIEZEGO
# szukania (`znajdz_ciekawostki` — ta nie nadaje nic). Po publikacji `run.py`
# dopisywal fakt do `zuzyte_fakty.json`, ktorego `wez_kandydatow` NIE CZYTA,
# a wpis w indeksie zostawal „nowy" — wiec ten sam fakt mogl wyjsc nastepnego
# dnia. Zatrzymywalo go tylko rozmyte porownanie z pamiecia notek: statystyka,
# nie konstrukcja. To ta sama wpadka co dwie notki o jajkach 23 i 24 sierpnia.
stages._zapisz_indeks([
    {"status": "nowy", "kiedy": "2099-01-01",
     "fact": "OpenAI cut the mini tier price by half"},
    {"status": "nowy", "kiedy": "2099-01-01",
     "fact": "a completely different fact about something else"},
])
_ile = stages.oznacz_uzyty({"fact": "OpenAI cut the mini tier price by half"})
_po = stages.wczytaj_indeks()
sprawdz("opublikowany fakt oznaczony", _ile == 1, _ile)
sprawdz("i ma status uzyty", _po[0]["status"] == "uzyty", _po[0]["status"])
sprawdz("a sasiedni wpis NIETKNIETY", _po[1]["status"] == "nowy",
        _po[1]["status"])
sprawdz("data wydania zapisana", bool(_po[0].get("wydany")), _po[0].get("wydany"))

# FAKT ZE SWIEZEGO SZUKANIA nie ma wpisu w indeksie — to nie jest blad.
sprawdz("fakt spoza indeksu nie wywala i nie znaczy nic",
        stages.oznacz_uzyty({"fact": "czegos takiego w indeksie nie ma"}) == 0)
sprawdz("pusty fakt tez nie wywala", stages.oznacz_uzyty({"fact": ""}) == 0)
sprawdz("i sam napis dziala tak samo jak slownik",
        stages.oznacz_uzyty("a completely different fact about something else")
        == 1)

# KOD PUBLIKUJACY NAPRAWDE TO WOLA. Sama funkcja nic nie znaczy, jesli
# `run.py` jej nie uzywa — to ta sama rodzina wad, co martwy wpis EFFORT.
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("run.py odhacza fakt w indeksie po publikacji",
        "stages.oznacz_uzyty(n[\"fakt\"])" in _run)
sprawdz("i robi to obok zapisz_zuzyte, nie zamiast",
        "stages.zapisz_zuzyte([n[\"fakt\"]])" in _run)

# KAZDY ROZWAZANY MA WYJSC Z RANGA. Model potrafi oddac kolejnosc KROTSZA niz
# partia — zmierzone na zywo: 11 pozycji na 12 wyslanych. Pominiety wpis
# zostawal bez rangi na zawsze i przy nastepnym przebiegu znowu wlaczal
# ranking, wiec oszczednosc z warunku wyzej bylaby zerowa.
sprawdz("pominiete przez model dostaja range na koncu kolejki",
        "_dol = len(kolejnosc)" in _zr_bank
        and 'k["ranga"] = _dol' in _zr_bank)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
