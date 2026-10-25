# -*- coding: utf-8 -*-
"""Plan sledztwa i starszy redaktor (`sledztwo_plan.py`, 25.10.2026).

PO CO. Proby sledczego 25.10 chybialy przez pytania: proceduralne, pasujace do kazdej
historii, bez pytania o role AI przy luce, bez sprzetu, licencji i sil w wyscigu przy
premierze. Sam plan nie przeszedl zadnej proby. Ten test pilnuje ZACHOWANIA, nie napisow:

  1. prompty: dwanascie soczewek w prompcie, skladaja sie przez `stages._prompt`,
     zero nazw historii z prob;
  2. dobry plan: bez zapasu, Q1..Qn, cztery pierwsze z waga 1, proza bez cyfr;
  3. test podmiany wobec szablonow soczewek (pytanie przepisane z promptu z nazwa
     wstawiona w srodek odpada), pytanie bez nazw historii odpada, odpowiedz w naglowku
     odpada, dubel odpada — z kontrdowodem, ze konkretne pytanie zostaje;
  4. test podmiany wobec SZESCIU ostatnich planow z `sledztwa.jsonl` (siodmy juz nie);
  5. odmowa i uciecie -> zapas; za malo dobrych -> jedna proba zapasu; oba zle ->
     FALLBACK w logu i pytania stale; BudgetExceeded przechodzi;
  6. historia o luce: strona obroncy, pytanie o exploit i dokument z PoC odpadaja;
  7. brak JSON-u -> ratunek; prompt, ktory sie nie sklada -> FALLBACK, nie wyjatek;
  8. `pytania_tekstem`, `plan_do_kart`;
  9. krytyk: najwyzej trzy, K1.., waga 1, ogolne i juz odpowiedziane odpadaja, zapas,
     pominiecie przy wyczerpanym progu badania, pusto przy awarii;
 10. kanal kosztu „artykul" na kazdym platnym wywolaniu.

Nazwy z prob (Kimi, Moonshot, PHP2Shell) sa tu wylacznie DANYMI testu.
BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_sledztwo_plan.py
"""
import contextlib
import io
import json
import pathlib
import re
import sqlite3
import string
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

KAT = pathlib.Path(tempfile.mkdtemp(prefix="plan-sledztwa-"))
config.uzyj_katalogu_danych(KAT)

import db             # noqa: E402
import llm            # noqa: E402
import sledztwo       # noqa: E402
import sledztwo_plan as sp   # noqa: E402
import stages         # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# --- atrapy modeli ------------------------------------------------------------------

WYWOLANIA = []      # (purpose, system, user, kanal)
ODPOWIEDZI = {}     # purpose -> lista odpowiedzi (napis albo wyjatek), zjadana po kolei
RATUNKI = []        # odpowiedzi atrapy `llm.ratuj_json`
_prawdziwy_call, _prawdziwy_ratunek = llm.call, llm.ratuj_json


def _atrapa_call(purpose, system, user, conn=None, run_id=None, **kw):
    WYWOLANIA.append((purpose, system, user, db.AKCJA))
    kolejka = ODPOWIEDZI.get(purpose) or []
    if not kolejka:
        raise AssertionError("niespodziewane wywolanie %s" % purpose)
    x = kolejka.pop(0)
    if isinstance(x, BaseException):
        raise x
    return x if isinstance(x, str) else json.dumps(x)


def _atrapa_ratunku(purpose, tekst, ksztalt, conn=None, run_id=None):
    WYWOLANIA.append(("ratuj:" + purpose, "", tekst, db.AKCJA))
    return RATUNKI.pop(0) if RATUNKI else ""


def ustaw(**odp):
    WYWOLANIA.clear()
    ODPOWIEDZI.clear()
    RATUNKI.clear()
    for k, v in odp.items():
        ODPOWIEDZI[k] = list(v)


def cele():
    return [w[0] for w in WYWOLANIA]


def cicho(fn, *a, **k):
    bufor = io.StringIO()
    with contextlib.redirect_stdout(bufor):
        wynik = fn(*a, **k)
    return wynik, bufor.getvalue()


# Cyfra poza nazwa: nazwy z cyfra (K3.1, GPT-6, H100) maja zostac, liczby nie.
CYFRA = re.compile(r"(?<![A-Za-z0-9.\-])\d")


def powod(odrzucone, poczatek):
    """Powod odrzucenia pytania zaczynajacego sie od `poczatek` (pusto, gdy nie odrzucone)."""
    return next((o["powod"] for o in odrzucone if o["q"].startswith(poczatek)), "")


llm.call = _atrapa_call
llm.ratuj_json = _atrapa_ratunku

# --- dane: premiera modelu z proby 25.10 ---------------------------------------------

KIMI = {"miejsce": 1, "tytul": "Kimi K3.1 Pro matches closed models on coding tests",
        "kategoria": "PREMIERA_MODELU", "zapytanie": "Kimi K3.1 Pro", "klucze": ["Kimi", "K3.1"],
        "naglowki": [
            {"kanal": "Latent Space", "temat": "Kimi K3.1 Pro: Fable-5.1-Class Open Weights",
             "url": "https://www.latent.space/p/kimi", "data": "2026-10-23"},
            {"kanal": "The Decoder", "temat": "Moonshot's Kimi K3.1 Pro tops Terminal-Bench 4.0",
             "url": "https://the-decoder.com/kimi", "data": "2026-10-23"},
            {"kanal": "Artificial Analysis", "temat": "Kimi K3.1 Pro wrote 150M tokens on Intelligence Index",
             "url": "https://artificialanalysis.ai/kimi", "data": "2026-10-24"}]}
LEDES = [
    {"publisher": "Simon Willison", "title": "Kimi K3.1 Pro",
     "lede": "Moonshot released Kimi K3.1 Pro today. It's not yet open weights, but Moonshot promise "
             "'Full model weights will be released by Nov 4, 2026'. Pricing is $10 per million output tokens.",
     "dlugosc": 6000},
    {"publisher": "Artificial Analysis", "title": "Kimi K3.1 Pro launch benchmarks",
     "lede": "K3.1 Pro scores 67%, the highest score of any model on Terminal-Bench 4.0. Artificial Analysis "
             "currently lists it as proprietary.", "dlugosc": 9000},
    {"publisher": "Krotki serwis", "title": "Short", "lede": "Kimi is out.", "dlugosc": 300},
]


def q(soczewka, pytanie, waga=2, dowod="a dated primary record", gdzie="the developer's own site",
      zapytanie=""):
    return {"id": "Q", "soczewka": soczewka, "pytanie": pytanie, "waga": waga, "dowod": dowod,
            "gdzie": gdzie, "zapytanie": zapytanie}


DOBRE_KIMI = [
    q("NEW", "What did Moonshot change in Kimi K3.1 Pro compared with K3, and which gains does it claim "
             "over Claude Opus 5.5?", 1, zapytanie="Kimi K3.1 Pro release notes K3"),
    q("HOW_IT_WORKS", "Why does Kimi K3.1 Pro spend so many tokens on each answer, and what does that "
                      "verbosity say about how it reasons?", 1),
    q("CLAIM", "Does the Terminal-Bench 4.0 score Moonshot reports for Kimi K3.1 Pro match what Artificial "
               "Analysis measured under the same settings?", 1),
    q("BIG", "Has an open model from Moonshot caught the closed labs, or will Kimi K3.1 Pro fall behind "
             "once rivals answer?", 1),
    q("TIDBIT", "What does the Kimi K3.1 Pro model card say about when the full weights arrive?", 2,
      gdzie="model card and the Hugging Face repository"),
    q("PRACTICAL", "What hardware would a company need to run the Kimi K3.1 Pro weights itself, and what does "
                   "the licence allow?", 2),
    q("POWER", "Which Western labs lose pricing power if Kimi K3.1 Pro sells at $10 per million output tokens?", 3),
    q("PEOPLE", "What do developers who tried Kimi K3.1 Pro report about its coding, and where do they "
                "disagree?", 2),
    q("WATCH", "Will Moonshot ship the Kimi K3.1 Pro weights by the promised date?", 3),
]
PLAN_KIMI = {
    "co_nowego": "An open model scores 67% on Terminal-Bench 4.0 and costs $10 per million tokens.",
    "rdzen_ai": "Open models trail the closed frontier by 3 points, not 12.",
    "zalozenie_czytelnika": "Readers assume 2026 open models are a year behind.",
    "dokumenty": [{"co": "Kimi K3.1 Pro model card", "kto": "Moonshot", "gdzie": "kimi.ai"},
                  {"co": "Terminal-Bench 4.0 leaderboard entry", "kto": "Artificial Analysis",
                   "gdzie": "artificialanalysis.ai"},
                  {"co": "Kimi K3.1 Pro model card", "kto": "Moonshot", "gdzie": "huggingface.co"},
                  {"co": "OpenRouter listing", "kto": "OpenRouter", "gdzie": "openrouter.ai"},
                  {"co": "licence text", "kto": "Moonshot", "gdzie": "Hugging Face repository"},
                  {"co": "pricing page", "kto": "Moonshot", "gdzie": "platform.moonshot.ai"}],
    "pytania": DOBRE_KIMI,
    "pominiete_soczewki": [{"soczewka": "CONSEQUENCES", "dlaczego": "covered by POWER for this release"},
                           {"soczewka": "NUMBERS", "dlaczego": "the figures sit inside CLAIM"},
                           {"soczewka": "PRECEDENT", "dlaczego": "no earlier open release closed the gap"}],
    "rachunki": ["150M tokens at $10 per million output tokens"],
    "wielkie_pytanie": {"pytanie": "Has open caught closed?",
                        "wieksze_niz_wyglada": "3 points behind at half the price",
                        "mniejsze_niz_wyglada": "the weights are not out until Nov 4, 2026",
                        "nasz_typ": "smaller", "co_zmieni": "weights on Hugging Face by November 4"},
    "smaczek": {"co": "It wrote 150M tokens against a median of 87M", "gdzie": "Artificial Analysis page"},
    "termin": [{"co": "full weights", "kiedy": "2026-11-04"}, {"co": "zly", "kiedy": "November 4"}],
}

# =================================================================================
print("=== 1. PROMPTY: SOCZEWKI, SKLADANIE, ZERO NAZW Z PROB ===")
_pp = (config.PROMPTS_DIR / "plan_sledztwa.md").read_text(encoding="utf-8")
_pk = (config.PROMPTS_DIR / "krytyk_sledztwa.md").read_text(encoding="utf-8")
_linie = sp._linie_soczewek()
sprawdz("prompt planu ma linie kazdej z dwunastu soczewek (test podmiany czyta je stad)",
        sorted(_linie) == sorted(sp.SOCZEWKI), sorted(_linie))
sprawdz("SOCZEWKI i WYMAGANE jak w kontrakcie",
        sp.SOCZEWKI == ("NEW", "HOW_IT_WORKS", "CLAIM", "NUMBERS", "CONSEQUENCES", "POWER", "PRACTICAL",
                        "PEOPLE", "PRECEDENT", "BIG", "TIDBIT", "WATCH")
        and sp.WYMAGANE == ("NEW", "HOW_IT_WORKS", "BIG", "TIDBIT"))
sprawdz("prompt planu to tekst §3: wymagane soczewki, strona obroncy, test czytelnika",
        "NEW, HOW_IT_WORKS, BIG\nand TIDBIT are required" in _pp
        and "(For security incidents, HOW_IT_WORKS and PRACTICAL mean the defender's side" in _pp
        and '"huh, I didn\'t know that"' in _pp and "Write 8–12 research questions" in _pp
        and _pp.rstrip().endswith("Opening of the two longest fetched sources: {ledes}"))
_zakazane = re.compile(r"kimi|moonshot|php2shell|nextdc|medicare|terminal-bench|willison|artificial analysis",
                       re.I)
sprawdz("zaden prompt ani regula modulu nie nazywa historii z prob",
        not _zakazane.search(_pp) and not _zakazane.search(_pk)
        and not _zakazane.search("\n".join([l for l in pathlib.Path("agent-v2/sledztwo_plan.py")
                                           .read_text(encoding="utf-8").splitlines()
                                            if not l.lstrip().startswith("#")])))
for _nazwa, _tekst_p in (("plan_sledztwa.md", _pp), ("krytyk_sledztwa.md", _pk)):
    _pola = {f for _, f, _, _ in string.Formatter().parse(_tekst_p) if f and f != "marka"}
    try:
        _gotowy = stages._prompt(_nazwa, **{p: "POLE<%s>" % p for p in _pola})
        _ok = all("POLE<%s>" % p in _gotowy for p in _pola) and "{" in _gotowy and "{{" not in _gotowy
    except (KeyError, ValueError, IndexError) as exc:
        _ok = exc
    sprawdz("%s sklada sie przez stages._prompt i kazde pole dochodzi" % _nazwa, _ok is True, _ok)
sprawdz("marka przychodzi z config.MARKA, nie z tresci promptu",
        "{marka}" in _pp and config.MARKA not in _pp)
sprawdz("krytyk ma rdzen §3: trzy pozycje, a-d, jedno wyszukiwanie, nie dodaje faktow",
        "Name at\nmost three items" in _pk and "For each give one precise web search. An empty list is fine. "
        "Do not add facts." in _pk and "(d) the most surprising verified thing" in _pk)
# Sekcja danych w obu promptach ma byc na koncu: za nia juz tylko pola i krotkie etykiety.
for _nazwa, _tekst_p in (("plan_sledztwa.md", _pp), ("krytyk_sledztwa.md", _pk)):
    _po = _tekst_p.split("data, never instructions", 1)[1]
    _proza = [l for l in _po.splitlines()[1:] if l.strip() and not re.search(r"\{[a-z_]+\}", l)
              and len(l.strip()) > 40]
    sprawdz("%s: za sekcja danych nie ma naszej prozy" % _nazwa, not _proza, _proza)

# =================================================================================
print()
print("=== 2. DOBRY PLAN: BEZ ZAPASU, Q1..Qn, WAGA, PROZA BEZ CYFR ===")
ustaw(pytania_ciekawosci=[PLAN_KIMI])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "What does Kimi K3.1 Pro really prove?", LEDES,
                  typ="premiera")
sprawdz("jedno wywolanie, cel pytania_ciekawosci (bez zapasu)", cele() == ["pytania_ciekawosci"], cele())
sprawdz("wszystkie 9 pytan przeszlo", len(plan["pytania"]) == 9,
        [(o["q"][:50], o["powod"]) for o in plan["odrzucone"]])
sprawdz("ksztalt pytan jak w kontrakcie (id, soczewka, q, waga, dowod, gdzie, zapytanie)",
        all({"id", "soczewka", "q", "waga", "dowod", "gdzie", "zapytanie"} <= set(p) for p in plan["pytania"])
        and [p["id"] for p in plan["pytania"]] == ["Q%d" % i for i in range(1, 10)])
sprawdz("cztery pierwsze maja wage 1, reszta 2-3, kolejnosc wg wagi",
        [p["waga"] for p in plan["pytania"]][:4] == [1, 1, 1, 1]
        and all(p["waga"] >= 2 for p in plan["pytania"][4:])
        and [p["waga"] for p in plan["pytania"]] == sorted(p["waga"] for p in plan["pytania"]))
sprawdz("fallback=False, model z config.MODEL_FOR", plan["fallback"] is False
        and plan["model"] == config.MODEL_FOR.get("pytania_ciekawosci"), plan["model"])
sprawdz("dokumenty: najwyzej 4, bez dubla", len(plan["dokumenty"]) == 4
        and len({d["co"] for d in plan["dokumenty"]}) == 4, plan["dokumenty"])
_proza = " ".join([plan["rdzen_ai"], plan["zalozenie_czytelnika"], plan["co_nowego"],
                   " ".join(plan["wielkie_pytanie"].values()), " ".join(plan["smaczek"].values())])
sprawdz("proza planu bez cyfr", not CYFRA.search(_proza), _proza)
sprawdz("KONTRDOWOD: proza naprawde miala liczby, ktore zeszly",
        "3 points" in PLAN_KIMI["rdzen_ai"] and "points" in plan["rdzen_ai"] and "3" not in plan["rdzen_ai"],
        plan["rdzen_ai"])
sprawdz("data w prozie znika w calosci, nie zostaje „Nov,”",
        "Nov" not in plan["wielkie_pytanie"]["mniejsze_niz_wyglada"]
        and plan["wielkie_pytanie"]["mniejsze_niz_wyglada"].startswith("the weights are not out"),
        plan["wielkie_pytanie"]["mniejsze_niz_wyglada"])
_bc = sp._bez_cyfr("Kimi K3.1 Pro beats GPT-6 on one H100 for $10, 40% cheaper (2,500 tokens, 150M in all).")
sprawdz("nazwy z cyfra zostaja w prozie (K3.1, GPT-6, H100), liczby, kwoty i procenty schodza",
        all(n in _bc for n in ("K3.1", "GPT-6", "H100")) and not CYFRA.search(_bc)
        and "%" not in _bc and "$" not in _bc, _bc)
sprawdz("termin: tylko daty YYYY-MM-DD", plan["termin"] == [{"co": "full weights", "kiedy": "2026-11-04"}],
        plan["termin"])
sprawdz("pominiete soczewki z powodem, wymagane uzyte", {p["soczewka"] for p in plan["pominiete_soczewki"]}
        == {"CONSEQUENCES", "NUMBERS", "PRECEDENT"} and set(sp.WYMAGANE) <= set(plan["soczewki"]))
sprawdz("zapytanie bez nazwy historii dostaje ja na poczatek",
        all("kimi" in p["zapytanie"].lower() or "k3.1" in p["zapytanie"].lower() for p in plan["pytania"]),
        [p["zapytanie"] for p in plan["pytania"]])
_prompt_planu = WYWOLANIA[0][2]
sprawdz("model widzi typ, hosty, ktorych nie pobieramy, naglowki i DWA najdluzsze poczatki",
        "(model release)" in _prompt_planu and "youtube.com" in _prompt_planu
        and config.BLOCKED_HOSTS[0] in _prompt_planu and "Moonshot's Kimi K3.1 Pro tops" in _prompt_planu
        and "highest score of any model" in _prompt_planu and "Full model weights" in _prompt_planu
        and "Kimi is out." not in _prompt_planu, _prompt_planu[-900:])
sprawdz("system planu niesie marke z config.MARKA", config.MARKA in WYWOLANIA[0][1])
sprawdz("plan pamieta pytanie glowne i typ (dla krytyka)", plan["pytanie_glowne"].startswith("What does Kimi")
        and plan["typ"] == "premiera" and plan["bezpieczenstwo"] is False)
sprawdz("brak FALLBACK w logu dobrego planu", "FALLBACK" not in log, log[-300:])

# =================================================================================
print()
print("=== 3. TEST PODMIANY WOBEC SZABLONOW, NAZWY, NAGLOWKA, DUBLA ===")
_zle = [
    q("NEW", "What does this change for an ordinary person?", 1),
    q("NEW", "What exactly changed with Kimi K3.1 Pro, against which baseline?", 1),
    q("TIDBIT", "Did Kimi K3.1 Pro write 150M tokens on the Intelligence Index?", 2),
    q("PEOPLE", "What do developers who tried Kimi K3.1 Pro report about its coding, and where do they "
                "disagree with each other?", 2),
    q("HOW_IT_WORKS", "How does it work?", 1),
    q("NEWS", "Is Kimi K3.1 Pro new?", 1),
    q("PRACTICAL", "What does Kimi K3.1 Pro cost to run?", 2, dowod=""),
    q("PRACTICAL", "Kimi K3.1 Pro pricing", 2),
]
ustaw(pytania_ciekawosci=[dict(PLAN_KIMI, pytania=DOBRE_KIMI + _zle)])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "What does Kimi K3.1 Pro really prove?", LEDES)
_od = plan["odrzucone"]
sprawdz("odpadlo dokladnie 8 zlych, zostalo 9 dobrych", len(plan["pytania"]) == 9 and len(_od) == 8,
        [(o["q"][:40], o["powod"]) for o in _od])
sprawdz("pytanie bez nazw historii odpada", "nie nazywa" in powod(_od, "What does this change for"), _od)
sprawdz("pytanie przepisane z linii soczewki z nazwa w srodku odpada jako szablon",
        "szablon NEW" in powod(_od, "What exactly changed with Kimi"), _od)
sprawdz("pytanie, na ktore odpowiada naglowek, odpada", "naglowku" in powod(_od, "Did Kimi K3.1 Pro write"), _od)
sprawdz("dubel pytania z tego samego planu odpada", "dubel" in powod(_od, "What do developers who tried"), _od)
sprawdz("nieznana soczewka, brak dowodu, pytanie bez nazw i nie-pytanie odpadaja",
        "nieznana soczewka" in powod(_od, "Is Kimi K3.1 Pro new?")
        and "dowod" in powod(_od, "What does Kimi K3.1 Pro cost to run?")
        and "nie nazywa" in powod(_od, "How does it work?")
        and "to nie pytanie" in powod(_od, "Kimi K3.1 Pro pricing"), _od)
sprawdz("odrzuconych NIE dopelniamy szablonami (zero pytan stalych)",
        not any(p.get("stale") for p in plan["pytania"]) and plan["fallback"] is False)
# KONTRDOWOD: test podmiany nie jest czerwony na wszystkim — konkretne pytania o te historie
# z tymi samymi slowami pytajnymi co szablony przechodza.
_k = sp._kontekst(KIMI, "", LEDES, poprzednie=False)
sprawdz("KONTRDOWOD: konkretne pytanie o te historie przechodzi test podmiany",
        sp._powod_odrzucenia(sp._pytanie_z_modelu(DOBRE_KIMI[0], 0), _k, []) == "")
sprawdz("aktor nazwany tylko na poczatku zdania zrodla tez nazywa historie (Moonshot)",
        sp._nazywa_historie("What did Moonshot promise about the release?", _k)
        and not sp._nazywa_historie("What did the company promise about the release?", _k))
sprawdz("wielka litera w naglowku Title Case nie robi z pytania ogolnego pytania o historie",
        not sp._nazywa_historie("Are open weights good for everyone?", _k))
_bez_nazw = {"tytul": "Teenagers who talk to chatbots daily report more loneliness, survey finds",
             "naglowki": [{"kanal": "BBC", "temat": "Daily chatbot use linked to teen loneliness"}]}
_kb = sp._kontekst(_bez_nazw, "", [], poprzednie=False)
sprawdz("historia bez nazwy wlasnej: dwa slowa tresci tytulu nazywaja historie",
        not _kb["wyrozniajace"]
        and sp._nazywa_historie("How lonely do teenagers who chat daily say they feel?", _kb)
        and not sp._nazywa_historie("What does this change for an ordinary person?", _kb))
sprawdz("KONTRDOWOD: przy historii z nazwa same slowa tytulu nie wystarcza",
        not sp._nazywa_historie("Do closed models still win coding tests?", _k))
sprawdz("liczba z tekstow historii nazywa historie, liczba spoza nie",
        sp._nazywa_historie("Why does a model need 150 times more tokens?", _k)
        and not sp._nazywa_historie("Why does a model need 999 times more tokens?", _k))
# RECENZJA 25.10.2026: te ogolne pytania przechodzily bramke nazwy (pierwsze slowo z wielkiej
# litery z lede, rok albo mala liczba z tekstow historii).
for _ogolne in ("Overall, who pays for this?", "Despite the hype, what do ordinary users actually report?",
                "After the launch, who pays first and who gains later?",
                "What will change for ordinary people in 2026?",
                "What are the 3 biggest complaints users have about chatbots?"):
    sprawdz("ogolne pytanie nie nazywa historii: %s" % _ogolne[:40], not sp._nazywa_historie(_ogolne, _k))
sprawdz("KONTRDOWOD: nazwa produktu na poczatku pytania dalej nazywa historie",
        sp._nazywa_historie("Kimi K3.1 Pro or Claude: which one costs less per task?", _k))

# =================================================================================
print()
print("=== 4. TEST PODMIANY WOBEC SZESCIU OSTATNICH PLANOW ===")
_plik = config.DATA_DIR / sledztwo.PLIK_SLEDZTW
_rekordy = [
    # siodmy od konca: jego wzor NIE moze juz odrzucac
    {"run_id": 1, "kiedy": "2026-10-01", "historia": "Najstarsza", "klucze": ["Gizmo"],
     "plan_pytania": ["Who audits the Gizmo safety claims before they ship to schools?"]},
]
for i in range(2, 7):
    _rekordy.append({"run_id": i, "kiedy": "2026-10-%02d" % (i + 1), "historia": "Inna %d" % i,
                     "plan_pytania": [{"id": "Q1", "q": "What did Lab%d publish about Model%d?" % (i, i)}]})
_rekordy.append({"run_id": 7, "kiedy": "2026-10-20", "historia": "Wczorajsza", "klucze": ["Widget"],
                 "plan_pytania": [{"id": "Q3", "soczewka": "POWER",
                                   "q": "How much does Acme charge per million output tokens for Widget 7 "
                                        "compared with Gizmo 2?"}]})
_plik.write_text("\n".join(json.dumps(r) for r in _rekordy) + "\nto nie jest json\n", encoding="utf-8")
_powtorka = q("POWER", "How much does Moonshot charge per million output tokens for K3.1 Pro compared with "
                       "Claude Opus 5.5?", 2)
_stary_wzor = q("CONSEQUENCES", "Who audits the Kimi K3.1 Pro safety claims before they ship to schools?", 2)
ustaw(pytania_ciekawosci=[dict(PLAN_KIMI, pytania=DOBRE_KIMI + [_powtorka, _stary_wzor])])
plan, log = cicho(sp.plan_sledztwa, None, 99, KIMI, "What does Kimi K3.1 Pro really prove?", LEDES)
_od = plan["odrzucone"]
sprawdz("pytanie o wzorze z planu sprzed dnia (inne nazwy) odpada jako ogolne",
        "jak pytanie planu 2026-10-20" in powod(_od, "How much does Moonshot charge"), _od)
sprawdz("wzor z SIODMEGO planu od konca juz nie odrzuca (okno = 6 planow)",
        any(p["q"].startswith("Who audits the Kimi") for p in plan["pytania"]), _od)
sprawdz("zla linia pliku nie psuje odczytu", len(sp._poprzednie_plany()) == 6, len(sp._poprzednie_plany()))
sprawdz("plan z tego samego przebiegu nie jest wlasnym poprzednikiem",
        any("Wczorajsza" in p["etykieta"] for p in sp._poprzednie_plany())
        and all("Wczorajsza" not in p["etykieta"] for p in sp._poprzednie_plany(run_id=7)))
# KONTRDOWOD: ten sam plan, gdy JEST w oknie szesciu, odrzuca — inaczej powyzsze nic nie mowi.
_plik.write_text("\n".join(json.dumps(r) for r in _rekordy[:6]) + "\n", encoding="utf-8")
ustaw(pytania_ciekawosci=[dict(PLAN_KIMI, pytania=DOBRE_KIMI + [_stary_wzor])])
plan, log = cicho(sp.plan_sledztwa, None, 99, KIMI, "x", LEDES)
sprawdz("KONTRDOWOD: ten sam wzor z planu w oknie szesciu odrzuca",
        "jak pytanie planu 2026-10-01" in powod(plan["odrzucone"], "Who audits the Kimi"), plan["odrzucone"])
_plik.unlink()

# =================================================================================
print()
print("=== 5. ODMOWA, UCIECIE, ZA MALO DOBRYCH, OBA ZLE -> FALLBACK ===")
_zapas_kimi = dict(PLAN_KIMI)
ustaw(pytania_ciekawosci=[llm.OdmowaDostawcy("refusal: cyber")], pytania_ciekawosci_zapas=[_zapas_kimi])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("odmowa Sonnetu -> zapas, plan z zapasu bez FALLBACK",
        cele() == ["pytania_ciekawosci", "pytania_ciekawosci_zapas"] and len(plan["pytania"]) == 9
        and plan["fallback"] is False and plan["model"] == config.MODEL_FOR.get("pytania_ciekawosci_zapas",
                                                                                  "pytania_ciekawosci_zapas")
        and "FALLBACK" not in log, (cele(), plan["model"]))
sprawdz("proby zapisane w planie (odmowa, potem wynik zapasu)",
        plan["proby"][0]["wynik"].startswith("odmowa") and "9 dobrych" in plan["proby"][1]["wynik"], plan["proby"])
ustaw(pytania_ciekawosci=[llm.Truncated("max_tokens")], pytania_ciekawosci_zapas=[PLAN_KIMI])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("uciecie Sonnetu -> zapas", cele() == ["pytania_ciekawosci", "pytania_ciekawosci_zapas"]
        and not plan["fallback"] and "uciete" in plan["proby"][0]["wynik"], plan["proby"])
_cztery = dict(PLAN_KIMI, pytania=DOBRE_KIMI[:4])
_dobry_zapas = dict(PLAN_KIMI, pytania=DOBRE_KIMI[:7])
ustaw(pytania_ciekawosci=[_cztery], pytania_ciekawosci_zapas=[_dobry_zapas])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("4 dobre pytania -> JEDNA proba zapasu, wygrywa lepsza (7 pytan)",
        cele() == ["pytania_ciekawosci", "pytania_ciekawosci_zapas"] and len(plan["pytania"]) == 7
        and not plan["fallback"] and "jedna proba zapasu" in log, (cele(), len(plan["pytania"])))
_bez_smaczku = dict(PLAN_KIMI, pytania=[p for p in DOBRE_KIMI if p["soczewka"] not in ("TIDBIT", "WATCH")])
ustaw(pytania_ciekawosci=[_bez_smaczku], pytania_ciekawosci_zapas=[_cztery])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("KONTRDOWOD: gorszy zapas nie wypiera lepszego Sonnetu (brak TIDBIT -> proba, ale zostaje Sonnet)",
        cele() == ["pytania_ciekawosci", "pytania_ciekawosci_zapas"]
        and plan["model"] == config.MODEL_FOR.get("pytania_ciekawosci") and len(plan["pytania"]) == 7
        and any("brak wymaganej soczewki: TIDBIT" in b for b in plan["braki"]),
        (cele(), plan["model"], plan["braki"]))
ustaw(pytania_ciekawosci=[_cztery], pytania_ciekawosci_zapas=[dict(PLAN_KIMI, pytania=DOBRE_KIMI[:2])])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("obie proby ponizej progu -> FALLBACK w logu, fallback=True",
        plan["fallback"] is True and "[plan] FALLBACK" in log, log[-400:])
sprawdz("plan awaryjny zachowuje dobre pytania modelu i dokłada stale dla brakujacych soczewek",
        sum(1 for p in plan["pytania"] if not p.get("stale")) == 4
        and set(sp.WYMAGANE) <= set(plan["soczewki"]) and len(plan["pytania"]) >= sp.MIN_PYTAN
        and all("Kimi K3.1 Pro" in p["q"] for p in plan["pytania"] if p.get("stale")),
        [(p["soczewka"], p.get("stale"), p["q"][:40]) for p in plan["pytania"]])
ustaw(pytania_ciekawosci=[RuntimeError("siec")], pytania_ciekawosci_zapas=[KeyError("pytania_ciekawosci_zapas")])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES, typ="premiera")
sprawdz("oba modele padly -> pytania stale, FALLBACK, dokumenty typu premiery, zero wyjatku",
        plan["fallback"] and "FALLBACK" in log and len(plan["pytania"]) == sp.PYTAN_W_ZAPASIE
        and all(p.get("stale") for p in plan["pytania"]) and len(plan["dokumenty"]) == 2
        and "model card" in plan["dokumenty"][0]["co"] and plan["model"] == "pytania stale",
        (len(plan["pytania"]), plan["dokumenty"], plan["model"]))
ustaw(pytania_ciekawosci=[llm.BudgetExceeded("sufit")])
try:
    cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
    _przeszlo = False
except llm.BudgetExceeded:
    _przeszlo = True
sprawdz("BudgetExceeded przechodzi (przerywa przebieg, nie zapas)", _przeszlo and cele() == ["pytania_ciekawosci"])
ustaw()
plan, log = cicho(sp.plan_sledztwa, None, 7, None, None, None)
sprawdz("smieciowe wejscie (h=None) -> plan stalych pytan, nie wyjatek",
        plan["fallback"] and len(plan["pytania"]) >= sp.MIN_PYTAN, log[-300:])

# =================================================================================
print()
print("=== 6. HISTORIA O LUCE: STRONA OBRONCY ===")
LUKA = {"miejsce": 2, "tytul": "PHP2Shell: AI-found PHP vulnerability lets attackers run code on servers",
        "kategoria": "RYZYKO_BEZPIECZENSTWO", "zapytanie": "PHP2Shell", "klucze": ["PHP2Shell", "PHP"],
        "naglowki": [{"kanal": "The Register", "temat": "PHP2Shell vulnerability found with frontier models",
                      "url": "https://www.theregister.com/php", "data": "2026-10-21"}]}
# RECENZJA 25.10.2026: filtr exploita przepuszczal pytania o samo „exploit" i repozytoria.
_kl = sp._kontekst(LUKA, "", [], poprzednie=False)
for _zle in ("Where can the PHP2Shell exploit be downloaded from GitHub?",
             "Is there a public exploit for PHP2Shell yet?",
             "Which PHP request triggers PHP2Shell and what does the malicious request look like?"):
    _pz = sp._pytanie_z_modelu({"soczewka": "PRACTICAL", "pytanie": _zle, "dowod": "repo", "gdzie": "github"}, 0)
    sprawdz("luka: pytanie o exploit odpada: %s" % _zle[:40], "exploita" in sp._powod_odrzucenia(_pz, _kl, []))
_pz = sp._pytanie_z_modelu({"soczewka": "PRACTICAL", "pytanie": "Is PHP2Shell being exploited in the wild, "
                            "and which PHP versions are exposed?", "dowod": "advisory", "gdzie": "php.net"}, 0)
sprawdz("KONTRDOWOD: pytanie o wykorzystywanie w sieci (narazenie) zostaje",
        "exploita" not in sp._powod_odrzucenia(_pz, _kl, []))
_odrz_dok = []
_dok = sp._dokumenty([{"co": "public exploit for PHP2Shell", "kto": "researchers", "gdzie": "exploit-db.com"},
                      {"co": "PHP2Shell advisory", "kto": "PHP maintainers", "gdzie": "php.net"}], _kl, _odrz_dok)
sprawdz("luka: dokument z exploitem odpada, advisory zostaje",
        [d["co"] for d in _dok] == ["PHP2Shell advisory"] and len(_odrz_dok) == 1, (_dok, _odrz_dok))
sprawdz("premiera z jednym naglowkiem o hakerach to nie historia o luce",
        not sp._bezpieczenstwo({"tytul": "Kimi K3.1 Pro launches", "kategoria": "PREMIERA_MODELU",
                                "naglowki": [{"temat": "Hackers jailbreak Kimi K3.1 Pro within hours"}]}))
sprawdz("historia o pracy z 'exploited by' to nie historia o luce",
        not sp._bezpieczenstwo({"tytul": "Gig workers exploited by AI data-labelling firms",
                                "kategoria": "PRACA_EKONOMIA", "naglowki": []}))
# Proza planu bez liczb, takze z doklejona jednostka (recenzja 25.10.2026).
for _wej, _wyj in (("Each H100 has 80GB of memory", "Each H100 has of memory"),
                   ("a 1GW data centre", "a data centre"),
                   ("565MW against 296.8 MW", "against"),
                   ("the 2nd lab", "the lab"), ("a $2.8T market", "a market"),
                   ("Kimi K3.1 Pro beats GPT-6", "Kimi K3.1 Pro beats GPT-6")):
    sprawdz("bez cyfr: %r" % _wej, sp._bez_cyfr(_wej) == _wyj, sp._bez_cyfr(_wej))
_pyt_luki = [
    q("NEW", "What did the PHP2Shell disclosure add to the 2024 maintainers' note on the same PHP weakness?", 1),
    q("HOW_IT_WORKS", "How much did frontier models lower the cost of finding PHP2Shell compared with the "
                      "earlier manual audits of PHP?", 1),
    q("PRACTICAL", "Which PHP versions are exposed to PHP2Shell, and is there a patch from the PHP maintainers?", 1),
    q("BIG", "Is PHP2Shell the first flaw that AI found faster than PHP's own maintainers, or a rediscovery?", 1),
    q("TIDBIT", "What does the PHP2Shell advisory say about who reported it first?", 2),
    q("PEOPLE", "What do PHP hosting administrators report about patching PHP2Shell?", 2),
    q("CLAIM", "Where is the working proof-of-concept for PHP2Shell on GitHub?", 2),
    q("WATCH", "When will the PHP maintainers ship the PHP2Shell fix to the long-term branch?", 3),
]
ustaw(pytania_ciekawosci=[{"pytania": _pyt_luki, "dokumenty": [
    {"co": "PHP2Shell security advisory", "kto": "PHP maintainers", "gdzie": "php.net"},
    {"co": "PHP2Shell PoC exploit repository", "kto": "researcher", "gdzie": "github.com/x/php2shell-poc"},
    {"co": "CVE entry for PHP2Shell", "kto": "MITRE", "gdzie": "cve.org"}]}])
plan, log = cicho(sp.plan_sledztwa, None, 8, LUKA, "Did AI find PHP2Shell?", [])
sprawdz("model widzi „security incident” w typie historii", "(news story; security incident)" in WYWOLANIA[0][2])
sprawdz("plan oznaczony jako historia o luce", plan["bezpieczenstwo"] is True)
sprawdz("pytanie o dzialajacy PoC odpada", any("exploita" in o["powod"] and "proof-of-concept" in o["q"]
                                             for o in plan["odrzucone"]), plan["odrzucone"])
sprawdz("dokument z repozytorium PoC odpada, advisory i CVE zostaja",
        [d["co"] for d in plan["dokumenty"]] == ["PHP2Shell security advisory", "CVE entry for PHP2Shell"],
        plan["dokumenty"])
sprawdz("KONTRDOWOD: pytania obroncy (wersje, patch, koszt znalezienia) zostaja",
        any("patch" in p["q"] for p in plan["pytania"]) and any("lower the cost" in p["q"] for p in plan["pytania"]))
ustaw(pytania_ciekawosci=[RuntimeError("x")], pytania_ciekawosci_zapas=[RuntimeError("y")])
plan, log = cicho(sp.plan_sledztwa, None, 8, LUKA, "Did AI find PHP2Shell?", [])
_jak = [p for p in plan["pytania"] if p["soczewka"] == "HOW_IT_WORKS"]
sprawdz("plan awaryjny przy luce: HOW_IT_WORKS od strony obroncy, dokument = advisory",
        _jak and _jak[0]["q"].startswith("Who is exposed by PHP2Shell")
        and plan["dokumenty"][0]["co"].startswith("the security advisory"), (_jak, plan["dokumenty"]))
sprawdz("KONTRDOWOD: premiera modelu (bez slow o luce) nie jest historia o luce",
        sp._bezpieczenstwo(KIMI) is False)

# =================================================================================
print()
print("=== 7. BRAK JSON-U -> RATUNEK; PROMPT, KTORY SIE NIE SKLADA ===")
ustaw(pytania_ciekawosci=["Here is my plan in prose: " + "the questions are many. " * 20])
RATUNKI.append(json.dumps(PLAN_KIMI))
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("proza zamiast JSON-u -> ratuj_json tym samym celem, plan z ratunku",
        cele() == ["pytania_ciekawosci", "ratuj:pytania_ciekawosci"] and len(plan["pytania"]) == 9, cele())
ustaw(pytania_ciekawosci=["proza " * 60], pytania_ciekawosci_zapas=[PLAN_KIMI])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("ratunek pusty -> zapas", cele() == ["pytania_ciekawosci", "ratuj:pytania_ciekawosci",
                                            "pytania_ciekawosci_zapas"] and not plan["fallback"], cele())
_stary_prompt = stages._prompt
stages._prompt = lambda name, **k: (_ for _ in ()).throw(KeyError("brakujace_pole"))
try:
    ustaw()
    plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
finally:
    stages._prompt = _stary_prompt
sprawdz("prompt, ktory sie nie sklada -> FALLBACK glosno, bez wywolania modelu",
        plan["fallback"] and "prompt planu sie nie sklada" in log and cele() == [], log[-200:])
_bez_big = dict(PLAN_KIMI, pytania=[p for p in DOBRE_KIMI if p["soczewka"] != "BIG"],
                wielkie_pytanie={"pytanie": "Has Moonshot's Kimi K3.1 Pro closed the gap with the closed labs",
                                 "wieksze_niz_wyglada": "a", "mniejsze_niz_wyglada": "b"})
ustaw(pytania_ciekawosci=[_bez_big])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
sprawdz("brak pytania BIG, ale jest wielkie_pytanie -> pytanie BIG z planu (bez zapasu)",
        cele() == ["pytania_ciekawosci"] and any(p["soczewka"] == "BIG" and p["q"].endswith("closed labs?")
                                                 for p in plan["pytania"]), (cele(), plan["braki"]))

ustaw(pytania_ciekawosci=[dict(PLAN_KIMI, dokumenty=[{"co": "Kimi K3.1 Pro model card", "kto": "Moonshot",
                                                      "gdzie": "kimi.ai"}])])
plan, log = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES, typ="premiera")
sprawdz("jeden dokument -> uzupelniony z tabeli typu (cennik i licencja), bez dubla karty modelu",
        [d["co"] for d in plan["dokumenty"]] == ["Kimi K3.1 Pro model card",
                                                 "the pricing and licence page of Kimi K3.1 Pro"]
        and not plan["fallback"] and any("tabeli typu" in b for b in plan["braki"]), plan["dokumenty"])

# =================================================================================
print()
print("=== 8. PYTANIA TEKSTEM I PLAN DO KATOW ===")
ustaw(pytania_ciekawosci=[PLAN_KIMI])
plan, _ = cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
_tekst = sp.pytania_tekstem(plan["pytania"])
sprawdz("pytania_tekstem: '- [Q1|NEW] ...?' w kolejnosci wagi",
        _tekst.splitlines()[0].startswith("- [Q1|NEW] What did Moonshot change")
        and len(_tekst.splitlines()) == 9, _tekst[:200])
sprawdz("pytania_tekstem sortuje po wadze takze cudza liste",
        sp.pytania_tekstem([{"id": "K1", "soczewka": "TIDBIT", "q": "b?", "waga": 3},
                            {"id": "Q2", "soczewka": "NEW", "q": "a?", "waga": 1}, {"q": ""}, "zle"])
        == "- [Q2|NEW] a?\n- [K1|TIDBIT] b?")
_karty = sp.plan_do_kart(plan)
sprawdz("plan_do_kart: pytania (id, soczewka, q), oba przypadki BIG, rdzen AI, zalozenie",
        set(_karty) == {"pytania", "wielkie_pytanie", "rdzen_ai", "zalozenie_czytelnika"}
        and set(_karty["pytania"][0]) == {"id", "soczewka", "q"}
        and set(_karty["wielkie_pytanie"]) == {"pytanie", "wieksze_niz_wyglada", "mniejsze_niz_wyglada"})
sprawdz("plan_do_kart: bez naszego typu, smaczku i dokumentow; proza bez cyfr",
        "smaller" not in json.dumps(_karty["wielkie_pytanie"]) and "smaczek" not in _karty
        and not CYFRA.search(json.dumps({k: v for k, v in _karty.items() if k != "pytania"})),
        _karty["wielkie_pytanie"])
sprawdz("plan_do_kart czysci cyfry takze w planie spoza plan_sledztwa",
        sp.plan_do_kart({"rdzen_ai": "Costs fell 40% in 2026"})["rdzen_ai"] == "Costs fell in",
        sp.plan_do_kart({"rdzen_ai": "Costs fell 40% in 2026"}))
sprawdz("pusty plan -> pusty slownik", sp.plan_do_kart({}) == {} and sp.plan_do_kart(None) == {})

# =================================================================================
print()
print("=== 9. STARSZY REDAKTOR ===")
KSIEGA = [
    {"id": "Q1", "soczewka": "NEW", "q": DOBRE_KIMI[0]["pytanie"], "waga": 1, "status": "answered",
     "odpowiedz": "Moonshot says it narrowly loses to Claude Opus 5.5 on Terminal-Bench 4.0.",
     "zrodla": [{"url": "https://kimi.ai/blog/k3-1", "quote": "narrowly behind Claude Opus 5.5 (66.4%)"}]},
    {"id": "Q5", "soczewka": "TIDBIT", "q": DOBRE_KIMI[4]["pytanie"], "waga": 2, "status": "open",
     "odpowiedz": "", "zrodla": []},
]
_kryt = {"pozycje": [
    {"rodzaj": "a", "soczewka": "CLAIM", "pytanie": "Where is Moonshot's own Kimi K3.1 Pro model card that "
     "states the date for the full weights?", "dlaczego": "we cite the date second-hand",
     "dowod": "the model card", "gdzie": "Hugging Face", "zapytanie": "\"Kimi K3.1 Pro\" model card weights"},
    {"rodzaj": "b", "pytanie": "What does this change for an ordinary person?", "zapytanie": "impact"},
    {"rodzaj": "c", "soczewka": "NEW", "pytanie": DOBRE_KIMI[0]["pytanie"], "zapytanie": "x"},
    {"rodzaj": "d", "pytanie": "Why does Artificial Analysis list Kimi K3.1 Pro as proprietary while it is "
     "billed as open weights?", "zapytanie": ""},
    {"rodzaj": "c", "soczewka": "CLAIM", "pytanie": "Is the $10 per million output tokens price for Kimi K3.1 "
     "Pro from Moonshot or only from OpenRouter?", "zapytanie": "Kimi K3.1 Pro pricing per million"},
    {"rodzaj": "b", "soczewka": "POWER", "pytanie": "Which Kimi K3.1 Pro customers leave closed labs first?",
     "zapytanie": "Kimi K3.1 Pro customers"},
], "uwagi": ["The 67% figure comes from one evaluator.", 7]}
ustaw(krytyk_sledztwa=[_kryt])
wyn, log = cicho(sp.krytyk, None, 7, KIMI, plan, KSIEGA)
sprawdz("najwyzej trzy pozycje, id K1..K3, waga 1",
        [p["id"] for p in wyn["pytania"]] == ["K1", "K2", "K3"] and all(p["waga"] == 1 for p in wyn["pytania"]),
        [(p["id"], p["q"][:40]) for p in wyn["pytania"]])
sprawdz("ksztalt jak pytania planu + rodzaj i dlaczego",
        all({"id", "soczewka", "q", "waga", "dowod", "gdzie", "zapytanie", "rodzaj", "dlaczego"} <= set(p)
            for p in wyn["pytania"]))
_pk_powody = [o["powod"] for o in wyn["odrzucone"]]
sprawdz("ogolna pozycja i powtorka odpowiedzianego pytania odpadaja; czwarta dobra — ponad limit",
        any("nie nazywa" in x for x in _pk_powody) and any("dubel" in x for x in _pk_powody)
        and any("ponad 3" in x for x in _pk_powody), _pk_powody)
sprawdz("brak soczewki -> z rodzaju (d -> TIDBIT); puste wyszukiwanie dostaje nazwe historii",
        wyn["pytania"][1]["soczewka"] == "TIDBIT" and "Kimi" in wyn["pytania"][1]["zapytanie"], wyn["pytania"][1])
sprawdz("uwagi tylko napisy, najwyzej trzy", wyn["uwagi"] == ["The 67% figure comes from one evaluator."])
_pk_prompt = WYWOLANIA[0][2]
sprawdz("krytyk widzi plan, ksiege ze statusami i zrodlami, typ i pytanie glowne",
        "[Q1|NEW]" in _pk_prompt and "status: answered" in _pk_prompt and "kimi.ai/blog" in _pk_prompt
        and "(model release)" not in _pk_prompt and "(news story)" in _pk_prompt
        and "record that must exist" in _pk_prompt and "(not built yet" in _pk_prompt, _pk_prompt[-700:])
ustaw(krytyk_sledztwa=[llm.OdmowaDostawcy("cyber")], krytyk_sledztwa_zapas=[_kryt])
wyn, log = cicho(sp.krytyk, None, 7, KIMI, plan, KSIEGA, {"confirmed_claims": [
    {"claim": "AA measured 67%", "url": "https://artificialanalysis.ai/x"}]})
sprawdz("odmowa -> zapas DeepSeek", cele() == ["krytyk_sledztwa", "krytyk_sledztwa_zapas"]
        and len(wyn["pytania"]) == 3, cele())
sprawdz("karta, gdy jest, idzie do krytyka", "AA measured 67%" in WYWOLANIA[-1][2])
ustaw(krytyk_sledztwa=[RuntimeError("a")], krytyk_sledztwa_zapas=[llm.Truncated("b")])
wyn, log = cicho(sp.krytyk, None, 7, KIMI, plan, KSIEGA)
sprawdz("obie proby padly -> pusto, bez wyjatku", wyn["pytania"] == [] and wyn["uwagi"] == []
        and "bez uwag" in log, log)
ustaw(krytyk_sledztwa=[{"pozycje": [], "uwagi": []}])
wyn, _ = cicho(sp.krytyk, None, 7, KIMI, plan, KSIEGA)
sprawdz("pusta lista to poprawny wynik — bez zapasu", wyn["pytania"] == [] and cele() == ["krytyk_sledztwa"])
_baza = sqlite3.connect(":memory:")
_baza.execute("CREATE TABLE calls (run_id INT, purpose TEXT, cost_usd REAL)")
_baza.execute("INSERT INTO calls VALUES (7, 'investigation_search', 0.07), (7, 'investigation_extract', 0.04),"
              " (7, 'przeslania', 5.0), (8, 'investigation_search', 0.5)")
ustaw()
wyn, log = cicho(sp.krytyk, _baza, 7, KIMI, plan, KSIEGA)
sprawdz("badanie wydalo prog (0,11 >= 0,10) -> krytyk pominiety bez wywolania",
        cele() == [] and "pominiety" in wyn and "0.110" in log, log)
ustaw(krytyk_sledztwa=[_kryt])
_baza.execute("UPDATE calls SET cost_usd = 0.01 WHERE run_id = 7 AND purpose LIKE 'investigation%'")
wyn, _ = cicho(sp.krytyk, _baza, 7, KIMI, plan, KSIEGA)
sprawdz("KONTRDOWOD: ponizej progu (koszt innych etapow sie nie liczy) krytyk rusza",
        cele() == ["krytyk_sledztwa"] and len(wyn["pytania"]) == 3, cele())
ustaw()
wyn, log = cicho(sp.krytyk, None, 7, KIMI, {}, [])
sprawdz("bez planu i ksiegi -> pominiety", cele() == [] and wyn["pytania"] == [] and "pominiety" in wyn)
wyn, log = cicho(sp.krytyk, None, 7, None, None, None)
sprawdz("smieci na wejsciu -> pusto, nie wyjatek", wyn["pytania"] == [])
ustaw(krytyk_sledztwa=[{"pozycje": [{"rodzaj": "a", "pytanie": "Where is the PHP2Shell working exploit code "
                                     "on GitHub?", "zapytanie": "PHP2Shell exploit code github"},
                                    {"rodzaj": "a", "pytanie": "Where is the official PHP2Shell advisory from "
                                     "the PHP maintainers?", "zapytanie": "PHP2Shell advisory php.net"}]}])
wyn, _ = cicho(sp.krytyk, None, 8, LUKA, {"pytania": [{"id": "Q1", "q": "x?"}], "typ": "sledztwo"}, [])
sprawdz("krytyk przy luce: pozycja o exploit odpada, advisory zostaje",
        [p["q"][:30] for p in wyn["pytania"]] == ["Where is the official PHP2Shel"]
        and "security incident" in WYWOLANIA[0][2], wyn)

# =================================================================================
print()
print("=== 10. KANAL KOSZTU NA KAZDYM PLATNYM WYWOLANIU ===")
ustaw(pytania_ciekawosci=["proza " * 60], pytania_ciekawosci_zapas=[PLAN_KIMI], krytyk_sledztwa=[_kryt])
RATUNKI.append("")
_stara_akcja = db.AKCJA
cicho(sp.plan_sledztwa, None, 7, KIMI, "x", LEDES)
cicho(sp.krytyk, None, 7, KIMI, plan, KSIEGA)
sprawdz("plan, ratunek, zapas i krytyk ksieguja sie na kanal „artykul”",
        len(WYWOLANIA) == 4 and all(w[3] == "artykul" for w in WYWOLANIA), [(w[0], w[3]) for w in WYWOLANIA])
sprawdz("i kanal jest zdjety po wyjsciu", db.AKCJA == _stara_akcja, db.AKCJA)

llm.call, llm.ratuj_json = _prawdziwy_call, _prawdziwy_ratunek
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
