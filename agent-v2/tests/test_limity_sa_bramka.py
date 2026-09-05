# -*- coding: utf-8 -*-
"""Zadeklarowane limity zrodel i fragmentow sa egzekwowane kodem, nie prosba.

CO SIE DZIALO (R5 z audytu researchu, potwierdzone odczytem naszego kodu).
`DISCOVERY_MAX_RESULTS` idzie do promptu jako „{max_results} is a ceiling",
a `CLASSIFY_MAX_EXCERPTS` jako liczba wyciagow — i na tym sie konczylo. Kod
przyjmowal tyle, ile model oddal, bez odsiewu powtorzonych adresow i bez
sufitu. Kazde zrodlo ponad limit to osobne POBRANIE i osobne wywolanie
KLASYFIKATORA; kazdy nadmiarowy fragment rosnie potem w wejsciu syntezy
i karty pisarza.

ZMIERZONE NA PRODUKCJI PRZED ZMIANA (8 przebiegow artykulu, tabela `sources`):
od 4 do 10 zrodel na przebieg i ZERO powtorzonych adresow — model dotad limitu
przestrzegal. To wada UTAJONA, nie zywa. Egzekwujemy ja mimo to, bo prosba
w prompcie nie jest bramka: jeden przebieg z dwudziestoma adresami kosztowalby
dwadziescia pobran, zanim ktokolwiek by to zauwazyl.

CZEGO SWIADOMIE NIE ROBIMY. `CLASSIFY_MAX_EXCERPT_CHARS` tez jest
deklarowane — i dlugosci NIE przycinamy. Ciecie cytatu w polowie potrafi
ODWROCIC jego znaczenie: wystarczy, ze na koncu stalo „not" albo warunek
zakresu. Za dlugi fragment kosztuje tokeny; przyciety potrafi kosztowac
falszywy dowod. Zglaszamy glosno i zostawiamy calosc.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_limity_sa_bramka.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import stages   # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


print("=== 1. DYSKOVERIA: POWTORZONE ADRESY I SUFIT ===")
import json   # noqa: E402

ILE = config.DISCOVERY_MAX_RESULTS
# Model oddaje DUZO WIECEJ niz sufit, w tym ten sam adres kilka razy
# w roznych postaciach (z ukosnikiem, z kotwica).
ZRODLA = ([{"url": "https://a.example/doc", "title": "t"}] * 3
          + [{"url": "https://a.example/doc/", "title": "t"}]
          + [{"url": "https://a.example/doc#sekcja", "title": "t"}]
          + [{"url": "https://b%d.example/x" % i, "title": "t"}
             for i in range(ILE + 8)])
ODP = json.dumps({"sources": ZRODLA}, ensure_ascii=False)

_ORYG = {"call": stages.llm.call, "dom": stages.db.recent_domains,
         "martwe": stages.hosty_ktore_nigdy_nie_dzialaly}
try:
    stages.llm.call = lambda *a, **kw: ODP
    stages.db.recent_domains = lambda conn, limit: []
    # BEZ BAZY. Ten test bada sufit i odsiew powtorek, a nie historie hostow —
    # `conn` jest tu `None`, wiec pytanie do bazy musi zostac uciszone.
    stages.hosty_ktore_nigdy_nie_dzialaly = lambda conn: []
    # `collect_urls` dostaje adresy „z sieci" — podstawiamy wszystkie, zeby
    # filtr „spoza wyszukiwania" nie mieszal sie do tego pomiaru.
    def _call(purpose, system, user, **kw):
        lista = kw.get("collect_urls")
        if lista is not None:
            lista.extend(z["url"] for z in ZRODLA)
        return ODP
    stages.llm.call = _call

    kept = stages.discovery(None, None, "pytanie", [])
    url = [z["url"] for z in kept]
    sprawdz("nie przekracza sufitu", len(kept) <= ILE, len(kept))
    sprawdz("ten sam adres tylko raz",
            len({u.split("#")[0].rstrip("/") for u in url}) == len(url), url[:4])
    sprawdz("ukosnik i kotwica to ten sam adres",
            sum(1 for u in url if "a.example/doc" in u) == 1,
            [u for u in url if "a.example" in u])
finally:
    stages.llm.call = _ORYG["call"]
    stages.db.recent_domains = _ORYG["dom"]
    stages.hosty_ktore_nigdy_nie_dzialaly = _ORYG["martwe"]

print()
print("=== 2. KLASYFIKATOR: SUFIT LICZBY FRAGMENTOW ===")
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("classify przycina liczbe wyciagow",
        "excerpts[: config.CLASSIFY_MAX_EXCERPTS]" in _zr)
sprawdz("i melduje, ze przycial",
        "fragmentow przy suficie" in _zr)

print()
print("=== 3. DLUGOSCI CYTATU NIE PRZYCINAMY — SWIADOMIE ===")
# Ta asercja jest zapisem DECYZJI, a nie zachowania: gdyby ktos kiedys dopisal
# przycinanie tekstu, ma najpierw przeczytac, dlaczego go tu nie ma.
sprawdz("nie ma ciecia tekstu fragmentu",
        "[: config.CLASSIFY_MAX_EXCERPT_CHARS]" not in _zr)
sprawdz("ale za dlugie sa zglaszane",
        "dluzszych niz" in _zr and "ciecie zmienia sens" in _zr)

print()
print("=== 4. SUFITY SA LICZBAMI Z KONFIGURACJI, NIE WPISANE W KOD ===")
sprawdz("sufit zrodel z config", isinstance(config.DISCOVERY_MAX_RESULTS, int)
        and config.DISCOVERY_MAX_RESULTS > 0, config.DISCOVERY_MAX_RESULTS)
sprawdz("sufit fragmentow z config",
        isinstance(config.CLASSIFY_MAX_EXCERPTS, int)
        and config.CLASSIFY_MAX_EXCERPTS > 0, config.CLASSIFY_MAX_EXCERPTS)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
