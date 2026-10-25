# -*- coding: utf-8 -*-
"""Sledztwo, trzy przeslania i zdrowie zrodel (27.09.2026).

PO CO. Wlasciciel: „jak wybierze ciekawy temat, rozlozy go na rozne rzeczy, jesli
warto przeprowadzi sledztwo (...) hipotezy tez mozemy swoje stawiac (...) 3 ciekawe
notki na ten sam temat, ale z roznym przeslaniem" i „sprawdzaj, czy zrodla sie nie
wywalily".

Test pilnuje, kazde z kontrdowodem:
  1. historie z radaru: najlepszy naglowek na poczatku, warianty za nim;
  2. bramka: za malo serwisow — nie; historia juz badana — nie; YouTube i hosty
     zablokowane nie licza sie jako zrodla;
  3. nowosc: ustalenie na DWOCH adresach tak, na jednym — to streszczenie;
  4. przeslania: kod odrzuca motyw bez „przeciw", scenariusz bez „co obali",
     przeslanie bez twierdzen karty i powtorzony rodzaj;
  5. kolejka: od 25.10 kuriozum pierwsze, do trzech katow na dobe, wydane nie wraca,
     stare wygasa (seria sledcza: 4-5 katow jednej historii, `sledztwo.RODZAJE`);
  6. limity tygodnia i droga do dziennika; zdrowie zrodel.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import korpus_kanalow as kk     # noqa: E402
import llm                      # noqa: E402
import radar                    # noqa: E402
import sledztwo                 # noqa: E402
import stages                   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


TERAZ = datetime.now(timezone.utc)
_prawdziwy_call = llm.call


def w(kanal, url, temat, radar_=None):
    return {"kanal": kanal, "url": url, "temat": temat, "data": TERAZ.strftime("%Y-%m-%d"),
            "styk": "branza", **({"radar": radar_} if radar_ else {})}


print("=== 1. HISTORIE Z RADARU ===")
ULOZONE = [
    w("BBC Tech", "https://www.bbc.co.uk/a", "Rogue OpenAI agent infiltrated a government site",
      {"miejsce": 1, "hak": "An agent broke in", "glebia": "timeline"}),
    w("The Verge AI", "https://www.theverge.com/b", "OpenAI pauses training",
      {"miejsce": 2, "hak": "Training paused", "glebia": "why"}),
    w("NPR Tech", "https://www.npr.org/c", "OpenAI agents probed federal websites",
      {"miejsce": 1, "wariant": True}),
    w("Wes Roth", "https://www.youtube.com/watch?v=1", "OpenAI did WHAT", {"miejsce": 1, "wariant": True}),
    w("Pew", "https://pew.example/x", "Survey", None),
]
_uporzadkuj = radar.uporzadkuj
radar.uporzadkuj = lambda korpus, conn=None, run_id=None: list(ULOZONE)
try:
    hs = sledztwo.historie([], conn=None)
finally:
    radar.uporzadkuj = _uporzadkuj
sprawdz("dwie historie w kolejnosci radaru", [h["miejsce"] for h in hs] == [1, 2], [h["miejsce"] for h in hs])
sprawdz("najlepszy naglowek na poczatku, tytul historii z niego",
        hs[0]["tytul"].startswith("Rogue OpenAI") and hs[0]["hak"] == "An agent broke in")
sprawdz("warianty w historii", len(hs[0]["naglowki"]) == 3, len(hs[0]["naglowki"]))
sprawdz("KONTRDOWOD: wpis bez radaru nie tworzy historii", all(h["miejsce"] in (1, 2) for h in hs))
# 25.10.2026: bramka byla tylko dla piatki radaru, a duza historia bywa szosta.
_siedem = [w("BBC Tech", "https://www.bbc.co.uk/%d" % m, "Story %d" % m, {"miejsce": m, "hak": "", "glebia": ""})
           for m in range(1, 8)]
radar.uporzadkuj = lambda korpus, conn=None, run_id=None: list(_siedem)
try:
    _hs7 = sledztwo.historie([], conn=None)
finally:
    radar.uporzadkuj = _uporzadkuj
sprawdz("bramka widzi wszystkie historie radaru, nie piec", [h["miejsce"] for h in _hs7] == list(range(1, 8)),
        [h["miejsce"] for h in _hs7])

print()
print("=== 2. BRAMKA ===")
zr = sledztwo.zrodla_historii(hs[0])
sprawdz("YouTube nie jest zrodlem sledztwa", all("youtube" not in z["url"] for z in zr), zr)
ok, powod = sledztwo.ocena_historii(hs[0])
sprawdz("dwa serwisy to za malo", not ok and "2 niezaleznych" in powod, powod)
DUZA = {"miejsce": 1, "tytul": "Duza historia", "hak": "", "glebia": "", "naglowki": [
    w(k, "https://%s/%d" % (h, i), "Story %d" % i) for i, (k, h) in enumerate(
        (("BBC", "www.bbc.co.uk"), ("NPR", "www.npr.org"), ("ABC", "www.abc.net.au"),
         ("Wired", "www.wired.com"), ("Ars", "arstechnica.com"),
         ("Blok", "www.federalregister.gov"), ("BBC", "www.bbc.co.uk")))]}
ok, powod = sledztwo.ocena_historii(DUZA)
sprawdz("piec serwisow — warto badac", ok, powod)
sprawdz("host zablokowany (federalregister) nie jest zrodlem",
        all("federalregister" not in z["url"] for z in sledztwo.zrodla_historii(DUZA)))
sledztwo.zapisz_sledztwo({"historia": "stara", "zrodla": [sledztwo._klucz("https://www.bbc.co.uk/0"),
                                                          sledztwo._klucz("https://www.npr.org/1")]})
ok, powod = sledztwo.ocena_historii(DUZA)
sprawdz("KONTRDOWOD: historia juz badana (2 wspolne zrodla) — nie", not ok and "badana" in powod, powod)
(config.DATA_DIR / sledztwo.PLIK_SLEDZTW).unlink()

print()
print("=== 3. NOWOSC ===")
KARTA = {"working_thesis": "An agent broke in; the company told the government weeks later.",
         "main_mechanism": "retrospective detection",
         "confirmed_claims": [
             {"claim": "Breach on 18 June", "evidence": "June 18: breached", "url": "https://www.abc.net.au/t"},
             {"claim": "Company aware on 11 August", "evidence": "August 11: aware", "url": "https://www.abc.net.au/t"},
             {"claim": "Framework published 16 September favours disclosure",
              "evidence": "favors disclosure", "url": "https://www.transformernews.ai/p"},
             {"claim": "No mention of Australia on 16 September", "evidence": "no mention",
              "url": "https://www.transformernews.ai/p"}]}
ODP = {}
llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])
try:
    ODP["nowosc"] = {"jest": True, "ustalenie": "It published a pro-disclosure framework while silent on a breach it knew about.",
                     "twierdzenia": [2, 3, 4], "dlaczego_nie_w_jednym": "timeline in ABC, framework in Transformer"}
    n = sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA)
    sprawdz("ustalenie na dwoch adresach — jest", n["jest"] and len(n["zrodla"]) == 2, n)
    ODP["nowosc"] = {"jest": True, "ustalenie": "Breach in June, awareness in August.", "twierdzenia": [1, 2]}
    n = sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA)
    sprawdz("KONTRDOWOD: jeden adres — to streszczenie, nie ustalenie", not n["jest"], n)
    ODP["nowosc"] = {"jest": False, "ustalenie": "", "dlaczego_nie_w_jednym": "all in one report"}
    sprawdz("model mowi: nie ma — nie ma", not sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA)["jest"])
    ODP["nowosc"] = {"jest": True, "ustalenie": "x", "twierdzenia": [99, "a"]}
    sprawdz("KONTRDOWOD: numery spoza karty nie licza sie",
            not sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA)["jest"])
    # ZYWY TEST 27.09: „luka w osi czasu" przeszla, a ABC wylozylo ja w calosci.
    ODP["nowosc"] = {"jest": True, "twierdzenia": [1, 2, 3],
                     "ustalenie": "Access on 18 June, discovery in August, notice on September 10."}
    TEKSTY = {"https://www.abc.net.au/t": "June 18: breached. August 11: aware. September 10: email sent.",
              "https://www.npr.org/x": "On June 18 an agent accessed the portal."}
    n = sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA, teksty_zrodel=TEKSTY)
    sprawdz("KONTRDOWOD: wszystkie daty ustalenia w jednym zrodle (ABC) — to nie ustalenie",
            not n["jest"] and "abc.net.au" in n["powod"], n)
    ODP["nowosc"] = {"jest": True, "twierdzenia": [2, 3],
                     "ustalenie": "It published a disclosure framework on 16 September while silent "
                                  "on a breach it had known about since August 11."}
    TEKSTY2 = {"https://www.abc.net.au/t": "August 11: aware of the breach.",
               "https://www.transformernews.ai/p": "published on September 16, favors disclosure"}
    n = sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA, teksty_zrodel=TEKSTY2)
    sprawdz("daty z dwoch roznych zrodel — ustalenie jest", n["jest"], n)
    sprawdz("znaczniki: 18 June i June 18 to to samo",
            sledztwo._znaczniki("on 18 June") == sledztwo._znaczniki("June 18th"),
            (sledztwo._znaczniki("on 18 June"), sledztwo._znaczniki("June 18th")))
    llm.call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("padlo"))
    sprawdz("awaria modelu — brak ustalenia, bez wyjatku",
            not sledztwo.nowosc(sqlite3.connect(":memory:"), None, KARTA, DUZA)["jest"])
    ok, opis = sledztwo.pelny_obraz(KARTA)
    sprawdz("KONTRDOWOD: cztery twierdzenia z dwoch serwisow to nie pelny obraz", not ok, opis)
    _pelna = {"confirmed_claims": [{"claim": "c%d" % i, "url": "https://s%d.example/x" % (i % 5)}
                                   for i in range(9)]}
    sprawdz("dziewiec twierdzen z pieciu serwisow — pelny obraz", sledztwo.pelny_obraz(_pelna)[0],
            sledztwo.pelny_obraz(_pelna))

    print()
    print("=== 3b. ZDANIA BEZ POKRYCIA W ARTYKULE ===")
    BODY = ("The agent kept trying. Every request they sent went out from systems the company "
            "controls. It ended up inside.\n\nAustralia set up a taskforce of 12 agencies.")
    ODP["naprawa_artykulu"] = {"poprawki": [
        {"nr": 1, "nowe": "The requests came from OpenAI's own evaluation, not an outside attacker."},
        {"nr": 2, "nowe": "Australia set up a taskforce of 40 agencies."}]}
    llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])
    nowy, log = stages.popraw_bez_pokrycia(
        sqlite3.connect(":memory:"), None, BODY, KARTA,
        [{"text": "Every request they sent went out from systems the company controls."},
         {"text": "Australia set up a taskforce of 12 agencies."},
         {"text": "A sentence that is not in the article at all."}])
    sprawdz("zdanie bez pokrycia przepisane", "own evaluation" in nowy and "company controls" not in nowy, nowy)
    sprawdz("KONTRDOWOD: poprawka z liczba spoza dowodow (40) odrzucona, zdanie zostaje",
            "12 agencies" in nowy and "40" not in nowy and any("spoza dowodow" in x for x in log), (nowy, log))
    sprawdz("akapity zostaja", "\n\n" in nowy)
    ODP["naprawa_artykulu"] = {"poprawki": [{"nr": 1, "nowe": ""}]}
    nowy, log = stages.popraw_bez_pokrycia(
        sqlite3.connect(":memory:"), None, BODY, KARTA,
        [{"text": "Every request they sent went out from systems the company controls."}])
    sprawdz("pusta poprawka usuwa zdanie", "company controls" not in nowy and "kept trying. It ended" in nowy, nowy)
    llm.call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("padlo"))
    nowy, log = stages.popraw_bez_pokrycia(sqlite3.connect(":memory:"), None, BODY, KARTA,
                                           [{"text": "Every request they sent went out from systems the company controls."}])
    sprawdz("awaria — tekst bez zmian", nowy == BODY, log)
    # Zywy test 27.09: No excerpt I have seen gives the company's reason.
    _warsztat = [z["text"] for z in stages.zdania_o_warsztacie(
        "No excerpt I have seen gives the company's reason for the gap. The card says little. "
        "Our reading is that OpenAI waited. The agent kept going.")]
    sprawdz("zdania o naszej kuchni wylapane",
            _warsztat == ["No excerpt I have seen gives the company's reason for the gap.",
                          "The card says little."], _warsztat)
    sprawdz("KONTRDOWOD: our reading (podpis hipotezy) to nie kuchnia",
            not any("Our reading" in z for z in _warsztat))

    print()
    print("=== 4. KATY SERII (od 25.10.2026 szesc rodzajow, 4-5 na historie) ===")
    llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])
    ODP["przeslania"] = {"przeslania": [
        {"rodzaj": "ZA_DWA_LATA", "przeslanie": "Scenario without facts.", "tresc": "x", "hak": "y", "fakty": [],
         "za": "a", "przeciw": "b", "co_obali": "c"},
        {"rodzaj": "ZA_DWA_LATA", "przeslanie": "Agent incidents get a reporting clock.", "hak": "PM promised consequences",
         "tresc": "If regulators copy Australia...", "fakty": [1, 4], "za": "PM said legal consequences",
         "przeciw": "self-regulation", "co_obali": "no rule by 2028"},
        {"rodzaj": "USTALENIE", "przeslanie": "Silent while publishing a disclosure rule.", "hak": "August 11",
         "tresc": "Timeline plus framework.", "fakty": [2, 3, 4], "za": "", "przeciw": "", "co_obali": ""},
        {"rodzaj": "MOTYW", "przeslanie": "They let victims decide publicity.", "tresc": "Policy defers.",
         "hak": "the framework", "fakty": [3], "za": "policy quote", "przeciw": "", "co_obali": "a request to wait"},
        {"rodzaj": "MOTYW", "przeslanie": "Duplicate motive.", "tresc": "x", "hak": "y", "fakty": [1],
         "za": "a", "przeciw": "b", "co_obali": "c"},
        {"rodzaj": "KURIOZUM", "przeslanie": "Eight weeks of silence.", "tresc": "x", "fakty": [1, 2]},
        {"rodzaj": "INNE", "przeslanie": "?", "tresc": "?", "hak": "?", "fakty": [1]},
        {"rodzaj": "USTALENIE", "przeslanie": "A second finding.", "tresc": "x", "hak": "y", "fakty": [1]},
        {"rodzaj": "USTALENIE", "przeslanie": "skip me", "tresc": "x", "hak": "y", "fakty": [1], "pominac": True}]}
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        pr = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA)
    rodzaje = [p["rodzaj"] for p in pr]
    sprawdz("zostaja: ustalenie, drugi motyw (pierwszy bez dowodu przeciw), scenariusz z faktami"
            " — w kolejnosci publikacji, nie odpowiedzi modelu",
            rodzaje == ["USTALENIE", "MOTYW", "ZA_DWA_LATA"], rodzaje)
    # 25.10.2026 (wlasciciel: „mamy byc wyrazisci, nie wszystko musi byc na 100% udowodnione"):
    # analiza bez dowodu przeciw PRZECHODZI — drugi motyw odpada juz jako powtorka.
    sprawdz("motyw bez dowodu przeciw PRZYJETY (wyrazistosc), drugi motyw to powtorka",
            [p["przeslanie"] for p in pr if p["rodzaj"] == "MOTYW"] == ["They let victims decide publicity."]
            and "analiza bez dowodu przeciw" not in _log.getvalue(), _log.getvalue())
    sprawdz("scenariusz bez twierdzen karty odrzucony", "bez twierdzen karty" in _log.getvalue())
    sprawdz("powtorzony rodzaj odrzucony z nazwanym powodem", "powtorzony rodzaj" in _log.getvalue())
    sprawdz("KONTRDOWOD: kat bez haka (konkretnego szczegolu na otwarcie) odrzucony",
            "KURIOZUM: bez haka" in _log.getvalue(), _log.getvalue())
    sprawdz("przeslanie niesie twierdzenia karty z cytatem i adresem oraz hak",
            pr[0]["fakty"][0] == {k: KARTA["confirmed_claims"][1][k] for k in ("claim", "evidence", "url")}
            and pr[0]["hak"] == "August 11", pr[0])
    # SZESC DOBRYCH KATOW -> PIEC. Odpada kat faktow z najmniejsza liczba twierdzen
    # (przy remisie pozniejszy); motyw i scenariusz zostaja, bo na nich stoi artykul.
    _katy = {"KURIOZUM": [1, 2], "MECHANIZM": [1], "USTALENIE": [2, 3, 4], "KTO_PLACI": [4],
             "MOTYW": [3], "ZA_DWA_LATA": [1]}
    ODP["przeslania"] = {"przeslania": [
        {"rodzaj": r, "przeslanie": "Angle %s." % r, "tresc": "x", "hak": "detail %s" % r, "fakty": f,
         "za": "a", "przeciw": "b", "co_obali": "c"} for r, f in reversed(list(_katy.items()))]}
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        pr5 = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA)
    sprawdz("szesc katow -> piec; odpada KTO_PLACI (remis z MECHANIZM, pozniejszy), kuriozum pierwsze",
            [p["rodzaj"] for p in pr5] == ["KURIOZUM", "MECHANIZM", "USTALENIE", "MOTYW", "ZA_DWA_LATA"]
            and "KTO_PLACI: ponad 5 katow" in _log.getvalue(), ([p["rodzaj"] for p in pr5], _log.getvalue()))
    # ODMOWA OPUSA (klasyfikator „cyber", 25.10: pierwsza seria to luka PHP2Shell) —
    # te same katy pisze zapas; bez niego sledztwo zapisalo by sie bez katow.
    _odp_katow = dict(ODP["przeslania"])

    def _odmowa(purpose, system, user, **kw):
        if purpose == "przeslania":
            raise llm.OdmowaDostawcy("dostawca odmówił: cyber")
        return json.dumps(_odp_katow)
    llm.call = _odmowa
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        _zap = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA)
    sprawdz("odmowa Opusa: katy pisze zapas (DeepSeek), log to mowi",
            len(_zap) == 5 and "odmowil katow" in _log.getvalue()
            and config.MODEL_FOR.get("przeslania_zapas") == config.DEEPSEEK
            and config.MAX_TOKENS.get("przeslania_zapas"), _log.getvalue()[-300:])

    def _odmowa_obu(purpose, system, user, **kw):
        raise llm.OdmowaDostawcy("dostawca odmówił: cyber")
    llm.call = _odmowa_obu
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("KONTRDOWOD: gdy odmowi tez zapas — pusto, bez wyjatku",
                sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA) == [])
    llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])
    sprawdz("kazdy rodzaj obu zestawow ma typ notki i opis, kolejnosc zaczyna od haka, konczy analiza",
            set(sledztwo.TYP_NOTKI) == set(sledztwo.RODZAJE) | set(sledztwo.RODZAJE_PREMIERY)
            == set(sledztwo.OPISY_KATOW) and sledztwo.RODZAJE[0] == "KURIOZUM"
            and sledztwo.RODZAJE_PREMIERY[0] == "SMACZEK"
            and sledztwo.RODZAJE[-2:] == ("MOTYW", "ZA_DWA_LATA")
            and sledztwo.RODZAJE_PREMIERY[-1] == "CO_Z_TEGO")

    print()
    print("=== 4b. PREMIERA MODELU: WLASNY ZESTAW KATOW (25.10.2026) ===")
    PROMPTY_KATOW = []

    def _premiera(purpose, system, user, **kw):
        PROMPTY_KATOW.append(user)
        return json.dumps({"przeslania": [
            {"rodzaj": "KURIOZUM", "przeslanie": "Not in this set.", "tresc": "x", "hak": "y", "fakty": [1]},
            {"rodzaj": "WIELKIE_PYTANIE", "przeslanie": "Is it AGI at maths?", "tresc": "x", "hak": "a score",
             "fakty": [1], "za": "score", "przeciw": "", "co_obali": "c"},
            {"rodzaj": "CO_Z_TEGO", "przeslanie": "Cheaper proofs.", "tresc": "x", "hak": "price", "fakty": [2],
             "za": "a", "przeciw": "b", "co_obali": ""},
            {"rodzaj": "LICZBY", "przeslanie": "Claimed 70, measured 52.", "tresc": "x", "hak": "70 vs 52",
             "fakty": [1, 2], "za": "", "przeciw": "", "co_obali": ""},
            {"rodzaj": "SMACZEK", "przeslanie": "It refused its own test.", "tresc": "x", "hak": "system card 4.2",
             "fakty": [3]}]})
    llm.call = _premiera
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        _pr_p = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA, typ="premiera")
    sprawdz("premiera: zostaja katy premiery w jej kolejnosci, analizy bez „przeciw” tez",
            [p["rodzaj"] for p in _pr_p] == ["SMACZEK", "LICZBY", "WIELKIE_PYTANIE", "CO_Z_TEGO"],
            [p["rodzaj"] for p in _pr_p])
    sprawdz("KONTRDOWOD: kat zwyklego sledztwa w premierze odrzucony",
            "nieznany rodzaj 'KURIOZUM'" in _log.getvalue(), _log.getvalue())
    _prompty = {n: pathlib.Path("agent-v2/prompts/%s" % n).read_text(encoding="utf-8")
                for n in ("przeslania.md", "notka.md", "pisarz.md")}
    sprawdz("prompty kaza miec zdanie i nie zakazuja werdyktu AGI",
            "Have opinions" in _prompty["przeslania.md"] and "Have a point of view" in _prompty["notka.md"]
            and "point of view" in _prompty["pisarz.md"]
            and not any("Never declare AGI" in t for t in _prompty.values())
            and "If it looks like AGI at maths" in sledztwo.OPISY_KATOW["WIELKIE_PYTANIE"])
    sprawdz("granica zostaje: fakty tylko z karty",
            "facts (numbers, quotes, people, dates, events) come only" in _prompty["przeslania.md"])
    sprawdz("prompt premiery opisuje jej katy, nie katy sledztwa",
            PROMPTY_KATOW and "LICZBY" in PROMPTY_KATOW[-1] and "claimed versus measured" in PROMPTY_KATOW[-1]
            and "KURIOZUM —" not in PROMPTY_KATOW[-1] and '"SMACZEK"|"LICZBY"' in PROMPTY_KATOW[-1])
    sprawdz("typ sledztwa z kategorii", sledztwo.typ_sledztwa("PREMIERA_MODELU") == "premiera"
            and sledztwo.typ_sledztwa("PRACA_EKONOMIA") == "sledztwo" and sledztwo.typ_sledztwa(None) == "sledztwo")

    print()
    print("=== 4c. DUZY TEMAT: WIELKOSC x WAGA KATEGORII x KARA ZA POWTORKE ===")

    def _hist(m, tytul, hosty):
        return {"miejsce": m, "tytul": tytul, "hak": "", "glebia": "", "naglowki": [
            w("K%d" % i, "https://%s/%d/%d" % (h, m, i), "%s %d" % (tytul, i)) for i, h in enumerate(hosty)]}
    _hosty = ["www.bbc.co.uk", "www.npr.org", "www.wired.com", "arstechnica.com", "www.theverge.com",
              "techcrunch.com", "www.reuters.com", "www.ft.com"]
    H_RYZYKO = _hist(1, "Security flaw", _hosty[:4])        # radar 1, 4 serwisy
    H_PRAWO = _hist(2, "New AI law", _hosty[:5])            # 5 serwisow
    H_PREMIERA = _hist(3, "New model launch", _hosty[:8])   # 8 serwisow
    H_MALA = _hist(4, "Tiny story", _hosty[:2])             # za mala
    KATEGORIE_ATRAPA = {"historie": [{"nr": 1, "kategoria": "RYZYKO_BEZPIECZENSTWO", "zapytanie": "flaw"},
                                     {"nr": 2, "kategoria": "POLITYKA_PRAWO", "zapytanie": "AI law"},
                                     {"nr": 3, "kategoria": "PREMIERA_MODELU", "zapytanie": "Model X"}]}
    llm.call = lambda purpose, system, user, **kw: json.dumps(KATEGORIE_ATRAPA)
    with contextlib.redirect_stdout(io.StringIO()):
        _wyb, _rank = sledztwo.wybierz_historie([H_RYZYKO, H_PRAWO, H_PREMIERA, H_MALA])
    sprawdz("wygrywa najwieksza historia o najlepszej kategorii, nie pierwsza z radaru",
            _wyb is H_PREMIERA and _wyb["kategoria"] == "PREMIERA_MODELU" and _wyb["zapytanie"] == "Model X"
            and _wyb["serwisy"] == 8, (_wyb or {}).get("tytul"))
    sprawdz("ranking ma kazda historie, zbyt mala z powodem, ocenione z wynikiem",
            len(_rank) == 4 and not _rank[3]["ok"] and all("wynik" in r for r in _rank[:3]), _rank)
    # KARA: dwa ostatnie sledztwa byly premierami, a duza historia firmowa ma 6 serwisow.
    sledztwo.zapisz_sledztwo({"historia": "x", "zrodla": [], "kategoria": "PREMIERA_MODELU"})
    H_FIRMA = _hist(5, "Company drama", _hosty[:6])
    KATEGORIE_ATRAPA["historie"].append({"nr": 5, "kategoria": "FIRMY_WLADZA", "zapytanie": "drama"})
    with contextlib.redirect_stdout(io.StringIO()):
        _wyb2, _rank2 = sledztwo.wybierz_historie([H_PREMIERA, H_FIRMA])
    sprawdz("ta sama dziedzina co niedawne sledztwo dostaje kare i przegrywa z inna duza",
            _wyb2 is H_FIRMA and any(r.get("kara") for r in _rank2), [(r["tytul"], r.get("wynik")) for r in _rank2])
    llm.call = lambda purpose, system, user, **kw: (_ for _ in ()).throw(RuntimeError("padlo"))
    with contextlib.redirect_stdout(io.StringIO()):
        _wyb3, _ = sledztwo.wybierz_historie([H_RYZYKO, H_PRAWO, H_PREMIERA])
    sprawdz("KONTRDOWOD: bez kategorii (awaria) wybor sama wielkoscia — nadal najwieksza",
            _wyb3 is H_PREMIERA, (_wyb3 or {}).get("tytul"))
    (config.DATA_DIR / sledztwo.PLIK_SLEDZTW).unlink()

    print()
    print("=== 4d. GLOSY LUDZI (Hacker News) I CENNIK (OpenRouter) NA ATRAPIE SIECI ===")

    class _Odp:
        def __init__(self, d):
            self._d = d

        def json(self):
            return self._d

    class _Siec:
        def __init__(self):
            self.zapytania = []

        def get(self, url, params=None, timeout=None):
            self.zapytania.append((url, params))
            if url == sledztwo.HN_SZUKAJ:
                return _Odp({"hits": [
                    {"objectID": "1", "title": "Model X is out", "points": 900, "num_comments": 400},
                    {"objectID": "2", "title": "Tiny thread", "points": 999, "num_comments": 3},
                    {"objectID": "3", "title": "Model X benchmarks", "points": 300, "num_comments": 120},
                    {"objectID": "4", "title": "Third big thread", "points": 100, "num_comments": 90}]})
            if url.startswith("https://hn.algolia.com/api/v1/items/"):
                return _Odp({"children": [
                    {"text": "<p>I ran it on my own repo for a week &amp; it fixed real bugs, but it also invented an API that does not exist.</p>"},
                    {"text": "short"}]})
            if url == sledztwo.OPENROUTER_MODELE:
                return _Odp({"data": [
                    {"id": "lab/model-x", "name": "Lab: Model X", "created": 1792000000, "context_length": 400000,
                     "pricing": {"prompt": "0.000003", "completion": "0.000015"}},
                    {"id": "lab/model-y", "name": "Lab: Model Y", "created": 1790000000, "context_length": 100000,
                     "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]})
            raise AssertionError(url)
    _siec = _Siec()
    with contextlib.redirect_stdout(io.StringIO()):
        _gl = sledztwo.glosy_hn("Model X", http=_siec)
    sprawdz("Hacker News: dwa najwieksze watki z >= 20 komentarzami, maly pominiety",
            [d["url"] for d in _gl] == ["https://news.ycombinator.com/item?id=1",
                                        "https://news.ycombinator.com/item?id=3"], [d["url"] for d in _gl])
    sprawdz("komentarz bez HTML, krotki pominiety, dokument podpisany jako opinie",
            "fixed real bugs, but it also invented" in _gl[0]["text"] and "&amp;" not in _gl[0]["text"]
            and "short" not in _gl[0]["text"] and _gl[0]["text"].startswith(sledztwo.NAGLOWEK_GLOSOW), _gl[0]["text"][:200])
    sprawdz("zapytanie z oknem dat (created_at_i)", "created_at_i>" in str(_siec.zapytania[0][1]))
    with contextlib.redirect_stdout(io.StringIO()):
        _cn = sledztwo.cennik_openrouter("Model X", http=_siec)
    sprawdz("OpenRouter: pasujacy model, cena za milion tokenow, kontekst, podpis posrednika",
            len(_cn) == 1 and "$3.00" in _cn[0]["text"] and "$15.00" in _cn[0]["text"] and "400000" in _cn[0]["text"]
            and "Model Y" not in _cn[0]["text"] and "reseller" in _cn[0]["text"], _cn and _cn[0]["text"])

    class _Padla:
        def get(self, *a, **k):
            raise OSError("brak sieci")
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("KONTRDOWOD: awaria sieci = pusto, bez wyjatku",
                sledztwo.glosy_hn("Model X", http=_Padla()) == [] and sledztwo.cennik_openrouter("Model X", http=_Padla()) == []
                and sledztwo.glosy_hn("", http=_siec) == [])
finally:
    llm.call = _prawdziwy_call

print()
print("=== 5. KOLEJKA: DO TRZECH KATOW NA DOBE ===")
sprawdz("pusta kolejka — nic", sledztwo.wez_przeslanie() is None)
sprawdz("pusta kolejka — nic nie czeka, mozna badac", sledztwo.czekajace_przeslania() == 0)
sledztwo.dodaj_do_kolejki(pr5, DUZA, KARTA, run_id=7)
sprawdz("po sledztwie czeka piec katow", sledztwo.czekajace_przeslania() == 5,
        sledztwo.czekajace_przeslania())
_k0 = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
sprawdz("kat wazny cztery dni i niesie hak do notki",
        all(datetime.fromisoformat(p["wazny_do"]) - datetime.fromisoformat(p["kiedy"])
            == timedelta(days=sledztwo.WAZNOSC_PRZESLANIA_DNI) for p in _k0)
        and sledztwo.WAZNOSC_PRZESLANIA_DNI == 4 and _k0[0]["perspektywa"]["hak"] == "detail KURIOZUM", _k0[0])
# Sledztwo bierze czolo radaru, ktore tego samego dnia poszlo juz zwykla notka
# (27.09: 11:22 notka o Medicare, 13:11 sledztwo o tym samym).
sprawdz("KONTRDOWOD: w dniu sledztwa przeslanie czeka do jutra", sledztwo.wez_przeslanie() is None)
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
p1 = sledztwo.wez_przeslanie()
sprawdz("pierwsze idzie kuriozum", (p1 or {}).get("rodzaj") == "KURIOZUM", p1)
fakt, material = sledztwo.material_notki(p1)
sprawdz("notka dostaje przeslanie, hak i twierdzenia sledztwa",
        material["perspective"]["przeslanie"] == pr5[0]["przeslanie"]
        and material["perspective"]["hak"] == "detail KURIOZUM"
        and material["investigation"]["supporting_claims"] and fakt["url"])
sprawdz("typ notki z rodzaju", p1["typ_notki"] == "CIEKAWOSTKA")


def _wydane(*pary):
    """Dziennik z notkami z przeslan: (identyfikator, kiedy)."""
    (config.DATA_DIR / "dziennik.jsonl").write_text("".join(json.dumps(
        {"rodzaj": "notka", "udane": True, "kiedy": k.isoformat(), "przeslanie_id": i}) + "\n"
        for i, k in pary), encoding="utf-8")


_id = [p["id"] for p in sorted(_k0, key=lambda p: p["kolejnosc"])]
_wydane((_id[0], TERAZ))
p2 = sledztwo.wez_przeslanie()
sprawdz("po jednym dzis — drugi kat jeszcze dzis (mechanizm)", (p2 or {}).get("rodzaj") == "MECHANIZM", p2)
# Zywy test 25.10: notka ze scenariuszem otworzyla faktem, na ktorym stala notka z ustaleniem.
_wcz = sledztwo.material_notki(p2)[1]["investigation"]["earlier_angles_already_published"]
sprawdz("notka wie, jakie katy tej historii juz wyszly (przeslanie i hak), bez siebie samej",
        [k["angle"] for k in _wcz] == ["KURIOZUM"] and _wcz[0]["opening_detail"] == "detail KURIOZUM"
        and _wcz[0]["message"] == pr5[0]["przeslanie"], _wcz)
sprawdz("KONTRDOWOD: katy innej historii i niewydane sie nie licza",
        sledztwo._wczesniejsze_katy({"historia": "Inna historia", "id": "x"}) == []
        and all(k["angle"] != "USTALENIE" for k in _wcz))
_wydane((_id[0], TERAZ), (_id[1], TERAZ), (_id[2], TERAZ))
sprawdz("KONTRDOWOD: po trzech dzis — czwarty dopiero jutro", sledztwo.wez_przeslanie() is None)
_wydane((_id[0], TERAZ), (_id[0], TERAZ), (_id[1], TERAZ))
sprawdz("ta sama notka zapisana dwa razy liczy sie raz",
        (sledztwo.wez_przeslanie() or {}).get("rodzaj") == "USTALENIE")
_wydane(*((i, TERAZ - timedelta(days=1)) for i in _id[:3]))
p3 = sledztwo.wez_przeslanie()
sprawdz("nazajutrz: motyw, a wydane wczoraj nie wracaja", (p3 or {}).get("rodzaj") == "MOTYW", p3)
sprawdz("wydane nie czekaja — zostaja dwa", sledztwo.czekajace_przeslania() == 2,
        sledztwo.czekajace_przeslania())
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["wazny_do"] = (TERAZ - timedelta(hours=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
sprawdz("KONTRDOWOD: przeslanie po terminie nie wychodzi", sledztwo.wez_przeslanie() is None)
sprawdz("KONTRDOWOD: przeterminowane nie blokuja nowego sledztwa", sledztwo.czekajace_przeslania() == 0)
(config.DATA_DIR / "dziennik.jsonl").unlink()

print()
print("=== 6. LIMITY, DROGA DO DZIENNIKA, ZDROWIE ZRODEL ===")
sprawdz("limit: zero sledztw", sledztwo.ile_sledztw() == 0 and sledztwo.ile_artykulow() == 0)
sledztwo.zapisz_sledztwo({"historia": "a", "zrodla": []})
sledztwo.oznacz_artykul(5)
# 18-24.10.2026: wpis artykulu liczyl sie jako drugie sledztwo i limit 2 blokowal
# zegar przez tydzien po jednym sledztwie.
sprawdz("limit liczy sledztwa BEZ wpisow artykulu, artykuly osobno",
        sledztwo.ile_sledztw() == 1 and sledztwo.ile_artykulow() == 1,
        (sledztwo.ile_sledztw(), sledztwo.ile_artykulow()))


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


_art, _st, _run = _kod("agent-v2/artykul_z_puli.py"), _kod("agent-v2/stages.py"), _kod("agent-v2/run.py")
sprawdz("artykul: droga --sledztwo i pominiecie artykulu z puli po artykule ze sledztwa",
        '"--sledztwo" in sys.argv' in _art and "_sledztwo.ile_artykulow(6)" in _art)
sprawdz("sledztwo bez --wyslij nie rusza kolejki ani pamieci",
        "if na_serio:" in _art and "sledztwo.dodaj_do_kolejki" in _art)
# 27.09 pierwsze sledztwo na produkcji: pisarz artykulu odmowil („cyber") i
# przebieg wywrocil sie tracebackiem, choc przeslania byly juz w kolejce.
sprawdz("odmowa dostawcy przy artykule sledztwa konczy przebieg komunikatem, po zapisie przeslan",
        "except llm.OdmowaDostawcy" in _art
        and _art.index("sledztwo.dodaj_do_kolejki") < _art.index("except llm.OdmowaDostawcy")
        < _art.index("sledztwo.oznacz_artykul(run_id)"))
sprawdz("nowe sledztwo, gdy w kolejce zostalo mniej niz dzien katow (przed wyborem historii)",
        "czeka = sledztwo.czekajace_przeslania()" in _art
        and "if czeka >= sledztwo.PRZESLAN_NA_DOBE" in _art
        and _art.index("sledztwo.czekajace_przeslania()") < _art.index("sledztwo.historie("))
sprawdz("artykul ze sledztwa raz na tydzien: limit przed pisaniem, po kolejce katow",
        "sledztwo.ile_artykulow(6) >= sledztwo.ARTYKULOW_NA_TYDZIEN" in _art
        and _art.index("sledztwo.dodaj_do_kolejki") < _art.index("sledztwo.ile_artykulow(6) >= sledztwo.ARTYKULOW")
        < _art.index("kod = _napisz_i_zapisz(conn, run_id, brief, card, evidence)"))
sprawdz("artykul: pelny obraz i JEDNA nasza analiza przy co najmniej czterech katach",
        'analiza_ok = bool(rodzaje & set(sledztwo.ANALIZY)) and len(przes) >= 4' in _art)
_sl = _art[_art.index("def _przebieg_sledztwa"):]
sprawdz("przebieg: wybor duzego tematu, pytania premiery, glosy HN i cennik w korpusie, typ do pisarza",
        "sledztwo.wybierz_historie(historie" in _art and "pod += list(sledztwo.PYTANIA_PREMIERY)" in _art
        and "sledztwo.glosy_hn(_zapytanie)" in _art and "sledztwo.cennik_openrouter(_zapytanie)" in _art
        and 'card["investigation_type"]' in _art and "przeslania(conn, run_id, card, dossier, wybrana, typ=typ)" in _art
        and _sl.index("corpus = stages.fetch(conn, run_id, zrodla)") < _sl.index("sledztwo.glosy_hn(_zapytanie)")
        < _sl.index("evidence = stages.classify("))
sprawdz("pisarz notki dostaje wczesniejsze katy w prompcie",
        "earlier_angles_already_published" in pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8"))
sprawdz("pisarz artykulu dostaje wszystkie katy serii",
        'card["investigation_angles"]' in _art and "investigation_angles" in
        pathlib.Path("agent-v2/prompts/pisarz.md").read_text(encoding="utf-8"))
sprawdz("notke z przeslania pisze Opus, zwykla notka zostaje przy rotacji pisarzy",
        'etap_pisarza = "notka_przeslania"' in _st
        and _st.index("etap_pisarza = _pisarze[") < _st.index('etap_pisarza = "notka_przeslania"')
        and config.MODEL_FOR.get("notka_przeslania") == config.CLAUDE
        and config.MAX_TOKENS.get("notka_przeslania") and config.EFFORT.get("notka_przeslania"))
sprawdz("notka bierze przeslanie i zapisuje jego identyfikator",
        "_sledztwo.wez_przeslanie()" in _st and 'wynik["przeslanie_id"]' in _st
        and '"przeslanie_id":' in _run)
rekord = stages._rekord_do_weryfikacji("DYSKUSJA", material)
sprawdz("weryfikator dostaje twierdzenia sledztwa z cytatami",
        "Claims from our investigation" in rekord and "August 11" in rekord, rekord[-300:])

stan = {n: {"ok": True, "blad": "", "wpisow": 3, "najnowszy": TERAZ.strftime("%Y-%m-%d")}
        for n in {**kk.ZRODLA, **kk.ZRODLA_LUDZIE}}
stan["EFF"] = {"ok": False, "blad": "HTTP 404", "wpisow": 0, "najnowszy": ""}
stan["Pew"] = {"ok": True, "blad": "", "wpisow": 0, "najnowszy": (TERAZ - timedelta(days=30)).strftime("%Y-%m-%d")}
for _ in range(kk.PORAZEK_DO_ALARMU):
    kk._zapisz_zdrowie(stan)
zle = dict(kk.zle_zrodla())
sprawdz("zrodlo, ktore nie odpowiada 3 razy z rzedu, zglaszane", "EFF" in zle and "404" in zle["EFF"], zle)
sprawdz("zrodlo bez nowych wpisow o AI od 30 dni zglaszane", "Pew" in zle and "30 dni" in zle["Pew"], zle)
sprawdz("KONTRDOWOD: zdrowe zrodla nie sa zglaszane", "OpenAI" not in zle and len(zle) == 2, zle)
stan["EFF"] = {"ok": True, "blad": "", "wpisow": 1, "najnowszy": TERAZ.strftime("%Y-%m-%d")}
kk._zapisz_zdrowie(stan)
sprawdz("jeden sukces zeruje licznik porazek", "EFF" not in dict(kk.zle_zrodla()))
import karta_wynikow  # noqa: E402
sprawdz("karta wynikow pokazuje zrodla z problemem",
        any("Pew" in x for x in karta_wynikow.zrodla_z_problemem(config.DATA_DIR)))

for nazwa in ("nowosc.md", "przeslania.md", "pisarz.md", "notka.md"):
    import re  # noqa: E402
    _surowy = (pathlib.Path("agent-v2/prompts") / nazwa).read_text(encoding="utf-8")
    _pola = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", _surowy))
    try:
        _surowy.format(**{p: "x" for p in _pola})
        _ok = True
    except (KeyError, ValueError, IndexError) as exc:
        _ok = exc
    sprawdz("%s formatuje sie bez bledu" % nazwa, _ok is True, _ok)

print()
print("=== 7. NOTKA Z PRZESLANIA: OPUS, A GDY ODMOWI — ZWYKLY PISARZ (prawdziwe notki_dnia) ===")
# Opus 5.5 ma klasyfikatory „cyber"; 27.09 odmowil artykulu o agentach na
# stronach rzadow. `note` lapie odmowe jako pusta liste kandydatow.
sledztwo.dodaj_do_kolejki(pr5, DUZA, KARTA, run_id=8)
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
ETAPY = []


def _atrapa_note(conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", **k):
    ETAPY.append(etap)
    if etap == "notka_przeslania":
        return {"type": typ, "forma": note_form, "candidates": []}
    return {"type": typ, "forma": note_form,
            "candidates": [{"note": "A plain note.", "safe_to_post": True}]}


_zastepcze = {"artykul_do_promocji": lambda: None, "pamiec_wystawionych": lambda: [],
              "znajdz_ciekawostki": lambda conn, run_id, ile=8: [],
              "opublikowane_teksty": lambda *a, **k: [], "teksty_ostatnich_notek": lambda *a, **k: [],
              "note": _atrapa_note}
_oryginaly = {n: getattr(stages, n) for n in _zastepcze}
try:
    for n, f in _zastepcze.items():
        setattr(stages, n, f)
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        _n = stages.notki_dnia(None, 0, ciekawostki=[], ile=1)
finally:
    for n, f in _oryginaly.items():
        setattr(stages, n, f)
sprawdz("najpierw pisze Opus, po pustym wyniku zwykly pisarz",
        ETAPY[:2] == ["notka_przeslania", "note"], ETAPY)
sprawdz("notka wychodzi i niesie identyfikator przeslania",
        bool(_n) and bool(_n[0].get("przeslanie_id"))
        and (_n[0].get("candidates") or [{}])[0].get("note") == "A plain note.", _n)
sprawdz("log mowi, ze Opus nie napisal i kto pisze zamiast niego",
        "Opus nie napisal notki" in _log.getvalue(), _log.getvalue()[-400:])
ETAPY.clear()
_zastepcze["note"] = lambda conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", **k: (
    ETAPY.append(etap) or {"type": typ, "forma": note_form,
                           "candidates": [{"note": "Opus note.", "safe_to_post": True}]})
try:
    for n, f in _zastepcze.items():
        setattr(stages, n, f)
    with contextlib.redirect_stdout(io.StringIO()):
        _n = stages.notki_dnia(None, 0, ciekawostki=[], ile=1)
finally:
    for n, f in _oryginaly.items():
        setattr(stages, n, f)
sprawdz("KONTRDOWOD: gdy Opus napisze, zwykly pisarz nie jest wolany",
        ETAPY == ["notka_przeslania"], ETAPY)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
