# -*- coding: utf-8 -*-
"""Parowanie banku nie pyta modelu o zbior, ktory sie nie zmienil.

CO ZMIERZYLEM NA PRODUKCJI, czternascie dni:

    5 x  [parowanie] grup: 0, scalonych pozycji: 0
    1 x  [parowanie] grup: 1, scalonych pozycji: 1

Szesc uruchomien, jedna scalona para. Kazde wywolanie to okolo 20 tysiecy
tokenow WYJSCIA — 98% kosztu tego etapu — czyli okolo 1,43 USD miesiecznie za
jedno scalenie.

PRZYCZYNA NIE BYLA W MODELU. `sparuj_bank` szlo przy KAZDYM przebiegu i za
kazdym razem wysylalo caly zbior wolnych wpisow. A bank miedzy przebiegami
czesto sie nie zmienia — material bierze sie z indeksu bez nowego szukania,
wiec te same 20-40 wpisow jechalo do modelu piec razy dziennie. Odpowiedz
„nie ma duplikatow" nie zmieni sie, dopoki zbior sie nie zmieni.

DLACZEGO ODCISK, A NIE ZEGAR. Prog czasowy („raz na dobe") przepuscilby
przebieg, w ktorym doszlo dwadziescia nowych faktow, i zablokowal ten, w ktorym
nie doszlo nic. Pytanie brzmi „czy zbior sie zmienil", wiec pilnuje tego odcisk
zbioru.

CZEGO TA ZMIANA NIE ROBI: nie dotyka tego, JAK model grupuje ani ile scala.
Zmienia sie tylko to, czy w ogole go pytamy.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_parowanie_nie_pyta_dwa_razy.py
"""
import json
import pathlib
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


PYTANIA = []
ODPOWIEDZ = {"groups": []}


def atrapa_call(purpose, system, user, **k):
    PYTANIA.append(purpose)
    return json.dumps(ODPOWIEDZ)


stages.llm.call = atrapa_call


def wpis(i, tekst):
    return {"fact": tekst, "status": "nowy",
            "kiedy": "2099-01-01T00:00:00+00:00", "url": "https://e/%d" % i}


BANK = [wpis(0, "OpenAI cut cached input pricing by half."),
        wpis(1, "A regulator set the threshold at 12 units."),
        wpis(2, "Two operators filed the same fault report."),
        wpis(3, "A registry lists 41 exemptions this year.")]

print("=== 1. PIERWSZE PAROWANIE PYTA ===")
stages._zapisz_indeks(list(BANK))
PYTANIA.clear()
w1 = stages.sparuj_bank(None, None)
sprawdz("model zapytany raz", len(PYTANIA) == 1, PYTANIA)
sprawdz("i to o parowanie", PYTANIA == ["parowanie"], PYTANIA)

print()
print("=== 2. DRUGIE, NA TYM SAMYM BANKU, JUZ NIE PYTA ===")
PYTANIA.clear()
w2 = stages.sparuj_bank(None, None)
sprawdz("model NIE zapytany", not PYTANIA, PYTANIA)
sprawdz("i widac to w wyniku", w2.get("pominiete") == 1, w2)

print()
print("=== 3. TRZECIE, NA TYM SAMYM — nadal nie pyta ===")
PYTANIA.clear()
stages.sparuj_bank(None, None)
sprawdz("nadal cisza", not PYTANIA, PYTANIA)

print()
print("=== 4. NOWY FAKT W BANKU — PYTA ZNOWU ===")
# To jest cala pointa odcisku: nie zegar, tylko zmiana zbioru.
stages._zapisz_indeks(list(BANK) + [wpis(4, "A new and different finding.")])
PYTANIA.clear()
stages.sparuj_bank(None, None)
sprawdz("zbior sie zmienil, wiec pytamy", len(PYTANIA) == 1, PYTANIA)

print()
print("=== 5. USUNIETY FAKT TEZ ZMIENIA ZBIOR ===")
stages._zapisz_indeks(list(BANK)[:3])
PYTANIA.clear()
stages.sparuj_bank(None, None)
sprawdz("mniej wpisow tez znaczy inny zbior", len(PYTANIA) == 1, PYTANIA)

print()
print("=== 6. KOLEJNOSC WPISOW NIE UDAJE ZMIANY ===")
# Indeks bywa przestawiany (ranking, zwroty do puli). Sama zmiana kolejnosci
# nie jest zmiana ZBIORU i nie moze kosztowac wywolania.
stages._zapisz_indeks(list(reversed(list(BANK)[:3])))
PYTANIA.clear()
stages.sparuj_bank(None, None)
sprawdz("przestawienie kolejnosci nie pyta ponownie", not PYTANIA, PYTANIA)

print()
print("=== 7. PO SCALENIU ZBIOR JEST INNY, WIEC WOLNO ZAPYTAC ===")
stages._zapisz_indeks(list(BANK))
ODPOWIEDZ = {"groups": []}
stages.sparuj_bank(None, None)          # zapisuje odcisk
ODPOWIEDZ = {"groups": [{"zostaje": 0, "scalic": [1]}]}
# Zmieniam zbior, zeby parowanie doszlo do modelu i cos scalilo.
stages._zapisz_indeks(list(BANK) + [wpis(9, "Yet another separate finding.")])
PYTANIA.clear()
wynik = stages.sparuj_bank(None, None)
sprawdz("parowanie doszlo do modelu", len(PYTANIA) == 1, PYTANIA)
po = stages.wczytaj_indeks()
sprawdz("indeks nadal ma wszystkie wpisy (nic nie kasujemy)",
        len(po) == 5, len(po))

print()
print("=== 8. MALY BANK NIE PYTA I NIE PSUJE ODCISKU ===")
stages._zapisz_indeks([wpis(0, "Only one entry here.")])
PYTANIA.clear()
w = stages.sparuj_bank(None, None)
sprawdz("ponizej trzech wpisow nie pytamy", not PYTANIA, PYTANIA)
sprawdz("i wynik mowi zero", w.get("grup") == 0 and w.get("scalone") == 0, w)

print()
print("=== 9. BRAK PLIKU ODCISKU NIE WYWALA ===")
_p = config.DATA_DIR / "parowanie_odcisk.txt"
if _p.exists():
    _p.unlink()
stages._zapisz_indeks(list(BANK))
PYTANIA.clear()
try:
    stages.sparuj_bank(None, None)
    sprawdz("bez pliku odcisku dziala i pyta", len(PYTANIA) == 1, PYTANIA)
except Exception as exc:
    sprawdz("bez pliku odcisku nie wywala", False, type(exc).__name__)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
