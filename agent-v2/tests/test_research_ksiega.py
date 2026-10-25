# -*- coding: utf-8 -*-
"""Ksiega pytan sledztwa, poscig za dokumentem pierwotnym i dlugie dokumenty (25.10.2026).

PO CO. Proby sledcze 25.10: w trzech z czterech badanie wracalo do tego samego pytania
(Kimi K3.1 Pro: runda 3 = runda 2, ten sam dokument pobrany drugi raz pod „www."),
widok 60 tys. znakow chowal fragmenty z pozniejszych rund, ocena dziesieciu pytan nie
miescila sie w limicie tokenow, oryginalne ujawnienie luki przepadlo na 403, a okladka
raportu MFW zjadala caly limit dokumentu. Test pilnuje, kazde z kontrdowodem:
  1. ksiega z 12 pytaniami: paczki po 5, cytaty {source_id, excerpt_index} sprawdzane kodem;
  2. wybor rundy: waga, niepokryta soczewka, Q0 na koncu; jedno pytanie najwyzej dwa razy,
     drugi raz tylko po fragmentach i innym zapytaniu; stop po dwoch pustych rundach;
  3. ucieta odpowiedz -> ta sama paczka po 3, badanie idzie dalej; dwa przejscia bez
     jednej udanej paczki -> koniec; budzet przechodzi wyzej;
  4. widok rundy: nowe fragmenty najpierw; www-kopia i archiwa nie wchodza;
  5. nakladka `assessment`, `synthesis_question`, `attach` (max 3 braki), `stan_ksiegi`,
     wpis „znajdz oryginal", ksiega z poprzedniej ksiegi (pytania krytyka);
  6. `dokument`: tylko adres z wynikow wyszukiwarki i tylko sam dokument, nigdy wyjatek;
  7. dlugi dokument: kawalki wedlug pytania; cytat przez „[...]" odpada; tryb artykulu
     z puli bez zmian.

BEZ PYTESTA, bez sieci, bez platnych wywolan (atrapy `llm.call` i `stages.fetch`).
Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_research_ksiega.py
"""
import contextlib
import io
import json
import pathlib
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm        # noqa: E402
import research   # noqa: E402
import stages     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# ------------------------------------------------------------------ dane (z prob 25.10)
BLOG = "https://kimi.ai/blog/kimi-k3-1-pro"
AA = "https://artificialanalysis.ai/articles/kimi-k3-1-pro-launch-benchmarks"
SW = "https://simonwillison.net/2026/Oct/23/kimi-k31-pro/"
HF = "https://huggingface.co/moonshotai/Kimi-K3.1-Pro"
NEWS = "https://newmoney.example/data-centre-debt"
FBLOG = "The model scores 65.7% on Terminal-Bench 4.0, narrowly behind Claude Opus 5.5 (66.4%)."
FAA = "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%"
FSW = "it's not yet open weights, but Moonshot promise 'Full model weights will be released by Nov 4, 2026'"
FHF = "The repository lists 2.8T total parameters with 104B active per token."
FNEWS = "The Bank of England estimated in its report that 40% of the new debt sits with private credit funds."


def zrodlo(url, fragment, klasa="SUPPORTING", tytul="Page"):
    return {"url": url, "host": research.urlsplit(url).hostname, "title": tytul,
            "publisher": research.urlsplit(url).hostname, "class": klasa,
            "excerpts": [fragment], "numbers": [], "relevance": 1.0}


DOWODY = [zrodlo(BLOG, FBLOG, "PRIMARY", "Kimi K3.1 Pro"), zrodlo(AA, FAA), zrodlo(SW, FSW)]
KORPUS = [{"url": BLOG, "text": FBLOG}, {"url": AA, "text": FAA}, {"url": SW, "text": FSW}]
SOCZEWKI = ["NEW", "HOW_IT_WORKS", "BIG", "TIDBIT", "CLAIM", "NUMBERS", "PRACTICAL",
            "PEOPLE", "POWER", "CONSEQUENCES", "PRECEDENT", "WATCH"]


def pytanie(i, soczewka=None, waga=None, zapytanie=None):
    return {"id": "Q%d" % i, "soczewka": soczewka or SOCZEWKI[(i - 1) % 12],
            "q": "Question %d about Kimi K3.1 Pro?" % i,
            "waga": waga or (1 if i <= 4 else 2 if i <= 8 else 3),
            "dowod": "evidence %d" % i, "gdzie": "model card",
            "zapytanie": zapytanie if zapytanie is not None else "kimi k3.1 pro query %d" % i}


def widok_z_promptu(prompt):
    return json.loads(prompt.split("Passages:\n", 1)[1].split("\n\nQuestions (", 1)[0])


def pytania_z_promptu(prompt):
    czesc = prompt.split("what we already know):\n", 1)[1]
    return json.loads(czesc.split("\n\nReturn only", 1)[0])


def cytuj(widok, fraza):
    for s in widok:
        for e in s["excerpts"]:
            if fraza in e["text"]:
                return {"source_id": s["source_id"], "excerpt_index": e["excerpt_index"]}
    return None


class Atrapa:
    """`llm.call` i `stages.fetch` bez sieci. Ksiege odpowiada funkcja `self.ksiega`
    (pytania, widok) -> {id: wpis}; reszta celow bierze odpowiedzi z kolejek."""

    def __init__(self):
        self.wywolania, self.pobrane = [], []
        self.ksiega = lambda pytania, widok: {}
        self.kolejki = {"investigation_search": [], "investigation_extract": [],
                        "investigation_document": []}
        self.teksty = {}

    def call(self, purpose, system, prompt, conn=None, run_id=None, web_search=False,
             collect_urls=None):
        self.wywolania.append((purpose, prompt))
        conn.execute("INSERT INTO calls VALUES (?,?,?)", (run_id, purpose, .001))
        if purpose == "ksiega":
            pytania, widok = pytania_z_promptu(prompt), widok_z_promptu(prompt)
            wynik = self.ksiega(pytania, widok)
            if isinstance(wynik, BaseException):
                raise wynik
            out = []
            for p in pytania:
                w = dict((wynik or {}).get(p["id"]) or {"status": "open"})
                fraza = w.pop("fraza", None)
                if fraza:
                    c = cytuj(widok, fraza)
                    w.setdefault("cites", [c] if c else [])
                out.append({"id": p["id"], **w})
            return json.dumps({"questions": out})
        kolejka = self.kolejki[purpose]
        if not kolejka:
            raise AssertionError("nieoczekiwane platne wywolanie: " + purpose)
        odpowiedz, urls = kolejka.pop(0)
        if isinstance(odpowiedz, BaseException):
            raise odpowiedz
        if collect_urls is not None:
            collect_urls.extend(urls)
        return json.dumps(odpowiedz)

    def fetch(self, conn, run_id, zrodla):
        self.pobrane.append([z["url"] for z in zrodla])
        return [{**z, "text": self.teksty[z["url"]]} for z in zrodla if z["url"] in self.teksty]

    def runda(self, url, fragment, tekst=None, odpowiada=False):
        """Jedna udana runda: szukanie -> `url`, wyciag -> `fragment`."""
        self.teksty[url] = tekst or fragment
        self.kolejki["investigation_search"].append(({"sources": [{"url": url}]}, [url]))
        self.kolejki["investigation_extract"].append(({"documents": [{
            "source_id": 1, "class": "SUPPORTING", "answers_question": odpowiada,
            "excerpts": [fragment], "numbers": []}]}, []))

    def pusta(self, url="https://nothing.example/x"):
        self.kolejki["investigation_search"].append(({"sources": []}, [url]))

    def ile(self, purpose):
        return sum(1 for p, _ in self.wywolania if p == purpose)


A = None
CONN = None
_oryginal_call, _oryginal_fetch = llm.call, stages.fetch


def nowy():
    """Swieza atrapa, baza kosztow i katalog danych (bez pamieci podrecznej z innych scen)."""
    global A, CONN
    A = Atrapa()
    CONN = sqlite3.connect(":memory:")
    CONN.execute("CREATE TABLE calls (run_id INTEGER, purpose TEXT, cost_usd REAL)")
    config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
    llm.call = A.call
    stages.fetch = A.fetch
    return A


def badaj(pytania, max_rund=0, dowody=None, korpus=None, stop_usd=None, pytanie_glowne=None):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        ev, d = research.deepen(CONN, 1, pytanie_glowne or "Did Kimi K3.1 Pro catch up with closed models?",
                                list(DOWODY if dowody is None else dowody),
                                list(KORPUS if korpus is None else korpus),
                                max_rund=max_rund, pytania=pytania, stop_usd=stop_usd)
    return ev, d, log.getvalue()


config.RESEARCH_ENABLED = True
config.RESEARCH_STOP_USD = 0.15

try:
    print("=== 1. KSIEGA Z 12 PYTANIAMI: PACZKI PO 5, CYTATY SPRAWDZA KOD ===")
    nowy()
    A.ksiega = lambda pytania, widok: {
        "Q1": {"status": "answered", "answer": "The company says it trails Opus 5.5.", "fraza": "65.7%"},
        "Q2": {"status": "partial", "answer": "Artificial Analysis measured 67%.", "fraza": "highest score"},
        "Q3": {"status": "not_yet", "answer": "Moonshot promises weights by Nov 4.", "when": "2026-11-04",
               "fraza": "Nov 4, 2026"},
        "Q4": {"status": "answered", "answer": "Bogus.", "cites": [{"source_id": 99, "excerpt_index": 0}]},
        "Q5": {"status": "answered", "answer": "No citation given.", "cites": []},
        "Q6": {"status": "answered", "answer": "Wrong index.", "cites": [{"source_id": 1, "excerpt_index": 7}]},
        "Q7": {"status": "not_yet", "answer": "Already past.", "when": "2026-01-01", "fraza": "Nov 4, 2026"},
        "Q8": {"status": "answered", "answer": "", "fraza": "65.7%"},
        "Q9": {"status": "answered", "answer": "Index as text.", "cites": [{"source_id": "2", "excerpt_index": "0"}]},
        "Q10": {"status": "open", "answer": "", "next_query": "Kimi K3.1 Pro licence text"},
    }
    ev, d, log = badaj([pytanie(i) for i in range(1, 13)], max_rund=0)
    ks = {w["id"]: w for w in d["ksiega"]}
    rozmiary = [len(pytania_z_promptu(p)) for c, p in A.wywolania if c == "ksiega"]
    sprawdz("12 pytan planu + Q0 = 13 wpisow, Q0 na koncu",
            len(d["ksiega"]) == 13 and d["ksiega"][-1]["id"] == "Q0", [w["id"] for w in d["ksiega"]])
    sprawdz("Q0 to pierwszy akapit pytania glownego",
            ks["Q0"]["q"] == "Did Kimi K3.1 Pro catch up with closed models?", ks["Q0"]["q"])
    sprawdz("trzy paczki: 5, 5, 3", rozmiary == [5, 5, 3], rozmiary)
    sprawdz("odpowiedziane z cytatem — cytat to caly fragment spod tego adresu",
            ks["Q1"]["status"] == "answered" and ks["Q1"]["zrodla"] == [{"url": BLOG, "quote": FBLOG}],
            ks["Q1"])
    sprawdz("czesciowe zostaje czesciowym, z odpowiedzia",
            ks["Q2"]["status"] == "partial" and ks["Q2"]["odpowiedz"].startswith("Artificial"), ks["Q2"])
    sprawdz("not_yet z cytatem i przyszla data", ks["Q3"]["status"] == "not_yet"
            and ks["Q3"]["kiedy"] == "2026-11-04", ks["Q3"])
    for ident, powod in (("Q4", "zrodlo spoza widoku"), ("Q5", "bez cytatu"),
                         ("Q6", "indeks spoza zrodla"), ("Q7", "data juz minela"),
                         ("Q8", "pusta odpowiedz")):
        sprawdz("KONTRDOWOD %s (%s) -> open, bez odpowiedzi i zrodel" % (ident, powod),
                ks[ident]["status"] == "open" and not ks[ident]["odpowiedz"] and not ks[ident]["zrodla"],
                ks[ident])
    sprawdz("source_id i excerpt_index jako tekst cyfr tez sa cytatem",
            ks["Q9"]["status"] == "answered" and ks["Q9"]["zrodla"][0]["url"] == AA, ks["Q9"])
    sprawdz("next_query zapisany dla otwartego", ks["Q10"]["next_query"] == "Kimi K3.1 Pro licence text")
    sprawdz("zero rund przy max_rund=0", d["stop_reason"] == "round_limit" and not d["rundy_ksiegi"],
            d["stop_reason"])
    prompt0 = next(p for c, p in A.wywolania if c == "ksiega")
    sprawdz("fragmenty w prompcie maja jawny excerpt_index",
            '"excerpt_index": 0' in prompt0 and FBLOG in prompt0)
    sprawdz("fragmenty stoja PRZED pytaniami (wspolny poczatek paczek)",
            prompt0.index("Passages:") < prompt0.index("Questions (id"))
    st = research.stan_ksiegi(d)
    sprawdz("stan_ksiegi liczy statusy (bez wpisow pochodnych)",
            (st["pytan"], st["odpowiedziane"], st["czesciowe"], st["nie_teraz"], st["otwarte"])
            == (13, 2, 1, 1, 9), st)
    # wagi 1-2: Q1..Q8 + Q0 = 9, bez Q3 (not_yet) = 8; pokryte Q1, Q2 -> 0,25
    sprawdz("pokrycie wag 1-2 bez pytan not_yet w mianowniku", st["pokrycie_waga12"] == 0.25, st)
    zapis = json.loads(pathlib.Path(d["path"]).read_text(encoding="utf-8"))
    sprawdz("dossier zapisany z ksiega i nakladka", len(zapis["ksiega"]) == 13
            and "questions" in zapis["assessment"] and "-ksiega-" in d["path"], d["path"])

    print()
    print("=== 2. KTORE PYTANIE DOSTAJE RUNDE ===")
    nowy()
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "answered", "answer": "The company says X.",
                                              "fraza": "65.7%"}}
    A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "NEW", 1), pytanie(2, "NEW", 1), pytanie(3, "PEOPLE", 2)], max_rund=3)
    sprawdz("soczewka juz pokryta odpowiedzia ustepuje innej, choc ma nizsza wage",
            [r["id"] for r in d["rundy_ksiegi"]][:1] == ["Q3"], d["rundy_ksiegi"])
    nowy()
    A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "NEW", 2), pytanie(2, "PEOPLE", 1)], max_rund=2)
    sprawdz("waga 1 przed waga 2, niezaleznie od kolejnosci w planie",
            [r["id"] for r in d["rundy_ksiegi"]] == ["Q2", "Q1"], d["rundy_ksiegi"])
    nowy()
    A.pusta(); A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "NEW", 2, zapytanie="")], max_rund=3)
    sprawdz("pytanie bez zapytania i bez next_query nie dostaje rundy; Q0 bez zapytania tez",
            not d["rundy_ksiegi"] and d["stop_reason"] == "no_actionable_gap", d["stop_reason"])
    nowy()
    A.ksiega = lambda pytania, widok: {"Q0": {"status": "open", "next_query": "main question query"}}
    A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "NEW", 2)], max_rund=2)
    sprawdz("Q0 z next_query dostaje runde, ale po pytaniu planu o tej samej wadze",
            [r["id"] for r in d["rundy_ksiegi"]] == ["Q1", "Q0"], d["rundy_ksiegi"])

    print()
    print("=== 3. JEDNO PYTANIE NAJWYZEJ DWA RAZY (proba Kimi: runda 3 = runda 2) ===")
    nowy()
    stan = {"runda": 0}

    def ksiega_kimi(pytania, widok):
        ids = [p["id"] for p in pytania]
        if "Q1" in ids and cytuj(widok, "2.8T"):
            # po rundzie: czesciowa odpowiedz i TO SAMO zapytanie innymi znakami
            return {"Q1": {"status": "partial", "answer": "The repository lists 2.8T parameters.",
                           "fraza": "2.8T", "next_query": "Kimi K3.1 Pro: weights, licence!"}}
        return {"Q1": {"status": "open", "next_query": "kimi k3.1 pro weights licence"}}
    A.ksiega = ksiega_kimi
    A.runda(HF, FHF)
    A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1), pytanie(2, "PRACTICAL", 1),
                        pytanie(3, "NEW", 2)], max_rund=6)
    ids = [r["id"] for r in d["rundy_ksiegi"]]
    sprawdz("zapytanie rozniace sie tylko znakami nie kupuje drugiej rundy",
            ids == ["Q1", "Q2", "Q3"], ids)
    sprawdz("dwie puste rundy z rzedu koncza badanie", d["stop_reason"] == "two_empty_rounds",
            d["stop_reason"])
    sprawdz("raport: zadne pytanie dwa razy", research.stan_ksiegi(d)["pytania_dwa_razy"] == [],
            research.stan_ksiegi(d))
    sprawdz("pusta runda ma powod", d["rundy_ksiegi"][1]["powod"] == "no_new_sources", d["rundy_ksiegi"])

    nowy()

    def ksiega_druga(pytania, widok):
        out = {}
        if cytuj(widok, "2.8T"):
            out["Q1"] = {"status": "partial", "answer": "The repository lists 2.8T parameters.",
                         "fraza": "2.8T", "next_query": "Kimi K3.1 Pro hardware needed to run"}
        else:
            out["Q1"] = {"status": "open", "next_query": "kimi k3.1 pro weights licence"}
        out["Q2"] = {"status": "open", "next_query": "kimi k3.1 pro price per token"}
        if cytuj(widok, "Pricing page"):
            out["Q2"]["next_query"] = "a completely different price query"
        return out
    A.ksiega = ksiega_druga
    A.runda(HF, FHF)                                       # 1: Q1 dodaje fragment
    A.pusta()                                              # 2: Q2 nic
    A.runda("https://news.example/kimi", "Pricing page says $10 per million output tokens.")  # 3: Q3
    A.runda("https://hw.example/kimi", "Running it needs eight GPUs with 80GB each.")          # 4: Q1 raz drugi
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1), pytanie(2, "PRACTICAL", 1),
                        pytanie(3, "NEW", 2)], max_rund=4)
    ids = [r["id"] for r in d["rundy_ksiegi"]]
    sprawdz("druga proba Q1 (dodala fragmenty, inne zapytanie) — po swiezych pytaniach",
            ids == ["Q1", "Q2", "Q3", "Q1"], ids)
    sprawdz("KONTRDOWOD: Q2, ktorego pierwsza runda nic nie dala, drugiej nie dostaje",
            ids.count("Q2") == 1, ids)
    sprawdz("druga proba idzie nowym zapytaniem z ksiegi",
            d["rundy_ksiegi"][3]["zapytanie"] == "Kimi K3.1 Pro hardware needed to run", d["rundy_ksiegi"])
    sprawdz("raport widzi pytanie badane dwa razy", research.stan_ksiegi(d)["pytania_dwa_razy"] == ["Q1"])
    w1 = next(w for w in d["ksiega"] if w["id"] == "Q1")
    sprawdz("wpis pamieta obie proby i ich plon", [z["dodane"] for z in w1["zapytania"]] == [1, 1]
            and w1["proby"] == 2, w1["zapytania"])

    print()
    print("=== 4. WIDOK RUNDY: NOWE NAJPIERW; CZESCIOWE NIE COFAJA SIE ===")
    nowy()

    def ksiega_widok(pytania, widok):
        if cytuj(widok, "2.8T"):
            return {"Q1": {"status": "open", "next_query": "x"}}       # model „zapomina" odpowiedz
        return {"Q1": {"status": "partial", "answer": "The company reports 65.7%.", "fraza": "65.7%",
                       "next_query": "kimi k3.1 pro parameters"}}
    A.ksiega = ksiega_widok
    A.runda(HF, FHF, odpowiada=True)
    A.pusta(); A.pusta()
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1)], max_rund=3)
    prompty = [p for c, p in A.wywolania if c == "ksiega"]
    widok_rundy = widok_z_promptu(prompty[1])
    sprawdz("nowy fragment rundy ma source_id 1", widok_rundy[0]["url"] == HF, widok_rundy[0]["url"])
    sprawdz("fragment, na ktorym stoi czesciowa odpowiedz, jest w widoku",
            any(s["url"] == BLOG for s in widok_rundy), [s["url"] for s in widok_rundy])
    sprawdz("fragment juz pokazany i niecytowany nie wraca",
            not any(s["url"] == SW for s in widok_rundy), [s["url"] for s in widok_rundy])
    w1 = d["ksiega"][0]
    sprawdz("czesciowa odpowiedz nie cofa sie do open, zachowuje zrodla",
            w1["status"] == "partial" and w1["zrodla"] == [{"url": BLOG, "quote": FBLOG}], w1)
    sprawdz("nowe dowody doszly do evidence z flaga answers_question",
            ev[-1]["url"] == HF and ev[-1]["answers_question"] is True, ev[-1])

    print()
    print("=== 5. TEN SAM DOKUMENT POD www, ARCHIWA I KOD EXPLOITOW NIE WCHODZA ===")
    nowy()
    WWW = "https://www.kimi.ai/blog/kimi-k3-1-pro"
    ARCH = "https://web.archive.org/web/2026/https://kimi.ai/blog"
    POC = "https://github.com/someone/cve-2026-1234-poc"
    REPO = "https://github.com/moonshotai/kimi-k3"
    A.teksty[REPO] = "The README lists 2.8T total parameters with 104B active per token."
    A.kolejki["investigation_search"].append(({"sources": [{"url": WWW}]}, [WWW]))
    A.kolejki["investigation_search"].append(({"sources": [{"url": ARCH}, {"url": POC}, {"url": REPO}]},
                                              [ARCH, POC, REPO]))
    A.kolejki["investigation_extract"].append(({"documents": [{"source_id": 1, "class": "PRIMARY",
        "excerpts": ["The README lists 2.8T total parameters with 104B active per token."]}]}, []))
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "open", "next_query": "another query"}}
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1), pytanie(2, "NEW", 1)], max_rund=2)
    sprawdz("kopia pod www juz pobranego dokumentu nie jest pobierana drugi raz",
            d["rundy_ksiegi"][0]["powod"] == "no_new_sources" and [WWW] not in A.pobrane,
            (d["rundy_ksiegi"], A.pobrane))
    sprawdz("archiwum i repozytorium exploita odpadaja, zwykle repozytorium zostaje",
            A.pobrane == [[REPO]], A.pobrane)

    print()
    print("=== 6. UCIETA ODPOWIEDZ, ZLY JSON, AWARIE, BUDZET ===")
    nowy()
    proby = []

    def ksiega_ucieta(pytania, widok):
        proby.append([p["id"] for p in pytania])
        if len(pytania) == 5:
            return llm.Truncated("max_tokens")
        return {p["id"]: {"status": "answered", "answer": "The company says so.", "fraza": "65.7%"}
                for p in pytania}
    A.ksiega = ksiega_ucieta
    ev, d, log = badaj([pytanie(i, waga=1) for i in range(1, 5)], max_rund=0)
    sprawdz("ucieta paczka 5 pytan -> ponowka po 3 i 2", [len(p) for p in proby] == [5, 3, 2], proby)
    sprawdz("i statusy z ponowki weszly do ksiegi",
            all(w["status"] == "answered" for w in d["ksiega"]), [w["status"] for w in d["ksiega"]])
    sprawdz("ucieta odpowiedz nie konczy badania", not d["stop_reason"].startswith("failed"),
            d["stop_reason"])
    nowy()
    A.ksiega = lambda pytania, widok: ValueError("brak JSON w odpowiedzi")
    A.runda(HF, FHF)
    A.runda("https://x.example/a", "Another passage about the weights licence terms.")
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1)], max_rund=6)
    sprawdz("dwa przejscia statusow bez jednej udanej paczki -> koniec (nie placimy dalej na slepo)",
            d["stop_reason"] == "ksiega_failed" and len(d["rundy_ksiegi"]) == 1,
            (d["stop_reason"], d["rundy_ksiegi"]))
    sprawdz("material z rundy zostaje mimo awarii statusow", ev[-1]["url"] == HF)
    nowy()
    A.kolejki["investigation_search"].append((ValueError("zly JSON szukania"), []))
    A.pusta()
    ev, d, log = badaj([pytanie(1, "HOW_IT_WORKS", 1), pytanie(2, "NEW", 1)], max_rund=4)
    sprawdz("awaria szukania konczy tylko te runde",
            [r["powod"] for r in d["rundy_ksiegi"]] == ["search_failed:ValueError", "no_new_sources"]
            and d["stop_reason"] == "two_empty_rounds", d["rundy_ksiegi"])
    nowy()
    A.ksiega = lambda pytania, widok: llm.BudgetExceeded("dobowy limit")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            research.deepen(CONN, 1, "Q?", list(DOWODY), list(KORPUS), max_rund=2,
                            pytania=[pytanie(1)])
        budzet = False
    except llm.BudgetExceeded:
        budzet = True
    pliki = list(config.DATA_DIR.glob("research/*/run-1-ksiega-*.json"))
    sprawdz("BudgetExceeded przechodzi wyzej", budzet)
    sprawdz("a dossier jest zapisany z powodem", len(pliki) == 1 and json.loads(
        pliki[0].read_text(encoding="utf-8"))["stop_reason"] == "global_budget_or_preflight", pliki)

    print()
    print("=== 7. KOSZT: NOWE CELE W LICZNIKU, PROG ZE STOP_USD ===")
    nowy()
    CONN.execute("INSERT INTO calls VALUES (1, 'ksiega', .06)")
    CONN.execute("INSERT INTO calls VALUES (1, 'investigation_document', .05)")
    CONN.execute("INSERT INTO calls VALUES (1, 'classify', 5.0)")
    sprawdz("_spent liczy ksiege i poscig za dokumentem, nie klasyfikacje",
            abs(research._spent(CONN, 1) - .11) < 1e-9, research._spent(CONN, 1))
    ev, d, log = badaj([pytanie(1)], max_rund=3, stop_usd=0.10)
    sprawdz("prog sledztwa 0,10 zatrzymuje przed pierwszym wywolaniem",
            d["stop_reason"] == "cost_threshold" and not A.wywolania, (d["stop_reason"], A.wywolania))
    sprawdz("a bez stop_usd obowiazuje config.RESEARCH_STOP_USD (0,15)",
            research.deepen.__defaults__[-1] is None)
    nowy()
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "answered", "answer": "Says X.", "fraza": "65.7%"}}
    badaj([pytanie(1)], max_rund=0)
    przed = A.ile("ksiega")
    A.wywolania.clear()
    badaj([pytanie(1)], max_rund=0)
    sprawdz("ten sam prompt ksiegi w 24 h nie placi drugi raz", przed == 1 and A.ile("ksiega") == 0,
            (przed, A.ile("ksiega")))

    print()
    print("=== 8. NAKLADKA: SYNTEZA, KARTA, HIPOTEZY DLA KATOW ===")
    nowy()
    A.ksiega = lambda pytania, widok: {
        "Q1": {"status": "answered", "answer": "The makers say it narrowly trails Opus 5.5.", "fraza": "65.7%"},
        "Q2": {"status": "not_yet", "answer": "Weights are promised by Nov 4.", "when": "2026-11-04",
               "fraza": "Nov 4"}}
    pyt = [pytanie(1, "CLAIM", 1), pytanie(2, "WATCH", 1), pytanie(3, "PEOPLE", 1),
           pytanie(4, "POWER", 1), pytanie(5, "PRACTICAL", 2), pytanie(6, "NUMBERS", 3)]
    ev, d, log = badaj(pyt, max_rund=0)
    a = d["assessment"]
    sprawdz("nakladka ma stary ksztalt (hypotheses, questions, ready)",
            {"hypotheses", "actors", "questions", "counterargument", "ready"} <= set(a), sorted(a))
    sprawdz("hipoteza z odpowiedzi na pytanie o twierdzenie, z fragmentem",
            len(a["hypotheses"]) == 1 and a["hypotheses"][0]["support"][0]["url"] == BLOG, a["hypotheses"])
    sq = research.synthesis_question("Main?", d)
    sprawdz("synteza dostaje ksiege: odpowiedzi, otwarte, not_yet",
            "ANSWERED" in sq and "OPEN" in sq and "NOT YET (settles around 2026-11-04)" in sq
            and "inferences are NOT confirmed facts" in sq, sq[:300])
    karta = research.attach({"confirmed_claims": [], "not_established": ["already here"]}, d)
    braki = karta["not_established"]
    sprawdz("attach dopisuje najwyzej 3 braki z ksiegi", len(braki) == 4 and braki[0] == "already here",
            braki)
    sprawdz("najpierw otwarte pytania o wadze 1, pytanie o wadze 3 nie wchodzi",
            braki[1:] == [pyt[2]["q"], pyt[3]["q"], pyt[1]["q"] + " (depends on an event expected around 2026-11-04)"],
            braki)
    sprawdz("karta niesie stan ksiegi", karta["investigation"]["ksiega_stan"]["odpowiedziane"] == 1,
            karta["investigation"])
    try:
        import sledztwo
        tekst = sledztwo._hipotezy_do_promptu(d)
        sprawdz("sledztwo._hipotezy_do_promptu czyta nakladke", "narrowly trails" in tekst, tekst)
    except Exception as exc:     # noqa: BLE001 — import sledztwo moze zalezec od czesci K
        sprawdz("sledztwo._hipotezy_do_promptu czyta nakladke", False, repr(exc))

    print()
    print("=== 9. ZNAJDZ ORYGINAL DLA LICZBY INSTYTUCJI Z WTORNEGO ZRODLA ===")
    nowy()
    dowody = DOWODY + [zrodlo(NEWS, FNEWS)]
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "answered", "answer": "A portal says 40%.",
                                              "fraza": "Bank of England"}}
    ev, d, log = badaj([pytanie(1, "CONSEQUENCES", 1)], max_rund=0, dowody=dowody)
    o = [w for w in d["ksiega"] if w.get("pochodne")]
    sprawdz("kod dodaje wpis O1 z instytucja i liczba w zapytaniu",
            len(o) == 1 and o[0]["id"] == "O1" and "Bank of England" in o[0]["zapytanie"]
            and "40" in o[0]["zapytanie"] and o[0]["waga"] == 1, o)
    sprawdz("stan_ksiegi liczy go osobno", research.stan_ksiegi(d)["pytan"] == 2
            and research.stan_ksiegi(d)["oryginaly_szukane"] == 1, research.stan_ksiegi(d))
    nowy()
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "answered", "answer": "A portal says 40%.",
                                              "fraza": "Bank of England"}}
    oryginal = zrodlo("https://www.bankofengland.co.uk/fsr", "Lenders' exposure table.", "PRIMARY",
                      "Bank of England Financial Stability Report")
    ev, d, log = badaj([pytanie(1, "CONSEQUENCES", 1)], max_rund=0, dowody=dowody + [oryginal])
    sprawdz("KONTRDOWOD: gdy oryginal juz jest wsrod zrodel pierwotnych — bez wpisu",
            not [w for w in d["ksiega"] if w.get("pochodne")], [w["id"] for w in d["ksiega"]])
    nowy()
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "answered", "answer": "AA measured 67%.",
                                              "fraza": "highest score"}}
    ev, d, log = badaj([pytanie(1, "CLAIM", 1)], max_rund=0)
    sprawdz("KONTRDOWOD: pomiar bez przypisania instytucji — bez wpisu",
            not [w for w in d["ksiega"] if w.get("pochodne")], [w["id"] for w in d["ksiega"]])

    print()
    print("=== 10. DRUGA KSIEGA Z PIERWSZEJ (PYTANIA KRYTYKA) ===")
    nowy()
    pierwsza = [{"id": "Q1", "q": "Question 1?", "soczewka": "CLAIM", "waga": 1, "status": "answered",
                 "odpowiedz": "The makers say so.", "zrodla": [{"url": BLOG, "quote": FBLOG}], "proby": 1},
                {"id": "Q0", "q": "Main?", "soczewka": "MAIN", "waga": 2, "status": "open", "proby": 0},
                {"id": "Q9", "q": "Fake answered?", "status": "answered", "odpowiedz": "No source."},
                {"id": "Q8", "q": "Quote not in evidence?", "status": "answered", "odpowiedz": "Made up.",
                 "zrodla": [{"url": BLOG, "quote": "The model scores 99% on every benchmark."}]},
                {"id": "Q7", "q": "Quote glued from two passages?", "status": "partial",
                 "odpowiedz": "Glued.", "zrodla": [{"url": BLOG, "quote": "(66.4%). Pricing starts"}]}]
    # Dwa fragmenty pod jednym adresem: cytat z konca pierwszego i poczatku drugiego.
    dwa_fragmenty = [{**DOWODY[0], "excerpts": [FBLOG, "Pricing starts at $10 per million output tokens."]},
                     *DOWODY[1:]]
    krytyk = [{"id": "K1", "soczewka": "POWER", "q": "Who gains leverage if the weights ship?",
               "waga": 1, "dowod": "licence", "gdzie": "Hugging Face", "zapytanie": "kimi k3.1 licence"}]
    widziane = []
    A.ksiega = lambda pytania, widok: widziane.append([p["id"] for p in pytania]) or {}
    A.pusta(); A.pusta()
    ev, d, log = badaj(pierwsza + krytyk, max_rund=2, pytanie_glowne="Main?", dowody=dwa_fragmenty)
    ks = {w["id"]: w for w in d["ksiega"]}
    sprawdz("odpowiedziane z pierwszej ksiegi nie ida ponownie do oceny",
            widziane and "Q1" not in widziane[0] and "K1" in widziane[0], widziane)
    sprawdz("wpis answered bez zrodla wraca do open", ks["Q9"]["status"] == "open", ks["Q9"])
    sprawdz("wpis, ktorego cytatu nie ma w dzisiejszych dowodach, wraca do open",
            ks["Q8"]["status"] == "open" and not ks["Q8"]["zrodla"], ks["Q8"])
    sprawdz("KONTRDOWOD: cytat sklejony z dwoch fragmentow tez nie przechodzi",
            ks["Q7"]["status"] == "open", ks["Q7"])
    sprawdz("a prawdziwy cytat z pierwszej ksiegi zostaje", ks["Q1"]["status"] == "answered", ks["Q1"])
    sprawdz("bez drugiego Q0", [w["id"] for w in d["ksiega"]].count("Q0") == 1)
    sprawdz("runde dostaje najpierw pytanie krytyka (waga 1)", d["rundy_ksiegi"][0]["id"] == "K1",
            d["rundy_ksiegi"])

    print()
    print("=== 11. POSCIG ZA DOKUMENTEM PIERWOTNYM ===")
    nowy()
    CARD = "https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/MODEL_CARD.md"
    ART = "https://news.example/kimi-model-card-explained"
    A.kolejki["investigation_document"].append(({"documents": [
        {"url": ART, "is_the_document": False, "official": False},
        {"url": "https://web.archive.org/web/2026/" + CARD, "is_the_document": True},
        {"url": "https://invented.example/card", "is_the_document": True},
        {"url": CARD, "title": "Model card", "is_the_document": True, "official": True,
         "note": "the card itself"},
        {"url": SW, "is_the_document": True}]},
        [ART, "https://web.archive.org/web/2026/" + CARD, CARD, SW]))
    seen = {research.url_key(u) for u in (BLOG, AA, SW)}
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = research.dokument(CONN, 1, "the Kimi K3.1 Pro model card", "Moonshot AI",
                                  "Hugging Face model repository", seen=seen)
    sprawdz("oddaje sam dokument z wynikow wyszukiwarki",
            [z["url"] for z in wynik] == [CARD] and wynik[0]["class"] == "PRIMARY", wynik)
    sprawdz("ksztalt wyniku _search + czego szukalismy",
            {"url", "host", "title", "publisher", "class", "note", "dokument"} <= set(wynik[0])
            and wynik[0]["publisher"] == "Moonshot AI", wynik[0])
    sprawdz("KONTRDOWOD: artykul o dokumencie, archiwum, adres spoza wynikow i juz pobrany odpadaja",
            len(wynik) == 1)
    sprawdz("seen uzupelnione o znaleziony adres", research.url_key(CARD) in seen)
    prompt = next(p for c, p in A.wywolania if c == "investigation_document")
    sprawdz("prompt nazywa dokument, wydawce, miejsce i limit 2 szukan",
            "the Kimi K3.1 Pro model card" in prompt and "Moonshot AI" in prompt
            and "at most 2 web searches" in prompt, prompt[:200])
    nowy()
    A.kolejki["investigation_document"].append(({"documents": [{"url": CARD, "is_the_document": True}]}, []))
    with contextlib.redirect_stdout(io.StringIO()):
        pusto = research.dokument(CONN, 1, "the model card", "Moonshot AI", "Hugging Face")
    sprawdz("wyszukiwarka nic nie oddala -> pusto, nie adres z pamieci", pusto == [], pusto)
    nowy()
    A.kolejki["investigation_document"].append((ValueError("zly JSON"), []))
    with contextlib.redirect_stdout(io.StringIO()):
        pusto = research.dokument(CONN, 1, "the model card", "Moonshot AI", "Hugging Face")
    sprawdz("zly JSON -> pusto, bez wyjatku", pusto == [])
    nowy()
    CONN.execute("INSERT INTO calls VALUES (1, 'investigation', 1.0)")
    with contextlib.redirect_stdout(io.StringIO()):
        pusto = research.dokument(CONN, 1, "the model card", "Moonshot AI", "Hugging Face")
    sprawdz("prog kosztu badania -> pusto, bez wywolania", pusto == [] and not A.wywolania)
    nowy()
    A.kolejki["investigation_document"].append((llm.BudgetExceeded("limit"), []))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            research.dokument(CONN, 1, "the model card", "Moonshot AI", "Hugging Face")
        sprawdz("BudgetExceeded przechodzi wyzej", False)
    except llm.BudgetExceeded:
        sprawdz("BudgetExceeded przechodzi wyzej", True)
    nowy()
    sprawdz("puste `co` -> pusto bez wywolania",
            research.dokument(CONN, 1, "", "x", "y") == [] and not A.wywolania)

    print()
    print("=== 12. DLUGI DOKUMENT: KAWALKI WEDLUG PYTANIA (okladka raportu MFW) ===")
    okladka = "\n".join("Contents chapter %d foreword acknowledgements and glossary." % i
                        for i in range(800))
    tabela = "Table 3: data-centre lenders hold 40% of the exposure, mostly private credit funds."
    dlugi = okladka + "\n" + tabela + "\n" + "Annex text about methodology.\n" * 50
    wyslany = research.uloz_kawalki(dlugi, "Who are the lenders and what share of exposure? 40%", 18000)
    sprawdz("dlugi tekst miesci sie w limicie", len(wyslany) <= 18000, len(wyslany))
    sprawdz("kawalek z liczba i slowami pytania jest w srodku", tabela in wyslany)
    sprawdz("a przerwy sa oznaczone", "[...]" in wyslany)
    sprawdz("KONTRDOWOD: bez slow pytania — pierwsze znaki, jak dotad",
            research.uloz_kawalki(dlugi, "", 18000) == dlugi[:18000])
    sprawdz("KONTRDOWOD: krotki tekst wraca bez zmian", research.uloz_kawalki(tabela, "lenders", 18000) == tabela)
    sprawdz("8,675 w pytaniu trafia 8675 w dokumencie",
            "8675" in research._terminy("about 8,675 jobs")[1])
    nowy()
    A.teksty["https://imf.example/gfsr.pdf"] = dlugi
    A.kolejki["investigation_search"].append(({"sources": [{"url": "https://imf.example/gfsr.pdf"}]},
                                              ["https://imf.example/gfsr.pdf"]))
    przez_przerwe = "Annex text about methodology.\n[...]\nContents chapter 1 foreword"
    A.kolejki["investigation_extract"].append(({"documents": [{"source_id": 1, "class": "PRIMARY",
        "excerpts": [tabela, przez_przerwe]}]}, []))
    A.ksiega = lambda pytania, widok: {"Q1": {"status": "open", "next_query": "lenders share of exposure 40%"}}
    ev, d, log = badaj([pytanie(1, "NUMBERS", 1, zapytanie="lenders share of exposure 40%")],
                       max_rund=1)
    prompt = next(p for c, p in A.wywolania if c == "investigation_extract")
    sprawdz("wyciag w trybie ksiegi dostaje tabele z glebi dokumentu",
            json.dumps(tabela)[1:-1] in prompt, prompt[:200])
    sprawdz("cytat z kawalka przechodzi, cytat sklejony przez [...] odpada",
            ev[-1]["excerpts"] == [tabela], ev[-1]["excerpts"])
    nowy()
    A_URL = "https://imf.example/old.pdf"
    A.teksty[A_URL] = dlugi
    with contextlib.redirect_stdout(io.StringIO()):
        A.kolejki["investigation_extract"].append(({"documents": []}, []))
        research._extract(CONN, 1, "Q?", {"question": "lenders 40%"}, [{"url": A_URL, "text": dlugi}])
    prompt = next(p for c, p in A.wywolania if c == "investigation_extract")
    sprawdz("KONTRDOWOD: artykul z puli (bez slow) dostaje pierwsze 18 000 znakow jak dotad",
            tabela not in prompt and "Contents chapter 0" in prompt)

    print()
    print("=== 13. TRYB ARTYKULU Z PULI BEZ ZMIAN ===")
    nowy()
    config.RESEARCH_ENABLED = False
    with contextlib.redirect_stdout(io.StringIO()):
        _, d_stary = research.deepen(CONN, 1, "Q?", list(DOWODY), list(KORPUS))
        _, d_nowy = research.deepen(CONN, 1, "Q?", list(DOWODY), list(KORPUS), pytania=[])
    config.RESEARCH_ENABLED = True
    sprawdz("bez pytania: zadnej ksiegi w dossier", "ksiega" not in d_stary and d_stary["assessment"] == {},
            sorted(d_stary))
    sprawdz("pusta lista pytan to juz ksiega (z samym Q0)",
            [w["id"] for w in d_nowy["ksiega"]] == ["Q0"] and d_nowy["stop_reason"] == "disabled")
    sprawdz("attach starego dossier bez limitu 3 i bez stanu ksiegi",
            "ksiega_stan" not in research.attach({}, {"assessment": {"questions": []}}).get("investigation", {}))

    print()
    print("=== 14. CELE KSIEGI W KONFIGURACJI (dopisuje czesc N) ===")
    for cel in ("ksiega", "investigation_document"):
        sprawdz("%s w research.PURPOSES" % cel, cel in research.PURPOSES)
        if cel in config.MODEL_FOR and cel in config.MAX_TOKENS:
            sprawdz("%s idzie na DeepSeeka z sufitem <= 8000" % cel,
                    config.MODEL_FOR[cel] == config.DEEPSEEK and config.MAX_TOKENS[cel] <= 8000,
                    (config.MODEL_FOR[cel], config.MAX_TOKENS[cel]))
        else:
            print("  POMINIETE  %s: brak w config.MODEL_FOR/MAX_TOKENS — czeka na czesc N" % cel)
finally:
    llm.call, stages.fetch = _oryginal_call, _oryginal_fetch

print()
print("=== 15. PO RECENZJI 25.10.2026 ===")
sprawdz("skrot z nazwy testu albo modelu to nie instytucja (SWE-bench, GPT-5, HN)",
        research._instytucja("It scores 65.7% on SWE-bench Verified, the report shows") == ""
        and research._instytucja("GPT-5 reached 80% on the test, the paper found") == ""
        and research._instytucja("HN commenters said it costs 40% less") == "")
sprawdz("KONTRDOWOD: znana instytucja ze skrotu dalej jest instytucja",
        research._instytucja("The IMF estimated that 40% of jobs are exposed") == "IMF")
sprawdz("adres, ktory nie jest napisem, daje pusty klucz zamiast wyjatku",
        research.url_key(123) == "" and research.url_key(None) == "")
_zasiane = [{"id": "Q%d" % i, "q": "Question %d?" % i, "waga": 3 if i > 10 else 1,
             "status": "answered" if i in (11, 12) else "open", "odpowiedz": "x" if i in (11, 12) else ""}
            for i in range(1, 16)]
_zasiane += [{"id": "K%d" % i, "q": "Critic %d?" % i, "waga": 1} for i in range(1, 4)]
with contextlib.redirect_stdout(io.StringIO()):
    _wp = research._wpisy_z_pytan("Main question?", _zasiane)
_ids = {w["id"] for w in _wp}
sprawdz("sufit ksiegi nie wycina pytan z odpowiedzia (Q11, Q12 answered zostaja)",
        len(_wp) <= research.MAKS_PYTAN_KSIEGI and {"Q11", "Q12", "K1", "K2", "K3"} <= _ids, sorted(_ids))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
