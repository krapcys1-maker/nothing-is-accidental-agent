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

# ILE MIEJSC MOZE ZAJAC JEDNO ZRODLO — patrz `tresci_zrodel`.
MAKS_Z_JEDNEGO_ZRODLA = 2

# CZEGO NIE PROBUJEMY POBIERAC. Strona filmu nie ma tekstu artykulu, a plik
# binarny tylko zmarnuje zapytanie i czas.
POMIJANE = ("youtube.com", "youtu.be", ".pdf", ".zip", ".mp4", ".mp3")

_ZAPAS: dict[str, Any] = {"kiedy": 0.0, "tresci": None}
ZAPAS_WAZNY_S = 1800

# SKLAD SPIZARNI — silnik tematow, 26 wrzesnia 2026 (eksperyment E6).
# Plan: `agent-v2/docs/WYBOR_TEMATOW_2026-09-26.md`.
#
# TU ZAPADA DECYZJA O TEMACIE, nie w modelu. Przy niepustej spizarni skaut nie
# szuka w sieci (`web_search = not _tresc` w `stages.znajdz_ciekawostki`), wiec
# pisze o tym, co tu wlozymy. Do tego dnia wkladalismy osiem najnowszych wpisow
# z trzydziestu pierwszych, a najnowsze sa blogi branzowe, bo pisza najczesciej.
# ZMIERZONE z serwera 26.09 przed zmiana: siedem z osmiu tekstow branzowych,
# a polowa z trzydziestu wpisow to YouTube, ktorego spizarnia w ogole nie czyta.
# Trzy zmiany promptu nic nie daly, bo zmienialy slowa, a material wybieral kod.
#
# Teraz kolejnosc ma trzy etapy (patrz `tresci_zrodel`): najpierw po jednym
# tekscie z kazdego zrodla o ludziach, potem najwyzej MAKS_BRANZA branzowych,
# na koniec dopelnienie. Branzy nie wycinamy: premiery modeli to tez nasz temat.
MAKS_BRANZA = 2
# Ponizej tylu tekstow o ludziach log mowi glosno, ze zrodla o ludziach nie
# daly materialu — wtedy spizarnia jest znowu branzowa i trzeba wiedziec czemu.
MIN_LUDZIE = 4


def _styk(w: dict[str, Any]) -> str:
    return str(w.get("styk") or "branza")


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
    #
    # PROG PODNIESIONY Z 60 DO 150 SLOW po zywej probie 5 wrzesnia 2026:
    # wpis „August newsletter is out" mial 1552 znaki samej nawigacji strony
    # i przeszedl. Zajmowal miejsce w spizarni i nie dawal zadnego faktu.
    return len(tekst.split()) >= 150


def kolejnosc_ludzi(wpisy: list[dict[str, Any]],
                    styki_w_banku: set[str] | frozenset[str] = frozenset()
                    ) -> list[dict[str, Any]]:
    """Wpisy spoza branzy w kolejnosci, w jakiej spizarnia ma je probowac.

    Najpierw styki, ktorych bank nie widzial od trzech dni, potem reszta; w
    kazdej grupie najpierw PIERWSZY wpis kazdego styku, zeby osiem miejsc nie
    poszlo na jedna rodzine. Sort stabilny: w obrebie grupy zostaje porzadek
    korpusu, czyli po dacie.
    """
    ludzie = sorted((w for w in wpisy if _styk(w) != "branza"),
                    key=lambda w: _styk(w) in styki_w_banku)
    pierwsze, reszta, widziane = [], [], set()
    for w in ludzie:
        (reszta if _styk(w) in widziane else pierwsze).append(w)
        widziane.add(_styk(w))
    return pierwsze + reszta


def tresci_zrodel(wpisy: list[dict[str, Any]], ile: int = ILE_ZRODEL,
                  znakow: int = ZNAKOW_ZE_STRONY,
                  styki_w_banku: set[str] | frozenset[str] | None = None,
                  ) -> list[dict[str, str]]:
    """Pobiera tresc `ile` nadajacych sie wpisow korpusu — z kwota, patrz wyzej.

    Trzy etapy, kazdy liczy tylko teksty NAPRAWDE pobrane:
      1. o ludziach: po jednym z kazdego zrodla, az zostanie MAKS_BRANZA miejsc;
      2. branza: najwyzej MAKS_BRANZA, po jednym z kazdego zrodla;
      3. dopelnienie: reszta o ludziach, potem branza, do MAKS_Z_JEDNEGO_ZRODLA
         ze zrodla. Branza przekracza MAKS_BRANZA TYLKO wtedy, gdy o ludziach
         nie ma czego wziac — chuda spizarnia to platne szukanie.

    NIGDY NIE PODNOSI WYJATKU i nigdy nie zatrzymuje przebiegu. Zrodlo, ktore
    nie odpowiada, jest pomijane — skaut ma wtedy mniej materialu, ale ma
    material. Brak notki jest gorszy niz notka z wezszego wyboru.
    """
    import httpx

    out: list[dict[str, str]] = []
    # ILE MIEJSC MOZE ZAJAC JEDNO ZRODLO. Zmierzone na zywej spizarni
    # 5 wrzesnia 2026: bez tego sufitu Simon Willison zajal TRZY z osmiu
    # miejsc, bo korpus idzie po dacie, a on publikuje czesto. Osiem tekstow
    # z trzech zrodel to nie jest spizarnia, tylko jedna polka — a skaut ma
    # z tego zrobic osiem faktow z ROZNYCH dziedzin.
    z_kanalu: dict[str, int] = {}
    # Adres, ktory raz nie dal tekstu, nie jest probowany drugi raz w kolejnym
    # etapie — to byloby drugie zapytanie o te sama sciane zgody.
    sprobowane: set[str] = set()
    ludzie = kolejnosc_ludzi(wpisy, frozenset(styki_w_banku or ()))
    branza = [w for w in wpisy if _styk(w) == "branza"]
    naglowki = {"User-Agent": config.FETCH_USER_AGENT}
    try:
        klient = httpx.Client(timeout=config.FETCH_TIMEOUT_S,
                              follow_redirects=True, headers=naglowki)
    except Exception:
        return out

    def _branzy() -> int:
        return sum(1 for z in out if z["styk"] == "branza")

    with klient as c:
        def wez(kandydaci: list[dict[str, Any]], dopoki, na_zrodlo: int) -> None:
            for w in kandydaci:
                if not dopoki():
                    return
                url = str(w.get("url") or "").strip()
                if (not url or url in sprobowane
                        or any(p in url.lower() for p in POMIJANE)):
                    continue
                kan = str(w.get("kanal") or "?")
                if z_kanalu.get(kan, 0) >= na_zrodlo:
                    continue
                sprobowane.add(url)
                try:
                    r = c.get(url)
                    if r.status_code != 200:
                        continue
                    tekst = _na_tekst(r.text)
                except Exception:
                    continue
                if not _warto(tekst):
                    continue
                z_kanalu[kan] = z_kanalu.get(kan, 0) + 1
                out.append({
                    "kanal": kan,
                    "temat": str(w.get("temat") or ""),
                    "data": str(w.get("data") or "")[:10],
                    "url": url,
                    "styk": _styk(w),
                    "tekst": tekst[:znakow],
                })
                # GRZECZNIE, NIE SZYBKO. Te adresy sa nasze na dlugo; serwer,
                # ktory nas zablokuje, kosztuje wiecej niz pol sekundy zwloki.
                time.sleep(0.4)

        wez(ludzie, lambda: len(out) < ile - MAKS_BRANZA, 1)
        wez(branza, lambda: len(out) < ile and _branzy() < MAKS_BRANZA, 1)
        wez(ludzie + branza, lambda: len(out) < ile, MAKS_Z_JEDNEGO_ZRODLA)
    return out


def sklad(gotowe: list[dict[str, str]]) -> str:
    """Jedna linia do logu: ile tekstow, z ilu zrodel, jakie styki."""
    styki: dict[str, int] = {}
    for z in gotowe:
        styki[z.get("styk", "branza")] = styki.get(z.get("styk", "branza"), 0) + 1
    return ("%d tekstow z %d zrodel; styki: %s"
            % (len(gotowe), len({z["kanal"] for z in gotowe}),
               ", ".join("%s %d" % kv for kv in sorted(styki.items()))))


def blok_do_promptu(wpisy: list[dict[str, Any]], ile: int = ILE_ZRODEL,
                    styki_w_banku: set[str] | frozenset[str] | None = None) -> str:
    """Tresci zrodel gotowe do wklejenia w prompt skauta.

    Pusty napis, gdy nic nie udalo sie pobrac — wolajacy ma wtedy przejsc na
    platne szukanie, bo skaut bez materialu nie odda nic.
    """
    teraz = time.time()
    if (_ZAPAS["tresci"] is not None
            and teraz - _ZAPAS["kiedy"] < ZAPAS_WAZNY_S):
        gotowe = _ZAPAS["tresci"]
    else:
        gotowe = tresci_zrodel(wpisy, ile=ile, styki_w_banku=styki_w_banku)
        _ZAPAS["tresci"] = gotowe
        _ZAPAS["kiedy"] = teraz
        # SKLAD DO LOGU PRZY KAZDYM POBRANIU — przyrzad z 8 wrzesnia nie
        # wypisywal, co bylo w spizarni, i dlatego nie pokazal, ze to ona
        # wybiera temat.
        if gotowe:
            ludzi = sum(1 for z in gotowe if z.get("styk", "branza") != "branza")
            print("  [spizarnia] %s%s" % (
                sklad(gotowe),
                "" if ludzi >= MIN_LUDZIE else
                " — O LUDZIACH TYLKO %d, zrodla o ludziach nie daly materialu"
                % ludzi), flush=True)
    if not gotowe:
        return ""
    czesci = []
    for z in gotowe:
        # STYK W NAGLOWKU: skaut widzi, skad jest tekst. Styk faktu i tak
        # przepisuje kod (`stages.styk_ze_zrodla`), wiec to jest informacja
        # dla modelu, a nie jego zadanie.
        czesci.append(
            "### [%s] %s\nSource: %s\nPublished: %s\nTouchpoint: %s\n\n%s"
            % (z["kanal"], z["temat"], z["url"], z["data"],
               z.get("styk", "branza"), z["tekst"]))
    return "\n\n---\n\n".join(czesci)


def ostatnie_tresci() -> list[dict[str, str]]:
    """Teksty ostatnio pobranej spizarni — `stages.styk_ze_zrodla` bierze z nich
    styk faktu po adresie i po hoscie."""
    return list(_ZAPAS["tresci"] or [])


def wyczysc_zapas() -> None:
    """Do testow — zapas procesowy nie moze przeciekac miedzy przypadkami."""
    _ZAPAS["tresci"] = None
    _ZAPAS["kiedy"] = 0.0
