"""Test rytmu publikacji: notki nie moga wychodzic parami."""
import pathlib
import statistics
import sys

sys.path.insert(0, "agent-v3")
import config  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. ODSTEP MIEDZY NOTKAMI ===")
dol, gora = config.ODSTEPY["notka"]
print("    %s-%s min (bylo 10-25)" % (dol // 60, gora // 60))
sprawdz("dolna granica co najmniej 40 min", dol >= 2400, dol)
sprawdz("gorna co najmniej 80 min", gora >= 4800, gora)
sprawdz("STARY odstep 10-25 min dawal pary (test rozroznia)", dol > 1500)
sprawdz("komentarze zostaly krotkie (to inna czynnosc)",
        config.ODSTEPY["komentarz"][1] <= 600, config.ODSTEPY["komentarz"])
sprawdz("polubienia nadal najkrotsze",
        config.ODSTEPY["lajk"][1] < config.ODSTEPY["komentarz"][0])

print()
print("=== 2. ZWLOKA PRZED PIERWSZA NOTKA ===")
zd, zg = config.ZWLOKA_PRZED_NOTKAMI
print("    0-%s min" % (zg // 60))
sprawdz("zwloka istnieje", zg > 0)
sprawdz("zwloka co najmniej pol godziny w gorze", zg >= 1800, zg)
sprawdz("moze byc zerowa (nie zawsze czekamy)", zd == 0, zd)

print()
print("=== 3. CZY WSZYSTKO MIESCI SIE W CZASIE PRZEBIEGU ===")
budzet_czasu = config.LIMIT_CZASU_PRZEBIEGU_S - config.ZAPAS_CZASU_S
najgorszy = zg + gora            # zwloka + jeden odstep miedzy dwiema notkami
print("    najgorszy przypadek: %s min, budzet przebiegu: %s min"
      % (najgorszy // 60, budzet_czasu // 60))
sprawdz("dwie notki mieszcza sie w najgorszym razie", najgorszy < budzet_czasu,
        "%s >= %s" % (najgorszy, budzet_czasu))
sprawdz("trzy notki juz NIE musza sie zmiescic — od tego jest zostal_czas",
        zg + 2 * gora > budzet_czasu)

print()
print("=== 4. SYMULACJA DNIA: CZY ZNIKAJA PARY ===")
import random  # noqa: E402

random.seed(3)
STARTY = [11 * 60 + 20, 19 * 60 + 20, 23 * 60 + 40]   # UTC, w minutach


def dzien(odstep, zwloka):
    czasy = []
    for start in STARTY:
        t = start + random.uniform(0, 25) + random.uniform(*zwloka) / 60
        for _ in range(2):
            czasy.append(t % (24 * 60))
            t += random.uniform(*odstep) / 60
    return sorted(czasy)


def najkrotszy_odstep(czasy):
    return min(b - a for a, b in zip(czasy, czasy[1:]))


stare = [najkrotszy_odstep(dzien((600, 1500), (0, 0))) for _ in range(200)]
nowe = [najkrotszy_odstep(dzien(config.ODSTEPY["notka"],
                                config.ZWLOKA_PRZED_NOTKAMI)) for _ in range(200)]
print("    STARY: najkrotszy odstep w dniu, mediana %.0f min" % statistics.median(stare))
print("    NOWY:  najkrotszy odstep w dniu, mediana %.0f min" % statistics.median(nowe))
sprawdz("stary rytm dawal pary ponizej 30 min",
        statistics.median(stare) < 30, statistics.median(stare))
sprawdz("nowy rytm nie daje par ponizej 40 min",
        statistics.median(nowe) >= 40, statistics.median(nowe))
sprawdz("poprawa co najmniej dwukrotna",
        statistics.median(nowe) > 2 * statistics.median(stare))

print()
print("=== 5. GODZINY ZOSTAJA TE, KTORE WYBRALISMY ===")
zegar = pathlib.Path("agent-v3/systemd/nia-agent.timer").read_text(encoding="utf-8")
for g in ("11:20:00", "19:20:00", "23:40:00"):
    sprawdz("zegar nadal ma %s UTC" % g, g in zegar)
sprawdz("okno publikacji nietkniete", config.OKNO_PUBLIKACJI_ET == (6, 22),
        config.OKNO_PUBLIKACJI_ET)

zrodlo = pathlib.Path("agent-v3/run.py").read_text(encoding="utf-8")
sprawdz("run.py stosuje zwloke", "ZWLOKA_PRZED_NOTKAMI" in zrodlo)
sprawdz("zwloka TYLKO przy prawdziwym wystawianiu",
        "if wyslij:" in zrodlo.split("ZWLOKA_PRZED_NOTKAMI")[0][-260:])

print()
print("=== 6. PLAN PRZYCIETY DO ZEGARA ===")

import time as _t  # noqa: E402
import run as _run  # noqa: E402

budzet = config.LIMIT_CZASU_PRZEBIEGU_S - config.ZAPAS_CZASU_S
_run._KONIEC_CZASU = _t.time() + budzet
n = _run.zmiesci_sie("notka", 4, config.UDZIAL_CZASU_NA_NOTKI)
k = _run.zmiesci_sie("komentarz", 14)
print("    pelny przebieg (%s min): notki %s/4, komentarze %s/14" % (budzet // 60, n, k))
sprawdz("cztery notki NIE mieszcza sie w przebiegu", n < 4, n)
sprawdz("ale dwie sie mieszcza (dzien ma 5 notek na 3 przebiegi)", n >= 2, n)
sprawdz("komentarze nadal wchodza w calosci", k == 14, k)

_run._KONIEC_CZASU = _t.time() + 600
sprawdz("gdy zostalo 10 min, notek prawie nie ma",
        _run.zmiesci_sie("notka", 4, config.UDZIAL_CZASU_NA_NOTKI) <= 1)
sprawdz("i komentarzy tez", _run.zmiesci_sie("komentarz", 14) <= 2)

_run._KONIEC_CZASU = _t.time() + 60
sprawdz("przy sekundach do konca nie obiecujemy nic ponad jedno",
        _run.zmiesci_sie("notka", 4, config.UDZIAL_CZASU_NA_NOTKI) <= 1)

_run._KONIEC_CZASU = None
sprawdz("uruchomienie reczne bez limitu nic nie przycina",
        _run.zmiesci_sie("notka", 4, 0.6) == 4)
sprawdz("zero zostaje zerem", _run.zmiesci_sie("notka", 0, 0.6) == 0)

# KONTRDOWOD: formula liczaca przerwe PO KAZDYM dzialaniu dawala o polowe za malo
_run._KONIEC_CZASU = _t.time() + budzet
odstep = sum(config.ODSTEPY["notka"]) / 2
zostalo = budzet * config.UDZIAL_CZASU_NA_NOTKI
zle = int(zostalo // (odstep + config.CZAS_DZIALANIA_S))
dobrze = _run.zmiesci_sie("notka", 4, config.UDZIAL_CZASU_NA_NOTKI)
print("    stara formula (przerwa po kazdej): %s, poprawna (n-1 przerw): %s"
      % (zle, dobrze))
sprawdz("poprawka n-1 przerw naprawde zmienia wynik (test rozroznia)",
        dobrze > zle, (dobrze, zle))

zrodlo = pathlib.Path("agent-v3/run.py").read_text(encoding="utf-8")
sprawdz("dzien() przycina plan do czasu", 'zmiesci_sie("notka"' in zrodlo)
sprawdz("notki maja pierwszenstwo, ale nie caly przebieg",
        "UDZIAL_CZASU_NA_NOTKI" in zrodlo)

print()
print("=== WYNIK: %s zdanych, %s oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
