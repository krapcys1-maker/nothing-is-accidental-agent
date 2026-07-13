# CURRENT_PROJECT_STATE — Nothing Is Accidental Agent

> **STATUS: JEDYNY OBOWIĄZUJĄCY OBRAZ STANU PROJEKTU.**
> Data weryfikacji: **2026-07-13** (`python -m pytest` → **454 passed**; Etap 0 zamknięty, a blockery typed-provider-error/retry i atomowej finalizacji staged B są wdrożone offline i oczekują na niezależne review; scheduler/jobs/workery nierozpoczęte).
> Architektura: `MASTER_ARCHITECTURE.md` · Kolejność prac: `IMPLEMENTATION_ROADMAP.md`.
> Aktualizować przy każdej zmianie stanu modułu; statusy tylko z zestawu: `NOT_STARTED / SKELETON / PARTIAL / WORKING / VERIFIED / BLOCKED / DEPRECATED`. `VERIFIED` wyłącznie dla kodu URUCHOMIONEGO i przetestowanego.

## Liczby kontrolne (zweryfikowane)

- Testy: **454 passed** (offline, deterministyczne, bez sieci; typed-provider-error/retry/audit oraz atomowa staged B: karta+źródła+SUCCESS+COMPLETE+terminalny run+USED, typowane tryby fresh/resume/force, CAS, trwały marker force, 13 crash points po reopen i dwie równoległe SQLite connections). Terminalny no-op COMPLETE ponownie waliduje mode i trwały snapshot resume, więc nie przyjmuje sprzecznego kontekstu; publiczne finalizery legacy odrzucają każdy `staged`, a `finish_run` staged sukces. Gałąź: `dev/first-successful-research-card`.
- Realny koszt projektu: **0,684580 USD** (13 wpisów `model_usage` z `dry_run=0`; Task 9 łącznie **0,183964 USD**, w tym resume B **0,013914 USD**; limit miesięczny 40 USD → wykorzystane 1,71%).
- Realne próby researchu: **4** (+1 diagnostyka pojedynczego źródła) — **1 ukończona Research Card na żywym API** (oraz 1 dry_run). Karta realna #2 ma rekomendację jakościową REJECT i nie przechodzi do treści.
- Baza po kontrolowanym resume Task 9: runs = 4×DRY_RUN + 3×FAILED + 1×SUCCESS (`c01171bc`); research_runs = 2×COMPLETE (1 dry-run, 1 real), 2×FAILED i 1×PARTIAL (`9bbeb020`). Run `c01171bc` ma kartę #2, 4×EXTRACTED/VERIFIED, topic USED, 7 usage i koszt 0,183964 USD; drugie B zakończyło się `end_turn` bez retry.
- Publikacje na Substacku: **0** (fizycznie zablokowane przez `DisabledBrowser`).

## Tabela stanu modułów

| Moduł | Status | % | Co działa | Co nie działa / znane błędy | Testy | Ostatnia weryfikacja | Następny krok |
|---|---|---|---|---|---|---|---|
| Konfiguracja (`app/core/config.py`) | VERIFIED | 90 | .env+YAML, zero ścieżek absolutnych, fallback na *.example | kill-switch czytany raz przy starcie (runtime — Etap 1) | pośrednie (fixtures) | 2026-07-12 | bez zmian do Etapu 1 |
| Modele domenowe (`app/models.py`) | VERIFIED | 92 | wszystkie enumy/modele zbudowanej części; `TopicStatus.USED` aktywny po COMPLETE | `RunStatus.STOPPED` — martwa wartość | tak | 2026-07-12 | bez zmian w Task 6 |
| Storage SQLite + 8 migracji | VERIFIED | 99 | repozytoria, flow, WAL/busy timeout, atomowy koszt, claim A2, finalizacja run–topic–card oraz warunkowe przejścia statusów z kontrolą `rowcount`; `0008` utrwala force per staged run | starsze migracje bez transakcji; brak helperów dla przyszłych tabel | storage + flow + candidate attempts + finalization + status transitions/race | 2026-07-13 | niezależne review F4 |
| Policy Engine | PARTIAL | 40 | kill-switch (statyczny), active, centralny `check_run_budget` z capem runu oraz budżetem D/M (miesięczny nadrzędny), progi tematów | brak: autonomy_level, AccountMode, limity AccountPolicy, cooldowny, SAFE MODE | test_policy_engine + research_run_budget | 2026-07-12 | reszta Etap 4 |
| UsageTracker (koszty) | VERIFIED | 95 | model_usage+COSTS.csv, dry_run flaga, koszt przy błędach researchu; Task 9: 7 wpisów i 0,183964 USD zgodne z cache runu | równoległy append CSV nieodporny (przyszły worker) | tak + 4 realne runy + resume B | 2026-07-13 | eksport z DB przy Etapie 8 |
| ModelRouter | VERIFIED | 90 | zadanie→model z .env | scripts omijają router (P2-8) | tak | 2026-07-12 | P2-8 przy Etapie 0/1 |
| FakeLLMClient / FakeResearchClient | VERIFIED | 100 | deterministyczne dry_run/testy, scenariusze brzegowe | — | tak | 2026-07-12 | — |
| AnthropicLLMClient (tematy) | WORKING | 85 | odpowiedź→Usage→parse; pojedynczy zewnętrzny code fence; typowane provider/parse/schema errors; usage parse-error księgowane raz przez workflow | **nigdy nie uruchomiony realnie (NOT VERIFIED live)** | parser + klient SDK fake + workflow SQLite | 2026-07-12 | realny run tematów wyłącznie za osobną zgodą |
| AnthropicResearchClient (3 generacje metod) | VERIFIED | 98 | A1 i 4×A2 oraz resume B potwierdzone live; SDK mapuje timeout, connection, 429, 4xx, 5xx i unknown; retry tylko jawna lista transient po callbacku budżetowym; audit zachowuje typ/status/retryable/stop_reason bez SDK body i z redakcją Bearer | P2-19 `timeout-billed-unrecorded`; A2 = search-o-URL, nie fetch treści | 411 offline + realny Task 9 + resume B | 2026-07-13 | niezależne review kontraktu błędów przed płatnymi workerami |
| Estymator kosztów | VERIFIED | 85 | conservative+expected z 2 realnych obserwacji, margines ≥50% | dwie kalibracje (legacy z cennika vs staged stałe) — P2-1; kalibracja n=2 | tak | 2026-07-12 | ujednolicić przy Etapie 2 |
| Workflow tematów + dedup | VERIFIED | 90 | pełny przepływ dry_run, dedup lokalny, progi, SUCCESS-fix | realny run tematów nigdy nie wykonany | tak | 2026-07-12 | realny run po Etap 0 zad. 6 |
| Research staged A1/A2/B + resume | VERIFIED | 99 | realny A1 + 4×A2 + B; failure zachował SOURCES_COMPLETE, repair naprawił audit, resume dał COMPLETE/SUCCESS/USED; typed error ma identyczny bezpieczny format w run/research_run/stage/candidate audit bez SDK body i sekretów; finalizacja B używa trwałego force i CAS, a wyłącznie `finalize_staged_research_with_card` może zapisać staged COMPLETE/SUCCESS/B SUCCESS/USED z kosztem z `model_usage`; legacy finalizery i `finish_run` nie mogą oznaczyć staged sukcesu | karta #2 jakościowo REJECT; `research_runs.error` zachował historyczny parse-error (P2-20) | 454 offline + Task 9 live + repair + resume | 2026-07-13 | niezależne review; scheduler/jobs/workery osobnym zadaniem |
| Research legacy (single, two-stage) | WORKING | 100 | działa, 24 testy | NIEZALECANY (ADR-016→020); do DEPRECATED po sukcesie staged live | tak | 2026-07-12 | Etap 2 zad. 6 |
| Walidacja + injection guard | VERIFIED | 90 | deterministyczna bramka, min_verified_sources, neutralizacja injection | wzorce EN-only (P2-7) | tak | 2026-07-12 | rozszerzenie przy Etapie 2 |
| Diagnostyka odpowiedzi | VERIFIED | 95 | raw+stop_reason per etap, potwierdzona na żywo | nadpisuje poprzednią próbę tego samego etapu (P2-13, świadome) | tak | 2026-07-12 | — |
| CLI `app/main.py` + runner | VERIFIED | 85 | run-topics, run-research (dry), blokada `--real` (P0-3) | docelowo jedyne wejście — scripts do wchłonięcia (Etap 1) | tak | 2026-07-12 | — |
| `scripts/run_capped_research.py` | VERIFIED | 94 | pre-flight deleguje do `PolicyEngine.check_run_budget`; estymata obejmuje `1+max_retries`; estimate-only bez klienta; resume uwzględnia zapisany usage | `--max-sources 0` znaczy „wszyscy" (P2-15) | black-box CLI + budget delegation | 2026-07-12 | bez zmian w Task 6 |
| Porty: Storage/Notification | VERIFIED / WORKING | 90/70 | kontrakty + adaptery używane wszędzie | — | pośrednie | 2026-07-12 | — |
| Porty: SecretStore/FileStore | SKELETON | 20 | kod adapterów istnieje | **martwy kod — zero wywołań** (config używa os.getenv wprost) | brak | 2026-07-12 | podpiąć w Etapie 8 (lub usunąć decyzją) |
| Porty: Browser/Scheduler | SKELETON | 10 | celowe stuby; DisabledBrowser blokuje każdą akcję | to zabezpieczenie, nie brak | — | 2026-07-12 | Etap 1 (scheduler), Etap 5 (browser) |
| Tabele bez kodu (content_items, interactions, target_items, approvals, metrics_daily, screenshots) | SKELETON | 5 | schemat od migracji 0001 | żaden kod ich nie dotyka | — | 2026-07-12 | Etapy 3–7 |
| Task queue / workers / scheduler | NOT_STARTED | 0 | poprzedzający je kontrakt typed-provider-error/retry jest gotowy offline | brak tabel, lease, jobów, workerów i runtime scheduler | kontrakt klienta: tak | 2026-07-13 | dopiero po niezależnym review blockera |
| Content pipeline (artykuły/Notes) | NOT_STARTED | 0 | pełny snapshot Fable + blueprint: Article Brief, A1–A9, N1–N16 dry-run, audyty, SEO i diversity memory | brak kodu, migracji i generatorów; raport/blueprint nie są wdrożeniem, a kosztorysy są niewalidowane | — | 2026-07-13 | Etap 3 po Etapach 1–2 |
| Approval/autonomy + panel FastAPI | NOT_STARTED | 0 | — | — | — | — | Etap 4 |
| Publishing (Playwright/Substack) | NOT_STARTED | 0 | — | — | — | — | Etap 5 |
| Interakcje (komentarze/odpowiedzi) | NOT_STARTED | 0 | dokumentacyjny podział: publiczne Notes, K1–K8, odpowiedzi/restacki w Etapie 6 | brak kodu i akcji publicznych | — | 2026-07-13 | Etap 6 |
| Analytics + strategy engine | NOT_STARTED | 0 | dokumentacyjne definicje oddzielnych metryk i `is_estimated` | brak kolektora, atrybucji, eksperymentów i strategy engine | — | 2026-07-13 | Etap 7 |
| Backend API / frontend | NOT_STARTED | 0 | — | (panel = Etap 4; poza nim brak frontendu w planie MVP) | — | — | Etap 4 |

## Aktualne blokery

Brak blockerów Etapu 0 — kryterium zakończenia spełnione. P1 polegające na mapowaniu wszystkich wyjątków `messages.create` na retryowalny timeout zostało naprawione offline jako pierwszy warunek przed płatnymi workerami Etapu 1 i oczekuje na niezależne review. Karta #2 ma `publication_recommendation=REJECT`, więc nie może zasilić przyszłego content pipeline bez poprawy dowodów. Historyczny run `9bbeb020` i P2-20 pozostają długiem technicznym.

## Ostatnie ważne decyzje

- **ADR-022 (ACCEPTED / EXECUTED 2026-07-13):** właściciel zatwierdził dokładnie jeden świeży staged run z capem 0,55 USD. A1/A2 odniosły sukces, B zakończyło się `max_tokens`/parse-error; koszt 0,170050 USD; bez retry/resume.
- **2026-07-13 (jawna zgoda właściciela):** po osobnym repairze zatwierdzono dokładnie jeden resume wyłącznie B z absolutnym capem 0,20 USD i `max_retries=0`; wynik `end_turn`, karta #2, łączny koszt 0,183964 USD.
- **ADR-021:** repo GitHub PRIVATE, main stabilny + branche dev.
- **ADR-020:** research staged A1/A2/B; **ADR-019:** trwałość etapów; **ADR-017/018:** cel = pełna autonomia operacyjna + anonimowa marka redakcyjna bez proaktywnego ujawniania AI (NO_REPLY, zero impersonacji).
- **ADR-029:** retry błędów Anthropic jest dozwolone wyłącznie dla jawnie typowanych timeout/SDK-network/429/500/502/503/504; 400/401/403/404/422, unknown, parse, truncation i validation są terminalne dla próby.
- **Korekta ADR-031 po końcowym review F4:** COMPLETE nie omija kontraktu `StagedFinalizationContext`; terminalny no-op odrzuca sprzeczny fresh/force/resume mode oraz niezgodny CAS bez mutacji. `finalize_research_success` i `mark_research_run_complete` są legacy-only i odrzucają `staged` we wszystkich stanach, także COMPLETE i FAILED.
- **ADR-032–036 (ACCEPTED, wyłącznie dokumentacyjnie):** modularny system redakcyjny, prawo do `SKIP`, izolacja NIA/build logu, rozdzielenie follows i subscribers oraz Notes dry-run w Etapie 3/publiczne operacje w Etapie 6. Pełny snapshot Fable jest w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md`; wszystkie elementy wdrożeniowe pozostają PLANNED/NOT_STARTED.
- **2026-07-12 (ten audyt):** konsolidacja dokumentacji do 3 dokumentów źródła prawdy; stare plany w `docs/archive/superseded_plans/` (ADR-023).

## Etapy

- **Aktywny etap roadmapy:** Etap 1 — wyłącznie pierwszy blocker przygotowawczy klienta Anthropic; kod oczekuje na niezależne review. Scheduler, jobs, workery i rezerwacje budżetowe pozostają nierozpoczęte.
- **Ostatni ukończony krok:** Etap 0 / zadanie 9 — kontrolowany resume B dał pierwszą realną kompletną Research Card; **Etap 0 formalnie zakończony**.
- **Następne trzy zadania:**
  1. Niezależne review typowanego mapowania Anthropic i polityki retry; bez API.
  2. Po akceptacji osobne zadanie projektowe dla jobs/lease/system_flags i globalnych rezerwacji budżetowych.
  3. Nie uruchamiać płatnych workerów przed domknięciem pozostałych blockerów wykonawczych Etapu 1.

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
