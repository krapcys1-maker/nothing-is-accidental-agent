# -*- coding: utf-8 -*-
"""Druga runda dyskoverii patrzy na REKORDY, nie tylko na sztuki.

CO ZGLASZA AUDYT (M6). `run.py` odpala druga runde takze wtedy, gdy zrodel
pierwotnych jest mniej niz `MIN_PRIMARY_SOURCES`, i wola wtedy dyskoverie
z `tylko_pierwotne=True`. `artykul_z_puli._przebieg` mial sam warunek „mniej
niz 4 pobrane". Produkcja chodzi ta druga sciezka.

DLACZEGO TO NIE JEST KOSMETYKA. `run.py` ma powod zapisany z pomiaru: korpus
bywa PELNY i jednoczesnie bezwartosciowy — przebieg z dziewiecioma pobranymi
zrodlami, z czego JEDNO pierwotne. Dziewiec jest duzo powyzej progu czterech,
wiec warunek na sztuki nie odpalal sie nigdy, a pisarz dostawal dziewiec
tekstow O dokumencie i ani jednego dokumentu.

CO ZMIERZYLEM NA PRODUKCJI. Zapytaniem z audytu, na zywej bazie:

    run 106   pobrane 6    pierwotne 4    artykul
    run  77   pobrane 7    pierwotne 4    artykul-z-puli
    run  76   pobrane 10   pierwotne 10   artykul-z-puli

Wszystkie powyzej progu dwoch. WIEC TO JEST NAPRAWA RYZYKA, NIE ZAOBSERWOWANEJ
SZKODY — i tyle jest warta. Mowie to wprost, zeby nikt nie szukal poprawy w
tekstach, ktorej nie bedzie.

PRZY OKAZJI DWIE RZECZY, KTORYCH AUDYT NIE WYMIENIL:
  * komentarz nad tym blokiem mowil „tak samo jak w run.py" i BYL NIEPRAWDA —
    to jest dokladnie ten rodzaj komentarza, ktory kaze nie sprawdzac;
  * odsiew szedl po URL, a w `run.py` po HOSCIE. Po samym URL-u ten sam serwis
    wchodzil drugi raz pod innym adresem, wiec druga runda potrafila oddac to,
    co juz bylo — i zaplacic za to.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_druga_runda_widzi_rekordy.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

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


_zr = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
_blok = _zr.split("DRUGA RUNDA")[1].split("-- klasyfikacja --")[0] \
    if "DRUGA RUNDA" in _zr else ""

print("=== 1. WARUNEK PATRZY NA JEDNO I DRUGIE ===")
sprawdz("blok drugiej rundy w ogole istnieje", bool(_blok), len(_blok))
sprawdz("liczy zrodla pierwotne", 'c.get("class") == "PRIMARY"' in _blok)
sprawdz("porownuje z MIN_PRIMARY_SOURCES",
        "config.MIN_PRIMARY_SOURCES" in _blok)
sprawdz("i nadal z progiem liczby zrodel",
        "config.MIN_ZRODEL_DO_PISANIA" in _blok)
sprawdz("odpala przy KTORYMKOLWIEK z dwoch",
        "_za_chudo or _bez_rekordow" in _blok)

print()
print("=== 2. PROG Z CONFIGU, NIE WPISANY W KOD ===")
# Dwa miejsca liczace to samo z dwoch roznych liczb rozjezdzaja sie po
# pierwszej zmianie. Przedtem stala tu wpisana czworka.
sprawdz("nie ma juz wpisanej czworki w warunku",
        "< 4:" not in _blok, [w for w in _blok.split("\n") if "< 4" in w])
sprawdz("progi sa liczbami, ktore config naprawde ma",
        isinstance(config.MIN_PRIMARY_SOURCES, int)
        and isinstance(config.MIN_ZRODEL_DO_PISANIA, int),
        (config.MIN_PRIMARY_SOURCES, config.MIN_ZRODEL_DO_PISANIA))

print()
print("=== 3. DRUGA RUNDA SZUKA WTEDY SAMYCH REKORDOW ===")
# Bez tego druga runda oddaje kolejne omowienia — czyli placimy 0,28 USD za
# wiecej tego samego.
sprawdz("wola dyskoverie z tylko_pierwotne",
        "tylko_pierwotne=_bez_rekordow" in _blok)
sprawdz("i wiaze to z BRAKIEM REKORDOW, nie z chudym korpusem",
        "tylko_pierwotne=_za_chudo" not in _blok)

print()
print("=== 4. ODSIEW PO HOSCIE, NIE PO URL ===")
sprawdz("odsiew liczony z hosta", 'c.get("host") or c.get("url", "")' in _blok)
sprawdz("nowe zrodla tez porownywane po hoscie",
        's.get("host") or s.get("url", "")' in _blok)

print()
print("=== 5. TA SAMA REGULA CO W run.py ===")
# Zrodlo prawdy jest jedno; gdy `run.py` zmieni regule, ten test ma zapiszczec.
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("run.py nadal ma oba warunki",
        "config.MIN_PRIMARY_SOURCES" in _run and "za_chudo or bez_rekordow" in _run)
sprawdz("run.py nadal wola tylko_pierwotne przy braku rekordow",
        "tylko_pierwotne=bez_rekordow" in _run)
sprawdz("stages.discovery faktycznie przyjmuje ten argument",
        "tylko_pierwotne: bool = False"
        in pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
