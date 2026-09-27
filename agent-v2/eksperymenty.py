# -*- coding: utf-8 -*-
"""Czy zmiana cos dala — odbior notek po 72 h w grupach, z przedzialem ufnosci.

PO CO. Wlasciciel 27.09.2026: „jak cos bedziemy zmieniac, zeby wiedziec, co
przynioslo skutek, a co nie". Karta wynikow pokazuje srednie grup, ale przy
kilkunastu notkach w grupie roznica 30% bywa czystym przypadkiem: odchylenie
logarytmu wyswietlen to 0,55, mediana notki 19 wyswietlen, a 72 ze 105 notek
nie mialo ani jednej odwiedziny profilu. Ten modul mowi wprost: lepiej /
gorzej / brak dowodu roznicy / za malo danych — i ile notek brakuje.

MIARY (po 72 h od pierwszego pomiaru, `statystyki.po_godzinach`):
  - wyswietlenia: srednia GEOMETRYCZNA (rozklad jest skosny) oraz `wzgl_tla` —
    ile razy notki grupy bija typowa notke konta z tego samego tygodnia
    (`odejmij_tlo`); STOSUNEK DO ODNIESIENIA LICZYMY NA TYM DRUGIM, bo zasieg
    spadal we wrzesniu o 55% i surowe srednie porownywaly tygodnie, nie zmiany;
  - zaangazowanie: (polubienia + odpowiedzi + restacki) na 100 wyswietlen;
  - odbior: (odwiedziny profilu + 5 x zapisy przypisane) na 100 wyswietlen,
    liczony lacznie dla grupy — ta sama miara co `statystyki.wynik_odbioru`.
Przedzial: bootstrap 95% (2000 losowan, stale ziarno — ten sam wynik za
kazdym razem). NIE 90%: przy 90% co dziesiate porownanie BEZ zadnego efektu
wychodzi „lepiej" albo „gorzej" — test tego modulu trafil na taki fuks
(stosunek 0,75 przy tym samym rozkladzie).

GRUPY. `--pole wniosek|radar|glebia|koncowka` — te same grupy co karta wynikow;
`--pole eksperyment:<nazwa>` — ramiona eksperymentu przeplatanego
(`config.EKSPERYMENTY`); `--pole przeslanie`; kazde inne pole dziennika wprost
(`wersja`, `forma`, `typ`, `styk`, `model`).

UZYCIE (z korzenia repozytorium, tylko odczyt):
  python agent-v2/eksperymenty.py --pole eksperyment:wniosek
  python agent-v2/eksperymenty.py --pole wniosek --od 2026-09-27
Plan pomiaru: `agent-v2/docs/POMIAR_I_EKSPERYMENTY_2026-09-27.md`.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from typing import Any, Callable

import config

MIN_NOTEK = 10          # ponizej tylu notek w grupie werdykt to „za malo danych"
LOSOWAN = 2000          # bootstrap
ZIARNO = 7
WAGA_ZAPISU = 5         # jak `statystyki.WAGA_ZAPISU`


def _grupujacy(pole: str) -> Callable[[dict], str]:
    """Funkcja: wpis dziennika -> nazwa grupy."""
    import karta_wynikow as kw
    gotowe = {"wniosek": kw._grupa_wniosku, "radar": kw._grupa_radaru,
              "glebia": kw._grupa_glebi, "koncowka": kw._grupa_koncowki}
    if pole in gotowe:
        return gotowe[pole]
    if pole == "przeslanie":
        return lambda e: ("przed" if "przeslanie_id" not in e
                          else "z_przeslania" if e.get("przeslanie_id") else "zwykla")
    if pole.startswith("eksperyment:"):
        nazwa = pole.split(":", 1)[1]
        return lambda e: str((e.get("eksperymenty") or {}).get(nazwa) or "poza")
    return lambda e: str(e.get(pole) if e.get(pole) not in (None, "") else "brak")


def wiersze(dziennik: list[dict], pomiary: dict, zapisy: dict[str, int],
            od: str = "", do: str = "") -> list[dict[str, Any]]:
    """Notki z pomiarem po 72 h: wpis dziennika + liczby odbioru."""
    out = []
    for e in dziennik:
        if not (isinstance(e, dict) and e.get("rodzaj") == "notka" and e.get("udane")
                and e.get("id")):
            continue
        dzien = str(e.get("kiedy") or "")[:10]
        if (od and dzien < od) or (do and dzien > do):
            continue
        s = pomiary.get(str(e["id"]))
        if not s:
            continue
        w = int(s.get("wyswietlenia") or 0)
        if w <= 0:
            continue
        inter = s.get("interakcje") or {}
        odw = int(s.get("odwiedziny_profilu") if s.get("odwiedziny_profilu") is not None
                  else inter.get("Profile visit", 0))
        zaang = sum(int(inter.get(k, 0) or 0) for k in ("Like", "Reply", "Restack"))
        if not inter:
            zaang = int(s.get("polubienia") or 0)
        out.append({"wpis": e, "w": w, "lw": math.log(w), "zaang": zaang, "dzien": dzien,
                    "odbior": odw + WAGA_ZAPISU * int(zapisy.get(str(e["id"]), 0))})
    return out


def _dzien(x: dict) -> int:
    from datetime import date
    try:
        return date.fromisoformat(str(x.get("dzien") or "")[:10]).toordinal()
    except ValueError:
        return 0


def odejmij_tlo(dane: list[dict], okno: int = 7, min_sasiadow: int = 5) -> None:
    """Kazdej notce: `lr` = log wyswietlen MINUS typowa notka konta z tego tygodnia.

    ZASIEG ZALEZY OD TYGODNIA BARDZIEJ NIZ OD NOTKI. We wrzesniu 2026 srednia
    geometryczna spadla z 26,5 do 12,2 wyswietlenia, wiec grupa z sierpnia
    wygrywala z kazda grupa z wrzesnia — pierwsze uruchomienie tego modulu
    ogloslilo „lepiej x1,95" dla notek bez pola `model`, czyli po prostu
    starszych. Tlo = mediana log-wyswietlen INNYCH notek z +-`okno` dni
    (za malo sasiadow -> mediana calosci). Zmienia porownanie z „ktora grupa
    ma wiecej wyswietlen" na „ktora grupa bije swoje tlo".
    """
    if not dane:
        return
    dni = [_dzien(x) for x in dane]
    wszystkie = sorted(x["lw"] for x in dane)
    globalna = wszystkie[len(wszystkie) // 2]
    for i, x in enumerate(dane):
        sasiedzi = sorted(y["lw"] for j, y in enumerate(dane)
                          if j != i and dni[j] and dni[i] and abs(dni[j] - dni[i]) <= okno)
        tlo = sasiedzi[len(sasiedzi) // 2] if len(sasiedzi) >= min_sasiadow else globalna
        x["lr"] = x["lw"] - tlo


def _rozne_okresy(a: list[dict], b: list[dict]) -> bool:
    """Czy grupy pochodza z roznych okresow — wtedy trend miesza sie ze zmiana."""
    da, db = [_dzien(x) for x in a if _dzien(x)], [_dzien(x) for x in b if _dzien(x)]
    if not da or not db:
        return False
    w_b = sum(1 for d in da if min(db) <= d <= max(db)) / len(da)
    w_a = sum(1 for d in db if min(da) <= d <= max(da)) / len(db)
    return min(w_a, w_b) < 0.5


def _kwantyle(wartosci: list[float]) -> tuple[float, float]:
    wartosci = sorted(wartosci)
    return (wartosci[int(0.025 * len(wartosci))],
            wartosci[max(0, int(0.975 * len(wartosci)) - 1)])


def _bootstrap(a: list[dict], b: list[dict], stat: Callable[[list, list], float | None]
               ) -> tuple[float, float] | None:
    rnd = random.Random(ZIARNO)
    wyniki = []
    for _ in range(LOSOWAN):
        x = stat([rnd.choice(a) for _ in a], [rnd.choice(b) for _ in b])
        if x is not None:
            wyniki.append(x)
    return _kwantyle(wyniki) if len(wyniki) > LOSOWAN // 2 else None


def _geo(r: list[dict]) -> float:
    return math.exp(sum(x["lw"] for x in r) / len(r))


def _na_100(r: list[dict], pole: str) -> float:
    w = sum(x["w"] for x in r)
    return 100.0 * sum(x[pole] for x in r) / w if w else 0.0


def _stosunek(a: list[dict], b: list[dict]) -> float:
    """Ile razy grupa `a` bije swoje tlo mocniej niz grupa `b` (patrz `odejmij_tlo`)."""
    return math.exp(sum(x["lr"] for x in a) / len(a) - sum(x["lr"] for x in b) / len(b))


def _sd_log(r: list[dict]) -> float:
    if len(r) < 2:
        return 0.0
    m = sum(x["lr"] for x in r) / len(r)
    return math.sqrt(sum((x["lr"] - m) ** 2 for x in r) / (len(r) - 1))


def porownaj(dane: list[dict], grupa: Callable[[dict], str],
             odniesienie: str | None = None) -> dict[str, Any]:
    """Grupy, ich miary i porownanie kazdej z grupa odniesienia.

    Odniesienie: podane, albo „off" dla eksperymentu, albo najliczniejsza grupa.
    """
    if any("lr" not in x for x in dane):
        odejmij_tlo(dane)
    grupy: dict[str, list[dict]] = {}
    for x in dane:
        grupy.setdefault(grupa(x["wpis"]), []).append(x)
    if not grupy:
        return {"grupy": {}, "odniesienie": None}
    if odniesienie not in grupy:
        odniesienie = "off" if "off" in grupy else max(grupy, key=lambda g: len(grupy[g]))
    ref = grupy[odniesienie]
    sd = _sd_log(dane)
    out: dict[str, Any] = {"grupy": {}, "odniesienie": odniesienie, "sd_log": round(sd, 3)}
    for nazwa, r in sorted(grupy.items(), key=lambda kv: -len(kv[1])):
        g: dict[str, Any] = {"n": len(r), "wysw_geom": round(_geo(r), 1),
                             "wzgl_tla": round(math.exp(sum(x["lr"] for x in r) / len(r)), 2),
                             "zaang_na_100": round(_na_100(r, "zaang"), 1),
                             "odbior_na_100": round(_na_100(r, "odbior"), 2)}
        if nazwa != odniesienie:
            g["stosunek"] = round(_stosunek(r, ref), 3)
            przedzial = _bootstrap(r, ref, _stosunek)
            g["przedzial_95"] = tuple(round(v, 3) for v in przedzial) if przedzial else None
            # NAJMNIEJSZY WYKRYWALNY EFEKT przy tych licznosciach (moc 80%,
            # dwustronnie 5%) — mowi, czy „brak dowodu" znaczy „brak efektu",
            # czy tylko „za krotko mierzymy".
            g["wykrywalny_efekt"] = (round(math.exp(2.8 * sd * math.sqrt(1 / len(r) + 1 / len(ref))) - 1, 2)
                                     if sd else None)
            if len(r) < MIN_NOTEK or len(ref) < MIN_NOTEK:
                g["werdykt"] = "za malo danych (%d i %d notek, trzeba co najmniej %d)" % (
                    len(r), len(ref), MIN_NOTEK)
            elif przedzial and przedzial[0] > 1:
                g["werdykt"] = "lepiej"
            elif przedzial and przedzial[1] < 1:
                g["werdykt"] = "gorzej"
            else:
                g["werdykt"] = "brak dowodu roznicy (wykrylibysmy dopiero ok. %+d%%)" % round(
                    100 * (g["wykrywalny_efekt"] or 0))
            # ROZNE OKRESY: nawet po odjeciu tla grupa z innych tygodni moze
            # roznic sie czyms, co przyszlo razem z czasem (inne zrodla, inny
            # bank). Werdykt zostaje, ale z ostrzezeniem — dowodem jest dopiero
            # eksperyment przeplatany (`config.EKSPERYMENTY`).
            if _rozne_okresy(r, ref):
                g["werdykt"] += " — OSTROZNIE: grupy z roznych okresow"
        out["grupy"][nazwa] = g
    return out


def _wczytaj() -> tuple[list[dict], dict, dict]:
    import statystyki
    dziennik = []
    try:
        with (config.DATA_DIR / "dziennik.jsonl").open(encoding="utf-8") as f:
            for linia in f:
                try:
                    dziennik.append(json.loads(linia))
                except ValueError:
                    continue
    except OSError:
        pass
    return (dziennik, statystyki.po_godzinach("notka", 72).get("pozycje") or {},
            statystyki.zapisy_przypisane())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Odbior notek w grupach, z przedzialem ufnosci (tylko odczyt).")
    p.add_argument("--pole", default="wniosek")
    p.add_argument("--od", default=config.DATA_PRZESTAWIENIA)
    p.add_argument("--do", default="")
    p.add_argument("--odniesienie", default=None)
    a = p.parse_args(argv)
    dziennik, pomiary, zapisy = _wczytaj()
    dane = wiersze(dziennik, pomiary, zapisy, a.od, a.do)
    wynik = porownaj(dane, _grupujacy(a.pole), a.odniesienie)
    print("Pole: %s | notek z pomiarem 72 h: %d | od %s%s | odniesienie: %s"
          % (a.pole, len(dane), a.od, (" do " + a.do) if a.do else "", wynik.get("odniesienie")))
    print("%-16s %4s %9s %9s %9s %10s  %s" % ("grupa", "n", "wysw_geom", "wzgl_tla", "zaang/100",
                                             "odbior/100", "wzgledem odniesienia (95%)"))
    for nazwa, g in wynik["grupy"].items():
        wzgl = ""
        if "stosunek" in g:
            pr = g.get("przedzial_95")
            wzgl = "x%.2f [%s] — %s" % (g["stosunek"], ("%.2f-%.2f" % pr) if pr else "?", g["werdykt"])
        print("%-16s %4d %9.1f %9.2f %9.1f %10.2f  %s" % (nazwa[:16], g["n"], g["wysw_geom"], g["wzgl_tla"],
                                                         g["zaang_na_100"], g["odbior_na_100"], wzgl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
