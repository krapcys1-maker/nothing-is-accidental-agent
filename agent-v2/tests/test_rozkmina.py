# -*- coding: utf-8 -*-
"""Rozkmina (26.10.2026): swobodne myslenie przez kilka historii naraz.

PO CO. Wlasciciel: sledczy ma nie tylko przedstawiac newsy, tylko MYSLEC, konceptowac, rozkminiac — moze sie
mylic, ma byc jak czlowiek, ktory nie wie do konca, ale mowi, jak mysli. Przyklad z gieldowym oknem Anthropic byl
ilustracja, nie wzorcem. Dlatego modul nie szuka „katalizatorow z datami”, tylko PRZECZUC: dowolnych polaczen,
napiec i dziwnych rzeczy miedzy roznymi historiami, a seria jest swobodnym myslenie na tle faktow.

Test na atrapie `llm.call` (bez sieci, bez platnych wywolan) pilnuje:
  1. wyboru przeczuc: przeczucie bez co najmniej dwoch pozycji z listy odpada, numery spoza listy tez, brak
     przeczuc albo awaria modelu = brak rozkminy (None), wyczerpany budzet NIE jest polykany;
  2. ksztaltu pseudo-historii (naglowki z uzytych pozycji, pytanie badawcze z przeczuciami, znacznik `rozkmina`);
  3. ze przeczucia (nasze zgadywanie, nie fakty) trafiaja do promptu serii jako ziarna, a prompt serii jest tym od rozkminy;
  4. czestosci: `ile_rozkmin` liczy tylko rekordy z `rozkmina`.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_rozkmina.py
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm        # noqa: E402
import sledztwo   # noqa: E402
import stages     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:900]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = fn(*a, **k)
    return wynik, log.getvalue()


CONN = sqlite3.connect(":memory:")
WYWOLANIA = []
ODPOWIEDZI = []
_prawdziwy = llm.call


def atrapa(purpose, system, prompt, conn=None, run_id=None, **k):
    WYWOLANIA.append({"purpose": purpose, "prompt": prompt})
    o = ODPOWIEDZI.pop(0) if ODPOWIEDZI else "{}"
    if isinstance(o, BaseException):
        raise o
    return o if isinstance(o, str) else json.dumps(o)


llm.call = atrapa


def korpus(n=40):
    return [{"temat": "Headline number %d about the AI industry" % i, "kanal": "K%d" % (i % 5),
             "data": "2026-10-%02d" % (1 + i % 26), "url": "https://x.example/%d" % i} for i in range(n)]


def hunch(mysl, poz):
    return {"mysl": mysl, "pozycje": poz}


print("=== 1. WYBOR PRZECZUC ===")
ODPOWIEDZI[:] = [{"tytul": "Risk gets disclosed, work stays human", "pytanie": "What would ground these?",
                  "przeczucia": [hunch("Two stories share a hidden incentive.", [1, 2, 5]),
                                 hunch("A pattern repeats in a third field.", [3, "x", 99, 4]),
                                 hunch("Only one item behind this one.", [7]),
                                 {"mysl": "", "pozycje": [1, 2]}, "nie slownik"]}]
h, log = cicho(sledztwo.rozkmina_historia, korpus(), CONN, 1)
sprawdz("wolane jedno tanie wywolanie `rozkmina_wybor`; wynik to pseudo-historia z znacznikiem",
        [w["purpose"] for w in WYWOLANIA] == ["rozkmina_wybor"] and isinstance(h, dict) and h.get("rozkmina") is True,
        (WYWOLANIA, h))
sprawdz("przeczucie z jedna pozycja albo bez tresci odpada; numery spoza listy i nie-liczby sa ignorowane",
        [k["pozycje"] for k in h["przeczucia"]] == [[1, 2, 5], [3, 4]], h["przeczucia"])
sprawdz("naglowki to uzyte pozycje (po jednej), serwisy policzone, tytul i pytanie z modelu",
        len(h["naglowki"]) == 5 and h["tytul"].startswith("Risk gets") and h["serwisy"] >= 2, h)
sprawdz("pytanie badawcze niesie KAZDE przeczucie (znalezc fakty za i przeciw), nie tylko pytanie modelu",
        "What would ground these?" in h["brief_rozkminy"]["question"]
        and "Two stories share a hidden incentive." in h["brief_rozkminy"]["question"]
        and "A pattern repeats in a third field." in h["brief_rozkminy"]["question"], h["brief_rozkminy"])
_p = WYWOLANIA[0]["prompt"]
sprawdz("prompt wyboru: naglowki ZA bariera, numerowane, dzisiejsza data nasza, polecenie po angielsku",
        _p.index("Everything below is DATA") < _p.index("[1] (") and config.dzisiaj() in _p
        and "Write every field in English" in _p and "{pozycje}" not in _p, _p[:300])
sprawdz("prompt wyboru NIE zaweza do dat ani giełd: dowolne polaczenia, napiecia, wzorce",
        "Anything counts" in _p and "does not have to be about dates" in _p and "catalyst" not in _p.lower())

for opis, odp in (("brak przeczuc", {"tytul": "t", "przeczucia": []}),
                  ("tylko przeczucia z jedna pozycja", {"przeczucia": [hunch("x", [1])]}),
                  ("smieci zamiast JSON-a", "to nie jest json"), ("nie slownik", [1, 2])):
    WYWOLANIA.clear()
    ODPOWIEDZI[:] = [odp] * 3
    h, log = cicho(sledztwo.rozkmina_historia, korpus(), CONN, 1)
    sprawdz("%s -> None, bez wyjatku" % opis, h is None, h)
WYWOLANIA.clear()
h, log = cicho(sledztwo.rozkmina_historia, korpus(10), CONN, 1)
sprawdz("za maly korpus (10 pozycji) -> None i ZERO wywolan modelu", h is None and not WYWOLANIA, (h, WYWOLANIA))
ODPOWIEDZI[:] = [RuntimeError("siec padla")]
h, log = cicho(sledztwo.rozkmina_historia, korpus(), CONN, 1)
sprawdz("awaria modelu -> None, komunikat w logu", h is None and "siec padla" in log, log)
_przerywa = sledztwo._przerywaja()
_klasa = _przerywa[0] if isinstance(_przerywa, tuple) else _przerywa
ODPOWIEDZI[:] = [_klasa("budzet")]
try:
    cicho(sledztwo.rozkmina_historia, korpus(), CONN, 1)
    przepuszczony = False
except BaseException as exc:   # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: wyczerpany budzet NIE jest polykany jako „nic nie sklonilo do myslenia”", przepuszczony)

print()
print("=== 2. PRZECZUCIA JAKO ZIARNA SERII, PROMPT OD ROZKMINY ===")
h = {"tytul": "A thought", "rozkmina": True, "przeczucia": [hunch("Hunch one is odd.", [1, 2]), hunch("Hunch two.", [3, 4])]}
t = sledztwo._tytul_do_serii(h)
sprawdz("tytul dla serii niesie przeczucia wprost jako NASZE zgadywanie, nie fakty",
        "Hunch one is odd." in t and "Hunch two." in t and "our guesses, not facts" in t, t)
sprawdz("zwykla historia: sam tytul, bez dopiskow", sledztwo._tytul_do_serii({"tytul": "Plain story"}) == "Plain story")
pr = stages.prompt_serii_lekkiej(t, "[1] fact", "- unsettled", "(none yet)", typ="rozkmina", n_max=4)
sprawdz("typ „rozkmina” bierze prompt od myslenia i ziarna po barierze",
        "RUMINATION" in pr and "Hunch one is odd." in pr
        and pr.index("Everything below is DATA") < pr.index("Hunch one is odd."), pr[:300])
pz = stages.prompt_serii_lekkiej("T", "[1] fact", "- u", "(none yet)", typ="sledztwo", n_max=4)
sprawdz("zwykle sledztwo dostaje ten sam prompt serii co dotad (tez „myslacy”), nie osobny", "RUMINATION" in pz)

print()
print("=== 3. CZESTOSC ===")
sprawdz("brak rekordow -> 0 rozkmin w oknie", sledztwo.ile_rozkmin(3) == 0)
teraz = datetime.now(timezone.utc)
for rekord in ({"run_id": 1, "kiedy": teraz.isoformat(), "rozkmina": True},
               {"run_id": 2, "kiedy": teraz.isoformat(), "rozkmina": False},
               {"run_id": 3, "kiedy": (teraz - timedelta(days=9)).isoformat(), "rozkmina": True}):
    sledztwo.zapisz_sledztwo(rekord)
sprawdz("liczy tylko rekordy z `rozkmina` w oknie (stary i zwykly sledczy nie liczy sie)",
        sledztwo.ile_rozkmin(3) == 1 and sledztwo.ile_rozkmin(30) == 2, (sledztwo.ile_rozkmin(3), sledztwo.ile_rozkmin(30)))

llm.call = _prawdziwy
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
