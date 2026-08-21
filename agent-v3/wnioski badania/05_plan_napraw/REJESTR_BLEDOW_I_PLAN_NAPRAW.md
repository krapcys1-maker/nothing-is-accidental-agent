# Rejestr błędów i plan napraw Agent V3

**Stan:** plan przed implementacją  
**Źródło:** ustalenia A-001–A-073  
**Zasada:** jeden logiczny błąd lub jedna nierozdzielna własność na zmianę; wyłącznie V3

## 1. Statusy napraw

- `OPEN` — defekt potwierdzony statycznie;
- `TEST_FAILING` — istnieje test odtwarzający wadę starej wersji;
- `PATCHED` — kod zmieniony, test celu przechodzi;
- `REGRESSION_PASSED` — przechodzi właściwy zestaw regresji offline;
- `FIXED_OFFLINE` — własność udowodniona bez sieci;
- `FIXED_READ_ONLY` — dodatkowo sprawdzona sieciowo bez mutacji;
- `CLOSED` — spełnione wszystkie kryteria właściwe dla danego błędu.

`PATCHED` nigdy nie jest synonimem `CLOSED`.

## 2. Protokół pojedynczej naprawy

Każda naprawa otrzymuje kartę:

1. identyfikator audytu i krótka hipoteza;
2. dokładna ścieżka wykonania prowadząca do wady;
3. odcisk plików przed zmianą;
4. test kontrdowodu, który przechodzi na starej wadliwej logice albo jawnie ją rekonstruuje;
5. test, który nie przechodzi przed poprawką;
6. minimalna zmiana w V3;
7. test celu, testy sąsiednie i pełna bezpieczna regresja;
8. kontrola drzewka plików po teście;
9. aktualizacja dokumentacji i statusu;
10. commit obejmujący wyłącznie potwierdzone ścieżki V3.

Jeżeli test dotyka sieci, modelu lub przeglądarki, karta wskazuje powód, dla którego fixture nie wystarcza, oraz koszt z księgi.

## 3. Kolejność blokująca

### Faza 0 — punkt odniesienia

**Cel:** utrwalić obecny korpus, gałąź, dokumentację i bezpieczną komendę testów.  
**Ustalenia:** A-025, A-026, A-044, A-073.  
**Wyjście:** centralna dokumentacja, hash manifestu, test hermetyczności katalogu danych i lista testów wyłączonych z automatycznej regresji.

### Faza 1 — izolacja V3 i rejestr możliwości

**Cel:** uczynić technicznie niemożliwą mutację zewnętrzną w trybie prototypowym.  
**Ustalenia:** A-001–A-004, A-023, A-053, A-056, A-058, A-059, A-066, A-068.  
**Wyjście:**

- żadna ścieżka V3 nie wskazuje wykonawczo V2;
- V3 nie czyta sekretów ani sesji z katalogu wspólnego w trybie testowym;
- centralny `CapabilityRegistry` klasyfikuje odczyt, draft, publikację, komentarz, reakcję, follow, subskrypcję i wdrożenie;
- domyślna konfiguracja zezwala tylko na fixture;
- kill switch jest sprawdzany bezpośrednio przed każdą mutacją;
- `wyslij=False` nie otwiera ani nie zmienia zdalnego edytora;
- skrypty wdrożeniowe nie są wykonywalne w trybie prototypowym.

### Faza 2 — prawda o działaniu i stanie

**Cel:** liczyć tylko potwierdzone skutki i zachować wynik niepewny.  
**Ustalenia:** A-005–A-007, A-024, A-029–A-032, A-041–A-044, A-047, A-055, A-060, A-069, A-070, A-072.  
**Wyjście:**

- jedno zdarzenie `ActionAttempt` z `attempt_id`, idempotency key i capability;
- stany `INTENDED`, `SENT`, `CONFIRMED`, `REJECTED`, `UNKNOWN`;
- zamrożony `OperationalDay` w jednej strefie;
- budżet zapisany raz na dobę i obejmujący wszystkie działania;
- awaria dziennika blokuje dalsze mutacje;
- artykuł jest potwierdzany przez ID bieżącej próby;
- restack nie niszczy kontekstu dalszej pętli;
- outcome jest wiązany z treścią i horyzontem, nie tylko czasem.

### Faza 3 — bezpieczeństwo researchu i pochodzenie twierdzeń

**Cel:** udowodnić, skąd pochodzi każde zdanie faktograficzne.  
**Ustalenia:** A-015–A-018, A-021, A-033–A-040, A-052, A-054, A-071.  
**Wyjście:**

- bezpieczny fetch z kontrolą scheme/DNS/IP po każdym redirect;
- limit bajtów odpowiedzi i czasu;
- exact-document binding między discovery i fetch;
- wersjonowany schemat karty syntezy;
- walidacja odpowiedzi modeli przed użyciem;
- identyfikatory źródła, fragmentu, twierdzenia, zdania i przypisu;
- zdanie mieszane nie może ukryć faktu pod etykietą inferencji;
- URL jest bezpiecznie escapowany we wszystkich kontekstach HTML.

### Faza 4 — autonomiczna redakcja

**Cel:** bramki zmieniają tekst lub kierują go do automatycznej kwarantanny.  
**Ustalenia:** A-008–A-014, A-019–A-020, A-027, A-036–A-038, A-062–A-065.  
**Wyjście:**

- jedna maszyna stanów artykułu;
- ważności uwag zamiast samej liczby;
- pełna ponowna kontrola po rewizji;
- `NEEDS_REVIEW` usunięty z aktywnego kontraktu;
- stany `QUARANTINED_EVIDENCE` i `QUARANTINED_EDITORIAL`;
- rewizje prawidłowo związane z `article_id`;
- `ODLOZ` ma warunek wznowienia i wygaśnięcie;
- długość i głos są egzekwowanym, wersjonowanym kontraktem;
- wszystkie warstwy głosu mają kontrolę integralności.

### Faza 5 — koszt, cache i konfiguracja

**Cel:** konfiguracja opisuje prawdziwe zachowanie, a koszt jest rezerwowany przed krokiem.  
**Ustalenia:** A-017, A-022, A-046, A-048–A-051, A-053, A-057, A-061, A-067.  
**Wyjście:**

- rezerwacja i rozliczenie kosztu;
- nieznane pola/model/cena powodują jawny błąd;
- jeden kontrakt tokenów, timeoutów i effort;
- `--topics` wpływa na wszystkie zależne limity;
- cache ma pełny klucz i może być całkowicie wyłączony;
- zegar jest przekazywany do pętli wewnętrznych;
- środowisko zależności ma reprodukowalny lock.

### Faza 6 — pamięć wyników i autonomiczne uczenie

**Cel:** wynik wpływa na następne decyzje bez sprowadzenia jakości do engagement.  
**Ustalenia:** A-008–A-011, A-027, A-041, A-072.  
**Wyjście:**

- kolektor treści i metryk w stałych horyzontach;
- baseline'y według typu treści, wieku konta i okresu;
- klasyfikacja pytań, polemik, przykładów i korekt;
- obserwacja ma próbę, efekt, kontrprzykład, ważność i historię;
- aktywacja reguły wymaga minimalnej próby, stabilności, rollout'u i rollbacku;
- brak jednego globalnego `success_score`.

### Faza 7 — operacje autonomiczne

**Cel:** bezpieczne przejście od shadow do w pełni autonomicznego trybu.  
**Ustalenia:** A-001, A-026, A-056, A-058, A-066, A-068–A-069.  
**Wyjście:**

- wersjonowany manifest środowiska;
- preflight zależności i kontraktów API;
- rollback bez `reset --hard` na nieczystym drzewie;
- scheduler nie może ominąć capability gates;
- każda operacja produkcyjna ma idempotency key i potwierdzenie;
- automatyczne zatrzymanie i rekoncyliacja po stanie `UNKNOWN`.

## 4. Pierwsze dwanaście kart napraw

| Kolejność | Karta | Ustalenia | Minimalny rezultat |
|---:|---|---|---|
| 1 | N-001 Izolacja ścieżek V2 | A-001, A-026, A-053 | V3 nie wykonuje ani nie opisuje aktywnego uruchomienia V2 |
| 2 | N-002 Globalny rejestr możliwości | A-003, A-004, A-023, A-059 | każda mutacja ma jedną nieomijalną bramkę |
| 3 | N-003 Izolacja sekretów i sesji | A-002 | fixture mode nie może odczytać żywych poświadczeń |
| 4 | N-004 Hermetyczny test całego potoku | A-023, A-044 | pipeline przechodzi bez sieci i bez zapisu do projektu |
| 5 | N-005 Ledger prób i potwierdzeń | A-005, A-006, A-007, A-060, A-069 | sukces wyłącznie po potwierdzeniu ID próby |
| 6 | N-006 Zamrożona doba i budżet | A-029–A-032 | stały limit obejmuje wszystkie działania i restarty |
| 7 | N-007 Bezpieczny fetch | A-033, A-034, A-054 | blokada prywatnych IP, redirectów i nadmiaru bajtów |
| 8 | N-008 Schematy odpowiedzi LLM | A-018, A-038, A-052 | każda odpowiedź przechodzi wersjonowaną walidację |
| 9 | N-009 Pochodzenie twierdzeń | A-015, A-016, A-035, A-039 | każdy fakt i liczba mają pełny łańcuch dowodu |
| 10 | N-010 Transakcyjny zapis artykułu | A-013, A-041, A-042, A-055 | brak rozjazdu plik–DB–rewizja |
| 11 | N-011 Autonomiczna rewizja i kwarantanna | A-019, A-020, A-036, A-064, A-065 | brak `NEEDS_REVIEW`; pełna kontrola po rewizji |
| 12 | N-012 Kolektor metryk i kohort | A-008–A-011, A-072 | snapshoty i wyniki względne po właściwym ID |

## 5. Zasada stopu technicznego

Jeżeli naprawa ujawnia nową ścieżkę P0, seria przechodzi do tej ścieżki przed dalszą rozbudową. Jeżeli test nie potrafi odróżnić starej i nowej implementacji, zmiana nie może otrzymać statusu `FIXED_OFFLINE`.

## 6. Powiązanie z pełną autonomią

Plan nie dodaje etapu zewnętrznej akceptacji. Wszystkie kryteria są wykonywalne maszynowo. Materiał nieprzechodzący bramek jest autonomicznie poprawiany, odkładany lub kwarantannowany; nie jest publikowany przez fallback.
