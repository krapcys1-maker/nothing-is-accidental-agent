# 14 — WNIOSKI CZĄSTKOWE

## Cel pliku
Po każdym etapie: co nas zaskoczyło, co działało, co nie, co agent robił lepiej, gdzie nadal był potrzebny człowiek, jakie założenie okazało się błędne, co zmienimy dalej. To „refleksja po etapie", surowiec do puenty artykułów.

## Szablon wpisu
```markdown
### Wnioski po <etap / data>
- **Co zaskoczyło:**
- **Co działało:**
- **Co nie działało:**
- **Co agent zrobił lepiej niż typowy człowiek:**
- **Gdzie nadal potrzebny był człowiek:**
- **Jakie założenie okazało się błędne:**
- **Co zmienimy dalej:**
```

---

### Wnioski po V0–V2 (2026-07-11, faza offline)
- **Co zaskoczyło:**
  - Ile porządku wymusiła zasada „najpierw plan, potem kod". Audyt wykrył **rozbieżności liczbowe** między trzema dokumentami (wagi scoringu, funkcja celu), których nikt wcześniej nie ujednolicił — bez tego kod byłby budowany z trzech sprzecznych źródeł.
  - Że **web search dominuje koszt researchu** (~0.049 USD na kartę w szacunku), a nie same tokeny modelu. To zmienia intuicję o tym, gdzie leży budżet.
- **Co działało:**
  - Podział „mózg/ręce/pamięć/strażnik" — czysty i testowalny (44 testy). Deterministyczny Policy Engine daje realne poczucie kontroli nad kosztem.
  - Tryb `dry_run` — pozwolił zbudować i zademonstrować cały pipeline **bez wydania ani centa**.
  - Lokalna deduplikacja tematów bez płatnego modelu — tania i skuteczna (wykryła 6 duplikatów przy powtórnym runie).
- **Co nie działało / było ryzykowne:**
  - Brak `.gitignore` na starcie — realny wyciek klucza czekał na okazję (naprawione, ale rotacja odłożona = ryzyko rezydualne R1).
  - Drobny błąd importu w teście — przypomnienie, że pełny `pytest` musi być bramką każdego etapu.
- **Co agent zrobił lepiej niż typowy człowiek:**
  - Skrupulatny, kompletny audyt trzech dokumentów naraz i wychwycenie sprzeczności liczbowych.
  - Bezbłędne, natychmiastowe dokumentowanie każdego kroku (build log, ADR, koszty) — człowiek zwykle to odkłada.
- **Gdzie nadal potrzebny był człowiek:**
  - **Decyzje właścicielskie:** zakres MVP, autonomia, panel, budżet, obsługa klucza, nisza żony — to nie są decyzje techniczne.
  - **Bramka „idź dalej / czekaj"** przed każdym kosztem i publikacją.
- **Jakie założenie okazało się (częściowo) błędne:**
  - Wizja **fotorealistycznych grafik** zderzyła się z rzeczywistością „Anthropic-only" → w MVP tylko SVG. Rozjazd wizja↔wykonalność, świadomie zaakceptowany (ADR-003).
  - Arytmetyka budżetu (2 USD/dzień × 30 > 40/mies.) — wymagała twardego priorytetu miesięcznego (ADR-012).
- **Co zmienimy dalej:**
  - Zmierzyć **realny** koszt (pierwszy `--real`) i porównać z szacunkiem dry_run — to zweryfikuje cały model kosztowy.
  - Zbudować generator artykułów z 3 audytami i dopiero na realnych szkicach ocenić jakość (największa niewiadoma).

### Wnioski po pierwszym realnym wywołaniu (2026-07-11 19:09 UTC)
- **Co zaskoczyło:**
  - Jak szybko teoria zderzyła się z praktyką: pierwsza prawdziwa, płatna próba **nie powiodła się** — nie z powodu złej architektury, tylko banalnego limitu długości odpowiedzi modelu, który nigdy nie ujawnił się w testach (bo testy używały krótkich, sztucznych odpowiedzi).
  - Że błąd „nieudanego researchu" pociągnął za sobą **drugi, poważniejszy błąd**: utratę informacji o realnym koszcie. Coś, co miało być prostym „nie wyszło, spróbujemy inaczej", omal nie stało się cichą dziurą w budżecie.
- **Co działało:**
  - Cała warstwa bezpieczeństwa zadziałała dokładnie tak, jak zaprojektowana: zero automatycznego ponawiania płatnego wywołania, twardy cap kosztu sprawdzony PRZED wywołaniem, klucz API nigdzie nie ujawniony, zero publikacji, zero dotknięcia przeglądarki.
  - Decyzja, żeby nie ruszać współdzielonego globalnego środowiska Pythona (używanego też przez inne narzędzia) i zamiast tego zbudować izolowane środowisko tylko dla tego projektu — nic poza projektem nie zostało naruszone.
- **Co nie działało:**
  - Limit długości odpowiedzi modelu (ustawiony „na oko" na etapie planowania) okazał się za ciasny na realny wynik z 6 wyszukiwaniami.
  - Obsługa błędu gubiła informację o prawdziwym koszcie — klasyczny przykład, że „ścieżka błędu" bywa testowana słabiej niż „ścieżka sukcesu".
- **Co agent zrobił lepiej niż typowy człowiek:**
  - Natychmiastowa, pełna, nieukrywająca niczego dokumentacja błędu — łącznie z błędem, który dotyczył samego mechanizmu liczenia kosztów, czyli czegoś, co łatwo byłoby „zamieść pod dywan" w normalnym projekcie.
- **Gdzie nadal był potrzebny człowiek:**
  - **Zgoda na wydanie realnych pieniędzy** — z precyzyjnymi, jawnie wypisanymi limitami (cap kosztu, limit wyszukiwań, limit ponowień). Bez tej zgody nic by się nie wydarzyło.
  - **Decyzja, co dalej** po nieudanej próbie — czy zatwierdzić kolejną (z poprawką), czy najpierw zweryfikować koszt w panelu Anthropic.
- **Jakie założenie okazało się błędne:**
  - Że limit 3000 „tokenów" wyjścia wystarczy na pełną kartę researchu. Dane testowe (fikcyjne, krótkie) ukryły ten problem aż do pierwszego realnego kontaktu z prawdziwym modelem.
- **Co zmienimy dalej:**
  - Przed kolejną realną próbą: podnieść limit długości odpowiedzi modelu.
  - Rozważyć testowanie z bardziej „hojnymi" (długimi) danymi fikcyjnymi, żeby wcześniej wychwytywać podobne problemy pojemności.
  - Sprawdzić realny koszt tej próby w konsoli Anthropic, żeby zamknąć lukę w księgowości. **[Zrobione — patrz wnioski niżej.]**

### Wnioski po weryfikacji realnego kosztu i naprawie estymatora (2026-07-11, ta sama sesja, później)
- **Co zaskoczyło:**
  - Jak duży był błąd naszego pierwszego szacunku: 0,095 USD wobec realnych 0,25 USD — **2,63× więcej, ~163% błędu**. To nie była drobna nieścisłość; nasz „bezpieczny sufit" był w rzeczywistości bliżej połowy prawdziwej ceny.
  - Że sam limit kosztu (`--max-cost-usd`), który wyglądał jak twardy hamulec, w rzeczywistości nigdy nim nie był — to tylko kontrola PRZED wysłaniem zapytania, oparta na (jak się okazało, błędnym) szacunku. Prawdziwym hamulcem były inne, mniej widoczne ustawienia (limit długości odpowiedzi i limit liczby wyszukiwań), które akurat zadziałały poprawnie.
- **Co działało:**
  - Mimo błędnego szacunku, **nic nie wymknęło się spod kontroli** — realny koszt (0,25 USD) i tak zmieścił się w zatwierdzonym limicie (0,30 USD), tylko z mniejszym zapasem, niż zakładaliśmy (0,05 USD zamiast rzekomych 0,20 USD).
  - Naprawa całej sytuacji odbyła się **bez wydania ani centa więcej** — nowy estymator, dwuetapowy podział researchu i 16 nowych testów powstały wyłącznie na danych testowych.
- **Co nie działało:**
  - Zbyt uproszczony model kosztu: zakładaliśmy stały „zapas" na wyniki wyszukiwania, a w praktyce ten koszt rośnie wraz z liczbą wyszukiwań — im więcej razy model szuka w internecie, tym więcej tekstu wraca do niego jako kontekst do przetworzenia.
- **Co agent zrobił lepiej niż typowy człowiek:**
  - Natychmiastowe przeliczenie i przyznanie się do błędu w estymacji, bez prób umniejszania skali pomyłki (163% to spora różnica) — i przełożenie tego wprost na konkretną poprawkę kodu i testy, tego samego dnia.
- **Gdzie nadal był potrzebny człowiek:**
  - **Sama weryfikacja realnej kwoty** — agent nie ma dostępu do panelu rozliczeniowego Anthropic; bez właściciela sprawdzającego konsolę, błąd estymacji pozostałby niewykryty przez czas nieokreślony.
  - **Decyzja o zakresie naprawy** — właściciel określił dokładnie, co ma się zmienić (podział na dwa kroki, margines bezpieczeństwa, limit wyszukiwań), zamiast zostawiać to swobodnej interpretacji.
- **Jakie założenie okazało się błędne:**
  - Że „hojny bufor" (stała liczba tokenów jako zapas bezpieczeństwa) wystarczy jako metoda szacowania kosztu. W praktyce koszt zależy od STRUKTURY zapytania (ile wyszukiwań), nie tylko od jego rozmiaru.
- **Co zmienimy dalej:**
  - Przed kolejnym realnym wywołaniem: zebrać więcej realnych punktów danych (obecna kalibracja opiera się na dokładnie jednej obserwacji), żeby estymator stawał się coraz dokładniejszy, nie tylko coraz bardziej ostrożny.
  - Rozważyć, czy warto budować wewnętrzny „licznik" realnych wydatków synchronizowany z panelem dostawcy, zamiast polegać wyłącznie na własnych obliczeniach.

### Wnioski po doprecyzowaniu celu: pełna autonomia jako stan docelowy (2026-07-11, ADR-017)
- **Co zaskoczyło:** jak łatwo dokumentacja mogła „zdryfować" w stronę nadmiernej ostrożności, mimo że pierwotny cel (agent SAMODZIELNIE prowadzący konto) nigdy się nie zmienił. Kolejne, słuszne bramki bezpieczeństwa (LEVEL_1 na start, akceptacja każdej akcji na początku) zaczęły z czasem brzmieć jak opis architektury docelowej, nie fazy przejściowej — nikt tego świadomie nie zdecydował, po prostu tak wyszło z kumulacji ostrożnych sformułowań.
- **Co działało:** to, że właściciel zauważył ten dryf i skorygował go PRZED napisaniem jakiegokolwiek kodu autonomicznych interakcji — dużo taniej naprawić założenie w dokumentacji niż w działającym systemie.
- **Co nie działało:** dotychczasowe sformułowania w wielu miejscach ("artykuły i komentarze zawsze za akceptacją") nie miały jasno oznaczonego „na razie" — czytane osobno, bez pełnego kontekstu ADR-004, brzmiały jak stała reguła.
- **Co agent zrobił lepiej niż typowy człowiek:** żadne — to była korekta pochodząca WYŁĄCZNIE od właściciela. Warto to odnotować uczciwie: agent sam nie zauważył własnego dryfu dokumentacyjnego, mimo że pisał większość tych sformułowań.
- **Gdzie nadal był potrzebny człowiek:** dokładnie tutaj — zauważenie rozjazdu między „co napisaliśmy" a „co naprawdę chcieliśmy" wymaga kogoś, kto trzyma w głowie pierwotny cel na przestrzeni wielu sesji i wielu drobnych decyzji. To rodzaj nadzoru, którego nie da się łatwo zautomatyzować.
- **Jakie założenie okazało się błędne:** że „bezpieczny start" i „cel systemu" można opisywać tymi samymi zdaniami bez wyraźnego rozróżnienia „dziś" vs „docelowo". Rozwiązanie: każda wzmianka o poziomie autonomii odtąd jawnie mówi, czy opisuje stan bieżący, czy cel.
- **Co zmienimy dalej:** przy każdej kolejnej dużej decyzji architektonicznej — jawnie pytać „czy to opisuje fazę startową, czy stan docelowy" i zapisywać obie wersje osobno, żeby to samo nieporozumienie się nie powtórzyło.

### Wnioski po stabilizacji wznawialności Research Pipeline (2026-07-12, ADR-019)
- **Co zaskoczyło:** że naprawienie jednego problemu (ucięcie odpowiedzi wewnątrz jednego wywołania, ADR-016) tak łatwo zostawia **cień tego samego problemu** jeden poziom wyżej — tym razem jako „co jeśli proces padnie MIĘDZY dwoma już oddzielonymi krokami". To nie był nowy pomysł na błąd, tylko ten sam błąd przesunięty w architekturze, znaleziony dopiero, gdy ktoś zadał pytanie „a co jeśli DOKŁADNIE teraz?".
- **Co działało:** podejście „napraw PROAKTYWNIE, zanim to się wydarzy naprawdę" — tym razem nie czekaliśmy na drugi kosztowny incydent, żeby zauważyć lukę. Cała naprawa (nowe tabele, atomowy zapis, funkcja wznowienia, 10 testów) powstała i została potwierdzona **bez jednego dodatkowego centa** wydanego na API.
- **Co nie działało:** nic nowego nie zawiodło w tym etapie — to była praca prewencyjna, nie naprawa żywego błędu. Jedyna drobna usterka (brakujący licznik w pomocniczej klasie testowej) była kosmetyczna i złapana natychmiast.
- **Co agent zrobił lepiej niż typowy człowiek:** systematyczne rozpisanie WSZYSTKICH ścieżek awarii (awaria w kroku A, awaria w kroku B, awaria między A i B, awaria w trakcie samego zapisu do bazy) i zaprojektowanie testu dla każdej z nich osobno — w tym testu, który świadomie symuluje restart procesu (nowe obiekty w pamięci), żeby nie oszukiwać się reużytym stanem.
- **Gdzie nadal był potrzebny człowiek:** **zdefiniowanie granic etapu** — właściciel z góry określił dokładnie, czego NIE robić w tej turze (generator artykułów, Playwright, publikacja, drugie płatne wywołanie), co pozwoliło skupić całą pracę na jednym, wąskim problemie i domknąć go w całości, zamiast rozjechać się na pół zbudowane funkcje w kilku miejscach naraz.
- **Jakie założenie okazało się błędne:** że „podział na dwa kroki" (ADR-016) sam w sobie już rozwiązywał problem trwałości. W rzeczywistości rozwiązywał tylko jeden konkretny scenariusz utraty danych (ucięcie w połowie odpowiedzi), a nie ogólną zasadę „nic kosztownego nie powinno istnieć wyłącznie w pamięci procesu".
- **Co zmienimy dalej:** przy każdej kolejnej wieloetapowej operacji (np. przyszły generator artykułów z audytami) od razu zadawać to samo pytanie z góry — „co się stanie, jeśli proces padnie między krokiem N i N+1" — zamiast czekać, aż podział na etapy „wygląda gotowo", i doklejać trwałość później.

### Wnioski po przebudowie kroku 1 na szukanie + czytanie pojedynczego źródła (2026-07-12, ADR-020)
- **Co zaskoczyło:** jak łatwo można pomylić „załatanie objawu" z „naprawieniem przyczyny". Naturalna, pierwsza reakcja na „odpowiedź się urywa" to „podnieś limit długości odpowiedzi" — i to nawet by POMOGŁO w tym konkretnym przypadku. Ale właściciel od razu zauważył, że to nie usuwa przyczyny (jedna odpowiedź na wiele źródeł naraz), tylko przesuwa próg, przy którym problem wróci — przy nieco większej liczbie źródeł albo nieco dłuższych faktach.
- **Co działało:** dokładnie te same mechanizmy bezpieczeństwa, które kilka godzin wcześniej pozwoliły bezpiecznie ZAOBSERWOWAĆ ten problem (bez utraty pieniędzy czy danych), teraz pozwoliły go bezpiecznie NAPRAWIĆ — cała przebudowa i 12 nowych testów powstały bez wydania ani centa.
- **Co nie działało:** nic nowego nie zawiodło w tym etapie — to była praca projektowa/naprawcza, nie test na żywo.
- **Co agent zrobił lepiej niż typowy człowiek:** rozłożenie problemu na czynniki pierwsze i zaprojektowanie rozwiązania, które usuwa całą KLASĘ awarii (dowolne źródło, dowolna pozycja w liście), zamiast punktowo łatać konkretny zaobserwowany przypadek — oraz systematyczne pokrycie testami obu skrajnych scenariuszy (pierwsze źródło pada, ostatnie źródło pada), żeby udowodnić, że rozwiązanie faktycznie jest ogólne, nie przypadkowo zadziałało tylko dla jednego układu.
- **Gdzie nadal był potrzebny człowiek:** **odróżnienie objawu od przyczyny.** To właśnie właściciel zatrzymał proces przed wdrożeniem płytszej naprawy („po prostu podnieś limit") i zażądał głębszej analizy — to rodzaj osądu inżynierskiego, który wymaga dystansu do własnej pierwszej, intuicyjnej reakcji.
- **Jakie założenie okazało się błędne:** że „lżejszy schemat" (mniej pól do wypełnienia na źródło) sam w sobie wystarczająco redukuje ryzyko ucięcia. W praktyce dopóki JEDNA odpowiedź obejmuje WIELE źródeł, ryzyko nigdy nie znika całkowicie — tylko się zmniejsza, aż do momentu, gdy znowu się ujawni.
- **Co zmienimy dalej:** przy każdej przyszłej sytuacji „coś się urywa/nie mieści" — najpierw zapytać „czy to jest wada PARAMETRU, czy wada KONSTRUKCJI", zanim sięgniemy po najprostszą łatkę (podnieś limit, zwiększ retry, itp.).

### Wnioski po diagnostyce limitu A2 i naprawie podsumowania (2026-07-12)
- **Co zaskoczyło:** pierwsza próba nie kosztowała ani centa, bo padła jeszcze lokalnie na niezgodności starego SDK Anthropic z nowym httpx. Dopiero po naprawie środowiska diagnostyka dotarła do API.
- **Co udowodniliśmy:** jedna poprawna odpowiedź A2 dla kandydata `id=3` potrzebowała 915 tokenów wyjścia i zakończyła się `end_turn`, więc dawny default 500 był za niski. To NIE dowodzi, że nieudani kandydaci 1 i 2 potrzebowaliby dokładnie tyle samo — nie zostali ponowieni.
- **Decyzja:** 5000 pozostaje jednorazowym sufitem diagnostycznym; produkcyjny default to 1500 z jawnym override CLI.
- **Lekcja kosztowa:** koszt jednego calla (0,028969 USD), koszt skumulowany runu (0,126793 USD) i koszt całego projektu (0,500616 USD) to trzy różne metryki. Podsumowanie CLI powinno opisywać bieżącą inwokację A2, baza — całą historię runu. Conservative estimate 0,1256 USD był bezpieczny, ale ~4,34× wyższy od calla, więc nie należy nazywać go dokładnym.
- **Co pozostaje otwarte:** brak P1-5 (retry failed candidates), brak prawdziwego fetch źródła i brak pełnej realnej Research Card. Naprawa limitu nie jest dowodem gotowości epistemicznej całego pipeline'u.

### Wnioski z offline preflight pierwszej kompletnej karty (2026-07-12)

- Cztery źródła są celowym minimum odporności: przy progu trzech źródeł pozwalają przeżyć jeden błąd A2, ale nie dwa.
- Trzeba rozdzielać koszt oczekiwany (0,201280 USD), konserwatywny (0,510375 USD) i limit zatwierdzany przez człowieka (0,55 USD). Cap nie jest prognozą.
- Zabezpieczenia strukturalne działają: tryb staged jest domyślny, legacy real path jest blokowany, retry można wyzerować, a limity źródeł i wyszukiwań są przekazywane do narzędzi.
- Nadal istnieją luki: cap działa przed rozpoczęciem, nie w trakcie; timeout może pozostawić nieznany koszt; A2 nie pobiera strony bezpośrednio; dwa błędy ekstrakcji zatrzymają syntezę; B nie ma jeszcze realnego sukcesu.
- Wynik preflight pozwala poprosić właściciela o zgodę, ale nie jest obietnicą powstania karty. Werdykt techniczny: READY FOR OWNER APPROVAL.

### Wnioski po uszczelnieniu cache'a kosztu i SQLite (2026-07-12)
- **Co zaskoczyło:** koszty można księgować poprawnie przy każdym pojedynczym wywołaniu, a mimo to mieć błędne podsumowanie całego runu, jeśli pole cache'a jest aktualizowane lokalną zmienną tylko z bieżącego etapu.
- **Co działa:** append-only `model_usage` jako kanon; dla researchu zapis usage i absolutne odtworzenie `runs.cost_usd` z tej księgi są jedną transakcją. Idempotentny helper pozostaje dla sukcesu, błędu, resume i wtedy, gdy żadnego nowego calla nie było.
- **Granica rozwiązania:** WAL jest potwierdzany dla bazy plikowej, a timeout 5000 ms jest ustawiany przed próbą przełączenia trybu; nie zastępuje to przyszłego workera, lease ani walidacji przejść stanów.
- **Materiał do artykułu:** dobra, zwięzła lekcja: „pole z całkowitym kosztem nie powinno być drugim księgowym; powinno być odtwarzalnym widokiem księgi".

### Wnioski po jawnym retry A2 (2026-07-12, ADR-024)
- **Co zaskoczyło:** „wznów run” i „spróbuj ponownie tego samego źródła” brzmią podobnie, ale są różnymi decyzjami kosztowymi. Zlanie ich w jedno zwykłe resume ukryłoby następne wywołanie modelu.
- **Co działa:** `attempts` zapisuje rozpoczęte A2, retry jest osobnym ruchem z capem, a wyczerpanie daje `PARTIAL_EXHAUSTED` zamiast pętli pozornie wznawialnych komend. Reset jest bezpłatny i idempotentny.
- **Granica rozwiązania:** licznik chroni przed niekontrolowanym retry, nie tworzy nowych kandydatów ani nie poprawia P0-2c; re-discovery pozostaje przyszłą, odrębną decyzją.
- **Dowód:** pamięciowa kopia historycznej bazy przeszła oba pragma, 14 regresji Task 3 i 153 testy pełne; koszt pracy 0 USD i zero API.

### Wnioski po korekcie retry przez niezależne review (2026-07-12)
- **Co zaskoczyło:** „inkrementuj tuż przed callem” jest dobrą ostrożnością kosztową, ale nie jest opisem faktu, że call na pewno dotarł. Awaria zamienia tę różnicę w decyzję produktową.
- **Co działa:** atomowy claim zapisuje rezerwację i `EXTRACTION_IN_PROGRESS`; zwykłe resume zatrzymuje się przy niepewności. Historyczna baza dostaje minimalną wiedzę 0/1, nie wygodną fikcję zera.
- **Granica rozwiązania:** nie ma automatycznego timeout recovery. Przyszły worker musi kiedyś dostarczyć jawny lease/recovery, ale dziś bezpieczniej odmówić niż kupić kolejny call.
- **Materiał do artykułu:** „Najważniejszą informacją po awarii nie jest to, ile razy próbowaliśmy. Jest nią to, czy wolno nam udawać, że wiemy, co stało się ostatnim razem.”

### Wnioski po walidacji lifecycle (2026-07-12, ADR-027)
- **Co zaskoczyło:** poprawna lista statusów nie chroni przed race, jeśli SELECT i UPDATE są osobnymi krokami.
- **Co działa:** status źródłowy i docelowy spotykają się w jednym atomowym UPDATE; `rowcount` jest dowodem wygranej albo konfliktu, a no-op istnieje tylko tam, gdzie kontrakt mówi o nim wprost.
- **Granica:** nie jest to rozwiązanie P2-17 dla dwóch świeżych researchów tego samego tematu; przyszły claim tematu nadal wymaga osobnej decyzji.
- **Dowód:** plikowa SQLite, race terminalizacji, resume i claimu, rollback po reopen, 330 testów i 0 USD.

### Wnioski z korekty dwóch P1 Task 8 (2026-07-13)
- **Jawność:** wyjątek nie jest jawny dlatego, że komentarz nazywa go resume; musi mieć osobny kontrakt i wymagane dane domenowe.
- **Concurrency:** dwa połączenia sekwencyjne dowodzą warunku statusu, ale nie dowodzą zachowania przy wspólnym starcie. `Barrier` zmienia test jakościowo.
- **SQLite:** SELECT w rozpoczętej transakcji może stworzyć konflikt upgrade-lock. Bezpieczeństwo powinien nieść warunkowy UPDATE i CAS, a nie utrzymywany read-lock.
- **Dowód:** dwa race tests powtórzone 10 razy, 337 testów, 0 USD.

### Wnioski z pierwszego realnego Task 9 (2026-07-13)
- **Trwałość zadziałała:** A1 i cztery A2 zostały opłacone raz, zapisane i nie zniknęły po błędzie B.
- **Bramka sukcesu zadziałała:** cztery VERIFIED nie wystarczyły do ogłoszenia wyniku; bez poprawnej Research Card cały Task 9 pozostaje nieudany.
- **Cap był bezpieczny:** 0,170050 USD wobec 0,510375 USD conservative i 0,55 USD limitu; zero retry.
- **Nowa luka:** odzyskiwalny `research_runs=SOURCES_COMPLETE` współistnieje z ogólnym `runs=RUNNING` po zakończeniu procesu. Odzyskiwalność i prawdziwość audytu to dwa różne wymagania.

## Otwarte pytania (do rozstrzygnięcia danymi, nie opinią)
- Czy szacunek kosztu dry_run jest bliski rzeczywistości?
- Jaki procent szkiców agenta przejdzie bez poprawek człowieka?
- Czy jakość tekstu utrzyma się w serii (ryzyko powtarzalności stylu, R12)?
- Ile realnie minut człowieka zajmuje akceptacja jednego artykułu?
- **Nowe (po ADR-017):** czy wskaźnik poprawek/odrzuceń na LEVEL_2 (bez ręcznej akceptacji) będzie porównywalny do LEVEL_1 (z akceptacją) — to bezpośredni test, czy scoring faktycznie zastępuje człowieka, czy tylko udaje, że zastępuje.

## Powiązania
- `07_BLEDY_I_NIEUDANE_PROBY.md`, `08_INTERWENCJE_CZLOWIEKA.md`, `09_KOSZTY.md`, `15_PLAN_SERII_ARTYKULOW.md`, `docs/DECISIONS.md` ADR-017, ADR-019, ADR-020

### 2026-07-13 — wniosek po pierwszym realnym B

„Dane są odzyskiwalne” i „audit mówi prawdę” to dwa niezależne wymagania. `SOURCES_COMPLETE` uratowało cztery opłacone źródła, ale pozostawione `RUNNING` fałszowało stan procesu. Poprawny kontrakt musi zachować oba fakty naraz: szczegółowy research jest wznawialny, ogólny run jest terminalnie FAILED. Drugi wniosek: podniesienie limitu ma sens wyłącznie razem z pomiarem, zwięzłym promptem i przeliczeniem capu.

### 2026-07-13 — wniosek po kontrolowanym repair

Historyczne dane można naprawiać bez utraty audytowalności, jeśli zgoda, preconditions, CAS, `rowcount`, backup i porównanie po reopen są częścią jednej procedury. Terminalny FAILED nie usuwa odzyskiwalności B: `research_runs=SOURCES_COMPLETE` nadal mówi, skąd można wznowić, a `runs=FAILED` mówi prawdę o zakończonej próbie. Resume pozostaje osobną, potencjalnie płatną decyzją.

### 2026-07-13 — wniosek po pierwszej realnej karcie

Resumability przyniosło mierzalny zwrot: zamiast powtarzać pięć calli A1/A2, system zapłacił 0,013914 USD wyłącznie za B i domknął run. Jednocześnie COMPLETE nie znaczy „publikowalne”: REJECT wykazał brak wystarczającego mapowania tezy i twierdzeń do źródeł. Etap 0 dowiódł odporności technicznej; jakość dowodów pozostaje pracą Etapu 2. P2-20 przypomina, że bieżące pole error powinno mieć jednoznaczną semantykę względem historycznego stage logu.

### 2026-07-13 — wniosek przed automatyzacją retry

Scheduler nie może decydować o ponowieniu na podstawie etykiety „provider error”. Potrzebuje zamkniętej taksonomii i domyślnej odmowy: dopiero jawny timeout, network, 429 albo wybrany 5xx jest kandydatem do retry, a i wtedy budżet może zatrzymać kolejną próbę. Błędy formatu i walidacji nie stają się bardziej poprawne przez drugi płatny call. Brak lokalnego usage również nie dowodzi braku rachunku — P2-19 pozostaje granicą obserwowalności.

Typowany wyjątek ma wartość także po zakończeniu procesu. Jeśli przy zapisie zostaje z niego tylko komunikat, przyszły operator lub worker nie odróżni 401 od 422 bez ponownej interpretacji tekstu. Trwały audit musi więc zachować klasę i bezpieczne skalarne metadane, ale nie provider payload ani raw response.

### 2026-07-16 — automatyzacja nie musi oznaczać większego prawa

Task Scheduler zwiększa regularność uruchomienia, ale nie uprawnienia. Ten sam Policy Engine, lease i SQLite nadal rozstrzygają wykonanie, a `--offline-only` dodatkowo odcina paid runner. Podobnie raport jest użyteczny właśnie dlatego, że nie „uzupełnia” braków zerem. Migracja jest bezpieczniejsza, kiedy procedura kończy się kandydatem i raportem, a nie automatyczną podmianą produkcji. `CANDIDATE COMPLETE` opisuje stan dowodu, nie zgodę na live.

### 2026-07-17 — poprawny czujnik może być źle wpięty

`DB_HANDLES_PRESENT` nie był błędnym pomiarem. System naprawdę widział otwartą bazę. Błąd leżał poziom wyżej: composition root sam tworzył stan, którego probe miał zabronić. To ważne rozróżnienie, bo naprawą nie jest poluzowanie czujnika, tylko zmiana kolejności zasobów.

Pierwszy realny request pokazał też, że „provider odpowiedział” i „workflow odniósł sukces” są osobnymi zdarzeniami. HTTP 200 uruchamia obowiązek księgowy, nie gwarancję Research Card. Usage i settlement muszą przetrwać nawet wtedy, gdy parser odrzuci odpowiedź. W tym przebiegu infrastruktura osiągnęła cel exact-once, a produkt zakończył się uczciwym `FAILED`.

### 2026-07-17 — stabilny identyfikator nie zawsze powinien być nazwą pliku

Session ID ma być deterministyczny, bo wiąże job, request i fence. Raport ma być historyczny, więc musi rozróżniać invocation. Użycie jednego klucza do obu zadań wygląda elegancko, dopóki drugi przebieg nie zastąpi pierwszego dowodu. Dobre modele tożsamości rozdzielają „to samo logicznie” od „inne zdarzenie w czasie”.

Podobnie parser nie powinien udawać, że wydobycie obiektu ze środka prose jest naprawą bez kosztu poznawczego. Jeśli kontrakt mówi „jeden object”, prose przed lub po jest błędem, a nie materiałem do zgadywania. Pełny fence jest jednoznaczną warstwą transportową; dwa obiekty już nie. Exact-once obejmuje także pokusę, by po nieudanym parse poprosić model o poprawkę.

Najważniejszy wniosek z forensics jest negatywny: czasem najbardziej uczciwym wynikiem jest `INSUFFICIENT DURABLE EVIDENCE`. System może poprawić przyszły dowód, ale nie może cofnąć się i dopisać brakującego stop reason do historii.

## 2026-07-17 — Prywatność i typy są częścią lifecycle

Prywatny plik nie może być wyjątkiem od redakcji sekretów. Jeżeli zapis diagnostyki jest best-effort, jego failure nie może też zmieniać wyniku finansowego ani uruchamiać ponowienia. Wspólny sanitizer i atomowy zapis oddzielają jakość dowodu od wyniku requestu.

Drugi wniosek: poprawna składnia nie oznacza poprawnej wartości. 400-cyfrowy integer jest legalnym JSON-em, ale nielegalnym score. Typowana walidacja musi nastąpić przed stratną konwersją, inaczej błąd reprezentacji może rozerwać exact-once ledger.

## 2026-07-17 — Zamknięcie Etapu 1: sukces nie jest tym samym co udany artykuł

Etap 1 został formalnie zamknięty, mimo że jedyny realny request skończył się błędem parsowania i nie powstała Research Card. To był świadomy wybór kryterium: celem Etapu 1 był domknięty, audytowalny lifecycle jednego realnego, capowanego requestu — dokładnie jeden attempt, `REQUEST_STARTED → SETTLED`, jedno usage, terminalny `FAILED`, zero retry, fail-closed flagi i bajt-w-bajt nietknięta produkcyjna baza. Wszystko to zaszło i zostało niezależnie zweryfikowane (`APPROVE WITH MINOR/P2`). Pozytywna karta researchowa to cel Etapu 2, nie bramka Etapu 1.

Drugi wniosek: rola „reviewera" i rola „właściciela zamykającego etap" muszą być rozdzielone. Reviewer stwierdził brak MAJOR/CRITICAL i rekomendował możliwość zamknięcia; formalną decyzję podjął właściciel. Dwa pozostałe drobne P2 dotyczą wyłącznie etykiet diagnostycznych parsera (zachowanie fail-closed jest poprawne) — trafiły do backlogu Etapu 2, a nie do kolejnej fali naprawczej. Dyscyplina „nie naprawiaj przy okazji" to część tego, co pozwoliło etap zamknąć bez ryzyka regresji.

## 2026-07-17 — Cel operacji nie rozszerza jej autoryzacji

Jeśli pozytywny wynik wymaga działania jawnie zabronionego, poprawnym rezultatem nie jest obejście z późniejszym przywróceniem stanu. Jest nim zatrzymanie przed pierwszą mutacją. „Net zero diff” nie oznacza „zero zmian kodu”.

## 2026-07-18 — Limit, którego nie mierzysz, nie jest limitem

Dwa ucięcia przy różnych wartościach `max_tokens` miały wspólną przyczynę: budżet wyjścia konsumowały niewidoczne tokeny (rozumowanie, tool-use, cytowania), których nikt nie liczył. Wniosek pierwszy: kontrakt rozmiaru musi być jawny po obu stronach — model dostaje limity per pole, a system deterministycznie je egzekwuje, zamiast ufać dobrej woli modelu. Wniosek drugi: wartość limitu ma wynikać z rachunku (payload na granicach + zmierzony narzut + margines), nie z tego, że poprzednia była za mała. Wniosek trzeci: przekroczenie budżetu to typowany, terminalny błąd z zachowanym kosztem — ciche obcinanie treści byłoby gorsze niż porażka, bo ukrywałoby utratę danych w produkcie.

## 2026-07-18 — Rozliczenie i wykonanie potrzebują osobnych dowodów

Attempt `SETTLED` mówi, że pieniądze zostały rozliczone, ale nie dowodzi jeszcze, że wszystkie encje wykonawcze są terminalne. Recovery po crashu musi więc zachować finansowy finał i dopisać osobny, walidowany fakt wykonawczy. Ta sama zasada porządkuje review: historia prywatnego brancha i końcowe drzewo produktu są różnymi artefaktami, więc właściciel może świadomie zaakceptować pierwsze i wymagać czystości drugiego.

## 2026-07-18 — Zamknięcie może być czynnością wyłącznie dokumentacyjną

Kiedy kod przeszedł niezależny review i został zmergowany, „zamknięcie fali" nie oznacza już pisania kodu. WAVE E2-A zamknięto zmianą wyłącznie dokumentów: stanu projektu, rejestru decyzji i kroniki. Kod, testy, migracje i produkcyjna baza pozostały bajt w bajt takie same. Ta dyscyplina — oddzielić moment implementacji od momentu formalnego zapisu — pozwala zamknąć falę bez ryzyka wprowadzenia nowej regresji przy okazji porządków, a rozdzielenie ról implementera, reviewera i właściciela zamykającego etap chroni przed samopotwierdzeniem.

Drugi wniosek dotyczy drobnych ustaleń review. Nie każdy finding trzeba naprawić od razu; część rozsądniej jest jawnie przyjąć jako P2 z opisanym wpływem i — co najważniejsze — z warunkiem ponownej oceny. „Brak triggera niemutowalności payloadu" nie jest dziś problemem, bo wspierane flow re-waliduje payload — ale musi zostać ponownie rozpatrzony, zanim pojawi się cokolwiek płatnego lub działającego na zewnątrz. Zapisany warunek `MUST REASSESS` zamienia cichy dług w widoczną bramkę przyszłego etapu.

## 2026-07-19 — Stan sprawdzony chwilę temu nie jest stanem autoryzowanym teraz

Preflight i snapshot mogą oba być poprawne, a mimo to decyzja o zapisie może być już nieaktualna. Dlatego granica bezpieczeństwa nie kończy się na „mamy backup". Musi ponownie związać fizyczny plik, jego hash, rozmiar, ledger i brak sidecarów z chwilą writable open.

Drugi wniosek: „recovery" nie oznacza automatycznego retry ani ukrytego restore. Jeżeli migracje commitują per krok, uczciwy system raportuje ostatni trwały szczebel i wymaga nowej decyzji właściciela. Bezpieczne wznowienie jest nową operacją, nie kontynuacją starego pozwolenia.

## 2026-07-22 — Dokładna approval wymaga dokładnego dispatchu

Approval może wiązać wszystkie parametry requestu, a mimo to być niewystarczająca, jeśli publiczny composition root wybiera dowolny rekord kolejki. Granica bezpieczeństwa musi sięgać aż do claimu: ten sam `job_id`, który zatwierdził człowiek, musi trafić do `claim_specific_job`.

Drugi wniosek dotyczy dwóch rodzajów recovery. Przywrócenie policy flags po przerwaniu procesu nie daje prawa do ponowienia płatnego requestu. Marker może naprawić konfigurację, lecz decyzja o dalszym lifecycle pozostaje w trwałym attempt/reconciliation i wymaga jawnej operacji operatora.

## 2026-07-23 — Pesymistyczny cap jest rezerwacją, nie prognozą rachunku

Cap `0.024303 USD` był wyliczony tak, by bezpiecznie objąć graniczny output. Rzeczywisty rachunek `0.013128 USD` nie unieważnia marginesu — pokazuje, że rezerwacja i settlement pełnią różne role. Pierwsza chroni decyzję przed requestem, drugi zapisuje fakt po nim.

Najważniejszy dowód sukcesu był negatywny: nie pojawił się retry, drugi attempt, search, maintenance, browser ani publikacja. Controlled-live jest wiarygodny nie dlatego, że „coś wygenerował”, lecz dlatego, że trwały ledger potrafi policzyć zarówno to, co się wydarzyło, jak i to, co pozostało niemożliwe.

## 2026-07-23 — Zamknięty etap nie oznacza nieograniczonego systemu

Etap 2 można było zamknąć, ponieważ dowód dla jego zakresu był kompletny i niezależnie zrecenzowany, nie dlatego, że agent umie już wszystko. L1 nadal ogranicza realne działania, LEVEL_3 nie jest potwierdzone, a publikacja nie została zweryfikowana.

Jawne P2 są częścią uczciwego zamknięcia. Proceduralne sidecary, minimalny raport i historyczny ledger legacy pozostają widoczne, ale nie unieważniają jednego rozliczonego requestu i terminalnego lifecycle. Kolejny etap wymaga nowej decyzji, nie automatycznego rozpędu.
## 2026-07-23 — Po WAVE C2

- Trwały brief jest granicą między evidence a writerem; log nie wystarcza.
- „Jedna poprawka” wymaga trwałego intentu i podłogi attempt #2, inaczej łatwo staje się nieograniczonym retry.
- Logiczną decyzję o modelu można utrwalić bez wymyślania API ID; `UNVERIFIED` jest prawidłowym stanem.
- Profil stylu powinien być pochodną wysokiego poziomu. Raw korpus nie powinien trafiać do runtime ani każdego promptu.
- Brak przykładów Notes trzeba nazwać `PROVISIONAL`, nie ukrywać lepszym copy.

## 2026-07-23 — Po WAVE C3

- Provider-ready to cecha kontraktu i recovery, nie dowód, że provider jest włączony.
- Logical model name, API model ID i pricing są trzema różnymi faktami; połączenie ich w jeden string tworzy cichy fallback.
- Usage po błędnym JSON-ie nadal jest faktem finansowym i musi zostać rozliczone.
- Najtrudniejsze okno restartu leży po powrocie callera, ale przed trwałym wynikiem. Bez dowodu nie wolno retry'ować.
- Heartbeat powinien wynikać z relacji timeout↔lease, nie z samego istnienia P2.

## 2026-07-24 — Po WAVE C4

- Autonomiczna decyzja bez fingerprintu wejścia jest tylko zapamiętanym wynikiem, nie audytem.
- LEVEL_3 nie oznacza fail-open: komplet evaluations, hard policies i progi są ostrzejszym warunkiem niż sam poziom autonomii.
- Rewalidacja musi nastąpić pod tym samym lockiem i fence, pod którym zapisuje się lifecycle.
- Human-required również jest decyzją Policy Engine i zasługuje na trwały audit, choć nie jest autonomicznym approvalem.
- `content_runs` może zachować wynik wykonania C3, podczas gdy `content_items` niesie końcową decyzję C4; trzeba nazwać tę granicę, aby nie pomylić jej z niespójnością.
- Zero nowych calli jest łatwiejsze do udowodnienia, gdy C4 API w ogóle nie przyjmuje providera.
