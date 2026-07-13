# HUMAN_INTERVENTIONS

## Cel

Rejestr każdej ingerencji człowieka: akceptacji, odrzucenia, edycji treści, ręcznego zatrzymania, korekty strategii, ręcznego logowania. Kluczowa metryka eksperymentu brzmi „ile nadzoru agent nadal potrzebuje?" — ten plik na nią odpowiada. Pozwala policzyć: procent treści przyjętych bez zmian, liczbę poprawek na artykuł, czas człowieka dziennie, liczbę ręcznych zatrzymań.

## Zasady

- Jeden wpis = jedna ingerencja.
- Notuj szacowany czas człowieka (minuty) — zasila metrykę „czas człowieka".
- Powiąż z obiektem (content_item / interaction / run) i kontem.

## Typy interwencji (do rozpoznania)

Człowiek: odrzucił decyzję agenta · poprawił tekst · poprawił fakt · zatrzymał publikację · zmienił strategię · zmienił grafikę · naprawił kod · ręcznie zalogował konto · zmienił poziom autonomii · inne.

Skróty typu: REJECT · EDIT_TEXT · FIX_FACT · STOP_PUBLISH · STRATEGY · EDIT_IMAGE · FIX_CODE · LOGIN · AUTONOMY · OTHER.

## Szablon wpisu

```markdown
### [YYYY-MM-DD HH:MM] Typ — krótki opis
- **Typ:** (jeden ze skrótów powyżej)
- **Konto:** account_id
- **Obiekt:** content_item #.. / interaction #.. / run <uuid> (lub —)
- **Co agent chciał zrobić:** proponowana akcja/treść agenta
- **Dlaczego człowiek zareagował:** powód interwencji
- **Co zostało zmienione:** konkretna zmiana (przed → po, jeśli dotyczy)
- **Jaki był efekt:** skutek zmiany (jakość/koszt/harmonogram/strategia)
- **Czas człowieka:** ~N min
- **Wpływ na strategię:** jeśli zmienia zasady → wpis w DECISIONS.md (ADR-XXX)
```

---

## Wpisy

### [2026-07-11] STRATEGY — decyzje właściciela po audycie
- **Typ:** STRATEGY
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** docs/DECISIONS.md
- **Powód:** rozstrzygnięcie pytań otwartych przed kodowaniem.
- **Zmiana:** (1) klucz API — tylko `.gitignore`, bez rotacji [ADR-010]; (2) docelowy sufit autonomii = LEVEL_2 z bramkowaniem [ADR-004]; (3) MVP na jednym koncie `nothing_is_accidental` [ADR-007]; (4) nisza żony = astrologia, konto nieaktywne [ADR-008]; (5) panel = FastAPI [ADR-009].
- **Czas człowieka:** ~5 min
- **Wpływ na strategię:** tak — zamyka ADR-004/007/008/009/010; pozostaje OPEN-4 (budżet dzienny). Plan nadal czeka na ogólną akceptację przed Etapem 0.

### [2026-07-12] STRATEGY — właściciel wyznaczył granice pre-flight pierwszej kompletnej Research Card
- **Typ:** STRATEGY
- **Konto:** nothing_is_accidental
- **Obiekt:** proponowany świeży research topic #2 (jeszcze bez run_id)
- **Co agent chciał zrobić:** przygotować kolejny realny staged research po udanej diagnostyce A2.
- **Dlaczego człowiek zareagował:** realny wydatek i ryzyko kolejnej awarii wymagają najpierw pełnego offline pre-flightu, jawnej estymacji oraz osobnej zgody.
- **Co zostało zmienione:** właściciel narzucił branch `dev/first-successful-research-card`, `max_sources=4`, 1 search per source, A2=1500, retry=0, normalne B; zabronił API, resume, Playwrighta, P1-5, P0-2c, zmian architektury i statusów DB w tej turze.
- **Jaki był efekt:** wykonano wyłącznie testy, read-only kontrolę bazy i estimate-only; koszt 0 USD; powstała propozycja ADR-022 i exact command, ale żadna zgoda na realny call nie została domniemana.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** tak — jeden przyszły run ma być jawnie zatwierdzony, świeży i bez retry; ADR-022 pozostaje PROPOSED.

### [2026-07-12] STRATEGY — review właściciela po audycie/konsolidacji: 4 korekty przed commitem
- **Typ:** STRATEGY
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** MASTER_ARCHITECTURE.md / IMPLEMENTATION_ROADMAP.md / CURRENT_PROJECT_STATE.md / AGENTS.md / dzienniki
- **Co agent chciał zrobić:** zakończyć konsolidację dokumentacji (ADR-023) i zaproponować commit; w blokerach CURRENT_PROJECT_STATE zgoda na run ADR-022 figurowała jako bloker #1.
- **Dlaczego człowiek zareagował:** ocena 8,5/10, zatwierdzenie kierunkowe, ale wykryte 4 niespójności: (1) bloker sugerował, że realny run jest następny w kolejce, podczas gdy roadmapa wymaga najpierw zadań 1–8 Etapu 0; (2) zasady ARCHITECTURE_EVOLUTION nadal wskazywały IMPLEMENTATION_PLAN.md jako miejsce architektury docelowej; (3) AGENTS.md łączył baner korygujący ze starymi, sprzecznymi instrukcjami („baner mówi, żeby nie słuchać reszty pliku"); (4) zasady BUILD_LOG odsyłały do etapów starego planu.
- **Co zostało zmienione:** blokery przepisane (najpierw zadania 1–8, dopiero potem osobna zgoda na zad. 9/ADR-022); zasada ARCHITECTURE_EVOLUTION wskazuje MASTER_ARCHITECTURE + ROADMAP, stare odwołania oznaczone jako archiwalne; AGENTS.md przepisany na krótką wersję 2.0 (stary import → docs/archive/superseded_plans/AGENTS_imported_cowork_instructions_2026-07.md); zasady/szablony BUILD_LOG i DECISIONS wskazują ROADMAP/MASTER; sweep normatywnych odwołań w kronice i SCREENSHOT_INDEX → ścieżki archiwum. Zakaz: zmian architektury, logiki aplikacji, startu Etapu 0 i płatnych runów.
- **Jaki był efekt:** jeden spójny kanon bez konstrukcji „plik odwołuje sam siebie"; kolejność Etapu 0 jednoznaczna; commit dokumentacyjny dopiero po tych korektach.
- **Czas człowieka:** ~15 min (review + decyzja).
- **Wpływ na strategię:** tak — potwierdzone: koniec debaty architektonicznej; następny krok = zadanie 1 Etapu 0 (bez pytania kolejnych modeli o nową architekturę, chyba że problem wymaga zmiany ADR).

### [2026-07-12] APPROVAL — Etap 0 / Task 1 zatwierdzony po drugim code review
- **Typ:** APPROVAL
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** Etap 0 / Task 1 — `research_runs.flow` i bezpieczne resume
- **Co agent chciał zrobić:** zamknąć Task 1 po poprawieniu findingów pierwszego review i opublikować zmiany na branchu developerskim.
- **Dlaczego człowiek zareagował:** commit i push wymagały jawnego zatwierdzenia końcowego zakresu po drugim, niezależnym review.
- **Co zostało zmienione:** właściciel zaakceptował wynik `APPROVE` i polecił commit `Add explicit research run flow and safe resume validation` oraz push wyłącznie na `origin/dev/first-successful-research-card`; Task 2 pozostaje nierozpoczęty.
- **Jaki był efekt:** Task 1 dopuszczony do commita i pushu; bez zgody na API, Playwrighta, realny research ani kolejne zadania roadmapy.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** brak zmiany architektury; formalne zamknięcie Task 1 i utrzymanie kolejności roadmapy.

### [2026-07-12] APPROVAL — wykonanie Etapu 0 / Task 2
- **Typ:** APPROVAL
- **Konto:** — (dotyczy całego projektu)
- **Obiekt:** spójność `runs.cost_usd` z `model_usage` oraz SQLite WAL/busy timeout
- **Co agent chciał zrobić:** naprawić cache kosztu staged i ustawić centralne parametry połączenia SQLite, nie rozpoczynając zadania 3.
- **Dlaczego człowiek zareagował:** po zatwierdzeniu Task 1 właściciel dopuścił dokładnie następne zadanie roadmapy, zachowując zakaz API, Playwrighta i realnego researchu.
- **Co zostało zmienione:** właściciel polecił synchronizację z istniejącego `get_research_usage`, WAL i `busy_timeout=5000`, z testami wszystkich ścieżek staged; nie udzielił zgody na Task 3–9.
- **Jaki był efekt:** Task 2 wykonano offline; kanon kosztu pozostał `model_usage`, a cache `runs.cost_usd` jest odświeżany bez podwójnego doliczania.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** brak zmiany ADR; utrzymano kolejność Etapu 0 i warunek osobnej zgody na realny run.

### [2026-07-12] APPROVAL — wykonanie wyłącznie Etapu 0 / Task 3
- **Typ:** APPROVAL
- **Konto:** — (cały projekt)
- **Obiekt:** capowany retry `EXTRACTION_FAILED`, migracja 0007 i `PARTIAL_EXHAUSTED`.
- **Co agent chciał zrobić:** odblokować bezpieczną, ręcznie inicjowaną drogę dla historycznego PARTIAL bez wznawiania go ani wykonywania API.
- **Dlaczego człowiek zareagował:** retry może prowadzić do przyszłego kosztu, więc właściciel wymagał jawnej komendy, capu, testów i pozostawienia working tree do review.
- **Co zostało zmienione:** zatwierdzono wyłącznie Task 3; zakazano Task 4+, API, realnego researchu, Playwrighta, commita, pushu i zmiany produkcyjnej bazy.
- **Jaki był efekt:** implementacja resetuje tylko eligible failed i sam reset kosztuje 0 USD; żaden realny run nie został zmieniony.

### [2026-07-12] APPROVAL — poprawki P1/P2 po niezależnym review Task 3
- **Typ:** APPROVAL
- **Konto:** — (cały projekt)
- **Obiekt:** wyłącznie findings review dla attempts, claimu A2, `PARTIAL_EXHAUSTED`, migracji/ledgeru, izolacji kont i wpisu screenshot.
- **Co agent miał zrobić:** poprawić implementację Task 3 oraz regresje bez uruchamiania retry na historycznym runie.
- **Co zostało zmienione:** właściciel rozszerzył autoryzację Task 3 o naprawę czterech P1 i bezpośrednio związanych P2; utrzymał zakaz API, researchu, Playwrighta, Task 4+, commita i pushu.
- **Jaki był efekt:** poprawki i testy wykonano offline; źródłowa baza nie została otwarta do migracji ani zmieniona.

### [2026-07-12] APPROVAL — wykonanie Etapu 0 / Task 4
- **Typ:** APPROVAL
- **Obiekt:** `topics.status=USED`, blokada świeżego researchu kompletnej karty i jawny `--force-re-research`.
- **Zakres decyzji właściciela:** wdrożyć dokładnie Task 4 z pełnymi regresjami, bez automatycznego płatnego ponowienia.
- **Efekt:** implementacja i testy wykonane offline; bez API, realnego researchu, zmian produkcyjnej bazy, commita lub pushu.

### [2026-07-12] APPROVAL — poprawki P1/P2 po review Task 4
- **Typ:** APPROVAL
- **Obiekt:** wyłącznie integralność card-topic-account, pełna atomowość finalizacji, pre-guard runnera, fail-closed i testy Task 4.
- **Zakres decyzji właściciela:** nie rozpoczynać Task 5, nie naprawiać race condition, nie wykonywać API ani commit/push.
- **Efekt:** poprawki wykonano offline; race zapisano jako P2 do przyszłego claimu/lease.

### [2026-07-12] APPROVAL — Etap 0 / Task 5, szczelny budżet retry
- **Typ:** APPROVAL
- **Obiekt:** centralny cap runu, retry techniczne i delegacja CLI.
- **Zakres decyzji właściciela:** wyłącznie Task 5; pełne testy offline; bez API, Task 6, zmian P2-17/P2-18, commita i pushu.
- **Efekt:** wdrożono ADR-026 i pozostawiono working tree do niezależnego review; koszt 0 USD.

### [2026-07-12] APPROVAL — review i natychmiastowa korekta P0/P1 Task 5
- **Typ:** APPROVAL
- **Zakres:** właściciel polecił nie kończyć na REJECT, poprawić wszystkie P0/P1, dodać regresje i pozostawić zmiany bez commita/pushu.
- **Efekt:** pięć P1 poprawiono offline; P2-17/P2-18 i Task 6 pozostały nietknięte.

### [2026-07-12] APPROVAL — Etap 0 / Task 6, wyrównanie klienta tematów
- **Typ:** APPROVAL
- **Obiekt:** parser odpowiedzi tematów, typowane błędy i księgowanie usage po parse-error.
- **Zakres decyzji właściciela:** implementacja, testy, self-review i poprawa wszystkich P0/P1; wyłącznie offline, bez API, realnego generowania tematów, researchu, Task 7, commita i pushu.
- **Efekt:** response→Usage→parse, ścisły code fence i trwały `FAILED` z kanonicznym kosztem; 286 testów, 0 USD; P2-17/P2-18/P2-19 bez zmian.

### [2026-07-12] APPROVAL — Etap 0 / Task 8, walidacja przejść stanów
- **Typ:** APPROVAL
- **Obiekt:** pełna inwentaryzacja i zabezpieczenie istniejących repozytoryjnych zmian statusu.
- **Zakres decyzji właściciela:** atomowy warunek statusu, `rowcount`, typowany błąd, testy illegal/race/reopen i self-review; bez Task 9, API, realnego researchu, Playwrighta, commita i pushu. P2-17/P2-18/P2-19 pozostają poza zakresem.
- **Efekt:** ADR-027, 44 nowe regresje i 330 testów offline; working tree pozostawiony do niezależnego review, koszt 0 USD.

### [2026-07-13] APPROVAL — Etap 0 / Task 9, dokładnie jeden realny run
- **Typ:** APPROVAL / PAID API
- **Obiekt:** pierwszy świeży staged run topic #2 według ADR-022.
- **Zakres decyzji właściciela:** dokładnie jedna komenda, cap maks. 0,55 USD, `max_retries=0`; bez drugiego runu, retry, resume, force, Playwrighta, publikacji i Etapu 1.
- **Efekt:** A1 i 4×A2 zakończone sukcesem; B zwróciło ucięty JSON przy `max_tokens`. Koszt 0,170050 USD. Polecenie zatrzymania po błędzie zachowano literalnie; nie wykonano żadnej dodatkowej płatnej akcji.

### 2026-07-13 — zgoda na wyłącznie offline naprawę blockerów Task 9

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres decyzji właściciela:** naprawić truncation B i fałszywe RUNNING, dodać testy i dokumentację; nie wykonywać API, resume, drugiego runu, retry failed candidates, force ani ręcznej mutacji realnej bazy.
- **Efekt:** kod i 351 testów offline gotowe do niezależnego review. Historyczny run, main i świat zewnętrzny pozostały bez zmian; kolejna operacja lifecycle oraz płatny resume wymagają osobnych zgód.

### [2026-07-13] APPROVAL — kontrolowana naprawa statusu historycznego runu Task 9
- **Typ:** APPROVAL / MAINTENANCE
- **Konto:** nothing_is_accidental
- **Obiekt:** run `c01171bc-7ff5-4b83-bbfa-c0b164137793`
- **Co agent chciał zrobić:** uzgodnić ogólny audit runu z faktem, że realny etap B zakończył się `stop_reason=max_tokens` i błędem parsowania uciętego JSON.
- **Dlaczego człowiek zareagował:** mutacja historycznej bazy wymaga osobnej, jawnej zgody oraz ścisłych preconditions i dowodu niezmienności opłaconych danych.
- **Co zostało zmienione:** właściciel dopuścił wyłącznie lokalne `RUNNING → FAILED`, ustawienie `finished_at` i audytowalnego `error`; zakazał API, resume, retry, A1, A2, B i zmian kosztu. Operacja warunkowa zmieniła dokładnie jeden rekord (`rowcount=1`).
- **Jaki był efekt:** `research_runs=SOURCES_COMPLETE`, topic `SELECTED`, 4× EXTRACTED/VERIFIED, sześć wpisów usage i koszt 0,170050 USD pozostały bez zmian; run jest gotowy wyłącznie do osobno zatwierdzonego resume B. Dodatkowy koszt: 0 USD.
- **Czas człowieka:** niezmierzony (instrukcja tekstowa).
- **Wpływ na strategię:** brak zmiany architektury; jest to kontrolowana korekta auditu historycznego.

### [2026-07-13] APPROVAL / PAID API — dokładnie jeden resume wyłącznie B
- **Typ:** APPROVAL / PAID API
- **Konto:** nothing_is_accidental
- **Obiekt:** run `c01171bc-7ff5-4b83-bbfa-c0b164137793`, topic #2
- **Zakres zgody:** dokładnie jeden realny call syntezy B przez oficjalny kontrakt resume, `synthesize_max_tokens=3000`, `max_retries=0`, absolutny cap całego runu 0,20 USD.
- **Zakazy:** bez nowego runu, A1/A2, discovery/extraction, retry, force, drugiego B, Playwrighta, publikacji i Etapu 1.
- **Efekt:** PolicyEngine dopuścił projekcję 0,196300 USD; call zakończył `end_turn`, kosztował 0,013914 USD i utworzył kartę #2. Finalny koszt runu 0,183964 USD; COMPLETE/SUCCESS/USED, 4 VERIFIED. Karta ma jakościowe REJECT i nie przechodzi do treści. Etap 0 formalnie zakończony.
- **Czas człowieka:** niezmierzony (jawna instrukcja tekstowa).
- **Wpływ na strategię:** spełniono bramkę przejścia roadmapy; nie jest to zgoda na rozpoczęcie Etapu 1.

### [2026-07-13] APPROVAL — pierwszy blocker przygotowawczy Etapu 1

- **Typ:** APPROVAL / IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Obiekt:** typowane mapowanie błędów Anthropic i polityka retry research clienta.
- **Zakres decyzji właściciela:** wolno zmienić kontrakt błędów, retry, testy i dokumentację; każda próba ma nadal przechodzić budget callback. Nie wolno naprawiać P2-19 przez sztuczny koszt.
- **Zakazy:** bez API, researchu, resume, retry realnego calla, schedulera, jobs, workerów, budżetowych rezerwacji, commita i pushu przed niezależnym review.
- **Efekt:** 382 testy offline; typed/fail-closed mapping gotowy do review, scheduler/jobs/workery nadal NOT_STARTED, koszt 0 USD.

### [2026-07-13] APPROVAL — naprawa F4 atomowej finalizacji staged B

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres zgody właściciela:** zmienić wyłącznie storage/workflow/testy/dokumentację, aby karta B i lifecycle były atomowe; dodać rollback, idempotencję, reopen i współbieżność SQLite.
- **Zakazy:** bez API, realnego researchu, resume, schedulerów, jobs, workerów, rezerwacji budżetowych, migracji, commita, pushu, PR i merge.
- **Efekt:** helper transakcyjny i 420 testów offline; historyczna baza i świat zewnętrzny bez zmian, dodatkowy koszt 0 USD. Zmiana oczekuje na niezależne review.

### [2026-07-13] APPROVAL — trzy lokalne poprawki P1 do F4

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Obiekt:** typowany context finalizacji staged B, trwałe force i macierz crash/reopen.
- **Zakres decyzji właściciela:** usunąć luźne booleany force/resume, w razie potrzeby dodać minimalną migrację trwałego markera, wykonać preflight przed B i pełne testy rollback po reopen. Pozostawić zmiany do kolejnego niezależnego review.
- **Zakazy:** bez Anthropic API, realnego researchu/resume, schedulera, jobs, workerów, rezerwacji budżetowych, zmian historycznej bazy, commita, pushu, PR i merge.
- **Efekt:** `0008` dodaje marker force per staged run; CAS resume i 13 crash points przeszły offline. 446 testów, dodatkowy koszt 0 USD; brak zewnętrznych działań.

### [2026-07-13] APPROVAL — końcowy P1 F4: mode przed terminalnym no-op

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres decyzji właściciela:** naprawić wyłącznie akceptację sprzecznego `StagedFinalizationContext` przez COMPLETE/no-op i dodać powiązane testy; wolno doprecyzować trwały snapshot B FAILED bez migracji.
- **Zakazy:** bez API, realnego researchu/resume, zmian historycznej bazy, schedulerów, jobs, workerów, rezerwacji budżetowych, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** mode, marker force i CAS resume są walidowane przed no-op; 449 testów offline, koszt 0 USD. Zmiany oczekują na niezależne review.
