# -*- coding: utf-8 -*-
"""Nota o wieku nie idzie do pisarza, gdy material jest swiezy.

DWA ARTYKULY Z RZEDU ZGINELY NA TYM SAMYM ZDANIU, 30 sierpnia 2026. Oba mialy
kazde twierdzenie o TEMACIE potwierdzone zrodlami pierwotnymi. Oba zatrzymala
bramka faktow przed publikacja — i za kazdym razem na zdaniu o NASZYCH
ZRODLACH, nie o temacie.

    karta:   „Only METR's URL carries an explicit publication date;
              the other sources are undated in the excerpts."
    tekst 1: „the OpenAI, Hugging Face and CyberScoop accounts are undated"
    tekst 2: „only METR's carries an explicit publication date; the passages
              we rely on (...) reached us undated"
    bramka:  „the OpenAI, Hugging Face and CyberScoop accounts ALL carry
              explicit dates"

PROSBA W PROMPCIE NIE WYSTARCZYLA — I TO JEST SEDNO TEGO TESTU. Po pierwszej
porazce poprawilem regule w `pisarz.md`. Drugi tekst i tak poleglal, bo zdanie
ma DWIE polowy, a zakwalifikowana zostala tylko druga. „Ktore zrodlo ma date"
jest twierdzeniem o cudzych dokumentach zawsze, niezaleznie od opakowania.

ZRODLO PROBLEMU LEZY NIZEJ. Tabela `sources` nie ma kolumny z data — potok
nigdy nie wyciaga daty publikacji. Synteza widzi wyciagi, nie widzi w nich daty
i melduje to uczciwie. To zdanie o NASZYM POBIERANIU, nie o swiecie.

A zastrzezenie nie bylo nawet potrzebne: `newest` w tej karcie to 2026-08-26,
czyli material mial CZTERY DNI.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo.
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


TERAZ = datetime(2026, 8, 30, tzinfo=timezone.utc)

# KARTA PRZEPISANA Z PRODUKCJI, nie wymyslona — to ta, ktora zabila dwa teksty.
KARTA_SWIEZA = {
    "working_thesis": "Guardrails were removed because removing them was the test.",
    "confirmed_claims": [{"claim": "x", "evidence": "y", "url": "https://metr.org/z"}],
    "source_dates": {
        "newest": "2026-08-26",
        "oldest": "unknown",
        "note": ("Only METR's URL carries an explicit publication date; "
                 "the other sources are undated in the excerpts."),
    },
}

print("=== 1. SWIEZY MATERIAL — NOTA NIE IDZIE DO PISARZA ===")
czysta = stages.karta_dla_pisarza(KARTA_SWIEZA, teraz=TERAZ)
sprawdz("nota wyczyszczona",
        czysta["source_dates"]["note"] == "",
        repr(czysta["source_dates"]["note"])[:80])
sprawdz("ale daty zostaja — pisarz ma czym ostemplowac tekst",
        czysta["source_dates"]["newest"] == "2026-08-26")
sprawdz("reszta karty nietknieta",
        czysta["confirmed_claims"] == KARTA_SWIEZA["confirmed_claims"]
        and czysta["working_thesis"] == KARTA_SWIEZA["working_thesis"])

print()
print("=== 2. ORYGINAL NIE JEST ZMIENIANY ===")
# Karta idzie takze do bazy i do recenzenta. Gdyby czyszczenie mutowalo
# oryginal, skasowalibysmy informacje wszedzie, nie tylko w pisaniu.
sprawdz("karta wejsciowa nadal ma note",
        KARTA_SWIEZA["source_dates"]["note"].startswith("Only METR"))

print()
print("=== 3. STARY MATERIAL — NOTA IDZIE, BO SIE NALEZY ===")
# Cel tej noty jest prawdziwy: „ukrycie zastrzezenia jest gorsze niz wiek".
# Poprawka nie moze go zabic, inaczej zamieniamy jeden blad na drugi.
stara = dict(KARTA_SWIEZA, source_dates=dict(KARTA_SWIEZA["source_dates"],
                                             newest="2025-01-10"))
wynik = stages.karta_dla_pisarza(stara, teraz=TERAZ)
sprawdz("nota zachowana przy materiale sprzed roku",
        wynik["source_dates"]["note"].startswith("Only METR"))

print()
print("=== 4. NIEZNANY WIEK — TEZ IDZIE ===")
# „Nie wiem, ile to ma lat" to nie to samo co „jest swieze". Koszt pomylki
# jest niesymetryczny: przepuszczony stary tekst kosztuje wiarygodnosc.
nieznana = dict(KARTA_SWIEZA,
                source_dates=dict(KARTA_SWIEZA["source_dates"], newest="???"))
sprawdz("nota zachowana, gdy `newest` sie nie parsuje",
        stages.karta_dla_pisarza(nieznana, teraz=TERAZ)
        ["source_dates"]["note"].startswith("Only METR"))

print()
print("=== 5. KARTY BEZ DAT NIE PSUJEMY ===")
for opis, karta in (("brak source_dates", {"working_thesis": "x"}),
                    ("source_dates nie jest slownikiem",
                     {"source_dates": "2026"}),
                    ("pusta nota", {"source_dates": {"newest": "2026-08-26",
                                                     "note": ""}})):
    wy = stages.karta_dla_pisarza(karta, teraz=TERAZ)
    sprawdz("  %s -> oddane bez zmian" % opis, wy == karta)

print()
print("=== 6. WPIETE W PISANIE, A NIE W RECENZJE ===")
import pathlib
zrodlo = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
i_write = zrodlo.index("\ndef write(")
i_koniec = zrodlo.index("\ndef ", i_write + 10)
blok_write = zrodlo[i_write:i_koniec]
sprawdz("pisarz dostaje karte przycieta",
        "karta_dla_pisarza(card)" in blok_write)
i_rev = zrodlo.index("\ndef review(")
blok_rev = zrodlo[i_rev:zrodlo.index("\ndef ", i_rev + 10)]
# RECENZENT MA WIDZIEC WSZYSTKO. On nie pisze tekstu, tylko sprawdza go
# wobec materialu — przyciecie zabraloby mu informacje bez powodu.
sprawdz("recenzent dostaje karte PELNA",
        "karta_dla_pisarza" not in blok_rev)

print()
print("=== 7. KONTRDOWOD: BEZ POPRAWKI ZDANIE DOCHODZI DO PISARZA ===")
# Gdyby test przechodzil takze na kodzie sprzed poprawki, nie mierzylby nic.
po_staremu = json.dumps(KARTA_SWIEZA, ensure_ascii=False)
po_nowemu = json.dumps(stages.karta_dla_pisarza(KARTA_SWIEZA, teraz=TERAZ),
                       ensure_ascii=False)
sprawdz("stara droga niesie zdanie o cudzych datach",
        "undated in the excerpts" in po_staremu)
sprawdz("nowa juz nie",
        "undated in the excerpts" not in po_nowemu)

print()
print("=== 8. PROG JEST TYM SAMYM, CO W BRAMCE WIEKU ===")
# Dwie liczby na to samo pytanie rozjezdzaja sie w koncu zawsze.
# ZAKRES LICZONY DO KONCA FUNKCJI, NIE DO 2600 ZNAKU. Pierwotnie stalo tu
# okno o stalej dlugosci i pekalo przy kazdym dopisanym komentarzu — 5 wrzesnia
# 2026 oblalo sie po dolozeniu akapitu o `ocena_ciekawosci`, chociaz stala
# byla na miejscu. Test, ktory reaguje na dlugosc komentarza zamiast na tresc
# kodu, myli czujnosc z halasem.
_od = zrodlo.index("def karta_dla_pisarza")
_do = zrodlo.find(chr(10) + "def ", _od + 1)
_cialo = zrodlo[_od:_do if _do > 0 else len(zrodlo)]
sprawdz("uzywamy MAKS_WIEK_ZRODLA_DNI",
        "config.MAKS_WIEK_ZRODLA_DNI" in _cialo,
        config.MAKS_WIEK_ZRODLA_DNI)

print()
print("=== OCENA PRZYDATNOSCI NIE IDZIE DO PISARZA ===")
# `ocena_ciekawosci` to caly wynik etapu `warto_pisac`: werdykt, powody
# i wskazowka ratunku. Szla do pisarza razem z karta dowodowa, a `pisarz.md`
# nie odwoluje sie do tego pola ANI RAZU — wiec nie byla do niczego uzywana.
#
# Gorzej niz bezuzyteczna: przy werdykcie ODLOZ model z zadaniem „napisz"
# dostawal obok wyjasnienie, ze material nie daje czytelnikowi powodu do
# zainteresowania. To konkurencyjne zadanie, ktore zacheca do asekuracji albo
# do metakomentarza o slabosci wlasnego materialu.
#
# TRZY SCIEZKI, BO SA TRZY WYJSCIA Z TEJ FUNKCJI. Pierwsza wersja poprawki
# stala przy koncowym `return` i nie robila nic w dwoch z nich.
for _opis, _karta in (
        ("swieza karta z nota o dacie",
         {"source_dates": {"newest": "2099-01-01", "note": "uwaga"}}),
        ("karta bez noty o dacie",
         {"source_dates": {"newest": "2099-01-01", "note": ""}}),
        ("karta ze starym zrodlem",
         {"source_dates": {"newest": "2020-01-01", "note": "uwaga"}}),
):
    _k = dict(_karta, ocena_ciekawosci={"werdykt": "ODLOZ",
                                        "powod": "nie ma tu ciekawosci"},
              unused_evidence=[{"fragment": "material"}],
              confirmed_claims=[{"id": 1}])
    _w = stages.karta_dla_pisarza(_k)
    sprawdz("%s — ocena NIE dochodzi" % _opis,
            "ocena_ciekawosci" not in _w, sorted(_w))
    sprawdz("%s — material zostaje" % _opis,
            "unused_evidence" in _w and "confirmed_claims" in _w, sorted(_w))
    # KARTA ZAPISYWANA NA DYSK MA ZOSTAC BOGATA — zmieniamy widok pisarza,
    # a nie archiwum.
    sprawdz("%s — oryginal nietkniety" % _opis, "ocena_ciekawosci" in _k)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
