# -*- coding: utf-8 -*-
"""Sterowanie rozumowaniem DeepSeeka na `chat/completions`.

CO BYLO NIE TAK. `_call_deepseek` wysylal `model`, `max_tokens` i `messages` —
i nic wiecej. Tymczasem DeepSeek na tej koncowce rozumuje DOMYSLNIE, a jedyne
pokretlo, jakie konto mialo (`config.DEEPSEEK_EFFORT`), trafia wylacznie do
`/responses`, czyli do pieciu etapow z wyszukiwaniem. Pozostale dziewietnascie
nie widzialo go nigdy. Zapis w `KOSZT_2026-09-05.md` („DeepSeek ma jedno
wspolne DEEPSEEK_EFFORT=low — juz najnizsze") byl z tego powodu nieprawdziwy
dla wiekszosci etapow.

CO ZMIERZYLEM NA ZYWYM API 6 wrzesnia 2026 (pytajac API, nie dokumentacji —
to samo pytanie, `deepseek-v4-flash`, cztery warianty):

    brak parametru (jak bylo)    53 tokeny wyjscia, 42 rozumowania
    thinking disabled            10                  0
    thinking low                 91                 80
    thinking high               121                110

Wszystkie cztery daly IDENTYCZNA, poprawna odpowiedz. Wniosek, ktory z tego
plynie, jest inny niz zalecal zewnetrzny audyt: domyslne ustawienie NIE JEST
`high` — jest nizsze niz `low`, wiec DeepSeek dobiera wysilek sam, a zalecane
`low` byloby DROZSZE od stanu dzisiejszego.

CZEGO TEN TEST PILNUJE PRZEDE WSZYSTKIM. Ze wlaczenie tego mechanizmu NIE
ZMIENIA NICZEGO, dopoki etap nie zostanie swiadomie dopisany do tablicy. Pusta
tablica ma znaczyc „dokladnie to, co konto robilo do dzis" — bo na prawdziwym
prompcie `cele` wylaczenie rozumowania ZMIENILO DECYZJE (szesc wybranych celow
zamiast trzech), a szesc celow to dwa razy wiecej platnych prob komentarza
w dole potoku.

BEZ PYTESTA, zero sieci, zero platnych wywolan. Uruchamiac z korzenia repo:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_myslenie_deepseeka.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm      # noqa: E402

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


class _Odpowiedz:
    status_code = 200

    @staticmethod
    def raise_for_status():
        pass

    @staticmethod
    def json():
        return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                          "prompt_cache_hit_tokens": 0}}


wyslane = {}


def _atrapa_post(url, headers=None, json=None, timeout=None):
    wyslane["url"] = url
    wyslane["cialo"] = json
    return _Odpowiedz()


print("=== 1. DOMYSLNIE NIC SIE NIE ZMIENIA ===")
# To jest najwazniejsza asercja w tym pliku. Mechanizm ma byc BEZCZYNNY,
# dopoki ktos swiadomie nie doda etapu.
sprawdz("tablica `DEEPSEEK_MYSLENIE` jest pusta",
        config.DEEPSEEK_MYSLENIE == {}, config.DEEPSEEK_MYSLENIE)
sprawdz("nieznany etap nie dostaje ustawienia",
        config.myslenie_deepseek("cokolwiek") is None,
        config.myslenie_deepseek("cokolwiek"))

_oryg = llm.httpx.post
try:
    llm.httpx.post = _atrapa_post
    llm._call_deepseek("cele", "sys", "usr")
    sprawdz("`thinking` NIE leci do API dla etapu spoza tablicy",
            "thinking" not in (wyslane.get("cialo") or {}),
            sorted((wyslane.get("cialo") or {}).keys()))
    sprawdz("a cialo nadal niesie to, co zawsze",
            all(k in (wyslane.get("cialo") or {})
                for k in ("model", "max_tokens", "messages")),
            sorted((wyslane.get("cialo") or {}).keys()))
    sprawdz("i idzie na `chat/completions`",
            str(wyslane.get("url", "")).endswith("/chat/completions"),
            wyslane.get("url"))

    print()
    print("=== 2. ETAP DOPISANY DO TABLICY DOSTAJE PARAMETR ===")
    config.DEEPSEEK_MYSLENIE["cele"] = {"type": "disabled"}
    try:
        wyslane.clear()
        llm._call_deepseek("cele", "sys", "usr")
        sprawdz("`thinking` leci dla etapu z tablicy",
                (wyslane.get("cialo") or {}).get("thinking") == {"type": "disabled"},
                (wyslane.get("cialo") or {}).get("thinking"))
        wyslane.clear()
        llm._call_deepseek("comment", "sys", "usr")
        sprawdz("a INNY etap nadal go nie dostaje",
                "thinking" not in (wyslane.get("cialo") or {}),
                sorted((wyslane.get("cialo") or {}).keys()))
    finally:
        config.DEEPSEEK_MYSLENIE.pop("cele", None)

    print()
    print("=== 3. TABLICA NIE ODDAJE SWOJEGO WNETRZA ===")
    # Gdyby oddawala te sama liste, jedno wywolanie mogloby ja po cichu
    # przestawic dla calego procesu.
    config.DEEPSEEK_MYSLENIE["cele"] = {"type": "enabled", "reasoning_effort": "low"}
    try:
        w = config.myslenie_deepseek("cele")
        w["reasoning_effort"] = "high"
        sprawdz("zmiana oddanego slownika nie psuje tablicy",
                config.DEEPSEEK_MYSLENIE["cele"]["reasoning_effort"] == "low",
                config.DEEPSEEK_MYSLENIE["cele"])
    finally:
        config.DEEPSEEK_MYSLENIE.pop("cele", None)

    print()
    print("=== 4. PUSTY WPIS ZNACZY 'NIE RUSZAJ', NIE 'WYSLIJ PUSTKE' ===")
    config.DEEPSEEK_MYSLENIE["cele"] = {}
    try:
        sprawdz("pusty slownik traktowany jak brak wpisu",
                config.myslenie_deepseek("cele") is None,
                config.myslenie_deepseek("cele"))
        wyslane.clear()
        llm._call_deepseek("cele", "sys", "usr")
        sprawdz("i nic nie leci do API",
                "thinking" not in (wyslane.get("cialo") or {}),
                sorted((wyslane.get("cialo") or {}).keys()))
    finally:
        config.DEEPSEEK_MYSLENIE.pop("cele", None)
finally:
    llm.httpx.post = _oryg

print()
print("=== 5. STARE POKRETLO NADAL DOTYCZY TYLKO `/responses` ===")
# Zeby nikt nie uznal, ze `DEEPSEEK_EFFORT` zaczal dzialac wszedzie.
#
# PIERWSZA WERSJA TEGO SPRAWDZENIA BYLA ZLA i oblala z wlasnej winy:
# porownywala POZYCJE W PLIKU („`/responses` stoi przed `_call_deepseek`"),
# czyli uklad tekstu, a nie zachowanie kodu. To ten sam blad, ktory tego dnia
# zdarzyl mi sie juz raz. Teraz pytam DRZEWO SKLADNI, ktora funkcja czego uzywa.
import ast   # noqa: E402

_drzewo = ast.parse(pathlib.Path("agent-v2/llm.py").read_text(encoding="utf-8"))


def _uzywa(nazwa_funkcji, nazwa_stalej):
    for w in ast.walk(_drzewo):
        if isinstance(w, ast.FunctionDef) and w.name == nazwa_funkcji:
            return any(isinstance(x, ast.Attribute) and x.attr == nazwa_stalej
                       for x in ast.walk(w))
    return None


sprawdz("`_call_deepseek` NIE siega po `DEEPSEEK_EFFORT`",
        _uzywa("_call_deepseek", "DEEPSEEK_EFFORT") is False,
        _uzywa("_call_deepseek", "DEEPSEEK_EFFORT"))
sprawdz("ale siega po `myslenie_deepseek`",
        _uzywa("_call_deepseek", "myslenie_deepseek") is True)
# KONTRDOWOD: gdzies w pliku `DEEPSEEK_EFFORT` byc MUSI, inaczej sprawdzenie
# wyzej przechodziloby takze wtedy, gdyby ktos skasowal cale pokretlo.
sprawdz("KONTRDOWOD: `DEEPSEEK_EFFORT` nadal gdzies w `llm.py` jest",
        any(isinstance(x, ast.Attribute) and x.attr == "DEEPSEEK_EFFORT"
            for x in ast.walk(_drzewo)))

print()
print("=== 6. POMIAR, NA KTORYM TO STOI, JEST ZAPISANY PRZY KODZIE ===")
# Liczba bez zapisanego pomiaru wraca za tydzien jako „chyba tak bylo".
_cfg = pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8")
sprawdz("config zapisuje, ze domyslne NIE JEST `high`",
        "NIE JEST `high`" in _cfg)
sprawdz("i zapisuje, dlaczego tablica jest pusta",
        "ZMIENILO DECYZJE" in _cfg.replace("Ę", "E").replace("Ł", "L")
        or "ZMIENIŁO DECYZJĘ" in _cfg)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
