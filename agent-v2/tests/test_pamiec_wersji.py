# -*- coding: utf-8 -*-
"""Premiera to wersja, ktorej NIGDY wczesniej nie widzielismy — nie tylko w korpusie.

DLACZEGO TO POWSTALO (27.09.2026). 26.09 o 19:35 wykrywacz wydarzen oglosil
PREMIERE „3.8" i otworzyl furtke szukania. Gemini 3.8 obsluzylismy jako premiere
6.09 — dwadziescia dni wczesniej. Nowosc numeru byla liczona wzgledem korpusu
sprzed okna czterech dni, a korpus to 200 najnowszych tematow, czyli kilka dni
wstecz. Wlasciciel: pisanie o premierze dwa tygodnie po premierze jest
niewybaczalne.

Test odtwarza tamten dzien (kontrola: bez pamieci wersji blad wraca) i sprawdza
strone odwrotna: prawdziwa nowa premiera o tym samym numerze, ale innej rodziny,
nadal jest premiera.

BEZ PYTESTA, bez sieci. Uruchamiac z korzenia repozytorium.
"""
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import korpus_kanalow as kk   # noqa: E402
import stages                 # noqa: E402

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
DZIS = TERAZ.strftime("%Y-%m-%d")
PRZEDWCZORAJ = (TERAZ - timedelta(days=2)).strftime("%Y-%m-%d")
DAWNO = (TERAZ - timedelta(days=20)).strftime("%Y-%m-%d")


def wpis(kanal, temat, data=DZIS):
    return {"kanal": kanal, "temat": temat, "data": data,
            "url": "https://%s.example/x" % kanal.lower().replace(" ", "")}


print("=== 1. KLUCZE WERSJI ===")
sprawdz("numer z rodzina z tytulu",
        kk.klucze_wersji("Introducing Gemini 3.8 Live with Live Avatar") == {"gemini 3.8"},
        kk.klucze_wersji("Introducing Gemini 3.8 Live with Live Avatar"))
sprawdz("numer z nazwa w srodku jest kluczem sam dla siebie",
        kk.klucze_wersji("GLM-5.3-Flash tops the chart") == {"glm-5.3-flash"},
        kk.klucze_wersji("GLM-5.3-Flash tops the chart"))
sprawdz("goly numer, gdy rodziny brak", kk.klucze_wersji("3.8 is wild today") == {"3.8"})
sprawdz("tekst ciagly: bez golych numerow",
        kk.klucze_wersji("revenue grew 5.5 times", tylko_z_rodzina=True) == set())
sprawdz("rok to nie wersja", kk.klucze_wersji("AGI 2026 is coming") == set())

print()
print("=== 2. PAMIEC ZAPISUJE NAJWCZESNIEJSZY DZIEN I PRZEZYWA PRZEBIEG ===")
pam = kk.pamiec_wersji([wpis("Kanal A", "Gemini 3.8 Live with Live Avatar")],
                       dodatkowe=[("3.8 flash gemini", DAWNO, False),
                                  ("Opus 5.5 costs 4 dollars", PRZEDWCZORAJ, True),
                                  ("revenue grew 5.5 times", DAWNO, True)])
sprawdz("gemini 3.8 z najwczesniejsza data (z obsluzonego wydarzenia)",
        pam.get("gemini 3.8") == DAWNO, pam)
sprawdz("opus 5.5 z tekstu ciaglego, bo ma rodzine", pam.get("opus 5.5") == PRZEDWCZORAJ, pam)
sprawdz("KONTRDOWOD: goly „5.5” z tekstu ciaglego NIE wchodzi", "5.5" not in pam, pam)
plik = config.DATA_DIR / "wersje_widziane.json"
sprawdz("pamiec zapisana na dysku", plik.exists()
        and json.loads(plik.read_text(encoding="utf-8")).get("gemini 3.8") == DAWNO)
pam2 = kk.pamiec_wersji([wpis("Kanal B", "Gemini 3.8 again", DZIS)])
sprawdz("nowszy wpis nie nadpisuje wczesniejszej daty", pam2.get("gemini 3.8") == DAWNO, pam2)

print()
print("=== 3. DZIEN 26.09 ODTWORZONY ===")
# Dwa kanaly, wspolny tylko numer — sciezka premiery, tak jak 26.09 („3.8").
KORPUS = [wpis("Sam Witteveen", "Introducing Gemini 3.8 Live with Live Avatar"),
          wpis("Matt Wolfe", "Google gives 3.8 Live a face")]
bez = kk.wielkie_wydarzenia(KORPUS)
sprawdz("KONTROLA: bez pamieci wersji wraca blad — „3.8” jako premiera",
        any(w["premiera"] and "3.8" in w["o_czym"] for w in bez), bez)
z = kk.wielkie_wydarzenia(KORPUS, wersje_widziane={"gemini 3.8": DAWNO})
sprawdz("z pamiecia wersji 3.8 sprzed dwudziestu dni NIE jest premiera",
        not any(w["premiera"] for w in z), z)
GOLE = [wpis("Kanal A", "3.8 Live gets a face today"),
        wpis("Kanal B", "The 3.8 Live avatar explained")]
sprawdz("KONTROLA: tytuly z golym numerem bez pamieci — premiera",
        any(w["premiera"] for w in kk.wielkie_wydarzenia(GOLE)))
sprawdz("tytuly z golym numerem, gdy Gemini 3.8 juz bylo — nie premiera",
        not any(w["premiera"] for w in kk.wielkie_wydarzenia(
            GOLE, wersje_widziane={"gemini 3.8": DAWNO})))
FALA = [wpis("Sam Witteveen", "Introducing Gemini 3.8 Live with Live Avatar"),
        wpis("Matt Wolfe", "Gemini 3.8 Live Avatar is wild"),
        wpis("TheAIGRID", "Google Gemini 3.8 Live gets a face")]
fala = kk.wielkie_wydarzenia(FALA, wersje_widziane={"gemini 3.8": DAWNO})
sprawdz("fala (trzy kanaly o tym samym) zostaje wydarzeniem, ale nie premiera",
        fala and all(not w["premiera"] for w in fala), fala)

print()
print("=== 4. PRAWDZIWA PREMIERA NADAL JEST PREMIERA ===")
NOWA = [wpis("Wes Roth", "Grok 5.5 just dropped"),
        wpis("Matthew Berman", "Grok 5.5 hands-on")]
sprawdz("Grok 5.5 wchodzi jako premiera mimo pamietanego Opusa 5.5",
        any(w["premiera"] for w in kk.wielkie_wydarzenia(
            NOWA, wersje_widziane={"opus 5.5": DAWNO, "gemini 3.8": DAWNO})))
sprawdz("wersja widziana PRZEDWCZORAJ (w oknie) nadal jest premiera",
        any(w["premiera"] for w in kk.wielkie_wydarzenia(
            NOWA, wersje_widziane={"grok 5.5": PRZEDWCZORAJ})))

print()
print("=== 5. HISTORIA BOTA ZASILA PAMIEC ===")
(config.DATA_DIR / "wydarzenia_obsluzone.json").write_text(json.dumps(
    {"3.8,flash,gemini": {"kiedy": DAWNO, "ile": 1, "proby": 1}}), encoding="utf-8")
stages.WYDARZENIA_OBSLUZONE = config.DATA_DIR / "wydarzenia_obsluzone.json"
(config.DATA_DIR / "dziennik.jsonl").write_text(json.dumps(
    {"rodzaj": "notka", "udane": True, "kiedy": DAWNO + "T10:00:00+00:00",
     "tekst": "Claude Fable 5.1 writes our articles now."}) + "\n", encoding="utf-8")
hist = stages._historia_wersji()
sprawdz("obsluzone wydarzenia w historii", ("3.8 flash gemini", DAWNO, False) in hist, hist[:3])
sprawdz("wystawione notki w historii, tylko z rodzina",
        any(t.startswith("Claude Fable") and z is True for t, _, z in hist), hist)

_kod = "\n".join(w for w in pathlib.Path("agent-v2/stages.py").read_text(
    encoding="utf-8").splitlines() if not w.lstrip().startswith("#"))
sprawdz("skaut podaje pamiec wersji wykrywaczowi",
        "wersje_widziane=_wersje" in _kod and "dodatkowe=_historia_wersji()" in _kod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
