"""Ile agent naprawde robi na koncie — i czy budzet da sie wydac.

Przeglad z 20 sierpnia 2026 na wlasnych danych. Do tej pory widelki byly
liczbami wzietymi z wyobrazenia o tempie czlowieka. Dziennik za piec dni
pokazal cos innego:

    lajki        9,6/dzien   przy budzecie 12-20
    komentarze   7,0/dzien   przy budzecie 15-20
    restacki     0,4/dzien   przy budzecie 2-4
    obserwacje   0,0/dzien   przy budzecie 30-44 MIESIECZNIE

Ostatnia linijka to nie niedobor, tylko martwy blok. Przyczyna nie byla
w liczbie, tylko w KOLEJNOSCI: zegar przebiegu sprawdzaja bloki od odpowiedzi
po subskrypcje, a polubienia i restacki nie patrza na niego wcale. Gdy czas
sie konczyl, wypadaly dokladnie te bloki, ktore byly wobec zegara uczciwe —
a obserwowanie stalo za komentarzami, czyli za jedynym blokiem potrafiacym
zjesc caly budzet czasu.

Budzet, ktorego nie da sie wydac, nie jest budzetem: klamie w logu, psuje
dzielenie normy na przebiegi i ukrywa, ze cos w ogole nie chodzi.
"""
import re
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# Zmierzone srednie z dziennika, 16-20 sierpnia. Sluza za punkt odniesienia:
# widelki maja OPISYWAC to, co agent robi, a nie zyczyc sobie tego.
ZMIERZONE = {"lajki": 9.6, "komentarze": 7.0, "restacki": 0.4,
             "obserwacje": 0.0, "notki": 3.0}

print("=== 1. WIDELKI NIE MOGA BYC ODERWANE OD WYKONANIA ===")
POROWNANIA = [
    ("lajki", config.LAJKI_DZIENNIE, ZMIERZONE["lajki"]),
    ("komentarze", config.KOMENTARZE_DZIENNIE, ZMIERZONE["komentarze"]),
    ("restacki", config.RESTACK_DZIENNIE, ZMIERZONE["restacki"]),
]
for nazwa, (dol, gora), zmierzone in POROWNANIA:
    print("    %-11s widelki %s-%-3s   zmierzone %.1f" % (nazwa, dol, gora, zmierzone))
    # Dolna granica ma byc w zasiegu. Gorna moze byc ambitna, ale nie o rzad
    # wielkosci — inaczej dzielenie normy na przebiegi liczy fikcje.
    sprawdz("  %-11s górna granica w granicach rozsądku" % nazwa,
            gora <= max(4, zmierzone * 4), (gora, zmierzone))

print()
print("=== 2. KONKRETNE DECYZJE Z 20 SIERPNIA ===")
sprawdz("lajki 10-16 (było 12-20)", config.LAJKI_DZIENNIE == (10, 16),
        config.LAJKI_DZIENNIE)
sprawdz("komentarze 8-12 (było 15-20)", config.KOMENTARZE_DZIENNIE == (8, 12),
        config.KOMENTARZE_DZIENNIE)
sprawdz("restacki 1-2 (było 2-4)", config.RESTACK_DZIENNIE == (1, 2),
        config.RESTACK_DZIENNIE)
sprawdz("obserwacje 20-30/mies (było 30-44)",
        config.FOLLOW_MIESIECZNIE == (20, 30), config.FOLLOW_MIESIECZNIE)
sprawdz("subskrypcje bez zmian 6-12/mies",
        config.SUBSKRYPCJE_MIESIECZNIE == (6, 12), config.SUBSKRYPCJE_MIESIECZNIE)
sprawdz("notki nietknięte — to silnik wzrostu",
        len(config.NOTE_MIX_OTHER_DAY) == 5, len(config.NOTE_MIX_OTHER_DAY))

print()
print("=== 3. KAZDE WIDELKI MAJA SENS JAKO WIDELKI ===")
for nazwa in ("LAJKI_DZIENNIE", "KOMENTARZE_DZIENNIE", "RESTACK_DZIENNIE",
              "FOLLOW_MIESIECZNIE", "SUBSKRYPCJE_MIESIECZNIE"):
    dol, gora = getattr(config, nazwa)
    sprawdz("%-24s dół <= góra, oba > 0" % nazwa, 0 < dol <= gora, (dol, gora))

print()
print("=== 4. RESTACK JEST NAJRZADSZY ZE WSZYSTKIEGO ===")
# Bo jako jedyny stawia NASZE nazwisko obok cudzego tekstu.
sprawdz("restacków mniej niż lajków",
        config.RESTACK_DZIENNIE[1] < config.LAJKI_DZIENNIE[0],
        (config.RESTACK_DZIENNIE, config.LAJKI_DZIENNIE))
sprawdz("restacków mniej niż komentarzy",
        config.RESTACK_DZIENNIE[1] < config.KOMENTARZE_DZIENNIE[0],
        (config.RESTACK_DZIENNIE, config.KOMENTARZE_DZIENNIE))

print()
print("=== 5. KOLEJNOSC BLOKOW — TU SIEDZIALO ZERO OBSERWACJI ===")
zrodlo = open("agent-v2/run.py", encoding="utf-8").read()
m = re.search(r"for nazwa, robota in \((.*?)\):", zrodlo, re.S)
sprawdz("pętla bloków istnieje", m is not None)
kolejnosc = re.findall(r'\("(\w+)",', m.group(1)) if m else []
print("    %s" % " -> ".join(kolejnosc))
sprawdz("wszystkie osiem bloków", len(kolejnosc) == 8, kolejnosc)

i = {n: k for k, n in enumerate(kolejnosc)}
sprawdz("obserwowanie PRZED komentarzami",
        i.get("obserwowanie", 99) < i.get("komentarze", -1), i)
sprawdz("subskrypcje PRZED komentarzami",
        i.get("subskrypcje", 99) < i.get("komentarze", -1), i)
# KONTRDOWOD: to jest dokladnie ta kolejnosc, ktora byla wczesniej i dawala
# zero obserwacji. Bez tego sprawdzenia test nie odroznia wersji.
STARA = ["odpowiedzi", "notki", "komentarze", "dyskusje", "obserwowanie",
         "subskrypcje", "polubienia", "restacki"]
sprawdz("to NIE jest stara kolejność (test rozróżnia)", kolejnosc != STARA,
        kolejnosc)

print()
print("=== 6. CO ZOSTAJE NA SWOIM MIEJSCU I DLACZEGO ===")
sprawdz("odpowiedzi pierwsze — to zobowiązanie wobec czytelnika",
        kolejnosc and kolejnosc[0] == "odpowiedzi", kolejnosc[:1])
sprawdz("notki drugie — to nasza własna treść",
        len(kolejnosc) > 1 and kolejnosc[1] == "notki", kolejnosc[:2])
sprawdz("restacki ostatnie — niosą najwięcej ryzyka",
        kolejnosc and kolejnosc[-1] == "restacki", kolejnosc[-1:])

print()
print("=== 7. BLOKI TANIE IDA PRZED DROGIMI ===")
# Obserwacja i subskrypcja to jedno wejscie na profil, zero wywolan modelu.
# Komentarz to pobranie strony, trzy warianty i sprawdzenie faktow (~3 centy).
TANIE = {"obserwowanie", "subskrypcje", "polubienia"}
DROGIE = {"komentarze", "dyskusje"}
najdrozszy_tani = max((i[n] for n in TANIE if n in i), default=99)
pierwszy_drogi = min((i[n] for n in DROGIE if n in i), default=-1)
sprawdz("co najmniej jeden tani blok wyprzedza drogie",
        min((i[n] for n in TANIE if n in i), default=99) < pierwszy_drogi, i)

print()
print("=== 8. ILE TO KOSZTUJE MIESIECZNIE ===")
# Zmierzone na produkcji: komentarz to trzy warianty + factcheck ~ 3 centy.
ZA_KOMENTARZ = 0.03
for opis, ile in (("było (15-20/dzień)", 17.5), ("jest (8-12/dzień)", 10.0)):
    print("    %-22s %5.1f/dzień -> $%5.2f miesięcznie" % (opis, ile, ile * 30 * ZA_KOMENTARZ))
sprawdz("nowe widełki oszczędzają ponad 5 USD miesięcznie",
        (17.5 - sum(config.KOMENTARZE_DZIENNIE) / 2) * 30 * ZA_KOMENTARZ > 5,
        (17.5 - sum(config.KOMENTARZE_DZIENNIE) / 2) * 30 * ZA_KOMENTARZ)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
