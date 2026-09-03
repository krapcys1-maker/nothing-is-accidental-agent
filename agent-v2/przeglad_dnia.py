# -*- coding: utf-8 -*-
"""Caly lancuch jednego dnia: szukanie -> bank -> wybor -> notka -> publikacja.

PO CO. Wlasciciel powtarzal 3 wrzesnia 2026: „masz wchodzic w bank sprawdzic
tematy recznie, zobaczyc jakie przyszly, co wyszukal szukacz i dlaczego tak
zostaly posegregowane, co zostalo wziete do notek, jak notki zostaly napisane
i co zostalo wypuszczone". Robilem to za kazdym razem osobnymi poleceniami po
SSH — czyli tak, ze nikt poza mna nie mogl tego powtorzyc.

CZYTA, NIE WOLA MODELU. Zero kosztu, zero zapisow. Zrodla:
  * `data/dziennik.jsonl`      — co wyszlo w swiat,
  * `data/indeks_kandydatow.json` — bank pomyslow z rangami i katami,
  * dziennik systemowy przebiegu — decyzje, ktorych nie widac w plikach.

UWAGA NA DZIENNIK. Pole `tekst` przy notce jest UCIETE DO 300 ZNAKOW (21 z 34
notek od przestawienia konta). Do oceny brzmienia notki trzeba wziac pelny
tekst z profilu, nie stad — patrz `docs/AUDYT_NOTEK_2026-09-03.md`.

Uruchamiac z korzenia repozytorium:
    .venv/bin/python agent-v2/przeglad_dnia.py [RRRR-MM-DD]
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config  # noqa: E402


def _dzien() -> str:
    if len(sys.argv) > 1 and re.match(r"^\d{4}-\d{2}-\d{2}$", sys.argv[1]):
        return sys.argv[1]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _naglowek(tekst: str) -> None:
    print()
    print("=" * 74)
    print(tekst)
    print("=" * 74)


def _wpisy(dzien: str) -> list[dict]:
    sciezka = config.DATA_DIR / "dziennik.jsonl"
    if not sciezka.exists():
        return []
    out = []
    for l in io.open(sciezka, encoding="utf-8", errors="replace"):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if str(r.get("kiedy") or "")[:10] == dzien:
            out.append(r)
    return out


def _bank() -> list[dict]:
    sciezka = config.DATA_DIR / "indeks_kandydatow.json"
    if not sciezka.exists():
        return []
    try:
        dane = json.load(io.open(sciezka, encoding="utf-8"))
    except Exception:
        return []
    if isinstance(dane, dict):
        dane = dane.get("pozycje") or next(iter(dane.values()), [])
    return dane if isinstance(dane, list) else []


def _log_przebiegu(dzien: str) -> list[str]:
    """Linie decyzji z dziennika systemowego. Puste, gdy go nie ma."""
    try:
        sur = subprocess.run(
            ["journalctl", "-u", "nia-agent.service", "--since", dzien,
             "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    WAZNE = ("[ciekawostki]", "[bank]", "[indeks]", "[katy]", "[notki]",
             "[kanaly]", "[zrodla]", "UWAGA: otwiera", "PODLOGA")
    return [l for l in sur.splitlines() if any(w in l for w in WAZNE)]


def main() -> None:
    dzien = _dzien()
    print("PRZEGLAD DNIA %s   (czas UTC)" % dzien)

    wpisy = _wpisy(dzien)
    bank = _bank()
    log = _log_przebiegu(dzien)

    # ------------------------------------------------------------------
    _naglowek("1. SZUKANIE — co poszlo w swiat jako zapytanie")
    szukania = [l for l in log if "[ciekawostki]" in l or "[curiosity]" in l]
    if not szukania:
        print("  (brak sladu w dzienniku systemowym — przebieg mogl isc recznie)")
    for l in szukania[-14:]:
        print("  " + l.strip()[:150])

    # ------------------------------------------------------------------
    _naglowek("2. BANK — co w nim lezy, jak posortowane, jakie katy")
    wolne = [k for k in bank
             if k.get("status") == "nowy"
             and str(k.get("kiedy") or "")[:10] >= config.DATA_PRZESTAWIENIA]
    print("  wolnych tematow: %d   (podloga %d, sufit %d)"
          % (len(wolne), getattr(config, "BANK_MIN_WOLNYCH", 0),
             getattr(config, "BANK_MAKS_WOLNYCH", 0)))
    z_ranga = [k for k in wolne if k.get("ranga") is not None]
    z_katami = [k for k in wolne if k.get("katy")]
    ile_katow = sum(len(k.get("katy") or []) for k in wolne)
    nieuzyte = sum(1 for k in wolne for x in (k.get("katy") or [])
                   if isinstance(x, dict) and not x.get("uzyty"))
    print("  z nadana ranga: %d    z katami: %d    katow razem: %d"
          " (nieuzytych %d)" % (len(z_ranga), len(z_katami), ile_katow, nieuzyte))
    print()
    for k in sorted(wolne, key=lambda x: (x.get("ranga") is None,
                                          x.get("ranga") or 0))[:14]:
        katy = k.get("katy") or []
        print("  ranga=%-4s katow=%d/%d  %s"
              % (k.get("ranga"),
                 sum(1 for x in katy if isinstance(x, dict) and not x.get("uzyty")),
                 len(katy), str(k.get("fact") or "")[:88]))
        for x in katy:
            if not isinstance(x, dict):
                continue
            print("        %s lamie: %s"
                  % ("[uzyty]" if x.get("uzyty") else "[wolny]",
                     str(x.get("lamie") or "")[:70]))
            if x.get("czego_brakuje"):
                print("                brakuje: %s"
                      % str(x["czego_brakuje"])[:70])

    # ------------------------------------------------------------------
    _naglowek("3. WYBOR — co odpadlo i dlaczego")
    powody = [l for l in log
              if "pomijam" in l or "blizniak" in l or "[katy]" in l
              or "juz pisalismy" in l]
    if not powody:
        print("  (nic nie odpadlo albo brak sladu)")
    for l in powody[-16:]:
        print("  " + l.strip()[:150])

    # ------------------------------------------------------------------
    _naglowek("4. NOTKI — co napisane i wystawione")
    notki = [r for r in wpisy if r.get("rodzaj") == "notka" and r.get("udane")]
    print("  wystawionych: %d" % len(notki))
    if notki:
        print("  typy:  %s" % dict(Counter(r.get("typ") for r in notki)))
        print("  formy: %s" % dict(Counter(r.get("forma") for r in notki)))
        print("  modele:%s" % dict(Counter(r.get("model") for r in notki)))
        dl = [r.get("slow") or 0 for r in notki]
        print("  slow:  min %d  mediana %d  maks %d"
              % (min(dl), sorted(dl)[len(dl) // 2], max(dl)))
    for r in notki:
        print()
        print("  --- %s  typ=%s forma=%s slow=%s model=%s ranga_faktu=%s"
              % (str(r.get("kiedy"))[11:16], r.get("typ"), r.get("forma"),
                 r.get("slow"), r.get("model"), r.get("fakt_ranga")))
        # UCIETE DO 300 ZNAKOW W ZRODLE — patrz naglowek pliku.
        print("      " + str(r.get("tekst") or "").replace("\n", " ")[:220])

    # ------------------------------------------------------------------
    _naglowek("5. RESZTA DNIA")
    for rodzaj in ("komentarz", "odpowiedz", "polubienie", "restack",
                   "subskrypcja", "artykul"):
        ile = sum(1 for r in wpisy
                  if r.get("rodzaj") == rodzaj and r.get("udane"))
        if ile:
            print("  %-14s %d" % (rodzaj, ile))
    ostrzezenia = [l for l in log if "UWAGA: otwiera" in l or "PODLOGA" in l]
    if ostrzezenia:
        print()
        print("  SYGNALY:")
        for l in ostrzezenia[-6:]:
            print("    " + l.strip()[:140])


if __name__ == "__main__":
    main()
