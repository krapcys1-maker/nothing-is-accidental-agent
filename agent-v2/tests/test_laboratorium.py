# -*- coding: utf-8 -*-
"""Laboratorium: tygodniowy raport badawczy obu kont (25.10.2026).

PO CO. Wlasciciel: „ma byc policzona predkosc przyrostu subskrybentow, chce wiedziec,
czy jak mam wiecej subskrypcji, szybciej mi subskrybentow przybywa (...) to ma byc
laboratorium badawcze". Test pilnuje rachunku na danych SYNTETYCZNYCH o znanym wyniku
(liczonym niezaleznie od testowanego kodu), z kontrdowodami:

  1. statystyka: rangi z remisami, Spearman (+1, -1, stala seria -> None), przedzial
     Poissona (znane wartosci dla 0 i 10), iloraz tempa z przedzialem, nachylenie;
  2. `tygodnie`: pelne tygodnie pon-niedz, sumy dzialan i zasiegu, luka w liczniku = None;
  3. `policz_konto`: przyrost idacy za wyswietleniami daje rho +1 z wyswietleniami,
     a dzialania niezalezne od przyrostu — brak zwiazku; reszta po zasiegu;
  4. `notki_tygodniami`: grupy wedlug tygodnia publikacji, notki mlodsze niz 3 dni
     pominiete, seria sledcza osobno;
  5. `zapisz` i podpiecie pod `obserwatorium.py zbierz --raport` (awaria nie zatrzymuje
     raportu dobowego).

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import json
import os
import pathlib
import random
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

import laboratorium as lab   # noqa: E402
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


print("=== 1. STATYSTYKA ===")
sprawdz("rangi z remisami usrednionymi", lab._rangi([3, 1, 2, 2]) == [4, 1, 2.5, 2.5], lab._rangi([3, 1, 2, 2]))
_x = [1, 5, 2, 8, 3, 9, 4, 7]
_s = lab.spearman(_x, [10 * v for v in _x])
sprawdz("Spearman: ta sama kolejnosc -> +1, p male", _s and _s["rho"] == 1.0 and _s["p"] < 0.01, _s)
_s = lab.spearman(_x, [-v for v in _x])
sprawdz("Spearman: odwrocona kolejnosc -> -1", _s and _s["rho"] == -1.0, _s)
sprawdz("KONTRDOWOD: stala seria nie ma korelacji (None, nie zero)", lab.spearman(_x, [3] * 8) is None)
sprawdz("KONTRDOWOD: ponizej 5 tygodni nie liczy", lab.spearman([1, 2, 3, 4], [1, 2, 3, 4]) is None)
_p0, _p10 = lab.przedzial_poissona(0, 4), lab.przedzial_poissona(10, 1)
# Dokladne 95% Poissona: k=0 -> 0-3,69; k=10 -> 4,80-18,39.
sprawdz("Poisson k=0 w 4 tygodniach: 0 do ok. 0,92 na tydzien",
        _p0[0] == 0 and abs(_p0[1] - 3.689 / 4) < 0.02, _p0)
sprawdz("Poisson k=10: ok. 4,8-18,4", abs(_p10[0] - 4.80) < 0.1 and abs(_p10[1] - 18.39) < 0.1, _p10)
sprawdz("KONTRDOWOD: ujemne netto nie dostaje przedzialu Poissona", lab.przedzial_poissona(-2, 4) is None)
_rr = lab.iloraz_tempa(20, 10)
# log-normalny: 2 * exp(+-1,96 * sqrt(1/20 + 1/10)) = 0,94-4,27
sprawdz("iloraz tempa 20/10 = 2,0 (95%: 0,94-4,27)", _rr == {"iloraz": 2.0, "dol": 0.94, "gora": 4.27}, _rr)
sprawdz("KONTRDOWOD: iloraz z zerem nie istnieje", lab.iloraz_tempa(5, 0) is None)
_n = lab.nachylenie([1, 2, 3, 4, 5])
sprawdz("nachylenie dokladnej prostej = 1, przedzial zerowej szerokosci",
        _n and _n["nachylenie"] == 1.0 and _n["dol"] == 1.0 and _n["gora"] == 1.0, _n)
sprawdz("KONTRDOWOD: trzy tygodnie to za malo na trend", lab.nachylenie([1, 2, 3]) is None)
sprawdz("reszty dokladnej prostej sa zerami", lab.reszty([2, 4, 6, 8], [1, 2, 3, 4]) == [0, 0, 0, 0],
        lab.reszty([2, 4, 6, 8], [1, 2, 3, 4]))

print()
print("=== 2. TYGODNIE ===")
# 12 tygodni od poniedzialku 3.08.2026. Wyswietlenia tygodnia k: 70 + 70*(k % 4);
# przyrost tygodnia k = wyswietlenia / 70 (czyli 1..4 osoby), rozlozony na niedziele.
# Nasze subskrypcje: losowe, niezalezne od przyrostu (ziarno stale).
START = date(2026, 8, 3)
los = random.Random(7)
dni, poziom = {}, 10
_oczekiwane = []
for k in range(12):
    wysw_dzien = 10 * (1 + k % 4)
    nasze = los.randint(0, 3)
    for i in range(7):
        d = START + timedelta(days=7 * k + i)
        if i == 6:
            poziom += 1 + k % 4
        dni[d.isoformat()] = {"subskrybenci": poziom, "obserwujacy": 5 + 7 * k + i, "wyswietlenia": wysw_dzien,
                              "pomiar_tresci": 1, "dz_subskrypcje": nasze, "dz_obserwacje": 1,
                              "dz_komentarze": 2, "dz_notki": 3}
    _oczekiwane.append(1 + k % 4)
# Doba przed startem — zeby pierwszy tydzien mial stan poczatkowy.
dni[(START - timedelta(days=1)).isoformat()] = {"subskrybenci": 10, "obserwujacy": 4}
WCZORAJ = (START + timedelta(days=7 * 12 - 1)).isoformat()   # niedziela
tyg = lab.tygodnie(dni, WCZORAJ)
sprawdz("dwanascie pelnych tygodni od poniedzialku", len(tyg) == 12 and tyg[0]["od"] == START.isoformat()
        and tyg[-1]["do"] == WCZORAJ, [(t["od"], t["do"]) for t in tyg[:2]])
sprawdz("przyrost netto tygodnia = roznica stanow", [t["sub"] for t in tyg] == _oczekiwane,
        [t["sub"] for t in tyg])
sprawdz("sumy tygodnia: wyswietlenia, notki, wychodzace = subskrypcje + obserwacje",
        tyg[1]["wyswietlenia"] == 140 and tyg[1]["dz_notki"] == 21
        and tyg[1]["wychodzace"] == tyg[1]["dz_subskrypcje"] + 7 and tyg[1]["pelny_pomiar"], tyg[1])
_luka = {d: dict(v) for d, v in dni.items()}
_luka[(START + timedelta(days=13)).isoformat()].pop("subskrybenci")
sprawdz("KONTRDOWOD: brak odczytu licznika na koncu tygodnia -> None, nie zero",
        lab.tygodnie(_luka, WCZORAJ)[1]["sub"] is None and lab.tygodnie(_luka, WCZORAJ)[2]["sub"] is None)

# KOPIA LISTY: zapisy brutto z kolumny daty (adresy nieczytane), tylko tygodnie przed kopia.
LISTA = _tmp / "konto_z_lista"
(LISTA / "kopie").mkdir(parents=True)
(LISTA / "kopie" / "subskrybenci-2026-08-01.csv").write_text("Email,Type,Start date\n", encoding="utf-8")
_wiersze = ["Email,Type,Start date"]
for k in range(12):
    for j in range(2 + k % 3):
        d = START + timedelta(days=7 * k + j)
        _wiersze.append('x%d_%d@example.com,Free,"%s %d, %d"' % (k, j, d.strftime("%b"), d.day, d.year))
_wiersze.append('zly@example.com,Free,"jakas data"')
(LISTA / "kopie" / "subskrybenci-2026-10-14.csv").write_text("\n".join(_wiersze) + "\n", encoding="utf-8")
_zap, _data = lab.zapisy_z_listy(LISTA)
sprawdz("lista: najnowsza kopia, zapisy na dobe, zly wiersz pominiety",
        _data == "2026-10-14" and sum(_zap.values()) == sum(2 + k % 3 for k in range(12))
        and _zap[START.isoformat()] == 1, (_data, sum(_zap.values())))
_tl = lab.tygodnie(dni, WCZORAJ, zapisy=_zap, data_kopii=_data)
sprawdz("tygodnie z lista: brutto do kopii, pozniejsze None (lista ich nie zna)",
        [t["nowi_lista"] for t in _tl[:3]] == [2, 3, 4] and _tl[-1]["nowi_lista"] is None
        and _tl[-1]["do"] > _data, [t["nowi_lista"] for t in _tl])
sprawdz("KONTRDOWOD: bez kopii listy brak zapisow", lab.zapisy_z_listy(_tmp / "pusto") == ({}, None))

print()
print("=== 3. DAWKA -> SKUTEK ===")
DZIS = (START + timedelta(days=7 * 12)).isoformat()
wynik = lab.policz_konto(dni, _tmp / "pusto", None, WCZORAJ, DZIS)
z = wynik["zaleznosci"]
sprawdz("przyrost idzie za wyswietleniami: rho +1, istotne",
        z["przyrost~wyswietlenia"]["rho"] == 1.0 and z["przyrost~wyswietlenia"]["p"] < 0.05, z["przyrost~wyswietlenia"])
_niez = z["przyrost~nasze_subskrypcje"]
sprawdz("KONTRDOWOD: dzialania niezalezne od przyrostu — nieistotne", _niez and _niez["p"] >= 0.05, _niez)
sprawdz("po odjeciu zasiegu nie ma czego tlumaczyc (reszty stale -> None)",
        z["reszta_po_zasiegu~wychodzace"] is None, z["reszta_po_zasiegu~wychodzace"])
sprawdz("tempo 4 tygodni i iloraz do 4 wczesniejszych",
        wynik["tempo_4t"]["razem"] == sum(_oczekiwane[-4:]) and wynik["tempo_4t_wczesniej"]["razem"] == sum(_oczekiwane[-8:-4])
        and wynik["iloraz_tempa"]["iloraz"] == 1.0, (wynik["tempo_4t"], wynik["iloraz_tempa"]))
sprawdz("trend bez wykrywalnego nachylenia (cykl 1-4) ma przedzial przez zero",
        wynik["trend"]["dol"] < 0 < wynik["trend"]["gora"], wynik["trend"])
sprawdz("bez listy zaleznosci licza netto z licznika", wynik["przyrost_w_zaleznosciach"] == "sub")
# Licznik konta od tygodnia 7 (jak NIE od 7.09), lista od poczatku: lista obejmuje 10 tygodni.
_dni_krotkie = {d: {k: v for k, v in w.items() if k != "subskrybenci" or d >= (START + timedelta(days=41)).isoformat()}
                for d, w in dni.items()}
_zl = lab.policz_konto(_dni_krotkie, LISTA, None, WCZORAJ, DZIS)
sprawdz("z dluzsza lista zaleznosci licza zapisy z listy", _zl["przyrost_w_zaleznosciach"] == "nowi_lista"
        and _zl["kopia_listy"] == "2026-10-14" and _zl["zaleznosci"]["przyrost~wyswietlenia"]["n"] == 10,
        (_zl["przyrost_w_zaleznosciach"], _zl["zaleznosci"]["przyrost~wyswietlenia"]))
sprawdz("nowi na 1000 wyswietlen: suma przyrostu / suma wyswietlen",
        wynik["na_1000_wyswietlen"] == round(1000 * sum(_oczekiwane) / sum(t["wyswietlenia"] for t in tyg), 2),
        wynik["na_1000_wyswietlen"])

print()
print("=== 4. NOTKI WEDLUG TYGODNIA PUBLIKACJI ===")
KAT = _tmp / "konto_notek"
KAT.mkdir()
_dz, _st = [], []
for i, (dzien, wysw, slow, seria) in enumerate([
        ("2026-10-12", 20, 60, False), ("2026-10-14", 10, 110, False), ("2026-10-16", 40, 50, True),
        ("2026-10-20", 8, 120, False), ("2026-10-23", 99, 55, True)]):
    _dz.append({"rodzaj": "notka", "udane": True, "id": "n%d" % i, "kiedy": dzien + "T11:00:00+00:00",
                "slow": slow, "przeslanie_id": "p%d" % i if seria else None})
    _st += [{"rodzaj": "notka", "id": "n%d" % i, "wyswietlenia": wysw // 2},
            {"rodzaj": "notka", "id": "n%d" % i, "wyswietlenia": wysw}]
_dz.append({"rodzaj": "notka", "udane": False, "id": "zla", "kiedy": "2026-10-13T11:00:00+00:00"})
(KAT / "dziennik.jsonl").write_text("".join(json.dumps(x) + "\n" for x in _dz), encoding="utf-8")
(KAT / "statystyki.jsonl").write_text("".join(json.dumps(x) + "\n" for x in _st), encoding="utf-8")
nt = lab.notki_tygodniami(KAT, "2026-10-25")
sprawdz("dwa tygodnie publikacji; notka z 23.10 (2 dni) jeszcze nie wchodzi",
        [n["tydzien"] for n in nt] == ["2026-10-12", "2026-10-19"] and nt[1]["notek"] == 1, nt)
sprawdz("mediana z najwyzszego odczytu, mediana slow, seria osobno",
        nt[0]["mediana_wysw"] == 20 and nt[0]["mediana_slow"] == 60 and nt[0]["seria_notek"] == 1
        and nt[0]["seria_mediana_wysw"] == 40, nt[0])
sprawdz("KONTRDOWOD: nieudana notka nie liczy sie", nt[0]["notek"] == 3, nt[0])

print()
print("=== 4b. SERIE: CO SIE KLIKA (KATY I KATEGORIE) ===")
SER = _tmp / "konto_serii"
SER.mkdir()
_dz, _st = [], []
for i, (pid, wysw) in enumerate([("202610200900-501-kuriozum", 40), ("202610201500-501-mechanizm", 10),
                                 ("202610210900-502-kuriozum", 20), (None, 7)]):
    _dz.append({"rodzaj": "notka", "udane": True, "id": "s%d" % i, "kiedy": "2026-10-20T10:00:00+00:00",
                "przeslanie_id": pid})
    _st.append({"rodzaj": "notka", "id": "s%d" % i, "wyswietlenia": wysw})
(SER / "dziennik.jsonl").write_text("".join(json.dumps(x) + "\n" for x in _dz), encoding="utf-8")
(SER / "statystyki.jsonl").write_text("".join(json.dumps(x) + "\n" for x in _st), encoding="utf-8")
(SER / "sledztwa.jsonl").write_text(json.dumps({"run_id": 501, "kategoria": "PREMIERA_MODELU"}) + "\n"
                                    + json.dumps({"run_id": 502, "kategoria": "PRACA_EKONOMIA"}) + "\n",
                                    encoding="utf-8")
_ser = lab.katy_serii(SER, "2026-10-25")
sprawdz("katy serii: mediana wedlug rodzaju kata (kuriozum 30 z 2 notek, mechanizm 10)",
        _ser["katy"] == [{"nazwa": "KURIOZUM", "notek": 2, "mediana_wysw": 30.0},
                         {"nazwa": "MECHANIZM", "notek": 1, "mediana_wysw": 10}], _ser["katy"])
sprawdz("i wedlug kategorii historii z numeru przebiegu sledztwa",
        {w["nazwa"]: w["notek"] for w in _ser["kategorie"]} == {"PREMIERA_MODELU": 2, "PRACA_EKONOMIA": 1},
        _ser["kategorie"])
sprawdz("KONTRDOWOD: zwykla notka sprzed 26.10 nie miesza sie z seriami", _ser["zwykle_od_26_10"] == [])

print()
print("=== 5. ZAPIS I PODPIECIE ===")
obs.katalog().mkdir(parents=True, exist_ok=True)
(obs.katalog() / "dni_NIE.json").write_text(json.dumps(dni), encoding="utf-8")
(obs.katalog() / "zrodla_NIE.json").write_text(json.dumps(
    {"okno": {"od": "2026-09-24", "do": "2026-10-24"}, "razem_panel": 14,
     "przypisane": {"razem": 15, "wg_rodzaju": {"restack": 5, "notka": 4, "komentarz": 4}}}), encoding="utf-8")
w = lab.policz(wczoraj=WCZORAJ)
sprawdz("oba konta w wyniku; konto bez danych nie wywraca rachunku",
        set(w["konta"]) == {"NIE", "NIA"} and w["konta"]["NIA"]["tempo_4t"] is None
        if "tempo_4t" in w["konta"]["NIA"] else set(w["konta"]) == {"NIE", "NIA"}, list(w["konta"]))
t = lab.tekst(w)
sprawdz("tekst: predkosc, dawka -> skutek, tabela tygodni, atrybucja",
        "## NIE" in t and "## NIA" in t and "Predkosc przyrostu" in t and "Dawka -> skutek" in t
        and "| tydzien od |" in t and "restack 5, komentarz 4, notka 4" in t, t[:600])
p = lab.zapisz()
sprawdz("zapis do obserwatorium: laboratorium.md i .json",
        p.name == "laboratorium.md" and p.exists() and (obs.katalog() / "laboratorium.json").exists())
_kod = pathlib.Path("agent-v2/obserwatorium.py").read_text(encoding="utf-8")
sprawdz("zegar obserwatorium (zbierz --raport) liczy laboratorium, a awaria go nie zatrzymuje",
        "laboratorium.zapisz()" in _kod and _kod.index('(katalog() / "raport.md").write_text(tekst')
        < _kod.index("laboratorium.zapisz()")
        and "laboratorium: nie policzone" in _kod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
