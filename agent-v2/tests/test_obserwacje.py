"""Test rozdzielenia obserwacji od subskrypcji i roznorodnosci notek.

Kazda zmiana z kontrdowodem. Nic nie publikuje.
"""
import ast
import hashlib
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
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


oryg = (browser.podlacz_sie, browser.wymagaj_sesji, browser.DZIENNIK,
        browser.naprawde_wyslac)


def ustaw(dostepne):
    klikniete.clear()
    s = Strona(dostepne)
    browser.wymagaj_sesji = lambda: None
    browser.podlacz_sie = lambda: (Kontekst(s), Kontekst(s), Kontekst(s))
    browser.naprawde_wyslac = lambda wyslij, co: wyslij
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
    (browser.podlacz_sie, browser.wymagaj_sesji, browser.DZIENNIK,
     browser.naprawde_wyslac) = oryg

print()
print("=== 2. OSOBNE BUDZETY ===")

zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("blok obserwowania uzywa budzetu 'follow'",
        'budzet["follow"]' in zrodlo)
sprawdz("blok subskrypcji uzywa budzetu 'subskrypcje'",
        'budzet["subskrypcje"]' in zrodlo)
sprawdz("obserwowanie wola obserwuj_profil, nie zasubskrybuj",
        "browser.obserwuj_profil(uchwyt, wyslij=True)" in zrodlo)
sprawdz("subskrypcje sa osobnym blokiem dnia",
        '("subskrypcje", subskrybuj)' in zrodlo)
print("    widelki: obserwacje %s/mies, subskrypcje %s/mies"
      % (config.FOLLOW_MIESIECZNIE, config.SUBSKRYPCJE_MIESIECZNIE))
# Asercja wisiala na liczbie obserwacji: subskrypcji mialo byc mniej NIZ ICH.
# Po wycofaniu obserwacji (2026-08-23, Substack zdjal „Follow" z profili)
# obserwacji jest zero, wiec porownanie stalo sie niespelnialne — a bronilo
# rzeczy, ktora dalej jest prawdziwa i nie ma z obserwacjami nic wspolnego.
#
# Awaria, przed ktora to stalo: `_klik_na_profilu` probowal kolejno „Subscribe"
# i „Follow" i bral pierwszy znaleziony, a „Subscribe" jest zawsze — wiec kazda
# proba obserwacji konczyla sie SUBSKRYPCJA. Agent subskrybowal w tempie
# obserwacji, prosto do skrzynki wlasciciela. Miara tego bledu jest wielkosc
# BEZWZGLEDNA subskrypcji, nie ich stosunek do czegokolwiek.
sprawdz("subskrypcji jest malo, bo ladzia w skrzynce wlasciciela",
        config.SUBSKRYPCJE_MIESIECZNIE[1] <= 12, config.SUBSKRYPCJE_MIESIECZNIE)
sprawdz("i wielokrotnie mniej niz komentarzy, ktore nikogo nie zasypuja",
        config.SUBSKRYPCJE_MIESIECZNIE[1] * 4 < config.KOMENTARZE_DZIENNIE[0] * 30,
        (config.SUBSKRYPCJE_MIESIECZNIE, config.KOMENTARZE_DZIENNIE))
sprawdz("KONTRDOWOD: tempo obserwacji sprzed naprawy by tego nie przeszlo",
        not (30 <= 12))

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
print("=== 4b. PAMIEC NIE KONCZY SIE O POLNOCY ===")
# 23 i 24 sierpnia poszly dwie notki o tym samym symbolu otwartego sloika na
# butelce szamponu. Ten sam fakt, inne zdania. Ochrona istniala i dzialala —
# tylko `juz_o_tym` zaczynalo KAZDY DZIEN puste, wiec pytala wylacznie o to,
# co wystawiamy dzisiaj. Miedzy dniami zostawal `_klucz_faktu`, odcisk
# DOKLADNY, ktory na przeformulowaniu puszcza.
WCZORAJ = ("Open-jar symbol on a shampoo bottle means the product carries no "
           "expiry date at all. The number beside it counts months from the day "
           "the lid first comes off. Under 30 months of unopened durability, the "
           "law requires a printed best-before instead.")
DZIS = {"domain": "Cosmetics labelling",
        "fact": ("Your shampoo bottle carries that little open jar instead of an "
                 "expiry date, not alongside one. Under cosmetics law, anything "
                 "lasting more than 30 months unopened is excused from printing a "
                 "best-before at all.")}

sprawdz("dokladny odcisk faktu NIE lapie przeformulowania",
        stages._klucz_faktu(WCZORAJ) != stages._klucz_faktu(DZIS["fact"]))
sprawdz("ale rozmyta miara juz tak",
        stages._o_tym_samym(DZIS["fact"], WCZORAJ,
                            **stages.POROWNANIE_MIEDZY_DNIAMI) is True)
sprawdz("wiec material z wczoraj zostaje odrzucony",
        stages.wybierz_material([dict(DZIS)], [], [WCZORAJ]) is None)
# KONTRDOWOD: bez pamieci poprzednich dni ten sam material przechodzi — czyli
# test naprawde mierzy TE zmiane, a nie cokolwiek innego.
sprawdz("a bez tej pamieci przeszedlby (tak powstala wpadka)",
        stages.wybierz_material([dict(DZIS)], [])["domain"] == "Cosmetics labelling")

# Prog miedzy dniami MUSI byc ostrzejszy od dziennego, inaczej blokuje notki
# na przypadkowych slowach. Zmierzone: przy progu dziennym notka o cenach w UE
# zderzala sie z notka o filtrach UV na `nothing`, `number`, `whole`.
LUZNE_A = ("Sticker price in the EU is the whole price. VAT and every other tax "
           "are already inside the number on the shelf, so nothing is added at "
           "the till.")
LUZNE_B = ("Sunscreen's SPF number says nothing about the rays that age your "
           "skin. It measures UVB only, and the whole label turns on that.")
sprawdz("prog miedzy dniami jest ostrzejszy od dziennego",
        stages.POROWNANIE_MIEDZY_DNIAMI["prog"] > 0.15
        and stages.POROWNANIE_MIEDZY_DNIAMI["min_wspolnych"] > 2,
        stages.POROWNANIE_MIEDZY_DNIAMI)
sprawdz("i luzne zderzenie NIE blokuje notki",
        stages._o_tym_samym(LUZNE_A, LUZNE_B,
                            **stages.POROWNANIE_MIEDZY_DNIAMI) is False)

# Adres w notce promocyjnej nie jest tematem. Dwie notki z linkiem mialy trzy
# wspolne slowa — `https`, `substack`, nazwa publikacji — zanim ktokolwiek
# spojrzal, o czym sa.
Z_LINKIEM = "Airplane windows have a tiny hole. https://nothingisaccidental.substack.com/p/x"
Z_LINKIEM_2 = "Eggs are refrigerated in America. https://nothingisaccidental.substack.com/p/y"
sprawdz("adres nie wpada do slow tematu",
        not ({"https", "substa"} & stages._slowa(Z_LINKIEM)),
        sorted(stages._slowa(Z_LINKIEM)))
sprawdz("wiec dwie notki z linkiem nie sa 'o tym samym'",
        stages._o_tym_samym(Z_LINKIEM, Z_LINKIEM_2) is False)

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
print()
print("=== 6. OBSERWACJE WYCOFANE, BO PRZYCISKA NIE MA ===")
# Obserwacje nie wykonaly sie ANI RAZU i przez tygodnie wygladalo to na blad
# kolejnosci blokow albo za waski budzet. Moja pierwsza diagnoza byla tez
# bledna: myslalem, ze bierzemy uchwyt PUBLIKACJI zamiast uchwytu CZLOWIEKA.
# Sprawdzone na zywym API — dla wszystkich pieciu hostow z historii oba uchwyty
# sa IDENTYCZNE, wiec nie o to chodzilo.
#
# Prawdziwy powod, zmierzony 2026-08-23 na szesciu profilach (trzech obcych
# i trzech z naszej historii): Substack zdjal „Follow" ze stron profilowych.
# Zostalo „Subscribe" i „Message", a slowo „Follow" nie wystepuje w ich HTML
# ani razu — ani na `/@kto/notes`. Przycisk przetrwal tylko w widgetach
# „kogo obserwowac", czyli w liscie PODPOWIEDZI, ktorej ta funkcja unika
# od pierwszego dnia.
#
# Test pilnuje teraz, ze zdolnosc jest WYLACZONA SWIADOMIE, a nie zepsuta.

sprawdz("norma obserwacji to zero", config.FOLLOW_MIESIECZNIE == (0, 0),
        config.FOLLOW_MIESIECZNIE)
sprawdz("i powod stoi przy stalej, nie w commicie",
        "Substack zdjal" in pathlib.Path("agent-v2/config.py").read_text(
            encoding="utf-8"))
sprawdz("subskrypcje NIETKNIETE — to osobna, dzialajaca zdolnosc",
        config.SUBSKRYPCJE_MIESIECZNIE[1] > 0, config.SUBSKRYPCJE_MIESIECZNIE)

# Zerowa norma nie moze wysadzic licznika ani udawac awarii. Rubryka wiecznie
# na zerze czytalaby sie jak „cos jest zepsute" — a tu nie ma czego naprawiac.
sprawdz("licznik zna rodzaj 'obserwacja'", "obserwacja" in config.normy_dzienne())
sprawdz("i jego norma dzienna to zero",
        config.normy_dzienne()["obserwacja"] == 0)

with tempfile.TemporaryDirectory() as tmp:
    stary_kat = config.DATA_DIR
    try:
        config.DATA_DIR = pathlib.Path(tmp)
        (config.DATA_DIR / "dziennik.jsonl").write_text(
            '{"rodzaj": "lajk", "udane": true, "kiedy": "2999-01-01T00:00:00Z"}\n',
            encoding="utf-8")
        pods = stages.podsumowanie_dzialan(7)
    finally:
        config.DATA_DIR = stary_kat
    obs = pods.get("obserwacja", {})
    sprawdz("zerowa norma nie dzieli przez zero", isinstance(pods, dict))
    sprawdz("realizacja to BRAK, a nie 0% — inaczej wyglada jak awaria",
            obs.get("realizacja") is None, obs.get("realizacja"))

# KONTRDOWOD: to wylaczenie jedna stala, a nie wyprucie bloku. Gdyby przycisk
# wrocil, blok ma byc na miejscu i gotowy — inaczej „wycofane" znaczy „usuniete"
# i nikt tego nie odkreci.
zrodlo_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
drzewo = ast.parse(zrodlo_run)
blok = [w for w in ast.walk(drzewo)
        if isinstance(w, ast.FunctionDef) and w.name == "obserwuj"]
sprawdz("blok obserwacji NADAL ISTNIEJE w kodzie", len(blok) == 1)
sprawdz("i nadal potrafilby kliknac, gdyby norma wrocila",
        "obserwuj_profil" in {n.func.attr for n in ast.walk(blok[0])
                              if isinstance(n, ast.Call)
                              and isinstance(n.func, ast.Attribute)})
sprawdz("powod wycofania stoi w samym bloku",
        "WYCOFANE 2026-08-23" in ast.get_docstring(blok[0]))
# KONTRDOWOD, ze to naprawde jedna stala: budzet dnia musi liczyc pozycje
# „follow" WLASNIE z FOLLOW_MIESIECZNIE. Gdyby liczyl ja skadinad, zmiana
# stalej niczego by nie odkrecila, a „wycofane" znaczyloby „zakopane".
zrodlo_stages = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
budzet = [w for w in ast.walk(ast.parse(zrodlo_stages))
          if isinstance(w, ast.FunctionDef) and w.name == "budzet_dnia"]
stale_w_budzecie = {n.attr for n in ast.walk(budzet[0])
                    if isinstance(n, ast.Attribute)}
sprawdz("budzet dnia liczy follow z tej wlasnie stalej",
        "FOLLOW_MIESIECZNIE" in stale_w_budzecie)
sprawdz("KONTRDOWOD: subskrypcje maja SWOJA stala, wiec sa niezalezne",
        "SUBSKRYPCJE_MIESIECZNIE" in stale_w_budzecie)


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
