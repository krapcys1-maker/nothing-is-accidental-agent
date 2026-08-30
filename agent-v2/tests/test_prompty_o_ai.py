# -*- coding: utf-8 -*-
"""Zaden prompt nie moze UCZYC na przykladach z epoki przedmiotow.

DLACZEGO TO POWSTALO. Konto przestawiono na AI 25 sierpnia i wtedy „przejrzano
wszystkie prompty". 30 sierpnia okazalo sie, ze osiem plikow nadal uczy modelu
na lotnictwie, konklawe, stacji benzynowej, szkolnym autobusie, anodzie na
kadlubie statku i symbolu otwartego sloika. Recznego przegladu nie da sie
powtarzac w kolko, wiec pilnuje tego test.

DLACZEGO TO GROZNE. Model nasladuje PRZYKLAD, nie regule. `restack.md` mowil
wprost, ze paralela z butelki szamponu jest poza tematem — i trzy akapity nizej
dawal jako wzorzec zdanie o regulacjach kosmetycznych. Zywy przebieg
wyprodukowal wtedy paralele o kremie nawilzajacym. Regula byla poprawiona,
przyklady nie.

CO JEST DOZWOLONE. Zapisy o WLASNYCH PORAZKACH zostaja i maja zostac: artykul o
symbolu otwartego sloika naprawde powstal i naprawde byl zly, a stara regula
grafiki naprawde dala laptop na szarym papierze. One ucza, czego NIE robic, i
same sie uniewazniaja. Dlatego kazde takie miejsce jest tu wypisane z osobna —
lista wyjatkow ma byc krotka i widoczna, zeby nikt nie dopisal do niej nowego
przykladu uczacego pod pozorem historii.

BEZ PYTESTA. Serwer go nie ma. Plik uruchamia sie z korzenia repozytorium.
"""
import pathlib
import re
import sys

PROMPTY = pathlib.Path("agent-v2/prompts")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# Slownictwo epoki przedmiotow. Nie jest to lista slow zakazanych w tresci —
# to lista slow, ktore w PROMPCIE znacza, ze uczymy modelu innego zawodu.
SPRZED_PRZESTAWIENIA = [
    "petrol station", "school bus", "school-bus", "tuna", "lighthouse",
    "conclave", "papal", "cardinals", "runway", "boil-water", "shampoo",
    "sunscreen", "traffic light", "crew rest", "airliner", "open-jar",
    "cosmetics", "fuel pump", "fuel-pump", "period-after-opening",
    "airline overbooking", "hotel overbooking", "sacrificial anode",
    "crumple zone", "ship's hull", "aircraft window", "vent hole",
    "bridge weight limit", "supermarket",
]

# Miejsca, gdzie takie slowo stoi CELOWO. Klucz to nazwa pliku, wartosc to
# fragmenty linii, ktore wolno przepuscic.
WYJATKI = {
    # Stara regula grafiki, nazwana po to, zeby jej nikt nie przywrocil.
    "grafika.md": ("built for a publication about everyday things",
                   "An article about the open-jar symbol on",
                   "cosmetics once got an actual glass jar"),
    # Zakaz, nie wzorzec: „paralela z butelki szamponu jest poza tematem".
    "restack.md": ("is off the subject",),
    # Zapisy wlasnej porazki — artykul, ktory trzeba bylo skasowac.
    "synteza.md": ("A piece that failed had none of this",),
    "warto_pisac.md": ("was dull, and the diagnosis was",),
    "wykonalnosc.md": ("exists. The subject was the open-jar symbol",),
}

pliki = sorted(PROMPTY.glob("*.md"))

print("=== 0. TEST, KTORY NIC NIE CZYTA, PRZECHODZI ZAWSZE ===")
sprawdz("znalazlem prompty do sprawdzenia (%d)" % len(pliki), len(pliki) >= 15)

print()
print("=== 1. ZADEN PROMPT NIE UCZY NA PRZEDMIOTACH ===")
wszystkie_trafienia = []
for plik in pliki:
    dozwolone = WYJATKI.get(plik.name, ())
    trafienia = []
    for nr, linia in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1):
        male = linia.lower()
        if any(w in linia for w in dozwolone):
            continue
        for slowo in SPRZED_PRZESTAWIENIA:
            if slowo in male:
                trafienia.append("%s:%d %r" % (plik.name, nr, slowo))
                break
    if trafienia:
        wszystkie_trafienia.extend(trafienia)
sprawdz("zaden prompt nie uczy na epoce przedmiotow",
        not wszystkie_trafienia,
        "; ".join(wszystkie_trafienia[:6]))

print()
print("=== 2. WYKRYWACZ NAPRAWDE COS WYKRYWA ===")
# KONTRDOWOD. Test szukajacy slow, ktorych juz nigdzie nie ma, przechodzilby
# rowniez wtedy, gdyby byl zepsuty. Sprawdzamy go na probce.
PROBKA = ["Everyone assumes the petrol station is holding their money.",
          "The papal conclave is the clean example.",
          "Aviation and cosmetics counts."]
zlapane = sum(1 for w in PROBKA
              if any(s in w.lower() for s in SPRZED_PRZESTAWIENIA))
sprawdz("lapie wszystkie trzy zdania z probki", zlapane == 3, zlapane)
sprawdz("i nie lapie zdania o naszym temacie",
        not any(s in "A model refusing a request is decided by a filter."
                .lower() for s in SPRZED_PRZESTAWIENIA))

print()
print("=== 3. LISTA WYJATKOW NIE ZGNILA ===")
# Wyjatek, ktory juz nic nie przepuszcza, ma zniknac. Inaczej lista rosnie i po
# roku przepuszcza wszystko, bo nikt nie pamieta, ktory wpis do czego byl.
martwe = []
for nazwa, fragmenty in WYJATKI.items():
    sciezka = PROMPTY / nazwa
    if not sciezka.exists():
        martwe.append("%s — pliku nie ma" % nazwa)
        continue
    tresc = sciezka.read_text(encoding="utf-8")
    for f in fragmenty:
        if f not in tresc:
            martwe.append("%s — %r juz nie wystepuje" % (nazwa, f))
sprawdz("kazdy wyjatek nadal cos przepuszcza", not martwe, "; ".join(martwe))

print()
print("=== 4. PROMPTY TEMATYCZNE NAZYWAJA TEMAT KONTA ===")
# `\s+`, NIE spacja. Prompty sa lamane na 79 znakow, wiec fraza „artificial
# intelligence" bywa przecieta koncem linii — pierwsza wersja tego testu
# oblewala na prompcie, ktory temat nazywal poprawnie, tylko w dwoch wierszach.
for nazwa in ("skaut.md", "ciekawostki.md", "bank.md", "warto_pisac.md"):
    sciezka = PROMPTY / nazwa
    if not sciezka.exists():
        sprawdz("%s istnieje" % nazwa, False)
        continue
    male = sciezka.read_text(encoding="utf-8").lower()
    sprawdz("%s nazywa temat konta" % nazwa,
            bool(re.search(r"artificial\s+intelligence|about\s+ai\b", male)))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
