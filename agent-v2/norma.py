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


def budzety_dzienne() -> dict:
    """Ile agent SOBIE ZALOZYL kazdego dnia — z pliku, nie z dzisiejszej konfiguracji.

    WYKONANIE PLANU I AMBICJA TO DWA ROZNE PYTANIA. `config.normy_dzienne()`
    mowi, ile POWINNO wychodzic docelowo; zapisany budzet mowi, ile agent w tym
    dniu w ogole zamierzal. Mierzenie wykonania ambicja daje dwa falszywe
    alarmy naraz: przez pierwsze 30 dni budzet leci dolna polowa widelek
    (rozbieg), a kazda zmiana widelek przepisuje historie wstecz.

    Zmierzone 30 sierpnia: 29 sierpnia agent zalozyl 10 komentarzy i zrobil 6 —
    60% wlasnego planu — a licznik pokazywal 32%, bo widelki zmienily sie tego
    samego dnia z (8,12) na (15,23).
    """
    import json
    plik = config.DATA_DIR / "budzety.json"
    try:
        stan = json.loads(plik.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(stan, dict):
        return {}
    # Przepisujemy na nazwy z dziennika, zeby licznik nie musial tlumaczyc.
    wynik = {}
    for dzien, wpis in stan.items():
        b = (wpis or {}).get("budzet") or {}
        wynik[dzien] = {config.BUDZET_NA_RODZAJ[k]: v
                        for k, v in b.items() if k in config.BUDZET_NA_RODZAJ}
    return wynik


def _data(dzien: str):
    """„2026-08-30" -> datetime w UTC. `cichy_dzien` pyta o obiekt, nie napis."""
    return datetime.strptime(dzien, "%Y-%m-%d").replace(tzinfo=timezone.utc)


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


def przebiegow_dzis() -> int:
    """Ile przebiegow agenta domknelo sie dzis. Zero, gdy bazy nie ma."""
    try:
        import db
        conn = db.connect()
        dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        (ile,) = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE finished_at LIKE ? AND stage = 'dzien'",
            (dzis + "%",)).fetchone()
        conn.close()
        return int(ile or 0)
    except Exception:
        return 0


def slad(dni: int) -> int:
    """Gdzie dokladnie psuja sie publikacje — wg pozycji w serii i odstepu.

    PO CO OSOBNY WIDOK. Norma mowi ILE wyszlo, a nie DLACZEGO reszta nie.
    30 sierpnia trzeba bylo odtwarzac pozycje w serii z timestampow dziennika,
    grupujac wpisy po przerwach i zgadujac granice serii — i dopiero to
    pokazalo, ze awaryjnosc potraja sie po pierwszej akcji. Agent zna te liczbe
    w chwili dzialania; teraz ja zapisuje (`nr_w_serii`, `od_poprzedniej_s`),
    a to jest miejsce, w ktorym sie ja czyta.

    Wpisy sprzed 30 sierpnia tych pol nie maja i sa tu pomijane — lepiej
    pokazac mniej niz zmyslic pozycje.
    """
    granica = (datetime.now(timezone.utc) - timedelta(days=dni)).strftime("%Y-%m-%d")
    wpisy = []
    if DZIENNIK.exists():
        with DZIENNIK.open(encoding="utf-8") as plik:
            for linia in plik:
                linia = linia.strip()
                if not linia:
                    continue
                try:
                    w = json.loads(linia)
                except ValueError:
                    continue
                if not isinstance(w, dict) or "nr_w_serii" not in w:
                    continue
                if str(w.get("kiedy") or "")[:10] < granica:
                    continue
                wpisy.append(w)

    if not wpisy:
        print("Brak wpisow ze sladem przebiegu.")
        print("Slad zapisywany jest od 30 sierpnia 2026 — poczekaj na przebieg.")
        return 0

    print("SLAD PRZEBIEGU — %d dzialan z ostatnich %d dni" % (len(wpisy), dni))

    print()
    print("=== AWARYJNOSC WG POZYCJI W SERII ===")
    print("  %-8s %-14s %6s %8s %7s" % ("rodzaj", "ktora z rzedu", "prob",
                                        "porazek", "%"))
    licz: dict = collections.defaultdict(lambda: [0, 0])
    for w in wpisy:
        klucz = (w.get("rodzaj"), min(int(w.get("nr_w_serii") or 1), 5))
        licz[klucz][0] += 1
        licz[klucz][1] += 0 if w.get("udane") else 1
    for (rodzaj, nr), (prob, zle) in sorted(licz.items()):
        etykieta = "%d%s" % (nr, "+" if nr == 5 else "")
        print("  %-8s %-14s %6d %8d %6.0f%%" % (
            rodzaj, etykieta, prob, zle, 100.0 * zle / prob))

    print()
    print("=== AWARYJNOSC WG ODSTEPU OD POPRZEDNIEJ ===")
    # Przedzialy dobrane pod decyzje, ktora jest do podjecia: czy piec minut
    # wystarcza. Pierwsza akcja w przebiegu nie ma odstepu i tu nie wchodzi.
    progi = ((0, 300, "ponizej 5 min"), (300, 600, "5-10 min"),
             (600, 1200, "10-20 min"), (1200, 10 ** 9, "ponad 20 min"))
    kubelki: dict = collections.defaultdict(lambda: [0, 0])
    for w in wpisy:
        sek = w.get("od_poprzedniej_s")
        if sek is None:
            continue
        for dol, gora, nazwa in progi:
            if dol <= sek < gora:
                kubelki[nazwa][0] += 1
                kubelki[nazwa][1] += 0 if w.get("udane") else 1
                break
    if not kubelki:
        print("  (jeszcze zadnej akcji z poprzedniczka w tym samym przebiegu)")
    for _, _, nazwa in progi:
        if nazwa in kubelki:
            prob, zle = kubelki[nazwa]
            print("  %-14s %6d prob %6d porazek %6.0f%%" % (
                nazwa, prob, zle, 100.0 * zle / prob))

    print()
    print("=== NAJCZESTSZE POWODY ===")
    powody: collections.Counter = collections.Counter()
    for w in wpisy:
        if not w.get("udane"):
            powody[str(w.get("powod") or "?")[:58]] += 1
    for powod, ile in powody.most_common(6):
        print("  %3dx  %s" % (ile, powod))
    if not powody:
        print("  (zadnej porazki w tym okresie)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dni", type=int, default=14)
    ap.add_argument("--dzis", action="store_true",
                    help="tylko dzisiejszy stan, jedna linia na rodzaj")
    ap.add_argument("--slad", action="store_true",
                    help="awaryjnosc wg pozycji w serii i odstepu")
    args = ap.parse_args()

    if args.slad:
        return slad(args.dni)

    normy = config.normy_dzienne()
    dni = 1 if args.dzis else args.dni
    zrobione, nieudane = wczytaj(dni)
    kolejne = sorted(zrobione) or [datetime.now(timezone.utc).strftime("%Y-%m-%d")]

    if args.dzis:
        dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        zrobione_przebiegi = przebiegow_dzis()
        print("STAN NA DZIS (%s, UTC) — po %d z %d przebiegow"
              % (dzis, zrobione_przebiegi, config.PRZEBIEGOW_DZIENNIE))
        if zrobione_przebiegi < config.PRZEBIEGOW_DZIENNIE:
            # BEZ TEGO LICZNIK KLAMIE O CZWARTEJ RANO. Doba UTC zaczyna sie w
            # nocy, pierwszy przebieg idzie po 11:00 — wiec do poludnia kazda
            # pozycja pokazuje "0%!!" i wyglada jak awaria. Licznik, ktory
            # codziennie rano krzyczy bez powodu, uczy ignorowania siebie, a
            # wtedy nie zauwazy sie dnia, w ktorym naprawde cos padlo.
            print("   (norma rozklada sie na caly dzien — do konca zostalo %d)"
                  % (config.PRZEBIEGOW_DZIENNIE - zrobione_przebiegi))
        cicho = config.cichy_dzien()
        if cicho:
            print("   >> DZIS JEST CICHY DZIEN — %s wyciszone celowo, zero nie"
                  " jest tu porazka" % ", ".join(config.CICHY_DZIEN_WYCISZA_RODZAJE))
        for r in RODZAJE:
            ile, norma = zrobione[dzis][r], normy.get(r, 0)
            if cicho and r in config.CICHY_DZIEN_WYCISZA_RODZAJE:
                print("  %-12s %3d      — cichy dzien, nie nadajemy" % (r, ile))
            elif r in NIEWYKONALNE:
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

    # CICHY DZIEN NIE JEST DNIEM NIEWYKONANEJ NORMY. Srednia liczy sie dla
    # kazdej pozycji z INNEJ liczby dni: notki i restacki tylko z dni, w
    # ktorych mialy prawo wyjsc. Bez tego jeden dzien na osiem zaniza wynik o
    # jedna osma i po miesiacu wyglada to jak trwaly spadek produkcji.
    ciche = {d for d in kolejne if config.cichy_dzien(_data(d))}
    zalozone = budzety_dzienne()
    sumy = collections.Counter()
    wykonane = collections.Counter()
    plany = collections.Counter()
    dni_liczone = collections.Counter()
    bez_planu = []
    for d in kolejne:
        cicho = d in ciche
        plan_dnia = zalozone.get(d)
        if plan_dnia is None:
            bez_planu.append(d)
        wiersz = "  %-11s" % d
        for r in RODZAJE:
            ile = zrobione[d][r]
            wyciszony = cicho and r in config.CICHY_DZIEN_WYCISZA_RODZAJE
            # PLAN TEGO DNIA, a gdy go nie zapisano — dzisiejsza norma, i
            # wtedy dzien jest oznaczony gwiazdka, zeby nikt nie czytal tego
            # jako pomiaru wykonania.
            cel = (plan_dnia or {}).get(r, normy.get(r, 0))
            if not wyciszony:
                sumy[r] += ile
                dni_liczone[r] += 1
                # WYKONANIE LICZYMY TYLKO Z DNI, KTORYCH PLAN ZNAMY. Dzien bez
                # zapisanego planu podstawialby dzisiejsza norme i alarm
                # meldowalby niewykonanie planu, ktorego nikt wtedy nie mial.
                if plan_dnia is not None:
                    wykonane[r] += ile
                    plany[r] += cel
            wiersz += "%12s" % (
                "cisza" if wyciszony
                else ("%d/%.0f%s" % (ile, cel, _znak(ile, cel)) if cel >= 1
                      else (str(ile) if ile else "-")))
        znaki = ("   << cichy dzien" if cicho else "")
        if plan_dnia is None:
            znaki += "  *plan nieznany"
        print(wiersz + znaki)

    print("  " + "-" * (len(naglowek) - 2))
    n = len(kolejne)

    def _srednia(r):
        ile_dni = dni_liczone[r] or 1
        return sumy[r] / ile_dni

    def _wykonanie(r):
        """Ile z tego, co agent SOBIE ZALOZYL, naprawde zrobil."""
        return (100.0 * wykonane[r] / plany[r]) if plany[r] else None

    for etykieta, wart in (
            ("SREDNIA", lambda r: "%.1f" % _srednia(r)),
            ("% PLANU", lambda r: ("%.0f%%" % _wykonanie(r)
                                   if _wykonanie(r) is not None else "-")),
            ("% NORMY", lambda r: ("%.0f%%" % (100.0 * _srednia(r) / normy[r])
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

    if ciche:
        print("  ciche dni w oknie: %d (%s) — %s nie licza sie z nich do sredniej"
              % (len(ciche), ", ".join(sorted(ciche)),
                 ", ".join(config.CICHY_DZIEN_WYCISZA_RODZAJE)))

    if bez_planu:
        print("  dni bez zapisanego planu (*): %d — mierzone dzisiejsza norma,"
              " wiec to NIE jest pomiar wykonania" % len(bez_planu))

    # ALARM NA WYKONANIU PLANU, NIE NA AMBICJI. Norma mowi, dokad zmierzamy;
    # plan mowi, co agent mial dzis zrobic. Tylko drugie jest pod jego
    # kontrola, a alarm ma budzic wtedy, gdy cos NIE DZIALA — nie wtedy, gdy
    # konto jest mlode albo widelki podniesiono wczoraj.
    ponizej = [r for r in RODZAJE
               if r not in NIEWYKONALNE and _wykonanie(r) is not None
               and _wykonanie(r) < config.PROG_ALARMU_WOLUMENU]
    if ponizej:
        print()
        print("  PONIZEJ PROGU %d%% WYKONANIA PLANU: %s"
              % (config.PROG_ALARMU_WOLUMENU, ", ".join(ponizej)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
