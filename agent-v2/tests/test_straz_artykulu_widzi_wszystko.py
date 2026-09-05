# -*- coding: utf-8 -*-
"""Straz powtorek artykulu widzi wszystkie artykuly, nie piec ostatnich.

CO ZGLASZA AUDYT (Q11). `tematy_do_porownania(conn, limit=DIVERSITY_LOOKBACK)`
zasila `niepowtorzony` w `pick_topic` i `wybierz_fakt`. Przy jednym artykule na
tydzien piec znaczy PIEC TYGODNI — szosty wstecz nie istnieje dla kodu, choc
skaut dostaje wszystkie tytuly z `promocja.json`.

Audyt zastrzega: „ponizej szesciu sprawa jest uspiona".

CO ZMIERZYLEM NA PRODUKCJI: artykulow jest PIETNASCIE, wiec sprawa nie jest
uspiona — DZIESIEC bylo niewidocznych. A wsrod tych piatki widocznych stoja
obok siebie:

    „The Guardrails Were Off on Purpose"
    „The Guardrails Were Off Because That Was the Test"

czyli okno bylo za male nawet na to, co obejmowalo.

CENA JEST ZNIKOMA i to jest cala trudnosc tej decyzji — nie ma jej. Tabela
rosnie o wiersz TYGODNIOWO, porownanie bierze 1200 znakow tresci na artykul,
a caly odczyt dzieje sie raz na przebieg artykulu, czyli raz na tydzien.

CZEGO TO NIE RUSZA. `DIVERSITY_LOOKBACK` zostaje przy `db.recent_domains`
i przy historii dla skauta — tam piec ma inne znaczenie. Zmiana dotyczy
wylacznie okna porownania tematow.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_straz_artykulu_widzi_wszystko.py
"""
import pathlib
import sqlite3
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


def baza(ile):
    """Baza z `ile` artykulami, kazdy o czym innym."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY,"
                 " topic TEXT, title TEXT, body TEXT)")
    for i in range(ile):
        conn.execute(
            "INSERT INTO articles (topic, title, body) VALUES (?,?,?)",
            ("temat numer %d" % i, "Tytul %d" % i,
             "Tresc artykulu numer %d o instytucji Urzad%d i liczbie %d000."
             % (i, i, i)))
    conn.commit()
    return conn


print("=== 1. PELNA HISTORIA, NIE PIEC OSTATNICH ===")
conn = baza(15)   # tyle, ile mial serwer w dniu pomiaru
wszystkie = stages.tematy_do_porownania(conn)
sprawdz("pietnascie artykulow daje pietnascie pozycji",
        len(wszystkie) == 15, len(wszystkie))
sprawdz("NAJSTARSZY tez jest widoczny",
        any("numer 0" in t for t in wszystkie),
        [t[:30] for t in wszystkie[-2:]])
sprawdz("i ten sprzed piatki — czyli szosty wstecz",
        any("numer 9" in t for t in wszystkie))

print()
print("=== 2. WASKIE OKNO NADAL DA SIE POPROSIC ===")
# Sygnatura zostaje, bo testy i narzedzia moga chciec waskiego okna.
piec = stages.tematy_do_porownania(conn, limit=5)
sprawdz("limit=5 oddaje piec", len(piec) == 5, len(piec))
# TAUTOLOGIA USUNIETA. Stalo tu `all(...) or len(piec) == 5` — drugi czlon
# byl juz sprawdzony wierszy wyzej, wiec caly warunek byl zawsze prawdziwy
# i asercja nie badala niczego.
sprawdz("i sa to piec NAJNOWSZYCH, czyli 10-14",
        [t.split("numer ")[1].split()[0] for t in piec]
        == ["14", "13", "12", "11", "10"],
        [t[:24] for t in piec])

print()
print("=== 3. PORZADEK OD NAJNOWSZEGO ===")
# `niepowtorzony` porownuje po kolei; najswiezsze musi byc pierwsze, inaczej
# przy dlugiej historii najwazniejsze porownanie robi sie na koncu.
sprawdz("pierwszy element to najnowszy artykul",
        "numer 14" in wszystkie[0], wszystkie[0][:40])
sprawdz("ostatni to najstarszy", "numer 0" in wszystkie[-1], wszystkie[-1][:40])

print()
print("=== 4. PUSTA BAZA NIE WYWALA ===")
sprawdz("zero artykulow -> pusta lista",
        stages.tematy_do_porownania(baza(0)) == [])
_zla = sqlite3.connect(":memory:")
sprawdz("brak tabeli tez nie wywala",
        stages.tematy_do_porownania(_zla) == [])

print()
print("=== 5. OBA WYWOLANIA PRODUKCYJNE BIORA PELNA HISTORIE ===")
# Gdyby ktores podawalo limit, zmiana nie mialaby zadnego skutku.
for plik in ("agent-v2/run.py", "agent-v2/artykul_z_puli.py"):
    zr = pathlib.Path(plik).read_text(encoding="utf-8")
    kod = chr(10).join(w for w in zr.splitlines()
                       if not w.lstrip().startswith("#"))
    wolania = [w for w in kod.split("tematy_do_porownania(")[1:]]
    sprawdz("%s wola bez limitu" % plik.split("/")[-1],
            all(w.lstrip().startswith("conn)") for w in wolania),
            [w[:26] for w in wolania])

print()
print("=== 6. TRESC WCHODZI DO POROWNANIA, NIE SAM TYTUL ===")
# Tytul jest metafora — „Convicted by Deadline" nie dzieli ani jednego slowa
# z „automated debt recovery". Bez tresci szersze okno nic by nie dalo.
sprawdz("pozycja niesie tresc artykulu",
        any("instytucji" in t for t in wszystkie), wszystkie[0][:60])
sprawdz("i temat", any("temat numer" in t for t in wszystkie))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
