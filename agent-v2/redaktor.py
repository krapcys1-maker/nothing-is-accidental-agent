# -*- coding: utf-8 -*-
"""REDAKTOR W CIENIU (R1, 1.11.2026) — cotygodniowy dziennik decyzji redakcji: obserwacje, propozycje, przewidywania, rozliczenie.

PO CO. Wlasciciel (1.11): bot ma dzialac bardziej jak czlowiek — analizowac, co przynosi sukces, na tej podstawie wybierac tematy, proponowac
research, styl i dlugosc notek, i podejmowac decyzje. `co_dziala.py` juz liczy co noc, co dziala (formaty, wymiary notki, werdykty z bootstrapu
po niezaleznych jednostkach), ale to raport dla CZLOWIEKA: nic z niego nie wraca do bota. Ten modul jest pierwszym krokiem: raz w tygodniu czyta
ten raport (`obserwatorium/co_dziala.json`) i zapisuje, CO REDAKTOR BY POSTANOWIL, dlaczego, i czego sie spodziewa — a po terminie rozlicza
swoje przewidywania (jak `zaklady.py`, tylko dla decyzji redakcyjnych). To jest CIEN: nic z tego nie zmienia ani tematow, ani stylu, ani dlugosci,
ani zadnego tekstu, ani doboru celow. Wykonywanie propozycji (R2) wymaga protokolu oceny i nigdy nie rusza w oknie bazowym pamieci (uzgodnienie
z sesja badawcza, tablica P-013).

CO ROBI. (1) Bierze z raportu grupy z wymiarow notki (kat, kategoria, dlugosc, pora, forma, styk, pytanie...) i klasyfikuje je wg WERDYKTU, ktory
policzyl `co_dziala` (lepiej / gorzej / brak dowodu / za malo danych / odniesienie) — sam NIE liczy statystyki od nowa. (2) Z mocnych sygnalow robi
propozycje (zwiekszyc / ograniczyc udzial grupy jako EKSPERYMENT), ze slabych — „kandydatow do sprawdzenia" (dosc notek, niezaleznych jednostek,
wyrazna przewaga i dluzsze okno dla wymiarow dzien/pora), a gdy zadnej grupy nie da sie jeszcze rozroznic od szumu, pisze to wprost: „nie zmieniac
polityki, zbierac dane". (3) Do kazdej propozycji dopisuje przewidywanie, ktore da sie sprawdzic z kolejnych raportow, i rozlicza stare po terminie
(potwierdzone / chybione / bez rozstrzygniecia — to ostatnie, gdy nowych danych za malo). (4) Pisze notatke redaktora dla czlowieka:
`obserwatorium/redaktor.md`.

JAK ROZLICZA (po dwoch przegladach 1.11): okno `co_dziala` jest KUMULATYWNE (stale `od`), wiec ten sam raport po 14 dniach zawiera notki, ktore
dały sygnal. Dlatego kazde przewidywanie o grupie sprawdza sie dopiero po przyroscie NOWYCH danych: co najmniej MIN_NOWYCH notek i
MIN_NOWYCH_KLASTROW niezaleznych jednostek (inaczej „bez rozstrzygniecia”). (a) Przewidywanie o „kandydacie” porownuje NOWE notki grupy z NOWYMI
notkami grupy odniesienia (ta sama os co dowod; szacunek z przyrostu: srednia logarytmow wzgl. tla z chwili zapisu i teraz), a nie z tlem, bo
cały wymiar moze miec wspolne przesuniecie wzgledem tla. (b) Przewidywanie o mocnym sygnale sprawdza WERDYKT grupy po przyroscie danych: ten sam
= potwierdzone, odwrocony albo zanik przedzialu („brak dowodu”) = chybione. (c) Zmiana okna raportu lub grupy odniesienia uniewaznia porownanie.
(d) Ta sama grupa i typ przewidywania nie wracaja co tydzien, dopoki poprzednie nie jest rozliczone (takze „nie zmieniac polityki”).
UCZCIWIE: wymiarow jest wiele (kilkadziesiat grup), a poprawki na wielokrotne testy nie ma — przy kilkudziesieciu grupach „mocny sygnal” z samego
szumu pojawia sie niemal zawsze. Odsetek „potwierdzone” z cienia NIE jest dowodem, ze redaktor ma racje; sluzy do kalibracji dopiero z R2.

CZEGO NIE ROBI. Bez modelu, bez sieci. Zapisuje WYLACZNIE liczby zbiorcze i nazwy grup (kategorie, formaty): zadnych tekstow notek, zadnych
uchwytow ani danych czytelnikow (P-013 pkt 5). Nic nie zapisuje, jesli nie ma swiezego raportu (starszego niz doba). Nie zmienia `co_dziala.py`
ani niczego, co bot czyta przy pisaniu.

EPOKA REDAKCYJNA. Kazdy rekord ma `epoka_redakcyjna`; zmiana POLITYKI (R2 i dalej) podnosi numer, zeby analiza pamieci mogla stratyfikowac po epoce
(P-013 pkt 4). Dopoki polityka sie nie zmienia (cien), numer to 0. Rekord epoki niesie tez statusy trwajacych eksperymentow (zmienne dla analizy).
"""
from __future__ import annotations

import json
import math
import subprocess
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config

WERSJA_SCHEMATU = 1
EPOKA_REDAKCYJNA = 0              # polityka bez zmian (cien); R2 podniesie
PLIK = "redaktor_cien.jsonl"
RAPORT = "redaktor.md"
MIN_NOTEK = 8                     # ponizej tylu notek z pomiarem nie wyciagamy wnioskow o polityce
MAKS_PROPOZYCJI = 5
HORYZONT_DNI = 14                 # po tylu dniach sprawdzamy przewidywanie
MIN_NOWYCH = 4                    # tyle NOWYCH notek grupy trzeba, zeby rozliczyc przewidywanie o kandydacie
MAKS_BAJTOW = 10 * 1024 * 1024
# Kandydat do sprawdzenia (grupa BEZ przedzialu ufnosci) musi miec dosc notek, niezaleznych jednostek i wyrazna przewage, zeby nie gonic
# za szumem: na zywym raporcie z 1.11 (12 notek, mediana 11 wyswietlen) grupy po 3 notki z przewaga 1,02-1,54 byly samym szumem.
KAND_MIN_N = 4
KAND_MIN_KLASTROW = 3
KAND_MIN_WZGL = 1.15                # przewaga NAD GRUPA ODNIESIENIA (wzgl_tla grupy / wzgl_tla odniesienia)
MIN_NOWYCH_KLASTROW = 2           # tyle NOWYCH niezaleznych jednostek trzeba, zeby rozliczyc przewidywanie o grupie
KAND_FRAKCJA_WYKRYWALNEGO = 0.5   # przewaga musi byc co najmniej taka czescia „wykrywalnego efektu” raportu
OKNO_DLA_DNIA_I_PORY = 14         # wymiary dzien i pora: przy krotszym oknie grupa to jedna data kalendarzowa, nie niezalezny tydzien

# Wymiar raportu -> rodzaj propozycji. Wymiary spoza tabeli to „styl”.
RODZAJ_WYMIARU = {"kat": "temat", "kategoria": "temat", "dlugosc": "dlugosc", "pora": "pora", "dzien": "pora"}
# Wymiary, z ktorych NIE robimy propozycji: opisuja kto pisal, a nie co czytelnika interesuje.
POMIJANE_WYMIARY = {"model", "pozycja"}


def _kat(katalog: Path | str | None) -> Path:
    return Path(katalog) if katalog else Path(config.DATA_DIR)


def _jsonl(plik: Path) -> list[dict[str, Any]]:
    try:
        tekst = plik.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for linia in tekst.split("\n"):
        linia = linia.strip()
        if not linia:
            continue
        try:
            w = json.loads(linia)
        except ValueError:
            continue
        if isinstance(w, dict):
            out.append(w)
    return out


def _tydzien(dzien: date) -> str:
    rok, tydz, _ = dzien.isocalendar()
    return "%d-W%02d" % (rok, tydz)


def _kod() -> str:
    """Skrot commita. Bez `import stages` (to wciaga caly graf modulow bota do procesu obserwatorium): wprost z gita, z limitem czasu."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, errors="replace", timeout=5,
                              cwd=str(Path(__file__).resolve().parent)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def wczytaj_raport(kat: Path) -> dict[str, Any] | None:
    """`obserwatorium/co_dziala.json` albo None (brak lub uszkodzony)."""
    try:
        d = json.loads((kat / "obserwatorium" / "co_dziala.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and isinstance(d.get("wymiary"), dict) else None


def _klasa(g: dict[str, Any], jest_odniesieniem: bool) -> str:
    """lepiej / gorzej / brak_dowodu / za_malo / odniesienie — wg werdyktu policzonego przez `co_dziala` (nie liczymy od nowa)."""
    if jest_odniesieniem:
        return "odniesienie"
    w = str(g.get("werdykt") or "")
    if w.startswith("lepiej"):
        return "lepiej"
    if w.startswith("gorzej"):
        return "gorzej"
    if w.startswith("brak dowodu"):
        return "brak_dowodu"
    return "za_malo"


def sygnaly(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Plaska lista grup ze wszystkich wymiarow: {id, wymiar, grupa, klasa, n, klastrow, wzgl_tla, stosunek, przedzial_95, odniesienie, ostroznie...}."""
    out = []
    for wymiar, tab in (d.get("wymiary") or {}).items():
        if not isinstance(tab, dict):
            continue
        ref = tab.get("odniesienie")
        g_ref = (tab.get("grupy") or {}).get(ref) if ref is not None else None
        wzgl_odn = g_ref.get("wzgl_tla") if isinstance(g_ref, dict) else None
        n_odn = g_ref.get("n") if isinstance(g_ref, dict) else None
        for nazwa, g in (tab.get("grupy") or {}).items():
            if not isinstance(g, dict):
                continue
            w = g.get("wzgl_tla")
            przewaga = (round(w / wzgl_odn, 3) if isinstance(wzgl_odn, (int, float)) and wzgl_odn > 0 else w) if isinstance(w, (int, float)) else None
            out.append({
                "id": "%s|%s" % (wymiar, nazwa), "wymiar": wymiar, "grupa": str(nazwa),
                "klasa": _klasa(g, nazwa == ref), "n": g.get("n"), "klastrow": g.get("klastrow"),
                "wzgl_tla": g.get("wzgl_tla"), "stosunek": g.get("stosunek"), "przedzial_95": g.get("przedzial_95"),
                "wykrywalny_efekt": g.get("wykrywalny_efekt"), "odniesienie": ref, "wzgl_odn": wzgl_odn, "n_odn": n_odn, "przewaga": przewaga,
                "ostroznie": "OSTROZNIE" in str(g.get("werdykt") or ""), "za_malo": bool(g.get("za_malo"))})
    return out


def _liczniki(sygn: list[dict[str, Any]]) -> dict[str, int]:
    out = {"lepiej": 0, "gorzej": 0, "brak_dowodu": 0, "za_malo": 0, "odniesienie": 0}
    for s in sygn:
        out[s["klasa"]] += 1
    return out


def _termin(dzis: date) -> str:
    return (dzis + timedelta(days=HORYZONT_DNI)).isoformat()


def _dowod(s: dict[str, Any]) -> dict[str, Any]:
    return {k: s[k] for k in ("id", "n", "klastrow", "wzgl_tla", "wzgl_odn", "przewaga", "stosunek", "przedzial_95", "odniesienie", "ostroznie")}


def _przew_werdykt(s: dict[str, Any], dzis: date, okno_od: Any) -> dict[str, Any]:
    return {"typ": "grupa_werdykt", "wymiar": s["wymiar"], "grupa": s["grupa"], "oczekiwana": s["klasa"], "odniesienie": s["odniesienie"],
            "n_przy_zapisie": s["n"], "klastrow_przy_zapisie": s["klastrow"], "min_nowych": MIN_NOWYCH, "min_nowych_klastrow": MIN_NOWYCH_KLASTROW,
            "okno_od": okno_od, "sprawdz_po": _termin(dzis),
            "opis": "po %d dniach i co najmniej %d nowych notkach (%d nowych niezaleznych jednostkach) werdykt grupy %s/%s wzgledem odniesienia „%s” "
                    "nadal bedzie „%s”" % (HORYZONT_DNI, MIN_NOWYCH, MIN_NOWYCH_KLASTROW, s["wymiar"], s["grupa"], s["odniesienie"], s["klasa"])}


def _przew_nowe(s: dict[str, Any], dzis: date, okno_od: Any) -> dict[str, Any]:
    wzgledem = "odniesienie" if isinstance(s.get("wzgl_odn"), (int, float)) and s["wzgl_odn"] > 0 and isinstance(s.get("n_odn"), int) else "tlo"
    return {"typ": "grupa_nowe_notki", "wymiar": s["wymiar"], "grupa": s["grupa"], "odniesienie": s["odniesienie"], "wzgledem": wzgledem,
            "n_przy_zapisie": s["n"], "wzgl_przy_zapisie": s["wzgl_tla"], "klastrow_przy_zapisie": s["klastrow"],
            "odn_n_przy_zapisie": s.get("n_odn"), "odn_wzgl_przy_zapisie": s.get("wzgl_odn"),
            "wartosc_odniesienia": 1.0, "min_nowych": MIN_NOWYCH, "min_nowych_klastrow": MIN_NOWYCH_KLASTROW, "okno_od": okno_od,
            "sprawdz_po": _termin(dzis),
            "opis": "po %d dniach NOWE notki grupy %s/%s (co najmniej %d, w co najmniej %d nowych niezaleznych jednostkach) beda srednio %s" % (
                HORYZONT_DNI, s["wymiar"], s["grupa"], MIN_NOWYCH, MIN_NOWYCH_KLASTROW,
                ("nie gorsze niz nowe notki grupy odniesienia „%s”" % s["odniesienie"]) if wzgledem == "odniesienie" else "powyzej tla (wzgl. tla >= 1,0)")}


def _okno_dni(d: dict[str, Any], dzis: date) -> int | None:
    try:
        return (dzis - date.fromisoformat(str(d.get("od"))[:10])).days
    except ValueError:
        return None


def propozycje(d: dict[str, Any], sygn: list[dict[str, Any]], dzis: date, tydzien: str,
               otwarte: set[tuple[str, str, str]] | None = None) -> tuple[list[dict[str, Any]], int]:
    """(propozycje, ile obcieto). Do MAKS_PROPOZYCJI; przy braku mocnych sygnalow pierwsza to „nie zmieniac polityki”.
    `otwarte` = (wymiar, grupa, typ przewidywania) z nierozliczonych poprzednich epok: te same nie wracaja co tydzien."""
    otwarte = otwarte or set()
    n_notek = int(d.get("notek_z_pomiarem") or 0)
    out: list[dict[str, Any]] = []
    okno = _okno_dni(d, dzis)

    def dodaj(typ: str, tresc: str, uzasadnienie: str, dowod: dict[str, Any], przewidywanie: dict[str, Any]) -> None:
        out.append({"id": "R-%s-%d" % (tydzien, len(out) + 1), "typ": typ, "tresc": tresc, "uzasadnienie": uzasadnienie,
                    "dowod": dowod, "przewidywanie": przewidywanie})

    kandydaci = [s for s in sygn if s["wymiar"] not in POMIJANE_WYMIARY and s["klasa"] != "odniesienie"]
    mocne = [s for s in kandydaci if s["klasa"] in ("lepiej", "gorzej") and (s["wymiar"], s["grupa"], "grupa_werdykt") not in otwarte]
    if (n_notek < MIN_NOTEK or not any(s["klasa"] in ("lepiej", "gorzej") for s in kandydaci)) and ("", "", "silne_sygnaly") not in otwarte:
        dodaj("polityka", "Nie zmieniac polityki redakcyjnej w tej epoce; zbierac dane.",
              ("Notek z pomiarem jest %d (potrzeba co najmniej %d), mediana wyswietlen %s: za malo, by oddzielic efekt formy od szumu." % (
                  n_notek, MIN_NOTEK, d.get("mediana_wysw"))) if n_notek < MIN_NOTEK else
              ("Zadna grupa nie ma jeszcze werdyktu „lepiej” ani „gorzej” (notek z pomiarem %d, mediana wyswietlen %s): rozroznienia, "
               "ktore widac, mieszcza sie w szumie." % (n_notek, d.get("mediana_wysw"))),
              {"notek_z_pomiarem": n_notek, "mediana_wysw": d.get("mediana_wysw"), "min_notek": MIN_NOTEK},
              {"typ": "silne_sygnaly", "wartosc_odniesienia": 1, "sprawdz_po": _termin(dzis),
               "opis": "po %d dniach co najmniej jedna grupa dostanie werdykt „lepiej” albo „gorzej”" % HORYZONT_DNI})
    sila = lambda s: -abs(math.log(s["stosunek"])) if isinstance(s.get("stosunek"), (int, float)) and s["stosunek"] > 0 else 0.0   # noqa: E731
    mocne.sort(key=lambda s: (sila(s), s["id"]))
    for s in mocne:
        if len(out) >= MAKS_PROPOZYCJI:
            break
        typ = RODZAJ_WYMIARU.get(s["wymiar"], "styl")
        lepiej = s["klasa"] == "lepiej"
        dodaj(typ, "%s udzial grupy „%s” (wymiar %s) — jako eksperyment z regula decyzji z gory (R2, nie teraz)." % (
            "Zwiekszyc" if lepiej else "Ograniczyc", s["grupa"], s["wymiar"]),
            "Przedzial 95%% stosunku do grupy odniesienia „%s” wyklucza 1: %s (n=%s, klastrow=%s)%s." % (
                s["odniesienie"], s["przedzial_95"], s["n"], s["klastrow"],
                "; werdykt z zastrzezeniem: grupy z roznych okresow" if s["ostroznie"] else ""),
            _dowod(s), _przew_werdykt(s, dzis, d.get("od")))

    def wykrywalny_ok(s: dict[str, Any]) -> bool:
        w = s.get("wykrywalny_efekt")
        return not isinstance(w, (int, float)) or round(s["przewaga"] - 1.0, 6) >= round(KAND_FRAKCJA_WYKRYWALNEGO * w, 6)

    slabi = [s for s in kandydaci if s["klasa"] in ("brak_dowodu", "za_malo") and isinstance(s["n"], int) and s["n"] >= KAND_MIN_N
             and isinstance(s["klastrow"], int) and s["klastrow"] >= KAND_MIN_KLASTROW
             and isinstance(s["przewaga"], (int, float)) and s["przewaga"] >= KAND_MIN_WZGL and wykrywalny_ok(s)
             and not (s["wymiar"] in ("dzien", "pora") and (okno is None or okno < OKNO_DLA_DNIA_I_PORY))
             and (s["wymiar"], s["grupa"], "grupa_nowe_notki") not in otwarte]
    slabi.sort(key=lambda x: (-x["przewaga"], x["id"]))
    for s in slabi:
        if len(out) >= MAKS_PROPOZYCJI:
            break
        typ = RODZAJ_WYMIARU.get(s["wymiar"], "styl")
        dodaj("research" if typ == "temat" else typ,
              "Sprawdzic, czy grupa „%s” (wymiar %s) naprawde idzie lepiej: %s." % (
                  s["grupa"], s["wymiar"], "przygotowac dossier i test tematu" if typ == "temat" else "zebrac wiecej notek do porownania"),
              "Przewaga %s nad grupa odniesienia „%s” (wzgl. tla %s wobec %s) przy n=%s (klastrow %s), ale %s: kandydat, nie wniosek." % (
                  s["przewaga"], s["odniesienie"], s["wzgl_tla"], s["wzgl_odn"], s["n"], s["klastrow"],
                  "przedzial obejmuje 1" if s["klasa"] == "brak_dowodu" else "bez przedzialu (za malo niezaleznych jednostek)"),
              _dowod(s), _przew_nowe(s, dzis, d.get("od")))
    obcieto = max(0, len(mocne) + len(slabi) - sum(1 for p in out if p["typ"] != "polityka"))
    if not out:
        # wszystkie mocne sygnaly i kandydaci maja jeszcze nierozliczone przewidywania (albo nie ma niczego do zaproponowania)
        dodaj("polityka", "Bez nowych propozycji w tym tygodniu; polityka bez zmian.",
              "Wszystkie grupy z sygnalem maja jeszcze nierozliczone przewidywania z wczesniejszych tygodni (notek z pomiarem %d)." % n_notek,
              {"notek_z_pomiarem": n_notek, "otwartych_przewidywan": len(otwarte)},
              {"typ": "brak", "opis": "bez nowego przewidywania: poprzednie czeka na rozliczenie"})
    return out[:MAKS_PROPOZYCJI], obcieto


def _obecna_grupa(d: dict[str, Any], wymiar: str, grupa: str) -> dict[str, Any] | None:
    g = (((d.get("wymiary") or {}).get(wymiar) or {}).get("grupy") or {}).get(grupa)
    return g if isinstance(g, dict) else None


def _nowe_wzgl(n0: Any, w0: Any, n1: Any, w1: Any) -> float | None:
    """Sredni (geometrycznie) wzgl. tla NOWYCH notek grupy: wzgl_tla(nowe) = exp((n1*ln w1 - n0*ln w0) / (n1 - n0)) — `co_dziala` liczy wzgl_tla jako
    exp(srednia logarytmow), wiec srednia jest wazona liczba notek. None, gdy nie da sie policzyc (brak nowych, zle liczby)."""
    try:
        n0, n1 = int(n0), int(n1)
        if n1 <= n0 or not (w0 > 0 and w1 > 0) or not (math.isfinite(w0) and math.isfinite(w1)):
            return None
        return math.exp((n1 * math.log(w1) - n0 * math.log(w0)) / (n1 - n0))
    except (TypeError, ValueError, OverflowError):
        return None


def _za_malo_nowych(p: dict[str, Any], g: dict[str, Any]) -> str | None:
    """Powod „bez rozstrzygniecia”, gdy od zapisu przybylo za malo notek lub niezaleznych jednostek (albo nie da sie tego policzyc); inaczej None."""
    try:
        nowych = int(g["n"]) - int(p["n_przy_zapisie"])
        klastrow = int(g["klastrow"]) - int(p["klastrow_przy_zapisie"])
    except (KeyError, TypeError, ValueError):
        return "brak liczb do policzenia przyrostu"
    if nowych < int(p.get("min_nowych") or MIN_NOWYCH):
        return "nowych notek: %d" % nowych
    if klastrow < int(p.get("min_nowych_klastrow") or MIN_NOWYCH_KLASTROW):
        return "nowych niezaleznych jednostek: %d" % klastrow
    return None


def rozlicz_przewidywanie(p: dict[str, Any], d: dict[str, Any]) -> tuple[str, Any]:
    """(wynik, wartosc aktualna): potwierdzone / chybione / bez_rozstrzygniecia (za malo NOWYCH danych — to tez uczciwa odpowiedz)."""
    typ = p.get("typ")
    if p.get("okno_od") and str(d.get("od")) != str(p["okno_od"]):
        return "bez_rozstrzygniecia", "inne okno raportu: %s" % d.get("od")      # zmiana okna raportu zmienia, co znaczy „nowe notki”
    if typ == "silne_sygnaly":
        ile = sum(1 for s in sygnaly(d) if s["wymiar"] not in POMIJANE_WYMIARY and s["klasa"] in ("lepiej", "gorzej"))
        return ("potwierdzone" if ile >= p["wartosc_odniesienia"] else "chybione"), ile
    if typ in ("grupa_werdykt", "grupa_nowe_notki"):
        g = _obecna_grupa(d, p["wymiar"], p["grupa"])
        if not g:
            return "bez_rozstrzygniecia", None
        ref = ((d.get("wymiary") or {}).get(p["wymiar"]) or {}).get("odniesienie")
        if ref != p.get("odniesienie"):
            return "bez_rozstrzygniecia", "inne odniesienie: %s" % ref      # zmiana grupy odniesienia uniewaznia porownanie
        powod = _za_malo_nowych(p, g)
        if powod:
            return "bez_rozstrzygniecia", powod
        if typ == "grupa_werdykt":
            klasa = _klasa(g, p["grupa"] == ref)
            if klasa == p["oczekiwana"]:
                return "potwierdzone", klasa
            # po przyroscie danych werdykt sie odwrocil albo przedzial przestal wykluczac 1: przewidywanie „nadal lepiej/gorzej” sie nie sprawdzilo
            return ("chybione" if klasa in ("lepiej", "gorzej", "brak_dowodu") else "bez_rozstrzygniecia"), klasa
        nowe = _nowe_wzgl(p.get("n_przy_zapisie"), p.get("wzgl_przy_zapisie"), g.get("n"), g.get("wzgl_tla"))
        if nowe is None:
            return "bez_rozstrzygniecia", None
        if p.get("wzgledem") == "odniesienie":
            r = _obecna_grupa(d, p["wymiar"], str(ref))
            nowe_r = _nowe_wzgl(p.get("odn_n_przy_zapisie"), p.get("odn_wzgl_przy_zapisie"), r.get("n"), r.get("wzgl_tla")) if r else None
            if nowe_r is None:
                return "bez_rozstrzygniecia", None
            nowe = nowe / nowe_r
        return ("potwierdzone" if nowe >= p["wartosc_odniesienia"] else "chybione"), round(nowe, 3)
    return "bez_rozstrzygniecia", None


def rozlicz(wpisy: list[dict[str, Any]], d: dict[str, Any], dzis: date) -> list[dict[str, Any]]:
    """Nowe linie „rozliczenie” dla propozycji, ktorych termin minal, a ktore nie byly jeszcze rozliczone."""
    rozliczone = {w.get("id_propozycji") for w in wpisy if w.get("rodzaj") == "rozliczenie"}
    out = []
    for e in wpisy:
        if e.get("rodzaj") != "epoka":
            continue
        for pr in e.get("propozycje") or []:
            p = pr.get("przewidywanie") or {}
            if pr.get("id") in rozliczone or not p.get("sprawdz_po") or str(p["sprawdz_po"]) > dzis.isoformat():
                continue
            rozliczone.add(pr.get("id"))
            wynik, akt = rozlicz_przewidywanie(p, d)
            out.append({"rodzaj": "rozliczenie", "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU,
                        "id_propozycji": pr.get("id"), "epoka_wpisu": e.get("tydzien"), "kiedy": dzis.isoformat(),
                        "wynik": wynik, "wartosc_aktualna": akt, "przewidywanie": p.get("opis"),
                        "epoka_redakcyjna": EPOKA_REDAKCYJNA})
    return out


def _otwarte(wpisy: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    """(wymiar, grupa, typ przewidywania) z propozycji, ktorych jeszcze nie rozliczono (dla „polityki” wymiar i grupa sa puste)."""
    rozliczone = {w.get("id_propozycji") for w in wpisy if w.get("rodzaj") == "rozliczenie"}
    out = set()
    for e in wpisy:
        if e.get("rodzaj") != "epoka":
            continue
        for pr in e.get("propozycje") or []:
            p = pr.get("przewidywanie") or {}
            if pr.get("id") not in rozliczone and p.get("sprawdz_po"):
                out.add((str(p.get("wymiar") or ""), str(p.get("grupa") or ""), p.get("typ")))
    return out


def tekst(epoka: dict[str, Any] | None, rozliczenia: list[dict[str, Any]], ostatnie_rozliczenia: list[dict[str, Any]]) -> str:
    """Notatka redaktora dla czlowieka (cien: nic z tego nie jest wykonywane)."""
    if not epoka:
        return "# Notatka redaktora\n\nBrak raportu `co_dziala.json`; nic nie zapisano.\n"
    L = ["# Notatka redaktora (cien, tydzien %s)" % epoka["tydzien"], "",
         "To **zapis zamiarow, nie decyzje wykonane**: redaktor w cieniu niczego nie zmienia w tematach, stylu ani dlugosci. "
         "Epoka redakcyjna %d (polityka bez zmian)." % epoka["epoka_redakcyjna"], "",
         "## Co widze", "",
         "- Notek z pomiarem: %s, mediana wyswietlen: %s." % (epoka["n_notek"], epoka["mediana_wysw"]),
         "- Grupy w raporcie wg werdyktu: %s." % ", ".join("%s %d" % (k, v) for k, v in epoka["sygnaly"].items()),
         "- Trwajace eksperymenty (zmienne dla analizy): %s." % (", ".join(sorted(k for k, v in (epoka.get("eksperymenty") or {}).items() if v == "trwa")) or "brak"),
         "", "## Co bym postanowil", ""]
    for p in epoka["propozycje"]:
        L += ["- **%s** (%s): %s" % (p["id"], p["typ"], p["tresc"]), "  - dlaczego: %s" % p["uzasadnienie"],
              "  - przewiduje: %s%s" % (p["przewidywanie"]["opis"], (" (sprawdze po %s)" % p["przewidywanie"]["sprawdz_po"]) if p["przewidywanie"].get("sprawdz_po") else "")]
    if epoka.get("obcieto"):
        L.append("- (pominieto jeszcze %d propozycji z powodu limitu %d na tydzien)" % (epoka["obcieto"], MAKS_PROPOZYCJI))
    L += ["", "## Czy sie sprawdzilo", ""]
    wszystkie = rozliczenia + ostatnie_rozliczenia
    if not wszystkie:
        L.append("- Zadne wczesniejsze przewidywanie nie osiagnelo jeszcze terminu.")
    for r in wszystkie:
        L.append("- %s: **%s** (%s; wartosc teraz: %s)" % (r["id_propozycji"], r["wynik"].replace("_", " "), r["przewidywanie"], r["wartosc_aktualna"]))
    L += ["", "*Uczciwie: jesli nowych danych jest za malo, pisze „bez rozstrzygniecia” zamiast zgadywac.*", ""]
    return "\n".join(L)


def _dopisz(plik: Path, rekordy: list[dict[str, Any]]) -> None:
    plik.parent.mkdir(parents=True, exist_ok=True)
    koniec_ok = True
    try:
        with open(plik, "rb") as f:
            f.seek(0, 2)
            if f.tell():
                f.seek(-1, 2)
                koniec_ok = f.read(1) == b"\n"
    except OSError:
        pass
    with open(plik, "a", encoding="utf-8") as f:
        if not koniec_ok:
            f.write("\n")
        for r in rekordy:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def zapisz(*, dzis: date | None = None, katalog: Path | str | None = None) -> Path | None:
    """Jeden przebieg: rozlicz zapadle przewidywania, a jesli tego tygodnia nie ma jeszcze epoki, zapisz ja. Zwraca sciezke notatki
    albo None (wylaczone, brak lub stary raport, plik za duzy; powod idzie do logu). Wyjatki zostawia wywolujacemu (hak w `obserwatorium` je lapie)."""
    if not getattr(config, "REDAKTOR_CIEN", False):
        print("  [redaktor] pominiety: flaga REDAKTOR_CIEN wylaczona", flush=True)
        return None
    kat = _kat(katalog)
    d = wczytaj_raport(kat)
    if d is None:
        print("  [redaktor] pominiety: brak lub uszkodzony obserwatorium/co_dziala.json", flush=True)
        return None
    dzis = dzis or datetime.now(timezone.utc).date()
    if str(d.get("dzis") or "") < (dzis - timedelta(days=1)).isoformat():
        print("  [redaktor] pominiety: raport nieswiezy (dzis w raporcie %s, a jest %s) — co_dziala nie policzylo sie dzisiaj" % (
            d.get("dzis"), dzis.isoformat()), flush=True)
        return None
    plik = kat / PLIK
    try:
        if plik.stat().st_size > MAKS_BAJTOW:
            print("  [redaktor] pominiety: plik %s przekroczyl %d MB" % (PLIK, MAKS_BAJTOW // 1048576), flush=True)
            return None
    except OSError:
        pass
    wpisy = _jsonl(plik)
    nowe = rozlicz(wpisy, d, dzis)
    tydzien = _tydzien(dzis)
    epoka = next((w for w in wpisy if w.get("rodzaj") == "epoka" and w.get("tydzien") == tydzien), None)
    if epoka is None:
        sygn = sygnaly(d)
        prop, obcieto = propozycje(d, sygn, dzis, tydzien, _otwarte(wpisy + nowe))
        epoka = {"rodzaj": "epoka", "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU, "code_commit": _kod(),
                 "tydzien": tydzien, "dzis": dzis.isoformat(), "raport_dzis": d.get("dzis"), "epoka_redakcyjna": EPOKA_REDAKCYJNA,
                 "polityka": "bez_zmian (cien)", "okno_od": d.get("od"), "n_notek": int(d.get("notek_z_pomiarem") or 0),
                 "mediana_wysw": d.get("mediana_wysw"), "sygnaly": _liczniki(sygn),
                 "eksperymenty": {k: (v or {}).get("status") for k, v in (d.get("eksperymenty") or {}).items() if isinstance(v, dict)},
                 "propozycje": prop, "obcieto": obcieto, "status": "ok"}
        nowe = nowe + [epoka]
    if nowe:
        _dopisz(plik, nowe)
    ostatnie = [w for w in (wpisy + nowe) if w.get("rodzaj") == "rozliczenie"][-5:]
    nowe_rozl = [w for w in nowe if w.get("rodzaj") == "rozliczenie"]
    sciezka = kat / "obserwatorium" / RAPORT
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tekst(epoka, nowe_rozl, [r for r in ostatnie if r not in nowe_rozl]), encoding="utf-8")
    return sciezka
