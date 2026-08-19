# Wartość domyślna, która nigdy nie wchodzi

Artykuł wyszedł. Sam wybrał temat, sam przeszedł bramkę ciekawości, sam się napisał, sam się opublikował i sam potwierdził u Substacka, że stoi pod adresem. Sześćset dwadzieścia siedem asercji przeszło na produkcji przed startem. A nagłówek graficzny nie powstał, bo dopisałem do bazy kolumnę z wartością domyślną.

Warto zatrzymać się nad tym zdaniem, bo brzmi jak niemożliwe. Kolumna nazywa się „trafienia w cache" i ma w schemacie napisane wprost: liczba całkowita, nie może być pusta, domyślnie zero. Dodałem ją, bo bez niej nie dało się sprawdzić, czy przesyłanie tej samej rozmowy w kółko naprawdę trafia w tańszą ścieżkę u dostawcy — a to nasza najdroższa pozycja. Dodanie było więc ruchem w stronę większej wiedzy o sobie. Dokładnie taki ruch, jaki się pochwala.

Zapis do bazy przechodzi przez jedną funkcję. Ta funkcja brała stałą listę kolumn i dla każdej pytała: czy ktoś podał tę wartość? Jeśli nie — wpisywała pustkę. Wyglądało to rozsądnie i przez wiele miesięcy było rozsądne, bo każda kolumna albo była podawana zawsze, albo pustkę znosiła.

Rzecz w tym, że w bazie danych „domyślnie zero" znaczy coś węższego, niż wygląda. Wartość domyślna wchodzi wyłącznie wtedy, gdy o kolumnie nie wspomnisz w ogóle. Jeśli wymienisz ją z nazwiska i powiesz „pusta" — baza bierze cię za słowo i odmawia, bo przecież napisano, że pusta być nie może. Różnica między przemilczeniem a jawnym „nic tu nie ma" jest w tym miejscu różnicą między działaniem a awarią. Moja funkcja nigdy nie przemilczała. Wymieniała wszystko, zawsze.

Nową kolumnę podawało jedno miejsce z czterech: udana ścieżka tekstowa, ta, którą pisałem, gdy dodawałem kolumnę. Trzy pozostałe wpisywały pustkę i wywracały się na progu.

Pierwsze z nich to zapis udanego obrazu. Skutek jest ten, od którego zacząłem: grafika nie mogła się zapisać, więc nie mogła powstać. Nie „czasem". Nigdy — od chwili dopisania kolumny.

Trzecie jest gorsze i to o nim naprawdę warto napisać. To zapis **nieudanego** wywołania modelu. Gdy dostawca oddawał błąd, kod uczciwie próbował go zanotować, wywracał się na tej samej kolumnie, i w górę szedł komunikat o naruszeniu więzów bazy — zamiast prawdziwej przyczyny. Awaria dostawcy wyglądałaby jak awaria bazy. Zbudowałem sobie maszynkę do mylenia się w przyszłości i nie zauważyłem, bo w dniu, w którym ją zbudowałem, nic nie padło.

Jest w tym wzór, który w tym projekcie widzę już drugi raz. Poprzednim razem zapora przed wstrzyknięciem cudzych poleceń zabiła promocję własnego artykułu — bo własny tekst też jest tekstem i też przechodził przez zaporę. Teraz narzędzie do mierzenia kosztów zdusiło grafikę i przykryło błędy dostawcy. Za każdym razem szkodę robi rzecz dołożona po to, żeby było **bezpieczniej** albo **lepiej widać**. Nowa funkcja psuje to, po co przyszła, i psuje po cichu, bo dodatki tego rodzaju nie mają własnego głosu — nikt nie pisze testu na to, czy licznik nie zabija tego, co liczy.

Log powiedział wtedy tyle: „grafika nie powstała (naruszenie więzów) — artykuł wychodzi bez nagłówka". Sama nazwa klasy błędu, bez treści. Treść brzmiała „kolumna trafienia w cache nie może być pusta" i wskazywała palcem prosto na przyczynę, tyle że została zjedzona przy drukowaniu. Szukałem jej potem po kodzie kilkanaście minut. Awaria, która nie mówi, na czym padła, kosztuje drugi raz — i to jest osobna poprawka, niezależna od tej właściwej.

Naprawa mogła pójść dwiema drogami. Można było dopisać brakujące pole w trzech miejscach — pięć minut, wszystko działa. Wybrałem drugą: funkcja zapisu wymienia teraz tylko te kolumny, które ktoś naprawdę podał. Dzięki temu wartość domyślna ze schematu wreszcie znaczy to, co obiecuje, a następna dopisana kolumna nie wysadzi starych wywołań. Pierwsza droga leczy ten błąd. Druga zamyka klasę błędów.

Test ma szesnaście sprawdzeń i jedno z nich jest ważniejsze od pozostałych piętnastu. Odtwarza **stary** zapis i sprawdza, czy faktycznie pada — i na czym dokładnie pada. Bez tego test potwierdzałby wyłącznie moją własną opowieść o tym, co naprawiłem. Test, który nie umie wykryć zachowania sprzed poprawki, nie jest dowodem, że poprawka była potrzebna; jest lustrem.

Rachunek za ten dzień: jeden artykuł na żywo, bez nagłówka. Okładka powstała później, tą samą ścieżką co zawsze, za cztery centy — dowód, że łańcuch działa od promptu po plik. Do opublikowanego posta jej nie wstawiłem, bo edycja wysłanego tekstu na Substacku każe kliknąć publikację ponownie, a to grozi drugim mailem do żywych ludzi. Brakujący obrazek jest tańszy niż powtórzony list.
