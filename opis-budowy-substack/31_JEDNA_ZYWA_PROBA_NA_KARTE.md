# Numer wersji, który był kwitem na ponowienie

W kodzie produkcyjnym stoi jedno pole: `prompt_version`. Wygląda niewinnie — mówi, którą wersją instrukcji napisano dany artykuł. Przez ostatnie tygodnie rosło od jedynki do piątki. Żadne z tych podbić nie oznaczało zmiany instrukcji.

Każde z nich kupowało prawo do drugiej próby.

## Reguła, która chroniła nie to, co miała

Karta badawcza to najdroższa rzecz w tym systemie. Zanim model w ogóle zacznie pisać, ktoś zapłacił za wyszukanie źródeł, za ich pobranie, za syntezę — razem około dziewięćdziesięciu centów. Karta jest opłacona, sprawdzona i zamrożona: dokładne wejście, które pojedzie do modelu, zostaje zapisane wraz ze swoim odciskiem, żeby dało się później udowodnić, co dokładnie system wysłał.

I tu leżała reguła: ten odcisk musi być unikalny w całej bazie. Intencja była oczywista — konto nigdy nie ma zapłacić dwa razy za ten sam artykuł.

Czternastego sierpnia pięć przebiegów treści weszło do potoku. Cztery zginęły. Trzy na naszych własnych usterkach bramki jakości, jedna dlatego, że odpowiedź recenzenta uderzyła w sufit ośmiu tysięcy tokenów i przyszła urwana w połowie zdania. **Żaden nie zginął dlatego, że artykuł był zły.**

Ponowienie było niemożliwe. Nie „trudne" — niemożliwe. Druga próba na tej samej karcie liczyła dokładnie ten sam odcisk, bo odcisk opisuje wejście modelu i nic poza nim: nie ma w nim numeru zadania, numeru elementu ani numeru próby. Nowa próba zderzała się ze zwłokami tej, która przed chwilą padła.

Cztery karty. Trzy dolary sześćdziesiąt. Za nic.

## Dlaczego obejście było gorsze niż awaria

Skoro odcisk liczy się z zawartości, wystarczy zmienić zawartość. Podbij `prompt_version` — odcisk się zmieni, ponowienie przejdzie.

Tak właśnie robiliśmy. Pięć razy.

W bazie leży teraz pięć elementów treści na jednej karcie badawczej, każdy z innym odciskiem zamrożonego wejścia. Rejestr twierdzi, że pięć różnych wersji instrukcji wyprodukowało pięć różnych prób. Instrukcja była ta sama. Rejestr kłamie i to my kazaliśmy mu kłamać.

To jest cena, którą trudno zauważyć w momencie płacenia. Awaria kosztuje dziewięćdziesiąt centów i widać ją od razu. Obejście kosztuje wiarygodność zapisu, którego jedynym zadaniem jest być wiarygodnym — i nie widać tego nigdy, aż do dnia, w którym ktoś zapyta, który prompt napisał który tekst.

## Zdanie, które było źle napisane

Naprawa nie polegała na dopisaniu wyjątku. Polegała na przeczytaniu reguły jeszcze raz i zauważeniu, że mówi coś innego niż to, co chcieliśmy powiedzieć.

Chcieliśmy powiedzieć: *żadne dwa żywe artykuły nie mogą stać na jednej opłaconej karcie*. Żeby konto nie zapłaciło dwa razy równocześnie.

Napisaliśmy: *żadne dwa artykuły, kiedykolwiek, nie mogą stać na jednej karcie*.

Różnica to jedno słowo i cała historia. Pierwsza wersja chroni **jednoczesność**. Druga chroni **historię** — a historii nie trzeba chronić, historia już się wydarzyła i nikomu nie zaszkodzi.

Reguła brzmi teraz tak, jak od początku miała brzmieć: kiedy próba umiera, jej zamrożone wejście dostaje znacznik „zastąpione" i przestaje zajmować żywe miejsce. Karta jest znów wolna. Kolejna próba zamraża **dokładnie to samo wejście**, bajt w bajt, bez żadnego udawania — i to jest cały sens: ponowienie nie musi już niczego fałszować.

## Ta sama blokada, dwa razy

Najbardziej pouczające w tej naprawie było to, że pierwsza wersja diagnozy była niepełna, i to w sposób, który wyglądałby jak sukces.

Blokada istniała **dwa razy**. Raz na odcisku zamrożonego wejścia, drugi raz na zupełnie innej kolumnie w innej tabeli — policzonej z tych samych pięciu faktów, tą samą metodą, z tym samym brakiem numeru zadania. Zdjęcie tylko pierwszej pozwoliłoby ponowieniu zajść jedno zdanie dalej i umrzeć na identycznym błędzie, z identycznym komunikatem. Już po przebudowaniu tabeli na produkcyjnej bazie.

Duplikaty logiki nie mają wspólnego autora ani wspólnej nazwy. Mają wspólny kształt. Znaleźć je można tylko szukając kształtu.

## Miejsce, gdzie postawiono stempel

Znacznik „zastąpione" mógł stawiać kod. Byłoby to prostsze i całkowicie wystarczające — dziś.

Postawiono go w bazie, na poziomie reguły, która odpala się przy każdym zapisie kończącym próbę niepowodzeniem. Powód jest jeden: kod w Pythonie chroni ścieżki, które istnieją teraz. Reguła w bazie chroni także tę, którą ktoś dopisze za pół roku, nie pamiętając o niczym z tego dokumentu.

Ta sama zasada kazała domknąć dziurę, która nie istniała, dopóki naprawa jej nie otworzyła: właściciel ma prawo ręcznie wznowić martwy element do ponownej recenzji. Gdyby w międzyczasie ponowienie zajęło żywe miejsce, wznowienie stworzyłoby dwa żywe artykuły na jednej karcie — czyli dokładnie to, przed czym cała reguła miała chronić. Wznowienie odbiera więc miejsce z powrotem, a jeśli jest zajęte, cała operacja pada zamknięta, zanim cokolwiek zdąży się zmienić.

Naprawa, która otwiera nową dziurę, nie jest naprawą. To jest ta sama praca, tylko przesunięta o metr.

## Granica, której nie przekroczono

Zwolnione zostały wyłącznie próby jawnie nieudane.

Zostaje trzecia kategoria: próby, po których nie wiadomo, czy dostawca zdążył wyprodukować i policzyć artykuł. Przerwane połączenie, brak wpisu o zużyciu, brak potwierdzenia w którąkolwiek stronę. Kuszące byłoby zwolnić i je — to trzy dalsze karty, prawie trzy dolary.

Nie zwolniono. Odblokowanie karty, za którą być może już zapłacono za gotowy tekst, jest decyzją o pieniądzach, a nie o kształcie tabeli. Wymaga własnego rejestru zgód i podpisu człowieka. Trzy karty zostają martwe i jest to zapisane jako koszt, nie przemilczane.

Odrzucono też pokusę, która wygląda na rozsądny kompromis: listę „technicznych" powodów awarii, które automatycznie zwalniają kartę. To dokładnie ten sam błąd, tylko piętro wyżej. Pierwszy powód, którego nikt nie przewidział — a takie zawsze przychodzą — znów zabiłby kartę na zawsze.

## Co z tego zostaje

Ograniczenie, którego jedynym obejściem jest fałszowanie danych wejściowych, nie jest ograniczeniem. Jest podatkiem od uczciwości rejestru — i płaci się go za każdym razem, gdy ktoś wybierze pracujący system zamiast prawdziwego zapisu.

Zmiana nie została jeszcze zastosowana na produkcyjnej bazie. Czeka na przegląd i osobną zgodę, bo dotyka trzynastu trwałych wierszy w rejestrze, który z założenia jest tylko do dopisywania.
