# -*- coding: utf-8 -*-
"""PLATNA proba: notka poza oknem zostaje SKROCONA i wychodzi.

Zestaw darmowy podstawia odpowiedzi modelu, wiec dowodzi tylko, ze sciezka jest
spieta. Pytanie „czy skrocona notka jest nadal ta sama notka" ma odpowiedz
wylacznie z prawdziwego modelu — i ocenia ja czlowiek, czytajac obie wersje.

CO ROBI, w dwoch czesciach:

  A. Bierze OPUBLIKOWANA notke z korpusu i kaze ja zmiescic w oknie WEZSZYM
     niz jej wlasna dlugosc. To wymusza sciezke skracania na tekscie, ktory
     naprawde wyszedl, i pozwala porownac przed/po.
  B. Pisze nowa notke z zywego banku przez caly potok (rozbior -> pisanie ->
     dlugosc -> sprawdzenie faktow) i pokazuje, co z niej wyszlo.

CZEGO NIE RUSZA. Nie publikuje i nie oznacza faktu jako wydanego. Bank liczony
sha256 przed i po; rozbieznosc jest bledem.

Uruchamiac z korzenia repozytorium, na serwerze:
    PYTHONIOENCODING=utf-8 .venv/bin/python agent-v2/tests/platne/proba_dlugosci.py [NR_FAKTU]
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, "agent-v2")

import config   # noqa: E402
import db       # noqa: E402
import stages   # noqa: E402

NR = int(sys.argv[1]) if len(sys.argv) > 1 else 11

plik = pathlib.Path(config.DATA_DIR) / "indeks_kandydatow.json"
przed = hashlib.sha256(plik.read_bytes()).hexdigest()

conn = db.connect()

print("=" * 78)
print("A. SKRACANIE NOTKI, KTORA NAPRAWDE WYSZLA")
print("=" * 78)
korpus = [t for t in stages.opublikowane_teksty() if 100 <= len(t.split()) <= 140]
if not korpus:
    print("  brak notki w tym zakresie dlugosci — pomijam czesc A")
else:
    tekst = " ".join(korpus[-1].split())
    slow = len(tekst.split())
    # Okno wezsze niz sam tekst: wymusza dokladnie te sciezke, ktora dzis
    # zastapila wyrzucanie notki.
    sufit = slow - 12
    print("ORYGINAL (%d slow, okno 33-%d, czyli o %d za duzo):" % (slow, sufit, 12))
    print(tekst)
    print()
    wynik = stages.dopasuj_dlugosc(conn, None, tekst, min_slow=33,
                                   max_slow=sufit, kontekst="proba")
    if not wynik:
        print("SKRACANIE NIE POMOGLO — notka wyszlaby w calosci, tak jak byla")
    else:
        print("PO SKROCENIU (%d slow) — %s:" % (wynik["slow"],
                                                wynik["co_zmienione"]))
        print(wynik["tekst"])
        print()
        stare = tekst.split(". ")[0]
        nowe = wynik["tekst"].split(". ")[0]
        print("otwarcie nietkniete: %s" % ("TAK" if stare == nowe else
                                           "NIE — %r" % nowe[:70]))

print()
print("=" * 78)
print("B. CALY POTOK NA NOWYM FAKCIE")
print("=" * 78)
dane = json.loads(plik.read_text(encoding="utf-8"))
if isinstance(dane, dict):
    dane = dane.get("fakty") or next(
        (v for v in dane.values() if isinstance(v, list) and v), [])
wolne = [f for f in dane if isinstance(f, dict) and not f.get("wydany")]
fakt = wolne[NR % len(wolne)]
print("fakt: %s" % str(fakt.get("fact"))[:150])
print()

wynik = stages.note(conn, None, "CIEKAWOSTKA", fakt, note_form="PROSTA")
kand = (wynik or {}).get("candidates") or []
print()
if not kand:
    print("ZADEN KANDYDAT — to jest dokladnie to, co mialo przestac sie zdarzac")
for k in kand:
    print("NOTKA (%d slow, w oknie=%s, bezpieczna=%s):"
          % (len((k.get("note") or "").split()), k.get("length_ok"),
             k.get("safe_to_post")))
    print(k.get("note"))
    if k.get("tekst_przed_dlugoscia"):
        print()
        print("   [skracana: %s]" % k.get("dlugosc"))

po = hashlib.sha256(plik.read_bytes()).hexdigest()
print()
if po != przed:
    print("BLAD: proba ZMIENILA bank (%s -> %s)" % (przed[:12], po[:12]))
    sys.exit(1)
print("bank nietkniety (sha %s)" % przed[:12])
