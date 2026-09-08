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
import collections
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


# --- CZY FAKT DOTYCZY DZIEDZINY, O KTORA PYTALISMY -------------------------
#
# DLACZEGO TA MIARA ZASTEPUJE PODZIAL BRANZA/SWIAT. Tamten podzial sprawdzilem
# 8 wrzesnia na czternastu faktach oznaczonych recznie: stary klasyfikator
# zgadzal sie ze mna w 71%, moj przepisany w 64%. Za malo, zeby cokolwiek na
# tym budowac — i powod jest strukturalny, nie do zalatania slowami: KAZDY fakt
# jest o AI, a konto celowo ubiera skutek w jezyk ludzki („twoj rachunek",
# „klasa twojego dziecka"), wiec prawie wszystko wyglada jak „oba".
#
# Ta miara nie pyta, CZY temat jest ludzki. Pyta, czy model odpowiedzial na to,
# o co go zapytano — a to jest sprawdzalne bez zadnej mojej listy slow.
#
# ZASADA: slowo rozroznia, gdy jest RZADKIE w naszym korpusie. „model", „data",
# „AI" sa wszedzie i nie znacza nic; „classroom", „megawatt", „pelican" znacza.
# Rzadkosc liczona Z DANYCH (czestosc w faktach banku), nie z mojej oceny.
#
# SKALIBROWANE NA ZYWYM BANKU (131 faktow, 8 wrzesnia):
#     fakt pasuje do WLASNEJ dziedziny (tej, ktora model sam mu nadal):  60%
#     fakt pasuje do CUDZEJ, losowej:                                     3%
# To jest sufit i podloga tego przyrzadu. Przy pieciu dziedzinach naraz poziom
# przypadku wynosi okolo 14% (piec szans po 3%). Wynik bliski 14% znaczy, ze
# dziedziny sa ignorowane; wynik bliski 60% — ze sa realizowane.
STOP = set("""a an the and or of to in on for with by from as at is are was were
be been being that this these those it its it's not no than then so such which
who whom whose what when where how why can could will would may might must
you your yours we our us they their them he she his her i me my one two three
new now more most less least own same other another each every all any some
about into over under after before between during without within across
""".split())


def slowa(tekst):
    return [w for w in re.findall(r"[a-z][a-z'\-]{2,}", (tekst or "").lower())
            if w not in STOP]


def czestosci(korpus):
    """Ile RÓZNYCH tekstow zawiera dane slowo. Liczone z danych, nie z glowy."""
    df = collections.Counter()
    for t in korpus:
        for w in set(slowa(t)):
            df[w] += 1
    return df, len(korpus)


def rzadkie(tekst, df, ile_tekstow, prog=0.10):
    """Slowa z tekstu, ktore wystepuja w mniej niz `prog` czesci korpusu."""
    return {w for w in set(slowa(tekst))
            if df.get(w, 0) < max(2, prog * ile_tekstow)}


def dotyczy(fakt_tekst, dziedzina, df, ile_tekstow):
    kluczowe = rzadkie(dziedzina, df, ile_tekstow)
    if not kluczowe:
        return None            # dziedzina bez rzadkich slow — nie orzekamy
    wf = set(slowa(fakt_tekst))
    return bool(kluczowe & wf)


def zaszereguj(fakt):
    """BRANZA / SWIAT / OBA / ZADNE — po polach, ktore niosa tresc."""
    t = " ".join(str((fakt or {}).get(k) or "")
                 for k in ("domain", "fact", "consequence", "actually"))
    b, s = bool(BRANZA.search(t)), bool(SWIAT.search(t))
    return "OBA" if b and s else "BRANZA" if b else "SWIAT" if s else "ZADNE"


def host(url):
    """Sam host adresu, bez `www.` — do liczenia RÓZNORODNOSCI ZRODEL."""
    from urllib.parse import urlparse
    try:
        return (urlparse(str(url or "")).netloc or "").lower().replace("www.", "")
    except ValueError:
        return ""


def zrodla(nazwa, fakty):
    """Ile ROZNYCH hostow — najostrzejsza i najtansza miara monotonii.

    ZMIERZONE 8 wrzesnia 2026 i to bylo znalezisko dnia: 32 swieze fakty
    z pieciu szukan pochodzily z CZTERECH hostow (latent.space 11,
    pytorch.org 10, simonwillison.net 6, importai.substack.com 5), podczas gdy
    bank narastajacy tygodniami ma 88 roznych hostow na 131 faktow.
    Czytelnik sledzacy ktorykolwiek z tych czterech widzial juz wszystko.

    Ta miara nie wymaga zadnej mojej listy slow ani osadu, co jest „o swiecie".
    Liczy hosty.
    """
    lic = collections.Counter(host(f.get("url")) for f in fakty)
    n = max(1, len(fakty))
    naj = lic.most_common(1)[0][1] if lic else 0
    print("  %-22s ROZNYCH ZRODEL: %2d na %2d faktow   najczestsze: %d (%.0f%%)"
          % (nazwa, len(lic), len(fakty), naj, 100.0 * naj / n))
    for h, k in lic.most_common(6):
        print("      %-40s %d" % (h or "(brak url)", k))
    return len(lic)


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
    zrodla("bank", _wolne)
    print("      (podzial branza/swiat zgadza sie z recznym oznaczeniem tylko"
          " w 64-71% — patrz komentarz wyzej. Traktowac jako TLO, nie pomiar.)")

    # CZESTOSCI SLOW Z BANKU — podstawa miary „czy fakt dotyczy dziedziny".
    # Liczone raz, z produkcyjnego banku, zeby „rzadkosc" znaczyla to samo
    # przy kazdym uruchomieniu.
    _korpus = [" ".join(str(f.get(k) or "") for k in
                        ("fact", "consequence", "actually")) for f in _wolne]
    DF, ILE_TEKSTOW = czestosci(_korpus)
    print("      korpus do miary dopasowania: %d faktow, %d roznych slow"
          % (ILE_TEKSTOW, len(DF)))

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
    dopasowania = []
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
            # CZY MODEL ODPOWIEDZIAL NA TO, O CO GO ZAPYTANO.
            _lista_dziedzin = [d.strip() for d in
                               (dziedziny_uzyte[-1] or "").split(",") if d.strip()]
            if fakty and _lista_dziedzin:
                _trafione = 0
                for _f in fakty:
                    _tf = " ".join(str(_f.get(k) or "") for k in
                                   ("domain", "fact", "consequence", "actually"))
                    if any(dotyczy(_tf, _d, DF, ILE_TEKSTOW) for _d in _lista_dziedzin):
                        _trafione += 1
                dopasowania.append((_trafione, len(fakty)))
                print("  DOTYCZY PODANYCH DZIEDZIN: %d z %d (%.0f%%)"
                      % (_trafione, len(fakty), 100.0 * _trafione / len(fakty)))
            # FAKTY ZAPISANE NA DYSK, zeby nie placic drugi raz za te same dane.
            # Pierwsze uruchomienie ich nie zapisalo i cala analiza przepadla.
            for _f in fakty:
                _f["_dziedziny_zamowione"] = dziedziny_uzyte[-1]
                _f["_szukanie"] = nr + 1
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
    print("=== ROZNORODNOSC ZRODEL — najostrzejsza miara monotonii ===")
    zrodla("%d faktow z %d szukan" % (len(wszystkie), a.ile), wszystkie)
    print("      punkt odniesienia z 8 wrzesnia: 4 ZRODLA na 32 fakty.")
    print("      bank narastajacy tygodniami: 88 zrodel na 131 faktow.")

    print()
    print("=== CZY MODEL ODPOWIADAL NA ZADANE PYTANIE ===")
    if dopasowania:
        _t = sum(x for x, _ in dopasowania)
        _w = sum(y for _, y in dopasowania)
        print("  DOTYCZY PODANYCH DZIEDZIN: %d z %d (%.0f%%)"
              % (_t, _w, 100.0 * _t / max(1, _w)))
        print("  skala tego przyrzadu, zmierzona na banku:")
        print("     ~60%%  = dziedziny sa realizowane (fakt wobec WLASNEJ dziedziny)")
        print("     ~14%%  = poziom przypadku przy pieciu dziedzinach")
        print("     ~ 3%%  = fakt wobec CUDZEJ, losowej dziedziny")
    else:
        print("  (brak danych — zadne szukanie nic nie oddalo)")

    _plik = pathlib.Path("/tmp/proba_tematow_fakty.json")
    try:
        _plik.write_text(json.dumps(wszystkie, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        print()
        print("  fakty zapisane do %s (%d szt.) — kolejna analiza jest darmowa"
              % (_plik, len(wszystkie)))
    except OSError as exc:
        print("  nie zapisalem faktow: %r" % exc)

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
