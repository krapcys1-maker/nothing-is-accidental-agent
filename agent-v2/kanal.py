"""Kanal czytelnika — jedyne zrodlo celow do komentowania.

Osobny plik, bo to jest CZYTANIE CUDZYCH tresci przez zalogowana sesje, a nie
publikowanie: browser.py rosl juz do tysiaca linii i mieszanie w nim odczytu
z dzialaniem utrudnialo czytanie obu.
"""

from __future__ import annotations

from typing import Any

import browser
import config

JS_KANAL = """
() => null
"""


def posty_z_kanalu(ile: int = 25) -> list[dict[str, Any]]:
    """Ostatnie posty z kanalu czytelnika, z liczba komentarzy i reakcji."""
    browser.wymagaj_sesji()
    p, br, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    try:
        dane = browser.api_json(page, "/api/v1/reader/posts") or {}
        posty = []
        for x in (dane.get("posts") or [])[:ile]:
            if not isinstance(x, dict):
                continue
            # NASZE wlasne teksty wypadaja od razu. Kanal czytelnika pokazuje
            # tez nas samych, a wybor celow przy pierwszym uruchomieniu uznal
            # nasz artykul o jajkach za wart skomentowania — agent
            # komentowalby sam siebie.
            adres = x.get("canonical_url") or ""
            if config.SUBSTACK_HANDLE in adres:
                continue
            posty.append({
                "tytul": (x.get("title") or "")[:120],
                "opis": (x.get("subtitle") or x.get("description") or "")[:300],
                "pub": ((x.get("publication") or {}).get("name") or ""),
                "komentarze": x.get("comment_count") or 0,
                "reakcje": x.get("reaction_count") or 0,
                "url": x.get("canonical_url") or "",
                "data": (x.get("post_date") or "")[:10],
            })
        print(f"  [kanał] postów: {len(posty)}", flush=True)
        return posty
    finally:
        page.close()
        br.close()
        p.stop()
