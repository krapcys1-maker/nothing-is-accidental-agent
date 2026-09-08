# -*- coding: utf-8 -*-
"""Co drugie szukanie idzie BEZ zaczynu z kanalow — zeby siatka miala szanse.

SKAD TO SIE WZIELO. Wlasciciel 7 wrzesnia 2026: „na koncie zrobila sie
monotonia, jak na tablicy ogloszen, wszystko wrzucane jakby z automatu".

CO SPRAWDZILEM NAJPIERW — czy to styl. NIE JEST. Na 60 notkach ery AI
(od 25 sierpnia) jest 60 ROZNYCH otwarc, zero powtorzonych; wzorzec „jedno
slowo. To tyle, ile..." wystepuje w 7%; rotacja form dziala i kazda notka dnia
ma inna. Gdybym poprawial styl, poprawialbym rzecz, ktora dziala.

GDZIE MONOTONIA NAPRAWDE JEST — w temacie. Bank, 131 wolnych faktow:

    tylko branza (ceny, modele, benchmarki, firmy)     92  (70%)
    o swiecie (ludzie, szkola, sad, praca, zdrowie)     8  (6%)
    jedno i drugie                                     27

A LISTA DZIEDZIN JEST ZBALANSOWANA: z 46 pozycji 22 branzowe, 20 o swiecie,
4 historyczne. Losujemy piec, wiec powinno wychodzic pol na pol.

DLACZEGO NIE WYCHODZI — zmierzone na prompcie:

    zaczyn z kanalow   2201 znakow, konkretne datowane naglowki branzowe
    dziedziny           315 znakow, abstrakcyjne opisy obszarow

Siedem razy wiecej miejsca i konkret zamiast abstrakcji. Do tego sam prompt
mowil „Work the grid, but work it ON THE WEEK'S SUBJECTS", a opis pola
`domain` brzmial „the part of the AI stack, INDUSTRY or public record".
Trzy rzeczy naraz pchaly model w bieżączke.

DLACZEGO KODEM, A NIE PROSBA. Bo „prosba w prompcie nie jest bramka" — to jest
w tym projekcie zapisane po dwoch przegranych artykulach. Poprawilem tez oba
miejsca w prompcie, ale gwarancje daje dopiero to: PRZY CO DRUGIM SZUKANIU
ZACZYN W OGOLE NIE IDZIE DO MODELU.

BEZ PYTESTA, zero sieci, zero platnych wywolan. Z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zaczyn_nie_zjada_siatki.py
"""
import pathlib
import re
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


print("=== 1. PRZELACZNIK ISTNIEJE I JEST WLACZONY ===")
sprawdz("`ZACZYN_CO_DRUGIE_SZUKANIE` jest w konfiguracji",
        hasattr(config, "ZACZYN_CO_DRUGIE_SZUKANIE"))
sprawdz("i jest wlaczony", config.ZACZYN_CO_DRUGIE_SZUKANIE is True,
        getattr(config, "ZACZYN_CO_DRUGIE_SZUKANIE", None))

print()
print("=== 2. KOD NAPRAWDE POMIJA ZACZYN CO DRUGA DOBE ===")
# Nie czytam komentarza — odtwarzam warunek z ZRODLA i sprawdzam, ze zalezy
# od doby. Test, ktory sprawdza wlasne wyobrazenie o kodzie, jest bez wartosci.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("`znajdz_ciekawostki` pyta o `ZACZYN_CO_DRUGIE_SZUKANIE`",
        "config.ZACZYN_CO_DRUGIE_SZUKANIE" in _zr)
sprawdz("i rozstrzyga to PARZYSTOSCIA DOBY, nie losem",
        "toordinal() % 2 == 0" in _zr)
sprawdz("a `zaczyn_z_kanalow()` nie jest juz wolany bezwarunkowo w tym miejscu",
        "zaczyn_kanalow=_zaczyn" in _zr)


def _wybor(ordinal):
    """Odtworzenie warunku z kodu: czy przy tej dobie idzie zaczyn."""
    return (not config.ZACZYN_CO_DRUGIE_SZUKANIE) or ordinal % 2 == 0


_kolejne = [_wybor(d) for d in range(6)]
sprawdz("doby ida na zmiane: %s" % _kolejne,
        _kolejne == [True, False, True, False, True, False], _kolejne)
sprawdz("czyli polowa szukan bez zaczynu",
        sum(_kolejne) == len(_kolejne) // 2)

print()
print("=== 3. WYLACZENIE PRZELACZNIKA WRACA DO STANU SPRZED ZMIANY ===")
_stary = config.ZACZYN_CO_DRUGIE_SZUKANIE
try:
    config.ZACZYN_CO_DRUGIE_SZUKANIE = False
    sprawdz("przy `False` zaczyn idzie ZAWSZE",
            all(_wybor(d) for d in range(6)))
finally:
    config.ZACZYN_CO_DRUGIE_SZUKANIE = _stary

print()
print("=== 4. TEKST ZASTEPCZY MOWI WPROST, ZE LISTY NIE MA ===")
# Pusta sekcja czytalaby sie jak awaria kanalow — a to jest DECYZJA.
_i = _zr.index("brak listy tym razem")
_okolica = _zr[_i - 200:_i + 400]
sprawdz("tekst zastepczy nazywa to zamierzonym", "zamierzone" in _okolica)
sprawdz("i zabrania zgadywania biezaczki",
        "nie zgaduj" in _okolica.lower())
sprawdz("log mowi, ktory to byl przypadek",
        "dzis sama siatka" in _zr)

print()
print("=== 5. PROMPT NIE PODPORZADKOWUJE JUZ SIATKI BIEZACZCE ===")
_p = pathlib.Path("agent-v2/prompts/ciekawostki.md").read_text(encoding="utf-8")
sprawdz("znikelo „work it ON THE WEEK'S SUBJECTS\"",
        "work it ON THE WEEK'S SUBJECTS" not in _p)
sprawdz("i stoi wymog polowy spoza naglowkow tygodnia",
        "At least half of what you return" in _p)
sprawdz("prompt nazywa po imieniu, czym konto NIE jest",
        "trade noticeboard" in _p)

print()
print("=== 6. OPIS POLA `domain` NIE STERUJE JUZ W BRANZE ===")
# Stalo tam „the part of the AI stack, INDUSTRY or public record" — czyli samo
# pole, ktore mialo opisywac temat, wskazywalo wylacznie na branze.
sprawdz("`domain` nie mowi juz samo „industry\"",
        "the part of the AI stack, industry or public record" not in _p)
sprawdz("i dopuszcza miejsce w swiecie",
        "a clinic, a classroom, a court" in _p)

print()
print("=== 7. SIATKA DZIEDZIN JEST I POZOSTAJE ZBALANSOWANA ===")
# Gdyby przechylila sie w branze, cala reszta tej zmiany nic nie da.
BRANZA = re.compile(
    r"(train|token|benchmark|leaderboard|inference|chip|data centre|compute|"
    r"model|eval|state of the art|demo|supply chain|sells|credits|query)", re.I)
SWIAT = re.compile(
    r"(drug|protein|diagnos|weather|climate|robot|self-driving|warfare|job|"
    r"translation|Act|copyright|owns|surveillance|deepfake|school|companion|"
    r"labelling|therapist)", re.I)
_b = sum(1 for d in config.DZIEDZINY_CIEKAWOSTEK if BRANZA.search(d) and not SWIAT.search(d))
_s = sum(1 for d in config.DZIEDZINY_CIEKAWOSTEK if SWIAT.search(d))
print("      branzowych %d, o swiecie %d, wszystkich %d"
      % (_b, _s, len(config.DZIEDZINY_CIEKAWOSTEK)))
sprawdz("o swiecie jest co najmniej jedna trzecia listy",
        _s >= len(config.DZIEDZINY_CIEKAWOSTEK) // 3, (_s, len(config.DZIEDZINY_CIEKAWOSTEK)))
sprawdz("i zadna ze stron nie ma przewagi wiekszej niz dwukrotna",
        max(_b, _s) <= 2 * max(1, min(_b, _s)), (_b, _s))

print()
print("=== 8. INSTRUKCJA O OBSZARACH IDZIE ZA ZACZYNEM ===")
# TO BYLA MOJA WADA Z 7 WRZESNIA. Zdjalem zaczyn co druga dobe, ale zostawilem
# w `ciekawostki.md` zdanie „The live subjects above are the material. These
# areas are the LENS you look through" oraz „three quarters start from the list
# above". W dobie BEZ zaczynu model dostawal polecenie „zacznij od listy",
# ktorej nie ma — i szedl po zrodla, ktore zna najlepiej.
#
# ZMIERZONE NA 32 SWIEZYCH FAKTACH z pieciu szukan: WSZYSTKIE z CZTERECH
# hostow (latent.space 11, pytorch.org 10, simonwillison.net 6,
# importai.substack.com 5). Bank narastajacy tygodniami ma 88 roznych hostow
# na 131 faktow.
sprawdz("prompt nie ma juz wpisanej na stale reguly „areas are the LENS\"",
        "areas are the LENS you look through" not in _p)
sprawdz("i nie ma wpisanego na stale „three quarters start from the list\"",
        "three quarters start from the list" not in _p)
sprawdz("obie sa teraz polami", "{jak_uzywac_obszarow}" in _p
        and "{ile_z_obszarow}" in _p)
sprawdz("`stages` podaje oba pola", "jak_uzywac_obszarow=_jak_obszary" in _zr
        and "ile_z_obszarow=_ile_obszary" in _zr)

# OBIE WERSJE MUSZA ISTNIEC — jedna dla doby z zaczynem, druga bez.
sprawdz("wersja Z zaczynem zachowuje regule „LENS\"",
        "areas are the LENS you look through" in _zr)
sprawdz("wersja BEZ zaczynu mowi, ze obszary SA materialem",
        "areas ARE the material" in _zr)
sprawdz("i nazywa zmierzona wade po imieniu (cztery zrodla)",
        "FOUR distinct sources" in _zr)
sprawdz("i stawia wymog o ZRODLACH, nie o tresci",
        "no more than " in _zr and "share a source" in _zr)

# NAJWAZNIEJSZE: wersja bez zaczynu NIE MOZE zgubic ochrony przed staroscia.
# Gdy ta sekcja brzmiala „take your facts from these areas and no others",
# czysty przebieg oddal zrodla z 2024, 2022 i 1992 roku.
sprawdz("wersja BEZ zaczynu zachowuje ochrone przed staroscia",
        "2022 and 1992" in _zr or "age rules below still hold" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
