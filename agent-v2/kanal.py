"""Kanal czytelnika — jedyne zrodlo celow do komentowania.

Osobny plik, bo to jest CZYTANIE CUDZYCH tresci przez zalogowana sesje, a nie
publikowanie: browser.py rosl juz do tysiaca linii i mieszanie w nim odczytu
z dzialaniem utrudnialo czytanie obu.
"""

from __future__ import annotations

from typing import Any

import browser
import config

HISTORIA_KOMENTARZY = config.DATA_DIR / "gdzie_komentowalismy.json"


def _historia() -> dict:
    import json

    if not HISTORIA_KOMENTARZY.exists():
        return {}
    try:
        return json.loads(HISTORIA_KOMENTARZY.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def zapamietaj_komentarz(post: dict) -> None:
    """Odnotowuje, u kogo dzis komentowalismy."""
    import json
    from datetime import datetime, timezone

    h = _historia()
    h[klucz_publikacji(post)] = datetime.now(timezone.utc).isoformat()
    HISTORIA_KOMENTARZY.parent.mkdir(parents=True, exist_ok=True)
    HISTORIA_KOMENTARZY.write_text(json.dumps(h, ensure_ascii=False, indent=1),
                                   encoding="utf-8")


def klucz_publikacji(post: dict) -> str:
    """Kim jest autor posta. Z ADRESU, bo nazwa publikacji bywa pusta w kanale."""
    from urllib.parse import urlparse

    return urlparse(post.get("url") or "").netloc or (post.get("pub") or "?")


def _wiek_minut(data: str) -> float:
    from datetime import datetime, timezone

    try:
        kiedy = datetime.fromisoformat(str(data).replace("Z", "+00:00"))
    except ValueError:
        return 1e9        # nieznana data = traktujemy jak stary, nie blokujemy
    return (datetime.now(timezone.utc) - kiedy).total_seconds() / 60


def _za_swiezy(post: dict) -> bool:
    """Czy post jest na tyle swiezy, ze komentarz wygladalby jak czujka bota."""
    import random

    prog = random.uniform(*config.MIN_WIEK_POSTA_MIN)
    return _wiek_minut(post.get("data", "")) < prog


def _za_niedawno_u_nich(post: dict) -> bool:
    """Czy komentowalismy u tej publikacji w ostatnich dniach."""
    from datetime import datetime, timedelta, timezone

    ostatnio = _historia().get(klucz_publikacji(post))
    if not ostatnio:
        return False
    try:
        kiedy = datetime.fromisoformat(ostatnio)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - kiedy) < timedelta(
        days=config.ODSTEP_DNI_NA_PUBLIKACJE)

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
        odrzucone = {"swieze": 0, "za_czesto": 0}
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
            kandydat = {
                "tytul": (x.get("title") or "")[:120],
                "opis": (x.get("subtitle") or x.get("description") or "")[:300],
                "pub": ((x.get("publication") or {}).get("name") or ""),
                "komentarze": x.get("comment_count") or 0,
                "reakcje": x.get("reaction_count") or 0,
                "url": x.get("canonical_url") or "",
                "data": x.get("post_date") or "",   # pelna, do liczenia wieku
            }
            # DWA SITA, oba o ZACHOWANIU, nie o tresci.
            if _za_swiezy(kandydat):
                odrzucone["swieze"] += 1
                continue
            if _za_niedawno_u_nich(kandydat):
                odrzucone["za_czesto"] += 1
                continue
            posty.append(kandydat)
        # NOWI LUDZIE NAJPIERW. Cztery dni odstepu chronia przed nachodzeniem
        # tej samej osoby, ale nie robia z nas kogos, kto poznaje nowych.
        # Konto, ktore krazy miedzy pieciona znajomymi nazwiskami, nie rosnie —
        # a wlasnie o nowych ludzi nam chodzi.
        znani = set(_historia())
        posty.sort(key=lambda x: klucz_publikacji(x) in znani)
        nowi = sum(1 for x in posty if klucz_publikacji(x) not in znani)

        print(f"  [kanał] postów: {len(posty)}   nowych autorów: {nowi}"
              f"   odrzucone: {odrzucone['swieze']} za świeżych,"
              f" {odrzucone['za_czesto']} bo niedawno tam komentowaliśmy",
              flush=True)
        return posty
    finally:
        page.close()
        br.close()
        p.stop()


def notki_z_kanalu(ile: int = 25) -> list[dict]:
    """Cudze notki, pod ktorymi mozna wejsc w dyskusje.

    Dla swiezego konta to najwazniejsze miejsce: pod notkami toczy sie rozmowa,
    a kanal Substacka promuje watki, ktore zyja. Komentarz pod artykulem czyta
    kilka osob; sensowna uwaga pod zywa notka trafia do calego jej watku.
    """
    browser.wymagaj_sesji()
    p, br, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    try:
        dane = browser.api_json(page, "/api/v1/reader/feed?tab=for-you&type=base") or {}
        notki = []
        odrzucone = 0
        for x in (dane.get("items") or [])[:ile * 2]:
            c = (x or {}).get("comment") or {}
            if not c.get("body") or c.get("post_id"):
                continue                     # to nie notka, tylko komentarz
            if c.get("handle") == config.SUBSTACK_HANDLE:
                continue                     # nasza wlasna
            kandydat = {
                "id": c.get("id"), "autor": c.get("name") or "",
                "handle": c.get("handle") or "",
                "tekst": (c.get("body") or "")[:1200],
                "reakcje": c.get("reaction_count") or 0,
                "odpowiedzi": c.get("children_count") or 0,
                "data": c.get("date") or "",
                "url": f"https://substack.com/note/c-{c.get('id')}",
            }
            if _za_swiezy(kandydat):
                odrzucone += 1
                continue
            notki.append(kandydat)
        # Najzywsze najpierw: tam nasza uwaga zostanie przeczytana.
        notki.sort(key=lambda n: n["reakcje"] * 2 + n["odpowiedzi"] * 3,
                   reverse=True)
        print(f"  [notki innych] {len(notki)} do rozwazenia"
              f"   ({odrzucone} odrzuconych jako za swieze)", flush=True)
        return notki[:ile]
    finally:
        page.close()
        br.close()
        p.stop()
