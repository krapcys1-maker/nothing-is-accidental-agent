"""Test rozdzielenia obserwacji od subskrypcji i roznorodnosci notek.

Kazda zmiana z kontrdowodem. Nic nie publikuje.
"""
import hashlib
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v3")
import browser  # noqa: E402
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


def odcisk(p):
    p = pathlib.Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "brak"


PILNOWANE = [config.DB_PATH, config.DATA_DIR / "zuzyte_fakty.json",
             config.DATA_DIR / "promocja.json", config.DATA_DIR / "dziennik.jsonl"]
PRZED = {str(p): odcisk(p) for p in PILNOWANE}

print("=== 1. OBSERWOWANIE KLIKA TYLKO 'FOLLOW' ===")

klikniete = []


class Przycisk:
    def __init__(self, nazwa, jest):
        self.nazwa, self.jest = nazwa, jest
        self.first = self

    def count(self):
        return 1 if self.jest else 0

    def is_visible(self):
        return self.jest

    def click(self, timeout=None):
        klikniete.append(self.nazwa)
        self.jest = False


class Strona:
    def __init__(self, dostepne):
        self.dostepne = dostepne
        self.przyciski = {}

    def goto(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass

    def get_by_role(self, rola, name=None, exact=None):
        if name not in self.przyciski:
            self.przyciski[name] = Przycisk(name, name in self.dostepne)
        return self.przyciski[name]

    def close(self):
        pass


class Kontekst:
    def __init__(self, strona):
        self.strona = strona

    def new_page(self):
        return self.strona

    def close(self):
        pass

    def stop(self):
        pass


class Proba:
    id = "fake-attempt"
    idempotency_key = "fake-key"
    status = "CONFIRMED"
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def dispatch(self): pass
    def confirm(self, *_args, **_kwargs): pass
    def unknown(self, *_args, **_kwargs): pass


oryg = (browser.podlacz_sie, browser.wymagaj_sesji,
        browser.wymagaj_wlasciwego_konta, browser.DZIENNIK,
        browser.naprawde_wyslac, browser.proba_mutacji)


def ustaw(dostepne):
    klikniete.clear()
    s = Strona(dostepne)
    browser.wymagaj_sesji = lambda: None
    browser.wymagaj_wlasciwego_konta = lambda _page: None
    browser.podlacz_sie = lambda: (Kontekst(s), Kontekst(s), Kontekst(s))
    browser.naprawde_wyslac = lambda wyslij, co, _capability: wyslij
    browser.proba_mutacji = lambda *_args, **_kwargs: Proba()
    browser.DZIENNIK = pathlib.Path(tempfile.mkdtemp()) / "d.jsonl"


try:
    # Profil, na ktorym sa OBA przyciski — tak wyglada kazdy profil Substacka.
    ustaw({"Subscribe", "Follow"})
    w = browser.obserwuj_profil("ktos", wyslij=True)
    sprawdz("obserwowanie klika 'Follow'", klikniete == ["Follow"], klikniete)
    sprawdz("i NIE klika 'Subscribe'", "Subscribe" not in klikniete, klikniete)
    sprawdz("melduje sukces", w["zrobione"] is True, w)

    ustaw({"Subscribe", "Follow"})
    browser.zasubskrybuj("ktos", wyslij=True)
    sprawdz("subskrypcja klika 'Subscribe'", klikniete == ["Subscribe"], klikniete)
    sprawdz("i NIE klika 'Follow'", "Follow" not in klikniete, klikniete)

    # KONTRDOWOD: stara kolejnosc na tym samym profilu.
    stara_kolejnosc = ("Subscribe", "Subskrybuj", "Follow", "Obserwuj")
    pierwszy_stary = next(n for n in stara_kolejnosc if n in {"Subscribe", "Follow"})
    sprawdz("STARA kolejnosc wybralaby 'Subscribe' (test rozroznia)",
            pierwszy_stary == "Subscribe")

    # Gdy wlasciwego przycisku NIE MA — nie wolno kliknac zastepczego.
    ustaw({"Subscribe"})
    w = browser.obserwuj_profil("ktos", wyslij=True)
    sprawdz("brak 'Follow' -> NIE klika nic", klikniete == [], klikniete)
    sprawdz("i melduje, ze sie nie udalo", w["zrobione"] is False, w)
    sprawdz("z powodem", "obserwacja" in (w["blad"] or ""), w["blad"])

    ustaw({"Follow"})
    browser.zasubskrybuj("ktos", wyslij=True)
    sprawdz("brak 'Subscribe' -> subskrypcja tez nic nie klika", klikniete == [],
            klikniete)

    # Polska wersja interfejsu
    ustaw({"Obserwuj", "Subskrybuj"})
    browser.obserwuj_profil("ktos", wyslij=True)
    sprawdz("dziala po polsku: 'Obserwuj'", klikniete == ["Obserwuj"], klikniete)

    # Tryb sprawdzenia nie klika
    ustaw({"Subscribe", "Follow"})
    browser.obserwuj_profil("ktos", wyslij=False)
    sprawdz("tryb sprawdzenia nie klika nic", klikniete == [], klikniete)
finally:
    (browser.podlacz_sie, browser.wymagaj_sesji,
     browser.wymagaj_wlasciwego_konta, browser.DZIENNIK,
     browser.naprawde_wyslac, browser.proba_mutacji) = oryg

print()
print("=== 2. OSOBNE BUDZETY ===")

zrodlo = pathlib.Path("agent-v3/run.py").read_text(encoding="utf-8")
sprawdz("blok obserwowania uzywa budzetu 'follow'",
        'if not na_teraz.get("follow")' in zrodlo)
sprawdz("blok subskrypcji uzywa budzetu 'subskrypcje'",
        'if not na_teraz.get("subskrypcje")' in zrodlo)
sprawdz("obserwowanie wola obserwuj_profil, nie zasubskrybuj",
        "browser.obserwuj_profil(uchwyt, wyslij=True)" in zrodlo)
sprawdz("subskrypcje sa osobnym blokiem dnia",
        '("subskrypcje", subskrybuj)' in zrodlo)
print("    widelki: obserwacje %s/mies, subskrypcje %s/mies"
      % (config.FOLLOW_MIESIECZNIE, config.SUBSKRYPCJE_MIESIECZNIE))
sprawdz("subskrypcji ma byc wyraznie mniej niz obserwacji",
        config.SUBSKRYPCJE_MIESIECZNIE[1] < config.FOLLOW_MIESIECZNIE[0])

print()
print("=== 3. NOTKI NIE POWTARZAJA TEMATU ===")

ARTYKUL = ("The Egg Aisle Is a Legal Document  American rules make eggs cold. "
           "European rules forbid chilling Class A eggs. Refrigeration is "
           "regulation, not habit.")
PULA = [
    {"domain": "Grocery and food safety",
     "fact": "American eggs must be refrigerated because US federal rules require "
             "that shell eggs be washed and sanitized, stripping the cuticle."},
    {"domain": "Air travel", "fact": "The tiny hole in the middle pane of an "
     "airplane window is a bleed hole that vents cabin pressure."},
    {"domain": "Restaurants", "fact": "Under the tip credit, US employers can pay "
     "tipped staff a lower base wage if tips make up the difference."},
]

zapas = list(PULA)
wybrany = stages.wybierz_material(zapas, [ARTYKUL])
print("    artykul dnia: eggs / refrigeration")
print("    wybrano:      %s" % (wybrany or {}).get("domain"))
sprawdz("NIE wybiera faktu o jajkach, gdy artykuł jest o jajkach",
        wybrany is not None and "egg" not in wybrany["fact"].lower(), wybrany)
sprawdz("wybiera pierwszy NIEKOLIDUJACY", wybrany["domain"] == "Air travel",
        wybrany["domain"])
sprawdz("zdjety z zapasu", len(zapas) == 2, len(zapas))

# KONTRDOWOD: stary sposob wzialby pierwszy z brzegu, czyli jajka.
sprawdz("STARY sposob wzialby fakt o jajkach (test rozroznia)",
        "egg" in PULA[0]["fact"].lower())

# Druga notka w tym samym przebiegu tez nie moze byc o tym samym.
juz = [ARTYKUL, "%s %s" % (wybrany["domain"], wybrany["fact"])]
drugi = stages.wybierz_material(zapas, juz)
sprawdz("druga notka to znowu inny temat",
        drugi is not None and drugi["domain"] == "Restaurants", drugi)

# Gdy zostaje juz tylko materiał o tym samym — lepiej mniej niz powtorka.
sprawdz("gdy wszystko koliduje -> None, zamiast powtorzyc",
        stages.wybierz_material([dict(PULA[0])], [ARTYKUL]) is None)
sprawdz("pusty zapas -> None", stages.wybierz_material([], [ARTYKUL]) is None)
sprawdz("brak czego unikac -> bierze pierwszy",
        stages.wybierz_material(list(PULA), [])["domain"] == "Grocery and food safety")

print()
print("=== 4. MIARA PODOBIENSTWA ===")

sprawdz("ten sam temat rozpoznany",
        stages._o_tym_samym(ARTYKUL, PULA[0]["fact"]) is True)
sprawdz("inny temat NIE jest mylony",
        stages._o_tym_samym(ARTYKUL, PULA[1]["fact"]) is False)
sprawdz("krotkie teksty nie sa oceniane (za malo slow)",
        stages._o_tym_samym("eggs", "eggs") is False)

print()
print("=== 5. FAKT W PAMIECI ZUZYTYCH TO ZDANIE, NIE SLOWNIK ===")

oryg_plik = stages.ZUZYTE_FAKTY
stages.ZUZYTE_FAKTY = pathlib.Path(tempfile.mkdtemp()) / "z.json"
try:
    stages.zapisz_zuzyte([{"fact": "fakt ze slownika", "url": "http://x"}])
    stages.zapisz_zuzyte(["zwykle zdanie"])
    wczytane = stages.wczytaj_zuzyte()
    print("    w pliku: %s" % wczytane)
    sprawdz("slownik zapisany jako samo zdanie",
            "fakt ze slownika" in wczytane, wczytane)
    sprawdz("zdanie zapisane normalnie", "zwykle zdanie" in wczytane, wczytane)
    sprawdz("wszystko jest tekstem", all(isinstance(t, str) for t in wczytane))

    # KONTRDOWOD: to wlasnie wywalalo szukanie ciekawostek.
    try:
        stages._klucz_faktu({"fact": "x"})
        polecialo = False
    except AttributeError:
        polecialo = True
    sprawdz("slownik NADAL wywala _klucz_faktu (wiec musi byc odsiany wczesniej)",
            polecialo)

    # Plik zepsuty recznie — czytanie ma go posprzatac, nie paść.
    stages.ZUZYTE_FAKTY.write_text(
        '[{"fact": "ze slownika"}, "ze zdania", null, 5]', encoding="utf-8")
    w = stages.wczytaj_zuzyte()
    sprawdz("zepsuty plik sprzatany przy odczycie",
            w == ["ze slownika", "ze zdania", "5"], w)
    sprawdz("i nie wywala _klucz_faktu", all(
        isinstance(stages._klucz_faktu(t), str) for t in w))
finally:
    stages.ZUZYTE_FAKTY = oryg_plik

print()
print("=== PRODUKCJA ===")
zle = 0
for p in PILNOWANE:
    t = odcisk(p)
    ok = t == PRZED[str(p)]
    zle += 0 if ok else 1
    print("  %-24s %s" % (pathlib.Path(p).name, "bez zmian" if ok else "ZMIENIONA"))

print()
print("=== WYNIK: %s zdanych, %s oblanych%s ===" %
      (zdane, oblane, ", PRODUKCJA RUSZONA" if zle else ""))
sys.exit(1 if (oblane or zle) else 0)
