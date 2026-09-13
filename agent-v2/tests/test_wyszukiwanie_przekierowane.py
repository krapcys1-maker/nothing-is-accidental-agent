"""Wywolanie z siecia idzie do modelu, ktory NAPRAWDE szuka — i kosztuje tyle, ile kosztuje.

DLACZEGO TO POWSTALO. 10 wrzesnia 2026 DeepSeek przestawil `deepseek-v4-flash`
na V4.1 Flash, a ten przez `/responses` nie ma narzedzia wyszukiwania. Zmierzone
13 wrzesnia z tabeli `calls`, przed i po 10.09 04:00 UTC:

    factcheck        170 z 238 wywolan szukalo  ->  0 z 38
    curiosity         15 z 44                   ->  0 z 5
    aktualne_modele    6 z 6                    ->  0 z 5

Wywolania konczyly sie sukcesem, tylko dziesiec razy taniej — wiec sprawdzanie
faktow przed publikacja (`stages.zweryfikuj`: notki, komentarze, artykuly) przez
trzy dni sprawdzala tekst pamiecia modelu, a nie siecia. A 14 wrzesnia o 04:00 UTC to samo czekalo `deepseek-v4-pro`.

Ten plik pilnuje czterech rzeczy: kto szuka, dokad idzie wywolanie z siecia,
co trafia do ksiegi i po jakiej stawce DeepSeek liczy przekierowane nazwy.
"""
import pathlib
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import db      # noqa: E402
import llm     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


T = datetime.fromisoformat

print("=== 1. KTO SZUKA — daty z pomiaru 13 wrzesnia 2026 ===")
sprawdz("V4.1 Flash nie szuka", not config.szuka_naprawde("deepseek-flash", T("2026-09-13T12:00:00+00:00")))
sprawdz("stara nazwa Flash po 10.09 tez nie",
        not config.szuka_naprawde("deepseek-v4-flash", T("2026-09-11T12:00:00+00:00")))
sprawdz("stara nazwa Flash SZUKALA przed 10.09",
        config.szuka_naprawde("deepseek-v4-flash", T("2026-09-09T12:00:00+00:00")))
sprawdz("V4 Pro szuka jeszcze 13.09",
        config.szuka_naprawde("deepseek-v4-pro", T("2026-09-13T12:00:00+00:00")))
sprawdz("V4 Pro nie szuka od 14.09 04:00 UTC",
        not config.szuka_naprawde("deepseek-v4-pro", T("2026-09-14T04:00:00+00:00")))
sprawdz("nieznany DeepSeek nie szuka, dopoki proba nie potwierdzi",
        not config.szuka_naprawde("deepseek-pro", T("2026-09-20T12:00:00+00:00")))
sprawdz("Claude szuka", config.szuka_naprawde(config.HAIKU, T("2026-09-13T12:00:00+00:00")))
sprawdz("zastepca dla faktow to Haiku", config.model_do_szukania("factcheck") == config.HAIKU)
# Opus kosztowal w dyskoverii do $1,65 przy suficie przebiegu artykulu $2,20.
sprawdz("odkrywanie zrodel do artykulu tez na Haiku, nie na Opusie",
        config.model_do_szukania("discovery") == config.HAIKU)
sprawdz("Haiku ma wpis narzedzia wyszukiwania bez ostrzezenia",
        config.narzedzie_wyszukiwania(config.HAIKU) == ("web_search_20250305", ""))

print()
print("=== 2. PROBA Z nowe_modele MA PIERWSZENSTWO — ale tylko pozniejsza niz awaria ===")
_proby = dict(config.PROBY_WYSZUKIWANIA)
try:
    config.PROBY_WYSZUKIWANIA["deepseek-flash"] = {"dziala": True, "kiedy": "2026-09-20T12:00:00+00:00"}
    sprawdz("swieza udana proba przywraca szukanie",
            config.szuka_naprawde("deepseek-flash", T("2026-09-21T00:00:00+00:00")))
    sprawdz("ale nie wstecz: przed proba dalej nie szuka",
            not config.szuka_naprawde("deepseek-flash", T("2026-09-19T00:00:00+00:00")))
    config.PROBY_WYSZUKIWANIA["deepseek-v4-pro"] = {"dziala": True, "kiedy": "2026-09-13T12:00:00+00:00"}
    sprawdz("proba sprzed daty awarii nie przykrywa awarii",
            not config.szuka_naprawde("deepseek-v4-pro", T("2026-09-15T00:00:00+00:00")))
finally:
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_proby)

print()
print("=== 3. llm.call: z siecia do zastepcy, bez sieci zostaje na etapie ===")
wywolania = []


def falszywy_claude(purpose, system, user, web_search, model=None):
    wywolania.append(("claude", purpose, model, web_search))
    return '{"facts": []}', 100, 10, 2, ["https://example.org/a"]


def falszywy_responses(purpose, system, user, model=None):
    wywolania.append(("deepseek-responses", purpose, model, True))
    return '{"facts": []}', 100, 10, 0, []


def falszywy_deepseek(purpose, system, user):
    wywolania.append(("deepseek", purpose, config.MODEL_FOR[purpose], False))
    return '{"facts": []}', 100, 10, 0, 0


_oryg = {"claude": llm._call_claude, "responses": llm._call_deepseek_responses,
         "deepseek": llm._call_deepseek, "szuka": config.szuka_naprawde,
         "wolno": config.WOLNO_WOLAC_MODEL, "ka": config.ANTHROPIC_API_KEY,
         "kd": config.DEEPSEEK_API_KEY, "sucho": config.DRY_RUN}
_szuka_prawdziwe = config.szuka_naprawde
zdjecie = config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
try:
    config.WOLNO_WOLAC_MODEL = True
    # `DRY_RUN` konczy `call` PRZED wyborem sciezki dostawcy, wiec z nim ten
    # test nie widzialby, dokad wywolanie naprawde idzie. Wywolania i tak sa
    # atrapami — sieci nie dotykamy.
    config.DRY_RUN = False
    config.ANTHROPIC_API_KEY = "atrapa"
    config.DEEPSEEK_API_KEY = "atrapa"
    llm._call_claude = falszywy_claude
    llm._call_deepseek_responses = falszywy_responses
    llm._call_deepseek = falszywy_deepseek
    # ZEGAR USTALONY na 15 wrzesnia: wynik testu nie moze zalezec od dnia,
    # w ktorym ktos go uruchamia.
    config.szuka_naprawde = lambda model, kiedy=None: _szuka_prawdziwe(
        model, T("2026-09-15T00:00:00+00:00"))
    conn = db.connect()

    llm.call("factcheck", "s", "u", conn=conn, run_id=None, web_search=True)
    llm.call("factcheck", "s", "u", conn=conn, run_id=None, web_search=False)
    llm.call("discovery", "s", "u", conn=conn, run_id=None, web_search=True)
    sprawdz("factcheck z siecia: Haiku przez sciezke Claude",
            wywolania[0] == ("claude", "factcheck", config.HAIKU, True), wywolania[0])
    sprawdz("factcheck bez sieci: zostaje na modelu etapu",
            wywolania[1] == ("deepseek", "factcheck", config.MODEL_FOR["factcheck"], False), wywolania[1])
    sprawdz("discovery od 14.09: Haiku, bo V4 Pro stracil wyszukiwanie",
            wywolania[2] == ("claude", "discovery", config.HAIKU, True), wywolania[2])

    wiersze = [dict(w) for w in conn.execute(
        "select model, provider, web_searches, cost_usd from calls order by id")]
    sprawdz("ksiega zapisuje model, ktory NAPRAWDE odpowiedzial",
            wiersze[0]["model"] == config.HAIKU and wiersze[0]["provider"] == "anthropic", wiersze[0])
    sprawdz("koszt Haiku z oplata za dwa wyszukiwania",
            abs(wiersze[0]["cost_usd"] - round(100 / 1e6 * 1.0 + 10 / 1e6 * 5.0 + 2 * 0.01, 6)) < 1e-9,
            wiersze[0])

    # KONTRDOWOD: stan sprzed naprawy — kazdy model uznany za szukajacy.
    wywolania.clear()
    config.szuka_naprawde = lambda model, kiedy=None: True
    llm.call("factcheck", "s", "u", conn=conn, run_id=None, web_search=True)
    sprawdz("KONTRDOWOD: bez rozpoznania zdolnosci fakty szlyby na V4.1 Flash przez /responses",
            wywolania[0] == ("deepseek-responses", "factcheck", config.DEEPSEEK, True), wywolania[0])
    conn.close()
finally:
    llm._call_claude = _oryg["claude"]
    llm._call_deepseek_responses = _oryg["responses"]
    llm._call_deepseek = _oryg["deepseek"]
    config.szuka_naprawde = _oryg["szuka"]
    config.WOLNO_WOLAC_MODEL = _oryg["wolno"]
    config.DRY_RUN = _oryg["sucho"]
    config.ANTHROPIC_API_KEY = _oryg["ka"]
    config.DEEPSEEK_API_KEY = _oryg["kd"]
    config.przywroc_katalog_danych(zdjecie)

print()
print("=== 4. STAWKI: przekierowania DeepSeeka, weekend, oplata za wyszukiwanie ===")
s = config.stawka_deepseek("deepseek-v4-pro", T("2026-09-14T05:00:00+00:00"))
sprawdz("V4 Pro od 14.09 rozliczany po stawce V4.1 Flash",
        (s["in"], s["out"], s["cache"]) == (0.15, 0.6, 0.003), s)
sprawdz("i nie udaje stawki potwierdzonej faktura", s["verified"] is False, s)
s = config.stawka_deepseek("deepseek-v4-pro", T("2026-09-13T12:00:00+00:00"))
sprawdz("V4 Pro 13.09 jeszcze po swojej stawce", (s["in"], s["out"]) == (0.66, 1.98), s)
s = config.stawka_deepseek("deepseek-v4-flash", T("2026-09-11T12:00:00+00:00"))
sprawdz("stara nazwa Flash po 10.09 po stawce V4.1", s["in"] == 0.15 and s["model"] == "deepseek-flash", s)
s = config.stawka_deepseek("deepseek-v4-flash", T("2026-09-09T12:00:00+00:00"))
sprawdz("stara nazwa Flash przed 10.09 po starej, potwierdzonej", s["in"] == 0.22 and s["verified"], s)
s = config.stawka_deepseek("deepseek-flash", T("2026-09-15T07:00:00+00:00"))
sprawdz("V4.1 Flash we wtorek o 07:00 to szczyt: dwa razy", s["in"] == 0.3 and s["szczyt"], s)
s = config.stawka_deepseek("deepseek-flash", T("2026-09-13T07:00:00+00:00"))
sprawdz("niedziela o 07:00 to NIE szczyt", s["in"] == 0.15 and not s["szczyt"], s)
sprawdz("KONTRDOWOD: stara regula (sama godzina) uznalaby niedziele 07:00 za szczyt",
        T("2026-09-13T07:00:00+00:00").hour in config.GODZINY_SZCZYTU_UTC)

usd, _ = llm._cost("claude-haiku-4-5-20251001", 1_000_000, 0, 10)
sprawdz("Haiku: milion tokenow wejscia plus dziesiec wyszukiwan", abs(usd - 1.10) < 1e-9, usd)
usd, _ = llm._cost("claude-fable-5-1", 0, 0, 100)
sprawdz("Fable: wyszukiwania juz nie ida do ksiegi za darmo", abs(usd - 1.0) < 1e-9, usd)
usd, potwierdzona = llm._cost("claude-opus-5-1", 1_000_000, 0, 0)
sprawdz("model spoza cennika: stawka rodziny zamiast KeyError",
        abs(usd - 5.0) < 1e-9 and potwierdzona is False, (usd, potwierdzona))
usd, potwierdzona = llm._cost("deepseek-pro", 1_000_000, 0, 0)
sprawdz("nowy DeepSeek spoza cennika: stawka rodziny Pro, niepotwierdzona",
        usd > 0 and potwierdzona is False, (usd, potwierdzona))

print()
print("wynik: %d OK, %d BLAD" % (zdane, oblane))
sys.exit(1 if oblane else 0)
