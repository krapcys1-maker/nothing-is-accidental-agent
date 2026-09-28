# -*- coding: utf-8 -*-
"""Komentarz bez sprawdzania faktow — decyzja wlasciciela 28.09.2026.

Sprawdzamy notki i artykuly, komentarzy nie (`config.SPRAWDZANIE_FAKTOW_KOMENTARZY`).
Zmierzone na 7 dniach (kolumna `calls.akcja`): komentarze to 100 ze 124 sprawdzen
i 0,40 z 0,55 USD tygodniowo, a przez 4 tygodnie sprawdzanie obalalo drobiazgi
(nazwa instytutu, cena, szczegol specyfikacji). Wlasciciel: „niech tak bedzie".

Test pilnuje:
  1. domyslnie WYLACZONE: komentarz nie wola `zweryfikuj` ani `napraw_obalone`,
     nie ma zadnego wywolania `factcheck`, a zapis mowi JAWNIE `nie_sprawdzone`;
  2. zapory PRZED sprawdzaniem dzialaja dalej (zmyslone przezycie zostaje w zapisie);
  3. KONTRDOWOD: po wlaczeniu flagi `zweryfikuj` i naprawa sa wolane jak dawniej.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_komentarz_bez_sprawdzania_faktow.py
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


wolane: list[str] = []
weryfikacje: list[int] = []
naprawy: list[int] = []


def atrapa_call(purpose, system, user, **k):
    wolane.append(purpose)
    if purpose == "comment":
        return json.dumps({"comment": "I asked three people about this rollout and all of them "
                                      "said the 2024 deadline was set before the pilot ended.",
                           "what_it_adds": "timeline"})
    raise AssertionError("nieoczekiwane platne wywolanie: %s" % purpose)


stages.llm.call = atrapa_call
stages.zweryfikuj = lambda *a, **k: weryfikacje.append(1) or {"safe_to_post": True, "verdict": "ok"}
stages.napraw_obalone = lambda *a, **k: naprawy.append(1) or None
POST = {"title": "Rollout", "text": "Cudzy tekst o wdrozeniu.", "url": "https://example.org/p/a"}


def komentarz():
    with contextlib.redirect_stdout(io.StringIO()):
        return stages.comment_on(object(), 1, POST)


print("=== 1. DOMYSLNIE: KOMENTARZ BEZ SPRAWDZANIA FAKTOW ===")
sprawdz("flaga domyslnie wylaczona", config.SPRAWDZANIE_FAKTOW_KOMENTARZY is False)
wynik = komentarz()
gotowe = [c for c in wynik["candidates"] if c.get("safe_to_post")]
sprawdz("jest kandydat do wystawienia", len(gotowe) == 1, len(gotowe))
sprawdz("`zweryfikuj` nie wolane", weryfikacje == [], weryfikacje)
sprawdz("`napraw_obalone` nie wolane", naprawy == [], naprawy)
sprawdz("zadnego wywolania factcheck — tylko pisanie komentarza",
        set(wolane) == {"comment"}, wolane)
sprawdz("zapis mowi JAWNIE: nie sprawdzone",
        (gotowe[0].get("weryfikacja") or {}).get("nie_sprawdzone") is True if gotowe else False,
        gotowe[0].get("weryfikacja") if gotowe else None)

print()
print("=== 2. ZAPORY PRZED SPRAWDZANIEM DZIALAJA DALEJ ===")
sprawdz("zmyslone przezycie (I asked three people) zapisane jako podloga",
        bool(gotowe and gotowe[0].get("podloga")), gotowe[0].get("podloga") if gotowe else None)

print()
print("=== 3. KONTRDOWOD: PO WLACZENIU FLAGI SPRAWDZANIE WRACA ===")
config.SPRAWDZANIE_FAKTOW_KOMENTARZY = True
wolane.clear()
try:
    wynik2 = komentarz()
finally:
    config.SPRAWDZANIE_FAKTOW_KOMENTARZY = False
sprawdz("`zweryfikuj` wolane", weryfikacje == [1], weryfikacje)
sprawdz("naprawa probowana (atrapa nic nie poprawia)", naprawy == [1], naprawy)
sprawdz("zapis ma werdykt sprawdzenia, nie `nie_sprawdzone`",
        not any((c.get("weryfikacja") or {}).get("nie_sprawdzone") for c in wynik2["candidates"]),
        [c.get("weryfikacja") for c in wynik2["candidates"]])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
