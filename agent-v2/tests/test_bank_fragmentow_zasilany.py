# -*- coding: utf-8 -*-
"""Wtorkowy artykul odklada nieuzyte fragmenty, a nie wyrzuca je.

CO ZGLASZA AUDYT (Q5). `card["unused_evidence"]` ustawia tylko `run.py`.
`artykul_z_puli._napisz_i_zapisz` zapisuje karte bez tego pola, wiec
`stages.bank_fragmentow` jest zawsze pusty — galaz DOLOZ konczy sie na „bank
pusty", bibliotekarz nigdy nie rusza.

CO ZMIERZYLEM NA PRODUKCJI, ZANIM COKOLWIEK TKNALEM. Odciecie jest ostre co do
artykulu:

    artykul  1-8   (18-25 sierpnia)   bank = 5,6,3,6,1,7,3,9   razem 299 fragmentow
    artykul  9-15  (25 sierp-1 wrzes) bank = BRAK x7           razem 0

Kazda z tych siedmiu kart niosla 7-8 zrodel. Czyli nie „bank bywa pusty", tylko
SIEDEM ARTYKULOW Z RZEDU WYRZUCILO CALY OPLACONY MATERIAL — dokladnie odkad
wtorkowy artykul przeszedl na `artykul_z_puli`.

PRZYCZYNA BYLA W SYGNATURZE, NIE W LOGICE. `_napisz_i_zapisz(conn, run_id,
brief, card)` nie dostawalo `evidence`, wiec nie mialo z czego zlozyc pola.
Czytelnik dzialal caly czas i czytal pustke — to jest ten sam ksztalt co
„prosba w prompcie nie jest bramka", tylko odwrocony: kod BYL, brakowalo mu
danych.

DWIE RZECZY, KTORYCH AUDYT NIE MOGL WIEDZIEC, A KTORE ZMIENIAJA WNIOSEK.

1. „Bank jest zawsze pusty" NIE JEST prawda o naszym drzewie. Bank ma 299
   fragmentow — te z artykulow 1-8, ktore szly przez `run.py`. Nasza odmiana
   usterki to nie pustka, tylko ZAMROZENIE: bank stanal 25 sierpnia i od tego
   dnia nie urosl ani o jeden wpis.

2. KONTRDOWOD SAMEGO AUDYTU TRAFIA, i trzeba to powiedziec wprost: bank czyta
   WYLACZNIE galaz `werdykt == "DOLOZ"`. Na produkcji, przez 15 artykulow,
   DOLOZ nie padl ANI RAZU (4x PISZ, 11x brak oceny). Wiec ta naprawa nie
   kupuje dzisiaj niczego widocznego. Kosztuje zero i zatrzymuje wyciek —
   ale kto bedzie mierzyl jej skutek po tekstach, nie zobaczy nic, bo miejsce,
   ktore z banku korzysta, jeszcze sie nie otworzylo. Osobne pytanie, czy
   „DOLOZ nigdy" to zdrowy rozklad, czy druga usterka — nie tutaj.

CZEGO TEN TEST PILNUJE:
  1. gdy `evidence` jest podane — pole powstaje, w ksztalcie ktory czyta
     `bank_fragmentow` (url / publisher / excerpts / numbers);
  2. gdy NIE jest (`--z-karty`) — pole zostaje NIETKNIETE, bo karta z dysku
     niesie juz swoje i dopisanie pustki by je skasowalo;
  3. normalna sciezka faktycznie je podaje — bo tu byla usterka;
  4. przejscie od konca: zapisana karta jest czytelna dla `bank_fragmentow`.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_bank_fragmentow_zasilany.py
"""
import inspect
import json
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import artykul_z_puli   # noqa: E402
import stages           # noqa: E402

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


EVIDENCE = [
    {"url": "https://a.example/raport", "publisher": "A Press",
     "excerpts": ["A" * 80, "B" * 90], "numbers": ["12 units"]},
    {"url": "https://b.example/rule", "publisher": None,
     "excerpts": ["C" * 70], "numbers": []},
    {"url": "https://c.example/x"},          # zrodlo kalekie — nie moze wywalic
]

print("=== 1. SYGNATURA W OGOLE PRZYJMUJE MATERIAL ===")
_par = inspect.signature(artykul_z_puli._napisz_i_zapisz).parameters
sprawdz("_napisz_i_zapisz przyjmuje evidence", "evidence" in _par)
sprawdz("i jest nieobowiazkowe (--z-karty wchodzi bez niego)",
        _par["evidence"].default is None if "evidence" in _par else False)

print()
print("=== 2. NORMALNA SCIEZKA NAPRAWDE JE PODAJE ===")
# Tu byla cala usterka: funkcja bez argumentu nie ma z czego zlozyc pola.
_zr = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
sprawdz("wywolanie normalnej sciezki podaje evidence",
        "_napisz_i_zapisz(conn, run_id, brief, card, evidence)" in _zr)
sprawdz("sciezka --z-karty NIE podaje (i tak ma byc)",
        "_napisz_i_zapisz(conn, run_id, brief, card)" in _zr)

print()
print("=== 3. POLE POWSTAJE W KSZTALCIE, KTORY CZYTA BANK ===")
# Odtwarzam sam zapis pola, bo `_napisz_i_zapisz` w calosci chodzi po modelach.
# WYCINAM KOD ZE ZRODLA — i pilnuje wycinka, bo to ten sam ksztalt, w ktorym
# juz cztery razy „test przechodzil, nie sprawdzajac niczego". Zly split dalby
# pusty blok, ktory wykona sie bez bledu i nie ustawi nic.
sprawdz("kotwica wycinka jest jednoznaczna", _zr.count("if evidence:") == 1,
        _zr.count("if evidence:"))
if _zr.count("if evidence:") != 1:
    # Konczy diagnoza, nie sladem stosu. Na kodzie sprzed naprawy tu wlasnie
    # test staje — i to jest odtworzony kontrdowod, nie awaria testu.
    print()
    print("  (zapis pola nie istnieje — reszty nie ma czego sprawdzac)")
    print()
    print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
    sys.exit(1)
_kod = _zr.split("if evidence:")[1].split("print(")[0]
sprawdz("wycinek naprawde zawiera zapis pola",
        "unused_evidence" in _kod and "excerpts" in _kod, len(_kod))
karta = {}
exec(compile("card = {}\nevidence = EV\nif evidence:" + _kod, "<zapis>", "exec"),
     {"EV": EVIDENCE}, karta)
ue = karta["card"].get("unused_evidence")
sprawdz("pole powstalo", isinstance(ue, list), type(ue))
sprawdz("z kazdego zrodla po wpisie", len(ue or []) == 3, len(ue or []))
sprawdz("kalekie zrodlo nie wywala zapisu",
        (ue or [{}])[-1].get("excerpts") == [], (ue or [{}])[-1])
sprawdz("klucze zgodne z czytelnikiem",
        all(set(w) == {"url", "publisher", "excerpts", "numbers"} for w in ue or []),
        sorted((ue or [{}])[0]))

print()
print("=== 4. PRZEJSCIE OD KONCA: BANK TO ODCZYTA ===")
# Dowod, ze zapis i odczyt sie spotykaja — bo dotad NIE spotykaly sie wcale.
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT,"
             " evidence TEXT, created_at TEXT)")
conn.execute("INSERT INTO articles (title, evidence, created_at) VALUES (?,?,?)",
             ("Proba", json.dumps(karta["card"]), "2026-09-05 12:00:00"))
bank = stages.bank_fragmentow(conn)
sprawdz("bank widzi fragmenty", len(bank) == 3, len(bank))
sprawdz("ogryzki ponizej 60 znakow odpadaja",
        all(len(f["text"]) >= 60 for f in bank))
sprawdz("kazdy fragment niesie zrodlo",
        all(f["url"] for f in bank), [f["url"] for f in bank])
sprawdz("i nazwe wydawcy albo host",
        all(f["publisher"] for f in bank), [f["publisher"] for f in bank])

print()
print("=== 5. BEZ MATERIALU POLE ZOSTAJE NIETKNIETE ===")
# `--z-karty` wczytuje karte z dysku. Gdyby zapis szedl bezwarunkowo, pusta
# lista skasowalaby to, co karta juz niosla.
karta2 = {}
exec(compile("card = {'unused_evidence': [{'url': 'stare'}]}\nevidence = None\n"
             "if evidence:" + _kod, "<zapis>", "exec"), {}, karta2)
sprawdz("stare pole przetrwalo brak argumentu",
        karta2["card"]["unused_evidence"] == [{"url": "stare"}],
        karta2["card"].get("unused_evidence"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
