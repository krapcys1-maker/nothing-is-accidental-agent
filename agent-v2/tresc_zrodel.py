# -*- coding: utf-8 -*-
"""Tresc zrodel z korpusu, pobrana ZA DARMO — zamiast platnego szukania.

PO CO TO POWSTALO. Skaut dostawal z korpusu same TYTULY („- [2026-09-04]
OpenAI — <naglowek>") i zdanie „uzyj tej listy do tego, co sie dzieje, nigdy
jako zrodla". Zeby wiec zdobyc fakt z liczba, musial go doszukac sam — a
szukanie u DeepSeeka prowadzi serwer i rozlicza KAZDA runde jako wejscie.

ZMIERZONE 29 sierpnia - 4 wrzesnia 2026: `curiosity` to 34 wywolania, 568
wyszukiwan (16,9 na wywolanie), 11,25 mln tokenow wejscia i 3,48 USD — 15%
calego rachunku. A 60 z 62 przyniesionych faktow (97%) bylo ZAKOTWICZONYCH
w naszym wlasnym korpusie, czyli ich temat juz u nas lezal, pobrany za darmo.

Placilismy za odnajdywanie tego, co mielismy. Tytul nie jest zrodlem — ale
adres obok tytulu prowadzi do tekstu, ktory zrodlem jest, i pobranie go
kosztuje jedno zapytanie HTTP.

CZEGO TO NIE ROBI. Nie dotyka YouTube'a: strona filmu nie ma tresci artykulu,
a przy okazji YouTube i tak blokuje ten serwer (12 z 13 kanalow oddaje 404
albo 500 — sprawdzone 5 wrzesnia 2026, ten sam adres ByCloud dzialal
kilkanascie minut wczesniej, wiec to blokada, nie zly identyfikator).
Bierzemy wylacznie ZRODLA PIERWOTNE, ktore odpowiadaja niezawodnie i sa
lepszym materialem: to sa same wydarzenia, a nie komentarz do nich.
"""
from __future__ import annotations

import html
import re
import time
from typing import Any

import config

# ILE ZRODEL CZYTAMY NA JEDNO SZUKANIE. Osiem to tyle, ile faktow skaut ma
# oddac — jedno zrodlo na fakt, z zapasem na te, ktore nic nie dadza.
ILE_ZRODEL = 8

# ILE ZNAKOW BIERZEMY Z JEDNEJ STRONY. Wejscie liczy sie do rachunku, wiec
# sufit jest tu oszczednoscia, a nie ostroznoscia: osiem stron po 2500 znakow
# to okolo 5 tysiecy tokenow — wobec 319 tysiecy, ktore kosztowalo jedno
# platne szukanie.
ZNAKOW_ZE_STRONY = 2500

# CZEGO NIE PROBUJEMY POBIERAC. Strona filmu nie ma tekstu artykulu, a plik
# binarny tylko zmarnuje zapytanie i czas.
POMIJANE = ("youtube.com", "youtu.be", ".pdf", ".zip", ".mp4", ".mp3")

_ZAPAS: dict[str, Any] = {"kiedy": 0.0, "tresci": None}
ZAPAS_WAZNY_S = 1800


def _na_tekst(surowy: str) -> str:
    """HTML na czysty tekst. Prymitywnie i celowo.

    Model nie potrzebuje ukladu strony, tylko zdan z liczbami. Wycinamy to,
    co nigdy nie jest trescia (skrypty, style, znaczniki), rozwijamy encje
    i sklejamy biale znaki.
    """
    bez = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", surowy)
    bez = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", bez)
    bez = re.sub(r"(?s)<[^>]+>", " ", bez)
    bez = html.unescape(bez)
    bez = re.sub(r"[ \t\r\f\v]+", " ", bez)
    bez = re.sub(r"\n\s*\n\s*", "\n", bez)
    return bez.strip()


def _warto(tekst: str) -> bool:
    """Czy z tej strony jest co czytac.

    Sciana zgody, blad i pusta powloka aplikacji tez oddaja HTTP 200 — to ta
    sama pulapka, przez ktora trzy kanaly YouTube udawaly przez tydzien, ze
    dzialaja. Sprawdzamy TRESC, nie kod odpowiedzi.
    """
    if len(tekst) < 400:
        return False
    # Strona z liczbami jest tu warta wiecej niz strona bez nich, ale brak
    # liczb nie dyskwalifikuje: „OpenAI wycofuje model X" to tez fakt.
    return len(tekst.split()) >= 60


def tresci_zrodel(wpisy: list[dict[str, Any]], ile: int = ILE_ZRODEL,
                  znakow: int = ZNAKOW_ZE_STRONY) -> list[dict[str, str]]:
    """Pobiera tresc pierwszych `ile` nadajacych sie wpisow korpusu.

    NIGDY NIE PODNOSI WYJATKU i nigdy nie zatrzymuje przebiegu. Zrodlo, ktore
    nie odpowiada, jest pomijane — skaut ma wtedy mniej materialu, ale ma
    material. Brak notki jest gorszy niz notka z wezszego wyboru.
    """
    import httpx

    out: list[dict[str, str]] = []
    naglowki = {"User-Agent": config.FETCH_USER_AGENT}
    try:
        klient = httpx.Client(timeout=config.FETCH_TIMEOUT_S,
                              follow_redirects=True, headers=naglowki)
    except Exception:
        return out
    with klient as c:
        for w in wpisy:
            if len(out) >= ile:
                break
            url = str(w.get("url") or "").strip()
            if not url or any(p in url.lower() for p in POMIJANE):
                continue
            try:
                r = c.get(url)
                if r.status_code != 200:
                    continue
                tekst = _na_tekst(r.text)
            except Exception:
                continue
            if not _warto(tekst):
                continue
            out.append({
                "kanal": str(w.get("kanal") or "?"),
                "temat": str(w.get("temat") or ""),
                "data": str(w.get("data") or "")[:10],
                "url": url,
                "tekst": tekst[:znakow],
            })
            # GRZECZNIE, NIE SZYBKO. Te adresy sa nasze na dlugo; serwer, ktory
            # nas zablokuje, kosztuje wiecej niz pol sekundy zwloki.
            time.sleep(0.4)
    return out


def blok_do_promptu(wpisy: list[dict[str, Any]], ile: int = ILE_ZRODEL) -> str:
    """Tresci zrodel gotowe do wklejenia w prompt skauta.

    Pusty napis, gdy nic nie udalo sie pobrac — wolajacy ma wtedy przejsc na
    platne szukanie, bo skaut bez materialu nie odda nic.
    """
    teraz = time.time()
    if (_ZAPAS["tresci"] is not None
            and teraz - _ZAPAS["kiedy"] < ZAPAS_WAZNY_S):
        gotowe = _ZAPAS["tresci"]
    else:
        gotowe = tresci_zrodel(wpisy, ile=ile)
        _ZAPAS["tresci"] = gotowe
        _ZAPAS["kiedy"] = teraz
    if not gotowe:
        return ""
    czesci = []
    for z in gotowe:
        czesci.append(
            "### [%s] %s\nSource: %s\nPublished: %s\n\n%s"
            % (z["kanal"], z["temat"], z["url"], z["data"], z["tekst"]))
    return "\n\n---\n\n".join(czesci)


def wyczysc_zapas() -> None:
    """Do testow — zapas procesowy nie moze przeciekac miedzy przypadkami."""
    _ZAPAS["tresci"] = None
    _ZAPAS["kiedy"] = 0.0
