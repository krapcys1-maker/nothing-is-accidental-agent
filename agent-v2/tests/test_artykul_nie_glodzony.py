# -*- coding: utf-8 -*-
"""Wtorkowy artykul nie zostaje zaglodzony przez notki sprzed trzech godzin.

CO ZGLOSIL PRZEGLAD ZEWNETRZNY (na czystym rdzeniu). Zegar: notki o 07:00,
11:20, 17:00, 19:20, 21:30, 23:40; artykul we wtorek o 14:00 — czyli DWA
przebiegi notek ida przed artykulem. Limit `SZUKANIE_BANKU_NA_DOBE` jest
WSPOLNY i nie rozroznia wolajacego, wiec notki moga zjesc caly przydzial,
a wtedy `artykul_z_puli` konczy sie na:

    fakty = stages.wez_kandydatow(ile)          # pusto
    if not fakty:
        fakty = stages.znajdz_ciekawostki(...)  # oddaje [] — limit wyczerpany
    if not fakty:
        raise ValueError("pula ciekawostek pusta")

`zalegly_artykul` tego nie ratuje: ratuje TEKST, ktory powstal, a tu nie
powstaje nic.

CO USTALILISMY NA NASZYM KODZIE. Scenariusz w tej postaci NAS NIE DOTYCZY,
bo mamy podloge, ktorej czysty rdzen nie ma: przy mniej niz
`BANK_MIN_WOLNYCH` wolnych tematach przydzial rosnie do
`SZUKANIE_BANKU_MAKS_PROB`. Sprawdzone na zywo 5 wrzesnia 2026: bank pusty ->
wolno 5 prob, dwa przebiegi notek zostawiaja trzy.

ZOSTALA JEDNAK SZCZELINA i ona jest przedmiotem tego pliku: PODLOGA PATRZY NA
PUSTKE BANKU, NIE NA POTRZEBE ARTYKULU. Gdy bank ma 15 pozycji i zadna nie
nadaje sie na artykul (wszystkie zderzaja sie z tematami poprzednich),
przydzial wynosi zwykle dwa i oba przebiegi notek moga go zjesc.

RACHUNEK JEST ODWROTNY DO ZAMIERZONEGO: limit oszczedza jedno szukanie —
0,0185 USD po przejsciu na spizarnie 5 wrzesnia — i potrafi kosztowac caly
artykul (okolo 1,5 USD) plus tydzien publikacji. Artykul jest przy tym
JEDYNYM miejscem, z ktorego przychodza subskrypcje.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_artykul_nie_glodzony.py
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


print("=== 1. PODLOGA BANKU BIJE LIMIT DOBOWY (to juz mielismy) ===")
_stare_wolne = stages._wolnych_w_banku
try:
    stages._wolnych_w_banku = lambda: 0
    sprawdz("pusty bank podnosi przydzial do sufitu prob",
            stages._ile_prob_wolno_dzis() == config.SZUKANIE_BANKU_MAKS_PROB,
            stages._ile_prob_wolno_dzis())
    sprawdz("a to wiecej niz dwa przebiegi notek przed 14:00",
            config.SZUKANIE_BANKU_MAKS_PROB > 2,
            config.SZUKANIE_BANKU_MAKS_PROB)
    stages._wolnych_w_banku = lambda: config.BANK_MIN_WOLNYCH + 5
    stages._faktow_dopisanych_dzis = lambda: 1
    sprawdz("ale przy PELNYM banku przydzial jest zwykly",
            stages._ile_prob_wolno_dzis() == config.SZUKANIE_BANKU_NA_DOBE,
            stages._ile_prob_wolno_dzis())
    sprawdz("i wtedy dwa przebiegi notek moga go zjesc w calosci",
            config.SZUKANIE_BANKU_NA_DOBE <= 2, config.SZUKANIE_BANKU_NA_DOBE)
finally:
    stages._wolnych_w_banku = _stare_wolne

print()
print("=== 2. ARTYKUL PRZECHODZI MIMO WYCZERPANEGO LIMITU DOBOWEGO ===")
_wolania = []


def _fake_call(purpose, system, user, **kw):
    _wolania.append(purpose)
    return '{"facts": [{"fact": "cos z liczba 42", "url": "https://e.example/1"}]}'


_stare = {
    "call": stages.llm.call,
    "przeb": stages._przebiegi_z_bankiem_dzis,
    "wolno": stages._ile_prob_wolno_dzis,
    "pelny": stages.bank_pelny,
    "wolne": stages._wolnych_w_banku,
    "wyd": stages._nowe_wydarzenia,
}
try:
    stages.llm.call = _fake_call
    stages.bank_pelny = lambda: False
    # ZADNEGO NOWEGO WYDARZENIA. Pierwsza wersja tego testu tego nie uciszyla
    # i oblala — bo galaz „NOWE wydarzenie" otwiera furtke PRZED podloga i
    # przed zwolnieniem dla artykulu, wiec do badanej galezi nigdy nie
    # dochodzilo. Sam ten fakt jest wart zapisania: limit dobowy ma juz
    # DRUGIE obejscie, o ktorym latwo zapomniec przy liczeniu kosztow.
    stages._nowe_wydarzenia = lambda w: ([], [])
    stages._wolnych_w_banku = lambda: config.BANK_MIN_WOLNYCH + 5
    # LIMIT DOBOWY WYCZERPANY: dwa przebiegi przy przydziale dwa.
    stages._przebiegi_z_bankiem_dzis = lambda conn: 2
    stages._ile_prob_wolno_dzis = lambda: 2

    _wolania.clear()
    stages.znajdz_ciekawostki(None, None, ile=4)
    sprawdz("NOTKA przy wyczerpanym limicie NIE szuka", _wolania == [], _wolania)

    _wolania.clear()
    stages.znajdz_ciekawostki(None, None, ile=4, dla_artykulu=True)
    sprawdz("ARTYKUL przy tym samym limicie SZUKA",
            "curiosity" in _wolania, _wolania)

    print()
    print("=== 3. ALE SUFIT PROB ZOSTAJE — ZEPSUTE SZUKANIE MA SIE ZATRZYMAC ===")
    # Zwolnienie dotyczy limitu DOBOWEGO, nie sufitu prob. Bez tego zepsute
    # szukanie probowaloby w kolko, tylko dlatego, ze wola je artykul —
    # a mielismy juz przebieg z 23 zapytaniami i zerem faktow za 0,13 USD.
    stages._przebiegi_z_bankiem_dzis = lambda conn: config.SZUKANIE_BANKU_MAKS_PROB
    _wolania.clear()
    _w = stages.znajdz_ciekawostki(None, None, ile=4, dla_artykulu=True)
    sprawdz("artykul przy wyczerpanym SUFICIE PROB juz nie szuka",
            _wolania == [], _wolania)
    sprawdz("i oddaje pusto, nie wyjatek", _w == [], _w)
finally:
    stages.llm.call = _stare["call"]
    stages._przebiegi_z_bankiem_dzis = _stare["przeb"]
    stages._ile_prob_wolno_dzis = _stare["wolno"]
    stages.bank_pelny = _stare["pelny"]
    stages._wolnych_w_banku = _stare["wolne"]
    stages._nowe_wydarzenia = _stare["wyd"]

print()
print("=== 4. SCIEZKA ARTYKULU NAPRAWDE SIE PRZEDSTAWIA ===")
# Sam parametr nic nie znaczy, jesli wolajacy go nie podaje — to ta sama
# rodzina wad, co martwy wpis EFFORT.
_zr = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
sprawdz("artykul_z_puli wola z dla_artykulu=True",
        "dla_artykulu=True" in _zr)
sprawdz("i nadal NAJPIERW siega do banku, dopiero potem szuka",
        _zr.index("stages.wez_kandydatow(ile)")
        < _zr.index("dla_artykulu=True"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
