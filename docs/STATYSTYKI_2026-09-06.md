# Czy wyciągamy ze statystyk wszystko — audyt z 6 września 2026

Wszystko zmierzone na żywej bazie serwera.

## Krótka odpowiedź

Dla **notek i artykułów** przyrząd jest dobry — 100% pozycji ma liczby, 13 pól
na rekord. Przyrząd działa też dla komentarzy — i to on pokazał rzecz
najważniejszą z całego audytu:

**Czternaście najnowszych komentarzy pod cudzymi artykułami zobaczyło ZERO
osób.** Nie „nie wiemy ile" — zero. A tam idzie 86% naszych komentarzy i
największy wolumen wywołań modelu w całym systemie.

## 1. Zasięg, najwyższy odczyt na pozycję

| rodzaj | sztuk | śr. wyświetleń | mediana | zero wyśw. | śr. polubień | śr. odpowiedzi |
|---|---|---|---|---|---|---|
| notka | 91 | **32,6** | 25 | 0% | 2,89 | 0,57 |
| artykuł | 7 | 16,6 | 11 | 0% | 1,86 | 1,14 |
| odpowiedź | 7 | 14,7 | 19 | 0% | 2,14 | 1,71 |
| **komentarz** | 99 | **1,0** | **0** | **74%** | 0,20 | 0,07 |

## 2. ~~Dziura w przyrządzie~~ — SPRAWDZONE NA ŻYWYM API: to jest WYNIK

**Napisałem tu najpierw, że 84% komentarzy jest niemierzalnych. To była
nieprawda i skreślam ją w całości.** Poszedłem sprawdzić końcówkę na żywo
i okazało się coś gorszego.

Końcówka `/api/v1/note_stats/c-<id>` **działa tak samo dla obu rodzajów**.
Oddaje kartę `note` zawsze, a karty `impressionValues`, `surfaces`, `audience`
i `interactions` **tylko wtedy, gdy jest co w nich pokazać**. Brak kart nie
znaczy „nie wiemy" — znaczy „zero".

Sprawdzone na czternastu NAJNOWSZYCH komentarzach pod artykułami i ośmiu pod
notkami:

| gdzie | próbka | pełne karty | śr. wyświetleń | max | z interakcją |
|---|---|---|---|---|---|
| **pod cudzym artykułem** | 14 | **0 z 14** | **0,0** | **0** | **0** |
| pod cudzą notką | 8 | 7 z 8 | 2,9 | 12 | 4 z 8 |

**Każdy z czternastu ostatnich komentarzy pod artykułem został zobaczony przez
zero osób.** Nie „nie wiemy ile" — zero.

A 86 z 99 naszych komentarzy stoi właśnie pod artykułami.

### Co to znaczy w pieniądzach i pracy

Kanał komentarzy to **728 wywołań modelu na 30 dni i 3,81 USD** — największy
wolumen w całym systemie. 86% tej pracy idzie pod artykuły, gdzie zasięg jest
zerowy.

Komentarz pod cudzą **notką** działa: 2,9 wyświetlenia, połowa dostaje
interakcję. To ta sama praca, w innym miejscu, z niezerowym skutkiem.

### Ostrożność, na jaką mnie stać

Wnioskuję „brak karty = zero", a nie czytam jawnego zera. Za tą interpretacją
stoi to, że wśród komentarzy pod notkami siedem z ośmiu **ma** karty i ma
wyświetlenia, a ten jeden bez kart ma zero. Gdyby brak kart znaczył „brak
danych", ta zgodność byłaby przypadkiem.

## 3. Subskrypcje — wszystkie z artykułów

    artykuł      7 subskrypcji z 3 pozycji
    notka        0
    komentarz    0
    odpowiedź    0

Konto urosło o 11 subskrypcji w 14 dni, a przyrząd przypisuje **siedem
z nich artykułom i ani jednej niczemu innemu**. Trzy artykuły na 30 dni wobec
91 notek i 99 komentarzy.

## 4. Dwa pola zawsze puste

    obserwacje       3 588 rekordów, ZAWSZE puste
    zapisy_platne    1 260 rekordów, ZAWSZE puste

Ta sama klasa wady, co `fakt_ranga` (pole zbudowane po to, żeby coś zmierzyć,
i przez cały czas puste). Albo pole ma się wypełniać, albo nie ma powodu, żeby
je zbierać i zapisywać.

## 5. Czego NIE potwierdziłem, choć wyglądało na prawdę

Po pierwszym rzucie wyszło mi, że **statystyki komentarzy znikają po dobie**
(26% → 10% → 0% wraz z wiekiem). Sprawdziłem to na tych samych
identyfikatorach mierzonych wielokrotnie: **zero komentarzy straciło liczby**,
a odczyty normalnie rosną (0 → 25 → 27 → 30 wyświetleń, polubienia 3 → 4 → 5).

Mój podział według wieku był bez sensu, bo pole `zmierzone` **nie jest czasem
pomiaru** — dla jednego komentarza pięć rekordów ma tę samą wartość. Gdybym
tego nie sprawdził, zgłosiłbym nieistniejącą awarię.

## 6. Co da się z tym zrobić

**Jedna rzecz jest teraz oczywista i mierzalna:**

1. **Przenieść wysiłek komentarzy z artykułów pod notki.** Dziś blok
   `komentarze()` celuje w artykuły i bierze pełny przydział, a blok
   `dyskusje()` celuje w notki i bierze połowę tego samego. Zasięg mówi
   odwrotnie: **artykuł 0, notka 2,9**. To jest zmiana przydziału, nie kodu
   modelu — i pierwsza rzecz, jaką bym zrobił.

**Tanie i pewne:**

2. **Dwa martwe pola** (`obserwacje`, `zapisy_platne`) — 4 848 zapisanych
   pustek. Sprawdzić, czy Substack je oddaje; jeśli nie, usunąć z wyciągu.

**Pytanie warte najwięcej:**

3. Wszystkie 7 przypisanych subskrypcji przyszło z **artykułów**, których
   piszemy trzy na miesiąc. Notek 91, komentarzy 99. Jeśli ten rozkład utrzyma
   się na większej próbce, pytanie o przydział sił jest ważniejsze niż każda
   optymalizacja kosztu z tej sesji.

## 7. Ile razy pomyliłem się w tym jednym audycie

Dwa razy, oba tego samego dnia i oba na przyrządzie, nie na danych:

1. **„Statystyki komentarzy znikają po dobie"** — pole `zmierzone` nie jest
   czasem pomiaru, więc mój podział według wieku był bez sensu. Sprawdzenie na
   tych samych identyfikatorach: zero utraconych odczytów, liczby normalnie
   rosną.
2. **„84% komentarzy jest niemierzalnych"** — końcówka działa tak samo dla obu
   rodzajów; brak kart znaczy zero, nie brak danych. Sprawdziłem to dopiero
   wtedy, gdy poszedłem zapytać żywego API zamiast czytać zapisane rekordy.

**Wniosek dla następnego czytelnika: zanim ogłosisz, że przyrząd jest zepsuty,
zapytaj źródła.** Obie moje pomyłki brały się z czytania zapisów zamiast
sprawdzenia, co API naprawdę odpowiada.

