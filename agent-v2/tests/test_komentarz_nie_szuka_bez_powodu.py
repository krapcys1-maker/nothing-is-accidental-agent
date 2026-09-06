# -*- coding: utf-8 -*-
"""Sprawdzanie faktow pod komentarzem nie placi za szukanie, gdy nie ma czego.

CO ZMIERZYLEM, ZANIM TKNALEM KOD. Kanal komentarzy, okres z etykietami:

    comment    n=116  wej=1263   wyj=2138   szukan=0.0   0.6554 USD
    cele       n=41   wej=888    wyj=16281  szukan=0.0   0.5002 USD
    factcheck  n=49   wej=26231  wyj=3357   szukan=3.3   0.4154 USD

Koszt jednego WYSTAWIONEGO komentarza: 0,0399 USD, z czego sprawdzanie faktow
to 26%. Dla porownania notka kosztuje 0,1405 USD — komentarze sa TRZY I POL
RAZA TANSZE i nie one sa problemem konta.

Problem jest waski i widac go po tym, CO sprawdzenie odpowiadalo. Wszystkie
cztery zastrzezenia z czternastu dni brzmialy tak samo:

    „no checkable factual claims naming a study, institution, or attributed
     figure"
    „a positional argument and historical analogy containing no number, date,
     study, named institution"

Czyli nie lapalo falszu — meldowalo, ze nie bylo czego lapac. A za kazde takie
zameldowanie placilismy 26 231 tokenow wejscia i 3,3 wyszukiwania.

ZMIERZONE NA 117 ZYWYCH KOMENTARZACH: srednia dlugosc 33 slowa, a 45% nie ma
ani liczby, ani nazwy wlasnej poza poczatkiem zdania.

CZEGO TA ZMIANA NIE ROBI. Nie wylacza sprawdzenia — wylacza tylko PLATNE
SZUKANIE. Model dalej ocenia tekst z wlasnej wiedzy, wiec twierdzenie bez
liczby i bez nazwy, jak „a text-trained model sees co-occurrence rather than
causality", nadal przez kontrole przechodzi. To ten sam ruch, co przy notce
MYSL (`szukaj=(note_type != "MYSL")`).

DLACZEGO SAM WOREK „PEWNYCH". Sprawdzilem obie wersje na tych samych
117 komentarzach:

    pewne + niepewne : szukaloby 91% — oszczednosc 0,18 USD/miesiac
    same pewne       : szukaloby 55% — oszczednosc 0,86 USD/miesiac

Worek „niepewnych" lapie kazdy wyraz na poczatku zdania („One", „Twenty",
„Models"), wiec z nim bramka nie robi nic.

ZNANA LUKA, PRZYJETA SWIADOMIE: „Google shipped it last week" nie bedzie
szukane, bo nazwa stoi na poczatku zdania. Cena bledu jest niska —
sprawdzenie i tak NIE BLOKUJE komentarza.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_komentarz_nie_szuka_bez_powodu.py
"""
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import stages   # noqa: E402

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


def jest_co_sprawdzac(t):
    """Ta sama regula, co w `comment_on` — trzymana tu, zeby dalo sie ja badac."""
    return bool(re.search(r"\d", t)) or bool(stages.nazwy_wlasne(t))


print("=== 1. TEKST BEZ LICZBY I BEZ NAZWY NIE URUCHAMIA SZUKANIA ===")
# Prawdziwe komentarze z produkcji.
for t in ("One midnight message sustains the waiting. Intermittent reward"
          " keeps hope alive.",
          "Twenty years at the same skill level gives the article its actual"
          " unit. Correction, not time.",
          "Treating models as files is right.",
          "Models are trained to sound certain, which is a different thing."):
    sprawdz("nie szuka: %s" % t[:46], not jest_co_sprawdzac(t))

print()
print("=== 2. TEKST Z KONKRETEM SZUKA DALEJ ===")
for t in ("OpenAI raised the price by 20% in March.",
          "The report from Anthropic says otherwise.",
          "In July 2020 the certificates were treated as equivalent.",
          "That figure comes from the Frontier Safety Framework."):
    sprawdz("szuka: %s" % t[:46], jest_co_sprawdzac(t))

print()
print("=== 3. ZNANA LUKA JEST ZAPISANA, NIE UKRYTA ===")
# Nazwa na poczatku zdania trafia do worka „niepewnych" i nie uruchamia
# szukania. Test PILNUJE, ze to jest opisane w kodzie — inaczej za rok ktos
# uzna to za usterke i „naprawi", nie wiedzac, ze to byl wybor.
sprawdz('nazwa na poczatku zdania faktycznie nie uruchamia szukania',
        not jest_co_sprawdzac("Google shipped it last week."))
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("luka opisana przy kodzie", "ZNANA LUKA" in _zr)
sprawdz("z podanym powodem, ze sprawdzenie i tak nie blokuje",
        "NIE BLOKUJE komentarza" in _zr)

print()
print("=== 4. SPRAWDZENIE NADAL SIE ODBYWA ===")
# Gdyby ktos zamienil to na pominiecie CALEGO sprawdzenia, komentarz z falszem
# przechodzilby bez zadnej kontroli. Wylaczamy szukanie, nie kontrole.
_kod = chr(10).join(w for w in _zr.splitlines()
                    if not w.lstrip().startswith("#"))
sprawdz("zweryfikuj jest wolane zawsze",
        'audyt = zweryfikuj(conn, run_id, text, post.get("title", ""),' in _kod)
sprawdz("a sterowane jest tylko szukanie", "szukaj=_jest_co)" in _kod)
sprawdz("i nie ma tam `continue` omijajacego kontrole",
        "if not _jest_co:\n            continue" not in _kod)

print()
print("=== 5. REGULA W KODZIE ZGADZA SIE Z TA TESTOWANA ===")
# Dwie kopie tej samej reguly rozjechalyby sie po pierwszej zmianie.
sprawdz("kod liczy tak samo: cyfra albo nazwa wlasna",
        're.search(r"\\d", text)) or bool(nazwy_wlasne(text))' in _kod)

print()
print("=== 6. PUSTY I DZIWNY TEKST NIE WYWALA ===")
for t in ("", "   ", "!!!", "?"):
    try:
        sprawdz("%-6r -> %s" % (t, jest_co_sprawdzac(t)),
                isinstance(jest_co_sprawdzac(t), bool))
    except Exception as exc:
        sprawdz("%-6r nie wywala" % t, False, type(exc).__name__)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
