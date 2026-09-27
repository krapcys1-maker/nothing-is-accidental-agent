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
  5. kolejka: ustalenie pierwsze, jedno na dobe, wydane nie wraca, stare wygasa;
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
    print("=== 4. TRZY PRZESLANIA ===")
    llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])
    ODP["przeslania"] = {"przeslania": [
        {"rodzaj": "USTALENIE", "przeslanie": "Silent while publishing a disclosure rule.",
         "tresc": "Timeline plus framework.", "fakty": [2, 3, 4], "za": "", "przeciw": "", "co_obali": ""},
        {"rodzaj": "MOTYW", "przeslanie": "They let victims decide publicity.", "tresc": "Policy defers.",
         "fakty": [3], "za": "policy quote", "przeciw": "", "co_obali": "a request to wait"},
        {"rodzaj": "MOTYW", "przeslanie": "Duplicate motive.", "tresc": "x", "fakty": [1],
         "za": "a", "przeciw": "b", "co_obali": "c"},
        {"rodzaj": "ZA_DWA_LATA", "przeslanie": "Scenario without facts.", "tresc": "x", "fakty": [],
         "za": "a", "przeciw": "b", "co_obali": "c"},
        {"rodzaj": "ZA_DWA_LATA", "przeslanie": "Agent incidents get a reporting clock.",
         "tresc": "If regulators copy Australia...", "fakty": [1, 4], "za": "PM said legal consequences",
         "przeciw": "self-regulation", "co_obali": "no rule by 2028"},
        {"rodzaj": "INNE", "przeslanie": "?", "tresc": "?", "fakty": [1]},
        {"rodzaj": "USTALENIE", "przeslanie": "A second finding.", "tresc": "x", "fakty": [1]},
        {"rodzaj": "USTALENIE", "przeslanie": "skip me", "tresc": "x", "fakty": [1], "pominac": True}]}
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        pr = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA)
    rodzaje = [p["rodzaj"] for p in pr]
    sprawdz("zostaja: ustalenie i drugi motyw (pierwszy bez dowodu przeciw), scenariusz z faktami",
            rodzaje == ["USTALENIE", "MOTYW", "ZA_DWA_LATA"], rodzaje)
    sprawdz("KONTRDOWOD: motyw bez dowodu przeciw odrzucony (log)",
            "motyw bez dowodu przeciw" in _log.getvalue(), _log.getvalue())
    sprawdz("scenariusz bez twierdzen karty odrzucony", "bez twierdzen karty" in _log.getvalue())
    sprawdz("powtorzony rodzaj odrzucony z nazwanym powodem", "powtorzony rodzaj" in _log.getvalue())
    sprawdz("przeslanie niesie twierdzenia karty z cytatem i adresem",
            pr[0]["fakty"][0] == {k: KARTA["confirmed_claims"][1][k] for k in ("claim", "evidence", "url")},
            pr[0]["fakty"][:1])
finally:
    llm.call = _prawdziwy_call

print()
print("=== 5. KOLEJKA: JEDNO PRZESLANIE NA DOBE ===")
sprawdz("pusta kolejka — nic", sledztwo.wez_przeslanie() is None)
sledztwo.dodaj_do_kolejki(pr, DUZA, KARTA, run_id=7)
# Sledztwo bierze czolo radaru, ktore tego samego dnia poszlo juz zwykla notka
# (27.09: 11:22 notka o Medicare, 13:11 sledztwo o tym samym).
sprawdz("KONTRDOWOD: w dniu sledztwa przeslanie czeka do jutra", sledztwo.wez_przeslanie() is None)
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
p1 = sledztwo.wez_przeslanie()
sprawdz("pierwsze idzie ustalenie", (p1 or {}).get("rodzaj") == "USTALENIE", p1)
fakt, material = sledztwo.material_notki(p1)
sprawdz("notka dostaje przeslanie i twierdzenia sledztwa",
        material["perspective"]["przeslanie"] == pr[0]["przeslanie"]
        and material["investigation"]["supporting_claims"] and fakt["url"])
sprawdz("typ notki z rodzaju", p1["typ_notki"] == "CIEKAWOSTKA")
# Dziennik: ustalenie wyszlo DZIS.
(config.DATA_DIR / "dziennik.jsonl").write_text(json.dumps(
    {"rodzaj": "notka", "udane": True, "kiedy": TERAZ.isoformat(), "przeslanie_id": p1["id"]}) + "\n",
    encoding="utf-8")
sprawdz("KONTRDOWOD: po przeslaniu dzis — drugie dopiero jutro", sledztwo.wez_przeslanie() is None)
(config.DATA_DIR / "dziennik.jsonl").write_text(json.dumps(
    {"rodzaj": "notka", "udane": True, "kiedy": (TERAZ - timedelta(days=1)).isoformat(),
     "przeslanie_id": p1["id"]}) + "\n", encoding="utf-8")
p2 = sledztwo.wez_przeslanie()
sprawdz("nazajutrz: motyw, a wydane ustalenie nie wraca", (p2 or {}).get("rodzaj") == "MOTYW", p2)
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["wazny_do"] = (TERAZ - timedelta(hours=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
sprawdz("KONTRDOWOD: przeslanie po terminie nie wychodzi", sledztwo.wez_przeslanie() is None)
(config.DATA_DIR / "dziennik.jsonl").unlink()

print()
print("=== 6. LIMITY, DROGA DO DZIENNIKA, ZDROWIE ZRODEL ===")
sprawdz("limit: zero sledztw", sledztwo.ile_sledztw() == 0 and sledztwo.ile_artykulow() == 0)
sledztwo.zapisz_sledztwo({"historia": "a", "zrodla": []})
sledztwo.oznacz_artykul(5)
sprawdz("limit liczy sledztwa i artykuly", sledztwo.ile_sledztw() == 2 and sledztwo.ile_artykulow() == 1)


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))


_art, _st, _run = _kod("agent-v2/artykul_z_puli.py"), _kod("agent-v2/stages.py"), _kod("agent-v2/run.py")
sprawdz("artykul: droga --sledztwo i pominiecie artykulu z puli po artykule ze sledztwa",
        '"--sledztwo" in sys.argv' in _art and "_sledztwo.ile_artykulow(6)" in _art)
sprawdz("sledztwo bez --wyslij nie rusza kolejki ani pamieci",
        "if na_serio:" in _art and "sledztwo.dodaj_do_kolejki" in _art)
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
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
