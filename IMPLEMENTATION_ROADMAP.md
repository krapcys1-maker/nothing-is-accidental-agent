# IMPLEMENTATION_ROADMAP — Nothing Is Accidental Agent

> **STATUS: JEDYNA OBOWIĄZUJĄCA KOLEJNOŚĆ DALSZYCH PRAC.**
> Data: 2026-07-13 · Architektura docelowa: `MASTER_ARCHITECTURE.md` · Stan bieżący: `CURRENT_PROJECT_STATE.md`.
> Zastępuje plany etapów z `docs/IMPLEMENTATION_PLAN.md` (§B.11, CZĘŚCI D–F) i plan napraw z audytu 12.07 — oba w `docs/archive/superseded_plans/`.
>
> **ETAP 0 ZAKOŃCZONY. ETAP 1 = `CLOSED` (formalna decyzja właściciela 2026-07-17; podstawa: niezależny re-review NIA-P2-RV-01…05 = `APPROVE WITH MINOR/P2`).** **WAVE 0A/0B/1A = `CLOSED — APPROVED WITH P2`; pierwsza WAVE LA-01 = `REJECTED — MAJOR`; LA-01-R1 i LA-02 = `APPROVED WITH MINOR/P2 — CHECKPOINTED`; LA-03 = `APPROVE WITH MINOR/P2`; pierwszy pakiet P2 = `REJECTED — MAJOR`; naprawa NIA-P2-RV-01…05 = `APPROVE WITH MINOR/P2`.** Kod zna 14 migracji i ma **1235/1235 testów offline**, exact-once `294+299+311+331`. False blockers `PROCESSES_PRESENT` i `DB_HANDLES_PRESENT` są zamknięte bez wyłączania probe'ów. Jedna autoryzowana komenda wykonała dokładnie jeden request: attempt #1 `SETTLED`, `REQUEST_STARTED` obecny, usage `0.053182 USD`, zero retry/attemptu #2. HTTP 200 zakończył się typowanym `ResearchParseError`; job/run/research_run są terminalnie `FAILED`, bez Research Card — brak Research Card NIE blokuje zamknięcia Etapu 1. Gate `False`, marker brak, flagi fail-closed. Zamknięcie Etapu 1 nie autoryzuje kolejnego live: nowy realny request wymaga oddzielnej, jawnej decyzji właściciela i nowego joba; terminalnego joba nie wolno retry'ować; Etap 2 nierozpoczęty. Dwa MINOR/P2 parsera (`RV-R2-P2-1`, `RV-R2-P2-2`) są nieblokujące i trafiają do backlogu Etapu 2.

> **Controlled-live 2026-07-17:** pierwszy attempt pre-provider ujawnił `PROCESSES_PRESENT` (LA-02), kolejny autoryzowany przebieg ujawnił self-handle `DB_HANDLES_PRESENT` i został naprawiony przez LA-03. Po 1181 testach, fake CLI i produkcyjnym standalone PASS wykonano dokładnie jeden realny provider request. Nie wolno go ponowić: request ma trwałe `REQUEST_STARTED`, usage i settlement. Review pierwszego pakietu P2 wydał `REJECT — MAJOR`; zamknięta naprawa NIA-P2-RV-01…05 (1235 testów) przeszła niezależny re-review z wynikiem `APPROVE WITH MINOR/P2`, na podstawie którego właściciel formalnie zamknął Etap 1 (ADR-088). Bieżący job wyczerpał `max_attempts=1` i jest terminalnie `FAILED`; kolejny operation/job wymaga wyłącznie nowej jawnej autoryzacji właściciela.

## Formalne zamknięcie Etapu 1 — 2026-07-17

- **Decyzja:** właściciel formalnie ustawił **Etap 1 = `CLOSED`**. Podstawa: niezależny re-review NIA-P2-RV-01…05 = **`APPROVE WITH MINOR/P2`** (zero CRITICAL, zero MAJOR, pięć findings technicznie zamknięte). Formalny zapis: `docs/DECISIONS.md` ADR-088.
- **Dowód:** 1235/1235, exact-once `294+299+311+331` (`1235` node ID), 28-case parser matrix, durable score/usage/settlement, pięć klas sekretów, cztery failpointy diagnostyki, jawny clock i historia raportów; fake/temp DB, zero sieci/API/provider requestu/browsera/publikacji/kosztu; produkcyjna DB byte-identical.
- **Backlog Etapu 2 (nieblokujące, nie naprawiane teraz):** `RV-R2-P2-1` (prose od `N`/`I` → etykieta `json_syntax` zamiast `prose_outside_json`), `RV-R2-P2-2` (trailing comma → `incomplete_json` zamiast `json_syntax`). Obie pozostają fail-closed; nie otwierają nowej fali.
- **Granica:** zamknięcie nie autoryzuje kolejnego live. Nowy realny request wymaga oddzielnej, jawnej decyzji właściciela i nowego joba; brak Research Card z ostatniego controlled-live nie był bramką zamknięcia.

## Pakiet P2 po LA-03 — zamknięty i zatwierdzony (historia naprawy)

- **Forensics:** trwałe dane wskazują `json_syntax` w line 29/column 6/char 4376, ale historyczny durable single nie zachował raw ani stop reason; konkretniejsza przyczyna pozostaje `INSUFFICIENT DURABLE EVIDENCE`, nie hipoteza.
- **Parser:** jedna odpowiedź, jeden object lub kompletny fence, ścisłe pola/typy/ranges, osobne parse/schema/truncation, prywatna diagnostyka raw/stop reason; bez repair, retry i attemptu #2.
- **Raporty:** append-preserving per invocation, stabilny session plus attempt/timestamp/nonce; recovery wskazuje poprzedni report key; atomowy replace/fsync i report-before-marker-clear bez zmian.
- **Quiescence:** `run_controlled_live_once` wymaga jawnego frozen pre-storage payloadu; żaden composition root nie ma hidden default probe po otwarciu storage.
- **Dowód naprawy po review:** 1235/1235, exact-once `294+299+311+331`, 28-case parser matrix, durable score/usage/settlement, pięć klas sekretów, cztery failpointy diagnostyki, jawny clock i historia raportów; fake/temp DB, zero provider requestu i kosztu.
- **Status:** niezależny re-review wydał `APPROVE WITH MINOR/P2`; naprawa jest podstawą formalnego zamknięcia Etapu 1 (wyżej).

## WAVE LA-03 — pre-storage quiescence i pierwszy request (APPROVE WITH MINOR/P2)

- **Naprawa:** canonical DB/WAL/SHM handle probe przed głównym `SqliteStorage.open`; zamrożony wynik używany po open; trwała rewalidacja DB/schema/job/pricing/intent/flags przed markerem; marker O_EXCL i drugi durable recheck przed flagami/claimem/providerem.
- **Ochrony zachowane:** foreign read-only/writable SQLite, WAL i SHM nadal STOP; drift między fazami STOP; drugi wrapper STOP; `max_attempts=1`, `max_retries=0`, request/fence/ledger/usage/settlement/budget/reconciliation bez zmian.
- **Dowód offline:** 1181/1181, exact-once cover 1181, dedicated full fake subprocess i standalone temp PASS.
- **Wynik live:** exactly one request/attempt/`REQUEST_STARTED`; jedno usage i `SETTLED` za `0.053182 USD`; HTTP 200, potem `ResearchParseError`; job/run/research_run `FAILED`, brak Research Card; flags/gate fail-closed, marker absent, zero retry.
- **Status:** niezależny review wydał `APPROVE WITH MINOR/P2`; cel pierwszego provider requestu wykonany. (Stan na moment LA-03, zastąpiony przez ADR-088: formalne zamknięcie Etapu 1 wymagało wtedy review pakietu P2 i decyzji właściciela — oba nastąpiły, Etap 1 = `CLOSED` 2026-07-17, a pozytywny durable flow/Research Card NIE był bramką zamknięcia.) Kolejny request jest zabroniony bez nowej zgody.

## WAVE LA-02 — lokalna naprawa observer effect i diagnostics (zatwierdzona)

- **Wykonane offline:** ancestry launchera oparte na rzeczywistym PID/PPID, pełnej identity, zgodnym entrypoincie i creation order; PowerShell/pwsh/cmd/bash bez wyjątków opartych wyłącznie na nazwie; blokady drugiego entranta, workera, maintenance, schedulera, holdera, tasku, PID reuse i niespójnej identity pozostają.
- **Diagnostyka:** zewnętrzny `PREFLIGHT_FAILED` nie usuwa inner `PROCESSES_PRESENT`; raport obejmuje invariant/check order, blocking PIDs, redacted command line, classification, reason codes, ancestry i fingerprint. Standalone `controlled-live-quiescence-check` używa canonical probe'a bez DB open/storage/provider/markera/gate'u.
- **Dowód:** 1174/1174 offline, exact-once `284+284+298+308`; 21 testów LA-02 plus nowa regresja fake controlled-live ancestry i wcześniejsze LA-01-R1/QP-01; temp DB/fake callery, zero sieci/API/SDK/browsera/publikacji/kosztu.
- **Status:** `APPROVED WITH MINOR/P2 — CHECKPOINTED`. Root cause `PROCESSES_PRESENT` jest `CLOSED`; P2-2 false STOP pozostaje `OPEN OBSERVATION / DOCUMENTED` i nie blokuje checkpointu. Produkcja schema 0014 i post-enqueue SHA `5FF5DBA3FA57A2DFBB8B638DD7E6CC9E84825A96C6080AA17F8A05B188D97B78` są niezmienione; job `QUEUED/attempts=0`; gate `False`; druga próba niedozwolona.

Oznaczenia P0-x/P1-x/P2-x pochodzą z audytu 2026-07-12 (zarchiwizowany; findingi przeniesione tutaj i do `CURRENT_PROJECT_STATE.md`). ✅ = już wykonane (nie jest zadaniem).

---

## Formalne zamknięcie WAVE 1A — 2026-07-16

Skonsolidowany pakiet Etapu 1, QP-01 oraz trwały stan po produkcyjnej migracji przeszły niezależny review z wynikiem **`APPROVE WITH MINOR/P2`**. WAVE 0A, 0B i 1A pozostają formalnie `CLOSED — APPROVED WITH P2` i nie są ponownie otwierane. Produkcyjna baza jest zweryfikowana jako schema `0014`, a nowy baseline jako `VERIFIED`. Pierwsza LA-01 została później odrzucona jako `REJECTED — MAJOR`; naprawa LA-01-R1 przeszła osobny review z wynikiem `APPROVE WITH MINOR/P2` i może zostać checkpointowana z jednym nieblokującym P2 sanitizera. Minimalny Windows Task Scheduler launcher, typowany cap attempts i read-only raport są wdrożone; zadań systemowych nie zarejestrowano. (Stan historyczny na 2026-07-16: Etap 1 pozostawał wtedy `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`, live API `ZABRONIONE`. Etap 1 został formalnie zamknięty 2026-07-17 — patrz nagłówek roadmapy i ADR-088; live API nadal wymaga oddzielnej zgody.) Etap 2 nie został rozpoczęty.

## Historia implementacji — WAVE 1A (2026-07-15–2026-07-16)

WAVE 0B jest formalnie `CLOSED — APPROVED WITH P2`. WAVE 1A wdraża ręczny resolver L1 jako warunek dalszego rozważania durable-real execution, lecz sama nie odblokowuje żadnej akcji płatnej: status to `CANDIDATE — AWAITING INDEPENDENT REVIEW` (po naprawie odrzucenia `REJECTED — MAJOR`); Etap 1 pozostaje `BLOCKED`, live API `ZABRONIONE`. Migracja `0014_provider_attempt_reconciliation` została poprawiona **in place** (bez 0015). Resolver oddziela decyzję finansową od wykonawczej, używa wyłącznie `model_usage` dla znanego kosztu (akceptowanego po pełnej weryfikacji tożsamości, nie po samym koszcie), zapisuje historię operatora w **append-only** `reconciliation_events`, a `MANUAL_REVIEW_REMAINS_REQUIRED` jest dozwolone tylko z `CHARGE_UNKNOWN` (obserwacja) — więc żaden terminalny attempt nie zostaje z jobem w `NEEDS_VERIFICATION`. `RESULT_ALREADY_FINALIZED` wymaga wyłącznej Research Card; spójność `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd` jest niezmienna; brak retry/attemptu #2/provider calla. Dowód offline: **980 testów**, 14 migracji, coverage partycji exact-once oraz brak zmiany chronionej bazy. (Historyczne 919/894/948/955 to wcześniejsze iteracje.) Poprawka `W1A-VERIFY-01` (ADR-064): `EXECUTION_FAILED` akceptuje reaper-`STOPPED` run i atomowo `STOPPED → FAILED`, bez wskrzeszenia/`DONE`/attemptu #2; flaky node 30/30, plik 10/10. Poprawka `W1A-VERIFY-02` (ADR-065): pełna walidacja lineage przed mutacją (aplikacja + version token v2 + trigger SQLite 0014); foreign `runs.account_id`/`workflow=ANALYTICS` był fail-open nieobjęty 955/955 — teraz każda niespójność account/workflow/topic/flow/kind/intent = fail-closed bez mutacji; +25 testów lineage, disproof 10/10.

**Domknięcie kandydackie `W1A-R4-01` (ADR-067, po czwartym niezależnym `REJECTED — MAJOR`):** przed każdą terminalizacją przypiętego researchu wspólna operacja StoragePort atomowo sprawdza provider attempt. Bez attemptu zachowuje `FAILED`; `RESERVED`/`REQUEST_STARTED` eskaluje do `NEEDS_RECONCILIATION` z append-only audytem i `job=NEEDS_VERIFICATION`; istniejące reconciliation pozostaje idempotentne. Rezerwacja jest zachowana do operatora, bez retry/attemptu #2/providera. Worker fallback, kontrolowana niepewność i heartbeat używają tej samej granicy. Triggery 0014 blokują terminalne job/run/research_run przy `RESERVED`/`REQUEST_STARTED`. P2-1 pozostaje fail-closed; P2-2 nie jest nadmiernie deklarowane: StoragePort gwarantuje jedną transakcję resolvera, SQLite wymusza spójny trwały koniec, lecz nie dowodzi pochodzenia wobec uprzywilejowanego autora wielu tabel. Dowód implementera: 1036/1036, partycje 248+253+267+268, concurrency 38×30, krytyczne pliki 10×, QA 10×. **Status przekazany przez implementera:** `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; późniejsze niezależne zatwierdzenie i formalne zamknięcie właściciela opisuje ADR-068. Etap 1 nadal `BLOCKED`; live API nadal `ZABRONIONE`.

## Etap 0 — Stabilizacja obecnego projektu (ZAKOŃCZONY 2026-07-13)

- **Cel — OSIĄGNIĘTY:** domknięto znane wady wykonawcze researchu i uzyskano pierwszą kompletną, realną Research Card z terminalnym `SUCCESS`.
- **Uzasadnienie:** wcześniejsze realne próby kończyły się bez kompletnej karty. Kontrolowany staged run `c01171bc` zachował A1/A2 po pierwszym błędzie B, a następnie za osobną zgodą wznowił wyłącznie B i spełnił kryterium etapu bez powtarzania opłaconych etapów.
- **Zależności:** brak.
- **Już wykonane w tym etapie ✅:** testy 102/102 zielone; naprawy P0-1 (SUCCESS), P0-2a/b (wymuszone UNVERIFIED + `min_verified_sources`), P0-3 (blokada `run-research --real`) — z testami regresyjnymi; diagnostyka raw+stop_reason; default A2=1500; konsolidacja dokumentacji (ten zestaw dokumentów).
- **Pliki/moduły:** `app/storage/migrations/`, `app/storage/repositories.py`, `app/models.py`, `app/workflows/research/pipeline.py`, `app/orchestrator/runner.py`, `app/policies/policy_engine.py`, `app/research/cost_estimator.py`, `app/storage/db.py`, `scripts/run_capped_research.py`, testy.

### Zadania (w tej kolejności)

1. ✅ **[P1-1/P1-9] Migracja `0006_research_run_flow.sql` — WYKONANE 2026-07-12:** kolumna `research_runs.flow` ('single'|'two_stage'|'staged') NOT NULL bez defaultu + deterministyczny backfill; wszystkie istniejące funkcje resume walidują flow, a CLI także dozwolony status przed jakąkolwiek pracą; `_detect_flow` usunięte z CLI; 127 testów zielonych.
2. ✅ **[P1-2 + P1-8] Spójność księgi runów — WYKONANE 2026-07-12:** researchowy INSERT `model_usage`, kanoniczna suma i absolutny UPDATE `runs.cost_usd` są jedną transakcją; idempotentny helper pozostaje dla no-call/resume. A1/A2/B synchronizują cache przy każdym wyjściu bez zmiany statusu. `connect()` ustawia najpierw `busy_timeout=5000`, potem potwierdzone `journal_mode=WAL` dla bazy plikowej; 139 testów zielonych.
3. ✅ **[P1-5] Migracja `0007_candidate_attempts.sql` — WYKONANE 2026-07-12, poprawione po review:** `attempts` = liczba atomowo zarezerwowanych A2; historyczne `EXTRACTED`/`EXTRACTION_FAILED` dostają konserwatywną dolną granicę 1, a `PENDING` 0. Claim wymaga `attempts < cap` i prowadzi przez `EXTRACTION_IN_PROGRESS`, który po awarii blokuje zwykłe resume. Jawne `retry-failed-candidates` resetuje wyłącznie eligible failed, jest izolowane kontem i może odblokować `PARTIAL_EXHAUSTED` do `PARTIAL` po podniesieniu capu; brak API i kosztu. Migracja 0007 oraz ledger są jedną transakcją runnera. Domyślny cap=2 oznacza pierwszą próbę + jedno ręczne retry; `PARTIAL_EXHAUSTED` pozostaje terminalny dla zwykłego resume. 164 testy zielone.
4. ✅ **[P1-6] Cykl życia tematu — WYKONANE 2026-07-12, poprawione po trzech review:** legacy `finalize_research_success` weryfikuje run–topic–card–account i w jednej transakcji ustawia COMPLETE, jawnie oczekiwany terminalny `runs.status` oraz `topics.status=USED` dla `single`/`two_stage`; identyczne powtórzenie jest no-op bez UPDATE, a inna karta, koszt, status lub uszkodzony COMPLETE są odrzucane bez mutacji. Flow `staged` finalizuje wyłącznie `finalize_staged_research_with_card`; nie może przejść przez publiczny legacy finalizer ani jego alias. Świeży research z poprawną kompletną kartą jest blokowany przed klientem, a USED/COMPLETE bez poprawnej relacji zatrzymuje się fail-closed, także z force. Tylko jawne `--force-re-research` omija poprawną blokadę re-researchu; `--resume` nie przyjmuje tej flagi. Pełna macierz obejmuje SELECTED+COMPLETE, historię FAILED/PARTIAL/COMPLETE, force wobec korupcji, account mismatch z czterema licznikami, błędy wymuszonych runów oraz negatywne flow↔Stage B i karty obcego topicu/konta; **212 testów zielonych**. Dokładne porównanie kosztu float pozostaje fail-closed P2-18.
5. ✅ **[P1-3 + P1-4] Budżet szczelny — WYKONANE 2026-07-12, poprawione po pełnym review:** estymata ×(1+max_retries), re-check z `model_usage` przed każdą próbą, obowiązkowy cap dla realnego pipeline, absolutny cap resume, walidacja run–account przed usage, centralny `PolicyEngine.check_run_budget` z fail-closed dla niepoprawnego stanu oraz jawne `timeout-billed-unrecorded`; 257 testów offline.
6. ✅ **[nowe, z tego audytu] Wyrównanie klienta tematów — WYKONANE 2026-07-12:** `AnthropicLLMClient` buduje `Usage` przed parsowaniem, zachowuje usage/model w typowanych błędach parse/schema, rozróżnia błąd providera bez odpowiedzi, zdejmuje dokładnie jeden kompletny zewnętrzny code fence, a workflow księguje dostępny koszt raz i kończy run `FAILED` bez częściowych topics; **286 testów offline**, zero API i 0 USD.
7. ✅ **[P2-9] Higiena rejestru decyzji — WYKONANE 2026-07-12:** ADR-001/002/003/005/006 zweryfikowane względem architektury, roadmapy, bieżącego stanu i wdrożenia, następnie oznaczone `ACCEPTED`. Historyczne mapowanie publikacji w ADR-005 doprecyzowano do aktualnego Etapu 5 bez zmiany meritum; brak sprzeczności, zero zmian kodu, 286 testów offline i 0 USD.
8. ✅ **Walidacja przejść stanów — WYKONANE 2026-07-13, poprawione po review:** pełna inwentaryzacja objęła `runs`, `research_runs`, `topics` i `research_source_candidates`; `research_sources` nie mają lifecycle statusu, a przyszłe `content_items`/`approvals`/`interactions` nie mają używanych helperów. Każdy istniejący statusowy UPDATE ma warunek `status IN (...)` (oraz `flow`, gdy wymagany), kontrolę `rowcount`, atomowy rollback i typowany `LifecycleTransitionError` albo zachowany `ResearchTopicIntegrityError`. `finish_run` nie przepisuje FAILED; wyłącznie jawny research resume używa osobnego helpera z pełną walidacją relacji i CAS. Race terminalizacji, resume i candidate claim są rzeczywiście równoległe na osobnych połączeniach SQLite z `Barrier`; **337 testów offline**, zero API i 0 USD.
9. ✅ **Realny run researchu — WYKONANE 2026-07-13:** świeży staged run ADR-022 wykonał A1 i 4×A2, a pierwsze B zakończyło się `stop_reason=max_tokens`, zachowując `SOURCES_COMPLETE`. Po osobnym, zatwierdzonym repair auditu właściciel zezwolił na dokładnie jeden resume B z `--synthesize-max-tokens 3000 --max-retries 0 --max-cost-usd 0.20`. Centralny PolicyEngine dopuścił projekcję 0,196300 USD. Jedyny call B zakończył się `end_turn`, 1904/2402 tokenów, zero search, kosztem 0,013914 USD. Run osiągnął `SUCCESS`, research `COMPLETE`, topic `USED`, karta #2 ma 4 VERIFIED, a łączny koszt 0,183964 USD pozostał poniżej capu. Karta jakościowo ma rekomendację `REJECT` (`THESIS_UNSUPPORTED`, `CLAIMS_WITHOUT_SOURCES`), co blokuje użycie jej do treści, ale nie narusza technicznego kryterium zakończenia Etapu 0. Nie wykonano retry, A1/A2, nowego runu ani Etapu 1.

- **Migracje:** 0006 ma własną transakcję; 0007 jest transakcyjna razem z wpisem `schema_migrations`, kontrolowana przez runner.
- **Testy:** resume cross-flow → ValueError (obie strony); `runs.cost_usd == sum(model_usage)` po każdej ścieżce staged (w tym B-failure); retry-failed z capem attempts; PARTIAL_EXHAUSTED terminalny; topic USED + `--force-re-research`; drugi attempt zablokowany gdy budżet wyczerpany między próbami; macierz dozwolonych przejść `mark_*`; parser topics z fence/uciętym JSON + księgowanie kosztu.
- **Kryteria akceptacji:** wszystkie dotychczasowe 102 testy + nowe zielone; run `9bbeb020` da się jawnie ponowić albo zamknąć jako PARTIAL_EXHAUSTED; `_detect_flow` nie istnieje.
- **Kryterium zakończenia etapu — SPEŁNIONE 2026-07-13:** istnieje realna Research Card #2 z `research_runs.status=COMPLETE`, `runs.status=SUCCESS`, 4 źródłami VERIFIED i kosztem 0,183964 ≤ 0,20 USD; potwierdzone po reopen bazy i opisane w `docs/RESEARCH_LOG.md`.
- **Ryzyka:** kolejna porażka realnego runu (mitygacja: retry-failed-candidates sprawia, że częściowa porażka przestaje być terminalna); backfill flow błędnie sklasyfikuje historyczny run (w bazie są 4 historyczne runy workflow research, z czego przed migracją tylko 2 miały rekord w `research_runs`; dwa znane runy single są mapowane po pełnym UUID, koncie i temacie, a pozostałe wyłącznie po jednoznacznych śladach strukturalnych).
- **Rollback:** 0006 przebudowuje `research_runs` i po migracji baza wymaga kodu świadomego obowiązkowego pola `flow`; sam powrót do poprzedniego commita nie jest kompatybilnym rollbackiem i spowoduje błędy `NOT NULL` przy nowych insertach starego kodu. Cofnięcie 0006 wymaga odtworzenia kopii bazy sprzed migracji albo osobnej migracji odwrotnej. 0007 jest addytywne: wcześniejszy kod ignoruje dodatkową kolumnę, a fizyczne usunięcie `attempts` wymaga osobnej migracji przebudowującej tabelę, nie resetu pliku bazy.
- **Nie wolno zmieniać:** legacy pipeline'ów (poza dopisaniem walidacji flow), trzech tabel źródeł, semantyki DRY_RUN, promptów researchu (działają — zmiany promptów tylko z osobnym uzasadnieniem), `.env`/cennika.

---

## Etap 1 — Fundament wykonawczy (scheduler, kolejka, workers)

- **Cel:** przejście z „człowiek uruchamia komendy" na „system sam wykonuje zakolejkowane zadania" — bez utraty ani zdublowania żadnego płatnego działania.
- **Uzasadnienie:** wszystko od Etapu 3 wzwyż (treści, publikacja, interakcje, metryki) wymaga zadań cyklicznych i odporności na restart; audyt wskazał brak locków i reapera jako warunek wstępny współbieżności.
- **Zależności:** Etap 0.
- **Pliki/moduły:** `app/storage/migrations/0009_jobs_system_flags.sql`, `app/models.py`, `app/ports/storage.py`, `app/storage/repositories.py`, `app/scheduler/`, `app/operations/`, runtime `PolicyEngine`, orchestrator i jobowa gałąź single research — wdrożone i zweryfikowane OFFLINE. Minimalna integracja Windows Task Scheduler wyłącznie uruchamia kanoniczny worker i maintenance; nie tworzy nowej logiki kolejkowej. Paid/browser pozostają BLOCKED, zadania systemowe nie są zarejestrowane, a produkcyjna migracja pozostaje niewykonana.
- **Zadania:**
  0. **✅ WYKONANE — Blockery przed płatnymi workerami ograniczone offline (2026-07-13):** (a) typowana taksonomia provider errors/retry; (b) atomowa finalizacja staged B z `0008`; (c) trwała foundation kolejki `0009`; (d) jeden worker/dispatcher dla LOCAL noop i RESEARCH `dry_run=true`; (e) fail-closed relacja job→run→research_run oraz recovery przypiętego runu. **512 testów**, 0 USD, brak API. To nie odblokowuje paid ani browser/public actions.
  1. **✅ WYKONANE —** tabela `jobs` + `system_flags`, modele/port/repozytoria, idempotency key, active research topic constraint, lease/heartbeat/recovery, marker `external_effect_started_at`, ścisły CAS `job.run_id` oraz NEEDS_VERIFICATION dla BROWSER/niepewnego lub już przypiętego research runu; rezerwacja globalnego budżetu.
  2. **✅ WYKONANE —** `run_once()` używa istniejącego atomowego claimu, przejścia LEASED→RUNNING i CAS terminalizacji. Podczas synchronicznego dispatchu daemon guard z osobnym połączeniem SQLite odnawia istniejący lease okresowo (produkcyjnie: lease 60 s, interwał 20 s). Daemon jest wyłącznie osłoną procesu: worker zawsze ustawia stop event, wywołuje `wake`, wykonuje bounded join z timeoutem i sprawdza `is_alive()`. Normalnie wątek kończy się i jest dołączony; timeout może pozostawić go żywego do odblokowania zależności, ale blokuje `DONE`, a po odblokowaniu stop event zatrzymuje kolejny heartbeat. `lost_lease` i `failure` są in-memory, a trwałe rozstrzygnięcie pozostaje w SQLite oraz recovery/reconciliation. Utrata lease lub błąd guarda blokuje `DONE`, a utrata lease ma pierwszeństwo przed błędem dispatchu. Nie ma retry dispatchu. `run_forever()` wymaga jawnego interwału; CLI `worker --once` wykonuje najwyżej jeden job.
  3. **✅ WYKONANE —** `idempotency_key UNIQUE`; joby BROWSER po wygaśnięciu lease → NEEDS_VERIFICATION, nigdy ponowne wykonanie.
  4. **✅ WYKONANE —** `attempts` jest zwiększane atomowo przy claimie, `attempts < max_attempts` ogranicza eligibility, a recovery rozdziela bezpieczne requeue, terminalne FAILED i niepewne NEEDS_VERIFICATION/reconciliation. `worker_policy.default_max_attempts` jest typowaną konfiguracją osiągalną z bezpiecznego composition root; durable paid enqueue nadal wymusza `max_attempts=1`. Read-only `operational-report` raportuje kolejkę/lease/reconciliation/rezerwacje/flagi i zwraca `UNKNOWN/BLOCKED` dla braków. Globalny timeout synchronicznego dispatchu jest jawnie descope/P2: provider timeout + lease + heartbeat + bounded guard join zabezpieczają istniejący kontrakt bez zabijania wątku w trakcie SQLite write.
  5. **✅ WYKONANE —** `PolicyEngine` odczytuje przy każdym jobie pięć runtime flags z SQLite bez cache i fail-closed dla offline workera. `dry_run=false`, paid oraz browser/public kończą się bez wykonania efektem BLOCKED/FAILED.
     - **⛔ BLOCKED —** paid worker oraz browser/public worker.
  6. **✅ WYKONANE —** jawne `reap-runs --once --stale-after-seconds X` najpierw uruchamia recovery jobów, potem w `BEGIN IMMEDIATE` robi CAS `RUNNING→STOPPED` wyłącznie dla stale runu bez joba `QUEUED/LEASED/RUNNING`. Przypięty RESEARCH po expiry zostaje `NEEDS_VERIFICATION`; auto-resume nie istnieje.
     - **✅ WYKONANE —** `MaintenanceRunner` wykonuje ten sam porządek przez osobne połączenie SQLite: `maintain --once` robi dokładnie jeden przebieg, a `maintain --poll --interval-seconds X` wykonuje pierwszy przebieg od razu i kolejne sekwencyjnie po stałym opóźnieniu. Pętla ma jawny stop event, waliduje skończone dodatnie progi i zatrzymuje się fail-closed przy błędzie factory/recovery/reapera/close/waitera. Jeżeli recovery/reaper i `close()` zawodzą razem, kontrolowany błąd zachowuje primary operation error i secondary cleanup error; sam błąd `close()` także nie raportuje sukcesu. Nie claimuje jobów, nie dispatchuje, nie uruchamia researchu ani nie odczytuje flag workera, więc safety cleanup działa także przy disabled/safe/kill.
     - **⬜ NOT_STARTED —** usługa schedulera systemowego (cron/service/autostart) dla maintenance/reapera.
  7. **✅ WYKONANE —** okna redakcyjne przed enqueue: czysty `SchedulingPolicy` czyta wyłącznie jawną konfigurację `growth_policy.editorial_schedule`, waliduje IANA timezone, okna tego samego dnia bez nakładania oraz deterministyczne DST. Zapisuje UTC `earliest_run_at` i zamknięty `schedule_reason`; czas przeszły, brak/niepoprawna konfiguracja i dowolny reason code są odrzucane fail-closed. Atomowy claim wybiera tylko `QUEUED` z `earliest_run_at <= now`, więc job przyszły pozostaje bez lease i attempts. `enqueue-research` tworzy wyłącznie job RESEARCH `dry_run`; nie uruchamia workera, dispatchu, API ani researchu.
     - **✅ CANDIDATE 2026-07-14 —** końcowa akceptacja restartu procesu dla jobów zaplanowanych: 58 scenariuszy plikowej SQLite/reopen. ADR-044 atomizuje inicjalizację; ADR-045 fence’uje późniejsze mutacje; ADR-046 wzmacnia czas i CSV; ADR-047 atomowo zamyka success joba; ADR-048 zamyka runtime kontrakt `DispatchResult`. Old-owner matrix, expiry przed recovery, claim po locku, crash/failpointy finalizacji, post-terminal diagnostic, malformed terminalization i realny CSV directory path są zielone. Wymagane ponowne niezależne review.
     - **⬜ NOT_STARTED —** usługa schedulera systemowego (cron/service/autostart), która jedynie uruchamia istniejące pętle; nie jest częścią polityki okien.
- **Migracje:** produkcja ma dokładnie `0001`–`0014`. Kontrolowany executor zastosował `0010`–`0014` po zweryfikowanym backupie i rehearsal; post-verification potwierdziło 35 triggerów, 13 legacy proofs, koszt `0.684580`, 0 jobs/attempts/events i kanoniczne flagi. Nowy baseline DB to `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`.
- **Testy:** WAVE 0B miała historycznie 894 testy, zaakceptowany baseline WAVE 1A — 1036, skonsolidowany pakiet — 1052, a poprawka QP-01 — **1079 passed / collected offline** z partycjami 259+264+277+279. (Snapshot QP-01 z 2026-07-16.) Etap 1 był wtedy formalnie `BLOCKED`, live API `ZABRONIONE`; obecnie Etap 1 = `CLOSED` (ADR-088), a kolejny live wymaga nowej zgody.
- **Kryteria akceptacji/zakończenia:** WAVE 0A jest **formally closed / `APPROVED WITH P2`**; P0-01, P1-01 i P1-02 są zamknięte. Zamknięcie WAVE 0A nie było zamknięciem Etapu 1; kryterium review/migration/live/formal decision z ADR-070 zostało później w całości spełnione, a Etap 1 = `CLOSED` (2026-07-17, ADR-088). Dry-run job ma atomową inicjalizację i wszystkie późniejsze trwałe mutacje fenced w SQLite. Minimalny launcher systemowy istnieje, lecz nie został zarejestrowany; paid/browser pozostają nieodblokowane.
- **WAVE 0A (2026-07-14, `APPROVED WITH P2` / FORMALLY CLOSED):** P0-01, P1-01 i P1-02 są zamknięte. Każdy realny SDK Anthropic jest tworzony z `max_retries=0` i skończonym dodatnim timeoutem; jedna logiczna próba klienta research wykonuje jedno żądanie. Zamknięcie fali nie odblokowuje paid workera, live API ani Etapu 2; bieżące warunki Etapu 1 są wymienione wyłącznie w ADR-070.
- **Ryzyka:** współbieżność SQLite (mitygacja: WAL z Etapu 0, jeden worker, lease); nadmierna komplikacja (mitygacja: ZERO zewnętrznych zależności — czysty SQLite).
- **Rollback:** worker to nowy, osobny punkt wejścia — wyłączenie go przywraca dokładnie dzisiejszy tryb ręczny.
- **Nie wolno zmieniać:** pipeline'ów researchu (worker je WOŁA, nie modyfikuje), kanonu kosztów, semantyki resume.

---

## Etap 2 — Research pipeline: dowód zamiast opinii (dokończenie)

- **Cel:** A2 czyta TREŚĆ źródła (nie „opinię o URL-u") i utrwala dowód per twierdzenie; kontrola sprzeczności; porządki po legacy.
- **Uzasadnienie:** P0-2c — bez fetch treści nazwa „extraction" jest na wyrost, a przyszły fact-audit artykułów (Etap 3) nie ma na czym pracować.
- **Zależności:** Etap 0 (pierwszy sukces staged na żywo); niezależny od Etapu 1 (może iść równolegle, ale nie przed Etapem 0).
- **Pliki/moduły:** NOWY `app/ports/fetch.py` (`FetchPort: fetch(url) -> FetchedDocument(text, status, retrieved_at)`), `app/research/anthropic_client.py` (A2 z narzędziem web_fetch API albo treścią z FetchPort w prompcie), `app/research/base.py`, migracja 0010 (`evidence_excerpt` per twierdzenie), `app/research/injection_guard.py`.
- **Zadania:**
  1. FetchPort + adapter (narzędzie web_fetch Anthropic API jako pierwszy wybór; lokalny fetcher jako drugi adapter później).
  2. A2: ekstrakcja Z TREŚCI; `evidence_excerpt` (krótki cytat + kontekst) per supported_claim; `VERIFIED` TYLKO gdy treść była faktycznie pobrana.
  3. Ujednolicenie semantyki `research_min_sources` (jedno znaczenie: liczba źródeł EXTRACTED+VERIFIED wymagana do B).
  4. Re-discovery jako jawna, osobna, capowana operacja („dodaj kandydatów do istniejącego runu") — domyka lukę „PARTIAL bez wyjścia mimo retry".
  5. Rozszerzenie injection guard (wektor rośnie wraz z fetch pełnych treści): wzorce wielojęzyczne, skan URL-i.
  6. Wygaszenie legacy: po ≥2 sukcesach staged na żywo — oznaczenie `run_research_pipeline`/`run_two_stage_research_pipeline` jako DEPRECATED (docstring + warning), plan konsolidacji tabel źródeł (osobna decyzja przed usunięciem czegokolwiek).
  7. Detekcja sprzeczności: pole `contradictions` + `contradictions_block` już istnieją — dodać test na realnym schemacie B i regułę „sprzeczność między evidence_excerpt dwóch źródeł → flaga do REVISE".
- **Migracje:** 0010 (evidence per claim).
- **Testy:** A2 bez fetch → wymuszone UNVERIFIED (już jest — rozszerzyć o ścieżkę fetch-failed); excerpt trafia do bazy i do karty; injection w pobranej treści neutralizowany; re-discovery nie dubluje kandydatów (dedup po URL).
- **Kryteria zakończenia:** realna karta, w której KAŻDE confirmed_claim ma źródło + evidence_excerpt z pobranej treści; koszt fetch w kanonie kosztów.
- **Ryzyka:** wzrost kosztu A2 (mitygacja: estymator rozszerzony o fetch, capy bez zmian); web_fetch może nie działać dla części stron (mitygacja: verification_status=FAILED, nie udawanie sukcesu).
- **Rollback:** flaga configu `research_fetch_enabled=false` przywraca dzisiejsze zachowanie A2.
- **Nie wolno zmieniać:** struktury A1/B, maszyny stanów (poza nową operacją re-discovery), bramek budżetowych.

---

## Etap 3 — Content pipeline (artykuły i Notes — BEZ publikacji)

- **Cel:** z karty PROCEED powstaje artykuł/Note przechodzący 3 deterministyczne audyty, zapisany jako `content_items.DRAFT→PENDING_APPROVAL`. Zero publikacji.
- **Uzasadnienie:** to pierwszy krok w stronę wartości użytkowej; tabela `content_items` czeka od migracji 0001.
- **Zależności:** Etap 0 + Etap 2 (fact-audit wymaga evidence_excerpt). Minimalna bramka Policy dla akcji CREATE_* — wdrażana TU, przed generatorami (zasada: bramka → generator).
- **Pliki/moduły:** NOWY `app/workflows/content/` (planner, writer, audits, rewriter), `app/policies/policy_engine.py` (check dla CREATE_ARTICLE/CREATE_NOTE: mode, limity tworzenia), repozytoria content_items, `instrukcja dla pisania artykulow/CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md` jako podręcznik stylu (wejście do promptów + reguł deterministycznych).
- **Zadania:** planner (artykuł vs Note wg score tematu — progi już w configu); writer (draft z karty, każde twierdzenie linkowane do claim+excerpt); audyt faktów (deterministyczny: każde twierdzenie w tekście musi mapować się na claim karty; twierdzenia bez pokrycia → obniżenie score/REVISE); audyt stylu (podręcznik + mierzalne reguły: długości, struktura, zakazane frazy); audyt growth (tytuł/lead/CTA wg polityk); pętla rewrite (max N z configu); duplicate detection vs istniejące content_items (ten sam mechanizm co dedup tematów); scoring końcowy + zapis evaluations.
- **Doprecyzowanie dokumentacyjne:** Article Brief, A1–A9, N1–N16 wyłącznie lokalnie/dry-run, Fact/Style/Growth Audit, SEO metadata i diversity memory są opisane jako PLANNED/PROPOSED w `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`; pełny materiał referencyjny jest w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md` (EXTERNAL STRATEGIC RESEARCH — NOT IMPLEMENTED). Negatywna bramka kończy się `SKIP` z reason code; nie publikuje ani nie tworzy automatycznej treści zastępczej.
- **Migracje:** 0011 (`evaluations`; ewentualne braki kolumn content_items).
- **Testy:** E2E dry-run topics→research→draft→audyty→PENDING_APPROVAL (pierwszy pełny test integracyjny przez wszystkie workflow); twierdzenie bez pokrycia w karcie → REVISE; duplikat treści wykryty; koszt każdego wywołania w kanonie; Policy blokuje CREATE_ARTICLE dla konta COMMENT_ONLY.
- **Kryteria zakończenia:** pełny łańcuch dry-run zielony; ≥1 realny artykuł-draft z audytami (za zgodą właściciela) oceniony przez człowieka jako publikowalny.
- **Ryzyka:** jakość stylu (mitygacja: podręcznik + iteracje z właścicielem na dry-runach); koszt generacji (mitygacja: te same bramki budżetowe i capy per-run).
- **Rollback:** moduł content jest addytywny; nieużywanie go przywraca stan Etapu 2.
- **Nie wolno zmieniać:** research pipeline'u, `DisabledBrowser` (publikacja nadal fizycznie niemożliwa).

---

## Etap 4 — Approval i autonomy (bramki przed publikacją)

- **Cel:** kompletny, egzekwowany system poziomów autonomii, akceptacji i SAFE MODE — ZANIM powstanie jakakolwiek możliwość publikacji.
- **Uzasadnienie:** publikacja bez działających bramek = niekontrolowane ryzyko reputacyjne; dziś `autonomy_level`/`AccountMode`/`AccountPolicy` to martwa konfiguracja (P1-10).
- **Zależności:** Etap 1 (system_flags, jobs), Etap 3 (jest co zatwierdzać).
- **Pliki/moduły:** `app/policies/policy_engine.py` (centralny `check(action, ctx)`), repozytoria approvals, NOWY `app/ui/` (panel FastAPI localhost: readonly stan + approvals + kill-switch), migracja 0012 (`autonomous_decisions`).
- **Zadania:** macierz akcja×poziom×tryb konta; egzekucja WSZYSTKICH limitów AccountPolicy (daily_comment_limit, daily_note_limit, weekly_article_limit, max_per_author_per_day, link_ratio); cooldowny; scoring gates (auto-approve TYLKO ≥ progu + log autonomous_decisions); SAFE MODE (progi błędów z configu, wejście auto, wyjście ręczne przez panel); approvals workflow w panelu; per-akcja cap kosztu w bibliotece (dokończenie P1-4).
- **Migracje:** 0012 (`autonomous_decisions`).
- **Testy:** każda kombinacja poziom×akcja z macierzy; limit dzienny blokuje N+1-szą akcję; SAFE MODE zatrzymuje trwającą pętlę przy następnym checku; auto-approve poniżej progu ODMAWIA; wszystkie decyzje autonomiczne logowane.
- **Kryteria zakończenia:** żadna akcja zewnętrzna nie może wykonać się z pominięciem `PolicyEngine.check` (test architektoniczny: orchestrator jest jedynym wołającym porty); panel pozwala zatwierdzić/odrzucić draft.
- **Ryzyka:** panel = pierwszy współbieżny czytelnik bazy (mitygacja: WAL już włączony w Etapie 0).
- **Rollback:** poziom autonomii w configu z powrotem na LEVEL_0/1; panel można wyłączyć.
- **Nie wolno zmieniać:** zasad ADR-018 (NO_REPLY, brak ujawniania) — one nie podlegają poziomom autonomii.

---

## Etap 5 — Publishing (Substack adapter)

- **Cel:** stabilna, idempotentna publikacja zatwierdzonych treści na Substacku z weryfikacją skutku.
- **Uzasadnienie:** pierwsza realna wartość zewnętrzna eksperymentu; wszystkie poprzednie etapy istnieją po to, żeby ten był bezpieczny.
- **Zależności:** Etapy 1+3+4 W CAŁOŚCI. Jawna zgoda właściciela + weryfikacja ToS Substacka (otwarty punkt z ADR-018) PRZED pierwszą publikacją.
- **Pliki/moduły:** NOWY `app/browser/` (adapter `PublicationChannelPort`/`BrowserPort` na Playwright), `app/workflows/publishing/`, tabela `screenshots` (wreszcie używana), `jobs` kind='browser'.
- **Zadania:** persistent context per konto + procedura pierwszego RĘCZNEGO logowania (MASTER §8.2); `is_logged_in` + stop-conditions; publish z `idempotency_key` + verify-before-publish + potwierdzenie odczytem stanu + screenshot; status UNCERTAIN bez auto-retry; recovery po częściowym błędzie (NEEDS_VERIFICATION po wygasłym lease); serializacja jobów browser (jeden Chromium); `max_consecutive_browser_errors` → SAFE MODE; drugi adapter `FileExportChannel` jako test szczelności kontraktu portu.
- **Migracje:** 0013 (kolumny weryfikacji publikacji w content_items/jobs, jeśli brakujące).
- **Testy:** dubel idempotency_key odrzucony; UNCERTAIN nigdy nie retry'owany automatycznie; crash po kliknięciu a przed potwierdzeniem → NEEDS_VERIFICATION; adapter plikowy przechodzi ten sam kontrakt testowy co Substack (contract tests portu).
- **Kryteria zakończenia:** ≥1 realna publikacja Note za akceptacją, potwierdzona odczytem stanu + screenshot; zero dubli w całej historii jobów.
- **Ryzyka:** zmiany UI Substacka (stop-conditions + selektory w jednym miejscu); ToS (weryfikacja przed startem, decyzja właściciela); ban/rate-limiting (limity z Etapu 4 + wolny start).
- **Rollback:** kill-switch/SAFE MODE; wyłączenie workera browser; treści pozostają w APPROVED.
- **Nie wolno zmieniać:** zasady „UNCERTAIN ≠ retry"; zakazu auto-loginu; braku zapisu haseł.

---

## Etap 6 — Interakcje (czytanie, komentarze, odpowiedzi)

> Doprecyzowanie: wybór i publiczna obsługa Notes oraz K1–K8 (komentarze), odpowiedzi i restacki należą do tego etapu, nie do Etapu 3. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` (PLANNED/PROPOSED); wartości, dane i koszty z raportu Fable pozostają zewnętrzną, mieszaną weryfikacyjnie propozycją.

- **Cel:** kontrolowane uczestnictwo w ekosystemie: czytanie, komentarze, odpowiedzi czytelnikom, subskrypcje — w limitach i z pełnym logiem.
- **Zależności:** Etap 5 (ta sama warstwa przeglądarki i te same bramki).
- **Pliki/moduły:** NOWY `app/workflows/interactions/` (discovery targetów, scoring, generacja, odpowiedzi), tabele `target_items`/`interactions` (wreszcie używane).
- **Zadania:** read-only discovery (feed/szukajki) → target_items ze score; scoring komentarza (specyfikacja przeniesiona ze starego planu D.5 do configu); generacja komentarza (bramka Policy → generator); odpowiedzi na komentarze pod własnymi treściami; scoring subskrypcji (D.6); NO_REPLY dla pytań o tożsamość (ADR-018 — deterministyczny klasyfikator + brak odpowiedzi w wątku); limity częstotliwości (daily_comment_limit, max_per_author_per_day, cooldowny per autor); polityki bezpieczeństwa: zero DM, zero inicjowania kontaktu, zero linków ponad link_ratio.
- **Testy:** limit per autor egzekwowany; identity-question → brak odpowiedzi + log; komentarz poniżej progu scoringu nie wychodzi z DRAFT.
- **Kryteria zakończenia:** tydzień działania na LEVEL_1/2 bez przekroczenia żadnego limitu i bez interwencji krytycznej.
- **Ryzyka:** odbiór społeczny komentarzy (wolumen minimalny na starcie, jakość > ilość); moderacja Substacka (cooldown po ukrytym komentarzu — stop-condition).
- **Rollback:** wyłączenie kind='interaction' w schedulerze.
- **Nie wolno zmieniać:** bezwzględnych zakazów z MASTER §7.2/§7.3.

---

## Etap 7 — Analytics i strategy loop

> Doprecyzowanie: metryki per content item, rozdzielone followers/free subscribers/paid subscribers/engaged subscribers, estymowana atrybucja (`is_estimated`), eksperymenty i weekly strategy należą do tego etapu. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` (PLANNED/PROPOSED); nie istnieje jeszcze kolektor ani wynik eksperymentu.

- **Cel:** system mierzy skutki własnych działań i koryguje strategię na podstawie danych, z pełnym logiem decyzji.
- **Zależności:** Etap 5 (są publikacje do mierzenia); Etap 6 wzbogaca dane, nie blokuje.
- **Pliki/moduły:** NOWY `app/metrics/` (kolektor → metrics_daily), NOWY `app/workflows/strategy/`, migracja `0014_strategy_decisions.sql`.
- **Zadania:** kolektor metryk (read-only Playwright; estymacje oznaczane `is_estimated`); attribution (metryka↔treść po external_url/dacie); tygodniowy raport (docs/weekly-reports/ — automatyczny szkic); ocena skuteczności vs funkcja celu wzrostu (wagi z growth_policy, ADR-002); strategy engine: propozycje korekt parametrów treści/harmonogramu → `strategy_decisions` (problem→dane→decyzja→oczekiwany efekt→wynik po fakcie); korekty wchodzą przez config, NIGDY w politykę bezpieczeństwa; na LEVEL<3 zmiany strategii wymagają akceptacji.
- **Testy:** attribution deterministyczna na danych syntetycznych; strategia nie może zmienić limitów bezpieczeństwa (test negatywny); każdy wpis strategii kompletny.
- **Migracje:** 0014 (`strategy_decisions`).
- **Kryteria zakończenia:** ≥2 cykle tygodniowe z raportem i ≥1 udokumentowaną, zamkniętą pętlą decyzja→efekt.
- **Ryzyka:** za mało danych do wniosków (mitygacja: decyzje oznaczane confidence, minimalne progi próby).
- **Rollback:** strategia w trybie „proponuj, nie stosuj".

---

## Etap 8 — Productization readiness (self-hosted)

- **Cel:** projekt instalowalny przez kogoś innego niż autor: konfiguracja wielu publikacji, Docker, VPS, diagnostyka.
- **Zależności:** Etapy 1–7 stabilne (≥1 miesiąc działania).
- **Zadania:** aktywacja multi-konta (izolacja już testowana — ADR-006/007); Dockerfile (python:3.12-slim + playwright chromium; wolumeny `/app/data`, `/app/config`; profile przeglądarki w wolumenie); `.env` → zmienne środowiskowe kontenera (podpięcie `EnvSecretStore` zamiast rozproszonego `os.getenv`); runtime-writes poza repo (COSTS.csv/RESEARCH_LOG → `data/`, eksport do docs osobnym krokiem — P2-11); jawny krok `migrate` w deployu (P2-10); backup SQLite (`VACUUM INTO` przed oknami publikacji); healthcheck + diagnostyka (`doctor` CLI); eksport/import konfiguracji publikacji; dokument instalacji na VPS; separacja danych klientów = izolacja per instancja (jedna instalacja = jeden właściciel; multi-tenant POZA zakresem).
- **Kryteria zakończenia:** czysta instalacja z README na świeżym VPS kończy się działającym dry-runem w <30 minut.
- **Ryzyka:** dryf konfiguracji lokalna↔kontener (mitygacja: jeden loader konfiguracji, testy na obu ścieżkach).
- **Rollback:** tryb lokalny pozostaje pierwszorzędny; Docker to opakowanie, nie zależność.

---

## ETAP 1 — **`CLOSED`** (formalna decyzja właściciela 2026-07-17)

Etap 0 spełnił kryterium zakończenia 2026-07-13. Techniczny zakres Etapu 1 obejmuje kolejkę, claim/lease/fence/heartbeat, restart/recovery, maintenance/reaper, scheduling policy, runtime flags, dry-run worker, durable provider/usage/settlement/reconciliation, minimalny launcher Windows Task Scheduler, read-only raport, LA-01-R1/LA-02, LA-03 oraz zatwierdzoną naprawę NIA-P2-RV-01…05. Kod i produkcja mają schema `0014`; aktualny post-live SHA to `5BEA9E26597E6A628EF875A7F5115465E94CB600B38213A67794EE94232C6D10`. Pierwszy realny durable request jest rozliczony; nie powstała Research Card, co nie było bramką zamknięcia. Zadania systemowe nie są zarejestrowane. Browser/public worker pozostaje BLOCKED; kolejny live request jest ZABRONIONY bez nowej, oddzielnej zgody właściciela.

### Spełnione kryterium zakończenia Etapu 1

- **Przed kontrolowanym live testem:** dokładny kontrakt testu z twardym capem, `max_retries=0`, jednym jobem i jednym requestem; osobna zgoda właściciela. Migracja `0009→0014`, nowy baseline, inicjalizacja pięciu flag oraz niezależny review QP-01 i trwałego wyniku migracji — wykonane. ✅
- **Formalne CLOSED:** wykonano jeden kontrolowany live durable single flow (attempt/request rozliczony); niezależny re-review naprawy NIA-P2-RV-01…05 wydał `APPROVE WITH MINOR/P2`; brak otwartego MAJOR/CRITICAL; właściciel podjął formalną decyzję o zamknięciu 2026-07-17 (ADR-088). ✅ Pozytywna Research Card nie była wymaganym kryterium.
- **Poza kryterium:** browser/publikacja, FetchPort/evidence excerpts, content/panel/autonomia/interakcje/analytics, Etap 2+ i P2 bez osiągalnego naruszenia (w tym `RV-R2-P2-1`/`RV-R2-P2-2` → backlog Etapu 2).

Review LA-01-R1 i LA-02 są zakończone wynikiem `APPROVE WITH MINOR/P2`; LA-03 ma `APPROVE WITH MINOR/P2`, a naprawa NIA-P2-RV-01…05 wraz z trwałym wynikiem live przeszła niezależny re-review z tym samym werdyktem. Root causes `PROCESSES_PRESENT` i `DB_HANDLES_PRESENT` są zamknięte technicznie. Pierwszy realny request dowiódł exact-once/usage/settlement/fail-closed; typowany parse failure oznacza brak Research Card, co NIE było bramką zamknięcia. Na tej podstawie właściciel podjął formalną decyzję: Etap 1 = `CLOSED` (2026-07-17, ADR-088). Nie wolno rozpoczynać Etapu 2 ani ponawiać terminalnego joba; kolejny realny request wymaga oddzielnej, jawnej decyzji właściciela i nowego dozwolonego joba.

### WAVE 0B.2 — zapis historyczny provider ledger hardening (2026-07-14)

**Wynik historyczny 752 testów, zastąpiony przez WAVE 0B.3.** `0012_provider_ledger_hardening` uzupełnia 0010/0011 bez ich edycji. Realny client przechodzi wyłącznie przez typowany context i atomowe potwierdzenie `REQUEST_STARTED`; snapshot intentu determinuje model, timeout, tokeny, pricing i kontrakt pipeline/prompt mimo późniejszej zmiany ENV. Migracja rozróżnia legacy od dowodliwego usage, a DB/API wymuszają request→attempt→job→run. Nie ma auto-retry ani attempt #2 po niejednoznacznym wyniku. Nie jest to WAVE 1: durable paid A1/A2/B, real resume i operator reconciliation pozostają poza zakresem.

### WAVE 0B.3 — historyczna derived request identity i authoritative lease time (2026-07-14)

**Wynik historyczny, zastąpiony przez końcową falę WAVE 0B.** Centralna bramka wylicza `expected_request_id = f"{job_id}:{stage}:{attempt_no}"` bez normalizacji i wymaga go zarówno od contextu, jak i `ProviderAttempt` oraz `Idempotency-Key`. Druga asercja storage, wykonywana tuż przed SDK, pobiera `now` z execution clock w transakcji SQLite; `checked_at` nie autoryzuje lease.

### WAVE 0B — domykająca fala po review (2026-07-15)

**Status historyczny przed checkpointem WAVE 0B: `WAVE 0B APPROVED WITH P2 — READY FOR CHECKPOINT`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.** `0013_provider_attempt_usage_integrity` była wtedy trzynastą migracją. **Stan obecny:** WAVE 0B i WAVE 1A są `CLOSED — APPROVED WITH P2`; pierwsza LA-01 jest `REJECTED — MAJOR`, LA-01-R1 i LA-02 są `APPROVED WITH MINOR/P2 — CHECKPOINTED`, LA-03 ma `APPROVE WITH MINOR/P2`, pierwszy pakiet P2 jest `REJECTED — MAJOR`, a naprawa NIA-P2-RV-01…05 przeszła niezależny re-review z wynikiem `APPROVE WITH MINOR/P2`, na której podstawie właściciel formalnie zamknął **Etap 1 = `CLOSED`** (2026-07-17, ADR-088); kod i produkcja mają `0014`, post-live DB SHA `5BEA9E…C6D10`, bieżąca regresja 1235/1235, a pierwszy request jest `SETTLED` bez Research Card.

Intent jest jedynym snapshotem semantyki requestu: zawiera dane prompt-input (`question`, `niche`, `required_depth`, `guidance`), stage, account/topic, provider/model, limity, pricing+fingerprint, cap, workflow/mode, retry, flags i wersje schema/prompt/pipeline. Worker buduje `ResearchPlan` z tego snapshotu, a guard bieżącego topic/account wyłącznie odmawia po drift — nie odbudowuje requestu z mutowalnych danych. Finalna transakcja przed callerem sprawdza cały lifecycle `job→run→research_run→attempt`, terminalne pola oraz ponownie wyliczony fingerprint. Każda rozbieżność daje `caller=0`, usage/koszt/settlement=0, brak attempt #2 i kontrolowane `NEEDS_RECONCILIATION`.

Procesowy kernel testów działa przed collection i dziedziczy się do subprocessów; chroni bazę projektu, socket/DNS, SDK, lowercase secret i proxy, Windows/URI SQLite oraz nie blokuje tymczasowych SQLite. Niedurable `--real --resume` jest odrzucone przed jakąkolwiek mutacją. Weryfikacje po REV-06 (873; 206+218+226+223) i REV-09/10 (887; 211+222+229+225) są historyczne. Bieżąca po W0B-RR-01 ma **894 passed / collected** (213+224+231+226), jeden `ROUND_HALF_UP` kontrakt USD do granicy publicznej, full SHA-256 exact-once coverage i brak BOM. Baseline DB niezmieniony. **Nie jest to zamknięcie WAVE 0B ani Etapu 1; niezależny review został zakończony, a oczekiwany jest wyłącznie commit checkpointu.**

W0B-REV-06 naprawia potwierdzoną lukę kosztową bez rozszerzania paid scope: `max_tokens` z durable intentu jest przekazywany do caller/estimate/policy/reservation, nie zastępuje go pipeline'owa stała 3000. Actual cost jest porównywany po canonicalizacji pieniądza; nadwyżka utrwala usage, zatrzymuje attempt jako `NEEDS_RECONCILIATION` i odmawia sukcesu/attempt #2. Testy offline używają wyłącznie fake callerów i tymczasowych SQLite; live API pozostaje `ZABRONIONE`.
