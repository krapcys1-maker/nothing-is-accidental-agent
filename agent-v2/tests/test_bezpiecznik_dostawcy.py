# -*- coding: utf-8 -*-
"""Bezpiecznik dostawcy (2.10.2026, decyzja wlasciciela: „napraw, zeby sie nie powtorzylo").

CO SIE STALO 1.10.2026. Od 19:35 do 21:55 UTC DeepSeek przyjmowal zapytania
i nie odpowiadal. Przy przeciazeniu wysyla puste linie podtrzymania, wiec limit
odczytu httpx (do 300 s) nigdy nie strzelal: kazde wywolanie wisialo ~15 minut
i konczylo sie `KeyError: 'choices'`. Przebieg 343 zrobil szesc takich wywolan,
az zabil go systemd (SIGTERM). Nic nie wyszlo, a drugie konto stalo tak samo.

TERAZ: kazda proba ma termin CALKOWITY liczony zegarem (`llm._z_terminem`),
a po dwoch zawieszeniach z rzedu dostawca wypada do konca przebiegu
(`llm.DostawcaWylaczony`) — etapy dostaja zwykla porazke, reszta pracy idzie.

BEZ PYTESTA, bez sieci, bez platnych wywolan — dostawca to atrapa. Z korzenia repo.
"""
import contextlib
import io
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, "agent-v2")
import config  # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import db      # noqa: E402
import httpx   # noqa: E402
import llm     # noqa: E402
import stages  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. TERMIN CALKOWITY PROBY ===")
sprawdz("szybka odpowiedz przechodzi", llm._z_terminem(lambda: 7, 1.0) == 7)
_t = time.monotonic()
try:
    llm._z_terminem(lambda: time.sleep(2) or 1, 0.2)
    _w = "przeszlo"
except httpx.ReadTimeout:
    _w = time.monotonic() - _t
sprawdz("SEDNO: wiszace wywolanie przerwane po terminie, a nie po calym czekaniu",
        isinstance(_w, float) and _w < 1.0, _w)


def _zle():
    raise KeyError("choices")


try:
    llm._z_terminem(_zle, 1.0)
    _e = None
except KeyError as exc:
    _e = exc
sprawdz("blad z watku wychodzi w watku glownym, ten sam wyjatek", isinstance(_e, KeyError))

print()
print("=== 2. CO JEST ZAWIESZENIEM ===")
sprawdz("przekroczony czas — zawsze", llm._zawieszenie(httpx.ReadTimeout("x"), 0.1))
sprawdz("KeyError 'choices' po 15 minutach — tak (tak wygladal 1.10)",
        llm._zawieszenie(KeyError("choices"), 900))
sprawdz("KONTRDOWOD: szybki zly JSON — nie", not llm._zawieszenie(KeyError("choices"), 2))
sprawdz("uciecie, odmowa, budzet — nie (odpowiedz przyszla)",
        not any(llm._zawieszenie(e, 900) for e in (
            llm.Truncated("x"), llm.OdmowaDostawcy("x"), llm.BudgetExceeded("x"))))
sprawdz("wylaczony dostawca nie jest bledem przejsciowym (bez ponowien)",
        not llm.przejsciowy(llm.DostawcaWylaczony("x")))
sprawdz("etapy traktuja go jak zwykla porazke, nie przerwanie przebiegu",
        not issubclass(llm.DostawcaWylaczony, stages.PRZERYWAJA))

print()
print("=== 3. LLM.CALL: DWA ZAWIESZENIA Z RZEDU I KONIEC WOLANIA ===")
conn = db.connect()
run = db.start_run(conn, "test-bezpiecznik")
STARE = {k: getattr(config, k) for k in (
    "WOLNO_WOLAC_MODEL", "DRY_RUN", "DEEPSEEK_API_KEY", "MIMO_API_KEY",
    "PONOWIENIE_ODSTEP_S", "TERMIN_CALKOWITY_RAZY", "timeout_for")}
STARE_LLM = {k: getattr(llm, k) for k in ("_call_deepseek", "_call_mimo")}
WOLANIA = []


def wiszacy(purpose, system, user):
    WOLANIA.append(purpose)
    time.sleep(1.0)
    return ("x", 1, 1, 0, 0)


def mimo_ok(purpose, system, user):
    return ('{"note": "ok"}', 10, 5, 0, 0)


try:
    config.WOLNO_WOLAC_MODEL = True
    config.DRY_RUN = False
    config.DEEPSEEK_API_KEY = "offline"
    config.MIMO_API_KEY = "offline"
    config.PONOWIENIE_ODSTEP_S = 0
    config.TERMIN_CALKOWITY_RAZY = 1
    config.timeout_for = lambda max_tokens: 0.15
    llm._call_deepseek = wiszacy
    llm._call_mimo = mimo_ok
    llm._ZAWIESZENIA.clear()
    llm._WYLACZENI.clear()

    _t = time.monotonic()
    _log = io.StringIO()
    with contextlib.redirect_stdout(_log):
        try:
            llm.call("bank", "s", "u", conn=conn, run_id=run)
            w1 = "przeszlo"
        except llm.DostawcaWylaczony as exc:
            w1 = str(exc)
    sprawdz("SEDNO: dwa zawieszenia z rzedu -> DostawcaWylaczony, bez trzeciej proby",
            "wylaczony do konca przebiegu" in w1 and len(WOLANIA) == 2, (w1, WOLANIA))
    sprawdz("caly etap trwal tyle, co dwa terminy, nie 15 minut",
            time.monotonic() - _t < 3, round(time.monotonic() - _t, 2))
    sprawdz("log mowi wprost, ze dostawca wypadl", "[dostawca] deepseek" in _log.getvalue(),
            _log.getvalue()[-200:])

    WOLANIA.clear()
    _t = time.monotonic()
    try:
        llm.call("radar", "s", "u", conn=conn, run_id=run)
        w2 = "przeszlo"
    except llm.DostawcaWylaczony:
        w2 = time.monotonic() - _t
    sprawdz("SEDNO: kolejny etap u tego dostawcy konczy sie od razu, bez wolania go",
            isinstance(w2, float) and w2 < 0.5 and WOLANIA == [], (w2, WOLANIA))
    wiersze = conn.execute("SELECT purpose, ok, note FROM calls WHERE run_id=? ORDER BY id",
                           (run,)).fetchall()
    sprawdz("ksiega: obie porazki zapisane (ok=0), druga z powodem",
            len(wiersze) == 2 and all(r[1] == 0 for r in wiersze)
            and "DostawcaWylaczony" in str(wiersze[-1][2]), wiersze)
    with contextlib.redirect_stdout(io.StringIO()):
        txt = llm.call("note_mimo", "s", "u", conn=conn, run_id=run)
    sprawdz("inny dostawca (MiMo) dziala dalej", txt == '{"note": "ok"}', txt)

    print()
    print("=== 4. JEDNO ZAWIESZENIE, POTEM ODPOWIEDZ — LICZNIK OD ZERA ===")
    llm._ZAWIESZENIA.clear()
    llm._WYLACZENI.clear()
    stan = {"n": 0}

    def raz_wisi(purpose, system, user):
        stan["n"] += 1
        if stan["n"] == 1:
            time.sleep(1.0)
        return ('{"a": 1}', 5, 5, 0, 0)

    llm._call_deepseek = raz_wisi
    with contextlib.redirect_stdout(io.StringIO()):
        txt = llm.call("bank", "s", "u", conn=conn, run_id=run)
    sprawdz("chwilowe zawieszenie nie wylacza dostawcy: wynik jest, licznik wyzerowany",
            txt == '{"a": 1}' and llm._ZAWIESZENIA.get("deepseek") == 0
            and "deepseek" not in llm._WYLACZENI, (txt, llm._ZAWIESZENIA, llm._WYLACZENI))
finally:
    for k, v in STARE.items():
        setattr(config, k, v)
    for k, v in STARE_LLM.items():
        setattr(llm, k, v)
    llm._ZAWIESZENIA.clear()
    llm._WYLACZENI.clear()

print()
print("=== 5. USTAWIENIA ===")
sprawdz("termin calkowity nie krotszy niz limit odczytu (legalne dlugie odpowiedzi przechodza)",
        config.TERMIN_CALKOWITY_RAZY >= 1)
sprawdz("wylaczenie po dwoch zawieszeniach, prog zawieszenia 2 minuty",
        (config.ZAWIESZEN_DO_WYLACZENIA, config.PROG_ZAWIESZENIA_S) == (2, 120))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
