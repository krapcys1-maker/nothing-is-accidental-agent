# -*- coding: utf-8 -*-
"""Dwie zmiany z 3 wrzesnia 2026: dlugie okno dla WYJASNIENIA i zamowienia z banku.

DLACZEGO DLUGIE OKNO. Wlasciciel przeczytal opublikowana notke trzy razy i nie
wiedzial, o czym jest, po czym przepisal ja recznie — 158 slow przy naszym
suficie 64. Rozklad jego wersji: 28 slow na definicje terminu zwyklymi slowami,
65 na przylozenie jej do czytelnika, 24 na wersje porzadna, 35 na zalecenie.
W 64 slowa miesci sie DOKLADNIE JEDEN z tych czterech blokow, wiec model
zostawia teze i wycina wyjasnienie. Sufit podniesiony NIE dla wszystkich, tylko
dla jednej formy — reszta zostaje na 33-64, bo zaangazowanie mierzone publicznie
faworyzuje krotkie, a my nie mamy wlasnego pomiaru (na 34 notkach reakcje byly
plaskie: 3,2 przy otwarciu konkretnym, 3,0 przy abstrakcyjnym).

DLACZEGO ZAMOWIENIA. `posortuj_bank` prosi model o katy i o `czego_brakuje`
przy kazdym. Pole bylo zapisywane i liczone w logu, a czytane przez nikogo —
zmierzone na zywym przebiegu tego dnia: 18 katow przy 11 faktach, 9 z brakiem
materialu, zero realizacji. Ta sama klasa bledu co bramka bedaca prosba w
promptcie: sygnal wytworzony, oplacony i wyrzucony.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_dluga_notka_i_zamowienia.py
Zero wywolan modelu, zero sieci.
"""
import sys

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import stages  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. OKNO DLUGOSCI ZALEZY OD FORMY ===")
sprawdz("WYJASNIENIE dostaje dlugie okno",
        config.zakres_slow("WYJASNIENIE")
        == (config.NOTE_MIN_WORDS_DLUGA, config.NOTE_MAX_WORDS_DLUGA),
        config.zakres_slow("WYJASNIENIE"))
sprawdz("sufit dlugiej formy to 200 slow, jak ustawil wlasciciel",
        config.NOTE_MAX_WORDS_DLUGA == 200, config.NOTE_MAX_WORDS_DLUGA)
sprawdz("wersja wlasciciela (158 slow) MIESCI SIE w dlugim oknie",
        config.NOTE_MIN_WORDS_DLUGA <= 158 <= config.NOTE_MAX_WORDS_DLUGA)
sprawdz("i NIE miescila sie w zwyklym — to jest cala przyczyna zmiany",
        not (config.NOTE_MIN_WORDS <= 158 <= config.NOTE_MAX_WORDS))

print()
print("=== 2. KONTRDOWOD: POZOSTALE FORMY ZOSTAJA KROTKIE ===")
for forma in ("PROSTA", "SCENA", "LICZBA", "ZACZEP_I_KONKRET"):
    sprawdz("%s nadal 33-64" % forma,
            config.zakres_slow(forma) == (config.NOTE_MIN_WORDS,
                                          config.NOTE_MAX_WORDS),
            config.zakres_slow(forma))
sprawdz("nieznana forma tez dostaje krotkie okno, nie dlugie",
        config.zakres_slow("CZEGOS_TAKIEGO_NIE_MA")
        == (config.NOTE_MIN_WORDS, config.NOTE_MAX_WORDS))
sprawdz("brak formy (None) tez",
        config.zakres_slow(None) == (config.NOTE_MIN_WORDS,
                                     config.NOTE_MAX_WORDS))

print()
print("=== 3. DLUGA FORMA JEST W ROTACJI I MA OPIS ===")
sprawdz("WYJASNIENIE jest w NOTE_FORM_MIX", "WYJASNIENIE" in config.NOTE_FORM_MIX)
sprawdz("i ma wlasny opis w NOTE_FORMS", "WYJASNIENIE" in config.NOTE_FORMS)
_opis = config.NOTE_FORMS.get("WYJASNIENIE", "")
sprawdz("opis zada DEFINICJI terminu, bo to jej powod istnienia",
        "define" in _opis.lower(), _opis[:60])
sprawdz("opis ZAKAZUJE otwierania sporem, ktorego czytelnik nie slyszal",
        "I keep hearing" in _opis, _opis[:60])
sprawdz("jedna dluga forma na dziewiec — czyli okolo jednej notki na dobe",
        len(config.NOTE_FORM_MIX) == 9
        and sum(1 for f in config.NOTE_FORM_MIX if f in config.FORMY_DLUGIE) == 1,
        len(config.NOTE_FORM_MIX))

print()
print("=== 4. ZAMOWIENIA Z BANKU ===")
DZIS = config.DATA_PRZESTAWIENIA
BANK = [
    # fakt wolny, kat nieuzyty z brakiem -> zamowienie
    {"status": "nowy", "kiedy": DZIS, "wazny_do": "2099-01-01",
     "katy": [{"kat": "a", "lamie": "b", "czego_brakuje": "cena za milion tokenow",
               "uzyty": False}]},
    # ten sam brak drugi raz -> ma sie NIE powtorzyc
    {"status": "nowy", "kiedy": DZIS, "wazny_do": "2099-01-01",
     "katy": [{"kat": "c", "lamie": "d", "czego_brakuje": "cena za milion tokenow",
               "uzyty": False}]},
    # kat JUZ UZYTY -> to historia, nie zamowienie
    {"status": "nowy", "kiedy": DZIS, "wazny_do": "2099-01-01",
     "katy": [{"kat": "e", "lamie": "f", "czego_brakuje": "wynik testu bezpieczenstwa",
               "uzyty": True}]},
    # fakt JUZ ZUZYTY -> nie zamawiamy do niego niczego
    {"status": "uzyty", "kiedy": DZIS, "wazny_do": "2099-01-01",
     "katy": [{"kat": "g", "lamie": "h", "czego_brakuje": "liczba megawatow",
               "uzyty": False}]},
    # fakt PO TERMINIE -> tak samo
    {"status": "nowy", "kiedy": DZIS, "wazny_do": "2000-01-01",
     "katy": [{"kat": "i", "lamie": "j", "czego_brakuje": "data wejscia w zycie",
               "uzyty": False}]},
    # kat bez braku -> nie ma czego zamawiac
    {"status": "nowy", "kiedy": DZIS, "wazny_do": "2099-01-01",
     "katy": [{"kat": "k", "lamie": "l", "czego_brakuje": "", "uzyty": False}]},
]
_stary = stages.wczytaj_indeks
stages.wczytaj_indeks = lambda *a, **k: BANK
try:
    zam = stages.zamowienia_z_banku()
finally:
    stages.wczytaj_indeks = _stary

sprawdz("brak przy wolnym fakcie i nieuzytym kacie wchodzi",
        "cena za milion tokenow" in zam, zam)
sprawdz("ten sam brak NIE dubluje sie", zam.count("cena za milion tokenow") == 1, zam)
sprawdz("KONTRDOWOD: brak przy kacie juz uzytym nie wchodzi",
        "wynik testu bezpieczenstwa" not in zam, zam)
sprawdz("KONTRDOWOD: brak przy fakcie zuzytym nie wchodzi",
        "liczba megawatow" not in zam, zam)
sprawdz("KONTRDOWOD: brak przy fakcie po terminie nie wchodzi",
        "data wejscia w zycie" not in zam, zam)
sprawdz("pusty `czego_brakuje` nie tworzy pustej pozycji",
        all(z.strip() for z in zam), zam)
sprawdz("razem dokladnie jedno zamowienie z tego banku", len(zam) == 1, zam)

print()
print("=== 5. KONTRDOWOD: PUSTY BANK NIE ZAMAWIA NICZEGO ===")
stages.wczytaj_indeks = lambda *a, **k: []
try:
    sprawdz("pusty indeks -> pusta lista", stages.zamowienia_z_banku() == [])
    stages.wczytaj_indeks = lambda *a, **k: (_ for _ in ()).throw(OSError("dysk"))
    sprawdz("awaria odczytu indeksu nie wywraca szukania",
            stages.zamowienia_z_banku() == [])
finally:
    stages.wczytaj_indeks = _stary

print()
print("=== 6. PROMPT SZUKANIA MA GDZIE TO WSTAWIC ===")
import pathlib  # noqa: E402
_tresc = pathlib.Path("agent-v2/prompts/ciekawostki.md").read_text(encoding="utf-8")
sprawdz("prompt zawiera miejsce na zamowienia", "{zamowienia}" in _tresc)
sprawdz("i mowi, ze zamowienia idą PRZED siatka",
        "before you work the grid" in _tresc)
sprawdz("i zakazuje oddawania slabego faktu byle odhaczyc pozycje",
        "do not return a weak fact" in _tresc)

print()
print("=== 7. SKAUT WIDZI TAKZE BANK I WYDANE NOTKI ===")
# Zarzut wlasciciela: „skaut jeden temat przyniosl i jeszcze taki, ktory byl".
# Przyczyna: `recent_angles` oddaje wylacznie tematy ARTYKULOW, wiec bank notek
# i notki opublikowane byly dla skauta niewidzialne.
BANK2 = [
    {"status": "nowy", "kiedy": config.DATA_PRZESTAWIENIA,
     "fact": "Ireland gave 23 percent of metered electricity to data centres"},
    {"status": "uzyty", "kiedy": config.DATA_PRZESTAWIENIA,
     "fact": "TEGO JUZ UZYLISMY, wiec nie musi wracac na liste banku"},
    {"status": "nowy", "kiedy": "2020-01-01",
     "fact": "SPRZED PRZESTAWIENIA KONTA, inna epoka tematyczna"},
]
_stary_indeks = stages.wczytaj_indeks
_stare_teksty = stages.opublikowane_teksty
stages.wczytaj_indeks = lambda *a, **k: BANK2
_NOTKA_ATRAPA = ("Two paragraphs. That is how much of any answer I skip."
                 + chr(10) + chr(10) + "Drugi akapit.")
stages.opublikowane_teksty = lambda *a, **k: [_NOTKA_ATRAPA]
try:
    dom = stages._juz_w_domu()
finally:
    stages.wczytaj_indeks = _stary_indeks
    stages.opublikowane_teksty = _stare_teksty

sprawdz("wolny fakt z banku trafia do skauta",
        any("Ireland gave 23 percent" in d for d in dom), dom)
sprawdz("i jest oznaczony jako `bank:`",
        any(d.startswith("bank: ") for d in dom), dom)
sprawdz("opublikowana notka tez trafia",
        any("Two paragraphs" in d for d in dom), dom)
sprawdz("i jest oznaczona jako `wydane:`",
        any(d.startswith("wydane: ") for d in dom), dom)
sprawdz("z notki idzie TYLKO pierwszy wiersz, nie caly tekst",
        not any("Drugi akapit" in d for d in dom), dom)
sprawdz("KONTRDOWOD: fakt juz zuzyty nie wraca jako `bank:`",
        not any("TEGO JUZ UZYLISMY" in d for d in dom), dom)
sprawdz("KONTRDOWOD: fakt sprzed przestawienia konta nie wraca",
        not any("SPRZED PRZESTAWIENIA" in d for d in dom), dom)

_tresc_sk = pathlib.Path("agent-v2/prompts/skaut.md").read_text(encoding="utf-8")
sprawdz("prompt skauta ma miejsce na te liste", "{juz_mamy}" in _tresc_sk)
sprawdz("i mowi, ze to sa rzeczy JUZ oplacone",
        "already paid for" in _tresc_sk)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
