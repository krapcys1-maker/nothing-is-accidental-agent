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
        "SELECT status, stage, note FROM runs WHERE status != 'RUNNING'"
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

# Ile najwyzej dzialan dziennie uznajemy za normalne. Powyzej tego cos sie
# zapetlilo — a konto zbanowane za spam jest nie do odzyskania.
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
    row = conn.execute("SELECT MAX(started_at) AS ostatni FROM runs").fetchone()
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
    """Czy agent nie zapetlil sie i nie zasypuje Substacka."""
    conn = _polaczenie()
    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM calls WHERE date(at) = ? AND purpose IN "
        "('note', 'comment', 'reply')", (dzis,),
    ).fetchone()["n"]
    if n > MAX_DZIALAN_DZIENNIE:
        return (f"Dzis {n} wywolan tworzacych tresc przy suficie "
                f"{MAX_DZIALAN_DZIENNIE}. Cos sie zapetlilo.")
    return None


def koszt() -> str | None:
    conn = _polaczenie()
    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wydane = db.spent_usd(conn, dzis)
    if wydane > config.DAILY_LIMIT_USD * 0.9:
        return (f"Dzis wydane ${wydane:.2f} przy dziennym suficie "
                f"${config.DAILY_LIMIT_USD}.")
    return None


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


def sprawdz_wszystko() -> list[str]:
    """Uruchamia komplet kontroli i alarmuje o tym, co znalazl."""
    kontrole = (
        ("cisza", "Agent milczy", cisza),
        ("zawieszone", "Przebiegi wisialy w RUNNING", zawieszone),
        ("dysk", "Dysk sie konczy", dysk),
        ("nadaktywnosc", "Agent robi za duzo", nadaktywnosc),
        ("koszt", "Koszt blisko sufitu", koszt),
        ("powtorki", "Agent sie powtarza", powtorki),
    )
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

    # Ile reakcji przypada na JEDNO dzialanie danego rodzaju. To jest liczba,
    # ktora mowi, gdzie warto klasc wysilek.
    na_komentarze = sum(int(w.get("ilu") or 0) for w in skutki
                        if str(w.get("typ", "")).startswith("comment"))
    na_notki = sum(int(w.get("ilu") or 0) for w in skutki
                   if str(w.get("typ", "")).startswith("note"))
    ile_kom = sum(1 for w in wystawione if w["rodzaj"] == "komentarz")
    ile_not = sum(1 for w in wystawione if w["rodzaj"] == "notka")
    if ile_kom or ile_not:
        print("\n  zwrot z jednego dzialania:")
        if ile_kom:
            print(f"    komentarz u obcych  {na_komentarze / ile_kom:>5.2f}"
                  f"  ({na_komentarze} reakcji / {ile_kom} komentarzy)")
        if ile_not:
            print(f"    notka na profilu    {na_notki / ile_not:>5.2f}"
                  f"  ({na_notki} reakcji / {ile_not} notek)")

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
