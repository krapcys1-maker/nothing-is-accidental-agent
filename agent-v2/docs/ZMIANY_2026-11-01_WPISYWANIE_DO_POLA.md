# Czyszczenie i weryfikacja pola przed wpisaniem tekstu (`browser.wpisz_do_pola`), 1.11.2026

**Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Incydent

1.11.2026 jedna odpowiedź bota pod cudzym komentarzem wyszła z doklejonym na początku tekstem próbnym „Dry run only - this text is never sent.”. Przyczyna: mój własny test na żywo (`wyslij=False`) wpisał ten tekst w pole odpowiedzi i go nie wysłał, ale Substack zachowuje **szkic** odpowiedzi pod danym komentarzem. Kiedy bot odpisał tam naprawdę, `page.keyboard.type` dopisał odpowiedź ZA szkicem i wszystko poszło razem. Komentarz jest publiczny; nie został usunięty (decyzja właściciela).

To ta sama klasa wady, którą mamy w całym projekcie: założenie, że pole jest puste, bez sprawdzenia.

## Co zmieniono

Nowa funkcja `browser.wpisz_do_pola(page, pole, tekst)` zastępuje cztery surowe `page.keyboard.type(tekst, delay=12)` (odpowiedź pod artykułem, odpowiedź pod notką, nowa notka, komentarz):

1. czyta zawartość pola; jeśli cokolwiek w nim jest (poza białymi znakami), zaznacza całość (`Control+a`) i kasuje (`Delete`);
2. wpisuje tekst;
3. czyta pole jeszcze raz i porównuje **tylko litery i cyfry, bez wielkości liter** (edytor zamienia cudzysłowy, spacje i czasem pierwszą literę): w polu ma stać nasz tekst, jego początek (40 znaków) musi się zgadzać, a długość nie może przekraczać naszej o więcej niż 40 znaków;
4. gdy w polu jest coś obcego (szkic wraca po skasowaniu, edytor dopisał podpowiedź), czyści i próbuje drugi raz; po drugim niepowodzeniu rzuca `RuntimeError` i **nic nie jest wysyłane** (wywołujący traktuje to jak zwykły błąd publikacji);
5. gdy pola nie da się odczytać (zmiana struktury strony), NIE blokuje wysyłki: wpisuje i zapisuje w logu „nie umiem odczytać pola”. Blokowanie publikacji przez niepewny odczyt byłoby gorsze niż stare zachowanie.

## Czego nie zmienia

Treści odpowiedzi, doboru celów, kolejności kroków ani limitów czasu. Szkice pod innymi komentarzami, których bot nie dotyka, zostają, jak były.

## Dowody

`tests/test_wpisz_do_pola.py` (20 sprawdzeń, atrapa edytora i strony, bez przeglądarki i sieci): puste pole, szkic z incydentu, szkic identyczny z naszym tekstem, szkic wracający raz i zawsze, obcy tekst dopisany po naszym, edytor zmieniający cudzysłowy i wielkość pierwszej litery, polskie znaki, pole nieczytelne, oraz sprawdzenie źródła: jedyne `page.keyboard.type(tekst` jest w helperze, a wszystkie cztery miejsca go wołają. Mutacje `robocze/mutacje_pole.py`: 13 mutantów, wszystkie zabite przy zielonej bazie.

**Czego test NIE dowodzi:** zachowania prawdziwego edytora Substacka. Dowodem będzie dopiero ślad z produkcji po wdrożeniu (linie `[pole] ...` w logu przebiegu; brak takich linii oznacza, że pola były czyste).

## Wycofanie

`git reset --hard <poprzednia wersja>`. Nie ma flagi: zmiana jest tylko ostrożniejsza niż poprzednie zachowanie.
