"""Siatka generatorow i cztery bramki przed wydaniem grosza.

Mielismy 52 DZIEDZINY — odpowiedz na pytanie GDZIE szukac — i zero wzorcow,
czyli zadnej odpowiedzi na pytanie CZEGO. Model dostawal „przyroda, finanse,
prawo" i wracal do tego, co mu wychodzi najlatwiej.

Sprawdzian przydatnosci, ktory zrobilem przed wdrozeniem: szesc naszych
artykulow trafia w PIEC roznych wzorcow ponizej. Siatka pokrywa to, co juz
umiemy, i nazywa kilka, ktorych nie tknelismy.
"""
import re
import sys

sys.path.insert(0, "agent-v3")
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


KOMPLET = {
    "fact": "Mains clocks count grid cycles, and a 2018 shortfall left European "
            "clocks six minutes slow.",
    "wrong_belief": "Most people assume the oven clock keeps time by itself",
    "actually": "It counts cycles of the electricity grid, so grid drift moves it",
    "decision": "50 Hz fixed as the synchronous norm, ENTSO-E 1951",
    "consequence": "the clock on your oven",
    "url": "https://www.entsoe.eu/news/2018/03/06/press-release/",
    "domain": "elektrycznosc",
}


def wariant(**zmiany):
    k = dict(KOMPLET)
    k.update(zmiany)
    return k


print("=== 1. SIATKA ISTNIEJE I JEST DUZA ===")
sprawdz("dwanascie wzorcow", len(config.GENERATORY) == 12, len(config.GENERATORY))
sprawdz("kazdy ma pytanie sondujace",
        all("Probe:" in o for o in config.GENERATORY.values()))
komorki = len(config.GENERATORY) * len(config.DZIEDZINY_CIEKAWOSTEK)
print("    siatka: %d wzorcow x %d dziedzin = %d komorek"
      % (len(config.GENERATORY), len(config.DZIEDZINY_CIEKAWOSTEK), komorki))
sprawdz("siatka ma setki komorek", komorki >= 400, komorki)

print()
print("=== 2. WZORCE SIE ROTUJA (jednolity ksztalt to podpis maszyny) ===")
losowania = [tuple(sorted(config.losowe_generatory())) for _ in range(40)]
sprawdz("nie zawsze te same cztery", len(set(losowania)) > 5, len(set(losowania)))
sprawdz("zawsze tyle, ile zamowiono",
        all(len(l) == config.ILE_GENERATOROW_NA_PRZEBIEG for l in losowania))
uzyte = {g for l in losowania for g in l}
sprawdz("z czasem wypadaja wszystkie", uzyte == set(config.GENERATORY),
        set(config.GENERATORY) - uzyte)

print()
print("=== 3. NASZE ARTYKULY MAPUJA SIE NA WZORCE (sprawdzian przydatnosci) ===")
NASZE = {"0014 okno w samolocie": "MARGIN", "0016 symbol kosmetyczny": "BOUNDARY",
         "0017 blokada karty": "BOUNDARY", "0019 zolte swiatlo": "CONFESSION",
         "0020 kolor autobusu": "DECIDER", "0024 SPF": "MEASUREMENT"}
for tytul, gen in NASZE.items():
    sprawdz("%-26s -> %s" % (tytul, gen), gen in config.GENERATORY)
sprawdz("szesc artykulow trafia w piec roznych wzorcow",
        len(set(NASZE.values())) == 5, set(NASZE.values()))

print()
print("=== 4. BRAMKA 1: NAZWANY DECYDENT Z DATA ===")
sprawdz("komplet przechodzi", stages.bramka_kandydata(KOMPLET)[0])
for opis, k in (("bez decydenta", wariant(decision="")),
                ("decydent bez daty", wariant(decision="ustalone przez komitet")),
                ("zjawisko fizyczne", wariant(decision="nikt, tak dziala fizyka"))):
    ok, powod = stages.bramka_kandydata(k)
    sprawdz("%-22s odpada" % opis, not ok, powod)

print()
print("=== 5. BRAMKA 2: NIEWIEDZA TO NIE PRZEKONANIE ===")
# Najostrzejsza regula w calym potoku. „Wiekszosc nie wie" produkuje trivie:
# skoro nikt nie ma zdania, nie ma czego zlamac i nie ma na co odpowiedziec.
for zdanie in ("Most people do not know how this works",
               "Most readers have never heard of this symbol",
               "Readers are unaware of the rule behind it"):
    ok, powod = stages.bramka_kandydata(wariant(wrong_belief=zdanie))
    sprawdz("odrzuca: %s" % zdanie[:42], not ok, powod)
ok, _ = stages.bramka_kandydata(
    wariant(wrong_belief="Most people assume SPF 50 blocks twice as much as SPF 25"))
sprawdz("ale prawdziwe przekonanie przechodzi", ok)

print()
print("=== 6. BRAMKI 3 I 4: KONTAKT I SPRAWDZALNOSC ===")
sprawdz("bez skutku w reku odpada",
        not stages.bramka_kandydata(wariant(consequence=""))[0])
sprawdz("bez zrodla odpada", not stages.bramka_kandydata(wariant(url="brak"))[0])

print()
print("=== 7. SEZONOWOSC ===")
from datetime import datetime, timezone   # noqa: E402
sprawdz("kazdy miesiac ma rzeczy w reku",
        all(config.co_teraz_w_reku(datetime(2026, m, 15, tzinfo=timezone.utc))
            for m in range(1, 13)))
sierpien = config.co_teraz_w_reku(datetime(2026, 8, 15, tzinfo=timezone.utc))
styczen = config.co_teraz_w_reku(datetime(2026, 1, 15, tzinfo=timezone.utc))
sprawdz("sierpien to nie styczen", sierpien != styczen)
sprawdz("sierpien wymienia krem z filtrem", "sunscreen" in sierpien, sierpien)
sprawdz("pazdziernik wymienia ogrzewanie",
        "heating" in config.co_teraz_w_reku(datetime(2026, 10, 1, tzinfo=timezone.utc)))

print()
print("=== 8. PROMPT NIESIE OBIE OSIE I SEZON ===")
tekst = (config.PROMPTS_DIR / "ciekawostki.md").read_text(encoding="utf-8")
for pole in ("{dziedziny}", "{generatory}", "{w_reku}", "{miesiac}"):
    sprawdz("prompt ma %s" % pole, pole in tekst)
sprawdz("prompt tlumaczy, po co druga os",
        "They do not tell you what you are looking" in tekst)
sprawdz("prompt zamawia nadprodukcje",
        config.KANDYDATOW_NA_PRZEBIEG >= 20, config.KANDYDATOW_NA_PRZEBIEG)

print()
print("=== 9. ETAP PRZEKAZUJE WZORCE DO PROMPTU ===")
zrodlo = open("agent-v3/stages.py", encoding="utf-8").read()
sprawdz("znajdz_ciekawostki losuje wzorce", "config.losowe_generatory()" in zrodlo)
sprawdz("i podaje sezon", "co_teraz_w_reku" in zrodlo)
try:
    g = config.losowe_generatory()
    gotowy = stages._prompt(
        "ciekawostki.md", ile=25, dziedziny="- transport",
        generatory="\n".join("**%s** — %s" % (x, config.GENERATORY[x]) for x in g),
        miesiac="August", w_reku=config.co_teraz_w_reku(), uzyte="(nic)")
    sprawdz("prompt renderuje sie bez wyjatku", True)
    sprawdz("wzorce trafiaja do tekstu", any(x in gotowy for x in g))
    sprawdz("nie zostalo niepodstawione pole",
            not re.search(r"\{(dziedziny|generatory|w_reku|miesiac|ile|uzyte)\}", gotowy))
except Exception as e:
    sprawdz("prompt renderuje sie bez wyjatku", False, repr(e))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
