# -*- coding: utf-8 -*-
"""Wspolna nazwa wlasna to POWOD DO PYTANIA, a nie wyrok.

DLACZEGO TEN TEST ISTNIEJE. 8 wrzesnia 2026 w przebiegu 11:21 trzej kandydaci
odpadli na komunikacie „ta sama nazwa co w juz wystawionej notce". Sam przebieg
norme wykonal (plan 1, wydane 1), wiec kosztu NIE BYLO WIDAC po liczbie notek —
widac go dopiero po banku. Pomiar na zywym banku pokazal skale: ze 131 wolnych
faktow 88 (67%) odpadalo na tej jednej zaporze, a w czolowce blokujacych staly
firmy, nie tematy:

    anthropic 13    hugging 12    nvidia 11    google 11    minimax 7

Google kupujace systemy upadlych linii lotniczych i Google trenujace model to
dwie rozne wiadomosci. Firma jest AKTOREM, nie tematem.

CZTERY PROBY PROGU STATYSTYCZNEGO, WSZYSTKIE OBALONE POMIAREM. Szukalem liczby,
ktora odroznia firme od nazwy modelu, na tych samych danych:

    czestosc w banku       glm53flash 7 = minimax 7 = claude 7 = deepmind 7
    pokrycie slowami       trojka GLM ma 1-3 wspolne rdzenie, czyli MNIEJ
                           niz falszywe blokady (2-4)
    czestosc w zrodlach    glm53 ma 4, dokladnie miedzy google (2) i
                           anthropic (5)
    udzial wspolnych nazw  GLM 0.33, falszywe 0.12-1.00, mediana 0.71 —
                           GLM lezy w srodku rozkladu falszywych

Trzecia z tych prob byla juz WDROZONA na probe i zabila zapore calkowicie:
zalozycielska trojka notek o GLM-5.3-Flash przestala byc lapana, 3 pary z 3
przechodzily. Wycofana. Roznica miedzy firma a tematem jest w ZNACZENIU, wiec
zadna statystyka nazwy jej nie zlapie.

CO Z TYM ZROBILISMY. Znaczenie ocenia model — i JUZ TO U NAS ROBI: bank pyta
`_powtorka_wg_modelu` przy kazdym wejsciu kandydata. Przy wyborze notki pada
teraz to samo pytanie tym samym przyrzadem, tylko wobec notek juz wystawionych.
Pytamy WYLACZNIE gdy zapora nazw zadziala — okolo raz-dwa na przebieg, na
DeepSeeku po 400 tokenow.

CZEGO TEN TEST PILNUJE — skutkow, nie ksztaltu:

  1. wspolna nazwa + model mowi „to nie powtorka”  -> fakt WYCHODZI
  2. wspolna nazwa + model mowi „powtorka”         -> fakt odpada
  3. model pytany TYLKO gdy zapora nazw zadziala   -> zero wywolan bez kolizji
  4. brak `conn` (testy, wywolania bez bazy)       -> zostaje zdanie zapory
  5. nieudane wywolanie modelu                     -> fakt WYCHODZI
     (zawodzimy na „to nie powtorka”, jak wersja przy banku — przepuszczona
      powtorka kosztuje jedna notke, odrzucony material cale wyszukiwanie)
  6. `conn` i `run_id` naprawde docieraja z `notki_dnia`, bo bez tego
     produkcja pytalaby modelu nigdy, a zestaw i tak bylby zielony

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_nazwa_pyta_model.py
"""
import json
import pathlib
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
    """Cokolwiek nie-None. Gdyby kod czegos od niej chcial, ma krzyknac.

    Piaty raz w tym projekcie niepelna atrapa udawala usterke kodu, wiec
    atrapy krzycza zamiast po cichu oddawac None.
    """

    def __getattr__(self, nazwa):
        raise AssertionError(
            "wybor notki siega po conn.%s — atrapa tego nie przewiduje" % nazwa)


# Dwa fakty o tej samej firmie, ale o zupelnie roznych rzeczach. Wzorowane na
# prawdziwej parze z banku: „Google won a bankruptcy auction for Spirit
# Airlines' internal systems" kontra notka o trenowaniu modelu.
FAKT = {
    "domain": "aviation",
    "fact": "Google won a bankruptcy auction for Spirit Airlines' internal"
            " scheduling systems, paying 41 million dollars for software the"
            " airline had valued at 300 million in its own filings.",
}
WYSTAWIONA = ("Google trained its newest translation model on a corpus that"
              " excludes every language with fewer than 40 million speakers,"
              " which is most of them.")


def wywolaj(odpowiedz_modelu, conn=AtrapaConn(), wyjatek=False):
    """Uruchamia wybor z podstawionym `llm.call` i zwraca (fakt, ile_pytan)."""
    pytania = []
    oryginal = llm.call

    def podstawiony(purpose, system, prompt, **kw):
        pytania.append(purpose)
        if wyjatek:
            raise RuntimeError("polaczenie zerwane")
        return json.dumps(odpowiedz_modelu)

    llm.call = podstawiony
    try:
        wynik = stages.wybierz_material(
            [dict(FAKT)], [], ["cokolwiek"], teksty=[WYSTAWIONA],
            korpus_zrodel=None, conn=conn, run_id=1)
    finally:
        llm.call = oryginal
    return wynik, pytania


print("=== zapora nazw naprawde lapie te pare ===")
# Bez tego caly test bylby o niczym: gdyby `google` nie blokowalo, wszystkie
# ponizsze przypadki przechodzilyby z powodu, ktorego nie badamy.
_tekst_faktu = "%s %s" % (FAKT["domain"], FAKT["fact"])
_nazwa = stages.wspolna_nazwa(_tekst_faktu, WYSTAWIONA, [WYSTAWIONA] * 3)
sprawdz("`google` jest wspolna nazwa tej pary", bool(_nazwa),
        "wspolna_nazwa zwrocilo %r — dalsze przypadki nic nie sprawdzaja"
        % _nazwa)

print()
print("=== 1. model mowi „to nie powtorka” -> fakt wychodzi ===")
fakt, pytania = wywolaj({"powtorka_nr": 0, "powod": ""})
sprawdz("fakt zostal wydany mimo wspolnej nazwy", fakt is not None)
sprawdz("model byl pytany dokladnie raz", pytania == ["powtorka"],
        "pytania=%r" % pytania)

print()
print("=== 2. model mowi „powtorka” -> fakt odpada ===")
fakt, pytania = wywolaj({"powtorka_nr": 1, "powod": "obie o tym samym modelu"})
sprawdz("fakt odrzucony", fakt is None)
sprawdz("model byl pytany", pytania == ["powtorka"], "pytania=%r" % pytania)

print()
print("=== 3. bez kolizji nazw model NIE jest pytany ===")
# Fakt bez zadnej wspolnej nazwy z wystawiona notka. Zapora nie ma sie o co
# oprzec, wiec platne wywolanie nie ma prawa paść.
inny = {"domain": "shipping",
        "fact": "The Panama Canal Authority cut daily transits to 24 after the"
                " driest February in the basin since measurements began."}
pytania = []
oryginal = llm.call
llm.call = lambda purpose, *a, **k: (pytania.append(purpose)
                                     or json.dumps({"powtorka_nr": 0}))
try:
    fakt = stages.wybierz_material([dict(inny)], [], ["cokolwiek"],
                                   teksty=[WYSTAWIONA], conn=AtrapaConn(),
                                   run_id=1)
finally:
    llm.call = oryginal
sprawdz("fakt bez wspolnej nazwy wychodzi", fakt is not None)
sprawdz("i nie kosztowal ani jednego wywolania", pytania == [],
        "pytania=%r" % pytania)

print()
print("=== 4. bez `conn` zostaje samo zdanie zapory nazw ===")
fakt, pytania = wywolaj({"powtorka_nr": 0}, conn=None)
sprawdz("fakt odrzucony jak przed zmiana", fakt is None)
sprawdz("model nie byl pytany", pytania == [], "pytania=%r" % pytania)

print()
print("=== 5. nieudane wywolanie przepuszcza material ===")
fakt, pytania = wywolaj({"powtorka_nr": 1}, wyjatek=True)
sprawdz("fakt wychodzi mimo bledu modelu", fakt is not None)

print()
print("=== 5b. sufit pytan na jeden wybor ===")
# Bank pelen faktow o jednej firmie: kazdy kandydat zderza sie nazwa, a model
# na kazdego odpowiada „powtorka". Bez sufitu byloby tyle platnych pytan, ilu
# kandydatow — produkcja miesci sie w dobowym suficie z zapasem rzedu 20%.
_duzo = []
for _n in range(20):
    _duzo.append({"domain": "aviation",
                  "fact": "Google bought asset number %d from the estate of a"
                          " collapsed regional carrier, paying far under the"
                          " valuation in its own bankruptcy filings." % _n})
_pytania = []
_oryginal = llm.call
llm.call = lambda purpose, *a, **k: (_pytania.append(purpose)
                                     or json.dumps({"powtorka_nr": 1,
                                                    "powod": "to samo"}))
try:
    _fakt = stages.wybierz_material(_duzo, [], ["cokolwiek"],
                                    teksty=[WYSTAWIONA], conn=AtrapaConn(),
                                    run_id=1)
finally:
    llm.call = _oryginal
sprawdz("pytan nie wiecej niz sufit",
        len(_pytania) <= stages.MAKS_PYTAN_O_POWTORKE,
        "zadano %d pytan przy suficie %d"
        % (len(_pytania), stages.MAKS_PYTAN_O_POWTORKE))
sprawdz("sufit naprawde zostal dotkniety, wiec przypadek czegos dowodzi",
        len(_pytania) == stages.MAKS_PYTAN_O_POWTORKE,
        "zadano %d — za malo kandydatow, zeby sufit cokolwiek sprawdzil"
        % len(_pytania))
sprawdz("po suficie wraca zdanie zapory nazw", _fakt is None)

print()
print("=== 5c. przegladanie pamieci przerywa sie na trzeciej kolizji ===")
# `wspolna_nazwa` liczy przy kazdym wywolaniu nazwy calego korpusu i 341
# tematow zrodlowych. Wersja bez przerwania robila to 40 razy na kandydata.
_ile = [0]
_oryg_nazwa = stages.wspolna_nazwa


def _liczaca(a, b, korpus=None, **kw):
    _ile[0] += 1
    return _oryg_nazwa(a, b, korpus, **kw)


stages.wspolna_nazwa = _liczaca
_oryginal = llm.call
llm.call = lambda purpose, *a, **k: json.dumps({"powtorka_nr": 0})
try:
    stages.wybierz_material([dict(FAKT)], [], ["cokolwiek"],
                            teksty=[WYSTAWIONA] * 40, conn=AtrapaConn(),
                            run_id=1)
finally:
    stages.wspolna_nazwa = _oryg_nazwa
    llm.call = _oryginal
sprawdz("przy 40 zderzajacych sie notkach pyta o nazwe najwyzej 3 razy",
        _ile[0] <= 3, "wywolan wspolna_nazwa: %d" % _ile[0])

print()
print("=== 6. produkcja naprawde podaje conn i run_id ===")
# Bez tego przewodu wszystkie powyzsze przypadki moglyby byc zielone, a na
# produkcji model nie bylby pytany ani razu — zestaw swiecilby na zielono nad
# martwym mechanizmem.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
# Liczymy WYWOLANIA `wybierz_material`, ktore dostaja conn — a nie samo
# wystapienie napisu, bo `conn=conn, run_id=run_id` pada w tym pliku przy
# kilkudziesieciu innych wywolaniach i taka asercja bylaby zawsze zielona.
_wywolania = _zr.count("korpus_zrodel=_tematy_zrodel(),")
_wiersze = _zr.splitlines()
_z_conn = sum(
    1 for _i, _w in enumerate(_wiersze)
    if "korpus_zrodel=_tematy_zrodel()," in _w
    and _wiersze[_i + 1].strip() == "conn=conn, run_id=run_id)")
sprawdz("kazde wywolanie wyboru z notek_dnia niesie conn i run_id",
        _wywolania >= 3 and _z_conn == _wywolania,
        "wywolan %d, z conn %d — przewod urwany, produkcja nie zapytalaby"
        " modelu ani razu" % (_wywolania, _z_conn))
sprawdz("wybor materialu przyjmuje conn",
        "conn: sqlite3.Connection | None = None," in _zr)
sprawdz("zapora pyta o powtorke tym samym przyrzadem, co bank",
        "_powtorka_wg_modelu(\n                    fakt_tekst, zderzone,"
        " conn, run_id)" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
