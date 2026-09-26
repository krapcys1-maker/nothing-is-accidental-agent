# -*- coding: utf-8 -*-
"""Silnik tematow (E6): styk ze zrodla, spizarnia z kwota, kwota notek, miara.

PO CO. 26 wrzesnia 2026 zmierzylismy z serwera, co naprawde wybiera temat:
spizarnia (`tresc_zrodel`) — osiem tekstow, przy ktorych skaut nie szuka
w sieci. Siedem z osmiu bylo branzowych, a polowa wpisow, z ktorych wybierala,
to YouTube, ktorego nie czyta. Plan: `agent-v2/docs/WYBOR_TEMATOW_2026-09-26.md`.

Test pilnuje czterech ogniw, kazde z kontrdowodem:
  1. styk niesie ZRODLO, a kod przepisuje go na fakt — model go nie nadaje;
  2. spizarnia: najwyzej 2 teksty branzowe na 8, gdy o ludziach jest material,
     a branza dopelnia tylko wtedy, gdy o ludziach go brakuje;
  3. kwota: co najmniej jedna z trzech notek dnia spoza branzy;
  4. miara: odwiedziny profilu i zapisy na 100 wyswietlen po 72 h, po stykach,
     bez polubien i bez restackow.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

# ODCIECIE OD PRODUKCJI — dziennik, statystyki i bank ida do katalogu testu.
# Pilnuje tego `test_testy_nie_czytaja_produkcji.py`.
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import karta_wynikow           # noqa: E402
import korpus_kanalow as kk    # noqa: E402
import statystyki              # noqa: E402
import stages                  # noqa: E402
import tresc_zrodel as tz      # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


TERAZ = datetime.now(timezone.utc)
DZIS = TERAZ.strftime("%Y-%m-%d")
JUTRO = (TERAZ + timedelta(days=1)).strftime("%Y-%m-%d")


def _dziennik(wpisy):
    (config.DATA_DIR / "dziennik.jsonl").write_text(
        "".join(json.dumps(w) + "\n" for w in wpisy), encoding="utf-8")


print("=== 1. STYK NIESIE ZRODLO, NIE MODEL ===")
sprawdz("Pew to codziennosc", kk.styk_wpisu("Pew") == "codziennosc")
sprawdz("EdSurge to szkola", kk.styk_wpisu("EdSurge") == "szkola")
sprawdz("Wpadki AI (od dawna w korpusie) to szkody",
        kk.styk_wpisu("Wpadki AI") == "szkody")
sprawdz("blog laboratorium to branza", kk.styk_wpisu("OpenAI") == "branza")
sprawdz("nieznane zrodlo to branza, nie zgadywanie",
        kk.styk_wpisu("Ktokolwiek") == "branza")
sprawdz("arXiv: tytul o uczniach daje szkole",
        kk.styk_wpisu("arXiv cs.CY", "How students use chatbots for homework")
        == "szkola")
sprawdz("arXiv: tytul bez slow z mapy zostaje przy ludziach",
        kk.styk_wpisu("arXiv cs.CY", "A taxonomy of audit practices") == "ludzie")
sprawdz("Rest of World: wyscig z Chinami to branza, nie praca",
        kk.styk_wpisu("Rest of World", "America is in the wrong AI race with China")
        == "branza")
sprawdz("Rest of World: robotnicy danych to praca",
        kk.styk_wpisu("Rest of World", "Gig workers in Nairobi label data for AI")
        == "praca")
_wszystkie = set(kk.STYK_ZRODLA.values()) | set(kk.STYK_Z_TYTULU.values()) \
    | {s for s, _ in kk.MAPA_STYKU}
sprawdz("kazdy styk z tabel jest na liscie `config.STYKI`",
        _wszystkie <= set(config.STYKI), sorted(_wszystkie - set(config.STYKI)))
_bez_reguly = [n for n in kk.ZRODLA_LUDZIE
               if n not in kk.STYK_ZRODLA and n not in kk.STYK_Z_TYTULU]
sprawdz("zadne zrodlo o ludziach nie jest po cichu branza", not _bez_reguly,
        _bez_reguly)

_e = ET.fromstring("<item><title>How adults in 25 countries view AI chatbots"
                   "</title><link>https://www.pewresearch.org/x</link>"
                   "<pubDate>%s</pubDate></item>"
                   % TERAZ.strftime("%a, %d %b %Y %H:%M:%S +0000"))
_k = kk.przetworz([("Pew", _e)])
sprawdz("`przetworz` dopisuje styk do wpisu korpusu",
        _k and _k[0].get("styk") == "codziennosc", _k)

print()
print("=== 1b. FILTR O AI DLA FEEDOW OGOLNYCH ===")


def _wpis(tytul, opis=""):
    return ET.fromstring("<item><title>%s</title><description>%s</description>"
                         "</item>" % (tytul, opis))


sprawdz("pytanie Pew o regulacje AI przechodzi",
        kk.o_ai(_wpis("Do people trust China, the U.S. or the EU to regulate AI?")))
sprawdz("wielka litera nie gubi frazy",
        kk.o_ai(_wpis("Machine Learning in Rural Hospitals")))
sprawdz("A.I. z kropkami przechodzi (dawny wzorzec go gubil)",
        kk.o_ai(_wpis("An A.I. tried to breach four targets")))
sprawdz("KONTRDOWOD: religia bez AI odpada",
        not kk.o_ai(_wpis("Religion in public life, 2026 survey")))
sprawdz("KONTRDOWOD: „Aid” to nie AI", not kk.o_ai(_wpis("Aid for farmers")))
sprawdz("CourtListener bez filtra (tytul orzeczenia to nazwiska)",
        "CourtListener" not in kk.FILTR_O_AI and "Pew" in kk.FILTR_O_AI)

print()
print("=== 2. SPIZARNIA: NAJWYZEJ DWA TEKSTY BRANZOWE ===")


class _Odp:
    def __init__(self, kod, tekst):
        self.status_code = kod
        self.text = tekst


WOLANE: list = []


class _Klient:
    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        WOLANE.append(url)
        if "pada" in url:
            raise RuntimeError("padlo")
        return _Odp(200, "<p>%s</p>" % " ".join(["slowo"] * 200))


def _w(kanal, nr, dni_temu):
    return {"kanal": kanal, "temat": "%s temat %d" % (kanal, nr),
            "url": "https://%s.example/%d" % (kanal.lower().replace(" ", ""), nr),
            "data": (TERAZ - timedelta(days=dni_temu)).strftime("%Y-%m-%d"),
            "styk": kk.styk_wpisu(kanal)}


# KORPUS JAK NA PRODUKCJI: najnowsze sa blogi branzowe, bo pisza najczesciej.
BRANZA = [_w(k, n, 0) for k in ("Latent Space", "DeepMind", "HuggingFace",
                                 "Epoch AI", "PyTorch") for n in (1, 2)]
LUDZIE = [_w("Pew", 1, 2), _w("Pew", 2, 2), _w("EdSurge", 1, 3), _w("The 74", 1, 3),
          _w("KFF Health", 1, 4), _w("EFF", 1, 4), _w("CourtListener", 1, 5)]
KORPUS = BRANZA + LUDZIE
sprawdz("KONTROLA: pierwsze osiem korpusu to sama branza (stara spizarnia)",
        all(w["styk"] == "branza" for w in KORPUS[:8]))

import httpx  # noqa: E402

_prawdziwy = httpx.Client
_sen = tz.time.sleep
httpx.Client = _Klient
tz.time.sleep = lambda s: None
try:
    WOLANE.clear()
    sp = tz.tresci_zrodel(KORPUS)
    _br = [z for z in sp if z["styk"] == "branza"]
    _lu = [z for z in sp if z["styk"] != "branza"]
    sprawdz("osiem tekstow", len(sp) == 8, len(sp))
    sprawdz("branzowe najwyzej dwa", len(_br) == 2, [z["kanal"] for z in _br])
    sprawdz("o ludziach szesc — co najmniej MIN_LUDZIE", len(_lu) == 6,
            [z["kanal"] for z in _lu])
    sprawdz("z jednego zrodla o ludziach po jednym tekscie (Pew raz)",
            sum(1 for z in _lu if z["kanal"] == "Pew") == 1)
    sprawdz("branza z dwoch ROZNYCH zrodel",
            len({z["kanal"] for z in _br}) == 2, [z["kanal"] for z in _br])
    sprawdz("tekst niesie styk dalej",
            {z["styk"] for z in _lu} == {"codziennosc", "szkola", "zdrowie", "prawo"},
            sorted({z["styk"] for z in _lu}))

    # MALO MATERIALU O LUDZIACH: branza dopelnia, zeby spizarnia nie byla
    # chuda — chuda spizarnia to platne szukanie.
    sp2 = tz.tresci_zrodel(BRANZA + LUDZIE[:2])
    sprawdz("przy dwoch wpisach o ludziach (jedno zrodlo) spizarnia nadal pelna",
            len(sp2) == 8, len(sp2))
    sprawdz("  i bierze z Pew oba teksty, zanim dopelni branza",
            sum(1 for z in sp2 if z["kanal"] == "Pew") == 2)

    # ADRES, KTORY PADL, NIE JEST PROBOWANY DRUGI RAZ W NASTEPNYM ETAPIE.
    WOLANE.clear()
    tz.tresci_zrodel([dict(_w("Pew", 9, 1), url="https://pew.example/pada")]
                     + BRANZA[:1])
    sprawdz("padniety adres wolany raz",
            WOLANE.count("https://pew.example/pada") == 1, WOLANE)

    # STYKI, KTORYCH BANK NIE WIDZIAL OD TRZECH DNI, IDA PIERWSZE.
    _kol = tz.kolejnosc_ludzi(LUDZIE, frozenset({"szkola", "codziennosc"}))
    sprawdz("brakujace w banku styki na poczatku kolejki",
            [w["styk"] for w in _kol[:2]] == ["zdrowie", "prawo"],
            [w["styk"] for w in _kol])
    sprawdz("po jednym z kazdego styku, zanim drugi raz ten sam",
            [w["kanal"] for w in _kol].index("The 74")
            > [w["kanal"] for w in _kol].index("Pew"),
            [w["kanal"] for w in _kol])

    # BLOK DO PROMPTU I LOG SKLADU.
    tz.wyczysc_zapas()
    _log = io.StringIO()
    with contextlib.redirect_stdout(_log):
        blok = tz.blok_do_promptu(KORPUS, styki_w_banku=set())
    sprawdz("blok niesie styk kazdego tekstu, po angielsku jak prompt",
            "Touchpoint: school" in blok and "Touchpoint: AI industry" in blok
            and "Touchpoint: daily life" in blok, blok[:300])
    sprawdz("kazdy styk ma angielska nazwe dla modelu",
            set(config.STYKI) <= set(tz.STYK_DLA_MODELU),
            sorted(set(config.STYKI) - set(tz.STYK_DLA_MODELU)))
    sprawdz("log wypisuje sklad spizarni",
            "[spizarnia] 8 tekstow z 8 zrodel" in _log.getvalue(), _log.getvalue())
    sprawdz("`ostatnie_tresci` oddaje teksty ze stykiem",
            len(tz.ostatnie_tresci()) == 8
            and all("styk" in z for z in tz.ostatnie_tresci()))
    tz.wyczysc_zapas()
    _log = io.StringIO()
    with contextlib.redirect_stdout(_log):
        tz.blok_do_promptu(BRANZA + LUDZIE[:1])
    sprawdz("KONTRDOWOD: bez materialu o ludziach log mowi to glosno",
            "O LUDZIACH TYLKO 1" in _log.getvalue(), _log.getvalue())
finally:
    httpx.Client = _prawdziwy
    tz.time.sleep = _sen
    tz.wyczysc_zapas()

print()
print("=== 2b. LISTA KANALOW DLA SKAUTA ZAWIERA ZRODLA O LUDZIACH ===")
# Prompt skauta kaze wiazac trzy czwarte materialu z lista kanalow. Gdyby byly
# na niej tylko najnowsze (branza), tekst o ludziach ze spizarni wygladalby na
# material „spoza kanalow".
_stary_korpus = stages.korpus_kanalow.korpus_kanalow
stages.korpus_kanalow.korpus_kanalow = lambda ile=30, **kw: list(KORPUS)[:ile]
try:
    _lista = stages.zaczyn_z_kanalow(4)
finally:
    stages.korpus_kanalow.korpus_kanalow = _stary_korpus
sprawdz("KONTROLA: cztery najnowsze to branza",
        all(w["styk"] == "branza" for w in KORPUS[:4]))
sprawdz("a na liscie sa tez zrodla o ludziach", "EdSurge" in _lista
        and "Pew" in _lista, _lista)
sprawdz("  w liczbie najwyzej polowy listy",
        sum(1 for l in _lista.splitlines() if "Pew" in l or "EdSurge" in l
            or "The 74" in l or "KFF" in l or "EFF" in l or "CourtListener" in l)
        <= 2, _lista)

print()
print("=== 3. STYK FAKTU PRZEPISANY ZE ZRODLA ===")
TRESCI = [{"url": "https://www.edsurge.com/news/ai-tutors/", "styk": "szkola"},
          {"url": "https://kffhealthnews.org/news/a", "styk": "zdrowie"},
          {"url": "https://arxiv.org/abs/1", "styk": "szkola"},
          {"url": "https://arxiv.org/abs/2", "styk": "ludzie"}]
sprawdz("po adresie (ukosnik na koncu nie przeszkadza)",
        stages.styk_ze_zrodla({"url": "https://www.edsurge.com/news/ai-tutors"},
                              TRESCI) == ("szkola", "adres"))
sprawdz("po hoscie tekstu spizarni",
        stages.styk_ze_zrodla({"url": "https://kffhealthnews.org/inne"}, TRESCI)
        == ("zdrowie", "host"))
sprawdz("host z dwoma stykami nie rozstrzyga — idzie rejestr (arXiv to ludzie)",
        stages.styk_ze_zrodla({"url": "https://arxiv.org/abs/3"}, TRESCI)
        == ("ludzie", "rejestr"),
        stages.styk_ze_zrodla({"url": "https://arxiv.org/abs/3"}, TRESCI))
sprawdz("spoza spizarni: rejestr zrodel po hoscie feedu",
        stages.styk_ze_zrodla({"url": "https://www.pewresearch.org/short-reads/x"},
                              []) == ("codziennosc", "rejestr"))
sprawdz("KONTRDOWOD: nieznany host to branza, nie zgadywanie",
        stages.styk_ze_zrodla({"url": "https://nieznany.example/x"}, TRESCI)
        == ("branza", "brak"))
sprawdz("fakt bez adresu to branza",
        stages.styk_ze_zrodla({}, TRESCI) == ("branza", "brak"))
sprawdz("model nie zwraca styku (nie ma go w ksztalcie odpowiedzi)",
        "styk" not in stages._POLA_Z_KSZTALTU, stages._POLA_Z_KSZTALTU)
sprawdz("styk to ksiegowosc, nie dowod dla pisarza",
        "styk" in stages.KSIEGOWOSC_BANKU
        and "styk" not in stages.DOWOD_DLA_PISARZA)

print()
print("=== 4. STYK PRZEZYWA ZAPIS DO BANKU ===")
TEKSTY = {
    1: ("The provider chose to bill prompt caching as a separate line rather "
        "than folding it into the token rate, so the same request costs "
        "differently depending on what came before it."),
    2: ("A hardware vendor publishes throughput per watt measured on one "
        "workload, and the figure quoted everywhere omits which workload it "
        "was, so two chips get compared on numbers that were never comparable."),
    3: ("Open weights are released under a licence whose user threshold turns "
        "the permission off above a certain size of company, which almost "
        "nobody reads before building on it."),
    4: ("A benchmark suite keeps part of its questions unpublished, and the "
        "gap between the public score and the held-out score is where "
        "contamination shows up."),
}


def fakt(nr, url, **reszta):
    f = {"fact": TEKSTY[nr],
         "wrong_belief": "People assume nobody chose this.",
         "actually": "Somebody chose it, and the document says who.",
         "decision": ("A decision: somebody signed off on that arrangement and "
                      "the record names when."),
         "consequence": ("Your bill for the same request moved, and you were not "
                         "told which half moved."),
         "url": url, "source_date": DZIS, "control_date": DZIS,
         "control_url": url, "control_verdict": "CONFIRMS",
         "control_fact": "checked today, unchanged",
         "domain": "how models are served and priced"}
    f.update(reszta)
    return f


_katalog = pathlib.Path(tempfile.mkdtemp())
_stary_indeks = stages.INDEKS_KANDYDATOW
stages.INDEKS_KANDYDATOW = _katalog / "indeks.json"
stages.INDEKS_KANDYDATOW.write_text("[]", encoding="utf-8")
try:
    for nr in (1, 2):
        ok, powod = stages.bramka_kandydata(fakt(nr, "https://x.example/%d" % nr))
        sprawdz("KONTROLA: atrapa %d przechodzi bramke" % nr, ok, powod)
    stages.dopisz_kandydatow([
        fakt(1, "https://www.edsurge.com/news/a", styk="szkola", styk_skad="adres"),
        fakt(2, "https://www.pewresearch.org/b")])
    bank = json.loads(stages.INDEKS_KANDYDATOW.read_text(encoding="utf-8"))
    _po = {b["fact"][:20]: b for b in bank}
    sprawdz("styk ze skauta zapisany", _po[TEKSTY[1][:20]].get("styk") == "szkola",
            _po[TEKSTY[1][:20]])
    sprawdz("kandydat z innej drogi dostaje styk z rejestru",
            (_po[TEKSTY[2][:20]].get("styk"), _po[TEKSTY[2][:20]].get("styk_skad"))
            == ("codziennosc", "rejestr"), _po[TEKSTY[2][:20]])
    sprawdz("pisarz nie dostaje styku",
            "styk" not in stages._fakt_do_pisarza(_po[TEKSTY[1][:20]]))

    print()
    print("=== 5. KWOTA: CO NAJMNIEJ JEDNA Z TRZECH NOTEK SPOZA BRANZY ===")

    def _wpis_banku(nr, styk, z_kanalu, ranga):
        w = fakt(nr, "https://h%d.example/x" % nr)
        w.update({"styk": styk, "z_kanalu": z_kanalu, "ranga": ranga,
                  "status": "nowy", "kiedy": DZIS + "T08:00:00+00:00",
                  "wazny_do": JUTRO + "T23:00:00+00:00"})
        return w

    def _wez(bank, dziennik=()):
        stages._zapisz_indeks([dict(b) for b in bank])
        _dziennik(list(dziennik))
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            wziete = stages.wez_kandydatow(1)
        return [w["fact"] for w in wziete], log.getvalue()

    X = _wpis_banku(1, "branza", True, 0)
    Y = _wpis_banku(2, "szkola", True, 9)
    Y2 = _wpis_banku(3, "zdrowie", False, 0)
    sprawdz("KONTROLA: oba fakty przechodza swiezosc",
            stages.swiezosc_faktu(X)[0] and stages.swiezosc_faktu(Y)[0])

    wziete, log = _wez([X, Y])
    sprawdz("dzis nic spoza branzy: pierwszy idzie fakt ze stykiem, mimo rangi 9",
            wziete == [Y["fact"]], (wziete, log))
    sprawdz("  i log to mowi", "[kwota]" in log, log)

    _dzis_poza = [{"rodzaj": "notka", "udane": True, "id": "1",
                   "kiedy": TERAZ.isoformat(timespec="seconds"), "styk": "prawo"}]
    wziete, log = _wez([X, Y], _dzis_poza)
    sprawdz("kwota spelniona dzis: wraca zwykly porzadek (ranga 0 pierwsza)",
            wziete == [X["fact"]], (wziete, log))

    _wczoraj = [dict(_dzis_poza[0],
                     kiedy=(TERAZ - timedelta(days=1)).isoformat(timespec="seconds"))]
    wziete, _ = _wez([X, Y], _wczoraj)
    sprawdz("notka spoza branzy z WCZORAJ kwoty na dzis nie spelnia",
            wziete == [Y["fact"]], wziete)

    wziete, _ = _wez([X, Y2, Y])
    sprawdz("z dwoch spoza branzy wygrywa zakotwiczony w kanalach",
            wziete == [Y["fact"]], wziete)

    wziete, log = _wez([X])
    sprawdz("bank bez faktu spoza branzy: idzie branza i log o tym mowi",
            wziete == [X["fact"]] and "nie ma" in log, (wziete, log))

    config.KWOTA_SPOZA_BRANZY = False
    try:
        wziete, log = _wez([X, Y])
        sprawdz("KONTRDOWOD: bez kwoty wygrywa ranga — kwota robi roznice",
                wziete == [X["fact"]] and "[kwota]" not in log, (wziete, log))
    finally:
        config.KWOTA_SPOZA_BRANZY = True

    stages._zapisz_indeks([dict(Y, kiedy=DZIS), dict(X, kiedy="2020-01-01")])
    sprawdz("styki w banku z ostatnich trzech dni",
            stages.styki_w_banku(3) == {"szkola"}, stages.styki_w_banku(3))

    print()
    print("=== 6. SEDZIA BANKU WIDZI STYK KANDYDATA ===")
    _prompty = []
    _stary_call = stages.llm.call

    def _udawany(purpose, system, user, **kw):
        _prompty.append(user)
        return '{"kolejnosc": [0, 1], "oceny": []}'

    stages.llm.call = _udawany
    try:
        stages._zapisz_indeks([dict(X, ranga=None), dict(Y, ranga=None)])
        with contextlib.redirect_stdout(io.StringIO()):
            stages.posortuj_bank(None, None)
    finally:
        stages.llm.call = _stary_call
    sprawdz("prompt sedziego niesie styk kazdego kandydata",
            _prompty and "styk: szkola" in _prompty[0]
            and "styk: branza" in _prompty[0], _prompty[:1])
finally:
    stages.INDEKS_KANDYDATOW = _stary_indeks

print()
print("=== 7. MIARA: ODWIEDZINY I ZAPISY NA 100 WYSWIETLEN, PO STYKACH ===")
sprawdz("wynik bez wyswietlen to brak wyniku, nie zero",
        statystyki.wynik_odbioru(0, 1, 0) is None)
sprawdz("zapis wazy piec odwiedzin",
        statystyki.wynik_odbioru(150, 5, 1) == 6.67,
        statystyki.wynik_odbioru(150, 5, 1))
sprawdz("przypisane zapisy: maksimum po odczytach, nie suma",
        statystyki.zapisy_przypisane([
            {"podsumowanie": {"zapisy_per_notka": {"n2": 1}}},
            {"podsumowanie": {"zapisy_per_notka": {"n2": 1}}}]) == {"n2": 1})

WYST = TERAZ - timedelta(days=5)


def _pomiary(nid, wysw, odw, polub=0, wyst=WYST, godziny=(70, 80)):
    wyniki = []
    for godz in godziny:
        chwila = (wyst + timedelta(hours=godz)).isoformat(timespec="seconds")
        wyniki.append({"rodzaj": "notka", "id": nid, "kiedy": chwila,
                       "zmierzone": chwila,
                       "wystawione": wyst.isoformat(timespec="seconds"),
                       "tekst": "notka %s" % nid, "wyswietlenia": wysw,
                       "odwiedziny_profilu": odw, "polubienia": polub,
                       "odpowiedzi": 0})
    return wyniki


STAT = (_pomiary("n1", 100, 4) + _pomiary("n2", 50, 1)
        + _pomiary("n3", 200, 2) + _pomiary("n4", 100, 0, polub=50)
        + _pomiary("r1", 500, 20) + _pomiary("n5", 80, 8)
        # Mloda notka: pomiary tylko z pierwszych godzin, jak na produkcji.
        + _pomiary("n6", 999, 99, wyst=TERAZ - timedelta(hours=10),
                   godziny=(2, 9)))
(config.DATA_DIR / statystyki.NAZWA_PLIKU).write_text(
    "".join(json.dumps(s) + "\n" for s in STAT), encoding="utf-8")
ZRODLA = [{"podsumowanie": {"zapisy_per_notka": {"n2": 1}}},
          {"podsumowanie": {"zapisy_per_notka": {"n2": 1}}}]
(config.DATA_DIR / "zrodla.jsonl").write_text(
    "".join(json.dumps(z) + "\n" for z in ZRODLA), encoding="utf-8")
DZIENNIK = [
    {"rodzaj": "notka", "udane": True, "id": "n1", "styk": "szkola"},
    {"rodzaj": "notka", "udane": True, "id": "n2", "styk": "szkola"},
    {"rodzaj": "notka", "udane": True, "id": "n3", "styk": "branza"},
    {"rodzaj": "notka", "udane": True, "id": "n4", "styk": "branza"},
    {"rodzaj": "notka", "udane": True, "id": "n5"},
    {"rodzaj": "notka", "udane": True, "id": "n6", "styk": "szkola"},
    {"rodzaj": "restack", "udane": True, "id": "r1"},
]
_dziennik(DZIENNIK)
with contextlib.redirect_stdout(io.StringIO()):
    tabela = stages.co_zadzialalo()
_linie = tabela.splitlines()
_szk = next((l for l in _linie if l.strip().startswith("szkola:")), "")
_bra = next((l for l in _linie if l.strip().startswith("branza:")), "")
sprawdz("szkola: dwie dojrzale notki, 150 wysw., 5 odwiedzin, 1 zapis, 6.7",
        "2 notes, 150 views, 5 profile visits, 1 signups, score 6.7" in _szk, _szk)
sprawdz("branza: polubienia nie licza sie wcale (50 polubien, wynik 0.7)",
        "2 notes, 300 views, 2 profile visits, 0 signups, score 0.7" in _bra, _bra)
sprawdz("rodzina z lepszym wynikiem stoi wyzej",
        _szk and _bra and _linie.index(_szk) < _linie.index(_bra))
sprawdz("KONTRDOWOD: restack (500 wysw.) nie wchodzi do miary",
        "500" not in tabela and "520" not in tabela, tabela)
sprawdz("notka sprzed E6 (bez styku) nie jest zgadywana",
        not any("n5" in l for l in _linie) and "8 profile" not in tabela)
sprawdz("notka mlodsza niz 72 h czeka (999 wyswietlen nie ma)",
        "999" not in tabela and "1149" not in tabela, tabela)
_dziennik([])
sprawdz("bez notek ze stykiem tabela mowi to wprost",
        stages.co_zadzialalo() == "(no notes measured by touchpoint yet)")

_do = TERAZ.date() - timedelta(days=1)
_od = _do - timedelta(days=6)
_grupy = karta_wynikow.odbior_po_stykach(STAT, DZIENNIK, ZRODLA, _od, _do)
sprawdz("karta: ta sama miara dla notek spoza branzy",
        _grupy["spoza_branzy"]["n"] == 2 and _grupy["spoza_branzy"]["wynik"] == 6.67,
        _grupy["spoza_branzy"])
sprawdz("karta: branza osobno",
        _grupy["branza"]["n"] == 2 and _grupy["branza"]["wynik"] == 0.67,
        _grupy["branza"])
sprawdz("karta: notki sprzed E6 w osobnej grupie",
        _grupy["bez_styku"]["n"] == 1, _grupy["bez_styku"])

print()
print("=== 8. PROMPTY I DROGA STYKU DO DZIENNIKA ===")


def _jednym(t):
    return " ".join(t.split())


PROMPTY = pathlib.Path("agent-v2/prompts")
notka = _jednym((PROMPTY / "notka.md").read_text(encoding="utf-8"))
for zdanie in (
        "They use AI tools or live with their effects, but have never looked "
        "under this particular part.",
        "Open with the thing itself, in words a reader could repeat. A bare "
        "number, a question or a teaser is not an opening.",
        "If the evidence shows where this lands for a reader (a screen they use, "
        "a bill they pay, their work, school, health or rights), say it plainly "
        "once. Don't invent one when it doesn't."):
    sprawdz("notka.md: %s..." % zdanie[:44], zdanie in notka)
sprawdz("notka.md: czytelnik, ktory „nic nie wie”, zniknal",
        "They know nothing about this" not in notka)
cie = _jednym((PROMPTY / "ciekawostki.md").read_text(encoding="utf-8"))
bank_md = _jednym((PROMPTY / "bank.md").read_text(encoding="utf-8"))
PYTANIA = ("Where does an ordinary reader meet this?",
           "What is new here, in one sentence?",
           "Can it be explained in two sentences without jargon?")
sprawdz("ciekawostki.md: cztery pytania", all(p in cie for p in PYTANIA))
sprawdz("bank.md: cztery pytania", all(p in bank_md for p in PYTANIA))
sprawdz("ciekawostki.md: model nie zwraca styku", '"styk' not in cie)
sprawdz("ciekawostki.md: wyjasnia linie Touchpoint", "Touchpoint" in cie)
for nazwa in ("ciekawostki.md", "bank.md", "notka.md"):
    _surowy = (PROMPTY / nazwa).read_text(encoding="utf-8")
    _pola = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", _surowy))
    try:
        _surowy.format(**{p: "x" for p in _pola})
        _ok = True
    except (KeyError, ValueError, IndexError) as exc:
        _ok = exc
    sprawdz("%s formatuje sie bez bledu" % nazwa, _ok is True, _ok)


def _kod(sciezka):
    return "\n".join(w for w in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not w.lstrip().startswith("#"))


_stages = _kod("agent-v2/stages.py")
sprawdz("notka niesie styk faktu",
        'wynik["styk"] = styk_faktu(fakt)' in _stages)
sprawdz("spizarnia dostaje caly korpus i styki banku",
        "korpus_kanalow.korpus_kanalow(200)" in _stages
        and "styki_w_banku=styki_w_banku()" in _stages)
sprawdz("run.py przekazuje styk do publikacji",
        'styk=n.get("styk")' in _kod("agent-v2/run.py"))
sprawdz("browser.py zapisuje styk w obu wpisach dziennika notki",
        _kod("agent-v2/browser.py").count("styk=styk") == 2)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
