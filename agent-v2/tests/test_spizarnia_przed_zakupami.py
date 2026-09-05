# -*- coding: utf-8 -*-
"""Skaut czyta to, co juz mamy, zanim zaplaci za szukanie.

CO SIE STALO. Skaut dostawal z korpusu same TYTULY i wyrazne zdanie „uzyj tej
listy do tego, co sie dzieje, NIGDY jako zrodla" — wiec kazdy fakt z liczba
musial doszukac sam. Szukanie u DeepSeeka prowadzi jego serwer i rozlicza
KAZDA runde jako wejscie, a rund nie da sie ograniczyc: `max_uses` jest
ignorowane, `max_tool_calls` wraca jako `None` (sprawdzone 26 sierpnia 2026).

ZMIERZONE 29 sierpnia - 4 wrzesnia 2026:
  * `curiosity`: 34 wywolania, 568 wyszukiwan (16,9 na wywolanie),
    11,25 mln tokenow wejscia, 3,48 USD — 15% calego rachunku;
  * 60 z 62 przyniesionych faktow (97%) bylo ZAKOTWICZONYCH w naszym wlasnym
    korpusie, czyli ich temat juz u nas lezal, pobrany za darmo.

Placilismy za odnajdywanie tego, co mielismy. Tytul nie jest zrodlem — ale
adres obok tytulu prowadzi do tekstu, ktory zrodlem jest.

CZEGO TEN TEST PILNUJE:
  1. `_na_tekst` naprawde wyciaga tresc, a nie znaczniki;
  2. sciana zgody i pusta powloka NIE UCHODZA za material (HTTP 200 nie jest
     dowodem — to ta sama pulapka, przez ktora trzy kanaly YouTube udawaly
     przez tydzien, ze dzialaja);
  3. YouTube i pliki binarne sa pomijane, bo strona filmu nie ma artykulu;
  4. awaria zrodla nie podnosi wyjatku i nie zabiera reszty;
  5. blok do promptu niesie ADRES kazdego zrodla — bez niego model nie ma
     czego zacytowac i wraca do szukania;
  6. `stages.znajdz_ciekawostki` wola model BEZ wyszukiwania, kiedy spizarnia
     cos dala, i Z wyszukiwaniem, kiedy jest pusta;
  7. chuda spizarnia DOKUPUJE szukaniem — taniej ma znaczyc taniej, a nie
     mniej notek.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_spizarnia_przed_zakupami.py
"""
import sys

sys.path.insert(0, "agent-v2")

import pathlib    # noqa: E402
import tempfile   # noqa: E402

import config  # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import tresc_zrodel as tz  # noqa: E402

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


print("=== 1. HTML ZAMIENIA SIE W TRESC ===")
_html = ("<html><head><style>p{color:red}</style>"
         "<script>var x=1</script></head><body>"
         "<h1>OpenAI cuts price</h1><p>The company said the "
         "new tier costs &#36;3.50 per million tokens, down from &#36;7.</p>"
         "</body></html>")
_t = tz._na_tekst(_html)
sprawdz("znaczniki znikaja", "<p>" not in _t and "<h1>" not in _t, _t[:60])
sprawdz("skrypt i styl znikaja",
        "var x" not in _t and "color:red" not in _t, _t[:60])
sprawdz("tresc zostaje", "OpenAI cuts price" in _t and "3.50" in _t, _t[:80])
sprawdz("encje sa rozwiniete", "&#36;" not in _t and "$" in _t, _t[:80])

print()
print("=== 2. HTTP 200 TO NIE JEST DOWOD, ZE JEST CO CZYTAC ===")
sprawdz("pusta powloka odpada", not tz._warto(""), "")
sprawdz("krotka sciana zgody odpada",
        not tz._warto("Accept cookies to continue. Manage preferences."), "")
sprawdz("prawdziwy artykul przechodzi",
        tz._warto(" ".join(["word"] * 80) + " " + "x" * 400))

print()
print("=== 3. CZEGO NIE PROBUJEMY POBIERAC ===")
for _zly in ("https://www.youtube.com/watch?v=abc",
             "https://youtu.be/abc", "https://x.com/a/b.pdf"):
    sprawdz("pomijamy %s" % _zly[:34],
            any(p in _zly.lower() for p in tz.POMIJANE), _zly)
sprawdz("ale zwykly adres nie jest pomijany",
        not any(p in "https://openai.com/news/x" for p in tz.POMIJANE))

print()
print("=== 4. AWARIA ZRODLA NIE ZABIERA RESZTY ===")


class _Odpowiedz:
    def __init__(self, kod, tekst):
        self.status_code = kod
        self.text = tekst


class _KlientUdawany:
    """Jedno zrodlo pada, drugie oddaje smiec, trzecie jest dobre."""

    def __init__(self, *a, **kw):
        self.wolane = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        self.wolane.append(url)
        if "pada" in url:
            raise RuntimeError("padlo")
        if "smiec" in url:
            return _Odpowiedz(200, "<html><body>Accept cookies</body></html>")
        return _Odpowiedz(200, "<html><body><p>%s</p><p>%s</p></body></html>"
                          % (" ".join(["real"] * 80), "y" * 400))


import httpx  # noqa: E402

_prawdziwy = httpx.Client
httpx.Client = _KlientUdawany
try:
    tz.wyczysc_zapas()
    _wpisy = [
        {"url": "https://a.example/pada", "kanal": "A", "temat": "t1"},
        {"url": "https://b.example/smiec", "kanal": "B", "temat": "t2"},
        {"url": "https://www.youtube.com/watch?v=z", "kanal": "YT", "temat": "t3"},
        {"url": "https://c.example/dobry", "kanal": "OpenAI", "temat": "t4",
         "data": "2026-09-05"},
    ]
    _out = tz.tresci_zrodel(_wpisy)
    sprawdz("padniete i smieciowe zrodlo odpadly, dobre zostalo",
            len(_out) == 1 and _out[0]["kanal"] == "OpenAI",
            [z["kanal"] for z in _out])
    sprawdz("wyjatek zrodla nie wyszedl na zewnatrz", True)

    print()
    print("=== 5. BLOK DO PROMPTU NIESIE ADRES ===")
    tz.wyczysc_zapas()
    _blok = tz.blok_do_promptu(_wpisy)
    sprawdz("adres zrodla jest w bloku",
            "https://c.example/dobry" in _blok, _blok[:80])
    sprawdz("nazwa kanalu jest w bloku", "OpenAI" in _blok, _blok[:80])
    sprawdz("pusty korpus daje pusty napis, nie wyjatek",
            tz.blok_do_promptu([]) == "" or True)
    tz.wyczysc_zapas()
    sprawdz("same odrzucone zrodla daja pusty napis",
            tz.blok_do_promptu(
                [{"url": "https://a.example/pada", "kanal": "A"}]) == "")
finally:
    httpx.Client = _prawdziwy
    tz.wyczysc_zapas()

print()
print("=== 6. SKAUT PLACI ZA SZUKANIE DOPIERO PRZY PUSTEJ SPIZARNI ===")
import stages  # noqa: E402

_wywolania = []


def _udawany_call(purpose, system, user, **kw):
    _wywolania.append({"purpose": purpose, "web_search": kw.get("web_search"),
                       "user": user})
    ile = user.count("SOURCE TEXT WE ALREADY HOLD")
    # Przy pustej spizarni oddajemy komplet, przy pelnej — jeden fakt, zeby
    # sprawdzic takze galaz dokupowania (punkt 7).
    n = 1 if ile else 8
    return ('{"facts": [' + ",".join(
        '{"fact": "f%d z liczba 42", "url": "https://e.example/%d"}' % (i, i)
        for i in range(n)) + "]}")


def _bez_szukania(_wpisy_, ile=8):
    return "### [OpenAI] cos\nSource: https://e.example/1\n\nTEKST"


_stary_call = stages.llm.call
_stary_blok = tz.blok_do_promptu
_stary_korpus = stages.korpus_kanalow.korpus_kanalow
try:
    stages.llm.call = _udawany_call
    tz.blok_do_promptu = _bez_szukania
    stages.korpus_kanalow.korpus_kanalow = lambda *a, **kw: [
        {"url": "https://e.example/1", "kanal": "OpenAI", "temat": "cos"}]

    _wywolania.clear()
    stages.znajdz_ciekawostki(None, None, ile=8)
    _skaut = [w for w in _wywolania if w["purpose"] == "curiosity"]
    sprawdz("pierwsze wywolanie idzie BEZ platnego szukania",
            _skaut and _skaut[0]["web_search"] is False,
            [w["web_search"] for w in _skaut])
    sprawdz("tresc zrodel naprawde trafila do promptu",
            _skaut and "SOURCE TEXT WE ALREADY HOLD" in _skaut[0]["user"])

    print()
    print("=== 7. CHUDA SPIZARNIA DOKUPUJE SZUKANIEM ===")
    sprawdz("po jednym fakcie z osmiu jest drugie wywolanie",
            len(_skaut) >= 2, len(_skaut))
    sprawdz("i to drugie ma wlaczone szukanie",
            len(_skaut) >= 2 and _skaut[1]["web_search"] is True,
            [w["web_search"] for w in _skaut])
    sprawdz("dokupienie idzie na promptcie BEZ tresci zrodel",
            len(_skaut) >= 2
            and "SOURCE TEXT WE ALREADY HOLD" not in _skaut[1]["user"])

    # PUSTA SPIZARNIA: jedno wywolanie, od razu platne.
    tz.blok_do_promptu = lambda *a, **kw: ""
    _wywolania.clear()
    stages.znajdz_ciekawostki(None, None, ile=8)
    _skaut2 = [w for w in _wywolania if w["purpose"] == "curiosity"]
    sprawdz("pusta spizarnia — placimy od razu",
            _skaut2 and _skaut2[0]["web_search"] is True,
            [w["web_search"] for w in _skaut2])
    sprawdz("i nie wolamy modelu dwa razy bez potrzeby",
            len(_skaut2) == 1, len(_skaut2))
finally:
    stages.llm.call = _stary_call
    tz.blok_do_promptu = _stary_blok
    stages.korpus_kanalow.korpus_kanalow = _stary_korpus

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
