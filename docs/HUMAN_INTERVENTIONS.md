# HUMAN_INTERVENTIONS

## [2026-07-16] Właściciel formalnie zamknął WAVE 1A po niezależnym `APPROVE WITH MINOR/P2`

- **Stan wejściowy:** implementer po systemowej naprawie `W1A-R4-01` zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; nie miał uprawnienia do zamknięcia WAVE.
- **Niezależny wynik:** reviewer odtworzył 1036 collected i 1036/1036 passed, cztery partycje exact-once, `compileall` i `git diff --check`; dodatkowo wykonał 149/149 własnych kontrprób przez prawdziwy `Worker.run_once`, 36/36 sprawdzeń SQLite floor oraz 30/30 recovery/reaper/crash-window. Nie stwierdził osiągalnego MAJOR ani CRITICAL i wydał `APPROVE WITH MINOR/P2` z rekomendacją zamknięcia WAVE.
- **Formalna decyzja człowieka:** właściciel ustawił WAVE 1A na `CLOSED — APPROVED WITH P2` z datą 2026-07-16. To decyzja właściciela następująca po niezależnym review, nie samopotwierdzenie implementera.
- **Pozostające P2:** P2-1 zachowuje fail-closed fingerprint mismatch, widoczność operatora, brak przepisywania intentu, retry i attemptu #2. P2-2 uznaje atomowość StoragePort i spójny trwały floor SQLite, ale nie przypisuje SQLite dowodu pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel.
- **Granica decyzji:** zamknięcie WAVE 1A nie zamyka Etapu 1, nie odblokowuje live API i nie rozpoczyna Etapu 2. Etap 1 pozostaje `BLOCKED`; live API pozostaje `ZABRONIONE`.

## [2026-07-16] Właściciel przekazał CZWARTY niezależny `REJECTED — MAJOR` i autoryzował `W1A-R4-01`

- **Zakres i decyzja człowieka:** odtworzyć kontrpróbę przez prawdziwy `Worker.run_once`, zmapować wszystkie terminalne ścieżki job/run/research_run, naprawić systemowo każde workerowe failure boundary i dodać defense-in-depth w SQLite. Bez pytania o dodatkową zgodę dozwolona była pełna fala napraw oraz dokumentacji.
- **Twarde warunki:** attempt `RESERVED`/`REQUEST_STARTED` po lokalnej awarii ma trafić do widocznego `NEEDS_RECONCILIATION` z zachowaną rezerwacją, bez retry, attemptu #2 i providera; brak attemptu ma zachować zwykłe `FAILED`; istniejące reconciliation ma być idempotentne. Obowiązkowe były testy reopen/recovery/reaper/resolver/budżetu/raw SQLite/concurrency i niezależna próba obalenia.
- **Zakazy człowieka:** zero sieci/DNS/socketów/API/SDK/browsera/publikacji/kosztu; tylko fake i temp DB; bez zapisu do `data/agent.db`; bez stage/commit/push/PR/merge i innych zakazanych operacji Git; `docs/BUILD_LOG.md` oraz `instrukcja dla pisania artykulow/` nietykane. Zakaz zamykania WAVE, odblokowania Etapu 1 i live API.
- **Efekt offline:** centralna atomowa operacja StoragePort, wszystkie workerowe ścieżki przełączone na nią, trzy lifecycle guardy SQLite i +29 trwałych testów. Suite 1036/1036; partycje 248+253+267+268; concurrency 38×30; krytyczne pliki ×10; QA ×10; E2E Worker w 10 świeżych procesach; 0 USD i chroniona baza niezmieniona. Status: `WAVE 1A — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; WAVE nadal otwarta, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Szczegóły: ADR-067.

## [2026-07-16] Właściciel przekazał TRZECI niezależny `REJECTED — MAJOR` i autoryzował pełną falę naprawczą

- **Zakres i decyzja człowieka:** naprawić w jednej spójnej fali wszystkie potwierdzone findingi trzeciego review: W1A-AUD-04 jako MAJOR BLOCKING (eskalacja crash-window `RESERVED`/`REQUEST_STARTED` z martwym lease do `NEEDS_RECONCILIATION` z trwałym powodem i audytem, widoczna dla operatora, bez retry/attemptu #2/providera), W1A-SQLITE-01 (pełna atomowość terminalizacji na poziomie SQLite: event `FINAL_RESOLUTION` + terminalny lifecycle + zwolniona rezerwacja + zgodne cache, attempt flipowany jako ostatnia mutacja), W1A-SQLITE-02 (niezmienność kanonicznego `model_usage` i zamrożenie cache po terminalu), pełne W1A-AUD-01 (błędy query/close w CLI), W1A-DOC-01 (sweep baseline'ów) i W1A-QA-01 (cleanup QA). Migracja 0014 in-place, bez 0015. Obowiązkowe testy crash/recovery (20) i raw-SQLite (20), powtórzenia 30×/10×, drugi pełny audyt. Zakaz zamykania WAVE, APPROVE, odblokowania Etapu 1 i live API.
- **Zakazy:** zero sieci/DNS/socketów/API/SDK/browsera/publikacji/kosztu; tylko fake SDK i tymczasowe bazy; brak zapisu do `data/agent.db`; brak stage/commit/push/PR/merge; `docs/BUILD_LOG.md` i `instrukcja dla pisania artykulow/` nietykane.
- **Efekt offline:** wszystkie trzy MAJOR + trzy mniejsze naprawione defense-in-depth (aplikacja + triggery 0014 + testy); +25 trwałych testów, licznik **982 → 1007**, suite 1007/1007, partycje 4/4, concurrency 33×30, pliki 10/10, QA 10/10 bez pozostałości, kontrpróby 5/5, chroniona baza byte-identical. Szczegóły: ADR-066 i `docs/ERRORS_AND_FAILURES.md` (wpis 2026-07-16). WAVE 1A = `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## [2026-07-16] Właściciel zlecił pełny audyt software-assurance całego working tree z autoryzacją jednej fali napraw

- **Zakres i decyzja człowieka:** pełny read-only audit HEAD `c25e125` oraz wszystkich niecommitowanych zmian (nie tylko `W1A-VERIFY-02`/resolvera), z niezależną weryfikacją każdej deklaracji poprzedniego implementera (980 testów, 14 migracji, partycje, concurrency, QA, chroniona baza) i regresji wszystkich wcześniejszych findingów. Po pełnej fazie audytowej autoryzowana natychmiastowa naprawa wszystkich potwierdzonych problemów w jednej skonsolidowanej fali, bez pytania o dodatkową zgodę. Zakaz zamykania WAVE 1A, odblokowania Etapu 1 i autoryzacji live API.
- **Zakazy:** zero sieci/DNS/socketów/realnego API/SDK/browsera/publikacji/kosztu; tylko fake SDK i tymczasowe bazy; brak zapisu do `data/agent.db`; brak stage/commit/push/PR/merge; bez otwierania `docs/BUILD_LOG.md` i katalogu `instrukcja dla pisania artykulow/`.
- **Wynik:** wszystkie deklaracje implementera potwierdzone (w tym 980/980 przed naprawami); zero MAJOR/CRITICAL; trzy MINOR naprawione (W1A-AUD-01…03), jeden P2 report-only (W1A-AUD-04, styczne do P2-19 — decyzja właściciela wymagana dla rozszerzenia kontraktu resolvera); licznik testów **980 → 982**; chroniona baza byte-identical. Szczegóły: `docs/ERRORS_AND_FAILURES.md` (wpis 2026-07-16). WAVE 1A pozostaje `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## [2026-07-15] Właściciel autoryzował wyłącznie naprawę `W1A-VERIFY-02` (pełna walidacja lineage)

- **Zakres i decyzja człowieka:** po drugim niezależnym review (`REJECTED — MAJOR`) naprawić **tylko** finding `W1A-VERIFY-02` — resolver musi przed jakąkolwiek mutacją zweryfikować pełną, jednoznaczną relację `provider_attempt → job → run → research_run → account → workflow → topic → durable intent`.  Nie zmieniać semantyki `RESULT_ALREADY_FINALIZED`, kontraktu finansowego ani zakresu WAVE 1A.
- **Twarde inwarianty (potwierdzone testami):** każda niespójność lineage ⇒ fail-closed bez mutacji attemptu/joba/runu/research_runu/rezerwacji/usage/eventu, bez retry/attemptu #2/providera.
- **Naprawa (defense-in-depth):** warstwa aplikacji (`_reconciliation_require_consistent_lineage`) + version token v2 (wszystkie pola lineage) + trigger SQLite `provider_attempts_reconcile_requires_consistent_lineage` (0014 in-place).  Trwałe dowody w repo: `tests/test_reconciliation_lineage.py` i `scripts/qa/reconciliation_lineage_disproof.py`.
- **Zakazy:** brak sieci, API, SDK, browsera, publikacji, kosztu, zmiany `data/agent.db`, stagingu, commita, pushu, PR i merge.
- **Efekt offline:** licznik **955 → 980**, suite 980/980, 4 partycje exact-once, concurrency 30/30, lineage disproof 10/10, chroniona baza niezmieniona.  WAVE 1A pozostaje `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.  Szczegóły: ADR-065.

## [2026-07-15] Właściciel autoryzował wyłącznie naprawę `W1A-VERIFY-01` (resolver vs reaper STOPPED)

- **Zakres i decyzja człowieka:** naprawić **tylko** finding `W1A-VERIFY-01` — resolver `EXECUTION_FAILED` ma umożliwić rozstrzygnięcie osieroconego runu `STOPPED → FAILED` w istniejącej atomowej operacji reconciliation. Nie zmieniać semantyki `RESULT_ALREADY_FINALIZED`, kontraktu finansowego ani zakresu WAVE 1A.
- **Twarde inwarianty (potwierdzone testami):** obsługa `STOPPED` nie wskrzesza runu, nie ustawia `RUNNING`, nie robi requeue/retry/attemptu #2, nie woła providera, nie usuwa historii reaper/maintenance, nie pozwala na `DONE`, nie omija version tokenu, nie osłabia CAS, nie akceptuje sukcesowego run/research_run ani cudzego joba/konta.
- **Zakazy:** brak sieci, API, SDK, browsera, publikacji, kosztu, zmiany `data/agent.db`, stagingu, commita, pushu, PR i merge.
- **Efekt offline:** dodano `_EXECUTION_FAILED_RUN_STATUSES` (wspólne źródło warunku i CAS) + 7 deterministycznych testów; flaky node **30/30**, plik **10/10**, pełny suite **955**, 20/20 kontrprób BLOCKED, chroniona baza niezmieniona. WAVE 1A pozostaje `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`. Szczegóły: ADR-064.

## [2026-07-15] Właściciel zlecił WAVE 1A — resolver operatorski L1

- **Zakres i decyzja człowieka:** wdrożyć wyłącznie lokalne, audytowalne reconciliation `NEEDS_RECONCILIATION` / `NEEDS_VERIFICATION`; rozdzielić koszt od wyniku pipeline'u i nie tworzyć drugiego ledgeru.
- **Zakazy:** brak API, sieci, SDK providera, retry, attemptu #2, resume, browsera, publikacji, kosztu, modyfikacji `data/agent.db`, stagingu, commita, pushu, PR i merge.
- **Efekt offline:** WAVE 0B jest formalnie `CLOSED — APPROVED WITH P2`; WAVE 1A jest kandydatem do niezależnego review. Resolver wymaga jawnego operatora, notatki i `--confirm`; podgląd (preview) jest tylko-do-odczytu i zwraca version token. Po naprawie odrzucenia `REJECTED — MAJOR` (append-only `reconciliation_events`, pełna tożsamość usage, wyłączna własność karty, brak dead-endu `MANUAL`, spójność ledger↔cache): **955 testów**, 14 migracji, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Historyczne 919/894 to wartości wcześniejszych iteracji.

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

### [2026-07-13] APPROVAL — Etap 1, wyłącznie foundation kolejki

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres decyzji właściciela:** zbudować `0009`, modele/port/repozytorium jobs, lease/recovery/idempotency, blokadę research per topic, runtime storage flags i globalną rezerwację budżetu wraz z testami offline.
- **Zakazy:** bez worker loopa, schedulera runtime, API, realnego researchu/resume, migracji historycznej bazy, publikacji/Playwrighta, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** storage foundation wdrożona offline; worker i runtime PolicyEngine flags pozostają nierozpoczęte. 463 testy, koszt 0 USD.

### [2026-07-13] APPROVAL — minimalny worker Etapu 1, tylko offline

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres decyzji właściciela:** dodać pojedynczy worker, jawny dispatcher, runtime PolicyEngine/system_flags, CLI `worker --once`, recovery i testy; wolno zintegrować wyłącznie istniejący dry-run research pipeline oraz trwałe wiązanie job→run.
- **Zakazy:** bez Anthropic API, sieci, realnego researchu/resume, `data/agent.db`, publikacji, Playwrighta, browser/public actions, paid actions, reapera runs, migracji, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** LOCAL noop i RESEARCH `dry_run=true` są zweryfikowane offline; runtime flags fail-closed i CAS lease chronią lifecycle. Live API pozostaje NOT VERIFIED, paid/browser BLOCKED, reaper NOT_STARTED. Pełny suite 489 testów, koszt 0 USD.

### [2026-07-13] APPROVAL — uszczelnienie relation/CAS i recovery przypiętego research runu

- **Typ:** IMPLEMENTATION BOUNDARY / NO EXTERNAL ACTION.
- **Zakres decyzji właściciela:** usztywnić `attach_job_run` po account/topic/workflow/research_runs oraz zatrzymać po expiry RESEARCH z istniejącym `run_id` w NEEDS_VERIFICATION; wolno dodać testy offline i minimalne typowane błędy.
- **Zakazy:** bez reapera `runs`, realnego resume, Anthropic API, sieci, realnego researchu, `data/agent.db`, migracji, paid/browser workera, publikacji, Playwrighta, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** przypięty run jest trwały i nie może być zastąpiony runem innego account/topic/workflow/flow. RESEARCH bez `run_id` nadal może wrócić do QUEUED, lecz z `run_id` zachowuje rezerwację i trafia fail-closed do NEEDS_VERIFICATION; worker go nie uruchamia ponownie. Pełny suite 512 testów, koszt 0 USD.

### [2026-07-13] APPROVAL — jawny stale reaper runów i sanitacja audit error

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Zakres decyzji właściciela:** dodać atomowy reaper `RUNNING→STOPPED` po recovery joba, bezpieczną komendę `reap-runs --once`, testy SQLite/Barrier oraz zawężoną sanitację `JobRunRelationError`.
- **Zakazy:** bez API, sieci, realnego researchu/resume, `data/agent.db`, migracji, workera paid/browser, publikacji, Playwrighta, schedulera cyklicznego, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** tylko stale run bez joba `QUEUED/LEASED/RUNNING` może przejść do STOPPED; po expiry RESEARCH z `run_id` zostaje NEEDS_VERIFICATION, rezerwacja pozostaje, a reaper nie daje dispatchu/resume. Pełny suite 529 testów, koszt 0 USD.

### [2026-07-13] APPROVAL — okresowy heartbeat wyłącznie dla długiego dispatchu offline

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Zakres decyzji właściciela:** dodać bezpieczny okresowy guard heartbeat oparty na istniejącym `heartbeat_job_lease`, z osobnym połączeniem SQLite, kontrolowanym zakończeniem wątku oraz deterministycznymi testami utraty lease i współbieżności.
- **Zakazy:** bez nowej migracji lub implementacji lease, retry dispatchu, API, sieci, realnego researchu/resume, `data/agent.db`, paid/browser workera, schedulerów cyklicznych, okien redakcyjnych, commita, pushu, PR i merge; instrukcja pisania poza zakresem.
- **Efekt:** guard działa tylko w LOCAL/RESEARCH `dry_run`, zawsze jest joinowany i blokuje `DONE` po utracie lease/błędzie guarda. Pełny suite 548 testów, koszt 0 USD.
- **Korekta P1:** guard jest daemonem wyłącznie jako osłona procesu; worker zawsze podejmuje stop event, `wake`, bounded join i kontrolę `is_alive()`. Timeout nie daje prawa do `DONE`, a po odblokowaniu guard widzi stop event przed kolejnym heartbeat. Aktualny wynik: 15 pierwotnych testów periodic heartbeat + 11 testów bounded lifecycle/P1 = 26; `test_worker_runtime.py` 59 passed, pełny suite 566 passed, koszt 0 USD.

### [2026-07-13] APPROVAL — osobna offline maintenance loop Etapu 1

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Zakres decyzji właściciela:** dodać oddzielny runner maintenance i CLI `maintain --once/--poll`, który zawsze robi recovery wygasłych lease przed stale-run reaperem, z osobnym połączeniem SQLite na cykl, walidacją progów, jawnym stopem i testami współbieżności/fail-closed.
- **Zakazy:** bez claimu jobów, dispatchu, workera, researchu, resume, API, sieci, paid/browser/public action, okien redakcyjnych, cron/service/autostartu, migracji, zmian `data/agent.db`, commita, pushu, PR i merge; instrukcje pisania poza zakresem.
- **Efekt:** one-shot i poll są zweryfikowane offline. Błąd factory/recovery/reapera/close/waitera zatrzymuje poll; przy podwójnym błędzie recovery/reapera + `close()` pierwszeństwo diagnostyczne ma operation error, a cleanup error pozostaje zachowany. Równoległe runnery używają istniejących transakcji SQLite/CAS. Usługa schedulera systemowego i okna redakcyjne pozostają NOT_STARTED, realne resume NOT IMPLEMENTED, live API NOT VERIFIED, paid/browser/public BLOCKED. 26 testów maintenance, pełny suite 592 passed, koszt 0 USD.

### [2026-07-13] APPROVAL — deterministyczne okna redakcyjne przed enqueue Etapu 1

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Zakres decyzji właściciela:** dodać czystą politykę harmonogramu dla istniejących `earliest_run_at` i `schedule_reason`, centralny enqueue, eligibility claimu, dry-run CLI oraz testy IANA/DST, restartu, idempotencji i współbieżności SQLite.
- **Zakazy:** bez API, sieci, realnego researchu, dispatchu, workera paid/browser/public, realnego resume, usługi systemowego schedulera, zmian `data/agent.db`, migracji, `docs/BUILD_LOG.md`, instrukcji pisania, commita, pushu, PR i merge.
- **Efekt:** `SchedulingPolicy` wyznacza lokalne okno z jawnej strefy IANA, przechowuje UTC `earliest_run_at` i zamknięty `schedule_reason`; future job pozostaje bez lease/attempt, a `enqueue-research` tworzy tylko RESEARCH `dry_run`. 31 testów scheduling, pełny suite 623 test cases passed, hash `data/agent.db` bez zmiany, koszt 0 USD.

### [2026-07-13] APPROVAL — naprawa P1 atomowej inicjalizacji RESEARCH i końcowy restart acceptance

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Zakres decyzji właściciela:** naprawić wykryty P1 między utworzeniem `run`/`research_run` a `jobs.run_id`; wolno dodać jedną atomową operację StoragePort, zmienić wyłącznie ścieżkę RESEARCH workera, zachować test acceptance i dopisać failpointy/reopen/concurrency oraz dokumentację.
- **Zakazy:** bez migracji i bez zmiany `data/agent.db`; bez adopcji lub kasowania historycznych sierot, API, sieci, realnego researchu, browsera, publikacji, paid actions, commita, pushu, PR i merge. `docs/BUILD_LOG.md` oraz katalog instrukcji pisania pozostają poza zakresem.
- **Efekt:** `initialize_research_run_for_job` łączy run, research_run i CAS `job.run_id` w jednym `BEGIN IMMEDIATE`; pre-commit crash rollbackuje komplet, post-commit crash zachowuje jeden komplet i recovery wybiera NEEDS_VERIFICATION. 14 scenariuszy restart acceptance oraz pełny suite 655 passed, realny koszt 0 USD, hash prawdziwej bazy bez zmiany. Etap 1: candidate complete, awaiting independent review.
## [2026-07-13] Właściciel ponownie zablokował Etap 1 po niezależnym review old-owner fencing

- **Typ:** korekta bezpieczeństwa P1 i decyzja o granicy zakresu.
- **Decyzja człowieka:** zachować atomową inicjalizację ADR-044, ale cofnąć status Etapu 1 do `BLOCKED — old-owner research fencing P1`, dopóki każda późniejsza mutacja pipeline’u nie będzie sprawdzać aktualnego lease w SQLite. Zakazano commita/pushu, API, browsera, publikacji i realnego researchu; wymagano literalnej macierzy old-owner, race i ponownego niezależnego review.
- **Wpływ na implementację:** dodano zamknięty `JobExecutionContext`, worker-only fenced API oraz `StaleJobExecutionError`; manualne pipeline’y bez joba pozostały oddzielne. Dodatkowe P2 objęły primary-vs-rollback, walidację `created=False`, failpoint po CAS i canonical UTC.
- **Wynik:** 26 acceptance tests i pełny suite 667 passed offline; po testach status przywrócono wyłącznie do `candidate complete, awaiting independent review`, nie do formalnie ukończonego. `data/agent.db` niezmieniona, koszt 0 USD.

## [2026-07-13] Właściciel zlecił naprawę trzech P1 końcowego review Etapu 1

- **Typ:** korekta bezpieczeństwa P1 / OFFLINE ONLY.
- **Zakres decyzji właściciela:** pobierać czas lifecycle dopiero po write locku, potraktować `COSTS.csv` jako pochodny eksport odporny na błąd oraz atomowo zamknąć job/run/research_run po nieoczekiwanym błędzie pipeline’u. Wymagane były deterministyczne testy z realnymi wątkami i plikową SQLite, reopen/integrity oraz matrix expiry.
- **Zakazy:** bez API, sieci, browsera, publikacji, działań paid, retry kosztownych/publikujących, migracji, zmian `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik:** ADR-046; 42 acceptance i pełny suite 683 passed offline. Etap 1 wrócił wyłącznie do `candidate complete, awaiting independent review`; koszt 0 USD, hash prawdziwej bazy bez zmiany.

## [2026-07-14] Właściciel zlecił naprawę ostatniego potwierdzonego P1 terminalizacji po dispatchu

- **Typ:** korekta bezpieczeństwa P1 / OFFLINE ONLY.
- **Zakres decyzji właściciela:** sukces jobowego RESEARCH ma atomowo zapisać także `jobs=DONE`; dispatcher ma przekazać jawny wynik terminalizacji, a worker nie może wykonać heartbeat, generic completion ani generic failure po trwałym sukcesie workflow. Wymagane były literalny czerwony repro, failpointy success/failure, matrix expiry, delayed claim, prawdziwy błąd katalogu CSV i ponowne niezależne review.
- **Zakazy:** bez API, sieci, browsera, publikacji, działań paid, retry kosztownych/publikujących, migracji, zmian `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik:** ADR-047; 53 acceptance, runtime 60 i pełny suite 695 passed offline. Etap 1 jest wyłącznie `candidate complete, awaiting independent review`; koszt 0 USD, hash prawdziwej bazy bez zmiany.

## [2026-07-14] Właściciel zlecił naprawę kontraktu terminalizacji DispatchResult

- **Typ:** korekta bezpieczeństwa P1/P2 / OFFLINE ONLY.
- **Decyzja człowieka:** zamknąć kontrakt trzech trybów terminalizacji, usunąć implicit default, odrzucać malformed wynik bez canonical write i udowodnić to po rzeczywistym atomic success/failure. Dodać kontrolę pojedynczego INSERT karty i źródeł oraz test primary-vs-rollback dla sukcesu.
- **Zakazy:** bez API, sieci, browsera, publikacji, paid actions, realnego researchu, migracji, zmiany `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik:** ADR-048; status podczas naprawy `BLOCKED — DispatchResult terminalization contract P1`, po zielonej macierzy `candidate complete, awaiting independent review`. 58 acceptance, runtime 60 i pełny suite 700 passed offline; koszt 0 USD, hash prawdziwej bazy bez zmiany.

## [2026-07-14] Zlecenie WAVE 0B — durable real-provider boundary

- **Typ:** IMPLEMENTATION BOUNDARY / OFFLINE ONLY.
- **Decyzja człowieka:** dodać stabilny request_id, durable enqueue z operation-key, atomową per-request rezerwację i fail-closed reconciliation; usunąć fresh real bypass joba/lease/fence, zachowując istniejące resume poza nową ścieżką.
- **Zakazy:** bez API, sieci, browsera, publikacji, kosztu, pełnego realnego resume, WAVE 1A/1B, modyfikacji `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik:** `0010_provider_attempts`, request-bound usage i single durable worker path są zaimplementowane oraz przetestowane offline. `data/agent.db` pozostaje na SHA `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`. **`WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`**; Etap 1 nie jest zamknięty.

## [2026-07-14] Zlecenie WAVE 0B.1 — naprawa trzech P1 z niezależnego review

- **Typ:** korekta bezpieczeństwa P1 z bezpośrednio sprzężonymi P2 / OFFLINE ONLY.
- **Decyzja człowieka:** naprawić wyłącznie świeży bypass realnego two-stage/staged, globalną tożsamość `operation_key` i constraints/state machine `provider_attempts`/`model_usage`; nie rozpoczynać WAVE 1A ani pełnej reconciliation.
- **Zakazy:** bez API, sieci, browsera, publikacji, kosztu, migracji lub zapisu `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik:** `0011_provider_attempt_invariants`, globalny atomowy enqueue i fail-closed real-provider gate są gotowe offline. Status: **`WAVE 0B.1 CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`**; Etap 1 nie jest zamknięty.

## [2026-07-14] Zlecenie WAVE 0B.2 po drugim niezależnym REJECT

- **Decyzja człowieka:** naprawić wyłącznie P1-01/P1-02/P1-03 oraz bezpośrednio sprzężone P2; dodać 0012, ale nie zmieniać 0010/0011.
- **Zakazy:** bez WAVE 1A, pełnej reconciliation, API, sieci, browsera, publikacji, kosztu, `data/agent.db`, commita, pushu, PR i merge.
- **Wynik historyczny:** kandydat WAVE 0B.2 został zastąpiony przez WAVE 0B.3; Etap 1 pozostaje BLOCKED.

## [2026-07-14] Zlecenie WAVE 0B.3 — dwa P1 z re-review WAVE 0B.2

- **Decyzja człowieka:** naprawić wyłącznie derived request identity i świeżą asercję lease; nie zmieniać intentu, migracji 0012, legacy usage, budżetu ani settlementu bez konieczności.
- **Zakazy:** bez WAVE 1A, API, sieci, browsera, publikacji, kosztu, zapisu `data/agent.db`, commita, pushu, PR, merge, `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Wynik roboczy:** `WAVE 0B.3 CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`; Etap 1 pozostaje BLOCKED, 770 testów offline i baseline bazy bez zmiany.

## [2026-07-15] Wynik niezależnego końcowego review WAVE 0B i zgoda na staging checkpointu

- **Decyzja człowieka / podstawa:** review wydał `APPROVE WITH MINOR/P2`: 894/894 testów, partycje 213/224/231/226, brak MAJOR i CRITICAL, zamknięte W0B-RR-01 oraz W0B-CLEAN-01, brak regresji W0B-REV-06 i niezmieniona chroniona baza.
- **Zakres:** przygotować tylko staging zatwierdzonego checkpointu WAVE 0B oraz niezależnie go sprawdzić. Rzeczywisty inwentarz wynosi 72 wpisy (50 modified, 1 deleted, 21 untracked).
- **Zakazy:** bez commita, pushu, PR, merge, API, sieci, browsera, kosztu, zmiany `data/agent.db` oraz stagingu `docs/BUILD_LOG.md` i katalogu instrukcji pisania.
- **Stan:** WAVE 0B = `APPROVED WITH P2 — READY FOR CHECKPOINT`, nie `CLOSED`; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## [2026-07-16] Zlecenie jednego skonsolidowanego pakietu końcowego Etapu 1

- **Decyzja człowieka:** nie otwierać ponownie WAVE 0A/0B/1A i nie przebudowywać durable provider lifecycle. Zrealizować minimalny Windows Task Scheduler, audyt attempts/timeout, read-only raport, copy-only plan migracji `0009→0014`, dwie poprawki F-02 oraz jedno zamknięte kryterium acceptance.
- **Granice:** zero sieci/DNS/socketów/API/real SDK/browsera/publikacji/kosztu; wyłącznie fake callery i tymczasowe bazy. Nie migrować ani nie zapisywać `data/agent.db`; nie otwierać `.env`; nie modyfikować `docs/BUILD_LOG.md` ani katalogu instrukcji pisania; bez stage/commit/push/PR/merge.
- **Decyzja o uprawnieniach:** przygotowanie konfiguracji Task Scheduler nie jest zgodą na rejestrację. Każde zadanie systemowe wymaga osobnej jawnej zgody. Copy-preflight nie jest zgodą na podmianę produkcyjnej bazy. Live test wymaga jeszcze osobnej zgody, twardego capu, jednego joba/requestu i `max_retries=0`.
- **Kryterium właściciela:** po pakiecie status może być wyłącznie `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; Etap 1 pozostaje otwarty/blokowany do review, kontrolowanego live acceptance i formalnej decyzji człowieka.

## [2026-07-16] Zlecenie skonsolidowanej poprawki procedury po pełnym rollbacku

- **Decyzja człowieka:** usunąć rozbieżność profilu flag, zastąpić błędny warunek sidecarów jednym kontraktem WAL/SHM, przygotować jeden opakowany executor in-place z quiesce, trzema bramkami świeżości, pełnym backupem/rehearsal/restore i kanonicznym migratorem oraz wykonać kontrpróby wyłącznie na bazach tymczasowych.
- **Wymagany profil:** `kill_switch=true`, `safe_mode=true`, `worker_enabled=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`.
- **Granice:** nie wykonywać drugiej migracji produkcyjnej, nie ustanawiać nowego baseline'u, nie uruchamiać live API, SDK, browsera, workera ani maintenance, nie rejestrować Windows Task Scheduler i nie wykonywać stage/commit/push/PR/merge. `docs/BUILD_LOG.md` pozostaje nietknięty.
- **Status:** narzędzie może otrzymać wyłącznie `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Druga próba wymaga nowej, osobnej zgody właściciela; Etap 1 nadal `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.
