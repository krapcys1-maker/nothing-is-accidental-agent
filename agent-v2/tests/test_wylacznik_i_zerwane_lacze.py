# -*- coding: utf-8 -*-
"""Dwie wady zgloszone 7 wrzesnia 2026 przez agenta drugiej instalacji.

Zgloszenie przyszlo Z ZEWNATRZ, wiec sprawdzilem obie rzeczy sam, w kodzie
i na zywym srodowisku. Obie okazaly sie prawdziwe.

WADA 1 — WYLACZNIK ZATRZYMYWAL RACHUNEK, NIE KONTO.

`config.KILL_SWITCH` byl sprawdzany w JEDNYM miejscu: `llm._preflight`, czyli
przed wywolaniem MODELU. W `browser.py` nie wystepowal ani razu.

ZGLOSZENIE MOWILO O TRZECH AKCJACH; WYPROWADZONE Z KODU WYSZLO GORZEJ. Przez
`naprawde_wyslac` — jedyna brame przed publicznym dzialaniem — przechodzi
JEDENASCIE funkcji i ZADNA nie wola modelu bezposrednio:

    _klik_na_profilu, obserwuj_profil, polec_publikacje, polub_w_kanale,
    restackuj_w_kanale, ustaw_oswiadczenie_ai, wystaw_artykul,
    wystaw_komentarz, wystaw_notke, wystaw_odpowiedz,
    wystaw_odpowiedz_pod_artykulem

Wylacznik zatrzymywal wiec PISANIE nowych tekstow (bo to idzie przez model),
ale nie zatrzymywal WYSTAWIANIA — ani polubien, obserwacji i rekomendacji,
ktore modelu nie potrzebuja wcale. Wlasciciel ustawiajacy `KILL_SWITCH=true`,
zeby zatrzymac konto, dostawal konto, ktore dalej dziala w swiecie. To jest
gorsze niz brak wylacznika, bo wyglada na dzialajacy.

Nazwy funkcji w tym tescie NIE sa wpisane recznie — sekcja 3 wyprowadza je
z drzewa skladni `browser.py`. Moja pierwsza wersja zgadywala (`polub`,
`obserwuj`) i oblala na nieistniejacych nazwach.

WADA 2 — ZERWANE LACZE KSIEGOWANE JAKO BLAD TRWALY.

`llm.przejsciowy` rozpoznawal `httpx.TimeoutException` i `httpx.TransportError`.
Wyjatki SDK Anthropica NIE dziedzicza po niczym z `httpx` i nie niosa
`status_code` — zmierzone na produkcyjnym srodowisku:

    APITimeoutError      dziedziczy po httpx: False   status_code: brak
    APIConnectionError   dziedziczy po httpx: False   status_code: brak
    przejsciowy(...) oddawalo dla obu: False

Czyli jedno zerwane polaczenie przy pisaniu artykulu nie bylo ponawiane, tylko
od razu przerzucalo prace na pisarza zapasowego — bez sladu w logu, ze to byla
awaria transportu, a nie odmowa modelu.

BEZ PYTESTA, zero sieci, zero platnych wywolan. Z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_wylacznik_i_zerwane_lacze.py
"""
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import browser   # noqa: E402
import httpx     # noqa: E402
import llm       # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


print("=== 1. WYLACZNIK ZATRZYMUJE TAKZE TO, CO NIE WOLA MODELU ===")
_stary_ks, _stary_dry = config.KILL_SWITCH, config.DRY_RUN
try:
    config.KILL_SWITCH = False
    config.DRY_RUN = False
    sprawdz("KONTROLA: przy wylaczniku OFF akcja przechodzi",
            browser.naprawde_wyslac(True, "polubienie") is True)

    config.KILL_SWITCH = True
    sprawdz("przy wylaczniku ON akcja NIE przechodzi",
            browser.naprawde_wyslac(True, "polubienie") is False)
    # I nie zamienia „nie prosze" na „prosze" — bramka ma tylko odmawiac.
    sprawdz("i nie wypuszcza czegos, o co nikt nie prosil",
            browser.naprawde_wyslac(False, "polubienie") is False)

    config.KILL_SWITCH = False
    config.DRY_RUN = True
    sprawdz("DRY_RUN nadal dziala tak jak dzialal",
            browser.naprawde_wyslac(True, "polubienie") is False)
finally:
    config.KILL_SWITCH, config.DRY_RUN = _stary_ks, _stary_dry

print()
print("=== 2. TO NAPRAWDE JEST JEDYNA BRAMA ===")
# Warunek w `naprawde_wyslac` jest wart tyle, ile miejsc przez nia przechodzi.
_zr_b = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
_ile = len(re.findall(r"naprawde_wyslac\(", _zr_b)) - 1   # bez definicji
sprawdz("przez brame przechodzi wiele dzialan (%d)" % _ile, _ile >= 8, _ile)
sprawdz("i wylacznik jest sprawdzany WLASNIE w niej",
        "config.KILL_SWITCH" in _zr_b)

print()
print("=== 3. DLACZEGO TO BYLA WADA: czesc tych akcji nie wola modelu ===")
# Gdyby KAZDA wolala model, `_preflight` zatrzymalby je i wylacznik dzialalby
# przypadkiem. Nie zgaduje nazw funkcji — WYPROWADZAM je z kodu: bioremy
# kazda funkcje, ktora przechodzi przez brame, i pytam, czy siega po `llm`.
import ast   # noqa: E402

_drzewo = ast.parse(_zr_b)
_przez_brame = {}
for _w in ast.walk(_drzewo):
    if not isinstance(_w, ast.FunctionDef):
        continue
    _ma_brame = any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id == "naprawde_wyslac" for x in ast.walk(_w))
    if not _ma_brame:
        continue
    _wola_model = any(isinstance(x, ast.Attribute)
                      and isinstance(x.value, ast.Name) and x.value.id == "llm"
                      for x in ast.walk(_w))
    _przez_brame[_w.name] = _wola_model

sprawdz("znalazlem funkcje przechodzace przez brame (%d)" % len(_przez_brame),
        len(_przez_brame) >= 8, sorted(_przez_brame))
_bez_modelu = sorted(k for k, v in _przez_brame.items() if not v)
print("      bez modelu: %s" % ", ".join(_bez_modelu))
print("      z modelem : %s"
      % ", ".join(sorted(k for k, v in _przez_brame.items() if v)))
# TO JEST SEDNO: gdyby ta lista byla pusta, wylacznik w preflighcie
# wystarczylby i poprawka nie mialaby sensu.
sprawdz("CZESC dzialan NIE wola modelu — preflight ich nie zatrzyma",
        bool(_bez_modelu), _przez_brame)

print()
print("=== 4. ZERWANE LACZE JEST BLEDEM PRZEJSCIOWYM ===")
import anthropic   # noqa: E402

_req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
for nazwa in ("APITimeoutError", "APIConnectionError"):
    K = getattr(anthropic, nazwa, None)
    if K is None:
        print("  (SDK nie ma %s — pomijam)" % nazwa)
        continue
    # KONTRDOWOD DO POPRAWKI: gdyby te klasy dziedziczyly po httpx, poprawka
    # bylaby zbedna, a ten test niczego by nie pilnowal.
    sprawdz("KONTRDOWOD: %-18s NIE dziedziczy po httpx" % nazwa,
            not issubclass(K, (httpx.TimeoutException, httpx.TransportError)))
    try:
        e = K(request=_req)
    except TypeError:
        e = K(message="x", request=_req)
    sprawdz("%-18s jest PRZEJSCIOWY" % nazwa, llm.przejsciowy(e) is True,
            llm.przejsciowy(e))

print()
print("=== 5. RESZTA KLASYFIKATORA NIETKNIETA ===")
# Poprawka ma dokladac, a nie przestawiac. Zwlaszcza `BudgetExceeded`:
# ponawianie po wyczerpanym budzecie to palenie pieniedzy w petli.
sprawdz("httpx.ConnectError nadal przejsciowy",
        llm.przejsciowy(httpx.ConnectError("x")) is True)
sprawdz("httpx.ReadTimeout nadal przejsciowy",
        llm.przejsciowy(httpx.ReadTimeout("x")) is True)
sprawdz("BudgetExceeded nadal TRWALY",
        llm.przejsciowy(llm.BudgetExceeded("x")) is False)
sprawdz("PreflightFailed nadal TRWALY",
        llm.przejsciowy(llm.PreflightFailed("x")) is False)
sprawdz("Truncated nadal TRWALY",
        llm.przejsciowy(llm.Truncated("x")) is False)
sprawdz("zwykly ValueError nadal TRWALY",
        llm.przejsciowy(ValueError("x")) is False)


class _Odmowa(Exception):
    status_code = 403


class _Przeciazenie(Exception):
    status_code = 529


sprawdz("kod 403 nadal TRWALY", llm.przejsciowy(_Odmowa()) is False)
sprawdz("kod 529 nadal PRZEJSCIOWY", llm.przejsciowy(_Przeciazenie()) is True)

print()
print("=== 6. BRAK KLASY W SDK NIE WYWALA KLASYFIKATORA ===")
# Starsze wydania SDK nie mialy `APITimeoutError`. Klasyfikator bledow, ktory
# sam sie wywala, jest gorszy niz zly klasyfikator.
_byla = getattr(anthropic, "APITimeoutError", None)
try:
    if _byla is not None:
        del anthropic.APITimeoutError
    sprawdz("bez `APITimeoutError` w SDK nadal dziala",
            llm.przejsciowy(httpx.ConnectError("x")) is True)
    sprawdz("i nadal rozpoznaje `APIConnectionError`",
            llm.przejsciowy(anthropic.APIConnectionError(request=_req)) is True)
finally:
    if _byla is not None:
        anthropic.APITimeoutError = _byla

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
