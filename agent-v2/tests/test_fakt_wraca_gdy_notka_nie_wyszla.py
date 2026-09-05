# -*- coding: utf-8 -*-
"""Fakt notki, ktora nie wyszla, wraca do puli zamiast sie spalic.

CO ZGLASZA AUDYT (Q2). `wez_kandydatow` znaczy kandydata jako uzytego przy
WYJMOWANIU, a `notki_dnia` oddaje na koncu tylko NIETKNIETY zapas. Fakt zdjety
przez `wybierz_material` pod notke, ktora potem nie wyszla — na dlugosci,
zaporze, braku `--wyslij` albo koncu czasu — nie byl ani wydany, ani zwrocony.

CO ZMIERZYLEM NA PRODUKCJI, ZANIM TKNALEM KOD. Czternascie dni dziennika:

    notki napisane      50
    notki wystawione    40
    stracone             6   (przebiegi 102, 104, 105, 129, 139)

Dwa mechanizmy, oba widoczne w dzienniku:

    przebieg 104 — notka napisana (45 slow, OK), potem „ODRZUCONA PRZED
      SPRAWDZENIEM: adres www w tresci". Zadnej proby zastepczej. Fakt spalony,
      z przebiegu nie wyszlo nic.

    przebieg 139 — napisane TRZY notki z gory, wydana jedna, potem „czas
      przebiegu wyczerpany — odpuszczam notki (przerwa 39 min nie zmiesci sie
      w 34 min)". Dwie oplacone notki i dwa fakty przepadly razem.

CZEGO NIE ZMIENIAM. Zasada „wolimy stracic kandydata niz wystawic dwa razy"
zostaje nietknieta — ona dotyczy faktu, ktory JUZ POSZEDL w swiat, i takiego
nadal blokuje `zapisz_zuzyte` oraz pamiec notek. Fakt, ktorego nikt nigdy nie
zobaczyl, nie ma jak sie zdublowac.

JAK TO WPIETO I DLACZEGO TAK. Petla notek jest OSTATNIA instrukcja `notki()`,
wiec `return` znaczy w niej dokladnie tyle, co `break` — ale po `break` kod
ponizej sie wykona. Trzy `return` zamienione na `break`, zwrot na koncu petli.
Pierwsza wersja tej poprawki wyciagala petle do osobnej funkcji z `try/finally`
i zmieniala przez to znaczenie `return` w calym bloku; odrzucona.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_fakt_wraca_gdy_notka_nie_wyszla.py
"""
import ast
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


ZR = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
DRZEWO = ast.parse(ZR)


def petla_notek():
    """Petla `for n in stages.notki_dnia(...)` z `run.py`, jako wezel AST."""
    for f in ast.walk(DRZEWO):
        if not (isinstance(f, ast.FunctionDef) and f.name == "notki"):
            continue
        for w in ast.walk(f):
            if (isinstance(w, ast.For)
                    and isinstance(w.iter, ast.Call)
                    and getattr(w.iter.func, "attr", "") == "notki_dnia"):
                return w
    return None


print("=== 1. Z PETLI NOTEK NIE DA SIE WYJSC OMIJAJAC ZWROTU ===")
# To jest cala gwarancja: `return` wychodzi z `notki()` i pomija kod za petla,
# `break` nie. Sprawdzam AST, a nie napisy — inaczej komentarz ze slowem
# „return" wystarczylby, zeby test przeszedl.
petla = petla_notek()
sprawdz("petla po notkach istnieje", petla is not None)
if petla is not None:
    powroty = [w.lineno for w in ast.walk(petla) if isinstance(w, ast.Return)]
    sprawdz("nie ma w niej ani jednego return", not powroty, powroty)
    sprawdz("sa za to break-i", any(isinstance(w, ast.Break)
                                    for w in ast.walk(petla)))

print()
print("=== 2. PETLA JEST OSTATNIA — INACZEJ break NIE ZNACZY TEGO CO return ===")
# Gdyby ktos dopisal cos ZA petla, `break` zaczalby to wykonywac, a `return`
# nie — i zamiana przestalaby byc rownowazna. Wtedy ten test ma zapiszczec.
for f in ast.walk(DRZEWO):
    if isinstance(f, ast.FunctionDef) and f.name == "notki":
        po_petli = [w for w in f.body[f.body.index(petla) + 1:]] \
            if petla in f.body else []
        # Zwrot do puli jest jedyna rzecza, ktora ma prawo tam stac.
        sprawdz("za petla stoi wylacznie zwrot do puli",
                len(po_petli) <= 1, len(po_petli))

print()
print("=== 3. KAZDA SCIEZKA BEZ PUBLIKACJI ODKLADA FAKT ===")
sprawdz("blok zwrotu w ogole istnieje",
        "niewydane: list[dict] = []" in ZR
        and "oddane do puli, bo nie wyszly" in ZR)
if "niewydane: list[dict] = []" not in ZR:
    # Na kodzie sprzed naprawy test staje TUTAJ — z diagnoza, nie ze sladem
    # stosu. To jest odtworzony kontrdowod, a nie awaria testu.
    print()
    print("  (zwrotu nie ma — reszty nie ma czego sprawdzac)")
    print()
    print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
    sys.exit(1)
_blok = ZR[ZR.index("niewydane: list[dict] = []"):
           ZR.index("oddane do puli, bo nie wyszly")]
sprawdz("koniec czasu", _blok.count('niewydane.append(n["fakt"])') >= 1)
sprawdz("brak kandydata po sprawdzeniu (przebieg 104)",
        "Tu ladowal przebieg 104" in _blok)
sprawdz("rytm nie pozwolil wystawic", "rytm(" in _blok)
sprawdz("publikacja sie nie udala",
        'not wynik.get("wyslane") and n.get("fakt")' in _blok)
sprawdz("przebieg na sucho tez nie spala",
        "PRZEBIEG NA SUCHO NIE SPALA MATERIALU" in _blok)
sprawdz("wszystkich odlozen jest piec",
        _blok.count('niewydane.append(n["fakt"])') == 5,
        _blok.count('niewydane.append(n["fakt"])'))

print()
print("=== 4. WYDANY FAKT NIE WRACA ===")
# Kontrola odwrotna. Gdyby wracal takze opublikowany, zapora przed powtorka
# przestalaby dzialac — a to jest wazniejsze niz oszczednosc.
sprawdz("po udanej publikacji fakt idzie do zuzytych",
        'if wynik.get("wyslane") and n.get("fakt"):' in _blok
        and "zapisz_zuzyte" in _blok)
_po_wyslaniu = _blok[_blok.index('if wynik.get("wyslane") and n.get("fakt")'):]
sprawdz("i NIE trafia do zwracanych",
        'niewydane.append' not in _po_wyslaniu.split("oznacz_uzyty")[0])

print()
print("=== 5. ZWROT NAPRAWDE ODZNACZA W INDEKSIE ===")
# Bez tego sekcje wyzej sprawdzalyby ksztalt kodu, a nie skutek.
FAKT_A = {"fact": "OpenAI cut cached input pricing by half on 4 September 2026."}
FAKT_B = {"fact": "A completely separate finding about railway signalling."}
stages._zapisz_indeks([
    dict(FAKT_A, status="uzyty", kiedy="2099-01-01"),
    dict(FAKT_B, status="uzyty", kiedy="2099-01-01"),
])
ile = stages.zwroc_kandydatow([FAKT_A])
po = {" ".join(k["fact"].split()): k.get("status") for k in stages.wczytaj_indeks()}
sprawdz("oddany dokladnie jeden", ile == 1, ile)
sprawdz("zwrocony fakt jest znowu do wziecia",
        po[" ".join(FAKT_A["fact"].split())] == "nowy",
        po[" ".join(FAKT_A["fact"].split())])
sprawdz("sasiedni fakt nietkniety",
        po[" ".join(FAKT_B["fact"].split())] == "uzyty",
        po[" ".join(FAKT_B["fact"].split())])

print()
print("=== 6. PUSTA LISTA NIC NIE ROBI ===")
# Petla bez strat wola zwrot z pusta lista — nie moze przy tym niczego ruszyc.
stages._zapisz_indeks([dict(FAKT_A, status="uzyty", kiedy="2099-01-01")])
sprawdz("zwrot z pustej listy oddaje zero", stages.zwroc_kandydatow([]) == 0)
sprawdz("i nie odznacza niczego",
        stages.wczytaj_indeks()[0].get("status") == "uzyty",
        stages.wczytaj_indeks()[0].get("status"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
