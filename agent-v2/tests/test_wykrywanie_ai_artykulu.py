# -*- coding: utf-8 -*-
"""Przelacznik wykrywania AI przy artykule (26.10.2026).

PO CO. Substack zmienil napis przycisku w oknie ustawien z „Turn off AI detection” na „Disable AI detection”
(sekcja „Text Analysis”). Kod szukal starego napisu i PO CICHU szedl dalej: artykul 0496 (25.10) wyszedl z
plakietka, a w logu nie bylo ani slowa. To ustawienie PLATFORMY, sterowane przez autora (decyzja wlasciciela
z 15.08.2026); nie zmienia tekstu.

Test na atrapie strony (bez przegladarki i bez sieci) pilnuje:
  1. rozpoznania dzisiejszego, starego i polskiego napisu — po wzorcu, nie po jednym napisie;
  2. ze sukces jest SPRAWDZANY (przycisk zmienia sie w „Re-enable” albo znika), nie meldowany;
  3. ze brak przycisku albo martwe klikniecie daja GLOSNE ostrzezenie i False, a publikacja idzie dalej (nic nie rzuca);
  4. ze nie klika niczego innego („Scan for AI text”, „Send to everyone now”, „Cancel”).

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_wykrywanie_ai_artykulu.py
"""
import contextlib
import io
import sys

sys.path.insert(0, "agent-v2")
import browser  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:900]))


class Przycisk:
    def __init__(self, strona, tekst, po_kliknieciu=None, rzuca=False, widoczny=True):
        self.strona, self.tekst, self.po, self.rzuca, self.widoczny = strona, tekst, po_kliknieciu, rzuca, widoczny

    def is_visible(self):
        return self.widoczny

    def inner_text(self):
        return self.tekst

    def click(self, timeout=None):
        self.strona.klikniete.append(self.tekst)
        if self.rzuca:
            raise RuntimeError("klikniecie padlo")
        if self.po is not None:
            self.strona.przyciski = [p for p in self.strona.przyciski if p is not self]
            if self.po:
                self.strona.przyciski.append(Przycisk(self.strona, self.po))


class Strona:
    def __init__(self, teksty, **k):
        self.klikniete = []
        self.przyciski = []
        for t in teksty:
            po = k.get("po", {}).get(t)
            self.przyciski.append(Przycisk(self, t, po_kliknieciu=po, rzuca=k.get("rzuca") == t))

    def query_selector_all(self, sel):
        return list(self.przyciski) if sel == "button" else []

    def wait_for_timeout(self, ms):
        pass


def uruchom(teksty, **k):
    s = Strona(teksty, **k)
    bufor = io.StringIO()
    with contextlib.redirect_stdout(bufor):
        wynik = browser.wylacz_wykrywanie_ai_artykulu(s)
    return wynik, s, bufor.getvalue()


OKNO = ["Cancel", "Scan for AI text", "{WYLACZ}", "Send to everyone now", "Settings", "Continue"]


def okno(napis):
    return [napis if t == "{WYLACZ}" else t for t in OKNO]


print("=== 1. NAPISY: DZISIEJSZY, STARY, POLSKI ===")
for napis, po in (("Disable AI detection", "Re-enable AI detection"), ("Turn off AI detection", "Turn on AI detection"),
                  ("Wyłącz wykrywanie AI", "Włącz wykrywanie AI"), ("Disable detection", "Enable detection")):
    wynik, s, log = uruchom(okno(napis), po={napis: po})
    sprawdz("%r: klika i zglasza sukces po sprawdzeniu" % napis, wynik is True and s.klikniete == [napis]
            and "sprawdzone" in log, (wynik, s.klikniete, log))

print()
print("=== 2. NIC INNEGO NIE KLIKA ===")
wynik, s, log = uruchom(okno("Disable AI detection"), po={"Disable AI detection": "Re-enable AI detection"})
sprawdz("nie klika „Scan for AI text”, „Send to everyone now”, „Cancel”, „Continue”",
        s.klikniete == ["Disable AI detection"], s.klikniete)

print()
print("=== 3. PORAZKA JEST GLOSNA, A PUBLIKACJA IDZIE DALEJ ===")
wynik, s, log = uruchom(["Cancel", "Scan for AI text", "Send to everyone now"])
sprawdz("brak przycisku: False, brak klikniec, ostrzezenie z lista przyciskow okna",
        wynik is False and not s.klikniete and "UWAGA" in log and "Scan for AI text" in log, (wynik, log))
wynik, s, log = uruchom(okno("Disable AI detection"))   # klikniecie nic nie zmienia
sprawdz("martwe klikniecie (przycisk nadal ten sam): False i ostrzezenie, nie falszywy sukces",
        wynik is False and "UWAGA" in log and "nie wylaczylo" in log, (wynik, log))
wynik, s, log = uruchom(okno("Disable AI detection"), rzuca="Disable AI detection")
sprawdz("wyjatek przy kliknieciu: False, ostrzezenie, NIC NIE RZUCA (publikacja idzie dalej)",
        wynik is False and "UWAGA" in log and "padlo" in log, (wynik, log))
wynik, s, log = uruchom(["Cancel", "Re-enable AI detection", "Send to everyone now"])
sprawdz("juz wylaczone (jest tylko „Re-enable”): True bez klikania", wynik is True and not s.klikniete
        and "juz wylaczone" in log, (wynik, s.klikniete, log))
wynik, s, log = uruchom(okno("Disable AI detection"), po={"Disable AI detection": ""})
sprawdz("przycisk znika po kliknieciu (bez „Re-enable”): uznane za sukces", wynik is True, (wynik, log))

print()
print("=== 4. PODLACZENIE W PUBLIKACJI ===")
kod = open("agent-v2/browser.py", encoding="utf-8").read()
sprawdz("wystaw_artykul wola nowa funkcje i zapisuje wynik do `wynik`",
        'wynik["wykrywanie_ai_wylaczone"] = wylacz_wykrywanie_ai_artykulu(page)' in kod
        and "Turn off AI detection" not in kod.split("def wystaw_artykul")[1].split("publikuj = None")[0])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
