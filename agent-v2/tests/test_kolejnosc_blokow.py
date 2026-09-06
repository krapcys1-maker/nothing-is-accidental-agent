# -*- coding: utf-8 -*-
"""Blok z lepszym wynikiem nie moze stac za blokiem z gorszym.

CO ZMIERZYLEM 6 wrzesnia 2026 na dzienniku systemowym z 7 dni (6 618 linii)
i na wlasnym dzienniku konta:

    blok        uciety na czasie    komentarzy z reakcja
    dyskusje    7 razy w 7 dni      31%  (13 pozycji z odczytem)
    komentarze  3 razy              16%  (86 pozycji)
    notki       2 razy

Dyskusje staly SZOSTE z dziewieciu, zaraz po komentarzach — czyli kanal
z lepszym wynikiem dostawal resztki czasu po kanale z gorszym i przez to byl
ucinany dwa razy czesciej.

CO TEN TEST PILNUJE. Nie tego, ze lista ma konkretna dlugosc — tego, ze
DYSKUSJE IDA PRZED KOMENTARZAMI, i ze zadna z pozostalych pozycji nie
wyparowala przy tej zamianie. Kolejnosc blokow jest zwykla krotka w `run.py`,
wiec kazda przyszla zmiana w tym miejscu jest jednowierszowa i latwo ja
przestawic z powrotem bez zauwazenia.

CZEGO NIE SPRAWDZAM, bo tego celowo NIE ZMIENILEM: przydzialu. Artykuly nadal
biora `na_teraz["komentarze"]`, dyskusje `max(1, N // 2)`. Przewaga dyskusji
stoi na trzynastu pozycjach z odczytem — za malo, zeby przestawiac wolumeny.
Sama kolejnosc te probke powieksza.

BEZ PYTESTA, zero sieci. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_kolejnosc_blokow.py
"""
import ast
import pathlib
import sys

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


ZR = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
DRZEWO = ast.parse(ZR)


def kolejnosc_blokow():
    """Nazwy blokow z petli `for nazwa, robota in (...)` — Z DRZEWA SKLADNI.

    Nie z regeksu po tekscie: regeks zlapalby tez nazwe w komentarzu albo
    w napisie i test zaczalby pilnowac dokumentacji zamiast kodu.
    """
    for w in ast.walk(DRZEWO):
        if not isinstance(w, ast.For):
            continue
        if not (isinstance(w.target, ast.Tuple) and len(w.target.elts) == 2):
            continue
        cel = [e.id for e in w.target.elts if isinstance(e, ast.Name)]
        if cel != ["nazwa", "robota"]:
            continue
        if not isinstance(w.iter, ast.Tuple):
            continue
        nazwy = []
        for para in w.iter.elts:
            if isinstance(para, ast.Tuple) and para.elts:
                p = para.elts[0]
                if isinstance(p, ast.Constant) and isinstance(p.value, str):
                    nazwy.append(p.value)
        if nazwy:
            return nazwy
    return []


KOLEJNOSC = kolejnosc_blokow()

print("=== 1. PETLA BLOKOW W OGOLE SIE ZNAJDUJE ===")
# Bez tego cala reszta przechodzilaby na pustej liscie i test bylby o niczym.
sprawdz("znaleziona petla blokow", len(KOLEJNOSC) >= 8, KOLEJNOSC)
print("      kolejnosc: %s" % " -> ".join(KOLEJNOSC))

print()
print("=== 2. DYSKUSJE PRZED KOMENTARZAMI ===")
sprawdz("oba bloki nadal istnieja",
        "dyskusje" in KOLEJNOSC and "komentarze" in KOLEJNOSC, KOLEJNOSC)
if "dyskusje" in KOLEJNOSC and "komentarze" in KOLEJNOSC:
    i_d, i_k = KOLEJNOSC.index("dyskusje"), KOLEJNOSC.index("komentarze")
    sprawdz("dyskusje ida PRZED komentarzami (7 uciec na czasie wobec 3)",
            i_d < i_k, "dyskusje=%d komentarze=%d" % (i_d, i_k))
    # KONTRDOWOD: gdyby test porownywal cokolwiek innego niz pozycje, przeszedlby
    # takze przy odwroconej kolejnosci.
    sprawdz("KONTRDOWOD: odwrocona kolejnosc oblalaby to sprawdzenie",
            not (i_k < i_d))

print()
print("=== 3. ZAMIANA NICZEGO NIE ZGUBILA ===")
# Przestawianie krotki to najlatwiejszy sposob, zeby przypadkiem skasowac
# pozycje i nie zauwazyc: blok po prostu przestaje sie odpalac, bez bledu.
WYMAGANE = ("odpowiedzi", "notki", "obserwowanie", "subskrypcje", "dyskusje",
            "komentarze", "polubienia", "restacki", "zalegly artykul",
            "kopia listy")
for b in WYMAGANE:
    sprawdz("blok %-16s jest na liscie" % b, b in KOLEJNOSC)
sprawdz("i nie ma powtorzen", len(KOLEJNOSC) == len(set(KOLEJNOSC)),
        KOLEJNOSC)

print()
print("=== 4. PRZYDZIAL CELOWO NIETKNIETY ===")
# Zapis, ze to bylo DECYZJA, a nie przeoczenie. Gdyby ktos przestawil takze
# przydzial, ten test ma o tym powiedziec — nie dlatego, ze to zle, tylko
# dlatego, ze wtedy trzeba na nowo policzyc, na czym ta zmiana stoi.
sprawdz("artykuly nadal biora pelne `na_teraz[\"komentarze\"]`",
        'cele[: na_teraz["komentarze"]]' in ZR)
sprawdz("dyskusje nadal biora polowe",
        'cele[: max(1, na_teraz["komentarze"] // 2)]' in ZR)

print()
print("=== 5. POWOD ZMIANY STOI PRZY KODZIE ===")
# Liczba bez zapisanego pomiaru wraca za tydzien jako „chyba tak bylo".
for co, czego in (("liczba uciec dyskusji", "7 razy w 7 dni"),
                  ("rozmiar probki, ktora NIE wystarcza", "TRZYNASTU")):
    sprawdz("zapisana %s" % co, czego in ZR, czego)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
