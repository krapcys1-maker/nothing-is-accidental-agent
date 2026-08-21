# Krytyczna analiza materiałów wejściowych

**Data:** 2026-08-21  
**Materiały:** `poprawa.txt`, `tutaj jest do zaczerpiecia z neta.txt`  
**Cel:** oddzielić trafne hipotezy od ocen bez protokołu i dostosować kierunek do pełnej autonomii V3

## 1. Status źródeł

Oba pliki są wartościowymi notatkami koncepcyjnymi. Nie są wynikami kontrolowanego eksperymentu ani aktualną specyfikacją V3. Pierwszy rozwija pomysł pamięci wyników i pętli redakcyjnej. Drugi porównuje kilka publicznych repozytoriów, lecz opiera część ocen na README i używa punktacji bez wspólnej rubryki.

Wniosek: pliki pozostają archiwalnym źródłem hipotez. Wiążące są ustalenia audytu, zweryfikowane badanie repozytoriów i specyfikacja pełnej autonomii.

## 2. Hipotezy przyjęte

### H-W01. Intencja, wykonanie i potwierdzenie muszą być osobnymi zdarzeniami

Hipoteza jest silnie potwierdzona audytem A-005–A-007, A-055, A-059, A-060 i A-069–A-070. Każda operacja powinna mieć `attempt_id`, idempotency key, wynik transportu, potwierdzenie platformy i stan `UNKNOWN` przy braku dowodu.

### H-W02. Bramki muszą rzeczywiście zmieniać tekst lub decyzję

Potwierdzają to A-019, A-020, A-036, A-064 i A-065. Sama lista uwag nie tworzy redakcji. Potrzebna jest autonomiczna rewizja, ponowna pełna kontrola i kwarantanna po niepowodzeniu.

### H-W03. Pamięć ma przechowywać treść, kontekst i skutki

Kierunek jest zasadny, ale musi zachować wiele osi wyniku oraz stałe horyzonty. Potwierdzają to A-008–A-011 i A-072. Rekord treści powinien łączyć cechy redakcyjne, snapshoty 1h/24h/7d/30d, baseline kohorty, sygnały jakościowe i relacje z wcześniejszym materiałem.

### H-W04. `ODLOZ` musi mieć pełny cykl życia

Potwierdza to A-014. Stan wymaga przyczyny, brakujących dowodów, warunku wznowienia, terminu kolejnej kontroli, liczby prób i stanu końcowego.

### H-W05. Księgowanie kosztów musi być ścisłe

Potwierdzają to A-022, A-048–A-051. Nieznane pole, nieznany model, brak ceny lub nierozliczona rezerwacja nie mogą być interpretowane jako koszt zerowy.

### H-W06. Źródła potrzebują maszyny stanów

Potwierdzają to A-015, A-016, A-034, A-039 i A-054. Minimalny cykl:

`DISCOVERED -> FETCHED -> EXTRACTED -> USED_IN_CLAIM -> CITED_IN_SENTENCE`

Oddzielnie zapisuje się `FETCH_FAILED`, `REJECTED`, `STALE` i `SECURITY_BLOCKED`.

### H-W07. Cache musi zależeć od pełnego kontraktu

Potwierdzają to A-017 i A-057. Klucz powinien uwzględniać etap, skrót wejścia, wersję promptu, model, ustawienia, wersję schematu i TTL danych zewnętrznych.

### H-W08. Nie należy przebudowywać systemu w zestaw usług bez dowodu potrzeby

Audyt potwierdza, że głównym problemem są kontrakty i spójność, nie brak rozproszonej infrastruktury. Najpierw należy uszczelnić istniejące moduły i zmniejszyć ich sprzężenie przez jawne interfejsy.

## 3. Hipotezy przyjęte po korekcie

### H-K01. Uczenie z różnicy wersji tekstu

Przydatny jest niezmienny oryginał, wersja po rewizji, lista przyczyn zmian i maszynowy diff. Nie przyjmujemy reguł stylu na podstawie pojedynczej różnicy. Reguła kandydująca musi przejść test na wielu tekstach, ograniczony rollout i automatyczny rollback.

### H-K02. Agent analityczny

Nie potrzebujemy osobnego „agenta” tylko dlatego, że tak nazywa go projekt zewnętrzny. Potrzebujemy deterministycznego kolektora, warstwy cech, porównań kohortowych oraz modelu używanego wyłącznie do klasyfikacji sygnałów jakościowych w wersjonowanym schemacie.

### H-K03. Warstwa API/MCP

Wspólny interfejs narzędziowy może zmniejszyć duplikację, lecz dopiero po wprowadzeniu rejestru możliwości. Samo wystawienie publikacji jako narzędzia zwiększa powierzchnię ryzyka i nie czyni systemu redakcyjnym.

### H-K04. Pełna autonomia

Wszystkie propozycje zależne od zewnętrznej bramki akceptacyjnej są niezgodne z celem V3. Zastępuje je koniunkcja automatycznych bramek, ograniczona rewizja, kwarantanna, testy własności i potwierdzenie konkretnej operacji.

## 4. Twierdzenia odrzucone jako nieudowodnione

### O-01. Punktacja repozytoriów

Oceny typu „autonomia 9, research 9, production hardening 9” nie mają datasetu, rubryki, wag ani replikacji. Nie będą używane do ustalania dojrzałości V3.

### O-02. Twierdzenie, że V2 jest jednym z najbardziej zaawansowanych publicznych agentów

Kwerenda GitHub nie obejmuje projektów prywatnych, komercyjnych, słabo indeksowanych ani repozytoriów używających innej terminologii. Można powiedzieć tylko, że V2/V3 ma szerszy potok niż sześć zbadanych projektów w określonych wymiarach.

### O-03. Liczba funkcji jako dowód dojrzałości

Więcej etapów, promptów, tabel i działań społecznościowych nie dowodzi niezawodności ani jakości. W V3 szerokość funkcjonalna współistnieje z krytycznymi brakami P0.

### O-04. Engagement jako bezpośredni sygnał jakości

Reakcje mogą premiować sensację, konflikt lub wzrost konta niezależny od treści. Dlatego wynik pozostaje wielowymiarowy, kohortowy i oddzielony od krytycznych bramek faktograficznych.

### O-05. Automatyczne kopiowanie nieoficjalnych endpointów

Publiczny zeszyt endpointów jest hipotezą integracyjną, nie stabilnym API. Każdy endpoint wymaga adaptera, fixture'u kontraktowego, timeoutu, typu błędu i degradacji.

## 5. Wnioski dla planu V3

Materiały wejściowe prawidłowo rozpoznały największą lukę: brak zamkniętej pętli `treść -> wynik -> obserwacja -> następna decyzja`. Audyt wykazał jednak, że nie wolno budować tej pętli przed izolacją prototypu, naprawą potwierdzeń, stabilizacją stanu i domknięciem pochodzenia twierdzeń.

Kolejność wynikająca z analizy:

1. izolacja i rejestr możliwości;
2. jednoznaczny model próby i potwierdzenia;
3. hermetyczny pełny pipeline offline;
4. wersjonowane kontrakty modeli i danych;
5. pochodzenie źródło–twierdzenie–zdanie;
6. autonomiczna rewizja z kwarantanną;
7. kolektor wyników i kohorty;
8. autonomiczne uczenie z rolloutem i rollbackiem.

## 6. Relacja do badań porównawczych

Wszystkie repozytoria wymienione w `tutaj jest do zaczerpiecia z neta.txt` zostały ponownie sprawdzone w kodzie źródłowym. Wyniki, hashe commitów i ograniczenia znajdują się w `../04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md`.
