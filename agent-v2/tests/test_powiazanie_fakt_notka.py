# -*- coding: utf-8 -*-
"""Da sie powiedziec, ktory wpis banku stal sie ktora notka.

CO SIE DZIALO (B6 z audytu banku — i cos wazniejszego, co wyszlo przy probie
jego zmierzenia).

Audyt zarzuca, ze `wez_kandydatow` znaczy kandydata jako `uzyty` PRZED
napisaniem, wiec przerwany przebieg zostawia material spalony. Probowalem to
policzyc: porownanie statusu w indeksie z `zuzyte_fakty.json` dalo 46 z 62
(74%) faktow „uzytych bez publikacji".

TEN POMIAR BYL NIERZETELNY I TO JEST GLOWNE USTALENIE. Sprawdzenie tresci
w wydanych notkach odnalazlo 24 z tych 46 — czyli one WYSZLY, tylko odhaczenie
ich nie dopasowalo. Liczenie w druga strone tez nie dziala: `zuzyte_fakty.json`
ma 81 wpisow, indeks 126, a wspolnych kluczy jest 21, bo wiekszosc notek stoi
na materiale ze SWIEZEGO szukania, ktory do indeksu nie trafil.

Kod sam to zreszta zapisal przy polu `fakt_ranga`: „bez tego trzeba parowac
notke z faktem po nakladaniu sie slow, co dalo 14 par z 46 notek". Ranga byla
polowicznym rozwiazaniem — mowi, JAK OCENIONY byl fakt, ale nie KTORY to fakt.

Wiec zanim naprawie rezerwacje, naprawiam PRZYRZAD: powiazanie zapisane po obu
stronach. Dziennik notki dostaje `fakt_klucz`, wpis indeksu dostaje numer
notki. Bez tego kazdy wniosek o spalonym materiale jest zgadywaniem — a ja
zgadlem juz raz i wyszlo 74% zamiast prawdy.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_powiazanie_fakt_notka.py
"""
import inspect
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


FAKT = {"fact": "OpenAI cut the cached input price by half on 4 September 2026."}

print("=== 1. INDEKS ZAPAMIETUJE, KTORA NOTKA Z NIEGO POWSTALA ===")
stages._zapisz_indeks([
    dict(FAKT, status="nowy", kiedy="2099-01-01"),
    {"fact": "a completely different fact about something else",
     "status": "nowy", "kiedy": "2099-01-01"},
])
ile = stages.oznacz_uzyty(FAKT, "330206949")
po = stages.wczytaj_indeks()
sprawdz("oznaczony dokladnie jeden wpis", ile == 1, ile)
sprawdz("status uzyty", po[0].get("status") == "uzyty", po[0].get("status"))
sprawdz("numer notki zapisany",
        po[0].get("wydany_jako") == "330206949", po[0].get("wydany_jako"))
sprawdz("sasiedni wpis nietkniety",
        po[1].get("status") == "nowy" and "wydany_jako" not in po[1], po[1])

print()
print("=== 2. BEZ NUMERU NIC SIE NIE PSUJE ===")
# Numer notki bywa nieodczytany — `browser` mowi wtedy wprost „NIE ODCZYTANY".
# Odhaczenie faktu ma dzialac dalej, tylko bez powiazania.
stages._zapisz_indeks([dict(FAKT, status="nowy", kiedy="2099-01-01")])
sprawdz("odhacza mimo braku numeru",
        stages.oznacz_uzyty(FAKT) == 1)
_p = stages.wczytaj_indeks()[0]
sprawdz("i nie dopisuje pustego powiazania",
        "wydany_jako" not in _p, sorted(_p))

print()
print("=== 3. DRUGA STRONA: DZIENNIK NOTKI NIESIE ODCISK FAKTU ===")
import browser   # noqa: E402

sprawdz("wystaw_notke przyjmuje fakt_klucz",
        "fakt_klucz" in inspect.signature(browser.wystaw_notke).parameters)
_br = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
sprawdz("i oddaje go do dziennika w OBU miejscach zapisu",
        _br.count("fakt_klucz=fakt_klucz") == 2,
        _br.count("fakt_klucz=fakt_klucz"))

_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("run.py liczy klucz z tego samego faktu",
        "fakt_klucz=stages._klucz_faktu(" in _run)
sprawdz("i podaje numer notki do indeksu",
        'stages.oznacz_uzyty(n["fakt"], wynik.get("id"))' in _run)

print()
print("=== 4. OBIE STRONY UZYWAJA TEJ SAMEJ FUNKCJI KLUCZA ===")
# Dwa sposoby liczenia odcisku rozjechalyby sie tak samo, jak rozjechal sie
# status z `zuzyte_fakty.json`.
sprawdz("klucz z dziennika i z indeksu to ta sama funkcja",
        "_klucz_faktu" in _run
        and "_klucz_faktu" in inspect.getsource(stages.oznacz_uzyty))
sprawdz("i jest odporny na przestawienie slow",
        stages._klucz_faktu("Acme released Model 5.1 today.")
        == stages._klucz_faktu("Model 5.1 released Acme today."))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
