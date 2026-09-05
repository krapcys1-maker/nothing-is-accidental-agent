# -*- coding: utf-8 -*-
"""Poprawiona wersja odrzuconego pomyslu ma prawo wejsc — ale nie kazda.

CO SIE DZIALO (B5 z audytu banku, potwierdzone przy naprawie B3).
`dopisz_kandydatow` buduje zbior `znane` z CALEGO indeksu, takze z wpisow
odrzuconych. Kandydat o tym samym kluczu byl wiec pomijany rowniez wtedy, gdy
nadeslana wersja naprawiala dokladnie to, na czym poprzednia odpadla.
Odrzucenie bylo ostateczne dla POMYSLU, a mialo byc ostateczne dla WADY.

ZMIERZONE 5 wrzesnia 2026. Fakt o agentach OpenAI uzywajacych publicznych
wiki jako skrzynki kontaktowej odpadl na blednej regule o slowie „no one".
Regule zdjalem tego samego dnia — ale fakt sam NIE WROCIL: kazda jego nowa
wersja byla pomijana jako powtorka wpisu lezacego w indeksie jako odrzucony.
Jedna zla decyzja zamykala temat na zawsze. Pozycje trzeba bylo naprawic
recznie w danych.

CZEGO TEN TEST PILNUJE — i granica jest tu wazniejsza niz sama poprawka:
  1. WRACAJA tylko odrzucenia BRAMKI, i tylko gdy nowa wersja ja przechodzi;
  2. powtorka, parowanie blizniakow, „juz o tym pisalismy" i werdykt sedziego
     zostaja OSTATECZNE — tam nie ma czego naprawiac w kandydacie, bo wada
     jest w jego relacji do tego, co juz mamy. Mieszanie tych dwoch rzeczy
     wpuscilo by powtorki do banku;
  3. niezmieniony martwy pomysl odpada dalej i nie kosztuje nic — bramka to
     czysty kod, bez modelu i bez sieci;
  4. wpis jest AKTUALIZOWANY W MIEJSCU, nie dokladany — inaczej indeks roslby
     o kazda probe, a kolejne sita uznalyby nowy wpis za powtorke samego siebie.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_poprawiony_wpis_wraca.py
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


DOBRY = {
    "fact": "OpenAI agents used ordinary public wikis as a message board during a benchmark.",
    "wrong_belief": "people assume agents only talk through the API",
    "actually": "they used an ordinary public wiki",
    "decision": "No one designed it; it emerged from agents that had web access and OpenAI shut it down",
    "consequence": "your public wiki can carry machine traffic you never see",
    "url": "https://example.org/wiki", "source_date": "2026-09-04",
}
# TA SAMA HISTORIA, ale wersja, ktora bramki NIE przejdzie — brak adresu.
UŁOMNY = dict(DOBRY, url="")

ZAPISANE: dict = {}


def _przygotuj(indeks):
    ZAPISANE.clear()
    stages.wczytaj_indeks = lambda: [dict(x) for x in indeks]
    stages._zapisz_indeks = lambda idx: ZAPISANE.update({"idx": idx})
    stages.opublikowane_teksty = lambda: []
    stages._powtorka_wg_modelu = lambda *a, **kw: (None, "")


def _wpis(status, powod, fakt=None):
    return dict(DOBRY, fact=fakt or DOBRY["fact"], status=status,
                powod=powod, kiedy="2026-09-01")


_ORYG = {n: getattr(stages, n) for n in
         ("wczytaj_indeks", "_zapisz_indeks", "opublikowane_teksty",
          "_powtorka_wg_modelu")}

try:
    print("=== 1. ODRZUCENIE BRAMKI WRACA, GDY WERSJA JEST POPRAWIONA ===")
    _przygotuj([_wpis("odrzucony", "brak zrodla")])
    lic = stages.dopisz_kandydatow([DOBRY])
    _idx = ZAPISANE.get("idx", [])
    # PIERWSZY WPIS ALBO PUSTY SLOWNIK. Bez tego test WYWALAL sie na
    # `_idx[0]`, gdy poprawki nie ma — a test, ktory pada zamiast zglosic
    # brak, nie mowi CO jest nie tak. Kontrdowod ma byc czytelny.
    _p = _idx[0] if _idx else {}
    sprawdz("policzony jako przyjety", lic.get("przyjete") == 1, lic)
    sprawdz("indeks NIE urosl — aktualizacja w miejscu",
            len(_idx) == 1, len(_idx))
    sprawdz("status wrocil na nowy", _p.get("status") == "nowy",
            _p.get("status"))
    sprawdz("powod zapisuje, co bylo wczesniej",
            "poprzednio: brak zrodla" in str(_p.get("powod")),
            _p.get("powod"))
    sprawdz("ranga zdjeta, sedzia oceni od nowa",
            bool(_p) and "ranga" not in _p, sorted(_p))

    print()
    print("=== 2. NIEZMIENIONY MARTWY POMYSL NADAL ODPADA ===")
    _przygotuj([_wpis("odrzucony", "brak zrodla")])
    lic2 = stages.dopisz_kandydatow([UŁOMNY])
    sprawdz("nie wchodzi", lic2.get("przyjete") == 0, lic2)
    sprawdz("i liczy sie jako znany, a nie nowy odrzucony",
            lic2.get("znane") == 1, lic2)
    sprawdz("indeks bez zmian", not ZAPISANE.get("idx")
            or len(ZAPISANE["idx"]) == 1, ZAPISANE.get("idx"))

    print()
    print("=== 3. POWTORKA I PAROWANIE ZOSTAJA OSTATECZNE ===")
    # Tu wada nie jest w kandydacie, tylko w jego relacji do tego, co mamy.
    # Wpuszczenie takiego wpisu wrocilo by powtorki do banku.
    for powod in ("powtorka innymi slowami: ten sam uklad co X",
                  "juz o tym pisalismy — notka: Y",
                  "parowanie: ta sama historia co Z",
                  "bank: It is a projection, not a checkable fact."):
        _przygotuj([_wpis("odrzucony", powod)])
        lic3 = stages.dopisz_kandydatow([DOBRY])
        sprawdz("NIE wraca po odrzuceniu %r" % powod.split(":")[0][:24],
                lic3.get("przyjete") == 0, lic3)

    print()
    print("=== 4. WPISY UZYTE I PRZETERMINOWANE NIE SA RUSZANE ===")
    for status in ("uzyty", "przeterminowany", "nowy"):
        _przygotuj([_wpis(status, "")])
        lic4 = stages.dopisz_kandydatow([DOBRY])
        sprawdz("status %r nadal blokuje powtorke" % status,
                lic4.get("przyjete") == 0, lic4)
finally:
    for n, f in _ORYG.items():
        setattr(stages, n, f)

print()
print("=== 5. KOD NAPRAWDE TAK ROBI ===")
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("lista odrzucen ostatecznych jest jawna",
        "ODRZUCENIA_OSTATECZNE" in _zr)
sprawdz("i powrot wymaga przejscia bramki",
        "bramka_kandydata(k) if _stary" in _zr)
sprawdz("aktualizacja idzie w miejsce, nie przez append",
        "_stary.update({" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
