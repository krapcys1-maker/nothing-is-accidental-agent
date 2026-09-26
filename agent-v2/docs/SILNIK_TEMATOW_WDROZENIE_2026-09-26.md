# Silnik tematów — wdrożenie na poligonie (eksperyment E6), 26.09.2026

Plan: `WYBOR_TEMATOW_2026-09-26.md` (diagnoza i kroki) i `SILNIK_TEMATOW_2026-09-26.md`
(badania). Ten plik mówi, co z planu weszło do kodu, czym się od niego różni, jaki
był stan przed zmianą i jak rozstrzygniemy, czy zostaje. Konto: Nothing Is Accidental
(poligon). Do NIA zmiana trafia dopiero po rozstrzygnięciu.

## Pomiar przed zmianą (produkcja `96e41ae`, 26.09, 17:27 UTC)

Zmierzone z serwera skryptem `pomiary/zrodla_ludzie.py` (zero wywołań modelu, zero
zapisów). Pełny wydruk: `robocze/krok0_przed_2026-09-26.txt` na komputerze właściciela.

- **Spiżarnia:** 8 tekstów z 7 źródeł, z tego **7 branżowych** (Latent Space ×2,
  DeepMind, HuggingFace, Epoch AI, Google Research, PyTorch) i jeden o prawie
  (Transformer). Połowa z 30 wpisów, z których wybierała (15), to YouTube, którego
  spiżarnia w ogóle nie czyta. Diagnoza raportu potwierdzona: o temacie decydował kod.
- **Koszt wyboru tematu, 30 dni, produkcja:** 5,54 USD z 35,07 USD rachunku (16%):
  `curiosity` 3,79 USD w 77 wywołaniach, `bank` 1,13, `parowanie` 0,57, `powtorka`
  0,05. Raport szacował 1–2 USD miesięcznie; prawdziwa liczba jest około trzy razy
  wyższa, głównie przez liczbę wywołań skauta (2,6 na dobę, nie jedno).

## Źródła o ludziach — sprawdzone z serwera, nie z wyszukiwarki

| źródło | styk | wpisy o AI z 30 dni | decyzja |
|---|---|---|---|
| CourtListener (orzeczenia o AI) | prawo | 17 z 17 | wchodzi, bez filtra AI |
| EdSurge | szkola | 12 z 21 | wchodzi |
| Rest of World | z tytułu, domyślnie branza | 9 z 12 | wchodzi |
| Pew Research | codziennosc | 8 z 90 | wchodzi |
| EFF | prawo | 13 z 34 | wchodzi |
| 404 Media | z tytułu, domyślnie codziennosc | 7 z 15 | wchodzi |
| KFF Health News | zdrowie | 1 z 10 | wchodzi (jedyne o zdrowiu) |
| The 74 | szkola | 1 z 25 | wchodzi |
| FTC, ochrona konsumenta | pieniadze | 1 z 11 | wchodzi (jedyne o pieniądzach) |
| arXiv cs.CY, cs.HC | z tytułu, domyślnie ludzie | 0 — sobota | wchodzi warunkowo; pusty w tygodniu → wypada |
| NBER | praca | 404 / nieczytelny XML | odrzucone |
| FDA, lista urządzeń | zdrowie | 401 | odrzucone |
| Tech Policy Press | prawo | zero wpisów | odrzucone |
| SEC | pieniadze | 1 z 16, wymaga adresu kontaktowego | odrzucone |
| FTC, komunikaty | pieniadze | 0 z 10 | odrzucone |
| Federal Register (API) | prawo | 27 dokumentów | to API, nie feed — osobny krok |
| Baza orzeczeń Charlotina (CSV) | prawo | plik jest | etap 2 raportu |

Oznaczone stykiem, choć były w korpusie od dawna: Wpadki AI → szkody, Komisja UE → prawo,
Transformer → prawo.

## Co weszło do kodu

1. **Źródła i styk źródła** — `korpus_kanalow.ZRODLA_LUDZIE`, `STYK_ZRODLA`,
   `STYK_Z_TYTULU` z `MAPA_STYKU`, `styk_wpisu`. Każdy wpis korpusu niesie `styk`.
   Feedy ogólne przechodzą przez filtr AI (ten sam wzorzec co w pomiarze, plus
   „A.I.” z kropkami, które tamten gubił).
2. **Spiżarnia z kwotą** — `tresc_zrodel.tresci_zrodel`: z całego korpusu (200 wpisów,
   nie z 30 pierwszych), najpierw po jednym tekście z każdego źródła o ludziach
   (różne styki, a styki nieobecne w banku od 3 dni na początku), potem najwyżej
   2 branżowe, na końcu dopełnienie. Branża przekracza 2 tylko wtedy, gdy o ludziach
   nie ma materiału. Każdy blok w prompcie ma linię `Touchpoint:`. Skład spiżarni
   trafia do logu przy każdym pobraniu (`[spizarnia] ...`).
3. **Styk faktu ze źródła** — `stages.styk_ze_zrodla`: po adresie tekstu spiżarni,
   potem po hoście, potem po hoście feedu z rejestru; bez dopasowania `branza`.
   Zapis w banku: `styk`, `styk_skad`. To księgowość, nie dowód: pisarz go nie dostaje.
4. **Kwota** — `stages.wez_kandydatow`: dopóki dziś nie wyszła notka spoza branży
   (dziennik, `dzis_notka_spoza_branzy`), najlepszy fakt z innym stykiem idzie
   pierwszy. Wyłącznik: `config.KWOTA_SPOZA_BRANZY`.
5. **Miara** — `statystyki.wynik_odbioru` = 100 × (odwiedziny profilu + 5 × zapisy
   przypisane) / wyświetlenia, po 72 h. Zapisy z przypisania Substacka
   (`zrodla.jsonl`). Sędzia banku (`co_zadzialalo`) dostaje tabelę po stykach zamiast
   listy notek mierzonych polubieniami; restacki wypadają. Karta wyników ma trzy nowe
   wiersze: odbiór notek spoza branży, branżowych i sprzed E6.
6. **Styk w dzienniku notki** — `notki_dnia` → `run.py` → `browser.wystaw_notke`.
7. **Prompty** — `notka.md` (czytelnik, który używa AI, otwarcie od samej rzeczy,
   skutek dla czytelnika tylko gdy dowód go pokazuje), `ciekawostki.md` i `bank.md`
   (cztery pytania oceny; styk ustawia kod).
8. **Przyrząd** — `tests/platne/proba_tematow.py` czyści spiżarnię przed każdą próbą
   i wypisuje jej skład, to, czy szukanie było włączone, i udział faktów spoza branży.

## Czym różni się od planów i dlaczego

- **Styk nadaje kod ze źródła, nie model z cytatem.** Tak mówi `WYBOR_TEMATOW` i tak
  robi `z_kanalu`: deklarację trzeba by sprawdzać, a kod i tak zna źródło. Wersja
  z cytatem (z `SILNIK_TEMATOW`) sprawdzała tylko, czy zdanie stoi w materiale, a nie
  co znaczy — „faktura API” przeszłaby jako pieniądze.
- **Bez limitu „2 fakty z hosta” przy zapisie.** Wyrzucałby opłacone fakty (8.09:
  24 z 35), a różnorodność daje już kwota spiżarni i jeden fakt z hosta na partię
  przy wyborze (`wez_kandydatow`).
- **Rest of World nie jest z góry „pracą”.** We wrześniu pisze głównie o wyścigu
  AI z Chinami; styk bierze z tytułu, domyślnie branża.
- **Ars Technica AI i MIT Technology Review nie weszły** — to prasa o branży;
  zawyżałyby udział „spoza branży”.

## Jak rozstrzygniemy (progi zapisane z góry)

| kiedy | co | próg |
|---|---|---|
| zaraz po wdrożeniu, 0 USD | skład spiżarni z logu przebiegu | najwyżej 2 branżowe na 8, co najmniej 4 o ludziach |
| opcjonalnie, ok. 0,1–0,2 USD | `proba_tematow.py --live --ile 5` | co najmniej 50% faktów spoza branży |
| 14 dni, dziennik | notki spoza branży | co najmniej 1 z 3 dziennie |
| 14 dni, `karta_wynikow.py` co tydzień | odbiór 72 h: spoza branży wobec branży | spoza branży nie gorsze; całe konto nie gorsze niż przed |

**Uwaga o E0 (nowy głos od 25.09).** Porównanie przed/po całego konta miesza E6 z E0.
Porównanie w obrębie tego samego okresu — notki spoza branży wobec branżowych — nie
jest zakłócone, bo obie grupy mają ten sam głos i tego samego pisarza. Na nim stoi
decyzja.

Przy trzech notkach dziennie 14 dni to około 42 notek, z tego około 14 spoza branży:
wykryjemy dużą różnicę (dwukrotną), nie małą. Decyzja około 13.10 (14 dni i 72 h
dojrzewania): zostaje, cofamy albo kolejne 2 tygodnie.

## Czego jeszcze nie ma

- Federal Register przez API z filtrem AI (27 dokumentów w 30 dni) — potrzebny adapter.
- Etap 2 raportu: tygodniowe różnice w bazie orzeczeń Charlotina, na liście FDA, w BTOS.
- Etap 3: Wikipedia i GDELT jako flaga popytu.
- Bandyta na stykach (próbkowanie Thompsona) — po dwóch tygodniach danych.
- Szkielety notek (Ekran, Rachunek, Twoje życie, Rozwiązanie, Ciąg dalszy).
- CourtListener: `przetworz` odrzuca tytuły krótsze niż 4 słowa, więc orzeczenia
  z dwiema stronami („Cervantes v. Bianco”) nie wejdą — wchodzą tylko dłuższe nazwy.
