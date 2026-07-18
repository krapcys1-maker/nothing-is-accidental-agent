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

- **ETAP 2 / E2-A = `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW` (ADR-102).** Nowy offline-only CLI/job/Worker/Dispatcher uruchamia STAGED A1/A2/B z `FakeFetch`, zapisuje E1 retrieval i zweryfikowany exact excerpt, nadaje `VERIFIED` wyłącznie lokalnie, tworzy Research Card i atomowo terminalizuje lifecycle. Addytywne `0017_evidence_pipeline_lineage` utrwala candidate→retrieval→excerpt→card source; runtime wymaga dokładnie `0017`. Produkcyjna DB nadal jest na `0014`; `0015`–`0017` nie zostały zastosowane. Live, realny Fetch, provider, browser i publikacja pozostają nieautoryzowane.

- **ETAP 2 / WAVE E1 = `CLOSED — APPROVED WITH MINOR/P2`; ETAP 2 = `IN PROGRESS — E1 CLOSED, E2 NOT STARTED` (ADR-101).** Po niezależnym `REJECT`, jednej naprawie B01–B04 i re-review `APPROVE WITH MINOR/P2` PR #3 został zmergowany do `main` jako `42762a76d8c151cdb13d07fa384d32c9bfef0231`. Post-merge checkpoint: 1454/1454, zero skipped, exact-once `352+355+366+381=1454`, evidence `79/79` i migration `44/44`, QA `35/35`, `21/21`, `4/4`, `10/10`. Produkcja nadal ma schema `0014`; `0015`/`0016` wymagają osobnej autoryzacji; live, realny Fetch, browser i publikacja pozostają zablokowane.
- Zbudowane i przetestowane offline: konfiguracja, kod SQLite z **17 migracjami** (produkcja nadal zweryfikowana na `0014`/14), Policy Engine, kolejka/worker, ledger provider attempt, durable single-research v3 i E2-A offline evidence spine. `0016` pozostaje fundamentem E1; `0017` dodaje minimalny append-only lineage candidate→retrieval→excerpt→card source oraz jawny composition root STAGED. Lokalny verifier, a nie fake/model A2, nadaje `VERIFIED`. Runtime `SqliteStorage.open()` wymaga dokładnie `0017`; inicjalizacja oraz kroki `0014→0015`, `0015→0016` i `0016→0017` są osobnymi operacjami. Legacy single i paid `durable_provider_v2` nie zmieniły semantyki.
- **HISTORYCZNY SNAPSHOT ADR-095 PRZED STARTEM E1:** WAVE OUTPUT-SIZE CONTRACT = `CLOSED — APPROVED WITH MINOR/P2`; POSITIVE CONTROLLED-LIVE = `INDEPENDENTLY CONFIRMED`; ETAP 2 POSITIVE-LIVE GATE = `FORMALLY ACCEPTED`; Etap 2 był wtedy `NOT STARTED`. Implementer wykazał 1288/1288, niezależny końcowy review wykonał 223/223 własnych wąskich testów i wydał `APPROVE`, a właściciel formalnie przyjął bramkę. Trwały wynik: koszt `0.063278 USD`, job `DONE`, run `SUCCESS`, research_run `COMPLETE`, attempt `SETTLED`, Research Card `id=3`, redakcyjne `REJECT/WEAK_SOURCES`. Bieżący status określa ADR-101; kolejny live jest `NOT AUTHORIZED`, browser i publikacja pozostają `BLOCKED`, gate `False`, flagi fail-closed.

Operacyjne instrukcje dla schedulera, raportu, konfiguracji attempts i przyszłej migracji copy-preflight są w [`docs/STAGE1_OPERATIONS.md`](docs/STAGE1_OPERATIONS.md). `python -m app.main operational-report` otwiera bazę wyłącznie read-only i pokazuje braki jako `UNKNOWN/BLOCKED`. `python scripts/manage_windows_tasks.py plan --task worker` oraz analogiczne `--task maintenance` tylko generują plan; instalacja każdego zadania wymaga osobnej zgody i jawnego przełącznika potwierdzającego.

Migracje schema `0014→0015`, `0015→0016` i `0016→0017` nie są wykonywane podczas startu aplikacji. Jawne rooty to odpowiednio `scripts/migrate_schema_0015.py`, `scripts/migrate_schema_0016.py` i `scripts/migrate_schema_0017.py --db-path <PATH> --confirm-0016-to-0017`; każdy wymaga konkretnego pliku, jawnego confirm i exact preflightu jednego kroku. Uruchomienie migratora nie zastępuje osobnej zgody właściciela, quiescence ani backupu. Produkcyjna baza nie została nimi zmigrowana.

Migracja produkcji `0009→0014`, nowy baseline, inicjalizacja pięciu flag, niezależny review QP-01/trwałego wyniku migracji, review LA-01-R1/LA-02/LA-03 oraz niezależny re-review naprawy NIA-P2-RV-01…05 są zakończone. Etap 1 został formalnie zamknięty przez właściciela 2026-07-17 na podstawie werdyktu `APPROVE WITH MINOR/P2` (zero MAJOR/CRITICAL); wykonano jeden kontrolowany live durable single flow z twardym capem, `max_retries=0`, dokładnie jednym jobem i jednym requestem. Browser, publikacja, FetchPort, content pipeline, panel FastAPI, autonomia, interakcje, analytics i Etap 2+ nie należały do tego kryterium.
- Niezbudowane: durable realne A1/A2/B, realne resume, artykuły/Notes, approval/autonomia, publikacja (Playwright), interakcje, analityka i panel.
- Zero publikacji na Substacku; miesięczny ledger: `1.012590 USD` z limitu 40 USD.

## Formalne przyjęcie bramki positive-live (2026-07-18)

Niezależny review nie uruchamiał ponownie pełnych 1288 testów: wykonał własne wąskie `223/223`, potwierdził exact-once i bajtową identyczność kodu/testów z wcześniej zaakceptowanym pełnym baseline'em, a następnie wydał `APPROVE`. Właściciel formalnie przyjął bramkę w ADR-095. Sześć P2 ADR-094 pozostaje nieblokującym backlogiem, w tym ryzyko ponownego dryfu liczby testów w README mimo synchronizacji bieżącej wartości. Przyjęcie bramki nie rozpoczyna Etapu 2 i nie upoważnia do nowego requestu ani działania publicznego.

## Historyczna aktualizacja controlled-live po review LA-03 (2026-07-17)

Review potwierdził 1181/1181, dokładnie jeden realny request, `max_retries=0`, brak attemptu #2, jedno usage i settlement oraz pełny powrót fail-closed. Wskazał trzy P2: nadpisywanie raportu przy deterministycznym `session_id`, nieaktualny README oraz ukryty fallback `quiescence_probe=None` po otwarciu storage.

Pierwszy pakiet P2 został odrzucony w niezależnym review jako `REJECT — MAJOR`. Zamknięta fala naprawcza NIA-P2-RV-01…05 zachowuje każdy raport w pliku `<session_id>--<attempt/timestamp/invocation>.json`, wymaga jawnego zamrożonego payloadu pre-storage, waliduje score przed konwersją, akceptuje wyłącznie literalny fence `json`, sanitizuje diagnostic i raport jednym rekurencyjnym mechanizmem oraz atomowo utrwala diagnostykę. Enqueue i controlled-live test używają jednego jawnego czasu. Dowód: 1235/1235 i exact-once `294+299+311+331`, wyłącznie fake/temp DB, koszt `0.000000 USD`. Status: niezależny re-review wydał `APPROVE WITH MINOR/P2`, na tej podstawie właściciel formalnie zamknął Etap 1 (ADR-088). Dwa nieblokujące MINOR/P2 parsera (`RV-R2-P2-1`, `RV-R2-P2-2`) przeniesiono do backlogu Etapu 2. Zamknięcie nie autoryzuje nowego requestu.

## Formalne zamknięcie WAVE 1A (2026-07-16; zapis historyczny)

Implementer zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`. Niezależny finalny re-review odtworzył 1036/1036, cztery partycje exact-once, `compileall` i `git diff --check`, a także wykonał własne kontrpróby: 149/149 przez prawdziwy `Worker.run_once`, 36/36 SQLite floor oraz 30/30 recovery/reaper/crash-window. Werdykt `APPROVE WITH MINOR/P2` został przyjęty przez właściciela, który formalnie ustawił WAVE 1A na `CLOSED — APPROVED WITH P2`. Pozostają P2-1 (fingerprint mismatch: fail-closed, widoczny operatorowi, bez przepisywania intentu i bez retry) oraz P2-2 (atomowy StoragePort i spójny stan SQLite nie dowodzą pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel). Etap 1 pozostaje `BLOCKED`, live API `ZABRONIONE`; Etap 2 nie został rozpoczęty.

## Historyczna aktualizacja implementacji WAVE 1A (2026-07-15–2026-07-16)

> **Nowsza aktualizacja `W1A-R4-01` (2026-07-16):** czwarty niezależny review odtworzył `job=FAILED` + `attempt=REQUEST_STARTED` po lokalnym błędzie Workera. Centralna operacja StoragePort atomowo terminalizuje tylko bez active attemptu, a `RESERVED`/`REQUEST_STARTED` eskaluje do widocznego `NEEDS_RECONCILIATION`, zachowując rezerwację i zabraniając retry. Triggery SQLite blokują obejście przez terminalne job/run/research_run. P2-1 pozostaje fail-closed; P2-2 oznacza trwały floor SQLite, nie dowód pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel. Walidacja: **1036/1036**, partycje 248+253+267+268, race 38×30, krytyczne pliki i QA ×10, niezmieniona chroniona baza. WAVE nadal otwarta; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

WAVE 0B jest formalnie **`CLOSED — APPROVED WITH P2`** po checkpointowym commicie `c25e1254044d89c7703a6614e9ee831eb226e87c`. WAVE 1A jest wyłącznie **`CANDIDATE — AWAITING INDEPENDENT REVIEW`** po naprawie odrzucenia `REJECTED — MAJOR`: migracja `0014` poprawiona in place (append-only `reconciliation_events`, pełny kontrakt stanów i surowe wymuszenia SQLite), lokalny resolver L1 oraz CLI rozdzielają finansowe i wykonawcze skutki `NEEDS_RECONCILIATION`. `MANUAL_REVIEW_REMAINS_REQUIRED` jest dozwolone tylko z `CHARGE_UNKNOWN` (brak dead-endu). Istniejący `model_usage` akceptowany po pełnej tożsamości; `RESULT_ALREADY_FINALIZED` wymaga wyłącznej Research Card. `model_usage` pozostał jedynym ledgerem kosztu; niezmienna spójność ledger↔cache; nie ma auto-retry, attemptu #2 ani wywołania providera. CLI preview/confirm używa version tokenu. Walidacja tej historycznej iteracji: **1007 testów**, 14 migracji (`0001`–`0014`), niezmieniona chroniona baza. Historyczne 919/894/948/955/980/982 są wcześniejszymi iteracjami. Poprawka `W1A-VERIFY-01` (ADR-064): resolver `EXECUTION_FAILED` akceptuje maintenance-`STOPPED` run i atomowo doprowadza `STOPPED → FAILED` (bez wskrzeszenia, `DONE` ani attemptu #2); +7 deterministycznych testów, flaky node 30/30. Poprawka `W1A-VERIFY-02` (ADR-065): pełna walidacja lineage — foreign `runs.account_id`/`workflow=ANALYTICS` był wcześniej fail-open i nie był objęty 955/955; teraz aplikacja + version token v2 + trigger SQLite wymuszają zgodność account/workflow/topic/flow/kind/intent (każda niespójność = fail-closed, zero mutacji); +25 testów lineage (`tests/test_reconciliation_lineage.py`, `scripts/qa/reconciliation_lineage_disproof.py`). Pełny audyt software-assurance working tree (2026-07-16): trzy MINOR naprawione (kontrolowane exit codes `list-reconciliations`, usunięte martwe pole `version_token` wyniku resolvera, anotacja `actual_cost_usd`); W1A-AUD-04 sklasyfikowany wtedy jako P2 report-only. **Trzecie niezależne review = `REJECTED — MAJOR` (2026-07-16):** W1A-AUD-04 przeklasyfikowany na MAJOR (stuck `RESERVED`/`REQUEST_STARTED` po crashu = niewidoczny, nierozstrzygalny, wieczna rezerwacja), plus W1A-SQLITE-01 (surowa terminalizacja bez pełnego lifecycle/eventu) i W1A-SQLITE-02 (mutowalny/kasowalny kanon po settlement). **Fala naprawcza (autoryzowana):** recovery eskaluje oba crash-windows do `NEEDS_RECONCILIATION` z enumerowanym powodem (`LEASE_EXPIRED_BEFORE/AFTER_REQUEST_STARTED`) i append-only eventem `AUTO_ESCALATION`; attempt, który nigdy nie osiągnął `REQUEST_STARTED`, może być rozstrzygnięty wyłącznie `NOT_CHARGED`; resolver flipuje attempt jako OSTATNIĄ mutację, a triggery 0014 (in-place) wymagają przy terminalizacji zgodnego eventu `FINAL_RESOLUTION`, terminalnego spójnego lifecycle ze zwolnioną rezerwacją i cache'ów równych kanonowi; kanoniczny `model_usage` i oba cache są niezmienne po terminalu; pełna obsługa błędów CLI `list-reconciliations` (3/6 dla open/query/close); QA script sprząta katalogi tymczasowe z twardą kontrolą w exit code. +25 trwałych testów (eskalacja H1–H20, raw-SQLite I, ciek QA); **982 → 1007**. Historyczne 919/894/948/955/980/982 są historyczne. Etap 1 nadal `BLOCKED`, live API `ZABRONIONE`.

## Uruchomienie

```bash
pip install -e .[dev]           # + .[llm] tylko do realnych wywołań API
python -m pytest                # 1474 testy, bez sieci
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
- Realny koszt jest autorytatywnie definiowany wyłącznie przez `config/pricing_profiles.yaml` (profil `status: approved`), NIE przez `.env`. Właściciel musi ręcznie zatwierdzić ceny i model przed realnym uruchomieniem; ceny nie są pobierane z internetu.
- Kontrolowany live acceptance przechodzi wyłącznie przez `python -m app.main controlled-live-once`. Ostatnia autoryzacja została zużyta przez dokładnie jeden request; job jest terminalnie `DONE/max_attempts=1` i nie może być ponawiany. Formalne przyjęcie bramki positive-live nie jest nową autoryzacją. Bieżący gate jest `False`, flags fail-closed, a każdy przyszły realny request wymaga nowej jawnej decyzji właściciela i nowej durable identity.
- Repozytorium jest PRIVATE (ADR-021); jawność AI reguluje ADR-018.
