# -*- coding: utf-8 -*-
"""Notka nie dostaje formy, ktorej jej typ wykonac nie moze.

CO SIE STALO. Forma byla przydzielana z dryfu dnia roku, NIEZALEZNIE od typu.
Komentarz przy tym kodzie mowil to wprost jako zalete: „po osmiu dniach kazda
para typ-forma zdazy wystapic". Tyle ze czesc par jest nie do wykonania.

Opis typu MYSL brzmi: „NO EVIDENCE CARD, and therefore NO FACTS: no number, no
date, no named company doing a named thing, no study, no percentage". A formy
mowia:

    LICZBA            „Open with the number itself"
    LISTA             „EVERY line must carry a fact"
    KONTRAST          „Two facts set against each other"
    ODWROCENIE        „the record that contradicts it"
    PYTANIE           „Deliver the whole fact first"
    ZACZEP_I_KONKRET  „what the arrangement actually is and who decided"

ZMIERZONE 5 wrzesnia 2026 na rotacji z calego roku: 730 z 1095 przydzialow
MYSL, czyli 67% — DWA NA TRZY — dawalo forme zadajaca tego, czego typ zabrania.
Model dostawal dwa polecenia nie do pogodzenia i musial ktores zlamac.
Najczesciej zakaz faktow, bo forma opisuje KSZTALT, ktory widac, a zakaz jest
niewidzialny — czyli wynikiem byla notka MYSL ze zmyslona liczba.

CZEGO TEN TEST PILNUJE:
  1. zadna para typ-forma niewykonalna juz nie wypada;
  2. roznorodnosc NIE ZNIKA: typy bez wykluczen nadal dostaja pelna rotacje,
     a typ z wykluczeniami rotuje rowno po tym, co mu zostalo;
  3. rozklad nie jest skosny — pierwsza wersja tej poprawki „szla dalej az do
     wykonalnej" i zbierala piec odrzuconych na jednej formie (WYJASNIENIE
     wychodzilo w 56%), czyli robila nowy szablon zamiast rownowagi;
  4. wykluczenia obejmuja WYLACZNIE formy zadajace wprost rzeczy zakazanej
     w typie — lista nie ma prawa rosnac o podejrzenia.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_forma_wykonalna_dla_typu.py
"""
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

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


def przydziel(dryf, typy, od=0):
    """Powtarza logike z `stages.notki_dnia` — na wypadek, gdyby ktos ja
    uproscil z powrotem do jednej linii bez sprawdzania typu."""
    out = []
    for i, t in enumerate(typy):
        zle = config.FORMY_NIEMOZLIWE.get(t, frozenset())
        mozliwe = [f for f in config.NOTE_FORM_MIX if f not in zle]
        if not mozliwe:
            mozliwe = list(config.NOTE_FORM_MIX)
        out.append(mozliwe[(dryf + od + i) % len(mozliwe)])
    return out


print("=== 1. PRZEZ CALY ROK ZADNA PARA NIEWYKONALNA ===")
zle = 0
per_typ: dict[str, Counter] = {}
for dzien in range(1, 366):
    for dzien_art in (True, False):
        typy = list(config.NOTE_MIX_ARTICLE_DAY if dzien_art
                    else config.NOTE_MIX_OTHER_DAY)
        for t, f in zip(typy, przydziel(dzien, typy)):
            per_typ.setdefault(t, Counter())[f] += 1
            if f in config.FORMY_NIEMOZLIWE.get(t, frozenset()):
                zle += 1
sprawdz("zero niewykonalnych par w calym roku", zle == 0, zle)

print()
print("=== 2. ROZNORODNOSC NIE ZNIKA ===")
_mysl = per_typ.get("MYSL", Counter())
_dozwolone = [f for f in config.NOTE_FORM_MIX
              if f not in config.FORMY_NIEMOZLIWE["MYSL"]]
sprawdz("MYSL dostaje KAZDA z form, ktore moze wykonac",
        set(_mysl) == set(_dozwolone), (sorted(_mysl), sorted(_dozwolone)))
_ciek = per_typ.get("CIEKAWOSTKA", Counter())
sprawdz("typ bez wykluczen nadal dostaje PELNA rotacje",
        set(_ciek) == set(config.NOTE_FORM_MIX), sorted(_ciek))

print()
print("=== 3. ROZKLAD JEST ROWNY, NIE SKOSNY ===")
# Pierwsza wersja poprawki dawala WYJASNIENIE w 56% przypadkow MYSL, bo
# zbierala wszystkie odrzucone na nastepnej dozwolonej formie w kolejce.
_naj = max(_mysl.values()) / sum(_mysl.values())
sprawdz("zadna forma MYSL nie przekracza polowy przydzialow",
        _naj < 0.5, "%.0f%%" % (100 * _naj))
sprawdz("i mieszcza sie blisko rownego udzialu",
        _naj < 1.5 / len(_dozwolone), "%.2f" % _naj)

print()
print("=== 4. LISTA WYKLUCZEN NIE ROSNIE O PODEJRZENIA ===")
# Kazda pozycja ma miec pokrycie w OPISIE FORMY: zada faktu, liczby, dokumentu
# albo nazwanego decydenta. Bez tego wykluczenie jest gustem, nie sprzecznoscia.
DOWODY = {
    "LICZBA": "Open with the number",
    "LISTA": "must carry a fact",
    "KONTRAST": "Two facts",
    "ODWROCENIE": "the record that contradicts",
    "PYTANIE": "Deliver the whole fact",
    "ZACZEP_I_KONKRET": "who de",
}
for f in sorted(config.FORMY_NIEMOZLIWE["MYSL"]):
    opis = str(config.NOTE_FORMS.get(f, ""))
    sprawdz("wykluczenie %s ma pokrycie w opisie formy" % f,
            DOWODY.get(f, "\x00") in opis, opis[:70])
sprawdz("a typ MYSL faktycznie zabrania faktow",
        "NO FACTS" in str(config.NOTE_TYPES.get("MYSL", "")))
sprawdz("wykluczenia dotycza na razie WYLACZNIE mysli",
        set(config.FORMY_NIEMOZLIWE) == {"MYSL"},
        sorted(config.FORMY_NIEMOZLIWE))

print()
print("=== 5. KOD NAPRAWDE TAK ROBI ===")
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("stages pyta o FORMY_NIEMOZLIWE przy przydziale",
        "config.FORMY_NIEMOZLIWE.get(_typ" in _zr)
sprawdz("i rotuje po LISCIE WYKONALNYCH, nie po pelnej z pomijaniem",
        "_mozliwe[(_dryf + od + i) % len(_mozliwe)]" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
