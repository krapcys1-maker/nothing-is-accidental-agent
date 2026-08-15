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
