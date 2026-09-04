# -*- coding: utf-8 -*-
"""Parowanie banku: jedyne pytanie o ZBIOR, nie o pojedyncze pozycje.

PO CO TO POWSTALO. Kazde inne sprawdzenie w tym potoku patrzy na fakt osobno —
swiezosc, straznik powtorek, ranking banku. Nikt nie pytal o zbior, i to jest
zrodlo plaskosci zglaszanej przez wlasciciela od sierpnia:

    31 sierpnia 2026  TRZY notki o GLM-5.3-Flash jednego dnia (wskazniki
                      powtorzen, chinskie uklady, cena). Trzy rozne ustalenia,
                      jeden model w kanale.
    4 wrzesnia 2026   dwa najwyzej ocenione fakty w banku dotyczyly cennika
                      Gemini 3.8 Flash.

Pozostale zabezpieczenia dzialaja dopiero PRZY WYBORZE NOTKI — za pozno, bo
bank jest juz wtedy zapchany wariantami jednej historii.

CZEGO PILNUJE TEN TEST. `sparuj_bank` USUWA material z platnej puli, wiec
wiekszosc asercji to kontrdowody: zla odpowiedz modelu nie moze zabrac banku.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_parowanie_banku.py
Zero wywolan modelu, zero sieci.
"""
import json
import sys

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import llm     # noqa: E402
import stages  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def fakt(tresc):
    return {"status": "nowy", "kiedy": config.DATA_PRZESTAWIENIA,
            "wazny_do": "2099-01-01", "source_date": config.DATA_PRZESTAWIENIA,
            "fact": tresc}


def uruchom(bank, odpowiedz):
    """Puszcza parowanie z podstawiona odpowiedzia modelu."""
    st_ind, st_zap, st_call = (stages.wczytaj_indeks, stages._zapisz_indeks,
                               llm.call)
    stages.wczytaj_indeks = lambda *a, **k: bank
    stages._zapisz_indeks = lambda x: None
    llm.call = lambda *a, **k: (odpowiedz if isinstance(odpowiedz, str)
                                else json.dumps(odpowiedz))
    try:
        return stages.sparuj_bank(None, None)
    finally:
        stages.wczytaj_indeks, stages._zapisz_indeks = st_ind, st_zap
        llm.call = st_call


print("=== 1. TA SAMA HISTORIA ZOSTAJE SCALONA ===")
B = [fakt("Gemini 3.8 Flash sells at the same per-token price as 3.7 Flash"),
     fakt("Gemini 3.8 Flash costs 40 percent more per finished task than 3.7"),
     fakt("Ireland gave 23 percent of its metered electricity to data centres")]
w = uruchom(B, {"grupy": [{"zostaje": 0, "scalone": [1],
                           "dlaczego": "ten sam cennik jednego modelu"}]})
sprawdz("jedna grupa rozpoznana", w["grup"] == 1, w)
sprawdz("scalona dokladnie jedna pozycja", w["scalone"] == 1, w)
sprawdz("mocniejszy ZOSTAJE wolny", B[0]["status"] == "nowy", B[0]["status"])
sprawdz("slabszy wychodzi z puli", B[1]["status"] == "odrzucony", B[1]["status"])
sprawdz("i ma zapisany powod, nie znika bez sladu",
        "parowanie" in str(B[1].get("powod", "")), B[1].get("powod"))
sprawdz("tresc scalonego ladu je na tym, ktory zostaje",
        any("40 percent" in t for t in B[0].get("scalone_z") or []),
        B[0].get("scalone_z"))
sprawdz("KONTRDOWOD: fakt spoza grupy nietkniety",
        B[2]["status"] == "nowy", B[2]["status"])

print()
print("=== 2. KONTRDOWODY: ZLA ODPOWIEDZ NIE MOZE ZABRAC BANKU ===")
B2 = [fakt("aaa pierwszy fakt o czyms"), fakt("bbb drugi fakt o czym innym"),
      fakt("ccc trzeci fakt zupelnie osobny")]
uruchom(B2, {"grupy": []})
sprawdz("pusta odpowiedz nie rusza niczego",
        all(x["status"] == "nowy" for x in B2), [x["status"] for x in B2])

B3 = [fakt("aaa"), fakt("bbb"), fakt("ccc")]
uruchom(B3, {"grupy": [{"zostaje": 99, "scalone": [1]}]})
sprawdz("nieistniejacy `zostaje` jest pomijany",
        all(x["status"] == "nowy" for x in B3), [x["status"] for x in B3])

B4 = [fakt("aaa"), fakt("bbb"), fakt("ccc")]
uruchom(B4, {"grupy": [{"zostaje": 0, "scalone": [99, 1]}]})
sprawdz("nieistniejacy identyfikator w `scalone` jest odsiewany, reszta dziala",
        B4[1]["status"] == "odrzucony" and B4[2]["status"] == "nowy",
        [x["status"] for x in B4])

B5 = [fakt("aaa"), fakt("bbb"), fakt("ccc")]
uruchom(B5, {"grupy": [{"zostaje": 0, "scalone": [0]}]})
sprawdz("KONTRDOWOD: fakt nie moze scalic sam siebie",
        all(x["status"] == "nowy" for x in B5), [x["status"] for x in B5])

B6 = [fakt("aaa"), fakt("bbb"), fakt("ccc")]
uruchom(B6, "to nie jest JSON, model sie rozgadal")
sprawdz("KONTRDOWOD: brak JSON-a zostawia bank bez zmian",
        all(x["status"] == "nowy" for x in B6), [x["status"] for x in B6])


def wybuch(*a, **k):
    raise RuntimeError("model padl")


_st = llm.call
llm.call = wybuch
_si, _sz = stages.wczytaj_indeks, stages._zapisz_indeks
B7 = [fakt("aaa"), fakt("bbb"), fakt("ccc")]
stages.wczytaj_indeks = lambda *a, **k: B7
stages._zapisz_indeks = lambda x: None
try:
    w7 = stages.sparuj_bank(None, None)
finally:
    llm.call, stages.wczytaj_indeks, stages._zapisz_indeks = _st, _si, _sz
sprawdz("awaria modelu nie wywraca przebiegu", w7 == {"grup": 0, "scalone": 0}, w7)
sprawdz("i nie rusza banku", all(x["status"] == "nowy" for x in B7))

print()
print("=== 3. SUFIT SCALEN NA PRZEBIEG ===")
# Oslona przed JEDNA zla odpowiedzia: parowanie usuwa material z platnej puli,
# wiec zle grupowanie nie moze zabrac wiekszosci banku w jednym wywolaniu.
B8 = [fakt("fakt numer %d o czyms zupelnie innym" % i) for i in range(8)]
w8 = uruchom(B8, {"grupy": [{"zostaje": 0,
                             "scalone": [1, 2, 3, 4, 5, 6, 7]}]})
sprawdz("scalono najwyzej tyle, ile pozwala sufit",
        w8["scalone"] == stages.MAKS_SCALEN_NA_PRZEBIEG, w8)
sprawdz("reszta banku przezyla",
        sum(1 for x in B8 if x["status"] == "nowy")
        == len(B8) - stages.MAKS_SCALEN_NA_PRZEBIEG,
        [x["status"] for x in B8])

print()
print("=== 4. MALY BANK NIE JEST PYTANY ===")
wolano = {"ile": 0}


def licz(*a, **k):
    wolano["ile"] += 1
    return json.dumps({"grupy": []})


_st2 = llm.call
llm.call = licz
_si2, _sz2 = stages.wczytaj_indeks, stages._zapisz_indeks
B9 = [fakt("aaa"), fakt("bbb")]
stages.wczytaj_indeks = lambda *a, **k: B9
stages._zapisz_indeks = lambda x: None
try:
    w9 = stages.sparuj_bank(None, None)
finally:
    llm.call, stages.wczytaj_indeks, stages._zapisz_indeks = _st2, _si2, _sz2
sprawdz("przy dwoch faktach nie ma czego parowac — zero wywolan",
        wolano["ile"] == 0, wolano)
sprawdz("i zwraca zera", w9 == {"grup": 0, "scalone": 0}, w9)

print()
print("=== 5. ETAP MA MODEL I SUFIT, PROMPT MA SWOJE MIEJSCA ===")
sprawdz("etap `parowanie` ma przypisany model",
        "parowanie" in config.MODEL_FOR, sorted(config.MODEL_FOR)[:3])
sprawdz("i jest to model najtanszy — to grupowanie, nie pisanie",
        config.MODEL_FOR["parowanie"] == config.MODEL_FOR["powtorka"],
        config.MODEL_FOR["parowanie"])
sprawdz("ma sufit tokenow", config.MAX_TOKENS.get("parowanie", 0) > 0,
        config.MAX_TOKENS.get("parowanie"))
_p = stages._prompt("parowanie.md", pozycje="0. cokolwiek")
sprawdz("prompt zada JSON-a z grupami", '"grupy"' in _p)
sprawdz("prompt mowi WPROST, ze przy watpliwosci NIE grupujemy",
        "DO NOT group" in _p)
sprawdz("prompt podaje mierzona przyczyne, nie ogolnik",
        "GLM-5.3-Flash" in _p and "Gemini 3.8 Flash" in _p)
sprawdz("prompt ostrzega przed scaleniem po samej firmie",
        "Same company, different event" in _p)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
