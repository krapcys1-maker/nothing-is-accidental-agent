"""Test: dlugosc artykulu skalowana do materialu, nie stala.

Zrodlo problemu: artykul o symbolu otwartego sloiczka mial material na trzysta
slow, a sztywny cel 1075 kazal napisac tysiac sto. Reszta to byly powtorzenia.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
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


print("=== 1. DLUGOSC IDZIE ZA GLEBOKOSCIA ===")
r = config.dlugosc_dla("RICH")
s = config.dlugosc_dla("SINGLE")
print("    RICH   cel %s (%s-%s)" % (r["cel"], r["min"], r["max"]))
print("    SINGLE cel %s (%s-%s)" % (s["cel"], s["min"], s["max"]))
sprawdz("waski temat dostaje wyraznie krotsza forme", s["cel"] < r["cel"] * 0.7,
        "%s vs %s" % (s["cel"], r["cel"]))
sprawdz("krotki artykul ma sensowne dno (nie notka)", s["min"] >= 400, s["min"])
sprawdz("dlugi nie przekracza tego, co czyta sie do konca", r["max"] <= 1300, r["max"])
sprawdz("zakresy sie nie nakladaja", s["max"] < r["min"], (s["max"], r["min"]))
# ZMIANA DECYZJI (2026-08-20). Bylo: nieznana glebokosc dostaje RICH. Nieznana
# glebokosc znaczy jednak „model oddal cos spoza slownika", czyli NIE WIEM, ile
# tu jest materialu — a odpowiedzia na „nie wiem" nie moze byc forma najdluzsza,
# bo to maksymalizuje ryzyko wypelniacza. Srodek jest uczciwy w obie strony.
sprawdz("nieznana glebokosc -> forma srodkowa, nie najdluzsza",
        config.dlugosc_dla("COKOLWIEK") == s)
sprawdz("pusta glebokosc tez", config.dlugosc_dla("") == s)

print()
print("=== 2. WYBOR TEMATU: GLEBOKOSC PRZED PEWNOSCIA ===")
TEMATY = [{"title": "waski ale pewny"}, {"title": "bogaty"}, {"title": "jednozdaniowy"}]
OCENY = [
    {"index": 0, "feasible": True, "confidence": 0.95, "expected_primary_sources": 8,
     "depth": "SINGLE"},
    {"index": 1, "feasible": True, "confidence": 0.55, "expected_primary_sources": 3,
     "depth": "RICH"},
    {"index": 2, "feasible": True, "confidence": 0.99, "expected_primary_sources": 9,
     "depth": "THIN"},
]
t, a = stages.pick_topic(TEMATY, OCENY)
print("    wybrano: %s (%s)" % (t["title"], a["depth"]))
sprawdz("bogaty wygrywa z pewniejszym, ale plytkim", t["title"] == "bogaty", t)
sprawdz("STARY sposob wzialby 'jednozdaniowy' — najwyzsza pewnosc (test rozroznia)",
        max(OCENY, key=lambda x: x["confidence"])["index"] == 2)

# THIN nie jest odrzucany, tylko ostatni w kolejce
tylko_thin = [{"index": 0, "feasible": True, "confidence": 0.9,
               "expected_primary_sources": 5, "depth": "THIN"}]
t2, a2 = stages.pick_topic([{"title": "ostatnia deska"}], tylko_thin)
sprawdz("gdy nie ma nic lepszego, THIN nadal przechodzi", t2["title"] == "ostatnia deska")

bez_glebokosci = [{"index": 0, "feasible": True, "confidence": 0.8,
                   "expected_primary_sources": 4}]
t3, a3 = stages.pick_topic([{"title": "stary format"}], bez_glebokosci)
sprawdz("ocena bez pola depth nie wywala (zgodnosc wstecz)", t3["title"] == "stary format")

print()
print("=== 3. PISARZ DOSTAJE WLASCIWA DLUGOSC ===")
import inspect  # noqa: E402
sygn = inspect.signature(stages.write).parameters
sprawdz("write przyjmuje glebokosc", "glebokosc" in sygn)
sprawdz("glebokosc ma domyslna wartosc (stare wywolania dzialaja)",
        sygn["glebokosc"].default == "RICH")
zrodlo_w = inspect.getsource(stages.write)
sprawdz("write NIE uzywa juz stalej TARGET_WORDS",
        "config.TARGET_WORDS" not in zrodlo_w)
sprawdz("write bierze dlugosc z glebokosci", 'config.dlugosc_dla(glebokosc)' in zrodlo_w)
zrodlo_r = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("run.py czyta depth z odsiewu", 'verdict.get("depth")' in zrodlo_r)
sprawdz("run.py przekazuje glebokosc do pisarza",
        "stages.write(conn, run_id, card, glebokosc)" in zrodlo_r)

for g, d in (("RICH", r), ("SINGLE", s)):
    # Ruch koncowy i liczba paraleli sa od teraz losowane per artykul, wiec
    # pisarz.md ich wymaga — patrz test_forma_artykulu.py.
    ruch_nazwa, ruch_opis = config.losowy_ruch_koncowy()
    _, opis_paraleli = config.losowa_liczba_paraleli(g)
    gotowy = stages._prompt(
        "pisarz.md", language="English", target_words=d["cel"], min_words=d["min"],
        max_words=d["max"], kotwica_dlugosci="x", style_examples="x", style_positive="y",
        style_negative="z", ruch_koncowy_nazwa=ruch_nazwa, ruch_koncowy=ruch_opis,
        ile_paraleli=opis_paraleli, card_json="{}")
    sprawdz("prompt dla %s niesie cel %s slow" % (g, d["cel"]), str(d["cel"]) in gotowy)

print()
print("=== 4. ODSIEW OCENIA DRUGI AKT ===")
wykonalnosc = (config.PROMPTS_DIR / "wykonalnosc.md").read_text(encoding="utf-8")
for s_ in ("RICH", "SINGLE", "THIN", "parallels", "second act"):
    sprawdz("odsiew mowi o %s" % s_, s_ in wykonalnosc)
sprawdz("odsiew ostrzega przed hojnoscia w ocenie",
        "Marking everything RICH" in wykonalnosc)

print()
print("=== 5. SYNTEZA ZBIERA PARALELE, PISARZ NIMI ZARABIA DLUGOSC ===")
synteza = (config.PROMPTS_DIR / "synteza.md").read_text(encoding="utf-8")
sprawdz("synteza ma pole parallel_mechanisms", "parallel_mechanisms" in synteza)
sprawdz("synteza wymaga trafnosci, nie luznych porownan",
        "worse than none" in synteza)
sprawdz("synteza pozwala oddac pusta liste", "empty list" in synteza)
pisarz = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf-8")
sprawdz("pisarz wie, ze dlugosc trzeba zarobic", "Earning the length" in pisarz)
sprawdz("pisarz ma pisac krotko, gdy paralel brak", "write short" in pisarz)

print()
print("=== 6. CIECIA W PISARZU ===")
# ZMIANA DECYZJI (2026-08-23): prompt mial JEDNOCZESNIE nakaz zbierania
# granic w jeden akapit i zakaz zbierania ich w ogole. Zostal zakaz.
sprawdz("granice nie sa zbierane w osobny akapit",
        "Never collect them." in pisarz
        and "One paragraph. Not two, not three." not in pisarz)
sprawdz("zakaz powtarzania mechanizmu", "Name the mechanism once" in pisarz)

print()
print("=== 7. GRAFIKA: SYMBOL TO NIE PRZEDMIOT ===")
grafika = (config.PROMPTS_DIR / "grafika.md").read_text(encoding="utf-8")
sprawdz("prompt odroznia symbol od przedmiotu", "A symbol is not an object" in grafika)
sprawdz("podaje wpadke jako przyklad", "jam jar" in grafika)
sprawdz("daje test: czy da sie to podniesc w domu",
        "pick this object up in your house" in grafika)

print()
print("=== THIN: NAJMNIEJ MATERIALU, NAJKROTSZA FORMA ===")
# Prompt odsiewu mowi o THIN wprost: „the finding is a sentence. No article at
# any length." A tabela dlugosci miala tylko RICH i SINGLE, wiec THIN wpadal
# w galaz domyslna rowna RICH i dostawal 1075 slow. Temat o najmniejszej ilosci
# materialu dostawal najdluzsza forme — dokladnie ta usterka, przed ktora ta
# tabela powstala.
r = config.dlugosc_dla("RICH")
sg = config.dlugosc_dla("SINGLE")
th = config.dlugosc_dla("THIN")
sprawdz("THIN ma wlasny wpis", th != r, th)
sprawdz("i jest krotszy od SINGLE", th["cel"] < sg["cel"], (th["cel"], sg["cel"]))
sprawdz("a SINGLE od RICH", sg["cel"] < r["cel"], (sg["cel"], r["cel"]))
# KONTRDOWOD: sam osobny wpis nie wystarczy, jesli bylby rownie dlugi.
# Roznica ma byc odczuwalna, nie kosmetyczna.
sprawdz("THIN jest krotszy od RICH o ponad polowe", th["cel"] * 2 < r["cel"],
        (th["cel"], r["cel"]))
sprawdz("kazdy poziom ma spojne min/cel/max",
        all(w["min"] <= w["cel"] <= w["max"] for w in (r, sg, th)))
sprawdz("i zakresy sie nie nakladaja",
        th["max"] <= sg["cel"] and sg["max"] <= r["cel"],
        (th["max"], sg["cel"], sg["max"], r["cel"]))

# GALAZ DOMYSLNA. Nieznana glebokosc znaczy „nie wiem, ile tu jest materialu" —
# na to uczciwa odpowiedzia jest forma srednia, nie najdluzsza.
for nieznane in ("", None, "cokolwiek", "rich "):
    sprawdz("nieznane %r dostaje SINGLE, nie RICH" % nieznane,
            config.dlugosc_dla(nieznane)["cel"] == sg["cel"],
            config.dlugosc_dla(nieznane))
# Ale poprawna nazwa ma dzialac niezaleznie od wielkosci liter.
sprawdz("mala litera to nadal ta sama glebokosc",
        config.dlugosc_dla("thin") == th)

# Liczba paraleli jest LOSOWANA, wiec jedno wywolanie nie dowodzi niczego —
# pierwsza wersja tej asercji porownala dwa losy i przeszla przez przypadek.
# Sprawdzamy rozklad: krotki artykul nigdy nie bierze trzech paraleli, bo
# nie ma ich z czego rozwinac.
losy_thin = {config.losowa_liczba_paraleli("THIN")[0] for _ in range(300)}
losy_single = {config.losowa_liczba_paraleli("SINGLE")[0] for _ in range(300)}
losy_rich = {config.losowa_liczba_paraleli("RICH")[0] for _ in range(300)}
sprawdz("THIN nigdy nie bierze trzech paraleli", 3 not in losy_thin, losy_thin)
sprawdz("SINGLE tez nie", 3 not in losy_single, losy_single)
sprawdz("a RICH moze", 3 in losy_rich, losy_rich)
sprawdz("kazdy bierze co najmniej jedna", min(losy_thin | losy_rich) >= 1)

# Kolejnosc wyboru tematu MUSI stawiac THIN na koncu — inaczej krotsza forma
# staje sie wygodna wymowka zamiast ostatniej deski ratunku.
zrodlo = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("THIN wazy najmniej przy wyborze tematu",
        '"RICH": 2, "SINGLE": 1, "THIN": 0' in zrodlo)

print()
print("=== WYNIK: %s zdanych, %s oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
