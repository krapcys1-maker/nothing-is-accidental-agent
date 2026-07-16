# Nothing Is Accidental Agent

Lokalny (local-first) agent AI budowany do autonomicznego prowadzenia publikacji Substack „Nothing Is Accidental" — wybór tematów, research z dowodami, pisanie, ocena jakości, publikacja, interakcje i pętla strategii — w twardych limitach budżetu i z pełnym audytem każdej decyzji, kosztu, błędu i interwencji człowieka.

## Source of Truth

The only authoritative architecture and implementation documents are:

- `MASTER_ARCHITECTURE.md`
- `IMPLEMENTATION_ROADMAP.md`
- `CURRENT_PROJECT_STATE.md`

All other historical plans and audits are archived in `docs/archive/superseded_plans/` and must not be used as implementation guidance.

Obowiązujące dodatkowo (logi, nie plany): `docs/DECISIONS.md` (rejestr ADR), `docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md`, `docs/HUMAN_INTERVENTIONS.md`, `docs/COSTS.csv`, `docs/RESEARCH_LOG.md` oraz kronika redakcyjna `opis-budowy-substack/` (materiał do serii artykułów). Podręcznik stylu pisania: `instrukcja dla pisania artykulow/`.

## Stan projektu (skrót — pełny obraz w CURRENT_PROJECT_STATE.md)

- Zbudowane i przetestowane offline: konfiguracja, SQLite z **14 migracjami** (ostatnia `0014_provider_attempt_reconciliation`), Policy Engine, kolejka/worker, ledger provider attempt, durable single-research `durable_provider_v2`, minimalny launcher systemowy, raport read-only i copy-preflight migracji. `model_usage` pozostaje jedynym ledgerem kosztu; operatorski resolver L1 rozdziela fakt finansowy od wyniku wykonawczego, z append-only historią `reconciliation_events`, pełną weryfikacją lineage i bez retry/attemptu #2. **1052 testy, wszystkie offline.**
- WAVE 0A, WAVE 0B i WAVE 1A są formalnie **`CLOSED — APPROVED WITH P2`**. Skonsolidowany Etap 1 ma status implementera **`CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`**, ale formalnie pozostaje `BLOCKED`. Minimalny Windows Task Scheduler launcher i read-only raport są zweryfikowane offline; nie zarejestrowano zadań systemowych. Kod zna 14 migracji, produkcyjna `data/agent.db` nadal ma 9 i nie została zmigrowana. Live API jest **ZABRONIONE**.

Operacyjne instrukcje dla schedulera, raportu, konfiguracji attempts i przyszłej migracji copy-preflight są w [`docs/STAGE1_OPERATIONS.md`](docs/STAGE1_OPERATIONS.md). `python -m app.main operational-report` otwiera bazę wyłącznie read-only i pokazuje braki jako `UNKNOWN/BLOCKED`. `python scripts/manage_windows_tasks.py plan --task worker` oraz analogiczne `--task maintenance` tylko generują plan; instalacja każdego zadania wymaga osobnej zgody i jawnego przełącznika potwierdzającego.

Formalne zamknięcie Etapu 1 wymaga kolejno: niezależnego review tego pakietu; osobno zatwierdzonej migracji produkcji `0009→0014`, nowego baseline SHA i inicjalizacji pięciu flag; jednego kontrolowanego live durable single flow z twardym capem, `max_retries=0`, dokładnie jednym jobem i jednym requestem; niezależnego review trwałego wyniku; braku MAJOR/CRITICAL; formalnej decyzji właściciela. Browser, publikacja, FetchPort, content pipeline, panel FastAPI, autonomia, interakcje, analytics i Etap 2+ nie należą do tego kryterium.
- Niezbudowane: durable realne A1/A2/B, realne resume, artykuły/Notes, approval/autonomia, publikacja (Playwright), interakcje, analityka i panel.
- Zero publikacji na Substacku; realny koszt dotąd: 0,684580 USD z limitu 40 USD/mies.

## Formalne zamknięcie WAVE 1A (2026-07-16)

Implementer zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Niezależny finalny re-review odtworzył 1036/1036, cztery partycje exact-once, `compileall` i `git diff --check`, a także wykonał własne kontrpróby: 149/149 przez prawdziwy `Worker.run_once`, 36/36 SQLite floor oraz 30/30 recovery/reaper/crash-window. Werdykt `APPROVE WITH MINOR/P2` został przyjęty przez właściciela, który formalnie ustawił WAVE 1A na `CLOSED — APPROVED WITH P2`. Pozostają P2-1 (fingerprint mismatch: fail-closed, widoczny operatorowi, bez przepisywania intentu i bez retry) oraz P2-2 (atomowy StoragePort i spójny stan SQLite nie dowodzą pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel). Etap 1 pozostaje `BLOCKED`, live API `ZABRONIONE`; Etap 2 nie został rozpoczęty.

## Historyczna aktualizacja implementacji WAVE 1A (2026-07-15–2026-07-16)

> **Nowsza aktualizacja `W1A-R4-01` (2026-07-16):** czwarty niezależny review odtworzył `job=FAILED` + `attempt=REQUEST_STARTED` po lokalnym błędzie Workera. Centralna operacja StoragePort atomowo terminalizuje tylko bez active attemptu, a `RESERVED`/`REQUEST_STARTED` eskaluje do widocznego `NEEDS_RECONCILIATION`, zachowując rezerwację i zabraniając retry. Triggery SQLite blokują obejście przez terminalne job/run/research_run. P2-1 pozostaje fail-closed; P2-2 oznacza trwały floor SQLite, nie dowód pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel. Walidacja: **1036/1036**, partycje 248+253+267+268, race 38×30, krytyczne pliki i QA ×10, niezmieniona chroniona baza. WAVE nadal otwarta; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

WAVE 0B jest formalnie **`CLOSED — APPROVED WITH P2`** po checkpointowym commicie `c25e1254044d89c7703a6614e9ee831eb226e87c`. WAVE 1A jest wyłącznie **`CANDIDATE — AWAITING INDEPENDENT REVIEW`** po naprawie odrzucenia `REJECTED — MAJOR`: migracja `0014` poprawiona in place (append-only `reconciliation_events`, pełny kontrakt stanów i surowe wymuszenia SQLite), lokalny resolver L1 oraz CLI rozdzielają finansowe i wykonawcze skutki `NEEDS_RECONCILIATION`. `MANUAL_REVIEW_REMAINS_REQUIRED` jest dozwolone tylko z `CHARGE_UNKNOWN` (brak dead-endu). Istniejący `model_usage` akceptowany po pełnej tożsamości; `RESULT_ALREADY_FINALIZED` wymaga wyłącznej Research Card. `model_usage` pozostał jedynym ledgerem kosztu; niezmienna spójność ledger↔cache; nie ma auto-retry, attemptu #2 ani wywołania providera. CLI preview/confirm używa version tokenu. Walidacja tej historycznej iteracji: **1007 testów**, 14 migracji (`0001`–`0014`), niezmieniona chroniona baza. Historyczne 919/894/948/955/980/982 są wcześniejszymi iteracjami. Poprawka `W1A-VERIFY-01` (ADR-064): resolver `EXECUTION_FAILED` akceptuje maintenance-`STOPPED` run i atomowo doprowadza `STOPPED → FAILED` (bez wskrzeszenia, `DONE` ani attemptu #2); +7 deterministycznych testów, flaky node 30/30. Poprawka `W1A-VERIFY-02` (ADR-065): pełna walidacja lineage — foreign `runs.account_id`/`workflow=ANALYTICS` był wcześniej fail-open i nie był objęty 955/955; teraz aplikacja + version token v2 + trigger SQLite wymuszają zgodność account/workflow/topic/flow/kind/intent (każda niespójność = fail-closed, zero mutacji); +25 testów lineage (`tests/test_reconciliation_lineage.py`, `scripts/qa/reconciliation_lineage_disproof.py`). Pełny audyt software-assurance working tree (2026-07-16): trzy MINOR naprawione (kontrolowane exit codes `list-reconciliations`, usunięte martwe pole `version_token` wyniku resolvera, anotacja `actual_cost_usd`); W1A-AUD-04 sklasyfikowany wtedy jako P2 report-only. **Trzecie niezależne review = `REJECTED — MAJOR` (2026-07-16):** W1A-AUD-04 przeklasyfikowany na MAJOR (stuck `RESERVED`/`REQUEST_STARTED` po crashu = niewidoczny, nierozstrzygalny, wieczna rezerwacja), plus W1A-SQLITE-01 (surowa terminalizacja bez pełnego lifecycle/eventu) i W1A-SQLITE-02 (mutowalny/kasowalny kanon po settlement). **Fala naprawcza (autoryzowana):** recovery eskaluje oba crash-windows do `NEEDS_RECONCILIATION` z enumerowanym powodem (`LEASE_EXPIRED_BEFORE/AFTER_REQUEST_STARTED`) i append-only eventem `AUTO_ESCALATION`; attempt, który nigdy nie osiągnął `REQUEST_STARTED`, może być rozstrzygnięty wyłącznie `NOT_CHARGED`; resolver flipuje attempt jako OSTATNIĄ mutację, a triggery 0014 (in-place) wymagają przy terminalizacji zgodnego eventu `FINAL_RESOLUTION`, terminalnego spójnego lifecycle ze zwolnioną rezerwacją i cache'ów równych kanonowi; kanoniczny `model_usage` i oba cache są niezmienne po terminalu; pełna obsługa błędów CLI `list-reconciliations` (3/6 dla open/query/close); QA script sprząta katalogi tymczasowe z twardą kontrolą w exit code. +25 trwałych testów (eskalacja H1–H20, raw-SQLite I, ciek QA); **982 → 1007**. Historyczne 919/894/948/955/980/982 są historyczne. Etap 1 nadal `BLOCKED`, live API `ZABRONIONE`.

## Uruchomienie

```bash
pip install -e .[dev]           # + .[llm] tylko do realnych wywołań API
python -m pytest                # 1052 testy, bez sieci
python scripts/run_test_partitions.py --parts 4 --verify  # pełne SHA-256 node ID
python -m app.main run-topics --count 6      # dry_run (zero kosztu)
python -m app.main run-research              # dry_run (zero kosztu)
# realny research: WYŁĄCZNIE scripts/run_capped_research.py (pre-flight, capy,
# --estimate-only); wymaga każdorazowej zgody właściciela na wydatek
python scripts/run_capped_research.py --topic-id 2 --estimate-only
```

Konfiguracja: `.env` (sekrety, modele — patrz `.env.example`) + `config/*.yaml` (limity, wagi, konta). Domyślnie `DRY_RUN=true`.

## Ważne zasady

- Nie wpisuj hasła do Substacka nigdzie — logowanie zawsze ręczne w osobnym profilu przeglądarki.
- Każde płatne lub publikujące uruchomienie wymaga osobnej, jawnej zgody właściciela.
- Repozytorium jest PRIVATE (ADR-021); jawność AI reguluje ADR-018.
