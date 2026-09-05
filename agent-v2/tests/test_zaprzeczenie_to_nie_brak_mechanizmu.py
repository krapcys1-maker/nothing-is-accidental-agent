# -*- coding: utf-8 -*-
"""Zdanie z „no one" moze opisywac mechanizm — i kod nie rozstrzyga tego sam.

CO SIE DZIALO (B3 z audytu researchu, potwierdzone dowodem z produkcji).
`bramka_kandydata` odrzucala `decision` zawierajaca „nobody", „no one",
„nothing" albo „nikt". Regula zadzialala w calej historii DOKLADNIE RAZ i byl
to falszywy alarm, ktory kosztowal mocny fakt na zawsze:

    fakt:     OpenAI agents used ordinary public wikis as a message board
              during a web-research benchmark, May-June 2026
    decision: „No one designed a wiki-message-board behaviour; it emerged from
              agents that had web access, and OpenAI shut the activity down
              around 22 June."

To JEST mechanizm — emergencja u agentow z dostepem do sieci — i do tego
nazwana decyzja z data. Odrzucenie jest OSTATECZNE, a poprawione wersje tego
samego faktu sa od tej pory pomijane jako powtorka odrzuconego. Jeden falszywy
alarm zamknal temat na stale.

Komentarz przy progu dlugosci mowil to zreszta wprost, na podstawie
wczesniejszego pomiaru: liste slow kluczowych probowano DWA RAZY i ani razu nie
rozdzielila mechanizmu od gestu. Dolozono ja mimo to, na przeczucie „dluga
wersja »nikogo tu nie ma« przejdzie przez prog" — przypadku, ktorego nie
zaobserwowano ani razu.

GDZIE PODZIALA SIE LUKA. Nie znikla, tylko zmienila wlasciciela. Sedzia banku
moze wyrzucic kandydata z kodem NO_MECHANISM, ale kod WETOWAL ten werdykt,
gdy `decision` mialo szesc slow i wiecej. Przy zdaniu z zaprzeczeniem sama
dlugosc nie rozstrzyga — tak samo dlugie jest „No one designed it; it emerged
from agents with web access" (mechanizm JEST) i „Nobody made this decision, it
is simply how the world works and nobody chose it" (mechanizmu NIE MA). Kod nie
umie ich rozdzielic, wiec w tym jednym przypadku nie wetuje modelu.

Poza zaprzeczeniem weto ZOSTAJE: tam pomiar dlugosci jest rzetelny.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zaprzeczenie_to_nie_brak_mechanizmu.py
"""
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


BAZA = {
    "fact": "OpenAI agents used public wikis as a message board during a benchmark.",
    "wrong_belief": "people assume agents only talk through the API",
    "actually": "they used an ordinary public wiki",
    "consequence": "your public wiki can carry machine traffic you never see",
    "url": "https://example.org/x", "source_date": "2026-09-01",
}
Z_MECHANIZMEM = ("No one designed a wiki-message-board behaviour; it emerged "
                 "from agents that had web access, and OpenAI shut the "
                 "activity down around 22 June.")
BEZ_MECHANIZMU = ("Nobody made this decision, it is simply how the world "
                  "works and nobody chose it")
GEST = "nikt, tak dziala fizyka"
ZWYKLY = ("Providers each choose their own serving stack: hardware, "
          "precision, batching policy and caching")

print("=== 1. BRAMKA NIE ODRZUCA JUZ ZA SAMO SLOWO ===")
sprawdz("mechanizm PO zaprzeczeniu przechodzi (przypadek z produkcji)",
        stages.bramka_kandydata(dict(BAZA, decision=Z_MECHANIZMEM))[0])
sprawdz("zwykly mechanizm nadal przechodzi",
        stages.bramka_kandydata(dict(BAZA, decision=ZWYKLY))[0])

print()
print("=== 2. PROG DLUGOSCI ZOSTAJE — GEST TO NADAL GEST ===")
_ok, _p = stages.bramka_kandydata(dict(BAZA, decision=GEST))
sprawdz("trzy slowa nadal odpadaja", not _ok, _p[:52])
sprawdz("i powodem jest gest, nie zaprzeczenie",
        "gestem" in _p, _p[:52])

print()
print("=== 3. LUKA PRZESZLA DO SEDZIEGO, NIE ZNIKNELA ===")
# Zdanie bez mechanizmu przechodzi teraz bramke — i to jest swiadome.
# Ma je moc usunac SEDZIA, ktoremu kod przestal wetowac przy zaprzeczeniu.
sprawdz("samo zaprzeczenie przechodzi bramke",
        stages.bramka_kandydata(dict(BAZA, decision=BEZ_MECHANIZMU))[0])

_wolania = []


def _sedzia_wyrzuca(purpose, system, user, **kw):
    _wolania.append(purpose)
    return ('{"kolejnosc": [0], "oceny": [{"id": 0, "wyrzuc": true,'
            ' "kod_wyrzucenia": "NO_MECHANISM",'
            ' "powod_wyrzucenia": "says what happened, not what makes it so",'
            ' "na_artykul": false, "dlaczego_mocny": "", "podobne_do": "",'
            ' "drugi_kat": "", "katy": []}]}')


_ORYG = {"call": stages.llm.call, "indeks": stages.wczytaj_indeks,
         "zapisz": stages._zapisz_indeks, "co": stages.co_zadzialalo}


def _z_decyzja(d):
    return [dict(BAZA, decision=d, status="nowy", kiedy="2099-01-01"),
            dict(BAZA, fact="drugi fakt zupelnie o czym innym",
                 decision=ZWYKLY, status="nowy", kiedy="2099-01-01")]


try:
    stages.llm.call = _sedzia_wyrzuca
    stages.co_zadzialalo = lambda ile=6: ""
    zapisane = {}
    stages._zapisz_indeks = lambda idx: zapisane.update({"idx": idx})

    # (a) ZAPRZECZENIE — sedzia MA moc wyrzucic.
    stages.wczytaj_indeks = lambda: _z_decyzja(BEZ_MECHANIZMU)
    stages.posortuj_bank(None, None)
    _st = [k.get("status") for k in zapisane.get("idx", [])]
    sprawdz("przy zaprzeczeniu werdykt sedziego STOI", "odrzucony" in _st, _st)

    # (b) BEZ ZAPRZECZENIA — kod nadal broni kandydata przed sedzia.
    zapisane.clear()
    stages.wczytaj_indeks = lambda: _z_decyzja(ZWYKLY)
    stages.posortuj_bank(None, None)
    _st2 = [k.get("status") for k in zapisane.get("idx", [])]
    sprawdz("bez zaprzeczenia weto DZIALA jak dotad",
            "odrzucony" not in _st2, _st2)
finally:
    stages.llm.call = _ORYG["call"]
    stages.wczytaj_indeks = _ORYG["indeks"]
    stages._zapisz_indeks = _ORYG["zapisz"]
    stages.co_zadzialalo = _ORYG["co"]

print()
print("=== 4. REGULA ZNIKNELA Z BRAMKI, A NIE ZOSTALA UKRYTA ===")
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("bramka nie oddaje juz powodu o zjawisku",
        "nikt tego nie sprawil — to zjawisko" not in _zr)
sprawdz("a weto sedziego pyta o zaprzeczenie",
        "not _zaprzeczenie" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
