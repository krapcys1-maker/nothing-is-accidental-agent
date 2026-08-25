"""Artykul nie wychodzi w swiat bez sprawdzenia faktow.

CO SIE STALO. 25 sierpnia 2026 poszedl na produkcje artykul „The Watermark Was
Never a Verdict". Stal na tym, ze kalifornijska SB 942 wymaga znaku wodnego w
TEKSCIE. Nastepnego dnia notka promujaca ten sam artykul przeszla przez
`stages.zweryfikuj()` i ODPADLA — obowiazki SB 942 obejmuja obraz, wideo i
dzwiek, a slowo „text" zostalo z czesci nakladajacej obowiazki usuniete.

Notka za pol centa zlapala blad, ktorego artykul za 76 centow nie mial jak
zlapac, bo na jego sciezce tego sprawdzenia po prostu nie bylo.

DLACZEGO GO NIE BYLO. `gates.verdict` zwraca zawsze „SAVED" — decyzja
wlasciciela z 15 sierpnia: „artykul powstaje ZAWSZE, uwagi wracaja do
wlasciciela do przeczytania". Sluszna, dopoki artykul byl szkicem dla czlowieka.
Gdy publikacja stala sie automatyczna, „nic nie blokuje" zaczelo znaczyc „nic
nie sprawdza".

CZEGO PILNUJE TEN TEST. Ze miedzy wejsciem w galaz `--wyslij` a wywolaniem
`browser.wystaw_artykul` stoi `stages.zweryfikuj`, i ze przy niepowodzeniu
sciezka WRACA zamiast publikowac. Zapis artykulu ma zostac — blokujemy wyjscie
na zewnatrz, nie prace.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def wycinek_publikacji(src: str) -> str:
    """Kod od wejscia w galaz `--wyslij` do wywolania `wystaw_artykul`.

    Patrzymy na sam ten odcinek, a nie na caly plik: `zweryfikuj` wystepuje w
    run.py takze przy notkach i komentarzach, wiec zwykle „czy slowo jest w
    pliku" przeszloby TAKZE przed poprawka i niczego by nie dowodzilo.
    """
    poczatek = src.find("if args.wyslij:")
    if poczatek < 0:
        return ""
    koniec = src.find("wystaw_artykul", poczatek)
    if koniec < 0:
        return ""
    return src[poczatek:koniec]


# Tak wygladala ta galaz PRZED poprawka. Wykrywacz ma ja odrzucic — bez tego
# nie wiadomo, czy test w ogole rozroznia wersje.
PRZED_POPRAWKA = '''
        if args.wyslij:
            import browser

            print("\\n-- publikacja --", flush=True)
            wynik = browser.wystaw_artykul(path, wyslij=True)
'''

RUN = pathlib.Path("agent-v2/run.py")
src = RUN.read_text(encoding="utf-8")

print("=== 1. WYKRYWACZ ROZROZNIA WERSJE (KONTRDOWOD) ===")
sprawdz("stara galaz NIE ma zweryfikuj przed publikacja",
        "zweryfikuj" not in wycinek_publikacji(PRZED_POPRAWKA),
        repr(wycinek_publikacji(PRZED_POPRAWKA))[:120])
sprawdz("i wykrywacz w ogole cos z niej wycina",
        "import browser" in wycinek_publikacji(PRZED_POPRAWKA))

print()
print("=== 2. BIEZACY KOD SPRAWDZA FAKTY PRZED WYJSCIEM W SWIAT ===")
wycinek = wycinek_publikacji(src)
sprawdz("galaz --wyslij zostala znaleziona", bool(wycinek))
sprawdz("stoi w niej wywolanie stages.zweryfikuj",
        "stages.zweryfikuj(" in wycinek, wycinek[-200:])
sprawdz("sprawdzany jest TEKST ARTYKULU, nie karta",
        'draft["body"]' in wycinek, wycinek[-200:])
sprawdz("decyzja czytana jest z safe_to_post",
        "safe_to_post" in wycinek, wycinek[-200:])

print()
print("=== 3. NIEPOWODZENIE ZATRZYMUJE PUBLIKACJE, NIE PRACE ===")
# Miedzy sprawdzeniem a `wystaw_artykul` musi byc wyjscie ze sciezki. Bez niego
# ostrzezenie tylko by sie wypisalo, a artykul i tak by poszedl — czyli
# dokladnie to, co robila stara brama „nic nie blokuje".
po_audycie = wycinek[wycinek.find("stages.zweryfikuj("):] if "stages.zweryfikuj(" in wycinek else ""
sprawdz("jest wyjscie ze sciezki przed publikacja",
        "return" in po_audycie, po_audycie[:200])
sprawdz("i wyjscie zalezy od NIEPOWODZENIA sprawdzenia",
        'not audyt.get("safe_to_post")' in po_audycie, po_audycie[:200])
sprawdz("artykul mimo to zostaje zapisany",
        "zapisany" in po_audycie or "path" in po_audycie, po_audycie[:200])

print()
print("=== 4. SPRAWDZENIE NIE MOZE BYC CICHE ===")
# Zablokowany artykul, o ktorym nikt sie nie dowiaduje, jest gorszy niz
# opublikowany z bledem: znika bez sladu i nikt nie wie, czego szukac.
sprawdz("powod blokady jest wypisywany",
        "NIE PUBLIKUJE" in po_audycie, po_audycie[:200])
sprawdz("i wypisywane sa poszczegolne zakwestionowane twierdzenia",
        "refuted" in po_audycie and "claims" in po_audycie, po_audycie[:300])

print()
print("=== 5. `zweryfikuj` PRZY WLASNEJ AWARII PRZEPUSZCZA ===")
# Zepsuta weryfikacja to nie dowod falszu. Gdyby awaria blokowala, jedna
# padnieta sesja sieciowa kasowalaby artykul wart 76 centow.
import stages   # noqa: E402
zrodlo_zweryfikuj = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
poczatek = zrodlo_zweryfikuj.find("def zweryfikuj(")
cialo = zrodlo_zweryfikuj[poczatek:poczatek + 2000]
sprawdz("awaria oddaje safe_to_post = True",
        '"safe_to_post": True' in cialo, cialo[:200])
sprawdz("i mowi wprost, ze puszcza na pierwszej siatce",
        "pierwszej siatce" in cialo)
sprawdz("funkcja istnieje i jest wywolywalna", callable(stages.zweryfikuj))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
