# -*- coding: utf-8 -*-
"""Zapora wycina wade, a nie caly tekst. Cisza przestaje byc odpowiedzia.

POLECENIE WLASCICIELA z 9 wrzesnia 2026: „ma dzialac za wszelka cene, zadnego
blokowania notek komentarzy restackow czy artykulow, masz usunac wszelkie
blokady".

CO BYLO. Piec miejsc wyrzucalo CALY tekst z powodu JEDNEGO fragmentu:

    odpowiedz   wstrzykniecie w cudzym tekscie, na ktory odpowiadamy
    odpowiedz   zmyslone przezycie albo nienazwane badanie
    komentarz   wstrzykniecie
    komentarz   te same dwie podlogi z pamieci
    notka       wstrzykniecie

Zapory byly SLUSZNE. Bledna byla REAKCJA: cisza. W 30 dniach kosztowalo to
szesc notek, a w dzienniku zostawalo po nich slowo „ODRZUCONA".

CO JEST TERAZ. `stages.przepisz_bez_wady` w dwoch stopniach: model przepisuje
tekst bez wady, a gdy padnie albo wada dalej stoi — zdania tniemy kodem.
Sprawdzenie biegnie PO KAZDYM stopniu.

CZEGO TA ZMIANA NIE ROBI, i to jest granica, ktorej nie ruszam: nie wypuszcza
wady. „Bez blokad" znaczy „nie milcz", a nie „wypuszczaj cudze polecenia przez
nasze konto" ani „twierdz, ze konto czegos doswiadczylo". Tekst z wada nie ma
jak przejsc, bo sprawdzenie stoi po kazdym stopniu — zmienia sie tylko to, ze
zamiast kasowac caly tekst, oddajemy jego czysta czesc.

CZEGO TEN TEST PILNUJE:

  1. model przepisuje — wychodzi jego wersja
  2. model pada — kod tnie zdania i tekst NADAL wychodzi
  3. model oddaje tekst, w ktorym wada DALEJ stoi — kod tnie i sprawdza jeszcze raz
  4. tekst z wada NIE MA JAK przejsc na zewnatrz
  5. gdy po wycieciu nie zostaje nic — dopiero wtedy pustka
  6. pusty budzet i wylacznik leca na wylot
  7. zalegly artykul PROBUJE DALEJ po suficie prob, zamiast rezygnowac

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zadna_zapora_nie_milczy.py
"""
import json
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm      # noqa: E402
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
        print("  PADA  %s%s" % (opis, (" — " + dodatek) if dodatek else ""))


class AtrapaConn:
    def __getattr__(self, nazwa):
        raise AssertionError("kod siega po conn.%s — atrapa tego nie ma" % nazwa)


WZOR = re.compile(r"\bI saw it happen\b", re.I)
TEKST = ("The filter sits in front of the model. I saw it happen myself."
         " The permission is what is actually guarded.")


def wolaj(odpowiedz, wyjatek=None, conn=AtrapaConn()):
    oryginal = llm.call

    def podstawiony(purpose, system, prompt, **kw):
        if wyjatek:
            raise wyjatek("proba")
        return json.dumps(odpowiedz)

    llm.call = podstawiony
    try:
        return stages.przepisz_bez_wady(
            conn, 1, TEKST,
            wada="a claim of personal experience we do not have",
            sprawdz=lambda t: bool(WZOR.search(t)),
            wzorzec_awaryjny=WZOR)
    finally:
        llm.call = oryginal


print("=== 1. model przepisuje — wychodzi jego wersja ===")
CZYSTA = "The filter sits in front of the model. The permission is guarded."
wynik = wolaj({"text": CZYSTA, "co_zmienione": "wycialem zdanie"})
sprawdz("wychodzi wersja modelu", wynik == CZYSTA, repr(wynik))
sprawdz("i nie nosi juz wady", not WZOR.search(wynik or ""))

print()
print("=== 2. model pada — kod tnie zdania, tekst NADAL wychodzi ===")
wynik = wolaj({}, wyjatek=RuntimeError)
sprawdz("cos wyszlo mimo bledu modelu", bool(wynik), repr(wynik))
sprawdz("bez wady", wynik and not WZOR.search(wynik))
sprawdz("i reszta zdan zostala", wynik and "permission" in wynik, repr(wynik))

print()
print("=== 3. model oddaje tekst, w ktorym wada DALEJ stoi ===")
wynik = wolaj({"text": TEKST})
sprawdz("kod dociul sam", bool(wynik) and not WZOR.search(wynik), repr(wynik))

print()
print("=== 4. tekst z wada NIE MA JAK przejsc ===")
# Najwazniejsza asercja w tym pliku. „Bez blokad" nie znaczy „bez sprawdzen".
for _odp in ({"text": TEKST}, {"text": ""}, {}):
    _w = wolaj(_odp)
    sprawdz("wynik dla %r nie nosi wady" % str(_odp)[:28],
            not WZOR.search(_w or ""), repr(_w))

print()
print("=== 5. gdy po wycieciu nie zostaje nic — dopiero wtedy pustka ===")
oryginal = llm.call
llm.call = lambda *a, **k: json.dumps({"text": ""})
try:
    pusto = stages.przepisz_bez_wady(
        AtrapaConn(), 1, "I saw it happen.",
        wada="x", sprawdz=lambda t: bool(WZOR.search(t)),
        wzorzec_awaryjny=WZOR)
finally:
    llm.call = oryginal
sprawdz("jedno zdanie, ktore CALE bylo wada, zostawia pustke", pusto == "",
        repr(pusto))

print()
print("=== 6. pusty budzet i wylacznik leca na wylot ===")
for _klasa, _opis in ((llm.BudgetExceeded, "pusty budzet"),
                      (llm.PreflightFailed, "wylacznik")):
    try:
        wolaj({}, wyjatek=_klasa)
        _co = "POLKNIETE"
    except _klasa:
        _co = "leci dalej"
    except Exception as _e:                                   # noqa: BLE001
        _co = "inny wyjatek: %s" % type(_e).__name__
    sprawdz("%s leci na wylot" % _opis, _co == "leci dalej", _co)

print()
print("=== 7. piec miejsc naprawde siega po wyciecie ===")
_st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("wywolan `przepisz_bez_wady` jest piec",
        _st.count("przepisz_bez_wady(\n") >= 5,
        "znalazlem %d" % _st.count("przepisz_bez_wady(\n"))
for _stary in ('print(f"  [odpowiedź {i + 1}] ODRZUCONA: {powod}", flush=True)\n'
               '                candidates.append(data)',
               'data["reply"] = None\n                    print(f"    ODRZUCONA'
               ' PRZED WYSLANIEM: {nazwa}"'):
    sprawdz("stara sciezka kasujaca caly tekst zniknela (%s...)" % _stary[:34],
            _stary not in _st)

print()
print("=== 8. zalegly artykul probuje dalej, a nie rezygnuje ===")
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("po suficie prob alarmuje I PROBUJE DALEJ",
        "alarmuje\"\n                  \" i PROBUJE DALEJ" in _run
        or "PROBUJE DALEJ" in _run)
sprawdz("i nie ma juz rezygnacji z tekstu",
        "PRZESTAJE\"\n                  \" PROBOWAC" not in _run)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
