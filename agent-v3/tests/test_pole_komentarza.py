"""Wybor pola komentarza: pierwsza WIDOCZNA textarea, a brak pola to nie wyjatek.

Zlapane dwa razy pierwszego dnia na produkcji, na dwoch roznych publikacjach:

    BLAD: TimeoutError: Locator.click: Timeout 15000ms exceeded.
      - waiting for locator("textarea").first

Zapora `wolno_komentowac` czyta z API pole `write_comment_permissions` i przy
watpliwosci przepuszcza — swiadomie, bo blad w druga strone zamykalby agentowi
usta wszedzie tam, gdzie wartosci nie znamy. Sprawdzilem oba posty: API NIE
ODDAJE tego pola wcale, oddaje okrojony obiekt z samym `type`. Brak pola
przechodzi wiec jak zgoda, agent idzie pisac, a pod postem nie ma gdzie.

Do tego `locator("textarea").first` bralo pierwsza textarea w DRZEWIE, nie
pierwsza widoczna. Gdy pola nie bylo wcale albo gdy przed nim stala ukryta,
Playwright czekal pelne 15 sekund na aktywnosc elementu i konczyl wyjatkiem,
ktory nie niosl zadnej informacji poza nazwa lokatora.

Ten test pilnuje trzech rzeczy: ze bierzemy widoczna, ze brak pola konczy sie
zdaniem zamiast wyjatkiem, i ze stary sposob naprawde na tym padal.

CZEGO TEN TEST NIE NAPRAWIA, i trzeba to powiedziec wprost: trzy warianty
komentarza i sprawdzenie faktow sa juz OPLACONE, zanim w ogole otworzymy
strone. Poprawka zamienia 15 sekund czekania na natychmiastowe „nie ma pola",
ale nie odzyskuje tych pieniedzy. Zeby je odzyskac, trzeba by sprawdzac
obecnosc pola PRZED pisaniem — a to zmiana kolejnosci calego bloku i decyzja
wlasciciela, nie moja przy okazji.
"""
import sys
import pathlib
import tempfile

sys.path.insert(0, "agent-v3")
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

    def count(self):
        return 1

    def click(self, **k):
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
    def __init__(self, strona):
        self.strona = strona

    def count(self):
        return 1

    def is_visible(self):
        return True

    def click(self, **k):
        if self.strona.blad_klikniecia:
            raise TimeoutError("awaria po dispatch")


class Strona:
    """`pola` to lista widocznosci kolejnych textarea w DRZEWIE."""

    def __init__(self, pola, blad_klikniecia=False):
        self.pola = pola
        self.blad_klikniecia = blad_klikniecia
        self.klikniete = []
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
        return Lista(self, []) if rola != "button" else _PrzyciskiLista(self)

    def type(self, tekst, **k):
        self.wpisane.append(tekst)

    def close(self):
        pass


class _PrzyciskiLista:
    def __init__(self, strona):
        self.strona = strona

    @property
    def first(self):
        return Przycisk(self.strona)


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


class Proba:
    id = "fake-attempt"
    idempotency_key = "fake-key"
    def __init__(self):
        self.status = "PENDING"
        self.dispatched = False
    def __enter__(self): return self
    def __exit__(self, exc_type, *_args):
        if exc_type is not None and self.status == "PENDING":
            self.status = "UNKNOWN" if self.dispatched else "FAILED"
        return False
    def dispatch(self): self.dispatched = True
    def confirm(self, *_args, **_kwargs): self.status = "CONFIRMED"
    def unknown(self, *_args, **_kwargs): self.status = "UNKNOWN"


def komentuj(pola, wyslij=True, blad_klikniecia=False):
    strona = Strona(pola, blad_klikniecia=blad_klikniecia)
    tmp = tempfile.TemporaryDirectory()
    oryg = (browser.podlacz_sie, browser.wymagaj_sesji,
            browser.wymagaj_wlasciwego_konta, browser.naprawde_wyslac,
            browser.juz_sie_odezwalismy, browser.potwierdz_komentarz,
            browser.proba_mutacji, browser.DZIENNIK)
    browser.podlacz_sie = lambda: (Nic(), Nic(), Kontekst(strona))
    browser.wymagaj_sesji = lambda: None
    browser.wymagaj_wlasciwego_konta = lambda _page: None
    browser.naprawde_wyslac = lambda w, r, _capability: w
    browser.juz_sie_odezwalismy = lambda p, u: False
    browser.potwierdz_komentarz = lambda p, u, t=None: None
    browser.proba_mutacji = lambda *_args, **_kwargs: Proba()
    browser.DZIENNIK = pathlib.Path(tmp.name) / "dziennik-testowy.jsonl"
    try:
        w = browser.wystaw_komentarz("https://ktos.substack.com/p/cos",
                                     "Nasze zdanie o mechanizmie.", wyslij=wyslij)
    finally:
        (browser.podlacz_sie, browser.wymagaj_sesji,
         browser.wymagaj_wlasciwego_konta, browser.naprawde_wyslac,
         browser.juz_sie_odezwalismy, browser.potwierdz_komentarz,
         browser.proba_mutacji, browser.DZIENNIK) = oryg
        tmp.cleanup()
    return w, strona


print("=== 1. JEDNA WIDOCZNA TEXTAREA — ZWYKLY PRZYPADEK ===")
w, s = komentuj([True])
sprawdz("wpisalo sie", w["wpisane"] is True, w)
sprawdz("bez bledu", w["blad"] is None, w["blad"])
sprawdz("kliknieto pole nr 0", s.klikniete == [0], s.klikniete)
sprawdz("brak potwierdzenia daje UNKNOWN", w.get("status") == "UNKNOWN", w)

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
zrodlo = open("agent-v3/browser.py", encoding="utf-8").read()
sprawdz("limit na klikniecie pola zszedl z 15 s", "pole.click(timeout=8_000)" in zrodlo)
sprawdz("i nie zostal nigdzie stary 15-sekundowy",
        'page.locator("textarea").first\n        pole.click(timeout=15_000)'
        not in zrodlo)

print()
print("=== 7. WYJATEK PO DISPATCH ZACHOWUJE UNKNOWN W WYNIKU ===")
w, s = komentuj([True], blad_klikniecia=True)
sprawdz("wynik zachowal UNKNOWN", w.get("status") == "UNKNOWN", w)
sprawdz("wynik zachowal ID proby", w.get("attempt_id") == "fake-attempt", w)
sprawdz("blad nie zostal ukryty", "TimeoutError" in (w.get("blad") or ""), w)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
