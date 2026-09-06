# Czy wyciągamy ze statystyk wszystko — audyt z 6 września 2026

Wszystko zmierzone na żywej bazie serwera.

## Krótka odpowiedź

Dla **notek i artykułów** przyrząd jest dobry — 100% pozycji ma liczby, 13 pól
na rekord. Dla **komentarzy pod cudzymi artykułami**, czyli dla największego
wolumenu wywołań w całym systemie, **jesteśmy niemal ślepi**.

## 1. Zasięg, najwyższy odczyt na pozycję

| rodzaj | sztuk | śr. wyświetleń | mediana | zero wyśw. | śr. polubień | śr. odpowiedzi |
|---|---|---|---|---|---|---|
| notka | 91 | **32,6** | 25 | 0% | 2,89 | 0,57 |
| artykuł | 7 | 16,6 | 11 | 0% | 1,86 | 1,14 |
| odpowiedź | 7 | 14,7 | 19 | 0% | 2,14 | 1,71 |
| **komentarz** | 99 | **1,0** | **0** | **74%** | 0,20 | 0,07 |

## 2. Ale te 74% to w większości DZIURA W PRZYRZĄDZIE, nie wynik

| gdzie stoi komentarz | sztuk | ma liczby | śr. wyśw. |
|---|---|---|---|
| **pod cudzym artykułem** | 86 | **16%** | 0,9 |
| pod cudzą notką | 13 | **92%** | 1,7 |
| nasze własne notki | 91 | **100%** | 32,6 |

Końcówka `/api/v1/note_stats/c-<id>` obsługuje komentarze pod **notkami**
(92% trafień), a pod **artykułami** oddaje coś tylko w 16% przypadków.
A 86 z 99 naszych komentarzy stoi właśnie pod artykułami.

**Czyli kanał, w którym robimy najwięcej wywołań modelu (728 na 30 dni,
3,81 USD), jest w 84% niemierzalny.**

To jest osobna sprawa od tego, że tam, gdzie mierzyć potrafimy, komentarz
zbiera 1,7 wyświetlenia wobec 32,6 dla notki. Jedno nie zastępuje drugiego:
nie wiemy, czy 84% niemierzonych zachowuje się tak samo.

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

**Najpierw to, co jest tanie i pewne:**

1. **Dwa martwe pola** — sprawdzić, czy Substack w ogóle je oddaje. Jeśli nie,
   usunąć z wyciągu; jeśli tak, naprawić odczyt. Dziś zapisujemy 4 848 pustych
   wartości.

**Potem to, co wymaga rozpoznania na żywym API:**

2. **Komentarze pod artykułami.** Trzeba znaleźć, czy Substack w ogóle podaje
   ich zasięg — a jeśli nie, przyjąć to wprost i przestać udawać, że mamy
   pomiar. Dziś zapisujemy 86 rekordów z zerami, które wyglądają jak wynik,
   a są brakiem danych. To gorsze niż jawna luka.

**A pytanie warte najwięcej brzmi inaczej niż „ile to kosztuje":**

3. Wszystkie 7 przypisanych subskrypcji przyszło z **artykułów**, których
   piszemy trzy na miesiąc. Notek piszemy 91, komentarzy 99. Jeśli ten rozkład
   się utrzyma na większej próbce, pytanie o przydział sił jest ważniejsze niż
   każda optymalizacja kosztu, jaką dziś zrobiłem.
