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
    udane = Counter(w.get("rodzaj") for w in po_pivocie if w.get("udane"))
    nieudane = Counter(w.get("rodzaj") for w in po_pivocie if not w.get("udane"))
    for rodzaj in sorted(set(udane) | set(nieudane)):
        print("    %-12s udane %3d, nieudane %2d"
              % (rodzaj, udane.get(rodzaj, 0), nieudane.get(rodzaj, 0)))
    # KAZDY RODZAJ MA WYCHODZIC. Rodzaj, ktorego nie ma ani razu, to albo
    # martwa galaz, albo cichy blad — jedno i drugie warto zobaczyc.
    for rodzaj in ("notka", "komentarz", "odpowiedz", "polubienie",
                   "restack", "subskrypcja"):
        werdykt("wychodzi: %s" % rodzaj,
                "OK" if udane.get(rodzaj) else "UWAGA",
                "%d od %s" % (udane.get(rodzaj, 0), PIVOT))
    # OBSERWACJE. Przycisku „Follow" na Substacku nie da sie dosiegnac
    # z naszej sesji — to ustalenie, nie usterka. Melduje jako UWAGE, zeby
    # nie zniknelo z pola widzenia, ale nie jako BLAD.
    werdykt("obserwacje (follow) — znane ograniczenie",
            "OK" if udane.get("obserwacja") else "UWAGA",
            "%d prob; brak przycisku w sesji" % udane.get("obserwacja", 0))
    if nieudane:
        naj = nieudane.most_common(3)
        werdykt("porazki nie dominuja",
                "OK" if sum(nieudane.values()) < sum(udane.values()) / 2 else "UWAGA",
                ", ".join("%s %d" % (r, i) for r, i in naj))

    # ---------------------------------------------------------------
    etap(2, "NORMA — plan wobec wykonania, dzien po dniu")
    dni = defaultdict(Counter)
    for w in po_pivocie:
        if w.get("udane"):
            dni[dzien(w)][str(w.get("rodzaj"))] += 1
    for d in sorted(dni)[-7:]:
        print("    %s  %s" % (d, "  ".join(
            "%s %d" % (r, i) for r, i in sorted(dni[d].items())
            if r in ("notka", "komentarz", "odpowiedz", "polubienie",
                     "restack", "subskrypcja"))))
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
            for rodzaj in ("notka", "komentarz", "polubienie", "restack"):
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
    etap(7, "PROMOCJA I PAMIEC — czy nic sie nie starzeje w cichosci")
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
