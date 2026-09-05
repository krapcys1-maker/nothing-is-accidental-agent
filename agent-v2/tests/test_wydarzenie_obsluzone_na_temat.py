# -*- coding: utf-8 -*-
"""Wydarzenie zamyka sie materialem O NIM, nie czymkolwiek z tej samej partii.

CO SIE DZIALO (S2 z audytu researchu, potwierdzone na produkcji).
Do `_zapamietaj_wydarzenia` szla JEDNA liczba na cala partie i trafiala do
KAZDEGO nowego wydarzenia. Wydarzenie mogl wiec zamknac material na zupelnie
inny temat, a furtka „to jest nowe, wolno poszukac" zostawala zatrzasnieta.

DWA ZMIERZONE PRZYPADKI, oba z produkcyjnego pliku pamieci:

  * 2 wrzesnia 2026: `"5.1,fable": {"ile": 5}` — premiera Fable 5.1, modelu,
    ktorym SAMI piszemy artykuly, uznana za obsluzona piecioma faktami
    o OpenAI i SpaceX, kontroli eksportu BIS, modelu Astra i Apple Siri.
    Ani jedno slowo o Fable; w banku ani jeden fakt, na koncie ani jedna notka.
  * 3 wrzesnia 2026: `"astra,gpt-6": {"ile": 2}` — wydarzenie NIE bedace
    premiera, o ktorym mowily cztery kanaly, zamkniete dwojka bedaca liczba
    WSZYSTKICH faktow tamtego przebiegu.

Pierwszy przypadek poprawiono 3 wrzesnia, ale WYLACZNIE dla premiery. Drugi
pokazuje, ze reszta zdarzen zostala z ta sama wada — i to jest ta poprawka.

CZEGO TEN TEST PILNUJE:
  1. fakty o czym innym NIE zamykaja wydarzenia;
  2. fakty o nim — zamykaja;
  3. dwa wydarzenia w jednej partii dostaja WLASNE liczby, a nie wspolna;
  4. zero nie zatrzaskuje furtki, tylko podbija licznik prob;
  5. pomiar w logu i decyzja o zamknieciu licza TAK SAMO — jedna funkcja,
     bo dwie kopie tego samego liczenia rozjezdzaja sie zawsze. To wlasnie
     rozjazd miedzy nimi byl pierwotna przyczyna: `_ile_prem` bylo liczone
     poprawnie i tylko DRUKOWANE, a do decyzji szlo `len(fakty)`.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_wydarzenie_obsluzone_na_temat.py
"""
import json
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


ASTRA = {"o_czym": ["astra", "gpt-6"], "premiera": False}
FABLE = {"o_czym": ["5.1", "fable"], "premiera": True}

OBCE = [{"fact": "Warehouse robots swap batteries in four minutes"},
        {"fact": "A retail chain cut queue times by half"}]
O_ASTRZE = [{"fact": "GPT-6 Astra's system card reports lower monitorability"},
            {"fact": "The UK institute evaluated gpt-6 astra in a sandbox"}]

print("=== 1. LICZYMY MATERIAL O TYM WYDARZENIU, NIE CALA PARTIE ===")
sprawdz("fakty o czym innym daja zero",
        stages.faktow_o_wydarzeniu(ASTRA, OBCE) == 0,
        stages.faktow_o_wydarzeniu(ASTRA, OBCE))
sprawdz("fakty o nim sa policzone",
        stages.faktow_o_wydarzeniu(ASTRA, O_ASTRZE) == 2,
        stages.faktow_o_wydarzeniu(ASTRA, O_ASTRZE))
sprawdz("pusta partia daje zero",
        stages.faktow_o_wydarzeniu(ASTRA, []) == 0)
sprawdz("wydarzenie bez rdzeni daje zero, a nie wyjatek",
        stages.faktow_o_wydarzeniu({}, O_ASTRZE) == 0)

print()
print("=== 2. OBCY MATERIAL NIE ZAMYKA FURTKI ===")
stages.WYDARZENIA_OBSLUZONE.parent.mkdir(parents=True, exist_ok=True)
stages.WYDARZENIA_OBSLUZONE.write_text("{}", encoding="utf-8")
znane: dict = {}
stages._zapamietaj_wydarzenia([ASTRA], znane, OBCE)
_wpis = znane[stages._rdzen_wydarzenia(ASTRA)]
sprawdz("zapisane `ile` to zero, a nie liczba calej partii",
        _wpis["ile"] == 0, _wpis)
sprawdz("i licznik prob rosnie", _wpis["proby"] == 1, _wpis)
# ZERO NIE ZATRZASKUJE FURTKI — to druga linia obrony, ktora byla tu juz
# wczesniej i ma zostac.
_nowe, _ = stages._nowe_wydarzenia([ASTRA])
sprawdz("wydarzenie z zerem NADAL jest nowe", len(_nowe) == 1, _nowe)

print()
print("=== 3. MATERIAL NA TEMAT ZAMYKA ===")
znane2: dict = {}
stages._zapamietaj_wydarzenia([ASTRA], znane2, O_ASTRZE)
sprawdz("zapisane `ile` to liczba faktow o nim",
        znane2[stages._rdzen_wydarzenia(ASTRA)]["ile"] == 2,
        znane2)
stages.WYDARZENIA_OBSLUZONE.write_text(
    json.dumps(znane2, ensure_ascii=False), encoding="utf-8")
_nowe2, _ = stages._nowe_wydarzenia([ASTRA])
sprawdz("i wtedy wydarzenie przestaje byc nowe", _nowe2 == [], _nowe2)

print()
print("=== 4. DWA WYDARZENIA W PARTII MAJA WLASNE LICZBY ===")
# To jest sedno: wczesniej JEDNA liczba szla do obu wpisow.
stages.WYDARZENIA_OBSLUZONE.write_text("{}", encoding="utf-8")
znane3: dict = {}
stages._zapamietaj_wydarzenia([ASTRA, FABLE], znane3, O_ASTRZE)
_a = znane3[stages._rdzen_wydarzenia(ASTRA)]["ile"]
_f = znane3[stages._rdzen_wydarzenia(FABLE)]["ile"]
sprawdz("wydarzenie z materialem dostaje swoja liczbe", _a == 2, _a)
sprawdz("wydarzenie BEZ materialu dostaje zero, mimo wspolnej partii",
        _f == 0, _f)

print()
print("=== 5. POMIAR I DECYZJA LICZA TAK SAMO ===")
# Pierwotna przyczyna byla wlasnie rozjazdem: liczba o premierze byla liczona
# poprawnie i tylko DRUKOWANA, a do decyzji szlo `len(fakty)`.
import inspect   # noqa: E402

_zr = inspect.getsource(stages.znajdz_ciekawostki)
sprawdz("log korzysta z tej samej funkcji",
        "faktow_o_wydarzeniu(_w, fakty)" in _zr)
sprawdz("i zapis dostaje FAKTY, a nie gotowa liczbe",
        "_zapamietaj_wydarzenia(nowe_wyd, znane_wyd, fakty)" in _zr)
sprawdz("sciezka awaryjna przekazuje pusta liste",
        "_zapamietaj_wydarzenia(nowe_wyd, znane_wyd, [])" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
