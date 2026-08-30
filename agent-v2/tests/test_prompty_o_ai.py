# -*- coding: utf-8 -*-
"""Zaden prompt nie moze UCZYC na przykladach z epoki przedmiotow.

DLACZEGO TO POWSTALO. Konto przestawiono na AI 25 sierpnia i wtedy „przejrzano
wszystkie 25 promptow". 30 sierpnia okazalo sie, ze osiem plikow nadal uczy
modelu na lotnictwie, konklawe, stacji benzynowej, szkolnym autobusie, anodzie
na kadlubie statku i symbolu otwartego sloika. Recznego przegladu nie da sie
powtorzyc w kolko, wiec pilnuje tego test.

DLACZEGO TO GROZNE. Model nasladuje PRZYKLAD, nie regule. `restack.md` mowil
wprost, ze paralela z butelki szamponu jest poza tematem — i trzy akapity nizej
dawal jako wzorzec zdanie o regulacjach kosmetycznych. Zywy przebieg wyprodukowal
wtedy paralele o kremie nawilzajacym. Regula byla poprawiona, przyklady nie.

CO JEST DOZWOLONE. Zapisy o WLASNYCH PORAZKACH zostaja i maja zostac: artykul o
symbolu otwartego sloika naprawde powstal i naprawde byl zly, a stara regula
grafiki naprawde dala laptop na szarym papierze. One ucza, czego NIE robic, i
same sie uniewazniaja. Dlatego kazde takie miejsce jest tu wypisane z osobna —
lista wyjatkow ma byc krotka i widoczna, zeby nikt nie dopisal do niej nowego
przykladu uczacego pod pozorem historii.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTY = Path(__file__).resolve().parent.parent / "prompts"

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

# Miejsca, gdzie takie slowo stoi CELOWO, bo opisuje wlasna porazke albo
# wprost jej zakazuje. Klucz to nazwa pliku, wartosc to fragmenty linii,
# ktore wolno przepuscic.
WYJATKI: dict[str, tuple[str, ...]] = {
    # Stara regula grafiki, nazwana po to, zeby jej nikt nie przywrocil.
    "grafika.md": (
        "built for a publication about everyday things",
        "An article about the open-jar symbol on",
        "cosmetics once got an actual glass jar",
    ),
    # Zakaz, nie wzorzec: „paralela z butelki szamponu jest poza tematem".
    "restack.md": ("is off the subject",),
    # Zapisy wlasnej porazki — artykul, ktory trzeba bylo skasowac.
    "synteza.md": ("A piece that failed had none of this",),
    "warto_pisac.md": ("was dull, and the diagnosis was",),
    "wykonalnosc.md": ("exists. The subject was the open-jar symbol",),
}


def _pliki() -> list[Path]:
    return sorted(PROMPTY.glob("*.md"))


def test_sa_jakies_prompty():
    """Test, ktory nic nie czyta, przechodzi zawsze. Najpierw upewnij sie."""
    assert len(_pliki()) >= 15, "spodziewam sie kilkunastu promptow"


def _dozwolone(plik: Path, linia: str) -> bool:
    return any(w in linia for w in WYJATKI.get(plik.name, ()))


@pytest.mark.parametrize("plik", _pliki(), ids=lambda p: p.name)
def test_prompt_nie_uczy_na_przedmiotach(plik: Path):
    trafienia = []
    for nr, linia in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1):
        male = linia.lower()
        for slowo in SPRZED_PRZESTAWIENIA:
            if slowo in male and not _dozwolone(plik, linia):
                trafienia.append("  %s:%d  %r  -> %s"
                                 % (plik.name, nr, slowo, linia.strip()[:88]))
                break
    assert not trafienia, (
        "prompt uczy na przykladach sprzed przestawienia konta na AI.\n"
        "Jesli to zapis wlasnej porazki, dopisz go do WYJATKI z komentarzem.\n"
        + "\n".join(trafienia))


def test_lista_wyjatkow_nie_zgnila():
    """Wyjatek, ktory juz nic nie przepuszcza, ma zniknac.

    Inaczej lista rosnie i po roku przepuszcza wszystko, bo nikt nie pamieta,
    ktory wpis do czego byl.
    """
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
    assert not martwe, "martwe wyjatki do usuniecia:\n  " + "\n  ".join(martwe)


def test_kazdy_prompt_mowi_o_czym_jest_konto():
    """Prompty, ktore opisuja TEMAT, musza nazwac go wprost.

    Nie wszystkie — `grafika.md` czy `komentarz.md` maja inna robote. Ale te,
    ktore proponuja albo oceniaja tematy, nie moga zostawiac dziedziny domysli.
    """
    tematyczne = ["skaut.md", "ciekawostki.md", "bank.md", "warto_pisac.md"]
    braki = []
    for nazwa in tematyczne:
        sciezka = PROMPTY / nazwa
        if not sciezka.exists():
            braki.append("%s — brak pliku" % nazwa)
            continue
        male = sciezka.read_text(encoding="utf-8").lower()
        # `\s+`, NIE spacja. Prompty sa lamane na 79 znakow, wiec fraza
        # „artificial intelligence" bywa przecieta koncem linii — pierwsza
        # wersja tego testu oblewala na prompcie, ktory temat nazywal
        # poprawnie, tylko w dwoch wierszach.
        if not re.search(r"artificial\s+intelligence|about\s+ai\b", male):
            braki.append("%s — nie nazywa tematu konta" % nazwa)
    assert not braki, "\n  ".join(braki)


if __name__ == "__main__":
    # Testy w tym repozytorium sa URUCHAMIANE JAKO SKRYPTY, po jednym pliku.
    # Bez tego bloku plik odpalony recznie nie zrobilby nic i wyszedl zerem —
    # czyli wygladalby na test, ktory przeszedl, nie wykonawszy niczego.
    import sys as _sys
    _sys.exit(pytest.main([__file__, "-q"]))
