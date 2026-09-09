# -*- coding: utf-8 -*-
"""PLATNA proba A/B: ta sama notka napisana Z ROZBIOREM i BEZ.

Zestaw darmowy podstawia odpowiedzi modelu, wiec dowodzi tylko, ze rozbior
trafia do promptu. Pytanie „czy notka jest przez to lepsza" ma odpowiedz
wylacznie z prawdziwego modelu na prawdziwym materiale — i ocenia ja czlowiek,
nie asercja.

CO ROBI. Bierze fakt z zywego banku (albo numer faktu z argumentu), pokazuje
rozbior, a potem pisze DWIE notki na tym samym materiale, tego samego typu
i ksztaltu: jedna z rozbiorem, druga bez. Drukuje obie obok siebie.

CZEGO NIE RUSZA. Nie publikuje, nie zapisuje do dziennika, nie oznacza faktu
jako wydanego. Bank liczony sha256 przed i po — rozbieznosc jest bledem.

Uruchamiac z korzenia repozytorium, na serwerze:
    PYTHONIOENCODING=utf-8 .venv/bin/python agent-v2/tests/platne/proba_rozbioru.py [NR_FAKTU] [FORMA]
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, "agent-v2")
# Proba wersji jeszcze niewdrozonej: NOWY=<katalog> wchodzi PRZED
# "agent-v2", bo PYTHONPATH przegrywa z tym wpisem.
import os
if os.environ.get("NOWY"):
    sys.path.insert(0, os.environ["NOWY"])

import config   # noqa: E402
import db       # noqa: E402
import stages   # noqa: E402

NR = int(sys.argv[1]) if len(sys.argv) > 1 else 0
FORMA = sys.argv[2] if len(sys.argv) > 2 else "PROSTA"

plik = pathlib.Path(config.DATA_DIR) / "indeks_kandydatow.json"
przed = hashlib.sha256(plik.read_bytes()).hexdigest()

dane = json.loads(plik.read_text(encoding="utf-8"))
if isinstance(dane, dict):
    dane = dane.get("fakty") or next(
        (v for v in dane.values() if isinstance(v, list) and v), [])
wolne = [f for f in dane if isinstance(f, dict) and not f.get("wydany")]
fakt = wolne[NR]

print("=" * 78)
print("MATERIAL (fakt %d z %d wolnych)" % (NR, len(wolne)))
print("=" * 78)
for pole in ("domain", "fact", "wrong_belief", "actually", "consequence"):
    if fakt.get(pole):
        print("%-14s %s" % (pole, str(fakt[pole])[:300]))

conn = db.connect()

print()
print("=" * 78)
print("ROZBIOR")
print("=" * 78)
r = stages.rozbior(conn, None, fakt)
if not r:
    print("  rozbior nie odpowiedzial — proba nic nie porowna")
    sys.exit(1)
print("W PROSTYCH SLOWACH: %s" % r.get("w_prostych_slowach"))
print("SKALA             : %s" % (r.get("skala") or "(pusta — material nie dal"
                                  " porownania)"))
for p in r.get("pytania") or []:
    print("  ? %s" % p.get("pytanie"))
    print("    %s  [%s]" % (p.get("odpowiedz"),
                            "z materialu" if p.get("z_dowodu") else "sad"))
print("JESLI SIE UTRZYMA : %s" % r.get("jesli_sie_utrzyma"))
print("GDZIE BY PEKLO    : %s" % r.get("gdzie_by_peklo"))
print("CO O TYM SADZE    : %s" % r.get("co_o_tym_sadze"))
print("CZEGO NIE WIADOMO : %s" % "; ".join(r.get("czego_nie_wiadomo") or []))


def napisz(z_rozbiorem):
    """Jedna notka. Przy `z_rozbiorem=False` etap rozbioru jest wyciszony."""
    oryginal = stages.rozbior
    if not z_rozbiorem:
        stages.rozbior = lambda *a, **k: {}
    try:
        return stages.note(conn, None, "CIEKAWOSTKA", fakt, note_form=FORMA)
    finally:
        stages.rozbior = oryginal


def pokaz(wynik):
    """Kandydaci `note` trzymaja tekst pod kluczem `note`, nie `tekst`."""
    kand = (wynik or {}).get("candidates") or []
    if not kand:
        print("(zaden kandydat nie przeszedl)")
        return
    for k in kand:
        print(k.get("note") or "(pusty)")
        print("   [slow=%d  bezpieczna=%s  odrzucona=%s]"
              % (len((k.get("note") or "").split()),
                 k.get("safe_to_post"), k.get("odrzucony") or "nie"))


print()
print("=" * 78)
print("A — NOTKA BEZ ROZBIORU (jak dotad)")
print("=" * 78)
a = napisz(False)
pokaz(a)

print()
print("=" * 78)
print("B — NOTKA Z ROZBIOREM")
print("=" * 78)
b = napisz(True)
pokaz(b)

po = hashlib.sha256(plik.read_bytes()).hexdigest()
print()
if po != przed:
    print("BLAD: proba ZMIENILA bank (%s -> %s)" % (przed[:12], po[:12]))
    sys.exit(1)
print("bank nietkniety (sha %s)" % przed[:12])
