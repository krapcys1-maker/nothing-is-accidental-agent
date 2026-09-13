"""Wywolanie z siecia idzie do modelu DeepSeeka, ktory NAPRAWDE szuka — i kosztuje tyle, ile kosztuje.

DLACZEGO TO POWSTALO. 10 wrzesnia 2026 DeepSeek przestawil `deepseek-v4-flash`
na V4.1 Flash, a ten przez `/responses` nie ma narzedzia wyszukiwania. Zmierzone
13 wrzesnia z tabeli `calls`, przed i po 10.09 04:00 UTC:

    factcheck        170 z 238 wywolan szukalo  ->  0 z 38
    curiosity         15 z 44                   ->  0 z 5
    aktualne_modele    6 z 6                    ->  0 z 5

Wywolania konczyly sie sukcesem, tylko dziesiec razy taniej — wiec weryfikacja
faktow przed publikacja (`stages.zweryfikuj`: notki, komentarze, artykuly) przez
trzy dni sprawdzala tekst pamiecia modelu, a nie siecia.

PODZIAL PO NAPRAWIE: V4.1 Flash robi wszystko, co nie wymaga sieci; wywolania
z siecia ida na DeepSeek V4 Pro, ktory szuka. Tylko DeepSeek — przez jedno
popoludnie zastepca byl Claude Haiku, a wlasciciel: „my nie uzywamy zadnego
haiku". Sekcja 5 pilnuje, zeby nie wrocil.
"""
import contextlib
import io
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

print("=== 1. KTO SZUKA — pomiary z 13 wrzesnia 2026 ===")
sprawdz("V4.1 Flash nie szuka", not config.szuka_naprawde("deepseek-flash", T("2026-09-13T12:00:00+00:00")))
sprawdz("stara nazwa Flash po 10.09 tez nie",
        not config.szuka_naprawde("deepseek-v4-flash", T("2026-09-11T12:00:00+00:00")))
sprawdz("stara nazwa Flash SZUKALA przed 10.09",
        config.szuka_naprawde("deepseek-v4-flash", T("2026-09-09T12:00:00+00:00")))
sprawdz("V4 Pro szuka 13.09",
        config.szuka_naprawde("deepseek-v4-pro", T("2026-09-13T12:00:00+00:00")))
sprawdz("V4 Pro szuka takze po 14.09 — DeepSeek zostawil model",
        config.szuka_naprawde("deepseek-v4-pro", T("2026-09-15T12:00:00+00:00")))
sprawdz("nieznany DeepSeek nie szuka, dopoki proba nie potwierdzi",
        not config.szuka_naprawde("deepseek-pro", T("2026-09-20T12:00:00+00:00")))
sprawdz("zastepca dla weryfikacji faktow to DeepSeek V4 Pro",
        config.model_do_szukania("factcheck") == config.DEEPSEEK_PRO)
sprawdz("V4.1 Flash zostaje modelem etapu weryfikacji", config.MODEL_FOR["factcheck"] == config.DEEPSEEK)

print()
print("=== 2. PROBA Z nowe_modele MA PIERWSZENSTWO — ale tylko pozniejsza niz awaria ===")
_proby = dict(config.PROBY_WYSZUKIWANIA)
try:
    config.PROBY_WYSZUKIWANIA["deepseek-flash"] = {"dziala": True, "kiedy": "2026-09-20T12:00:00+00:00"}
    sprawdz("swieza udana proba przywraca szukanie",
            config.szuka_naprawde("deepseek-flash", T("2026-09-21T00:00:00+00:00")))
    sprawdz("ale nie wstecz: przed proba dalej nie szuka",
            not config.szuka_naprawde("deepseek-flash", T("2026-09-19T00:00:00+00:00")))
    config.PROBY_WYSZUKIWANIA["deepseek-v4-flash"] = {"dziala": True, "kiedy": "2026-09-09T12:00:00+00:00"}
    sprawdz("proba sprzed daty awarii nie przykrywa awarii",
            not config.szuka_naprawde("deepseek-v4-flash", T("2026-09-11T00:00:00+00:00")))
    # CICHA UTRATA NA MODELU, KTORY SZUKAL — dokladnie przypadek z 10 wrzesnia.
    config.PROBY_WYSZUKIWANIA["deepseek-v4-pro"] = {"dziala": False, "kiedy": "2026-09-20T12:00:00+00:00"}
    sprawdz("proba mowiaca, ze Pro przestal szukac, zdejmuje go z wyszukiwania",
            not config.szuka_naprawde("deepseek-v4-pro", T("2026-09-21T00:00:00+00:00")))
finally:
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_proby)

print()
print("=== 3. llm.call: z siecia do V4 Pro, bez sieci zostaje na V4.1 Flash ===")
wywolania = []


def falszywy_claude(purpose, system, user, web_search, model=None):
    wywolania.append(("claude", purpose, model, web_search))
    return '{"facts": []}', 100, 10, 2, ["https://example.org/a"]


def falszywy_responses(purpose, system, user, model=None):
    wywolania.append(("deepseek-responses", purpose, model, True))
    return '{"facts": []}', 100, 10, 3, ["https://example.org/b"]


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
    sprawdz("weryfikacja z siecia: DeepSeek V4 Pro przez /responses",
            wywolania[0] == ("deepseek-responses", "factcheck", config.DEEPSEEK_PRO, True), wywolania[0])
    sprawdz("weryfikacja bez sieci: V4.1 Flash",
            wywolania[1] == ("deepseek", "factcheck", config.DEEPSEEK, False), wywolania[1])
    sprawdz("odkrywanie zrodel: zostaje na V4 Pro, ktory szuka",
            wywolania[2] == ("deepseek-responses", "discovery", config.DEEPSEEK_PRO, True), wywolania[2])
    sprawdz("zadne wywolanie nie poszlo do Claude", not any(w[0] == "claude" for w in wywolania), wywolania)

    wiersz = dict(conn.execute("select model, provider, web_searches, cost_usd from calls order by id limit 1").fetchone())
    sprawdz("ksiega zapisuje model, ktory NAPRAWDE odpowiedzial",
            wiersz["model"] == config.DEEPSEEK_PRO and wiersz["provider"] == "deepseek", wiersz)
    sprawdz("wyszukiwania DeepSeeka bez doplaty za sztuke — mieszcza sie w tokenach",
            abs(wiersz["cost_usd"] - llm._cost(config.DEEPSEEK_PRO, 100, 10, 0)[0]) < 1e-9, wiersz)

    # V4 Pro traci narzedzie wedlug proby: nie ma zastepcy spoza DeepSeeka —
    # wywolanie idzie jak dotad, ale GLOSNO.
    wywolania.clear()
    llm._SZUKANIE_PRZEKIEROWANE.discard("curiosity")
    _proby3 = dict(config.PROBY_WYSZUKIWANIA)
    config.PROBY_WYSZUKIWANIA["deepseek-v4-pro"] = {"dziala": False, "kiedy": "2026-09-14T00:00:00+00:00"}
    wydruk = io.StringIO()
    with contextlib.redirect_stdout(wydruk):
        llm.call("curiosity", "s", "u", conn=conn, run_id=None, web_search=True)
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_proby3)
    sprawdz("gdy nikt nie szuka: wywolanie zostaje na modelu etapu, bez przeskoku do Claude",
            wywolania[0] == ("deepseek-responses", "curiosity", config.MODEL_FOR["curiosity"], True), wywolania[0])
    sprawdz("i mowi o tym glosno", "UWAGA curiosity" in wydruk.getvalue(), wydruk.getvalue())

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
s = config.stawka_deepseek("deepseek-v4-pro", T("2026-09-14T11:00:00+00:00"))
sprawdz("V4 Pro po 14.09 dalej po swojej stawce — DeepSeek zostawil model i rozliczenie",
        (s["in"], s["out"], s["cache"]) == (0.66, 1.98, 0.022) and s["verified"], s)
# KONTRDOWOD: pierwsza wersja naprawy miala wpis przekierowania Pro na Flash
# od 14.09 04:00 UTC. Z tym wpisem ta sama stawka spada ponad cztery razy.
_przek = config.PRZEKIEROWANIA_DEEPSEEK
try:
    config.PRZEKIEROWANIA_DEEPSEEK = _przek + (
        ("deepseek-v4-pro", "2026-09-14T04:00:00+00:00", "deepseek-flash"),)
    zla = config.stawka_deepseek("deepseek-v4-pro", T("2026-09-14T11:00:00+00:00"))
    sprawdz("KONTRDOWOD: z wpisem z pierwszej wersji Pro liczylby sie po 0,15 — test to lapie",
            zla["in"] == 0.15, zla)
finally:
    config.PRZEKIEROWANIA_DEEPSEEK = _przek
s = config.stawka_deepseek("deepseek-v4-pro", T("2026-09-13T12:00:00+00:00"))
sprawdz("V4 Pro 13.09 po swojej stawce", (s["in"], s["out"]) == (0.66, 1.98), s)
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

usd, _ = llm._cost("claude-fable-5-1", 0, 0, 100)
sprawdz("Fable: wyszukiwania juz nie ida do ksiegi za darmo", abs(usd - 1.0) < 1e-9, usd)
usd, potwierdzona = llm._cost("claude-opus-5-1", 1_000_000, 0, 0)
sprawdz("model spoza cennika: stawka rodziny zamiast KeyError",
        abs(usd - 5.0) < 1e-9 and potwierdzona is False, (usd, potwierdzona))
usd, potwierdzona = llm._cost("deepseek-pro", 1_000_000, 0, 0)
sprawdz("nowy DeepSeek spoza cennika: stawka rodziny Pro, niepotwierdzona",
        usd > 0 and potwierdzona is False, (usd, potwierdzona))

print()
print("=== 5. HAIKU NIE WRACA — decyzja wlasciciela ===")
import nowe_modele  # noqa: E402

wszystkie = set(config.MODEL_FOR.values()) | {config.model_do_szukania(e) for e in config.MODEL_FOR}
sprawdz("zaden etap ani zastepca nie wskazuje Haiku", not any("haiku" in m for m in wszystkie), sorted(wszystkie))
sprawdz("brak roli HAIKU w konfiguracji", "HAIKU" not in config.ROLE_MODELI and not hasattr(config, "HAIKU"))
sprawdz("automatyczna zamiana nie ma rodziny haiku",
        all(rodzina != "haiku" for _, rodzina in nowe_modele.ROLE.values()))
_llm_src = pathlib.Path("agent-v2/llm.py").read_text(encoding="utf-8")
sprawdz("brak wymuszania narzedzia pisanego pod Haiku", "wymus_szukanie" not in _llm_src)
# KONTRDOWOD: przyrzad sekcji widzi Haiku, gdy ktos go podstawi.
_zast = config.MODEL_DO_SZUKANIA_DOMYSLNY
try:
    config.MODEL_DO_SZUKANIA_DOMYSLNY = "claude-haiku-4-5-20251001"
    wszystkie = {config.model_do_szukania(e) for e in config.MODEL_FOR}
    sprawdz("KONTRDOWOD: podstawiony Haiku jako zastepca — przyrzad go widzi",
            any("haiku" in m for m in wszystkie))
finally:
    config.MODEL_DO_SZUKANIA_DOMYSLNY = _zast

print()
print("wynik: %d OK, %d BLAD" % (zdane, oblane))
sys.exit(1 if oblane else 0)
