# -*- coding: utf-8 -*-
"""Kontrola zdrowia zamyka wiszacy przebieg, ale NIE zabiera mu nazwy etapu.

CO ZMIERZONO. Audyt wydatkow 3 wrzesnia 2026 znalazl w bazie 19 przebiegow
o etapie `kontrola`, WSZYSTKIE ze statusem STALE. Wygladalo to jak rodzaj
przebiegu, ktory nigdy nie konczy sie dobrze — i tak to opisalem w raporcie.
Bylo inaczej: `kontrola` to nie rodzaj przebiegu, tylko SLOWO, ktore kontrola
zdrowia wpisywala w pole `stage`, zamykajac wiersz wiszacy ponad trzy godziny.

    alarm.py:263   db.finish_run(conn, id, "STALE", "kontrola", "...")
    db.py:257      UPDATE runs SET ... stage = ? ...

Prawdziwa nazwa etapu byla nadpisywana w chwili zamykania. Wsrod tych 19
bylo SZESC przebiegow artykulowych, ktore zdazyly zaplacic po 0,80 USD za
pelny tekst i umarly przed publikacja — 4,49 USD, ktorego zaden raport nie
umial przypisac do artykulow, bo dowod byl zamazany.

Koszt tej wady nie byl w pieniadzach, a w slepocie: audyt nie umial
powiedziec, KTORY etap sie wiesza. To ta sama klasa, co pole `subskrypcje`
przy notce — liczba, ktora wyglada na odpowiedz, a jest sladem pomiaru.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_kontrola_nie_zamazuje_etapu.py
Zero wywolan modelu, zero sieci, produkcyjna baza nietknieta (`uzyj_katalogu_danych`).
"""
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


KAT = pathlib.Path(tempfile.mkdtemp())
_ZDJECIE = config.uzyj_katalogu_danych(KAT)
try:
    import db       # noqa: E402
    import alarm    # noqa: E402

    conn = db.connect()
    DAWNO = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

    def wiszacy(etap):
        """Wiersz w stanie RUNNING starszy niz prog kontroli zdrowia."""
        cur = conn.execute(
            "INSERT INTO runs (started_at, status, stage, tryb)"
            " VALUES (?, 'RUNNING', ?, 'test')", (DAWNO, etap))
        conn.commit()
        return cur.lastrowid

    def wiersz(rid):
        return dict(conn.execute(
            "SELECT status, stage, note FROM runs WHERE id = ?", (rid,)).fetchone())

    print("=== 1. ZAMKNIETY, ALE Z WLASNA NAZWA ETAPU ===")
    ida = {etap: wiszacy(etap) for etap in ("artykul", "dzien", "artykul-z-puli")}
    komunikat = alarm.zawieszone()
    sprawdz("kontrola zdrowia w ogole cos zglosila", bool(komunikat), komunikat)
    for etap, rid in sorted(ida.items()):
        w = wiersz(rid)
        sprawdz("`%s` -> status STALE" % etap, w["status"] == "STALE", w)
        sprawdz("`%s` -> etap NIETKNIETY" % etap, w["stage"] == etap, w["stage"])
    sprawdz("powod trafil do `note`, nie do `stage`",
            all("kontrole zdrowia" in (wiersz(r)["note"] or "")
                for r in ida.values()),
            [wiersz(r)["note"] for r in ida.values()])

    print()
    print("=== 2. KOMUNIKAT NAZYWA, CO WISI ===")
    # To jest cala pointa: po przeczytaniu tej linii ma byc wiadomo, ktory
    # etap sie wiesza. Same numery wierszy tego nie mowia.
    for etap in ("artykul", "dzien", "artykul-z-puli"):
        sprawdz("komunikat wymienia `%s`" % etap, etap in komunikat, komunikat)
    sprawdz("i nadal podaje numery", any(str(r) in komunikat for r in ida.values()),
            komunikat)

    print()
    print("=== 3. `finish_run` Z NAZWA ETAPU DZIALA JAK DOTAD ===")
    # Zmiana ma byc DODANIEM mozliwosci, nie podmiana zachowania: pozostale
    # dziewiec miejsc w kodzie podaje swoj wlasny etap i musi dalej dzialac.
    rid = wiszacy("dzien")
    db.finish_run(conn, rid, "FAILED", "dzien", "wyjatek w polowie")
    w = wiersz(rid)
    sprawdz("status i etap zapisane wprost",
            w["status"] == "FAILED" and w["stage"] == "dzien", w)
    sprawdz("nota zapisana", w["note"] == "wyjatek w polowie", w["note"])

    print()
    print("=== 4. KONTRDOWOD: STARE WYWOLANIE ZAMAZYWALO ETAP ===")
    # Odtwarzamy tamto wywolanie na tych samych danych. Gdyby dawalo to samo
    # co nowe, cala poprawka byla by bez znaczenia.
    rid = wiszacy("artykul")
    db.finish_run(conn, rid, "STALE", "kontrola", "przebieg wisial ponad trzy godziny")
    w = wiersz(rid)
    sprawdz("stara droga ZASTEPUJE `artykul` slowem `kontrola`",
            w["stage"] == "kontrola", w["stage"])
    # I ze nowa droga tego nie robi — na wierszu o tym samym etapie.
    rid2 = wiszacy("artykul")
    db.finish_run(conn, rid2, "STALE", note="tak jak robi to kontrola zdrowia")
    sprawdz("nowa droga zostawia `artykul`", wiersz(rid2)["stage"] == "artykul",
            wiersz(rid2)["stage"])

    print()
    print("=== 5. KOSZT PRZEBIEGU NADAL SIE DOLICZA ===")
    # `finish_run` przy okazji sumuje koszt wywolan przebiegu. Galaz bez etapu
    # to osobny SQL, wiec to jest miejsce, w ktorym latwo bylo zgubic sume.
    rid = wiszacy("dzien")
    db.record_call(conn, run_id=rid, provider="deepseek", model="deepseek-v4-flash",
                   purpose="classify", tokens_in=10, tokens_out=5, cost_usd=0.25)
    db.finish_run(conn, rid, "STALE", note="bez etapu")
    koszt = conn.execute("SELECT cost_usd FROM runs WHERE id = ?", (rid,)).fetchone()[0]
    sprawdz("suma kosztow policzona takze w galezi bez etapu",
            abs((koszt or 0) - 0.25) < 1e-9, koszt)
finally:
    config.przywroc_katalog_danych(_ZDJECIE)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
