# -*- coding: utf-8 -*-
"""E11 — pisarz notek Xiaomi MiMo V2.6 Flash na polowie notek NIE (28.09.2026).

PO CO. Wlasciciel po slepym tescie (MiMo 11:5 na 8 produkcyjnych promptach):
„mozesz mu dac notki na probe, ale tylko na NIE". Polowa notek z banku idzie do
MiMo (`config.EKSPERYMENTY["pisarz"]`, wlasne losowanie), reszta zostaje u DeepSeeka.

Test pilnuje, z kontrdowodami:
  1. dostawca `mimo`, kontrola wstepna wymaga `MIMO_API_KEY`;
  2. `_call_mimo`: adres API Xiaomi, naglowek `api-key`, myslenie wylaczone jak u
     DeepSeeka dla notki, sufit tokenow etapu, trafienia w cache odjete od wejscia,
     ucieta odpowiedz = `Truncated`;
  3. `llm.call("note_mimo")` zapisuje koszt po cenniku MiMo; wywolanie z siecia
     na MiMo to blad konfiguracji;
  4. PRAWDZIWE `notki_dnia`: ramie „on" -> `note_mimo`, „off" -> `note`, ramie
     w wyniku; bez klucza zostaje DeepSeek; gdy MiMo nie napisze — pisze DeepSeek
     w tym samym przebiegu i wynik niesie `pisarz_zastepczy`.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
import db       # noqa: E402
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


print("=== 1. DOSTAWCA I KLUCZ ===")
sprawdz("mimo-v2.6-flash -> dostawca mimo", llm.dostawca(config.MIMO) == "mimo")
sprawdz("KONTRDOWOD: DeepSeek zostaje DeepSeekiem", llm.dostawca(config.DEEPSEEK) == "deepseek")
sprawdz("note_mimo idzie do MiMo z sufitem jak zwykla notka",
        config.MODEL_FOR["note_mimo"] == config.MIMO
        and config.MAX_TOKENS["note_mimo"] == config.MAX_TOKENS["note"])
sprawdz("cena MiMo z cennika Xiaomi (0,14 / 0,28 / cache 0,0028)",
        config.PRICING[config.MIMO] == {"in": 0.14, "out": 0.28, "cache": 0.0028, "verified": False})
conn = db.connect()
run = db.start_run(conn, "test-pisarz-mimo")
# Kazde wywolanie modelu w tym tescie idzie na atrape `httpx.post` — bez tego
# bezpiecznik darmowych testow (serwer) odmawia juz w kontroli wstepnej.
config.WOLNO_WOLAC_MODEL = True
stary_klucz = config.MIMO_API_KEY
config.MIMO_API_KEY = ""
try:
    llm._preflight("note_mimo", conn, run)
    bez_klucza = None
except llm.PreflightFailed as exc:
    bez_klucza = str(exc)
sprawdz("bez MIMO_API_KEY kontrola wstepna odmawia i mowi, czego brak",
        bez_klucza is not None and "MIMO_API_KEY" in bez_klucza, bez_klucza)
config.MIMO_API_KEY = "test-key"

print()
print("=== 2. TRANSPORT ===")
wyslane = []


class Odp:
    def __init__(self, dane):
        self._d = dane

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def atrapa_post(dane):
    def post(url, headers=None, json=None, timeout=None):
        wyslane.append({"url": url, "headers": headers, "json": json})
        return Odp(dane)
    return post


DANE = {"choices": [{"finish_reason": "stop", "message": {"content": '{"note": "A MiMo note."}'}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 300,
                  "prompt_tokens_details": {"cached_tokens": 400}}}
stary_post = llm.httpx.post
llm.httpx.post = atrapa_post(DANE)
try:
    tekst, tin, tout, szuk, hit = llm._call_mimo("note_mimo", "system", "user")
finally:
    llm.httpx.post = stary_post
w = wyslane[-1]
sprawdz("adres API Xiaomi zgodny z OpenAI",
        w["url"] == "https://api.xiaomimimo.com/v1/chat/completions", w["url"])
sprawdz("klucz w naglowku api-key", (w["headers"] or {}).get("api-key") == "test-key")
sprawdz("model, sufit i myslenie wylaczone (jak DeepSeek dla notki)",
        w["json"]["model"] == config.MIMO and w["json"]["max_tokens"] == config.MAX_TOKENS["note_mimo"]
        and w["json"].get("thinking") == {"type": "disabled"}, w["json"])
sprawdz("system i user w wiadomosciach",
        [m["role"] for m in w["json"]["messages"]] == ["system", "user"])
sprawdz("trafienia w cache odjete od wejscia: 1000 - 400 = 600, cache 400, wyjscie 300",
        (tin, hit, tout, szuk) == (600, 400, 300, 0), (tin, hit, tout, szuk))
sprawdz("tekst odpowiedzi", tekst == '{"note": "A MiMo note."}', tekst)
llm.httpx.post = atrapa_post({"choices": [{"finish_reason": "length", "message": {"content": "{"}}],
                              "usage": {"prompt_tokens": 10, "completion_tokens": 10}})
try:
    try:
        llm._call_mimo("note_mimo", "s", "u")
        uciete = False
    except llm.Truncated:
        uciete = True
finally:
    llm.httpx.post = stary_post
sprawdz("ucieta odpowiedz = Truncated (bez niedomknietego JSON-a dalej)", uciete)

print()
print("=== 3. LLM.CALL: KOSZT PO CENNIKU MiMo, BEZ SIECI ===")
config.WOLNO_WOLAC_MODEL = True
config.DRY_RUN = False
llm.httpx.post = atrapa_post(DANE)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        wynik = llm.call("note_mimo", "system", "user", conn=conn, run_id=run)
finally:
    llm.httpx.post = stary_post
wiersz = conn.execute("SELECT provider, model, tokens_in, cache_hit, tokens_out, cost_usd FROM calls "
                      "WHERE run_id=? ORDER BY id DESC LIMIT 1", (run,)).fetchone()
oczekiwany = round((600 * 0.14 + 400 * 0.0028 + 300 * 0.28) / 1e6, 6)
sprawdz("wywolanie zapisane: dostawca mimo, model MiMo, tokeny z cache osobno",
        wiersz is not None and tuple(wiersz[:5]) == ("mimo", config.MIMO, 600, 400, 300), wiersz)
sprawdz("koszt po cenniku MiMo", wiersz is not None and abs(float(wiersz[5]) - oczekiwany) < 1e-9,
        (wiersz[5] if wiersz else None, oczekiwany))
sprawdz("llm.call oddaje tekst", wynik == '{"note": "A MiMo note."}', wynik)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        llm.call("note_mimo", "s", "u", conn=conn, run_id=run, web_search=True)
    z_siecia = "przeszlo"
except llm.PreflightFailed as exc:
    z_siecia = str(exc)
sprawdz("wywolanie z siecia na MiMo = blad konfiguracji, nie ciche szukanie",
        "MiMo bez szukania" in z_siecia, z_siecia)

print()
print("=== 4. PRAWDZIWE notki_dnia: RAMIE, KLUCZ, ZASTEPCA ===")
ETAPY = []
PUSTO = {"note_mimo"}


def _atrapa_note(conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", **k):
    ETAPY.append(etap)
    if etap in PUSTO:
        return {"type": typ, "forma": note_form, "candidates": []}
    return {"type": typ, "forma": note_form,
            "candidates": [{"note": "A plain note by %s." % etap, "safe_to_post": True}]}


FAKT = {"fact": "On 27 September 2026 a regulator published a rule on AI audits.",
        "url": "https://example.org/audits", "source_date": "2026-09-27", "status": "nowy",
        "styk": "branza"}
_zastepcze = {"artykul_do_promocji": lambda: None, "pamiec_wystawionych": lambda: [],
              "wez_kandydatow": lambda ile=1: [],
              "znajdz_ciekawostki": lambda conn, run_id, ile=8: [dict(FAKT)],
              "wybierz_material": lambda zapas, *a, **k: zapas.pop(0) if zapas else None,
              "wniosek": lambda *a, **k: {},
              "opublikowane_teksty": lambda *a, **k: [], "teksty_ostatnich_notek": lambda *a, **k: [],
              "note": _atrapa_note}
_oryginaly = {n: getattr(stages, n) for n in _zastepcze}
import glebia   # noqa: E402

_karta = glebia.karta_glebi


def dzien(udzial, klucz="test-key", pusto=frozenset({"note_mimo"})):
    ETAPY.clear()
    PUSTO.clear()
    PUSTO.update(pusto)
    stare = dict(config.EKSPERYMENTY)
    # Tylko E11: ramie wniosku (E10) nie ma tu nic do rzeczy.
    config.EKSPERYMENTY.clear()
    config.EKSPERYMENTY["pisarz"] = {"udzial": udzial, "od": "2000-01-01", "do": "2999-12-31"}
    config.MIMO_API_KEY = klucz
    glebia.karta_glebi = lambda *a, **k: None
    try:
        for n, f in _zastepcze.items():
            setattr(stages, n, f)
        with contextlib.redirect_stdout(io.StringIO()) as log:
            n = stages.notki_dnia(None, 0, ciekawostki=[], ile=1)
    finally:
        for n2, f in _oryginaly.items():
            setattr(stages, n2, f)
        glebia.karta_glebi = _karta
        config.EKSPERYMENTY.clear()
        config.EKSPERYMENTY.update(stare)
    return n, log.getvalue()


n, log = dzien(1.0, pusto=frozenset())
sprawdz("ramie on: pisze MiMo (note_mimo), ramie w wyniku",
        ETAPY == ["note_mimo"] and bool(n) and (n[0].get("eksperymenty") or {}).get("pisarz") == "on",
        (ETAPY, n[0].get("eksperymenty") if n else None))
n, log = dzien(1.0)
sprawdz("MiMo nie napisal: w tym samym przebiegu pisze DeepSeek, wynik niesie pisarz_zastepczy",
        ETAPY == ["note_mimo", "note"] and bool(n) and n[0].get("pisarz_zastepczy") is True
        and (n[0].get("candidates") or [{}])[0].get("note") == "A plain note by note.", (ETAPY, n))
sprawdz("log mowi, ze MiMo nie napisal i kto pisze", "MiMo nie napisal notki" in log, log[-300:])
n, log = dzien(0.0)
sprawdz("KONTRDOWOD ramie off: pisze DeepSeek, ramie off w wyniku",
        ETAPY == ["note"] and (n[0].get("eksperymenty") or {}).get("pisarz") == "off", (ETAPY, n))
n, log = dzien(1.0, klucz="")
sprawdz("bez klucza: zostaje DeepSeek (przebieg nie pada), log mowi dlaczego",
        ETAPY == ["note"] and "brak MIMO_API_KEY" in log, (ETAPY, log[-300:]))
config.MIMO_API_KEY = stary_klucz

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
