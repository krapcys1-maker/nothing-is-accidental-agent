# E-019 — ręczny audyt Scouta i wybór jednej drogi artykułu

**Data:** 2026-08-21  
**Status:** `SCOUT_RAW_REPLAY_PASS; FEASIBILITY_LIVE_PASS; TWO_MANUAL_FAILS; FINAL_SELECTION_PASS_AFTER_OFFLINE_FIX; DISCOVERY_NOT_YET_RUN`  
**Zakres:** Scout E-018, feasibility oraz deterministyczny selektor; bez researchu, pisarza i Notes  
**Substack:** zero sesji, odczytu konta, szkicu, zapisu, publikacji i innych mutacji

## 1. Pytanie badawcze i rygor zaliczenia

Czy portfel live Scouta E-018 prowadzi w normalnym V3 do jednego tematu, który:

1. nie jest ciekawostką możliwą do wyczerpania w trzech zdaniach;
2. ma konkretną drogę artykułową zamiast sześciu tematów zmieszanych w omnibus;
3. ma publicznie osiągalne źródła pierwotne;
4. ma drugi akt: inną konsekwencję, konflikt albo równoległy mechanizm;
5. przechodzi ręczną kontrolę treści, nie tylko kontrakt JSON?

Status `PASS` wymagał spełnienia wszystkich pięciu punktów. Zielony parser albo
samodeklaracja modelu `RICH` nie wystarczały. Każda wada zatrzymywała przejście
do następnego segmentu.

## 2. Materiał wejściowy

Nie wygenerowano ponownie Scouta. Użyto dokładnego, niezmienionego raw response
E-018 i przeliczono go przez aktualny kod:

| Materiał | SHA-256 |
|---|---|
| pełny capture Scouta E-018 | `841BCE55FF7571A2D2E6A4D5AF6CE0390A826F5A37EAA711CBA3151D8196C395` |
| raw response wewnątrz capture | `7240511AD38593B9D40C785565836842FDF40AD020BB1126494F26EAC1B876F4` |
| feasibility F1 raw response | `4D2340AA37DF63572EF062374046C2A0318F928373C6627035FE73C7A9AE0150` |
| feasibility F2 raw response | `949BACE39965BD85D5FE9A650FEA29B5540EE764740148457A954DA1C11075B5` |

Pełne system prompty, user prompty i odpowiedzi są lokalnie w:

- `.live-experiments/E-018-scout-universe-live/model-captures.json`;
- `.live-experiments/E-019-scout-manual-audit/model-captures.json`;
- `.live-experiments/E-019b-scout-route-depth-live/model-captures.json`.

Pliki są ignorowane przez Git, nie zawierają kluczy API i pozwalają odtworzyć
każdą ocenę bez przepisywania odpowiedzi.

## 3. Co naprawdę wymyślił Scout

Pełne osie, napięcia, gałęzie, fatalne słabości i rodziny dowodu są w raporcie
E-018. Poniżej pozostaje komplet sześciu uniwersów i 24 dróg, które faktycznie
poszły do feasibility.

| Uniwersum | Cztery konkretne drogi artykułowe |
|---|---|
| **Suspicion as Default** | chargebacki i domniemana wina sprzedawcy; koszt prior authorization w dniach i pracy; niewidoczne risk scores kontroli podatkowych; rytuały podejrzenia w hotelu i na lotnisku |
| **The Uninsurable World** | wyjście ubezpieczyciela przed katastrofą; bilans insurer of last resort; rynek kredytu bez standardowego ubezpieczenia; granice mutual aid |
| **The Afterlife of Abandoned Infrastructure** | osierocony szyb naftowy; wejście i mapowanie starej kopalni; przyszłość nieczynnego korytarza kolejowego; porzucone oprogramowanie używane przez łańcuch dostaw |
| **The Last Human in the Loop** | zdalny operator pojazdu autonomicznego; człowiek uwalniający fałszywie zablokowaną płatność; ludzcy skrybowie za „automatyczną” dokumentacją AI; kolejki wyjątków moderacji |
| **The Quality of Recycled Materials** | cena i zanieczyszczenie beli papieru; kaskada po zmianie progu czystości importu; nieznana chemia zużytych baterii; kto zna zawartość beli plastiku |
| **The Standard Human Body** | męski i ciężarny crash-test dummy; dawka leku a masa ciała; PPE dla wąskiego zakresu ciał; globalny eksport założeń norm ergonomicznych |

Odrzucone zalążki również pozostały widoczne: identyczne tablice rejestracyjne,
boil-water notice, keycard przy telefonie, świat bez gotówki i lotniskowe
lost-and-found. Odrzucenie boil-water notice jest pożądanym kontrprzykładem:
to materiał na krótką Note albo explainer, nie pole artykułowe.

## 4. Wady ujawnione przez dokładny replay

### 4.1. Ranking tracił pierwsze, drugie i trzecie miejsce

Kod traktował listy `largest_article_universe`, `most_compelling` i pozostałe
jak zbiory. Pierwszy, drugi i trzeci element dostawały ten sam przyrost. Na raw
E-018 dawało to remis po +5 dla `Suspicion as Default` i `The Uninsurable
World`. Po zachowaniu kolejności 3/2/1 aktualny wynik to:

| Miejsce | Uniwersum | Wynik rankingu Scouta |
|---:|---|---:|
| 1 | Suspicion as Default | 13 |
| 2 | The Uninsurable World | 8 |
| 3 | The Afterlife of Abandoned Infrastructure | 5 |
| 4 | The Last Human in the Loop | -2 |
| 5 | The Quality of Recycled Materials | -3 |
| 6 | The Standard Human Body | -3 |

### 4.2. `obvious_coverage` było błędnie liczone jako nasycenie

Kontrakt wymagał czterech przykładów oczywistego pokrycia właśnie po to, aby
model ich unikał. Kod liczył je jednak jak cztery dowody nasycenia i oznaczał
wszystkie sześć nowych uniwersów `nasycony=true`. Pole nie mierzyło tego, co
twierdziła nazwa. Dla nowego kontraktu `obvious_coverage` nie ustawia już
nasycenia.

### 4.3. Downstream ignorował wybraną drogę

Feasibility dostawało wyłącznie nazwę i centralne pytanie uniwersum. Research
otrzymałby następnie pytanie parasolowe, a nie jedną z czterech dróg. Była to
bezpośrednia droga do szerokiego, płaskiego tekstu „o wszystkim”. Aktualny
kontrakt wymaga oceny wszystkich dróg oraz `selected_route_index`; brak wyboru
kończy segment błędem.

## 5. Live feasibility F1 — techniczny PASS, ręczny FAIL

Jeden normalnie routowany `deepseek-v4-flash`, zero retry:

| Metryka | Wynik |
|---|---:|
| tokeny wejścia | 4 702 |
| tokeny wyjścia | 29 646 |
| czas | 279,531 s |
| koszt KNOWN | 0,020601 USD |
| web search/fetch/Substack | 0/0/0 |
| kontrakt | PASS |

F1 wybrał `Suspicion as Default` i drogę o prior authorization. Ręczny audyt
potwierdził, że rodziny CMS, OIG/GAO, ankiet lekarzy i polityk payerów istnieją.
Wynik nie zawierał jednak głębokości wybranej drogi. Dziedziczył `RICH` z
całego uniwersum, mimo że jedna droga mogła być materiałem tylko na krótki
tekst. Status treści: `FAIL`; nie uruchomiono discovery.

## 6. Negatywny test cache — koszt 0 USD

Zmiana wyłącznie promptu feasibility unieważniła także cache Scouta, ponieważ
stara tożsamość cache używała jednego wspólnego hasha wszystkich promptów.
Uprząż segmentowa zatrzymała nieuprawniony drugi Scout przed dispatch. Wynik:

- zero wywołań modelu i zero kosztu;
- wada cross-stage cache odtworzona live;
- cache ma teraz fingerprint promptu i kontraktu osobno dla każdego etapu;
- test dowodzi, że zmiana feasibility nie unieważnia płatnego Scouta.

## 7. Live feasibility F2 — wszystkie 24 drogi

Kontrakt `feasibility@3` wymaga osobnego `RICH/SINGLE/THIN`, drugiego aktu,
liczby rodzin źródeł i notatki źródłowej dla każdej drogi. Jeden normalny
`deepseek-v4-flash`, zero retry:

| Metryka | Wynik |
|---|---:|
| tokeny wejścia | 4 854 |
| tokeny wyjścia | 27 870 |
| czas | 250,297 s |
| koszt KNOWN | 0,019462 USD |
| web search/fetch/Substack | 0/0/0 |
| kontrakt | PASS; 24/24 dróg ocenionych |

Rozkład głębokości: trzy drogi `RICH`, dwadzieścia `SINGLE`, jedna `THIN`.
`THIN` była wyłącznie droga mutual aid w `The Uninsurable World`; model jawnie
stwierdził, że bez wywiadów publiczny materiał wyczerpuje się w jednym zdaniu.

| Uniwersum | Droga wybrana wewnątrz uniwersum | Głębokość | Pewność | Rodziny źródeł |
|---|---|---|---:|---:|
| Standard Human Body | historia crash-test dummy i droga do pregnant dummy | RICH | 0,90 | 4 |
| Suspicion as Default | koszt prior authorization | SINGLE | 0,85 | 4 |
| Afterlife of Abandoned Infrastructure | osierocony szyb naftowy | RICH | 0,90 | 4 |
| Last Human in the Loop | człowiek za fraud review | SINGLE | 0,85 | 3 |
| Quality of Recycled Materials | zmiana progu czystości importu | RICH | 0,85 | 4 |
| Uninsurable World | wyjście ubezpieczyciela przed katastrofą | SINGLE | 0,80 | 3 |

### Drugi ręczny FAIL

Runtime nadal wybrał prior authorization. Przyczyna nie leżała w modelu:
deterministyczny selektor umieszczał ranking całego uniwersum przed głębokością
wybranej drogi. Wybierał więc `SINGLE` przed trzema dostępnymi `RICH`.

Poprawka przesunęła głębokość dokładnej drogi przed ranking parasola. Nowy test
kontrprzykładu wymusza, aby wysoko ocenione uniwersum z drogą `SINGLE` przegrało
z niżej ocenionym uniwersum mającym drogę `RICH`.

## 8. Ostateczny wybór na niezmienionych danych live

Po poprawce, bez trzeciego płatnego wywołania, dokładne dane F2 dają:

- **uniwersum:** `The Afterlife of Abandoned Infrastructure`;
- **pytanie uniwersum:** co dzieje się, gdy kopalnia, tama, kabel, fabryka albo
  system przestają być użyteczne dla właściciela, ale nadal istnieją;
- **droga artykułu:** `How does an orphaned oil well become a public problem
  decades after the company that drilled it disappears?`;
- **mechanizm:** fizyczny szyb pozostaje, lecz podmiot prawny znika, a
  niewystarczające zabezpieczenie przenosi koszt zamknięcia na państwo;
- **drugi akt:** ten sam mechanizm zostawia publiczny rachunek przy kopalniach
  węgla i osieroconych terenach Superfund;
- **ocena:** `RICH`, pewność 0,90, cztery rodziny źródeł pierwotnych.

Pełny deterministyczny wynik i ręczny werdykt zapisano w
`.live-experiments/E-019b-scout-route-depth-live/manual-selection-replay.json`.

## 9. Ręczna kontrola obiecanych źródeł

Model nie dostał wyszukiwarki. Po jego odpowiedzi wykonano osobną, publiczną i
read-only kontrolę źródeł. Nie użyto sesji Substacka.

| Obietnica modelu | Rzeczywiście znaleziony dokument pierwotny | Wniosek |
|---|---|---|
| BLM: statusy szybów, odpowiedzialność i bonds | [BLM, Protecting Taxpayers and Communities from Orphaned Oil and Gas Wells](https://www.blm.gov/sites/default/files/docs/2024-06/BLM-OilandGas-Orphanwells-Factsheet-June2024.pdf) | istnieje; definiuje shut-in, idled i orphaned, odpowiedzialność po transferze oraz aktualne minima zabezpieczeń |
| niedostateczne bonds i koszt publiczny | [GAO-19-615](https://www.gao.gov/products/gao-19-615) | istnieje; raportuje mechanizm niedostatecznego zabezpieczenia i kosztu po stronie BLM |
| dane i potencjalne zobowiązania | [GAO-18-250](https://www.gao.gov/products/gao-18-250) | istnieje; pokazuje luki danych i ryzyko zobowiązań |
| stanowe programy i rejestry | [DOI State Orphaned Wells Program](https://www.doi.gov/state-orphaned-wells-program) | istnieje; publikuje guidance, data template i zasady finansowania |
| aktualny przepływ publicznych pieniędzy | [DOI FY2025 Annual Report](https://www.doi.gov/sites/default/files/documents/2025-11/fy-2025-orphaned-wells-congressional-report.pdf) | istnieje; zawiera granty, stany, nadzór i raportowanie wyników |

Ręczna kontrola zalicza dostępność źródeł. Nie dowodzi jeszcze tez przyszłego
artykułu: discovery musi zwrócić dokładne URL-e, fetch musi zachować dokumenty,
a klasyfikacja i synteza muszą przypisać każde twierdzenie do fragmentu.

## 10. V2 kontra aktualny V3

V2 pozostawało tylko do odczytu. E-019 nie zmienia modeli ani całego układu ról;
naprawia przejście między istniejącym Scoutem i research.

| Wymiar | V2 / stary V3 | Aktualny V3 po E-019 | Dowód |
|---|---|---|---|
| jednostka | jeden obiekt, procedura albo ciekawostka | szerokie uniwersum plus jedna jawna droga artykułu | raw E-018 i replay E-019 |
| pomysły | głównie recall znanych precedensów | kilka trybów wynalazczych, odrzucone zalążki, fatalna słabość | raw Scouta |
| ranking | listy względne bez zachowania pozycji | kolejność 1/2/3 zachowana i audytowalny breakdown | test kontrprzykładu |
| feasibility | ocena całego hasła | 24/24 dróg z osobną głębokością i drugim aktem | F2 live |
| przejście do researchu | temat parasolowy | dokładne pytanie i mechanizm wybranej drogi | `selected_article_route` |
| odporność cache | zmiana jednego promptu unieważniała wszystkie etapy | fingerprint promptu/kontraktu per etap | negatywny replay koszt 0 |
| ręczna jakość | brak obowiązkowej granicy | dwa wyniki techniczne zatrzymane jako ręczny FAIL | E-019-F1/F2 |

V3 jest na tej granicy jakościowo lepsze od V2, bo potrafi stworzyć duże pole,
nie pomylić go z pojedynczym artykułem i wybrać drogę z dowodowym drugim aktem.
Nie ma jeszcze dowodu przewagi całego bota: artykuł, rewizja i Notes dla tego
tematu jeszcze nie powstały.

## 11. Koszt i bezpieczeństwo

- F1: 0,020601 USD KNOWN;
- F2: 0,019462 USD KNOWN;
- negatywny replay cache i wszystkie poprawki/testy: 0 USD;
- razem E-019: **0,040063 USD KNOWN**;
- konserwatywna ekspozycja całych badań po E-019: **6,44480970 USD**;
- pozostały margines globalnego capu 10 USD: **3,55519030 USD**;
- zero retry, zero web search modeli, zero fetchu runtime, zero Substacka.

## 12. Werdykt i następna granica

Przed werdyktem wykonano pełną regresję. Pierwsze dwa przebiegi zachowano jako
54/55: pierwszy ujawnił martwą stałą starego nasycenia, drugi sporadyczny
`WinError 5` checkpointu. Po usunięciu martwego API, odtworzeniu flake 3/10,
unikalnym tempie, ograniczonym retry oraz stressie 10/10 finalna regresja
T-174 przeszła **55/55 w 56,775 s**. Żaden z tych testów nie użył sieci.

Scout jako generator portfela: **PASS na tym jednym live**. Wygenerował sześć
różnych pól i jawnie odrzucił małe ciekawostki. Feasibility jako ocena 24 dróg:
**PASS live**. Pierwsze dwa wybory runtime: **FAIL ręczny**. Ostateczny wybór na
tych samych danych po deterministycznych poprawkach: **PASS do discovery**.

Nie wolno jeszcze nazywać bota świetnym. Najbliższy test ma wykonać wyłącznie
normalne discovery dla osieroconych szybów, ręcznie porównać zapytania i URL-e
z powyższym źródłowym kontrprzykładem, a dopiero potem dopuścić fetch.

Errata przed E-020: samo pytanie nie niosło do discovery mechanizmu,
oczekiwanego dowodu ani drugiego aktu. A-122 przeniosło pełny brief i dodało go
do tożsamości cache. T-175 przeszło 20/20, a finalna regresja przed live
discovery T-176 przeszła 55/55 w 56,756 s.
