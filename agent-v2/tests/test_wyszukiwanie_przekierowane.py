"""Wywolania z siecia ida droga, na ktorej DeepSeek NAPRAWDE szuka — i kosztuja tyle, ile kosztuja.

DLACZEGO TO POWSTALO. 10 wrzesnia 2026 DeepSeek przestawil `deepseek-v4-flash`
na V4.1 Flash, a ten przez `/responses` nie ma narzedzia wyszukiwania. Zmierzone
13 wrzesnia z tabeli `calls`, przed i po 10.09 04:00 UTC:

    factcheck        170 z 238 wywolan szukalo  ->  0 z 38
    curiosity         15 z 44                   ->  0 z 5
    aktualne_modele    6 z 6                    ->  0 z 5

Weryfikacja faktow przed publikacja przez trzy dni sprawdzala tekst pamiecia modelu.

TEN SAM V4.1 FLASH PRZEZ ENDPOINT DEEPSEEKA ZGODNY Z API ANTHROPIC SZUKA —
wywolania z siecia ida wiec teraz tamtedy, a V4.1 Flash robi je sam. Przez jedno
popoludnie zastepca byl Claude Haiku; wlasciciel: „my nie uzywamy zadnego haiku".
Sekcja 5 pilnuje, zeby nie wrocil.
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

print("=== 1. KTO SZUKA — nowa droga, pomiary z 13 wrzesnia 2026 ===")
sprawdz("V4.1 Flash szuka", config.szuka_naprawde("deepseek-flash", T("2026-09-13T20:00:00+00:00")))
sprawdz("V4 Pro szuka", config.szuka_naprawde("deepseek-v4-pro", T("2026-09-15T12:00:00+00:00")))
sprawdz("nieznany DeepSeek nie szuka, dopoki proba nie potwierdzi",
        not config.szuka_naprawde("deepseek-pro", T("2026-09-20T12:00:00+00:00")))
sprawdz("Claude szuka", config.szuka_naprawde(config.CLAUDE))
sprawdz("weryfikacja faktow chodzi na V4.1 Flash", config.MODEL_FOR["factcheck"] == config.DEEPSEEK)
sprawdz("zapasowy zastepca to V4 Pro", config.model_do_szukania("factcheck") == config.DEEPSEEK_PRO)

print()
print("=== 2. PROBA Z nowe_modele MA PIERWSZENSTWO ===")
_proby = dict(config.PROBY_WYSZUKIWANIA)
_padlo = dict(config.SZUKANIE_PADLO_OD)
try:
    config.PROBY_WYSZUKIWANIA["deepseek-flash"] = {"dziala": False, "kiedy": "2026-09-20T12:00:00+00:00"}
    sprawdz("proba mowiaca, ze Flash przestal szukac, zdejmuje go z wyszukiwania",
            not config.szuka_naprawde("deepseek-flash", T("2026-09-21T00:00:00+00:00")))
    sprawdz("ale nie wstecz: przed proba dalej szuka",
            config.szuka_naprawde("deepseek-flash", T("2026-09-19T00:00:00+00:00")))
    # Mechanizm daty awarii zostaje na nastepny raz — sprawdzamy, ze dziala.
    config.SZUKANIE_PADLO_OD["deepseek-v4-pro"] = "2026-09-25T00:00:00+00:00"
    config.PROBY_WYSZUKIWANIA["deepseek-v4-pro"] = {"dziala": True, "kiedy": "2026-09-24T12:00:00+00:00"}
    sprawdz("proba sprzed daty awarii nie przykrywa awarii",
            not config.szuka_naprawde("deepseek-v4-pro", T("2026-09-26T00:00:00+00:00")))
finally:
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_proby)
    config.SZUKANIE_PADLO_OD.clear()
    config.SZUKANIE_PADLO_OD.update(_padlo)

print()
print("=== 3. llm.call: z siecia przez endpoint zgodny z Anthropic, bez sieci zwykla droga ===")
wywolania = []


def falszywy_claude(purpose, system, user, web_search, model=None):
    wywolania.append(("claude", purpose, model, web_search))
    return '{"facts": []}', 100, 10, 2, ["https://example.org/a"]


def falszywy_responses(purpose, system, user, model=None):
    wywolania.append(("deepseek-responses", purpose, model, True))
    return '{"facts": []}', 100, 10, 0, []


def falszywy_z_siecia(purpose, system, user, model=None):
    wywolania.append(("deepseek-z-siecia", purpose, model, True))
    return '{"facts": []}', 100, 10, 2, ["https://example.org/b"], 50


def falszywy_deepseek(purpose, system, user):
    wywolania.append(("deepseek", purpose, config.MODEL_FOR[purpose], False))
    return '{"facts": []}', 100, 10, 0, 0


_oryg = {"claude": llm._call_claude, "responses": llm._call_deepseek_responses,
         "z_siecia": llm._call_deepseek_z_siecia, "deepseek": llm._call_deepseek,
         "wolno": config.WOLNO_WOLAC_MODEL, "ka": config.ANTHROPIC_API_KEY,
         "kd": config.DEEPSEEK_API_KEY, "sucho": config.DRY_RUN}
zdjecie = config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
try:
    config.WOLNO_WOLAC_MODEL = True
    # `DRY_RUN` konczy `call` PRZED wyborem drogi, wiec z nim ten test nie
    # widzialby, dokad wywolanie naprawde idzie. Drogi sa atrapami.
    config.DRY_RUN = False
    config.ANTHROPIC_API_KEY = "atrapa"
    config.DEEPSEEK_API_KEY = "atrapa"
    llm._call_claude = falszywy_claude
    llm._call_deepseek_responses = falszywy_responses
    llm._call_deepseek_z_siecia = falszywy_z_siecia
    llm._call_deepseek = falszywy_deepseek
    conn = db.connect()

    llm.call("factcheck", "s", "u", conn=conn, run_id=None, web_search=True)
    llm.call("factcheck", "s", "u", conn=conn, run_id=None, web_search=False)
    llm.call("discovery", "s", "u", conn=conn, run_id=None, web_search=True)
    sprawdz("weryfikacja z siecia: V4.1 Flash sam, nowa droga",
            wywolania[0] == ("deepseek-z-siecia", "factcheck", config.DEEPSEEK, True), wywolania[0])
    sprawdz("weryfikacja bez sieci: V4.1 Flash zwykla droga",
            wywolania[1] == ("deepseek", "factcheck", config.DEEPSEEK, False), wywolania[1])
    sprawdz("odkrywanie zrodel: model etapu, nowa droga",
            wywolania[2] == ("deepseek-z-siecia", "discovery", config.MODEL_FOR["discovery"], True), wywolania[2])
    sprawdz("nic nie idzie przez /responses ani do Claude",
            not any(w[0] in ("deepseek-responses", "claude") for w in wywolania), wywolania)

    wiersz = dict(conn.execute(
        "select model, provider, web_searches, cache_hit, cost_usd from calls order by id limit 1").fetchone())
    sprawdz("ksiega: model, dostawca, wyszukiwania i trafienia w cache z odpowiedzi",
            (wiersz["model"], wiersz["provider"], wiersz["web_searches"], wiersz["cache_hit"])
            == (config.DEEPSEEK, "deepseek", 2, 50), wiersz)
    sprawdz("koszt po stawce DeepSeeka, bez doplaty za sztuke wyszukiwania",
            abs(wiersz["cost_usd"] - llm._cost(config.DEEPSEEK, 100, 10, 0, 50)[0]) < 1e-9, wiersz)

    # Flash traci narzedzie wedlug proby: wywolania z siecia ida do V4 Pro.
    wywolania.clear()
    _proby3 = dict(config.PROBY_WYSZUKIWANIA)
    config.PROBY_WYSZUKIWANIA["deepseek-flash"] = {"dziala": False, "kiedy": "2026-09-01T00:00:00+00:00"}
    llm.call("curiosity", "s", "u", conn=conn, run_id=None, web_search=True)
    sprawdz("Flash bez narzedzia: wywolanie z siecia idzie do V4 Pro",
            wywolania[0] == ("deepseek-z-siecia", "curiosity", config.DEEPSEEK_PRO, True), wywolania[0])

    # Zaden nie szuka: bez przeskoku do innego dostawcy, ale GLOSNO.
    wywolania.clear()
    llm._SZUKANIE_PRZEKIEROWANE.discard("aktualne_modele")
    config.PROBY_WYSZUKIWANIA["deepseek-v4-pro"] = {"dziala": False, "kiedy": "2026-09-01T00:00:00+00:00"}
    wydruk = io.StringIO()
    with contextlib.redirect_stdout(wydruk):
        llm.call("aktualne_modele", "s", "u", conn=conn, run_id=None, web_search=True)
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_proby3)
    sprawdz("gdy nikt nie szuka: zostaje na modelu etapu, bez przeskoku do Claude",
            wywolania[0] == ("deepseek-z-siecia", "aktualne_modele", config.MODEL_FOR["aktualne_modele"], True),
            wywolania[0])
    sprawdz("i mowi o tym glosno", "UWAGA aktualne_modele" in wydruk.getvalue(), wydruk.getvalue())
    conn.close()
finally:
    llm._call_claude = _oryg["claude"]
    llm._call_deepseek_responses = _oryg["responses"]
    llm._call_deepseek_z_siecia = _oryg["z_siecia"]
    llm._call_deepseek = _oryg["deepseek"]
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

print()
print("=== 5. HAIKU NIE WRACA — decyzja wlasciciela ===")
import nowe_modele  # noqa: E402

wszystkie = set(config.MODEL_FOR.values()) | {config.model_do_szukania(e) for e in config.MODEL_FOR}
sprawdz("zaden etap ani zastepca nie wskazuje Haiku", not any("haiku" in m for m in wszystkie), sorted(wszystkie))
sprawdz("brak roli HAIKU w konfiguracji", "HAIKU" not in config.ROLE_MODELI and not hasattr(config, "HAIKU"))
sprawdz("automatyczna zamiana nie ma rodziny haiku",
        all(rodzina != "haiku" for _, rodzina in nowe_modele.ROLE.values()))
_zast = config.MODEL_DO_SZUKANIA_DOMYSLNY
try:
    config.MODEL_DO_SZUKANIA_DOMYSLNY = "claude-haiku-4-5-20251001"
    sprawdz("KONTRDOWOD: podstawiony Haiku jako zastepca — przyrzad go widzi",
            any("haiku" in config.model_do_szukania(e) for e in config.MODEL_FOR))
finally:
    config.MODEL_DO_SZUKANIA_DOMYSLNY = _zast

print()
print("=== 6. NOWA DROGA: co idzie do DeepSeeka i jak czytamy odpowiedz ===")
wyslane = {}


class _Odpowiedz:
    def __init__(self, dane):
        self._dane = dane
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._dane


ODPOWIEDZ_Z_SIECIA = {
    "stop_reason": "end_turn",
    "content": [
        {"type": "thinking", "thinking": "..."},
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "x"}},
        {"type": "web_search_tool_result", "content": [
            {"type": "web_search_result", "url": "https://api-docs.deepseek.com/news/news260910/"},
            {"type": "web_search_result", "url": "https://example.org/b"}]},
        {"type": "text", "text": '{"claims": []}'},
    ],
    "usage": {"input_tokens": 12776, "output_tokens": 2621, "cache_read_input_tokens": 2944,
              "server_tool_use": {"web_search_requests": 2}},
}
_post = llm.httpx.post
_kd = config.DEEPSEEK_API_KEY
try:
    config.DEEPSEEK_API_KEY = "atrapa"

    def _falszywy_post(url, **kwargs):
        wyslane["url"], wyslane["kw"] = url, kwargs
        return _Odpowiedz(wyslane.get("oddaj", ODPOWIEDZ_Z_SIECIA))

    llm.httpx.post = _falszywy_post
    tekst, tin, tout, szukan, adresy, cache = llm._call_deepseek_z_siecia("factcheck", "s", "u")
    cialo = wyslane["kw"]["json"]
    sprawdz("adres: endpoint zgodny z API Anthropic",
            wyslane["url"] == "https://api.deepseek.com/anthropic/v1/messages", wyslane["url"])
    sprawdz("naglowek klucza w stylu Anthropic", "x-api-key" in wyslane["kw"]["headers"])
    sprawdz("model etapu i narzedzie web_search_20250305 z limitem etapu",
            cialo["model"] == config.DEEPSEEK
            and cialo["tools"][0]["type"] == "web_search_20250305"
            and cialo["tools"][0]["max_uses"] == config.max_szukan("factcheck"), cialo)
    sprawdz("tekst tylko z blokow text", tekst == '{"claims": []}', tekst)
    sprawdz("wyszukiwania z usage serwera, nie z tekstu", szukan == 2, szukan)
    sprawdz("adresy z wynikow wyszukiwarki", adresy == ["https://api-docs.deepseek.com/news/news260910/",
                                                        "https://example.org/b"], adresy)
    sprawdz("tokeny i trafienia w cache", (tin, tout, cache) == (12776, 2621, 2944), (tin, tout, cache))

    # KONTRDOWOD: odpowiedz, w ktorej model tylko PISZE o szukaniu — zero wyszukiwan.
    wyslane["oddaj"] = {"stop_reason": "end_turn",
                        "content": [{"type": "text", "text": "<search_web><query>x</query></search_web>"}],
                        "usage": {"input_tokens": 86, "output_tokens": 124}}
    _, _, _, szukan, adresy, _ = llm._call_deepseek_z_siecia("factcheck", "s", "u")
    sprawdz("KONTRDOWOD: udawane znaczniki w tekscie to zero wyszukiwan i zero adresow",
            szukan == 0 and adresy == [], (szukan, adresy))

    wyslane["oddaj"] = {"stop_reason": "max_tokens", "content": [], "usage": {}}
    try:
        llm._call_deepseek_z_siecia("factcheck", "s", "u")
        sprawdz("uciecie na suficie podnosi Truncated", False)
    except llm.Truncated:
        sprawdz("uciecie na suficie podnosi Truncated", True)
finally:
    llm.httpx.post = _post
    config.DEEPSEEK_API_KEY = _kd

print()
print("wynik: %d OK, %d BLAD" % (zdane, oblane))
sys.exit(1 if oblane else 0)
