"""Kolejka promocji: trzy notki na artykul, po jednej dziennie, NAJSWIEZSZY pierwszy.

Decyzja wlasciciela z 20 sierpnia 2026: „promocja ma byc jedna notka po
artykule dziennie, trzy dni z rzedu".

Wczesniej bylo piec notek i kolejka szla w kolejnosci WSTAWIANIA. Skutek widac
bylo na zywych danych: artykul opublikowany 19 sierpnia stal w pliku za dwoma
starszymi, ktore nie wybraly jeszcze swoich dni, wiec pierwsza notke promujaca
dostalby okolo 29 sierpnia — z linkiem zimnym i tekstem dawno zepchnietym w dol
kanalu. Slowo „po artykule" znaczy zaraz po nim.

Przy okazji wyszla druga rzecz, ktorej nie szukalem. Warunek „ten artykul byl
juz dzis promowany" tylko POMIJAL go i szedl dalej po liscie. Funkcja jest
wolana raz na przebieg, a przebiegow jest trzy dziennie — wiec drugi przebieg
brał nastepny artykul z kolejki i tego samego dnia wychodzila DRUGA notka
promujaca, tyle ze innego tekstu. Nigdy sie to nie ujawnilo, bo kolejka nie
byla dosc pelna. Regula mowi „jedna dziennie" i to jest caly dzien, nie jeden
wiersz pliku.
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


KAT = pathlib.Path(tempfile.mkdtemp())
ORYG = stages.PROMOCJA
stages.PROMOCJA = KAT / "promocja.json"


def ustaw(*wpisy):
    """Kolejka w kolejnosci WSTAWIANIA: pierwszy argument = najstarszy."""
    stages.PROMOCJA.write_text(json.dumps(list(wpisy), ensure_ascii=False),
                               encoding="utf-8")


def _dzis(przesuniecie=0):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc)
            + timedelta(days=przesuniecie)).strftime("%Y-%m-%d")


def wpis(tytul, wystawione=0, ostatnia=None, dodane=None):
    # `dodane` domyslnie DZISIAJ: te przypadki badaja kolejnosc i liczniki, a
    # nie okno waznosci, wiec maja byc swieze. Okno ma wlasna sekcje nizej.
    return {"url": "https://x/p/%s" % tytul.lower().replace(" ", "-"),
            "tytul": tytul, "tekst": "tresc", "wystawione": wystawione,
            "ostatnia": ostatnia,
            "dodane": dodane if dodane is not None else _dzis()}


try:
    print("=== 1. TRZY, NIE PIEC ===")
    sprawdz("NOTEK_PROMUJACYCH = 3", config.NOTEK_PROMUJACYCH == 3,
            config.NOTEK_PROMUJACYCH)

    print()
    print("=== 2. NAJSWIEZSZY IDZIE PIERWSZY ===")
    # Doslownie stan produkcji z 19 sierpnia: dwa starsze bez ani jednej notki,
    # swiezy artykul dopisany na koncu.
    ustaw(wpis("Egg Aisle", wystawione=3),
          wpis("Airplane Window"),
          wpis("The Clock"),
          wpis("The Bottle"))
    w = stages.artykul_do_promocji()
    sprawdz("wybrany jest NAJSWIEZSZY", w and w["tytul"] == "The Bottle",
            w and w["tytul"])

    # KONTRDOWOD: stary sposob (kolejnosc wstawiania) wzialby Airplane Window,
    # czyli tekst sprzed dwoch dni. Bez tego test nie odroznialby wersji.
    stary = next((a for a in stages.wczytaj_promocje()
                  if a.get("wystawione", 0) < config.NOTEK_PROMUJACYCH), None)
    sprawdz("stary sposob wzialby starszy tekst (test rozroznia)",
            stary and stary["tytul"] == "Airplane Window", stary and stary["tytul"])

    print()
    print("=== 3. TRZY DNI Z RZEDU NA TYM SAMYM ARTYKULE ===")
    ustaw(wpis("The Bottle"))
    dni = []
    for _ in range(4):
        w = stages.artykul_do_promocji()
        if w is None:
            dni.append(None)
            continue
        dni.append(w["tytul"])
        stages.odhacz_promocje(w["url"])
        # UPLYW DOBY. `odhacz_promocje` stempluje dzisiejsza date, a nowy
        # warunek „czy cokolwiek szlo dzis" porownuje wlasnie z dzisiejsza —
        # wiec zeby zasymulowac nastepny dzien, cofamy stempel w przeszlosc.
        # To jedyna rzecz, ktora tu udajemy: licznik `wystawione` rosnie
        # naprawde i to on ma zatrzymac promocje po trzecim dniu.
        dane = stages.wczytaj_promocje()
        for a in dane:
            a["ostatnia"] = "2026-01-01"
        stages.PROMOCJA.write_text(json.dumps(dane, ensure_ascii=False),
                                   encoding="utf-8")
    print("    kolejne dni: %s" % dni)
    sprawdz("promowany przez DOKLADNIE trzy dni",
            dni[:3] == ["The Bottle"] * 3, dni)
    sprawdz("czwartego dnia juz nie", dni[3] is None, dni[3])
    licznik = stages.wczytaj_promocje()[0]["wystawione"]
    sprawdz("licznik doszedl do trzech", licznik == 3, licznik)

    print()
    print("=== 4. JEDNA NA DOBE ZNACZY JEDNA, NIE JEDNA NA ARTYKUL ===")
    # Trzy przebiegi dziennie wolaja te funkcje trzy razy. Gdy pierwszy juz
    # wystawil notke, kolejne maja MILCZEC — nawet jesli w kolejce czeka inny
    # artykul z niewybranymi dniami.
    from datetime import datetime, timezone   # noqa: E402
    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ustaw(wpis("Starszy", wystawione=1),
          wpis("Nowszy", wystawione=1, ostatnia=dzis))
    w = stages.artykul_do_promocji()
    sprawdz("po dzisiejszej notce nie ma drugiej", w is None,
            w and w["tytul"])

    # KONTRDOWOD: stary warunek tylko pomijal wiersz, wiec oddalby „Starszy".
    dane = stages.wczytaj_promocje()
    po_staremu = next((a for a in dane
                       if a.get("wystawione", 0) < config.NOTEK_PROMUJACYCH
                       and a.get("ostatnia") != dzis), None)
    sprawdz("stary sposob wystawilby DRUGA notke tego dnia (test rozroznia)",
            po_staremu and po_staremu["tytul"] == "Starszy",
            po_staremu and po_staremu["tytul"])

    print()
    print("=== 5. PRZYPADKI BRZEGOWE ===")
    ustaw()
    sprawdz("pusta kolejka nie wywala", stages.artykul_do_promocji() is None)
    stages.PROMOCJA.unlink(missing_ok=True)
    sprawdz("brak pliku nie wywala", stages.artykul_do_promocji() is None)
    ustaw(wpis("Wyczerpany", wystawione=3), wpis("Tez", wystawione=5))
    sprawdz("wszystkie wyczerpane -> nic", stages.artykul_do_promocji() is None)

    print()
    print("=== 6. NOWY ARTYKUL PRZEJMUJE KOLEJKE OD ZARAZ ===")
    # Publikacja w trakcie trzech dni starszego tekstu: nowy jest swiezszy,
    # wiec od nastepnego dnia promujemy jego. To jest wybor, nie usterka —
    # zimny link nie zyskuje na czekaniu, a swiezy traci.
    ustaw(wpis("Wczorajszy", wystawione=1))
    stages.zapisz_do_promocji("https://x/p/dzisiejszy", "Dzisiejszy", "tresc")
    w = stages.artykul_do_promocji()
    sprawdz("nowy artykul wchodzi przed niedokonczony starszy",
            w and w["tytul"] == "Dzisiejszy", w and w["tytul"])

    print()
    print("=== 7. OKNO WAZNOSCI: STARY ARTYKUL PRZESTAJE BYC PROMOWANY ===")
    # Zmierzone 26 sierpnia na produkcji. Konto przestawiono na AI, ale w
    # kolejce zostaly cztery teksty z epoki przedmiotow codziennych, dwa z
    # niewybranymi dniami. Nic ich nie usuwalo, bo jedynym warunkiem wyjscia
    # bylo wybranie trzech notek. Po wyczerpaniu biezacego artykulu kanal o AI
    # wystawilby notke promujaca artykul o szamponie sprzed tygodnia.
    sprawdz("OKNO_PROMOCJI_DNI istnieje", config.OKNO_PROMOCJI_DNI == 7,
            getattr(config, "OKNO_PROMOCJI_DNI", "brak"))

    ustaw(wpis("Szampon", wystawione=1,
               dodane=_dzis(-config.OKNO_PROMOCJI_DNI - 1)))
    sprawdz("artykul spoza okna nie jest promowany",
            stages.artykul_do_promocji() is None,
            (stages.artykul_do_promocji() or {}).get("tytul"))

    # KONTRDOWOD: przed poprawka jedynym warunkiem bylo `wystawione`, wiec ten
    # sam wpis zostalby wybrany. Bez tego sprawdzenia test nie odrozniac wersji.
    po_staremu = next((a for a in reversed(stages.wczytaj_promocje())
                       if a.get("wystawione", 0) < config.NOTEK_PROMUJACYCH),
                      None)
    sprawdz("stary sposob wystawilby szampon (test rozroznia)",
            po_staremu and po_staremu["tytul"] == "Szampon",
            po_staremu and po_staremu["tytul"])

    # GRANICA JEST WLACZAJACA: ostatni dzien okna jeszcze promuje.
    ustaw(wpis("Ostatni dzien", dodane=_dzis(-config.OKNO_PROMOCJI_DNI)))
    w = stages.artykul_do_promocji()
    sprawdz("w ostatnim dniu okna jeszcze promujemy",
            w and w["tytul"] == "Ostatni dzien", w and w["tytul"])

    # WPIS BEZ `dodane` pochodzi sprzed tej reguly — traktujemy jak stary.
    stary_format = {"url": "https://x/p/legacy", "tytul": "Bez daty",
                    "tekst": "tresc", "wystawione": 0, "ostatnia": None}
    ustaw(stary_format)
    sprawdz("wpis bez `dodane` nie jest promowany",
            stages.artykul_do_promocji() is None,
            (stages.artykul_do_promocji() or {}).get("tytul"))

    # ...ale swiezy artykul dopisany OBOK niego nadal dziala. Okno ma odcinac
    # przeterminowane, nie zatrzymywac kolejki.
    ustaw(stary_format)
    stages.zapisz_do_promocji("https://x/p/swiezy", "Swiezy", "tresc")
    w = stages.artykul_do_promocji()
    sprawdz("swiezy obok przeterminowanego dziala",
            w and w["tytul"] == "Swiezy", w and w["tytul"])
    sprawdz("i zapis stempluje `dodane`",
            stages.wczytaj_promocje()[-1].get("dodane") == _dzis(),
            stages.wczytaj_promocje()[-1].get("dodane"))
finally:
    stages.PROMOCJA = ORYG

print()
print("=== TRZY NOTKI PROMUJACE NIE MOGA POWTARZAC TEGO SAMEGO ===")
# Zmierzone na dzienniku produkcji: trzy notki promujace artykul 0025, z trzech
# kolejnych dni, nioslY te sama fraze „ASTM, which maintains the standard, says"
# i ten sam „68% of Americans". Karta promocyjna to CALY TEKST ARTYKULU podawany
# bez zmian, wiec model co dzien wybieral z niego to samo.
#
# Indeks `zuzyte_fakty` tego nie lapal i lapac nie mogl — on pilnuje ciekawostek
# z puli faktow, a promocja przez te pule nie przechodzi w ogole.
import json as _json         # noqa: E402
import tempfile as _tmp      # noqa: E402

with _tmp.TemporaryDirectory() as _kat:
    _stary = stages.PROMOCJA
    stages.PROMOCJA = pathlib.Path(_kat) / "promocja.json"
    try:
        stages.PROMOCJA.write_text(_json.dumps(
            [{"url": "u1", "tytul": "T", "tekst": "tresc", "wystawione": 0}]),
            encoding="utf-8")
        stages.odhacz_promocje("u1", "Pierwsza notka: ASTM i 68 procent.")
        stages.odhacz_promocje("u1", "Druga notka: zupelnie co innego.")
        _d = _json.loads(stages.PROMOCJA.read_text(encoding="utf-8"))[0]
        sprawdz("dzien promocji nadal sie liczy", _d["wystawione"] == 2, _d)
        sprawdz("i tresc kazdej notki jest zapamietana",
                len(_d.get("powiedziane") or []) == 2, _d.get("powiedziane"))
        sprawdz("w kolejnosci, w jakiej wyszly",
                _d["powiedziane"][0].startswith("Pierwsza"), _d.get("powiedziane"))
        # KONTRDOWOD: odhaczenie BEZ tresci nie moze dopisywac pustych wpisow —
        # inaczej lista rosnie o nic i model dostaje szum.
        stages.odhacz_promocje("u1", "")
        _d2 = _json.loads(stages.PROMOCJA.read_text(encoding="utf-8"))[0]
        sprawdz("puste odhaczenie nie dopisuje wpisu",
                len(_d2["powiedziane"]) == 2, _d2["powiedziane"])
        sprawdz("ale dzien i tak sie liczy", _d2["wystawione"] == 3)
    finally:
        stages.PROMOCJA = _stary

# Karta promocyjna MUSI niesc te pamiec do modelu, inaczej zapis jest ozdoba.
_st = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("karta promocyjna niesie juz powiedziane",
        '"already_said_in_earlier_notes"' in _st)
_run = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("i run.py przekazuje tresc przy odhaczaniu",
        "odhacz_promocje(" in _run and 'gotowe[0].get("note")' in _run)
# I prompt musi tego ZAKAZYWAC — samo podanie pola nic nie znaczy.
_n = pathlib.Path("agent-v2/prompts/notka.md").read_text(encoding="utf-8")
sprawdz("prompt zakazuje powtarzania wydanych zdan",
        "already_said_in_earlier_notes" in _n and "those sentences are" in _n)
sprawdz("i nazywa, jak to wyglada z zewnatrz",
        "working through a backlog" in _n)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
