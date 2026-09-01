# -*- coding: utf-8 -*-
"""Audyt CALEGO systemu na zywych danych, jednym poleceniem.

    python agent-v2/audyt_systemu.py

PO CO. Segmenty tematow i researchu maja wlasne audyty. Reszta — publikowanie,
notki, komentarze, statystyki, budzet, artykul — nie miala zadnego, a to
wlasnie tam wychodzily wady, ktorych testy nie widza: test pilnuje, ze kod robi
to, co obiecuje, audyt pyta, czy PRODUKCJA wyglada tak, jak powinna.

Kazda wada z tej sesji byla widoczna w danych i niewidoczna w testach:
licznik komentarzy zanizal 30% wobec realnych 63%, `feasible` bylo True u
szesciu na szesc, kolejka promocji nie miala daty waznosci, a artykulow nie
mierzylismy WCALE, mimo ze pomiar „dzialal".

NIE WOLA PLATNEGO MODELU. Kod wyjscia 1, gdy cokolwiek jest BLEDEM.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))

import browser   # noqa: E402
import config    # noqa: E402
import statystyki  # noqa: E402

WERDYKTY: list[tuple[str, str]] = []

# DZIEN PRZESTAWIENIA KONTA NA AI. Wszystko starsze opisuje inna publikacje
# i mieszanie tego z dzisiejszym stanem juz raz doprowadzilo do zlej decyzji
# (sedzia banku dostal do oceny notki o szamponie).
PIVOT = "2026-08-25"

# CO MA WYCHODZIC NA ZEWNATRZ — JEDNA LISTA, DWOCH CZYTELNIKOW (etap 1 i 2).
#
# Byly tu dwie recznie przepisane krotki po szesc pozycji, w dwoch miejscach
# tego samego pliku. Trzecia kopia powstalaby przy pierwszym nowym rodzaju,
# a rozjechanie sie kopii to dokladnie ta klasa bledu, ktora ten audyt lapie
# (`config.normy_dzienne` mowila „follow", dziennik zapisywal „obserwacja"
# i licznik meldowal 0% przy dzialajacym bloku).
#
# `obserwacja` JEST TU OD 1 WRZESNIA 2026 i to jest sedno zmiany — powody
# stoja przy petli werdyktow w etapie 1.
RODZAJE_WYCHODZACE = ("notka", "komentarz", "odpowiedz", "polubienie",
                      "restack", "subskrypcja", "obserwacja")

# ROZLICZANE Z PLANU DNIA (etap 2) — WEZSZA LISTA, I TO NIE JEST WYJATEK,
# TYLKO ARYTMETYKA.
#
# Prog „zrobione >= plan * 0,6" niesie informacje dopiero przy planie, ktory
# da sie w ogole podzielic. Realne normy dobowe (`config.normy_dzienne`):
# notka 5, komentarz ~18, polubienie ~13, restack 1,5, obserwacja ~1,2
# (`FOLLOW_MIESIECZNIE` 30-44 na 30 dni), subskrypcja 0,3 (6-12 na miesiac).
#
# `obserwacja` DOSZLA 1 WRZESNIA 2026, bo lezy w tej samej skali co restack,
# ktory stoi tu od poczatku. `subskrypcja` zostaje poza lista: przy 0,3 na dobe
# wiekszosc dni ma plan ZERO, a 60% z zera nie jest pytaniem. Ten sam rachunek
# prowadzi `norma.py` (`MIN_PLAN_DZIENNY_DO_ZNAKU` = 3 dla kratki tabeli,
# `MIN_BRAKOW_W_OKNIE_DO_ALARMU` = 4 dla alarmu) — i tam obserwacje takze
# podlegaja WYLACZNIE progom, od kiedy `NIEWYKONALNE` jest puste.
RODZAJE_Z_PLANEM = ("notka", "komentarz", "polubienie", "restack",
                    "obserwacja")

# POMINIECIE NIE JEST ANI SUKCESEM, ANI PORAZKA — I DLATEGO MA WLASNY LICZNIK.
#
# `obserwacja_pominieta` zapisuje sie z `udane=True` w trzech sytuacjach i
# zadna z nich nie jest wystawieniem czegokolwiek: profil okazal sie juz
# obserwowany („Unfollow" w menu, `browser.py:2701`), cala pula hostow z
# historii komentarzy jest juz obserwowana (`run.py:1061`), albo wszyscy
# wylosowani byli znani z pamieci (`run.py:1156`). Slotu dnia to nie zjada
# (`run.py:1087` liczy wylacznie proby), wiec blok probuje dalej.
#
# WLICZONE DO `udane` — podnosilyby „wychodzi: obserwacja" na OK przy ZERZE
# prawdziwych obserwacji, czyli robilyby dokladnie to, co robilo zdanie
# o „braku przycisku": tlumaczylyby zero. Wliczone do `nieudane` — zanizalyby
# wynik za stan calkowicie poprawny i podbijaly „porazki dominuja". Stoja wiec
# osobno: raport je pokazuje i o nic z nich nie pyta.
#
# `norma.RODZAJE` tego rodzaju NIE ZAWIERA i zawierac nie ma — ten licznik
# musi go pominac sam, bo czyta dziennik wprost.
POMINIECIA = ("obserwacja_pominieta",)


def policz_rodzaje(wpisy: list[dict]) -> tuple[Counter, Counter, Counter]:
    """(udane, nieudane, pominiete) — trzy liczniki, bo stany naprawde sa trzy.

    Dzielenie dziennika samym `udane` mialo sens, dopoki kazdy wpis byl proba.
    Od 1 wrzesnia 2026 jest rodzaj, ktory proba nie jest (patrz `POMINIECIA`),
    a nosi `udane=True` — wiec `Counter(... if w.get("udane"))` zaliczalby go
    do sukcesow. Jedno miejsce, w ktorym to sie rozstrzyga, zeby zadna suma
    nizej nie musiala o tym pamietac.
    """
    udane: Counter = Counter()
    nieudane: Counter = Counter()
    pominiete: Counter = Counter()
    for w in wpisy:
        rodzaj = w.get("rodzaj")
        if rodzaj in POMINIECIA:
            pominiete[rodzaj] += 1
            continue
        (udane if w.get("udane") else nieudane)[rodzaj] += 1
    return udane, nieudane, pominiete


def etap(nr: int, nazwa: str) -> None:
    print()
    print("=" * 78)
    print("ETAP %d — %s" % (nr, nazwa))
    print("=" * 78)


def werdykt(nazwa: str, stan: str, szczegol: str = "") -> None:
    WERDYKTY.append((nazwa, stan))
    print("  >> %-5s %s%s" % (stan, nazwa, ("   " + szczegol) if szczegol else ""))


def dziennik() -> list[dict]:
    if not browser.DZIENNIK.exists():
        return []
    wpisy = []
    for linia in browser.DZIENNIK.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia:
            continue
        try:
            w = json.loads(linia)
        except ValueError:
            continue
        if isinstance(w, dict):
            wpisy.append(w)
    return wpisy


def dzien(w: dict) -> str:
    return str(w.get("kiedy") or "")[:10]


def main() -> int:
    wpisy = dziennik()
    po_pivocie = [w for w in wpisy if dzien(w) >= PIVOT]
    c = sqlite3.connect(str(config.DB_PATH))
    c.row_factory = sqlite3.Row

    # ---------------------------------------------------------------
    etap(1, "PUBLIKOWANIE — co naprawde wychodzi na zewnatrz")
    if not wpisy:
        werdykt("dziennik istnieje", "BLAD", str(browser.DZIENNIK))
        return 1
    print("  wpisow w dzienniku: %d, po przestawieniu na AI (%s): %d"
          % (len(wpisy), PIVOT, len(po_pivocie)))
    udane, nieudane, pominiete = policz_rodzaje(po_pivocie)
    for rodzaj in sorted(set(udane) | set(nieudane)):
        print("    %-12s udane %3d, nieudane %2d"
              % (rodzaj, udane.get(rodzaj, 0), nieudane.get(rodzaj, 0)))
    # POMINIECIA STOJA OBOK TABELI, NIE W NIEJ. Kolumny nazywaja sie „udane"
    # i „nieudane", wiec kazda liczba postawiona w ktorejkolwiek z nich cos
    # twierdzi — a pominiecie nie twierdzi ani jednego, ani drugiego. Powody
    # przy `POMINIECIA`.
    if pominiete:
        print("    pominiecia (ani sukces, ani porazka): %s"
              % ", ".join("%s %d" % (r, i) for r, i in sorted(pominiete.items())))
    # KAZDY RODZAJ MA WYCHODZIC. Rodzaj, ktorego nie ma ani razu, to albo
    # martwa galaz, albo cichy blad — jedno i drugie warto zobaczyc.
    #
    # OBSERWACJE WESZLY DO TEJ PETLI 1 WRZESNIA 2026, BEZ WLASNEGO ZDANIA.
    # Stal tu osobny werdykt „obserwacje (follow) — znane ograniczenie" i
    # drukowal „brak przycisku w sesji", bo 23 sierpnia uznano, ze Substack
    # zdjal „Follow" z profili. POMIAR BYL DOBRY: slowa „Follow" naprawde nie
    # ma w HTML profilu. ZLY BYL WNIOSEK — menu z ta pozycja Substack
    # dorysowuje DOPIERO PO KLIKNIECIU `button[aria-label="Profile actions"]`,
    # wiec w HTML zamknietej strony przycisku nie ma i byc nie moze. Zmierzone
    # ponownie na zywej sesji 1 wrzesnia 2026 (sam odczyt, zero klikniec): menu
    # to `Copy link / Share / Send message / Follow / Mute / Block / Report`,
    # a na profilu juz obserwowanym w miejscu „Follow" stoi „Unfollow".
    #
    # DLACZEGO TO BYLO GORSZE TUTAJ NIZ GDZIEKOLWIEK INDZIEJ. Jedynym
    # produktem tego pliku jest raport dla czlowieka. Zero z wyjasnieniem
    # przestaje wygladac na problem, wiec nikt go nie sprawdza — audyt, ktory
    # tlumaczy zero zdaniem nieprawdziwym, jest gorszy od audytu, ktory tego
    # zera w ogole nie zauwaza. To samo zdanie stalo w `norma.NIEWYKONALNE`
    # i zostalo zdjete tego samego dnia; ta lista jest dzis pusta.
    for rodzaj in RODZAJE_WYCHODZACE:
        werdykt("wychodzi: %s" % rodzaj,
                "OK" if udane.get(rodzaj) else "UWAGA",
                "%d od %s" % (udane.get(rodzaj, 0), PIVOT))
    if nieudane:
        naj = nieudane.most_common(3)
        # MIANOWNIK TO PROBY, NIE WPISY. `sum(udane.values())` bralo wszystko,
        # co ma `udane=True` — a od 1 wrzesnia jest tam takze
        # `obserwacja_pominieta`, ktora nie jest praca. Kazde pominiecie
        # podnosilo wiec prog, powyzej ktorego porazki „dominuja", i robilo
        # ten werdykt lagodniejszym za stan, w ktorym NIC nie wyszlo.
        # `policz_rodzaje` odsiewa to u zrodla, wiec ta suma juz liczy proby.
        werdykt("porazki nie dominuja",
                "OK" if sum(nieudane.values()) < sum(udane.values()) / 2 else "UWAGA",
                ", ".join("%s %d" % (r, i) for r, i in naj))

    # ---------------------------------------------------------------
    etap(2, "NORMA — plan wobec wykonania, dzien po dniu")
    dni = defaultdict(Counter)
    for w in po_pivocie:
        # `POMINIECIA` odpadaja tu z tego samego powodu, co w etapie 1: ponizej
        # ta liczba idzie wprost do „plan X w dniu Y" i pominiecie liczone jak
        # wykonanie meldowaloby wykonany plan przy zerze prawdziwych obserwacji.
        if w.get("udane") and w.get("rodzaj") not in POMINIECIA:
            dni[dzien(w)][str(w.get("rodzaj"))] += 1
    for d in sorted(dni)[-7:]:
        print("    %s  %s" % (d, "  ".join(
            "%s %d" % (r, i) for r, i in sorted(dni[d].items())
            if r in RODZAJE_WYCHODZACE)))
    # PLAN AGENTA, NIE DZISIEJSZA AMBICJA. `config.normy_dzienne()` mowi, ile
    # POWINNO wychodzic docelowo; `norma.budzety_dzienne()` — ile agent w tym
    # dniu w ogole sobie zalozyl. Mierzenie wykonania ambicja daje falszywy
    # alarm: 29 sierpnia agent zalozyl 10 komentarzy i zrobil 6 (60% planu),
    # a licznik liczony widelkami pokazywal 32%.
    import norma as norma_mod
    zalozone = norma_mod.budzety_dzienne() or {}
    try:
        normy = config.normy_dzienne() or {}
    except Exception:
        normy = {}
    if normy and dni:
        # OSTATNI PELNY DZIEN, nie dzisiejszy: dzis moze byc dopiero w polowie
        # i kazdy plan wygladalby na niewykonany.
        dzis = datetime.now(timezone.utc).date().isoformat()
        pelne = [d for d in sorted(dni) if d < dzis]
        if pelne:
            ost = pelne[-1]
            plan_dnia = zalozone.get(ost) if isinstance(zalozone.get(ost), dict) else {}
            # CICHY DZIEN NIE JEST NIEDOBOREM. Wycisza dokladnie to, co
            # NADAJEMY — notki i restacki — a rozmowa idzie normalnie. Audyt,
            # ktory tego nie wie, zglaszalby „notek 0 z 5" za kazdym razem,
            # gdy system zachowa sie zgodnie z projektem. Falszywy alarm uczy
            # ignorowac alarmy, wiec pytamy o to samo, co pyta przebieg.
            cichy = config.cichy_dzien(
                datetime.fromisoformat(ost).replace(tzinfo=timezone.utc))
            wyciszone = set(config.CICHY_DZIEN_WYCISZA_RODZAJE) if cichy else set()
            if cichy:
                print("    (%s byl CICHYM DNIEM — %s sa wyciszone z zalozenia)"
                      % (ost, ", ".join(sorted(wyciszone)) or "nadawane tresci"))
            for rodzaj in RODZAJE_Z_PLANEM:
                if rodzaj in wyciszone:
                    werdykt("plan %s w dniu %s" % (rodzaj, ost), "OK",
                            "cichy dzien — wyciszone z zalozenia")
                    continue
                plan = plan_dnia.get(rodzaj) or normy.get(rodzaj)
                if not plan:
                    continue
                zrobione = dni[ost].get(rodzaj, 0)
                werdykt("plan %s w dniu %s" % (rodzaj, ost),
                        "OK" if zrobione >= plan * 0.6 else "UWAGA",
                        "%d z %g%s" % (zrobione, plan,
                                       " (zalozony)" if plan_dnia.get(rodzaj)
                                       else " (norma docelowa)"))
    else:
        werdykt("normy dzienne sa policzalne", "BLAD",
                "ani budzety.json, ani config.normy_dzienne()")

    # ---------------------------------------------------------------
    etap(3, "KOMENTARZE — czy nie wygladamy na bota")
    kom = [w for w in po_pivocie
           if w.get("rodzaj") in ("komentarz", "odpowiedz") and w.get("udane")]
    # DWA RODZAJE KOMENTARZY, DWA POLA. Pod cudzym ARTYKULEM `gdzie` to adres;
    # pod cudza NOTKA `gdzie` to „note/c-<numer>", a publikacja stoi w polu
    # `publikacja`. Pierwsza wersja tego audytu brala tylko hosty z adresow —
    # czyli 19 z 50 komentarzy, a 31 pomijala CALKIEM. Do tego dzielila maksimum
    # przez WSZYSTKIE komentarze, takze te bez hosta, wiec drukowany udzial byl
    # zanizony ponad dwukrotnie. Wniosek „nie wygladamy na bota" byl prawdziwy,
    # ale wyszedl ze szczescia, nie z metody.
    hosty = Counter()
    bez_adresu = 0
    for w in kom:
        host = urlparse(str(w.get("gdzie") or "")).netloc.lower()
        if host:
            hosty[host.removeprefix("www.")] += 1
            continue
        kto = " ".join(str(w.get("publikacja") or "").split())
        if kto:
            hosty[kto] += 1
        else:
            bez_adresu += 1
    print("  komentarzy i odpowiedzi po przestawieniu: %d w %d miejscach"
          % (len(kom), len(hosty)))
    if bez_adresu:
        # Nie zgadujemy, gdzie poszly. Melduje, bo pomiar bez tej liczby
        # wyglada na pelny, a nie jest.
        werdykt("kazdy komentarz wie, gdzie poszedl",
                "OK" if bez_adresu * 5 <= len(kom) else "UWAGA",
                "%d z %d bez adresu i bez nazwy publikacji"
                % (bez_adresu, len(kom)))
    for h, i in hosty.most_common(6):
        print("    %-42s %d" % (h[:42], i))
    if hosty:
        najwiecej = hosty.most_common(1)[0][1]
        # MIANOWNIK TO PRZYPISANE, NIE WSZYSTKIE. Dzielenie przez `len(kom)`
        # rozwadnia udzial o kazdy komentarz, ktorego nie umiemy przypisac.
        przypisane = sum(hosty.values())
        udzial = najwiecej / max(1, przypisane)
        # PROG WLASCICIELA: „nie ma nakurwiac na jednym profilu". Jedna
        # publikacja ponad polowa wszystkiego to juz tak wyglada.
        werdykt("zadna publikacja nie zbiera polowy komentarzy",
                "OK" if udzial < 0.5 else "BLAD",
                "najwiecej %d z %d przypisanych (%d%%)"
                % (najwiecej, przypisane, round(100 * udzial)))
        werdykt("pula jest wezsza niz caly Substack, ale nie jednoosobowa",
                "OK" if len(hosty) >= 3 else "UWAGA",
                "%d publikacji" % len(hosty))
        # POLUBIENIA TEZ MAJA WIEDZIEC, GDZIE POSZLY. To NAJCZESTSZE nasze
        # dzialanie — 151 wobec 95 komentarzy — i do 31 sierpnia zapisywalo sie
        # jako `{kiedy, rodzaj, udane}` i nic wiecej. Nie dalo sie wiec nawet
        # ZMIERZYC, czy lajkujemy pod AI, czy pod rezerwa paliwowa.
        lajki = [w for w in po_pivocie
                 if w.get("rodzaj") == "polubienie" and w.get("udane")]
        z_celem = [w for w in lajki if str(w.get("publikacja") or "").strip()]
        if lajki:
            print("  polubien: %d, z zapisanym celem: %d"
                  % (len(lajki), len(z_celem)))
            for h, i in Counter(str(w.get("publikacja"))
                                for w in z_celem).most_common(5):
                print("    %-42s %d" % (h[:42], i))
        # Prog niski, bo historia sprzed poprawki zostaje w pliku na zawsze —
        # pytamy, czy zapis DZIALA, nie czy przepisano przeszlosc.
        werdykt("polubienia zapisuja, czyj wpis polubily",
                "OK" if z_celem else "UWAGA",
                "%d z %d ma cel" % (len(z_celem), len(lajki)))

        odstep = getattr(config, "ODSTEP_DNI_NA_PUBLIKACJE", 0)
        werdykt("odstep miedzy wizytami w tej samej publikacji stoi",
                "OK" if odstep >= 3 else "BLAD", "%s dni" % odstep)

    # ---------------------------------------------------------------
    etap(4, "STATYSTYKI — czy mierzymy wszystko, co wystawiamy")
    zmierzone = Counter()
    # SCIEZKA Z MODULU, NIE ZGADNIETA. Pierwsza wersja tego audytu pytala
    # o `statystyki.PLIK`, ktorego nie ma — `getattr` oddawal None, plik
    # „nie istnial" i audyt zglaszal ZERO pomiarow przy 369 prawdziwych.
    # Audyt, ktory myli sie w nazwie, produkuje falszywy alarm; a falszywy
    # alarm uczy ignorowac alarmy.
    plik = statystyki._plik()
    if plik.exists():
        for linia in plik.read_text(encoding="utf-8").splitlines():
            try:
                w = json.loads(linia)
            except ValueError:
                continue
            if isinstance(w, dict):
                zmierzone[str(w.get("rodzaj"))] += 1
    print("  pomiarow w pliku: %s"
          % ", ".join("%s %d" % (r, i) for r, i in sorted(zmierzone.items())))
    # ARTYKUL BYL JEDYNYM RODZAJEM Z ZEREM POMIAROW przy 369 komentarzach
    # i 365 notkach — i to najdrozszy, jaki produkujemy.
    for rodzaj in ("notka", "komentarz", "artykul"):
        werdykt("mierzymy: %s" % rodzaj,
                "OK" if zmierzone.get(rodzaj) else "BLAD",
                "%d pomiarow" % zmierzone.get(rodzaj, 0))
    zrodlo = (KATALOG / "browser.py").read_text(encoding="utf-8")
    werdykt("artykul czytany z panelu wydawcy, nie z koncowki notek",
            "OK" if "post_management/published" in zrodlo else "BLAD")
    werdykt("i nie sklada przedrostka 'p-' do note_stats",
            "OK" if "note_stats/{przedrostek}" not in zrodlo else "BLAD")
    werdykt("nasza wlasna tresc nie podlega limitowi pomiaru",
            "OK" if "NASZE_RODZAJE" in zrodlo else "BLAD")

    # ---------------------------------------------------------------
    etap(5, "ARTYKUL — dlugosc, uwagi i petla zwrotna")
    art = list(c.execute("SELECT id, title, body, notes, created_at"
                         " FROM articles ORDER BY id"))
    dlugosci = [len(str(a["body"] or "").split("## Sources")[0].split())
                for a in art]
    if dlugosci:
        print("  artykulow: %d, dlugosc %d-%d slow (srednia %d)"
              % (len(art), min(dlugosci), max(dlugosci),
                 sum(dlugosci) / len(dlugosci)))
        pasma = {k: v for k, v in config.DLUGOSC_WG_GLEBOKOSCI.items()}
        w_pasmie = sum(1 for d in dlugosci
                       if any(p["min"] <= d <= p["max"] for p in pasma.values()))
        werdykt("kazdy artykul miesci sie w ktorymkolwiek pasmie",
                "OK" if w_pasmie == len(dlugosci) else "UWAGA",
                "%d z %d" % (w_pasmie, len(dlugosci)))
        # SKALOWANIE DLUGOSCI DOTAD SIE NIE ODEZWALO, i to z DWOCH roznych
        # przyczyn na dwoch sciezkach — dlatego ta uwaga zostaje, dopoki nie
        # wyjdzie pierwszy artykul krotszy niz RICH.
        #
        #   `artykul_z_puli.py` (ta, ktora publikuje): `glebokosc` czytano
        #     z `ocena.get("depth")`, a kontrakt `warto_pisac.md` pola `depth`
        #     NIE MA — pole czytane, nigdy nieustawiane, wiec zawsze RICH.
        #     Naprawione: glebokosc liczy KOD z pieciu filarow oceny.
        #   `run.py`: `wykonalnosc.md` porzadkuje tematy RICH przed SINGLE,
        #     a wybor bierze najlepszy — wiec RICH wygrywa doborem.
        #
        # Pierwsza przyczyna byla wada, druga nia nie jest. Historyczne
        # jedenascie artykulow powstalo przed poprawka, wiec ich plaska
        # dlugosc nie mowi nic o dzisiejszym stanie.
        rich = pasma["RICH"]
        wszystkie_rich = all(d >= rich["min"] for d in dlugosci)
        werdykt("skalowanie dlugosci ma sie czym odezwac",
                "UWAGA" if wszystkie_rich else "OK",
                "wszystkie %d artykulow w pasmie RICH; martwe pole `depth`"
                " naprawione, czekamy na pierwszy krotszy" % len(dlugosci)
                if wszystkie_rich else "")
    uwagi = Counter()
    z_uwagami = 0
    for a in art:
        try:
            n = json.loads(a["notes"] or "[]")
        except ValueError:
            continue
        if not n:
            continue
        z_uwagami += 1
        for g in {str(x.get("gate")) for x in n if isinstance(x, dict)}:
            if g not in ("DLUGOSC", "RECENZJA"):
                uwagi[g] += 1
    print("  uwagi bramek (artykulow z zapisem: %d):" % z_uwagami)
    for g, i in uwagi.most_common(8):
        print("    %-28s %d/%d" % (g, i, z_uwagami))
    werdykt("bramki formy sie odzywaja, a nie milcza",
            "OK" if uwagi else "BLAD")
    # KONTRDOWOD NA MARTWA BRAMKE: uwaga, ktora pada przy KAZDYM artykule,
    # nic nie rozroznia — tak samo jak `feasible` True u szesciu na szesc.
    stale = [g for g, i in uwagi.items() if z_uwagami >= 4 and i == z_uwagami]
    werdykt("zadna bramka nie pada przy kazdym artykule",
            "OK" if not stale else "UWAGA", ", ".join(stale))
    import stages
    petla = stages.ostatnie_uwagi()
    werdykt("uwagi wracaja do pisarza nastepnego artykulu",
            "OK" if petla.strip() else "BLAD",
            "%d znakow" % len(petla))

    # ---------------------------------------------------------------
    etap(6, "PIENIADZE — sufit, tor testowy, koszt dnia")
    dzis = datetime.now(timezone.utc).date().isoformat()
    kolumny = {r[1] for r in c.execute("PRAGMA table_info(runs)")}
    werdykt("tor testowy jest oddzielony od produkcji",
            "OK" if "tryb" in kolumny else "BLAD",
            "kolumna runs.tryb")
    koszty = defaultdict(float)
    for r in c.execute(
            "SELECT substr(k.at,1,10) d, COALESCE(r.tryb,'produkcja') t,"
            " SUM(k.cost_usd) s FROM calls k LEFT JOIN runs r ON r.id=k.run_id"
            " GROUP BY d, t ORDER BY d DESC LIMIT 14"):
        koszty[(r["d"], r["t"])] = float(r["s"] or 0)
    for (d, t), s in sorted(koszty.items(), reverse=True)[:8]:
        print("    %s  %-10s %6.2f USD" % (d, t, s))
    dzis_prod = sum(s for (d, t), s in koszty.items()
                    if d == dzis and t == "produkcja")
    werdykt("dzisiejsza produkcja miesci sie w sufcie",
            "OK" if dzis_prod <= config.DAILY_LIMIT_USD else "BLAD",
            "%.2f z %.2f USD" % (dzis_prod, config.DAILY_LIMIT_USD))
    werdykt("sufit dzienny nie jest podniesiony na stale",
            "OK" if config.DAILY_LIMIT_USD <= 5.0
            or config.SUFIT_PODNIESIONY_NA == dzis else "UWAGA",
            "%.2f USD" % config.DAILY_LIMIT_USD)

    # ---------------------------------------------------------------
    etap(7, "CO NAS KOSZTUJE JEDEN CZYTELNIK")
    # JEDYNA LICZBA, KTORA WIAZE PIENIADZE Z CELEM. Reszta audytu mowi, czy
    # system dziala; ta mowi, czy warto. Wlasciciel nie podejmie tej decyzji,
    # nie majac jej przed oczami — a do 31 sierpnia nie byla nigdzie liczona,
    # bo nie zapisywalismy liczby subskrybentow w czasie.
    stany = []
    if browser.WZROST.exists():
        for linia in browser.WZROST.read_text(encoding="utf-8").splitlines():
            try:
                w = json.loads(linia)
            except ValueError:
                continue
            if isinstance(w, dict) and w.get("kiedy"):
                stany.append(w)
    if len(stany) < 2:
        werdykt("koszt czytelnika policzalny", "UWAGA",
                "za malo zapisow wzrostu (%d) — potrzebne co najmniej dwa dni"
                % len(stany))
    else:
        a, b = stany[0], stany[-1]
        od, do = str(a["kiedy"])[:10], str(b["kiedy"])[:10]
        przyrost = (int(b.get("subskrybenci") or 0)
                    - int(a.get("subskrybenci") or 0))
        wydane = c.execute(
            "SELECT COALESCE(SUM(k.cost_usd),0) FROM calls k"
            " LEFT JOIN runs r ON r.id=k.run_id"
            " WHERE COALESCE(r.tryb,'produkcja')='produkcja'"
            " AND substr(k.at,1,10) BETWEEN ? AND ?", (od, do)).fetchone()[0]
        print("  od %s do %s: wydane %.2f USD, subskrybentow %+d"
              % (od, do, wydane, przyrost))
        if przyrost > 0:
            werdykt("koszt jednego subskrybenta", "OK",
                    "%.2f USD" % (wydane / przyrost))
        else:
            # ZERO PRZYROSTU TO NIE JEST KOSZT NIESKONCZONY, tylko brak
            # odpowiedzi. Dzielenie przez zero dawaloby liczbe, ktora wyglada
            # na pomiar i nim nie jest.
            werdykt("koszt jednego subskrybenta", "UWAGA",
                    "%.2f USD wydane, zero przyrostu w tym oknie" % wydane)

    # ILE MATERIALU ZJADA LEZAKOWANIE. Bank bierze NAJLEPSZE z puli, wiec odpad
    # jest cena selekcji, nie wada. Ale nikt go dotad nie liczyl, a rzad
    # wielkosci decyduje, czy zbieramy w sam raz, czy dwa razy za duzo.
    import stages as _stages
    indeks = _stages.wczytaj_indeks()
    if indeks:
        lic = Counter(str(k.get("status")) for k in indeks)
        print("  bank: %s  (sufit %d wpisow, termin %d dni)"
              % (dict(lic), 600, config.BANK_MAKS_DNI))
        zmarnowane = lic.get("przeterminowany", 0)
        wziete = lic.get("uzyty", 0)
        rozliczone = zmarnowane + wziete
        if rozliczone:
            udzial = zmarnowane / rozliczone
            werdykt("wiecej pomyslow uzywamy niz przeterminowujemy",
                    "OK" if udzial < 0.5 else "UWAGA",
                    "%d przeterminowanych na %d rozliczonych (%d%%)"
                    % (zmarnowane, rozliczone, round(100 * udzial)))
        else:
            werdykt("bank ma juz co rozliczac", "UWAGA",
                    "nic jeszcze nie zostalo ani uzyte, ani przeterminowane")
        werdykt("bank daleko od sufitu",
                "OK" if len(indeks) < 600 * 0.8 else "UWAGA",
                "%d z 600" % len(indeks))

    # ---------------------------------------------------------------
    etap(8, "PROMOCJA I PAMIEC — czy nic sie nie starzeje w cichosci")
    okno = getattr(config, "OKNO_PROMOCJI_DNI", None)
    werdykt("kolejka promocji ma date waznosci",
            "OK" if okno else "BLAD", "%s dni" % okno)
    platne = browser.hosty_tylko_dla_placacych()
    werdykt("pamietamy publikacje tylko dla placacych",
            "OK" if isinstance(platne, set) else "BLAD",
            "%d hostow" % len(platne))
    # PAMIEC O TEMATACH NIE MA I NIE MA MIEC LIMITU DNI — od 25 sierpnia
    # pamietamy WSZYSTKIE wystawione notki. Pytanie o liczbe dni bylo wiec
    # zle postawione: nie ma takiego ustawienia. Mierzymy wiec SKUTEK, czyli
    # to, o co naprawde chodzi — czy w produkcji leza powtorki.
    #
    # Powod: 23 i 24 sierpnia poszly dwie notki o tym samym symbolu na
    # butelce szamponu, bo ochrona konczyla sie o polnocy.
    import stages
    teksty = [(dzien(w), " ".join(str(w.get("tekst") or "").split()))
              for w in po_pivocie
              if w.get("rodzaj") == "notka" and w.get("udane") and w.get("tekst")]
    blizniaki = [(a[0], b[0], a[1][:60]) for i, a in enumerate(teksty)
                 for b in teksty[i + 1:]
                 if a[0] != b[0] and stages._o_tym_samym(
                     a[1], b[1], **stages.POROWNANIE_MIEDZY_DNIAMI)]
    for d1, d2, s in blizniaki[:4]:
        print("    POWTORKA %s / %s: %s" % (d1, d2, s))
    werdykt("miedzy dniami nie ma powtorzonych notek",
            "OK" if not blizniaki else "BLAD",
            "%d par w %d notkach" % (len(blizniaki), len(teksty)))

    # ---------------------------------------------------------------
    print()
    print("=" * 78)
    licz = Counter(s for _, s in WERDYKTY)
    print("PODSUMOWANIE: OK %d, UWAGA %d, BLAD %d"
          % (licz.get("OK", 0), licz.get("UWAGA", 0), licz.get("BLAD", 0)))
    for nazwa, stan in WERDYKTY:
        if stan != "OK":
            print("  %-6s %s" % (stan, nazwa))
    print("=" * 78)
    return 1 if licz.get("BLAD") else 0


if __name__ == "__main__":
    raise SystemExit(main())
