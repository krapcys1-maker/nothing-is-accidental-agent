# -*- coding: utf-8 -*-
"""Straznik powtorek w banku: to samo wydarzenie napisane starannie inaczej.

CO ZMIERZONO. 3 wrzesnia 2026 bank produkcyjny mial 22 wolne fakty. Filtr
slowny (`_o_tym_samym` + `_wspolna_kotwica`) zglaszal ZERO powtorek. Przeczytane
recznie, cztery pary opisywaly to samo:

    DeepSeek Harness      to samo otwarcie zrodel z 13 sierpnia 2026
    Breeze TTS 2          ta sama teza: kod otwarty, wagi niekomercyjne
    H3 Max                ta sama liczba: piec sekund wideo w mniej niz trzy
    Jalapeno              ten sam uklad 700 W

Filtr liczy WSPOLNE SLOWA. Zdanie przepisane leniwie je ma; przepisane
starannie — nie. Dlatego po filtrze slownym idzie drugi przebieg: te same dwa
zdania czyta model, ale pytany jest TYLKO o pozycje dzielace z kandydatem
nazwe albo liczbe.

CO TEN TEST SPRAWDZA, A CZEGO NIE. Nie sprawdza, czy model ma racje — to
zalezy od modelu i nie da sie tego zamrozic w tescie. Sprawdza CALA RESZTE:
ze pary w ogole DOCHODZA do modelu (bez wspolnej kotwicy nikt by nie zapytal),
ze werdykt „powtorka" naprawde zatrzymuje fakt przed bankiem, ze awaria
wywolania przepuszcza fakt zamiast go gubic, i ze za fakt bez wspolnej kotwicy
NIE PLACIMY. Werdykt zywego modelu na tych samych osmiu zdaniach jest
sprawdzany osobno, na serwerze.

ZDANIA SA PRODUKCYJNE, przepisane co do znaku z `indeks_kandydatow.json`
z 3 wrzesnia 2026 — nie streszczone, bo streszczenie zmienia podobienstwo
slow, czyli dokladnie to, co tu mierzymy.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_straznik_powtorek.py
Zaden platny model nie jest wolany — `llm.call` jest podmieniony na atrape.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# OSIEM ZDAN Z PRODUKCJI, cztery pary. Litera A to ta, ktora w banku zostala.
DSH_A = "On August 13, 2026, DeepSeek open-sourced DeepSeek Harness (DSH) v0.1, an agent framework built on an 'everything is a plugin' principle in which the model itself writes, runs and modifies code and can spawn new agents — an open-source system for AI building AI — which drew tens of thousands of GitHub stars within a day."
DSH_B = "DeepSeek Harness (open-sourced 13 Aug 2026 under MIT) is built so that the model, tools, skills, sessions, sandbox, storage, agent loop, scheduler and UI are all replaceable plugins — including the agent loop and the runtime itself — and a 'creation mode' lets the agent inspect and compose plugins at runtime, making the harness's own configuration something the machine can operate on."
BREEZE_A = "The top-ranked open-weights text-to-speech model, Breeze TTS 2, is 'open source' only in its code: the weights, derivative models and self-hosted outputs are under a research-and-non-commercial license."
BREEZE_B = "Breeze TTS 2's code is open under Apache 2.0, but its model weights carry a separate research-and-non-commercial licence — so you can run the whole voice model locally, free and about 3x faster than real time on an H100, but you may not use the weights in a commercial product without written permission."
H3_A = "H3 Max, a post-trained version of MiniMax's open H3 built by the startup fal, generates a 5-second video in under 3 seconds — roughly 35x the throughput of MiniMax's own H3 endpoint and about 15x faster than anything of comparable quality — while ranking #1 in human-preference for overall quality, prompt understanding and aesthetics."
H3_B = "MiniMax's H3 Max, released 1 September 2026, generates a five-second 768p audio-and-video clip in under three seconds — about 35× the throughput of its predecessor H3 — crossing the speed threshold for real-time live video."
CHIP_A = "OpenAI's first custom chip, Jalapeño, unveiled with Broadcom, is an inference-only ASIC — it does not train models — rated at a 700W TDP where Nvidia's GB300 is 1400W, and it was carried from design start to tape-out in 9 months against an industry norm of 18–36 months because the chip design itself was heavily AI-assisted."
CHIP_B = "OpenAI's Jalapeño inference chip, a 700W part (sustained under 550W during testing) with 216 GiB of HBM4, beat NVIDIA's GB200 and GB300 racks in OpenAI's own published benchmark by 1.5–1.9x throughput per kilowatt and 1.7–3.6x lower latency — but it is inference-only and cannot train a model, and it was not tested against NVIDIA's newer Vera Rubin."

PARY = (("DeepSeek Harness", DSH_A, DSH_B),
        ("Breeze TTS 2", BREEZE_A, BREEZE_B),
        ("H3 Max", H3_A, H3_B),
        ("Jalapeno", CHIP_A, CHIP_B))

PODOBIENSTWO = {"min_wspolnych": 4, "prog": 0.35}

katalog = pathlib.Path(tempfile.mkdtemp())
_stary_indeks = stages.INDEKS_KANDYDATOW
_stare_call = stages.llm.call
stages.INDEKS_KANDYDATOW = katalog / "indeks.json"

wolania = []
ODPOWIEDZ = {"co": {"powtorka_nr": 0, "powod": ""}}


def atrapa(purpose, system, user, **kw):
    """Zapisuje, o co pytano, i oddaje werdykt ustawiony przez test."""
    wolania.append({"etap": purpose, "prompt": user})
    if isinstance(ODPOWIEDZ["co"], Exception):
        raise ODPOWIEDZ["co"]
    return json.dumps(ODPOWIEDZ["co"])


stages.llm.call = atrapa


class Polaczenie:
    """`conn` jest tu tylko przepustka do `llm.call`, a ten jest atrapa."""


def wyczysc():
    if stages.INDEKS_KANDYDATOW.exists():
        stages.INDEKS_KANDYDATOW.unlink()
    wolania.clear()


def wsadz(tekst):
    """Fakt gotowy do banku — pola, ktorych zada `bramka_kandydata`."""
    return {"fact": tekst, "wrong_belief": "People think the opposite.",
            "actually": "The record shows otherwise.",
            "url": "https://example.com/a", "source_date": "2026-08-26",
            "domain": "example.com",
            "consequence": "It changes what you should expect next.",
            "decision": "Do not assume the cheaper option is the same thing."}


try:
    print("=== 1. FILTR SLOWNY TYCH CZTERECH PAR NIE WIDZI ===")
    # To jest POWOD istnienia drugiego przebiegu. Gdyby filtr slowny je lapal,
    # placenie za model byloby marnowaniem pieniedzy.
    for nazwa, a, b in PARY:
        slowny = (stages._o_tym_samym(a, b, **PODOBIENSTWO)
                  and stages._wspolna_kotwica(a, b))
        sprawdz("filtr slowny przepuszcza pare %s" % nazwa, not slowny,
                (nazwa, stages._o_tym_samym(a, b, **PODOBIENSTWO)))

    print()
    print("=== 2. ALE KAZDA PARA DZIELI NAZWE ALBO LICZBE ===")
    # Bez tego model nie zostalby o nie zapytany i caly straznik bylby slepy
    # dokladnie tam, gdzie ma widziec.
    for nazwa, a, b in PARY:
        sprawdz("para %s trafia do modelu (dzieli bohatera)" % nazwa,
                stages._dzieli_temat(a, b))
    # DLACZEGO OSOBNE, SZERSZE SITO. Waska kotwica pomija pierwsze slowo zdania
    # (gramatyka, nie imie) i skroty krotsze niz cztery znaki — a zdanie
    # "Breeze TTS 2s code is open..." traci przez to CALEGO bohatera. Ta para
    # jest dowodem, ze bez poszerzenia straznik bylby slepy tam, gdzie ma widziec.
    sprawdz("waska kotwica gubi pare Breeze TTS 2 — i to jest powod szerszej",
            not stages._wspolna_kotwica(BREEZE_A, BREEZE_B)
            and stages._dzieli_temat(BREEZE_A, BREEZE_B))
    # A HOJNOSC MA GRANICE: fakt z innej branzy nie dzieli bohatera z zadnym.
    obcy_temat = ("A Norwegian ferry operator replaced its diesel engines with "
                  "battery packs charged from shore power between crossings.")
    sprawdz("fakt z innej branzy nie dzieli bohatera z zadnym z osmiu",
            not any(stages._dzieli_temat(obcy_temat, t)
                    for _, a, b in PARY for t in (a, b)))

    print()
    print("=== 3. WERDYKT POWTORKI ZATRZYMUJE FAKT PRZED BANKIEM ===")
    for nazwa, a, b in PARY:
        wyczysc()
        ODPOWIEDZ["co"] = {"powtorka_nr": 0, "powod": ""}
        stages.dopisz_kandydatow([wsadz(a)], conn=Polaczenie(), run_id=1)
        ODPOWIEDZ["co"] = {"powtorka_nr": 1, "powod": "to samo wydarzenie"}
        licz = stages.dopisz_kandydatow([wsadz(b)], conn=Polaczenie(), run_id=1)
        bank = [k for k in stages.wczytaj_indeks() if k.get("status") == "nowy"]
        sprawdz("%s: drugie zdanie nie weszlo do banku" % nazwa,
                len(bank) == 1 and licz["powtorka_llm"] == 1, (len(bank), licz))

    print()
    print("=== 4. PYTANIE IDZIE NA WLASCIWY ETAP I NIESIE OBA ZDANIA ===")
    wyczysc()
    ODPOWIEDZ["co"] = {"powtorka_nr": 0, "powod": ""}
    stages.dopisz_kandydatow([wsadz(DSH_A)], conn=Polaczenie(), run_id=1)
    wolania.clear()
    stages.dopisz_kandydatow([wsadz(DSH_B)], conn=Polaczenie(), run_id=1)
    sprawdz("etap to `powtorka`, wiec placi wg wlasnego cennika",
            len(wolania) == 1 and wolania[0]["etap"] == "powtorka",
            [w["etap"] for w in wolania])
    sprawdz("prompt niesie NOWE zdanie", DSH_B[:80] in wolania[0]["prompt"])
    sprawdz("prompt niesie zdanie Z BANKU", DSH_A[:80] in wolania[0]["prompt"])
    sprawdz("etap ma model i sufit tokenow w konfiguracji",
            "powtorka" in config.MODEL_FOR and "powtorka" in config.MAX_TOKENS,
            (config.MODEL_FOR.get("powtorka"), config.MAX_TOKENS.get("powtorka")))

    print()
    print("=== 5. AWARIA WYWOLANIA PRZEPUSZCZA FAKT, NIE GUBI GO ===")
    # Doktryna: lepiej niech wyjdzie cos wadliwego niz nic. Przepuszczona
    # powtorka kosztuje jedna notke; zgubiony material kosztuje cale
    # wyszukiwanie i nie da sie go odzyskac.
    wyczysc()
    ODPOWIEDZ["co"] = {"powtorka_nr": 0, "powod": ""}
    stages.dopisz_kandydatow([wsadz(DSH_A)], conn=Polaczenie(), run_id=1)
    ODPOWIEDZ["co"] = RuntimeError("provider padl")
    licz = stages.dopisz_kandydatow([wsadz(DSH_B)], conn=Polaczenie(), run_id=1)
    bank = [k for k in stages.wczytaj_indeks() if k.get("status") == "nowy"]
    sprawdz("po awarii fakt JEST w banku",
            len(bank) == 2 and licz["przyjete"] == 1, (len(bank), licz))

    print()
    print("=== 6. ZA CO NIE PLACIMY ===")
    # a) fakt bez wspolnej kotwicy z bankiem — nie ma o co pytac
    wyczysc()
    ODPOWIEDZ["co"] = {"powtorka_nr": 0, "powod": ""}
    stages.dopisz_kandydatow([wsadz(DSH_A)], conn=Polaczenie(), run_id=1)
    wolania.clear()
    obcy = ("A Norwegian ferry operator replaced its diesel engines with "
            "battery packs charged from shore power between crossings.")
    stages.dopisz_kandydatow([wsadz(obcy)], conn=Polaczenie(), run_id=1)
    sprawdz("fakt bez wspolnej nazwy i liczby nie kosztuje wywolania",
            len(wolania) == 0, len(wolania))
    # b) powtorka zlapana juz przez filtr slowny — nie placimy drugi raz
    wyczysc()
    stages.dopisz_kandydatow([wsadz(DSH_A)], conn=Polaczenie(), run_id=1)
    wolania.clear()
    stages.dopisz_kandydatow(
        [wsadz(DSH_A + " Additionally, the release notes list the same "
                       "plugin points once more.")],
        conn=Polaczenie(), run_id=1)
    sprawdz("wariant zlapany slowami nie idzie do modelu",
            len(wolania) == 0, len(wolania))
    # c) bez polaczenia (np. wywolanie spoza przebiegu) straznik milczy
    wyczysc()
    stages.dopisz_kandydatow([wsadz(DSH_A)])
    wolania.clear()
    stages.dopisz_kandydatow([wsadz(DSH_B)])
    sprawdz("bez `conn` straznik nie jest wolany i nic nie wybucha",
            len(wolania) == 0 and len(stages.wczytaj_indeks()) == 2,
            (len(wolania), len(stages.wczytaj_indeks())))

finally:
    stages.INDEKS_KANDYDATOW = _stary_indeks
    stages.llm.call = _stare_call

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
