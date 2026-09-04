# -*- coding: utf-8 -*-
"""Komentarz bez ani jednego slowa nie kosztuje trzech wywolan modelu.

CO ZMIERZONO. Przebieg produkcyjny 3 wrzesnia 2026 trzykrotnie zapytal model
o odpowiedz na komentarz bedacy samym emoji i trzy razy dostal to samo:

    [reply] deepseek-v4-pro  wej=2733 wyj=80  $0.0020
    [odpowiedz 1] MILCZY — A laughing emoji carries no question or position...
    [reply] deepseek-v4-pro  wej=2733 wyj=71  $0.0019
    [odpowiedz 2] MILCZY — The comment is only a laughing emoji with nothing...
    [reply] deepseek-v4-pro  wej=2733 wyj=65  $0.0019
    [odpowiedz 3] MILCZY — The comment is only an emoji reaction with no...

0,0058 USD za potwierdzenie tego samego wniosku trzy razy. Wejscie bylo za
kazdym razem IDENTYCZNE (2733 tokeny), wiec zadna z prob nie miala szansy
znalezc czegos, czego nie znalazla pierwsza.

CZEGO TEN TEST NIE ROBI. Nie skraca petli po pierwszej ciszy — trzy podejscia
istnieja po to, zeby model mial szanse cos jednak powiedziec, i to jest zgodne
z doktryna, ktora nie uznaje ciszy za wybor. Odrzucamy WYLACZNIE przypadek, w
ktorym po drugiej stronie nie ma zdania: ani jednego slowa dluzszego niz litera.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_odpowiedz_bez_slow.py
Zaden platny model nie jest wolany — `llm.call` jest podmieniony na atrape.
"""
import json
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
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


wolania = []
_stare_call = stages.llm.call


def atrapa(purpose, system, user, **kw):
    wolania.append(purpose)
    return json.dumps({"reply": "A short answer that says something.",
                       "kind": "built_on", "reason_if_silent": ""})


class Polaczenie:
    """`conn` jest tylko przepustka do `llm.call`, a ten jest atrapa."""


def odpowiedz_na(tekst):
    wolania.clear()
    return stages.reply_to(
        Polaczenie(), 1,
        {"under": "our own note", "author": "Ktos", "text": tekst},
        {"our_note": "Nasza notka o czyms"})


# Przypadki produkcyjne i graniczne. Emoji zapisane przez `chr`, zeby plik
# przechodzil przez konsole, ktora ich nie umie wypisac.
SMIECH = chr(0x1F602)
KCIUK = chr(0x1F44D)

BEZ_SLOW = [(SMIECH, "samo emoji — dokladnie przypadek z produkcji"),
            (KCIUK * 2, "dwa emoji"),
            ("...", "sama interpunkcja"),
            ("!!!", "same wykrzykniki"),
            ("2026", "sama liczba"),
            ("a", "jedna litera"),
            ("", "pusty tekst")]

ZE_SLOWAMI = [("ok", "dwie litery to juz slowo"),
              ("Nice one", "krotka pochwala"),
              ("Ale skad wiadomo, ze to nie przypadek?", "prawdziwe pytanie")]

stages.llm.call = atrapa
try:
    print("=== 1. BEZ ANI JEDNEGO SLOWA — ZERO WYWOLAN ===")
    for tekst, opis in BEZ_SLOW:
        out = odpowiedz_na(tekst)
        sprawdz("%-24s nie kosztuje wywolania" % opis, len(wolania) == 0,
                wolania)

    print()
    print("=== 2. ALE KSZTALT ODPOWIEDZI JEST TEN SAM ===")
    # Wywolujacy w `run.py` siega po `out["candidates"]`. Skrocona sciezka,
    # ktora oddaje inny slownik, kupuje oszczednosc trzech wywolan za wyjatek
    # w srodku przebiegu — czyli za cala reszte doby.
    out = odpowiedz_na(SMIECH)
    sprawdz("jest klucz `candidates`", "candidates" in out, sorted(out))
    sprawdz("i da sie po nim przejsc tak jak w `run.py`",
            [k for k in out["candidates"] if k.get("reply")] == [],
            out["candidates"])
    sprawdz("powod jest nazwany, a nie udawany werdyktem modelu",
            out["candidates"][0].get("reason_if_silent") == "no_text",
            out["candidates"][0])

    print()
    print("=== 3. TEKST ZE SLOWEM IDZIE DO MODELU JAK DOTAD ===")
    # KONTRDOWOD: gdyby sito bylo za szerokie, oszczedzaloby przez milczenie —
    # czyli robilo dokladnie to, czego doktryna zabrania.
    for tekst, opis in ZE_SLOWAMI:
        out = odpowiedz_na(tekst)
        sprawdz("%-24s pyta model %d razy" % (opis, config.COMMENT_CANDIDATES),
                len(wolania) == config.COMMENT_CANDIDATES, len(wolania))
        sprawdz("   i oddaje tresc do wystawienia",
                any(k.get("reply") for k in out["candidates"]))

    print()
    print("=== 4. ILE TO OSZCZEDZA ===")
    # Kontrdowod liczbowy, odtwarzany a nie przepisany: tyle wywolan poszlo by
    # przy starym zachowaniu na tych samych siedmiu przypadkach.
    stare = len(BEZ_SLOW) * config.COMMENT_CANDIDATES
    # PROG WZGLEDNY, NIE STALY. Stalo tu `stare >= 14`, czyli zaklad, ze
    # `COMMENT_CANDIDATES` wynosi co najmniej 2. Gdy 4 wrzesnia 2026 zeszlo
    # do jednego, test oblal — mimo ze oszczednosc jest dokladnie taka sama
    # jak byla: kazdy pominiety cel to CALE podejscie, ktore nie rusza.
    sprawdz("stare zachowanie kosztowaloby %d wywolan zamiast 0" % stare,
            stare >= len(BEZ_SLOW), stare)
finally:
    stages.llm.call = _stare_call

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
