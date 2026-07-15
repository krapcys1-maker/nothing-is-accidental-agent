# CURRENT_PROJECT_STATE — Nothing Is Accidental Agent

> **STATUS: JEDYNY OBOWIĄZUJĄCY OBRAZ STANU PROJEKTU.**
> Data weryfikacji: **2026-07-15**. **STATUS ETAPU 1: `BLOCKED`. WAVE 0A = `APPROVED WITH P2`; WAVE 0B = `APPROVED WITH P2 — READY FOR CHECKPOINT`.** Niezależny końcowy review nie znalazł MAJOR ani CRITICAL; formalne `CLOSED` nastąpi dopiero po osobno autoryzowanym commicie checkpointu. Końcowa fala naprawcza WAVE 0B jest zweryfikowana wyłącznie offline. Lokalny incydent testowy bazy jest zamknięty przez kontrolowane odtworzenie logiczne i nowy baseline; nie istnieje bitowy snapshot poprzedniego pliku. Usługa schedulera systemowego = NOT_STARTED; **live API = ZABRONIONE**; browser/public worker = BLOCKED.
> Architektura: `MASTER_ARCHITECTURE.md` · Kolejność prac: `IMPLEMENTATION_ROADMAP.md`.
> Aktualizować przy każdej zmianie stanu modułu; statusy tylko z zestawu: `NOT_STARTED / SKELETON / PARTIAL / WORKING / VERIFIED / BLOCKED / DEPRECATED`. `VERIFIED` wyłącznie dla kodu URUCHOMIONEGO i przetestowanego.

## Liczby kontrolne (zweryfikowane)

- Testy: **894 passed / collected** (offline, deterministyczne, bez sieci; w tym 53 testy kolejki, **60 testów runtime**, **26 testów maintenance**, **49 testów scheduling**, **58 restart acceptance** i rozszerzona macierz WAVE 0B). WAVE 0B utrwala kanoniczny snapshot prompt-input, stage i parametrów requestu; literalne regresje obejmują fingerprint, lifecycle, restart, SDK, safety kernel oraz W0B-REV-06/09/10 i W0B-RR-01. Gałąź: `dev/first-successful-research-card`.
- Realny koszt projektu: **0,684580 USD** (13 wpisów `model_usage` z `dry_run=0`; Task 9 łącznie **0,183964 USD**, w tym resume B **0,013914 USD**; limit miesięczny 40 USD → wykorzystane 1,71%).
- Realne próby researchu: **4** (+1 diagnostyka pojedynczego źródła) — **1 ukończona Research Card na żywym API** (oraz 1 dry_run). Karta realna #2 ma rekomendację jakościową REJECT i nie przechodzi do treści.
- Nowy logiczny baseline po kontrolowanym odtworzeniu: `runs = 5×DRY_RUN + 3×FAILED + 1×SUCCESS` (`c01171bc`); `research_runs = 2×COMPLETE` (1 dry-run, 1 real), `2×FAILED` i `1×PARTIAL` (`9bbeb020`). Run `c01171bc` ma kartę #2, 4 źródła VERIFIED, 7 usage i koszt 0,183964 USD; łącznie pozostaje 13 realnych wpisów usage o koszcie 0,684580 USD.
- **Baseline bazy ustanowiony po review:** `data/agent.db` ma SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`. Usunięto wyłącznie potwierdzone artefakty fake/dry-run klasy A i przywrócono sekwencje klasy B; `integrity_check=ok`, `foreign_key_check=[]`. Werdykt historyczny pozostaje `NOT PROVABLY RESTORABLE`: nie odnaleziono bitowej kopii SHA `C92D9565DDA322997DE0D6A78D3943336E58CD9261229949E0BCFE4E43F9A63C`, ale nie stwierdzono utraty realnych danych. Zachowano forensic copy, kandydata oraz backup stanu po incydencie.
- Publikacje na Substacku: **0** (fizycznie zablokowane przez `DisabledBrowser`).

## Tabela stanu modułów

| Moduł | Status | % | Co działa | Co nie działa / znane błędy | Testy | Ostatnia weryfikacja | Następny krok |
|---|---|---|---|---|---|---|---|
| Konfiguracja (`app/core/config.py`) | VERIFIED | 90 | .env+YAML, zero ścieżek absolutnych, fallback na *.example | kill-switch czytany raz przy starcie (runtime — Etap 1) | pośrednie (fixtures) | 2026-07-12 | bez zmian do Etapu 1 |
| Modele domenowe (`app/models.py`) | VERIFIED | 94 | modele zbudowanej części oraz zamknięty `JobExecutionContext(job_id, lease_owner, run_id, Clock, kind, workflow)` tworzony po atomowej inicjalizacji | paid/browser execution context nie jest jeszcze projektowany | tak | 2026-07-13 | osobne granice paid/browser |
| Storage SQLite + 13 migracji | VERIFIED | 99 | WAL/busy timeout, fenced worker writes oraz ledger `0010`–`0013`; durable `execution_intent` v2, request snapshot i finalna asercja `job→run→research_run→attempt` | brak usługi schedulera; operator reconciliation nie jest wdrożony | storage + flow + queue + migracje/race/reopen | 2026-07-15 | niezależne re-review WAVE 0B |
| Policy Engine | PARTIAL | 50 | kill-switch statyczny, aktywność konta, centralny `check_run_budget`, progi oraz runtime check pięciu flag SQLite bez cache dla workera | brak: autonomy_level, AccountMode, limity AccountPolicy, cooldowny i automatyczne wejście SAFE MODE; paid/browser są celowo BLOCKED | test_policy_engine + research_run_budget + worker runtime | 2026-07-13 | reszta Etapu 1/4 |
| UsageTracker (koszty) | VERIFIED | 97 | `record_job` sprawdza fence, zapisuje usage z request_id i rozlicza dokładnie aktywny attempt; parse error z usage nie gubi kosztu | unknown outcome pozostaje `NEEDS_RECONCILIATION`; eksport CSV wymaga audytu KEEP/DEPRECATE/REMOVE przed Etapem 8 | tak + ledger/parse/race + CSV failpoint | 2026-07-14 | re-review; przyszły resolver WAVE 1 |
| ModelRouter | VERIFIED | 90 | zadanie→model z .env | scripts omijają router (P2-8) | tak | 2026-07-12 | P2-8 przy Etapie 0/1 |
| FakeLLMClient / FakeResearchClient | VERIFIED | 100 | deterministyczne dry_run/testy, scenariusze brzegowe | — | tak | 2026-07-12 | — |
| AnthropicLLMClient (tematy) | WORKING | 88 | odpowiedź→Usage→parse, typowane błędy; SDK ma `max_retries=0`, derived request identity i exact `Idempotency-Key` | realny adapter nie jest dostępny z `app.main`; WAVE 0A formalnie zamknięta jako `APPROVED WITH P2` | fake SDK + workflow SQLite + WAVE 0A | 2026-07-14 | backlog P2; osobny zakres Etapu 1 |
| AnthropicResearchClient (3 generacje metod) | WORKING | 99 | produkcyjny klient wymaga `DurableProviderAttemptContext`, derived request identity, snapshotu requestu i pełnej asercji lifecycle przed callerem/SDK; SDK ma `max_retries=0` | P2-19 `timeout-billed-unrecorded`; realne durable A1/A2/B i resume są poza zakresem WAVE 0B | offline gate/ledger + historyczne live | 2026-07-15 | niezależne re-review; WAVE 1A osobno |
| Estymator kosztów | VERIFIED | 85 | conservative+expected z 2 realnych obserwacji, margines ≥50% | dwie kalibracje (legacy z cennika vs staged stałe) — P2-1; kalibracja n=2 | tak | 2026-07-12 | ujednolicić przy Etapie 2 |
| Workflow tematów + dedup | VERIFIED | 90 | pełny przepływ dry_run, dedup lokalny, progi, SUCCESS-fix | realny run tematów nigdy nie wykonany | tak | 2026-07-12 | realny run po Etap 0 zad. 6 |
| Research staged A1/A2/B + resume | VERIFIED | 99 | realny A1 + 4×A2 + B; failure zachował SOURCES_COMPLETE, repair naprawił audit, resume dał COMPLETE/SUCCESS/USED; typed error ma identyczny bezpieczny format w run/research_run/stage/candidate audit bez SDK body i sekretów; finalizacja B używa trwałego force i CAS, a wyłącznie `finalize_staged_research_with_card` może zapisać staged COMPLETE/SUCCESS/B SUCCESS/USED z kosztem z `model_usage`; legacy finalizery i `finish_run` nie mogą oznaczyć staged sukcesu | karta #2 jakościowo REJECT; `research_runs.error` zachował historyczny parse-error (P2-20) | 454 offline + Task 9 live + repair + resume | 2026-07-13 | niezależne review; scheduler/jobs/workery osobnym zadaniem |
| Research legacy (single, two-stage) | WORKING | 100 | działa, 24 testy | NIEZALECANY (ADR-016→020); do DEPRECATED po sukcesie staged live | tak | 2026-07-12 | Etap 2 zad. 6 |
| Walidacja + injection guard | VERIFIED | 90 | deterministyczna bramka, min_verified_sources, neutralizacja injection | wzorce EN-only (P2-7) | tak | 2026-07-12 | rozszerzenie przy Etapie 2 |
| Diagnostyka odpowiedzi | VERIFIED | 95 | raw+stop_reason per etap, potwierdzona na żywo | nadpisuje poprzednią próbę tego samego etapu (P2-13, świadome) | tak | 2026-07-12 | — |
| CLI `app/main.py` + runner | VERIFIED | 95 | run-topics, manualny run-research (dry), blokada `--real`, `worker --once`, reaper, maintenance i centralny dry-run enqueue; runner przekazuje uprawnienie claimu, a pipeline materializuje zamknięty context po inicjalizacji i terminalizuje job w success transaction | brak paid/browser CLI, realnego resume przez worker i usługi schedulera systemowego | CLI + worker + 53 restart acceptance | 2026-07-14 | niezależne review, potem scheduler service |
| `scripts/run_capped_research.py` | VERIFIED | 94 | pre-flight deleguje do `PolicyEngine.check_run_budget`; estymata obejmuje `1+max_retries`; estimate-only bez klienta; resume uwzględnia zapisany usage | `--max-sources 0` znaczy „wszyscy" (P2-15) | black-box CLI + budget delegation | 2026-07-12 | bez zmian w Task 6 |
| Porty: Storage/Notification | VERIFIED / WORKING | 99/70 | Storage rozdziela manualne mutacje od worker-only fenced API; success terminalizuje job atomowo, a post-terminal notification jest diagnostyką best-effort | brak usługi schedulera systemowego | queue + worker + maintenance + restart acceptance | 2026-07-14 | niezależne review |
| Porty: SecretStore/FileStore | SKELETON | 20 | kod adapterów istnieje | **martwy kod — zero wywołań** (config używa os.getenv wprost) | brak | 2026-07-12 | podpiąć w Etapie 8 (lub usunąć decyzją) |
| Porty: Browser/Scheduler | SKELETON / VERIFIED | 10/82 | DisabledBrowser blokuje każdą akcję; worker, reaper, `MaintenanceRunner`, polityka okien i restart acceptance są zweryfikowane offline | browser/public worker pozostaje BLOCKED, brak usługi schedulera systemowego | worker + maintenance + scheduling + restart acceptance | 2026-07-13 | Etap 5 / scheduler service |
| Tabele bez kodu (content_items, interactions, target_items, approvals, metrics_daily, screenshots) | SKELETON | 5 | schemat od migracji 0001 | żaden kod ich nie dotyka | — | 2026-07-12 | Etapy 3–7 |
| Task queue storage (jobs/flags/lease/rezerwacja) | VERIFIED | 99 | `0009`, atomowy claim/idempotency/recovery/rezerwacje oraz trwałe `earliest_run_at` i kontrolowany `schedule_reason`; claim pobiera czas po write locku, więc może przejąć job, który stał się eligible podczas oczekiwania | reaper wymaga jawnego progu i recovery jobów; przypięty run po expiry wymaga reconciliation, nie resume | `test_jobs_queue` + worker/maintenance/scheduling Barrier/reopen | 2026-07-14 | scheduler service osobno |
| Worker loop / scheduler runtime | VERIFIED | 90 | `run_once`/`run_forever`, dispatcher LOCAL/RESEARCH dry-run, periodic guard, maintenance i scheduling; zamknięty `DispatchResult` rozróżnia workflow success/failure od LOCAL i malformed result propaguje jako niemutujący błąd kontraktu | live API NOT VERIFIED; paid/browser/public BLOCKED; system scheduler NOT_STARTED; realne resume NOT IMPLEMENTED; przypięty run po expiry → NEEDS_VERIFICATION | runtime 60 + maintenance 26 + scheduling 49 + acceptance 58 + pełny 700 | 2026-07-14 | ponowne niezależne review, scheduler service, osobne granice paid/browser |
| Content pipeline (artykuły/Notes) | NOT_STARTED | 0 | pełny snapshot Fable + blueprint: Article Brief, A1–A9, N1–N16 dry-run, audyty, SEO i diversity memory | brak kodu, migracji i generatorów; raport/blueprint nie są wdrożeniem, a kosztorysy są niewalidowane | — | 2026-07-13 | Etap 3 po Etapach 1–2 |
| Approval/autonomy + panel FastAPI | NOT_STARTED | 0 | — | — | — | — | Etap 4 |
| Publishing (Playwright/Substack) | NOT_STARTED | 0 | — | — | — | — | Etap 5 |
| Interakcje (komentarze/odpowiedzi) | NOT_STARTED | 0 | dokumentacyjny podział: publiczne Notes, K1–K8, odpowiedzi/restacki w Etapie 6 | brak kodu i akcji publicznych | — | 2026-07-13 | Etap 6 |
| Analytics + strategy engine | NOT_STARTED | 0 | dokumentacyjne definicje oddzielnych metryk i `is_estimated` | brak kolektora, atrybucji, eksperymentów i strategy engine | — | 2026-07-13 | Etap 7 |
| Backend API / frontend | NOT_STARTED | 0 | — | (panel = Etap 4; poza nim brak frontendu w planie MVP) | — | — | Etap 4 |

## Aktualne blokery

**ETAP 1 pozostaje BLOCKED przez pozostałe P1.** WAVE 0A jest formalnie zamknięta jako `APPROVED WITH P2`: P0-01 (ukryte retry SDK), P1-01 (niejawny real-mode) i P1-02 (fail-open pricing) są zamknięte. Odtworzono logicznie `data/agent.db` i ustanowiono SHA baseline `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`; incydent bazy jest zamknięty, choć nie jest to dowód bitowego odtworzenia starego pliku. Backlog P2: (1) mocniejszy regression test na granicy `messages.create`, (2) pełna parametryzacja pricingu, (3) poprawna kolejność aktualizacji dokumentacji. Systemowa usługa schedulera nadal nie istnieje; paid/live, browser/public i realne resume pozostają BLOCKED/NOT VERIFIED. Nie wdrożono eksportera, outboxa ani ledgeru request ID; karta #2 nadal ma `publication_recommendation=REJECT`.

## Ostatnie ważne decyzje

- **ADR-022 (ACCEPTED / EXECUTED 2026-07-13):** właściciel zatwierdził dokładnie jeden świeży staged run z capem 0,55 USD. A1/A2 odniosły sukces, B zakończyło się `max_tokens`/parse-error; koszt 0,170050 USD; bez retry/resume.
- **2026-07-13 (jawna zgoda właściciela):** po osobnym repairze zatwierdzono dokładnie jeden resume wyłącznie B z absolutnym capem 0,20 USD i `max_retries=0`; wynik `end_turn`, karta #2, łączny koszt 0,183964 USD.
- **ADR-021:** repo GitHub PRIVATE, main stabilny + branche dev.
- **ADR-020:** research staged A1/A2/B; **ADR-019:** trwałość etapów; **ADR-017/018:** cel = pełna autonomia operacyjna + anonimowa marka redakcyjna bez proaktywnego ujawniania AI (NO_REPLY, zero impersonacji).
- **ADR-029:** retry błędów Anthropic jest dozwolone wyłącznie dla jawnie typowanych timeout/SDK-network/429/500/502/503/504; 400/401/403/404/422, unknown, parse, truncation i validation są terminalne dla próby.
- **ADR-037 (ACCEPTED / zweryfikowane offline):** jobs+lease+idempotency+active-topic lock+global reservation oraz `system_flags`; BROWSER po lease expiry → NEEDS_VERIFICATION.
- **ADR-038 (ACCEPTED / zweryfikowane offline):** jeden worker odczytuje runtime flags bez cache, wykonuje tylko LOCAL noop i RESEARCH `dry_run=true`, wiąże `job.run_id` przez CAS; paid/browser pozostają BLOCKED. Jednorazowy reaper dodaje ADR-040, lecz worker nie uruchamia go automatycznie.
- **ADR-039 (ACCEPTED / zweryfikowane offline):** CAS sprawdza pełną relację RESEARCH job→run→research_run (account/topic/workflow/flow). Po expiry RESEARCH z `run_id` trafia fail-closed do NEEDS_VERIFICATION z zachowaną rezerwacją; worker nie uruchamia go od początku ani nie implementuje resume.
- **ADR-040 (ACCEPTED / zweryfikowane offline):** jawny reaper po recovery atomowo zatrzymuje wyłącznie stale `RUNNING` bez executable joba; `QUEUED/LEASED/RUNNING` job blokuje stop, `NEEDS_VERIFICATION` pozostaje trwały, a cykliczny scheduler nie istnieje.
- **ADR-041 (ACCEPTED / zweryfikowane offline):** podczas synchronicznego dispatchu worker uruchamia daemon periodic heartbeat guard z osobnym połączeniem SQLite. Daemon jest tylko osłoną procesu; worker zawsze podejmuje stop event, `wake`, bounded join i kontrolę `is_alive()`. Zwykle wątek kończy się i jest dołączony, lecz timeout może zostawić go żywego do odblokowania zależności — bez prawa workera do `DONE`; po odblokowaniu guard widzi stop event przed kolejnym heartbeat. `lost_lease` i `failure` są in-memory, a trwałe rozstrzygnięcie należy do SQLite oraz recovery/reconciliation. Guard nie wznawia wygasłego lease ani nie retry’uje dispatchu, a utrata lease ma pierwszeństwo przed błędem dispatchu i blokuje `DONE`. Zweryfikowane wyłącznie dla LOCAL/RESEARCH `dry_run`; paid/live API = NOT VERIFIED, browser/public = BLOCKED.
- **ADR-043 (ACCEPTED / zweryfikowane offline):** przed utworzeniem nowego joba `SchedulingPolicy` deterministycznie wybiera lokalne okno z konfiguracji IANA/DST, zapisuje UTC `earliest_run_at` i zamknięty `schedule_reason`; claim egzekwuje eligibility. W chwili tej decyzji final restart acceptance była NOT_STARTED; późniejsze ADR-044/045 doprowadziły ją do candidate awaiting review. Usługa systemowa nadal NOT_STARTED; paid/browser/public = BLOCKED.
- **ADR-046 (ACCEPTED / candidate po testach, awaiting independent review):** lifecycle pobiera UTC dopiero po `BEGIN IMMEDIATE`; heartbeat nie wskrzesza lease, który wygasł podczas oczekiwania. `COSTS.csv` jest odtwarzalnym eksportem po commicie SQLite, więc jego błąd jest ostrzeżeniem. Nieoczekiwany błąd jobowego pipeline’u po inicjalizacji atomowo terminalizuje job/run/research_run.
- **ADR-047 (ACCEPTED / candidate po testach, awaiting independent review):** `finalize_job_research_execution` atomowo terminalizuje `jobs=DONE` razem z kartą, źródłami i lifecycle researchu. Dispatcher zwraca typowany `TerminalizationMode`; tylko `WORKER_MUST_COMPLETE` używa generic completion.
- **ADR-048 (ACCEPTED / candidate po testach, awaiting independent review):** `DispatchResult` ma wymagany, zweryfikowany runtime `TerminalizationMode`; Worker obsługuje wyczerpująco trzy mode i propaguje naruszenie kontraktu bez canonical write. Inserty finalizacji wymagają `rowcount == 1` i rollback nie maskuje primary error.
- **ADR-050 (ACCEPTED / EXECUTED):** nowy baseline SQLite `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB` pochodzi z kontrolowanego logicznego odtworzenia wyłącznie klasy A/B; brak bitowego snapshotu poprzedniego pliku pozostaje udokumentowany.
- **ADR-051 (ACCEPTED / EXECUTED):** WAVE 0A została formalnie zamknięta jako `APPROVED WITH P2`; P0-01, P1-01 i P1-02 są zamknięte, trzy P2 są backlogiem, a Etap 1 pozostaje BLOCKED przez inne P1.
- **Korekta ADR-031 po końcowym review F4:** COMPLETE nie omija kontraktu `StagedFinalizationContext`; terminalny no-op odrzuca sprzeczny fresh/force/resume mode oraz niezgodny CAS bez mutacji. `finalize_research_success` i `mark_research_run_complete` są legacy-only i odrzucają `staged` we wszystkich stanach, także COMPLETE i FAILED.
- **ADR-032–036 (ACCEPTED, wyłącznie dokumentacyjnie):** modularny system redakcyjny, prawo do `SKIP`, izolacja NIA/build logu, rozdzielenie follows i subscribers oraz Notes dry-run w Etapie 3/publiczne operacje w Etapie 6. Pełny snapshot Fable jest w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md`; wszystkie elementy wdrożeniowe pozostają PLANNED/NOT_STARTED.
- **2026-07-12 (ten audyt):** konsolidacja dokumentacji do 3 dokumentów źródła prawdy; stare plany w `docs/archive/superseded_plans/` (ADR-023).

## Etapy

### Aktualizacja nadrzędna — final restart acceptance Etapu 1 (2026-07-14)

Ten wpis zastępuje niżej starsze wzmianki „końcowa akceptacja restartu = NOT_STARTED” oraz historyczne liczby 26/42/53 acceptance i 667/683/695 testów. ADR-044 atomizuje inicjalizację, ADR-045 zamyka old-owner research fencing, ADR-046 usuwa trzy P1 czasu/CSV/unexpected failure, ADR-047 przenosi sukces joba do transakcji workflow, a ADR-048 zamyka kontrakt wyniku dispatchu. `tests/test_stage1_restart_acceptance.py` ma 58 scenariuszy, w tym final heartbeat failpoint, brak generic `complete_job`/`fail_job`, atomic failure, malformed terminalization, success/failure transaction failpoints, crash po commicie, macierz expiry przed recovery, claim po write locku i błąd katalogu CSV. Pełny suite: 700 passed; realny koszt 0 USD. WAVE 0A została formalnie zamknięta jako `APPROVED WITH P2`; formalne zamknięcie Etapu 1 nie zostało ogłoszone.

- **Aktywny etap roadmapy:** Etap 1 — fundament, worker, heartbeat, maintenance, scheduling i final restart acceptance są zweryfikowane offline; wymagane jest ponowne niezależne review WAVE 0B. Paid/browser są BLOCKED, live API jest ZABRONIONE, usługa schedulera systemowego NOT_STARTED.
- **Ostatni ukończony krok:** Etap 0 / zadanie 9 — kontrolowany resume B dał pierwszą realną kompletną Research Card; **Etap 0 formalnie zakończony**.
- **Następne trzy zadania:**
  1. Niezależne review polityki harmonogramu redakcyjnego, w tym restartu i UTC/DST; bez API.
  2. Końcowa akceptacja restartu dla jobów zaplanowanych; usługa schedulera systemowego pozostaje osobnym zadaniem.
  3. Nie uruchamiać płatnych ani browser/public workerów przed osobnym zakresem bezpieczeństwa i zgodą właściciela.

## Znane długi techniczne (poza blokerami; numeracja z audytu 12.07)

| # | Dług | Plan |
|---|---|---|
| P1-3/P1-4 | ZAMKNIĘTE po pełnym review: retry worst-case, re-check, obowiązkowy cap realnego pipeline, stały cap resume i centralne D/M | Task 5; 257 testów offline |
| P1-7 | kill-switch nie działa w runtime (snapshot z .env) | Etap 1 (system_flags) |
| P2-1 | dwie kalibracje estymatora (rozjazd przy zmianie cen w .env) | Etap 2 |
| P2-2 | koszt w 3 miejscach (model_usage=kanon; runs.cost_usd i research_runs.total_cost_usd=cache) | `runs.cost_usd` synchronizowany w Etapie 0 zad. 2; total_cost_usd pozostaje cache |
| P2-4 | budżet dzienny wg dnia UTC (właściciel w Europe/Warsaw) | decyzja: zostaje UTC — udokumentowane |
| P2-5 | migracje bez transakcji (częściowa awaria = zakleszczenie) | nowe migracje od 0006 z BEGIN/COMMIT |
| P2-6 | RESEARCH_LOG.md tylko przy sukcesie (nieudane realne runy nielogowane automatycznie) | Etap 2 |
| P2-7 | injection guard EN-only, URL-e nieskanowane | Etap 2 (przy fetch) |
| P2-8 | scripts używają settings.model_quality zamiast ModelRouter | Etap 0/1 |
| P2-9 | ZAMKNIĘTE: ADR-001/002/003/005/006 miały status PROPOSED mimo wdrożenia | Task 7: wszystkie zweryfikowane i oznaczone ACCEPTED |
| P2-10/P2-11 | migracja przy każdym otwarciu bazy; runtime pisze do docs/ | Etap 8 |
| P2-12 | brak prompt cachingu (N×A2 dzieli system prompt) | po sukcesie live |
| P2-13/P2-14 | diagnostyka nadpisuje poprzednią próbę; stage log nie mierzy czasu | świadomie odłożone |
| P2-15 | `--max-sources 0` znaczy „wszyscy" | Etap 0 przy zad. 1 |
| P2-16 | ujemne `research_source_candidates.attempts` spełnia `attempts < cap` i może przyznać dodatkowe claimy po ręcznym uszkodzeniu rekordu; normalny kod tworzy wyłącznie 0/1+ | dodać `attempts >= 0` do claimu, `Field(ge=0)`, test i ewentualny CHECK constraint |
| P2-17 | dwa równoległe świeże procesy mogą przejść guard przed utworzeniem któregokolwiek runu i oba rozpocząć research tego samego tematu | Etap 1: trwały claim/lease lub constraint aktywnego researchu per topic |
| P2-18 | idempotentny no-op porównuje koszt przez dokładne `float == float`; binarnie różne reprezentacje tej samej kwoty mogą dać fałszywą odmowę, ale nie nadpiszą danych | docelowo najmniejsza jednostka, `Decimal` albo tolerancja zgodna z kanonem `model_usage`; bez zmiany w Task 4 |
| zamknięty | AnthropicLLMClient bez księgowania kosztu przy parse-error, bez testów | Task 6: typowane błędy, fence parser, ledger workflow; 286 testów offline |
| nowy | EnvSecretStore/LocalFileStore = martwy kod | Etap 8 (podpiąć) albo usunąć decyzją |
| znany | lokalne `.venv`: open-interpreter wymaga anthropic<0.38 przy zainstalowanym 0.116 (ostrzeżenie pip, poza projektem) | obserwować |
| P2-19 | `timeout-billed-unrecorded`: provider może zbilować timeout bez zwrócenia usage | niskie retry/capy, worst-case i re-check; rekonsyliacja billingowa poza Task 5 |
| P2-20 | po udanym resume `research_runs=COMPLETE`, ale pole `research_runs.error` zachowuje historyczny parse-error pierwszego B; historia jest też w `research_stage_results`, więc bieżące pole może mylić odczytujących | niezależne review; rozstrzygnąć, czy finalizacja ma czyścić bieżący error, bez mutacji w tym zadaniu |

## WAVE 0B.1 — zapis historyczny, zastąpiony przez WAVE 0B.2 (2026-07-14)

**Status historyczny, zastąpiony przez WAVE 0B.2.** Etap 1 nadal jest `BLOCKED` i nie został zamknięty. WAVE 0B.1 przygotowała globalny `operation_key` i 0011; WAVE 0B.2 domknęła centralną bramkę klienta, pełny intent oraz ledger 0012. Nie jest to akceptacja WAVE 0B.

`0010_provider_attempts` wraz z `0011_provider_attempt_invariants` wiążą nowy realny request z `(job_id, stage, attempt_no)` oraz deterministycznym `request_id=job_id:stage:attempt_no`. Stany są ograniczone do `RESERVED → REQUEST_STARTED → SETTLED/NEEDS_RECONCILIATION` albo `RESERVED → RELEASED`; liczba próby i rezerwacja są dodatnie. Nowy realny `model_usage` wymaga request_id istniejącego attemptu; historyczne nieudowadnialne wiersze są jawnie oznaczone `is_legacy_usage=1`.

Świeży `scripts/run_capped_research.py --real --operation-key …` nadal wykonuje tylko pre-flight i durable enqueue, nie tworzy klienta ani nie woła providera. `enqueue_job_result()` atomowo rozstrzyga `JOB_ENQUEUED` albo `JOB_ALREADY_EXISTS`; ten sam globalny klucz z semantycznie innym kanonicznym payloadem kończy się `OPERATION_KEY_CONFLICT`. Budżet liczy porównania jako `Decimal` (6 miejsc); test obejmuje granicę `0.10 + 0.20` i realny wyścig dwóch konekcji SQLite.

Historyczny wynik WAVE 0B.1 (**741 passed**) został zastąpiony przez wynik WAVE 0B.2: **752 passed**. Nie uruchomiono API, sieci, browsera, publikacji, kosztu ani migracji `data/agent.db`; baseline SHA pozostaje `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.

## WAVE 0B.2 — zapis historyczny, zastąpiony przez WAVE 0B.3 (2026-07-14)

**Status historyczny: wynik 752 testów został zastąpiony przez WAVE 0B.3.** Etap 1 pozostaje `BLOCKED`. Produkcyjny klient Anthropic wymaga `DurableProviderAttemptContext` i potwierdzenia aktywnego `REQUEST_STARTED` tuż przed callerem/SDK; adapter offline jest jawnie oddzielony.

Addytywna migracja `0012_provider_ledger_hardening` waliduje przed kopiowaniem deterministiczny request_id oraz sprzeczną historię usage, a następnie wymusza relację request→attempt→job.run_id→usage.run_id. Udowodnione historyczne usage nie jest legacy; legacy oznacza wyłącznie brak historycznego request_id i ma immutable proof migracji. Runtime nie może zadeklarować legacy, a attempt #2 po `RESERVED`, `REQUEST_STARTED` albo `NEEDS_RECONCILIATION` jest blokowany atomowo.

Payload durable zawiera kanoniczny snapshot modelu, timeoutu, tokenów, cennika/fingerprintu, pipeline/prompt contract, capu i limitu requestów. Worker używa snapshotu po zmianie ENV. Kwoty są `ROUND_HALF_UP` do 6 miejsc; dodatnia sub-kwantowa wartość dająca zero jest typowo odrzucana. WAVE 1A (durable real A1/A2/B, real resume) i operator reconciliation pozostają poza zakresem.

## WAVE 0B.3 — historyczna derived request identity i świeży lease (2026-07-14)

**Status historyczny, zastąpiony przez końcową falę WAVE 0B.** `expected_request_id` jest wyłącznie dokładnym `f"{job_id}:{stage}:{attempt_no}"`: context, confirmation i `Idempotency-Key` muszą być równe tej wartości przed callerem/SDK. Nie ma normalizacji whitespace/case, stage nie może zawierać separatora, a nieprawidłowa tożsamość kończy się typed error bez callera.

`checked_at` pozostało śladem diagnostycznym i nie bierze udziału w autoryzacji. `assert_durable_provider_attempt_active()` pobiera bieżący czas z injected execution clock po `BEGIN IMMEDIATE`; odrzuca lease po expiry, takeover, zmianę run/fence i `NEEDS_RECONCILIATION`, a widzi odnowienie lease. Historyczna regresja offline: **770 passed**, koszt 0 USD, bez API/sieci/browsera/publikacji i bez zmiany baselineu bazy.

## WAVE 0B — domykająca fala po niezależnym review (2026-07-15)

**Status: `WAVE 0B CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 nadal `BLOCKED`; live API = `ZABRONIONE`.** WAVE nie jest zamknięta formalnie i nie odblokowuje paid workera, browsera, publikacji ani realnego resume.

- Kernel testowy jest aktywowany przez `sitecustomize.py` wyłącznie dla pytest albo dziedziczonego `NIA_TEST_MODE`. Przed collection, setup/call/teardown i w subprocessach czyści także lowercase `anthropic_api_key` oraz wszystkie proxy, blokuje `socket`/DNS, konstrukcję realnego `Anthropic`/`AsyncAnthropic`, `sqlite3.connect` i `sqlite3.dbapi2.connect` dla kanonicznie rozpoznanego `data/agent.db`. Chroni Windows drive-case, slash/backslash, lokalne URI `file:` i fail-closed odrzuca URI z nielokalnym authority; tymczasowe SQLite pozostaje dozwolone.
- Jedynym paid kontraktem pozostaje `durable_provider_v2` z `durable_research_intent_v2`. `0013_provider_attempt_usage_integrity` jest trzynastą i ostatnią obecną migracją; attempt runtime zapisuje SHA-256 kanonicznego `execution_intent`. Snapshot obejmuje canonical prompt-input (`question`, `niche`, `required_depth`, `guidance`), stage i wszystkie parametry requestu. Finalna asercja przed fake/SDK callerem ponownie kanonizuje `jobs.payload_json` i sprawdza pełne `job→run→research_run→attempt`; rozbieżność nie wykonuje callera, usage ani settlementu i przechodzi do `NEEDS_RECONCILIATION`. v1 fail-closed.
- `scripts/run_capped_research.py --resume … --real` odmawia przed `load_settings`, SQLite, `ensure_account`, polityką, klientem, usage trackerem i log writerem. Fake/offline resume pozostaje obsługiwane.
- Weryfikacja historyczna przed W0B-REV-06: collect **861**; cztery rozłączne grupy (204 + 217 + 212 + 228) dały **861 passed** offline; `data/agent.db` przed/po miała SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.

### W0B-REV-06 — spójność `max_tokens` i settlementu (2026-07-15)

**Status nadal: `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.** `max_tokens` jest wspieranym, dodatnim parametrem trwałego `durable_research_intent_v2`, objętym fingerprintem. Dispatcher przekazuje go jednocześnie do realnego klienta i do `run_research_pipeline`; pipeline używa go dla `estimate_worst_case_search_call_usd`, policy check i dokładnie tej samej rezerwacji provider attempt.

Settlement canonicalizuje rezerwację i actual cost do sześciu miejsc USD (`ROUND_HALF_UP`). Przy `actual_cost <= reserved_amount` attempt przechodzi do `SETTLED`. Przy `actual_cost > reserved_amount` jedna transakcja zachowuje `model_usage` i cache kosztu runu, ustawia attempt na `NEEDS_RECONCILIATION` z `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION` (bez cichego SUCCESS i bez attempt #2), a pipeline przekazuje typowany wynik do ścieżki verification. Operator reconciliation nadal nie istnieje.

Weryfikacja po W0B-REV-06 była **historyczna**: collect **873** i partycje **206 + 218 + 226 + 223 = 873 passed**. Nie jest to bieżąca liczba po W0B-REV-10.

### W0B-REV-09/10 — kronika i jeden kontrakt kwoty (2026-07-15)

Obowiązkowa kronika została uzupełniona, a wszystkie aktywne źródła wskazują ten sam stan. W0B-REV-10 przenosi estymator, `UsageTracker`, projekcje pipeline, rezerwacje, comparison actual/reserved i cache kosztu na wspólny kontrakt `Decimal(str(value)) → quantize(0.000001, ROUND_HALF_UP)`. Kwoty są sumowane jako Decimal przed pojedynczą granicą kwantyzacji; nie ma aktywnego Pythonowego `round(..., 6)` dla pieniędzy.

Weryfikacja po W0B-REV-09/10 jest **historyczna**: **887 collected/passed**; dokładny podział to **211 + 222 + 229 + 225 = 887**. Runner nadal używa pełnego SHA-256 UTF-8 node ID jako big-endian integer modulo 4 i potwierdza exact-once coverage, brak BOM, brak duplikatów, brak pominięć i brak nadmiarowych node IDs. Chroniona baza nie była otwierana do zapisu.

### W0B-RR-01 / W0B-CLEAN-01 — domknięcie agregacji i decyzji finansowych (2026-07-15)

Niezależny re-review znalazł pozostałą lukę: publicznie skwantyzowany koszt jednego źródła był mnożony w staged estimate, a policy, część storage/pipeline i komunikat CLI jeszcze wykonywały decyzje pieniężne na `float`. Naprawa nie zmienia lifecycle, intentu, `max_tokens`, request identity, schematu ani migracji. Estymator przechowuje raw komponenty jako `Decimal` do pojedynczej granicy publicznej, a policy, ledgerowe sumy, rezerwacje i CLI canonicalizują przez wspólny helper przed porównaniem lub wyświetleniem. Trzy składniki po `0.0000005` dają więc jeden wynik `0.000002`, nie trzy osobne roundingi.

Usunięto też dwa martwe konstruktory `AnthropicResearchClient` z prywatnych helperów resume w `scripts/run_capped_research.py`; real resume nadal kończy się fail-closed przed klientem, a dispatcher jest jedynym rootem realnego klienta. Końcowa walidacja offline: **894 collected/passed**, partycje **213 + 224 + 231 + 226 = 894**, pełny SHA-256 UTF-8 node ID modulo 4, exact-once, bez BOM, duplikatów, pominięć i nadmiarowych node IDs. Testy użyły wyłącznie fake callerów i tymczasowych SQLite. `WAVE 0B` ma status `APPROVED WITH P2 — READY FOR CHECKPOINT`; Etap 1 `BLOCKED`, live API `ZABRONIONE`. WAVE nie jest `CLOSED` przed commitem checkpointu.
