# Czyszczenie i weryfikacja pola przed wpisaniem tekstu (`browser.wpisz_do_pola`), 1.11.2026

**Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Incydent

1.11.2026 jedna odpowiedź bota pod cudzym komentarzem wyszła z doklejonym na początku tekstem próbnym „Dry run only - this text is never sent.”. Przyczyna: mój własny test na żywo (`wyslij=False`) wpisał ten tekst w pole odpowiedzi i go nie wysłał, ale Substack zachowuje **szkic** odpowiedzi pod danym komentarzem. Kiedy bot odpisał tam naprawdę, `page.keyboard.type` dopisał odpowiedź ZA szkicem i wszystko poszło razem. Komentarz jest publiczny; nie został usunięty (decyzja właściciela).

To ta sama klasa wady, którą mamy w całym projekcie: założenie, że pole jest puste, bez sprawdzenia.

## Co zmieniono

Nowa funkcja `browser.wpisz_do_pola(page, pole, tekst)` zastępuje cztery surowe `page.keyboard.type(tekst, delay=12)` (odpowiedź pod artykułem, odpowiedź pod notką, nowa notka, komentarz):

1. czyta zawartość pola (`.value` dla `<textarea>`, `innerText` dla `contenteditable`, awaryjnie `inner_text`); jeśli cokolwiek w nim jest (poza białymi znakami), zaznacza całość (`Control+a`) i kasuje (`Delete`);
2. gdy znalazł i skasował szkic, zapisuje to w logu (`[pole] w polu był szkic — wyczyszczone przed wpisaniem`, bez treści szkicu), żeby było widać na produkcji, że poprawka działa; wpisuje tekst;
3. czyta pole jeszcze raz i porównuje **tylko litery i cyfry, bez wielkości liter** (edytor zamienia cudzysłowy, spacje i czasem pierwszą literę): w polu ma stać nasz tekst, jego początek (40 znaków) musi się zgadzać, a długość nie może przekraczać naszej o więcej niż 20 znaków (obcy tekst z incydentu miał 29);
4. gdy w polu jest coś obcego (szkic wraca po skasowaniu, edytor dopisał podpowiedź), czyści i próbuje drugi raz; po drugim niepowodzeniu rzuca `RuntimeError` i **nic nie jest wysyłane** (wywołujący traktuje to jak zwykły błąd publikacji);
5. gdy pola nie da się odczytać (zmiana struktury strony) albo odczyt po wpisaniu jest pusty mimo niepustego tekstu (ślepy czytnik), NIE blokuje wysyłki: wpisuje i zapisuje w logu „nie umiem odczytać pola” albo „pole wygląda na puste po wpisaniu”. Blokowanie publikacji przez niepewny odczyt byłoby gorsze niż stare zachowanie, a przy pustym polu Substack i tak nie odblokuje przycisku wysyłki.

**Poprawka po przeglądzie i teście na prawdziwym Chromium (1.11).** Pierwsza wersja czytała pole przez `inner_text`. Dwa z czterech torów (komentarz pod postem i odpowiedź pod artykułem) piszą w `<textarea>`, a `innerText` dla textarea jest PUSTY. Wykrył to istniejący test `test_odpowiedz_pod_artykulem.py` na prawdziwym Chromium (nowa czerwień względem bazy na serwerze) i niezależny przegląd. Skutek, gdyby to poszło na produkcję: poprawka nic by nie robiła na polu z incydentu, a po wpisaniu każdy komentarz i każda odpowiedź pod artykułem kończyłyby się błędem. Teraz: czytnik `.value`, pusty odczyt po wpisaniu nie blokuje, a `test_wpisz_do_pola.py` sprawdza oba typy pól na prawdziwym Chromium.

## Czego to NIE obejmuje

- Piąte miejsce wpisywania tekstu, okno restacku z komentarzem (`restackuj_w_kanale`, `pole.type`), nie używa helpera. Nie ma dowodu, że ten modal zachowuje szkice; zostaje jak było.
- Przyczyna incydentu, tryb bez wysyłki (`wyslij=False`), nadal zostawia szkic w polu. Helper czyści go przy następnym wpisie bota, ale właściciel pracujący ręcznie na tym koncie mógłby go zobaczyć lub wysłać. Testów na żywo bez wysyłki nie robić w polach pod prawdziwymi komentarzami.

## Czego nie zmienia

Treści odpowiedzi, doboru celów, kolejności kroków ani limitów czasu. Szkice pod innymi komentarzami, których bot nie dotyka, zostają, jak były.

## Dowody

`tests/test_wpisz_do_pola.py` (30 sprawdzeń: atrapa edytora i strony oraz prawdziwy Chromium z `<textarea>` i `contenteditable`, ze szkicem i bez): puste pole, szkic z incydentu, szkic identyczny z naszym tekstem, szkic wracający raz i zawsze, obcy tekst dopisany po naszym, edytor zmieniający cudzysłowy i wielkość pierwszej litery, polskie znaki, pole nieczytelne, oraz sprawdzenie źródła: jedyne `page.keyboard.type(tekst` jest w helperze, a wszystkie cztery miejsca go wołają. Mutacje `robocze/mutacje_pole.py`: 17 mutantów, wszystkie zabite przy zielonej bazie.

**Czego test NIE dowodzi:** zachowania prawdziwego edytora Substacka. Dowodem będzie dopiero ślad z produkcji po wdrożeniu: linia `[pole] w polu był szkic` pojawia się tylko wtedy, gdy szkic naprawdę istniał (jej brak oznacza czyste pola), a linia `[pole] w polu jest coś poza naszym tekstem` albo błąd `w polu został obcy tekst` oznacza, że weryfikacja coś zablokowała i trzeba to obejrzeć. Pierwsza wersja dokumentu twierdziła, że brak linii `[pole]` oznacza czyste pola; to było nieprawdą, bo skasowany szkic nie zostawiał śladu (wykryte w trzecim przeglądzie, naprawione).

## Wycofanie

`git reset --hard <poprzednia wersja>`. Nie ma flagi: zmiana jest tylko ostrożniejsza niż poprzednie zachowanie.
