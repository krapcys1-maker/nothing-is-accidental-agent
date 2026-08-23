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

sys.path.insert(0, "agent-v3")
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


def wpis(tytul, wystawione=0, ostatnia=None):
    return {"url": "https://x/p/%s" % tytul.lower().replace(" ", "-"),
            "tytul": tytul, "tekst": "tresc", "wystawione": wystawione,
            "ostatnia": ostatnia}


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
    dzis = config.data_redakcyjna()
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
finally:
    stages.PROMOCJA = ORYG

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
