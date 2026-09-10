# -*- coding: utf-8 -*-
"""Notka ma GLOS, a nie tylko fakty. I ten glos naprawde dociera do modelu.

OCENA WLASCICIELA z 9 wrzesnia 2026, po przeczytaniu trzech kolejnych notek
na koncie: „to nie jest pisanie, to jest podawanie faktow, kanal stal sie news
roomem jakich tysiace, tak sie nigdy nie przebijemy".

Mial racje i przyczyny byly DWIE, obie do zmierzenia.

PRZYCZYNA 1 — REGULA DOWODOWA WIAZALA TAKZE MYSLENIE.

`notka.md` miala „Invent nothing. Every fact, number, date and name is in the
evidence above" i ZADNEJ przeciwwagi. `pisarz.md` (artykul) ma ja od dawna:

    „The rule above binds FACTS. It does not bind thinking (…) Analogy,
     comparison, interpretation (…) all of this is yours, and the piece is
     dull without it. A reader can get the regulation number anywhere. What
     they come here for is someone seeing the shape of the thing."

Artykul mial 527 wierszy opisu glosu. Notka miala jedno zdanie („pisz jak ktos,
kto tlumaczy cos znajomemu przy kawie") i kilkanascie zakazow. Pisarz notek
traktowal wiec jako zwiazane WSZYSTKO, lacznie z wlasna mysla — i pisal jedyne,
co przy takim zwiazaniu da sie napisac: recytacje.

PRZYCZYNA 2 — PLIK O TYM, JAK NIE BRZMIEC JAK MASZYNA, NIE BYL NIGDZIE
DOKLEJANY.

`prompts/po_ludzku.md` zaczyna sie od zdania: „Ten fragment jest dolaczany do
promptow komentarza, odpowiedzi i notki". NIE BYL. Zaden kod go nie czytal —
wlasna dokumentacja projektu wymienia go jako wade numer 10 („cztery pliki
w `prompts/` nie sa czytane przez zaden kod").

W tym niedoklejonym pliku stalo dokladnie to, czego brakowalo:

    „Vary it, hard (…) Sometimes answer in one short sentence"
    „Take a position. Where the honest reaction is blunt, be blunt"
    lista slow zdradzajacych maszyne (delve, moreover, robust, landscape…)

ZMIERZONE NA 96 OPUBLIKOWANYCH NOTKACH, zanim to naprawiono: slowo `strange`
w ZERO notek, `funny` w zero, `absurd` w zero, `why` w jednej. Konto ani razu
nie uznalo niczego za dziwne.

CZEGO TEN TEST PILNUJE:

  1. `po_ludzku.md` NAPRAWDE dociera do promptu notki, komentarza i odpowiedzi
     — sprawdzane przez zlozenie promptu, nie przez obecnosc pliku na dysku
  2. do artykulu NIE dociera (ma wlasny, obszerniejszy opis w `pisarz.md`)
  3. regula dowodowa jawnie NIE wiaze myslenia
  4. prompt opisuje, KTO pisze, a nie tylko czego nie wolno

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_notka_ma_glos.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import stages   # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  PADA  %s%s" % (opis, (" — " + dodatek) if dodatek else ""))


def notka():
    return stages._prompt(
        "notka.md", language="English", min_words=33, max_words=120,
        note_type="CIEKAWOSTKA", type_brief="x", note_form="PROSTA",
        form_brief="y", evidence="{}", rozbior="(brak)",
        ostatnie_otwarcia_json="[]", ostatnie_zakonczenia_json="[]")


print("=== 1. `po_ludzku.md` DOCIERA do promptow krotkich tekstow ===")
# Sprawdzane przez ZLOZENIE promptu, nie przez to, czy plik lezy na dysku.
# Przez pol roku lezal i nie docieral nigdzie.
_n = notka()
for opis, fragment in (
    ("rada o zmiennej dlugosci zdan", "Length: vary it, hard"),
    ("polecenie zajecia stanowiska", "Take a position"),
    ("lista slow zdradzajacych maszyne", "delve, moreover"),
    ("zakaz zamykania uklonem", "No summary, no \"overall\", no bow"),
):
    sprawdz("notka niesie: %s" % opis, fragment in _n, "brak %r" % fragment)

print()
print("=== 2. komentarz i odpowiedz MAJA te rady, ale wklejone w tresc ===")
# I to jest sedno wady. Naglowek `po_ludzku.md` wymienia trzy prompty. Dwa
# dostaly te rady przez RECZNE PRZEPISANIE do wlasnej tresci, trzeci — notka —
# nie dostal ich wcale, bo pliku zrodlowego nikt nie czytal. Doklejanie do
# wszystkich trzech dublowaloby tekst tam, gdzie juz jest.
for plik in ("komentarz.md", "odpowiedz.md"):
    tresc = (config.PROMPTS_DIR / plik).read_text(encoding="utf-8")
    sprawdz("%s ma rady WLASNE, wiec nie doklejamy" % plik,
            "Take a position" in tresc and plik not in stages.Z_PO_LUDZKU,
            "ma rady: %s, na liscie: %s"
            % ("Take a position" in tresc, plik in stages.Z_PO_LUDZKU))
sprawdz("doklejamy WYLACZNIE do notki",
        stages.Z_PO_LUDZKU == frozenset({"notka.md"}),
        sorted(stages.Z_PO_LUDZKU))
# Sprawdzamy fragment, ktorego notka NIE ma we wlasnej tresci — inaczej
# asercja mierzylaby sama siebie: sekcja „WHO IS WRITING" tez mowi „Take
# a position", wiec ten napis niczego by nie dowodzil o doklejaniu.
sprawdz("ogon wnosi do notki cos, czego ona sama nie ma",
        "delve, moreover" not in
        (config.PROMPTS_DIR / "notka.md").read_text(encoding="utf-8"))

print("=== 3. artykul NIE dostaje tego ogona ===")
# Ma wlasny opis glosu w `pisarz.md`, 527 wierszy. Doklejenie drugiego
# zestawu rad o tym samym rozjezdzalo by sie z nim przy pierwszej zmianie.
sprawdz("`pisarz.md` nie jest na liscie doklejania",
        "pisarz.md" not in stages.Z_PO_LUDZKU, sorted(stages.Z_PO_LUDZKU))
_p = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf-8")
sprawdz("i ma wlasny, obszerny opis glosu",
        "## The voice" in _p and len(_p.splitlines()) > 300,
        "%d wierszy" % len(_p.splitlines()))

print()
print("=== 4. regula dowodowa NIE wiaze myslenia ===")
sprawdz("notka mowi wprost, ze wiaze fakty, nie myslenie",
        "binds FACTS, not thinking" in _n)
sprawdz("i wymienia, co nalezy do piszacego",
        "Analogy, comparison, interpretation" in _n)
sprawdz("i kaze oznaczac mysl jako mysl, zamiast jej unikac",
        "An idea marked as an idea is never a violation" in _n)
sprawdz("i zabrania rozmydlania interpretacji dla bezpieczenstwa",
        "hedge an interpretation into meaninglessness" in _n)

print()
print("=== 5. prompt mowi, KTO pisze ===")
sprawdz("jest osobna sekcja o piszacym", "# WHO IS WRITING" in _n)
sprawdz("piszacy jest w srodku sprawy, nie ponad nia",
        "You are inside this, not above it" in _n)
sprawdz("ma powtarzalne odkrycie, po ktore wraca czytelnik",
        "stranger and simpler" in _n)
sprawdz("jest trudny do zaimponowania, ale nie kwasny",
        "hard to impress and you are not sour" in _n)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
