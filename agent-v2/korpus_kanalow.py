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
# youtube.com/@uchwyt przekierowuje na zgode.
#
# SPRAWDZENIEM NIE JEST KOD 200 — I TO NAS KOSZTOWALO TRZY KANALY.
# Do 3 wrzesnia 2026 stalo tu „sprawdzone: kazdy oddaje RSS 200". Kod 200
# oddaje takze feed CUDZEGO kanalu, wiec bledny identyfikator przechodzil
# kontrole. Zmierzone tego dnia na zywo, przez pobranie i odczytanie wpisow:
#
#   TheAIGRID  UCSPkiRjFYpz... -> feed „TheLifeGrid", ZERO wpisow
#   ByCloud    UC6r0JH23PKZ... -> hiszpanski kanal growy, ostatni film
#                                 2019-05-26 („Vagrant Story", Fortnite)
#   MLST       UCZHmQk67mSJ... -> „Yannic Kilcher", nie MLST
#
# ByCloud byl gorszy niz bezuzyteczny: pietnascie hiszpanskich tytulow z lat
# 2013-2019 wchodzilo do zbioru `znane` w `wielkie_wydarzenia`, czyli zatruwalo
# wykrywacz premier historia bez zwiazku z AI. Poprawny TheAIGRID ma film o
# Fable 5.1 z 2 wrzesnia — czyli o premierze, na ktora bylismy slepi.
#
# SPRAWDZAJAC IDENTYFIKATOR, CZYTAJ <title> FEEDU I DATE OSTATNIEGO WPISU.
# Nie kod odpowiedzi.
KANALY = {
    # Zdarzenia i newsy
    "AI Revolution":       "UC5l7RouTQ60oUjLjt1Nh-UQ",
    "Wes Roth":            "UCqcbQf6yw5KzRoDDcZ_wBSw",
    "Matt Wolfe":          "UChpleBmo18P08aKCIgti38g",
    "TheAIGRID":           "UCbY9xX3_jW5c2fjlZVBI4cg",
    "1littlecoder":        "UCpV_X0VrL8-jg3t6wYGS-1g",
    "Sam Witteveen":       "UC55ODQSvARtgSyc8ThfiepQ",
    # Wyjasnianie mechanizmow — najblizsze temu, co robimy
    "AI Explained":        "UCNJ1Ymd5yFuUPtn21xtRbbw",
    "Two Minute Papers":   "UCbfYPyITQ-7l4upoX8nvctg",
    "ByCloud":             "UCgfe2ooZD3VJPB6aJAnuQng",
    "Dr Waku":             "UCZf5IX90oe5gdPppMXGImwg",
    # Wielkie pytania z rozmow — rejestr Kaweckiego.
    # Lex Fridman WYPADL: w wiekszosci nie o AI, a klipy z jednego
    # wywiadu dawaly dziesiec pozycji dziennie i wypychaly reszte.
    "Dwarkesh Patel":      "UCXl4i9dYBrFOabk0xGmbkRA",
    "MLST":                "UCMLtBahI5DMrt0NPvDSoIRQ",
    # Produktowe — trzymane osobno, bo najczesciej daja poradniki
    "Matthew Berman":      "UCawZsQWqfGSbCI5yjkdVkTA",
}

# ZRODLA PIERWOTNE — DRUGI TYP KORPUSU, dolozony 3 wrzesnia 2026.
#
# CZEGO BRAKOWALO. Wszystkie trzynascie kanalow wyzej to JEDEN typ zrodla:
# komentarz do zdarzenia, po fakcie, po angielsku, z USA. Zadne z nich nie
# publikuje DOKUMENTU Z DATA. Doktryna wymaga „nazwanej liczby i dokumentu do
# podlinkowania", a tytul filmu na YouTube nie niesie liczby — niesie obietnice
# liczby, ktora dopiero trzeba znalezc. Stad bramka faktograficzna zabijajaca
# teksty i stad slepota na premiery: o wydaniu modelu wiadomo z filmu dzien
# lub dwa PO tym, jak wyszla karta modelu.
#
# Kazdy adres ponizej sprawdzony na zywo 3 wrzesnia 2026: kod 200, wlasciwy
# tytul feedu, wpis z ostatnich dni. Odrzucone tego samego dnia i DLACZEGO:
#   qwenlm.github.io/blog/index.xml  — 200, wyglada zywo, ostatni wpis
#                                      2025-09-23. Feed martwy od roku.
#   vertex-ai-release-notes.xml      — poprawny Atom, ostatni wpis 2026-03-16.
#   epoch.ai/rss.xml, anthropic.com/rss.xml — 404, nie istnieja.
#   datacenterdynamics.com/rss/      — 302, a bez filtra na moc i AI zalewa
#                                      korpus (10 pozycji na 90 minut).
# To sa dokladnie te pulapki, przed ktorymi chroni regula spod `KANALY`:
# kod odpowiedzi nie jest sprawdzeniem, tytul i data ostatniego wpisu — jest.
ZRODLA = {
    "OpenAI":        "https://openai.com/news/rss.xml",
    "DeepMind":      "https://deepmind.google/blog/rss.xml",
    "HuggingFace":   "https://huggingface.co/blog/feed.xml",
    "vLLM":          "https://github.com/vllm-project/vllm/releases.atom",
    "Awarie Claude": "https://status.claude.com/history.rss",
    "Komisja UE":    "https://digital-strategy.ec.europa.eu/en/rss.xml",
    "Epoch AI":      "https://epochai.substack.com/feed",
    # DOLOZONE 5 WRZESNIA 2026 — ZEBY SKAUT NIE MUSIAL DOKUPYWAC.
    #
    # Powod jest kosztowy, nie kolekcjonerski. Skaut placi za szukanie tylko
    # wtedy, gdy spizarnia jest pusta (patrz `tresc_zrodel`), a spizarnia
    # miala 72 tematy, z czego 15 z YouTube'a i 57 stad. Kazde zrodlo dolozone
    # tutaj to tematy, ktorych nie trzeba doszukiwac za 16,9 rundy wyszukiwania.
    #
    # Wszystkie sprawdzone na zywo tego dnia: HTTP 200, niepusta lista wpisow
    # i TYTUL FEEDU zgodny z nazwa — bo sam kod 200 nic nie dowodzi.
    # Odrzucone przy tej samej probie: Anthropic i Meta AI (404), arXiv cs.AI
    # i Stanford HAI (200 i zero wpisow), NIST (dziala, ale „NIST News" to
    # calosc instytutu — metrologia i pozar w laboratorium obok AI).
    "Google Research": "https://research.google/blog/rss/",
    "Microsoft Res":   "https://www.microsoft.com/en-us/research/feed/",
    "PyTorch":         "https://pytorch.org/blog/feed.xml",
    "Ollama":          "https://github.com/ollama/ollama/releases.atom",
    "llama.cpp":       "https://github.com/ggml-org/llama.cpp/releases.atom",
    "Together AI":     "https://www.together.ai/blog/rss.xml",
    "Awarie OpenAI":   "https://status.openai.com/history.rss",
    # WYPADKI I SZKODY — material, ktorego zaden blog producenta nie da.
    "Wpadki AI":       "https://incidentdatabase.ai/rss.xml",
    # ZA MARTWY YOUTUBE. Kanaly mialy oddawac sygnal „o czym mowi sie teraz";
    # 12 z 13 nie oddaje nic (patrz KANALY), a te trzy feedy pelnia dokladnie
    # te role i odpowiadaja niezawodnie. To komentarz, nie zrodlo pierwotne —
    # ale rola „co jest zywe" nigdy nie byla rola zrodla.
    "Simon Willison":  "https://simonwillison.net/atom/everything/",
    "Import AI":       "https://importai.substack.com/feed",
    "Transformer":     "https://www.transformernews.ai/feed",
    # TWORCY Z YOUTUBE, CZYTANI POZA YOUTUBE'M — dolozone 5 wrzesnia 2026.
    #
    # YouTube dlawi ten serwer (patrz KANALY) i nie da sie tego naprawic po
    # naszej stronie, bo blokada dotyczy TEGO, GDZIE JESTESMY, a nie tego, jak
    # czesto pytamy. Ale czesc tych kanalow to podcasty i biuletyny, ktore maja
    # WLASNE feedy — udostepnione przez samych autorow wlasnie po to, zeby
    # czytaly je maszyny. To nie jest obejscie blokady; to jest wejscie
    # drzwiami, ktore autor otworzyl.
    #
    # Dwarkesh i MLST oddaja DOKLADNIE te sama tresc, co ich kanaly: nagranie
    # idzie na YouTube i do feedu podcastu rownolegle.
    "Dwarkesh":        "https://www.dwarkesh.com/feed",
    "MLST":            "https://anchor.fm/s/1e4a0eac/podcast/rss",
    # Biuletyn i strona autora — ten sam czlowiek, tresc pokrewna, nie
    # identyczna z filmami. Nazwa feedu inna niz nazwa kanalu i to jest w
    # porzadku: „Forward Future" to biuletyn Matthew Bermana, a strona
    # Károly'ego Zsolnai-Fehéra to zaplecze Two Minute Papers.
    "Forward Future":  "https://matthewberman.substack.com/feed",
    "Dr Waku":         "https://drwaku.substack.com/feed",
    "Zsolnai-Fehér":   "https://users.cg.tuwien.ac.at/zsolnai/feed/",
    # ODRZUCONE PRZY TEJ SAMEJ PROBIE, i warto zapisac dlaczego:
    #   * `aiexplained.substack.com` — HTTP 200, osiem wpisow, TYTUL FEEDU
    #     „Discover_AI". To CUDZY Substack, nie kanal AI Explained. Kontrola
    #     „czy odpowiada" wciagnelaby go jako nasze zrodlo;
    #   * `theaigrid.substack.com` — tytul „Andrew Black", zero wpisow;
    #   * `bycloud.substack.com` — tytul „Cloud | Substack", zero wpisow;
    #   * `samwitteveen.substack.com` — pasuje, ale JEDEN wpis;
    #   * ByCloud, Matt Wolfe, Wes Roth, 1littlecoder — feedu poza YouTube
    #     nie maja wcale.
    #
    # DOLOZONE PRZY OKAZJI. Znalezione podczas tej samej proby, ta sama rola
    # („o czym mowi sie teraz"), oba odpowiadaja niezawodnie.
    "Latent Space":    "https://www.latent.space/feed",
    "Interconnects":   "https://www.interconnects.ai/feed",
}

# ILE NAJNOWSZYCH BIERZEMY Z JEDNEGO ZRODLA. YouTube oddaje 15 i tyle wystarcza;
# feed OpenAI ma 1164 wpisow i bez sufitu jedno zrodlo zdominowaloby korpus.
# Bierzemy po dacie, nie po kolejnosci w pliku — kolejnosc bywa dowolna.
Z_JEDNEGO_ZRODLA = 12


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
    # NAWIAS Z LICZBA ZOSTAJE — tam siedzi numer wersji, czyli jedyne slowo,
    # ktore przy premierze modelu maja wspolne rozne kanaly. Zmierzone
    # 2 wrzesnia 2026: „Anthropic went CRAZY (Mythos/Fable 5.1)" (Matthew
    # Berman) traci nawias, potem slowo „CRAZY", zostaje „Anthropic went" —
    # dwa slowa przy progu czterech, wiec CALA pozycja wypada z korpusu.
    # A byl to jedyny DRUGI kanal, ktory tego dnia mowil o Fable 5.1.
    r"\s*\((?![^)]*\d)[^)]*\)\s*$", r"\s*\[(?![^\]]*\d)[^\]]*\]\s*$",
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


def _pole(e: Any, nazwa: str) -> str:
    """Tresc pola wpisu, obojetnie czy feed jest Atomem czy RSS-em 2.0.

    YouTube oddaje Atom (`entry`/`title`/`published` w przestrzeni nazw),
    a laboratoria i rejestry — RSS 2.0 (`item`/`title`/`pubDate`, bez
    przestrzeni). Jeden korpus ma czytac oba, wiec pytamy najpierw o wersje
    z przestrzenia, potem o goly znacznik.
    """
    w = e.find("a:%s" % nazwa, NS)
    if w is None:
        w = e.find(nazwa)
    return (w.text or "").strip() if w is not None else ""


def _data_wpisu(e: Any) -> str:
    """Data wpisu jako RRRR-MM-DD. Atom daje ISO, RSS 2.0 format RFC 822."""
    iso = _pole(e, "published") or _pole(e, "updated")
    if iso[:4].isdigit():
        return iso[:10]
    rfc = _pole(e, "pubDate") or iso
    if rfc:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(rfc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    return ""


def _link_wpisu(e: Any) -> str:
    """Adres wpisu. W Atomie w atrybucie `href`, w RSS-ie w tresci znacznika."""
    w = e.find("a:link", NS)
    if w is not None and w.get("href"):
        return w.get("href")
    w = e.find("link")
    if w is None:
        return ""
    return w.get("href") or (w.text or "").strip()


def przetworz(wpisy: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    """(nazwa_kanalu, element) -> kandydaci. Czysta funkcja, testowalna."""
    widziane: set[str] = set()
    out: list[dict[str, Any]] = []
    for kanal, e in wpisy or []:
        tytul = _pole(e, "title")
        if not tytul:
            continue
        surowy = " ".join(tytul.split())
        if NIE_TEMAT.search(surowy):
            continue
        czysty = oczysc(surowy)
        if len(czysty.split()) < 4:
            continue
        klucz = re.sub(r"[^a-z0-9 ]", "", czysty.lower())[:60]
        if klucz in widziane:
            continue
        widziane.add(klucz)
        out.append({
            "temat": czysty,
            "surowy": surowy,
            "kanal": kanal,
            "data": _data_wpisu(e),
            "url": _link_wpisu(e),
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


# Rok to nie numer wersji. Bez tego wyzwalacz premiery bral „AGI 2026" u dwoch
# kanalow za premiere modelu o numerze 2026.
_ROK = re.compile(r"^(19|20)\d\d$")


def _numer_wersji(slowo: str) -> bool:
    """Czy token wyglada na numer wydania: ma cyfre i nie jest rokiem.

    „5.1", „5.3", „gpt-6", „4.6" — tak. „2026", „claude", „agents" — nie.
    """
    return any(c.isdigit() for c in slowo) and not _ROK.match(slowo)


def wielkie_wydarzenia(korpus: list[dict[str, Any]], min_kanalow: int = 3,
                       min_wspolnych: int = 2, swiezosc_dni: int = 4,
                       min_kanalow_premiery: int = 2) -> list[dict[str, Any]]:
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
    z jakosci. Ta funkcja NICZEGO NIE BLOKUJE: pusta lista znaczy „spokojny
    dzien", a nie „stop".

    SYGNAL JEST OBIEKTYWNY I LICZY GO KOD, nie model. Sa dwa i celowo mierza
    co innego:

    1. FALA — ten sam rdzen tematu u co najmniej `min_kanalow` ROZNYCH
       kanalow, i KAZDY z tych kanalow ma film nie starszy niz `swiezosc_dni`.
       Jeden kanal krzyczacy „EVERYTHING CHANGED" to nie wydarzenie, tylko
       naglowek.

    2. PREMIERA — NOWY numer wersji u co najmniej `min_kanalow_premiery`
       ROZNYCH kanalow w tym samym oknie. Powod jest zmierzony: w dniu
       premiery jedynym slowem wspolnym dla kanalow jest NAZWA I NUMER, bo
       reszta tytulu to szum, u kazdego inny — a regula fali wymaga wtedy
       dwoch wspolnych slow i dlatego milczy. 2 wrzesnia 2026 o Fable 5.1
       mowily tego dnia dwa kanaly (Wes Roth, Matthew Berman) i wspolne mialy
       dokladnie {fable, 5.1}; wykrywacz oddal zero.

       Nie jest to obnizenie progu do dwoch kanalow, bo warunki sa trzy naraz:
       token musi miec CYFRE i nie byc rokiem, NIE MOZE wystepowac w korpusie
       sprzed okna, i musza go miec DWA rozne kanaly. Zmierzone na 64 dniach
       korpusu: ten wyzwalacz odpalil sie dwa razy, obydwa to premiera Fable
       5.1. Doktryna „jeden kanal to nie wydarzenie" zostaje nietknieta —
       swiadek nadal musi byc wiecej niz jeden.

    NOWOSC LICZYMY WZGLEDEM PODANEGO KORPUSU, wiec te funkcje wola sie na
    PELNYM korpusie (`korpus_kanalow(200)`), nigdy na przycietym: w korpusie
    bez historii kazdy numer wersji wyglada na nowy.
    """
    from datetime import datetime as _d, timedelta as _td, timezone as _tz
    granica = (_d.now(_tz.utc) - _td(days=swiezosc_dni)).strftime("%Y-%m-%d")

    # PIERWSZENSTWO PRZYSLUGUJE TEMU, CO DZIEJE SIE TERAZ — i liczy sie to
    # NA POZYCJE, nie na grupe. Poprzednia wersja sprawdzala swiezosc przez
    # `max(data)` calej grupy, wiec trzy kanaly rozrzucone na trzy miesiace
    # przechodzily dzieki jednemu swiezemu filmowi. Tak przeszlo JEDYNE
    # wykrycie w historii tej funkcji: grupa GLM 5.3 miala filmy z 15, 26 i 30
    # sierpnia oraz 1 wrzesnia — rozpietosc 17 dni przy oknie czterech.
    # Rzecz, o ktorej trzy kanaly mowily dwa tygodnie temu, jest historia,
    # a nie powodem, zeby przestawiac kolejke.
    swieze = [p for p in (korpus or []) if (p.get("data") or "") >= granica]
    if not swieze:
        return []

    # --- 1. FALA: ten sam rdzen u wielu kanalow, kazdy w oknie ---
    grupy: list[dict[str, Any]] = []
    for poz in swieze:
        rdzen = _rdzen(poz.get("temat") or "")
        if len(rdzen) < min_wspolnych:
            continue
        for g in grupy:
            if len(g["rdzen"] & rdzen) >= min_wspolnych:
                g["pozycje"].append(poz)
                g["kanaly"].add(poz.get("kanal", ""))
                g["rdzen"] &= rdzen or g["rdzen"]
                break
        else:
            grupy.append({"rdzen": rdzen, "pozycje": [poz], "premiera": False,
                          "kanaly": {poz.get("kanal", "")}})

    # --- 2. PREMIERA: numer wersji, ktorego wczesniej w korpusie nie bylo ---
    # Pozycja bez daty liczy sie do historii, nie do okna — czyli w razie
    # watpliwosci wyzwalacz MILCZY, zamiast strzelac.
    znane: set[str] = set()
    for p in korpus or []:
        if (p.get("data") or "") < granica:
            znane |= _rdzen(p.get("temat") or "")
    premiery: dict[str, list[dict[str, Any]]] = {}
    for p in swieze:
        for s in _rdzen(p.get("temat") or ""):
            if s not in znane and _numer_wersji(s):
                premiery.setdefault(s, []).append(p)
    for _s, pozycje in sorted(premiery.items()):
        kanaly = {p.get("kanal", "") for p in pozycje}
        if len(kanaly) < min_kanalow_premiery:
            continue
        # ETYKIETA TO CZESC WSPOLNA TYTULOW, NIE SAM NUMER. `stages` robi
        # z niej klucz pamieci zdarzen, wiec gole „5.1" zlepiloby dwie rozne
        # premiery o tym samym numerze w jedno i druga nigdy nie otworzylaby
        # furtki. „5.1, fable" jest jednoznaczne.
        wspolne = set.intersection(*[_rdzen(p.get("temat") or "")
                                     for p in pozycje])
        grupy.append({"rdzen": wspolne or {_s}, "pozycje": pozycje,
                      "premiera": True, "kanaly": kanaly})

    # JEDNO ZDARZENIE = JEDEN WPIS. Kazdy wpis kosztuje, bo `stages` otwiera
    # platne szukanie raz na KAZDY nowy klucz zdarzenia (~0,23 USD). Skleic
    # trzeba dwa przypadki: premiera zlapana juz przez fale, oraz dwa numery
    # z tych samych tytulow („fable 5.1" i „5.1"), ktore daja te sama etykiete.
    pokryte = {id(p) for g in grupy
               if not g["premiera"] and len(g["kanaly"]) >= min_kanalow
               for p in g["pozycje"]}
    wyniki: list[dict[str, Any]] = []
    widziane: set[tuple[str, ...]] = set()
    for g in grupy:
        if len(g["kanaly"]) < (min_kanalow_premiery if g["premiera"]
                               else min_kanalow):
            continue
        if g["premiera"] and all(id(p) in pokryte for p in g["pozycje"]):
            continue
        o_czym = sorted(g["rdzen"])[:6]
        if tuple(o_czym) in widziane:
            continue
        widziane.add(tuple(o_czym))
        wyniki.append({"o_czym": o_czym,
                       "kanalow": len(g["kanaly"]),
                       "kanaly": sorted(g["kanaly"]),
                       "tytuly": [p.get("temat") or "" for p in g["pozycje"][:4]],
                       "data": max((p.get("data") or "") for p in g["pozycje"]),
                       "premiera": g["premiera"]})

    # Premiera przed fala — wlasciciel chce pisac o nowym modelu tego samego
    # dnia; fala o rzeczy o tydzien starszej moze poczekac na drugie miejsce.
    wyniki.sort(key=lambda w: w["data"], reverse=True)
    wyniki.sort(key=lambda w: (not w["premiera"], -w["kanalow"]))
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


# KANAL, KTORY NIE ODPOWIADA, IDZIE NA PRZERWE — grzecznie, nie sprytnie.
#
# Zmierzone 5 wrzesnia 2026: 12 z 13 kanalow YouTube oddaje 404 albo 500. Nie
# sa to zle identyfikatory — ten sam adres ByCloud oddal 15 filmow kilkanascie
# minut wczesniej, a strona `@uchwytu` oddaje 200 i sciane bez identyfikatora.
# YouTube po prostu blokuje ten serwer, jak wiekszosc adresow w serwerowni.
#
# Bez przerwy walimy tam 12 razy na przebieg i 60 razy dziennie po nic — a
# powtarzane pukanie do serwisu, ktory nas odrzucil, blokade tylko poglebia.
# NIE OBCHODZIMY BLOKADY I NIE BEDZIEMY: przerwa to jest uznanie odmowy, nie
# jej omijanie. Po dobie probujemy raz jeszcze, bo blokady bywaja czasowe.
# PROG I DLUGOSC DOBRANE DO ZMIERZONEJ NATURY BLOKADY, nie z glowy.
#
# Sprawdzone 5 wrzesnia 2026 dwiema probami po piec kanalow: bez przerwy 1/5,
# z przerwa CZTERECH SEKUND 0/5. Rozkladanie zapytan w czasie NIE POMAGA, bo
# to nie jest limit na sekunde — ten sam kanal w ciagu godziny oddal 429, potem
# 404, potem 500, a na koncu 200 z poprawnym tytulem. Odpowiedz jest losowa dla
# kazdego zapytania: mniej wiecej jedno na piec przechodzi.
#
# Przy takim rozkladzie prog 3 bylby za ostry — kanal, ktory dziala w 20%,
# trafia trzy porazki z rzedu w polowie przypadkow i szedlby na przerwe bez
# powodu. Piec porazek to juz 33%, a przerwa szescio-, nie dwudziestoczterogodzinna,
# bo tresc i tak trzyma `ZAPAS_TRESCI_GODZIN`.
PORAZEK_DO_PRZERWY = 5
PRZERWA_GODZIN = 6

# ILE TRZYMAMY TRESC, KTORA RAZ SIE UDALA.
#
# To jest wlasciwa odpowiedz na przerywana blokade — i jedyna, ktora NIE
# ZWIEKSZA liczby zapytan. Kanal, ktory przeszedl raz, zostaje z nami na dobe;
# przy pieciu przebiegach dziennie i szansie jeden do pieciu zbieramy wiekszosc
# kanalow, nie pukajac ani razu wiecej niz dotad.
#
# Czego to NIE JEST: obejscia. Nie zmieniamy adresu, nie udajemy przegladarki,
# nie chodzimy przez posrednika. Pytamy tyle samo razy co wczoraj i po prostu
# nie wyrzucamy tego, co juz dostalismy.
ZAPAS_TRESCI_GODZIN = 24


def _plik_przerw():
    import config
    return config.DATA_DIR / "kanaly_na_przerwie.json"


def _wczytaj_przerwy() -> dict[str, Any]:
    import json
    try:
        return json.loads(_plik_przerw().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _zapisz_przerwy(dane: dict[str, Any]) -> None:
    import json
    try:
        _plik_przerw().write_text(json.dumps(dane, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    except Exception:
        pass


def _kanaly_na_przerwie() -> set[str]:
    from datetime import datetime, timezone
    teraz = datetime.now(timezone.utc).isoformat()
    return {n for n, w in _wczytaj_przerwy().items()
            if str((w or {}).get("do_kiedy") or "") > teraz}


def _zapisz_porazke(nazwa: str) -> None:
    from datetime import datetime, timedelta, timezone
    dane = _wczytaj_przerwy()
    w = dane.get(nazwa) or {}
    w["porazki"] = int(w.get("porazki") or 0) + 1
    if w["porazki"] >= PORAZEK_DO_PRZERWY:
        w["do_kiedy"] = (datetime.now(timezone.utc)
                         + timedelta(hours=PRZERWA_GODZIN)).isoformat()
        w["porazki"] = 0
    dane[nazwa] = w
    _zapisz_przerwy(dane)


def _plik_tresci():
    import config
    return config.DATA_DIR / "korpus_ostatnia_tresc.json"


def _wczytaj_tresci() -> dict[str, Any]:
    import json
    try:
        return json.loads(_plik_tresci().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _zapamietaj_tresc(nazwa: str, xml: str) -> None:
    """Odklada surowa odpowiedz zrodla, zeby przezyla jego zla godzine."""
    import json
    from datetime import datetime, timezone
    dane = _wczytaj_tresci()
    dane[nazwa] = {"kiedy": datetime.now(timezone.utc).isoformat(),
                   "xml": xml[:400_000]}
    try:
        _plik_tresci().write_text(json.dumps(dane, ensure_ascii=False),
                                  encoding="utf-8")
    except Exception:
        pass


def _tresc_z_zapasu(nazwa: str) -> str:
    """Ostatnia udana odpowiedz tego zrodla, jesli nie jest starsza niz doba."""
    from datetime import datetime, timedelta, timezone
    w = _wczytaj_tresci().get(nazwa) or {}
    kiedy = str(w.get("kiedy") or "")
    if not kiedy:
        return ""
    prog = (datetime.now(timezone.utc)
            - timedelta(hours=ZAPAS_TRESCI_GODZIN)).isoformat()
    return str(w.get("xml") or "") if kiedy > prog else ""


def _zapisz_sukces(nazwa: str) -> None:
    """Kanal, ktory oddal material, zaczyna liczenie od zera.

    Bez tego pojedyncze potkniecia z roznych dni sumowalyby sie do przerwy przy
    kanale, ktory dziala — a przerwa ma dotyczyc martwych, nie kapryśnych.
    """
    dane = _wczytaj_przerwy()
    if nazwa in dane:
        dane.pop(nazwa)
        _zapisz_przerwy(dane)


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
    _odpoczywa = _kanaly_na_przerwie()
    if _odpoczywa:
        print("  [kanaly] na przerwie po powtarzajacych sie bledach: %s"
              % ", ".join(sorted(_odpoczywa)), flush=True)
    with httpx.Client(timeout=config.FETCH_TIMEOUT_S, follow_redirects=True,
                      headers={"User-Agent": config.FETCH_USER_AGENT}) as c:
        for nazwa, cid in KANALY.items():
            if nazwa in _odpoczywa:
                continue
            xml = ""
            try:
                r = c.get(RSS, params={"channel_id": cid})
                if r.status_code == 200:
                    xml = r.text
                    _zapamietaj_tresc(nazwa, xml)
                else:
                    print("  [kanaly] %s: HTTP %s" % (nazwa, r.status_code),
                          flush=True)
                    _zapisz_porazke(nazwa)
            except Exception as exc:
                print("  [kanaly] %s: %s" % (nazwa, type(exc).__name__), flush=True)
                _zapisz_porazke(nazwa)
            # ZLA GODZINA ZRODLA NIE ZNACZY, ZE NIE MAMY JEGO TRESCI.
            # Blokada jest przerywana (patrz `ZAPAS_TRESCI_GODZIN`), wiec
            # siegamy po ostatnia udana odpowiedz zamiast zostawiac dziure.
            if not xml:
                xml = _tresc_z_zapasu(nazwa)
                if xml:
                    print("  [kanaly] %s: biore z zapasu (ostatnia udana doba)"
                          % nazwa, flush=True)
            if not xml:
                continue
            try:
                ile_przed = len(wpisy)
                for e in ET.fromstring(xml.encode("utf-8")).findall("a:entry", NS):
                    wpisy.append((nazwa, e))
                if len(wpisy) > ile_przed:
                    _zapisz_sukces(nazwa)
            except Exception as exc:
                print("  [kanaly] %s: nieczytelny feed (%s)"
                      % (nazwa, type(exc).__name__), flush=True)
        from datetime import datetime, timedelta, timezone
        prog_wieku = (datetime.now(timezone.utc)
                      - timedelta(days=config.MAKS_WIEK_ZRODLA_DNI)
                      ).strftime("%Y-%m-%d")

        # ZRODLA PIERWOTNE. Ta sama sesja HTTP, ta sama funkcja `przetworz` —
        # roznica jest w formacie feedu (RSS 2.0 zamiast Atoma) i obsluguje ja
        # `_pole`. Awaria jednego zrodla nie moze zabrac reszty, wiec kazde
        # ma wlasny `try`, tak jak kanaly.
        for nazwa, adres in ZRODLA.items():
            # TEN SAM ZAPAS CO PRZY KANALACH. Zrodlo pierwotne tez ma prawo
            # miec zla godzine, a jego zla godzina nie moze znaczyc dziury w
            # spizarni — bo pusta spizarnia to platne szukanie.
            surowy = ""
            try:
                r = c.get(adres)
                if r.status_code == 200:
                    surowy = r.text
                    _zapamietaj_tresc("zrodlo:" + nazwa, surowy)
                else:
                    print("  [zrodla] %s: HTTP %s" % (nazwa, r.status_code),
                          flush=True)
            except Exception as exc:
                print("  [zrodla] %s: %s" % (nazwa, type(exc).__name__),
                      flush=True)
            if not surowy:
                surowy = _tresc_z_zapasu("zrodlo:" + nazwa)
                if surowy:
                    print("  [zrodla] %s: biore z zapasu (ostatnia udana doba)"
                          % nazwa, flush=True)
            if not surowy:
                continue
            try:
                korzen = ET.fromstring(surowy.encode("utf-8"))
                poz = korzen.findall(".//a:entry", NS) or korzen.findall(".//item")
                poz.sort(key=_data_wpisu, reverse=True)
                # WIEK ODCINAMY JUZ TUTAJ, inaczej niz przy kanalach. YouTube
                # oddaje 15 ostatnich filmow i to sa z natury rzeczy filmy
                # swieze; feed OpenAI ma 1164 wpisow, a Epoch AI publikuje
                # rzadko, wiec „dwanascie najnowszych" siega u niego czerwca.
                # Takie pozycje i tak odpadaja pozniej na terminie w banku —
                # ale zajmuja miejsce w korpusie, ktory idzie do promptu.
                for e in poz[:Z_JEDNEGO_ZRODLA]:
                    if _data_wpisu(e) < prog_wieku:
                        continue
                    wpisy.append((nazwa, e))
            except Exception as exc:
                print("  [zrodla] %s: %s" % (nazwa, type(exc).__name__), flush=True)

    k = przetworz(wpisy)
    print("  [kanaly] %d wpisow z %d kanalow i %d zrodel -> %d tematow"
          % (len(wpisy), len(KANALY), len(ZRODLA), len(k)), flush=True)
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
