# -*- coding: utf-8 -*-
"""Karta wynikow liczy oba konta TAK SAMO — i tylko czyta.

Po co: od 26 wrzesnia 2026 Nothing Is Accidental jest poligonem, a NIA kontem
produkcyjnym. Wniosek „na poligonie zadzialalo" ma sens tylko wtedy, gdy oba
konta mierzy ten sam przyrzad z tymi samymi definicjami. Kazda definicja
z naglowka `karta_wynikow.py` ma tu swoj przypadek i kontrdowod:

  * reakcja wlasnego konta (drugiego bota) nie jest odzewem;
  * komentarz mlodszy niz 48 h jeszcze sie nie liczy;
  * „nowy reagujacy" to pierwszy raz w historii, nie pierwszy raz w tygodniu;
  * zasieg bierze pomiar najblizszy 72 h i pomija wpisy niedojrzale;
  * koszt to tylko przebiegi produkcyjne.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_karta_wynikow.py
"""
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import karta_wynikow as kw  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


OD, DO = date(2026, 9, 19), date(2026, 9, 25)
WLASNE = {"nothingisaccidental", "nia1503032"}


def zapisz_jsonl(sciezka, wpisy):
    sciezka.write_text("".join(json.dumps(w) + "\n" for w in wpisy), encoding="utf-8")


def konto(katalog: pathlib.Path) -> pathlib.Path:
    katalog.mkdir(parents=True)
    zapisz_jsonl(katalog / "wzrost.jsonl", [
        {"kiedy": "2026-09-18T20:00:00+00:00", "subskrybenci": 20, "obserwujacy": 30},
        {"kiedy": "2026-09-25T20:00:00+00:00", "subskrybenci": 23, "obserwujacy": 34},
        {"kiedy": "2026-09-26T08:00:00+00:00", "subskrybenci": 99, "obserwujacy": 99},
    ])
    zapisz_jsonl(katalog / "dziennik.jsonl", [
        # komentarze: dwa dojrzale, jeden za mlody (25.09, mniej niz 48 h)
        {"kiedy": "2026-09-20T10:00:00+00:00", "rodzaj": "komentarz", "udane": True,
         "nasz_id": 1, "skad": "kanal", "wiek_celu_min": 100},
        {"kiedy": "2026-09-21T10:00:00+00:00", "rodzaj": "komentarz", "udane": True,
         "nasz_id": 2, "skad": "szukanie: ai", "wiek_celu_min": 60000},
        {"kiedy": "2026-09-25T10:00:00+00:00", "rodzaj": "komentarz", "udane": True,
         "nasz_id": 3, "skad": "kanal", "wiek_celu_min": 50},
        {"kiedy": "2026-09-22T10:00:00+00:00", "rodzaj": "komentarz", "udane": False,
         "nasz_id": 4},
        {"kiedy": "2026-09-22T11:00:00+00:00", "rodzaj": "notka", "udane": True, "id": "500"},
        {"kiedy": "2026-09-22T12:00:00+00:00", "rodzaj": "restack", "udane": True, "id": "600"},
        {"kiedy": "2026-09-10T12:00:00+00:00", "rodzaj": "notka", "udane": True, "id": "700"},
        # reakcje: na komentarz 1 odpowiada czlowiek, na 2 TYLKO drugi bot
        {"kiedy": "2026-09-21T09:00:00+00:00", "rodzaj": "skutek", "udane": True,
         "czego": 1, "uchwyty": ["czytelnik"], "kiedy_zdarzenia": "2026-09-21T08:00:00"},
        {"kiedy": "2026-09-22T09:00:00+00:00", "rodzaj": "skutek", "udane": True,
         "czego": 2, "uchwyty": ["nia1503032"], "kiedy_zdarzenia": "2026-09-22T08:00:00"},
        # stary znajomy: reagowal juz 1 wrzesnia, wiec w tym tygodniu NIE jest nowy
        {"kiedy": "2026-09-01T09:00:00+00:00", "rodzaj": "skutek", "udane": True,
         "czego": 700, "uchwyty": ["staryznajomy"], "kiedy_zdarzenia": "2026-09-01T08:00:00"},
        {"kiedy": "2026-09-23T09:00:00+00:00", "rodzaj": "skutek", "udane": True,
         "czego": 500, "uchwyty": ["staryznajomy", "nowa_osoba"],
         "kiedy_zdarzenia": "2026-09-23T08:00:00"},
    ])
    zapisz_jsonl(katalog / "statystyki.jsonl", [
        # notka 500 wystawiona 19.09 (okno zasiegu to 16-22.09, bo musi dojrzec):
        # pomiary po 24, 70 i 100 h — liczy sie ten po 70 h
        {"rodzaj": "notka", "id": "500", "wyswietlenia": 5,
         "wystawione": "2026-09-19T11:00:00Z", "zmierzone": "2026-09-20T11:00:00Z"},
        {"rodzaj": "notka", "id": "500", "wyswietlenia": 21, "odwiedziny_profilu": 2,
         "wystawione": "2026-09-19T11:00:00Z", "zmierzone": "2026-09-22T09:00:00Z"},
        {"rodzaj": "notka", "id": "500", "wyswietlenia": 30,
         "wystawione": "2026-09-19T11:00:00Z", "zmierzone": "2026-09-23T15:00:00Z"},
        # restack 600 zapisany w statystykach jako notka
        {"rodzaj": "notka", "id": "600", "wyswietlenia": 40,
         "wystawione": "2026-09-20T12:00:00Z", "zmierzone": "2026-09-23T12:00:00Z"},
        # notka 800: zmierzona tylko po 24 h — niedojrzala, nie wchodzi
        {"rodzaj": "notka", "id": "800", "wyswietlenia": 3,
         "wystawione": "2026-09-21T12:00:00Z", "zmierzone": "2026-09-22T12:00:00Z"},
    ])
    zapisz_jsonl(katalog / "zrodla.jsonl", [
        {"podsumowanie": {"zapisy_per_notka": {"600": 1}},
         "zapisy": {"totals": [{"name": "subscribers", "total": 5}]}},
        {"podsumowanie": {"zapisy_per_notka": {"600": 3, "999": 1}},
         "zapisy": {"totals": [{"name": "subscribers", "total": 7}]}},
    ])
    baza = sqlite3.connect(katalog / "agent-v2.db")
    baza.executescript(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY, started_at TEXT, status TEXT, tryb TEXT);"
        "CREATE TABLE calls (id INTEGER PRIMARY KEY, run_id INTEGER, at TEXT,"
        " purpose TEXT, cost_usd REAL);"
        "INSERT INTO runs VALUES (1, '2026-09-20T11:00:00', 'DONE', 'produkcja');"
        "INSERT INTO runs VALUES (2, '2026-09-21T11:00:00', 'DONE', 'test');"
        "INSERT INTO runs VALUES (3, '2026-09-22T11:00:00', 'FAILED', 'produkcja');"
        "INSERT INTO calls VALUES (1, 1, '2026-09-20T11:01:00', 'note', 0.50);"
        "INSERT INTO calls VALUES (2, 1, '2026-09-20T11:02:00', 'comment', 0.20);"
        "INSERT INTO calls VALUES (3, 2, '2026-09-21T11:01:00', 'note', 9.00);"
        "INSERT INTO calls VALUES (4, 3, '2026-09-22T11:01:00', 'factcheck', 0.00);"
        "INSERT INTO calls VALUES (5, 1, '2026-09-26T11:01:00', 'note', 5.00);")
    baza.commit()
    baza.close()
    return katalog


def odcisk(katalog):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(katalog.iterdir())}


KAT = pathlib.Path(tempfile.mkdtemp(prefix="karta-"))
A = konto(KAT / "poligon")
PRZED = odcisk(A)

k = kw.karta("Poligon", A, OD, DO, WLASNE)

print("=== 1. WZROST ===")
sprawdz("stan na koniec okna, nie z dzisiaj", k["wzrost"]["subskrybenci"] == 23, k["wzrost"])
sprawdz("zmiana wobec konca doby przed oknem", k["wzrost"]["przyrost_subskrybenci"] == 3)
sprawdz("obserwujacy tez", k["wzrost"]["przyrost_obserwujacy"] == 4)

print()
print("=== 2. DZIALANIA ===")
sprawdz("liczy tylko udane", k["dzialania"].get("komentarz") == 3, k["dzialania"])
sprawdz("notka sprzed okna sie nie liczy", k["dzialania"].get("notka") == 1)
sprawdz("zdarzenia `skutek` to nie nasze dzialania", "skutek" not in k["dzialania"])

print()
print("=== 3. ODZEW KOMENTARZY ===")
kom = k["komentarze"]
sprawdz("komentarz mlodszy niz 48 h jeszcze sie nie liczy", kom["komentarzy"] == 2, kom)
sprawdz("reakcja drugiego bota nie jest odzewem", kom["z_odzewem"] == 1, kom)
sprawdz("odzew 50%", kom["odzew_proc"] == 50)
sprawdz("udzial wyszukiwarki i starych celow", kom["z_wyszukiwarki_proc"] == 50
        and kom["cele_starsze_niz_30_dni_proc"] == 50, kom)
kontr = kw.odzew_komentarzy(kw._jsonl(A / "dziennik.jsonl"), OD, DO, set())
sprawdz("KONTRDOWOD: bez wykluczenia drugi bot zawyza odzew do 100%",
        kontr["odzew_proc"] == 100, kontr)

print()
print("=== 4. NOWI REAGUJACY ===")
sprawdz("pierwszy raz w historii, nie w tygodniu: 2 (czytelnik, nowa_osoba)",
        k["nowi_reagujacy"] == 2, k["nowi_reagujacy"])

print()
print("=== 5. ZASIEG PO 72 H ===")
z = k["zasieg_72h"]
sprawdz("notka: pomiar najblizszy 72 h (70 h), nie ostatni", z["notka"]["mediana"] == 21, z)
sprawdz("notka niedojrzala (tylko 24 h) nie wchodzi", z["notka"]["n"] == 1, z)
sprawdz("restack rozpoznany po dzienniku, choc zapisany jako notka",
        z["restack"]["n"] == 1 and z["restack"]["mediana"] == 40, z)
sprawdz("odwiedziny profilu z tego samego pomiaru", z["notka"]["odwiedziny_profilu_na_szt"] == 2.0)

print()
print("=== 6. ZAPISY ===")
za = k["zapisy"]
sprawdz("okno 30 dni z ostatniego odczytu", za["zapisy_30_dni"] == 7, za)
sprawdz("przypisanie: maksimum na tresc ze wszystkich odczytow",
        za["przypisane_tresciom"] == {"restack": 3, "poza dziennikiem": 1}, za)

print()
print("=== 7. KOSZT ===")
ko = k["koszt"]
sprawdz("tylko przebiegi produkcyjne i tylko w oknie", ko["usd"] == 0.70, ko)
sprawdz("na dobe", ko["usd_na_dobe"] == 0.1, ko)
sprawdz("przebiegi produkcyjne wg statusu", ko["przebiegi"] == {"DONE": 1, "FAILED": 1}, ko)

print()
print("=== 8. TYLKO ODCZYT ===")
sprawdz("zadny plik konta nie zmienil sie ani o bajt", odcisk(A) == PRZED)

print()
print("=== 9. WYDRUK I ZAPIS NA ZADANIE ===")
B = konto(KAT / "produkcja")
DWA_KONTA = (("Poligon", A, "nothingisaccidental"), ("Produkcja", B, "nia1503032"))
ZAPIS = KAT / "zapis"
stare = config.uzyj_katalogu_danych(ZAPIS)
try:
    sprawdz("domyslna lista kont idzie za przestawionym katalogiem danych",
            kw.konta()[0][1] == config.DATA_DIR, kw.konta()[0][1])
    bufor = io.StringIO()
    with redirect_stdout(bufor):
        kw.main(["--do", "2026-09-25"], lista_kont=DWA_KONTA)
    wydruk = bufor.getvalue()
    sprawdz("wydruk ma oba konta obok siebie",
            "Poligon" in wydruk and "Produkcja" in wydruk, wydruk[:200])
    sprawdz("bez --zapisz nic nie powstaje", not (ZAPIS / "karta_wynikow.jsonl").exists())
    with redirect_stdout(io.StringIO()):
        kw.main(["--do", "2026-09-25", "--zapisz"], lista_kont=DWA_KONTA)
    linie = (ZAPIS / "karta_wynikow.jsonl").read_text(encoding="utf-8").splitlines()
    sprawdz("--zapisz dopisuje po jednej linii na konto", len(linie) == 2, len(linie))
finally:
    config.przywroc_katalog_danych(stare)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
