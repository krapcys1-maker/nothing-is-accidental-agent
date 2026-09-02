# Gruntowny audyt agenta v2

Data audytu: 2026-09-02  
Audytowany stan: `main`, commit `20bc0627655667522b7787549f41db0905f1f14a`  
Zakres: `agent-v2/`; bez `archiwum/`, bez `agent-v3/`, bez galezi pamieci.  
Zmiany w kodzie podczas audytu: zadne.

## 1. Werdykt

| Wymaganie wlasciciela | Werdykt | Stan faktyczny |
|---|---|---|
| 100% deterministyczny | **NIE** przy literalnym znaczeniu | Czesc budzetowa jest deterministyczna z daty, ale wybor tresci, kolejnosc celow, odstepy, godziny startu i odpowiedzi modeli sa celowo losowe. |
| Drobny blad jest lepszy niz brak publikacji | **CZESCIOWO TAK** | Zwykle bledy recenzji, formy, grafiki i sprawdzania faktow nie blokuja. Nieudana publikacja artykulu jest jednak zamykana jako `DONE`, bez automatycznej ponownej proby. |
| Tylko AI | **MOCNO WYMUSZANE, ALE NIE GWARANTOWANE** | Tematy, skaut, bank, notki, artykuly i wybor celow sa ustawione na AI. Ostateczna zgodnosc tematyczna jest jednak osadem modelu, nie deterministyczna bramka kodowa. |
| 5 notek dziennie | **NIE jako gwarancja dobowa** | Zwykly budzet wynosi 5, ale cichy dzien zeruje wszystkie notki; po awarii przebiegu rozdzielnik nie domyka reszty zgodnie z komentarzem. |
| Około 20-30 komentarzy dziennie | **NIE** | Konfiguracja daje 15-23, a przez pierwsze 30 dni efektywnie 15-19. Dwa bloki moga tez zuzyc ten sam przydzial niezaleznie i przekroczyc limit. |
| 1 artykul miesiecznie | **NIE** | Zegar produkcyjny uruchamia artykul co wtorek, czyli jeden tygodniowo. |
| Restacki, lajki, obserwacje, subskrypcje | **ZGODNE Z OBECNYMI STALYMI, NIE ZAGWARANTOWANE** | Ustawione sa: restacki 1-2/dobe, lajki 10-16/dobe, obserwacje 10-16/miesiac, subskrypcje 12-20/miesiac; cichy dzien zeruje restacki, a rozbieg obniza czesc widelek. |
| Pamiec dopiero na osobnej galezi | **TAK** | W audytowanym drzewie `main` nie ma modulu `opinie.py`, integracji Hindsight ani operacji `reflect`; audyt nie ocenial galezi `pamiec/oszacowania`. |
| Mapa projektu odpowiada rzeczywistosci | **CZESCIOWO** | Zalaczniki generowane z AST sa aktualne, ale reczne rozdzialy mapy, README i doktryna zawieraja stare liczby, harmonogram i cel artykulow. |

Najwazniejsze rozroznienie: jesli „100% deterministyczny” mialo znaczyc „100% autonomiczny, bez zgody czlowieka”, ten warunek jest w duzej mierze spelniony: doktryna nakazuje brak zgod i preferuje publikacje z drobnym bledem (`agent-v2/DOKTRYNA.md:19-24`). Jesli znaczy „te same wejscia zawsze daja te same decyzje i wynik”, system tego warunku nie spelnia.

## 2. Co jest dobre i zgodne z zalozeniami

### 2.1. Autonomia i odpornosc na drobne bledy

- Dzien jest rozbity na dziewiec niezaleznych blokow; zwykly wyjatek w jednym jest zapisywany, a pozostale bloki ida dalej (`agent-v2/run.py:1071-1101`, `agent-v2/run.py:2030-2036`).
- Wyczerpanie budzetu i blad preflightu sa odroznione od lokalnej awarii i koncza caly przebieg, zamiast generowac serie takich samych bledow (`agent-v2/run.py:1074-1097`).
- Nieudane pobranie statystyk nie zatrzymuje odpowiedzi ani publikacji (`agent-v2/run.py:1123-1129`).
- Recenzja i obserwacja formy artykulu sa informacyjne. Zwykla awaria tych etapow prowadzi dalej, a uwagi nie blokuja (`agent-v2/artykul_z_puli.py:1197-1230`, `agent-v2/artykul_z_puli.py:1243-1282`).
- Grafika jest dodatkiem: kazdy blad generowania lub zapisu jest lapany, a artykul wychodzi bez niej (`agent-v2/stages.py:751-778`).
- Ostateczne sprawdzenie faktow zapisuje zastrzezenia, ale samo `safe_to_post=False` nie zatrzymuje artykulu (`agent-v2/artykul_z_puli.py:1349-1367`).
- Przy braku budzetu po napisaniu tekst jest ratowany poza normalnym katalogiem artykulow, a wyjatek pozostaje widoczny (`agent-v2/artykul_z_puli.py:1214-1225`, `agent-v2/artykul_z_puli.py:1243-1256`).

### 2.2. Kierunek AI

- Cala aktywna lista dziedzin dotyczy systemow AI, ich ewaluacji, infrastruktury, zastosowan i regulacji (`agent-v2/config.py:892-967`).
- System skauta nazywa pismo publikacja o sztucznej inteligencji (`agent-v2/stages.py:49-58`).
- System szukania faktow rowniez wymaga materialu o AI i zrodel (`agent-v2/stages.py:1099-1114`).
- Prompt wyboru komentarzy wymaga, by czytelnik celu mial powod obserwowac publikacje o AI; wyklucza zwykle systemy bez maszyny (`agent-v2/prompts/cele.md:7-16`, `agent-v2/prompts/cele.md:25-40`).
- Brief artykulu z puli mowi wprost, ze tekst ma byc o sztucznej inteligencji (`agent-v2/artykul_z_puli.py:75-89`).
- Bank dopuszcza odrzucenie `NOT_AI`, a ranking jest opisany jako ranking faktow dla publikacji o AI (`agent-v2/stages.py:6205-6208`, `agent-v2/stages.py:6306-6337`).
- Test ochronny skanuje stare wzorce tematyczne i osobno wymaga nazwania AI w promptach tematycznych (`agent-v2/tests/test_prompty_o_ai.py:115-165`, `agent-v2/tests/test_prompty_o_ai.py:345-357`). Test przeszedl w audytowanym commicie.

### 2.3. Liczby i routing modeli

- Produkcyjny routing podstawowych etapow odpowiada podanym wartosciom: notka to `claude-opus-5`, pisarz artykulu to `claude-fable-5`, etapy Pro i Flash sa rozdzielone w `MODEL_FOR` (`agent-v2/config.py:104-108`, `agent-v2/config.py:113-154`, `agent-v2/config.py:200-243`).
- Zwykly dzien ma piec typow notek, wiec podstawowy budzet wynosi 5 (`agent-v2/config.py:1580-1584`, `agent-v2/stages.py:860-869`).
- Aktualne stale spoleczne sa zapisane w jednym miejscu: lajki 10-16, komentarze 15-23, obserwacje 10-16/miesiac, subskrypcje 12-20/miesiac, restacki 1-2 (`agent-v2/config.py:1613-1627`, `agent-v2/config.py:1720-1721`, `agent-v2/config.py:1838-1842`).
- Budzet dnia jest powtarzalny dla tej samej daty: uzywa lokalnego generatora z ziarnem zawierajacym date (`agent-v2/stages.py:828-852`).
- Piec zdarzen zegara dziennego jest rzeczywiscie wpisanych do jednostki: 11:20, 17:00, 19:20, 21:30 i 23:40 UTC (`agent-v2/systemd/nia-agent.timer:48-54`).

### 2.4. Bezpieczenstwo i rozdzial odpowiedzialnosci

- Dane logowania, `.env`, bazy i stan sesji sa ignorowane przez Git (`.gitignore:1-18`, `.gitignore:29-49`, `.gitignore:97-99`). W audytowanym drzewie nie znalazlem sledzonego pliku z aktywnymi poswiadczeniami.
- Tekst od obcych jest oznaczany w promptach jako dane, nie instrukcje (`agent-v2/prompts/komentarz.md:187-192`, `agent-v2/prompts/odpowiedz.md:183-194`, `agent-v2/prompts/pisarz.md:154-155`).
- Jest deterministyczna zapora wyjscia na adresy, wzmianki i typowe slady prompt injection (`agent-v2/stages.py:3224-3263`). To redukuje ryzyko, ale skanuje wynik, a nie dowodzi, ze model nie posluchal subtelniejszego polecenia.
- Dzienny proces ma nieblokujacy zamek plikowy, ktory zapobiega dwom rownoleglym uruchomieniom `run.py` (`agent-v2/run.py:112-138`, `agent-v2/run.py:2073-2080`).

## 3. Niezgodnosci krytyczne z wymaganiami wlasciciela

### K1. Produkcja planuje jeden artykul tygodniowo, nie miesiecznie

Zegar ma `OnCalendar=Tue *-*-* 14:00:00` (`agent-v2/systemd/nia-artykul.timer:2-17`), a usluga uruchamia `artykul_z_puli.py --wyslij` (`agent-v2/systemd/nia-artykul.service:12-30`). Doktryna powtarza ten sam tygodniowy cel (`agent-v2/DOKTRYNA.md:62-72`, `agent-v2/DOKTRYNA.md:115-120`). To jest bezposrednia niezgodnosc z jednym artykulem miesiecznie, a nie tylko blad dokumentacji.

### K2. Zakres komentarzy nie odpowiada celowi 20-30 dziennie

Stala to 15-23 (`agent-v2/config.py:1619-1627`). Przez pierwsze 30 dni kod obniza gorna granice do dolnej polowy (`agent-v2/config.py:1891`, `agent-v2/stages.py:815-852`), co dla `(15, 23)` daje efektywnie 15-19. Zatem nawet zaplanowany, bezawaryjny dzien moze byc calkowicie ponizej wymaganego minimum 20.

### K3. Ten sam przydzial komentarzy jest wydawany przez dwa bloki

Blok komentarzy pod artykulami moze przejsc po `na_teraz["komentarze"]` celach (`agent-v2/run.py:1410-1422`). Pozniejszy blok dyskusji pod notkami niezaleznie bierze jeszcze `max(1, na_teraz["komentarze"] // 2)` (`agent-v2/run.py:1496-1505`, `agent-v2/run.py:1518-1529`). Oba zwiekszaja ten sam licznik i oba zapisują rodzaj `komentarz` (`agent-v2/run.py:1494`, `agent-v2/run.py:1538-1565`). Pomiedzy blokami nie ma odjecia juz wykonanych komentarzy (`agent-v2/run.py:2030-2036`).

Skutek: przy przydziale `N` jeden przebieg moze podjac do `N + max(1, floor(N/2))` publikacji. Kolejny przebieg zobaczy wpisy w dzienniku, lecz ostatni przebieg doby moze juz przekroczyc caly budzet. Test sprawdza, czy dyskusja liczy sie jako komentarz, ale nie sprawdza wspolnego sufitu obu blokow (`agent-v2/tests/test_licznik_wolumenow.py:391-439`).

### K4. Po nieudanym przebiegu algorytm nie domyka normy, chociaz tak twierdzi docstring

Docstring mowi, ze przebieg przerwany sie nie liczy, wiec kolejne przebiegi maja widziec mniej pozostalych uruchomien, a ostatni ma dzielic przez jeden (`agent-v2/run.py:344-356`). Kod odejmuje jednak tylko liczbe statusow `DONE` od stalej 5 (`agent-v2/run.py:358-367`).

Przy pieciu terminach i jednej wczesniejszej porazce przed ostatnim terminem sa tylko trzy `DONE`; funkcja zwraca `5 - 3 = 2`, mimo ze zostal jeden termin. Przydzial dzieli wtedy pozostala prace przez dwa (`agent-v2/run.py:1004-1021`) i moze zostawic okolo polowy reszty bez wykonania. Kod nie zna harmonogramu i nie potrafi odroznic minionego nieudanego terminu od terminu, ktory dopiero nadejdzie.

### K5. Piec notek nie jest kontraktem na kazda dobe

Podstawowy budzet rzeczywiscie wynosi 5 (`agent-v2/stages.py:860-869`), ale ciche dni sa wlaczone, wyznaczane z daty i zeruja `notki` oraz `restacki` (`agent-v2/config.py:1771-1790`, `agent-v2/config.py:1812-1835`, `agent-v2/run.py:994-1003`). Kazdy taki dzien ma zaplanowane zero notek. To swiadoma polityka systemu, ale jest sprzeczna z literalnym wymaganiem pieciu notek dziennie.

Dodatkowo zwykle awarie bloku notek sa polykane przez izolator blokow, po czym caly przebieg jest zamykany jako `DONE` (`agent-v2/run.py:1071-1101`, `agent-v2/run.py:2100-2115`). Taki `DONE` zmniejsza liczbe rzekomo pozostalych przebiegow, mimo ze notka z niego nie wyszla.

### K6. Nieudana publikacja artykulu wyglada jak zakonczony sukcesem przebieg

`browser.wystaw_artykul` lapie kazdy wyjatek i zwraca slownik z `wyslane=False`; brak widocznego przycisku publikacji rowniez nie rzuca bledu (`agent-v2/browser.py:3414-3428`, `agent-v2/browser.py:3466-3508`). Sterownik wypisuje `NIE POSZEDL`, lecz bezwarunkowo zwraca kod 0 (`agent-v2/artykul_z_puli.py:1361-1367`). `main()` zamienia kod 0 na status `DONE` (`agent-v2/artykul_z_puli.py:344-365`). Usluga artykulu nie ma `Restart=` ani drugiego terminu (`agent-v2/systemd/nia-artykul.service:26-30`).

Skutek: gotowy artykul moze nie trafic na Substack, a systemd i baza uznaja przebieg za udany. Kolejny automatyczny termin jest dopiero za tydzien w obecnej konfiguracji.

### K7. Harmonogram moze przypisac ostatni przebieg do nastepnej doby UTC

Ostatni termin to 23:40 UTC, a losowe opoznienie moze wyniesc 1500 sekund, czyli dojsc do 00:05 nastepnego dnia (`agent-v2/systemd/nia-agent.timer:52-54`). Zarowno budzet, jak i licznik przebiegow wybieraja dzien z faktycznego `datetime.now(timezone.utc)`, nie z terminu zegara (`agent-v2/stages.py:840-852`, `agent-v2/run.py:358-367`).

Skutek: czesc uruchomien 23:40 jest ksiegowana do budzetu kolejnej doby. W zaleznosci od wylosowanego opoznienia dzien moze miec cztery, piec albo szesc faktycznych uruchomien wedlug daty UTC, a rozdzielnik nadal zaklada stala liczbe 5.

## 4. Deterministycznosc

### 4.1. Elementy deterministyczne

- Budzet dnia korzysta z osobnego generatora z ziarnem `data|nia-budzet-dnia` (`agent-v2/stages.py:828-852`).
- Cichy dzien wynika z SHA-256 daty i nie potrzebuje stanu (`agent-v2/config.py:1812-1835`).
- Progi, sortowania, limity tokenow, routing modeli i bramki kodowe sa jawne w konfiguracji.

### 4.2. Elementy niedeterministyczne

- Postawa, otwarcie i dlugosc komentarza sa losowane bez ziarna (`agent-v2/config.py:1166-1199`).
- Ksztalt mysli, zakonczenie artykulu, liczba paraleli i zestaw generatorow sa losowane bez ziarna (`agent-v2/config.py:1580-1583`, `agent-v2/config.py:2327-2343`, `agent-v2/config.py:2442-2448`).
- Kolejnosc celow jest tasowana bez ziarna (`agent-v2/run.py:817-825`).
- Wiek dopuszczonego posta i hasla wyszukiwarki sa losowane (`agent-v2/kanal.py:58-67`, `agent-v2/kanal.py:222-230`).
- Dziedziny do szukania faktow sa losowane na kazdy przebieg (`agent-v2/stages.py:1295-1309`).
- Pierwsza notka ma losowa zwloke (`agent-v2/run.py:1200-1227`), a przegladarka losuje odstepy i opoznienie pisania (`agent-v2/browser.py:2336-2348`, `agent-v2/browser.py:4587-4599`).
- Systemd dodaje losowo do 25 minut do przebiegow dnia i do 15 minut do artykulu (`agent-v2/systemd/nia-agent.timer:48-54`, `agent-v2/systemd/nia-artykul.timer:15-17`).
- Wywolania Anthropic i DeepSeek nie podaja ziarna ani temperatury (`agent-v2/llm.py:186-200`, `agent-v2/llm.py:404-419`). Nawet z ziarnem wynik zalezalby od zewnetrznego modelu, wyszukiwarki i biezacego stanu Substacka.

To nie jest przypadkowy rozjazd: doktryna wprost nakazuje losowac start, forme, zakonczenie i dlugosc (`agent-v2/DOKTRYNA.md:79-90`). Wymaganie 100% deterministycznosci stoi wiec w konflikcie z obecna doktryna produktu.

## 5. Tylko AI: co zostalo i czego nie da sie zagwarantowac

### 5.1. Aktywne pozostalosci po poprzednim temacie

- `prompts/historia_startowa.json` nadal zawiera pietnascie tytulow o ciezarowkach, stolikach, wtyczkach, platnosciach, opakowaniach i innych codziennych systemach (`agent-v2/prompts/historia_startowa.json:1-16`). `recent_angles()` dolacza je przy krotkiej historii (`agent-v2/stages.py:68-94`), a `scout()` wstawia je do promptu (`agent-v2/stages.py:4914-4932`). W samym prompcie sa jednak wyraznie lista rzeczy zakazanych do powtarzania (`agent-v2/prompts/skaut.md:394-397`), wiec to aktywny kontekst historyczny, nie pozytywne polecenie pisania o nich.
- Prompt grafiki opisuje stary brief o przedmiotach codziennych jako blad, ktorego nie wolno przywracac, po czym jawnie nakazuje sceny z AI (`agent-v2/prompts/grafika.md:19-33`).
- Prompt restacku wymienia butelki szamponu i polisy jako przyklady poza tematem (`agent-v2/prompts/restack.md:19-24`).
- Prompty syntezy, oceny i wykonalnosci zachowuja historie nieudanego artykulu o symbolu na kosmetykach jako kontrprzyklad (`agent-v2/prompts/synteza.md:124-132`, `agent-v2/prompts/warto_pisac.md:39-45`, `agent-v2/prompts/wykonalnosc.md:37-47`).
- Nazwa `CIEKAWOSTKA`, `DZIEDZINY_CIEKAWOSTEK` i funkcja `znajdz_ciekawostki` nadal istnieja (`agent-v2/config.py:909`, `agent-v2/config.py:1363`, `agent-v2/stages.py:1221`). To nazwa formatu materialu, nie dawnego tematu: sama lista dziedzin jest juz o AI (`agent-v2/config.py:909-967`).
- Docstring modulu artykulu opisuje poprzednia publikacje i przejscie na AI (`agent-v2/artykul_z_puli.py:1-15`). To historia decyzji, nie instrukcja dla modelu.
- Korpus stylu zawiera materialy spoza AI, ale trafia do pisarza jako 3-5 przykladow ruchu retorycznego, nie jako zrodlo tematu (`agent-v2/style.py:1-10`, `agent-v2/style.py:72-90`). Nie uznaje tego za naruszenie zakresu tematycznego.

### 5.2. Luka w gwarancji

Kod nie ma koncowej, deterministycznej odpowiedzi na pytanie „czy gotowy artykul/notka/komentarz jest o AI”. Temat jest pilnowany przez instrukcje i decyzje modeli. Nawet `NOT_AI` powstaje z werdyktu modelu w rankingu banku (`agent-v2/stages.py:6306-6355`). Zapora koncowa sprawdza wstrzykniecia, adresy i wzmianki, lecz nie temat AI (`agent-v2/stages.py:3224-3263`).

Odpowiedzi pod wlasnymi tresciami lub naszymi komentarzami dziedzicza temat z watku, ale prompt odpowiedzi nie nazywa AI; nakazuje odpowiedziec gospodarzowi i odrzuca tylko przemoc, pusta pochwale, brak danych i spor poza tematem (`agent-v2/prompts/odpowiedz.md:1-24`). Dlatego cel „tylko AI” jest mocno wspierany, lecz nie jest formalna gwarancja kazdego opublikowanego zdania.

Nie da sie ustalic empirycznie, czy po przestawieniu konta wyszla tresc spoza AI: lokalny dziennik dostepny podczas audytu ma tylko trzy wpisy `obserwacja_pominieta` z 2026-09-01 i nie zawiera tekstow publikacji.

## 6. Dostarczanie mimo bledow: pozostale luki

### 6.1. Artykul moze zostac na dysku po wyczerpaniu budzetu

Finalne `zweryfikuj()` przepuszcza zwykle awarie modelu, ale ponownie rzuca `BudgetExceeded` i `PreflightFailed` (`agent-v2/stages.py:3290-3343`). W sciezce artykulu sprawdzenie odbywa sie juz po zapisie pliku, ale przed publikacja (`agent-v2/artykul_z_puli.py:1297-1323`, `agent-v2/artykul_z_puli.py:1349-1363`). W takiej sytuacji artykul jest odzyskiwalny na dysku, lecz nie wychodzi na Substack.

Starsza sciezka w `run.py` przed rozpoczeciem calego artykulu sprawdza, czy zostal co najmniej caly `RUN_LIMIT_USD` (`agent-v2/run.py:2124-2139`). Produkcyjna usluga korzysta teraz z `artykul_z_puli.py`, gdzie takiego sprawdzenia calego przebiegu nie ma; sa tylko preflighty przed kolejnymi wywolaniami.

### 6.2. Artykul nie korzysta ze wspolnego zamka

`run.main()` zajmuje `agent.lock` (`agent-v2/run.py:2073-2080`), natomiast `artykul_z_puli.main()` od razu otwiera baze i przebieg (`agent-v2/artykul_z_puli.py:327-365`). Skrypt wdrozenia sprawdza ten zamek oraz proces `run.py --dzien`, ale nie proces `artykul_z_puli.py` (`agent-v2/wdroz.sh:38-59`). Artykul moze wiec nakladac sie na dzienny przebieg lub wdrozenie.

Polaczenie z SQLite nie wlacza WAL ani jawnego `busy_timeout` (`agent-v2/db.py:87-96`). Nie da sie ustalic z samego kodu, czy kolizja wystapi w praktyce, ale dwa zapisujace procesy sa dozwolone przez architekture i nie maja wspolnej blokady.

### 6.3. Maksymalny czas przebiegu jest dluzszy niz czesc przerw w harmonogramie

Usluga moze trwac do 9000 sekund, czyli 150 minut (`agent-v2/systemd/nia-agent.service:19-28`). Odstepy 17:00-19:20, 19:20-21:30 i 21:30-23:40 maja odpowiednio 140, 130 i 130 minut, a start moze byc dodatkowo opozniony do 25 minut (`agent-v2/systemd/nia-agent.timer:48-54`). Kod rozpoznaje drugi proces zamkiem, lecz zwraca wtedy kod 0 (`agent-v2/run.py:2073-2080`). Sam kod nie ma mechanizmu odrobienia tak pominietego terminu. Nie da sie ustalic z repozytorium, jak czesto rzeczywisty czas dochodzi do tej granicy.

### 6.4. Wybrany powod komentarza ginie przed pisaniem

`wybierz_cele` dopisuje `co_dodamy` do przyjetego celu (`agent-v2/stages.py:1058-1096`), a `comment_on` umie uzyc tego pola jako konkretnego zadania (`agent-v2/stages.py:3756-3779`). Produkcyjny blok artykulow przekazuje jednak `strony[0]`, a blok notek buduje nowy slownik bez `co_dodamy` (`agent-v2/run.py:1419-1422`, `agent-v2/run.py:1518-1530`).

Skutek: system placi za decyzje „co wniesiemy”, po czym model piszacy komentarz jej nie dostaje. To nie blokuje publikacji, ale oslabia dopasowanie i moze zwiekszac liczbe ogolnych albo chybionych komentarzy. Wada jest tez jawnie zapisana w `agent-v2/DO_ZROBIENIA.md:29-49`.

## 7. Koszty i zapory

### 7.1. Co dziala

- Limity sa sprawdzane przed kazdym wywolaniem: na przebieg, dzien i miesiac (`agent-v2/llm.py:84-122`).
- Produkcyjny limit dzienny wynosi normalnie 5 USD, testowy 3 USD, miesieczny 40 USD, a na jeden przebieg 1,60 USD (`agent-v2/config.py:481`, `agent-v2/config.py:499-523`).
- Ponawiane sa tylko bledy uznane za przejsciowe, najwyzej dwa razy (`agent-v2/config.py:517-521`, `agent-v2/llm.py:512-546`).
- Udane wywolania sa rejestrowane centralnie przez `llm.call`.

### 7.2. Ograniczenia

- Limity sa progami „juz wydano”, a nie rezerwacja kosztu kolejnego wywolania: warunki sprawdzaja `spent >= limit` (`agent-v2/llm.py:84-122`). Ostatnie wywolanie moze wiec przekroczyc sufit o swoj koszt.
- Nieudane wywolanie jest zapisywane z kosztem 0, bo koszt jest nieznany (`agent-v2/llm.py:529-545`); nieudany obraz rowniez ma koszt 0 (`agent-v2/llm.py:592-603`). Jesli dostawca naliczy koszt przed timeoutem lub bledem odpowiedzi, zapory go nie zobacza.
- Preflight kluczy porownuje model tylko z dokladnym `CLAUDE`, `DEEPSEEK` i modelem obrazowym (`agent-v2/llm.py:73-79`). Nie sprawdza z gory aliasow `FABLE`, `SONNET` ani `DEEPSEEK_PRO`, chociaz routing ich uzywa (`agent-v2/config.py:104-108`, `agent-v2/config.py:113-243`). Brak klucza ujawni sie pozniej jako blad dostawcy, a nie czytelna odmowa preflightu.
- Nie weryfikowalem zewnetrznych cen ani faktur. Audyt potwierdza jedynie, ze kod ma jawny cennik i znacznik `verified` (`agent-v2/config.py:276-299`).

## 8. Mapa projektu i dokumentacja

### 8.1. Czesc wiarygodna

Generator jasno rozdziela mechaniczne czesci od recznej narracji (`agent-v2/dokumentacja-zrodla/sklej.py:21-30`). Lista modulow obejmuje wszystkie 22 pliki `.py` z katalogu glownego, a spis funkcji powstaje przez AST (`agent-v2/dokumentacja-zrodla/sklej.py:47-72`, `agent-v2/dokumentacja-zrodla/sklej.py:130-149`). Test regeneruje dokument, porownuje wynik i przywraca pliki po sprawdzeniu (`agent-v2/tests/test_dokumentacja_zywa.py:83-114`). Test przeszedl.

Wniosek: `JAK_ZBUDOWANY_JEST_BOT.md` jest dobrym indeksem aktualnych modulow, funkcji, stalych i tresci promptow w wygenerowanych zalacznikach.

### 8.2. Czesc niewiarygodna jako mapa stanu produkcji

- Reczny rozdzial harmonogramu nadal pokazuje trzy uruchomienia i `PRZEBIEGOW_DZIENNIE = 3` (`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:2305-2317`), podczas gdy jednostka i wygenerowana tabela maja piec (`agent-v2/systemd/nia-agent.timer:48-54`, `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:12727`).
- Reczny opis kosztu nadal mnozy srednia przez trzy przebiegi (`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:5917-5919`).
- Reczny opis operacji nadal nazywa timer dzienny trzyrazy-dziennym i wymienia trzy godziny (`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:5952-5966`).
- Opis taryfy twierdzi, ze harmonogram zawiera tylko 11:20, 19:20 i 23:40, pomijajac 17:00 i 21:30 (`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:5513`).
- Rootowa mapa serwera tez podaje tylko trzy godziny (`JAK_TO_JEST_PODZIELONE.md:14-22`) i twierdzi, ze dzis sa 43 zestawy testow (`JAK_TO_JEST_PODZIELONE.md:39-47`).
- Rootowy README podaje 11 plikow `.py`, 11 231 wierszy i 43 zestawy testow (`README.md:19-26`). Audytowany katalog ma 22 pliki `.py`, 25 905 wierszy lacznie z pustymi, 114 darmowych skryptow `test_*.py` i 9 platnych.
- Wygenerowana tabela stalych pokazuje obok siebie martwe `COMMENTS_PER_DAY = 4` i zywe `KOMENTARZE_DZIENNIE = (15, 23)` (`agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:12694`, `agent-v2/JAK_ZBUDOWANY_JEST_BOT.md:12716`). Generator wiernie pokazuje kod, ale nie odroznia tu ustawienia aktywnego od pozostalosci.
- Doktryna jest zgodna z obecnym kodem w sprawie losowosci i tygodniowego artykulu, lecz sprzeczna z aktualnym poleceniem wlasciciela: 15-23 komentarze i 1 artykul tygodniowo (`agent-v2/DOKTRYNA.md:62-72`, `agent-v2/DOKTRYNA.md:79-90`, `agent-v2/DOKTRYNA.md:115-120`).

Werdykt dla mapy: **warstwa mechaniczna jest adekwatna; warstwa narracyjna i operacyjna nie jest zrodlem prawdy**.

## 9. Testy i odtwarzalnosc

### 9.1. Wynik na czystym, przypietym `main`

- `python -m compileall -q agent-v2`: **OK**.
- Darmowe skrypty: **110 z 114 przeszlo**.
- Platne/sieciowe: **9 nie zostalo uruchomionych**, zeby audyt nie wydawal pieniedzy i nie dotykal zywego konta.
- Test dokumentacji, testy zakresu AI, testy modeli, wolumenow, bramek, dziennika i kopii testowej byly wsrod przechodzacych.

### 9.2. Cztery nieprzechodzace skrypty

1. `test_czas.py`: test wysyla prawdziwy `SIGTERM` do procesu (`agent-v2/tests/test_czas.py:76-104`). Na Windowsie proces nie przeszedl sciezki obslugi sygnalu i zostawil `RUNNING`. Produkcja jest opisana jako Linux, wiec nie jest to dowod awarii produkcyjnej; jest to brak przenosnosci testu.
2. `test_podlogi_playbook.py`: test oczekuje ignorowanego pliku artykulu `0025`, a po jego braku przechodzi na niepelny, zapisany wycinek (`agent-v2/tests/test_podlogi_playbook.py:40-54`). Pozniejsze asercje wymagaja cech pelnego artykulu (`agent-v2/tests/test_podlogi_playbook.py:128-152`). Czysty klon nie ma tego artefaktu, wiec test nie jest samowystarczalny.
3. `test_ratunek_tekstu.py`: test oczekuje, ze kontrolny wiersz zwiekszy `recent_angles` o jeden (`agent-v2/tests/test_ratunek_tekstu.py:647-673`, `agent-v2/tests/test_ratunek_tekstu.py:750-768`). W czystym srodowisku lista juz byla wypelniona do limitu historia startowa, wiec obie strony mialy po piec pozycji. To zaleznosc testu od zastanego wypelnienia historii.
4. `test_zapora_platnych_wywolan.py`: test wymaga, by `DRY_RUN` przeszedl bez klucza (`agent-v2/tests/test_zapora_platnych_wywolan.py:85-98`). `llm.call` uruchamia `_preflight` przed obsluga `DRY_RUN` (`agent-v2/llm.py:484-510`), a preflight sprawdza klucz modelu (`agent-v2/llm.py:73-79`). To rzeczywista sprzecznosc kodu z testem i komentarzem, ujawniajaca sie w swiezym klonie bez `.env`.

### 9.3. Wdrozenie nie uruchamia pelnej siatki testow

`wdroz.sh` importuje wybrany zestaw modulow i sprawdza trzy warunki (`agent-v2/wdroz.sh:70-80`), a potem testuje sesje przegladarki (`agent-v2/wdroz.sh:86-102`). Nie uruchamia 114 darmowych skryptow i nie importuje m.in. produkcyjnego sterownika `artykul_z_puli.py`. Przejscie smoke testu nie oznacza zatem przejscia testow repozytorium.

## 10. Dane, pomiary i granice tego audytu

Lokalny stan runtime, ktory byl dostepny do odczytu, nie jest pelna ani aktualna kopia produkcji:

- baza ma 130 przebiegow od 2026-08-15 do 2026-08-30: 78 `DONE`, 22 `FAILED`, 30 `RUNNING`;
- ma 623 zapisane wywolania o lacznym koszcie 20,9253 USD i 16 wierszy artykulow;
- katalog lokalnych plikow artykulow jest pusty;
- dziennik ma tylko trzy wpisy z 2026-09-01, wszystkie `obserwacja_pominieta`.

Z tego materialu **nie da sie ustalic** rzeczywistej liczby notek, komentarzy, artykulow ani udzialu AI po zmianach na `main`. Werdykty o wolumenie w tym raporcie dotycza tego, co kod planuje i co moze wykonac, nie twierdzenia, ile produkcja faktycznie opublikowala.

Wbudowany `audyt_systemu.py` nie rozroznia „normy policzalne, ale brak dni z udana publikacja” od „normy niepoliczalne”: warunek wymaga jednoczesnie `normy` i `dni`, a w przeciwnym razie wypisuje blad o braku budzetow i norm (`agent-v2/audyt_systemu.py:262-328`). Na tym skromnym dzienniku jego komunikat o niepoliczalnych normach jest falszywym alarmem.

Petla uwag do nastepnego artykulu zalezy od lokalnych plikow `*.uwagi.md`, nie od wiersza w bazie (`agent-v2/stages.py:180-218`). `save()` zapisuje zarowno plik uwag, jak i osobny rekord artykulu (`agent-v2/stages.py:274-315`). Kopia zawierajaca sama baze odtwarza liste artykulow, ale nie odtwarza uwag dla pisarza. Przy pustym katalogu artykulow ta pamiec zwraca pusty tekst.

## 11. Ostateczna ocena ryzyka

### Wysokie

1. Czestotliwosc artykulu jest okolo czterokrotnie wyzsza od zalozenia produktowego: tydzien zamiast miesiaca.
2. Nieudana publikacja artykulu zostawia `DONE`, wiec nie uruchamia naturalnego sygnalu ponowienia ani bledu.
3. Dzielenie normy po nieudanym przebiegu robi odwrotnosc tego, co obiecuje docstring, i zostawia niewykonana reszte.
4. Budzet komentarzy nie jest wspolny dla komentarzy pod artykulami i pod notkami.
5. Cel 5 notek dziennie jest sprzeczny z wlaczonymi cichymi dniami.

### Srednie

6. „Tylko AI” zalezy od poprawnosci decyzji modelu i nie ma koncowej bramki tematycznej.
7. Artykul nie ma wspolnego zamka z dniem i wdrozeniem.
8. Ostatni dzienny timer moze przejsc przez polnoc UTC i zostac policzony do innej doby.
9. Trzy maksymalne okna wykonania moga nachodzic na nastepne terminy zegara.
10. Powod `co_dodamy` ginie miedzy wyborem celu a pisaniem komentarza.
11. Limity kosztu moga zostac przekroczone kosztem ostatniego wywolania, a koszt nieudanych wywolan jest liczony jako zero.

### Dokumentacyjne i obserwowalnosc

12. Reczne fragmenty mapy projektu nadal opisuja trzy przebiegi, stare godziny, stare koszty i stara liczbe testow.
13. Cztery darmowe skrypty nie przechodza w czystym srodowisku; trzy sa zalezne od platformy lub lokalnych danych, jeden ujawnia rzeczywista sprzecznosc `DRY_RUN`/preflight.
14. Wbudowany audyt systemu wypisuje falszywy blad norm przy pustym dzienniku publikacji.
15. Baza bez katalogu artykulow nie odtwarza uwag, ktore maja uczyc nastepny artykul.

## 12. Konkluzja

Rdzen bota jest sensownie rozdzielony, mocno nastawiony na AI i wyraznie projektowany tak, by pojedynczy blad nie zabieral calego dnia. Najwiekszy problem nie lezy w generowaniu tresci, tylko w **rachunkowosci wykonania**: harmonogram, status `DONE`, liczba pozostalych przebiegow i dwa bloki komentarzy nie opisuja tego samego zdarzenia w ten sam sposob.

Przy obecnym `main` nie mozna powiedziec, ze bot realizuje zadany kontrakt: nie jest literalnie deterministyczny, nie gwarantuje pieciu notek, nie celuje w 20-30 komentarzy i planuje artykul co tydzien zamiast co miesiac. Mozna natomiast powiedziec, ze przejscie tematyczne na AI zostalo wykonane szeroko i konsekwentnie; pozostale stare przyklady sa w wiekszosci jawnie oznaczona historia lub kontrprzyklady, nie aktywne polecenia powrotu do „ukrytych systemow”.
