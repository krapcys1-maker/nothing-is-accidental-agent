"""Wskazowki dla pisarza z playbooka: same ZAKAZY, zaden nakaz ksztaltu.

Playbook z 20 sierpnia ma okolo czterdziestu regul i czesc z nich kaze umiescic
cos w konkretnym miejscu: lede z liczba, przylapanie czytelnika na 25-40%,
najmocniejszy fakt w osobnym akapicie, trzy przyspieszajace akapity koncowe.
Zastosowane doslownie daja szablon — a to jest ta sama wada, ktora juz raz
zrobilismy: naprawa wad TRESCI zamienila sie w wade FORMY, bo prompt zamawial
szkielet. Wtedy ratunkiem bylo losowanie ruchu koncowego i liczby paraleli.

Dlatego do promptu weszly wylacznie reguly ZAKAZUJACE. Ten test pilnuje obu
stron tej decyzji naraz: czy zakazy sa, i czy nie wsadzono przy okazji nakazu
pozycji. Druga polowa jest wazniejsza, bo to ona zabezpiecza przed nawrotem.
"""
import pathlib
import re
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import gates    # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


P = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf-8")
# Prompt jest lamany do 79 znakow, wiec KAZDE porownanie frazy robimy na
# tekscie ze sklejonymi bialymi znakami. Inaczej test oblewa sie na miejscu
# zlamania wiersza zamiast na braku reguly — i mowi o formatowaniu, nie o tresci.
PLASKI = " ".join(P.split())

print("=== 1. SZESC ZAKAZOW JEST W PROMPCIE ===")
ZAKAZY = {
    "nie wydawaj tego samego twierdzenia dwa razy": "supporting rather than advancing",
    "najmocniejszy fakt nie w tonie przypisu":      "voice of a footnote",
    "wnioskowanie znaczy sie struktura zdania":     "not by a label",
    "nie obwieszczaj powsciagliwosci":              "announce your own restraint",
    "kazda liczba niesie zrodlo w swoim zdaniu":    "carries its source in the sentence",
    # Bylo: "where it arises, alone" — zdanie zakazywalo akapitu granic,
    # ktory PIEC innych miejsc promptu zaklada (regula, regula o pierwszym
    # zdaniu, zakaz rozdymania, pole schematu, bramka). Zostal jeden
    # akapit, a to zdanie rzadzi teraz jego POLOZENIEM.
    "granice tam, gdzie otwiera sie luka":          "where the gap opens",
}
for opis, fraza in ZAKAZY.items():
    sprawdz("%-46s" % opis, fraza in PLASKI, fraza)

print()
print("=== 2. ZAKAZANE OTWARCIA — PROMPT I BRAMKA MOWIA TO SAMO ===")
sprawdz("prompt zakazuje wysylania czytelnika po ogledziny",
        "go and look at something" in PLASKI)
for fraza in ("Turn over", "Look at the label", "Next time you", "Ask most people",
              "We all know"):
    sprawdz("prompt wymienia %r" % fraza, fraza in PLASKI)
    sprawdz("  i bramka je łapie", bool(gates.zakazane_otwarcie(fraza + " the thing.")),
            fraza)

print()
print("=== 3. PROMPT NIE ZAMAWIA KSZTALTU ===")
# To jest sedno. Kazda z tych fraz oznaczalaby nakaz pozycji.
NAKAZY = [
    (r"\b25\s*%|\b40\s*%|\b60\s*%|\b70\s*%", "procent głębokości"),
    (r"first sentence must", "nakaz co do pierwszego zdania"),
    (r"must contain a number", "nakaz liczby w otwarciu"),
    (r"its own paragraph", "nakaz osobnego akapitu"),
    (r"last three paragraphs", "nakaz trzech akapitów końcowych"),
    (r"pull quote", "nakaz cytatu do wyciągnięcia"),
    (r"shortest sentence in", "nakaz najkrótszego zdania w sekcji"),
    (r"words or fewer per", "nakaz rytmu co N słów"),
]
for wzor, opis in NAKAZY:
    trafienie = re.search(wzor, PLASKI, re.I)
    sprawdz("brak nakazu: %-38s" % opis, trafienie is None,
            trafienie.group(0) if trafienie else "")

sprawdz("prompt mówi wprost, że kształt należy do pisarza",
        "the shape of the piece is yours" in PLASKI)
sprawdz("i że powtórzone otwarcie to strata",
        "opens the same way as the last one" in PLASKI)

print()
print("=== 4. PULAPKA: SCIECIE ZASTRZEZEN NIE MOZE ZROBIC Z NICH FAKTOW ===")
# Gdyby prompt kazal tylko „mniej zastrzezen", pisarz podalby wnioski jako
# fakty — czyli zamiast tiku dostalibysmy zdania bez pokrycia, wade
# powazniejsza, i to wlasnie ta, ktorej pilnuje recenzent.
sprawdz("prompt ostrzega przed niezaznaczonym domysłem",
        "unmarked guess" in PLASKI)
sprawdz("i mówi wprost, że to gorsza wada",
        "far\nworse fault" in P or "far worse fault" in P)
sprawdz("i pozwala zostawić zastrzeżenie, gdy inaczej się nie da",
        "keep the hedge" in PLASKI)
sprawdz("config ostrzega o tej samej pułapce",
        "UWAGA NA PULAPKE" in (config.__file__ and
                               pathlib.Path(config.__file__).read_text(encoding="utf-8")))

print()
print("=== 5. NOWY TEKST NIE ROZWALA STAREJ BRAMKI FRAZA_Z_INSTRUKCJI ===")
# Bramka porownuje szesciowyrazowe ciagi artykulu z pisarz.md. Dopisanie
# tekstu do promptu powieksza zbior zakazanych ciagow — sprawdzamy, ze nadal
# lapie wklejke i nadal przepuszcza zwykla proze.
wklejka = "the shape of the piece is yours and nothing else"
sprawdz("wklejka z promptu nadal łapana",
        any("shape of the piece" in f for f in gates.frazy_z_instrukcji(wklejka)),
        gates.frazy_z_instrukcji(wklejka))
zwykly = ("The resin code identifies a polymer. It was published in 1988 and "
          "revised in 2013 after complaints about the arrows around it.")
sprawdz("zwykła proza nie jest zgłaszana",
        gates.frazy_z_instrukcji(zwykly) == [], gates.frazy_z_instrukcji(zwykly))

print()
print("=== 6. PROMPT NADAL SIE SKLADA ===")
import stages   # noqa: E402
try:
    gotowy = stages._prompt(
        "pisarz.md", card_json="{}", language="English", target_words=1075,
        min_words=900, max_words=1250, kotwica_dlugosci="x",
        style_examples="x", style_positive="y",
        style_negative="z", ile_paraleli="one",
        ruch_koncowy_nazwa="KTO_NA_TYM_STOI",
        ruch_koncowy="nazwij beneficjenta i tego, kto placi")
    sprawdz("renderuje się bez wyjątku", True)
    sprawdz("niesie nowe zakazy", "voice of a footnote" in gotowy)
    sprawdz("nie zostało niepodstawione pole",
            not re.search(r"\{(card_json|style_examples|ile_paraleli)\}", gotowy))
except KeyError as e:
    sprawdz("renderuje się bez wyjątku", False, "brakujące pole: %s" % e)
except Exception as e:
    sprawdz("renderuje się bez wyjątku", False, repr(e))

print()
print("=== OTWARCIE: ZAKAZ ZOSTAJE, NAKAZ ZDJETY ===")
# Nakaz „Open with the collision itself" byl jednoczesnie najtrwalsza sygnatura
# i kanalem fabrykacji. Dla SYSTEM_UNDER_TEST karta NIE NIESIE polowki-
# zalozenia — skaut daje tam `the_moment`, `open_outcome` i `governing_record`
# wprost „instead" — a kontyngent zada, zeby polowa listy byla tego rodzaju.
# Wiec przy co drugim artykule pisarz dorabial „everyone assumes" z niczego,
# i nikt tego nie lapal: recenzent klasyfikuje takie zdania jako PROSE.
sprawdz("nie ma juz nakazu jednego otwarcia",
        "Open with the collision itself" not in PLASKI)
sprawdz("jest zakaz dorabiania brakujacej polowki",
        "Do not manufacture the missing half." in PLASKI)
sprawdz("i powod, dla ktorego nikt by tego nie zlapal",
        "no figure to check and no source to miss" in PLASKI)
# PODLOGA MUSI ZOSTAC — zdjecie nakazu nie moze otworzyc drogi errandom
# ani teasowaniu mechanizmu.
sprawdz("zakaz otwarcia-polecenia zostal",
        "Do not open by sending the reader to go and look at something." in PLASKI)
sprawdz("i zakaz przetrzymywania mechanizmu",
        "Name that mechanism early and plainly. Do not withhold it for a reveal."
        in PLASKI)
sprawdz("kolizja nadal DOZWOLONA tam, gdzie karta ja niesie",
        "the collision between" in PLASKI and "broken_belief" in PLASKI)
# KONTRDOWOD: gdyby prompt po prostu milczal o otwarciu, powyzsze przeszloby
# tak samo. Wymagamy, zeby aktywnie kierowal do tego, co karta MA.
sprawdz("prompt mowi, czym otwierac przy braku przekonania",
        "Open with whatever this card actually holds." in PLASKI)

print()
print("=== POWSCIAGLIWOSC MA BYC NIEWIDOCZNA ===")
# Cztery z szesciu artykulow przystawaly, zeby powiedziec o wlasnej ostroznosci:
# „I will not invent it", „I want to be careful here", „and I will say them once
# rather than hedge throughout". Czytelnik, ktoremu mowi sie, ze jest sie
# ostroznym, dostaje samoocene; czytelnik, ktory widzi zatrzymanie, dostaje dowod.
sprawdz("prompt zakazuje ogloszen o wlasnej powsciagliwosci",
        "do not perform your own restraint" in PLASKI)
sprawdz("i cytuje konkretne przyklady z opublikowanych tekstow",
        "I will not invent it" in PLASKI and "I want to be careful here" in PLASKI)
sprawdz("i nazywa roznice: samoocena kontra dowod",
        "watches you stop has evidence" in PLASKI)
# KONTRDOWOD, I TO JEST TU NAJWAZNIEJSZE: zakaz NIE MOZE zabrac markerow
# wnioskowania. Recenzent po nich rozpoznaje INFERENCE i oszczedza smiale
# odczytania — bez nich czesc z nich dostawalaby flage albo cicho wypadala.
sprawdz("markery wnioskowania zostaja wprost dozwolone",
        "they stay" in PLASKI and "about the claim, not about your conduct" in PLASKI)
for m in ("my reading is", "this looks like", "the structure suggests"):
    sprawdz("  marker %r nadal w prompcie" % m, m in PLASKI)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
