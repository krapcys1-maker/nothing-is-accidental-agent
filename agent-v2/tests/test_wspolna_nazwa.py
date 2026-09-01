# -*- coding: utf-8 -*-
"""Trzy notki o tym samym modelu w jeden dzien — „plaskosc", o ktorej mowil wlasciciel.

CO WYSZLO 31 sierpnia 2026. Piec notek, z tego TRZY o modelu GLM-5.3-Flash:

    12:40  „On GLM-5.3 Flash, the run that passes a flaky task is the longer
            one only 46% of the time."
    19:58  „Ox Alpha (...) was Zhipu's GLM-5.3-Flash, served entirely from
            a cluster of more than 100,000 Chinese-made chips."
    22:09  „GLM-5.3-Flash charges $0.15 per million input tokens and still
            scores 57 on the Artificial Analysis Intelligence Index."

Trzy rozne ustalenia — o powtorzeniach, o chinskich ukladach, o cenie. Ale
czytelnik nie widzi trzech ustalen. Widzi trzy notki o tym samym modelu
w ciagu jednego dnia.

WYKRYWACZ UZNAL KAZDA PARE ZA ROZNA. `_o_tym_samym` liczy wspolne rdzenie
i ich udzial; tu wspolnych bylo cztery, a udzial ponizej progu — bo kazda
notka mowila o czym innym INNYMI slowami. Dwie z nich dzielily przy tym
DOSLOWNIE token `glm-5.3-flash`.

BANK BYL PELEN BLIZNIAKOW, co to napedzalo. Zmierzone tego samego dnia na
53 wpisach po przestawieniu konta:

    GLM-5.3        8 wpisow        Ox Alpha        4
    Jalapeno       7               Spirit Airlines 3
    Hugging Face   5               Jane Street     3

Wykrywacz bliźniakow W PARTII istnial i dzialal (`_dzielą_rzadkie`), ale byl
funkcja LOKALNA w `wez_kandydatow` — sciezka notek go nie widziala, a
porownanie MIEDZY DNIAMI szlo wylacznie po slowach.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import stages  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# PRAWDZIWE TEKSTY Z PRODUKCJI, skrocone. Nie wymyslone.
GLM_A = ("On GLM-5.3 Flash, the run that passes a flaky task is the longer one "
         "only 46% of the time. Worse than a coin flip.")
GLM_B = ("Ox Alpha, the anonymous model that swept OpenRouter's usage charts, "
         "was Zhipu's GLM-5.3-Flash, served from Chinese-made chips.")
GLM_C = ("Cheap models are supposed to be worse models. GLM-5.3-Flash charges "
         "$0.15 per million input tokens and still scores 57.")
INNA = ("A model's refusal is not a rule. It's a single direction in its "
        "weights, and subtracting that direction removes refusing altogether.")
OSOBISTA = ("Two paragraphs. That's how much of any answer I skip before I "
            "start reading. Somewhere in the last year the model trained me.")

print("=== 1. TRZY NOTKI O GLM SA ROZPOZNANE JAKO TO SAMO ===")
for opis, a, b in (("12:40 vs 19:58", GLM_A, GLM_B),
                   ("19:58 vs 22:09", GLM_B, GLM_C),
                   ("12:40 vs 22:09", GLM_A, GLM_C)):
    sprawdz("  %s" % opis, stages.wspolna_nazwa(a, b) == "glm53",
            stages.wspolna_nazwa(a, b))

print()
print("=== 2. MYSLNIK I SPACJA TO TA SAMA NAZWA ===")
# To bylo sedno: `GLM-5.3-Flash` (jeden token) wobec `GLM-5.3 Flash` (dwa).
sprawdz("`GLM-5.3-Flash` daje rdzen glm53",
        "glm53" in stages.nazwy_wlasne("GLM-5.3-Flash charges $0.15"))
sprawdz("`GLM-5.3 Flash` tez",
        "glm53" in stages.nazwy_wlasne("On GLM-5.3 Flash, the run"))
sprawdz("i pelna postac zostaje przy zapisie z myslnikiem",
        "glm53flash" in stages.nazwy_wlasne("GLM-5.3-Flash charges"))

print()
print("=== 3. ROZNE TEMATY ZOSTAJA ROZNE ===")
# Poprawka, ktora blokuje wszystko, jest gorsza od wady: przy realizacji
# normy notek 63% falszywy alarm kosztuje notke.
for opis, a, b in (("GLM vs abliteracja", GLM_A, INNA),
                   ("GLM vs osobista", GLM_A, OSOBISTA),
                   ("abliteracja vs osobista", INNA, OSOBISTA)):
    sprawdz("  %s -> rozne" % opis, not stages.wspolna_nazwa(a, b),
            stages.wspolna_nazwa(a, b))

print()
print("=== 4. POCZATEK ZDANIA NIE JEST NAZWA WLASNA ===")
# „Cheap models are supposed..." oddawalo `cheap` jako nazwe, wiec dwa
# dowolne teksty zaczynajace sie tym samym slowem wygladaly na blizniaki.
sprawdz("`Cheap` na poczatku zdania odsiane",
        "cheap" not in stages.nazwy_wlasne(GLM_C), sorted(stages.nazwy_wlasne(GLM_C)))
sprawdz("dwa teksty od tego samego slowa to nie blizniaki",
        not stages.wspolna_nazwa("Cheap tricks never work. The point is simple.",
                                 "Cheap talk is what this industry runs on."))
# ALE nazwa z cyfra albo wielka litera w srodku liczy sie takze na poczatku.
sprawdz("`GPT-5` na poczatku zdania nadal jest nazwa",
        "gpt5" in stages.nazwy_wlasne("GPT-5 changed the default. Nothing else did."))

print()
print("=== 5. RZADKOSC LICZONA W KORPUSIE ===")
# Nazwa, ktora pada w polowie naszych notek („OpenAI"), nie odroznia niczego.
korpus = ["OpenAI said this. " * 2, "OpenAI said that.", "OpenAI again.",
          "Something about Jalapeno chips."]
sprawdz("czesta nazwa nie blokuje",
        not stages.wspolna_nazwa("OpenAI raised prices", "OpenAI hired someone",
                                 korpus))
sprawdz("rzadka nazwa blokuje",
        stages.wspolna_nazwa("The Jalapeno chip is inference-only",
                             "Nvidia lost to Jalapeno on watts", korpus)
        == "jalapeno")

# OGRANICZENIE, KTORE PRZYJMUJEMY SWIADOMIE. Nazwa stojaca WYLACZNIE na
# poczatku zdania przepada — „Jalapeno beat the GB200" nie odda `jalapeno`.
# To cena za odsianie „Cheap", „Three", „Same" i kazdego innego pierwszego
# slowa. Przy notce na 50-60 slow nazwa pada zwykle takze w srodku zdania,
# a falszywe trafienie kosztuje notke: przy realizacji normy 63% to nie
# jest darmowe. Test zapisuje to jako ZNANE, nie udaje, ze nie istnieje.
sprawdz("nazwa tylko na poczatku zdania przepada (znane ograniczenie)",
        not stages.wspolna_nazwa("The Jalapeno chip is inference-only",
                                 "Jalapeno beat the GB200", korpus))
sprawdz("bez korpusu wystarczy sama wspolna nazwa",
        stages.wspolna_nazwa("OpenAI raised prices", "OpenAI hired someone")
        == "openai")

print()
print("=== 6. WPIETE W WYBOR NOTKI, MIEDZY DNIAMI ===")
zrodlo = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
i = zrodlo.index("def wybierz_material(")
blok = zrodlo[i:zrodlo.index("\ndef ", i + 10)]
sprawdz("wybor notki pyta o wspolna nazwe", "wspolna_nazwa(" in blok)
sprawdz("i robi to po sprawdzeniu slow, nie zamiast",
        blok.index("POROWNANIE_MIEDZY_DNIAMI") < blok.index("wspolna_nazwa("))
sprawdz("korzysta z TEKSTOW, nie z gotowych rdzeni",
        "teksty_wczesniej" in blok)
sprawdz("i mowi w logu, co pominal", "[notki] pomijam" in blok)

print()
print("=== 7. DZIALANIE OD KONCA: WYBOR POMIJA POWTORKE ===")
wynik = stages.wybierz_material(
    [{"domain": "AI", "fact": GLM_B},
     {"domain": "AI", "fact": "Roughly 1200 agents traded 70,000 messages."}],
    unikaj=[], wczesniej=[GLM_A, INNA])
sprawdz("wzial temat o agentach, nie drugi raz o GLM",
        wynik and "1200 agents" in str(wynik.get("fact")), wynik)
# KONTRDOWOD: bez notki o GLM w pamieci ten sam kandydat ma przejsc.
wynik2 = stages.wybierz_material(
    [{"domain": "AI", "fact": GLM_B}], unikaj=[], wczesniej=[INNA])
sprawdz("a bez GLM w pamieci bierze go normalnie",
        wynik2 and "Ox Alpha" in str(wynik2.get("fact")), wynik2)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
