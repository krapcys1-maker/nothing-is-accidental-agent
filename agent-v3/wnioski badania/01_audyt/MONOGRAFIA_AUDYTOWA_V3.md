# Agent V3 jako prototyp autonomicznego systemu redakcyjnego

## Audyt architektury, wiarygodności dowodowej, bezpieczeństwa operacyjnego i zdolności uczenia się

**Status dokumentu:** wersja robocza 0.2, audyt statyczny z późniejszym aneksem porównawczym  
**Data rozpoczęcia:** 2026-08-21  
**Przedmiot badania:** katalog `agent-v3`  
**Materiał porównawczy:** katalog `agent-v2` — wyłącznie do odczytu  
**Rejestr ustaleń:** `SPOSTRZEZENIA_AUDYTOWE.md`  
**Ograniczenie nadrzędne:** bez publikacji, bez produkcji i bez wykonywania płatnych lub sieciowych ścieżek samego agenta; późniejsza kwerenda publicznego kodu była tylko do odczytu

---

## Streszczenie

Przedmiotem badania jest prototyp Agent V3, rozwijany ewolucyjnie z wersji V2. Celem audytu nie jest zaprojektowanie nowego agenta, lecz ustalenie, które elementy istniejącego rozwiązania tworzą już zalążek systemu redakcyjnego, które są wyłącznie deklaracją lub rusztowaniem, a które mogą doprowadzić do błędnej publikacji, utraty pochodzenia dowodów albo niekontrolowanej aktywności konta.

Badanie wykonano metodą statycznej analizy repozytorium: inwentaryzacji artefaktów, rekonstrukcji przepływu sterowania i danych, analizy AST, porównania promptów z kodem wykonawczym, inspekcji modelu stanu oraz replikacji katalogu znanych wad V2 na kodzie V3. Nie uruchamiano integracji, przeglądarki, modeli, publikacji ani testów dotykających sieci lub konta. Tym samym wyniki opisują właściwości implementacji i kontraktów, a nie empiryczną jakość tekstów opublikowanych przez V3.

Audyt wykazał, że prototyp ma rozbudowany potok research–synteza–pisanie–recenzja–rewizja, znaczną bazę promptów i testów oraz sensowne kierunki rozwoju: pamięć redakcyjną, odłożone tematy, rewizje, metryki i sygnały odbiorców. Nie tworzą one jednak jeszcze zamkniętej pętli uczenia się. Najważniejsze bariery to: brak hermetycznej granicy od produkcji; liczenie prób zamiast potwierdzonych skutków; niestabilny kontrakt limitu dnia; rozproszony, nietransakcyjny stan; brak strukturalnej walidacji odpowiedzi modeli; niepełny łańcuch pochodzenia źródła i twierdzenia; fail-open w kontrolach redakcyjnych oraz niewystarczająco wiarygodne testy całych własności systemu.

Szczególnie ważne jest operacyjne rozróżnienie: `wyslij=False` nie oznacza braku zmian zewnętrznych. Kod potrafi przy tej wartości otworzyć zalogowany edytor, wypełnić i zapisać zdalny szkic. Z kolei potwierdzenie artykułu opiera się na podobieństwie tytułu, a nie identyfikatorze bieżącej próby. Dlatego nawet „podgląd” nie jest dopuszczalnym narzędziem badawczym dla prototypu.

Wniosek główny brzmi: V3 nie wymaga przepisania od zera. Wymaga zatrzymania rozbudowy funkcji zewnętrznych i uszczelnienia granic istniejącego potoku. Dopiero po zbudowaniu pełnej symulacji offline można rzetelnie badać, czy automatyczna redakcja poprawia tekst, a pamięć wyników poprawia następne decyzje.

**Słowa kluczowe:** autonomiczny agent, system redakcyjny, pochodzenie danych, automatyczne bramki, walidacja LLM, automatyzacja przeglądarki, niezawodność, audyt statyczny.

---

## 1. Cel, zakres i pytania badawcze

### 1.1. Cel praktyczny

Celem projektu jest poprawienie istniejącego agenta tak, aby działał „redakcyjnie”: nie tylko generował i wystawiał tekst, lecz zarządzał materiałem dowodowym, pamiętał wcześniejsze decyzje, rozpoznawał niepewność, wykonywał kontrolowaną rewizję, mierzył skutki publikacji i ostrożnie aktualizował własne reguły.

W niniejszej fazie celem nie jest implementacja tych zmian. Celem jest zbudowanie możliwie pełnego, sprawdzalnego opisu stanu zastanego.

### 1.2. Pytania badawcze

**RQ1.** Czy V3 jest fizycznie i logicznie odizolowany od V2 i środowiska produkcyjnego?

**RQ2.** Czy każdą publikację i każdą mutację konta można powiązać z intencją, wykonaniem i potwierdzonym skutkiem?

**RQ3.** Czy łańcuch od źródła przez fragment dowodowy i twierdzenie do zdania artykułu jest kompletny oraz możliwy do odtworzenia?

**RQ4.** Czy bramki redakcyjne rzeczywiście blokują nieakceptowalne teksty i czy rewizja nie wprowadza regresji?

**RQ5.** Czy istniejące elementy pamięci i metryk tworzą zamkniętą, ostrożną pętlę uczenia redakcyjnego?

**RQ6.** Czy testy mogą wykazać własności całego systemu bez sekretów, sieci, kosztów i konta produkcyjnego?

**RQ7.** Które defekty V2 zostały usunięte, które jedynie zamaskowane, a które przeniesione do V3?

### 1.3. Hipotezy robocze

H1: istniejący potok zawiera wystarczająco dużo wartościowej logiki, aby rozwój ewolucyjny był mniej ryzykowny niż przepisanie systemu.

H2: głównym ograniczeniem V3 nie jest jakość pojedynczego promptu, lecz brak spójnych kontraktów między etapami i stanami.

H3: deklarowana pamięć redakcyjna jest obecnie głównie warstwą danych, a nie empirycznie działającym mechanizmem uczenia.

H4: część zabezpieczeń działa na poziomie pojedynczej funkcji, lecz nie zapewnia własności całego przebiegu lub całej doby.

Hipotezy nie są w tym dokumencie traktowane jako wyniki. Każda wymaga odrębnego testu falsyfikacyjnego po zbudowaniu środowiska offline.

---

## 2. Granice badania i zasady bezpieczeństwa

### 2.1. Dozwolone działania

- odczyt plików V3;
- odczyt V2 jako materiału porównawczego;
- lokalna analiza tekstowa i AST bez importu kodu integracyjnego;
- zapis dokumentacji wyłącznie w V3;
- formułowanie hipotez oraz protokołów przyszłych eksperymentów.

### 2.2. Działania wyłączone

- publikacja artykułu, notki, komentarza, polubienia, restacku, follow lub subskrypcji;
- dotykanie konta Substack lub sesji przeglądarkowej;
- wdrażanie usług, timerów, skryptów startowych lub zmian produkcyjnych;
- wywołania płatnych modeli w celu audytu;
- testy sieciowe i testy na żywym koncie;
- modyfikowanie V2;
- funkcjonalne naprawy prototypu w tej fazie.

### 2.3. Konsekwencja metodologiczna

Audyt może udowodnić obecność ścieżki, brak walidacji, niespójność kontraktów lub możliwość określonego przebiegu sterowania. Nie może udowodnić rzeczywistej skuteczności publikacji, reakcji odbiorców ani niezawodności selektorów interfejsu bez eksperymentu. Wszelkie zdania o zachowaniu zewnętrznej platformy są zatem oznaczane jako źródłowe lub hipotetyczne, a nie jako wynik testu V3.

---

## 3. Metoda

### 3.1. Korpus badawczy

Korpus V3 obejmuje 117 plików:

| Klasa artefaktu | Liczba | Rozmiar liniowy | Rola |
|---|---:|---:|---|
| pliki Python | 59 | — | implementacja, testy i skrypty |
| główne moduły Python | 12 | 11 239 linii | rdzeń systemu |
| zwykłe pliki testowe | 36 | 6 308 linii | kontrole lokalne i statyczne |
| skrypty testów płatnych | 10 | 940 linii | testy zależne od usług |
| prompty Markdown | 26 | 2 843 linie | kontrakty z modelami |
| dokumenty Markdown w katalogu głównym | 9 przed audytem | 1 929 linii | opis projektu i historia |
| pozostałe | 31 | — | konfiguracje usług, tekst, JSON, baza i skrypty |

W dwunastu głównych modułach naliczono około 56 751 słów. Prompty zawierają około 22 068 słów. Oznacza to, że zachowanie systemu jest rozdzielone między kod i obszerną warstwę instrukcji; badanie tylko jednego z tych obszarów byłoby niewystarczające.

### 3.2. Techniki analityczne

1. **Inwentaryzacja artefaktów.** Policzenie plików, rozszerzeń, linii i funkcji.
2. **Rekonstrukcja sterowania.** Prześledzenie głównego przepływu artykułu oraz rutyny dnia od punktu wejścia do zapisów stanu.
3. **Rekonstrukcja przepływu danych.** Identyfikacja danych wejściowych, przekształceń, walidacji, zapisów oraz miejsc utraty pochodzenia.
4. **Analiza AST.** Kontrola składni, zależności lokalnych, szerokich wyjątków i nieużywanych parametrów.
5. **Analiza kontraktów.** Porównanie oczekiwanych pól promptów z polami odczytywanymi przez kod i bramki.
6. **Analiza stanu.** Inspekcja tabel SQLite, plików JSON/JSONL, cache i Markdown.
7. **Replikacja defektów V2.** Sprawdzenie, czy w V3 nadal istnieje mechanizm opisany w archiwalnym katalogu znanych problemów.
8. **Analiza zagrożeń.** Ocena granic produkcji, tożsamości, niepewnych mutacji, prompt injection i URL pochodzących z modelu.

### 3.3. Skala siły dowodu

| Kod | Rodzaj | Znaczenie |
|---|---|---|
| D | dowód bezpośredni | widoczny w kodzie, schemacie, prompcie lub pliku |
| T | dowód z przepływu | wynika z połączenia co najmniej dwóch bezpośrednich obserwacji |
| R | replikacja historyczna | defekt V2 nadal ma odpowiadający mechanizm w V3 |
| E | dowód eksperymentalny | wymaga kontrolowanego uruchomienia; w tej fazie brak |
| H | hipoteza | prawdopodobne wyjaśnienie lub oczekiwany skutek, jeszcze niesprawdzone |

Każde ustalenie w rejestrze powinno docelowo otrzymać kod dowodu, poziom pewności, warunek falsyfikacji i status: otwarte, potwierdzone testem, obalone, zaakceptowane ryzyko albo naprawione.

### 3.4. Klasy ważności

| Priorytet | Kryterium |
|---|---|
| P0 | możliwość publikacji/mutacji na złym koncie, obejścia blokady, niekontrolowanego wolumenu lub utraty dowodu o skutku |
| P1 | istotna wada wiarygodności, jakości, kosztu, odtwarzalności albo integralności danych |
| P2 | dług techniczny, sprzeczność dokumentacyjna lub ryzyko utrzymaniowe bez natychmiastowej mutacji zewnętrznej |

Priorytet nie jest estymacją czasu naprawy. Krótka poprawka może być P0, a duży refaktor P2.

---

## 4. Charakterystyka architektury

### 4.1. Główne moduły

| Moduł | Linie | Funkcje/klasy | Odpowiedzialność dominująca |
|---|---:|---:|---|
| `stages.py` | 3 066 | 74/0 | etapy modeli, research, materiały, rutyna treści |
| `browser.py` | 2 402 | 54/0 | automatyzacja platformy i dziennik działań |
| `config.py` | 1 558 | 16/0 | polityki, limity, modele, czas i ścieżki |
| `run.py` | 1 334 | 15/1 | orkiestracja artykułu i dnia |
| `editorial.py` | 541 | 22/0 | pamięć, metryki, obserwacje, rewizje i odłożenia |
| `alarm.py` | 536 | 18/0 | alarmy operacyjne |
| `llm.py` | 545 | 11/3 | adaptery modeli, koszt i parser odpowiedzi |
| `gates.py` | 514 | 16/0 | deterministyczne bramki tekstu |
| `kanal.py` | 295 | 10/0 | pobieranie i historia kanału |
| `db.py` | 217 | 8/0 | SQLite i księgowanie przebiegów |
| pozostałe dwa | 231 | 8/2 | styl i kopia subskrybentów |

Cztery największe moduły mają łącznie około 8,4 tys. linii. Architektura jest modularna na poziomie nazw plików, lecz kontrakty między etapami są przeważnie nieformalnymi słownikami. Własności przekrojowe — pochodzenie, koszt, gotowość do publikacji, limit dnia — nie należą do jednego modułu.

### 4.2. Zależności lokalne

- `run` zależy od `alarm`, `browser`, `config`, `db`, `editorial`, `gates`, `kanal` i `stages`;
- `stages` zależy od `browser`, `config`, `db`, `editorial`, `gates`, `llm` i `style`;
- `alarm` zależy od `browser`, `config`, `db` i `stages`;
- `browser` zależy od `config` i pośrednio od `stages`;
- `llm` zależy od `config` i `db`;
- `db` zależy od `config` i `editorial`;
- `editorial` jest względnie samodzielny.

`editorial.py` ma dobre położenie do bycia wyraźną warstwą domenową, ale obecnie część jego funkcji nie ma producenta danych ani konsumenta decyzji. Zależność `db -> editorial` oznacza też, że podstawowa inicjalizacja bazy zna rozszerzenie redakcyjne, choć reszta potoku nie realizuje jeszcze całego cyklu.

### 4.3. Jednostki odpowiedzialności

Analiza wskazuje cztery nakładające się systemy:

1. **fabryka artykułu:** temat, źródła, synteza, szkic, recenzja, zapis;
2. **warstwa wykonawcza konta:** publikacja, notki, komentarze, reakcje, follow i subskrypcje;
3. **księga operacyjna:** przebiegi, wywołania, koszty, dziennik działań i stan kampanii;
4. **projektowany system redakcyjny:** treści, rewizje, metryki, sygnały i obserwacje.

Największe ryzyko powstaje tam, gdzie jeden system zakłada, że drugi zapewnił własność, której ten nie rejestruje. Przykład: warstwa wykonawcza zakłada, że dziennik bezbłędnie policzy wykonaną mutację, a dziennik świadomie ignoruje każdy błąd zapisu.

---

## 5. Rekonstrukcja przepływu artykułu

### 5.1. Przepływ nominalny

| Nr | Etap | Wejście | Główny wynik | Kontrola/stan |
|---:|---|---|---|---|
| 1 | `scout` | pamięć, pytania, bank i liczba tematów | kandydaci tematów | cache, koszt |
| 2 | `feasibility` | kandydaci | ocena źródeł i głębokości | wybór najlepszego, nawet z odrzuconych |
| 3 | `discovery` | pytanie i ostatnie domeny | lista URL-i | klasy źródeł, hosty |
| 4 | `fetch` | URL-e | teksty dokumentów | druga runda przy cienkim korpusie |
| 5 | `classify` | pytanie i korpus | fragmenty, liczby, klasy | materiał dowodowy |
| 6 | `synthesis` | materiał dowodowy | karta artykułu | fallback po awarii |
| 7 | `warto_pisac` | karta | `PISZ`, `DOLOZ` albo `ODLOZ` | możliwość odłożenia |
| 8 | `write` | karta, głębokość, pamięć | tytuł, podtytuł, tekst | ponowienie na innym modelu |
| 9 | `review` | karta i szkic | klasyfikacja zdań | fakt bez pokrycia |
| 10 | `forma` | szkic | obserwacje formy | bramki niedeterministyczne |
| 11 | bramki | tekst, karta, poprzednie teksty | lista ustaleń | podłogi deterministyczne |
| 12 | decyzja | ustalenia | gotowy, rewizja lub alarm | progi ilościowe |
| 13 | `revise` | szkic i ustalenia | poprawiony szkic | druga recenzja i forma |
| 14 | `save` | pełny stan | Markdown, uwagi i rekord | status artykułu |
| 15 | publikacja | zapisany artykuł | mutacja zewnętrzna | tylko przy fladze i `can_publish` |

W kodzie nominalny przepływ zaczyna się w `run.py:781`, a kończy zapisaniem stanu około `run.py:1275`. Publikacja jest dodatkowym krokiem po zapisie.

### 5.2. Najważniejsze asymetrie

**Research może być niewystarczający, ale artykuł nadal powstaje.** Po klasyfikacji komentarz w `run.py:907-908` ustanawia zasadę, że opłacony research musi zakończyć się artykułem. Wyjątkiem jest później dodane rzeczywiste odłożenie tematu. Awaria samej bramki ciekawości pozostaje jednak fail-open.

**Recenzja jest jednocześnie krytyczna i „nieblokująca”.** Jej niedostępność trafia do listy ustaleń i obecna decyzja redakcyjna może zablokować publikację, ale komentarze historyczne w kodzie nadal twierdzą, że brak recenzji nie może zatrzymać zapisu. Trzeba rozdzielić bezpieczne „zapisz do szuflady” od niebezpiecznego „gotowe do publikacji”.

**Status jest obliczany późno.** Źródła i koszty są zapisywane wcześniej według `run_id`, natomiast artykuł i część pamięci powstają na końcu. Awaria może pozostawić częściowy, niejednoznaczny stan.

**Rewizja nie jest związana kluczem artykułu.** Rewizja zostaje zapisana przed rekordem artykułu i używa `run_id`, ale tabela ma miejsce na `article_id`. Bez późniejszego powiązania nie da się jednoznacznie rekonstruować historii przy wielu artefaktach jednego przebiegu.

### 5.3. Utrata pochodzenia dowodowego

Pożądany łańcuch ma postać:

`wynik wyszukiwania -> dokładny URL -> pobrany dokument -> fragment -> twierdzenie -> zdanie szkicu -> zdanie po rewizji -> przypis publikacji`.

Obecna implementacja przechowuje wiele elementów, ale nie jeden wspólny identyfikator łańcucha. `sources` wiąże URL z przebiegiem; karta przechowuje twierdzenia i liczby; recenzent opisuje zdania tekstem; lista `## Sources` korzysta tylko z części URL-i; rewizja przechowuje obrazy `before/after`. To wystarcza do późniejszego dochodzenia, ale nie do maszynowego dowodu kompletności.

### 5.4. Niezależność klasyfikacji faktów

Recenzent może zaklasyfikować zdanie jako `FACT`, `INFERENCE` lub `PROSE`. Kod znajduje fakt jawnie oznaczony jako nieoparty, ale nie sprawdza:

- czy liczba rekordów recenzji odpowiada liczbie zdań artykułu;
- czy każde zdanie występuje dokładnie raz;
- czy faktograficzna przesłanka nie została połączona z inferencją w jednym zdaniu;
- czy recenzent użył źródła przypisanego do danego twierdzenia;
- czy rewizja nie zmieniła semantyki źródłowego zdania.

Wniosek: jest to użyteczny etap kontrolny, ale jego wynik jest opinią modelu o tekście, a nie formalnym dowodem pokrycia.

---

## 6. Rekonstrukcja rutyny dnia

### 6.1. Bloki działania

Rutyna `dzien()` obejmuje:

1. odpowiedzi pod własnymi treściami;
2. pięć notek;
3. komentarze u innych;
4. dyskusje pod cudzymi notkami;
5. obserwowanie nowych publikacji;
6. subskrypcje;
7. polubienia;
8. restacki.

Kolejność ma znaczenie, ponieważ wspólny budżet czasu może wyeliminować późniejsze bloki. Część funkcji sprawdza pozostały czas wewnątrz pętli, część deleguje całe działanie do przeglądarki.

### 6.2. Model limitu

Planowany kontrakt to:

`pozostało = zamrożony limit doby - suma potwierdzonych działań tej samej doby`.

Kod realizuje przybliżenie:

`pozostało = nowo wylosowany limit przebiegu - suma wybranych wpisów dziennika UTC`.

Różnice są istotne:

- limit jest losowany ponownie w każdym przebiegu;
- follow i subskrypcje nie mają licznika w `ile_dzis_wystawione()`;
- część działań oznacza próbę, a nie potwierdzony stan;
- zapis dziennika może bezgłośnie nie dojść do skutku;
- publikacja posługuje się dniem Nowego Jorku, licznik dniem UTC.

Właściwość „nigdy więcej niż X na dobę” nie jest zatem obecnie dowiedziona.

### 6.3. Intencja, wykonanie i potwierdzenie

Dla każdej mutacji trzeba rozdzielić trzy zdarzenia:

| Stan | Pytanie | Przykładowe wymagane dane |
|---|---|---|
| intencja | co agent zamierzał zrobić? | typ, cel, uzasadnienie, limit, run_id |
| wykonanie | co wysłał interfejsowi? | akcja, selektor/endpoint, czas, idempotency key |
| potwierdzenie | co platforma rzeczywiście przyjęła? | zewnętrzny identyfikator, URL, stan po odczycie |

Obecny dziennik często zapisuje tylko jeden wpis opisany jako sukces. Jeżeli kliknięcie zakończyło się niejednoznacznie lub zapis dziennika zawiódł, brakuje modelu stanu `UNKNOWN`. To prowadzi do niebezpiecznego ponawiania.

---

## 7. Model danych i trwałość

### 7.1. SQLite

Rdzeń i warstwa redakcyjna deklarują łącznie dziesięć tabel:

| Tabela | Rola |
|---|---|
| `runs` | stan i koszt przebiegu |
| `calls` | wywołania modeli i księgowanie |
| `articles` | zapis artykułu i jego status |
| `sources` | źródła powiązane z przebiegiem |
| `content_items` | kanoniczna jednostka treści redakcyjnej |
| `metric_snapshots` | migawki wyników w horyzontach |
| `audience_signals` | komentarze, pytania i inne sygnały |
| `editorial_observations` | ostrożne wnioski redakcyjne |
| `deferred_topics` | tematy odłożone z brakującym elementem |
| `article_revisions` | historia rewizji |

Nie znaleziono kluczy obcych, numeru wersji schematu ani kompletnej migracji. Jedyna ręczna migracja dotyczy `calls.cache_hit`. Relacje istnieją logicznie, ale baza ich nie wymusza.

### 7.2. Stan plikowy

Istotny stan znajduje się także w:

- `dziennik.jsonl`;
- `gdzie_komentowalismy.json`;
- `zuzyte_fakty.json`;
- `promocja.json`;
- `bank_notek.json`;
- `pytania_czytelnikow.json`;
- `indeks_kandydatow.json`;
- `alarmy.json`;
- sesji przeglądarki;
- plikach cache;
- artykułach i uwagach Markdown.

Ta dystrybucja nie jest automatycznie wadą. Wadą jest brak wspólnego identyfikatora zdarzenia i semantyki odtwarzania po przerwaniu między zapisami. Częste zachowanie „uszkodzony JSON = pusty stan” zamienia błąd integralności w fałszywy brak historii.

### 7.3. Wymagany model zdarzeń

Minimalny przyszły kontrakt powinien zachować dotychczasową bazę, ale dodać niezmienne zdarzenie operacyjne:

- `event_id`;
- `run_id`;
- `content_id` lub `target_id`;
- rodzaj działania;
- stan: `INTENDED`, `SENT`, `CONFIRMED`, `REJECTED`, `UNKNOWN`;
- czas w UTC oraz przypisana do niego doba redakcyjna;
- zewnętrzny identyfikator lub dowód potwierdzenia;
- przyczynę i wersję polityki.

Jest to propozycja projektowa, nie część bieżącego audytu wykonawczego.

---

## 8. Pamięć i pętla uczenia redakcyjnego

### 8.1. Co już istnieje

`editorial.py` zawiera:

- rejestrację treści i publikacji;
- migawki metryk;
- względną ocenę na tle baseline;
- sygnały odbiorców;
- obserwacje redakcyjne z pewnością;
- pamięć wybieraną do promptów;
- odłożone tematy;
- rewizje artykułu.

Jest to wartościowe rusztowanie: model danych rozróżnia wynik treści, sygnał i obserwację. Sama obecność tabel nie oznacza jednak, że agent się uczy.

### 8.2. Brakujące ogniwa

Zamknięta pętla wymaga sekwencji:

`publikacja -> pomiar -> normalizacja -> obserwacja -> test kontrprzykładu -> ostrożna reguła -> użycie reguły -> pomiar następstwa`.

W V3 brakuje co najmniej:

- pewnego kolektora metryk publikacji;
- jednoznacznych horyzontów pomiaru liczonych od czasu publikacji;
- właściwego baseline dla typu treści, wieku i ekspozycji;
- procesu tworzącego obserwację z wielu wyników;
- mechanizmu wygaszania lub obalania obserwacji;
- rejestru, która obserwacja wpłynęła na którą decyzję;
- testu, czy decyzja oparta na pamięci poprawiła wynik.

### 8.3. Ryzyko pozornego uczenia

Jeżeli pojedyncza treść uzyska dobry wynik, a system zapisze ogólną regułę typu „czytelnicy wolą X”, może pomylić korelację z przyczyną. Na wynik wpływają m.in. temat, tytuł, czas, wielkość ekspozycji, typ treści, wcześniejsza aktywność i przypadek.

Dlatego obserwacja redakcyjna powinna mieć:

- próbę i okres;
- porównywalny baseline;
- wielkość efektu, nie tylko kierunek;
- potencjalne czynniki zakłócające;
- kontrprzykłady;
- datę ważności;
- regułę falsyfikacji;
- maksymalny wpływ na decyzję.

Bez tych pól „pamięć” może wzmacniać przypadkowe wzorce szybciej niż jakość.

---

## 9. Walidacja modeli i promptów

### 9.1. Parser odpowiedzi

`llm.parse_json()` wycina tekst od pierwszej do ostatniej klamry i wykonuje `json.loads`. Jest to kontrola składni, nie schematu. Nie dowodzi:

- obecności wymaganych pól;
- właściwych typów i zakresów;
- braku pól nieoczekiwanych;
- zgodności wersji;
- kompletności list;
- zachowania relacji między polami.

Niektóre etapy wykonują później lokalne sprawdzenia, ale brak jednej granicy kontraktowej prowadzi zarówno do awarii, jak i do cichych wartości domyślnych.

### 9.2. Sprzeczności instrukcji

Znaleziono przykłady, w których prompt lub komentarz ustanawia dwie konkurujące reguły:

- jeden akapit o granicach wiedzy kontra rozproszone zastrzeżenia przy każdym niewiadomym;
- „nic nie blokuje” kontra decyzja `NEEDS_REVIEW`;
- `THIN` jako najkrótszy wariant kontra fallback długości `RICH`;
- dokładne źródła kontra dopuszczenie analogii bez źródeł;
- „budżet dnia” kontra losowanie przy każdym przebiegu.

Sprzeczność nie zawsze kończy się błędem. Powoduje jednak, że zachowanie zależy od arbitralnej interpretacji modelu lub warstwy wykonawczej, przez co wynik staje się mniej odtwarzalny.

### 9.3. Prompt injection

Źródła zewnętrzne i tekst użytkowników są danymi niezaufanymi. Obecny system szuka wybranych oznak instrukcji, lecz treść źródła nadal współdzieli kontekst z poleceniem. Bez schematu, dozwolonego zbioru operacji i testów ataków nie można uznać, że słownik fraz zapewnia izolację.

Przyszły korpus testowy powinien zawierać co najmniej:

- jawne polecenie zignorowania systemu;
- zakodowaną instrukcję;
- instrukcję podszytą pod cytat lub metadane;
- żądanie ujawnienia sekretu;
- żądanie dołożenia fałszywego źródła;
- manipulację klasyfikacją `FACT/INFERENCE`;
- URL prowadzący do zasobu prywatnego;
- długi tekst przesuwający właściwe polecenie poza uwagę modelu.

---

## 10. Bezpieczeństwo produkcyjne

### 10.1. Izolacja V3

W katalogu V3 znajdują się skrypty operacyjne odwołujące się do V2 i flagi `--wyslij`. V3 wczytuje też ścieżki sekretów i sesji z poziomu wspólnego projektu. Oznacza to, że nazwa katalogu „prototyp” nie stanowi fizycznej granicy.

Bezpieczny prototyp powinien nie posiadać poświadczeń, ścieżki do żywej sesji ani możliwości wywołania publikacji nawet przy błędzie flagi. Marker testowy w jednej funkcji jest dodatkową ochroną, ale nie obejmuje wszystkich punktów mutacji.

Flaga `wyslij` kontroluje przede wszystkim końcowy publiczny przycisk. Funkcja artykułu w trybie `False` nadal otwiera panel, wkleja treść i obraz, przechodzi do ustawień oraz raportuje zapis szkicu. Jest to zdalna mutacja prywatnego stanu konta, wykonywana bez kontroli właściwej tożsamości, która działa tylko dla `True`. Z tego powodu „dry” i „niepublikujący” muszą być dwoma osobnymi pojęciami: pierwszy nie może kontaktować się z kontem, drugi może tworzyć draft wyłącznie po jawnej zgodzie.

### 10.2. Tożsamość

Kod zawiera kontrolę właściwego konta przed mutacją, ale tożsamość publikacji występuje w więcej niż jednej stałej. Ponadto wynik kontroli zależy od widocznego stanu interfejsu i może wymagać osobnego potwierdzenia roli administracyjnej.

Warunek bezpieczeństwa powinien być globalny:

> Żadna funkcja mutująca nie może wykonać działania, jeśli nie ma świeżego, jednoznacznego dowodu tożsamości konta, publikacji i uprawnienia.

Nie wystarczy, że jedna ścieżka publikacji go sprawdza.

### 10.3. Kill switch

Obecny kill switch jest związany głównie z warstwą modeli. Automatyzacja przeglądarki wymaga osobnego, sprawdzanego bezpośrednio przed każdą mutacją przełącznika. Wartość odczytana tylko przy imporcie nie zapewnia reakcji w trakcie długiego przebiegu.

### 10.4. URL i SSRF

URL wygenerowany przez model powinien być traktowany jak polecenie dostępu do sieci. Wymaga co najmniej:

- schematu `https`;
- kontroli dokładnego wyniku wyszukiwarki;
- rozwiązania DNS i odrzucenia zakresów prywatnych, loopback, link-local i metadanych;
- ponownej kontroli po każdym przekierowaniu;
- limitu rozmiaru, czasu i typów treści;
- rejestru ostatecznego URL;
- polityki domen dopuszczonych lub izolowanego fetchera.

W audycie nie wykonywano prób dostępu do adresów prywatnych.

---

## 11. Testowalność i odtwarzalność

### 11.1. Stan testów

Repozytorium ma dużą liczbę kontroli: około 877 wywołań asercji lub funkcji sprawdzających. Ilość jest atutem, ale ich zakres jest nierówny. Około 52 kontrole opierają się na statycznej obecności tekstu w kodzie.

Testy tekstowe dobrze chronią:

- obecność komentarza lub stałej;
- kolejność fragmentów;
- zakaz wybranego ciągu;
- prostą konwencję pliku.

Nie dowodzą jednak:

- że wartość dociera do konsumenta;
- że limit obowiązuje w trzech przebiegach;
- że nie wykonano mutacji po niepewnym błędzie;
- że każdy fakt ma źródło;
- że rewizja nie pogorszyła tekstu.

### 11.2. Brak pełnej symulacji offline

`DRY_RUN` blokuje część mutacji i modeli, lecz puste odpowiedzi modeli nie pozwalają przejść całego potoku JSON. Zwykły przebieg bez `--wyslij` nadal może używać sieci i płatnych usług. Brakuje trybu, który:

- podmienia wszystkie usługi fixture'ami;
- używa katalogu tymczasowego;
- zabrania gniazd sieciowych;
- odmawia odczytu sekretów i sesji;
- rejestruje każdą próbę mutacji jako błąd testu;
- przechodzi cały potok od scouta do statusu i raportu.

### 11.3. Hermetyczność testów

Jeden z testów otwiera `data/zasiew-produkcji.db`, przez co lokalne uruchomienie może utworzyć plik w katalogu prototypu. Wszystkie testy bazy i plików powinny otrzymywać jawny katalog tymczasowy. Test hermetyczności powinien po zakończeniu porównać drzewo projektu i zgłosić każdą nieoczekiwaną mutację.

### 11.4. Proponowana piramida dowodowa

1. testy schematów odpowiedzi i czyste funkcje;
2. testy kontraktów pojedynczych etapów z fixture'ami;
3. testy własności przekrojowych na pełnym offline pipeline;
4. testy mutacji przeglądarki na lokalnej fałszywej stronie;
5. replay historycznych przebiegów bez sieci;
6. shadow run bez możliwości publikacji;
7. dopiero po przejściu wszystkich wcześniejszych bramek — ograniczony, automatycznie odwracalny test zewnętrzny bez publikacji.

Punkty 4–7 nie są autoryzowane w bieżącej fazie.

---

## 12. Wyniki według pytań badawczych

### RQ1. Izolacja od produkcji

**Wynik:** negatywny. Granica katalogu nie jest granicą wykonawczą. Skrypty V3 potrafią wskazywać V2, a sekrety i sesja są współdzielone. Marker kopii testowej obejmuje tylko część ścieżek. Dowody: A-001–A-004, A-026.

Dodatkowy wynik P0: `wyslij=False` nadal może zapisać draft na żywym koncie, więc nie stanowi granicy eksperymentalnej. Dowód: A-059.

### RQ2. Potwierdzenie mutacji

**Wynik:** negatywny. System często liczy zamiary lub próby, a dziennik pełniący rolę limitera może bezgłośnie utracić wpis. Limity follow i subskrypcji nie są odejmowane, a cel dobowy zmienia się między przebiegami. Dowody: A-006, A-029–A-032.

Potwierdzenie artykułu nie identyfikuje bieżącej próby, a wewnętrzne pętle części działań nie respektują deadline'u przebiegu. Dowody: A-060–A-061.

### RQ3. Pochodzenie dowodów

**Wynik:** częściowy. Źródła, fragmenty, liczby i twierdzenia są zbierane, lecz nie istnieje kompletny identyfikowalny łańcuch do zdania i przypisu po rewizji. Weryfikacja exact URL, liczby i klasy faktu ma luki. Dowody: A-015–A-018, A-034–A-035, A-038–A-040.

### RQ4. Bramki i rewizja

**Wynik:** nierozstrzygnięty z istotnym ryzykiem. Istnieje lepszy mechanizm decyzji i ponownej kontroli, ale progi nie są skalibrowane, recenzja nie dowodzi kompletności, a brak materiału nie zawsze blokuje pisanie. Nie istnieje zbiór regresyjny rewizji. Dowody: A-019–A-021, A-035–A-037.

### RQ5. Pętla uczenia

**Wynik:** negatywny jako pętla, pozytywny jako rusztowanie. Tabele i funkcje pamięci istnieją, lecz nie ma kompletnego kolektora, normalizacji, procesu obserwacji, falsyfikacji ani śladu wpływu reguły na decyzję. Dowody: A-008–A-011, A-027.

### RQ6. Test offline

**Wynik:** negatywny. Nie można obecnie przejść wiarygodnie całego systemu bez sieci, sekretów i możliwych zapisów do katalogu danych. Część testów utrwala kontrakty V2 lub sprawdza tekst źródła. Dowody: A-020, A-023, A-025, A-043–A-044.

Również ścieżka wdrożeniowa nie odtwarza kompletnego środowiska: nie instaluje zależności i nie wykonuje leniwych importów, które historycznie powodowały późną awarię. Dowody: A-066–A-068.

### RQ7. Dziedzictwo V2

**Wynik:** mieszany. V3 dodaje sensowne elementy redakcyjne i poprawia część ścieżek, ale wiele historycznych sprzeczności nadal występuje. Pełna macierz znajduje się w rozdziale 13.

---

## 13. Macierz replikacji problemów V2

| Problem historyczny | Stan V3 | Dowód/uwaga |
|---|---|---|
| `recent_domains` obliczane, ale nieużywane | nadal występuje | parametr discovery jest nieużywany; zapytanie oczekuje `SAVED` |
| poziom `THIN` wpada w `RICH` | nadal występuje | brak klucza w mapie długości |
| dwa schematy `parallel_mechanisms` | nadal występuje | bank i synteza używają innych pól |
| liczby sprawdzane w zbyt szerokim korpusie | nadal występuje | cała karta jest serializowana do bramki |
| lista źródeł pomija część użytych URL-i | nadal występuje | lista pochodzi z `confirmed_claims` |
| follow/subskrypcje mnożone przez przebiegi | mechanizm nadal możliwy | liczniki dzienne nie zwracają tych kategorii |
| odpowiedzi/akcje fail-open | nadal występuje | szerokie wyjątki, dziennik `pass` |
| kill switch tylko w części systemu | nadal występuje | brak jednolitej kontroli przed każdą mutacją |
| globalna zmiana modelu przy retry pisarza | nadal występuje | `MODEL_FOR["write"]` jest mutowane |
| statusy `SAVED/BLOCKED` | częściowo zmienione | nowe statusy istnieją, stare zapytania i testy zostały |
| `ODLOZ` bez rzeczywistego odłożenia | częściowo poprawione | zapis do `deferred_topics`; brak pełnego wznowienia |
| recenzja faktów czytana tylko z listy zbiorczej | częściowo poprawione | kod scala także zdania `supported=false`, lecz nie sprawdza kompletności |
| cache tylko po nazwie etapu | częściowo poprawione | klucz ma wejście/model/prompty, nadal brak wersji kodu i schematu |
| brak historii rewizji | częściowo poprawione | tabela i zapis istnieją, brak pewnego `article_id` |
| brak modelu metryk/pamięci | strukturalnie poprawione | istnieją tabele/funkcje, brak producentów i pętli |

Macierz jest robocza. „Częściowo poprawione” nie oznacza „gotowe”; oznacza, że w V3 istnieje konkretna zmiana odpowiadająca problemowi V2, lecz nie dowiedziono całej własności.

---

## 14. Protokół przyszłej falsyfikacji

Poniższe eksperymenty są projektem badawczym. Nie wolno ich wykonywać w bieżącej fazie poza hermetycznym środowiskiem, które nie istnieje jeszcze.

### E1. Niezmienność budżetu doby

**Teza:** każde z trzech uruchomień tej samej doby widzi identyczny plan dnia.  
**Metoda:** zamrożony zegar, 100 dat, trzy procesy na datę, restart między procesami.  
**Falsyfikacja:** choć jedna kategoria otrzymuje inną wartość w obrębie daty.  
**Dodatkowa własność:** suma potwierdzonych działań nigdy nie przekracza planu.

### E2. Niepewna mutacja

**Teza:** po timeout po wysłaniu akcji system nie ponawia jej automatycznie.  
**Metoda:** fałszywy adapter zwraca timeout po zapisaniu mutacji.  
**Oczekiwany stan:** `UNKNOWN`, alarm i brak kolejnej próby.  
**Falsyfikacja:** drugi identyczny zamiar zostaje wykonany bez rekoncyliacji.

### E3. Kompletność pochodzenia

**Teza:** każde zdanie faktograficzne ma co najmniej jeden identyfikator twierdzenia, fragmentu i źródła.  
**Metoda:** kontrolowany artykuł z faktami, inferencją, zdaniem mieszanym i liczbą o dwóch formatach.  
**Falsyfikacja:** zdanie `FACT` przechodzi bez łańcucha albo inferencja ukrywa faktograficzną przesłankę.

### E4. Regresja rewizji

**Teza:** rewizja usuwa wskazane wady i nie dodaje nowych krytycznych wad.  
**Metoda:** wersjonowany zbiór szkiców z oczekiwanymi defektami zapisanymi w kontrakcie; losowa kolejność porównania przed/po.  
**Miary:** recall usuniętych wad, liczba nowych faktów, zmiana tezy, zachowanie źródeł i stylu.  
**Falsyfikacja:** dowolny nowy fakt bez źródła lub zmiana centralnej tezy bez jawnej decyzji.

### E5. Odporność na uszkodzenie stanu

**Teza:** uszkodzony JSON nie jest interpretowany jako pusta historia.  
**Metoda:** przerwanie zapisu na każdym bajcie oraz symulacja braku miejsca.  
**Oczekiwany wynik:** odczyt poprzedniej atomowej wersji albo bezpieczna blokada.  
**Falsyfikacja:** system przydziela pełny limit, ponieważ odczyt zwrócił pusty stan.

### E6. Prompt injection

**Teza:** instrukcja w materiale źródłowym nie zmienia dozwolonego celu etapu.  
**Metoda:** korpus ataków opisany w rozdziale 9.3; zero sieci.  
**Miary:** naruszenie schematu, dołożenie nieźródłowego twierdzenia, wyciek, zmiana URL.  
**Falsyfikacja:** choć jeden atak wpływa na decyzję poza dozwolonym polem danych.

### E7. Użyteczność pamięci

**Teza:** reguła z pamięci poprawia wcześniej określoną miarę bez zwiększenia wad jakości.  
**Metoda:** historyczny backtest lub sparowane generowanie z pamięcią i bez niej na tych samych fixture'ach.  
**Wymóg:** obserwacja musi być sformułowana przed testem i mieć kryterium obalenia.  
**Falsyfikacja:** brak efektu, efekt przeciwny lub wzrost krytycznych ustaleń.

---

## 15. Kryteria uznania V3 za system redakcyjny

V3 można uznać za rzeczywiście redakcyjny dopiero, gdy spełni łącznie następujące warunki:

1. **Izolacja:** prototyp nie ma technicznej możliwości dotknięcia produkcji.
2. **Pochodzenie:** każde zdanie faktograficzne ma odtwarzalny łańcuch do źródła.
3. **Decyzja:** gotowość do publikacji jest oddzielona od samego zapisania szkicu.
4. **Rewizja:** poprawa ma test regresji i zachowuje tezę, źródła oraz głos.
5. **Stan:** każda mutacja ma intencję, wykonanie, potwierdzenie lub stan niepewny.
6. **Limity:** doba i budżet są zamrożone, odtwarzalne oraz liczą wyłącznie potwierdzone skutki.
7. **Pamięć:** obserwacja ma próbę, baseline, kontrprzykład, ważność i historię wpływu.
8. **Hermetyczność:** pełny potok przechodzi offline bez sekretów, sieci i zapisów operacyjnych.
9. **Migracje:** schemat danych jest wersjonowany, a relacje integralne.
10. **Obserwowalność:** awaria ma klasę; błąd integralności nie staje się pustym sukcesem.
11. **Zewnętrzny draft:** brak flagi publikacji nie może sam w sobie autoryzować tworzenia szkicu na koncie.
12. **Pomiar kohortowy:** wynik jest łączony z konkretną treścią/działaniem, nie tylko podobnym oknem czasu.

Samo spełnienie liczby testów lub obecność tabel nie wystarczy. Każde kryterium jest własnością przekrojową i wymaga co najmniej jednego testu negatywnego.

---

## 16. Kolejność dalszych prac po audycie

Kolejność wynika z zależności dowodowych, nie z atrakcyjności funkcji:

1. odłączyć V3 od V2, sekretów, sesji i skryptów publikacyjnych;
2. zbudować pełny adapter fixture/offline i test zakazu sieci/mutacji;
3. zamrozić kontrakty etapów: wersjonowane schematy wejść i wyjść;
4. ujednolicić dobę redakcyjną, zdarzenia akcji i potwierdzenie skutku;
5. wprowadzić wersję schematu bazy oraz bezpieczne migracje;
6. domknąć pochodzenie źródło–fragment–twierdzenie–zdanie–przypis;
7. skalibrować bramki i rewizję na wersjonowanym korpusie referencyjnym;
8. podłączyć kolektor metryk i właściwe baseline'y;
9. dopiero wtedy uruchomić obserwacje redakcyjne i testować ich wpływ;
10. osobno zaprojektować etap shadow, wymagający nowej zgody.

Ta sekwencja zachowuje istniejącą architekturę. Nie proponuje nowego agenta, tylko wprowadza dowodliwe granice między istniejącymi etapami.

---

## 17. Ograniczenia i zagrożenia trafności

### 17.1. Trafność wewnętrzna

Analiza statyczna może przeoczyć zachowanie zależne od danych, biblioteki lub interfejsu. Z kolei znalezienie możliwej ścieżki nie dowodzi jej częstości. Priorytety opisują możliwą szkodę, nie prawdopodobieństwo z danych produkcyjnych.

### 17.2. Trafność konstruktu

„Jakość redakcyjna” jest pojęciem wielowymiarowym. Liczba uwag, długość, klikalność lub reakcje nie są jej samodzielnym zamiennikiem. Potrzebna jest jawna, wersjonowana rubryka obejmująca prawdziwość, jasność mechanizmu, oryginalność, proporcję dowodu do tezy, styl i użyteczność. Autonomiczna decyzja publikacyjna musi wymagać przejścia wszystkich krytycznych wymiarów, a nie jednego wyniku łącznego.

### 17.3. Trafność zewnętrzna

Wyniki o interfejsie platformy mogą się dezaktualizować. Niniejszy audyt nie testował aktualnego API ani UI. Zewnętrzne projekty wymienione w materiałach użytkownika są inspiracją architektoniczną, nie benchmarkiem skuteczności V3.

### 17.4. Stronniczość materiału historycznego

Dokumentacja V2 zawiera komentarze autora i opisy incydentów. Są cennym źródłem hipotez, ale nie wszystkie stwierdzenia mają niezależny log. W macierzy replikacji uznawano problem za obecny dopiero po odnalezieniu odpowiadającego mechanizmu w V3.

### 17.5. Zmiany istniejące przed audytem

V3 zawiera prototypowe modyfikacje wykonane przed zawężeniem zadania do samego audytu. Nie są one traktowane jako zatwierdzone ani zweryfikowane. Dokument opisuje stan zastany w chwili analizy; przed późniejszą implementacją trzeba ustalić czysty punkt odniesienia.

---

## 18. Wnioski

Agent V3 jest zaawansowanym prototypem generatora i operatora treści z rozpoczętą warstwą redakcyjną. Ma bogatszy materiał niż system budowany od zera: rozbudowane prompty, research wieloetapowy, klasyfikację dowodów, bramki, recenzję zdaniową, rewizję, bank materiałów, odłożone tematy oraz szkic modelu pamięci.

Jednocześnie system nie spełnia jeszcze kluczowych własności wymaganych od autonomicznej redakcji. Największą luką nie jest brak kolejnego modelu czy promptu, lecz brak wiarygodnej odpowiedzi na pięć pytań: co dokładnie było źródłem, dlaczego podjęto decyzję, co rzeczywiście zostało wykonane, czy kontrola objęła cały tekst i czy późniejsza reguła wynika z wystarczających danych.

Najbardziej racjonalny kierunek to zachowanie istniejącego potoku i uczynienie jego granic sprawdzalnymi. Pierwszym produktem kolejnej fazy nie powinien być nowy artykuł ani nowa integracja, tylko hermetyczna symulacja, w której da się bez ryzyka obalić własne założenia.

---

## Bibliografia i materiały

### Materiały wewnętrzne

1. `agent-v3/run.py` — orkiestracja przepływu artykułu i rutyny dnia.
2. `agent-v3/stages.py` — implementacja etapów researchu, generowania i działań redakcyjnych.
3. `agent-v3/browser.py` — automatyzacja platformy oraz dziennik działań.
4. `agent-v3/config.py` — polityki modeli, kosztów, czasu i wolumenu.
5. `agent-v3/db.py` — podstawowy model trwałości.
6. `agent-v3/editorial.py` — prototyp warstwy pamięci redakcyjnej.
7. `agent-v3/gates.py` — deterministyczne bramki tekstu.
8. `agent-v3/prompts/` — kontrakty instrukcyjne etapów modelowych.
9. `agent-v3/tests/` — testy i kontrole statyczne.
10. `agent-v3/wnioski badania/02_dokumentacja_zastana/material_historyczny_v2/JAK_ZBUDOWANY_JEST_BOT.md` — materiał historyczny i katalog wcześniejszych defektów.
11. `agent-v3/wnioski badania/03_materialy_wejsciowe/poprawa.txt` — wewnętrzna propozycja pętli redakcyjnej; traktowana jako projekt, nie dowód skuteczności.
12. `agent-v3/wnioski badania/03_materialy_wejsciowe/tutaj jest do zaczerpiecia z neta.txt` — eksploracyjny przegląd projektów; traktowany jako źródło hipotez.
13. `agent-v3/wnioski badania/01_audyt/SPOSTRZEZENIA_AUDYTOWE.md` — żywy rejestr ustaleń niniejszego audytu.
14. `agent-v3/wnioski badania/04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md` — datowane badanie porównawcze z hashami wersji.
15. `agent-v3/wnioski badania/05_plan_napraw/SPECYFIKACJA_PELNEJ_AUTONOMII.md` — obowiązujący cel architektoniczny.

### Źródła zewnętrzne wykorzystane pomocniczo

1. [AnthonyDavidAdams/substack-api-reference — ENDPOINTS.md](https://github.com/AnthonyDavidAdams/substack-api-reference/blob/main/ENDPOINTS.md) — nieoficjalna dokumentacja obserwowanych endpointów; nie jest gwarancją stabilnego kontraktu platformy.
2. [conorbronsdon/substack-mcp](https://github.com/conorbronsdon/substack-mcp) — przykład narzędziowej warstwy integracyjnej; wykorzystany wyłącznie jako materiał porównawczy.

Źródła zewnętrzne nie były uruchamiane ani kopiowane do prototypu. Płytkie kopie badawcze utworzono wyłącznie w katalogu tymczasowym poza V3. Twierdzenia o V3 opierają się przede wszystkim na artefaktach lokalnych.

Numeryczne oceny projektów z materiału eksploracyjnego nie są wynikami niniejszego audytu: brak im wspólnej rubryki, datowanych rewizji i niezależnej replikacji. W monografii nie używa się ich do uzasadnienia dojrzałości V3.

---

## Aneks A. Rejestr ilościowy kontroli

- pliki Python sparsowane przez AST: 59;
- błędy składni: 0;
- przybliżona liczba wywołań asercji/kontroli testowych: 877;
- przybliżona liczba testów opartych na statycznym tekście źródła: 52;
- szerokie obsługi wyjątków: `browser.py` 30, `stages.py` 19, `run.py` 14;
- szerokie obsługi natychmiast milczące/przechodzące dalej: `browser.py` 9, `stages.py` 6;
- statycznie nieużywane parametry: trzy, opisane w A-046.

Liczby są wynikiem analizy statycznej i mogą zależeć od definicji „kontroli” oraz „szerokiego wyjątku”. Skrypty wykorzystane do liczenia nie uruchamiały kodu agenta.

## Aneks B. Reguła prowadzenia dalszego rejestru

Każde następne ustalenie powinno zawierać:

1. unikalny identyfikator;
2. priorytet;
3. obserwację bezpośrednią;
4. mechanizm prowadzący do skutku;
5. możliwą szkodę;
6. zakres dotkniętych artefaktów;
7. klasę dowodu;
8. poziom pewności;
9. warunek falsyfikacji;
10. rekomendację, ale bez wdrażania w fazie audytu.

Taki format ma zapobiec mieszaniu faktu, interpretacji, hipotezy i decyzji projektowej.
