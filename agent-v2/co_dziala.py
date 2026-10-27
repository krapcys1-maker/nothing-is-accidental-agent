# -*- coding: utf-8 -*-
"""CO DZIALA — zestaw statystyk Nothing Is Accidental jako samodzielnego produktu (27.10.2026).

PO CO. Wlasciciel: NIE nie jest tylko poligonem dla drugiego bota, tylko wlasnym produktem, wiec ma miec PELEN
zestaw statystyk. `obserwatorium.py` mierzy konto (wzrost, lejek, koszt), `laboratorium.py` — tempo i dawke ->
skutek, `eksperymenty.py` — pojedyncze zmiany. Brakowalo odpowiedzi na pytanie, ktore zadaje redaktor naczelny
co tydzien: CO Z TEGO, CO PISZEMY, DZIALA? Ten raport odpowiada na nie z jednego dziennika notek i liczy to samo,
co karta wynikow i eksperymenty (te same pomiary po 72 h, to samo tlo tygodnia, ten sam bootstrap):

  1. FORMATY    — zwykla notka z banku, seria sledcza, rozkmina, MYSL, promocja artykulu, notka rozliczajaca:
                  zasieg po 72 h wzgledem tla, odbior (odwiedziny profilu + zapisy), zapisy przypisane.
  2. WYMIARY    — kat serii, kategoria historii, pozycja w serii, dlugosc, pora, dzien tygodnia, forma, typ,
                  model, styk, pytanie na koncu: ktora cecha notki idzie z wiekszym zasiegiem.
  3. NAJLEPSZE  — najczesciej czytane notki epoki, z formatem i katem.
  4. EKSPERYMENTY — przeplatane (po notkach) i E22 (po SERIACH — notki jednej serii nie sa niezalezne).
  5. KOSZT      — za temat, za notke i za 1000 wyswietlen wedlug formatu; gdzie ida pieniadze (grupy etapow).
  6. SPRAWDZENIE FAKTOW — jak czesto naprawia, zastrzega, nie dochodzi do skutku (pole `fc` w dzienniku).
  7. POTOK      — ile sledztw, ile serii wyszlo w calosci, ile notek wygaslo w kolejce.
  8. WZROST     — tempo subskrybentow i lejek konta (z obserwatorium).
  9. ZAKLADY    — ksiega zgadywan (`zaklady.py`): trafienia, przedzial, kalibracja.
 10. CZUJNIK    — przebicia „co klika teraz" (`co_klika.jsonl`).
 11. WNIOSKI    — co robic czesciej / rzadziej, a gdzie dowodow jeszcze brak i ile notek brakuje.

UCZCIWIE O MOCY. Konto ma kilka notek serii na tydzien, mediana notki to kilkanascie wyswietlen, a odchylenie
logarytmu wyswietlen wieksze niz 0,5. Raport nie ocenia na „czucie": grupa ponizej progu jest pokazana jako
„za malo danych", a werdykt „lepiej/gorzej" pada tylko, gdy przedzial 95% bootstrapu nie obejmuje 1
(`eksperymenty.porownaj`). Porownania z roznych okresow dostaja ostrzezenie. Sedziowie LLM zasiegu nie przewiduja
(pomiar 28.09) — dowodem jest zawsze konto.

CZEGO NIE ROBI. Bez modelu, bez sieci, tylko odczyt (baza `mode=ro`); jedyny zapis to `--zapisz`:
`obserwatorium/co_dziala.md` i `.json` oraz jedna linia na dobe w `co_dziala.jsonl`. Czyta wylacznie dane NIE
(`config.DATA_DIR`) — drugiego bota nie dotyka, wiec da sie go przeniesc do innego konta bez zmian.

Uruchomienie z korzenia repozytorium:
    python agent-v2/co_dziala.py                  # raport na ekran
    python agent-v2/co_dziala.py --od 2026-10-26  # inny poczatek epoki
    python agent-v2/co_dziala.py --zapisz         # i do plikow (robi to tez `obserwatorium.py zbierz --raport`)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import config
import eksperymenty as ek

EPOKA_OD = "2026-10-26"      # od tego dnia sledczy pisze serie obok banku (fala 1 i lekki tor)
TLO_OD = "2026-09-28"        # tlo tygodnia liczymy ze wszystkich notek od startu pomiaru 72 h
MIN_W_GRUPIE = 3             # mniejsze grupy tabel nazywa „za malo"
MIN_KLASTROW = 6             # ponizej tylu NIEZALEZNYCH jednostek (serii, dob) w grupie nie ma werdyktu
MIN_SERII_NA_RAMIE = MIN_KLASTROW   # to samo dla eksperymentu po seriach (E22)
DOJRZALOSC_H = 72            # notka jest „dojrzala", gdy od publikacji minely trzy doby
LOSOWAN = ek.LOSOWAN
ZIARNO = ek.ZIARNO
PLIK_HISTORII = "co_dziala.jsonl"

FORMATY = ("zwykla", "seria", "rozkmina", "mysl", "promocja", "rozliczenie")
OPIS_FORMATOW = {
    "zwykla": "notka z banku faktow", "seria": "notka serii sledczej", "rozkmina": "notka rozkminy (przekroj historii)",
    "mysl": "MYSL (notka-przemyslenie obok serii)", "promocja": "notka promujaca artykul",
    "rozliczenie": "notka rozliczajaca zaklad"}

DLUGOSCI = (("do 50 slow", 0, 50), ("51-70 slow", 51, 70), ("71-90 slow", 71, 90), ("91-110 slow", 91, 110),
            ("ponad 110 slow", 111, 10 ** 6))
# Godziny CALKOWITE, wiec zakresy domkniete: 12:30 UTC to godzina 12, czyli kubelek 12-16 (nie 06-12).
PORY = (("00-06 UTC", 0, 5), ("06-12 UTC", 6, 11), ("12-16 UTC", 12, 15), ("16-20 UTC", 16, 19), ("20-24 UTC", 20, 23))
DNI_TYGODNIA = ("pon", "wt", "sr", "czw", "pt", "sob", "nd")

# Etapy z tabeli `calls.purpose` -> grupa kosztu (pierwsza pasujaca: nazwa dokladna albo przedrostek). Reszta to „inne" —
# raport pokazuje je jawnie, wiec nowy etap bez wpisu tutaj nie ginie, tylko widac go na liscie.
GRUPY_KOSZTU = (
    ("zaklady", (), ("zaklady",)),
    ("sledztwo i rozkmina", ("classify", "synthesis", "deepen", "nowosc", "przeslania", "przeslania_zapas", "notka_przeslania",
                             "notka_przeslania_fakt", "ksiega", "katy", "plan", "kategoria_historii", "wielkie_historie",
                             "pytania_ciekawosci", "dokumenty_lekkie", "seria_redakcja", "naglowek_naprawa", "ten_sam_punkt",
                             "wiernosc_notki"), ("seria_lekka", "rozkmina", "investigation")),
    ("sprawdzenie faktow i naprawa", ("factcheck", "naprawa", "naprawa_komentarza", "naprawa_artykulu"), ()),
    ("artykul (pisanie, recenzja, okladka)", ("write", "review", "obraz", "grafika", "warto_pisac", "wybor", "bibliotekarz"),
     ("article", "artykul")),
    ("komentarze, odpowiedzi, restacki", ("cele", "comment", "reply", "restack", "restack_opus"), ("odpowiedz", "komentarz")),
    ("notki z banku (szukanie, rozbior, pisanie)", ("curiosity", "discovery", "bank", "note", "note_mimo", "note_tani", "rozbior",
                                                      "wniosek", "forma", "radar", "glebia", "parowanie", "powtorka"), ()),
    ("rejestr modeli", ("aktualne_modele", "nowe_modele"), ()),
)


# --- wczytanie danych ----------------------------------------------------------------------------

def _jsonl(plik: Path) -> list[dict[str, Any]]:
    out = []
    try:
        with plik.open(encoding="utf-8") as f:
            for linia in f:
                if not linia.strip():
                    continue
                try:
                    w = json.loads(linia)
                except ValueError:
                    continue
                if isinstance(w, dict):
                    out.append(w)
    except OSError:
        pass
    return out


def _json(plik: Path, domyslnie: Any) -> Any:
    try:
        return json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return domyslnie


def zbierz_dane() -> dict[str, Any]:
    """Wszystko, czego raport potrzebuje, z plikow NIE (`config.DATA_DIR`). Tylko odczyt."""
    import statystyki
    kat = Path(config.DATA_DIR)
    return {"dziennik": _jsonl(kat / "dziennik.jsonl"),
            "pomiary": statystyki.po_godzinach("notka", 72).get("pozycje") or {},
            "zapisy": statystyki.zapisy_przypisane(),
            "sledztwa": _jsonl(kat / "sledztwa.jsonl"),
            "kolejka": _json(kat / "przeslania.json", []),
            "co_klika": _jsonl(kat / "co_klika.jsonl"),
            "koszty": koszty_z_bazy(kat / "agent-v2.db"),
            "dni": _wczytaj_dni()}


def _wczytaj_dni() -> dict[str, dict]:
    """Doby konta NIE policzone przez obserwatorium (`zbierz`); brak pliku = pusto."""
    try:
        import obserwatorium
        return obserwatorium.wczytaj_dni("NIE")
    except Exception:   # noqa: BLE001
        return {}


def koszty_z_bazy(baza: Path) -> dict[str, Any]:
    """Koszt wywolan z `calls` (produkcja): {'run': {run_id: usd}, 'purpose': [(doba, purpose, usd)]}. Pusto, gdy brak bazy."""
    if not baza.exists():
        return {"run": {}, "purpose": []}
    try:
        conn = sqlite3.connect(Path(baza).resolve().as_uri() + "?mode=ro&immutable=1", uri=True)   # `as_uri`: dziala tez z dyskiem Windows
        try:
            run = {str(r): float(u) for r, u in conn.execute(
                "SELECT c.run_id, SUM(c.cost_usd) FROM calls c JOIN runs r ON r.id = c.run_id "
                "WHERE COALESCE(r.tryb, 'produkcja') = 'produkcja' AND c.run_id IS NOT NULL "
                "AND substr(c.purpose, 1, 8) != 'zaklady_' GROUP BY c.run_id")}
            purpose = [(str(d), str(p), float(u)) for d, p, u in conn.execute(
                "SELECT substr(c.at, 1, 10), c.purpose, SUM(c.cost_usd) FROM calls c LEFT JOIN runs r ON r.id = c.run_id "
                "WHERE COALESCE(r.tryb, 'produkcja') = 'produkcja' GROUP BY 1, 2")]
        finally:
            conn.close()
    except sqlite3.Error:
        return {"run": {}, "purpose": []}
    return {"run": run, "purpose": purpose}


# --- klasyfikacja notek ---------------------------------------------------------------------------

def _run_z_przeslania(e: dict[str, Any]) -> str:
    """Numer przebiegu sledztwa z `przeslanie_id`: „202610251853-499-3-power_shift" (od 25.10.2026) albo starszy
    „202610091321-394-motyw"; pusty, gdy to nie seria."""
    pid = str(e.get("przeslanie_id") or "")
    if pid.endswith("-rozliczenie"):
        return ""          # wpis ROZLICZENIE dzieli numer przebiegu ze sledztwem, w ktorym go dodano — to nie jest jego notka
    czesci = pid.split("-")
    return czesci[1] if len(czesci) >= 3 and czesci[1].isdigit() else ""


def format_notki(e: dict[str, Any], rozkminy: set[str]) -> str:
    """Format notki z wpisu dziennika. `przeslanie_id` wygrywa z `typ`: MYSL i promocje nie maja przeslania."""
    pid = str(e.get("przeslanie_id") or "")
    if pid.endswith("-rozliczenie"):
        return "rozliczenie"
    if pid:
        return "rozkmina" if _run_z_przeslania(e) in rozkminy else "seria"
    if str(e.get("typ") or "") == "MYSL":
        return "mysl"
    if str(e.get("typ") or "") == "ARTYKUL":
        return "promocja"
    return "zwykla"


def _slow(e: dict[str, Any]) -> int:
    s = e.get("slow")
    return int(s) if isinstance(s, int) and s > 0 else len(str(e.get("tekst") or "").split())


def _kubelek(x: int, kubelki: tuple) -> str:
    return next((nazwa for nazwa, od, do in kubelki if od <= x <= do), "?")


def _kiedy(e: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(e.get("kiedy") or ""))
    except ValueError:
        return None


def grupowania(rozkminy: set[str], kategorie: dict[str, str]) -> dict[str, tuple[str, Callable[[dict], str], Callable[[dict], bool]]]:
    """Wymiary tabel: {klucz: (tytul, funkcja wpis -> grupa, filtr wpisow)}. Filtr zaweza do notek, o ktorych wymiar mowi."""
    def seryjna(e):
        return format_notki(e, rozkminy) in ("seria", "rozkmina")

    def kat(e):
        k = ((e.get("kat_serii") or {}).get("rodzaj") if isinstance(e.get("kat_serii"), dict) else "") or \
            (str(e.get("przeslanie_id") or "").split("-")[-1].upper() if e.get("przeslanie_id") else "")
        return str(k or "brak")

    def pozycja(e):
        c = str(e.get("przeslanie_id") or "").split("-")
        return "nr %s" % c[2] if len(c) >= 4 and c[2].isdigit() else "brak"

    def pora(e):
        t = _kiedy(e)
        return _kubelek(t.hour, PORY) if t else "brak"

    def dzien(e):
        t = _kiedy(e)
        return DNI_TYGODNIA[t.weekday()] if t else "brak"

    return {
        "format": ("Format notki", lambda e: format_notki(e, rozkminy), lambda e: True),
        "kat": ("Kat serii (rodzaj notki w serii)", kat, seryjna),
        "kategoria": ("Kategoria historii (wybor sledztwa)", lambda e: kategorie.get(_run_z_przeslania(e)) or "brak",
                      lambda e: seryjna(e) and bool(kategorie.get(_run_z_przeslania(e)))),
        "pozycja": ("Pozycja w serii", pozycja, seryjna),
        "dlugosc": ("Dlugosc notki", lambda e: _kubelek(_slow(e), DLUGOSCI), lambda e: True),
        "pora": ("Pora publikacji (UTC)", pora, lambda e: True),
        "dzien": ("Dzien tygodnia", dzien, lambda e: True),
        "typ": ("Typ notki", lambda e: str(e.get("typ") or "brak"), lambda e: True),
        "forma": ("Forma notki", lambda e: str(e.get("forma") or "brak"), lambda e: bool(e.get("forma"))),
        "model": ("Model pisarza", lambda e: str(e.get("model") or "brak"), lambda e: bool(e.get("model"))),
        "styk": ("Styk faktu (bank)", lambda e: str(e.get("styk") or "brak"), lambda e: format_notki(e, rozkminy) == "zwykla"),
        "pytanie": ("Konczy sie pytaniem", lambda e: "tak" if e.get("konczy_pytaniem") else "nie",
                    lambda e: e.get("konczy_pytaniem") is not None),
    }


# --- wiersze i porownania -------------------------------------------------------------------------

def wiersze_epoki(dane: dict[str, Any], od: str, do: str = "") -> list[dict[str, Any]]:
    """Notki z pomiarem po 72 h od `od` z tlem policzonym na WSZYSTKICH notkach od `TLO_OD`.

    Wiersz = wiersz `eksperymenty.wiersze` + `id`, odwiedziny profilu, zapisy i `lr` (log wyswietlen minus tlo
    tygodnia). Notka bez wyswietlen po 72 h jest poza porownaniem (`eksperymenty.wiersze` ja pomija) — raport
    liczy ja osobno w `zero_wyswietlen`, zeby „nikt nie zajrzal" nie znikalo po cichu."""
    wszystkie = ek.wiersze(dane["dziennik"], dane["pomiary"], dane["zapisy"], od=min(od, TLO_OD), do=do)
    for x in wszystkie:
        ident = str(x["wpis"].get("id"))
        s = dane["pomiary"].get(ident) or {}
        inter = s.get("interakcje") or {}
        x["id"] = ident
        x["odw"] = int(s.get("odwiedziny_profilu") if s.get("odwiedziny_profilu") is not None
                       else inter.get("Profile visit", 0) or 0)
        x["zap"] = int(dane["zapisy"].get(ident, 0))
    ek.odejmij_tlo(wszystkie)
    return [x for x in wszystkie if x["dzien"] >= od]


def zero_wyswietlen(dane: dict[str, Any], od: str) -> int:
    """Notki epoki z dojrzalym pomiarem i zerem wyswietlen (poza porownaniem `eksperymenty.wiersze`)."""
    n = 0
    for e in dane["dziennik"]:
        if (e.get("rodzaj") == "notka" and e.get("udane") and e.get("id") and str(e.get("kiedy") or "")[:10] >= od):
            s = dane["pomiary"].get(str(e["id"]))
            if s is not None and not int(s.get("wyswietlenia") or 0):
                n += 1
    return n


def _mediana(v: list[float]) -> float | None:
    return round(statistics.median(v), 1) if v else None


def _klaster(x: dict[str, Any]) -> str:
    """Niezalezna jednostka notki: seria (cztery notki jednej historii nie sa niezalezne), a poza seria — doba publikacji
    (notki jednej doby dziela tlo i los eksperymentow losowanych na dobe, jak `pora_notki`)."""
    run = _run_z_przeslania(x["wpis"])
    return ("s" + run) if run else ("d" + str(x["dzien"]))


def _po_klastrach(rows: list[dict[str, Any]]) -> list[list[float]]:
    """Lista klastrow, kazdy jako lista `lr` jego notek."""
    k: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        k[_klaster(x)].append(x["lr"])
    return list(k.values())


def _sr(klastry: list[list[float]]) -> float:
    return sum(sum(k) for k in klastry) / sum(len(k) for k in klastry)


def ci_klastrow(a: list[list[float]], b: list[list[float]]) -> tuple[float, float, float]:
    """(stosunek, dolny, gorny) grupy `a` do `b`: bootstrap 95% po KLASTRACH (losujemy cale serie/doby z powtorzeniami,
    srednia liczona po notkach wylosowanych klastrow), to samo ziarno co `eksperymenty`. Notki jednej serii nie sa
    niezalezne, wiec bootstrap po notkach dawalby przedzial za waski i falszywe werdykty (test ma na to kontrdowod)."""
    rnd = random.Random(ZIARNO)
    losy = sorted(math.exp(_sr([rnd.choice(a) for _ in a]) - _sr([rnd.choice(b) for _ in b])) for _ in range(LOSOWAN))
    return (math.exp(_sr(a) - _sr(b)), losy[int(0.025 * LOSOWAN)], losy[int(0.975 * LOSOWAN) - 1])


def _wykrywalny(a: list[list[float]], b: list[list[float]], wszystkie: list[list[float]]) -> float | None:
    """Najmniejszy wykrywalny efekt (moc 80%, 5%) przy tej liczbie niezaleznych jednostek."""
    srednie = [sum(k) / len(k) for k in wszystkie]
    if len(srednie) < 2:
        return None
    sd = statistics.stdev(srednie)
    return math.exp(2.8 * sd * math.sqrt(1 / len(a) + 1 / len(b))) - 1 if sd else None


def tabela(rows: list[dict[str, Any]], grupa: Callable[[dict], str], odniesienie: str | None = None) -> dict[str, Any]:
    """`eksperymenty.porownaj` (opis grup, wybor odniesienia) + kolumny, ktorych tam nie ma, + WERDYKT z bootstrapu po
    niezaleznych jednostkach (`ci_klastrow`): `stosunek`, `przedzial_95`, `wykrywalny_efekt` i `werdykt` z `porownaj`
    sa nadpisane wersja po klastrach, a ostrzezenie „grupy z roznych okresow” zostaje."""
    if not rows:
        return {"grupy": {}, "odniesienie": None, "n": 0}
    w = ek.porownaj(rows, grupa, odniesienie)
    po_grupach: dict[str, list[dict]] = defaultdict(list)
    for x in rows:
        po_grupach[grupa(x["wpis"])].append(x)
    klastry = {nazwa: _po_klastrach(r) for nazwa, r in po_grupach.items()}
    wszystkie = _po_klastrach(rows)
    ref = w.get("odniesienie")
    for nazwa, g in w["grupy"].items():
        r = po_grupach[nazwa]
        g["mediana_wysw"] = _mediana([x["w"] for x in r])
        g["z_odwiedzinami"] = round(sum(1 for x in r if x["odw"] > 0) / len(r), 2)
        g["zapisy"] = sum(x["zap"] for x in r)
        g["odwiedziny"] = sum(x["odw"] for x in r)
        g["za_malo"] = len(r) < MIN_W_GRUPIE
        g["klastrow"] = len(klastry[nazwa])
        if nazwa == ref:
            continue
        a, b = klastry[nazwa], klastry[ref]
        ostrzezenie = " — OSTROZNIE: grupy z roznych okresow" if ek._rozne_okresy(r, po_grupach[ref]) else ""
        g["wykrywalny_efekt"] = (round(_wykrywalny(a, b, wszystkie), 2) if _wykrywalny(a, b, wszystkie) is not None else None)
        if len(a) < MIN_KLASTROW or len(b) < MIN_KLASTROW:
            g["przedzial_95"] = None
            g["werdykt"] = "za malo danych (%d i %d niezaleznych jednostek — serii lub dob; trzeba co najmniej %d)%s" % (
                len(a), len(b), MIN_KLASTROW, ostrzezenie)
            continue
        stosunek, lo, hi = ci_klastrow(a, b)
        g["stosunek"] = round(stosunek, 3)
        g["przedzial_95"] = (round(lo, 3), round(hi, 3))
        g["werdykt"] = ("lepiej" if lo > 1 else "gorzej" if hi < 1 else "brak dowodu roznicy (wykrylibysmy dopiero ok. %+d%%)" % round(
            100 * (g["wykrywalny_efekt"] or 0))) + ostrzezenie
    w["n"] = len(rows)
    return w


def porownanie_po_seriach(rows: list[dict[str, Any]], nazwa: str) -> dict[str, Any]:
    """Eksperyment, w ktorym ramie dostaje CALA SERIA (E22): notki jednej serii nie sa niezalezne, wiec bootstrap
    idzie po seriach — kazda seria to jedna liczba (srednia `lr` jej notek), a ramiona porownujemy po seriach."""
    serie: dict[str, dict[str, Any]] = {}
    for x in rows:
        ramie = (x["wpis"].get("eksperymenty") or {}).get(nazwa)
        run = _run_z_przeslania(x["wpis"])
        if ramie in ("on", "off") and run:
            s = serie.setdefault(run, {"ramie": ramie, "lr": [], "w": [], "slow": []})
            s["lr"].append(x["lr"])
            s["w"].append(x["w"])
            s["slow"].append(_slow(x["wpis"]))
    wynik: dict[str, Any] = {"nazwa": nazwa, "ramiona": {}}
    for ramie in ("on", "off"):
        r = [s for s in serie.values() if s["ramie"] == ramie]
        wynik["ramiona"][ramie] = {
            "serii": len(r), "notek": sum(len(s["lr"]) for s in r),
            "mediana_wysw": _mediana([w for s in r for w in s["w"]]),
            "mediana_slow": _mediana([sl for s in r for sl in s["slow"]]),
            "wzgl_tla": round(math.exp(statistics.mean(statistics.mean(s["lr"]) for s in r)), 2) if r else None}
    on = [s for s in serie.values() if s["ramie"] == "on"]
    off = [s for s in serie.values() if s["ramie"] == "off"]
    if len(on) < MIN_SERII_NA_RAMIE or len(off) < MIN_SERII_NA_RAMIE:
        wynik["werdykt"] = "za malo serii (%d i %d, trzeba co najmniej %d na ramie)" % (len(on), len(off), MIN_SERII_NA_RAMIE)
        wynik["stosunek"] = None
        return wynik
    stosunek, dolny, gorny = ci_klastrow([s["lr"] for s in serie.values() if s["ramie"] == "on"],
                                         [s["lr"] for s in serie.values() if s["ramie"] == "off"])
    wynik["stosunek"] = round(stosunek, 3)
    wynik["przedzial_95"] = (round(dolny, 3), round(gorny, 3))
    wynik["werdykt"] = "lepiej" if dolny > 1 else "gorzej" if gorny < 1 else "brak dowodu roznicy"
    return wynik


# --- koszt ----------------------------------------------------------------------------------------

def grupa_kosztu(purpose: str) -> str:
    for nazwa, dokladne, przedrostki in GRUPY_KOSZTU:
        if purpose in dokladne or any(purpose.startswith(p) for p in przedrostki):
            return nazwa
    return "inne"


def koszt_wg_grup(koszty: dict[str, Any], od: str, do: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for doba, purpose, usd in koszty.get("purpose") or []:
        if od <= doba <= do:
            out[grupa_kosztu(purpose)] += usd
    return {k: round(v, 3) for k, v in sorted(out.items(), key=lambda kv: -kv[1])}


def koszt_serii(dane: dict[str, Any], rows: list[dict[str, Any]], rozkminy: set[str], od: str,
                teraz: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Koszt tematu sledztwa i notki wedlug formatu (seria / rozkmina) oraz koszt na 1000 wyswietlen po 72 h.

    Koszt tematu = suma `calls` przebiegu sledztwa BEZ wywolan ksiegi zakladow (te dotycza starszych notek, a chodza pod
    numerem przebiegu sledztwa; patrz `koszty_z_bazy`). Dzielimy go przez liczbe notek, ktore z tej serii REALNIE wyszly.
    KOSZT NA 1000 WYSWIETLEN liczymy tylko z serii DOJRZALYCH (wszystkie wydane notki maja 72 h): inaczej koszt serii,
    ktorej notki jeszcze zbieraja zasieg, dzielilby sie przez czesc wyswietlen i zawyzal wynik."""
    teraz = teraz or datetime.now(timezone.utc)
    granica = teraz - timedelta(hours=DOJRZALOSC_H)
    wydane: dict[str, int] = defaultdict(int)
    mlode: set[str] = set()
    for e in dane["dziennik"]:
        if e.get("rodzaj") == "notka" and e.get("udane") and str(e.get("kiedy") or "")[:10] >= od and _run_z_przeslania(e):
            run = _run_z_przeslania(e)
            wydane[run] += 1
            t = _kiedy(e)
            if t is None or t > granica:
                mlode.add(run)
    wysw: dict[str, int] = defaultdict(int)
    for x in rows:
        if _run_z_przeslania(x["wpis"]):
            wysw[_run_z_przeslania(x["wpis"])] += x["w"]
    out: dict[str, dict[str, Any]] = {}
    for fmt in ("seria", "rozkmina"):
        runy = [r for r in wydane if (r in rozkminy) == (fmt == "rozkmina") and str(r) in dane["koszty"].get("run", {})]
        if not runy:
            continue
        usd = [dane["koszty"]["run"][r] for r in runy]
        notek = sum(wydane[r] for r in runy)
        dojrzale = [r for r in runy if r not in mlode]
        usd_d = sum(dane["koszty"]["run"][r] for r in dojrzale)
        w = sum(wysw[r] for r in dojrzale)
        out[fmt] = {"tematow": len(runy), "koszt_tematu_mediana": round(statistics.median(usd), 3), "koszt_razem": round(sum(usd), 3),
                    "notek_wydanych": notek, "koszt_notki": round(sum(usd) / notek, 4) if notek else None,
                    "tematow_dojrzalych": len(dojrzale), "wysw_72h": w,
                    "koszt_na_1000_wysw": round(1000 * usd_d / w, 2) if w else None}
    return out


# --- sprawdzenie faktow, potok, czujnik -----------------------------------------------------------------

def sprawdzenie_faktow(dane: dict[str, Any], rozkminy: set[str], od: str) -> dict[str, Any]:
    """Pole `fc` (od 27.10.2026): ile notek mialo obalone twierdzenie, ile naprawiono, ile zastrzezen, ile bez sprawdzenia."""
    wg: dict[str, list[dict]] = defaultdict(list)
    bez = 0
    for e in dane["dziennik"]:
        if e.get("rodzaj") != "notka" or not e.get("udane") or str(e.get("kiedy") or "")[:10] < od:
            continue
        if isinstance(e.get("fc"), dict) and e["fc"]:
            wg[format_notki(e, rozkminy)].append(e["fc"])
        else:
            bez += 1
    out = {"bez_pola": bez, "formaty": {}}
    for fmt, lista in wg.items():
        n = len(lista)
        out["formaty"][fmt] = {
            "n": n, "z_obalonym": sum(1 for f in lista if f.get("obalonych")), "naprawionych": sum(1 for f in lista if f.get("naprawiona")),
            "z_zastrzezeniem": sum(1 for f in lista if f.get("zastrzezenia")),
            "nie_sprawdzonych": sum(1 for f in lista if f.get("nie_sprawdzone")),
            "twierdzen_na_notke": round(sum(int(f.get("twierdzen") or 0) for f in lista) / n, 1)}
    return out


def potok(dane: dict[str, Any], rozkminy: set[str], od: str, teraz: datetime) -> dict[str, Any]:
    """Ile sledztw, ile notek z nich powstalo, wyszlo i wygaslo w kolejce; ile dni od sledztwa do pierwszej notki."""
    rekordy = [r for r in dane["sledztwa"] if r.get("przeslania") and str(r.get("kiedy") or "")[:10] >= od]
    wydane: dict[str, list[datetime]] = defaultdict(list)
    for e in dane["dziennik"]:
        if e.get("rodzaj") == "notka" and e.get("udane") and _run_z_przeslania(e):
            t = _kiedy(e)
            if t:
                wydane[_run_z_przeslania(e)].append(t)
    kolejka = [p for p in dane["kolejka"] if isinstance(p, dict)]
    iso = teraz.isoformat()
    opublikowane = {str(e.get("przeslanie_id")) for e in dane["dziennik"] if e.get("przeslanie_id") and e.get("udane")}
    # ROZLACZNE trzy stany nieopublikowanego wpisu, jak `sledztwo._do_wydania`: pominiety (flaga albo po `MAKS_PROB`
    # nieudanych probach), wygasly (termin minal) i czekajacy (reszta).
    try:
        import sledztwo
        maks_prob = sledztwo.MAKS_PROB
    except Exception:   # noqa: BLE001
        maks_prob = 2
    czeka = wygaslo = pominiete = 0
    for p in kolejka:
        if str(p.get("id")) in opublikowane:
            continue
        if p.get("pominiety") or int(p.get("proby") or 0) >= maks_prob:
            pominiete += 1
        elif str(p.get("wazny_do") or "") < iso:
            wygaslo += 1
        else:
            czeka += 1
    opoznienia = []
    for r in rekordy:
        try:
            start = datetime.fromisoformat(str(r["kiedy"]))
        except ValueError:
            continue
        pierwsze = min(wydane.get(str(r.get("run_id")), []), default=None)
        if pierwsze:
            opoznienia.append((pierwsze - start).total_seconds() / 86400)
    wyprodukowane = sum(len(r["przeslania"]) if isinstance(r.get("przeslania"), list) else 0 for r in rekordy)
    wyszlo = sum(len(wydane.get(str(r.get("run_id")), [])) for r in rekordy)
    return {"sledztw": len(rekordy), "w_tym_rozkmin": sum(1 for r in rekordy if str(r.get("run_id")) in rozkminy),
            "notek_wyprodukowanych": wyprodukowane, "notek_wyszlo": wyszlo,
            "kolejka_czeka": czeka, "kolejka_wygaslo": wygaslo, "kolejka_pominietych": pominiete,
            "dni_do_pierwszej_notki_mediana": round(statistics.median(opoznienia), 1) if opoznienia else None}


def czujnik(dane: dict[str, Any], teraz: datetime) -> dict[str, Any]:
    wpisy = dane.get("co_klika") or []
    granica7 = (teraz - timedelta(days=7)).isoformat()
    granica28 = (teraz - timedelta(days=28)).isoformat()
    top = sorted(wpisy, key=lambda w: -float(w.get("przebicie") or 0))[:5]
    return {"wszystkich": len(wpisy), "ostatnie_7": sum(1 for w in wpisy if str(w.get("wykryto") or "") >= granica7),
            "ostatnie_28": sum(1 for w in wpisy if str(w.get("wykryto") or "") >= granica28),
            "publikacji": len({str(w.get("kanal")) for w in wpisy}),
            "top": [{"temat": str(w.get("temat"))[:90], "kanal": w.get("kanal"), "przebicie": w.get("przebicie"),
                     "reakcje": w.get("reakcje"), "data": w.get("data")} for w in top]}


def wzrost(dane: dict[str, Any], dzis: date) -> dict[str, Any]:
    """Tempo i lejek konta z obserwatorium (`dni_NIE.json`); brak pliku = puste."""
    dni = dane.get("dni") or {}
    if not dni:
        return {}
    try:
        import obserwatorium
        wczoraj = (dzis - timedelta(days=1)).isoformat()
        return {"7": obserwatorium.tempo(dni, wczoraj, 7), "28": obserwatorium.tempo(dni, wczoraj, 28)}
    except Exception:   # noqa: BLE001
        return {}


# --- caly raport -------------------------------------------------------------------------------------

def policz(dane: dict[str, Any] | None = None, od: str = EPOKA_OD, dzis: date | None = None) -> dict[str, Any]:
    dane = dane if dane is not None else zbierz_dane()
    dzis = dzis or datetime.now(timezone.utc).date()
    # „Teraz" do porownan z terminami kolejki i dojrzaloscia notek: prawdziwa chwila, gdy raport jest z dzisiaj
    # (zegar obserwatorium 03:40 UTC), a koniec doby, gdy ktos prosi o inny dzien (testy, odtworzenie).
    teraz = (datetime.now(timezone.utc) if dzis == datetime.now(timezone.utc).date()
             else datetime.combine(dzis, datetime.max.time(), tzinfo=timezone.utc))
    rozkminy = {str(r.get("run_id")) for r in dane["sledztwa"] if r.get("rozkmina")}
    kategorie = {str(r.get("run_id")): str(r.get("kategoria")) for r in dane["sledztwa"] if r.get("kategoria")}
    rows = wiersze_epoki(dane, od)
    w: dict[str, Any] = {"dzis": dzis.isoformat(), "od": od, "notek_z_pomiarem": len(rows),
                         "zero_wyswietlen": zero_wyswietlen(dane, od),
                         "notek_wydanych": sum(1 for e in dane["dziennik"] if e.get("rodzaj") == "notka" and e.get("udane")
                                               and str(e.get("kiedy") or "")[:10] >= od),
                         "mediana_wysw": _mediana([x["w"] for x in rows]),
                         "sd_log": round(ek._sd_log(rows), 3) if len(rows) > 1 else None}
    gr = grupowania(rozkminy, kategorie)
    w["formaty"] = tabela(rows, gr["format"][1], "zwykla")
    w["wymiary"] = {}
    for klucz, (tytul, fn, filtr) in gr.items():
        if klucz == "format":
            continue
        podzbior = [x for x in rows if filtr(x["wpis"])]
        w["wymiary"][klucz] = dict(tabela(podzbior, fn), tytul=tytul)
    w["najlepsze"] = [{"id": x["id"], "wysw": x["w"], "odw": x["odw"], "zapisy": x["zap"],
                       "format": format_notki(x["wpis"], rozkminy), "kat": gr["kat"][1](x["wpis"]),
                       "slow": _slow(x["wpis"]), "poczatek": " ".join(str(x["wpis"].get("tekst") or "").split())[:110]}
                      for x in sorted(rows, key=lambda x: -x["w"])[:8]]
    aktywne = {}
    for nazwa, ust in (config.EKSPERYMENTY or {}).items():
        if not isinstance(ust, dict):
            continue
        status = ("zaplanowany" if ust.get("od") and od_dzis(ust["od"]) > dzis
                  else "zakonczony" if ust.get("do") and od_dzis(ust["do"]) < dzis else "trwa")
        wpis = {"status": status, "od": ust.get("od"), "do": ust.get("do"), "udzial": ust.get("udzial")}
        arm_rows = [x for x in rows if (x["wpis"].get("eksperymenty") or {}).get(nazwa) in ("on", "off")]
        wpis["notek_w_ramionach"] = len(arm_rows)
        if nazwa == "dlugosc_serii":
            wpis["po_seriach"] = porownanie_po_seriach(rows, nazwa)
        elif len(arm_rows) >= 2 * MIN_W_GRUPIE:
            wpis["tabela"] = tabela(arm_rows, ek._grupujacy("eksperyment:" + nazwa), "off")
        aktywne[nazwa] = wpis
    w["eksperymenty"] = aktywne
    w["koszt_serii"] = koszt_serii(dane, rows, rozkminy, od, teraz)
    # PELNE DOBY DO WCZORAJ (jak okna `obserwatorium.tempo`): dzisiejsza doba jest niepelna i zanizalaby tempo.
    w["koszt_grup_7"] = koszt_wg_grup(dane["koszty"], (dzis - timedelta(days=7)).isoformat(), (dzis - timedelta(days=1)).isoformat())
    w["koszt_grup_28"] = koszt_wg_grup(dane["koszty"], (dzis - timedelta(days=28)).isoformat(), (dzis - timedelta(days=1)).isoformat())
    w["fc"] = sprawdzenie_faktow(dane, rozkminy, od)
    w["potok"] = potok(dane, rozkminy, od, teraz)
    w["wzrost"] = wzrost(dane, dzis)
    w["czujnik"] = czujnik(dane, teraz)
    w["zaklady"] = _zaklady()
    w["wnioski"] = wnioski(w)
    return w


def od_dzis(s: Any) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return date.max


def _zaklady() -> dict[str, Any]:
    try:
        import zaklady
        return zaklady.statystyki()
    except Exception:   # noqa: BLE001
        return {}


def wnioski(w: dict[str, Any]) -> list[str]:
    """Wnioski z liczb, bez zgadywania: co jest dowiedzione, czego brakuje i ile notek potrzeba."""
    out = []
    formaty = (w.get("formaty") or {}).get("grupy") or {}
    odn = (w.get("formaty") or {}).get("odniesienie")
    for nazwa, g in formaty.items():
        if nazwa == odn:
            continue
        ostrzez = "OSTROZNIE: grupy z roznych okresow" in g.get("werdykt", "")
        przedrostek = "WSKAZANIE (nie dowod — grupy z roznych okresow): " if ostrzez else ""
        if g.get("werdykt", "").startswith("lepiej"):
            out.append("%s%s: %s bije zwykla notke (x%.2f wzgledem tla, przedzial %s, %d i %d niezaleznych jednostek)." % (
                przedrostek, "PISAC CZESCIEJ" if not ostrzez else "wiecej", nazwa, g["stosunek"], g["przedzial_95"], g["klastrow"],
                formaty[odn]["klastrow"]))
        elif g.get("werdykt", "").startswith("gorzej"):
            out.append("%s%s: %s przegrywa ze zwykla notka (x%.2f, przedzial %s, %d i %d niezaleznych jednostek)." % (
                przedrostek, "PISAC RZADZIEJ" if not ostrzez else "mniej", nazwa, g["stosunek"], g["przedzial_95"], g["klastrow"],
                formaty[odn]["klastrow"]))
        elif g.get("werdykt", "").startswith("za malo"):
            out.append("BRAK DOWODU: %s ma %d notek z pomiarem i %d niezaleznych jednostek (trzeba co najmniej %d w grupie i w "
                       "odniesieniu)." % (nazwa, g["n"], g["klastrow"], MIN_KLASTROW))
        else:
            out.append("BRAK DOWODU: %s nie odroznia sie od zwyklej notki — %s." % (nazwa, g.get("werdykt")))
    e22 = ((w.get("eksperymenty") or {}).get("dlugosc_serii") or {}).get("po_seriach") or {}
    if e22.get("werdykt") in ("lepiej", "gorzej"):
        out.append("DLUGOSC SERII (E22): krotsze notki (30-60 slow) wypadaja %s niz domyslne 50-110 (x%.2f, przedzial %s)." % (
            e22["werdykt"], e22["stosunek"], e22["przedzial_95"]))
    z = w.get("zaklady") or {}
    if z.get("rozstrzygnietych") is not None and 0 < z["rozstrzygnietych"] < 10:
        out.append("ZAKLADY: %d rozstrzygniec — za malo na ocene trafnosci (potrzeba co najmniej 10)." % z["rozstrzygnietych"])
    if w.get("zero_wyswietlen"):
        out.append("UWAGA: %d notek epoki mialo po 72 h zero wyswietlen i nie wchodzi do porownan (ich odsetek to czesc wyniku)." % w["zero_wyswietlen"])
    return out


# --- tekst raportu ----------------------------------------------------------------------------------------

def _p(x: Any, jednostka: str = "") -> str:
    return "—" if x is None else ("%s%s" % (x, jednostka))


def _wiersz_tabeli(nazwa: str, g: dict[str, Any], odn: str | None) -> str:
    if nazwa == odn:
        stos, werdykt = "odniesienie", ""
    else:
        pr = g.get("przedzial_95")
        stos = "%s [%s–%s]" % (g.get("stosunek"), pr[0], pr[1]) if pr else _p(g.get("stosunek"))
        werdykt = g.get("werdykt", "")
    return "| %s | %d | %s | x%s | %s | %s | %d | %s | %s |" % (
        nazwa, g["n"], _p(g.get("mediana_wysw")), g["wzgl_tla"], g["odbior_na_100"], "%.0f%%" % (100 * g["z_odwiedzinami"]),
        g["zapisy"], stos, werdykt.replace("|", "/"))


NAGLOWEK_TABELI = ("| grupa | notek | mediana wysw. 72 h | wobec tla tygodnia | odbior na 100 wysw. | z odwiedzinami profilu "
                   "| zapisy | stosunek do odniesienia [95%] | werdykt |\n|---|---|---|---|---|---|---|---|---|")


def tekst(w: dict[str, Any]) -> str:
    L = ["# Co dziala — Nothing Is Accidental, %s" % w["dzis"], "",
         "Epoka od %s (domyslnie: od startu serii sledczej obok banku). Zasieg po 72 h wzgledem tla tygodnia, odbior = odwiedziny profilu + 5 x zapisy "
         "przypisane na 100 wyswietlen. Werdykt tylko, gdy przedzial 95%% bootstrapu nie obejmuje 1; w grupie ponizej %d notek "
         "nie pada zaden." % (w["od"], ek.MIN_NOTEK), "",
         "Notek wydanych w epoce: %d, z dojrzalym pomiarem 72 h: %d (zero wyswietlen poza porownaniem: %d). Mediana wyswietlen "
         "notki %s, odchylenie logarytmu %s." % (w["notek_wydanych"], w["notek_z_pomiarem"], w["zero_wyswietlen"],
                                                 _p(w["mediana_wysw"]), _p(w["sd_log"])), ""]
    L += ["## Wnioski", ""] + ["- " + x for x in (w["wnioski"] or ["Za wczesnie na jakikolwiek wniosek — pierwsze dane dojrzewaja 72 h."])] + [""]
    f = w["formaty"]
    L += ["## 1. Formaty", "", NAGLOWEK_TABELI]
    for nazwa, g in f.get("grupy", {}).items():
        L.append(_wiersz_tabeli(nazwa, g, f.get("odniesienie")))
    L += ["", "Formaty: " + "; ".join("%s = %s" % (k, v) for k, v in OPIS_FORMATOW.items()) + ".", ""]
    L += ["## 2. Wymiary notki", "",
          "Kazda tabela porownuje grupy w ramach swojego wymiaru, z odniesieniem = najliczniejsza grupa. Wymiary nie sa niezalezne "
          "(seria jest dluzsza niz bank, rozkmina wychodzi o innej porze) — to mapa, gdzie szukac, a dowodem jest eksperyment.", ""]
    for klucz, t in w["wymiary"].items():
        L += ["### %s" % t["tytul"], ""]
        if not t.get("grupy"):
            L += ["Brak notek z pomiarem w tym wymiarze.", ""]
            continue
        L.append(NAGLOWEK_TABELI)
        for nazwa, g in t["grupy"].items():
            L.append(_wiersz_tabeli(nazwa, g, t.get("odniesienie")))
        L.append("")
    L += ["## 3. Najczesciej czytane notki epoki (po 72 h)", "", "| wysw. | odwiedziny | zapisy | format | kat | slow | poczatek |", "|---|---|---|---|---|---|---|"]
    for n in w["najlepsze"]:
        L.append("| %d | %d | %d | %s | %s | %d | %s |" % (n["wysw"], n["odw"], n["zapisy"], n["format"], n["kat"], n["slow"],
                                                       n["poczatek"].replace("|", "/")))
    L += ["", "## 4. Eksperymenty", ""]
    for nazwa, e in w["eksperymenty"].items():
        L.append("- **%s** (%s, %s–%s, udzial %s): notek w ramionach %d" % (nazwa, e["status"], e["od"], e["do"], _p(e.get("udzial")),
                                                                        e["notek_w_ramionach"]))
        ps = e.get("po_seriach")
        if ps:
            for ramie, r in ps["ramiona"].items():
                L.append("  - ramie %s: serii %d, notek %d, mediana wysw. %s, mediana slow %s, wobec tla %s" % (
                    ramie, r["serii"], r["notek"], _p(r["mediana_wysw"]), _p(r["mediana_slow"]), _p(r["wzgl_tla"], "x")))
            L.append("  - po SERIACH: %s%s" % (ps["werdykt"], (", stosunek on/off %s %s" % (ps["stosunek"], ps["przedzial_95"])) if ps.get("stosunek") else ""))
        elif e.get("tabela") and e["tabela"].get("grupy"):
            for ramie, g in e["tabela"]["grupy"].items():
                L.append("  - ramie %s: %d notek, wobec tla x%s%s" % (ramie, g["n"], g["wzgl_tla"],
                                                                        (", " + g["werdykt"]) if g.get("werdykt") else ""))
    L += ["", "## 5. Koszt", ""]
    if w["koszt_serii"]:
        L += ["| format | tematow | koszt tematu (mediana) | notek wydanych | koszt notki | wysw. 72 h | USD / 1000 wysw. |", "|---|---|---|---|---|---|---|"]
        for fmt, k in w["koszt_serii"].items():
            L.append("| %s | %d | %s | %d | %s | %d | %s |" % (fmt, k["tematow"], k["koszt_tematu_mediana"], k["notek_wydanych"],
                                                              _p(k["koszt_notki"]), k["wysw_72h"], _p(k["koszt_na_1000_wysw"])))
    else:
        L.append("Brak kosztow serii w bazie (przebiegi sledztwa bez wpisu w `calls`).")
    for okno, klucz in (("7 dni", "koszt_grup_7"), ("28 dni", "koszt_grup_28")):
        if w[klucz]:
            L += ["", "Gdzie ida pieniadze, %s: %s (razem %.2f USD)." % (okno, ", ".join("%s %.2f" % (k, v) for k, v in w[klucz].items()),
                                                                          sum(w[klucz].values()))]
    L += ["", "## 6. Sprawdzenie faktow przy publikacji", ""]
    fc = w["fc"]
    if fc["formaty"]:
        L += ["| format | notek | z obalonym twierdzeniem | naprawionych | z zastrzezeniem | nie sprawdzone | twierdzen na notke |", "|---|---|---|---|---|---|---|"]
        for fmt, g in fc["formaty"].items():
            L.append("| %s | %d | %d | %d | %d | %d | %s |" % (fmt, g["n"], g["z_obalonym"], g["naprawionych"], g["z_zastrzezeniem"],
                                                              g["nie_sprawdzonych"], g["twierdzen_na_notke"]))
    L.append("Notek epoki bez pola `fc` (sprzed 27.10.2026): %d." % fc["bez_pola"])
    p = w["potok"]
    L += ["", "## 7. Potok sledztwa", "",
          "- sledztw w epoce: %d (w tym rozkmin %d); notek wyprodukowanych %d, wyszlo %d; kolejka: czeka %d, wygaslo %d, pominietych po probach %d; "
          "mediana dni od sledztwa do pierwszej notki: %s" % (p["sledztw"], p["w_tym_rozkmin"], p["notek_wyprodukowanych"], p["notek_wyszlo"],
                                                            p["kolejka_czeka"], p["kolejka_wygaslo"], p["kolejka_pominietych"],
                                                            _p(p["dni_do_pierwszej_notki_mediana"]))]
    L += ["", "## 8. Wzrost konta", ""]
    if w["wzrost"]:
        for okno in ("7", "28"):
            t = w["wzrost"][okno]
            L.append("- %s dni: subskrybenci netto %+d, obserwujacy netto %+d, wyswietlenia %d (obcy %s), odwiedziny profilu %d, "
                     "zapisy przypisane %d, koszt %.2f USD%s" % (okno, t["subskrybenci_netto"], t["obserwujacy_netto"], t["wyswietlenia"],
                                                                _p(t["obcy_udzial"]), t["odwiedziny_profilu"], t["zapisy_przypisane_karty"], t["koszt_usd"],
                                                                (", %s subskr. na 1000 wysw." % t["subskr_na_1000_wysw"]) if t.get("subskr_na_1000_wysw") is not None else ""))
    else:
        L.append("Brak doby w obserwatorium (uruchom `obserwatorium.py zbierz`).")
    try:
        import zaklady
        L += [""] + zaklady.tekst_statystyk(w["zaklady"] or None)
    except Exception:   # noqa: BLE001
        L += ["", "## Ksiega zakladow", "", "Niedostepna."]
    c = w["czujnik"]
    L += ["## 10. Czujnik „co klika teraz”", "",
          "Przebicia w AI-Substackach (reakcje / mediana publikacji): wykrytych lacznie %d (z 7 dni %d, z 28 dni %d) w %d publikacjach. "
          "To sygnal do uczenia — po kilku tygodniach da sie policzyc, jakie ramy przebijaja i czy nasze notki o nich zyskuja." % (
              c["wszystkich"], c["ostatnie_7"], c["ostatnie_28"], c["publikacji"])]
    for t in c["top"]:
        L.append("- %sx (%s reakcji) %s — %s, %s" % (t["przebicie"], t["reakcje"], t["kanal"], t["temat"], t["data"]))
    return "\n".join(L) + "\n"


def zapisz(od: str = EPOKA_OD) -> Path:
    """`obserwatorium/co_dziala.md` i `.json` + jedna linia na dobe w `co_dziala.jsonl` (historia do trendow)."""
    w = policz(od=od)
    kat = Path(config.DATA_DIR) / "obserwatorium"
    kat.mkdir(parents=True, exist_ok=True)
    (kat / "co_dziala.json").write_text(json.dumps(w, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    p = kat / "co_dziala.md"
    p.write_text(tekst(w), encoding="utf-8")
    historia = Path(config.DATA_DIR) / PLIK_HISTORII
    znane = {x.get("dzis") for x in _jsonl(historia)}
    if w["dzis"] not in znane:
        migawka = {"dzis": w["dzis"], "od": od, "notek": w["notek_z_pomiarem"], "mediana_wysw": w["mediana_wysw"],
                   "formaty": {k: {"n": g["n"], "wzgl_tla": g["wzgl_tla"], "odbior_na_100": g["odbior_na_100"]}
                               for k, g in (w["formaty"].get("grupy") or {}).items()},
                   "zaklady": {k: (w["zaklady"] or {}).get(k) for k in ("zakladow", "rozstrzygnietych", "trafionych", "brier")},
                   "koszt_28": round(sum(w["koszt_grup_28"].values()), 2)}
        with historia.open("a", encoding="utf-8") as f:
            f.write(json.dumps(migawka, ensure_ascii=False, default=str) + "\n")
    return p


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Co dziala w Nothing Is Accidental (tylko odczyt).")
    p.add_argument("--od", default=EPOKA_OD, help="poczatek epoki (data)")
    p.add_argument("--zapisz", action="store_true", help="zapisz tez do obserwatorium/co_dziala.md i .json")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.zapisz:
        print(zapisz(a.od).read_text(encoding="utf-8"))
    else:
        print(tekst(policz(od=a.od)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
