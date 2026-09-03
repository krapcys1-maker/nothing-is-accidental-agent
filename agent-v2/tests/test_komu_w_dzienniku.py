# -*- coding: utf-8 -*-
"""Komentarz zapisuje UCHWYT rozmowcy, tak samo jak polubienie.

CO ZMIERZONO na produkcyjnym dzienniku 3 wrzesnia 2026:

    polubienie   `komu` = 30 ze 188 (ale 23 z 23 od 1 wrzesnia)  -> 'genieai'
    komentarz    `komu` = 0 ze 149                               -> brak
    komentarz    `publikacja` = jest zawsze                      -> 'Naval'

Dwa kanaly mowily o tych samych ludziach dwoma jezykami: polubienie uchwytem,
komentarz nazwa wyswietlana. Pytanie „czy ten, komu polubilismy notke, dostal
tez komentarz" nie mialo jak sie policzyc — a to jest pytanie o to, czy
robimy cokolwiek spojnego wobec konkretnego czlowieka, czy strzelamy na oslep.

CZEGO NIE ZROBIONO I DLACZEGO. Nie wpisano nazwy pod `komu`. Nazwa („Naval")
i uchwyt („genieai") to dwie rozne rzeczy; sklejenie ich dalo by pole
wygladajace na laczalne i nie bedace nim — wade gorsza od braku pola, bo
cicha. `publikacja` zostaje osobno, do czytania.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_komu_w_dzienniku.py
Zero wywolan modelu, zero sieci.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import kanal   # noqa: E402
import run     # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. UCHWYT DOJEZDZA DO DZIENNIKA ===")
cel = {"pub": "Naval", "uchwyt": "naval", "skad": "kanal czytelnika",
       "komentarze": 3, "reakcje": 10, "data": ""}
opis = run.opis_celu(cel)
sprawdz("wpis ma pole `komu`", "komu" in opis, sorted(opis))
sprawdz("i jest w nim UCHWYT, nie nazwa", opis.get("komu") == "naval", opis)
sprawdz("nazwa zostaje osobno, pod `publikacja`",
        opis.get("publikacja") == "Naval", opis)

print()
print("=== 2. BRAK UCHWYTU NIE PSUJE WPISU ===")
# Nie kazde zrodlo go oddaje. Puste pole jest uczciwe; wyjatek w srodku
# przebiegu kosztowalby cala reszte doby.
opis2 = run.opis_celu({"pub": "Czyjas Publikacja", "skad": "szukanie",
                       "komentarze": 0, "reakcje": 0, "data": ""})
sprawdz("bez uchwytu pole jest puste, a wpis powstaje",
        opis2.get("komu") == "" and opis2.get("publikacja"), opis2)

print()
print("=== 3. PRAWDZIWA SCIEZKA CELOW NIESIE UCHWYT ===")
# Uchwyt musi byc w SAMYM CELU, inaczej `opis_celu` nie ma go skad wziac.
# Sprawdzamy to prawdziwa funkcja `kanal.posty_z_kanalu` z podstawiona
# odpowiedzia API — nie asercja na tresci zrodla. Asercja „taki napis jest w
# pliku" przechodzi takze wtedy, gdy pole nigdy nie dojezdza do celu, bo np.
# wyzej stoi `continue`; ta oblewa.
ODPOWIEDZ_API = {"posts": [{
    "title": "Jak to dziala",
    "subtitle": "opis",
    "canonical_url": "https://ktos.substack.com/p/jak-to-dziala",
    "publication": {"name": "Life With Machines", "subdomain": "lifewithmachines"},
    "comment_count": 2, "reaction_count": 5,
    "post_date": "2026-08-01T10:00:00.000Z",
}]}


class _Atrapa:
    """Tyle przegladarki, ile `posty_z_kanalu` naprawde dotyka.

    Funkcja sprzata w `finally`: zamyka strone, przegladarke i zatrzymuje
    silnik. Atrapa musi umiec to samo, inaczej test wywala sie na sprzataniu
    i nie dociera do jedynego pytania, ktore zadaje.
    """

    def new_page(self):
        return _Atrapa()

    def close(self):
        pass

    def stop(self):
        pass


_stare = {
    "wymagaj_sesji": kanal.browser.wymagaj_sesji,
    "podlacz_sie": kanal.browser.podlacz_sie,
    "api_json": kanal.browser.api_json,
}
_zdjecie = config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
try:
    kanal.browser.wymagaj_sesji = lambda *a, **k: None
    kanal.browser.podlacz_sie = lambda *a, **k: (_Atrapa(), _Atrapa(), _Atrapa())
    kanal.browser.api_json = lambda *a, **k: ODPOWIEDZ_API
    cele = kanal.posty_z_kanalu(5)
finally:
    for nazwa, funkcja in _stare.items():
        setattr(kanal.browser, nazwa, funkcja)
    config.przywroc_katalog_danych(_zdjecie)

sprawdz("cel w ogole powstal (inaczej reszta sekcji nic nie bada)",
        len(cele) == 1, len(cele))
if cele:
    sprawdz("cel niesie `uchwyt` z pola `subdomain`",
            cele[0].get("uchwyt") == "lifewithmachines", cele[0].get("uchwyt"))
    sprawdz("i osobno nazwe do czytania",
            cele[0].get("pub") == "Life With Machines", cele[0].get("pub"))
    # I DOMKNIECIE LANCUCHA: to, co `kanal` zbudowal, przechodzi przez
    # `opis_celu` do dziennika. Kazde z tych dwoch ogniw dziala osobno —
    # ten warunek sprawdza, ze sa polaczone.
    sprawdz("i dojezdza az do wpisu w dzienniku",
            run.opis_celu(cele[0]).get("komu") == "lifewithmachines",
            run.opis_celu(cele[0]))

print()
print("=== 4. KONTRDOWOD: NAZWA I UCHWYT TO NIE TO SAMO ===")
# Gdyby byly tym samym, cale to rozroznienie byloby ceremonia. Pary wziete z
# produkcyjnego dziennika 3 wrzesnia 2026 — laczenie po nazwie gubi drugiego
# czlowieka z kazdej pary.
PARY_Z_PRODUKCJI = (("Naval", "naval"),
                    ("Chaos Engine", "chaosengine2026"),
                    ("Life With Machines", "lifewithmachines"))
sprawdz("nazwa i uchwyt roznia sie w KAZDEJ parze z produkcji",
        all(nazwa != uchwyt for nazwa, uchwyt in PARY_Z_PRODUKCJI),
        PARY_Z_PRODUKCJI)
# I NAJWAZNIEJSZE: uchwyt jest tym, ktory pasuje do dziennika polubien.
# Tam stoi 'genieai', nie 'Genie AI' — wiec laczyc mozna tylko po uchwycie.
sprawdz("uchwyt jest w ksztalcie, jaki trzymaja polubienia (bez spacji i "
        "wielkich liter)",
        all(u == u.lower() and " " not in u for _, u in PARY_Z_PRODUKCJI),
        [u for _, u in PARY_Z_PRODUKCJI])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
