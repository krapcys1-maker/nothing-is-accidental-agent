# -*- coding: utf-8 -*-
"""Obserwatorium — oba konta w jednym miejscu: dane dnia, dziennik zmian, silnik statystyk.

PO CO. Wlasciciel 28.09.2026: „znajdz sposob na gromadzenie danych i z NIA, i z
Nothing Is Accidental — przyrost subskrybentow, wyswietlenia, followersi; trzeba
zrobic dziennik zmian wykonywanych, daty kiedy zostaly wprowadzone, i silnik,
ktory mierzy statystyki (...) tempo przyrostu (...) badania nad Substackiem, jak
najlepiej rozwijac konto".

ZASADY
- TYLKO ODCZYT danych obu botow i ZADNYCH nowych zapytan do Substacka. Oba boty
  juz zapisuja (NIA to fork, ten sam ksztalt plikow): wzrost konta 4-6 razy na
  dobe, statystyki kazdej tresci, zrodla ruchu i zapisow, dziennik dzialan i
  koszt w bazie. Do katalogu NIA nic nie piszemy; jej baze otwieramy
  z `immutable=1`, zeby SQLite nie zostawil tam plikow pomocniczych.
- BEZ DANYCH OSOBOWYCH. Z list czytelnikow bierzemy wylacznie LICZBE nowych
  osob; nazwy i uchwyty nie trafiaja do obserwatorium. Pole `kto_sie_zapisal`
  ze statystyk jest pomijane.
- ZAPIS TRWALY. Pliki botow mozna kiedys przyciac, a git reflog kasuje sie po
  90 dniach — obserwatorium trzyma wlasne podsumowania dni i dziennik zmian
  w `data/obserwatorium/`.
- SIOSTRA. Kazde konto ma drugie na liscie subskrybentow (sprawdzone 28.09):
  licznik subskrybentow zawyza sie o 1, a wzajemne dzialania botow nie sa
  wzrostem. Raport pokazuje subskrybentow „bez siostry" i dzialania do siostry.

UZYCIE (z korzenia repozytorium):
  python agent-v2/obserwatorium.py zbierz [--raport]   # codziennie z zegara
  python agent-v2/obserwatorium.py raport [--dni 14]
  python agent-v2/obserwatorium.py zmiana --konto NIE --rodzaj eksperyment --id E11 --opis "..."
  python agent-v2/obserwatorium.py zmiany [--dni 30]
Plan i definicje: `agent-v2/docs/OBSERWATORIUM_2026-09-28.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

REPO_NIE = Path(__file__).resolve().parent.parent
POLA_STANU = ("subskrybenci", "subskrybenci_darmowi", "obserwujacy", "nasze_subskrypcje",
              "nasze_rekomendacje")
# ZAPISY Z TRESCI — DWIE ROZNE LICZBY, I TO JEST LEKCJA Z 28.09.2026.
# `zapisy_przypisane` = karta „new subscribers" przy notce/komentarzu/restacku
# (`zapisy_darmowe` + `zapisy_platne`): Substack przypisuje zapis TEJ pozycji.
# `zapisy_okno_artykulu` = `signups_within_1_day` artykulu (u botow pod nazwa
# `subskrypcje`): KAZDY zapis w dobie po wysylce, skadkolwiek przyszedl —
# okno czasowe, nie przypisanie (pomiar 02.09, `browser.zapisz_zrodla_ruchu`).
# Pierwsza wersja obserwatorium wziela to drugie za przypisanie, a pierwszego
# nie czytala, i oglosila „zapisy daja artykuly, notki 0" — odwrotnie niz jest.
# Wlasciciel: „z notek 0, to skad reszta subskrybentow? sprawdz, cos mi tu smierdzi".
# Pole `obserwacje` przy tresci pochodzi z typu interakcji, ktorego Substack
# dla notek nie przysyla (zawsze 0) — nie liczymy go wcale.
LICZNIKI = ("wyswietlenia", "obcy", "odwiedziny_profilu", "polubienia", "odpowiedzi", "restacki",
            "zapisy_przypisane", "zapisy_okno_artykulu")
DZIALANIA = {"notka": "notki", "artykul": "artykuly", "komentarz": "komentarze",
             "odpowiedz": "odpowiedzi", "odpowiedz_pod_artykulem": "odpowiedzi",
             "restack": "restacki", "polubienie": "polubienia", "obserwacja": "obserwacje",
             "subskrypcja": "subskrypcje"}
RODZAJE_ZMIAN = ("wdrozenie", "zmiana", "eksperyment", "konfiguracja", "recznie", "platforma",
                 "incydent")
# ZMIANY, KTORYCH SKUTEK LICZYMY. Wdrozenie to kazdy commit na serwerze — 27.09
# bylo ich jedenascie jednego dnia, wiec skutek pojedynczego wdrozenia to szum.
# Liczymy dla zmian nazwanych: eksperymentow, zmian z rejestru, PR-ow NIA,
# wpisow recznych. Aktywacje presetu NIA to kontekst (75 w trzy tygodnie).
# ZMIANY Z TEJ SAMEJ DOBY IDA RAZEM: skutku E7, E8 i E9 z 27.09 nie da sie
# rozdzielic, wiec raport nie udaje, ze umie.
ZMIANY_ZE_SKUTKIEM = ("zmiana", "eksperyment", "recznie", "platforma")
MIN_DNI_PO = 7          # krocej po zmianie raport pisze „za wczesnie"

# ZMIANY Z REJESTRU POLIGONU (`docs/POLIGON_I_PRODUKCJA.md`) — godziny z git
# reflog serwera (wdrozenie, ktore je wnioslo). Czasy przyblizone sa oznaczone.
ZASIEW = (
    {"id": "NIE-przestawienie", "kiedy": "2026-08-25T00:00:00+00:00", "konto": "NIE",
     "rodzaj": "zmiana", "opis": "Konto przestawione na tematy AI (config.DATA_PRZESTAWIENIA)",
     "czas_przyblizony": True},
    {"id": "E0", "kiedy": "2026-09-25T00:00:00+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "opis": "E0: nowy glos, notki pisze DeepSeek Flash, krotsze prompty (wdrazane recznie 25-26.09)",
     "czas_przyblizony": True},
    {"id": "E6", "kiedy": "2026-09-26T17:46:12+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "wersja": "86f615a", "opis": "E6: silnik tematow — spizarnia z kwota, styk ze zrodla, kwota notek spoza branzy"},
    {"id": "E7", "kiedy": "2026-09-27T05:24:02+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "wersja": "2f18373", "opis": "E7: temat wygasa 3 dni po dacie zrodla, tansze szukanie, +10 zrodel"},
    {"id": "E8-radar", "kiedy": "2026-09-27T06:02:59+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "wersja": "160e436", "opis": "E8: radar ciekawosci i karta glebi"},
    {"id": "E8-sledztwo", "kiedy": "2026-09-27T10:27:59+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "wersja": "8ae1485", "opis": "E8: sledztwo z trzema przeslaniami (pierwsze na produkcji 27.09 13:14)"},
    {"id": "E9", "kiedy": "2026-09-27T12:33:41+00:00", "konto": "NIE", "rodzaj": "zmiana",
     "wersja": "245bc2e", "opis": "E9: niesztandarowy wniosek przed notka, sedzia banku v2"},
    {"id": "E10", "kiedy": "2026-09-28T00:00:00+00:00", "konto": "NIE", "rodzaj": "eksperyment",
     "wersja": "b85718c", "od": "2026-09-28", "do": "2026-10-25",
     "opis": "E10: wniosek 70/30 w eksperymencie przeplatanym (ocena ok. 29.10)"},
)


def konta() -> list[dict[str, Any]]:
    """Oba konta: katalog danych, repozytorium (dla reflogu), uchwyt i siostra."""
    dom = Path.home()
    nie_uchwyt, nia_uchwyt = config.SUBSTACK_HANDLE, "nia1503032"
    return [
        {"konto": "NIE", "dane": Path(config.DATA_DIR), "uchwyt": nie_uchwyt, "siostra": nia_uchwyt,
         "repo": Path(os.environ.get("OBS_NIE_REPO", str(REPO_NIE)))},
        {"konto": "NIA", "uchwyt": nia_uchwyt, "siostra": nie_uchwyt,
         "dane": Path(os.environ.get("KARTA_NIA_DANE",
                                     str(dom / "nia-agent/agent-v2/instancje/nia-serwer"))),
         "repo": Path(os.environ.get("OBS_NIA_REPO", str(dom / "nia-agent")))},
    ]


def katalog() -> Path:
    return Path(config.DATA_DIR) / "obserwatorium"


# --- odczyt -------------------------------------------------------------------

def _jsonl(p: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with p.open(encoding="utf-8") as f:
            for linia in f:
                try:
                    w = json.loads(linia)
                except ValueError:
                    continue
                if isinstance(w, dict):
                    out.append(w)
    except OSError:
        pass
    return out


def _dzien(ts: Any) -> str:
    s = str(ts or "")
    return s[:10] if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-" else ""


def stan_na_doby(wzrost: list[dict]) -> dict[str, dict]:
    """Stan konta na koniec doby UTC (ostatni pomiar dnia)."""
    out: dict[str, dict] = {}
    for w in sorted(wzrost, key=lambda w: str(w.get("kiedy") or "")):
        d = _dzien(w.get("kiedy"))
        if d and w.get("subskrybenci") is not None:
            out[d] = {k: w[k] for k in POLA_STANU if w.get(k) is not None}
    return out


def nowi_na_doby(czytelnicy: list[dict], siostra: str = "") -> dict[str, dict]:
    """Ilu NOWYCH obserwujacych i subskrybentow pojawilo sie danego dnia.

    Nowy = uchwyt, ktorego nie bylo w zadnej wczesniejszej liscie. Pierwszy
    odczyt kazdej listy tylko zasiewa pamiec (nie wiemy, kiedy ci ludzie
    przyszli). Zwracamy wylacznie liczby — uchwyty zostaja w pamieci funkcji.
    Siostra (drugi bot) nie jest wzrostem.
    """
    widziani: dict[str, set[str]] = {"obserwujacy": set(), "subskrybenci": set()}
    zasiane: set[str] = set()
    out: dict[str, Counter] = defaultdict(Counter)
    for w in sorted(czytelnicy, key=lambda w: str(w.get("kiedy") or "")):
        d = _dzien(w.get("kiedy"))
        if not d or w.get("blad"):
            continue
        for pole in ("obserwujacy", "subskrybenci"):
            lista = w.get(pole)
            if not isinstance(lista, list):
                continue
            uchwyty = {str(x.get("uchwyt") or x.get("nazwa") or "") for x in lista
                       if isinstance(x, dict)} - {"", siostra}
            if pole in zasiane:
                out[d]["nowi_" + pole] += len(uchwyty - widziani[pole])
            zasiane.add(pole)
            widziani[pole] |= uchwyty
    return {d: dict(c) for d, c in out.items()}


def _liczniki(s: dict) -> dict[str, int]:
    inter = s.get("interakcje") or {}
    odb = s.get("odbiorcy") or {}
    odw = s.get("odwiedziny_profilu")
    if odw is None:
        odw = inter.get("Profile visit", 0)
    artykul = s.get("rodzaj") == "artykul"
    return {"wyswietlenia": int(s.get("wyswietlenia") or 0), "obcy": int(odb.get("Unconnected") or 0),
            "odwiedziny_profilu": int(odw or 0), "polubienia": int(s.get("polubienia") or 0),
            "odpowiedzi": int(s.get("odpowiedzi") or 0), "restacki": int(s.get("restacki") or 0),
            "zapisy_przypisane": int(s.get("zapisy_darmowe") or 0) + int(s.get("zapisy_platne") or 0),
            "zapisy_okno_artykulu": int(s.get("subskrypcje") or 0) if artykul else 0}


def tresci_na_doby(statystyki: list[dict]) -> dict[str, dict]:
    """Przyrosty licznikow wszystkich tresci, przypisane do doby pomiaru.

    Kazda tresc ma liczniki narastajace (wyswietlenia, obcy, odwiedziny
    profilu...). Przyrost miedzy kolejnymi pomiarami idzie do doby, w ktorej
    Substack go policzyl (`zmierzone`, gdy jest; inaczej `kiedy`). Liczymy od
    najwyzszej widzianej dotad wartosci, wiec chwilowy spadek licznika w API nie
    dubluje wyswietlen, gdy wroci. Pierwszy pomiar niesie wszystko od publikacji.
    """
    serie: dict[tuple, list] = defaultdict(list)
    for s in statystyki:
        if "wyswietlenia" not in s or not s.get("id"):
            continue
        t = str(s.get("zmierzone") or s.get("kiedy") or "")
        if _dzien(t):
            serie[(str(s.get("rodzaj") or "inne"), str(s["id"]))].append((t, s))
    out: dict[str, Counter] = defaultdict(Counter)
    for (rodzaj, _), punkty in serie.items():
        punkty.sort(key=lambda x: x[0])
        dotad = dict.fromkeys(LICZNIKI, 0)
        for t, s in punkty:
            v, d = _liczniki(s), _dzien(t)
            for k in LICZNIKI:
                if v[k] > dotad[k]:
                    przyrost = v[k] - dotad[k]
                    out[d][k] += przyrost
                    if k in ("wyswietlenia", "zapisy_przypisane"):
                        out[d]["%s_%s" % (k, rodzaj)] += przyrost
                    dotad[k] = v[k]
    return {d: dict(c) for d, c in out.items()}


def dzialania_na_doby(dziennik: list[dict], siostra: str = "") -> dict[str, dict]:
    """Udane dzialania bota na dobe, plus ile z nich trafilo w siostre."""
    out: dict[str, Counter] = defaultdict(Counter)
    for w in dziennik:
        r = DZIALANIA.get(str(w.get("rodzaj")))
        d = _dzien(w.get("kiedy"))
        if not r or not d or not w.get("udane"):
            continue
        out[d]["dz_" + r] += 1
        if siostra and siostra in "%s %s" % (w.get("komu") or "", w.get("gdzie") or ""):
            out[d]["dz_do_siostry"] += 1
    return {d: dict(c) for d, c in out.items()}


def koszt_na_doby(baza: Path) -> dict[str, float]:
    """Koszt przebiegow produkcyjnych na dobe. `immutable=1`: zadnych plikow obok bazy."""
    if not baza.exists():
        return {}
    try:
        conn = sqlite3.connect("file:%s?mode=ro&immutable=1" % baza, uri=True)
        try:
            wiersze = conn.execute(
                "SELECT substr(c.at, 1, 10), SUM(c.cost_usd) FROM calls c JOIN runs r ON r.id = c.run_id "
                "WHERE COALESCE(r.tryb, 'produkcja') = 'produkcja' GROUP BY 1").fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return {d: round(v or 0.0, 4) for d, v in wiersze if _dzien(d)}


def zrodla_zapisow(zrodla: list[dict]) -> dict[str, Any]:
    """Ostatni odczyt „skad przychodza czytelnicy i zapisy" (okno Substacka, 30 dni)."""
    for w in reversed(zrodla):
        if w.get("blad") or not isinstance(w.get("ruch"), dict):
            continue
        ruch = [{"zrodlo": r.get("source"), "kategoria": r.get("source_category"),
                 "wyswietlenia": r.get("views"), "osoby": r.get("users"), "zapisy": r.get("free_signup")}
                for r in (w["ruch"].get("rows") or []) if isinstance(r, dict)]
        def _ile(wezel):
            return next((m.get("total") for m in wezel.get("metrics") or []
                         if isinstance(m, dict) and m.get("name") == "Subscribers"), None)
        zapisy = []
        for z in ((w.get("zapisy") or {}).get("sourceMetrics") or []):
            if not isinstance(z, dict):
                continue
            # DZIECI ZRODLA: „Substack" dzieli sie na „Notes" (zapisy przypisane
            # notkom) i „Other" (profil, rekomendacje, wyszukiwarka, aplikacja).
            dzieci = [{"zrodlo": c.get("sourceName") or c.get("source"), "zapisy": _ile(c)}
                      for c in z.get("children") or [] if isinstance(c, dict) and _ile(c)]
            zapisy.append({"zrodlo": z.get("sourceName") or z.get("source"), "kategoria": z.get("category"),
                           "zapisy": _ile(z), "w_tym": dzieci})
        pods = {k: v for k, v in (w.get("podsumowanie") or {}).items() if k != "zapisy_per_notka"}
        pods["tresci_z_zapisami"] = len((w.get("podsumowanie") or {}).get("zapisy_per_notka") or {})
        return {"kiedy": w.get("kiedy"), "okno": w.get("okno"), "ruch": ruch, "zapisy": zapisy,
                "podsumowanie": pods}
    return {}


def przypisane_tresciom(zrodla: list[dict], dziennik: list[dict], statystyki: list[dict]) -> dict[str, Any]:
    """Zapisy, ktore Substack przypisal konkretnym pozycjom (panel zrodel), wg rodzaju.

    Kazdy odczyt panelu to okno 30 dni, wiec pozycja liczy sie MAKSIMUM po
    odczytach (tak samo jak `statystyki.zapisy_przypisane`). Rodzaj z dziennika
    bota (restack, notka, komentarz…); pozycji spoza dziennika bot nie
    wystawil — to np. reczne notki wlasciciela. Tylko numery tresci i liczby.
    """
    naj: dict[str, int] = {}
    for w in zrodla:
        for k, v in ((w.get("podsumowanie") or {}).get("zapisy_per_notka") or {}).items():
            try:
                naj[str(k)] = max(naj.get(str(k), 0), int(v))
            except (TypeError, ValueError):
                continue
    # RODZAJ Z DZIENNIKA BOTA; pozycja, ktora statystyki profilu znaja, a bot
    # jej nie wystawil, dostaje dopisek `_spoza_dziennika` (reczne notki
    # wlasciciela, tresci sprzed dziennika) — inaczej wlasciciel i bot
    # zlewaja sie w jedno „notka".
    rodzaj_id: dict[str, str] = {}
    for s in statystyki:
        if s.get("id"):
            rodzaj_id.setdefault(str(s["id"]), "%s_spoza_dziennika" % (s.get("rodzaj") or "tresc"))
    for w in dziennik:
        for pole in ("id", "nasz_id"):
            if w.get(pole) and w.get("rodzaj"):
                rodzaj_id[str(w[pole])] = str(w["rodzaj"])
    wg: Counter = Counter()
    for ident, ile in naj.items():
        wg[rodzaj_id.get(ident) or "spoza_dziennika"] += ile
    # OSTATNIE OKNO (30 dni) osobno: „razem" to wszystkie odczyty od poczatku,
    # a etykieta „30 dni" w raporcie musi znaczyc 30 dni.
    ostatnie = next(((w.get("podsumowanie") or {}).get("zapisy_per_notka") or {}
                     for w in reversed(zrodla) if not w.get("blad") and w.get("podsumowanie")), {})
    return {"razem": sum(naj.values()), "pozycji": len(naj), "wg_rodzaju": dict(wg.most_common()),
            "ostatnie_okno": sum(int(v) for v in ostatnie.values() if str(v).isdigit()),
            "najlepsze": sorted(naj.items(), key=lambda kv: -kv[1])[:10]}


def podsumuj_konto(k: dict) -> dict[str, dict]:
    """Wszystkie doby konta: stan, nowi, przyrosty tresci, dzialania, koszt."""
    dane = Path(k["dane"])
    czesci = (stan_na_doby(_jsonl(dane / "wzrost.jsonl")),
              nowi_na_doby(_jsonl(dane / "czytelnicy.jsonl"), k.get("siostra", "")),
              tresci_na_doby(_jsonl(dane / "statystyki.jsonl")),
              dzialania_na_doby(_jsonl(dane / "dziennik.jsonl"), k.get("siostra", "")))
    koszt = koszt_na_doby(dane / "agent-v2.db")
    dni = sorted(set().union(*czesci, koszt))
    out = {}
    for d in dni:
        w: dict[str, Any] = {}
        for c in czesci:
            w.update(c.get(d) or {})
        if d in koszt:
            w["koszt_usd"] = koszt[d]
        out[d] = w
    return out


# --- zapis ----------------------------------------------------------------------

def _zapisz_json(p: Path, dane: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dane, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def wczytaj_dni(konto: str) -> dict[str, dict]:
    try:
        return json.loads((katalog() / ("dni_%s.json" % konto)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def zbierz() -> dict[str, int]:
    """Podsumowania dni obu kont + nowe zmiany z reflogu i aktywacji. Idempotentne."""
    wynik = {}
    for k in konta():
        stare = wczytaj_dni(k["konto"])
        nowe = podsumuj_konto(k)
        # DOBY, KTORYCH JUZ NIE DA SIE POLICZYC (przyciete pliki bota), zostaja
        # z poprzedniego zapisu; policzalne liczymy od nowa, bo bot moze jeszcze
        # dopisac pomiar do wczorajszej tresci.
        polaczone = {**stare, **nowe}
        _zapisz_json(katalog() / ("dni_%s.json" % k["konto"]), polaczone)
        zrodla = _jsonl(Path(k["dane"]) / "zrodla.jsonl")
        _zapisz_json(katalog() / ("zrodla_%s.json" % k["konto"]),
                     dict(zrodla_zapisow(zrodla),
                          przypisane=przypisane_tresciom(zrodla, _jsonl(Path(k["dane"]) / "dziennik.jsonl"),
                                                         _jsonl(Path(k["dane"]) / "statystyki.jsonl"))))
        wynik[k["konto"]] = len(polaczone)
    wynik["zmiany_nowe"] = zasiej() + sum(importuj_reflog(k) for k in konta()) + importuj_aktywacje()
    return wynik


# --- dziennik zmian ---------------------------------------------------------------

def zmiany() -> list[dict]:
    return sorted(_jsonl(katalog() / "zmiany.jsonl"), key=lambda z: str(z.get("kiedy") or ""))


def dodaj_zmiane(wpis: dict) -> bool:
    """Dopisuje zmiane, gdy jej `id` jeszcze nie ma. Zwraca, czy dopisal."""
    if not wpis.get("id") or not _dzien(wpis.get("kiedy")) or wpis.get("rodzaj") not in RODZAJE_ZMIAN:
        return False
    if any(z.get("id") == wpis["id"] for z in _jsonl(katalog() / "zmiany.jsonl")):
        return False
    katalog().mkdir(parents=True, exist_ok=True)
    with (katalog() / "zmiany.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(wpis, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def zasiej() -> int:
    return sum(dodaj_zmiane(dict(z, zrodlo="rejestr")) for z in ZASIEW)


def importuj_reflog(k: dict) -> int:
    """Wdrozenia z git reflog repozytorium konta: kiedy HEAD przeszedl na nowy commit.

    Reflog serwera ma DOKLADNE godziny wdrozen (fast-forward w `wdroz.sh` NIE
    i skryptach NIA) — lepsze niz daty commitow. Kasuje sie po 90 dniach, stad
    codzienny import. Scalenie PR-a na NIA to zmiana nazwana (liczymy skutek).
    """
    repo = Path(k["repo"])
    if not (repo / ".git").exists():
        return 0
    try:
        wyjscie = subprocess.run(
            ["git", "-C", str(repo), "reflog", "--date=iso-strict",
             "--format=%gd\x1f%gs\x1f%h\x1f%s"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    wpisy = []
    for linia in wyjscie.splitlines():
        czesci = linia.split("\x1f")
        if len(czesci) != 4:
            continue
        ref, akcja, h, temat = czesci
        if not (akcja.startswith(("merge", "pull", "reset: moving to")) and "{" in ref):
            continue
        kiedy = ref[ref.index("{") + 1:ref.rindex("}")]
        if not _dzien(kiedy):
            continue
        rodzaj = "zmiana" if (k["konto"] == "NIA" and temat.startswith("Merge pull request")) else "wdrozenie"
        if akcja.startswith("reset"):
            temat = "cofniecie/przestawienie: " + temat
        wpisy.append({"id": "%s|reflog|%s|%s" % (k["konto"], h, kiedy), "kiedy": kiedy, "konto": k["konto"],
                      "rodzaj": rodzaj, "wersja": h, "opis": temat[:200], "zrodlo": "reflog"})
    return sum(dodaj_zmiane(w) for w in sorted(wpisy, key=lambda w: w["kiedy"]))


def importuj_aktywacje() -> int:
    """Aktywacje presetow NIA (`aktywacje.jsonl`) — zmiany konfiguracji z odciskiem."""
    nia = next((k for k in konta() if k["konto"] == "NIA"), None)
    if not nia:
        return 0
    ile = 0
    poprzedni = None
    for a in sorted(_jsonl(Path(nia["dane"]) / "aktywacje.jsonl"), key=lambda a: str(a.get("kiedy") or "")):
        if a.get("numer") is None or not _dzien(a.get("kiedy")):
            continue
        # TEN SAM ODCISK = ta sama konfiguracja podlaczona ponownie, nie zmiana.
        if a.get("odcisk") and a.get("odcisk") == poprzedni:
            continue
        poprzedni = a.get("odcisk")
        ile += dodaj_zmiane({"id": "NIA|aktywacja|%s" % a["numer"], "kiedy": a["kiedy"], "konto": "NIA",
                             "rodzaj": "konfiguracja", "zrodlo": "aktywacje",
                             "opis": "%s presetu %s (odcisk %s)" % (a.get("zdarzenie"), a.get("preset"),
                                                                   str(a.get("odcisk") or "")[:10])})
    return ile


# --- silnik ------------------------------------------------------------------------

def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def netto(dni: dict[str, dict], pole: str) -> dict[str, int]:
    """Zmiana stanu (np. subskrybentow) doba do doby — tylko miedzy sasiednimi dobami."""
    out = {}
    poprzedni = None
    for d in sorted(dni):
        v = dni[d].get(pole)
        if v is None:
            continue
        if poprzedni and (_d(d) - _d(poprzedni[0])).days == 1:
            out[d] = v - poprzedni[1]
        poprzedni = (d, v)
    return out


def okno(dni: dict[str, dict], do: str, ile: int) -> list[str]:
    koniec = _d(do)
    return [(koniec - timedelta(days=i)).isoformat() for i in range(ile - 1, -1, -1)]


def tempo(dni: dict[str, dict], do: str, ile: int = 7) -> dict[str, Any]:
    """Wzrost i lejek w oknie `ile` dob konczacym sie `do` (wlacznie)."""
    daty = okno(dni, do, ile)
    suma = lambda pole: sum(int((dni.get(d) or {}).get(pole) or 0) for d in daty)  # noqa: E731
    ns, no = netto(dni, "subskrybenci"), netto(dni, "obserwujacy")
    pokrycie = sum(1 for d in daty if d in ns)
    subs = sum(ns.get(d, 0) for d in daty)
    obs = sum(no.get(d, 0) for d in daty)
    wysw = suma("wyswietlenia")
    koszt = sum(float((dni.get(d) or {}).get("koszt_usd") or 0) for d in daty)
    # PUNKT STARTU TEMPA: ostatni stan przed oknem, a gdy pomiary zaczely sie
    # w srodku okna — pierwszy stan w oknie (i tempo liczone od niego).
    z_pomiarem = [d for d in sorted(dni) if d <= daty[-1] and "subskrybenci" in dni[d]]
    przed = [d for d in z_pomiarem if d < daty[0]]
    d_start = przed[-1] if przed else (z_pomiarem[0] if z_pomiarem else None)
    start = dni[d_start]["subskrybenci"] if d_start else None
    koniec = dni[z_pomiarem[-1]]["subskrybenci"] if z_pomiarem else None
    rozpietosc = (_d(z_pomiarem[-1]) - _d(d_start)).days if d_start and z_pomiarem else 0
    wynik = {"dni": ile, "dni_z_pomiarem": pokrycie, "subskrybenci_netto": subs, "obserwujacy_netto": obs,
             "nowi_subskrybenci": suma("nowi_subskrybenci"), "nowi_obserwujacy": suma("nowi_obserwujacy"),
             "wyswietlenia": wysw, "obcy": suma("obcy"), "odwiedziny_profilu": suma("odwiedziny_profilu"),
             "zapisy_przypisane_karty": suma("zapisy_przypisane"),
             "zapisy_okno_artykulu": suma("zapisy_okno_artykulu"),
             "koszt_usd": round(koszt, 2)}
    wynik["subskr_na_1000_wysw"] = round(1000 * subs / wysw, 2) if wysw else None
    wynik["obcy_udzial"] = round(suma("obcy") / wysw, 3) if wysw else None
    wynik["koszt_na_subskr"] = round(koszt / subs, 2) if subs > 0 else None
    # TEMPO = subskrybenci na tydzien (od pierwszego do ostatniego stanu w oknie)
    # i ten sam przyrost jako % SREDNIEGO poziomu w oknie. Procent od stanu
    # poczatkowego klamal dla mlodego konta: NIA zaczynala od 2 subskrybentow,
    # wiec wychodzilo 280% tygodniowo.
    poziomy = [dni[d]["subskrybenci"] for d in z_pomiarem if not d_start or d >= d_start]
    na_tydzien = (round((koniec - start) * 7 / rozpietosc, 1)
                  if start is not None and koniec is not None and rozpietosc > 0 else None)
    wynik["subskrybenci_na_tydzien"] = na_tydzien
    wynik["wzrost_proc_na_tydzien"] = (round(100 * na_tydzien / (sum(poziomy) / len(poziomy)), 1)
                                       if na_tydzien is not None and poziomy and sum(poziomy) else None)
    for dz in sorted(set(DZIALANIA.values())):
        wynik["dz_" + dz] = suma("dz_" + dz)
    wynik["dz_do_siostry"] = suma("dz_do_siostry")
    return wynik


def _srednia_dobowa(dni: dict[str, dict], daty: list[str], pole: str) -> float | None:
    if pole in ("subskrybenci", "obserwujacy"):
        n = netto(dni, pole)
        wart = [n[d] for d in daty if d in n]
    else:
        wart = [float((dni.get(d) or {}).get(pole) or 0) for d in daty if d in dni]
    return round(sum(wart) / len(wart), 3) if wart else None


def skutek(dni: dict[str, dict], dni_kontrola: dict[str, dict] | None, kiedy: str, ile: int = 14,
           dzis: str | None = None) -> dict[str, Any]:
    """Przed/po zmianie (srednie dobowe) i roznica roznic wzgledem drugiego konta.

    ROZNICA ROZNIC: (po - przed) na koncie ze zmiana minus (po - przed) na
    drugim koncie w tych samych dniach — odejmuje to, co dzialo sie z calym
    Substackiem (algorytm, sezon, dzien tygodnia). To NIE jest eksperyment:
    konta roznia sie persona i wiekiem, a zasieg zmienia sie w tle; wynik to
    wskazowka, dowodem jest eksperyment przeplatany (`eksperymenty.py`).
    """
    dzis = dzis or datetime.now(timezone.utc).date().isoformat()
    start = _d(kiedy)
    przed = [(start - timedelta(days=i)).isoformat() for i in range(ile, 0, -1)]
    po = [(start + timedelta(days=i)).isoformat() for i in range(ile)
          if (start + timedelta(days=i)).isoformat() < dzis]
    out: dict[str, Any] = {"dni_po": len(po), "dni_przed": ile}
    for pole in ("subskrybenci", "obserwujacy", "wyswietlenia", "odwiedziny_profilu", "obcy"):
        a, b = _srednia_dobowa(dni, przed, pole), _srednia_dobowa(dni, po, pole)
        wpis = {"przed": a, "po": b, "zmiana": (round(b - a, 3) if a is not None and b is not None else None)}
        if dni_kontrola is not None:
            ka, kb = _srednia_dobowa(dni_kontrola, przed, pole), _srednia_dobowa(dni_kontrola, po, pole)
            if None not in (a, b, ka, kb):
                wpis["roznica_roznic"] = round((b - a) - (kb - ka), 3)
        out[pole] = wpis
    return out


# --- raport --------------------------------------------------------------------------

def _f(v: Any, znak: bool = False) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = ("%+.2f" if znak else "%.2f") % v
        return s.rstrip("0").rstrip(".") if "." in s else s
    return ("%+d" % v) if (znak and isinstance(v, int)) else str(v)


def _zrodla(konto: str) -> dict[str, Any]:
    try:
        return json.loads((katalog() / ("zrodla_%s.json" % konto)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def raport(dni_raportu: int = 14, dzis: str | None = None) -> str:
    dzis = dzis or datetime.now(timezone.utc).date().isoformat()
    wczoraj = (_d(dzis) - timedelta(days=1)).isoformat()
    dane = {k["konto"]: wczytaj_dni(k["konto"]) for k in konta()}
    nazwy = list(dane)
    L = ["# Obserwatorium — %s" % dzis, "",
         "Dane obu kont z plikow botow (tylko odczyt). Doby UTC; ostatnia pelna doba: %s." % wczoraj, ""]
    L += ["## Stan i tempo", "", "| | " + " | ".join(nazwy) + " |", "|---|" + "---|" * len(nazwy)]
    stan = {n: dane[n].get(max((d for d in dane[n] if "subskrybenci" in dane[n][d]), default=""), {})
            for n in nazwy}
    t7 = {n: tempo(dane[n], wczoraj, 7) for n in nazwy}
    t28 = {n: tempo(dane[n], wczoraj, 28) for n in nazwy}
    wiersze = [
        ("subskrybenci (bez siostry)", lambda n: "%s (%s)" % (_f(stan[n].get("subskrybenci")),
                                                             _f((stan[n].get("subskrybenci") or 1) - 1))),
        ("obserwujacy", lambda n: _f(stan[n].get("obserwujacy"))),
        ("subskrybenci netto: 7 / 28 dni", lambda n: "%s / %s" % (_f(t7[n]["subskrybenci_netto"], True),
                                                                   _f(t28[n]["subskrybenci_netto"], True))),
        ("obserwujacy netto: 7 / 28 dni", lambda n: "%s / %s" % (_f(t7[n]["obserwujacy_netto"], True),
                                                                  _f(t28[n]["obserwujacy_netto"], True))),
        ("tempo: subskrybenci na tydzien (28 dni; % sredniego poziomu)",
         lambda n: "%s (%s%%)" % (_f(t28[n]["subskrybenci_na_tydzien"], True), _f(t28[n]["wzrost_proc_na_tydzien"]))),
        ("wyswietlenia 7 dni (udzial obcych)", lambda n: "%s (%s)" % (_f(t7[n]["wyswietlenia"]),
                                                                     _f(t7[n]["obcy_udzial"]))),
        ("odwiedziny profilu 7 dni", lambda n: _f(t7[n]["odwiedziny_profilu"])),
        ("zapisy przypisane pozycjom (panel Substacka, 30 dni)",
         lambda n: _f((_zrodla(n).get("przypisane") or {}).get("ostatnie_okno"))),
        ("subskrybenci na 1000 wyswietlen (28 dni)", lambda n: _f(t28[n]["subskr_na_1000_wysw"])),
        ("koszt 7 dni USD (na subskrybenta)", lambda n: "%s (%s)" % (_f(t7[n]["koszt_usd"]),
                                                                     _f(t7[n]["koszt_na_subskr"]))),
        ("dzialania 7 dni: notki / komentarze / restacki", lambda n: "%s / %s / %s" % (
            t7[n]["dz_notki"], t7[n]["dz_komentarze"], t7[n]["dz_restacki"])),
        ("w tym do siostry (7 dni)", lambda n: _f(t7[n]["dz_do_siostry"])),
    ]
    for etykieta, fn in wiersze:
        L.append("| %s | %s |" % (etykieta, " | ".join(fn(n) for n in nazwy)))
    L += ["", "## Ostatnie %d dob" % dni_raportu, "",
          "Kolumny: subskr. netto, obserw. netto, wyswietlenia, obcy, odwiedziny profilu, notki, komentarze, koszt.", ""]
    L += ["| doba | " + " | ".join(nazwy) + " |", "|---|" + "---|" * len(nazwy)]
    netto_s = {n: netto(dane[n], "subskrybenci") for n in nazwy}
    netto_o = {n: netto(dane[n], "obserwujacy") for n in nazwy}
    for d in okno({}, wczoraj, dni_raportu)[::-1]:
        kom = []
        for n in nazwy:
            w = dane[n].get(d) or {}
            kom.append("%s, %s, %s, %s, %s, %s, %s, %s" % (
                _f(netto_s[n].get(d), True), _f(netto_o[n].get(d), True), _f(w.get("wyswietlenia")),
                _f(w.get("obcy")), _f(w.get("odwiedziny_profilu")), _f(w.get("dz_notki")),
                _f(w.get("dz_komentarze")), _f(w.get("koszt_usd"))))
        L.append("| %s | %s |" % (d, " | ".join(kom)))
    L += ["", "## Skad przychodza subskrybenci", "",
          "Panel Substacka (okno 30 dni) i zapisy przypisane konkretnym pozycjom. „Okno doby po artykule\"",
          "to KAZDY zapis w dobie po wysylce, skadkolwiek przyszedl — nie przypisanie i nie sumuje sie z reszta.", ""]
    for n in nazwy:
        z = _zrodla(n)
        zap = sorted((x for x in z.get("zapisy") or [] if x.get("zapisy")), key=lambda x: -(x["zapisy"] or 0))
        ruch = sorted((x for x in z.get("ruch") or [] if x.get("wyswietlenia")), key=lambda x: -(x["wyswietlenia"] or 0))
        razem = sum(int(x["zapisy"] or 0) for x in zap)
        prz = z.get("przypisane") or {}
        L.append("- **%s** — panel: %d zapisow = %s" % (n, razem, ", ".join(
            "%s %s%s" % (x["zrodlo"], x["zapisy"], (" (" + ", ".join("%s %s" % (c["zrodlo"], c["zapisy"])
                                                                   for c in x.get("w_tym") or []) + ")")
                         if x.get("w_tym") else "") for x in zap) or "—"))
        L.append("  - przypisane pozycjom (wszystkie odczyty): %s zapisow przy %s pozycjach — %s" % (
            _f(prz.get("razem")), _f(prz.get("pozycji")),
            ", ".join("%s %s" % (r, v) for r, v in (prz.get("wg_rodzaju") or {}).items()) or "—"))
        L.append("  - okno doby po artykule (28 dni): %s; ruch: %s" % (
            _f(t28[n]["zapisy_okno_artykulu"]),
            ", ".join("%s %s" % (x["zrodlo"], x["wyswietlenia"]) for x in ruch[:4]) or "—"))
    L += ["", "## Wyswietlenia wg rodzaju tresci (28 dni)", ""]
    for n in nazwy:
        daty = okno({}, wczoraj, 28)
        rodzaje = sorted({k.split("_", 1)[1] for d in daty for k in (dane[n].get(d) or {})
                          if k.startswith("wyswietlenia_")})
        L.append("- **%s** — %s" % (n, "; ".join(
            "%s %d" % (r, sum(int((dane[n].get(d) or {}).get("wyswietlenia_" + r) or 0) for d in daty))
            for r in rodzaje) or "—"))
    L += ["", "## Zmiany i ich skutek", "",
          "Zmiany nazwane (rejestr, eksperymenty, PR-y NIA, wpisy reczne), zgrupowane po dobie — zmian z tej",
          "samej doby nie da sie rozdzielic. Srednie dobowe 14 dni przed i po; RR = roznica roznic wzgledem",
          "drugiego konta (wskazowka, nie dowod; dowodem jest eksperyment przeplatany).", "",
          "| doba | konto | zmiany | dni po | subskr./dobe: przed → po (RR) | wyswietlenia/dobe: przed → po (RR) |",
          "|---|---|---|---|---|---|"]
    grupy: dict[tuple, list] = defaultdict(list)
    for z in zmiany():
        if z.get("rodzaj") in ZMIANY_ZE_SKUTKIEM and z.get("konto") in dane:
            grupy[(str(z["kiedy"])[:10], z["konto"])].append(z)
    for (doba, konto), lista in sorted(grupy.items())[-15:]:
        inne = [n for n in nazwy if n != konto]
        s = skutek(dane[konto], dane[inne[0]] if inne else None, doba, 14, dzis)
        nazwy_zmian = ", ".join(
            (str(z.get("id")) if str(z.get("id", "")).startswith(("E", "NIE-")) else
             (str(z.get("opis") or "").split(" from ")[0].replace("Merge pull request ", "PR ")))[:40]
            for z in lista)

        def _komorka(p):
            if s["dni_po"] < MIN_DNI_PO:
                return "za wczesnie (%d dni po)" % s["dni_po"]
            w = s[p]
            rr = w.get("roznica_roznic")
            return "%s → %s%s" % (_f(w["przed"]), _f(w["po"]), (" (%s)" % _f(rr, True)) if rr is not None else "")
        L.append("| %s | %s | %s | %d | %s | %s |" % (doba, konto, nazwy_zmian[:120], s["dni_po"],
                                                      _komorka("subskrybenci"), _komorka("wyswietlenia")))
    ostatnie = [z for z in zmiany() if str(z.get("kiedy") or "")[:10] >= (_d(dzis) - timedelta(days=dni_raportu)).isoformat()]
    L += ["", "## Wdrozenia z ostatnich %d dob (%d)" % (dni_raportu, len(ostatnie)), ""]
    for z in ostatnie[-25:]:
        L.append("- %s %s %s: %s" % (str(z["kiedy"])[:16].replace("T", " "), z.get("konto"), z.get("rodzaj"),
                                     str(z.get("opis") or "")[:90]))
    L += ["", "## Jakosc danych", "",
          "- Kazde konto ma drugie na liscie subskrybentow (+1 w liczniku); wzajemne dzialania botow to nie wzrost.",
          "- Koszt NIA sprzed 27.09 jest zawyzony (nowe modele liczone po podwojnej stawce, wiersze nieprzeliczone).",
          "- Nowi obserwujacy/subskrybenci liczeni z list czytelnikow (pierwsze pojawienie sie uchwytu).",
          "- Przyrosty tresci przypisane do doby, w ktorej Substack je policzyl (`zmierzone`).",
          "- Przypisanie zapisow tylko z panelu zrodel i kart notek. `signups_within_1_day` artykulu to okno",
          "  czasowe (kazdy zapis w dobie po wysylce) — pierwsza wersja raportu wziela je za przypisanie.",
          "- Obserwujacy nie maja przypisania do tresci (Substack go nie podaje); widac tylko wzrost konta."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Obserwatorium obu kont (tylko odczyt danych botow).")
    sub = p.add_subparsers(dest="cmd", required=True)
    z = sub.add_parser("zbierz")
    z.add_argument("--raport", action="store_true")
    r = sub.add_parser("raport")
    r.add_argument("--dni", type=int, default=14)
    m = sub.add_parser("zmiana")
    m.add_argument("--konto", required=True, choices=("NIE", "NIA", "oba", "platforma"))
    m.add_argument("--rodzaj", required=True, choices=RODZAJE_ZMIAN)
    m.add_argument("--opis", required=True)
    m.add_argument("--id", default="")
    m.add_argument("--kiedy", default="")
    lz = sub.add_parser("zmiany")
    lz.add_argument("--dni", type=int, default=30)
    a = p.parse_args(argv)
    if a.cmd == "zbierz":
        print("zebrane:", zbierz(), flush=True)
        if a.raport:
            tekst = raport()
            (katalog() / "raport.md").write_text(tekst, encoding="utf-8")
            print(tekst)
    elif a.cmd == "raport":
        tekst = raport(a.dni)
        (katalog() / "raport.md").write_text(tekst, encoding="utf-8")
        print(tekst)
    elif a.cmd == "zmiana":
        kiedy = a.kiedy or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        ident = a.id or "%s|recznie|%s" % (a.konto, kiedy)
        ok = dodaj_zmiane({"id": ident, "kiedy": kiedy, "konto": a.konto, "rodzaj": a.rodzaj,
                           "opis": a.opis, "zrodlo": "recznie"})
        print("dopisane" if ok else "NIE dopisane (takie id juz jest albo zly wpis)")
    elif a.cmd == "zmiany":
        od = (datetime.now(timezone.utc).date() - timedelta(days=a.dni)).isoformat()
        for z in zmiany():
            if str(z.get("kiedy") or "")[:10] >= od:
                print("%s %-4s %-12s %s" % (str(z["kiedy"])[:16], z.get("konto"), z.get("rodzaj"),
                                           str(z.get("opis") or "")[:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
