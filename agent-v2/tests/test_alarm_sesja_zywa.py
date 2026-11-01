# -*- coding: utf-8 -*-
"""Alarm sesji mierzy ZYWA sesje, a nie stary plik (30.10.2026).

## Co bylo zepsute

Bot pracuje na zywym Chrome serwera (CDP), a `storage-state.json` jest tylko
zapasem. Alarm `alarm.sprawdz_sesje_i_ostrzez` i ostrzezenie „sesja wygasa za
N dni" brały dni Z PLIKU, ktorego nikt nie odswiezal od sierpnia. 30.10.2026
plik mowil 14 dni (wygasniecie 14.11), a zywa sesja miala 89 (28.01.2027):
Substack przedluza ja przy aktywnosci. Falszywy alarm kazal logowac sie bez
potrzeby, a jego tekst kazal to robic NA KOMPUTERZE wlasciciela i kopiowac plik
na serwer — czyli robic to, co nie dziala (sesja z innego adresu IP jest
odrzucana przy publikowaniu).

## Czego pilnuje ten test

1. `browser.odswiez_plik_sesji` zapisuje do pliku stan zywej sesji i oddaje
   liczbe dni z ZYWEJ sesji, a nie ze starego pliku.
2. Plik NIE jest nadpisywany, gdy zywy Chrome jest wylogowany, nie odpowiada,
   albo zapis sie wywali — kopia zapasowa nie moze zostac zastapiona gorsza.
3. Gdy Chrome nie odpowiada, nie uruchamia sie ZADNA przegladarka w jego
   miejsce (alarm nie otwiera headless).
4. Alarm po odswiezeniu nie krzyczy o sesji, ktora zyje; krzyczy, gdy zywa
   sesja tez dobiega konca.
5. Tekst alarmu mowi o logowaniu NA SERWERZE i o `browser.py sesja`, i nie
   kaze kopiowac pliku z komputera.

Bez sieci i bez przegladarki; plik sesji jest tymczasowy.
"""
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, "agent-v2")
import alarm     # noqa: E402
import browser   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


KAT = pathlib.Path(tempfile.mkdtemp())
PLIK = KAT / "storage-state.json"
DZIEN = 86400


def stan(dni):
    """Zawartosc pliku sesji z ciasteczkiem, ktore wygasa za `dni` dni."""
    return {"cookies": [{"name": browser.SESSION_COOKIE,
                         "expires": time.time() + dni * DZIEN + 3600}],
            "origins": []}


def zapisz_plik(dni):
    PLIK.write_text(json.dumps(stan(dni)), encoding="utf-8")


class Kontekst:
    """Zywy Chrome: ciasteczka i `storage_state` zapisujace to, co ma w pamieci."""

    def __init__(self, dni, zalogowany=True, wywal_zapis=False, smieci=False):
        self._dni, self._zal = dni, zalogowany
        self._wywal, self._smieci = wywal_zapis, smieci
        self.zapisy = 0

    def cookies(self):
        return stan(self._dni)["cookies"] if self._zal else []

    def storage_state(self, path=None):
        self.zapisy += 1
        if self._wywal:
            raise OSError("dysk pelny")
        tekst = "{to nie jest json" if self._smieci else json.dumps(stan(self._dni))
        pathlib.Path(path).write_text(tekst, encoding="utf-8")


class Przegladarka:
    def close(self):
        pass


class Pw:
    def stop(self):
        pass


oryg = (browser.SESSION_FILE, browser._chrome_odpowiada, browser.podlacz_sie, alarm.wyslij)
wyslane = []
laczenia = []


def ustaw(chrome_zyje, kontekst):
    browser._chrome_odpowiada = lambda: chrome_zyje

    def polacz():
        laczenia.append(1)
        return Pw(), Przegladarka(), kontekst
    browser.podlacz_sie = polacz
    wyslane.clear()
    laczenia.clear()


browser.SESSION_FILE = PLIK
alarm.wyslij = lambda klucz, temat, tresc: wyslane.append((klucz, temat, tresc)) or True
try:
    print("=== 1. ODSWIEZENIE Z ZYWEJ SESJI ===")
    zapisz_plik(14)
    sprawdz("punkt wyjscia: plik mowi ok. 14 dni", 13 <= browser.dni_do_wygasniecia() <= 14,
            browser.dni_do_wygasniecia())
    ustaw(True, Kontekst(89))
    dni = browser.odswiez_plik_sesji()
    sprawdz("oddaje dni ZYWEJ sesji (89), nie starego pliku (14)", dni in (88, 89), dni)
    sprawdz("plik zostal zapisany stanem zywej sesji", 88 <= browser.dni_do_wygasniecia() <= 89,
            browser.dni_do_wygasniecia())
    sprawdz("plik tymczasowy (unikalna nazwa z `mkstemp`) nie zostaje na dysku",
            list(KAT.glob("*.nowy")) == [], [p.name for p in KAT.iterdir()])

    if os.name == "posix":
        # ZAPISANY PLIK TO CIASTECZKA ZALOGOWANEJ SESJI: nie moze stac sie
        # czytelny dla innych uzytkownikow serwera. Plik tymczasowy powstaje
        # z domyslnymi uprawnieniami (tu symulujemy 644), a plik sesji mial 600.
        zapisz_plik(14)
        os.chmod(PLIK, 0o600)

        class KontekstLuzny(Kontekst):
            def storage_state(self, path=None):
                super().storage_state(path=path)
                os.chmod(path, 0o644)

        ustaw(True, KontekstLuzny(89))
        browser.odswiez_plik_sesji()
        sprawdz("uprawnienia pliku sesji zostaja 600 (plik tymczasowy mial 644)",
                oct(PLIK.stat().st_mode & 0o777) == "0o600", oct(PLIK.stat().st_mode & 0o777))
        PLIK.unlink()
        ustaw(True, KontekstLuzny(89))
        browser.odswiez_plik_sesji()
        sprawdz("bez poprzedniego pliku nowy dostaje 600, nie 644",
                oct(PLIK.stat().st_mode & 0o777) == "0o600", oct(PLIK.stat().st_mode & 0o777))
    else:
        print("  (pominiete: uprawnienia plikow sprawdzane tylko na systemie POSIX)")

    print()
    print("=== 2. KOPIA ZAPASOWA NIE MOZE ZOSTAC ZASTAPIONA GORSZA ===")
    for opis, k in (("zywy Chrome WYLOGOWANY", Kontekst(89, zalogowany=False)),
                    ("zapis sie wywala", Kontekst(89, wywal_zapis=True)),
                    ("zapis oddaje smieci zamiast JSON-a", Kontekst(89, smieci=True))):
        zapisz_plik(14)
        przed = PLIK.read_text(encoding="utf-8")
        ustaw(True, k)
        wynik = browser.odswiez_plik_sesji()
        sprawdz("%s -> None, plik bez zmian" % opis,
                wynik is None and PLIK.read_text(encoding="utf-8") == przed, wynik)
        sprawdz("   ... i bez pozostawionego pliku tymczasowego",
                list(KAT.glob("*.nowy")) == [], [p.name for p in KAT.iterdir()])
    zapisz_plik(14)
    ustaw(False, Kontekst(89))
    sprawdz("Chrome nie odpowiada -> None", browser.odswiez_plik_sesji() is None)
    sprawdz("   ... i NIE uruchamiamy zadnej przegladarki w jego miejsce", laczenia == [], laczenia)

    print()
    print("=== 3. ALARM PO ODSWIEZENIU ===")
    zapisz_plik(14)
    ustaw(True, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("plik mowil 14, zywa sesja 89 -> ALARMU NIE MA (falszywy alarm z 30.10)",
            wyslane == [], wyslane)
    zapisz_plik(14)
    ustaw(True, Kontekst(9))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("zywa sesja tez konczy sie (9 dni) -> alarm `sesja-konczy`",
            [w[0] for w in wyslane] == ["sesja-konczy"], wyslane)
    sprawdz("   ... z liczba dni z ZYWEJ sesji w temacie",
            wyslane and ("8 dni" in wyslane[0][1] or "9 dni" in wyslane[0][1]), wyslane)
    zapisz_plik(14)
    ustaw(False, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("Chrome nie odpowiada -> mierzymy plik jak dotad (14 dni -> alarm)",
            [w[0] for w in wyslane] == ["sesja-konczy"], wyslane)
    zapisz_plik(60)
    ustaw(False, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("plik 60 dni, Chrome milczy -> bez alarmu", wyslane == [], wyslane)
    PLIK.write_text(json.dumps(stan(-3)), encoding="utf-8")
    ustaw(False, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("plik wygasly i Chrome milczy -> alarm `sesja-wygasla`",
            [w[0] for w in wyslane] == ["sesja-wygasla"], wyslane)
    PLIK.unlink()
    ustaw(False, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("brak pliku i Chrome milczy -> alarm `sesja-brak`",
            [w[0] for w in wyslane] == ["sesja-brak"], wyslane)

    print()
    print("=== 4. TEKST ALARMU ===")
    zapisz_plik(3)
    ustaw(False, Kontekst(89))
    alarm.sprawdz_sesje_i_ostrzez()
    tresc = wyslane[0][2] if wyslane else ""
    sprawdz("mowi o logowaniu NA SERWERZE", "NA SERWERZE" in tresc, tresc[:120])
    sprawdz("podaje komende `browser.py sesja`", "browser.py sesja" in tresc, tresc)
    sprawdz("komenda DZIALA NA SERWERZE: interpreter projektu w katalogu projektu, nie goly `python`",
            "cd ~/nothing-is-accidental-agent && .venv/bin/python agent-v2/browser.py sesja" in tresc, tresc)
    sprawdz("odswiezenie sie nie udalo -> alarm mowi, ze liczba pochodzi ze STAREGO pliku",
            "Chrome serwera nie odpowiedzial" in tresc and "zywego Chrome serwera" not in tresc, tresc[:200])
    zapisz_plik(3)
    ustaw(True, Kontekst(3))
    wyslane.clear()
    alarm.sprawdz_sesje_i_ostrzez()
    sprawdz("odswiezenie sie udalo -> alarm mowi o pliku I zywym Chrome (i liczba jest z zywej sesji)",
            wyslane and "zywego Chrome serwera" in wyslane[0][2] and "nieaktualna" not in wyslane[0][2],
            wyslane)
    sprawdz("mowi o pulpicie przez tunel (noVNC)", "noVNC" in tresc and "6080" in tresc, tresc)
    sprawdz("NIE kaze kopiowac pliku z komputera",
            "skopiuj" not in tresc.lower() and "swoim komputerze" not in tresc, tresc)
    zrodlo = pathlib.Path("agent-v2/alarm.py").read_text(encoding="utf-8")
    sprawdz("w zrodle alarmu nie ma starej instrukcji z komputera wlasciciela",
            "na swoim komputerze" not in zrodlo and "skopiuj data/storage-state.json" not in zrodlo)
    sprawdz("alarm wola odswiezenie PRZED pomiarem dni",
            zrodlo.index("browser.odswiez_plik_sesji()") < zrodlo.index("dni = browser.dni_do_wygasniecia()"))
finally:
    (browser.SESSION_FILE, browser._chrome_odpowiada, browser.podlacz_sie, alarm.wyslij) = oryg

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
