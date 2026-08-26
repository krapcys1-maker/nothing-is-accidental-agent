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
        "why_this_scene": "zmusza do wyboru sceny Z TEKSTU, nie ilustracji tematu",
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
print("=== 5. GODZINY NOTEK: KAZDA STALA Z OSOBNA ===")
# TEN TEST PILNOWAL NIEPRAWDY. Sprawdzal tylko BEST_NOTE_HOURS, a potem
# potwierdzal, ze config OSTRZEGA o nieuzywanych stalych — nie sprawdzajac,
# czy to ostrzezenie jest prawdziwe dla KAZDEJ z nich. Nie bylo:
# `WORST_NOTE_HOURS` stalo w bloku "CZTERY PONIZSZE STALE NIE SA UZYWANE PRZEZ
# ZADNA LINIE KODU" (stale byly trzy) i jest EGZEKWOWANE przez
# `pora_na_publikacje` — miedzy 12:00 a 13:59 u czytelnikow agent nie wystawia
# ani notek, ani komentarzy. Kto uwierzylby komentarzowi i skasowal ta stala,
# dostalby NameError w funkcji wolanej na poczatku kazdego przebiegu dnia.
#
# Sprawdzamy wiec KAZDA stala osobno, w obie strony.
def _uzyta(nazwa):
    """Czy stala pada gdziekolwiek POZA wlasna definicja i komentarzami."""
    bez_komentarzy = re.sub(r"^\s*#.*$", "", cfg, flags=re.M)
    bez_definicji = re.sub(r"^" + nazwa + r"\s*=.*$", "", bez_komentarzy, flags=re.M)
    return (bool(re.search(r"\b" + nazwa + r"\b", bez_definicji))
            or bool(re.search(r"\b" + nazwa + r"\b", reszta)))


NAZWANE_JAKO_MARTWE = ("BEST_NOTE_HOURS", "BEST_NOTE_DAYS")
for nazwa in NAZWANE_JAKO_MARTWE:
    sprawdz("%s jest naprawde nieuzywana" % nazwa, not _uzyta(nazwa))
# KONTRDOWOD: stala EGZEKWOWANA nie moze stac w bloku "nieuzywane".
sprawdz("WORST_NOTE_HOURS jest uzywana", _uzyta("WORST_NOTE_HOURS"))
sprawdz("i config mowi o niej, ze jest EGZEKWOWANA", "EGZEKWOWANE" in cfg)
# Liczba w naglowku musi zgadzac sie z liczba stalych pod nim — bylo "CZTERY"
# przy trzech stalych, z czego jedna zywa.
naglowek = re.search(r"UWAGA: (\w+) PONIZSZE STALE NIE SA UZYWANE", cfg)
sprawdz("naglowek bloku martwych stalych istnieje", naglowek is not None)
if naglowek:
    LICZEBNIKI = {"JEDNA": 1, "DWIE": 2, "TRZY": 3, "CZTERY": 4, "PIEC": 5}
    sprawdz("i podaje tyle stalych, ile ich naprawde jest",
            LICZEBNIKI.get(naglowek.group(1)) == len(NAZWANE_JAKO_MARTWE),
            "%s wobec %d" % (naglowek.group(1), len(NAZWANE_JAKO_MARTWE)))

# ZACHOWANIE SPRAWDZONE NAPRAWDE, nie odczytane z komentarza.
from datetime import datetime, timezone   # noqa: E402
from zoneinfo import ZoneInfo             # noqa: E402

sys.path.insert(0, "agent-v2")
import config as _cfg                      # noqa: E402


def _wolno(godzina_et):
    t = datetime(2026, 8, 23, godzina_et, 30,
                 tzinfo=ZoneInfo(_cfg.PUBLISH_TIMEZONE)).astimezone(timezone.utc)
    return _cfg.pora_na_publikacje(t)[0]


for g in _cfg.WORST_NOTE_HOURS:
    sprawdz("o %02d:30 ET agent NIE publikuje" % g, not _wolno(g))
sprawdz("a godzine wczesniej owszem", _wolno(min(_cfg.WORST_NOTE_HOURS) - 1))
sprawdz("i godzine pozniej tez", _wolno(max(_cfg.WORST_NOTE_HOURS) + 1))
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
print("=== 7. STALA U WSZYSTKICH KANDYDATOW = ZERO INFORMACJI ===")
# Drugi wariant tej samej wady, i to ten, ktory przezyl dwie poprzednie
# naprawy. Pole JEST czytane, sortowanie z niego korzysta, test statyczny
# przechodzi — a sygnal ma u wszystkich kandydatow te sama wartosc, wiec
# nie ustawia nikogo przed nikim. Zlapane golym okiem w logu 2026-08-20:
# `watki na temat: [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]`.
sys.path.insert(0, str(pathlib.Path("agent-v2").resolve()))
from stages import _stale_sygnaly

DZIESIEC_JAK_NA_ZYWO = [
    {"ile_watkow": 3, "ile_precedensow": i % 3, "nasycony": True,
     "zasieg": "AN_INDUSTRY" if i < 6 else "A_PLACE"}
    for i in range(10)
]
martwe = _stale_sygnaly(DZIESIEC_JAK_NA_ZYWO,
                        ("ile_watkow", "ile_precedensow", "nasycony", "zasieg"))
sprawdz("stale pole jest zglaszane", any(m.startswith("ile_watkow=") for m in martwe), martwe)
sprawdz("i stala prawda tez (nie tylko liczby)",
        any(m.startswith("nasycony=") for m in martwe), martwe)
# KONTRDOWOD: pola, ktore realnie roznicuja, NIE moga trafic na te liste,
# inaczej wykrywacz jest tylko halasem i przestaniemy go czytac.
sprawdz("pole rozroznajace NIE jest zglaszane",
        not any(m.startswith("ile_precedensow=") for m in martwe), martwe)
sprawdz("nawet gdy ma tylko dwie wartosci",
        not any(m.startswith("zasieg=") for m in martwe), martwe)

# HISTORYCZNE REGRESJE — dokladnie te trzy stale, ktore juz nas kosztowaly.
sprawdz("lapie samooceny zawsze 1.0",
        _stale_sygnaly([{"score": 1.0} for _ in range(8)], ("score",)) != [])
sprawdz("lapie watki zawsze szesc",
        _stale_sygnaly([{"ile_watkow": 6} for _ in range(10)], ("ile_watkow",)) != [])
sprawdz("lapie znane teksty zawsze trzy",
        _stale_sygnaly([{"ile_juz_napisano": 3} for _ in range(10)],
                       ("ile_juz_napisano",)) != [])

# Przy jednym kandydacie stalej nie da sie odroznic od wartosci — milczymy,
# zamiast oskarzac model o wyrownywanie na probce rozmiaru jeden.
sprawdz("jeden kandydat to nie dowod na nic",
        _stale_sygnaly([{"ile_watkow": 3}], ("ile_watkow",)) == [])
sprawdz("pusta lista tez nie", _stale_sygnaly([], ("ile_watkow",)) == [])
# Brak pola u wszystkich to tez stala (None) i tez ma byc widoczny: to znaczy,
# ze model w ogole go nie oddal, a kod dalej sie nim sortuje.
sprawdz("brak pola u wszystkich = stala None",
        _stale_sygnaly([{}, {}, {}], ("confidence",)) != [])

st_src = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("wykrywacz jest realnie wolany w skaucie", "_stale_sygnaly(topics" in st_src)
sprawdz("i obejmuje watki", '"ile_watkow"' in st_src.split("_stale_sygnaly(topics")[1][:400])
sprawdz("i nasycenie", '"nasycony"' in st_src.split("_stale_sygnaly(topics")[1][:400])

print()
print("=== 8. KOMUNIKAT NIE MOZE OBIECYWAC ODSIEWU, KTOREGO NIE MA ===")
# Kara nalozona na 100% kandydatow nie przesuwa nikogo. Log mowil
# „10 z 10 juz opisanych gdzie indziej — na koniec kolejki", czyli brzmial
# jak odsiew, a byl brakiem odsiewu.
sprawdz("odsiew ogloszony tylko gdy kogos faktycznie przesuwa",
        "if nasycone and len(nasycone) < len(topics):" in st_src)
sprawdz("a przy komplecie mowimy wprost, ze nic nie rozroznilo",
        "nasycenie nic nie rozroznilo" in st_src)

print()
print("=== 9. PARAMETR PRZEKAZYWANY I NIECZYTANY ===")
# Trzeci wariant tej samej wady, tym razem po stronie Pythona, nie modelu.
# `db.recent_domains` liczylo domeny ostatnich artykulow PRZY KAZDYM przebiegu,
# run.py przekazywalo je do `stages.discovery`, a cialo funkcji nie tykalo ich
# ani razu. Docstring w db.py obiecywal „wejscie do reguly roznorodnosci",
# ktorej nie bylo nigdzie w repozytorium. To nie moglo byc rusztowaniem —
# rusztowanie to pole, ktore MODEL musi napisac; tego parametru model nigdy
# nie widzial.
st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("recent_domains jest teraz czytany, nie tylko przyjmowany",
        st.count("recent_domains") >= 2, st.count("recent_domains"))
dysk = pathlib.Path("agent-v2/prompts/dyskoveria.md").read_text(encoding="utf-8")
sprawdz("i dociera do promptu dyskoverii", "{ostatnie_domeny}" in dysk)
# ZAKAZUJE nawyku, nie NAKAZUJE pozycji — inaczej po dziesieciu tekstach sama
# regula staje sie podpisem maszyny.
sprawdz("regula zakazuje nawyku, nie nakazuje zrodla",
        "out of habit" in dysk and "no other host carries it" in dysk)

print()
print("=== 10. KAZDY PLACEHOLDER PROMPTU MA SWOJ ARGUMENT ===")
# `_prompt` robi str.format. Placeholder bez argumentu to KeyError, ktory
# wybucha PO oplaceniu wczesniejszych etapow. Argument bez placeholdera jest
# cichszy i grozniejszy: nie wywala niczego, tylko po cichu nic nie robi —
# czyli usterka zostaje, a wyglada na naprawiona.
import re as _re
POJEDYNCZY = _re.compile(r"(?<!\{)\{([a-z_][a-z0-9_]*)\}(?!\})")
braki = []
for plik in sorted(pathlib.Path("agent-v2/prompts").glob("*.md")):
    for pole in set(POJEDYNCZY.findall(plik.read_text(encoding="utf-8"))):
        if ("%s=" % pole) not in st:
            braki.append("%s -> %s" % (plik.name, pole))
sprawdz("zaden prompt nie ma placeholdera bez argumentu", not braki, braki)

# DRUGI KIERUNEK, KTOREGO TU BRAKOWALO. Sprawdzalem tylko placeholdery bez
# argumentu — czyli KeyError, ktory wybucha glosno. Odwrotnosc jest cichsza
# i wlasnie dlatego przezyla: argument PRZEKAZYWANY do promptu, ktory go
# nie uzywa, po prostu znika. Znalezione tak: `min_words` szlo do `pisarz.md`
# przy kazdym artykule i nie bylo w tym prompcie ani razu, wiec pisarz nigdy
# nie dostawal dolnej granicy dlugosci.
#
# Parsujemy WYWOLANIA `_prompt(...)`, zeby wiedziec, ktory argument idzie do
# ktorego pliku — sama obecnosc `min_words=` w stages.py nic nie znaczy, bo
# `notka.md` uzywa go poprawnie.
import ast as _ast   # noqa: E402

martwe_kwargi = []
for _w in _ast.walk(_ast.parse(st)):
    if not (isinstance(_w, _ast.Call) and getattr(_w.func, "id", "") == "_prompt"):
        continue
    if not (_w.args and isinstance(_w.args[0], _ast.Constant)
            and str(_w.args[0].value).endswith(".md")):
        continue
    nazwa = _w.args[0].value
    plik = pathlib.Path("agent-v2/prompts") / nazwa
    if not plik.exists():
        martwe_kwargi.append("%s -> pliku nie ma" % nazwa)
        continue
    tresc = plik.read_text(encoding="utf-8")
    for kw in _w.keywords:
        if kw.arg and ("{%s}" % kw.arg) not in tresc:
            martwe_kwargi.append("%s <- %s" % (nazwa, kw.arg))
sprawdz("zaden argument nie jest przekazywany do promptu, ktory go nie uzywa",
        not martwe_kwargi, martwe_kwargi)
# KONTRDOWOD: wykrywacz musi w ogole widziec wywolania i argumenty, inaczej
# przechodzi na pustym zbiorze i nie chroni przed niczym.
_ile_wywolan = sum(1 for _w in _ast.walk(_ast.parse(st))
                   if isinstance(_w, _ast.Call) and getattr(_w.func, "id", "") == "_prompt")
sprawdz("i widzi realne wywolania _prompt", _ile_wywolan >= 10, _ile_wywolan)

print()
print("=== 11. PISARZ NIE DOSTAJE DWOCH SPRZECZNYCH POLECEN ===")
# Oba zdania napisano, zeby naprawic TE SAMA awarie — artykul, ktory spedzil
# trzecia czesc dlugosci na tym, czego dowody nie mowia — tylko z przeciwnych
# stron: „zmiesc granice w jeden akapit" kontra „nigdy ich nie zbieraj".
# Model dostawal oba naraz.
pisarz = pathlib.Path("agent-v2/prompts/pisarz.md").read_text(encoding="utf-8")
# ZGODNOSC, NIE BRZMIENIE. Rano zapisalem tu asercje na konkretne zdanie
# i zabetonowala ona bledne rozstrzygniecie: przeczytalem dwie sprzeczne reguly
# i przestawilem te, ktora stala po stronie WIEKSZOSCI. Akapit granic jest
# zalozony w PIECIU miejscach — regula „Say the limits once", cala regula
# o pierwszym zdaniu TEGO akapitu z przykladami, zakaz „do not expand the
# limits paragraph", pole schematu `limits_paragraph_present` czytane
# w run.py, oraz bramka `gates.zapowiedziany_akapit_granic`, ktora bada
# pierwsze zdanie tego akapitu i bez niego nie ma sensu.
#
# Wiec test pyta teraz o to, co naprawde ma byc prawda: zadne zdanie promptu
# nie zakazuje akapitu, ktory piec innych miejsc zaklada.
sprawdz("prompt zamawia JEDEN akapit granic",
        "One paragraph, and only one." in pisarz
        and "Say the limits once" in pisarz)
sprawdz("i rzadzi jego POLOZENIEM, nie istnieniem",
        "Put that paragraph where the gap opens" in pisarz)
sprawdz("zadne zdanie nie zakazuje zbierania granic",
        "Never collect them." not in pisarz
        and "Put each unknown where it arises, alone." not in pisarz)
sprawdz("zakaz rozdymania nadal zaklada, ze akapit istnieje",
        "expand the limits paragraph" in pisarz)
sprawdz("schemat nadal pyta o obecnosc akapitu",
        "limits_paragraph_present" in pisarz)
# Kotwica dlugosci ma sie skalowac — inaczej pracuje przeciw DLUGOSC_WG_GLEBOKOSCI.
sprawdz("kotwica dlugosci jest polem, nie wpisana na sztywno",
        "{kotwica_dlugosci}" in pisarz and "1048 and 1101" not in pisarz)
sprawdz("i pisarz dostaje dolna granice", "{min_words}" in pisarz)
import config as _c2   # noqa: E402
sprawdz("kazdy poziom glebokosci ma wlasna kotwice",
        len({_c2.kotwica_dlugosci(g) for g in ("RICH", "SINGLE", "THIN")}) == 3)
sprawdz("kotwica RICH nadal powoluje sie na dwa przyjete teksty",
        "1048" in _c2.kotwica_dlugosci("RICH"))
sprawdz("a kotwica THIN mowi, ze krotko jest wlasciwie",
        "shortest form" in _c2.kotwica_dlugosci("THIN"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
