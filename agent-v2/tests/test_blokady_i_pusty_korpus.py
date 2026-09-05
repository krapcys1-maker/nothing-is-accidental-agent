# -*- coding: utf-8 -*-
"""Blokada idzie do przegladarki, a pusty korpus nie zabija przebiegu.

ZLAPANE ZYWYM PRZEBIEGIEM 91, i to najcenniejsza porazka tego dnia.

Poprawka dyskoverii zadzialala: model przestal dopychac liste do dziesieciu
pozycji i oddal CZTERY, wszystkie pierwotne (historycznie 10 pozycji i 3,0
pierwotne przy dlugim szukaniu). I wlasnie dlatego przebieg padl — bo dokumenty
pierwotne prawnicze i akademickie siedza za zaporami:

    opencasebook.org   HTTP 403
    papers.ssrn.com    HTTP 403
    canlii.org         HTTP 403
    law.stanford.edu   PDF bez warstwy tekstowej
    !! nie pobrano ani jednej strony

Poprawiajac JAKOSC zrodel, pogorszylem SKUTECZNOSC pobierania. Dwie wady:

1. PONOWIENIE W PRZEGLADARCE OBEJMOWALO TYLKO „za malo tresci". Blokady nie
   dostawaly go wcale. Odlozylem te poprawke wczesniej, bo na 28 ARCHIWALNYCH
   blokadach przegladarka odzyskiwala 7% — ale tamte hosty byly z epoki
   przedmiotow, a te sa tym, po co research istnieje. Koszt jest bliski zeru:
   ta sama sesja przegladarki i tak sie odpala.

2. PUSTY KORPUS RZUCAL WYJATEK WEWNATRZ `fetch`. `run.py` ma tuz za tym
   wywolaniem druga runde dyskoverii, wlasnie na taki wypadek — ale sterowanie
   nigdy tam nie wracalo. Zabezpieczenie bylo NIEOSIAGALNE dokladnie wtedy, gdy
   bylo najbardziej potrzebne.

GRANICA ZOSTAJE: jesli strona MOWI, ze nie zyczy sobie automatu, przyjmujemy to
takze w przegladarce. Zwykla przegladarka, bez podmiany tozsamosci, bez
posrednikow, bez omijania captcha. 404 nie ponawiamy — tam naprawde nic nie ma.

BEZ PYTESTA, bez platnych wywolan i BEZ SIECI. Uruchamiac z korzenia repo.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def do_przegladarki(powod: str) -> bool:
    """Ten sam warunek, ktory decyduje w `fetch`."""
    return bool(powod and (powod.startswith("za mało treści")
                           or powod in stages._DO_PONOWIENIA
                           or powod.endswith("Error")))


print("=== 1. BLOKADY IDA DO PRZEGLADARKI ===")
for kod in ("HTTP 403", "HTTP 401", "HTTP 429", "HTTP 503"):
    sprawdz("%s ponawiamy" % kod, do_przegladarki(kod))
sprawdz("bledy sieci tez", do_przegladarki("ConnectError"))
sprawdz("pusta tresc nadal tak", do_przegladarki("za mało treści (0 znaków)"))

print()
print("=== 2. A CZEGO NIE PONAWIAMY ===")
sprawdz("404 nie — tam naprawde nic nie ma", not do_przegladarki("HTTP 404"))
sprawdz("odmowa wprost nie — szanujemy ja",
        not do_przegladarki("host odmówił automatowi"))
sprawdz("skan PDF nie — to nie kwestia klienta",
        not do_przegladarki("PDF bez warstwy tekstowej (skan?)"))
sprawdz("brak powodu nie", not do_przegladarki(""))

print()
print("=== 3. KONTRDOWOD: STARY WARUNEK PRZEPUSZCZAL SAMO 'za malo' ===")
# Gdyby sekcja 1 przechodzila takze na starym warunku, niczego by nie dowodzila.
def stary(powod: str) -> bool:
    return bool(powod and powod.startswith("za mało treści"))


sprawdz("stary warunek NIE ponawial 403", not stary("HTTP 403"))
sprawdz("ale ponawial pusta tresc", stary("za mało treści (0 znaków)"))
sprawdz("czyli trzy blokady przebiegu 91 przepadaly",
        not any(stary(k) for k in ("HTTP 403", "HTTP 403", "HTTP 403")))

print()
print("=== 4. ODMOWA JEST SPRAWDZANA TAKZE W PRZEGLADARCE ===")
zrodlo = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
i = zrodlo.index("def _dobierz_przegladarka")
blok = zrodlo[i:i + 2500]
sprawdz("przegladarka tez patrzy na frazy odmowy",
        "REFUSAL_PHRASES" in blok)
sprawdz("i zapisuje to jako odmowe, nie jako sukces",
        "host odmówił automatowi" in blok)

print()
print("=== 5. PUSTY KORPUS NIE RZUCA WYJATKU ===")
zr_fetch = zrodlo[zrodlo.index("def fetch("):]
zr_fetch = zr_fetch[:zr_fetch.index("DISCOVERY_SYSTEM")]
sprawdz("fetch nie rzuca przy zerze stron",
        "raise ValueError(\"nie pobrano ani jednej strony" not in zr_fetch)
sprawdz("tylko mowi o tym glosno",
        "ZERO stron" in zr_fetch)

print()
print("=== 6. TO RUN.PY DECYDUJE, CO ZROBIC Z PUSTKA ===")
rp = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("run.py konczy przebieg jawnie przy pustym korpusie",
        "if not corpus:" in rp)
sprawdz("i robi to PO drugiej rundzie, nie przed",
        rp.index("if za_chudo or bez_rekordow:") < rp.index("if not corpus:"))
sprawdz("konczy bez wyjatku, zapisanym powodem",
        'return _done(conn, run_id, "fetch")' in rp)

print()
print("=== 7. SPRAWDZONE NA ZYWO, NA TYCH SAMYCH ADRESACH ===")
# Nie atrapa: cztery adresy z przebiegu 91 przepuszczone przez POPRAWIONY
# `fetch` na serwerze 30 sierpnia. Wynik zapisany tutaj, zeby nie trzeba bylo
# wierzyc opisowi w commicie.
#
#   [pobranie] drugie podejscie w przegladarce: 3 stron     <- wczesniej ZERO
#   opencasebook.org   16 371 znakow   ODZYSKANE
#   papers.ssrn.com       263 znaki    strona-zapora
#   canlii.org              0 znakow
#   law.stanford.edu   pominiety — skan PDF, przegladarka nic nie zmieni
#   fetch PRZEZYL zero pobran, wyjatek nie poleciał
#
# 1 z 3 to ten sam rzad wielkosci, co pomiar na archiwum (7%) — i wystarcza,
# bo przebieg 91 zginal z ZEREM, a na tym samym materiale konczy sie teraz
# jednym prawdziwym dokumentem i zywym przebiegiem.
sprawdz("skan PDF nadal poza ponowieniem (przegladarka go nie naprawi)",
        not do_przegladarki("PDF bez warstwy tekstowej (skan?)"))
sprawdz("a trzy blokady 403 do niego trafiaja",
        all(do_przegladarki("HTTP 403") for _ in range(3)))

print()
print("=== 8. PROGI NIE ZMIENILY SIE PRZY OKAZJI ===")
sprawdz("nadal wymagamy zrodel do pisania",
        config.MIN_ZRODEL_DO_PISANIA >= 1, config.MIN_ZRODEL_DO_PISANIA)
sprawdz("i nadal minimum pierwotnych",
        config.MIN_PRIMARY_SOURCES >= 1, config.MIN_PRIMARY_SOURCES)

print()
print("=== KANAL, KTORY NIE ODPOWIADA, IDZIE NA PRZERWE ===")
# ZMIERZONE 5 wrzesnia 2026: 12 z 13 kanalow YouTube oddaje 404 albo 500.
# To nie sa zle identyfikatory — ten sam adres ByCloud oddal 15 filmow
# kilkanascie minut wczesniej. YouTube blokuje ten serwer.
#
# Bez przerwy pukamy tam 12 razy na przebieg i 60 razy dziennie po nic, a
# powtarzane pukanie do serwisu, ktory nas odrzucil, blokade poglebia.
# PRZERWA TO UZNANIE ODMOWY, NIE JEJ OMIJANIE — po dobie probujemy raz
# jeszcze, bo blokady bywaja czasowe.
import pathlib as _pl        # noqa: E402
import tempfile as _tf       # noqa: E402

import korpus_kanalow as _kk   # noqa: E402

# KATALOG DANYCH NA BOK. Pierwsza wersja tej sekcji zapisala
# `kanaly_na_przerwie.json` do PRAWDZIWEGO `data/` — czyli test o odpornosci
# korpusu sam przestawil produkcyjny stan. `uzyj_katalogu_danych` to jedyna
# usankcjonowana droga; pilnuje jej `test_komplet_sciezek`.
_ZDJECIE = config.uzyj_katalogu_danych(_pl.Path(_tf.mkdtemp()))

_kk._zapisz_przerwy({})
sprawdz("na starcie nikt nie odpoczywa", _kk._kanaly_na_przerwie() == set())

for _ in range(_kk.PORAZEK_DO_PRZERWY - 1):
    _kk._zapisz_porazke("Kanal Testowy")
sprawdz("dwie porazki to jeszcze nie przerwa",
        "Kanal Testowy" not in _kk._kanaly_na_przerwie(),
        _kk._kanaly_na_przerwie())

_kk._zapisz_porazke("Kanal Testowy")
sprawdz("trzecia porazka wysyla na przerwe",
        "Kanal Testowy" in _kk._kanaly_na_przerwie(),
        _kk._kanaly_na_przerwie())

# KAPRYSNY TO NIE MARTWY. Bez zerowania licznika pojedyncze potkniecia z
# roznych dni sumowalyby sie do przerwy przy kanale, ktory dziala.
_kk._zapisz_przerwy({})
_kk._zapisz_porazke("Kaprysny")
_kk._zapisz_porazke("Kaprysny")
_kk._zapisz_sukces("Kaprysny")
_kk._zapisz_porazke("Kaprysny")
_kk._zapisz_porazke("Kaprysny")
sprawdz("sukces zeruje licznik porazek",
        "Kaprysny" not in _kk._kanaly_na_przerwie(),
        _kk._kanaly_na_przerwie())

# PRZERWA MA KONIEC. Blokada bywa czasowa i kanal ma dostac druga szanse.
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
_kk._zapisz_przerwy({"Stary": {"porazki": 0, "do_kiedy":
                     (_dt.now(_tz.utc) - _td(hours=1)).isoformat()}})
sprawdz("przerwa, ktorej termin minal, juz nie obowiazuje",
        "Stary" not in _kk._kanaly_na_przerwie(), _kk._kanaly_na_przerwie())
sprawdz("a przerwa ma koniec, nie jest wieczna",
        0 < _kk.PRZERWA_GODZIN <= 24, _kk.PRZERWA_GODZIN)
_kk._zapisz_przerwy({})

print()
print("=== TRESC, KTORA RAZ SIE UDALA, PRZEZYWA ZLA GODZINE ZRODLA ===")
# ZMIERZONE 5 wrzesnia 2026 dwiema probami po piec kanalow: bez przerwy 1/5,
# z przerwa CZTERECH SEKUND 0/5. Rozkladanie zapytan w czasie NIE POMAGA — to
# nie jest limit na sekunde. Ten sam kanal w ciagu godziny oddal 429, potem
# 404, potem 500, a na koncu 200 z poprawnym tytulem: odpowiedz jest losowa,
# okolo jedno zapytanie na piec przechodzi.
#
# Wlasciwa odpowiedz na taka blokade NIE ZWIEKSZA liczby zapytan: pytamy tyle
# samo razy co wczoraj i po prostu nie wyrzucamy tego, co juz dostalismy.
_kk._plik_tresci().unlink(missing_ok=True)
sprawdz("bez zapasu nie ma czego brac",
        _kk._tresc_z_zapasu("Kanal X") == "")

_kk._zapamietaj_tresc("Kanal X", "<feed>tresc</feed>")
sprawdz("swiezy zapas wraca w calosci",
        _kk._tresc_z_zapasu("Kanal X") == "<feed>tresc</feed>",
        _kk._tresc_z_zapasu("Kanal X")[:40])

# ZAPAS MA TERMIN. Feed sprzed tygodnia opisuje inny swiat i nie moze udawac
# dzisiejszego korpusu — to ta sama zasada, co odsiew przeterminowanych faktow.
import json as _js
from datetime import datetime as _d2, timedelta as _t2, timezone as _z2
_kk._plik_tresci().write_text(_js.dumps({"Stary": {
    "kiedy": (_d2.now(_z2.utc) - _t2(hours=_kk.ZAPAS_TRESCI_GODZIN + 1)).isoformat(),
    "xml": "<feed>stare</feed>"}}), encoding="utf-8")
sprawdz("zapas starszy niz doba juz nie wraca",
        _kk._tresc_z_zapasu("Stary") == "", _kk._tresc_z_zapasu("Stary")[:30])
_kk._plik_tresci().unlink(missing_ok=True)

# PROG DOBRANY DO ZMIERZONEJ NATURY BLOKADY, nie z glowy. Przy szansie jeden
# do pieciu prog 3 dawalby przerwe polowie dzialajacych kanalow.
sprawdz("prog porazek nie jest ostrzejszy niz zmierzona szansa",
        _kk.PORAZEK_DO_PRZERWY >= 5, _kk.PORAZEK_DO_PRZERWY)
sprawdz("a przerwa jest krotsza niz zapas tresci",
        _kk.PRZERWA_GODZIN < _kk.ZAPAS_TRESCI_GODZIN,
        (_kk.PRZERWA_GODZIN, _kk.ZAPAS_TRESCI_GODZIN))

print()
print("=== ZRODLA PIERWOTNE SA PRAWDZIWA SPIZARNIA ===")
# Skaut placi za szukanie tylko przy pustej spizarni, wiec liczba zrodel to
# pozycja kosztowa. 5 wrzesnia 2026: 7 -> 18.
sprawdz("zrodel pierwotnych jest wiecej niz kanalow YouTube",
        len(_kk.ZRODLA) > len(_kk.KANALY), (len(_kk.ZRODLA), len(_kk.KANALY)))
sprawdz("kazde zrodlo ma adres http",
        all(str(a).startswith("http") for a in _kk.ZRODLA.values()))
sprawdz("zadne zrodlo nie powtarza adresu",
        len(set(_kk.ZRODLA.values())) == len(_kk.ZRODLA))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
