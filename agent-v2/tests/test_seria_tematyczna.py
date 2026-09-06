# -*- coding: utf-8 -*-
"""Seria tematyczna: cztery notki o jednym temacie, jedna na dobe.

PO CO. Zmierzone 6 wrzesnia 2026 na produkcji: notki daly ZERO subskrypcji,
wszystkie siedem przyszlo z artykulow. Notki robia zasieg, ktory nie prowadzi
donikad, bo pojedyncza notka nie daje powodu, zeby wrocic.

CO TEN TEST NAPRAWDE SPRAWDZA. Nie to, ze funkcje sie wywoluja — to, ze
mechanizm nie da sie zepsuc w czterech miejscach, w ktorych to konto juz raz
sie na czyms podobnym przejechalo:

 1. STAN ZMIENIA SIE DOPIERO PO PUBLIKACJI. Fakt odhaczal sie kiedys przy
    znalezieniu i przepadal, gdy notka nie poszla. Dzien promocji artykulu
    odhaczal sie przy przejsciu bramki i artykul dostawal mniej niz piec notek.
    Tu ta sama wada dalaby czesci 1, 2 i 4.
 2. JEDNA CZESC NA DOBE. Szesc przebiegow na dobe wydaloby cala serie przed
    obiadem i „czesc 2 jutro" nie znaczyloby nic.
 3. PROG DOPASOWANIA ODSIEWA SMIECI. Przy progu 3 temat „AI w pracy" dostawal
    cztery fakty o aukcji upadlosciowej Spirit Airlines, kazdy za dokladnie
    3 punkty. Test odtwarza ten wlasnie przypadek.
 4. KONTEKST SERII NIE WYCIEKA NA ZWYKLA NOTKE. Gdyby zostawal z poprzedniego
    obiegu petli, zwykla notka wyszlaby z zapowiedzia ciagu dalszego.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_seria_tematyczna.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import seria   # noqa: E402

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


def czysto():
    """Kasuje stan miedzy sekcjami — inaczej sekcja 5 czyta smieci z 4."""
    for p in (seria.PLIK, seria.PLIK.with_suffix(".json.kopia"),
              seria.PLIK.with_suffix(".json.tmp")):
        try:
            p.unlink()
        except OSError:
            pass


def fakt(domain, tresc, **reszta):
    d = {"domain": domain, "fact": tresc}
    d.update(reszta)
    return d


# --- MATERIAL WZIETY Z ZYWEGO BANKU, CO DO ZNAKU ------------------------
# Pierwsza wersja tego testu miala fakty PRZEZE MNIE SKROCONE i oblala:
# skracajac, zjadlem terminy, wiec `PRAD` punktowalo 3 zamiast 15/11/10/6
# i nie przechodzilo progu. Test sprawdzal wtedy moje wyobrazenie o banku,
# a nie bank. To ta sama slepota, ktora dzis wyszla piec razy na atrapach
# `stages` — dlatego wpisy sa tu SKOPIOWANE, nie napisane.
#
# Wyciagniete z produkcji 6 wrzesnia 2026 (`indeks_kandydatow.json`),
# pola obciete do 300 znakow, poza tym bez zmian.
PRAD = [
    # 15 punktow dla swojego tematu
    {
        "domain": (
            "data centres and the electricity grid"
        ),
        "fact": (
            "Data centres already use roughly a fifth of all electricity "
            "metered in Ireland — headed toward about 30% by 2030 — which "
            "is why the energy regulator kept an effective moratorium on "
            "new Dublin-area data-centre grid connections for years, and "
            "why, even after a December 2025 connection policy relaxed i"
        ),
        "consequence": (
            "Your AI service's physical home is chosen by who can spare "
            "the megawatts — a country whose grid is full simply stops "
            "taking new data centres, no matter how cheap the land or "
            "tax."
        ),
        "wrong_belief": (
            "AI infrastructure gets built wherever a company decides to "
            "put a warehouse of servers."
        ),
        "actually": (
            "It gets built where spare electrons exist: Dublin, once "
            "Europe's data-centre capital, has run out of grid headroom, "
            "and operators are shifting new AI capacity to less "
            "constrained grids."
        ),
    },
    # 11 punktow dla swojego tematu
    {
        "domain": (
            "data centres and electricity"
        ),
        "fact": (
            "OpenAI and Anthropic began 2026 at roughly 2 gigawatts of "
            "compute each and will end it above 5 GW each — meaning about "
            "one-third of all new AI compute built worldwide this year "
            "goes to two companies, a share Dylan Patel (SemiAnalysis) "
            "projects will approach half next year; because a watt of new "
            "sili"
        ),
        "consequence": (
            "the AI service you use is increasingly served from data "
            "centres rented and run for two companies, not for a market "
            "of many."
        ),
        "wrong_belief": (
            "AI computing power is spread across many labs and companies."
        ),
        "actually": (
            "Two labs are absorbing roughly a third of the world's newly "
            "built compute this year, and once you multiply their wattage "
            "share by the faster chips of each new generation, the "
            "concentration in effective compute is even larger than the "
            "gigawatt numbers suggest."
        ),
    },
    # 10 punktow dla swojego tematu
    {
        "domain": (
            "data centres and compute procurement"
        ),
        "fact": (
            "Anthropic is paying the cloud provider Nscale roughly $45 "
            "billion over six years for about 460 megawatts of AI compute "
            "at Nscale's West Virginia 'Monarch' campus — capacity that "
            "Microsoft had reserved in March 2026 and abandoned in summer "
            "2026, with Anthropic then taking over as tenant."
        ),
        "consequence": (
            "The electricity behind your Claude conversations is "
            "contracted years in advance — one campus alone is sized to "
            "draw as much power as hundreds of thousands of homes."
        ),
        "wrong_belief": (
            "Big AI compute deals go to whoever has the best chips or the "
            "newest technology."
        ),
        "actually": (
            "The prize is power and a grid hookup: the site's value was "
            "its ~1.35 GW capacity and connection, and Anthropic, racing "
            "toward an IPO, has signed a string of these deals to lock up "
            "megawatts years in advance."
        ),
    },
    # 6 punktow dla swojego tematu
    {
        "domain": (
            "AI hardware and data centres"
        ),
        "fact": (
            "OpenAI's Jalapeño inference chip, a 700W part (sustained "
            "under 550W during testing) with 216 GiB of HBM4, beat "
            "NVIDIA's GB200 and GB300 racks in OpenAI's own published "
            "benchmark by 1.5–1.9x throughput per kilowatt and 1.7–3.6x "
            "lower latency — but it is inference-only and cannot train a "
            "model, and it"
        ),
        "consequence": (
            "the model answering your request may be served by OpenAI's "
            "own chip, but the model behind it was still trained on "
            "NVIDIA hardware."
        ),
        "wrong_belief": (
            "OpenAI's new chip beats NVIDIA's and frees the company from "
            "depending on it."
        ),
        "actually": (
            "Jalapeño wins on inference per watt, but it can't train a "
            "single model — so every new OpenAI model still depends on "
            "NVIDIA silicon for the training run."
        ),
    },
]

# CZTERY FAKTY, KTORE PRZY PROGU 3 WCHODZILY DO SERII „AI w pracy".
# Kazdy punktuje DOKLADNIE 3 i zaden nie jest o pracy: dwa razy ta sama
# aukcja upadlosciowa Spirit Airlines, dostep do programu cyber i opis
# produktu. To one sa wlasciwym sprawdzianem progu.
SMIECI = [
    # 3 punktow dla swojego tematu
    {
        "domain": (
            "your employer's data"
        ),
        "fact": (
            "Google won the bankruptcy auction for Spirit Airlines' "
            "internal data with a $10 million bid — roughly 100 million "
            "emails, 500 million Microsoft Teams chats and operational "
            "records — to train its AI models, beating an AI-training "
            "firm's $7.5 million bid."
        ),
        "consequence": (
            "the records your employer leaves behind can be auctioned to "
            "an AI lab after the company fails."
        ),
        "wrong_belief": (
            "AI companies get their training data by scraping what's "
            "public."
        ),
        "actually": (
            "They now bid at bankruptcy auctions for a defunct airline's "
            "internal records — a dataset nobody ever published."
        ),
    },
    # 3 punktow dla swojego tematu
    {
        "domain": (
            "data, privacy and employment"
        ),
        "fact": (
            "In Spirit Airlines' bankruptcy, Google won a $10 million "
            "court auction for the failed carrier's internal data — "
            "employee emails, Teams messages, spreadsheets and calendars "
            "— saying it would use the de-identified data to train its AI "
            "models, beating an AI-data company that bid $7.5 million; a "
            "flight"
        ),
        "consequence": (
            "your workplace emails and chat messages are an asset your "
            "employer owns, and in bankruptcy they can be sold to train "
            "someone else's AI."
        ),
        "wrong_belief": (
            "The data a company holds on its employees is the company's "
            "to keep, and dies with it."
        ),
        "actually": (
            "When a company goes bankrupt, its data is just an asset that "
            "a court sells to the highest bidder — and AI companies are "
            "now the bidders."
        ),
    },
    # 3 punktow dla swojego tematu
    {
        "domain": (
            "cyber model access governance"
        ),
        "fact": (
            "Even organisations approved for Google DeepMind's Fairwind "
            "cyber program may give Gemini 3.8 Flash Cyber only to their "
            "internal cybersecurity, incident-response or penetration- "
            "testing teams, must require phishing-resistant multi-factor "
            "authentication for every user, must track who has access, "
            "and ar"
        ),
        "consequence": (
            "Even if your employer is a vetted Fairwind partner, only "
            "designated security teams get the model, and no vendor will "
            "ever resell you access to it."
        ),
        "wrong_belief": (
            "Once your organisation is approved for a defensive cyber "
            "model, it is just another internal tool anyone on your "
            "security team can hand around."
        ),
        "actually": (
            "Approval carries hard operating strings: the model is walled "
            "to specific security teams, every user needs phishing- "
            "resistant MFA, employee access is tracked, and a partner "
            "cannot resell or even lend the capability to a contractor."
        ),
    },
    # 3 punktow dla swojego tematu
    {
        "domain": (
            "frontier model product"
        ),
        "fact": (
            "OpenAI positioned GPT-6 Astra around agentic jobs—computer "
            "use, software engineering, math/science, polished office "
            "work and cybersecurity—rather than around chat."
        ),
        "consequence": (
            "Your AI assistant subscription is now being marketed as a "
            "worker that can use software and handle security tasks, not "
            "just answer you."
        ),
        "wrong_belief": (
            "A new flagship language model is mostly judged by how well "
            "it writes and chats."
        ),
        "actually": (
            "OpenAI's stated launch framing is about tasks the model can "
            "do on a computer, including cybersecurity."
        ),
    },
]

print("=== 1. PUNKTOWANIE: `domain` wazy wiecej niz tresc ===")
_terminy = seria.TEMATY["Prad i data centre"]
_w_domain = seria.punkty(fakt("data centres and electricity", "nothing here"),
                         _terminy)
_w_tresci = seria.punkty(fakt("something else",
                              "the data centre and the electricity"), _terminy)
sprawdz("trafienie w `domain` daje wiecej niz to samo w tresci",
        _w_domain > 0 and _w_tresci > 0 and _w_domain >= _w_tresci,
        "domain=%s tresc=%s" % (_w_domain, _w_tresci))
sprawdz("fakt bez zwiazku z tematem dostaje zero",
        seria.punkty(fakt("cooking", "eggs boil at a lower temperature"),
                     _terminy) == 0)
# Liczenie po ROZNYCH terminach, nie po wystapieniach.
sprawdz("dwadziescia razy `grid` nie przebija prawdziwego dopasowania",
        seria.punkty(fakt("x", "grid " * 20), _terminy)
        < seria.punkty(PRAD[0], _terminy),
        "%s vs %s" % (seria.punkty(fakt("x", "grid " * 20), _terminy),
                      seria.punkty(PRAD[0], _terminy)))

print()
print("=== 2. PROG ODSIEWA TO, CO PRZY PROGU 3 WCHODZILO DO SERII ===")
# To jest sedno tego testu. Kazdy z tych czterech faktow ma DOKLADNIE 3 punkty
# dla tematu „AI w pracy" i zaden nie jest o pracy.
_praca = seria.TEMATY["AI w pracy"]
_punkty_smieci = [seria.punkty(f, _praca) for f in SMIECI]
sprawdz("kazdy smiec punktuje DOKLADNIE 3 — tyle, ile na zywym banku",
        _punkty_smieci == [3, 3, 3, 3], str(_punkty_smieci))
sprawdz("i zaden nie wchodzi do serii „AI w pracy\"",
        seria.zdatne(SMIECI, "AI w pracy") == [], _punkty_smieci)
sprawdz("a bank ze smieci NIE wyzywi zadnej serii",
        seria.mozliwe(SMIECI) == [], seria.mozliwe(SMIECI))
sprawdz("prawdziwy material przechodzi",
        len(seria.zdatne(PRAD, "Prad i data centre")) == 4,
        len(seria.zdatne(PRAD, "Prad i data centre")))

print()
print("=== 3. TEMAT WYBIERA BANK, NIE PLAN ===")
czysto()
_moz = seria.mozliwe(PRAD + SMIECI)
sprawdz("z mieszanego banku wychodzi dokladnie jeden temat",
        [t for t, _ in _moz] == ["Prad i data centre"], _moz)
sprawdz("zdatne sa posortowane od najlepiej dopasowanego",
        [p for p, _ in seria.zdatne(PRAD, "Prad i data centre")]
        == sorted((p for p, _ in seria.zdatne(PRAD, "Prad i data centre")),
                  reverse=True))

print()
print("=== 4. PROPOZYCJA NIE ZAPISUJE NICZEGO ===")
# Gdyby zapisywala, sprawdzenie na sucho zaczynaloby PRAWDZIWA serie, a jej
# pierwsza czesc nigdy by nie wyszla — czytelnik dostalby serie od czesci 2.
czysto()
_zapas = list(PRAD)
_p = seria.propozycja(_zapas)
sprawdz("propozycja jest", isinstance(_p, dict) and _p.get("czesc") == 1, _p)
sprawdz("plik stanu NIE powstal", not seria.PLIK.exists(),
        "istnieje: %s" % seria.PLIK.exists())
sprawdz("zadna seria nie jest aktywna", seria.aktywna() is None)
# PO AUDYCIE Z 6.09: `propozycja` oddaje KANDYDATOW i niczego nie zdejmuje.
# Wybor koncowy nalezy do `wybierz_material`, zeby czesc serii przechodzila
# przez TE SAMA straz roznorodnosci, co zwykla notka — patrz sekcja 14.
sprawdz("propozycja NICZEGO nie zdejmuje z zapasu",
        len(_zapas) == 4, len(_zapas))
sprawdz("oddaje liste kandydatow, nie jeden fakt",
        isinstance(_p.get("kandydaci"), list) and len(_p["kandydaci"]) == 4,
        type(_p.get("kandydaci")))
sprawdz("na czele stoi najlepiej dopasowany", _p["kandydaci"][0] is PRAD[0],
        (_p["kandydaci"][0] or {}).get("domain"))
sprawdz("kontekst niesie etykiete PO ANGIELSKU, nie polski klucz",
        (_p["kontekst"] or {}).get("etykieta") == "Where the electricity goes",
        (_p["kontekst"] or {}).get("etykieta"))
sprawdz("czesc 1 z 4 nie jest ostatnia",
        (_p["kontekst"] or {}).get("ostatnia") is False)

print()
print("=== 5. STAN POWSTAJE DOPIERO PRZY POTWIERDZONEJ PUBLIKACJI ===")
czysto()
seria.zapisz_czesc("Prad i data centre", 1, "111",
                   otwarcie="Data centres already use", fakt=PRAD[0]["fact"])
_a = seria.aktywna()
sprawdz("po zapisie seria jest aktywna", isinstance(_a, dict), _a)
sprawdz("i ma jedna wydana czesc", len((_a or {}).get("wydane") or []) == 1)
sprawdz("z numerem notki", ((_a or {}).get("wydane") or [{}])[0].get("id") == "111")

print()
print("=== 6. JEDNA CZESC NA DOBE ===")
# Szesc przebiegow na dobe wydaloby cala serie przed obiadem.
sprawdz("po wydaniu czesci 1 dzis nie ma czego wydawac",
        seria.czesc_na_dzis() is None, seria.czesc_na_dzis())
sprawdz("i propozycja tez milczy", seria.propozycja(list(PRAD)) is None)
# Cofamy dobe ostatniej czesci — udajemy, ze minela noc.
_s = seria.stan()
_s["aktywna"]["wydane"][0]["doba"] = "2000-01-01"
_s["aktywna"]["wydane"][0]["kiedy"] = "2000-01-01T00:00:00+00:00"
seria._zapisz(_s)
sprawdz("nazajutrz czeka czesc 2", seria.czesc_na_dzis() == 2,
        seria.czesc_na_dzis())

print()
print("=== 7. CZESC 2 NIE POWTARZA FAKTU CZESCI 1 ===")
_zapas2 = list(PRAD)
_p2 = seria.propozycja(_zapas2)
sprawdz("propozycja czesci 2 jest", (_p2 or {}).get("czesc") == 2, _p2)
sprawdz("i fakt czesci 1 NIE jest juz wsrod kandydatow",
        PRAD[0] not in ((_p2 or {}).get("kandydaci") or []),
        [(f or {}).get("domain") for f in ((_p2 or {}).get("kandydaci") or [])])
sprawdz("kontekst niesie otwarcie czesci 1, zeby go nie powtorzyc",
        "Data centres already use"
        in " ".join(((_p2 or {}).get("kontekst") or {}).get(
            "poprzednie_otwarcia") or []),
        ((_p2 or {}).get("kontekst") or {}).get("poprzednie_otwarcia"))

print()
print("=== 8. SERIA KONCZY SIE PO CZTERECH CZESCIACH ===")
czysto()
for i in range(1, 5):
    seria.zapisz_czesc("Prad i data centre", i, "id%d" % i,
                       otwarcie="otwarcie %d" % i, fakt="fakt %d" % i)
    if i < 4:
        _s = seria.stan()
        _s["aktywna"]["wydane"][-1]["doba"] = "2000-01-0%d" % i
        _s["aktywna"]["wydane"][-1]["kiedy"] = "2000-01-0%dT00:00:00+00:00" % i
        seria._zapisz(_s)
sprawdz("po czwartej czesci zadna seria nie jest aktywna",
        seria.aktywna() is None, seria.aktywna())
sprawdz("i seria wyladowala w skonczonych",
        len(seria.stan().get("skonczone") or []) == 1,
        seria.stan().get("skonczone"))
sprawdz("czesc 4 byla oznaczona jako ostatnia",
        (seria.kontekst(4, (seria.stan()["skonczone"][0])) or {}).get("ostatnia")
        is True)

print()
print("=== 9. ZAPIS ODPORNY NA BZDURY ===")
czysto()
# Czesc 2 bez trwajacej serii: NIE wolno zalozyc serii od srodka.
seria.zapisz_czesc("Prad i data centre", 2, "999")
sprawdz("czesc 2 bez serii nie zaklada niczego", seria.aktywna() is None,
        seria.aktywna())
seria.zapisz_czesc("Prad i data centre", 1, "1")
seria.zapisz_czesc("Prawo i sady", 2, "2")
sprawdz("czesc z innego tematu nie wchodzi do trwajacej serii",
        len((seria.aktywna() or {}).get("wydane") or []) == 1,
        (seria.aktywna() or {}).get("wydane"))
# Ten sam numer dwa razy — nieudana proba nie ma dolozyc drugiego wpisu.
_s = seria.stan()
_s["aktywna"]["wydane"][0]["doba"] = "2000-01-01"
_s["aktywna"]["wydane"][0]["kiedy"] = "2000-01-01T00:00:00+00:00"
seria._zapisz(_s)
seria.zapisz_czesc("Prad i data centre", 1, "1-znowu")
sprawdz("ta sama czesc nie zapisuje sie dwa razy",
        len((seria.aktywna() or {}).get("wydane") or []) == 1,
        (seria.aktywna() or {}).get("wydane"))

print()
print("=== 10. USZKODZONY PLIK CZYTA SIE JAKO PUSTY, NIE JAKO WYJATEK ===")
# Bank raz juz znikanl przez zwykly `write_text`; tu wada byla ta sama:
# przerwana seria zatrzymalaby notki na drugi dzien.
seria.PLIK.write_text("{to nie jest json", encoding="utf-8")
sprawdz("uszkodzony stan nie wywala przebiegu",
        seria.stan() == {"aktywna": None, "skonczone": []}, seria.stan())
seria.PLIK.write_text("[]", encoding="utf-8")
sprawdz("lista zamiast slownika tez nie wywala",
        seria.stan() == {"aktywna": None, "skonczone": []}, seria.stan())

print()
print("=== 11. PUSTY BANK NIE ZACZYNA SERII ===")
czysto()
sprawdz("brak materialu = brak propozycji", seria.propozycja([]) is None)
sprawdz("i brak stanu", not seria.PLIK.exists())

print()
print("=== 12. TO SAMO PRZEZ `stages`, NIE TYLKO W `seria` ===")
# Nie wystarczy, ze modul dziala — sprawdzam, ze `stages.note` NAPRAWDE
# wklada blok serii do promptu i NAPRAWDE go pomija bez serii. To jest ta
# roznica, ktora piec razy dzis wyszla na atrapach: test funkcji zamiast testu
# tego, co jej podaje kod.
import stages   # noqa: E402

_zapisane = {}


def _atrapa_prompt(nazwa, **kw):
    _zapisane["nazwa"] = nazwa
    return "PROMPT-BAZOWY"


stages._prompt = _atrapa_prompt
stages.teksty_ostatnich_notek = lambda *a, **k: []
stages.ostatnie_otwarcia = lambda *a, **k: []
stages.zdania_z_tikiem = lambda *a, **k: []


class _Stop(Exception):
    pass


def _lap_prompt(*a, **k):
    # Przerywamy zaraz po zlozeniu promptu — nie chcemy platnego wywolania.
    _zapisane["prompt"] = a[2] if len(a) > 2 else k.get("prompt")
    raise _Stop()


stages.llm.call = _lap_prompt

_kontekst = {"temat": "Prad i data centre",
             "etykieta": "Where the electricity goes",
             "czesc": 2, "ile_czesci": 4, "ostatnia": False,
             "poprzednie_otwarcia": ["Data centres already use a fifth"],
             "poprzednie_fakty": ["Ireland metered electricity"]}
for opis, kontekst, ma_byc in (("z seria", _kontekst, True),
                               ("bez serii", None, False)):
    _zapisane.clear()
    try:
        stages.note(None, 1, "CIEKAWOSTKA", {"fact": "x"}, seria=kontekst)
    except _Stop:
        pass
    except Exception as exc:            # noqa: BLE001
        print("      (note() przerwane inaczej: %r)" % exc)
    p = _zapisane.get("prompt") or ""
    sprawdz("%-10s blok serii %s w prompcie"
            % (opis, "jest" if ma_byc else "NIE jest"),
            ("part of a series" in p) is ma_byc,
            "dlugosc promptu %d" % len(p))
    if ma_byc:
        sprawdz("           znacznik po ANGIELSKU, z numerem 2/4",
                "Where the electricity goes — 2/4" in p,
                p[-260:] if p else "")
        sprawdz("           polski klucz tematu NIE trafia do promptu",
                "Prad i data centre" not in p and "Prąd" not in p)
        sprawdz("           poprzednie otwarcie jest w prompcie",
                "Data centres already use a fifth" in p)

print()
print("=== 13. CALY `notki_dnia`, NIE SAM MODUL ===")
# TO JEST TA ROZNICA, ktora dzis piec razy wyszla na atrapach: test funkcji
# sprawdza funkcje, a nie to, co jej podaje kod. Moja wlasna poprawka Q2
# przeszla test i wywalilaby produkcje, bo test podawal slowniki tam, gdzie
# `run.py` podaje napis. Wiec tutaj odpalam PRAWDZIWY `notki_dnia`.
czysto()
_stan_przed = seria.PLIK.exists()

_oryg = (stages.znajdz_ciekawostki, stages.note, stages.artykul_do_promocji,
         stages.pamiec_wystawionych, stages._prompt)
try:
    stages.artykul_do_promocji = lambda: None
    stages.pamiec_wystawionych = lambda: []
    stages.znajdz_ciekawostki = lambda conn, run_id, ile=8: []
    stages.opublikowane_teksty = lambda *a, **k: []
    stages.teksty_ostatnich_notek = lambda *a, **k: []
    # `**k` — atrapa ma przyjmowac to, co przyjmuje oryginal. Atrapa wezsza od
    # kodu udaje usterke kodu; ten wzorzec powtorzyl sie dzis PIEC RAZY.
    stages.note = lambda conn, run_id, typ, material, link=None,         note_form="PROSTA", **k: {"typ": typ, "material": material,
                                  "seria_w_prompcie": bool(k.get("seria")),
                                  "candidates": []}
    _zapas = [dict(f) for f in PRAD] + [dict(f) for f in SMIECI]
    _notki = stages.notki_dnia(None, 0, ciekawostki=_zapas, ile=3)

    sprawdz("przebieg wydal trzy notki", len(_notki) == 3, len(_notki))
    _z_seria = [n for n in _notki if n.get("seria_czesc")]
    sprawdz("DOKLADNIE JEDNA jest czescia serii (nie zero, nie trzy)",
            len(_z_seria) == 1, [n.get("seria_czesc") for n in _notki])
    sprawdz("i jest to czesc 1 wlasciwego tematu",
            _z_seria and _z_seria[0].get("seria_czesc") == 1
            and _z_seria[0].get("seria_temat") == "Prad i data centre",
            _z_seria[0] if _z_seria else None)
    sprawdz("czesc serii stoi na NAJLEPIEJ dopasowanym fakcie",
            _z_seria and "electricity grid"
            in str((_z_seria[0].get("material") or {}).get("fact") or ""),
            str((_z_seria[0].get("material") or {}).get("fact"))[:90]
            if _z_seria else "")
    # KONTEKST NIE WYCIEKA. Gdyby zostawal miedzy obiegami petli, pozostale
    # notki wyszlyby z zapowiedzia ciagu dalszego, ktorego nie ma.
    sprawdz("pozostale notki NIE dostaly kontekstu serii",
            sum(1 for n in _notki if n.get("seria_w_prompcie")) == 1,
            [n.get("seria_w_prompcie") for n in _notki])
    sprawdz("i nie maja pol serii",
            all(not n.get("seria_temat") for n in _notki
                if not n.get("seria_czesc")))
    # I NAJWAZNIEJSZE: pisanie niczego nie zapisalo.
    sprawdz("`notki_dnia` NIE zapisal stanu serii — zapisze dopiero `run.py`"
            " po potwierdzonej publikacji",
            not seria.PLIK.exists() and not _stan_przed,
            "plik istnieje: %s" % seria.PLIK.exists())
    sprawdz("wiec zadna seria nie jest aktywna po samym pisaniu",
            seria.aktywna() is None, seria.aktywna())

    # KONTRDOWOD: bank bez materialu na zaden temat NIE zaklada serii.
    _tylko_smieci = [dict(f) for f in SMIECI]
    _notki2 = stages.notki_dnia(None, 0, ciekawostki=_tylko_smieci, ile=3)
    sprawdz("KONTRDOWOD: ze smieciowego banku ZADNA notka nie jest czescia serii",
            not any(n.get("seria_czesc") for n in _notki2),
            [n.get("seria_czesc") for n in _notki2])
finally:
    (stages.znajdz_ciekawostki, stages.note, stages.artykul_do_promocji,
     stages.pamiec_wystawionych, stages._prompt) = _oryg

print()
print("=== 14. DWIE WADY Z AUDYTU 6.09 — DOWOD, ZE NAPRAWIONE ===")
czysto()

# --- B4: doba UTC sama nie wystarcza -----------------------------------------
# Zegar produkcji: 11:20, 17:00, 19:20, 21:30, 23:40 UTC. OSTATNI PRZEBIEG
# PRZECHODZI PRZEZ POLNOC, wiec czesc o 23:51 (doba D) i czesc o 00:20
# (doba D+1) to 29 MINUT ODSTEPU u czytelnika — a obie sa „jedna na dobe"
# wedlug kalendarza. Dlatego druga bramka liczy GODZINY, nie kalendarz.
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402

seria.zapisz_czesc("Prad i data centre", 1, "111",
                   otwarcie="o", fakt=PRAD[0]["fact"])
_s = seria.stan()
_w = _s["aktywna"]["wydane"][0]
# Udajemy DOKLADNIE ten przypadek: czesc poszla 29 minut temu, ale wczoraj
# wedlug kalendarza UTC.
_w["doba"] = "2000-01-01"
_w["kiedy"] = (_dt.now(_tz.utc) - _td(minutes=29)).isoformat()
seria._zapisz(_s)
sprawdz("KONTRDOWOD: sam kalendarz przepuscilby czesc 2 po 29 minutach",
        _w["doba"] != seria._dzis())
sprawdz("bramka odstepu ZATRZYMUJE ja", seria.czesc_na_dzis() is None,
        seria.czesc_na_dzis())
# 17 godzin to nadal za malo, 19 juz wystarczy — prog stoi na 18.
for ile_h, ma_przejsc in ((17, False), (19, True)):
    _s = seria.stan()
    _s["aktywna"]["wydane"][0]["kiedy"] = (
        _dt.now(_tz.utc) - _td(hours=ile_h)).isoformat()
    seria._zapisz(_s)
    sprawdz("po %d h czesc 2 %s" % (ile_h, "przechodzi" if ma_przejsc else "czeka"),
            (seria.czesc_na_dzis() == 2) is ma_przejsc, seria.czesc_na_dzis())
# Wpis bez czytelnego czasu NIE ma prawa zatrzymac serii na zawsze.
_s = seria.stan()
_s["aktywna"]["wydane"][0]["kiedy"] = "to nie jest data"
_s["aktywna"]["wydane"][0]["doba"] = "2000-01-01"
seria._zapisz(_s)
sprawdz("zepsuty czas nie blokuje serii na zawsze",
        seria.czesc_na_dzis() == 2, seria.czesc_na_dzis())

# --- B5: czesc serii przechodzi przez TE SAMA straz, co zwykla notka ---------
# Nie sprawdzam, czy `seria` ma wlasna straz — sprawdzam, ze NIE MA i ze
# odsiew robi `wybierz_material`. Dwie kopie jednej reguly rozjezdzaja sie
# przy pierwszej poprawce.
print()
_zr = pathlib.Path("agent-v2/seria.py").read_text(encoding="utf-8")
sprawdz("`seria.py` NIE ma wlasnej kopii strazy roznorodnosci",
        "wspolna_nazwa" not in _zr and "pamiec_wystawionych" not in _zr)
_zs = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
_i_prop = _zs.index("seria.propozycja(")
_ogon = _zs[_i_prop:_i_prop + 1400]
sprawdz("`stages` puszcza kandydatow serii przez `wybierz_material`",
        "wybierz_material(" in _ogon)
sprawdz("i podaje jej pamiec wystawionych oraz teksty notek",
        "wczesniejsze" in _ogon and "teksty_notek" in _ogon)

# ZACHOWANIEM, NIE CZYTANIEM KODU: material zderzony z wczorajsza notka
# NIE moze wyjsc jako czesc serii.
czysto()
_oryg2 = (stages.znajdz_ciekawostki, stages.note, stages.artykul_do_promocji,
          stages.pamiec_wystawionych, stages.teksty_ostatnich_notek,
          stages.opublikowane_teksty)
try:
    stages.artykul_do_promocji = lambda: None
    stages.znajdz_ciekawostki = lambda conn, run_id, ile=8: []
    stages.note = lambda conn, run_id, typ, material, link=None,         note_form="PROSTA", **k: {"typ": typ, "material": material,
                                  "candidates": []}
    stages.opublikowane_teksty = lambda *a, **k: []
    # Pamiec udaje, ze KAZDY fakt serii juz wyszedl w poprzednich dniach.
    stages.pamiec_wystawionych = lambda: [
        frozenset(stages._slowa("%s %s" % (f.get("domain") or "",
                                           f.get("fact") or "")))
        for f in PRAD]
    stages.teksty_ostatnich_notek = lambda *a, **k: []
    _n = stages.notki_dnia(None, 0, ciekawostki=[dict(f) for f in PRAD], ile=2)
    sprawdz("material zderzony z wczesniejsza notka NIE wychodzi jako czesc serii",
            not any(x.get("seria_czesc") for x in _n),
            [x.get("seria_czesc") for x in _n])
finally:
    (stages.znajdz_ciekawostki, stages.note, stages.artykul_do_promocji,
     stages.pamiec_wystawionych, stages.teksty_ostatnich_notek,
     stages.opublikowane_teksty) = _oryg2

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
