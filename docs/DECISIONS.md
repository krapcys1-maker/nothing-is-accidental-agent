# DECISIONS (Architecture Decision Log)

### ADR-068: Formalne zamknięcie WAVE 1A po niezależnym finalnym re-review

- **Data:** 2026-07-16
- **Status:** ACCEPTED — decyzja właściciela; **`WAVE 1A = CLOSED — APPROVED WITH P2`**. WAVE 0A i WAVE 0B również pozostają `CLOSED — APPROVED WITH P2`. Etap 1 = `BLOCKED`; live API = `ZABRONIONE`; Etap 2 nie został rozpoczęty.
- **Rozdzielenie odpowiedzialności:** implementer po `W1A-R4-01` zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Niezależny reviewer odtworzył testy implementera, wykonał własne kontrpróby i wydał werdykt `APPROVE WITH MINOR/P2` z rekomendacją `WAVE 1A MAY BE CLOSED WITH MINOR/P2`. Formalną decyzję o zamknięciu podjął następnie właściciel; nie jest ona deklaracją implementera.
- **Niezależny dowód:** 1036 collected i 1036/1036 passed; cztery partycje exact-once; `compileall` exit 0; `git diff --check` exit 0; 149/149 własnych kontrprób przez prawdziwy `Worker.run_once`; 36/36 sprawdzeń SQLite floor; 30/30 sprawdzeń recovery/reaper/crash-window; zero osiągalnych MAJOR/CRITICAL; chroniona baza byte-identical; zero sieci, DNS, socketów, realnego SDK/API, browsera, publikacji i kosztu.
- **P2-1 — fingerprint mismatch durable intentu:** pozostaje fail-closed i widoczny operatorowi, z zachowaną rezerwacją, bez automatycznego przepisywania fingerprintu lub durable intentu, bez retry i attemptu #2. Może wymagać ręcznej decyzji właściciela; nie blokuje zamknięcia WAVE 1A.
- **P2-2 — granica SQLite:** StoragePort wykonuje resolver atomowo w jednej transakcji, a SQLite wymusza spójny trwały stan końcowy. SQLite nie dowodzi pochodzenia danych wobec arbitralnego uprzywilejowanego autora ręcznie modyfikującego wiele tabel. Jest to świadoma granica odpowiedzialności, nie blocker.
- **Granica decyzji:** zamknięcie WAVE 1A nie zamyka Etapu 1, nie odblokowuje paid execution ani live API i nie zezwala na rozpoczęcie Etapu 2.

### ADR-067: W1A-R4-01 — aktywny provider attempt musi zostać znormalizowany przed terminalizacją lifecycle

- **Data:** 2026-07-16
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline. **Status przekazany przez implementera:** `WAVE 1A — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Późniejszy niezależny werdykt i formalne zamknięcie właściciela zapisuje ADR-068. Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.
- **Kontekst:** czwarty niezależny review (`REJECTED — MAJOR`) odtworzył przez prawdziwy `Worker.run_once` trwały stan `job=FAILED` + `provider_attempt=REQUEST_STARTED` po lokalnym `sqlite3.OperationalError`. Attempt nie był widoczny w kolejce L1, recovery go nie eskalowało, resolver go odrzucał, a rezerwacja bezterminowo blokowała budżet. Przyczyną był fallback `_fail_unexpected_research_pipeline → fail_job_research_execution(..., terminalize_job=True)`, który terminalizował job/run/research_run bez odczytu aktywnego attemptu.
- **Decyzja:** jedyną semantyczną granicą failure dla przypiętego single research jest `StoragePort.fail_or_escalate_job_research_execution`, wykonywana w jednym `BEGIN IMMEDIATE`. Operacja rewaliduje relację job→run→research_run, lease i fence, odczytuje aktywny attempt oraz zwraca jawny wynik. Bez aktywnego attemptu zachowuje dotychczasowe `FAILED`. `RESERVED` atomowo przechodzi do `NEEDS_RECONCILIATION` z `UNEXPECTED_EXECUTION_FAILURE_BEFORE_REQUEST_STARTED`, append-only `AUTO_ESCALATION` (`NOT_CHARGED`) i jobem `NEEDS_VERIFICATION`. `REQUEST_STARTED` analogicznie używa `UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED` i `CHARGE_UNKNOWN`. Istniejący `NEEDS_RECONCILIATION` jest idempotentny i nie dostaje drugiego eventu. Rezerwacja pozostaje aktywna; nie ma retry, attemptu #2 ani provider calla. Kontrolowane `UncertainExternalEffectError` i błąd heartbeat po przypięciu runu używają tej samej operacji; brak attemptu może zostać zachowany jako `PRESERVED_NEEDS_VERIFICATION` bez fałszywego `FAILED`.
- **SQLite defense-in-depth:** migracja `0014` została poprawiona in place (bez 0015). Triggery blokują bezpośrednie `jobs→DONE/FAILED/CANCELLED`, `runs→SUCCESS/FAILED/STOPPED/DRY_RUN` i `research_runs→COMPLETE/FAILED`, gdy powiązany attempt nadal ma `RESERVED` albo `REQUEST_STARTED`. `NEEDS_RECONCILIATION` pozostaje dozwolone, więc legalny resolver nadal buduje spójny terminalny stan w swojej transakcji.
- **P2-1:** failure normalization nie przepisuje ani nie „naprawia” niespójnego durable intentu. Może bezpiecznie wystawić attempt do `NEEDS_RECONCILIATION`, zachowując rezerwację i payload/fingerprint; resolver nadal przelicza fingerprint i odmawia mutacji. Pełna naprawa P2-1 pozostaje backlogiem właściciela.
- **P2-2 — granica twierdzenia:** **StoragePort wykonuje resolver atomowo w jednej transakcji. SQLite wymusza spójny trwały stan końcowy. SQLite nie udowadnia pochodzenia wszystkich danych wobec arbitralnego uprzywilejowanego autora wielu tabel.** Triggery są floor stanu trwałego, nie dowodem, że każdy semantycznie poprawny stan powstał wyłącznie przez autoryzowaną operację aplikacji.
- **Weryfikacja:** +29 trwałych testów (`1007 → 1036`), prawdziwy `Worker.run_once` z fake dispatcherem/callerem i zero provider calli; `sqlite3.OperationalError`, `RuntimeError`, `OSError`, błąd mark-reconciliation i heartbeat; reopen, recovery, reaper, resolver, preview/stale token, oba terminalne rozstrzygnięcia, `CHARGE_UNKNOWN`, budżet przed/po, raw SQLite i rollback. Pełny suite 1036/1036; partycje exact-once 248+253+267+268; 38 testów concurrency/race ×30; siedem plików worker/reconciliation/lineage/recovery/maintenance/migration ×10; QA 10/10 bez wycieków; nowy E2E w 10 świeżych procesach; zero sieci/API/browsera/publikacji/kosztu.

### ADR-066: WAVE 1A — eskalacja crash-window i pełna atomowość terminalizacji na poziomie SQLite (po trzecim `REJECTED — MAJOR`)

- **Data:** 2026-07-16
- **Status:** ACCEPTED / wdrożone offline; **`WAVE 1A CANDIDATE — AWAITING INDEPENDENT REVIEW`** (bez zmiany statusu). WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`. Uzupełnia ADR-064/065.
- **Kontekst:** trzecie niezależne review odrzuciło WAVE 1A. (1) **W1A-AUD-04 = MAJOR BLOCKING:** po crashu i wygaśnięciu lease trwałe `RESERVED`/`REQUEST_STARTED` były niewidoczne dla kolejki L1, nierozstrzygalne (resolver akceptował wyłącznie `NEEDS_RECONCILIATION`) i bezterminowo rezerwowały budżet; test audytowy utrwalał stuck state jako sukces. (2) **W1A-SQLITE-01:** surowa terminalizacja attemptu nie wymagała pełnego lifecycle ani eventu `FINAL_RESOLUTION`. (3) **W1A-SQLITE-02:** kanoniczny `model_usage` był mutowalny/kasowalny po `RECONCILED_SETTLED` przy nietkniętych cache'ach.
- **Decyzja:**
  - **Eskalacja crash-window (aplikacja + 0014):** `release_or_requeue_expired_leases` w tej samej `BEGIN IMMEDIATE` transakcji eskaluje każdy attempt `RESERVED`/`REQUEST_STARTED`, którego job jest w `NEEDS_VERIFICATION` z martwym fence: `RESERVED → NEEDS_RECONCILIATION` z powodem `LEASE_EXPIRED_BEFORE_REQUEST_STARTED` (macierz stanów 0014 dopuszcza `NEEDS_RECONCILIATION` z `request_started_at IS NULL` wyłącznie z tym powodem; trigger przejść ma dokładnie jedno nowe ramię), `REQUEST_STARTED → NEEDS_RECONCILIATION` z powodem `LEASE_EXPIRED_AFTER_REQUEST_STARTED`; każda eskalacja zostawia append-only event **`AUTO_ESCALATION`** (nowy typ, previous ∈ {RESERVED, REQUEST_STARTED}); operacja jest idempotentna, serializowana, nie dotyka żywego lease ani terminali, nie wykonuje retry/attemptu #2/providera i unieważnia stary preview token. Attempt bez `REQUEST_STARTED` (dowodliwie zero calla) może być rozstrzygnięty **wyłącznie `NOT_CHARGED`**; `RECONCILED_SETTLED` wymaga startu requestu również w macierzy stanów.
  - **Atomowość terminalizacji (W1A-SQLITE-01):** resolver zapisuje w kolejności `walidacja → lifecycle (run/research_run/job) → usage + oba cache → FINAL_RESOLUTION → attempt jako OSTATNIA mutacja`; `0014` wymusza triggerami przy `NEEDS_RECONCILIATION → RECONCILED_*`: dokładnie zgodny event `FINAL_RESOLUTION` (resulting status, combined resolution, operator, note), terminalny spójny lifecycle zgodny z execution resolution (`FAILED/FAILED/FAILED` bez karty albo `DONE/SUCCESS/COMPLETE` z kartą) ze zwolnioną rezerwacją i lease, oraz `runs.cost_usd`/`research_runs.total_cost_usd` równe kanonowi (tolerancja 5e-7 = pół kwantu). Eventy każdego typu można dopisywać tylko przy żywym `NEEDS_RECONCILIATION` (trigger zastępuje dawny „resulting musi równać się attemptowi"); dopisanie eventu do terminala jest niereprezentowalne.
  - **Niezmienność kanonu (W1A-SQLITE-02):** triggery no-UPDATE/no-DELETE na kanonicznym `model_usage` rekoncyliowanego attemptu (każda kolumna, w tym koszt/tokeny/tożsamość) oraz zamrożenie `runs.cost_usd` i `research_runs.total_cost_usd` po terminalu; nowy wpis dla terminalnego attemptu niereprezentowalny (relacja + UNIQUE `request_id`).
  - **CLI/QA:** pełna kontrolowana obsługa `list-reconciliations` (config→3; open/query/format/close→6, bez tracebacku), `reconcile-attempt` + `RuntimeError`/guarded close; QA disproof z prefiksem `nia-lineage-disproof-`, cleanupem w `finally` i twardą kontrolą pozostałości w exit code.
- **Skutek:** +25 trwałych testów (macierz eskalacji H1–H20 i macierz raw-SQLite, ciek QA); licznik **982 → 1007**, pełny suite 1007/1007, partycje exact-once 4/4, concurrency 33 nodes ×30, pliki 10/10, QA 10/10, kontrpróby niezależne 5/5, `data/agent.db` byte-identical. Obowiązuje ADR-066.
- **Kto podjął:** właściciel przekazał wynik trzeciego review i autoryzował pełną falę naprawczą; wykonanie offline.

### ADR-065: WAVE 1A — `W1A-VERIFY-02`, pełna walidacja lineage reconciliation (defense-in-depth)

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone offline; **`WAVE 1A CANDIDATE — AWAITING INDEPENDENT REVIEW`** (bez zmiany statusu). WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`. Uzupełnia ADR-063/064 (nie unieważnia).
- **Kontekst:** drugie niezależne review odrzuciło WAVE 1A (`REJECTED — MAJOR`).  Reviewer wykazał na tymczasowej bazie fail-open: przy `jobs.account_id`/`research_runs.account_id` = właściciel, `runs.account_id` = konto obce, `runs.workflow` = `ANALYTICS` resolver akceptował reconciliation i terminalizował attempt/job/run/research_run.  **Root cause:** `_reconciliation_state_row` nie czytał `runs.account_id`/`runs.workflow`/`jobs.kind`/`jobs.workflow`, a walidacja sprawdzała tylko `research_runs` account/topic; brak weryfikacji pełnej relacji `provider_attempt → job → run → research_run → account → workflow → topic → durable intent`.  Zielony baseline **955/955 (ADR-064) nie obejmował tego przypadku.**
- **Decyzja (defense-in-depth, bez zmiany kontraktu finansowego ani `RESULT_ALREADY_FINALIZED`):**
  - **Warstwa aplikacji:** `_reconciliation_state_row` czyta teraz również `runs.account_id`, `runs.workflow`, `jobs.kind`, `jobs.workflow`, `research_runs.flow`.  Nowy `_reconciliation_require_consistent_lineage` (jeden helper, zero rozjechanych literałów) waliduje przed jakąkolwiek mutacją: job `kind`/`workflow`=RESEARCH; `runs.account_id == jobs.account_id == research_runs.account_id == intent.account_id`; `runs.workflow == RESEARCH`; `research_runs.topic_id == jobs.topic_id == intent.topic_id`; `research_runs.flow == single`; fingerprint durable intentu; zwraca zweryfikowany intent.  Wywoływany na każdej ścieżce mutującej (CHARGE_UNKNOWN, CHARGED_KNOWN, NOT_CHARGED).
  - **Version token → v2:** obejmuje wszystkie pola lineage (job/run/research account, `runs.workflow`, `jobs.kind`/`workflow`, `jobs.run_id`, topic, `research_runs.flow`, fingerprint) plus dotychczasowe statusy/koszt/historię.  Dowolna zmiana między preview a confirm ⇒ `ReconciliationPreviewStaleError` (fail-closed).
  - **Warstwa SQLite (0014 in-place, bez 0015):** trigger `provider_attempts_reconcile_requires_consistent_lineage` `BEFORE UPDATE OF status` blokuje terminalizację, chyba że cały lineage jest spójny (join `jobs→runs→research_runs`, account/workflow/topic/flow/kind oraz `json_extract` payload↔job).  `json_extract` NULL ⇒ fail-closed.  Fingerprint intentu (SHA-256 nad kanonicznym payloadem) pozostaje inwariantem aplikacyjnym — SQLite go nie przeliczy; udokumentowane.
- **Każda niespójność:** fail-closed, zero mutacji (attempt/job/run/research_run/rezerwacja/usage/event), bez retry/attemptu #2/providera.
- **Skutek:** trwałe testy regresyjne: `tests/test_reconciliation_lineage.py` (17 negatywnych rozjazdów, każdy z pełnym brakiem mutacji + stale-token + raw-trigger + pozytywna macierz) oraz `scripts/qa/reconciliation_lineage_disproof.py` (uruchamialny przez reviewera, temp DB, safety kernel, exit code).  Licznik **955 → 980**; pełny suite 980/980, 4 partycje exact-once (236+240+254+250), concurrency 30/30 (×2), reconciliation 10/10, lineage disproof 10/10, `data/agent.db` niezmieniona.  Obowiązuje ADR-065.
- **Kto podjął:** właściciel autoryzował wyłącznie naprawę `W1A-VERIFY-02`; wykonanie offline.

### ADR-064: WAVE 1A — `W1A-VERIFY-01`, resolver `EXECUTION_FAILED` akceptuje reaper-`STOPPED`

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone offline; **`WAVE 1A CANDIDATE — AWAITING INDEPENDENT REVIEW`** (bez zmian statusu). WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`. Uzupełnia ADR-063 (nie unieważnia).
- **Kontekst:** niezależna weryfikacja ADR-063 wykazała jeden niedeterministyczny test (`test_resolver_interleaves_with_recovery_and_reaper_without_reviving_attempt`, ~50% flaky). **Root cause:** maintenance-reaper `reap_orphaned_stale_runs` terminalizuje osierocony stale run do `STOPPED`, gdy job pozostaje `NEEDS_VERIFICATION` (guard reapera nie blokuje, bo `NEEDS_VERIFICATION ∉ {QUEUED,LEASED,RUNNING}`), a resolver w gałęzi `EXECUTION_FAILED` akceptował tylko `run_status ∈ {RUNNING, FAILED}`. Gdy reaper wygrywał wyścig o blokadę zapisu, resolver odmawiał („Execution failure requires a non-success single lifecycle") — fail-closed i bezpieczny, ale zależny od kolejności wątków.
- **Decyzja (minimalny, kompletny zakres):**
  - `EXECUTION_FAILED` akceptuje `run_status ∈ {RUNNING, STOPPED, FAILED}` przez **jedno** źródło `_EXECUTION_FAILED_RUN_STATUSES`, użyte i w warunku, i w `WHERE ... IN (...)` compare-and-swap `UPDATE` (rozjazd między nimi był pierwotną wadą; teraz jest niemożliwy).
  - `STOPPED → FAILED` w tej samej atomowej transakcji `BEGIN IMMEDIATE`: attempt → `RECONCILED_SETTLED`/`RECONCILED_RELEASED`, job/run/research_run → `FAILED`, rozliczona/zwolniona rezerwacja, zgodny `model_usage` + cache, append-only `FINAL_RESOLUTION`.
  - `error`/`finished_at` przez `COALESCE`, więc historia reaper/maintenance nie jest usuwana; `cost_usd` odświeżany do kanonu ledgera.
  - **Bez zmian:** semantyka `RESULT_ALREADY_FINALIZED` (nadal wymaga wyłącznej Research Card + `SUCCESS`/`COMPLETE`; `STOPPED` nigdy → `DONE`), kontrakt finansowy, brak retry/attemptu #2/providera, version token, wyłączna własność karty, brak dead-endu `MANUAL`.
- **Skutek:** licznik testów **948 → 955** (+7 deterministycznych scenariuszy resolver↔reaper: reaper-first, resolver-first no-op, wyścig order-independent, reopen po STOPPED, RESULT_ALREADY_FINALIZED na STOPPED odrzucone, foreign account, conflicting research_run). Stabilność: flaky node **30/30**, plik **10/10**; pełny suite **955/955** offline, partycje exact-once (227+233+248+247), 20/20 niezależnych kontrprób BLOCKED, `data/agent.db` niezmieniona. Bez stagingu/commita/pushu/PR/merge.
- **Kto podjął:** właściciel autoryzował wyłącznie naprawę `W1A-VERIFY-01`; wykonanie offline.

### ADR-063: WAVE 1A resolver — naprawa po niezależnym `REJECTED — MAJOR`

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone offline; **`WAVE 1A CANDIDATE — AWAITING INDEPENDENT REVIEW`**. WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.
- **Kontekst:** niezależny audyt odrzucił pierwszą iterację WAVE 1A (`REJECTED — MAJOR`: W1A-RR-01…06, W1A-NEW-01/02). Ta decyzja koryguje ADR-062 w jednej fali, bez migracji 0015.
- **Decyzja (poprawiony kontrakt):**
  - Migracja `0014_provider_attempt_reconciliation` poprawiona **in place**: pełny kontrakt stanów `provider_attempts`, pola audytu przycinane po wszystkich białych znakach, enum `reconciliation_resolution`, a terminalne `RECONCILED_SETTLED`/`RECONCILED_RELEASED` są niezmienne i nieusuwalne (`DROP TRIGGER IF EXISTS`, zachowane inwarianty 0011–0013).
  - Nowa **append-only** tabela `reconciliation_events` (`UNRESOLVED_OBSERVATION` → `FOLLOW_UP` → `FINAL_RESOLUTION`, monotoniczny `sequence_number`, `idempotency_key`, triggery blokujące UPDATE/DELETE) jest jedynym źródłem historii; pola na `provider_attempts` tylko podsumowują stan terminalny.
  - Istniejący `model_usage` akceptowany wyłącznie po **pełnej weryfikacji tożsamości** (provider, model, task z formalnego zbioru `_RESEARCH_USAGE_TASKS`, run_id, konto, real/legacy, fingerprint, koszt), nie na podstawie samego kosztu.
  - `RESULT_ALREADY_FINALIZED` wymaga **wyłącznego** dowodu Research Card: `UNIQUE research_runs(research_card_id)` plus pełny łańcuch card ↔ research_run ↔ run ↔ job ↔ konto ↔ topic.
  - **Brak dead-endu `MANUAL`:** `MANUAL_REVIEW_REMAINS_REQUIRED` jest dozwolone tylko z `CHARGE_UNKNOWN` (obserwacja, nigdy terminalna); `CHARGED_KNOWN`/`NOT_CHARGED` wybierają `EXECUTION_FAILED` albo `RESULT_ALREADY_FINALIZED`. Żaden terminalny attempt nie zostaje z jobem w `NEEDS_VERIFICATION`.
  - Niezmienna spójność ledger↔cache: `SUM(model_usage) = runs.cost_usd = research_runs.total_cost_usd` (Decimal) po każdej zmianie kanonu; `CHARGED_KNOWN` wymaga kosztu `> 0` (koszt 0 → `NOT_CHARGED`).
  - CLI: `reconcile-attempt` preview czyta trwały stan i zwraca **version token**; `--confirm` wymaga tokenu i fail-closed przy stale, z kontrolowanymi exit codes.
- **Skutek:** **955 testów offline**, 14 migracji, `model_usage` jedyny kanon, `data/agent.db` niezmieniona. Obowiązuje ADR-063; ADR-062 pozostaje jako zapis pierwszej (odrzuconej) iteracji. Historyczne 894/13 i `READY FOR CHECKPOINT` są historyczne.
- **Kto podjął:** właściciel zlecił naprawę WAVE 1A; wykonanie offline.

### ADR-062: Operatorskie reconciliation L1 rozdziela koszt od wyniku wykonawczego (WAVE 1A — iteracja pierwsza)

- **Data:** 2026-07-15
- **Status:** SUPERSEDED przez ADR-063 (iteracja odrzucona jako `REJECTED — MAJOR`). Zapis historyczny pierwotnej macierzy „trzy finanse × trzy wykonania jako niezależne"; poprawiony kontrakt i status obowiązują w ADR-063. WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** właściciel zlecił zamknięty, offline zakres resolvera; wykonanie: Codex.
- **Decyzja:** `0014_provider_attempt_reconciliation` dodaje wyłącznie stany `RECONCILED_SETTLED` i `RECONCILED_RELEASED` oraz pola audytu. Jedna operacja StoragePort w `BEGIN IMMEDIATE` wiąże aktualny attempt, usage, job, run i research_run. `CHARGED_KNOWN` zapisuje albo sprawdza jeden canonical `model_usage`; `NOT_CHARGED` odmawia przy non-legacy usage; `CHARGE_UNKNOWN` nie rozwiązuje attemptu ani rezerwacji. Wykonanie jest osobną decyzją: `DONE` jest dopuszczalne wyłącznie po istniejącej, poprawnie powiązanej Research Card.
- **Granice:** brak providera/SDK, retry, attemptu #2, resume, karty tworzonej przez resolver, drugiego ledgeru, API, kosztu, zmiany `data/agent.db`, stagingu, commita, pushu, PR i merge w tej fali.
- **Weryfikacja (iteracja historyczna):** fresh/upgrade/rollback 0014, failpointy transakcji, dwa połączenia SQLite, sprzeczne decyzje, stale CLI preview, money/usage/state negatives, import graph CLI bez dispatchera/workera/SDK; 919 testów offline. Obowiązująca weryfikacja po naprawie (ADR-063): **955 testów offline**.

## Cel

Rejestr decyzji projektowych i architektonicznych — zwłaszcza tych rozstrzygających rozbieżności między dokumentami. Każda decyzja opisuje kontekst, rozważane opcje, wybór i konsekwencje. To „dlaczego" systemu; „co i kiedy" jest w `BUILD_LOG.md`. Decyzje otwarte (czekające na właściciela) trzymamy w sekcji „Otwarte" i zamykamy po akceptacji.

## Zasady

- Jedna decyzja = jeden wpis z numerem `ADR-XXX`.
- Status: PROPOSED / ACCEPTED / REJECTED / SUPERSEDED (przez ADR-YYY).
- Rozstrzygnięcia rozbieżności między dokumentami zawsze wskazują „źródło prawdy".

## Szablon wpisu

```markdown
### ADR-XXX: Tytuł decyzji
- **Data:** YYYY-MM-DD
- **Status:** PROPOSED | ACCEPTED | REJECTED | SUPERSEDED
- **Czego dotyczyła:** jaki problem / jaka rozbieżność
- **Rozważane opcje:** A) ... B) ... C) ...
- **Decyzja i uzasadnienie:** co wybrano i dlaczego
- **Zalety:** ...
- **Ryzyka:** ...
- **Kto podjął:** Claude | człowiek | wspólnie
- **Zmieniona później:** nie | tak → ADR-YYY (kiedy i dlaczego)
- **Powiązania:** ADR-..., MASTER_ARCHITECTURE.md §..., IMPLEMENTATION_ROADMAP.md Etap ...
```

> Uwaga (2026-07-12, ADR-023): powiązania w historycznych wpisach ADR-001..022 wskazują na dokumenty zarchiwizowane w `docs/archive/superseded_plans/` (IMPLEMENTATION_PLAN.md, ARCHITECTURE.md, SUBSTACK_INTEGRATION.md) — pozostają jako kontekst historyczny; nowe wpisy odwołują się do dokumentów źródła prawdy.

> Wcześniejsze wpisy ADR-001..010 używają skróconej formy (Kontekst/Opcje/Decyzja/Konsekwencje). Nowe wpisy stosują pola powyżej.

---

## Decyzje architektoniczne

### ADR-001: Źródło prawdy dla wag scoringu tematów
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** trzy dokumenty podają różne wagi scoringu tematu (ARCHITECTURE/YAML vs PROJEKT vs MASTER).
- **Opcje:** A) ARCHITECTURE/growth_policy.yaml (25/20/15/15/10/10/5) B) PROJEKT (25/25/20/10/10/10) C) MASTER.
- **Decyzja:** A — spójne z plikiem konfiguracyjnym, który będzie kodem.
- **Konsekwencje:** PROJEKT/MASTER traktowane jako inspiracja; wagi tylko z configu.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.1, załącznik rozbieżności.

### ADR-002: Źródło prawdy dla funkcji celu wzrostu
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** ARCHITECTURE/YAML (45/20/15/10/5/5) vs MASTER (40/20/15/10/10/5 + konwersja).
- **Decyzja:** ARCHITECTURE/growth_policy.yaml.
- **Konsekwencje:** „konwersja profil→subskrypcja" liczona jako metryka pomocnicza oznaczona jako estymacja, nie składnik funkcji celu.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.1, A.9.

### ADR-003: Grafiki SVG-only w MVP
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** MASTER/PROJEKT chcą obrazów „cinematic editorial"; Anthropic-only daje tylko SVG→PNG.
- **Decyzja:** MVP = SVG-only za interfejsem `ImageProvider`; zewnętrzny generator poza MVP.
- **Konsekwencje:** okładki/diagramy zamiast fotorealizmu; brak kosztu grafik w MVP.
- **Powiązania:** IMPLEMENTATION_PLAN.md §A.4, §B.1.

### ADR-004: Docelowy sufit autonomii MVP = LEVEL_2 (z bramkowaniem)
- **Data:** 2026-07-11
- **Status:** ACCEPTED, **doprecyzowana przez ADR-017 (ta sama data, później)** — patrz niżej. Sedno ADR-004 (bezpieczny, stopniowy start) pozostaje w mocy; semantyka „artykuły/komentarze zawsze człowiek" była opisem **fazy startowej**, nie stanu docelowego.
- **Kontekst:** właściciel wybrał celowanie od razu w LEVEL_2 (auto-publikacja wybranych typów Notes). PROJEKT/MASTER nadal wymagają akceptacji KAŻDEGO artykułu i KAŻDEGO komentarza na starcie.
- **Decyzja:** startowy sufit MVP = LEVEL_2 rozumiane wąsko: auto-publikacja tylko wcześniej zatwierdzonych *typów* Notes; artykuły, komentarze, linki, restacki — człowiek **na etapie startowym**. *(Docelowa, szersza semantyka LEVEL_2/LEVEL_3 — patrz ADR-017.)*
- **Bramkowanie (twarde):** auto-publikacja Notes NIE włącza się, dopóki (a) nie działa warstwa przeglądarki (Etap 4), (b) nie ma ≥1 tygodnia stabilnej jakości szkiców, (c) właściciel nie włączy jej jawnym przełącznikiem. Do tego czasu efektywny poziom = LEVEL_1 (dry_run, wszystko za akceptacją).
- **Konsekwencje:** architektura i Policy Engine od początku wspierają LEVEL_2, ale start jest bezpieczny; żaden pierwszy etap nic nie publikuje.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.8, CZĘŚĆ D, ADR-005, **ADR-017**.

### ADR-005: Brak publikacji na Substacku w MVP-0
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** `IMPLEMENTATION_PROMPT.md` zakazuje wdrażania publikacji; DoD §23 zakłada publikację jako cel końcowy.
- **Decyzja:** Etapy 0–3 offline (dry_run), publikacja dopiero od Etapu 4 i tylko po wyraźnej zgodzie właściciela.
- **Konsekwencje:** pierwszy MVP produkuje szkice do akceptacji, nie publikuje.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.11.

### ADR-006: Jedna baza SQLite ze scopingiem po account_id
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** izolacja kont vs prostota raportów.
- **Decyzja:** jedna baza; obowiązkowy `account_id` w StoragePort; testy izolacji.
- **Konsekwencje:** prostsze raporty, ryzyko wycieku między kontami przy błędzie — pokryte testami.
- **Powiązania:** IMPLEMENTATION_PLAN.md §A.6, §B.9, §B.10.

#### Weryfikacja wdrożenia ADR-001/002/003/005/006 — Etap 0 / Task 7

- **ADR-001:** `config/growth_policy.example.yaml` jest kanonem wag 25/20/15/15/10/10/5; `load_settings()` ładuje je do `Settings.topic_scoring_weights`, a workflow tematów używa ich w `compute_weighted_score`. Brak nowszego ADR zmieniającego te wagi.
- **ADR-002:** funkcja celu i wagi 45/20/15/10/5/5 są zapisane w jedynym bieżącym `growth_policy`; analytics/strategy loop jest dopiero Etapem 7 roadmapy, ale nie istnieje konkurencyjne źródło ani nowsza decyzja zmieniająca kontrakt.
- **ADR-003:** bieżący MVP nie ma zewnętrznego generatora rasterowego ani kosztu grafik; decyzja pozostaje ograniczeniem zakresu. `ImageProvider` będzie potrzebny dopiero przy implementacji modułu grafik — jego brak dziś nie oznacza wdrożenia alternatywnej drogi.
- **ADR-005:** brak publikacji jest faktycznie wymuszony (`DisabledBrowser`, zero kodu publikacyjnego i zero publikacji). Historyczne określenie „od Etapu 4” pochodzi sprzed konsolidacji roadmapy; aktualne mapowanie z `IMPLEMENTATION_ROADMAP.md` lokuje właściwą publikację w **Etapie 5**. Zmieniła się numeracja, nie meritum: publikacja dopiero po wcześniejszych bramkach i osobnej zgodzie właściciela.
- **ADR-006:** aplikacja używa jednej bazy SQLite; encje i operacje per-konto są scopowane bezpośrednim `account_id` albo zweryfikowaną relacją przez temat/run. Repozytoria i testy izolacji obejmują topics, research cards, runy, usage i finalizację.
- **Wynik:** wszystkie pięć decyzji pozostaje zgodnych z `MASTER_ARCHITECTURE.md`, `IMPLEMENTATION_ROADMAP.md` i `CURRENT_PROJECT_STATE.md`; żadna nie została zastąpiona nowszym ADR. Nie znaleziono sprzeczności P1.

### ADR-007: Zakres MVP = jedno konto (nothing_is_accidental)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** właściciel: „narazie agent ma działać tylko na koncie tym nowym".
- **Decyzja:** MVP obsługuje wyłącznie `nothing_is_accidental`. `owner_account` i `wife_account` pozostają `active: false`. Architektura wielokontowa zostaje (porty, account_id, izolacja), ale nie jest aktywowana w pierwszym etapie.
- **Konsekwencje:** prostszy, szybszy pierwszy etap; testy izolacji wielokontowej i tak piszemy, by włączenie kolejnych kont było bezpieczne.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.9, §B.11.

### ADR-008: Nisza konta żony = astrologia (nieaktywne w MVP)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** `wife_account.niche` było puste.
- **Decyzja:** nisza = astrologia; konto pozostaje `active: false` do czasu po MVP jednego konta.
- **Konsekwencje:** wartość zapisana na przyszłość; discovery komentarzy dla żony będzie miało punkt startu, gdy konto zostanie włączone.
- **Powiązania:** ADR-007.

### ADR-009: Panel = FastAPI + prosty frontend
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** wybór między Streamlit a FastAPI.
- **Decyzja:** FastAPI + prosty frontend, dostęp tylko przez localhost.
- **Konsekwencje:** więcej pracy na starcie, ale bliżej docelowej architektury i łatwiejsza migracja do chmury / dodanie API akceptacji.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.2 (`app/ui/`), Etap 3.

### ADR-010: Klucz API — tylko `.gitignore`, bez rotacji teraz
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** realny klucz w `.env`; właściciel wybrał na razie tylko zabezpieczenie repo.
- **Decyzja:** dodać `.gitignore` (z `.env`, `data/`, `config/accounts.yaml`, `config/growth_policy.yaml`) i `.env.example` (placeholdery). Klucza nie rotujemy na tym etapie.
- **Konsekwencje:** repo nie wyeksponuje klucza przy commitcie. **Ryzyko rezydualne pozostaje**, jeśli klucz już gdzieś trafił (kopia pliku, backup) — do rotacji przed pierwszym publicznym udostępnieniem repo. Pozycja utrzymana jako otwarta w ERRORS_AND_FAILURES (R1).
- **Powiązania:** ERRORS_AND_FAILURES.md (R1), Etap 0.

### ADR-011: Integracja z istniejącym kontem Substack (bez tworzenia nowego)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** sposób podłączenia agenta do konta „Nothing Is Accidental", które już istnieje.
- **Rozważane opcje:** A) utworzyć nowe konto dla agenta; B) połączyć się z istniejącym kontem przez dedykowany profil Playwright po ręcznym logowaniu.
- **Decyzja i uzasadnienie:** B. Konto istnieje (bio: „Explaining the hidden systems, incentives and decisions behind ordinary things.", język EN); nie tworzymy nowego. Integracja przez osobny persistent context Playwright w `data/browser-profiles/nothing_is_accidental/`; logowanie ręczne (magic-link), bez auto-logowania i bez zapisu hasła.
- **Zalety:** brak hasła do przechowania; pełna izolacja sesji; człowiek kontroluje uwierzytelnienie.
- **Ryzyka:** wygaśnięcie sesji, zmiany UI (R2/R3), ToS automatyzacji (R11) — mitygowane stop-conditions i brakiem publikacji na obecnym etapie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** docs/architecture/SUBSTACK_INTEGRATION.md, ADR-005, IMPLEMENTATION_PLAN.md §B.6/§B.9.

### ADR-012: Polityka budżetu — miesięczny limit ma bezwzględny priorytet
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** relacja limitu dziennego i miesięcznego oraz zachowanie po przekroczeniu.
- **Rozważane opcje:** A) obniżyć limit dzienny do ~1.30; B) zostawić 2.00/dzień i 40.00/miesiąc, ale miesięczny nadrzędny.
- **Decyzja i uzasadnienie:** B. Limit dzienny = **2.00 USD**, miesięczny = **40.00 USD**. **Limit miesięczny ma bezwzględny priorytet**: po osiągnięciu 40.00 USD w danym miesiącu wszystkie płatne działania zostają zatrzymane, niezależnie od limitu dziennego. Policy Engine sprawdza `month_to_date` przed każdym płatnym wywołaniem.
- **Zalety:** twardy sufit kosztu miesięcznego; prostota (nie trzeba zaniżać dziennego).
- **Ryzyka:** w skrajnym scenariuszu dzienny sufit pozwala teoretycznie na 60 USD/mies. — dlatego to miesięczny limit jest egzekwowany jako nadrzędny (blokada), a dzienny to dodatkowe ograniczenie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** growth_policy.example.yaml, IMPLEMENTATION_PLAN.md §A.7, app/policies/policy_engine.py.

### ADR-013: Mechanizm dry_run i kolumna model_usage.dry_run
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** jak realizować „jedno wywołanie Anthropic" w trybie dry_run bez wydawania budżetu i bez zależności sieciowej w testach.
- **Rozważane opcje:** A) realne płatne wywołanie API już w walking skeleton; B) w dry_run klient zastępczy (`FakeLLMClient`) bez sieci/kosztu, koszt zapisany jako estymacja oflagowana `dry_run`.
- **Decyzja i uzasadnienie:** B. Interfejs `LLMClient` ma dwie implementacje: `FakeLLMClient` (dry_run, deterministyczny) i `AnthropicLLMClient` (realny, `--real`). Dodano kolumnę `model_usage.dry_run`; budżet (`sum_real_cost_usd`) sumuje tylko wpisy realne. Uzasadnienie: nie wydajemy budżetu bez wyraźnej zgody, testy są offline i deterministyczne, a mechanizm kosztów jest w pełni zademonstrowany.
- **Zalety:** zero kosztu i sieci w MVP-0; realne wywołanie o jeden przełącznik dalej; testy szybkie i powtarzalne.
- **Ryzyka:** estymowany koszt dry_run ≠ realny (świadomie oznaczony jako „szacunek dry_run").
- **Kto podjął:** Claude (zgodnie z zasadą „bez realnych kluczy/kosztów bez zgody" i wobec sformułowania „rzeczywisty lub szacowany koszt").
- **Zmieniona później:** nie.
- **Powiązania:** app/llm/fake_client.py, app/llm/usage_tracker.py, IMPLEMENTATION_PLAN.md §B.4.

### ADR-014: Deduplikacja tematów lokalna (bez płatnego modelu)
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** jak wykrywać duplikaty tematów bez dodatkowego kosztu na każde sprawdzenie.
- **Rozważane opcje:** A) embeddingi/model semantyczny (płatny per temat); B) lokalny deterministyczny: znormalizowany tytuł + Jaccard tokenów + SequenceMatcher, próg z configu.
- **Decyzja i uzasadnienie:** B. Wymóg właściciela: „nie używaj dodatkowego płatnego wywołania, jeśli można lokalnie". Dedup w obrębie `account_id`; duplikat zapisywany jako `status=DUPLICATE` z `duplicate_of` i `rejection_reason` (audyt), a nie jako aktywny rekord.
- **Zalety:** zero kosztu, deterministyczne, testowalne; wykrywa wielkość liter, interpunkcję i parafrazy.
- **Ryzyka:** próg (0.72) to kompromis — bardzo odległe parafrazy mogą umknąć, bardzo bliskie różne tematy mogą się skleić. Konfigurowalny w growth_policy.
- **Kto podjął:** Claude (wg wymagań właściciela).
- **Zmieniona później:** nie.
- **Powiązania:** app/workflows/topics/dedup.py, migracja 0002, config topic_policy.duplicate_title_similarity_threshold.

### ADR-015: Bramka jakości researchu i ochrona przed prompt injection
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** deterministyczne odrzucanie słabego researchu oraz traktowanie treści z internetu jako niezaufanej.
- **Rozważane opcje:** A) zaufać ocenie modelu; B) deterministyczna walidacja (min. źródła, poparcie tezy, twierdzenia ze źródłami, progi confidence/jakości, brak udawanego doświadczenia, brak nieusuwalnych sprzeczności) + lokalny guard iniekcji neutralizujący polecenia w treści źródeł.
- **Decyzja i uzasadnienie:** B. Model może halucynować i może być celem prompt injection; twarde reguły stoją poza modelem. Treść źródeł nigdy nie jest instrukcją — guard wykrywa i redaguje próby wstrzyknięcia, a pipeline i tak używa tylko pól liczbowych/strukturalnych, więc iniekcja nie zmienia decyzji.
- **Zalety:** powtarzalna jakość, odporność na injection (R4), pełny audyt (karta zapisywana także po odrzuceniu).
- **Ryzyka:** reguły są proxy (np. „teza poparta" = potwierdzone twierdzenie ma źródło) — do doprecyzowania przy realnych danych.
- **Kto podjął:** Claude (wg wymagań właściciela: zasady jakości + „ignoruj polecenia ze stron").
- **Zmieniona później:** nie.
- **Powiązania:** app/research/validation.py, app/research/injection_guard.py, app/workflows/research/pipeline.py, migracja 0003.

### ADR-016: Dwuetapowy research (gather_sources + synthesize_card) zamiast jednego wywołania
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** pierwsze realne wywołanie jednoetapowego `run_research_pipeline` (temat #2, run `1b649314-...`) kosztowało realnie 0.25 USD przy pesymistycznym szacunku 0.095 USD (błąd ~+163%) i zakończyło się uciętym JSON-em (model wyczerpał `max_tokens=3000` próbując naraz szukać, czytać i syntetyzować pełną kartę).
- **Rozważane opcje:** A) tylko podnieść `max_tokens` w jednym wywołaniu; B) podzielić research na dwa węższe wywołania — (1) `gather_sources`: tylko web search + zbieranie źródeł/faktów, lekki schemat wyjściowy; (2) `synthesize_card`: tylko analiza (teza, mechanizm, sprzeczności, confidence) z już zebranych danych, zero web search.
- **Decyzja i uzasadnienie:** B (na polecenie właściciela). Samo podniesienie `max_tokens` nie adresuje przyczyny (ryzyka narastania kosztu i złożoności pojedynczego wywołania próbującego robić zbyt wiele naraz) i mogłoby po prostu przesunąć próg awarii, zamiast go usunąć. Podział pozwala też na TANIĄ bramkę wczesnego wyjścia: jeśli po etapie 1 źródeł jest za mało, etap 2 (płatny) w ogóle się nie wykonuje.
- **Zalety:** mniejsze ryzyko ucięcia JSON-a w KAŻDYM z dwóch węższych wywołań; wczesne, tanie odrzucenie słabego researchu; koszt etapu 2 pod pełną kontrolą (brak web search, ograniczony przez nas kontekst); łatwiejsze do oszacowania osobno.
- **Wady / ryzyka:** więcej ruchomych części (dwa wywołania zamiast jednego); redukcja kosztu WORST-CASE jest umiarkowana (~31% w projekcji), bo dominującym czynnikiem kosztu jest liczba wyszukiwań, nie sam podział — główna korzyść to STABILNOŚĆ (mniej ucięć), nie wyłącznie oszczędność. Jawnie udokumentowane, nie sprzedawane jako coś więcej niż jest.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** app/research/cost_estimator.py, app/research/anthropic_client.py (`gather_sources`/`synthesize_card`), app/workflows/research/pipeline.py (`run_two_stage_research_pipeline`), docs/ERRORS_AND_FAILURES.md („Pre-flight cost estimator underestimated the real cost").

### ADR-017: Docelowym trybem projektu jest pełna autonomia operacyjna
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela — doprecyzowanie, nie zwrot)
- **Czego dotyczyła:** audyt wykazał, że dokumentacja (macierz akceptacji `IMPLEMENTATION_PLAN.md §B.8`, semantyka ADR-004, większość `opis-budowy-substack/`) zaczęła sugerować, że ręczna akceptacja KAŻDEJ akcji jest stanem docelowym systemu, a nie fazą startową. Właściciel doprecyzował, że tak nie jest.
- **Rozważane opcje:** A) system docelowo pozostaje asystentem generującym wyłącznie propozycje do ręcznego zatwierdzania; B) system docelowo prowadzi konto w pełni autonomicznie (LEVEL_3), a ręczna akceptacja jest mechanizmem fazy startowej i bramką przy przejściu między poziomami autonomii, nie stałym elementem architektury.
- **Decyzja i uzasadnienie:** B. **„Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta."** Rolę audytowalności na poziomach autonomicznych (LEVEL_2/LEVEL_3) przejmuje deterministyczny scoring + Policy Engine + pełny log każdej decyzji (`autonomous_decisions`), nie ręczny klik człowieka.
- **Zalety:** zgodność z pierwotnym celem eksperymentu („czy agent potrafi SAMODZIELNIE prowadzić publikację" — nie „czy potrafi przygotowywać szkice do zatwierdzenia"); jaśniejsza narracja do serii artykułów; wymusza budowę realnych mechanizmów jakości (scoring, SAFE MODE) zamiast polegania na człowieku jako jedynym filtrze.
- **Ryzyka:** wyższe ryzyko reputacyjne/jakościowe przy przejściu na LEVEL_2/3 (błąd trafia na żywą platformę bez człowieka w pętli) — mitygowane twardymi, mierzalnymi warunkami przejścia (`IMPLEMENTATION_PLAN.md §D.3`) i SAFE MODE (`§D.7`), obie wymagające jawnej zgody właściciela przy KAŻDYM podniesieniu poziomu.
- **Co się NIE zmienia:** brak publicznego ujawnienia automatyzacji jest obowiązkowym założeniem eksperymentu. Informacja o AI pozostaje wyłącznie w prywatnej dokumentacji do czasu osobnej decyzji właściciela — to pozostaje niezmienne na każdym poziomie autonomii; autonomia dotyczy WYKONANIA, nie publicznego ujawniania natury agenta. Zakaz wiadomości prywatnych i inicjowania kontaktu z innymi autorami — pozostaje bezwzględny na każdym poziomie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** tak → **ADR-018** (2026-07-11, ta sama data, później) doprecyzowuje punkt „Co się NIE zmienia" powyżej — pierwotna wersja tego ADR błędnie zakładała PUBLICZNE ujawnienie AI; poprawiona treść powyżej już to odzwierciedla.
- **Powiązania:** `IMPLEMENTATION_PLAN.md` CZĘŚĆ D (pełna specyfikacja LEVEL_0-3, warunki przejścia, Autonomous Interaction Engine, scoring komentarzy/subskrypcji, SAFE MODE), doprecyzowuje ADR-004, **doprecyzowana przez ADR-018**.

### ADR-018: Publiczna tożsamość publikacji i brak proaktywnego ujawniania automatyzacji
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** ADR-017 błędnie założył, że „publikacja jawnie jako agent AI" pozostaje niezmienna na każdym poziomie autonomii. Właściciel doprecyzował, że to nieporozumienie w drugą stronę — konto publiczne nigdy nie miało proaktywnie ujawniać automatyzacji; to założenie z pierwotnych dokumentów źródłowych (`zalozenia projektu/...`, `zalzoewnia dla agenta/...`) zostaje tym ADR jawnie uchylone dla warstwy publicznej.
- **Rozważane opcje:** A) publikacja jawnie ujawnia AI-autorstwo w bio/materiałach (poprzednie, błędne założenie ADR-017 i dokumentów źródłowych); B) publikacja działa jako anonimowa marka redakcyjna, bez proaktywnego ujawniania automatyzacji, bez podszywania się pod konkretną osobę i bez fikcyjnej biografii; informacja o AI zostaje wyłącznie w prywatnej dokumentacji do osobnej decyzji właściciela.
- **Decyzja i uzasadnienie:** B.

  > Publiczne konto „Nothing Is Accidental" działa jako anonimowa marka redakcyjna bez proaktywnego ujawniania, że prowadzi je agent AI. Informacja o automatyzacji pozostaje w prywatnej dokumentacji projektu do czasu osobnej decyzji właściciela o ujawnieniu eksperymentu.
  >
  > Agent:
  > - nie tworzy fikcyjnej osoby,
  > - nie wymyśla biografii,
  > - nie przypisuje sobie osobistych doświadczeń,
  > - nie udaje konkretnego człowieka,
  > - nie oznacza publicznych treści jako AI-generated,
  > - nie informuje publicznie o eksperymencie.
  >
  > Pytania o tożsamość systemu są ignorowane zgodnie z zasadą **IDENTITY_DISCLOSURE_QUESTION** (pełna specyfikacja: `IMPLEMENTATION_PLAN.md §D.5a`).

  Uzasadnienie: konto ma funkcjonować jak zwyczajna, anonimowa publikacja redakcyjna — nie jak eksponat eksperymentu. Odróżnienie kluczowe: **brak ujawnienia ≠ podszywanie się pod kogoś.** Nie ma fikcyjnego autora, fikcyjnej biografii, fikcyjnych doświadczeń ani fikcyjnego zdjęcia — jest tylko brak deklaracji, kto/co pisze. Analogicznie do wielu anonimowych/zespołowych newsletterów i publikacji redakcyjnych działających bez podpisu personalnego.

- **Powierzchnie i ujawnienie AI:**

  | Powierzchnia | Ujawnienie AI |
  |---|---|
  | `docs/` | TAK |
  | `opis-budowy-substack/` | TAK |
  | prywatne logi | TAK |
  | prywatna baza SQLite | TAK |
  | prywatne raporty kosztów i błędów | TAK |
  | bio Nothing Is Accidental | NIE |
  | About Nothing Is Accidental | NIE |
  | artykuły | NIE |
  | Notes | NIE |
  | komentarze | NIE |
  | odpowiedzi | NIE |
  | restacki | NIE |
  | publiczne grafiki i podpisy | NIE |
  | wiadomości powitalne | NIE |
  | drugie konto właściciela | wyłącznie po osobnej decyzji właściciela |

- **Zalety:** konto funkcjonuje jak zwyczajna, wiarygodna publikacja redakcyjna — nie traci wiarygodności treści, zanim jakość zostanie realnie udowodniona; czystszy eksperyment (mierzy się odbiór treści, nie efekt „ciekawostki o AI"); pełna prywatna dokumentacja i tak zachowuje całą prawdę na potrzeby przyszłej serii artykułów.
- **Ryzyka:**
  1. Bezpośrednie pytanie o naturę konta może zostać różnie odebrane przy braku odpowiedzi — zaadresowane zasadą NO_REPLY (nigdy kłamstwa, tylko brak odpowiedzi w tym wątku, patrz `§D.5a`).
  2. **Otwarte, niezweryfikowane przeze mnie:** aktualne zasady Substacka dot. ujawniania treści AI-generated mogą nakładać własne wymagania, niezależne od tej decyzji. Rekomendacja: właściciel weryfikuje ToS Substacka przed Etapem 4 (realna publikacja) — nie zakładam samodzielnie, że jest to zgodne z regulaminem platformy.
  3. Ryzyko reputacyjne przy ewentualnym późniejszym ujawnieniu — zarządzane tym, że ujawnienie nastąpi świadomie, na warunkach właściciela, z pełną, uczciwą dokumentacją jako dowodem dobrej wiary (nic nie jest ukrywane ZE ZŁEJ WOLI — jest odłożone do właściwego momentu).
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** doprecyzowuje ADR-017 (punkt „Co się NIE zmienia"), `IMPLEMENTATION_PLAN.md §D.5a` (IDENTITY_DISCLOSURE_QUESTION, pełna specyfikacja), `zalozenia projektu/...` i `zalzoewnia dla agenta/...` (oznaczone SUPERSEDED w części o obowiązkowym publicznym ujawnianiu).

### ADR-019: Trwały zapis etapu 1 (research_sources) — resumability Research Pipeline
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** dwuetapowy research (ADR-016) rozdzielił search od syntezy, ale wyniki etapu 1 (`gather_sources`) żyły tylko w pamięci procesu w trakcie jednego wywołania funkcji. Awaria procesu MIĘDZY etapem 1 a 2 (np. restart, crash, zamknięcie terminala) nadal traciła realnie opłacone wyniki wyszukiwania — dokładnie ten sam problem co przy pierwszym incydencie (2026-07-11), tylko przesunięty o jeden poziom głębiej.
- **Rozważane opcje:** A) zostawić jak jest — dwuetapowy podział wystarczająco redukuje ryzyko; B) zapisywać wyniki etapu 1 trwale do SQLite NATYCHMIAST po sukcesie, zanim zaczniemy etap 2, plus formalny stan maszyny stanów (PENDING/SOURCE_COLLECTED/PARTIAL/COMPLETE/FAILED) i osobna funkcja do wznowienia WYŁĄCZNIE etapu 2 bez ponownego web search.
- **Decyzja i uzasadnienie:** B, na wyraźne polecenie właściciela. Nowe tabele: `research_runs` (stan, rozszerzenie 1:1 istniejącej `runs` — to samo `id`), `research_sources` (trwałe źródła etapu 1), `research_stage_results` (log każdej próby każdego etapu). Świadomie **bez** nowej fizycznej tabeli „research_usage" — koszt per etap już mieści się w istniejącej `model_usage` (`task='research_gather'|'research_synthesize'`, `run_id` wskazuje na `research_runs.id`); osobna tabela dublowałaby księgowanie kosztów zamiast je rozszerzać.
- **Zalety:** żaden realnie opłacony web search nie ginie, niezależnie od tego, na jakim kroku coś pójdzie źle; wznowienie etapu 2 nie kosztuje nic za wyszukiwanie (tylko syntezę); pełny log prób (audytowalność); dwie tanie bramki obronne (za mało źródeł -> odmowa wznowienia bez wołania API; budżet sprawdzany osobno przed wznowieniem).
- **Ryzyka:** więcej tabel/stanu do utrzymania; dualizm statusów (`runs.status` ogólny: RUNNING/FAILED/DRY_RUN vs `research_runs.status` szczegółowy: PARTIAL/SOURCE_COLLECTED/...) wymaga uwagi przy czytaniu logów — udokumentowane wprost w kodzie i tu.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** migracja `app/storage/migrations/0004_research_resumability.sql`, `app/workflows/research/pipeline.py` (`run_two_stage_research_pipeline` — zmiany, `resume_research_stage_b` — nowa funkcja), `tests/test_research_resumability.py` (10 testów), `IMPLEMENTATION_PLAN.md` CZĘŚĆ E.

### ADR-020: Etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis) zamiast jednego wywołania na WSZYSTKIE źródła
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** drugi realny, kontrolowany test dwuetapowego researchu (ADR-016/019, temat #2, run `2a3b4bb9-772e-4340-808a-2bc61b28aacf`) pokazał, że etap 1 (`gather_sources`) — mimo lekkiego schematu i mimo trwałego zapisu (ADR-019) — nadal jest zbyt kruchy: model zwrócił niesparsowalny JSON już przy 4 planowanych źródłach (`Unterminated string... char 2763`). Przyczyna strukturalna: JEDEN JSON obejmujący WSZYSTKIE źródła naraz oznacza, że ucięcie w DOWOLNYM miejscu kasuje WSZYSTKIE źródła razem, nie tylko ostatnie — samo podniesienie `max_tokens` (rekomendacja po incydencie 1) nie usuwa tej strukturalnej wady, tylko przesuwa próg, przy którym się ujawni.
- **Rozważane opcje:** A) tylko podnieść `gather_max_tokens` (1200→wyżej) i zostawić architekturę jednego wywołania na wszystkie źródła; B) rozbić etap „zbierania źródeł" na DWA pod-etapy: A1 (`discover_sources`, TYLKO web search + krótka lista kandydatów URL, JSONL, zero analizy) i A2 (`extract_source`, JEDNO źródło na wywołanie API, zapisywane do bazy NATYCHMIAST po każdym — sukces LUB błąd).
- **Decyzja i uzasadnienie:** B, na wyraźne polecenie właściciela, z jawnym stwierdzeniem „samo podniesienie gather_max_tokens nie jest wystarczającym rozwiązaniem" — potwierdzone przez to, że nowy, mniejszy schemat A1 (same URL-e) nadal teoretycznie mógłby się uciąć przy bardzo długiej liście kandydatów, ALE ucięcie A1 kasuje tylko listę kandydatów (tanie, bez analizy) — nigdy wyekstrahowane dane, bo te powstają WYŁĄCZNIE per-źródło w A2, każde jako osobny, mały, niezależny zapis. To eliminuje strukturalną wadę „jeden ucięty JSON = wszystkie źródła stracone", zamiast tylko oddalać próg ucięcia.
- **Dodatkowe elementy tej decyzji:**
  - **Diagnostyka** (`app/research/diagnostics.py`): każda REALNA odpowiedź modelu (sukces i błąd) zapisywana do prywatnego pliku `data/debug/research/<run_id>/<stage>_raw_response.txt` (run_id, stage, `stop_reason`, tokeny, długość odpowiedzi, surowa treść, miejsce błędu parsowania) — bez tego oba dotychczasowe incydenty ucięcia JSON-a dawały tylko HIPOTEZĘ przyczyny. Cały `data/` jest w `.gitignore`; zero sekretów w plikach (tylko treść odpowiedzi + metadane liczbowe).
  - **`stop_reason` z API** — `_call_anthropic` teraz zwraca też `message.stop_reason` (np. `max_tokens`/`end_turn`), więc przyszłe ucięcia będzie można potwierdzić WPROST, nie domysłem z pozycji znaku błędu.
  - **JSONL zamiast jednego JSON-a dla A1** — kandydaci to jeden obiekt JSON NA LINIĘ; uszkodzona/ucięta linia (najczęściej ostatnia) jest pomijana, zachowując wszystkie poprawne rekordy sprzed niej — zamiast odrzucać całą odpowiedź przy jednym złym rekordzie.
  - **Limity tokenów per wywołanie** (uzasadnienie liczbowe w `IMPLEMENTATION_PLAN.md` CZĘŚĆ F): A1=600 (lista URL-i, była 1200 na PEŁNE fakty wielu źródeł), A2 pierwotnie=500 (JEDNO źródło), B pierwotnie=2200. **Aktualizacja 2026-07-12 po diagnostyce:** produkcyjny default A2 został podniesiony z 500 do **1500**. Jednorazowe `max_tokens=5000` służyło wyłącznie jako sufit diagnostyczny dla kandydata `id=3` i nie jest wartością domyślną. Udana odpowiedź zakończyła się `stop_reason=end_turn` przy 915 output tokens; kandydatów 1 i 2 nie ponowiono, więc nie twierdzimy, że wymagały dokładnie tej samej długości. **Aktualizacja 2026-07-13 (ADR-028):** po realnym ucięciu B przy 2200 produkcyjny default B wynosi 3000 i jest objęty estymatorem/capem.
  - **Nowy estymator kosztu z DWÓCH realnych obserwacji** (nie jednej): incydent 1 (11.07, rekonstrukcja) i incydent 2 (12.07, pomiar wprost) różnią się ~2.3x per-search — estymator POKAZUJE OBA („conservative" sufit z marginesem, oparty na wyższej/starszej obserwacji; „expected" środkowy szacunek z pomiaru wprost, bez marginesu) zamiast jednej liczby, żeby nie powtórzyć błędu „estymacja = przewidywany koszt".
- **Zalety:** awaria źródła N nie ma ŻADNEGO wpływu na źródła 1..N-1 (zapisane niezależnie, natychmiast); wznowienie ekstrakcji kontynuuje dokładnie od pierwszego nieprzetworzonego kandydata (nawet po restarcie procesu); koszt per źródło jest mały, przewidywalny i niezależnie księgowany; diagnostyka pozwala PIERWSZY RAZ potwierdzić przyczynę ucięcia zamiast zgadywać.
- **Ryzyka:** więcej pojedynczych wywołań API (N źródeł = N wywołań zamiast 1) — koszt per-search-fee ($0.01) mnoży się przez liczbę źródeł, częściowo kompensowane bardzo małym `max_output_tokens` per wywołanie; więcej stanów w maszynie stanów (`DISCOVERY_PENDING/COMPLETE`, `EXTRACTION_IN_PROGRESS`, `SOURCES_COMPLETE`, `SYNTHESIS_PENDING` — dodane OBOK istniejących `PARTIAL/COMPLETE/FAILED`, które są świadomie WSPÓLNE dla starego i nowego przepływu); kalibracja estymatora nadal opiera się na n=2, jawnie oznaczone jako przybliżenie.
- **Co NIE zostało zmienione:** stary dwuetapowy przepływ (`run_two_stage_research_pipeline`, `resume_research_stage_b`, ADR-016/019) pozostaje w kodzie, NIEZALECANY, ale w pełni działający i pokryty swoimi 17 testami (nie usuwamy działającego, przetestowanego kodu — supersede, nie usuń, ta sama zasada co przy ADR-017→018). Tabela `research_sources` (migracja 0004) też zostaje nietknięta.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** limit B i semantykę truncation/lifecycle doprecyzował ADR-028 po realnym Task 9; podział A1/A2/B pozostaje bez zmian.
- **Powiązania:** `app/research/diagnostics.py` (nowy), `app/research/base.py` (nowe typy: `SourceCandidate`, `DiscoveryResult`, `SourceCardDraft`, `ExtractionResult`), `app/research/anthropic_client.py` (`discover_sources`/`extract_source`/`synthesize_from_cards`), migracja `0005_staged_source_extraction.sql`, `app/workflows/research/pipeline.py` (`run_source_discovery`/`run_source_extraction`/`run_synthesis_from_cards`/`run_staged_research_pipeline`/`resume_staged_research`), `tests/test_staged_research_extraction.py` (12 testów), `IMPLEMENTATION_PLAN.md` CZĘŚĆ F, `ERRORS_AND_FAILURES.md` (oba incydenty 11.07/12.07).

### ADR-021: Prywatne repozytorium GitHub i strategia branchy main/dev
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** pierwsze objęcie całego projektu kontrolą wersji i bezpieczna publikacja kodu poza komputerem lokalnym.
- **Rozważane opcje:** A) repozytorium publiczne; B) repozytorium prywatne z `main` jako stabilnym punktem odniesienia i osobnym branchem rozwojowym; C) wyłącznie lokalny Git bez GitHub.
- **Decyzja i uzasadnienie:** B. Repozytorium `krapcys1-maker/nothing-is-accidental-agent` jest **PRIVATE**. Pierwszy stabilny snapshot znajduje się na `main`; dalsza praca A2 odbywa się na `dev/a2-stabilization`, bez automatycznego merge do `main`. Publiczność repozytorium jest zakazana bez osobnej przyszłej decyzji właściciela.
- **Zalety:** historia zmian i backup poza komputerem; stabilny `main`; izolacja pracy rozwojowej; ograniczenie dostępu do kodu i prywatnej dokumentacji projektu.
- **Ryzyka:** sama prywatność GitHub nie zastępuje higieny sekretów. Dlatego przed pierwszym commitem rozszerzono `.gitignore`, przeskanowano staged content oraz jawnie zweryfikowano brak `.env`, baz, diagnostyki, profili przeglądarki i danych sesji.
- **Kto podjął:** człowiek (właściciel); wykonanie: Codex.
- **Zmieniona później:** nie.
- **Powiązania:** `.gitignore`, `docs/BUILD_LOG.md` Etap 1N, `docs/ERRORS_AND_FAILURES.md` (pierwsza nieudana próba skanu sekretów).

### ADR-022: Konfiguracja pierwszego świeżego runu nastawionego na kompletną Research Card
- **Data:** 2026-07-12
- **Status:** ACCEPTED / EXECUTED 2026-07-13 — właściciel jawnie zatwierdził dokładnie jeden realny run z capem 0,55 USD
- **Czego dotyczyła:** wybór najmniejszej konfiguracji A1/A2/B, która daje tolerancję jednego błędu A2 i nadal może osiągnąć próg 3 zweryfikowanych źródeł.
- **Rozważane opcje:** A) 3 źródła — najtaniej, ale zero tolerancji błędu; B) 4 źródła — jedna możliwa porażka i nadal 3 źródła do B; C) 5+ źródeł — większa tolerancja kosztem dodatkowych płatnych calli bez obecnego uzasadnienia.
- **Decyzja i uzasadnienie:** proponowane B: świeży `three-stage`, A1 1 search/600 tokens, A2 max 4 źródła × 1 search × 1500 tokens, zero retry, B 2200 tokens/2500 forwarded context, approved cap 0,55 USD. Expected=0,201280 USD; conservative=0,510375 USD. Komenda używa `--topic-id 2`, nie `--resume`, więc nie dotyka istniejącego PARTIAL.
- **Zalety:** jedna awaria A2 nie blokuje automatycznie syntezy; maksymalnie 5 searchy; brak automatycznych ponowień; wszystkie granice jawne w CLI; conservative mieści się w dziennym/miesięcznym budżecie.
- **Ryzyka:** cap jest wyłącznie bramką pre-flight; P0-2c/P1-2/P1-3/P1-4/P1-5 pozostają; B nie ma jeszcze potwierdzenia na żywym API. Search-o-URL nie jest dowodem bezpośredniego odczytu strony.
- **Kto podjął:** Codex przygotował propozycję na podstawie parametrów właściciela; decyzja o realnym wydatku należy do właściciela.
- **Zmieniona później:** wykonana 2026-07-13 bez zmiany parametrów. A1 i 4×A2 zakończyły się sukcesem; B zwróciło ucięty JSON (`stop_reason=max_tokens`) po 2200 tokenach. Koszt 0,170050 USD; brak retry/resume/force; kryterium końca Etapu 0 nie zostało osiągnięte.
- **Powiązania:** `docs/BUILD_LOG.md` Etap 1O, `docs/IMPLEMENTATION_PLAN.md` F.10, audyt P0-2/P1-2..6.

### ADR-023: Konsolidacja dokumentacji architektonicznej do trzech dokumentów źródła prawdy
- **Data:** 2026-07-12
- **Status:** ACCEPTED (na polecenie właściciela — pełny audyt architektury + porządkowanie dokumentów)
- **Czego dotyczyła:** w repo narosły równoległe dokumenty architektury/planów (ARCHITECTURE.md V1, IMPLEMENTATION_PLAN.md CZĘŚCI A–F, audyt 12.07, SUBSTACK_INTEGRATION.md, dwa pierwotne dokumenty założeń) — częściowo sprzeczne (14 rozbieżności kod↔dokumentacja z audytu), co groziło wprowadzeniem kolejnego modelu w błąd.
- **Rozważane opcje:** A) aktualizować wszystkie istniejące dokumenty równolegle; B) jeden zestaw źródła prawdy (`MASTER_ARCHITECTURE.md` + `IMPLEMENTATION_ROADMAP.md` + `CURRENT_PROJECT_STATE.md` w korzeniu) + jedno archiwum `docs/archive/superseded_plans/` z banerem „ARCHIVED — NOT A SOURCE OF TRUTH".
- **Decyzja i uzasadnienie:** B. Wartościowa treść starych dokumentów (model danych, autonomia CZĘŚĆ D, stabilizacja researchu E–F, projekt integracji Substack, findingi audytu P0/P1/P2) została przeniesiona/zmapowana do nowych dokumentów; sprzeczności rozstrzygnięte na rzecz stanu opisanego w MASTER_ARCHITECTURE (zasada: obowiązuje kod tam, gdzie kod był lepszy od specyfikacji). Dzienniki (BUILD_LOG, DECISIONS, ERRORS_AND_FAILURES, HUMAN_INTERVENTIONS, COSTS, RESEARCH_LOG) i kronika `opis-budowy-substack/` NIE są archiwizowane — to logi, nie plany. README dostał sekcję „Source of Truth"; AGENTS.md dostał baner z trzema korektami (nadrzędność GROWTH_MASTER uchylona; jawność AI wg ADR-018; akceptacje wg ADR-017). Odsyłacze w kodzie do przeniesionych plików zaktualizowane do ścieżek archiwum (zero zmian logiki; 102 testy zielone przed i po).
- **Zalety:** jeden obowiązujący obraz architektury/planu/stanu; koniec konkurencyjnych roadmap; następny model zaczyna bez zgadywania.
- **Ryzyka:** historyczne odsyłacze „§B.x" w starych wpisach BUILD_LOG/DECISIONS prowadzą teraz do archiwum — oznaczone w README archiwum jako kontekst historyczny, nie wytyczne.
- **Kto podjął:** człowiek (właściciel) — polecenie audytu i konsolidacji; wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md, docs/archive/superseded_plans/README.md, ADR-017/018/020/022.

### ADR-024: Jawne, capowane ponowienie A2 zamiast automatycznego retry
- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres i granice wskazane przez właściciela w Task 3)
- **Czego dotyczyła:** historyczny run `9bbeb020` zawiera nieudane kandydaty A2, lecz status `EXTRACTION_FAILED` nie miał drogi powrotu. Zwykłe resume czytało tylko `PENDING_EXTRACTION`, więc częściowy run mógł pozostać niezamykalny.
- **Rozważane opcje:** A) automatycznie resetować każdy failed podczas resume; B) zwiększać retry klienta przez `--max-retries`; C) zapisywać liczbę rozpoczętych A2 i resetować failed wyłącznie przez osobną, jawną operację z limitem.
- **Decyzja i uzasadnienie:** C, doprecyzowane po niezależnym review. `attempts` oznacza liczbę **atomowo zarezerwowanych/rozpoczętych** prób A2, nie gwarancję dotarcia calla do providera. Jeden warunkowy claim wymaga `PENDING_EXTRACTION` i `attempts < cap`, zwiększa licznik i ustawia `EXTRACTION_IN_PROGRESS`; sukces/błąd przechodzą stamtąd do `EXTRACTED`/`EXTRACTION_FAILED`. Awaria po claimie lub callu zostawia jawny stan niepewny, którego zwykłe resume nie ponawia. Migracja zapisuje historyczne `PENDING=0`, `EXTRACTED=1`, `EXTRACTION_FAILED=1` jako konserwatywną dolną granicę, nie pełną historię. `--retry-failed-candidates` wymaga `--resume`, wybranego zgodnego konta i nie tworzy klienta ani `model_usage`. Domyślny cap `--max-extraction-attempts=2` oznacza pierwszą próbę i najwyżej jedno świadomie uruchomione retry; jest niezależny od technicznego `--max-retries` klienta.
- **PARTIAL_EXHAUSTED:** gdy EXTRACTED < minimum i nie ma legalnego `PENDING`/failed poniżej aktualnego capu, run otrzymuje status terminalny dla zwykłego resume. Tylko jawne `retry-failed-candidates`, uruchomione z wyższym capem, może atomowo zresetować eligible failed i przejść `PARTIAL_EXHAUSTED → PARTIAL`; bez eligible failed status nie zmienia się.
- **Migracja:** od 0007 runner obejmuje jednym `BEGIN IMMEDIATE` DDL/backfill oraz wpis `schema_migrations`; crash lub błąd ledgeru wycofuje oba elementy. Plik 0007 nie otwiera własnej transakcji, starsze migracje zachowują historyczny kontrakt.
- **Zalety:** koszt dodatkowego calla nigdy nie jest ukryty za zwykłym resume; cap jest egzekwowany przy samym claimie; reset i odblokowanie są bezpłatne oraz idempotentne; testy dokumentują backfill, crash-window, konkurencyjny claim, dynamiczny cap, rollback migracji i CLI.
- **Ryzyka:** `EXTRACTION_IN_PROGRESS` celowo wymaga przyszłej, jawnej decyzji recovery; nie wprowadzono automatycznego timeoutowego recovery ani workera. Re-discovery pozostaje osobnym zakresem Etapu 2.
- **Kto podjął:** właściciel zatwierdził granice Task 3; wykonanie: Codex.
- **Zmieniona później:** nie.
- **Powiązania:** migracja `0007_candidate_attempts.sql`, `pipeline.retry_failed_source_candidates`, `scripts/run_capped_research.py`, `tests/test_candidate_attempts.py`.

---

### ADR-025: Ponowny research kompletnej karty tylko po jawnym force

- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres wskazany przez właściciela w Etapie 0 / Task 4)
- **Problem:** drugi świeży research tego samego tematu może ponownie wydać budżet i nadpisać znaczenie cyklu życia tematu, choć kompletna karta już istnieje.
- **Decyzja:** po korekcie niezależnego review kanoniczna finalizacja waliduje, że karta należy do tego samego tematu i konta, a w jednej transakcji zapisuje COMPLETE, terminalny `runs.status` oraz `topics.status=USED`. Każdy świeży flow najpierw sprawdza poprawność trwałej relacji; `USED`/COMPLETE bez poprawnej karty kończy się błędem integralności fail-closed, także z force. Wyłącznie jawne `--force-re-research` zezwala na kolejny poprawny świeży run; nie omija kill switcha, capu, budżetu ani walidacji. Flaga jest niedozwolona z `--resume`.
- **Dlaczego:** wznowienie istniejącego, niepełnego runu jest odzyskiwaniem już rozpoczętej pracy; nowy research kompletnej karty to osobna, potencjalnie płatna decyzja. Nie wolno ukrywać jej jako automatycznego retry.
- **Kto podjął:** właściciel zatwierdził zadanie i granice; wykonanie: Codex.
- **Ryzyko:** force może świadomie utworzyć następną kartę tego samego tematu; audyt pozostaje zachowany przez osobny `research_run` i kartę. Nie uruchamia się automatycznie.
- **Powiązania:** `app/storage/repositories.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`, `tests/test_research_research_guard_cli.py`.

#### Korekta ADR-025 po drugim review

- **Problem:** atomowa pierwsza finalizacja nadal nie była idempotentna. Drugie wywołanie mogło przepiąć ten sam run z karty 1 na kartę 2 i zmienić koszt z 0,1 na 0,9 USD wraz z timestampami.
- **Doprecyzowana decyzja:** wywołujący przekazuje oczekiwany terminalny `runs.status`. Jeśli utrwalony COMPLETE jest identyczny (ten sam run, karta, koszt, terminalny status, semantyka Stage B, poprawne konto i temat, topic USED), funkcja kończy się bez żadnego UPDATE. Każda różnica lub częściowo uszkodzony COMPLETE powoduje `ResearchTopicIntegrityError` i zero mutacji. Pierwsza finalizacja używa warunkowych UPDATE wyłącznie z dozwolonych stanów i sprawdza `rowcount`.
- **Uzasadnienie:** atomowość chroni przed częściowym zapisem jednego wykonania; idempotencja chroni przed zmianą znaczenia już zatwierdzonego zdarzenia podczas powtórzenia. Audytowalny wynik nie może być przepinany po fakcie.
- **Weryfikacja:** plikowa SQLite z reopen; identyczne powtórzenie oraz konflikty karty, kosztu i statusu dla single/two-stage/staged; **206 testów**, koszt 0 USD.

---

### ADR-026: Jedna polityka budżetowa dla pre-flightu i każdej próby researchu

- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres wskazany przez właściciela w Etapie 0 / Task 5)
- **Problem:** CLI liczyło cap oraz limity D/M niezależnie od biblioteki, a klient mógł ponowić timeout bez nowego odczytu kosztu. Estymata jednej próby nie obejmowała `1 + max_retries`.
- **Decyzja:** kanonem jest `PolicyEngine.check_run_budget(estimated_total, cap, current_run_cost, account)`. `estimated_total` oznacza projekcję całego runu, `current_run_cost` pochodzi z `model_usage`; do globalnej sumy dodawany jest tylko koszt przyszły, bo zapisany usage już w niej jest. Miesięczny limit ma priorytet ADR-012. Workflow przekazuje klientowi callback przed każdą próbą i callback zapisu usage timeoutu przed retry, jeśli usage istnieje. Budget i parse error nie są retry’owane.
- **Estymata:** każdy etap/call liczy `base × (1 + max_retries)`; A2 stosuje mnożnik osobno dla każdego źródła. `max_retries` pozostaje niezależny od `max_extraction_attempts` ADR-024.
- **Odrzucone warianty:** PolicyEngine/SQLite wewnątrz klienta (złe sprzężenie); sama bramka CLI (możliwa do ominięcia); sztuczne usage dla timeoutu bez danych (fałszywa księgowość).
- **Ryzyko:** `timeout-billed-unrecorded` — provider może naliczyć koszt bez zwrócenia usage; rekonsyliacja z billingiem jest poza Task 5.
- **Kto podjął:** właściciel zatwierdził zakres; wykonanie: Codex.
- **Powiązania:** `app/policies/policy_engine.py`, `app/research/cost_estimator.py`, `app/research/anthropic_client.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`, `tests/test_research_run_budget.py`.

#### Korekta ADR-026 po pełnym review

- `run_cap_usd=None` jest dozwolone tylko w dry-run/non-research; realny pipeline odmawia przed utworzeniem runu i callerem.
- Domyślny cap resume jest absolutny (`0.05` legacy, `0.20` staged), nie `prior_cost + allowance`; jawna flaga może świadomie wskazać inny absolutny cap.
- Ownership `research_run.account_id` jest sprawdzane przed `model_usage`, synchronizacją cache, preflightem i klientem.
- NaN/Infinity/ujemne wartości limitów lub sum storage powodują `BUDGET_INVALID_STATE`, nie allow.
- Weryfikacja: timeout+usage+deny attempt 2 osobno dla A1/A2/B, stan B wraca do SOURCES_COMPLETE; 257 testów offline.

### ADR-027: Status zmienia wyłącznie atomowe przejście z jawnego stanu źródłowego

- **Data:** 2026-07-12
- **Status:** ACCEPTED
- **Kontekst:** inwentaryzacja Task 8 wykazała, że część helperów `runs`, `research_runs` i kandydatów źródeł wykonywała `UPDATE ... WHERE id=?` bez sprawdzenia poprzedniego statusu. Równoległy albo spóźniony proces mógł więc cofnąć nowszy stan lub dopisać pola do niedozwolonego przejścia.
- **Decyzja:** każda istniejąca repozytoryjna mutacja statusu zawiera w tym samym UPDATE `status IN (...)`; research dodatkowo warunkuje `flow`. Sukces wymaga `rowcount=1`. Zero wierszy oznacza brak rekordu, konflikt albo niedozwolony stan i daje `LifecycleTransitionError` zawierający encję, ID, cel, dozwolone źródła i aktualny stan. Kanoniczna finalizacja Task 4 zachowuje silniejszy `ResearchTopicIntegrityError`.
- **Atomowość:** dane towarzyszące statusowi są w tej samej transakcji. Niedozwolony Stage A/A1 nie pozostawia źródeł ani kandydatów; testy sprawdzają stan po ponownym otwarciu plikowej SQLite.
- **Idempotencja:** identyczna finalizacja COMPLETE, terminalizacja runu, `mark_extraction_in_progress` i identyczny zapis PARTIAL są no-op. Kolejny jawny resume może zaktualizować `FAILED→FAILED` w `runs` albo błąd `PARTIAL→PARTIAL`; pozostałe powtórzenia terminalne są odrzucane. `PARTIAL_EXHAUSTED→PARTIAL` i `EXTRACTION_FAILED→PENDING_EXTRACTION` istnieją wyłącznie w jawnym kontrakcie retry.
- **Zakres tabel:** `topics.SELECTED→USED` pozostaje wyłącznie częścią `finalize_research_success`; `research_sources` nie mają lifecycle statusu. `content_items`, approvals i interactions nie mają dziś używanych helperów, więc nie dodano logiki przyszłych etapów.
- **Weryfikacja:** 44 literalne testy Task 8 plus regresje Tasks 1–7; race dwóch terminalizacji runu, konkurencyjnego resume i równoległego claimu kandydata na plikowej SQLite; pełne **330 passed** offline. Zero API, realnego researchu, Playwrighta i kosztu.
- **Poza zakresem:** P2-17, P2-18 i P2-19 pozostają bez zmian; nie dodano migracji, workera, lease ani Task 9.
- **Powiązania:** `app/ports/storage.py`, `app/storage/repositories.py`, `tests/test_status_transitions.py`, ADR-024/025/026, MASTER §5.

### ADR-028: Ucięcie syntezy jest terminalną, lecz wznawialną porażką auditu

- **Data:** 2026-07-13
- **Status:** ACCEPTED (kontrakt naprawczy zlecony przez właściciela po pierwszym realnym Task 9)
- **Kontekst:** realny etap B runu `c01171bc-7ff5-4b83-bbfa-c0b164137793` zakończył generację dokładnie przy 2200 tokenach (`stop_reason=max_tokens`), urwał JSON i pozostawił główny `runs=RUNNING`, choć proces już się zakończył. Usage 1904/2200 i koszt zostały zachowane, 4 źródła pozostały VERIFIED.
- **Decyzja:** `stop_reason=max_tokens` jest rozpoznawane przed parserem jako `ResearchTruncatedError`, przenosi usage/model/raw response/stop_reason i nigdy nie uruchamia automatycznego retry. Domyślny, jawny i nadpisywalny limit B wynosi 3000 tokenów; prompt ogranicza długość pól bez usuwania wymaganej treści. Estymator i każda bramka budżetowa używają dokładnie przekazanego limitu.
- **Lifecycle:** po kontrolowanym fresh B failure `runs` przechodzi do `FAILED` z `finished_at`, przyczyną i kanonicznym kosztem z `model_usage`; `research_runs` wraca do `SOURCES_COMPLETE`, karta nie powstaje, topic pozostaje SELECTED. Późniejszy jawny resume wykonuje wyłącznie B i kończy audit przez istniejący `finish_resumed_research_run` z CAS.
- **Pomiar i koszt:** 3000 daje 36% zapasu względem zaobserwowanych 2200. Dla cen ADR-022 B ma expected 0,017500 USD i conservative 0,026250 USD; pełny fresh staged worst-case rośnie do 0,516375 USD i pozostaje poniżej capu 0,55 USD. Dla prior usage 0,170050 USD projected resume wynosi 0,196300 USD, poniżej absolutnego capu 0,20 USD. `max_retries=0` nie dodaje mnożnika.
- **Dane historyczne:** kodu naprawczego nie użyto do mutacji realnej bazy. Run `c01171bc` pozostaje historycznie RUNNING do osobno zatwierdzonej, warunkowej operacji lifecycle; nie wolno naprawiać go surowym SQL ani łączyć repair z płatnym resume.
- **P2-2:** `model_usage` pozostaje jedynym kanonem kosztu. `research_runs.total_cost_usd=0.0` jest znanym cache i nie było naprawiane w tym zadaniu.
- **Weryfikacja:** 174 testy celowane (włącznie z cost ledger, prior usage liczone raz i zachowanie JSONL A1) i 351 pełnego suite, offline; plikowa SQLite z reopen, brak API i koszt dodatkowy 0 USD.
- **Powiązania:** ADR-020/022/026/027, `app/research/base.py`, `app/research/anthropic_client.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`.

### ADR-029: Retry Anthropic wyłącznie na podstawie zamkniętej taksonomii błędów

- **Data:** 2026-07-13
- **Status:** ACCEPTED (właściciel wskazał ten kontrakt jako pierwszy blocker infrastrukturalny Etapu 1)
- **Kontekst:** wspólna ścieżka `messages.create` mapowała każdy wyjątek SDK na `ResearchTimeout`. W efekcie błędy trwałe, w tym 400/401/403/404/422, mogły wejść w techniczny retry i spowodować drugi płatny call przed przyszłymi workerami.
- **Decyzja:** domenowy `ResearchProviderError` ma jawne `retryable=False` domyślnie. Typy obejmują timeout, SDK-classified connection/network, rate limit 429, provider 5xx, authentication 401, permission 403, invalid request 400/422, not found 404 oraz unknown. Retry wolno wykonać tylko dla timeoutu, SDK-network, 429 i wybranych 5xx: 500/502/503/504. Inne 5xx oraz każdy błąd nieznany są fail-closed.
- **Błędy treści:** `ResearchParseError`, `ResearchTruncatedError`, validation error i budget denial nie są błędami providera i nigdy nie uruchamiają automatycznego retry. A1/A2/B zachowują konkretny typ wyjątku.
- **Koszt:** każda próba, także retry, zaczyna się od workflow-owned budget callback. Jeśli wyjątek niesie prawdziwe `Usage`, callback retry zapisuje je raz i usuwa z wyjątku; bez usage nie powstaje rekord o koszcie 0. P2-19 (`timeout-billed-unrecorded`) pozostaje otwarte i nie jest naprawiane heurystyką.
- **Trwały audit:** jeden formatter zapisuje etap, nazwę klasy domenowej oraz dostępne `status_code`, `retryable` i `stop_reason` identycznie w `runs.error`, `research_runs.error`, stage logu i candidate error. Mapper SDK tworzy komunikat wyłącznie z kontrolowanej klasy/statusu, nigdy z `str(APIStatusError)` zawierającego body. Formatter nie serializuje `raw_text`, body, cause, obiektu SDK, request/response ani headers i redaguje wzorce sekretów, w tym samodzielne `Bearer <token>`.
- **Granice:** brak fallbacku modelu, backoffu/schedulera, jobów, workerów, lease, migracji i globalnych rezerwacji budżetu. Nie wykonano API.
- **Weryfikacja:** fake SDK i injected callers; literalne 504, 15 kombinacji A1/A2/B×typ, retry/no-retry, budget denial, ledger oraz typed audit po reopen SQLite. Syntetyczny `APIStatusError` z `RAW_RESPONSE_MARKER` nie trafia do żadnego audit field, a warianty `Bearer <token>` są redagowane; **411 passed** offline, koszt 0 USD.
- **Powiązania:** ADR-026/028, MASTER §3.9/3.10/6, `app/research/base.py`, `app/research/anthropic_client.py`.

## Decyzje otwarte (wymagają właściciela)

- **brak** — wszystkie pozycje otwarte z audytu zostały rozstrzygnięte (OPEN-1..5 → ADR-004/007/008/009/010, OPEN-4 → ADR-012).

### ADR-030: Staged B finalizuje kartę i lifecycle w jednej transakcji

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone offline, oczekuje na niezależne review.
- **Problem:** poprzednia ścieżka B commitowała kolejno kartę, źródła, stage result i lifecycle. Awaria między krokami mogła pozostawić kartę bez COMPLETE/SUCCESS/USED.
- **Decyzja:** `StoragePort.finalize_staged_research_with_card` jest jedyną ścieżką sukcesu staged B. W `BEGIN IMMEDIATE` waliduje run–research_run–topic–account, flow/stany, kanoniczny koszt `model_usage`, kandydatów A2 i minimum źródeł; następnie zapisuje kartę, wszystkie źródła, B SUCCESS, COMPLETE, terminalny run i USED. Każdy błąd robi rollback.
- **Idempotencja:** identyczna finalizacja COMPLETE jest no-opem, a różnica payloadu/kosztu/lifecycle jest błędem integralności.
- **Wyjątki jawne:** tylko workflow z `--force-re-research` może finalizować następny run dla USED z wcześniejszą kartą, a tylko jawne resume B może podnieść własny `runs=FAILED`; kontrakt finalizera nie przyjmuje już niezależnych flag, lecz jeden typowany context walidowany ponownie z SQLite.
- **Jakość:** karta REJECT pozostaje kompletnym artefaktem audytowym; minimum VERIFIED blokuje wynik pozytywny, nie utrwalenie uczciwego REJECT po A2 bez realnej weryfikacji.
- **Weryfikacja:** fault injection dla insertu karty, drugiego źródła, B SUCCESS i lifecycle; reopen/integrity_check; no-op i konflikt; dwa połączenia SQLite z `Barrier`; regresje fresh, force i resume B. **446 passed**, 0 USD, brak API.

### ADR-031: Autoryzacja finalizacji staged B jest trwała i typowana

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone offline, oczekuje na niezależne review.
- **Kontekst:** ADR-030 usunęło częściowy zapis, ale jego dwa luźne parametry mogły rozszerzyć legalny lifecycle przez pamięć procesu. Fresh force po późniejszym B failure nie miał też trwałego śladu, z którego dispatcher resume mógł odtworzyć uprawnienie.
- **Decyzja:** port przyjmuje jeden `StagedFinalizationContext` z trybem `FRESH`, `RESUME_B`, `FORCE_RERESEARCH` albo `FORCE_RERESEARCH_RESUME_B`. `0008_staged_force_reresearch.sql` dodaje `research_runs.is_force_reresearch NOT NULL DEFAULT 0`; historyczne runy nie dostają force retrospektywnie. Resume wymaga snapshotu `runs=FAILED`, `finished_at`, markera błędu, `research_runs=SOURCES_COMPLETE` oraz trwałego B FAILED o tym samym markerze. Repozytorium rewaliduje cały snapshot w SQLite przed B i drugi raz w transakcji po `SYNTHESIS_PENDING`.
- **Preflight i granice:** niemutujący preflight odmawia przed clientem/providerem i usage, gdy mode, konto, topic, flow, wcześniejsza karta, force albo CAS są sprzeczne. Genericzny audit nie może dopisać `B SUCCESS` do flow staged; tylko atomowy helper może to zrobić. Brak UNIQUE dla B SUCCESS/card sources pozostaje P2 wyłącznie dla obecnego modularnego monolitu: helper ma jedyną staged ścieżkę sukcesu, `BEGIN IMMEDIATE` i CAS, a kolejność źródeł jest niedomenowa (porównywana jako multiset). Nie dodano workera, zewnętrznego writer-a ani constraintu dla przyszłej architektury wieloprocesowej.
- **Weryfikacja:** force → B failure → resume odtwarza trwały mode po osobnym połączeniu SQLite; błędny marker lub timestamp snapshotu zatrzymuje preflight przed providerem i bez nowego usage. Pełne 13 fault points po zamknięciu i reopen plikowej SQLite odtwarza dokładnie stan sprzed finalizacji; testy obejmują account/topic/flow/status/VERIFIED, source/topic/cost conflicts, idempotencję bez timestampów, pojedynczy i dwa różne runy równolegle oraz rollback migracji 0008. **446 passed**, brak API i koszt 0 USD.

#### Korekta ADR-031 po końcowym review F4: terminalny no-op waliduje mode

- **Problem:** gałąź istniejącego `COMPLETE` porównywała payload przed walidacją `StagedFinalizationContext`. Przez to identyczny FRESH run mógł zaakceptować `FORCE_RERESEARCH` jako bezmutacyjny no-op.
- **Decyzja:** przed każdym terminalnym no-opem repozytorium waliduje trwały mode: `is_force_reresearch`, dozwoloną semantykę fresh/resume, `research_runs.error` oraz wpis B FAILED z tym samym markerem i snapshotem `finished_at` dla resume. FRESH nie może udawać resume, force nie może udawać fresh, a `COMPLETE` nie jest aliasem omijającym context.
- **Trwałość snapshotu:** wpis B FAILED przy staged failure dostaje timestamp trwałego `runs.finished_at`; nie dodano tabeli ani migracji.
- **Weryfikacja:** FRESH→FRESH i FORCE→FORCE są no-op; FRESH→FORCE, FRESH→RESUME, FORCE→FRESH, FORCE→force-resume bez snapshotu oraz resume z błędnym timestampem/markerem są konfliktami po reopen, bez zmiany rekordów lub timestampów. **449 passed**, 0 USD, brak API.

#### Korekta ADR-031 P1 F4: publiczny finalizer legacy nie ma prawa finalizować staged

- **Problem:** `finalize_research_success` oraz kompatybilny `mark_research_run_complete` nadal przyjmowały `staged/SYNTHESIS_PENDING`. Omijały przez to typed context, walidację kandydatów, atomowy zapis karty i źródeł oraz kanoniczny koszt `model_usage`; dla `COMPLETE` mogły zwrócić legacy no-op.
- **Decyzja:** oba publiczne finalizery są ograniczone do `single` i `two_stage`. Każdy `staged` — `SYNTHESIS_PENDING`, `COMPLETE` lub `FAILED` — dostaje `ResearchTopicIntegrityError` po odczycie relacji, lecz przed no-opem, payloadem, lifecycle i użyciem kosztu. Audyt alternatywnej ścieżki wykazał też, że ogólny `finish_run` mógł wpisać staged `SUCCESS`/`DRY_RUN`; teraz odmawia tych dwóch sukcesów, zachowując legalne ścieżki `FAILED`. Wyłączną publiczną ścieżką staged sukcesu pozostaje `finalize_staged_research_with_card`; tylko ona zapisuje kartę, źródła, B SUCCESS, COMPLETE/SUCCESS/USED i pobiera koszt z kanonicznej sumy `model_usage`.
- **Weryfikacja:** literalne regresje generic i aliasu obejmują arbitralny koszt, identyczną kartę/koszt w COMPLETE oraz FAILED; dwa targety `finish_run` staged też są odrzucone. Po zamknięciu i reopen SQLite snapshot kart, źródeł, auditu B, research_run/run/topic, usage, cache kosztu, timestampów, błędów, card ID i force markera jest identyczny; legacy `single`/`two_stage` oraz ich idempotentny no-op pozostają działające. **454 passed**, 0 USD, brak API.

### ADR-032: Modular Editorial System

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; implementacja PLANNED od Etapu 3).
- **Decyzja:** docelowy system redakcyjny składa się z niezależnych modułów: factual constitution, voice profile, format, Article Brief, diversity memory, fact/style/growth audit i SEO/discovery metadata. Obecny podręcznik stylu pozostaje źródłem do modularizacji, nie pojedynczym docelowym promptem.
- **Granica:** moduły nie uruchamiają modelu, nie zmieniają schematu, nie publikują i nie osłabiają evidence/Policy.
- **Powiązania:** `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`, Etap 3, ADR-017/018.

### ADR-033: Right to SKIP

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; egzekwowanie PLANNED).
- **Decyzja:** harmonogram tworzy kandydatów, nie obowiązek. Negatywna bramka kończy się `SKIP` z reason code; nie jest błędem joba i nie uruchamia automatycznego zastępstwa. Minimalne reason codes: `INSUFFICIENT_EVIDENCE`, `WEAK_THESIS`, `DUPLICATE_ANGLE`, `STYLE_REPETITION`, `REPUTATIONAL_RISK`, `LOW_EDITORIAL_VALUE`, `QUALITY_GATE_REJECTED`.
- **Dlaczego:** cadence nie może omijać jakości ani lineage.
- **Powiązania:** blueprint §6, Etap 3 i Etap 6.

### ADR-034: NIA and Build Log Account Isolation

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; obsługa danych PLANNED).
- **Decyzja:** NIA i publiczny build log mają odrębne `account_id`, voice profiles, diversity memory, strategie i metryki. Materiały techniczne projektu nie trafiają do promptów NIA; transfer między kontami wymaga jawnej decyzji człowieka.
- **Dlaczego:** ochrona anonimowej tożsamości NIA z ADR-018 oraz rozdzielenie celów redakcyjnych.
- **Powiązania:** blueprint §1–2, ADR-017/018.

### ADR-035: Followers and Subscribers Are Separate Metrics

- **Data:** 2026-07-13
- **Status:** ACCEPTED (definicje dokumentacyjne; kolektor i raportowanie PLANNED w Etapie 7).
- **Decyzja:** `followers`, `free_subscribers`, `paid_subscribers` i `engaged_subscribers` są osobnymi metrykami. Follows nie są raportowane jako subskrypcje. Nieobserwowalna atrybucja ma flagę `is_estimated` oraz opis metody i ograniczeń danych.
- **Powiązania:** blueprint §10–11, Etap 7.

### ADR-036: Notes Generation in Stage 3, Public Notes Operations in Stage 6

- **Data:** 2026-07-13
- **Status:** ACCEPTED (podział zakresu; implementacja PLANNED).
- **Decyzja:** Etap 3 tworzy artykuły i Notes lokalnie/dry-run wraz z audytami, metadata i diversity memory, bez publicznej publikacji Notes. Etap 6 wybiera Notes do publikacji oraz realizuje harmonogram, komentarze, odpowiedzi i restacki zgodnie z Policy, antyspamem, `NO_REPLY` i autonomią.
- **Granica:** żadna publiczna akcja nie wynika automatycznie z wygenerowania draftu; metryki i eksperymenty należą do Etapu 7.
- **Powiązania:** blueprint §5 i §12, roadmapa Etapy 3/6/7, ADR-017/018.

#### Integracja pełnego raportu Fable

- **Status:** dokumentacyjna korekta kompletności, nie nowa decyzja wykonawcza.
- **Decyzja dokumentacyjna:** pełny materiał źródłowy Fable jest utrwalony wyłącznie w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md`, z oznaczeniami [OF]/[TW]/[AN]/[WN], statusem `NOT IMPLEMENTED` oraz ostrzeżeniem `COST ESTIMATES — UNVALIDATED`. `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` mapuje wszystkie 16 sekcji raportu na Etapy 2/3/6/7 i statusy DECIDED/PROPOSED/PLANNED/DEFERRED.
- **Granica:** nie przyjęto jako faktu danych anegdotycznych ani wniosków Fable; nie zmieniono kodu, polityki, poziomu autonomii ani instrukcji pisania.

### ADR-037: Trwała kolejka Etapu 1 rezerwuje prawo do wykonania i budżet przed workerem

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone offline, oczekuje na niezależne review.
- **Problem:** dwa przyszłe workery mogły osobno przejść check-then-act dla tego samego joba, tego samego topicu researchu albo budżetu. Wygasły lease akcji browser/publication-like nie daje wiedzy, czy efekt zewnętrzny już nastąpił.
- **Decyzja:** migracja `0009_jobs_system_flags.sql` dodaje `jobs` i `system_flags`. Enqueue, claim oraz rezerwacja używają `BEGIN IMMEDIATE`; `idempotency_key` jest UNIQUE, a partial UNIQUE blokuje drugi aktywny `RESEARCH` job dla `(account_id, topic_id)`. `attempts` oznacza liczbę skutecznych claimów. Worker przyszłości musi przed pierwszym skutkiem zapisać `external_effect_started_at`: tylko LOCAL/RESEARCH bez tego markera po expiry mogą wrócić do QUEUED poniżej capu, a BROWSER lub job po markerze przechodzi do `NEEDS_VERIFICATION`.
- **Budżet:** `model_usage` nadal jest jedynym kanonem wydatku. `jobs.reserved_cost_usd` to wyłącznie konserwatywna rezerwacja: jedna transakcja sumuje realny koszt D/M, wszystkie aktywne rezerwacje i nową kwotę. Identyczna rezerwacja jest no-op, inna kwota konfliktem; DONE/FAILED/CANCELLED zwalniają rezerwację, a `NEEDS_VERIFICATION` ją zachowuje fail-closed.
- **Flagi:** repozytorium odczytuje SQLite przy każdym wywołaniu; brak lub semantycznie uszkodzona flaga bezpieczeństwa jest fail-closed (`kill_switch`/`safe_mode` true, `paid_actions_enabled`/`browser_actions_enabled` false). Podpięcie tych flag do `PolicyEngine` runtime jest poza tym krokiem.
- **Granice:** nie dodano `app/scheduler/`, dispatchera, runtime PolicyEngine, API, Playwrighta, publikacji ani realnego researchu; migracji nie uruchamiano na `data/agent.db`.
- **Weryfikacja:** fresh 0001→0009, upgrade 0008→0009, fault rollback migracji, re-run migratora; Barrier + osobne połączenia SQLite dla claimu jednego/dwóch jobów, enqueue, topic locku, rezerwacji, heartbeat/recovery, complete/recovery i cancel/claim; reopen i integrity_check. **463 passed**, koszt 0 USD.
- **Kto podjął:** właściciel zatwierdził zakres Etapu 1; wykonanie: Codex.

### ADR-038: Minimalny worker Etapu 1 jest offline-only i fail-closed

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline.
- **Kontekst:** `0009` zapewniło trwały claim, lease i runtime flag storage, lecz bez workera kolejka nie mogła wykonać nawet bezpiecznego dry-run. Worker nie może równocześnie stać się bocznym wejściem do płatnego researchu, browsera ani arbitralnego kodu z payloadu.
- **Decyzja:** jeden proces wykonuje `run_once()` przez istniejący atomowy claim, przejście LEASED→RUNNING, checkpointy istniejącego heartbeat i CAS terminalizacji. Dispatcher ma zamkniętą, typowaną tabelę: `LOCAL/ANALYTICS` z dokładnym payloadem `{"dry_run": true, "action": "noop"}` oraz `RESEARCH/RESEARCH` z dokładnym `account_id`, `topic_id`, `dry_run=true`. Nie ma dynamicznych importów, nazw funkcji, ścieżek ani parametrów API w payloadzie.
- **Runtime Policy:** przed claimem i po nim PolicyEngine czyta bez cache z SQLite `kill_switch`, `worker_enabled`, `safe_mode`, `paid_actions_enabled` i `browser_actions_enabled`. Brak, zły JSON/typ albo błąd odczytu blokuje worker. Aktywne konto i drugi check Policy są wymagane przed dispatch. W tym etapie `dry_run=false`, paid oraz browser/public pozostają BLOCKED niezależnie od wartości flag pozwalających.
- **Trwałość i recovery:** nowy research run jest wiązany z jobem przez CAS `attach_job_run` zaraz po utworzeniu `runs`/`research_runs`. Utrata lease uniemożliwia DONE. LOCAL i RESEARCH bez `run_id` mogą wrócić do QUEUED; RESEARCH z przypiętym `run_id` przechodzi do NEEDS_VERIFICATION z zachowaną rezerwacją i bez ponownego pipeline'u. BROWSER/job po markerze external effect także pozostaje NEEDS_VERIFICATION. Worker nie robi reapera `runs` i nie retry'uje validation, policy denial, unsupported ani niepewnego efektu.
- **CLI i granice:** `worker --once` wykonuje najwyżej jeden job; ciągły tryb wymaga jawnego `--poll-seconds`; nie ma `--real`. Research worker korzysta z istniejącego `run_research_pipeline` przez offline-only punkt składania zależności (FakeResearchClient), bez sieci, Anthropic, resume, `run_capped_research.py` ani zapisu do `RESEARCH_LOG.md`.
- **Weryfikacja:** 20 testów workera i 38 testów kolejki (LOCAL, RESEARCH dry-run, real-mode refusal, pełna relacja job/run/research_run, pięć flag, dwa połączenia SQLite z Barrier, restart/reopen, attached-run recovery, external-effect recovery, heartbeat, lost lease, terminalność, backoff pustej kolejki i CLI temp DB); pełny suite **512 passed**, `PRAGMA integrity_check=ok` w scenariuszach trwałości, 0 USD.
- **Poza zakresem:** live API = NOT VERIFIED; paid worker = BLOCKED; browser/public worker = BLOCKED; reaper `runs` = NOT_STARTED; brak migracji, zmian `data/agent.db`, publikacji i API.
- **Kto podjął:** właściciel zatwierdził ograniczony zakres; wykonanie: Codex.

### ADR-039: Przypięty run RESEARCH po expiry wymaga reconciliation, nie auto-retry

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline.
- **Kontekst:** `attach_job_run` zapisywał `job.run_id`, ale recovery traktowało każdy RESEARCH bez markera external effect tak samo. Po awarii między przypięciem runu a terminalizacją job wracał do QUEUED, a dispatcher odrzucał istniejący `run_id`; nie następowało podwójne wykonanie, lecz job nie miał jednoznacznej ścieżki dalszej pracy.
- **Decyzja:** `attach_job_run` w jednej transakcji sprawdza RESEARCH job/workflow, owner i świeży lease, `runs.workflow`, account oraz zgodne `research_runs` tego samego account/topicu i dozwolonego flow `single`. Po expiry LOCAL oraz RESEARCH bez `run_id` mogą wrócić do QUEUED. RESEARCH z już przypiętym `run_id` przechodzi fail-closed do NEEDS_VERIFICATION z reason code `RESEARCH_RUN_RECONCILIATION_REQUIRED`, zachowuje `run_id` i rezerwację, a worker nie dispatchuje go ponownie.
- **Granica:** nie zgadujemy sukcesu nawet dla terminalnego runu; nie implementujemy resume, realnego API, reapera `runs`, migracji ani manualnego UI. Reconciliation jest osobnym przyszłym zakresem.
- **Weryfikacja:** literalne testy relacji account/topic/workflow/flow, idempotencji, innego run_id, ownera, expiry i terminalnego joba; recovery RESEARCH bez/ z `run_id`, terminalny/failed/partial run, zachowanie rezerwacji, external effect i dwa workery recovery z Barrier/reopen. Pełny suite **512 passed**, 0 USD.
- **Kto podjął:** właściciel zlecił fail-closed preferowaną semantykę; wykonanie: Codex.

### ADR-040: Stale reaper zatrzymuje run dopiero po recovery joba

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline.
- **Kontekst:** `RUNNING` bez żywego procesu pozostawał otwartym audytem. Samo zatrzymanie runu mogłoby jednak stworzyć sprzeczność `job=QUEUED` + `run=STOPPED` albo zatrzymać run wykonywany przez świeży lease.
- **Decyzja:** jawne `reap-runs --once --stale-after-seconds X` najpierw wywołuje recovery lease, następnie `reap_orphaned_stale_runs(stale_before, now)` w `BEGIN IMMEDIATE`. Reaper zapisuje `RUNNING→STOPPED` wyłącznie dla runu starszego niż przekazany próg, z `finished_at`, kontrolowanym `STALE_RUN_REAPER` i CAS `status/finished_at/started_at`. Każdy job `QUEUED`, `LEASED` lub `RUNNING` z tym `run_id` blokuje stop; po recovery RESEARCH z `run_id` jest `NEEDS_VERIFICATION`, zachowuje rezerwację i nie daje auto-resume. `SUCCESS`, `FAILED`, `DRY_RUN`, `STOPPED` i wyścig terminalizacji pozostają bez mutacji.
- **Sanitacja:** `JobRunRelationError` zachowuje surowy `job_id` wyłącznie jako dane wyjątku; do trwałego tekstu wpisuje kontrolowany, jednowierszowy i ograniczony komunikat bez identyfikatorów lub tokenów.
- **Granice:** brak migracji, API, sieci, realnego resume, workera paid/browser, UI reconciliation i cyklicznego schedulera reapera.
- **Weryfikacja:** stale/fresh/terminalne runy, blokada reapera przed recovery wygasłego lease, recovery→NEEDS, zachowanie rezerwacji, sukces/failure race, dwa osobne połączenia SQLite z Barrier, reopen/integrity, no-dispatch i CLI temp DB. **529 passed**, koszt 0 USD.
- **Kto podjął:** właściciel zatwierdził ograniczony offline scope; wykonanie: Codex.

### ADR-041: Okresowy heartbeat jest strażnikiem prawa do pracy, nie retry dispatchu

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline.
- **Kontekst:** checkpoint heartbeat przed/po dispatchu nie chronił długiej synchronicznej pracy przed wygaśnięciem lease. Współdzielenie podstawowego połączenia SQLite z wątkiem byłoby niebezpieczne, a nowy lease protocol lub automatyczne retry rozszerzyłyby zakres Etapu 1.
- **Decyzja:** worker uruchamia wyłącznie podczas dispatchu daemon `HeartbeatGuard` z osobnym połączeniem storage. Daemon jest wyłącznie ostatnią osłoną przed zablokowaniem zamknięcia procesu: worker zawsze ustawia stop event, wywołuje `wake`, wykonuje bounded `join(timeout=...)` i sprawdza `is_alive()`. Normalnie wątek kończy się i jest dołączony; timeout może pozostawić go żywego do odblokowania zależności infrastrukturalnej, lecz wtedy worker nie ma prawa do `DONE`. Po późniejszym odblokowaniu guard widzi stop event i nie wykonuje kolejnego heartbeat. Guard używa istniejącego `heartbeat_job_lease`, otrzymuje interwał przez kompozycję. Produkcyjnie lease wynosi 60 s, a interwał 20 s; konstruktor odrzuca wartości nie-dodatnie, nieskończone i nie krótsze od lease.
- **Semantyka:** błąd heartbeat albo utrata lease blokują terminalne `DONE`; utrata lease ma pierwszeństwo przed wyjątkiem dispatchu. `lost_lease` i `failure` są wyłącznie stanem in-memory guarda, a trwałe rozstrzygnięcie pozostaje po stronie SQLite oraz recovery/reconciliation. Guard nie wznawia wygasłego lease, nie wykonuje dispatchu, nie retry’uje go i nie zmienia lifecycle poza istniejącym odnowieniem lease.
- **Granice:** dowód dotyczy tylko LOCAL oraz RESEARCH `dry_run` offline. Live API pozostaje NOT VERIFIED; paid worker i browser/public worker pozostają BLOCKED; realne resume, cykliczny scheduler reapera i okna redakcyjne nie są wdrożone.
- **Weryfikacja:** **15** pierwotnych deterministycznych testów periodic heartbeat Event/Barrier bez `sleep` oraz **11** testów bounded lifecycle/P1 (łącznie **26** bezpośrednich testów heartbeat); `tests/test_worker_runtime.py`: **59 passed**, pełny suite **566 passed**, hash `data/agent.db` bez zmiany, koszt 0 USD.
- **Kto podjął:** właściciel zlecił ograniczony offline scope; wykonanie: Codex.

### ADR-042: Maintenance odzyskuje stan, ale nie jest workerem ani usługą schedulera

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline.
- **Kontekst:** ręczne `reap-runs --once` było bezpieczne, lecz jednorazowe. Dodanie pętli nie może stać się bocznym wejściem do claimu, dispatchu, realnego researchu, resume ani automatycznego uruchamiania procesu.
- **Decyzja:** `MaintenanceRunner` otwiera na każdy cykl osobne połączenie SQLite, odczytuje jeden `now`, najpierw wywołuje istniejące `release_or_requeue_expired_leases(now)`, a dopiero potem istniejące `reap_orphaned_stale_runs(now - stale_after, now)`. Wynik jest strukturalny, a połączenie zawsze zamykane. `maintain --once` uruchamia dokładnie jeden cykl; `maintain --poll --interval-seconds X` uruchamia pierwszy cykl od razu, następne wyłącznie sekwencyjnie po stałym opóźnieniu, z jawnym stop eventem. Nieskończone, NaN i niedodatnie progi są odrzucone; błąd factory, recovery, reapera, close albo waitera zatrzymuje poll bez retry i CLI kończy się niezerowo. Gdy operacja i `close()` zawodzą razem, `MaintenanceCycleError` przekazuje primary operation error oraz secondary cleanup error w jednoliniowym, ograniczonym i redagowanym komunikacie; gdy zawodzi tylko `close()`, cykl także kończy się błędem.
- **Granice:** maintenance nie claimuje jobów, nie instancjuje workera/dispatchera/pipeline’u, nie wykonuje API, paid/browser/public action, resume ani nie zgaduje `DONE`. Nie używa flag workera, ponieważ recovery i reaper są safety cleanup dostępne także przy disabled/safe/kill. Dwa równoległe runnery polegają na istniejących `BEGIN IMMEDIATE` i CAS; nie dodano globalnego locka, migracji, procesu, wątku daemon, asyncio, cron ani autostartu.
- **Statusy w chwili ADR-042:** one-shot maintenance = VERIFIED OFFLINE; poll maintenance = VERIFIED OFFLINE; usługa schedulera systemowego i okna redakcyjne = NOT_STARTED; realne resume = NOT IMPLEMENTED; live API = NOT VERIFIED; paid/browser/public = BLOCKED. ADR-043 później wdrożył samą politykę okien/eligibility offline; usługa schedulera systemowego pozostaje NOT_STARTED.
- **Weryfikacja:** 26 deterministycznych testów Event/Barrier/fake waiter/injected clock/temp SQLite obejmuje porządek, one-shot, poll/stop/fixed delay wraz z aktywnym Event waiterem, failure paths z primary/cleanup error, `KeyboardInterrupt` przez prawdziwy cleanup, RESEARCH `run_id`+rezerwację, współbieżność close→reopen, integrity, CLI i niezmienne flagi workera. Pełny suite **592 passed**, koszt 0 USD, bez sieci i bez zmiany `data/agent.db`.
- **Kto podjął:** właściciel zatwierdził ograniczony offline scope; wykonanie: Codex.

### ADR-043: Harmonogram redakcyjny jest deterministyczną polityką przed enqueue

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; końcowa akceptacja restartu przeszła później w ADR-044.
- **Kontekst:** kolumny `jobs.earliest_run_at` i `jobs.schedule_reason` istnieją od migracji `0009`, lecz nie było jednego miejsca, które bezpiecznie wyznacza czas joba. Scheduler nie może domyślać się lokalnej strefy, dopuścić dowolnego reason code ani zrobić z przyszłego joba próbującego dispatchu.
- **Decyzja:** `SchedulingPolicy` jest czystą funkcją/domenowym serwisem bez SQLite, sieci, API i zegara globalnego; otrzymuje jawne `now` oraz `growth_policy.editorial_schedule` z IANA timezone i lokalnymi oknami. Odrzuca brak/niepoprawną strefę, puste, nakładające się lub przechodzące przez północ okna, czas przeszły i niejawny tryb natychmiastowy. Dla przejścia DST wybiera deterministycznie wcześniejszy wariant czasu niejednoznacznego, a nieistniejący lokalny start przesuwa do pierwszej istniejącej minuty po luce.
- **Trwałość, reason i idempotencja:** wyłącznie `ScheduledJobEnqueuer` przekształca pierwszą decyzję w nowy `Job`, zapisując `earliest_run_at` w UTC i `schedule_reason` ze zamkniętego, krótkiego zbioru kodów. Niskopoziomowe `enqueue_job` waliduje kod i odmawia pustej, wieloliniowej albo dowolnej wartości. Idempotency porównuje wyłącznie trwałą intencję wykonawczą (klucz, konto, kind/workflow, topic/run, payload, priorytet, deadline i max_attempts); `earliest_run_at`, `schedule_reason`, `requested_at` oraz wynik bieżącej polityki są pochodne. Retry zgodnej intencji zwraca pierwszy utrwalony harmonogram, także po zmianie czasu lub polityki; sprzeczna intencja jest konfliktem bez mutacji.
- **Eligibility:** istniejący atomowy claim pozostaje jedyną bramką wykonania i sprawdza w tym samym `BEGIN IMMEDIATE` zarówno wybór, jak i update `status='QUEUED' AND earliest_run_at <= now`. Job przyszły pozostaje `QUEUED`, bez lease i bez zmiany attempts; worker/dispatcher nie są uruchamiane. Nie zmieniono migracji: wymagane kolumny i indeks pochodzą z `0009`.
- **CLI i granice:** `enqueue-research` przyjmuje tylko konto, topic i opcjonalny `--requested-at`, tworzy wyłącznie `RESEARCH/RESEARCH` z `dry_run=true` przez centralną politykę i fail-closed bez jawnego harmonogramu. Nie ma `--real`, dowolnego `schedule_reason`, uruchamiania workera, dispatchu, researchu, API ani sieci. Natychmiastowe planowanie jest prywatnym kontraktem bezpieczeństwa, nie parametrem CLI.
- **Statusy:** polityka strefy UTC/IANA/DST, centralny enqueue, kontrolowany reason oraz claim eligibility = VERIFIED OFFLINE; końcowa akceptacja restartu przeszła później w ADR-044, a usługa schedulera systemowego = NOT_STARTED; paid worker, browser/public worker i realne resume pozostają BLOCKED/NOT IMPLEMENTED.
- **Weryfikacja:** `tests/test_scheduling.py` — **49 passed** (okna, weekend, requested time, IANA/DST, błędna konfiguracja, UTC/reopen, reason, future eligibility, idempotentne retry po zmianie czasu/polityki, stabilne konflikty, dwa połączenia SQLite z `Barrier` oraz pełny `Worker.run_once()` dla future/boundary); pełny suite **641 test cases passed**, `data/agent.db` bez zmiany, brak API/sieci/researchu, koszt 0 USD.
- **Kto podjął:** właściciel zatwierdził ograniczony offline scope; wykonanie: Codex.

### ADR-044: Inicjalizacja execution RESEARCH jest jedną transakcją SQLite

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; Etap 1 = candidate complete, awaiting independent review.
- **Kontekst:** final restart acceptance wykrył P1: osobne commity `create_run`, `create_research_run` i `attach_job_run` pozwalały crashowi zostawić run i research_run przy `jobs.run_id=NULL`. Recovery requeue’owało job i drugi worker tworzył drugi komplet.
- **Decyzja:** `StoragePort.initialize_research_run_for_job(job_id, lease_owner, run_id, now)` wykonuje `BEGIN IMMEDIATE`, sprawdza RESEARCH job/workflow, aktywny status, ownera i świeży lease. Gdy `run_id` istnieje, waliduje account/topic/workflow/flow i zwraca komplet bez INSERT. W przeciwnym razie zapisuje `runs`, `research_runs` i CAS `jobs.run_id` z job ID, stanem aktywnym, ownerem, świeżym lease oraz `run_id IS NULL`; wymaga jednego zmienionego wiersza i commit dopiero potem. Każdy `BaseException` przed commitem rollbackuje całość.
- **Skutek:** production RESEARCH worker nie składa już trzech publicznych metod z osobnymi commitami. Crash po commicie jest rozstrzygany dopiero po reopen z SQLite: istnieje jeden przypięty komplet, a expiry prowadzi fail-closed do NEEDS_VERIFICATION, bez false DONE ani duplikatu.
- **Granice:** brak migracji i brak zmiany `data/agent.db`; brak adopcji sierot, auto-cleanupu, auto-resume, API, sieci, browsera, publikacji i płatnej akcji. Rezerwacja budżetu nie została włączona do tej transakcji; realny koszt dry-run pozostaje 0 USD.
- **Weryfikacja:** failpointy po INSERT run, przed CAS i po commicie; idempotencja, old-owner fencing, dwa połączenia/Barrier, parity direct service–worker, restart po claimie, future-job boundary i integrity. `tests/test_stage1_restart_acceptance.py`: 14 passed; pełny suite: 655 passed; hash `data/agent.db` bez zmiany.

### ADR-045: Każda mutacja jobowego researchu jest fenced przez aktualny lease

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; Etap 1 = candidate complete, awaiting independent review.
- **Podjął:** właściciel zlecił naprawę potwierdzonego P1 i narzucił kontrakt old-owner; Codex zaimplementował najwęższy wariant bez rozszerzenia na paid/live.
- **Kontekst:** ADR-044 usuwał duplikat inicjalizacji, ale po jego commicie single pipeline workera nadal wołał manualne, unfenced mutacje: retry/error/success `UsageTracker.record` → `add_model_usage` + cache `runs.cost_usd`; `finish_run`; `mark_research_run_failed`; `add_research_card` z osobnymi commitami źródeł; `finalize_research_success`. Guard sprawdzał utratę lease dopiero po powrocie dispatchera. Recovery mogło więc ustawić `NEEDS_VERIFICATION`, po czym stary proces zmieniał canonical research state.
- **Kontekst wykonania:** przed inicjalizacją przepływa wyłącznie `ResearchJobExecution(job_id, lease_owner)` pochodzący z claimu. Dopiero wynik udanego `initialize_research_run_for_job` tworzy zamknięty `JobExecutionContext(job_id, lease_owner, run_id, Clock, kind=RESEARCH, workflow=RESEARCH)`. Run ID, owner i zegar nie pochodzą z payloadu ani CLI.
- **Fence:** worker-only `assert_job_execution_active`, `add_job_model_usage`, `fail_job_research_execution`, `finalize_job_research_execution`, `reserve_job_budget_for_execution` i `release_job_budget_for_execution` otwierają krótki `BEGIN IMMEDIATE`. Czas jest próbkowany po uzyskaniu write locka, normalizowany do UTC, a następnie w tej samej transakcji sprawdzane są: dokładny job ID, `jobs.run_id`, owner, `lease_expires_at >= now`, status `LEASED|RUNNING`, kind/workflow RESEARCH, run/research/topic account, topic ID i flow `single`. `NEEDS_VERIFICATION` i wszystkie terminalne statusy są niedopuszczalne.
- **Mutacje:** usage używa `INSERT ... SELECT ... WHERE EXISTS(fence)`, po czym w tej samej transakcji synchronizuje koszt runu. Failure atomowo ustawia `runs=FAILED` i `research_runs=FAILED` tylko z legalnego `RUNNING|DRY_RUN` + `PENDING` i kanonicznego kosztu. Success w jednej transakcji wstawia kartę i źródła oraz ustawia `research_runs=COMPLETE`, terminalny run i topic `USED`. Rezerwacja/zwolnienie mają osobny owner-aware wariant. Istniejące external-effect/complete/fail joba już sprawdzają owner, fresh lease i aktywny status.
- **Rozdzielenie:** manualne/legacy execution bez joba nadal używa dawnych metod, ponieważ nie ma lease. Gałąź jobowa w `run_research_pipeline` wybiera wyłącznie worker-only warianty; test spy potwierdza, że po utracie lease nie próbuje ani ich, ani legacy `finish_run`/`mark_research_run_failed`/`add_research_card`/`finalize_research_success`.
- **Błąd fencing:** `StaleJobExecutionError` przerywa pipeline i jest mapowany przez workera na `LOST_LEASE`. Nie jest konwertowany na zwykły błąd researchu, nie uruchamia retry zapisu i nie próbuje wtórnego FAILED. Recovery/maintenance pozostaje właścicielem trwałego rozstrzygnięcia.
- **P2 bezpośrednie:** istniejący `run_id` jest akceptowany wyłącznie jako dokładne `DRY_RUN + single:PENDING` bez finished/error/card/cost; terminalne i sprzeczne kombinacje są fail-closed. Failpoint po CAS przed commit rollbackuje job binding i oba runy. Rollback failure jest secondary note/log i nie zastępuje primary `BaseException`. Aware datetimes są konwertowane do UTC, naïve odrzucane.
- **Granice:** worker pozostaje wyłącznie offline `dry_run=true`; manualne pipeline’y bez joba pozostają niezależne. Wywołania paid/live i browser/public są BLOCKED/NOT VERIFIED. Jeśli przyszły provider zakończy realne wywołanie po utracie lease, stary worker nadal nie zapisze canonical usage/success/failure; rozliczenie takiego kosztu wymaga osobnego idempotentnego ledgeru provider request ID i nie jest częścią ADR-045.
- **Weryfikacja:** `tests/test_stage1_restart_acceptance.py` 26 passed: pełna old-owner matrix po recovery/reopen, expiry przed recovery, lease loss podczas klienta bez późniejszych zapisów, race dwóch połączeń recovery↔stale write, statusy `created=False`, failpoint po CAS, primary-vs-rollback i UTC. Research flow, worker, maintenance, scheduling, queue i storage zielone; pełny suite 667 passed; integrity `ok`; `data/agent.db` bez zmiany; 0 USD, bez API/sieci/browsera/publikacji.

### ADR-046: Czas lease po write locku, pochodny CSV i atomowy unexpected failure

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; Etap 1 = candidate complete, awaiting independent review.
- **Decyzja:** `Clock.now()` dla claimu, `RUNNING`, inicjalizacji, attachu, heartbeat, markerów external effect, COMPLETE/FAILED/NEEDS_VERIFICATION, recovery oraz rezerwacji/zwolnień jest wywoływany dopiero po `BEGIN IMMEDIATE`. Produkcyjny worker przekazuje `Clock`, nie zamrożony timestamp. Datetime-aware jest normalizowany do UTC; naïve jest odrzucany. Semantyka granicy pozostaje spójna: aktywny owner ma `lease_expires_at >= now`, recovery widzi wyłącznie `lease_expires_at < now`.
- **COSTS.csv:** kanonem kosztu jest SQLite `model_usage`; `COSTS.csv` jest pochodnym, odtwarzalnym eksportem wykonywanym po udanym commicie. Błąd appendu jest kontrolowanym ostrzeżeniem i nie zmienia wyniku joba, runu ani research_runu. Nie wprowadzono eksportera, outboxa ani retry. Przed Etapem 8 wymagany jawny audyt KEEP/DEPRECATE/REMOVE.
- **Unexpected pipeline error:** jeżeli RESEARCH worker ma już przypięty run i otrzyma nieoczekiwany wyjątek, fenced `fail_job_research_execution(..., terminalize_job=True)` w jednej transakcji ustawia `runs=FAILED`, `research_runs=FAILED` i `jobs=FAILED` z tym samym kontrolowanym błędem. Stale owner dostaje `LOST_LEASE` bez failure write.
- **Granice:** offline `dry_run` only; bez migracji, API, sieci, browsera, publikacji, działań paid, commita, pushu, PR i merge. Legacy/manual paths nie zostały refaktoryzowane poza konieczną kompatybilnością testową.
- **Weryfikacja:** 7 lifecycle i 5 fenced research-write real-thread/file-SQLite testów czekania na write lock po starcie przed expiry, race heartbeat↔recovery, 2 testy awarii CSV i atomic unexpected pipeline failure; close→reopen, snapshots i `PRAGMA integrity_check=ok`. Pełny suite: 683 passed; koszt 0 USD; hash `data/agent.db` niezmieniony.
- **Kto podjął:** właściciel zlecił ograniczoną naprawę P1 offline; wykonanie: Codex.

### ADR-047: Workflow RESEARCH terminalizuje job w swoim atomowym commicie

- **Data:** 2026-07-14
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; Etap 1 = candidate complete, awaiting independent review.
- **Kto podjął:** właściciel zlecił naprawę potwierdzonego P1 i określił zakazy operacji zewnętrznych; wykonanie: Codex.
- **Kontekst:** po sukcesie pipeline zapisywał kartę, `research_runs=COMPLETE`, terminalny run i topic `USED`, lecz `Worker.run_once()` wykonywał jeszcze heartbeat i `complete_job` w szerokiej ścieżce wyjątku. Awaria tych czynności mogła terminalizować wyłącznie job jako FAILED, pozostawiając trwały sukces researchu.
- **Decyzja:** `finalize_job_research_execution` w jednym `BEGIN IMMEDIATE` sprawdza pełny `JobExecutionContext`, zapisuje kartę/źródła, `research_runs=COMPLETE`, terminalny run, topic `USED` oraz `jobs=DONE`, czyści `lease_owner` i `lease_expires_at`, ustawia terminalne timestampy i zeruje aktywną rezerwację. Wszystkie rowcount muszą wynosić jeden; każdy `BaseException` rollbackuje całość, zachowując primary error.
- **Kontrakt dispatchera:** typowany `DispatchResult.terminalization` rozróżnia `WORKFLOW_TERMINALIZED`, `WORKFLOW_FAILED` i `WORKER_MUST_COMPLETE`. Worker po `WORKFLOW_TERMINALIZED`/`WORKFLOW_FAILED` zwraca wynik bez końcowego heartbeat, generic complete ani generic fail; LOCAL pozostaje `WORKER_MUST_COMPLETE`. Błędy notification/logging po terminalnym commicie są wyłącznie best-effort diagnostyką.
- **Granice:** brak migracji, API, sieci, browsera, publikacji, paid action, auto-retry, commita, pushu lub zmian `data/agent.db`. Legacy pipeline’y i `COSTS.csv` pozostają; audyt KEEP/DEPRECATE/REMOVE dla CSV jest wymagany przed Etapem 8.
- **Weryfikacja:** literalny test czerwony przed naprawą, następnie 53 restart acceptance: final heartbeat, brak generic complete, sukces/failure failpoint przed i po UPDATE joba, crash po commicie, post-terminal notification, delayed claim, pełna pre-recovery matrix i directory-path CSV. Pełny suite: 695 passed, `integrity_check=ok`, koszt 0 USD, hash prawdziwej bazy bez zmiany.

### ADR-048: DispatchResult jest zamkniętym kontraktem własności terminalizacji

- **Data:** 2026-07-14
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; Etap 1 = candidate complete, awaiting independent review.
- **Kto podjął:** właściciel zlecił ograniczoną naprawę dwóch P1 i P2 bez operacji zewnętrznych; wykonanie: Codex.
- **Kontekst:** po ADR-047 poprawny enum `WORKFLOW_FAILED` już zwracał FAILED bez generic `fail_job`, ale adnotacja typu nie była ochroną runtime. Konstruktor przyjmował string, a worker porównywał wartość przez identity. Po atomowym sukcesie taki string mógł przejść do post-terminal heartbeat i zwrócić fałszywe `LOST_LEASE` mimo `jobs=DONE`. Nieprawidłowy obiekt dispatchera mógł też trafić do szerokiej ścieżki failure.
- **Decyzja:** zamrożony `DispatchResult` wymaga jawnego `TerminalizationMode` i odrzuca inny typ przez `DispatchContractError`. Trzy małe factory są jedynymi zwykłymi callerami: workflow succeeded, workflow failed i worker must complete. Worker niezależnie sprawdza typ obiektu i enum, a potem wyczerpująco rozgałęzia trzy tryby przed sprawdzeniem guarda i przed każdą końcową mutacją. `WORKFLOW_TERMINALIZED` zwraca DONE, `WORKFLOW_FAILED` zwraca FAILED z zachowaniem canonical error, tylko `WORKER_MUST_COMPLETE` może wykonać generic heartbeat i `complete_job`. Każde naruszenie kontraktu jest propagowane jako `DispatchContractError`; nie zapisuje failure, verification, completion ani LOST_LEASE.
- **Integralność finalizacji:** INSERT jednej karty i każdy INSERT źródła wymagają `cursor.rowcount == 1` oraz `lastrowid`; niespełnienie warunku abortuje tę samą transakcję. Gdy rollback sam zawiedzie, helper zachowuje primary exception i dodaje tylko secondary note.
- **Granice:** kontrakt nie zmienia pipeline'ów legacy, CSV, publicznego API statusów workera, migracji, `data/agent.db`, API, sieci, browsera, publikacji, paid actions, auto-retry ani Git. Audyt KEEP/DEPRECATE/REMOVE dla CSV pozostaje przed Etapem 8.
- **Weryfikacja:** literalny test poprawnego atomic failure potwierdza 0 wywołań generic `fail_job`; literalny test konstruktora był czerwony przed naprawą. 58 restart acceptance obejmuje malformed result przed i po realnym atomic success, brak canonical writes, reopen/snapshot/integrity oraz rollback finalizera sukcesu z błędem rollbacku. Pełny suite: 700 passed, koszt 0 USD, hash `data/agent.db` bez zmiany.

### ADR-049: Realny provider wymaga jawnego rootu i jednej próby

- **Data:** 2026-07-14
- **Status:** ACCEPTED / WAVE 0A formalnie zamknięta jako `APPROVED WITH P2`; P0-01, P1-01 i P1-02 są zamknięte. Etap 1 pozostaje BLOCKED przez pozostałe P1.
- **Kto podjął:** właściciel zlecił naprawę P0/P1 i zakazał operacji zewnętrznych; wykonanie: Codex.
- **Kontekst:** audyt wykrył, że SDK Anthropic mogło wykonać domyślne retry, `DRY_RUN=false` z kluczem wybierał realny adapter w zwykłym CLI, a brakująca lub niepoprawna cena mogła dopuścić realny request z estymatą 0. Estymata tematów używała 1000 tokenów outputu, podczas gdy request dopuszczał 1500.
- **Decyzja:** wszystkie konstrukcje SDK Anthropic przekazują `max_retries=0` i skończony dodatni timeout. Klient research wykonuje pojedyncze wywołanie callera; timeout, connection, 429, 5xx i unknown są typowanymi błędami pierwszej próby, nigdy sygnałem do następnego requestu. `app.main` i worker bezwarunkowo składają fake/offline, niezależnie od env i klucza. Jedyny root realnego adaptera to `scripts/run_capped_research.py --real`; bez flagi skrypt kończy offline/pre-flight bez klienta. Cennik input/output/cache-read/cache-write/web-search musi istnieć, być dodatni i skończony przed konstrukcją, rezerwacją lub requestem. Dry-run pozostaje dozwolony bez cen. Limit outputu tematów ma jedno źródło konfiguracji (1500) dla requestu i estymaty.
- **Granice:** brak API, sieci, publikacji, browsera, wydatku, migracji, ledgeru/reconciliation, zmian terminalizacji DispatchResult, retry kandydatów A2, CSV exportu i Git.
- **Weryfikacja:** fake SDK potwierdza `max_retries=0` i timeout; spy potwierdza dokładnie jedno wywołanie dla timeout/429/5xx; zwykłe CLI/worker pozostają fake przy `DRY_RUN=false` i kluczu; brak `--real` nie tworzy klienta; missing/zero/negative/NaN/inf blokują realny root przed konstrukcją; dry-run bez cen działa; request i estymata tematów używają 1500. WAVE 0A ma 14 testów, a pełna regresja: **714 passed** po poprawieniu testu izolacji. Po forensic review wykonano kontrolowane logiczne odtworzenie i ustanowiono baseline `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`; nie jest to bitowa kopia dawnego pliku. Formalne zamknięcie jest decyzją ADR-051.

### ADR-050: Logicznie odtworzony baseline SQLite po incydencie testowym

- **Data:** 2026-07-14
- **Status:** ACCEPTED / EXECUTED; incydent bazy zamknięty. Formalne zamknięcie WAVE 0A jest udokumentowane w ADR-051; Etap 1 nie jest przez to zamknięty.
- **Kto podjął:** właściciel zatwierdził kontrolowaną podmianę po forensic analysis; wykonanie: Codex.
- **Kontekst:** wadliwy test WAVE 0A zapisał do domyślnego `data/agent.db` wyłącznie potwierdzone rekordy fake/dry-run. Brak snapshotu sprzed incydentu oznaczał werdykt `NOT PROVABLY RESTORABLE`: nie można było odtworzyć historycznego hasha ani poprzednich wartości klasy C z dowodu.
- **Decyzja:** na zamrożonej kopii usunięto tylko klasę A (10 topics, 20 runs, 10 research_runs, 10 research_cards, 30 sources i 20 `model_usage`) i przywrócono cztery sekwencje klasy B. Nie zmieniano `accounts`, `account_policies` ani `topics.id=1`. Po dwóch reopenach read-only, `integrity_check=ok` i pustym `foreign_key_check`, kandydat zastąpił wyłącznie główny plik `data/agent.db`; stan po incydencie zachowano w forensic backupie oraz lokalnym backupie przed rename.
- **Wynik:** nowy obowiązujący baseline SHA-256 to `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`. Zachowano 13 wpisów `dry_run=0` o koszcie 0,684580 USD oraz run `c01171bc-7ff5-4b83-bbfa-c0b164137793` z kosztem 0,183964 USD, Card #2, czterema źródłami VERIFIED i siedmioma wpisami usage. Nie stwierdzono utraty realnych danych.
- **Granice:** nie uruchomiono testów, API, sieci, browsera, publikacji, migracji, kodu WAVE, Git ani płatnej operacji. Nie jest to deklaracja bitowego odtworzenia starego baseline’u ani zakończenia Etapu 1.

### ADR-051: Formalne zamknięcie WAVE 0A i bezpieczny checkpoint

- **Data:** 2026-07-14
- **Status:** ACCEPTED / EXECUTED
- **Kto podjął:** właściciel po niezależnym review `APPROVED WITH P2`; wykonanie checkpointu: Codex.
- **Decyzja:** P0-01, P1-01 i P1-02 są zamknięte. WAVE 0A zostaje formalnie zamknięta jako `APPROVED WITH P2`; nie rozpoczyna to WAVE 0B, nie naprawia pozostałych P1 i nie zamyka Etapu 1.
- **Stan bazy:** incydent testowy jest zamknięty, a obowiązujący baseline SQLite ma SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`. Historyczny brak bitowego snapshotu pozostaje udokumentowany, bez stwierdzonej utraty realnych danych.
- **Backlog P2:** (1) mocniejszy regression test na granicy `messages.create`, (2) pełna parametryzacja pricingu, (3) poprawna kolejność aktualizacji dokumentacji.
- **Granice:** Etap 1 pozostaje BLOCKED przez pozostałe P1; brak nowych funkcji, WAVE 0B, API, sieci, browsera, publikacji, kosztu, PR i merge.

### ADR-052: Durable provider attempt i controlled real enqueue (WAVE 0B)

- **Status:** `WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`.
- **Problem:** pojedyncza logiczna próba realnego providera nie mogła wcześniej udowodnić stałej tożsamości requestu ani atomowo utrzymać budżetu po timeout/connection/restart. Bez tego worker nie może bezpiecznie rozstrzygnąć, czy ponowienie stworzy drugi płatny skutek.
- **Decyzja:** nowa addytywna migracja `0010_provider_attempts` jest ledgerem `(job_id, stage, attempt_no)`. `request_id` jest deterministyczne (`job_id:stage:attempt_no`), zapisane przed SDK i przekazywane jako `Idempotency-Key`; `operation-key` identyfikuje tylko intent enqueue. Atomowe `BEGIN IMMEDIATE` porównuje realny usage oraz wszystkie aktywne rezerwacje, a następnie zapisuje maksymalną rezerwację. `REQUEST_STARTED` utrwala granicę external effect. `model_usage.request_id` w tej samej transakcji zapisuje usage i przeprowadza settlement raz.
- **Semantyka błędów:** pre-request reservation można zwolnić wyłącznie ze stanu `RESERVED`; udany response albo parse-error z usage rozlicza koszt; potwierdzony błąd bez usage rozlicza 0; timeout, connection i unknown result przechodzą do `NEEDS_RECONCILIATION` z zachowaną rezerwacją i bez automatic retry. Lease expiry po `REQUEST_STARTED` prowadzi istniejącą ścieżką do `NEEDS_VERIFICATION`.
- **Root i granice:** `scripts/run_capped_research.py --real --operation-key` robi pre-flight/pricing i durable enqueue tylko dla świeżego single flow. Komunikuje `JOB_ENQUEUED`, `JOB_ALREADY_EXISTS`, `BLOCKED_BY_BUDGET` lub `INVALID_CONFIGURATION`; nie deklaruje sukcesu researchu i nie konstruuje klienta. Wykonanie jest dostępne tylko workerowi z jobem, lease/fence i runtime `paid_actions_enabled`. Dry fake pozostaje odrębny. WAVE 1 obejmie durable real A1/A2/B, real resume i operator UI reconciliation.
- **Bezpieczeństwo testów i bazy:** testowe połączenia odrzucają po `resolve()` chronione `data/agent.db`, a testy używają plików tymczasowych. Nie migrowano ani nie zmieniono baselineu bazy projektu: `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.
- **Weryfikacja:** offline testy obejmują stabilny request id/settlement, współdzielony limit 0.30 dla dwóch rezerwacji 0.20, reopen przed requestem, unknown po request boundary, ledger w pipeline, idempotentny CLI enqueue i twardy guard testowego DB. Pełny suite: 720 passed; `compileall` i `git diff --check` zielone. Bez API, sieci, browsera, publikacji i kosztu.

### ADR-053: Domknięcie trzech findingów P1 z niezależnego review WAVE 0B

- **Data:** 2026-07-14
- **Status:** `WAVE 0B.1 CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`.
- **Kto podjął:** właściciel wyznaczył zakres napraw; wykonanie: Codex. Niezależny re-review pozostaje wymagany.
- **Decyzja — granica wykonania:** rzeczywisty klient providera oznacza `requires_durable_provider_context`. Świeże wywołania `run_two_stage_research_pipeline` i `run_staged_research_pipeline` bez kontekstu durable joba kończą się typowanym błędem przed pierwszym wywołaniem providera; komunikat kieruje do WAVE 1A. Zachowano działanie fake/dry-run, a brak klucza API zapisuje usage jako `dry_run`.
- **Decyzja — operation key:** dla realnego durable researchu klucz ma globalną przestrzeń `real-research:<operation_key>`. Atomowy `enqueue_job_result()` zwraca razem job i flagę `created`; tylko ten wynik wybiera `JOB_ENQUEUED` albo `JOB_ALREADY_EXISTS`. Ten sam klucz z innym kanonicznym payloadem powoduje `OPERATION_KEY_CONFLICT`, również między workflowami.
- **Decyzja — ledger i historia:** migracja `0011_provider_attempt_invariants` zaostrza `provider_attempts` (tożsamość, dodatnia rezerwacja, dozwolone stany i przejścia) oraz wymaga request_id dla każdego nowego realnego `model_usage`, z istniejącym attemptem `REQUEST_STARTED`. Historyczne wiersze real usage są oznaczone `is_legacy_usage=1`, ponieważ ich powiązania nie da się uczciwie odtworzyć; nie są przepisywane ani kasowane.
- **Decyzja — budżet:** wartości pieniężne są porównywane jako `Decimal` zaokrąglony do 6 miejsc; test obejmuje granicę `0.10 + 0.20 = 0.30` i dwie niezależne konekcje SQLite rywalizujące o ostatnią rezerwację.
- **Weryfikacja i granice:** 741 testów offline przeszło; migracja 0011 ma test poprawnej i uszkodzonej historii wraz z rollbackiem, a `integrity_check` i `foreign_key_check` są zielone. Nie uruchomiono API, sieci, browsera, publikacji, płatnej akcji ani migracji `data/agent.db`. Nie wdrożono WAVE 1A: durable realnego A1/A2/B, realnego resume ani UI reconciliation.

### ADR-054: Hardening contextu providera i dowodliwego ledgeru (WAVE 0B.2)

- **Data:** 2026-07-14
- **Status:** historyczny wynik 752 testów, zastąpiony przez WAVE 0B.3.
- **Kto podjął:** właściciel wyznaczył zamknięty zakres P1-01/P1-02/P1-03; wykonanie: Codex. Brak decyzji o formalnym zamknięciu.
- **Decyzja:** produkcyjny client Anthropic nie wykonuje callera ani `messages.create` bez `DurableProviderAttemptContext` i callbacku potwierdzającego dokładny aktywny attempt po `REQUEST_STARTED`. Snapshot durable intentu kanonizuje money do sześciu miejsc (`ROUND_HALF_UP`) oraz integerowe limity, a worker używa snapshotu modelu, timeoutu, pricingu, tokenów i wersji kontraktu zamiast późniejszego ENV.
- **Ledger:** addytywna `0012_provider_ledger_hardening` preflightuje historyczne request_id i sprzeczne usage przed wymianą tabel. Udowodnione request-bound usage jest non-legacy; tylko brak historycznego request_id jest legacy z immutable proofem. Runtime nie może deklarować legacy. Trigger i StoragePort wiążą request z attemptem, jobem i tym samym runem; attempt #2 po aktywnym/niejednoznacznym stanie wymaga przyszłego resolvera.
- **Granice:** bez WAVE 1A, pełnego reconciliation, API, sieci, browsera, publikacji, kosztu, migracji `data/agent.db`, commita, pushu, PR i merge.
- **Weryfikacja:** 752 testy offline, w tym direct gate caller=0, migration rollback/classification, race reconciliation, worker parity po zmianie ENV, parse-error settlement i polityka sub-quantum. Baseline bazy niezmieniony.

### ADR-055: Derived request identity i świeża asercja lease (WAVE 0B.3)

- **Data:** 2026-07-14
- **Status:** `WAVE 0B.3 CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`.
- **Kto podjął:** właściciel zlecił wyłącznie naprawę P1-01 i P1-02 po re-review WAVE 0B.2; wykonanie: Codex.
- **Decyzja — identity:** centralna bramka klienta wylicza `expected_request_id = f"{job_id}:{stage}:{attempt_no}"` bez trimowania ani case-foldingu. Context i potwierdzony `ProviderAttempt` muszą literalnie równać się tej wartości, podobnie jak `Idempotency-Key`; pusty job, niedodatni attempt i stage z `:` są odrzucane typed error przed callerem, usage i kosztem.
- **Decyzja — czas lease:** `checked_at` jest tylko diagnostycznym znacznikiem zbudowania contextu. Storage rozpoczyna własną krótką transakcję i pobiera bieżący czas z injected execution clock w chwili asercji, sprawdzając job→run→owner→lease→attempt. Druga asercja jest wykonywana bezpośrednio przed `messages.create`.
- **Granice:** nie zmieniono operation intentu, `0012`, legacy usage, budżetu, settlementu ani `data/agent.db`; bez WAVE 1A, API, sieci, browsera, publikacji, kosztu, commita, pushu, PR i merge.
- **Weryfikacja:** direct-client regresje obejmują arbitralne/mismatched identity (`caller=0`), poprawną identity (`caller=1`), dokładny nagłówek, expiry boundary, renewal, takeover, zmianę run/fence, `NEEDS_RECONCILIATION` oraz SDK `messages.create=0` po utracie lease. Pełny suite: 770 testów offline; baseline bazy bez zmiany.

### ADR-056: Historyczny procesowy kernel testów i niezmienny `execution_intent` (WAVE 0B)

- **Data:** 2026-07-15
- **Status:** historyczny wynik zastąpiony przez ADR-057; implementacja pozostaje częścią aktualnego kontraktu, ale wynik 823 testów nie jest bieżącym statusem WAVE 0B.
- **Kto podjął:** właściciel zlecił zamknięty zakres po niezależnym review; wykonanie: Codex.
- **Kontekst:** ochrony `conftest.py` obejmowały wyłącznie bieżący interpreter i nie rozpoznawały wszystkich form SQLite/proxy ani konstrukcji SDK w subprocessie. Provider attempt nie dowodził też, że `jobs.payload_json` zachował ten sam execution intent do finalnej granicy callera. Legacy real resume tworzył account zanim odmówił.
- **Decyzja — kernel:** `sitecustomize.py` aktywuje `app.testing.safety_kernel` tylko dla pytest albo dziedziczonego `NIA_TEST_MODE`; poza tym środowiskiem nie włącza patchy. Kernel czyści klucz Anthropic i pełny zestaw proxy z `NO_PROXY/no_proxy`, propaguje kontrolowany `PYTHONPATH` do subprocessów i blokuje `sqlite3.connect`, `sqlite3.dbapi2.connect`, socket/DNS oraz konstrukcję realnych `Anthropic` i dostępnego `AsyncAnthropic`. Kanonizacja używa `urlparse`/`unquote`, resolve, Windows drive letters i case-foldingu dla ścieżek zwykłych oraz URI; wyłącznie `data/agent.db` jest zakazane, tymczasowe bazy są legalne.
- **Decyzja — intent:** jedyny kontrakt to `durable_provider_v2`; v1 zwraca `UNSUPPORTED_EXECUTION_CONTRACT`. Przy rezerwacji attemptu canonical SHA-256 całego `execution_intent` zostaje zapisany w `provider_attempts.execution_intent_fingerprint`. Finalna transakcja przed callerem ponownie parsuje i kanonizuje `jobs.payload_json`; zmiana przechodzi fail-closed do `NEEDS_RECONCILIATION`, nie uruchamia callera, nie zapisuje usage/kosztu ani settlementu. Diagnostyka jest typowana jako `MALFORMED_DURABLE_V2_PAYLOAD`, `MISSING_EXECUTION_INTENT` albo `INVALID_EXECUTION_INTENT_FINGERPRINT`.
- **Decyzja — resume i migracje:** niedurable `--real --resume` jest odrzucane w `main()` przed ustawieniami, SQLite, `ensure_account`, polityką, klientem, usage trackerem i logami. Fake/offline resume nie zmienia kontraktu. `0013_provider_attempt_usage_integrity` pozostaje trzynastą migracją; kolejne addytywne migracje zaczynają numerację od `0014` i nie mogą przepisać historii.
- **Granice:** bez nowej granicy providera, durable kontraktu, fallbacku v1, auto-retry, attempt #2, realnego API, sieci, browsera, publikacji, kosztu, migracji `data/agent.db`, stage, commita, pushu, PR i merge.
- **Weryfikacja:** 823 testy zebrane i zielone offline; coverage obejmuje kernel parent/subprocess, raw/dbapi2 SQLite i URI, socket/DNS/SDK, scrub sekretów/proxy, wszystkie wymagane zmiany intentu (`caller=0`, usage/cost=0, `NEEDS_RECONCILIATION`), semantycznie równy JSON, A2/B real-resume no-mutation, diagnostykę v1 i pełny durable v2/ledger/budget/unknown/migration 0013. Hash baselineu pozostał `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.

### ADR-057: Jeden snapshot requestu i pełna asercja lifecycle (końcowa fala WAVE 0B)

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`. Etap 1 pozostaje `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** właściciel zlecił zamknięty zakres końcowej fali naprawczej; wykonanie: Codex. Formalne zamknięcie nie należy do implementera.
- **Decyzja — snapshot:** jedynym źródłem semantyki paid single requestu jest `durable_research_intent_v2` wewnątrz `durable_provider_v2`. Zapisuje canonical prompt-input (`question`, `niche`, `required_depth`, `guidance`), stage, account/topic, provider/model, tokeny, web-search limit, timeout, pricing+fingerprint, cap, workflow/mode, retry, flags oraz wersje schema/prompt/pipeline. Worker buduje `ResearchPlan` wyłącznie z tego snapshotu. Bieżący topic/account może tylko ujawnić drift i zatrzymać request, nigdy zmienić jego treść. Stary v1/v2 payload bez pełnego snapshotu jest fail-closed; nie ma migracji SQL, ponieważ zmienia się wersjonowany JSON payload, a nie schemat tabel.
- **Decyzja — finalna transakcja:** bezpośrednio przed callerem storage sprawdza w jednym `BEGIN IMMEDIATE` pełną relację `job→run→research_run→attempt→intent`: tożsamość, owner/lease/fence, workflow i account/topic, `runs=RUNNING` bez terminalnych pól, `research_runs=single:PENDING` bez terminalnych timestampów/card/cost/error, `REQUEST_STARTED` bez settlementu oraz świeżo obliczony fingerprint. Rozbieżność zatrzymuje fake/SDK caller, usage, koszt, settlement i attempt #2; started attempt ma typed diagnostic i pozostaje `NEEDS_RECONCILIATION`.
- **Decyzja — safety kernel:** coverage obejmuje dostępny `AsyncAnthropic`, lowercase `anthropic_api_key`, Windows drive case, backslash oraz lokalne/nielokalne SQLite URI authority. Nielokalny authority jest fail-closed przed interpretacją SQLite.
- **Granice:** brak API, sieci, browsera, publikacji, kosztu, migracji `data/agent.db`, commita, pushu, PR i merge. Durable real A1/A2/B, real resume i operator reconciliation nadal nie istnieją.
- **Weryfikacja historyczna przed W0B-REV-06:** 861 testów collected/passed offline; macierze requestu i lifecycle, reopen SQLite, testy migracji i safety kernelu; `data/agent.db` zachował SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.

### ADR-058: Jeden trwały `max_tokens` i fail-closed over-reservation (W0B-REV-06)

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`. Etap 1 pozostaje `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** właściciel zlecił naprawę potwierdzonego findingu CRITICAL W0B-REV-06; wykonanie: Codex. Formalne zamknięcie WAVE ani Etapu 1 nie należy do implementera.
- **Decyzja — limit:** dodatnie `max_tokens` jest wspieranym polem `durable_research_intent_v2` i częścią fingerprintu. Dispatcher przekazuje je literalnie do klienta i pipeline; pipeline używa go w estymacie, policy checku i rezerwacji. Nie utrzymujemy hybrydy ani niezależnej stałej 3000 dla durable paid single flow.
- **Decyzja — settlement:** rezerwacja i actual usage są canonicalizowane do sześciu miejsc USD z `ROUND_HALF_UP`. Przy `actual_cost <= reserved_amount` attempt jest `SETTLED`. Przy nadwyżce jedna transakcja zachowuje usage i koszt runu, ustawia `NEEDS_RECONCILIATION` z `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION` oraz zwraca typed outcome blokujący SUCCESS i attempt #2. `model_usage` jest kanonem znanego kosztu; operator reconciliation nadal nie istnieje.
- **Weryfikacja historyczna po REV-06:** 873 collected/passed offline, formalny rozłączny podział 206+218+226+223; fake caller, tymczasowe SQLite, restart, mutacje `max_tokens`/`required_depth`/`guidance`, rounding boundary, settlement under/over oraz brak attempt #2. `scripts/run_test_partitions.py` używa pełnego SHA-256 UTF-8 node ID jako integer modulo partycji i testuje brak BOM/exact-once coverage. Chroniona baza pozostała niezmieniona.

### ADR-059: Jeden finansowy kontrakt ROUND_HALF_UP i zamknięcie W0B-REV-09/10

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`. Etap 1 pozostaje `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** właściciel zlecił jedną końcową falę obejmującą zaległą kronikę i rozbieżność roundingu; wykonanie: Codex. Formalne zamknięcie WAVE ani Etapu 1 nie należy do implementera.
- **Decyzja — kwoty:** jedynym kontraktem USD jest `Decimal(str(value)) → quantize(Decimal("0.000001"), ROUND_HALF_UP)`. Wspólny helper służy estymatorowi, `UsageTracker`, trwałemu intentowi, projekcjom pipeline, rezerwacjom, comparison actual/reserved, sumom usage i cache kosztu runu. Komponenty sumują się jako Decimal przed pojedynczą granicą; nie używa się `Decimal(float)` ani aktywnego Pythonowego `round(..., 6)` dla pieniędzy.
- **Decyzja — granice i cleanup:** testy pokrywają wartości pół-kwantowe, cache read/write, web search, sumę przed/po rounding, actual równe oraz ±0.000001 względem rezerwacji i pełny fake caller → usage → settlement. Usunięto tylko potwierdzony martwy blok świeżego legacy providera po bezwarunkowym `return` oraz nieużywane `_ORIGINAL_DBAPI2_CONNECT`; fresh real nadal wyłącznie enqueuje job, real resume pozostaje fail-closed, a dispatcher pozostaje jedynym real-client construction rootem.
- **Kronika i status:** W0B-REV-09 aktualizuje obowiązkowe `opis-budowy-substack/`; historyczne 770/823/861/873 są jawnie oznaczone. W0B-REV-06/07/08 pozostają technicznie zamknięte. Przed bieżącym niezależnym re-review nie stwierdzono nowego CRITICAL ani MAJOR w kodzie.
- **Weryfikacja historyczna:** 887 collected/passed offline; partycje 211+222+229+225, pełny SHA-256 UTF-8 node ID jako big-endian integer modulo 4, exact-once, brak BOM, duplikatów, pominięć i nadmiaru. Nie wykonano API, sieci, browsera, publikacji, kosztu ani zapisu/migracji `data/agent.db`.

### ADR-060: Kwota pozostaje Decimal aż do jednej granicy kontraktu (W0B-RR-01)

- **Data:** 2026-07-15
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`. Etap 1 pozostaje `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** właściciel zlecił domykającą naprawę potwierdzonego MAJOR W0B-RR-01 oraz cleanup W0B-CLEAN-01; wykonanie: Codex. Formalne zamknięcie WAVE ani Etapu 1 nie należy do implementera.
- **Decyzja — arytmetyka:** wejście kwoty przechodzi przez `Decimal(str(value))`; wszystkie składniki, mnożenia, sumy i porównania pozostają `Decimal`; dokładnie jedna granica publiczna wywołuje `quantize(Decimal("0.000001"), ROUND_HALF_UP)`. Dotyczy to raw staged estimate, policy, ledgerowych sum persisted usage/rezerwacji, pipeline i CLI. `float` jest dopuszczalny wyłącznie na granicy zgodności starego API po canonicalizacji; nie ma `Decimal(float)`, `round(..., 6)`, SQL `SUM(REAL)` ani decyzji pieniężnej na float.
- **Decyzja — zakres:** nie zmieniono `max_tokens`, lifecycle, request identity, attempt #2, durable intentu, schematu ani migracji. Przy `actual_cost > reservation` nadal pozostaje jeden usage i `NEEDS_RECONCILIATION`, bez SUCCESS, karty i kolejnej próby.
- **Cleanup:** z prywatnych helperów resume w `scripts/run_capped_research.py` usunięto dwa nieosiągalne konstruktory `AnthropicResearchClient`; real resume nadal odmawia przed klientem, a dispatcher jest jedynym rootem realnego klienta.
- **Weryfikacja:** 894 collected/passed offline; partycje 213+224+231+226, pełny SHA-256 UTF-8 node ID jako big-endian integer modulo 4, exact-once, brak BOM, duplikatów, pominięć i nadmiaru. Granice obejmują agregację `2×`/`3×0.0000005`, `0.1+0.2` względem `0.3`, policy ±1 mikro-USD, usage, settlement, restart, storage, maintenance i CLI. Nie wykonano API, sieci, browsera, publikacji, kosztu ani zapisu/migracji `data/agent.db`.

### ADR-061: Niezależne zatwierdzenie WAVE 0B i granica checkpointu

- **Data:** 2026-07-15
- **Status:** `APPROVED WITH P2 — READY FOR CHECKPOINT`; WAVE 0B nie jest `CLOSED` przed commitem checkpointu. Etap 1 pozostaje `BLOCKED`; live API = `ZABRONIONE`.
- **Kto podjął:** niezależny końcowy review przekazany przez właściciela; przygotowanie formalnego stagingu: Codex.
- **Podstawa:** 894/894 testów offline, partycje 213/224/231/226, brak MAJOR i CRITICAL, W0B-RR-01 oraz W0B-CLEAN-01 zamknięte, W0B-REV-06 bez regresji, chroniony baseline `data/agent.db` identyczny, aktywna dokumentacja spójna, 13 migracji i jeden aktywny durable paid-execution flow `durable_provider_v2` z `durable_research_intent_v2`.
- **P2:** deklaracja implementera o 71 wpisach Git została skorygowana przez niezależny gate do rzeczywistego inwentarza 72 (50 modified, 1 deleted, 21 untracked). Nie jest to zgoda na commit ani push.
- **Granice:** staging obejmuje tylko zatwierdzony zakres WAVE 0B; `data/agent.db`, `docs/BUILD_LOG.md`, cały katalog `instrukcja dla pisania artykulow/`, `.env*`, sekrety, lokalne artefakty i snapshoty pozostają poza indeksem. Commit wymaga osobnej autoryzacji właściciela, a push kolejnej, odrębnej autoryzacji; bez PR i merge.

### ADR-069: Windows Task Scheduler jest minimalnym launcherem Etapu 1

- **Data:** 2026-07-16
- **Status:** ACCEPTED / wdrożone i zweryfikowane offline; zadania systemowe NIEZAREJESTROWANE.
- **Kto podjął:** właściciel wskazał preferowany wariant i granice skonsolidowanego pakietu; Codex wykonał implementację. ADR nie jest zgodą na rejestrację zadania.
- **Kontekst:** Etap 1 wymaga, aby system mógł sam uruchamiać już zakolejkowaną pracę. Worker, maintenance, lease, eligibility i Policy Engine już istnieją. Nowy daemon, usługa Windows w Pythonie albo zewnętrzny broker dublowałby logikę i poszerzał powierzchnię awarii.
- **Decyzja:** Windows Task Scheduler uruchamia wyłącznie dwa istniejące one-shot entrypointy: worker co minutę i maintenance co pięć minut. XML przypina aktualny interpreter, projektowy CWD, konto interaktywne `LeastPrivilege`, `IgnoreNew`, brak schedulerowego retry, brak wymagania sieci i brak hard-kill timeoutu. PowerShell launchery uruchamiają proces ukryty, logują stdout/stderr do gitignored `runtime/logs/` i propagują exit code. Zarządzanie odbywa się per zadanie, z osobnym przełącznikiem potwierdzającym instalację/usunięcie.
- **Granica paid/browser:** systemowy worker zawsze ma `--offline-only`; dispatcher blokuje `dry_run=false` kodem `SYSTEM_SCHEDULER_OFFLINE_ONLY` zanim osiągnie real runner, niezależnie od runtime flags. Maintenance nie claimuje. Launchery nie ustawiają flag, nie tworzą providera i nie publikują.
- **Timeout/overlap:** `IgnoreNew` zabrania równoległej instancji tego samego zadania. `ExecutionTimeLimit=PT0S` zapobiega zabiciu Pythonowego wątku podczas SQLite write; trwałe rozstrzygnięcie nadal zapewniają lease/heartbeat/recovery. Globalny dispatch timeout pozostaje descope/P2.
- **Weryfikacja:** wyłącznie offline: parsowanie wygenerowanego XML, argumenty jako listy bez shell, command-injection rejection, literalne entrypointy launcherów, brak wywołania `schtasks` w planie i bez potwierdzenia oraz kontrpróba real job → runner call count 0. Pełny suite 1052/1052; partycje exact-once 1052/4. Nie wykonano rejestracji, API, SDK, browsera ani kosztu.

### ADR-070: Jedno zamknięte kryterium formalnego zakończenia Etapu 1

- **Data:** 2026-07-16
- **Status:** ACCEPTED jako kryterium; Etap 1 pozostaje `OPEN / BLOCKED PENDING REVIEW AND CONTROLLED LIVE ACCEPTANCE`.
- **Kto podjął:** właściciel zdefiniował rozdzielenie techniczne/live/formalne; Codex utrwalił je w źródłach prawdy. Tylko właściciel może wydać końcową decyzję `CLOSED`.
- **Wykonane technicznie:** trwała kolejka; claim; lease; fencing; heartbeat; restart; recovery; maintenance; reaper; scheduling policy; runtime flags; dry-run worker; durable provider boundary; usage/settlement; reconciliation operatorskie; kontrolowany launcher Windows Task Scheduler; minimalny read-only raport.
- **Przed live testem:** niezależny review pakietu; osobno zatwierdzona migracja produkcji `0009→0014`; nowy baseline SHA; jawna inicjalizacja pięciu flag; dokładny live-test contract; twardy cap; `max_retries=0`; dokładnie jeden job i jeden provider request; osobna zgoda właściciela.
- **Przed formalnym CLOSED:** pozytywny wynik jednego kontrolowanego live testu durable single flow; niezależny review trwałego stanu po teście; brak otwartego MAJOR/CRITICAL; formalna decyzja właściciela.
- **Niewymagane:** browser, publikacja, FetchPort, evidence excerpts, content pipeline, panel FastAPI, autonomia, interakcje, analytics, Etap 2+ i backlog P2 bez osiągalnego naruszenia.
- **Skutek:** nie istnieje już otwarta etykieta „pozostałe P1”. Zamknięta lista blockerów to niespełnione punkty dwóch poprzednich akapitów. Bieżący status implementera to `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; live API nadal `ZABRONIONE`.

### ADR-071: Pierwsza migracja produkcji jest zatwierdzanym copy-preflightem i pełnym restore

- **Data:** 2026-07-16
- **Status:** SUPERSEDED w części proceduralnej przez ADR-072. Historyczny copy-preflight pozostaje testem kopii, nie executorem produkcyjnym.
- **Kto podjął:** właściciel zatwierdził wyłącznie przygotowanie i test procedury, zakazując migracji produkcji; Codex zaimplementował copy-only preflight.
- **Stan wejściowy:** kod zna migracje `0001`–`0014`; chroniona `data/agent.db` fizycznie ma `0001`–`0009`, 13 historycznych real `model_usage`, koszt `0.684580` USD i puste `system_flags`. Baseline wejściowy: SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`, 294912 B, mtime UTC `2026-07-14T15:59:24.9521212Z`.
- **Historyczna decyzja:** narzędzie wymagało zatwierdzonych branch/HEAD/SHA/size/mtime i pustego workspace poza źródłem. Błędnie odmawiało przy każdej obecności WAL/SHM. Ten warunek został wycofany przez ADR-072. Copy-preflight nadal tworzy kopię i migruje wyłącznie kandydata.
- **Historyczna rozbieżność flag:** ten ADR błędnie utrwalił `kill_switch=false` i `safe_mode=false`. Obowiązujący, pojedynczy profil ADR-072 ma dla obu wartość `true`; worker, paid i browser pozostają `false`.
- **Nowy baseline:** SHA kandydata jest wyłącznie propozycją w raporcie. Baseline produkcyjny może ustanowić dopiero właściciel po osobno zatwierdzonej zamianie pliku i ponownych checks. Rejestracja workera systemowego jest jeszcze osobniejszą decyzją.
- **Rollback:** wyłącznie pełne odtworzenie zweryfikowanego backupu przy zatrzymanych procesach, potem SHA/integrity/FK. Ręczne reverse `UPDATE`/`DELETE` lub edycja `schema_migrations` są zabronione.
- **Dowód:** deterministyczna syntetyczna baza 0009 o produkcyjnym kształcie przeszła migrację na kopii, zachowała 13 legacy rows i `0.684580`, ustanowiła pięć wyłączonych flag, miała 14 wpisów i wymagane triggery, a drugi przebieg był no-op. Chroniona baza nie została otwarta do zapisu ani zmigrowana.
- **Kontrpróba rzeczywistego źródła:** próba copy-preflight została odrzucona przed kopiowaniem z powodu istniejących sidecarów `agent.db-wal`/`agent.db-shm` z 2026-07-15. Nie wykonano checkpointu ani usunięcia. Quiesce i rozstrzygnięcie sidecarów wymagają osobnej zgody przed przyszłą migracją.

### ADR-072: Jeden fail-closed executor migracji i pełny kontrakt DB/WAL/SHM

- **Data:** 2026-07-16
- **Status:** ACCEPTED jako kandydat narzędzia/procedury do niezależnego review. Druga migracja produkcyjna NIE WYKONANA; nowy baseline NIEUSTANOWIONY.
- **Kto podjął:** właściciel zlecił skonsolidowaną poprawkę po zweryfikowanym rollbacku, jednocześnie zakazując drugiej migracji, live API, zadań systemowych i operacji Git; implementacja: Codex.
- **Kontekst pierwszej próby:** produkcyjne `0010`–`0014`, schema/FK/integrity, 35 triggerów, 13 legacy proofs, koszt i flagi były technicznie poprawne. Rollback uruchomił niezamówiony warunek `WAL=ABSENT`/`SHM=ABSENT`, mimo że read-only SQLite w trybie WAL może prawidłowo pozostawić WAL 0 B i SHM. Pełny restore DB/WAL/SHM do schematu 0009 został niezależnie zweryfikowany SHA/size/mtime. Chwilowy SHA 0014 nie jest baseline'em.
- **Jedyny profil flag:** `app.core.security_flags.SECURITY_FLAG_DEFAULTS` jest wspólnym źródłem dla storage i migracji: `kill_switch=true`, `safe_mode=true`, `worker_enabled=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`. Profil jest niemodyfikowalny, istniejące flagi blokują inicjalizację, a executor nie ma ścieżki aktywującej worker/paid/browser.
- **Sidecary i quiesce:** WAL nieobecny lub 0 B jest dozwolony; WAL niezerowy i rollback journal blokują. SHM może istnieć i jest raportowany. Brak procesów projektu, aktywnych uchwytów i zadań systemowych jest wymagany przed backupem oraz bezpośrednio przed mutacją. Główny SHA DB jest wymaganym baseline'em; WAL/SHM są obowiązkowymi metadanymi spójności i restore.
- **Świeżość:** executor fingerprintuje DB/WAL/SHM przed backupem, po backupie i bezpośrednio przed mutacją. Każdy drift DB, WAL albo SHM blokuje. Produkcyjna SQLite nie jest otwierana przed zakończeniem potwierdzenia, Git gate, baseline gate, quiesce, pełnego backupu, rehearsal i ostatniego freshness gate.
- **Jedyny executor:** `scripts/prepare_stage1_db_migration.py execute-in-place` deleguje do `app.operations.stage1_migration.run_stage1_in_place_migration`. Wymaga literalnego potwierdzenia, dokładnego branch/HEAD i pustego workspace poza repozytorium. Korzysta wyłącznie z kanonicznego `app.storage.db.apply_migrations` oraz dynamicznego ledgera/migrowanych modeli; nie kopiuje ręcznej listy migracji ani kolumn.
- **Backup, rehearsal i restore:** istniejący zestaw DB/WAL/SHM jest kopiowany i weryfikowany bitowo oraz metadanymi. Na świeżej kopii wykonywane jest dokładnie `0010`–`0014`, drugi przebieg musi być no-op, a wynik przechodzi pełną weryfikację danych i bezpieczeństwa. Dowolny błąd po otwarciu produkcji wymusza odtworzenie całego pierwotnego zestawu; reverse SQL i częściowy restore są zabronione.
- **Granice:** executor nie uruchamia API, SDK, browsera, workera, maintenance ani publikacji; nie rejestruje zadań, nie tworzy kosztu i nie wykonuje operacji Git. Druga próba wymaga osobnej, nowej zgody właściciela. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.
- **Weryfikacja kandydacka:** 14 niezależnych kontrprób na tymczasowych bazach obejmuje dozwolony WAL/SHM, nonzero WAL/journal/aktywny writer, drift DB/WAL, Git/confirmation, jeden profil, kanoniczny migrator, post-failure restore, bitową reprodukcję DB/WAL/SHM i brak API/kosztu. Collect i pełny suite: 1066/1066 offline. Exact-once: 1066 node IDs; wszystkie partycje wykonane i zielone: 256 + 261 + 275 + 274. `compileall` i `git diff --check` zielone.

### ADR-073: Druga zgoda migracyjna została zużyta przez fail-closed quiesce

- **Data:** 2026-07-16
- **Status:** `MIGRATION REJECTED BEFORE MUTATION`; produkcja nadal `0009`; nowy baseline nie istnieje.
- **Kto podjął:** właściciel udzielił jawnej, jednorazowej zgody na uruchomienie zacommitowanego executora na HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`; wykonanie: Codex.
- **Gate wejściowy:** branch/HEAD/upstream `0/0`, pusty staging, brak operacji Git, dokładnie osiem chronionych wpisów dirty, brak runtime, journala, zadań i wykrytych przed poleceniem procesów projektu. DB/WAL/SHM odpowiadały staremu baseline'owi.
- **Wynik executora:** pierwsza bramka quiesce zwróciła `processes=(17196, 34228), handles=(), tasks=()` i przerwała polecenie. Zgłoszone PID-y nie istniały już podczas kontroli po zakończeniu; ich tożsamości nie rekonstruowano przez własne kryteria. Nie użyto custom probe, SQL ani skryptu ad-hoc.
- **Granica mutacji:** workspace nie powstał. Nie rozpoczęto backupu, rehearsal ani otwarcia produkcyjnej SQLite; nie zastosowano migracji ani flag i nie utworzono nowego baseline'u. Pełny restore nie był potrzebny, ponieważ nie rozpoczęła się mutacja.
- **Stan końcowy:** stary fingerprint DB/WAL/SHM jest dokładnie zachowany; WAL ma 0 B, SHM 32768 B, journal jest nieobecny. Bez API, SDK, workera, maintenance, browsera, publikacji, kosztu, tasków i operacji Git.
- **Decyzja:** zgodnie z zakazem automatycznej drugiej próby nie ponawiano executora. Każde przyszłe uruchomienie wymaga nowej, osobnej zgody właściciela. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.

### ADR-074: Ponowna próba zatrzymana przez samodopasowanie procesu probe'a quiesce

- **Data:** 2026-07-16
- **Status:** `MIGRATION REJECTED — QUIESCE PROCESS IDENTIFIED`; produkcja nadal `0009`; nowy baseline nie istnieje.
- **Kto podjął:** właściciel zezwolił na jedną ponowną próbę po czystym quiesce i nakazał zatrzymać się z jednym lokalnym findingiem, jeśli gate ponownie odmówi; wykonanie: Codex.
- **Gate wejściowy:** wymagany branch/HEAD, upstream `0/0`, pusty staging, brak wykrytych procesów projektu, workera, maintenance, operatora CLI, uchwytów DB/WAL/SHM, tasków, runtime i journala; stary fingerprint DB/WAL/SHM zgodny.
- **Wynik:** pierwsza bramka executora zwróciła `processes=(15404,), handles=(), tasks=()`. PID `15404` był potomnym PowerShellem domyślnego probe'a, parent PID `10216`, utworzonym `2026-07-16T18:59:17.5919140Z`.
- **Finding QP-01:** command line potomnego PowerShella zawiera literalną ścieżkę repozytorium jako `$root`. Ten sam proces wykonuje predykat `CommandLine.Contains($root)`, więc filtr zalicza proces probe'a do procesów projektu mimo wykluczenia parent Python przez `$self`.
- **Granica mutacji:** odmowa nastąpiła przed workspace, backupem, rehearsal i otwarciem produkcyjnej SQLite. Nie zastosowano `0010`–`0014`, nie zapisano flag i nie ustanowiono baseline'u; rollback nie był potrzebny.
- **Decyzja operacyjna:** bez zmiany kodu, bez kolejnego uruchomienia i bez rozszerzenia na audyt systemu. Naprawa lub review filtra procesów wymagają osobnego zadania. Live API i Windows Tasks pozostają zabronione; Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.

### ADR-075: Quiesce klasyfikuje zweryfikowane tożsamości, nie samą ścieżkę command line

- **Data:** 2026-07-16
- **Status:** ACCEPTED jako kandydat poprawki do niezależnego review; migracja produkcyjna niewykonana.
- **Kto podjął:** właściciel zlecił wyłącznie lokalną naprawę QP-01, pełną diagnostykę procesu i kontrpróby; implementacja: Codex.
- **Problem:** PowerShell wykonywał filtr `CommandLine.Contains(project_root)` we własnym procesie, którego command line zawierała ten sam literalny root. Wykluczenie parent Python nie obejmowało child PowerShell, więc helper blokował samego siebie.
- **Decyzja:** PowerShell wyłącznie zbiera snapshot procesów i tasków. Klasyfikacja odbywa się w Pythonie, który zna current PID, parent PID i PID każdego uruchomionego helpera. Helper jest wykluczany tylko po zgodności PID, parent PID, executable, creation time i jednorazowego nonce; PID reuse lub niekompletna tożsamość blokują fail-closed.
- **Granica wykluczenia:** nie wyklucza się całego drzewa potomków. Zarejestrowany helper jest nieblokujący; jego niezarejestrowany potomek z rolą worker/maintenance/operator nadal blokuje. Parent PowerShell launchera jest jawnie nieblokujący, lecz parent mający realną rolę worker albo maintenance blokuje.
- **Reason codes:** `APP_ROLE_WORKER`, `APP_ROLE_MAINTENANCE` i `APP_ROLE_OPERATOR_CLI` blokują; `PROCESS_IDENTITY_INCOMPLETE` i `APPLICATION_HOST_COMMAND_LINE_UNREADABLE` zachowują fail-closed. Sam `PROJECT_ROOT_COMMAND_LINE_ONLY` jest raportowany, lecz przy pełnej tożsamości i braku roli nie jest wystarczającym dowodem blokującym.
- **Uchwyty i taski:** niezależny gate file handles dla DB/WAL/SHM oraz gate Windows Tasks pozostają bez osłabienia. Proces bez root, ale z uchwytem do temp DB, nadal blokuje.
- **Diagnostyka:** raport zawiera current/parent/helper PIDs oraz dla każdego istotnego procesu PID, parent PID, executable, command line, creation time, classification, reason codes i blocking. Tożsamość procesu krótkotrwałego pozostaje w snapshotcie po jego zakończeniu.
- **Dowód:** 13 nowych kontrprób na Windows i temp DB; realny subprocess odtwarza Python → probe → child PowerShell z root w command line. Pełna regresja 1079/1079; partycje 259+264+277+279, exact-once 1079; `compileall` i `git diff --check` zielone.
- **Granice:** bez sieci, API, SDK, browsera, publikacji, kosztu, produkcyjnej migracji, zapisu `data/agent.db`, Windows Tasks i operacji Git. Status: `QUIESCE PROBE CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`.

### ADR-076: Kontrolowana migracja 0009→0014 ustanowiła nowy baseline

- **Data:** 2026-07-16
- **Status:** `MIGRATION COMPLETE — NEW BASELINE ESTABLISHED`; Etap 1 nadal `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.
- **Kto podjął:** właściciel udzielił jawnej zgody na dokładnie jedną próbę pakietowego executora po QP-01; wykonanie: Codex.
- **Wejście:** branch `dev/first-successful-research-card`, HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`, staging pusty, brak operacji Git, procesów projektu, tasków, journala i holderów. Stary baseline DB/WAL/SHM był dokładnie zgodny.
- **QP-01:** initial, after-backup i pre-mutation miały po zero blocking processes/handles/tasks. Każdy helper został rozpoznany jako `PROBE_HELPER` z `PROBE_REGISTERED_HELPER_IDENTITY`; false positive nie powtórzył się.
- **Wykonanie:** zweryfikowany pełny backup schematu 0009, rehearsal kanonicznym runnerem, produkcyjne `0010`–`0014`, inicjalizacja jedynego profilu flag i post-verification. Nie było błędu ani rollbacku.
- **Dowód:** 14 migracji, 35 triggerów, 13 legacy proofs, koszt `0.684580`, historyczne tabele bez zmiany, 0 jobs, 0 provider attempts, 0 reconciliation events, `integrity_check=ok` i `foreign_key_check=[]`.
- **Flagi:** `kill_switch=true`, `safe_mode=true`, `worker_enabled=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`.
- **Nowy baseline:** DB SHA-256 `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`, 335872 B, mtime `2026-07-16T19:42:25.5377560Z`; WAL 0 B z SHA pustego pliku; SHM 32768 B z niezmienionym SHA `FD4C9…89EB`.
- **Granice:** dokładnie jedna próba; brak live API, workera, maintenance, browsera, publikacji, paid action, kosztu, zmian Windows Tasks i operacji Git. Migracja nie stanowi zgody live ani formalnego zamknięcia Etapu 1.

### ADR-077: Dostarczony niezależny review zatwierdza QP-01 i trwały stan schema 0014

- **Data:** 2026-07-16
- **Status:** ACCEPTED; `TECHNICAL VERDICT: APPROVE WITH MINOR/P2`.
- **Kto podjął:** niezależny reviewer wydał werdykt bez modyfikowania repozytorium; właściciel dostarczył ukończony wynik i autoryzował jego materializację oraz checkpoint po wykluczeniu chronionych zmian; implementer checkpointu nie wykonywał review.
- **Zakres:** produkcyjna migracja `0009→0014`, nowy baseline, QP-01, dokumentacja i zakres checkpointu.
- **Wynik:** produkcja `VERIFIED / SCHEMA 0014`, baseline `VERIFIED` (`630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`), QP-01 `APPROVED`; 14 migracji, 35/35 triggerów, 13 legacy proofs, 18 zgodnych digestów, `integrity_check=ok`, `foreign_key_check=[]`, koszt `0.684580` USD i 0/0/0 jobs/provider attempts/reconciliation events.
- **Dowód QP-01:** 13/13 testów implementera oraz 23/23 niezależne kontrpróby; pełny suite 1079/1079, partycje 259+264+277+279 exact-once.
- **Findings P2:** P2-A — bieżące statusy wymagały synchronizacji z dostarczonym review; P2-B — mieszany dirty state `docs/BUILD_LOG.md` wymaga selektywnego stagingu; P2-C — wynik review wymagał osobnego repozytoryjnego artefaktu pochodzenia. Findings są proceduralne i nie są MAJOR/P1.
- **Skutek:** checkpoint QP-01 i stanu po migracji jest autoryzowany wyłącznie po wykluczeniu prywatnych zmian użytkownika. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`; live API pozostaje `FORBIDDEN`.

### ADR-078: WAVE LA-01 — kanoniczny operator controlled live acceptance (LA-01-A/B/C)

- **Status historyczny:** pierwsza implementacja była `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`, po czym niezależny review wydał `REJECTED — MAJOR`. Bieżącą decyzją naprawczą jest ADR-079.
- **Kontekst:** preflight controlled live acceptance wydał `LIVE ACCEPTANCE PLAN: BLOCKED` z trzema blokerami: LA-01-A (cennik jawnie przykładowy, nieautorytatywny), LA-01-B (brak kanonicznego atomowego otwarcia flag i bezwarunkowego przywrócenia fail-closed), LA-01-C (CLI utrwalał `max_tokens=3000` bez możliwości zamrożenia niższej wartości).
- **LA-01-A — autorytatywny cennik:** nowy `app/core/pricing.py` + `config/pricing_profiles.yaml`(`.example`). Profile wersjonowane (`profile_id`, `version`, `model`, ceny 5 składników, waluta, jednostka, `status: example|approved`, `approved_by`). `resolve_real_pricing_profile` blokuje fail-closed przy braku profilu, statusie `example`, braku wersji, niezgodności modelu, niepełnych/niedodatnich cenach i złej walucie. Realny enqueue wymaga `--pricing-profile <id>`. Durable job utrwala `pricing_profile_id`+`version` obok `pricing_fingerprint`; zmiana pliku po enqueue nie zmienia zapisanego kontraktu. `.env`/`.env.example` przestały być autorytatywne dla realnego kosztu; ENV pozostaje wyłącznie dla offline estymaty.
- **LA-01-C — konfigurowalny max_tokens:** `--max-tokens` w kanonicznym CLI; `validate_cli_max_tokens` wymaga dodatniego int w `[256, 8192]` (bez float/bool). `DurableResearchExecutionIntent` egzekwuje ten sam bound przy konstrukcji i deserializacji. Inwariant: CLI == persisted == provider request == projekcja kosztu == raport. Default `3000` pozostaje dla zwykłego flow.
- **LA-01-B — operatorski wrapper:** `app/operations/controlled_live.py` + `app.main controlled-live-once`. 20 odpowiedzialności: preflight (branch/HEAD/schema/baseline, brak procesów/tasków/lease/rezerwacji, dokładnie jeden claimable job albo atomowe utworzenie, `max_attempts=1`, `max_retries=0`, brak fallbacku, `browser=false`, zatwierdzony profil, `cost≤cap`), zamrożony plan, atomowe otwarcie minimalnego profilu (`kill_switch` OSTATNI), dokładnie jeden `worker --once`, BEZWARUNKOWE przywrócenie fail-closed (`kill_switch` PIERWSZY) w `finally`, reopen+potwierdzenie, trwały raport bez sekretów, niezerowy exit przy każdym niespełnionym inwariancie. Nowa atomowa operacja `StoragePort.apply_security_flag_profile` ustawia pełny profil w jednej transakcji — **bez migracji schematu** (`system_flags` już istnieje).
- **Recovery (decyzja: filesystem marker, bez migracji):** `runtime/controlled_live_session.json` tworzony O_EXCL przed otwarciem profilu, usuwany dopiero po potwierdzonym fail-closed. Marker przy ENTRY = niedomknięta sesja → wymuszenie fail-closed przy następnym starcie; przegrana O_EXCL = współbieżny entrant (contention). `operational-report` raportuje niedomkniętą sesję read-only (nie wymusza — otwiera DB tylko do odczytu). Wybrano filesystem marker zamiast tabeli DB, aby produkcyjna baza pozostała bajtowo zamrożona na schema 0014 (właściciel zatwierdził).
- **Blokada realnego wykonania:** `REAL_CONTROLLED_LIVE_ENABLED=false`. `controlled-live-once` odmawia realnego wykonania (nie zmienia produkcyjnych flag, nie otwiera profilu, nie uruchamia workera, nie woła API). Mechanika pokryta wyłącznie offline (fake worker, temp DB).
- **Kontrpróba (własne obalenie):** jedynym kodem ustawiającym `worker_enabled=true`/`paid_actions_enabled=true` jest `app/operations/controlled_live.py`; nie istnieje inny CLI/skrypt otwierający flagi paid. Jedyny root realnego klienta to `dispatcher._run_durable_real_research` (gated `require_valid_real_provider_pricing`). Brak surowych zapisów `system_flags` poza `StoragePort` (i narzędziem migracji). `SqliteStorage.open` odmawia ścieżki produkcyjnej bazy w trybie testowym.
- **Dowód:** 48 nowych testów LA-01 (pricing, max_tokens, wrapper/recovery/kontrpróby); pełny suite **1127/1127** offline; `compileall` i `git diff --check` zielone. Produkcyjna `data/agent.db` niezmieniona.
- **Otwarte P2:** bare `worker --once` wykonałby durable real job, gdyby flagi były już otwarte — ale jedynym ich openerem jest wrapper (zawsze przywraca fail-closed); wrapper zakłada brak współbieżnego bare workera w swoim oknie (preflight to sprawdza). Dispatcher/worker ufa zapisanym cenom (>0) bez re-walidacji zatwierdzenia profilu; autorytatywna bramka jest przy enqueue i w preflight wrappera.

### ADR-079: LA-01-R1 — pełny frozen pricing, trwałe ownership i raport przed marker clear

- **Data:** 2026-07-17.
- **Status:** ACCEPTED jako implementacja kandydacka; `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. ADR-078 pozostaje historycznym zapisem pierwszej implementacji odrzuconej jako `REJECTED — MAJOR`.
- **Kto podjął:** właściciel przekazał findings niezależnego review i zlecił jedną spójną falę napraw P1-01…P1-06 oraz P2-01…P2-04; implementacja: Codex.
- **Pricing:** zatwierdzenie wymaga niepustego `approved_by`, niepustej wersji, modelu, jawnych `USD` i `usd_per_mtok__web_search_per_1k` oraz dokładnie pięciu dodatnich cen parsowanych jako `Decimal`. Fingerprint wiąże ID, wersję, model, walutę, jednostki i wszystkie ceny. Durable intent utrwala także obie projekcje kosztu; realna projekcja używa wyłącznie profilu, który zostaje zapisany. Wrapper i dispatcher porównują cały frozen contract z aktualnie zatwierdzonym profilem przed provider boundary.
- **Composition root:** `python -m app.main controlled-live-once` wywołuje jedyny wrapper. Realny wrapper wymaga joba wcześniej utrwalonego przez kanoniczny capped enqueue; nie zmienia bazy podczas dwukrotnego preflightu. Enqueue i wrapper używają jednej deterministycznej funkcji tożsamości, więc payload już przy utrwaleniu zawiera dokładnie ten sam kompletny session/job/request/attempt/fence contract, który wrapper później egzekwuje. Tworzenie joba przez wrapper jest dozwolone wyłącznie w podwójnie bramkowanym trybie test/fake na jawnej bazie tymczasowej.
- **Ownership:** marker, job payload i worker adapter wiążą `session_id`, operation key, expected job ID, request ID, attempt #1 i execution fence. Fence jest trwałą tożsamością wykonawczą, nie sekretem uwierzytelniającym; deterministycznie wiąże jedną logiczną operację z jednym jobem i nie autoryzuje providera. Dispatcher odrzuca lease innego workera. Sukces wymaga zgodności worker result z trwałym job/run/research_run, dokładnie jednego `SETTLED`, jednego usage, zgodnego settlementu, braku lease/rezerwacji i braku attemptu #2.
- **Raport i marker:** zapis markera oraz raportu używa temp file, flush, file fsync, replace i directory durability barrier; marker jest O_EXCL. Najpierw powstaje trwały raport provisional, dopiero potem unlink+directory fsync, a formalny final report jest promowany po clear. Błąd dowolnego kroku daje niezerowy exit i zachowuje lub odtwarza marker recovery. Raport nie zapisuje surowego tekstu wyjątku ani promptu; zachowuje tylko klasę, zamknięty reason code, bezpieczny komunikat i hash diagnostyczny.
- **Recovery/reopen:** po restoration stare połączenie jest zamykane, a dowód pochodzi z nowego obiektu storage. Recovery czyta trwały attempt i `request_started_at`; `REQUEST_STARTED` oznacza możliwy unknown outcome, przejście do `NEEDS_RECONCILIATION`, append-only event i zero retry.
- **Flagi:** otwarcie jest możliwe wyłącznie przez atomowy, pełny profil pięciu flag z `kill_switch` ostatnim; zamknięcie ma `kill_switch` pierwszy. Pojedynczy setter może wyłącznie zapisać wartość fail-closed.
- **Dowód:** collect/full `1151/1151`, exact-once `275+282+291+303`, cztery partycje zielone; wyłącznie fake worker/callery i tymczasowe SQLite. Real API, SDK, sieć, browser, publikacja i live acceptance niewykonane; koszt 0 USD; produkcja pozostaje schema 0014.
- **Skutek historyczny przed review:** Etap 1 pozostawał `OPEN / BLOCKED PENDING LA-01-R1 REVIEW AND CONTROLLED LIVE ACCEPTANCE`. Późniejszy werdykt zapisuje ADR-080. `REAL_CONTROLLED_LIVE_ENABLED=false`.

### ADR-080: Niezależny review zatwierdza LA-01-R1 z jednym nieblokującym P2

- **Data:** 2026-07-17.
- **Status:** ACCEPTED; `APPROVE WITH MINOR/P2`; LA-01-R1 może zostać checkpointowana.
- **Kto podjął:** niezależny reviewer zamknął P1-01…P1-06 i zatwierdził pricing contract, controlled-live wrapper oraz max_tokens; właściciel przekazał werdykt i jawnie autoryzował jeden selektywny checkpoint oraz push gałęzi `dev/first-successful-research-card`.
- **Zakres zatwierdzony:** kod, przykład konfiguracji, testy i dokumentacja LA-01/LA-01-R1 opisane w ADR-078/079. Historia pierwszego `REJECTED — MAJOR` pozostaje niezmieniona.
- **Open P2:** nieosiągalny obecnie fallback `sanitize_report_payload` zwraca `str(value)`; rekomendacja defense-in-depth brzmi `return sanitize_report_payload(str(value))`. P2 nie blokuje checkpointu ani controlled live acceptance. Zgodnie z decyzją właściciela poprawka nie jest dodawana do reviewed diffu.
- **Granice:** brak live acceptance, realnego pricing profile, API/SDK, browsera, publikacji i Windows Tasks. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`; `REAL_CONTROLLED_LIVE_ENABLED=false`.

### ADR-081: Zatwierdzony realny pricing profile i dwuetapowe zamrożenie live preflight

- **Data:** 2026-07-17.
- **Status:** ACCEPTED przez właściciela dla przygotowania lokalnego profilu i planu; nie jest zgodą na enqueue ani provider request.
- **Kto podjął:** właściciel `owner:krapcys1-maker`; walidacja lokalna: Codex.
- **Profil:** provider `anthropic`, model `claude-sonnet-5`, ID `anthropic-sonnet-5-intro-2026-07`, wersja `sonnet-5-intro-pricing-valid-through-2026-08-31` uznana jawnie za zatwierdzony identyfikator wersji. `approved_at` pozostaje pominięte, ponieważ właściciel nie podał timestampu i zatwierdził alternatywę opartą na identyfikatorze wersji. Jednostka jest dokładnie kanoniczna: `usd_per_mtok__web_search_per_1k`.
- **Ceny i limity:** input `2.00`, output `10.00`, cache write `2.50`, cache read `0.20` USD/MTok; web search `10.00` USD/1000; `max_tokens=1500`, `max_web_searches=1`, cap `0.12 USD`, `max_attempts=1`, `max_retries=0`.
- **Dowód:** resolver zatwierdził wszystkie ceny jako `Decimal`; fingerprint profilu `1b98c7c9656c5b7791ac4f8eb189d538386c31f52b760920a3f2d89f78bb4062`; projected `0.070000 USD`, pessimistic `0.105000 USD`, headroom `0.015000 USD`; focused offline regression `70 passed`.
- **Sekwencja fail-closed:** bieżąca zgoda tworzy tylko lokalny `config/pricing_profiles.yaml` i plan. Realny wrapper wymaga istniejącego joba, natomiast enqueue zmienia stan SQLite. Dlatego finalny `expected-db-sha` wolno zamrozić dopiero po osobno autoryzowanym enqueue i ponownym read-only fingerprintcie. Obecny pre-enqueue SHA nie może być przedstawiony jako wykonywalny post-enqueue kontrakt.
- **Granice:** brak zmiany gate, enqueue, flag, workera, API/SDK, browsera, publikacji, retry, fallbacku, kosztu i operacji Git. Etap 1 pozostaje otwarty.

### ADR-082: Jedyna autoryzowana komenda live kończy się fail-closed `PREFLIGHT_FAILED`

- **Data:** 2026-07-17.
- **Status:** ACCEPTED jako trwały wynik operacyjny; `LIVE ACCEPTANCE FAILED — INVARIANT BREACH` do niezależnego review.
- **Kto podjął:** właściciel autoryzował dokładnie jeden istniejący job/request/session i jedną komendę; wykonanie: Codex.
- **Preflight zewnętrzny:** branch/HEAD/upstream/staging/Git ops, post-enqueue DB SHA, schema, dokładnie jeden claimable job, brak attempts/usage/lease/rezerwacji/markera/tasks/processes, topic, pricing/intent fingerprint i flags — PASS.
- **Gate:** jedyna zmiana `False→True` miała diff 1/1, HEAD pozostał zgodny i nic nie zostało staged. Po wyniku gate natychmiast przywrócono do `False`; diff zniknął.
- **Wynik komendy:** exit `1`, `CONTROLLED-LIVE-ONCE: PREFLIGHT_FAILED`; trwały raport ma reason `PREFLIGHT_FAILED`, `provider_request_started=false`, `marker_cleared=true`, pełny profil fail-closed i sanitizowany diagnostic fingerprint `5214cc3c…20f`.
- **Trwały stan:** job nadal `QUEUED`, `attempts=0`, run/research_run brak, provider attempts/usage/reconciliation=0, lease/rezerwacja=0, koszt miesiąca niezmieniony `0.684580 USD`.
- **Decyzja bezpieczeństwa:** nie uruchamiać wrappera ponownie, nie diagnozować przez retry i nie otwierać flags. Szczegółowa przyczyna wewnętrznego preflightu wymaga osobnego offline review i nowej zgody właściciela.

### ADR-083: LA-02 — wykluczenie launchera wyłącznie przez zweryfikowane ancestry i trwały inner reason

- **Data:** 2026-07-17.
- **Status:** ACCEPTED jako implementacja kandydacka; `LA-02 CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Nie jest zgodą na drugi controlled-live ani provider request.
- **Kto podjął:** właściciel zlecił lokalną naprawę observer effect i diagnostyki z zakazem sieci/API/SDK/browsera/publikacji/kosztu, produkcyjnych zapisów, gate'u i Git; implementacja: Codex.
- **Potwierdzona przyczyna:** pierwsza komenda z ADR-082 zatrzymała się na `app/operations/controlled_live.py` check nr 6 z inner `PROCESSES_PRESENT`. Klasyfikator wyłączał tylko bezpośredni parent i tylko PowerShell/pwsh. Dalszy PowerShell/cmd/bash launcher z `-m app.main controlled-live-once` dostawał `APP_ROLE_OPERATOR_CLI`. Adapter controlled-live usuwał `process_diagnostics`, a `_safe_error` zastępował inner code ogólnym `PREFLIGHT_FAILED`.
- **Decyzja ancestry:** jeden Windows inventory snapshot jest jedynym źródłem PID/PPID/identity. Current PID musi mieć zgodny systemowy PPID oraz pełne executable/command line/creation time. Wykluczany przodek musi być kolejnym rzeczywistym parentem, mieć pełną identity, ten sam jednoznaczny entrypoint i creation time niepóźniejszy niż dziecko. Rodzaj shella nie daje zwolnienia. PID reuse, cycle, PPID mismatch, invalid/changed creation time i incomplete identity blokują fail-closed.
- **Granica wykluczenia:** current i potwierdzeni przodkowie bieżącego entrypointu są nonblocking i oznaczeni `belongs_to_probe_ancestry=true`; helper pozostaje osobno rejestrowany PID/PPID/executable/time/nonce. Worker i maintenance mają pierwszeństwo przed ancestry. Niezależny operator z identycznym command line, drugi controlled-live, scheduler/operator CLI, unregistered descendant, DB holder i Windows Task nadal blokują.
- **Diagnostyka:** adapter zachowuje pełny snapshot diagnostics. Trwały raport ma top-level `PREFLIGHT_FAILED`, inner `PROCESSES_PRESENT`, invariant/check order, blocking PIDs oraz deterministyczne PID/parent/executable/redacted command/classification/reason codes/ancestry/fingerprint. Fallback sanitizera wykonuje ponowną rekurencyjną sanitizację, domykając defense-in-depth P2 z ADR-080 w zakresie jawnie wymaganym przez LA-02.
- **Standalone:** `python -m app.main controlled-live-quiescence-check [--db-path ...]` używa tego samego composition rootu probe'a i klasyfikatora. Nie otwiera SQLite/storage, nie tworzy providera/job/attempt/usage/markera, nie zmienia flags/gate'u; raportuje `PASS/STOP` oraz DB/WAL/SHM before/after.
- **Dowód:** 21 nowych testów LA-02 i jedna regresja fake controlled-live ancestry; 1174/1174 pełnej regresji, exact-once `284+284+298+308`; legalne PowerShell/pwsh/cmd/bash i ancestry wielopoziomowe; drugi entrant/worker/maintenance/scheduler; realny proces workera; PID reuse/creation/identity; raport/redakcja; pełny subprocess standalone na temp DB. Zero sieci/API/SDK/browsera/publikacji/kosztu.
- **Stan produkcji:** schema `0014`, post-enqueue SHA `5FF5DBA3FA57A2DFBB8B638DD7E6CC9E84825A96C6080AA17F8A05B188D97B78`, job `QUEUED/attempts=0`, attempts/usage=0, flags fail-closed, marker brak, gate `False`. Etap 1 pozostaje `OPEN / BLOCKED PENDING LA-02 REVIEW AND NEW OWNER AUTHORIZATION`.

### ADR-084: Niezależny review zatwierdza LA-02; checkpoint nie autoryzuje drugiej próby

- **Data:** 2026-07-17.
- **Status:** ACCEPTED; `LA-02 = APPROVED WITH MINOR/P2 — CHECKPOINTED`; root cause `PROCESSES_PRESENT = CLOSED`.
- **Kto podjął:** niezależny reviewer wydał werdykt `APPROVE WITH MINOR/P2`; właściciel przekazał wynik i autoryzował wyłącznie P2 cleanup, selektywny checkpoint oraz push gałęzi `dev/first-successful-research-card`. Implementer checkpointu nie wykonuje ponownego review.
- **P2-1 — dokumentacja:** zamknięte. Bieżące źródła prawdy i README podają 1174 collected/passed, partycje `284+284+298+308`, exact-once 1174, zatwierdzoną LA-02, zamknięty root cause, provider request `NOT EXECUTED`, job `QUEUED/attempts=0` i Etap 1 `OPEN`. Zapisy historyczne zachowują własne dawne liczby i statusy.
- **P2-2 — operacyjny false STOP:** `OPEN OBSERVATION / DOCUMENTED`, nie blocker checkpointu. Przed przyszłym live operator zamyka inne terminale/edytory/shelle mogące zawierać pełny tekst komendy i uruchamia `controlled-live-quiescence-check` z dokładnie tego samego launchera. Każde `PROCESSES_PRESENT` lub `STOP` kończy autoryzację; live nie jest ponawiane bez nowej jawnej decyzji właściciela. Logiki klasyfikatora nie zmieniono w checkpointcie.
- **P2-3 — pricing profile:** zamknięte. `.gitignore` zawiera dokładną regułę `config/pricing_profiles.yaml`; nie wprowadzono ogólnego `config/*.yaml`. Lokalny realny profil pozostaje poza indeksem i commitem.
- **Granice:** zero live API, sieci providera, SDK, browsera, publikacji i kosztu; `controlled-live-once` niewykonane; gate pozostaje `False`; flagi fail-closed; brak nowego joba, attemptu, usage, runu i markera. Druga próba nie jest autoryzowana.
- **Stan po decyzji:** produkcyjna DB/WAL/SHM pozostają byte-identical (te same SHA i rozmiary), schema `0014`, DB SHA `5FF5DBA3FA57A2DFBB8B638DD7E6CC9E84825A96C6080AA17F8A05B188D97B78`; metadata-only mtime SHM pozostaje osobną open observation. Job `real-research-09fd6a30e07e63e96699ca002dbaead4` ma `QUEUED/attempts=0`; provider attempts i usage dla requestu wynoszą zero. Etap 1 = `OPEN / READY FOR NEW OWNER AUTHORIZATION AFTER STANDALONE QUIESCENCE CHECK`.

### ADR-085: LA-03 rozdziela pre-storage quiescence od durable lifecycle; jedna autoryzacja kończy się jednym settled requestem

- **Data:** 2026-07-17.
- **Status:** ACCEPTED jako decyzja właściciela i trwały wynik operacyjny; implementacja oraz live state oczekiwały wtedy niezależnego review (stan zaktualizowany: niezależny re-review naprawy NIA-P2-RV-01…05 wydał `APPROVE WITH MINOR/P2`, a **ADR-088 zamyka Etap 1 = `CLOSED` 2026-07-17**).
- **Kto podjął:** właściciel jawnie zlecił kontynuację aż do dokładnie jednego rzeczywistego provider requestu, z capem `0.12 USD`, attempt #1, zero retry/fallbacku/browsera/publikacji; implementacja i wykonanie: Codex.
- **Root cause:** realny composition root otwierał główne `SqliteStorage` przed canonical handle probe. Windows `CreateFileW` z share mode 0 deterministycznie widział własne połączenie jako `DB_HANDLES_PRESENT`; nie był to foreign holder.
- **Decyzja kompozycyjna:** `controlled-live-once` najpierw wywołuje ten sam `run_controlled_live_quiescence_check` co standalone, bez storage/markera/providera. Dopiero PASS otwiera jeden główny storage. Post-open durable preflight ponownie sprawdza DB SHA/schema/job/pricing/intent/flags; marker O_EXCL powstaje po pierwszej rewalidacji, a drugi durable recheck potwierdza ownership i brak driftu przed flagami/claimem/providerem. Nie wykonuje się zero-sharing probe po własnym open.
- **Zabezpieczenia zachowane:** probe nie został wyłączony; obce read-only/writable SQLite oraz WAL/SHM nadal STOP. Drift między fazami, drugi wrapper, obcy marker, nieclaimable job, pricing/intent/flags mismatch nadal STOP. `max_attempts=1`, `max_retries=0`, request identity, fence, ledger, `REQUEST_STARTED`, usage, settlement, budget i reconciliation pozostają bez zmian.
- **Dowód offline:** 1181/1181, exact-once cover 1181; fake subprocess przeszedł CLI→storage→worker→provider fake→usage→settlement→terminalizacja; focused 71/71; standalone temp PASS.
- **Wynik live:** produkcyjny standalone PASS; dokładnie jeden Anthropic request zakończony HTTP 200. Attempt #1 ma `REQUEST_STARTED` i `SETTLED`, jedno usage `0.053182 USD`, zero attemptu #2/retry/reconciliation. Niepoprawny JSON wywołał typowany `ResearchParseError`; job/run/research_run są terminalnie `FAILED`, bez lease/rezerwacji i Research Card. Wrapper zwrócił `VALIDATION_FAILED_FAIL_CLOSED`; marker został trwale usunięty po raporcie, flags i gate wróciły fail-closed.
- **Skutek:** cel pierwszego rzeczywistego provider requestu jest spełniony. Etap 1 był wtedy `OPEN`, ponieważ nie oceniono jeszcze kryterium zamknięcia (stan zaktualizowany: **ADR-088 zamyka Etap 1 = `CLOSED` 2026-07-17**; pozytywny durable flow/Research Card nie jest wymaganą bramką). Bieżący job wyczerpał jedyny attempt; kolejny provider request wymaga nowej jawnej autoryzacji i nowej dozwolonej operacji. Etap 2 nie został rozpoczęty.

### ADR-086: Review LA-03 zatwierdza lifecycle; P2 zamyka parser, frozen pre-storage i historię raportów

- **Data:** 2026-07-17.
- **Status:** LA-03 `APPROVE WITH MINOR/P2`; implementacja P2 `CANDIDATE — AWAITING INDEPENDENT REVIEW`. Etap 1 był wtedy `OPEN` (stan zaktualizowany: **ADR-088 zamyka Etap 1 = `CLOSED` 2026-07-17**).
- **Kto podjął:** niezależny reviewer wydał werdykt LA-03 i findings P2; właściciel przekazał formalny wynik oraz zlecił lokalne wdrożenie P2 bez realnego requestu. Implementacja i offline verification: Codex.
- **Forensics:** request `real-research-09fd6a30e07e63e96699ca002dbaead4:research:1` ma jeden attempt `REQUEST_STARTED → SETTLED`, usage 13306/1657/1 i koszt `0.053182 USD`. Job/run/research_run zachowują `ResearchParseError: Expecting property name enclosed in double quotes: line 29 column 6 (char 4376)`. Nie istnieje katalog diagnostyczny dla runu `f74165fb-9677-4e6d-abfd-09607bd4dd78`; stara single path odrzucała `stop_reason` i nie dopinała raw. Decyzja: nie przypisywać prose/fence/truncation ani konkretnego znaku bez evidence.
- **Kontrakt odpowiedzi:** jedyny reachable durable single parser przyjmuje dokładnie jeden JSON object lub jeden kompletny zewnętrzny fence. Nie wykonuje brace extraction z prose. Wymaga zamkniętego zestawu pól i typów; `ResearchSchemaError` jest odrębny od błędu składni, a `ResearchTruncatedError` wymaga jawnego `stop_reason=max_tokens`. Provider response, usage i stop reason po jednym callu są zachowane do prywatnej diagnostyki. Parse/schema/truncation nie są retryable; brak repair calla, fallbacku i attemptu #2.
- **Structured output:** lokalnie zainstalowany Anthropic SDK 0.116.0 eksponuje `output_config.format=json_schema`, ale w dozwolonym offline zakresie nie ma dowodu zgodności konkretnego `claude-sonnet-5` z web-search + structured output. Nie dodaje się niezweryfikowanego parametru do jedynej ścieżki requestu; prompt i parser zostały wzmocnione deterministycznie. Osobna decyzja może włączyć structured output dopiero po autorytatywnym potwierdzeniu kompatybilności.
- **Raporty:** deterministyczny `session_id` pozostaje tożsamością logicznej operacji, lecz nazwa raportu używa także attemptu, UTC timestampu i nonce. Provisional/final tego samego invocation promują ten sam plik przez temp/flush/fsync/replace/directory fsync. Następny invocation tworzy nowy plik i nie niszczy historii. Marker przechowuje `report_key`; recovery tworzy odrębny report i wskazuje poprzedni key.
- **Quiescence:** `run_controlled_live_once` wymaga jawnego `frozen_quiescence`. Production CLI wykonuje canonical probe przed `SqliteStorage.open`, zamraża wynik i przekazuje mapping; `None`/brak argumentu kończy się błędem konstrukcji przed worker/providerem. Nie istnieje hidden default handle probe po open.
- **Dowód:** collect/full 1200/1200; exact-once `290+293+304+313`, wszystkie partycje zielone. 14 klas odpowiedzi, tripwire caller count=1, durable parse/schema/truncation z jednym usage i `SETTLED`, dwa raporty tego samego operation key, recovery linkage, missing payload i composition order. Fake callery/test SDK seams i tymczasowe SQLite; lokalny real SDK tylko do introspekcji wersji/signature, bez `messages.create`; zero provider requestu, browsera, publikacji i kosztu.
- **Granice:** produkcyjna DB/WAL/SHM ma pozostać byte-identical; brak enqueue, gate/flags changes, nowego joba, realnego workera, Git stage/commit/push. Terminalny job nie może być retry'owany. Kolejny request wymaga nowej jawnej autoryzacji i nowej dozwolonej operacji.

### ADR-087: Odrzucony pierwszy pakiet P2 jest naprawiany wyłącznie w zakresie NIA-P2-RV-01…05

- **Data:** 2026-07-17.
- **Status:** ACCEPTED jako decyzja o zakresie; implementacja `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Etap 1 był wtedy `OPEN` (stan zaktualizowany: niezależny re-review wydał `APPROVE WITH MINOR/P2`, a **ADR-088 zamyka Etap 1 = `CLOSED` 2026-07-17**).
- **Kto podjął:** niezależny reviewer wydał `REJECT — MAJOR`; właściciel zlecił zamkniętą naprawę pięciu findings. Implementacja i weryfikacja offline: Codex; implementer nie zatwierdza własnej pracy.
- **Zakres:** (1) score jest walidowany jako skończony `Decimal` i w zakresie przed konwersją, więc ogromne liczby kończą się `ResearchSchemaError` po jednym usage i settlement; (2) operator report, diagnostic i trwałe błędy korzystają ze wspólnego rekurencyjnego sanitizera, a diagnostic używa temp/file fsync/replace/directory fsync best-effort; (3) enqueue przyjmuje jawny `now` tego samego `Clock`, z którego korzysta wrapper; (4) parser akceptuje tylko jeden obiekt lub literalny zewnętrzny fence `json`, drugi `raw_decode` rozpoznaje każdą kolejną legalną wartość, a root scalar/array jest schema error; (5) aktywne sekcje `CURRENT_PROJECT_STATE.md` używają bieżących liczb i post-live baseline'u.
- **Lifecycle:** parse/schema/truncation po provider boundary zachowują dokładnie jeden caller, attempt `REQUEST_STARTED`, usage i settlement oraz terminalny `FAILED`; diagnostyka nie ma prawa zmienić tego wyniku. Brak retry, repair requestu, attemptu #2, `NEEDS_RECONCILIATION`, `NEEDS_VERIFICATION` i aktywnej rezerwacji w naprawionych ścieżkach.
- **Dowód kandydacki:** 28-przypadkowa macierz single-response, durable score failures/boundary, test pięciu klas sekretów, cztery failpointy diagnostyki i jawne granice zegara. Bieżący collect/full to 1235/1235, partycje exact-once `294+299+311+331`; wyłącznie fake callery/SDK seam i tymczasowe SQLite.
- **Granice:** zero sieci/API/browsera/publikacji/kosztu, nowego produkcyjnego joba, realnego `controlled-live-once`, migracji i operacji Git. Produkcyjna DB/WAL/SHM pozostaje byte-identical z SHA `5BEA9E26597E6A628EF875A7F5115465E94CB600B38213A67794EE94232C6D10`. Pozytywny niezależny review i nowa decyzja właściciela są wymagane przed rozważeniem nowego joba/requestu.

### ADR-088: Formalne zamknięcie Etapu 1 po niezależnym re-review NIA-P2-RV-01…05

- **Data:** 2026-07-17.
- **Status:** ACCEPTED — decyzja właściciela; **`ETAP 1 = CLOSED`**. WAVE 0A/0B/1A pozostają `CLOSED — APPROVED WITH P2`; LA-01-R1, LA-02, LA-03 pozostają `APPROVED/APPROVE WITH MINOR/P2`. Live API nadal `ZABRONIONE` bez oddzielnej jawnej decyzji; Etap 2 nie został rozpoczęty.
- **Rozdzielenie odpowiedzialności:** pierwszy pakiet P2 po LA-03 otrzymał `REJECT — MAJOR`; implementer zamknął pięć findings NIA-P2-RV-01…05 i zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Niezależny reviewer odtworzył testy implementera, wykonał własne kontrpróby i wydał werdykt `APPROVE WITH MINOR/P2` z rekomendacją, że właściciel może formalnie zamknąć Etap 1. Formalną decyzję o zamknięciu podjął następnie właściciel; nie jest ona deklaracją implementera ani reviewera.
- **Podstawa:** niezależny re-review `APPROVE WITH MINOR/P2` — zero CRITICAL, zero MAJOR, wszystkie pięć findings (score/lifecycle, sanitizer diagnostyki, deterministyczny zegar, kontrakt parsera jednej odpowiedzi, spójność dokumentacji) technicznie zamknięte. Dowód: 1235 collected i 1235/1235 passed; exact-once `1235` node ID; partycje `294+299+311+331`; `compileall` exit 0; `git diff --check` czysty; własne kontrpróby reviewera (parser/score, durable lifecycle złego score, granice score 0/1, sanitizer i pięć failpointów zapisu, deterministyczny zegar w fixture 2030/2020, pełny CLI subprocess z fake workerem); audyt produkcyjnej DB wyłącznie na byte-identycznej kopii; zero sieci, realnego SDK/API, browsera, publikacji i kosztu.
- **Research Card:** brak pozytywnej Research Card z ostatniego controlled-live NIE jest bramką zamknięcia Etapu 1. Job `real-research-09fd6a30e07e63e96699ca002dbaead4` wykonał dokładnie jeden attempt/request (`REQUEST_STARTED → SETTLED`, usage `0.053182 USD`), zakończony typowanym `ResearchParseError` i terminalnym `FAILED`; jest terminalny i nie może być retry'owany.
- **Backlog Etapu 2 (nieblokujący, nie naprawiany w ramach zamknięcia):** `RV-R2-P2-1` — prose zaczynająca się od `N` lub `I` może otrzymać etykietę diagnostyczną `json_syntax` zamiast `prose_outside_json`; `RV-R2-P2-2` — kompletny błędny JSON z trailing comma może otrzymać etykietę `incomplete_json` zamiast `json_syntax`. Oba pozostają fail-closed tym samym `ResearchParseError`, bez wpływu na lifecycle. Pozostałe obserwacje re-review pozostają `BACKLOG — NON-BLOCKING`. Żadna z nich nie otwiera nowej fali.
- **Granica decyzji:** zamknięcie Etapu 1 nie odblokowuje paid execution ani live API, nie autoryzuje nowego joba/requestu ani rejestracji zadań systemowych i nie rozpoczyna Etapu 2. Kolejny realny request wymaga oddzielnej, jawnej decyzji właściciela i nowego dozwolonego joba.
- **Integralność:** branch `dev/first-successful-research-card`, HEAD `d87f87e66a7ef8d5a446d83625075b2726e58a3d`, ahead/behind `0/0`. Zmieniono wyłącznie dokumentację statusową; kod, testy, migracje, provider, storage i runtime bez zmian. Produkcyjna DB/WAL/SHM byte-identical z SHA `5BEA9E26597E6A628EF875A7F5115465E94CB600B38213A67794EE94232C6D10`, rozmiar `335872 B`, bez WAL/SHM/journal. Bez stage/commit/push/PR/merge w ramach tego zadania.
