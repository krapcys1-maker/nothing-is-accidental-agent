"""Czytanie stron przeglądarką — tam, gdzie zwykły HTTP nie wystarcza.

Substack renderuje treść JavaScriptem: w HTML-u jest 148 KB, a czytelnego
tekstu 371 znaków, bo post siedzi w blobie JSON. Zwykły pobieracz zobaczy
pustą skorupę.

Czytamy WYŁĄCZNIE publiczne strony, bez logowania i bez sesji. Agent otwiera
je tak jak każdy czytelnik. Publikowanie, komentowanie i polubienia nie
istnieją w tym pliku i nie powstaną bez osobnej decyzji właściciela.
"""

from __future__ import annotations

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
_JS_NIEODPOWIEDZIANE = """
async ([handle, ile]) => {
    const pr = await (await fetch('/api/v1/user/' + handle + '/public_profile',
                                  {credentials: 'include'})).json();
    if (!pr || !pr.id) return {blad: 'brak profilu'};
    const feed = await (await fetch('/api/v1/reader/feed/profile/' + pr.id +
                                    '?types%5B%5D=note',
                                    {credentials: 'include'})).json();
    const nasze = (feed.items || [])
        .map(x => x.comment).filter(c => c && c.children_count > 0)
        .slice(0, ile);
    const czekaja = [];
    for (const n of nasze) {
        const t = await (await fetch('/api/v1/reader/comment/' + n.id +
                                     '/replies?comment_id=' + n.id,
                                     {credentials: 'include'})).json();
        for (const galaz of (t.commentBranches || [])) {
            const plaskie = [];
            (function chodz(w) {
                if (!w) return;
                const c = w.comment || w;
                if (c && c.body) plaskie.push(c);
                (w.descendantComments || w.children || []).forEach(chodz);
            })(galaz);
            if (!plaskie.length) continue;
            const ostatni = plaskie[plaskie.length - 1];
            // Jeśli ostatni głos w gałęzi jest nasz, rozmowa nie czeka na nas.
            if (ostatni.user_id === pr.id) continue;
            czekaja.push({
                pod_czym: (n.body || '').slice(0, 400),
                pod_id: n.id,
                autor: ostatni.name,
                jezyk: ostatni.language,
                tekst: ostatni.body || '',
                id: ostatni.id,
                data: ostatni.date,
            });
        }
    }
    return {czekaja};
}
"""


def nieodpowiedziane(ile: int = 10) -> list[dict[str, Any]]:
    """Cudze odpowiedzi pod naszymi notkami, na które jeszcze nie odpisaliśmy."""
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    try:
        page.goto(f"https://substack.com/@{PROFIL_HANDLE}",
                  timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS)
        wynik = page.evaluate(_JS_NIEODPOWIEDZIANE, [PROFIL_HANDLE, ile])
        czekaja = wynik.get("czekaja", []) if isinstance(wynik, dict) else []
        print(f"  czeka na odpowiedź: {len(czekaja)}", flush=True)
        for c in czekaja:
            print(f"    · {c['autor']} [{c.get('jezyk')}] {c['tekst'][:70]}", flush=True)
        return czekaja
    finally:
        page.close()
        browser.close()
        p.stop()


def potwierdz_notke(page, tekst: str) -> bool:
    """Pyta Substacka, czy notka naprawdę wisi na naszym profilu."""
    probka = " ".join(tekst.split())[:60]
    try:
        return bool(page.evaluate(
            """async ([handle, probka]) => {
                const pr = await (await fetch('/api/v1/user/' + handle + '/public_profile',
                                              {credentials: 'include'})).json();
                if (!pr || !pr.id) return false;
                const f = await (await fetch('/api/v1/reader/feed/profile/' + pr.id +
                                             '?types%5B%5D=note',
                                             {credentials: 'include'})).json();
                const norm = s => (s || '').replace(/\\s+/g, ' ');
                return (f.items || []).some(
                    x => norm(JSON.stringify(x)).includes(probka));
            }""",
            [PROFIL_HANDLE, probka],
        ))
    except Exception as exc:
        print(f"  (nie udało się potwierdzić notki: {exc})"[:160], flush=True)
        return False


def potwierdz_odpowiedz(page, note_id: int, tekst: str) -> bool:
    """Pyta Substacka, czy nasza odpowiedź naprawdę jest w wątku."""
    probka = " ".join(tekst.split())[:60]
    try:
        return bool(page.evaluate(
            """async ([id, probka]) => {
                const t = await (await fetch('/api/v1/reader/comment/' + id +
                                             '/replies?comment_id=' + id,
                                             {credentials: 'include'})).json();
                const norm = s => (s || '').replace(/\\s+/g, ' ');
                return norm(JSON.stringify(t.commentBranches || [])).includes(probka);
            }""",
            [note_id, probka],
        ))
    except Exception as exc:
        print(f"  (nie udało się potwierdzić odpowiedzi: {exc})"[:160], flush=True)
        return False


def wystaw_odpowiedz(note_id: int, tekst: str, wyslij: bool = False) -> dict[str, Any]:
    """Odpowiada w wątku pod naszą własną notką."""
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        page.goto(f"https://substack.com/@{PROFIL_HANDLE}/note/c-{note_id}",
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
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
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
            przycisk.click()
            page.wait_for_timeout(6000)
            wynik["wyslane"] = potwierdz_notke(page, tekst)
            print("  NOTKA POTWIERDZONA NA PROFILU" if wynik["wyslane"]
                  else "  KLIKNIĘTE, ALE NOTKI NIE MA NA PROFILU", flush=True)
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


def potwierdz_komentarz(page, url: str, tekst: str) -> bool:
    """Pyta Substacka, czy komentarz naprawdę wisi — zamiast wierzyć kliknięciu."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    probka = " ".join(tekst.split())[:60]
    try:
        return bool(page.evaluate(
            """async ([slug, probka]) => {
                const p = await (await fetch('/api/v1/posts/' + slug,
                                             {credentials: 'include'})).json();
                if (!p || !p.id) return false;
                const c = await (await fetch('/api/v1/post/' + p.id +
                                             '/comments?all_comments=true',
                                             {credentials: 'include'})).json();
                const lista = c.comments || c || [];
                const norm = s => (s || '').replace(/\\s+/g, ' ');
                return lista.some(k => norm(k.body).includes(probka));
            }""",
            [slug, probka],
        ))
    except Exception as exc:
        print(f"  (nie udało się potwierdzić u Substacka: {exc})"[:160], flush=True)
        return False


def wystaw_komentarz(url: str, tekst: str, wyslij: bool = False) -> dict[str, Any]:
    """Wystawia komentarz pod cudzym postem. Domyślnie WYPEŁNIA i NIE WYSYŁA."""
    wymagaj_sesji()
    p, browser, context = podlacz_sie()
    page = context.new_page()
    wynik: dict[str, Any] = {"wpisane": False, "wyslane": False, "blad": None}
    try:
        page.goto(url, timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
        page.wait_for_timeout(SETTLE_MS + 2000)

        # Sekcja komentarzy doczytuje się dopiero po przewinięciu w dół.
        page.mouse.wheel(0, 20_000)
        page.wait_for_timeout(3500)

        # Pod postem pole komentarza to TEXTAREA, nie contenteditable jak przy
        # notkach — to dwa różne edytory i jeden selektor nie obsłuży obu.
        pole = page.locator("textarea").first
        pole.click(timeout=15_000)
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
            wynik["wyslane"] = potwierdz_komentarz(page, url, tekst)
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
