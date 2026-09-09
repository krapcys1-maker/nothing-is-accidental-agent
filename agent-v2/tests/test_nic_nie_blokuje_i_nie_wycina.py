# -*- coding: utf-8 -*-
"""Tekst wychodzi taki, jaki napisal model. Sprawdzenia sa LOGIEM.

DECYZJA WLASCICIELA z 9 wrzesnia 2026, powtorzona dwa razy tego samego dnia:

    „ma dzialac za wszelka cene, zadnego blokowania notek komentarzy
     restackow czy artykulow, masz usunac wszelkie blokady"
    „nic nie ma wycinac"

HISTORIA TEGO MIEJSCA W JEDEN DZIEN, bo warto ja miec zapisana:

    bramka      tekst do kosza w calosci. Notka o osiem slow ponad sufit
                skonczyla caly przebieg 11:21 cisza; zapora wstrzykniecia
                zabrala szesc notek w 30 dni.
    nozyczki    wycinalismy wadliwy fragment i publikowali reszte.
                Odrzucone: „nic nie ma wycinac".
    log         to, co jest teraz.

CO ZOSTALO ZDJETE — kazde z tych miejsc konczylo publikacje:

    notka       dlugosc poza oknem (dwie bramki: `note` i `run.py`)
    notka       zapora wstrzykniecia
    odpowiedz   zapora wstrzykniecia
    odpowiedz   zmyslone przezycie, nienazwane badanie
    komentarz   zapora wstrzykniecia
    komentarz   te same dwie podlogi z pamieci
    naprawa     poprawka faktu odrzucana za dlugosc
    artykul     rezygnacja po 12 nieudanych probach wystawienia

CO ZOSTALO BRAMKA — jedna rzecz, bo nie ma czego wystawic: PUSTY TEKST.

CZEGO TEN TEST PILNUJE — ze zadne z tych miejsc nie wrocilo. Pilnuje SKUTKU
(tekst wychodzi) i BRAKU STAREGO KSZTALTU (nie ma `continue` ani wycinania).

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_nic_nie_blokuje_i_nie_wycina.py
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


ZA_DLUGA = " ".join(["word"] * 128)


def napisz(tekst):
    """Pelne `stages.note` z podstawionym modelem. Oddaje kandydatow."""
    oryginal = llm.call

    def podstawiony(purpose, system, prompt, **kw):
        if purpose == "note":
            return json.dumps({"note": tekst, "words": len(tekst.split()),
                               "fact_used": "x",
                               "source_url": "https://e.invalid/a"})
        return json.dumps({})

    llm.call = podstawiony
    try:
        wynik = stages.note(AtrapaConn(), 1, "CIEKAWOSTKA",
                            {"fact": "x", "url": "https://e.invalid/a"})
    except Exception as e:                                    # noqa: BLE001
        print("     (pisanie przerwane: %s)" % e)
        wynik = None
    finally:
        llm.call = oryginal
    return (wynik or {}).get("candidates") or []


print("=== 1. notka poza oknem WYCHODZI i nie jest ruszana ===")
kand = napisz(ZA_DLUGA)
sprawdz("kandydat istnieje", len(kand) == 1, "kandydatow: %d" % len(kand))
sprawdz("tekst nietkniety — dokladnie to, co napisal model",
        kand and (kand[0].get("note") or "").strip() == ZA_DLUGA)
sprawdz("128 slow zostalo 128", kand and kand[0].get("words_actual") == 128,
        str(kand[0].get("words_actual")) if kand else "brak")
sprawdz("oznaczona jako poza oknem, ale to tylko pomiar",
        kand and kand[0].get("length_ok") is False)
sprawdz("i doszla do sprawdzenia faktow", kand and "weryfikacja" in kand[0])

print()
print("=== 2. pusty tekst to jedyna bramka ===")
kand = napisz("")
sprawdz("pusta notka nie idzie",
        not [k for k in kand if (k.get("note") or "").strip()])

print()
print("=== 3. stare ksztalty nie wrocily do kodu ===")
_st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")

for opis, wzor, gdzie in (
    ("notka nie odpada na dlugosci w `note`",
     'if not text or not data.get("length_ok"):', _st),
    ("notka nie odpada na dlugosci w `run.py`",
     'k.get("safe_to_post") and k.get("length_ok")', _run),
    ("notka nie odpada na zaporze wstrzykniecia",
     'print("    ODRZUCONA PRZED SPRAWDZENIEM: %s"', _st),
    ("odpowiedz nie odpada na zaporze wstrzykniecia",
     'print(f"  [odpowiedź {i + 1}] ODRZUCONA: {powod}"', _st),
    ("odpowiedz nie odpada na podlodze z pamieci",
     'print(f"    ODRZUCONA PRZED WYSLANIEM: {nazwa}"', _st),
    ("komentarz nie odpada na zaporze wstrzykniecia",
     'print(f"    ODRZUCONY PRZED SPRAWDZENIEM: {powod}"', _st),
    ("komentarz nie odpada na podlodze z pamieci",
     'print(f"    ODRZUCONY PRZED SPRAWDZENIEM: {podloga}"', _st),
    ("poprawka faktu nie odpada na dlugosci",
     '[naprawa] ODRZUCONA: %d slow', _st),
    ("artykul nie rezygnuje po suficie prob", 'PRZESTAJE" " PROBOWAC', _run),
):
    sprawdz(opis, wzor not in gdzie)

sprawdz("i nie ma juz wycinania wady z tekstu",
        "przepisz_bez_wady" not in _st and "dopasuj_dlugosc" not in _st)
sprawdz("zalegly artykul probuje dalej", "PROBUJE DALEJ" in _run)

print()
print("=== 4. sprawdzenia nadal ZAPISUJA, co zobaczyly ===")
# Zdjecie bramki nie ma znaczyc zdjecia pomiaru: bez zapisu nie da sie
# policzyc, jak czesto zapora by zadzialala, a to jedyny sposob, zeby
# zauwazyc, gdyby cos zaczelo wychodzic masowo.
for opis, wzor in (
    ("notka zapisuje werdykt zapory wstrzykniecia", 'data["czysty"] = czysty'),
    ("odpowiedz zapisuje", 'data["zapora_wstrzykniecia"] = powod'),
    ("komentarz zapisuje podloge", 'data["podloga"] = podloga'),
    ("notka zapisuje wynik pomiaru dlugosci", 'data["length_ok"] = in_range'),
):
    sprawdz(opis, wzor in _st)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
