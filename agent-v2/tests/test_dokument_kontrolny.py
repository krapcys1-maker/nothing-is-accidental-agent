"""Swiezosc mierzona DOKUMENTEM KONTROLNYM, nie wiekiem kotwicy.

CO BYLO ZLE. `swiezosc_faktu` konczylo sie na warunku „jesli tekst nie nazywa
wersji produktu i nie trafil w liste trzydziestu slow typu now/costs — przepusc",
i wracalo ZANIM ktokolwiek spojrzal na date. Swiezosc byla sprawdzana
slownikiem, nie data. Zmierzone 26 sierpnia 2026 na setce tematow: 43 z 54
tematow po progu przechodzilo nieprzeczytanych.

TRZY NOTKI, KTORE TO WYPUSCILO, i wszystkie trzy mialy dobra kotwice:
  - Kenia: liczby zgodne ze sledztwem TIME ze stycznia 2023, ale Sama zerwala
    kontrakt z OpenAI w lutym 2022 i wyszla z moderacji tresci w 2023. Uklad
    opisany w czasie przeszlym, wiec bez bledu czasu — ale nie istnieje.
  - Japonia: art. 30-4 nadal obowiazuje (sprawdzone: nowela z czerwca 2026 go
    nie tyka), ale „zero pozwolen" zaciera szesc warunkow, a porownanie „ani
    USA, ani UE" jest po prostu falszywe — art. 4 dyrektywy DSM to rowniez
    wyjatek bez pozwolenia, roznica jest w opt-oucie.
  - Microsoft: liczba z 10-K prawdziwa, ale uklad zmienila umowa
    restrukturyzacyjna STARSZA od raportu.

DWIE RZECZY, KTORE Z TEGO WYNIKAJA:
  1. Dokument kontrolny nie musi byc NOWSZY od zrodla. Ma RZADZIC.
  2. Wiek kotwicy przestaje byc powodem odrzucenia. Badanie z 2023 i ustawa z
     2018 maja przechodzic czysto — wlasciciel powiedzial to wprost.
"""
import datetime
import sys

sys.path.insert(0, "agent-v2")
import stages   # noqa: E402

zdane = oblane = 0
TERAZ = datetime.datetime(2026, 8, 26, tzinfo=datetime.timezone.utc)


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def fakt(**kw):
    d = {"fact": "x", "actually": "", "wrong_belief": "", "consequence": "",
         "decision": "", "source_date": "2023-01-18"}
    d.update(kw)
    return d


def wolno(**kw):
    return stages.swiezosc_faktu(fakt(**kw), teraz=TERAZ)


print("=== 1. ENDS: UKLAD JUZ NIE ISTNIEJE ===")
ok, powod = wolno(control_verdict="ENDS",
                  control_fact="Sama zerwala kontrakt w lutym 2022")
sprawdz("fakt o zerwanym ukladzie odpada", not ok, powod)
sprawdz("i powod nazywa rzecz po imieniu", "nie istnieje" in powod, powod)

print()
print("=== 2. MODIFIES: PRZECHODZI TYLKO Z ZASTRZEZENIEM ===")
ok, _ = wolno(control_verdict="MODIFIES",
              control_fact="art. 30-4 ma szesc warunkow, wykladnia niewiazaca")
sprawdz("z trescia zastrzezenia przechodzi", ok)
ok, powod = wolno(control_verdict="MODIFIES", control_fact="")
sprawdz("bez tresci odpada", not ok, powod)
# Zastrzezenie bez tresci jest GORSZE niz brak zastrzezenia: wyglada na
# sprawdzone, a nie niesie niczego, co pisarz moglby powiedziec.
sprawdz("powod mowi o pustym control_fact", "control_fact" in powod, powod)

print()
print("=== 3. CONFIRMS: WIEK KOTWICY PRZESTAJE MIEC ZNACZENIE ===")
# To jest cel calej zmiany. Obie kotwice sa grubo po progu 90 dni i obie MAJA
# przechodzic, bo ktos sprawdzil, ze rzecz nadal obowiazuje.
ok, powod = wolno(source_date="2023-07-06", control_verdict="CONFIRMS",
                  control_date="2026-06-26", control_fact="replikowane w 2026")
sprawdz("badanie z 2023 przechodzi (kotwica 1148 dni)", ok, powod)
ok, powod = wolno(source_date="2018-05-25", control_verdict="CONFIRMS",
                  control_date="2026-08-03", control_fact="nowela nie tyka art. 30-4")
sprawdz("ustawa z 2018 przechodzi (kotwica 3015 dni)", ok, powod)

print()
print("=== 4. CONFIRMS MUSI BYC SPRAWDZENIEM NA DZIS ===")
ok, powod = wolno(control_verdict="CONFIRMS", control_date="2024-01-01",
                  control_fact="x")
sprawdz("stary dokument kontrolny nie jest sprawdzeniem", not ok, powod)
sprawdz("prog liczony na DACIE KONTROLNEJ", "kontrolny ma" in powod, powod)

ok, _ = wolno(control_verdict="CONFIRMS", control_date="",
              control_fact="szukalem, nic nowszego nie ma")
sprawdz("brak daty uchodzi ze sladem szukania", ok)
ok, powod = wolno(control_verdict="CONFIRMS", control_date="", control_fact="")
sprawdz("ale puste pole juz nie", not ok, powod)

print()
print("=== 5. KONTRDOWOD: STARA BRAMKA PRZEPUSZCZALA WSZYSTKO TO SAMO ===")
# Bez pol kontrolnych kod wraca na stara sciezke. Fakt bez nazwanej wersji i bez
# slowa z listy przechodzi mimo zrodla sprzed lat — dokladnie tak dzialalo
# WSZYSTKO przed ta zmiana. Gdyby ten przypadek odpadal, test nie dowodzilby,
# ze to dokument kontrolny robi robote.
ok, _ = wolno(fact="Sama paid workers under two dollars an hour",
              source_date="2023-01-18")
sprawdz("bez pol kontrolnych stara sciezka nadal przepuszcza", ok)

# A z polami kontrolnymi ten sam fakt odpada. To jest cala roznica.
ok, _ = wolno(fact="Sama paid workers under two dollars an hour",
              source_date="2023-01-18", control_verdict="ENDS",
              control_fact="kontrakt zerwany w lutym 2022")
sprawdz("z polami kontrolnymi ten sam fakt odpada", not ok)

print()
print("=== 6. STARE ODMOWY NIE ZNIKLY ===")
ok, powod = wolno(fact="o1 is being deprecated", control_verdict="CONFIRMS",
                  control_date="2026-08-20", control_fact="x")
sprawdz("rzecz z ogloszonym koncem zycia nadal odpada", not ok, powod)
sprawdz("i to PRZED sprawdzeniem kontrolnym", "koncem zycia" in powod, powod)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
