# -*- coding: utf-8 -*-
"""Model przepytuje material, ZANIM napisze notke.

DLACZEGO TO POWSTALO — decyzja wlasciciela z 9 wrzesnia 2026, po przeczytaniu
wlasnego konta: „chcialbym zeby model jak przeczyta info na jakis temat zadal
sobie pytania na jego temat i odpowiedzial sobie na nie, wyciagnal wnioski (…)
a nie tylko wystawil suchy fakt".

CO POKAZAL POMIAR NA 96 OPUBLIKOWANYCH NOTKACH. Konto ani razu nie nazwalo
niczego dziwnym (`strange` 0, `funny` 0, `absurd` 0), raz zapytalo „dlaczego",
a 17 razy kazalo czytelnikowi cos POLICZYC. Przyczyna nie byla stylistyczna,
tylko strukturalna, i siedziala w dwoch miejscach:

  * regula 4 promptu kazala KAZDA notke zamykac czyms, co czytelnik moze dzis
    obejrzec, policzyc albo porownac — dobre zakonczenie, ale jako JEDYNE
    zrobilo z konta nauczyciela rozdajacego cwiczenia;
  * miedzy „mamy fakt" a „piszemy notke" nie bylo ETAPU MYSLENIA. Karta faktu
    jest bogata, ale kazde jej pole material OPISUJE i zadne go nie OCENIA,
    wiec pisarz mial komplet danych i zero zdania na ich temat — a bez zdania
    da sie napisac tylko wyjasnienie.

Ksztalty notek (`config.NOTE_FORMS`) obracaly sie przy tym POPRAWNIE — w 14
dniach wyszlo 20 roznych par typ/forma. Monotonia nie byla wiec mechaniczna
i przestawianie rotacji niczego by nie dalo. To sprawdzono PRZED zmiana.

CZEGO TEN TEST PILNUJE:

  1. rozbior idzie PRZED pisaniem, na tym samym materiale
  2. jego wynik naprawde trafia do promptu notki
  3. brak polaczenia albo blad modelu NIE zabija notki (zawodzi na pusto)
  4. prompt notki dzieli material na FAKTY i SAD — bez tej granicy etap byl
     by maszynka do wymyslania liczb
  5. `ostatnie_zakonczenia` czyta CALE ostatnie zdanie i pomija adres, bo
     powtarza sie ruch, a nie slowo
  6. regula jednego finalu naprawde zniknela z promptu

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_rozbior_przed_notka.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

KATALOG = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KATALOG)

import llm      # noqa: E402
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
        print("  PADA  %s%s" % (opis, (" — " + dodatek) if dodatek else ""))


MATERIAL = {
    "fact": "A lab says it has settled one of the Millennium Prize problems.",
    "wrong_belief": "Machines cannot do original mathematics.",
    "url": "https://example.invalid/proof",
}

ROZBIOR_MODELU = {
    "w_prostych_slowach": "A prize problem is a maths question left open"
                          " for decades with money attached to it.",
    "skala": "",
    "pytania": [
        {"pytanie": "What does settled mean here?",
         "odpowiedz": "The material does not say whether anyone checked it.",
         "z_dowodu": True},
        {"pytanie": "Is this a machine doing maths, or helping?",
         "odpowiedz": "Reading the phrasing, it is assistance.",
         "z_dowodu": False},
    ],
    "jesli_sie_utrzyma": "Proof assistants stop being a niche tool.",
    "gdzie_by_peklo": "Nobody has verified the proof yet.",
    "co_o_tym_sadze": "The announcement is doing more work than the result.",
    "czego_nie_wiadomo": ["who checked the proof"],
}


class AtrapaConn:
    """Cokolwiek nie-None. Krzyczy, gdy kod czegos od niej chce.

    Szosty raz w tym projekcie niepelna atrapa udawala usterke kodu.
    """

    def __getattr__(self, nazwa):
        raise AssertionError("kod siega po conn.%s — atrapa tego nie ma" % nazwa)


def przechwyc(odpowiedzi, wyjatek_na=()):
    """Podstawia `llm.call` i zbiera (etapy, prompty)."""
    etapy, prompty = [], {}

    def podstawiony(purpose, system, prompt, **kw):
        etapy.append(purpose)
        prompty[purpose] = prompt
        if purpose in wyjatek_na:
            raise RuntimeError("zerwane polaczenie")
        return json.dumps(odpowiedzi.get(purpose, {}))

    return podstawiony, etapy, prompty


print("=== 1. rozbior idzie PRZED pisaniem, na tym samym materiale ===")
podstawiony, etapy, prompty = przechwyc({
    "rozbior": ROZBIOR_MODELU,
    "note": {"note": "x " * 50, "words": 50, "fact_used": "f",
             "source_url": "https://example.invalid/proof"},
})
oryginal = llm.call
llm.call = podstawiony
try:
    stages.note(AtrapaConn(), 1, "CIEKAWOSTKA", dict(MATERIAL))
except Exception as e:                                        # noqa: BLE001
    print("     (pisanie przerwane: %s — sprawdzam co zdazylo pasc)" % e)
finally:
    llm.call = oryginal

sprawdz("rozbior zostal wywolany", "rozbior" in etapy, "etapy=%r" % etapy)
sprawdz("i wywolany PRZED pisaniem notki",
        "rozbior" in etapy and "note" in etapy
        and etapy.index("rozbior") < etapy.index("note"),
        "etapy=%r" % etapy)
sprawdz("rozbior dostal ten sam material, co pisarz",
        "Millennium" in prompty.get("rozbior", ""))

print()
print("=== 2. wynik rozbioru trafia do promptu notki ===")
_notka = prompty.get("note", "")
sprawdz("stanowisko modelu jest w promptcie pisarza",
        "The announcement is doing more work" in _notka)
sprawdz("miejsce, w ktorym rzecz moze peknac, tez",
        "Nobody has verified the proof yet" in _notka)
sprawdz("i to, czego material nie rozstrzyga",
        "who checked the proof" in _notka)

print()
print("=== 3. brak polaczenia i blad modelu NIE zabijaja notki ===")
# Bez `conn` rozbior nie ma kogo zapytac.
sprawdz("bez conn rozbior oddaje pustke, nie wyjatek",
        stages.rozbior(None, None, dict(MATERIAL)) == {})

podstawiony, etapy2, prompty2 = przechwyc(
    {"note": {"note": "x " * 50, "words": 50, "fact_used": "f",
              "source_url": "https://example.invalid/proof"}},
    wyjatek_na=("rozbior",))
llm.call = podstawiony
try:
    stages.note(AtrapaConn(), 1, "CIEKAWOSTKA", dict(MATERIAL))
except Exception:                                             # noqa: BLE001
    pass
finally:
    llm.call = oryginal
sprawdz("po bledzie rozbioru pisarz i tak zostal wywolany",
        "note" in etapy2, "etapy=%r" % etapy2)
sprawdz("i wie, ze rozbioru nie ma",
        "(brak" in prompty2.get("note", ""))

print()
print("=== 3b. pusty budzet i wylacznik ZATRZYMUJA, a nie sa polykane ===")
# Pierwsza wersja lapala `BudgetExceeded` razem z reszta bledow i przez to
# OBCHODZILA ZAPORE BUDZETU: przy wyczerpanym budzecie rozbior wypisywal
# linijke, a notka szla dalej. To samo dotyczy `KILL_SWITCH`, ktory zglasza
# sie jako `PreflightFailed`. Zlapane przez `test_pusty_budzet_nie_sprawdza`.
for _klasa, _opis in ((llm.BudgetExceeded, "pusty budzet"),
                      (llm.PreflightFailed, "wylacznik")):
    def _rzuca(purpose, *a, **k):
        raise _klasa("proba")

    _oryg = llm.call
    llm.call = _rzuca
    try:
        stages.rozbior(AtrapaConn(), 1, dict(MATERIAL))
        _wynik = "POLKNIETE"
    except _klasa:
        _wynik = "leci dalej"
    except Exception as _e:                                   # noqa: BLE001
        _wynik = "inny wyjatek: %s" % type(_e).__name__
    finally:
        llm.call = _oryg
    sprawdz("%s leci z rozbioru na wylot" % _opis, _wynik == "leci dalej",
            "rozbior zrobil: %s" % _wynik)

print()
print("=== 4. prompt dzieli material na FAKTY i SAD ===")
# Bez tej granicy etap bylby maszynka do wymyslania liczb: model pytany
# „jak duze to jest" zawsze cos odpowie.
_zr = pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8")
sprawdz("sad nazwany sadem, nie faktem",
        "judgement,\nnot fact" in _zr or "judgement, not fact" in _zr)
sprawdz("i zakaz podawania go jako liczby albo zdarzenia",
        "never state it as" in _zr)
_ro = pathlib.Path("agent-v2/prompts/rozbior.md").read_text(encoding="utf-8")
sprawdz("rozbior zabrania porownan z pamieci modelu",
        "comparison you supply from your own memory" in _ro)
sprawdz("pusta skala jest DOZWOLONA jako odpowiedz",
        "An empty" in _ro and "is a good answer" in _ro)

print()
print("=== 5. ostatnie zakonczenia: cale zdanie, bez adresu ===")
(KATALOG / "dziennik.jsonl").write_text(
    "\n".join(json.dumps(w, ensure_ascii=False) for w in [
        {"rodzaj": "notka", "tekst": "One thing. Count the crowds you stood in."},
        {"rodzaj": "notka",
         "tekst": "Another thing. The filter is in front.\nhttps://x.invalid/p"},
        {"rodzaj": "komentarz", "tekst": "Nie ta rzecz. Pomijamy."},
    ]), encoding="utf-8")
konce = stages.ostatnie_zakonczenia()
sprawdz("bierze cale ostatnie zdanie, nie pierwsze slowo",
        konce and konce[0] == "Count the crowds you stood in.",
        "konce=%r" % konce)
sprawdz("adres na koncu pomijany — liczy sie zdanie przed nim",
        len(konce) > 1 and konce[1] == "The filter is in front.",
        "konce=%r" % konce)
sprawdz("komentarze nie wchodza miedzy notki", len(konce) == 2,
        "konce=%r" % konce)

print()
print("=== 6. jedyny dozwolony final naprawde zniknal ===")
sprawdz("zakonczenia sa WYBOREM, nie nakazem",
        "The endings available to you" in _zr)
sprawdz("model widzi, czym konczyly sie poprzednie notki",
        "{ostatnie_zakonczenia_json}" in _zr)
sprawdz("zakaz zadawania pracy domowej zostal",
        "nobody does homework from a feed" in _zr)
sprawdz("konto ma prawo miec zdanie",
        "you are allowed to think something" in _zr.lower())

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
