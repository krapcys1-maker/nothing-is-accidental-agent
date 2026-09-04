# -*- coding: utf-8 -*-
"""Przebieg sprawdzajacy nie zabiera slotu publikacyjnego ani budzetu.

CO SIE STALO 4 wrzesnia 2026. Sprawdzalem dzienne zmiany przebiegami bez
`--wyslij`. Kolumna `runs.tryb` istniala od dawna, ale `run.py` jej nie
ustawial, wiec KAZDY przebieg zapisywal sie jako „produkcja" — takze taki,
ktory niczego nie publikuje. Skutki:

  * `ile_przebiegow_zostalo` dzieli dzienna norme przez przebiegi zamkniete
    dzis. Trzy sprawdzenia zabraly trzy z pieciu slotow, wiec dzien skonczyl
    sie na DWOCH notkach z dziesieciu — i nie byla to wina bramek;
  * audyt kosztow rozdziela wydatki po tym samym polu, wiec pieniadze wydane
    na sprawdzanie liczyly sie do produkcyjnego sufitu dnia.

CZEGO TEN TEST PILNUJE. Ze sprawdzenie jest darmowe w OBU ksiegach, i ze
stara regula — „przebieg PRZERWANY liczy sie tak samo" — nadal obowiazuje
przebiegi produkcyjne, bo tam czas naprawde uplynal.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_sprawdzenie_nie_zabiera_slotu.py
Zero wywolan modelu, zero sieci, baza w katalogu tymczasowym.
"""
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, "agent-v2")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


import config  # noqa: E402

_kat = tempfile.mkdtemp(prefix="nia-slot-")
config.DATA_DIR = pathlib.Path(_kat)
config.DB_PATH = pathlib.Path(_kat) / "agent.db"

import db   # noqa: E402
import run  # noqa: E402

conn = db.connect()
DZIS = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def zamknij(tryb):
    """Jeden zakonczony przebieg dnia w danym trybie."""
    rid = db.start_run(conn, stage="dzien", tryb=tryb)
    db.finish_run(conn, rid, "DONE")
    return rid


print("=== 1. STAN WYJSCIOWY ===")
sprawdz("na czysto zostaje caly komplet przebiegow",
        run.ile_przebiegow_zostalo(conn) == config.PRZEBIEGOW_DZIENNIE,
        run.ile_przebiegow_zostalo(conn))

print()
print("=== 2. SPRAWDZENIA NIE ZABIERAJA SLOTOW ===")
for i in range(3):
    zamknij("test")
sprawdz("trzy przebiegi sprawdzajace nie zabraly ani jednego slotu",
        run.ile_przebiegow_zostalo(conn) == config.PRZEBIEGOW_DZIENNIE,
        run.ile_przebiegow_zostalo(conn))

print()
print("=== 3. KONTRDOWOD: PRODUKCYJNE ZABIERAJA ===")
zamknij("produkcja")
po_jednym = run.ile_przebiegow_zostalo(conn)
sprawdz("jeden przebieg produkcyjny zabiera dokladnie jeden slot",
        po_jednym == config.PRZEBIEGOW_DZIENNIE - 1, po_jednym)
zamknij("produkcja")
sprawdz("drugi zabiera drugi",
        run.ile_przebiegow_zostalo(conn) == config.PRZEBIEGOW_DZIENNIE - 2,
        run.ile_przebiegow_zostalo(conn))

print()
print("=== 4. PRZEBIEG PRZERWANY NADAL LICZY SIE TAK SAMO ===")
# Stara regula i jej powod sie nie zmieniaja: przy produkcyjnej porazce czas
# doby naprawde uplynal, wiec slot przepadl.
rid = db.start_run(conn, stage="dzien", tryb="produkcja")
db.finish_run(conn, rid, "FAILED")
sprawdz("produkcyjna porazka zabiera slot tak samo jak sukces",
        run.ile_przebiegow_zostalo(conn) == config.PRZEBIEGOW_DZIENNIE - 3,
        run.ile_przebiegow_zostalo(conn))

print()
print("=== 5. TRWAJACY PRZEBIEG NIE LICZY SAM SIEBIE ===")
db.start_run(conn, stage="dzien", tryb="produkcja")   # bez finish_run
sprawdz("biezacy przebieg jeszcze sie nie policzyl",
        run.ile_przebiegow_zostalo(conn) == config.PRZEBIEGOW_DZIENNIE - 3,
        run.ile_przebiegow_zostalo(conn))

print()
print("=== 6. KOD NAPRAWDE TAK ROBI ===")
zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("zapytanie odsiewa tryb inny niz produkcja",
        "COALESCE(tryb, 'produkcja') = 'produkcja'" in zrodlo)
sprawdz("przebieg bez --wyslij zapisuje sie jako test",
        'tryb="produkcja" if args.wyslij else "test"' in zrodlo)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
