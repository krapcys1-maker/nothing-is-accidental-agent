"""Czytanie stron przeglądarką — tam, gdzie zwykły HTTP nie wystarcza.

Substack renderuje treść JavaScriptem: w HTML-u jest 148 KB, a czytelnego
tekstu 371 znaków, bo post siedzi w blobie JSON. Zwykły pobieracz zobaczy
pustą skorupę.

Czytamy WYŁĄCZNIE publiczne strony, bez logowania i bez sesji. Agent otwiera
je tak jak każdy czytelnik. Publikowanie, komentowanie i polubienia nie
istnieją w tym pliku i nie powstaną bez osobnej decyzji właściciela.
"""

from __future__ import annotations

from typing import Any

import config

READ_TIMEOUT_MS = 45_000
SETTLE_MS = 2_500

# Plik sesji. Powstaje, gdy WŁAŚCICIEL zaloguje się własnoręcznie w otwartym
# oknie. Hasło nie przechodzi przez ten kod ani przez nic, co ja czytam.
# `.gitignore` obejmuje ten wzorzec od początku projektu.
SESSION_FILE = config.DATA_DIR / "storage-state.json"


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
        page.goto("https://substack.com/sign-in", timeout=READ_TIMEOUT_MS)
        input("   [naciśnij Enter, gdy będziesz zalogowany] ")
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

    checks = [
        ("kim jestem", "https://substack.com/home"),
        ("feed notek", "https://substack.com/notes"),
        ("moja publikacja", "https://substack.com/@nothingisaccidental"),
        ("edytor artykułu", "https://substack.com/publish/post"),
        ("kogo obserwuję", "https://substack.com/inbox"),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(SESSION_FILE), viewport={"width": 1400, "height": 1200}
        )
        page = context.new_page()
        for name, url in checks:
            try:
                page.goto(url, timeout=READ_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(SETTLE_MS)
                text = page.inner_text("body")
                logged_out = "sign in" in text.lower()[:300]
                posts = len({u for u in page.eval_on_selector_all(
                    'a[href*="/p/"]', "e=>e.map(x=>x.href)")})
                buttons = [b.strip() for b in page.eval_on_selector_all(
                    "button", "e=>e.map(x=>x.innerText)") if b.strip()][:8]
                print(
                    f"  {name:20} {'WYLOGOWANY' if logged_out else 'zalogowany':11} "
                    f"tekst={len(text):>6} postów={posts:>3}",
                    flush=True,
                )
                if buttons:
                    print(f"     przyciski: {', '.join(buttons)[:110]}", flush=True)
            except Exception as exc:
                print(f"  {name:20} BŁĄD {type(exc).__name__}", flush=True)
        context.close()
        browser.close()


if __name__ == "__main__":
    import sys

    polecenie = sys.argv[1] if len(sys.argv) > 1 else "rozpoznanie"
    {"zaloguj": zaloguj, "rozpoznanie": rozpoznanie}[polecenie]()


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
