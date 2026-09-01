"""Alarm do właściciela i kontrola zdrowia agenta.

Agent chodzi bez nadzoru, więc cicha awaria jest gorsza od głośnej: gdy sesja
Substacka wygaśnie, a nikt się nie dowie, konto milczy przez tydzień i dopiero
wtedy ktoś zauważa. Ostrzeżenie wypisane na stdout serwera nie dociera do nikogo.

Druga połowa pliku sprawdza rzeczy, których monitoring infrastruktury nie
wykryje. Najgroźniejsza awaria nie polega na tym, że coś padnie — polega na tym,
że WSZYSTKO ŚWIECI NA ZIELONO, a agent milczy od trzech dni albo publikuje
bzdury. Serwer działa, API odpowiada, baza zapisuje, i nikt nie wie.

Alarm jest RZADKI z założenia. Ten sam problem nie zgłasza się częściej niż raz
na dobę, bo kanał, który dzwoni co godzinę, przestaje być czytany po dwóch dniach
— a wtedy jest gorszy niż jego brak.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import config
import db

HISTORIA = config.DATA_DIR / "alarmy.json"
CISZA_GODZIN = 24


def _ustawienia() -> dict[str, str]:
    return {
        "do": os.environ.get("ALARM_EMAIL_TO", "").strip(),
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": os.environ.get("SMTP_PORT", "587").strip(),
        "user": os.environ.get("SMTP_USER", "").strip(),
        # Google pokazuje haslo aplikacji w czterech grupach po cztery znaki
        # i ludzie wklejaja je ze spacjami. Dziala, ale przez przypadek —
        # wycinamy je, zeby nie bylo zagadka za trzy miesiace.
        "haslo": os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip(),
    }


def skonfigurowany() -> bool:
    u = _ustawienia()
    return bool(u["do"] and u["user"] and u["haslo"])


def _ostatnio(klucz: str) -> datetime | None:
    if not HISTORIA.exists():
        return None
    try:
        dane = json.loads(HISTORIA.read_text(encoding="utf-8"))
        return datetime.fromisoformat(dane[klucz])
    except (ValueError, KeyError, OSError):
        return None


def _zapisz(klucz: str) -> None:
    dane = {}
    if HISTORIA.exists():
        try:
            dane = json.loads(HISTORIA.read_text(encoding="utf-8"))
        except ValueError:
            pass
    dane[klucz] = datetime.now(timezone.utc).isoformat()
    HISTORIA.parent.mkdir(parents=True, exist_ok=True)
    HISTORIA.write_text(json.dumps(dane, ensure_ascii=False, indent=1),
                        encoding="utf-8")


def wyslij(klucz: str, temat: str, tresc: str) -> bool:
    """Wysyła alarm. `klucz` identyfikuje RODZAJ problemu, nie pojedynczy wypadek.

    Zwraca True, gdy poszedł. Nigdy nie rzuca wyjątkiem: alarm, który wywala
    agenta, byłby gorszy od problemu, który zgłasza.
    """
    u = _ustawienia()
    if not skonfigurowany():
        print(f"  [alarm NIEWYSLANY — brak konfiguracji] {temat}", flush=True)
        return False

    poprzednio = _ostatnio(klucz)
    if poprzednio and datetime.now(timezone.utc) - poprzednio < timedelta(
            hours=CISZA_GODZIN):
        print(f"  [alarm pominiety — zglaszany w ciagu doby] {temat}", flush=True)
        return False

    wiadomosc = EmailMessage()
    wiadomosc["Subject"] = f"[agent NIA] {temat}"
    wiadomosc["From"] = u["user"]
    wiadomosc["To"] = u["do"]
    wiadomosc.set_content(
        f"{tresc}\n\n--\nagent-v2, {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
        f"serwer: {os.uname().nodename if hasattr(os, 'uname') else 'lokalnie'}\n"
    )
    try:
        with smtplib.SMTP(u["host"], int(u["port"]), timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(u["user"], u["haslo"])
            s.send_message(wiadomosc)
        _zapisz(klucz)
        print(f"  [alarm wyslany] {temat}", flush=True)
        return True
    except Exception as exc:
        print(f"  [alarm NIE POSZEDL: {type(exc).__name__}] {temat}", flush=True)
        return False


def sprawdz_sesje_i_ostrzez() -> None:
    """Pilnuje jedynej rzeczy, która zatrzymuje agenta bez żadnego błędu."""
    import browser

    dni = browser.dni_do_wygasniecia()
    if dni is None:
        wyslij("sesja-brak", "Brak sesji Substacka",
               "Agent nie ma pliku sesji i nie moze nic wystawic.")
    elif dni <= 0:
        wyslij("sesja-wygasla", "Sesja Substacka WYGASLA",
               "Agent nie wystawi juz nic, dopoki nie odnowisz sesji.\n"
               "Zaloguj sie w Chrome na swoim komputerze i wykonaj:\n"
               "  python agent-v2/browser.py sesja\n"
               "a potem skopiuj data/storage-state.json na serwer.")
    elif dni <= browser.OSTRZEGAJ_PONIZEJ_DNI:
        wyslij("sesja-konczy", f"Sesja Substacka wygasa za {dni} dni",
               f"Zostalo {dni} dni. Odnow ja, zanim agent zamilknie.\n"
               "Zaloguj sie w Chrome i wykonaj:\n"
               "  python agent-v2/browser.py sesja")


def sprawdz_przebiegi_i_ostrzez(ile: int = 3) -> None:
    """Alarmuje, gdy agent pada raz za razem.

    Jeden nieudany przebieg to zdarzenie — sieć, dostawca, zły dzień. Trzy pod
    rząd to awaria, która sama nie minie, a bez tego alarmu wyszłaby na jaw
    dopiero wtedy, gdy właściciel zajrzy na konto i zobaczy tydzień ciszy.
    """
    conn = db.connect()
    ostatnie = conn.execute(
        # TYLKO TOR PRODUKCYJNY. Trzy nieudane przebiegi DEWELOPERSKIE
        # wysylaly wlascicielowi „Agent padl 3 razy pod rzad" — a agent
        # dzialal. Kolumna `runs.tryb` istnieje wlasnie po to.
        "SELECT status, stage, note FROM runs"
        " WHERE status != 'RUNNING' AND COALESCE(tryb,'produkcja')='produkcja'"
        " ORDER BY id DESC LIMIT ?", (ile,),
    ).fetchall()
    if len(ostatnie) < ile:
        return
    if all(r["status"] not in ("DONE", "SAVED") for r in ostatnie):
        szczegoly = "\n".join(
            f"  - {r['status']} na etapie {r['stage']}: {(r['note'] or '')[:120]}"
            for r in ostatnie)
        wyslij("przebiegi-pada",
               f"Agent padl {ile} razy pod rzad",
               f"Ostatnie {ile} przebiegow zakonczylo sie bledem:\n\n{szczegoly}\n\n"
               "Zajrzyj na serwer:\n"
               "  journalctl -u nia-agent.service -n 60 --no-pager")


# Ile godzin ciszy uznajemy za awarie. Agent chodzi trzy razy dziennie, wiec
# doba bez sladu znaczy, ze trzy przebiegi z rzedu sie nie odbyly.
CISZA_ALARMOWA_H = 26

# Progi zajetosci dysku. Pelny dysk to najbardziej podstepna awaria VPS-a: baza
# przestaje zapisywac, logi znikaja, a proces dalej "dziala".
DYSK_OSTRZEZENIE = 80
DYSK_ALARM = 92

# Ile najwyzej dzialan na dobe uznajemy za normalne. Powyzej tego cos sie
# zapetlilo — a konto zbanowane za spam jest nie do odzyskania.
#
# LICZYMY TO, CO WYSZLO W SWIAT, nie wywolania modelu. Ban bierze sie z tego,
# co widzi Substack. Na jeden komentarz ida trzy warianty plus sprawdzanie
# faktow: zmierzone 25 sierpnia, 27 wywolan "comment" wobec 4 komentarzy w
# dzienniku — siedmiokrotnosc.
#
# Przy liczeniu wywolan sufit 60 bylby dotykany przez normalna prace (54 w
# oknie 24h tego samego dnia), wiec alarm wylby codziennie i nauczylby nas go
# ignorowac. A realne ryzyko — 60 opublikowanych dzialan — nie bylo mierzone
# wcale.
#
# Suma norm dziennych z configu to okolo 30 dzialan. Sufit 60 jest wiec
# podwojeniem tego, co zaplanowane: dosc luzny, zeby nie krzyczec na dobry
# dzien, i dosc ciasny, zeby zlapac zapetlenie.
MAX_DZIALAN_DZIENNIE = 60


def _polaczenie() -> sqlite3.Connection:
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    return conn


def cisza() -> str | None:
    """Czy agent w ogole cos ostatnio zrobil.

    Awaria, ktorej nie widac: proces umiera, serwer dziala dalej, a nikt sie nie
    dowiaduje przez trzy dni. Sprawdzenie ostatnich przebiegow nic nie da, bo
    przy martwym agencie NOWYCH przebiegow po prostu nie ma.
    """
    conn = _polaczenie()
    # PRZEBIEG TESTOWY NIE JEST DOWODEM, ZE KONTO ZYJE. Bez tego filtru
    # praca nad kodem uciszala alarm o martwym agencie produkcyjnym — a to
    # jedyny alarm, ktory lapie „agent w ogole nie wstal".
    row = conn.execute(
        "SELECT MAX(started_at) AS ostatni FROM runs"
        " WHERE COALESCE(tryb,'produkcja')='produkcja'").fetchone()
    if not row or not row["ostatni"]:
        return "Agent nie ma w bazie ANI JEDNEGO przebiegu."
    try:
        kiedy = datetime.fromisoformat(str(row["ostatni"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    godzin = (datetime.now(timezone.utc) - kiedy).total_seconds() / 3600
    if godzin > CISZA_ALARMOWA_H:
        return (f"Ostatni przebieg byl {godzin:.0f} godzin temu "
                f"({kiedy:%Y-%m-%d %H:%M} UTC). Agent milczy.")
    return None


def zawieszone() -> str | None:
    """Przebiegi, ktore zostaly w stanie RUNNING na zawsze."""
    conn = _polaczenie()
    granica = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    wiszace = conn.execute(
        "SELECT id, started_at FROM runs WHERE status = 'RUNNING' AND started_at < ?",
        (granica,),
    ).fetchall()
    if not wiszace:
        return None
    # Zamykamy je, zeby nie zasmiecaly obrazu — proces i tak juz nie zyje.
    for r in wiszace:
        db.finish_run(conn, r["id"], "STALE",
                      "kontrola", "przebieg wisial ponad trzy godziny")
    return (f"{len(wiszace)} przebiegow wisialo w stanie RUNNING ponad trzy "
            f"godziny — zamkniete jako STALE (id: "
            f"{', '.join(str(r['id']) for r in wiszace[:5])}).")


def dysk() -> str | None:
    uzyte, wolne = 0, 0
    total, used, free = shutil.disk_usage(str(config.DATA_DIR))
    procent = used / total * 100
    if procent >= DYSK_ALARM:
        return (f"Dysk zajety w {procent:.0f}% (wolne {free / 2**30:.1f} GB). "
                "Przy pelnym dysku baza przestanie zapisywac.")
    if procent >= DYSK_OSTRZEZENIE:
        return f"Dysk zajety w {procent:.0f}% — warto posprzatac."
    return None


def nadaktywnosc() -> str | None:
    """Czy agent nie zapetlil sie i nie zasypuje Substacka.

    OKNO KROCZACE 24 GODZIN, nie kalendarzowe "dzisiaj" — i to jest cala
    poprawka, bez ktorej ten straznik byl ozdoba.

    Alarm chodzi o 07:00 UTC. Wszystkie trzy przebiegi agenta (11:20, 19:20,
    23:40 UTC) leza PO nim, wiec o siodmej rano kubelek "dzisiaj" jest pusty
    z definicji. Zmierzone przez audyt: sufit 60 dzialan zostal realnie
    przekroczony dwukrotnie — 141 wywolan 16 sierpnia, 81 siedemnastego — a
    w pliku alarmow nie ma ani jednego wpisu o nadaktywnosci. Jedyny straznik
    miedzy zapetleniem a banem konta nigdy niczego nie zobaczyl.

    Zapetlenie i tak nie respektuje polnocy: przebieg o 23:40, ktory oszalal,
    zasypie Substacka o 00:15 i w kalendarzowym "dzis" bedzie wygladal
    niewinnie.
    """
    import json as _json

    granica = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    # DZIENNIK, NIE BAZA WYWOLAN. Tu stoi to, co naprawde wyszlo na Substacka —
    # patrz uzasadnienie przy MAX_DZIALAN_DZIENNIE.
    plik = config.DATA_DIR / "dziennik.jsonl"
    n = 0
    try:
        for linia in plik.read_text(encoding="utf-8").splitlines():
            linia = linia.strip()
            if not linia:
                continue
            try:
                w = _json.loads(linia)
            except ValueError:
                continue
            if not isinstance(w, dict) or not w.get("udane"):
                continue
            if str(w.get("rodzaj") or "") in ("skutek", ""):
                continue
            if str(w.get("kiedy") or "") >= granica:
                n += 1
    except OSError:
        return None
    if n > MAX_DZIALAN_DZIENNIE:
        return (f"W ostatnich 24 godzinach {n} wywolan tworzacych tresc przy "
                f"suficie {MAX_DZIALAN_DZIENNIE}. Cos sie zapetlilo.")
    return None


def koszt() -> str | None:
    """Czy zblizamy sie do sufitu — dziennego ALBO miesiecznego.

    Sufit miesieczny byl EGZEKWOWANY (`llm._preflight` rzuca BudgetExceeded),
    ale nikt o nim nie ostrzegal. Pierwszym sygnalem bylby wiec agent padajacy
    w polowie przebiegu — w najgorszym razie po oplaceniu researchu i przed
    napisaniem artykulu. Ostrzezenie ma przyjsc, gdy da sie jeszcze cos z tym
    zrobic, a nie w chwili zatrzymania.

    Prog miesieczny jest nizszy niz dzienny (75% wobec 90%), bo miesiac zostaje
    wyczerpany na wiele dni przed koncem i wtedy cisza jest dluga.
    """
    conn = _polaczenie()
    teraz = datetime.now(timezone.utc)
    dzis = teraz.strftime("%Y-%m-%d")

    # DWA DNI OSOBNO, nie tylko dzisiejszy. Alarm chodzi o 07:00 UTC, a
    # przebiegi agenta o 11:20, 19:20 i 23:40 — wiec o siodmej "dzisiaj" jest
    # jeszcze puste i pytanie o nie zawsze odpowiadalo zero.
    #
    # Nie robimy tu okna kroczacego, bo sufit JEST kalendarzowy (`_preflight`
    # liczy wydatki per data). Okno daloby falszywy alarm: dwa dni po 60%
    # sufitu to 120% w oknie, a zaden dzien nie zostal przekroczony.
    wczoraj = (teraz - timedelta(days=1)).strftime("%Y-%m-%d")
    for dzien, opis in ((wczoraj, "Wczoraj"), (dzis, "Dzis")):
        wydane = db.spent_usd(conn, dzien)
        # SUFIT Z TAMTEGO DNIA, NIE Z DZISIAJ. `DAILY_LIMIT_USD` mowi o dzis,
        # a pytamy takze o wczoraj — i wczoraj sufit mogl byc podniesiony na
        # jeden dzien pracy przy wlascicielu. Alarm porownujacy wczorajszy
        # wydatek z dzisiejsza stala doniosl „$7.22 przy suficie $5.0" w dniu,
        # w ktorym obowiazywal sufit dziesieciu dolarow.
        sufit = config.sufit_dnia(dzien)
        if wydane > sufit * 0.9:
            return (f"{opis} wydane ${wydane:.2f} przy dziennym suficie "
                    f"${sufit:.2f}.")
    # OBA TORY, TAK JAK EGZEKWOWANIE. `db.spent_usd` ma `tryb="produkcja"`
    # domyslnie, a `llm._preflight` sumuje produkcje I test:
    #     spent_month = spent_usd(..., "produkcja") + spent_usd(..., "test")
    # Alarm liczacy sam tor produkcyjny mogl wiec MILCZEC do konca: przy
    # suficie 40 USD i 15 USD wydanych na testach `BudgetExceeded` leci przy
    # 25 USD produkcji, a prog alarmu (0,75 x 40 = 30 USD produkcyjnych) nie
    # zostaje osiagniety nigdy. Czyli alarm nie ostrzegal dokladnie przed ta
    # awaria, dla ktorej powstal — „agent padajacy w polowie przebiegu".
    wydane_m = (db.spent_usd(conn, dzis[:7], tryb="produkcja")
                + db.spent_usd(conn, dzis[:7], tryb="test"))
    if wydane_m > config.MONTHLY_LIMIT_USD * 0.75:
        import calendar

        zostalo_dni = calendar.monthrange(teraz.year, teraz.month)[1] - teraz.day
        zostalo_usd = config.MONTHLY_LIMIT_USD - wydane_m
        return (f"W tym miesiacu wydane ${wydane_m:.2f} przy suficie "
                f"${config.MONTHLY_LIMIT_USD}. Zostalo ${zostalo_usd:.2f} "
                f"na {zostalo_dni} dni — po wyczerpaniu agent staje w miejscu, "
                f"w ktorym akurat jest.")
    return None


def wolumeny() -> str | None:
    """Czy agent robi tyle, ile deklaruje — czy tylko wyglada, ze robi.

    NAJTRUDNIEJSZA DO ZAUWAZENIA KLASA AWARII: nic sie nie wywala, log wyglada
    normalnie, przebieg konczy sie `DONE`, a polowa dzialan nie wychodzi.
    Zmierzone przy pisaniu tej kontroli, osiem dni produkcji: notki 58% normy,
    komentarze 55%, restacki 33%. Nikt tego nie wiedzial przez dwa tygodnie,
    bo licznik zyl w pamieci jednego przebiegu i ginal razem z nim.

    Prog jest niski celowo. Budzety sa LOSOWANE z widelek i dzielone na
    przebiegi, wiec wahania kilkunastoprocentowe to normalna praca. Polowa
    normy utrzymujaca sie przez tydzien to nie wahanie, tylko usterka.
    """
    import stages

    dane = stages.podsumowanie_dzialan(7)
    if not dane:
        return None
    slabe = [(r, d) for r, d in dane.items()
             if d["realizacja"] is not None
             and d["realizacja"] < config.PROG_ALARMU_WOLUMENU]
    if not slabe:
        return None
    slabe.sort(key=lambda x: x[1]["realizacja"])
    # LICZBA W MAILU MA BYC TA SAMA, CO W PROGU. Wczesniej prog liczyl sie
    # z `realizacja`, a mianownik w tekscie z `norma * 7` — dwie rozne rzeczy,
    # wiec mail podawal procent niepasujacy do wlasnych liczb w nawiasie.
    opis = ", ".join("%s %d%% (%d z ~%d%s)"
                     % (r, d["realizacja"], d["udane"],
                        round(d.get("oczekiwane") or d["norma"] * 7),
                        "" if d.get("z_planu") else ", wobec normy docelowej")
                     for r, d in slabe)
    return ("Przez ostatnie 7 dni agent zrobil znacznie mniej, niz deklaruje: "
            + opis + ". Nic sie nie wywalilo — to jest ta awaria, ktorej nie "
            "widac w logu.")


def powtorki() -> str | None:
    """Czy agent nie zaczal pisac wciaz tego samego.

    Powtarzanie sie jest objawem, ktorego zaden monitoring infrastruktury nie
    zobaczy: wszystko dziala, a konto zaczyna wygladac na zepsutego bota.
    """
    import stages

    zuzyte = stages.wczytaj_zuzyte()[-30:]
    if len(zuzyte) < 10:
        return None
    klucze = [stages._klucz_faktu(t) for t in zuzyte]
    powtorzone = len(klucze) - len(set(klucze))
    if powtorzone > len(klucze) * 0.2:
        return (f"{powtorzone} z ostatnich {len(klucze)} faktow to powtorki. "
                "Agent zaczyna sie zapetlac tematycznie.")
    return None


def kopia_subskrybentow() -> str | None:
    """Czy istnieje AKTUALNA kopia listy subskrybentow.

    NAJWAZNIEJSZA z tych kontroli i dodana ostatnia, bo brakowalo jej najdluzej.

    Wszystko inne w tym projekcie da sie odtworzyc: teksty, karty dowodowe,
    okladki i cala historia kosztow leza w repozytorium albo powstaja na nowo za
    kilka centow. Lista subskrybentow zyje WYLACZNIE u Substacka, a regulamin
    pozwala zamknac konto natychmiast i w wylacznej ocenie serwisu. Przy tempie
    6-12 subskrypcji miesiecznie sto osob to okolo jedenastu miesiecy pracy.

    Eksportu nie da sie zautomatyzowac — endpoint nie istnieje, a sondowanie
    nieudokumentowanych adresow to dokladnie to, co regulamin nazywa
    scrapingiem. Skoro wiec krok jest RECZNY, musi o nim ktos przypominac,
    inaczej nie zdarzy sie nigdy. I nie zdarzyl sie: katalog `kopie/` nie
    istnial na produkcji przez caly czas dzialania agenta.

    Kontrola ciszy zauwaza milczacego agenta po 26 godzinach. Brak kopii
    subskrybentow nie byl zauwazany przez nic — az do dnia, w ktorym bylaby
    potrzebna.
    """
    katalog = config.DATA_DIR / "kopie"
    if not katalog.exists():
        return ("nie ma ANI JEDNEJ kopii listy subskrybentow (brak katalogu %s). "
                "To jedyne aktywo, ktorego nie da sie odtworzyc. Zrob eksport: "
                "Dashboard -> Subscribers -> Export, plik do %s, potem "
                "`python agent-v2/kopia_subskrybentow.py`" % (katalog, katalog / "przychodzace"))
    kopie = sorted(katalog.glob("subskrybenci-*.csv"))
    if not kopie:
        return ("katalog kopii istnieje, ale jest pusty — zadnej kopii listy "
                "subskrybentow. Patrz `python agent-v2/kopia_subskrybentow.py`")
    from datetime import datetime, timezone

    najnowsza = max(kopie, key=lambda p: p.stat().st_mtime)
    wiek = (datetime.now(timezone.utc)
            - datetime.fromtimestamp(najnowsza.stat().st_mtime, timezone.utc))
    if wiek.days > config.KOPIA_SUBSKRYBENTOW_CO_ILE_DNI:
        return ("ostatnia kopia listy subskrybentow ma %d dni (%s), a prog to %d. "
                "Zrob nowy eksport."
                % (wiek.days, najnowsza.name, config.KOPIA_SUBSKRYBENTOW_CO_ILE_DNI))
    return None


def sprawdz_wszystko() -> list[str]:
    """Uruchamia komplet kontroli i alarmuje o tym, co znalazl."""
    kontrole = (
        ("cisza", "Agent milczy", cisza),
        ("zawieszone", "Przebiegi wisialy w RUNNING", zawieszone),
        ("dysk", "Dysk sie konczy", dysk),
        ("nadaktywnosc", "Agent robi za duzo", nadaktywnosc),
        ("koszt", "Koszt blisko sufitu", koszt),
        ("powtorki", "Agent sie powtarza", powtorki),
        ("wolumeny", "Agent robi mniej, niz deklaruje", wolumeny),
        ("kopia-subskrybentow", "BRAK KOPII LISTY SUBSKRYBENTOW",
         kopia_subskrybentow),
    )
    # TABELA WOLUMENOW DRUKOWANA ZAWSZE, nie tylko gdy cos jest nie tak.
    # Alarm ma odpowiadac na pytanie „ile wyszlo", a nie tylko krzyczec, gdy
    # jest zle — inaczej cisza znaczy „albo dobrze, albo kontrola nie dziala".
    try:
        import stages

        dane = stages.podsumowanie_dzialan(7)
        if dane:
            print("--- co wyszlo przez 7 dni ---")
            for rodzaj, d in dane.items():
                norma = ("  norma ~%.1f/dzien -> %s%%"
                         % (d["norma"], d["realizacja"])) if d["realizacja"] is not None else ""
                nieud = ("  nieudanych %d" % d["nieudane"]) if d["nieudane"] else ""
                print("  %-12s %4d   %.2f/dzien%s%s"
                      % (rodzaj, d["udane"], d["na_dzien"], norma, nieud))
            powody = stages.powody_porazek(7)
            if powody:
                print("--- dlaczego sie nie udalo ---")
                for rodzaj, powod, ile in powody[:8]:
                    print("  %-12s %3dx  %s" % (rodzaj, ile, powod))
            print()
    except Exception as exc:
        print("  (nie policzylem wolumenow: %s)" % type(exc).__name__)

    znalezione: list[str] = []
    for klucz, temat, funkcja in kontrole:
        try:
            wynik = funkcja()
        except Exception as exc:
            wynik = f"kontrola sama padla: {type(exc).__name__}: {exc}"
        if wynik:
            znalezione.append(f"[{klucz}] {wynik}")
            wyslij(f"kontrola-{klucz}", temat, wynik)
            print(f"  ! {klucz}: {wynik}", flush=True)
        else:
            print(f"  ok {klucz}", flush=True)
    return znalezione



def przeglad(dni: int = 3) -> None:
    """Co agent NAPRAWDE zrobil przez ostatnie dni i gdzie sie pomylil.

    Do tej pory dalo sie sprawdzic, ile kosztowalo myslenie, ale nie CO z tego
    poszlo w swiat. A po dwoch dniach to jedyne pytanie, ktore ma znaczenie.
    Ten przeglad czyta dziennik dzialan i baze, i pokazuje jedno obok drugiego.
    """
    import collections
    import json as _json

    import browser

    granica = datetime.now(timezone.utc) - timedelta(days=dni)
    wpisy = []
    if browser.DZIENNIK.exists():
        for linia in browser.DZIENNIK.read_text(encoding="utf-8").splitlines():
            try:
                w = _json.loads(linia)
                if datetime.fromisoformat(w["kiedy"]) >= granica:
                    wpisy.append(w)
            except (ValueError, KeyError):
                continue

    print(f"\n=== CO AGENT ZROBIL PRZEZ {dni} DNI ===")
    if not wpisy:
        print("  dziennik pusty — albo agent nic nie robil, albo nie dziala")
    licznik = collections.Counter(w["rodzaj"] for w in wpisy)
    nieudane = [w for w in wpisy if not w.get("udane")]
    for rodzaj, ile in licznik.most_common():
        zle = sum(1 for w in nieudane if w["rodzaj"] == rodzaj)
        print(f"  {rodzaj:<24} {ile:>3}" + (f"   NIEUDANYCH: {zle}" if zle else ""))

    if nieudane:
        print(f"\n=== CO SIE NIE UDALO ({len(nieudane)}) ===")
        for w in nieudane[:10]:
            print(f"  {w['kiedy'][5:16]}  {w['rodzaj']:<20} {str(w.get('gdzie') or w.get('komu') or '')[:44]}")

    # dlugosci: czy nie robimy wszystkiego w jednym rozmiarze
    dlugosci = [w["slow"] for w in wpisy if isinstance(w.get("slow"), int)]
    if len(dlugosci) >= 3:
        import statistics
        print("\n=== DLUGOSCI WYPOWIEDZI ===")
        print(f"  od {min(dlugosci)} do {max(dlugosci)} slow, "
              f"srednia {statistics.mean(dlugosci):.0f}, "
              f"odchylenie {statistics.pstdev(dlugosci):.0f}")
        if statistics.pstdev(dlugosci) < 8:
            print("  ! ZA ROWNO — jednolita dlugosc to jeden z tropow bota")

    # gdzie komentowalismy: czy nie u tych samych
    gdzie = [w.get("gdzie", "") for w in wpisy if w["rodzaj"] == "komentarz"]
    if gdzie:
        from urllib.parse import urlparse
        hosty = collections.Counter(urlparse(g).netloc for g in gdzie if g)
        print(f"\n=== GDZIE KOMENTOWALISMY ===")
        for h, n in hosty.most_common(8):
            print(f"  {n}x  {h}" + ("   ! WIECEJ NIZ RAZ" if n > 1 else ""))

    conn = _polaczenie()
    od = granica.strftime("%Y-%m-%d")
    koszt = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) k, COUNT(*) n FROM calls WHERE date(at) >= ?",
        (od,)).fetchone()
    padly = conn.execute(
        "SELECT COUNT(*) n FROM runs WHERE status NOT IN ('DONE','SAVED')"
        " AND started_at >= ?", (granica.isoformat(),)).fetchone()["n"]
    print(f"\n=== KOSZT I PRZEBIEGI ===")
    print(f"  wywolan modeli: {koszt['n']}   koszt: ${koszt['k']:.4f}")
    print(f"  przebiegow zakonczonych bledem: {padly}")

    _co_z_tego_wyszlo(wpisy)


def _co_z_tego_wyszlo(wpisy: list[dict]) -> None:
    """Czy nasze dzialania w ogole wracaja — i ktore z nich.

    Sam licznik wystawionych tresci nie mowi nic o tym, czy warto bylo. Te
    zestawienia odpowiadaja na trzy pytania, ktorych dotad nikt nie mogl zadac:
    co wraca czesciej, notka czy komentarz; czy oplaca sie byc wczesnie; i ktore
    hasla wyszukiwania przynosza rozmowy zamiast ciszy.
    """
    import collections
    import statistics

    skutki = [w for w in wpisy if w.get("rodzaj") == "skutek"]
    wystawione = [w for w in wpisy
                  if w.get("rodzaj") in ("komentarz", "notka", "odpowiedz")
                  and w.get("udane")]
    if not skutki and not wystawione:
        return

    print("\n=== CO Z TEGO WYSZLO ===")
    if not skutki:
        print("  brak zapisanych reakcji — albo ich nie bylo, albo dziennik"
              " jeszcze ich nie zbieral")
    else:
        ile_osob = sum(int(w.get("ilu") or 0) for w in skutki)
        print(f"  reakcji: {len(skutki)} zdarzen, {ile_osob} osob")
        for typ, n in collections.Counter(w.get("typ") for w in skutki).most_common():
            print(f"    {typ:<16} {n}")

    # ODPOWIEDZI OSOBNO OD POLUBIEN, i to odpowiedzi sa naglowkiem.
    #
    # Powod nie jest estetyczny. Jesli jedyna miara sukcesu jest suma reakcji,
    # a polubien jest zawsze wielokrotnie wiecej niz odpowiedzi, to kazda
    # decyzja opierana na tej liczbie przesuwa pismo w strone tego, co zbiera
    # polubienia — czyli w strone szoku. Publikacja o tym, dlaczego zwykle
    # rzeczy sa takie, jakie sa, przegralaby sama ze soba w kilka miesiecy.
    #
    # Odpowiedz znaczy, ze ktos poswiecil czas. Polubienie znaczy, ze ktos
    # przewinal i kliknal. To sa rozne zdarzenia i nie wolno ich sumowac.
    def _ilu(warunek) -> int:
        return sum(int(w.get("ilu") or 0) for w in skutki if warunek(str(w.get("typ", ""))))

    odp_kom = _ilu(lambda t: t == "comment_reply")
    odp_not = _ilu(lambda t: t == "note_reply")
    lajk_kom = _ilu(lambda t: t == "comment_like")
    lajk_not = _ilu(lambda t: t in ("note_like", "note_restack"))
    ile_kom = sum(1 for w in wystawione if w["rodzaj"] == "komentarz")
    ile_not = sum(1 for w in wystawione if w["rodzaj"] == "notka")
    if ile_kom or ile_not:
        print("\n  ODPOWIEDZI na jedno dzialanie — to jest miara, ktora sie liczy:")
        if ile_kom:
            print(f"    komentarz u obcych  {odp_kom / ile_kom:>5.2f}"
                  f"  ({odp_kom} odpowiedzi / {ile_kom} komentarzy)")
        if ile_not:
            print(f"    notka na profilu    {odp_not / ile_not:>5.2f}"
                  f"  ({odp_not} odpowiedzi / {ile_not} notek)")
        print("\n  polubienia (osobno — NIE laczyc z powyzszym):")
        if ile_kom:
            print(f"    komentarz u obcych  {lajk_kom / ile_kom:>5.2f}")
        if ile_not:
            print(f"    notka na profilu    {lajk_not / ile_not:>5.2f}")
        laczna_odp, laczne_lajki = odp_kom + odp_not, lajk_kom + lajk_not
        if laczne_lajki and laczna_odp:
            print(f"\n    na jedna odpowiedz przypada {laczne_lajki / laczna_odp:.1f}"
                  " polubien — dlatego suma reakcji to miara polubien, nie rozmowy")
        elif laczne_lajki and not laczna_odp:
            print(f"\n    ! {laczne_lajki} polubien i ZERO odpowiedzi — tresci sa"
                  " przyjmowane, ale nie zaczepiaja nikogo do rozmowy")

    # CZY OPLACA SIE BYC WCZESNIE. Pod tekstem ze 126 komentarzami nasza uwaga
    # jest niewidoczna — ale to trzeba pokazac liczbami, a nie twierdzic.
    odpowiedzialy = {w.get("czego") for w in skutki if w.get("czego")}
    z_pozycja = [w for w in wpisy if w.get("rodzaj") == "komentarz"
                 and w.get("udane") and isinstance(w.get("komentarzy_przed"), int)]
    if z_pozycja:
        wczesnie = [w for w in z_pozycja
                    if w["komentarzy_przed"] <= config.KOMFORTOWO_KOMENTARZY]
        pozno = [w for w in z_pozycja
                 if w["komentarzy_przed"] > config.KOMFORTOWO_KOMENTARZY]
        print("\n  czy oplaca sie byc wczesnie:")
        for nazwa, grupa in (("wczesnie (<=%s)" % config.KOMFORTOWO_KOMENTARZY, wczesnie),
                             ("w tloku", pozno)):
            if not grupa:
                continue
            wrocilo = sum(1 for w in grupa if w.get("nasz_id") in odpowiedzialy)
            print(f"    {nazwa:<18} {len(grupa):>3} komentarzy, wrocilo {wrocilo}"
                  f"  ({100 * wrocilo / len(grupa):.0f}%)")
        sr = statistics.mean(w["komentarzy_przed"] for w in z_pozycja)
        print(f"    srednio bylo przed nami {sr:.0f} komentarzy")

    # KTORE HASLA PRZYNOSZA ROZMOWY. Osiemnascie hasel, a nie wiemy, ktore dzialaja.
    wg_hasla: dict[str, list[int]] = collections.defaultdict(list)
    for w in wpisy:
        if w.get("rodzaj") != "komentarz" or not w.get("udane"):
            continue
        wg_hasla[str(w.get("skad") or "?")].append(
            1 if w.get("nasz_id") in odpowiedzialy else 0)
    if len(wg_hasla) > 1:
        print("\n  skad przyszedl cel, ktory odpowiedzial:")
        for skad, wyniki in sorted(wg_hasla.items(),
                                   key=lambda kv: -sum(kv[1])):
            print(f"    {skad[:44]:<44} {sum(wyniki)}/{len(wyniki)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "przeglad":
        przeglad(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        print("skonfigurowany:", skonfigurowany())
        wyslij("test", "Test kanalu alarmowego",
               "Jesli to czytasz, alarmy dochodza.")
    else:
        sprawdz_sesje_i_ostrzez()
        sprawdz_przebiegi_i_ostrzez()
        print("--- kontrola zdrowia ---", flush=True)
        sprawdz_wszystko()
