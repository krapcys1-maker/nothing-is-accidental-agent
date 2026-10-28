# -*- coding: utf-8 -*-
"""Wolne miejsca spod artykulow ida pod notki — po E14, w tym samym przebiegu.

PO CO. Regula zapisana PRZED ocena (13.10.2026, `docs/POMIAR_I_EKSPERYMENTY_2026-09-27.md`):
komentarze ponizej 75% planu nie z winy Substacka -> nadwyzka pod notkami. Bylo
70% w dobach 10-12.10, bo blok artykulow konczyl przebieg z „po 4 rundach:
0 celow", a pod notkami cele byly. W E14 (do 19.10) miejsce artykulu musialo
przepadac — inaczej rodzaj celu zalezalby od tego, gdzie akurat byly cele.

Test uruchamia PRAWDZIWE funkcje z `run.py` (wyjete z drzewa skladni, jak
w `test_nie_jak_nia.py`) na atrapach:

  1. `komentarze_z_rachunkiem` liczy wolne miejsca TYLKO gdy blok doszedl do konca;
  2. `nadwyzka_pod_notkami` rusza poza E14, przy wolnych miejscach i z czasem;
  3. `dyskusje(ile, nadwyzka)` bierze `ile` miejsc, pomija notki, pod ktorymi
     przebieg juz byl, a wpis w dzienniku dostaje `przydzial="nadwyzka"`.

BEZ PYTESTA, zero sieci, zero platnych wywolan. Uruchamiac z korzenia repo:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_nadwyzka_pod_notkami.py
"""
import ast
import contextlib
import io
import pathlib
import sys
import textwrap
from types import SimpleNamespace

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


ZRODLO = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
DRZEWO = ast.parse(ZRODLO)


def funkcja(nazwa, ns):
    """Wyjmuje zagniezdzona funkcje z `run.py` i wykonuje jej definicje w `ns`."""
    fn = next(w for w in ast.walk(DRZEWO) if isinstance(w, ast.FunctionDef) and w.name == nazwa)
    kod = textwrap.dedent(" " * fn.col_offset + ast.get_source_segment(ZRODLO, fn))
    exec(compile(kod, "run.py::" + nazwa, "exec"), ns)
    return ns[nazwa]


def cicho(f, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        wynik = f(*a, **k)
    return wynik, out.getvalue()


print("=== 1. RACHUNEK WOLNYCH MIEJSC PO ARTYKULACH ===")


def przebieg_artykulow(zrobil, wywal=False, artykuly=5):
    ns = {"przydzial": {"artykuly": artykuly, "notki": 2, "e14": False},
          "zrobione": {"komentarze": 3}, "po_artykulach": {}}

    def komentarze():
        ns["zrobione"]["komentarze"] += zrobil
        if wywal:
            raise RuntimeError("przegladarka padla")

    ns["komentarze"] = komentarze
    f = funkcja("komentarze_z_rachunkiem", ns)
    try:
        f()
    except RuntimeError:
        pass
    return ns["po_artykulach"]


sprawdz("5 miejsc, 1 komentarz (od stanu 3) -> 4 wolne", przebieg_artykulow(1) == {"wolne": 4},
        przebieg_artykulow(1))
sprawdz("wszystkie miejsca zapelnione -> 0 wolnych", przebieg_artykulow(5) == {"wolne": 0})
sprawdz("wiecej niz miejsc (dubel z kanalu) -> 0, nie liczba ujemna", przebieg_artykulow(7) == {"wolne": 0})
sprawdz("AWARIA BLOKU nie zostawia rachunku — nie przenosi sie pod notki",
        przebieg_artykulow(0, wywal=True) == {})

print()
print("=== 2. KIEDY NADWYZKA RUSZA ===")


def nadwyzka(wolne, e14=False, czas=True):
    wolania = []
    ns = {"przydzial": {"artykuly": 5, "notki": 2, "e14": e14},
          "po_artykulach": {} if wolne is None else {"wolne": wolne},
          "zostal_czas": lambda na_co="", potrzeba_s=0.0: czas,
          "dyskusje": lambda ile=None, nadwyzka=False: wolania.append((ile, nadwyzka))}
    f = funkcja("nadwyzka_pod_notkami", ns)
    _, out = cicho(f)
    return wolania, out


w, out = nadwyzka(4)
sprawdz("SEDNO: poza E14 4 wolne miejsca -> dyskusje(ile=4, nadwyzka=True)", w == [(4, True)], w)
sprawdz("i log mowi, ile przechodzi pod notki", "wolnych miejsc: 4" in out, out)
sprawdz("w E14 nadwyzka nie rusza (miejsce artykulu przepada, jak w planie E14)", nadwyzka(4, e14=True)[0] == [])
sprawdz("0 wolnych -> nic", nadwyzka(0)[0] == [])
sprawdz("bez rachunku (awaria albo blok nie ruszyl) -> nic", nadwyzka(None)[0] == [])
sprawdz("bez czasu na jeden komentarz z przerwa -> nic", nadwyzka(4, czas=False)[0] == [])

print()
print("=== 3. DRUGA RUNDA POD NOTKAMI ===")
NOTKI = [{"id": i, "tekst": "notka %d" % i, "autor": "A%d" % i, "reakcje": 9, "odpowiedzi": 2,
          "url": "https://substack.com/@a%d/note/c-%d" % (i, i), "data": "2026-10-19T10:00:00+00:00",
          "handle": "a%d" % i} for i in range(1, 7)]


def runda(ile, nadwyzka_, odwiedzone, przydzial_notki=2):
    wystawione = []

    def wystaw_odpowiedz(note_id, tekst, wyslij=True, kontekst=None, rodzaj=""):
        wystawione.append((note_id, dict(kontekst or {})))
        return {"wyslane": True}

    ns = {"przydzial": {"artykuly": 5, "notki": przydzial_notki, "e14": False},
          "odwiedzone_notki": odwiedzone,
          "kanal": SimpleNamespace(notki_z_kanalu=lambda: [dict(n) for n in NOTKI], szukaj_nowych=lambda: []),
          "_sito_celow": lambda kanal, cele, limit, notki: cele,
          "_zywe_najpierw": lambda kanal, cele: cele,
          "_wedlug_odpowiadalnosci": lambda kanal, cele, notki: cele,
          "dane_maniery": lambda cel, tekst, dzien=None: {},
          "limit_autorow": SimpleNamespace(odsiej=lambda c: c, zapisz=lambda c: None),
          "stages": SimpleNamespace(
              wybierz_cele=lambda conn, run_id, cele: cele,
              comment_on=lambda conn, run_id, cel: {"candidates": [{"comment": "Konkretna uwaga.",
                                                                    "safe_to_post": True}],
                                                   "otwarcie": "", "postawa": ""}),
          "conn": None, "run_id": 1, "wyslij": True, "rytm_stanu": {},
          "uloz_wedlug_swiezosci": lambda cele, klucz: cele,
          "zostal_czas": lambda *a, **k: True, "rytm": lambda *a, **k: True,
          "pamiec_do_celu": lambda uchwyt, adres: {"tekst": "", "ramie": ""},
          "browser": SimpleNamespace(wystaw_odpowiedz=wystaw_odpowiedz),
          "opis_celu": lambda cel: {}, "ramiona_komentarza": lambda cel, rodzaj, e14: {},
          "zrobione": {"komentarze": 0}}
    f = funkcja("dyskusje", ns)
    cicho(f) if ile is None else cicho(f, ile=ile, nadwyzka=nadwyzka_)
    return wystawione, ns["zrobione"]["komentarze"]


odwiedzone = set()
pierwsza, n1 = runda(None, False, odwiedzone)
sprawdz("pierwsza runda: miejsca z przydzialu (2)", [i for i, _ in pierwsza] == [1, 2] and n1 == 2, pierwsza)
sprawdz("pierwsza runda bez znacznika nadwyzki", all("przydzial" not in k for _, k in pierwsza))
druga, n2 = runda(3, True, odwiedzone)
sprawdz("SEDNO: druga runda bierze `ile` (3) i POMIJA notki z pierwszej", [i for i, _ in druga] == [3, 4, 5],
        [i for i, _ in druga])
sprawdz("wpis drugiej rundy ma `przydzial=\"nadwyzka\"`",
        all(k.get("przydzial") == "nadwyzka" for _, k in druga) and n2 == 3, druga)
sprawdz("odwiedzone notki zapamietane po obu rundach", odwiedzone == {"1", "2", "3", "4", "5"}, odwiedzone)
trzecia, _ = runda(5, True, odwiedzone)
sprawdz("gdy zostala jedna nieodwiedzona notka, runda bierze tylko ja", [i for i, _ in trzecia] == [6], trzecia)
pusta, n0 = runda(None, False, set(), przydzial_notki=0)
sprawdz("KONTRDOWOD: przydzial 0 i bez `ile` — blok nic nie robi, jak dotad", pusta == [] and n0 == 0)

print()
print("=== 4. PETLA BLOKOW ===")
sprawdz("petla wola `komentarze_z_rachunkiem`, nie gole `komentarze`",
        '("komentarze", komentarze_z_rachunkiem)' in ZRODLO
        and '("komentarze", komentarze)' not in ZRODLO)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
