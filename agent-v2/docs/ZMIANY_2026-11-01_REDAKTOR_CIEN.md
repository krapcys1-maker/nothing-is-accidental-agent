# Redaktor w cieniu (etap R1), 1.11.2026

Zlecenie właściciela (1.11): bot ma działać bardziej jak człowiek: analizować, co przynosi sukces (co się klika), na tej podstawie wybierać tematy, proponować research, styl i długość notek i podejmować decyzje. Uzgodnione z sesją badawczą „Pamięć LLM" (odpowiedź P-013): R1 (cień, bez wpływu na treść) od zaraz, R2 (wykonywanie propozycji) dopiero po protokole oceny pamięci i nigdy w oknie bazowym, każdy rekord z numerem epoki redakcyjnej, w dzienniku tylko liczby zbiorcze. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Co robi

Raz dziennie (po `co_dziala.zapisz()` w `obserwatorium.py zbierz --raport`, 03:40 UTC) `redaktor.zapisz()` czyta `obserwatorium/co_dziala.json`, czyli to, co bot już liczy: grupy z wymiarów notki (kąt, kategoria, długość, pora, forma, styk, pytanie na końcu...) z werdyktami z bootstrapu po niezależnych jednostkach (`lepiej` / `gorzej` / `brak dowodu` / `za mało danych`). **Sam nie liczy statystyki od nowa.** Raz na tydzień ISO zapisuje do `data/redaktor_cien.jsonl` rekord „epoka" i pisze notatkę redaktora dla człowieka do `data/obserwatorium/redaktor.md`.

- **Obserwacje:** liczba notek z pomiarem, mediana wyświetleń, liczniki grup wg werdyktu.
- **Propozycje** (najwyżej 5), każda z dowodem (liczby z raportu), z przewidywaniem i terminem 14 dni: mocny sygnał „lepiej" → zwiększyć udział grupy jako eksperyment; „gorzej" → ograniczyć; kandydaci bez przedziału (wzgl. tła > 1, co najmniej 3 notki) → sprawdzić (dla tematu: zlecić research); gdy notek z pomiarem jest mniej niż 8 → „nie zmieniać polityki, zbierać dane". Wymiary `model` i `pozycja` oraz grupa odniesienia nie dają propozycji.
- **Rozliczenie:** po terminie sprawdza przewidywanie z tego samego raportu: `potwierdzone`, `chybione` albo `bez_rozstrzygniecia` (gdy danych dalej za mało; to uczciwa odpowiedź, nie zgadywanie). Każde przewidywanie jest rozliczane raz.

## Czego NIE robi

- Nie zmienia tematów, stylu, długości, żadnego tekstu ani doboru celów. Propozycje są tylko zapisem zamiarów; wykonanie (R2) wymaga osobnej decyzji po protokole oceny.
- Bez modelu i sieci. W dzienniku wyłącznie liczby zbiorcze i nazwy grup (kategorie, formaty): żadnych tekstów notek, uchwytów ani danych czytelników. Pole `najlepsze` z raportu nie jest kopiowane.
- Nie zmienia `co_dziala.py` ani niczego, co bot czyta przy pisaniu.

## Epoka redakcyjna

Każdy rekord ma `epoka_redakcyjna` (dziś 0 = polityka bez zmian). Zmiana polityki w R2 podniesie numer, żeby analiza pamięci mogła stratyfikować po epoce.

## Wyłączenie i wycofanie

`config.REDAKTOR_CIEN = False` albo `git reset --hard <poprzednia wersja>`. Awaria nie zatrzymuje raportu dobowego (hak w `try/except`). Limit pliku 10 MB. Zapis dopisuje `\n`, jeśli poprzednia linia została ucięta.

## Dowody i ograniczenia

- Test `tests/test_redaktor.py` (40 sprawdzeń); mutacje `robocze/mutacje_redaktor.py` (wynik w sekcji „Wdrożenie”).
- **Dane są na razie bardzo małe** (w epoce od 26.10 jest 12 notek z pomiarem, mediana 11 wyświetleń, żadna grupa nie ma jeszcze werdyktu), więc pierwsze wpisy będą mówiły głównie „nie zmieniać polityki, zbierać dane". To zamierzone: redaktor ma uczciwie przyznać, że nie wie.
- Przewidywania są proste i sprawdzalne z tego samego raportu; to nie jest jeszcze kalibracja prawdopodobieństw.
- Wersja z modelem (napisanie propozycji słowami redaktora z weryfikacją cytatów przez kod) to osobny, późniejszy krok.
