# -*- coding: utf-8 -*-
"""PLATNA proba: ile faktow model przepuszcza tam, gdzie zapora nazw blokowala.

DLACZEGO PLATNA I DLACZEGO OSOBNA. Zestaw darmowy podstawia odpowiedzi modelu,
wiec dowodzi tylko tego, ze przewod dziala. Pytanie „ile faktow to naprawde
odblokuje" ma odpowiedz wylacznie z prawdziwego modelu na prawdziwym banku.

CO ROBI. Bierze wolne fakty z zywego banku, wybiera te, ktore zapora nazw
odrzuca, i na PROBIE pyta model, czy to powtorka wobec notek juz wystawionych.
Liczy, ile razy model mowi „nie" — czyli ile z tych blokad bylo falszywych.

CZEGO NIE RUSZA. Nie zapisuje niczego: ani banku, ani dziennika notek. Bank
jest liczony przed i po (sha256) i rozbieznosc jest bledem.

Uruchamiac z korzenia repozytorium, na serwerze:
    PYTHONIOENCODING=utf-8 .venv/bin/python agent-v2/tests/platne/proba_zapory_nazw.py [ILE]
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, "agent-v2")

import config   # noqa: E402
import db       # noqa: E402
import stages   # noqa: E402

ILE = int(sys.argv[1]) if len(sys.argv) > 1 else 15

plik_banku = pathlib.Path(config.DATA_DIR) / "indeks_kandydatow.json"
przed_sha = hashlib.sha256(plik_banku.read_bytes()).hexdigest()

dane = json.loads(plik_banku.read_text(encoding="utf-8"))
if isinstance(dane, dict):
    dane = dane.get("fakty") or next(
        (v for v in dane.values() if isinstance(v, list) and v), [])
wolne = [f for f in dane if isinstance(f, dict) and not f.get("wydany")]

korpus = stages.opublikowane_teksty()
zrodla = stages._tematy_zrodel()
wystawione = stages.teksty_ostatnich_notek()

print("bank: %d wolnych faktow, korpus %d notek, pamiec %d tekstow"
      % (len(wolne), len(korpus), len(wystawione)))

# Zbieramy te, ktore ZAPORA NAZW odrzuca — tylko o nie pytamy.
zderzone = []
for f in wolne:
    tekst = "%s %s" % (f.get("domain") or "", f.get("fact") or "")
    trafione = []
    nazwa = ""
    for u in wystawione:
        n = stages.wspolna_nazwa(tekst, u, korpus, korpus_zrodel=zrodla)
        if n:
            nazwa = nazwa or n
            trafione.append(u)
            if len(trafione) == 3:
                break
    if trafione:
        zderzone.append((tekst, nazwa, trafione))

print("zapora nazw odrzuca: %d z %d (%.0f%%)"
      % (len(zderzone), len(wolne), 100.0 * len(zderzone) / max(1, len(wolne))))
print("pytam model o probe %d z nich" % min(ILE, len(zderzone)))
print()

conn = db.connect()
run_id = None
przepuszczone = 0
zatrzymane = 0
bledy = 0
for tekst, nazwa, trafione in zderzone[:ILE]:
    try:
        nr, powod = stages._powtorka_wg_modelu(tekst, trafione, conn, run_id)
    except Exception as e:                                  # noqa: BLE001
        bledy += 1
        print("  BLAD  %s: %s" % (nazwa, e))
        continue
    if nr:
        zatrzymane += 1
        print("  POWTORKA   nazwa=%-12s %s" % (nazwa, powod[:60]))
    else:
        przepuszczone += 1
        print("  PRZEPUSC   nazwa=%-12s %s" % (nazwa, tekst[:66]))

zbadane = przepuszczone + zatrzymane
print()
print("=== WYNIK PROBY ===")
print("  zbadane:      %d" % zbadane)
print("  przepuszczone: %d  (%.0f%% blokad bylo falszywych)"
      % (przepuszczone, 100.0 * przepuszczone / max(1, zbadane)))
print("  potwierdzone:  %d" % zatrzymane)
if bledy:
    print("  bledy wywolan: %d" % bledy)

if zbadane:
    szacunek = len(zderzone) * przepuszczone / zbadane
    print()
    print("  przy tym udziale zapora zwalnia okolo %d z %d zablokowanych"
          % (round(szacunek), len(zderzone)))
    print("  przepustowosc banku: %d%% -> okolo %d%%"
          % (round(100.0 * (len(wolne) - len(zderzone)) / len(wolne)),
             round(100.0 * (len(wolne) - len(zderzone) + szacunek) / len(wolne))))

po_sha = hashlib.sha256(plik_banku.read_bytes()).hexdigest()
print()
if po_sha != przed_sha:
    print("BLAD: proba ZMIENILA bank (%s -> %s)" % (przed_sha[:12], po_sha[:12]))
    sys.exit(1)
print("bank nietkniety (sha %s)" % przed_sha[:12])
