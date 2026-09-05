# -*- coding: utf-8 -*-
"""Alarm liczy reakcje po CELU, nie po typie zdarzenia.

CO SIE STALO. Komentarz pod CUDZA NOTKA dostaje u Substacka numer z tej samej
przestrzeni `c-`, co nasza notka — wiec jego polubienie przychodzi jako
`note_like`, a odpowiedz jako `note_reply`. `alarm.py` liczyl kanaly po tym
napisie i dopisywal nasze komentarze do kanalu notek.

ZMIERZONE 5 wrzesnia 2026 na produkcyjnym dzienniku, od przestawienia konta:
z 214 reakcji 26 typu `note_*` stoi pod NASZYM KOMENTARZEM. Roznica w tym, co
z tego wychodzi:

    po typie:    notka 2,84/szt   komentarz 0,13/szt   -> notka 22x lepsza
    po numerze:  notka 1,27/szt   komentarz 0,29/szt   -> notka 4,4x

Na podstawie tej pierwszej liczby powstalo zlecenie analizy z teza, ze
komentarze sa 22 razy gorsze od notek. Przeszacowanie pieciokrotne.

`wzajemnosc.kanal_reakcji` robi to poprawnie od 2 wrzesnia i ma o tym wlasny
komentarz z wlasnym pomiarem. Alarm z tego nie korzystal — czyli poprawka
istniala w jednym miejscu, a przyrzad, ktory czyta wlasciciel, dalej klamal.

CZEGO TEN TEST PILNUJE:
  1. komentarz pod cudza notka liczy sie jako komentarz, mimo typu `note_*`;
  2. droga zapasowa (reakcja bez podpiecia) nadal dziala i nie wywala alarmu;
  3. alarm mowi, ILE reakcji udalo sie podpiac — zeby liczba nie udawala
     dokladniejszej, niz jest.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_kanal_nie_z_typu.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import wzajemnosc as wz   # noqa: E402

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


print("=== 1. KOMENTARZ POD CUDZA NOTKA TO KOMENTARZ, NIE NOTKA ===")
POZYCJE = {
    "111": {"rodzaj": "notka", "kiedy": None, "gdzie": ""},
    "222": {"rodzaj": "komentarz", "kiedy": None,
            "gdzie": "https://substack.com/@ktos/note/c-999"},
    "333": {"rodzaj": "komentarz", "kiedy": None,
            "gdzie": "https://ktos.substack.com/p/artykul"},
}
# TO JEST SEDNO: typ mowi `note_like`, bo komentarz pod notka ma numer z tej
# samej przestrzeni. Cel mowi, ze to nasz komentarz.
sprawdz("polubienie NASZEJ notki -> notka",
        wz.kanal_reakcji({"typ": "note_like", "czego": "111"}, POZYCJE)
        == "notka")
sprawdz("polubienie z typem note_like pod NASZYM komentarzem -> komentarz",
        wz.kanal_reakcji({"typ": "note_like", "czego": "222"}, POZYCJE)
        .startswith("komentarz"),
        wz.kanal_reakcji({"typ": "note_like", "czego": "222"}, POZYCJE))
sprawdz("i rozroznia komentarz pod notka od komentarza pod artykulem",
        wz.kanal_reakcji({"typ": "note_like", "czego": "222"}, POZYCJE)
        != wz.kanal_reakcji({"typ": "comment_like", "czego": "333"}, POZYCJE))

print()
print("=== 2. DROGA ZAPASOWA ZOSTAJE ===")
# Czesc notek i komentarzy nie ma w dzienniku wlasnego numeru. Odpowiedz
# z grubsza jest lepsza niz zadna — ale ma byc widoczne, ze jest z grubsza.
sprawdz("reakcja bez podpiecia nadal dostaje jakis kanal",
        wz.kanal_reakcji({"typ": "note_like", "czego": "nie-ma-takiego"},
                         POZYCJE) in ("notka", "nieznany"),
        wz.kanal_reakcji({"typ": "note_like", "czego": "brak"}, POZYCJE))
sprawdz("i brak pola `czego` tez nie wywala",
        isinstance(wz.kanal_reakcji({"typ": "comment_like"}, POZYCJE), str))

print()
print("=== 3. ALARM NAPRAWDE Z TEGO KORZYSTA ===")
# Sama poprawna funkcja w `wzajemnosc.py` nic nie daje, jesli przyrzad,
# ktory czyta wlasciciel, liczy po swojemu. To ta sama rodzina wad, co martwy
# wpis EFFORT: poprawka istnieje, ale nie dociera tam, gdzie ma skutek.
_alarm = pathlib.Path("agent-v2/alarm.py").read_text(encoding="utf-8")
sprawdz("alarm wola kanal_reakcji", "kanal_reakcji(" in _alarm)
sprawdz("i nie liczy juz kanalow po napisie typu",
        'lambda t: t == "comment_reply"' not in _alarm
        and 'lambda t: t in ("note_like", "note_restack")' not in _alarm)
sprawdz("alarm melduje, ile reakcji udalo sie podpiac",
        "podpiete pod nasza pozycje" in _alarm)
sprawdz("i ma droge zapasowa, gdy pozycji nie ma wcale",
        "BEZ POZYCJI ZOSTAJE STARY SPOSOB" in _alarm)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
