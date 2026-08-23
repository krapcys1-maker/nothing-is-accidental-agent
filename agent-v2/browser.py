"""Czytanie stron przeglądarką — tam, gdzie zwykły HTTP nie wystarcza.

Substack renderuje treść JavaScriptem: w HTML-u jest 148 KB, a czytelnego
tekstu 371 znaków, bo post siedzi w blobie JSON. Zwykły pobieracz zobaczy
pustą skorupę.

Czytamy WYŁĄCZNIE publiczne strony, bez logowania i bez sesji. Agent otwiera
je tak jak każdy czytelnik. Publikowanie, komentowanie i polubienia nie
istnieją w tym pliku i nie powstaną bez osobnej decyzji właściciela.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import config

READ_TIMEOUT_MS = 45_000
SETTLE_MS = 2_500

# Plik sesji. Powstaje, gdy WŁAŚCICIEL zaloguje się własnoręcznie w otwartym
# oknie. Hasło nie przechodzi przez ten kod ani przez nic, co ja czytam.
# `.gitignore` obejmuje ten wzorzec od początku projektu.
SESSION_FILE = config.DATA_DIR / "storage-state.json"


CDP_PORT = 9222

# Ciasteczko realnej sesji Substacka. `substack.lli` to tylko podpowiedź
# "kiedyś tu byłeś" i ustawia się także anonimowo — pierwsza wersja kontroli
# opierała się na tekście strony, publiczna strona główna ją przechodziła
# i skrypt zapisał pustą sesję jako zalogowaną.
SESSION_COOKIE = "substack.sid"


# Ile dni przed wygaśnięciem sesji zaczynamy ostrzegać. Ciasteczko żyje ~90 dni,
# więc dwa tygodnie to spokojny zapas na to, żeby właściciel zdążył zareagować.
OSTRZEGAJ_PONIZEJ_DNI = 14


def wlasciwe_konto(page) -> bool:
    """Czy jestesmy na WLASCIWYM koncie tuz przed publikacja.

    Automatyzacja przegladarki potrafi trafic w cudze okno albo w sesje sprzed
    przelogowania. Tresc opublikowana z niewlasciwego konta jest bledem, ktorego
    nie da sie cofnac w oczach tych, ktorzy ja zobaczyli — wiec pytamy o
    tozsamosc, zamiast zakladac.
    """
    kto = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
    ok = isinstance(kto, dict) and kto.get("handle") == PROFIL_HANDLE
    if not ok:
        print(f"  ! NIE TO KONTO albo brak sesji: {str(kto)[:80]}", flush=True)
    return ok


DZIENNIK = config.DATA_DIR / "dziennik.jsonl"


def dopisz_wynik(rodzaj: str, wynik: dict, **szczegoly) -> None:
    """Jeden wpis na dzialanie — takze wtedy, gdy sie NIE UDALO, i z powodem.

    DWIE DZIURY NARAZ, obie groznie ciche.

    Pierwsza: wpis do dziennika stal WEWNATRZ `try`, a wyjatek byl lapany
    nizej. Akcja, ktora wywalila sie bledem, nie zostawiala w dzienniku
    ZADNEGO sladu — nie wiedzielismy nie tylko dlaczego, ale i ze w ogole
    byla. Licznik wolumenow liczylby wiec z danych, ktore same gubia porazki.

    Druga: gdy nie znalezlismy przycisku wysylki, kod nie wchodzil w zadna
    galez i przechodzil dalej w milczeniu. To najczestsza realna awaria przy
    obcym interfejsie i akurat ona nie zostawiala niczego.

    Zapis jest IDEMPOTENTNY: pierwszy, ktory zdazy, wygrywa. Dzieki temu
    sciezka sukcesu zapisuje szczegoly, a `finally` domyka tylko te przebiegi,
    ktore do niej nie doszly.
    """
    if wynik.get("_zapisane"):
        return
    wynik["_zapisane"] = True
    udane = bool(wynik.get("wyslane") or wynik.get("zrobione"))
    if not udane:
        szczegoly["powod"] = (
            wynik.get("blad")
            or ("nie znalazlem przycisku wysylki"
                if wynik.get("przycisk_widoczny") is False else "")
            or "Substack nie potwierdzil, ze wyszlo")
    zapisz_w_dzienniku(rodzaj, udane=udane, **szczegoly)


def zapisz_w_dzienniku(rodzaj: str, **szczegoly) -> None:
    """Dziennik DZIALAN, nie wywolan modelu.

    Baza zapisuje, ile kosztowalo mysleenie. Nie zapisuje, CO z tego poszlo
    w swiat, do kogo i czy sie udalo — a po dwoch dniach to jest jedyne pytanie,
    ktore ma znaczenie: gdzie agent sie pomylil i co poprawic.

    Jeden wiersz na dzialanie, w pliku, ktory da sie czytac oczami i skryptem.
    Nigdy nie przerywa dzialania: dziennik, ktory wywala agenta, byl by gorszy
    od jego braku.
    """
    import json as _json
    from datetime import datetime, timezone

    try:
        wpis = {"kiedy": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rodzaj": rodzaj, **szczegoly}
        DZIENNIK.parent.mkdir(parents=True, exist_ok=True)
        with open(DZIENNIK, "a", encoding="utf-8") as f:
            f.write(_json.dumps(wpis, ensure_ascii=False) + "\n")
    except Exception:
        pass


def z_dziennika_dzis() -> dict[str, int]:
    """Ile komentarzy i polubien poszlo dzis — wedlug naszego zapisu.

    Notki potrafimy policzyc u zrodla, komentarzy i polubien NIE. Kanal profilu
    zwraca wylacznie notki — sprawdzone na zywo: jedenascie pozycji, ani jednej
    z `post_id` — a szesc innych endpointow naszych komentarzy nie oddaje wcale.

    To swiadomy wyjatek od zasady „rzeczywistosc jest zrodlem prawdy", zrobiony
    tam, gdzie rzeczywistosci nie da sie zapytac. Bez niego kazdy przebieg widzial
    zero i bral pelny dzienny budzet od nowa, wiec ochrona przed wystawieniem
    normy drugi raz dzialala TYLKO dla notek. Dziennik przezywa restart, wiec
    daje te sama gwarancje tam, gdzie Substack milczy.

    Liczymy wylacznie dzialania UDANE i wylacznie dzisiejsze, w UTC — tak samo
    jak liczy je `ile_dzis_wystawione`, zeby obie polowy licznika mierzyly ten
    sam dzien.
    """
    import json as _json
    from datetime import datetime, timezone

    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ile = {"komentarze": 0, "lajki": 0, "restacki": 0}
    nazwa = {"komentarz": "komentarze", "polubienie": "lajki",
             "restack": "restacki"}
    try:
        if not DZIENNIK.exists():
            return ile
        for linia in DZIENNIK.read_text(encoding="utf-8").splitlines():
            linia = linia.strip()
            if not linia:
                continue
            try:
                wpis = _json.loads(linia)
            except ValueError:
                continue          # jedna uszkodzona linia nie psuje calej reszty
            if not isinstance(wpis, dict):
                continue
            if not str(wpis.get("kiedy", "")).startswith(dzis):
                continue
            if not wpis.get("udane"):
                continue
            klucz = nazwa.get(wpis.get("rodzaj"))
            if klucz:
                ile[klucz] += 1
    except Exception:
        pass                      # licznik nie moze zatrzymac przebiegu
    return ile


def naprawde_wyslac(wyslij: bool, co: str) -> bool:
    """Ostatnie sito przed KAZDYM dzialaniem widocznym publicznie.

    DRY_RUN blokowal wywolania modeli, ale NIE blokowal przegladarki — wiec
    przebieg "na sucho" na serwerze nie napisal ani slowa, a mimo to polubil
    dwa cudze posty. Tryb, ktory nazywa sie suchym, musi byc suchy takze wobec
    swiata zewnetrznego, inaczej jest pulapka.
    """
    if wyslij and config.DRY_RUN:
        print(f"  [{co}] DRY_RUN — NIE wysylam, mimo ze proszono", flush=True)
        return False
    return wyslij


def zalogowany(context) -> bool:
    """Twarde sprawdzenie: albo jest ciasteczko sesji, albo go nie ma."""
    return any(c.get("name") == SESSION_COOKIE for c in context.cookies())


def dni_do_wygasniecia() -> int | None:
    """Ile dni zostało sesji. None, gdy sesji nie ma wcale."""
    import datetime
    import json

    if not SESSION_FILE.exists():
        return None
    dane = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    for ciastko in dane.get("cookies", []):
        if ciastko.get("name") != SESSION_COOKIE:
            continue
        koniec = ciastko.get("expires", -1)
        if not koniec or koniec < 0:
            return 0
        wygasa = datetime.datetime.fromtimestamp(koniec, datetime.timezone.utc)
        return (wygasa - datetime.datetime.now(datetime.timezone.utc)).days
    return None


def wymagaj_sesji() -> None:
    """Sprawdza sesję przed pracą i mówi wprost, gdy trzeba się zalogować.

    Agent chodzi bez nadzoru, więc cicha awaria na wygasłej sesji byłaby
    najgorszym wariantem: przez tydzień nic by nie wychodziło, a log milczał.
    """
    dni = dni_do_wygasniecia()
    if dni is None:
        raise SystemExit(
            "Brak sesji Substacka.\n"
            "Uruchom Chrome z portem debugowania, zaloguj się i wykonaj:\n"
            "  python agent-v2/browser.py sesja"
        )
    if dni <= 0:
        raise SystemExit(
            f"Sesja Substacka wygasła. Zaloguj się ponownie i wykonaj:\n"
            "  python agent-v2/browser.py sesja"
        )
    if dni <= OSTRZEGAJ_PONIZEJ_DNI:
        print(
            f"  [uwaga] sesja Substacka wygasa za {dni} dni — warto odnowić",
            flush=True,
        )


CHROME_PROFILE = Path.home() / "substack-agent-chrome"
CHROME_SCIEZKI = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path("/usr/bin/google-chrome"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
)


def _chrome_odpowiada() -> bool:
    import httpx

    try:
        httpx.get(f"http://localhost:{CDP_PORT}/json/version", timeout=3)
        return True
    except Exception:
        return False


def uruchom_chrome() -> bool:
    """Otwiera Chrome na trwałym profilu agenta, jeśli jeszcze nie działa.

    Trwały profil znaczy, że logowanie przeżywa restarty — po pierwszym razie
    właściciel nie zobaczy już formularza logowania ani CAPTCHY.

    Chrome jest uruchamiany zwykłym poleceniem, BEZ flag automatyzacji. To jest
    istotne: gdy przeglądarkę startował Playwright, reCAPTCHA zapętlała się
    nawet dla człowieka.
    """
    import subprocess

    if _chrome_odpowiada():
        return True
    exe = next((s for s in CHROME_SCIEZKI if s.exists()), None)
    if exe is None:
        print("  Nie znalazłem Chrome. Uruchom go sam z portem "
              f"--remote-debugging-port={CDP_PORT}", flush=True)
        return False
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [str(exe), f"--remote-debugging-port={CDP_PORT}",
         f"--user-data-dir={CHROME_PROFILE}", "https://substack.com/home"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(1)
        if _chrome_odpowiada():
            return True
    return False


def rozgrzej(context) -> bool:
    """Pozwala Cloudflare wydać zgodę dla adresu, z którego akurat działamy.

    Z centrum danych pierwsze wejście dostaje stronę "Just a moment…", bo
    `cf_clearance` z sesji właściciela było wydane na jego domowy adres. To NIE
    jest obchodzenie zabezpieczenia — przeciwnie, wchodzimy wprost na chroniony
    adres i pozwalamy wyzwaniu zrobić swoje. Prawdziwa przeglądarka rozwiązuje
    je w kilka sekund i dostaje własną zgodę.

    Bez tego kroku z serwera nie działa nic; z nim działa kompozytor i wejścia
    na adresy API.
    """
    page = context.new_page()
    try:
        page.goto(f"https://substack.com/api/v1/user/{config.SUBSTACK_HANDLE}"
                  "/public_profile",
                  timeout=READ_TIMEOUT_MS * 2, wait_until="domcontentloaded")
        for _ in range(8):
            page.wait_for_timeout(3000)
            if "Just a moment" not in page.inner_text("body")[:60]:
                return True
        print("  [rozgrzewka] Cloudflare nie ustąpił", flush=True)
        return False
    except Exception as exc:
        print(f"  [rozgrzewka] {type(exc).__name__}: {exc}"[:120], flush=True)
        return False
    finally:
        page.close()


def api_json(page, sciezka: str, baza: str | None = None) -> Any:
    """Czyta API WCHODZĄC na adres, zamiast wołać `fetch` ze strony.

    Sprawdzone na serwerze: z centrum danych `fetch` z wnętrza strony wraca 403
    ze stroną wyzwania, a zwykłe wejście na ten sam adres oddaje JSON. Różnica
    jest w tym, jak Cloudflare ocenia zapytanie w tle wobec nawigacji.

    Działa tak samo na komputerze właściciela, więc mamy jedną drogę, nie dwie.
    """
    import json as _json

    # Adresy dziela sie na dwa swiaty i pomylenie ich daje bledy trudne do
    # zdiagnozowania: /api/v1/posts nalezy do PUBLIKACJI
    # (nothingisaccidental.substack.com), a /api/v1/reader/* i /api/v1/user/*
    # do serwisu (substack.com). Potwierdzanie artykulu pytalo pod zlym adresem
    # i zawsze odpowiadalo "nie ma", wiec udana publikacja raportowalaby porazke.
    #   - substack.com          : /api/v1/reader/*, /api/v1/user/*
    #   - NASZA publikacja       : /api/v1/posts (lista naszych artykulow)
    #   - CUDZA publikacja       : /api/v1/posts/<slug>, /api/v1/post/<id>/comments
    # Dlatego adres bazowy jest jawnym argumentem, a nie domyslem. Poprzednia
    # wersja zawsze pytala substack.com i cicho zwracala "nie znalazlem".
    baza = baza or "https://substack.com"
    page.goto(f"{baza}{sciezka}", timeout=READ_TIMEOUT_MS * 2,
              wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    tekst = page.inner_text("body").strip()
    if tekst.startswith("Just a moment"):
        page.wait_for_timeout(6000)
        tekst = page.inner_text("body").strip()
    try:
        return _json.loads(tekst)
    except ValueError:
        return None


def podlacz_sie():
    """Podłącza się do Chrome'a, którego uruchomił i zalogował WŁAŚCICIEL.

    Dlaczego tak, a nie przez uruchomienie przeglądarki przez Playwrighta:
    Playwright startuje Chrome z flagami automatyzacji, a reCAPTCHA ocenia całą
    sesję, nie samo kliknięcie — więc odrzuca ją niezależnie od tego, kto klika.
    Właściciel nie mógł przejść CAPTCHY, mimo że jest człowiekiem.

    Tutaj przeglądarkę uruchamia człowiek i człowiek się loguje. W momencie
    przechodzenia CAPTCHY to jest zwykły Chrome — nic nie jest ukrywane ani
    podszywane. Agent podłącza się do gotowej, zalogowanej sesji.
    """
    from playwright.sync_api import sync_playwright

    # NA SERWERZE PODŁĄCZAMY SIĘ DO PRAWDZIWEGO CHROME'A, tak samo jak na
    # komputerze właściciela. Chrome chodzi tam na wirtualnym ekranie jako usługa
    # `nia-chrome`, a właściciel zalogował się w nim własnoręcznie.
    #
    # Dlaczego nie przeglądarka bezgłowa: sprawdzone na żywo tego samego wieczoru.
    # Ta sama sesja, ten sam adres, ten sam serwer — publikacja przez prawdziwego
    # Chrome'a kończy się kodem 200, a przez bezgłowego Chromium notka po prostu
    # nie powstaje. Cloudflare rozpoznaje tryb bezgłowy po odcisku przeglądarki.
    if config.TRYB_SERWERA and _chrome_odpowiada():
        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return p, browser, context

    if config.TRYB_SERWERA or not _chrome_odpowiada():
        if not SESSION_FILE.exists():
            raise SystemExit(
                "Tryb serwerowy wymaga pliku sesji.\n"
                f"Skopiuj na serwer: {SESSION_FILE}"
            )
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            storage_state=str(SESSION_FILE),
            user_agent=config.FETCH_USER_AGENT,
            viewport={"width": 1440, "height": 900},
            locale="en-US",   # interfejs po angielsku, niezależnie od serwera
        )
        rozgrzej(context)
        return p, browser, context

    if not _chrome_odpowiada():
        print("  Chrome nie działa — otwieram go na profilu agenta.", flush=True)
        if not uruchom_chrome():
            raise SystemExit("Nie udało się otworzyć Chrome'a.")

    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    except Exception as exc:
        p.stop()
        raise SystemExit(
            f"Chrome działa, ale nie mogę się podłączyć ({type(exc).__name__})."
        ) from exc
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return p, browser, context


def sprawdz_sesje() -> None:
    """Czy Chrome właściciela jest zalogowany i co agent w nim widzi."""
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        # USUNIETO 2026-08-20 blok wklejony tu omylkowo z `wystaw_notke`.
        # Odwolywal sie do `wyslij`, `tekst` i `wynik`, ktore w tej funkcji nie
        # istnieja, wiec `python agent-v2/browser.py sesja` konczylo sie
        # NameError przy pierwszej linii `try`.
        #
        # To nie byla usterka kosmetyczna: TA WLASNIE KOMENDA jest cytowana
        # w alarmie wysylanym do wlasciciela, gdy sesja wygasa. Procedura
        # ratunkowa nie dzialala, a dowiedzielibysmy sie o tym dopiero
        # w chwili, gdy naprawde bylaby potrzebna.
        page.goto("https://substack.com/home", timeout=READ_TIMEOUT_MS,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS)
        text = page.inner_text("body")
        zalogowany = "sign in" not in text.lower()[:300] and len(text) > 1200
        print(f"  sesja: {'ZALOGOWANA' if zalogowany else 'NIEZALOGOWANA'}"
              f"   tekst={len(text)} znaków")
        if zalogowany:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(SESSION_FILE))
            dni = dni_do_wygasniecia()
            print(f"  stan sesji zapisany: {SESSION_FILE}")
            if dni is not None:
                print(f"  wazna jeszcze {dni} dni")
    finally:
        page.close()
        browser.close()
        p.stop()


def sprawdz_serwer() -> None:
    """Odpowiada na JEDNO pytanie: czy zapisana sesja żyje z adresu tego serwera.

    Niczego nie publikuje, nie polubia i nie zmienia. Sam odczyt, bo to pytanie
    trzeba rozstrzygnąć ZANIM zbudujemy na nim resztę: jeśli Substack odrzuca
    sesję z innego adresu, cała droga przez przeglądarkę wymaga przemyślenia od
    nowa i lepiej wiedzieć to teraz niż po tygodniu pracy.
    """
    import os

    os.environ["AGENT_V2_SERVER"] = "1"
    config.TRYB_SERWERA = True

    dni = dni_do_wygasniecia()
    print(f"  plik sesji: {'jest' if SESSION_FILE.exists() else 'BRAK'}"
          f"{f', wazna {dni} dni' if dni is not None else ''}", flush=True)

    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        page.goto("https://substack.com/", timeout=READ_TIMEOUT_MS * 2,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 3000)
        ciastko = zalogowany(context)
        print(f"  ciasteczko sesji: {'JEST' if ciastko else 'BRAK'}", flush=True)

        # Twardszy dowód niż ciasteczko: czy zalogowane API nas rozpoznaje.
        kto = api_json(page, f"/api/v1/user/{config.SUBSTACK_HANDLE}/public_profile")
        print(f"  odpowiedz API: {kto if not isinstance(kto, dict) else {k: kto.get(k) for k in ('id', 'name')}}",
              flush=True)
        page.goto("https://substack.com/", timeout=READ_TIMEOUT_MS * 2,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 3000)

        widzi_kompozytor = "on your mind" in page.inner_text("body").lower()
        print(f"  kompozytor notek widoczny: {widzi_kompozytor}", flush=True)

        if ciastko and isinstance(kto, dict) and kto.get("id") and widzi_kompozytor:
            print("\n  WYNIK: sesja dziala z tego adresu. Mozna isc dalej.", flush=True)
        else:
            print("\n  WYNIK: sesja NIE dziala stad. NIE budujemy dalej na tej"
                  " drodze — trzeba przemyslec logowanie na serwerze.", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()


def zaloguj() -> None:
    """Otwiera prawdziwe okno przeglądarki i czeka, aż właściciel się zaloguje.

    Substack loguje magicznym linkiem na e-mail, więc i tak musi to zrobić
    człowiek — agent na serwerze nie ma dostępu do skrzynki. Po zalogowaniu
    zapisujemy stan sesji do pliku i od tej pory agent otwiera przeglądarkę
    już zalogowaną.
    """
    from playwright.sync_api import sync_playwright

    print("Otwieram okno przeglądarki. Zaloguj się na Substacku.")
    print("Gdy zobaczysz swoje konto, wróć tutaj i naciśnij Enter.\n")
    with sync_playwright() as p:
        # Prawdziwy Chrome, nie okrojone Chromium Playwrighta. Wbudowana kopia
        # nie ma części komponentów i reCAPTCHA potrafi się w niej zapętlić
        # nawet dla człowieka — to nie blokada, tylko niekompletna przeglądarka.
        # Logowanie i tak wykonuje właściciel własnoręcznie.
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
            print("   (używam Twojego Chrome)\n")
        except Exception:
            browser = p.chromium.launch(headless=False)
            print("   (nie znalazłem Chrome, używam wbudowanej przeglądarki)\n")
        context = browser.new_context(viewport={"width": 1400, "height": 950})
        page = context.new_page()

        # NAJPIERW strona główna, nie formularz logowania. Pokazywanie formularza
        # komuś, kto jest już zalogowany, potrafi zapętlić CAPTCHĘ — nie ma czego
        # potwierdzać. Jeśli sesja istnieje, nie ma się w ogóle po co logować.
        #
        # USUNIETO 2026-08-20 ten sam blok wklejony omylkowo z `wystaw_notke`,
        # co w `sprawdz_sesje` — odwolywal sie do nieistniejacych tu nazw
        # `wyslij`, `tekst` i `wynik`. Obie funkcje ratunkowe byly martwe.
        page.goto("https://substack.com/home", timeout=READ_TIMEOUT_MS,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS)
        if zalogowany(context):
            print("   Jesteś już zalogowany — logowanie niepotrzebne.\n")
        else:
            print("   Nie jesteś zalogowany. Zaloguj się w otwartym oknie.\n")
            page.goto("https://substack.com/sign-in", timeout=READ_TIMEOUT_MS)
            while True:
                input("   [naciśnij Enter, gdy będziesz zalogowany] ")
                if zalogowany(context):
                    print("   Widzę sesję. Zapisuję.\n")
                    break
                print("   Nadal nie widzę sesji (brak ciasteczka substack.sid).")
                print("   Dokończ logowanie w oknie i naciśnij Enter jeszcze raz.")
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        context.close()
        browser.close()
    print(f"\nSesja zapisana: {SESSION_FILE}")
    print("Plik jest w .gitignore. Wylogowanie się na Substacku go unieważnia.")


def rozpoznanie() -> None:
    """Sprawdza, czy agent umie się poruszać po zalogowanym koncie.

    WYŁĄCZNIE ogląda i raportuje. Nie klika 'opublikuj', nie wysyła komentarza,
    nie polubia. Ten kod ma się dowiedzieć, czy nawigacja jest wykonalna —
    zanim ktokolwiek zdecyduje, że agent ma coś wysłać.
    """
    from playwright.sync_api import sync_playwright

    if not SESSION_FILE.exists():
        raise SystemExit(
            f"Brak pliku sesji ({SESSION_FILE}).\n"
            "Uruchom najpierw:  python agent-v2/browser.py zaloguj"
        )

    # Ekrany edytora rysują się długo, więc czekamy dłużej niż przy czytaniu.
    checks = [
        ("feed — skąd brać posty", "https://substack.com/home", 6000),
        ("notki — feed", "https://substack.com/notes", 6000),
        ("panel publikacji", "https://nothingisaccidental.substack.com/publish/home", 9000),
        ("edytor artykułu", "https://nothingisaccidental.substack.com/publish/post", 12000),
        ("skrzynka", "https://substack.com/inbox", 6000),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(SESSION_FILE), viewport={"width": 1400, "height": 1200}
        )
        page = context.new_page()
        for name, url, wait in checks:
            try:
                page.goto(url, timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(wait)
                text = page.inner_text("body")
                posts = len({u for u in page.eval_on_selector_all(
                    'a[href*="/p/"]', "e=>e.map(x=>x.href)")})
                buttons = [b.strip() for b in page.eval_on_selector_all(
                    "button, a[role=button]", "e=>e.map(x=>x.innerText)") if b.strip()]
                pola = page.eval_on_selector_all(
                    "[contenteditable=true], textarea, input[type=text]",
                    "e=>e.map(x=>x.getAttribute('placeholder')||x.getAttribute('aria-label')||'(bez etykiety)')",
                )
                print(f"  {name:26} tekst={len(text):>6}  postów={posts:>3}", flush=True)
                if buttons:
                    uniq = list(dict.fromkeys(buttons))[:10]
                    print(f"     przyciski: {' | '.join(uniq)[:150]}", flush=True)
                if pola:
                    print(f"     pola do pisania: {' | '.join(pola[:6])[:150]}", flush=True)
            except Exception as exc:
                print(f"  {name:26} BŁĄD {type(exc).__name__}: {exc}"[:160], flush=True)
        # Zapisujemy stan po każdej pracy: Substack odświeża ciasteczko przy
        # aktywności, więc regularne używanie konta samo przesuwa datę ważności.
        context.storage_state(path=str(SESSION_FILE))
        context.close()
        browser.close()


PROFIL_HANDLE = "nothingisaccidental"

# Substack tłumaczy cudze treści na język interfejsu i podmienia je w HTML-u.
# Nasza notka po angielsku wyświetlała się po polsku, a odpowiedź Anglika też.
# Agent czytający stronę odpisałby po polsku komuś, kto pisał po angielsku —
# więc treści bierzemy WYŁĄCZNIE z API, gdzie `body` jest oryginałem, a pole
# `language` mówi, w jakim języku naprawdę napisano.
def _plaskie(galaz: dict) -> list[dict]:
    """Rozwija gałąź wątku do płaskiej listy komentarzy."""
    out: list[dict] = []
    stos = [galaz]
    while stos:
        w = stos.pop()
        if not isinstance(w, dict):
            continue
        c = w.get("comment") or w
        if isinstance(c, dict) and c.get("body"):
            out.append(c)
        stos.extend(w.get("descendantComments") or w.get("children") or [])
    return out


def _kiedy(c: dict) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(
            str(c.get("date", "")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def ile_dzis_wystawione() -> dict[str, int]:
    """Ile notek, komentarzy i polubien poszlo dzisiaj.

    NOTKI liczymy u Substacka, bo rzeczywistosc jest lepszym zrodlem niz wlasna
    ksiegowosc: po restarcie albo przerwanym przebiegu ksiegowosc sie rozjezdza
    i agent wystawia dzienna norme drugi raz.

    KOMENTARZE I POLUBIENIA licza sie z dziennika, bo Substack ich nie oddaje —
    kanal profilu zwraca same notki. Powod i sprawdzenie: `z_dziennika_dzis`.
    Gdyby Substack kiedys zaczal pokazywac wlasne komentarze, to jest jedyne
    miejsce do zmiany.
    """
    from datetime import datetime, timezone

    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wynik = {"notki": 0, **z_dziennika_dzis()}
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
        if not isinstance(profil, dict) or not profil.get("id"):
            return wynik
        feed = api_json(page, f"/api/v1/reader/feed/profile/{profil['id']}") or {}
        for x in feed.get("items", []):
            c = (x or {}).get("comment") or {}
            if not str(c.get("date", "")).startswith(dzis):
                continue
            # Notka nie ma posta pod soba; komentarz owszem — a komentarzy stad
            # nie bierzemy, bo ten kanal ich nie zwraca.
            if not c.get("post_id"):
                wynik["notki"] += 1
        return wynik
    except Exception as exc:
        print(f"  (nie policzylem dzisiejszych: {type(exc).__name__})", flush=True)
        return wynik
    finally:
        page.close()
        browser.close()
        p.stop()


def dopisz_skutki() -> int:
    """Dopisuje do dziennika, CO Z NASZYCH DZIALAN WYNIKLO.

    Dziennik wiedzial, co wystawilismy, i nic o tym, czy ktokolwiek to zauwazyl.
    A to jest jedyne pytanie, na ktore trzeba umiec odpowiedziec, zeby cokolwiek
    poprawic: osiemnascie komentarzy przynioslo trzy reakcje, siedem notek —
    osiem. Musialem to policzyc recznie, bo agent tego nie zapisywal.

    Kanal aktywnosci mowi o polubieniach i odpowiedziach numerami komentarzy,
    a `wystaw_komentarz` zapisuje teraz numer naszego. Da sie wiec zestawic
    jedno z drugim i pytac: czy komentarz jako piaty wraca czesciej niz jako
    piecdziesiaty, i ktore z osiemnastu hasel przynosza rozmowy.

    Kazde zdarzenie zapisujemy RAZ — po jego wlasnym numerze, ktory Substack
    nadaje. Inaczej kazdy przebieg dopisywalby te same polubienia od nowa
    i statystyka rosla by sama z siebie.
    """
    import json as _json

    juz_zapisane = set()
    try:
        if DZIENNIK.exists():
            for linia in DZIENNIK.read_text(encoding="utf-8").splitlines():
                linia = linia.strip()
                if not linia:
                    continue
                try:
                    wpis = _json.loads(linia)
                except ValueError:
                    continue
                if isinstance(wpis, dict) and wpis.get("rodzaj") == "skutek":
                    juz_zapisane.add(wpis.get("zdarzenie"))
    except OSError:
        pass

    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    nowych = 0
    try:
        kanal = api_json(page, "/api/v1/activity-feed-web?filter=all") or {}
        if not isinstance(kanal, dict):
            return 0
        ludzie = {u["id"]: u for u in (kanal.get("users") or [])
                  if isinstance(u, dict) and u.get("id") is not None}
        for z in kanal.get("activityItems") or []:
            if not isinstance(z, dict):
                continue
            klucz = z.get("id") or z.get("item_key")
            if not klucz or klucz in juz_zapisane:
                continue
            typ = z.get("type")
            if not typ:
                continue
            # ZAPISUJEMY KAZDY RODZAJ, nie liste znanych. Lista miala w sobie
            # doslowne „restack", a Substack nazywa zdarzenia `note_like`,
            # `note_reply`, `comment_like` — wiec podanie naszej notki dalej
            # przyszloby zapewne jako `note_restack` i wypadloby bez sladu.
            # Akurat restack jest najcenniejszym sygnalem, jaki mozemy dostac:
            # w badaniu 9 641 notek konwertowal dwunastokrotnie lepiej niz
            # polubienie. Sygnal, ktorego nie widzimy, nie istnieje.
            #
            # Kanal aktywnosci dotyczy WYLACZNIE naszych tresci, wiec nie ma tu
            # czego odsiewac — nieznany rodzaj to nowa wiadomosc, nie smiec.
            kto = [(ludzie.get(i) or {}).get("name")
                   for i in (z.get("recent_sender_ids") or [])]
            zapisz_w_dzienniku(
                "skutek", udane=True, zdarzenie=klucz, typ=typ,
                # `czego` to numer NASZEJ tresci, ktora wywolala reakcje —
                # po nim laczymy skutek z wpisem o jej wystawieniu.
                czego=z.get("target_comment_id"),
                ilu=int(z.get("sender_count") or 0),
                kto=[k for k in kto if k][:5],
                kiedy_zdarzenia=str(z.get("created_at") or "")[:19])
            nowych += 1
        if nowych:
            print(f"  [skutki] nowych reakcji na nasze tresci: {nowych}", flush=True)
        return nowych
    except Exception as exc:
        print(f"  (nie dopisalem skutkow: {type(exc).__name__})", flush=True)
        return 0
    finally:
        page.close()
        browser.close()
        p.stop()


def odpowiedzi_na_nasze_komentarze(ile: int = 10) -> list[dict[str, Any]]:
    """Odpowiedzi na NASZE komentarze zostawione pod CUDZYMI tekstami.

    Trzecie miejsce, w ktorym toczy sie rozmowa, i jedyne, ktorego agent nie
    widzial wcale. Sprawdzal odpowiedzi pod wlasnymi notkami i pod wlasnymi
    artykulami — a komentarz zostawiony u kogos obcego zyje gdzie indziej i nie
    pojawia sie w zadnym z tych dwoch zrodel. Nie chodzilo o opoznienie: takiej
    odpowiedzi agent nie zobaczylby nigdy.

    Dla mlodego konta to najgorsze mozliwe miejsce na milczenie, bo wlasnie tam
    zaczyna sie rozmowa z ludzmi, ktorzy nas jeszcze nie znaja.

    Zrodlem jest `activity-feed-web` — to samo, czego uzywa zakladka „Activity".
    Zdarzenie `comment_reply` niesie numer NASZEGO komentarza i numer ICH
    odpowiedzi, a w tej samej odpowiedzi przychodza tresci, autorzy i posty,
    wiec nie trzeba o nic dopytywac.

    Nie mylic z `note_reply`: to odpowiedzi pod naszymi notkami, ktore obsluguje
    `nieodpowiedziane`. Braloby sie je tu drugi raz.
    """
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
        moje_id = (profil or {}).get("id")
        if not moje_id:
            return []

        kanal = api_json(page, "/api/v1/activity-feed-web?filter=all") or {}
        if not isinstance(kanal, dict):
            return []

        # Tresci lezą obok zdarzen, w kilku workach naraz — sklejamy w jeden.
        wpisy: dict[Any, dict] = {}
        for worek in ("comments", "feedItemComments", "communityComments"):
            for c in kanal.get(worek) or []:
                if isinstance(c, dict) and c.get("id") is not None:
                    wpisy.setdefault(c["id"], c)
        ludzie = {u["id"]: u for u in (kanal.get("users") or [])
                  if isinstance(u, dict) and u.get("id") is not None}
        posty = {x["id"]: x for x in (kanal.get("posts") or [])
                 if isinstance(x, dict) and x.get("id") is not None}

        czekaja: list[dict[str, Any]] = []
        for zdarzenie in kanal.get("activityItems") or []:
            if not isinstance(zdarzenie, dict):
                continue
            if zdarzenie.get("type") != "comment_reply":
                continue
            ich_id = zdarzenie.get("comment_id")
            nasz_id = zdarzenie.get("target_comment_id")
            if not ich_id or not nasz_id:
                continue

            ich = wpisy.get(ich_id) or {}
            nasz = wpisy.get(nasz_id) or {}
            tekst = ich.get("body") or ""
            if not tekst.strip():
                continue

            # Czy juz odpisalismy PO ich odpowiedzi. Pytamy watku, nie wlasnego
            # zapisu: po restarcie zapis klamie, Substack wie na pewno.
            watek = api_json(page, f"/api/v1/reader/comment/{ich_id}/replies"
                                   f"?comment_id={ich_id}") or {}
            plaskie = [c for g in (watek.get("commentBranches") or [])
                       for c in _plaskie(g)]
            # Porownujemy CZAS, nie napisy: `created_at` zdarzenia i `date`
            # komentarza bywaja zapisane inaczej (raz z milisekundami, raz bez),
            # a porownanie tekstowe daloby wtedy cichy falsz.
            kiedy_ich = _kiedy({"date": zdarzenie.get("created_at")})
            if any(c.get("user_id") == moje_id and _kiedy(c) > kiedy_ich
                   for c in plaskie):
                continue

            autor = (ich.get("name")
                     or (ludzie.get((zdarzenie.get("recent_sender_ids") or [None])[0])
                         or {}).get("name") or "")
            post = posty.get(zdarzenie.get("target_post_id")) or {}
            czekaja.append({
                "pod_czym": (nasz.get("body") or "")[:400],
                # Odpowiadamy ICH komentarzowi, nie swojemu — inaczej wpis
                # wyladowalby obok rozmowy zamiast w niej.
                "pod_id": ich_id,
                "autor": autor,
                "jezyk": ich.get("language"),
                "tekst": tekst,
                "id": ich_id,
                "gdzie": "komentarz_obcy",
                "kontekst": f"our own comment under \"{post.get('title') or 'someone else’s post'}\"",
                "url": post.get("canonical_url") or "",
            })
            if len(czekaja) >= ile:
                break

        if czekaja:
            print(f"  odpowiedzi na nasze komentarze u innych: {len(czekaja)}",
                  flush=True)
            for c in czekaja:
                print(f"    · {c['autor']} [{c.get('jezyk') or '?'}] {c['tekst'][:78]}",
                      flush=True)
        return czekaja
    except Exception as exc:
        print(f"  (nie sprawdzilem odpowiedzi u innych: {type(exc).__name__})",
              flush=True)
        return []
    finally:
        page.close()
        browser.close()
        p.stop()


def komentarze_pod_artykulami(ile: int = 5) -> list[dict[str, Any]]:
    """Cudze komentarze pod NASZYMI artykulami, na ktore nie odpisalismy.

    Kanal profilu pokazuje tylko notki, wiec artykuly wymagaja osobnego pytania.
    Bez tego czytelnik moglby zadac pytanie pod tekstem i nie doczekac sie
    odpowiedzi — a to szkodzi bardziej niz brak nowych komentarzy u obcych.
    """
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    czekaja: list[dict[str, Any]] = []
    try:
        moj = f"https://{config.SUBSTACK_HANDLE}.substack.com"
        profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
        moje_id = (profil or {}).get("id")
        posty = api_json(page, "/api/v1/posts?limit=10", baza=moj)
        lista = posty if isinstance(posty, list) else (posty or {}).get("posts") or []
        for post in lista[:ile]:
            if not isinstance(post, dict) or not post.get("id"):
                continue
            if not (post.get("comment_count") or 0):
                continue
            dane = api_json(page, f"/api/v1/post/{post['id']}/comments"
                                  "?all_comments=true", baza=moj)
            kom = dane if isinstance(dane, list) else (dane or {}).get("comments") or []
            nasze_daty = [_kiedy(k) for k in kom
                          if isinstance(k, dict) and k.get("user_id") == moje_id]
            nasz_ostatni = max(nasze_daty, default=0.0)
            for k in kom:
                if not isinstance(k, dict) or k.get("user_id") == moje_id:
                    continue
                if nasz_ostatni and _kiedy(k) < nasz_ostatni:
                    continue
                czekaja.append({
                    "pod_czym": (post.get("title") or "")[:200],
                    "pod_id": post["id"], "gdzie": "artykul",
                    "url": post.get("canonical_url") or "",
                    "autor": k.get("name"), "jezyk": k.get("language"),
                    "tekst": k.get("body") or "", "id": k.get("id"),
                    "data": k.get("date"),
                    "reakcje": k.get("reaction_count") or 0,
                })
        print(f"  pod artykulami czeka: {len(czekaja)}", flush=True)
        for c in czekaja[:5]:
            print(f"    · {c['autor']} pod {c['pod_czym'][:34]!r}: "
                  f"{c['tekst'][:52]}", flush=True)
        return czekaja
    except Exception as exc:
        print(f"  (nie sprawdzilem artykulow: {type(exc).__name__}: {exc})"[:150],
              flush=True)
        return czekaja
    finally:
        page.close()
        browser.close()
        p.stop()


def nieodpowiedziane(ile: int = 10) -> list[dict[str, Any]]:
    """Cudze odpowiedzi pod naszymi notkami, na które jeszcze nie odpisaliśmy.

    Treści bierzemy z API, nie ze strony: Substack tłumaczy cudze wpisy na język
    interfejsu, a odpowiedź po polsku komuś, kto pisał po angielsku, byłaby
    kompromitacją. W API `body` jest oryginałem, a `language` mówi, jak napisano.
    """
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
        if not isinstance(profil, dict) or not profil.get("id"):
            print("  nie udało się odczytać profilu", flush=True)
            return []
        moje_id = profil["id"]
        feed = api_json(page, f"/api/v1/reader/feed/profile/{moje_id}"
                              "?types%5B%5D=note") or {}
        nasze = [x["comment"] for x in feed.get("items", [])
                 if isinstance(x, dict) and isinstance(x.get("comment"), dict)
                 and (x["comment"].get("children_count") or 0) > 0][:ile]

        czekaja: list[dict[str, Any]] = []
        for n in nasze:
            watek = api_json(page, f"/api/v1/reader/comment/{n['id']}/replies"
                                   f"?comment_id={n['id']}") or {}
            galezie = watek.get("commentBranches") or []
            wszystkie = [c for g in galezie for c in _plaskie(g)]
            # Nasz najnowszy głos w CAŁYM wątku, nie w pojedynczej gałęzi:
            # odpowiedź wpisana pod notką jest RODZEŃSTWEM cudzego komentarza,
            # więc liczenie wewnątrz gałęzi kazało odpisywać w kółko.
            nasz_ostatni = max((_kiedy(c) for c in wszystkie
                                if c.get("user_id") == moje_id), default=0.0)
            for g in galezie:
                plaskie = _plaskie(g)
                if not plaskie:
                    continue
                ostatni = max(plaskie, key=_kiedy)
                if ostatni.get("user_id") == moje_id:
                    continue
                if nasz_ostatni and _kiedy(ostatni) < nasz_ostatni:
                    continue
                czekaja.append({
                    "pod_czym": (n.get("body") or "")[:400], "pod_id": n["id"],
                    "autor": ostatni.get("name"), "jezyk": ostatni.get("language"),
                    "tekst": ostatni.get("body") or "", "id": ostatni.get("id"),
                    "data": ostatni.get("date"),
                })
        print(f"  czeka na odpowiedź: {len(czekaja)}", flush=True)
        for c in czekaja:
            print(f"    · {c['autor']} [{c.get('jezyk')}] {c['tekst'][:70]}",
                  flush=True)
        return czekaja
    finally:
        page.close()
        browser.close()
        p.stop()


def sluchaj_publikacji(page) -> list[int]:
    """Zbiera kody odpowiedzi na zapytania PUBLIKUJACE.

    Najpewniejsze zrodlo prawdy o tym, czy tresc poszla: wlasna odpowiedz
    Substacka na nasz zapis. Kanal profilu aktualizuje sie z opoznieniem —
    czasem ponad pol minuty — wiec sprawdzanie go zaraz po klknieciu dawalo
    falszywe "nie wyszlo" dla notek, ktore wyszly. To jest tez to, co research
    o awariach takich agentow zalecal wprost: patrzec na odpowiedz API zapisu,
    a nie na wlasny log sukcesu.
    """
    odpowiedzi: list = []
    page.on("response", lambda r: odpowiedzi.append(r)
            if "/api/v1/comment/feed" in r.url and r.request.method == "POST"
            else None)
    return odpowiedzi


def id_z_odpowiedzi(odpowiedzi: list) -> str:
    """Identyfikator notki, ktory Substack oddal przy zapisie.

    BRAKOWALO GO I TO ROZRYWALO POMIAR NA POL. Dziennik zapisywal osobno
    „wystawilismy notke o trybie samolotowym" i osobno „notka 315733831
    zebrala trzy polubienia" — bez zadnego pola, po ktorym da sie stwierdzic,
    czy to ta sama. Wiedzielismy, ze publikujemy, i nie wiedzielismy, co
    z tego dziala.

    Bralismy z odpowiedzi WYLACZNIE kod HTTP, a tresc — z identyfikatorem
    utworzonej notki — szla do kosza.

    Ciala odpowiedzi czytamy DOPIERO TU, po klknieciu i odczekaniu, a nie
    w callbacku zdarzenia: w callbacku tresc bywa jeszcze niedostepna i
    czytanie jej potrafi rzucic. Brak identyfikatora nie jest bledem —
    notka wyszla albo nie wyszla niezaleznie od tego, czy umiemy ja pozniej
    odnalezc.
    """
    for r in odpowiedzi:
        try:
            if r.status != 200:
                continue
            dane = r.json()
        except Exception:
            continue
        # Ksztalt odpowiedzi nie jest przez nikogo obiecany, wiec sprawdzamy
        # kilka miejsc zamiast zakladac jedno.
        for wezel in (dane, (dane or {}).get("comment"), (dane or {}).get("item")):
            if isinstance(wezel, dict) and wezel.get("id") is not None:
                return str(wezel["id"])
    return ""


def potwierdz_notke(page, tekst: str, prob: int = 4) -> bool:
    """Pyta Substacka, czy notka naprawdę wisi na naszym profilu.

    Pyta KILKA RAZY, bo kanał profilu aktualizuje się z opóźnieniem. Pojedyncze
    sprawdzenie po sześciu sekundach zwracało "nie ma" dla notki, która wyszła
    poprawnie — a fałszywy alarm w tę stronę jest grozniejszy niz brak
    potwierdzenia: rozbraja zabezpieczenie przed wystawieniem tego samego
    drugi raz.
    """
    import json as _json

    probka = " ".join(tekst.split())[:60]
    profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
    if not isinstance(profil, dict) or not profil.get("id"):
        return False
    for nr in range(prob):
        feed = api_json(page, f"/api/v1/reader/feed/profile/{profil['id']}"
                              "?types%5B%5D=note")
        if probka in " ".join(_json.dumps((feed or {}).get("items", []),
                                          ensure_ascii=False).split()):
            return True
        if nr < prob - 1:
            page.wait_for_timeout(8000)
    return False

def polub_w_kanale(ile: int, wyslij: bool = False) -> dict[str, Any]:
    """Polubienia w kanale czytelnika.

    Polubienie jest najtańszym uczciwym sygnałem, jaki konto może wysłać, i
    jedynym, który nic nie twierdzi — dlatego wolno je robić bez pytania.
    Odstępy między kliknięciami są losowe: piętnaście polubień w półtorej minuty
    to nie jest czytanie i każdy system to widzi.
    """
    import random

    wyslij = naprawde_wyslac(wyslij, "polubienia")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"znalezione": 0, "polubione": 0, "blad": None}
    try:
        page.goto("https://substack.com/", timeout=READ_TIMEOUT_MS * 2,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 6000)

        przyciski = page.get_by_role("button", name="Like")
        wynik["znalezione"] = przyciski.count()
        print(f"  do polubienia w kanale: {wynik['znalezione']}", flush=True)

        for i in range(min(ile, przyciski.count())):
            kandydat = przyciski.nth(i)
            try:
                if not kandydat.is_visible():
                    continue
                if not wyslij:
                    wynik["polubione"] += 1
                    continue
                kandydat.scroll_into_view_if_needed(timeout=8000)
                kandydat.click(timeout=8000)
                wynik["polubione"] += 1
                print(f"  polubione {wynik['polubione']}/{ile}", flush=True)
                zapisz_w_dzienniku("polubienie", udane=True)
                page.wait_for_timeout(
                    int(random.uniform(*config.ODSTEPY["lajk"]) * 1000))
            except Exception as exc:
                # POLKNIETA PORAZKA. Szlo do logu i nigdzie indziej, wiec
                # dziennik pokazywal same udane polubienia — a przy 67%
                # realizacji normy pytanie brzmi wlasnie „co sie nie udalo".
                powod = f"{type(exc).__name__}: {exc}"[:140]
                print(f"    (pominiete: {type(exc).__name__})", flush=True)
                zapisz_w_dzienniku("polubienie", udane=False, powod=powod)
        if not wyslij:
            print(f"  (nie klikam — tryb sprawdzenia; kliknalbym"
                  f" {wynik['polubione']})", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def _klik_na_profilu(handle: str, napisy: tuple[str, ...], rodzaj: str,
                     wyslij: bool) -> dict[str, Any]:
    """Klika JEDEN konkretny przycisk na cudzym profilu — i tylko jego.

    OBSERWOWANIE I SUBSKRYPCJA TO DWIE ROZNE RZECZY. Obserwowanie sprawia, ze
    czyjes notki pojawiaja sie w naszym kanale; subskrypcja przysyla jego teksty
    MAILEM do skrzynki wlasciciela. Dlatego widelki sa inne: 30-44 obserwacje
    miesiecznie, ale tylko 6-12 subskrypcji.

    Jedna funkcja probowala kolejno „Subscribe", „Subskrybuj", „Follow",
    „Obserwuj" i brala pierwszy znaleziony. Na profilu Substacka „Subscribe" jest
    zawsze, wiec do „Follow" nie dochodzilo NIGDY — kazda z czterech prob
    w logach kliknela subskrypcje. Agent subskrybowal w tempie obserwacji.

    Gdy wlasciwego przycisku nie ma, nie robimy NIC. Klikniecie „w zastepstwie"
    to dokladnie ten blad, ktory to spowodowal.
    """
    wyslij = naprawde_wyslac(wyslij, rodzaj)
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"handle": handle, "zrobione": False, "blad": None}
    try:
        page.goto(f"https://substack.com/@{handle}", timeout=READ_TIMEOUT_MS * 2,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 4000)
        for nazwa in napisy:
            k = page.get_by_role("button", name=nazwa, exact=True).first
            if k.count() == 0 or not k.is_visible():
                continue
            print(f"  przycisk: {nazwa!r}  ({rodzaj})", flush=True)
            if not wyslij:
                print("  (nie klikam — tryb sprawdzenia)", flush=True)
                return wynik
            k.click(timeout=10_000)
            page.wait_for_timeout(5000)
            # Po kliknieciu napis zmienia sie na stan przeciwny.
            wynik["zrobione"] = k.count() == 0 or not k.is_visible()
            dopisz_wynik(rodzaj, wynik, komu=handle)
            print("  ZROBIONE" if wynik["zrobione"]
                  else "  KLIKNIETE, ALE STAN SIE NIE ZMIENIL", flush=True)
            return wynik
        wynik["blad"] = f"nie ma przycisku {rodzaj} u {handle}"
        print(f"  {wynik['blad']} — nie klikam nic innego", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        # BRAK PRZYCISKU TO TEZ WYNIK i musi zostawic slad. Bez tego blok
        # obserwacji, ktory nie znalazl ani jednego przycisku „Follow" przez
        # siedem dni, wygladal w dzienniku jak blok, ktory sie nie odbyl —
        # a on sie odbywal, chodzil po profilach i za kazdym razem odchodzil
        # z pustymi rekami. Tego nie da sie naprawic, czego nie widac.
        if wyslij:
            dopisz_wynik(rodzaj, wynik, komu=handle)
        page.close()
        browser.close()
        p.stop()
    return wynik


def pobierz_subskrybentow() -> dict[str, Any]:
    """Czyta liste subskrybentow z WLASNEGO panelu, wlasna sesja.

    ## Dlaczego to NIE jest to, czego wczesniej odmowilismy

    Odmowilismy ZGADYWANIA NIEUDOKUMENTOWANYCH ADRESOW API — `/api/v1/subscriber/csv`
    i podobnych, ktore zwracaja 404. Powtarzane sondowanie takich adresow to
    dokladnie to, co regulamin Substacka nazywa scrapingiem, a kopia listy ma
    konto CHRONIC, nie narazac.

    To jest co innego: wlasciciel patrzy na wlasny panel wlasna sesja. Ta sama
    przegladarka, ta sama sesja i ta sama droga, ktora agent od tygodni wystawia
    notki i komentarze. Zadnego cudzego konta, zadnego omijania limitow, zadnego
    adresu, ktorego panel sam by nie odpytal.

    ## Czego ta funkcja NIE gwarantuje i dlaczego to wazne

    Kompletu. Przy czterech subskrybentach tabela miesci sie na jednym ekranie,
    ale przy stu Substack doladowuje wiersze przy przewijaniu. Dlatego przewijamy
    do skutku i oddajemy `kompletna=False`, gdy liczba wierszy nadal rosla, kiedy
    skonczyl sie limit prob.

    NIEPELNA LISTA JEST GROZNIEJSZA NIZ JEJ BRAK: zapisana jako kopia wyglada
    jak komplet, a przy odtwarzaniu okazuje sie polowa. Dlatego decyzje o zapisie
    podejmuje `kopia_subskrybentow`, nie ta funkcja — tutaj oddajemy tylko fakty.
    """
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wiersze": [], "kompletna": False, "powod": ""}
    try:
        page.goto("https://%s.substack.com/publish/subscribers" % config.SUBSTACK_HANDLE,
                  timeout=READ_TIMEOUT_MS * 2, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 5000)

        # PRZEWIJAMY DO SKUTKU. Warunek konca to „dwa razy z rzedu tyle samo
        # wierszy", a nie „przewinelismy N razy" — inaczej wolna siec dawalaby
        # niepelna liste wygladajaca na pelna.
        ile_bylo, bez_zmian = -1, 0
        for _ in range(40):
            wiersze = _wiersze_subskrybentow(page)
            if len(wiersze) == ile_bylo:
                bez_zmian += 1
                if bez_zmian >= 2:
                    wynik["kompletna"] = True
                    break
            else:
                bez_zmian = 0
            ile_bylo = len(wiersze)
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1200)
        else:
            wynik["powod"] = ("lista nadal rosla po 40 przewinieciach — "
                              "nie moge zarczyc, ze to komplet")

        wynik["wiersze"] = _wiersze_subskrybentow(page)
        if not wynik["wiersze"]:
            wynik["kompletna"] = False
            wynik["powod"] = ("panel nie oddal ani jednego adresu — zmienil sie "
                              "uklad strony albo wygasla sesja")
    except Exception as exc:
        wynik["kompletna"] = False
        wynik["powod"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def zloz_wiersze_subskrybentow(surowe) -> list[dict[str, str]]:
    """Sklada wiersze z komorek tabeli panelu: adres, typ i data rozpoczecia.

    Osobna, CZYSTA funkcja — bez przegladarki — bo pierwsza wersja brala typ
    z `komorki[1]` na sztywno i wstawiala tam POWTORZONY ADRES. Wyszlo to
    dopiero na zywym pobraniu, przy ogladaniu zapisanego pliku. Nie polegamy
    juz na numerze kolumny: znajdujemy komorke z adresem i bierzemy NASTEPNA,
    bo w naglowku panelu typ stoi zaraz za subskrybentem.

    Nie polegamy tez na klasach CSS — Substack generuje je losowo
    (`container-_91AK1`), wiec selektor po klasie padnie przy pierwszym
    wdrozeniu po ich stronie.
    """
    import re

    adres_re = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    wiersze: list[dict[str, str]] = []
    for komorki in surowe or []:
        komorki = [str(k or "").strip() for k in komorki]
        gdzie = next((i for i, k in enumerate(komorki)
                      if adres_re.fullmatch(k)), None)
        if gdzie is None:
            continue
        # Typ to nastepna komorka, ale nigdy druga kopia adresu ani pusta.
        typ = ""
        for k in komorki[gdzie + 1:]:
            if k and not adres_re.fullmatch(k):
                typ = k
                break
        wiersze.append({
            "email": komorki[gdzie],
            "typ": typ,
            "od": next((k for k in komorki[gdzie + 1:]
                        if re.search(r"\b(19|20)\d{2}\b", k)), ""),
        })
    return wiersze


def _wiersze_subskrybentow(page) -> list[dict[str, str]]:
    """Czyta komorki tabeli z panelu i oddaje je zlozone."""
    surowe = page.eval_on_selector_all(
        "table tr, [role=row]",
        "els => els.map(e => Array.from(e.querySelectorAll('td, [role=cell]'))"
        ".map(c => (c.innerText || '').trim()))")
    return zloz_wiersze_subskrybentow(surowe)


def uchwyt_autora(host: str) -> str | None:
    """Konto CZLOWIEKA, ktory pisze pod tym adresem — nie konto publikacji.

    OBSERWOWANIE I SUBSKRYPCJA TO DWIE ROZNE RZECZY i tutaj ta roznica przestaje
    byc teoria. Strona PUBLIKACJI ma przycisk `Subscribe`. Przycisk `Follow`
    maja profile LUDZI.

    `uchwyt_publikacji` dla adresow w domenie Substacka robi skrot
    `host.split(".")[0]`, wiec oddaje uchwyt PUBLIKACJI — a obserwacja szukala
    potem `Follow` tam, gdzie go z definicji nie ma. Sto procent porazek, po
    cichu, przez tygodnie: zero obserwacji przy normie okolo dwudziestu pieciu
    miesiecznie. Wyszlo dopiero wtedy, gdy porazki zaczely zostawiac slad
    w dzienniku — wczesniej blok wygladal na taki, ktory sie nie odbywa.

    Autora czytamy z `publishedBylines` — ta droga juz istniala w
    `uchwyt_publikacji`, ale byla uzywana wylacznie przy wlasnych domenach.
    Gdy nie da sie ustalic, oddajemy None: lepiej nie obserwowac nikogo niz
    klikac na chybil trafil na cudzym profilu.
    """
    host = (host or "").strip().lower().rstrip("/")
    if not host:
        return None
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        posty = api_json(page, "/api/v1/posts?limit=3", baza=f"https://{host}")
        lista = posty if isinstance(posty, list) else (posty or {}).get("posts") or []
        for post in lista:
            for bylina in (post or {}).get("publishedBylines") or []:
                uchwyt = (bylina or {}).get("handle")
                if uchwyt:
                    return str(uchwyt)
        return None
    except Exception:
        return None
    finally:
        page.close()
        browser.close()
        p.stop()


def obserwuj_profil(handle: str, wyslij: bool = False) -> dict[str, Any]:
    """Obserwuje cudzy profil — jego notki trafiaja do naszego kanalu.

    Nie przysyla nic mailem, wiec limit jest szerszy niz przy subskrypcji.
    """
    return _klik_na_profilu(handle, ("Follow", "Obserwuj"), "obserwacja", wyslij)


def zasubskrybuj(handle: str, wyslij: bool = False) -> dict[str, Any]:
    """Subskrybuje cudzy profil. Ląduje w skrzynce właściciela, więc wąsko."""
    return _klik_na_profilu(handle, ("Subscribe", "Subskrybuj"), "subskrypcja",
                            wyslij)


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rozbierz_artykul(sciezka: Path) -> dict[str, Any]:
    """Rozkłada plik artykułu na tytuł, podtytuł i treść jako HTML.

    Treść idzie do edytora WKLEJENIEM HTML-a, nie wpisywaniem znak po znaku:
    Substack używa ProseMirror, który przy wpisywaniu gubi linki w źródłach —
    a nazwane źródła to obietnica z oświadczenia o AI, nie ozdoba.
    """
    linie = sciezka.read_text(encoding="utf-8").splitlines()
    tytul = linie[0].lstrip("# ").strip() if linie else ""
    podtytul = ""
    reszta: list[str] = []
    for i, l in enumerate(linie[1:], 1):
        s = l.strip()
        if not podtytul and s.startswith("*") and s.endswith("*") and len(s) > 2:
            podtytul = s.strip("*").strip()
            continue
        reszta.append(l)

    html: list[str] = []
    lista_otwarta = False
    for blok in "\n".join(reszta).split("\n\n"):
        b = blok.strip()
        if not b or b == "---":
            continue
        if b.startswith("## "):
            if lista_otwarta:
                html.append("</ul>")
                lista_otwarta = False
            html.append(f"<h2>{_esc(b[3:].strip())}</h2>")
            continue
        if b.startswith("- "):
            if not lista_otwarta:
                html.append("<ul>")
                lista_otwarta = True
            for poz in b.splitlines():
                poz = poz.strip()[2:].strip()
                m = re.match(r"\[(.+?)\]\((\S+?)\)$", poz)
                html.append(
                    f'<li><a href="{_esc(m.group(2))}">{_esc(m.group(1))}</a></li>'
                    if m else f"<li>{_esc(poz)}</li>"
                )
            continue
        if lista_otwarta:
            html.append("</ul>")
            lista_otwarta = False
        html.append(f"<p>{_esc(' '.join(b.split()))}</p>")
    if lista_otwarta:
        html.append("</ul>")
    return {"tytul": tytul, "podtytul": podtytul, "html": "".join(html)}


_JS_WKLEJ_HTML = """
([html]) => {
    const el = document.querySelector('.tiptap');
    if (!el) return false;
    el.focus();
    const dt = new DataTransfer();
    dt.setData('text/html', html);
    dt.setData('text/plain', '');
    el.dispatchEvent(new ClipboardEvent('paste',
        {clipboardData: dt, bubbles: true, cancelable: true}));
    return true;
}
"""

_JS_WKLEJ_OBRAZ = """
([b64]) => {
    const el = document.querySelector('.tiptap');
    if (!el) return false;
    el.focus();
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const plik = new File([arr], 'naglowek.png', {type: 'image/png'});
    const dt = new DataTransfer();
    dt.items.add(plik);
    el.dispatchEvent(new ClipboardEvent('paste',
        {clipboardData: dt, bubbles: true, cancelable: true}));
    return true;
}
"""


def wypelnij_artykul(page, artykul: dict[str, Any], obraz: Path | None) -> None:
    """Wkłada tytuł, podtytuł, grafikę i treść do otwartego edytora.

    Grafika idzie W TREŚĆ, na samą górę — tak, jak robi to właściciel ręcznie.
    Szukałem osobnego slotu okładki i była to droga naokoło: obraz wklejony do
    treści edytor sam wysyła na swój serwer i sam robi z niego podgląd.
    """
    import base64

    page.locator("textarea.page-title").first.fill(artykul["tytul"])
    page.wait_for_timeout(400)
    if artykul.get("podtytul"):
        page.locator("textarea.subtitle").first.fill(artykul["podtytul"])
        page.wait_for_timeout(400)

    edytor = page.locator(".tiptap").first
    edytor.click()
    page.wait_for_timeout(400)
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.wait_for_timeout(400)

    # Treść wklejamy jako HTML, nie wpisujemy: ProseMirror gubi przy wpisywaniu
    # linki w źródłach, a nazwane źródła to obietnica z oświadczenia o AI.
    page.evaluate(_JS_WKLEJ_HTML, [artykul["html"]])
    page.wait_for_timeout(3000)
    print(f"  wklejona treść: {len(edytor.inner_text().split())} słów, "
          f"{page.locator('.tiptap a').count()} węzłów linkowych", flush=True)

    if obraz and obraz.exists():
        edytor.click()
        page.keyboard.press("Control+Home")
        page.wait_for_timeout(500)
        page.evaluate(_JS_WKLEJ_OBRAZ,
                      [base64.b64encode(obraz.read_bytes()).decode()])
        for _ in range(20):   # wysyłka na serwer Substacka trwa
            page.wait_for_timeout(1500)
            if page.locator(".tiptap img").count():
                break
        wgrany = page.locator(".tiptap img").count() > 0
        print(f"  grafika: {'wgrana' if wgrany else 'NIE WESZŁA'}", flush=True)

    wstaw_przycisk_subskrypcji(page)


def wstaw_przycisk_subskrypcji(page) -> bool:
    """Jeden przycisk subskrypcji, po ostatnim akapicie a przed źródłami.

    Tam ląduje argument, więc tam czytelnik decyduje — a ostatnią rzeczą na
    stronie zostaje lista źródeł, czyli podpis tego pisma i dokładnie to, co
    obiecuje oświadczenie o AI. Dwa przyciski byłyby nachalne przy piśmie,
    którego walutą jest powściągliwość.
    """
    naglowek = page.locator(".tiptap h1, .tiptap h2").filter(has_text="Sources").first
    if naglowek.count() == 0:
        print("  przycisk subskrypcji: brak nagłówka źródeł, pomijam", flush=True)
        return False
    akapit = naglowek.locator("xpath=preceding-sibling::p[1]")
    if akapit.count() == 0:
        return False
    akapit.click()
    page.keyboard.press("End")
    page.wait_for_timeout(600)

    for nazwa in ("Przycisk", "Button"):
        k = page.get_by_role("button", name=nazwa).first
        if k.count() > 0 and k.is_visible():
            k.click()
            break
    page.wait_for_timeout(2500)
    for nazwa in ("Subskrybuj", "Subscribe"):
        opcja = page.get_by_text(nazwa, exact=True).first
        if opcja.count() > 0 and opcja.is_visible():
            opcja.click()
            page.wait_for_timeout(3000)
            print("  przycisk subskrypcji wstawiony", flush=True)
            return True
    print("  przycisk subskrypcji: nie znalazłem opcji", flush=True)
    return False


def tresc_oswiadczenia() -> str:
    """Oświadczenie „Jak to robię" — z pliku, nie z drugiej kopii w kodzie.

    Tekst jest publiczny i wiążący, więc ma jedno źródło: cytat blokowy
    w `prompts/OSWIADCZENIE_AI.md`, gdzie leży razem z uzasadnieniem.
    """
    plik = config.PROMPTS_DIR / "OSWIADCZENIE_AI.md"
    linie = [l[2:].strip() for l in plik.read_text(encoding="utf-8").splitlines()
             if l.startswith("> ")]
    tekst = " ".join(linie).strip()
    if not tekst:
        raise RuntimeError("nie znalazłem treści oświadczenia w OSWIADCZENIE_AI.md")
    return tekst


def ustaw_oswiadczenie_ai(wyslij: bool = False) -> dict[str, Any]:
    """Ustawia stałe oświadczenie pokazywane każdemu, kto skanuje nas pod kątem AI.

    Ustawienie konta, nie posta — robi się raz i wisi przy wszystkim: przy
    artykułach, notkach i odpowiedziach.
    """
    wyslij = naprawde_wyslac(wyslij, "oswiadczenie")
    wymagaj_sesji()
    tekst = tresc_oswiadczenia()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"tekst": tekst, "zapisane": False, "blad": None}
    try:
        page.goto(f"https://{config.SUBSTACK_HANDLE}.substack.com/publish/post"
                  "?type=newsletter",
                  timeout=READ_TIMEOUT_MS * 2, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 5000)
        # Okno oświadczenia wisi pod skanowaniem AI, a to pod stroną ustawień.
        page.locator("textarea.page-title").first.fill("(ustawienie oświadczenia)")
        page.wait_for_timeout(600)
        for nazwa in ("Kontynuuj", "Continue"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                k.click()
                break
        page.wait_for_timeout(8000)
        for nazwa in ("Skanuj w poszukiwaniu tekstu AI", "Scan for AI text"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                k.click()
                break
        page.wait_for_timeout(9000)
        for nazwa in ("Utwórz oświadczenie", "Create", "How I"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                k.click()
                break
        page.wait_for_timeout(4000)

        # Pole oświadczenia to jedyna widoczna textarea BEZ atrybutu placeholder:
        # nazwy klas są zahaszowane, więc szukanie po nich zepsułoby się przy
        # najbliższej zmianie po stronie Substacka.
        pole = None
        for i in range(page.locator("textarea").count()):
            el = page.locator("textarea").nth(i)
            if el.is_visible() and not el.get_attribute("placeholder"):
                pole = el
                break
        if pole is None:
            raise RuntimeError("nie znalazłem pola oświadczenia")
        pole.fill(tekst)
        page.wait_for_timeout(1200)
        print(f"  wpisane oświadczenie: {len(tekst.split())} słów", flush=True)

        zapisz = None
        for nazwa in ("Zapisz oświadczenie", "Save statement", "Save"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                zapisz = k
                break
        wynik["przycisk_widoczny"] = zapisz is not None
        if wyslij and zapisz is not None:
            zapisz.click()
            page.wait_for_timeout(5000)
            wynik["zapisane"] = True
            print("  OŚWIADCZENIE ZAPISANE", flush=True)
        elif not wyslij:
            print("  (nie zapisuję — tryb sprawdzenia)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def wystaw_odpowiedz_pod_artykulem(
    url_artykulu: str, autor: str, tekst: str, wyslij: bool = False,
) -> dict[str, Any]:
    """Odpowiada pod KONKRETNYM komentarzem pod naszym artykułem.

    Inny mechanizm niż pod notką: tam wątek jest płaski i odpowiada się w polu
    pod całą notką, tu każdy komentarz ma własny przycisk odpowiedzi. Dzięki temu
    rozmówca dostaje powiadomienie, a wątek czyta się jak rozmowa.
    """
    wyslij = naprawde_wyslac(wyslij, "odpowiedz pod artykułem")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        page.goto(url_artykulu.rstrip("/") + "/comments",
                  timeout=READ_TIMEOUT_MS * 2, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 6000)
        page.mouse.wheel(0, 12_000)
        page.wait_for_timeout(2500)

        # Szukamy komentarza po autorze, a przycisk odpowiedzi w jego okolicy —
        # inaczej trafilibyśmy w cudzy wątek.
        # Przycisk odpowiedzi znajdujemy po ODLEGLOSCI OD KOMENTARZA, a nie po
        # drzewie DOM: uklad zmienia sie miedzy widokami, a przy wielu
        # komentarzach trafienie w cudzy watek byloby wpadka nie do cofniecia.
        wybrany = page.evaluate("""(autor) => {
            const kandydaci = [...document.querySelectorAll('*')].filter(
                n => !n.children.length &&
                     /^(reply|odpowiedz)$/i.test((n.innerText || '').trim()));
            const kotwice = [...document.querySelectorAll('*')].filter(
                n => !n.children.length &&
                     (n.innerText || '').trim() === autor);
            if (!kandydaci.length || !kotwice.length) return -1;
            const k = kotwice[0].getBoundingClientRect();
            let najlepszy = -1, naj = 1e9;
            kandydaci.forEach((c, i) => {
                const r = c.getBoundingClientRect();
                const d = Math.hypot(r.top - k.top, r.left - k.left);
                if (d < naj) { naj = d; najlepszy = i; }
            });
            kandydaci.forEach((c, i) => c.setAttribute('data-nia',
                                                       i === najlepszy ? '1' : '0'));
            return najlepszy;
        }""", autor)
        if wybrany < 0:
            raise RuntimeError("nie znalazłem przycisku odpowiedzi")
        przycisk = page.locator('[data-nia="1"]').first
        print(f"  przycisk odpowiedzi znaleziony przy komentarzu {autor!r}",
              flush=True)
        przycisk.click(timeout=15_000)
        page.wait_for_timeout(3000)

        pole = page.locator("textarea").first
        pole.click(timeout=10_000)
        page.keyboard.type(tekst, delay=12)
        page.wait_for_timeout(1500)
        wynik["wpisane"] = True
        print(f"  wpisane w pole odpowiedzi: {len(tekst.split())} słów", flush=True)

        wyslac = None
        for nazwa in ("Reply", "Post", "Odpowiedz", "Opublikuj"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                wyslac = k
                break
        wynik["przycisk_widoczny"] = wyslac is not None

        if wyslij and wyslac is not None:
            wyslac.click()
            page.wait_for_timeout(8000)
            wynik["wyslane"] = potwierdz_komentarz(page, url_artykulu, tekst)
            dopisz_wynik("odpowiedz_pod_artykulem", wynik,
                               gdzie=url_artykulu, komu=autor,
                               slow=len(tekst.split()), tekst=tekst[:300])
            print("  ODPOWIEDŹ POD ARTYKUŁEM POTWIERDZONA" if wynik["wyslane"]
                  else "  KLIKNIĘTE, ALE ODPOWIEDZI NIE WIDAĆ", flush=True)
        elif not wyslij:
            print("  (nie wysyłam — tryb sprawdzenia)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def potwierdz_artykul(page, tytul: str) -> bool:
    """Pyta Substacka, czy artykuł naprawdę jest opublikowany."""
    probka = " ".join(tytul.split())[:50]
    dane = api_json(page, "/api/v1/posts?limit=5",
                    baza=f"https://{config.SUBSTACK_HANDLE}.substack.com")
    # Ten adres oddaje LISTE, nie obiekt z kluczem "posts" — sprawdzone na zywo.
    lista = dane if isinstance(dane, list) else (dane or {}).get("posts") or []
    return any(probka in (x.get("title") or "") and x.get("post_date")
               for x in lista if isinstance(x, dict))

def wystaw_artykul(
    sciezka_md: Path, sciezka_png: Path | None = None, wyslij: bool = False,
) -> dict[str, Any]:
    """Wystawia artykuł na Substacku. Domyślnie WYPEŁNIA i NIE WYSYŁA."""
    wyslij = naprawde_wyslac(wyslij, "artykul")
    wymagaj_sesji()
    artykul = rozbierz_artykul(sciezka_md)
    if sciezka_png is None:
        kandydat = sciezka_md.with_suffix(".png")
        sciezka_png = kandydat if kandydat.exists() else None

    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wypelnione": False, "wyslane": False, "blad": None,
                             "tytul": artykul["tytul"]}
    try:
        if wyslij and potwierdz_artykul(page, artykul["tytul"]):
            print("  artykul o tym tytule juz jest opublikowany — przerywam",
                  flush=True)
            wynik["wyslane"] = True
            wynik["pominiete"] = True
            return wynik

        page.goto(f"https://{config.SUBSTACK_HANDLE}.substack.com/publish/post"
                  "?type=newsletter",
                  timeout=READ_TIMEOUT_MS * 2, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 5000)
        wynik["szkic"] = page.url

        wypelnij_artykul(page, artykul, sciezka_png)
        wynik["wypelnione"] = True

        dalej = None
        for nazwa in ("Kontynuuj", "Continue", "Weiter"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                dalej = k
                break
        if dalej is None:
            raise RuntimeError("nie znalazłem przycisku przejścia do ustawień")
        dalej.click()
        page.wait_for_timeout(8000)

        if config.WYLACZ_WYKRYWANIE_AI:
            for nazwa in ("Wyłącz wykrywanie AI", "Turn off AI detection"):
                k = page.get_by_role("button", name=nazwa).first
                if k.count() > 0 and k.is_visible():
                    k.click()
                    page.wait_for_timeout(2500)
                    print("  wykrywanie AI wyłączone dla tego posta", flush=True)
                    break

        publikuj = None
        for nazwa in ("Wyślij teraz do wszystkich", "Send to everyone now",
                      "Send now", "Publish now"):
            k = page.get_by_role("button", name=nazwa).first
            if k.count() > 0 and k.is_visible():
                publikuj = k
                print(f"  przycisk publikacji: {nazwa!r}", flush=True)
                break
        wynik["przycisk_widoczny"] = publikuj is not None

        if wyslij and publikuj is not None:
            publikuj.click()
            page.wait_for_timeout(15000)
            wynik["wyslane"] = potwierdz_artykul(page, artykul["tytul"])
            dopisz_wynik("artykul", wynik,
                               tytul=artykul["tytul"])
            print("  ARTYKUŁ POTWIERDZONY U SUBSTACKA" if wynik["wyslane"]
                  else "  KLIKNIĘTE, ALE SUBSTACK GO NIE POKAZUJE", flush=True)
            if wynik["wyslane"]:
                # Artykuł idzie do promowania: jedna notka z linkiem dziennie
                # przez kolejne dni. Zapisujemy TU, bo tylko tutaj wiemy na pewno,
                # że tekst naprawdę jest publiczny.
                import stages
                # ADRES BIERZEMY OD SUBSTACKA, nie zgadujemy z tytulu. Slug bywa
                # skracany: „the-hole-in-your-airplane-window-is-doing-exactly-
                # what-it-should" stalo sie „the-hole-in-your-airplane-window".
                # Zgadniety adres odpowiadal 302, wiec link zyl na przekierowaniu,
                # ktorego nikt nam nie obiecal.
                adres = potwierdz_adres_artykulu(page, artykul["tytul"])
                # I CZYSTY TEKST, nie HTML. Do promptu notki szlo 9000 znakow
                # znacznikow, z ktorych model musial wylowic tresc.
                stages.zapisz_do_promocji(adres, artykul["tytul"],
                                          bez_znacznikow(artykul.get("html", ""))[:2000])
        elif not wyslij:
            print("  (nie wysyłam — tryb sprawdzenia; szkic zapisany)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def potwierdz_odpowiedz(page, note_id: int, tekst: str) -> bool:
    """Pyta Substacka, czy nasza odpowiedź naprawdę jest w wątku."""
    import json as _json

    probka = " ".join(tekst.split())[:60]
    for nr in range(4):
        watek = api_json(page, f"/api/v1/reader/comment/{note_id}/replies"
                               f"?comment_id={note_id}")
        if probka in " ".join(_json.dumps((watek or {}).get("commentBranches", []),
                                          ensure_ascii=False).split()):
            return True
        if nr < 3:
            page.wait_for_timeout(8000)
    return False

def wystaw_odpowiedz(note_id: int, tekst: str, wyslij: bool = False,
                     kontekst: dict[str, Any] | None = None) -> dict[str, Any]:
    """Odpowiada w watku — pod nasza notka albo w cudzej dyskusji.

    `kontekst` jak przy komentarzu: co wiedzielismy o celu, gdy pisalismy.
    """
    wyslij = naprawde_wyslac(wyslij, "odpowiedz")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        if wyslij and potwierdz_odpowiedz(page, note_id, tekst):
            print("  ta odpowiedz juz jest w watku — nie wystawiam drugi raz",
                  flush=True)
            wynik["wyslane"] = True
            wynik["pominiete"] = True
            return wynik

        # Krotki adres dziala dla KAZDEJ notki, takze cudzej — sprawdzone.
        # Dzieki temu ta sama funkcja obsluguje odpowiedz u siebie i wejscie
        # w dyskusje u kogos obcego.
        page.goto(f"https://substack.com/note/c-{note_id}",
                  timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 3000)

        # Pole odpowiedzi otwiera dopiero kliknięcie KONTENERA — kliknięcie w sam
        # napis nic nie robi. Napisy trzymamy w kilku językach, bo interfejs idzie
        # za językiem przeglądarki, a na serwerze będzie inny niż tutaj.
        otwarte = False
        for napis in ("Zostaw odpowiedź", "Leave a reply", "Reply", "Antwort"):
            kand = page.get_by_text(napis, exact=False).first
            if kand.count() == 0:
                continue
            kand.locator("xpath=..").click(timeout=15_000)
            page.wait_for_timeout(3000)
            if page.locator("[contenteditable=true]").count() > 0:
                otwarte = True
                break
        if not otwarte:
            raise RuntimeError("nie otworzyłem pola odpowiedzi")

        page.locator("[contenteditable=true]").first.click(timeout=10_000)
        page.wait_for_timeout(700)
        page.keyboard.type(tekst, delay=12)
        page.wait_for_timeout(1500)
        wynik["wpisane"] = True
        print(f"  wpisane w pole odpowiedzi: {len(tekst.split())} słów", flush=True)

        przycisk = None
        for nazwa in ("Reply", "Odpowiedz", "Post", "Opublikuj", "Wyślij"):
            kandydat = page.get_by_role("button", name=nazwa).first
            if kandydat.count() > 0 and kandydat.is_visible():
                przycisk = kandydat
                print(f"  przycisk wysyłki: {nazwa!r}", flush=True)
                break
        wynik["przycisk_widoczny"] = przycisk is not None

        if wyslij and przycisk is not None:
            przycisk.click()
            page.wait_for_timeout(6000)
            wynik["wyslane"] = potwierdz_odpowiedz(page, note_id, tekst)
            dopisz_wynik("odpowiedz", wynik,
                               gdzie=f"note/c-{note_id}",
                               slow=len(tekst.split()), tekst=tekst[:300],
                               **(kontekst or {}))
            print("  ODPOWIEDŹ POTWIERDZONA W WĄTKU" if wynik["wyslane"]
                  else "  KLIKNIĘTE, ALE ODPOWIEDZI NIE MA W WĄTKU", flush=True)
        elif not wyslij:
            print("  (nie wysyłam — tryb sprawdzenia)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def wystaw_notke(tekst: str, wyslij: bool = False) -> dict[str, Any]:
    """Wystawia notkę. Domyślnie WYPEŁNIA i NIE WYSYŁA.

    `wyslij=False` to nie ostrożność dla samej ostrożności: notki nie da się
    cofnąć w oczach tych, którzy ją zobaczyli. Najpierw sprawdzamy, czy kod
    trafia we właściwe pole, dopiero potem wysyłamy.
    """
    wyslij = naprawde_wyslac(wyslij, "notka")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        # Czy tej notki juz nie wystawilismy? Pytamy RZECZYWISTOSCI, a nie
        # wlasnej ksiegowosci: proces przerwany po klknieciu, a przed zapisem,
        # zostawilby ksiegowosc niezgodna ze stanem faktycznym. Substack wie
        # lepiej niz my, co u nas wisi.
        if wyslij and potwierdz_notke(page, tekst):
            print("  ta notka juz jest na profilu — nie wystawiam drugi raz",
                  flush=True)
            wynik["wyslane"] = True
            wynik["pominiete"] = True
            return wynik

        page.goto("https://substack.com/home", timeout=READ_TIMEOUT_MS,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS)

        # Kompozytor nie jest ani polem, ani przyciskiem w sensie roli ARIA —
        # trafia w niego dopiero kliknięcie. Szukamy go po STRUKTURZE, nie po
        # napisie: Substack podaje interfejs w języku przeglądarki, więc zaszyte
        # "What's on your mind?" przestało działać, gdy ten sam profil otworzył
        # się po polsku. Na serwerze locale będzie jeszcze inne.
        otwarty = False
        for sel in ("[class*=Composer]", "[class*=composer]"):
            kand = page.locator(sel).first
            if kand.count() > 0:
                kand.click(timeout=15_000)
                otwarty = True
                break
        if not otwarty:
            # Ostatnia deska: napisy, które znamy. Gdy i to padnie, lepiej rzucić
            # wyjątkiem niż wpisać notkę w przypadkowe pole.
            for napis in ("What's on your mind?", "O czym", "Was beschäftigt"):
                kand = page.get_by_text(napis, exact=False).first
                if kand.count() > 0:
                    kand.click(timeout=15_000)
                    otwarty = True
                    break
        if not otwarty:
            raise RuntimeError("nie znalazłem kompozytora notek")
        page.wait_for_timeout(2500)
        pole = page.locator("[contenteditable=true]").first
        pole.click(timeout=10_000)
        page.wait_for_timeout(800)
        page.keyboard.type(tekst, delay=12)
        page.wait_for_timeout(1500)
        wynik["wpisane"] = True
        print(f"  wpisane w pole notki: {len(tekst.split())} słów", flush=True)

        # Tu też nie zakładamy angielskiego interfejsu.
        przycisk = None
        for nazwa in ("Post", "Opublikuj", "Wyślij", "Publish", "Veröffentlichen"):
            kandydat = page.get_by_role("button", name=nazwa).first
            if kandydat.count() > 0 and kandydat.is_visible():
                przycisk = kandydat
                print(f"  przycisk wysyłki: {nazwa!r}", flush=True)
                break
        wynik["przycisk_widoczny"] = przycisk is not None
        print(f"  przycisk wysyłki widoczny: {wynik['przycisk_widoczny']}", flush=True)

        if wyslij and wynik["przycisk_widoczny"]:
            odpowiedzi = sluchaj_publikacji(page)
            przycisk.click()
            page.wait_for_timeout(6000)
            kody = [r.status for r in odpowiedzi]
            # Najpierw pytamy o odpowiedz Substacka na sam zapis — jest
            # natychmiastowa. Kanal profilu sprawdzamy tylko wtedy, gdy
            # odpowiedzi nie zlapalismy.
            if any(k == 200 for k in kody):
                wynik["wyslane"] = True
                print("  NOTKA PRZYJETA (odpowiedz Substacka: 200)", flush=True)
            else:
                wynik["wyslane"] = potwierdz_notke(page, tekst)
                print("  NOTKA POTWIERDZONA NA PROFILU" if wynik["wyslane"]
                      else f"  NIE WYSZLA (odpowiedzi: {kody or 'brak'})",
                      flush=True)
            wynik["id"] = id_z_odpowiedzi(odpowiedzi)
            if wynik["wyslane"]:
                print("  id notki: %s" % (wynik["id"] or
                      "NIE ODCZYTANY — reakcji nie da sie z nia polaczyc"),
                      flush=True)
            dopisz_wynik("notka", wynik, slow=len(tekst.split()),
                         tekst=tekst[:300], id=wynik["id"])
        elif not wyslij:
            print("  (nie wysyłam — tryb sprawdzenia)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        # DOMKNIECIE: jesli sciezka sukcesu nie zdazyla zapisac — bo wyjatek
        # albo bo nie bylo przycisku — porazka i tak trafia do dziennika.
        if wyslij:
            dopisz_wynik("notka", wynik, slow=len(tekst.split()),
                         tekst=tekst[:300], id=wynik.get("id", ""))
        page.close()
        browser.close()
        p.stop()
    return wynik


def mozna_komentowac(url: str) -> bool:
    """Czy pod tym tekstem wolno nam w ogóle napisać.

    Trzy komentarze dziennie przepadały u publikacji, które CZYTAC pozwalaja
    wszystkim, a KOMENTOWAC tylko placacym. Klikniecie nic nie robilo, a caly
    koszt byl juz poniesiony: pobranie strony, trzy warianty komentarza
    i sprawdzenie faktow. Gorzej — kazde takie podejscie zjadalo miejsce
    z dziennego limitu, wiec realnie wychodzily trzy komentarze mniej.

    Substack mowi o tym w polu `write_comment_permissions`, dostepnym ZANIM
    cokolwiek napiszemy. Wystarczylo zapytac.

    Przy watpliwosci odpowiadamy TAK. Blad w te strone kosztuje jedno nieudane
    klikniecie; blad w druga zamyka agentowi usta wszedzie tam, gdzie pole ma
    wartosc, ktorej nie znamy.
    """
    if "/note/c-" in url:
        return True                   # pod notkami komentuje kazdy
    from urllib.parse import urlparse

    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        post = api_json(page, f"/api/v1/posts/{slug}",
                        baza=f"https://{urlparse(url).netloc}")
        if not isinstance(post, dict):
            return True
        prawo = str(post.get("write_comment_permissions") or "").lower()
        if prawo in {"only_paid", "only_founding", "none", "no_one"}:
            print(f"  komentarze tylko dla placacych ({prawo}) — odpuszczam"
                  f" przed pisaniem", flush=True)
            return False
        return True
    except Exception:
        return True                   # nie wiem, wiec probuje
    finally:
        page.close()
        browser.close()
        p.stop()


def uchwyt_publikacji(host: str) -> str | None:
    """Nazwa konta do obserwowania — z hosta albo, gdy trzeba, z API.

    `host.split(".")[0]` dziala wylacznie dla adresow w domenie Substacka. Przy
    wlasnej domenie (`www.slowboring.com`) dawalo **"www"** i agent probowal
    obserwowac konto o takiej nazwie: trzy z czterech subskrypcji dziennie szly
    w prozne, a dziennik pokazywal `komu='www'` trzy razy pod rzad.

    Publikacja na wlasnej domenie i tak ma konto w Substacku, a jego nazwa stoi
    w `publishedBylines` dowolnego jej posta. Gdy nie da sie ustalic, zwracamy
    None — lepiej nie obserwowac nikogo niz obserwowac nieistniejace konto.
    """
    host = (host or "").strip().lower().rstrip("/")
    if not host:
        return None
    if host.endswith(".substack.com"):
        return host.split(".")[0]

    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        posty = api_json(page, "/api/v1/posts?limit=1", baza=f"https://{host}")
        lista = posty if isinstance(posty, list) else (posty or {}).get("posts") or []
        for post in lista:
            for bylina in (post or {}).get("publishedBylines") or []:
                uchwyt = (bylina or {}).get("handle")
                if uchwyt:
                    return str(uchwyt)
        return None
    except Exception:
        return None
    finally:
        page.close()
        browser.close()
        p.stop()


def juz_sie_odezwalismy(page, url: str) -> bool:
    """Czy JUZ napisalismy cokolwiek pod tym postem albo pod ta notka.

    Najostrzejszy sygnal automatu, jaki mozna dac: dwa wlasne komentarze pod
    jednym tekstem, w odstepie godzin, a miedzy nimi nikt sie nie odezwal.
    Czlowiek nie wraca dopisywac drugiego eseju pod cudzym postem, na ktory nikt
    nie odpowiedzial.

    Pytamy o to RZECZYWISTOSCI, a nie wlasnej ksiegowosci: zapis moze sie
    rozjechac, Substack wie na pewno.
    """
    from urllib.parse import urlparse

    profil = api_json(page, f"/api/v1/user/{PROFIL_HANDLE}/public_profile")
    moje_id = (profil or {}).get("id")
    if not moje_id:
        return True          # nie wiem, czyli nie ryzykuje

    if "/note/c-" in url:                    # notka
        nid = url.rstrip("/").rsplit("c-", 1)[-1]
        watek = api_json(page, f"/api/v1/reader/comment/{nid}/replies"
                               f"?comment_id={nid}") or {}
        wszystkie = [c for g in (watek.get("commentBranches") or [])
                     for c in _plaskie(g)]
    else:                                    # artykul cudzy
        czyja = f"https://{urlparse(url).netloc}"
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        post = api_json(page, f"/api/v1/posts/{slug}", baza=czyja)
        if not isinstance(post, dict) or not post.get("id"):
            return False
        dane = api_json(page, f"/api/v1/post/{post['id']}/comments"
                              "?all_comments=true", baza=czyja)
        wszystkie = dane if isinstance(dane, list) else (dane or {}).get("comments") or []

    return any(isinstance(c, dict) and c.get("user_id") == moje_id
               for c in wszystkie)


def bez_znacznikow(html: str) -> str:
    """Sam tekst, bez HTML-a. Do promptu notki promujacej szlo 9000 znakow
    znacznikow, z ktorych model musial wylowic tresc."""
    import re as _re

    tekst = _re.sub(r"<[^>]+>", " ", html or "")
    tekst = tekst.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return _re.sub(r"\s+", " ", tekst).strip()


def potwierdz_adres_artykulu(page, tytul: str) -> str:
    """Prawdziwy adres opublikowanego artykulu — od Substacka, nie z tytulu.

    Adres byl skladany przez zamiane tytulu na slug, a Substack slugi SKRACA:
    „The Hole in Your Airplane Window Is Doing Exactly What It Should" dostalo
    adres `/p/the-hole-in-your-airplane-window`. Zgadniety adres odpowiadal 302,
    wiec notka promujaca dzialala tylko dzieki przekierowaniu, ktorego Substack
    nam nie obiecal. Notka promujaca z martwym linkiem jest gorsza niz jej brak.

    Gdyby odczyt zawiodl, wracamy do zgadywania — lepszy link na przekierowaniu
    niz zaden.
    """
    import re as _re

    baza = f"https://{config.SUBSTACK_HANDLE}.substack.com"
    zapasowy = (f"{baza}/p/"
                + _re.sub(r"[^a-z0-9]+", "-", (tytul or "").lower()).strip("-"))
    try:
        dane = api_json(page, "/api/v1/posts?limit=5", baza=baza)
        lista = dane if isinstance(dane, list) else (dane or {}).get("posts") or []
        for post in lista:
            if (post or {}).get("title") == tytul:
                adres = post.get("canonical_url") or (
                    f"{baza}/p/{post.get('slug')}" if post.get("slug") else "")
                if adres:
                    print(f"  adres artykulu wg Substacka: {adres}", flush=True)
                    return adres
    except Exception as exc:
        print(f"  (nie odczytalem adresu: {type(exc).__name__})", flush=True)
    print(f"  adres zlozony z tytulu (zapasowo): {zapasowy}", flush=True)
    return zapasowy


def potwierdz_komentarz(page, url: str, tekst: str) -> int | None:
    """Pyta Substacka, czy komentarz naprawdę wisi — zamiast wierzyć kliknięciu.

    Oddaje NUMER naszego komentarza, nie samo „tak". Numer jest potrzebny, zeby
    pozniej dopisac do dziennika, co z tego komentarza wyszlo: kanal aktywnosci
    mowi o polubieniach i odpowiedziach wlasnie numerami. Bez tego wiemy tylko,
    ze cos napisalismy, a nie czy ktokolwiek to zauwazyl.

    Numer jest prawdziwy, wiec nadal dziala jak „tak"; brak to None.

    Gdy komentarz JEST, ale odpowiedz nie podaje numeru, oddajemy -1, nie None.
    Ta funkcja pilnuje takze, zeby nie napisac drugi raz pod tym samym tekstem,
    a None znaczyloby „nie ma" i agent dopisalby kolejny komentarz — czyli
    dokladnie ten podpis bota, ktorego unikamy.
    """
    from urllib.parse import urlparse

    probka = " ".join(tekst.split())[:60]

    # NOTKA TO NIE ARTYKUL i nie ma jej pod adresem artykulow. Ostatni czlon
    # adresu notki wyglada jak slug (`c-315876268`), wiec pytanie szlo do
    # /api/v1/posts/c-315876268 i wracalo bledem HTTP. Skutek: komentarz pod
    # notka NIGDY nie zostawal potwierdzony, nawet gdy poszedl. `juz_sie_odezwalismy`
    # rozroznialo te dwa przypadki od poczatku — tutaj tego zabraklo.
    if "/note/c-" in url:
        nid = url.rstrip("/").rsplit("c-", 1)[-1]
        for nr in range(4):
            watek = api_json(page, f"/api/v1/reader/comment/{nid}/replies"
                                   f"?comment_id={nid}") or {}
            wszystkie = [c for g in (watek.get("commentBranches") or [])
                         for c in _plaskie(g)]
            for c in wszystkie:
                if probka in " ".join((c.get("body") or "").split()):
                    return c.get("id") or -1
            if nr < 3:
                page.wait_for_timeout(8000)
        return None

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    czyja = f"https://{urlparse(url).netloc}"        # publikacja AUTORA posta
    post = api_json(page, f"/api/v1/posts/{slug}", baza=czyja)
    if not isinstance(post, dict) or not post.get("id"):
        return None
    # Kilka prob, bo lista komentarzy — jak kanal profilu — aktualizuje sie
    # z opoznieniem, a falszywe "nie ma" rozbraja ochrone przed dublowaniem.
    for nr in range(4):
        dane = api_json(page, f"/api/v1/post/{post['id']}/comments?all_comments=true",
                        baza=czyja)
        lista = dane if isinstance(dane, list) else (dane or {}).get("comments") or []
        for k in lista:
            if isinstance(k, dict) and probka in " ".join(
                    (k.get("body") or "").split()):
                return k.get("id") or -1
        if nr < 3:
            page.wait_for_timeout(8000)
    return None

def wystaw_komentarz(url: str, tekst: str, wyslij: bool = False,
                     kontekst: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wystawia komentarz pod cudzym postem. Domyślnie WYPEŁNIA i NIE WYSYŁA.

    `kontekst` to wszystko, co WIEMY O CELU w chwili pisania: skad go mamy, ile
    komentarzy juz tam bylo, jaka publicznosc, jak stary tekst. Dziennik zapisywal
    tylko, ze cos napisalismy — a po dwoch dniach jedyne pytanie, ktore ma
    znaczenie, brzmi: czy warto bylo. Bez tych liczb nie da sie na nie odpowiedziec,
    a kosztuja zero, bo mamy je juz w reku i dotad je wyrzucalismy.
    """
    wyslij = naprawde_wyslac(wyslij, "komentarz")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        if wyslij and juz_sie_odezwalismy(page, url):
            print("  JUZ SIE TAM ODEZWALISMY — drugi komentarz pod tym samym"
                  " tekstem to podpis bota, odpuszczam", flush=True)
            wynik["wyslane"] = True
            wynik["pominiete"] = True
            return wynik

        if wyslij and potwierdz_komentarz(page, url, tekst):
            print("  ten komentarz juz tam wisi — nie wystawiam drugi raz",
                  flush=True)
            wynik["wyslane"] = True
            wynik["pominiete"] = True
            return wynik

        page.goto(url, timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 2000)

        # Sekcja komentarzy doczytuje się dopiero po przewinięciu w dół.
        page.mouse.wheel(0, 20_000)
        page.wait_for_timeout(3500)

        # Pod postem pole komentarza to TEXTAREA, nie contenteditable jak przy
        # notkach — to dwa różne edytory i jeden selektor nie obsłuży obu.
        #
        # PIERWSZA W DOM TO NIE ZAWSZE TA WŁAŚCIWA. `locator("textarea").first`
        # brał pierwszą textarea w drzewie niezależnie od tego, czy jest
        # widoczna. Gdy pola komentarza nie było wcale — a zdarza się to na
        # postach, których API nie oddaje `write_comment_permissions`, więc
        # zapora przepuszcza je zgodnie z zasadą „przy wątpliwości próbuję" —
        # Playwright czekał pełne 15 sekund na aktywność elementu, którego nie
        # ma, i kończył wyjątkiem. Zdarzyło się to dwa razy pierwszego dnia na
        # produkcji: scalesignals i glowwithella.
        #
        # Bierzemy pierwszą WIDOCZNĄ, a brak pola mówimy wprost zamiast
        # wywracać się na czasie. Wyjątek i tak nie niósł żadnej informacji
        # poza nazwą lokatora.
        pole = None
        for i in range(page.locator("textarea").count()):
            kandydat = page.locator("textarea").nth(i)
            try:
                if kandydat.is_visible():
                    pole = kandydat
                    break
            except Exception:
                continue
        if pole is None:
            wynik["blad"] = "nie ma pola komentarza pod tym postem"
            print(f"  {wynik['blad']} — odpuszczam", flush=True)
            return wynik
        pole.click(timeout=8_000)
        page.wait_for_timeout(800)
        page.keyboard.type(tekst, delay=12)
        page.wait_for_timeout(1500)
        wynik["wpisane"] = True
        print(f"  wpisane w pole komentarza: {len(tekst.split())} słów", flush=True)

        # Interfejs bywa po polsku, więc szukamy obu wariantów nazwy.
        przycisk = None
        for nazwa in ("Post", "Opublikuj", "Wyślij", "Comment", "Skomentuj"):
            kandydat = page.get_by_role("button", name=nazwa).first
            if kandydat.count() > 0 and kandydat.is_visible():
                przycisk = kandydat
                print(f"  przycisk wysyłki: {nazwa!r}", flush=True)
                break
        wynik["przycisk_widoczny"] = przycisk is not None
        print(f"  przycisk wysyłki widoczny: {wynik['przycisk_widoczny']}", flush=True)

        if wyslij and wynik["przycisk_widoczny"]:
            przycisk.click()
            page.wait_for_timeout(6000)
            # Kliknięcie przycisku nie jest dowodem, że komentarz został przyjęty,
            # a agent bez człowieka nie ma komu tego sprawdzić. Pytamy więc Substacka.
            # Strony nie da się do tego użyć: komentarze doklejają się po stronie
            # klienta i inner_text ich nie widzi — sprawdzenie po tekscie strony dało
            # fałszywy alarm przy pierwszym realnym komentarzu, który naprawdę wisiał.
            nasz_numer = potwierdz_komentarz(page, url, tekst)
            wynik["wyslane"] = nasz_numer is not None
            wynik["id"] = nasz_numer
            dopisz_wynik("komentarz", wynik, gdzie=url,
                               slow=len(tekst.split()), tekst=tekst[:300],
                               nasz_id=nasz_numer, **(kontekst or {}))
            print("  KOMENTARZ POTWIERDZONY U SUBSTACKA" if wynik["wyslane"]
                  else "  KLIKNIĘTE, ALE SUBSTACK GO NIE POKAZUJE", flush=True)
        elif not wyslij:
            print("  (nie wysyłam — tryb sprawdzenia)", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


if __name__ == "__main__":
    import sys

    polecenie = sys.argv[1] if len(sys.argv) > 1 else "sesja"
    {
        "sesja": sprawdz_sesje,      # podłącz się do Chrome'a właściciela
        "zaloguj": zaloguj,          # stara droga, zapętla CAPTCHĘ — nie używać
        "rozpoznanie": rozpoznanie,
        "serwer": sprawdz_serwer,    # jedyne pytanie: czy sesja żyje z tego adresu
    }[polecenie]()


def read_pages(urls: list[str]) -> list[dict[str, Any]]:
    """Otwiera strony w przeglądarce i zwraca ich widoczny tekst.

    Jedna instancja przeglądarki na całą listę — start Chromium to sekundy,
    a stron bywa kilkanaście.
    """
    from playwright.sync_api import sync_playwright

    out: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=config.FETCH_USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        for url in urls:
            entry: dict[str, Any] = {"url": url, "text": "", "title": "", "error": None}
            try:
                page.goto(url, timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(SETTLE_MS)  # treść dorysowuje się po JS
                entry["title"] = page.title()
                entry["text"] = page.inner_text("body")
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            out.append(entry)
            print(
                f"  [przeglądarka] {'OK  ' if not entry['error'] else 'NIE '} "
                f"{len(entry['text']):>7} znaków  {url[:58]}"
                f"{'  ' + entry['error'] if entry['error'] else ''}",
                flush=True,
            )
        context.close()
        browser.close()
    return out


def restackuj_w_kanale(
    ile: int, decyzja, wyslij: bool = False,
) -> dict[str, Any]:
    """Podaje dalej cudze notki z wlasnym zdaniem.

    `decyzja` to funkcja (notka: dict) -> dict, ktora oddaje
    {"restack": bool, "sentence": str, "reason": str}. Decyzja siedzi POZA ta
    funkcja, bo tu jest tylko klikanie — a o tym, czy warto, decyduje etap
    `stages.ocen_restack`, ktory da sie przetestowac bez przegladarki.

    Sciezka ustalona na zywym Substacku, nie zgadnieta:
      przycisk `Restack` ma aria-haspopup="menu", wiec NIE restackuje od razu,
      tylko rozwija menu z pozycjami `Restack`, `Restack with a note`
      i `View restacks`. Bierzemy druga — samo podanie dalej bez zdania nic
      nie wnosi, a to zdanie jest calym sensem tej akcji.

    Odstepy sa dluzsze niz przy polubieniach (10-30 min), bo restack wymaga
    PRZECZYTANIA cudzej notki. Cztery restacki w dwie minuty to nie jest
    czytanie i widac to na profilu tak samo, jak widac bylo notki parami.
    """
    import random

    wyslij = naprawde_wyslac(wyslij, "restacki")
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"znalezione": 0, "rozwazone": 0, "restackowane": 0,
                             "odmowy": [], "blad": None}
    try:
        page.goto("https://substack.com/", timeout=READ_TIMEOUT_MS * 2,
                  wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 6000)

        przyciski = page.get_by_role("button", name="Restack")
        wynik["znalezione"] = przyciski.count()
        print(f"  notek w kanale do rozwazenia: {wynik['znalezione']}", flush=True)

        for i in range(min(ile * 4, przyciski.count())):
            if wynik["restackowane"] >= ile:
                break
            kandydat = przyciski.nth(i)
            try:
                if not kandydat.is_visible():
                    continue
                # Tresc notki bierzemy z KONTENERA wokol przycisku. Bez niej
                # decyzja bylaby losowaniem, a nie ocena.
                notka = _notka_przy_przycisku(kandydat)
                if not notka.get("tekst"):
                    continue
                wynik["rozwazone"] += 1
                ocena = decyzja(notka)
                if not ocena.get("restack"):
                    powod = str(ocena.get("reason", ""))[:90]
                    wynik["odmowy"].append(powod)
                    print(f"    pomijam: {powod}", flush=True)
                    continue

                zdanie = ocena["sentence"]
                print(f"    RESTACK u {notka.get('autor', '?')[:24]}: {zdanie[:90]}",
                      flush=True)
                if not wyslij:
                    wynik["restackowane"] += 1
                    continue

                # ODSTEP STOI PRZED KOLEJNYM RESTACKIEM, NIE PO POPRZEDNIM.
                # Wczesniej czekalo sie na koncu ciala petli, a warunek wyjscia
                # sprawdza sie dopiero na gorze nastepnego obrotu — wiec agent
                # po wykonaniu normy spal jeszcze 10-30 minut z otwarta
                # przegladarka i dopiero wtedy wychodzil. Przy limicie jednego
                # restacka na przebieg, czyli w typowym przypadku, kazda taka
                # przerwa byla pusta w calosci.
                #
                # Samo „przerwij po wykonaniu normy" NIE WYSTARCZALO i zlapal to
                # dopiero test: gdy w kanale bylo mniej notek niz wynosil budzet,
                # norma nie byla wykonana, wiec petla i tak zasypiala, a zaraz
                # potem konczyla sie z braku kandydatow. Odstep postawiony PRZED
                # dziala w obu przypadkach, bo czeka tylko ten, kto naprawde ma
                # zaraz kliknac.
                if wynik["restackowane"]:
                    page.wait_for_timeout(
                        int(random.uniform(*config.ODSTEPY["restack"]) * 1000))

                kandydat.scroll_into_view_if_needed(timeout=8000)
                kandydat.click(timeout=8000)
                page.wait_for_timeout(1500)
                page.get_by_role("menuitem", name="Restack with a note").click(
                    timeout=8000)
                page.wait_for_timeout(SETTLE_MS)
                pole = page.get_by_role("textbox").last
                pole.click(timeout=8000)
                pole.type(zdanie, delay=random.randint(18, 45))
                page.wait_for_timeout(1200)
                # Substack nazywa przycisk wyslania "Post" — szukamy go
                # WEWNATRZ okna, nie w calym kanale, zeby nie trafic w cudzy.
                page.get_by_role("button", name="Post").last.click(timeout=8000)
                page.wait_for_timeout(SETTLE_MS + 2000)
                wynik["restackowane"] += 1
                zapisz_w_dzienniku("restack", udane=True,
                                   komu=notka.get("autor", ""), slow=len(zdanie.split()))
                print(f"    podane dalej {wynik['restackowane']}/{ile}", flush=True)
            except Exception as exc:
                # Tak samo jak przy polubieniach: porazka szla do logu i nigdzie
                # indziej. Restacki chodza na 33% normy — bez tego wpisu nie ma
                # jak stwierdzic, czy to brak kandydatow w kanale, czy zmieniony
                # interfejs Substacka.
                powod = f"{type(exc).__name__}: {exc}"[:140]
                print(f"    (pominiete: {type(exc).__name__}: {exc}"[:150] + ")",
                      flush=True)
                zapisz_w_dzienniku("restack", udane=False, powod=powod,
                                   komu=notka.get("autor", ""))
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(600)
                except Exception:
                    pass
        if not wyslij:
            print(f"  (nie klikam — tryb sprawdzenia; podalbym dalej"
                  f" {wynik['restackowane']})", flush=True)
    except Exception as exc:
        wynik["blad"] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"  BŁĄD: {wynik['blad']}", flush=True)
    finally:
        page.close()
        browser.close()
        p.stop()
    return wynik


def _notka_przy_przycisku(przycisk) -> dict[str, str]:
    """Tresc i autor notki, przy ktorej stoi ten przycisk.

    Wchodzimy w gore drzewa, dopoki kontener nie zrobi sie na tyle duzy, zeby
    obejmowac cala notke. Szukanie po klasach odpada: Substack generuje je
    losowo (`container-_91AK1`), wiec selektor po klasie padnie przy pierwszym
    wdrozeniu po ich stronie.
    """
    try:
        dane = przycisk.evaluate(
            """e => {
                let n = e;
                for (let i = 0; i < 8 && n.parentElement; i++) {
                    n = n.parentElement;
                    if (n.innerText && n.innerText.length > 120) break;
                }
                const t = (n.innerText || '').trim();
                const a = n.querySelector('a[href*="/@"], a[href*="substack.com/profile"]');
                return {tekst: t, autor: a ? (a.innerText || '').trim() : ''};
            }"""
        )
    except Exception:
        return {}
    tekst = str(dane.get("tekst") or "")
    # Obcinamy ogon interfejsu: nazwy przyciskow trafiaja do innerText.
    for smiec in ("\nLike\n", "\nComment\n", "\nRestack\n", "\nShare\n"):
        tekst = tekst.replace(smiec, "\n")
    return {"tekst": tekst.strip()[:1800], "autor": str(dane.get("autor") or "")[:80]}
