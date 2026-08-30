"""Ile agent naprawde zrobil, dzien po dniu, wobec normy.

PO CO TO ISTNIEJE. Wlasciciel zobaczyl na Substacku, ze notek jest malo, i
dowiedzial sie o tym SAM — patrzac na profil, nie od systemu. Normy byly
policzone (`config.normy_dzienne`), alarm mial prog (`PROG_ALARMU_WOLUMENU`),
a mimo to przez pietnascie dni realizacja notek stala na 57 procent i nikt
tego nie widzial. Licznik, ktorego nie da sie uruchomic jednym poleceniem,
nie jest licznikiem.

CO POKAZUJE. Wylacznie PRODUKCJE — ile agent wystawil. Odbiór (wyswietlenia,
polubienia od czytelnikow, subskrypcje z pozycji) mieszka w `statystyki.py` i
jest osobnym pytaniem: tam chodzi o to, co przyszlo z powrotem.

ZRODLEM JEST DZIENNIK, nie Substack. To jedyny zapis, w ktorym atrybucja jest
z definicji poprawna — dziennik notuje wylacznie wlasne dzialania. Kanal
profilu pokazuje takze notki pisane recznie przez wlasciciela i wlasnie to
mylenie kosztowalo agenta przydzial: 29 sierpnia profil mial piec notek, z
czego dwie byly bota.

    python agent-v2/norma.py            # ostatnie 14 dni
    python agent-v2/norma.py --dni 30
    python agent-v2/norma.py --dzis     # sam dzisiejszy stan, krotko
"""
import argparse
import collections
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

DZIENNIK = config.DATA_DIR / "dziennik.jsonl"

# Kolejnosc kolumn: od tego, co wlasciciel sprawdza najczesciej.
RODZAJE = ("notka", "komentarz", "polubienie", "restack", "subskrypcja",
           "obserwacja")

# Pozycje NIEWYKONALNE nie sa porazka i nie moga zanizac wyniku na zawsze.
# Substack zdjal przycisk „Follow" ze stron profilowych — sprawdzone na szesciu
# profilach 23 sierpnia 2026. Dopoki go nie ma, obserwacje pokazujemy jako
# „brak przycisku", a nie jako 0 procent normy.
NIEWYKONALNE = {"obserwacja": "Substack zdjal przycisk Follow"}


def wczytaj(dni: int):
    """(zrobione, nieudane) — liczniki per dzien i rodzaj."""
    granica = (datetime.now(timezone.utc) - timedelta(days=dni)).strftime("%Y-%m-%d")
    zrobione = collections.defaultdict(collections.Counter)
    nieudane = collections.defaultdict(collections.Counter)
    if not DZIENNIK.exists():
        return zrobione, nieudane
    with DZIENNIK.open(encoding="utf-8") as plik:
        for linia in plik:
            linia = linia.strip()
            if not linia:
                continue
            try:
                w = json.loads(linia)
            except ValueError:
                continue
            if not isinstance(w, dict) or w.get("rodzaj") not in RODZAJE:
                continue
            dzien = str(w.get("kiedy") or "")[:10]
            if not dzien or dzien < granica:
                continue
            (zrobione if w.get("udane") else nieudane)[dzien][w["rodzaj"]] += 1
    return zrobione, nieudane


def _znak(ile: float, norma: float) -> str:
    """Jak daleko od normy. Prog alarmu jest ten sam, co w `alarm.py`."""
    if norma < 1:
        return ""
    proc = 100.0 * ile / norma
    if proc >= 90:
        return " "
    return "!" if proc >= config.PROG_ALARMU_WOLUMENU else "!!"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dni", type=int, default=14)
    ap.add_argument("--dzis", action="store_true",
                    help="tylko dzisiejszy stan, jedna linia na rodzaj")
    args = ap.parse_args()

    normy = config.normy_dzienne()
    dni = 1 if args.dzis else args.dni
    zrobione, nieudane = wczytaj(dni)
    kolejne = sorted(zrobione) or [datetime.now(timezone.utc).strftime("%Y-%m-%d")]

    if args.dzis:
        dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print("STAN NA DZIS (%s, UTC)" % dzis)
        for r in RODZAJE:
            ile, norma = zrobione[dzis][r], normy.get(r, 0)
            if r in NIEWYKONALNE:
                print("  %-12s %3d      — %s" % (r, ile, NIEWYKONALNE[r]))
            elif norma >= 1:
                print("  %-12s %3d / %-4.0f %3.0f%%%s" % (
                    r, ile, norma, 100.0 * ile / norma, _znak(ile, norma)))
            else:
                print("  %-12s %3d      (norma %.2f/dobe)" % (r, ile, norma))
        return 0

    naglowek = "  %-11s" % "dzien" + "".join("%12s" % r[:11] for r in RODZAJE)
    print("NORMA DZIENNA: " + "  ".join(
        "%s=%.1f" % (r, normy.get(r, 0)) for r in RODZAJE))
    print()
    print(naglowek)
    print("  " + "-" * (len(naglowek) - 2))

    sumy = collections.Counter()
    for d in kolejne:
        wiersz = "  %-11s" % d
        for r in RODZAJE:
            ile = zrobione[d][r]
            sumy[r] += ile
            norma = normy.get(r, 0)
            wiersz += "%12s" % (
                "%d/%.0f%s" % (ile, norma, _znak(ile, norma)) if norma >= 1
                else (str(ile) if ile else "-"))
        print(wiersz)

    print("  " + "-" * (len(naglowek) - 2))
    n = len(kolejne)
    for etykieta, wart in (
            ("SREDNIA", lambda r: "%.1f" % (sumy[r] / n)),
            ("% NORMY", lambda r: ("%.0f%%" % (100.0 * (sumy[r] / n) / normy[r])
                                   if normy.get(r, 0) >= 1 else "-"))):
        print("  %-11s" % etykieta + "".join("%12s" % wart(r) for r in RODZAJE))

    braki = {r: sum(nieudane[d][r] for d in nieudane) for r in RODZAJE}
    braki = {r: v for r, v in braki.items() if v}
    print()
    print("  dni: %d (%s .. %s)" % (n, kolejne[0], kolejne[-1]))
    if braki:
        print("  nieudane proby: %s" % ", ".join(
            "%s %d" % (r, v) for r, v in sorted(braki.items())))
    for r, powod in NIEWYKONALNE.items():
        print("  %s: %s — zero nie jest tu porazka" % (r, powod))

    ponizej = [r for r in RODZAJE
               if normy.get(r, 0) >= 1 and r not in NIEWYKONALNE
               and 100.0 * (sumy[r] / n) / normy[r] < config.PROG_ALARMU_WOLUMENU]
    if ponizej:
        print()
        print("  PONIZEJ PROGU %d%%: %s" % (config.PROG_ALARMU_WOLUMENU,
                                            ", ".join(ponizej)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
