"""Pliki uslug systemd: jedno wejscie, jeden zegar, jedna liczba.

Trzy rzeczy, ktore kosztowaly albo omal nie kosztowaly:

1. `nia-agent.service` mial sekcje [Install] z WantedBy=multi-user.target.
   Usluga typu oneshot uruchamiana z zegara nie ma czego instalowac — ale
   `systemctl enable nia-agent`, polecenie ktore kazdy odruchowo wpisuje,
   dopisaloby ja do startu systemu. Przebieg z `--wyslij` ruszalby wtedy przy
   kazdym bootcie, poza harmonogramem. Na serwerze usluga byla `disabled`,
   wiec do niczego nie doszlo — ale to nie jest zabezpieczenie, tylko szczescie.
   Pozostale dwie uslugi byly `static` od poczatku i to jest wzorzec.

2. TimeoutStartSec w usludze i LIMIT_CZASU_PRZEBIEGU_S w configu to TA SAMA
   liczba zapisana w dwoch miejscach. Rozjazd nie daje bledu — daje agenta,
   ktory liczy sobie inny koniec przebiegu niz ten, po ktorym systemd go ubija.
   Dokladnie taki rozjazd zabil dwa przebiegi.

3. Kazda usluga oneshot musi miec swoj timer. Usluga bez zegara i bez
   [Install] nie uruchomi sie nigdy, a wyglada na wdrozona.
"""
import pathlib
import re
import sys

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


KAT = pathlib.Path("agent-v2/systemd")
uslugi = sorted(KAT.glob("*.service"))
zegary = {p.stem for p in KAT.glob("*.timer")}

print("=== 1. ZADNA USLUGA Z ZEGARA NIE MA [Install] ===")
sprawdz("uslugi w ogole istnieja", len(uslugi) >= 3, len(uslugi))
for u in uslugi:
    tresc = u.read_text(encoding="utf-8")
    oneshot = re.search(r"^Type=oneshot", tresc, re.M) is not None
    ma_install = re.search(r"^\[Install\]", tresc, re.M) is not None
    if oneshot:
        sprawdz("%s (oneshot) nie ma sekcji [Install]" % u.name, not ma_install)
        sprawdz("%s ma swoj zegar" % u.name, u.stem in zegary,
                sorted(zegary))
    else:
        # Uslugi dlugodzialajace (VNC, Chrome) [Install] MAJA MIEC — maja
        # wstawac razem z systemem. Rozroznienie idzie po Type=, nie po nazwie.
        #
        # TU STALO `sprawdz(..., True)` — asercja, ktora nie mogla oblac nigdy,
        # a zajmowala miejsce w liczniku zdanych. Zdanie powyzej jest twarde
        # („MAJA MIEC") i wlasnie ono jest tu sprawdzane: usluga dlugodzialajaca
        # BEZ `[Install]` nie wstanie po restarcie maszyny i nikt tego nie
        # zauwazy, dopoki agent nie zamilknie na dobre.
        sprawdz("%s nie jest oneshot — MA mieć [Install] (wstaje z systemem)"
                % u.name, ma_install,
                "brak sekcji [Install] w usludze dlugodzialajacej")

print()
print("=== 2. LIMIT CZASU: JEDNA LICZBA W JEDNYM MIEJSCU ===")
agent = (KAT / "nia-agent.service").read_text(encoding="utf-8")
m = re.search(r"^TimeoutStartSec=(\d+)", agent, re.M)
sprawdz("usluga agenta ma limit czasu", m is not None)
if m:
    sprawdz("i jest rowny LIMIT_CZASU_PRZEBIEGU_S z configu",
            int(m.group(1)) == config.LIMIT_CZASU_PRZEBIEGU_S,
            "usluga=%s config=%s" % (m.group(1), config.LIMIT_CZASU_PRZEBIEGU_S))
    # Zapas musi byc mniejszy od limitu, inaczej koniec przebiegu wypada
    # PRZED jego poczatkiem i agent nie zrobi nic.
    sprawdz("zapas czasu jest mniejszy od limitu",
            0 < config.ZAPAS_CZASU_S < config.LIMIT_CZASU_PRZEBIEGU_S,
            (config.ZAPAS_CZASU_S, config.LIMIT_CZASU_PRZEBIEGU_S))
    # KONTRDOWOD dla samego limitu: musi starczyc na wiecej niz jedno
    # dzialanie z najdluzszym odstepem, inaczej agent nigdy nie wystawi dwoch.
    najdluzszy = max(g for _, g in config.ODSTEPY.values())
    sprawdz("i starczy na co najmniej dwa dzialania z najdluzsza przerwa",
            config.LIMIT_CZASU_PRZEBIEGU_S - config.ZAPAS_CZASU_S > najdluzszy,
            "najdluzsza przerwa %d s" % najdluzszy)

print()
print("=== 2b. PRZEBIEG NIE MOZE DOZYC NASTEPNEGO TERMINU ===")
# NAJDROZSZA WADA, JAKA TU BYLA, I NIKT JEJ NIE MIERZYL.
#
# Przebieg trzyma zamek. Jesli trwa dluzej niz odstep do nastepnego terminu,
# nastepny przebieg odpala sie, nie dostaje zamka i konczy sie po cichu — bez
# bledu, bez wpisu, bez pracy. Zmierzone na 54 przebiegach od 20 sierpnia do
# 3 wrzesnia 2026: mediana 70 min, ale 14 z 54 (26 procent) trwalo dluzej niz
# 130 min, czyli dluzej niz najkrotszy odstep. Trzy zostaly zabite przez
# systemd dokladnie po 150,0 min. Co czwarty przebieg mogl skasowac nastepce.
#
# Liczby ida z PLIKU ZEGARA, nie z pamieci: rozjazd ma wyjsc tutaj, a nie
# z pomiaru doby, ktora zostala w plecy.
zegar = (KAT / "nia-agent.timer").read_text(encoding="utf-8")
terminy = []
for g, mi in re.findall(r"^OnCalendar=\*-\*-\* (\d{2}):(\d{2}):", zegar, re.M):
    terminy.append(int(g) * 3600 + int(mi) * 60)
terminy.sort()
poslizg_m = re.search(r"^RandomizedDelaySec=(\d+)", zegar, re.M)
poslizg = int(poslizg_m.group(1)) if poslizg_m else 0

sprawdz("zegar ma co najmniej dwa terminy (inaczej nie ma czego porownywac)",
        len(terminy) >= 2, terminy)
sprawdz("liczba terminow zgadza sie z PRZEBIEGOW_DZIENNIE",
        len(terminy) == config.PRZEBIEGOW_DZIENNIE,
        (len(terminy), config.PRZEBIEGOW_DZIENNIE))
if len(terminy) >= 2:
    najkrotszy = min(b - a for a, b in zip(terminy, terminy[1:]))
    # POSLIZG SKRACA LUKE. `RandomizedDelaySec` przesuwa start losowo, wiec
    # najgorszy przypadek to „ten przebieg spozniony maksymalnie, nastepny
    # punktualnie" — i wlasnie ten przypadek musi sie miescic.
    luka = najkrotszy - poslizg
    sprawdz("najkrotszy odstep minus poslizg jest dodatni",
            luka > 0, (najkrotszy, poslizg))
    sprawdz("LIMIT_CZASU_PRZEBIEGU_S (%d s) miesci sie w tej luce (%d s)"
            % (config.LIMIT_CZASU_PRZEBIEGU_S, luka),
            config.LIMIT_CZASU_PRZEBIEGU_S < luka,
            "przebieg dozylby nastepnego terminu i skasowal go po cichu")
    # KONTRDOWOD ODTWARZANY, NIE OPISANY: stare liczby (limit 9000, poslizg
    # 1500) oblewaja ten sam warunek. Bez tego asercja przechodzilaby takze
    # wtedy, gdyby nic sie nie zmienilo.
    sprawdz("KONTRDOWOD: przy limicie 9000 i poslizgu 1500 warunek OBLEWA",
            not (9000 < najkrotszy - 1500), (najkrotszy, najkrotszy - 1500))

print()
print("=== 2c. DOBA MA DOWIEZC PLAN NOTEK, TAKZE PO STRACIE PRZEBIEGU ===")
# Sufit notek na przebieg jest CZASOWY. Przy pieciu przebiegach po dwie notki
# doba daje dokladnie dziesiec — plan co do jednej i zero zapasu. Dlatego
# istnieje tryb nadrabiania i dlatego jego arytmetyka jest sprawdzana tutaj,
# a nie odkrywana po dobie zakonczonej na osmiu.
import run as _run          # noqa: E402
import stages as _stg       # noqa: E402

_stg.NADRABIANE = set()
zwykle = _run.ile_notek_na_przebieg()
_stg.NADRABIANE = {"notka"}
nadrabiane = _run.ile_notek_na_przebieg(config.UDZIAL_CZASU_NA_NOTKI_NADRABIANIE)
_stg.NADRABIANE = set()
plan = len(config.NOTE_MIX_OTHER_DAY)

sprawdz("zwykly przebieg bierze co najmniej dwie notki", zwykle >= 2, zwykle)
sprawdz("doba bez awarii dowozi plan (%d x %d >= %d)"
        % (zwykle, config.PRZEBIEGOW_DZIENNIE, plan),
        zwykle * config.PRZEBIEGOW_DZIENNIE >= plan, (zwykle, plan))
sprawdz("nadrabianie bierze WIECEJ niz zwykly przebieg",
        nadrabiane > zwykle, (nadrabiane, zwykle))
sprawdz("i po stracie JEDNEGO przebiegu plan nadal sie domyka (%d x %d >= %d)"
        % (nadrabiane, config.PRZEBIEGOW_DZIENNIE - 1, plan),
        nadrabiane * (config.PRZEBIEGOW_DZIENNIE - 1) >= plan,
        (nadrabiane, plan))
# PLAN I SEN MUSZA CZYTAC TE SAMA LICZBE. Gdyby `zmiesci_sie` bralo przerwe
# z `ODSTEPY`, a `losuj_odstep` z nadrabiania, planista obiecywalby trzecia
# notke, a `zostal_czas` odmawialby jej tuz przed snem — bez bledu w logu.
_stg.NADRABIANE = {"notka"}
sprawdz("przy nadrabianiu obowiazuje KROTSZA przerwa, ta sama dla obu",
        _stg.zakres_odstepu("notka") == config.ODSTEP_NOTKI_NADRABIANIE,
        _stg.zakres_odstepu("notka"))
_stg.NADRABIANE = set()
sprawdz("a bez nadrabiania — zwykla",
        _stg.zakres_odstepu("notka") == config.ODSTEPY["notka"],
        _stg.zakres_odstepu("notka"))
# I ZE KROTSZA JEST NAPRAWDE KROTSZA, a nie tylko inna.
sprawdz("KONTRDOWOD: przerwa nadrabiania jest krotsza od zwyklej",
        config.ODSTEP_NOTKI_NADRABIANIE[1] < config.ODSTEPY["notka"][1],
        (config.ODSTEP_NOTKI_NADRABIANIE, config.ODSTEPY["notka"]))

print()
print("=== 3. BEZ AUTOMATYCZNEGO PONAWIANIA PLATNYCH PRZEBIEGOW ===")
# Restart= po bledzie oznacza ponawianie oplaconych wywolan bez nadzoru.
for u in uslugi:
    tresc = u.read_text(encoding="utf-8")
    if re.search(r"^Type=oneshot", tresc, re.M):
        sprawdz("%s nie restartuje sie sama" % u.name,
                re.search(r"^Restart=", tresc, re.M) is None)

print()
print("=== 4. ZEGAR WSKAZUJE NA SCIEZKE, KTORA NAPRAWDE UZYWAMY ===")
# `artykul_z_puli.py` powstal 25 sierpnia 2026, zeby ZASTAPIC sciezke skauta:
# skaut wymaga dwoch udokumentowanych precedensow, a pod AI takie tematy sa
# tylko trzy — zasilki, auta autonomiczne, gielda — wiec trzy artykuly z rzedu
# wyszly o zautomatyzowanej biurokracji zamiast o AI.
#
# Zastepnik napisano, uzywano RECZNIE i przez piec dni NIE WPIETO W ZEGAR.
# `nia-artykul.service` wskazywal caly czas na sciezke zastapiona, wiec gdyby
# timer wystartowal, produkowalby te sama monokulture i pomijal bramke
# „uniesie artykul", podpytania do researchu, glebokosc z pieciu filarow oraz
# spizarnie kandydatow. Ta sama klasa zaniedbania, co szampon w kolejce
# promocyjnej: zmiana zrobiona, resztka po niej nie sprzatnieta.
_artykul = [u for u in uslugi if "artykul" in u.name]
sprawdz("jednostka artykulu istnieje", bool(_artykul), [u.name for u in uslugi])
for u in _artykul:
    tresc = u.read_text(encoding="utf-8")
    exec_line = next((l for l in tresc.splitlines()
                      if l.startswith("ExecStart=")), "")
    sprawdz("%s uruchamia sciezke z puli, nie skauta" % u.name,
            "artykul_z_puli.py" in exec_line, exec_line[:90])
    sprawdz("%s nie wola run.py na artykul" % u.name,
            "run.py" not in exec_line, exec_line[:90])
    # Bez --wyslij timer napisalby artykul i zostawil go na dysku, czyli
    # tygodniowa publikacja przestalaby wychodzic bez jednego komunikatu.
    sprawdz("%s ma --wyslij, inaczej nic nie wychodzi" % u.name,
            "--wyslij" in exec_line, exec_line[:90])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
