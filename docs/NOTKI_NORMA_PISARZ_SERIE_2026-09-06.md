# Trzy pytania o notki — pomiar z 6 września 2026

Wszystko liczone na żywej bazie serwera (`agent-v2/data/agent-v2.db`) i na
dzienniku produkcji. Daty publikacji notek wzięte z logu systemd, bo dziennik
**nie zapisuje numeru notki przy publikacji**, a pole `kiedy` w statystykach to
czas POMIARU, nie wydania.

## 1. Czy podwojenie normy (5 → 10) coś dało — ZA WCZEŚNIE

Zmiana weszła 3 września. Pierwszy odczyt wyglądał źle: 32,1 → 15,2 wyświetleń
na notkę. **To był artefakt świeżości**, nie wynik. Notka potrzebuje trzech dni:

| wiek notki | notek | średnio wyświetleń |
|---|---|---|
| 1 dzień | 7 | 7,1 |
| 2 dni | 1 | 19,0 |
| 3 dni | 4 | 28,5 |
| 6 dni | 5 | 54,0 |
| 7 dni | 19 | 28,2 |

Po odsianiu notek młodszych niż dwa dni zostaje **pięć sztuk** z okresu po
zmianie. Na pięciu notkach nie orzeka się niczego.

    PRZED (norma 5)   30 notek / 10 dób   32,1 wyśw./notkę   96,3 wyśw./dobę
    PO   (norma 10)    5 notek /  2 doby  26,6 wyśw./notkę   66,5 wyśw./dobę

**Wniosek: odpowiedź dopiero za tydzień–dwa.** To jedenasty raz w tej serii
prac, gdy okno pomiaru było węższe niż potrzeba — tym razem złapane przed
ogłoszeniem wyniku, a nie po.

## 2. Opus czy DeepSeek — NA ZASIĘGU RÓŻNICY NIE WIDAĆ, CENA 3,5×

Od 3 września produkcja pisze notki **naprzemiennie dwoma modelami**. Podział
jest celowy i dobrze zbudowany (`stages.py:4516`): parzystość przesuwa się co
dobę, żeby pisarz nie przywiązał się na stałe do typu notki — inaczej pomiar po
dwóch tygodniach mierzyłby RODZAJ notki, nie autora.

Sprawdziłem, czy oba modele dostają porównywalne zadania — dostają. Rozkład
typów i form podobny, DeepSeek dostaje nawet dłuższe formy (do 164 słów wobec
115 u Opusa).

**Zasięg (tylko notki co najmniej 2-dniowe):**

| model | notek | wyśw. | polub. | odp. | odwiedziny profilu |
|---|---|---|---|---|---|
| claude-opus-5 | 10 | 22,6 | 3,20 | 0,70 | 0,20 |
| deepseek-v4-pro | 9 | 26,0 | 3,33 | 0,44 | 0,44 |

Mediany 23 wobec 26, zakresy 16–36 wobec 18–38 — **nakładają się prawie
całkowicie.** Różnicy nie ma; DeepSeek jest nominalnie wyżej, ale to szum.

**Cena, zmierzona na produkcji (`run_id IS NOT NULL`, od 3 września):**

| etap | model | na wywołanie |
|---|---|---|
| `note` | claude-opus-5 | **0,06320 USD** |
| `note_tani` | deepseek-v4-pro | **0,01817 USD** |

**Opus kosztuje 3,5 razy więcej za notkę nie do odróżnienia w liczbach.**
Przy pięciu notkach Opusa na dobę różnica to 0,225 USD dziennie, czyli
**6,76 USD miesięcznie — około 21% całego rachunku produkcji** (1,04 USD/dobę).

### Ostrożność, na jaką mnie stać

Przyrządem jest tu zasięg, a **audyt z 3 września wykazał, że reakcje NIE
odróżniają dobrej notki od bełkotu** (3,2 wobec 3,0 wobec 3,1 — płasko). Czyli:
brak różnicy w zasięgu nie dowodzi braku różnicy w jakości. Dowodzi tylko tego,
że **żadna liczba, którą zbieramy, nie broni ceny Opusa.**

Podział zaprojektowano do odczytu po dwóch tygodniach, czyli **około
17 września**. Do tego czasu nic bym nie zmieniał; wtedy próbka będzie ~35 na
model zamiast 10 i 9.

## 3. Serie tematyczne zamiast samego newsa — POMYSŁ MA PODSTAWĘ

### Przesłanka właściciela jest prawdziwa i dała się zmierzyć

Bank kandydatów: **129 ze 131 faktów ma `z_kanalu: True` — 98,5%.** Notki są
newsowe **z budowy**, nie przez przypadek.

Lista dziedzin tematycznych `DZIEDZINY_CIEKAWOSTEK` **istnieje** w `config.py`
i pokrywa większość tego, o co pyta właściciel: leki i diagnostyka, „które
zawody zmieniły się pierwsze, mierzone a nie przepowiadane", klimat, roboty,
prawo (EU AI Act), tłumaczenia. **Ale do banku nie trafia z niej prawie nic.**

### Co mówią liczby o newsie kontra reszcie

Notki co najmniej 2-dniowe, podział po tym, czy tekst niesie zaczep w bieżącym:

| rodzaj | notek | wyśw./notkę | polub./notkę | **odwiedziny profilu** |
|---|---|---|---|---|
| newsowa | 12 | **38,8** | **4,25** | 0,50 |
| bez zaczepu | 23 | 27,4 | 2,74 | **0,61** |

Dwie najlepsze notki w całym zbiorze (94 i 79 wyświetleń) są newsowe.

**Ale miary rozchodzą się w przeciwne strony.** News wygrywa uwagę. Notka bez
zaczepu wygrywa **odwiedziny profilu — jedyny sygnał kroku PRZED subskrypcją.**

### Liczba, która przesądza o sensie pomysłu

    artykuł      7 subskrypcji
    notka        0
    komentarz    0
    odpowiedź    0

**Notki robią zasięg, który nie prowadzi donikąd.** Pojedyncza notka nie daje
nikomu powodu, żeby wrócić. „Część 2 jutro" — daje. To jedyny mechanizm, jakiego
nie próbowaliśmy, a który uderza dokładnie w tę zmierzoną słabość.

### Trzy przeszkody, uczciwie

1. **Bank tego dziś nie wyżywi.** 131 faktów, schodzi ~10 na dobę, dobierane po
   świeżości. Seria pięciu notek o AI w szkole potrzebuje pięciu faktów O TYM
   TEMACIE, a `czego_brakuje` pyta dziś „czego brak", nie „czego brak W TYM
   TEMACIE". To realna zmiana w szukaniu, nie kosmetyka.
2. **„AI przyszłość, jak może wyglądać" zderza się z regułą faktu.** Cała
   architektura wymaga, żeby zdanie stało na pobranym źródle — to jest sens
   pracy nad `not_fetched` i bramek faktów. Seria spekulacyjna albo złamie tę
   regułę, albo wyjdzie pusta. Wersja, która działa, jest już w liście dziedzin:
   **„które zawody zmieniły się pierwsze, mierzone a nie przepowiadane"**.
3. **Koszt utopiony, jeśli otwarcie padnie.** Gdy część 1 zbierze 15 wyświetleń,
   części 2–5 idą do nikogo.

### Co bym zrobił

**Jedna seria, cztery notki, jeden temat, który bank już karmi.** Kolejne doby,
jawnie ponumerowane, ostatnia wskazuje na artykuł tygodniowy. Koszt przy
DeepSeeku: **około 0,07 USD.** W pełni odwracalne.

**Miarą MUSZĄ być odwiedziny profilu i subskrypcje, nie polubienia** — bo
polubienia, jak wyżej, nie odróżniają dobrej notki od bełkotu. Punkt odniesienia:
0,61 odwiedzin na notkę i 0 subskrypcji.

## Czego w tym dokumencie nie ma

Nie ma odpowiedzi na pytanie 1 i nie ma decyzji o Opusie. Obie wymagają
próbki, która narośnie do ~17 września. Zapisuję to jako termin, nie jako
„kiedyś".
