"""Shared editor lookup chooses a visible editable field and handles its absence.
The preflight tests in test_pakiet_oszczednosci cover checking BEFORE drafting.
"""
import sys

sys.path.insert(0, "agent-v2")
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


class Pole:
    def __init__(self, strona, i, widoczne):
        self.strona, self.i, self.widoczne = strona, i, widoczne

    def is_visible(self):
        return self.widoczne

    def is_editable(self):
        return self.widoczne

    def count(self):
        return 1

    def click(self, **k):
        # Limit zapisujemy ZAWSZE, takze przy nieudanym klikaniu: to jedyna
        # liczba, ktora agent naprawde podaje Playwrightowi, i tylko ona mowi,
        # ile sekund kosztuje nas post bez pola komentarza.
        self.strona.limity.append(k.get("timeout"))
        if not self.widoczne:
            # Dokladnie to robi Playwright: czeka do timeoutu i rzuca.
            raise TimeoutError("Locator.click: Timeout %sms exceeded."
                               % k.get("timeout", 15000))
        self.strona.klikniete.append(self.i)


class Lista:
    def __init__(self, strona, pola):
        self.strona, self.pola = strona, pola

    def count(self):
        return len(self.pola)

    def nth(self, i):
        return Pole(self.strona, i, self.pola[i])

    @property
    def first(self):
        if not self.pola:
            return Pole(self.strona, 0, False)     # nie ma czego kliknac
        return Pole(self.strona, 0, self.pola[0])

    def is_visible(self):
        return bool(self.pola) and self.pola[0]


class Przycisk:
    def count(self):
        return 1

    def is_visible(self):
        return True

    def click(self, **k):
        pass


class Strona:
    """`pola` to lista widocznosci kolejnych textarea w DRZEWIE."""

    def __init__(self, pola):
        self.pola = pola
        self.klikniete = []
        self.limity = []          # z jakim `timeout` przyszlo kazde klikniecie
        self.wpisane = []
        self.keyboard = self
        self.mouse = self

    def goto(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass

    def wheel(self, *a):
        pass

    def locator(self, sel):
        return Lista(self, self.pola if sel == "textarea" else [])

    def get_by_role(self, rola, name=None, **k):
        return Lista(self, []) if rola != "button" else _PrzyciskiLista()

    def type(self, tekst, **k):
        self.wpisane.append(tekst)

    def close(self):
        pass


class _PrzyciskiLista:
    @property
    def first(self):
        return Przycisk()


class Nic:
    def close(self):
        pass

    def stop(self):
        pass


class Kontekst:
    def __init__(self, strona):
        self.strona = strona

    def new_page(self):
        return self.strona


def komentuj(pola, wyslij=False):
    strona = Strona(pola)
    oryg = (browser.podlacz_sie, browser.wymagaj_sesji, browser.naprawde_wyslac,
            browser.juz_sie_odezwalismy, browser.potwierdz_komentarz)
    browser.podlacz_sie = lambda: (Nic(), Nic(), Kontekst(strona))
    browser.wymagaj_sesji = lambda: None
    browser.naprawde_wyslac = lambda w, r: w
    browser.juz_sie_odezwalismy = lambda p, u: False
    browser.potwierdz_komentarz = lambda p, u, t=None: False
    try:
        w = browser.wystaw_komentarz("https://ktos.substack.com/p/cos",
                                     "Nasze zdanie o mechanizmie.", wyslij=wyslij)
    finally:
        (browser.podlacz_sie, browser.wymagaj_sesji, browser.naprawde_wyslac,
         browser.juz_sie_odezwalismy, browser.potwierdz_komentarz) = oryg
    return w, strona


print("=== 1. JEDNA WIDOCZNA TEXTAREA — ZWYKLY PRZYPADEK ===")
w, s = komentuj([True])
sprawdz("wpisalo sie", w["wpisane"] is True, w)
sprawdz("bez bledu", w["blad"] is None, w["blad"])
sprawdz("kliknieto pole nr 0", s.klikniete == [0], s.klikniete)

print()
print("=== 2. PRZED WLASCIWYM POLEM STOI UKRYTE ===")
# Tu stary selektor bral ukryta i czekal 15 s, choc wlasciwe pole bylo nizej.
w, s = komentuj([False, True])
sprawdz("wpisalo sie mimo ukrytej na poczatku", w["wpisane"] is True, w)
sprawdz("wybrano DRUGA, czyli pierwsza widoczna", s.klikniete == [1], s.klikniete)

print()
print("=== 3. NIE MA ZADNEJ TEXTAREA — TO NIE JEST AWARIA ===")
# Dokladnie przypadek z produkcji: post bez pola komentarza.
w, s = komentuj([])
sprawdz("nie wpisano nic", w["wpisane"] is False, w)
sprawdz("blad nazywa rzecz po imieniu",
        w["blad"] and "pola komentarza" in w["blad"], w["blad"])
sprawdz("nie mowi o lokatorze ani o czasie",
        w["blad"] and "Timeout" not in w["blad"] and "locator" not in w["blad"],
        w["blad"])
sprawdz("nic nie kliknieto", s.klikniete == [], s.klikniete)

print()
print("=== 4. SAME UKRYTE — TAK SAMO ===")
w, s = komentuj([False, False, False])
sprawdz("nie wpisano nic", w["wpisane"] is False, w)
sprawdz("i nie wywalilo sie", w["blad"] and "pola komentarza" in w["blad"],
        w["blad"])

print()
print("=== 5. KONTRDOWOD: STARY SPOSOB TU PADAL ===")
# Bez tego test potwierdzalby tylko moja poprawke. Odtwarzamy stary selektor
# doslownie: `locator("textarea").first.click(timeout=15000)`.
for opis, pola in (("brak textarea", []), ("pierwsza ukryta", [False, True])):
    strona = Strona(pola)
    try:
        strona.locator("textarea").first.click(timeout=15_000)
        sprawdz("stary sposob padal: %s" % opis, False,
                "przeszedl — test NIE odroznia wersji")
    except TimeoutError as e:
        sprawdz("stary sposob padal: %s" % opis, True)
        print("        (%s)" % e)

print()
print("=== 6. NOWY SPOSOB CZEKA KROCEJ, GDY JUZ MUSI ===")
# MIERZONE, NIE CZYTANE Z NAPISU. Do 2 wrzesnia stalo tu
# `"pole.click(timeout=8_000)" in zrodlo` — asercja, ktora oblewa przy zapisie
# `8000` zamiast `8_000` (ta sama liczba, to samo zachowanie) i przechodzi,
# gdy klikanie wyladuje w galezi, do ktorej przebieg nie dochodzi.
# Atrapa zapisuje teraz limit, z ktorym Playwright DOSTAJE polecenie.
w, s = komentuj([True])
sprawdz("pole naprawde kliknieto", s.klikniete == [0], s.klikniete)
sprawdz("limit na klikniecie pola zszedl z 15 s", s.limity == [8_000], s.limity)
# Przy poscie BEZ pola komentarza — przypadek z produkcji — nie czekamy wcale.
w2, s2 = komentuj([])
sprawdz("i nie zostal nigdzie stary 15-sekundowy",
        all(t is not None and t < 15_000 for t in s.limity + s2.limity),
        s.limity + s2.limity)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
