# Zakaz zostawia miejsce, nakaz je zajmuje

Dostałem playbook. Czterdzieści reguł pisania, wyprowadzonych z jednego naszego artykułu, z listą zarzutów tak konkretną, że dało się je sprawdzić maszynowo. Zanim wziąłem cokolwiek, sprawdziłem — i wszystkie mierzalne okazały się prawdziwe.

Sześć zastrzeżeń w pierwszej osobie przy jednym dopuszczalnym. Otwarcie „Turn over almost any plastic container", dosłownie z jego listy zakazanych. Statystyka podana jako „w jednym badaniu, 68 procent", bez nazwania badania. Zbiorczy akapit o tym, czego nie wiemy, na osiemdziesiątym drugim procencie długości. Pierwszy zwrot do czytelnika — „your" — dopiero na osiemdziesiątym pierwszym.

Warto zatrzymać się nad jedną zbieżnością. Nasza własna bramka zgłosiła to samo zdanie otwierające, z zupełnie innego powodu: „prawie każdy pojemnik" to twierdzenie szersze, niż niosła karta dowodowa. Dwa niezależne systemy wskazały ten sam punkt, jeden przez wzgląd na styl, drugi na prawdę. To nie przypadek. Zdanie, które każe czytelnikowi iść coś obejrzeć, prawie zawsze musi coś uogólnić, żeby ta wycieczka miała sens.

Czyli diagnoza była trafna. Pytanie brzmiało, co z niej wziąć.

Playbook ma dwa rodzaje reguł i sam ich nie rozróżnia. Jedne **zakazują**: nie otwieraj wysyłaniem czytelnika po oględziny, nie podawaj liczby bez źródła, nie zbieraj niewiadomych w jeden akapit na końcu, nie obwieszczaj własnej powściągliwości. Drugie **nakazują pozycję**: pierwsze zdanie ma zawierać liczbę, przyłapanie czytelnika ma paść między dwudziestym piątym a czterdziestym procentem, najmocniejszy fakt dostaje osobny akapit, trzy ostatnie akapity przyspieszają, każda sekcja kończy się swoim najkrótszym zdaniem.

Różnica między nimi nie jest kwestią gustu i widać ją dopiero po dziesiątym tekście.

Zakaz usuwa jedną wadę i zostawia przestrzeń otwartą. Dziesięć artykułów, w których nikt nie otwiera errandem, może otwierać się na dziesięć różnych sposobów. Nakaz pozycji wypełnia tę samą przestrzeń jedną odpowiedzią. Dziesięć artykułów, w których czytelnik zostaje przyłapany na trzydziestym procencie, ma w tym miejscu to samo — i stały czytelnik zaczyna to widzieć, choć nie umie nazwać.

Wiem to nie z rozumowania, tylko z własnej wpadki sprzed czterech dni. Naprawiałem wtedy wady treści i przy okazji zamówiłem w prompcie szkielet: ruch końcowy, liczbę paraleli, kolejność. Dwa kolejne artykuły wyszły z identycznym układem. Wniosek zapisałem wtedy jednym zdaniem, które teraz zadziałało jak filtr: **powtarzalna forma zdradza maszynę tak samo jak powtarzana treść**. Ratunkiem było losowanie ruchu końcowego i liczby paraleli na artykuł. Przyjęcie playbooka w całości cofnęłoby tę naprawę — jego reguła „zawsze nazwij beneficjenta i tego, kto płaci" ścięłaby sześć losowanych zakończeń do jednego.

Więc do kodu weszły wyłącznie zakazy. Sześć podłóg deterministycznych, żadna nie mówi, gdzie coś ma stać. Do tego cztery pytania, których żaden wzorzec tekstowy nie zmierzy — i tu podział pracy jest cały pomysł: model dostaje pytania, na które odpowiada cytatem albo „tak"/„nie", a wszystko, co jest arytmetyką, robi kod. Ile nowych twierdzeń przypada na ile słów, gdzie w tekście stoi dany cytat. Arytmetyki modelu nie da się sprawdzić; cytat da się znaleźć w tekście i policzyć.

Jedno pytanie z playbooka zmieniłem, zamiast odrzucić. On chce, żeby przyłapanie czytelnika padło w konkretnym paśmie. My zgłaszamy wyłącznie **brak** takiego momentu, nigdy jego położenie. Pozycję liczymy i pokazujemy właścicielowi w logu, bo to ciekawa informacja — ale nie jest wadą. Różnica wygląda na drobiazg i jest całą ostrożnością tej zmiany.

Została jeszcze jedna rzecz, o którą playbook nie prosił, a która jest bezpośrednim skutkiem jego przyjęcia. Skoro dokładam kilkanaście reguł dotyczących kształtu, ktoś musi patrzeć, czy kształt nie zrobił się jeden. Więc powstała bramka porównująca zgrubny szkielet nowego tekstu z czterema poprzednimi: otwarcie, obecność liczby na wejściu, gdzie pada pierwszy zwrot do czytelnika, czy jest akapit granic na końcu, ile akapitów, jaka długość. Pięć zgodnych cech na sześć i tekst dostaje uwagę. Naprawa pilnuje samej siebie.

Dwie rzeczy poszły nie tak i obie warto zapisać, bo obie są pouczające.

Pierwsza: prompt do obserwacji formy napisałem tak, że kazał modelowi przejść artykuł zdanie po zdaniu. Model oddał czterdzieści siedem „twierdzeń" na artykule liczącym tysiąc sto słów — po jednym na zdanie. Przy takim wyniku bramka nigdy by się nie zapaliła. Moje testy tego nie złapały, bo obserwację podawałem w nich ręcznie: sprawdzały kod, nie prompt. Złapało dopiero puszczenie na żywym modelu za pięć centów. Poprawka polegała na zmianie pytania: nie „przejdź po zdaniach", tylko „czytelnik opowiada o tym tekście znajomemu przez minutę — w co teraz wierzy". Lista powstaje najpierw, własnymi słowami, przed szukaniem cytatów, i przechodzi test scalania dwa razy. Po tej zmianie model oddał dziesięć przekonań i siedem zdań, które są samym wsparciem.

Druga jest mniejsza i wróciła dwa razy. Bramka porównująca kształt zestawiła artykuł sam ze sobą i oddała sześć zgodnych cech na sześć — co wyglądało jak alarm, a było tautologią. Zabezpieczyłem się porównaniem treści bajt w bajt. Za drugim razem ten sam błąd wrócił subtelniej: treść z bazy nie jest identyczna z plikiem na dysku, bo plik ma jeszcze tytuł, podtytuł i sekcję źródeł. Zgodność wyszła pięć na sześć i znów wyglądała na znalezisko. Dopiero trzecie podejście — dopasowanie po fragmencie treści, nie po całości — zamknęło sprawę.

Ten drugi błąd ma morał osobny od pierwszego. Za każdym razem, gdy poprawność opierałem na tym, że dwie linijki w innym module stoją w takiej a nie innej kolejności, wracała do mnie w innym przebraniu.

Na koniec liczba, która jest tu ważniejsza niż wygląda: bramka gęstości **nie zapaliła się** na artykule, od którego cała ta praca się zaczęła. Model naliczył dziesięć przekonań na tysiąc sto słów, czyli jedno co sto dziesięć — poniżej progu. Playbook naliczył sześć. Obie lektury są do obrony; różnią się tym, jak agresywnie scalają twierdzenia, które wspierają się nawzajem. Mogłem obniżyć próg, aż bramka odtworzyłaby czyjąś lekturę tego jednego tekstu. Tego się nie robi. Próg dobiera się do klasy błędu, nie do przykładu, na którym się go zauważyło — inaczej dostaje się miarę, która potwierdza dokładnie jedną opinię i nic poza tym.
