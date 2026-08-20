"""Wykrywacz martwych sygnalow: pol, ktore model wylicza, a kod wyrzuca.

TO NIE JEST TEST JEDNEJ USTERKI, tylko siec na cala ich klase.

Skaut liczyl siedem ocen — curiosity, source_quality, non_obvious, universality,
discussion_potential, visual_potential, originality — i NIE CZYTALA ICH ANI JEDNA
LINIA KODU. Trwalo to tygodniami. Placilismy za wyliczenie w kazdym przebiegu
i wyrzucalismy wynik, a jednoczesnie skarzylismy sie, ze tematy sa oklepane,
majac w reku nieuzywane pole `originality`.

Ta sama wada ma drugi wariant: STALA, KTORA WYGLADA JAK ZABEZPIECZENIE.
`MAX_KOMENTARZY_NA_PUBLIKACJE = 2` nie bylo egzekwowane nigdzie, a ja sam
powolalem sie na nie tego samego dnia jako na istniejacy limit. Martwa stala
jest GORSZA niz jej brak, bo czyta sie ja jak gwarancje.

Dlatego test szuka obu naraz i wymaga, zeby kazdy wyjatek byl WYMIENIONY
Z POWODEM. Dopisanie czegos do listy wyjatkow ma byc decyzja, nie odruchem.

CO JEST UPRAWNIONYM WYJATKIEM. Sa pola, ktorych kod nie czyta CELOWO: model
musi je napisac, zeby dobrze pomyslec. „Dlaczego akurat ten przedmiot",
„w czym te dwa mechanizmy sa te same" — odpowiedz nie jest nam potrzebna,
ale jej sformulowanie zmienia to, co model odda w polach, ktore czytamy.
To jest rusztowanie i zostaje. Roznica miedzy rusztowaniem a martwym polem
polega na tym, ze rusztowanie da sie uzasadnic jednym zdaniem — i tu jest
wymagane.
"""
import pathlib
import re
import sys

sys.path.insert(0, "agent-v2")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


KOD_PY = list(pathlib.Path("agent-v2").glob("*.py"))
KOD = "\n".join(p.read_text(encoding="utf-8") for p in KOD_PY)
PROMPTY = sorted(pathlib.Path("agent-v2/prompts").glob("*.md"))

# --- RUSZTOWANIE: pola, ktorych kod NIE czyta i to jest zamierzone -----------
# Kazdy wpis wymaga powodu. Dopisanie tu czegokolwiek to decyzja.
RUSZTOWANIE = {
    "bibliotekarz.md": {
        "missing": "czego brakuje grupie — czytane przez czlowieka w logu",
        "why_it_travels": "zmusza do sprawdzenia, czy mechanizm NAPRAWDE jest ten sam",
    },
    "forma.md": {
        "belief": "model musi nazwac przekonanie WLASNYMI slowami, zanim znajdzie cytat — to wymusza scalanie",
        "first_stated": "kotwiczy przekonanie w tekscie, zeby nie dalo sie go wymyslic",
        "object": "wymusza konkret przy przylapaniu czytelnika",
        "supports": "wskazuje, ktore przekonanie wspiera zdanie — pilnuje, ze wsparcie nie jest przekonaniem",
    },
    "grafika.md": {
        "why_this_object": "zmusza do wyboru przedmiotu Z TEKSTU, nie ilustracji tematu",
    },
    "notka.md": {
        "fact_used": "model ma wskazac fakt, na ktorym stoi notka — zapora przed zmysleniem",
        "source_url": "to samo, dla zrodla",
        "words": "wlasna deklaracja dlugosci; prawdziwa liczy kod",
    },
    "pisarz.md": {
        "numbers_used": "spis liczb uzytych w tekscie — bramka LICZBA_SPOZA_KORPUSU i tak liczy je sama",
    },
    "restack.md": {
        "mechanism_named": "zmusza do nazwania mechanizmu, zanim padnie decyzja o podaniu dalej",
    },
    "synteza.md": {
        "how_it_matches": "uzasadnienie paraleli — bez niego model dokleja dowolna dziedzine",
    },
    "warto_pisac.md": {
        "one_line_verdict": "podsumowanie dla czlowieka czytajacego uwagi",
        "the_situation": "wymusza konkret przy nierozstrzygnietym wyniku",
        "what_would_rescue_it": "podpowiedz dla wlasciciela, czego szukac przy DOLOZ",
    },
    "weryfikacja.md": {
        "what_the_source_says": "dowod za werdyktem — do przeczytania, gdy fakt zostaje obalony",
    },
    "wykonalnosc.md": {
        "parallels": "zmusza do UZASADNIENIA oceny RICH; sama ocena jest czytana",
    },
}

# --- STALE nieuzywane, ktore zostaja SWIADOMIE -------------------------------
STALE_ZOSTAJA = {
    "BEST_NOTE_HOURS": "zapis ustalen; nasze zrodla sie nie zgadzaja co do godzin",
    "WORST_NOTE_HOURS": "j.w.",
    "BEST_NOTE_DAYS": "j.w.",
    "WORST_NOTE_DAYS": "j.w.",
    "KANDYDATOW_NA_PRZEBIEG": "uzywane w promptcie ciekawostek przez podstawienie",
    "ODPOWIEDZI_POZA_LIMITEM": "prog opisowy, sprawdzany w tescie odpowiedzi",
}

print("=== 1. POLA MODELU, KTORYCH KOD NIE CZYTA ===")
niespodzianki = {}
for p in PROMPTY:
    tekst = p.read_text(encoding="utf-8")
    klucze = set(re.findall(r'"([a-z][a-z0-9_]{2,})"\s*:', tekst))
    martwe = []
    for k in sorted(klucze):
        if re.search(r'["\']%s["\']' % re.escape(k), KOD) or ("." + k) in KOD:
            continue
        if k in RUSZTOWANIE.get(p.name, {}):
            continue
        martwe.append(k)
    if martwe:
        niespodzianki[p.name] = martwe

for nazwa, pola in niespodzianki.items():
    print("    %-22s %s" % (nazwa, ", ".join(pola)))
sprawdz("zadne pole nie jest martwe bez powodu", not niespodzianki,
        niespodzianki)

ile_rusztowania = sum(len(v) for v in RUSZTOWANIE.values())
print("    (rusztowania z uzasadnieniem: %d pol w %d promptach)"
      % (ile_rusztowania, len(RUSZTOWANIE)))
sprawdz("kazde rusztowanie ma NIEPUSTY powod",
        all(len(str(r).split()) >= 4 for v in RUSZTOWANIE.values() for r in v.values()))

print()
print("=== 2. STALE, KTORYCH NIE UZYWA ZADEN KOD ===")
cfg = pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8")
reszta = "\n".join(p.read_text(encoding="utf-8") for p in KOD_PY
                   if p.name != "config.py")
martwe_stale = []
for s in sorted(set(re.findall(r"^([A-Z][A-Z0-9_]{3,})\s*=", cfg, re.M))):
    if re.search(r"\b%s\b" % s, reszta):
        continue
    if len(re.findall(r"\b%s\b" % s, cfg)) > 1:
        continue          # uzywana wewnatrz samego configu
    if s in STALE_ZOSTAJA:
        continue
    martwe_stale.append(s)
print("    znalezione: %s" % (", ".join(martwe_stale) or "(brak)"))
sprawdz("zadna stala nie jest martwa bez powodu", not martwe_stale, martwe_stale)

print()
print("=== 3. USUNIETE 20 SIERPNIA — NIE MOGA WROCIC ===")
# Kazda z tych czterech udawala dzialajacy mechanizm.
for stala, czym_byla in (
        ("MAX_KOMENTARZY_NA_PUBLIKACJE", "limit, ktorego nikt nie egzekwowal"),
        ("NOTES_PER_DAY", "duplikat len(NOTE_MIX_OTHER_DAY)"),
        ("MAX_DZIALAN_NA_GODZINE", "ogranicznik tempa, ktory nie ograniczal"),
        ("FLAGGED_GATES", "lista czterech bramek, gdy jest ich szesnascie")):
    sprawdz("%-30s nie wrocilo (%s)" % (stala, czym_byla[:34]),
            not re.search(r"^%s\s*=" % stala, cfg, re.M))

print()
print("=== 4. ZASTEPCY USUNIETYCH NAPRAWDE DZIALAJA ===")
# Usuniecie limitu jest bezpieczne TYLKO wtedy, gdy istnieje ostrzejszy.
import config   # noqa: E402
kanal_src = pathlib.Path("agent-v2/kanal.py").read_text(encoding="utf-8")
sprawdz("limit u tej samej publikacji istnieje i jest czytany",
        "ODSTEP_DNI_NA_PUBLIKACJE" in kanal_src)
sprawdz("i jest OSTRZEJSZY niz usuniety (raz na kilka dni, nie 2 dziennie)",
        config.ODSTEP_DNI_NA_PUBLIKACJE >= 2, config.ODSTEP_DNI_NA_PUBLIKACJE)
sprawdz("liczbe notek nadal wyznacza NOTE_MIX_OTHER_DAY",
        len(config.NOTE_MIX_OTHER_DAY) == 5, len(config.NOTE_MIX_OTHER_DAY))
sprawdz("tempo nadal wyznaczaja ODSTEPY", bool(config.ODSTEPY))
sprawdz("zrodlem prawdy o bramkach jest gates.deterministic_floors",
        "def deterministic_floors" in
        pathlib.Path("agent-v2/gates.py").read_text(encoding="utf-8"))

print()
print("=== 5. GODZINY NOTEK: NIEUZYWANE I OZNACZONE JAKO NIEUZYWANE ===")
# Jesli kiedys zaczna dzialac, ten test ma o tym powiedziec.
uzywane = bool(re.search(r"\bBEST_NOTE_HOURS\b", reszta))
print("    BEST_NOTE_HOURS uzywane w kodzie: %s" % uzywane)
sprawdz("config OSTRZEGA, ze sa nieuzywane",
        "NIE SA UZYWANE PRZEZ ZADNA LINIE KODU" in cfg)
# Config jest lamany do 79 znakow, a zdanie przechodzi przez granice wiersza
# RAZEM ze znakiem komentarza — samo sklejenie bialych znakow zostawia w srodku
# „#". Wiec najpierw zdejmujemy znaki komentarza, potem sklejamy.
PLASKI_CFG = " ".join(re.sub(r"^\s*#\s?", "", cfg, flags=re.M).split())
sprawdz("i mowi, ze zrodla sie nie zgadzaja",
        "NASZE WLASNE ZRODLA SIE NIE ZGADZAJA" in PLASKI_CFG)
# OKNO_PUBLIKACJI_ET jest uzywane WEWNATRZ configu, przez `pora_na_publikacje`,
# i to wystarcza — inaczej niz godziny notek, ktorych nie czyta nikt.
sprawdz("okno publikacji NADAL dziala (to nie to samo co godziny)",
        len(re.findall(r"OKNO_PUBLIKACJI_ET", cfg)) > 1,
        len(re.findall(r"OKNO_PUBLIKACJI_ET", cfg)))
sprawdz("i jest realnie wolane w przebiegu", "pora_na_publikacje()" in reszta)

print()
print("=== 6. RECENZENT: SKLADAMY Z DWOCH ZRODEL, NIE Z JEDNEGO ===")
# Recenzent oznacza kazde zdanie i OSOBNO powtarza nieoparte w liscie.
# Czytanie tylko listy znaczylo ufanie, ze model poprawnie przepisze wlasny
# wynik w drugie miejsce.
run_src = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("czytamy takze sentences[].supported",
        's.get("supported") is not False' in run_src)
sprawdz("i dopisujemy pominiete do listy",
        "unsupported.append" in run_src)
sprawdz("i mowimy o tym w logu", "nie powtórzył w liście zbiorczej" in run_src)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
