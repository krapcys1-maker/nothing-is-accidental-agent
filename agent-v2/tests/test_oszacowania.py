# -*- coding: utf-8 -*-
"""Warstwa oszacowan ma umiec powiedziec „NIE WIEM" — i mowic to czesto.

PO CO TO POWSTALO. Bot zapisuje wszystko i nie czyta niczego. Wie, ze wystawil
121 komentarzy, i nie wie, czy ktorykolwiek cos dal. `oszacowania.py` liczy to
z surowych zapisow PRZY KAZDYM WYWOLANIU — bez przechowywania zdan, bo ten
projekt stracil dziewiec dni na zapamietanym zdaniu „Substack zdjal przycisk
Follow", ktore przestalo byc prawdziwe, a system cytowal je dalej.

CZEGO TEN TEST PILNUJE NAJMOCNIEJ — ZEBY OSZACOWANIE NIE UDAWALO WIEDZY.
Rachunek deterministyczny daje powtarzalnosc, nie prawde. Falsz wchodzi tedy:
swieze zero brane za zero ostateczne, mala proba, porownanie tresci o roznym
wieku, dane sprzed przestawienia konta, petla zwrotna. Kazda z tych drog ma
tu wlasny przypadek.

I OSOBNO: ZE STALE REDAKCYJNE NIE SA HIPOTEZAMI. Wagi postaw trzymaja KOREKTE
i ZGODE nisko dlatego, ze „wieczny korygujacy i potakiwacz to ta sama wada
z dwoch stron" — to decyzja o tym, czym jest to pismo, a nie twierdzenie do
obalenia liczba odpowiedzi. Optymalizator puszczony luzem nauczylby sie
zaczepiac, bo zaczepka zbiera odpowiedzi, i mialby racje w kazdej liczbie
osobno. Dlatego modulacja jest ograniczona z gory, z dolu, i nie dotyka
wariantow, o ktorych nie wiemy nic.

BEZ PYTESTA, zero sieci, zero platnych wywolan, produkcja nietknieta — dane
sa budowane w katalogu tymczasowym.
Uruchamiac z korzenia repo:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_oszacowania.py
"""
import io
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config      # noqa: E402

# Katalog danych PRZED zaimportowaniem modulow, ktore go czytaja.
KATALOG = pathlib.Path(tempfile.mkdtemp(prefix="oszacowania-test-"))
config.DATA_DIR = KATALOG

import oszacowania  # noqa: E402
import statystyki   # noqa: E402

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

# TEST NIE MOZE ZALEZEC OD DZISIEJSZEJ DATY. Pierwsza wersja budowala „komentarz
# sprzed dziesieciu dni" i wszystkie przypadki padly, bo dziesiec dni przed
# 1 wrzesnia 2026 to 22 sierpnia — czyli PRZED przestawieniem konta (25 sierpnia),
# wiec modul poprawnie je odsiewal. Test mierzyl wtedy kalendarz, nie kod.
#
# Przy okazji wyszla rzecz warta zapamietania: 1 wrzesnia 2026 cale uzyteczne
# okno mialo szerokosc CZTERECH DNI — od progu dojrzalosci (3 dni) do
# przestawienia konta (7 dni wstecz). Stad „nie wiem" wszedzie.
config.PRZESTAWIENIE_KONTA = "2020-01-01"


def dni_temu(n):
    return (TERAZ - timedelta(days=n)).isoformat()


def zapisz(dziennik, pomiary):
    """Buduje oba pliki od zera. Kazdy przypadek dostaje wlasny swiat."""
    with io.open(KATALOG / "dziennik.jsonl", "w", encoding="utf-8") as f:
        for w in dziennik:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")
    with io.open(KATALOG / "statystyki.jsonl", "w", encoding="utf-8") as f:
        for w in pomiary:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")


def komentarz(ident, postawa, wiek_dni, gdzie="https://x.substack.com/p/a"):
    return {"rodzaj": "komentarz", "kiedy": dni_temu(wiek_dni),
            "nasz_id": ident, "postawa": postawa, "udane": True, "gdzie": gdzie}


def pomiar(ident, odpowiedzi, wiek_dni):
    return {"rodzaj": "komentarz", "id": str(ident), "kiedy": dni_temu(0),
            "wystawione": dni_temu(wiek_dni), "odpowiedzi": odpowiedzi,
            "polubienia": 0, "wyswietlenia": 0, "subskrypcje": 0,
            "restacki": 0, "klikniecia_w_link": 0, "tekst": "x"}


def serie(postawa, ile, odpowiedzi_w_ilu, wiek_dni, od=0):
    """`ile` komentarzy jednej postawy, z czego `odpowiedzi_w_ilu` z odpowiedzia."""
    dz, po = [], []
    for i in range(ile):
        ident = "%s-%d" % (postawa[:3], od + i)
        dz.append(komentarz(ident, postawa, wiek_dni))
        po.append(pomiar(ident, 1 if i < odpowiedzi_w_ilu else 0, wiek_dni))
    return dz, po


print("=== 1. SWIEZE ZERO NIE JEST ZEREM ===")
# Komentarz sprzed godziny bez odpowiedzi nie dowodzi, ze postawa nie dziala.
dz, po = serie("CIEKAWOSC", 20, 0, wiek_dni=0)
zapisz(dz, po)
g = oszacowania.postawy_komentarza()
sprawdz("niedojrzale nie wchodza do rachunku",
        g["oszacowania"] == [], g["oszacowania"])
sprawdz("i widac ile ich odpadlo", g["straty"]["niedojrzale"] == 20, g["straty"])

print()
print("=== 2. DOJRZALE WCHODZA ===")
dz, po = serie("CIEKAWOSC", 20, 4, wiek_dni=10)
zapisz(dz, po)
g = oszacowania.postawy_komentarza()
o = g["oszacowania"][0]
sprawdz("policzone", o["mianownik"] == 20 and o["licznik"] == 4, o)
sprawdz("wartosc to udzial, nie suma", abs(o["wartosc"] - 0.2) < 1e-9, o["wartosc"])
sprawdz("przy 20 obserwacjach WIEM", o["wiem"] is True, o)

print()
print("=== 3. MALA PROBA -> NIE WIEM, Z PODANIEM PROGU ===")
dz, po = serie("KOREKTA", 3, 3, wiek_dni=10)
zapisz(dz, po)
o = oszacowania.postawy_komentarza()["oszacowania"][0]
sprawdz("trzy z trzech to nadal NIE WIEM", o["wiem"] is False, o)
sprawdz("wartosc mimo to policzona", o["wartosc"] == 1.0, o["wartosc"])
sprawdz("i powod nazywa prog", str(config.OSZACOWANIA_MIN_NA_WARIANT) in o["powod"],
        o["powod"])

print()
print("=== 4. DANE SPRZED PRZESTAWIENIA KONTA ODPADAJA ===")
# Pomiary sprzed 25 sierpnia 2026 opisuja publikacje o czym innym.
config.PRZESTAWIENIE_KONTA = (TERAZ - timedelta(days=20)).date().isoformat()
stare = (datetime.fromisoformat(config.PRZESTAWIENIE_KONTA)
         .replace(tzinfo=timezone.utc) - timedelta(days=5))
dz = [{"rodzaj": "komentarz", "kiedy": stare.isoformat(), "nasz_id": "old-1",
       "postawa": "CIEKAWOSC", "udane": True, "gdzie": "https://x.substack.com/p/a"}]
po = [{"rodzaj": "komentarz", "id": "old-1", "kiedy": dni_temu(0),
       "wystawione": stare.isoformat(), "odpowiedzi": 9}]
zapisz(dz, po)
g = oszacowania.postawy_komentarza()
sprawdz("stary wpis nie wchodzi", g["oszacowania"] == [], g["oszacowania"])
sprawdz("i jest policzony osobno",
        g["straty"]["sprzed_przestawienia"] == 1, g["straty"])

config.PRZESTAWIENIE_KONTA = "2020-01-01"

print()
print("=== 5. BRAK NUMERU I SENTYNELA -1 ===")
dz = [komentarz("", "CIEKAWOSC", 10), komentarz(-1, "CIEKAWOSC", 10),
      komentarz("real-1", "CIEKAWOSC", 10)]
po = [pomiar("real-1", 1, 10)]
zapisz(dz, po)
g = oszacowania.postawy_komentarza()
sprawdz("pusty numer to brak numeru", g["straty"]["bez_id"] >= 1, g["straty"])
sprawdz("-1 tez jest brakiem numeru, nie brakiem pomiaru",
        g["straty"]["bez_id"] == 2 and g["straty"]["bez_pomiaru"] == 0,
        g["straty"])

print()
print("=== 6. RACHUNEK STRAT SIE ZGADZA ===")
# Bez tego „1 na 13" nie mowi, czy trzynascie to calosc, czy resztka po
# odsianiu osiemdziesieciu.
dz, po = serie("MECHANIZM", 14, 2, wiek_dni=8)
dz2, po2 = serie("MECHANIZM", 5, 0, wiek_dni=0, od=100)
dz.append(komentarz("brak-postawy", "", 8))
zapisz(dz + dz2, po + po2)
g = oszacowania.postawy_komentarza()
policzone = sum(o["mianownik"] for o in g["oszacowania"])
sprawdz("policzone + odpadle = wszystkie wpisy",
        policzone + sum(g["straty"].values()) == len(dz + dz2),
        "%d + %d != %d" % (policzone, sum(g["straty"].values()), len(dz + dz2)))

print()
print("=== 7. TRYB OBSERWACYJNY NIE RUSZA ZADNEJ WAGI ===")
dz, po = serie("CIEKAWOSC", 20, 20, wiek_dni=10)
dz2, po2 = serie("KOREKTA", 20, 0, wiek_dni=10, od=50)
zapisz(dz + dz2, po + po2)
bylo = config.OSZACOWANIA_TRYB_OBSERWACYJNY
config.OSZACOWANIA_TRYB_OBSERWACYJNY = True
wagi = oszacowania.wagi_postaw()
redakcyjne = {k: float(v[0]) for k, v in config.POSTAWY_KOMENTARZA.items()}
sprawdz("wagi identyczne z redakcyjnymi", wagi == redakcyjne,
        {k: (wagi[k], redakcyjne[k]) for k in wagi if wagi[k] != redakcyjne[k]})

print()
print("=== 8. PO WLACZENIU: MODULACJA OGRANICZONA Z GORY I Z DOLU ===")
config.OSZACOWANIA_TRYB_OBSERWACYJNY = False
wagi = oszacowania.wagi_postaw()
m = config.OSZACOWANIA_MAKS_MODULACJA
podloga = config.OSZACOWANIA_PODLOGA_EKSPLORACJI
sprawdz("CIEKAWOSC (20/20) urosla", wagi["CIEKAWOSC"] > redakcyjne["CIEKAWOSC"])
sprawdz("ale nie wiecej niz o %.0f%%" % (m * 100),
        wagi["CIEKAWOSC"] <= redakcyjne["CIEKAWOSC"] * (1 + m) + 1e-9,
        wagi["CIEKAWOSC"])
sprawdz("KOREKTA (0/20) zmalala", wagi["KOREKTA"] < redakcyjne["KOREKTA"])
sprawdz("ale NIGDY do zera — podloga eksploracji",
        wagi["KOREKTA"] >= redakcyjne["KOREKTA"] * podloga - 1e-9,
        wagi["KOREKTA"])
sprawdz("wariant bez danych zostaje nietkniety",
        wagi["ROZSZERZENIE"] == redakcyjne["ROZSZERZENIE"], wagi["ROZSZERZENIE"])

print()
print("=== 9. DWA WARIANTY, O KTORYCH NIC NIE WIEMY -> WAGI BEZ ZMIAN ===")
dz, po = serie("CIEKAWOSC", 3, 3, wiek_dni=10)
dz2, po2 = serie("KOREKTA", 3, 0, wiek_dni=10, od=50)
zapisz(dz + dz2, po + po2)
wagi = oszacowania.wagi_postaw()
sprawdz("brak wiedzy nie jest zlym wynikiem", wagi == redakcyjne,
        {k: (wagi[k], redakcyjne[k]) for k in wagi if wagi[k] != redakcyjne[k]})
config.OSZACOWANIA_TRYB_OBSERWACYJNY = bylo

print()
print("=== 10. MIGAWKA JEST MALA I NIESIE NIEPEWNOSC ===")
# Migawka idzie do LINII dziennika przy decyzji. Bez niej za miesiac nie da sie
# ustalic, dlaczego bot wybral akurat te postawe: oszacowan nie przechowujemy.
dz, po = serie("CIEKAWOSC", 20, 5, wiek_dni=10)
zapisz(dz, po)
o = oszacowania.postawy_komentarza()["oszacowania"][0]
mig = oszacowania.migawka(o)
sprawdz("ma wariant, wartosc, n i `wiem`",
        set(mig) == {"wariant", "wartosc", "n", "wiem"}, mig)
sprawdz("miesci sie w linii dziennika",
        len(json.dumps(mig, ensure_ascii=False)) < 120, mig)

print()
print("=== 11. PUSTE DANE NIE WYWALAJA NICZEGO ===")
zapisz([], [])
try:
    g = oszacowania.wszystkie()
    # NAZWY PYTAN, NIE ICH LICZBA. Pierwsza wersja sprawdzala „len == 4"
    # i oblala przy dolozeniu pory dnia — czyli mierzyla, ile pytan bylo wczoraj,
    # zamiast tego, czy kazde umie odpowiedziec na pustych danych. Lista nazw
    # tez pilnuje kompletu, ale gdy sie zmieni, mowi CO sie zmienilo.
    nazwy = sorted(x["pytanie"] for x in g)
    sprawdz("komplet pytan mimo pustki",
            nazwy == sorted(["postawa -> odpowiedzi", "typ notki -> odpowiedzi",
                             "forma notki -> odpowiedzi", "host -> odpowiedzi",
                             "pora notki -> wyswietlenia"]), nazwy)
    sprawdz("kazde oddaje komplet kluczy",
            all(set(x) == {"pytanie", "wynik", "oszacowania", "straty"} for x in g),
            [set(x) for x in g])
    sprawdz("raport sie sklada", isinstance(oszacowania.raport(g), str))
    sprawdz("wagi wracaja redakcyjne", oszacowania.wagi_postaw() == redakcyjne)
except Exception as exc:                              # noqa: BLE001
    sprawdz("pustka nie wywala", False, "%s: %s" % (type(exc).__name__, exc))

print()
print("=== 12. USZKODZONA LINIA NIE KASUJE HISTORII ===")
dz, po = serie("CIEKAWOSC", 20, 4, wiek_dni=10)
zapisz(dz, po)
with io.open(KATALOG / "dziennik.jsonl", "a", encoding="utf-8") as f:
    f.write('{"rodzaj": "komentarz", "kiedy": "2026-0')     # SIGTERM w polowie
o = oszacowania.postawy_komentarza()["oszacowania"]
sprawdz("polowiczna linia pominieta, reszta policzona",
        bool(o) and o[0]["mianownik"] == 20, o)

print()
print("=== 13. RAPORT W PRZEBIEGU NIE MOZE ZABIC PRZEBIEGU ===")
# `run._summary` wola raport takze ze sciezki AWARYJNEJ, tuz przed `raise`.
# Gdyby raport rzucil stamtad, podmienilby prawdziwa przyczyne awarii na
# wlasna i zabralby jedyny slad tego, co sie naprawde stalo.
#
# Sprawdzane na DRZEWIE SKLADNI, nie po napisie: `import run` ciagnie
# playwrighta, ktorego na maszynie wlasciciela nie ma, wiec test wywolujacy
# `_summary` naprawde bylby testem obecnosci przegladarki.
import ast as _ast
_zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
_summary = next((w for w in _ast.walk(_ast.parse(_zrodlo))
                 if isinstance(w, _ast.FunctionDef) and w.name == "_summary"), None)
sprawdz("`_summary` istnieje", _summary is not None)
_wola_raport = [w for w in _ast.walk(_summary)
                if isinstance(w, _ast.Call)
                and getattr(w.func, "attr", "") == "raport"] if _summary else []
sprawdz("i wola raport oszacowan", bool(_wola_raport))
_pod_try = []
for _t in _ast.walk(_summary or _ast.Module(body=[], type_ignores=[])):
    if isinstance(_t, _ast.Try) and _t.handlers:
        _pod_try += [w for w in _ast.walk(_t)
                     if isinstance(w, _ast.Call)
                     and getattr(w.func, "attr", "") == "raport"]
sprawdz("wolanie stoi pod `try` z obsluga wyjatku",
        bool(_pod_try), "raport bez oslony podmienia przyczyne awarii")

print()
print("=" * 62)
print("ZDANE: %d    OBLANE: %d" % (zdane, oblane))
sys.exit(1 if oblane else 0)
