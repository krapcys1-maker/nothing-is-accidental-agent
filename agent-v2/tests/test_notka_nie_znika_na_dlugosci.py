# -*- coding: utf-8 -*-
"""Notka za dluga jest SKRACANA, a nie wyrzucana.

POLECENIE WLASCICIELA z 9 wrzesnia 2026, po przebiegu 11:21, ktory nie wystawil
niczego: „nie ma takiej mozliwosci, ze cos nie idzie, jest odrzucone i juz".

CO SIE STALO. Notka miala 128 slow przy suficie 120 dla formy SCENA. Zniknela
bez sladu poza jedna linijka „POZA" w dzienniku, a caly przebieg zamknal sie
jako udany z zerem notek.

DLACZEGO TO BYLO GORSZE, NIZ WYGLADALO. Tuz nad tym miejscem stal komentarz
„POMIAR, NIE BRAMKA" — a dlugosc byla bramka w DWOCH miejscach naraz:

    stages.note   `if not text or not data.get("length_ok"): continue`
                  — kandydat wypadal PRZED sprawdzeniem faktow, wiec nie
                    dostawal nawet `safe_to_post`
    run.py        `if k.get("safe_to_post") and k.get("length_ok")`
                  — i drugi raz przy wysylce

`NOTE_CANDIDATES = 1`, wiec kazde z tych miejsc samo wystarczalo, zeby dzien
skonczyl sie cisza. Komentarz opisywal zamiar, kod robil co innego, a rozjazdu
nie bylo widac, bo notka znikala bez sladu.

CO JEST TERAZ. Trzecia droga, ta sama co przy sprawdzaniu faktow: ani bramka,
ani milczenie, tylko poprawka. `stages.dopasuj_dlugosc` skraca notke do okna
jednym tanim wywolaniem; gdy sie nie uda — notka wychodzi za dluga, a log to
mowi. Osiem slow ponad sufit kosztuje mniej niz dzien bez notki.

CZEGO TEN TEST PILNUJE — wylacznie skutkow:

  1. notka poza oknem trafia do dopasowania, a nie do kosza
  2. po dopasowaniu wychodzi i jest oznaczona jako mieszczaca sie
  3. gdy dopasowanie ZAWIEDZIE, notka i tak wychodzi
  4. gdy dopasowanie odda tekst DALEJ poza oknem, zostaje oryginal
     (poprawka gorsza od oryginalu nie ma prawa go zastapic)
  5. pusty tekst nadal nie wychodzi — to jedyna bramka, jaka zostaje
  6. `run.py` nie odsiewa juz po dlugosci
  7. pusty budzet i wylacznik leca z dopasowania na wylot

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_notka_nie_znika_na_dlugosci.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm      # noqa: E402
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


class AtrapaConn:
    def __getattr__(self, nazwa):
        raise AssertionError("kod siega po conn.%s — atrapa tego nie ma" % nazwa)


DLUGA = " ".join(["word"] * 128)
KROTKA = " ".join(["word"] * 100)

print("=== 1. sama funkcja dopasowania ===")


def dopasuj(odpowiedz, tekst=DLUGA, conn=AtrapaConn(), wyjatek=None):
    wolania = []
    oryginal = llm.call

    def podstawiony(purpose, system, prompt, **kw):
        wolania.append(purpose)
        if wyjatek:
            raise wyjatek("proba")
        return json.dumps(odpowiedz)

    llm.call = podstawiony
    try:
        return stages.dopasuj_dlugosc(conn, 1, tekst, min_slow=33,
                                      max_slow=120), wolania
    finally:
        llm.call = oryginal


wynik, wolania = dopasuj({"text": KROTKA, "co_zmienione": "wycialem dygresje"})
sprawdz("za dluga notka zostaje skrocona",
        wynik and wynik["slow"] == 100, "wynik=%r" % wynik)
sprawdz("i kosztowala jedno wywolanie", wolania == ["dlugosc"],
        "wolania=%r" % wolania)

wynik, wolania = dopasuj({"text": KROTKA}, tekst=KROTKA)
sprawdz("notka W OKNIE nie jest ruszana ani placona",
        wynik is None and wolania == [], "wynik=%r wolania=%r" % (wynik, wolania))

wynik, _ = dopasuj({"text": " ".join(["word"] * 140)})
sprawdz("poprawka DALEJ poza oknem jest odrzucana, zostaje oryginal",
        wynik is None, "wynik=%r" % wynik)

wynik, _ = dopasuj({"text": ""})
sprawdz("pusta poprawka nie zastepuje oryginalu", wynik is None)

wynik, _ = dopasuj({}, wyjatek=RuntimeError)
sprawdz("blad wywolania zostawia oryginal", wynik is None)

sprawdz("bez conn nie ma kogo pytac",
        stages.dopasuj_dlugosc(None, None, DLUGA,
                               min_slow=33, max_slow=120) is None)

print()
print("=== 2. pusty budzet i wylacznik leca na wylot ===")
for _klasa, _opis in ((llm.BudgetExceeded, "pusty budzet"),
                      (llm.PreflightFailed, "wylacznik")):
    try:
        dopasuj({}, wyjatek=_klasa)
        _co = "POLKNIETE"
    except _klasa:
        _co = "leci dalej"
    except Exception as _e:                                   # noqa: BLE001
        _co = "inny wyjatek: %s" % type(_e).__name__
    sprawdz("%s leci z dopasowania na wylot" % _opis, _co == "leci dalej",
            "dopasowanie zrobilo: %s" % _co)

print()
print("=== 3. notka za dluga PRZECHODZI przez cale pisanie ===")


def napisz(odpowiedzi, wyjatek_na=()):
    """Pelne `stages.note` z podstawionymi odpowiedziami modelu."""
    etapy = []
    oryginal = llm.call

    def podstawiony(purpose, system, prompt, **kw):
        etapy.append(purpose)
        if purpose in wyjatek_na:
            raise RuntimeError("zerwane")
        return json.dumps(odpowiedzi.get(purpose, {}))

    llm.call = podstawiony
    try:
        wynik = stages.note(AtrapaConn(), 1, "CIEKAWOSTKA",
                            {"fact": "x", "url": "https://e.invalid/a"})
    except Exception as e:                                    # noqa: BLE001
        print("     (pisanie przerwane: %s)" % e)
        wynik = None
    finally:
        llm.call = oryginal
    return wynik, etapy


NOTKA_ZA_DLUGA = {"note": DLUGA, "words": 128, "fact_used": "x",
                  "source_url": "https://e.invalid/a"}

wynik, etapy = napisz({"note": NOTKA_ZA_DLUGA,
                       "dlugosc": {"text": KROTKA, "co_zmienione": "ciach"}})
kand = (wynik or {}).get("candidates") or []
sprawdz("dopasowanie zostalo wywolane", "dlugosc" in etapy, "etapy=%r" % etapy)
sprawdz("kandydat istnieje, a nie zniknal", len(kand) == 1,
        "kandydatow: %d" % len(kand))
sprawdz("po skroceniu miesci sie w oknie",
        kand and kand[0].get("length_ok") is True,
        "length_ok=%r" % (kand[0].get("length_ok") if kand else None))
sprawdz("oryginal zachowany, zeby dalo sie porownac",
        kand and kand[0].get("tekst_przed_dlugoscia"))

print()
print("=== 4. gdy dopasowanie zawiedzie, notka I TAK wychodzi ===")
wynik, etapy = napisz({"note": NOTKA_ZA_DLUGA}, wyjatek_na=("dlugosc",))
kand = (wynik or {}).get("candidates") or []
sprawdz("kandydat nadal istnieje", len(kand) == 1,
        "kandydatow: %d" % len(kand))
sprawdz("oznaczony jako poza oknem, ale nie usuniety",
        kand and kand[0].get("length_ok") is False)
sprawdz("i doszedl do sprawdzenia faktow, czyli nie wypadl wczesniej",
        "factcheck" in etapy, "etapy=%r" % etapy)

print()
print("=== 4b. poprawka faktyczna tez jest skracana, a nie wyrzucana ===")
# Zmierzone platna proba 9 wrzesnia: sprawdzanie faktow obalilo twierdzenie,
# naprawa je przepisala i wyszla na 135 slow przy suficie 120 — po czym
# zostala WYRZUCONA. Obalone twierdzenie zostalo w notce, ktora poszla
# w swiat. To gorsze niz notka o pietnascie slow za dluga: czytelnik dostaje
# nieprawde, ktora sami wykrylismy i sami naprawilismy.
_st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
_i = _st.find("[naprawa] ODRZUCONA")
_przed = _st[max(0, _i - 1200):_i]
sprawdz("naprawa siega po skracanie, zanim odrzuci",
        "dopasuj_dlugosc(conn, run_id, nowy" in _przed,
        "poprawka faktyczna nadal ginie na liczniku slow")
sprawdz("i odrzuca dopiero, gdy skracanie zawiedzie",
        "else:" in _przed.split("dopasuj_dlugosc")[-1])

print()
print("=== 5. pusty tekst to jedyna bramka, jaka zostaje ===")
wynik, _ = napisz({"note": {"note": "", "words": 0}})
kand = [k for k in ((wynik or {}).get("candidates") or [])
        if (k.get("note") or "").strip()]
sprawdz("pusta notka nie idzie", kand == [], "kandydaci=%r" % kand)

print()
print("=== 6. run.py nie odsiewa juz po dlugosci ===")
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("filtr wysylki patrzy tylko na `safe_to_post`",
        'gotowe = [k for k in n["candidates"] if k.get("safe_to_post")]' in _run)
sprawdz("i nie ma juz drugiego warunku o dlugosci",
        'k.get("safe_to_post") and k.get("length_ok")' not in _run)
_st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("pisanie tez nie pomija kandydata za dlugiego",
        'if not text or not data.get("length_ok"):' not in _st)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
