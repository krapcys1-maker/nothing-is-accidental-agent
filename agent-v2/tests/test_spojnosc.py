# -*- coding: utf-8 -*-
"""Spojnosc nowej notki serii z naszymi opublikowanymi (27.10.2026, `spojnosc.py`).

PO CO TEN TEST. 27.10 reczne czytanie kolejki wykazalo, ze notka 506-2 przeczy opublikowanym 499-1
i 499-4 — a zadna bramka tego nie widziala, bo sprawdzenie faktow szuka w SIECI, nie w naszym
dzienniku. `spojnosc.sprawdz` pyta dziennika przy publikacji. Test pilnuje kolejnosci tanich krokow
(brak kandydatow = zero wywolan, cytat spoza tekstu zabija znalezisko PRZED platnym potwierdzeniem),
rozstrzygniec (aktualizacja i „wygrywa nowa” to nie naprawa), zapasu przy odmowie Opusa, granicy
„nie sprawdzilem to nie czysto”, a przy `stages.note` — ze sprzecznosc idzie przez te sama naprawe co
obalony fakt, naprawa jest sprawdzana ponownie, a przy porazce zostaje oryginal.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_spojnosc.py
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

KATALOG = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KATALOG)

import db          # noqa: E402
import llm         # noqa: E402
import spojnosc    # noqa: E402
import stages      # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1500]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = fn(*a, **k)
    return wynik, log.getvalue()


# --- atrapa modelu: kolejki odpowiedzi PER CEL; ostatnia odpowiedz sie powtarza -------------------
WYWOLANIA = []
ODP = {}


def atrapa(purpose, system, prompt, conn=None, run_id=None, **k):
    WYWOLANIA.append({"purpose": purpose, "system": system, "prompt": prompt})
    kolejka = ODP.get(purpose)
    if kolejka is None:
        raise AssertionError("NIEDOZWOLONE wywolanie modelu: %s" % purpose)
    o = kolejka.pop(0) if len(kolejka) > 1 else kolejka[0]
    if isinstance(o, BaseException):
        raise o
    return o if isinstance(o, str) else json.dumps(o)


_prawdziwy_call = llm.call
llm.call = atrapa


def cele():
    return [w["purpose"] for w in WYWOLANIA]


def reset(**odp):
    spojnosc._OPUS_ODMOWIL = False
    WYWOLANIA.clear()
    ODP.clear()
    ODP.update({k: list(v) for k, v in odp.items()})


# --- dane --------------------------------------------------------------------------------------
TERAZ = datetime(2026, 10, 27, 17, 0, tzinfo=timezone.utc)
NOWA = ("The PHP Foundation reported the remote code execution flaw first, on 11 August, and OpenAI "
        "independently reported the same root cause. Labs now compete on reputation, and credit is the "
        "prize in every advisory.")
WCZESNIEJSZA = ("Wiz reported the remote code execution flaw in PHP first, on 19 August, using Wiz Atlas, "
                "and nobody else had found the same root cause by then.")
NIEZWIAZANA = "Cats sleep most of the day and dream about tuna, which is a pleasant habit worth admiring."

CYTAT_NOWY = "The PHP Foundation reported the remote code execution flaw first, on 11 August"
CYTAT_STARY = "Wiz reported the remote code execution flaw in PHP first, on 19 August"


def wpis(tekst, dni_temu, rodzaj="notka", udane=True, **reszta):
    kiedy = (TERAZ - timedelta(days=dni_temu)).isoformat()
    return dict({"kiedy": kiedy, "rodzaj": rodzaj, "udane": udane, "tekst": tekst}, **reszta)


def zapisz_dziennik(wpisy, surowe_linie=()):
    linie = [json.dumps(w, ensure_ascii=False) for w in wpisy] + list(surowe_linie)
    (config.DATA_DIR / "dziennik.jsonl").write_text("\n".join(linie) + "\n", encoding="utf-8")


def znalezisko(id_="E1", nowy=CYTAT_NOWY, stary=CYTAT_STARY, why="different first reporter and date"):
    return {"findings": [{"id": id_, "new_quote": nowy, "earlier_quote": stary, "why": why}]}


def ocena(werdykt="CONTRADICTION", popiera="EARLIER", n=1, why="cannot both be first"):
    return {"pairs": [{"n": n, "verdict": werdykt, "supported_by": popiera, "why": why}]}


print("=== 1. KANDYDACI Z DZIENNIKA ===")
zapisz_dziennik([
    wpis(WCZESNIEJSZA, 5),                                         # powiazana, w oknie
    wpis(WCZESNIEJSZA + " Old.", 30),                              # poza oknem 21 dni
    wpis(NIEZWIAZANA, 2),                                          # niepowiazana
    wpis(WCZESNIEJSZA + " Restack.", 1, rodzaj="restack"),         # nie notka
    wpis(WCZESNIEJSZA + " Failed.", 1, udane=False),               # nieudana
    wpis(NOWA, 1),                                                 # ta sama tresc co nowa — pomijana
    wpis(WCZESNIEJSZA, 3),                                         # duplikat tresci — raz
    wpis("", 1),                                                   # pusty tekst
], surowe_linie=["to nie jest json", ""])
k = spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)
sprawdz("kandydat: tylko powiazana notka z okna, bez restacka, nieudanej, starej, duplikatu i tej samej tresci",
        len(k) == 1 and k[0]["tekst"] == WCZESNIEJSZA and k[0]["nr"] == "E1", [x["tekst"][:40] for x in k])
sprawdz("brak pliku dziennika = zero kandydatow, bez wyjatku",
        spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ, plik=KATALOG / "nie-ma.jsonl") == [])
zapisz_dziennik([wpis(WCZESNIEJSZA, 5)])
sprawdz("notka z przyszlosci (zly zegar) nie jest kandydatem",
        spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ - timedelta(days=10)) == []
        and len(spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)) == 1)

# prog powiazania: 2 wspolne slowa to za malo, liczba liczy sie za dwa
zapisz_dziennik([wpis("Foundation flaw alone says something else entirely about rabbits and burrows today.", 2)])
sprawdz("dwa wspolne slowa tresci to za malo, zeby byc kandydatem",
        spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ) == [])
zapisz_dziennik([wpis("Foundation flaw reported something else entirely about rabbits and burrows today.", 2)])
sprawdz("dokladnie trzy wspolne slowa tresci to juz kandydat (granica progu z obu stron)",
        len(spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)) == 1)
zapisz_dziennik([wpis("Foundation flaw on 11 something else entirely about rabbits and burrows today.", 2)])
sprawdz("liczba wspolna z tekstem liczy sie za dwa slowa (2 slowa + liczba = 4 >= 3)",
        len(spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)) == 1)

zapisz_dziennik([wpis("Foundation rabbits and burrows on 11 meadows today.", 2)])
sprawdz("jedno wspolne slowo + jedna wspolna liczba = 3: kandydat (liczba liczy sie za DWA slowa)",
        len(spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)) == 1)
zapisz_dziennik([wpis("Foundation flaw on 5 rabbits and burrows today.", 2)])
sprawdz("liczba jednocyfrowa (numeracja) nie liczy sie: 2 slowa + wspolne 5 to nadal 2, za malo",
        spojnosc.wczesniejsze_notki("The Foundation flaw affected 5 servers.", teraz=TERAZ) == [])

# ranking: przy nadmiarze kandydatow zostaja NAJBARDZIEJ powiazani, a nie najnowsi
zapisz_dziennik([wpis("Foundation flaw reported rabbits burrows variant number %d." % i, i) for i in range(1, 15)]
                + [wpis(WCZESNIEJSZA, 16), wpis(WCZESNIEJSZA + " Second angle.", 17), wpis(WCZESNIEJSZA + " Third angle.", 18)])
k = spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)
sprawdz("przy nadmiarze zostaja najbardziej powiazane, nawet starsze od slabych",
        sum(1 for x in k if x["tekst"].startswith("Wiz reported")) == 3 and len(k) == config.SPOJNOSC_KANDYDATOW,
        [x["tekst"][:30] for x in k])

# limit kandydatow i kolejnosc chronologiczna
zapisz_dziennik([wpis("PHP Foundation remote code execution flaw reported variant number %d." % i, i) for i in range(1, 21)])
k = spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)
sprawdz("najwyzej %d kandydatow" % config.SPOJNOSC_KANDYDATOW, len(k) == config.SPOJNOSC_KANDYDATOW, len(k))
sprawdz("od najstarszej do najnowszej, numerowani E1..", [x["nr"] for x in k] == ["E%d" % i for i in range(1, len(k) + 1)]
        and all(k[i]["kiedy"] <= k[i + 1]["kiedy"] for i in range(len(k) - 1)))

zapisz_dziennik([wpis(WCZESNIEJSZA + " Separator\u2028inside\u2029the\u0085note text itself.", 3)])
sprawdz("notka z U+2028/U+2029/U+0085 w tresci nie ginie (dziennik czytany po \\n, nie `splitlines()`)",
        len(spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)) == 1)
dobry = json.dumps(wpis(WCZESNIEJSZA, 3), ensure_ascii=False)
(config.DATA_DIR / "dziennik.jsonl").write_bytes(("\n".join([dobry, "X"]) + "\n").encode("utf-8") + b"\xff\xfe zepsuty wiersz\n" + dobry.encode("utf-8") + b"\n")
try:
    k = spojnosc.wczesniejsze_notki(NOWA, teraz=TERAZ)
    sprawdz("jeden uszkodzony bajt w dzienniku nie wylacza sprawdzenia (czytelne wiersze zostaja kandydatami)", len(k) == 1, len(k))
except Exception as exc:                                        # noqa: BLE001
    sprawdz("jeden uszkodzony bajt w dzienniku nie wylacza sprawdzenia", False, repr(exc))

print()
print("=== 2. CYTAT MUSI STAC W TEKSCIE DOSLOWNIE ===")
Z = "The PHP Foundation reported the flaw first, on 11 August, and “OpenAI” agreed."
sprawdz("doslowny cytat przechodzi", spojnosc._cytat_w_tekscie(Z, "The PHP Foundation reported the flaw first") != "")
sprawdz("wielkosc liter, cudzyslowy i spacje nie psuja dopasowania",
        spojnosc._cytat_w_tekscie(Z, "the  PHP foundation reported the flaw  first, on 11 August, and \"OpenAI\" agreed") != "")
sprawdz("cytat spoza tekstu jest odrzucany", spojnosc._cytat_w_tekscie(Z, "Wiz reported the flaw first, on 19 August") == "")
sprawdz("parafraza jest odrzucana", spojnosc._cytat_w_tekscie(Z, "The Foundation was first to report the flaw") == "")
sprawdz("dwa slowa to za malo", spojnosc._cytat_w_tekscie(Z, "PHP Foundation") == "")
sprawdz("wiecej niz 40 slow to nie cytat", spojnosc._cytat_w_tekscie(" ".join(["slowo"] * 50), " ".join(["slowo"] * 45)) == "")
sprawdz("wielokropek na brzegach nie psuje cytatu", spojnosc._cytat_w_tekscie(Z, "…The PHP Foundation reported the flaw first…") != "")
sprawdz("pusty i None to nie cytat", spojnosc._cytat_w_tekscie(Z, "") == "" and spojnosc._cytat_w_tekscie(Z, None) == "")

print()
print("=== 3. SPRAWDZ: KOLEJNOSC TANICH KROKOW ===")
zapisz_dziennik([wpis(WCZESNIEJSZA, 5), wpis(NIEZWIAZANA, 2)])
CONN = sqlite3.connect(":memory:")

reset()
_stare = config.SPOJNOSC_Z_DZIENNIKIEM
config.SPOJNOSC_Z_DZIENNIKIEM = False
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "kontekst", teraz=TERAZ)
config.SPOJNOSC_Z_DZIENNIKIEM = _stare
sprawdz("przelacznik wylaczony: stan `wylaczone`, ZERO wywolan", w["stan"] == "wylaczone" and cele() == [], (w["stan"], cele()))

reset()
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NIEZWIAZANA + " Plus reflections about naps.", "", teraz=TERAZ,
             plik=KATALOG / "pusty.jsonl")
sprawdz("brak kandydatow: stan `brak_kandydatow`, ZERO wywolan", w["stan"] == "brak_kandydatow" and cele() == [], (w["stan"], cele()))

reset()
w, _ = cicho(spojnosc.sprawdz, CONN, 1, "", "", teraz=TERAZ)
sprawdz("pusty tekst: zero wywolan", cele() == [] and w["stan"] == "wylaczone", (w["stan"], cele()))

reset(spojnosc=[{"findings": []}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "kontekst", teraz=TERAZ)
sprawdz("Flash nic nie wskazal: `czysto`, JEDNO wywolanie, Opus nie zawolany",
        w["stan"] == "czysto" and cele() == ["spojnosc"] and w["kandydatow"] == 1, (w["stan"], cele()))

reset(spojnosc=[znalezisko(nowy="The PHP Foundation was beaten to it by Wiz, in July, which nobody noticed")])
w, log = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "kontekst", teraz=TERAZ)
sprawdz("wymyslony cytat zabija znalezisko PRZED platnym potwierdzeniem (Opus nie zawolany)",
        w["stan"] == "czysto" and cele() == ["spojnosc"] and w["cytaty_odrzucone"] == 1 and w["znalezione"] == 0, (w, cele()))
sprawdz("i log to mowi", "cytat spoza tekstu" in log, log)

reset(spojnosc=[znalezisko(id_="E9")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "kontekst", teraz=TERAZ)
sprawdz("nieistniejace id notki odrzuca znalezisko", w["stan"] == "czysto" and cele() == ["spojnosc"] and w["cytaty_odrzucone"] == 1, w)

reset(spojnosc=[znalezisko(stary="Wiz was second to report the flaw, on 21 August, after the Foundation")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "kontekst", teraz=TERAZ)
sprawdz("wymyslony cytat WCZESNIEJSZEJ notki tez odrzuca", w["stan"] == "czysto" and w["cytaty_odrzucone"] == 1, w)

print()
print("=== 4. SPRAWDZ: ROZSTRZYGNIECIA POTWIERDZENIA ===")
reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")])
w, log = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "EVIDENCE: Foundation advisory dated 11 August", teraz=TERAZ)
sprawdz("sprzecznosc potwierdzona, material popiera wczesniejsza: stan `sprzecznosc`, jedna do naprawy",
        w["stan"] == "sprzecznosc" and len(w["sprzecznosci"]) == 1 and not w["nowa_lepsza"], w)
sprawdz("kolejnosc: Flash, potem Opus", cele() == ["spojnosc", "spojnosc_potwierdz"] and w["potwierdzil"] == "opus", cele())
s = (w["sprzecznosci"] or [{}])[0]
sprawdz("sprzecznosc niesie oba cytaty, numer i date wczesniejszej notki",
        s.get("nowy_cytat") == CYTAT_NOWY and s.get("wczesniejszy_cytat") == CYTAT_STARY
        and s.get("nr") == "E1" and s.get("kiedy") == "2026-10-22", s)
sprawdz("potwierdzenie widzi material, z ktorego powstala notka (nie z pamieci)",
        "Foundation advisory dated 11 August" in WYWOLANIA[1]["prompt"] and CYTAT_STARY in WYWOLANIA[1]["prompt"], WYWOLANIA[1]["prompt"][-600:])
sprawdz("wykrywanie dostaje nowa notke i wczesniejsza z identyfikatorem i data",
        NOWA[:40] in WYWOLANIA[0]["prompt"] and "[E1 | 2026-10-22]" in WYWOLANIA[0]["prompt"], WYWOLANIA[0]["prompt"][-700:])

DRUGA = "Wiz Atlas found the PHP bug before the Foundation had published anything about the flaw."
CYTAT_STARY_2 = "Wiz Atlas found the PHP bug before the Foundation had published anything"
zapisz_dziennik([wpis(WCZESNIEJSZA, 5), wpis(DRUGA, 4)])
dwa = {"findings": [
    {"id": "E1", "new_quote": CYTAT_NOWY, "earlier_quote": CYTAT_STARY, "why": "first"},
    {"id": "E2", "new_quote": CYTAT_NOWY, "earlier_quote": CYTAT_STARY_2, "why": "second"}]}
reset(spojnosc=[dwa], spojnosc_potwierdz=[{"pairs": [
    {"n": 1, "verdict": "CONSISTENT", "supported_by": "NEITHER", "why": "ok"},
    {"n": 2, "verdict": "CONTRADICTION", "supported_by": "EARLIER", "why": "clash"}]}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("dwie pary o roznych werdyktach: sprzecznoscia jest TA, ktora ocena wskazala (numer pary, nie kolejnosc)",
        len(w["sprzecznosci"]) == 1 and w["sprzecznosci"][0]["wczesniejszy_cytat"] == CYTAT_STARY_2
        and w["sprzecznosci"][0]["nr"] == "E2", w)
zapisz_dziennik([wpis(WCZESNIEJSZA, 5), wpis(NIEZWIAZANA, 2)])

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("UPDATE", "NEW")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("aktualizacja to nie sprzecznosc: `czysto`, nic do naprawy", w["stan"] == "czysto" and not w["sprzecznosci"] and not w["nowa_lepsza"], w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONSISTENT", "NEITHER")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("zgodnosc to nie sprzecznosc", w["stan"] == "czysto" and not w["sprzecznosci"], w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "NEW")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("sprzecznosc, ale material popiera NOWA notke: `nowa_lepsza`, NIC do naprawy (nie przepisujemy wbrew zrodlom)",
        w["stan"] == "nowa_lepsza" and not w["sprzecznosci"] and len(w["nowa_lepsza"]) == 1, w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "NEITHER")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("sprzecznosc, materialu nie rozstrzyga: idzie do naprawy w strone tego, co juz opublikowane",
        w["stan"] == "sprzecznosc" and len(w["sprzecznosci"]) == 1, w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[{"pairs": [{"n": 7, "verdict": "CONTRADICTION", "supported_by": "EARLIER"}]}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("potwierdzenie bez oceny tej pary (zly numer), a zapas tez zawodzi: `nie_sprawdzone`, NIE `czysto`",
        w["stan"] == "nie_sprawdzone" and not w["sprzecznosci"], w)

for opis, zla in (("pusty obiekt", {}), ("pusta lista par", {"pairs": []}), ("inny klucz", {"verdicts": [{"n": 1, "verdict": "CONTRADICTION"}]}),
                  ("wpis bez numeru", {"pairs": [{"verdict": "CONTRADICTION", "supported_by": "EARLIER"}]}),
                  ("numeracja od zera", {"pairs": [{"n": 0, "verdict": "CONTRADICTION", "supported_by": "EARLIER"}]}),
                  ("werdykt spoza listy", {"pairs": [{"n": 1, "verdict": "MAYBE", "supported_by": "EARLIER"}]}),
                  ("werdykt to szablon z promptu", {"pairs": [{"n": 1, "verdict": "CONTRADICTION|UPDATE|CONSISTENT"}]}),
                  ("pary nie sa lista", {"pairs": "CONTRADICTION"})):
    reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[zla], spojnosc_potwierdz_zapas=[ocena("CONTRADICTION", "EARLIER")])
    w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
    sprawdz("odpowiedz Opusa bezuzyteczna (%s): zapas wydaje ocene, nie `czysto`" % opis,
            w["stan"] == "sprzecznosc" and w["potwierdzil"] == "zapas", (w["stan"], w["potwierdzil"]))
    reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[zla], spojnosc_potwierdz_zapas=[zla])
    w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
    sprawdz("oba potwierdzenia bezuzyteczne (%s): `nie_sprawdzone`" % opis, w["stan"] == "nie_sprawdzone", (w["stan"], w["potwierdzil"]))

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[{"pairs": [{"n": "1.", "verdict": "contradiction", "supported_by": "earlier"}]}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("numer pary jako tekst „1.” i male litery sa czytelne — bez zapasu", w["stan"] == "sprzecznosc" and w["potwierdzil"] == "opus", w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[{"pairs": [{"n": 1, "verdict": "CONTRADICTION", "supported_by": "tak"}]}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("nieznane `supported_by` to NEITHER (naprawa w strone wczesniejszej), nie blad",
        w["stan"] == "sprzecznosc" and w["sprzecznosci"][0]["popiera"] == "NEITHER", w)

for opis, zla in (("pusty obiekt", {}), ("inny klucz", {"results": [{"id": "E1"}]}), ("lista zamiast obiektu", [1, 2]),
                  ("findings nie jest lista", {"findings": "none"})):
    reset(spojnosc=[zla])
    w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
    sprawdz("wykrywanie bez listy `findings` (%s): `nie_sprawdzone`, NIE `czysto`" % opis, w["stan"] == "nie_sprawdzone", w)
reset(spojnosc=[{"findings": []}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("pusta lista `findings` to uczciwe „nic nie ma”: `czysto`", w["stan"] == "czysto", w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("contradiction", "earlier")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("wielkosc liter w werdykcie nie ma znaczenia", w["stan"] == "sprzecznosc", w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("MAYBE", "EARLIER")], spojnosc_potwierdz_zapas=[ocena("UPDATE", "NEW")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("nieznany werdykt NIE jest potwierdzeniem: ocene wydaje zapas", w["stan"] == "czysto" and w["potwierdzil"] == "zapas", w)

NOWE_5 = ["The PHP Foundation reported the remote code execution flaw first", "OpenAI independently reported the same root cause",
          "Labs now compete on reputation", "credit is the prize in every advisory", "reported the remote code execution flaw first, on 11 August"]
STARE_5 = ["Wiz reported the remote code execution flaw in PHP first", "using Wiz Atlas", "on 19 August, using Wiz Atlas",
           "nobody else had found the same root cause", "found the same root cause by then"]
piec = {"findings": [{"id": "E1", "new_quote": n, "earlier_quote": s, "why": "w%d" % i} for i, (n, s) in enumerate(zip(NOWE_5, STARE_5))]}
reset(spojnosc=[piec],
      spojnosc_potwierdz=[{"pairs": [{"n": i, "verdict": "CONSISTENT", "supported_by": "NEITHER"} for i in range(1, 4)]}])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("do potwierdzenia idzie najwyzej %d par, choc Flash wskazal piec" % config.SPOJNOSC_MAKS_PAR,
        w["znalezione"] == config.SPOJNOSC_MAKS_PAR and "PAIR 3" in WYWOLANIA[1]["prompt"]
        and "PAIR 4" not in WYWOLANIA[1]["prompt"], (w["znalezione"], WYWOLANIA[1]["prompt"][-500:]))

reset(spojnosc=[{"findings": znalezisko()["findings"] * 3}], spojnosc_potwierdz=[ocena("CONSISTENT", "NEITHER")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("ta sama para powtorzona trzy razy to JEDNA para (nie zjada miejsca innym) i nie liczy sie jako odrzucona",
        w["znalezione"] == 1 and w["cytaty_odrzucone"] == 0 and "PAIR 2" not in WYWOLANIA[1]["prompt"], (w, WYWOLANIA[1]["prompt"][-300:]))

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONSISTENT", "NEITHER")])
cicho(spojnosc.sprawdz, CONN, 1, NOWA, "A" * 6100 + "ZZOGON", teraz=TERAZ)
sprawdz("material dla potwierdzenia jest obciety do 6000 znakow (koszt jest ograniczony)",
        "ZZOGON" not in WYWOLANIA[1]["prompt"] and "A" * 6000 in WYWOLANIA[1]["prompt"] and "A" * 6001 not in WYWOLANIA[1]["prompt"])

reset(spojnosc=[znalezisko(why="REASON-OF-THE-FIRST-READER")], spojnosc_potwierdz=[ocena("CONSISTENT", "NEITHER")])
cicho(spojnosc.sprawdz, CONN, 1, NOWA, "DOWOD-TRESC", teraz=TERAZ)
pot = WYWOLANIA[1]["prompt"]
sprawdz("Opus dostaje PELNE obie notki, nie tylko cytaty",
        WCZESNIEJSZA in pot and NOWA in pot and "using Wiz Atlas" in pot, pot[-1500:])
sprawdz("Opus NIE dostaje uzasadnienia pierwszego czytelnika (zakotwiczenie), ale dostaje dzisiejsza date",
        "REASON-OF-THE-FIRST-READER" not in pot and "Today is 2026-10-27" in pot
        and "Today is 2026-10-27" in WYWOLANIA[0]["prompt"], pot[:300])

print()
print("=== 5. ZAPAS PRZY ODMOWIE OPUSA I GRANICA „NIE SPRAWDZILEM” ===")
reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[llm.OdmowaDostawcy("cyber")],
      spojnosc_potwierdz_zapas=[ocena("CONTRADICTION", "EARLIER")])
w, log = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("Opus odmawia (klasyfikator „cyber”): potwierdza Flash z myslenie, wynik ten sam",
        w["stan"] == "sprzecznosc" and w["potwierdzil"] == "zapas"
        and cele() == ["spojnosc", "spojnosc_potwierdz", "spojnosc_potwierdz_zapas"], (w["stan"], cele()))

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[llm.OdmowaDostawcy("cyber")], spojnosc_potwierdz_zapas=[ocena("CONSISTENT", "NEITHER")])
cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
WYWOLANIA.clear()
cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("po odmowie Opusa NASTEPNE potwierdzenie w tym przebiegu idzie od razu do zapasu (bez drugiej, skazanej proby)",
        cele() == ["spojnosc", "spojnosc_potwierdz_zapas"] and spojnosc._OPUS_ODMOWIL is True, cele())
reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[RuntimeError("timeout")], spojnosc_potwierdz_zapas=[ocena("CONSISTENT", "NEITHER")])
cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("zwykla awaria Opusa (nie odmowa) NIE wylacza go na reszte przebiegu", spojnosc._OPUS_ODMOWIL is False)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=["to nie jest json"], spojnosc_potwierdz_zapas=[ocena("CONSISTENT", "NEITHER")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("zly JSON od Opusa tez idzie do zapasu", w["potwierdzil"] == "zapas" and w["stan"] == "czysto", w)

reset(spojnosc=[znalezisko()], spojnosc_potwierdz=[RuntimeError("padl")], spojnosc_potwierdz_zapas=[RuntimeError("tez padl")])
w, log = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("padly oba potwierdzenia: `nie_sprawdzone`, NIGDY `czysto`, bez wyjatku, bez sprzecznosci",
        w["stan"] == "nie_sprawdzone" and not w["sprzecznosci"], w)

reset(spojnosc=[RuntimeError("dostawca padl")])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("padl Flash: `nie_sprawdzone`", w["stan"] == "nie_sprawdzone" and cele() == ["spojnosc"], (w["stan"], cele()))

reset(spojnosc=["to nie jest json"])
w, _ = cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
sprawdz("Flash oddal smieci: `nie_sprawdzone`, nie `czysto`", w["stan"] == "nie_sprawdzone", w)

for nazwa, wyjatek in (("BudgetExceeded", llm.BudgetExceeded("sufit")), ("PreflightFailed", llm.PreflightFailed("kill"))):
    for gdzie in ("spojnosc", "spojnosc_potwierdz"):
        reset(spojnosc=[znalezisko()] if gdzie != "spojnosc" else [wyjatek],
              spojnosc_potwierdz=[wyjatek], spojnosc_potwierdz_zapas=[ocena()])
        try:
            cicho(spojnosc.sprawdz, CONN, 1, NOWA, "", teraz=TERAZ)
            sprawdz("%s w `%s` leci na wylot" % (nazwa, gdzie), False, "zjedzony")
        except (llm.BudgetExceeded, llm.PreflightFailed):
            sprawdz("%s w `%s` leci na wylot (stan konta, nie awaria jednego wywolania)" % (nazwa, gdzie), True)

print()
print("=== 6. ZARZUT DLA NAPRAWY I ZAPIS DO DZIENNIKA ===")
sp = {"stan": "sprzecznosc", "kandydatow": 3, "znalezione": 2,
      "sprzecznosci": [{"nr": "E1", "kiedy": "2026-10-22", "nowy_cytat": CYTAT_NOWY, "wczesniejszy_cytat": CYTAT_STARY, "dlaczego": "x"}],
      "nowa_lepsza": [], "naprawiona": True, "potwierdzil": "opus"}
zarzuty = spojnosc.jako_zarzuty(sp["sprzecznosci"])
sprawdz("sprzecznosc to zarzut `refuted` z cytatem nowej strony jako twierdzeniem",
        len(zarzuty) == 1 and stages._status_twierdzenia(zarzuty[0]) == "refuted" and zarzuty[0]["claim"] == CYTAT_NOWY, zarzuty)
sprawdz("material naprawy to wlasna notka, z data i cytatem",
        CYTAT_STARY in zarzuty[0]["what_the_source_says"] and "2026-10-22" in zarzuty[0]["what_the_source_says"], zarzuty)
sk = spojnosc.skrot(sp)
sprawdz("skrot do dziennika: liczby i znaczniki",
        {k: v for k, v in sk.items() if k != "szczegoly"} == {
            "stan": "sprzecznosc", "kandydatow": 3, "znalezione": 2, "sprzecznosci": 1, "nowa_lepsza": 0,
            "naprawiona": True, "stoi": False, "naprawa_odrzucona": False, "powod_odrzucenia": "", "potwierdzil": "opus"}, sk)
sprawdz("skrot niesie krotkie cytaty, zeby dalo sie przeczytac, CO sie zderzylo (a nie tylko ile razy)",
        sk["szczegoly"] == [{"rodzaj": "sprzecznosc", "kiedy": "2026-10-22", "popiera": "", "nowy": CYTAT_NOWY, "wczesniejszy": CYTAT_STARY}], sk)
sp2 = dict(sp, sprzecznosci=[], nowa_lepsza=sp["sprzecznosci"] * 5)
sprawdz("szczegolow najwyzej trzy, rodzaj `nowa_lepsza` rozpoznawalny, cytat ucinany do 160 znakow",
        len(spojnosc.skrot(sp2)["szczegoly"]) == 3 and spojnosc.skrot(sp2)["szczegoly"][0]["rodzaj"] == "nowa_lepsza"
        and len(spojnosc.skrot(dict(sp, sprzecznosci=[dict(sp["sprzecznosci"][0], nowy_cytat="x" * 500)]))["szczegoly"][0]["nowy"]) == 160)
sprawdz("bez znalezisk nie ma klucza `szczegoly`", "szczegoly" not in spojnosc.skrot(dict(sp, sprzecznosci=[], nowa_lepsza=[])))
sprawdz("skrot pustego wpisu nie rzuca", spojnosc.skrot({})["stan"] == "" and spojnosc.skrot({})["sprzecznosci"] == 0)

print()
print("=== 7. stages.note(sprawdz_spojnosc=True): TA SAMA NAPRAWA CO DLA FAKTU ===")
conn = db.connect()
rid = db.start_run(conn, "test-spojnosc", tryb="test")
DOWOD = {"fact": "The PHP Foundation advisory dates the report to 11 August.", "url": "https://s1.example/x",
         "source_date": "2026-10-25", "actually": "", "decision": "", "consequence": "", "wrong_belief": ""}
SWIEZY = datetime.now(timezone.utc)
POPRAWIONA = ("Wiz reported the remote code execution flaw in PHP first, on 19 August, using Wiz Atlas. "
              "The PHP Foundation says its own report came from a Calif researcher, and that OpenAI "
              "independently reported the same root cause. Labs now compete on reputation, and credit is the prize "
              "in every advisory they publish for the world.")
# Kosmetyka: zdanie z cytatem nowej strony zostaje w tekscie, wiec ponowne sprawdzenie WIDZI sprzecznosc.
POPRAWKA_KOSMETYCZNA = NOWA.replace("independently", "separately")
FAKT_CZYSTO = {"claims": [{"claim": "x", "status": "confirmed"}]}
FAKT_OBALONY = {"claims": [{"claim": "OpenAI reported the root cause in 2024.", "status": "refuted",
                            "what_the_source_says": "The record says OpenAI reported it in 2026."}]}


def zapisz_swiezy_dziennik():
    wpisy = [{"kiedy": (SWIEZY - timedelta(days=5)).isoformat(), "rodzaj": "notka", "udane": True, "tekst": WCZESNIEJSZA}]
    (config.DATA_DIR / "dziennik.jsonl").write_text("\n".join(json.dumps(w) for w in wpisy) + "\n", encoding="utf-8")


def notka(nr, flaga=True, tekst=NOWA, typ="CIEKAWOSTKA", **kw):
    stages._NAPRAW_ZUZYTE.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        wynik = stages.note(conn, rid + nr, typ, DOWOD, etap="notka_przeslania_fakt", bez_rozbioru=True,
                            gotowy_tekst=tekst, sprawdz_spojnosc=flaga, **kw)
    return (wynik.get("candidates") or [{}])[0]


zapisz_swiezy_dziennik()
reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWIONA, "co_zmienione": "aligned with Wiz 19 August"}])
kand = notka(1)
fc = stages.skrot_weryfikacji(kand)
sprawdz("kolejnosc platnych krokow: fakty w sieci, spojnosc, potwierdzenie, naprawa, PONOWNE fakty, PONOWNA spojnosc",
        cele() == ["factcheck", "spojnosc", "spojnosc_potwierdz", "naprawa", "factcheck", "spojnosc"], cele())
reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko(), {"findings": []}],
      spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWIONA, "co_zmienione": "aligned with Wiz 19 August"}])
kand = notka(2)
fc = stages.skrot_weryfikacji(kand)
sprawdz("przez `note` do potwierdzenia idzie REKORD, z ktorego notka powstala (nie pusty kontekst)",
        any(w["purpose"] == "spojnosc_potwierdz" and "The PHP Foundation advisory dates the report to 11 August" in w["prompt"]
            for w in WYWOLANIA), [w["prompt"][:300] for w in WYWOLANIA if w["purpose"] == "spojnosc_potwierdz"])
sprawdz("sprzecznosc potwierdzona i naprawiona: wychodzi tekst POPRAWIONY",
        kand.get("note") == POPRAWIONA and kand.get("tekst_przed_naprawa") == NOWA, kand.get("note"))
DATA_WCZESNIEJSZEJ = (SWIEZY - timedelta(days=5)).strftime("%Y-%m-%d")
sprawdz("naprawa dostala jako material nasza wlasna notke, z data i cytatem",
        any(w["purpose"] == "naprawa" and CYTAT_STARY in w["prompt"] and DATA_WCZESNIEJSZEJ in w["prompt"] for w in WYWOLANIA),
        [w["prompt"][-900:] for w in WYWOLANIA if w["purpose"] == "naprawa"])
sprawdz("zapis: naprawiona = prawda, nie stoi, nie odrzucona",
        kand["spojnosc"]["naprawiona"] is True and not kand["spojnosc"].get("stoi")
        and not kand["spojnosc"].get("naprawa_odrzucona"), kand["spojnosc"])
sprawdz("`fc.obalonych` zostaje miara FAKTOW z sieci, a `fc.naprawiona` nie liczy naprawy SAMEJ sprzecznosci "
        "(`co_dziala` liczy „naprawionych” jako podzbior „z obalonym”); naprawa sprzecznosci ma wlasne pole",
        fc["obalonych"] == 0 and fc["naprawiona"] is False and fc["spojnosc"]["naprawiona"] is True
        and fc["spojnosc"]["sprzecznosci"] == 1, fc)
pot = [w["prompt"] for w in WYWOLANIA if w["purpose"] == "spojnosc_potwierdz"][0]
sprawdz("potwierdzenie dostaje tez to, co siec powiedziala o nowej notce przed chwila — NA POCZATKU materialu",
        "WEB FACT-CHECK OF THE NEW NOTE" in pot and "- [confirmed] x" in pot
        and pot.index("WEB FACT-CHECK OF THE NEW NOTE") < pot.index("The PHP Foundation advisory dates the report"), pot[:900])

reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko(), znalezisko()],
      spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWKA_KOSMETYCZNA, "co_zmienione": "x"}])
kand = notka(3)
fc = stages.skrot_weryfikacji(kand)
sprawdz("naprawa NIE usunela sprzecznosci, a nie poprawiala faktu z sieci: ODRZUCONA, zostaje oryginal",
        kand.get("note") == NOWA and "tekst_przed_naprawa" not in kand and kand["spojnosc"]["naprawa_odrzucona"] is True
        and kand["spojnosc"]["stoi"] is True, (kand.get("note"), kand["spojnosc"]))
sprawdz("a notka i tak idzie (nic nie blokuje), powod odrzucenia to dziennik",
        kand.get("safe_to_post") is True and kand["spojnosc"]["powod_odrzucenia"] == "dziennik", kand["spojnosc"])
sprawdz("zapis niesie, ze sprzecznosc stoi", fc["spojnosc"]["stoi"] is True and fc["spojnosc"]["naprawa_odrzucona"] is True, fc)

reset(factcheck=[FAKT_OBALONY, FAKT_CZYSTO], spojnosc=[znalezisko(), znalezisko()],
      spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWKA_KOSMETYCZNA, "co_zmienione": "x"}])
kand = notka(4)
fc = stages.skrot_weryfikacji(kand)
sprawdz("gdy naprawa poprawia tez OBALONY FAKT z sieci, zostaje nawet przy stojacej sprzecznosci",
        kand.get("note") == POPRAWKA_KOSMETYCZNA and kand["spojnosc"]["stoi"] is True
        and not kand["spojnosc"].get("naprawa_odrzucona"),
        (kand.get("note"), kand["spojnosc"]))
sprawdz("`fc.obalonych` liczy tu JEDEN fakt z sieci, bez sprzecznosci, a naprawa faktu jest `naprawiona`",
        fc["obalonych"] == 1 and fc["naprawiona"] is True, fc)
sprawdz("naprawa dostala OBA zarzuty w jednym wywolaniu (jedna proba, nie dwie)",
        cele().count("naprawa") == 1 and "OpenAI reported the root cause in 2024" in
        [w for w in WYWOLANIA if w["purpose"] == "naprawa"][0]["prompt"]
        and CYTAT_STARY in [w for w in WYWOLANIA if w["purpose"] == "naprawa"][0]["prompt"], cele())

reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko(), RuntimeError("padl przy ponownym")],
      spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWIONA, "co_zmienione": "x"}])
kand = notka(13)
sprawdz("ponowne sprawdzenie naprawy nie doszlo do skutku: naprawa zostaje, ale NIE jest zapisana jako sprawdzona",
        kand.get("note") == POPRAWIONA and kand["spojnosc"]["naprawiona"] is False and not kand["spojnosc"].get("stoi"),
        kand["spojnosc"])

reset(factcheck=[FAKT_CZYSTO, FAKT_OBALONY], spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": POPRAWIONA, "co_zmienione": "x"}])
kand = notka(14)
fc = stages.skrot_weryfikacji(kand)
sprawdz("TEKST CZYSTY W SIECI NIE ZOSTAJE ZAMIENIONY NA OBALONY: siec obala naprawe samej sprzecznosci -> wychodzi oryginal",
        kand.get("note") == NOWA and "tekst_przed_naprawa" not in kand and kand["spojnosc"]["naprawa_odrzucona"] is True
        and kand["spojnosc"]["powod_odrzucenia"] == "siec" and kand["spojnosc"]["stoi"] is True,
        (kand.get("note"), kand["spojnosc"]))
sprawdz("...bez zbednej ponownej spojnosci (tekst i tak odrzucony) i bez blokowania publikacji",
        cele() == ["factcheck", "spojnosc", "spojnosc_potwierdz", "naprawa", "factcheck"] and kand.get("safe_to_post") is True, cele())
sprawdz("...a zapis niesie powod", fc["spojnosc"]["powod_odrzucenia"] == "siec" and fc["spojnosc"]["naprawa_odrzucona"] is True, fc)

reset(factcheck=[FAKT_CZYSTO, RuntimeError("siec padla")], spojnosc=[znalezisko()],
      spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")], naprawa=[{"text": POPRAWIONA, "co_zmienione": "x"}])
kand = notka(15)
sprawdz("siec nie dala rady sprawdzic naprawy sprzecznosci: tez oryginal (oryginal NIE jest „falszywy na pewno”)",
        kand.get("note") == NOWA and kand["spojnosc"]["naprawa_odrzucona"] is True
        and kand["spojnosc"]["powod_odrzucenia"] == "siec_nie_sprawdzona", (kand.get("note"), kand["spojnosc"]))

reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")],
      naprawa=[{"text": NOWA, "co_zmienione": "nic"}])
kand = notka(5)
sprawdz("model naprawy nie zmienil tekstu: oryginal, sprzecznosc `stoi`, bez ponownej spojnosci (nie bylo czego sprawdzac)",
        kand.get("note") == NOWA and kand["spojnosc"]["stoi"] is True and cele().count("spojnosc") == 1, (cele(), kand["spojnosc"]))

_stare_n = config.NAPRAWA_OBALONYCH
config.NAPRAWA_OBALONYCH = False
reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "EARLIER")])
kand = notka(6)
config.NAPRAWA_OBALONYCH = _stare_n
sprawdz("naprawa wylaczona w konfiguracji: tekst bez zmian, sprzecznosc `stoi` w zapisie, zero wywolan naprawy",
        kand.get("note") == NOWA and kand["spojnosc"]["stoi"] is True and "naprawa" not in cele(), (cele(), kand["spojnosc"]))

reset(factcheck=[FAKT_CZYSTO], spojnosc=[znalezisko()], spojnosc_potwierdz=[ocena("CONTRADICTION", "NEW")])
kand = notka(7)
sprawdz("material popiera nowa notke: bez naprawy, tekst nietkniety, zapis `nowa_lepsza`",
        kand.get("note") == NOWA and "naprawa" not in cele() and kand["spojnosc"]["stan"] == "nowa_lepsza"
        and not kand["spojnosc"].get("stoi"), (cele(), kand["spojnosc"]))

reset(factcheck=[FAKT_CZYSTO], spojnosc=[{"findings": []}])
kand = notka(8)
fc = stages.skrot_weryfikacji(kand)
sprawdz("czysto: tekst bez zmian, zapis `czysto`, kolejnosc fakty -> spojnosc",
        kand.get("note") == NOWA and cele() == ["factcheck", "spojnosc"] and fc["spojnosc"]["stan"] == "czysto", (cele(), fc))

reset(factcheck=[FAKT_CZYSTO])
kand = notka(9, flaga=False)
fc = stages.skrot_weryfikacji(kand)
sprawdz("BEZ FLAGI zero wywolan spojnosci i zadnego sladu w zapisie (notki spoza serii dzialaja jak dotad)",
        cele() == ["factcheck"] and "spojnosc" not in kand and "spojnosc" not in fc, (cele(), fc))

reset(factcheck=[FAKT_CZYSTO])
kand = notka(10, typ="MYSL")
sprawdz("MYSL nie dostaje sprawdzenia spojnosci nawet z flaga (nie stoi na fakcie)",
        "spojnosc" not in cele() and "spojnosc" not in kand, cele())

reset(factcheck=[FAKT_CZYSTO], spojnosc=[RuntimeError("padl")])
kand = notka(11)
sprawdz("padla spojnosc: notka wychodzi niezmieniona, zapis `nie_sprawdzone`",
        kand.get("note") == NOWA and kand["spojnosc"]["stan"] == "nie_sprawdzone" and kand.get("safe_to_post") is True, (kand.get("note"), kand.get("spojnosc")))

reset(factcheck=[FAKT_CZYSTO], spojnosc=[llm.BudgetExceeded("sufit przebiegu")])
try:
    notka(12)
    sprawdz("wyczerpany budzet w spojnosci przerywa notke (nie udaje czystej)", False, "zjedzone")
except llm.BudgetExceeded:
    sprawdz("wyczerpany budzet w spojnosci przerywa notke (nie udaje czystej)", True)

print()
print("=== 8. WPIECIE W PRZEBIEG ===")
zrodlo = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("`notki_dnia` wlacza spojnosc dla notek z przeslania (seria, rozkmina)",
        '_bramki = {"bez_rozbioru": True, "sprawdz_spojnosc": True}' in zrodlo)
sprawdz("MYSL i zwykle notki z banku NIE dostaja flagi",
        zrodlo.count('"sprawdz_spojnosc": True') == 1)
for cel in ("spojnosc", "spojnosc_potwierdz", "spojnosc_potwierdz_zapas"):
    sprawdz("cel `%s` ma model i sufit w konfiguracji" % cel, cel in config.MODEL_FOR and cel in config.MAX_TOKENS)
sprawdz("potwierdzenie na Claude, zapas i wykrywanie na Flashu",
        config.MODEL_FOR["spojnosc_potwierdz"] == config.CLAUDE
        and config.MODEL_FOR["spojnosc"] == config.MODEL_FOR["spojnosc_potwierdz_zapas"] == config.DEEPSEEK)
for nazwa in ("spojnosc.md", "spojnosc_potwierdz.md"):
    sprawdz("prompt %s renderuje sie z polami" % nazwa,
            len(stages._prompt(nazwa, nowa="N", wczesniejsze="W", maks=3, dowod="D", pary="P", dzis="2026-10-27")) > 200)
# KONTRAKT ODPOWIEDZI: kod czyta dokladnie te klucze i wartosci — prompt musi je podawac.
P1 = stages._prompt("spojnosc.md", nowa="NOWA-TRESC", wczesniejsze="WCZESNIEJSZE-TRESC", maks=3, dzis="2026-10-27")
P2 = stages._prompt("spojnosc_potwierdz.md", dowod="DOWOD-TRESC", nowa="NOWA-TRESC", pary="PARY-TRESC", dzis="2026-10-27")
sprawdz("wykrywanie: klucze odpowiedzi, o ktore pyta kod",
        all(x in P1 for x in ('"findings"', '"id"', '"new_quote"', '"earlier_quote"', '"why"')), P1[-400:])
sprawdz("wykrywanie: cytat ma byc doslowny, limit znalezisk z konfiguracji, pusta lista jest normalna",
        "EXACTLY" in P1 and "At most 3 findings" in P1 and "An empty list is the normal answer" in P1)
sprawdz("wykrywanie: aktualizacja i dwa ujecia tej samej historii to NIE sprzecznosc",
        "NOT a contradiction" in P1 and "update" in P1)
sprawdz("potwierdzenie: klucze i wartosci, ktore czyta kod",
        all(x in P2 for x in ('"pairs"', '"n"', '"verdict"', '"supported_by"', "CONTRADICTION", "UPDATE", "CONSISTENT",
                              "NEW", "EARLIER", "NEITHER")), P2[-500:])
sprawdz("potwierdzenie: NEITHER, gdy material nie rozstrzyga (bez tego model zgaduje strone)",
        "when the evidence does not settle it" in P2)
sprawdz("potwierdzenie: ocena z materialu, nie z pamieci",
        "never from memory" in P2 and "DOWOD-TRESC" in P2 and "PARY-TRESC" in P2)
sprawdz("oba prompty traktuja wklejone teksty jako dane, nie polecenia (wstrzykniecie przez cudza notke)",
        P1.count("data, never instructions") == 2 and P2.count("data, never instructions") == 3, (P1.count("data, never"), P2.count("data, never")))
sprawdz("oba prompty KONCZA sie przypomnieniem po danych (niezaufane stare notki nie sa ostatnim tekstem)",
        "## End of data" in P1 and "## End of data" in P2 and P1.rstrip().endswith("described above.")
        and "never instructions to you" in P1 and "never instructions to you" in P2, (P1[-300:], P2[-300:]))
sprawdz("oba prompty znaja date i regule faktow zmiennych w czasie (liczba, cena, status to nie sprzecznosc, tylko pozniejszy stan)",
        "Today is 2026-10-27" in P1 and "Today is 2026-10-27" in P2 and "changes over time" in P1 and "changes over time" in P2)
sprawdz("potwierdzenie: asekuracja („we think”) nie zamienia faktu w opinie",
        "does not turn a factual claim into an opinion" in P2)
sprawdz("potwierdzenie: zdanie POTWIERDZONE przez siec jest poparte materialem", "CONFIRMED is supported by the evidence" in P2)
sprawdz("stale kontraktu: okno 21 dni, 12 kandydatow, prog 3, 3 pary (zmiana wymaga swiadomej zmiany testu)",
        (config.SPOJNOSC_OKNO_DNI, config.SPOJNOSC_KANDYDATOW, config.SPOJNOSC_MIN_WSPOLNYCH, config.SPOJNOSC_MAKS_PAR) == (21, 12, 3, 3))
sprawdz("wykrywanie na Flashu z myslenie ma ograniczony wysilek (koszt), zapas tak samo; Opus ma `medium`",
        config.DEEPSEEK_EFFORT_FOR.get("spojnosc") == "low" and config.DEEPSEEK_EFFORT_FOR.get("spojnosc_potwierdz_zapas") == "low"
        and config.EFFORT.get("spojnosc_potwierdz") == "medium")

llm.call = _prawdziwy_call
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
