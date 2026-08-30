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


# Slowa, ktore nie odrozniaja jednego wydarzenia od drugiego. Bez tej listy
# „AI" i „model" laczylyby w jedno wydarzenie cala tablice.
_TLO = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "it", "its", "this", "that", "you",
    "your", "we", "our", "just", "now", "new", "ai", "model", "models", "gpt",
    "llm", "how", "why", "what", "chatgpt", "openai", "google", "than",
    "from", "has", "have", "can", "will", "about", "more", "most", "first",
}


def _rdzen(temat: str) -> set[str]:
    """Slowa nosne tytulu — do porownywania, czy dwa kanaly mowia o tym samym."""
    return {s for s in re.findall(r"[a-z0-9][a-z0-9\-\.]{2,}", temat.lower())
            if s not in _TLO}


def wielkie_wydarzenia(korpus: list[dict[str, Any]], min_kanalow: int = 3,
                       min_wspolnych: int = 2,
                       swiezosc_dni: int = 4) -> list[dict[str, Any]]:
    """Rzeczy, o ktorych mowi NARAZ kilka roznych kanalow.

    PO CO. Wlasciciel: „jak wychodzi nowy model albo jest duze wydarzenie AI,
    to musi miec pierwszenstwo przed wszystkim".

    To stoi w napieciu z regula, ktora skaut i bank maja od poczatku: „wyszedl
    nowy model" nie jest tematem, tylko tym, co w tym tygodniu pisza wszyscy.
    Regula jest sluszna — bez niej stajemy sie jednym z pieciuset kanalow
    opisujacych premiere.
    
    Napiecie znika, gdy rozdzielic OKAZJE od TEMATU. Wydarzenie mowi nam, KIEDY
    czytelnik patrzy w te strone; nie mowi, CO mamy napisac. Tresc nadal musi
    przejsc te same bramki — mechanizm, zlamane przekonanie, sprawdzalnosc.
    Wykrycie wydarzenia daje wiec PIERWSZENSTWO W KOLEJCE, nigdy zwolnienia
    z jakosci.

    SYGNAL JEST OBIEKTYWNY I LICZY GO KOD, nie model: ten sam rdzen tematu
    u co najmniej `min_kanalow` ROZNYCH kanalow. Jeden kanal krzyczacy
    „EVERYTHING CHANGED" to nie wydarzenie, tylko naglowek.
    """
    grupy: list[dict[str, Any]] = []
    for poz in korpus or []:
        rdzen = _rdzen(poz.get("temat", ""))
        if len(rdzen) < min_wspolnych:
            continue
        for g in grupy:
            if len(g["rdzen"] & rdzen) >= min_wspolnych:
                g["pozycje"].append(poz)
                g["kanaly"].add(poz.get("kanal", ""))
                g["rdzen"] &= rdzen or g["rdzen"]
                break
        else:
            grupy.append({"rdzen": rdzen, "pozycje": [poz],
                          "kanaly": {poz.get("kanal", "")}})
    # PIERWSZENSTWO PRZYSLUGUJE TEMU, CO DZIEJE SIE TERAZ. Bez tego progu
    # wykrywacz oddawal jako „wielkie wydarzenie" premiere sprzed szesnastu dni
    # — zlapane pierwszym uruchomieniem na zywym korpusie. Rzecz, o ktorej trzy
    # kanaly mowily dwa tygodnie temu, jest historia, a nie powodem, zeby
    # przestawiac kolejke.
    from datetime import datetime as _d, timedelta as _td, timezone as _tz
    granica = (_d.now(_tz.utc) - _td(days=swiezosc_dni)).strftime("%Y-%m-%d")

    wyniki = [{"o_czym": sorted(g["rdzen"])[:6],
               "kanalow": len(g["kanaly"]),
               "kanaly": sorted(g["kanaly"]),
               "tytuly": [p["temat"] for p in g["pozycje"][:4]],
               "data": max((p.get("data") or "") for p in g["pozycje"])}
              for g in grupy if len(g["kanaly"]) >= min_kanalow
              and max((p.get("data") or "") for p in g["pozycje"]) >= granica]
    wyniki.sort(key=lambda w: (-w["kanalow"], w["data"]), reverse=False)
    wyniki.sort(key=lambda w: w["kanalow"], reverse=True)
    return wyniki


# Korpus zbudowany w tym procesie, i kiedy. Trzynascie zapytan HTTP na kanaly
# YouTube'a nie jest darmowe w czasie, a przebieg wola te funkcje DWA RAZY:
# raz po zaczyn do promptu ciekawostek, raz po wykrywacz wielkich wydarzen.
# Zmierzone 30 sierpnia: w logu jednego przebiegu linia „180 filmow z 13
# kanalow" pojawiala sie dwukrotnie, kilkanascie sekund po sobie.
#
# TERMIN, NIE WIECZNOSC. Przebieg dnia potrafi trwac ponad godzine, wiec zapas
# bez terminu oznaczalby, ze pod koniec cyklu patrzymy na kanaly sprzed 90
# minut. Pol godziny to kompromis: w jednym przebiegu pobieramy raz, a proces
# dlugowieczny i tak sie odswiezy.
_ZAPAS: dict[str, Any] = {"kiedy": 0.0, "wpisy": None}
ZAPAS_WAZNY_S = 1800


def korpus_kanalow(ile: int = 30) -> list[dict[str, Any]]:
    import time

    import httpx

    import config

    # Zapas trzyma PELNA liste, a nie przyciete `ile` — inaczej wywolanie po 26
    # tematow zatrulo by pozniejsze wywolanie po 200, ktorego potrzebuje
    # wykrywacz wydarzen.
    if (_ZAPAS["wpisy"] is not None
            and time.time() - _ZAPAS["kiedy"] < ZAPAS_WAZNY_S):
        return list(_ZAPAS["wpisy"])[:ile]

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
    # Zapas zapisujemy TYLKO wtedy, gdy cos przyszlo. Zapamietanie pustki po
    # sieciowej wpadce wyciszyloby kanaly na pol godziny, a prompt dostalby
    # „(nothing fetched today)" mimo dzialajacej sieci.
    if k:
        _ZAPAS["wpisy"] = list(k)
        _ZAPAS["kiedy"] = time.time()
    return k[:ile]


if __name__ == "__main__":
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    for x in korpus_kanalow():
        print("  [%s] %-18s %s" % (x["data"], x["kanal"][:18], x["temat"][:66]))
