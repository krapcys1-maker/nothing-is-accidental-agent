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
print("=== 8. OTWARCIE SPOREM, KTOREGO CZYTELNIK NIE SLYSZAL ===")
# Zmierzone na wszystkich 34 notkach od przestawienia konta: wykrywacz strzela
# przy dwoch i sa to dokladnie te dwie, ktore przy recznym czytaniu okazaly sie
# nieczytelne. Ponizej oba prawdziwe teksty, doslownie.
NOTKA_07 = ("Shelved genius is the most flattering story this industry tells "
            "about itself. I keep half-agreeing.")
NOTKA_34 = ("Trying it yourself is also a benchmark. Sample size one, run "
            "once, never written down. I keep hearing that public tests are "
            "useless and personal experience is the honest measure.")
sprawdz("lapie notke #07 (wlasny zwrot podany jak znany)",
        bool(stages.otwiera_sporem(NOTKA_07)), stages.otwiera_sporem(NOTKA_07))
sprawdz("lapie notke #34 — te, ktora wlasciciel czytal trzy razy",
        bool(stages.otwiera_sporem(NOTKA_34)), stages.otwiera_sporem(NOTKA_34))
sprawdz("i zwraca CALE zdanie, a nie sam pasujacy fragment",
        stages.otwiera_sporem(NOTKA_34).startswith("I keep hearing"),
        stages.otwiera_sporem(NOTKA_34))

# ZASIEG TRZECH ZDAN NIE JEST OZDOBA. W notce #34 ruch stoi w zdaniu TRZECIM,
# wiec wykrywacz patrzacy na dwa przepuscilby tekst, dla ktorego powstal.
sprawdz("KONTRDOWOD ZASIEGU: przy dwoch zdaniach #34 by uciekla",
        not stages.OTWARCIE_SPOREM.search(
            "Trying it yourself is also a benchmark.")
        and not stages.OTWARCIE_SPOREM.search(
            "Sample size one, run once, never written down."))

print()
print("=== 9. KONTRDOWOD: DOBRE NOTKI PRZECHODZA CZYSTO ===")
CZYSTE = [
    "Two paragraphs. That is how much of any answer I skip before I read.",
    "Asking a chatbot to check its own draft feels like free proofreading.",
    "Cheap models are supposed to be worse models. Pay a tenth, get less.",
    "Ireland gave 23 percent of its metered electricity to data centres.",
    "A model refusal is not a rule. It is a single direction in its weights.",
]
for t in CZYSTE:
    sprawdz("przepuszcza: %s" % t[:46], not stages.otwiera_sporem(t),
            stages.otwiera_sporem(t))
sprawdz("pusty tekst nie wywraca wykrywacza", stages.otwiera_sporem("") == "")
sprawdz("None tez nie", stages.otwiera_sporem(None) == "")
sprawdz("ten sam ruch DALEJ w tekscie jest w porzadku",
        not stages.otwiera_sporem(
            "Ireland gave 23 percent of its power to data centres. The share "
            "rose for a third year. The grid operator said so in August. "
            "Everyone says this is about crypto."))

print()
print("=== 10. REGULA STOI TEZ W PROMPCIE NOTKI ===")
_tresc_nt = pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8")
sprawdz("prompt zakazuje tego otwarcia wprost",
        "Never open by contradicting something the reader has not heard"
        in _tresc_nt)
sprawdz("i podaje OBIE winne notki jako przyklad",
        "Shelved genius" in _tresc_nt and "I keep hearing" in _tresc_nt)
sprawdz("i mowi, czym zastapic — przekonaniem czytelnika o SOBIE",
        "as something they" in _tresc_nt.lower()
        or "the reader's OWN" in _tresc_nt)

print()
print("=== 11. JEDEN FAKT ODDAJE KILKA NOTEK PRZEZ KATY ===")
# Do 4 wrzesnia 2026 katy byly wylacznie ZAPISYWANE: pisanie notki zjadalo caly
# fakt. Model rozpisywal je przy kazdym przebiegu i placilismy za to, a „z
# jednego newsa trzy notki" nie zdarzylo sie ani razu.


def _fakt(tresc, katy, kiedy=None):
    return {"status": "nowy", "kiedy": kiedy or config.DATA_PRZESTAWIENIA,
            "wazny_do": "2099-01-01", "source_date": config.DATA_PRZESTAWIENIA,
            "fact": tresc,
            "katy": [{"kat": k, "lamie": k + " belief", "czego_brakuje": "",
                      "uzyty": False} for k in katy]}


def _wywolaj(bank, ile):
    zapisane = {}
    st_ind, st_zap = stages.wczytaj_indeks, stages._zapisz_indeks
    st_pub = stages.opublikowane_teksty
    stages.wczytaj_indeks = lambda *a, **k: bank
    stages._zapisz_indeks = lambda x: zapisane.update({"bank": x})
    stages.opublikowane_teksty = lambda *a, **k: []
    try:
        return stages.wez_kandydatow(ile)
    finally:
        stages.wczytaj_indeks, stages._zapisz_indeks = st_ind, st_zap
        stages.opublikowane_teksty = st_pub


B1 = [_fakt("Ireland gave 23 percent of metered power to data centres",
            ["cena", "sieci", "prawo"])]
w1 = _wywolaj(B1, 1)
sprawdz("jedna notka -> jeden kandydat", len(w1) == 1, len(w1))
sprawdz("kandydat niesie kat", bool(w1 and w1[0].get("kat_wziety")),
        w1[0].get("kat_wziety") if w1 else None)
sprawdz("fakt ZOSTAJE w banku, bo ma jeszcze dwa katy",
        B1[0]["status"] == "nowy", B1[0]["status"])
sprawdz("zuzyty jest DOKLADNIE jeden kat",
        sum(1 for k in B1[0]["katy"] if k["uzyty"]) == 1,
        [k["uzyty"] for k in B1[0]["katy"]])

B2 = [_fakt("Ireland gave 23 percent of metered power to data centres",
            ["cena", "sieci", "prawo"])]
w2 = _wywolaj(B2, 3)
sprawdz("trzy notki z JEDNEGO faktu", len(w2) == 3, len(w2))
sprawdz("kazda dostaje INNY kat",
        len({str((x.get("kat_wziety") or {}).get("kat")) for x in w2}) == 3,
        [(x.get("kat_wziety") or {}).get("kat") for x in w2])
sprawdz("po wyczerpaniu katow fakt wychodzi z banku",
        B2[0]["status"] == "uzyty", B2[0]["status"])

B3 = [_fakt("a" * 40 + " pierwszy", ["a1", "a2"]),
      _fakt("b" * 40 + " drugi", ["b1", "b2"])]
w3 = _wywolaj(B3, 4)
sprawdz("dwa fakty po dwa katy daja cztery notki", len(w3) == 4, len(w3))
_kolejnosc = [x["fact"][:1] for x in w3]
sprawdz("kolejnosc jest RUNDAMI, nie po jednym fakcie do wyczerpania",
        _kolejnosc[:2] != [_kolejnosc[0], _kolejnosc[0]], _kolejnosc)

B4 = [_fakt("fakt zupelnie bez katow", [])]
w4 = _wywolaj(B4, 2)
sprawdz("KONTRDOWOD: fakt bez katow oddaje jedna notke", len(w4) == 1, len(w4))
sprawdz("i wychodzi z banku od razu", B4[0]["status"] == "uzyty",
        B4[0]["status"])
sprawdz("a jego `kat_wziety` jest pusty",
        w4 and w4[0].get("kat_wziety") is None, w4[0].get("kat_wziety"))

print()
print("=== 12. KONTRDOWOD: FAKT NIE JEST WLASNYM BLIZNIAKIEM ===")
# Fakt z nieuzytym katem zostaje „nowy", ale z dzisiejsza data w `uzyty_kiedy`
# — czyli trafia do listy wolnych I do listy porownawczej. Bez wykluczenia
# tozsamosci wypadlby jako wlasny blizniak i pozostale katy nie doczekalyby
# sie nigdy.
B5 = [_fakt("Ireland gave 23 percent of metered power to data centres",
            ["cena", "sieci"])]
B5[0]["uzyty_kiedy"] = __import__("db").now()
w5 = _wywolaj(B5, 1)
sprawdz("fakt wzięty dzis nadal da sie wziac po kolejny kat",
        len(w5) == 1, len(w5))

_tresc_nt2 = pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8")
sprawdz("prompt notki wie, co zrobic z `kat_wziety`", "kat_wziety" in _tresc_nt2)
sprawdz("i mowi, ze `lamie` ma byc ZA KAZDYM RAZEM inne",
        "DIFFERENT wrong belief" in _tresc_nt2)

print()
print("=== 13. KOLEJNE UJECIE PRZECHODZI PRZEZ WYBOR MATERIALU ===")
# TU MECHANIZM KATOW ZYJE ALBO UMIERA. `wez_kandydatow` moze oddac dwa wpisy
# tego samego faktu, ale wybiera z nich `wybierz_material` — a on odrzuca
# material podobny do naszych wczesniejszych notek. Bez zwolnienia dla
# `kat_nr > 0` katy byly by martwe na produkcji mimo zielonych testow wyzej.
FAKT_TRESC = ("DeepSeek open-sourced Harness v0.1 where the model writes runs "
              "and modifies its own plugins")
STARA_NOTKA = FAKT_TRESC          # nasza wczesniejsza notka o tym samym

pierwsze = [{"fact": FAKT_TRESC, "domain": "agents", "kat_nr": 0,
             "kat_wziety": {"kat": "a", "lamie": "pierwsze przekonanie"}}]
kolejne = [{"fact": FAKT_TRESC, "domain": "agents", "kat_nr": 1,
            "kat_wziety": {"kat": "b", "lamie": "drugie przekonanie"}}]

w_pierwsze = stages.wybierz_material(pierwsze, [], [STARA_NOTKA],
                                     teksty=[STARA_NOTKA])
sprawdz("BRAMKA STOI: pierwsze ujecie podobne do starej notki odpada",
        w_pierwsze is None, w_pierwsze)
w_kolejne = stages.wybierz_material(kolejne, [], [STARA_NOTKA],
                                    teksty=[STARA_NOTKA])
sprawdz("ZWOLNIENIE DZIALA: kolejne ujecie przechodzi",
        w_kolejne is not None,
        (w_kolejne or {}).get("kat_nr"))
sprawdz("i niesie SWOJ kat, nie pierwszy",
        (w_kolejne or {}).get("kat_wziety", {}).get("lamie")
        == "drugie przekonanie",
        (w_kolejne or {}).get("kat_wziety"))

# Zwolnienie dotyczy WYLACZNIE poprzednich dni. To, co idzie DZIS, blokuje
# kazdy material bez wyjatku — 31 sierpnia wyszly trzy notki o GLM-5.3-Flash
# jednego dnia i czytelnik zobaczyl plaskosc, nie trzy ustalenia.
w_dzis = stages.wybierz_material(kolejne, [FAKT_TRESC], [], teksty=[])
sprawdz("KONTRDOWOD: to samo co DZIS blokuje takze kolejne ujecie",
        w_dzis is None, w_dzis)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
