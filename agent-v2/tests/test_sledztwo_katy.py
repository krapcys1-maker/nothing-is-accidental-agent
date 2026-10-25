# -*- coding: utf-8 -*-
"""Katy sledztwa, uczciwy hak, poziom tematu i kolejka (25.10.2026, fala 1, czesc K).

PO CO. Spec §4-5 i §9 pkt 3, 7, 9, 12, 17, 18: jedna tabela `KATY` zamiast menu, regula
liczby notek z bogactwa sledztwa, kontrakt uczciwego haka w kodzie (prosba w promptcie nie
jest bramka), sklad i kolejnosc serii, jedna runda zwrotna do planisty, kolejka, ktora nie
blokuje czola i nie wypuszcza prowadzacego tego samego dnia bez kluczy.

Kazda regula ma przyklad przechodzacy i oblewajacy. Przyklady hakow z §4 (premiera Kimi
K3.1 Pro, fakty z plikow proby) sa DANYMI testu — w kodzie i promptach nie ma zadnej nazwy.

BEZ PYTESTA, bez sieci, bez platnych wywolan (llm.call podmieniony). Uruchamiac z korzenia
repozytorium: NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_sledztwo_katy.py
"""
import contextlib
import io
import json
import pathlib
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm        # noqa: E402
import sledztwo   # noqa: E402

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
CONN = sqlite3.connect(":memory:")


def cicho(fn, *a, **k):
    """Wywolanie z przechwyconym logiem: (wynik, log)."""
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = fn(*a, **k)
    return wynik, log.getvalue()


# ============================================================================================
print("=== 1. TABELA KATOW ===")
OCZEKIWANE = ("REVEAL", "NUMBER_FELT", "HOW_IT_WORKS", "CLAIM_VS_MEASURED", "WHO_GAINS_PAYS", "POWER_SHIFT",
              "WHAT_IT_TAKES", "PEOPLE", "VERDICT", "MOTIVE", "WHERE_IT_LEADS", "ROZLICZENIE")
sprawdz("KATY ma dokladnie dwanascie wspolnych tagow", tuple(sledztwo.KATY) == OCZEKIWANE, tuple(sledztwo.KATY))
sprawdz("kazdy kat: typ notki istniejacy w config.NOTE_TYPES, opis po angielsku, flaga analizy",
        all(set(k) == {"typ_notki", "opis", "analiza"} and k["typ_notki"] in config.NOTE_TYPES
            and isinstance(k["analiza"], bool) and len(k["opis"]) > 40
            and not re.search("[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", k["opis"])
            for k in sledztwo.KATY.values()))
sprawdz("analiza = werdykt, motyw, prognoza (typ DYSKUSJA); reszta to fakty",
        set(sledztwo.ANALIZY) == {"VERDICT", "MOTIVE", "WHERE_IT_LEADS"}
        and all(sledztwo.KATY[r]["typ_notki"] == "DYSKUSJA" for r in sledztwo.ANALIZY))
_menu = sledztwo._katy_do_promptu()
sprawdz("ROZLICZENIE nie idzie do planisty (etap 21 poza fala 1), reszta tak",
        "ROZLICZENIE" not in _menu and all("- %s —" % r in _menu for r in OCZEKIWANE[:-1]), _menu[:200])
_prz = pathlib.Path("agent-v2/prompts/przeslania.md").read_text(encoding="utf-8")
sprawdz("bez dosłownego „AGI at maths” w opisach katow i w prompcie katow",
        "AGI at maths" not in _menu and "AGI at maths" not in _prz
        # `PYTANIA_PREMIERY` zniknely z fala 1 (plan robi `sledztwo_plan`) — sprawdzamy prompt planu.
        and "AGI at maths" not in pathlib.Path("agent-v2/prompts/plan_sledztwa.md").read_text(encoding="utf-8"))
_NAZWY_Z_PROB = ("Kimi", "Moonshot", "PHP2Shell", "NextDC", "Medicare", "Chainguard", "Willison")
sprawdz("zadnej nazwy firmy ani historii z prob w promptach i opisach katow",
        not any(n.lower() in t.lower() for n in _NAZWY_Z_PROB for t in (
            _menu, _prz, *(pathlib.Path("agent-v2/prompts/%s" % p).read_text(encoding="utf-8")
                           for p in ("nowosc.md", "ten_sam_punkt.md", "naglowek_naprawa.md")))))
sprawdz("pochodne tabeli spojne (zgodnosc ze starym przebiegiem)",
        sledztwo.TYP_NOTKI["VERDICT"] == "DYSKUSJA" and sledztwo.RODZAJE == OCZEKIWANE[:-1]
        and sledztwo.ZESTAWY_KATOW["premiera"] == sledztwo.ZESTAWY_KATOW["sledztwo"]
        and sledztwo.RUND_SLEDZTWA == 6 and sledztwo.SLEDZTWO_STOP_USD == 0.10)

# ============================================================================================
print()
print("=== 2. NORMALIZACJA LICZB (spec §4 pkt 2) ===")


def wartosci(t, nazwy=None):
    return [w for w, _ in sledztwo._liczby_slow(sledztwo._slowa(t), nazwy)]


sprawdz("$2.00 = $2, 8,675 = 8675", wartosci("It costs $2.00 for 8,675 users.") == ["2", "8675"],
        wartosci("It costs $2.00 for 8,675 users."))
sprawdz("150M = 150 million = 150000000; 1.5bn = 1500000000",
        wartosci("150M tokens, 150 million tokens, 1.5bn dollars") == ["150000000", "150000000", "1500000000"],
        wartosci("150M tokens, 150 million tokens, 1.5bn dollars"))
sprawdz("slownie -> cyfry (three, twenty-five, two million), procent = wartosc",
        wartosci("three labs, twenty-five agents, two million users, 65.7% and 65.7 percent")
        == ["3", "25", "2000000", "65.7", "65.7"],
        wartosci("three labs, twenty-five agents, two million users, 65.7% and 65.7 percent"))
sprawdz("mnozniki: half, twice, a third, three times, 3.5x, 2-fold",
        wartosci("half the price, twice as fast, a third of it, three times more, 3.5x, 2-fold")
        == ["x0.5", "x2", "x0.33", "x3", "x3.5", "x2"],
        wartosci("half the price, twice as fast, a third of it, three times more, 3.5x, 2-fold"))
sprawdz("zakres i znak tez sa liczbami: „10-12%” = 10 i 12, „-3%” = 3, „2025-2026” = dwa lata",
        wartosci("shares fell -3% after a 10-12% rise in 2025-2026") == ["3", "10", "12", "2025", "2026"],
        wartosci("shares fell -3% after a 10-12% rise in 2025-2026"))
sprawdz("KONTRDOWOD: „one commenter” i nazwy z cyframi (K3.1, GPT-6, H100) to nie liczby",
        wartosci("One commenter ran K3.1 and GPT-6 on an H100.") == [], wartosci("One commenter ran K3.1 and GPT-6 on an H100."))
_cz = [sledztwo._oczysc(s) for s in sledztwo._slowa("It narrowly loses to Claude Opus 5.5 on Terminal-Bench 4.0 by Nov 4.")]
_nz = sledztwo._indeksy_nazw(_cz, "narrowly behind Claude Opus 5.5 (66.4%) on Terminal-Bench 4.0; by Nov 4", [])
sprawdz("wersje z dowodow zdejmowane (Opus 5.5, Terminal-Bench 4.0), data „Nov 4” zostaje liczba",
        wartosci("It narrowly loses to Claude Opus 5.5 on Terminal-Bench 4.0 by Nov 4.", _nz) == ["4"],
        wartosci("It narrowly loses to Claude Opus 5.5 on Terminal-Bench 4.0 by Nov 4.", _nz))

# ============================================================================================
print()
print("=== 3. UCZCIWY HAK: PRZYKLADY Z §4 (premiera Kimi K3.1 Pro) ===")
KIMI_BLOG = {"claim": "Moonshot says Kimi K3.1 Pro scores 65.7% on Terminal-Bench 4.0, narrowly behind Claude Opus 5.5",
             "evidence": "On Terminal-Bench 4.0, K3.1 Pro scores 65.7%, narrowly behind Claude Opus 5.5 (66.4%).",
             "url": "https://kimi.ai/blog/kimi-k3-1-pro", "kind": "VENDOR_CLAIM", "klasa": "PRIMARY"}
AA_ART = {"claim": "Artificial Analysis measured Kimi K3.1 Pro at 67% on Terminal-Bench 4.0, the highest of any model",
          "evidence": "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%",
          "url": "https://artificialanalysis.ai/articles/kimi-k3-1-pro-launch-benchmarks",
          "kind": "INDEPENDENT_MEASURE", "klasa": "INDEPENDENT"}
AA_MOD = {"claim": "Kimi K3.1 Pro generated 150M tokens on the Intelligence Index, against a median of 87M",
          "evidence": "it generated 150M tokens, which is very verbose in comparison to the median of 87M",
          "url": "https://artificialanalysis.ai/models/kimi-k3-1-pro", "kind": "INDEPENDENT_MEASURE",
          "klasa": "INDEPENDENT"}
WILL = {"claim": "Simon Willison notes Kimi K3.1 Pro is not yet open weights; Moonshot promises weights by Nov 4, 2026",
        "evidence": "it's not yet open weights, but Moonshot promise 'Full model weights will be released by Nov 4, 2026'",
        "url": "https://simonwillison.net/2026/Oct/23/kimi-k31-pro/", "kind": "FACT", "klasa": "SECONDARY"}
ART = {"claim": "Artificial Analysis currently lists Kimi K3.1 Pro as proprietary",
       "evidence": "Artificial Analysis currently lists it as proprietary", "url": "https://news.example.com/0495",
       "kind": "FACT", "klasa": "SECONDARY"}
LS = {"claim": "Latent Space calls Kimi K3.1 Pro Fable-5.1-class open weights",
      "evidence": "Kimi K3.1 Pro: Fable-5.1-Class Open Weights", "url": "https://www.latent.space/p/kimi",
      "kind": "VOICE", "klasa": "VOICE"}
HALF = {"claim": "Simon Willison puts Kimi K3.1 Pro at half the price of Claude Opus 5.5",
        "evidence": "K3.1 Pro comes in at roughly half the price of Claude Opus 5.5",
        "url": "https://simonwillison.net/2026/Oct/23/kimi-k31-pro/", "kind": "FACT", "klasa": "SECONDARY"}
PROJ = {"claim": "Artificial Analysis expects the gap to closed models to narrow from 12 points to 3 once weights are out",
        "evidence": "Once the weights for K3.1 Pro are released, we expect the gap to narrow from 12 points to 3",
        "url": "https://artificialanalysis.ai/articles/kimi-k3-1-pro-launch-benchmarks",
        "kind": "INDEPENDENT_MEASURE", "klasa": "INDEPENDENT"}
KARTA_KIMI = [KIMI_BLOG, AA_ART, AA_MOD, WILL, ART, LS, HALF, PROJ]
ENCJE_KIMI = ["Kimi K3.1 Pro", "Claude Opus 5.5", "Terminal-Bench 4.0"]
KTX = {"wszystkie_fakty": KARTA_KIMI, "encje": ENCJE_KIMI}
PRZYKLADY = [
    ("1. CLAIM_VS_MEASURED", "Kimi K3.1 Pro's makers say it narrowly loses to Claude Opus 5.5 at command-line coding.",
     [KIMI_BLOG, AA_ART]),
    ("2. REVEAL / PROMISE", "Kimi K3.1 Pro is billed as an open-weights model, but the weights are not out yet.",
     [WILL, ART, LS]),
    ("3. NUMBER_CONTRAST", "While earning its Intelligence Index score, Kimi K3.1 Pro wrote 150 million tokens; "
                           "the median model, 87 million.", [AA_MOD, WILL]),
    ("przepisany kuszacy hak", "Simon Willison puts Kimi K3.1 Pro at half the price of Claude Opus 5.5.", [HALF]),
]
for nazwa, linia, fakty in PRZYKLADY:
    _b = sledztwo.sprawdz_linie(linia, fakty, KTX)
    sprawdz("przechodzi: %s" % nazwa, _b == [], _b)
_kuszacy = sledztwo.sprawdz_linie("Three points behind the best AI, at half the price.", [PROJ, HALF, AA_ART], KTX)
sprawdz("KONTRDOWOD: kuszacy hak oblewa na czterech regulach z §4",
        any(b.startswith("condition: the evidence for '3'") for b in _kuszacy)
        and any(b.startswith("attribution: 'x0.5'") for b in _kuszacy)
        and any("'best'" in b for b in _kuszacy) and any("'behind'" in b for b in _kuszacy), _kuszacy)

print()
print("=== 3b. REGULY HAKA, KAZDA Z KONTRDOWODEM ===")
for linia, czego in (("On October 21, the lab published a fix for its AI agent.", "date"),
                     ("According to a new report, AI agents now write most of the code.", "According to"),
                     ("Is this the end of closed AI models for good?", "question"),
                     ("You won't believe what this AI model costs to run.", "teaser"),
                     ("AI wins.", "words"),
                     ("This sentence about one model goes on and on far past the limit of eighteen words that we "
                      "allow for hooks.", "words")):
    _b = sledztwo.sprawdz_linie(linia, [AA_ART], KTX)
    sprawdz("ksztalt: %s" % czego, any(b.startswith("shape:") and (czego.lower() in b.lower()) for b in _b), _b)
_b = sledztwo.sprawdz_linie("Claude Opus 5.5 has the highest score on Terminal-Bench 4.0 of any model.", [AA_ART], KTX)
sprawdz("KONTRDOWOD wiazania: „highest” z zdania o innym modelu nie przechodzi na Claude",
        any(b.startswith("entity: 'highest'") for b in _b), _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro posted the highest score on Terminal-Bench 4.0 of any model.", [AA_ART], KTX)
sprawdz("wiazanie: to samo „highest” przy wlasciwej encji przechodzi", _b == [], _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro scored 71% on Terminal-Bench 4.0.", [AA_ART], KTX)
sprawdz("KONTRDOWOD: liczba spoza dowodu (71)", any("71 is not in the evidence" in b for b in _b), _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro's full weights arrive by Nov 4, Moonshot says.", [WILL], KTX)
sprawdz("KONTRDOWOD warunku: dowod mowi „will/promise”, linia stwierdza fakt",
        any(b.startswith("condition:") for b in _b), _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro's full weights will arrive by Nov 4, Moonshot says.", [WILL], KTX)
sprawdz("warunek przeniesiony („will”) i obietnica podpisana mowca z dowodu („Moonshot says”)", _b == [], _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro costs half as much as Claude Opus 5.5.", [HALF], KTX)
sprawdz("KONTRDOWOD podpisu: cena z jednego zrodla bez nazwy zrodla",
        any(b.startswith("attribution:") for b in _b), _b)
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro narrowly loses to Claude Opus 5.5 at command-line coding.",
                            [KIMI_BLOG], KTX)
sprawdz("KONTRDOWOD podpisu: twierdzenie producenta bez nazwy producenta",
        any(b.startswith("attribution:") for b in _b), _b)
_POZYCZKA = {"claim": "The lender's covenant breaks if the data-centre operator's AI tenant pays late",
             "evidence": "The covenant on the loan is breached if the AI tenant pays late, the filing says.",
             "url": "https://www.asx.com.au/x", "kind": "FACT", "klasa": "PRIMARY"}
_b = sledztwo.sprawdz_linie("The loan covenant breaks if an AI tenant pays late.", [_POZYCZKA], {})
sprawdz("KONTRDOWOD zargonu: „covenant” bez glosy", any(b.startswith("plain words: 'covenant'") for b in _b), _b)
_b = sledztwo.sprawdz_linie("The loan covenant (a promise to lenders) breaks if an AI tenant pays late.", [_POZYCZKA], {})
sprawdz("zargon z glosa w nawiasie przechodzi", _b == [], _b)
_SPADEK = {"claim": "NextDC shares fell 40% after a power delay",
           "evidence": "NextDC shares fell 40% after the company disclosed a grid connection delay.",
           "url": "https://www.reuters.com/x", "kind": "FACT", "klasa": "SECONDARY"}
_NAG = ["Shares in this data centre company are down 40% as investors lose faith in the AI story",
        "Shares in this data center company are down 40% as investors lose faith in the AI story",
        "NextDC shares sink on power delay"]
_lin = "Reuters reports NextDC shares fell 40% after a grid delay for AI."
_b1 = sledztwo.sprawdz_linie(_lin, [_SPADEK], {"naglowki": _NAG, "pozycja": 1})
_b3 = sledztwo.sprawdz_linie(_lin, [_SPADEK], {"naglowki": _NAG, "pozycja": 3})
sprawdz("KONTRDOWOD powszechnosci: liczba z dwoch naglowkow nie jest hakiem notki 1; na pozycji 3 moze",
        any(b.startswith("commonness:") for b in _b1) and _b3 == [], (_b1, _b3))
_b = sledztwo.sprawdz_linie("Kimi K3.1 Pro wrote 150 million tokens on one test.", [AA_MOD],
                            dict(KTX, liczby_hakow=["150000000"]))
sprawdz("KONTRDOWOD: liczba juz bedaca hakiem innej notki serii", any("already the hook number" in b for b in _b), _b)
_POCH = [{"wartosc": "2.8 trillion", "zalozenie": "one byte per weight"}]
_b1 = sledztwo.sprawdz_linie("Kimi K3.1 Pro needs 2.8 trillion bytes of memory.", [AA_MOD], dict(KTX, pochodne=_POCH))
_b2 = sledztwo.sprawdz_linie("By our arithmetic Kimi K3.1 Pro needs 2.8 trillion bytes, at one byte per weight.",
                             [AA_MOD], dict(KTX, pochodne=_POCH))
sprawdz("liczba wyliczona: tylko jako „by our arithmetic” z zalozeniem",
        any(b.startswith("derived:") for b in _b1) and not any(b.startswith("derived:") for b in _b2), (_b1, _b2))

# ============================================================================================
print()
print("=== 4. BRAMKA NOTKI (spec §9 pkt 7) ===")
NOTKA_1 = ("Kimi K3.1 Pro's makers say it narrowly loses to Claude Opus 5.5 at command-line coding. Their own table: "
           "65.7% against 66.4% on Terminal-Bench 4.0. Artificial Analysis ran the test itself and measured 67%, "
           "\"the highest score of any model on Terminal-Bench 4.0\". A maker underselling its model is rare.")
KN = {"encje": ENCJE_KIMI, "linia": PRZYKLADY[0][1]}
_b = sledztwo.sprawdz_notke(NOTKA_1, [KIMI_BLOG, AA_ART], KN)
sprawdz("notka z przykladu 1 przechodzi (3 liczby, wszystkie z twierdzen, termin AI, zaczyna od linii)", _b == [], _b)
NOTKA_3 = ("While earning its Intelligence Index score, Kimi K3.1 Pro wrote 150 million tokens; the median model, "
           "87 million. Artificial Analysis, which ran the test, calls that \"very verbose\". A token is a word-piece, "
           "and every extra one is billed.")
_b = sledztwo.sprawdz_notke(NOTKA_3, [AA_MOD], {"encje": ENCJE_KIMI})
sprawdz("notka z przykladu 3 przechodzi: „token” objasniony w trzecim zdaniu", _b == [], _b)
_b = sledztwo.sprawdz_notke(NOTKA_3.replace("A token is a word-piece, and every", "Every"), [AA_MOD],
                            {"encje": ENCJE_KIMI})
sprawdz("KONTRDOWOD: „tokens” bez zadnej glosy w notce", any("'tokens'" in b for b in _b), _b)
_b = sledztwo.sprawdz_notke(NOTKA_1 + " It scored 12% on another test.", [KIMI_BLOG, AA_ART], KN)
sprawdz("KONTRDOWOD: czwarta liczba i liczba spoza twierdzen",
        any("4 numbers" in b for b in _b) and any("12 not in the cited claims" in b for b in _b), _b)
_b = sledztwo.sprawdz_notke("I think Kimi K3.1 Pro is a big deal for AI. My bet is it wins.", [AA_ART], KN)
sprawdz("KONTRDOWOD: pierwsza osoba liczby pojedynczej", any(b.startswith("voice:") for b in _b), _b)
_b = sledztwo.sprawdz_notke("The AI model made a Type I error on 67% of runs, \"I was stunned\", one tester said.",
                            [AA_ART], {})
sprawdz("„Type I” i „I” w cytacie to nie pierwsza osoba", not any(b.startswith("voice:") for b in _b), _b)
_b = sledztwo.sprawdz_notke("The lab's share price fell. Investors sold. Then the AI model shipped.", [AA_ART], {})
sprawdz("KONTRDOWOD: brak aktora AI w dwoch pierwszych zdaniach", any(b.startswith("AI term:") for b in _b), _b)
_b = sledztwo.sprawdz_notke(NOTKA_1, [KIMI_BLOG, AA_ART], dict(KN, linia="Kimi K3.1 Pro is cheap now."))
sprawdz("KONTRDOWOD: notka nie zaczyna sie od sprawdzonej linii", any(b.startswith("first line:") for b in _b), _b)
_seria = ["Picture a model that checks its own work. It does now.", "Kimi K3.1 Pro is not a chatbot, it's an agent."]
_b = sledztwo.sprawdz_notke("Picture a lab that undersells its AI model. That is Kimi K3.1 Pro, not hype, but data.",
                            [AA_ART], {"teksty_serii": _seria, "encje": ENCJE_KIMI})
sprawdz("KONTRDOWOD: drugi „Picture a...” i drugie „nie X, tylko Y” w serii",
        any(b.startswith("opening:") for b in _b) and any(b.startswith("construction:") for b in _b), _b)
_b = sledztwo.sprawdz_notke("Kimi K3.1 Pro scored 67% on an AI test. Who measured it?", [AA_ART],
                            {"teksty_serii": ["Is this AI open yet?"], "encje": ENCJE_KIMI})
sprawdz("KONTRDOWOD: drugie zakonczenie pytaniem w serii", any(b.startswith("ending:") for b in _b), _b)
_b = sledztwo.sprawdz_notke("Kimi K3.1 Pro (a Chinese AI model) scored 67% on the test.", [AA_ART],
                            {"gloss_juz_uzyty": ["Kimi K3.1 Pro"], "encje": ENCJE_KIMI})
sprawdz("KONTRDOWOD: encja objasniona drugi raz w serii", any(b.startswith("gloss:") for b in _b), _b)
_b = sledztwo.sprawdz_notke("Kimi K3.1 Pro scored 67% on the AI test.", [AA_ART],
                            {"liczby_serii": {"67": 2}, "encje": ENCJE_KIMI})
sprawdz("KONTRDOWOD: liczba juz w dwoch notkach serii", any("two notes of this series" in b for b in _b), _b)

# ============================================================================================
print()
print("=== 5. POZIOM TEMATU (spec §5 „Number of notes”) ===")


def karta(n, hosty, pierwotne=0, cena=False):
    tw = []
    for i in range(n):
        h = hosty[i % len(hosty)]
        tw.append({"claim": "Claim %d about the model%s" % (i, " at $3 per million tokens" if cena and i == 0 else ""),
                   "evidence": "Passage %d." % i, "url": "https://%s/%d" % (h, i),
                   "klasa": "PRIMARY" if i < pierwotne else "SECONDARY"})
    return {"confirmed_claims": tw}


def ksiega(odp, dubel=0):
    ks = [{"id": "Q%d" % i, "q": "Question %d?" % i, "soczewka": "NEW", "waga": 1, "status": "answered",
           "zrodla": [{"url": "https://a.example/%d" % i, "quote": "distinct passage %d" % i}]} for i in range(odp)]
    ks += [{"id": "D%d" % i, "q": "Duplicate %d?" % i, "status": "partial",
            "zrodla": [{"url": "https://a.example/0", "quote": "distinct passage 0"}]} for i in range(dubel)]
    return {"ksiega": ks + [{"id": "QX", "q": "Open?", "status": "open"}]}


_hosty6 = ["a.example", "b.example", "c.example", "d.example", "e.example", "f.example"]
_glosy = {"voices": [{"quote": "It fixed real bugs.", "who": "a developer on Hacker News"},
                     {"quote": "It invents APIs.", "who": "a tester on GitHub"}]}
P_PREMIERA = sledztwo.poziom_tematu({"serwisy": 5, "naglowki": [{"punkty": 1065}]},
                                    dict(karta(12, _hosty6[:5], pierwotne=3, cena=True), **_glosy), ksiega(7))
sprawdz("premiera (W 5+1 za HN, A 7, Pr 3, glosy): wzor 6, ale W<9 -> L, n_max 4 (pozycje 5-6 tylko XL)",
        P_PREMIERA["n_wzor"] == 6 and P_PREMIERA["poziom"] == "L" and P_PREMIERA["n_max"] == 4
        and P_PREMIERA["W"] == 6 and P_PREMIERA["na_dobe"] == 3, P_PREMIERA)
P_CIENKA = sledztwo.poziom_tematu({"serwisy": 3}, karta(8, _hosty6[:4]), None)
sprawdz("cienka historia bez zrodla pierwotnego: 2 - 1 -> zacisk 2, poziom S, 2 notki na dobe",
        P_CIENKA["n_max"] == 2 and P_CIENKA["poziom"] == "S" and P_CIENKA["Pr"] == 0 and P_CIENKA["na_dobe"] == 2,
        P_CIENKA)
P_XL = sledztwo.poziom_tematu({"serwisy": 10}, dict(karta(14, _hosty6, pierwotne=2), **_glosy), ksiega(8))
sprawdz("XL: W 10, A 8, Pr 2 -> 6 notek", P_XL["poziom"] == "XL" and P_XL["n_max"] == 6, P_XL)
P_M = sledztwo.poziom_tematu({"serwisy": 6}, karta(8, _hosty6[:4], pierwotne=1, cena=True), ksiega(3))
sprawdz("M: W 6, Pr 1 z cena -> 4", P_M["poziom"] == "M" and P_M["n_max"] == 4, P_M)
P_DUBEL = sledztwo.poziom_tematu({"serwisy": 6}, karta(8, _hosty6[:4], pierwotne=1), ksiega(3, dubel=4))
sprawdz("KONTRDOWOD: pytania z ta sama odpowiedzia licza sie raz (A = 3, nie 7)", P_DUBEL["A"] == 3, P_DUBEL)
sprawdz("ile_katow to cienka nakladka na poziom_tematu",
        sledztwo.ile_katow({"serwisy": 3}, karta(8, _hosty6[:4])) == P_CIENKA["n_max"])
_art_ok, _art_powod = sledztwo.temat_na_artykul({"serwisy": 3}, karta(8, _hosty6[:4]), {"jest": True, "zgodne": True},
                                                [{"rodzaj": "VERDICT"}])
sprawdz("KONTRDOWOD: nowe ustalenie samo nie otwiera artykulu (spec §9 pkt 17)", not _art_ok, _art_powod)
_ks_big = ksiega(7)
_ks_big["ksiega"].append({"id": "QB", "q": "Bigger or smaller?", "soczewka": "BIG", "status": "partial",
                          "zrodla": [{"url": "https://b.example/1", "quote": "the case for bigger"}]})
_art_ok, _art_powod = sledztwo.temat_na_artykul({"serwisy": 6}, dict(karta(12, _hosty6, pierwotne=2), **_glosy), {},
                                                [{"rodzaj": "VERDICT"}], dossier=_ks_big)
sprawdz("artykul: poziom L, 12 twierdzen z 6 hostow, 2 pierwotne, 8 odpowiedzi, werdykt i BIG zbadane",
        _art_ok, _art_powod)

# ============================================================================================
print()
print("=== 6. KATY: PLANISTA, BRAMKI, SKLAD, KOLEJNOSC, HAKI ===")
TW = [
    {"claim": "Acme Labs says Lumen 2 scores 71% on CodeBench 3, behind Rival Pro 4 at 73%",
     "evidence": "On CodeBench 3, Lumen 2 scores 71%, just behind Rival Pro 4 (73%).",
     "url": "https://acme.example/blog/lumen-2", "kind": "VENDOR_CLAIM", "klasa": "PRIMARY"},
    {"claim": "Independent evaluators measured Lumen 2 at 75% on CodeBench 3, the highest of any model",
     "evidence": "Lumen 2 scores 75% on CodeBench 3, the highest score of any model we tested.",
     "url": "https://artificialanalysis.ai/models/lumen-2", "kind": "INDEPENDENT_MEASURE", "klasa": "INDEPENDENT"},
    {"claim": "OpenRouter lists Lumen 2 at $3 per million output tokens",
     "evidence": "Lumen 2 is priced at $3 per million output tokens on OpenRouter.",
     "url": "https://openrouter.ai/acme/lumen-2", "kind": "LISTING", "klasa": "LISTING"},
    {"claim": "Lumen 2 runs on a single gaming GPU", "evidence": "Lumen 2 runs on a single gaming GPU.",
     "url": "https://acme.example/model-card", "kind": "FACT", "klasa": "PRIMARY"},
    {"claim": "Lumen 2 runs its own tests on code before answering",
     "evidence": "Lumen 2 runs its own tests on the code it writes before it answers.",
     "url": "https://acme.example/model-card", "kind": "FACT", "klasa": "PRIMARY"},
    {"claim": "A developer on Hacker News says Lumen 2 fixed real bugs",
     "evidence": "I ran Lumen 2 on my repo for a week and it fixed real bugs.",
     "url": "https://news.ycombinator.com/item?id=1", "kind": "VOICE", "klasa": "VOICE",
     "who": "a developer on Hacker News"},
    {"claim": "Another commenter says Lumen 2 invented an API",
     "evidence": "It also invented an API that does not exist.", "url": "https://news.ycombinator.com/item?id=2",
     "kind": "VOICE", "klasa": "VOICE", "who": "a Hacker News commenter"},
    {"claim": "Acme Labs will release the Lumen 2 weights by December 1",
     "evidence": "Acme Labs will release the Lumen 2 weights by December 1, the company said.",
     "url": "https://acme.example/news/weights", "kind": "VENDOR_CLAIM", "klasa": "PRIMARY"},
    {"claim": "Training took 4 months", "evidence": "Training took 4 months on 2,000 chips.",
     "url": "https://news1.example/a", "kind": "FACT", "klasa": "SECONDARY"},
    {"claim": "OpenRouter lists Rival Pro 4 at $15 per million output tokens",
     "evidence": "Rival Pro 4 costs $15 per million output tokens on OpenRouter.",
     "url": "https://openrouter.ai/rival/pro-4", "kind": "LISTING", "klasa": "LISTING"},
    {"claim": "Lumen 2 generated 90M tokens in evaluation against a 40M median",
     "evidence": "Lumen 2 generated 90M tokens during our evaluation, against a median of 40M.",
     "url": "https://artificialanalysis.ai/models/lumen-2", "kind": "INDEPENDENT_MEASURE", "klasa": "INDEPENDENT"},
    {"claim": "The Lumen 2 preview was downloaded 300,000 times in a week",
     "evidence": "The Lumen 2 preview was downloaded 300,000 times in its first week.",
     "url": "https://news2.example/b", "kind": "FACT", "klasa": "SECONDARY"},
]
KARTA = {"confirmed_claims": TW, "working_thesis": "Lumen 2 is 3x cheaper and 55 points better.",
         "voices": [{"quote": "it fixed real bugs", "who": "a developer on Hacker News", "url": TW[5]["url"]},
                    {"quote": "invented an API that does not exist", "who": "a Hacker News commenter",
                     "url": TW[6]["url"]}],
         "contradictions": ["The maker's score is lower than the independent one."],
         "investigation_plan": {"pytania": [{"id": "Q2", "soczewka": "HOW_IT_WORKS", "q": "How does it check code?"}],
                                "wielkie_pytanie": {"pytanie": "Has open caught up?",
                                                    "wieksze_niz_wyglada": "It runs at home.",
                                                    "mniejsze_niz_wyglada": "One test only."},
                                "rdzen_ai": "Coding AI moves to the desk."}}
DOSSIER = {"ksiega": [
    {"id": "Q1", "soczewka": "NEW", "waga": 1, "status": "answered", "odpowiedz": "It runs on one GPU.",
     "zrodla": [{"url": TW[3]["url"], "quote": "runs on a single gaming GPU"}]},
    {"id": "Q2", "soczewka": "HOW_IT_WORKS", "waga": 1, "status": "answered", "odpowiedz": "It tests its code.",
     "zrodla": [{"url": TW[4]["url"], "quote": "runs its own tests"}]},
    {"id": "Q3", "soczewka": "CLAIM", "waga": 1, "status": "answered", "odpowiedz": "Measured 75%.",
     "zrodla": [{"url": TW[1]["url"], "quote": "scores 75%"}]},
    {"id": "Q4", "soczewka": "NUMBERS", "waga": 2, "status": "answered", "odpowiedz": "$3 vs $15.",
     "zrodla": [{"url": TW[2]["url"], "quote": "$3 per million"}]},
    {"id": "Q5", "soczewka": "PRACTICAL", "waga": 2, "status": "answered", "odpowiedz": "One GPU.",
     "zrodla": [{"url": TW[3]["url"], "quote": "a single gaming GPU"}]},
    {"id": "Q6", "soczewka": "PEOPLE", "waga": 2, "status": "partial", "odpowiedz": "Mixed.",
     "zrodla": [{"url": TW[5]["url"], "quote": "fixed real bugs"}]},
    {"id": "Q7", "soczewka": "BIG", "waga": 1, "status": "partial", "odpowiedz": "Weights by December.",
     "zrodla": [{"url": TW[7]["url"], "quote": "by December 1"}]},
    {"id": "Q8", "soczewka": "WATCH", "waga": 3, "status": "not_yet", "kiedy": "2026-12-01"},
    {"id": "Q9", "soczewka": "POWER", "waga": 2, "status": "open"}]}
H = {"tytul": "Acme ships Lumen 2", "serwisy": 6, "klucze": ["Lumen", "Acme", "AI"], "miejsce": 101,
     "kategoria": "PREMIERA_MODELU",
     "naglowki": [{"temat": "Acme ships Lumen 2, a coding model", "kanal": "Verge", "url": "https://v.example/1"},
                  {"temat": "Lumen 2 review: fast and cheap", "kanal": "Matt", "url": "https://www.youtube.com/watch?v=1"},
                  {"temat": "Lumen 2 is out", "kanal": "Hacker News", "url": "https://news.ycombinator.com/item?id=9",
                   "punkty": 420}]}


def kat(rodzaj, ust, q, wniosek, naglowek, fakty, kierunek="NEUTRAL", lead=False, zalozenie="", sprawdzian=None,
        why="people who write code at home", ai="Shows what coding AI can now do on a desk"):
    return {"rodzaj": rodzaj, "ustalenie": ust, "q": q, "os": "PRACTICAL", "kierunek": kierunek, "wniosek": wniosek,
            "ai_link": ai, "why_care": why, "naglowek": naglowek, "hak": "detail", "fakty": fakty,
            "zalozenie": zalozenie, "sprawdzian": sprawdzian, "lead": lead, "tresc": "Reasoning."}


A = kat("REVEAL", 1, "Q5", "A capable coding model now fits on one gaming GPU",
        "Lumen 2 runs on a single gaming GPU.", [4, 5], "AMPLIFY", lead=True)
B = kat("HOW_IT_WORKS", 2, "Q2", "It tests its own code before it answers",
        "Lumen 2 runs its own tests on the code it writes before it answers.", [5, 1])
C = kat("CLAIM_VS_MEASURED", 3, "Q3", "Independent testers scored it higher than its makers did",
        "Acme Labs says Lumen 2 trails Rival Pro 4, but independent testers measured 75%.", [1, 2], "AMPLIFY")
D = kat("NUMBER_FELT", 4, "Q3", "It tops the coding leaderboard",
        "Lumen 2 posts the highest CodeBench 3 score of any model tested.", [2], "AMPLIFY")
E = kat("VERDICT", 5, "Q7", "By June 2027 open coding models will match closed ones on this test",
        "Lumen 2's weights will be public by December 1, Acme Labs says.", [8, 2], zalozenie="Acme ships on time",
        sprawdzian={"kiedy": "2027-06-30", "co": "an open model within 1 point of the best closed one"})
F = kat("VERDICT", 6, "Q7", "Open models have nearly caught up", "Lumen 2 is close.", [9], zalozenie="x")
G = kat("KURIOZUM", 6, "Q1", "Odd detail", "Lumen 2 took 4 months to train.", [9])
HH = kat("PEOPLE", 4, "Q9", "Rivals are worried", "Rival Pro 4 is worried.", [12])
I = kat("WHO_GAINS_PAYS", 6, "Q4", "Rival labs lose margin", "OpenRouter lists Lumen 2 at $3 per million output tokens.",
        [3], why="investors and rival labs")
J = kat("WHERE_IT_LEADS", 6, "Q4", "Cheaper coding agents will push subscription prices down within a year",
        "OpenRouter lists Lumen 2 at $3 per million output tokens, Rival Pro 4 at $15.", [3, 10],
        zalozenie="rivals match the price", sprawdzian={"kiedy": "2027-10-01", "co": "a major price cut"})
K = kat("PEOPLE", 7, "Q6", "Early users say it fixes real bugs but invents APIs",
        "One developer says the AI fixed real bugs in a week.", [6, 7], why="developers who try new coding tools",
        ai="Shows where coding AI still fails")
L = kat("WHAT_IT_TAKES", 1, "Q5", "You need only one GPU", "Lumen 2 needs one GPU.", [4])
M = kat("REVEAL", 2, "Q2", "Self-testing is the trick", "Lumen 2 tests itself.", [11])
N = kat("POWER_SHIFT", None, "Q1", "The maker's own score undersells it",
        "Lumen 2 was downloaded 300,000 times in its first week.", [12], "DEFLATE")
SEDNO = {"jedno_zdanie": "A coding model that runs on 1 gaming GPU now matches the best closed ones",
         "co_obchodzi": [{"os": "PRACTICAL", "dlaczego": "runs at home", "fakty": [4]},
                         {"os": "MONEY", "dlaczego": "cheap", "fakty": [3, 10]},
                         {"os": "BOGUS", "dlaczego": "x", "fakty": [1]}],
         "zalozenie_czytelnika": {"zalozenie": "closed labs are far ahead", "karta": "OVERTURNS"},
         "werdykt": {"teza": "Open coding models will match closed ones by June 2027", "zalozenie": "weights ship",
                     "kontrargument": "one test only", "sprawdzian": {"kiedy": "2027-06-30", "co": "gap under 1 point"}},
         "za_wiekszym": [2, 4]}
USTALENIA = [{"ustalenie": "Runs on one GPU", "fakty": [4]}, {"ustalenie": "Tests itself", "fakty": [5]},
             {"ustalenie": "Measured above its own claim", "fakty": [1, 2], "do_artykulu": True},
             {"ustalenie": "Tops the board", "fakty": [2]}, {"ustalenie": "Weights by December", "fakty": [8]},
             {"ustalenie": "Price gap", "fakty": [3, 10]}, {"ustalenie": "Users mixed", "fakty": [6, 7]}]
ODP = {"sedno": SEDNO, "ustalenia": USTALENIA, "katy": [A, B, C, D, E, F, G, HH, I, J, K, L, M, N]}
WYWOLANIA = []
NAPRAWA_C = "Acme Labs says Lumen 2 trails Rival Pro 4; independent testers put Lumen 2 at 75%."


def atrapa(odpowiedzi):
    def _call(purpose, system, user, **kw):
        WYWOLANIA.append((purpose, user))
        if purpose in ("przeslania", "przeslania_zapas"):
            o = odpowiedzi[purpose] if isinstance(odpowiedzi.get(purpose), list) else [odpowiedzi.get(purpose)]
            ile = sum(1 for p, _ in WYWOLANIA if p == purpose)
            x = o[min(ile, len(o)) - 1]
            if isinstance(x, Exception):
                raise x
            return x if isinstance(x, str) else json.dumps(x)
        if purpose == "ten_sam_punkt":
            return json.dumps(odpowiedzi.get("ten_sam_punkt") or {"pary": []})
        if purpose == "naglowek_naprawa":
            return json.dumps({"naglowek": NAPRAWA_C if "trails Rival Pro 4" in user
                               else "One developer says the AI fixed bugs in 7 days."})
        raise AssertionError("nieoczekiwany cel %s" % purpose)
    return _call


try:
    # --- bramka przed wywolaniem ---------------------------------------------------------
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": ODP})
    _r, _log = cicho(sledztwo.przeslania, CONN, 1, {"confirmed_claims": TW[:5]}, DOSSIER, H)
    sprawdz("KONTRDOWOD: 5 twierdzen — planista NIE wolany, brak serii",
            _r == [] and not WYWOLANIA and "nie wolany" in _log, (_r, WYWOLANIA, _log))
    _r, _log = cicho(sledztwo.przeslania, CONN, 1, {"confirmed_claims": [dict(c, url="https://one.example/%d" % i)
                                                                          for i, c in enumerate(TW)]}, DOSSIER, H)
    sprawdz("KONTRDOWOD: 12 twierdzen z jednego hosta — tez nie", _r == [] and not WYWOLANIA, WYWOLANIA)

    # --- pelny przebieg ---------------------------------------------------------------------
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": ODP, "ten_sam_punkt": {"pary": [{"a": "N8", "b": "N3", "dlaczego": "same"}]}})
    _karta = json.loads(json.dumps(KARTA))
    SERIA, _log = cicho(sledztwo.przeslania, CONN, 7, _karta, DOSSIER, H, typ="premiera", ile=6)
    _prompt = next(u for p, u in WYWOLANIA if p == "przeslania")
    sprawdz("prompt katow: kazdy numer twierdzenia, ksiega, glosy, naglowki, plan; bez tezy z liczbami",
            all("[%d]" % i in _prompt for i in range(1, 13)) and "[Q9|POWER" in _prompt and "OPEN" in _prompt
            and "a developer on Hacker News" in _prompt and "Lumen 2 is out (420 points" in _prompt
            and "OUR PLAN BEFORE RESEARCH" in _prompt and "Has open caught up?" in _prompt
            and "55" not in _prompt.split("## Evidence card")[1].split("CONFIRMED CLAIMS")[0], _prompt[-1500:])
    sprawdz("prompt katow formatuje sie bez bledu i nie ma zostawionych pol {...}",
            not re.search(r"(?<!\{)\{[a-z_]+\}(?!\})", _prompt))
    _rodzaje = [p["rodzaj"] for p in SERIA]
    sprawdz("seria szesciu: prowadzacy pierwszy, werdykt trzeci, prognoza ostatnia",
            _rodzaje == ["REVEAL", "HOW_IT_WORKS", "VERDICT", "CLAIM_VS_MEASURED", "PEOPLE", "WHERE_IT_LEADS"],
            _rodzaje)
    sprawdz("odrzucone kodem z nazwanym powodem: asekuracja, nieznany tag, pytanie otwarte, czytelnik, rdzen, "
            "ustalenie, ten sam punkt",
            all(x in _log for x in ("hedged takeaway ('nearly')", "unknown angle tag 'KURIOZUM'",
                                    "which research left OPEN", "why_care names no reader",
                                    "core claim [4] already carries", "same finding (ustalenie 2)",
                                    "same point as the note")), _log)
    sprawdz("sklad: drugi kat o wynikach testow nie wchodzi (najwyzej jeden), analiza <= 40%",
            "NUMBER_FELT" not in _rodzaje and sum(1 for p in SERIA if p["rodzaj"] in sledztwo.ANALIZY) == 2)
    sprawdz("brak rundy zwrotnej, gdy sklad pelny i pula wystarcza (jedno wywolanie planisty)",
            sum(1 for p, _ in WYWOLANIA if p == "przeslania") == 1, [p for p, _ in WYWOLANIA])
    _c = SERIA[3]
    sprawdz("hak z bledem wiazania: jedna naprawa Flashem i ponowna bramka -> linia naprawiona",
            _c["linia"] == NAPRAWA_C and _c["wariant"] == "gated" and _c["bramka"]["pierwsza"]
            and _c["bramka"]["po_naprawie"] == [], _c["bramka"])
    _k = SERIA[4]
    sprawdz("hak, ktory nie przeszedl po naprawie: brak stalej linii (W), niesprawdzone zdanie nie jest hakiem",
            _k["linia"] == "" and _k["wariant"] == "W" and _k["bramka"]["po_naprawie"], _k["bramka"])
    sprawdz("naprawa naglowka najwyzej raz na kat (dwa katy z bledem = dwa wywolania)",
            sum(1 for p, _ in WYWOLANIA if p == "naglowek_naprawa") == 2, [p for p, _ in WYWOLANIA])
    sprawdz("kazdy kat ma pola z §4 i zgodnosci, fakty to twierdzenia karty z numerem",
            all(all(f in p for f in ("rodzaj", "q", "os", "kierunek", "wniosek", "ai_link", "why_care", "naglowek",
                                     "hak", "fakty", "zalozenie", "sprawdzian", "lead", "linia", "wariant",
                                     "przeslanie", "tresc", "za", "przeciw", "co_obali"))
                and p["przeslanie"] == p["wniosek"] and p["fakty"][0]["nr"] and "evidence" in p["fakty"][0]
                for p in SERIA) and [p["lead"] for p in SERIA] == [True] + [False] * 5)
    sprawdz("sedno w karcie: bez cyfr, os bez twierdzenia odpada, werdykt przyjety",
            _karta["sedno"]["jedno_zdanie"] == "A coding model that runs on gaming GPU now matches the best closed ones"
            and [x["os"] for x in _karta["sedno"]["co_obchodzi"]] == ["PRACTICAL", "MONEY"]
            and _karta["sedno"]["werdykt_ok"], _karta.get("sedno"))
    sprawdz("ustalenie do artykulu ignorowane, gdy temat nie jest artykulowy", _karta["do_artykulu"] == [])

    # --- runda zwrotna -----------------------------------------------------------------------
    WYWOLANIA.clear()
    PIERWSZA = {"sedno": dict(SEDNO, werdykt={"teza": "Too early to tell", "zalozenie": ""}),
                "ustalenia": USTALENIA, "katy": [A, B, D, HH, F]}
    DRUGA = {"sedno": SEDNO, "ustalenia": USTALENIA, "katy": [A, B, C, E, K]}
    llm.call = atrapa({"przeslania": [PIERWSZA, DRUGA]})
    _s2, _log = cicho(sledztwo.przeslania, CONN, 8, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=4)
    _drugi = [u for p, u in WYWOLANIA if p == "przeslania"]
    sprawdz("runda zwrotna: powody odrzucen, braki skladu i blad werdyktu wracaja do planisty RAZ",
            len(_drugi) == 2 and "Our code checked your answer" in _drugi[1] and "which research left OPEN" in _drugi[1]
            and "we have attributed voices" in _drugi[1] and "werdykt hedges" in _drugi[1]
            and "Your first answer" in _drugi[1], _drugi[1][-1500:] if len(_drugi) > 1 else _drugi)
    sprawdz("po rundzie zwrotnej seria z drugiej odpowiedzi: 4 katy, werdykt trzeci, nie ostatni",
            [p["rodzaj"] for p in _s2] == ["REVEAL", "HOW_IT_WORKS", "VERDICT", "PEOPLE"], [p["rodzaj"] for p in _s2])

    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": [{"katy": [A]}, {"katy": [A, G]}]})
    _s3, _log = cicho(sledztwo.przeslania, CONN, 9, json.loads(json.dumps(KARTA)), DOSSIER, H)
    sprawdz("KONTRDOWOD: jeden kat po bramkach i rundzie zwrotnej — brak serii (N < 2)",
            _s3 == [] and "za malo katow na serie" in _log and sum(1 for p, _ in WYWOLANIA if p == "przeslania") == 2,
            _log[-400:])

    # --- artykulowy: ustalenie zarezerwowane ---------------------------------------------------
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": ODP})
    _karta_a = json.loads(json.dumps(KARTA))
    _s4, _log = cicho(sledztwo.przeslania, CONN, 10, _karta_a, DOSSIER, H, ile=6, artykulowy=True)
    sprawdz("temat artykulowy: ustalenie do_artykulu w karcie, kat na nim odpada z powodu",
            [u["ustalenie"] for u in _karta_a["do_artykulu"]] == ["Measured above its own claim"]
            and "CLAIM_VS_MEASURED" not in [p["rodzaj"] for p in _s4] and "reserved for our article" in _log,
            ([p["rodzaj"] for p in _s4], _log[-600:]))

    # --- odmowa, uciecie, proza, budzet ----------------------------------------------------------
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": llm.OdmowaDostawcy("dostawca odmówił: cyber"), "przeslania_zapas": ODP})
    _s5, _log = cicho(sledztwo.przeslania, CONN, 11, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=6)
    sprawdz("odmowa Opusa: katy pisze zapas, log to mowi", len(_s5) == 6 and "nie dal katow" in _log
            and [p for p, _ in WYWOLANIA if p.startswith("przeslania")] == ["przeslania", "przeslania_zapas"], _log[-300:])
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": llm.Truncated("max_tokens"), "przeslania_zapas": ODP})
    _s6, _ = cicho(sledztwo.przeslania, CONN, 12, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=6)
    sprawdz("uciecie na suficie: tez zapas", len(_s6) == 6)
    WYWOLANIA.clear()
    _proza = "Here is my plan for the series of notes. " * 10
    llm.call = atrapa({"przeslania": [_proza, ODP]})
    _s7, _log = cicho(sledztwo.przeslania, CONN, 13, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=6)
    sprawdz("odpowiedz proza: ratunek JSON-u (llm.ratuj_json), katy nie przepadaja",
            len(_s7) == 6 and "brak JSON" in _log, _log[-300:])
    llm.call = atrapa({"przeslania": llm.BudgetExceeded("limit")})
    try:
        cicho(sledztwo.przeslania, CONN, 14, json.loads(json.dumps(KARTA)), DOSSIER, H)
        _przeszlo = False
    except llm.BudgetExceeded:
        _przeszlo = True
    sprawdz("budzet przechodzi na wylot (PRZERYWAJA), nie jest polykany", _przeszlo)

    # --- ten sam punkt wobec 14 dni ----------------------------------------------------------
    (config.DATA_DIR / "dziennik.jsonl").write_text(json.dumps(
        {"kiedy": (TERAZ - timedelta(days=2)).isoformat(), "rodzaj": "notka", "udane": True, "typ": "MYSL",
         "id": 77, "tekst": "We think coding models are moving onto ordinary desks."}) + "\n", encoding="utf-8")
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": ODP, "ten_sam_punkt": {"pary": [{"a": "N1", "b": "P1", "dlaczego": "same"}]}})
    _s8, _log = cicho(sledztwo.przeslania, CONN, 15, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=6)
    _tsp = next(u for p, u in WYWOLANIA if p == "ten_sam_punkt")
    sprawdz("ten_sam_punkt dostaje nasze notki z 14 dni; kat powtarzajacy opublikowana MYSL odpada",
            "P1 [PUBLISHED] We think coding models" in _tsp and "REVEAL" not in [p["rodzaj"] for p in _s8]
            and "same point as our note published" in _log, (_tsp[-400:], [p["rodzaj"] for p in _s8]))
    (config.DATA_DIR / "dziennik.jsonl").unlink()
    WYWOLANIA.clear()
    llm.call = atrapa({"przeslania": {"sedno": SEDNO, "ustalenia": USTALENIA, "katy": [
        A, B, dict(C, wniosek="It tests its own code before it answers, every time")]},
        "ten_sam_punkt": RuntimeError("padlo")})

    def _tsp_pada(purpose, system, user, **kw):
        if purpose == "ten_sam_punkt":
            raise RuntimeError("padlo")
        return atrapa({"przeslania": {"sedno": SEDNO, "ustalenia": USTALENIA, "katy": [
            A, B, dict(C, wniosek="It tests its own code before it answers, every time")]}})(purpose, system, user, **kw)
    llm.call = _tsp_pada
    _s9, _log = cicho(sledztwo.przeslania, CONN, 16, json.loads(json.dumps(KARTA)), DOSSIER, H, ile=3)
    sprawdz("awaria ten_sam_punkt: zostaje porownanie slow kodem (ta sama mysl innymi slowami odpada)",
            "zostaje porownanie slow" in _log and "same point as the note" in _log, _log[-600:])
finally:
    llm.call = _prawdziwy_call

# ============================================================================================
print()
print("=== 7. KOLEJKA: KLUCZE, POZIOM, SUFIT DOBY, PROBY, STARE WPISY ===")
P_KOL = sledztwo.poziom_tematu(H, KARTA, DOSSIER)
_wpisy = [dict(p) for p in SERIA]
_wpisy.insert(2, {"wniosek": "zly kat bez rodzaju"})
_ile, _log = cicho(sledztwo.dodaj_do_kolejki, _wpisy, H, KARTA, run_id=21, poziom=dict(P_KOL, na_dobe=2))
_kol = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
sprawdz("zly kat odpada z logiem, reszta (6) wchodzi", _ile == 6 and len(_kol) == 6 and "odpada" in _log, _log)
sprawdz("wpis ma klucze, poziom, na_dobe, proby, linie, wariant, lead, k/n i identyfikator z tagiem",
        all(set(("klucze", "poziom", "na_dobe", "proby", "linia", "wariant", "lead", "k", "n")) <= set(p) for p in _kol)
        and _kol[0]["klucze"] == ["Lumen", "Acme"] and _kol[0]["na_dobe"] == 2 and _kol[0]["lead"]
        and _kol[0]["id"].endswith("-21-1-reveal") and [p["k"] for p in _kol] == [1, 2, 3, 4, 5, 6]
        and _kol[4]["wariant"] == "W" and _kol[4]["perspektywa"]["naglowek"] == "", _kol[0])


def dziennik(*notki):
    (config.DATA_DIR / "dziennik.jsonl").write_text("".join(json.dumps(dict(
        {"rodzaj": "notka", "udane": True}, **n)) + "\n" for n in notki), encoding="utf-8")


dziennik()
_p = sledztwo.wez_przeslanie()
sprawdz("tego samego dnia: prowadzacy z kluczami wychodzi, gdy zadna dzisiejsza notka ich nie ma",
        (_p or {}).get("k") == 1, _p)
dziennik({"kiedy": TERAZ.isoformat(), "tekst": "Acme just shipped something new for AI coders."})
sprawdz("KONTRDOWOD: dzisiejsza notka z kluczem historii — prowadzacy czeka do jutra",
        sledztwo.wez_przeslanie() is None)
_bez_kluczy = json.loads(json.dumps(_kol))
for p in _bez_kluczy:
    p["klucze"] = []
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_bez_kluczy), encoding="utf-8")
dziennik()
sprawdz("KONTRDOWOD: bez kluczy prowadzacy nie wychodzi tego samego dnia (nie da sie sprawdzic)",
        sledztwo.wez_przeslanie() is None)
for p in _kol:
    p["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
_ids = [p["id"] for p in _kol]
dziennik({"kiedy": TERAZ.isoformat(), "przeslanie_id": _ids[0]}, {"kiedy": TERAZ.isoformat(), "przeslanie_id": _ids[1]})
sprawdz("sufit doby = min(PRZESLAN_NA_DOBE, na_dobe): przy na_dobe 2 po dwoch notkach — koniec na dzis",
        sledztwo.wez_przeslanie() is None)
for p in _kol:
    p["na_dobe"] = 3
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
sprawdz("przy na_dobe 3 trzecia notka serii tego dnia wychodzi (k=3)", (sledztwo.wez_przeslanie() or {}).get("k") == 3)
sprawdz("KONTRDOWOD: w dzien promocji artykulu sufit serii 2 (spec §5)", sledztwo.wez_przeslanie(promocja=True) is None)
dziennik({"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[0]},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[1]})
_, _log = cicho(sledztwo.oznacz_probe, _ids[2], "notka oblala bramke: numbers")
sprawdz("jedna nieudana proba: kat dalej czeka na swoja kolej", (sledztwo.wez_przeslanie() or {}).get("k") == 3)
_, _log = cicho(sledztwo.oznacz_probe, _ids[2], "notka oblala wiernosc")
_kol2 = json.loads((config.DATA_DIR / sledztwo.PLIK_KOLEJKI).read_text(encoding="utf-8"))
sprawdz("po dwoch probach kat pominiety z powodami i nie blokuje czola: idzie k=4",
        _kol2[2]["pominiety"] and len(_kol2[2]["powody_prob"]) == 2 and "pominiety po 2" in _log
        and (sledztwo.wez_przeslanie() or {}).get("k") == 4 and sledztwo.czekajace_przeslania() == 3,
        (sledztwo.czekajace_przeslania(), _log))
cicho(sledztwo.oznacz_probe, "nie-ma-takiego", "x")
sprawdz("oznacz_probe na nieznanym kacie nie wywala", True)
_p4 = sledztwo.wez_przeslanie()
_fakt, _mat = sledztwo.material_notki(_p4)
sprawdz("material notki: bez tezy sledztwa, linia kata jako first_line, tylko twierdzenia kata",
        "thesis" not in _mat["investigation"] and "55" not in json.dumps(_mat)
        and _mat["investigation"]["first_line"] == _p4["linia"]
        and [c["nr"] for c in _mat["investigation"]["supporting_claims"]] == [c["nr"] for c in _p4["fakty"]]
        and _mat["investigation"]["position"] == "4/6", _mat["investigation"])
sprawdz("material wie, jakie katy tej historii juz wyszly", [k["angle"] for k in
                                                            _mat["investigation"]["earlier_angles_already_published"]]
        == ["REVEAL", "HOW_IT_WORKS"], _mat["investigation"]["earlier_angles_already_published"])
dziennik({"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[0],
          "tekst": "Lumen 2 runs on a single gaming GPU. Acme Labs, a small AI lab, built it."},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[1], "tekst": "It tests itself, 75% of the time."})
_kt = sledztwo.kontekst_notki(_p4)
sprawdz("kontekst bramki notki: teksty serii, liczby serii, encje juz objasnione",
        len(_kt["teksty_serii"]) == 2 and _kt["liczby_serii"].get("75") == 1 and "Acme" in _kt["gloss_juz_uzyty"], _kt)
_b = sledztwo.sprawdz_notke("Acme (a small AI lab) says the AI fixed real bugs.", _p4["fakty"], _p4)
sprawdz("sprawdz_notke przyjmuje sam wpis kolejki jako kontekst (linia, glosa raz na serie)",
        any(b.startswith("gloss: Acme") for b in _b), _b)

# STARE WPISY: kolejka produkcyjna sprzed fali 1 (KURIOZUM, LICZBY, MECHANIZM) musi dac sie wydac.
STARY = [{"id": "202610241313-512-%s" % r.lower(), "rodzaj": r, "typ_notki": t, "historia": "Stara historia",
          "kiedy": (TERAZ - timedelta(days=1)).isoformat(), "kolejnosc": i,
          "wazny_do": (TERAZ + timedelta(days=2)).isoformat(), "styk": "branza", "radar_miejsce": 3,
          "perspektywa": {"rodzaj": r, "przeslanie": "Old message %d" % i, "naglowek": "Unchecked old line %d" % i,
                          "hak": "old hook"},
          "fakty": [{"claim": "Old claim", "evidence": "old evidence", "url": "https://old.example/x"}],
          "teza_sledztwa": "Old thesis with 55 points."}
         for i, (r, t) in enumerate((("KURIOZUM", "CIEKAWOSTKA"), ("LICZBY", "CIEKAWOSTKA"), ("MECHANIZM", "CIEKAWOSTKA")))]
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(STARY), encoding="utf-8")
dziennik()
_ps = sledztwo.wez_przeslanie()
_fs, _ms = sledztwo.material_notki(_ps)
sprawdz("stary wpis (KURIOZUM) wychodzi, typ notki ze wpisu, bez tezy i bez niesprawdzonego naglowka",
        _ps["rodzaj"] == "KURIOZUM" and _ps["typ_notki"] == "CIEKAWOSTKA" and "55" not in json.dumps(_ms)
        and _ms["perspective"]["naglowek"] == "" and _ms["perspective"]["przeslanie"] == "Old message 0"
        and _fs["url"] == "https://old.example/x", (_ps, _ms))
dziennik({"kiedy": TERAZ.isoformat(), "przeslanie_id": STARY[0]["id"]})
sprawdz("drugi stary wpis (LICZBY) po pierwszym; czeka dwa", (sledztwo.wez_przeslanie() or {}).get("rodzaj") == "LICZBY"
        and sledztwo.czekajace_przeslania() == 2)
_ks = sledztwo.kontekst_notki(sledztwo.wez_przeslanie())
sprawdz("stary wpis w kontekscie notki tez dziala (bez kluczy i linii)", _ks["linia"] == "" and _ks["encje"] == [])

# ============================================================================================
print()
print("=== 8. MYSL: TEMATY OBOK, KLUCZE SERII, OPUBLIKOWANE KATY ===")
(config.DATA_DIR / sledztwo.PLIK_KOLEJKI).write_text(json.dumps(_kol), encoding="utf-8")
sprawdz("klucze serii z waznej kolejki", sledztwo.klucze_serii() == ["Lumen", "Acme"], sledztwo.klucze_serii())
sledztwo.zapisz_sledztwo({"run_id": 21, "historia": "Acme ships Lumen 2", "zrodla": [], "klucze": ["Lumen", "Acme"],
                          "ranking": [{"tytul": "Acme ships Lumen 2", "kategoria": "PREMIERA_MODELU", "wynik": 4.1},
                                      {"tytul": "Courts weigh an AI copyright case", "kategoria": "POLITYKA_PRAWO"},
                                      {"tytul": "Lumen 2 benchmarks leak early", "kategoria": "PREMIERA_MODELU"},
                                      {"tytul": "Teachers try AI tutors in class", "kategoria": "SPOLECZENSTWO"}]})
sprawdz("tematy obok: ranking bez wybranej historii i bez tytulow z kluczami serii",
        sledztwo.tematy_obok() == ["Courts weigh an AI copyright case", "Teachers try AI tutors in class"],
        sledztwo.tematy_obok())
sprawdz("tematy obok: limit", sledztwo.tematy_obok(1) == ["Courts weigh an AI copyright case"])
dziennik({"kiedy": (TERAZ - timedelta(days=20)).isoformat(), "przeslanie_id": "stary-1-1-reveal", "tekst": "stara"},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[0], "tekst": "Lumen 2 note"},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "przeslanie_id": _ids[0], "tekst": "Lumen 2 note"},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "typ": "MYSL", "id": 5, "tekst": "We bet on boring AI."},
         {"kiedy": (TERAZ - timedelta(days=1)).isoformat(), "typ": "CIEKAWOSTKA", "id": 6, "tekst": "bank fact"})
_op = sledztwo.opublikowane_katy(14)
sprawdz("opublikowane katy: notki serii (raz) i MYSL z 14 dni, z wnioskiem kata z kolejki; bank i stare nie",
        [o["typ"] or o["rodzaj"] for o in _op] == ["REVEAL", "MYSL"] and _op[0]["wniosek"] == A["wniosek"]
        and _op[1]["tekst"] == "We bet on boring AI.", _op)
(config.DATA_DIR / "dziennik.jsonl").unlink()
sprawdz("tabela odbioru bez danych: mowi to wprost, nie wymysla", "not enough" in sledztwo._odbior_do_promptu()
        or "no measured" in sledztwo._odbior_do_promptu(), sledztwo._odbior_do_promptu())
_tydzien = TERAZ - timedelta(days=10)
# Sroda tego tygodnia w poludnie: notki w jednym tygodniu ISO i co najmniej 3-dniowe.
_tydzien = (_tydzien - timedelta(days=_tydzien.weekday() - 2)).replace(hour=12, minute=0)
_notki = []
_stat = []
for i, (pid, wysw) in enumerate((("202610101313-5-1-reveal", 40), ("202610101313-5-2-verdict", 5),
                                 ("202610101313-5-3-people", 20), ("202610101313-5-4-how_it_works", 9),
                                 ("", 10), ("", 10), ("", 12))):
    _notki.append({"kiedy": (_tydzien + timedelta(minutes=i)).isoformat(), "id": 900 + i, "przeslanie_id": pid or None,
                   "tekst": "Note %d text" % i})
    _stat.append({"rodzaj": "notka", "id": 900 + i, "wyswietlenia": wysw})
dziennik(*_notki)
(config.DATA_DIR / "statystyki.jsonl").write_text("".join(json.dumps(s) + "\n" for s in _stat), encoding="utf-8")
_odb = sledztwo._odbior_do_promptu(ile=2)
sprawdz("tabela odbioru: przyrost wobec mediany tygodnia, najlepsze i najslabsze notki serii z tagiem",
        _odb.startswith("Best:\n- lift 4.00 | REVEAL | Note 0 text") and "Worst:" in _odb
        and _odb.rstrip().endswith("VERDICT | Note 1 text") and "lift 0.45" in _odb and "PEOPLE" in _odb, _odb)
(config.DATA_DIR / "dziennik.jsonl").unlink()
(config.DATA_DIR / "statystyki.jsonl").unlink()

# ============================================================================================
print()
print("=== 9. NOWOSC: DWA PRZEBIEGI, PRZYCZYNA Z CYTATEM ===")
KARTA_N = {"confirmed_claims": [
    {"claim": "Breach on 18 June", "evidence": "June 18: breached", "url": "https://www.abc.net.au/t"},
    {"claim": "Company aware on 11 August", "evidence": "August 11: aware", "url": "https://www.abc.net.au/t"},
    {"claim": "Framework of 16 September favours disclosure", "evidence": "favors disclosure",
     "url": "https://www.transformernews.ai/p"}]}
HN_ = {"naglowki": [{"temat": "Agent breach", "kanal": "ABC"}]}
DOBRE = {"jest": True, "ustalenie": "It published a pro-disclosure framework while silent on a breach it knew about.",
         "twierdzenia": [2, 3], "dlaczego_nie_w_jednym": "timeline in ABC, framework in Transformer"}
NOW = []


def nowosc_atrapa(*odp):
    def _call(purpose, system, user, **kw):
        assert purpose == "nowosc", purpose
        NOW.append(user)
        return json.dumps(odp[min(len(NOW), len(odp)) - 1])
    return _call


try:
    NOW.clear()
    llm.call = nowosc_atrapa(DOBRE, dict(DOBRE, twierdzenia=[3, 2]))
    _n = sledztwo.nowosc(CONN, None, KARTA_N, HN_)
    sprawdz("dwa zgodne przebiegi: jest, zgodne", _n["jest"] and _n.get("zgodne") and len(NOW) == 2, _n)
    sprawdz("prompt nowosci ma regule like-for-like i pole cytatu przyczyny",
            "Like for like" in NOW[0] and "cytat_przyczyny" in NOW[0])
    NOW.clear()
    llm.call = nowosc_atrapa(DOBRE, {"jest": False, "dlaczego_nie_w_jednym": "all in one report"})
    _n = sledztwo.nowosc(CONN, None, KARTA_N, HN_)
    sprawdz("KONTRDOWOD: drugi przebieg mowi „nie” — nie ma ustalenia", not _n["jest"] and "nie zgadzaja" in _n["powod"], _n)
    NOW.clear()
    llm.call = nowosc_atrapa(DOBRE, dict(DOBRE, twierdzenia=[1, 3]))
    sprawdz("zgodne, gdy przebiegi dziela twierdzenie (2 i 3 wobec 1 i 3)", sledztwo.nowosc(CONN, None, KARTA_N, HN_)["jest"])
    NOW.clear()
    llm.call = nowosc_atrapa({"jest": False, "dlaczego_nie_w_jednym": "nothing new"})
    _n = sledztwo.nowosc(CONN, None, KARTA_N, HN_)
    sprawdz("pierwszy przebieg „nie” — drugiego nie ma (oszczednosc)", not _n["jest"] and len(NOW) == 1)
    NOW.clear()
    _przycz = dict(DOBRE, ustalenie="The framework was published because the breach was about to leak.")
    llm.call = nowosc_atrapa(_przycz)
    _n = sledztwo.nowosc(CONN, None, KARTA_N, HN_)
    sprawdz("KONTRDOWOD: czasownik przyczynowy bez cytatu ze zrodla", not _n["jest"] and "przyczynowy" in _n["powod"], _n)
    NOW.clear()
    _przycz_c = dict(_przycz, cytat_przyczyny="the framework was rushed out because the breach was about to leak")
    llm.call = nowosc_atrapa(_przycz_c)
    _n = sledztwo.nowosc(CONN, None, KARTA_N, HN_, teksty_zrodel={
        "https://x.example": "Insiders say the framework was rushed out because the breach was about to leak."})
    sprawdz("czasownik przyczynowy z dosłownym cytatem ze zrodla przechodzi", _n["jest"], _n)
finally:
    llm.call = _prawdziwy_call

# ============================================================================================
print()
print("=== 10. PROMPTY CZESCI K FORMATUJA SIE ===")
for nazwa in ("przeslania.md", "nowosc.md", "ten_sam_punkt.md", "naglowek_naprawa.md"):
    _surowy = (pathlib.Path("agent-v2/prompts") / nazwa).read_text(encoding="utf-8")
    _pola = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", _surowy))
    try:
        _surowy.format(**{p: "x" for p in _pola})
        _ok = True
    except (KeyError, ValueError, IndexError) as exc:
        _ok = exc
    sprawdz("%s formatuje sie bez bledu (pola: %s)" % (nazwa, ", ".join(sorted(_pola))), _ok is True, _ok)
_kp = sledztwo._karta_do_promptu({"confirmed_claims": [{"claim": "c%d" % i, "evidence": "e" * 900, "url": "u"}
                                                       for i in range(16)], "not_established": ["gap"] * 6},
                                 limit=6000)
sprawdz("karta w prompcie: 16 twierdzen z numerami nawet przy ciasnym limicie, braki na gorze",
        all("[%d] c%d" % (i + 1, i) in _kp for i in range(16)) and _kp.index("NOT ESTABLISHED") < _kp.index("[1]")
        and len(_kp) <= 6000, len(_kp))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
