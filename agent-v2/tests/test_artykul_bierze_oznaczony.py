# -*- coding: utf-8 -*-
"""Wybor tematu artykulu czyta ocene artykulowosci, za ktora zaplacilismy.

CO SIE DZIALO (B10 z audytu researchu, odtworzone na naszym kodzie).
`posortuj_bank` placi model za ocene, ktory fakt UNIESIE dluga forme,
zapisuje ja jako `na_artykul` i ogranicza udzial takich pozycji do
`BANK_UDZIAL_ARTYKULOW`. `wybierz_fakt` tego pola NIE CZYTALO ANI RAZU —
bralo pierwszy niekolidujacy w kolejnosci z banku.

ZMIERZONE NA ZYWYM BANKU 5 wrzesnia 2026: 19 wolnych pozycji, 3 oznaczone,
i wszystkie trzy staly na czele rankingu. Wybor trafial wiec w oznaczona
PRZEZ KORELACJE, nie przez decyzje — bo `posortuj_bank` stawia znacznik na
czolowce rankingu, a `wez_kandydatow` sortuje po randze.

KIEDY TO GRYZIE. Gdy czolowe kandydatury zderza sie z pamiecia notek albo
poprzednich artykulow: sciezka schodzi nizej i pisze artykul z materialu,
ktory bank uznal za za chudy na dluga forme. Tego wlasnie pilnuje ten plik.

CZEGO TEN TEST PILNUJE:
  1. kolizja zostaje PIERWSZYM sitem — powtorzony temat dyskwalifikuje
     bezwarunkowo, bo dla czytelnika notka i artykul o tym samym to dwa razy
     to samo;
  2. wsrod tego, co przeszlo, wygrywa oznaczony na artykul;
  3. brak oznaczonego NIE zatrzymuje artykulu — tydzien bez tekstu jest
     gorszy niz tekst z materialu nieoznaczonego;
  4. niewykorzystane kandydatury WRACAJA do puli, takze po tej zmianie.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_artykul_bierze_oznaczony.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import artykul_z_puli   # noqa: E402
import stages           # noqa: E402

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


ZWROCONE: list = []


def _przygotuj(kandydaci, pamiec=()):
    """Podstawia bank, pamiec i zwrot — wszystko bez sieci i bez modelu."""
    ZWROCONE.clear()
    stages.wez_kandydatow = lambda ile=8: list(kandydaci)
    stages.tematy_do_porownania = lambda conn: list(pamiec)
    stages.ostatnie_notki = lambda ile=1000: []
    stages.zwroc_kandydatow = lambda lista: ZWROCONE.extend(lista)


_ORYG = {n: getattr(stages, n) for n in
         ("wez_kandydatow", "tematy_do_porownania", "ostatnie_notki",
          "zwroc_kandydatow")}

try:
    print("=== 1. WSROD NIEKOLIDUJACYCH WYGRYWA OZNACZONY ===")
    # Kolejnosc z banku stawia nieoznaczonego PIERWSZEGO — dokladnie sytuacja,
    # ktora audyt odtworzyl jako blad.
    # ZDANIA MUSZA BYC DOSC DLUGIE, ZEBY W OGOLE MOGLY SIE ZDERZYC.
    # Pierwsza wersja tych atrap miala po trzy slowa i wykrywacz powtorek
    # (`min_wspolnych: 4`) nie uznawal ich za zderzone NAWET SAMYCH ZE SOBA —
    # wiec test o kolizjach nie badal kolizji. Atrapa krotsza niz prog,
    # ktory bada, jest zawsze zielona i zawsze bezuzyteczna.
    A = {"fact": "thin candidate about warehouse robot battery swap timing",
         "domain": "logistics", "na_artykul": False}
    B = {"fact": "strong candidate about compute contract cost per megawatt",
         "domain": "energy", "na_artykul": True}
    _przygotuj([A, B])
    w = artykul_z_puli.wybierz_fakt(None, None)
    sprawdz("wybrany jest oznaczony, mimo ze byl drugi w kolejce",
            w is B, w.get("fact"))
    sprawdz("nieoznaczony wrocil do puli", ZWROCONE == [A],
            [x.get("fact") for x in ZWROCONE])

    print()
    print("=== 2. KOLIZJA NADAL DYSKWALIFIKUJE BEZWARUNKOWO ===")
    # Oznaczony, ale juz o tym pisalismy — ma przegrac z nieoznaczonym
    # czystym. Powtorka jest gorsza niz chudszy material.
    _przygotuj([A, B], pamiec=["energy strong candidate about compute contract cost per megawatt"])
    w2 = artykul_z_puli.wybierz_fakt(None, None)
    sprawdz("oznaczony z kolizja NIE wygrywa", w2 is A, w2.get("fact"))
    sprawdz("i to on wraca do puli", ZWROCONE == [B],
            [x.get("fact") for x in ZWROCONE])

    print()
    print("=== 3. BRAK OZNACZONEGO NIE ZATRZYMUJE ARTYKULU ===")
    C = {"fact": "another thin candidate about queue latency in retail",
         "domain": "retail", "na_artykul": False}
    _przygotuj([A, C])
    w3 = artykul_z_puli.wybierz_fakt(None, None)
    sprawdz("przy zerze oznaczonych wychodzi pierwszy z brzegu",
            w3 is A, w3.get("fact"))
    sprawdz("reszta i tak wraca do puli", ZWROCONE == [C],
            [x.get("fact") for x in ZWROCONE])

    print()
    print("=== 4. GDY WSZYSTKO KOLIDUJE, TEZ PATRZYMY NA ZNACZNIK ===")
    # Sciezka awaryjna „biore pierwszy" tez ma preferowac oznaczonego —
    # inaczej w najgorszym dniu bierzemy najslabszy material.
    _przygotuj([A, B], pamiec=[
        "logistics thin candidate about warehouse robot battery swap timing",
        "energy strong candidate about compute contract cost per megawatt"])
    w4 = artykul_z_puli.wybierz_fakt(None, None)
    sprawdz("przy samych kolizjach wygrywa oznaczony", w4 is B,
            w4.get("fact"))

    print()
    print("=== 5. PUSTA PULA NADAL JEST BLEDEM, NIE CICHYM ZEREM ===")
    _przygotuj([])
    stages.znajdz_ciekawostki = lambda *a, **kw: []
    try:
        artykul_z_puli.wybierz_fakt(None, None)
        sprawdz("pusta pula podnosi wyjatek", False, "nie podniosla")
    except ValueError:
        sprawdz("pusta pula podnosi wyjatek", True)
finally:
    for n, f in _ORYG.items():
        setattr(stages, n, f)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
