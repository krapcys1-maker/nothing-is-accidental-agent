# -*- coding: utf-8 -*-
"""Cena nowego modelu z cennika dostawcy — przy zamianie, bez zgadywania.

DLACZEGO TO POWSTALO (26 wrzesnia 2026). `nowe_modele` przeszedl 23.09 z Opusa 5
na Opus 5.5, a nowy model nie mial wpisu w cenniku — liczyl sie wiec jak Opus 5
(5/25 USD za milion tokenow), choc cennik Anthropic podaje 4/20. Drugi bot
wlasciciela w tym samym miejscu liczyl podwojna stawke poprzednika i konczyl
mu sie budzet przed koncem miesiaca. Wlasciciel: „napraw, zeby sprawdzalo, jakie
ma ceny model, jak zamienia, albo niech zamienia 1:1".

Wycinki stron nizej sa PRAWDZIWYMI fragmentami cennikow pobranych 26.09.2026
(`platform.claude.com/.../pricing.md` i `developers.openai.com/api/docs/pricing`),
skrocone do potrzebnych wierszy. Test NIE chodzi do sieci.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config            # noqa: E402
import cennik_dostawcy   # noqa: E402
import db                # noqa: E402
import nowe_modele       # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


ANTHROPIC_MD = """The following table shows pricing for all Claude models:

| Model                 | Base input tokens     | 5m cache writes | 1h cache writes | Cache hits and refreshes | Output tokens          |
| :-------------------- | :-------------------- | :-------------- | :-------------- | :----------------------- | :--------------------- |
| Claude Fable 5.1      | $10 / MTok            | $12.50 / MTok   | $20 / MTok      | $0.25 / MTok<sup>1</sup> | $50 / MTok             |
| Claude Opus 5.5       | $4 / MTok             | $5 / MTok       | $8 / MTok       | $0.20 / MTok<sup>2</sup> | $20 / MTok             |
| Claude Opus 5         | $5 / MTok             | $6.25 / MTok    | $10 / MTok      | $0.50 / MTok             | $25 / MTok             |
| Claude Sonnet 5       | $2 / MTok<sup>3</sup> | $2.50 / MTok    | $4 / MTok       | $0.20 / MTok             | $10 / MTok<sup>3</sup> |

The Batch API allows asynchronous processing with a 50% discount.

| Model                 | Batch input  | Batch output  |
| :-------------------- | :----------- | :------------ |
| Claude Opus 5.5       | $2 / MTok    | $10 / MTok    |
| Claude Haiku 6        | $0.50 / MTok | $2.50 / MTok  |
"""

OPENAI_HTML = """<div>Standard Batch Flex Fast mode Standard Short context Long context
<table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th>
<th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th></tr>
<tr><td>gpt-6-astra</td><td>$10.00</td><td>$1.00</td><td>$12.50</td><td>$50.00</td><td>$20.00</td><td>$2.00</td><td>$25.00</td><td>$75.00</td></tr>
<tr><td>gpt-6-sol</td><td>$2.00</td><td>$0.20</td><td>$2.50</td><td>$10.00</td><td>$4.00</td><td>$0.40</td><td>$5.00</td><td>$15.00</td></tr>
<tr><td>gpt-6-luna</td><td>$0.10</td><td>$0.01</td><td>$0.125</td><td>$0.50</td><td>$0.20</td><td>$0.02</td><td>$0.25</td><td>$0.75</td></tr>
</table>
Cyber models Our latest Daybreak models. Prices per 1M tokens. Short context Long context
<table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th>
<th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th></tr>
<tr><td>gpt-5.6-sol</td><td>$4.00</td><td>$0.40</td><td>$5.00</td><td>$20.00</td><td>$8.00</td><td>$0.80</td><td>$10.00</td><td>$30.00</td></tr>
</table>
All models Batch Short context Long context
<table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th></tr>
<tr><td>gpt-6-sol</td><td>$1.00</td><td>$0.10</td><td>$1.25</td><td>$5.00</td></tr>
</table></div>"""


print("=== 1. CENNIK ANTHROPIC: PIERWSZA TABELA, WLASCIWE KOLUMNY ===")
sprawdz("nazwa z identyfikatora", cennik_dostawcy.nazwa_anthropic("claude-opus-5-5")
        == "Claude Opus 5.5")
sprawdz("data na koncu nie zmienia nazwy",
        cennik_dostawcy.nazwa_anthropic("claude-opus-5-5-20260901") == "Claude Opus 5.5")
sprawdz("Opus 5.5: 4 / cache 0,20 / 20",
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-opus-5-5")
        == {"in": 4.0, "cache": 0.2, "out": 20.0},
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-opus-5-5"))
sprawdz("Opus 5: 5 / 0,50 / 25",
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-opus-5")
        == {"in": 5.0, "cache": 0.5, "out": 25.0})
sprawdz("przypis <sup> nie psuje liczby (Sonnet 5: 2 / 10)",
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-sonnet-5")
        == {"in": 2.0, "cache": 0.2, "out": 10.0})
sprawdz("KONTRDOWOD: model tylko w tabeli batch nie dostaje ceny batch",
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-haiku-6") is None)
sprawdz("model, ktorego nie ma, to brak ceny",
        cennik_dostawcy.z_cennika_anthropic(ANTHROPIC_MD, "claude-opus-9") is None)
_zmieniony = ANTHROPIC_MD.replace("| Base input tokens     | 5m cache writes",
                                  "| Output tokens     | 5m cache writes")
sprawdz("KONTRDOWOD: przestawione kolumny — parser odmawia zamiast pomylic",
        cennik_dostawcy.z_cennika_anthropic(_zmieniony, "claude-opus-5-5") is None)

print()
print("=== 2. CENNIK OPENAI: TRYB STANDARDOWY, KROTKI KONTEKST ===")
sprawdz("GPT-6 sol: 2 / 0,20 / 10 (nie batch 1/5, nie dlugi kontekst 4/15)",
        cennik_dostawcy.z_cennika_openai(OPENAI_HTML, "gpt-6-sol")
        == {"in": 2.0, "cache": 0.2, "out": 10.0},
        cennik_dostawcy.z_cennika_openai(OPENAI_HTML, "gpt-6-sol"))
sprawdz("GPT-5.6 sol: 4 / 0,40 / 20 (tabela Daybreak)",
        cennik_dostawcy.z_cennika_openai(OPENAI_HTML, "gpt-5.6-sol")
        == {"in": 4.0, "cache": 0.4, "out": 20.0})
sprawdz("KONTRDOWOD: „gpt-6-sol-pro” to nie „gpt-6-sol”",
        cennik_dostawcy.z_cennika_openai(OPENAI_HTML, "gpt-6-sol-pro") is None)
sprawdz("KONTRDOWOD: bez kolumny cache writes parser odmawia",
        cennik_dostawcy.z_cennika_openai(OPENAI_HTML.replace(
            "<th>Cache writes</th><th>Output</th>\n<th>Input</th>", "<th>Output</th>\n<th>Input</th>", 1),
            "gpt-6-astra") is None)

print()
print("=== 3. LICZBY MUSZA WYGLADAC NA CENNIK ===")
sprawdz("wejscie drozsze od wyjscia to nie cennik",
        not cennik_dostawcy.wiarygodna({"in": 20, "out": 4}))
sprawdz("cache drozszy od wejscia to nie cennik",
        not cennik_dostawcy.wiarygodna({"in": 4, "out": 20, "cache": 5}))
sprawdz("KONTRDOWOD: dwadziescia razy drozej od poprzednika — odrzucone",
        not cennik_dostawcy.wiarygodna({"in": 100, "out": 500}, {"in": 5, "out": 25}))
sprawdz("normalna cena przechodzi",
        cennik_dostawcy.wiarygodna({"in": 4, "out": 20, "cache": 0.2}, {"in": 5, "out": 25}))
sprawdz("podwyzka liczona po wejsciu i wyjsciu: 4/20 wobec 5/25 to -20%",
        abs(cennik_dostawcy.podwyzka({"in": 4, "out": 20}, {"in": 5, "out": 25}) + 0.2) < 1e-9)

print()
print("=== 4. POBRANIE: AWARIA TO „NIE WIEM”, NIE WYJATEK ===")
cena, zrodlo = cennik_dostawcy.stawka_u_dostawcy(
    "claude-opus-5-5", pobierz=lambda url: ANTHROPIC_MD)
sprawdz("z atrapa strony: cena i zrodlo",
        cena == {"in": 4.0, "cache": 0.2, "out": 20.0} and zrodlo.startswith("cennik anthropic"),
        (cena, zrodlo))


def _pada(url):
    raise TimeoutError("nie odpowiada")


cena, zrodlo = cennik_dostawcy.stawka_u_dostawcy("gpt-6-sol", pobierz=_pada)
sprawdz("siec padla: brak ceny z powodem, bez wyjatku",
        cena is None and "nie odpowiedzial" in zrodlo, zrodlo)
_wolane = []
for model in ("deepseek-flash", "gpt-image-2.5-sunburst"):
    cena, zrodlo = cennik_dostawcy.stawka_u_dostawcy(
        model, pobierz=lambda url: _wolane.append(url) or "")
    sprawdz("%s: cennika nie czytamy (liczy sie 1:1)" % model, cena is None, zrodlo)
sprawdz("  i nie idziemy po niego do sieci", _wolane == [], _wolane)
sprawdz("darmowy test nie idzie do sieci nawet bez atrapy",
        cennik_dostawcy.stawka_u_dostawcy("claude-opus-5-5")[0] is None)

print()
print("=== 5. CENNIK BOTA: OPUS 5.5 I SONNET 5 WEDLUG DOSTAWCY ===")
sprawdz("Opus 5.5 w cenniku: 4/20, cache 0,20",
        {k: config.PRICING["claude-opus-5-5"][k] for k in ("in", "out", "cache")}
        == {"in": 4.0, "out": 20.0, "cache": 0.2})
sprawdz("Sonnet 5: 2/10 (podwyzka do 3/15 odwolana)",
        (config.PRICING["claude-sonnet-5"]["in"], config.PRICING["claude-sonnet-5"]["out"]) == (2.0, 10.0))
sprawdz("nieznany Opus liczy sie 1:1 jak Opus 5 — nie podwojnie",
        (config.stawka_modelu("claude-opus-9")["in"], config.stawka_modelu("claude-opus-9")["out"])
        == (5.0, 25.0))
_stan = {"zamiany": {
    "CLAUDE": {"z": "claude-opus-5", "na": "claude-opus-5-6", "cena": {"in": 3, "out": 15, "cache": 0.3}},
    "SONNET": {"z": "claude-sonnet-5", "na": "claude-sonnet-5-1", "cena": {"in": 30, "out": 3}},
    "FABLE": {"z": "claude-fable-5-1", "na": "ZLA NAZWA", "cena": {"in": 1, "out": 2}},
}}
_ceny = config._ceny_zamian(_stan)
sprawdz("cena zapisana przy zamianie jest czytana", _ceny.get("claude-opus-5-6")
        == {"in": 3.0, "out": 15.0, "cache": 0.3, "verified": False}, _ceny)
sprawdz("KONTRDOWOD: odwrocone liczby i zla nazwa nie wchodza",
        set(_ceny) == {"claude-opus-5-6"}, sorted(_ceny))

print()
print("=== 6. ZAMIANA MODELU SPRAWDZA CENE PRZED PLATNA PROBA ===")
ANTHROPIC = {"claude-opus-5": "2026-07-24", "claude-opus-5-6": "2026-09-30",
             "claude-sonnet-5": "2026-06-29", "claude-sonnet-5-1": "2026-09-30",
             "claude-fable-5-1": "2026-08-28", "claude-fable-5-2": "2026-09-30"}
DEEPSEEK = {"deepseek-flash": "", "deepseek-v4-pro": ""}
STRONA = ANTHROPIC_MD + (
    "\n| Model | Base input tokens | 5m cache writes | 1h cache writes | Cache hits and refreshes | Output tokens |\n"
    "| :- | :- | :- | :- | :- | :- |\n"
    "| Claude Opus 5.6 | $3 / MTok | $3.75 / MTok | $6 / MTok | $0.30 / MTok | $15 / MTok |\n"
    "| Claude Sonnet 5.1 | $6 / MTok | $7.50 / MTok | $12 / MTok | $0.60 / MTok | $30 / MTok |\n")

_zapas = {"rolami": {r: getattr(config, r) for r in nowe_modele.ROLE},
          "model_for": dict(config.MODEL_FOR), "narzedzia": dict(config.WEB_SEARCH_TOOL),
          "szukanie": dict(config.MODEL_DO_SZUKANIA), "szukanie_dom": config.MODEL_DO_SZUKANIA_DOMYSLNY,
          "proby": dict(config.PROBY_WYSZUKIWANIA), "wolno": config.WOLNO_WOLAC_MODEL,
          "ka": config.ANTHROPIC_API_KEY, "kd": config.DEEPSEEK_API_KEY, "sucho": config.DRY_RUN,
          "lista": nowe_modele.lista_modeli, "odp": nowe_modele.proba_odpowiedzi,
          "szuk": nowe_modele.proba_wyszukiwania, "pobierz": cennik_dostawcy._pobierz,
          "ceny": dict(config.CENY_ZAMIAN)}
proby = []
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
try:
    config.ANTHROPIC_API_KEY = config.DEEPSEEK_API_KEY = "atrapa"
    config.WOLNO_WOLAC_MODEL, config.DRY_RUN = True, False
    nowe_modele.lista_modeli = lambda: {"anthropic": dict(ANTHROPIC), "deepseek": dict(DEEPSEEK)}
    nowe_modele.proba_odpowiedzi = lambda d, m: (proby.append(m) or (True, "odpowiada", 20, 5))
    nowe_modele.proba_wyszukiwania = lambda m: (True, 1, 60, 30, "szuka (1 wyszukiwan)")
    cennik_dostawcy._pobierz = lambda url: STRONA
    conn = db.connect()
    wynik = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    wykonane = {d["rola"]: d for d in wynik["wykonane"]}
    odrzucone = {d["rola"]: d for d in wynik["odrzucone"]}
    sprawdz("tanszy Opus 5.6 wchodzi", "CLAUDE" in wykonane and config.CLAUDE == "claude-opus-5-6",
            sorted(wykonane))
    sprawdz("  i liczy sie po cenie z cennika, nie jak Opus 5",
            (config.stawka_modelu("claude-opus-5-6")["in"], config.stawka_modelu("claude-opus-5-6")["out"])
            == (3.0, 15.0), config.stawka_modelu("claude-opus-5-6"))
    sprawdz("drozszy Sonnet 5.1 (6/30 wobec 2/10) NIE wchodzi sam",
            "SONNET" in odrzucone and "drozszy" in odrzucone["SONNET"]["dlaczego"]
            and config.SONNET == "claude-sonnet-5", odrzucone.get("SONNET"))
    sprawdz("  i nie placimy za jego probe", "claude-sonnet-5-1" not in proby, proby)
    sprawdz("Fable 5.2 bez ceny w cenniku wchodzi 1:1 jak poprzednik",
            "FABLE" in wykonane and wykonane["FABLE"]["cena_zrodlo"].startswith("jak poprzednik")
            and (config.stawka_modelu("claude-fable-5-2")["in"], config.stawka_modelu("claude-fable-5-2")["out"])
            == (10.0, 50.0), wykonane.get("FABLE"))
    stan = json.loads(config.plik_wyboru_modeli().read_text(encoding="utf-8"))
    sprawdz("cena zapisana w stanie zamian", stan["zamiany"]["CLAUDE"].get("cena")
            == {"in": 3.0, "cache": 0.3, "out": 15.0}, stan["zamiany"]["CLAUDE"])
    sprawdz("nowy proces odczyta ja z pliku",
            config._ceny_zamian(stan).get("claude-opus-5-6", {}).get("out") == 15.0)

    # UZUPELNIENIE: zamiana sprzed tej zmiany, bez ceny, dostaje ja przy
    # nastepnym sprawdzeniu — darmowym GET, bez ponownej proby modelu.
    stan["zamiany"]["CLAUDE"].pop("cena")
    config.plik_wyboru_modeli().write_text(json.dumps(stan), encoding="utf-8")
    config.CENY_ZAMIAN.pop("claude-opus-5-6", None)
    proby.clear()
    wynik2 = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    stan2 = json.loads(config.plik_wyboru_modeli().read_text(encoding="utf-8"))
    sprawdz("zamiana bez ceny dostaje ja z cennika",
            stan2["zamiany"]["CLAUDE"].get("cena", {}).get("out") == 15.0, stan2["zamiany"]["CLAUDE"])
    sprawdz("  i dziala od razu w tym procesie",
            config.stawka_modelu("claude-opus-5-6")["out"] == 15.0)
    conn.close()
finally:
    nowe_modele.lista_modeli = _zapas["lista"]
    nowe_modele.proba_odpowiedzi = _zapas["odp"]
    nowe_modele.proba_wyszukiwania = _zapas["szuk"]
    cennik_dostawcy._pobierz = _zapas["pobierz"]
    config.WOLNO_WOLAC_MODEL, config.DRY_RUN = _zapas["wolno"], _zapas["sucho"]
    config.ANTHROPIC_API_KEY, config.DEEPSEEK_API_KEY = _zapas["ka"], _zapas["kd"]
    for rola, model in _zapas["rolami"].items():
        setattr(config, rola, model)
    config.MODEL_FOR.clear()
    config.MODEL_FOR.update(_zapas["model_for"])
    config.WEB_SEARCH_TOOL.clear()
    config.WEB_SEARCH_TOOL.update(_zapas["narzedzia"])
    config.MODEL_DO_SZUKANIA.clear()
    config.MODEL_DO_SZUKANIA.update(_zapas["szukanie"])
    config.MODEL_DO_SZUKANIA_DOMYSLNY = _zapas["szukanie_dom"]
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_zapas["proby"])
    config.CENY_ZAMIAN.clear()
    config.CENY_ZAMIAN.update(_zapas["ceny"])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
