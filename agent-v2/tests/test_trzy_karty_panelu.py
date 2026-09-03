# -*- coding: utf-8 -*-
"""Trzy karty panelu notki, ktorych nie czytalismy — a byly tam od zawsze.

CO ZMIERZONO. Audyt segmentu statystyk, 3 wrzesnia 2026: przeszedlem zywym
API przez WSZYSTKIE 159 pozycji z pomiarem i policzylem, ktore karty panel
w ogole oddaje:

    note               159        czytana
    surfaces            95        czytana
    audience            95        czytana
    interactions        77        czytana
    impressions         63        czytana TYLKO jako suma
    impressionValues    32        czytana
    new_subscribers      4        NIE CZYTANA
    shareValues          2        NIE CZYTANA

`new_subscribers` bylo najdrozszym przeoczeniem. Karta niesie liczbe nowych
subskrybentow przypisanych DO TEJ POZYCJI, razem z imionami. Zmierzone:

    notka     323761132   2 zapisy   sidharth chandra, Leonard
    odpowiedz 320809275   1 zapis    Camli Travel Notes
    notka     322556153   1 zapis    Faisal Shahzad Naeem
    notka     322757850   1 zapis    William Short

Te same liczby podaje NIEZALEZNIE panel zrodel ruchu
(`/api/v1/publication/stats/growth/sources`) — ale tylko ta karta podaje, KTO.
Do tego dnia raport twierdzil, ze notki nie przynosza nikogo, bo czytal pole
`subskrypcje`, ktorego dla notki nie ma wcale.

`impressions` bylo czytane tylko jako LICZBA ZBIORCZA, a niesie godzinowy
przebieg z pierwszych 48 godzin w DWOCH seriach: „This note" i „Your average".
Panel sam podaje wzorzec konta, czyli odpowiada na jedyne pytanie, ktore cos
zmienia: czy ta pozycja byla lepsza od naszej zwyklej.

KSZTALT PROBEK JEST Z ZYWEGO API, przepisany z odpowiedzi dla notki
323761132 — nie wymyslony. Same funkcje sa czyste (slownik na wejsciu,
slownik na wyjsciu), wiec caly ten test chodzi bez sieci i bez sesji.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_trzy_karty_panelu.py
"""
import sys

sys.path.insert(0, "agent-v2")
import statystyki   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# ---------------------------------------------------------------- probki
NOWI = {
    "type": "userCard", "cardId": "new_subscribers",
    "explainer": {"title": "New subscribers"},
    "headers": [{"title": "New paid subs", "valueType": "number", "value": 0},
                {"title": "New free subs", "valueType": "number", "value": 2}],
    "userLists": [{"label": "Paid", "users": [], "numberNotShown": 0},
                  {"label": "Free", "users": [
                      {"id": 300318015, "name": "sidharth chandra", "bio": ""},
                      {"id": 300318016, "name": "Leonard", "bio": ""}]}],
}
UDOSTEPNIENIA = {"type": "valueCard", "cardId": "shareValues",
                 "headers": [{"title": "Shares", "valueType": "number",
                              "value": 2}]}


def krzywa(nasze, wzorzec):
    """Karta `impressions` o ksztalcie z zywego API. Wartosci NARASTAJACE."""
    def seria(etykieta, wartosci, pierwsza):
        return {"label": etykieta, "isPrimary": pierwsza,
                "values": [{"timestamp": t, "value": v} for t, v in wartosci]}
    return {"type": "graphCard", "cardId": "impressions",
            "graphData": {"type": "line",
                          "xAxis": {"startLabel": "First 48 hours"},
                          "series": [seria("This note", nasze, True),
                                     seria("Your average", wzorzec, False)]}}


GODZINY = ["2026-08-27T13:00:00.000Z",   # zero
           "2026-08-27T20:00:00.000Z",   # +7 h
           "2026-08-28T12:00:00.000Z",   # +23 h  <- ostatni w oknie 24 h
           "2026-08-28T15:00:00.000Z",   # +26 h
           "2026-08-29T12:00:00.000Z"]   # +47 h  <- ostatni w oknie 48 h


def dane_z(*karty):
    return {"lastUpdatedAt": "2026-09-03T15:00:00Z", "cards": list(karty)}


try:
    print("=== 1. KTO SIE ZAPISAL Z TEJ POZYCJI ===")
    r = statystyki.z_kart(dane_z(NOWI))
    sprawdz("liczba darmowych zapisow", r.get("zapisy_darmowe") == 2,
            r.get("zapisy_darmowe"))
    sprawdz("liczba platnych zapisow", r.get("zapisy_platne") == 0,
            r.get("zapisy_platne"))
    # DWA NAGLOWKI, NIE JEDEN. `_suma` bierze z naglowkow tylko PIERWSZY, wiec
    # dla tej karty oddawalaby zero („New paid subs") i wygladalo by to na
    # brak zapisow — czyli na odpowiedz, a nie na pominiecie.
    sprawdz("KONTRDOWOD: `_suma` czyta z tej karty tylko pierwszy naglowek",
            statystyki._suma(NOWI) == 0, statystyki._suma(NOWI))
    sprawdz("imiona ludzi, nie tylko liczba",
            r.get("kto_sie_zapisal") == ["sidharth chandra", "Leonard"],
            r.get("kto_sie_zapisal"))
    # Pozycja bez tej karty ma zera i pusta liste, a nie brak pola: raport ma
    # odrozniac „nikt sie nie zapisal" od „nie ma czego czytac".
    puste = statystyki.z_kart(dane_z(UDOSTEPNIENIA))
    sprawdz("bez karty: zera i pusta lista, ale pola SA",
            puste.get("zapisy_darmowe") == 0
            and puste.get("kto_sie_zapisal") == [],
            (puste.get("zapisy_darmowe"), puste.get("kto_sie_zapisal")))

    print()
    print("=== 2. UDOSTEPNIENIA ===")
    r = statystyki.z_kart(dane_z(UDOSTEPNIENIA))
    sprawdz("liczba udostepnien", r.get("udostepnienia") == 2,
            r.get("udostepnienia"))
    sprawdz("bez karty zostaje zero",
            statystyki.z_kart(dane_z(NOWI)).get("udostepnienia") == 0)

    print()
    print("=== 3. KRZYWA Z PIERWSZYCH 48 GODZIN I WZORZEC KONTA ===")
    nasze = list(zip(GODZINY, [3, 12, 40, 45, 60]))
    wzor = list(zip(GODZINY, [2, 8, 20, 22, 25]))
    r = statystyki.z_kart(dane_z(krzywa(nasze, wzor)))
    # OKNO JEST DOMKNIETE OD GORY: +23 h wchodzi, +26 h nie.
    sprawdz("nasze wejscia po 24 h to ostatni punkt W OKNIE (40, nie 45)",
            r.get("nasza_po_24h") == 40, r.get("nasza_po_24h"))
    sprawdz("i po 48 h (60)", r.get("nasza_po_48h") == 60, r.get("nasza_po_48h"))
    sprawdz("wzorzec konta po 24 h (20)", r.get("wzorzec_po_24h") == 20,
            r.get("wzorzec_po_24h"))
    sprawdz("iloraz: dwa razy lepiej niz zwykle",
            r.get("nad_wzorcem_24h") == 2.0, r.get("nad_wzorcem_24h"))
    # POZYCJA SLABSZA OD WZORCA MA POKAZAC LICZBE PONIZEJ JEDNEGO, a nie
    # zniknac z tabeli — inaczej przeglad widzi same sukcesy.
    slaba = statystyki.z_kart(dane_z(krzywa(
        list(zip(GODZINY, [1, 2, 5, 5, 6])), wzor)))
    sprawdz("pozycja slabsza od wzorca daje iloraz < 1",
            0 < slaba.get("nad_wzorcem_24h", 0) < 1,
            slaba.get("nad_wzorcem_24h"))
    # BRAK KRZYWEJ NIE MOZE UDAWAC ZERA. Panel oddaje ja przy 63 z 159 pozycji.
    bez = statystyki.z_kart(dane_z(UDOSTEPNIENIA))
    sprawdz("bez krzywej pol z niej NIE MA (a nie sa zerami)",
            "nasza_po_24h" not in bez and "nad_wzorcem_24h" not in bez,
            sorted(k for k in bez if "po_24h" in k or "wzorc" in k))
    # A wzorzec rowny zeru nie moze dzielic.
    zerowy = statystyki.z_kart(dane_z(krzywa(
        list(zip(GODZINY, [1, 2, 5, 5, 6])),
        list(zip(GODZINY, [0, 0, 0, 0, 0])))))
    sprawdz("wzorzec zerowy nie wywala dzielenia",
            "nad_wzorcem_24h" not in zerowy, zerowy.get("nad_wzorcem_24h"))

    print()
    print("=== 4. STARE POLA NIE ZNIKNELY ===")
    # Trzy nowe czytelniki dopisuja, a nie podmieniaja. Gdyby cokolwiek
    # nadpisaly, caly dotychczasowy pomiar stalby sie nieporownywalny.
    r = statystyki.z_kart(dane_z(NOWI, UDOSTEPNIENIA, krzywa(nasze, wzor)))
    for pole in ("wyswietlenia", "powierzchnie", "odbiorcy", "interakcje",
                 "interakcje_razem", "polubienia", "odpowiedzi", "restacki",
                 "zmierzone", "ma_karty_zasiegu"):
        sprawdz("pole `%s` nadal jest" % pole, pole in r, sorted(r))

finally:
    pass

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
