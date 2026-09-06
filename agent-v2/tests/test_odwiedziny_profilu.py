# -*- coding: utf-8 -*-
"""Odwiedziny profilu i zapisania maja wlasne pola — bo to jest sygnal.

CO ZMIERZYLEM. Substack przysyla SIEDEM typow interakcji, a wlasne pole na
wierzchu rekordu mialy tylko cztery. Policzone na 3 911 rekordach statystyk:

    Like           2929   -> bylo
    Profile visit  1103   -> NIE BYLO
    Reply           625   -> bylo
    Restack         305   -> bylo
    Link click      204   -> bylo
    Share            71   -> jest jako `udostepnienia` z karty shareValues
    Save             62   -> NIE BYLO

ODWIEDZINY PROFILU TO DRUGI NAJCZESTSZY SYGNAL W CALYM ZBIORZE — i jedyny,
ktory mowi o KROKU PRZED SUBSKRYPCJA: ktos przeczytal i poszedl sprawdzic, kim
jestesmy. Lezal w slowniku `interakcje` i nie czytal go ANI JEDEN raport.

CO POKAZUJE, gdy sie go policzy (odwiedziny na 100 wyswietlen):

    odpowiedz  3,9   43% pozycji ma co najmniej jedna
    notka      1,4   33%
    komentarz  1,0    1%
    artykul    0,0    0%

Odpowiedzi maja najlepsza konwersje w calym systemie, a kosztuja 0,0020 USD —
najmniej ze wszystkiego, co robimy. I osobno: 35 notek mialo ponad 20
wyswietlen przy ZEROWEJ liczbie odwiedzin.

CZEGO TA ZMIANA NIE ROBI. Nie zmienia niczego w zachowaniu bota. Wystawia
liczbe, ktora juz mielismy, w miejsce, gdzie raport moze ja przeczytac.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_odwiedziny_profilu.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import statystyki   # noqa: E402

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


# Ksztalt WZIETY Z ZYWEGO API, nie wymyslony: karty maja `items`, a nie `rows`.
# Pierwsza wersja tego testu uzywala `rows` i wszystkie pola wychodzily zerowe,
# takze `polubienia` — czyli test sprawdzalby moje wyobrazenie o odpowiedzi.
KARTY = {"cards": [
    {"cardId": "interactions", "items": [
        {"title": "Like", "value": 5},
        {"title": "Profile visit", "value": 3},
        {"title": "Save", "value": 2},
        {"title": "Reply", "value": 1},
        {"title": "Restack", "value": 4},
        {"title": "Link click", "value": 6},
    ]},
    {"cardId": "impressionValues", "items": [{"title": "Impressions", "value": 40}]},
]}

r = statystyki.z_kart(KARTY)

print("=== 1. NOWE POLA SA NA WIERZCHU ===")
sprawdz("odwiedziny_profilu = 3", r.get("odwiedziny_profilu") == 3,
        r.get("odwiedziny_profilu"))
sprawdz("zapisane = 2", r.get("zapisane") == 2, r.get("zapisane"))

print()
print("=== 2. STARE POLA NIETKNIETE ===")
for pole, ile in (("polubienia", 5), ("odpowiedzi", 1), ("restacki", 4),
                  ("klikniecia_w_link", 6)):
    sprawdz("%-18s = %d" % (pole, ile), r.get(pole) == ile, r.get(pole))

print()
print("=== 3. SLOWNIK INTERAKCJI NADAL NIESIE WSZYSTKO ===")
# Tabela nazw NIE jest filtrem — nowy, nieznany typ ma dalej trafiac do
# slownika, nawet gdy nie dostanie wlasnego pola.
sprawdz("Profile visit jest w slowniku",
        (r.get("interakcje") or {}).get("Profile visit") == 3, r.get("interakcje"))
_z_nowym = statystyki.z_kart({"cards": [
    {"cardId": "interactions", "items": [{"title": "Czegos Takiego", "value": 9}]}]})
sprawdz("nieznany typ tez trafia do slownika",
        (_z_nowym.get("interakcje") or {}).get("Czegos Takiego") == 9,
        _z_nowym.get("interakcje"))

print()
print("=== 4. BEZ KART POLA NADAL ISTNIEJA I SA ZEREM ===")
# Raport, ktory raz dostaje pole, a raz nie, wywala sie na pierwszej pozycji,
# ktorej nikt nie polubil.
pusty = statystyki.z_kart({"cards": []})
for pole in ("odwiedziny_profilu", "zapisane", "polubienia", "obserwacje"):
    sprawdz("%-18s jest i wynosi 0" % pole, pusty.get(pole) == 0, pusty.get(pole))

print()
print("=== 5. DWA POLA, KTORE ZOSTAJA ZEROWE Z POWODU, NIE Z BLEDU ===")
# `obserwacje`: Substack nie przyslal „Follow" ani razu w 3 911 rekordach —
# obserwowanie dzieje sie na profilu, nie pod notka.
# `zapisy_platne`: konto nie ma platnego poziomu.
_zr = pathlib.Path("agent-v2/statystyki.py").read_text(encoding="utf-8")
sprawdz("powod pustego `obserwacje` zapisany przy kodzie",
        "nie przyslal go ANI RAZU" in _zr)
sprawdz("i powod pustego `zapisy_platne`",
        "konto nie ma platnego" in _zr)
sprawdz("`obserwacje` NADAL jest w polach zerowych",
        "obserwacje" in statystyki.POLA_ZEROWE)

print()
print("=== 6. NAZWY ODPORNE NA LICZBE MNOGA ===")
# Substack pisze raz „Profile visit", raz moze „Profile visits". Tabela ma oba.
for tytul in ("Profile visit", "Profile visits", "profile visit"):
    w = statystyki.z_kart({"cards": [
        {"cardId": "interactions", "items": [{"title": tytul, "value": 7}]}]})
    sprawdz("%-16s -> odwiedziny_profilu" % tytul,
            w.get("odwiedziny_profilu") == 7, w.get("odwiedziny_profilu"))
for tytul in ("Save", "Saves"):
    w = statystyki.z_kart({"cards": [
        {"cardId": "interactions", "items": [{"title": tytul, "value": 4}]}]})
    sprawdz("%-16s -> zapisane" % tytul, w.get("zapisane") == 4, w.get("zapisane"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
