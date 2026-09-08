# -*- coding: utf-8 -*-
"""Narzedzie do mierzenia skladu tematow NIE MA PRAWA zasmiecic banku.

`tests/platne/proba_tematow.py` wola PRAWDZIWE `stages.znajdz_ciekawostki`,
a ono normalnie dopisuje znalezione fakty do indeksu kandydatow
(`dopisz_kandydatow`, stages.py). Bez przechwycenia kazde sprawdzenie
zasmiecaloby zbior, ktory bada — faktami, ktore nie przeszly przez zadna
z bramek, przez ktore przechodza fakty produkcyjne.

TO NIE JEST HIPOTETYCZNE. 2 wrzesnia 2026 `tematy_przegrane.json` mial 400
wpisow, z czego 294 byly ATRAPAMI Z TESTOW — bo sciezka liczyla sie
z `config.DATA_DIR`, a testy jej nie przekierowywaly. Ten sam mechanizm,
inny plik.

DLACZEGO TEN TEST JEST DARMOWY, a narzedzie platne. Wlasnosc, ktora tu
sprawdzam — „zapis jest przechwycony" — nie wymaga zadnego wywolania modelu.
Sprawdzanie jej platnym uruchomieniem znaczyloby placic za dowiedzenie sie,
ze cos jest bezpieczne, PO tym jak sie to zrobilo.

BEZ PYTESTA, zero sieci, zero platnych wywolan. Z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_proba_tematow_nie_tyka_banku.py
"""
import ast
import pathlib
import sys

NARZEDZIE = pathlib.Path("agent-v2/tests/platne/proba_tematow.py")

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


print("=== 1. NARZEDZIE ISTNIEJE I LEZY TAM, GDZIE WOLNO PLACIC ===")
sprawdz("plik jest", NARZEDZIE.exists(), str(NARZEDZIE))
# `config._w_darmowym_tescie` puszcza platnosc TYLKO ze sciezki z „platne".
sprawdz("lezy w `tests/platne/`, wiec wykrywanie darmowego toru go przepuszcza",
        "platne" in NARZEDZIE.parts, NARZEDZIE.parts)
ZR = NARZEDZIE.read_text(encoding="utf-8")
DRZEWO = ast.parse(ZR)

print()
print("=== 2. ZAPIS DO BANKU JEST PRZECHWYCONY ===")
sprawdz("narzedzie podmienia `stages.dopisz_kandydatow`",
        "stages.dopisz_kandydatow = _nie_zapisuj" in ZR)
sprawdz("i przywraca oryginal w `finally`",
        "finally:" in ZR and "stages.dopisz_kandydatow = oryginal" in ZR)
# ZACHOWANIEM, NIE CZYTANIEM: wyciagamy zamiennik ze zrodla i wolamy go.
_ns = {}
for _w in ast.walk(DRZEWO):
    if isinstance(_w, ast.FunctionDef) and _w.name == "_nie_zapisuj":
        _mod = ast.Module(body=[_w], type_ignores=[])
        _kod = compile(ast.fix_missing_locations(_mod), "<zamiennik>", "exec")
        _zebrane = []
        _ns["zebrane"] = _zebrane
        exec(_kod, _ns)                                  # noqa: S102
        break
sprawdz("zamiennik `_nie_zapisuj` da sie wyjac ze zrodla",
        callable(_ns.get("_nie_zapisuj")))
if callable(_ns.get("_nie_zapisuj")):
    _wynik = _ns["_nie_zapisuj"]([{"fact": "atrapa"}], conn=None, run_id=0)
    sprawdz("nic nie dopisuje (`dopisane` = 0)",
            (_wynik or {}).get("dopisane") == 0, _wynik)
    sprawdz("melduje, ze to proba", (_wynik or {}).get("proba") is True, _wynik)
    sprawdz("i ZBIERA to, co mialo byc dopisane (zeby dalo sie policzyc)",
            _ns["zebrane"] and _ns["zebrane"][0][0]["fact"] == "atrapa",
            _ns["zebrane"])

print()
print("=== 3. ODCISK PLIKU BANKU PRZED I PO ===")
# Przechwycenie moze zawiesc na sciezce, ktorej nie przewidzialem. Odcisk
# jest jedynym sprawdzeniem, ktore tego nie zaklada.
sprawdz("liczy sha256 indeksu PRZED", "PRZED = odcisk(INDEKS)" in ZR)
sprawdz("i PO", "PO = odcisk(INDEKS)" in ZR)
sprawdz("porownuje je i mowi wprost", "bank NIETKNIETY" in ZR)
sprawdz("a przy roznicy KONCZY SIE BLEDEM, nie ostrzezeniem",
        "PLIK BANKU SIE ZMIENIL" in ZR and "return 1" in ZR)

print()
print("=== 4. NIC NIE WYCHODZI W SWIAT ===")
sprawdz("narzedzie nie siega po `browser`", "import browser" not in ZR)
for slowo in ("wystaw_notke", "wystaw_komentarz", "naprawde_wyslac", "--wyslij"):
    sprawdz("nie wola `%s`" % slowo, slowo not in ZR)
sprawdz("i melduje `opublikowanych: 0`", "opublikowanych: 0" in ZR)

print()
print("=== 5. PLATNOSC WYMAGA JAWNEJ ZGODY ===")
sprawdz("bez `--live` konczy sie bledem", 'p.error("Dodaj --live' in ZR)
sprawdz("i odmawia, gdy wykryje tor darmowy",
        "config.W_TESCIE" in ZR and "tor DARMOWY" in ZR)
sprawdz("przebieg idzie torem `test`, wiec nie zjada sufitu konta",
        'tryb="test"' in ZR)
sprawdz("ale koszt JEST raportowany", "koszt: %.4f USD" in ZR)

print()
print("=== 6. NARZEDZIE MOWI, KIEDY POMIAR JEST SLABY ===")
# Najgorszy przyrzad to taki, ktory milczy o wlasnych granicach.
sprawdz("ostrzega przy mniej niz dziesieciu probkach",
        "Do odroznienia 70%% od 50%% trzeba dziesieciu" in ZR
        or "trzeba dziesieciu" in ZR)
sprawdz("i gdy wszystkie szukania dostaly ten sam zestaw dziedzin",
        "TEN SAM zestaw dziedzin" in ZR)
sprawdz("zapisuje punkt odniesienia (bank 70/6 z 7 wrzesnia)",
        "branza 70%, swiat 6%" in ZR)

print()
print("=== 7. KLASYFIKATOR JEST JEDEN, WSPOLNY DLA PRZED I PO ===")
# Gdyby narzedzie liczylo inaczej niz punkt odniesienia, „przesuniecie" byloby
# roznica miedzy przyrzadami, a nie miedzy stanami.
sys.path.insert(0, str(NARZEDZIE.parent))
import importlib.util   # noqa: E402

_spec = importlib.util.spec_from_file_location("_pt", NARZEDZIE)
_pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pt)
sprawdz("`zaszereguj` istnieje", callable(getattr(_pt, "zaszereguj", None)))
PRZYPADKI = (
    ({"domain": "AI pricing", "fact": "tokens cost more"}, "BRANZA"),
    ({"domain": "a classroom", "fact": "students were tested by a teacher"}, "SWIAT"),
    ({"domain": "x", "fact": "a hospital bought GPU compute for patients"}, "OBA"),
    ({"domain": "x", "fact": "a pelican rode a bicycle"}, "ZADNE"),
)
for _f, _ocz in PRZYPADKI:
    _w = _pt.zaszereguj(_f)
    sprawdz("%-6s <- %s" % (_w, str(_f.get("fact"))[:44]), _w == _ocz,
            "oczekiwane %s" % _ocz)
sprawdz("pusty fakt nie wywala klasyfikatora",
        _pt.zaszereguj({}) == "ZADNE" and _pt.zaszereguj(None) == "ZADNE")

print()
print("=== 8. MIARA: CZY FAKT DOTYCZY DZIEDZINY ===")
# Zastapila podzial branza/swiat, bo tamten zgadzal sie z recznym oznaczeniem
# tylko w 64-71% — za malo, zeby na tym budowac. Ta miara nie pyta, CZY temat
# jest ludzki; pyta, czy model odpowiedzial na to, o co go zapytano.
sprawdz("`dotyczy` istnieje", callable(getattr(_pt, "dotyczy", None)))
sprawdz("`czestosci` istnieje", callable(getattr(_pt, "czestosci", None)))

# ZACHOWANIEM: budujemy maly korpus i sprawdzamy, ze miara ODROZNIA.
_KORPUS = [
    "A model was trained on tokens and the price per million fell.",
    "The classroom tablet flagged a pupil for cheating on an exam.",
    "A court in Delhi ruled on training data and copyright.",
    "The megawatt draw of one data centre in Ireland rose again.",
    "Benchmarks measure resemblance, not a resolved case.",
    "A nurse in a clinic waited for the screening result.",
]
_df, _n = _pt.czestosci(_KORPUS)
sprawdz("czestosci policzone z korpusu", _n == len(_KORPUS) and len(_df) > 10,
        (_n, len(_df)))
sprawdz("fakt o klasie DOTYCZY dziedziny o szkole",
        _pt.dotyczy("The classroom tablet flagged a pupil", "exams in the classroom",
                    _df, _n) is True)
sprawdz("i NIE dotyczy dziedziny o megawatach",
        _pt.dotyczy("The classroom tablet flagged a pupil",
                    "megawatt draw of a data centre", _df, _n) is False)
# KONTRDOWOD: gdyby miara patrzyla na slowa CZESTE, wszystko pasowaloby
# do wszystkiego. Slowo obecne w kazdym tekscie nie moze niczego wskazac.
_wspolny = ["the model does a thing"] * 8
_df2, _n2 = _pt.czestosci(_wspolny)
sprawdz("KONTRDOWOD: slowo obecne wszedzie nie jest kluczem",
        _pt.dotyczy("the model does a thing", "the model does a thing",
                    _df2, _n2) is None,
        "dziedzina bez rzadkich slow ma oddawac None, nie True")
sprawdz("dziedzina bez rzadkich slow oddaje None, a nie falszywe TAK",
        _pt.dotyczy("x", "", _df, _n) is None)

print()
print("=== 9. KALIBRACJA JEST ZAPISANA PRZY KODZIE ===")
# Miara bez skali nie mowi nic: 30% to duzo czy malo?
for co in ("60%", "14%", "3%"):
    sprawdz("zapisany punkt skali %s" % co, co in ZR, co)
sprawdz("i zrodlo kalibracji (zywy bank)", "SKALIBROWANE NA ZYWYM BANKU" in ZR)
sprawdz("zapisane, ze stary podzial mial 64-71% zgodnosci",
        "64-71%" in ZR)

print()
print("=== 10. FAKTY SA ZAPISYWANE, ZEBY NIE PLACIC DWA RAZY ===")
# Pierwsze uruchomienie ich nie zapisalo i cala analiza przepadla razem
# z 0,38 USD.
sprawdz("narzedzie zapisuje fakty na dysk", "proba_tematow_fakty.json" in ZR)
sprawdz("i mowi, gdzie", "kolejna analiza jest darmowa" in ZR)
sprawdz("kazdy fakt niesie, o jakie dziedziny pytano",
        "_dziedziny_zamowione" in ZR)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
