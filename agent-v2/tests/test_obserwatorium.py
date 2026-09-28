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
sprawdz("nowi dnia 21.09: jeden obserwujacy, jeden subskrybent",
        nowi.get("2026-09-21") == {"nowi_obserwujacy": 1, "nowi_subskrybenci": 1}, nowi)
sprawdz("wynik to same liczby — zadnych uchwytow ani nazw", "ewa" not in json.dumps(nowi) and "Jan" not in json.dumps(nowi))

print()
print("=== 2. PRZYROSTY TRESCI ===")
stat = [{"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-20T10:00:00Z", "wyswietlenia": 10,
         "odbiorcy": {"Unconnected": 4}, "interakcje": {"Profile visit": 1}, "subskrypcje": 1},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-21T10:00:00Z", "wyswietlenia": 15,
         "odbiorcy": {"Unconnected": 6}, "interakcje": {"Profile visit": 2}, "subskrypcje": 1},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-21T20:00:00Z", "wyswietlenia": 14},
        {"rodzaj": "notka", "id": "1", "zmierzone": "2026-09-22T10:00:00Z", "wyswietlenia": 17,
         "kto_sie_zapisal": ["Tajny Czytelnik"]},
        {"rodzaj": "artykul", "id": "9", "kiedy": "2026-09-21T11:00:00+00:00", "wyswietlenia": 40}]
tr = obs.tresci_na_doby(stat)
sprawdz("pierwszy pomiar niesie wszystko od publikacji", tr["2026-09-20"]["wyswietlenia"] == 10 and tr["2026-09-20"]["obcy"] == 4, tr)
sprawdz("przyrost 21.09 = 5 wyswietlen notki + 40 artykulu, obcy +2, profil +1",
        tr["2026-09-21"]["wyswietlenia"] == 45 and tr["2026-09-21"]["wyswietlenia_artykul"] == 40
        and tr["2026-09-21"]["obcy"] == 2 and tr["2026-09-21"]["odwiedziny_profilu"] == 1, tr["2026-09-21"])
sprawdz("KONTRDOWOD: chwilowy spadek 15 -> 14 -> 17 nie dubluje (22.09 = +2, nie +3)",
        tr["2026-09-22"]["wyswietlenia"] == 2, tr["2026-09-22"])
sprawdz("zapis przypisany notce liczony raz", tr["2026-09-20"].get("subskrypcje") == 1
        and not tr["2026-09-21"].get("subskrypcje"), tr)

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
przed_nia = sorted(p.name for p in NIA.iterdir())
wynik = obs.zbierz()
sprawdz("zebrane oba konta", wynik.get("NIE") and wynik.get("NIA"), wynik)
dni_nie = obs.wczytaj_dni("NIE")
sprawdz("doba 21.09 NIE: stan, przyrosty tresci i dzialania w jednym wpisie",
        dni_nie["2026-09-21"].get("subskrybenci") == 6 and dni_nie["2026-09-21"].get("wyswietlenia") == 45
        and dni_nie["2026-09-21"].get("dz_notki") == 1, dni_nie.get("2026-09-21"))
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
dni_x = {"2026-09-%02d" % d: {"subskrybenci": 10 + max(0, d - 14) * 2, "wyswietlenia": 100} for d in range(1, 29)}
dni_y = {"2026-09-%02d" % d: {"subskrybenci": 10 + d // 3, "wyswietlenia": 100} for d in range(1, 29)}
t = obs.tempo(dni_x, "2026-09-27", 7)
sprawdz("tempo: +14 subskrybentow w 7 dniach (po 2 na dobe), na 1000 wyswietlen = 20",
        t["subskrybenci_netto"] == 14 and t["subskr_na_1000_wysw"] == 20.0, t)
s = obs.skutek(dni_x, dni_y, "2026-09-15", 7, dzis="2026-09-28")
sprawdz("skutek: przed 0/dobe, po 2/dobe, roznica roznic dodatnia",
        s["subskrybenci"]["przed"] == 0 and s["subskrybenci"]["po"] == 2
        and s["subskrybenci"]["roznica_roznic"] > 1.5, s["subskrybenci"])
sprawdz("KONTRDOWOD: wyswietlenia bez zmiany — roznica roznic 0",
        s["wyswietlenia"].get("roznica_roznic") == 0, s["wyswietlenia"])
_pozno = {"2026-09-%02d" % d: {"subskrybenci": 10 + d - 20} for d in range(20, 28)}
t = obs.tempo(_pozno, "2026-09-27", 28)
sprawdz("tempo liczone od pierwszego pomiaru, gdy pomiary ruszyly w srodku okna (+7 z 10 w 7 dni = 70%)",
        t["wzrost_proc_na_tydzien"] == 70.0, t["wzrost_proc_na_tydzien"])
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
sprawdz("KONTRDOWOD: raport bez nazw czytelnikow", "Tajny Czytelnik" not in tekst and "Ola" not in tekst)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
