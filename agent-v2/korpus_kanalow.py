"""Tematy z kanalow, ktore robia dokladnie to, co ma robic nasza publikacja.

DLACZEGO TO ZRODLO, A NIE ARXIV. Zbudowalem korpus odkryc naukowych i wlasciciel
odrzucil jego plon jednym zdaniem — tokamak go nie interesuje. Wybral natomiast
z listy kanalow: chip z zywych komorek mozgowych, agenci ustalajacy wlasny
protokol, model bijacy najlepsze, ktorego autora nikt nie zna, Claude ktory
przegral 650 razy i pobil rekord czlowieka.

Roznica nie jest w dziedzinie, tylko w tym, ze kazdy z tych tematow **da sie
opowiedziec komus przy stole**. Praca o rownowadze plazmy nie da sie, choc jest
lepsza nauka. Kanaly o AI robia ten dobor od lat i maja na nim liczniki — wiec
zamiast zgadywac, co jest ciekawe, czytamy, co ONI wybrali.

CZEGO STAD NIE BIERZEMY. Naglowkow. „This Will Change EVERYTHING" obiecuje rzecz,
ktorej nie pokryje zaden dokument, a bramka faktograficzna ja zatrzyma — i dobrze,
bo to jedyna roznica miedzy nami a generatorem hype'u. Bierzemy ZDARZENIE, ktore
za naglowkiem stoi, i sami je sprawdzamy: przez `kod_odpowiada`, przez wlasny
pomiar, przez dokument.

DOSTEP. Kanaly YouTube maja publiczny kanal RSS, ktory NIE przechodzi przez
sciane zgody — a strona kanalu przechodzi i dlatego jej nie uzywamy. RSS oddaje
ostatnie ~15 filmow: tytul, date, adres. Nic wiecej nie potrzeba.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

RSS = "https://www.youtube.com/feeds/videos.xml"
NS = {"a": "http://www.w3.org/2005/Atom"}

# Identyfikatory ustalone przez wyszukiwarke (strony statystyk kanalow), bo
# youtube.com/@uchwyt przekierowuje na zgode. Sprawdzone: kazdy oddaje RSS 200.
KANALY = {
    # Zdarzenia i newsy
    "AI Revolution":       "UC5l7RouTQ60oUjLjt1Nh-UQ",
    "Wes Roth":            "UCqcbQf6yw5KzRoDDcZ_wBSw",
    "Matt Wolfe":          "UChpleBmo18P08aKCIgti38g",
    "TheAIGRID":           "UCSPkiRjFYpz-8DY-aF_1wRg",
    "1littlecoder":        "UCpV_X0VrL8-jg3t6wYGS-1g",
    "Sam Witteveen":       "UC55ODQSvARtgSyc8ThfiepQ",
    # Wyjasnianie mechanizmow — najblizsze temu, co robimy
    "AI Explained":        "UCNJ1Ymd5yFuUPtn21xtRbbw",
    "Two Minute Papers":   "UCbfYPyITQ-7l4upoX8nvctg",
    "ByCloud":             "UC6r0JH23PKZfogSwn2Q-oMw",
    "Dr Waku":             "UCZf5IX90oe5gdPppMXGImwg",
    # Wielkie pytania z rozmow — rejestr Kaweckiego.
    # Lex Fridman WYPADL: w wiekszosci nie o AI, a klipy z jednego
    # wywiadu dawaly dziesiec pozycji dziennie i wypychaly reszte.
    "Dwarkesh Patel":      "UCXl4i9dYBrFOabk0xGmbkRA",
    "MLST":                "UCZHmQk67mSJgfCCTn7xBfew",
    # Produktowe — trzymane osobno, bo najczesciej daja poradniki
    "Matthew Berman":      "UCawZsQWqfGSbCI5yjkdVkTA",
}

# JAK ZDOBYWA SIE IDENTYFIKATOR KANALU, bo to kosztowalo pol godziny.
# youtube.com/@uchwyt przekierowuje na sciane zgody i nie oddaje niczego;
# oEmbed dziala tylko dla FILMOW, nie dla kanalow (404); przegladarka nie
# wystawia przyciskow zgody w drzewie dostepnosci.
#
# Dziala: zwykle zapytanie HTTP z ciasteczkiem zgody `CONSENT=YES+cb...`
# i `SOCS=CAI`, a potem regex na `"externalId":"(UC...)"` w HTML. Wlasciciel
# zatwierdzil przejscie przez zgode wprost.
#
# Sam kanal RSS zgody NIE wymaga — potrzebna jest wylacznie do jednorazowego
# ustalenia identyfikatora nowego kanalu.

# Naglowkowa oprawa do zdjecia. Zostawiamy ZDARZENIE, wyrzucamy obietnice.
OPRAWA = (
    r"\s*\(.*?\)\s*$", r"\s*\[.*?\]\s*$",
    r"\b(this )?(will |just )?change(s|d)? everything\b",
    r"\b(insane|shocking\w*|crazy|wild|unbelievable|mind-?blowing)\b",
    r"\bcritical warning\b", r"\bpanicking\b", r"\byou won'?t believe\b",
    r"^\s*(BREAKING|URGENT|WOW)[:\s-]+", r"\s*[\U0001F300-\U0001FAFF]\s*",
)

# Tytuly, ktore nie sa zdarzeniem tylko trescia kanalu — nie nasza sprawa.
NIE_TEMAT = re.compile(
    r"\b(how to|tutorial|my (setup|workflow|system)|behind the scenes|BTS|"
    r"i built|build a business|giveaway|q&a|ama|livestream|podcast #\d)\b"
    r"|\bthe .{0,20} situation\b"
    # TRESCI PRODUKTOWE I PORADNIKI. Pierwszy przebieg przepuscil „Grok Bot can
    # shop for you", „11 Use Cases That Feel Like Cheating", „You NEED to try
    # this" — to sa recenzje narzedzi, nie zdarzenia, i nie ma o czym pisac.
    r"|\b(use cases?|you need to try|saves? (so much )?time|is so easy|"
    r"hands-?on|first look|i tested|top \d+|\d+ (best|new|open-source))\b"
    # KLIPY Z WYWIADU. Kanaly rozmow tna jedna rozmowe na kilkanascie kawalkow
    # i kazdy ma w tytule „X and Y" — dziesiec pozycji dziennie z jednego
    # materialu zalewa liste i wypycha wszystko inne.
    r"|\b\w+\s+and\s+(Lex Fridman|Dwarkesh Patel)\b",
    re.IGNORECASE,
)


def oczysc(tytul: str) -> str:
    """Zdejmuje obietnice, zostawia zdarzenie."""
    t = tytul
    for w in OPRAWA:
        t = re.sub(w, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" .,-–—…")
    return t


def przetworz(wpisy: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """(nazwa_kanalu, element) -> kandydaci. Czysta funkcja, testowalna."""
    widziane: set[str] = set()
    out: list[dict[str, Any]] = []
    for kanal, e in wpisy or []:
        t = e.find("a:title", NS)
        if t is None or not (t.text or "").strip():
            continue
        surowy = " ".join(t.text.split())
        if NIE_TEMAT.search(surowy):
            continue
        czysty = oczysc(surowy)
        if len(czysty.split()) < 4:
            continue
        klucz = re.sub(r"[^a-z0-9 ]", "", czysty.lower())[:60]
        if klucz in widziane:
            continue
        widziane.add(klucz)
        link = e.find("a:link", NS)
        out.append({
            "temat": czysty,
            "surowy": surowy,
            "kanal": kanal,
            "data": (e.find("a:published", NS).text or "")[:10]
                    if e.find("a:published", NS) is not None else "",
            "url": link.get("href") if link is not None else "",
            "rola": "zdarzenie do sprawdzenia; naglowka nie kopiujemy",
        })
    out.sort(key=lambda x: x["data"], reverse=True)
    return out


def korpus_kanalow(ile: int = 30) -> list[dict[str, Any]]:
    import httpx

    import config

    wpisy: list[tuple[str, Any]] = []
    with httpx.Client(timeout=config.FETCH_TIMEOUT_S, follow_redirects=True,
                      headers={"User-Agent": config.FETCH_USER_AGENT}) as c:
        for nazwa, cid in KANALY.items():
            try:
                r = c.get(RSS, params={"channel_id": cid})
                if r.status_code != 200:
                    print("  [kanaly] %s: HTTP %s" % (nazwa, r.status_code), flush=True)
                    continue
                for e in ET.fromstring(r.content).findall("a:entry", NS):
                    wpisy.append((nazwa, e))
            except Exception as exc:
                print("  [kanaly] %s: %s" % (nazwa, type(exc).__name__), flush=True)
    k = przetworz(wpisy)
    print("  [kanaly] %d filmow z %d kanalow -> %d tematow"
          % (len(wpisy), len(KANALY), len(k)), flush=True)
    return k[:ile]


if __name__ == "__main__":
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    for x in korpus_kanalow():
        print("  [%s] %-18s %s" % (x["data"], x["kanal"][:18], x["temat"][:66]))
