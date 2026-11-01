# -*- coding: utf-8 -*-
"""R1 — REDAKTOR W CIENIU (1.11.2026): `redaktor.py`, hak w `obserwatorium.py`.

PO CO. Wlasciciel chce, zeby bot analizowal, co dziala, i na tej podstawie proponowal tematy, research, styl i dlugosc. Pierwszy krok to
CIEN: dziennik decyzji z przewidywaniami, bez wplywu na tresc. Test pilnuje, ze redaktor (1) czyta werdykty z `co_dziala.json` i nie liczy
statystyki od nowa, (2) robi propozycje tylko z grup, ktore sa „lepiej/gorzej" (mocne) albo dobrze wygladaja, ale bez przedzialu (kandydaci),
i nigdy z odniesienia ani z wymiarow model/pozycja, (3) przy za malej probie pisze „nie zmieniac polityki", (4) dopisuje przewidywanie, ktore da sie
sprawdzic, i rozlicza je po terminie (potwierdzone / chybione / bez rozstrzygniecia), (5) zapisuje wylacznie liczby zbiorcze i nazwy grup,
(6) jest idempotentny w obrebie tygodnia, (7) ma flage, limit rozmiaru i numer epoki redakcyjnej.

BEZ PYTESTA, bez sieci, bez modelu. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_redaktor.py
"""
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

KAT = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KAT)

import redaktor   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1200]))


DZIS = date(2026, 11, 2)                      # poniedzialek, tydzien ISO 2026-W45 (LITERAL)
OBS = KAT / "obserwatorium"
OBS.mkdir(parents=True, exist_ok=True)
PLIK = KAT / "redaktor_cien.jsonl"
MD = OBS / "redaktor.md"


def g(n, klastrow, wzgl, stosunek=None, przedzial=None, werdykt="za malo danych (1 i 1 niezaleznych jednostek)", za_malo=False):
    x = {"n": n, "klastrow": klastrow, "wzgl_tla": wzgl, "mediana_wysw": 11, "za_malo": za_malo, "werdykt": werdykt}
    if stosunek is not None:
        x["stosunek"] = stosunek
        x["przedzial_95"] = przedzial
    return x


def raport(notek=12, **dodatkowe):
    d = {"dzis": DZIS.isoformat(), "od": "2026-10-26", "notek_z_pomiarem": notek, "mediana_wysw": 11.0,
         "wymiary": {
             "dlugosc": {"odniesienie": "65-110", "n": 21, "grupy": {
                 "65-110": g(10, 8, 1.0),
                 "33-64": g(8, 7, 1.4, 1.5, [1.1, 2.0], "lepiej"),
                 "111+": g(3, 2, 0.6, 0.5, None, "za malo danych (2 i 8 niezaleznych jednostek)")}},
             "kategoria": {"odniesienie": "HOW_IT_WORKS", "n": 20, "grupy": {
                 "HOW_IT_WORKS": g(8, 7, 1.0),
                 "MONEY": g(4, 3, 1.6),
                 "REVEAL": g(2, 1, 1.9, za_malo=True),
                 "PEOPLE": g(9, 6, 0.5, 0.4, [0.3, 0.8], "gorzej")}},
             "pytanie": {"odniesienie": "nie", "n": 15, "grupy": {
                 "nie": g(10, 7, 1.0),
                 "tak": g(5, 4, 1.2, 1.1, [0.8, 1.5], "brak dowodu roznicy (wykrylibysmy dopiero ok. +60%)")}},
             "model": {"odniesienie": "a", "n": 10, "grupy": {"a": g(5, 5, 1.0), "b": g(5, 5, 1.5, 1.6, [1.2, 2.0], "lepiej")}}},
         "najlepsze": [{"id": "1", "wysw": 25, "poczatek": "SEKRETNY POCZATEK NOTKI Z @uchwyt i jan@example.com", "kat": "REVEAL"}]}
    d.update(dodatkowe)
    return d


def zapisz_raport(d):
    (OBS / "co_dziala.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def linie(plik=PLIK):
    return [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()] if plik.exists() else []


def uruchom(dzis=DZIS):
    return redaktor.zapisz(dzis=dzis, katalog=KAT)


print("=== 1. KLASYFIKACJA GRUP WG WERDYKTU `co_dziala` ===")
sprawdz("odniesienie: klasa odniesienie niezaleznie od werdyktu", redaktor._klasa({"werdykt": "lepiej"}, True) == "odniesienie")
sprawdz("lepiej / gorzej / brak dowodu / za malo danych",
        [redaktor._klasa({"werdykt": w}, False) for w in ("lepiej", "gorzej", "brak dowodu roznicy (..)", "za malo danych (..)", "", None)]
        == ["lepiej", "gorzej", "brak_dowodu", "za_malo", "za_malo", "za_malo"])
sygn = redaktor.sygnaly(raport())
sprawdz("sygnaly: plaska lista, id wymiar|grupa, odniesienie rozpoznane", {s["id"] for s in sygn} >= {"dlugosc|33-64", "kategoria|PEOPLE", "pytanie|tak"}
        and [s["klasa"] for s in sygn if s["id"] == "kategoria|HOW_IT_WORKS"] == ["odniesienie"], [s["id"] for s in sygn])
sprawdz("liczniki klas sumuja sie do liczby grup", sum(redaktor._liczniki(sygn).values()) == len(sygn), redaktor._liczniki(sygn))

print("=== 2. PROPOZYCJE ===")
zapisz_raport(raport())
sciezka = uruchom()
w = linie()
e = w[0] if w else {}
sprawdz("powstaje jeden rekord epoki i notatka dla czlowieka", len(w) == 1 and e.get("rodzaj") == "epoka" and sciezka == MD and MD.exists(), w)
sprawdz("tozsamosc: tydzien ISO, epoka redakcyjna 0, polityka bez zmian, schemat 1, status ok, okno z raportu",
        e["tydzien"] == "2026-W45" and e["epoka_redakcyjna"] == 0 and e["polityka"].startswith("bez_zmian") and e["schema_version"] == 1
        and e["status"] == "ok" and e["okno_od"] == "2026-10-26" and e["n_notek"] == 12 and e["dzis"] == "2026-11-02", e)
pr = {p["tresc"].split(" ")[0] + "|" + p["dowod"]["id"]: p for p in e["propozycje"]}
ids = [p["dowod"].get("id") for p in e["propozycje"]]
sprawdz("mocny sygnal „lepiej”: propozycja zwiekszenia jako EKSPERYMENT, rodzaj dlugosc", any(
    p["typ"] == "dlugosc" and p["tresc"].startswith("Zwiekszyc") and p["dowod"]["id"] == "dlugosc|33-64" and "eksperyment" in p["tresc"]
    for p in e["propozycje"]), e["propozycje"])
sprawdz("mocny sygnal „gorzej”: propozycja ograniczenia, rodzaj temat", any(
    p["typ"] == "temat" and p["tresc"].startswith("Ograniczyc") and p["dowod"]["id"] == "kategoria|PEOPLE" for p in e["propozycje"]))
sprawdz("kandydat bez przedzialu w kategorii: research (n>=3, wzgl. tla > 1); n<3 odpada (REVEAL)", any(
    p["typ"] == "research" and p["dowod"]["id"] == "kategoria|MONEY" for p in e["propozycje"]) and "kategoria|REVEAL" not in ids, ids)
sprawdz("brak dowodu roznicy ale wzgl. tla > 1: kandydat typu styl (pytanie)", any(
    p["typ"] == "styl" and p["dowod"]["id"] == "pytanie|tak" for p in e["propozycje"]), ids)
sprawdz("wymiary model i pozycja nie daja propozycji, odniesienie tez nie", not any(i.startswith(("model|", "pozycja|")) for i in ids)
        and "kategoria|HOW_IT_WORKS" not in ids and "dlugosc|65-110" not in ids, ids)
sprawdz("kandydat o wzgl. tla <= 1 (dlugosc|111+: 0,6) nie jest proponowany", "dlugosc|111+" not in ids, ids)
sprawdz("n notek >= 8 i sa mocne sygnaly: brak propozycji „polityka”", not any(p["typ"] == "polityka" for p in e["propozycje"]))
bez = raport()
for _w in bez["wymiary"].values():
    for _g in _w["grupy"].values():
        if _g.get("werdykt") in ("lepiej", "gorzej"):
            _g["werdykt"] = "brak dowodu roznicy (wykrylibysmy dopiero ok. +60%)"
pb = redaktor.propozycje(bez, redaktor.sygnaly(bez), DZIS, "2026-W45")
sprawdz("12 notek, ale zadna grupa bez werdyktu lepiej/gorzej: pierwsza propozycja „nie zmieniac polityki” z uzasadnieniem o szumie",
        pb[0]["typ"] == "polityka" and "szumie" in pb[0]["uzasadnienie"] and pb[0]["dowod"]["notek_z_pomiarem"] == 12, pb[0])
szum = raport()
szum["wymiary"] = {}
szum["wymiary"]["forma"] = {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), "male_n": g(3, 3, 1.9), "malo_klastrow": g(6, 2, 1.8),
                                                         "slaba_przewaga": g(6, 5, 1.10), "dobra": g(6, 5, 1.3)}}
ps = {p["dowod"].get("id") for p in redaktor.propozycje(szum, redaktor.sygnaly(szum), DZIS, "2026-W45")}
sprawdz("kandydat wymaga n>=4, klastrow>=3 i przewagi >=1,15 (szum odpada)", "forma|dobra" in ps and not ps & {"forma|male_n", "forma|malo_klastrow", "forma|slaba_przewaga"}, ps)
sprawdz("dowod niesie liczby z raportu (n, klastrow, wzgl. tla, stosunek, przedzial), nie nowe obliczenia", next(
    p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["dowod"] == {
        "id": "dlugosc|33-64", "n": 8, "klastrow": 7, "wzgl_tla": 1.4, "stosunek": 1.5, "przedzial_95": [1.1, 2.0]})
sprawdz("kazda propozycja ma przewidywanie z terminem 14 dni i opisem",
        all(p["przewidywanie"]["sprawdz_po"] == (DZIS + timedelta(days=14)).isoformat() and p["przewidywanie"]["opis"] for p in e["propozycje"]))
sprawdz("kierunek przewidywania: lepiej >=, gorzej <=", next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["kierunek"] == ">="
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|PEOPLE")["przewidywanie"]["kierunek"] == "<=")
sprawdz("id propozycji unikalne i z numerem tygodnia", len({p["id"] for p in e["propozycje"]}) == len(e["propozycje"])
        and all(p["id"].startswith("R-2026-W45-") for p in e["propozycje"]))
sprawdz("deterministycznie: ten sam raport = te same propozycje", redaktor.propozycje(raport(), redaktor.sygnaly(raport()), DZIS, "2026-W45")
        == redaktor.propozycje(raport(), redaktor.sygnaly(raport()), DZIS, "2026-W45"))
duzo = raport()
duzo["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), **{"g%d" % i: g(8, 7, 1.5, 1.6, [1.2, 2.0], "lepiej") for i in range(9)}}}}
sprawdz("co najwyzej 5 propozycji", len(redaktor.propozycje(duzo, redaktor.sygnaly(duzo), DZIS, "2026-W45")) == 5)
maly = raport(notek=5)
pm = redaktor.propozycje(maly, redaktor.sygnaly(maly), DZIS, "2026-W45")
sprawdz("za mala proba (5 < 8): pierwsza propozycja „nie zmieniac polityki, zbierac dane” z przewidywaniem liczby notek",
        pm[0]["typ"] == "polityka" and "Nie zmieniac polityki" in pm[0]["tresc"] and pm[0]["przewidywanie"]["typ"] == "liczba_notek"
        and pm[0]["przewidywanie"]["wartosc_odniesienia"] == 15, pm[0])

print("=== 3. PRYWATNOSC: TYLKO LICZBY ZBIORCZE I NAZWY GRUP ===")
surowy = PLIK.read_text(encoding="utf-8") + MD.read_text(encoding="utf-8")
sprawdz("brak tekstow notek, uchwytow i adresow w pliku i notatce", not any(x in surowy for x in ("SEKRETNY", "uchwyt", "example.com", "poczatek")) and "@" not in surowy, surowy[:200])

print("=== 4. IDEMPOTENTNOSC I NOWY TYDZIEN ===")
uruchom()
uruchom()
sprawdz("ten sam tydzien: nadal jedna epoka (idempotentne)", len([x for x in linie() if x["rodzaj"] == "epoka"]) == 1)
uruchom(DZIS + timedelta(days=7))
sprawdz("nowy tydzien ISO: druga epoka", [x["tydzien"] for x in linie() if x["rodzaj"] == "epoka"] == ["2026-W45", "2026-W46"])

print("=== 5. ROZLICZENIE PRZEWIDYWAN ===")
for i in (e["propozycje"]):
    pass
po = DZIS + timedelta(days=15)
sprawdz("przed terminem nic nie rozliczono", not [x for x in linie() if x["rodzaj"] == "rozliczenie"])
r2 = raport(dzis=po.isoformat())
r2["wymiary"]["dlugosc"]["grupy"]["33-64"]["wzgl_tla"] = 1.3             # przewidywanie >= 1,0: potwierdzone
r2["wymiary"]["kategoria"]["grupy"]["PEOPLE"]["wzgl_tla"] = 1.2          # przewidywanie <= 1,0: chybione
r2["wymiary"]["kategoria"]["grupy"]["MONEY"]["n"] = 2                    # za malo notek: bez rozstrzygniecia
r2["wymiary"]["pytanie"]["grupy"]["tak"]["wzgl_tla"] = 0.9               # przewidywanie >= 1,0: chybione
zapisz_raport(r2)
uruchom(po)
roz = {x["id_propozycji"]: x for x in linie() if x["rodzaj"] == "rozliczenie"}
wyn = {next(p["dowod"]["id"] for p in e["propozycje"] if p["id"] == k): v["wynik"] for k, v in roz.items()}
sprawdz("potwierdzone / chybione / bez rozstrzygniecia wg aktualnych liczb", wyn.get("dlugosc|33-64") == "potwierdzone"
        and wyn.get("kategoria|PEOPLE") == "chybione" and wyn.get("kategoria|MONEY") == "bez_rozstrzygniecia" and wyn.get("pytanie|tak") == "chybione", wyn)
sprawdz("rozliczenie niesie wartosc aktualna, epoke wpisu i epoke redakcyjna 0", all(x["epoka_redakcyjna"] == 0 and x["epoka_wpisu"] == "2026-W45"
        for x in roz.values()) and next(v for v in roz.values() if v["wynik"] == "potwierdzone")["wartosc_aktualna"] == 1.3)
n_roz = len(roz)
uruchom(po)
sprawdz("ponowny przebieg nie rozlicza drugi raz", len([x for x in linie() if x["rodzaj"] == "rozliczenie"]) == n_roz)
sprawdz("notatka mowi, ze to zapis zamiarow, i pokazuje rozliczenie", "nie decyzje wykonane" in MD.read_text(encoding="utf-8")
        and "bez rozstrzygniecia" in MD.read_text(encoding="utf-8") and "potwierdzone" in MD.read_text(encoding="utf-8"))
dm, _ = redaktor.rozlicz_przewidywanie({"typ": "liczba_notek", "wartosc_odniesienia": 15}, {"notek_z_pomiarem": 15})
sprawdz("przewidywanie liczby notek: potwierdzone przy >= celu, chybione ponizej",
        dm == "potwierdzone" and redaktor.rozlicz_przewidywanie({"typ": "liczba_notek", "wartosc_odniesienia": 15}, {"notek_z_pomiarem": 14})[0] == "chybione")
sprawdz("brak grupy w raporcie = bez rozstrzygniecia (nie zgadujemy)", redaktor.rozlicz_przewidywanie(
    {"typ": "grupa_wzgl_tla", "wymiar": "x", "grupa": "y", "kierunek": ">=", "wartosc_odniesienia": 1.0}, {"wymiary": {}})[0] == "bez_rozstrzygniecia")

print("=== 6. FLAGA, BRAK RAPORTU, USZKODZONY PLIK, ROZMIAR, UCIETY OGON ===")
KAT2 = pathlib.Path(tempfile.mkdtemp())
(KAT2 / "obserwatorium").mkdir()
sprawdz("brak raportu: None i nic nie zapisano", redaktor.zapisz(dzis=DZIS, katalog=KAT2) is None and not (KAT2 / PLIK.name).exists())
(KAT2 / "obserwatorium" / "co_dziala.json").write_text("{nie json", encoding="utf-8")
sprawdz("uszkodzony raport: None, bez wyjatku", redaktor.zapisz(dzis=DZIS, katalog=KAT2) is None)
(KAT2 / "obserwatorium" / "co_dziala.json").write_text(json.dumps({"dzis": "x"}), encoding="utf-8")
sprawdz("raport bez wymiarow: None", redaktor.zapisz(dzis=DZIS, katalog=KAT2) is None)
(KAT2 / "obserwatorium" / "co_dziala.json").write_text(json.dumps(raport()), encoding="utf-8")
config.REDAKTOR_CIEN = False
sprawdz("flaga False: None i nic nie zapisano", redaktor.zapisz(dzis=DZIS, katalog=KAT2) is None and not (KAT2 / PLIK.name).exists())
config.REDAKTOR_CIEN = True
_stare = redaktor.MAKS_BAJTOW
(KAT2 / PLIK.name).write_text("x" * 50 + "\n", encoding="utf-8")
redaktor.MAKS_BAJTOW = 10
sprawdz("limit rozmiaru: None i plik bez zmian", redaktor.zapisz(dzis=DZIS, katalog=KAT2) is None
        and (KAT2 / PLIK.name).read_text(encoding="utf-8") == "x" * 50 + "\n")
redaktor.MAKS_BAJTOW = _stare
(KAT2 / PLIK.name).write_text('{"rodzaj": "epoka", "tydzien": "1999-W01"}\n{"rodzaj": "epo', encoding="utf-8")
redaktor.zapisz(dzis=DZIS, katalog=KAT2)
t2 = (KAT2 / PLIK.name).read_text(encoding="utf-8").split("\n")
sprawdz("ucieta ostatnia linia: nowy rekord w osobnym, czytelnym wierszu", len(t2) == 4 and json.loads(t2[2])["tydzien"] == "2026-W45" and t2[3] == "", t2)

print("=== 7. WPIECIE ===")
_obs = pathlib.Path("agent-v2/obserwatorium.py").read_text(encoding="utf-8")
sprawdz("obserwatorium: hak po co_dziala, w try/except Exception, z komunikatem o awarii",
        re.search(r"import co_dziala.*?import redaktor\s+print\(\"redaktor:\", redaktor\.zapisz\(\), flush=True\)\s+except Exception as exc:\s+print\(\"redaktor: nie zapisany",
                  _obs, re.S) is not None)
_w = pathlib.Path("agent-v2/wdroz.sh").read_text(encoding="utf-8")
sprawdz("wdroz.sh importuje redaktor w kontroli „moduly wstaja”", "redaktor" in _w)
sprawdz("redaktor nie zmienia niczego, co czyta bot: nie importuje stages/run/llm do decyzji",
        not re.search(r"^\s*(from|import)\s+(run|llm|browser)\b", pathlib.Path("agent-v2/redaktor.py").read_text(encoding="utf-8"), re.M))
sprawdz("pliki sa ignorowane przez Git (data/)", all(
    __import__("subprocess").run(["git", "check-ignore", "-q", p], capture_output=True).returncode == 0
    for p in ("agent-v2/data/redaktor_cien.jsonl", "agent-v2/data/obserwatorium/redaktor.md")))

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
