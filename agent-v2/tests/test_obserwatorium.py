# -*- coding: utf-8 -*-
"""Obserwatorium obu kont (28.09.2026) — dane dnia, dziennik zmian, silnik.

PO CO. Wlasciciel: „gromadzenie danych i z NIA, i z Nothing Is Accidental —
przyrost subskrybentow, wyswietlenia, followersi; dziennik zmian z datami;
silnik, ktory mierzy statystyki". Test pilnuje, z kontrdowodami:
  1. stan konta = ostatni pomiar doby; nowi czytelnicy = pierwsze pojawienie sie
     uchwytu, pierwszy odczyt nie liczy sie jako przyrost, siostra nie jest wzrostem;
  2. przyrosty tresci: do doby pomiaru, bez dublowania przy chwilowym spadku licznika;
  3. dzialania: tylko udane, osobno te do siostry;
  4. zbierz(): oba konta, BEZ NAZW I UCHWYTOW CZYTELNIKOW w plikach obserwatorium,
     doby niepoliczalne zostaja z poprzedniego zapisu, katalog NIA nietkniety;
  5. dziennik zmian: reflog prawdziwego repozytorium git, bez duplikatow;
  6. silnik: tempo, roznica roznic wzgledem drugiego konta, raport.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

_tmp = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(_tmp / "nie")
NIA = _tmp / "nia"
NIA.mkdir()
os.environ["KARTA_NIA_DANE"] = str(NIA)
os.environ["OBS_NIE_REPO"] = str(_tmp / "repo_nie")
os.environ["OBS_NIA_REPO"] = str(_tmp / "repo_nia")

import obserwatorium as obs   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def jsonl(p, wpisy):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(w) + "\n" for w in wpisy), encoding="utf-8")


print("=== 1. STAN I NOWI CZYTELNICY ===")
st = obs.stan_na_doby([{"kiedy": "2026-09-20T05:00:00+00:00", "subskrybenci": 10, "obserwujacy": 5},
                       {"kiedy": "2026-09-20T23:00:00+00:00", "subskrybenci": 11, "obserwujacy": 6},
                       {"kiedy": "2026-09-21T12:00:00+00:00", "subskrybenci": 13, "obserwujacy": 6}])
sprawdz("stan doby = ostatni pomiar doby", st["2026-09-20"]["subskrybenci"] == 11 and st["2026-09-21"]["subskrybenci"] == 13, st)
cz = [{"kiedy": "2026-09-20T05:00:00+00:00", "obserwujacy": [{"nazwa": "Ala", "uchwyt": "ala"}],
       "subskrybenci": [{"nazwa": "Bot", "uchwyt": "siostra"}, {"nazwa": "Ola", "uchwyt": "ola"}]},
      {"kiedy": "2026-09-21T05:00:00+00:00", "obserwujacy": [{"nazwa": "Ala", "uchwyt": "ala"}, {"nazwa": "Ewa", "uchwyt": "ewa"}],
       "subskrybenci": [{"nazwa": "Bot", "uchwyt": "siostra"}, {"nazwa": "Ola", "uchwyt": "ola"}, {"nazwa": "Jan", "uchwyt": "jan"}]},
      {"kiedy": "2026-09-22T05:00:00+00:00", "blad": "HTTP 500"}]
nowi = obs.nowi_na_doby(cz, siostra="siostra")
sprawdz("KONTRDOWOD: pierwszy odczyt nie jest przyrostem", "2026-09-20" not in nowi, nowi)
sprawdz("nowi na profilu dnia 21.09: jeden obserwujacy, jeden subskrybent (nazwa mowi: z listy profilu)",
        nowi.get("2026-09-21") == {"nowi_na_profilu_obserwujacy": 1, "nowi_na_profilu_subskrybenci": 1}, nowi)
_st_prog = obs.stan_na_doby([{"kiedy": "2026-09-20T05:00:00+00:00", "subskrybenci": 27,
                              "subskrybenci_darmowi": 10, "obserwujacy": 41}])
sprawdz("KONTRDOWOD 28.09: `subskrybenci_darmowi` to prog (1/10), nie liczba — nie wchodzi do stanu",
        _st_prog["2026-09-20"] == {"subskrybenci": 27, "obserwujacy": 41}, _st_prog)
sprawdz("wynik to same liczby — zadnych uchwytow ani nazw", "ewa" not in json.dumps(nowi) and "Jan" not in json.dumps(nowi))

print()
print("=== 2. PRZYROSTY TRESCI ===")
stat = [{"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-20T10:00:00Z", "wyswietlenia": 10,
         "odbiorcy": {"Unconnected": 4}, "interakcje": {"Profile visit": 1}, "zapisy_darmowe": 1},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-21T10:00:00Z", "wyswietlenia": 15,
         "odbiorcy": {"Unconnected": 6}, "interakcje": {"Profile visit": 2}, "zapisy_darmowe": 1},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-21T20:00:00Z", "wyswietlenia": 14},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-22T10:00:00Z", "wyswietlenia": 17,
         "kto_sie_zapisal": ["Tajny Czytelnik"], "zapisy_darmowe": 1},
        {"rodzaj": "artykul", "id": "9", "kiedy": "2026-09-21T11:00:00+00:00", "wyswietlenia": 40,
         "subskrypcje": 5}]
tr = obs.tresci_na_doby(stat)
sprawdz("pierwszy pomiar niesie wszystko od publikacji", tr["2026-09-20"]["wyswietlenia"] == 10 and tr["2026-09-20"]["obcy"] == 4, tr)
sprawdz("przyrost 21.09 = 5 wyswietlen notki + 40 artykulu, obcy +2, profil +1",
        tr["2026-09-21"]["wyswietlenia"] == 45 and tr["2026-09-21"]["wyswietlenia_artykul"] == 40
        and tr["2026-09-21"]["obcy"] == 2 and tr["2026-09-21"]["odwiedziny_profilu"] == 1, tr["2026-09-21"])
sprawdz("KONTRDOWOD: chwilowy spadek 15 -> 14 -> 17 nie dubluje (22.09 = +2, nie +3)",
        tr["2026-09-22"]["wyswietlenia"] == 2, tr["2026-09-22"])
sprawdz("zapis przypisany notce (karta new subscribers) liczony raz",
        tr["2026-09-20"].get("zapisy_przypisane") == 1 and not tr["2026-09-21"].get("zapisy_przypisane")
        and not tr["2026-09-22"].get("zapisy_przypisane"), tr)
sprawdz("KONTRDOWOD 28.09: signups_within_1_day artykulu to OKNO, nie przypisanie — osobne pole",
        tr["2026-09-21"].get("zapisy_okno_artykulu") == 5 and not tr["2026-09-21"].get("zapisy_przypisane")
        and "subskrypcje" not in tr["2026-09-21"], tr["2026-09-21"])
# AUDYT 28.09: ta sama notka mierzona jako „notka" i jako „odpowiedz" (numer z `gdzie`),
# cudzy wpis mierzony jako nasza odpowiedz, nasz komentarz poza glownym licznikiem.
_stat2 = [{"rodzaj": "notka", "id": "50", "zmierzone": "2026-09-20T10:00:00Z", "wyswietlenia": 30},
          {"rodzaj": "odpowiedz", "id": "50", "zmierzone": "2026-09-21T10:00:00Z", "wyswietlenia": 32},
          {"rodzaj": "odpowiedz", "id": "60", "zmierzone": "2026-09-21T10:00:00Z", "wyswietlenia": 25},
          {"rodzaj": "komentarz", "id": "70", "zmierzone": "2026-09-21T11:00:00Z", "wyswietlenia": 4,
           "zapisy_darmowe": 1}]
_dz2 = [{"rodzaj": "komentarz", "nasz_id": "70", "udane": True},
        {"rodzaj": "odpowiedz", "gdzie": "https://substack.com/@obcy/note/c-60", "udane": True}]
_tr2 = obs.tresci_na_doby(_stat2, _dz2)
sprawdz("jedna pozycja pod dwoma rodzajami = jeden szereg (21.09: +2, nie +32)",
        _tr2["2026-09-21"].get("wyswietlenia") == 2 and _tr2["2026-09-21"].get("wyswietlenia_notka") == 2,
        _tr2)
sprawdz("KONTRDOWOD: bez scalania ta sama notka dalaby 30 + 32 = 62 wyswietlenia",
        sum(int(s["wyswietlenia"]) for s in _stat2 if s["id"] == "50") == 62)
sprawdz("cudzy numer (numer watku z `gdzie`) odrzucony",
        not _tr2["2026-09-21"].get("wyswietlenia_odpowiedz"), _tr2["2026-09-21"])
sprawdz("nasz komentarz osobno: w polu rodzaju, NIE w glownym liczniku ani glownych zapisach",
        _tr2["2026-09-21"].get("wyswietlenia_komentarz") == 4
        and _tr2["2026-09-21"].get("zapisy_przypisane_komentarz") == 1
        and not _tr2["2026-09-21"].get("zapisy_przypisane"), _tr2["2026-09-21"])
_poz2 = obs.pozycje_tresci(_stat2, _dz2)
sprawdz("pozycje: 1 pod dwoma rodzajami, 1 cudza",
        sum(1 for p in _poz2.values() if len(p["rodzaje"]) > 1) == 1
        and [i for i, p in _poz2.items() if p["cudza"]] == ["60"])
sprawdz("bez dziennika nic nie odrzucamy (wolajacy bez dziennika dostaje stare zachowanie)",
        not any(p["cudza"] for p in obs.pozycje_tresci(_stat2).values()))
_prz = obs.przypisane_tresciom(
    [{"podsumowanie": {"zapisy_per_notka": {"11": 1, "12": 2}}},
     {"podsumowanie": {"zapisy_per_notka": {"11": 3, "13": 1}}}],
    [{"rodzaj": "restack", "id": "11"}, {"rodzaj": "notka", "nasz_id": "12"}],
    [{"rodzaj": "notka", "id": "12"}])
sprawdz("przypisanie z panelu: maksimum po odczytach, rodzaj z dziennika bota, reszta spoza dziennika",
        _prz["razem"] == 6 and _prz["pozycji"] == 3
        and _prz["wg_rodzaju"] == {"restack": 3, "notka": 2, "spoza_dziennika": 1}, _prz)
_prz2 = obs.przypisane_tresciom([{"podsumowanie": {"zapisy_per_notka": {"21": 2}}}], [],
                                [{"rodzaj": "notka", "id": "21"}])
sprawdz("KONTRDOWOD: notka ze statystyk profilu, ktorej bot nie wystawil, nie udaje notki bota",
        _prz2["wg_rodzaju"] == {"notka_spoza_dziennika": 2}, _prz2)
_drzewo = {"sourceMetrics": [{"sourceName": "Substack", "children": [{"sourceName": "Notes", "children": [
    {"noteId": "31", "sourceName": "NASZE: nasza notka"},
    {"noteId": "32", "sourceName": "Ktos Obcy: jego notka"},
    {"noteId": "33", "sourceName": "Inny Obcy: tez jego"}]}]}]}
_prz3 = obs.przypisane_tresciom(
    [{"zapisy": _drzewo, "podsumowanie": {"zapisy_per_notka": {"31": 1, "32": 2, "33": 1}}}],
    [{"rodzaj": "notka", "id": "31"},
     {"rodzaj": "komentarz", "gdzie": "https://substack.com/@obcy/note/c-32", "udane": True}],
    [], podpis="NASZE")
sprawdz("cudza notka z naszym komentarzem = komentarz pod cudza notka, bez niego = cudza notka",
        _prz3["wg_rodzaju"] == {"komentarz_pod_cudza_notka": 2, "notka": 1, "cudza_notka": 1}, _prz3)
sprawdz("KONTRDOWOD: nazwisk autorow cudzych notek nie ma w wyniku",
        "Ktos Obcy" not in json.dumps(_prz3) and "Inny Obcy" not in json.dumps(_prz3))
sprawdz("ostatnie okno (30 dni) osobno od sumy wszystkich odczytow", _prz["ostatnie_okno"] == 4, _prz)

print()
print("=== 2b. JAKOSC DANYCH: UZGODNIENIA MIEDZY ZRODLAMI (audyt 28.09) ===")


def _panel(kiedy, od, razem, zrodla_zapisow):
    return {"kiedy": kiedy, "okno": {"od": od, "do": "x", "dni": 30},
            "zapisy": {"totals": [{"name": "subscribers", "total": razem}],
                       "sourceMetrics": [{"sourceName": n, "metrics": [{"name": "Subscribers", "total": v}]}
                                         for n, v in zrodla_zapisow]}}


_zr = [_panel("2026-09-25T10:00:00+00:00", "2026-08-26", 17, [("Substack", 12), ("Direct to App", 8)]),
       _panel("2026-09-27T23:46:00+00:00", "2026-08-28", 21, [("Substack", 13), ("Direct to App", 8)])]
_zg = obs.zgodnosc_panelu(_zr)
sprawdz("panel: odczyt z „razem\" 17 przy sumie zrodel 20 wykryty, zgodny nie",
        _zg == {"odczytow": 2, "niezgodnych": 1, "doby": ["2026-09-25"]}, _zg)
_wz = [{"kiedy": "2026-08-27T22:00:00+00:00", "subskrybenci": 6},
       {"kiedy": "2026-09-10T12:00:00+00:00", "subskrybenci": 15},
       {"kiedy": "2026-09-27T23:45:00+00:00", "subskrybenci": 27},
       {"kiedy": "2026-09-28T02:00:00+00:00", "subskrybenci": 28}]
_bn = obs.brutto_netto(_zr, _wz)
sprawdz("brutto 21 z panelu wobec netto +21 licznika w tym samym oknie (koniec = ostatni stan PRZED odczytem)",
        _bn.get("brutto") == 21 and _bn.get("netto") == 21 and _bn.get("roznica") == 0, _bn)
_bn2 = obs.brutto_netto(_zr, _wz[1:])
sprawdz("KONTRDOWOD: licznik bez pomiaru na poczatku okna — brak porownania, z data startu licznika",
        "brak" in _bn2 and "2026-09-10" in _bn2["brak"], _bn2)
_pl = obs.pokrycie_list([{"kiedy": "2026-09-27T23:45:00+00:00", "obserwujacy": [{"uchwyt": "a"}] * 36,
                          "subskrybenci": [{"uchwyt": "b"}] * 24}],
                        [{"kiedy": "2026-09-27T23:45:00+00:00", "subskrybenci": 27, "obserwujacy": 41}])
sprawdz("listy profilu vs licznik: 36/41 i 24/27, bez uchwytow w wyniku",
        _pl.get("obserwujacy_lista") == 36 and _pl.get("obserwujacy_licznik") == 41
        and _pl.get("subskrybenci_lista") == 24 and _pl.get("subskrybenci_licznik") == 27
        and "\"a\"" not in json.dumps(_pl), _pl)
_pk = obs.pokrycie_komentarzy(
    [{"kiedy": "2026-09-26T10:00:00+00:00", "rodzaj": "komentarz", "udane": True, "nasz_id": "1"},
     {"kiedy": "2026-09-26T11:00:00+00:00", "rodzaj": "komentarz", "udane": True, "nasz_id": "2"},
     {"kiedy": "2026-09-26T12:00:00+00:00", "rodzaj": "odpowiedz", "udane": True},
     {"kiedy": "2026-09-10T12:00:00+00:00", "rodzaj": "komentarz", "udane": True, "nasz_id": "3"}],
    [{"id": "1", "wyswietlenia": 3}, {"id": "3", "wyswietlenia": 1}], dzis="2026-09-28")
sprawdz("komentarze z 7 dob: 3 wystawione, 1 bez numeru, 1 zmierzony (stary spoza okna sie nie liczy)",
        _pk == {"od": "2026-09-21", "wystawione": 3, "bez_numeru": 1, "zmierzone": 1}, _pk)

print()
print("=== 3. DZIALANIA ===")
dz = obs.dzialania_na_doby([
    {"kiedy": "2026-09-21T10:00:00+00:00", "rodzaj": "komentarz", "udane": True, "komu": "Duze Konto"},
    {"kiedy": "2026-09-21T11:00:00+00:00", "rodzaj": "komentarz", "udane": True, "gdzie": "https://substack.com/@siostra/note/1"},
    {"kiedy": "2026-09-21T12:00:00+00:00", "rodzaj": "komentarz", "udane": False},
    {"kiedy": "2026-09-21T13:00:00+00:00", "rodzaj": "notka", "udane": True},
    {"kiedy": "2026-09-21T14:00:00+00:00", "rodzaj": "skutek", "udane": True}], siostra="siostra")
sprawdz("udane komentarze 2, notka 1, do siostry 1, skutek pominiety",
        dz.get("2026-09-21") == {"dz_komentarze": 2, "dz_do_siostry": 1, "dz_notki": 1}, dz)

print()
print("=== 4. ZBIERZ: OBA KONTA, BEZ DANYCH OSOBOWYCH ===")
for katalog_konta, subs in ((config.DATA_DIR, (5, 6, 8)), (NIA, (3, 3, 4))):
    jsonl(katalog_konta / "wzrost.jsonl", [
        {"kiedy": "2026-09-%02dT23:00:00+00:00" % (20 + i), "subskrybenci": s, "obserwujacy": s * 2}
        for i, s in enumerate(subs)])
    jsonl(katalog_konta / "czytelnicy.jsonl", cz)
    jsonl(katalog_konta / "statystyki.jsonl", stat)
    jsonl(katalog_konta / "dziennik.jsonl", [{"kiedy": "2026-09-21T10:00:00+00:00", "rodzaj": "notka", "udane": True}])
    jsonl(katalog_konta / "zrodla.jsonl", [{"kiedy": "2026-09-22T00:00:00+00:00", "okno": {"dni": 30},
                                           "ruch": {"rows": [{"source": "substack app", "views": 30, "users": 9}]},
                                           "zapisy": {"sourceMetrics": [{"sourceName": "Substack",
                                                                         "metrics": [{"name": "Subscribers", "total": 3}]}]},
                                           "podsumowanie": {"zapisy_per_notka": {"1": 2}}}])
for katalog_konta in (config.DATA_DIR, NIA):
    _c = sqlite3.connect(str(katalog_konta / "agent-v2.db"))
    _c.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, tryb TEXT)")
    _c.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY, run_id INTEGER, at TEXT, purpose TEXT, cost_usd REAL)")
    _c.executemany("INSERT INTO runs (id, tryb) VALUES (?, ?)", [(1, "produkcja"), (2, "test"), (3, None)])
    # produkcja 0,50 + przebieg bez trybu 0,25 (= produkcja), test 0,10,
    # BEZ przebiegu: pusty run_id 0,20 i wiszacy 0,05 — pierwsza wersja gubila te dwa.
    _c.executemany("INSERT INTO calls (run_id, at, purpose, cost_usd) VALUES (?, ?, ?, ?)",
                   [(1, "2026-09-21T10:00:00", "note", 0.5), (3, "2026-09-21T11:00:00", "note", 0.25),
                    (2, "2026-09-21T12:00:00", "note", 0.1), (None, "2026-09-21T13:00:00", "note", 0.2),
                    (99, "2026-09-21T14:00:00", "note", 0.05)])
    _c.commit()
    _c.close()
przed_nia = sorted(p.name for p in NIA.iterdir())
wynik = obs.zbierz()
sprawdz("zebrane oba konta", wynik.get("NIE") and wynik.get("NIA"), wynik)
dni_nie = obs.wczytaj_dni("NIE")
sprawdz("doba 21.09 NIE: stan, przyrosty tresci i dzialania w jednym wpisie",
        dni_nie["2026-09-21"].get("subskrybenci") == 6 and dni_nie["2026-09-21"].get("wyswietlenia") == 45
        and dni_nie["2026-09-21"].get("dz_notki") == 1, dni_nie.get("2026-09-21"))
sprawdz("koszt w trzech czesciach: produkcja 0,75 / test 0,10 / bez przebiegu 0,25",
        (dni_nie["2026-09-21"].get("koszt_usd"), dni_nie["2026-09-21"].get("koszt_test_usd"),
         dni_nie["2026-09-21"].get("koszt_bez_przebiegu_usd")) == (0.75, 0.1, 0.25), dni_nie.get("2026-09-21"))
_jak = json.loads((config.DATA_DIR / "obserwatorium" / "jakosc_NIE.json").read_text(encoding="utf-8"))
sprawdz("plik jakosci zapisany: panel, brutto/netto, listy, komentarze, pozycje",
        {"panel", "brutto_netto", "listy", "komentarze", "pozycje"} <= set(_jak), sorted(_jak))
_wszystko = "".join(p.read_text(encoding="utf-8") for p in (config.DATA_DIR / "obserwatorium").iterdir())
sprawdz("KONTRDOWOD: w plikach obserwatorium nie ma nazw ani uchwytow czytelnikow",
        not any(x in _wszystko for x in ("Tajny Czytelnik", "\"ewa\"", "Ola", "\"jan\"")))
sprawdz("KONTRDOWOD: katalog NIA nietkniety (zadnych nowych plikow)", sorted(p.name for p in NIA.iterdir()) == przed_nia,
        sorted(p.name for p in NIA.iterdir()))
_dni = obs.wczytaj_dni("NIE")
_dni["2026-08-01"] = {"subskrybenci": 1}
obs._zapisz_json(config.DATA_DIR / "obserwatorium" / "dni_NIE.json", _dni)
obs.zbierz()
sprawdz("doby niepoliczalne z plikow bota zostaja z poprzedniego zapisu",
        obs.wczytaj_dni("NIE").get("2026-08-01") == {"subskrybenci": 1})

print()
print("=== 5. DZIENNIK ZMIAN Z REFLOGU ===")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


for repo in (_tmp / "repo_nie", _tmp / "repo_nia"):
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "a.txt").write_text("1")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "pierwszy")
    git(repo, "checkout", "-q", "-b", "gal")
    (repo / "a.txt").write_text("2")
    git(repo, "commit", "-q", "-am", "Merge pull request #7 from x/y" if "nia" in repo.name else "Zmiana tematow")
    git(repo, "checkout", "-q", "-")
    git(repo, "merge", "-q", "--ff-only", "gal")
ile = obs.zbierz()["zmiany_nowe"]
zm = obs.zmiany()
wdr = [z for z in zm if z.get("zrodlo") == "reflog"]
sprawdz("wdrozenie (fast-forward) z reflogu obu repozytoriow", {z["konto"] for z in wdr} == {"NIE", "NIA"}, wdr)
sprawdz("scalenie PR-a na NIA to zmiana nazwana, wdrozenie NIE to wdrozenie",
        any(z["konto"] == "NIA" and z["rodzaj"] == "zmiana" for z in wdr)
        and all(z["rodzaj"] == "wdrozenie" for z in wdr if z["konto"] == "NIE"), wdr)
sprawdz("rejestr zasiany (E6-E10 z godzinami wdrozen)", {"E6", "E9", "E10"} <= {z.get("id") for z in zm})
sprawdz("KONTRDOWOD: drugi import nie dubluje", obs.zbierz()["zmiany_nowe"] == 0 and len(obs.zmiany()) == len(zm))
sprawdz("reczny wpis przez CLI", obs.main(["zmiana", "--konto", "NIE", "--rodzaj", "recznie",
                                          "--opis", "wlasciciel przypial notke", "--kiedy",
                                          "2026-09-21T09:00:00+00:00"]) == 0
        and any(z.get("opis") == "wlasciciel przypial notke" for z in obs.zmiany()))
sprawdz("KONTRDOWOD: rodzaj spoza listy odrzucony",
        not obs.dodaj_zmiane({"id": "x", "kiedy": "2026-09-21", "rodzaj": "cokolwiek"}))
jsonl(NIA / "aktywacje.jsonl", [
    {"numer": 1, "kiedy": "2026-09-10T04:00:00+00:00", "zdarzenie": "podlacz", "preset": "p", "odcisk": "aaa"},
    {"numer": 2, "kiedy": "2026-09-10T05:00:00+00:00", "zdarzenie": "podlacz", "preset": "p", "odcisk": "aaa"},
    {"numer": 3, "kiedy": "2026-09-11T05:00:00+00:00", "zdarzenie": "podlacz", "preset": "p", "odcisk": "bbb"}])
obs.importuj_aktywacje()
_akt = [z for z in obs.zmiany() if z.get("zrodlo") == "aktywacje"]
sprawdz("KONTRDOWOD: ta sama konfiguracja podlaczona ponownie nie jest zmiana (2 z 3 aktywacji)",
        sorted(z["id"] for z in _akt) == ["NIA|aktywacja|1", "NIA|aktywacja|3"], _akt)

print()
print("=== 6. SILNIK ===")
dni_x = {"2026-09-%02d" % d: {"subskrybenci": 10 + max(0, d - 14) * 2, "wyswietlenia": 100, "pomiar_tresci": 1}
         for d in range(1, 29)}
dni_y = {"2026-09-%02d" % d: {"subskrybenci": 10 + d // 3, "wyswietlenia": 100, "pomiar_tresci": 1}
         for d in range(1, 29)}
t = obs.tempo(dni_x, "2026-09-27", 7)
sprawdz("tempo: +14 subskrybentow w 7 dniach (po 2 na dobe), na 1000 wyswietlen = 20",
        t["subskrybenci_netto"] == 14 and t["subskr_na_1000_wysw"] == 20.0, t)
s = obs.skutek(dni_x, dni_y, "2026-09-15", 7, dzis="2026-09-28")
sprawdz("skutek: przed 0/dobe, po 2/dobe, roznica roznic dodatnia",
        s["subskrybenci"]["przed"] == 0 and s["subskrybenci"]["po"] == 2
        and s["subskrybenci"]["roznica_roznic"] > 1.5, s["subskrybenci"])
sprawdz("KONTRDOWOD: wyswietlenia bez zmiany — roznica roznic 0",
        s["wyswietlenia"].get("roznica_roznic") == 0, s["wyswietlenia"])
# AUDYT 28.09: konto mierzone od 7.09, zmiana 7.09 — doby „przed" bez pomiaru to NIE zera.
_mlode_dni = {"2026-09-%02d" % d: ({"wyswietlenia": 230, "pomiar_tresci": 1} if d >= 7 else {"koszt_usd": 0.5})
              for d in range(1, 28)}
_s_mlode = obs.skutek(_mlode_dni, dni_y, "2026-09-07", 14, dzis="2026-09-28")
sprawdz("KONTRDOWOD: doby sprzed pierwszego pomiaru nie sa zerami — przed = brak, bez roznicy roznic",
        _s_mlode["wyswietlenia"]["przed"] is None and _s_mlode["wyswietlenia"]["dni_przed_z_danymi"] == 0
        and "roznica_roznic" not in _s_mlode["wyswietlenia"], _s_mlode["wyswietlenia"])
_s_mlode2 = obs.skutek(_mlode_dni, dni_y, "2026-09-09", 14, dzis="2026-09-28")
sprawdz("dwie doby danych przed zmiana: srednia jest, ale roznicy roznic nie liczymy",
        _s_mlode2["wyswietlenia"]["dni_przed_z_danymi"] == 2 and "roznica_roznic" not in _s_mlode2["wyswietlenia"],
        _s_mlode2["wyswietlenia"])
_pp = obs.pokrycie_pomiaru([{"id": "1", "wyswietlenia": 5, "kiedy": "2026-09-10T01:00:00+00:00",
                             "zmierzone": "2026-09-03T10:00:00Z"},
                            {"id": "1", "wyswietlenia": 9, "kiedy": "2026-09-12T01:00:00+00:00"}])
sprawdz("pokrycie pomiaru: doby 10-12.09 ciagiem, a doba `zmierzone` sprzed pierwszego odczytu nie",
        sorted(_pp) == ["2026-09-10", "2026-09-11", "2026-09-12"], sorted(_pp))
_pozno = {"2026-09-%02d" % d: {"subskrybenci": 10 + d - 20} for d in range(20, 28)}
t = obs.tempo(_pozno, "2026-09-27", 28)
sprawdz("tempo od pierwszego pomiaru, gdy pomiary ruszyly w srodku okna: +7/tydzien, 51,9% sredniego poziomu",
        t["subskrybenci_na_tydzien"] == 7.0 and t["wzrost_proc_na_tydzien"] == 51.9,
        (t["subskrybenci_na_tydzien"], t["wzrost_proc_na_tydzien"]))
_mlode = {"2026-09-%02d" % d: {"subskrybenci": s} for d, s in ((7, 2), (14, 8), (21, 13), (27, 19))}
_mlode.update({"2026-09-%02d" % d: {"subskrybenci": 2 + (d - 7) * 17 // 20} for d in range(8, 27) if "2026-09-%02d" % d not in _mlode})
t = obs.tempo(_mlode, "2026-09-27", 28)
sprawdz("KONTRDOWOD: mlode konto (2 -> 19) nie wychodzi 280% tygodniowo — procent od sredniego poziomu",
        t["subskrybenci_na_tydzien"] == 6.0 and t["wzrost_proc_na_tydzien"] < 80, t["wzrost_proc_na_tydzien"])
for zid in ("E91", "E92"):
    obs.dodaj_zmiane({"id": zid, "kiedy": "2026-09-21T0%d:00:00+00:00" % (1 if zid == "E91" else 2),
                      "konto": "NIE", "rodzaj": "zmiana", "opis": "test " + zid})
tekst = obs.raport(14, dzis="2026-09-23")
_wiersze_21 = [w for w in tekst.splitlines() if w.startswith("| 2026-09-21 | NIE |")]
sprawdz("dwie zmiany z tej samej doby = jeden wiersz, a przy 2 dniach po — za wczesnie",
        len(_wiersze_21) == 1 and "E91" in _wiersze_21[0] and "E92" in _wiersze_21[0]
        and "za wczesnie" in _wiersze_21[0], _wiersze_21)
sprawdz("raport ma oba konta, zmiany i jakosc danych",
        "| NIE | NIA |" in tekst and "Zmiany i ich skutek" in tekst and "Jakosc danych" in tekst, tekst[:400])
sprawdz("jakosc danych z liczbami: koszt w trzech czesciach i uzgodnienie panelu",
        "koszt 28 dni USD: produkcja / test / bez przebiegu" in tekst
        and "„razem\" != suma zrodel" in tekst, tekst[tekst.find("## Jakosc danych"):][:900])
sprawdz("KONTRDOWOD: raport bez nazw czytelnikow", "Tajny Czytelnik" not in tekst and "Ola" not in tekst)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
