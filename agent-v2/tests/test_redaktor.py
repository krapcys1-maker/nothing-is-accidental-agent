# -*- coding: utf-8 -*-
"""R1 — REDAKTOR W CIENIU (1.11.2026): `redaktor.py`, hak w `obserwatorium.py`.

PO CO. Wlasciciel chce, zeby bot analizowal, co dziala, i na tej podstawie proponowal tematy, research, styl i dlugosc. Pierwszy krok to
CIEN: dziennik decyzji z przewidywaniami, bez wplywu na tresc. Test pilnuje, ze redaktor (1) czyta werdykty z `co_dziala.json` i nie liczy
statystyki od nowa, (2) robi propozycje z grup „lepiej/gorzej” (mocne) albo z kandydatow, ktorzy spelniaja progi (n, niezalezne jednostki,
przewaga, wykrywalny efekt, dluzsze okno dla dnia i pory), nigdy z odniesienia ani z wymiarow model/pozycja, (3) przy braku mocnych sygnalow
pisze „nie zmieniac polityki”, (4) dopisuje przewidywanie, ktore da sie sprawdzic z kolejnych raportow, na TEJ SAMEJ osi co dowod, i rozlicza je
po terminie NA NOWYCH NOTKACH (potwierdzone / chybione / bez rozstrzygniecia), (5) nie powtarza tej samej grupy, dopoki poprzednie
przewidywanie nie jest rozliczone, (6) zapisuje wylacznie liczby zbiorcze i nazwy grup, (7) nie pracuje na nieswiezym raporcie, (8) jest
idempotentny w obrebie tygodnia ISO (takze na granicy roku), ma flage, limit rozmiaru, numer epoki redakcyjnej i statusy eksperymentow.

BEZ PYTESTA, bez sieci, bez modelu. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_redaktor.py
"""
import contextlib
import io
import json
import math
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


DZIS = date(2026, 11, 16)                     # poniedzialek, tydzien ISO 2026-W47 (LITERAL); okno raportu od 26.10 ma 21 dni
OBS = KAT / "obserwatorium"
OBS.mkdir(parents=True, exist_ok=True)
PLIK = KAT / "redaktor_cien.jsonl"
MD = OBS / "redaktor.md"
SUFIKS = " — OSTROZNIE: grupy z roznych okresow"


def g(n, klastrow, wzgl, stosunek=None, przedzial=None, werdykt="za malo danych (1 i 1 niezaleznych jednostek)", za_malo=False, wykrywalny=None):
    x = {"n": n, "klastrow": klastrow, "wzgl_tla": wzgl, "mediana_wysw": 11, "za_malo": za_malo, "werdykt": werdykt}
    if stosunek is not None:
        x["stosunek"] = stosunek
        x["przedzial_95"] = przedzial
    if wykrywalny is not None:
        x["wykrywalny_efekt"] = wykrywalny
    return x


def raport(dzis=DZIS, notek=12, od="2026-10-26", **dodatkowe):
    d = {"dzis": dzis.isoformat(), "od": od, "notek_z_pomiarem": notek, "mediana_wysw": 11.0,
         "wymiary": {
             "dlugosc": {"odniesienie": "65-110", "n": 21, "grupy": {
                 "65-110": g(10, 8, 1.0),
                 "33-64": g(8, 7, 1.4, 1.5, [1.1, 2.0], "lepiej" + SUFIKS),
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
         "eksperymenty": {"dlugosc_serii": {"status": "trwa", "od": "2026-10-29"}, "pisarz": {"status": "zakonczony", "od": "2026-09-28"}},
         "najlepsze": [{"id": "1", "wysw": 25, "poczatek": "SEKRETNY POCZATEK NOTKI Z @uchwyt i jan@example.com", "kat": "REVEAL"}]}
    d.update(dodatkowe)
    return d


def zapisz_raport(d, katalog=KAT):
    (katalog / "obserwatorium").mkdir(parents=True, exist_ok=True)
    (katalog / "obserwatorium" / "co_dziala.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def linie(plik=PLIK):
    return [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()] if plik.exists() else []


def uruchom(dzis=DZIS, katalog=KAT):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        w = redaktor.zapisz(dzis=dzis, katalog=katalog)
    return w, log.getvalue()


def prop(d, dzis=DZIS, tydzien="2026-W47", otwarte=None):
    return redaktor.propozycje(d, redaktor.sygnaly(d), dzis, tydzien, otwarte)[0]


print("=== 1. KLASYFIKACJA GRUP WG WERDYKTU `co_dziala` ===")
sprawdz("odniesienie: klasa odniesienie niezaleznie od werdyktu", redaktor._klasa({"werdykt": "lepiej"}, True) == "odniesienie")
sprawdz("lepiej / gorzej / brak dowodu / za malo danych (takze z sufiksem OSTROZNIE)",
        [redaktor._klasa({"werdykt": w}, False) for w in ("lepiej", "gorzej", "brak dowodu roznicy (..)", "za malo danych (..)", "", None, "lepiej" + SUFIKS)]
        == ["lepiej", "gorzej", "brak_dowodu", "za_malo", "za_malo", "za_malo", "lepiej"])
sygn = redaktor.sygnaly(raport())
sprawdz("sygnaly: plaska lista, id wymiar|grupa, odniesienie rozpoznane", {s["id"] for s in sygn} >= {"dlugosc|33-64", "kategoria|PEOPLE", "pytanie|tak"}
        and [s["klasa"] for s in sygn if s["id"] == "kategoria|HOW_IT_WORKS"] == ["odniesienie"], [s["id"] for s in sygn])
sprawdz("sygnaly niosa nazwe odniesienia i flage OSTROZNIE (tylko dla werdyktu z sufiksem)",
        next(s for s in sygn if s["id"] == "dlugosc|33-64")["ostroznie"] is True and next(s for s in sygn if s["id"] == "dlugosc|33-64")["odniesienie"] == "65-110"
        and next(s for s in sygn if s["id"] == "kategoria|PEOPLE")["ostroznie"] is False)
sprawdz("liczniki klas sumuja sie do liczby grup", sum(redaktor._liczniki(sygn).values()) == len(sygn), redaktor._liczniki(sygn))

print("=== 2. PROPOZYCJE ===")
zapisz_raport(raport())
sciezka, log = uruchom()
w = linie()
e = w[0] if w else {}
sprawdz("powstaje jeden rekord epoki i notatka dla czlowieka", len(w) == 1 and e.get("rodzaj") == "epoka" and sciezka == MD and MD.exists(), (w, log))
sprawdz("tozsamosc: tydzien ISO, epoka redakcyjna 0, polityka bez zmian, schemat 1, status ok, okno z raportu, raport_dzis",
        e["tydzien"] == "2026-W47" and e["epoka_redakcyjna"] == 0 and e["polityka"].startswith("bez_zmian") and e["schema_version"] == 1
        and e["status"] == "ok" and e["okno_od"] == "2026-10-26" and e["n_notek"] == 12 and e["dzis"] == "2026-11-16"
        and e["raport_dzis"] == "2026-11-16", e)
sprawdz("epoka niesie statusy eksperymentow (zmienne dla analizy) i licznik obcietych", e["eksperymenty"] == {"dlugosc_serii": "trwa", "pisarz": "zakonczony"}
        and e["obcieto"] == 0, (e.get("eksperymenty"), e.get("obcieto")))
sprawdz("kod: skrot commita jest tekstem (bez importu stages)", isinstance(e["code_commit"], str))
ids = [p["dowod"].get("id") for p in e["propozycje"]]
sprawdz("mocny sygnal „lepiej” (z sufiksem OSTROZNIE): propozycja zwiekszenia jako EKSPERYMENT, rodzaj dlugosc, z zastrzezeniem w uzasadnieniu", any(
    p["typ"] == "dlugosc" and p["tresc"].startswith("Zwiekszyc") and p["dowod"]["id"] == "dlugosc|33-64" and "eksperyment" in p["tresc"]
    and "z roznych okresow" in p["uzasadnienie"] and p["dowod"]["ostroznie"] is True for p in e["propozycje"]), e["propozycje"])
sprawdz("mocny sygnal „gorzej”: propozycja ograniczenia, rodzaj temat, bez zastrzezenia", any(
    p["typ"] == "temat" and p["tresc"].startswith("Ograniczyc") and p["dowod"]["id"] == "kategoria|PEOPLE" and "z roznych okresow" not in p["uzasadnienie"]
    for p in e["propozycje"]))
sprawdz("uzasadnienie mocnego sygnalu mowi, wzgledem czego jest przedzial (grupa odniesienia)", any(
    "odniesienia „65-110”" in p["uzasadnienie"] for p in e["propozycje"] if p["dowod"].get("id") == "dlugosc|33-64"))
sprawdz("kandydat bez przedzialu w kategorii: research (n>=4, wzgl. tla >= 1,15); n<4 odpada (REVEAL)", any(
    p["typ"] == "research" and p["dowod"]["id"] == "kategoria|MONEY" for p in e["propozycje"]) and "kategoria|REVEAL" not in ids, ids)
sprawdz("kandydat z klasa „brak dowodu”: uzasadnienie mowi „przedzial obejmuje 1”, nie „bez przedzialu”", any(
    p["typ"] == "styl" and p["dowod"]["id"] == "pytanie|tak" and "przedzial obejmuje 1" in p["uzasadnienie"] for p in e["propozycje"]), e["propozycje"])
sprawdz("wymiary model i pozycja nie daja propozycji, odniesienie tez nie", not any(i.startswith(("model|", "pozycja|")) for i in ids if i)
        and "kategoria|HOW_IT_WORKS" not in ids and "dlugosc|65-110" not in ids, ids)
sprawdz("kandydat o wzgl. tla <= 1 (dlugosc|111+: 0,6) nie jest proponowany", "dlugosc|111+" not in ids, ids)
sprawdz("mocne sygnaly sa: brak propozycji „polityka”", not any(p["typ"] == "polityka" for p in e["propozycje"]))
sprawdz("dowod niesie liczby z raportu, nazwe odniesienia i flage ostroznie", next(
    p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["dowod"] == {
        "id": "dlugosc|33-64", "n": 8, "klastrow": 7, "wzgl_tla": 1.4, "stosunek": 1.5, "przedzial_95": [1.1, 2.0], "odniesienie": "65-110", "ostroznie": True})
sprawdz("przewidywanie mocnego sygnalu jest na tej samej osi co dowod: werdykt wzgledem odniesienia (typ grupa_werdykt, oczekiwana klasa)",
        next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["typ"] == "grupa_werdykt"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["oczekiwana"] == "lepiej"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|PEOPLE")["przewidywanie"]["oczekiwana"] == "gorzej"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["odniesienie"] == "65-110")
sprawdz("przewidywanie kandydata dotyczy NOWYCH notek (n i wzgl. tla z chwili zapisu, min. 4 nowe)", next(
    p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|MONEY")["przewidywanie"] == {
        "typ": "grupa_nowe_notki", "wymiar": "kategoria", "grupa": "MONEY", "n_przy_zapisie": 4, "wzgl_przy_zapisie": 1.6, "wartosc_odniesienia": 1.0,
        "min_nowych": 4, "sprawdz_po": "2026-11-30", "opis": next(p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|MONEY")["przewidywanie"]["opis"]})
sprawdz("kazda propozycja ma termin 14 dni i opis przewidywania", all(
    p["przewidywanie"]["sprawdz_po"] == (DZIS + timedelta(days=14)).isoformat() and p["przewidywanie"]["opis"] for p in e["propozycje"]))
sprawdz("id propozycji unikalne i z numerem tygodnia", len({p["id"] for p in e["propozycje"]}) == len(e["propozycje"])
        and all(p["id"].startswith("R-2026-W47-") for p in e["propozycje"]))
sprawdz("deterministycznie: ten sam raport = te same propozycje", prop(raport()) == prop(raport()))
duzo = raport()
duzo["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), **{"g%d" % i: g(8, 7, 1.5, 1.2 + i / 10, [1.2, 2.0], "lepiej") for i in range(9)}}}}
pr_duzo, obc = redaktor.propozycje(duzo, redaktor.sygnaly(duzo), DZIS, "2026-W47")
sprawdz("co najwyzej 5 propozycji; obciecie idzie po sile dowodu (najwiekszy stosunek najpierw), nie alfabetycznie, i jest policzone",
        len(pr_duzo) == 5 and obc == 4 and pr_duzo[0]["dowod"]["id"] == "forma|g8" and pr_duzo[4]["dowod"]["id"] == "forma|g4", ([p["dowod"]["id"] for p in pr_duzo], obc))
maly = raport(notek=5)
pm = prop(maly)
sprawdz("za mala proba (5 < 8): pierwsza propozycja „nie zmieniac polityki, zbierac dane” z przewidywaniem silnych sygnalow (nie trywialnym licznikiem notek)",
        pm[0]["typ"] == "polityka" and "Nie zmieniac polityki" in pm[0]["tresc"] and pm[0]["przewidywanie"]["typ"] == "silne_sygnaly", pm[0])
bez = raport()
for _w in bez["wymiary"].values():
    for _g in _w["grupy"].values():
        if str(_g.get("werdykt")).startswith(("lepiej", "gorzej")):
            _g["werdykt"] = "brak dowodu roznicy (wykrylibysmy dopiero ok. +60%)"
pb = prop(bez)
sprawdz("12 notek, ale zadna grupa bez werdyktu lepiej/gorzej: pierwsza propozycja „nie zmieniac polityki” z uzasadnieniem o szumie",
        pb[0]["typ"] == "polityka" and "szumie" in pb[0]["uzasadnienie"] and pb[0]["dowod"]["notek_z_pomiarem"] == 12, pb[0])
tylko_model = raport()
for _t in ("dlugosc", "kategoria", "pytanie"):
    del tylko_model["wymiary"][_t]
pt = prop(tylko_model)
sprawdz("jedyny mocny sygnal w wymiarze „model” (z ktorego nie robimy propozycji): to NIE jest mocny sygnal, wiec „nie zmieniac polityki”, a nie pusta lista",
        len(pt) >= 1 and pt[0]["typ"] == "polityka", pt)
szum = raport()
szum["wymiary"] = {}
szum["wymiary"]["forma"] = {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), "male_n": g(3, 3, 1.9), "malo_klastrow": g(6, 2, 1.8),
                                                         "slaba_przewaga": g(6, 5, 1.10), "dobra": g(6, 5, 1.3),
                                                         "za_maly_efekt": g(6, 5, 1.3, wykrywalny=0.8)}}
ps = {p["dowod"].get("id") for p in prop(szum)}
sprawdz("kandydat wymaga n>=4, klastrow>=3, przewagi >=1,15 i przewagi >= polowy wykrywalnego efektu raportu (szum odpada)",
        "forma|dobra" in ps and not ps & {"forma|male_n", "forma|malo_klastrow", "forma|slaba_przewaga", "forma|za_maly_efekt"}, ps)
dp = raport()
dp["wymiary"] = {"dzien": {"odniesienie": "pon", "grupy": {"pon": g(10, 8, 1.0), "wt": g(6, 5, 1.4)}}, "pora": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), "y": g(6, 5, 1.4)}}}
sprawdz("wymiary dzien i pora: przy oknie raportu < 14 dni kandydat nie jest proponowany (jedna data kalendarzowa to nie niezalezny tydzien)",
        not {p["dowod"].get("id") for p in redaktor.propozycje(dp, redaktor.sygnaly(dp), date(2026, 11, 5), "2026-W45")[0]} & {"dzien|wt", "pora|y"})
sprawdz("...a przy oknie >= 14 dni jest", {"dzien|wt", "pora|y"} <= {p["dowod"].get("id") for p in prop(dp)})
sprawdz("grupa z nierozliczonym przewidywaniem nie wraca jako nowa propozycja (deduplikacja)", not {p["dowod"].get("id") for p in prop(
    raport(), otwarte={("kategoria", "MONEY", "grupa_nowe_notki"), ("dlugosc", "33-64", "grupa_werdykt")})} & {"kategoria|MONEY", "dlugosc|33-64"})

many = raport()
many["wymiary"] = {"kategoria": {"odniesienie": "BAZA", "grupy": dict(
    [("BAZA", g(10, 8, 1.0))] + [("K%d" % i, g(8, 6, 1.5 + i / 10, 1.5 + i / 10, [1.1, 2.5], "lepiej")) for i in range(8)])}}
pm, obc = redaktor.propozycje(many, redaktor.sygnaly(many), DZIS, "2026-W47")
sprawdz("limit propozycji na tydzien: osiem mocnych sygnalow daje najwyzej 5, a reszta idzie do licznika obcietych",
        len(pm) == redaktor.MAKS_PROPOZYCJI == 5 and obc == 3, (len(pm), obc))
sprawdz("...i zostaja te o najwiekszej sile (najdalej od 1), a numeracja propozycji jest ciagla",
        [p["dowod"]["id"] for p in pm] == ["kategoria|K7", "kategoria|K6", "kategoria|K5", "kategoria|K4", "kategoria|K3"]
        and [p["id"] for p in pm] == ["R-2026-W47-%d" % i for i in range(1, 6)], [p["dowod"]["id"] for p in pm])

print("=== 3. PRYWATNOSC: TYLKO LICZBY ZBIORCZE I NAZWY GRUP ===")
surowy = PLIK.read_text(encoding="utf-8") + MD.read_text(encoding="utf-8")
sprawdz("brak tekstow notek, uchwytow i adresow w pliku i notatce", not any(x in surowy for x in ("SEKRETNY", "uchwyt", "example.com", "poczatek")) and "@" not in surowy, surowy[:200])

print("=== 4. SWIEZOSC RAPORTU, IDEMPOTENTNOSC, NOWY TYDZIEN, GRANICA ROKU ===")
n0 = len(linie())
zapisz_raport(raport(dzis=DZIS - timedelta(days=5)))
w_st, log_st = uruchom()
sprawdz("raport starszy niz doba: None, nic nie dopisano, powod w logu", w_st is None and len(linie()) == n0 and "nieswiezy" in log_st, (w_st, log_st))
zapisz_raport(raport(dzis=DZIS - timedelta(days=1)))
sprawdz("raport z wczoraj jeszcze jest swiezy", uruchom()[0] is not None)
zapisz_raport(raport())
uruchom()
uruchom()
sprawdz("ten sam tydzien: nadal jedna epoka (idempotentne)", len([x for x in linie() if x["rodzaj"] == "epoka"]) == 1)
zapisz_raport(raport(dzis=DZIS + timedelta(days=7)))
uruchom(DZIS + timedelta(days=7))
ep = [x for x in linie() if x["rodzaj"] == "epoka"]
sprawdz("nowy tydzien ISO: druga epoka", [x["tydzien"] for x in ep] == ["2026-W47", "2026-W48"])
sprawdz("DEDUPLIKACJA miedzy tygodniami: przewidywania z W47 sa jeszcze nierozliczone, wiec ich grupy nie wracaja w W48",
        not ({p["dowod"].get("id") for p in ep[0]["propozycje"]} & {p["dowod"].get("id") for p in ep[1]["propozycje"]} - {None}),
        ([p["dowod"].get("id") for p in ep[1]["propozycje"]]))
KAT3 = pathlib.Path(tempfile.mkdtemp())
for dz, tydz in ((date(2026, 12, 31), "2026-W53"), (date(2027, 1, 1), "2026-W53"), (date(2027, 1, 4), "2027-W01")):
    zapisz_raport(raport(dzis=dz), KAT3)
    uruchom(dz, KAT3)
sprawdz("granica roku ISO: 31.12.2026 i 1.1.2027 to W53 (jedna epoka), 4.1.2027 to 2027-W01",
        [x["tydzien"] for x in linie(KAT3 / PLIK.name) if x["rodzaj"] == "epoka"] == ["2026-W53", "2027-W01"], [x["tydzien"] for x in linie(KAT3 / PLIK.name)])

print("=== 5. ROZLICZENIE NA NOWYCH NOTKACH ===")
KAT4 = pathlib.Path(tempfile.mkdtemp())
zapisz_raport(raport(), KAT4)
uruchom(DZIS, KAT4)
e4 = linie(KAT4 / PLIK.name)[0]
po = DZIS + timedelta(days=15)
sprawdz("przed terminem nic nie rozliczono", not [x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "rozliczenie"])
r2 = raport(dzis=po)
r2["wymiary"]["dlugosc"]["grupy"]["33-64"]["werdykt"] = "lepiej"                      # nadal lepiej: potwierdzone
r2["wymiary"]["kategoria"]["grupy"]["PEOPLE"]["werdykt"] = "lepiej"                    # oczekiwane gorzej, jest lepiej: chybione
r2["wymiary"]["kategoria"]["grupy"]["MONEY"].update({"n": 9, "wzgl_tla": 1.3})        # 5 nowych, srednio ok. 1,10: potwierdzone
r2["wymiary"]["pytanie"]["grupy"]["tak"].update({"n": 6, "wzgl_tla": 0.9})            # 1 nowa notka: bez rozstrzygniecia
zapisz_raport(r2, KAT4)
uruchom(po, KAT4)
roz = {x["id_propozycji"]: x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "rozliczenie"}
wyn = {next(p["dowod"]["id"] for p in e4["propozycje"] if p["id"] == k): v for k, v in roz.items()}
sprawdz("grupa_werdykt: nadal lepiej = potwierdzone, odwrocona klasa = chybione", wyn["dlugosc|33-64"]["wynik"] == "potwierdzone"
        and wyn["kategoria|PEOPLE"]["wynik"] == "chybione", {k: v["wynik"] for k, v in wyn.items()})
oczek = round(math.exp((9 * math.log(1.3) - 4 * math.log(1.6)) / 5), 3)
sprawdz("grupa_nowe_notki: wzgl. tla NOWYCH notek liczone z przyrostu (srednia logarytmow wazona liczba notek)", wyn["kategoria|MONEY"]["wynik"] == "potwierdzone"
        and wyn["kategoria|MONEY"]["wartosc_aktualna"] == oczek and 1.0 <= oczek < 1.3, (wyn["kategoria|MONEY"], oczek))
sprawdz("za malo NOWYCH notek (1 < 4) = bez rozstrzygniecia, mimo ze skumulowane wzgl. tla spadlo", wyn["pytanie|tak"]["wynik"] == "bez_rozstrzygniecia"
        and wyn["pytanie|tak"]["wartosc_aktualna"] == 1, wyn["pytanie|tak"])
sprawdz("rozliczenie niesie epoke wpisu i epoke redakcyjna 0", all(x["epoka_redakcyjna"] == 0 and x["epoka_wpisu"] == "2026-W47" for x in roz.values()))
n_roz = len(roz)
uruchom(po, KAT4)
sprawdz("ponowny przebieg nie rozlicza drugi raz", len([x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "rozliczenie"]) == n_roz)
sprawdz("tekst notatki: zapis zamiarow, trwajace eksperymenty, rozliczenie ze slowami „potwierdzone”, „chybione”, „bez rozstrzygniecia”",
        all(x in (KAT4 / "obserwatorium" / "redaktor.md").read_text(encoding="utf-8") for x in ("nie decyzje wykonane", "dlugosc_serii", "potwierdzone", "chybione", "bez rozstrzygniecia")))
chyb = redaktor.rozlicz_przewidywanie({"typ": "grupa_nowe_notki", "wymiar": "kategoria", "grupa": "MONEY", "n_przy_zapisie": 4, "wzgl_przy_zapisie": 1.6,
                                       "wartosc_odniesienia": 1.0, "min_nowych": 4},
                                      {"wymiary": {"kategoria": {"grupy": {"MONEY": {"n": 10, "wzgl_tla": 0.9}}}}})
sprawdz("nowe notki slabsze od tla (cala grupa spadla mocno): chybione", chyb[0] == "chybione" and chyb[1] < 1.0, chyb)
sprawdz("zmiana grupy odniesienia unieważnia porównanie werdyktu (bez rozstrzygniecia)", redaktor.rozlicz_przewidywanie(
    {"typ": "grupa_werdykt", "wymiar": "dlugosc", "grupa": "33-64", "oczekiwana": "lepiej", "odniesienie": "65-110"},
    {"wymiary": {"dlugosc": {"odniesienie": "111+", "grupy": {"33-64": g(8, 7, 1.4, 1.5, [1.1, 2.0], "lepiej")}}}})[0] == "bez_rozstrzygniecia")
sprawdz("silne_sygnaly: potwierdzone przy grupie lepiej/gorzej w wymiarze innym niz model, chybione bez niej",
        redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, raport())[0] == "potwierdzone"
        and redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, tylko_model)[0] == "chybione")
jedna = {"wymiary": {"dlugosc": {"odniesienie": "65-110", "grupy": {"65-110": g(10, 8, 1.0), "33-64": g(8, 7, 1.4, 1.5, [1.1, 2.0], "lepiej")}}}}
sprawdz("silne_sygnaly: DOKLADNIE jedna grupa „lepiej” spelnia prog 1 (granica >=, nie >)",
        redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, jedna) == ("potwierdzone", 1))
sprawdz("brak grupy w raporcie = bez rozstrzygniecia (nie zgadujemy)", redaktor.rozlicz_przewidywanie(
    {"typ": "grupa_werdykt", "wymiar": "x", "grupa": "y", "oczekiwana": "lepiej", "odniesienie": "z"}, {"wymiary": {}})[0] == "bez_rozstrzygniecia")

print("=== 6. FLAGA, BRAK RAPORTU, USZKODZONY PLIK, ROZMIAR, UCIETY OGON ===")
KAT2 = pathlib.Path(tempfile.mkdtemp())
(KAT2 / "obserwatorium").mkdir()
w_brak, log_brak = uruchom(DZIS, KAT2)
sprawdz("brak raportu: None, powod w logu, nic nie zapisano", w_brak is None and not (KAT2 / PLIK.name).exists() and "brak lub uszkodzony" in log_brak, log_brak)
(KAT2 / "obserwatorium" / "co_dziala.json").write_text("{nie json", encoding="utf-8")
sprawdz("uszkodzony raport: None, bez wyjatku", uruchom(DZIS, KAT2)[0] is None)
(KAT2 / "obserwatorium" / "co_dziala.json").write_text(json.dumps({"dzis": "x"}), encoding="utf-8")
sprawdz("raport bez wymiarow: None", uruchom(DZIS, KAT2)[0] is None)
(KAT2 / "obserwatorium" / "co_dziala.json").write_text(json.dumps(raport()), encoding="utf-8")
config.REDAKTOR_CIEN = False
w_fl, log_fl = uruchom(DZIS, KAT2)
sprawdz("flaga False: None, powod w logu, nic nie zapisano", w_fl is None and not (KAT2 / PLIK.name).exists() and "flaga" in log_fl, log_fl)
config.REDAKTOR_CIEN = True
_stare = redaktor.MAKS_BAJTOW
(KAT2 / PLIK.name).write_text("x" * 50 + "\n", encoding="utf-8")
redaktor.MAKS_BAJTOW = 10
w_rz, log_rz = uruchom(DZIS, KAT2)
sprawdz("limit rozmiaru: None, powod w logu, plik bez zmian", w_rz is None and (KAT2 / PLIK.name).read_text(encoding="utf-8") == "x" * 50 + "\n" and "przekroczyl" in log_rz, log_rz)
redaktor.MAKS_BAJTOW = _stare
(KAT2 / PLIK.name).write_text('{"rodzaj": "epoka", "tydzien": "1999-W01"}\n{"rodzaj": "epo', encoding="utf-8")
uruchom(DZIS, KAT2)
t2 = (KAT2 / PLIK.name).read_text(encoding="utf-8").split("\n")
sprawdz("ucieta ostatnia linia: nowy rekord w osobnym, czytelnym wierszu", len(t2) == 4 and json.loads(t2[2])["tydzien"] == "2026-W47" and t2[3] == "", t2)

print("=== 7. WPIECIE I ZALEZNOSCI ===")
_obs = pathlib.Path("agent-v2/obserwatorium.py").read_text(encoding="utf-8")
sprawdz("obserwatorium: hak po co_dziala, w try/except Exception, z komunikatem o awarii",
        re.search(r"import co_dziala.*?import redaktor\s+print\(\"redaktor:\", redaktor\.zapisz\(\), flush=True\)\s+except Exception as exc:\s+print\(\"redaktor: nie zapisany",
                  _obs, re.S) is not None)
_w = pathlib.Path("agent-v2/wdroz.sh").read_text(encoding="utf-8")
sprawdz("wdroz.sh importuje redaktor w kontroli „moduly wstaja”", "redaktor" in _w)
_src = pathlib.Path("agent-v2/redaktor.py").read_text(encoding="utf-8")
sprawdz("redaktor nie importuje modulow bota (stages, run, llm, browser): zadnego sprzezenia z kodem, ktory pisze tresc",
        not re.search(r"^\s*(from|import)\s+(stages|run|llm|browser|db)\b", _src, re.M))
sprawdz("pliki sa ignorowane przez Git (data/)", all(
    __import__("subprocess").run(["git", "check-ignore", "-q", p], capture_output=True).returncode == 0
    for p in ("agent-v2/data/redaktor_cien.jsonl", "agent-v2/data/obserwatorium/redaktor.md")))

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
