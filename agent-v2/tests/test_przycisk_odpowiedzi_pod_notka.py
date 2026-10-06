# -*- coding: utf-8 -*-
"""Odpowiedz pod notka: przycisk wysylki „Post” PRZED „Reply” (6.10.2026).

WADA. `browser.wystaw_odpowiedz` szukala przycisku wysylki na liscie
`("Reply", "Odpowiedz", "Post", ...)` i brala PIERWSZY WIDOCZNY. „Reply” to
przycisk odpowiedzi pod JUZ ISTNIEJACYM komentarzem: otwiera pole, nie wysyla. Na
stronie notki z odpowiedziami — a od 4.10 wybieramy zywe watki, czyli wlasnie takie —
jest widoczny, wiec kod klikal go zamiast „Post”.

POMIAR NA DZIENNIKU PRODUKCJI (od 20.09.2026): po kliknieciu „Post” odpowiedz
potwierdzona w 102 z 102 przypadkow, po kliknieciu „Reply” w 0 z 11 („KLIKNIETE, ALE
ODPOWIEDZI NIE MA W WATKU"). 4.10: 5 takich porazek na 24 proby pod notkami.

Test mierzy ZACHOWANIE: atrapa strony, na ktorej klikniecie „Reply” NIE wysyla, a
klikniecie „Post” wysyla. KONTRDOWOD jest odtworzony, nie opisany: ten sam scenariusz
przechodzi przez `browser.py` z commita `e4b1378` (sprzed poprawki), wczytanego jako
osobny modul.

BEZ PYTESTA, zero sieci i zero modelu; dziennik idzie do katalogu tymczasowego.
Z korzenia repo:  python agent-v2/tests/test_przycisk_odpowiedzi_pod_notka.py
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, "agent-v2")
import browser  # noqa: E402

KORZEN = pathlib.Path(__file__).resolve().parents[2]
ODNIESIENIE = "e4b1378"          # browser.py SPRZED poprawki, przypiety do SHA
TEKST = "Trzy zdania o czyms konkretnym."

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# --- ATRAPA STRONY: „Reply” otwiera pole, „Post” wysyla -----------------------
class Brak:
    def count(self):
        return 0

    def is_visible(self):
        return False

    def nth(self, i):
        return self

    @property
    def first(self):
        return self

    def click(self, **k):
        raise AssertionError("klikniecie w niedopasowany lokator")


class Element:
    def count(self):
        return 1

    def is_visible(self):
        return True

    def is_editable(self):
        return True

    def nth(self, i):
        return self

    @property
    def first(self):
        return self

    def click(self, **k):
        pass

    def scroll_into_view_if_needed(self, **k):
        pass


class Zbior:
    def __init__(self, elementy):
        self.elementy = list(elementy)

    def count(self):
        return len(self.elementy)

    def nth(self, i):
        return self.elementy[i]

    @property
    def first(self):
        return self.elementy[0] if self.elementy else Brak()


class PrzyciskWysylki(Element):
    def __init__(self, strona):
        self.strona = strona

    def click(self, **k):
        self.strona.wyslano = True
        self.strona.klikniete.append("Post")


class PrzyciskOtwierajacy(Element):
    """„Reply” pod istniejacym komentarzem: otwiera pole, NIC NIE WYSYLA."""

    def __init__(self, strona):
        self.strona = strona

    def click(self, **k):
        self.strona.klikniete.append("Reply")


class Otwieracz(Element):
    def __init__(self, strona):
        self.strona = strona

    def click(self, **k):
        self.strona.edytowalne = Zbior([Element()])

    def locator(self, selektor):
        return self


class _Mysz:
    def wheel(self, *a):
        pass


class _Klawiatura:
    def type(self, tekst, **k):
        pass


class Strona:
    def __init__(self, przyciski):
        self.przyciski = dict(przyciski)         # nazwa -> "wysylka" | "otwieracz"
        self.wyslano = False
        self.klikniete = []
        self.mouse = _Mysz()
        self.keyboard = _Klawiatura()
        self.edytowalne = Zbior([])
        self.ostatni = ""

    def goto(self, url, **k):
        self.ostatni = url

    def wait_for_timeout(self, ms):
        pass

    def inner_text(self, selektor):
        url = self.ostatni
        if "/api/v1/reader/comment/" in url:
            galezie = [{"id": 555001, "body": TEKST}] if self.wyslano else []
            return json.dumps({"commentBranches": galezie})
        return "{}"

    def locator(self, selektor):
        if "contenteditable" in selektor:
            return self.edytowalne
        return Brak()

    def get_by_role(self, rola, name=None, exact=False):
        rodzaj = self.przyciski.get(name)
        if rodzaj == "wysylka":
            return PrzyciskWysylki(self)
        if rodzaj == "otwieracz":
            return PrzyciskOtwierajacy(self)
        return Brak()

    def get_by_text(self, napis, exact=False):
        return Zbior([Otwieracz(self)]) if napis == "Leave a reply" else Brak()

    def close(self):
        pass


class _Sterownik:
    def stop(self):
        pass


class _Przegladarka:
    def close(self):
        pass


class _Kontekst:
    def __init__(self, strona):
        self.strona = strona

    def new_page(self):
        return self.strona


KATALOG = pathlib.Path(tempfile.mkdtemp(prefix="nia-przycisk-"))
DZIENNIK = KATALOG / "dziennik.jsonl"


def przygotuj(modul):
    modul.DZIENNIK = DZIENNIK
    modul.wymagaj_sesji = lambda: None
    modul.config.DRY_RUN = False
    return modul


def odpowiedz(modul, przyciski):
    strona = Strona(przyciski)
    modul.podlacz_sie = lambda: (_Sterownik(), _Przegladarka(), _Kontekst(strona))
    if DZIENNIK.exists():
        DZIENNIK.unlink()
    wynik = modul.wystaw_odpowiedz(352087712, TEKST, wyslij=True)
    return wynik, strona


def modul_z_commita(commit):
    proc = subprocess.run(["git", "-C", str(KORZEN), "show", "%s:agent-v2/browser.py" % commit],
                          capture_output=True)
    if proc.returncode != 0:
        raise SystemExit("nie dostalem %s z gita: %s" % (commit, proc.stderr.decode("utf-8", "replace")[:200]))
    m = types.ModuleType("browser_%s" % commit)
    m.__dict__["__name__"] = "browser_%s" % commit
    m.__dict__["__file__"] = "agent-v2/browser.py"
    exec(compile(proc.stdout.decode("utf-8"), "agent-v2/browser.py(%s)" % commit, "exec"), m.__dict__)
    return przygotuj(m)


przygotuj(browser)

print("=== 1. ZYWY WATEK: NA STRONIE JEST I „Reply”, I „Post” ===")
w, s = odpowiedz(browser, {"Reply": "otwieracz", "Post": "wysylka"})
sprawdz("klikniety zostaje „Post”", s.klikniete == ["Post"], s.klikniete)
sprawdz("odpowiedz naprawde poszla i jest potwierdzona w watku",
        s.wyslano and w.get("wyslane") is True, w)

print()
print("=== 2. KONTRDOWOD: TEN SAM SCENARIUSZ NA KODZIE Z %s ===" % ODNIESIENIE)
stary = modul_z_commita(ODNIESIENIE)
ws, ss = odpowiedz(stary, {"Reply": "otwieracz", "Post": "wysylka"})
sprawdz("stary kod klikal „Reply” (pierwszy widoczny)", ss.klikniete == ["Reply"], ss.klikniete)
sprawdz("i odpowiedz NIE poszla („KLIKNIETE, ALE ODPOWIEDZI NIE MA W WATKU”)",
        not ss.wyslano and ws.get("wyslane") is False, ws)

print()
print("=== 3. POZOSTALE UKLADY BEZ ZMIAN ===")
w, s = odpowiedz(browser, {"Post": "wysylka"})
sprawdz("sam „Post” dziala jak dotad", s.klikniete == ["Post"] and w.get("wyslane") is True, (s.klikniete, w))
for nazwa in ("Opublikuj", "Wyślij"):
    w, s = odpowiedz(browser, {nazwa: "wysylka"})
    sprawdz("interfejs po polsku: „%s” wysyla" % nazwa, w.get("wyslane") is True, w)
w, s = odpowiedz(browser, {"Reply": "otwieracz"})
sprawdz("gdy NIE MA innego przycisku, „Reply” zostaje ostatnia deska (probujemy, nie zostawiamy pustej reki)",
        s.klikniete == ["Reply"] and w.get("przycisk_widoczny") is True, (s.klikniete, w))
w, s = odpowiedz(browser, {})
sprawdz("bez zadnego przycisku nic nie klikamy i nie udajemy sukcesu",
        s.klikniete == [] and w.get("wyslane") is not True and w.get("przycisk_widoczny") is False, (s.klikniete, w))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
