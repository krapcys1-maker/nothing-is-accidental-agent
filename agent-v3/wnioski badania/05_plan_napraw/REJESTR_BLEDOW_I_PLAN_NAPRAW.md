# Rejestr błędów i plan napraw Agent V3

**Stan:** plan wykonywany iteracyjnie; karty N-001–N-024 udokumentowane
**Źródło:** ustalenia A-001–A-103
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
**Ustalenia:** A-025, A-026, A-044, A-073, A-096, A-098, A-101.
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
**Ustalenia:** A-005–A-007, A-024, A-029–A-032, A-041–A-044, A-047, A-055, A-060, A-069, A-070, A-072, A-093, A-099.
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
**Ustalenia:** A-015–A-018, A-021, A-033–A-040, A-052, A-054, A-071, A-080–A-081.
**Wyjście:**

- bezpieczny fetch z kontrolą scheme/DNS/IP po każdym redirect;
- limit bajtów odpowiedzi i czasu;
- exact-document binding między discovery i fetch;
- wersjonowany schemat karty syntezy;
- walidacja odpowiedzi modeli przed użyciem;
- identyfikatory źródła, fragmentu, twierdzenia, zdania i przypisu;
- zdanie mieszane nie może ukryć faktu pod etykietą inferencji;
- URL jest bezpiecznie escapowany we wszystkich kontekstach HTML.
- surowy tekst zewnętrzny nie trafia do warstwy instrukcyjnej ani trwałej pamięci promptowej;
- granica danych stoi przed pierwszym bajtem niezaufanej treści w wyrenderowanym prompcie.

### Faza 4 — autonomiczna redakcja

**Cel:** bramki zmieniają tekst lub kierują go do automatycznej kwarantanny.  
**Ustalenia:** A-008–A-014, A-019–A-021, A-027, A-036–A-038, A-062–A-065, A-074–A-079, A-082–A-083, A-094, A-097.
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
- każdy format otrzymuje właściwy profil gatunku i wspólną tożsamość marki;
- redaktor otrzymuje ten sam kontrakt głosu co pisarz i zachowuje go w teście przed/po;
- dozwolone kombinacje ruchu, postawy i otwarcia są spójne semantycznie;
- empiryczna reguła promptu ma manifest dowodu, ograniczenia i termin ponownej oceny.

### Faza 5 — koszt, cache i konfiguracja

**Cel:** konfiguracja opisuje prawdziwe zachowanie, a koszt jest rezerwowany przed krokiem.  
**Ustalenia:** A-017, A-022, A-046, A-048–A-051, A-053, A-057, A-061, A-067, A-086–A-088, A-095.
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
**Ustalenia:** A-001, A-026, A-056, A-058, A-066, A-068–A-069, A-089–A-092, A-100.
**Wyjście:**

- wersjonowany manifest środowiska;
- preflight zależności i kontraktów API;
- rollback bez `reset --hard` na nieczystym drzewie;
- scheduler nie może ominąć capability gates;
- każda operacja produkcyjna ma idempotency key i potwierdzenie;
- automatyczne zatrzymanie i rekoncyliacja po stanie `UNKNOWN`.

## 4. Pierwsze piętnaście kart napraw

| Kolejność | Karta | Ustalenia | Status | Minimalny rezultat |
|---:|---|---|---|---|
| 1 | N-001 Izolacja ścieżek V2 | A-001, A-026, A-053 | FIXED_OFFLINE | V3 nie wykonuje ani nie opisuje aktywnego uruchomienia V2 |
| 2 | N-002 Globalny rejestr możliwości | A-003, A-004, A-023, A-059 | FIXED_OFFLINE | każda mutacja ma jedną nieomijalną bramkę |
| 3 | N-003 Izolacja sekretów i sesji | A-002 | FIXED_OFFLINE | fixture mode nie może odczytać żywych poświadczeń |
| 4 | N-004 Hermetyczny test całego potoku | A-023, A-044, A-098 | FULL_PIPELINE_FIXED_OFFLINE; LIVE_BLOCKED_MISSING_CREDENTIALS | zwykłe `run.main` przechodzi pełny replay 7/7; E-012 obejmuje pełny live ról i odmawia bez kluczy |
| 5 | N-005 Ledger prób i potwierdzeń | A-005, A-006, A-007, A-060, A-069, A-093 | FINAL_AND_DRAFT_LEDGER_FIXED_OFFLINE; PLATFORM_LIVE_NOT_RUN | końcowy dispatch i wcześniejszy zapis zdalnego szkicu mają osobne intenty, potwierdzenia i recovery |
| 6 | N-006 Zamrożona doba i budżet | A-029–A-032, A-084 | FIXED_OFFLINE; LIVE_CONTRACT_OPEN | stały limit obejmuje wszystkie działania, restarty i zmianę polityki w środku dnia; live pozostaje niezweryfikowane |
| 7 | N-007 Bezpieczny fetch | A-033, A-034, A-054, A-085 | FIXED_OFFLINE; LIVE_CONTRACT_OPEN | publiczny unicast, przypięty DNS, ręczne redirecty, exact URL, pochodzenie i limity; prawdziwy TLS pozostaje niezweryfikowany |
| 8 | N-008 Schematy odpowiedzi LLM | A-018, A-038 | FIXED_OFFLINE; LIVE_CONTRACT_OPEN | 22/22 granice przechodzą wersjonowaną walidację; błędy krytyczne są fail-closed |
| 9 | N-009 Pochodzenie twierdzeń | A-015, A-016, A-035, A-039 | FIXED_OFFLINE; LIVE_PARTIAL_PASS | DeepSeek przeszedł klasyfikację i recenzję MIXED, lecz nie zwrócił pełnej syntezy; wynik Sonnet jest historycznym, nieuprawnionym override i nie waliduje normalnego routingu V3 |
| 10 | N-010 Transakcyjny zapis artykułu | A-013, A-041, A-042, A-055 | FIXED_OFFLINE; POWER_LOSS_NOT_PROVEN | prepare/intent/transaction/recovery; 7/7 celu i 48/48 regresji |
| 11 | N-011 Autonomiczna rewizja i kwarantanna | A-019, A-020, A-036, A-064, A-065 | FIXED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN | trzy terminalne stany, dwie iteracje, pełne bramki po każdej zmianie; 13/13 i 50/50 PASS |
| 12 | N-012 Kolektor metryk, kohort i niepewności | A-008–A-011, A-052, A-072, A-099 | OPEN | snapshoty i wyniki względne po właściwym ID; przedział liczebności nie udaje pewności statystycznej |
| 13 | N-013 Wersjonowany kontrakt głosu | A-021, A-062–A-063, A-074–A-079, A-082, A-094 | OPEN | jedna tożsamość marki, profile gatunków, hashe assetów i zgodne ruchy dla każdej roli |
| 14 | N-014 Izolacja danych w promptach i pamięci | A-040, A-080–A-081 | OPEN | niezaufany tekst nie może stać się instrukcją ani trwałą regułą |
| 15 | N-015 Semantyczne testy promptów i rewizji | A-020, A-035, A-063–A-065, A-075–A-076, A-083, A-097 | OPEN | wyrenderowane kontrakty i przypadki przed/po dowodzą faktów, głosu oraz braku regresji |

## 5. Karty wykryte podczas eksperymentów live

| Karta | Ustalenie | Status | Minimalny rezultat |
|---|---|---|---|
| N-016 Okresowy cennik modeli | A-087 | FIXED_OFFLINE; BILL_RECONCILIATION_OPEN | taryfa Sonnet 5 zależy od czasu UTC i nie udaje potwierdzenia fakturą |
| N-017 Nieznany koszt i retry modelu | A-086 | FIXED_OFFLINE; LIVE_REPLAY_OPEN | niepełna odpowiedź po dispatch ma koszt UNKNOWN, zachowuje rezerwację i nie jest automatycznie ponawiana |
| N-018 Promowalny artefakt V3 | A-089–A-092 | FOUNDATION_DOCUMENTED; IMPLEMENTATION_OPEN | jeden niemutowalny bundle, migracje, shadow/canary i atomowy rollback |

Brak request ID w adapterach (A-088) jest zadaniem przekrojowym N-017/N-018:
kolumna istnieje, lecz identyfikatory nie są jeszcze przechwytywane na wszystkich
transportach.

## 6. Karty utworzone po pełnym audycie stanu bieżącego

| Karta | Ustalenie | Status | Minimalny rezultat |
|---|---|---|---|
| N-019 Ledger zdalnego szkicu | A-093 | FIXED_OFFLINE; PLATFORM_LIVE_NOT_RUN | osobne `draft_write` przed pierwszym zdalnym zapisem i publikacja zależna od potwierdzonego ID; 45/45 regresji |
| N-020 Atomowa rezerwacja kosztu modelu | A-095, A-112 | ATOMICITY_FIXED_OFFLINE; ACTUAL_CAP_REOPENED | jedna transakcja check-and-reserve działa, lecz E-018 dowiodło, że settlement może przekroczyć rezerwację bez limitu `max_tokens`; dalszy zakres w N-028 |
| N-021 Wiązanie ID publikacji z treścią | A-099 | OPEN | `PUBLISHED` zawsze ma dokładne external ID, URL i referencję próby |
| N-022 Autonomiczne uwierzytelnienie i backup | A-100 | OPEN; PLATFORM_CONTRACT_REQUIRED | wspierane odnowienie auth i eksport albo twarda blokada promocji |
| N-023 Kanoniczny pin korpusu stylu | A-102 | FIXED_OFFLINE; LIVE_WRITER_OPEN | identyczna treść LF/CRLF ma ten sam pin; N-004 używa realnego loadera |
| N-024 Izolacja artefaktów live | A-103 | FIXED_OFFLINE | `.env` i pełne raw artefakty są lokalne i ignorowane przez Git |
| N-025 Streaming i rekoncyliacja DeepSeek | A-104 | FIXED_OFFLINE; LIVE_BLOCKED_THREE_UNKNOWN; BILL_RECONCILIATION_REQUIRED | SSE wymaga DONE/usage; trzy rezerwy UNKNOWN blokują kolejny dispatch do dowodu dostawcy |
| N-026 Streaming `/responses` DeepSeek | A-108 | FIXED_OFFLINE; LIVE_DISCOVERY_BLOCKED_BUDGET | parser SSE `/responses` 4/4; dodatni discovery live dopiero po rekoncyliacji |
| N-027 Scout uniwersów artykułowych | A-109–A-111, A-113–A-114 | LIVE_PARTIAL_PASS; POST_LIVE_FIX_OFFLINE; DIVERSE_LIVE_OPEN | E-018 raw 6 tematów i 5 odrzuconych zalążków; replay 6/6; nowy system prompt jeszcze bez live |
| N-028 Twardy cap kosztu faktycznego | A-112 | SCOUT_HARNESS_FIXED_OFFLINE; SHARED_RUNTIME_OPEN | predispatch worst-case działa w Scout-only; wspólny runtime musi wyprowadzać `max_tokens` z rezerwacji |

## 7. Zasada stopu technicznego

Jeżeli naprawa ujawnia nową ścieżkę P0, seria przechodzi do tej ścieżki przed dalszą rozbudową. Jeżeli test nie potrafi odróżnić starej i nowej implementacji, zmiana nie może otrzymać statusu `FIXED_OFFLINE`.

## 8. Powiązanie z pełną autonomią

Plan nie dodaje etapu zewnętrznej akceptacji. Wszystkie kryteria są wykonywalne maszynowo. Materiał nieprzechodzący bramek jest autonomicznie poprawiany, odkładany lub kwarantannowany; nie jest publikowany przez fallback.
