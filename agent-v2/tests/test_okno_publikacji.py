# -*- coding: utf-8 -*-
"""Okno publikacji wycisza NOTKI, nie komentarze — i nie blokuje calego przebiegu.

CO SIE DZIALO 31 sierpnia 2026. Przebieg o 17:00 UTC znalazl DZIEWIEC celow
wartych komentarza — najlepszy wynik od przestawienia konta na AI, zaraz po
wymianie hasel wyszukiwania:

    [cele] warte komentarza: 9/23
     notki: 0
     komentarze: 0

Nie wystawil ANI JEDNEGO. Powod stal w logu linijke wyzej:

    okno publikacji: NIE — 13:00 u czytelnikow — najgorsze okno wg researchu

DWIE OSOBNE WADY W JEDNEJ LINIJCE.

1. `WORST_NOTE_HOURS = (12, 13)` ET blokowalo publikacje. Przebieg o 17:00 UTC
   to 13:00 ET, czyli DOKLADNIE ta godzina — wiec blokowal sie CODZIENNIE.
   Jeden z pieciu przebiegow, 20% dziennej zdolnosci, kazdego dnia.

   A regula stala na wlasnym zaprzeczeniu: komentarz w `config.py` mowi
   wprost, ze NASZE WLASNE ZRODLA SIE NIE ZGADZAJA — jedno wskazuje 6-8 ET,
   drugie 15-18 ET. Egzekwowalismy godziny, o ktorych sami piszemy, ze nie
   wiemy.

2. Okno wyciszalo KOMENTARZE razem z notkami. Jego wlasne uzasadnienie brzmi:
   „nowe tresci konkuruja o miejsce w kanale, a tekst wrzucony gdy publicznosc
   spi traci pierwsze godziny widocznosci". To jest prawda o NOTCE — naszej
   tresci na naszym profilu. Komentarz stoi pod CUDZYM tekstem i jego
   widocznosc zalezy od ruchu na tamtym poscie.

Decyzja wlasciciela: „nawet za cene wypuszczania poza oknami, bo tak to do
konca swiata bedziemy sie bawic z czekaniem na agenta i jego okno".

CZEGO TA POPRAWKA NIE RUSZA: progu snu. To inne twierdzenie i lepiej
uzasadnione — o 23:00 u czytelnikow nadal nie nadajemy.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo.
"""
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, "agent-v2")
import config  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def o(h, m=0, dzien=31):
    return datetime(2026, 8, dzien, h, m, tzinfo=timezone.utc)


print("=== 1. ZADEN Z PIECIU PRZEBIEGOW NIE JEST BLOKOWANY ===")
# To jest cala tresc naprawy: harmonogram ma dzialac w calosci.
for h, m in ((11, 20), (17, 0), (19, 20), (21, 30), (23, 40)):
    wolno, powod = config.pora_na_publikacje(o(h, m))
    sprawdz("  %02d:%02d UTC przechodzi" % (h, m), wolno, powod)

print()
print("=== 2. GODZINA 13:00 ET — TA, KTORA BLOKOWALA CODZIENNIE ===")
wolno, powod = config.pora_na_publikacje(o(17, 0))
sprawdz("nie blokuje", wolno, powod)
sprawdz("ale nadal jest odnotowana w powodzie",
        "slabsza" in powod, powod)
sprawdz("stala nadal istnieje jako zapis ustalen",
        config.WORST_NOTE_HOURS == (12, 13), config.WORST_NOTE_HOURS)

print()
print("=== 3. PROG SNU ZOSTAJE — TO INNE TWIERDZENIE ===")
# Poprawka mogla latwo znies wszystko. Nie ma.
for h, opis in ((3, "23:00 ET"), (5, "01:00 ET"), (9, "05:00 ET")):
    wolno, powod = config.pora_na_publikacje(o(h, 0, dzien=31))
    sprawdz("  %02d:00 UTC (%s) nadal wyciszone" % (h, opis),
            not wolno, powod)
sprawdz("i powod mowi o spiacej publicznosci",
        "spi" in config.pora_na_publikacje(o(3, 0))[1])

print()
print("=== 4. OKNO DOTYCZY NOTEK, NIE KOMENTARZY ===")
rp = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")

# MIERZONE NA DRZEWIE SKLADNI, NIE W OKNIE 1800 ZNAKOW.
#
# Stalo tu ciecie zrodla na sztywne okno od `wolno, powod = ...` i szukanie
# w nim napisow. Wada, ktorej ten plik pilnuje, blokowala JEDEN Z PIECIU
# PRZEBIEGOW CODZIENNIE — najdrozsza z opisanych w repozytorium — a wystarczylo
# zapisac ja inaczej (`na_teraz['komentarze']=0`, petla po kluczach) albo
# przesunac kod o 1800 znakow, zeby test zamilkl.
#
# Pytamy wiec o GALAZ, nie o odleglosc w znakach: znajdujemy `if`, ktorego
# warunek dotyczy `wolno`, i patrzymy, co ta galaz PRZYPISUJE.
import ast as _ast_o
_drzewo = _ast_o.parse(rp)

def _klucz(cel):
    """Nazwa klucza w `na_teraz[...]`, albo None."""
    if not isinstance(cel, _ast_o.Subscript):
        return None
    if getattr(cel.value, "id", "") != "na_teraz":
        return None
    s = cel.slice
    return s.value if isinstance(s, _ast_o.Constant) else None

_galezie = [n for n in _ast_o.walk(_drzewo) if isinstance(n, _ast_o.If)
            and any(getattr(x, "id", "") == "wolno" for x in _ast_o.walk(n.test))]
sprawdz("galaz okna publikacji istnieje w drzewie", len(_galezie) >= 1,
        len(_galezie))

_zerowane = set()
for _g in _galezie:
    for _n in _ast_o.walk(_g):
        if isinstance(_n, _ast_o.Assign):
            for _c in _n.targets:
                k = _klucz(_c)
                if k and isinstance(_n.value, _ast_o.Constant) and _n.value.value == 0:
                    _zerowane.add(k)
sprawdz("poza oknem notki ida na zero", "notki" in _zerowane, sorted(_zerowane))
sprawdz("a komentarze NIE sa zerowane", "komentarze" not in _zerowane,
        "zerowane w galezi okna: %s" % sorted(_zerowane))

# KONTRDOWOD: gdyby wykrywacz nie widzial przypisan, obie asercje przechodzilyby
# pusto. Sprawdzamy, ze widzi CHOC JEDNO.
sprawdz("wykrywacz naprawde widzi przypisania", bool(_zerowane), _zerowane)
sprawdz("i widac to w logu przebiegu",
        "komentarze IDA" in rp)

print()
print("=== 5. UZASADNIENIE JEST W KODZIE, NIE TYLKO W COMMICIE ===")
# Zeby ktos za miesiac nie „przywrocil" bramki jako oczywistej.
cfg = pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8")
sprawdz("kod podaje koszt blokady", "20% dziennej zdolnosci" in cfg)
sprawdz("i mowi, ze zrodla sie nie zgadzaly",
        "NASZE WLASNE ZRODLA SIE NIE ZGADZAJA" in cfg)
sprawdz("run.py tlumaczy, czemu komentarz to nie notka",
        "pod CUDZYM tekstem" in rp)

print()
print("=== 6. KONTRDOWOD: STARA REGULA MUSIALA TU BLOKOWAC ===")
# Gdyby 13:00 ET przechodzilo takze przed poprawka, nie bylo by czego naprawiac.
from zoneinfo import ZoneInfo  # noqa: E402
et = o(17, 0).astimezone(ZoneInfo(config.PUBLISH_TIMEZONE))
sprawdz("17:00 UTC to naprawde 13:00 ET", et.hour == 13, et.hour)
sprawdz("a 13 jest na liscie najgorszych godzin",
        et.hour in config.WORST_NOTE_HOURS)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
