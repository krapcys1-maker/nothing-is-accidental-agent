"""Test limitu czasu przebiegu i sladu po SIGTERM."""
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import run     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. JEDNA LICZBA W DWOCH MIEJSCACH — pilnujemy zgodnosci ===")

usluga = pathlib.Path("agent-v2/systemd/nia-agent.service").read_text(encoding="utf-8")
m = re.search(r"^TimeoutStartSec=(\d+)", usluga, re.M)
sprawdz("plik uslugi ma TimeoutStartSec", bool(m))
if m:
    z_uslugi = int(m.group(1))
    print("    usluga: %ss    config: %ss    zapas: %ss"
          % (z_uslugi, config.LIMIT_CZASU_PRZEBIEGU_S, config.ZAPAS_CZASU_S))
    sprawdz("config zgadza sie z plikiem uslugi",
            config.LIMIT_CZASU_PRZEBIEGU_S == z_uslugi,
            "%s != %s" % (config.LIMIT_CZASU_PRZEBIEGU_S, z_uslugi))
    sprawdz("agent konczy PRZED systemd, nie po",
            config.LIMIT_CZASU_PRZEBIEGU_S - config.ZAPAS_CZASU_S < z_uslugi)
    sprawdz("zapas wystarczy na domkniecie (>= 5 min)",
            config.ZAPAS_CZASU_S >= 300, config.ZAPAS_CZASU_S)

print()
print("=== 2. zostal_czas ===")

oryg = run._KONIEC_CZASU
try:
    run._KONIEC_CZASU = None
    sprawdz("bez ustawionego konca (uruchomienie reczne) -> nie przeszkadza",
            run.zostal_czas("cos") is True)

    run._KONIEC_CZASU = time.time() + 600
    sprawdz("gdy zostalo 10 minut -> pracuj dalej", run.zostal_czas("cos") is True)

    run._KONIEC_CZASU = time.time() - 1
    sprawdz("gdy czas minal -> przerwij", run.zostal_czas("komentarze") is False)

    run._KONIEC_CZASU = time.time()
    sprawdz("dokladnie na styku -> przerwij", run.zostal_czas() is False)
finally:
    run._KONIEC_CZASU = oryg

print()
print("=== 3. CZY PETLE NAPRAWDE PYTAJA O CZAS ===")

zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
for petla in ("notki", "komentarze", "dyskusje", "odpowiedzi", "obserwowanie"):
    sprawdz("petla %-13s pyta o czas" % petla,
            'zostal_czas("%s")' % petla in zrodlo)
sprawdz("dzien() ustawia koniec czasu na starcie",
        "_KONIEC_CZASU = time.time() + max(" in zrodlo)

print()
print("=== 4. SIGTERM ZOSTAWIA SLAD (prawdziwy proces, prawdziwy sygnal) ===")

kat = pathlib.Path(tempfile.mkdtemp())
baza = kat / "sygnal.db"
podstawka = kat / "wolno.py"
podstawka.write_text(
    "import pathlib, sys, time\n"
    "sys.path.insert(0, %r)\n" % os.path.abspath("agent-v2") +
    "import config, db, run\n"
    # WLASNY katalog danych, czyli wlasny zamek. Bez tego podproces bierze
    # zamek PRODUKCYJNY i konczy bez zmian, gdy agent akurat pracuje —
    # test klamalby wtedy o kodzie, bo zderzyl sie z rzeczywistoscia.
    "config.DATA_DIR = pathlib.Path(%r)\n" % str(kat) +
    "oryg = db.connect\n"
    "db.connect = lambda path=None: oryg(pathlib.Path(%r))\n" % str(baza) +
    "run.dzien = lambda conn, run_id, wyslij: time.sleep(600)\n"
    "run._summary = lambda *a, **k: None\n"
    "sys.argv = ['run.py', '--dzien']\n"
    "sys.exit(run.main())\n", encoding="utf-8")

proc = subprocess.Popen([sys.executable, str(podstawka)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(6)
proc.send_signal(signal.SIGTERM)
try:
    wyjscie = proc.communicate(timeout=30)[0].decode("utf-8", "replace")
except subprocess.TimeoutExpired:
    proc.kill()
    wyjscie = "(nie zakonczyl sie)"

print("    --- co powiedzial proces potomny ---")
for linia in (wyjscie or "").strip().splitlines()[-12:]:
    print("    | %s" % linia)
print("    kod wyjscia: %s" % proc.returncode)

import sqlite3  # noqa: E402

wiersze = []
if baza.exists():
    wiersze = list(sqlite3.connect(baza).execute(
        "SELECT status, stage, note FROM runs ORDER BY id"))
print("    wiersze w bazie: %s" % wiersze)
sprawdz("przebieg zapisal sie po SIGTERM (nie zostal w RUNNING)",
        bool(wiersze) and wiersze[-1][0] == "FAILED",
        wiersze[-1] if wiersze else "brak wiersza")
sprawdz("notatka mowi, ze to byl sygnal",
        bool(wiersze) and "SIGTERM" in (wiersze[-1][2] or ""),
        wiersze[-1][2] if wiersze else "")
sprawdz("zaden wiersz nie zostal w RUNNING",
        all(w[0] != "RUNNING" for w in wiersze), [w[0] for w in wiersze])

print()
print("=== WYNIK: %s zdanych, %s oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
