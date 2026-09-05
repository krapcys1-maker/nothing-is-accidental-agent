# -*- coding: utf-8 -*-
"""Licznik mierzy WYKONANIE PLANU, nie ambicje sprzed zmiany widelek.

DLACZEGO TO POWSTALO — trzy pomiary z 30 sierpnia, kazdy falszywy z innego
powodu, i wszystkie trzy wygladaly jak awaria produkcji.

1. NORMA BYLA WSTECZNA. Widelki komentarzy zmienily sie tego dnia z (8,12) na
   (15,23). Dzien 29 sierpnia, w ktorym agent zalozyl sobie 10 komentarzy i
   zrobil 6 — czyli 60% wlasnego planu — pokazywal sie jako 32% normy, bo
   mierzono go liczba, ktora wtedy nie istniala.

2. ROZBIEG OBNIZA BUDZET, A NIE NORME. Przez pierwsze 30 dni budzet leci dolna
   polowa widelek, wiec srodek widelek jest systematycznie wyzszy niz to, co
   system w ogole zamierza zrobic. Norma nieosiagalna z arytmetyki mierzy wiek
   konta, nie jakosc pracy.

3. CICHY DZIEN. Raz na osiem dni notki i restacki sa wyciszane celowo, a licznik
   liczyl to jako zero. Naprawione osobno, tu tylko pilnowane.

Po poprawce restacki pokazuja 100% wykonania planu zamiast „niedoboru", a
komentarze 47% zamiast 25% — nadal najgorsze i nadal ponizej progu, ale to jest
liczba, ktora cos znaczy.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium. Zero platnych wywolan.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. MAPOWANIE BUDZET -> DZIENNIK JEST PELNE ===")
# Bez tego licznik porownywal norme „follow" z dziennikiem zapisujacym
# „obserwacja" i meldowal 0% przy dzialajacym bloku.
import norma   # noqa: E402
sprawdz("kazdy rodzaj z licznika ma odpowiednik w budzecie",
        set(norma.RODZAJE) <= set(config.BUDZET_NA_RODZAJ.values()),
        set(norma.RODZAJE) - set(config.BUDZET_NA_RODZAJ.values()))
sprawdz("i odwrotnie — zaden klucz budzetu nie wskazuje w prozne",
        set(config.BUDZET_NA_RODZAJ.values()) <= set(norma.RODZAJE),
        set(config.BUDZET_NA_RODZAJ.values()) - set(norma.RODZAJE))

print()
print("=== 2. LISTA CISZY WYPROWADZONA, NIE PRZEPISANA ===")
sprawdz("nazwy z ciszy pochodza z mapowania",
        config.CICHY_DZIEN_WYCISZA_RODZAJE
        == tuple(config.BUDZET_NA_RODZAJ[k] for k in config.CICHY_DZIEN_WYCISZA),
        config.CICHY_DZIEN_WYCISZA_RODZAJE)

print()
print("=== 3. BUDZET DNIA JEST ZAPISYWANY ===")
import stages   # noqa: E402
katalog = pathlib.Path(tempfile.mkdtemp())
stara = stages.BUDZETY
stages.BUDZETY = katalog / "budzety.json"
try:
    stages._zapisz_budzet_dnia("2026-01-01", {"komentarze": 9, "notki": 5}, True)
    stan = json.loads(stages.BUDZETY.read_text(encoding="utf-8"))
    sprawdz("zapisany", "2026-01-01" in stan, list(stan))
    sprawdz("z trescia", stan["2026-01-01"]["budzet"]["komentarze"] == 9)
    sprawdz("i ze znacznikiem rozbiegu", stan["2026-01-01"]["rozbieg"] is True)

    # NIE NADPISUJEMY. Gdyby konfiguracja zmienila sie w srodku dnia,
    # obowiazuje ten plan, wedlug ktorego agent dzialal od rana.
    stages._zapisz_budzet_dnia("2026-01-01", {"komentarze": 99}, False)
    stan = json.loads(stages.BUDZETY.read_text(encoding="utf-8"))
    sprawdz("drugi zapis tego samego dnia NIE nadpisuje",
            stan["2026-01-01"]["budzet"]["komentarze"] == 9,
            stan["2026-01-01"]["budzet"])

    print()
    print("=== 4. ZAPIS NIE MOZE ZABIC PRZEBIEGU ===")
    # Licznik jest wazny, ale nie wazniejszy od pracy, ktora mierzy.
    stages.BUDZETY = katalog / "nie-ma-takiego-katalogu" / "x" / "b.json"
    try:
        stages._zapisz_budzet_dnia("2026-01-02", {"komentarze": 1}, False)
        sprawdz("bledna sciezka nie rzuca wyjatku", True)
    except Exception as exc:
        sprawdz("bledna sciezka nie rzuca wyjatku", False, repr(exc))
finally:
    stages.BUDZETY = stara

print()
print("=== 5. LICZNIK CZYTA PLAN I TLUMACZY NAZWY ===")
_zdjecie_dir = config.uzyj_katalogu_danych(katalog)
try:
    (katalog / "budzety.json").write_text(json.dumps({
        "2026-01-03": {"budzet": {"komentarze": 8, "notki": 5, "follow": 1},
                       "rozbieg": True}}), encoding="utf-8")
    b = norma.budzety_dzienne()
    sprawdz("dzien wczytany", "2026-01-03" in b, list(b))
    sprawdz("nazwy przetlumaczone na dziennikowe",
            b["2026-01-03"].get("komentarz") == 8
            and b["2026-01-03"].get("obserwacja") == 1,
            b.get("2026-01-03"))
    sprawdz("i nie ma juz nazw budzetowych",
            "komentarze" not in b["2026-01-03"], b["2026-01-03"])

    print()
    print("=== 6. BRAK PLIKU NIE WYWALA LICZNIKA ===")
    (katalog / "budzety.json").unlink()
    sprawdz("pusty wynik zamiast wyjatku", norma.budzety_dzienne() == {})
    (katalog / "budzety.json").write_text("to nie jest json", encoding="utf-8")
    sprawdz("uszkodzony plik tez", norma.budzety_dzienne() == {})
finally:
    config.przywroc_katalog_danych(_zdjecie_dir)

print()
print("=== 7. ALARM STOI NA WYKONANIU, NIE NA AMBICJI ===")
zrodlo = pathlib.Path("agent-v2/norma.py").read_text(encoding="utf-8")
sprawdz("licznik pokazuje osobno wykonanie planu", "% PLANU" in zrodlo)
sprawdz("i osobno norme", "% NORMY" in zrodlo)
sprawdz("alarm mowi wprost, ze chodzi o plan",
        "WYKONANIA PLANU" in zrodlo)
sprawdz("dni bez zapisanego planu sa oznaczone",
        "plan nieznany" in zrodlo)

print()
print("=== PODWYZKA MIESIECZNA WYGASA Z KALENDARZA, NIE Z PAMIECI ===")
# CO SIE STALO. 5 wrzesnia 2026 pomiar pokazal, ze przy tempie tego miesiaca
# sufit 40 USD padnie okolo 15.-20. dnia, a `BudgetExceeded` leci twardo przed
# KAZDYM platnym wywolaniem — konto zamilkloby do konca miesiaca:
#
#     wrzesien, 5 dni:  13,11 USD;  konto 9,85 -> 1,97/dobe -> 59 USD/miesiac
#
# Wlasciciel podniosl sufit do 150 USD WYLACZNIE na wrzesien, bo w tym
# miesiacu duzo sprawdzalismy; od pazdziernika ma wrocic 40.
#
# CZEGO TEN TEST PILNUJE: ze powrot NIE ZALEZY od tego, czy ktos o nim
# pamieta 1 pazdziernika. Zwykle podniesienie stalej zostaloby na zawsze —
# ta podwyzka konczy sie data.
sprawdz("we wrzesniu sufit jest podniesiony",
        config.sufit_miesieczny("2026-09-05") == config.PODWYZKA_MIESIECZNA_USD,
        config.sufit_miesieczny("2026-09-05"))
sprawdz("ostatniego dnia wrzesnia jeszcze obowiazuje",
        config.sufit_miesieczny("2026-09-30") == config.PODWYZKA_MIESIECZNA_USD,
        config.sufit_miesieczny("2026-09-30"))
sprawdz("1 pazdziernika WRACA BAZOWY, bez niczyjego udzialu",
        config.sufit_miesieczny("2026-10-01") == config.MONTHLY_LIMIT_USD,
        config.sufit_miesieczny("2026-10-01"))
sprawdz("i zostaje bazowy pozniej",
        config.sufit_miesieczny("2027-03-01") == config.MONTHLY_LIMIT_USD,
        config.sufit_miesieczny("2027-03-01"))
# BEZ DATY BIERZE ZEGAR — inaczej produkcja liczylaby wedlug niczego.
sprawdz("bez podanej daty oddaje liczbe, nie None",
        isinstance(config.sufit_miesieczny(), float),
        config.sufit_miesieczny())
# PODWYZKA NIE MOZE OBNIZYC. Gdyby ktos wpisal tam mniej niz bazowy sufit,
# „podwyzka" po cichu zacisnelaby budzet.
sprawdz("podwyzka nigdy nie jest nizsza od bazowego sufitu",
        config.sufit_miesieczny("2026-09-05") >= config.MONTHLY_LIMIT_USD)

# KOD NAPRAWDE Z TEGO KORZYSTA. Sama funkcja w config.py nic nie znaczy,
# jesli bramka nadal czyta stala — to ta sama rodzina wad co martwy EFFORT.
import pathlib as _pl2   # noqa: E402
for _plik in ("llm.py", "alarm.py", "run.py"):
    _zr = _pl2.Path("agent-v2/%s" % _plik).read_text(encoding="utf-8")
    sprawdz("%s pyta o sufit funkcja, nie stala" % _plik,
            "sufit_miesieczny(" in _zr and "config.MONTHLY_LIMIT_USD" not in _zr,
            _plik)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
