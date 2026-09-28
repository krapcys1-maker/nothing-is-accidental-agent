# -*- coding: utf-8 -*-
"""Eksperymenty E12-E18 i E20 — czy dzialaja i czy zbieraja dane (28.09.2026).

Wlasciciel 28.09.2026: „przygotuj caly test, zeby to dzialalo i zeby zbieralo
dane". Test pilnuje, z kontrdowodami:
  1. E12 — ramie z kalendarza (tygodnie ABBAAB) i widelki restackow w budzecie;
  2. E13 — Opus pisze zdanie restacka w ramieniu „on", ramie i model ida z restackiem;
  3. E14 — ta sama liczba miejsc na komentarz, rodzaj celu losowany na miejsce;
  4. E15 — swiezy cel na wylosowanych miejscach, prog anty-bota nietkniety;
  5. E16 — dzien „on" nie wystawia notek przed trzecim przebiegiem;
  6. E17/E18 — okno krotkiej notki i pytanie na koniec w prompcie; ramiona w dzienniku;
  7. `eksperymenty.py` — restacki, komentarze (odsetek z reakcja), tygodnie;
  8. alarm „pomiar oslepl";
  9. E20 — rekomendacje: odczyt w nowym ksztalcie API, zapis do pliku, doby w obserwatorium.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import datetime as _dt_mod
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

KATALOG = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KATALOG)

import alarm          # noqa: E402
import browser        # noqa: E402
import eksperymenty   # noqa: E402
import llm            # noqa: E402
import obserwatorium  # noqa: E402
import run            # noqa: E402
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


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


_ST, _RUN, _BR = _kod("agent-v2/stages.py"), _kod("agent-v2/run.py"), _kod("agent-v2/browser.py")
ORYG_EKSP = dict(config.EKSPERYMENTY)
DZIS = datetime.now(timezone.utc).date().isoformat()
ZAWSZE = {"od": "2026-01-01", "do": "2099-12-31"}

print("=== 0. REJESTR: ZATWIERDZONE OKNA ===")
E = config.EKSPERYMENTY
sprawdz("E12-E18 zapisane w konfiguracji z oknami dat",
        E.get("restacki_norma") == {"plan": ["on", "off", "off", "on", "on", "off"], "okres_dni": 7,
                                    "od": "2026-09-29", "do": "2026-11-09"}
        and E.get("pisarz_restackow") == {"udzial": 0.5, "od": "2026-09-29", "do": "2026-10-26"}
        and E.get("cel_komentarza") == {"udzial": 0.5, "od": "2026-09-29", "do": "2026-10-19"}
        and E.get("swiezosc_celu") == {"udzial": 0.5, "od": "2026-10-20", "do": "2026-11-09"}
        and E.get("pora_notki") == {"plan": ["on", "off"], "okres_dni": 1, "od": "2026-10-26", "do": "2026-11-22"}
        and E.get("krotka_notka") == {"udzial": 0.5, "od": "2026-10-26", "do": "2026-11-22"}
        and E.get("pytanie_na_koncu") == {"udzial": 0.5, "od": "2026-10-26", "do": "2026-11-22"}, E)
sprawdz("E15 startuje po E14, E16-E18 po E10 i E11",
        E["swiezosc_celu"]["od"] > E["cel_komentarza"]["do"]
        and all(E[n]["od"] > E["wniosek"]["do"] and E[n]["od"] > E["pisarz"]["do"]
                for n in ("pora_notki", "krotka_notka", "pytanie_na_koncu")))
_stare_int = [int(__import__("hashlib").sha256(("wniosek|2026-10-01|%d" % m).encode()).hexdigest()[:8], 16)
              / 0x100000000 < 0.7 for m in range(30)]
sprawdz("`%s` zamiast `%d` w haszu: ramiona E10/E11 dla liczb bez zmian",
        [stages.ramie("wniosek", m, "2026-10-01") == "on" for m in range(30)] == _stare_int)

print()
print("=== 1. E12 — TYGODNIE RESTACKOW ===")
_dni = ["2026-09-29", "2026-10-05", "2026-10-06", "2026-10-13", "2026-10-20", "2026-10-27",
        "2026-11-03", "2026-11-09"]
sprawdz("tygodnie wg planu ABBAAB od wtorku 29.09",
        [stages.ramie("restacki_norma", 0, d) for d in _dni] == ["on", "on", "off", "off", "on", "on", "off", "off"],
        [stages.ramie("restacki_norma", 0, d) for d in _dni])
sprawdz("KONTRDOWOD: przed i po oknie E12 nie trwa",
        stages.ramie("restacki_norma", 0, "2026-09-28") == "" and stages.ramie("restacki_norma", 0, "2026-11-10") == "")
sprawdz("w planie miejsce nie ma znaczenia (caly tydzien w jednym ramieniu)",
        len({stages.ramie("restacki_norma", m, "2026-10-08") for m in range(20)}) == 1)
sprawdz("widelki: on 3-5 (srednio 4), off 1-3 (srednio 2), poza eksperymentem jak dotad",
        stages.widelki_restackow("2026-09-29") == (3, 5) and stages.widelki_restackow("2026-10-06") == (1, 3)
        and stages.widelki_restackow("2026-09-28") == tuple(config.RESTACK_DZIENNIE),
        [stages.widelki_restackow(d) for d in ("2026-09-29", "2026-10-06", "2026-09-28")])


class _Zegar(datetime):
    TERAZ = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.TERAZ if tz else cls.TERAZ.replace(tzinfo=None)


def _budzet_w_dniu(dzien):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE runs (started_at TEXT)")
    conn.execute("INSERT INTO runs VALUES ('2026-01-01T00:00:00+00:00')")
    _Zegar.TERAZ = datetime.fromisoformat(dzien + "T12:00:00+00:00")
    _dt_mod.datetime = _Zegar
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return stages.budzet_dnia(conn)
    finally:
        _dt_mod.datetime = datetime


_on = [_budzet_w_dniu(d)["restacki"] for d in ("2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02",
                                                 "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23")]
_off = [_budzet_w_dniu(d)["restacki"] for d in ("2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09",
                                                  "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16")]
sprawdz("prawdziwy budzet dnia: tydzien on 3-5 restackow, tydzien off 1-3",
        all(3 <= x <= 5 for x in _on) and all(1 <= x <= 3 for x in _off) and sum(_on) > sum(_off), (_on, _off))
config.EKSPERYMENTY = {k: v for k, v in ORYG_EKSP.items() if k != "restacki_norma"}
_bez = _budzet_w_dniu("2026-09-29")
config.EKSPERYMENTY = dict(ORYG_EKSP)
_z = _budzet_w_dniu("2026-09-29")
sprawdz("KONTRDOWOD: E12 zmienia TYLKO restacki — reszta budzetu z tego samego ziarna bez zmian",
        {k: v for k, v in _bez.items() if k != "restacki"} == {k: v for k, v in _z.items() if k != "restacki"}
        and 1 <= _bez["restacki"] <= 2, (_bez, _z))

print()
print("=== 2. E13 — KTO PISZE ZDANIE RESTACKA ===")
sprawdz("routing: `restack_opus` na Opusie, niski wysilek, sufit tokenow",
        config.MODEL_FOR.get("restack_opus") == config.CLAUDE and config.EFFORT.get("restack_opus") == "low"
        and config.MAX_TOKENS.get("restack_opus") == 4000 + config.THINKING_HEADROOM_TOKENS,
        (config.MODEL_FOR.get("restack_opus"), config.EFFORT.get("restack_opus"),
         config.MAX_TOKENS.get("restack_opus")))
ETAPY = []
_oryg_llm = stages.llm
stages.llm = types.SimpleNamespace(
    call=lambda etap, *a, **k: ETAPY.append(etap) or json.dumps(
        {"restack": True, "reason": "ok", "sentence": "Airlines run the same bet on empty seats."}),
    parse_json=llm.parse_json)
NOTKA = {"autor": "kto-inny", "tekst": "Airlines overbook because a predictable share of passengers never show up."}
try:
    config.EKSPERYMENTY = {"pisarz_restackow": dict(ZAWSZE, udzial=1.0)}
    o_on = stages.ocen_restack(None, 0, NOTKA)
    config.EKSPERYMENTY = {"pisarz_restackow": dict(ZAWSZE, udzial=0.0)}
    o_off = stages.ocen_restack(None, 0, NOTKA)
    config.EKSPERYMENTY = {}
    o_poza = stages.ocen_restack(None, 0, NOTKA)
finally:
    stages.llm = _oryg_llm
    config.EKSPERYMENTY = dict(ORYG_EKSP)
sprawdz("ramie on: zdanie pisze `restack_opus`, wynik niesie model i ramie",
        ETAPY[0] == "restack_opus" and o_on.get("model") == config.CLAUDE
        and o_on.get("eksperymenty", {}).get("pisarz_restackow") == "on", (ETAPY, o_on))
sprawdz("ramie off: zwykly `restack` na Flashu",
        ETAPY[1] == "restack" and o_off.get("model") == config.DEEPSEEK
        and o_off.get("eksperymenty", {}).get("pisarz_restackow") == "off", (ETAPY, o_off))
sprawdz("KONTRDOWOD: poza eksperymentem jak dotad, bez pola eksperymentow",
        ETAPY[2] == "restack" and not o_poza.get("eksperymenty") and o_poza["restack"] is True, o_poza)
_klucze = ["%040x" % i for i in range(60)]
_r = [stages.ramie("pisarz_restackow", k, "2026-10-05") for k in _klucze]
sprawdz("los po tresci: ta sama notka = to samo ramie, rozne notki ~polowa on",
        all(stages.ramie("pisarz_restackow", k, "2026-10-05") == r for k, r in zip(_klucze, _r))
        and 0.3 < _r.count("on") / len(_r) < 0.7, _r.count("on"))
_blok = _BR[_BR.index("def restackuj_w_kanale("):_BR.index("def _notka_przy_przycisku(")]
sprawdz("przegladarka zapisuje model i ramiona do dziennika restacka",
        '("model", "eksperymenty")' in _blok and 'zapisz_w_dzienniku("restack"' in _blok)

print()
print("=== 3. E14 — GDZIE KOMENTARZ ===")
config.EKSPERYMENTY = {}
sprawdz("poza eksperymentem przydzial jak dotad: artykuly N, notki max(1, N//2)",
        [run.przydzial_komentarzy(n, 7) for n in (0, 1, 2, 5)] == [
            {"artykuly": 0, "notki": 0, "e14": False}, {"artykuly": 1, "notki": 1, "e14": False},
            {"artykuly": 2, "notki": 1, "e14": False}, {"artykuly": 5, "notki": 2, "e14": False}])
config.EKSPERYMENTY = {"cel_komentarza": dict(ZAWSZE, udzial=1.0)}
sprawdz("wszystkie miejsca on: wszystko pod notkami, suma bez zmian",
        run.przydzial_komentarzy(2, 7) == {"artykuly": 0, "notki": 3, "e14": True})
config.EKSPERYMENTY = {"cel_komentarza": dict(ZAWSZE, udzial=0.0)}
sprawdz("wszystkie miejsca off: wszystko pod artykulami",
        run.przydzial_komentarzy(2, 7) == {"artykuly": 3, "notki": 0, "e14": True})
config.EKSPERYMENTY = dict(ORYG_EKSP)
_p = [run.przydzial_komentarzy(2, rid, "2026-10-01") for rid in range(200)]
sprawdz("E14 w oknie: suma miejsc zawsze N + N//2, pod notkami ok. polowa, ten sam przebieg = ten sam podzial",
        all(x["artykuly"] + x["notki"] == 3 and x["e14"] for x in _p)
        and 0.4 < sum(x["notki"] for x in _p) / 600 < 0.6
        and run.przydzial_komentarzy(2, 11, "2026-10-01") == _p[11], sum(x["notki"] for x in _p) / 600)
sprawdz("KONTRDOWOD: przed oknem E14 przydzial jak dotad",
        run.przydzial_komentarzy(2, 11, "2026-09-28") == {"artykuly": 2, "notki": 1, "e14": False})
sprawdz("pola dziennika: rodzaj celu zawsze, ramie E14 tylko w eksperymencie",
        run.ramiona_komentarza({}, "notka", True) == {"pod": "notka", "eksperymenty": {"cel_komentarza": "on"}}
        and run.ramiona_komentarza({}, "artykul", True) == {"pod": "artykul", "eksperymenty": {"cel_komentarza": "off"}}
        and run.ramiona_komentarza({}, "artykul", False) == {"pod": "artykul"})
_kom = _RUN[_RUN.index("    def komentarze() -> None:"):_RUN.index("    def dyskusje() -> None:")]
_dys = _RUN[_RUN.index("    def dyskusje() -> None:"):_RUN.index("    def obserwuj() -> None:")]
sprawdz("blok artykulow bierze `przydzial[\"artykuly\"]`, a nie `na_teraz[\"komentarze\"]`",
        'ile = przydzial["artykuly"]' in _kom and 'na_teraz["komentarze"]' not in _kom
        and "cele[:ile]" in _kom and 'ramiona_komentarza(cel, "artykul"' in _kom)
sprawdz("blok notek bierze `przydzial[\"notki\"]` i zapisuje rodzaj celu",
        'przydzial["notki"]' in _dys and 'na_teraz["komentarze"]' not in _dys
        and 'ramiona_komentarza(cel, "notka"' in _dys)
sprawdz("przydzial liczony PO przycieciu komentarzy do zegara",
        _RUN.index('na_teraz["komentarze"] = zmiesci_sie("komentarz"')
        < _RUN.index('przydzial = przydzial_komentarzy(na_teraz["komentarze"], run_id)'))

print()
print("=== 4. E15 — SWIEZY CEL ===")
_teraz = datetime.now(timezone.utc)


def _cel(nazwa, minut):
    return {"url": nazwa, "data": (_teraz - timedelta(minutes=minut)).isoformat()}


CELE = [_cel("stary", 300), _cel("swiezy", 30), _cel("sredni", 60), _cel("bardzo_stary", 2000)]
config.EKSPERYMENTY = {"swiezosc_celu": dict(ZAWSZE, udzial=1.0)}
_u = run.uloz_wedlug_swiezosci(list(CELE), "7-notki")
sprawdz("ramie on: najpierw najswiezsze ponizej 2 h, potem kolejnosc wyboru",
        [c["url"] for c in _u] == ["swiezy", "sredni", "stary", "bardzo_stary"]
        and all(c["_e15"] == "on" for c in _u), [(c["url"], c["_e15"]) for c in _u])
config.EKSPERYMENTY = {"swiezosc_celu": dict(ZAWSZE, udzial=0.0)}
_u = run.uloz_wedlug_swiezosci(list(CELE), "7-notki")
sprawdz("ramie off: kolejnosc wyboru bez zmian, ramie zapisane",
        [c["url"] for c in _u] == [c["url"] for c in CELE] and all(c["_e15"] == "off" for c in _u))
config.EKSPERYMENTY = {}
_u = run.uloz_wedlug_swiezosci(CELE, "7-notki")
sprawdz("KONTRDOWOD: poza eksperymentem ta sama lista, bez pola ramienia",
        _u is CELE and not any("_e15" in c for c in _u))
config.EKSPERYMENTY = dict(ORYG_EKSP)
sprawdz("pola dziennika: ramie E15 z celu",
        run.ramiona_komentarza({"_e15": "on"}, "notka", False) == {"pod": "notka", "eksperymenty": {"swiezosc_celu": "on"}})
sprawdz("KONTRDOWOD: prog anty-bota nietkniety (artykul 90-900 min, notka 20-90 min)",
        tuple(config.MIN_WIEK_POSTA_MIN) == (90, 900) and tuple(config.MIN_WIEK_NOTKI_MIN) == (20, 90)
        and config.SWIEZY_CEL_MIN == 120)
sprawdz("oba bloki ukladaja cele przed petla komentarzy",
        'uloz_wedlug_swiezosci(cele, "%s-artykuly" % run_id)' in _kom
        and 'uloz_wedlug_swiezosci(cele, "%s-notki" % run_id)' in _dys)

print()
print("=== 5. E16 — PORA NOTKI ===")
sprawdz("dzien on (26.10): przebiegi 1 i 2 bez notek, od trzeciego jak zwykle",
        [run.notki_w_porze(1, z, "2026-10-26") for z in (5, 4, 3, 2, 1)] == [0, 0, 1, 1, 1])
sprawdz("dzien off (27.10) i przed oknem (25.10): bez zmian",
        [run.notki_w_porze(1, z, "2026-10-27") for z in (5, 4, 3)] == [1, 1, 1]
        and [run.notki_w_porze(2, z, "2026-10-25") for z in (5, 4)] == [2, 2])
from datetime import date  # noqa: E402
_poz = {}
for i in range(28):
    d = date(2026, 10, 26) + timedelta(days=i)
    _poz.setdefault(d.weekday(), []).append(stages.ramie("pora_notki", 0, d.isoformat()))
sprawdz("kazdy dzien tygodnia po rowno: 2 dni on i 2 off w czterech tygodniach",
        all(sorted(v) == ["off", "off", "on", "on"] for v in _poz.values()), _poz)
sprawdz("dzien() uzywa tej bramki po oknie publikacji",
        "_w_porze = notki_w_porze(na_teraz[\"notki\"], zostalo_przebiegow)" in _RUN
        and _RUN.index("wolno, powod = config.pora_na_publikacje()") < _RUN.index("_w_porze = notki_w_porze("))

print()
print("=== 6. E17 I E18 — KROTKA NOTKA, PYTANIE NA KONIEC ===")
_notka_md = (config.PROMPTS_DIR / "notka.md").read_text(encoding="utf-8")
sprawdz("zdanie, ktore E18 podmienia, stoi w notka.md (inaczej ramie przestaloby dzialac)",
        stages.ZDANIE_O_ZAKONCZENIU in _notka_md)
_pp = stages.z_pytaniem_na_koncu("A\n" + stages.ZDANIE_O_ZAKONCZENIU + "\nB")
sprawdz("E18: polecenie pytania zamiast dowolnego zakonczenia",
        stages.POLECENIE_PYTANIA in _pp and stages.ZDANIE_O_ZAKONCZENIU not in _pp)
sprawdz("KONTRDOWOD: bez zdania-kotwicy polecenie i tak trafia do promptu",
        stages.z_pytaniem_na_koncu("xyz").endswith(stages.POLECENIE_PYTANIA))
PROMPTY = []


def _atrapa_modelu(etap, system, user, conn=None, run_id=None, **k):
    PROMPTY.append((etap, user))
    return json.dumps({"note": "Short note " * 12 + "?", "words": 25})


_oryg = {n: getattr(stages, n) for n in ("zweryfikuj", "teksty_ostatnich_notek", "ostatnie_otwarcia")}
_oryg_call = llm.call
FAKT = {"fact": "Something checkable happened in 2026.", "url": "https://example.org/a",
        "domain": "example.org", "source_date": "2026-09-01"}
try:
    llm.call = _atrapa_modelu
    stages.zweryfikuj = lambda *a, **k: {"claims": [], "safe_to_post": True}
    stages.teksty_ostatnich_notek = lambda ile=40: []
    stages.ostatnie_otwarcia = lambda rodzaj="notka", ile=8: []
    with contextlib.redirect_stdout(io.StringIO()):
        stages.note(None, 0, "CIEKAWOSTKA", {"fact": dict(FAKT)}, etap="note",
                    wariant={"krotka": True, "pytanie": True})
        _z_wariantem = [u for e, u in PROMPTY if e == "note"][-1]
        stages.note(None, 0, "CIEKAWOSTKA", {"fact": dict(FAKT)}, etap="note")
        _bez_wariantu = [u for e, u in PROMPTY if e == "note"][-1]
        stages.note(None, 0, "CIEKAWOSTKA", {"fact": dict(FAKT)}, etap="note",
                    note_form=sorted(config.FORMY_DLUGIE)[0], wariant={"krotka": True})
        _dluga = [u for e, u in PROMPTY if e == "note"][-1]
finally:
    llm.call = _oryg_call
    for n, f in _oryg.items():
        setattr(stages, n, f)
_k = config.KROTKA_NOTKA_SLOW
sprawdz("E17: prompt z oknem krotkiej notki (%d-%d) i poleceniem wprost" % _k,
        ("%d–%d words" % _k) in _z_wariantem
        and (stages.POLECENIE_KROTKIEJ % (_k[0], _k[1], _k[1])) in _z_wariantem
        and (stages.ZDANIE_O_DLUGOSCI % _k) not in _z_wariantem, _z_wariantem[-1500:][:300])
sprawdz("zdanie, ktore E17 podmienia, stoi w notka.md",
        stages.ZDANIE_O_DLUGOSCI.replace("%d", "{min_words}", 1).replace("%d", "{max_words}", 1) in _notka_md)
sprawdz("E18: prompt z poleceniem pytania",
        stages.POLECENIE_PYTANIA in _z_wariantem and stages.ZDANIE_O_ZAKONCZENIU not in _z_wariantem)
sprawdz("KONTRDOWOD: bez wariantu okno i zakonczenie jak dotad",
        (stages.ZDANIE_O_DLUGOSCI % (config.NOTE_MIN_WORDS, config.NOTE_MAX_WORDS)) in _bez_wariantu
        and stages.ZDANIE_O_ZAKONCZENIU in _bez_wariantu and "SHORT note" not in _bez_wariantu)
sprawdz("KONTRDOWOD: dluga forma zostaje w swoim oknie mimo E17",
        (stages.ZDANIE_O_DLUGOSCI % (config.NOTE_MIN_WORDS_DLUGA, config.NOTE_MAX_WORDS_DLUGA)) in _dluga
        and "SHORT note" not in _dluga)

_dp = stages.dopnij_pytanie
sprawdz("E18: brak pytania na koncu — kod dopina pytanie z `closing_question`",
        _dp("Plain statement.", "Where does it land for you?") == "Plain statement.\n\nWhere does it land for you?")
sprawdz("KONTRDOWOD: bez dubla i bez psucia",
        _dp("Ends with a question?", "Other?") == "Ends with a question?"
        and _dp("Ask: where does it land for you? Then stop.", "Where does it land  for you?")
        == "Ask: where does it land for you? Then stop."
        and _dp("Plain.", "not a question") == "Plain." and _dp("", "Q?") == "")
PROMPTY.clear()
_oryg = {n: getattr(stages, n) for n in ("zweryfikuj", "teksty_ostatnich_notek", "ostatnie_otwarcia")}
try:
    llm.call = lambda etap, system, user, **k: json.dumps(
        {"note": "A plain statement " * 5 + "ends here.", "words": 16,
         "closing_question": "Where does the checking land for you?"})
    stages.zweryfikuj = lambda *a, **k: {"claims": [], "safe_to_post": True}
    stages.teksty_ostatnich_notek = lambda ile=40: []
    stages.ostatnie_otwarcia = lambda rodzaj="notka", ile=8: []
    with contextlib.redirect_stdout(io.StringIO()):
        _z = stages.note(None, 0, "CIEKAWOSTKA", {"fact": dict(FAKT)}, etap="note", wariant={"pytanie": True})
        _bez = stages.note(None, 0, "CIEKAWOSTKA", {"fact": dict(FAKT)}, etap="note")
finally:
    llm.call = _oryg_call
    for n, f in _oryg.items():
        setattr(stages, n, f)
sprawdz("prawdziwe note(): ramie on konczy sie pytaniem, nawet gdy model go nie postawil",
        _z["candidates"][0]["note"].rstrip().endswith("Where does the checking land for you?"),
        _z["candidates"][0]["note"][-80:])
sprawdz("KONTRDOWOD: bez wariantu notka taka, jak napisal model",
        _bez["candidates"][0]["note"].rstrip().endswith("ends here."), _bez["candidates"][0]["note"][-40:])

WARIANTY = []


def _atrapa_note(conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", wariant=None, **k):
    WARIANTY.append(dict(wariant or {}))
    return {"type": typ, "forma": note_form,
            "candidates": [{"note": "A note that ends with a question?", "safe_to_post": True}]}


_zast = {"artykul_do_promocji": lambda: None, "pamiec_wystawionych": lambda: [],
         "znajdz_ciekawostki": lambda conn, run_id, ile=8: [],
         "opublikowane_teksty": lambda *a, **k: [], "teksty_ostatnich_notek": lambda *a, **k: [],
         "note": _atrapa_note, "wniosek": lambda *a, **k: {}}
_oryg = {n: getattr(stages, n) for n in _zast}
_glebia = config.GLEBIA_WLACZONA
FAKT2 = {"domain": "health insurance", "fact": "A pilot pays the reviewer 25% of the care cost.",
         "url": "https://example.org/wiser", "styk": "zdrowie"}
try:
    config.GLEBIA_WLACZONA = False
    for n, f in _zast.items():
        setattr(stages, n, f)
    config.EKSPERYMENTY = {"krotka_notka": dict(ZAWSZE, udzial=1.0), "pytanie_na_koncu": dict(ZAWSZE, udzial=1.0),
                           "pora_notki": {"plan": ["on"], "okres_dni": 1, "od": "2026-01-01", "do": "2099-12-31"}}
    with contextlib.redirect_stdout(io.StringIO()):
        _n = stages.notki_dnia(None, 0, ciekawostki=[dict(FAKT2)], ile=1)
    config.EKSPERYMENTY = {}
    with contextlib.redirect_stdout(io.StringIO()):
        _n0 = stages.notki_dnia(None, 0, ciekawostki=[dict(FAKT2)], ile=1)
finally:
    config.EKSPERYMENTY = dict(ORYG_EKSP)
    config.GLEBIA_WLACZONA = _glebia
    for n, f in _oryg.items():
        setattr(stages, n, f)
sprawdz("prawdziwe notki_dnia: ramiona E16-E18 w wyniku, wariant dotarl do pisarza",
        _n and _n[0].get("eksperymenty") == {"pora_notki": "on", "krotka_notka": "on", "pytanie_na_koncu": "on"}
        and WARIANTY[0] == {"krotka": True, "pytanie": True}, (_n and _n[0].get("eksperymenty"), WARIANTY))
sprawdz("kandydat mowi, czy notka konczy sie pytaniem (sprawdzenie, ze zmiana zaszla)",
        _n and _n[0]["candidates"][0].get("konczy_pytaniem") is True)
sprawdz("KONTRDOWOD: poza eksperymentami ani ramion, ani wariantu",
        _n0 and not _n0[0].get("eksperymenty") and WARIANTY[1] == {"krotka": False, "pytanie": False},
        (_n0 and _n0[0].get("eksperymenty"), WARIANTY[1:]))
_blok_p = _ST[_ST.index('_ramie_pisarza = ramie("pisarz", od + nr)'):_ST.index("wynik = note(conn, run_id, typ, material,")]
sprawdz("notka z przeslania poza E17/E18, czesc serii poza E18, dluga forma poza E17",
        "if forma not in config.FORMY_DLUGIE:" in _blok_p and "if not seria_kontekst:" in _blok_p
        and _ST.index("if _przes:") < _ST.index('_ramie_krotkiej = ramie("krotka_notka", od + nr)'))
sprawdz("run.py przekazuje `konczy_pytaniem` do dziennika notki", '"konczy_pytaniem": gotowe[0].get(' in _RUN)

print()
print("=== 7. OCENA: RESTACKI, KOMENTARZE, TYGODNIE ===")
_dz = [{"rodzaj": "restack", "udane": True, "id": "r1", "kiedy": "2026-10-02T10:00:00+00:00",
        "eksperymenty": {"pisarz_restackow": "on"}},
       {"rodzaj": "notka", "udane": True, "id": "n1", "kiedy": "2026-10-02T10:00:00+00:00"}]
_pom = {x: {"wyswietlenia": 20, "odwiedziny_profilu": 1, "interakcje": {"Like": 2}} for x in ("r1", "n1")}
_w = eksperymenty.wiersze(_dz, _pom, {"r1": 1}, od="2026-09-27", rodzaj="restack")
sprawdz("restacki: wiersze z wpisow `restack`, ten sam pomiar co notki",
        len(_w) == 1 and _w[0]["wpis"]["id"] == "r1" and _w[0]["odbior"] == 6, _w)


def _komentarze(ile, ramie, z_reakcja, start=0):
    dz, pom = [], {}
    for i in range(ile):
        ident = "%s%d" % (ramie, start + i)
        dz.append({"rodzaj": "komentarz", "udane": True, "nasz_id": ident, "kiedy": "2026-10-05T10:00:00+00:00",
                   "pod": "notka" if ramie == "on" else "artykul", "eksperymenty": {"cel_komentarza": ramie}})
        pom[ident] = {"wyswietlenia": 0, "polubienia": 1 if i < z_reakcja else 0, "odpowiedzi": 0}
    return dz, pom


_a, _pa = _komentarze(60, "on", 24)
_b, _pb = _komentarze(60, "off", 6)
_dane = eksperymenty.wiersze_komentarzy(_a + _b, {**_pa, **_pb})
_g = eksperymenty.porownaj_komentarze(_dane, eksperymenty._grupujacy("eksperyment:cel_komentarza"))
sprawdz("komentarze: 40% wobec 10% reakcji przy 60 na ramie — lepiej",
        _g["odniesienie"] == "off" and _g["grupy"]["on"]["werdykt"] == "lepiej"
        and _g["grupy"]["on"]["z_reakcja"] == 40.0, _g["grupy"].get("on"))
_g2 = eksperymenty.porownaj_komentarze(_dane, eksperymenty._grupujacy("pod"))
sprawdz("to samo pole `pod` poza eksperymentem (rodzaj celu zawsze w dzienniku)",
        set(_g2["grupy"]) == {"notka", "artykul"})
_a, _pa = _komentarze(60, "on", 12)
_b, _pb = _komentarze(60, "off", 12)
_g = eksperymenty.porownaj_komentarze(eksperymenty.wiersze_komentarzy(_a + _b, {**_pa, **_pb}),
                                      eksperymenty._grupujacy("eksperyment:cel_komentarza"))
sprawdz("KONTRDOWOD: rowne odsetki — brak dowodu roznicy",
        _g["grupy"]["on"]["werdykt"].startswith("brak dowodu"), _g["grupy"]["on"])
_a, _pa = _komentarze(10, "on", 8)
_b, _pb = _komentarze(10, "off", 1)
_g = eksperymenty.porownaj_komentarze(eksperymenty.wiersze_komentarzy(_a + _b, {**_pa, **_pb}),
                                      eksperymenty._grupujacy("eksperyment:cel_komentarza"))
sprawdz("KONTRDOWOD: 10 komentarzy na ramie — za malo danych mimo duzej roznicy",
        _g["grupy"]["on"]["werdykt"].startswith("za malo danych"), _g["grupy"]["on"])
_dni_obs = {}
for i in range(-1, 42):
    d = (date(2026, 9, 29) + timedelta(days=i)).isoformat()
    _dni_obs[d] = {"subskrybenci": 30 + i + 1, "odwiedziny_profilu": 2, "zapisy_przypisane": 0,
                   "dz_restacki": 4 if stages.ramie("restacki_norma", 0, d) == "on" else 2}
_t = eksperymenty.tygodnie(_dni_obs, "restacki_norma",
                           [{"dzien": "2026-09-30", "w": 15, "zapisy": 1}, {"dzien": "2026-10-07", "w": 9, "zapisy": 0}])
sprawdz("tygodnie E12: szesc tygodni z ramionami, przyrost od stanu sprzed tygodnia",
        [x["ramie"] for x in _t] == ["on", "off", "off", "on", "on", "off"]
        and _t[0]["od"] == "2026-09-29" and _t[0]["do"] == "2026-10-05" and _t[0]["przyrost_subskrybentow"] == 7
        and _t[0]["restacki"] == 28 and _t[1]["restacki"] == 14 and _t[0]["zapisy_z_restackow"] == 1
        and _t[0]["wysw_restackow"] == 15, _t[:2])
_rs = eksperymenty.restacki_dziennika(
    [{"rodzaj": "restack", "udane": True, "id": "r1", "kiedy": "2026-09-30T10:00:00+00:00"},
     {"rodzaj": "restack", "udane": True, "id": "", "kiedy": "2026-09-30T11:00:00+00:00"}],
    {"r1": {"wyswietlenia": 15}}, {"r1": 2})
sprawdz("restacki z dziennika: wyswietlenia i zapisy po numerze, restack bez numeru liczony jako zero",
        _rs == [{"dzien": "2026-09-30", "w": 15, "zapisy": 2}, {"dzien": "2026-09-30", "w": 0, "zapisy": 0}], _rs)

print()
print("=== 8. ALARM: POMIAR OSLEPL ===")


def _zapisz(nazwa, wiersze):
    (KATALOG / nazwa).write_text("".join(json.dumps(w) + "\n" for w in wiersze), encoding="utf-8")


_t0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
_zapisz("statystyki.jsonl", [{"id": "1", "rodzaj": "notka", "wyswietlenia": 5,
                              "kiedy": (_t0 - timedelta(hours=2)).isoformat()},
                             {"id": "k1", "rodzaj": "komentarz", "wyswietlenia": 0,
                              "kiedy": (_t0 - timedelta(hours=20)).isoformat()}])
_zapisz("wzrost.jsonl", [{"subskrybenci": 30, "kiedy": (_t0 - timedelta(hours=2)).isoformat()}])
_zapisz("zrodla.jsonl", [{"zapisy": {"totals": {}}, "kiedy": (_t0 - timedelta(hours=5)).isoformat()}])
_kom = [{"rodzaj": "komentarz", "udane": True, "nasz_id": "k%d" % i, "kiedy": "2026-10-02T1%d:00:00+00:00" % i}
        for i in range(6)]
_zapisz("dziennik.jsonl", _kom)
sprawdz("wszystko swieze i komentarze mierzone — cisza", alarm.pomiar_statystyk(_t0) is None,
        alarm.pomiar_statystyk(_t0))
_m = alarm.pomiar_statystyk(_t0 + timedelta(hours=16))
sprawdz("KONTRDOWOD: 18 h bez odczytu notek i licznika — alarm nazywa oba pliki",
        _m and "statystyki.jsonl" in _m and "wzrost.jsonl" in _m and "zrodla.jsonl" not in _m, _m)
_zapisz("statystyki.jsonl", [{"id": "1", "rodzaj": "notka", "wyswietlenia": 5,
                              "kiedy": (_t0 - timedelta(hours=2)).isoformat()}])
_m = alarm.pomiar_statystyk(_t0)
sprawdz("KONTRDOWOD: 6 komentarzy z dwoch dob i zaden nie zmierzony — alarm",
        _m and "zmierzonych 0" in _m, _m)
(KATALOG / "zrodla.jsonl").unlink()
_m = alarm.pomiar_statystyk(_t0)
sprawdz("brak pliku panelu to tez alarm", _m and "panelu zrodel" in _m, _m)
sprawdz("kontrola podpieta do zegara alarmu",
        '("pomiar-statystyk", "POMIAR TRESCI OSLEPL", pomiar_statystyk)' in _kod("agent-v2/alarm.py"))

print()
print("=== 9. E20 — REKOMENDACJE ===")
ODP = {}
_oryg_api = browser.api_json
browser.api_json = lambda page, sciezka, baza=None: ODP.get(sciezka.split("?")[0])
try:
    ODP.clear()
    ODP["/api/v1/recommendations/stats/from"] = {"rows": [
        {"target_publication_id": 11, "is_active": True, "target_pub": {"id": 11, "subdomain": "a"}},
        {"target_publication_id": 12, "is_active": False, "target_pub": {"id": 12, "subdomain": "b"}}], "total": 2}
    _kto = browser.kogo_polecamy(object())
    sprawdz("kogo_polecamy: nowy ksztalt `{rows}` ze stats/from, tylko aktywne",
            [browser._numer_polecanej(w) for w in _kto] == ["11"], _kto)
    ODP["/api/v1/recommendations/stats/from"] = [{"id": 5}]
    sprawdz("stary ksztalt (lista) nadal czytany", [browser._numer_polecanej(w) for w in browser.kogo_polecamy(object())] == ["5"])
    ODP["/api/v1/recommendations/stats/from"] = {"errors": ["x"]}
    sprawdz("KONTRDOWOD: blad API to pusta lista, nie wyjatek", browser.kogo_polecamy(object()) == [])
    ODP.clear()
    sprawdz("KONTRDOWOD: nieudany odczyt licznikow to None, nie zera",
            browser.stan_rekomendacji(object()) is None and browser.zapisz_rekomendacje(object()) is None
            and not browser.REKOMENDACJE.exists())
    ODP["/api/v1/recommendations/exist"] = {"recommendingOthers": 5, "beingRecommended": 1, "totalSignups": 3}
    ODP["/api/v1/recommendations/stats/from"] = {"rows": [
        {"target_pub": {"subdomain": "normaltech"}, "created_at": "2026-09-28T18:00:00Z", "is_active": True,
         "is_mutual": False, "xp_signups": 0}]}
    ODP["/api/v1/recommendations/stats/to"] = {"rows": [
        {"source_pub": {"subdomain": "ktos"}, "created_at": "2026-10-02T09:00:00Z", "is_active": True,
         "is_mutual": True, "xp_signups": 3}]}
    _s = browser.zapisz_rekomendacje(object())
    _plik = [json.loads(x) for x in browser.REKOMENDACJE.read_text(encoding="utf-8").splitlines()]
    sprawdz("stan rekomendacji: liczniki panelu i obie strony, dopisany do pliku",
            _s and _s["polecamy"] == 5 and _s["polecaja_nas"] == 1 and _s["zapisy_z_rekomendacji"] == 3
            and _s["my"][0]["sub"] == "normaltech" and _s["nas"][0] == {
                "sub": "ktos", "od": "2026-10-02", "aktywna": True, "wzajemna": True, "zapisy": 3}
            and len(_plik) == 1 and _plik[0]["polecamy"] == 5, (_s, _plik))
finally:
    browser.api_json = _oryg_api
_doby = obserwatorium.rekomendacje_na_doby([
    {"kiedy": "2026-10-01T10:00:00+00:00", "polecamy": 1, "polecaja_nas": 0, "zapisy_z_rekomendacji": 0},
    {"kiedy": "2026-10-01T20:00:00+00:00", "polecamy": 5, "polecaja_nas": 0, "zapisy_z_rekomendacji": 0},
    {"kiedy": "2026-10-02T10:00:00+00:00", "polecamy": 5, "polecaja_nas": 1, "zapisy_z_rekomendacji": 2}])
sprawdz("obserwatorium: stan rekomendacji na koniec doby",
        _doby == {"2026-10-01": {"rek_polecamy": 5, "rek_polecaja_nas": 0, "rek_zapisy": 0},
                  "2026-10-02": {"rek_polecamy": 5, "rek_polecaja_nas": 1, "rek_zapisy": 2}}, _doby)
_konto = dict(obserwatorium.konta()[0], dane=KATALOG)
sprawdz("doby konta maja pola rekomendacji z pliku bota",
        any("rek_polecamy" in w for w in obserwatorium.podsumuj_konto(_konto).values()))
sprawdz("raport: eksperyment z data startu w przyszlosci to 'zaplanowane', nie 'za wczesnie'",
        "if doba > dzis:" in _kod("agent-v2/obserwatorium.py")
        and 'return "zaplanowane"' in _kod("agent-v2/obserwatorium.py"))
_pol = _BR[_BR.index("def polec_publikacje("):_BR.index("def zasubskrybuj(")]
sprawdz("wybor w wyszukiwarce po CALEJ nazwie, bez zgadywania po pierwszym slowie i bez `get_by_text`",
        "re.escape(fraza)" in _pol and "fraza.split()[0]" not in _pol and "get_by_text(fraza" not in _pol
        and 'wynik["podpowiedzi"]' in _pol)
sprawdz("pomiar zapisuje rekomendacje w kazdym przebiegu",
        "rek = zapisz_rekomendacje(page)" in _BR[_BR.index("def nasze_pozycje_do_pomiaru("):])

config.EKSPERYMENTY = dict(ORYG_EKSP)
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
