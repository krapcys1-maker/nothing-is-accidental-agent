# -*- coding: utf-8 -*-
"""LABORATORIUM — tygodniowy raport badawczy obu kont (25.10.2026).

PO CO. Wlasciciel 25.10.2026: „ma byc policzona predkosc przyrostu subskrybentow,
chce wiedziec, czy jak mam wiecej subskrypcji, szybciej mi subskrybentow przybywa,
ile kont jest aktywnych (...) to ma byc laboratorium badawcze". Przez tygodnie raport
obserwatorium dawal pojedyncze odczyty, a odpowiedz (przyrost idzie za wyswietleniami,
nasze subskrypcje innych kont go nie przyspieszaja) dalo sie policzyc z danych, ktore
juz byly. Ten raport liczy ja co dobe, sam, na calej historii obu kont:

  1. PREDKOSC: nowi subskrybenci na tydzien, ostatnie 4 tygodnie wobec 4 wczesniejszych
     (iloraz z przedzialem 95%) i trend tygodni (nachylenie z przedzialem 95%).
  2. DAWKA -> SKUTEK: tydzien po tygodniu, czy wiecej naszych dzialan wychodzacych
     (subskrypcje i obserwacje innych kont, komentarze) idzie z szybszym przyrostem —
     korelacja rang Spearmana z p z permutacji — i to samo PO odjeciu zasiegu
     (reszty z regresji przyrostu na wyswietlenia).
  3. ZASIEG I NOTKI: wyswietlenia na tydzien, mediana wyswietlen notki i jej dlugosc
     wedlug tygodnia publikacji, notki serii sledczej osobno.
  4. ATRYBUCJA: zapisy przypisane przez Substack w 30 dniach, wedlug rodzaju tresci.

Liczone z `obserwatorium/dni_<konto>.json` (tylko odczyt) oraz z dziennika i statystyk
kont. Bez modelu, bez sieci, bez zapisu do katalogu drugiego bota. Wynik:
`obserwatorium/laboratorium.md` i `.json`. Zegar: `obserwatorium.py zbierz --raport`.

UCZCIWIE O MOCY. Konto zbiera kilka osob tygodniowo, wiec tydzien to kilka zliczen:
przedzialy sa szerokie i raport je pokazuje, zamiast udawac pewnosc. „Netto" to zapisy
minus wypisy z licznika konta; przedzial Poissona liczony dla netto jest przyblizeniem.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import obserwatorium as obs

TYGODNI = 12            # ile pelnych tygodni bierze trend i tabela
OKNO_ILORAZU = 4        # ostatnie 4 tygodnie wobec 4 wczesniejszych
DOJRZALOSC_NOTKI_DNI = 3   # notka zbiera zasieg trzy dni (pomiar z 6.09.2026)
PERMUTACJI = 2000
SUMY = ("wyswietlenia", "obcy", "odwiedziny_profilu", "dz_subskrypcje", "dz_obserwacje",
        "dz_komentarze", "dz_notki", "dz_restacki")
# t-Studenta dla 95% dwustronnie, df 1..30 (bez scipy na serwerze).
T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179,
       2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064,
       2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


# --- statystyka ----------------------------------------------------------------

def _t95(df: int) -> float:
    return T95[df - 1] if 1 <= df <= len(T95) else 1.96


def przedzial_poissona(k: int, okres: float = 1.0) -> tuple[float, float] | None:
    """95% dla tempa zliczen `k` w `okres` (przyblizenie Byara). None dla k < 0."""
    if k < 0 or okres <= 0:
        return None
    z = 1.96
    dol = 0.0 if k == 0 else k * (1 - 1 / (9 * k) - z / (3 * math.sqrt(k))) ** 3
    g = k + 1
    gora = g * (1 - 1 / (9 * g) + z / (3 * math.sqrt(g))) ** 3
    return dol / okres, gora / okres


def iloraz_tempa(a: int, b: int) -> dict[str, Any] | None:
    """Iloraz dwoch zliczen w rownych oknach z 95% (log-normalny). None przy zerze."""
    if a <= 0 or b <= 0:
        return None
    rr = a / b
    se = math.sqrt(1 / a + 1 / b)
    return {"iloraz": round(rr, 2), "dol": round(rr * math.exp(-1.96 * se), 2),
            "gora": round(rr * math.exp(1.96 * se), 2)}


def nachylenie(y: list[float]) -> dict[str, Any] | None:
    """Regresja liniowa y na numer tygodnia: nachylenie (osob/tydzien na tydzien) z 95%."""
    n = len(y)
    if n < 4:
        return None
    x = list(range(n))
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    b = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    a = my - b * mx
    sse = sum((yi - (a + b * xi)) ** 2 for xi, yi in zip(x, y))
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 else float("nan")
    t = _t95(n - 2)
    return {"nachylenie": round(b, 2), "dol": round(b - t * se, 2), "gora": round(b + t * se, 2), "n": n}


def _rangi(v: list[float]) -> list[float]:
    """Rangi z remisami usrednionymi (1 = najmniejszy)."""
    kolej = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(kolej):
        j = i
        while j + 1 < len(kolej) and v[kolej[j + 1]] == v[kolej[i]]:
            j += 1
        for k in range(i, j + 1):
            r[kolej[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman(x: list[float], y: list[float], permutacji: int = PERMUTACJI,
             ziarno: int = 0) -> dict[str, Any] | None:
    """Rho Spearmana i p dwustronne z permutacji (stale ziarno — powtarzalne)."""
    if len(x) < 5:
        return None
    rx, ry = _rangi(x), _rangi(y)
    rho = _pearson(rx, ry)
    if rho is None:
        return None
    los = random.Random(ziarno)
    ile = 0
    pom = list(ry)
    for _ in range(permutacji):
        los.shuffle(pom)
        r = _pearson(rx, pom)
        if r is not None and abs(r) >= abs(rho) - 1e-12:
            ile += 1
    return {"rho": round(rho, 2), "p": round((ile + 1) / (permutacji + 1), 3), "n": len(x)}


def reszty(y: list[float], x: list[float]) -> list[float] | None:
    """Reszty z regresji y na x — przyrost PO odjeciu tego, co tlumaczy zasieg."""
    if len(y) < 4:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if not sxx:
        return None
    b = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    return [yi - (my + b * (xi - mx)) for xi, yi in zip(x, y)]


# --- dane ----------------------------------------------------------------------

def tygodnie(dni: dict[str, dict], wczoraj: str, ile: int = TYGODNI) -> list[dict[str, Any]]:
    """Pelne tygodnie (pon-niedz) z przyrostem netto i sumami dzialan oraz zasiegu.

    Tydzien bez odczytu licznika na poczatku lub koncu ma `sub` = None (luka to nie zero).
    `pelny_pomiar` = co najmniej 5 dob z pomiarem tresci — tylko takie tygodnie ida do
    rachunkow z wyswietleniami.
    """
    out = []
    for od, do, przyrost in obs.tygodnie_netto(dni, wczoraj, ile):
        daty = [(obs._d(od) + timedelta(days=i)).isoformat() for i in range(7)]
        w: dict[str, Any] = {"od": od, "do": do,
                             "sub": przyrost["sub"] if przyrost else None,
                             "obs": przyrost["obs"] if przyrost else None}
        for pole in SUMY:
            w[pole] = sum(int((dni.get(d) or {}).get(pole) or 0) for d in daty)
        w["pelny_pomiar"] = sum(1 for d in daty if (dni.get(d) or {}).get("pomiar_tresci")) >= 5
        w["wychodzace"] = w["dz_subskrypcje"] + w["dz_obserwacje"]
        out.append(w)
    return out


def notki_tygodniami(dane: Path, dzis: str, ile: int = TYGODNI) -> list[dict[str, Any]]:
    """Mediana wyswietlen i dlugosci notek wedlug tygodnia publikacji (notki >= 3 dni).

    Wyswietlenia notki = najwyzszy odczyt jej licznika ze statystyk konta. Notka serii
    sledczej = wpis z `przeslanie_id` (od 27.09.2026; drugie konto go nie ma).
    """
    naj: dict[str, int] = {}
    for s in obs._jsonl(dane / "statystyki.jsonl"):
        if s.get("rodzaj") == "notka" and s.get("id") and isinstance(s.get("wyswietlenia"), int):
            i = str(s["id"])
            naj[i] = max(naj.get(i, 0), s["wyswietlenia"])
    granica = (obs._d(dzis) - timedelta(days=DOJRZALOSC_NOTKI_DNI)).isoformat()
    koniec = obs._d(dzis)
    poniedzialek = koniec - timedelta(days=koniec.weekday())
    pierwszy = (poniedzialek - timedelta(days=7 * ile)).isoformat()
    grupy: dict[str, list[dict]] = {}
    for w in obs._jsonl(dane / "dziennik.jsonl"):
        if w.get("rodzaj") != "notka" or not w.get("udane") or not w.get("id"):
            continue
        kiedy = str(w.get("kiedy") or "")[:10]
        if not kiedy or kiedy > granica or kiedy < pierwszy or str(w["id"]) not in naj:
            continue
        d = obs._d(kiedy)
        tydzien = (d - timedelta(days=d.weekday())).isoformat()
        slow = w.get("slow") if isinstance(w.get("slow"), int) else len(str(w.get("tekst") or "").split())
        grupy.setdefault(tydzien, []).append({"wysw": naj[str(w["id"])], "slow": slow,
                                              "seria": bool(w.get("przeslanie_id"))})
    out = []
    for t in sorted(grupy):
        g = grupy[t]
        seria = [x["wysw"] for x in g if x["seria"]]
        out.append({"tydzien": t, "notek": len(g),
                    "mediana_wysw": statistics.median(x["wysw"] for x in g),
                    "mediana_slow": statistics.median(x["slow"] for x in g if x["slow"]) if any(x["slow"] for x in g) else None,
                    "seria_notek": len(seria),
                    "seria_mediana_wysw": statistics.median(seria) if seria else None})
    return out


# --- rachunek konta ---------------------------------------------------------------

def policz_konto(dni: dict[str, dict], dane: Path, zrodla: dict | None, wczoraj: str,
                 dzis: str) -> dict[str, Any]:
    tyg = tygodnie(dni, wczoraj)
    z_licznikiem = [t for t in tyg if t["sub"] is not None]
    wynik: dict[str, Any] = {"tygodnie": tyg}
    # 1. predkosc
    ost = z_licznikiem[-OKNO_ILORAZU:]
    wcz = z_licznikiem[-2 * OKNO_ILORAZU:-OKNO_ILORAZU]
    if len(ost) == OKNO_ILORAZU:
        a = sum(t["sub"] for t in ost)
        wynik["tempo_4t"] = {"razem": a, "na_tydzien": round(a / OKNO_ILORAZU, 1),
                             "przedzial": [round(v, 1) for v in przedzial_poissona(a, OKNO_ILORAZU)]
                             if przedzial_poissona(a, OKNO_ILORAZU) else None}
        if len(wcz) == OKNO_ILORAZU:
            b = sum(t["sub"] for t in wcz)
            wynik["tempo_4t_wczesniej"] = {"razem": b, "na_tydzien": round(b / OKNO_ILORAZU, 1)}
            wynik["iloraz_tempa"] = iloraz_tempa(a, b)
    wynik["trend"] = nachylenie([float(t["sub"]) for t in z_licznikiem])
    # 2. dawka -> skutek (tylko tygodnie z pelnym pomiarem tresci)
    pelne = [t for t in z_licznikiem if t["pelny_pomiar"]]
    y = [float(t["sub"]) for t in pelne]
    wysw = [float(t["wyswietlenia"]) for t in pelne]
    wynik["zaleznosci"] = {
        "przyrost~wyswietlenia": spearman(wysw, y),
        "przyrost~wychodzace": spearman([float(t["wychodzace"]) for t in pelne], y, ziarno=1),
        "przyrost~nasze_subskrypcje": spearman([float(t["dz_subskrypcje"]) for t in pelne], y, ziarno=2),
        "przyrost~komentarze": spearman([float(t["dz_komentarze"]) for t in pelne], y, ziarno=3),
    }
    r = reszty(y, wysw)
    wynik["zaleznosci"]["reszta_po_zasiegu~wychodzace"] = (
        spearman([float(t["wychodzace"]) for t in pelne], r, ziarno=4) if r else None)
    sw = sum(wysw)
    wynik["na_1000_wyswietlen"] = round(1000 * sum(y) / sw, 2) if sw else None
    # 3. notki
    wynik["notki"] = notki_tygodniami(dane, dzis)
    # 4. atrybucja Substacka (okno 30 dni z panelu zrodel)
    prz = (zrodla or {}).get("przypisane") or {}
    wynik["atrybucja"] = {"okno": (zrodla or {}).get("okno"), "wg_rodzaju": prz.get("wg_rodzaju"),
                          "razem": prz.get("razem"), "razem_panel": (zrodla or {}).get("razem_panel")}
    return wynik


def policz(wczoraj: str | None = None) -> dict[str, Any]:
    dzis = datetime.now(timezone.utc).date().isoformat()
    wczoraj = wczoraj or (obs._d(dzis) - timedelta(days=1)).isoformat()
    out: dict[str, Any] = {"kiedy": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                           "do": wczoraj, "konta": {}}
    for k in obs.konta():
        try:
            zrodla = json.loads((obs.katalog() / ("zrodla_%s.json" % k["konto"])).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            zrodla = None
        out["konta"][k["konto"]] = policz_konto(obs.wczytaj_dni(k["konto"]), Path(k["dane"]),
                                                zrodla, wczoraj, dzis)
    return out


# --- tekst -----------------------------------------------------------------------

def _rho(z: dict | None) -> str:
    if not z:
        return "nie do policzenia (mniej niz 5 tygodni albo stala seria)"
    sila = ("brak zwiazku" if abs(z["rho"]) < 0.3 else "slaby" if abs(z["rho"]) < 0.5 else "wyrazny")
    pewnosc = "istotne" if z["p"] < 0.05 else "nieistotne"
    return "rho %+.2f, p = %.3f, n = %d tyg. (%s, %s)" % (z["rho"], z["p"], z["n"], sila, pewnosc)


def tekst(w: dict[str, Any]) -> str:
    L = ["# Laboratorium — raport tygodniowy obu kont", "",
         "Stan na %s (pelne tygodnie pon-niedz do %s). Liczone samo co dobe; metoda w `agent-v2/laboratorium.py`."
         % (w["kiedy"][:16].replace("T", " ") + " UTC", w["do"]), ""]
    for konto, k in w["konta"].items():
        L += ["## %s" % konto, ""]
        t4, tw, rr, tr = k.get("tempo_4t"), k.get("tempo_4t_wczesniej"), k.get("iloraz_tempa"), k.get("trend")
        L.append("**1. Predkosc przyrostu subskrybentow (netto)**")
        if not t4:
            L.append("- za malo tygodni z odczytem licznika")
        if t4:
            L.append("- ostatnie 4 tygodnie: %s na tydzien (razem %d%s)" % (
                t4["na_tydzien"], t4["razem"],
                ", 95%%: %s-%s na tydzien" % tuple(t4["przedzial"]) if t4.get("przedzial") else ""))
        if tw:
            L.append("- 4 tygodnie wczesniej: %s na tydzien (razem %d)" % (tw["na_tydzien"], tw["razem"]))
        if rr:
            L.append("- iloraz tempa: %.2f (95%%: %.2f-%.2f) — %s" % (
                rr["iloraz"], rr["dol"], rr["gora"],
                "szybciej" if rr["dol"] > 1 else "wolniej" if rr["gora"] < 1 else "roznica w granicach szumu"))
        if tr:
            L.append("- trend %d tygodni: %+.2f osoby/tydz. na tydzien (95%%: %+.2f do %+.2f) — %s" % (
                tr["n"], tr["nachylenie"], tr["dol"], tr["gora"],
                "przyspiesza" if tr["dol"] > 0 else "zwalnia" if tr["gora"] < 0 else "bez wykrywalnego trendu"))
        L += ["", "**2. Dawka -> skutek (tydzien po tygodniu, tygodnie z pelnym pomiarem tresci)**"]
        z = k["zaleznosci"]
        L.append("- przyrost a wyswietlenia: %s" % _rho(z["przyrost~wyswietlenia"]))
        L.append("- przyrost a nasze subskrypcje + obserwacje innych kont: %s" % _rho(z["przyrost~wychodzace"]))
        L.append("- przyrost a same nasze subskrypcje: %s" % _rho(z["przyrost~nasze_subskrypcje"]))
        L.append("- przyrost a nasze komentarze: %s" % _rho(z["przyrost~komentarze"]))
        L.append("- po odjeciu zasiegu (reszta z regresji na wyswietlenia) a dzialania wychodzace: %s"
                 % _rho(z["reszta_po_zasiegu~wychodzace"]))
        if k.get("na_1000_wyswietlen") is not None:
            L.append("- nowi netto na 1000 wyswietlen notek i artykulow: %s (to nie konwersja jednego kanalu)"
                     % k["na_1000_wyswietlen"])
        L += ["", "| tydzien od | subskr. netto | obserw. netto | wyswietlenia | nasze subskr. | nasze obserw. | komentarze | notki |",
              "|---|---|---|---|---|---|---|---|"]
        for t in k["tygodnie"]:
            L.append("| %s | %s | %s | %s%s | %d | %d | %d | %d |" % (
                t["od"], "—" if t["sub"] is None else t["sub"], "—" if t["obs"] is None else t["obs"],
                t["wyswietlenia"], "" if t["pelny_pomiar"] else "*", t["dz_subskrypcje"],
                t["dz_obserwacje"], t["dz_komentarze"], t["dz_notki"]))
        L.append("")
        L.append("\\* tydzien bez pelnego pomiaru tresci (pomijany w zaleznosciach).")
        if k["notki"]:
            L += ["", "**3. Notki wedlug tygodnia publikacji (najwyzszy odczyt, notki co najmniej 3-dniowe)**", "",
                  "| tydzien | notek | mediana wysw. | mediana slow | w tym seria | mediana serii |",
                  "|---|---|---|---|---|---|"]
            for n in k["notki"]:
                L.append("| %s | %d | %s | %s | %d | %s |" % (
                    n["tydzien"], n["notek"], n["mediana_wysw"], n["mediana_slow"] or "—",
                    n["seria_notek"], "—" if n["seria_mediana_wysw"] is None else n["seria_mediana_wysw"]))
        a = k.get("atrybucja") or {}
        if a.get("wg_rodzaju"):
            L += ["", "**4. Zapisy przypisane przez Substack** (okno %s do %s): %s; razem %s, panel %s" % (
                (a.get("okno") or {}).get("od"), (a.get("okno") or {}).get("do"),
                ", ".join("%s %s" % (r, n) for r, n in sorted(a["wg_rodzaju"].items(), key=lambda x: (-x[1], x[0]))),
                a.get("razem"), a.get("razem_panel"))]
        L.append("")
    L += ["## Jak czytac", "",
          "- Iloraz tempa i trend z przedzialami 95%: przedzial obejmujacy 1 (albo 0 dla trendu) znaczy, ze przy",
          "  kilku osobach tygodniowo zmiany nie da sie odroznic od przypadku.",
          "- Spearman na tygodniach to zwiazek, nie przyczyna: zasieg i nasze dzialania zmienialy sie razem.",
          "  Wiersz „po odjeciu zasiegu\" pyta, czy dzialania pomagaja PONAD to, co tlumacza wyswietlenia.",
          "- Przyczynowo rozstrzygaja eksperymenty przeplatane (`eksperymenty.py`) i reguly ocen zapisane",
          "  przed startem (`docs/POMIAR_I_EKSPERYMENTY_2026-09-27.md`)."]
    return "\n".join(L) + "\n"


def zapisz() -> Path:
    w = policz()
    kat = obs.katalog()
    kat.mkdir(parents=True, exist_ok=True)
    (kat / "laboratorium.json").write_text(json.dumps(w, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    p = kat / "laboratorium.md"
    p.write_text(tekst(w), encoding="utf-8")
    return p


if __name__ == "__main__":
    sciezka = zapisz()
    print(sciezka.read_text(encoding="utf-8"))
    sys.exit(0)
