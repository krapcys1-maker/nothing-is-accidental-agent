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

RESTACKI (`--rodzaj restack`, E13) — te same miary co notki: restack z notka
jest notka na naszym profilu. KOMENTARZE (`--rodzaj komentarz`, E14, E15) —
odsetek z reakcja, bo zasiegu komentarza Substack prawie nie oddaje
(`porownaj_komentarze`). TYGODNIE (`--tygodnie restacki_norma`, E12) — miary
konta tydzien po tygodniu (`tygodnie`).

UZYCIE (z korzenia repozytorium, tylko odczyt):
  python agent-v2/eksperymenty.py --pole eksperyment:wniosek
  python agent-v2/eksperymenty.py --pole wniosek --od 2026-09-27
  python agent-v2/eksperymenty.py --rodzaj restack --pole eksperyment:pisarz_restackow
  python agent-v2/eksperymenty.py --rodzaj komentarz --pole eksperyment:cel_komentarza
  python agent-v2/eksperymenty.py --rodzaj komentarz --pole pod
  python agent-v2/eksperymenty.py --tygodnie restacki_norma
Plan pomiaru: `agent-v2/docs/POMIAR_I_EKSPERYMENTY_2026-09-27.md`.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import random
import re
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
            od: str = "", do: str = "", rodzaj: str = "notka") -> list[dict[str, Any]]:
    """Notki (albo restacki) z pomiarem po 72 h: wpis dziennika + liczby odbioru.

    RESTACK Z NOTKA JEST NOTKA na naszym profilu, wiec pomiar ma ten sam i pod
    tym samym numerem, co wpis `restack` w dzienniku (35 z 35 od 1.09.2026).
    """
    out = []
    for e in dziennik:
        if not (isinstance(e, dict) and e.get("rodzaj") == rodzaj and e.get("udane")
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


# --- KOMENTARZE (E14, E15) ------------------------------------------------------
#
# ZASIEGU KOMENTARZA PRAWIE NIE MA: Substack oddaje karte zasiegu dla malej czesci
# (28.09.2026: 78 ze 125 zmierzonych komentarzy ma 0 wyswietlen). Mierzymy wiec
# to, co jest: czy ktos zareagowal (polubienie, odpowiedz, restack) — 24 ze 125
# mialo polubienie, 9 odpowiedz. Komentarz mierzymy tylko 3 doby
# (`browser.DNI_POMIARU_KOMENTARZY`), wiec stan bierzemy po 48 h.
GODZIN_KOMENTARZA = 48
MIN_KOMENTARZY = 30     # ponizej tylu w grupie werdykt to „za malo danych"


def wiersze_komentarzy(dziennik: list[dict], pomiary: dict,
                       od: str = "", do: str = "",
                       rodzaje: tuple[str, ...] = ("komentarz",)) -> list[dict[str, Any]]:
    """Nasze komentarze (albo i odpowiedzi — `rodzaje`) z pomiarem i reakcjami."""
    out = []
    for e in dziennik:
        if not (isinstance(e, dict) and e.get("rodzaj") in rodzaje and e.get("udane")):
            continue
        ident = str(e.get("nasz_id") or e.get("id") or "")
        dzien = str(e.get("kiedy") or "")[:10]
        if not ident or (od and dzien < od) or (do and dzien > do):
            continue
        s = pomiary.get(ident)
        if not s:
            continue
        inter = s.get("interakcje") or {}

        def _ile(pole: str, klucz: str) -> int:
            return max(int(s.get(pole) or 0), int(inter.get(klucz, 0) or 0))

        pol, odp, rest = _ile("polubienia", "Like"), _ile("odpowiedzi", "Reply"), _ile("restacki", "Restack")
        out.append({"wpis": e, "dzien": dzien, "polubienia": pol, "odpowiedzi": odp,
                    "reakcja": 1 if pol + odp + rest else 0, "w": int(s.get("wyswietlenia") or 0),
                    "odwiedziny": _ile("odwiedziny_profilu", "Profile visit")})
    return out


def _odsetek(r: list[dict]) -> float:
    return sum(x["reakcja"] for x in r) / len(r) if r else 0.0


def porownaj_komentarze(dane: list[dict], grupa: Callable[[dict], str],
                        odniesienie: str | None = None) -> dict[str, Any]:
    """Grupy komentarzy: odsetek z reakcja, polubienia i odpowiedzi na 100.

    Stosunek odsetkow grupy do odniesienia z bootstrapem 95%, jak przy notkach.
    """
    grupy: dict[str, list[dict]] = {}
    for x in dane:
        grupy.setdefault(grupa(x["wpis"]), []).append(x)
    if not grupy:
        return {"grupy": {}, "odniesienie": None}
    if odniesienie not in grupy:
        odniesienie = "off" if "off" in grupy else max(grupy, key=lambda g: len(grupy[g]))
    ref = grupy[odniesienie]
    out: dict[str, Any] = {"grupy": {}, "odniesienie": odniesienie}
    for nazwa, r in sorted(grupy.items(), key=lambda kv: -len(kv[1])):
        g: dict[str, Any] = {
            "n": len(r), "z_reakcja": round(100 * _odsetek(r), 1),
            "polubienia_na_100": round(100.0 * sum(x["polubienia"] for x in r) / len(r), 1),
            "odpowiedzi_na_100": round(100.0 * sum(x["odpowiedzi"] for x in r) / len(r), 1),
            "odwiedziny": sum(x["odwiedziny"] for x in r),
            "z_zasiegiem": sum(1 for x in r if x["w"] > 0)}
        if nazwa != odniesienie:
            def stosunek(a: list[dict], b: list[dict]) -> float | None:
                return _odsetek(a) / _odsetek(b) if _odsetek(b) else None
            g["stosunek"] = round(stosunek(r, ref), 3) if stosunek(r, ref) is not None else None
            przedzial = _bootstrap(r, ref, stosunek)
            g["przedzial_95"] = tuple(round(v, 3) for v in przedzial) if przedzial else None
            if len(r) < MIN_KOMENTARZY or len(ref) < MIN_KOMENTARZY:
                g["werdykt"] = "za malo danych (%d i %d komentarzy, trzeba co najmniej %d)" % (
                    len(r), len(ref), MIN_KOMENTARZY)
            elif przedzial and przedzial[0] > 1:
                g["werdykt"] = "lepiej"
            elif przedzial and przedzial[1] < 1:
                g["werdykt"] = "gorzej"
            else:
                g["werdykt"] = "brak dowodu roznicy"
            if _rozne_okresy(r, ref):
                g["werdykt"] += " — OSTROZNIE: grupy z roznych okresow"
        out["grupy"][nazwa] = g
    return out


# --- TYGODNIE (E12) ----------------------------------------------------------------
#
# E12 zmienia LICZBE restackow na caly tydzien, wiec jednostka jest tydzien,
# a miary sa kontowe: przyrost subskrybentow, odwiedziny profilu, zapisy
# przypisane tresciom — z dob obserwatorium (`obserwatorium.podsumuj_konto`).
# Szesc tygodni to trzy na ramie: przedzialu nie liczymy, bo przy trzech
# punktach bylby dekoracja. Tabela mowi wprost, ile tygodni jeszcze brakuje.

def tygodnie(dni: dict[str, dict], nazwa: str, restacki: list[dict] | None = None
             ) -> list[dict[str, Any]]:
    """Tydzien po tygodniu eksperymentu z `plan` (`config.EKSPERYMENTY[nazwa]`)."""
    from datetime import date, timedelta
    import stages

    ustaw = (config.EKSPERYMENTY or {}).get(nazwa) or {}
    if not ustaw.get("plan") or not ustaw.get("od"):
        return []
    start, koniec = date.fromisoformat(ustaw["od"]), date.fromisoformat(ustaw.get("do") or ustaw["od"])
    okres = int(ustaw.get("okres_dni", 7))
    po_dniu: dict[str, list[dict]] = {}
    for x in restacki or []:
        po_dniu.setdefault(x["dzien"], []).append(x)
    out = []
    d = start
    while d <= koniec:
        daty = [(d + timedelta(days=i)).isoformat() for i in range(okres)
                if d + timedelta(days=i) <= koniec]
        dni_z_danymi = [t for t in daty if t in dni]
        przed = (d - timedelta(days=1)).isoformat()
        stany = [dni[t].get("subskrybenci") for t in [przed] + daty
                 if t in dni and dni[t].get("subskrybenci") is not None]
        rs = [x for t in daty for x in po_dniu.get(t, [])]
        out.append({
            "od": daty[0], "do": daty[-1], "ramie": stages.ramie(nazwa, 0, daty[0]),
            "dni_z_danymi": len(dni_z_danymi), "dni": len(daty),
            "restacki": sum(int(dni[t].get("dz_restacki", 0) or 0) for t in dni_z_danymi),
            "przyrost_subskrybentow": (stany[-1] - stany[0]) if len(stany) >= 2 else None,
            "odwiedziny_profilu": sum(int(dni[t].get("odwiedziny_profilu", 0) or 0) for t in dni_z_danymi),
            "zapisy_przypisane": sum(int(dni[t].get("zapisy_przypisane", 0) or 0) for t in dni_z_danymi),
            "wysw_restackow": sum(x["w"] for x in rs),
            "zapisy_z_restackow": sum(x["zapisy"] for x in rs)})
        d += timedelta(days=okres)
    return out


# --- E21: PAMIEC ROZMOWCY — ocena i monitoring zachowania ----------------------------
#
# Wlasciciel 29.09.2026: „wprowadz jako eksperyment plus zrob monitoring tego, jak
# sie zachowuje". Poza odbiorem (reakcje po 48 h, jak E14) patrzymy na to, co pamiec
# ma zmieniac W TEKSCIE: czy wypowiedz do tej samej osoby mniej powtarza poprzednia
# (podobienstwo slow) i czy nawiazuje do wczesniejszej rozmowy. Oba sygnaly to
# heurystyki — pokazuja, CZY model z pamieci korzysta, nie czy dobrze.
RODZAJE_ROZMOWY = ("komentarz", "odpowiedz", "odpowiedz_pod_artykulem")
NAWIAZANIE = re.compile(
    r"\b(last time|earlier|previously|as you (said|wrote|mentioned|noted|put it)|"
    r"you (said|wrote|mentioned|noted|argued) (before|earlier|last)|"
    r"we (talked|discussed|spoke|touched on)|your (last|previous|earlier|other) "
    r"(post|note|piece|comment)|picking up|following up|coming back to)\b", re.IGNORECASE)


def _slowa(tekst: Any) -> set[str]:
    return set(re.findall(r"[a-z']{4,}", str(tekst or "").lower()))


def podobienstwo(a: Any, b: Any) -> float:
    """Jaccard slow co najmniej czteroliterowych — 0 nic wspolnego, 1 te same slowa."""
    x, y = _slowa(a), _slowa(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _uchwyt(w: dict) -> str:
    return str(w.get("uchwyt") or w.get("komu") or "").strip().lower().lstrip("@")


def raport_pamieci(dziennik: list[dict], pomiary: dict, od: str = "", do: str = "",
                   cena_wejscia_usd_mln: float = 0.15, wywolan_na_rozmowe: int = 1
                   ) -> dict[str, Any]:
    """Liczby do monitoringu E21: pokrycie, ramiona, koszt, zachowanie, odbior."""
    rozmowy = sorted((w for w in dziennik if isinstance(w, dict)
                      and w.get("rodzaj") in RODZAJE_ROZMOWY and w.get("udane")),
                     key=lambda w: str(w.get("kiedy") or ""))
    poprzednia: dict[str, str] = {}
    okno, zachowanie = [], {"on": [], "off": []}
    for w in rozmowy:
        dzien = str(w.get("kiedy") or "")[:10]
        u = _uchwyt(w)
        if (not od or dzien >= od) and (not do or dzien <= do):
            okno.append(w)
            r = str((w.get("eksperymenty") or {}).get("pamiec_rozmowcy") or "")
            if r in zachowanie and u in poprzednia:
                zachowanie[r].append({
                    "podobienstwo": podobienstwo(w.get("tekst"), poprzednia[u]),
                    "nawiazanie": bool(NAWIAZANIE.search(str(w.get("tekst") or ""))),
                    "slow": int(w.get("slow") or 0)})
        if u and w.get("tekst"):
            poprzednia[u] = str(w["tekst"])
    z_polem = [w for w in okno if "pamiec_wymian" in w]
    znani = [w for w in z_polem if int(w.get("pamiec_wymian") or 0) > 0]
    ramie = collections.Counter(str((w.get("eksperymenty") or {}).get("pamiec_rozmowcy") or "brak")
                                for w in znani)
    znaki_on = [int(w.get("pamiec_znaki") or 0) for w in znani
                if (w.get("eksperymenty") or {}).get("pamiec_rozmowcy") == "on"]
    dni = max(1, len({str(w.get("kiedy") or "")[:10] for w in okno}))
    tokenow_dzien = sum(znaki_on) / 4.0 * wywolan_na_rozmowe / dni
    out: dict[str, Any] = {
        "rozmow": len(okno), "z_polem_pamieci": len(z_polem), "z_kontaktem": len(znani),
        "ramiona": dict(ramie),
        "znaki_on_srednio": round(sum(znaki_on) / len(znaki_on)) if znaki_on else 0,
        "koszt_usd_miesiecznie": round(tokenow_dzien * 30 * cena_wejscia_usd_mln / 1e6, 4),
        "zachowanie": {}}
    for r, lista in zachowanie.items():
        if lista:
            out["zachowanie"][r] = {
                "n": len(lista),
                "podobienstwo": round(sum(x["podobienstwo"] for x in lista) / len(lista), 3),
                "nawiazanie_proc": round(100.0 * sum(x["nawiazanie"] for x in lista) / len(lista), 1),
                "slow": round(sum(x["slow"] for x in lista) / len(lista), 1)}
    dane = [x for x in wiersze_komentarzy(okno, pomiary, rodzaje=RODZAJE_ROZMOWY)
            if (x["wpis"].get("eksperymenty") or {}).get("pamiec_rozmowcy")]
    out["odbior"] = porownaj_komentarze(dane, _grupujacy("eksperyment:pamiec_rozmowcy"))
    return out


def _drukuj_pamiec(od: str, do: str) -> int:
    import statystyki

    dziennik, _, _ = _wczytaj()
    pomiary = statystyki.po_godzinach(None, GODZIN_KOMENTARZA).get("pozycje") or {}
    cena = float((config.PRICING.get(config.MODEL_FOR.get("comment", "")) or {}).get("in") or 0.15)
    r = raport_pamieci(dziennik, pomiary, od, do, cena_wejscia_usd_mln=cena,
                       wywolan_na_rozmowe=int(getattr(config, "COMMENT_CANDIDATES", 1) or 1))
    print("E21 pamiec rozmowcy — od %s%s" % (od or "poczatku", (" do " + do) if do else ""))
    print("  komentarzy i odpowiedzi: %d; z polem pamieci (kod E21): %d; z wczesniejszym kontaktem: %d%s"
          % (r["rozmow"], r["z_polem_pamieci"], r["z_kontaktem"],
             (" (%.0f%%)" % (100.0 * r["z_kontaktem"] / r["z_polem_pamieci"])) if r["z_polem_pamieci"] else ""))
    print("  ramiona przy kontakcie: %s" % (r["ramiona"] or "—"))
    print("  pamiec w prompcie (on): srednio %d znakow ~ %d tokenow; koszt ok. %.4f USD miesiecznie"
          % (r["znaki_on_srednio"], r["znaki_on_srednio"] // 4, r["koszt_usd_miesiecznie"]))
    print("  zachowanie przy kontakcie (heurystyki):   %8s %8s" % ("on", "off"))
    for pole, opis in (("n", "wypowiedzi z poprzednia do tej osoby"),
                       ("podobienstwo", "podobienstwo do poprzedniej (0-1)"),
                       ("nawiazanie_proc", "nawiazanie do rozmowy (%)"),
                       ("slow", "srednio slow")):
        print("    %-38s %8s %8s" % (opis, *(r["zachowanie"].get(x, {}).get(pole, "—") for x in ("on", "off"))))
    print("  odbior po %d h:" % GODZIN_KOMENTARZA)
    for nazwa, g in (r["odbior"].get("grupy") or {}).items():
        print("    %-4s n=%-4d z reakcja %5.1f%%  odp/100 %5.1f  %s" % (
            nazwa, g["n"], g["z_reakcja"], g["odpowiedzi_na_100"], g.get("werdykt", "(odniesienie)")))
    return 0


def restacki_dziennika(dziennik: list[dict], najnowsze: dict, zapisy: dict[str, int]
                       ) -> list[dict[str, Any]]:
    """Nasze restacki: doba, ostatnie wyswietlenia i zapisy przypisane (do tygodni E12)."""
    out = []
    for e in dziennik:
        if not (isinstance(e, dict) and e.get("rodzaj") == "restack" and e.get("udane")):
            continue
        ident = str(e.get("id") or "")
        s = najnowsze.get(ident) or {}
        out.append({"dzien": str(e.get("kiedy") or "")[:10],
                    "w": int(s.get("wyswietlenia") or 0),
                    "zapisy": int(zapisy.get(ident, 0)) if ident else 0})
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


def _drukuj_tygodnie(nazwa: str) -> int:
    import obserwatorium
    import statystyki

    dziennik, _, zapisy = _wczytaj()
    konto = obserwatorium.konta()[0]
    dni = obserwatorium.podsumuj_konto(konto)
    rs = restacki_dziennika(dziennik, statystyki.najnowsze_per_pozycja("notka"), zapisy)
    wiersze_t = tygodnie(dni, nazwa, rs)
    if not wiersze_t:
        print("Eksperyment %r nie ma planu tygodni w config.EKSPERYMENTY." % nazwa)
        return 1
    print("Eksperyment tygodniowy: %s (konto %s)" % (nazwa, konto["konto"]))
    print("%-23s %5s %5s %8s %10s %10s %8s %9s %9s" % (
        "tydzien", "ramie", "dni", "restacki", "subskr. +", "odw.prof.", "zapisy",
        "wysw.rst", "zap.rst"))
    for t in wiersze_t:
        print("%-23s %5s %2d/%-2d %8d %10s %10d %8d %9d %9d" % (
            t["od"] + " - " + t["do"][5:], t["ramie"], t["dni_z_danymi"], t["dni"], t["restacki"],
            "-" if t["przyrost_subskrybentow"] is None else "%+d" % t["przyrost_subskrybentow"],
            t["odwiedziny_profilu"], t["zapisy_przypisane"], t["wysw_restackow"],
            t["zapisy_z_restackow"]))
    print("\nNa dobe w ramieniu (tylko dni z danymi):")
    for ramie in ("on", "off"):
        tt = [t for t in wiersze_t if t["ramie"] == ramie and t["dni_z_danymi"]]
        d = sum(t["dni_z_danymi"] for t in tt)
        if not d:
            print("  %-4s brak danych" % ramie)
            continue
        przyrost = [t["przyrost_subskrybentow"] for t in tt if t["przyrost_subskrybentow"] is not None]
        print("  %-4s tygodni %d, dni %d: restackow %.2f, subskrybentow %+.2f, odwiedzin profilu %.2f,"
              " zapisow przypisanych %.2f" % (
                  ramie, len(tt), d, sum(t["restacki"] for t in tt) / d,
                  sum(przyrost) / d if przyrost else 0.0,
                  sum(t["odwiedziny_profilu"] for t in tt) / d,
                  sum(t["zapisy_przypisane"] for t in tt) / d))
    pelne = sum(1 for t in wiersze_t if t["dni_z_danymi"] == t["dni"])
    print("\nPelnych tygodni: %d z %d. Werdykt dopiero po wszystkich — przy trzech tygodniach"
          " na ramie przedzial ufnosci bylby dekoracja." % (pelne, len(wiersze_t)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Odbior notek, restackow i komentarzy w grupach, "
                                            "z przedzialem ufnosci (tylko odczyt).")
    p.add_argument("--pole", default="wniosek")
    p.add_argument("--rodzaj", default="notka", choices=("notka", "restack", "komentarz"),
                   help="co porownujemy: notki (E10, E11, E16-E18), restacki (E13), komentarze (E14, E15)")
    p.add_argument("--tygodnie", default="", metavar="EKSPERYMENT",
                   help="eksperyment z planem tygodni, np. restacki_norma (E12)")
    p.add_argument("--pamiec", action="store_true",
                   help="E21: monitoring i ocena pamieci rozmowcy")
    p.add_argument("--od", default=config.DATA_PRZESTAWIENIA)
    p.add_argument("--do", default="")
    p.add_argument("--odniesienie", default=None)
    a = p.parse_args(argv)
    if a.tygodnie:
        return _drukuj_tygodnie(a.tygodnie)
    if a.pamiec:
        return _drukuj_pamiec(a.od if a.od != config.DATA_PRZESTAWIENIA else
                              str((config.EKSPERYMENTY.get("pamiec_rozmowcy") or {}).get("od") or ""),
                              a.do)
    dziennik, pomiary, zapisy = _wczytaj()
    if a.rodzaj == "komentarz":
        import statystyki
        pom = statystyki.po_godzinach("komentarz", GODZIN_KOMENTARZA).get("pozycje") or {}
        dane = wiersze_komentarzy(dziennik, pom, a.od, a.do)
        wynik = porownaj_komentarze(dane, _grupujacy(a.pole), a.odniesienie)
        print("Pole: %s | komentarzy z pomiarem %d h: %d | od %s%s | odniesienie: %s"
              % (a.pole, GODZIN_KOMENTARZA, len(dane), a.od, (" do " + a.do) if a.do else "",
                 wynik.get("odniesienie")))
        print("%-16s %4s %10s %8s %8s %6s %6s  %s" % ("grupa", "n", "z_reakcja%", "pol/100",
                                                      "odp/100", "odw.", "zasieg",
                                                      "wzgledem odniesienia (95%)"))
        for nazwa, g in wynik["grupy"].items():
            wzgl = ""
            if "stosunek" in g:
                pr = g.get("przedzial_95")
                wzgl = "x%s [%s] — %s" % ("%.2f" % g["stosunek"] if g["stosunek"] is not None else "?",
                                          ("%.2f-%.2f" % pr) if pr else "?", g["werdykt"])
            print("%-16s %4d %10.1f %8.1f %8.1f %6d %6d  %s" % (
                nazwa[:16], g["n"], g["z_reakcja"], g["polubienia_na_100"], g["odpowiedzi_na_100"],
                g["odwiedziny"], g["z_zasiegiem"], wzgl))
        return 0
    dane = wiersze(dziennik, pomiary, zapisy, a.od, a.do, rodzaj=a.rodzaj)
    wynik = porownaj(dane, _grupujacy(a.pole), a.odniesienie)
    print("Pole: %s | %s z pomiarem 72 h: %d | od %s%s | odniesienie: %s"
          % (a.pole, {"restack": "restackow"}.get(a.rodzaj, "notek"), len(dane), a.od,
             (" do " + a.do) if a.do else "", wynik.get("odniesienie")))
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
