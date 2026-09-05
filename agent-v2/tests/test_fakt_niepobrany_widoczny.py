# -*- coding: utf-8 -*-
"""Fakt startowy, ktorego nikt nie pobral, jest oznaczony i pisarz o tym wie.

CO ZGLASZA AUDYT (R11). Gdy adres faktu wyjsciowego nie pojawia sie w
`confirmed_claims`, kod dopisuje go tam sam. Wszystkie sytuacje — dokument
nieobecny, odrzucony, albo obecny lecz bez potwierdzonego twierdzenia —
prowadza do tego samego uzupelnienia, a fakt laduje w sekcji POTWIERDZONYCH.

CO USTALILEM NA NASZYM KODZIE. Polowa tego jest u nas zalatwiona i to porzadnie:
wpis dostaje `not_fetched: true`, a DWIE BRAMKI ten znacznik CZYTAJA —
`gates.szerokosc_podstawy` nie liczy hosta, ktorego nikt nie pobral (uwaga
`WASKA_PODSTAWA` powstala po artykule stojacym realnie na jednym zrodle),
a `gates._korpus_pobranych` wyprowadza stamtad liczby pod osobna uwage
`LICZBA_TYLKO_Z_PULI`. `evidence` bierze sie z `control_fact` albo `actually`,
a nie z echa samego twierdzenia.

CZEGO BRAKOWALO. Karta idzie do pisarza jako surowy JSON, wiec `not_fetched`
tam JEST — ale zaden prompt nie mowil, co ten znacznik znaczy. Pisarz widzial
wpis w `confirmed_claims` i nie mial powodu traktowac go inaczej niz cytat
z pobranego dokumentu. Bramki chronia liczby i szerokosc podstawy; nie chronia
zdania, ktore na takim fakcie zbuduje wniosek.

CZEGO TEN TEST PILNUJE:
  1. znacznik jest ustawiany i niesie ODREBNY wyciag, nie echo twierdzenia;
  2. obie bramki nadal go czytaja — bo to one egzekwuja, a prompt tylko
     objasnia;
  3. prompt pisarza mowi wprost, czym ten wpis jest i czego na nim nie wolno
     zbudowac.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_fakt_niepobrany_widoczny.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import gates   # noqa: E402

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


# Karta w ksztalcie, jaki naprawde wychodzi z syntezy: wstrzykniecie z
# `artykul_z_puli` dopisuje WYLACZNIE do `confirmed_claims` — `citable_numbers`
# pochodzi z pobranych dokumentow, wiec liczby faktu z puli tam NIE MA.
KARTA = {
    "confirmed_claims": [
        {"claim": "The agency set the threshold at 12 units.",
         "evidence": "the published rule fixes the threshold at 12 units",
         "url": "https://pula.example/fakt", "not_fetched": True},
        {"claim": "Seven operators reported the same failure.",
         "evidence": "7 operators filed the same fault report in March",
         "url": "https://pobrane.example/raport"},
    ],
    "citable_numbers": ["7 operators"],
}

print("=== 1. BRAMKI CZYTAJA ZNACZNIK — TO ONE EGZEKWUJA ===")
_zr = pathlib.Path("agent-v2/gates.py").read_text(encoding="utf-8")
sprawdz("szerokosc podstawy nie liczy niepobranego hosta",
        "not_fetched" in _zr.split("def szerokosc_podstawy")[1][:1200]
        if "def szerokosc_podstawy" in _zr else False)

# Sprawdzam ZACHOWANIE, nie ksztalt prywatnego zbioru. Pierwsza wersja tego
# testu siegala do `_korpus_pobranych` i przewrocila sie na tym, ze zwraca
# zbior tokenow, a nie tekst — czyli sprawdzalaby moje wyobrazenie o funkcji.
CIALO = ("The threshold sits at 12 units today. "
         "7 operators have already filed the same report.")
_uwagi = {u["gate"] for u in gates.deterministic_floors(CIALO, KARTA)}
sprawdz("liczba z niepobranego faktu dostaje WLASNA uwage",
        "LICZBA_TYLKO_Z_PULI" in _uwagi, sorted(_uwagi))
sprawdz("i NIE klamie, ze nie ma jej w materiale dowodowym",
        "LICZBA_SPOZA_KORPUSU" not in _uwagi, sorted(_uwagi))

# Kontrola odwrotna: liczba, ktorej nie ma NIGDZIE, nadal ma isc pod ostra
# uwage. Bez tego powyzsze przechodziloby tez wtedy, gdyby znacznik zjadl
# cala kontrole liczb.
_obce = {u["gate"] for u in gates.deterministic_floors(
    "The figure reached 4931 within a week.", KARTA)}
sprawdz("zmyslona liczba nadal jako LICZBA_SPOZA_KORPUSU",
        "LICZBA_SPOZA_KORPUSU" in _obce, sorted(_obce))

print()
print("=== 2. WYCIAG NIE JEST ECHEM TWIERDZENIA ===")
# To jest wzorzec, przed ktorym stoi „MUST CARRY THE WHOLE CLAIM" w syntezie:
# cytat bedacy kopia twierdzenia nie dowodzi niczego.
_w = KARTA["confirmed_claims"][0]
sprawdz("evidence rozni sie od claim",
        _w["evidence"].strip().lower() != _w["claim"].strip().lower())
_azp = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
sprawdz("kod bierze wyciag z control_fact albo actually",
        'fakt.get("control_fact")' in _azp and 'fakt.get("actually")' in _azp)
sprawdz("i ustawia znacznik", '"not_fetched": True' in _azp)

print()
print("=== 3. PISARZ WIE, CZYM JEST TEN WPIS ===")
# Bramki chronia liczby i szerokosc podstawy. NIE chronia zdania, ktore na
# takim fakcie zbuduje wniosek — a karta idzie do pisarza jako surowy JSON,
# wiec znacznik tam byl, tylko nikt nie powiedzial, co znaczy.
_pis = pathlib.Path("agent-v2/prompts/pisarz.md").read_text(encoding="utf-8")
# Prompt jest zawijany na 79 znakow i uzywa **wytluszczen**, wiec szukanie
# doslownego napisu sprawdza szerokosc kolumny, a nie tresc. Pierwsza wersja
# tego testu wywrocila sie wlasnie na tym.
_plaski = " ".join(_pis.replace("**", "").split())
sprawdz("prompt pisarza wspomina znacznik", "not_fetched" in _pis)
sprawdz("mowi, ze to NIE jest wyciag z pobranego dokumentu",
        "not a passage lifted from a document we retrieved" in _plaski)
sprawdz("kaze przypisac zrodlo", "you must attribute it to the source named in its" in _plaski)
sprawdz("i zabrania budowac na tym liczby ani wniosku",
        "Do not build a figure, a comparison or a conclusion on it" in _plaski)
sprawdz("objasnienie stoi PRZY karcie, nie gdzie indziej",
        _pis.index("not_fetched") < _pis.index("{card_json}"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
