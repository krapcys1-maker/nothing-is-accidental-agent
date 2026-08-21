# Specyfikacja pełnej autonomii Agent V3

**Status:** obowiązujący cel architektoniczny  
**Data:** 2026-08-21  
**Nadrzędność:** ten dokument ma pierwszeństwo przed historycznymi propozycjami opartymi na zewnętrznej akceptacji

## 1. Definicja celu

Docelowy Agent V3 samodzielnie wykonuje pełny cykl redakcyjny:

`obserwacja -> wybór tematu -> research -> synteza -> pisanie -> kontrola -> rewizja -> decyzja -> publikacja -> interakcje -> pomiar -> uczenie -> następna decyzja`

Autonomia obejmuje decyzje redakcyjne i operacyjne. System nie przekazuje gotowości tekstu do osobnej bramki akceptacyjnej. Każda decyzja musi jednak wynikać z jawnego, testowalnego kontraktu. Autonomia nie oznacza publikowania mimo braku dowodu.

## 2. Stany końcowe tekstu

Każdy artykuł kończy przebieg w dokładnie jednym stanie:

- `PUBLISHED_CONFIRMED` — opublikowany i potwierdzony identyfikatorem bieżącej próby;
- `READY_AUTONOMOUS` — przeszedł wszystkie bramki, lecz publikacja jest wyłączona przez politykę środowiska;
- `QUARANTINED_EVIDENCE` — brakuje pochodzenia twierdzeń lub źródeł;
- `QUARANTINED_EDITORIAL` — po dozwolonej liczbie rewizji pozostaje wada krytyczna;
- `DEFERRED` — materiał nie osiągnął progu researchu i ma warunek wznowienia;
- `BLOCKED_CAPABILITY` — środowisko nie ma dozwolonej możliwości wykonania operacji;
- `FAILED_TECHNICAL` — błąd techniczny z zachowanym stanem i klasą awarii;
- `OUTCOME_UNKNOWN` — operacja mogła zajść, lecz nie ma potwierdzenia; ponowienie jest zabronione do czasu automatycznej rekoncyliacji.

Żaden stan kwarantanny, awarii ani niepewności nie może zostać zmapowany na sukces.

## 3. Autonomiczna decyzja publikacyjna

Publikacja jest dozwolona tylko wtedy, gdy wszystkie warunki są prawdziwe:

1. środowisko ma jawną możliwość `PUBLISH_ARTICLE`;
2. identyfikator konta i publikacji zgadza się z kanoniczną konfiguracją;
3. źródła spełniają minima jakości i różnorodności;
4. każde zdanie faktograficzne ma łańcuch `source_id -> fragment_id -> claim_id -> sentence_id`;
5. żadna krytyczna bramka nie ma stanu `FAIL`, `UNKNOWN` ani `UNAVAILABLE`;
6. kontrakt długości, struktury i stylu jest spełniony;
7. rewizja, jeżeli była potrzebna, przeszła ponowną pełną kontrolę;
8. koszt został zarezerwowany przed krokiem i rozliczony po kroku;
9. doba, limit i idempotency key bieżącej próby są zamrożone;
10. transport zwrócił identyfikator publikacji powiązany z tą próbą;
11. odczyt potwierdzający wskazuje ten sam identyfikator, konto i skrót treści.

To jest koniunkcja, nie wynik średni. Wysoki styl nie kompensuje braku źródła, a wysoki engagement nie kompensuje błędu faktograficznego.

## 4. Autonomiczna rewizja

Rewizja działa jako ograniczona maszyna stanów:

1. klasyfikacja uwag według typu i ciężaru;
2. plan minimalnych zmian powiązany z identyfikatorami uwag;
3. wygenerowanie nowej wersji bez nadpisania oryginału;
4. porównanie semantyczne i strukturalne wersji;
5. ponowna kontrola wszystkich bramek, nie tylko bramek wcześniej niezaliczonych;
6. maksymalnie ustalona liczba iteracji;
7. kwarantanna, jeżeli wada krytyczna pozostaje albo pojawia się nowa.

Rewizja nie może rozszerzać tezy, dodawać faktu bez źródła ani usuwać informacji o niepewności tylko po to, by przejść bramkę.

## 5. Autonomiczne uczenie redakcyjne

System oddziela:

- dane surowe;
- cechy treści;
- wyniki w stałych horyzontach;
- obserwacje;
- hipotezy;
- reguły kandydujące;
- reguły aktywne;
- reguły wycofane.

Reguła może zostać aktywowana automatycznie wyłącznie, gdy:

- obejmuje minimalną, z góry ustaloną liczbę porównywalnych publikacji;
- efekt utrzymuje się w więcej niż jednym oknie czasu;
- ma przynajmniej jeden test kontrprzykładu;
- nie pogarsza krytycznych wymiarów jakości;
- otrzymuje wersję, zakres i czas ważności;
- jest wdrażana na ograniczonej części decyzji;
- ma automatyczny warunek rollbacku.

Pojedynczy viral, pojedyncza korekta lub pojedynczy słaby wynik nie może stać się regułą globalną.

## 6. Wielowymiarowy wynik

V3 nie ma jednego `success_score`. Przechowuje osobne osie:

- zasięg;
- otwarcia i kliknięcia;
- dyskusja;
- pytania i ciekawość;
- polemika;
- restacki;
- konwersja;
- długowieczność;
- korekty faktograficzne;
- stabilność jakości redakcyjnej.

Każda wartość ma wynik absolutny, wynik względem kohorty oraz horyzont pomiaru. Brak metryki ma wartość `MISSING`, nie zero.

## 7. Pełna autonomia a bezpieczeństwo

Pełna autonomia wymaga mocniejszych mechanizmów niż system zależny od zewnętrznej akceptacji:

- domyślnie brak możliwości mutacji;
- jawny rejestr możliwości dla każdej funkcji;
- fail-closed dla publikacji i interakcji;
- automatyczna kwarantanna zamiast wymuszonego sukcesu;
- idempotency key i rekoncyliacja stanów niepewnych;
- osobne limity dla każdego rodzaju działania;
- automatyczny kill switch obejmujący modele, przeglądarkę, API i scheduler;
- obserwowalność wystarczająca do maszynowego wykrycia regresji;
- rollback reguł uczenia i wersji promptów.

## 8. Tryby środowiska

- `OFFLINE_FIXTURE` — pełna logika, wszystkie transporty zastąpione fixture'ami;
- `READ_ONLY_NETWORK` — sieć wyłącznie do odczytu, technicznie zablokowane metody mutujące;
- `SHADOW` — pełne decyzje i raporty, ale brak możliwości wysłania mutacji;
- `AUTONOMOUS_LIVE` — wszystkie bramki i możliwości jawnie aktywne; docelowy tryb po udowodnieniu własności bezpieczeństwa.

Przejście między trybami jest konfiguracją wdrożeniową z kontrolą integralności. Flaga typu `wyslij=False` nie może zastępować modelu możliwości.

## 9. Kryterium osiągnięcia pełnej autonomii

Cel jest osiągnięty, gdy V3 przez wersjonowany zestaw replayów i testów integracyjnych samodzielnie:

- wybiera lub odkłada temat zgodnie z dowodami;
- tworzy tekst z kompletnym pochodzeniem;
- rozpoznaje i naprawia naprawialne wady;
- odrzuca lub kwarantannuje stan niebezpieczny;
- publikuje dokładnie raz i potwierdza konkretną próbę;
- mierzy skutki w stałych horyzontach;
- wprowadza i wycofuje reguły na podstawie stabilnych danych;
- zachowuje wszystkie limity po restarcie, awarii zapisu i timeoutach;
- nie wymaga osobnego etapu akceptacji redakcyjnej.
