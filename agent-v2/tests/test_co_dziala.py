# -*- coding: utf-8 -*-
"""Co dziala (27.10.2026): statystyki NIE jako produktu — formaty, wymiary, eksperymenty po seriach, koszt, zaklady.

PO CO. Raport ma odpowiadac redaktorowi, CO Z TEGO, CO PISZEMY, DZIALA — a przy kilkunastu notkach w grupie najgorsze,
co mozna zrobic, to ogloscic zwyciezce z szumu. Test na sztucznych danych (bez sieci, bez modelu) pilnuje:
  1. klasyfikacji notek (format z `przeslanie_id`, `typ`; oba formaty identyfikatora; MYSL, promocja, rozliczenie);
  2. porownan: wyrazna roznica = „lepiej”, ta sama populacja = „brak dowodu”, garstka notek = „za malo danych”;
  3. eksperymentu po SERIACH (E22): ramie na cala serie, bootstrap po seriach, prog serii na ramie;
  4. kosztu (grupy etapow, koszt tematu i notki), sprawdzenia faktow z pola `fc`, potoku, czujnika;
  5. calosci: raport z pustych danych nie pada, z pelnych ma wszystkie sekcje i wnioski; zapis plikow i historia.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_co_dziala.py
"""
import json
import pathlib
import random
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import co_dziala as cd   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:900]))


DZIS = date(2026, 11, 20)
START = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)


def stat(w, odw=0):
    return {"wyswietlenia": w, "odwiedziny_profilu": odw, "interakcje": {"Like": 1}}


def dane_puste():
    return {"dziennik": [], "pomiary": {}, "zapisy": {}, "sledztwa": [], "kolejka": [], "co_klika": [],
            "koszty": {"run": {}, "purpose": []}, "dni": {}}


def zbuduj(formaty, dni=24, seed=3):
    """Sztuczna historia: co doba po jednej notce z kazdego formatu (wartosc sredniej wysw. wg formatu), wspolne tlo tygodnia.

    `formaty` = {nazwa: (srednia_wysw, ile_notek)}; notki rozkladane po dobach na przemian, zeby grupy dzielily tygodnie."""
    r = random.Random(seed)
    d = dane_puste()
    nr = 0
    for dzien in range(dni):
        tlo = 1.0 + 0.3 * (dzien % 7 == 0)
        for fmt, (srednia, ile) in formaty.items():
            if dzien >= ile:
                continue
            nr += 1
            t = START + timedelta(days=dzien, hours=nr % 5)
            e = {"kiedy": t.isoformat(), "rodzaj": "notka", "udane": True, "id": str(1000 + nr), "slow": 60 + 7 * (nr % 9),
                 "tekst": "Note %d of format %s." % (nr, fmt), "typ": "CIEKAWOSTKA", "forma": "LISTA", "model": "deepseek-flash"}
            if fmt == "seria":
                e["przeslanie_id"] = "20261026%04d-%d-%d-reveal" % (dzien, 600 + dzien // 4, 1 + dzien % 4)
                e["kat_serii"] = {"rodzaj": "REVEAL", "k": 1 + dzien % 4}
            elif fmt == "rozkmina":
                e["przeslanie_id"] = "20261026%04d-%d-%d-motive" % (dzien, 700 + dzien // 4, 1 + dzien % 4)
            elif fmt == "mysl":
                e["typ"] = "MYSL"
            elif fmt == "promocja":
                e["typ"] = "ARTYKUL"
            w = max(1, int(round(srednia * tlo * r.lognormvariate(0, 0.35))))
            d["dziennik"].append(e)
            d["pomiary"][e["id"]] = stat(w, odw=1 if w > 25 else 0)
    d["sledztwa"] = [{"run_id": str(700 + k), "rozkmina": True, "przeslania": ["A", "B", "C", "D"],
                      "kiedy": (START + timedelta(days=4 * k)).isoformat()} for k in range(6)]
    return d


print("=== 1. KLASYFIKACJA NOTEK ===")
R = {"700", "701"}
for opis, e, oczek in (
        ("seria (nowy format identyfikatora)", {"przeslanie_id": "202610251853-499-3-power_shift"}, "seria"),
        ("seria (stary format identyfikatora)", {"przeslanie_id": "202610091321-394-motyw"}, "seria"),
        ("rozkmina po numerze przebiegu", {"przeslanie_id": "202610261848-700-1-reveal"}, "rozkmina"),
        ("notka rozliczajaca", {"przeslanie_id": "202611011200-9-1-rozliczenie"}, "rozliczenie"),
        ("MYSL bez przeslania", {"typ": "MYSL"}, "mysl"),
        ("promocja artykulu", {"typ": "ARTYKUL"}, "promocja"),
        ("zwykla z banku", {"typ": "CIEKAWOSTKA"}, "zwykla"),
        ("przeslanie wygrywa z typem", {"typ": "MYSL", "przeslanie_id": "202610251853-499-3-power_shift"}, "seria")):
    sprawdz("format: %s" % opis, cd.format_notki(e, R) == oczek, cd.format_notki(e, R))
sprawdz("numer przebiegu z obu formatow identyfikatora; z braku — pusty",
        cd._run_z_przeslania({"przeslanie_id": "202610251853-499-3-x"}) == "499"
        and cd._run_z_przeslania({"przeslanie_id": "202610091321-394-motyw"}) == "394"
        and cd._run_z_przeslania({}) == "" and cd._run_z_przeslania({"przeslanie_id": "zle"}) == "")
gr = cd.grupowania(R, {"499": "RYZYKO_BEZPIECZENSTWO"})
e = {"kiedy": "2026-11-02T17:30:00+00:00", "slow": 95, "przeslanie_id": "202610251853-499-3-power_shift",
     "kat_serii": {"rodzaj": "POWER_SHIFT"}, "konczy_pytaniem": True, "typ": "CIEKAWOSTKA"}
sprawdz("wymiary: dlugosc 91-110, pora 16-20 UTC, poniedzialek, pozycja nr 3, kat z `kat_serii`, kategoria z rekordu sledztwa, pytanie tak",
        gr["dlugosc"][1](e) == "91-110 slow" and gr["pora"][1](e) == "16-20 UTC" and gr["dzien"][1](e) == "pon"
        and gr["pozycja"][1](e) == "nr 3" and gr["kat"][1](e) == "POWER_SHIFT" and gr["kategoria"][1](e) == "RYZYKO_BEZPIECZENSTWO"
        and gr["pytanie"][1](e) == "tak", [(k, v[1](e)) for k, v in gr.items()])
sprawdz("kat starego identyfikatora = ostatni czlon wielkimi literami; zwykla notka nie ma kata ani pozycji",
        gr["kat"][1]({"przeslanie_id": "202610091321-394-motyw"}) == "MOTYW" and gr["pozycja"][1]({}) == "brak")
sprawdz("filtry wymiarow: kat i pozycja tylko dla serii, styk tylko dla banku, forma tylko gdy jest",
        gr["kat"][2](e) and not gr["kat"][2]({"typ": "CIEKAWOSTKA"}) and not gr["styk"][2](e) and gr["styk"][2]({"typ": "CIEKAWOSTKA"})
        and not gr["forma"][2]({}) and gr["forma"][2]({"forma": "LISTA"}))

print()
print("=== 2. PORZADNA ROZNICA, TA SAMA POPULACJA, GARSTKA ===")
d = zbuduj({"zwykla": (10, 24), "seria": (30, 24), "rozkmina": (10, 24), "mysl": (10, 4)})
w = cd.policz(d, od="2026-10-26", dzis=DZIS)
g = w["formaty"]["grupy"]
sprawdz("odniesienie = zwykla; 24 notki w kazdym z trzech formatow glownych, 4 w MYSL",
        w["formaty"]["odniesienie"] == "zwykla" and g["zwykla"]["n"] == 24 and g["seria"]["n"] == 24 and g["mysl"]["n"] == 4,
        {k: v["n"] for k, v in g.items()})
sprawdz("seria o trzykrotnie wiekszym zasiegu: werdykt „lepiej”, przedzial nad 1, stosunek rzedu 3",
        g["seria"]["werdykt"].startswith("lepiej") and g["seria"]["przedzial_95"][0] > 1 and 2.0 < g["seria"]["stosunek"] < 4.5, g["seria"])
sprawdz("rozkmina z tym samym rozkladem co bank: brak dowodu roznicy, przedzial obejmuje 1",
        g["rozkmina"]["werdykt"].startswith("brak dowodu") and g["rozkmina"]["przedzial_95"][0] < 1 < g["rozkmina"]["przedzial_95"][1], g["rozkmina"])
sprawdz("cztery notki MYSL: „za malo danych”, nigdy „lepiej/gorzej” — i grupa oznaczona jako za mala",
        g["mysl"]["werdykt"].startswith("za malo danych") and g["mysl"]["n"] >= cd.MIN_W_GRUPIE, g["mysl"])
sprawdz("kolumny dodatkowe: mediana wyswietlen, odsetek notek z odwiedzinami, zapisy",
        g["seria"]["mediana_wysw"] > g["zwykla"]["mediana_wysw"] and 0 <= g["seria"]["z_odwiedzinami"] <= 1 and g["seria"]["zapisy"] == 0, g["seria"])
tekst_wnioskow = " ".join(w["wnioski"])
sprawdz("wnioski: seria „PISAC CZESCIEJ”, rozkmina i MYSL jako brak dowodu, bez sztucznych werdyktow",
        "PISAC CZESCIEJ: seria" in tekst_wnioskow and "BRAK DOWODU: rozkmina" in tekst_wnioskow and "BRAK DOWODU: mysl" in tekst_wnioskow
        and "PISAC RZADZIEJ" not in tekst_wnioskow, w["wnioski"])
gorsza = zbuduj({"zwykla": (30, 24), "seria": (10, 24)})
wg = cd.policz(gorsza, od="2026-10-26", dzis=DZIS)
sprawdz("seria o jedna trzecia slabsza: „PISAC RZADZIEJ” z werdyktem „gorzej”",
        wg["formaty"]["grupy"]["seria"]["werdykt"].startswith("gorzej") and "PISAC RZADZIEJ: seria" in " ".join(wg["wnioski"]), wg["formaty"]["grupy"]["seria"])
d["zapisy"][d["dziennik"][0]["id"]] = 2
w2 = cd.policz(d, od="2026-10-26", dzis=DZIS)
sprawdz("zapisy przypisane notce trafiaja do kolumny grupy i do odbioru", sum(x["zapisy"] for x in w2["formaty"]["grupy"].values()) == 2, w2["formaty"]["grupy"])
sprawdz("tlo tygodnia liczone ze WSZYSTKICH notek od startu pomiaru; wiersze epoki tylko od `od`",
        len(cd.wiersze_epoki(d, "2026-11-10")) < len(cd.wiersze_epoki(d, "2026-10-26"))
        and all(x["dzien"] >= "2026-11-10" for x in cd.wiersze_epoki(d, "2026-11-10")))
sprawdz("notka z zerem wyswietlen po 72 h nie wchodzi do porownan, ale jest policzona osobno",
        (lambda dd: (dd["pomiary"].__setitem__(dd["dziennik"][5]["id"], stat(0)), cd.zero_wyswietlen(dd, "2026-10-26"))[1])(zbuduj({"zwykla": (10, 24)})) == 1)

print()
print("=== 3. E22: ROZNICA PO SERIACH, NIE PO NOTKACH ===")


def dane_e22(sr_on, sr_off, serii_on=10, serii_off=10, seed=5, efekt_serii=0.0):
    """`efekt_serii` = odchylenie logarytmu wspolnego mnoznika calej serii (notki jednej serii nie sa niezalezne)."""
    r = random.Random(seed)
    d = dane_puste()
    nr = 0
    for k in range(serii_on + serii_off):
        wspolny = r.lognormvariate(0, efekt_serii) if efekt_serii else 1.0
        ramie = "on" if k % 2 == 0 else "off"
        if (ramie == "on" and k // 2 >= serii_on) or (ramie == "off" and k // 2 >= serii_off):
            continue
        for poz in range(1, 5):
            nr += 1
            e = {"kiedy": (START + timedelta(days=k, hours=poz)).isoformat(), "rodzaj": "notka", "udane": True, "id": str(5000 + nr),
                 "slow": 45 if ramie == "on" else 90, "tekst": "x", "typ": "CIEKAWOSTKA",
                 "przeslanie_id": "202610290000-%d-%d-reveal" % (800 + k, poz), "eksperymenty": {"dlugosc_serii": ramie}}
            d["dziennik"].append(e)
            d["pomiary"][e["id"]] = stat(max(1, int(round((sr_on if ramie == "on" else sr_off) * wspolny * r.lognormvariate(0, 0.25)))))
    return d


rows = cd.wiersze_epoki(dane_e22(20, 10), "2026-10-26")
ps = cd.porownanie_po_seriach(rows, "dlugosc_serii")
sprawdz("10 serii na ramie, krotsze maja dwa razy wiekszy zasieg: „lepiej”, stosunek on/off okolo 2, dolny kraniec przedzialu nad 1",
        ps["werdykt"] == "lepiej" and 1.4 < ps["stosunek"] < 2.8 and ps["przedzial_95"][0] > 1
        and ps["ramiona"]["on"]["serii"] == 10 and ps["ramiona"]["on"]["notek"] == 40 and ps["ramiona"]["on"]["mediana_slow"] == 45
        and ps["ramiona"]["off"]["mediana_slow"] == 90, ps)
rows0 = cd.wiersze_epoki(dane_e22(10, 10), "2026-10-26")
ps0 = cd.porownanie_po_seriach(rows0, "dlugosc_serii")
sprawdz("te same rozklady: „brak dowodu roznicy”, przedzial obejmuje 1", ps0["werdykt"] == "brak dowodu roznicy" and ps0["przedzial_95"][0] < 1 < ps0["przedzial_95"][1], ps0)
rows3 = cd.wiersze_epoki(dane_e22(20, 10, serii_on=3, serii_off=3), "2026-10-26")
ps3 = cd.porownanie_po_seriach(rows3, "dlugosc_serii")
sprawdz("trzy serie na ramie: „za malo serii”, bez stosunku — nawet gdy roznica jest duza",
        ps3["werdykt"].startswith("za malo serii") and ps3["stosunek"] is None, ps3)
sprawdz("brak notek w ramionach: puste ramiona i „za malo serii”, bez wyjatku",
        cd.porownanie_po_seriach([], "dlugosc_serii")["werdykt"].startswith("za malo serii"))
rows_k = cd.wiersze_epoki(dane_e22(10, 10, serii_on=12, serii_off=12, efekt_serii=0.7), "2026-10-26")
po_seriach = cd.porownanie_po_seriach(rows_k, "dlugosc_serii")
po_notkach = cd.tabela([x for x in rows_k if (x["wpis"].get("eksperymenty") or {}).get("dlugosc_serii") in ("on", "off")],
                       __import__("eksperymenty")._grupujacy("eksperyment:dlugosc_serii"), "off")["grupy"]["on"]
szer = lambda pr: pr[1] - pr[0]   # noqa: E731
sprawdz("KONTRDOWOD: przy silnym efekcie serii bootstrap po NOTKACH dawalby wyraznie wezszy przedzial niz po seriach — "
        "to wlasnie bylby falszywy werdykt, ktorego nie chcemy",
        szer(po_notkach["przedzial_95"]) < 0.7 * szer(po_seriach["przedzial_95"]), (po_notkach["przedzial_95"], po_seriach["przedzial_95"]))
we = cd.policz(dane_e22(20, 10), od="2026-10-26", dzis=date(2026, 11, 2))["eksperymenty"]
sprawdz("raport: `dlugosc_serii` ma status „trwa” i tabele po seriach; `pora_notki` jeszcze „zaplanowany”; zakonczone sa „zakonczony”",
        we["dlugosc_serii"]["status"] == "trwa" and "po_seriach" in we["dlugosc_serii"] and we["pora_notki"]["status"] == "zaplanowany"
        and we["krotka_notka"]["status"] == "zakonczony", {k: v["status"] for k, v in we.items()})

print()
print("=== 4. KOSZT, SPRAWDZENIE FAKTOW, POTOK, CZUJNIK ===")
sprawdz("grupy kosztu: etapy sledztwa, bank, komentarze, artykul, fact-check, zaklady; nieznany etap = „inne”",
        [cd.grupa_kosztu(p) for p in ("seria_lekka", "rozkmina_wybor", "classify", "factcheck", "naprawa_artykulu", "write", "restack_opus",
                                      "cele", "zaklady_wyciag", "rozbior", "nowe_modele", "etap_przyszlosci")]
        == ["sledztwo i rozkmina", "sledztwo i rozkmina", "sledztwo i rozkmina", "sprawdzenie faktow i naprawa",
            "sprawdzenie faktow i naprawa", "artykul (pisanie, recenzja, okladka)", "komentarze, odpowiedzi, restacki",
            "komentarze, odpowiedzi, restacki", "zaklady", "notki z banku (szukanie, rozbior, pisanie)", "rejestr modeli", "inne"],
        [cd.grupa_kosztu(p) for p in ("seria_lekka", "classify", "factcheck", "write", "cele", "etap_przyszlosci")])
koszty = {"run": {"700": 0.12, "701": 0.10, "600": 0.30},
          "purpose": [("2026-11-18", "factcheck", 0.5), ("2026-11-19", "seria_lekka", 0.1), ("2026-11-01", "write", 2.0),
                      ("2026-11-19", "zaklady_notka", 0.01)]}
kg7 = cd.koszt_wg_grup(koszty, "2026-11-13", "2026-11-20")
sprawdz("koszt wedlug grup w oknie: sortowany malejaco, poza oknem odpada", list(kg7) == ["sprawdzenie faktow i naprawa", "sledztwo i rozkmina", "zaklady"]
        and kg7["sprawdzenie faktow i naprawa"] == 0.5, kg7)
dk = zbuduj({"seria": (30, 8), "rozkmina": (30, 8)})
dk["koszty"] = {"run": {str(600 + k): 0.1 for k in range(2)} | {str(700 + k): 0.2 for k in range(2)}, "purpose": []}
rk = cd.wiersze_epoki(dk, "2026-10-26")
ks = cd.koszt_serii(dk, rk, {"700", "701", "702"}, "2026-10-26")
sprawdz("koszt serii: temat, notka i 1000 wyswietlen osobno dla serii i rozkminy; dzielony przez notki, ktore wyszly",
        ks["seria"]["tematow"] == 2 and ks["seria"]["koszt_razem"] == 0.2 and ks["rozkmina"]["koszt_razem"] == 0.4
        and ks["seria"]["notek_wydanych"] == 8 and ks["seria"]["koszt_notki"] == 0.025 and ks["seria"]["koszt_na_1000_wysw"] > 0, ks)
dfc = zbuduj({"zwykla": (10, 4), "seria": (10, 3)})
for i, e in enumerate(dfc["dziennik"]):
    e["fc"] = {"twierdzen": 3, "obalonych": 1 if i % 2 == 0 else 0, "naprawiona": i % 2 == 0, "zastrzezenia": i == 1, "nie_sprawdzone": False}
dfc["dziennik"][0].pop("fc")
fc = cd.sprawdzenie_faktow(dfc, set(), "2026-10-26")
sprawdz("fc: odsetki per format, notki bez pola policzone osobno", fc["bez_pola"] == 1 and fc["formaty"]["seria"]["n"] == 3
        and fc["formaty"]["zwykla"]["n"] == 3 and fc["formaty"]["seria"]["twierdzen_na_notke"] == 3.0, fc)
dp = dane_puste()
dp["sledztwa"] = [{"run_id": "800", "przeslania": ["A", "B", "C", "D"], "kiedy": "2026-11-01T13:00:00+00:00"},
                  {"run_id": "801", "przeslania": ["A", "B"], "kiedy": "2026-11-03T13:00:00+00:00", "rozkmina": True}]
dp["dziennik"] = [{"kiedy": "2026-11-02T13:00:00+00:00", "rodzaj": "notka", "udane": True, "id": "1", "przeslanie_id": "202611011300-800-1-reveal"},
                  {"kiedy": "2026-11-03T13:00:00+00:00", "rodzaj": "notka", "udane": True, "id": "2", "przeslanie_id": "202611011300-800-2-motive"}]
dp["kolejka"] = [{"id": "202611011300-800-3-people", "wazny_do": "2026-11-05T00:00:00+00:00"},
                 {"id": "202611011300-800-4-verdict", "wazny_do": "2026-12-30T00:00:00+00:00"},
                 {"id": "202611011300-800-2-motive", "wazny_do": "2026-11-05T00:00:00+00:00"},
                 {"id": "x", "wazny_do": "2026-12-30T00:00:00+00:00", "pominiety": True}]
po = cd.potok(dp, {"801"}, "2026-10-26", datetime(2026, 11, 20, tzinfo=timezone.utc))
sprawdz("potok: 2 sledztwa (1 rozkmina), 6 notek wyprodukowanych, 2 wyszly; kolejka: 1 wygasla, 1 czeka, 1 pominieta; opoznienie 1 doba",
        po == {"sledztw": 2, "w_tym_rozkmin": 1, "notek_wyprodukowanych": 6, "notek_wyszlo": 2, "kolejka_czeka": 1,
               "kolejka_wygaslo": 1, "kolejka_pominietych": 1, "dni_do_pierwszej_notki_mediana": 1.0}, po)
dc = dane_puste()
dc["co_klika"] = [{"temat": "A post", "kanal": "Substack x", "przebicie": 3.1, "reakcje": 90, "data": "2026-11-18", "wykryto": "2026-11-19T10:00:00+00:00"},
                  {"temat": "Old", "kanal": "Substack y", "przebicie": 2.0, "reakcje": 50, "data": "2026-10-01", "wykryto": "2026-10-02T10:00:00+00:00"}]
c = cd.czujnik(dc, datetime(2026, 11, 20, tzinfo=timezone.utc))
sprawdz("czujnik: lacznie 2, z 7 dni 1, z 28 dni 1, 2 publikacje, najmocniejsze przebicie pierwsze",
        c["wszystkich"] == 2 and c["ostatnie_7"] == 1 and c["ostatnie_28"] == 1 and c["publikacji"] == 2 and c["top"][0]["przebicie"] == 3.1, c)
sprawdz("wzrost bez dob z obserwatorium = puste (nie wyjatek)", cd.wzrost(dane_puste(), DZIS) == {})

print()
print("=== 5. CALY RAPORT: PUSTE I PELNE DANE, ZAPIS, HISTORIA ===")
wp = cd.policz(dane_puste(), dzis=DZIS)
tp = cd.tekst(wp)
sprawdz("z pustych danych: raport sie buduje, mowi „za wczesnie”, nie dzieli przez zero", "Za wczesnie" in tp and wp["notek_z_pomiarem"] == 0, tp[:400])
tpelny = cd.tekst(w)
sprawdz("pelny raport ma wszystkie sekcje (wnioski, formaty, wymiary, najlepsze, eksperymenty, koszt, fakty, potok, wzrost, zaklady, czujnik)",
        all(h in tpelny for h in ("## Wnioski", "## 1. Formaty", "## 2. Wymiary notki", "### Kat serii", "### Dlugosc notki",
                                  "## 3. Najczesciej czytane", "## 4. Eksperymenty", "## 5. Koszt", "## 6. Sprawdzenie faktow",
                                  "## 7. Potok", "## 8. Wzrost", "## Ksiega zakladow", "## 10. Czujnik")), [l for l in tpelny.splitlines() if l.startswith("#")])
sprawdz("raport podaje przedzial 95% i mowi o minimum notek (uczciwie o mocy)", "[" in tpelny and "nie pada zaden" in tpelny)
sprawdz("najlepsze notki: osiem wierszy z formatem, posortowane malejaco", len(w["najlepsze"]) == 8
        and [n["wysw"] for n in w["najlepsze"]] == sorted((n["wysw"] for n in w["najlepsze"]), reverse=True))
import eksperymenty    # noqa: E402,F401
(config.DATA_DIR / "dziennik.jsonl").write_text("".join(json.dumps(e) + "\n" for e in d["dziennik"][:3]), encoding="utf-8")
p = cd.zapisz("2026-10-26")
sprawdz("zapis: `co_dziala.md` i `.json` w katalogu obserwatorium", p.exists() and p.with_suffix(".json").exists()
        and json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))["od"] == "2026-10-26", p)
cd.zapisz("2026-10-26")
historia = [json.loads(x) for x in (config.DATA_DIR / cd.PLIK_HISTORII).read_text(encoding="utf-8").splitlines() if x.strip()]
sprawdz("historia: jedna linia na dobe (drugi zapis tego samego dnia jej nie dubluje)", len(historia) == 1 and "formaty" in historia[0], historia)
kod_obs = open("agent-v2/obserwatorium.py", encoding="utf-8").read()
sprawdz("obserwatorium woła `co_dziala.zapisz` przy `zbierz --raport`, a jego awaria nie zatrzymuje raportu dobowego",
        "co_dziala.zapisz()" in kod_obs and "co dziala: nie policzone" in kod_obs)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
