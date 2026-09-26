"""Karta wynikow: te same liczby dla obu kont wlasciciela, tydzien po tygodniu.

SKAD. 26 wrzesnia 2026 wlasciciel ustalil: Nothing Is Accidental jest od dzis
POLIGONEM, a NIA glownym kontem produkcyjnym — tam zmian ma byc jak najmniej,
ale jak najbardziej trafnych. Poligon ma sens tylko wtedy, gdy oba konta mierzy
sie TAK SAMO; inaczej roznica miedzy nimi jest roznica przyrzadow, nie kont.
Pierwsze porownanie powstalo jednorazowym skryptem (raport
`docs/DWA_BOTY_POLE_DOSWIADCZALNE_2026-09-26.md`); to jest jego stala wersja.

CZEGO NIE ROBI. Nie woła modelu, nie otwiera przegladarki, bazy otwiera
w trybie tylko do odczytu. Jedyny zapis to `--zapisz`: jedna linia na konto
w `data/karta_wynikow.jsonl`, zeby tydzien dalo sie porownac z poprzednim.

DEFINICJE — jedne dla obu kont, kazda z powodem:
  * TYDZIEN to 7 pelnych dob UTC konczacych sie wczoraj. Dzisiejsza doba jest
    niepelna i zanizalaby kazdy licznik.
  * REAKCJE WLASNYCH KONT SIE NIE LICZA. Boty wlasciciela reagowaly na siebie
    nawzajem — 70% odpowiedzi na nasze komentarze pisala NIA — i zawyzaly
    odzew obu kont. Dotyczy odzewu i nowych reagujacych.
  * ZASIEG = mediana wyswietlen w pomiarze najblizszym 72 h od publikacji
    (±24 h), tylko wpisy, ktore zdazyly dojrzec. Notka zbiera zasieg przez
    trzy dni; wczesniejszy odczyt zawsze pokazuje spadek, ktorego nie ma.
  * ODZEW KOMENTARZA = jakakolwiek reakcja kogos spoza wlasnych kont, liczona
    na komentarzach starszych niz 48 h.
  * ZAPISY PRZYPISANE = `zapisy_per_notka` z `growth/sources`. Pole
    `subskrypcje` przy pozycji to okno doby, NIE przypisanie — tak powstal juz
    raz wniosek odwrocony o 180 stopni.
  * KOSZT = tylko przebiegi `tryb=produkcja`. Proby ida osobno.

Uruchamiac na serwerze, z katalogu repozytorium:
    .venv/bin/python agent-v2/karta_wynikow.py
    .venv/bin/python agent-v2/karta_wynikow.py --do 2026-10-03 --zapisz
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

def konta() -> tuple:
    """Konta wlasciciela: nazwa, katalog danych, uchwyt na Substacku.

    Liczone przy KAZDYM wywolaniu, nie przy imporcie: stala policzona
    z `config.DATA_DIR` przy imporcie nie rusza sie z
    `config.uzyj_katalogu_danych` (patrz `test_komplet_sciezek`). Katalog NIA
    lezy w jej instalacji na tym samym serwerze; inny da sie podac srodowiskiem.
    """
    return (
        ("Nothing Is Accidental", config.DATA_DIR, config.SUBSTACK_HANDLE),
        ("NIA", Path(os.environ.get(
            "KARTA_NIA_DANE",
            str(Path.home() / "nia-agent/agent-v2/instancje/nia-serwer"))), "nia1503032"),
    )


DOJRZALOSC_H = 72
TOLERANCJA_H = 24
ODZEW_PO_H = 48


def _czas(s) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _jsonl(sciezka: Path) -> list[dict]:
    if not sciezka.exists():
        return []
    out = []
    with sciezka.open(encoding="utf-8") as f:
        for linia in f:
            linia = linia.strip()
            if linia:
                try:
                    out.append(json.loads(linia))
                except ValueError:
                    pass
    return out


def _w_oknie(kiedy, od: date, do: date) -> bool:
    """Czy znacznik czasu wypada w dobach [od, do] wlacznie (UTC)."""
    return od.isoformat() <= str(kiedy)[:10] <= do.isoformat()


def wzrost(wpisy: list[dict], od: date, do: date) -> dict:
    """Stan konta na koniec okna i zmiana wobec konca doby przed oknem."""
    dzien: dict[str, dict] = {}
    for w in wpisy:
        dzien[str(w.get("kiedy"))[:10]] = w

    def stan(d: date) -> dict:
        klucze = [k for k in dzien if k <= d.isoformat()]
        return dzien[max(klucze)] if klucze else {}

    koniec, poczatek = stan(do), stan(od - timedelta(days=1))
    wynik = {"subskrybenci": koniec.get("subskrybenci"),
             "obserwujacy": koniec.get("obserwujacy")}
    for pole in ("subskrybenci", "obserwujacy"):
        if koniec.get(pole) is not None and poczatek.get(pole) is not None:
            wynik["przyrost_" + pole] = koniec[pole] - poczatek[pole]
    return wynik


def dzialania(dziennik: list[dict], od: date, do: date) -> dict:
    """Ile czego wyszlo naprawde (`udane`), bez zdarzen `skutek`."""
    c = Counter(e.get("rodzaj") for e in dziennik
                if e.get("udane") and e.get("rodzaj") != "skutek"
                and _w_oknie(e.get("kiedy"), od, do))
    return dict(c)


def _reagujacy(dziennik: list[dict], wlasne: set[str]) -> dict[str, set[str]]:
    """Numer naszej tresci -> uchwyty spoza wlasnych kont, ktore na nia zareagowaly."""
    kto: dict[str, set[str]] = defaultdict(set)
    for e in dziennik:
        if e.get("rodzaj") == "skutek":
            for u in e.get("uchwyty") or []:
                u = str(u).lower()
                if u not in wlasne:
                    kto[str(e.get("czego"))].add(u)
    return kto


def odzew_komentarzy(dziennik: list[dict], od: date, do: date,
                     wlasne: set[str]) -> dict:
    """Odsetek komentarzy z reakcja, na komentarzach starszych niz 48 h."""
    kto = _reagujacy(dziennik, wlasne)
    granica = datetime.combine(do + timedelta(days=1), datetime.min.time(),
                               tzinfo=timezone.utc) - timedelta(hours=ODZEW_PO_H)
    komentarze = [e for e in dziennik
                  if e.get("rodzaj") == "komentarz" and e.get("udane")
                  and e.get("nasz_id") and _w_oknie(e.get("kiedy"), od, do)
                  and (_czas(e.get("kiedy")) or granica) <= granica]
    z_odzewem = sum(1 for e in komentarze if kto.get(str(e["nasz_id"])))
    z_wyszukiwarki = sum(1 for e in komentarze
                         if str(e.get("skad") or "").startswith("szukanie"))
    stare_cele = sum(1 for e in komentarze
                     if (e.get("wiek_celu_min") or 0) > 30 * 24 * 60)
    n = len(komentarze)
    return {"komentarzy": n,
            "z_odzewem": z_odzewem,
            "odzew_proc": round(100 * z_odzewem / n) if n else None,
            "z_wyszukiwarki_proc": round(100 * z_wyszukiwarki / n) if n else None,
            "cele_starsze_niz_30_dni_proc": round(100 * stare_cele / n) if n else None}


def nowi_reagujacy(dziennik: list[dict], od: date, do: date,
                   wlasne: set[str]) -> int:
    """Ile uchwytow zareagowalo na nas PIERWSZY RAZ w historii konta w tym oknie.

    Rosnaca publicznosc, a nie ta sama para kont wracajaca co dzien.
    """
    pierwszy: dict[str, str] = {}
    for e in dziennik:
        if e.get("rodzaj") != "skutek":
            continue
        kiedy = str(e.get("kiedy_zdarzenia") or e.get("kiedy"))[:10]
        for u in e.get("uchwyty") or []:
            u = str(u).lower()
            if u not in wlasne and (u not in pierwszy or kiedy < pierwszy[u]):
                pierwszy[u] = kiedy
    return sum(1 for d in pierwszy.values() if od.isoformat() <= d <= do.isoformat())


def zasieg_72h(statystyki: list[dict], dziennik: list[dict], od: date,
               do: date) -> dict:
    """Mediana wyswietlen po 72 h dla notek i restackow opublikowanych w oknie
    przesunietym o trzy doby wstecz — tylko wpisy, ktore zdazyly dojrzec."""
    restacki = {str(e.get("id")) for e in dziennik
                if e.get("rodzaj") == "restack" and e.get("id")}
    przes_od, przes_do = od - timedelta(days=3), do - timedelta(days=3)
    pomiary: dict[tuple, list] = defaultdict(list)
    for s in statystyki:
        if "wyswietlenia" not in s or s.get("rodzaj") != "notka":
            continue
        wyst, zm = _czas(s.get("wystawione")), _czas(s.get("zmierzone"))
        if not wyst or not zm or not _w_oknie(s.get("wystawione"), przes_od, przes_do):
            continue
        rodzaj = "restack" if str(s.get("id")) in restacki else "notka"
        wiek = (zm - wyst).total_seconds() / 3600
        pomiary[(rodzaj, str(s.get("id")))].append((abs(wiek - DOJRZALOSC_H), s))
    wynik: dict = {}
    for rodzaj in ("notka", "restack"):
        dojrzale = [min(v, key=lambda x: x[0])[1] for (r, _), v in pomiary.items()
                    if r == rodzaj and min(x[0] for x in v) <= TOLERANCJA_H]
        widz = [s["wyswietlenia"] for s in dojrzale]
        odw = [s.get("odwiedziny_profilu")
               if s.get("odwiedziny_profilu") is not None
               else (s.get("interakcje") or {}).get("Profile visit", 0)
               for s in dojrzale]
        wynik[rodzaj] = {"n": len(widz),
                         "mediana": statistics.median(widz) if widz else None,
                         "odwiedziny_profilu_na_szt": (round(sum(odw) / len(odw), 2)
                                                       if odw else None)}
    return wynik


def zapisy(zrodla: list[dict], dziennik: list[dict]) -> dict:
    """Zapisy z ostatniego odczytu Substacka (okno 30 dni) i przypisania do
    naszych tresci — ze wszystkich odczytow, maksimum na tresc."""
    if not zrodla:
        return {}
    ostatni = zrodla[-1]
    razem = {m.get("name"): m.get("total")
             for m in (ostatni.get("zapisy") or {}).get("totals") or []}
    na_tresc: dict[str, int] = {}
    for z in zrodla:
        for k, v in ((z.get("podsumowanie") or {}).get("zapisy_per_notka") or {}).items():
            na_tresc[str(k)] = max(na_tresc.get(str(k), 0), v)
    rodzaj_po_id = {}
    for e in dziennik:
        for pole in ("id", "nasz_id"):
            if e.get(pole):
                rodzaj_po_id[str(e.get(pole))] = e.get("rodzaj")
    wg_rodzaju = Counter()
    for k, v in na_tresc.items():
        wg_rodzaju[rodzaj_po_id.get(k, "poza dziennikiem")] += v
    return {"zapisy_30_dni": razem.get("subscribers"),
            "przypisane_tresciom": dict(wg_rodzaju)}


def koszt(baza: Path, od: date, do: date) -> dict:
    """Koszt przebiegow produkcyjnych w oknie: razem, na dobe i trzy etapy."""
    if not baza.exists():
        return {}
    conn = sqlite3.connect(f"file:{baza}?mode=ro", uri=True)
    try:
        wiersze = conn.execute(
            "SELECT c.purpose, COALESCE(SUM(c.cost_usd), 0) FROM calls c "
            "JOIN runs r ON r.id = c.run_id "
            "WHERE r.tryb = ? AND substr(c.at, 1, 10) BETWEEN ? AND ? "
            "GROUP BY c.purpose ORDER BY 2 DESC",
            ("produkcja", od.isoformat(), do.isoformat())).fetchall()
        przebiegi = conn.execute(
            "SELECT status, COUNT(*) FROM runs WHERE tryb = ? "
            "AND substr(started_at, 1, 10) BETWEEN ? AND ? GROUP BY status",
            ("produkcja", od.isoformat(), do.isoformat())).fetchall()
    finally:
        conn.close()
    razem = sum(v for _, v in wiersze)
    dni = (do - od).days + 1
    return {"usd": round(razem, 2), "usd_na_dobe": round(razem / dni, 3),
            "etapy": [(e, round(v, 2)) for e, v in wiersze[:3]],
            "przebiegi": dict(przebiegi)}


def karta(nazwa: str, dane: Path, od: date, do: date, wlasne: set[str]) -> dict:
    dziennik = _jsonl(dane / "dziennik.jsonl")
    return {
        "konto": nazwa, "od": od.isoformat(), "do": do.isoformat(),
        "wzrost": wzrost(_jsonl(dane / "wzrost.jsonl"), od, do),
        "dzialania": dzialania(dziennik, od, do),
        "komentarze": odzew_komentarzy(dziennik, od, do, wlasne),
        "nowi_reagujacy": nowi_reagujacy(dziennik, od, do, wlasne),
        "zasieg_72h": zasieg_72h(_jsonl(dane / "statystyki.jsonl"), dziennik, od, do),
        "zapisy": zapisy(_jsonl(dane / "zrodla.jsonl"), dziennik),
        "koszt": koszt(dane / "agent-v2.db", od, do),
    }


def _wiersze(k: dict) -> list[tuple[str, str]]:
    w, d, kom, z = k["wzrost"], k["dzialania"], k["komentarze"], k["zasieg_72h"]
    ko, za = k["koszt"], k["zapisy"]

    def wart(v):
        return "—" if v is None else str(v)

    def zmiana(v):
        return "—" if v is None else f"{v:+d}"

    return [
        ("subskrybenci (zmiana)", f"{wart(w.get('subskrybenci'))} ({zmiana(w.get('przyrost_subskrybenci'))})"),
        ("obserwujacy (zmiana)", f"{wart(w.get('obserwujacy'))} ({zmiana(w.get('przyrost_obserwujacy'))})"),
        ("zapisy Substacka, 30 dni", wart(za.get("zapisy_30_dni"))),
        ("zapisy przypisane tresciom", ", ".join(f"{r} {n}" for r, n in
                                                 sorted((za.get("przypisane_tresciom") or {}).items(),
                                                        key=lambda x: -x[1])) or "—"),
        ("nowi reagujacy", str(k["nowi_reagujacy"])),
        ("notki / restacki / komentarze", f"{d.get('notka', 0)} / {d.get('restack', 0)} / {d.get('komentarz', 0)}"),
        ("odpowiedzi / artykuly", f"{d.get('odpowiedz', 0) + d.get('odpowiedz_pod_artykulem', 0)} / {d.get('artykul', 0)}"),
        ("odzew komentarzy po 48 h", f"{wart(kom.get('odzew_proc'))}% z {kom.get('komentarzy')}"),
        ("komentarze z wyszukiwarki", f"{wart(kom.get('z_wyszukiwarki_proc'))}%"),
        ("cele starsze niz 30 dni", f"{wart(kom.get('cele_starsze_niz_30_dni_proc'))}%"),
        ("notka: mediana 72 h (n)", f"{wart(z['notka']['mediana'])} ({z['notka']['n']})"),
        ("restack: mediana 72 h (n)", f"{wart(z['restack']['mediana'])} ({z['restack']['n']})"),
        ("odwiedziny profilu na notke", wart(z["notka"]["odwiedziny_profilu_na_szt"])),
        ("koszt USD (na dobe)", f"{ko.get('usd', '—')} ({ko.get('usd_na_dobe', '—')})"),
        ("najdrozsze etapy", ", ".join(f"{e} {v}" for e, v in ko.get("etapy", [])) or "—"),
        ("przebiegi", ", ".join(f"{s} {n}" for s, n in sorted(ko.get("przebiegi", {}).items())) or "—"),
    ]


def main(argv=None, lista_kont=None) -> int:
    p = argparse.ArgumentParser(description="Karta wynikow obu kont — tylko odczyt.")
    p.add_argument("--do", help="ostatnia doba okna (RRRR-MM-DD); domyslnie wczoraj")
    p.add_argument("--dni", type=int, default=7)
    p.add_argument("--zapisz", action="store_true",
                   help="dopisz karte do data/karta_wynikow.jsonl")
    a = p.parse_args(argv)
    do = date.fromisoformat(a.do) if a.do else datetime.now(timezone.utc).date() - timedelta(days=1)
    od = do - timedelta(days=a.dni - 1)
    lista_kont = lista_kont or konta()
    wlasne = {h.lower() for _, _, h in lista_kont}
    karty = [karta(n, d, od, do, wlasne) for n, d, _ in lista_kont if d.exists()]
    print(f"KARTA WYNIKOW {od} .. {do} (doby UTC; reakcje wlasnych kont pominiete)")
    kolumny = [dict(_wiersze(k)) for k in karty]
    szer = max(len(n) for n, _ in _wiersze(karty[0])) if karty else 20
    kol = 44
    print(" " * szer + "  " + "".join(f"{k['konto'][:kol - 2]:>{kol}}" for k in karty))
    for nazwa, _ in _wiersze(karty[0]) if karty else []:
        print(f"{nazwa:<{szer}}  " + "".join(f"{k[nazwa][:kol - 1]:>{kol}}" for k in kolumny))
    if a.zapisz:
        cel = config.DATA_DIR / "karta_wynikow.jsonl"
        with cel.open("a", encoding="utf-8") as f:
            for k in karty:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
        print(f"zapisane: {cel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
