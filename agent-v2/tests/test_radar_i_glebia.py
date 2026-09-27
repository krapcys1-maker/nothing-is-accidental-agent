# -*- coding: utf-8 -*-
"""Radar ciekawosci, karta glebi i miara koncowki (27.09.2026).

PO CO. Wlasciciel: „chce pisac ciekawe notki", „miec system, ktory wylapuje to",
„chcemy miec ten system glebokosci danych". Prototyp na zywo tego dnia: radar
ustawil 96 swiezych naglowkow (czolo: agent OpenAI na stronie rzadu Australii),
a pelny tekst BBC odpowiadal na pytanie, ktore notka zostawila „bez odpowiedzi".

Test pilnuje szesciu ogniw, kazde z kontrdowodem:
  1. radar: kolejnosc historii, warianty za czolem, nierankowane i stare na
     koncu, kopie zamiast zmian w korpusie, awaria = kolejnosc korpusu;
  2. spizarnia wg radaru: kolejnosc zostaje, jedna historia raz, E6 stoi,
     hak radaru w bloku dla skauta, miejsce radaru na fakcie;
  3. karta glebi: cytat, ktorego nie ma w tekscie, WYPADA; dokumenty tylko
     z linkow strony; brak strony = brak karty;
  4. weryfikator dostaje cytaty z karty;
  5. koncowka: piec prawdziwych koncowek z 20-26.09 zlapanych, dobre nie;
  6. karta wynikow liczy odbior po radarze, glebi i koncowce; droga do dziennika.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import glebia                   # noqa: E402
import karta_wynikow            # noqa: E402
import korpus_kanalow as kk     # noqa: E402
import llm                      # noqa: E402
import radar                    # noqa: E402
import stages                   # noqa: E402
import tresc_zrodel as tz       # noqa: E402

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


def dni_temu(n):
    return (TERAZ - timedelta(days=n)).strftime("%Y-%m-%d")


def wpis(kanal, temat, dni=0, url=None):
    return {"kanal": kanal, "temat": temat, "data": dni_temu(dni),
            "url": url or "https://%s.example/%s" % (kanal.lower().replace(" ", ""),
                                                      abs(hash(temat)) % 10 ** 6),
            "styk": kk.styk_wpisu(kanal, temat)}


KORPUS = [
    wpis("BBC Tech", "Rogue OpenAI agent infiltrated Australian government website"),   # 0
    wpis("Wpadki AI", "OpenAI hacked Medicare portal, Prime Minister says"),              # 1
    wpis("The Verge AI", "OpenAI pauses training of its most capable models"),           # 2
    wpis("Simon Willison", "Note on 24th September 2026 about my garden"),               # 3
    wpis("The Conversation AI", "AI is creating jobs as well as erasing them"),          # 4
    wpis("Ars Technica AI", "Trump admin using AI to deny medical care for seniors"),    # 5
    wpis("TechXplore AI", "Spotting AI writing: how reliable are the detectors"),        # 6
    wpis("Latent Space", "Foundries vs Navigators: lowering the cost of science"),       # 7
    wpis("404 Media", "AI love song played at murder trial"),                            # 8
    wpis("Wes Roth", "OpenAI just did WHAT", url="https://www.youtube.com/watch?v=x"),   # YouTube
    wpis("Pew", "Americans and AI at work, a survey", dni=9),                            # stary
]
GRUPY = {"grupy": [
    {"ids": [0, 1], "najlepszy": 0, "hak": "An AI agent broke into a government site",
     "glebia": "how it got in"},
    {"ids": [2], "najlepszy": 2, "hak": "OpenAI stops training its top models", "glebia": "why"},
    {"ids": [99, 4, 4], "najlepszy": 4, "hak": "AI makes cleanup jobs", "glebia": "pay"},
    {"ids": [0], "najlepszy": 0, "hak": "duplikat", "glebia": ""},
]}
WOLANIA = []
_prawdziwy_call = llm.call


def _call(purpose, system, user, **kw):
    WOLANIA.append({"purpose": purpose, "user": user})
    if purpose == "radar":
        return json.dumps(GRUPY)
    raise AssertionError("nieoczekiwany etap %s" % purpose)


print("=== 1. RADAR ===")
_przyklady = radar.przyklady_odbioru
radar.przyklady_odbioru = lambda *a, **k: (["- dobra notka o rachunku"], ["- slaba notka o kluczach API"])
llm.call = _call
try:
    radar.wyczysc_zapas()
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        wynik = radar.uporzadkuj(KORPUS, conn=sqlite3.connect(":memory:"), run_id=None)
    tematy = [w["temat"] for w in wynik]
    sprawdz("czolo: najlepszy z kazdej grupy w kolejnosci radaru",
            tematy[:3] == [KORPUS[0]["temat"], KORPUS[2]["temat"], KORPUS[4]["temat"]], tematy[:4])
    sprawdz("wariant historii (Wpadki AI) za wszystkimi czolami",
            tematy[3] == KORPUS[1]["temat"], tematy[3])
    sprawdz("miejsce i hak na najlepszym", wynik[0]["radar"] == {
        "miejsce": 1, "hak": "An AI agent broke into a government site", "glebia": "how it got in"},
        wynik[0].get("radar"))
    sprawdz("wariant ma to samo miejsce i znacznik", wynik[3]["radar"] == {"miejsce": 1, "wariant": True},
            wynik[3].get("radar"))
    sprawdz("zly identyfikator (99) i powtorka nie tworza pozycji",
            len(wynik) == len(KORPUS), len(wynik))
    sprawdz("naglowek juz uzyty w grupie 1 nie tworzy czwartej grupy",
            sum(1 for w in wynik if (w.get("radar") or {}).get("hak") == "duplikat") == 0)
    sprawdz("YouTube i stary wpis na koncu, nie u modelu",
            [w["kanal"] for w in wynik[-2:]] == ["Wes Roth", "Pew"]
            and "youtube" not in WOLANIA[0]["user"] and "survey" not in WOLANIA[0]["user"],
            [w["kanal"] for w in wynik[-2:]])
    sprawdz("model widzi najlepsze i najslabsze notki konta",
            "dobra notka o rachunku" in WOLANIA[0]["user"]
            and "slaba notka o kluczach API" in WOLANIA[0]["user"])
    sprawdz("korpus nietkniety — radar oddaje kopie", all("radar" not in w for w in KORPUS))
    sprawdz("log mowi, co jest na czele", "[radar]" in _log.getvalue() and "Rogue OpenAI" in _log.getvalue(),
            _log.getvalue())

    radar.wyczysc_zapas()
    GRUPY_ZAPAS = GRUPY
    GRUPY = {"grupy": []}
    with contextlib.redirect_stdout(io.StringIO()):
        pusto = radar.uporzadkuj(KORPUS, conn=sqlite3.connect(":memory:"))
    sprawdz("KONTRDOWOD: model bez grup — pusta lista (kolejnosc korpusu)", pusto == [], pusto)
    GRUPY = GRUPY_ZAPAS

    radar.wyczysc_zapas()
    llm.call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("padlo"))
    with contextlib.redirect_stdout(io.StringIO()):
        pusto = radar.uporzadkuj(KORPUS, conn=sqlite3.connect(":memory:"))
    sprawdz("KONTRDOWOD: awaria modelu — pusta lista, bez wyjatku", pusto == [], pusto)
    llm.call = _call

    radar.wyczysc_zapas()
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("za malo swiezych naglowkow — radar milczy",
                radar.uporzadkuj(KORPUS[:3], conn=sqlite3.connect(":memory:")) == [])
        sprawdz("bez bazy (test, recznie) — radar milczy",
                radar.uporzadkuj(KORPUS, conn=None) == [])
    _wl = config.RADAR_WLACZONY
    config.RADAR_WLACZONY = False
    radar.wyczysc_zapas()
    sprawdz("wylacznik dziala", radar.uporzadkuj(KORPUS, conn=sqlite3.connect(":memory:")) == [])
    config.RADAR_WLACZONY = _wl
finally:
    llm.call = _prawdziwy_call
    radar.przyklady_odbioru = _przyklady

print()
print("=== 2. SPIZARNIA WG RADARU ===")


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
        if PADA and PADA in url:
            return _Odp(403, "")
        return _Odp(200, "<p>%s</p>" % " ".join(["slowo"] * 200))


PADA = ""
import httpx  # noqa: E402

_prawdziwy_klient, _sen = httpx.Client, tz.time.sleep
httpx.Client, tz.time.sleep = _Klient, (lambda s: None)
try:
    sp = tz.tresci_zrodel(wynik, wg_radaru=True)
    kanaly = [z["kanal"] for z in sp]
    sprawdz("historia z czola jest w spizarni", "BBC Tech" in kanaly, kanaly)
    sprawdz("JEDNA HISTORIA RAZ: wariant (Wpadki AI) pominiety", "Wpadki AI" not in kanaly, kanaly)
    sprawdz("E6 stoi: teksty o ludziach (poza wariantami) wchodza pierwsze",
            {"The Conversation AI", "Ars Technica AI", "404 Media"} <= set(kanaly[:3]), kanaly)
    sprawdz("E6 stoi: w etapie branzy dwa naglowki, reszta to dopelnienie",
            kanaly[3:5] == ["BBC Tech", "The Verge AI"], kanaly)
    sprawdz("tekst niesie miejsce radaru", any((z.get("radar") or {}).get("miejsce") == 1 for z in sp))
    sp_bez = tz.tresci_zrodel(KORPUS)
    sprawdz("KONTRDOWOD: bez radaru oba naglowki tej samej historii wchodza",
            {"BBC Tech", "Wpadki AI"} <= {z["kanal"] for z in sp_bez}, [z["kanal"] for z in sp_bez])
    tz.wyczysc_zapas()
    blok = tz.blok_do_promptu(wynik, wg_radaru=True)
    sprawdz("blok dla skauta niesie hak radaru, podpisany jako przypuszczenie",
            "Why a reader may care (our radar's guess, not evidence): An AI agent broke into"
            in blok, blok[:400])
    PADA = "bbctech"
    sp_pada = tz.tresci_zrodel(wynik, wg_radaru=True)
    sprawdz("gdy strona najlepszego naglowka pada, historie niesie wariant",
            "Wpadki AI" in [z["kanal"] for z in sp_pada], [z["kanal"] for z in sp_pada])
    PADA = ""
    tz.wyczysc_zapas()
    fakt = {"url": sp[0]["url"]}
    sprawdz("fakt dostaje miejsce radaru po adresie tekstu",
            stages.radar_ze_zrodla(fakt, sp) == (sp[0].get("radar") or {}).get("miejsce"),
            stages.radar_ze_zrodla(fakt, sp))
    sprawdz("KONTRDOWOD: obcy adres — brak miejsca, nie zgadywanie",
            stages.radar_ze_zrodla({"url": "https://inny.example/x"}, sp) is None)
finally:
    httpx.Client, tz.time.sleep = _prawdziwy_klient, _sen
    tz.wyczysc_zapas()

print()
print("=== 3. KARTA GLEBI ===")
TEKST = ("OpenAI said it only learnt of the breach in August while reviewing ‘misaligned "
         "model activity’. Three other government systems “may” also have been "
         "affected. The models took actions it did not intend while looking up statistics "
         "about Australia during an internal evaluation. ") * 3
HTML = ('<p>x</p><a href="https://www.aihw.gov.au/report">r</a>'
        '<a href="https://www.bbc.co.uk/news/other">o</a><a href="https://doi.org/10.1/x">d</a>')
sprawdz("cytat z typograficznymi apostrofami znaleziony",
        glebia._w_tekscie("reviewing 'misaligned model activity'", TEKST))
sprawdz("KONTRDOWOD: parafraza nie jest cytatem",
        not glebia._w_tekscie("OpenAI found out in August", TEKST))
sprawdz("KONTRDOWOD: za krotki cytat niczego nie dowodzi", not glebia._w_tekscie("August", TEKST))
sprawdz("linki pierwotne: urzad i DOI, bez wlasnego serwisu",
        glebia.linki_pierwotne(HTML, "https://www.bbc.co.uk/news/articles/abc")
        == ["https://www.aihw.gov.au/report", "https://doi.org/10.1/x"],
        glebia.linki_pierwotne(HTML, "https://www.bbc.co.uk/news/articles/abc"))

ODPOWIEDZ_MODELU = {
    "data_points": [
        {"value": "3 systems", "compared_to": "", "who": "the PM",
         "quote": "Three other government systems \"may\" also have been affected"},
        {"value": "90%", "compared_to": "", "who": "invented",
         "quote": "ninety percent of agencies were breached"}],
    "most_surprising": {"detail": "found in a review", "quote": "learnt of the breach in August"},
    "reader_question": "How did it get in?",
    "answer": {"text": "during an internal evaluation",
               "quote": "while looking up statistics about Australia during an internal evaluation"},
    "primary_documents": ["https://www.aihw.gov.au/report", "https://zmyslony.example/pdf"]}
_pob = glebia._pobierz
glebia._pobierz = lambda url: ((HTML, TEKST) if "bbc" in url else ("", ""))
llm.call = lambda purpose, system, user, **kw: (
    json.dumps(ODPOWIEDZ_MODELU) if purpose == "glebia" else (_ for _ in ()).throw(AssertionError(purpose)))
try:
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        karta = glebia.karta_glebi({"url": "https://www.bbc.co.uk/news/articles/abc",
                                    "fact": "An OpenAI agent accessed a portal."},
                                   conn=sqlite3.connect(":memory:"))
    sprawdz("karta powstala", isinstance(karta, dict), karta)
    karta = karta or {}
    sprawdz("liczba z prawdziwym cytatem zostaje", [p["value"] for p in karta.get("data_points", [])] == ["3 systems"],
            karta.get("data_points"))
    sprawdz("KONTRDOWOD: zmyslona liczba (cytatu nie ma w tekscie) wypada",
            all(p["value"] != "90%" for p in karta.get("data_points", [])))
    sprawdz("odpowiedz na pytanie czytelnika z cytatem zostaje",
            (karta.get("answer") or {}).get("text") == "during an internal evaluation")
    sprawdz("dokumenty tylko z linkow strony", karta.get("primary_documents") == ["https://www.aihw.gov.au/report"],
            karta.get("primary_documents"))
    sprawdz("log mowi o odrzuconym cytacie", "odrzucone 1" in _log.getvalue(), _log.getvalue())
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("KONTRDOWOD: strony nie da sie pobrac — brak karty",
                glebia.karta_glebi({"url": "https://nie.example/x"}, conn=None) is None)
    ODPOWIEDZ_MODELU = {"data_points": [{"value": "1", "quote": "zmyslone zdanie, ktorego tam nie ma"}]}
    with contextlib.redirect_stdout(io.StringIO()):
        sprawdz("KONTRDOWOD: nic sprawdzalnego — brak karty",
                glebia.karta_glebi({"url": "https://www.bbc.co.uk/x"}, conn=None) is None)
    _wl = config.GLEBIA_WLACZONA
    config.GLEBIA_WLACZONA = False
    sprawdz("wylacznik dziala", glebia.karta_glebi({"url": "https://www.bbc.co.uk/x"}) is None)
    config.GLEBIA_WLACZONA = _wl
finally:
    glebia._pobierz = _pob
    llm.call = _prawdziwy_call

print()
print("=== 4. WERYFIKATOR DOSTAJE CYTATY Z KARTY ===")
dowod = {"fact": {"fact": "An OpenAI agent accessed a portal.", "url": "https://www.bbc.co.uk/x"},
         "depth": {k: v for k, v in karta.items() if k != "source_chars"}}
rekord = stages._rekord_do_weryfikacji("CIEKAWOSTKA", dowod)
sprawdz("rekord niesie cytat z karty", "Three other government systems" in rekord, rekord[-400:])
sprawdz("KONTRDOWOD: bez karty rekord jak przed zmiana",
        "Quoted from the full source page" not in stages._rekord_do_weryfikacji(
            "CIEKAWOSTKA", {"fact": dowod["fact"]}))

print()
print("=== 5. KONCOWKA, KTORA OCENIA MATERIAL ===")
PRAWDZIWE = [  # ostatnie zdania notek z 20-26.09.2026
    "That's the number I'd want to see before believing the world actually remembers what you did.",
    "I'd want the underlying production counts before treating the four-year figure as a law.",
    "Wait for someone without a launch blog to put it through its paces.",
    "No launch document has surfaced yet, and the reporting doesn't say whether the standards would bind anyone.",
    "What the review might find, nobody's saying yet.",
]
for z in PRAWDZIWE:
    sprawdz("lapie: %s..." % z[:50], bool(stages.konczy_ocena_materialu("Some context. " + z)))
DOBRE = ["Thinking got cheap. Doing stayed expensive.",
         "So AI can reorganise work without erasing it. The correction becomes the job.",
         "Australia is checking whether its break-in rulebook still works when the intruder is a program."]
for z in DOBRE:
    sprawdz("KONTRDOWOD: nie lapie: %s..." % z[:45], not stages.konczy_ocena_materialu(z))
sprawdz("tylko ostatnie zdanie — niepewnosc w srodku notki jest w porzadku",
        not stages.konczy_ocena_materialu("The company hasn't published the numbers. So the bill still lands on you."))

print()
print("=== 6. KARTA WYNIKOW I DROGA DO DZIENNIKA ===")
_do = date.today()
_wyst = (datetime.now(timezone.utc) - timedelta(days=5)).replace(microsecond=0)
STAT = []
DZ = []
for nid, radar_m, glb, konc, wysw, odw in (("1", 1, 3, "", 100, 5), ("2", 6, 0, "I'd want", 100, 1),
                                          ("3", None, 2, "", 50, 2)):
    STAT.append({"rodzaj": "notka", "id": nid, "wyswietlenia": wysw, "odwiedziny_profilu": odw,
                 "wystawione": _wyst.isoformat(), "zmierzone": (_wyst + timedelta(hours=72)).isoformat()})
    DZ.append({"rodzaj": "notka", "udane": True, "id": nid, "radar": radar_m, "glebia": glb,
               "glebia_odpowiedz": False, "koncowka_ocena": konc})
STAT.append({"rodzaj": "notka", "id": "4", "wyswietlenia": 40, "odwiedziny_profilu": 0,
             "wystawione": _wyst.isoformat(), "zmierzone": (_wyst + timedelta(hours=72)).isoformat()})
DZ.append({"rodzaj": "notka", "udane": True, "id": "4"})
rg = karta_wynikow.odbior_radar_glebia(STAT, DZ, [], _do - timedelta(days=6), _do)
sprawdz("radar: czolo / dalej / poza / przed", {g: v["n"] for g, v in rg["radar"].items()}
        == {"czolo": 1, "dalej": 1, "brak": 1, "przed": 1}, rg["radar"])
sprawdz("czolo liczone ta sama miara (5 odwiedzin na 100 wyswietlen)", rg["radar"]["czolo"]["wynik"] == 5.0,
        rg["radar"]["czolo"])
sprawdz("glebia: z karta / bez / przed", {g: v["n"] for g, v in rg["glebia"].items()}
        == {"z_karta": 2, "bez_karty": 1, "przed": 1}, rg["glebia"])
sprawdz("koncowka: mysl / ocena / przed", {g: v["n"] for g, v in rg["koncowka"].items()}
        == {"konczy_mysl": 2, "ocenia": 1, "przed": 1}, rg["koncowka"])


def _kod(sciezka):
    return "\n".join(w for w in pathlib.Path(sciezka).read_text(
        encoding="utf-8").splitlines() if not w.lstrip().startswith("#"))


_st, _run, _br = _kod("agent-v2/stages.py"), _kod("agent-v2/run.py"), _kod("agent-v2/browser.py")
sprawdz("skaut pyta radar przed spizarnia",
        "_radar.uporzadkuj(_korpus, conn=conn, run_id=run_id)" in _st
        and "wg_radaru=bool(_po_radarze)" in _st)
sprawdz("notka dostaje karte glebi i pola pomiaru",
        "_glebia.karta_glebi(fakt, conn=conn, run_id=run_id)" in _st
        and 'wynik["radar"]' in _st and 'wynik["glebia"]' in _st and 'wynik["zrodlo_host"]' in _st)
sprawdz("run.py przekazuje pomiar bez wolania nowych funkcji stages",
        "pomiar={" in _run and "stages.konczy_ocena_materialu" not in _run)
sprawdz("browser.py zapisuje pomiar w obu wpisach dziennika notki",
        _br.count("**(pomiar or {}))") == 2)
for nazwa in ("radar.md", "glebia.md", "notka.md", "rozbior.md"):
    _surowy = (pathlib.Path("agent-v2/prompts") / nazwa).read_text(encoding="utf-8")
    import re  # noqa: E402
    _pola = set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", _surowy))
    try:
        _surowy.format(**{p: "x" for p in _pola})
        _ok = True
    except (KeyError, ValueError, IndexError) as exc:
        _ok = exc
    sprawdz("%s formatuje sie bez bledu" % nazwa, _ok is True, _ok)
sprawdz("etapy maja model, sufit i wylaczone rozumowanie",
        all(config.MODEL_FOR.get(e) and config.MAX_TOKENS.get(e)
            and config.myslenie_deepseek(e) == {"type": "disabled"} for e in ("radar", "glebia")))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
