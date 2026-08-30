"""Host, u ktorego komentarz nigdy nie wchodzi, przestaje kosztowac.

TA SAMA WADA, CO PRZY ZRODLACH, w innym miejscu. `hosty_ktore_nigdy_nie_
dzialaly` powstalo, bo porazki pobierania byly zapisywane od poczatku i nigdy
nie wracaly do dyskoverii — `fda.gov` przepadl 3 razy na 3, a slot w limicie
dziesieciu adresow i tak byl na niego wydawany. Dziennik zapisuje nieudane
komentarze RAZEM Z ADRESEM od poczatku i nikt ich nie czytal.

ZMIERZONE 30 sierpnia 2026: 11 nieudanych komentarzy z 92 prob (12 procent),
7 odpowiedzi z 47. Sprawdzone u zrodla — 0 z 6 sprawdzalnych bylo jednak
opublikowanych, wiec to prawdziwa strata, nie blad rozpoznania. Kosztowalo
0,61 USD, czyli 92 procent calego przepalenia agenta.

DLACZEGO ZAPORA NIE WYSTARCZALA. `mozna_komentowac` pyta Substacka o pole
`write_comment_permissions` i przy watpliwosci odpowiada TAK — z uzasadnieniem
„blad w te strone kosztuje jedno nieudane klikniecie". To nieprawda: zapora
stoi PRZED `read_pages` i `comment_on`, wiec falszywe „tak" kosztuje trzy
warianty komentarza plus sprawdzenie faktow, okolo 2,3 centa. Trzy wyjscia
awaryjne (`return True`) prowadzily prosto do tej straty.

PODZIAL PRACY ZOSTAJE CELOWY: optymizm wobec hosta NIEZNANEGO jest sluszny,
bo blad w druga strone zamyka agentowi usta wszedzie tam, gdzie pole ma
wartosc, ktorej nie znamy. Nowe jest tylko to, ze optymizm kosztuje jedna
probe, a nie dziesiata.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import browser   # noqa: E402

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
ORYG = browser.DZIENNIK


def zapisz(*wpisy):
    plik = KAT / "dziennik.jsonl"
    plik.write_text("\n".join(json.dumps(w) for w in wpisy), encoding="utf-8")
    browser.DZIENNIK = plik


def k(host, udane, rodzaj="komentarz"):
    return {"kiedy": "2026-08-30T10:00:00+00:00", "rodzaj": rodzaj,
            "udane": udane, "gdzie": "https://%s/p/cos" % host}


try:
    print("=== 1. DWIE PORAZKI I ZERO SUKCESOW ZDEJMUJA HOST ===")
    zapisz(k("slowboring.com", False), k("slowboring.com", False))
    sprawdz("host z dwiema porazkami odpada",
            "slowboring.com" in browser.hosty_gdzie_komentarz_nie_wchodzi(),
            browser.hosty_gdzie_komentarz_nie_wchodzi())

    print()
    print("=== 2. JEDNA PORAZKA TO ZA MALO ===")
    # Prog dwoch prob, nie jednej — tak samo jak przy zrodlach: jedno
    # niepowodzenie to awaria po drugiej stronie, dwa z rzedu to wlasciwosc
    # hosta. Skreslanie po pierwszej pomylce zamykaloby agentowi usta.
    zapisz(k("nowy.com", False))
    sprawdz("po jednej probie host zostaje",
            "nowy.com" not in browser.hosty_gdzie_komentarz_nie_wchodzi())

    print()
    print("=== 3. JEDEN SUKCES KASUJE HOST Z LISTY ===")
    # Wydawca moze zmienic ustawienia. Lista ma pamietac, kto nas nie wpuszcza,
    # a nie karac dozywotnio — jedno udane wystawienie odblokowuje host samo.
    zapisz(k("czasem.com", False), k("czasem.com", False), k("czasem.com", True))
    sprawdz("host z jednym sukcesem wraca",
            "czasem.com" not in browser.hosty_gdzie_komentarz_nie_wchodzi(),
            browser.hosty_gdzie_komentarz_nie_wchodzi())

    print()
    print("=== 4. NOTKI SIE NIE LICZA ===")
    # Pod notkami komentuje kazdy i nie ma tam hosta w tym sensie. Wpis notki
    # ma w `gdzie` cos w rodzaju "note/c-123", nie adres.
    zapisz({"kiedy": "2026-08-30T10:00:00+00:00", "rodzaj": "komentarz",
            "udane": False, "gdzie": "note/c-322783482"},
           {"kiedy": "2026-08-30T10:00:00+00:00", "rodzaj": "komentarz",
            "udane": False, "gdzie": "note/c-322783483"})
    sprawdz("wpisy notek nie tworza martwego hosta",
            browser.hosty_gdzie_komentarz_nie_wchodzi() == set(),
            browser.hosty_gdzie_komentarz_nie_wchodzi())

    print()
    print("=== 5. TYLKO KOMENTARZE, NIE INNE RODZAJE ===")
    zapisz(k("inne.com", False, rodzaj="polubienie"),
           k("inne.com", False, rodzaj="polubienie"))
    sprawdz("nieudane polubienia nie blokuja komentowania",
            "inne.com" not in browser.hosty_gdzie_komentarz_nie_wchodzi())

    print()
    print("=== 6. KONTRDOWOD: BEZ TEJ FUNKCJI NIC NIE ODSIEWALO ===")
    # Przed poprawka `mozna_komentowac` szlo prosto do zapytania o
    # `write_comment_permissions`, a trzy jego wyjscia awaryjne oddawaly True.
    # Gdyby ta funkcja nic nie zwracala, ponizsze przeszloby i test bylby pusty.
    zapisz(k("martwy.com", False), k("martwy.com", False),
           k("zywy.com", True), k("zywy.com", False))
    lista = browser.hosty_gdzie_komentarz_nie_wchodzi()
    sprawdz("odsiewa martwy", "martwy.com" in lista, lista)
    sprawdz("i NIE odsiewa zywego", "zywy.com" not in lista, lista)
    sprawdz("lista nie jest pusta (test cokolwiek mierzy)", bool(lista))

    print()
    print("=== 7. ZAPORA NAPRAWDE Z NIEJ KORZYSTA ===")
    src = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
    poczatek = src.find("def mozna_komentowac")
    ciało = src[poczatek:poczatek + 1600]
    sprawdz("mozna_komentowac pyta o pamiec hostow",
            "hosty_gdzie_komentarz_nie_wchodzi()" in ciało, ciało[:300])
    sprawdz("i robi to PRZED wejsciem do sieci",
            ciało.find("hosty_gdzie_komentarz_nie_wchodzi()")
            < ciało.find("wymagaj_sesji()"),
            "kolejnosc odwrotna")
finally:
    browser.DZIENNIK = ORYG

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
