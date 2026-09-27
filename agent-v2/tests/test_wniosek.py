# -*- coding: utf-8 -*-
"""Niesztandarowy wniosek przed pisaniem notki (27.09.2026).

PO CO. Wlasciciel: „chcemy fajne tematy, mocne, plus z ciekawymi niesztandarowymi
wnioskami". Etap `stages.wniosek` szuka trzech wnioskow roznego rodzaju i oddaje
pisarzowi jeden. Test pilnuje, z kontrdowodami:
  1. wybrany wniosek trafia do pisarza w calosci (tok, przyklad, zarzut);
  2. kod odrzuca rodzaj spoza listy i pusty wniosek; zly indeks = pierwszy dobry;
  3. awaria = notka bez wniosku, a budzet i wylacznik lecą dalej;
  4. wylacznik i brak bazy nie wolaja modelu;
  5. droga: notki_dnia -> material["our_angle"] -> dziennik `wniosek`;
  6. prompty.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import json
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm      # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


ODP = {}
WOLANIA = []
_prawdziwy = llm.call


def _call(purpose, system, user, **kw):
    WOLANIA.append(purpose)
    x = ODP[purpose]
    if isinstance(x, BaseException):
        raise x
    return json.dumps(x)


DOWOD = {"fact": {"fact": "A pilot pays the reviewer 25% of the care cost for every denial."}}
llm.call = _call
try:
    print("=== 1. WYBRANY WNIOSEK TRAFIA DO PISARZA ===")
    ODP["wniosek"] = {"wnioski": [
        {"rodzaj": "MECHANISM", "wniosek": "The software is not the gatekeeper; the contract is.",
         "tok": ["a", "b"], "przyklad": "p1", "zarzut": "z1"},
        {"rodzaj": "MONEY_OR_POWER", "wniosek": "A no pays and a yes does not.",
         "tok": ["denial earns 25%", "approval earns nothing"], "przyklad": "a waiter paid per empty plate",
         "zarzut": "no evidence any denial was about money"},
        {"rodzaj": "NEXT", "wniosek": "Appeals will decide who waits.", "tok": ["c"], "przyklad": "p3", "zarzut": "z3"}],
        "wybrany": 1, "dlaczego": "most surprising"}
    kat = stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD)
    sprawdz("wybrany drugi wniosek", kat.get("kind") == "MONEY_OR_POWER"
            and kat.get("conclusion") == "A no pays and a yes does not.", kat)
    sprawdz("tok, przyklad i zarzut przechodza do pisarza",
            kat.get("reasoning") == ["denial earns 25%", "approval earns nothing"]
            and kat.get("everyday_example") and kat.get("strongest_objection"), kat)
    sprawdz("KONTRDOWOD: brak pewnosci = nasza interpretacja, nie fakt",
            kat.get("how_sure") == "OUR_READING", kat)
    ODP["wniosek"] = {"wnioski": [{"rodzaj": "MECHANISM", "wniosek": "A no pays.", "pewnosc": " shown "}],
                      "wybrany": 0}
    sprawdz("pewnosc SHOWN przechodzi (wielkosc liter i spacje bez znaczenia)",
            stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD).get("how_sure") == "SHOWN")
    ODP["wniosek"] = {"wnioski": [{"rodzaj": "MECHANISM", "wniosek": "A no pays.", "pewnosc": "CERTAIN"}],
                      "wybrany": 0}
    sprawdz("KONTRDOWOD: pewnosc spoza listy = OUR_READING",
            stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD).get("how_sure") == "OUR_READING")

    print()
    print("=== 2. KOD ODRZUCA ZLE WNIOSKI ===")
    ODP["wniosek"] = {"wnioski": [
        {"rodzaj": "HOT_TAKE", "wniosek": "Everything is doomed."},
        {"rodzaj": "NEXT", "wniosek": "   "},
        {"rodzaj": "PATTERN", "wniosek": "Insurers did this with fax machines.", "tok": ["x"]}],
        "wybrany": 0}
    kat = stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD)
    sprawdz("KONTRDOWOD: wybrany rodzaj spoza listy — bierzemy pierwszy dobry",
            kat.get("kind") == "PATTERN", kat)
    ODP["wniosek"] = {"wnioski": [{"rodzaj": "NEXT", "wniosek": "Only one."}], "wybrany": 7}
    sprawdz("indeks spoza listy — pierwszy dobry",
            stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD).get("conclusion") == "Only one.")
    ODP["wniosek"] = {"wnioski": [{"rodzaj": "HOT_TAKE", "wniosek": "x"}]}
    sprawdz("same zle — brak wniosku", stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD) == {})

    print()
    print("=== 3. AWARIE ===")
    ODP["wniosek"] = RuntimeError("padlo")
    sprawdz("awaria — notka bez wniosku", stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD) == {})
    ODP["wniosek"] = llm.BudgetExceeded("pusty budzet")
    try:
        stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD)
        sprawdz("KONTRDOWOD: pusty budzet leci dalej, nie jest polykany", False)
    except llm.BudgetExceeded:
        sprawdz("KONTRDOWOD: pusty budzet leci dalej, nie jest polykany", True)

    print()
    print("=== 4. WYLACZNIK I BRAK BAZY ===")
    WOLANIA.clear()
    ODP["wniosek"] = {"wnioski": [{"rodzaj": "NEXT", "wniosek": "x"}], "wybrany": 0}
    sprawdz("bez bazy — model nie wolany", stages.wniosek(None, None, DOWOD) == {} and not WOLANIA)
    _wl = config.WNIOSEK_WLACZONY
    config.WNIOSEK_WLACZONY = False
    sprawdz("wylacznik — model nie wolany",
            stages.wniosek(sqlite3.connect(":memory:"), None, DOWOD) == {} and not WOLANIA)
    config.WNIOSEK_WLACZONY = _wl
finally:
    llm.call = _prawdziwy

print()
print("=== 5. DROGA DO PISARZA I DZIENNIKA ===")


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


_st, _run = _kod("agent-v2/stages.py"), _kod("agent-v2/run.py")
sprawdz("notki_dnia wola wniosek po karcie glebi i daje go pisarzowi",
        "_kat = wniosek(conn, run_id, material)" in _st and 'material["our_angle"] = _kat' in _st
        and _st.index('material["depth"] =') < _st.index("_kat = wniosek(conn, run_id, material)"))
sprawdz("rodzaj wniosku w wyniku i w dzienniku",
        'wynik["wniosek"]' in _st and '"wniosek": n.get("wniosek")' in _run)
sprawdz("etap ma model, sufit i myslenie",
        config.MODEL_FOR.get("wniosek") and config.MAX_TOKENS.get("wniosek")
        and config.myslenie_deepseek("wniosek") == {"type": "enabled"})

print()
print("=== 6. PROMPTY ===")
notka = " ".join((pathlib.Path("agent-v2/prompts/notka.md")).read_text(encoding="utf-8").split())
sprawdz("notka.md mowi pisarzowi, co zrobic z our_angle", "`our_angle`" in notka)
sprawdz("notka.md: zastrzezenia zrodla zostaja, OUR_READING slychac (runda 3 A/B)",
        "The evidence's hedges stay" in notka and "When `how_sure` is OUR_READING" in notka
        and "never the words that keep a claim true" in notka)
wn = (pathlib.Path("agent-v2/prompts/wniosek.md")).read_text(encoding="utf-8")
sprawdz("wniosek.md: krok z dowodu trzyma zastrzezenie i pewnosc jest w odpowiedzi",
        "keeps its hedge" in wn and '"pewnosc": "SHOWN"|"OUR_READING"' in wn)
sprawdz("wniosek.md: wszystko po angielsku (A/B 27.09: Flash odpisal po polsku)",
        "Write every value in English." in wn)
_pola = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", wn))
try:
    wn.format(**{p: "x" for p in _pola})
    _ok = True
except (KeyError, ValueError, IndexError) as exc:
    _ok = exc
sprawdz("wniosek.md formatuje sie bez bledu", _ok is True, _ok)
bank = " ".join((pathlib.Path("agent-v2/prompts/bank.md")).read_text(encoding="utf-8").split())
sprawdz("sedzia banku woli mocne tematy i niesztandarowy wniosek",
        "Prefer STRONG TOPICS" in bank and "What would a smart reader NOT guess from the headline?" in bank)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
