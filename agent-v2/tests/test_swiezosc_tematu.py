# -*- coding: utf-8 -*-
"""Swiezosc tematu (27.09.2026): bank, sedzia, notka, spizarnia, wydarzenia, dziennik.

PO CO. Wlasciciel: „maja byc swieze notki". Zmierzone rano na produkcji:
wolne fakty w banku staly na zrodlach sprzed 2-8 dni (termin liczyl sie od
DOPISANIA, prog wieku zrodla wynosil 30 dni), pierwsze zrodlo o ludziach
w kolejce spizarni mialo wpis sprzed osmiu dni, a wykrywacz wydarzen liczyl
fale z czterech dni — te same fale otwieraly furtke skauta w kazdym przebiegu.

Test pilnuje szesciu ogniw, kazde z kontrdowodem:
  1. bank: zrodlo starsze niz `MAKS_WIEK_TEMATU_DNI` jest po terminie;
  2. sedzia banku nie dostaje (i nie placi za) przeterminowanych;
  3. notka: `wybierz_material` pomija przeterminowany fakt prosto ze skauta;
  4. spizarnia: tylko swieze teksty, starsze wylacznie na ratunek;
  5. wydarzenia: skaut pyta wykrywacz o fale z `WYDARZENIE_SWIEZOSC_DNI`;
  6. dziennik: notka niesie date strony zrodlowej.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

# ODCIECIE OD PRODUKCJI — bank, dziennik i pamieci ida do katalogu testu.
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import korpus_kanalow as kk    # noqa: E402
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
PROG = config.MAKS_WIEK_TEMATU_DNI


def dni_temu(n):
    return (TERAZ - timedelta(days=n)).strftime("%Y-%m-%d")


def fakt(nr, zrodlo_dni, **inne):
    f = {"fact": "A county court in district %d ruled that the school board must"
                 " publish its tutoring contract with the vendor in full." % nr,
         "actually": "The board has to publish the whole contract, including the"
                     " pricing annex it had kept private until the ruling.",
         "decision": "Judge Maria Lopez ordered disclosure under the state public"
                     " records act after a parent filed a request.",
         "consequence": "Parents in the district can read what the vendor is paid.",
         "domain": "schools %d" % nr,
         "url": "https://court%d.example/ruling" % nr,
         "source_date": dni_temu(zrodlo_dni)}
    f.update(inne)
    return f


print("=== 1. BANK: ZRODLO STARSZE NIZ PROG JEST PO TERMINIE ===")
sprawdz("prog tematu: trzy dni", PROG == 3, PROG)
sprawdz("prog tematu nie wiekszy niz prog twierdzen o stanie swiata",
        PROG <= config.MAKS_WIEK_ZRODLA_DNI)
sprawdz("zrodlo sprzed %d dni po terminie" % (PROG + 1),
        stages._po_terminie(fakt(1, PROG + 1)))
sprawdz("zrodlo sprzed %d dni jeszcze nie" % PROG, not stages._po_terminie(fakt(1, PROG)))
sprawdz("dzisiejsze zrodlo nie", not stages._po_terminie(fakt(1, 0)))
sprawdz("KONTRDOWOD: bez daty zrodla i dopisania nie jest po terminie",
        not stages._po_terminie({"fact": "x"}))

_dzis = TERAZ.strftime("%Y-%m-%d %H:%M")
_termin = (TERAZ + timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
bank = [dict(fakt(1, 1), status="nowy", kiedy=_dzis, wazny_do=_termin),
        dict(fakt(2, PROG + 3), status="nowy", kiedy=_dzis, wazny_do=_termin)]
stages.INDEKS_KANDYDATOW.parent.mkdir(parents=True, exist_ok=True)
stages.INDEKS_KANDYDATOW.write_text(json.dumps(bank), encoding="utf-8")
sprawdz("podloga i sufit licza tylko swieze", stages._wolnych_w_banku() == 1,
        stages._wolnych_w_banku())
with contextlib.redirect_stdout(io.StringIO()):
    wziete = stages.wez_kandydatow(5)
sprawdz("wez_kandydatow oddaje tylko swiezy",
        [w["url"] for w in wziete] == ["https://court1.example/ruling"],
        [w.get("url") for w in wziete])
_po = {k["url"]: k for k in stages.wczytaj_indeks()}
_stary = _po["https://court2.example/ruling"]
sprawdz("stary oznaczony jako przeterminowany",
        _stary.get("status") == "przeterminowany", _stary.get("status"))
sprawdz("powod niesie date zrodla", dni_temu(PROG + 3) in str(_stary.get("powod")),
        _stary.get("powod"))

print()
print("=== 2. SEDZIA BANKU NIE PLACI ZA PRZETERMINOWANE ===")
bank = [dict(fakt(1, 0), status="nowy", kiedy=_dzis, wazny_do=_termin),
        dict(fakt(3, 2), status="nowy", kiedy=_dzis, wazny_do=_termin),
        dict(fakt(4, PROG + 2), status="nowy", kiedy=_dzis, wazny_do=_termin)]
stages.INDEKS_KANDYDATOW.write_text(json.dumps(bank), encoding="utf-8")
PROMPTY = []
_prawdziwy_call = stages.llm.call


def _sedzia(purpose, system, user, **kw):
    PROMPTY.append(user)
    return json.dumps({"kolejnosc": [1, 0], "oceny": []})


stages.llm.call = _sedzia
try:
    with contextlib.redirect_stdout(io.StringIO()):
        stages.posortuj_bank(sqlite3.connect(":memory:"), None)
finally:
    stages.llm.call = _prawdziwy_call
sprawdz("sedzia zawolany raz", len(PROMPTY) == 1, len(PROMPTY))
_p = PROMPTY[0] if PROMPTY else ""
sprawdz("swieze w prompcie sedziego", "district 1 " in _p and "district 3 " in _p)
sprawdz("KONTRDOWOD: przeterminowany NIE trafia do sedziego", "district 4 " not in _p)

print()
print("=== 3. NOTKA POMIJA PRZETERMINOWANY FAKT PROSTO ZE SKAUTA ===")
_log = io.StringIO()
with contextlib.redirect_stdout(_log):
    wybrany = stages.wybierz_material([fakt(5, PROG + 4), fakt(6, 1)], [], [])
sprawdz("wybrany swiezy", (wybrany or {}).get("url") == "https://court6.example/ruling",
        (wybrany or {}).get("url"))
sprawdz("log mowi, co pominieto", "[swiezosc] pomijam" in _log.getvalue(), _log.getvalue())
with contextlib.redirect_stdout(io.StringIO()):
    zaden = stages.wybierz_material([fakt(7, PROG + 1)], [], [])
sprawdz("KONTRDOWOD: same przeterminowane — brak materialu, nie stara notka",
        zaden is None, zaden)

print()
print("=== 4. SPIZARNIA: SWIEZE TEKSTY, STARSZE TYLKO NA RATUNEK ===")


class _Odp:
    def __init__(self, kod, tekst):
        self.status_code = kod
        self.text = tekst


class _Klient:
    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        return _Odp(200, "<p>%s</p>" % " ".join(["slowo"] * 200))


def _w(kanal, nr, dni):
    return {"kanal": kanal, "temat": "%s temat %d" % (kanal, nr),
            "url": "https://%s.example/%d" % (kanal.lower().replace(" ", ""), nr),
            "data": dni_temu(dni), "styk": kk.styk_wpisu(kanal)}


SWIEZE = ([_w(k, n, 0) for k in ("Latent Space", "DeepMind", "HuggingFace") for n in (1, 2)]
          + [_w("Pew", 1, 1), _w("EdSurge", 1, PROG), _w("The 74", 1, 2)])
STARE = [_w("KFF Health", 1, PROG + 5), _w("EFF", 1, PROG + 2),
         _w("CourtListener", 1, PROG + 1), _w("Epoch AI", 1, PROG + 4)]
import httpx  # noqa: E402

_prawdziwy_klient = httpx.Client
_sen = tz.time.sleep
httpx.Client = _Klient
tz.time.sleep = lambda s: None
try:
    sp = tz.tresci_zrodel(STARE + SWIEZE)
    sprawdz("spizarnia pelna", len(sp) == tz.ILE_ZRODEL, len(sp))
    sprawdz("same swieze teksty", all(z["data"] >= dni_temu(PROG) for z in sp),
            sorted(z["data"] for z in sp))
    sprawdz("zrodla o ludziach nadal pierwsze (E6 stoi)",
            {"Pew", "EdSurge", "The 74"} <= {z["kanal"] for z in sp},
            [z["kanal"] for z in sp])
    _log = io.StringIO()
    with contextlib.redirect_stdout(_log):
        sp2 = tz.tresci_zrodel(STARE + [_w("Pew", 1, 1)])
    sprawdz("KONTRDOWOD: swiezych za malo — starsze dobrane do polowy spizarni",
            len(sp2) == tz.ILE_ZRODEL // 2, len(sp2))
    sprawdz("  i log mowi to glosno", "dobieram starsze" in _log.getvalue(),
            _log.getvalue())
    sprawdz("wpis bez daty idzie do starszych",
            tz._podziel_po_wieku([{"kanal": "X", "data": ""}]) == ([], [{"kanal": "X", "data": ""}]))
finally:
    httpx.Client = _prawdziwy_klient
    tz.time.sleep = _sen

print()
print("=== 5. WYDARZENIA: „MAX DZIEN PO” ===")
sprawdz("okno wydarzen: jeden dzien", config.WYDARZENIE_SWIEZOSC_DNI == 1,
        config.WYDARZENIE_SWIEZOSC_DNI)
FALA = [{"kanal": k, "temat": t, "data": dni_temu(3),
         "url": "https://%s.example/x" % k.lower().replace(" ", "")}
        for k, t in (("Kanal A", "Elon ships Grok 4.7 and it is wild"),
                     ("Kanal B", "Grok 4.7 from Elon tested today"),
                     ("Kanal C", "Elon Grok 4.7 first look"))]
sprawdz("KONTROLA: stare okno czterech dni widzi fale sprzed trzech dni",
        bool(kk.wielkie_wydarzenia(FALA)), kk.wielkie_wydarzenia(FALA))
sprawdz("okno jednego dnia jej nie widzi",
        not kk.wielkie_wydarzenia(FALA, swiezosc_dni=config.WYDARZENIE_SWIEZOSC_DNI))
DZISIEJSZA = [dict(w, data=dni_temu(0)) for w in FALA]
sprawdz("KONTRDOWOD: dzisiejsza fala nadal wykryta",
        bool(kk.wielkie_wydarzenia(DZISIEJSZA, swiezosc_dni=config.WYDARZENIE_SWIEZOSC_DNI)))

ARGUMENTY = []
_zapas = (kk.wielkie_wydarzenia, kk.korpus_kanalow, kk.pamiec_wersji, stages.bank_pelny,
          stages._ile_prob_wolno_dzis, stages._wolnych_w_banku)
kk.wielkie_wydarzenia = lambda korpus, **kw: ARGUMENTY.append(kw) or []
kk.korpus_kanalow = lambda ile=30: []
kk.pamiec_wersji = lambda korpus, dodatkowe=None: {}
stages.bank_pelny = lambda: True
stages._ile_prob_wolno_dzis = lambda: 99
stages._wolnych_w_banku = lambda: 99
try:
    with contextlib.redirect_stdout(io.StringIO()):
        stages.znajdz_ciekawostki(sqlite3.connect(":memory:"), None)
finally:
    (kk.wielkie_wydarzenia, kk.korpus_kanalow, kk.pamiec_wersji, stages.bank_pelny,
     stages._ile_prob_wolno_dzis, stages._wolnych_w_banku) = _zapas
sprawdz("skaut pyta wykrywacz z oknem z configu",
        bool(ARGUMENTY) and ARGUMENTY[0].get("swiezosc_dni") == config.WYDARZENIE_SWIEZOSC_DNI,
        ARGUMENTY)

print()
print("=== 6. DZIENNIK: NOTKA NIESIE DATE STRONY ZRODLOWEJ ===")


def _kod(sciezka):
    return "\n".join(w for w in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not w.lstrip().startswith("#"))


sprawdz("run.py przekazuje date zrodla faktu do publikacji",
        '.get("source_date")' in _kod("agent-v2/run.py")
        and "zrodlo_data=str(" in _kod("agent-v2/run.py"))
sprawdz("browser.py zapisuje ja w obu wpisach dziennika notki",
        _kod("agent-v2/browser.py").count("zrodlo_data=zrodlo_data") == 2)

print()
print("=== 7. ZRODLA PO AUDYCIE 27.09 ===")
NOWE = ("The Verge AI", "BBC Tech", "NPR Tech", "Ars Technica AI", "The Conversation AI",
        "TechXplore AI", "Wired AI", "MIT Tech Review AI", "Retraction Watch", "Futurism AI")
sprawdz("serwisy czytane przez ludzi w korpusie", all(n in kk.ZRODLA_LUDZIE for n in NOWE),
        [n for n in NOWE if n not in kk.ZRODLA_LUDZIE])
sprawdz("kazdy przechodzi filtr o AI", all(n in kk.FILTR_O_AI for n in NOWE))
sprawdz("kazdy ma styk z tytulu", all(n in kk.STYK_Z_TYTULU for n in NOWE))
sprawdz("premiera modelu z serwisu ogolnego to branza, nie codziennosc",
        kk.styk_wpisu("The Verge AI", "OpenAI pauses training of its most capable models")
        == "branza")
sprawdz("KONTRDOWOD: tytul o szkole z serwisu ogolnego to szkola",
        kk.styk_wpisu("BBC Tech", "AI tutors arrive in primary schools") == "szkola")
MARTWE = ("Forward Future", "Dr Waku pisany", "Zsolnai-Fehér", "llama.cpp")
sprawdz("martwe feedy usuniete",
        not any(n in kk.ZRODLA or n in kk.ZRODLA_LUDZIE for n in MARTWE))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
