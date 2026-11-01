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
        "id": "dlugosc|33-64", "n": 8, "klastrow": 7, "wzgl_tla": 1.4, "wzgl_odn": 1.0, "przewaga": 1.4, "stosunek": 1.5, "przedzial_95": [1.1, 2.0],
        "odniesienie": "65-110", "ostroznie": True})
sprawdz("przewidywanie mocnego sygnalu jest na tej samej osi co dowod: werdykt wzgledem odniesienia (typ grupa_werdykt, oczekiwana klasa)",
        next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["typ"] == "grupa_werdykt"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["oczekiwana"] == "lepiej"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|PEOPLE")["przewidywanie"]["oczekiwana"] == "gorzej"
        and next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]["odniesienie"] == "65-110")
_pm = next(p for p in e["propozycje"] if p["dowod"]["id"] == "kategoria|MONEY")["przewidywanie"]
sprawdz("przewidywanie kandydata dotyczy NOWYCH notek WZGLEDEM ODNIESIENIA (n, wzgl. tla i klastry z chwili zapisu, obu grup; okno raportu)",
        {k: _pm.get(k) for k in ("typ", "wymiar", "grupa", "odniesienie", "wzgledem", "n_przy_zapisie", "wzgl_przy_zapisie", "klastrow_przy_zapisie",
                                 "odn_n_przy_zapisie", "odn_wzgl_przy_zapisie", "wartosc_odniesienia", "min_nowych", "min_nowych_klastrow", "okno_od")}
        == {"typ": "grupa_nowe_notki", "wymiar": "kategoria", "grupa": "MONEY", "odniesienie": "HOW_IT_WORKS", "wzgledem": "odniesienie", "n_przy_zapisie": 4,
            "wzgl_przy_zapisie": 1.6, "klastrow_przy_zapisie": 3, "odn_n_przy_zapisie": 8, "odn_wzgl_przy_zapisie": 1.0, "wartosc_odniesienia": 1.0,
            "min_nowych": 4, "min_nowych_klastrow": 2, "okno_od": "2026-10-26"}, _pm)
_pw = next(p for p in e["propozycje"] if p["dowod"]["id"] == "dlugosc|33-64")["przewidywanie"]
sprawdz("przewidywanie werdyktu tez niesie stan z chwili zapisu i okno raportu (rozliczenie dopiero po przyroscie danych)",
        (_pw["n_przy_zapisie"], _pw["klastrow_przy_zapisie"], _pw["min_nowych"], _pw["min_nowych_klastrow"], _pw["okno_od"]) == (8, 7, 4, 2, "2026-10-26"), _pw)
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
odn = raport()
odn["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(12, 9, 1.5), "gorsza_od_odn": g(6, 5, 1.3), "lepsza_od_odn": g(6, 5, 1.9)}}}
po_odn = {p["dowod"].get("id") for p in prop(odn)}
sprawdz("kandydat jest oceniany WZGLEDEM ODNIESIENIA, nie tla: grupa 1,3 przy odniesieniu 1,5 odpada, a 1,9 (przewaga 1,27) przechodzi",
        "forma|lepsza_od_odn" in po_odn and "forma|gorsza_od_odn" not in po_odn, po_odn)
_pl = next(p for p in prop(odn) if p["dowod"].get("id") == "forma|lepsza_od_odn")
sprawdz("...a dowod niesie przewage i wzgl. tla odniesienia", _pl["dowod"]["przewaga"] == round(1.9 / 1.5, 3) and _pl["dowod"]["wzgl_odn"] == 1.5, _pl["dowod"])
gran = raport()
gran["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), "na_granicy": g(6, 5, 1.15, wykrywalny=0.30)}}}
sprawdz("granica: przewaga 1,15 przy wykrywalnym efekcie 0,30 spelnia „co najmniej polowa” mimo bledu zmiennoprzecinkowego (0,15 >= 0,15)",
        "forma|na_granicy" in {p["dowod"].get("id") for p in prop(gran)})
pusty = raport(notek=5)
pusty["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0)}}}
otw_pol = prop(pusty, otwarte={("", "", "silne_sygnaly")})
sprawdz("„nie zmieniac polityki” nie wraca co tydzien, dopoki poprzednie nie jest rozliczone; zamiast pustej listy jest informacja bez nowego przewidywania",
        len(otw_pol) == 1 and otw_pol[0]["typ"] == "polityka" and "Bez nowych" in otw_pol[0]["tresc"]
        and otw_pol[0]["przewidywanie"]["typ"] == "brak" and "sprawdz_po" not in otw_pol[0]["przewidywanie"], otw_pol)
sprawdz("...a bez otwartego przewidywania ten sam raport daje zwykle „nie zmieniac polityki” z terminem",
        prop(pusty)[0]["przewidywanie"]["typ"] == "silne_sygnaly" and prop(pusty)[0]["przewidywanie"]["sprawdz_po"])
sprawdz("otwarta „polityka” nie blokuje propozycji z mocnych sygnalow: nie powtarza tylko zdania o polityce",
        not any(p["typ"] == "polityka" for p in prop(maly, otwarte={("", "", "silne_sygnaly")})))
sprawdz("_otwarte liczy tez nierozliczone „polityki” (wymiar i grupa puste)", redaktor._otwarte([
    {"rodzaj": "epoka", "propozycje": [{"id": "R-1", "przewidywanie": {"typ": "silne_sygnaly", "sprawdz_po": "2026-12-01"}},
                                        {"id": "R-2", "przewidywanie": {"typ": "brak"}}]}]) == {("", "", "silne_sygnaly")})
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


def kum(n0, w0, nowych, x):
    """Skumulowane wzgl. tla (zaokraglone do 2 miejsc jak w raporcie), gdy n0 notek mialo w0, a `nowych` notek ma srednio x — wejscie zbudowane NIEZALEZNIE od wzoru w kodzie."""
    return round(math.exp((n0 * math.log(w0) + nowych * math.log(x)) / (n0 + nowych)), 2)


r2 = raport(dzis=po)
r2["wymiary"]["dlugosc"]["grupy"]["33-64"].update({"n": 13, "klastrow": 10})                                    # 5 nowych, 3 nowe jednostki, nadal lepiej: potwierdzone
r2["wymiary"]["kategoria"]["grupy"]["PEOPLE"].update({"n": 14, "klastrow": 9, "werdykt": "lepiej"})            # oczekiwane gorzej, jest lepiej: chybione
r2["wymiary"]["kategoria"]["grupy"]["MONEY"].update({"n": 9, "klastrow": 6, "wzgl_tla": kum(4, 1.6, 5, 1.2)})  # nowe notki srednio 1,2 przy odniesieniu 1,0: potwierdzone
r2["wymiary"]["kategoria"]["grupy"]["HOW_IT_WORKS"].update({"n": 13, "klastrow": 10})                          # odniesienie tez ma 5 nowych notek (srednio 1,0)
r2["wymiary"]["pytanie"]["grupy"]["tak"].update({"n": 6, "wzgl_tla": 0.9})                                      # 1 nowa notka: bez rozstrzygniecia
zapisz_raport(r2, KAT4)
uruchom(po, KAT4)
roz = {x["id_propozycji"]: x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "rozliczenie"}
wyn = {next(p["dowod"]["id"] for p in e4["propozycje"] if p["id"] == k): v for k, v in roz.items()}
sprawdz("grupa_werdykt: po przyroscie danych nadal lepiej = potwierdzone, odwrocona klasa = chybione", wyn["dlugosc|33-64"]["wynik"] == "potwierdzone"
        and wyn["kategoria|PEOPLE"]["wynik"] == "chybione", {k: v["wynik"] for k, v in wyn.items()})
sprawdz("grupa_nowe_notki: nowe notki (srednio 1,2, wejscie zbudowane niezaleznie od wzoru) wobec nowych notek odniesienia (1,0) = potwierdzone, wartosc ok. 1,2",
        wyn["kategoria|MONEY"]["wynik"] == "potwierdzone" and abs(wyn["kategoria|MONEY"]["wartosc_aktualna"] - 1.2) < 0.03, wyn["kategoria|MONEY"])
sprawdz("za malo NOWYCH notek (1 < 4) = bez rozstrzygniecia, mimo ze skumulowane wzgl. tla spadlo", wyn["pytanie|tak"]["wynik"] == "bez_rozstrzygniecia"
        and "nowych notek: 1" in str(wyn["pytanie|tak"]["wartosc_aktualna"]), wyn["pytanie|tak"])
sprawdz("rozliczenie niesie epoke wpisu i epoke redakcyjna 0", all(x["epoka_redakcyjna"] == 0 and x["epoka_wpisu"] == "2026-W47" for x in roz.values()))
n_roz = len(roz)
uruchom(po, KAT4)
sprawdz("ponowny przebieg nie rozlicza drugi raz", len([x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "rozliczenie"]) == n_roz)
sprawdz("tekst notatki: zapis zamiarow, trwajace eksperymenty, rozliczenie ze slowami „potwierdzone”, „chybione”, „bez rozstrzygniecia”",
        all(x in (KAT4 / "obserwatorium" / "redaktor.md").read_text(encoding="utf-8") for x in ("nie decyzje wykonane", "dlugosc_serii", "potwierdzone", "chybione", "bez rozstrzygniecia")))
PN = {"typ": "grupa_nowe_notki", "wymiar": "kategoria", "grupa": "MONEY", "odniesienie": "REF", "wzgledem": "tlo", "n_przy_zapisie": 4, "wzgl_przy_zapisie": 1.6,
      "klastrow_przy_zapisie": 3, "wartosc_odniesienia": 1.0, "min_nowych": 4, "min_nowych_klastrow": 2}


def rap(grupa, odn=None):
    return {"od": "2026-10-26", "wymiary": {"kategoria": {"odniesienie": "REF", "grupy": {"MONEY": grupa, **({"REF": odn} if odn else {})}}}}


chyb = redaktor.rozlicz_przewidywanie(PN, rap({"n": 10, "klastrow": 7, "wzgl_tla": kum(4, 1.6, 6, 0.8)}))
sprawdz("nowe notki slabsze od tla (srednio 0,8; wejscie zbudowane niezaleznie): chybione, wartosc ok. 0,8", chyb[0] == "chybione" and abs(chyb[1] - 0.8) < 0.03, chyb)
sprawdz("tyle samo nowych notek, ale tylko 1 nowa niezalezna jednostka (jedna seria): bez rozstrzygniecia, nie „potwierdzone”",
        redaktor.rozlicz_przewidywanie(PN, rap({"n": 10, "klastrow": 4, "wzgl_tla": kum(4, 1.6, 6, 1.5)}))[0] == "bez_rozstrzygniecia")
sprawdz("brak liczby klastrow w raporcie: bez rozstrzygniecia (nie zgadujemy)",
        redaktor.rozlicz_przewidywanie(PN, rap({"n": 10, "wzgl_tla": 1.2}))[0] == "bez_rozstrzygniecia")
PO = {**PN, "wzgledem": "odniesienie", "odn_n_przy_zapisie": 10, "odn_wzgl_przy_zapisie": 1.0}
sprawdz("wzgledem odniesienia: grupa nowych notek 1,2, ale odniesienie nowych notek 1,5 = chybione (caly wymiar urosl, grupa nie wyprzedza)",
        redaktor.rozlicz_przewidywanie(PO, rap({"n": 10, "klastrow": 7, "wzgl_tla": kum(4, 1.6, 6, 1.2)}, {"n": 20, "klastrow": 14, "wzgl_tla": kum(10, 1.0, 10, 1.5)}))[0] == "chybione")
sprawdz("wzgledem odniesienia: to samo przy braku nowych notek w odniesieniu = bez rozstrzygniecia",
        redaktor.rozlicz_przewidywanie(PO, rap({"n": 10, "klastrow": 7, "wzgl_tla": 1.2}, {"n": 10, "klastrow": 8, "wzgl_tla": 1.0}))[0] == "bez_rozstrzygniecia")
PW = {"typ": "grupa_werdykt", "wymiar": "kategoria", "grupa": "MONEY", "oczekiwana": "lepiej", "odniesienie": "REF", "n_przy_zapisie": 8, "klastrow_przy_zapisie": 6,
      "min_nowych": 4, "min_nowych_klastrow": 2}
sprawdz("werdykt „lepiej” zmienia sie na „brak dowodu” po przyroscie danych = chybione (zanik przedzialu to porazka przewidywania, nie brak rozstrzygniecia)",
        redaktor.rozlicz_przewidywanie(PW, rap(g(14, 9, 1.2, 1.1, [0.9, 1.4], "brak dowodu roznicy (..)")))[0] == "chybione")
sprawdz("werdykt bez przyrostu danych (te same notki, tylko nowy dzien): bez rozstrzygniecia, nie „potwierdzone”",
        redaktor.rozlicz_przewidywanie(PW, rap(g(9, 7, 1.4, 1.5, [1.1, 2.0], "lepiej")))[0] == "bez_rozstrzygniecia")
sprawdz("zmiana okna raportu (`od`) uniewaznia porownanie nowych notek", redaktor.rozlicz_przewidywanie(
    {**PW, "okno_od": "2026-10-26"}, {**rap(g(14, 9, 1.4, 1.5, [1.1, 2.0], "lepiej")), "od": "2026-10-01"})[0] == "bez_rozstrzygniecia")
sprawdz("...a przy tym samym oknie ten sam przypadek jest rozliczany", redaktor.rozlicz_przewidywanie(
    {**PW, "okno_od": "2026-10-26"}, rap(g(14, 9, 1.4, 1.5, [1.1, 2.0], "lepiej")))[0] == "potwierdzone")
sprawdz("estymator: bez nowych notek, zle liczby i NaN daja None, nie wyjatek", [redaktor._nowe_wzgl(*a) for a in (
    (4, 1.6, 4, 1.2), (4, 1.6, 3, 1.2), (4, 0, 9, 1.2), (4, 1.6, 9, float("nan")), (4, None, 9, 1.2), (4, 1.6, 9, float("inf")))] == [None] * 6)
sprawdz("zmiana grupy odniesienia unieważnia porównanie werdyktu (bez rozstrzygniecia)", redaktor.rozlicz_przewidywanie(
    {**PW, "wymiar": "dlugosc", "grupa": "33-64", "odniesienie": "65-110"},
    {"wymiary": {"dlugosc": {"odniesienie": "111+", "grupy": {"33-64": g(14, 9, 1.4, 1.5, [1.1, 2.0], "lepiej")}}}})[0] == "bez_rozstrzygniecia")
sprawdz("silne_sygnaly: potwierdzone przy grupie lepiej/gorzej w wymiarze innym niz model, chybione bez niej",
        redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, raport())[0] == "potwierdzone"
        and redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, tylko_model)[0] == "chybione")
jedna = {"wymiary": {"dlugosc": {"odniesienie": "65-110", "grupy": {"65-110": g(10, 8, 1.0), "33-64": g(8, 7, 1.4, 1.5, [1.1, 2.0], "lepiej")}}}}
sprawdz("silne_sygnaly: DOKLADNIE jedna grupa „lepiej” spelnia prog 1 (granica >=, nie >)",
        redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, jedna) == ("potwierdzone", 1))
sprawdz("brak grupy w raporcie = bez rozstrzygniecia (nie zgadujemy)", redaktor.rozlicz_przewidywanie(
    {"typ": "grupa_werdykt", "wymiar": "x", "grupa": "y", "oczekiwana": "lepiej", "odniesienie": "z"}, {"wymiary": {}})[0] == "bez_rozstrzygniecia")

print("=== 5b. FORMAT NOTKI, LICZNIKI, TEKSTY AWARYJNE, GRANICE I KOLEJNOSC (po przegladzie workflow) ===")
fm = raport()
fm["wymiary"] = {"dlugosc": {"odniesienie": "65-110", "grupy": {"65-110": g(10, 8, 1.0), "33-64": g(8, 7, 1.0, 1.0, [0.8, 1.2], "brak dowodu roznicy (..)")}}}
fm["formaty"] = {"odniesienie": "zwykla", "n": 30, "grupy": {"zwykla": g(20, 15, 1.0), "seria": g(10, 8, 1.7, 1.7, [1.2, 2.4], "lepiej")}}
sg = {s["id"]: s for s in redaktor.sygnaly(fm)}
pf = prop(fm)
sprawdz("format notki (`formaty`, osobne pole raportu) jest wymiarem „format”: sygnal, klasa, odniesienie", "format|seria" in sg and sg["format|seria"]["klasa"] == "lepiej"
        and sg["format|seria"]["odniesienie"] == "zwykla" and sg["format|zwykla"]["klasa"] == "odniesienie", sorted(sg))
sprawdz("...daje propozycje „zwiekszyc” (rodzaj styl) zamiast fałszywego „zadna grupa nie ma werdyktu”",
        any(p["typ"] == "styl" and p["tresc"].startswith("Zwiekszyc") and p["dowod"].get("id") == "format|seria" for p in pf) and not any(p["typ"] == "polityka" for p in pf), pf)
fm2 = raport(dzis=po)
fm2["wymiary"] = fm["wymiary"]
fm2["formaty"] = {"odniesienie": "zwykla", "n": 45, "grupy": {"zwykla": g(30, 22, 1.0), "seria": g(15, 11, 1.7, 1.7, [1.2, 2.4], "lepiej")}}
PWF = {**PW, "wymiar": "format", "grupa": "seria", "odniesienie": "zwykla", "n_przy_zapisie": 10, "klastrow_przy_zapisie": 8}
sprawdz("przewidywanie o formacie jest rozliczane z `formaty` (nadal lepiej po przyroscie danych = potwierdzone)",
        redaktor.rozlicz_przewidywanie(PWF, fm2)[0] == "potwierdzone" and redaktor.rozlicz_przewidywanie(PWF, {"od": "2026-10-26", "wymiary": {}})[0] == "bez_rozstrzygniecia")

KAT5 = pathlib.Path(tempfile.mkdtemp())
zapisz_raport(tylko_model, KAT5)
uruchom(DZIS, KAT5)
e5 = linie(KAT5 / PLIK.name)[0]
sprawdz("licznik „Co widze” liczy z tej samej puli co decyzja (bez wymiarow model i pozycja): jedyny „lepiej” w modelu nie jest widoczny",
        e5["sygnaly"]["lepiej"] == 0 and e5["sygnaly"]["gorzej"] == 0 and "bez wymiarow model i pozycja" in (KAT5 / "obserwatorium" / "redaktor.md").read_text(encoding="utf-8"), e5["sygnaly"])
sprawdz("...a decyzja o polityce nadal idzie wlasciwa galezia („zadna grupa nie ma werdyktu”), nie awaryjna",
        e5["propozycje"][0]["typ"] == "polityka" and "Zadna grupa nie ma jeszcze werdyktu" in e5["propozycje"][0]["uzasadnienie"], e5["propozycje"][0])
sprawdz("tekst awaryjny: bez grup z sygnalem mowi o czekajacej polityce, a nie o „grupach z sygnalem”",
        "Brak grup z sygnalem" in prop(pusty, otwarte={("", "", "silne_sygnaly")})[0]["uzasadnienie"]
        and "Wszystkie grupy z sygnalem" in prop(pusty, otwarte={("", "", "silne_sygnaly"), ("forma", "x", "grupa_werdykt")})[0]["uzasadnienie"])

# dzien / pora: `co_dziala` bierze notki dopiero po 72 h, wiec okno liczy sie od ostatniej dojrzalej doby
dk = raport()
dk["wymiary"] = {"dzien": {"odniesienie": "pon", "grupy": {"pon": g(10, 8, 1.0), "wt": g(6, 5, 1.4)}}}
ids_dk = lambda dz, rap_=dk: {p["dowod"].get("id") for p in redaktor.propozycje(rap_, redaktor.sygnaly(rap_), dz, "2026-W46")[0]}      # noqa: E731
sprawdz("dzien/pora: okno 17 dni (13 po dojrzewaniu 72 h) jeszcze nie wystarcza, 18 (14) wystarcza",
        "dzien|wt" not in ids_dk(date(2026, 11, 12)) and "dzien|wt" in ids_dk(date(2026, 11, 13)))
dk_bez = {k: v for k, v in dk.items() if k != "od"}
sprawdz("dzien/pora: raport bez daty `od` nie przechodzi (nie wiadomo, jak dlugie jest okno)", "dzien|wt" not in ids_dk(date(2026, 12, 20), dk_bez))

# wybor propozycji: kolejnosc, limit, obcieto razem z „polityka”
sl = raport(notek=12)
sl["wymiary"] = {"forma": {"odniesienie": "x", "grupy": dict([("x", g(12, 9, 1.0))] + [("C%d" % i, g(6, 5, 1.2 + i / 10)) for i in range(7)])}}
ps_, obc_ = redaktor.propozycje(sl, redaktor.sygnaly(sl), DZIS, "2026-W47")
sprawdz("kandydaci bez mocnych sygnalow: „polityka” + 4 najsilniejsze (malejaco po przewadze), reszta w liczniku obcietych (7 - 4 = 3)",
        [p["typ"] for p in ps_][:1] == ["polityka"] and [p["dowod"].get("id") for p in ps_[1:]] == ["forma|C6", "forma|C5", "forma|C4", "forma|C3"] and obc_ == 3,
        ([p["dowod"].get("id") for p in ps_], obc_))
mx = raport()
mx["wymiary"] = {"forma": {"odniesienie": "x", "grupy": {"x": g(10, 8, 1.0), "A": g(8, 7, 1.3, 1.3, [1.1, 1.6], "lepiej"), "B": g(8, 7, 0.4, 0.4, [0.2, 0.7], "gorzej"),
                                                         "C": g(8, 7, 2.0, 2.0, [1.5, 2.6], "lepiej")}}}
sprawdz("mocne sygnaly „lepiej” i „gorzej” razem: kolejnosc wg odleglosci od 1 w obie strony (B 0,4, C 2,0, A 1,3)",
        [p["dowod"]["id"] for p in prop(mx)] == ["forma|B", "forma|C", "forma|A"], [p["dowod"].get("id") for p in prop(mx)])
sprawdz("prog minimalnej liczby notek: dokladnie 8 daje propozycje z sygnalow, 7 daje „nie zmieniac polityki”",
        prop(raport(notek=8))[0]["typ"] != "polityka" and prop(raport(notek=7))[0]["typ"] == "polityka")

# rozliczenia: granice progow, klasa „za malo”, tylko „gorzej”, termin
sprawdz("dokladnie 4 nowe notki i 2 nowe jednostki: rozliczone (granica „co najmniej”)",
        redaktor.rozlicz_przewidywanie(PN, rap({"n": 8, "klastrow": 5, "wzgl_tla": kum(4, 1.6, 4, 1.5)}))[0] == "potwierdzone")
sprawdz("3 nowe notki: bez rozstrzygniecia, 1 nowa jednostka: bez rozstrzygniecia (z powodem w wartosci)",
        redaktor.rozlicz_przewidywanie(PN, rap({"n": 7, "klastrow": 5, "wzgl_tla": 1.5}))[0] == "bez_rozstrzygniecia"
        and "jednostek: 1" in str(redaktor.rozlicz_przewidywanie(PN, rap({"n": 8, "klastrow": 4, "wzgl_tla": 1.5}))[1]))
sprawdz("nowe notki dokladnie na poziomie odniesienia (1,0): potwierdzone (granica „>=”)",
        redaktor.rozlicz_przewidywanie({**PN, "wzgl_przy_zapisie": 1.0}, rap({"n": 8, "klastrow": 5, "wzgl_tla": 1.0}))[0] == "potwierdzone")
sprawdz("werdykt „za malo danych” po przyroscie danych: bez rozstrzygniecia, nie „chybione”",
        redaktor.rozlicz_przewidywanie(PW, rap(g(14, 9, 1.2, werdykt="za malo danych (..)")))[0] == "bez_rozstrzygniecia")
tylko_gorzej = {"wymiary": {"kategoria": {"odniesienie": "A", "grupy": {"A": g(10, 8, 1.0), "B": g(8, 7, 0.4, 0.4, [0.2, 0.7], "gorzej")}}}}
sprawdz("silne_sygnaly: sam „gorzej” tez jest mocnym sygnalem", redaktor.rozlicz_przewidywanie({"typ": "silne_sygnaly", "wartosc_odniesienia": 1}, tylko_gorzej) == ("potwierdzone", 1))
ep_ = {"rodzaj": "epoka", "tydzien": "2026-W47", "propozycje": [{"id": "R-x", "przewidywanie": {"typ": "silne_sygnaly", "wartosc_odniesienia": 1, "sprawdz_po": "2026-11-30", "opis": "x"}}]}
sprawdz("termin: rozliczenie dokladnie w dniu `sprawdz_po`, nie dzien wczesniej",
        len(redaktor.rozlicz([ep_], raport(), date(2026, 11, 30))) == 1 and len(redaktor.rozlicz([ep_], raport(), date(2026, 11, 29))) == 0)
roz_ = {"rodzaj": "rozliczenie", "id_propozycji": "R-1"}
ep2_ = {"rodzaj": "epoka", "propozycje": [{"id": "R-1", "przewidywanie": {"typ": "grupa_werdykt", "wymiar": "forma", "grupa": "A", "sprawdz_po": "2026-11-30"}}]}
sprawdz("_otwarte: propozycja po rozliczeniu przestaje byc otwarta (grupa moze wrocic)", redaktor._otwarte([ep2_]) == {("forma", "A", "grupa_werdykt")} and redaktor._otwarte([ep2_, roz_]) == set())
e49 = [x for x in linie(KAT4 / PLIK.name) if x["rodzaj"] == "epoka" and x["tydzien"] == "2026-W49"]
sprawdz("grupy rozliczone w TYM SAMYM przebiegu wracaja jako propozycje w nowej epoce (nie czekaja kolejnego tygodnia)",
        len(e49) == 1 and {"dlugosc|33-64", "kategoria|PEOPLE"} <= {p["dowod"].get("id") for p in e49[0]["propozycje"]}, [p["dowod"].get("id") for p in e49[0]["propozycje"]] if e49 else None)

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
