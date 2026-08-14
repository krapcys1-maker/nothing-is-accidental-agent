# Cztery usterki, których testy nie złapią

Dwa tysiące siedemset dziewięćdziesiąt jeden testów przechodzi. Pipeline i tak nie dowiózł artykułu. To nie jest zarzut wobec testów — to jest opis tego, gdzie mieszkają pozostałe błędy.

Wszystkie cztery usterki, które zatrzymały ten dzień, leżą na granicy z dostawcą modelu. Testy offline z definicji tej granicy nie dotykają: fake provider zawsze odpowiada, zawsze mieści się w czasie, zawsze zwraca poprawny JSON i zawsze kosztuje dokładnie tyle, ile zaplanowano. Realny nie.

**Pierwsza.** Podałem jawny limit trzydziestu centów. System zarezerwował sześć, bo tyle wyszło z „pesymistycznej" projekcji. Wywołanie kosztowało sześć i pół. Przekroczenie o trzy grosze uznano za naruszenie rezerwacji i cała próba została unieważniona — już po tym, jak dostawca dostał zapłatę. Zostały zero tematów i nierozliczona należność. Słowo „pesymistyczna" opisywało tu szacunek wejścia, nie jego ograniczenie; prompt przyszedł o siedemset tokenów większy, niż zgadła.

**Druga.** Wyjście modelu uderzyło w sufit tokenów i JSON urwał się w połowie. Ustawiłem ten sufit na tysiąc pięćset, bo tyle mówiła polityka roli — tyle że to była wartość minimalna, nie docelowa. Potem na dwa tysiące czterdzieści osiem, wzięte z tabeli zdolności modelu, która dotyczyła zupełnie innej roli. W bazie leżało jedenaście udanych przebiegów z sufitem cztery tysiące dziewięćdziesiąt sześć. Sprawdziłem je dopiero po drugiej porażce. To kosztowało czternaście centów i jest to najbardziej wstydliwa pozycja w tym rachunku, bo dowód był na wyciągnięcie jednego zapytania.

**Trzecia.** Korpus zamykał się na trzech źródłach, choć dostawca zwrócił dziesięć kandydatur. Mechanizm okazał się elegancki i przez to niewidoczny: funkcja pakująca czekała na zakończenie pobrań *zatwierdzonych*, a pętla operatorska zatwierdza je pojedynczo, bo baza dopuszcza jedno aktywne zadanie badawcze na temat. Po pierwszym pobraniu „nie ma oczekujących" było już prawdą. Korpus się zamykał, powstawało zadanie syntezy — i to zadanie samo stawało się tym jedynym aktywnym, więc pętla pobrań kończyła pracę. Siedem źródeł, w tym rządowa konsultacja i zapis debaty parlamentarnej, nie zostało nigdy tkniętych.

**Czwarta** jest moja i pokazuje, jak naprawy rodzą naprawy. Kazałem korpusowi czekać na wszystkich kandydatów. Zapomniałem, że funkcja pakująca jest wywoływana wyłącznie po *udanym* pobraniu. Ostatni kandydat zwrócił błąd dostępu — i kompletny, gotowy korpus dziewięciu źródeł nie doczekał się żadnej syntezy. Poprzednio nie miało to znaczenia, bo korpus zamykał się wcześnie. Moja poprawka odsłoniła wadę, która czekała.

Jest jeszcze piąta rzecz, i to ona zatrzymała wszystko naprawdę. Bogatszy korpus okazał się wolniejszy w syntezie i przekroczył limit czasu klienta. Połączenie zerwało się, nie wiadomo, czy dostawca zdążył policzyć. Nie ma wpisu o zużyciu, więc nie da się powiedzieć ani „zapłacono", ani „nie zapłacono". System odmawia zamknięcia takiej pozycji — i słusznie, bo obie odpowiedzi byłyby zmyślone. Zablokowana należność blokuje z kolei każdy kolejny przebieg.

To ostatnie wygląda jak wada, a jest ceną. Można zbudować system, który w takiej sytuacji wpisuje zero i jedzie dalej. Taki system nigdy się nie zatrzyma i nigdy nie będzie wiedział, ile wydał. Ten zatrzymuje się i mówi wprost: nie wiem, zapytaj człowieka. Rachunek za tę uczciwość wynosi dziś jeden zablokowany temat i pół dolara zawieszonej ekspozycji.

Warto też odnotować rzecz, która poszła lepiej, niż zakładaliśmy. Przez cały poprzedni tydzień powtarzaliśmy, że mniej więcej połowa poważnych źródeł odmawia automatowi. Przy dobrze dobranym temacie pobrało się dziewięć na dziesięć. Ta „połowa" nie była własnością internetu, tylko własnością źle dobranych tematów.
