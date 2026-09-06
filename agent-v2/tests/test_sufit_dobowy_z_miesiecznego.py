# -*- coding: utf-8 -*-
"""Sufit dobowy idzie za miesiecznym, zamiast stac na sztywno.

CO BYLO ZLE, znalezione 6 wrzesnia 2026 przy sprawdzaniu, czy wrzesniowa
podwyzka do 150 USD naprawde weszla. Weszla — `sufit_miesieczny()` oddaje 150.
Ale `DAILY_LIMIT_USD` i `sufit_dnia` oddawaly STALE 5,00 USD, bez zadnego
zwiazku z miesiecznym.

Na wrzesien pasowalo PRZYPADKIEM: 5 x 30 = 150, czyli dokladnie tyle, ile
wynosi podwyzka.

OD 1 PAZDZIERNIKA sufit miesieczny wraca do 40 USD, czyli 1,29 na dobe —
a dobowy zostalby na 5,00. Trzy i pol raza za luzno: miesiac dalby sie wypalic
w osiem dni, a jedyna zapora bylby sufit miesieczny, czyli dopiero PO fakcie.
Przebieg, ktory go przekroczy, juz zaplacil.

DWA OGRANICZENIA WZORU, oba postawione swiadomie i oba sprawdzane nizej:

  NIGDY LUZNIEJ NIZ 5,00. Z samego wzoru wrzesien wyszedlby na 8,00 — a
  wlasciciel prosil o wiekszy sufit MIESIECZNY, nie o luzniejsze doby. Ta
  poprawka ma zaciskac pazdziernik, nie rozluzniac wrzesien.

  NIGDY CIASNIEJ NIZ NA JEDEN DZIEN Z ARTYKULEM. Pazdziernikowe 40/31 x 1,6
  daje 2,06 — a wtorek to artykul (zmierzone 1,39-1,59) PLUS zwykla doba
  notek (okolo 1,05). Sufit dobowy odmawia PRZED wywolaniem, wiec taki wtorek
  nie powstalby wcale.

KOLEJNOSC W PLIKU TEZ JEST PILNOWANA. `sufit_dnia` siega po `sufit_miesieczny`
i po `RUN_LIMIT_ARTYKUL_USD`, wiec `DAILY_LIMIT_USD = sufit_dnia(...)` musi
stac za obiema. Przesuwalem to przypisanie DWA RAZY, za kazdym razem po
`NameError` przy imporcie — a `config`, ktory sie nie importuje, zatrzymuje
calego bota.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_sufit_dobowy_z_miesiecznego.py
"""
import calendar
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

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


print("=== 1. WRZESNIOWA PODWYZKA NAPRAWDE OBOWIAZUJE ===")
sprawdz("15 wrzesnia sufit miesieczny to 150",
        config.sufit_miesieczny("2026-09-15") == 150.0,
        config.sufit_miesieczny("2026-09-15"))
sprawdz("30 wrzesnia jeszcze 150",
        config.sufit_miesieczny("2026-09-30") == 150.0,
        config.sufit_miesieczny("2026-09-30"))
sprawdz("1 pazdziernika juz 40",
        config.sufit_miesieczny("2026-10-01") == 40.0,
        config.sufit_miesieczny("2026-10-01"))

print()
print("=== 2. WRZESIEN NIE ZOSTAL ROZLUZNIONY ===")
# Z samego wzoru wyszloby 8,00. Poprawka ma zaciskac pazdziernik, nie
# rozdawac wrzesniowi tego, o co nikt nie prosil.
sprawdz("dobowy we wrzesniu nadal 5,00",
        config.sufit_dnia("2026-09-15") == 5.00,
        config.sufit_dnia("2026-09-15"))
sprawdz("i nigdzie nie przekracza 5,00",
        all(config.sufit_dnia("2026-%02d-15" % m) <= 5.00 for m in range(1, 13)),
        [config.sufit_dnia("2026-%02d-15" % m) for m in range(1, 13)])

print()
print("=== 3. PAZDZIERNIK JEST ZACISNIETY ===")
_paz = config.sufit_dnia("2026-10-15")
sprawdz("dobowy w pazdzierniku ponizej 5,00", _paz < 5.00, _paz)
sprawdz("i wyraznie — co najmniej o jedna trzecia",
        _paz <= 5.00 * 0.7, _paz)
# Sensowna kontrola calosci: sufit dobowy razy dni nie moze byc absurdalnie
# wyzszy od miesiecznego, bo wtedy nie jest zadna zapora.
for d in ("2026-10-15", "2026-11-15", "2026-12-15"):
    dni = calendar.monthrange(int(d[:4]), int(d[5:7]))[1]
    sprawdz("%s: dobowy x dni miesci sie w 2,5x miesiecznego" % d,
            config.sufit_dnia(d) * dni <= config.sufit_miesieczny(d) * 2.5,
            round(config.sufit_dnia(d) * dni, 2))

print()
print("=== 4. WTOREK Z ARTYKULEM SIE MIESCI ===")
# Artykul zmierzony na 1,39-1,59 USD, zwykla doba notek okolo 1,05.
# Sufit dobowy odmawia PRZED wywolaniem, wiec za ciasny zabilby artykul.
POTRZEBA = 1.59 + 1.05
for d in ("2026-10-06", "2026-11-03", "2026-09-08"):
    sprawdz("%s udzwignie artykul (%.2f USD)" % (d, POTRZEBA),
            config.sufit_dnia(d) >= POTRZEBA, config.sufit_dnia(d))
sprawdz("i zawsze wiecej niz sam sufit przebiegu artykulu",
        config.sufit_dnia("2026-10-06") > config.RUN_LIMIT_ARTYKUL_USD,
        (config.sufit_dnia("2026-10-06"), config.RUN_LIMIT_ARTYKUL_USD))

print()
print("=== 5. RECZNE PODNIESIENIE JEDNEGO DNIA DZIALA DALEJ ===")
# `SUFIT_PODNIESIONY_NA` sluzy dniom pracy przy wlascicielu i ma byc silniejsze
# od wzoru — inaczej wprowadzenie wzoru cicho skasowaloby ten mechanizm.
sprawdz("podniesiony dzien to 10,00",
        config.sufit_dnia(config.SUFIT_PODNIESIONY_NA) == 10.00,
        config.sufit_dnia(config.SUFIT_PODNIESIONY_NA))

print()
print("=== 6. DAILY_LIMIT_USD ZGADZA SIE Z FUNKCJA ===")
# Dwie liczby, ktore moglyby sie rozjechac — a to wlasnie ta klasa bledu:
# egzekwowanie bierze stala, alarm bierze funkcje.
sprawdz("stala rowna funkcji na dzis",
        config.DAILY_LIMIT_USD == config.sufit_dnia(config._DZIS_UTC),
        (config.DAILY_LIMIT_USD, config.sufit_dnia(config._DZIS_UTC)))

print()
print("=== 7. KOLEJNOSC W PLIKU — config MUSI SIE IMPORTOWAC ===")
_zr = pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8")
_i_daily = _zr.index("DAILY_LIMIT_USD = sufit_dnia(")
sprawdz("przypisanie stoi za `def sufit_miesieczny`",
        _zr.index("def sufit_miesieczny") < _i_daily)
sprawdz("i za `RUN_LIMIT_ARTYKUL_USD`",
        _zr.index("RUN_LIMIT_ARTYKUL_USD = ") < _i_daily)
# Kontrola przyrzadu: powyzsze to napisy. To nizej to skutek.
sprawdz("a sam import config konczy sie bez wyjatku",
        isinstance(config.DAILY_LIMIT_USD, float), config.DAILY_LIMIT_USD)

print()
print("=== 8. ZLA DATA NIE WYWALA ===")
# `sufit_dnia` bierze napis z dziennika; pusty albo uszkodzony nie moze
# zatrzymac przebiegu.
for zle in ("", "nie-data", None, "2026"):
    try:
        w = config.sufit_dnia(zle)
        sprawdz("%-10r -> %.2f" % (zle, w), isinstance(w, float))
    except Exception as exc:
        sprawdz("%-10r nie wywala" % zle, False, type(exc).__name__)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
