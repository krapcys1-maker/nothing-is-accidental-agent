# -*- coding: utf-8 -*-
"""Obserwatorium: TEMPO PRZYROSTU liczone tym samym rachunkiem dla obu kont (6.10.2026).

PO CO. Wlasciciel zapytal, czy mierzymy predkosc przyrostu subskrybentow i obserwujacych
dla obu botow, bo drugie konto wyglada na szybsze. Raport mial netto 7 i 28 dni oraz tempo
subskrybentow na tydzien, ale nie pokazywal naraz: tygodnia po tygodniu, tego samego WIEKU
konta (dzien 0 = pierwszy odczyt licznika), kroczacych 7 dni z ilorazem i wskaznikow zasiegu.
Test pilnuje rachunku na danych SYNTETYCZNYCH o znanym przebiegu (wynik liczony niezaleznie
od testowanego kodu), z kontrdowodami na luki w pomiarze:

  1. `przyrost_miedzy` — roznica stanow, a przy braku ktoregokolwiek odczytu None, nie zero;
  2. `pierwszy_odczyt` — dzien 0 to pierwsza doba z OBOMA licznikami;
  3. `tygodnie_netto` — pelne tygodnie pon-niedz niezaleznie od dnia tygodnia „wczoraj”;
  4. `wedlug_wieku` — kroki 7/14/21..., bez dob spoza serii;
  5. `kroczace_7` — okno z luka daje None (luki nie wypelniamy);
  6. `wskazniki_zasiegu` — sumy i liczba dob z pomiarem, wyswietlenia na komentarz tylko z dob,
     w ktorych sa OBA pola;
  7. `sekcja_tempo` i `raport` — iloraz drugiego konta do pierwszego, „—” przy zerze i luce,
     jedno konto bez kolumny ilorazu, konto bez licznikow bez wyjatku; sekcja stoi po
     „Stan i tempo”, przed „Ostatnie dni”.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import json
import os
import pathlib
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

_tmp = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(_tmp / "nie")
NIA_KAT = _tmp / "nia"
NIA_KAT.mkdir()
os.environ["KARTA_NIA_DANE"] = str(NIA_KAT)
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


# --- DANE O ZNANYM PRZEBIEGU ---------------------------------------------------
# NIE: od 2026-08-31, subskrybenci 9 + n // 2, obserwujacy 11 + n  (n = doby od startu)
# NIA: od 2026-09-07, subskrybenci 2 + n,      obserwujacy 0 + 2 * n
START_NIE, START_NIA = date(2026, 8, 31), date(2026, 9, 7)


def nie(n):
    return 9 + n // 2, 11 + n


def nia(n):
    return 2 + n, 2 * n


def seria(start, ostatnia, f):
    out, d = {}, start
    while d <= ostatnia:
        s, o = f((d - start).days)
        out[d.isoformat()] = {"subskrybenci": s, "obserwujacy": o}
        d += timedelta(days=1)
    return out


DNI_NIE = seria(START_NIE, date(2026, 10, 5), nie)
DNI_NIA = seria(START_NIA, date(2026, 10, 6), nia)
WCZORAJ = "2026-10-05"        # poniedzialek


def n_nie(d):
    return (date.fromisoformat(d) - START_NIE).days


def n_nia(d):
    return (date.fromisoformat(d) - START_NIA).days


print("=== 1. PRZYROST MIEDZY DWIEMA DOBAMI ===")
p = obs.przyrost_miedzy(DNI_NIE, "2026-09-27", "2026-10-04")
oczek_s = nie(n_nie("2026-10-04"))[0] - nie(n_nie("2026-09-27"))[0]
oczek_o = nie(n_nie("2026-10-04"))[1] - nie(n_nie("2026-09-27"))[1]
sprawdz("roznica stanow NIE 27.09 -> 4.10", p == {"sub": oczek_s, "obs": oczek_o, "osoby": oczek_s + oczek_o}, (p, oczek_s, oczek_o))
sprawdz("tydzien NIE = +4 subskrybentow, +7 obserwujacych (z formuly)", (oczek_s, oczek_o) == (4, 7), (oczek_s, oczek_o))
luka = {d: dict(w) for d, w in DNI_NIE.items()}
del luka["2026-10-04"]["obserwujacy"]
sprawdz("KONTRDOWOD: brak jednego licznika na koncu okna = None, nie zero",
        obs.przyrost_miedzy(luka, "2026-09-27", "2026-10-04") is None)
sprawdz("brak doby w serii = None", obs.przyrost_miedzy(DNI_NIE, "2026-09-27", "2026-12-01") is None)
sprawdz("liczba bool nie jest licznikiem", obs.przyrost_miedzy({"a": {"subskrybenci": True, "obserwujacy": 1},
                                                              "b": {"subskrybenci": 2, "obserwujacy": 3}}, "a", "b") is None)

print()
print("=== 2. DZIEN 0 = PIERWSZA DOBA Z OBOMA LICZNIKAMI ===")
sprawdz("NIE zaczyna 31.08", obs.pierwszy_odczyt(DNI_NIE) == "2026-08-31")
sprawdz("NIA zaczyna 7.09", obs.pierwszy_odczyt(DNI_NIA) == "2026-09-07")
polowiczne = {"2026-09-01": {"subskrybenci": 5}, "2026-09-02": {"subskrybenci": 6, "obserwujacy": 1}}
sprawdz("doba z jednym licznikiem nie jest dniem 0", obs.pierwszy_odczyt(polowiczne) == "2026-09-02")
sprawdz("seria bez licznikow = None", obs.pierwszy_odczyt({"2026-09-01": {"wyswietlenia": 4}}) is None)

print()
print("=== 3. PELNE TYGODNIE PON-NIEDZ ===")
tyg = obs.tygodnie_netto(DNI_NIE, WCZORAJ, 6)
sprawdz("szesc tygodni, ostatni konczy sie w niedziele 4.10", len(tyg) == 6 and tyg[-1][1] == "2026-10-04" and tyg[-1][0] == "2026-09-28",
        [(x[0], x[1]) for x in tyg])
sprawdz("ostatni tydzien NIE: +4 / +7 / +11", tyg[-1][2] == {"sub": 4, "obs": 7, "osoby": 11}, tyg[-1][2])
tyg_nia = obs.tygodnie_netto(DNI_NIA, WCZORAJ, 6)
sprawdz("ostatni tydzien NIA: +7 / +14 / +21", tyg_nia[-1][2] == {"sub": 7, "obs": 14, "osoby": 21}, tyg_nia[-1][2])
sprawdz("tydzien sprzed startu pomiaru = None (nie zero)", tyg_nia[0][2] is None, tyg_nia[0])
for wczoraj, koniec in (("2026-10-04", "2026-10-04"), ("2026-10-07", "2026-10-04"), ("2026-10-10", "2026-10-04"),
                        ("2026-10-11", "2026-10-11")):
    t = obs.tygodnie_netto(DNI_NIE, wczoraj, 1)
    sprawdz("„wczoraj” %s (%s): ostatni PELNY tydzien konczy sie %s" % (wczoraj, date.fromisoformat(wczoraj).strftime("%a"), koniec),
            t[-1][1] == koniec, t)

print()
print("=== 4. WEDLUG WIEKU KONTA ===")
w_nie, w_nia = obs.wedlug_wieku(DNI_NIE), obs.wedlug_wieku(DNI_NIA)
sprawdz("NIE dzien 14: +7 / +14 / +21", w_nie[14] == {"sub": 7, "obs": 14, "osoby": 21}, w_nie.get(14))
sprawdz("NIA dzien 14: +14 / +28 / +42", w_nia[14] == {"sub": 14, "obs": 28, "osoby": 42}, w_nia.get(14))
sprawdz("NIA ma dobe 28, ale NIE ma doby 35 poza seria (30 dob danych)", 28 in w_nia and 35 not in w_nia, sorted(w_nia))
sprawdz("NIE ma dobe 35 (seria siega 5.10 = dzien 35)", 35 in w_nie and 42 not in w_nie, sorted(w_nie))
sprawdz("ten sam wiek, rozne tempo: NIA dzien 28 > NIE dzien 28", w_nia[28]["osoby"] > w_nie[28]["osoby"],
        (w_nia[28], w_nie[28]))

print()
print("=== 5. KROCZACE 7 DNI ===")
kr = dict(obs.kroczace_7(DNI_NIE, WCZORAJ, 10))
sprawdz("dziesiec dob, kazda z liczba", len(kr) == 10 and all(v is not None for v in kr.values()), kr)
sprawdz("kroczace 7 dni NIE 5.10: +7 subskr. nie, wynik z formuly",
        kr["2026-10-05"]["osoby"] == (nie(35)[0] - nie(28)[0]) + (nie(35)[1] - nie(28)[1]), kr["2026-10-05"])
dziura = {d: dict(w) for d, w in DNI_NIE.items()}
del dziura["2026-10-01"]
kr2 = dict(obs.kroczace_7(dziura, WCZORAJ, 10))
sprawdz("KONTRDOWOD: brak doby 1.10 w serii = None dla okna konczacego sie 1.10 (nie zero)", kr2["2026-10-01"] is None, kr2["2026-10-01"])
sprawdz("a KAZDE inne okno liczy sie tak samo jak bez luki (okno uzywa tylko stanow na jego koncach)",
        all(kr2[d] == kr[d] for d in kr if d != "2026-10-01"), {d: (kr2[d], kr[d]) for d in kr if d != "2026-10-01" and kr2[d] != kr[d]})

print()
print("=== 6. WSKAZNIKI ZASIEGU ===")
dni_z = {}
for i in range(14):            # 22.09 .. 5.10
    d = (date(2026, 9, 22) + timedelta(days=i)).isoformat()
    dni_z[d] = {"obcy": 10 if i < 7 else 4, "odwiedziny_profilu": 1}
for i in range(7, 14):         # komentarze: tylko ostatnie 7 dob, pomiar pelny
    d = (date(2026, 9, 22) + timedelta(days=i)).isoformat()
    dni_z[d].update({"wyswietlenia_komentarz": 20, "dz_komentarze": 5})
dni_z["2026-09-23"].update({"wyswietlenia_komentarz": 8, "dz_komentarze": 4})   # poprzedni okres: 1 doba z pomiarem
z = obs.wskazniki_zasiegu(dni_z, WCZORAJ)
sprawdz("wyswietlenia obcych: 70 -> 28, po 7 dob z pomiarem", z["obcy"] == {"przed": (70, 7), "teraz": (28, 7)}, z["obcy"])
sprawdz("wyswietlenia komentarzy: poprzedni okres tylko 1 doba z pomiarem (8), teraz 140",
        z["wyswietlenia_komentarz"] == {"przed": (8, 1), "teraz": (140, 7)}, z["wyswietlenia_komentarz"])
sprawdz("wyswietlenia na komentarz: 2.0 (8/4) -> 4.0 (140/35), tylko z dob z OBOMA polami",
        z["komentarz_na_komentarz"] == {"przed": (2.0, 1), "teraz": (4.0, 7)}, z["komentarz_na_komentarz"])
sprawdz("pole nieobecne w ogole = None, nie zero", obs.wskazniki_zasiegu({}, WCZORAJ)["obcy"]["teraz"] == (None, 0))

print()
print("=== 7. SEKCJA I RAPORT ===")
dane = {"NIE": DNI_NIE, "NIA": DNI_NIA}
tekst = "\n".join(obs.sekcja_tempo(dane, WCZORAJ))
sprawdz("naglowki czterech tabel", all(h in tekst for h in (
    "## Tempo przyrostu", "### Tydzien po tygodniu", "### Wedlug wieku konta", "### Kroczace 7 dni",
    "### Wskazniki zasiegu")), tekst[:300])
sprawdz("iloraz ostatniego tygodnia: NIA 21 / NIE 11 = 1.9x", "1.9x" in tekst, [l for l in tekst.splitlines() if "09-28..10-04" in l])
sprawdz("tygodnie sprzed pomiaru u OBU kont nie dostaja pustego wiersza",
        "08-24..08-30" not in tekst and "08-31..09-06" not in tekst, [l for l in tekst.splitlines() if "..08" in l or "..09-06" in l])
sprawdz("tydzien znany tylko jednemu kontu (NIE 7-13.09) zostaje w tabeli z „—” u drugiego",
        any(l.startswith("| 09-07..09-13") and "| —" in l for l in tekst.splitlines()))
# SUMA Z TYGODNI Z DANYMI DLA OBU KONT — liczona tu niezaleznie, z formul, nie z testowanego kodu.
konce = ["2026-09-20", "2026-09-27", "2026-10-04"]
oczek_nie = sum((nie(n_nie(d))[0] - nie(n_nie(d) - 7)[0]) + 7 for d in konce)
oczek_nia = 3 * (7 + 14)
razem = [l for l in tekst.splitlines() if "razem, 3 tyg." in l]
sprawdz("wiersz sumy z 3 tygodni z danymi dla obu: NIE %+d, NIA %+d, iloraz %.1fx" % (oczek_nie, oczek_nia, oczek_nia / oczek_nie),
        len(razem) == 1 and ("%+d" % oczek_nie) in razem[0] and ("%+d" % oczek_nia) in razem[0]
        and ("%.1fx" % (oczek_nia / oczek_nie)) in razem[0], razem)
sprawdz("KONTRDOWOD: tydzien znany jednemu kontu NIE wchodzi do sumy (suma NIE to 3 tygodnie, nie 4)",
        ("%+d" % (oczek_nie + 20)) not in (razem[0] if razem else ""), razem)
sprawdz("wiek: dzien 0 podany dla obu kont", "NIE 2026-08-31" in tekst and "NIA 2026-09-07" in tekst)
sprawdz("tydzien sprzed startu NIA to „—”, nie zero", any(l.startswith("| 09-07..09-13") or l.startswith("| 08-31..09-06") for l in tekst.splitlines())
        and "—" in tekst)
jedno = "\n".join(obs.sekcja_tempo({"NIE": DNI_NIE}, WCZORAJ))
sprawdz("jedno konto: sekcja bez kolumny ilorazu i bez wyjatku", "drugie / pierwsze" not in jedno and "### Tydzien" in jedno)
puste = "\n".join(obs.sekcja_tempo({"NIE": DNI_NIE, "NIA": {}}, WCZORAJ))
wiersze_kr = [[c.strip() for c in l.strip().strip("|").split("|")] for l in puste.splitlines() if l.startswith("| 2026-10-0")]
sprawdz("konto bez licznikow: w kroczacych 7 dniach kolumna konta i iloraz to „—” (bez wyjatku, bez dzielenia przez zero)",
        len(wiersze_kr) >= 5 and all(w[2] == "—" and w[3] == "—" and w[1] != "—" for w in wiersze_kr), wiersze_kr[:2])

obs.katalog().mkdir(parents=True, exist_ok=True)
(obs.katalog() / "dni_NIE.json").write_text(json.dumps(DNI_NIE), encoding="utf-8")
(obs.katalog() / "dni_NIA.json").write_text(json.dumps(DNI_NIA), encoding="utf-8")
rap = obs.raport(14, dzis="2026-10-06")
i_stan, i_tempo, i_dob = rap.find("## Stan i tempo"), rap.find("## Tempo przyrostu"), rap.find("## Ostatnie 14 dob")
sprawdz("raport: sekcja tempa po „Stan i tempo”, przed „Ostatnie dni”", 0 <= i_stan < i_tempo < i_dob, (i_stan, i_tempo, i_dob))

print()
print("=== 8. JAKOSC LIST CZYTELNIKOW: NAJPELNIEJSZY ZRZUT DOBY, NIE SAM OSTATNI ===")
# Zrzut potrafi byc OKROJONY (klik w zakladke pekl, grupa pusta, brak sladu bledu w pliku). Raport
# brał sam ostatni odczyt, wiec jeden taki zrzut pokazywal „0 przy liczniku 26” — u drugiego bota od
# 29.09 pusta jest ok. polowa zrzutow, reszta ma pelne listy.


def zrzut(kiedy, ile_obs, ile_sub):
    return {"kiedy": kiedy, "obserwujacy": [{"uchwyt": "x%d" % i} for i in range(ile_obs)],
            "subskrybenci": [{"uchwyt": "y%d" % i} for i in range(ile_sub)]}


liczniki = [{"kiedy": "2026-10-05T10:00:00+00:00", "subskrybenci": 25, "obserwujacy": 26},
            {"kiedy": "2026-10-05T23:48:00+00:00", "subskrybenci": 25, "obserwujacy": 26}]
zrzuty = [zrzut("2026-10-05T10:01:00+00:00", 24, 20),      # pelny
          zrzut("2026-10-05T17:00:00+00:00", 0, 0),        # okrojony
          zrzut("2026-10-05T23:49:00+00:00", 0, 0),        # okrojony i OSTATNI
          zrzut("2026-10-03T10:00:00+00:00", 22, 18)]      # starszy niz doba przed ostatnim — nie wchodzi
pl = obs.pokrycie_list(zrzuty, liczniki)
sprawdz("najpelniejszy zrzut doby, nie sam ostatni: 24 z 26 obserwujacych i 20 z 25 subskrybentow",
        (pl.get("obserwujacy_lista"), pl.get("obserwujacy_licznik"), pl.get("subskrybenci_lista"),
         pl.get("subskrybenci_licznik")) == (24, 26, 20, 25), pl)
sprawdz("w dobie sa 3 zrzuty (czwarty jest starszy niz 24 h przed ostatnim), z tego 2 okrojone",
        (pl.get("zrzutow_w_dobie"), pl.get("zrzutow_okrojonych")) == (3, 2), pl)
sprawdz("KONTRDOWOD: sam ostatni zrzut tej serii jest pusty — stary rachunek dalby 0 przy liczniku 26",
        zrzuty[2]["obserwujacy"] == [] and zrzuty[2]["subskrybenci"] == [])
wszystkie_puste = obs.pokrycie_list([zrzut("2026-10-05T10:01:00+00:00", 0, 0), zrzut("2026-10-05T23:49:00+00:00", 0, 0)],
                                    liczniki)
sprawdz("wszystkie zrzuty okrojone: bez wyjatku, 0 przy liczniku, 2 z 2 okrojone",
        wszystkie_puste.get("obserwujacy_lista") == 0 and wszystkie_puste.get("obserwujacy_licznik") == 26
        and wszystkie_puste.get("zrzutow_okrojonych") == 2, wszystkie_puste)
sprawdz("brak zrzutow albo brak licznikow = pusty wynik, nie wyjatek",
        obs.pokrycie_list([], liczniki) == {} and obs.pokrycie_list(zrzuty, []) == {})
sprawdz("uchwyty czytelnikow nie wchodza do wyniku (dane osobowe zostaja poza obserwatorium)",
        "x0" not in json.dumps(pl) and "y0" not in json.dumps(pl))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
