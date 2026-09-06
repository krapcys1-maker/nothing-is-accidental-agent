# -*- coding: utf-8 -*-
"""Tor artykulu ma wlasny sufit, bo dzielil go z notkami i sie nie miescil.

CO ZGLASZA AUDYT (S2). `RUN_LIMIT_USD = 1.60` obowiazuje oba tory, a `config`
opisuje koszt przebiegu artykulu jako 1,4-2,1 USD. Gorna polowa tego pasma nie
miesci sie pod sufitem wcale.

CO ZMIERZYLEM NA PRODUKCJI, w tabeli `runs`:

    przebieg 106   1,394 USD   DONE
    przebieg  77   1,5918 USD  DONE      <-- osiem tysiecznych od sufitu

Zaden nie padl jeszcze na `BudgetExceeded` — ale drugi minal sie z nim o
0,008 USD. To nie jest margines, to przypadek.

DLACZEGO TO BOLI BARDZIEJ NIZ PRZY NOTKACH. Sufit przebiegu podnosi
`BudgetExceeded` w `llm.py`, czyli przebieg ginie na etapie, ktory akurat
wypadl — a przy artykule pisanie kosztuje 0,76 USD i stoi PRZED recenzja, forma
i sprawdzeniem faktow. Przekroczenie znaczy wiec: zaplacilismy najdrozsza
czesc, tekst ladzie w `artykuly-przerwane/` i tydzien jest bez artykulu.

ILE. 2,20 USD — gorna granica zapisanego pasma plus zapas. Nie wiecej, bo przy
suficie miesiecznym 40 USD od pazdziernika cztery artykuly po 2,20 to 22%
miesiaca.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_sufit_artykulu.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))


zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


print("=== 1. DWIE LICZBY, I TA OD ARTYKULU JEST WYZSZA ===")
sprawdz("sufit artykulu istnieje", hasattr(config, "RUN_LIMIT_ARTYKUL_USD"))
sprawdz("jest wyzszy niz sufit notek",
        config.RUN_LIMIT_ARTYKUL_USD > config.RUN_LIMIT_USD,
        (config.RUN_LIMIT_USD, config.RUN_LIMIT_ARTYKUL_USD))
# Pomiar produkcji: najdrozszy zmierzony przebieg artykulu to 1,5918 USD.
sprawdz("miesci najdrozszy ZMIERZONY przebieg (1,5918)",
        config.RUN_LIMIT_ARTYKUL_USD > 1.5918, config.RUN_LIMIT_ARTYKUL_USD)
# I gorna granice pasma zapisanego w `config` (2,1).
sprawdz("miesci takze gorne 2,1 z opisu kosztu",
        config.RUN_LIMIT_ARTYKUL_USD >= 2.1, config.RUN_LIMIT_ARTYKUL_USD)
# Ale nie jest workiem bez dna: cztery artykuly w miesiacu maja sie zmiescic
# w pazdziernikowych 40 USD z duzym zapasem.
sprawdz("cztery artykuly to nie wiecej niz cwierc miesiaca",
        4 * config.RUN_LIMIT_ARTYKUL_USD <= 0.25 * 40.0,
        4 * config.RUN_LIMIT_ARTYKUL_USD)


def zatrzymuje(stage, wydane):
    """Czy przebieg o tym etapie zostalby zatrzymany po wydaniu tej kwoty.

    PYTA `config.sufit_przebiegu`, A NIE `llm._preflight`.

    Pierwsza wersja wolala `_preflight` i przechodzila u mnie, a padala na
    serwerze — bo `_preflight` sprawdza po drodze zapore „darmowy test nie
    placi", ktora jest ZWOLNIONA przy `DRY_RUN`. Mierzyla wiec srodowisko,
    nie regule. Trzeci taki test w tej sesji, wiec regula wyladowala w osobnej
    funkcji, ktora da sie sprawdzic wprost.

    Warunek jest ten sam, co w `llm._preflight`: `wydane >= sufit`.
    """
    return wydane >= config.sufit_przebiegu(stage)


print()
print("=== 2. SUFIT DOBIERANY PO ETAPIE PRZEBIEGU ===")
sprawdz("dzien przy 1,70 USD — ZATRZYMANY", zatrzymuje("dzien", 1.70))
sprawdz("artykul przy 1,70 USD — LECI DALEJ", not zatrzymuje("artykul", 1.70))
sprawdz("artykul-z-puli przy 1,70 USD — LECI DALEJ",
        not zatrzymuje("artykul-z-puli", 1.70))
sprawdz("artykul przy 2,30 USD — ZATRZYMANY", zatrzymuje("artykul", 2.30))
sprawdz("dzien przy 0,50 USD — leci dalej", not zatrzymuje("dzien", 0.50))

print()
print("=== 3. MARGINES PRZEBIEGU 77 ===")
# Konkretne liczby z produkcji. Przebieg 77 DOJECHAL — zaplacil 1,5918 USD przy
# suficie 1,60, czyli skonczyl osiem tysiecznych przed zatrzymaniem.
sprawdz("1,5918 nie zatrzymuje na zadnym z torow — 77 dojechal",
        not zatrzymuje("dzien", 1.5918)
        and not zatrzymuje("artykul-z-puli", 1.5918))
sprawdz("1,61 USD na starym torze — ZATRZYMANY", zatrzymuje("dzien", 1.61))
sprawdz("1,61 USD na torze artykulu — LECI DALEJ",
        not zatrzymuje("artykul-z-puli", 1.61))
sprawdz("2,05 USD na torze artykulu jeszcze przechodzi",
        not zatrzymuje("artykul-z-puli", 2.05))

print()
print("=== 4. NIEZNANY ETAP DOSTAJE SUFIT OSTROZNIEJSZY ===")
sprawdz("nieznany etap przy 1,70 — ZATRZYMANY", zatrzymuje("cos-nowego", 1.70))
sprawdz("brak etapu przy 1,70 — ZATRZYMANY", zatrzymuje(None, 1.70))
sprawdz("pusty napis tez", zatrzymuje("", 1.70))

print()
print("=== 4b. llm._preflight PYTA TE SAMA FUNKCJE ===")
# Bez tego sekcje wyzej sprawdzalyby regule, ktorej produkcja nie uzywa.
_llm = pathlib.Path("agent-v2/llm.py").read_text(encoding="utf-8")
_kod = chr(10).join(w for w in _llm.splitlines()
                    if not w.lstrip().startswith("#"))
sprawdz("preflight bierze sufit z config.sufit_przebiegu",
        "config.sufit_przebiegu(row[" in _kod)
sprawdz("i nie wybiera go sam", "RUN_LIMIT_ARTYKUL_USD if" not in _kod)
sprawdz("porownanie nadal >= sufit", 'float(row["s"]) >= _sufit' in _kod)

print()
print("=== 5. KONTROLA PRZED STARTEM PYTA O TE SAMA LICZBE ===")
# Kontrola „czy starczy na caly artykul" musi uzywac sufitu, ktory potem
# naprawde zatrzyma — inaczej mowi o 1,60, a zatrzymanie przychodzi przy 2,20.
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
_kod = chr(10).join(w for w in _run.splitlines()
                    if not w.lstrip().startswith("#"))
sprawdz("kontrola miesiaca uzywa sufitu artykulu",
        "_zostalo < config.RUN_LIMIT_ARTYKUL_USD" in _kod)
sprawdz("i komunikat podaje te sama liczbe",
        "artykul to do ${config.RUN_LIMIT_ARTYKUL_USD}" in _kod)
sprawdz("naglowek przebiegu pokazuje obie",
        "config.RUN_LIMIT_ARTYKUL_USD" in _kod
        and "config.RUN_LIMIT_USD" in _kod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
