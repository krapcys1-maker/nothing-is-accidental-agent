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

## Otwarte pytania (do rozstrzygnięcia danymi, nie opinią)
- Czy szacunek kosztu dry_run jest bliski rzeczywistości?
- Jaki procent szkiców agenta przejdzie bez poprawek człowieka?
- Czy jakość tekstu utrzyma się w serii (ryzyko powtarzalności stylu, R12)?
- Ile realnie minut człowieka zajmuje akceptacja jednego artykułu?
- **Nowe (po ADR-017):** czy wskaźnik poprawek/odrzuceń na LEVEL_2 (bez ręcznej akceptacji) będzie porównywalny do LEVEL_1 (z akceptacją) — to bezpośredni test, czy scoring faktycznie zastępuje człowieka, czy tylko udaje, że zastępuje.

## Powiązania
- `07_BLEDY_I_NIEUDANE_PROBY.md`, `08_INTERWENCJE_CZLOWIEKA.md`, `09_KOSZTY.md`, `15_PLAN_SERII_ARTYKULOW.md`, `docs/DECISIONS.md` ADR-017, ADR-019, ADR-020
