# Pomiar i eksperymenty — jak wiedzieć, co zadziałało (27.09.2026)

Polecenie właściciela z 27.09:

> „pomyśl jeszcze, jak to wszystko wdrożymy, jak robić z tego statystyki, jak
> mierzyć skuteczność i jak coś będziemy zmieniać, żeby wiedzieć, co przyniosło
> skutek, a co nie, i co warto później przenieść do NIA"

## Punkt wyjścia — zmierzone 27.09 (`robocze/moc_pomiaru.py`)

- **Ok. 3 notki na dobę** (średnio 2,7 z ostatnich 14 dni).
- **Po 72 h** notka ma medianę 19 wyświetleń (średnio 24, maksimum 250), 2,9
  polubienia, 0,4 odpowiedzi, 0,1 restacka i 0,4 odwiedziny profilu. 72 ze 105
  notek nie ma ani jednej odwiedziny.
- **Zasięg spada w tle.** Średnia geometryczna wyświetleń w tygodniach 35–39:
  26,5 → 24,6 → 19,0 → 11,1 → 12,2, czyli −55% w miesiąc. Każde „przed i po"
  pokaże więc pogorszenie, niezależnie od tego, co zmieniliśmy.
- **Zmienność:** odchylenie standardowe logarytmu wyświetleń wynosi 0,55.
- **Konto:** 27 subskrybentów i 40 obserwujących.
- **26–27.09 weszło naraz kilka zmian** (E6 tematy, E7 świeżość i źródła, E8
  radar i śledztwo, E9 wniosek). „Przed i po" ich nie rozdzieli.
- **Nowe narzędzie na historii** (`eksperymenty.py`, zasięg względem tła
  tygodnia): żadna cecha — model, forma, typ notki — nie ma wykrywalnego
  wpływu. Przy tej liczbie notek wykrylibyśmy dopiero efekty rzędu +35–60%.
  Surowe średnie wskazywały „lepsze" stare notki (×1,95), ale to był sierpień,
  kiedy zasięg był dwa razy wyższy, a nie efekt zmian.

## Trzy warstwy dowodu

| warstwa | co mówi | tempo | czym |
|---|---|---|---|
| 1. **Jakość** | czy tekst jest lepszy według rubryki właściciela (mocny temat, niesztandarowy wniosek, prosto, uczciwie) | godziny | ślepi sędziowie z dwóch rodzin z materiałem źródłowym + miary z kodu |
| 2. **Odbiór** | czy czytelnicy reagują inaczej | tygodnie | eksperyment przeplatany na notkach; miara decyzji: wyświetlenia po 72 h **względem tła tygodnia** |
| 3. **Wzrost** | czy konto rośnie | miesiące | subskrybenci, obserwujący, zapisy przypisane przez Substack konkretnym treściom |

Warstwa 1 **nie przewiduje zasięgu**: na 105 notkach z historii zgodność
sędziów z zasięgiem wyniosła Spearman ≤ 0,09 (`docs/WNIOSEK_2026-09-27.md`).
Dlatego rozstrzyga, jak pisać, ale nie obiecuje wzrostu. Warstwa 3 jest tą,
która się naprawdę liczy, ale jest za rzadka, żeby przypisać ją drobnej zmianie
w notkach. Służy do oceny dużych zakładów: śledztw, artykułów, restacków.

## Ile notek trzeba (moc 80%, błąd 5%)

| efekt do wykrycia | notek na ramię | przy 3 notkach/dobę, podział 50/50 |
|---|---|---|
| +100% | 10 | ok. 1 tydzień |
| +50% | 29 | ok. 3 tygodnie |
| +25% | 95 | ok. 2 miesiące |
| +15% | 241 | ok. 5 miesięcy |

**Wniosek:** na zasięgu testujemy tylko duże dźwignie i jedną naraz. Drobne
poprawki (sformułowanie w prompcie, forma) rozstrzyga warstwa 1 plus strażnicy
— udawanie, że zasięg je rozstrzygnie, byłoby czytaniem szumu.

## Co jest już wdrożone (27.09)

- **Dziennik notki** ma `wersja` (commit, który ją napisał) i `eksperymenty`
  (ramię eksperymentu przeplatanego) obok tego, co już było: `typ`, `forma`,
  `styk`, `model`, `radar`, `glebia`, `koncowka_ocena`, `wniosek`,
  `przeslanie_id`, `zrodlo_data`.
- **`config.EKSPERYMENTY`** — przełącznik przeplatany, np. `{"wniosek": 0.7}`.
  Pusto oznacza, że nic się nie zmienia (tak jest teraz). Przydział jest
  deterministyczny z dnia i numeru miejsca notki w dobie (`stages.ramie`), więc
  obie grupy dzielą te same dni, godziny i ten sam trend. Obsługiwane: `wniosek`.
- **`agent-v2/eksperymenty.py --pole <pole>`** — grupy notek, każda porównana
  z grupą odniesienia:
  - zasięg względem tła (mediana innych notek z ±7 dni),
  - 95% przedział (bootstrap), werdykt: lepiej / gorzej / brak dowodu (razem
    z efektem, który przy tej liczbie notek dałoby się wykryć) / za mało danych,
  - ostrzeżenie, gdy grupy pochodzą z różnych okresów.

  Przykłady: `--pole eksperyment:wniosek`, `--pole wniosek`, `--pole przeslanie`,
  `--pole wersja`, `--pole forma`.
- **`karta_wynikow.py`** (co poniedziałek) — odbiór grup: radar, karta głębi,
  końcówka, wniosek/przesłanie, spoza branży/branża, koszt, zdrowie źródeł.

## Zasady zmian — żeby wiedzieć, co zadziałało

1. **Każda zmiana dostaje numer w rejestrze** (E…): co i po co, hipoteza,
   miara, projekt (przeplatany / jakość / przed-po), ile notek, data i reguła
   decyzji. Rejestr: `docs/POLIGON_I_PRODUKCJA.md` (lokalnie).
2. **Jedna dźwignia naraz** w eksperymencie zasięgu. Niezależne dźwignie mogą
   iść równolegle tylko wtedy, gdy każda ma własne przeplatanie (osobny klucz
   w `EKSPERYMENTY` = osobne losowanie).
3. **Po dużym wdrożeniu dwa tygodnie zamrożenia** tej samej dźwigni — poza
   naprawami błędów.
4. **Reguła decyzji ustalona z góry**, na zasięgu względem tła, po zaplanowanej
   liczbie notek:
   - **wygrana:** dolna granica przedziału > 1,0, a zaangażowanie nie gorsze;
   - **bez szkody:** dolna granica > 0,9 — zostawiamy, jeśli za zmianą
     przemawia jakość (warstwa 1) albo koszt;
   - **szkoda:** górna granica < 1,0 — cofamy;
   - **za mało danych:** mierzymy dalej, do zaplanowanej liczby notek.

   Nie kończymy wcześniej, bo „wygląda dobrze". Codzienne podglądanie mnoży
   fałszywe alarmy — przy 95% i tak co dwudzieste porównanie bez żadnego
   efektu wychodzi „lepiej" albo „gorzej" (test tego narzędzia to pokazał).
5. **Strażnicy przy każdej zmianie:**
   - obalone fakty i naprawy weryfikatora, odmowy dostawcy,
   - końcówka oceniająca materiał, długość,
   - koszt na notkę i na dobę, zdrowie źródeł.
6. **Wyniki neutralne i ujemne zapisujemy tak samo jak dodatnie** (`docs/`).
   Lista „nie pomogło" jest równie cenna jak „pomogło".
7. **Wdrożenie zmiany** idzie tą samą drogą co 27.09:
   1. gałąź;
   2. A/B lub żywy test na kopii danych (tryb test);
   3. pełne testy na czystej kopii serwera (`robocze/testy_serwer.sh`, porównanie z bazą);
   4. `main` i GitHub;
   5. `bash agent-v2/wdroz.sh` (cofnięcie jednym poleceniem);
   6. ślad z pierwszego przebiegu produkcji;
   7. wpis w rejestrze.

## Kalendarz

- **28.09–11.10 — zamrożenie potoku notek** (tylko naprawy). Zbieramy tło pod
  nowy system. Pierwsze przesłania ze śledztwa wychodzą 28–30.09.
- **ok. 13.10** — decyzja E6 (tematy spoza branży), zaplanowana wcześniej.
- **Pierwszy eksperyment przeplatany — do decyzji właściciela:** wniosek
  70/30 przez 4 tygodnie. Daje ok. 84 notki (59 z wnioskiem, 25 bez) i wykrywa
  różnicę rzędu ±45%.
  - Dlaczego wniosek: to największa zmiana w pisaniu, jest tania, sędziowie
    są za nim, a jego wpływ na zasięg jest nieznany.
  - Cena tej wiedzy: 30% notek przez 4 tygodnie idzie bez wniosku.
  - Włączenie: `EKSPERYMENTY = {"wniosek": 0.7}` w `config.py`.
- **ok. 25.10 — ocena E8/E9:**
  - przesłania kontra zwykłe notki (`--pole przeslanie`),
  - artykuły ze śledztw (zapisy przypisane, wyświetlenia),
  - koszt i odsetek odmów dostawcy.
- **Co tydzień:** karta wyników i `eksperymenty.py` dla trwających eksperymentów.

## Śledztwa — co mierzyć

- **Przesłania:** grupa „przeslanie" w karcie i w `eksperymenty.py`. To ok. 6
  notek tygodniowo, więc po 4 tygodniach zobaczymy tylko duże różnice.
- **Artykuły ze śledztw kontra z puli:** zapisy przypisane przez Substack
  (`zrodla.jsonl`, `zapisy_per_notka`) i wyświetlenia. To ok. 1 artykuł
  tygodniowo, więc ocena dopiero po ok. 2 miesiącach.
- **Koszt śledztwa i odmowy dostawcy:** pierwsze śledztwo kosztowało 0,17 USD,
  a artykuł został odrzucony w kategorii „cyber".

## Drugie konto

Co i kiedy przenosić na drugie konto, zapisuje lokalny rejestr
(`docs/POLIGON_I_PRODUKCJA.md`, poza repozytorium). Zasada: najpierw naprawy
błędów i warstwa pomiaru, zmiany treści dopiero po dowodzie z tego konta.
