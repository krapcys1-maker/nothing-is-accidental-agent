Projektuję warstwę pamięci dla autonomicznego agenta i chcę, żebyś ją rozbił, zanim ją wdrożę.

**Kontekst.** Agent prowadzi Substacka o AI. Zapisuje wszystko (dziennik zdarzeń, statystyki każdej publikacji) i nie czyta niczego — nie zmienia zachowania na podstawie własnych wyników.

**Mój projekt.** Trzy warstwy: zdarzenie → oszacowanie → decyzja.

- Nie przechowuję żadnych zdań ani wniosków. Każde oszacowanie liczę od nowa z surowych zapisów przy każdym uruchomieniu. Powód: ten projekt stracił dziewięć dni, bo zapamiętał zdanie „Substack zdjął przycisk Follow", zdanie przestało być prawdą, a system cytował je dalej jako fakt.
- Oszacowanie nigdy nie jest zdaniem, tylko kompletem: wartość, licznik, mianownik, okno czasowe, wiek uwzględnionych wyników, status wiem/nie wiem z powodem, oraz identyfikatory dowodów.
- Zabezpieczenia: świeży wynik nie liczy się przez 3 dni (świeże zero to nie zero), próg 12 obserwacji na wariant, odcięcie danych sprzed zmiany tematyki konta, podłoga eksploracji (wariant z niską wagą i tak dostaje szanse, żeby nie zamknąć pętli zwrotnej).
- Tryb obserwacyjny: liczy i raportuje, nie zmienia żadnej decyzji.
- Stałe redakcyjne nie są hipotezami. Wagi sposobów wypowiedzi są niskie dla „wiecznego korygującego" i „potakiwacza" z powodów redakcyjnych, nie skuteczności. Optymalizator maksymalizujący odpowiedzi nauczyłby się zaczepiać i miałby rację w każdej liczbie osobno.
- Nie kontroluję zmiennych ubocznych (wielkość hosta, pora, wiek wpisu) i raport mówi to wprost.

**Stan faktyczny dziś:** moduł mówi „nie wiem" wszędzie. Użyteczne okno ma cztery dni — od progu dojrzałości do zmiany tematyki konta. Uważam to za poprawną odpowiedź, nie za usterkę.

**Pytania:**

1. Gdzie ten projekt jest źle pomyślany, a nie tylko niekompletny?
2. Czy „przeliczaj, nie przechowuj" to właściwy wybór, czy uciekam przed problemem, który i tak wróci? Kiedy konkretnie ta zasada zawiedzie?
3. Rozważałem gotowe rozwiązanie pamięci dla agentów i odrzuciłem je, bo retain i reflect wołają model, a mój rachunek liczy kod za darmo, przy suficie 40 USD miesięcznie. Czy to fałszywa oszczędność?
4. Próg 12 na wariant i dojrzałość 3 dni wybrałem z rachunku, nie z literatury. Rozbij te liczby.
5. Czego w tym projekcie nie ma, a powinno być — i co z tego dałoby się zrobić bez ani jednego dodatkowego wywołania modelu?

Nie chcę zachęty. Chcę listy miejsc, w których to pęknie.

Poniżej cały moduł, który to realizuje, i blok stałych z konfiguracji, do których się odwołuje.

---

## Załącznik 1 — `agent-v2/oszacowania.py`, cały plik

Gałąź `pamiec/oszacowania`, commit `d7b3fb7`, 442 wiersze.

```python
# -*- coding: utf-8 -*-
"""Warstwa oszacowan: co nasze wlasne zapisy MOWIA, i czego nie mowia.

TRZY WARSTWY, NIE DWIE — zdarzenie, oszacowanie, decyzja.

    zdarzenie     "komentarz 4718 w postawie CIEKAWOSC, 0 odpowiedzi, 9 dni"
    oszacowanie   "CIEKAWOSC: 1 odpowiedz na 13, ale dojrzalych jest 6 przy
                   progu 12 — NIE WIEM"
    decyzja       wagi postaw (dzis: bez zmian, bo tryb obserwacyjny)

Warstwy sa rozdzielone celowo. Oszacowanie NIE steruje niczym samo z siebie;
decyzja moze je zignorowac i przy stalych redakcyjnych ma do tego prawo.

DLACZEGO NIE PRZECHOWUJEMY ZDAN. Ten projekt stracil dziewiec dni, bo
zapamietal zdanie „Substack zdjal przycisk Follow". Zdanie przestalo byc
prawdziwe, a system cytowal je dalej jako fakt — az ktos recznie sprawdzil.
Kazde oszacowanie tutaj liczy sie OD NOWA z surowych zapisow, wiec nowe dane
uniewazniaja wniosek same, bez niczyjej interwencji, i nie ma czego zwietrzec.

CZEGO TO NIE ZNACZY. Nie znaczy, ze oszacowanie nie moze byc falszywe. Rachunek
deterministyczny daje POWTARZALNOSC, nie prawde. Falszywy wniosek nadal wchodzi
tedy:

  - brakujacy identyfikator      -> liczymy i pokazujemy `bez_id`
  - swieze zero                  -> `OSZACOWANIA_DOJRZALOSC_DNI`
  - porownanie roznych wiekow    -> wspolne pasmo wieku dla wszystkich wariantow
  - mala proba                   -> `OSZACOWANIA_MIN_NA_WARIANT`, per wariant
  - zmiana tematyki konta        -> `PRZESTAWIENIE_KONTA` + okno dni
  - petla zwrotna                -> `OSZACOWANIA_PODLOGA_EKSPLORACJI`
  - ZMIENNE UBOCZNE             -> NIE UMIEMY. Patrz nizej.

ZMIENNE UBOCZNE SA NIEZALATANE I TO JEST NAJWAZNIEJSZE ZDANIE W TYM PLIKU.
Komentarz pod duzym kontem dostaje odpowiedz czesciej niz pod malym. Postawy
nie sa losowane rownomiernie po wielkosci hosta, porze ani wieku wpisu. Roznica
miedzy postawami moze wiec byc w calosci roznica miedzy hostami. Nie mamy tylu
danych, zeby to rozdzielic, i dopoki nie mamy, kazde oszacowanie stad jest
RAPORTEM DO PRZECZYTANIA, a nie pilotem.

Uruchamiane samodzielnie wypisuje raport:
    PYTHONIOENCODING=utf-8 python agent-v2/oszacowania.py
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import config
import statystyki

def _dziennik():
    """Sciezka dziennika, czytana PRZY WYWOLANIU, nie przy imporcie.

    Stala modulowa wiazalaby katalog danych w chwili zaladowania modulu, wiec
    testu nie dalo by sie odsunac od produkcji inaczej niz przez przeladowanie
    modulu. `statystyki._plik()` robi to tak samo i z tego samego powodu.
    """
    return config.DATA_DIR / "dziennik.jsonl"

# Wynik, ktorego szukamy. ODPOWIEDZ jest miara pierwsza, bo rozmowa jest tym,
# po co w ogole komentujemy; polubienie to gest, ktory nie wymaga przeczytania.
GLOWNY_WYNIK = "odpowiedzi"


# --------------------------------------------------------------------------
# czytanie surowych zapisow
# --------------------------------------------------------------------------
def wpisy(rodzaj: str | None = None) -> list[dict[str, Any]]:
    """Dziennik, linia po linii. Uszkodzone linie pomija, jak `statystyki`.

    Proces ubity w trakcie zapisu zostawia polowiczna linie — w tym projekcie
    SIGTERM w zwloce przed notkami uszkodzil siedem przebiegow w tydzien. Jedna
    taka linia nie moze skasowac historii wszystkich pozostalych.
    """
    plik = _dziennik()
    if not plik.exists():
        return []
    out = []
    with io.open(plik, encoding="utf-8", errors="replace") as f:
        for linia in f:
            linia = linia.strip()
            if not linia:
                continue
            try:
                w = json.loads(linia)
            except Exception:
                continue
            if not isinstance(w, dict):
                continue
            if rodzaj is None or w.get("rodzaj") == rodzaj:
                out.append(w)
    return out


def _identyfikator(wartosc: Any) -> str:
    """Identyfikator nadajacy sie do POLACZENIA z pomiarem — albo pusty napis.

    `-1` znaczy w tym repozytorium „tresc jest, ale Substack nie podal numeru"
    (patrz `browser.potwierdz_komentarz`). Jako klucz nie polaczy sie z niczym,
    a policzony jako obecny wpadalby do `bez_pomiaru` i wygladal na usterke
    pomiaru zamiast na brak numeru u zrodla.
    """
    tekst = str(wartosc or "").strip()
    return "" if tekst in ("", "-1", "0", "None") else tekst


def _chwila(tekst: Any) -> datetime | None:
    """ISO -> czas z UTC. Cokolwiek innego -> None, bez wyjatku."""
    if not tekst:
        return None
    try:
        d = datetime.fromisoformat(str(tekst).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _wiek_dni(wpis: dict, pomiar: dict | None, teraz: datetime) -> float | None:
    """Ile dni ma TRESC — nie pomiar.

    Wiek liczymy od wystawienia, bo o to chodzi w progu dojrzalosci: pytamy,
    ile czasu swiat mial na reakcje. `wystawione` jest tylko na czesci pomiarow
    (zmierzone 1 wrzesnia 2026: na 22 z 66), wiec zapis dziennika jest
    peloprawnym zrodlem zapasowym, a nie awaryjna prowizorka.
    """
    kiedy = _chwila((pomiar or {}).get("wystawione")) or _chwila(wpis.get("kiedy"))
    if kiedy is None:
        return None
    return (teraz - kiedy).total_seconds() / 86400.0


# --------------------------------------------------------------------------
# oszacowanie: nigdy zdanie, zawsze komplet
# --------------------------------------------------------------------------
def _oszacowanie(pytanie: str, wariant: str, pozycje: list[dict],
                 wynik: str, teraz: datetime) -> dict[str, Any]:
    """Jeden wariant jednego pytania — z licznikiem, mianownikiem i niepewnoscia.

    `pozycje` to juz odsiane, dojrzale obserwacje: kazda ma `pomiar` i `wiek`.
    Zwracany slownik ma ZAWSZE te same klucze, takze gdy odpowiedz brzmi
    „nie wiem" — bo wolajacy nie moze byc zmuszony do zgadywania, czy pole
    istnieje.
    """
    n = len(pozycje)
    licznik = sum(int((p["pomiar"].get(wynik) or 0)) for p in pozycje)
    wieki = sorted(p["wiek"] for p in pozycje)
    ostatnie = max((p["pomiar"].get("kiedy") or "") for p in pozycje) if pozycje else ""
    wiem = n >= config.OSZACOWANIA_MIN_NA_WARIANT
    powod = "" if wiem else (
        "%d dojrzalych obserwacji, prog to %d"
        % (n, config.OSZACOWANIA_MIN_NA_WARIANT))
    return {
        "pytanie": pytanie,
        "wariant": wariant,
        "wynik": wynik,
        "licznik": licznik,
        "mianownik": n,
        "wartosc": (licznik / n) if n else None,
        "okno_dni": config.OSZACOWANIA_OKNO_DNI,
        "dojrzalosc_dni": config.OSZACOWANIA_DOJRZALOSC_DNI,
        "wiek_dni": {
            "min": round(wieki[0], 1) if wieki else None,
            "mediana": round(wieki[len(wieki) // 2], 1) if wieki else None,
            "max": round(wieki[-1], 1) if wieki else None,
        },
        "ostatnie_dane": ostatnie,
        "wiem": wiem,
        "powod": powod,
        "dowody": [str(p["id"]) for p in pozycje[:20]],
    }


def _zbierz(rodzaj: str, klucz_id: str,
            klucz_wariantu: str | Callable[[dict], str],
            pytanie: str, wynik: str = GLOWNY_WYNIK) -> dict[str, Any]:
    """Wspolny rachunek dla kazdego pytania „wariant -> wynik".

    `klucz_wariantu` moze byc nazwa pola ALBO funkcja, ktora wariant wylicza —
    bo nie kazde pytanie ma gotowa kolumne. Pora dnia i host mieszkaja w
    czasie i w adresie, a nie w osobnym polu.

    JEDNA IMPLEMENTACJA, NIE DWIE. Pierwsza wersja miala `hosty()` przepisane
    osobno, z wlasna kopia odsiewu i wlasnym slownikiem strat. Dwie kopie tej
    samej reguly rozjezdzaja sie po cichu, a w tym repozytorium jest to klasa
    bledu z wlasna historia — od dwoch kopii daty przestawienia konta po dwie
    kopie listy rodzajow w audycie.

    Zwraca oszacowania PLUS rachunek strat: ile wpisow odpadlo i dlaczego.
    Rachunek strat jest czescia odpowiedzi, nie przypisem — bez niego
    „CIEKAWOSC 1 na 13" nie mowi, czy trzynascie to duzo, czy resztka po
    odsianiu osiemdziesieciu.
    """
    teraz = datetime.now(timezone.utc)
    pomiary = statystyki.najnowsze_per_pozycja(rodzaj)
    granica = _chwila(config.PRZESTAWIENIE_KONTA)

    straty = {"bez_id": 0, "bez_wariantu": 0, "bez_pomiaru": 0,
              "sprzed_przestawienia": 0, "za_stare": 0, "niedojrzale": 0}
    wg_wariantu: dict[str, list[dict]] = {}

    for w in wpisy(rodzaj):
        ident = _identyfikator(w.get(klucz_id))
        wariant = str((klucz_wariantu(w) if callable(klucz_wariantu)
                       else w.get(klucz_wariantu)) or "")
        if not ident:
            straty["bez_id"] += 1
            continue
        if not wariant:
            straty["bez_wariantu"] += 1
            continue
        pomiar = pomiary.get(ident)
        if pomiar is None:
            straty["bez_pomiaru"] += 1
            continue
        kiedy = _chwila(w.get("kiedy"))
        if granica and kiedy and kiedy < granica:
            straty["sprzed_przestawienia"] += 1
            continue
        wiek = _wiek_dni(w, pomiar, teraz)
        if wiek is None or wiek > config.OSZACOWANIA_OKNO_DNI:
            straty["za_stare"] += 1
            continue
        # PROG DOJRZALOSCI. Zero sprzed godziny nie jest zerem, tylko brakiem
        # odpowiedzi na pytanie, ktorego nikt jeszcze nie uslyszal.
        if wiek < config.OSZACOWANIA_DOJRZALOSC_DNI:
            straty["niedojrzale"] += 1
            continue
        wg_wariantu.setdefault(wariant, []).append(
            {"id": ident, "pomiar": pomiar, "wiek": wiek, "wpis": w})

    oszacowania = [
        _oszacowanie(pytanie, wariant, pozycje, wynik, teraz)
        for wariant, pozycje in sorted(wg_wariantu.items())
    ]
    oszacowania.sort(key=lambda o: (-o["mianownik"], o["wariant"]))
    return {"pytanie": pytanie, "wynik": wynik,
            "oszacowania": oszacowania, "straty": straty}


# --------------------------------------------------------------------------
# pytania, ktore umiemy zadac
# --------------------------------------------------------------------------
def postawy_komentarza() -> dict[str, Any]:
    """Czy postawa komentarza ma zwiazek z tym, czy ktos odpowiada."""
    return _zbierz("komentarz", "nasz_id", "postawa", "postawa -> odpowiedzi")


def typy_notek() -> dict[str, Any]:
    """Czy typ notki ma zwiazek z reakcjami."""
    return _zbierz("notka", "id", "typ", "typ notki -> odpowiedzi")


def formy_notek() -> dict[str, Any]:
    """To samo dla formy. Forma trafia do dziennika dopiero od 1 wrzesnia 2026,
    wiec przez najblizsze tygodnie odpowiedz MA brzmiec „nie wiem" — i to nie
    jest usterka, tylko poprawny opis stanu wiedzy."""
    return _zbierz("notka", "id", "forma", "forma notki -> odpowiedzi")


def _host(wpis: dict) -> str:
    """Jedna nazwa hosta z tego, co dziennik akurat zapisal.

    Cel bywa zapisany jako pelny adres, jako sama domena albo jako uchwyt, a
    trzy zapisy tego samego hosta licza sie jako trzy hosty i kazdy ma za mala
    probe, zeby cokolwiek powiedziec. Ujednolicamy do domeny; czego nie da sie
    ujednolicic, wraca puste i wpada do `bez_wariantu`, gdzie widac ile tego.
    """
    for pole in ("gdzie", "publikacja", "skad"):
        wartosc = str(wpis.get(pole) or "").strip()
        if not wartosc:
            continue
        if "://" in wartosc:
            netloc = urlparse(wartosc).netloc.lower()
            if netloc:
                return netloc.removeprefix("www.")
        if "." in wartosc and " " not in wartosc:
            return wartosc.lower().removeprefix("www.")
    return ""


def hosty() -> dict[str, Any]:
    """Czy sa miejsca, gdzie nikt nigdy nie odpowiada.

    NIE JEST TO BLOKADA I NIE MA NIA BYC. „Nikt nigdy nie odpowiedzial" przy
    czterech probach nie znaczy nic; przy czterdziestu znaczy tyle, ze warto
    poszukac indziej. To sygnal do rankingu, nie wyrok.
    """
    return _zbierz("komentarz", "nasz_id", _host, "host -> odpowiedzi")


# Pory dnia w czterech blokach, nie w dwudziestu czterech. Przebiegow jest
# piec dziennie, wiec przy godzinowych kubelkach kazdy miesci najwyzej jeden
# wpis i zaden nigdy nie dojrzeje. Kubelek, ktory z definicji nie moze uzbierac
# proby, to nie jest ostrozny pomiar, tylko pomiar udawany.
BLOKI_DNIA = ((0, "00-05 noc"), (6, "06-11 rano"),
              (12, "12-17 popoludnie"), (18, "18-23 wieczor"))


def _blok_dnia(wpis: dict) -> str:
    """Ktory blok doby, wedlug czasu UTC z dziennika."""
    kiedy = _chwila(wpis.get("kiedy"))
    if kiedy is None:
        return ""
    etykieta = BLOKI_DNIA[0][1]
    for od, nazwa in BLOKI_DNIA:
        if kiedy.hour >= od:
            etykieta = nazwa
    return etykieta


def pory_dnia() -> dict[str, Any]:
    """Czy pora publikacji notki ma zwiazek z zasiegiem.

    Wynikiem sa WYSWIETLENIA, nie odpowiedzi: notka zbiera odpowiedzi rzadko,
    a wyswietlenia zawsze, wiec przy tej wielkosci konta tylko one maja szanse
    cokolwiek pokazac.

    ZASTRZEZENIE, KTORE ZOSTAJE NIEZALATANE: wyswietlenia zaleza takze od
    tematu, dlugosci i od tego, kto akurat byl online — a pora nie jest
    losowana niezaleznie od tych rzeczy, bo przebiegi stoja o stalych porach
    z 25-minutowym rozmyciem. Roznica miedzy blokami moze wiec byc roznica
    miedzy tym, co w tych blokach pisalismy.
    """
    return _zbierz("notka", "id", _blok_dnia, "pora notki -> wyswietlenia",
                   wynik="wyswietlenia")


def wszystkie() -> list[dict[str, Any]]:
    """Komplet pytan, ktore umiemy dzis zadac wlasnym zapisom."""
    return [postawy_komentarza(), typy_notek(), formy_notek(), hosty(),
            pory_dnia()]


# --------------------------------------------------------------------------
# decyzja: osobna warstwa, ktora ma prawo oszacowanie zignorowac
# --------------------------------------------------------------------------
def wagi_postaw(grupa: dict[str, Any] | None = None) -> dict[str, float]:
    """Wagi postaw po ewentualnej modulacji oszacowaniem.

    DZIS ZWRACA WAGI REDAKCYJNE BEZ ZMIAN, bo `OSZACOWANIA_TRYB_OBSERWACYJNY`
    jest wlaczony. Funkcja istnieje juz teraz, zeby modulacja miala jedno
    miejsce i zeby dalo sie ja przetestowac ZANIM cokolwiek zacznie od niej
    zalezec.

    GDY TRYB ZOSTANIE WYLACZONY, obowiazuja trzy ograniczenia i kazde ma swoj
    powod w historii tego repozytorium:

      1. Modulacja najwyzej o `OSZACOWANIA_MAKS_MODULACJA`, w gore i w dol.
         Wagi NIE MIERZA wylacznie skutecznosci: KOREKTA i ZGODA sa niskie
         dlatego, ze „wieczny korygujacy i potakiwacz to ta sama wada z dwoch
         stron" — to decyzja o tym, czym jest to pismo, a nie hipoteza do
         obalenia liczba odpowiedzi.
      2. Podloga eksploracji. Wariant z mala waga zbiera malo danych i przez to
         nigdy nie odzyska wagi. Petla zamyka sie sama i wyglada przy tym na
         wynik pomiaru.
      3. Wariant, o ktorym oszacowanie mowi „nie wiem", NIE JEST RUSZANY.
         Brak wiedzy to nie jest zly wynik.
    """
    bazowe = {k: float(v[0]) for k, v in config.POSTAWY_KOMENTARZA.items()}
    if config.OSZACOWANIA_TRYB_OBSERWACYJNY:
        return bazowe

    grupa = grupa or postawy_komentarza()
    pewne = [o for o in grupa["oszacowania"]
             if o["wiem"] and o["wartosc"] is not None]
    if len(pewne) < 2:
        return bazowe
    srednia = sum(o["wartosc"] for o in pewne) / len(pewne)
    if srednia <= 0:
        return bazowe

    m = config.OSZACOWANIA_MAKS_MODULACJA
    podloga = config.OSZACOWANIA_PODLOGA_EKSPLORACJI
    out = dict(bazowe)
    for o in pewne:
        nazwa = o["wariant"]
        if nazwa not in out:
            continue
        wzgledne = (o["wartosc"] - srednia) / srednia
        mnoznik = 1.0 + max(-1.0, min(1.0, wzgledne)) * m
        mnoznik = max(podloga, min(1.0 + m, mnoznik))
        out[nazwa] = round(bazowe[nazwa] * mnoznik, 3)
    return out


def migawka(oszacowanie: dict[str, Any]) -> dict[str, Any]:
    """Skrot oszacowania do zapisania PRZY DECYZJI, ktora je wykorzystala.

    Bez tego za miesiac nie da sie ustalic, dlaczego bot wybral akurat te
    postawe: oszacowania nie sa przechowywane, wiec odtworzyc ich sie nie da —
    dane zdazyly sie zmienic. Migawka jest jedynym sladem stanu wiedzy w chwili
    decyzji i dlatego jest maleńka: ma zmiescic sie w linii dziennika.
    """
    return {
        "wariant": oszacowanie.get("wariant"),
        "wartosc": oszacowanie.get("wartosc"),
        "n": oszacowanie.get("mianownik"),
        "wiem": oszacowanie.get("wiem"),
    }


# --------------------------------------------------------------------------
# raport
# --------------------------------------------------------------------------
def raport(grupy: list[dict[str, Any]] | None = None) -> str:
    """Czytelny raport. Pokazuje TAKZE to, czego nie wiemy, i co odpadlo."""
    grupy = grupy if grupy is not None else wszystkie()
    linie: list[str] = []
    tryb = ("OBSERWACYJNY — oszacowania nie zmieniaja zadnej decyzji"
            if config.OSZACOWANIA_TRYB_OBSERWACYJNY else "CZYNNY")
    linie.append("TRYB: %s" % tryb)
    linie.append("progi: dojrzalosc %d dni, okno %d dni, min %d na wariant, "
                 "od %s" % (config.OSZACOWANIA_DOJRZALOSC_DNI,
                            config.OSZACOWANIA_OKNO_DNI,
                            config.OSZACOWANIA_MIN_NA_WARIANT,
                            config.PRZESTAWIENIE_KONTA))
    for g in grupy:
        linie.append("")
        linie.append("=== %s ===" % g["pytanie"].upper())
        if not g["oszacowania"]:
            linie.append("  (nic nie przeszlo przez odsiew)")
        for o in g["oszacowania"]:
            wart = "-" if o["wartosc"] is None else ("%.3f" % o["wartosc"])
            stan = "" if o["wiem"] else "  NIE WIEM (%s)" % o["powod"]
            linie.append(
                "  %-24s %3d/%-3d = %-6s  wiek %s-%s d%s"
                % (o["wariant"][:24], o["licznik"], o["mianownik"], wart,
                   o["wiek_dni"]["min"], o["wiek_dni"]["max"], stan))
        s = g["straty"]
        linie.append("  odpadlo: %s" % ", ".join(
            "%s %d" % (k, v) for k, v in s.items() if v))
    linie.append("")
    linie.append("ZMIENNE UBOCZNE NIEKONTROLOWANE: wielkosc hosta, pora, wiek "
                 "wpisu. Roznica miedzy wariantami moze byc roznica miedzy "
                 "miejscami, w ktorych wypadly.")
    return "\n".join(linie)


if __name__ == "__main__":
    print(raport())
```

## Załącznik 2 — stałe z `agent-v2/config.py`, do których moduł się odwołuje

Ten sam commit. Moduł czyta je jako `config.OSZACOWANIA_*` i `config.PRZESTAWIENIE_KONTA`; bez tego bloku liczby 3 i 12 nie występują w załączniku 1.

```python
# --- warstwa oszacowan (pamiec, ktora nie pamieta zdan) ----------------------
# TRZY WARSTWY, NIE DWIE: zdarzenie -> oszacowanie -> decyzja. Zdarzenie to
# jeden zapisany fakt („komentarz 123 dostal 0 odpowiedzi"). Oszacowanie to
# rachunek z wielu zdarzen, NIOSACY WLASNA NIEPEWNOSC. Decyzja to osobny krok,
# ktory moze oszacowanie ZIGNOROWAC — i przy stalych redakcyjnych ma prawo.
#
# CZEGO TA WARSTWA NIE ROBI I NIE MA ROBIC. Nie zapisuje zdan. Ten projekt
# stracil dziewiec dni, bo zapamietal zdanie „Substack zdjal przycisk Follow",
# zdanie przestalo byc prawdziwe, a system cytowal je dalej jako fakt. Kazde
# oszacowanie liczy sie OD NOWA z surowych zapisow przy kazdym przebiegu, wiec
# nie ma czego zwietrzec. To NIE znaczy, ze oszacowanie nie moze byc falszywe —
# rachunek deterministyczny daje powtarzalnosc, nie prawde. Znaczy tylko, ze
# nowe dane uniewazniaja wniosek same, bez niczyjej interwencji.
#
# CZEGO NIE UMIEMY I MOWIMY TO WPROST: nie kontrolujemy zmiennych ubocznych.
# Komentarz pod duzym kontem dostaje odpowiedz czesciej niz pod malym, a nasze
# postawy nie sa losowane rownomiernie po wielkosci hosta. Roznica miedzy
# postawami moze wiec byc roznica miedzy hostami. Dlatego oszacowanie jest
# RAPORTEM, a nie pilotem.

# Tryb obserwacyjny: oszacowania sa liczone i pokazywane, ale NIE zmieniaja
# zadnej decyzji. Tak ma zostac, dopoki proby nie dojrzeja. Zmierzone
# 1 wrzesnia 2026 na produkcji: 54 komentarze daly sie polaczyc z postawa,
# a odpowiedzi bylo TRZY (MECHANIZM 1/14, CIEKAWOSC 1/13, PYTANIE 1/8).
# Przy takich liczbach kazde „ta postawa dziala lepiej" jest szumem.
OSZACOWANIA_TRYB_OBSERWACYJNY = True

# Ile dni tresc musi miec, zanim jej wynik cokolwiek znaczy. Komentarz sprzed
# godziny z zerem odpowiedzi NIE jest dowodem, ze postawa nie dziala — jest
# dowodem, ze nikt jeszcze nie zdazyl odpowiedziec. Bez tego progu swieze
# zera zalewaja rachunek i kazda postawa wyglada na martwa.
OSZACOWANIA_DOJRZALOSC_DNI = 3

# Najstarsze dane, ktore jeszcze biora udzial. Konto zmienilo tematyke
# 25 sierpnia 2026 i pomiary sprzed tej daty opisuja inna publikacje;
# `PRZESTAWIENIE_KONTA` odcina je twardo, a to okno odcina dodatkowo wszystko,
# co po prostu za stare.
OSZACOWANIA_OKNO_DNI = 60

# Ile DOJRZALYCH obserwacji musi miec pojedynczy wariant, zeby wolno bylo o nim
# powiedziec cokolwiek poza „nie wiem". Prog dotyczy KAZDEGO wariantu osobno,
# nie sumy: dwanascie komentarzy razem i jeden na postawe to nadal nic.
OSZACOWANIA_MIN_NA_WARIANT = 12

# O ile najwyzej wolno oszacowaniu ruszyc wage redakcyjna, gdy tryb
# obserwacyjny zostanie kiedys wylaczony. Polowa w gore, polowa w dol i ani
# kroku dalej, BO WAGI NIE MIERZA WYLACZNIE SKUTECZNOSCI. `POSTAWY_KOMENTARZA`
# trzyma KOREKTE i ZGODE nisko dlatego, ze „wieczny korygujacy i potakiwacz to
# ta sama wada z dwoch stron" — to jest decyzja o tym, czym jest to pismo.
# Optymalizator puszczony luzem nauczylby sie zaczepiac, bo zaczepka zbiera
# odpowiedzi, i mialby racje w kazdej liczbie osobno.
OSZACOWANIA_MAKS_MODULACJA = 0.5

# Podloga eksploracji. Wariant oceniony zle dostaje mniej okazji, wiec zbiera
# mniej danych, wiec nigdy nie odzyska wagi — petla, ktora zamyka sie sama i
# wyglada przy tym na wynik pomiaru. Zaden wariant nie schodzi ponizej tego
# ulamka swojej wagi redakcyjnej.
OSZACOWANIA_PODLOGA_EKSPLORACJI = 0.35

# Dzien, w ktorym konto przestalo pisac o czym innym i zaczelo o AI. Pomiary
# sprzed tej daty dotycza innej publikacji i innych czytelnikow.
#
# JEDNA KOPIA, NIE DWIE. Ta data stala dotad wylacznie w `audyt_systemu.PIVOT`,
# czyli w skrypcie audytowym — a od dzis potrzebuje jej takze kod chodzacy w
# kazdym przebiegu. Dwie kopie tej samej daty rozjezdzaja sie po cichu i to
# jest w tym repozytorium klasa bledu z wlasna historia.
PRZESTAWIENIE_KONTA = "2026-08-25"
```
