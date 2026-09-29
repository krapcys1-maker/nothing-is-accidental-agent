# -*- coding: utf-8 -*-
"""Pomiar zmian: eksperymenty przeplatane i statystyki z przedzialem (27.09.2026).

PO CO. Wlasciciel: „jak cos bedziemy zmieniac, zeby wiedziec, co przynioslo
skutek, a co nie". Zasieg spadl we wrzesniu o 55%, wiec „przed i po" klamie;
decyduje porownanie w tym samym okresie. Test pilnuje, z kontrdowodami:
  1. `stages.ramie`: pusto = nic sie nie zmienia; przydzial deterministyczny,
     udzial zgodny z konfiguracja, rozny miedzy dniami;
  2. prawdziwe `notki_dnia`: ramie „off" pisze bez wniosku, „on" z wnioskiem,
     a wynik niesie ramie do dziennika;
  3. `eksperymenty.porownaj`: wyrazna roznica = „lepiej", brak roznicy = „brak
     dowodu", mala grupa = „za malo danych"; przedzial obejmuje stosunek;
  4. droga do dziennika: wersja kodu i ramiona.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import math
import pathlib
import random
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import eksperymenty   # noqa: E402
import stages         # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. PRZYDZIAL DO RAMIENIA ===")
_stare = dict(config.EKSPERYMENTY)
config.EKSPERYMENTY = {}
sprawdz("pusta konfiguracja — eksperyment nie trwa", stages.ramie("wniosek", 0, "2026-10-01") == "")
config.EKSPERYMENTY = {"wniosek": 0.7}
sprawdz("deterministycznie: ten sam dzien i miejsce = to samo ramie",
        len({stages.ramie("wniosek", 3, "2026-10-01") for _ in range(5)}) == 1)
_ramiona = [stages.ramie("wniosek", m, "2026-10-%02d" % d) for d in range(1, 29) for m in range(0, 60)]
_udzial = _ramiona.count("on") / len(_ramiona)
sprawdz("udzial ramienia on zgodny z konfiguracja (0,7 +- 0,03)", abs(_udzial - 0.7) < 0.03, _udzial)
sprawdz("KONTRDOWOD: rozne dni daja rozne przydzialy",
        len({tuple(stages.ramie("wniosek", m, "2026-10-%02d" % d) for m in range(5)) for d in range(1, 15)}) > 3)
sprawdz("inny eksperyment nie trwa, mimo ze trwa wniosek", stages.ramie("glebia", 0, "2026-10-01") == "")
config.EKSPERYMENTY = {"wniosek": {"udzial": 0.7, "od": "2026-09-28", "do": "2026-10-25"}}
sprawdz("KONTRDOWOD: przed startem okna eksperyment nie trwa",
        stages.ramie("wniosek", 0, "2026-09-27") == "")
sprawdz("KONTRDOWOD: po koncu okna eksperyment sam sie konczy",
        all(stages.ramie("wniosek", m, "2026-10-26") == "" for m in range(10)))
_w_oknie = [stages.ramie("wniosek", m, "2026-%s" % d) for d in ("09-28", "10-10", "10-25") for m in range(40)]
sprawdz("w oknie (takze pierwszy i ostatni dzien) notki trafiaja do on/off, ok. 70% on",
        set(_w_oknie) == {"on", "off"} and 0.55 < _w_oknie.count("on") / len(_w_oknie) < 0.85,
        _w_oknie.count("on") / len(_w_oknie))
config.EKSPERYMENTY = _stare

print()
print("=== 2. PRAWDZIWE notki_dnia: OFF PISZE BEZ WNIOSKU, ON Z WNIOSKIEM ===")
WOLANIA = []
FAKT = {"domain": "health insurance", "fact": "A pilot pays the reviewer 25% of the care cost for every denial.",
        "url": "https://example.org/wiser", "styk": "zdrowie"}


def _atrapa_wniosku(conn, run_id, material):
    WOLANIA.append(1)
    return {"kind": "MONEY_OR_POWER", "conclusion": "A no pays."}


def _atrapa_note(conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", **k):
    return {"type": typ, "forma": note_form,
            "candidates": [{"note": "Note. %s" % bool(material.get("our_angle")), "safe_to_post": True}]}


_zastepcze = {"artykul_do_promocji": lambda: None, "pamiec_wystawionych": lambda: [],
              "znajdz_ciekawostki": lambda conn, run_id, ile=8: [],
              "opublikowane_teksty": lambda *a, **k: [], "teksty_ostatnich_notek": lambda *a, **k: [],
              "note": _atrapa_note, "wniosek": _atrapa_wniosku}
_oryg = {n: getattr(stages, n) for n in _zastepcze}
_glebia = config.GLEBIA_WLACZONA
wyniki = {}
try:
    config.GLEBIA_WLACZONA = False
    for n, f in _zastepcze.items():
        setattr(stages, n, f)
    for udzial, nazwa in ((0.0, "off"), (1.0, "on")):
        config.EKSPERYMENTY = {"wniosek": udzial}
        WOLANIA.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            _n = stages.notki_dnia(None, 0, ciekawostki=[dict(FAKT)], ile=1)
        wyniki[nazwa] = (list(WOLANIA), _n)
finally:
    config.EKSPERYMENTY = _stare
    config.GLEBIA_WLACZONA = _glebia
    for n, f in _oryg.items():
        setattr(stages, n, f)
_off, _on = wyniki["off"], wyniki["on"]
sprawdz("ramie off: wniosek NIE wolany, notka bez our_angle",
        _off[0] == [] and _off[1] and "False" in (_off[1][0]["candidates"][0]["note"]), _off)
sprawdz("ramie on: wniosek wolany, notka z our_angle",
        _on[0] == [1] and _on[1] and "True" in (_on[1][0]["candidates"][0]["note"]), _on)
sprawdz("wynik niesie ramie do dziennika",
        _off[1] and _off[1][0].get("eksperymenty") == {"wniosek": "off"}
        and _on[1] and _on[1][0].get("eksperymenty") == {"wniosek": "on"},
        [(x[1][0].get("eksperymenty") if x[1] else None) for x in (_off, _on)])

print()
print("=== 3. STATYSTYKI Z PRZEDZIALEM ===")
rnd = random.Random(1)


def _notka(i, ramie, srednia_log):
    w = max(1, int(math.exp(rnd.gauss(srednia_log, 0.55))))
    return {"wpis": {"id": str(i), "eksperymenty": {"wniosek": ramie}}, "w": w, "lw": math.log(w),
            "zaang": int(0.15 * w), "odbior": 0}


grupa = eksperymenty._grupujacy("eksperyment:wniosek")
wyraznie = [_notka(i, "on", 3.0 + math.log(2)) for i in range(40)] + [_notka(100 + i, "off", 3.0) for i in range(40)]
r = eksperymenty.porownaj(wyraznie, grupa)
g = r["grupy"].get("on") or {}
sprawdz("dwa razy wiecej wyswietlen przy 40 notkach — werdykt lepiej", g.get("werdykt") == "lepiej", g)
sprawdz("odniesieniem jest ramie off", r["odniesienie"] == "off", r["odniesienie"])
sprawdz("przedzial obejmuje stosunek",
        g.get("przedzial_95") and g["przedzial_95"][0] <= g["stosunek"] <= g["przedzial_95"][1], g)
# TE SAME LICZBY W OBU RAMIONACH, nie ten sam rozklad: losowe proby z jednego
# rozkladu przy przedziale 90% dawaly „gorzej" (stosunek 0,75) — tak wyglada
# fuks, ktory przedzial dopuszcza. Tu sprawdzamy logike werdyktu, nie los.
_wspolne = [_notka(200 + i, "on", 3.0) for i in range(40)]
rowno = _wspolne + [dict(x, wpis={"id": "k" + x["wpis"]["id"], "eksperymenty": {"wniosek": "off"}})
                    for x in _wspolne]
g = eksperymenty.porownaj(rowno, grupa)["grupy"].get("on") or {}
sprawdz("KONTRDOWOD: identyczne ramiona — brak dowodu roznicy, z podanym wykrywalnym efektem",
        str(g.get("werdykt", "")).startswith("brak dowodu") and g.get("wykrywalny_efekt")
        and g.get("stosunek") == 1.0, g)
_fuksy = 0
for proba in range(40):
    rnd.seed(1000 + proba)
    _null = [_notka(i, "on", 3.0) for i in range(30)] + [_notka(50 + i, "off", 3.0) for i in range(30)]
    _fuksy += eksperymenty.porownaj(_null, grupa)["grupy"]["on"]["werdykt"] in ("lepiej", "gorzej")
sprawdz("fałszywe alarmy przy braku efektu rzadkie (95%%: oczekiwane ok. 2 na 40, dopuszczamy do 6): %d" % _fuksy,
        _fuksy <= 6, _fuksy)
malo = [_notka(400 + i, "on", 3.0 + math.log(2)) for i in range(6)] + [_notka(500 + i, "off", 3.0) for i in range(6)]
g = eksperymenty.porownaj(malo, grupa)["grupy"].get("on") or {}
sprawdz("KONTRDOWOD: szesc notek na ramie — za malo danych, nawet przy duzej roznicy",
        str(g.get("werdykt", "")).startswith("za malo danych"), g)
# TREND: sierpien 2x wiecej wyswietlen niz wrzesien, grupy z roznych okresow
# (tak wygladalo pierwsze uruchomienie na produkcji: „brak modelu" = stare
# notki = „lepiej x1,95"). Po odjeciu tla roznicy byc nie moze.
from datetime import date, timedelta  # noqa: E402
_trend = []
for i in range(30):
    for dni, ramie, poziom in ((i, "stare", 3.0 + math.log(2)), (40 + i, "nowe", 3.0)):
        x = _notka(700 + dni, ramie, poziom)
        x["dzien"] = (date(2026, 8, 20) + timedelta(days=dni)).isoformat()
        _trend.append(x)
_g_tr = eksperymenty._grupujacy("eksperyment:wniosek")
_wyn = eksperymenty.porownaj(_trend, _g_tr, odniesienie="nowe")["grupy"]["stare"]
sprawdz("KONTRDOWOD: stare notki w lepszym okresie NIE wygrywaja po odjeciu tla, a werdykt ostrzega",
        not _wyn["werdykt"].startswith("lepiej") and "OSTROZNIE" in _wyn["werdykt"]
        and _wyn["wysw_geom"] > 1.6 * eksperymenty.porownaj(_trend, _g_tr, "nowe")["grupy"]["nowe"]["wysw_geom"],
        _wyn)
# PRZEPLATANE przy tym samym trendzie: obie grupy w tych samych dniach, „on" +100%.
_przepl = []
for i in range(60):
    dz = (date(2026, 8, 20) + timedelta(days=i)).isoformat()
    poziom = 3.0 + (math.log(2) if i < 30 else 0.0)          # tlo spada w polowie
    for ramie, bonus in (("on", math.log(2)), ("off", 0.0)):
        x = _notka(900 + 2 * i + (ramie == "on"), ramie, poziom + bonus)
        x["dzien"] = dz
        _przepl.append(x)
_wyn = eksperymenty.porownaj(_przepl, grupa)["grupy"]["on"]
sprawdz("przeplatane przy spadajacym tle: +100% wykryte jako lepiej, bez ostrzezenia o okresach",
        _wyn["werdykt"] == "lepiej" and 1.6 < _wyn["stosunek"] < 2.5, _wyn)
_dz = [{"rodzaj": "notka", "udane": True, "id": "a", "kiedy": "2026-10-02T10:00:00+00:00"},
       {"rodzaj": "notka", "udane": False, "id": "b", "kiedy": "2026-10-02T10:00:00+00:00"},
       {"rodzaj": "notka", "udane": True, "id": "c", "kiedy": "2026-09-01T10:00:00+00:00"},
       {"rodzaj": "restack", "udane": True, "id": "d", "kiedy": "2026-10-02T10:00:00+00:00"}]
_pom = {x: {"wyswietlenia": 20, "odwiedziny_profilu": 1, "interakcje": {"Like": 2, "Reply": 1}}
        for x in ("a", "b", "c", "d")}
_w = eksperymenty.wiersze(_dz, _pom, {"a": 1}, od="2026-09-27")
sprawdz("wiersze: tylko udane notki z okna, z zaangazowaniem i odbiorem (odwiedziny + 5 x zapis)",
        len(_w) == 1 and _w[0]["zaang"] == 3 and _w[0]["odbior"] == 6, _w)

print()
print("=== 4. DROGA DO DZIENNIKA ===")


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


_run, _st = _kod("agent-v2/run.py"), _kod("agent-v2/stages.py")
# Pola pomiaru liczy `stages.notki_dnia`, `run.py` tylko przekazuje — blok
# publikacji z `run.py` jest wykonywany w tescie bez globali modulu
# (`test_note_publication_count`), wiec nie moze siegac po nic spoza `n`.
sprawdz("stages dopisuje wersje kodu do wyniku, run.py tylko przekazuje ja i ramiona",
        '"wersja": n.get("wersja")' in _run and '"eksperymenty":' in _run
        and "def _wersja_kodu" in _st and 'wynik["wersja"] = WERSJA_KODU' in _st
        and "WERSJA_KODU" not in _run)
sprawdz("wersja kodu to skrot commita albo pusto (bez gita)",
        stages.WERSJA_KODU == "" or (4 <= len(stages.WERSJA_KODU) <= 12 and stages.WERSJA_KODU.isalnum()),
        stages.WERSJA_KODU)
sprawdz("notki_dnia: ramie wniosku zerowane przy kazdej notce i zapisywane w wyniku",
        '_ramie_wniosku = ""' in _st and 'wynik["eksperymenty"]' in _st
        and _st.index('_ramie_wniosku = ""') < _st.index('_ramie_wniosku = ramie("wniosek", od + nr)'))
sprawdz("E10 zatwierdzone przez wlasciciela 27.09: wniosek 70/30, 28.09-25.10 (bez zmian)",
        config.EKSPERYMENTY.get("wniosek") == {"udzial": 0.7, "od": "2026-09-28", "do": "2026-10-25"},
        config.EKSPERYMENTY)
sprawdz("E11 na polecenie wlasciciela 28.09: pisarz MiMo 50/50, to samo okno; obok tylko E12-E18"
        " zatwierdzone tego samego dnia (okna pilnuje test_eksperymenty_e12_e20)",
        config.EKSPERYMENTY.get("pisarz") == {"udzial": 0.5, "od": "2026-09-28", "do": "2026-10-25"}
        and set(config.EKSPERYMENTY) == {"wniosek", "pisarz", "restacki_norma", "pisarz_restackow",
                                         "cel_komentarza", "swiezosc_celu", "pora_notki",
                                         "krotka_notka", "pytanie_na_koncu", "pamiec_rozmowcy"},
        config.EKSPERYMENTY)
# NIEZALEZNE LOSOWANIE: ramiona E10 i E11 w tych samych slotach nie moga sie
# pokrywac systematycznie (osobny klucz = osobny hash), inaczej jeden
# eksperyment mierzylby drugi.
_pary = [(stages.ramie("wniosek", m, d), stages.ramie("pisarz", m, d))
         for d in ("2026-10-%02d" % i for i in range(1, 21)) for m in range(4)]
sprawdz("E10 i E11 losuja niezaleznie (wszystkie 4 kombinacje ramion wystepuja)",
        {("on", "on"), ("on", "off"), ("off", "on"), ("off", "off")} <= set(_pary),
        sorted(set(_pary)))
sprawdz("notki_dnia: ramie pisarza zerowane przy kazdej notce, notka z przeslania poza E11",
        '_ramie_pisarza = ""' in _st and '_ramie_pisarza = ramie("pisarz", od + nr)' in _st
        and _st.index('_ramie_pisarza = ""') < _st.index('_ramie_pisarza = ramie("pisarz", od + nr)')
        and '("pisarz", _ramie_pisarza)' in _st)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
