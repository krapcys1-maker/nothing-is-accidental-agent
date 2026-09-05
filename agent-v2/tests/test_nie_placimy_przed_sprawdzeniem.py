# -*- coding: utf-8 -*-
"""Trzy sita przed platna ocena celu — nie placimy za to, o czym juz wiemy.

Wszystkie trzy odpowiadaja na to samo pytanie: czy warto placic za ocene celu,
o ktorym z WLASNEGO dziennika juz wiadomo, ze nic z niego nie bedzie. Kazde
sprawdzenie czyta plik z dysku i nie rusza sieci ani modelu.

CO ZMIERZYLA ZEWNETRZNA ANALIZA SEGMENTU KOMENTARZY (5 wrzesnia 2026):

  * pod artykulami 47% prob odpada na „komentarze tylko dla placacych",
    a kazda zjada miejsce z przydzialu;
  * 15 celow okazuje sie „juz sie tam odezwalismy" dopiero PO napisaniu
    komentarza i PO sprawdzeniu faktow — czyli po trzech platnych wywolaniach;
  * 4 przebiegi z przydzialem ZERO i tak zaplacily za ocene celow.

STAN PRZED TA POPRAWKA. Sito platnych hostow (`hosty_tylko_dla_placacych`)
i sito hostow bez wejscia (`hosty_gdzie_komentarz_nie_wchodzi`) juz stalo przed
`wybierz_cele`. Brakowalo dwoch rzeczy: sita adresow, pod ktorymi juz stoimy,
oraz sprawdzenia przydzialu na wejsciu do bloku.

`dyskusje()` — komentarze pod cudzymi notkami — mial ten warunek przydzialu od
poczatku. `komentarze()` byl jedynym blokiem bez niego.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_nie_placimy_przed_sprawdzeniem.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

_KAT = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(_KAT)

import browser   # noqa: E402

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


print("=== 1. ADRESY, POD KTORYMI JUZ STOIMY — Z DZIENNIKA, ZA DARMO ===")
_wpisy = [
    {"rodzaj": "komentarz", "udane": True,
     "gdzie": "https://ktos.substack.com/p/pierwszy"},
    {"rodzaj": "komentarz", "udane": True,
     "gdzie": "https://ktos.substack.com/p/drugi?utm_source=x"},
    # NIEUDANY NIE LICZY SIE. Komentarz, ktory nie wszedl, nie stoi pod
    # tekstem — a cel, przy ktorym raz sie nie udalo, wolno rozwazyc znowu.
    {"rodzaj": "komentarz", "udane": False,
     "gdzie": "https://ktos.substack.com/p/nieudany"},
    {"rodzaj": "notka", "udane": True, "id": "1", "tekst": "nasza notka"},
]
browser.DZIENNIK.parent.mkdir(parents=True, exist_ok=True)
browser.DZIENNIK.write_text(
    "\n".join(json.dumps(w, ensure_ascii=False) for w in _wpisy) + "\n",
    encoding="utf-8")

_stali = browser.adresy_gdzie_juz_komentowalismy()
sprawdz("adres udanego komentarza jest zapamietany",
        "https://ktos.substack.com/p/pierwszy" in _stali, sorted(_stali))
sprawdz("znacznik w adresie nie robi z niego nowego celu",
        "https://ktos.substack.com/p/drugi" in _stali, sorted(_stali))
sprawdz("NIEUDANY komentarz nie blokuje ponownej proby",
        not any("nieudany" in a for a in _stali), sorted(_stali))
sprawdz("notka nie trafia miedzy adresy komentarzy",
        len(_stali) == 2, sorted(_stali))

# USZKODZONY DZIENNIK NIE MOZE ZATRZYMAC PRZEBIEGU. Sito ma byc oszczednoscia,
# nie nowym miejscem awarii: gdy nie da sie go zbudowac, przepuszczamy wszystko
# i placimy jak dawniej.
browser.DZIENNIK.write_text("{ to nie jest json\n", encoding="utf-8")
sprawdz("uszkodzony dziennik oddaje pusty zbior, nie wyjatek",
        browser.adresy_gdzie_juz_komentowalismy() == set())
browser.DZIENNIK.unlink(missing_ok=True)
sprawdz("brak dziennika tez nie wywala",
        browser.adresy_gdzie_juz_komentowalismy() == set())

print()
print("=== 2. SITO STOI PRZED PLATNA OCENA, NIE PO NIEJ ===")
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
i_sito = _run.find("adresy_gdzie_juz_komentowalismy()")
i_ocena = _run.find("cele = stages.wybierz_cele(conn, run_id, unikalne)")
sprawdz("sito adresow jest w run.py", i_sito > 0, i_sito)
sprawdz("i stoi PRZED wybierz_cele", 0 < i_sito < i_ocena, (i_sito, i_ocena))
# Dwa starsze sita tej samej rodziny maja tam stac dalej.
sprawdz("sito platnych hostow nadal przed ocena",
        0 < _run.find("hosty_tylko_dla_placacych()") < i_ocena)
sprawdz("sito hostow bez wejscia nadal przed ocena",
        0 < _run.find("hosty_gdzie_komentarz_nie_wchodzi()") < i_ocena)

print()
print("=== 3. PRZEGLADARKA ZOSTAJE JAKO DRUGA SIATKA ===")
# Dziennik nie wie o komentarzach wystawionych RECZNIE przez wlasciciela, wiec
# sprawdzenie w przegladarce nie moze zniknac razem z tym sitem.
_br = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
sprawdz("juz_sie_odezwalismy nadal wolane przy wystawianiu",
        "juz_sie_odezwalismy(page, url)" in _br)

print()
print("=== 4. PRZYDZIAL ZERO — NIE ZACZYNAMY WCALE ===")
sprawdz("komentarze() sprawdzaja przydzial na wejsciu",
        'if na_teraz["komentarze"] <= 0:' in _run)
i_przydzial = _run.find('if na_teraz["komentarze"] <= 0:')
sprawdz("i robia to PRZED ocena celow",
        0 < i_przydzial < i_ocena, (i_przydzial, i_ocena))
# `dyskusje()` mial ten warunek od poczatku — ma go zachowac.
sprawdz("dyskusje() nadal maja swoj warunek przydzialu",
        'if not na_teraz["komentarze"]:' in _run)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
