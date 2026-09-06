# -*- coding: utf-8 -*-
"""Niepelna atrapa `stages` mowi o sobie, zamiast udawac usterke kodu.

SKAD SIE WZIAL. 5-6 wrzesnia 2026, w jednej sesji, PIEC RAZY powtorzyl sie ten
sam wypadek: kod produkcyjny zaczal wolac cos, czego atrapa w tescie nie miala.

    test_artykul_nie_ginie_po_drodze  — `_napisz_i_zapisz` dostalo `evidence`
    test_artykul_nie_ginie_po_drodze  — `discovery` dostalo `tylko_pierwotne`
    test_czas                         — `dzien` dostalo `poza_oknem`
    test_budzet_nie_publikuje         — `stages.karta_do_weryfikacji`
    test_ratunek_tekstu               — to samo

ZA KAZDYM RAZEM OBJAW BYL MYLACY. `blok()` w `run.py` lapie wyjatki, wiec
`AttributeError` z niepelnej atrapy nie wyglada jak brak metody — wyglada jak
„etap sie nie wykonal". `test_ratunek_tekstu` zglaszal wtedy cztery porazki
o tym, ze artykul nie przeszedl przez `zweryfikuj`, a przyczyna byla o jedna
linijke wczesniej. Godzina szukania za kazdym razem.

DLACZEGO NIE ANALIZA STATYCZNA. Pierwsza wersja tego testu porownywala liste
`stages.X(` z pliku produkcyjnego z metodami atrapy i zglosila trzy braki —
WSZYSTKIE FALSZYWE. Te testy wchodza roznymi wejsciami: `test_ratunek_tekstu`
wola `_napisz_i_zapisz` wprost i nigdy nie dociera do `discovery`, a
`test_artykul_nie_ginie_po_drodze` podmienia samo `_napisz_i_zapisz` i nigdy
nie dociera do `zweryfikuj`. Zadna statyczna lista tego nie rozroznia, a regula
szersza niz usterka to blad, ktory tego samego dnia popelnilem juz trzy razy.

CO ZAMIAST TEGO. Atrapa ma `__getattr__`, ktore WYPISUJE, czego jej brakuje,
i dopiero potem podnosi `AttributeError`. `print` przed `raise`, bo to wlasnie
wyjatek bywa polkniety, a wydruk nie.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_atrapy_nadazaja_za_kodem.py
"""
import ast
import io
import pathlib
import sys

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


# Testy, ktore podmieniaja CALY modul `stages` na wlasna klase. Tylko te maja
# jak zgubic metode — reszta wola prawdziwy modul.
PLIKI = ("test_ratunek_tekstu.py", "test_budzet_nie_publikuje.py",
         "test_artykul_nie_ginie_po_drodze.py")


def klasa_atrapy(sciezka):
    for w in ast.parse(sciezka.read_text(encoding="utf-8")).body:
        if isinstance(w, ast.ClassDef) and w.name == "AtrapaStages":
            return w
    return None


print("=== 1. KAZDA ATRAPA MA STRAZ ===")
for nazwa in PLIKI:
    p = pathlib.Path("agent-v2/tests") / nazwa
    k = klasa_atrapy(p) if p.exists() else None
    if k is None:
        sprawdz("%-38s klasa AtrapaStages" % nazwa, False, "brak")
        continue
    metody = {f.name for f in k.body
              if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    sprawdz("%-38s ma __getattr__" % nazwa, "__getattr__" in metody,
            sorted(metody)[:6])

print()
print("=== 2. STRAZ WYPISUJE, ZANIM PODNIESIE ===")
# Sam `raise` nie wystarczy — `blok()` go polyka. Wydruk zostaje.
for nazwa in PLIKI:
    p = pathlib.Path("agent-v2/tests") / nazwa
    k = klasa_atrapy(p)
    if k is None:
        continue
    straz = next((f for f in k.body
                  if isinstance(f, ast.FunctionDef) and f.name == "__getattr__"),
                 None)
    if straz is None:
        sprawdz("%-38s straz istnieje" % nazwa, False)
        continue
    ma_print = any(isinstance(w, ast.Call)
                   and getattr(w.func, "id", "") == "print"
                   for w in ast.walk(straz))
    ma_raise = any(isinstance(w, ast.Raise) for w in ast.walk(straz))
    kolejnosc = [type(w).__name__ for w in straz.body]
    sprawdz("%-38s print i raise" % nazwa, ma_print and ma_raise,
            (ma_print, ma_raise))
    sprawdz("%-38s print PRZED raise" % nazwa,
            kolejnosc and kolejnosc[-1] == "Raise", kolejnosc)

print()
print("=== 3. STRAZ NAPRAWDE ODPALA — na zywej klasie ===")
# Bez tej sekcji sprawdzalbym ksztalt kodu, a nie zachowanie.
_p = pathlib.Path("agent-v2/tests/test_ratunek_tekstu.py")
_k = klasa_atrapy(_p)
_ns = {}
exec(compile(ast.Module(body=[_k], type_ignores=[]), "<atrapa>", "exec"), _ns)


class Pusta(_ns["AtrapaStages"]):
    """Bez `__init__` rodzica — interesuje mnie sam `__getattr__`."""

    def __init__(self):
        pass


_a = Pusta()
_wydruk = io.StringIO()
_stare = sys.stdout
sys.stdout = _wydruk
try:
    _a.metoda_dolozona_jutro
    _podnioslo = False
except AttributeError:
    _podnioslo = True
finally:
    sys.stdout = _stare
_tekst = _wydruk.getvalue()

sprawdz("brak metody podnosi AttributeError", _podnioslo)
sprawdz("i wypisuje nazwe brakujacej metody",
        "metoda_dolozona_jutro" in _tekst, _tekst[:90])
sprawdz("i mowi wprost, ze to nie usterka kodu produkcyjnego",
        "nie jest usterka kodu" in _tekst, _tekst[:90])

print()
print("=== 4. METODY, KTORE ATRAPA MA, DZIALAJA NORMALNIE ===")
# Straz nie moze przechwytywac tego, co istnieje.
_metody = {f.name for f in _k.body if isinstance(f, ast.FunctionDef)}
sprawdz("zweryfikuj jest zdefiniowane w atrapie", "zweryfikuj" in _metody)
_wydruk2 = io.StringIO()
sys.stdout = _wydruk2
try:
    _ = _a.zweryfikuj
finally:
    sys.stdout = _stare
sprawdz("i siegniecie po nie NIC nie wypisuje",
        _wydruk2.getvalue() == "", _wydruk2.getvalue()[:60])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
