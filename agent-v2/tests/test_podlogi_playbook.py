"""Szesc nowych podlog z playbooka — sprawdzone na PRAWDZIWYM artykule 0025.

Playbook (20 sierpnia) postawil szereg zarzutow wobec artykulu o kodzie
zywicy. Zanim cokolwiek z niego wzialem, sprawdzilem te zarzuty na tekscie —
i wszystkie mierzalne okazaly sie prawdziwe. Dlatego 0025 jest tu materialem
dowodowym, nie przykladem: kazda nowa podloga MUSI sie na nim zapalic. Jesli
ktoras milczy, to znaczy, ze mierzy cos innego, niz mysle.

CO TE PODLOGI ROBIA, A CZEGO NIE. Wszystkie ZAKAZUJA i zadna nie nakazuje
pozycji. To rozroznienie jest cala ostroznoscia tej zmiany: regula zakazujaca
usuwa wade i zostawia przestrzen otwarta, regula nakazujaca („zwrot do
czytelnika na 25-40% glebokosci") wypelnia ja jedna odpowiedzia i po dziesieciu
tekstach sama staje sie podpisem maszyny. Juz raz na tym poleglismy: naprawa
wad TRESCI zamienila sie w wade FORMY, bo prompt zamawial szkielet.

Dlatego szosta podloga — ODCISK_FORMY — pilnuje samej naprawy. Skoro
dokladamy kilkanascie regul dotyczacych ksztaltu, ktos musi patrzec, czy
ksztalt nie zrobil sie jeden.

MATERIAL DOWODOWY LEZY POZA REPOZYTORIUM — I TO JEST TU NAJWAZNIEJSZE ZDANIE.
`agent-v2/data/` jest w `.gitignore`, wiec artykul 0025 istnieje na maszynie,
ktora go napisala, i NIE ISTNIEJE na swiezym klonie ani na serwerze. Do
2 wrzesnia 2026 test po cichu podstawial wtedy wbudowane wycinki i szedl
dalej — a wycinki sa krotsze i INNEGO KSZTALTU niz pelny tekst, wiec piec
asercji o polozeniu akapitu granic mowilo wtedy „podloga sie nie zapalila",
choc naprawde brakowalo dowodu. Ten sam plik dawal wiec na serwerze pieciu
falszywych alarmow o podlogach, a lokalnie komplet OK.

DZIS JEST TAK: co da sie zmierzyc na wycinkach, mierzymy WSZEDZIE — i to
komplet kontrdowodow oraz piec z szesciu podlog. Czego wycinki nie unosza,
mierzymy tylko przy pelnym 0025, a jego brak oblewa DOKLADNIE JEDNA asercje,
ktora mowi wprost, czego brakuje. Zaden komunikat nie udaje juz, ze to podloga
zawiodla.
"""
import pathlib
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


# --- prawdziwy tekst, nie wymyslony ---------------------------------------
KANDYDACI = list(pathlib.Path("agent-v2/data/articles").glob("0025-*was-never*.md"))
KANDYDACI = [p for p in KANDYDACI if not p.name.endswith(".uwagi.md")]
PELNY_0025 = KANDYDACI[0].read_text(encoding="utf-8") if KANDYDACI else ""

# WYCINKI VERBATIM Z 0025 — to jest material dowodowy, ktory JEST w
# repozytorium, i on idzie do bramek ZAWSZE, takze wtedy, gdy pelny artykul
# lezy obok. Dzieki temu ten plik mierzy na serwerze to samo, co lokalnie.
WYCINKI = """Turn over almost any plastic container and you will find a small triangle with a number inside it, molded into the base. In one survey, 68% of Americans thought anything labeled with the code could be recycled.

Here is my reading of who got what out of that. A uniform code genuinely helped recyclers. Whether anyone planned that effect is a separate question; the benefit was collected either way.

Was the costume deliberate? The published histories do not establish intent, and I will not invent it. What they do establish is the correction.

My reading of that design is that it forces a label to answer for real capacity. My suspicion is that this class of misreading survives for a simple reason: it costs the sender nothing.

Nothing in the number tells you what your own curbside program will take; a code identifies a resin, not a destination, and local recyclability is a separate question the mark cannot answer. Why some items skip the code entirely is only partly explained by the patchwork of state mandates. Why the less common resins lack workable recycling markets is stated in the published accounts only in outline. Whether the solid triangle will reduce the confusion is unknown. And what happens to any particular coded container once it leaves your hand, the code cannot say.

The beneficiary of the original design has a name."""

# Bramki dostaja WYCINKI — te same wszedzie. Pelny 0025 dostaje osobna,
# jawnie oznaczona sekcje na koncu pliku.
ARTYKUL = WYCINKI

KARTA = {"confirmed_claims": [
    {"text": "resin code", "url": "https://astm.org/x"},
    {"text": "68 percent survey", "url": "https://scientificamerican.com/y"},
]}

print("=== 0. MATERIAL DOWODOWY ===")
print("    do bramek idą: wycinki verbatim z 0025 (%d słów) — wszędzie te same"
      % len(WYCINKI.split()))
print("    pełny 0025:    %s"
      % (("%s, %d słów" % (KANDYDACI[0].name, len(PELNY_0025.split())))
         if KANDYDACI else "BRAK (data/ jest w .gitignore)"))
# JEDYNA ASERCJA, KTORA OBLEWA PRZY BRAKU PELNEGO TEKSTU — i mowi wprost,
# czego brakuje. Docstring obiecuje, ze kazda nowa podloga zapali sie na 0025;
# bez tego pliku obietnica jest niesprawdzalna, a niesprawdzalna obietnica to
# w tym repozytorium osobna klasa bledu. Wycinki jej NIE zastepuja: sa krotsze
# i innego ksztaltu, wiec podlogi pytajace o POLOZENIE nie maja na czym stanac.
sprawdz("materiał dowodowy 0025 jest pod ręką", bool(PELNY_0025),
        "brak agent-v2/data/articles/0025-*was-never*.md — katalog jest "
        "w .gitignore, więc na świeżym klonie i na serwerze pliku nie ma; "
        "sekcje 5b i 7 zostaną pominięte")

print()
print("=== 1. BUDZET ZASTRZEZEN ===")
z = gates.zastrzezenia(ARTYKUL)
print("    znalezione: %s" % [x.lower() for x in z])
sprawdz("budżet wynosi 1", config.BUDZET_ZASTRZEZEN == 1, config.BUDZET_ZASTRZEZEN)
sprawdz("0025 przekracza budżet", len(z) > config.BUDZET_ZASTRZEZEN, len(z))
sprawdz("łapie 'my reading'", any("my reading" in x.lower() for x in z))
sprawdz("łapie 'my suspicion'", any("my suspicion" in x.lower() for x in z))
# KONTRDOWOD: tekst z jednym zastrzezeniem ma przechodzic. Bez tego bramka
# mowilaby tylko „nie uzywaj pierwszej osoby", a to nie o to chodzi.
sprawdz("jedno zastrzeżenie przechodzi",
        len(gates.zastrzezenia("My reading is that the rule came first. "
                               "The record says otherwise.")) == 1)
sprawdz("tekst bez zastrzeżeń przechodzi",
        gates.zastrzezenia("The code identifies a resin. ASTM says so.") == [])

print()
print("=== 2. OBWIESZCZONA POWSCIAGLIWOSC ===")
sprawdz("łapie 'I will not invent it'",
        bool(gates.POWSCIAGLIWOSC.search(ARTYKUL)))
sprawdz("łapie 'I refuse to speculate'",
        bool(gates.POWSCIAGLIWOSC.search("and I refuse to speculate about it")))
# KONTRDOWOD: nazwanie luki BEZ zapowiadania cnoty ma przechodzic.
sprawdz("samo nazwanie luki przechodzi",
        not gates.POWSCIAGLIWOSC.search(
            "The published histories do not establish intent."))

print()
print("=== 3. ZAKAZANE OTWARCIE ===")
o = gates.zakazane_otwarcie(ARTYKUL)
print("    %s" % (o[:96] or "(nic)"))
sprawdz("0025 otwiera się zakazanie", bool(o), "nie złapane")
sprawdz("to jest 'Turn over'", o.lower().startswith("turn over"), o[:40])
for zle in ("Look at the label on your jar.", "Next time you board a plane, look up.",
            "Most people think the date is a safety limit.", "We all know the drill."):
    sprawdz("odrzuca: %s" % zle[:34], bool(gates.zakazane_otwarcie(zle)))
# KONTRDOWOD: dobre otwarcia maja przechodzic, inaczej bramka zakazuje wszystkiego.
for dobre in ("In 2018 the European grid ran slow and clocks lost six minutes.",
              "The mark was designed for someone else entirely.",
              "Nine percent of all plastic ever made has been recycled."):
    sprawdz("przepuszcza: %s" % dobre[:34], not gates.zakazane_otwarcie(dobre))

print()
print("=== 4. STATYSTYKA BEZ ZRODLA ===")
s = gates.statystyki_bez_zrodla(ARTYKUL)
for x in s:
    print("    %s" % x[:100])
sprawdz("0025 ma taką statystykę", bool(s), "nie złapane")
sprawdz("to jest 'In one survey, 68%'",
        any("in one survey" in x.lower() for x in s), s)
# KONTRDOWOD 1: niby-zrodlo BEZ liczby jest nieszkodliwe i ma przechodzic.
sprawdz("bez liczby nie zgłasza",
        gates.statystyki_bez_zrodla("In one survey, opinions were mixed.") == [])
# KONTRDOWOD 2: liczba Z nazwanym zrodlem ma przechodzic.
sprawdz("liczba z przypisem przechodzi",
        gates.statystyki_bez_zrodla(
            "Scientific American counted 39 states with the mandate.") == [])

print()
print("=== 5. NIEWIADOME NA KONCU ===")
# TA PODLOGA PYTA O POLOZENIE, a nie o istnienie granic — wiec na wycinkach
# NIE MA CZEGO ZMIERZYC: skrot ma szesc akapitow zamiast dwunastu i ten sam
# akapit wypada w nim na innej glebokosci. Prawdziwy pomiar na 0025 jest
# w sekcji 5b; tutaj zostaja oba kontrdowody, ktore stoja na wlasnym
# materiale i dzialaja wszedzie tak samo.
# KONTRDOWOD 1: pojedyncza niewiadoma nie jest passusem.
sprawdz("jedna niewiadoma nie wystarcza",
        gates.niewiadome_na_koncu(
            "A. " * 300 + "\n\nWhether the fix worked is unknown, and that is "
            "the end of what the record carries on the question here.") == "")
# KONTRDOWOD 2: ten sam akapit NA POCZATKU ma przechodzic — bramka pyta o
# pozycje, nie o istnienie granic.
wczesnie = ("Whether it was deliberate is unknown and the record does not "
            "establish it; what happens later the code cannot say.\n\n"
            + "Filler sentence here. " * 200)
sprawdz("ten sam akapit na początku przechodzi",
        gates.niewiadome_na_koncu(wczesnie) == "", gates.niewiadome_na_koncu(wczesnie))

print()
print("=== 5b. POLOZENIE AKAPITU GRANIC — TYLKO NA PELNYM 0025 ===")
if PELNY_0025:
    n = gates.niewiadome_na_koncu(PELNY_0025)
    print("    %s" % (n[:110] or "(nic)"))
    sprawdz("0025 ma zbiorczy akapit granic na końcu", bool(n), "nie złapane")
    sprawdz("i jest w ostatniej trzeciej",
            n.startswith(("6", "7", "8", "9", "1")), n[:12])
    _odc_pelny = gates.odcisk_formy(PELNY_0025)
    sprawdz("odcisk pełnego 0025 widzi, że otwarcie nie ma liczby",
            _odc_pelny["liczba_w_otwarciu"] is False, _odc_pelny)
    sprawdz("i widzi granice na końcu",
            _odc_pelny["granice_na_koncu"] is True, _odc_pelny)
else:
    # NIE `sprawdz(..., True)`. Asercja, ktora nie moze oblac, zawyza licznik
    # zdanych i niczego nie pilnuje — o braku dowodu powiedziala juz sekcja 0.
    print("    POMINIETE — brak pełnego 0025 (sekcja 0 już to zgłosiła)")

print()
print("=== 6. ODCISK FORMY — PILNUJE SAMEJ NAPRAWY ===")
odc = gates.odcisk_formy(ARTYKUL)
print("    odcisk wycinków: %s" % odc)
sprawdz("odcisk ma sześć cech", len(odc) == 6, len(odc))

# TEN SAM TEKST TO NIE POWTORZONA FORMA, tylko ten sam plik. W przebiegu
# bramka wola sie PRZED zapisem, wiec artykul nie trafia do porownania — ale
# opieranie poprawnosci na kolejnosci dwoch linijek w innym module jest za
# cienkie, wiec porownanie odrzuca identyczna tresc samo z siebie.
sprawdz("ten sam tekst NIE jest zgłaszany jako powtórzona forma",
        gates.powtorzona_forma(ARTYKUL, [ARTYKUL]) == "",
        gates.powtorzona_forma(ARTYKUL, [ARTYKUL])[:70])
# Ale blizniak o tym samym ksztalcie i innej tresci — juz tak.
BLIZNIAK = ARTYKUL.replace("plastic", "polymer").replace("triangle", "mark")
sprawdz("bliźniak o tym samym kształcie zgłoszony",
        bool(gates.powtorzona_forma(ARTYKUL, [BLIZNIAK])),
        gates.odcisk_formy(BLIZNIAK))
sprawdz("brak poprzednich = brak zarzutu",
        gates.powtorzona_forma(ARTYKUL, []) == "")
# KONTRDOWOD: tekst o INNYM ksztalcie nie moze byc zgloszony, inaczej bramka
# krzyczalaby zawsze i nikt by jej nie sluchal.
inny = ("Nine percent of all plastic ever made has been recycled.\n\n"
        + "Short line. " * 40)
sprawdz("inny kształt nie jest zgłaszany",
        gates.powtorzona_forma(inny, [ARTYKUL]) == "",
        gates.powtorzona_forma(inny, [ARTYKUL]))

print()
print("=== 7. WSZYSTKO RAZEM ===")
# Do porownania formy podajemy BLIZNIAKA, nie ten sam tekst — inaczej
# bramka slusznie milczy i sekcja niczego by nie sprawdzila.
def zapalone(tekst):
    blizniak = tekst.replace("plastic", "polymer").replace("triangle", "mark")
    uwagi = gates.deterministic_floors(tekst, KARTA, poprzednie=[blizniak])
    return uwagi, {u["gate"] for u in uwagi}


uwagi, nazwy = zapalone(ARTYKUL)
print("    na wycinkach: %s" % sorted(nazwy))
# Piec z szesciu podlog stoi na TRESCI i zapala sie na wycinkach — wszedzie
# tak samo. Szosta (NIEWIADOME_NA_KONCU) pyta o polozenie i potrzebuje
# pelnego tekstu, wiec jest nizej.
for g in ("BUDZET_ZASTRZEZEN", "OBWIESZCZONA_POWSCIAGLIWOSC", "ZAKAZANE_OTWARCIE",
          "STATYSTYKA_BEZ_ZRODLA", "ODCISK_FORMY"):
    sprawdz("%-28s zapala się na wycinkach 0025" % g, g in nazwy)

if PELNY_0025:
    uwagi_pelne, nazwy_pelne = zapalone(PELNY_0025)
    print("    na pełnym 0025: %s" % sorted(nazwy_pelne))
    # TU JEST OBIETNICA Z DOCSTRINGU: kazda podloga MUSI sie zapalic na 0025.
    for g in ("BUDZET_ZASTRZEZEN", "OBWIESZCZONA_POWSCIAGLIWOSC",
              "ZAKAZANE_OTWARCIE", "STATYSTYKA_BEZ_ZRODLA",
              "NIEWIADOME_NA_KONCU", "ODCISK_FORMY"):
        sprawdz("%-28s zapala się na pełnym 0025" % g, g in nazwy_pelne)
else:
    print("    POMINIETE — brak pełnego 0025 (sekcja 0 już to zgłosiła)")

print()
print("=== 8. NIC NIE BLOKUJE ARTYKULU ===")
# Decyzja wlasciciela z 15 sierpnia stoi: research jest oplacony, wiec tekst
# powstaje ZAWSZE, a uwagi wracaja do przeczytania.
status, powod = gates.verdict(uwagi)
sprawdz("werdykt nadal SAVED", status == "SAVED", status)
sprawdz("bez powodu blokady", powod is None, powod)

print()
print("=== 9. STARE PODLOGI NIETKNIETE ===")
sprawdz("zmyślone przeżycie nadal łapane",
        any(u["gate"] == "ZMYSLONE_PRZEZYCIE" for u in gates.deterministic_floors(
            "Last week, I stood in the aisle and counted.", KARTA)))
sprawdz("nieistniejące badanie nadal łapane",
        any(u["gate"] == "NIEISTNIEJACE_BADANIE" for u in gates.deterministic_floors(
            "According to a recent study, this is common.", KARTA)))
sprawdz("stare wywołanie bez `poprzednie` nadal działa",
        isinstance(gates.deterministic_floors(ARTYKUL, KARTA), list))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
