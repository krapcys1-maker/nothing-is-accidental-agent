# -*- coding: utf-8 -*-
"""Przebieg sledztwa i artykul tygodnia (fala 1, 25.10.2026).

PO CO. Proby 25.10.2026 na kopii danych pokazaly trzy wady przebiegu:
  (1) pytania planu powstawaly z samych naglowkow, bo zrodla historii pobieralismy
      dopiero po planie;
  (2) proba z `--wyslij` (tak jak zegar) zaplacila 1,98 USD za artykul na Fable,
      bo galaz artykulu stala w srodku sledztwa;
  (3) rekord sledztwa stal za kolejka, wiec wyjatek w kolejce po oplaconym Opusie
      kasowal pamiec i historia wrocilaby nazajutrz do ponownego oplacenia.

Test pilnuje ZACHOWANIA na atrapach `sledztwo_plan`, `research`, `stages` i
`sledztwo` (cudze czesci fali 1 — ich interfejsy z kontraktu, nie z pamieci):
  1. kolejnosc etapow: zrodla PRZED planem, plan z `ledes`, poscig za <=4
     dokumentami (bez exploitow), klasyfikacja wzgledem calej ksiegi, badanie ksiegi
     (6 rund, sufit 0,10 USD), krytyk i dogrywka (2 rundy), karta w trybie sledczym
     i jej sprawdzenie, nowosc, poziom, katy, REKORD PRZED KOLEJKA;
  2. `_przebieg_sledztwa` nigdy nie wola `_napisz_i_zapisz` — takze przy temacie L;
  3. kazdy etap moze pasc, a sledztwo dochodzi do rekordu; za malo na serie: rekord
     jest, kolejki nie ma; wyjatek budzetu po planie: rekord z `przerwane`;
  4. stan po kazdym etapie, raport, `--z-sledztwa` i `--historia`;
  5. artykul tygodnia: kandydat ze sledztwa przed pula, regula §5, ODMOWA W TRYBIE
     TESTU (tryb przebiegu, znacznik kopii, `--bez-artykulu`) bez `_napisz_i_zapisz`.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_przebieg_sledztwa.py
"""
import contextlib
import copy
import inspect
import io
import json
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import db                        # noqa: E402
import llm                       # noqa: E402
import research as _research     # noqa: E402
import korpus_kanalow as _kk     # noqa: E402
import artykul_z_puli as azp     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1500]))


TERAZ = datetime.now(timezone.utc)
DZIS = TERAZ.strftime("%Y-%m-%d")
ZDARZENIA: list = []


def zd(nazwa, **szczegoly):
    ZDARZENIA.append((nazwa, szczegoly))


def nazwy():
    return [n for n, _ in ZDARZENIA]


def gdzie(nazwa, od=0):
    """Indeks pierwszego zdarzenia `nazwa` (od pozycji `od`), albo 10**6."""
    for i, (n, _) in enumerate(ZDARZENIA):
        if i >= od and n == nazwa:
            return i
    return 10 ** 6


def zdarzenia(nazwa):
    return [s for n, s in ZDARZENIA if n == nazwa]


# --- dane: historie, plan, karta (wymyslone, nie z prob) -------------------------

def naglowek(kanal, url, temat):
    return {"kanal": kanal, "url": url, "temat": temat, "data": DZIS, "styk": "branza"}


HISTORIA_A = {"miejsce": 1, "tytul": "Orbit Labs ships Q7 model with an open-weights promise",
              "naglowki": [naglowek("Wydawca A", "https://a.example/q7", "Orbit Labs ships Q7"),
                           naglowek("Wydawca B", "https://b.example/q7-review", "Q7 hands-on review"),
                           naglowek("Wydawca C", "https://c.example/q7-price", "Q7 price per task"),
                           naglowek("Wydawca D", "https://d.example/q7-blocked", "Q7 weights delayed")]}
HISTORIA_B = {"miejsce": 2, "tytul": "City council votes on face scanning in buses",
              "naglowki": [naglowek("Wydawca E", "https://e.example/bus", "Council votes on face scanning")]}
HISTORIA_C = {"miejsce": 101, "tytul": "Chip maker results beat forecasts",
              "naglowki": [naglowek("Wydawca F", "https://f.example/chips", "Chip maker results")]}
KATEGORIE = {1: ("PREMIERA_MODELU", "Orbit Q7", ["Q7", "Orbit"], 7, 4.1),
             2: ("POLITYKA_PRAWO", "bus face scanning", ["Council"], 3, None),
             101: ("FIRMY_WLADZA", "chip results", ["ChipCo"], 5, 2.9)}
SOCZEWKI = ("NEW", "HOW_IT_WORKS", "CLAIM", "NUMBERS", "BIG", "PEOPLE", "TIDBIT", "WATCH")
PLAN = {"pytania": [{"id": "Q%d" % (i + 1), "soczewka": s, "q": "Plan question %d about Q7 (%s)?" % (i + 1, s),
                     "waga": (1, 1, 1, 1, 2, 2, 3, 3)[i], "dowod": "model card table", "gdzie": "model card",
                     "zapytanie": "Orbit Q7 %s" % s.lower()} for i, s in enumerate(SOCZEWKI)],
        "dokumenty": [{"co": "Q7 model card", "kto": "Orbit Labs", "gdzie": "orbit.example"},
                      {"co": "exploit", "kto": "someone", "gdzie": "a code host"},
                      {"co": "Q7 pricing page", "kto": "Orbit Labs", "gdzie": "orbit.example/pricing"},
                      {"co": "Q7 licence", "kto": "Orbit Labs", "gdzie": "orbit.example/licence"},
                      {"co": "fifth document", "kto": "Orbit Labs", "gdzie": "orbit.example/five"}],
        "rdzen_ai": "open models close the gap", "zalozenie_czytelnika": "it is open today",
        "wielkie_pytanie": {"pytanie": "Is open catching closed?", "wieksze_niz_wyglada": "x",
                            "mniejsze_niz_wyglada": "y", "nasz_typ": "bigger", "co_zmieni": "weights"},
        "smaczek": {"co": "verbosity", "gdzie": "evaluator page"}, "termin": [],
        "pominiete_soczewki": [{"soczewka": "POWER", "dlaczego": "no leverage shift"}],
        "odrzucone": [{"q": "What does this change for an ordinary person?", "powod": "swap test 0.81"}],
        "fallback": False, "model": "claude-sonnet-5-5"}
PYTANIA_KRYTYKA = [{"id": "K1", "soczewka": "CLAIM", "q": "Critic: is the benchmark figure second-hand?", "waga": 1,
                    "dowod": "evaluator page", "gdzie": "evaluator", "zapytanie": "Q7 evaluator score"},
                   {"id": "K2", "soczewka": "PRACTICAL", "q": "Critic: what hardware does Q7 need?", "waga": 1,
                    "dowod": "model card", "gdzie": "model card", "zapytanie": "Q7 hardware memory"}]
KARTA = {"working_thesis": "Q7 is open in name only for now", "main_mechanism": "mixture of experts",
         "confirmed_claims": [{"claim": "Claim number %d about Q7." % i, "evidence": "Evidence %d." % i,
                               "url": "https://s%d.example/p%d" % (i % 5, i),
                               **({"klasa": "PRIMARY"} if i < 2 else {})} for i in range(12)],
         "uncertain_claims": [], "not_established": ["release date of weights"]}


# --- atrapy cudzych czesci ---------------------------------------------------------

class AtrapaSledztwo(types.ModuleType):
    SLEDZTW_NA_TYDZIEN = 99
    ARTYKULOW_NA_TYDZIEN = 1
    PRZESLAN_NA_DOBE = 3
    KATY = {"REVEAL": {"typ_notki": "CIEKAWOSTKA", "opis": "", "analiza": False},
            "HOW_IT_WORKS": {"typ_notki": "CIEKAWOSTKA", "opis": "", "analiza": False},
            "PEOPLE": {"typ_notki": "CIEKAWOSTKA", "opis": "", "analiza": False},
            "VERDICT": {"typ_notki": "DYSKUSJA", "opis": "", "analiza": True},
            "MOTIVE": {"typ_notki": "DYSKUSJA", "opis": "", "analiza": True}}

    def __init__(self):
        super().__init__("sledztwo")
        self.reset()

    def reset(self):
        self.rekordy, self.kolejka, self.oznaczone, self.wydane = [], [], [], set()
        self.poziom = {"n_max": 5, "poziom": "L", "W": 7, "C": 12, "H": 5, "Pr": 2, "A": 9, "V": True,
                       "dolar": True, "powod": "atrapa"}
        self.katy = None
        self.pada = {}
        self.zly_kat = None

    def _pada(self, nazwa):
        if nazwa in self.pada:
            raise self.pada[nazwa]

    # wybor
    def ile_sledztw(self, dni=7):
        return 0

    def ile_artykulow(self, dni=7):
        return len(self.oznaczone)

    def czekajace_przeslania(self):
        return 0

    def popularne_hn(self, *a, **k):
        return []

    def historie(self, korpus, conn=None, run_id=None):
        zd("historie")
        return [copy.deepcopy(HISTORIA_A), copy.deepcopy(HISTORIA_B)]

    def wielkie_historie(self, korpus, conn=None, run_id=None):
        return [copy.deepcopy(HISTORIA_C)]

    def scal_historie(self, a, b):
        return list(a) + list(b)

    def wybierz_historie(self, historie, conn=None, run_id=None, korpus=None):
        zd("wybor")
        ranking = []
        for h in historie:
            kat, zap, klu, serw, wynik = KATEGORIE[h["miejsce"]]
            h.update(kategoria=kat, zapytanie=zap, klucze=klu, serwisy=serw)
            r = {"miejsce": h["miejsce"], "tytul": h["tytul"], "ok": wynik is not None, "powod": "atrapa"}
            if wynik is not None:
                h["wynik_wyboru"] = wynik
                r.update(kategoria=kat, wynik=wynik, kara=False)
            ranking.append(r)
        return historie[0], ranking

    def zrodla_historii(self, h):
        return [{"url": w["url"], "host": w["url"].split("/")[2], "title": w["temat"], "publisher": w["kanal"]}
                for w in h.get("naglowki") or []]

    def typ_sledztwa(self, kategoria):
        return "premiera" if kategoria == "PREMIERA_MODELU" else "sledztwo"

    def fakt_z_historii(self, h):
        zd("fakt_z_historii", tytul=h.get("tytul"))
        return {"fact": h.get("tytul"), "url": h["naglowki"][0]["url"], "source_date": DZIS,
                "actually": "", "decision": "", "consequence": "", "wrong_belief": ""}

    def nazwy_wlasne(self, klucze):
        return [k for k in klucze or [] if any(c.isupper() or c.isdigit() for c in k)]

    # glosy i cena
    def glosy_hn(self, zapytanie, klucze=None):
        zd("glosy_hn")
        return [{"url": "https://news.ycombinator.com/item?id=1", "host": "news.ycombinator.com",
                 "publisher": "Hacker News", "title": "HN: Q7", "class": "SECONDARY", "text": "Opinion. " * 40}]

    def cennik_openrouter(self, zapytanie):
        zd("cennik")
        return [{"url": "https://openrouter.ai/models?q=q7", "host": "openrouter.ai", "publisher": "OpenRouter",
                 "title": "listing", "class": "SECONDARY", "text": "Q7 input $1.00 per million. " * 10}]

    # po karcie
    def nowosc(self, conn, run_id, card, h, teksty_zrodel=None):
        zd("nowosc", teksty=len(teksty_zrodel or {}))
        self._pada("nowosc")
        return {"jest": True, "ustalenie": "Combined finding about Q7", "twierdzenia": [1, 3],
                "powod": "two sources", "przebiegi": [True, True]}

    def poziom_tematu(self, h, card, dossier):
        zd("poziom", ksiega=len((dossier or {}).get("ksiega") or []))
        self._pada("poziom")
        return dict(self.poziom)

    def przeslania(self, conn, run_id, card, dossier, h, typ="sledztwo", ile=5, artykulowy=False, plan=None):
        zd("przeslania", ile=ile, artykulowy=artykulowy, plan=plan is not None, typ=typ)
        self._pada("przeslania")
        tw = card["confirmed_claims"]
        card["sedno"] = {"jedno_zdanie": "Q7 is open in name only", "werdykt": "bigger than it looks"}
        card["do_artykulu"] = [{"ustalenie": "Reserved finding about the licence", "fakty": [5]}]

        def kat(rodzaj, q, i, **k):
            return {"rodzaj": rodzaj, "q": q, "wniosek": "Takeaway %s" % rodzaj, "przeslanie": "Takeaway %s" % rodzaj,
                    "naglowek": "Hook %s" % rodzaj, "hak": "detail %s" % rodzaj, "kierunek": "AMPLIFY",
                    "fakty": [{k2: tw[j].get(k2) for k2 in ("claim", "evidence", "url")} for j in (i, i + 1)], **k}
        katy = [kat("REVEAL", "Q1", 0, lead=True), kat("VERDICT", "Q5", 2, zalozenie="weights ship"),
                kat("HOW_IT_WORKS", "Q2", 4), kat("PEOPLE", "Q6", 6)]
        return katy if self.katy is None else self.katy[:]

    # zapis i kolejka
    def zapisz_sledztwo(self, rekord):
        zd("zapisz_sledztwo", run_id=rekord.get("run_id"))
        self.rekordy.append(rekord)

    def dodaj_do_kolejki(self, lista, h, card, run_id=None, poziom=None):
        zd("dodaj_do_kolejki", n=len(lista), run_id=run_id, poziom=(poziom or {}).get("poziom"))
        if self.zly_kat and any(p.get("rodzaj") == self.zly_kat for p in lista):
            raise KeyError(self.zly_kat)
        for p in lista:
            self.kolejka.append({"id": "%s-%s" % (run_id, p.get("rodzaj")), "historia": h.get("tytul"),
                                 "fakty": p.get("fakty") or []})
        return len(lista)

    def oznacz_artykul(self, rid):
        zd("oznacz_artykul", rid=rid)
        self.oznaczone.append(rid)

    def _wydane_przeslania(self):
        return set(self.wydane), 0

    def _kolejka(self):
        return list(self.kolejka)

    # ZASTAPIONE w fali 1 — przebieg nie ma prawa po nie siegac
    def pytania_ciekawosci(self, *a, **k):
        zd("ZAKAZANE:pytania_ciekawosci")
        return [], {}

    def temat_na_artykul(self, *a, **k):
        zd("ZAKAZANE:temat_na_artykul")
        return True, "atrapa"

    def ile_katow(self, *a, **k):
        zd("ZAKAZANE:ile_katow")
        return 5

    @property
    def PYTANIA_PREMIERY(self):
        zd("ZAKAZANE:PYTANIA_PREMIERY")
        return ()

    @property
    def PYTANIE_PIERWOTNE(self):
        zd("ZAKAZANE:PYTANIE_PIERWOTNE")
        return ""


class AtrapaPlanu(types.ModuleType):
    def __init__(self):
        super().__init__("sledztwo_plan")
        self.pada = {}
        self.krytyk_pytania = PYTANIA_KRYTYKA

    def plan_sledztwa(self, conn, run_id, h, pytanie, ledes, typ="sledztwo"):
        zd("plan", ledes=copy.deepcopy(ledes), typ=typ, pytanie=pytanie)
        if "plan" in self.pada:
            raise self.pada["plan"]
        return copy.deepcopy(PLAN)

    def krytyk(self, conn, run_id, h, plan, ksiega, karta=None):
        zd("krytyk", ksiega=len(ksiega or []))
        if "krytyk" in self.pada:
            raise self.pada["krytyk"]
        return {"pytania": copy.deepcopy(self.krytyk_pytania), "uwagi": ["a figure is second-hand"]}

    def pytania_tekstem(self, pytania):
        return "\n".join("- [%s|%s] %s" % (q["id"], q["soczewka"], q["q"]) for q in pytania)

    def plan_do_kart(self, plan):
        return {"pytania": [{"id": q["id"], "soczewka": q["soczewka"], "q": q["q"]} for q in plan["pytania"]],
                "z_modulu": True}


class AtrapaResearch:
    url_key = staticmethod(_research.url_key)

    def __init__(self):
        self.pada = None
        self.koszt = 0.05

    def deepen(self, conn, run_id, question, evidence, corpus, max_rund=None, pytania=None, stop_usd=None):
        zd("deepen", max_rund=max_rund, pytania=[q["id"] for q in pytania or []], stop_usd=stop_usd,
           question=question)
        if self.pada is not None:
            raise self.pada
        ksiega = [{"id": q["id"], "q": q["q"], "soczewka": q["soczewka"], "waga": q.get("waga", 1),
                   "status": "answered" if i < 7 else "open", "odpowiedz": "The company says %s." % q["id"],
                   "kiedy": None, "zrodla": [{"url": "https://s%d.example/x" % (i % 3), "quote": "q"},
                                             {"url": "https://s%d.example/x" % ((i + 1) % 3), "quote": "q"}],
                   "proby": 1} for i, q in enumerate(pytania or [])]
        nowe = {"url": "https://ksiega.example/%s" % len(ZDARZENIA), "publisher": "K", "title": "t",
                "class": "SECONDARY", "excerpts": ["ledger excerpt"], "numbers": []}
        return list(evidence) + [nowe], {
            "question": question, "path": str(config.DATA_DIR / "research" / "dossier.json"),
            "stop_reason": "answered", "cost_usd": self.koszt, "ksiega": ksiega,
            "rundy_ksiegi": [{"id": q["id"], "zapytanie": q.get("zapytanie"), "urls": [], "dodane": 1}
                             for q in (pytania or [])[:2]],
            "assessment": {"questions": [], "hypotheses": []}, "evidence": ["nie-do-stanu"]}

    def dokument(self, conn, run_id, co, kto, gdzie, seen=None):
        zd("dokument", co=co)
        if co == "exploit":
            return [{"url": "https://code.example/x/q7-poc/blob/main/run.py", "host": "code.example"}]
        if "dokument" in (getattr(self, "pada_na", None) or ()):
            raise RuntimeError("dokument padl")
        slug = co.lower().replace(" ", "-")
        return [{"url": "https://orbit.example/docs/%s" % slug, "host": "orbit.example", "title": co,
                 "publisher": kto, "class": "PRIMARY", "note": ""}]

    def stan_ksiegi(self, dossier):
        k = dossier.get("ksiega") or []
        return {"pytan": len(k), "odpowiedziane": sum(1 for e in k if e["status"] == "answered"),
                "czesciowe": 0, "otwarte": sum(1 for e in k if e["status"] == "open"), "nie_teraz": 0,
                "pokrycie_waga12": 1.0}

    def synthesis_question(self, question, dossier):
        return question + "\n\n[BRIEFING BADANIA]"

    def attach(self, card, dossier):
        card["investigation"] = {"stop_reason": dossier.get("stop_reason")}
        return card


DLUGOSCI = {"https://a.example/q7": 5000, "https://b.example/q7-review": 3000, "https://c.example/q7-price": 1000}
BLOKADA = {"https://d.example/q7-blocked"}


class AtrapaStages:
    def __init__(self):
        self.karta = KARTA
        self.pada = {}

    def fetch(self, conn, run_id, sources):
        zd("fetch", urls=[s["url"] for s in sources])
        return [dict(s, text="T" * DLUGOSCI.get(s["url"], 2000)) for s in sources if s["url"] not in BLOKADA]

    def classify(self, conn, run_id, question, corpus):
        zd("classify", question=question, urls=[c["url"] for c in corpus if c.get("text")],
           z_feedu=[c["url"] for c in corpus if c.get("z_zapasu_kanalu")])
        return [{"url": c["url"], "publisher": c.get("publisher"), "title": c.get("title"),
                 "class": c.get("class") or "SECONDARY", "excerpts": ["excerpt from %s" % c["url"]], "numbers": []}
                for c in corpus if c.get("text")]

    def synthesis(self, conn, run_id, question, evidence, tryb="artykul"):
        zd("synthesis", tryb=tryb, question=question)
        if "synthesis" in self.pada:
            raise self.pada["synthesis"]
        return copy.deepcopy(self.karta)

    def sprawdz_karte(self, card, evidence, klucze=None, rekord=None):
        # Przebieg podaje klucze historii (proba 25.10.2026: bez nich PRIMARY bylo niemozliwe).
        zd("sprawdz_karte", evidence=len(evidence), klucze=klucze)
        if "sprawdz_karte" in self.pada:
            raise self.pada["sprawdz_karte"]
        out = dict(card)
        out["sprawdzona_kodem"] = True
        return out

    def fallback_card(self, question, evidence):
        zd("fallback_card")
        return {"working_thesis": question, "confirmed_claims": [], "_fallback": True}

    def discovery(self, *a, **k):
        zd("ZAKAZANE:discovery")
        return []

    def __getattr__(self, nazwa):
        zd("NIEZNANE:stages.%s" % nazwa)
        raise AttributeError(nazwa)


RSS_D = ("<rss><channel><item><title>Q7 weights delayed</title><link>https://d.example/q7-blocked</link>"
         "<description>&lt;p&gt;" + "Orbit Labs said the Q7 weights will follow later. " * 8
         + "&lt;/p&gt;</description></item></channel></rss>")


class AtrapaKorpusu(types.ModuleType):
    NS = _kk.NS
    _link_wpisu = staticmethod(_kk._link_wpisu)
    _pole = staticmethod(_kk._pole)

    def __init__(self):
        super().__init__("korpus_kanalow")

    def korpus_kanalow(self, ile=30):
        return [naglowek("Wydawca A", "https://a.example/q7", "Orbit Labs ships Q7")]

    def _tresc_z_zapasu(self, nazwa):
        return RSS_D if nazwa == "zrodlo:Wydawca D" else ""


SLEDZTWO, PLANY, RESEARCH, STAGES, KORPUS = (AtrapaSledztwo(), AtrapaPlanu(), AtrapaResearch(),
                                              AtrapaStages(), AtrapaKorpusu())
RUN = types.ModuleType("run")
RUN.ZNACZNIK_KOPII_TESTOWEJ = config.DATA_DIR.parent / ("ZNACZNIK_TESTU_%d" % id(RUN))
sys.modules.update({"sledztwo": SLEDZTWO, "sledztwo_plan": PLANY, "korpus_kanalow": KORPUS, "run": RUN})
azp.research, azp.stages = RESEARCH, STAGES

PYTANIA_BRIEFU: list = []


def atrapa_llm(purpose, system, prompt, conn=None, run_id=None, **k):
    zd("llm:" + purpose, prompt=prompt)
    if purpose != "wybor":
        raise AssertionError("niespodziewane platne wywolanie: %s" % purpose)
    q = PYTANIA_BRIEFU.pop(0) if PYTANIA_BRIEFU else "Why did Orbit Labs call Q7 open before shipping weights?"
    return json.dumps({"title": "Q7", "question": q, "sub_questions": [], "search_terms": []})


_prawdziwy_llm = llm.call
llm.call = atrapa_llm
PRAWDZIWE_NAPISZ = azp._napisz_i_zapisz
NAPISANE: list = []
KOD_NAPISZ = [0]


def atrapa_napisz(conn, run_id, brief, card, evidence=None):
    zd("_napisz_i_zapisz")
    NAPISANE.append({"brief": brief, "card": card, "evidence": evidence, "run_id": run_id})
    if isinstance(KOD_NAPISZ[0], BaseException):
        # Jak prawdziwe `_napisz_i_zapisz`: po awarii pisarza przestawia go na Opusa.
        config.MODEL_FOR["write"] = "opus-po-odmowie"
        raise KOD_NAPISZ[0]
    return KOD_NAPISZ[0]


class DoPuli(Exception):
    """Przebieg doszedl do artykulu z puli (`wybierz_fakt`)."""


def atrapa_wybierz_fakt(conn, run_id, ile=8):
    zd("wybierz_fakt")
    raise DoPuli()


azp._napisz_i_zapisz = atrapa_napisz
azp.wybierz_fakt = atrapa_wybierz_fakt


def uruchom(argv, tryb="produkcja", funkcja=None):
    """Jeden przebieg na swiezym wierszu `runs`; oddaje (kod, wydruk, run_id, wyjatek)."""
    conn = db.connect()
    rid = db.start_run(conn, "test-sledztwa", tryb=tryb)
    stary = sys.argv
    sys.argv = ["artykul_z_puli.py"] + list(argv)
    bufor = io.StringIO()
    kod = wyjatek = None
    try:
        with contextlib.redirect_stdout(bufor):
            kod = (funkcja or azp._przebieg)(conn, rid)
    except BaseException as exc:   # noqa: BLE001 — mierzymy, co wylatuje
        wyjatek = exc
    finally:
        sys.argv = stary
    return kod, bufor.getvalue(), rid, wyjatek


def stan_z_dysku(rid):
    return json.loads((config.DATA_DIR / "sledztwa" / ("%s.json" % rid)).read_text(encoding="utf-8"))


def zeruj():
    ZDARZENIA.clear()
    NAPISANE.clear()
    SLEDZTWO.reset()
    PLANY.pada, PLANY.krytyk_pytania = {}, PYTANIA_KRYTYKA
    RESEARCH.pada, RESEARCH.koszt, RESEARCH.pada_na = None, 0.05, ()
    STAGES.karta, STAGES.pada = KARTA, {}
    KOD_NAPISZ[0] = 0
    PYTANIA_BRIEFU.clear()


def zakazane():
    return [n for n in nazwy() if n.startswith(("ZAKAZANE:", "NIEZNANE:", "_napisz_i_zapisz"))
            or (n.startswith("llm:") and n != "llm:wybor")]


print("=== 1. PELNE SLEDZTWO Z --wyslij: KOLEJNOSC ETAPOW, REKORD PRZED KOLEJKA ===")
zeruj()
kod, log, R1, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("przebieg konczy sie kodem 0, bez wyjatku", kod == 0 and exc is None, (kod, exc, log[-1500:]))
fetch_historii = zdarzenia("fetch")[0] if zdarzenia("fetch") else {}
sprawdz("pierwsze pobranie to zrodla historii, PRZED planem",
        fetch_historii.get("urls") == [w["url"] for w in HISTORIA_A["naglowki"]]
        and gdzie("fetch") < gdzie("plan"), ZDARZENIA[:6])
_plan_zd = (zdarzenia("plan") or [{}])[0]
_ledes = _plan_zd.get("ledes") or []
sprawdz("plan dostaje poczatki dwoch najdluzszych zrodel (najdluzsze pierwsze, przyciete)",
        [l["publisher"] for l in _ledes] == ["Wydawca A", "Wydawca B"]
        and all(len(l["lede"]) <= azp.DLUGOSC_LEDE for l in _ledes), _ledes)
sprawdz("plan dostaje typ historii i pytanie glowne", _plan_zd.get("typ") == "premiera"
        and "Orbit Labs" in str(_plan_zd.get("pytanie")), _plan_zd)
_klas = (zdarzenia("classify") or [{}])[0]
sprawdz("strona z 403 wchodzi tekstem z feedu wydawcy (zapas kanalu)",
        "https://d.example/q7-blocked" in (_klas.get("z_feedu") or [])
        and "tekst z feedu wydawcy" in log, _klas.get("z_feedu"))
_dok = zdarzenia("dokument")
sprawdz("poscig za dokumentami: najwyzej 4 z 5 nazwanych", [d["co"] for d in _dok] == [
    d["co"] for d in PLAN["dokumenty"][:4]], _dok)
_pobrane = [u for f in zdarzenia("fetch") for u in f["urls"]]
sprawdz("KONTRDOWOD: adres z exploitem nie jest pobierany, dokumenty firmy sa",
        not any("poc" in u for u in _pobrane) and "https://orbit.example/docs/q7-model-card" in _pobrane
        and "pomijam adres z exploitem" in log, _pobrane)
sprawdz("klasyfikacja wzgledem CALEJ listy pytan planu (pytania_tekstem)",
        all("- [%s|%s]" % (q["id"], q["soczewka"]) in _klas.get("question", "") for q in PLAN["pytania"])
        and gdzie("glosy_hn") < gdzie("classify") and gdzie("cennik") < gdzie("classify"),
        _klas.get("question", "")[:300])
_dp = zdarzenia("deepen")
sprawdz("badanie ksiegi: pytania planu, 6 rund, sufit 0,10 USD",
        len(_dp) == 2 and _dp[0]["pytania"] == [q["id"] for q in PLAN["pytania"]]
        and _dp[0]["max_rund"] == 6 and _dp[0]["stop_usd"] == 0.10, _dp)
sprawdz("krytyk po badaniu, dogrywka TYLKO z jego pytaniami, 2 rundy",
        gdzie("deepen") < gdzie("krytyk") < gdzie("deepen", gdzie("krytyk"))
        and _dp[1]["pytania"] == ["K1", "K2"] and _dp[1]["max_rund"] == 2 and _dp[1]["stop_usd"] == 0.10, _dp)
_syn = (zdarzenia("synthesis") or [{}])[0]
sprawdz("karta w trybie sledczym, z pytaniami planu i krytyka oraz briefingiem badania",
        _syn.get("tryb") == "sledztwo" and "K2" in _syn.get("question", "")
        and "[BRIEFING BADANIA]" in _syn.get("question", ""), _syn)
sprawdz("sprawdz_karte po syntezie, przed nowoscia; nowosc -> poziom -> katy",
        gdzie("synthesis") < gdzie("sprawdz_karte") < gdzie("nowosc") < gdzie("poziom") < gdzie("przeslania"),
        nazwy())
_pr = (zdarzenia("przeslania") or [{}])[0]
sprawdz("katy: ile = min(n_max 5, C/2 = 6), temat L artykulowy, plan przekazany",
        _pr.get("ile") == 5 and _pr.get("artykulowy") is True and _pr.get("plan") is True, _pr)
sprawdz("REKORD PRZED KOLEJKA", gdzie("zapisz_sledztwo") < gdzie("dodaj_do_kolejki") < 10 ** 6, nazwy())
_rek = SLEDZTWO.rekordy[0] if SLEDZTWO.rekordy else {}
sprawdz("rekord: pytania planu (id, soczewka, q) do testu podmiany w kolejnych planach",
        [q["id"] for q in _rek.get("plan_pytania") or []] == [q["id"] for q in PLAN["pytania"]]
        and all(q.get("soczewka") and q.get("q") for q in _rek.get("plan_pytania")), _rek.get("plan_pytania"))
_rank = _rek.get("ranking") or []
sprawdz("rekord: ranking (tytul, kategoria, wynik), przepuszczone pierwsze, kategoria takze odrzuconej",
        [r["tytul"] for r in _rank] == [HISTORIA_A["tytul"], HISTORIA_C["tytul"], HISTORIA_B["tytul"]]
        and _rank[2]["kategoria"] == "POLITYKA_PRAWO" and _rank[2]["wynik"] is None and len(_rank) <= 8, _rank)
sprawdz("rekord: klucze, poziom, stan ksiegi, kandydat na artykul, zrodla historii",
        _rek.get("klucze") == ["Q7", "Orbit"] and (_rek.get("poziom") or {}).get("poziom") == "L"
        and (_rek.get("ksiega_stan") or {}).get("pytan") == 10 and _rek.get("artykul_kandydat") is True
        and len(_rek.get("zrodla") or []) == 4 and _rek.get("seria") is True, _rek)
sprawdz("kolejka: wszystkie katy z poziomem, numer sledztwa", (zdarzenia("dodaj_do_kolejki") or [{}])[0] == {
    "n": 4, "run_id": R1, "poziom": "L"}, zdarzenia("dodaj_do_kolejki"))
sprawdz("NIGDY _napisz_i_zapisz, zadnych zastapionych funkcji, zadnego platnego wywolania poza briefem",
        zakazane() == [] and not NAPISANE and nazwy().count("llm:wybor") == 1, zakazane())
_st = stan_z_dysku(R1)
sprawdz("stan na dysku: ranking, brief, plan, ksiega, sciezka dossier, karta, katy, poziom, dowody",
        all(_st.get(k) for k in ("ranking", "brief", "plan", "sciezka_dossier", "karta", "katy", "poziom",
                                 "evidence"))
        and len(_st["dossier"]["ksiega"]) == 10 and "evidence" not in _st["dossier"], sorted(_st))
sprawdz("stan: kazdy etap z kosztem i czasem, ostatni = kolejka",
        list(_st.get("etapy") or {}) == ["wybor", "brief", "pobranie", "plan", "dokumenty", "glosy", "klasyfikacja",
                                         "ksiega", "krytyk", "karta", "nowosc", "poziom", "katy", "rekord",
                                         "kolejka"] and _st.get("etap") == "kolejka", list(_st.get("etapy") or {}))
sprawdz("karta: plan do katow z modulu planu, sprawdzona kodem, sedno od katow",
        _st["karta"].get("investigation_plan", {}).get("z_modulu") and _st["karta"].get("sprawdzona_kodem")
        and _st["karta"].get("sedno"), sorted(_st["karta"]))
_rap = (config.DATA_DIR / "sledztwa" / ("%s-raport.txt" % R1)).read_text(encoding="utf-8")
sprawdz("raport: ranking, plan z odrzuconymi, dokumenty nazwane/zdobyte, ksiega, krytyk, karta, katy, koszt",
        all(s in _rap for s in ("== 1. RANKING", "odrzucone (test podmiany)", "pominieta soczewka",
                                "DOKUMENTY: NAZWANE 4, ZDOBYTE 3", "== 6. KSIEGA PYTAN", "STARSZY REDAKTOR",
                                "K1 [CLAIM]", "== 8. KARTA: 12 potwierdzonych", "== 9. NOWOSC", "sedno:",
                                "KOSZT I CZAS NA ETAP", "PASS  brak wywolania pisarza",
                                "PASS  pytania waga 1-2", "kandydat na artykul: True")), _rap[:3000])

print()
print("=== 2. BEZ --wyslij: STAN I RAPORT TAK, PAMIEC I KOLEJKA NIE ===")
zeruj()
kod, log, R2, exc = uruchom(["--sledztwo"])
sprawdz("kod 0, rekord i kolejka nietkniete", kod == 0 and exc is None and not SLEDZTWO.rekordy
        and not zdarzenia("dodaj_do_kolejki"), (kod, exc, nazwy()))
sprawdz("stan zapisany jako NIE na serio (nie bedzie kandydatem na artykul)",
        stan_z_dysku(R2).get("na_serio") is False and "katy NIE ida do kolejki" in log)

print()
print("=== 3. ZA MALO NA SERIE: REKORD TAK, KOLEJKA NIE ===")
zeruj()
SLEDZTWO.katy = [{"rodzaj": "REVEAL", "q": "Q1", "wniosek": "one", "fakty": []}]
kod, log, R3, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("jeden kat: rekord zapisany (seria=False), kolejki nie ma, kod 1",
        kod == 1 and len(SLEDZTWO.rekordy) == 1 and SLEDZTWO.rekordy[0]["seria"] is False
        and not zdarzenia("dodaj_do_kolejki") and "za malo katow na serie (1)" in log, (kod, exc, nazwy()))
zeruj()
STAGES.karta = dict(KARTA, confirmed_claims=KARTA["confirmed_claims"][:4])
kod, log, R3b, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("KONTRDOWOD: chuda karta (4 twierdzenia) — Opus od katow nie jest wolany, rekord jest",
        kod == 1 and not zdarzenia("przeslania") and len(SLEDZTWO.rekordy) == 1
        and "katow nie zamawiam" in log, (kod, nazwy()))

print()
print("=== 4. KAZDY ETAP MOZE PASC, SLEDZTWO DOCHODZI DO REKORDU ===")
zeruj()
PLANY.pada = {"plan": RuntimeError("plan padl"), "krytyk": ValueError("zly JSON")}
RESEARCH.pada_na = ("dokument",)
STAGES.pada = {"sprawdz_karte": KeyError("klasa")}
SLEDZTWO.pada = {"nowosc": ValueError("x"), "poziom": TypeError("y")}
kod, log, R4, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("plan, krytyk, sprawdz_karte, nowosc i poziom padaja — przebieg dochodzi do kolejki",
        kod == 0 and exc is None and SLEDZTWO.rekordy and zdarzenia("dodaj_do_kolejki"), (kod, exc, log[-1200:]))
sprawdz("plan zapasowy: linia FALLBACK, badanie dostaje stale pytania z soczewek obowiazkowych",
        "[plan] FALLBACK" in log and zdarzenia("deepen")[0]["pytania"] == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"],
        zdarzenia("deepen"))
sprawdz("poziom zapasowy S: katy dalej zamawiane, ale nie artykulowe",
        (zdarzenia("przeslania") or [{}])[0].get("artykulowy") is False and "zapas S" in log,
        zdarzenia("przeslania"))
sprawdz("karta niesprawdzona kodem jest tak oznaczona i powiedziana w logu",
        stan_z_dysku(R4)["karta"].get("_karta_niesprawdzona") == "KeyError" and "NIESPRAWDZONE" in log)
zeruj()
RESEARCH.pada = RuntimeError("ksiega padla")
kod, log, R4b, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("badanie ksiegi pada — karta z klasyfikacji, rekord i kolejka sa",
        kod == 0 and exc is None and SLEDZTWO.rekordy and "ide z tym, co dala klasyfikacja" in log,
        (kod, exc, log[-800:]))
zeruj()
STAGES.pada = {"synthesis": ValueError("zly JSON")}
kod, log, R4c, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("synteza pada — karta zapasowa (chuda), rekord zapisany, katow nie ma",
        kod == 1 and exc is None and zdarzenia("fallback_card") and SLEDZTWO.rekordy
        and not zdarzenia("przeslania"), (kod, exc, nazwy()))
zeruj()
SLEDZTWO.zly_kat = "PEOPLE"
kod, log, R4d, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("zly kat w kolejce odpada z logiem, reszta wchodzi, rekord przed",
        kod == 0 and [k["id"].split("-")[-1] for k in SLEDZTWO.kolejka] == ["REVEAL", "VERDICT", "HOW_IT_WORKS"]
        and "kat PEOPLE odpada" in log and gdzie("zapisz_sledztwo") < gdzie("dodaj_do_kolejki"),
        (SLEDZTWO.kolejka, log[-600:]))
zeruj()
SLEDZTWO.pada = {"przeslania": RuntimeError("Opus padl")}
kod, log, R4e, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("katy padaja — rekord zapisany, kod 1, bez wyjatku", kod == 1 and exc is None and SLEDZTWO.rekordy,
        (kod, exc))
zeruj()
RESEARCH.pada = llm.BudgetExceeded("limit przebiegu")
kod, log, R4f, exc = uruchom(["--sledztwo", "--wyslij"])
_st4f = stan_z_dysku(R4f)
sprawdz("budzet wyczerpany po planie: wyjatek leci dalej, ale rekord z `przerwane` juz jest",
        isinstance(exc, llm.BudgetExceeded) and SLEDZTWO.rekordy and "BudgetExceeded" in SLEDZTWO.rekordy[0].get(
            "przerwane", "") and "BudgetExceeded" in _st4f.get("przerwane", ""), (exc, SLEDZTWO.rekordy))
sprawdz("i raport z przerwanego sledztwa lezy na dysku",
        "PRZERWANE" in (config.DATA_DIR / "sledztwa" / ("%s-raport.txt" % R4f)).read_text(encoding="utf-8"))
zeruj()
PLANY.pada = {"plan": llm.BudgetExceeded("limit")}
kod, log, R4g, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("KONTRDOWOD: budzet pada juz na planie — historii nie palimy rekordem (prawie nic nie kosztowala)",
        isinstance(exc, llm.BudgetExceeded) and not SLEDZTWO.rekordy, (exc, SLEDZTWO.rekordy))

zeruj()
sys.modules["sledztwo_plan"] = None      # import modulu planu rzuca ImportError
try:
    kod, log, R4h, exc = uruchom(["--sledztwo", "--wyslij"])
finally:
    sys.modules["sledztwo_plan"] = PLANY
_st4h = stan_z_dysku(R4h) if exc is None else {}
sprawdz("BRAK MODULU PLANU: plan zapasowy, lista pytan i plan do katow z przebiegu, sledztwo dochodzi do kolejki",
        kod == 0 and exc is None and "[plan] FALLBACK" in log and not zdarzenia("krytyk")
        and "- [Q1|NEW]" in (zdarzenia("classify") or [{}])[0].get("question", "")
        and [q["id"] for q in _st4h.get("karta", {}).get("investigation_plan", {}).get("pytania", [])]
        == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"] and SLEDZTWO.kolejka, (kod, exc, log[-800:]))
sprawdz("raport proby liczy FALLBACK jako FAIL",
        "FAIL  zero linii FALLBACK" in (config.DATA_DIR / "sledztwa" / ("%s-raport.txt" % R4h)).read_text(
            encoding="utf-8"))

print()
print("=== 5. KRYTYK POMINIETY, GDY BADANIE WYCZERPALO SUFIT ===")
zeruj()
RESEARCH.koszt = 0.12
kod, log, R5, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("krytyk nie jest wolany, dogrywki nie ma, sledztwo idzie dalej",
        kod == 0 and not zdarzenia("krytyk") and len(zdarzenia("deepen")) == 1
        and "pominiety" in stan_z_dysku(R5)["krytyk"], (kod, nazwy()))

print()
print("=== 6. --historia <n> WYMUSZA HISTORIE Z RANKINGU ===")
zeruj()
kod, log, R6, exc = uruchom(["--sledztwo", "--wyslij", "--historia", "2"])
sprawdz("--historia 2: badana historia z miejsca 2, nie zwyciezca rankingu",
        (zdarzenia("fakt_z_historii") or [{}])[0].get("tytul") == HISTORIA_B["tytul"]
        and "WYMUSZONA (--historia 2)" in log, zdarzenia("fakt_z_historii"))
zeruj()
kod, log, R6b, exc = uruchom(["--sledztwo", "--wyslij", "--historia", "7"])
sprawdz("KONTRDOWOD: nieznane miejsce — kod 1, zadnego badania",
        kod == 1 and not zdarzenia("plan") and "nie ma takiej historii" in log, (kod, nazwy()))
zeruj()
kod, log, R6c, exc = uruchom(["--sledztwo", "--historia", "abc"])
sprawdz("KONTRDOWOD: miejsce nie liczba — kod 1", kod == 1 and not zdarzenia("plan"), (kod, log[-300:]))

print()
print("=== 7. --z-sledztwa <run_id>: WZNOWIENIE OD KATOW ===")
zeruj()
SLEDZTWO.pada = {"przeslania": RuntimeError("Opus padl")}
kod, log, R7, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("pierwszy przebieg: rekord tak, katy nie", kod == 1 and len(SLEDZTWO.rekordy) == 1 and not SLEDZTWO.kolejka)
ZDARZENIA.clear()
SLEDZTWO.pada = {}
kod, log, R7w, exc = uruchom(["--sledztwo", "--wyslij", "--z-sledztwa", str(R7)])
sprawdz("wznowienie: tylko poziom, katy, kolejka — zrodla, plan, badanie i karta NIE sa placone drugi raz",
        kod == 0 and exc is None and set(nazwy()) == {"poziom", "przeslania", "dodaj_do_kolejki"}, (kod, exc, nazwy()))
sprawdz("rekord nie dublowany (limit tygodnia liczy rekordy), kolejka pod numerem sledztwa",
        len(SLEDZTWO.rekordy) == 1 and all(k["id"].startswith("%s-" % R7) for k in SLEDZTWO.kolejka)
        and len(SLEDZTWO.kolejka) == 4, (SLEDZTWO.rekordy, SLEDZTWO.kolejka))
_st7 = stan_z_dysku(R7)
sprawdz("stan wie o wznowieniu i nie jest juz przerwany", _st7.get("wznowienia")
        and _st7["wznowienia"][-1]["run_id"] == R7w and _st7.get("kolejka_dodana") == 4)
ZDARZENIA.clear()
kod, log, _, exc = uruchom(["--sledztwo", "--wyslij", "--z-sledztwa", str(R7)])
sprawdz("KONTRDOWOD: drugie wznowienie nie dubluje katow w kolejce",
        kod == 0 and not zdarzenia("dodaj_do_kolejki") and len(SLEDZTWO.kolejka) == 4 and "nie dubluje" in log)
ZDARZENIA.clear()
kod, log, _, exc = uruchom(["--sledztwo", "--wyslij", "--z-sledztwa", str(R7), "--mimo-kolejki"])
sprawdz("--mimo-kolejki dodaje swiadomie", zdarzenia("dodaj_do_kolejki") and len(SLEDZTWO.kolejka) == 8)
kod, log, _, exc = uruchom(["--sledztwo", "--z-sledztwa", "999999"])
sprawdz("KONTRDOWOD: brak stanu — kod 1", kod == 1 and "brak zapisanego stanu" in log, log[-300:])

print()
print("=== 8. OGOLNIKOWE PYTANIE GLOWNE: JEDNA PONOWKA ===")
zeruj()
PYTANIA_BRIEFU[:] = ["What does Q7 really mean for open models?", "Will Q7 weights ship by the promised date?"]
_conn = db.connect()
_rid = db.start_run(_conn, "test-briefu", tryb="produkcja")
with contextlib.redirect_stdout(io.StringIO()):
    _b = azp._brief_sledztwa(_conn, _rid, copy.deepcopy(HISTORIA_A), SLEDZTWO)
_wybor = zdarzenia("llm:wybor")
sprawdz("ogolnik „what does X really mean” -> druga proba, brief bierze druga odpowiedz",
        len(_wybor) == 2 and _b["question"].startswith("Will Q7")
        and _b.get("pytanie_przed_ponowka", "").startswith("What does"), (_b, len(_wybor)))
_drugi = _wybor[1]["prompt"] if len(_wybor) > 1 else ""
sprawdz("ponowka mowi modelowi, co bylo nie tak, PRZED sekcja danych",
        "too generic" in _drugi and _drugi.index("too generic") < _drugi.index("## Supplied finding"),
        _drugi[-600:])
sprawdz("KONTRDOWOD: pierwszy prompt (i artykul z puli) bez dopisku",
        "too generic" not in _wybor[0]["prompt"])
zeruj()
with contextlib.redirect_stdout(io.StringIO()):
    _b = azp._brief_sledztwa(_conn, _rid, copy.deepcopy(HISTORIA_A), SLEDZTWO)
sprawdz("KONTRDOWOD: konkretne pytanie — jedno wywolanie", len(zdarzenia("llm:wybor")) == 1)

print()
print("=== 9. ARTYKUL TYGODNIA: NAJPIERW KANDYDAT ZE SLEDZTWA, ODMOWA W TESCIE ===")
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
zeruj()
kod, log, S1, exc = uruchom(["--sledztwo", "--wyslij"])
sprawdz("przygotowanie: sledztwo produkcyjne z katami", kod == 0 and stan_z_dysku(S1).get("katy"), (kod, exc))
ZDARZENIA.clear()
kod, log, A1, exc = uruchom(["--wyslij"])
_n = NAPISANE[0] if NAPISANE else {}
sprawdz("zegar tygodniowy bierze sledztwo, pula nietknieta", kod == 0 and exc is None and len(NAPISANE) == 1
        and not zdarzenia("wybierz_fakt") and "BIORE sledztwo %s" % S1 in log, (kod, exc, log[-1500:]))
_c = _n.get("card") or {}
sprawdz("pisarz dostaje katy serii, ustalenie dla artykulu NAJPIERW, werdykt jako analize, typ premiery",
        (_c.get("investigation_angles") or [{}])[0].get("rodzaj") == "RESERVED_FOR_ARTICLE"
        and [a["rodzaj"] for a in _c["investigation_angles"][1:]] == ["REVEAL", "VERDICT", "HOW_IT_WORKS", "PEOPLE"]
        and [h["rodzaj"] for h in _c.get("editorial_hypotheses") or []] == ["VERDICT"]
        and _c.get("investigation_type") == "model_release"
        and (_c.get("investigation_finding") or {}).get("claims") == ["Claim number 0 about Q7.",
                                                                      "Claim number 2 about Q7."], _c)
sprawdz("pisarz dostaje dowody sledztwa (bank fragmentow) i numer sledztwa w briefie",
        _n.get("evidence") and (_n.get("brief") or {}).get("sledztwo_run_id") == S1)
sprawdz("po udanym artykule: oznacz_artykul(numer SLEDZTWA) i znak w stanie",
        (zdarzenia("oznacz_artykul") or [{}])[0].get("rid") == S1
        and stan_z_dysku(S1).get("artykul", {}).get("kod") == 0)
ZDARZENIA.clear()
NAPISANE.clear()
kod, log, _, exc = uruchom(["--wyslij"])
sprawdz("drugi zegar w tym samym tygodniu: limit artykulow, nic nie pisze",
        kod == 1 and not NAPISANE and not zdarzenia("wybierz_fakt"), (kod, nazwy()))
SLEDZTWO.oznaczone.clear()
kod, log, _, exc = uruchom(["--wyslij"])
sprawdz("KONTRDOWOD: sledztwo juz wykorzystane — artykul z puli",
        isinstance(exc, DoPuli) and not NAPISANE and "artykul z tego sledztwa juz byl" in log, (exc, log[-800:]))

zeruj()
kod, log, S2, exc = uruchom(["--sledztwo", "--wyslij"])
ZDARZENIA.clear()
kod, log, _, exc = uruchom(["--wyslij"], tryb="test")
sprawdz("TRYB TEST: „ARTICLE SKIPPED (test)”, kod 1, bez _napisz_i_zapisz i bez puli",
        kod == 1 and exc is None and "ARTICLE SKIPPED (test)" in log.splitlines() and not NAPISANE
        and not zdarzenia("wybierz_fakt") and not zdarzenia("_napisz_i_zapisz"), (kod, exc, log[-600:]))
sprawdz("tryb test pokazuje za darmo, co zegar by wybral (podglad kandydata)",
        "[kandydat %s]" % S2 in log and "NADAJE SIE" in log, log[-800:])
RUN.ZNACZNIK_KOPII_TESTOWEJ.write_text("kopia", encoding="utf-8")
kod, log, _, exc = uruchom(["--wyslij"], tryb="produkcja")
sprawdz("ZNACZNIK KOPII TESTOWEJ: odmowa takze przy przebiegu produkcyjnym",
        kod == 1 and "ARTICLE SKIPPED (test)" in log and "kopia testowa" in log and not NAPISANE, (kod, log[-400:]))
RUN.ZNACZNIK_KOPII_TESTOWEJ.unlink()
kod, log, _, exc = uruchom(["--wyslij", "--bez-artykulu"], tryb="produkcja")
sprawdz("--bez-artykulu: odmowa", kod == 1 and "ARTICLE SKIPPED (test)" in log and not NAPISANE, (kod, log[-400:]))
(config.DATA_DIR / "karta_do_zatwierdzenia.json").write_text(json.dumps(
    {"card": KARTA, "brief": {"title": "t", "question": "q"}}), encoding="utf-8")
kod, log, _, exc = uruchom(["--z-karty", "--do-karty", "--wyslij"], tryb="test")
sprawdz("--z-karty w trybie test: odmowa (takze z --do-karty obok)",
        kod == 1 and "ARTICLE SKIPPED (test)" in log and not NAPISANE, (kod, log[-400:]))
ZDARZENIA.clear()
_conn = db.connect()
_rid_t = db.start_run(_conn, "test-pisarza", tryb="test")
_kod = _wyj = None
with contextlib.redirect_stdout(io.StringIO()) as _bufor:
    try:
        _kod = PRAWDZIWE_NAPISZ(_conn, _rid_t, {"title": "t", "question": "q"}, copy.deepcopy(KARTA))
    except Exception as _e:   # noqa: BLE001 — atrapa `stages` krzyczy na kazdy etap
        _wyj = _e
sprawdz("prawdziwe _napisz_i_zapisz w trybie test: odmowa PRZED pierwszym etapem (stages nietkniete)",
        _kod == 1 and _wyj is None and "ARTICLE SKIPPED (test)" in _bufor.getvalue() and ZDARZENIA == [],
        (_kod, _wyj, ZDARZENIA))

# swiezy kandydat S2 jest nadal wolny — stan za stary
_plik_s2 = config.DATA_DIR / "sledztwa" / ("%s.json" % S2)
_s2 = json.loads(_plik_s2.read_text(encoding="utf-8"))
_kiedy_s2 = _s2["kiedy"]
_s2["kiedy"] = (TERAZ - timedelta(days=6)).isoformat()
_plik_s2.write_text(json.dumps(_s2), encoding="utf-8")
kod, log, _, exc = uruchom(["--wyslij"])
sprawdz("stan sprzed 6 dni nie jest kandydatem — artykul z puli",
        isinstance(exc, DoPuli) and not NAPISANE and "stan sprzed 6" in log, (exc, log[-600:]))
_s2["kiedy"] = _kiedy_s2
_plik_s2.write_text(json.dumps(_s2), encoding="utf-8")
KOD_NAPISZ[0] = llm.OdmowaDostawcy("cyber")
_pisarz = config.MODEL_FOR.get("write")
kod, log, _, exc = uruchom(["--wyslij"])
sprawdz("odmowa pisarza przy sledztwie: tydzien dostaje artykul z puli, sledztwo oznaczone",
        isinstance(exc, DoPuli) and len(NAPISANE) == 1 and stan_z_dysku(S2).get("artykul", {}).get("kod") == "odmowa",
        (exc, log[-600:]))
sprawdz("artykul z puli po odmowie idzie na pisarzu wlasciciela, nie na zapasie",
        config.MODEL_FOR.get("write") == _pisarz, config.MODEL_FOR.get("write"))
config.MODEL_FOR["write"] = _pisarz
KOD_NAPISZ[0] = 0
zeruj()
kod, log, S3, exc = uruchom(["--sledztwo", "--wyslij"])
ZDARZENIA.clear()
kod, log, _, exc = uruchom([])
sprawdz("bez --wyslij: artykul ze sledztwa na dysk, bez oznaczania (zegar z --wyslij wezmie go dalej)",
        kod == 0 and len(NAPISANE) == 1 and not zdarzenia("oznacz_artykul") and not stan_z_dysku(S3).get("artykul"),
        (kod, nazwy()))

print()
print("=== 10. REGULA §5 NA ZAPISANYM STANIE ===")
BAZA = stan_z_dysku(S3)
_ok, _braki, _miary = azp._ocena_kandydata(BAZA)
sprawdz("stan wzorcowy: nadaje sie (L, 12 twierdzen z 5 serwisow, Pr 2, ksiega 9, werdykt)", _ok, (_braki, _miary))


def bez(zmiana, w_tescie=False, uzyte=None):
    s = copy.deepcopy(BAZA)
    zmiana(s)
    return azp._ocena_kandydata(s, w_tescie=w_tescie, uzyte=uzyte)


def _ustaw(s, sciezka, wartosc):
    cel = s
    for k in sciezka[:-1]:
        cel = cel[k]
    cel[sciezka[-1]] = wartosc


PRZYPADKI = [
    ("poziom M", lambda s: _ustaw(s, ("poziom", "poziom"), "M"), "poziom M"),
    ("9 twierdzen", lambda s: _ustaw(s, ("karta", "confirmed_claims"), s["karta"]["confirmed_claims"][:9]),
     "9 twierdzen"),
    ("3 serwisy", lambda s: [c.update(url="https://s%d.example/q" % (i % 3)) for i, c in
                             enumerate(s["karta"]["confirmed_claims"])], "z 3 serwisow"),
    ("1 rekord pierwotny", lambda s: _ustaw(s, ("poziom", "Pr"), 1), "1 rekordow"),
    ("5 odpowiedzi", lambda s: [e.update(status="open") for e in s["dossier"]["ksiega"][5:]], "5 pytan ksiegi"),
    ("bez werdyktu", lambda s: _ustaw(s, ("katy",), [k for k in s["katy"] if k["rodzaj"] != "VERDICT"]), "werdyktu"),
    ("werdykt na otwartym pytaniu", lambda s: [e.update(status="open") for e in s["dossier"]["ksiega"]
                                               if e["id"] == "Q5"], "werdyktu"),
    ("werdykt na jednym zrodle", lambda s: [e.update(zrodla=e["zrodla"][:1]) for e in s["dossier"]["ksiega"]],
     "werdyktu"),
    ("tryb test", lambda s: _ustaw(s, ("tryb",), "test"), "trybie test"),
    ("bez --wyslij", lambda s: _ustaw(s, ("na_serio",), False), "bez --wyslij"),
    ("6 dni", lambda s: _ustaw(s, ("kiedy",), (TERAZ - timedelta(days=6)).isoformat()), "sprzed 6"),
    ("przerwane", lambda s: _ustaw(s, ("przerwane",), "BudgetExceeded"), "przerwane"),
]
for opis, zmiana, oczekiwane in PRZYPADKI:
    _ok, _braki, _ = bez(zmiana)
    sprawdz("KONTRDOWOD: %s -> nie nadaje sie" % opis, not _ok and any(oczekiwane in b for b in _braki), _braki)
_ok, _braki, _ = bez(lambda s: _ustaw(s, ("tryb",), "test"), w_tescie=True)
sprawdz("w_tescie liczy sama tresc (rekord, podglad proby) — tryb nie przeszkadza", _ok, _braki)
_uzyte = {azp._norm(c["claim"]) for c in BAZA["karta"]["confirmed_claims"][:9]}
_ok, _braki, _m = bez(lambda s: None, uzyte=_uzyte)
sprawdz("tylko 3 twierdzenia spoza wydanych notek -> nie (regula 40%)",
        not _ok and any("spoza wydanych" in b for b in _braki) and _m.get("swieze") == 3, (_braki, _m))
_ok, _braki, _ = bez(lambda s: None, uzyte={azp._norm(c["claim"]) for c in BAZA["karta"]["confirmed_claims"][:8]})
sprawdz("4 swieze twierdzenia wystarcza", _ok, _braki)

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
(config.DATA_DIR / "sledztwa").mkdir(parents=True)


def zapisz_kandydata(rid, poziom, w, nowosc=False):
    s = copy.deepcopy(BAZA)
    s["run_id"], s["poziom"]["poziom"], s["poziom"]["W"] = rid, poziom, w
    s["nowosc"] = {"jest": nowosc}
    s.pop("artykul", None)
    (config.DATA_DIR / "sledztwa" / ("%s.json" % rid)).write_text(json.dumps(s), encoding="utf-8")


zapisz_kandydata(501, "L", 9)
zapisz_kandydata(502, "XL", 5)
with contextlib.redirect_stdout(io.StringIO()):
    _w = azp._kandydat_ze_sledztwa()
sprawdz("wybor: XL przed L, nawet przy mniejszej wielkosci", (_w or {}).get("run_id") == 502, _w and _w.get("run_id"))
(config.DATA_DIR / "sledztwa" / "502.json").unlink()
zapisz_kandydata(503, "L", 7)
with contextlib.redirect_stdout(io.StringIO()):
    _w = azp._kandydat_ze_sledztwa()
sprawdz("wybor: przy tym samym poziomie wieksza historia", (_w or {}).get("run_id") == 501)
zapisz_kandydata(504, "L", 7, nowosc=True)
with contextlib.redirect_stdout(io.StringIO()):
    _w = azp._kandydat_ze_sledztwa()
sprawdz("wybor: nowe ustalenie podnosi priorytet przed wielkoscia (ale nie zastepuje progu)",
        (_w or {}).get("run_id") == 504)

print()
print("=== 11. W PRZEBIEGU SLEDZTWA NIE MA GALEZI ARTYKULU (kod zrodlowy) ===")
_kod_sl = "\n".join(inspect.getsource(f) for f in (azp._przebieg_sledztwa, azp._badanie_sledztwa,
                                                    azp._katy_serii, azp._wznow_sledztwo))
_kod_sl = "\n".join(l for l in _kod_sl.splitlines() if not l.lstrip().startswith("#"))
for zakaz in ("_napisz_i_zapisz", "temat_na_artykul", "oznacz_artykul", "pytania_ciekawosci",
              "PYTANIA_PREMIERY", "PYTANIE_PIERWOTNE", "discovery("):
    sprawdz("sledztwo nie zawiera `%s`" % zakaz, zakaz not in _kod_sl)
SLEDZTWO.poziom = dict(SLEDZTWO.poziom, poziom="XL", n_max=6)
zeruj()
SLEDZTWO.poziom = dict(SLEDZTWO.poziom, poziom="XL", n_max=6)
kod, log, _, exc = uruchom(["--sledztwo", "--wyslij", "--mimo-limitu"])
sprawdz("temat XL z nowym ustaleniem i --wyslij: nadal zero wywolan pisarza",
        kod == 0 and not NAPISANE and not zdarzenia("_napisz_i_zapisz"), (kod, exc, nazwy()))

llm.call = _prawdziwy_llm
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
