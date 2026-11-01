# -*- coding: utf-8 -*-
"""Czyszczenie i weryfikacja pola przed wpisaniem tekstu (1.11.2026): `browser.wpisz_do_pola`.

PO CO. 1.11.2026 jedna odpowiedz pod cudzym komentarzem wyszla z doklejonym tekstem probnym „Dry run only - this text is never sent.” na
poczatku: moj test na zywo (`wyslij=False`) wpisal go w pole odpowiedzi, nie wyslal, a Substack zachowal SZKIC; potem bot odpisal tam naprawde
i `keyboard.type` dopisalo odpowiedz ZA szkicem. Test pilnuje, ze pole jest czyszczone, gdy cos w nim jest, ze po wpisaniu stoi w nim wylacznie nasz
tekst (z tolerancja na to, co edytor robi z cudzyslowami i spacjami), ze szkic, ktory wraca, konczy sie wyjatkiem (nic nie jest wysylane), ze
niemozliwosc odczytu pola NIE blokuje wysylki i ze wszystkie cztery miejsca wpisywania tekstu korzystaja z helpera.

BEZ PYTESTA, bez przegladarki, bez sieci. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_wpisz_do_pola.py
"""
import contextlib
import io
import pathlib
import re
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
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1200]))


class Edytor:
    """Atrapa contenteditable: zawartosc, zaznaczenie wszystkiego, opcjonalny „szkic wraca po skasowaniu”."""

    def __init__(self, tresc="", szkic_wraca=0, cudzyslow=False, nieczytelny=False, dopisek="", kapitalizuj=False, slepy_inner_text=False, slepy_wszystko=False):
        self.tresc = tresc
        self.szkic = tresc
        self.szkic_wraca = szkic_wraca          # ile razy po skasowaniu szkic wraca (autozapis)
        self.cudzyslow = cudzyslow
        self.nieczytelny = nieczytelny
        self.dopisek = dopisek                  # obcy tekst dopisywany przez edytor po kazdym wpisaniu (np. podpowiedz)
        self.kapitalizuj = kapitalizuj          # edytor zamienia pierwsza litere na wielka (autokorekta)
        self.slepy_inner_text = slepy_inner_text    # jak textarea w Chromium: innerText jest pusty, zywa wartosc czyta tylko `evaluate` (.value)
        self.slepy_wszystko = slepy_wszystko    # oba czytniki zwracaja pusty tekst (np. zmiana struktury strony)
        self.zaznaczone = False
        self.nacisniete = []


class Pole:
    def __init__(self, e):
        self.e = e

    def inner_text(self, timeout=None):
        if self.e.nieczytelny:
            raise RuntimeError("nie da sie odczytac")
        return "" if (self.e.slepy_inner_text or self.e.slepy_wszystko) else self.e.tresc

    def evaluate(self, js, timeout=None):
        if self.e.nieczytelny:
            raise RuntimeError("nie da sie odczytac")
        return "" if self.e.slepy_wszystko else self.e.tresc

    def click(self, timeout=None):
        pass


class Klawiatura:
    def __init__(self, e):
        self.e = e

    def type(self, tekst, delay=0):
        if self.e.kapitalizuj:
            tekst = tekst[:1].upper() + tekst[1:]
        self.e.tresc += tekst.replace("'", "’").replace('"', "”") if self.e.cudzyslow else tekst
        self.e.tresc += self.e.dopisek

    def press(self, klawisz):
        self.e.nacisniete.append(klawisz)
        if klawisz == "Control+a":
            self.e.zaznaczone = True
        elif klawisz == "Delete":
            if self.e.zaznaczone:
                self.e.tresc = ""
                self.e.zaznaczone = False
                if self.e.szkic_wraca > 0:
                    self.e.szkic_wraca -= 1
                    self.e.tresc = self.e.szkic


class Strona:
    def __init__(self, e):
        self.keyboard = Klawiatura(e)

    def wait_for_timeout(self, ms):
        pass


def wpisz(e, tekst):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        browser.wpisz_do_pola(Strona(e), Pole(e), tekst)
    return log.getvalue()


TEKST = "The date is the easy part; the harder part is what \"verified\" means. What would you want that tag to say?"

print("=== 1. CZYSTE POLE ===")
e = Edytor("")
wpisz(e, TEKST)
sprawdz("puste pole: wpisany dokladnie nasz tekst, nic nie czyszczono", e.tresc == TEKST and e.nacisniete == [], (e.tresc, e.nacisniete))

print("=== 2. SZKIC W POLU (przypadek z 1.11) ===")
e = Edytor("Dry run only - this text is never sent.")
log = wpisz(e, TEKST)
sprawdz("szkic zostal skasowany: w polu wylacznie nasz tekst", e.tresc == TEKST, e.tresc)
sprawdz("skasowany szkic zostawia slad w logu (bez jego tresci), zeby dalo sie zobaczyc na produkcji, ze poprawka dziala",
        "[pole] w polu byl szkic" in log and "Dry run" not in log, log)
log_czyste = wpisz(Edytor(""), TEKST)
sprawdz("czyste pole nie zostawia sladu w logu", "[pole]" not in log_czyste, log_czyste)
sprawdz("czyszczenie zaznacza wszystko i kasuje", e.nacisniete[:2] == ["Control+a", "Delete"], e.nacisniete)
e = Edytor(TEKST)
wpisz(e, TEKST)
sprawdz("szkic identyczny z naszym tekstem nie podwaja go", e.tresc == TEKST, e.tresc)
e = Edytor("  \n ")
wpisz(e, TEKST)
sprawdz("same biale znaki w polu to puste pole (bez czyszczenia)", e.tresc.endswith(TEKST) and e.nacisniete == [], (e.tresc, e.nacisniete))

print("=== 3. SZKIC, KTORY WRACA ===")
e = Edytor("Dry run only - this text is never sent.", szkic_wraca=1)
wpisz(e, TEKST)
sprawdz("szkic wraca raz po skasowaniu: druga proba go usuwa i wpisuje sam nasz tekst", e.tresc == TEKST, e.tresc)
e = Edytor("Dry run only - this text is never sent.", szkic_wraca=5)
try:
    wpisz(e, TEKST)
    wyjatek = None
except RuntimeError as exc:
    wyjatek = exc
sprawdz("szkic wraca zawsze: RuntimeError (nic nie jest wysylane), z wyjasnieniem", wyjatek is not None and "obcy tekst" in str(wyjatek), wyjatek)

e = Edytor("Draft: ok", szkic_wraca=5)
try:
    wpisz(e, TEKST)
    wyjatek = None
except RuntimeError as exc:
    wyjatek = exc
sprawdz("KROTKI obcy prefiks (mieszczacy sie w marginesie dlugosci), ktory wraca: RuntimeError (liczy sie tez poczatek, nie tylko dlugosc)", wyjatek is not None, e.tresc)

e = Edytor("", dopisek=" SPONSORED LINK click here to subscribe now and get a big discount")
try:
    wpisz(e, TEKST)
    wyjatek = None
except RuntimeError as exc:
    wyjatek = exc
sprawdz("obcy tekst DOPISANY po naszym (dluzszy niz margines): RuntimeError, nic nie jest wysylane", wyjatek is not None, e.tresc)

print("=== 4. TOLERANCJA EDYTORA ===")
e = Edytor("", cudzyslow=True)
wpisz(e, TEKST + " It's fine.")
sprawdz("edytor zamienia cudzyslowy na typograficzne: nadal przechodzi", e.tresc.endswith("fine.") and "”" in e.tresc, e.tresc)
e = Edytor("")
wpisz(e, "Short.")
sprawdz("krotki tekst (< 40 znakow alfanumerycznych)", e.tresc == "Short.")
e = Edytor("Zażółć gęślą jaźń " * 3)
wpisz(e, "Żółć i gęś: polskie znaki zostają, bo porównanie je zna.")
sprawdz("polskie znaki w tekscie i szkicu", e.tresc == "Żółć i gęś: polskie znaki zostają, bo porównanie je zna.", e.tresc)

e = Edytor("", kapitalizuj=True)
wpisz(e, "the date is the easy part; the harder part is what verified means.")
sprawdz("edytor zamienia pierwsza litere na wielka (autokorekta): porownanie nie rozroznia wielkosci liter", e.tresc.startswith("The date"), e.tresc)

e = Edytor("Dry run only - this text is never sent.", slepy_inner_text=True)
wpisz(e, TEKST)
sprawdz("textarea: innerText pusty, ale `.value` czytelne: szkic jest czyszczony i stoi sam nasz tekst (pole z incydentu 1.11)", e.tresc == TEKST, e.tresc)
e = Edytor("", dopisek=" Dry run only - this text is never sent.")
try:
    wpisz(e, TEKST)
    wyjatek = None
except RuntimeError as exc:
    wyjatek = exc
sprawdz("ogon o dlugosci tekstu z incydentu (29 znakow alfanumerycznych) dopisany za naszym tekstem: RuntimeError", wyjatek is not None, e.tresc)

print("=== 5. POLE NIECZYTELNE ===")
e = Edytor("", nieczytelny=True)
log = wpisz(e, TEKST)
sprawdz("nie da sie odczytac pola: nie blokuje (wpisuje i mowi o tym w logu)", e.tresc == TEKST and "nie umiem odczytac" in log, (e.tresc, log))
e = Edytor("", slepy_wszystko=True)
log = wpisz(e, TEKST)
sprawdz("czytnik slepy (pusty odczyt po wpisaniu niepustego tekstu): NIE blokuje, wpisuje i mowi o tym w logu",
        e.tresc == TEKST and "wyglada na puste" in log, (e.tresc, log))

print("=== 5b. PRAWDZIWY CHROMIUM: TEXTAREA I CONTENTEDITABLE ZE SZKICEM ===")
SZKIC = "Dry run only - this text is never sent."
_pw = _przegladarka = None
try:
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    _przegladarka = _pw.chromium.launch()
except Exception as exc:                                                          # noqa: BLE001
    sprawdz("Chromium dostepny (test wymaga prawdziwej przegladarki, jak test_odpowiedz_pod_artykulem)", False, exc)
else:
    try:
        strona = _przegladarka.new_page()
        for nazwa, html, wartosc in (
                ("textarea", '<textarea style="width:420px;height:90px">%s</textarea>', "document.querySelector('textarea').value"),
                ("contenteditable", '<div contenteditable="true" style="width:420px;height:90px;border:1px solid">%s</div>',
                 "document.querySelector('[contenteditable]').innerText")):
            sel = "textarea" if nazwa == "textarea" else "[contenteditable=true]"
            for opis, tresc in (("ze szkicem", SZKIC), ("puste", "")):
                strona.set_content(html % tresc)
                strona.locator(sel).first.click()                                  # tak jak w bocie: wywolujacy klika pole przed helperem
                with contextlib.redirect_stdout(io.StringIO()):
                    browser.wpisz_do_pola(strona, strona.locator(sel).first, TEKST)
                wynik = strona.evaluate("() => " + wartosc).strip()
                sprawdz("prawdziwy Chromium, %s %s: po wpisaniu stoi dokladnie nasz tekst" % (nazwa, opis), wynik == TEKST, wynik)
    finally:
        _przegladarka.close()
        _pw.stop()

print("=== 6. WPIECIE W browser.py ===")
src = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
sprawdz("jedyne `page.keyboard.type(tekst` jest w helperze", src.count("page.keyboard.type(tekst") == 1
        and src.index("page.keyboard.type(tekst") > src.index("def wpisz_do_pola("))
sprawdz("wszystkie 4 miejsca wpisywania tekstu wolaja helper", src.count("wpisz_do_pola(page, pole, tekst)") == 4, src.count("wpisz_do_pola(page, pole, tekst)"))
for nazwa in ("wystaw_odpowiedz_pod_artykulem", "wystaw_odpowiedz", "wystaw_notke", "wystaw_komentarz"):
    i = src.index("\ndef %s(" % nazwa)
    j = src.index("\ndef ", i + 5)
    sprawdz("%s: wpisuje przez helper" % nazwa, "wpisz_do_pola(page, pole, tekst)" in src[i:j])
sprawdz("helper czyta zawartosc pola przed i po wpisaniu oraz ma druga probe", src.count("odczytaj()") >= 3 and "for _ in range(2)" in src)

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
