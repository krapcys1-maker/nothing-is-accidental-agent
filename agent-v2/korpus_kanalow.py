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
    # llama.cpp USUNIETE 27.09.2026: tytuly wydan to numery kompilacji („b6543"),
    # `przetworz` odrzucal kazdy jako krotszy niz cztery slowa — zero wpisow.
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
    # NAZWA Z DOPISKIEM, bo „MLST" istnieje juz w KANALY. Korpus grupuje po
    # nazwie zrodla, wiec dwa rozne feedy pod jedna nazwa byly by nierozroznialne
    # w logu i w polu `kanal_zrodlowy` przy fakcie.
    "MLST podcast":    "https://anchor.fm/s/1e4a0eac/podcast/rss",
    # USUNIETE 27.09.2026 (audyt zrodel, `robocze/audyt_zrodel.py`): „Forward
    # Future" (ostatni wpis 2024-02), „Dr Waku pisany" (2025-06) i
    # „Zsolnai-Fehér" (2019-06) — martwe feedy, ktore tylko wydluzaly przebieg.
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

# ZRODLA O LUDZIACH — silnik tematow, 26 wrzesnia 2026 (eksperyment E6).
# Plan: `agent-v2/docs/WYBOR_TEMATOW_2026-09-26.md`.
#
# Wszystko wyzej to blogi firm, wydania bibliotek, strony awarii i podcasty
# branzowe; o ludziach pisza tam tylko Wpadki AI, Komisja UE i Transformer.
# A spizarnia (`tresc_zrodel`) bierze teksty wlasnie stad, wiec bank byl
# w 70% branzowy — o temacie decydowal kod, nie model (pomiar 26.09: z osmiu
# tekstow spizarni siedem branzowych).
#
# Licza sie jako kanaly w regule „trzy czwarte z kanalow" (decyzja wlasciciela
# zostaje; zmienia sie to, co jest kanalem), bo trafiaja do tego samego korpusu,
# z ktorego `stages.znajdz_ciekawostki` liczy `z_kanalu`.
#
# SPRAWDZONE NA ZYWO z serwera 26.09 (`pomiary/zrodla_ludzie.py`): tytul feedu,
# data ostatniego wpisu, wpisy o AI z 30 dni — nie sam kod 200.
#     CourtListener   17 z 17 (zapytanie juz jest o AI)   ostatni 25.09
#     EdSurge         12 z 21                             ostatni 23.09
#     Rest of World    9 z 12                             ostatni 24.09
#     Pew              8 z 90                             ostatni 25.09
#     EFF             13 z 34                             ostatni 25.09
#     404 Media        7 z 15                             ostatni 25.09
#     KFF Health News  1 z 10     The 74   1 z 25     FTC konsumenci   1 z 11
#     arXiv cs.CY, cs.HC  tytul poprawny, zero wpisow: sobota, arXiv nie
#                         publikuje w weekendy. Jesli w tygodniu pusty, wypada.
# ODRZUCONE przy tej samej probie: NBER (404 i nieczytelny XML), FDA (401),
# Tech Policy Press (zero wpisow), FTC komunikaty (0 o AI), SEC (1 o AI i wymog
# adresu kontaktowego w naglowku), The Markup i AlgorithmWatch (0 o AI).
# Federal Register (27 dokumentow o AI w 30 dni) to API, nie feed — osobny krok.
ZRODLA_LUDZIE = {
    "CourtListener":  "https://www.courtlistener.com/feed/search/"
                      "?q=%22artificial+intelligence%22&type=o",
    "EdSurge":        "https://www.edsurge.com/articles_rss",
    "The 74":         "https://www.the74million.org/feed/",
    "KFF Health":     "https://kffhealthnews.org/feed/",
    "Pew":            "https://www.pewresearch.org/feed/",
    "FTC konsumenci": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
    "EFF":            "https://www.eff.org/rss/updates.xml",
    "404 Media":      "https://www.404media.co/rss/",
    "Rest of World":  "https://restofworld.org/feed/latest",
    "arXiv cs.CY":    "https://rss.arxiv.org/rss/cs.CY",
    "arXiv cs.HC":    "https://rss.arxiv.org/rss/cs.HC",
    # SERWISY, KTORE CZYTAJA LUDZIE — 27.09.2026, wlasciciel: „sprawdz tez
    # zrodla, chce pisac ciekawe notki".
    #
    # ZMIERZONE tego ranka (`robocze/audyt_zrodel.py`): notki z blogow
    # laboratoriow mialy najslabszy odbior (latent.space 3 notki po 10
    # wyswietlen i 0 odwiedzin profilu, pytorch.org 0), a najlepsze notki konta
    # dotyczyly pieniedzy, praw i codziennego doswiadczenia czytelnika.
    # Najwieksza historia dnia (OpenAI wstrzymuje trening najmocniejszych
    # modeli; agenci OpenAI na stronach rzadu USA) byla w The Verge, BBC i NPR,
    # a w naszym korpusie — tylko z jednej strony.
    #
    # SPRAWDZONE Z SERWERA (`robocze/sonda_nowych_zrodel.py`): feed odpowiada,
    # wpisy o AI z ostatnich 3 dni, tekst najnowszego da sie pobrac:
    #     The Verge AI 9, BBC Tech 6 (z 13), NPR Tech 4 (z 10), Ars Technica
    #     AI 6, The Conversation AI 12, TechXplore AI 14, Wired AI 5, MIT
    #     Technology Review AI 1 (4 w tygodniu), Retraction Watch 2, Futurism
    #     AI 9 — wszystkie „tekst: OK" (6-12 tys. znakow).
    # ODRZUCONE przy tej samej probie: TechCrunch AI (15 w 3 dni, ale glownie
    # rundy finansowania — zajelyby oba miejsca branzy w spizarni), Guardian
    # (404), Nieman Lab i Stanford HAI (nieczytelny XML), ProPublica, Quanta
    # i Our World in Data (0 o AI), The Markup, AI Snake Oil, One Useful Thing,
    # Understanding AI i Platformer (0 wpisow z 7 dni), Techdirt (glownie
    # felietony prawne).
    #
    # Wszystkie przechodza `FILTR_O_AI` (jak reszta tej tabeli), a styk
    # dostaja z TYTULU — patrz `STYK_Z_TYTULU`.
    "The Verge AI":   "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "BBC Tech":       "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "NPR Tech":       "https://feeds.npr.org/1019/rss.xml",
    "Ars Technica AI": "https://arstechnica.com/ai/feed/",
    "The Conversation AI": "https://theconversation.com/us/topics/"
                           "artificial-intelligence-ai-90/articles.atom",
    "TechXplore AI":  "https://techxplore.com/rss-feed/machine-learning-ai-news/",
    "Wired AI":       "https://www.wired.com/feed/tag/ai/latest/rss",
    "MIT Tech Review AI": "https://www.technologyreview.com/topic/"
                          "artificial-intelligence/feed",
    "Retraction Watch": "https://retractionwatch.com/feed/",
    "Futurism AI":    "https://futurism.com/categories/ai-artificial-intelligence/feed",
}

# STYK ZRODLA — gdzie ludzie spotykaja to, o czym zrodlo pisze. NIE PYTAMY
# MODELU: styk faktu kod przepisuje ze zrodla (`stages.styk_ze_zrodla`), tak
# samo jak `z_kanalu`. Zrodla spoza tej tabeli sa `branza`.
STYK_ZRODLA = {
    "CourtListener": "prawo", "EdSurge": "szkola", "The 74": "szkola",
    "KFF Health": "zdrowie", "Pew": "codziennosc", "FTC konsumenci": "pieniadze",
    "EFF": "prawo",
    # Juz w korpusie od dawna, dotad liczone jak branza.
    "Wpadki AI": "szkody", "Komisja UE": "prawo", "Transformer": "prawo",
}

# ZRODLA MIESZANE: styk z tytulu, a gdy tytul nie ma zadnego slowa z mapy,
# wartosc tutaj. Rest of World pisze w tym miesiacu glownie o wyscigu z Chinami,
# a to jest branza, nie praca; arXiv cs.CY i cs.HC to badania o ludziach.
STYK_Z_TYTULU = {"Rest of World": "branza", "404 Media": "codziennosc",
                 "arXiv cs.CY": "ludzie", "arXiv cs.HC": "ludzie",
                 # Serwisy ogolne (27.09.2026) pisza i o branzy, i o ludziach:
                 # bez slowa z mapy tytul zostaje branza, zeby kwota spoza
                 # branzy (E6) nie liczyla premiery modelu jako „codziennosci".
                 "The Verge AI": "branza", "BBC Tech": "branza",
                 "NPR Tech": "branza", "Ars Technica AI": "branza",
                 "TechXplore AI": "branza", "Wired AI": "branza",
                 "MIT Tech Review AI": "branza", "Futurism AI": "branza",
                 # Te dwa pisza z definicji o ludziach i instytucjach: badacze
                 # o skutkach AI i uczciwosc nauki.
                 "The Conversation AI": "ludzie", "Retraction Watch": "ludzie"}
# Kolejnosc ma znaczenie: pierwsze trafienie wygrywa, a szkola i zdrowie sa
# wezsze niz praca czy prawo.
MAPA_STYKU = (
    ("szkola", re.compile(r"\b(students?|teachers?|schools?|classrooms?|"
                          r"universit(?:y|ies)|colleges?|education|homework|"
                          r"children|kids|teens?)\b", re.IGNORECASE)),
    ("zdrowie", re.compile(r"\b(patients?|doctors?|nurses?|hospitals?|"
                           r"health|medical|clinics?|therap(?:y|ists?))\b",
                           re.IGNORECASE)),
    ("praca", re.compile(r"\b(workers?|jobs?|employees?|employment|hiring|"
                         r"layoffs?|wages?|labou?r|unions?|gig|freelancers?)\b",
                         re.IGNORECASE)),
    ("prawo", re.compile(r"\b(courts?|judges?|lawsuits?|laws?|legal|"
                         r"regulat\w+|police|surveillance|privacy)\b",
                         re.IGNORECASE)),
    ("pieniadze", re.compile(r"\b(scams?|fraud|prices?|consumers?|loans?|"
                             r"insurance)\b", re.IGNORECASE)),
)


def styk_wpisu(kanal: str, tytul: str = "") -> str:
    """Styk jednego wpisu korpusu: ze zrodla, a przy zrodle mieszanym z tytulu."""
    if kanal in STYK_Z_TYTULU:
        return next((s for s, wz in MAPA_STYKU if wz.search(tytul or "")),
                    STYK_Z_TYTULU[kanal])
    return STYK_ZRODLA.get(kanal, "branza")


# FILTR O AI dla feedow, ktore pisza o wszystkim (Pew: polityka i religia, EFF:
# cale prawa cyfrowe, KFF: cala sluzba zdrowia). Ten sam wzorzec, ktorym mierzy
# `pomiary/zrodla_ludzie.py` — pomiar i produkcja licza to samo. Bez slowa
# „algorithm": w komunikatach urzedow to najczesciej handel algorytmiczny.
# CourtListener nie jest filtrowany: zapytanie juz jest o AI, a tytul orzeczenia
# to same nazwiska stron. `A.I.` z kropkami stoi osobno: w grupie zamknietej
# przez `\b` nie trafialo nigdy, bo po kropce nie ma granicy slowa.
FILTR_O_AI = set(ZRODLA_LUDZIE) - {"CourtListener"}
O_AI = re.compile(
    r"\bA\.I\.|\b(AI|artificial intelligence|machine learning|chatbots?|"
    r"ChatGPT|OpenAI|Anthropic|Claude|Gemini|Copilot|LLMs?|"
    r"large language models?|generative|deepfakes?|facial recognition|"
    r"automated decision[- ]making|neural networks?)\b",
    re.IGNORECASE)


def o_ai(e: Any) -> bool:
    """Czy wpis feedu dotyczy AI — po tytule i poczatku opisu (RSS albo Atom)."""
    opis = _pole(e, "description") or _pole(e, "summary")
    return bool(O_AI.search(_pole(e, "title") + " " + opis[:600]))


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
            # STYK ZE ZRODLA — patrz `STYK_ZRODLA`. Idzie dalej do spizarni
            # i z niej do faktu; model go nie nadaje.
            "styk": styk_wpisu(kanal, czysty),
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


# PAMIEC WERSJI — dopisana 27.09.2026 po premierze, ktora nia nie byla.
#
# 26.09 wykrywacz oglosil PREMIERE „3.8" i otworzyl furtke szukania, choc Gemini
# 3.8 obsluzylismy jako premiere juz 6.09 — dwadziescia dni wczesniej. Nowosc
# numeru liczyl wzgledem korpusu sprzed okna, a korpus to 200 najnowszych
# tematow, czyli kilka dni; po dolozeniu zrodel o ludziach — jeszcze mniej.
# Wlasciciel: pisanie o premierze dwa tygodnie po premierze jest niewybaczalne.
#
# Dlatego pierwsze pojawienie sie wersji zapisujemy NA STALE, z data wpisu,
# nie z data przebiegu. Klucz laczy numer z nazwa rodziny z tego samego tytulu
# („gemini 3.8"), zeby Opus 5.5 z wrzesnia nie zablokowal kiedys premiery innego
# modelu o numerze 5.5. Numer ze swoja nazwa w srodku („gpt-6", „glm-5.3-flash")
# jest kluczem sam dla siebie.
RODZINY_MODELI = ("gemini", "gemma", "claude", "opus", "sonnet", "haiku", "fable",
                  "grok", "llama", "deepseek", "qwen", "glm", "kimi", "minimax",
                  "mistral", "phi", "nova", "veo", "sora", "imagen", "codex")


def klucze_wersji(tekst: str, tylko_z_rodzina: bool = False) -> set[str]:
    """Klucze wersji z tekstu: „gemini 3.8", „gpt-6" albo sam „3.8", gdy rodziny brak.

    `tylko_z_rodzina`: bez gołych numerów — dla tekstu ciaglego (fakty, notki),
    w ktorym „5.5" to rownie dobrze „5.5 miliarda".
    """
    slowa = _rdzen(str(tekst or ""))
    rodziny = {r for r in RODZINY_MODELI if r in slowa}
    klucze: set[str] = set()
    for w in slowa:
        if not _numer_wersji(w):
            continue
        if w[0].isalpha():
            klucze.add(w)
        elif rodziny:
            klucze |= {"%s %s" % (r, w) for r in rodziny}
        elif not tylko_z_rodzina:
            klucze.add(w)
    return klucze


def pamiec_wersji(korpus: list[dict[str, Any]],
                  dodatkowe: list[tuple[str, str, bool]] | None = None) -> dict[str, str]:
    """{klucz wersji: najwczesniejszy dzien, w ktorym go widzielismy}. Trwala.

    `korpus` — tytuly z kanalow i zrodel, z data wpisu. Wersja liczy sie
    dopiero, gdy mowia o niej DWA ROZNE KANALY, a data to dzien, w ktorym
    dolaczyl drugi: jeden film z przeciekiem („Gemini 4 LEAKED") nie moze
    tygodniami wczesniej zamknac drogi prawdziwej premierze. `dodatkowe` —
    trojki (tekst, data, tylko_z_rodzina) z naszej historii: obsluzone
    wydarzenia i wystawione notki. Plik lezy w katalogu danych instancji;
    nieudany zapis nie zatrzymuje przebiegu.

    BANKU FAKTOW TU NIE MA — zmierzone przy pierwszym uruchomieniu na
    produkcji: dawal „gemini 4.0" z 12.09 (zapowiedz) i ceny w rodzaju
    „gemini 7.50", czyli wlasnie przedwczesne „juz bylo".
    """
    import json

    import config
    plik = config.DATA_DIR / "wersje_widziane.json"
    try:
        znane = json.loads(plik.read_text(encoding="utf-8"))
        if not isinstance(znane, dict):
            znane = {}
    except (OSError, ValueError):
        znane = {}
    zmiana = False

    def _dopisz_klucz(k: str, data: str) -> None:
        nonlocal zmiana
        if k not in znane or data < str(znane[k]):
            znane[k] = data
            zmiana = True

    def _dopisz(tekst: str, data: str, tylko_z_rodzina: bool) -> None:
        data = str(data or "")[:10]
        if len(data) != 10:
            return
        for k in klucze_wersji(tekst, tylko_z_rodzina):
            _dopisz_klucz(k, data)

    # KORPUS: data, w ktorej o wersji mowil juz DRUGI kanal.
    kanaly_wersji: dict[str, dict[str, str]] = {}
    for p in korpus or []:
        data = str(p.get("data") or "")[:10]
        if len(data) != 10:
            continue
        for k in klucze_wersji(p.get("temat") or ""):
            dni = kanaly_wersji.setdefault(k, {})
            kanal = str(p.get("kanal") or "?")
            if kanal not in dni or data < dni[kanal]:
                dni[kanal] = data
    for k, dni in kanaly_wersji.items():
        if len(dni) >= 2:
            _dopisz_klucz(k, sorted(dni.values())[1])
    for tekst, data, tylko_z_rodzina in dodatkowe or []:
        _dopisz(tekst, data, tylko_z_rodzina)
    if zmiana:
        try:
            plik.parent.mkdir(parents=True, exist_ok=True)
            tymczasowy = plik.with_suffix(".json.tmp")
            tymczasowy.write_text(json.dumps(znane, ensure_ascii=False, indent=1,
                                             sort_keys=True), encoding="utf-8")
            tymczasowy.replace(plik)
        except OSError as exc:
            print("  [wydarzenia] nie zapisalem pamieci wersji (%s)"
                  % type(exc).__name__, flush=True)
    return znane


def wielkie_wydarzenia(korpus: list[dict[str, Any]], min_kanalow: int = 3,
                       min_wspolnych: int = 2, swiezosc_dni: int = 4,
                       min_kanalow_premiery: int = 2,
                       wersje_widziane: dict[str, str] | None = None,
                       ) -> list[dict[str, Any]]:
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
    # WERSJA WIDZIANA PRZED OKNEM NIE JEST PREMIERA — takze wtedy, gdy korpus
    # jej juz nie pamieta. Patrz `pamiec_wersji`.
    stare_wersje = {k for k, d in (wersje_widziane or {}).items()
                    if str(d)[:10] < granica}

    def _juz_byla(s: str, temat: str) -> bool:
        klucze = klucze_wersji(temat)
        if any(k == s or k.endswith(" " + s) for k in klucze & stare_wersje):
            return True
        # TYTUL BEZ NAZWY RODZINY („3.8 Live gets a face") — goly numer pod
        # koniec wrzesnia to Gemini 3.8, ktore juz bylo. Tytul Z nazwa innej
        # rodziny („Grok 5.5") tu nie trafia, wiec cudza premiera nie przepada.
        if s in klucze:
            return any(k == s or k.endswith(" " + s) for k in stare_wersje)
        return False

    premiery: dict[str, list[dict[str, Any]]] = {}
    for p in swieze:
        for s in _rdzen(p.get("temat") or ""):
            if (s not in znane and _numer_wersji(s)
                    and not _juz_byla(s, p.get("temat") or "")):
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
class _Pomijam(Exception):
    """Tresc mamy z zapasu — sieci nie dotykamy. Sterowanie, nie awaria."""


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
            # KANAL NA PRZERWIE NIE JEST PYTANY — ale jego zapas i tak
            # czytamy. Zapas nie kosztuje zadnego zapytania, wiec przerwa ma
            # oszczedzac pukanie, a nie wyrzucac tresc, ktora juz mamy.
            xml = ""
            if nazwa in _odpoczywa:
                xml = _tresc_z_zapasu(nazwa)
                if xml:
                    print("  [kanaly] %s: na przerwie, biore z zapasu" % nazwa,
                          flush=True)
                else:
                    continue
            try:
                if xml:
                    raise _Pomijam()
                r = c.get(RSS, params={"channel_id": cid})
                if r.status_code == 200:
                    xml = r.text
                    _zapamietaj_tresc(nazwa, xml)
                else:
                    print("  [kanaly] %s: HTTP %s" % (nazwa, r.status_code),
                          flush=True)
                    _zapisz_porazke(nazwa)
            except _Pomijam:
                pass
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
        for nazwa, adres in {**ZRODLA, **ZRODLA_LUDZIE}.items():
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
                # FILTR PRZED SUFITEM, nie po nim: Pew ma 90 wpisow w miesiacu,
                # z tego 8 o AI — dwanascie najnowszych przefiltrowanych
                # dawaloby jeden, dwa tematy zamiast osmiu.
                if nazwa in FILTR_O_AI:
                    poz = [e for e in poz if o_ai(e)]
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
    print("  [kanaly] %d wpisow z %d kanalow i %d zrodel (w tym %d o ludziach) -> %d tematow"
          % (len(wpisy), len(KANALY), len(ZRODLA) + len(ZRODLA_LUDZIE),
             len(ZRODLA_LUDZIE), len(k)), flush=True)
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
