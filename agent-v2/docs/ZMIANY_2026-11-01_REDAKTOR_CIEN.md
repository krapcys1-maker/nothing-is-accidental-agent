# Redaktor w cieniu (etap R1), 1.11.2026

Zlecenie właściciela (1.11): bot ma działać bardziej jak człowiek: analizować, co przynosi sukces (co się klika), na tej podstawie wybierać tematy, proponować research, styl i długość notek i podejmować decyzje. Uzgodnione z sesją badawczą „Pamięć LLM" (odpowiedź P-013): R1 (cień, bez wpływu na treść) od zaraz, R2 (wykonywanie propozycji) dopiero po protokole oceny pamięci i nigdy w oknie bazowym, każdy rekord z numerem epoki redakcyjnej, w dzienniku tylko liczby zbiorcze. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

Ta wersja jest PO PRZEGLĄDZIE niezależnym (1.11): pierwsza wersja rozliczała przewidywania na skumulowanym oknie `co_dziala` (te same notki, które dały sygnał, „potwierdzały" go po 14 dniach), robiła propozycje z grup po 3 notki (na żywym raporcie to był sam szum) i nie sprawdzała świeżości raportu. Poniżej opis wersji poprawionej.

## Co robi

Raz dziennie (po `co_dziala.zapisz()` w `obserwatorium.py zbierz --raport`, 03:40 UTC) `redaktor.zapisz()` czyta `obserwatorium/co_dziala.json`, czyli to, co bot już liczy: grupy z wymiarów notki (kąt, kategoria, długość, pora, forma, styk, pytanie na końcu...) z werdyktami z bootstrapu po niezależnych jednostkach (`lepiej` / `gorzej` / `brak dowodu` / `za mało danych`). **Sam nie liczy statystyki od nowa.** Raz na tydzień ISO zapisuje do `data/redaktor_cien.jsonl` rekord „epoka" i pisze notatkę redaktora dla człowieka do `data/obserwatorium/redaktor.md`.

- **Obserwacje:** liczba notek z pomiarem, mediana wyświetleń, liczniki grup wg werdyktu, statusy trwających eksperymentów (zmienne dla analizy pamięci).
- **Propozycje** (najwyżej 5 na tydzień, reszta idzie do licznika `obcieto`), każda z dowodem (liczby z raportu), z przewidywaniem i terminem 14 dni:
  - mocny sygnał „lepiej" → zwiększyć udział grupy jako eksperyment; „gorzej" → ograniczyć. Przewidywanie: po 14 dniach werdykt grupy względem tej samej grupy odniesienia nadal będzie taki sam;
  - **kandydat do sprawdzenia** (grupa bez przedziału ufności) tylko gdy ma co najmniej 4 notki, co najmniej 3 niezależne jednostki, przewagę co najmniej 1,15 względem tła i co najmniej połowę „wykrywalnego efektu" raportu; dla wymiarów `dzien` i `pora` dodatkowo okno raportu co najmniej 14 dni (krótsze to jedna data kalendarzowa, nie niezależny tydzień). Dla tematu to zlecenie researchu. Przewidywanie: NOWE notki grupy (co najmniej 4) będą średnio nad tłem;
  - gdy notek z pomiarem jest mniej niż 8 albo żadna grupa nie ma jeszcze werdyktu „lepiej" ani „gorzej" → pierwsza propozycja to „nie zmieniać polityki, zbierać dane" (przewidywanie: po 14 dniach przynajmniej jedna grupa dostanie mocny werdykt);
  - wymiary `model` i `pozycja` (kto pisał, nie co czytelnika interesuje) oraz grupa odniesienia nie dają propozycji;
  - ta sama grupa i ten sam typ przewidywania nie wracają co tydzień, dopóki poprzednie nie jest rozliczone.
- **Rozliczenie:** po terminie `potwierdzone`, `chybione` albo `bez_rozstrzygniecia` (to ostatnie, gdy nowych danych za mało, grupy brak w raporcie albo zmieniła się grupa odniesienia: uczciwa odpowiedź, nie zgadywanie). Przewidywanie o kandydacie jest sprawdzane **tylko na nowych notkach** (szacunek z przyrostu: średnia logarytmów względem tła z chwili zapisu i teraz, ważona liczbą notek). Każde przewidywanie jest rozliczane raz.

## Czego NIE robi

- Nie zmienia tematów, stylu, długości, żadnego tekstu ani doboru celów. Propozycje są tylko zapisem zamiarów; wykonanie (R2) wymaga osobnej decyzji po protokole oceny.
- Bez modelu i sieci. Nie importuje modułów bota (`stages`, `run`, `llm`, `browser`, `db`); skrót commita bierze wprost z gita, z limitem 5 s. W dzienniku wyłącznie liczby zbiorcze i nazwy grup (kategorie, formaty): żadnych tekstów notek, uchwytów ani danych czytelników. Pole `najlepsze` z raportu nie jest kopiowane.
- Nie pracuje na nieświeżym raporcie: jeśli `dzis` w `co_dziala.json` jest starsze niż doba, pomija zapis i mówi to w logu (inaczej stary raport udawałby nowy tydzień).
- Nie zmienia `co_dziala.py` ani niczego, co bot czyta przy pisaniu.

## Epoka redakcyjna

Każdy rekord ma `epoka_redakcyjna` (dziś 0 = polityka bez zmian). Zmiana polityki w R2 podniesie numer, żeby analiza pamięci mogła stratyfikować po epoce.

## Wyłączenie i wycofanie

`config.REDAKTOR_CIEN = False` albo `git reset --hard <poprzednia wersja>`. Awaria nie zatrzymuje raportu dobowego (hak w `try/except`, błąd idzie do logu). Limit pliku 10 MB (po przekroczeniu zapis jest pomijany z komunikatem). Zapis dopisuje `\n`, jeśli poprzednia linia została ucięta. Uszkodzone linie w dzienniku są pomijane przy odczycie.

## Dowody i ograniczenia

- Test `tests/test_redaktor.py` (62 sprawdzenia, bez pytesta, bez sieci); mutacje `robocze/mutacje_redaktor.py`: 36 mutantów, wszystkie zabite przy zielonej bazie (skrypt odmawia pracy, gdy test sypie się bez mutacji).
- **Dane są na razie bardzo małe** (w epoce od 26.10 jest kilkanaście notek z pomiarem, mediana ok. 11 wyświetleń, żadna grupa nie ma jeszcze werdyktu), więc pierwsze wpisy będą mówiły głównie „nie zmieniać polityki, zbierać dane". To zamierzone: redaktor ma uczciwie przyznać, że nie wie.
- Przewidywania są proste i sprawdzalne z kolejnych raportów; to nie jest jeszcze kalibracja prawdopodobieństw. Próg „co najmniej 4 nowe notki" oznacza, że przy kilku notkach dziennie pierwsze rozliczenia często zakończą się „bez rozstrzygnięcia".
- Wersja z modelem (napisanie propozycji słowami redaktora z weryfikacją cytatów przez kod) to osobny, późniejszy krok.
