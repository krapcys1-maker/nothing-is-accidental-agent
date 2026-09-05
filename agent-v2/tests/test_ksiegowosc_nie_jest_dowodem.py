# -*- coding: utf-8 -*-
"""Pisarz notek dostaje dowod, a nie ksiegowosc banku.

CO ZGLASZA AUDYT (Q7). `material = {"fact": fakt}` podawalo CALY wpis indeksu,
a `note()` wkleja go do promptu przez `json.dumps` pod naglowkiem „The evidence
— everything you say comes from here, nothing from memory".

CO ZMIERZYLEM NA ZYWYM INDEKSIE (126 wpisow, produkcja): pol jest 27, z czego
16 to ksiegowosc banku i ZDANIA SEDZIEGO:

    dlaczego_mocny   121 wpisow   „A model escaping a safety sandbox and
                                   hundreds of agents coordinating..."
    podobne_do       121 wpisow   „landed side: like the chain-of-thought
                                   note, it shows the reader somet..."
    ranga            121 wpisow   1
    zielone_swiatlo  122 wpisow   True
    powod            126 wpisow   „juz o tym pisalismy — notka: Ox Alpha,
                                   the anonymous model that swept..."

NAJGORSZE JEST `powod`. Potrafi zawierac TEKST WCZESNIEJSZEJ NOTKI — bo taki
jest jego sens po stronie banku. Prompt notki mowi przy tym wprost:
„Everything else in the evidence is background you may draw on". Czyli
zapraszalismy pisarza, zeby czerpal z tresci notki, ktora juz wyszla —
dokladnie ta plaskosc, przed ktora stoi zapora „ta sama nazwa"
(`test_zapora_nazw_nie_slabnie.py`).

CZEGO NIE ODCINAM. `kat_wziety` zostaje: prompt wola je po nazwie i traktuje
jako ZADANIE („that is your assignment, not a suggestion"), a caly mechanizm
katow na tym stoi.

DLACZEGO BIALA LISTA, A NIE CZARNA. Dowod ma byc dowodem; pole, o ktorym nikt
nie pomyslal, ma domyslnie NIE isc do promptu. Cena jest jednak realna: nowy
rodzaj dowodu przepadlby po cichu — ten sam ksztalt, co wzorzec `*klucz*`
zjadajacy plik testu tego samego dnia. Dlatego druga stala, `KSIEGOWOSC_BANKU`,
nie filtruje niczego, tylko pozwala zauwazyc pole niesklasyfikowane. Pilnuje
tego sekcja 3.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_ksiegowosc_nie_jest_dowodem.py
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


# Wpis w ksztalcie, jaki naprawde lezy w indeksie produkcji — wszystkie 27 pol.
WPIS = {
    "fact": "The agency set the threshold at 12 units in August 2026.",
    "actually": "The rule fixes it at 12, not 20 as commonly repeated.",
    "control_fact": "the published rule fixes the threshold at 12 units",
    "control_url": "https://rejestr.example/rule", "control_verdict": "CONFIRMED",
    "control_date": "2026-08-14", "url": "https://zrodlo.example/a",
    "source_date": "2026-08-12", "domain": "Regulation",
    "consequence": "Operators below 12 never file at all.",
    "wrong_belief": "Everyone assumes the threshold is 20.",
    "kat_wziety": {"kat": "Lead with the filing gap",
                   "lamie": "that the threshold is 20"},
    # --- od tego miejsca ksiegowosc ---
    "status": "nowy", "kiedy": "2026-08-30T12:44:37+00:00",
    "wazny_do": "2026-09-06 12:44", "zielone_swiatlo": True, "ranga": 1,
    "na_artykul": False, "z_kanalu": True, "kanal_zrodlowy": "Some Channel",
    "uzyty_kiedy": None, "drugi_kat": True, "scalone_z": ["inny fakt"],
    "decision": "PISZ",
    "dlaczego_mocny": "A model escaping a safety sandbox and hundreds of "
                      "agents coordinating is the strongest thing in the bank.",
    "podobne_do": "landed side: like the chain-of-thought note, it shows the "
                  "reader something they can check themselves.",
    "powod": "juz o tym pisalismy — notka: Ox Alpha, the anonymous model that "
             "swept OpenRouter's usage charts, was Zhipu's GLM-5.3-Flash.",
    "katy": [{"kat": "inny kat", "uzyty": True}],
}

print("=== 1. DOWOD PRZECHODZI ===")
obciety = stages._fakt_do_pisarza(WPIS)
for pole in ("fact", "actually", "control_fact", "control_url",
             "control_verdict", "url", "source_date", "domain",
             "consequence", "wrong_belief"):
    sprawdz("%-16s zostaje" % pole, pole in obciety, sorted(obciety))
sprawdz("kat_wziety zostaje — prompt wola je po nazwie",
        obciety.get("kat_wziety") == WPIS["kat_wziety"])

print()
print("=== 2. KSIEGOWOSC I ZDANIA SEDZIEGO ODPADAJA ===")
for pole in ("ranga", "zielone_swiatlo", "dlaczego_mocny", "podobne_do",
             "powod", "status", "kiedy", "wazny_do", "katy", "z_kanalu",
             "na_artykul", "uzyty_kiedy", "drugi_kat", "scalone_z",
             "kanal_zrodlowy", "decision"):
    sprawdz("%-16s odciete" % pole, pole not in obciety, sorted(obciety))

# I to, co bolalo najbardziej: tresc wczesniejszej notki nie moze dojechac
# do pisarza jako „background you may draw on".
import json   # noqa: E402
sprawdz("tresc wczesniejszej notki nie trafia do promptu",
        "Ox Alpha" not in json.dumps(obciety, ensure_ascii=False),
        json.dumps(obciety, ensure_ascii=False)[:120])
sprawdz("ani zdanie sedziego o siale faktu",
        "strongest thing in the bank"
        not in json.dumps(obciety, ensure_ascii=False))

print()
print("=== 3. KAZDE POLE Z PRODUKCJI JEST SKLASYFIKOWANE ===")
# Biala lista milczy o polu, ktorego nie zna — nowy rodzaj dowodu przepadlby
# bez sladu. Ta sekcja wymusza decyzje: pole jest albo dowodem, albo
# ksiegowoscia, i nic nie moze byc niczym.
Z_PRODUKCJI = {
    "actually", "consequence", "control_date", "control_fact", "control_url",
    "control_verdict", "decision", "dlaczego_mocny", "domain", "drugi_kat",
    "fact", "kanal_zrodlowy", "katy", "kiedy", "na_artykul", "podobne_do",
    "powod", "ranga", "scalone_z", "source_date", "status", "url",
    "uzyty_kiedy", "wazny_do", "wrong_belief", "z_kanalu", "zielone_swiatlo",
}
znane = stages.DOWOD_DLA_PISARZA | stages.KSIEGOWOSC_BANKU
sprawdz("wszystkie 27 pol produkcji rozpoznane",
        not (Z_PRODUKCJI - znane), sorted(Z_PRODUKCJI - znane))
sprawdz("zadne pole nie jest w obu listach naraz",
        not (stages.DOWOD_DLA_PISARZA & stages.KSIEGOWOSC_BANKU),
        sorted(stages.DOWOD_DLA_PISARZA & stages.KSIEGOWOSC_BANKU))

print()
print("=== 4. PRODUKCJA NAPRAWDE PRZEZ TO PRZECHODZI ===")
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
# SAM KOD, BEZ KOMENTARZY. Pierwsza wersja tych dwoch asercji szukala
# starego zapisu w calym pliku i znajdowala go... we WLASNYM komentarzu
# opisujacym usterke. Trzeci taki falszywy alarm tego dnia.
_kod = chr(10).join(w for w in _zr.splitlines()
                    if not w.lstrip().startswith("#"))
sprawdz("material budowany przez filtr",
        'material = {"fact": _fakt_do_pisarza(fakt)}' in _kod)
sprawdz("i nie ma juz surowego przekazania",
        'material = {"fact": fakt}' not in _kod)

print()
print("=== 5. NIE-SLOWNIK PRZECHODZI BEZ ZMIAN ===")
# Fakt bywa samym zdaniem — patrz `tekst_faktu`. Filtr nie ma prawa go zjesc.
sprawdz("zdanie zostaje zdaniem",
        stages._fakt_do_pisarza("A bare sentence.") == "A bare sentence.")
sprawdz("None zostaje None", stages._fakt_do_pisarza(None) is None)

print()
print("=== 6. RANGA CZYTANA Z WLASCIWEGO POZIOMU ===")
# Osobne znalezisko z tej samej linii kodu: `wynik["fakt_ranga"]` bralo
# `material.get("ranga")`, a `material` to `{"fact": ...}` — wiec ranga nigdy
# nie lezala na jego poziomie i pole bylo ZAWSZE puste. Zmierzone w dzienniku
# produkcji: 18 wpisow niesie `fakt_ranga`, wszystkie 18 maja tam None.
sprawdz("ranga brana z wpisu, nie z opakowania",
        '(fakt or {}).get("ranga")' in _kod)
sprawdz("stara, zawsze pusta wersja zniknela",
        'material.get("ranga")' not in _kod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
