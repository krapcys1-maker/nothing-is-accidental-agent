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
  4. przeslania (od 25.10 jedna tabela `KATY`): bramka przed planista, tag ze starego
     menu i asekuracja odrzucone, kolejnosc z regul serii (szczegoly: test_sledztwo_katy.py);
  5. kolejka: prowadzacy pierwszy, do `na_dobe` katow na dobe, wydane nie wraca,
     stare wygasa;
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
    print("=== 4. KATY SERII (od 25.10.2026 jedna tabela KATY, sklad i kolejnosc kodem) ===")
    # Karta z siedmioma twierdzeniami z czterech hostow — ponizej szesciu z dwoch planista nie jest
    # wolany (spec §2 etap 15), wiec stara czterotwierdzeniowa KARTA nie dalaby serii.
    KARTA6 = {"working_thesis": KARTA["working_thesis"], "main_mechanism": KARTA["main_mechanism"],
              "confirmed_claims": KARTA["confirmed_claims"] + [
                  {"claim": "The agent ran inside the company's own evaluation",
                   "evidence": "The agent was running inside an evaluation when it reached the portal.",
                   "url": "https://www.npr.org/a"},
                  {"claim": "Australia set up a taskforce of 12 agencies",
                   "evidence": "Australia set up a taskforce of 12 agencies.", "url": "https://www.bbc.co.uk/n"},
                  {"claim": "The PM promised legal consequences",
                   "evidence": "The prime minister promised legal consequences.", "url": "https://www.bbc.co.uk/n"}]
              # Notek najwyzej polowa twierdzen (spec §5: N = min(n_max, po bramkach, C/2)) — piec katow
              # potrzebuje dziesieciu twierdzen.
              + [{"claim": "Background claim %d" % i, "evidence": "Background passage %d." % i,
                  "url": "https://www.wired.com/%d" % i} for i in range(3)]}

    def _kat(rodzaj, fakty, naglowek, wniosek, **x):
        return dict({"rodzaj": rodzaj, "fakty": fakty, "naglowek": naglowek, "wniosek": wniosek,
                     "ai_link": "Shows how AI agents slip past the rules", "why_care": "people who use AI agents",
                     "hak": "detail %s" % rodzaj, "tresc": "Reasoning.", "kierunek": "NEUTRAL", "os": "HIDDEN"}, **x)
    KATY_ODP = {"sedno": {"jedno_zdanie": "An AI agent broke in and the company stayed quiet",
                          "co_obchodzi": [{"os": "HIDDEN", "fakty": [2]}],
                          "werdykt": {"teza": "Another country will set an agent-incident clock by 2027",
                                      "zalozenie": "regulators copy Australia"}},
                "katy": [
                    _kat("REVEAL", [2, 1], "The AI company knew of the breach on August 11, the ABC reports.",
                         "It knew for weeks before saying anything", lead=True),
                    _kat("HOW_IT_WORKS", [5], "NPR says the agent was running inside an AI company's own evaluation.",
                         "The break-in came from a test, not an attacker"),
                    _kat("WHO_GAINS_PAYS", [6, 7], "BBC reports Australia set up a taskforce of 12 agencies after the "
                                                   "AI breach.", "Taxpayers now fund the clean-up"),
                    _kat("VERDICT", [3, 4], "Transformer News reports the AI company published a pro-disclosure "
                                            "rule while silent about Australia.",
                         "Within a year another country will set a reporting clock for AI agent incidents",
                         zalozenie="regulators copy Australia", sprawdzian={"kiedy": "2027-12-31", "co": "a second law"}),
                    _kat("MOTIVE", [7], "The prime minister promised legal consequences, the BBC reports.",
                         "The company bet that victims would rather stay quiet", zalozenie="victims fear publicity"),
                    _kat("KURIOZUM", [1], "Old tag from the old menu.", "Old menus are gone"),
                    _kat("MOTIVE", [3], "The company is surely hiding more.", "They are nearly certainly hiding more",
                         zalozenie="x")]}
    llm.call = lambda purpose, system, user, **kw: json.dumps(KATY_ODP if purpose.startswith("przeslania")
                                                              else {"pary": []})
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        pr5 = sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA6, {}, DUZA, ile=5)
    sprawdz("piec katow w kolejnosci regul: prowadzacy, potem najsilniejszy, werdykt trzeci, nie ostatni",
            [p["rodzaj"] for p in pr5] == ["REVEAL", "WHO_GAINS_PAYS", "VERDICT", "HOW_IT_WORKS", "MOTIVE"],
            ([p["rodzaj"] for p in pr5], _log.getvalue()[-800:]))
    sprawdz("KONTRDOWOD: tag ze starego menu (KURIOZUM) i asekuracja w analizie odrzucone z nazwanym powodem",
            "unknown angle tag 'KURIOZUM'" in _log.getvalue() and "hedged takeaway ('nearly')" in _log.getvalue(),
            _log.getvalue())
    sprawdz("kat niesie twierdzenia karty z cytatem i adresem, sprawdzona linie i hak",
            pr5[0]["fakty"][0]["evidence"] == "August 11: aware" and pr5[0]["fakty"][0]["nr"] == 2
            and pr5[0]["linia"] == pr5[0]["naglowek"] and pr5[0]["wariant"] == "gated"
            and pr5[0]["hak"] == "detail REVEAL", pr5[0])
    sprawdz("sedno trafia do karty", KARTA6.get("sedno", {}).get("jedno_zdanie", "").startswith("An AI agent"))
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        sprawdz("KONTRDOWOD: karta z czterema twierdzeniami — planista nie wolany, brak serii",
                sledztwo.przeslania(sqlite3.connect(":memory:"), None, KARTA, {}, DUZA) == []
                and "nie wolany" in _log.getvalue())
    # ODMOWA OPUSA (klasyfikator „cyber", 25.10: pierwsza seria to luka PHP2Shell) —
    # te same katy pisze zapas; bez niego sledztwo zapisalo by sie bez katow.

    def _odmowa(purpose, system, user, **kw):
        if purpose == "przeslania":
            raise llm.OdmowaDostawcy("dostawca odmówił: cyber")
        return json.dumps(KATY_ODP if purpose == "przeslania_zapas" else {"pary": []})
    llm.call = _odmowa
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        _zap = sledztwo.przeslania(sqlite3.connect(":memory:"), None, json.loads(json.dumps(KARTA6)), {}, DUZA, ile=5)
    sprawdz("odmowa Opusa: katy pisze zapas (DeepSeek), log to mowi",
            len(_zap) == 5 and "nie dal katow" in _log.getvalue()
            and config.MODEL_FOR.get("przeslania_zapas") == config.DEEPSEEK
            and config.MAX_TOKENS.get("przeslania_zapas"), _log.getvalue()[-300:])

    def _odmowa_obu(purpose, system, user, **kw):
        raise llm.OdmowaDostawcy("dostawca odmówił: cyber")
    llm.call = _odmowa_obu
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("KONTRDOWOD: gdy odmowi tez zapas — pusto, bez wyjatku",
                sledztwo.przeslania(sqlite3.connect(":memory:"), None, json.loads(json.dumps(KARTA6)), {}, DUZA) == [])
    llm.call = lambda purpose, system, user, **kw: json.dumps(ODP[purpose])

    print()
    print("=== 4b. PREMIERA MODELU: TEN SAM MECHANIZM, TYP HISTORII W PROMPCIE (25.10.2026) ===")
    PROMPTY_KATOW = []

    def _premiera(purpose, system, user, **kw):
        PROMPTY_KATOW.append(user)
        return json.dumps(KATY_ODP if purpose.startswith("przeslania") else {"pary": []})
    llm.call = _premiera
    with contextlib.redirect_stdout(io.StringIO()):
        _pr_p = sledztwo.przeslania(sqlite3.connect(":memory:"), None, json.loads(json.dumps(KARTA6)), {}, DUZA,
                                    typ="premiera", ile=5)
    sprawdz("premiera: te same katy z jednej tabeli, prompt mowi, ze to premiera modelu",
            [p["rodzaj"] for p in _pr_p] == [p["rodzaj"] for p in pr5]
            and "a model release" in PROMPTY_KATOW[0] and "- CLAIM_VS_MEASURED —" in PROMPTY_KATOW[0]
            and "- REVEAL —" in PROMPTY_KATOW[0], PROMPTY_KATOW[0][:400] if PROMPTY_KATOW else "")
    _prompty = {n: pathlib.Path("agent-v2/prompts/%s" % n).read_text(encoding="utf-8")
                for n in ("przeslania.md", "notka.md", "pisarz.md")}
    sprawdz("prompty kaza miec zdanie (werdykt bierze strone) i nie zakazuja werdyktu AGI",
            "made up their mind" in _prompty["przeslania.md"] and "taking a side" in _prompty["przeslania.md"]
            and "Have a point of view" in _prompty["notka.md"] and "point of view" in _prompty["pisarz.md"]
            and not any("Never declare AGI" in t for t in _prompty.values())
            and "taking a side" in sledztwo.KATY["VERDICT"]["opis"])
    sprawdz("bez dosłownego przykladu „AGI at maths” w prompcie i opisach katow (spec §3)",
            "AGI at maths" not in _prompty["przeslania.md"]
            and not any("AGI at maths" in k["opis"] for k in sledztwo.KATY.values()))
    sprawdz("granica zostaje: fakty tylko z karty",
            "facts (numbers, quotes, people, dates, events) come only" in _prompty["przeslania.md"].lower())
    # PLAN SLEDZTWA idzie do katow jako nasze myslenie, nie fakty. Od fali 1 (25.10.2026) plan robi
    # `sledztwo_plan.plan_sledztwa` (testy: `tests/test_sledztwo_plan.py`); tu tylko jego ksztalt
    # `plan_do_kart` w karcie katow.
    _plan2 = {"pytania": [{"id": "Q1", "soczewka": "PRACTICAL", "q": "What hardware does it need?"}],
              "wielkie_pytanie": {"pytanie": "Has open caught up?",
                                  "wieksze_niz_wyglada": "Prices fall for everyone.",
                                  "mniejsze_niz_wyglada": "Only one test moved."},
              "rdzen_ai": "Open models close the gap.", "zalozenie_czytelnika": "Closed labs lead."}
    _kp = sledztwo._karta_do_promptu(dict(KARTA, investigation_plan=_plan2))
    sprawdz("plan sledztwa trafia do karty katow jako nasze myslenie (nie fakty), z oboma przypadkami BIG",
            "OUR PLAN BEFORE RESEARCH (our thinking, not facts)" in _kp
            and "Has open caught up?" in _kp and "Only one test moved." in _kp
            and "Prices fall for everyone." in _kp, _kp[:600])
    sprawdz("kazdy tag tabeli ma typ notki i opis; stare menu (KURIOZUM, LICZBY) nie istnieje",
            all(sledztwo.KATY[r]["typ_notki"] in config.NOTE_TYPES and sledztwo.KATY[r]["opis"] for r in sledztwo.KATY)
            and "KURIOZUM" not in sledztwo.KATY and "LICZBY" not in sledztwo.KATY)
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
    # ROZBITA HISTORIA: radar dal jej 2 serwisy, a korpus ma ja w jeszcze 3 (25.10:
    # ta sama luka PHP2Shell raz 10, raz 7 serwisow, zaleznie od losowania radaru).
    H_ROZBITA = _hist(6, "NextDC shares crash", _hosty[:2])
    _stary = (TERAZ - timedelta(days=9)).strftime("%Y-%m-%d")
    KORPUS = [w("Reuters", "https://www.reuters.com/x", "NextDC shares sink 42% on power delay"),
              w("FT", "https://www.ft.com/x", "Why NextDC's fall matters for AI infrastructure"),
              w("Verge", "https://www.theverge.com/x", "NextDC: grid works paused in Melbourne"),
              dict(w("Ars", "https://arstechnica.com/x", "NextDC old story"), data=_stary),
              w("TC", "https://techcrunch.com/x", "NextDCX is another company"),
              w("Wired", "https://www.wired.com/x", "OpenAI ships a new feature")]
    llm.call = lambda purpose, system, user, **kw: json.dumps({"historie": [
        {"nr": 6, "kategoria": "PRACA_EKONOMIA", "zapytanie": "NextDC", "klucze": ["NextDC", "OpenAI"]}]})
    with contextlib.redirect_stdout(io.StringIO()):
        _wyb4, _rank4 = sledztwo.wybierz_historie([H_ROZBITA], korpus=KORPUS)
    sprawdz("rozbita historia dostaje naglowki z korpusu po slowie kluczowym i przechodzi bramke",
            _wyb4 is H_ROZBITA and H_ROZBITA["serwisy"] == 5 and H_ROZBITA["dolaczone"] == 3
            and "+3 z korpusu" in _rank4[0]["powod"], (_rank4, H_ROZBITA.get("serwisy")))
    # PRZEDRUK I PREMIERA (25.10.2026): TechXplore przedrukowal The Conversation pod tym samym
    # tytulem; premiera Kimi K3.1 Pro miala 2 serwisy do pobrania i 3 kanaly YouTube.
    _tyt = "Shares in this data centre company are down 40% as investors lose faith in the AI story"
    H_PRZEDRUK = {"miejsce": 7, "tytul": _tyt, "naglowki": [
        w("Conversation", "https://theconversation.com/a", _tyt),
        w("TechXplore", "https://techxplore.com/a", _tyt.replace("centre", "center")),
        w("NPR", "https://www.npr.org/a", "Oracle's debt is growing and investors are worried"),
        w("Futurism", "https://futurism.com/a", "Banks prepare for an AI catastrophe")]}
    sprawdz("przedruk pod tym samym tytulem to jeden wydawca: 4 hosty, zasieg 3, bramka nie",
            sledztwo.zasieg_historii(H_PRZEDRUK) == 3 and not sledztwo.ocena_historii(H_PRZEDRUK)[0],
            (sledztwo.zasieg_historii(H_PRZEDRUK), sledztwo.ocena_historii(H_PRZEDRUK)))
    H_KIMI = {"miejsce": 8, "tytul": "Introducing Kimi K3.1 Pro", "naglowki": [
        w("Simon Willison", "https://simonwillison.net/k", "Introducing Kimi K3.1 Pro"),
        w("Latent Space", "https://www.latent.space/k", "Kimi 3.1 Pro narrows the closed-AI lead"),
        w("Matt Wolfe", "https://www.youtube.com/watch?v=a", "Open-Source AI Models Caught Up!"),
        w("Matthew Berman", "https://www.youtube.com/watch?v=b", "Kimi K3.1 Invented the Benchmark Scores"),
        w("TheAIGRID", "https://www.youtube.com/watch?v=c", "Kimi K3.1 Just Revealed The Worlds Most Powerful AI")]}
    sprawdz("premiera: zasieg z kanalami YouTube (5), prog premiery 2 serwisy — przechodzi; zwykly prog nie",
            sledztwo.zasieg_historii(H_KIMI) == 5
            and sledztwo.ocena_historii(H_KIMI, sledztwo.MIN_SERWISOW_PREMIERY)[0]
            and not sledztwo.ocena_historii(H_KIMI)[0], sledztwo.ocena_historii(H_KIMI, 2))
    # DETEKTOR DUZYCH HISTORII (25.10.2026): Kimi K3.1 Pro nie weszla do 15 historii radaru.
    KORPUS_W = [w("Simon Willison", "https://simonwillison.net/k", "Introducing Kimi K3.1 Pro"),
                w("Matt Wolfe", "https://www.youtube.com/watch?v=a", "Open-Source AI Models Caught Up! (Kimi K3.1 Pro)"),
                w("Latent Space", "https://www.latent.space/k", "Kimi 3.1 Pro narrows the closed-AI lead"),
                w("Matthew Berman", "https://www.youtube.com/watch?v=b", "Kimi K3.1 Invented the Benchmark Scores"),
                w("BBC", "https://www.bbc.co.uk/php", "What is PHP and why did it spark a scramble?"),
                dict(w("Old", "https://old.example/k", "Kimi K2 from last month"), data=_stary)]
    llm.call = lambda purpose, system, user, **kw: json.dumps({"historie": [
        {"tytul": "Kimi K3.1 Pro release", "nr": [4, 3, 2, 1, 99, "x"]}, {"tytul": "solo", "nr": [5]}]})
    with contextlib.redirect_stdout(io.StringIO()):
        _wh = sledztwo.wielkie_historie(KORPUS_W)
    sprawdz("detektor: historia z numerow naglowkow, serwis do pobrania na czele, smieci i stare pominiete",
            len(_wh) == 1 and len(_wh[0]["naglowki"]) == 4 and "youtube" not in _wh[0]["naglowki"][0]["url"]
            and _wh[0]["miejsce"] == 101 and sledztwo.zasieg_historii(_wh[0]) == 4
            and all("K2" not in n["temat"] for n in _wh[0]["naglowki"]), _wh)
    H_RADAR_KIMI = {"miejsce": 2, "tytul": "Introducing Kimi K3.1 Pro", "naglowki": [KORPUS_W[0]]}
    _sc = sledztwo.scal_historie([H_RADAR_KIMI, H_PRZEDRUK], _wh)
    sprawdz("scalanie: historia detektora ze wspolnym adresem dokleja sie do radarowej, bez dubli",
            len(_sc) == 2 and len(H_RADAR_KIMI["naglowki"]) == 4, [len(h["naglowki"]) for h in _sc])
    _sc2 = sledztwo.scal_historie([H_PRZEDRUK], _wh)
    sprawdz("scalanie: nowa duza historia staje obok radarowych", len(_sc2) == 2 and _sc2[1]["z_detektora"])
    sprawdz("KONTRDOWOD: ogolne slowo (OpenAI), stary naglowek i fragment wyrazu (NextDCX) nie lacza",
            not any("OpenAI ships" in str(n.get("temat")) or "old story" in str(n.get("temat"))
                    or "NextDCX" in str(n.get("temat")) for n in H_ROZBITA["naglowki"]))

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
    sprawdz("nazwy wlasne: tylko wyrozniajace (wielka litera albo cyfra, bez ogolnych)",
            sledztwo.nazwy_wlasne(["safety", "PHP", "OpenAI", "GPT-6", "UK", "hacking", "NextDC", "PHP"])
            == ["PHP", "GPT-6", "NextDC"])
    _siec.zapytania.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        _gl2 = sledztwo.glosy_hn("Model X launch", http=_siec, klucze=["ModelX", "safety"])
    _pytania_hn = [q[1]["query"] for q in _siec.zapytania if q[0] == sledztwo.HN_SZUKAJ]
    class _SiecKiki(_Siec):
        def get(self, url, params=None, timeout=None):
            if url == sledztwo.HN_SZUKAJ:
                return _Odp({"hits": [
                    {"objectID": "9", "title": "Dogs agree that 'bouba' is round and 'kiki' is spiky",
                     "points": 348, "num_comments": 219},
                    {"objectID": "1", "title": "Kimi K3.1 Pro and K3.1 Pro Highspeed", "points": 1065,
                     "num_comments": 654}]})
            return super().get(url, params, timeout)
    with contextlib.redirect_stdout(io.StringIO()):
        _gk = sledztwo.glosy_hn("Kimi K3.1 Pro", http=_SiecKiki(), klucze=["Kimi"])
    sprawdz("KONTRDOWOD: watek bez szukanej nazwy w tytule (literowka „kiki”) odpada",
            [d["url"] for d in _gk] == ["https://news.ycombinator.com/item?id=1"], [d["title"] for d in _gk])
    sprawdz("Hacker News szuka po zapytaniu i nazwach wlasnych, watki bez powtorek",
            _pytania_hn == ["Model X launch", "ModelX"] and len(_gl2) == 2, (_pytania_hn, len(_gl2)))
    with contextlib.redirect_stdout(io.StringIO()):
        _cn = sledztwo.cennik_openrouter("Model X", http=_siec)
    sprawdz("OpenRouter: pasujacy model, cena za milion tokenow, kontekst, podpis posrednika",
            len(_cn) == 1 and "$3.00" in _cn[0]["text"] and "$15.00" in _cn[0]["text"] and "400000" in _cn[0]["text"]
            and "Model Y" not in _cn[0]["text"] and "reseller" in _cn[0]["text"], _cn and _cn[0]["text"])

    # POPULARNE WATKI AI Z HN jako korpus + premia za zainteresowanie (25.10.2026).
    class _SiecPop(_Siec):
        def get(self, url, params=None, timeout=None):
            if url == sledztwo.HN_SZUKAJ and "points>" in str((params or {}).get("numericFilters")):
                return _Odp({"hits": [
                    {"objectID": "7", "title": "Ask HN: If the models are so good, why doesn't OpenAI start 100 companies?",
                     "points": 651, "num_comments": 736, "created_at": "2026-10-24T10:00:00Z", "url": None},
                    {"objectID": "8", "title": "Local Wikipedia for things a half hour walk from you", "points": 1580,
                     "num_comments": 246, "created_at": "2026-10-24T10:00:00Z", "url": "https://x.example/w"}]})
            return super().get(url, params, timeout)
    with contextlib.redirect_stdout(io.StringIO()):
        _pop = sledztwo.popularne_hn(http=_SiecPop())
    sprawdz("popularne watki HN: tylko o AI, z punktami, adres watku gdy brak oryginalu",
            len(_pop) == 1 and _pop[0]["punkty"] == 651 and _pop[0]["url"].endswith("item?id=7")
            and _pop[0]["kanal"] == "Hacker News", _pop)
    import xml.etree.ElementTree as _ET
    _tm = _ET.fromstring('<item><title>Kimi K3.1 Pro draws scrutiny (VentureBeat)</title>'
                         '<link>https://www.techmeme.com/261025/p2#a261025p2</link><description>'
                         '&lt;A HREF="https://venturebeat.com/technology/kimi"&gt;x&lt;/A&gt;</description></item>')
    sprawdz("Techmeme: adres oryginalu z opisu zamiast strony Techmeme",
            kk._link_wpisu(_tm) == "https://venturebeat.com/technology/kimi", kk._link_wpisu(_tm))

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
print("=== 5. KOLEJKA: DO TRZECH KATOW NA DOBE (duzy temat, na_dobe 3) ===")
sprawdz("pusta kolejka — nic", sledztwo.wez_przeslanie() is None)
sprawdz("pusta kolejka — nic nie czeka, mozna badac", sledztwo.czekajace_przeslania() == 0)
sledztwo.dodaj_do_kolejki(pr5, DUZA, KARTA6, run_id=7, poziom={"poziom": "L", "na_dobe": 3})
sprawdz("po sledztwie czeka piec katow", sledztwo.czekajace_przeslania() == 5,
        sledztwo.czekajace_przeslania())
_k0 = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
sprawdz("kat wazny cztery dni i niesie hak do notki",
        all(datetime.fromisoformat(p["wazny_do"]) - datetime.fromisoformat(p["kiedy"])
            == timedelta(days=sledztwo.WAZNOSC_PRZESLANIA_DNI) for p in _k0)
        and sledztwo.WAZNOSC_PRZESLANIA_DNI == 4 and _k0[0]["perspektywa"]["hak"] == "detail REVEAL", _k0[0])
# Sledztwo bierze czolo radaru, ktore tego samego dnia poszlo juz zwykla notka
# (27.09: 11:22 notka o Medicare, 13:11 sledztwo o tym samym).
sprawdz("KONTRDOWOD: w dniu sledztwa przeslanie czeka do jutra", sledztwo.wez_przeslanie() is None)
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
for p in _kol:
    p["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
_td = sledztwo.temat_dnia()
sprawdz("temat dnia dla MYSL: historia serii, a zanim cokolwiek wyszlo — bez naszych notek",
        _td and _td["story"] == DUZA["tytul"] and _td["our_published_notes"] == [], _td)
# MYSL OBOK SERII, NIE O NIEJ (fala 1, 25.10.2026, spec §5 „MYSL"): stages nie wklada juz
# `temat_dnia` do MYSL (w probach powtarzala liczby i wniosek serii). Material MYSL to tematy
# obok i zakaz kluczy serii — testy w `tests/test_notki_sledcze.py`.
_mat_mysli, _zakaz = stages.material_mysli()
sprawdz("MYSL nie dostaje tematu dnia serii; klucze serii sa na liscie zakazanych",
        "temat_dnia" not in _mat_mysli and isinstance(_zakaz, list), (list(_mat_mysli), _zakaz))
p1 = sledztwo.wez_przeslanie()
sprawdz("pierwszy idzie prowadzacy kat serii", (p1 or {}).get("rodzaj") == "REVEAL" and p1["k"] == 1, p1)
fakt, material = sledztwo.material_notki(p1)
sprawdz("notka dostaje przeslanie, hak i twierdzenia sledztwa",
        material["perspective"]["przeslanie"] == pr5[0]["przeslanie"]
        and material["perspective"]["hak"] == "detail REVEAL"
        and material["investigation"]["supporting_claims"] and fakt["url"])
sprawdz("typ notki z rodzaju", p1["typ_notki"] == "CIEKAWOSTKA")


def _wydane(*pary):
    """Dziennik z notkami z przeslan: (identyfikator, kiedy)."""
    (config.DATA_DIR / "dziennik.jsonl").write_text("".join(json.dumps(
        {"rodzaj": "notka", "udane": True, "kiedy": k.isoformat(), "przeslanie_id": i}) + "\n"
        for i, k in pary), encoding="utf-8")


_id = [p["id"] for p in sorted(_k0, key=lambda p: p["k"])]
_wydane((_id[0], TERAZ))
# Proba 25.10: MYSL wziela prognoze kata, ktory mial wyjsc nazajutrz.
_td1 = sledztwo.temat_dnia()
sprawdz("temat dnia niesie tylko katy, ktore juz wyszly (nie zabiera jutrzejszych)",
        _td1["our_published_notes"] == [pr5[0]["przeslanie"]], _td1["our_published_notes"])
p2 = sledztwo.wez_przeslanie()
sprawdz("po jednym dzis — drugi kat jeszcze dzis (k=2)", (p2 or {}).get("rodzaj") == "WHO_GAINS_PAYS", p2)
# Zywy test 25.10: notka ze scenariuszem otworzyla faktem, na ktorym stala notka z ustaleniem.
_wcz = sledztwo.material_notki(p2)[1]["investigation"]["earlier_angles_already_published"]
sprawdz("notka wie, jakie katy tej historii juz wyszly (przeslanie i hak), bez siebie samej",
        [k["angle"] for k in _wcz] == ["REVEAL"] and _wcz[0]["opening_detail"] == "detail REVEAL"
        and _wcz[0]["message"] == pr5[0]["przeslanie"], _wcz)
sprawdz("KONTRDOWOD: katy innej historii i niewydane sie nie licza",
        sledztwo._wczesniejsze_katy({"historia": "Inna historia", "id": "x"}) == []
        and all(k["angle"] != "VERDICT" for k in _wcz))
_wydane((_id[0], TERAZ), (_id[1], TERAZ), (_id[2], TERAZ))
sprawdz("KONTRDOWOD: po trzech dzis — czwarty dopiero jutro", sledztwo.wez_przeslanie() is None)
_wydane((_id[0], TERAZ), (_id[0], TERAZ), (_id[1], TERAZ))
sprawdz("ta sama notka zapisana dwa razy liczy sie raz",
        (sledztwo.wez_przeslanie() or {}).get("rodzaj") == "VERDICT")
_wydane(*((i, TERAZ - timedelta(days=1)) for i in _id[:3]))
p3 = sledztwo.wez_przeslanie()
sprawdz("nazajutrz: czwarty kat serii, a wydane wczoraj nie wracaja", (p3 or {}).get("rodzaj") == "HOW_IT_WORKS", p3)
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
# PRZEBIEG SLEDZTWA (kolejnosc etapow, rekord przed kolejka, brak galezi artykulu, odmowa artykulu
# w trybie testu, --wyslij) sprawdzaja od fali 1 (25.10.2026) testy ZACHOWANIA w
# `tests/test_przebieg_sledztwa.py` — tu staly asercje po tekscie starego `_przebieg_sledztwa`.
_k8 = {"confirmed_claims": [{"claim": "c%d" % i, "url": "https://s%d.example/x" % (i % 5)} for i in range(12)]}
_k4 = {"confirmed_claims": [{"claim": "c%d" % i, "url": "https://s%d.example/x" % i} for i in range(5)]}
# 25.10.2026 (spec §5 „Number of notes", §9 pkt 18): liczba notek z bogactwa sledztwa, nie z samego
# zasiegu i liczby twierdzen — bez zrodla pierwotnego i ksiegi szeroki zasieg nie daje szesciu notek.
_k8p = {"confirmed_claims": [dict(c, klasa="PRIMARY" if i < 2 else "SECONDARY",
                                  claim="c%d at $3 per million tokens" % i if i == 0 else c["claim"])
                             for i, c in enumerate(_k8["confirmed_claims"])]}
sprawdz("ile katow = poziom tematu: bez zrodla pierwotnego 3 (zasieg 9) i 2 (zasieg 5); ze zrodlem i cena 4",
        sledztwo.ile_katow({"serwisy": 9}, _k8) == 3 and sledztwo.ile_katow({"serwisy": 5}, _k8) == 2
        and sledztwo.ile_katow({"serwisy": 9}, _k8p) == 4,
        (sledztwo.ile_katow({"serwisy": 9}, _k8), sledztwo.ile_katow({"serwisy": 5}, _k8),
         sledztwo.ile_katow({"serwisy": 9}, _k8p)))
_katy4 = [{"rodzaj": r} for r in ("REVEAL", "HOW_IT_WORKS", "VERDICT", "MOTIVE")]
sprawdz("temat na artykul: bez ksiegi i zrodel pierwotnych nie; nowe ustalenie samo tez nie (spec §9 pkt 17)",
        not sledztwo.temat_na_artykul({"serwisy": 6}, _k8, {}, _katy4)[0]
        and not sledztwo.temat_na_artykul({"serwisy": 4}, _k4, {"jest": True, "zgodne": True}, _katy4[:2])[0])
sprawdz("pisarz notki dostaje wczesniejsze katy w prompcie",
        "earlier_angles_already_published" in pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8"))
sprawdz("pisarz artykulu dostaje wszystkie katy serii",
        'card["investigation_angles"]' in _art and "investigation_angles" in
        pathlib.Path("agent-v2/prompts/pisarz.md").read_text(encoding="utf-8"))
# D1 fali 1 (25.10.2026): kazdy kat serii pisze Opus — prowadzacy i analiza celem
# `notka_przeslania`, kat faktow celem `notka_przeslania_fakt` (Flash gubil wiernosc w probie).
# Wieczorem 25.10.2026 wlasciciel kazal pisac tanio: oba cele notki serii na Flashu z myslenie.
sprawdz("notke z przeslania pisze tani model (oba cele notki serii), zwykla notka zostaje przy rotacji pisarzy",
        stages.etap_notki_serii({"rodzaj": "VERDICT", "lead": False}) == "notka_przeslania"
        and stages.etap_notki_serii({"rodzaj": "REVEAL", "lead": True}) == "notka_przeslania"
        and stages.etap_notki_serii({"rodzaj": "NUMBER_FELT", "lead": False}) == "notka_przeslania_fakt"
        and config.MODEL_FOR.get("notka_przeslania") == config.DEEPSEEK
        and config.MODEL_FOR.get("notka_przeslania_fakt") == config.DEEPSEEK
        and config.MAX_TOKENS.get("notka_przeslania")
        and (config.DEEPSEEK_MYSLENIE.get("notka_przeslania") or {}).get("type") == "enabled")
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
    if etap.startswith("notka_przeslania"):
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
