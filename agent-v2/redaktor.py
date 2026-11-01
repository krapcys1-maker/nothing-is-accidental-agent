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
propozycje (zwiekszyc / ograniczyc udzial grupy jako EKSPERYMENT), ze slabych — „kandydatow do sprawdzenia", a gdy danych jest za malo, pisze
to wprost: „nie zmieniac polityki, zbierac dane". (3) Do kazdej propozycji dopisuje przewidywanie, ktore da sie sprawdzic z tego samego raportu
po terminie, i rozlicza stare (potwierdzone / chybione / bez rozstrzygniecia — to ostatnie, gdy danych dalej za malo). (4) Pisze notatke redaktora
dla czlowieka: `obserwatorium/redaktor.md`.

CZEGO NIE ROBI. Bez modelu, bez sieci. Zapisuje WYLACZNIE liczby zbiorcze i nazwy grup (kategorie, formaty): zadnych tekstow notek, zadnych
uchwytow ani danych czytelnikow (raporty R maja dane czytelnikow, wiec w dzienniku maja byc tylko liczby zbiorcze — P-013 pkt 5). Nie zapisuje
nic, jesli nie ma raportu. Nie zmienia `co_dziala.py` ani niczego, co bot czyta przy pisaniu.

EPOKA REDAKCYJNA. Kazdy rekord ma `epoka_redakcyjna`; zmiana POLITYKI (R2 i dalej) podnosi numer, zeby analiza pamieci mogla stratyfikowac po epoce
(P-013 pkt 4). Dopoki polityka sie nie zmienia (cien), numer to `EPOKA_REDAKCYJNA = 0`.
"""
from __future__ import annotations

import hashlib
import json
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
MIN_W_GRUPIE_DO_ROZLICZENIA = 3   # jak `co_dziala.MIN_W_GRUPIE`
# Kandydat do sprawdzenia (grupa BEZ przedzialu ufnosci) musi miec dosc notek, niezaleznych jednostek i wyrazna przewage, zeby nie gonic
# za szumem: na zywym raporcie z 1.11 (12 notek, mediana 11 wyswietlen) grupy po 3 notki z przewaga 1,02-1,54 byly samym szumem.
KAND_MIN_N = 4
KAND_MIN_KLASTROW = 3
KAND_MIN_WZGL = 1.15
MAKS_BAJTOW = 10 * 1024 * 1024

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


def _id(*czesci: Any) -> str:
    return hashlib.sha256("|".join(str(c) for c in czesci).encode("utf-8")).hexdigest()[:10]


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
    """Plaska lista grup ze wszystkich wymiarow: {id, wymiar, grupa, klasa, n, klastrow, wzgl_tla, stosunek, przedzial_95}."""
    out = []
    for wymiar, tab in (d.get("wymiary") or {}).items():
        if not isinstance(tab, dict):
            continue
        ref = tab.get("odniesienie")
        for nazwa, g in (tab.get("grupy") or {}).items():
            if not isinstance(g, dict):
                continue
            out.append({
                "id": "%s|%s" % (wymiar, nazwa), "wymiar": wymiar, "grupa": str(nazwa),
                "klasa": _klasa(g, nazwa == ref), "n": g.get("n"), "klastrow": g.get("klastrow"),
                "wzgl_tla": g.get("wzgl_tla"), "stosunek": g.get("stosunek"), "przedzial_95": g.get("przedzial_95"),
                "za_malo": bool(g.get("za_malo"))})
    return out


def _liczniki(sygn: list[dict[str, Any]]) -> dict[str, int]:
    out = {"lepiej": 0, "gorzej": 0, "brak_dowodu": 0, "za_malo": 0, "odniesienie": 0}
    for s in sygn:
        out[s["klasa"]] += 1
    return out


def _przewidywanie_grupy(s: dict[str, Any], kierunek: str, dzis: date) -> dict[str, Any]:
    return {"typ": "grupa_wzgl_tla", "wymiar": s["wymiar"], "grupa": s["grupa"], "kierunek": kierunek,
            "wartosc_odniesienia": 1.0, "n_przy_zapisie": s["n"],
            "sprawdz_po": (dzis + timedelta(days=HORYZONT_DNI)).isoformat(),
            "opis": "po %d dniach wzglednie do tla grupa %s/%s bedzie %s 1,0 (przy co najmniej %d notkach)" % (
                HORYZONT_DNI, s["wymiar"], s["grupa"], "powyzej" if kierunek == ">=" else "ponizej", MIN_W_GRUPIE_DO_ROZLICZENIA)}


def propozycje(d: dict[str, Any], sygn: list[dict[str, Any]], dzis: date, tydzien: str) -> list[dict[str, Any]]:
    """Do MAKS_PROPOZYCJI propozycji z dowodami i przewidywaniami; przy zbyt malej probie jedna: „nie zmieniac polityki”."""
    n_notek = int(d.get("notek_z_pomiarem") or 0)
    out: list[dict[str, Any]] = []

    def dodaj(typ: str, tresc: str, uzasadnienie: str, dowod: dict[str, Any], przewidywanie: dict[str, Any]) -> None:
        out.append({"id": "R-%s-%d" % (tydzien, len(out) + 1), "typ": typ, "tresc": tresc, "uzasadnienie": uzasadnienie,
                    "dowod": dowod, "przewidywanie": przewidywanie})

    silne = any(s["klasa"] in ("lepiej", "gorzej") for s in sygn)
    if n_notek < MIN_NOTEK or not silne:
        dodaj("polityka", "Nie zmieniac polityki redakcyjnej w tej epoce; zbierac dane.",
              ("Notek z pomiarem jest %d (potrzeba co najmniej %d), mediana wyswietlen %s: za malo, by oddzielic efekt formy od szumu." % (
                  n_notek, MIN_NOTEK, d.get("mediana_wysw"))) if n_notek < MIN_NOTEK else
              ("Zadna grupa nie ma jeszcze werdyktu „lepiej” ani „gorzej” (notek z pomiarem %d, mediana wyswietlen %s): rozroznienia, "
               "ktore widac, mieszcza sie w szumie." % (n_notek, d.get("mediana_wysw"))),
              {"notek_z_pomiarem": n_notek, "mediana_wysw": d.get("mediana_wysw"), "min_notek": MIN_NOTEK},
              {"typ": "liczba_notek", "wartosc_odniesienia": n_notek + 10,
               "sprawdz_po": (dzis + timedelta(days=HORYZONT_DNI)).isoformat(),
               "opis": "po %d dniach raport bedzie mial co najmniej %d notek z pomiarem" % (HORYZONT_DNI, n_notek + 10)})
    kandydaci = [s for s in sygn if s["wymiar"] not in POMIJANE_WYMIARY and s["klasa"] != "odniesienie"]
    for s in sorted((x for x in kandydaci if x["klasa"] in ("lepiej", "gorzej")), key=lambda x: x["id"]):
        typ = RODZAJ_WYMIARU.get(s["wymiar"], "styl")
        lepiej = s["klasa"] == "lepiej"
        dodaj(typ, "%s udzial grupy „%s” (wymiar %s) — jako eksperyment z regula decyzji z gory (R2, nie teraz)." % (
            "Zwiekszyc" if lepiej else "Ograniczyc", s["grupa"], s["wymiar"]),
            "Przedzial 95%% stosunku do odniesienia %s wyklucza 1 (n=%s, klastrow=%s, wzgl. tla %s)." % (
                s["przedzial_95"], s["n"], s["klastrow"], s["wzgl_tla"]),
            {k: s[k] for k in ("id", "n", "klastrow", "wzgl_tla", "stosunek", "przedzial_95")},
            _przewidywanie_grupy(s, ">=" if lepiej else "<=", dzis))
    slabi = [s for s in kandydaci if s["klasa"] in ("brak_dowodu", "za_malo") and isinstance(s["n"], int) and s["n"] >= KAND_MIN_N
             and isinstance(s["klastrow"], int) and s["klastrow"] >= KAND_MIN_KLASTROW
             and isinstance(s["wzgl_tla"], (int, float)) and s["wzgl_tla"] >= KAND_MIN_WZGL]
    slabi.sort(key=lambda x: (-x["wzgl_tla"], x["id"]))
    for s in slabi[:max(0, MAKS_PROPOZYCJI - len(out))]:
        typ = RODZAJ_WYMIARU.get(s["wymiar"], "styl")
        dodaj("research" if typ == "temat" else typ,
              "Sprawdzic, czy grupa „%s” (wymiar %s) naprawde idzie lepiej: %s." % (
                  s["grupa"], s["wymiar"], "przygotowac dossier i test tematu" if typ == "temat" else "zebrac wiecej notek do porownania"),
              "Wzgl. tla %s przy n=%s (klastrow %s), ale bez przedzialu: kandydat, nie wniosek." % (s["wzgl_tla"], s["n"], s["klastrow"]),
              {k: s[k] for k in ("id", "n", "klastrow", "wzgl_tla", "stosunek", "przedzial_95")},
              _przewidywanie_grupy(s, ">=", dzis))
    return out[:MAKS_PROPOZYCJI]


def _obecna_grupa(d: dict[str, Any], wymiar: str, grupa: str) -> dict[str, Any] | None:
    g = (((d.get("wymiary") or {}).get(wymiar) or {}).get("grupy") or {}).get(grupa)
    return g if isinstance(g, dict) else None


def rozlicz_przewidywanie(p: dict[str, Any], d: dict[str, Any]) -> tuple[str, Any]:
    """(wynik, wartosc aktualna): potwierdzone / chybione / bez_rozstrzygniecia (za malo danych — to tez uczciwa odpowiedz)."""
    typ = p.get("typ")
    if typ == "liczba_notek":
        akt = int(d.get("notek_z_pomiarem") or 0)
        return ("potwierdzone" if akt >= p["wartosc_odniesienia"] else "chybione"), akt
    if typ == "grupa_wzgl_tla":
        g = _obecna_grupa(d, p["wymiar"], p["grupa"])
        if not g or not isinstance(g.get("n"), int) or g["n"] < MIN_W_GRUPIE_DO_ROZLICZENIA or not isinstance(g.get("wzgl_tla"), (int, float)):
            return "bez_rozstrzygniecia", (g or {}).get("n")
        akt = g["wzgl_tla"]
        ok = akt >= p["wartosc_odniesienia"] if p.get("kierunek") == ">=" else akt <= p["wartosc_odniesienia"]
        return ("potwierdzone" if ok else "chybione"), akt
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
            wynik, akt = rozlicz_przewidywanie(p, d)
            out.append({"rodzaj": "rozliczenie", "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU,
                        "id_propozycji": pr.get("id"), "epoka_wpisu": e.get("tydzien"), "kiedy": dzis.isoformat(),
                        "wynik": wynik, "wartosc_aktualna": akt, "przewidywanie": p.get("opis"),
                        "epoka_redakcyjna": EPOKA_REDAKCYJNA})
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
         "- Grupy w raporcie wg werdyktu: %s." % ", ".join("%s %d" % (k, v) for k, v in epoka["sygnaly"].items()), "",
         "## Co bym postanowil", ""]
    for p in epoka["propozycje"]:
        L += ["- **%s** (%s): %s" % (p["id"], p["typ"], p["tresc"]), "  - dlaczego: %s" % p["uzasadnienie"],
              "  - przewiduje: %s (sprawdze po %s)" % (p["przewidywanie"]["opis"], p["przewidywanie"]["sprawdz_po"])]
    L += ["", "## Czy sie sprawdzilo", ""]
    wszystkie = rozliczenia + ostatnie_rozliczenia
    if not wszystkie:
        L.append("- Zadne wczesniejsze przewidywanie nie osiagnelo jeszcze terminu.")
    for r in wszystkie:
        L.append("- %s: **%s** (%s; wartosc teraz: %s)" % (r["id_propozycji"], r["wynik"].replace("_", " "), r["przewidywanie"], r["wartosc_aktualna"]))
    L += ["", "*Uczciwie: jesli danych jest za malo, pisze „bez rozstrzygniecia” zamiast zgadywac.*", ""]
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
    albo None (wylaczone, brak raportu, plik za duzy). Wyjatki zostawia wywolujacemu (hak w `obserwatorium` je lapie)."""
    if not getattr(config, "REDAKTOR_CIEN", False):
        return None
    kat = _kat(katalog)
    d = wczytaj_raport(kat)
    if d is None:
        return None
    dzis = dzis or datetime.now(timezone.utc).date()
    plik = kat / PLIK
    try:
        if plik.stat().st_size > MAKS_BAJTOW:
            return None
    except OSError:
        pass
    wpisy = _jsonl(plik)
    nowe = rozlicz(wpisy, d, dzis)
    tydzien = _tydzien(dzis)
    epoka = next((w for w in wpisy if w.get("rodzaj") == "epoka" and w.get("tydzien") == tydzien), None)
    if epoka is None:
        sygn = sygnaly(d)
        try:
            import stages
            kod = getattr(stages, "WERSJA_KODU", "") or ""
        except Exception:                   # noqa: BLE001
            kod = ""
        epoka = {"rodzaj": "epoka", "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU, "code_commit": kod,
                 "tydzien": tydzien, "dzis": dzis.isoformat(), "epoka_redakcyjna": EPOKA_REDAKCYJNA,
                 "polityka": "bez_zmian (cien)", "okno_od": d.get("od"), "n_notek": int(d.get("notek_z_pomiarem") or 0),
                 "mediana_wysw": d.get("mediana_wysw"), "sygnaly": _liczniki(sygn),
                 "propozycje": propozycje(d, sygn, dzis, tydzien), "status": "ok"}
        nowe = nowe + [epoka]
    if nowe:
        _dopisz(plik, nowe)
    ostatnie = [w for w in (wpisy + nowe) if w.get("rodzaj") == "rozliczenie"][-5:]
    nowe_rozl = [w for w in nowe if w.get("rodzaj") == "rozliczenie"]
    sciezka = kat / "obserwatorium" / RAPORT
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tekst(epoka, nowe_rozl, [r for r in ostatnie if r not in nowe_rozl]), encoding="utf-8")
    return sciezka
