# Style notek i komentarzy o AI

Osobny materiał referencyjny dla krótkich form w `agent-v2`. Stan profili i liczby subskrybentów sprawdzono 1 września 2026 roku.

Ten dokument nie zastępuje reguł wykonawczych w `prompts/notka.md`, `prompts/komentarz.md` ani `config.py`. Jego rolą jest pokazanie, jak dobrzy autorzy wykonują konkretne ruchy w krótkich publikacjach i rozmowach. Nie jest instrukcją kopiowania charakterystycznego głosu żadnej osoby.

## Dlaczego styl powinien być osobny od stylu artykułów

Artykuł ma zbudować i udowodnić tezę. Notka ma sprawić, że jedna rzecz stanie się natychmiast zrozumiała. Komentarz ma zmienić albo rozwinąć rozmowę rozpoczętą przez kogoś innego.

| Forma | Główne zadanie | Jednostka treści | Najczęstsza porażka |
|---|---|---|---|
| Artykuł | Udowodnić tezę | Argument złożony z kilku części | Długi tekst bez wyraźnej stawki |
| Notka | Zatrzymać na jednej rzeczy | Jeden fakt, kontrast, mechanizm albo uczciwa myśl | Streszczenie artykułu albo ciekawostka bez konsekwencji |
| Komentarz | Wnieść coś do cudzej rozmowy | Jedna uwaga skierowana do konkretnej osoby | Mini-esej, korekta nauczycielska albo puste poparcie |

To rozróżnienie odpowiada obecnym kontraktom projektu: notka ma 33–64 słowa (`config.py:845-846`), a komentarz ma jedną myśl w dwóch–czterech zdaniach (`prompts/komentarz.md:17-18`). Komentarze dodatkowo losują różne długości i postawy (`config.py:1062`, `config.py:1091`), więc wzorzec nie może wymuszać jednej sylwetki każdej wypowiedzi.

## Profile wybrane jako materiał porównawczy

| Profil | Publiczność | Najlepszy wzorzec |
|---|---:|---|
| [Ethan Mollick](https://substack.com/@oneusefulthing) | 471 tys.+ | Krótka zapowiedź użytecznego materiału przez pytanie, które naprawdę słyszy od czytelników |
| [Gary Marcus](https://substack.com/@garymarcus) | 114 tys.+ | Mocny sprzeciw oparty na jednym kontraście lub kontrprzykładzie |
| [Arvind Narayanan](https://substack.com/@aisnakeoil) | 83 tys.+ | Rozdzielenie dwóch mechanizmów, które debata błędnie traktuje jako jeden |
| [Nathan Lambert](https://substack.com/@natolambert) | 80 tys.+ | Techniczna teza, jeden rachunek i jedna konsekwencja |
| [Simon Willison](https://substack.com/@simonw) | 70 tys.+ | Sprawdzona obserwacja z demonstracją lub śladem pozwalającym ją zweryfikować |
| [Rohit Krishnan](https://substack.com/@strangeloopcanon) | 28 tys.+ | Restack lub komentarz, który dopowiada mechanizm pominięty przez autora |
| [Nabeel S. Qureshi](https://substack.com/@nabeelqu) | 22 tys.+ | Wyraźne stanowisko, konkretna alternatywa i budowanie rozmowy przez odpowiedzi |

Wielkość profilu nie jest miarą jakości pojedynczej notki. Liczby służą tylko do potwierdzenia, że są to głosy z realną publicznością, a nie przypadkowe przykłady znalezione w wynikach wyszukiwania.

## 1. Nathan Lambert — techniczna teza skompresowana do jednego ruchu

### Jak buduje notkę

Lambert często zaczyna od korekty popularnego porównania albo od zdania, które można uznać za prognozę. Następnie podaje jeden mechanizm lub prosty rachunek. Ostatnia część mówi, co zmieni się, jeśli rachunek będzie się utrzymywał.

Jego skuteczny schemat wygląda tak:

1. nie `X`, tylko `Y`;
2. jedna liczba albo relacja przyczynowa;
3. konsekwencja dla ceny, dostępności, badań lub władzy.

W notce porównującej rozwój AI z prawem Moore’a nie poprzestaje na metaforze. Podaje tempo poprawy wydajności, przelicza je na pięć i dziesięć lat, a dopiero potem nazywa możliwy skutek gospodarczy. Dzięki temu finał jest wnioskiem z liczby, a nie ozdobnym hasłem.

### Jak zabiera głos w rozmowie

- Potrafi zaznaczyć dwie rzeczy naraz: krytykę działań firmy oraz mocniejszą krytykę reakcji państwa.
- Nie udaje, że każda kwestia ma jeden czysty obóz.
- W krótkiej odpowiedzi potrafi ograniczyć się do oceny stanu możliwości bez dopisywania całej teorii.
- Gdy temat jest szeroki, przechodzi w listę prognoz zamiast ściskać wiele tez w jeden akapit.

### Co przejąć

- Jedną sprawdzalną relację liczbową zamiast serii benchmarków.
- Nazwanie konsekwencji dopiero po pokazaniu mechanizmu.
- Możliwość zajęcia stanowiska pomiędzy dwoma gotowymi obozami.
- Rozróżnienie krótkiej notki od listy prognoz; projektu obowiązuje limit 33–64 słów, więc z listy trzeba wybrać tylko jeden punkt.

### Czego nie przejmować

- Żargonu zrozumiałego wyłącznie dla osób śledzących każdą premierę modeli.
- Kilku prognoz w jednej notce projektu.
- Mocnego wniosku z liczby, jeśli rachunek nie uwzględnia kosztu, jednostki albo warunku utrzymania trendu.

### Przykłady

- [Porównanie wydajności AI z prawem Moore’a](https://substack.com/@natolambert/note/c-300954439) — teza, rachunek i konsekwencja.
- [Próba utrzymania dwóch ocen naraz](https://substack.com/@natolambert/note/c-276255207) — krótka notka, która nie przyjmuje fałszywego wyboru między firmą a administracją.
- [Co naprawdę jest odpowiednikiem open source w AI](https://substack.com/@natolambert/note/c-316644076) — jedno rozróżnienie pojęciowe zastosowane do sporu o otwarte modele.

## 2. Simon Willison — najpierw ślad, potem opinia

### Jak buduje krótką publikację

Willison prowadzi własny strumień notek i linków, który pełni podobną funkcję do Substack Notes. Najczęściej bierze jedną rzecz, którą właśnie uruchomił, przeczytał albo sprawdził. Podaje konkretny szczegół i dopiero po nim własną ocenę.

Jego podstawowe ruchy:

- `sprawdziłem artefakt → oto ślad → ten szczegół zmienia ocenę`;
- `źródło twierdzi X → dodatkowy kontekst Y → dzięki temu zdarzenie staje się łatwiejsze do wyjaśnienia`;
- `stara czynność była możliwa, ale nieopłacalna → AI zmieniło koszt próby → zmieniło się zachowanie ludzi`.

W notce o automatyzowaniu urządzeń domowych nie twierdzi po prostu, że agenci „demokratyzują programowanie”. Pokazuje zmianę rachunku: spadł koszt napisania, nieudanej próby i późniejszego wyrzucenia kodu. To mechanizm, który można przenieść na inne dziedziny.

### Jak komentuje i koryguje

- Zaczyna od obiektu: komendy, dokumentu, logu, wyniku testu albo konkretnego zachowania produktu.
- Wskazuje dowód, który inna osoba może odtworzyć.
- Rozdziela to, co zobaczył, od tego, co z tego wnioskuje.
- Jeśli cudze wyjaśnienie zmienia jego rozumienie sprawy, mówi dokładnie, który brakujący szczegół to zrobił.

### Co przejąć

- Prymat weryfikowalnego śladu nad ogólnym autorytetem autora.
- Jedno doświadczenie lub dokument jako rdzeń notki, bez dokładania pięciu pobocznych nowości.
- Komentarz typu `KONKRET`: jeden dowód i jedno zdanie mówiące, dlaczego ten dowód ma znaczenie.
- Komentarz typu `KOREKTA`: najpierw fakt, z którego wynika różnica; czytelnik sam widzi sprzeciw.

### Czego nie przejmować

- Sformułowania „sprawdziłem” albo „uruchomiłem” w anonimowej marce, jeśli agent tego rzeczywiście nie zrobił.
- Technicznych identyfikatorów, które nie są potrzebne do zrozumienia rzeczy.
- Entuzjazmu dla narzędzia jako substytutu wyniku testu.

### Przykłady

- [Reverse-engineering is cheap now](https://simonwillison.net/2026/Jul/20/cheap-reverse-engineering/) — notka oparta na zmianie ekonomii małych projektów.
- [Nativ: Run AI models locally on your Mac](https://simonwillison.net/2026/Jul/21/nativ/) — krótki link-post zawierający funkcję produktu, porównanie i jeden detal z próby.
- [Investigating three real-world incidents in our cybersecurity evaluations](https://simonwillison.net/2026/Jul/30/three-real-world-incidents/) — przykład przejścia od danych źródłowych do precyzyjnie ograniczonego ostrzeżenia.
- [Strumień krótkich notek Willisona](https://simonwillison.net/notes/) — dobry materiał do obserwowania zmienności długości i formy.

## 3. Arvind Narayanan — kontrast, który porządkuje spór

### Jak buduje notkę

Narayanan często zauważa, że dwie osoby mogą patrzeć na ten sam system i uczciwie dojść do przeciwnych wniosków, ponieważ używają go w innych warunkach. Nadaje tym warunkom osobne nazwy, a następnie pokazuje mechanizm każdej ścieżki.

Przykładowe rozdzielenia z jego notek:

- używanie AI w dziedzinie własnej ekspertyzy kontra delegowanie dziedziny, której się nie rozumie;
- szybkość wzrostu możliwości kontra szybkość wdrażania ich przez organizacje;
- sporadyczne użycie chatbota kontra przebudowa całego procesu pracy;
- atrakcyjnie prosta obsługa kontra coraz trudniejsza weryfikacja ukrytych działań agenta.

To szczególnie użyteczny wzorzec dla projektu, ponieważ notka może złamać przekonanie bez polemiki. Wystarczy pokazać, że jedno słowo używane w dyskusji opisuje dwa różne zjawiska.

### Jak odpowiada w dyskusji

- Najpierw ustala warunek, od którego zależy prawdziwość tezy.
- Nie pyta tylko, czy AI „działa”, lecz kto potrafi ocenić wynik i kto odpowiada za błąd.
- Zamiast prostego za/przeciw buduje dwie ścieżki przyczynowe.
- Pozostawia miejsce na zmianę wniosku, wskazując brakujące pomiary lub bariery wdrożenia.

### Co przejąć

- Formę `KONTRAST`: te same narzędzia, inne warunki, przeciwne skutki.
- Nazwanie różnicy dopiero po pokazaniu obu stron.
- Komentarz typu `MECHANIZM` lub `ROZSZERZENIE`, który ujawnia brakujący etap między możliwością a skutkiem.
- Rozróżnienie możliwości, niezawodności i instytucjonalnego wdrożenia.

### Czego nie przejmować

- Długości jego pełnych notek. W projekcie należy wydobyć jeden kontrast, a nie streszczać cały model.
- Nowej nazwy dla każdej drobnej różnicy.
- Pierwszoosobowych opisów pracy, których anonimowa marka nie może uczciwie przypisać sobie.

### Przykłady

- [Growth cycle kontra dependence spiral](https://substack.com/@aisnakeoil/note/c-274974582) — dwie ścieżki używania tego samego narzędzia.
- [Paradoks magicznego interfejsu i trudniejszej weryfikacji](https://substack.com/@aisnakeoil/note/c-259452894) — dobry wzorzec notki rozpoczynanej od sprzeczności.
- [Dlaczego możliwość i adopcja poruszają się w innym tempie](https://substack.com/@aisnakeoil/note/c-225213445) — przykład rozbrojenia wykresu przez wskazanie pomieszanych kategorii.

## 4. Rohit Krishnan — najlepszy wzorzec dopowiedzenia mechanizmu

### Jak buduje restack i komentarz

Krishnan często zaczyna od uznania konkretnej rzeczy w cudzym tekście, ale nie kończy na pochwale. Natychmiast dopowiada mechanizm albo skutek drugiego rzędu, którego autor nie rozwinął.

Najczystszy schemat:

1. wskazanie dokładnej myśli z cudzej publikacji;
2. dopowiedzenie, co przesuwa się w systemie, gdy ta myśl jest prawdziwa;
3. nowa konsekwencja albo uczciwa niepewność.

W restacku tekstu o medycznych notatkach generowanych przez AI zauważa, że automatyzacja nie usuwa myślenia. Przenosi je w inne miejsce procesu, a wraz z nim zmienia osąd lekarza. To nie jest streszczenie ani korekta. To druga warstwa mechanizmu.

### Jak się nie zgadza

- Potrafi najpierw wymienić rzeczy, które uważa za trafne.
- Następnie nazywa dokładny punkt, w którym założenie przestaje działać.
- Pyta o działanie propozycji w konkretnym scenariuszu, zamiast atakować intencje autora.
- Zaznacza warunek zmiany własnej opinii.

### Co przejąć

- Domyślną postawę `MECHANIZM`: cudzy tekst pokazuje zdarzenie, komentarz pokazuje siłę, która je wytwarza.
- `ZGODA_Z_DOPOWIEDZENIEM`, w której dopowiedzenie naprawdę zmienia obraz, a nie tylko pokazuje wiedzę komentującego.
- Krótką odpowiedź bez obowiązku imponowania, jeśli cały wkład mieści się w jednym zdaniu.
- Restack, który objaśnia, po co udostępniany tekst jest ważny dla innego problemu.

### Czego nie przejmować

- Długości jego rozbudowanych notek i wielopunktowych polemik.
- Potocznych skrótów, jeśli czynią sens zależnym od znajomości niszowej debaty.
- Rozpoczynania pustym „dobrze powiedziane”. Krishnan czasem tak robi, ale taki wpis nie wnosi nic samodzielnie i nie pasuje do kontraktu projektu.

### Przykłady

- [Dopowiedzenie o przesuwającym się wąskim gardle](https://substack.com/@strangeloopcanon/note/c-244465930) — bardzo dobry wzorzec restacku opartego na mechanizmie.
- [Poparcie idei połączone z pytaniem o jej realne znaczenie](https://substack.com/profile/12282408-rohit-krishnan/note/c-320675727) — zgoda, zastrzeżenie i konkretna przyczyna w jednym ruchu.
- [Krótka odpowiedź o granicy obecnych możliwości](https://substack.com/profile/12282408-rohit-krishnan/note/c-306989714) — przykład, że pełna odpowiedź nie musi mieć akapitu.
- [Krytyka scenariusza AI 2040](https://substack.com/@strangeloopcanon/note/c-291665753) — materiał do analizy konstruktywnego sprzeciwu; nie jest wzorcem długości.

## 5. Nabeel S. Qureshi — stanowisko, które zostawia miejsce na odpowiedź

### Jak buduje krótką wypowiedź

Qureshi często wybiera zdarzenie, stawia wobec niego jasną alternatywę i kończy bez dodatkowej dekoracji. W notce o opowiadaniu prawdopodobnie wygenerowanym przez AI nie rozwija całej debaty o sztuce. Wskazuje zdarzenie i dwie możliwe reguły dla konkursów. Czytelnik ma konkretny wybór, z którym może się zgodzić albo spierać.

W szerszym podejściu do krótkich publikacji traktuje je jako publiczny dziennik myśli i generator tematów do późniejszych esejów. Zaleca pisać dla rodzaju ludzi, których chce się przyciągnąć, a nie dla maksymalnego zasięgu pojedynczego wpisu.

### Jak prowadzi rozmowę

- Preferuje ruch `tak, i`: dodanie nowej obserwacji zamiast potakiwania.
- Ostrzega przed wejściem w spór bez wcześniejszego zbudowania relacji.
- Odpowiada na pytanie wprost, a dopiero potem dodaje przykład lub ograniczenie.
- Nie próbuje wygrać każdej wymiany; celem jest znalezienie ludzi i idei, z którymi warto kontynuować rozmowę.

### Co przejąć

- Notkę typu `MYSL`, która zawiera określone stanowisko, ale nie przemyca nieudokumentowanego faktu.
- Prostą alternatywę: jeśli nie akceptujemy obecnej reguły, jakie dwie realne zasady pozostają?
- Pytanie, na którego odpowiedzi autor rzeczywiście jest ciekawy.
- W komentarzach: nową obserwację, nie pochwałę i nie pokaz erudycji.

### Czego nie przejmować

- Kategorycznego zakończenia, jeśli alternatywy nie zostały naprawdę wyczerpane.
- Perspektywy osobistej w typach notek, którym projekt zabrania pierwszoosobowego doświadczenia.
- Publikowania myśli tylko dlatego, że może być wiralowa; profil ma przyciągać właściwych czytelników, nie dowolny ruch.

### Przykłady

- [Notka o tekście wygenerowanym przez AI i nagrodzie literackiej](https://substack.com/@nabeelqu/note/c-279621480) — zdarzenie, stanowisko i konkretna alternatywa.
- [The Serendipity Machine](https://nabeelqu.substack.com/p/the-serendipity-machine) — opis filozofii krótkich publikacji oraz zasady odpowiadania częściej niż nadawania na początku rozwoju profilu.
- [Odpowiedź autora pod „How To Understand Things”](https://nabeelqu.substack.com/p/understanding/comments) — przykład bezpośredniej odpowiedzi, przykładu i krótkiego zastrzeżenia.

## 6. Ethan Mollick — notka jako dobre wejście do materiału

### Jak buduje krótką zapowiedź

Mollick wykorzystuje notkę promującą artykuł przede wszystkim do nazwania problemu czytelnika. Nie streszcza całego materiału i nie otwiera pustym „opublikowałem nowy tekst”. Wskazuje pytania, które regularnie słyszy, a następnie mówi, że tekst próbuje na nie odpowiedzieć.

Ten ruch działa, ponieważ link jest rozwiązaniem nazwanego problemu, a nie jedyną treścią notki.

### Co przejąć

- W notce promującej artykuł zacząć od problemu albo decyzji czytelnika.
- Obiecać dokładnie to, co artykuł rzeczywiście dostarcza.
- Nie próbować upchnąć w notce skrótu wszystkich sekcji tekstu.
- Użyć dwóch naturalnie powiązanych pytań tylko wtedy, gdy artykuł odpowiada na oba.

### Czego nie przejmować

- Formuły „często mnie pytają” w anonimowej marce, jeśli konto nie ma dowodu, że rzeczywiście otrzymuje takie pytania.
- Pierwszoosobowej praktyki wykładowcy lub badacza.
- Promowania każdego artykułu tym samym schematem pytań.

### Przykład

- [Zapowiedź przewodnika „Using AI Right Now”](https://substack.com/@oneusefulthing/note/c-128638385) — krótka identyfikacja dwóch problemów czytelnika i uczciwa obietnica zakresu artykułu.

## 7. Gary Marcus — specjalista od sprzeciwu, nie głos domyślny

### Jak buduje notkę

Marcus często zaczyna od intuicji, która powinna być prawdziwa, a w drugim bloku pokazuje, dlaczego według niego nie jest. Chętnie restackuje cudzą obserwację i dokłada jedno zdanie wiążące ją z fundamentalnym ograniczeniem modeli.

Jego skuteczny krótki ruch to:

1. powszechne oczekiwanie;
2. wyraźne „ale”;
3. jedna przyczyna techniczna albo kontrprzykład.

### Jak się nie zgadza

- Celuje bezpośrednio w twierdzenie.
- Nie ukrywa stanowiska pod serią grzecznościowych zastrzeżeń.
- Używa jednego przykładu jako klina podważającego zbyt szeroką tezę.
- Często kończy wcześniej, niż zrobiłby to autor explainera.

### Co przejąć

- Postawę `SPRZECIW` tylko wtedy, gdy jest dostępny konkretny kontrprzykład.
- Krótki kontrast między oczekiwaniem a zachowaniem systemu.
- Zdanie, które mówi, jaki mechanizm łączy przykład z szerszym problemem.
- Gotowość do niepozostawiania fałszywej symetrii tam, gdzie dowody są jednostronne.

### Czego nie przejmować

- Stałego tonu konfliktu. Konto, które reaguje sprzeciwem na wszystko, staje się przewidywalne i monotonne.
- Sarkastycznych jednozdaniowych restacków, które działają tylko dla osób już podzielających stanowisko.
- Wnioskowania o całej technologii na podstawie jednego medialnego błędu.
- Powtarzania wcześniejszej racji autora jako głównego dowodu obecnej tezy.

### Przykłady

- [Notka o automatyzacji i probabilistyczności modeli](https://substack.com/@garymarcus/note/c-282295434) — oczekiwanie, kontrast i przyczyna.
- [Zastrzeżenie wobec założenia, że infrastruktura po bańce zawsze pozostaje użyteczna](https://substack.com/@garymarcus/note/c-172815004) — restack rozszerzony o kontrprzykłady historyczne.
- [Krótki sarkastyczny restack „we wanted AGI”](https://substack.com/@garymarcus/note/c-189168099) — przykład rozpoznawalny i angażujący, ale niezalecany jako domyślna forma marki.

## Rekomendowany miks dla notek projektu

Rdzeń powinien pochodzić z trzech technik, a nie z jednego nazwiska:

1. **Simon Willison:** rzecz możliwa do sprawdzenia i jeden szczegół, który naprawdę zmienia ocenę.
2. **Nathan Lambert:** jedna relacja liczbowa lub techniczna i wynikająca z niej konsekwencja.
3. **Arvind Narayanan:** rozdzielenie dwóch mechanizmów ukrytych pod jednym słowem.

Techniki używane okresowo:

- **Nabeel Qureshi:** określone stanowisko w notce typu `MYSL` albo realna alternatywa do dyskusji.
- **Ethan Mollick:** promowanie artykułu przez problem czytelnika, a nie przez streszczenie publikacji.
- **Rohit Krishnan:** restack, który dopowiada skutek drugiego rzędu.
- **Gary Marcus:** rzadki sprzeciw z konkretnym kontrprzykładem.

### Sześć użytecznych form notki

| Forma | Konstrukcja | Główny wzorzec |
|---|---|---|
| Ślad | Fakt lub wynik testu → jeden szczegół → znaczenie | Willison |
| Rachunek | Teza → jedna liczba → konsekwencja | Lambert |
| Rozdzielenie | To samo słowo → dwa mechanizmy → przeciwne skutki | Narayanan |
| Alternatywa | Zdarzenie → dwie realne zasady lub decyzje | Qureshi |
| Dopowiedzenie | Cudza rzecz → pominięty mechanizm → dalszy skutek | Krishnan |
| Sprzeciw | Oczekiwanie → kontrprzykład → przyczyna | Marcus |

Notka projektu wybiera jedną z tych form. Nie łączy rachunku, kontrprzykładu, listy i pytania w 64 słowach.

## Rekomendowany miks dla komentarzy projektu

Komentarz nie powinien być skróconą notką. Jest zależny od treści, pod którą stoi. Najlepszy domyślny głos to połączenie Krishnana i Willisona: dopowiedzenie mechanizmu oraz konkretny ślad. Qureshi dostarcza modelu rozmowy, a Marcus modelu rzadkiego, jasnego sprzeciwu.

### Mapa do istniejących postaw w `config.py`

| Postawa projektu | Profil referencyjny | Co komentarz ma zrobić |
|---|---|---|
| `CIEKAWOSC` | Qureshi | Pociągnąć luźny wątek, którego odpowiedź rzeczywiście byłaby interesująca |
| `MECHANIZM` | Krishnan | Nazwać bodziec, koszt albo ograniczenie powodujące opisane zdarzenie |
| `KONKRET` | Willison | Dodać jeden sprawdzalny artefakt i powiedzieć, dlaczego zmienia odczytanie tekstu |
| `ROZSZERZENIE` | Narayanan | Pokazać ten sam mechanizm w innych warunkach albo na innym poziomie systemu |
| `PYTANIE` | Qureshi | Zapytać o rzecz pozostawioną naprawdę otwartą, bez ukrytej odpowiedzi |
| `SPRZECIW` | Marcus | Podważyć jedno nazwane twierdzenie jednym kontrprzykładem |
| `KOREKTA` | Willison | Podać dowód; nie zaczynać od oznajmienia autorowi, że się myli |
| `ZGODA_Z_DOPOWIEDZENIEM` | Krishnan | Dodać skutek drugiego rzędu, bez którego obraz był niepełny |

### Test komentarza przed publikacją

1. Czy bez cudzej publikacji ten tekst nadal wygląda jak samodzielny mini-esej? Jeśli tak, to prawdopodobnie nie jest komentarz.
2. Czy wskazuje dokładnie, do której myśli autora odpowiada?
3. Czy dodaje jedną rzecz, której w publikacji nie było?
4. Czy ta rzecz jest mechanizmem, konkretem, rozszerzeniem, pytaniem albo kontrprzykładem?
5. Czy można usunąć powitanie, pochwałę i podsumowanie bez utraty treści?
6. Czy fakt ma pokrycie, a nie pochodzi z pamięci modelu?
7. Czy najkrótsza uczciwa wersja nie jest lepsza?

Jeśli odpowiedź na punkt trzeci brzmi „nie”, właściwym komentarzem jest cisza.

## Notka, komentarz i odpowiedź na ten sam materiał

Załóżmy, że źródło pokazuje spadek kosztu wykonania zadania przez agenta.

- **Artykuł** bada dane, metodę pomiaru, przyczynę spadku, bariery wdrożenia i skutki dla rynku pracy.
- **Notka** wybiera jedną konsekwencję spadku kosztu, którą da się zrozumieć bez znajomości reszty materiału.
- **Komentarz** odnosi spadek kosztu do konkretnego założenia autora, np. wskazuje, że niższy koszt próby zmienia także opłacalność porzucania nieudanego kodu.
- **Odpowiedź** reaguje na to, co rozmówca dopowiedział: przyznaje trafną korektę, odpowiada na pytanie albo precyzuje granicę tezy.

Te cztery teksty nie powinny być czterema długościami tego samego akapitu.

## Ostateczna rekomendacja

Dla notek bazą powinny być: **Willison + Lambert + Narayanan**.

Dla komentarzy bazą powinny być: **Krishnan + Willison**, z podejściem Qureshiego do budowania rozmowy.

Marcus powinien działać jako rzadka postawa sprzeciwu, Mollick jako wzorzec notki promującej artykuł, a Qureshi także jako wzorzec notki typu `MYSL`. Taki podział daje krótkim formom własny charakter bez zamieniania profilu w kopię jednego autora.
