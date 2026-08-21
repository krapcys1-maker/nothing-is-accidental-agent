# Audyt agent-v3 — dziennik spostrzeżeń

Stan dokumentu: **audyt bazowy zakończony; rejestr otwarty na wyniki kolejnych napraw**  
Data rozpoczęcia: 2026-08-21  
Zakres: wyłącznie `agent-v3`; `agent-v2` jest tylko materiałem porównawczym i nie wolno go zmieniać.

## Twarda granica pracy

- Nie uruchamiać `--wyslij`.
- Nie uruchamiać skryptów `systemd/`, `wdroz.sh` ani `uruchom-dzien.cmd` z katalogu V3.
- Nie łączyć prototypu z kontem Substack ani z produkcyjną sesją przeglądarki.
- Nie uruchamiać testów z `tests/platne/` ani testów wymagających sieci.
- Nie wykonywać płatnych wywołań modeli.
- W bazowej fazie audytu nie zmieniano kodu funkcjonalnego. Po tej fazie wolno dopisywać dokumentację badawczą; naprawy funkcjonalne wymagają osobnej karty i testu kontrdowodu.
- W V3 istnieją częściowe zmiany prototypowe wykonane przed zawężeniem zadania do samego audytu. Nie są jeszcze zatwierdzone ani w pełni przetestowane i nie wolno traktować ich jako gotowego wdrożenia.

## Ocena ogólna

V2 dało V3 dużo wartościowego materiału: rozbudowany research, deterministyczne podłogi jakości, księgowanie kosztów, kontrolę rytmu, rozdzielenie etapów i pokaźny zestaw testów regresyjnych. Problem nie polega na braku funkcji. Problem polega na tym, że system jest nadal przede wszystkim **generatorem i automatem dystrybucyjnym**, a nie zamkniętą pętlą redakcyjną.

Prawdziwa pętla powinna łączyć:

`hipoteza redakcyjna -> materiał -> tekst -> kontrola -> publikacja -> wynik w kilku wymiarach -> reakcje jakościowe -> ostrożna obserwacja -> następna decyzja`.

W obecnym V3 zaimplementowane lub naszkicowane są głównie elementy lewej połowy. Tabele pamięci i metryk istnieją, ale nie mają jeszcze kolektorów, połączeń ani procesu wyciągania obserwacji. Bez tego „pamięć redakcyjna” pozostaje strukturą danych, nie pamięcią uczącej się redakcji.

## Rejestr ustaleń

Priorytety:

- **P0** — możliwość dotknięcia produkcji, publikacji błędu lub fałszowania stanu.
- **P1** — blokuje prawdziwą pętlę redakcyjną albo może systematycznie wypaczać decyzje.
- **P2** — dług konstrukcyjny, testowy lub dokumentacyjny.

### A-001 — P0 — skrypty V3 uruchamiają produkcyjne V2 z `--wyslij`

Dowód:

- `agent-v3/systemd/nia-agent.service` uruchamia `agent-v2/run.py --dzien --wyslij`.
- `agent-v3/systemd/nia-artykul.service` uruchamia `agent-v2/run.py --wyslij`.
- `agent-v3/uruchom-dzien.cmd` uruchamia `agent-v2\run.py --dzien --wyslij`.
- `agent-v3/wdroz.sh` sprawdza, wdraża i kopiuje pliki V2.

Skutek: uruchomienie „narzędzia z V3” może ominąć znacznik kopii testowej V3 i bezpośrednio dotknąć produkcji V2. To najważniejsza przyczyna, dla której żadnego skryptu operacyjnego V3 nie wolno teraz uruchamiać.

### A-002 — P0 — prototyp nie jest hermetycznie odcięty od sekretów i sesji produkcyjnej

Dowód:

- `config.py` ładuje nie tylko `agent-v3/.env`, lecz także `.env` z korzenia repozytorium.
- `browser.py` zna produkcyjny uchwyt publikacji i ścieżkę zapisanej sesji.
- Sam brak `--wyslij` nie oznacza pracy offline: rutyna dnia czyta prawdziwy profil, kanał i aktywność; przebieg artykułu korzysta z zewnętrznych modeli, wyszukiwarki i stron.

Skutek: przypadkowe uruchomienie prototypu może nie publikować, ale nadal używać rzeczywistych kluczy, ponosić koszt i czytać stan produkcyjnego konta. V3 potrzebuje później osobnego, jawnego trybu laboratoryjnego, który nie widzi sekretów ani sesji.

### A-003 — P0 — znacznik kopii blokuje tylko jedną ścieżkę

`TO_JEST_KOPIA_TESTOWA` blokuje `run.py --wyslij`, co jest wartościową ochroną. Nie chroni jednak przed:

- skryptami V3 wywołującymi bezpośrednio V2;
- bezpośrednim wywołaniem funkcji z `browser.py` poza `run.py`;
- odczytem produkcyjnej sesji i płatnymi wywołaniami bez `--wyslij`;
- świadomym lub przypadkowym usunięciem jednego łatwo usuwalnego pliku.

To dobra ostatnia zapora, ale nie może być całą izolacją prototypu.

### A-004 — P0 — `KILL_SWITCH` nie jest globalnym wyłącznikiem

`KILL_SWITCH` jest sprawdzany przez `llm._preflight`, ale nie przez warstwę przeglądarki. Polubienie, obserwacja, subskrypcja albo inna akcja niewymagająca modelu może nadal dojść do skutku. Nazwa sugeruje wyłączenie całego agenta, kontrakt realizuje tylko wyłączenie modeli.

### A-005 — P0 — dotychczasowa kontrola właściwego konta była pozorna

Pierwotna funkcja `wlasciwe_konto()` pytała publiczny endpoint profilu. Publiczna odpowiedź potwierdza, że wskazany profil istnieje, a nie że bieżąca sesja należy do niego. Anonimowy użytkownik mógł dostać tę samą odpowiedź.

W bieżącym katalogu V3 znajduje się częściowa poprawka używająca profilu `self` i członkostwa w publikacji. Powstała przed przejściem w tryb „tylko audyt” i nie ma jeszcze testów kontraktowych, dlatego jej status brzmi: **kierunek właściwy, implementacja niezatwierdzona**.

### A-006 — P0 — raport dnia liczy próby jako wykonane działania

Dowód w `run.py`:

- `zrobione["odpowiedzi"] += 1` wykonuje się także bez potwierdzonej odpowiedzi i w trybie niewysyłającym.
- `zrobione["notki"] += 1` wykonuje się niezależnie od `wynik["wyslane"]`.
- oba bloki komentarzy zwiększają licznik bez sprawdzenia wyniku funkcji przeglądarkowej;
- historia celu komentarza jest oznaczana przed upewnieniem się, że komentarz rzeczywiście istnieje;
- stan rytmu jest ustawiany po próbie, a nie po potwierdzonym działaniu.

Skutek: raport, budżet dzienny i historia kontaktów mogą opisywać świat, który nie zaistniał. Jest to błąd pomiarowy i redakcyjny, nie kosmetyczny.

W `browser.py` istnieją rozpoczęte przed audytem poprawki potwierdzania polubień i restacków. Nie rozwiązują jeszcze liczenia odpowiedzi/notek/komentarzy w `run.py` i nie są przetestowane.

### A-007 — P0 — awaria weryfikacji komentarza przepuszcza komentarz

`stages.zweryfikuj()` zwraca `safe_to_post=True`, gdy samo sprawdzanie faktów zakończy się wyjątkiem. Komentarz wyjaśnia to istnieniem „pierwszej siatki”, ale `sprawdz_fakty()` nie ma wywołania w normalnym przepływie komentarza. Tekst powstaje z wiedzy modelu, a po awarii jedynej działającej weryfikacji zostaje uznany za bezpieczny.

Skutek: dokładnie w chwili utraty kontroli system przechodzi w tryb fail-open. Dla publicznego tekstu jest to odwrotny kontrakt od potrzebnego.

### A-008 — P1 — pamięć redakcyjna jest obecnie niepodłączonym szkieletem

W `editorial.py` istnieją funkcje:

- `record_snapshot()`;
- `record_activity_event()`;
- `upsert_observation()`;
- `editorial_report()`.

Poza samym modułem żadna z nich nie jest wywoływana. `memory_brief()` trafia do skauta i pisarza, ale tabele metryk, sygnałów i obserwacji pozostaną puste. System ma wejście dla pamięci, lecz nie ma procesu, który tę pamięć tworzy.

### A-009 — P1 — brak kolektora metryk i porównywalnych okien pomiarowych

Nie ma kodu, który pobiera rzeczywiste wyniki artykułów/notek i zapisuje je przez `record_snapshot()`. Dodatkowo obecne koszyki czasu są zbyt szerokie:

- wszystko do 3 godzin trafia do `1H`;
- wszystko od ponad 3 do 72 godzin trafia do `24H`;
- wszystko powyżej 72 godzin, także po wielu tygodniach, trafia do `7D`.

Porównanie wyniku po 20 minutach z wynikiem po 3 godzinach albo po 4 dniach z wynikiem po 30 dniach nie jest porównaniem tego samego z tym samym.

### A-010 — P1 — brak procesu zamieniającego dane w ostrożne obserwacje

`upsert_observation()` potrafi przechować obserwację i poziom pewności, lecz nic nie ustala:

- jaka hipoteza jest testowana;
- które publikacje są jej próbką;
- jaki jest kontrprzykład;
- kiedy obserwację osłabić lub wycofać;
- czy korelacja formy z wynikiem nie wynika z tematu, pory lub wielkości konta.

Bez tego łatwo zbudować automatyczne przesądy redakcyjne, np. „ten rodzaj otwarcia działa”, na podstawie kilku nieporównywalnych tekstów.

### A-011 — P1 — taksonomia reakcji jest zadeklarowana szerzej niż zbierana

Pamięć pyta o `CURIOSITY`, `DISAGREEMENT`, `CORRECTION` i `DISCUSSION`. Automatyczne mapowanie zdarzeń tworzy głównie `DISCUSSION`, `RESTACK`, `LIKE` i `OTHER`; nie wytwarza `DISAGREEMENT` ani `CORRECTION`. Nie zapisuje też tekstu większości zdarzeń i nie wiąże `target_external_id` z lokalnym `content_id`.

Skutek: system nie umie jeszcze odróżnić aprobaty, pytania, sporu i korekty — czyli sygnałów o całkiem innym znaczeniu redakcyjnym.

### A-012 — P1 — statusy V2 i V3 są niespójne

W V3 występują równolegle dwa modele stanu:

- stary: `SAVED / BLOCKED` i `gates.verdict()` zawsze zwracający `SAVED`;
- nowy: `READY / REVISED / NEEDS_REVIEW / PUBLISHED`.

Konkretny skutek: `db.recent_domains()` wybiera wyłącznie artykuły o statusie `SAVED`. Nowe artykuły V3 nie będą więc zasilać pamięci różnorodności źródeł. Stary `gates.verdict()` pozostaje w kodzie i w testach, mimo że główny przebieg używa innej decyzji.

### A-013 — P1 — rewizja nie jest połączona z artykułem

`record_revision()` jest wywoływane przed zapisem artykułu, bez `article_id`. Po późniejszym utworzeniu artykułu kod nie uzupełnia tego klucza. Rewizję można powiązać z przebiegiem, ale nie bezpośrednio z obiektem treści. Przy więcej niż jednej treści na przebieg albo późniejszych korektach relacja stanie się niejednoznaczna.

### A-014 — P1 — `ODŁÓŻ` ma zapis, ale nie pełny cykl życia

Pozytywna zmiana: temat może zostać zachowany z powodem i brakującym elementem. Nadal brakuje operacji:

- `RESCUED` — brakujący dowód został znaleziony;
- `DISMISSED` — temat świadomie porzucony;
- harmonogramu kolejnej próby;
- limitu prób albo ochrony przed wiecznym powracaniem;
- powiązania nowego researchu ze starym bez nadpisania historii.

Aktualizacja tego samego odłożonego tematu zwiększa `attempts`, ale ponownie ustawia `WAITING` i zastępuje zapis researchu.

### A-015 — P1 — „unused evidence” nie oznacza materiału nieużytego

`run.py` zapisuje do `card["unused_evidence"]` wszystkie fragmenty i liczby z całego `evidence`. Kod nie porównuje ich z faktyczną treścią artykułu. `bank_fragmentow()` następnie traktuje ten zbiór jako niewykorzystane resztki.

Skutek: bank może recyklingować argumenty i fakty, które właśnie zostały użyte. Pamięć oparta na błędnej etykiecie będzie wzmacniać powtórzenia zamiast im zapobiegać.

### A-016 — P1 — cykl źródła kończy się na „pobrano”, nie na „wykorzystano i zacytowano”

Tabela `sources` zna discovery/fetch i awarie. Nie zna:

- czy źródło weszło do karty;
- które twierdzenia wspiera;
- czy pisarz faktycznie użył twierdzenia;
- czy źródło znalazło się w opublikowanym przypisie;
- czy później zostało skorygowane lub przestało być aktualne.

Lista `## Sources` jest budowana tylko z URL-i obecnych w `confirmed_claims`. Źródło liczby lub innego elementu karty może zostać pominięte, jeśli nie występuje także w tej liście.

### A-017 — P1 — cache nie opisuje całego kontraktu etapu

Nowy klucz cache uwzględnia wejście, model i hash promptów, co jest lepsze od starego klucza będącego nazwą etapu. Nadal nie uwzględnia:

- kodu funkcji etapu;
- wartości konfiguracyjnych używanych przy budowie promptu i walidacji;
- czasu ważności danych z sieci;
- wersji schematu odpowiedzi.

Zmiana kodu lub limitu może więc zwrócić wynik ze starego kontraktu. Odwrotnie, zmiana dowolnego niepowiązanego promptu unieważnia cache wszystkich etapów, bo hashowany jest cały katalog promptów. Pliki cache nie są zapisywane atomowo; przerwanie zapisu może zostawić uszkodzony JSON.

### A-018 — P1 — odpowiedzi modeli nie mają walidacji schematu

`llm.parse_json()` znajduje pierwszą i ostatnią klamrę i wykonuje `json.loads`. Nie sprawdza typów, wymaganych pól, dozwolonych wartości ani wersji kontraktu. Walidacja jest rozproszona i nierówna: niektóre etapy sprawdzają listę, inne od razu indeksują pola.

Skutek: poprawny składniowo, ale niepełny JSON może wysadzić późniejszy etap albo — gorzej — przejść z wartościami domyślnymi i zmienić decyzję bez alarmu.

### A-019 — P1 — reguły jakości wymagają kalibracji i dowodu, nie tylko implementacji

Aktualna polityka prototypu zakłada:

- 0–2 zwykłe uwagi: `READY`;
- 3–5: jedna automatyczna rewizja;
- 6+: alarm;
- fakt bez pokrycia: rewizja faktograficzna;
- niedostępna kontrola: alarm.

To sensowny szkic, ale progi nie są jeszcze skalibrowane na zbiorze historycznych artykułów ani udowodnione jako bezpieczna polityka autonomicznej publikacji. „Dwie uwagi” mogą oznaczać dwie drobnostki albo dwie poważne wady konstrukcji. Sama liczba bez ciężaru bramki nie wystarcza.

### A-020 — P1 — automatyczna rewizja nie ma jeszcze dowodu regresyjnego

Istnieje prompt minimalnej rewizji i druga kontrola. Brakuje testów pokazujących, że redaktor:

- usuwa fakt bez pokrycia bez dodania nowego;
- nie zmienia tezy ani głosu;
- zachowuje wszystkie wymagane źródła;
- nie zwiększa liczby wad formy;
- nie ukrywa problemu przez ogólne zastrzeżenie.

Do czasu takich testów rewizja jest hipotezą, nie bezpiecznym etapem redakcyjnym.

### A-021 — P1 — prompt pisarza daje sprzeczne instrukcje o granicach wiedzy

W jednym miejscu nakazuje jeden osobny akapit o granicach. Później nakazuje umieszczać każde niewiadome osobno tam, gdzie się pojawia, i krytykuje zebraną listę granic pod koniec. Obie rady mogą być dobre dla różnych tekstów, ale jednoczesny bezwarunkowy nakaz tworzy konflikt i sprzyja mechanicznemu kompromisowi.

### A-022 — P1 — limity kosztowe sprawdzają przeszłość, nie koszt następnego kroku

Preflight zatrzymuje kolejne wywołanie dopiero, gdy dotychczasowa suma osiągnęła limit. Nie rezerwuje szacowanego maksymalnego kosztu następnego wywołania. Przebieg stojący tuż pod limitem może zacząć najdroższy etap i skończyć wyraźnie ponad limitem.

Nieudane wywołania o nieznanym koszcie są księgowane jako `0.0` z `price_verified=0`. To uczciwie zaznacza niepewność, ale limity nadal liczą zero, więc księga operacyjna może zaniżać realny rachunek do czasu zewnętrznej rekoncyliacji, której nie ma.

### A-023 — P1 — brak w pełni bezpiecznego trybu symulacji

`DRY_RUN` pomija modele i blokuje kliknięcia, ale modele zwracają pusty tekst, więc większość pełnego potoku nie może przejść przez parser JSON. Z kolei zwykły przebieg bez `--wyslij` nadal korzysta z płatnych usług i sieci. Brakuje trybu opartego na fixture'ach, który przechodzi cały przepływ bez sekretów, sieci, kosztów i konta.

### A-024 — P1 — ścieżka artykułu może zostawić przebieg `RUNNING` po `SystemExit`

Rutyna dnia opakowuje `BaseException` i zapisuje `FAILED`. Główny przepływ artykułu łapie tylko `Exception`. Funkcje sesji potrafią rzucić `SystemExit`, który nie jest `Exception`; po takim zdarzeniu po utworzeniu rekordu przebiegu baza może zachować stan `RUNNING`.

### A-025 — P2 — testy V3 utrwalają część kontraktów V2

Przykłady:

- `test_bramki_jakosci.py` oczekuje zawsze `SAVED`;
- `test_podlogi_playbook.py` oczekuje nadal `SAVED`;
- test zapisu wywołań oczekuje `sqlite3.IntegrityError`, podczas gdy nowy ścisły kontrakt celowo rzuca `TypeError` przy brakujących polach;
- część testów sprawdza dosłowne fragmenty źródła zamiast zachowania;
- nie ma testów `editorial.py`, nowego cache, cyklu `ODŁÓŻ`, powiązania rewizji, nowej kontroli konta ani potwierdzenia akcji.

Duża liczba asercji jest wartością, ale nie jest jeszcze dowodem zgodności V3.

### A-026 — P2 — dokumentacja i komentarze opisują sprzeczne epoki systemu

W V3 pozostają dokumenty `JAK_DZIALA_V2.md`, `PLAN_V2.md`, zmienne `AGENT_V2_*`, komunikaty z poleceniami `agent-v2/browser.py`, komentarze o statusach `SAVED/BLOCKED` i zdania „nic nie blokuje”. Część opisuje świadomie historię, część jest nadal operacyjna.

Bez rozdzielenia „archiwum V2” od „kontraktu V3” operator nie będzie wiedział, które polecenie jest aktualne — a A-001 pokazuje, że pomyłka może dotknąć produkcji.

### A-027 — P2 — pytania czytelników nie mają stanu wykorzystania

Pytania są deduplikowane i ograniczone do 200 wpisów, ale `pytania_dla_skauta()` stale zwraca najnowsze. Nie ma stanu: nowe, rozważone, wykorzystane, odłożone, odpowiedziane artykułem. Te same pytania mogą wracać do kolejnych promptów bez informacji, co redakcja już z nimi zrobiła.

### A-028 — P2 — tożsamość publikacji ma więcej niż jedno źródło prawdy

Uchwyt występuje jako `config.SUBSTACK_HANDLE` i osobno jako `browser.PROFIL_HANDLE`. Nawet poprawna kontrola zalogowanego użytkownika może zostać zepsuta przez rozjazd tych dwóch stałych.

### A-029 — P0 — „budżet dnia” nie jest stały w obrębie dnia

`stages.budzet_dnia()` deklaruje, że limity są „losowane osobno na każdy dzień”, lecz wykonuje nowe `random.randint()` i `random.random()` przy każdym uruchomieniu. Wynik nie jest zapisany z datą ani deterministycznie wyprowadzany z daty. Trzy przebiegi tego samego dnia mogą zatem dostać trzy różne cele dobowe.

To narusza podstawowy warunek licznika: od wartości docelowej odejmowane są działania już wykonane, ale sama wartość docelowa zmienia się między pomiarami. Przykładowo późniejszy przebieg może podnieść limit po tym, jak wcześniejszy już go wyczerpał. Bez zamrożonego planu dnia nie da się też odtworzyć, czy agent przestrzegał polityki.

### A-030 — P0 — follow i subskrypcje nie są odejmowane od budżetu dnia

`browser.ile_dzis_wystawione()` zwraca liczniki notek, komentarzy, lajków i restacków. Nie zwraca `follow` ani `subskrypcje`. `run.py` buduje jednak `na_dzis` dla sześciu kategorii przez `budzet[k] - juz.get(k, 0)`. Dla dwóch brakujących kluczy `juz.get(..., 0)` zawsze daje zero.

Skutek: miesięczny budżet zamieniony na dzienny może zostać przydzielony ponownie w każdym z trzech przebiegów. Komentarz w kodzie deklaruje naprawę wcześniejszego mnożenia, lecz przepływ danych nadal nie zapewnia odejmowania już wykonanych obserwowań i subskrypcji. Testy sprawdzają obecność kluczy i kolejność bloków, nie bilans całej doby.

### A-031 — P0 — awaria dziennika może bezgłośnie wyłączyć ograniczenia wolumenu

Komentarze, lajki i restacki liczone są z `dziennik.jsonl`. `browser.zapisz_w_dzienniku()` przechwytuje każde `Exception` i wykonuje `pass`. Jeżeli dysk, uprawnienia lub serializacja zawiodą, działanie może zostać wykonane, lecz licznik nie otrzyma wpisu. Następny przebieg uzna niewidoczne działanie za niewykonane i przydzieli limit ponownie.

Fail-open jest tu szczególnie ryzykowny, bo dziennik nie jest wyłącznie telemetrią: jest elementem mechanizmu bezpieczeństwa. Komentarz „dziennik nie powinien wywalać agenta” opisuje dostępność, ale pomija konieczność zablokowania następnej mutacji, gdy nie da się utrwalić stanu limitu.

### A-032 — P0 — doba operacyjna ma dwie strefy czasowe

Okno publikacji liczone jest według `America/New_York`, natomiast dziennik działań, liczniki dobowe, cichy dzień i promocja artykułu używają daty UTC. W godzinach wieczornych Nowego Jorku po północy UTC polityka dzienna resetuje się w środku dnia odbiorcy.

To może powodować podwójny przydział limitu, zmianę reguły cichego dnia i przesunięcie dnia kampanii promocyjnej w trakcie jednego lokalnego wieczoru. System potrzebuje jawnie zdefiniowanej „doby redakcyjnej”; samo używanie poprawnych stref w poszczególnych funkcjach nie zapewnia poprawności całego kontraktu.

### A-033 — P0 — dopuszczalne źródło może wskazywać zasób prywatnej sieci

Discovery przyjmuje URL zaczynający się od `http`, o ile host nie pasuje do krótkiej listy blokad. Nie znaleziono walidacji adresów IP, rozwiązanego DNS, zakresów prywatnych, loopback, link-local ani endpointów metadanych. URL pochodzący z modelu może potem trafić do klienta HTTP lub przeglądarki.

Jest to powierzchnia SSRF. Sam fakt, że kandydat pochodzi z wyników wyszukiwania, nie jest wystarczającą ochroną: kod weryfikuje host, nie dokładny URL, a dane modelu i strony są wejściem niezaufanym. Każdy przyszły test musi używać fixture'ów; nie należy sondować takich adresów w audycie.

Klient ma `follow_redirects=True`, ale kod nie powtarza walidacji hosta/IP po przekierowaniu. Publiczny URL może więc przekierować do niedozwolonego celu. Do bazy trafia adres pierwotny, nie `response.url`, przez co ślad audytowy nie pokazuje miejsca, z którego rzeczywiście pobrano dokument.

### A-034 — P0 — weryfikacja discovery potwierdza host, nie dokładny dokument

Etap uznaje kandydacki URL za odnaleziony, jeśli w wynikach wyszukiwania pojawia się ten sam host. Model może więc zwrócić nieistniejącą lub sfabrykowaną ścieżkę w prawdziwej domenie i przejść pierwszą kontrolę. Dopiero późniejszy fetch może wykazać błąd, a zachowanie awaryjne potoku nie zawsze blokuje artykuł.

Łańcuch pochodzenia powinien rozróżniać: zapytanie, dokładny wynik wyszukiwarki, przekierowany URL, pobrany dokument, fragment dowodowy i twierdzenie. Obecny test hosta dowodzi wyłącznie związku z domeną.

### A-035 — P0 — twierdzenie faktograficzne może zostać ukryte pod etykietą inferencji

Prompt syntezy wymaga m.in. „parallel mechanisms”, które mają być trafne, lecz nie muszą mieć źródeł. Prompt recenzenta każe nie obalać zdań oznaczonych jako inferencja lub analogia. Jednocześnie klasyfikacja wymusza jedną kategorię na zdanie, a kod nie sprawdza kompletności pokrycia wszystkich zdań recenzją.

Zdanie może zawierać empiryczną przesłankę i inferencję. Oznaczenie całości jako `INFERENCE` tworzy lukę, w której niesprawdzona przesłanka wpływa na artykuł, ale nie uruchamia bramki faktograficznej. Słownik zwrotów ostrzegawczych nie zastępuje strukturalnego rozdzielenia przesłanki, źródła i wniosku.

### A-036 — P1 — minima researchu i syntezy są ostrzeżeniami, nie bramkami

Jeżeli research zbierze mniej materiału niż zakładano, potok ostrzega, lecz może przejść dalej. `fallback_card()` potrafi zbudować kartę z mechanicznych wycinków po awarii syntezy. Głębokość wyznaczona wcześniej może pozostać `RICH`, choć rzeczywisty korpus jest cienki.

W obecnym systemie pojedyncze źródło i jedna uwaga `WASKA_PODSTAWA` nie muszą zablokować publikowalnego statusu. Reguła operacyjna „jeżeli research został opłacony, artykuł ma powstać” konkuruje tu z regułą redakcyjną „tekst powstaje dopiero przy wystarczającej podstawie”. Priorytet nie został rozstrzygnięty jawnie.

### A-037 — P1 — poziom `THIN` dziedziczy długość `RICH`

`config.DLUGOSC_WG_GLEBOKOSCI` nie ma klucza `THIN`, a funkcja pobierająca zakres używa `RICH` jako wartości domyślnej. Dokumentacja opisuje `THIN` jako najkrótszy wariant. Kod odwraca tę intencję: najsłabsza podstawa dostaje domyślnie zakres bogatego artykułu, co zwiększa presję na dopowiadanie i powtórzenia.

### A-038 — P1 — karta syntezy ma co najmniej dwa niezgodne schematy

Normalne `parallel_mechanisms` używają pól `domain` i `how_it_matches`. Mechanizmy dołożone z banku notatek używają `domain`, `mechanism` i `z_banku`. Brak walidacji schematu sprawia, że downstream musi tolerować obie postacie albo cicho zgubi treść.

To przykład szerszej wady kontraktów słownikowych: znaczenie pola jest współdzielone konwencją, bez wersji i bez jednego typu kanonicznego.

### A-039 — P1 — bramka liczb bada kartę, która zawiera dane niebędące korpusem źródłowym

`gates.numbers_outside_corpus()` serializuje całą kartę syntezy i traktuje znajdujące się w niej cyfry jak dopuszczalny korpus. Do chwili kontroli karta zawiera także oceny modelu, analogie, wpisy z banku i URL-e. Liczba pochodząca z metadanych albo komentarza modelu może więc „uprawomocnić” identyczny token w artykule bez źródła.

Dodatkowo porównanie tekstowe jest wrażliwe na format (`2989787` kontra `2,989,787`) i może kolidować z cyframi obecnymi w adresach URL. Poprawna kontrola wymaga listy liczb związanych z konkretnym twierdzeniem i konkretnym fragmentem źródła.

### A-040 — P1 — ochrona przed prompt injection jest powierzchowna

Treść stron i sygnały czytelników są wstawiane do promptów modeli. Funkcja wykrywająca wstrzyknięcia opiera się głównie na frazach obecnych w wygenerowanym wyniku. Nie ma pełnej izolacji niezaufanego tekstu jako danych, polityki ignorowania poleceń ze źródeł ani walidacji, że odpowiedź pozostaje w dozwolonym schemacie i odwołuje się wyłącznie do dowodów.

Brak wykrytej frazy nie dowodzi braku manipulacji semantycznej. Ten problem należy testować na kontrolowanym korpusie ataków, nigdy na produkcji.

### A-041 — P1 — stan jest rozproszony między SQLite, JSON/JSONL i Markdown bez wspólnej transakcji

Oprócz dziesięciu tabel SQLite przepływ używa m.in. `dziennik.jsonl`, `gdzie_komentowalismy.json`, `zuzyte_fakty.json`, `promocja.json`, `bank_notek.json`, `pytania_czytelnikow.json`, `indeks_kandydatow.json`, `alarmy.json`, plików sesji, cache i artykułów Markdown. Większość zapisów JSON nie jest atomowa, a uszkodzony odczyt często wraca jako pusty stan.

Nie istnieje transakcja obejmująca kliknięcie, dziennik, bazę i plik wynikowy. Po awarii nie da się ogólnie stwierdzić, czy brak rekordu oznacza „nie wykonano”, „wykonano i nie zapisano”, czy „zapisano tylko połowę”. Jest to problem semantyki zdarzeń, nie tylko wyboru formatu.

### A-042 — P1 — schemat bazy nie ma wersji, kluczy obcych ani kompletnej ścieżki migracji

Baza ma dziesięć tabel, lecz nie deklaruje wersji schematu ani relacji `FOREIGN KEY`. `CREATE TABLE IF NOT EXISTS` nie aktualizuje tabel istniejących, a ręczna funkcja migracyjna zna tylko `calls.cache_hit`. Nie znaleziono też jawnego kontraktu `PRAGMA foreign_keys`, `busy_timeout` lub trybu WAL.

Przy dalszym rozwoju V3 łatwo otrzymać bazę, której nazwy tabel są poprawne, ale kolumny lub znaczenia pochodzą z innej wersji. Brak kluczy obcych pozwala osierocić źródła, rewizje, obserwacje i metryki bez sygnału błędu.

### A-043 — P1 — test nazwany „martwe sygnały” może dawać fałszywe poczucie pokrycia

Test uznaje część stałych za nieużywane, przeszukując wybrane pliki i celowo wyłączając użycie wewnątrz `config.py`. Tymczasem `WORST_NOTE_HOURS` jest egzekwowane właśnie przez `config.pora_na_publikacje()`. Test może więc raportować stałą jako martwą mimo wpływu na zachowanie.

To reprezentatywny przykład ryzyka testów opartych na wyszukiwaniu tekstu. W repozytorium znajduje się około 52 kontroli statycznego źródła; są przydatne jako alarm konwencji, ale nie zastępują testów ścieżki danych i własności całego dnia.

### A-044 — P1 — lokalny test może tworzyć plik w katalogu danych prototypu

`tests/test_martwe_hosty.py` otwiera ścieżkę `data/zasiew-produkcji.db`. Nawet kontrola opisywana jako darmowa/lokalna nie jest zatem hermetyczna i może mutować katalog danych. W trakcie audytu stwierdzono obecność pustego pliku tej nazwy.

Testy powinny otrzymywać katalog tymczasowy i odmawiać użycia ścieżki operacyjnej. Obecność pliku jest udokumentowana; nie usuwano go, żeby nie wykonywać destrukcyjnej operacji bez polecenia użytkownika.

### A-045 — P1 — wielkie moduły i słownikowe kontrakty utrudniają dowodzenie własności systemu

Cztery największe moduły (`config.py`, `run.py`, `stages.py`, `browser.py`) mają łącznie około 8,4 tys. linii. `stages.py` zawiera 74 funkcje, `browser.py` 54, a `run.py` 15 funkcji i główną orkiestrację. Między etapami przepływają głównie `dict[str, Any]` o nieformalnych schematach.

Nie jest to samo w sobie błąd funkcjonalny, lecz zwiększa koszt audytu i ryzyko zmian: własność taka jak „każde twierdzenie ma źródło” przecina wiele funkcji, promptów i plików stanu. Poprawa V3 nie wymaga przepisywania od zera, ale wymaga wydzielenia jawnych kontraktów na granicach istniejących etapów.

### A-046 — P2 — trzy parametry są statycznie nieużywane

Analiza AST wskazała:

- `recent_domains` w `stages.discovery()`;
- `juz_mamy` w `stages._dobierz_przegladarka()`;
- `findings` w `gates.verdict()`.

Pierwszy potwierdza, że reguła różnorodności nie wpływa na discovery nawet wtedy, gdy baza zwróci dane. Trzeci oznacza, że nazwa `verdict(findings)` sugeruje decyzję opartą na ustaleniach, lecz wynik funkcji nie zależy od przekazanej listy. Każdy przypadek wymaga testu zachowania przed naprawą, bo martwy parametr może ukrywać niedokończony kontrakt albo historyczny interfejs.

### A-047 — P2 — szerokie wyjątki redukują obserwowalność awarii

Analiza AST wykryła 30 szerokich obsług wyjątków w `browser.py`, 19 w `stages.py` i 14 w `run.py`; odpowiednio 9 i 6 przypadków w dwóch pierwszych modułach natychmiast milczy albo przechodzi dalej. Nie każdy szeroki `except` jest błędem — automatyzacja przeglądarki wymaga odporności — ale brak klasyfikacji utrudnia odróżnienie oczekiwanej niedostępności elementu od utraty stanu lub błędnej tożsamości.

W systemie redakcyjnym błąd powinien mieć co najmniej klasę: brak danych, odrzucenie jakości, błąd przejściowy, błąd trwały, niepewna mutacja albo naruszenie bezpieczeństwa. Dzisiaj wiele z nich kończy się takim samym pustym wynikiem.

### A-048 — P1 — rzeczywiste sufity tokenów są definiowane dwuetapowo pod tą samą nazwą

`config.py` najpierw deklaruje tabelę `MAX_TOKENS`, a około 700 linii dalej nadpisuje ją słownikiem, który dodaje do każdego etapu 28 000 tokenów zapasu na rozumowanie. Technicznie jest to celowe przekształcenie, ale nazwa nie odróżnia „sufitu treści” od „sufitu wysyłanego dostawcy”.

Skutek audytowy i operacyjny: osoba czytająca pierwszą tabelę widzi inną politykę niż ta faktycznie używana przez `llm.py`. Nie można też osobno sprawdzić, czy dany dostawca rozlicza rozumowanie w tej samej puli. Dwie wielkości powinny mieć osobne nazwy i być raportowane przy przebiegu.

### A-049 — P1 — kontrakt timeoutu jest sprzeczny z kontraktem sufitu tokenów

Komentarz `timeout_for()` mówi, że termin „realnie pokrywa podany sufit tokenów”, lecz funkcja ogranicza wynik do 300 sekund niezależnie od sufitu. Dla ścieżki DeepSeek z web search wynik jest następnie mnożony przez trzy, więc twardy „sufit na jedno wywołanie” wynosi w praktyce do 900 sekund w jednej gałęzi i 300 w pozostałych.

To może być rozsądna polityka ochrony całego dnia, lecz nie może jednocześnie gwarantować pełnego wykorzystania zadeklarowanego sufitu odpowiedzi. System potrzebuje jawnej decyzji: limit czasu ma pierwszeństwo i ucięcie jest oczekiwane albo limit tokenów jest osiągalnym kontraktem. Obecne komentarze obiecują oba.

### A-050 — P1 — parametr `--topics` nie zmienia statycznych sufitów zależnych od `TOPIC_COUNT`

CLI pozwala wybrać dowolną liczbę tematów, lecz wyliczenia `MAX_TOKENS` dla scouta i feasibility powstają z konfiguracyjnego `TOPIC_COUNT = 6`. Zwiększenie `--topics` zwiększa oczekiwaną odpowiedź i wejście kolejnego etapu bez proporcjonalnej zmiany jego kontraktu wyjściowego.

Testy i dokumentacja powinny albo ograniczyć parametr do wspieranego zakresu, albo obliczać budżety z rzeczywistego wejścia. Obecnie interfejs sugeruje elastyczność, której polityka tokenów nie odzwierciedla.

### A-051 — P1 — ponowienie pisarza omija klasyfikację błędów trwałych

Warstwa `llm.call()` poprawnie rozróżnia błędy przejściowe od `BudgetExceeded`, `PreflightFailed` i `Truncated`. Zewnętrzna obsługa etapu `write` w `run.py` przechwytuje jednak każde `Exception`, globalnie zmienia `config.MODEL_FOR["write"]` i wywołuje pisarza ponownie.

W rezultacie przekroczony budżet, zły kontrakt JSON, brak klucza lub inny błąd trwały uruchamia dodatkową próbę. Globalna zmiana konfiguracji pozostaje do końca procesu i może zaciemnić raport kosztu/modelu. Retry etapu powinien respektować tę samą klasyfikację co adapter, a wybór fallbacku być lokalną, zapisaną decyzją.

### A-052 — P1 — etykieta „confidence” jest wyłącznie przedziałem liczebności

`editorial.confidence_for()` przypisuje `VERY_LOW`, `LOW`, `MEDIUM` albo `HIGH` tylko na podstawie progów 10, 30 i 100 obserwacji. Nie uwzględnia zgodności kierunku, wielkości efektu, wariancji, niezależności próbek, braków danych ani czynników zakłócających. `upsert_observation()` przyjmuje `evidence_count` od wywołującego i na tej podstawie zapisuje etykietę.

Sto powtórzonych migawek tej samej treści albo sto sprzecznych przypadków może więc otrzymać `HIGH`. To nie jest statystyczna pewność, lecz kategoria liczebności. Nazwa i użycie w promptach powinny zachować to rozróżnienie, dopóki nie powstanie jawny model estymacji niepewności.

### A-053 — P1 — przestrzeń nazw środowiska jest tylko częściowo przeniesiona do V3

`config.py` czyta `AGENT_V3_SERVER`, `AGENT_V3_NO_LIMIT`, `AGENT_V3_CHEAP` i `AGENT_V3_WRITER`. Tymczasem `browser.sprawdz_serwer()`, skrypt wdrożeniowy i jednostki systemd nadal ustawiają `AGENT_V2_SERVER`. Funkcja przeglądarki ręcznie nadpisuje jeszcze `config.TRYB_SERWERA`, więc lokalnie może ukryć problem; artefakty usługowe nie mają takiej gwarancji.

Nawet po późniejszej naprawie ścieżek `agent-v2` na `agent-v3` serwis mógłby więc uruchomić V3 w niewłaściwym trybie. Migrację nazwy wersji trzeba traktować jako jeden atomowy kontrakt obejmujący kod, dokumentację, środowisko i usługi.

### A-054 — P1 — pobieranie nie ma twardego limitu rozmiaru odpowiedzi

`fetch()` wykonuje `client.get(url)`, po czym materializuje całe `response.text` albo `response.content` dla PDF. Nie znaleziono limitu bajtów odpowiedzi, liczby stron PDF ani rozpakowanego tekstu przed przetworzeniem. Timeout ogranicza czas oczekiwania, ale nie ilość pamięci i pracy po otrzymaniu danych.

Ponieważ URL jest wejściem pochodzącym z modelu, bardzo duży lub specjalnie skonstruowany dokument może zużyć pamięć, czas parsera i miejsce w późniejszym prompcie. Wymagany jest streaming z limitem oraz osobne limity typów treści; test powinien używać lokalnych fixture'ów o kontrolowanym rozmiarze.

### A-055 — P1 — zapis artykułu może zakończyć się trzema różnymi stanami częściowymi

`stages.save()` zapisuje najpierw plik artykułu, potem plik uwag, następnie rekord `articles` i wykonuje `commit`, a dopiero potem `editorial.register_article()` zapisuje `content_items` w osobnym commicie. Awaria na każdej granicy pozostawia inny podzbiór artefaktów:

- plik bez rekordu bazy;
- artykuł w bazie bez `content_items`;
- plik artykułu bez kompletnych uwag;
- rekord przebiegu `FAILED` obok częściowo poprawnego artykułu.

Ponowienie może dodatkowo nadpisać ten sam plik wynikający z `run_id` i sluga, a jednocześnie dopisać kolejny rekord bazy. Jest to konkretny przypadek ogólnego problemu A-041; potrzebny jest idempotentny plan zapisu i jawna procedura rekoncyliacji.

### A-056 — P2 — nawet odmowa publikacji z kopii następuje po mutacji pliku blokady

`main()` najpierw otwiera i zapisuje `data/agent.lock`, potem parsuje argumenty, a dopiero następnie wywołuje `odmow_publikacji_z_kopii()`. Komentarz mówi, że odmowa następuje „zanim cokolwiek zapisze”, lecz utworzenie/truncacja pliku blokady już zaszły. Nawet `--help` wchodzi najpierw w ścieżkę blokady.

Nie jest to mutacja produkcyjnego konta, ale falsyfikuje obietnicę „zero zapisu przed kontrolą” i utrudnia hermetyczne testy CLI. Kontrola capability prototypu powinna nastąpić przed utworzeniem jakiegokolwiek stanu runtime.

### A-057 — P1 — cache przechowuje pełne wejścia i wyjścia nawet bez `--use-cache`

`run.cached()` zawsze zapisuje envelope po wykonaniu etapu; flaga `--use-cache` decyduje tylko o odczycie. Envelope zawiera `identity.input` oraz `value`. Dla klasyfikacji wejściem jest cały pobrany korpus stron, a dla scouta i pisarza pamięć może zawierać tekst sygnałów czytelników.

Cache jest więc równocześnie archiwum surowych materiałów, odpowiedzi modeli i potencjalnych danych użytkowników. Pliki są jawne tekstowo, nie mają TTL, limitu rozmiaru, rejestru retencji ani procedury usuwania. `.gitignore` chroni przed przypadkowym commitem, ale nie przed lokalnym odczytem, kopią zapasową lub nieograniczonym wzrostem.

### A-058 — P2 — docstring `browser.py` deklaruje dokładne przeciwieństwo zawartości modułu

Nagłówek twierdzi, że moduł czyta wyłącznie publiczne strony bez sesji oraz że publikowanie, komentowanie i polubienia „nie istnieją w tym pliku”. Tymczasem moduł zarządza sesją i zawiera wszystkie główne mutacje: artykuł, notkę, komentarz, odpowiedzi, polubienia, obserwowanie/subskrypcję i restack.

To nie jest kosmetyka. Docstring modułu bywa pierwszym źródłem klasyfikacji bezpieczeństwa dla operatora, audytora lub narzędzia dokumentacyjnego. Fałszywe oznaczenie modułu mutującego jako read-only zwiększa ryzyko użycia go w środowisku, w którym powinien być zabroniony.

### A-059 — P0 — `wyslij=False` może nadal zmieniać żywy szkic na koncie

`naprawde_wyslac()` blokuje końcowy przycisk publicznej akcji, ale nie kontakt z kontem ani wcześniejsze operacje UI. `wystaw_artykul(..., wyslij=False)`:

- wymaga żywej sesji;
- otwiera panel publikacji;
- wypełnia tytuł, treść i grafikę;
- klika „Continue”;
- może kliknąć ustawienie wykrywania AI;
- kończy komunikatem „szkic zapisany”.

Kontrola właściwego konta jest wykonywana tylko przy `wyslij=True`. Tryb rzekomo niewysyłający może zatem utworzyć lub zmienić zdalny draft, potencjalnie na niewłaściwym koncie. Podobnie funkcje notki, komentarza i odpowiedzi w trybie podglądu otwierają żywy interfejs i wpisują tekst w pola.

Wniosek: `--wyslij` rozróżnia głównie publiczne zatwierdzenie, nie „brak zmian w systemie zewnętrznym”. Prototyp offline nie może polegać na tej fladze.

### A-060 — P0 — potwierdzenie artykułu nie identyfikuje konkretnej próby publikacji

`potwierdz_artykul()` uznaje sukces, jeżeli w pięciu ostatnich postach znajduje się tytuł zawierający pierwsze 50 znaków sprawdzanego tytułu i dowolne `post_date`. Nie wiąże wyniku z czasem bieżącej próby, szkicem, zewnętrznym ID ani dokładnym hashem treści.

Jeżeli starszy artykuł ma ten sam lub zbliżony tytuł:

- kontrola przed kliknięciem uzna nowy tekst za już opublikowany;
- kontrola po nieudanym kliknięciu może dać fałszywy sukces;
- lokalny artykuł zostanie oznaczony `PUBLISHED`, choć wskazany post jest innym obiektem;
- wyszukanie adresu może wybrać starszy post lub skonstruować zapasowy slug.

Potwierdzenie mutacji musi używać identyfikatora szkicu/postu zwróconego przez platformę i warunku czasowego, nie podobieństwa tytułu.

### A-061 — P1 — wewnętrzne pętle polubień i restacków nie respektują zegara przebiegu

`run.py` ma `zostal_czas()` i `rytm()`, ale `polub_w_kanale()` oraz `restackuj_w_kanale()` wykonują własne wieloelementowe pętle i losowe `page.wait_for_timeout()` bez dostępu do `_KONIEC_CZASU`. Po wejściu do funkcji mogą kontynuować mimo wyczerpania budżetu całego przebiegu.

Skutek jest poważniejszy niż spóźnienie: systemd może przerwać proces w środku interakcji, pozostawiając mutację o nieznanym skutku i bez wpisu dziennika. Szacowanie `zmiesci_sie()` przed blokiem nie zastępuje sprawdzenia bezpośrednio przed każdą mutacją i przerwą.

### A-062 — P1 — tylko jedna z trzech warstw głosu jest przypięta integralnościowo

Pisarz otrzymuje wybrane przykłady z `STYLE_CORPUS`, profil pozytywny i profil negatywny. Korpus i konkretne akapity są sprawdzane hashami. Dwa profile z katalogu współdzielonego na poziomie repozytorium są jedynie odczytywane; nie mają manifestu wersji ani oczekiwanego odcisku sprawdzanego przez kod.

Komentarz w `config.py` deklaruje odmowę „uczenia pisarza nieprzejrzanego głosu”, ale niezauważona zmiana profilu może zmienić instrukcję stylistyczną bez naruszenia hasha korpusu. Jeżeli profile są zatwierdzonym kontraktem redakcyjnym, muszą mieć tę samą identyfikowalność co przykłady.

Profile leżą poza `PROMPTS_DIR`, więc `_prompt_fingerprint()` także ich nie hashuje. Zmiana profilu nie unieważni cache etapu `write`; `--use-cache` może zwrócić tekst powstały według poprzedniego głosu, choć bieżący plik profilu jest inny.

### A-063 — P2 — kontrola przecieku instrukcji obejmuje tylko surowy `pisarz.md`

`gates.frazy_z_instrukcji()` szuka sześciowyrazowych fraz wyłącznie z pliku `prompts/pisarz.md`. Rzeczywisty prompt pisarza zawiera także wstrzyknięte profile pozytywny/negatywny, przykłady stylu, wylosowany ruch końcowy, pamięć redakcyjną i kartę. Rewizja otrzymuje osobny prompt `redaktor.md`.

Echo dowolnej z tych warstw może trafić do artykułu i nie zostać wykryte. Kontrola powinna porównywać wynik z rzeczywiście wyrenderowanym promptem danego wywołania, z wyłączeniem jawnie cytowanego materiału źródłowego, a nie z jednym plikiem szablonu.

### A-064 — P1 — długość artykułu jest instrukcją, nie egzekwowanym kontraktem

`write()` oblicza zakres według głębokości i wstawia go do promptu, ale po odpowiedzi sprawdza tylko obecność `body`. Kod nie blokuje tekstu krótszego lub dłuższego od zakresu. Pole `limits_paragraph_present` jest wyłącznie samodeklaracją modelu i zostaje wydrukowane, a `numbers_used` nie jest rozliczane z tekstem.

Raport w `run.py` dodatkowo pokazuje stare globalne `TARGET_WORDS/MIN_WORDS/MAX_WORDS` (1075/950–1200), nie zakres faktycznie przekazany dla `RICH` (900–1250) lub `SINGLE` (480–820). Operator może więc zobaczyć fałszywy kontrakt długości, a status nadal zostać `READY`.

### A-065 — P1 — ważność większości bramek redukuje się do samej liczby uwag

`quality_decision()` nadaje specjalne znaczenie tylko bramkom z list `FACTUAL_GATES` i `TECHNICAL_GATES`. Pozostałe są równoważne liczbowo: jedna `FRAZA_Z_INSTRUKCJI`, jedna `WASKA_PODSTAWA`, jedno zakazane otwarcie lub jeden wykryty odcisk powtarzalnej formy prowadzi do `READY`, o ile łączna liczba uwag nie przekroczy dwóch.

Wykryty dosłowny przeciek instrukcji nie jest drobną sugestią stylistyczną; świadczy, że produkt zawiera metatekst procesu. Podobnie niektóre pojedyncze wady mogą być poważniejsze niż pięć kosmetycznych. Polityka potrzebuje ważności i dozwolonej reakcji per bramka, a następnie kalibracji na korpusie, nie tylko progów 0–2/3–5/6+.

### A-066 — P1 — wdrożeniowy smoke test nie instaluje ani nie sprawdza zależności używanych leniwie

`wdroz.sh` po aktualizacji importuje moduły, ale nie wykonuje `pip install -r`, instalacji Chromium ani testów. `trafilatura` i `pypdf` są importowane wewnątrz funkcji fetch, więc sam `import stages` nie wykryje ich braku. Komentarz w `requirements.txt` opisuje już incydent, w którym potok zapłacił za wcześniejsze etapy i dopiero potem upadł na brakującym `trafilatura`.

Dodanie zależności do `requirements.txt` nie aktualizuje środowiska serwera. Po późniejszym dostosowaniu skryptu do V3 potrzebny jest instalacyjny krok transakcyjny i offline smoke test rzeczywistej ścieżki wszystkich leniwych importów przed przełączeniem usług.

### A-067 — P2 — przypięte są tylko zależności bezpośrednie, nie całe środowisko

`requirements.txt` przypina wersje sześciu pakietów bezpośrednich, ale nie zawiera rozstrzygniętych zależności przechodnich, hashy artefaktów, wersji Pythona, systemowych bibliotek Playwrighta ani identyfikatora obrazu środowiska. Deklaracja „serwer ma zachowywać się tak samo jak ten komputer” jest więc silniejsza niż zapewniana odtwarzalność.

To nie wymaga od razu konteneryzacji. Wymaga jednak wygenerowanego lockfile lub pełnego manifestu środowiska oraz sprawdzenia go w hermetycznym teście instalacji.

### A-068 — P1 — rollback wdrożenia może zniszczyć niezapisany stan worktree

Przy nieudanym smoke teście lub sprawdzeniu sesji `wdroz.sh` wykonuje `git reset --hard "$POPRZEDNIA"`. Skrypt wcześniej nie sprawdza, czy drzewo jest czyste, nie tworzy kopii zmian i nie odróżnia plików operatora od kodu wdrożenia.

Na serwerze z lokalną poprawką lub dokumentacją taki rollback może bezpowrotnie ją usunąć. Jest to ryzyko samego narzędzia operacyjnego; w audycie skrypt nie został uruchomiony.

### A-069 — P1 — krytyczne potwierdzenia zależą od niejawnych kontraktów endpointów

Tożsamość, lista postów, komentarze, odpowiedzi, notki, aktywność i restacki są odczytywane z wielu ścieżek `/api/v1/...` przez nawigowanie strony do JSON-u i parsowanie tekstu `body`. Kod zakłada konkretne, różne kształty odpowiedzi (lista, `posts`, `items`, `commentBranches`, `publicationUsers`) bez wersjonowanych fixture'ów kontraktowych.

`api_json()` przy dowolnej odpowiedzi niebędącej JSON-em zwraca `None` bez klasy błędu. Część konsumentów zamyka się bezpiecznie, część interpretuje to jako pusty stan. Zmiana platformy może więc wyglądać jak „brak komentarzy”, „brak wcześniejszej akcji” albo „brak potwierdzenia”, zależnie od miejsca.

System potrzebuje adaptera z jawnym schematem per endpoint, zachowanymi próbkami odpowiedzi i jednym rozróżnieniem: pusty poprawny wynik kontra niezgodny kontrakt.

### A-070 — P1 — potwierdzenie pierwszego restacku niszczy stronę używaną przez dalszą pętlę

`restackuj_w_kanale()` tworzy locatory przycisków na feedzie i iteruje do dziennego limitu 1–2. Po pierwszej mutacji `potwierdz_restack(page, ...)` wywołuje `api_json()` na tej samej karcie. `api_json()` realizuje odczyt przez `page.goto()` do endpointu profilu i feedu JSON, więc karta przestaje przedstawiać pierwotny feed.

Następna iteracja używa locatorów związanych z kartą, która pokazuje już dokument JSON. Drugi restack nie ma wiarygodnej ścieżki wykonania. Szeroki `except` w pętli zamienia ten błąd w „pominięte”, więc przebieg może zakończyć się bez alarmu i bez informacji, że nominalny limit 2 jest nieosiągalny.

### A-071 — P1 — adres źródła trafia do atrybutu HTML bez escapowania cudzysłowów

`rozbierz_artykul()` zamienia listę Markdown na HTML i buduje `href="..."`. Funkcja `_esc()` zastępuje `&`, `<` i `>`, ale nie cudzysłowy. URL pochodzi z łańcucha rozpoczętego przez wynik modelu i nie ma kanonicznej walidacji znaków ani schematu `https` przed zapisem/publikacją.

Adres zawierający `"` może przerwać atrybut i wstrzyknąć dodatkowy HTML do danych wklejanych w zalogowany edytor. Platforma może mieć własny sanitizer, lecz bezpieczeństwo V3 nie może zależeć od nieudokumentowanej warstwy zewnętrznej. URL powinien przejść parser dozwolonych schematów/hostów, a atrybut pełne escapowanie z `quote=True`.

### A-072 — P1 — raport „odpowiedzi na jedno działanie” nie buduje kohort działania i skutku

`alarm.przeglad(dni)` wybiera wpisy według czasu dopisania do lokalnego dziennika. `_co_z_tego_wyszlo()` sumuje wszystkie zdarzenia `comment_reply` przechwycone w oknie i dzieli je przez wszystkie komentarze wystawione w tym samym oknie. Nie wiąże licznika odpowiedzi z identyfikatorami mianownika przy wyliczaniu głównego wskaźnika.

Odpowiedź na stary komentarz przechwycona dzisiaj może więc zostać podzielona przez nowy komentarz z dzisiaj. Analogicznie reakcje wykryte z opóźnieniem przesuwają się między oknami. Późniejsza analiza „wcześnie kontra w tłoku” używa już `nasz_id`, co pokazuje, że złączenie jest możliwe, ale nie jest stosowane do nagłówkowych proporcji notka/komentarz.

Wskaźnik nie mierzy obecnie kohortowej odpowiedzi na działanie; mierzy stosunek dwóch strumieni zdarzeń z podobnego czasu zapisu.

### A-073 — P2 — wewnętrzny przegląd projektów nie jest benchmarkiem naukowym

`tutaj jest do zaczerpiecia z neta.txt` zawiera użyteczny katalog inspiracji, ale także numeryczne oceny autonomii, researchu, analytics i „production hardening”. Sam tekst uczciwie zaznacza, że jest to ocena na podstawie publicznego kodu/dokumentacji, a nie benchmark. Nie podaje jednak protokołu wyszukiwania, dat rewizji repozytoriów, rubryki punktowej ani procedury dwóch niezależnych oceniających.

Wnioski typu „V2 = 9/10” nie mogą być używane jako wynik porównawczy ani dowód dojrzałości V3. Plik należy traktować jako eksploracyjny przegląd literatury szarej i generator hipotez. Każdy zapożyczany mechanizm wymaga osobnej weryfikacji w źródle pierwotnym i lokalnego testu dopasowania do kontraktów V3.


## Kontrole wykonane bez kontaktu z produkcją

- Inwentaryzacja plików V3 i wyszukiwanie statyczne przepływów danych/statusów.
- Parsowanie AST wszystkich 59 plików `.py`: **0 błędów składni**.
- Nie importowano modułów integracyjnych w sposób uruchamiający sieć.
- Nie uruchomiono testów sieciowych ani płatnych.
- Nie uruchomiono żadnego skryptu publikującego, wdrożeniowego ani przeglądarkowego.

## Hipoteza kolejności późniejszych napraw — jeszcze nie wdrażać

1. Fizycznie odizolować V3 od V2, sekretów, sesji i skryptów operacyjnych.
2. Zbudować hermetyczny tryb fixture/offline i dopiero na nim uruchamiać pełny potok.
3. Ujednolicić statusy oraz kontrakty danych; dodać migracje V3 i walidację schematów.
4. Naprawić fail-open oraz liczenie wyłącznie potwierdzonych działań.
5. Domknąć cykl źródła, rewizji i `ODŁÓŻ`.
6. Dopiero potem podłączyć kolektory metryk i sygnałów.
7. Na końcu budować obserwacje redakcyjne z kontrolą próby, czasu i kontrprzykładów.

## Dziennik przebiegu audytu

### 2026-08-21 — wpis 1

- Ustalono granicę: tylko audyt, brak publikacji, brak produkcji, brak zmian funkcjonalnych.
- Potwierdzono, że V2 pozostaje nietknięte przez audyt.
- Zinwentaryzowano V3.
- Wykryto krytyczne odwołania skryptów V3 do produkcyjnego V2.
- Prześledzono statusy artykułu, cache, pamięć, rewizję, pomiar, działania dnia, źródła i księgowanie kosztów.
- Wykonano wyłącznie lokalną kontrolę składni bez importów i bez sieci.

### 2026-08-21 — wpis 2

- Policzone artefakty V3: 117 plików, w tym 59 plików Python i 40 plików Markdown.
- Dwanaście głównych modułów ma 11 239 linii; 36 zwykłych plików testowych ma 6 308 linii, a 10 skryptów testów płatnych 940 linii.
- Dwadzieścia sześć promptów ma 2 843 linie. Wielkość korpusu potwierdza, że V3 należy stabilizować kontraktami, a nie projektować ponownie od zera.
- Odtworzono zależności modułów, model dziesięciu tabel oraz rozproszony stan plikowy.
- Wykryto niespójność doby UTC/Nowy Jork, ponowne losowanie budżetu dnia oraz brak dziennych liczników obserwowań i subskrypcji.
- Wykryto luki pochodzenia źródeł, walidacji URL, klasyfikacji zdań faktograficznych i korpusu liczb.
- Audyt pozostał statyczny; nie importowano ani nie wykonywano kodu integracyjnego.

### 2026-08-21 — wpis 3

- Odtworzono kontrakty cache, kosztu, tokenów, timeoutów, stylu i automatycznej rewizji.
- Potwierdzono, że `wyslij=False` nie jest trybem offline: ścieżka artykułu zapisuje zdalny szkic i wykonuje operacje ustawień przed końcowym przyciskiem.
- Potwierdzono, że kontrola sukcesu artykułu używa podobieństwa tytułu, a nie identyfikatora bieżącej mutacji.
- Prześledzono nawigacyjne działanie `api_json()` i wykryto utratę feedu w wieloelementowej pętli restacków.
- Przeanalizowano konwerter Markdown–HTML, wdrożenie, manifest zależności i raport reakcji.
- Ustalono, że główne wskaźniki reakcji nie są kohortowo łączone z działaniami.
- Dodano macierz epistemiczną z podstawą, pewnością i kryterium obalenia każdego ustalenia.
- Nie uruchomiono żadnego testu, importu agenta, skryptu wdrożeniowego, adaptera sieciowego ani przeglądarki.
