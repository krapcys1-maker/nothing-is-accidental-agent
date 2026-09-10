# -*- coding: utf-8 -*-
"""PLATNA proba: pisze N notek prawdziwym modelem i pokazuje same teksty.

Do czytania przez czlowieka. Zadnych asercji — pytanie brzmi „czy to ma
charakter", a tego nie rozstrzygnie zaden `assert`.

CZEGO NIE RUSZA. Nie publikuje, nie zapisuje do dziennika, nie oznacza faktow
jako wydanych. Bank liczony sha256 przed i po; rozbieznosc jest bledem.

Uruchamiac z korzenia repozytorium, na serwerze:
    PYTHONIOENCODING=utf-8 .venv/bin/python agent-v2/tests/platne/proba_glosu.py [ILE] [OD]
"""
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, "agent-v2")

import config   # noqa: E402
import db       # noqa: E402
import stages   # noqa: E402

ILE = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OD = int(sys.argv[2]) if len(sys.argv) > 2 else 0

plik = pathlib.Path(config.DATA_DIR) / "indeks_kandydatow.json"
przed = hashlib.sha256(plik.read_bytes()).hexdigest()

dane = json.loads(plik.read_text(encoding="utf-8"))
if isinstance(dane, dict):
    dane = dane.get("fakty") or next(
        (v for v in dane.values() if isinstance(v, list) and v), [])
wolne = [f for f in dane if isinstance(f, dict) and not f.get("wydany")]

conn = db.connect()
FORMY = ["PROSTA", "ZACZEP_I_KONKRET", "KONTRAST", "LICZBA", "ODWROCENIE"]

for nr in range(ILE):
    fakt = wolne[(OD + nr) % len(wolne)]
    forma = FORMY[nr % len(FORMY)]
    print("=" * 78)
    print("%d/%d  forma %s" % (nr + 1, ILE, forma))
    print("   material: %s" % str(fakt.get("fact"))[:120])
    print("=" * 78)
    wynik = stages.note(conn, None, "CIEKAWOSTKA", fakt, note_form=forma)
    for k in (wynik or {}).get("candidates") or []:
        tekst = " ".join((k.get("note") or "").split())
        if not tekst:
            print("(pusto)")
            continue
        print()
        print(tekst)
        zdania = [z for z in re.split(r"(?<=[.!?])\s+", tekst) if z.strip()]
        dl = [len(z.split()) for z in zdania]
        print()
        print("   slow: %d | zdan: %d | najkrotsze: %d | najdluzsze: %d"
              % (len(tekst.split()), len(zdania), min(dl or [0]), max(dl or [0])))
        print("   dlugosci zdan: %s" % dl)
    print()

po = hashlib.sha256(plik.read_bytes()).hexdigest()
if po != przed:
    print("BLAD: proba ZMIENILA bank (%s -> %s)" % (przed[:12], po[:12]))
    sys.exit(1)
print("bank nietkniety (sha %s)" % przed[:12])
