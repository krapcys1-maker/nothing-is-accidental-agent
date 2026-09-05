# -*- coding: utf-8 -*-
"""Nazwa paczki to nie wzmianka — a wzmianka po ukosniku to nadal wzmianka.

DWIE RZECZY, ZNALEZIONE JEDNA PRZY DRUGIEJ 5 wrzesnia 2026.

1. FALSZYWY ALARM. W banku lezal odrzucony fakt „Hugging Face published
   @huggingface/kernels, a package containing more than…" z powodem
   „zapora: wzmianka @ w tresci". Zapora wziela nazwe paczki za wzmianke
   o osobie — ten sam rodzaj bledu, co regula o slowie „no one" przy
   `bramka_kandydata`.

   ZDEJMUJEMY MALPE, A NIE WPUSZCZAMY FAKTU. Kuszace bylo dopisac wyjatek
   „`@nazwa` z ukosnikiem to nie wzmianka". Odrzucone: nie da sie bezpiecznie
   sprawdzic, czy Substack nie zamieni „@huggingface" w oznaczenie, zanim
   dojdzie do ukosnika. Zdjecie malpy jest scisle bezpieczniejsze od obu
   poprzednich zachowan — fakt zyje, a oznaczenie nie ma z czego powstac.

2. DZIURA, KTORA BYLA TAM OD POCZATKU. Sprawdzajac, czy poprawka z punktu 1
   nie otwiera furtki, zmierzylem zapore na surowych tekstach:

       „See github.com/@simonw for details."   PRZECHODZILO
       „path/@simonw is the handle."           PRZECHODZILO

   Wzorzec brzmial `(^|\\s)@…`, czyli sprawdzal malpe wylacznie po SPACJI albo
   na poczatku. Wszystko po innym znaku przechodzilo. Moja poprawka miala te
   furtke tylko poszerzyc o jeden przypadek; zamiast tego zamykam ja calą:
   granica to teraz KAZDY znak niebedacy litera, cyfra ani podkresleniem.

   Pierwsza wersja tego zamkniecia miala `[^\\w@]` i przepuszczala „@@simonw",
   bo pierwsza malpa nie byla granica dla drugiej — a komentarz przy niej
   twierdzil, ze taki przypadek jest lapany. Komentarz klamal; zlapal to
   dopiero ten test.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zapora_malpa.py
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
        print("  BLAD  %s   %s" % (opis, dodatek))


def przechodzi(tekst):
    """Cala droga, ktora przechodzi fakt: normalizacja, potem zapora."""
    po = stages.bez_malpy_w_nazwie_paczki(tekst)
    return stages.bez_wstrzykniecia(po)[0], po


print("=== 1. NAZWA PACZKI PRZECHODZI, BEZ MALPY ===")
_ok, _po = przechodzi("Hugging Face published @huggingface/kernels today.")
sprawdz("fakt z produkcji przechodzi", _ok, _po)
sprawdz("i malpa zniknela z tekstu", "@" not in _po, _po)
sprawdz("a nazwa paczki zostala czytelna",
        "huggingface/kernels" in _po, _po)
_ok2, _po2 = przechodzi("@openai/agents shipped a runtime.")
sprawdz("paczka na poczatku zdania tez", _ok2, _po2)

print()
print("=== 2. WZMIANKA O OSOBIE NADAL BLOKUJE ===")
for opis, t in (("po spacji", "A post by @simonw said so."),
                ("na poczatku", "@simonw wrote about it."),
                ("PO UKOSNIKU — dziura sprzed poprawki",
                 "See github.com/@simonw for details."),
                ("po sciezce — ta sama dziura",
                 "path/@simonw is the handle."),
                ("podwojna malpa", "Contact @@simonw now."),
                ("w nawiasie", "(see @simonw) for details.")):
    _o, _p = przechodzi(t)
    sprawdz("blokuje wzmianke %s" % opis, not _o, _p)

print()
print("=== 3. PROBA PRZEMYCENIA PRZEZ KSZTALT PACZKI ===")
# Zdjecie malpy z „@ab/" zostawia „/@simonw" — i wlasnie dlatego granica
# musi obejmowac ukosnik. Bez tego moja wlasna poprawka bylaby furtka.
for t in ("Look at @ab/@simonw for details.",
          "Look at @a/@simonw for details.",
          "Try @scope/@victim now."):
    _o, _p = przechodzi(t)
    sprawdz("nie da sie przemycic przez %r" % t[8:22], not _o, _p)

print()
print("=== 4. CZEGO ZAPORA NIE MA RUSZAC ===")
for opis, t in (("adres pocztowy", "Write to press@example.com for details."),
                ("cena z malpa", "Sold 5 units @2 dollars each."),
                ("malpa w srodku slowa", "The handle x@y is not a mention."),
                ("zwykly tekst", "OpenAI cut the cached input price by half.")):
    _o, _p = przechodzi(t)
    sprawdz("przepuszcza %s" % opis, _o, _p)

print()
print("=== 5. NORMALIZACJA IDZIE PRZED BRAMKA I PRZED ZAPISEM ===")
# Gdyby poprawiana byla tylko kopia do sprawdzenia, fakt przeszedlby bramke,
# a do pisarza i tak trafilaby malpa.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("dopisz_kandydatow normalizuje pola kandydata",
        "k[_pole] = bez_malpy_w_nazwie_paczki(str(k[_pole]))" in _zr)
sprawdz("granica zapory to caly niealfanumeryczny znak",
        r'(^|\W)@[A-Za-z0-9_]{2,}' in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
