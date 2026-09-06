# -*- coding: utf-8 -*-
"""Sprawdzenie faktow artykulu widzi karte, a nie sam tytul.

CO ZGLASZA AUDYT (M1, czesc o artykule). „Sprawdzenie faktow szuka od zera
tego, co potok juz ma." Przy notkach zamknieto to dzis
(`_rekord_do_weryfikacji`), ale `artykul_z_puli` wolalo

    stages.zweryfikuj(conn, run_id, draft["body"], draft.get("title", ""))

czyli weryfikator dostawal SAM TYTUL. Karta z `confirmed_claims` — kazde
z wyciagiem ze zrodla, adresem i werdyktem, pobrane i oplacone kilka minut
wczesniej — nie docierala do niego wcale.

CO ZMIERZYLEM, ZANIM TO RUSZYLEM. Sprawdzanie faktow to 9,2% rachunku
(3,364 USD na 36,43 USD w 14 dni), czyli audyt przeszacowal je ~3x — wlasny
prog audytu („zdrowo: <25%") jest spelniony. Nie robie tego wiec DLA PIENIEDZY.
Robie dla jakosci: weryfikator bez karty kwestionuje zdania, ktore karta
wprost potwierdza, a przy artykule kazde zastrzezenie idzie do dziennika
i do oceny formy.

CZEGO TA NAPRAWA NIE MOZE ZROBIC — i to jest tu najwazniejsze. Kontrdowod
audytu brzmi: „Udzial refuted w claims NIE MOZE SPASC; jesli spadnie,
weryfikator zaczal ufac rekordowi zamiast go sprawdzac i zmiane trzeba cofnac."
Dlatego kontekst mowi wprost, ze karta nie jest ponad watpliwoscia, a
twierdzenie `not_fetched` — jedyne, ktorego nikt nie pobral — jest OZNACZONE.
Bez tej etykiety naprawa zjadlaby wlasny sens: weryfikator uznalby wpis
dolozony z puli za sprawdzony i przestal go sprawdzac.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_karta_idzie_do_weryfikatora.py
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


KARTA = {
    "confirmed_claims": [
        {"claim": "The agency set the threshold at 12 units.",
         "evidence": "the published rule fixes the threshold at 12 units",
         "url": "https://pula.example/fakt", "not_fetched": True},
        {"claim": "Seven operators filed the same fault report.",
         "evidence": "7 operators filed the same fault report in March 2026",
         "url": "https://pobrane.example/raport"},
        {"claim": "The register lists 41 exemptions.",
         "evidence": "41 exemptions are recorded in the annex",
         "url": "https://rejestr.example/annex"},
    ],
}

kontekst = stages.karta_do_weryfikacji("A Title About Thresholds", KARTA)

print("=== 1. TYTUL ZOSTAJE, KARTA DOCHODZI ===")
sprawdz("tytul nadal jest", kontekst.startswith("A Title About Thresholds"))
sprawdz("kazde twierdzenie z karty jest w kontekscie",
        all(c["claim"][:30] in kontekst for c in KARTA["confirmed_claims"]))
sprawdz("razem z wyciagiem ze zrodla",
        "7 operators filed the same fault report" in kontekst)
sprawdz("i z adresem", "https://pobrane.example/raport" in kontekst)

print()
print("=== 2. WERYFIKATOR MA SZUKAC TYLKO TEGO, CZEGO KARTA NIE ROZSTRZYGA ===")
sprawdz("kontekst mowi, skad wzial sie tekst",
        "The article was written from this evidence card" in kontekst)
sprawdz("i kaze zaczac od karty",
        "Check the text against the card FIRST" in kontekst)
sprawdz("i szukac tylko reszty",
        "search only for what the card does not settle" in kontekst)

print()
print("=== 3. KARTA NIE JEST PONAD WATPLIWOSCIA ===")
# Kontrdowod audytu: udzial `refuted` nie moze spasc. Jesli spadnie,
# weryfikator zaczal ufac karcie zamiast ja sprawdzac.
sprawdz("wprost napisane, ze karta moze byc bledna",
        "The card is not above doubt" in kontekst)
sprawdz("z poleceniem, zeby to powiedziec", "if an entry is wrong, say so"
        in kontekst)

print()
print("=== 4. NIEPOBRANE TWIERDZENIE JEST OZNACZONE ===")
# Bez tego naprawa zjadlaby wlasny sens: wpis dolozony z puli wygladalby na
# sprawdzony. Patrz `test_fakt_niepobrany_widoczny.py`.
sprawdz("wpis not_fetched ma etykiete", "NOT FETCHED" in kontekst)
_linia = [w for w in kontekst.splitlines() if "12 units." in w]
sprawdz("etykieta stoi przy WLASCIWYM twierdzeniu",
        _linia and "NOT FETCHED" in _linia[0], _linia)
sprawdz("a pobrane twierdzenia jej NIE maja",
        all("NOT FETCHED" not in w for w in kontekst.splitlines()
            if "fault report." in w))
sprawdz("i jest wyjasnione, co ta etykieta znaczy",
        "is not a quotation from any document we opened" in kontekst)

print()
print("=== 5. SUFITY, BO KONTEKST IDZIE PRZY KAZDYM SPRAWDZENIU ===")
DUZA = {"confirmed_claims": [
    {"claim": "Claim number %d about something." % i,
     "evidence": "x" * 900, "url": "https://e.example/%d" % i}
    for i in range(30)]}
_duzy = stages.karta_do_weryfikacji("T", DUZA)
sprawdz("liczba twierdzen obcieta",
        _duzy.count("- claim:") == stages.MAKS_TWIERDZEN_DO_WERYFIKACJI,
        _duzy.count("- claim:"))
sprawdz("wyciag obciety do 400 znakow", "x" * 401 not in _duzy)

print()
print("=== 6. BRAK KARTY NIC NIE PSUJE ===")
# `--z-karty` i sciezki bez karty maja dzialac jak dotad: sam tytul.
sprawdz("pusta karta oddaje sam tytul",
        stages.karta_do_weryfikacji("Sam tytul", {}) == "Sam tytul")
sprawdz("None tak samo",
        stages.karta_do_weryfikacji("Sam tytul", None) == "Sam tytul")
sprawdz("karta bez twierdzen tak samo",
        stages.karta_do_weryfikacji("Sam tytul",
                                    {"confirmed_claims": []}) == "Sam tytul")
sprawdz("smiec w twierdzeniach nie wywala",
        stages.karta_do_weryfikacji(
            "T", {"confirmed_claims": ["napis", None, {}]}) == "T")

print()
print("=== 7. PRODUKCJA NAPRAWDE PRZEZ TO PRZECHODZI ===")
_azp = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
_kod = chr(10).join(w for w in _azp.splitlines()
                    if not w.lstrip().startswith("#"))
sprawdz("artykul wola weryfikacje z karta",
        "stages.karta_do_weryfikacji(draft.get(\"title\", \"\"), card)" in _kod)
sprawdz("i nie podaje juz samego tytulu",
        'zweryfikuj(conn, run_id, draft["body"], draft.get("title", ""))'
        not in _kod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
