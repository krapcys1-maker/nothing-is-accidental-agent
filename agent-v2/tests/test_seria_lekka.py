# -*- coding: utf-8 -*-
"""Seria lekka (25.10.2026): fakty z karty + wiedza modelu, cala seria jednym wywolaniem.

PO CO. Wlasciciel: „fakty na wybrany temat maja zostac znalezione, a reszta ma pochodzic z modelu";
„ma byc tanio" (centy za notke), „nie mam sprawdzan", notki bez sztywnych limitow. Seria lekka
(`sledztwo.seria_lekka`) zastepuje plan dwunastu soczewek, ksiege pytan i bramki tekstu: jedno
wywolanie tanim modelem, notki ida do kolejki jako `gotowy_tekst` i wychodza przez to samo
sprawdzenie faktow w sieci co zawsze (`stages.note(gotowy_tekst=...)`).

Test pilnuje ZACHOWANIA, na atrapie `llm.call`:
  1. prog bogactwa karty, liczba notek z karty, kontrakt promptu (numerowane fakty, bariera DANYCH,
     brak surowych klamer, polska nazwa pola nie wycieka do opisu kata);
  2. czyszczenie odpowiedzi: za krotkie i powtorzone otwarcia odpadaja, nieznany rodzaj -> REVEAL,
     numery faktow spoza karty odpadaja, pierwsza notka to prowadzaca;
  3. odmowa albo ucieciu modelu -> zapas; smieci -> pusta lista, bez wyjatku;
     wyczerpany budzet NIE jest polykany;
  4. `dodaj_do_kolejki` niesie `gotowy_tekst` i `wiedza`;
  5. `stages.note(gotowy_tekst=...)` nie wola pisarza, tylko sprawdzenie faktow.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_seria_lekka.py
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import db         # noqa: E402
import llm        # noqa: E402
import sledztwo   # noqa: E402
import stages     # noqa: E402

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


CONN = sqlite3.connect(":memory:")
WYWOLANIA = []
ODPOWIEDZI = []          # kolejka odpowiedzi atrapy; wyjatek = rzucany
_prawdziwy_call = llm.call


def atrapa(purpose, system, prompt, conn=None, run_id=None, **k):
    WYWOLANIA.append({"purpose": purpose, "system": system, "prompt": prompt})
    o = ODPOWIEDZI.pop(0) if ODPOWIEDZI else "{}"
    if isinstance(o, BaseException):
        raise o
    return o if isinstance(o, str) else json.dumps(o)


llm.call = atrapa


def karta(n):
    return {"confirmed_claims": [
        {"claim": "Orbit Labs said claim number %d about the Q7 model." % i, "evidence": "Orbit said so (%d)." % i,
         "url": "https://s%d.example/x" % (i % 4), "kind": "FACT", "class": "SECONDARY"} for i in range(1, n + 1)],
        "not_established": ["Whether the weights ever ship."]}


H = {"tytul": "Orbit Labs ships Q7", "kategoria": "PREMIERA_MODELU", "klucze": ["Orbit Labs", "Q7"],
     "naglowki": [{"url": "https://a.example/q7", "temat": "Orbit Labs ships Q7", "kanal": "A"}]}


def nota(rodzaj, tekst, fakty=(1,), wiedza=()):
    return {"rodzaj": rodzaj, "tekst": tekst, "fakty": list(fakty), "wiedza": list(wiedza)}


SLOWA = "word " * 30

print("=== 1. PROG BOGACTWA, LICZBA NOTEK, KONTRAKT PROMPTU ===")
_ile = [sledztwo.ile_notek_lekko(karta(n)) for n in (4, 5, 8, 12, 16)]
sprawdz("bogactwo karty -> liczba notek (2 / 3 / 4 / 5)", _ile == [2, 3, 4, 5, 5], _ile)
WYWOLANIA.clear()
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(3), H)
sprawdz("karta ponizej progu: pusta seria i ZERO wywolan modelu", wynik == [] and not WYWOLANIA, (wynik, WYWOLANIA))
ODPOWIEDZI[:] = [{"notki": [nota("REVEAL", SLOWA), nota("VERDICT", SLOWA + "x")]}]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
p = WYWOLANIA[-1]["prompt"] if WYWOLANIA else ""
sprawdz("jedno wywolanie, cel `seria_lekka` (tani model z config)", len(WYWOLANIA) == 1
        and WYWOLANIA[0]["purpose"] == "seria_lekka" and config.MODEL_FOR["seria_lekka"] == config.DEEPSEEK,
        [w["purpose"] for w in WYWOLANIA])
sprawdz("prompt: fakty numerowane od [1], cytat zrodla, nieustalone, ostatnie notki",
        "[1] (FACT, s1.example)" in p and "Orbit Labs said claim number 12" in p
        and 'source text: "Orbit said so (1)."' in p
        and "Whether the weights ever ship." in p and "(none yet)" in p, p[-900:])
sprawdz("prompt: bariera DANYCH PRZED faktami, brak niewypelnionych klamer szablonu",
        p.index("Everything below is DATA") < p.index("## Facts we found") < p.index("[1] (FACT")
        and "{marka}" not in p and "{fakty}" not in p and "{katy}" not in p, p[:300])
sprawdz("prompt: naglowek historii (cudza tresc) stoi ZA bariera, w sekcji o historii",
        p.index("Everything below is DATA") < p.index("## The story") < p.index("Orbit Labs ships Q7")
        and p.count("Orbit Labs ships Q7") == 1, p[:400])
sprawdz("prompt: do 5 notek (karta 12 faktow), wiedza modelu dozwolona, glos „we” a nie „I”",
        "up to 5" in p and "EVERYTHING ELSE IS YOURS" in p and 'never "I" or "my"' in p)
sprawdz("prompt: polskie pole `sprawdzian` nie wycieka do opisu katow; notka po angielsku",
        "sprawdzian" not in p.lower() and "Write in English only" in p,
        [w for w in p.split() if "sprawdz" in w.lower()])
sprawdz("prompt: osoby przez role, bez wymyslonych szczegolow sceny",
        "Introduce every person or organisation by role" in p and "add no scene details" in p)
sprawdz("prompt: dlugosc to widelki i wskazowka, nie sufit",
        "usually 40–85 words" in p and "a guide, not a cap" in p)

print()
print("=== 2. CZYSZCZENIE ODPOWIEDZI ===")
dluga = "Open weights are a promise, not a release. " + SLOWA
ODPOWIEDZI[:] = [{"notki": [
    nota("how_it_works", dluga, fakty=(2, "4", 99, 2, "x")),
    nota("REVEAL", "too short to be a note"),
    nota("FOO", "Open weights are a promise, not a release. " + SLOWA + " again", fakty=()),
    nota("VERDICT", "Our call on this is different. " + SLOWA, fakty=(3,), wiedza=["  a background claim  ", "", None]),
    "nie slownik",
    nota("PEOPLE", "Another distinct angle on the story. " + SLOWA, fakty=(1,)),
]}]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H, "sledztwo", 3)
sprawdz("za krotka notka, powtorzone otwarcie i nie-slownik odpadaja; ogranicznik `ile` = 3",
        [w["rodzaj"] for w in wynik] == ["HOW_IT_WORKS", "VERDICT", "PEOPLE"], [w["rodzaj"] for w in wynik])
sprawdz("rodzaj z malych liter trafia do tabeli KATY; pierwsza notka to prowadzaca, reszta nie",
        wynik[0]["rodzaj"] in sledztwo.KATY and [w["lead"] for w in wynik] == [True, False, False])
sprawdz("numery faktow: 2 i \"4\" zostaja, 99 i \"x\" odpadaja, bez dubli; fakt niesie tresc, dowod i adres",
        [f["claim"] for f in wynik[0]["fakty"]] == ["Orbit Labs said claim number 2 about the Q7 model.",
                                                     "Orbit Labs said claim number 4 about the Q7 model."]
        and all(f["url"] and f["evidence"] for f in wynik[0]["fakty"]), wynik[0]["fakty"])
sprawdz("wiedza: oczyszczona z pustych i None", wynik[1]["wiedza"] == ["a background claim"], wynik[1]["wiedza"])
sprawdz("tekst notki nie jest przycinany ani poprawiany (zostaje jak od modelu, spacje scalone)",
        wynik[0]["tekst"] == " ".join(dluga.split()))
ODPOWIEDZI[:] = [{"notki": [nota("FOO", "A note with an unknown angle tag. " + SLOWA, fakty=())]}]
wynik, _ = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("nieznany rodzaj -> REVEAL; notka bez faktow bierze pierwszy fakt karty (zrodlo w kolejce zawsze jest)",
        wynik[0]["rodzaj"] == "REVEAL" and wynik[0]["fakty"][0]["claim"].endswith("claim number 1 about the Q7 model."),
        wynik)

print()
print("=== 3. AWARIE: ZAPAS, SMIECI, BUDZET ===")
WYWOLANIA.clear()
ODPOWIEDZI[:] = [llm.OdmowaDostawcy("odmowa"), {"notki": [nota("REVEAL", "First distinct opening here. " + SLOWA), nota("VERDICT", "Second distinct opening there. " + SLOWA)]}]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("odmowa modelu -> drugi tani model (`seria_lekka_zapas`), seria wychodzi",
        [w["purpose"] for w in WYWOLANIA] == ["seria_lekka", "seria_lekka_zapas"] and len(wynik) == 2,
        ([w["purpose"] for w in WYWOLANIA], wynik))
WYWOLANIA.clear()
ODPOWIEDZI[:] = [llm.Truncated("ucieto"), {"notki": [nota("REVEAL", "First distinct opening here. " + SLOWA), nota("VERDICT", "Second distinct opening there. " + SLOWA)]}]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("odpowiedz ucieta na suficie -> tez zapas", [w["purpose"] for w in WYWOLANIA][-1] == "seria_lekka_zapas"
        and len(wynik) == 2)
ODPOWIEDZI[:] = ["to nie jest json, tylko proza"] * 4
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("smieci zamiast JSON-a -> pusta lista, bez wyjatku", wynik == [], wynik)
ODPOWIEDZI[:] = [{"notki": "nie lista"}]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("`notki` nie jest lista -> pusta seria", wynik == [], wynik)
ODPOWIEDZI[:] = [RuntimeError("siec padla")]
wynik, log = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
sprawdz("blad sieci -> pusta lista i komunikat w logu", wynik == [] and "siec padla" in log, (wynik, log))
_przerywa = sledztwo._przerywaja()
_klasa = _przerywa[0] if isinstance(_przerywa, tuple) else _przerywa
ODPOWIEDZI[:] = [_klasa("budzet")]
try:
    cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
    przepuszczony = False
except BaseException as exc:   # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: wyczerpany budzet / wylacznik NIE jest polykany jako „seria pusta”", przepuszczony)

print()
print("=== 4. KOLEJKA NIESIE GOTOWY TEKST ===")
ODPOWIEDZI[:] = [{"notki": [nota("REVEAL", dluga, wiedza=["bg one"]), nota("VERDICT", "Our call is different. " + SLOWA)]}]
seria, _ = cicho(sledztwo.seria_lekka, CONN, 1, karta(12), H)
n, _ = cicho(sledztwo.dodaj_do_kolejki, seria, H, karta(12), 7, {"poziom": "LEKKI"})
kol = sledztwo._kolejka()
sprawdz("seria wchodzi cala do kolejki", n == 2 and len(kol) == 2, (n, kol))
sprawdz("wpis kolejki ma `gotowy_tekst` identyczny z napisanym i `wiedza`",
        kol[0]["gotowy_tekst"] == " ".join(dluga.split()) and kol[0]["wiedza"] == ["bg one"]
        and kol[0]["poziom"] == "LEKKI", kol[0].keys())
sprawdz("kolejnosc i prowadzaca zachowane (k, n, lead)", [(w["k"], w["n"], w["lead"]) for w in kol]
        == [(1, 2, True), (2, 2, False)])
n, _ = cicho(sledztwo.dodaj_do_kolejki, [{"rodzaj": "REVEAL", "wniosek": "x", "fakty": []}], H, karta(12), 8)
sprawdz("wpis ciezkiego toru (bez tekstu) ma pusty `gotowy_tekst` — pisze go pisarz, jak dotad",
        sledztwo._kolejka()[-1]["gotowy_tekst"] == "")

print()
print("=== 5. stages.note(gotowy_tekst=...) OMIJA PISARZA, NIE OMIJA SPRAWDZENIA FAKTOW ===")
conn = db.connect()
rid = db.start_run(conn, "test-seria-lekka", tryb="test")
WYWOLANIA.clear()
ODPOWIEDZI[:] = []
GOTOWA = "Open weights are a promise, not a release. " + SLOWA
dowod = {"fact": "Orbit Labs said claim number 1 about the Q7 model.", "url": "https://s1.example/x",
         "source_date": "2026-10-25", "actually": "", "decision": "", "consequence": "", "wrong_belief": ""}
try:
    with contextlib.redirect_stdout(io.StringIO()):
        wynik = stages.note(conn, rid, "CIEKAWOSTKA", dowod, etap="notka_przeslania_fakt",
                            bez_rozbioru=True, gotowy_tekst=GOTOWA)
except Exception as exc:   # noqa: BLE001
    wynik = exc
purposy = [w["purpose"] for w in WYWOLANIA]
sprawdz("note z gotowym tekstem nie wola pisarza (ani `notka_przeslania_fakt`, ani `note`)",
        not isinstance(wynik, Exception) and "notka_przeslania_fakt" not in purposy and "note" not in purposy,
        (wynik, purposy))
k = ((wynik or {}).get("candidates") or [{}])[0] if isinstance(wynik, dict) else {}
sprawdz("jeden kandydat: gotowy tekst, slowa zmierzone, model = seria lekka",
        isinstance(wynik, dict) and len(wynik.get("candidates") or []) == 1
        and str(k.get("note") or "").startswith("Open weights are a promise")
        and k.get("words_actual") == len(str(k.get("note")).split())
        and k.get("model") == config.MODEL_FOR["seria_lekka"], wynik)
sprawdz("sprawdzenie faktow w sieci DZIALA na takiej notce (cel `factcheck` wolany)",
        "factcheck" in purposy, purposy)

llm.call = _prawdziwy_call
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
