# -*- coding: utf-8 -*-
"""Czy zmiana promptu naprawde przesunela SKLAD TEMATOW. Nic nie publikuje.

PO CO TO POWSTALO. Do 8 wrzesnia 2026 nie mielismy jak sprawdzic, czy zmiana
promptu cokolwiek zrobila, ZANIM wyjdzie na konto. 7 wrzesnia zmienilem
`ciekawostki.md` w trzech miejscach i jedyna dostepna weryfikacja brzmiala
„poczekaj tydzien i przelicz bank" — czyli pomiar spozniony o tydzien
i zanieczyszczony wszystkim, co sie w tym tygodniu wydarzylo.

SKAD POMYSL. Z przegladu drugiego agenta (`narzedzia/proba_glosu.py` w repo
`nia-substack-agent`). Wziete stamtad sa TRZY rzeczy, i zadna z nich to kod:

  1. DZIESIEC PROBEK, NIE JEDNA. Ich komentarz: „trzy nie odroznia 5/10 od
     8/10". Jedna probka to anegdota.
  2. POWIEDZ WPROST, GDY POROWNANIE JEST NIEWAZNE, zamiast po cichu usrednic.
  3. MELDUJ KOSZT I LICZBE PLATNYCH WYWOLAN przy kazdym przebiegu.

Ich CZTERECH KRYTERIOW nie wzialem, bo sprawdzilem je na naszych danych i nie
pasuja: regula „koncz notke rozkazem" pogorszylaby nas (22,1 wobec 31,1
wyswietlen, n=18 wobec 42), slow recenzenta nie mamy ani razu na 63 notkach,
a dlugosc pilnuje juz `zakres_slow`. Ich narzedzie mierzy GLOS — nasz glos
zmierzylem i jest w porzadku (60 roznych otwarc na 60 notkach). Nasz zmierzony
problem to SKLAD TEMATOW, wiec to narzedzie mierzy jego.

PUNKT ODNIESIENIA, zmierzony 7 wrzesnia TYM SAMYM klasyfikatorem co nizej
(131 wolnych faktow w banku): **branza 70%, swiat 6%, oba 21%**. Dlatego
klasyfikator stoi w tym pliku, a nie jest wymyslany za kazdym razem — pomiar
przed i po musi isc tym samym przyrzadem, inaczej porownuje sie przyrzady.

CZEGO TO NARZEDZIE NIE ROBI:
  - nie publikuje niczego,
  - NIE DOPISUJE FAKTOW DO BANKU. `znajdz_ciekawostki` normalnie je tam
    wpisuje (`dopisz_kandydatow`); tutaj ten zapis jest przechwycony, a plik
    indeksu jest liczony sha256 PRZED i PO, i przebieg konczy sie bledem,
    jesli sie zmienil. Bez tego sprawdzanie zasmiecaloby bank, ktory bada.

KOSZT: okolo 0,078 USD za jedno szukanie (zmierzone na produkcji, 7 dni).
Dziesiec probek to okolo 0,78 USD. Idzie torem `test`, wiec NIE zjada
dobowego sufitu konta — ale koszt jest ZAPISYWANY, bo 53% rachunku za sierpien
okazalo sie moimi wlasnymi uruchomieniami i nikt tego nie widzial.

URUCHAMIANIE, z korzenia repozytorium:
    python agent-v2/tests/platne/proba_tematow.py --live --ile 10
"""
import argparse
import hashlib
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent-v2"))

# KLASYFIKATOR — JEDEN, WSPOLNY DLA POMIARU PRZED I PO.
#
# Te same dwa wzorce, ktorymi 7 wrzesnia zmierzylem bank na 70/6. Gdyby
# narzedzie liczylo inaczej niz punkt odniesienia, „przesuniecie" bylo by
# roznica miedzy przyrzadami, a nie miedzy stanami.
BRANZA = re.compile(
    r"(pricing|price|token|benchmark|model|release|launch|funding|valuation|"
    r"revenue|API|open.?weight|leaderboard|GPU|chip|compute|data ?cent|"
    r"inference|training run|startup|acquisition|IPO)", re.I)
SWIAT = re.compile(
    r"(patient|doctor|hospital|school|student|teacher|court|judge|law|worker|"
    r"job|employee|climate|weather|drug|disease|farm|city|police|election|"
    r"child|nurse|prison|housing|energy bill|welfare)", re.I)


def zaszereguj(fakt):
    """BRANZA / SWIAT / OBA / ZADNE — po polach, ktore niosa tresc."""
    t = " ".join(str((fakt or {}).get(k) or "")
                 for k in ("domain", "fact", "consequence", "actually"))
    b, s = bool(BRANZA.search(t)), bool(SWIAT.search(t))
    return "OBA" if b and s else "BRANZA" if b else "SWIAT" if s else "ZADNE"


def odcisk(sciezka):
    p = pathlib.Path(sciezka)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "brak"


def podsumuj(nazwa, fakty):
    lic = {"BRANZA": 0, "SWIAT": 0, "OBA": 0, "ZADNE": 0}
    for f in fakty:
        lic[zaszereguj(f)] += 1
    n = max(1, len(fakty))
    print("  %-22s branza %2d (%3.0f%%)   swiat %2d (%3.0f%%)   oba %2d   zadne %2d"
          % (nazwa, lic["BRANZA"], 100.0 * lic["BRANZA"] / n,
             lic["SWIAT"], 100.0 * lic["SWIAT"] / n, lic["OBA"], lic["ZADNE"]))
    return lic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true",
                   help="Zgoda na PLATNE wywolania. Bez tego nic sie nie dzieje.")
    p.add_argument("--ile", type=int, default=3, choices=range(1, 11),
                   metavar="1..10",
                   help="Ile szukan. Trzy nie odrozni 70%% od 50%%; dziesiec odrozni.")
    a = p.parse_args()
    if not a.live:
        p.error("Dodaj --live, zeby pozwolic na platne szukanie. "
                "To narzedzie NIGDY nie publikuje i nie dopisuje do banku.")

    import config
    import db
    import stages

    if config.W_TESCIE:
        p.error("Wykryto tor DARMOWY — model nie zostanie zawolany. "
                "Uruchom ten plik ze sciezki `tests/platne/`.")

    INDEKS = pathlib.Path(config.DATA_DIR) / "indeks_kandydatow.json"
    PRZED = odcisk(INDEKS)
    print("=== PUNKT ODNIESIENIA: BANK, JAKI JEST TERAZ ===")
    try:
        _sur = json.loads(INDEKS.read_text(encoding="utf-8"))
        _lista = _sur if isinstance(_sur, list) else (
            _sur.get("fakty") or next((v for v in _sur.values()
                                       if isinstance(v, list) and v), []))
        _wolne = [f for f in _lista if isinstance(f, dict) and not f.get("wydany")]
    except (OSError, ValueError):
        _wolne = []
    podsumuj("bank (%d wolnych)" % len(_wolne), _wolne)
    print("      (7 wrzesnia tym samym przyrzadem: branza 70%, swiat 6%)")

    # ZAPIS DO BANKU PRZECHWYCONY. Bez tego kazde sprawdzenie zasmiecaloby
    # zbior, ktory bada — a fakty z proby nie przeszly przez zadna z bramek,
    # ktore przechodza fakty produkcyjne.
    zebrane = []
    oryginal = stages.dopisz_kandydatow

    def _nie_zapisuj(kandydaci, **k):
        zebrane.append(list(kandydaci or []))
        return {"dopisane": 0, "proba": True}

    # DWIE BRAMKI PRODUKCYJNE TRZEBA OBEJSC — i to jest wlasciwe, nie sprytne.
    #
    # `znajdz_ciekawostki` odmawia szukania, gdy (a) dzis juz dobieralismy do
    # banku, albo (b) bank jest pelny. Obie decyzje sa poprawne w produkcji
    # i obie nie maja nic wspolnego z tym, co to narzedzie mierzy: JAKIE fakty
    # wychodza, gdy szukanie sie odbedzie.
    #
    # ZLAPANE PRZY PIERWSZYM URUCHOMIENIU: dziesiec „szukan" oddalo po zero
    # faktow, ZERO platnych wywolan i komunikat „(nie znalazlem)" przy
    # dziedzinach. Narzedzie meldowalo 0% branzy i 0% swiata — czyli liczbe,
    # ktora wygladala na pomiar, a byla cisza. Dlatego nizej jest nie tylko
    # obejscie, ale i JAWNY MELDUNEK, gdy szukanie mimo to odmowi.
    #
    # Obejscie jest bezpieczne, bo narzedzie nic nie dopisuje do banku
    # (`_nie_zapisuj`) i sprawdza to odciskiem pliku.
    _stary_sufit = config.BANK_MAKS_WOLNYCH
    _stare_proby = config.SZUKANIE_BANKU_MAKS_PROB
    _stare_na_dobe = config.SZUKANIE_BANKU_NA_DOBE
    config.BANK_MAKS_WOLNYCH = 10 ** 6      # „bank nigdy nie jest pelny"
    config.SZUKANIE_BANKU_MAKS_PROB = 10 ** 6
    config.SZUKANIE_BANKU_NA_DOBE = 10 ** 6
    print()
    print("  (bramki „bank pelny\" i „raz na dobe\" zdjete NA CZAS PROBY —")
    print("   narzedzie mierzy WYNIK szukania, nie decyzje o szukaniu)")

    conn = db.connect()
    run_id = db.start_run(conn, "proba-tematow", tryb="test")
    wszystkie = []
    dziedziny_uzyte = []
    z_zaczynem = []
    try:
        stages.dopisz_kandydatow = _nie_zapisuj
        for nr in range(a.ile):
            print()
            print("=== SZUKANIE %d z %d ===" % (nr + 1, a.ile))
            bufor = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(bufor):
                fakty = stages.znajdz_ciekawostki(conn, run_id)
            wyjscie = bufor.getvalue()
            # Dziedziny i obecnosc zaczynu odczytujemy z linii, ktore kod
            # DRUKUJE SAM. Gdy prefiks sie zmieni, mowimy „nie znalazlem"
            # zamiast podac zmyslona liczbe.
            m = re.search(r"\[ciekawostki\] dziedziny: (.+)", wyjscie)
            dziedziny_uzyte.append(m.group(1).strip() if m else "(nie znalazlem)")
            z = re.search(r"\[ciekawostki\] zaczyn z kanalow: (\w+)", wyjscie)
            z_zaczynem.append(z.group(1) if z else "?")
            print("  dziedziny: %s" % dziedziny_uzyte[-1][:96])
            print("  zaczyn z kanalow: %s" % z_zaczynem[-1])
            fakty = fakty or []
            # ZERO FAKTOW TO NIE JEST WYNIK — to jest cisza, i ma sie czytac
            # jak cisza. Pierwsze uruchomienie tego narzedzia zameldowalo
            # „0% branzy, 0% swiata" przy zerze platnych wywolan; wygladalo
            # jak pomiar, a bylo odmowa szukania.
            if not fakty:
                print("  SZUKANIE NIC NIE ODDALO — pelne wyjscie ponizej:")
                for _l in (wyjscie or "(nic nie wypisalo)").splitlines()[-12:]:
                    print("      | %s" % _l[:110])
            wszystkie.extend(fakty)
            podsumuj("to szukanie (%d)" % len(fakty), fakty)
            for f in fakty[:3]:
                print("      [%-6s] %s" % (zaszereguj(f),
                                           str(f.get("domain") or "")[:58]))
        db.finish_run(conn, run_id, "DONE", "proba-tematow")
    except BaseException:
        db.finish_run(conn, run_id, "FAILED", "proba-tematow")
        raise
    finally:
        stages.dopisz_kandydatow = oryginal
        config.BANK_MAKS_WOLNYCH = _stary_sufit
        config.SZUKANIE_BANKU_MAKS_PROB = _stare_proby
        config.SZUKANIE_BANKU_NA_DOBE = _stare_na_dobe

    print()
    print("=== RAZEM ===")
    lic = podsumuj("%d faktow z %d szukan" % (len(wszystkie), a.ile), wszystkie)

    wiersz = conn.execute(
        "SELECT count(*), sum(cost_usd) FROM calls WHERE run_id = ?",
        (run_id,)).fetchone()
    conn.close()

    PO = odcisk(INDEKS)
    print()
    print("=== CZY NICZEGO NIE ZEPSULEM ===")
    print("  bank NIETKNIETY: %s" % ("TAK" if PRZED == PO else "NIE!!!"))
    print("  przechwyconych prob zapisu do banku: %d" % len(zebrane))
    print("  platnych wywolan: %s   koszt: %.4f USD"
          % (wiersz[0], wiersz[1] or 0.0))
    print("  opublikowanych: 0")
    print()
    print("=== CZY POROWNANIE JEST WAZNE ===")
    # Dziedziny SA losowane przy kazdym szukaniu i tak ma byc — to one sa
    # badanym mechanizmem. Ale gdyby wszystkie szukania dostaly ten sam zestaw,
    # mierzylibysmy jeden przypadek, nie rozklad.
    print("  roznych zestawow dziedzin: %d na %d szukan"
          % (len(set(dziedziny_uzyte)), a.ile))
    print("  szukan z zaczynem: %s" % ", ".join(z_zaczynem))
    if len(set(dziedziny_uzyte)) == 1 and a.ile > 1:
        print("  UWAGA: wszystkie szukania dostaly TEN SAM zestaw dziedzin —")
        print("  to jest jeden przypadek powtorzony, nie rozklad.")
    if a.ile < 10:
        print("  UWAGA: %d probek. Do odroznienia 70%% od 50%% trzeba dziesieciu."
              % a.ile)
    if PRZED != PO:
        print()
        print("  BLAD: PLIK BANKU SIE ZMIENIL. Przechwycenie zapisu nie zadzialalo.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
