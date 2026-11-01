# Redaktor w cieniu (etap R1), 1.11.2026

Zlecenie właściciela (1.11): bot ma działać bardziej jak człowiek: analizować, co przynosi sukces (co się klika), na tej podstawie wybierać tematy, proponować research, styl i długość notek i podejmować decyzje. Uzgodnione z sesją badawczą „Pamięć LLM" (odpowiedź P-013): R1 (cień, bez wpływu na treść) od zaraz, R2 (wykonywanie propozycji) dopiero po protokole oceny pamięci i nigdy w oknie bazowym, każdy rekord z numerem epoki redakcyjnej, w dzienniku tylko liczby zbiorcze. **Data wdrożenia: patrz „Wdrożenie” na końcu.**

Ta wersja jest PO DWÓCH PRZEGLĄDACH niezależnych (1.11). Pierwszy wykazał: rozliczanie na skumulowanym oknie `co_dziala` (te same notki, które dały sygnał, „potwierdzały” go po 14 dniach), propozycje z grup po 3 notki (na żywym raporcie to był sam szum), brak kontroli świeżości raportu. Drugi (po przepisaniu): kandydat był oceniany względem tła, a cały raport porównuje z grupą odniesienia (wymiar może mieć wspólne przesunięcie względem tła, wtedy każdy kandydat przechodził); przewidywanie „nadal lepiej” rozliczane na tych samych danych; „lepiej → brak dowodu” liczone jako brak rozstrzygnięcia (stronniczość w stronę sukcesu); próg „4 nowe notki” liczył notki, a nie niezależne jednostki (jedna seria wystarczała); brak kontroli okna raportu; „nie zmieniać polityki” wracało co tydzień. Poniżej opis wersji poprawionej.

## Co robi

Raz dziennie (po `co_dziala.zapisz()` w `obserwatorium.py zbierz --raport`, 03:40 UTC) `redaktor.zapisz()` czyta `obserwatorium/co_dziala.json`, czyli to, co bot już liczy: grupy z wymiarów notki (kąt, kategoria, długość, pora, forma, styk, pytanie na końcu...) z werdyktami z bootstrapu po niezależnych jednostkach (`lepiej` / `gorzej` / `brak dowodu` / `za mało danych`). **Sam nie liczy statystyki od nowa.** Raz na tydzień ISO zapisuje do `data/redaktor_cien.jsonl` rekord „epoka" i pisze notatkę redaktora dla człowieka do `data/obserwatorium/redaktor.md`.

- **Obserwacje:** liczba notek z pomiarem, mediana wyświetleń, liczniki grup wg werdyktu, statusy trwających eksperymentów (zmienne dla analizy pamięci).
- **Propozycje** (najwyżej 5 na tydzień, reszta idzie do licznika `obcieto`), każda z dowodem (liczby z raportu), z przewidywaniem i terminem 14 dni:
  - mocny sygnał „lepiej" → zwiększyć udział grupy jako eksperyment; „gorzej" → ograniczyć. Przewidywanie: po 14 dniach i po przyroście co najmniej 4 notek w 2 nowych niezależnych jednostkach werdykt grupy względem tej samej grupy odniesienia nadal będzie taki sam;
  - **kandydat do sprawdzenia** (grupa bez przedziału ufności) tylko gdy ma co najmniej 4 notki, co najmniej 3 niezależne jednostki, przewagę co najmniej 1,15 **nad grupą odniesienia** (wzgl. tła grupy podzielone przez wzgl. tła odniesienia) i co najmniej połowę „wykrywalnego efektu" raportu; dla wymiarów `dzien` i `pora` dodatkowo okno raportu co najmniej 14 dni (krótsze to jedna data kalendarzowa, nie niezależny tydzień). Dla tematu to zlecenie researchu. Przewidywanie: NOWE notki grupy (co najmniej 4, w co najmniej 2 nowych niezależnych jednostkach) będą średnio nie gorsze niż NOWE notki grupy odniesienia (stan obu grup z chwili zapisu jest w rekordzie);
  - gdy notek z pomiarem jest mniej niż 8 albo żadna grupa nie ma jeszcze werdyktu „lepiej" ani „gorzej" → pierwsza propozycja to „nie zmieniać polityki, zbierać dane" (przewidywanie: po 14 dniach przynajmniej jedna grupa dostanie mocny werdykt); to zdanie nie wraca, dopóki poprzednie nie jest rozliczone (jeśli nie ma wtedy nic do zaproponowania, jest informacja bez nowego przewidywania);
  - wymiary `model` i `pozycja` (kto pisał, nie co czytelnika interesuje) oraz grupa odniesienia nie dają propozycji;
  - ta sama grupa i ten sam typ przewidywania nie wracają co tydzień, dopóki poprzednie nie jest rozliczone.
- **Rozliczenie:** po terminie `potwierdzone`, `chybione` albo `bez_rozstrzygniecia` (to ostatnie, gdy nowych danych za mało, grupy brak w raporcie albo zmieniła się grupa odniesienia: uczciwa odpowiedź, nie zgadywanie). Przewidywania o grupach są sprawdzane dopiero po przyroście **nowych** danych (co najmniej 4 notki i 2 niezależne jednostki, inaczej `bez_rozstrzygniecia`). Przewidywanie o kandydacie porównuje **nowe notki grupy z nowymi notkami grupy odniesienia** (szacunek z przyrostu: średnia logarytmów względem tła z chwili zapisu i teraz, ważona liczbą notek). Przewidywanie o mocnym sygnale: ten sam werdykt po przyroście danych = `potwierdzone`; odwrócony albo zanik przedziału („brak dowodu”) = `chybione`. Zmiana okna raportu (`od`) albo grupy odniesienia unieważnia porównanie. Każde przewidywanie jest rozliczane raz.

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

- Test `tests/test_redaktor.py` (79 sprawdzeń, bez pytesta, bez sieci; wejścia do estymatora nowych notek zbudowane niezależnie od wzoru w kodzie); mutacje `robocze/mutacje_redaktor.py`: 47 mutantów, wszystkie zabite przy zielonej bazie (skrypt odmawia pracy, gdy test sypie się bez mutacji).
- **Dane są na razie bardzo małe** (w epoce od 26.10 jest kilkanaście notek z pomiarem, mediana ok. 11 wyświetleń, żadna grupa nie ma jeszcze werdyktu), więc pierwsze wpisy będą mówiły głównie „nie zmieniać polityki, zbierać dane". To zamierzone: redaktor ma uczciwie przyznać, że nie wie.
- Przewidywania są proste i sprawdzalne z kolejnych raportów; to nie jest jeszcze kalibracja prawdopodobieństw. Próg nowych danych oznacza, że przy kilku notkach dziennie pierwsze rozliczenia często zakończą się „bez rozstrzygnięcia”.
- **Brak poprawki na wielokrotne testy.** Wymiarów jest wiele (kilkadziesiąt grup po 5% fałszywych alarmów), więc „mocny sygnał” z samego szumu pojawia się niemal zawsze, a bootstrap po małej liczbie klastrów bywa zbyt optymistyczny. Odsetek `potwierdzone` z cienia NIE jest dowodem, że redaktor ma rację; przed R2 trzeba osobno ocenić, ile propozycji przetrwało w nowych danych.
- Estymator nowych notek zależy od tła liczonego co noc od nowa (mediana sąsiadów ±7 dni), więc stare notki dryfują; symulacja przeglądającego dała błąd ok. 0,035 w logarytmie przy ok. 20 starych i 20 nowych notkach i wyraźnie więcej przy 5 nowych. To nie jest pomiar precyzyjny.
- Redaktor czyta tylko `wymiary` z `co_dziala.json`. Wymiar „format” (zwykła / seria / rozkmina) siedzi w osobnym polu `formaty` i nie jest uwzględniony: to luka, nie zamierzony wybór. Nie ma blokady plików przy dwóch równoległych przebiegach (ręczny plus timer); najgorszy skutek to podwójny rekord epoki.
- Wersja z modelem (napisanie propozycji słowami redaktora z weryfikacją cytatów przez kod) to osobny, późniejszy krok.
