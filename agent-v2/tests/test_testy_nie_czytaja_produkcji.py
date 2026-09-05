# -*- coding: utf-8 -*-
"""Test, ktory siega po produkcje, najpierw sie od niej odcina.

SKAD SIE WZIAL. 5 wrzesnia 2026 uruchomilem zestaw NA SERWERZE po wdrozeniu.
Dwa testy przechodzily na Windows i padaly na Linuksie. Zaden z nich nie mial
nic wspolnego z systemem — czytaly ZYWY dziennik wystawionych tresci, wiec ich
werdykt zalezal od tego, co bot zdazyl napisac:

    test_wspolna_nazwa      -> `opublikowane_teksty()` przez `wybierz_material`
    test_straznik_powtorek  -> `opublikowane_teksty()` przez `dopisz_kandydatow`

TO NIE BYL DROBIAZG HIGIENICZNY. Pod pierwszym z nich siedzialy DWIE prawdziwe
usterki produkcyjne (patrz `test_zapora_nazw_nie_slabnie.py`) — nie bylo jak
ich zobaczyc, dopoki test dawal inny wynik na kazdej maszynie. Drugi oblewal
na darmowym filtrze „JUZ O TYM PISALISMY", zanim badany straznik zdazyl
cokolwiek powiedziec, czyli na czyms, czego nie bada.

ZAPIS DO PRODUKCJI JEST JUZ CHRONIONY — `config.W_TESCIE` rozpoznaje darmowy
test po sciezce programu, patrz `test_testy_nie_pisza_do_produkcji.py`. Tamta
zapora nie obejmuje ODCZYTU i o niego chodzi tutaj.

LISTA WEJSC JEST KROTKA CELOWO. Pierwsza wersja tego testu wymagala odciecia
od KAZDEGO testu importujacego `stages` i wskazala 78 plikow. To bylaby regula
szersza niz usterka — ten sam blad, co wzorzec `*klucz*` zjadajacy plik testu
(patrz commit z tego samego dnia). Wiekszosc tych testow siega po funkcje
czyste i nie ma czego zepsuc.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_testy_nie_czytaja_produkcji.py
"""
import pathlib
import sys
import tempfile

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


# DWIE KLASY WEJSC, BO DWA ROZNE ZRODLA — i dwa rozne sposoby odciecia.
#
# DZIENNIK wystawionych tresci czyta `opublikowane_teksty()`. Siega po niego
# takze `wybierz_material` i `dopisz_kandydatow`, w srodku, bez argumentu.
# Jedyne odciecie to `config.uzyj_katalogu_danych`.
CZYTAJA_DZIENNIK = (
    "opublikowane_teksty",
    "wybierz_material",
    "dopisz_kandydatow",
)

# INDEKS KANDYDATOW to plik wskazywany stala modulowa. Kilka testow przestawia
# ja wprost (`stages.INDEKS_KANDYDATOW = ...`) i to WYSTARCZA — plik jest
# wtedy tymczasowy. Wymaganie od nich pelnego `uzyj_katalogu_danych` byloby
# regula szersza niz usterka.
CZYTAJA_INDEKS = (
    "wez_kandydatow",
    "wczytaj_indeks",
)

CZYTAJA_PRODUKCJE = CZYTAJA_DZIENNIK + CZYTAJA_INDEKS

def _bez_opisow(tresc: str) -> str:
    """Kod bez komentarzy i bez tekstow w potrojnych cudzyslowach.

    Zachowuje DLUGOSC — kazdy usuniety znak zastapiony spacja — zeby pozycje
    liczone w wyniku zgadzaly sie z pozycjami w oryginale. Bez tego porownanie
    „odciecie przed wywolaniem" przesuwa sie o dlugosc wycietych opisow.
    """
    znaki = list(tresc)
    i = 0
    while i < len(znaki):
        if tresc.startswith('"""', i) or tresc.startswith("'''", i):
            znacznik = tresc[i:i + 3]
            koniec = tresc.find(znacznik, i + 3)
            koniec = len(tresc) if koniec < 0 else koniec + 3
            for j in range(i, koniec):
                if znaki[j] != chr(10):
                    znaki[j] = " "
            i = koniec
            continue
        if znaki[i] == "#":
            while i < len(znaki) and znaki[i] != chr(10):
                znaki[i] = " "
                i += 1
            continue
        i += 1
    return "".join(znaki)


TEN_PLIK = pathlib.Path(__file__).name
pliki = sorted(pathlib.Path("agent-v2/tests").glob("test_*.py"))

print("=== 1. TESTY SIEGAJACE PO PRODUKCJE ODCINAJA SIE OD NIEJ ===")
print("    (przejrzanych plikow: %d)" % len(pliki))

bez_odciecia = []
za_pozno = []
sprawdzonych = 0
for plik in pliki:
    if plik.name == TEN_PLIK:
        continue
    tresc = plik.read_text(encoding="utf-8")
    # SAM KOD: bez komentarzy I BEZ DOCSTRINGOW. Opisy w tym repozytorium sa
    # dluzsze od kodu i cytuja w nim produkcyjne wywolania — `test_artykul_
    # nie_glodzony` ma `stages.wez_kandydatow(ile)` w docstringu w 10 wierszu,
    # czyli 36 wierszy przed wlasnym odcieciem. Odsiew po samych `#` uznawal
    # to za wywolanie i zglaszal test, ktory jest w porzadku.
    kod = _bez_opisow(tresc)
    uzycia = [f for f in CZYTAJA_PRODUKCJE if (f + "(") in kod]
    if not uzycia:
        continue
    sprawdzonych += 1
    # POZYCJE LICZONE W TYM SAMYM LANCUCHU. Pierwsza wersja brala jedna
    # z `tresc`, a druga z `kod` (bez komentarzy) i porownywala je ze soba —
    # przesuniete o dlugosc wycietych komentarzy, czyli o tysiace znakow.
    # Dawalo to falszywe alarmy na testach, ktore sa w porzadku.
    gdzie_odciecie = kod.find("uzyj_katalogu_danych(")
    if gdzie_odciecie < 0:
        # Sam indeks wystarczy odciac przestawieniem stalej modulowej.
        tylko_indeks = all(f in CZYTAJA_INDEKS for f in uzycia)
        if tylko_indeks and "INDEKS_KANDYDATOW =" in kod:
            continue
        bez_odciecia.append("%s -> %s" % (plik.name, ", ".join(uzycia)))
        continue
    # Odciecie ma stac przed PIERWSZYM wywolaniem, ktore siega po produkcje —
    # a nie przed importem modulu.
    #
    # Pierwsza wersja pytala „czy przed `import stages`" i wskazala
    # `test_obserwacje.py`, ktory robi to POPRAWNIE: przestawia katalog
    # zakresowo, w bloku `with`, i przywraca stan. Heurystyka byla zla, nie
    # test. Zapisuje to, bo jest to trzeci raz tego samego dnia, gdy regula
    # wychodzila szersza niz usterka.
    pierwsze_wywolanie = min(kod.index(f + "(") for f in uzycia)
    if gdzie_odciecie > pierwsze_wywolanie:
        za_pozno.append(plik.name)

print("    (z tego siegajacych po produkcje: %d)" % sprawdzonych)
sprawdz("kazdy taki test przestawia katalog danych",
        not bez_odciecia, bez_odciecia)
sprawdz("i robi to PRZED importem badanego modulu", not za_pozno, za_pozno)

print()
print("=== 2. KONTROLA PRZYRZADU: ODCIECIE NAPRAWDE ODCINA ===")
# Bez tej sekcji sekcja 1 sprawdzalaby OBECNOSC NAPISU w pliku, a nie skutek —
# czyli dokladnie ten rodzaj testu, ktory przechodzi, nie badajac niczego.
sys.path.insert(0, "agent-v2")
import config     # noqa: E402

_kat = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(_kat)
sprawdz("DATA_DIR wskazuje na katalog tymczasowy",
        str(config.DATA_DIR) == str(_kat), config.DATA_DIR)

import stages     # noqa: E402

sprawdz("korpus opublikowanych tekstow jest pusty",
        stages.opublikowane_teksty() == [],
        len(stages.opublikowane_teksty()))
sprawdz("indeks kandydatow lezy w katalogu tymczasowym",
        str(_kat) in str(stages.INDEKS_KANDYDATOW), stages.INDEKS_KANDYDATOW)

print()
print("=== 3. LISTA WEJSC NIE ZDEZAKTUALIZOWALA SIE ===")
# Gdyby ktorakolwiek z tych funkcji zniknela albo zmienila nazwe, sekcja 1
# przestalaby cokolwiek sprawdzac — po cichu, bo `in kod` po prostu nie trafi.
for nazwa in CZYTAJA_PRODUKCJE:
    sprawdz("stages nadal ma %s" % nazwa, hasattr(stages, nazwa))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
