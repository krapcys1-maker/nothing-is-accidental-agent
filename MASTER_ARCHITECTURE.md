# MASTER_ARCHITECTURE — Nothing Is Accidental Agent

> **AKTUALIZACJA FORMALNA E2-A 2026-07-18 (ADR-103): ETAP 2 / WAVE E2-A = `CLOSED — APPROVED WITH MINOR/P2`; cały Etap 2 = `IN PROGRESS — E1 CLOSED, E2-A CLOSED, E2-B NOT STARTED`.** Niezależny review `APPROVE WITH MINOR/P2`, merge PR #5 (`404d2d306bbfa24fc08f2f5db68931e7441f040a`; rodzice `07fda5e68a61c7b9ff68e4388b2689acdca55818` i zatwierdzony head `61a509bd9c0a457ac78bb8893438664017a14063`) oraz post-merge checkpoint **1474/1474** (zero skipped, exact-once `357+361+369+387`) potwierdziły offline evidence integration spine w pełnym subprocess acceptance: CLI→enqueue→Worker→Dispatcher→STAGED A1/A2/B→`FakeFetch`→evidence→lokalny verifier→Research Card→atomowa terminalizacja→reopen. Trwały wynik z bazy: job `DONE`, run `DRY_RUN` (koszt 0), research_run `COMPLETE` (staged), topic `USED`, 1 Research Card, 3/3 source candidates `VERIFIED`, 3 retrievals, 3 excerpts, pełne lineage account/topic/run/candidate/source/card, drugi Worker `IDLE`; provider_attempts/model_usage/reservations/settlements `0`, koszt `0.000000 USD`. Kod ma migracje `0001`–`0017`, runtime wymaga dokładnie `0017`; produkcja pozostaje na `0014` (SHA `9906AFBFB580BE8F576A6449B0930C41ED964FED814D99C947D1C28C5B060836`, `364544 B`, integrity `ok`, FK `0`, bez WAL/SHM/journal; otwierana wyłącznie `mode=ro&immutable=1`); `0015`/`0016`/`0017` niezastosowane. Trzy findings review przyjęte jako P2: `E2-A-P2-01` (QA harness — `OPEN P2 / BACKLOG`), `E2-A-P2-02` (shape-invalid payload → `NEEDS_VERIFICATION` zamiast `FAILED` — `ACCEPTED P2`), `E2-A-P2-03` (brak SQL-owej niemutowalności `jobs.payload_json` — `OPEN P2 — FUTURE PAID/LIVE GATE`, MUST REASSESS przed paid staged recovery / realnym staged providerem / controlled-live / działaniem zewnętrznym zależnym od trwałego intentu). E2-B nie rozpoczęte; real Fetch, realny staged provider, controlled-live, browser i publikacja nie są autoryzowane; live nie jest gotowe.

> **HISTORYCZNY SNAPSHOT PRZED NIEZALEŻNYM REVIEW — E2-A 2026-07-18 (ADR-102; zastąpiony przez ADR-103 wyżej): `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`.** Nowy, jawnie wersjonowany i wyłącznie offline composition root łączy kolejkę Etapu 1 z fundamentem evidence E1: `enqueue-offline-evidence-research` → trwały job `offline_evidence_v1` → Worker/Dispatcher → STAGED A1/A2/B → `FakeFetch` → retrieval/canonical text → lokalny verifier → excerpt → lokalne `VERIFIED` → Research Card → jedna transakcja terminalizująca card/source lineage, research_run, run, topic i job. `0017_evidence_pipeline_lineage` jest addytywne i append-only; wymusza account/run/candidate/evidence/source identity triggerami niezależnymi od FK. Wznowienie wygasłego lease jest dozwolone tylko dla tego dokładnego zero-cost intentu bez provider attempt/usage/external effect. Legacy single i paid `durable_provider_v2` są nietknięte. Produkcja pozostaje na `0014`; live, realny Fetch/HTTP, provider, browser i publikacja nie są autoryzowane.

> **AKTUALIZACJA FORMALNA 2026-07-18 (ADR-101): ETAP 2 / WAVE E1 = `CLOSED — APPROVED WITH MINOR/P2`; cały Etap 2 = `IN PROGRESS — E1 CLOSED, E2 NOT STARTED`.** PR #3 został zmergowany do `main` jako merge commit `42762a76d8c151cdb13d07fa384d32c9bfef0231`, którego drugim rodzicem jest zatwierdzony head `f42790b4cbfdc9a2ede4ae02443e4973c14203a5`. Zamknięcie obejmuje wyłącznie izolowany fundament evidence i nie integruje go z pipeline'em researchu, nie zmienia `verification_status`, nie tworzy realnego Fetch adaptera oraz nie autoryzuje E2, live API, providera, browsera, publikacji ani migracji produkcji. Produkcyjna DB pozostaje na `0014`; `0015` i `0016` nie zostały zastosowane. Starsze noty o `Etap 2 = NOT STARTED` poniżej są historycznymi snapshotami sprzed rozpoczęcia E1.

> **AKTUALIZACJA POST-MERGE 2026-07-18 (ADR-098):** PR #1 został formalnie zmergowany do `main` jako merge commit `548cc65cad70eaef631fafff7c350845984d18e6`; zatwierdzony HEAD `4a63e18863cef74dc135d96a858614c4f8da212b` jest jego drugim rodzicem. Historyczny branch `dev/first-successful-research-card` jest technicznie zakończony i nie jest bazą dalszych zmian. Pierwszy suite na `main` ujawnił wyłącznie branch-sensitive test z zaszytą starą nazwą brancha (`1330 passed, 1 failed`); mały checkpoint `fix/post-merge-branch-sensitive-test` pobiera teraz branch i HEAD z kontrolowanego repo testowego, bez zmiany lub osłabienia produkcyjnego gate'u. Dowód po poprawce: 1331/1331, exact-once `320+322+339+350`, QA schema-gate 17/17, recovery 4/4 i lineage 10/10. Produkcja nadal ma `0014`; migracja `0015` wymaga osobnej autoryzacji. Etap 2 = `NOT STARTED`; live = `NOT AUTHORIZED`.

> **AKTUALIZACJA ARCHITEKTONICZNA 2026-07-18 (ADR-097, PR1-MAJ-005-RR-01):** runtime open i migration open są rozdzielone, a race pomiędzy immutable preflightem i writable open jest fail-closed bez mutacji. `SqliteStorage.open()` najpierw sprawdza istniejący ledger przez `mode=ro&immutable=1`, następnie otwiera dokładnie istniejący plik przez SQLite URI `mode=rw` — bez `mkdir`, tworzenia DB i PRAGMA — po czym ponawia exact-schema gate na tym samym writable handle. Dopiero udany drugi gate dopuszcza `foreign_keys`, `busy_timeout` i `journal_mode=WAL`. Usunięcie pliku kończy się typowanym `SchemaVersionUnavailable` bez jego odtworzenia; podmiana na `0014` kończy się `SchemaVersionTooOld` przy identycznych SHA/size/mtime/ledger i bez sidecarów. Każdy zapisowy composition root dziedziczy ten gate. Jawna inicjalizacja i migrator `0014→0015` pozostają osobne; produkcja nadal ma `0014`, a `0015` nie została zastosowana.

> **STATUS: JEDYNE ŹRÓDŁO PRAWDY O ARCHITEKTURZE.**
> Data: 2026-07-14 · Wersja: 1.5 · Zastępuje: `ARCHITECTURE.md` (V1), `docs/IMPLEMENTATION_PLAN.md` (CZĘŚCI A–F), `docs/AUDYT_ARCHITEKTURY_2026-07-12.md`, `docs/architecture/SUBSTACK_INTEGRATION.md` — wszystkie przeniesione do `docs/archive/superseded_plans/`.
>
> Kolejność prac: `IMPLEMENTATION_ROADMAP.md`. Aktualny stan: `CURRENT_PROJECT_STATE.md`. Rejestr decyzji (ADR): `docs/DECISIONS.md` (nadal obowiązujący — ten dokument konsoliduje decyzje, nie zastępuje rejestru).
>
> **AKTUALIZACJA ARCHITEKTONICZNA 2026-07-18 (ADR-096):** po `REJECT — MAJOR` review PR #1 kod otrzymuje addytywną migrację `0015_settled_execution_recovery`. Znany wynik finansowy pozostaje `SETTLED`; jedyny canonical `model_usage` i koszt są niezmienne. Osobne append-only zdarzenie `EXECUTION_RECOVERY` autoryzuje atomową terminalizację job/run/research_run: sukces tylko z wyłączną, zgodną Research Card; bez karty — `FAILED`; niespójny ledger/lineage/cache/fence/rezerwacja — fail-closed `NEEDS_VERIFICATION`. Brak providera, retry, attemptu #2 i drugiego usage. Kod jest kandydatem do niezależnego re-review (1311/1311, exact-once `314+319+333+345`, QA 4/4). Produkcyjna baza pozostaje na `0014`; zastosowanie `0015` do produkcji nie było częścią tej fali.
>
> **AKTUALIZACJA ARCHITEKTONICZNA 2026-07-18 (ADR-095):** WAVE OUTPUT-SIZE CONTRACT = `CLOSED — APPROVED WITH MINOR/P2`; POSITIVE CONTROLLED-LIVE = `INDEPENDENTLY CONFIRMED`; ETAP 2 POSITIVE-LIVE GATE = `FORMALLY ACCEPTED`; ETAP 2 = `NOT STARTED`. Po technicznym wyniku implementera i jego 1288/1288 (`306+312+328+342`) niezależny review wykonał 223/223 własnych wąskich testów, potwierdził exact-once i bajtową identyczność kodu/testów z zaakceptowanym baseline'em oraz wydał `APPROVE` bez CRITICAL, MAJOR i nowych MINOR. Właściciel formalnie przyjął bramkę; nie autoryzował kolejnego live, browsera ani publikacji. Gate `False`, flagi fail-closed, sześć P2 ADR-094 pozostaje nieblokującym backlogiem.
>
> Bieżący baseline całej suity po formalnym zamknięciu Etapu 2 / WAVE E2-A i merge PR #5 (ADR-103): **collect/full `1474/1474`, zero skipped, exact-once `1474` unikalnych node ID** (rzeczywiste post-merge partycje `357+361+369+387`), oraz QA: evidence foundation `79/79`, evidence migration `48/48`, E2-A acceptance `16/16`, evidence floor `35/35`, runtime schema gate `24/24`, settled recovery `4/4`, reconciliation lineage `10/10`, E2-A lineage `4/4`. Poprzedni baseline po WAVE E1 / merge PR #3 (`1454/1454`, partycje `352+355+366+381`) oraz historyczne `1331`/`1328`/`1311`/`1288`/`223` dowodzą wcześniejszych fal i nie są bieżącym baseline'em. Twierdzenia niezweryfikowane oznaczono `NOT VERIFIED`.
>
> **HISTORYCZNY SNAPSHOT ETAPU 1/LA-03 — zastąpiony przez ADR-094/095:** WAVE 0A/0B/1A były zamknięte, a pierwszy LA-03 request zakończył się rozliczonym parse failure bez karty. Ten zapis wyjaśnia drogę do zamknięcia Etapu 1; bieżący stan positive-live i Etapu 2 definiuje aktualizacja wyżej. Kolejny request nadal wymaga oddzielnej jawnej decyzji właściciela.

## P2 po LA-03 — zamknięty kontrakt jednej odpowiedzi i historyczne raporty

Produkcyjny durable `single` używa wyłącznie `_parse` z `app/research/anthropic_client.py`. Granica przyjmuje dokładnie jedną odpowiedź providera i nigdy nie generuje repair requestu. Parser dopuszcza jeden obiekt JSON albo jeden kompletny zewnętrzny fence zaczynający się literalnie od `json`; drugi `raw_decode` rozpoznaje każdy kolejny legalny JSON jako `multiple_json_values`, a root inny niż object daje schema error. Zamknięty schema contract wymaga wszystkich pól ResearchDraft, typowanych list stringów, score `0..1` i dokładnych kluczy/typów źródła. Score jest normalizowany przez `Decimal` i sprawdzany pod kątem skończoności oraz zakresu przed bezpieczną konwersją. Błędy dzielą się na `ResearchParseError`, `ResearchSchemaError` i `ResearchTruncatedError`; tylko jawne `stop_reason=max_tokens` jest dowodem truncation. Każdy wynik po providerze zachowuje usage/raw/stop reason, a prywatny plik diagnostyczny jest rekurencyjnie sanitizowany i zapisywany temp→file fsync→replace→directory fsync jako best-effort po terminalizacji, bez wpływu na kanoniczny wynik.

`run_controlled_live_once` nie ma fallbacku handle probe. Wymaga jawnego `frozen_quiescence` z fazy pre-storage; jedyny production root tworzy go przed `SqliteStorage.open`. Raport operatorski ma odrębne `session_id` (stabilna tożsamość operacji) i `invocation_id/report_key` (attempt, UTC timestamp, nonce). Wszystkie promocje w jednym invocation atomowo zastępują ten sam plik, ale kolejny invocation nie może nadpisać historii. Marker przechowuje `report_key`; recovery tworzy osobny raport i wskazuje poprzedni. Kolejność pozostaje: durable provisional report + fsync → marker clear + directory fsync → final report.

Historyczny request nie ma trwałego raw ani stop reason. Durable evidence dowodzi tylko `json_syntax` w line 29/column 6/char 4376; bardziej szczegółowa przyczyna byłaby zgadywaniem. Naprawiony kontrakt został obalany offline 28-klasową macierzą, durable settlement tests, pięcioklasową próbą sekretów i failpointami diagnostyki. Bieżący dowód to 1235/1235 i exact-once `294+299+311+331`; naprawa przeszła niezależny re-review z wynikiem `APPROVE WITH MINOR/P2` i jest podstawą formalnego zamknięcia Etapu 1 (ADR-088). Dwa nieblokujące MINOR/P2 dotyczą wyłącznie etykiet diagnostycznych parsera (`RV-R2-P2-1`, `RV-R2-P2-2`) i trafiają do backlogu Etapu 2. Zamknięcie nie autoryzuje kolejnego requestu.

---

## LA-03 — pre-storage quiescence i pierwszy rzeczywisty durable provider request

Realny composition root uruchamia `run_controlled_live_quiescence_check` przed `SqliteStorage.open`, zamraża czysty wynik DB/WAL/SHM, a po otwarciu jednego głównego storage ponownie sprawdza branch/HEAD, DB SHA, schema, job identity/claimability, pricing, intent i flags. Marker O_EXCL powstaje dopiero po pierwszej pełnej trwałej rewalidacji; druga rewalidacja potwierdza marker i niezmienność planu. Probe uchwytów nie został wyłączony: obce read-only/writable SQLite oraz uchwyty WAL/SHM nadal dają `DB_HANDLES_PRESENT`; własne storage otwarte po PASS korzysta z zamrożonego wyniku i nie jest ponownie klasyfikowane jako obce. Drift DB pomiędzy fazami kończy się przed markerem, flagami, workerem i providerem.

Dowód offline: 1181/1181, exact-once cover 1181, pełny fake subprocess CLI→storage→worker→fake provider→`REQUEST_STARTED`→usage→settlement→terminalizacja. Produkcyjny standalone przed i po realnym wykonaniu zwrócił `PASS`. Autoryzowana operacja utworzyła dokładnie jeden attempt/request, otrzymała HTTP 200, rozliczyła `0.053182 USD`, po czym typowany `ResearchParseError` terminalizował job/run/research_run jako `FAILED`. Wrapper zwrócił `VALIDATION_FAILED_FAIL_CLOSED`, ponieważ sukces wymaga Research Card, ale trwały finansowy i wykonawczy lifecycle jest domknięty: jeden `SETTLED`, jedno usage, brak lease/rezerwacji/reconciliation, marker cleared, flags fail-closed i gate `False`. To spełnia cel pierwszego provider requestu. (Stan zaktualizowany przez ADR-088: pozytywna Research Card nie była formalną bramką zamknięcia Etapu 1; Etap 1 = `CLOSED` 2026-07-17.)

## LA-02 — kanoniczny kontrakt quiescence dla controlled-live

Quiescence używa jednego snapshotu procesów. Current PID jest powiązany z systemowym parent PID, a każdy wykluczany przodek musi być rzeczywistym kolejnym PPID, mieć kompletne executable/command line/creation time, ten sam jednoznaczny entrypoint i czas utworzenia niepóźniejszy niż dziecko. PowerShell, pwsh, cmd, bash i inny lokalny shell są traktowane tak samo: nazwa executable nie wystarcza do wykluczenia. PID reuse, cycle, niespójny PPID, niepoprawny czas albo niepełna identity kończą się fail-closed. Current i zweryfikowani przodkowie są oznaczani `belongs_to_probe_ancestry`; helper pozostaje osobnym wyjątkiem opartym na PID/PPID/executable/creation time/nonce.

Role worker i maintenance mają pierwszeństwo przed ancestry. Niezależny operator z identyczną komendą, drugi controlled-live, scheduler/operator CLI, niezarejestrowany potomek, proces z DB handle i Windows Task nadal blokują. Adapter controlled-live przenosi pełne diagnostics. Raport odmowy zachowuje zewnętrzny `PREFLIGHT_FAILED`, wewnętrzny `PROCESSES_PRESENT`, `QUIESCENCE_PROJECT_PROCESSES`, check order, blocking PIDs, zredagowane command lines, classification/reason codes/ancestry i fingerprinty. `controlled-live-quiescence-check` składa dokładnie ten sam probe bez storage, SQLite open, providera, markera lub gate'u i sprawdza niezmienność DB/WAL/SHM przed/po.

LA-02 nie zmienia pricingu, durable ownership, settlementu, providera ani migracji. Niezależny review zatwierdził ją wynikiem `APPROVE WITH MINOR/P2`; checkpoint nie autoryzuje requestu. P2-2 pozostaje open observation: obce terminale, edytory lub shelle zawierające pełny tekst komendy mogą wywołać false STOP, dlatego standalone check musi zostać uruchomiony z tego samego launchera po zamknięciu takich procesów. Dowód: 1174/1174 testów, w tym realne subprocessy Windows na temp DB, bez sieci/API/SDK/browsera/publikacji/kosztu.

## Formalne zamknięcie WAVE 1A — 2026-07-16

Implementer zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW` po `W1A-R4-01`. Niezależny finalny re-review odtworzył 1036/1036 oraz cztery partycje exact-once, potwierdził `compileall` i `git diff --check`, a także wykonał 149/149 własnych kontrprób przez prawdziwy `Worker.run_once`, 36/36 sprawdzeń SQLite floor i 30/30 sprawdzeń recovery/reaper/crash-window. Nie znaleziono osiągalnego MAJOR ani CRITICAL. Reviewer wydał `APPROVE WITH MINOR/P2`, a właściciel formalnie zamknął WAVE 1A jako `CLOSED — APPROVED WITH P2`. P2-1 pozostaje fail-closed i widoczny operatorowi; P2-2 pozostaje świadomą granicą odpowiedzialności SQLite. To zamknięcie nie zmienia blokady Etapu 1 ani zakazu live API.

## Historia implementacji — WAVE 1A (2026-07-15–2026-07-16)

WAVE 0B jest `CLOSED — APPROVED WITH P2`; WAVE 1A jest kandydatem do niezależnego review (po naprawie `REJECTED — MAJOR`), nie zamknięciem Etapu 1. `0014_provider_attempt_reconciliation` (poprawiona in place) zachowuje jeden kanon kosztu (`model_usage`) i dodaje operatorskie, atomowe rozstrzygnięcie L1. `CHARGED_KNOWN` dopisuje lub weryfikuje dokładnie jeden usage po **pełnej tożsamości** (provider/model/task/run/konto/fingerprint/koszt) i przechodzi do `RECONCILED_SETTLED` (koszt musi być `> 0`); `NOT_CHARGED` zakazuje usage i przechodzi do `RECONCILED_RELEASED`; `CHARGE_UNKNOWN` dopisuje **append-only** zdarzenie do `reconciliation_events` (obserwacja/follow-up, idempotentne), pozostawiając rezerwację i `NEEDS_RECONCILIATION` — nigdy nie nadpisuje historii. `MANUAL_REVIEW_REMAINS_REQUIRED` jest dozwolone wyłącznie z `CHARGE_UNKNOWN`, więc terminalny wynik finansowy zawsze terminalizuje job (brak dead-endu). Wynik wykonawczy nie jest wyprowadzany z księgowania: `DONE` wymaga wyłącznej Research Card (`UNIQUE research_runs(research_card_id)`). Spójność `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd` jest niezmienna. Resolver nie ma providera, retry, attemptu #2, tworzenia karty ani drugiego ledgeru; CLI preview/confirm używa version tokenu. Walidacja: **980 offline testów**, 14 migracji, `data/agent.db` niezmieniona; Etap 1 `BLOCKED`, live API `ZABRONIONE`. (Historyczne 919/894/948/955 to wcześniejsze iteracje.) Poprawka `W1A-VERIFY-01` (ADR-064): resolver `EXECUTION_FAILED` akceptuje run w stanie `STOPPED` z maintenance-reapera (`run_status ∈ {RUNNING, STOPPED, FAILED}` przez wspólny `_EXECUTION_FAILED_RUN_STATUSES` dla warunku i CAS) i atomowo `STOPPED → FAILED`; `RESULT_ALREADY_FINALIZED` i kontrakt finansowy bez zmian; +7 deterministycznych testów, flaky node 30/30. Poprawka `W1A-VERIFY-02` (ADR-065): resolver waliduje pełny lineage `attempt→job→run→research_run→account→workflow→topic→durable intent` przed jakąkolwiek mutacją — `_reconciliation_state_row` czyta teraz `runs.account_id`/`runs.workflow`/`jobs.kind`/`jobs.workflow`/`research_runs.flow`, `_reconciliation_require_consistent_lineage` wymusza zgodność (wszystkie account_id równe, `runs.workflow=RESEARCH`, topic/flow/kind), version token v2 obejmuje pola lineage, a trigger `provider_attempts_reconcile_requires_consistent_lineage` (0014) jest warstwą SQLite. Wcześniej foreign `runs.account_id`/`workflow=ANALYTICS` był fail-open i nie był objęty 955/955; +25 testów lineage.

**Aktualizacja `W1A-R4-01` (ADR-067, 2026-07-16):** wszystkie workerowe failure/uncertainty boundaries przypiętego single research delegują decyzję do `StoragePort.fail_or_escalate_job_research_execution`. Operacja w jednym `BEGIN IMMEDIATE` odczytuje aktywny provider attempt, rewaliduje lifecycle/lease/fence i wybiera: normalne `FAILED` bez attemptu; `RESERVED`/`REQUEST_STARTED → NEEDS_RECONCILIATION` + jeden `AUTO_ESCALATION` + `job=NEEDS_VERIFICATION`; albo idempotentne zachowanie istniejącego reconciliation. Rezerwacja pozostaje aktywna do decyzji operatora; retry, attempt #2 i provider call są zabronione. SQLite blokuje terminalne job/run/research_run obok `RESERVED`/`REQUEST_STARTED`, ale pozwala resolverowi przy `NEEDS_RECONCILIATION`. **Granica P2-2:** StoragePort wykonuje resolver atomowo w jednej transakcji; SQLite wymusza spójny trwały stan końcowy; SQLite nie udowadnia pochodzenia wszystkich danych wobec arbitralnego uprzywilejowanego autora wielu tabel. To floor trwałego stanu, nie dowód autoryzowanego pochodzenia. P2-1 pozostaje fail-closed: normalization nie zmienia niespójnego durable intentu, a resolver nadal odmawia po fingerprint mismatch. Dowód: 1036 testów offline, partycje exact-once, concurrency 38×30, krytyczne pliki 10× i QA 10×.

## 1. Aktualny stan architektury (stan faktyczny kodu, nie planu)

### 1.1. Co istnieje i jest kompletne (uruchomione + przetestowane)

| Element | Pliki | Dowód |
|---|---|---|
| Konfiguracja (.env + YAML, zero ścieżek absolutnych) | `app/core/config.py` | testy + 4 realne runy |
| Modele domenowe (Pydantic v2) | `app/models.py` | testy |
| SQLite + 17 migracji w kodzie (`0001`–`0017`, produkcja: 14) + repozytoria | `app/storage/` | `0016` (E1) utrwala retrieval/excerpt; addytywne `0017` (E2-A, ADR-102) dodaje append-only candidate/retrieval/excerpt/card-source lineage. Runtime wymaga dokładnie `0017`; kroki `0014→0015`, `0015→0016` i `0016→0017` są jawne i osobne. Produkcja pozostaje na `0014`, 14 migracjach. |
| Trwała kolejka + worker offline | `app/storage/repositories.py`, `app/scheduler/`, `app/main.py` | atomowy enqueue/idempotency, lease, runtime flags, centralny `SchedulingPolicy`, zamknięty dispatcher LOCAL/RESEARCH dry-run, atomowa inicjalizacja job→run→research_run, reaper i `MaintenanceRunner`. Po inicjalizacji zamknięty `JobExecutionContext` przenosi job ID, ownera, run ID i Clock. Każdy failure/uncertainty przypiętego researchu przechodzi przez wspólną atomową normalizację provider attemptu; worker nie wybiera `FAILED` na podstawie klasy wyjątku. Guard jest sygnałem in-memory, SQLite pozostaje autorytetem. Expiry przypiętego RESEARCH → NEEDS_VERIFICATION, bez auto-resume; testy plikowej SQLite z Barrier/reopen |
| Systemowy launcher i raport | `app/scheduler/windows_tasks.py`, `scripts/manage_windows_tasks.py`, `scripts/run_*_task.ps1`, `app/main.py operational-report` | Windows Task Scheduler tylko uruchamia istniejące entrypointy; `IgnoreNew`, jawny Python/CWD, logi runtime, kontrolowany exit. Worker systemowy zawsze używa `--offline-only`. Raport otwiera bazę `mode=ro` + `query_only`, braki pokazuje jako `UNKNOWN/BLOCKED`. Zadań nie zarejestrowano; produkcyjna migracja 0014 została wykonana osobnym kontrolowanym executorem |
| Approved pricing i controlled-live composition root | `app/core/pricing.py`, `app/research/durable_intent.py`, `app/operations/controlled_live.py`, `app/main.py controlled-live-once`, `app/main.py controlled-live-quiescence-check`, `app/scheduler/dispatcher.py` | Profil approved jest pełnym kontraktem `Decimal`; enqueue/projekcja/intent/wrapper/dispatcher/report używają tej samej ceny. Sesja wiąże expected job/request/attempt/token; sukces wymaga trwałego lifecycle+usage+settlement po prawdziwym reopen. Pre-storage payload jest obowiązkowy; nie ma ukrytego probe po open. Raport per invocation jest trwały przed marker clear i append-preserving między invocation; recovery zachowuje `REQUEST_STARTED` bez retry. Positive controlled-live zakończył się `end_turn`, kartą `id=3` i `DONE/SUCCESS/COMPLETE/SETTLED`, a niezależny review 223/223 wydał `APPROVE`. Real gate pozostaje wyłączony; kolejny request nie jest autoryzowany |
| Policy Engine (kill-switch, runtime flags workera z SQLite, aktywność konta, budżet dzienny/miesięczny z priorytetem miesięcznym ADR-012, progi tematów) | `app/policies/policy_engine.py` | `tests/test_policy_engine.py`, `tests/test_worker_runtime.py` |
| Księgowanie kosztów (model_usage + COSTS.csv, flaga dry_run) | `app/llm/usage_tracker.py` | SQLite `model_usage` jest kanonem; `COSTS.csv` to odtwarzalny eksport best-effort po commicie |
| Pipeline tematów (generacja+scoring+dedup+progi) | `app/workflows/topics/` | testy; realnie NIGDY nie uruchomiony (`NOT VERIFIED` na żywym API) |
| Deduplikacja tematów (lokalna, bez kosztu, ADR-014) | `app/workflows/topics/dedup.py` | `tests/test_dedup.py` |
| Research etapowy A1/A2/B (ADR-020) + wznawialność po restarcie | `app/workflows/research/pipeline.py` | 351 testów; na żywo Task 9: A1 ✅, A2 4/4 ✅, pierwsze B `max_tokens`, kontrolowany resume wyłącznie B ✅; karta #2, COMPLETE/SUCCESS/USED, 4 VERIFIED, 0,183964 USD |
| Bramka jakości researchu (deterministyczna, min_verified_sources) | `app/research/validation.py` | testy |
| Injection guard (treść źródeł = dane, nie polecenia) | `app/research/injection_guard.py` | testy |
| Kalibrowany estymator kosztów (2 realne obserwacje, margines ≥50%) | `app/research/cost_estimator.py` | testy + 3 realne runy |
| Diagnostyka surowych odpowiedzi (stop_reason wprost z API) | `app/research/diagnostics.py`, `app/workflows/research/pipeline.py` | staged potwierdzone na żywo; durable single domknięte offline po historycznym braku evidence |
| CLI + jedyne bezpieczne wejście realnego researchu | `app/main.py`, `scripts/run_capped_research.py` | 3 realne użycia |
| Naprawy P0 z audytu 12.07 (SUCCESS-status, wymuszone UNVERIFIED, blokada `--real`) | pipeline, validation, runner | 7 testów regresyjnych |
| Procesowa izolacja testów i trwały paid intent | `sitecustomize.py`, `app/testing/safety_kernel.py`, `app/research/durable_intent.py`, `app/storage/repositories.py` | kernel działa przed collection i w subprocessach; blokuje sieć, realny SDK oraz wszystkie formy produkcyjnego SQLite. Provider attempt zapisuje kanoniczny fingerprint intentu i porównuje go w finalnej transakcji przed callerem; zmiana zatrzymuje attempt w `NEEDS_RECONCILIATION` |

### 1.2. Co jest częściowe

- **Policy Engine** — centralnie egzekwuje cap per-run oraz budżet dzienny/miesięczny przez `check_run_budget`; miesięczny zachowuje priorytet ADR-012. Worker odczytuje przy każdym jobie pięć flag SQLite fail-closed (`kill_switch`, `worker_enabled`, `safe_mode`, paid i browser), lecz paid/browser pozostają bezwarunkowo zablokowane. Brak nadal: egzekucji `autonomy_level`, `AccountMode`, limitów per konto, cooldownów i automatycznego wejścia SAFE MODE.
- **Klient Anthropic dla tematów** (`app/llm/anthropic_client.py`) — offline zweryfikowany kontrakt response→Usage→parse, typowane provider/parse/schema errors, jeden zewnętrzny code fence i księgowanie dostępnego usage przez workflow także przy błędzie; nadal nigdy nie uruchomiony realnie (`NOT VERIFIED live`).
- **Maszyna stanów researchu** — Etap 0 / Tasks 1–9 ukończone. Task 9 zachował A1 i 4×A2 po uciętym pierwszym B, następnie kontrolowany repair ustawił prawdziwy audit FAILED, a osobno zatwierdzony resume wykonał dokładnie jedno B bez search/retry. Finalizacja ustawiła `research_runs=COMPLETE`, `runs=SUCCESS`, topic `USED` i kartę #2 przy 4 VERIFIED oraz koszcie 0,183964 USD. Karta ma jakościowe `REJECT`, więc nie jest wejściem do treści. Staged B ma typowany context fresh/resume/force; marker force jest trwały per run, a resume wymaga CAS `FAILED/finished_at/error` i wcześniejszego B FAILED. Także identyczny terminalny no-op najpierw rewaliduje mode, marker force i trwały snapshot resume; sprzeczny context kończy się błędem bez mutacji. Historyczny `research_runs.error` po sukcesie pozostaje z pierwszego B jako nieblokujący P2-20; historia prób jest poprawnie zachowana również w `research_stage_results`. Rezydualne P2-17/P2-18/P2-19 pozostają bez zmian.

### 1.3. Co jest tylko szkieletem

- `BrowserPort` (`DisabledBrowser` — celowo blokuje każdą akcję), `SchedulerPort` (`StubScheduler`).
- Tabele bez żadnego kodu, który je czyta/pisze (schemat od migracji 0001): `content_items`, `interactions`, `target_items`, `approvals`, `metrics_daily`, `screenshots`.

### 1.4. Co jest błędne lub nieużywane (martwy kod)

- `EnvSecretStore` i `LocalFileStore` — zdefiniowane, zero wywołań w całym repo (config czyta `os.getenv` bezpośrednio).
- Minimalna konfiguracja Windows Task Scheduler istnieje jako kontrolowany launcher kanonicznego `worker --once --offline-only` i `maintain --once`; nie jest nowym schedulerem domenowym. Żadne zadanie nie zostało zarejestrowane i nie ma autostartu bez osobnej zgody właściciela.
- Legacy pipeline'y researchu (`run_research_pipeline` jednoetapowy, `run_two_stage_research_pipeline`) — działają i mają testy, ale są NIEZALECANE (ADR-016→020). Manualne wywołanie bez joba zachowuje dawne mutacje; jedynie zamknięta gałąź workera tego samego single pipeline używa worker-only fenced API i nie może wywołać legacy finalizerów.

### 1.5. Duplikacja logiki

- **Bramka budżetowa**: `PolicyEngine.check_run_budget(projected_total, cap, current_run_cost, account)` jest kanonem dla capu runu i limitów D/M; niepoprawne limity/sumy kończą się fail-closed. Realny pipeline wymaga jawnego capu, resume używa absolutnego capu i waliduje run–account przed odczytem usage. CLI tylko zbiera argumenty, estymuje i deleguje. `model_usage(dry_run=0)` pozostaje jedyną podstawą decyzji.
- **Dwie kalibracje estymatora**: legacy liczy z cennika w runtime, staged ma stałe `0.04875`/`0.020956` — rozjadą się przy zmianie cen w `.env`.
- **Trzy tabele źródeł** dla trzech generacji przepływu (`sources`, `research_sources`, `research_source_candidates`) — świadome (supersede-nie-usuń), konsolidacja dopiero po wygaszeniu legacy.

### 1.6. Gdzie kod nie zgadzał się z dokumentacją

Pełna lista 14 rozbieżności była w audycie 12.07 (zarchiwizowany). Wszystkie rozbieżności rozstrzyga **ten dokument** — w każdym przypadku obowiązuje wersja opisana tutaj. Najważniejsze rozstrzygnięcia: `StoragePort` z typowanymi metodami (kod) jest lepszy niż generyczna specyfikacja (stary plan) — obowiązuje kod; `model_usage` z kolumnami `task`/`dry_run` — obowiązuje kod; `ProposedAction`, `PromptRegistry`, `ToolRegistry` — nie istnieją, są elementami architektury docelowej (sekcja 2), nie stanu obecnego.

---

## 2. Docelowa architektura

**Styl: modularny monolit + porty/adaptery. Jeden proces, SQLite, lokalnie → VPS. Bez mikroserwisów, bez zewnętrznych kolejek, bez Postgresa** (dopóki nie pojawi się realna współbieżność zapisu — patrz sekcja 10).

```
                    ┌─────────────────────────────────────────────┐
                    │ WEJŚCIA: app/main.py (CLI) · panel FastAPI  │
                    │ scripts/ = cienkie aliasy, nie druga logika │
                    └────────────────────┬────────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────┐
                    │ SCHEDULER: tabela `jobs` (SQLite) + jeden   │
                    │ worker loop; lease/lock; idempotency_key;   │
                    │ kind='browser' serializowany globalnie      │
                    └────────────────────┬────────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────────┐
                    │ ORCHESTRATOR: jedyny punkt egzekucji akcji  │
                    │ KAŻDA akcja: PolicyEngine.check(action,ctx) │
                    │ → wykonaj → zapisz skutek → potwierdź       │
                    └───────┬─────────────────────┬───────────────┘
                            ▼                     ▼
        ┌───────────────────────────┐  ┌─────────────────────────────────┐
        │ POLICY ENGINE (determini- │  │ WORKFLOWS (rdzeń domenowy)      │
        │ styczny, poza modelem):   │  │ topics · research (A1/A2/B) ·   │
        │ autonomy_level · mode ·   │  │ content (article/note) ·        │
        │ budżety D/M · cap per-run │  │ interactions · analytics ·      │
        │ · limity akcji · cooldown │  │ strategy                        │
        │ · kill-switch/SAFE MODE   │  └───────────┬─────────────────────┘
        │   (z DB, runtime)         │              │
        └───────────────────────────┘              ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ PORTY (Protocol) i ADAPTERY:                                 │
        │ StoragePort→SQLite · LLM/ResearchClient→Anthropic|Fake ·     │
        │ FetchPort→web_fetch · PublicationChannelPort→Substack        │
        │ (Playwright)|Export · NotificationPort · SecretStorePort ·   │
        │ FileStorePort · SchedulerPort                                │
        └──────────────────────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────────────────────┐
        │ SQLite (WAL): kanon kosztów = model_usage · audyt = runs +   │
        │ *_stage_results + autonomous_decisions · jobs · system_flags │
        └──────────────────────────────────────────────────────────────┘
```

### 2.1. Moduły, odpowiedzialności, granice

| Moduł | Odpowiedzialność | Granica (czego NIE robi) | Stan |
|---|---|---|---|
| **Orchestration layer** (`app/orchestrator/`) | składanie zależności, jedyny punkt egzekucji akcji zewnętrznych i płatnych | zero logiki domenowej; model językowy NIGDY nie woła portów bezpośrednio | zalążek (runner.py) |
| **Scheduler** (`app/scheduler/`) | czysty `SchedulingPolicy` planuje przed enqueue; worker wybiera przez atomowy claim; maintenance robi recovery→reaper; Windows Task Scheduler może tylko uruchamiać kanoniczne one-shot entrypointy z `IgnoreNew`, jawnym CWD/Python i logami runtime | systemowy worker ma twarde `--offline-only`; brak rejestracji zadań, paid/browser, retry dispatchu i globalnego kill-timeoutu | VERIFIED OFFLINE / NOT REGISTERED |
| **Task queue** | ta sama tabela `jobs` (kolejka = scheduler w SQLite, nie osobny system) | brak zewnętrznego brokera | VERIFIED OFFLINE |
| **Workers** | jeden proces workera, lease/CAS i daemon periodic heartbeat guard z osobnym storage podczas dispatchu; zamknięty dispatcher, osobny reaper i maintenance; systemowy wariant workera blokuje real research niezależnie od flag | brak puli procesów, paid/browser, auto-resume, retry dispatchu; zadania systemowe nie są zarejestrowane | VERIFIED OFFLINE |
| **Research engine** (`app/research/`, `app/workflows/research/`) | A1 discovery → A2 per-source extraction (z fetch treści — docelowo) → B synthesis; wznawialność; evidence | nie pisze artykułów; nie publikuje | WORKING |
| **Content planner** | wybór: artykuł vs Note, Article Brief, kandydaci harmonogramu i `SKIP` z reason code | nie generuje treści ani nie wymusza publikacji | NOT_STARTED; blueprint PROPOSED |
| **Writing engine** (`app/workflows/content/`, przyszły) | draft artykułu/Note wg `instrukcja dla pisania artykulow/`; rewrite po audytach | nie publikuje; startuje ZAWSZE od bramki Policy | NOT_STARTED |
| **Quality scoring** | 3 deterministyczne audyty (fact/style/growth) + progi z configu; scoring gates dla autonomii | samoocena modelu nigdy nie jest jedyną bramką | NOT_STARTED |
| **Evidence & citation handling** | każde twierdzenie → źródło + `evidence_excerpt` (cytat z treści źródła po fetch); citable_numbers z kontekstem | wiedza modelu nie zastępuje dowodu (P0-2) | OFFLINE INTEGRATION CLOSED (E2-A = APPROVED WITH MINOR/P2, ADR-103) — E2-A łączy prawdziwy CLI/Worker/Dispatcher ze STAGED fake A1/A2/B, `FakeFetch`, E1 verifierem i Research Card; `0017` utrwala pełny minimalny lineage. Legacy/paid staged i realny Fetch nadal nie istnieją. |
| **Memory** | SQLite jako pamięć trwała (topics/cards/content/metrics); brak osobnego vector-store w MVP | — | WORKING (w zakresie zbudowanym) |
| **Strategy engine** | analiza metryk → `strategy_decisions` (log) → korekty parametrów w configu, nigdy „po cichu" | nie zmienia polityk bezpieczeństwa | NOT_STARTED |
| **Analytics** | kolektor metryk → `metrics_daily`; followers, free/paid/engaged subscribers rozdzielone, estymacje jawnie oznaczane | follows ≠ subscriptions | NOT_STARTED (tabela czeka; blueprint PLANNED) |
| **Budget & cost control** | `model_usage` = JEDYNY kanon kosztu; PolicyEngine gate przed KAŻDYM płatnym wywołaniem; cap per-run w bibliotece | `runs.cost_usd`/`research_runs.total_cost_usd` = cache, nigdy podstawa decyzji | WORKING (centralny cap i retry budget zbudowane w Task 5) |
| **Model provider abstraction** (`app/llm/`, `app/research/base.py`) | Protocole `LLMClient`/`ResearchClient`; `ModelRouter` (zadanie→model z .env); Fake dla dry_run | logika biznesowa nie zna nazw modeli ani SDK | WORKING (sekcja 6) |
| **Publication adapters** | `PublicationChannelPort` — wspólny kontrakt kanałów (sekcja 8) | rdzeń nie zna Substacka | NOT_STARTED |
| **Substack adapter** | Playwright, dedykowany profil per konto, ręczne logowanie (magic-link), screenshoty, stop-conditions | nigdy auto-login, nigdy zapis hasła, brak prywatnych endpointów | NOT_STARTED (projekt: sekcja 8.2) |
| **Approval & autonomy** | poziomy LEVEL_0–3 (ADR-017), macierz akcji×poziom, tabela `approvals`, SAFE MODE | autonomia dotyczy WYKONANIA, nie ujawniania natury agenta (ADR-018) | NOT_STARTED (specyfikacja: sekcja 7) |
| **Audit log** | `runs` + `research_stage_results` + `autonomous_decisions` (przyszła) + `HUMAN_INTERVENTIONS.md`; każda decyzja/koszt/błąd/interwencja zapisywalna | — | PARTIAL |
| **Retry system** | retry TYLKO błędów transient (timeout), twardy limit prób, re-check budżetu przed każdą próbą, estymata ×(1+retries); błąd parsowania NIGDY nie jest ponawiany | ŻADNEGO auto-retry publikacji (UNCERTAIN → człowiek/odczyt stanu) | WORKING dla researchu; topics nie retry'uje parse/schema errors |
| **Failure recovery** | stany trwałe w SQLite po każdym etapie; wznowienie po restarcie czyta BAZĘ, nie pamięć; reaper po recovery oraz maintenance one-shot/poll; Task Scheduler może cyklicznie uruchamiać one-shot bez overlapu | brak auto-resume; systemowe zadania nie są zarejestrowane | VERIFIED OFFLINE / NOT REGISTERED |
| **Configuration system** | `.env` (sekrety, modele, tryby) + `config/*.yaml` (polityki, wagi, limity); wartości NIGDY w kodzie | — | WORKING |
| **Secrets management** | `.env` + `.gitignore` (ADR-010); docelowo przez `SecretStorePort` (adapter istnieje, nieużywany — podpiąć zamiast `os.getenv`) | zero haseł Substacka gdziekolwiek | WORKING (adapter martwy — dług) |
| **Backend API / frontend** | panel FastAPI, localhost-only (ADR-009): readonly stan + approvals + kill-switch (flaga DB) | brak wystawiania na sieć publiczną w MVP | NOT_STARTED |
| **Database** | SQLite + migracje plikowe; WAL potwierdzany dla każdego plikowego połączenia + busy_timeout=5000 (baza `:memory:` nie wymaga WAL); backup przed oknami publikacji | Postgres poza zakresem do czasu realnej współbieżności | WORKING |

---

## 3. Przepływy danych (workflow krok po kroku)

Konwencja: `[P]` = bramka PolicyEngine, `[$]` = płatne wywołanie API (zawsze poprzedzone `[P]` budżetu z pesymistyczną estymatą), `[DB]` = trwały zapis.

### 3.1. Wybór tematu (ZBUDOWANE)
`[P] can_run → [P] budżet → [$] generate_and_score_topics → scoring wg wag z configu → dedup lokalny (Jaccard+SequenceMatcher, per konto) → progi (SELECTED ≥75 / SCORED ≥65 / REJECTED / DUPLICATE) → [DB] topics → [DB] model_usage+COSTS.csv → [DB] runs: SUCCESS|DRY_RUN`

### 3.2. Research → karta badawcza (ZBUDOWANE, ADR-020)
```
[P] can_run → plan (lokalny, bez kosztu)
→ [P] budżet A1 → [$] A1 discover (web search, JSONL url+title; ucięta linia = pomijana)
  → injection guard → [DB] kandydaci + status DISCOVERY_COMPLETE (atomowo)
→ pętla per źródło: [P] budżet A2 → [$] A2 extract (JEDNO źródło = JEDNO wywołanie)
  → [DB] NATYCHMIAST po każdym (sukces LUB błąd; awaria N nie dotyka 1..N-1)
→ próg: ≥min_sources EXTRACTED? → SOURCES_COMPLETE : PARTIAL (STOP, bez płacenia za B)
→ [P] budżet B → [$] B synthesize (ZERO search, input pod kontrolą)
→ walidacja deterministyczna (min źródła, min VERIFIED w realnych runach,
  teza poparta, twierdzenia ze źródłami, progi confidence/jakości)
→ [DB] research_cards+sources → [DB] runs: SUCCESS → docs/RESEARCH_LOG.md
```
Błąd B → status wraca do SOURCES_COMPLETE (źródła nietknięte, ponawialne w nieskończoność bez web search). Wznowienie po restarcie: `resume_staged_research` czyta stan z bazy i wykonuje DOKŁADNIE JEDEN kolejny etap.

### 3.3. Walidacja researchu (ZBUDOWANE)
Deterministyczna bramka `validate_draft` — poza modelem. REJECT przy: za mało źródeł, za mało VERIFIED (realne runy), teza bez poparcia, twierdzenia bez źródeł, słabe źródła, niska pewność, wymagane doświadczenie osobiste, nieusuwalne sprzeczności. Karta zapisywana TAKŻE po odrzuceniu (audyt).

### 3.4. Generowanie artykułu → scoring → poprawki (DOCELOWE, Etap 3)
`[P] check(action=CREATE_ARTICLE/CREATE_NOTE: mode+autonomy+limity) → planner wybiera kartę PROCEED i Article Brief → [$] draft A1–A9 lub lokalny/dry-run Note N1–N16 (wg podręcznika stylu) → [$|lokalnie] fact/style/growth audit + SEO metadata + diversity memory → wynik < progu? → SKIP(reason code) albo [$] rewrite (max N) → [DB] content_items: DRAFT→PENDING_APPROVAL`. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` (PROPOSED/PLANNED) oraz pełny zewnętrzny snapshot `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md` (NOT IMPLEMENTED); Etap 3 nie publikuje Notes.

### 3.5. Akceptacja lub automatyczne zatwierdzenie (DOCELOWE, Etap 4)
`content PENDING_APPROVAL → PolicyEngine: wymaga człowieka? (poziom autonomii × typ akcji × scoring gate) → TAK: [DB] approvals PENDING → decyzja w panelu → APPROVED|REJECTED · NIE (LEVEL_2/3 + scoring ≥ progu): auto-APPROVED + [DB] autonomous_decisions (pełny log: co, dlaczego, jakie progi)`

### 3.6. Publikacja (DOCELOWE, Etap 5)
```
APPROVED → [DB] job (kind='browser', idempotency_key=hash(account,type,content_id))
→ worker: lease → [P] check(PUBLISH: limity dzienne/tygodniowe, cooldown, kill-switch, SAFE MODE)
→ verify-before-publish: czy treść już wisi? (odczyt stanu) → TAK: job DONE (idempotencja)
→ [DB] content: PUBLISHING → Playwright: publikuj → screenshot
→ potwierdzenie odczytem stanu: PUBLISHED (external_url) | UNCERTAIN
→ UNCERTAIN: NIGDY auto-retry — job NEEDS_VERIFICATION → odczyt stanu lub człowiek
→ crash/restart w trakcie: wygasły lease → NEEDS_VERIFICATION (nie „wykonaj ponownie")
```

### 3.7. Komentarze i odpowiedzi (DOCELOWE, Etap 6)
`wybór Notes do publikacji + discovery targetów (read-only) → scoring K1–K8 i antyspam → [P] check(NOTE/COMMENT/REPLY/RESTACK: limity, cooldown, link ratio) → generacja → approval wg poziomu → publikacja jak 3.6 → odpowiedzi: te same limity + NO_REPLY dla pytań o tożsamość (ADR-018)`. Publiczne Notes, komentarze i restacki zaczynają się wyłącznie w Etapie 6; blueprint i raport Fable są planem, nie implementacją.

### 3.8. Analiza wyników → zmiana strategii (DOCELOWE, Etap 7)
`kolektor metryk (read-only, Playwright) → [DB] metrics_daily (followers oraz free/paid/engaged subscribers rozdzielone; estymacje oznaczone) → atrybucja per content item → tygodniowa analiza i eksperymenty → [DB] strategy_decisions → korekta parametrów treści/harmonogramu w configu → NIGDY zmiana polityk bezpieczeństwa`. Szczegóły i ograniczenia danych: blueprint (PLANNED/PROPOSED) i pełny raport Fable (MIXED / NOT IMPLEMENTED).

### 3.9. Obsługa błędów (OBOWIĄZUJE WSZĘDZIE)
- Błędy providera są typowane przed decyzją retry. Retry z twardym limitem wolno wykonać tylko dla timeoutu, SDK-klasyfikowanego błędu połączenia, HTTP 429 oraz 500/502/503/504; przed KAŻDĄ próbą callback wykonuje ponowny `[P]` z aktualnym `model_usage`. HTTP 400/401/403/404/422, nieznany błąd providera, parse, truncation, validation i budget denial nigdy nie są retry’owane.
- `stop_reason=max_tokens` = typowany `ResearchTruncatedError` przed parse → zero retry, usage zapisane raz, diagnostyka zawiera limit; brak częściowej karty. Pozostały błąd parsowania JSON = NIE-transient → zero retry.
- Kontrolowany błąd B kończy ogólny audit jako FAILED (`finished_at` i error), ale szczegółowy research wraca do SOURCES_COMPLETE. Jawny resume używa `finish_resumed_research_run` z CAS i nie powtarza A1/A2.
- Trwały audit błędu researchu ma jeden bezpieczny format: `[stage] DomainError(status_code=..., retryable=..., stop_reason=...): message`. `runs`, `research_runs`, stage log i candidate error używają wspólnego formattera; mapper SDK tworzy komunikat wyłącznie z kontrolowanej klasy/statusu (nigdy z `str(APIStatusError)`), `raw_text`, body, cause, request/response i nagłówki nie są serializowane, a `sk-ant-*`, nazwane klucze i każdy `Bearer <token>` są redagowane.
- Każdy etap zostawia stan trwały w SQLite → wznowienie po restarcie zawsze z bazy.
- Kolejne błędy tej samej klasy ≥ progu → SAFE MODE (wejście automatyczne, wyjście TYLKO ręczne).

### 3.10. Rozliczanie kosztów — również nieudanych wywołań (ZBUDOWANE dla researchu)
Wyjątek `ResearchError` niesie `usage`/`model` z udanego wywołania API, którego wynik nie dał się sparsować → pipeline księguje koszt do `model_usage` ZANIM zwróci błąd. Typowany `ResearchProviderError` zachowuje usage tylko wtedy, gdy adapter rzeczywiście je otrzymał; przed retry usage jest przekazywane do workflow-owned callbacku i czyszczone z wyjątku, więc nie powstaje dubel. Brak usage nie tworzy fikcyjnego wpisu 0 USD. Klient tematów stosuje bezpieczny porządek response → `Usage` → parse. **Ryzyko rezydualne P2-19:** timeout może być zbilowany serwerowo bez lokalnego `usage`; nie wolno przedstawiać tego jako kosztu 0.

---

## 4. Model danych

Kanon: **`model_usage` = jedyne źródło prawdy o koszcie** (`dry_run=0` → budżet). `runs.cost_usd`, `research_runs.total_cost_usd` = cache. **Izolacja kont: `account_id` obowiązkowy w każdej encji per-konto.**

### 4.1. Encje istniejące (migracje 0001–0009)

| Encja | Przeznaczenie | Kluczowe pola | Statusy | Relacje / idempotencja |
|---|---|---|---|---|
| `accounts` + `account_policies` | publikacja/konto + jej limity (= **publication** w nomenklaturze docelowej) | id, mode, autonomy_level, active; limity dzienne/tygodniowe | mode: FULL_PUBLICATION/COMMENT_ONLY/DRAFT_ONLY/RESEARCH_ONLY | upsert po id (idempotentne `ensure_account`) |
| `topics` | temat (= **topic**) | account_id, title, question, score, score_breakdown, duplicate_of, rejection_reason | DISCOVERED→SCORED/SELECTED/REJECTED/DUPLICATE→USED | dedup lokalny per konto przed insertem |
| `runs` | przebieg workflow (= **audit event** poziomu runu) | id (uuid), workflow, status, cost_usd (cache), error | RUNNING→SUCCESS/FAILED/STOPPED; DRY_RUN | id generowany raz, przekazywany wszędzie |
| `research_runs` | maszyna stanów researchu (= **research task**); id = runs.id (rozszerzenie 1:1) | flow, status, stage_*_completed_at, research_card_id, error | patrz sekcja 5 | koszt przez model_usage.run_id — bez własnej tabeli kosztów |
| `research_source_candidates` | kandydat A1 ewoluujący w Source Card po A2 (= **source** + **claim** w postaci supported_claims_json) | url, title, supported_claims, numeric_facts, verification_status, quality, extraction_error, attempts | PENDING_EXTRACTION→EXTRACTION_IN_PROGRESS→EXTRACTED/EXTRACTION_FAILED | attempts = atomowo zarezerwowane A2; historyczne wartości są dolną granicą; retry tylko jawnie i poniżej capu |
| `research_sources` | trwałe źródła STAREGO przepływu (legacy) | jak wyżej, bez statusu per źródło | — | do konsolidacji po wygaszeniu legacy |
| `research_cards` + `sources` | karta badawcza (= **research card**) + źródła finalne | question, working_thesis, confirmed/uncertain_claims, contradictions, confidence, recommendation | PROCEED/REVISE/REJECT (rekomendacja) | karta zapisywana też po odrzuceniu |
| `research_stage_results` | log KAŻDEJ próby etapu (= **retry**/**failure** log researchu) | stage (A/A1/A2/B), status, error | SUCCESS/FAILED | append-only |
| `model_usage` | wywołanie modelu (= **model call** + **cost record**) | run_id, task, tokeny, web_search_requests, estimated_cost_usd, dry_run | — | append-only; koszt zapisywany TAKŻE przy błędzie |
| `jobs` | trwałe zadanie kolejki | kind, workflow, payload_json, status, priority, idempotency_key, lease, attempts, `run_id`, marker skutku i rezerwacja | QUEUED→LEASED→RUNNING→DONE/FAILED/NEEDS_VERIFICATION/CANCELLED | UNIQUE idempotency; partial UNIQUE aktywnego researchu per account/topic; worker atomowo tworzy zgodny single-flow run, research_run i `run_id`; expiry z `run_id` wymaga reconciliation |
| `system_flags` | runtime safety flags workera | key, value_json, reason, updated_at | JSON boolean albo fail-closed | odczyt SQLite bez cache; `kill_switch`, `worker_enabled`, `safe_mode`, paid/browser |
| `content_items` | artykuł/Note (= **draft**, **article**, **note**) — SCHEMAT BEZ KODU | type, title, body, status, score, research_card_id, external_url | docelowe: sekcja 5 | — |
| `interactions` | komentarz/odpowiedź/lajk (= **interaction**, **comment**, **reply**) — SCHEMAT BEZ KODU | target_item_id, type, body, status | docelowe: sekcja 5 | — |
| `target_items` | cudza publikacja do interakcji — SCHEMAT BEZ KODU | author, item_url, relevance_score | — | UNIQUE(account_id, item_url) |
| `approvals` | decyzja człowieka (= **human intervention** strukturalna) — SCHEMAT BEZ KODU | object_type+object_id, decision, notes | PENDING/APPROVED/REJECTED | — |
| `metrics_daily` | metryki dzienne — SCHEMAT BEZ KODU | subscribers, views, likes…, is_estimated | — | UNIQUE(account_id, date) |
| `screenshots` | dowody wizualne — SCHEMAT BEZ KODU | run_id, path, description | — | — |

**Budget** = konfiguracja (`max_daily_cost_usd`, `max_monthly_cost_usd` w growth_policy), nie tabela — egzekwowana przez PolicyEngine sumą z `model_usage`.

### 4.2. Encje docelowe (do dodania w etapach roadmapy)

| Encja | Etap | Przeznaczenie / kluczowe pola |
|---|---|---|
| `research_source_candidates.attempts` (kolumna) | 0 | jawny, capowany retry nieudanych kandydatów |
| `evaluations` (= **evaluation**) | 3 | wynik audytu treści: content_id, kind (fact/style/growth), score, findings_json |
| `autonomous_decisions` | 4 | log każdej decyzji podjętej bez człowieka: action, inputs, thresholds, outcome |
| `strategy_decisions` (= **strategy decision**) | 7 | data, problem, dane wejściowe, decyzja, oczekiwany efekt, wynik po fakcie |

### 4.3. Zasady idempotencji (obowiązujące)

1. Operacje płatne: nigdy nie powtarzaj automatycznie etapu, który zostawił trwały wynik (resume wykonuje wyłącznie NASTĘPNY etap).
2. Publikacja: `idempotency_key` + verify-before-publish + wynik UNCERTAIN nigdy nie jest retry'owany automatycznie.
3. Zapisy stanu: przejście statusu + dane w JEDNEJ transakcji. RESEARCH worker używa `initialize_research_run_for_job`: po weryfikacji joba, kind/workflow, ownera i świeżego lease `BEGIN IMMEDIATE` tworzy `runs`, `research_runs` i CAS `jobs.run_id IS NULL`; każdy `BaseException` przed commitem rollbackuje cały komplet. Gdy `run_id` już istnieje, adapter waliduje i zwraca istniejący komplet, a worker fail-closed kieruje go do weryfikacji zamiast go wykonywać. Staged B nadal używa własnego atomowego finalizera; kanoniczny koszt pochodzi wyłącznie z `model_usage`.
4. Każdy istniejący helper zmieniający status waliduje stan poprzedni w tym samym UPDATE (`WHERE status IN (...)`, a dla researchu także `flow`) i wymaga dokładnie jednego zmienionego wiersza. `rowcount=0` daje typowany błąd z aktualnym stanem, z wyjątkiem jawnych no-opów idempotencji; `rowcount>1` jest błędem integralności.

---

## 5. Maszyny stanów (dozwolone przejścia — inne są błędem)

```
runs.status:
  RUNNING → SUCCESS | FAILED | STOPPED
  DRY_RUN → DRY_RUN | FAILED
  FAILED → FAILED  (NIE przez finish_run; wyłącznie `finish_resumed_research_run` z poprawną relacją run–research–topic–account, flow/status i tokenem CAS)
  identyczne powtórzenie terminalizacji = no-op; inny terminal = błąd
  reaper (Etap 1, wdrożony offline): po recovery jobów RUNNING starszy niż jawny X
  bez joba QUEUED/LEASED/RUNNING → STOPPED(stale); NEEDS_VERIFICATION nie daje resume

topics.status:
  DISCOVERED → SCORED | SELECTED | REJECTED | DUPLICATE
  SELECTED → USED   (jedna transakcja z `research_runs.status=COMPLETE` i terminalnym `runs.status`; COMPLETE wymaga karty tego samego tematu i konta; identyczna refinalizacja = no-op, sprzeczna = błąd integralności)

research_runs.status (flow='staged'):
  DISCOVERY_PENDING → DISCOVERY_COMPLETE → EXTRACTION_IN_PROGRESS
    → SOURCES_COMPLETE ⇄ SYNTHESIS_PENDING → COMPLETE
    → PARTIAL            (z DISCOVERY_COMPLETE/EXTRACTION_IN_PROGRESS/PARTIAL; wznawialne: wyłącznie A2)
    → PARTIAL_EXHAUSTED  (brak legalnego PENDING/FAILED poniżej capu, EXTRACTED < min — terminalny dla zwykłego resume)
  PARTIAL_EXHAUSTED → PARTIAL (TYLKO jawne retry-failed-candidates po podniesieniu capu)
  DISCOVERY_PENDING → FAILED (terminal)
  (flow='single': PENDING → COMPLETE | FAILED)
  (flow='two_stage', legacy: PENDING → SOURCE_COLLECTED → COMPLETE | PARTIAL; PENDING → FAILED; PARTIAL może zapisać wynik kolejnej jawnej próby resume)

research_source_candidates.status:
  PENDING_EXTRACTION → EXTRACTION_IN_PROGRESS  (atomowy claim: attempts < cap)
  EXTRACTION_IN_PROGRESS → EXTRACTED | EXTRACTION_FAILED
  EXTRACTION_IN_PROGRESS → [wymaga jawnego recovery po awarii; zwykłe resume odmawia]
  EXTRACTION_FAILED → PENDING_EXTRACTION   (TYLKO jawny retry, attempts < cap)

content_items.status (docelowe, Etap 3–5):
  DRAFT → PENDING_APPROVAL → APPROVED → QUEUED → PUBLISHING
    → PUBLISHED | UNCERTAIN | FAILED
  PENDING_APPROVAL → REJECTED (→ DRAFT po poprawkach)
  UNCERTAIN: wyjście WYŁĄCZNIE przez odczyt stanu lub człowieka — NIGDY auto-retry

jobs.status (Etap 1: storage, worker i eligibility harmonogramu VERIFIED OFFLINE):
  QUEUED → LEASED → RUNNING → DONE | FAILED | NEEDS_VERIFICATION
  LEASED|RUNNING --(lease wygasł)--> QUEUED | FAILED | NEEDS_VERIFICATION

Claim jest legalny wyłącznie dla `status=QUEUED AND earliest_run_at <= now`; `earliest_run_at` jest zapisywany w UTC przez centralną politykę przed enqueue, a `schedule_reason` należy do zamkniętego zestawu kodów. Job oczekujący nie dostaje lease ani zwiększenia `attempts`.
  (LOCAL oraz RESEARCH bez `run_id` i bez `external_effect_started_at` mogą wrócić do QUEUED poniżej capu;
   RESEARCH z `run_id`, BROWSER/publication-like albo job po markerze → NEEDS_VERIFICATION,
   nigdy auto-retry ani auto-resume)

approvals.decision: PENDING → APPROVED | REJECTED (terminal)

SAFE MODE: flaga w system_flags, ortogonalna do statusów; wejście automatyczne
(progi błędów z configu), wyjście WYŁĄCZNIE ręczne; Policy czyta przy każdym checku.
```

---

## 6. Obsługa modeli AI (warstwa providerów)

**Decyzja: zostają wąskie, zadaniowe Protocole (`LLMClient`, `ResearchClient`) + `ModelRouter`.** Nie budujemy generycznego „uniwersalnego klienta LLM" — wąskie kontrakty na zadanie są testowalne (wstrzykiwane callery) i wystarczające. Nowy provider = nowa implementacja Protocolu, zero zmian w workflow.

| Wymóg | Realizacja | Stan |
|---|---|---|
| Anthropic | `AnthropicLLMClient` (tematy), `AnthropicResearchClient` (research, leniwy import SDK) | ZBUDOWANE |
| OpenAI / przyszli providerzy | kolejna implementacja Protocolu; wybór providera per task w `.env` (`PROVIDER_TOPICS=anthropic`); `ModelUsage.provider` już istnieje w schemacie | POZA ZAKRESEM teraz (sekcja 10) — architektura gotowa |
| Routing wg zadania | `ModelRouter.model_for(task)`: fast (topics/note/comment/classify) vs quality (research/article/audit/strategy); nazwy modeli TYLKO z `.env` | ZBUDOWANE (scripts mają go używać zamiast `settings.model_quality` — dług P2-8) |
| Fallback | brak automatycznego fallbacku na inny model — świadomie: fallback = nieprzewidywalny koszt; awaria → FAILED/PARTIAL + stan trwały + jawne wznowienie | DECYZJA |
| Błędy Anthropic | research: typy timeout, SDK-network, 429, 5xx, auth 401, permission 403, invalid 400/422, not-found 404 i unknown; mapowanie wspólne dla A1/A2/B | ZBUDOWANE offline (ADR-029; przed workerami Etapu 1) |
| Retry | tylko timeout, SDK-network, 429 i 500/502/503/504; estymata ×(1+max_retries); re-check przed każdą próbą; 4xx/unknown/parse/truncation/validation/budget NIGDY | ZBUDOWANE (Task 5 + ADR-029) |
| Limit tokenów | `max_tokens` per wywołanie, per etap, z CLI/configu (A1=600, A2=1500, B=3000 od ADR-028) — to REALNY limit kosztu w locie, przekazywany też do estymatora | ZBUDOWANE |
| Structured output | Durable single: dokładnie jeden object/pełny fence, zamknięty schema contract i parse/schema/truncation; staged JSON/JSONL zachowuje własne parsery | ZBUDOWANE / structured-output SDK parameter NIEAKTYWNY bez potwierdzenia model+web-search |
| Walidacja JSON | research: `max_tokens` rozpoznawane przed parse jako typowane truncation, pozostały parse error z `usage`+`raw_text`+`stop_reason`; topics: typowany parse/schema error z `usage`+modelem; koszt zaksięgowany, parse/truncation nigdy nie retry'owane | ZBUDOWANE (research + topics Task 6 + ADR-028) |
| Koszt przy błędzie/przerwaniu | jak wyżej + ryzyko rezydualne timeout-billed-unrecorded (udokumentowane) | ZBUDOWANE (research) |

---

## 7. Bezpieczeństwo i autonomia

### 7.1. Poziomy autonomii (ADR-017: cel = pełna autonomia operacyjna; człowiek zatwierdza POZIOM i GRANICE, nie każdą akcję)

| Poziom | Semantyka | Warunek wejścia |
|---|---|---|
| LEVEL_0 | dry_run, zero akcji zewnętrznych | start |
| LEVEL_1 | wszystko za akceptacją człowieka (approvals) | działająca warstwa publikacji |
| LEVEL_2 | auto-publikacja zatwierdzonych TYPÓW akcji (wybrane Notes, komentarze ≥ progu scoringu); artykuły za akceptacją | ≥1 tydzień stabilnej jakości + jawny przełącznik właściciela |
| LEVEL_3 | pełna autonomia operacyjna; człowiek nadzoruje przez log `autonomous_decisions` i limity | mierzalne kryteria jakości (progi scoringu, wskaźnik interwencji) + jawna zgoda właściciela przy KAŻDYM podniesieniu |

**Stan dziś: efektywnie LEVEL_0** (brak warstwy publikacji; `autonomy_level` w koncie to martwe pole do czasu Etapu 4).

### 7.2. Twarde mechanizmy (deterministyczne, poza modelem)

- **Budżety:** 2,00 USD/dzień, 40,00 USD/miesiąc; miesięczny NADRZĘDNY (ADR-012). Egzekwowane przed każdym płatnym wywołaniem. ZBUDOWANE.
- **Cap pojedynczej akcji:** `--max-cost-usd` jest egzekwowany bibliotecznie przez `PolicyEngine.check_run_budget`; przed etapem obejmuje pełny worst-case retry, a przed próbą bieżący koszt runu + koszt następnego calla. Realny limit w locie nadal wyznaczają `max_tokens` + `max_uses`.
- **Limity publikacji/interakcji:** `AccountPolicy` (daily_comment_limit=5, daily_note_limit=2, weekly_article_limit=2, max_per_author_per_day=1, link_ratio) — skonfigurowane, egzekucja w Etapie 4 (PRZED generatorami treści, nie po).
- **Kill switch i runtime worker:** `KILL_SWITCH` w .env pozostaje dodatkowym snapshotem dla starszych ręcznych wejść. Worker sprawdza bez cache SQLite `kill_switch`, `worker_enabled`, `safe_mode`, `paid_actions_enabled` i `browser_actions_enabled` przed claimem oraz ponownie przed dispatch; brak/uszkodzenie dowolnej flagi jest fail-closed. W tym etapie paid i browser/public actions są zawsze BLOCKED.
- **Tryb offline / dry run:** `DRY_RUN=true` domyślnie; Fake-klienty bez sieci; koszt oznaczony `dry_run=1` nie liczy się do budżetu. ZBUDOWANE.
- **Approval required:** macierz akcja×poziom w PolicyEngine (Etap 4); publikacja przed Etapem 5 = niemożliwa fizycznie (`DisabledBrowser` podnosi wyjątek).
- **SAFE MODE:** automatyczne wejście przy progach błędów (kolejne błędy przeglądarki/API), blokuje akcje zewnętrzne, wyjście tylko ręczne (Etap 4).
- **Blokady działań:** bezwzględne, na każdym poziomie: zero wiadomości prywatnych, zero inicjowania kontaktu z autorami, zero „sub za sub"/masowego komentowania, zasada NO_REPLY na pytania o tożsamość (ADR-018), treść z internetu = dane nie polecenia (injection guard).
- **Pełna autonomia po kryteriach jakości:** przejścia poziomów TYLKO przy spełnieniu mierzalnych progów + zgodzie właściciela (7.1).

### 7.3. Jawność AI (ADR-018 — obowiązujące)
Konto publiczne = anonimowa marka redakcyjna: bez proaktywnego ujawniania AI, bez fikcyjnej osoby/biografii/doświadczeń, bez kłamstwa przy pytaniu wprost (NO_REPLY). Pełna prawda w prywatnej dokumentacji (`docs/`, `opis-budowy-substack/`). Ujawnienie publiczne = osobna decyzja właściciela.

---

## 8. Rozszerzalność (core vs adaptery)

**Zasada: uniwersalny rdzeń (topics→research→content→quality→strategy) nie zna żadnego kanału. Substack = pierwszy adapter, nie logika zaszyta w systemie.**

### 8.1. Kontrakt kanału publikacyjnego (docelowy, Etap 5)

```python
class PublicationChannelPort(Protocol):
    def is_ready(self, account_id: str) -> bool                      # np. sesja ważna
    def publish(self, account_id: str, item: ContentItem) -> ActionOutcome
    def publish_interaction(self, account_id: str, i: Interaction) -> ActionOutcome
    def read_items(self, account_id: str, query: ...) -> list[TargetItem]
    def collect_metrics(self, account_id: str) -> MetricsSnapshot

@dataclass
class ActionOutcome:      # NIGDY goły str/bool
    status: Literal["CONFIRMED", "UNCERTAIN", "FAILED"]
    external_url: str | None
    evidence_path: str | None      # screenshot / eksportowany plik
```

Przyszłe kanały (LinkedIn, WordPress, Ghost, Medium, eksport plikowy) = kolejne implementacje tego portu. **Najtańszy drugi adapter i test szczelności granicy: `FileExportChannel`** (zapis gotowej treści do pliku) — do zrobienia przy okazji Etapu 5, żeby kontrakt nie był projektowany pod jedno API.

### 8.2. Substack adapter (pierwszy, Etap 5) — wiążące decyzje projektowe
Playwright, osobny persistent context per konto w `data/browser-profiles/<account_id>/` (gitignored); pierwsze logowanie RĘCZNE (magic-link) przez człowieka w widocznym oknie; zero zapisu haseł, zero automatyzacji e-maila, zero prywatnych endpointów Substacka; screenshot po każdej akcji publikacyjnej I przy każdym błędzie (do tabeli `screenshots`); stop-conditions: brak sesji → stop+notyfikacja (nigdy auto-login), zmiana UI (brak selektorów) → stop+wpis do ERRORS, ukrycie komentarza → cooldown; jeden Chromium = inwariant (serializacja jobów browser w schedulerze); `max_consecutive_browser_errors` → SAFE MODE.

### 8.3. Pozostałe osie wymiany
- **Model providers** — sekcja 6.
- **Storage adapters** — `StoragePort` (Protocol) z typowanymi metodami; SQLite → ewentualny Postgres to nowy adapter, nie przebudowa.
- **Configurable policies** — wszystkie progi/wagi/limity w `config/*.yaml` + `.env`; zmiana polityki nie dotyka kodu.

---

## 9. Decyzje architektoniczne (skonsolidowane; pełny rejestr: docs/DECISIONS.md)

Obowiązujące ADR-y: 001–024 (statusy PROPOSED dla 001/002/003/005/006 traktować jako ACCEPTED — wdrożone od tygodni; higiena statusów w Etapie 0). Kluczowe decyzje i nowe rozstrzygnięcia tego dokumentu:

| # | Problem | Decyzja (jedna droga) | Odrzucone | Uzasadnienie / konsekwencje |
|---|---|---|---|---|
| D1 | Kształt systemu | Modularny monolit + porty/adaptery, SQLite, jeden worker | mikroserwisy, zewnętrzne kolejki, Postgres teraz | skala 1–3 kont nie uzasadnia kosztów operacyjnych; porty dają drogę migracji bez przebudowy |
| D2 | Kolejka i scheduler | tabela `jobs` w SQLite + pętla workera z lease | APScheduler w pamięci, Celery/Redis | przeżywa restart, audytowalna, `idempotency_key` = anty-dubel publikacji; cron-w-pamięci gubi stan |
| D3 | Wejścia operacyjne | JEDNO wejście (`app/main.py`), skrypty = cienkie aliasy | dwa równoległe wejścia o różnym poziomie bezpieczeństwa | incydent P0-3: cała ochrona żyła w jednym skrypcie, a main.py miał niebezpieczną ścieżkę |
| D4 | Research | staged A1/A2/B (ADR-020); legacy do wygaszenia po sukcesie na żywo | jednoetapowy, dwuetapowy | dwa realne incydenty ucięcia JSON; per-źródło = awaria N nie kasuje 1..N-1 |
| D5 | Dowód w researchu | A2 z realnym fetch treści URL (FetchPort) + `evidence_excerpt` per twierdzenie | „search o URL-u" + samoocena modelu | wiedza modelu nie zastępuje dowodu (P0-2); bez excerptu fact-audit artykułów niewykonalny |
| D6 | Kanon kosztu | `model_usage` jedyny; koszt księgowany też przy błędzie; estymata pesymistyczna (margines ≥50%) ≠ przewidywany koszt | ufanie estymacie z cennika | błąd +163% na pierwszym realnym runie |
| D7 | Bramki jakości | deterministyczne (validate_draft, progi, limity) poza modelem; bramka Policy PRZED każdym generatorem | samoocena modelu jako bramka | model może halucynować i być celem injection |
| D8 | Publikacja | idempotency_key + verify-before-publish + UNCERTAIN bez auto-retry + potwierdzenie odczytem stanu | „kliknij i licz, że się udało"; auto-retry | „timeout w przeglądarce może być opublikowany" — ta sama klasa co zbilowany timeout API |
| D9 | Autonomia | poziomy 0–3, cel LEVEL_3 (ADR-017), przejścia za zgodą właściciela, SAFE MODE | wieczna ręczna akceptacja każdej akcji | cel eksperymentu: czy agent potrafi SAMODZIELNIE prowadzić publikację |
| D10 | Jawność AI | anonimowa marka redakcyjna, NO_REPLY, zero impersonacji (ADR-018) | publiczne ujawnienie AI (pierwotne założenia — SUPERSEDED) | decyzja właściciela; brak ujawnienia ≠ podszywanie się |
| D11 | Prowadzenie dokumentacji | 3 dokumenty źródła prawdy (ten + roadmapa + stan) i JEDNO archiwum; logi (BUILD_LOG, DECISIONS, ERRORS…) i kronika `opis-budowy-substack/` pozostają | wiele równoległych planów/audytów w głównych katalogach | kolejny model nie może zgadywać, który dokument obowiązuje |
| D12 | Fallback modeli | brak auto-fallbacku; awaria → trwały stan + jawne wznowienie | automatyczna zmiana modelu | nieprzewidywalny koszt/jakość; wznowienia są tanie dzięki trwałym etapom |
| D13 | Osierocony `RUNNING` | po recovery jobów jawny stale reaper CAS `RUNNING→STOPPED`; job `QUEUED/LEASED/RUNNING` blokuje stop | auto-resume, zatrzymanie mimo aktywnej kolejki, cykliczna pętla bez decyzji | zatrzymuje tylko audit bez tworzenia `QUEUED+STOPPED`; RESEARCH z runem zostaje NEEDS_VERIFICATION (ADR-040) |

---

### 9.1. Aktualizacja wykonawcza Etapu 1 — final restart acceptance (2026-07-14)

Wcześniejsze liczby 26/42/53 acceptance oraz 667/683/695 testów są historyczne. ADR-044 atomizuje `initialize_research_run_for_job`, ADR-045 zamyka old-owner research fencing, ADR-046 wymaga czasu po `BEGIN IMMEDIATE`, ADR-047 przenosi sukces joba do transakcji workflow, a ADR-048 domyka runtime kontrakt `DispatchResult`. `finalize_job_research_execution` zapisuje w jednej fenced transakcji kartę i źródła, `research_runs=COMPLETE`, terminalny run, topic `USED`, `jobs=DONE`, timestampy, kanoniczny koszt i wyczyszczony lease. `DispatchResult` nie ma domyślnego ownera terminalizacji, waliduje `TerminalizationMode` przy konstrukcji, a Worker waliduje go ponownie przed jakimkolwiek końcowym zapisem. System scheduler/service, paid/live oraz browser/public nie są tym odblokowane. `0010`–`0012` są teraz ledgerem provider request ID; outbox i operator reconciliation nadal nie są wdrożone.

## 10. Rzeczy, których OBECNIE NIE ROBIMY (nie rozbudowywać bez decyzji właściciela)

1. **Postgres, Docker, mikroserwisy, zewnętrzne kolejki (Redis/Celery), vector store** — SQLite+WAL i monolit wystarczą daleko poza obecną skalę (Docker dopiero w Etapie 8).
2. **Providerzy inni niż Anthropic** (OpenAI itd.) — architektura gotowa (sekcja 6), implementacja poza zakresem.
3. **Kanały inne niż Substack** (LinkedIn/WordPress/Ghost/Medium) — tylko kontrakt portu (8.1); żadnych adapterów teraz.
4. **Generatory treści (artykuły/Notes/komentarze) przed bramkami Policy** — kolejność: bramka → generator (Etap 3–4).
5. **Publikacja czegokolwiek na Substacku** — do Etapu 5 i jawnej zgody właściciela; `DisabledBrowser` blokuje fizycznie.
6. **Usuwanie legacy pipeline'ów researchu i konsolidacja trzech tabel źródeł** — dopiero po pierwszym sukcesie staged na żywo (deprecation → osobna decyzja).
7. **Prompt caching** — po potwierdzeniu architektury researchu na żywo (P2-12).
8. **Przepisywanie `StoragePort` pod generyczną specyfikację ze starego planu** — kod (typowane metody) jest lepszy; obowiązuje kod.
9. **Publiczne repozytorium / ujawnienie eksperymentu** — repo PRIVATE (ADR-021); ujawnienie = osobna decyzja właściciela.
10. **Web UI ponad panel localhost FastAPI** — żaden hosting publiczny w MVP.
11. **Multi-konto w praktyce** — architektura wielokontowa jest i zostaje testowana, ale aktywne jest wyłącznie `nothing_is_accidental` (ADR-007).
12. **Samodzielne zmiany polityk bezpieczeństwa przez strategy engine** — strategia koryguje parametry treści, nigdy limity/blokady.

---

## 11. WAVE 0A — inwariant pojedynczego realnego żądania (2026-07-14)

Status: **WAVE 0A/0B/1A formalnie `CLOSED — APPROVED WITH P2`; pierwsza LA-01 = `REJECTED — MAJOR`; LA-01-R1 i LA-02 = `APPROVED WITH MINOR/P2 — CHECKPOINTED`; LA-03 = `APPROVE WITH MINOR/P2`; pierwszy pakiet P2 = `REJECTED — MAJOR`; naprawa NIA-P2-RV-01…05 = `APPROVE WITH MINOR/P2`; Etap 1 = `CLOSED` (formalna decyzja właściciela 2026-07-17, ADR-088).** Migracja produkcji `0009→0014`, inicjalizacja flag oraz review LA-01-R1, LA-02, LA-03 i re-review naprawy są wykonane. Jeden autoryzowany provider request został rozliczony, ale nie utworzył Research Card (co nie było bramką zamknięcia); jego job jest terminalny i nie może być retry'owany. Kolejny live wymaga nowej, oddzielnej autoryzacji i nowego joba. Realny adapter Anthropic może działać wyłącznie po nowej zgodzie i pełnym pre-flight. Live API pozostaje zabronione bez takiej zgody.

`app.main run-topics` i `app.main run-research` są bezwarunkowo offline/fake. Worker pozostaje offline dla wszystkich zwykłych payloadów; jedyny kandydacki wyjątek WAVE 0B to wcześniej zapisany `durable_provider_v2` single job z lease/fence i runtime `paid_actions_enabled`. `durable_provider_v1` jest historyczny i fail-closed. `DRY_RUN=false` ani obecność klucza same w sobie nie aktywują providera. Brak `--real` w capped entrypoint kończy się estymatą/offline bez klienta API; świeże `--real` wyłącznie enqueuje durable job. Przed konstrukcją realnego klienta wymagane są wszystkie komponenty cennika (`input`, `output`, `cache read`, `cache write`, `web search`), każdy dodatni i skończony; brak, zero, wartość ujemna, `NaN` i `inf` blokują wykonanie. Dry-run może działać bez cen. Estymata tematów używa tego samego limitu outputu co request (1500). Live API jest obecnie ZABRONIONE.

Historyczna weryfikacja WAVE 0A miała 714 testów, WAVE 0B.3 — 770, W0B-RR-01 — 894, zaakceptowany baseline WAVE 1A — 1036, skonsolidowany pakiet — 1052, QP-01 — 1079, LA-01-R1 — 1151, LA-02 — 1174, LA-03 — 1181, a odrzucony pierwszy pakiet P2 — 1200. Bieżąca regresja naprawy to **1235 passed / collected** z exact-once `294+299+311+331`. Produkcyjna baza po autoryzowanym jednym requestcie ma SHA-256 `5BEA9E26597E6A628EF875A7F5115465E94CB600B38213A67794EE94232C6D10` i schema 0014. WAVE 0B i WAVE 1A są `CLOSED — APPROVED WITH P2`, pierwsza LA-01 jest `REJECTED — MAJOR`, LA-01-R1 i LA-02 są `APPROVED WITH MINOR/P2 — CHECKPOINTED`, LA-03 ma `APPROVE WITH MINOR/P2`, pierwszy pakiet P2 jest odrzucony, a jego naprawa NIA-P2-RV-01…05 przeszła niezależny re-review z wynikiem `APPROVE WITH MINOR/P2`. Etap 1 = `CLOSED` (formalna decyzja właściciela 2026-07-17, ADR-088); kolejny live request jest zabroniony bez nowej, oddzielnej decyzji właściciela i nowego joba.

## WAVE 0B: granica durable provider attempt

Stan historyczny WAVE 0B, zastąpiony przez WAVE 0B.2. Architektura płatnego single flow ma sekwencję durable fresh job → claim/lease/fence → `provider_attempts` `RESERVED` z deterministycznym request_id → `REQUEST_STARTED` tuż przed SDK → jedno rozliczenie usage albo `NEEDS_RECONCILIATION`. Rezerwacja jest obliczana w `BEGIN IMMEDIATE`; po `REQUEST_STARTED` expiry i unknown result nie dają auto-retry. Realne staged flows oraz resume pozostają poza zakresem, a live API nadal NOT VERIFIED.

### WAVE 0B.2 — historyczna aktualizacja architektury provider ledger (2026-07-14)

**Wynik historyczny, zastąpiony przez WAVE 0B.3.** `DurableProviderAttemptContext(job_id, run_id, stage, attempt_no, request_id, lease_owner, fence_token)` jest nieopcjonalną granicą każdego produkcyjnego callera Anthropic; callback storage atomowo oznacza i potwierdza dokładnie ten `REQUEST_STARTED` przed SDK. Fake/dry-run używa jawnego adaptera offline.

`0012_provider_ledger_hardening` najpierw waliduje stary request_id i relacje usage, a dopiero potem przebudowuje tabele. Dla runtime SQLite wymusza `model_usage.request_id → provider_attempts → jobs.run_id = model_usage.run_id`, dopuszczając tylko `REQUEST_STARTED`/`SETTLED`. Udowodnione historyczne usage zachowuje non-legacy; jedynie brak dawnego request_id dostaje immutable dowód legacy. Kolejna próba po aktywnym lub `NEEDS_RECONCILIATION` jest zablokowana w `BEGIN IMMEDIATE` do przyszłego jawnego resolvera.

Durable payload jest schema-aware snapshotem account/topic/workflow/mode/capu, provider/modelu, tokenów, timeoutu, pełnego cennika+fingerprintu, wersji pipeline/promptu, limitu requestów i flag. Canonical money ma sześć miejsc i `ROUND_HALF_UP`; tokeny są integerami. Worker nie odczytuje późniejszej konfiguracji wykonawczej z ENV. Durable real A1/A2/B, real resume i operator reconciliation pozostają poza zakresem WAVE 0B.2.

### WAVE 0B.3 — historyczna identity i czas autorytatywny przy granicy SDK (2026-07-14)

**Stan historyczny, zastąpiony przez końcową falę WAVE 0B.** Bramka klienta wylicza `request_id` wyłącznie jako `job_id:stage:attempt_no`; context, potwierdzony attempt i nagłówek idempotency muszą być literalnie równe tej wartości. `stage` nie dopuszcza separatora, `attempt_no` jest dodatni, a wartości identity nie są normalizowane.

`checked_at` jest tylko diagnostycznym timestampem budowy contextu. `assert_durable_provider_attempt_active()` rozpoczyna krótką transakcję i pobiera bieżący czas z wstrzykniętego execution clock tuż przed SDK, sprawdzając job→run→owner→lease→attempt. Dzięki temu odrzuca wygasły lease, takeover, zmianę run/fence i attempt po `NEEDS_RECONCILIATION`, a respektuje odnowienie lease. WAVE 1A, reconciliation i wszystkie działania zewnętrzne pozostają poza zakresem.

### WAVE 0B — końcowa fala snapshotu requestu i pełnej asercji lifecycle (2026-07-15)

**Stan historyczny przed checkpointem WAVE 0B: `WAVE 0B APPROVED WITH P2 — READY FOR CHECKPOINT`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.** Niezależny końcowy review potwierdził brak findingów MAJOR i CRITICAL; na tym historycznym etapie WAVE nie była `CLOSED` przed commitem checkpointu. Jedynym wspieranym kontraktem był `durable_provider_v2` z `durable_research_intent_v2`; był to jeden aktywny durable paid-execution flow. v1 oraz każdy niepełny/stary payload były fail-closed. Nie dodano wtedy migracji: zmiana była wersjonowaniem trwałego JSON payloadu, a `0013` pozostawała ostatnią migracją SQLite. Ten stan został zastąpiony przez `WAVE 0B = CLOSED — APPROVED WITH P2`, bieżącą czternastą migrację `0014` oraz późniejsze `WAVE 1A = CLOSED — APPROVED WITH P2`.

Źródłem semantyki requestu jest kanoniczny snapshot danych wejściowych promptu (question, niche, required_depth, guidance), stage, identity account/topic, provider/model, limitów tokenów/web search/timeout, cennika i jego fingerprintu, capu, workflow/mode, retry, flag oraz wersji promptu/pipeline. Worker buduje `ResearchPlan` wyłącznie z tego snapshotu; bieżące dane topic/account są jedynie finalnym guardem zgodności i nie stają się drugim źródłem requestu.

Bezpośrednio przed callerem finalna transakcja sprawdza nie tylko lease i attempt, lecz pełną relację `job → run → research_run → provider_attempt → execution_intent`: tożsamość, workflow/account/topic, `RUNNING` + brak `finished_at`/error, `single:PENDING` + brak terminalnych timestampów/card/cost/error, `REQUEST_STARTED` bez settlementu oraz ponownie wyliczony fingerprint payloadu. Każda rozbieżność blokuje caller, usage, koszt, settlement i attempt #2; started attempt zostaje jednoznacznie zatrzymany do reconciliation.

### W0B-REV-06 — jeden limit requestu, jedna rezerwacja (2026-07-15)

`max_tokens` jest trwałym dodatnim polem execution intentu i częścią jego fingerprintu. W paid single flow dispatcher przekazuje literalnie `intent.max_tokens` do `AnthropicResearchClient` oraz do pipeline. Pipeline używa tej samej wartości dla pesymistycznej estymaty, `PolicyEngine.check_run_budget` i `begin_provider_attempt(max_cost_usd=...)`; nie ma osobnej stałej 3000 na tej ścieżce.

Kwoty rezerwacji i usage są canonicalizowane do sześciu miejsc USD z `ROUND_HALF_UP`. `actual_cost <= reserved_amount` oznacza zwykłe `SETTLED`. `actual_cost > reserved_amount` jest wynikiem fail-closed: transakcja utrwala jeden wiersz `model_usage`, odświeża kanoniczny koszt runu i zmienia attempt `REQUEST_STARTED → NEEDS_RECONCILIATION` z kodem `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION`; `actual_cost_usd` attemptu pozostaje `NULL` zgodnie z jego stanowym CHECK, a rzeczywisty koszt jest w ledgerze usage. Nie powstaje karta, SUCCESS ani attempt #2. WAVE 0B ma status `APPROVED WITH P2 — READY FOR CHECKPOINT`, lecz nie jest `CLOSED` przed commitem; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

Weryfikacja **historyczna po W0B-REV-06**: 873 collected/passed, partycje 206+218+226+223. Weryfikacja po W0B-REV-09/10 jest także historyczna: 887 collected/passed, partycje 211+222+229+225. `app.core.money` ustanawia dla estymaty, usage, rezerwacji, porównań i cache kontrakt `Decimal(str(value)) → quantize(0.000001, ROUND_HALF_UP)`; componenty są sumowane przed pojedynczą granicą kontraktu. Runner testów używa pełnego SHA-256 UTF-8 node ID jako big-endian integer modulo liczby partycji oraz sprawdza exact-once coverage i brak BOM.

### W0B-RR-01 — pełny kontrakt Decimal do granicy publicznej (2026-07-15)

Po niezależnym re-review staged estimate nie zaokrągla już jednego źródła przed mnożeniem: raw komponenty pozostają `Decimal` aż do jednego końcowego `quantize(Decimal("0.000001"), ROUND_HALF_UP)`. Ta sama canonicalizacja poprzedza policy projection, sumy persisted usage/rezerwacji, odświeżenie kosztu pipeline oraz porównanie/rendering CLI; zgodność float jest wyłącznie granicą starego API. Nie zmieniono durable lifecycle, request identity, `max_tokens`, attemptów, schematu ani migracji. Dwa nieosiągalne konstruktory klienta w prywatnych ścieżkach resume usunięto; dispatcher pozostał jedynym rootem realnego klienta. Historyczna regresja końcowej iteracji WAVE 0B miała **894 passed / collected**, partycje 213+224+231+226; WAVE 0B miała wtedy status `APPROVED WITH P2 — READY FOR CHECKPOINT` (nie `CLOSED` przed commitem), Etap 1 `BLOCKED`, live API `ZABRONIONE`.
