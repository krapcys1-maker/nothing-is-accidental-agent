# -*- coding: utf-8 -*-
"""Karta sledztwa, notki serii, MYSL i weryfikacja bez JSON-u — fala 1 (25.10.2026).

PO CO. Proby sledztwa z 25.10 (premiera modelu, luka bezpieczenstwa, finanse
centrow danych) pokazaly cztery rzeczy, ktorych prosba w prompcie nie zalatwila:
  * karta przyjmowala twierdzenia, ktorych cytat nie stal w zrodle, a klasy zrodel
    nadawal model (strona o innym modelu jako PRIMARY);
  * notki serii zakopywaly najlepsze zdanie i mialy znieksztalcenia, ktorych
    weryfikator w sieci nie zlapal;
  * dwie z trzech MYSLI mowily „I", a MYSL o serii powtorzyla jej liczby;
  * sprawdzenie artykulu oddalo proze i zapisalo sie jako „czysto".

Test pilnuje ZACHOWANIA, kazde z kontrdowodem:
  1. reguly tekstu: pierwsza osoba poza cytatami, zakazy MYSL, pierwsze zdanie;
  2. klasy zrodel kodem (`klasa_zrodla`);
  3. `sprawdz_karte`: cytat doslownie z tego samego adresu, liczby w cytacie,
     rodzaj nie do podniesienia, `as_of` tylko z dat znanych kodowi, glosy;
  4. synteza w trybie sledczym: 16 twierdzen, sloty nie wypadaja;
  5. weryfikacja bez JSON-u: ratunek, ponowka „JSON first", nigdy `safe_to_post`;
  6. wiernosc notki wobec twierdzen kata;
  7. `note` z bramka: jedna poprawka, potem odrzucenie; notka serii bez rozbioru,
     wiernosc PRZED sprawdzeniem w sieci, zdanie po bramce w prompcie;
  8. naprawa nie przepisuje liczby z karty;
  9. `notki_dnia`: MYSL bez tematu serii, z historiami obok; MYSL po porazce -> fakt
     z banku; notka serii: pisarz wg D1, bramki, `oznacz_probe` i zwykla notka
     w tym miejscu; stare wpisy kolejki nadal wydawalne;
 10. weryfikator dostaje WSZYSTKIE twierdzenia kata, czasowe oznaczone.

Nazwy z prob (Kimi, Moonshot itd.) wystepuja tu WYLACZNIE jako dane testowe.
BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_notki_sledcze.py
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import glebia   # noqa: E402
import llm      # noqa: E402
import sledztwo  # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


@contextlib.contextmanager
def podmiana(obiekt, **atrybuty):
    """Podstawia atrybuty na czas bloku i przywraca je (takze nieistniejace wczesniej)."""
    brak = object()
    stare = {k: getattr(obiekt, k, brak) for k in atrybuty}
    for k, v in atrybuty.items():
        setattr(obiekt, k, v)
    try:
        yield
    finally:
        for k, v in stare.items():
            if v is brak:
                delattr(obiekt, k)
            else:
                setattr(obiekt, k, v)


def cicho(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as bufor:
        wynik = f(*a, **k)
    return wynik, bufor.getvalue()


print("=== 1. REGULY TEKSTU ===")
sprawdz("„I think” to pierwsza osoba", stages.pierwsza_osoba("I think this matters.") == ["I"])
sprawdz("„my”, „me”, „I'm”, „myself” tez",
        sorted(stages.pierwsza_osoba("My bet: it hit me. I'm sure. I did it myself.")) ==
        ["I", "I'm", "My", "me", "myself"], stages.pierwsza_osoba("My bet: it hit me. I'm sure. I did it myself."))
sprawdz("glos publikacji przechodzi", stages.pierwsza_osoba("We think our bet holds; us too.") == [])
sprawdz("cytat z „I” nie liczy sie", stages.pierwsza_osoba('The founder said "I was wrong" and left.') == [])
sprawdz("cyfra rzymska nie jest osoba (Type I, World War I, Phase I)",
        stages.pierwsza_osoba("A Type I error, World War I and Phase I trials.") == [])
sprawdz("AI, I/O, ME nie sa osoba", stages.pierwsza_osoba("AI chips, I/O limits, the ME market.") == [])
sprawdz("KONTRDOWOD: kropka przed „I” nie robi z niego cyfry rzymskiej",
        stages.pierwsza_osoba("It ended in phase. I think so.") == ["I"])

KLUCZE = ["Kimi K3.1 Pro", "Moonshot AI", "Pentagon AI contract"]
sprawdz("czysta MYSL przechodzi",
        stages.bramka_mysli("We think cheap models change who gets to build. Our bet: plenty.", KLUCZE) == [])
_p = stages.bramka_mysli("I think Kimi beats the others 3 times over.", KLUCZE)
sprawdz("cyfry, nazwa serii i „I” — trzy problemy", len(_p) == 3
        and "digits" in _p[0] and "Kimi K3.1 Pro" in _p[1] and "first person" in _p[2], _p)
sprawdz("zwykle slowo z klucza („contract”) nie jest nazwa serii",
        stages.bramka_mysli("We think every contract hides a bet.", KLUCZE) == [])
sprawdz("KONTRDOWOD: wlasna nazwa z klucza („Pentagon”) jest",
        bool(stages.bramka_mysli("We think the Pentagon wants cheaper chips.", KLUCZE)))
sprawdz("bez kluczy serii MYSL sprawdza tylko cyfry i osobe",
        stages.bramka_mysli("Kimi is interesting, we think.", []) == [])

LINIA = "Kimi K3.1 Pro's makers say it narrowly loses to Claude Opus 5.5 at command-line coding."
sprawdz("pierwsze zdanie zachowane doslownie",
        stages.zachowuje_pierwsze_zdanie(LINIA + " Their own table says so.", LINIA))
sprawdz("wolno dokleic nastepne zdanie myslnikiem",
        stages.zachowuje_pierwsze_zdanie(LINIA[:-1] + " — and the independent test disagrees.", LINIA))
sprawdz("typograficzny apostrof i biale znaki to to samo zdanie",
        stages.zachowuje_pierwsze_zdanie(LINIA.replace("'", "’").replace(" ", "  ", 1) + " More.", LINIA))
sprawdz("KONTRDOWOD: zmienione slowo to inne zdanie",
        not stages.zachowuje_pierwsze_zdanie(LINIA.replace("narrowly", "slightly") + " x", LINIA))
sprawdz("KONTRDOWOD: zdanie przesuniete na koniec nie jest pierwsze",
        not stages.zachowuje_pierwsze_zdanie("Here is a story. " + LINIA, LINIA))
sprawdz("puste zdanie po bramce (wariant W) nie wymaga niczego",
        stages.zachowuje_pierwsze_zdanie("Anything at all.", ""))
sprawdz("pierwsze zdanie notki do logu", stages.pierwsze_zdanie_tekstu("One. Two.") == "One.")

print()
print("=== 2. KLASY ZRODEL NADAJE KOD ===")
K = ["Kimi K3.1 Pro"]
for opis, url, tekst, klucze, rekord, oczekiwana in (
        ("strona aktora o tym modelu", "https://kimi.ai/blog/kimi-k3-1-pro",
         "Kimi K3.1 Pro: our new model", K, None, "PRIMARY"),
        ("strona aktora o poprzedniku", "https://kimi.ai/blog/kimi-k2",
         "Kimi K2 launch notes", K, None, "SECONDARY"),
        ("ewaluator o innym modelu nazwany strona innej firmy", "https://labs.scale.com/leaderboard",
         "Kimi K3.1 Pro on our leaderboard", K, None, "SECONDARY"),
        ("arXiv o tym modelu", "https://arxiv.org/abs/2610.00001",
         "Technical report of Kimi K3.1 Pro", K, None, "PRIMARY"),
        ("arXiv o innym modelu", "https://arxiv.org/abs/2610.00002",
         "Scaling laws for Kimi K2", K, None, "SECONDARY"),
        ("rekord nazwany adresem", "https://platform.moonshot.ai/docs/pricing",
         "Kimi K3.1 Pro pricing", K, "pricing page at platform.moonshot.ai", "PRIMARY"),
        ("niezalezny ewaluator", "https://artificialanalysis.ai/models/kimi-k3-1-pro",
         "anything", K, None, "INDEPENDENT"),
        ("odsprzedawca", "https://openrouter.ai/moonshotai/kimi-k3.1-pro", "x", K, None, "LISTING"),
        ("watek HN", "https://news.ycombinator.com/item?id=1", "Kimi K3.1 Pro", K, None, "VOICE"),
        ("dyskusja HF", "https://huggingface.co/moonshotai/Kimi-K3.1-Pro/discussions/4",
         "Kimi K3.1 Pro", K, None, "VOICE"),
        ("issue na GitHubie", "https://github.com/moonshotai/kimi/issues/12", "Kimi K3.1 Pro", K, None,
         "VOICE"),
        ("rejestr z kluczem", "https://www.sec.gov/Archives/x.htm", "Filing mentions Kimi K3.1 Pro", K,
         None, "PRIMARY"),
        ("prasa", "https://www.theverge.com/ai/kimi", "Kimi K3.1 Pro is here", K, None, "SECONDARY"),
        ("KONTRDOWOD: bez kluczy domena aktora nie wystarcza", "https://kimi.ai/blog/kimi-k3-1-pro",
         "Kimi K3.1 Pro", [], None, "SECONDARY")):
    sprawdz("%-52s -> %s" % (opis, oczekiwana),
            stages.klasa_zrodla(url, tekst, klucze, rekord) == oczekiwana,
            stages.klasa_zrodla(url, tekst, klucze, rekord))
sprawdz("klucz bez wersji: wystarczy nazwa",
        stages.klasa_zrodla("https://openai.com/index/x", "OpenAI announces", ["OpenAI"], None) == "PRIMARY")

print()
print("=== 3. KARTA SPRAWDZANA KODEM ===")
AA = "https://artificialanalysis.ai/models/kimi-k3-1-pro"
BLOG = "https://kimi.ai/blog/kimi-k3-1-pro"
SW = "https://simonwillison.net/2026/Oct/23/kimi-k31-pro/"
OR = "https://openrouter.ai/moonshotai/kimi-k3.1-pro"
HN = "https://news.ycombinator.com/item?id=9"
DOWODY = [
    {"url": AA, "title": "Kimi K3.1 Pro - Intelligence, Performance & Price Analysis",
     "class": "PRIMARY", "data": "2026-10-23",
     "excerpts": ["While evaluating the Intelligence Index, it generated 150M tokens, which is very "
                  "verbose in comparison to the median of 87M.",
                  "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%"]},
    {"url": BLOG, "title": "Kimi K3.1 Pro", "class": "PRIMARY",
     "excerpts": ["On Terminal-Bench 4.0 it scores 65.7%, narrowly behind Claude Opus 5.5 (66.4%)."]},
    {"url": SW, "title": "Kimi K3.1 Pro", "class": "SUPPORTING", "data": "2026-10-23",
     "excerpts": ["it's not yet open weights, but Moonshot promise 'Full model weights will be released "
                  "by Nov 4, 2026'", "Simon Willison notes $10 per million output tokens."]},
    {"url": OR, "title": "OpenRouter listing", "class": "SUPPORTING",
     "excerpts": ["Kimi K3.1 Pro: $2 per million input tokens, $10 per million output tokens."]},
    {"url": HN, "title": "Kimi K3.1 Pro thread", "class": "SUPPORTING",
     "excerpts": ["jdoe: I ran it on my repo and it is the first open model that fixed the build."]},
]
KARTA = {
    "working_thesis": "x",
    "confirmed_claims": [
        {"claim": "Artificial Analysis measured 67% on Terminal-Bench 4.0, the highest of any model.",
         "evidence": "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%",
         "url": AA + "/", "kind": "INDEPENDENT_MEASURE", "as_of": "2026-10-23", "q": "Q2",
         "slot": "PRIMARY_NUMBER"},
        {"claim": "The makers report 65.7%, behind Claude Opus 5.5 at 66.4%.",
         "evidence": "it scores 65.7%, narrowly behind Claude Opus 5.5 (66.4%)",
         "url": BLOG, "kind": "INDEPENDENT_MEASURE", "as_of": "2025-01-01"},
        {"claim": "It generated 150M tokens against a median of 87M.",
         "evidence": "it generated 150M tokens ... median of 87M", "url": "http://artificialanalysis.ai/models/kimi-k3-1-pro?utm_source=x",
         "kind": "FACT"},
        {"claim": "Weights are not out yet; release promised by Nov 4.",
         "evidence": "it's not yet open weights, but Moonshot promise 'Full model weights will be released by Nov 4, 2026'",
         "url": SW, "kind": "VENDOR_CLAIM", "as_of": "2026-11-04"},
        {"claim": "OpenRouter lists $10 per million output tokens.",
         "evidence": "$10 per million output tokens", "url": OR, "kind": "FACT"},
        {"claim": "It costs $12 per million output tokens.",
         "evidence": "Simon Willison notes $10 per million output tokens.", "url": SW},
        {"claim": "It beats every rival on coding.",
         "evidence": "It beats every rival on coding.", "url": SW},
        {"claim": "The model scored 67% on the test.",
         "evidence": "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%", "url": BLOG},
        {"claim": "A developer says it fixed the build.",
         "evidence": "it is the first open model that fixed the build", "url": HN, "kind": "FACT"},
    ],
    "citable_numbers": [{"value": "150M", "url": AA}, {"value": "99%", "url": AA},
                        {"value": "$10", "url": OR}],
    "voices": [{"quote": "it is the first open model that fixed the build", "who": "jdoe", "url": HN},
               {"quote": "it is the first open model that fixed the build", "who": "Jane Roe", "url": HN},
               {"quote": "a quote nobody said anywhere", "who": "x", "url": HN}],
    "uncertain_claims": ["earlier doubt"],
}
wynik, log = cicho(stages.sprawdz_karte, KARTA, DOWODY, klucze=["Kimi K3.1 Pro"])
tw = wynik["confirmed_claims"]
sprawdz("przechodza twierdzenia z cytatem z wlasnego adresu (5 z 9)", len(tw) == 6,
        [c["claim"][:40] for c in tw])
_po = {c["claim"][:25]: c for c in tw}


def _c(poczatek):
    return next((c for c in tw if c["claim"].startswith(poczatek)), {})


sprawdz("adres z koncowym ukosnikiem i znacznikami kampanii to ten sam adres",
        bool(_c("Artificial Analysis measur")) and bool(_c("It generated 150M tokens ")), list(_po))
sprawdz("wielokropek miedzy kawalkami tego samego fragmentu przechodzi",
        bool(_c("It generated 150M tokens ")))
sprawdz("cytat z innego adresu idzie do niepewnych",
        any("score of any model" not in d["claim"] and "67% on the test" in d["claim"]
            for d in wynik["sprawdzenie_karty"]["do_niepewnych"]), wynik["sprawdzenie_karty"]["do_niepewnych"])
sprawdz("cytat, ktorego nie ma w zrodle, idzie do niepewnych",
        any("beats every rival" in d["claim"] for d in wynik["sprawdzenie_karty"]["do_niepewnych"]))
sprawdz("liczba spoza cytatu ($12 przy cytacie o $10) idzie do niepewnych",
        any("$12" in d["claim"] and "12" in d["powod"] for d in wynik["sprawdzenie_karty"]["do_niepewnych"]))
sprawdz("niepewne zachowuja to, co juz bylo, i dostaja powod",
        wynik["uncertain_claims"][0] == "earlier doubt"
        and any("not confirmed" in u for u in wynik["uncertain_claims"][1:]))
sprawdz("klasy: ewaluator INDEPENDENT, blog aktora PRIMARY, odsprzedawca LISTING, HN VOICE",
        (_c("Artificial Analysis measur")["class"], _c("The makers report 65.7%,")["class"],
         _c("OpenRouter lists $10 per ")["class"], _c("A developer says it fixed")["class"])
        == ("INDEPENDENT", "PRIMARY", "LISTING", "VOICE"))
sprawdz("pomiar niezalezny zostaje na stronie ewaluatora",
        _c("Artificial Analysis measur")["kind"] == "INDEPENDENT_MEASURE")
sprawdz("KONTRDOWOD: „pomiar niezalezny” z bloga producenta spada do FACT",
        _c("The makers report 65.7%,")["kind"] == "FACT")
sprawdz("odsprzedawca zawsze LISTING, glos zawsze VOICE",
        _c("OpenRouter lists $10 per ")["kind"] == "LISTING"
        and _c("A developer says it fixed")["kind"] == "VOICE")
sprawdz("as_of: data zrodla z pobrania", _c("Artificial Analysis measur")["as_of"] == "2026-10-23")
sprawdz("as_of: data spoza znanych kodowi nie wchodzi (zrodlo bez daty -> puste)",
        _c("The makers report 65.7%,")["as_of"] == "")
sprawdz("as_of: data stojaca w cytacie jest znana kodowi",
        _c("Weights are not out yet; ")["as_of"] == "2026-11-04")
sprawdz("twierdzenie „not yet” oznaczone jako czasowe",
        _c("Weights are not out yet; ")["time_sensitive"] is True
        and _c("Artificial Analysis measur")["time_sensitive"] is False)
sprawdz("pytanie i slot przechodza, zle wartosci znikaja",
        _c("Artificial Analysis measur")["q"] == "Q2"
        and _c("Artificial Analysis measur")["slot"] == "PRIMARY_NUMBER"
        and _c("The makers report 65.7%,")["q"] == "" and _c("The makers report 65.7%,")["slot"] == "")
sprawdz("liczby do cytowania tylko doslownie we fragmentach swojego adresu",
        [n["value"] for n in wynik["citable_numbers"]] == ["150M", "$10"]
        and wynik["sprawdzenie_karty"]["liczby_odrzucone"] == ["99%"], wynik["citable_numbers"])
gl = wynik["voices"]
sprawdz("glos z cytatem w zrodle zostaje, zmyslony cytat odpada",
        len(gl) == 2 and wynik["sprawdzenie_karty"]["glosow_odrzuconych"] == 1, gl)
sprawdz("nazwisko obecne przy zrodle zostaje, cudze — ogolne przypisanie",
        gl[0]["who"] == "jdoe" and gl[1]["who"] == "" and gl[1].get("who_ogolnie") is True, gl)
sprawdz("kazde zrodlo dostaje klase kodu obok klasy z klasyfikacji",
        DOWODY[0]["source_class"] == "INDEPENDENT" and DOWODY[0]["class"] == "PRIMARY")
sprawdz("log mowi, ile twierdzen przeszlo", "[karta] 6 z 9" in log, log[:200])
_bez, _log2 = cicho(stages.sprawdz_karte, KARTA, DOWODY)
sprawdz("KONTRDOWOD: bez kluczy blog aktora nie jest PRIMARY, a log to mowi",
        all(c["class"] != "PRIMARY" for c in _bez["confirmed_claims"]) and "bez kluczy" in _log2)
_z_karty, _ = cicho(stages.sprawdz_karte, dict(KARTA, klucze=["Kimi K3.1 Pro"]), DOWODY)
sprawdz("klucze moga przyjsc w samej karcie",
        any(c["class"] == "PRIMARY" for c in _z_karty["confirmed_claims"]))
sprawdz("zly wpis nie wywraca sprawdzenia",
        cicho(stages.sprawdz_karte, {"confirmed_claims": [None, {"claim": ""}, "x"]}, [None, {}])[0]
        ["confirmed_claims"] == [])

print()
print("=== 4. SYNTEZA W TRYBIE SLEDCZYM ===")
TW20 = [{"claim": "c%d" % i, "evidence": "e", "url": "u", "slot": ""} for i in range(20)]
TW20[17]["slot"] = "PRICE_ACCESS"
TW20[19]["slot"] = "voice"
_odp = json.dumps({"confirmed_claims": TW20, "citable_numbers": [],
                   "voices": [{"quote": "q"}] * 6})
with podmiana(llm, call=lambda *a, **k: _odp):
    sl, _ = cicho(stages.synthesis, None, 1, "Q", [], tryb="sledztwo")
    ar, _ = cicho(stages.synthesis, None, 1, "Q", [])
sprawdz("sledztwo: 16 twierdzen", len(sl["confirmed_claims"]) == 16)
sprawdz("sloty z konca listy nie wypadaja przy przycinaniu",
        {"c17", "c19"} <= {c["claim"] for c in sl["confirmed_claims"]})
sprawdz("kolejnosc modelu zostaje", [c["claim"] for c in sl["confirmed_claims"]][:3] == ["c0", "c1", "c2"]
        and sl["confirmed_claims"][-1]["claim"] == "c19")
sprawdz("glosy przyciete do %d" % config.CARD_MAX_GLOSOW, len(sl["voices"]) == config.CARD_MAX_GLOSOW)
sprawdz("KONTRDOWOD: artykul dalej 8 pierwszych, bez glosow i bez znacznika trybu",
        [c["claim"] for c in ar["confirmed_claims"]] == ["c%d" % i for i in range(8)]
        and "tryb" not in ar and len(ar.get("voices") or []) == 6)
sprawdz("przycinanie bez nadmiaru nic nie zmienia",
        stages.przytnij_ze_slotami(TW20[:5], 16) == TW20[:5])

print()
print("=== 5. WERYFIKACJA BEZ JSON-u NIE JEST CZYSTA ===")
PROZA = "I'll search for the key claims first and then check each one against the sources. " * 4
JSON_OK = json.dumps({"claims": [{"claim": "x", "status": "confirmed"}], "safe_to_post": True,
                      "verdict": "fine"})
WOLANIA = []


def kolejka(odpowiedzi):
    lista = list(odpowiedzi)

    def _call(purpose, system, user, **k):
        WOLANIA.append({"purpose": purpose, "system": system, "user": user, **k})
        x = lista.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    return _call


WOLANIA.clear()
with podmiana(llm, call=kolejka([PROZA, PROZA, PROZA])):
    out, log = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("trzy wywolania: proba, ratunek ksztaltu, ponowka", len(WOLANIA) == 3, len(WOLANIA))
sprawdz("ratunek bez szukania, ponowka z szukaniem i nizszym limitem",
        WOLANIA[1]["system"] == llm.RATUNEK_SYSTEM and not WOLANIA[1].get("web_search")
        and WOLANIA[2].get("web_search") is True
        and WOLANIA[2].get("max_szukan") == config.max_szukan("factcheck") - 1, WOLANIA[1:])
sprawdz("ponowka mowi „JSON first”", "Return the JSON object FIRST" in WOLANIA[2]["user"])
sprawdz("dwa razy bez JSON-u: nie_sprawdzone i NIE safe_to_post",
        out.get("nie_sprawdzone") is True and out.get("safe_to_post") is False
        and out.get("bez_json") is True, out)
sprawdz("log mowi NIE SPRAWDZONE", "NIE SPRAWDZONE" in log, log)

WOLANIA.clear()
with podmiana(llm, call=kolejka([PROZA, PROZA, JSON_OK])):
    out, _ = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("ponowka z JSON-em: zwykly werdykt", out.get("safe_to_post") is True
        and out.get("nie_sprawdzone") is False and out.get("ponowka_json") is True, out)

WOLANIA.clear()
with podmiana(llm, call=kolejka([PROZA, JSON_OK])):
    out, _ = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("ratunek z lista twierdzen wystarcza — bez ponowki", len(WOLANIA) == 2
        and out.get("odzyskany") is True and out.get("safe_to_post") is True, (len(WOLANIA), out))

WOLANIA.clear()
with podmiana(llm, call=kolejka([PROZA, '{"claims": [], "safe_to_post": true, "verdict": "ok"}', PROZA])):
    out, _ = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("KONTRDOWOD: ratunek z PUSTA lista twierdzen nie uchodzi za czysto",
        len(WOLANIA) == 3 and out.get("safe_to_post") is False, (len(WOLANIA), out))

WOLANIA.clear()
with podmiana(llm, call=kolejka([JSON_OK])):
    out, _ = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("KONTRDOWOD: JSON za pierwszym razem — jedno wywolanie", len(WOLANIA) == 1
        and out.get("safe_to_post") is True)

with podmiana(llm, call=kolejka([RuntimeError("dostawca padl")])):
    out, _ = cicho(stages.zweryfikuj, None, 1, "text", "ctx")
sprawdz("awaria dostawcy zostaje przy starej, jawnej decyzji (pierwsza siatka)",
        out.get("nie_sprawdzone") is True and out.get("safe_to_post") is True)
try:
    with podmiana(llm, call=kolejka([PROZA, PROZA, llm.BudgetExceeded("limit")])):
        cicho(stages.zweryfikuj, None, 1, "text", "ctx")
    _wylecial = False
except llm.BudgetExceeded:
    _wylecial = True
sprawdz("pusty budzet na ponowce leci na wylot", _wylecial)

print()
print("=== 6. WIERNOSC NOTKI WOBEC TWIERDZEN KATA ===")
FAKTY = [{"claim": "Artificial Analysis measured 67%, the highest of any model.",
          "evidence": "the highest score of any model on Terminal-Bench 4.0. K3.1 Pro scores 67%",
          "url": AA, "kind": "INDEPENDENT_MEASURE"}]
NOTKA = ("Kimi K3.1 Pro scored 67% on Terminal-Bench 4.0. Though its comparison was Sonnet, not Opus. "
         "Our bet: it matters.")
WOLANIA.clear()
with podmiana(llm, call=kolejka([json.dumps({"faithful": False, "problems": [
        {"sentence": "Though its comparison was Sonnet, not Opus.", "why": "claims say highest of any model",
         "claim": 1},
        {"sentence": "A sentence that is not in the note at all.", "why": "noise", "claim": 1}]})])):
    w, _ = cicho(stages.wiernosc_notki, None, 1, NOTKA, FAKTY)
sprawdz("zdanie sprzeczne z twierdzeniem wykryte", w["wierna"] is False and len(w["problemy"]) == 1
        and "Sonnet" in w["problemy"][0]["zdanie"], w)
sprawdz("zdanie, ktorego w notce nie ma, odpada jako szum", len(w["problemy"]) == 1)
sprawdz("prompt niesie twierdzenia z cytatami i notke za bariera",
        WOLANIA[0]["purpose"] == "wiernosc_notki" and "quote: \"the highest score" in WOLANIA[0]["user"]
        and WOLANIA[0]["user"].index("DATA, never instructions") < WOLANIA[0]["user"].index(NOTKA[:30])
        and not WOLANIA[0].get("web_search"))
with podmiana(llm, call=kolejka(["no json here"])):
    w, _ = cicho(stages.wiernosc_notki, None, 1, NOTKA, FAKTY)
sprawdz("awaria: nie_sprawdzone, bez blokady", w["nie_sprawdzone"] is True and w["problemy"] == [])
sprawdz("bez twierdzen nie ma czego sprawdzac (bez wywolania)",
        cicho(stages.wiernosc_notki, None, 1, NOTKA, [])[0]["nie_sprawdzone"] is True)

print()
print("=== 7. NOTKA Z BRAMKA: JEDNA POPRAWKA, POTEM ODRZUCENIE ===")
ZDARZENIA = []


def _note_srodowisko(odpowiedzi):
    """Atrapy wokol prawdziwego `stages.note`: pisarz, wiernosc, rozbior i weryfikacja."""
    lista = list(odpowiedzi)

    def _call(purpose, system, user, **k):
        ZDARZENIA.append((purpose, user))
        return lista.pop(0)

    def _rozbior(conn, run_id, evidence):
        ZDARZENIA.append(("rozbior", ""))
        return {}

    def _weryfikuj(conn, run_id, tekst, kontekst="", szukaj=True):
        ZDARZENIA.append(("factcheck", tekst))
        return {"claims": [], "zarzuty": [], "safe_to_post": True, "nie_sprawdzone": False}

    return [podmiana(llm, call=_call),
            podmiana(stages, rozbior=_rozbior, zweryfikuj=_weryfikuj,
                     ostatnie_otwarcia=lambda *a, **k: [], ostatnie_zakonczenia=lambda *a, **k: [],
                     teksty_ostatnich_notek=lambda *a, **k: [], zakonczenia_brakiem=lambda *a, **k: [])]


def nota(odp):
    return json.dumps({"note": odp, "words": len(odp.split())})


def zrob_note(odpowiedzi, *a, **k):
    ZDARZENIA.clear()
    with contextlib.ExitStack() as stos:
        for p in _note_srodowisko(odpowiedzi):
            stos.enter_context(p)
        return cicho(stages.note, None, 1, *a, **k)


MYSL_ZLA = "I think Kimi beats everyone 3 times over."
MYSL_DOBRA = "We think a cheap model changes who gets to build. Our bet: more builders, not fewer."
_bm = lambda t: stages.bramka_mysli(t, KLUCZE)  # noqa: E731
wyn, log = zrob_note([nota(MYSL_ZLA), nota(MYSL_DOBRA)], "MYSL", {"o_czym_sie_mowi": "x"}, bramka=_bm)
sprawdz("MYSL lamiaca reguly dostaje jedna poprawke i wychodzi poprawiona",
        [k["note"] for k in wyn["candidates"]] == [MYSL_DOBRA] and "bramka_odrzucila" not in wyn, wyn)
_pisania = [z[1] for z in ZDARZENIA if z[0] == "note"]
sprawdz("poprawka dostaje szkic i liste problemow",
        len(_pisania) == 2 and "Your draft failed our checks" in _pisania[1]
        and MYSL_ZLA in _pisania[1] and "first person" in _pisania[1], [z[0] for z in ZDARZENIA])
sprawdz("zapis trzyma pierwsza wersje i jej problemy",
        wyn["candidates"][0]["bramka_pierwsza_wersja"]["note"] == MYSL_ZLA)
wyn, log = zrob_note([nota(MYSL_ZLA), nota("I still think so, 3 times.")], "MYSL",
                     {"o_czym_sie_mowi": "x"}, bramka=_bm)
sprawdz("po poprawce nadal zle: zero kandydatow i powody w wyniku",
        wyn["candidates"] == [] and wyn.get("bramka_odrzucila")
        and wyn["odrzucone_bramka"][0]["note"].startswith("I still"), wyn)
sprawdz("odrzucona notka nie idzie do sprawdzenia w sieci",
        not any(z[0] == "factcheck" for z in ZDARZENIA))
wyn, _ = zrob_note([nota(MYSL_ZLA)], "MYSL", {"o_czym_sie_mowi": "x"})
sprawdz("KONTRDOWOD: bez bramki notka idzie jak dotad (jedno pisanie, bez poprawki)",
        [k["note"] for k in wyn["candidates"]] == [MYSL_ZLA]
        and len([z for z in ZDARZENIA if z[0] == "note"]) == 1)

LINIA2 = "Kimi K3.1 Pro scored 67% on Terminal-Bench 4.0, the highest of any model."
SERIA_OK = LINIA2 + " That is an independent number, not the makers' own."
SERIA_PRZESUNIETA = "Here is the news. " + LINIA2


def bramka_serii(t):
    return [] if stages.zachowuje_pierwsze_zdanie(t, LINIA2) else ["must open with the line"]


WIERNA = json.dumps({"faithful": True, "problems": []})
wyn, _ = zrob_note([nota(SERIA_PRZESUNIETA), nota(SERIA_OK), WIERNA], "CIEKAWOSTKA",
                   {"fact": {"fact": "f"}, "investigation": {"supporting_claims": FAKTY}},
                   etap="notka_przeslania_fakt", bramka=bramka_serii, twierdzenia_kata=FAKTY,
                   bez_rozbioru=True, pierwsze_zdanie=LINIA2)
kolej = [z[0] for z in ZDARZENIA]
sprawdz("notka serii: bez rozbioru", "rozbior" not in kolej, kolej)
sprawdz("pisze cel kata, poprawka tym samym celem",
        kolej[:2] == ["notka_przeslania_fakt", "notka_przeslania_fakt"], kolej)
sprawdz("wiernosc PRZED sprawdzeniem w sieci, tylko dla tekstu po regulach kodu",
        kolej == ["notka_przeslania_fakt", "notka_przeslania_fakt", "wiernosc_notki", "factcheck"], kolej)
sprawdz("zdanie po bramce w prompcie, jako ostatnie polecenie",
        ZDARZENIA[0][1].rstrip().endswith("Everything after it is yours to write.")
        and LINIA2 in ZDARZENIA[0][1])
sprawdz("wychodzi wersja z zachowanym pierwszym zdaniem",
        [k["note"] for k in wyn["candidates"]] == [SERIA_OK] and wyn["candidates"][0]["wiernosc"]["wierna"])
NIEWIERNA = json.dumps({"faithful": False, "problems": [
    {"sentence": "That is an independent number, not the makers' own.", "why": "x", "claim": 1}]})
wyn, _ = zrob_note([nota(SERIA_OK), NIEWIERNA, nota(SERIA_OK), NIEWIERNA], "CIEKAWOSTKA",
                   {"fact": {"fact": "f"}}, etap="notka_przeslania", bramka=bramka_serii,
                   twierdzenia_kata=FAKTY, bez_rozbioru=True)
sprawdz("niewierna dwa razy: odrzucona z powodem wiernosci",
        wyn["candidates"] == [] and "does not match the claims" in " ".join(wyn["bramka_odrzucila"]), wyn)
wyn, _ = zrob_note([nota(SERIA_OK), WIERNA], "CIEKAWOSTKA", {"fact": {"fact": "f"}},
                   bramka=bramka_serii, twierdzenia_kata=FAKTY)
sprawdz("KONTRDOWOD: bez `bez_rozbioru` rozbior idzie jak dotad",
        [z[0] for z in ZDARZENIA][0] == "rozbior")

print()
print("=== 8. NAPRAWA NIE PRZEPISUJE LICZBY Z KARTY ===")
AUDYT = {"zarzuty": [{"claim": "the highest of any model", "status": "refuted",
                      "what_the_source_says": "second place"}]}
TEKST = "Kimi K3.1 Pro scored 67% on the test, the highest of any model."
NAPRAWIONY = "Kimi K3.1 Pro scored 70% on the test, in second place."
POTWIERDZONE = json.dumps({"claims": [{"claim": "x", "status": "confirmed"}], "safe_to_post": True})
with podmiana(llm, call=kolejka([json.dumps({"text": NAPRAWIONY})])):
    r, log = cicho(stages.napraw_obalone, None, 901, TEKST, AUDYT, kontekst="k", min_slow=1,
                   max_slow=99, etap="naprawa", zapora=lambda t: "", chronione=frozenset({"67"}))
sprawdz("naprawa gubiaca liczbe z karty jest odrzucona", r is None and "liczbe z karty" in log, log)
with podmiana(llm, call=kolejka([json.dumps({"text": NAPRAWIONY}), POTWIERDZONE])):
    r, _ = cicho(stages.napraw_obalone, None, 902, TEKST, AUDYT, kontekst="k", min_slow=1,
                 max_slow=99, etap="naprawa", zapora=lambda t: "")
sprawdz("KONTRDOWOD: bez listy chronionej ta sama naprawa przechodzi", bool(r) and r["tekst"] == NAPRAWIONY)
_ZAPIS = {}


def _naprawa_zapisz(*a, **k):
    _ZAPIS.update(k)
    return None


ZDARZENIA.clear()
with contextlib.ExitStack() as stos:
    for p in _note_srodowisko([nota(SERIA_OK), WIERNA]):
        stos.enter_context(p)
    stos.enter_context(podmiana(stages, napraw_obalone=_naprawa_zapisz))
    cicho(stages.note, None, 1, "CIEKAWOSTKA", {"fact": {"fact": "f"}}, bramka=bramka_serii,
          twierdzenia_kata=FAKTY, bez_rozbioru=True)
sprawdz("notka serii przekazuje naprawie liczby z karty kata",
        {"67", "4.0"} <= set(_ZAPIS.get("chronione") or ()), _ZAPIS.get("chronione"))

print()
print("=== 9. NOTKI DNIA: MYSL I NOTKA SERII ===")
WOLANE_NOTE = []
PROBY = []


def srodowisko_dnia(odpowiedzi_note, przeslanie=None, material=None, sprawdz_notke=None):
    """Prawdziwe `notki_dnia` z atrapami wszystkiego, co placi albo czyta dane."""
    lista = list(odpowiedzi_note)
    WOLANE_NOTE.clear()
    PROBY.clear()

    def _note(conn, run_id, typ, material, link=None, note_form="PROSTA", etap="note", **k):
        WOLANE_NOTE.append({"typ": typ, "material": material, "etap": etap, **k})
        odp = lista.pop(0) if lista else {"candidates": [{"note": "A bank note.", "safe_to_post": True}]}
        return dict({"type": typ, "forma": note_form}, **odp)

    def _wybierz(zapas, *a, **k):
        return zapas.pop(0) if zapas else None

    return [
        podmiana(stages, note=_note, artykul_do_promocji=lambda: None,
                 sparuj_bank=lambda *a, **k: {}, posortuj_bank=lambda *a, **k: None,
                 znajdz_ciekawostki=lambda *a, **k: [], pamiec_wystawionych=lambda: [],
                 teksty_ostatnich_notek=lambda *a, **k: [], dzis_notka_spoza_branzy=lambda: False,
                 zaczyn_z_kanalow=lambda ile=26: "- [2026-10-24] Feed — Kimi K3.1 Pro tops a coding test\n"
                                                 "- [2026-10-24] Feed — Schools ban phones and chatbots",
                 wybierz_material=_wybierz, _tematy_zrodel=lambda: [], wez_kandydatow=lambda *a, **k: [],
                 zwroc_kandydatow=lambda *a, **k: 0, wniosek=lambda *a, **k: {},
                 ramie=lambda *a, **k: ""),
        podmiana(stages.seria, propozycja=lambda *a, **k: None),
        podmiana(glebia, karta_glebi=lambda *a, **k: None),
        podmiana(sledztwo, wez_przeslanie=lambda: przeslanie,
                 material_notki=lambda p: (dict(fact="f", url="u"), material),
                 klucze_serii=lambda: ["Kimi K3.1 Pro"],
                 tematy_obok=lambda ile=5: ["Kimi K3.1 Pro price war", "A school district bans AI tutors"],
                 oznacz_probe=lambda pid, powod: PROBY.append((pid, powod)),
                 sprawdz_notke=sprawdz_notke or (lambda t, f, k=None: []),
                 sprawdz_linie=lambda l, f, k=None: ["opens with a date"],
                 KATY={"REVEAL": {"typ_notki": "CIEKAWOSTKA", "opis": "x", "analiza": False},
                       "VERDICT": {"typ_notki": "DYSKUSJA", "opis": "x", "analiza": True}}),
    ]


def dzien(odpowiedzi_note, ile=1, od=3, fakty_banku=None, **k):
    with contextlib.ExitStack() as stos:
        for p in srodowisko_dnia(odpowiedzi_note, **k):
            stos.enter_context(p)
        return cicho(stages.notki_dnia, None, 1, ciekawostki=list(fakty_banku or []), ile=ile, od=od)


FAKT_BANKU = {"fact": "A bank fact about schools.", "url": "https://x.example/a", "domain": "x"}
wyn, log = dzien([], fakty_banku=[FAKT_BANKU])
m = WOLANE_NOTE[0]
sprawdz("MYSL bez tematu serii", m["typ"] == "MYSL" and "temat_dnia" not in m["material"], m["material"])
sprawdz("MYSL dostaje historie obok serii, bez tych o serii",
        m["material"].get("inne_historie_tygodnia") == ["A school district bans AI tutors"], m["material"])
sprawdz("z zaczynu zdjete naglowki o serii",
        "Kimi" not in m["material"]["o_czym_sie_mowi"] and "Schools ban" in m["material"]["o_czym_sie_mowi"])
sprawdz("MYSL wie, czego nie nazywac", m["material"].get("nie_wymieniaj") == ["Kimi K3.1 Pro"])
sprawdz("MYSL dostaje bramke kodu (cyfry, seria, „I”)",
        callable(m.get("bramka")) and len(m["bramka"]("I think Kimi is 3x better")) == 3
        and m["bramka"](MYSL_DOBRA) == [])
sprawdz("KONTRDOWOD: MYSL nie zabiera faktu z banku", len(WOLANE_NOTE) == 1 and wyn[0]["fakt"] is None)

wyn, log = dzien([{"candidates": [], "bramka_odrzucila": ["contains digits"]}], fakty_banku=[FAKT_BANKU])
sprawdz("MYSL odrzucona po poprawce -> w tym miejscu fakt z banku",
        [w["typ"] for w in WOLANE_NOTE] == ["MYSL", "CIEKAWOSTKA"]
        and WOLANE_NOTE[1]["material"]["fact"]["fact"] == FAKT_BANKU["fact"], WOLANE_NOTE)
sprawdz("dzien oddaje jedna notke (fakt), nie pusta MYSL",
        len(wyn) == 1 and wyn[0]["type"] == "CIEKAWOSTKA", [w.get("type") for w in wyn])
sprawdz("fakt z banku nie dostaje bramki MYSL", "bramka" not in WOLANE_NOTE[1])

PRZES = {"id": "20261025-7-reveal", "rodzaj": "REVEAL", "typ_notki": "CIEKAWOSTKA", "historia": "Kimi",
         "linia": LINIA2, "lead": False, "fakty": FAKTY, "klucze": ["Kimi K3.1 Pro"], "k": 2, "n": 4,
         "kierunek": "AMPLIFY", "os": "HYPE_CHECK", "perspektywa": {"wniosek": "w"}}
MATERIAL = {"fact": {"fact": "f"}, "perspective": {"wniosek": "w"},
            "investigation": {"first_line": LINIA2, "supporting_claims": FAKTY}}
wyn, log = dzien([], od=0, przeslanie=PRZES, material=MATERIAL)
s = WOLANE_NOTE[0]
sprawdz("kat faktow pisze `notka_przeslania_fakt` (D1: Opus)", s["etap"] == "notka_przeslania_fakt", s["etap"])
sprawdz("notka serii: bramka, twierdzenia kata, bez rozbioru, zdanie po bramce",
        callable(s.get("bramka")) and s.get("twierdzenia_kata") == FAKTY and s.get("bez_rozbioru") is True
        and s.get("pierwsze_zdanie") == LINIA2, s)
with podmiana(sledztwo, sprawdz_notke=lambda t, f, k=None: []):
    _ok, _zle = s["bramka"](SERIA_OK), s["bramka"](SERIA_PRZESUNIETA)
sprawdz("bramka serii pilnuje pierwszego zdania", _ok == [] and _zle != [], (_ok, _zle))
sprawdz("notka niesie identyfikator i kat do dziennika",
        wyn[0]["przeslanie_id"] == PRZES["id"] and wyn[0]["kat_serii"]["wariant"] == "gated"
        and wyn[0]["kat_serii"]["k"] == 2 and wyn[0]["kat_serii"]["kierunek"] == "AMPLIFY", wyn[0].get("kat_serii"))
for opis, zmiana, etap in (("kat prowadzacy", {"lead": True}, "notka_przeslania"),
                           ("analiza (KATY)", {"rodzaj": "VERDICT"}, "notka_przeslania"),
                           ("stary wpis MOTYW", {"rodzaj": "MOTYW", "typ_notki": "DYSKUSJA"}, "notka_przeslania"),
                           ("stary wpis KURIOZUM", {"rodzaj": "KURIOZUM"}, "notka_przeslania_fakt")):
    dzien([], od=0, przeslanie=dict(PRZES, **zmiana), material=MATERIAL)
    sprawdz("%-22s -> %s" % (opis, etap), WOLANE_NOTE[0]["etap"] == etap, WOLANE_NOTE[0]["etap"])

wyn, log = dzien([], od=0, przeslanie=dict(PRZES, linia="", rodzaj="KURIOZUM"),
                 material={"fact": {"fact": "f"}, "investigation": {"first_line": "", "supporting_claims": FAKTY}})
sprawdz("bez zdania po bramce: wariant W, pierwsze zdanie sprawdzone do logu",
        wyn[0]["kat_serii"]["wariant"] == "W"
        and wyn[0]["kat_serii"]["pierwsze_zdanie_bramka"] == ["opens with a date"]
        and WOLANE_NOTE[0]["pierwsze_zdanie"] == "", wyn[0].get("kat_serii"))

_sn = lambda t, f, k=None: ["more than three numbers"] if "99" in t else []  # noqa: E731
dzien([], od=0, przeslanie=PRZES, material=MATERIAL, sprawdz_notke=_sn)
with podmiana(sledztwo, sprawdz_notke=_sn):
    _wynik_bramki = WOLANE_NOTE[0]["bramka"](SERIA_OK + " 99 99 99")
sprawdz("bramka serii wola `sledztwo.sprawdz_notke` na gotowym tekscie",
        _wynik_bramki == ["more than three numbers"], _wynik_bramki)
with podmiana(sledztwo, sprawdz_notke=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("zepsute"))):
    _wynik_bramki, _log = cicho(WOLANE_NOTE[0]["bramka"], SERIA_PRZESUNIETA)
sprawdz("KONTRDOWOD: zepsute `sprawdz_notke` nie wywraca bramki, log to mowi, zdanie dalej pilnowane",
        len(_wynik_bramki) == 1 and "sprawdz_notke niedostepne" in _log, (_wynik_bramki, _log))

wyn, log = dzien([{"candidates": [], "bramka_odrzucila": ["numbers outside cited claims"]}], od=0,
                 przeslanie=PRZES, material=MATERIAL, fakty_banku=[FAKT_BANKU])
sprawdz("notka serii lamiaca reguly: proba kata z powodem",
        PROBY == [(PRZES["id"], "reguly: numbers outside cited claims")], PROBY)
sprawdz("...bez drugiego pisarza na tych samych twierdzeniach, a w tym miejscu zwykla notka",
        [w["etap"] for w in WOLANE_NOTE] == ["notka_przeslania_fakt", "note"]
        and WOLANE_NOTE[1]["typ"] == "CIEKAWOSTKA" and "bramka" not in WOLANE_NOTE[1]
        and WOLANE_NOTE[1]["material"]["fact"]["fact"] == FAKT_BANKU["fact"], WOLANE_NOTE)
sprawdz("dzien ma jedna notke, bez identyfikatora przeslania",
        len(wyn) == 1 and not wyn[0].get("przeslanie_id"), wyn)

wyn, log = dzien([{"candidates": []}, {"candidates": []}], od=0, przeslanie=PRZES, material=MATERIAL,
                 fakty_banku=[FAKT_BANKU])
sprawdz("odmowa Opusa: zwykly pisarz z TYMI SAMYMI bramkami",
        [w["etap"] for w in WOLANE_NOTE][:2] == ["notka_przeslania_fakt", "note"]
        and WOLANE_NOTE[1].get("bez_rozbioru") is True and WOLANE_NOTE[1].get("pierwsze_zdanie") == LINIA2)
sprawdz("obaj bez tekstu: proba kata i zwykla notka w tym miejscu",
        PROBY == [(PRZES["id"], "zaden pisarz nie oddal tekstu")] and len(WOLANE_NOTE) == 3
        and WOLANE_NOTE[2]["typ"] == "CIEKAWOSTKA", (PROBY, [w["etap"] for w in WOLANE_NOTE]))
sprawdz("log mowi, ze Opus nie napisal", "Opus nie napisal notki" in log)

with podmiana(sledztwo, klucze_serii=lambda: (_ for _ in ()).throw(RuntimeError("zepsute"))):
    _mat, _log = cicho(stages.material_mysli)
sprawdz("awaria modulu sledztwa nie zabiera MYSL", _mat[1] == [] and "o_czym_sie_mowi" in _mat[0]
        and "klucze_serii niedostepne" in _log)

print()
print("=== 10. WERYFIKATOR DOSTAJE WSZYSTKIE TWIERDZENIA KATA ===")
OSIEM = [{"claim": "claim %d" % i, "evidence": "evidence %d" % i, "url": "https://x.example/%d" % i}
         for i in range(8)]
OSIEM[7]["claim"] = "The weights are not yet released."
rek = stages._rekord_do_weryfikacji("CIEKAWOSTKA", {"fact": {"fact": "f"},
                                                    "investigation": {"supporting_claims": OSIEM}})
sprawdz("wszystkie osiem twierdzen w kontekscie (bylo szesc)", "claim 6" in rek and "not yet released" in rek)
sprawdz("twierdzenie czasowe oznaczone do sprawdzenia na dzis",
        rek.count("TIME-SENSITIVE") == 1 and "not yet released.\" " not in rek)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
