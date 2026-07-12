# CURRENT_PROJECT_STATE — Nothing Is Accidental Agent

> **STATUS: JEDYNY OBOWIĄZUJĄCY OBRAZ STANU PROJEKTU.**
> Data weryfikacji: **2026-07-12** (`python -m pytest` → **286 passed** offline; Tasks 1–6 Etapu 0 ukończone; źródłowa baza niezmieniona).
> Architektura: `MASTER_ARCHITECTURE.md` · Kolejność prac: `IMPLEMENTATION_ROADMAP.md`.
> Aktualizować przy każdej zmianie stanu modułu; statusy tylko z zestawu: `NOT_STARTED / SKELETON / PARTIAL / WORKING / VERIFIED / BLOCKED / DEPRECATED`. `VERIFIED` wyłącznie dla kodu URUCHOMIONEGO i przetestowanego.

## Liczby kontrolne (zweryfikowane)

- Testy: **286 passed** (offline, deterministyczne, bez sieci; w tym parser i klient tematów, koszt parse-error, Tasks 1–5 oraz izolacja kont). Gałąź: `dev/first-successful-research-card`.
- Realny koszt projektu: **0,500616 USD** (6 wpisów `model_usage` z `dry_run=0`; limit miesięczny 40 USD → wykorzystane 1,25%).
- Realne próby researchu: **3** (+1 diagnostyka pojedynczego źródła) — **0 ukończonych Research Card na żywym API** (1 karta istnieje wyłącznie z dry_run).
- Baza źródłowa nie była modyfikowana: runs = 4×DRY_RUN + 3×FAILED (zero osieroconych RUNNING); research_runs = 1×FAILED, 1×PARTIAL (`9bbeb020`). Kod Task 3 daje po migracji bezpłatną, jawną drogę retry, ale jej nie uruchomiono.
- Publikacje na Substacku: **0** (fizycznie zablokowane przez `DisabledBrowser`).

## Tabela stanu modułów

| Moduł | Status | % | Co działa | Co nie działa / znane błędy | Testy | Ostatnia weryfikacja | Następny krok |
|---|---|---|---|---|---|---|---|
| Konfiguracja (`app/core/config.py`) | VERIFIED | 90 | .env+YAML, zero ścieżek absolutnych, fallback na *.example | kill-switch czytany raz przy starcie (runtime — Etap 1) | pośrednie (fixtures) | 2026-07-12 | bez zmian do Etapu 1 |
| Modele domenowe (`app/models.py`) | VERIFIED | 92 | wszystkie enumy/modele zbudowanej części; `TopicStatus.USED` aktywny po COMPLETE | `RunStatus.STOPPED` — martwa wartość | tak | 2026-07-12 | bez zmian w Task 6 |
| Storage SQLite + 7 migracji | VERIFIED | 97 | repozytoria, flow, WAL/busy timeout, atomowy koszt, claim A2 oraz atomowa finalizacja run–topic–card | starsze migracje bez transakcji; `mark_*` poza nowymi przejściami bez pełnej walidacji stanu poprzedniego | storage + flow + candidate attempts + finalization | 2026-07-12 | Etap 0 zad. 8 |
| Policy Engine | PARTIAL | 40 | kill-switch (statyczny), active, centralny `check_run_budget` z capem runu oraz budżetem D/M (miesięczny nadrzędny), progi tematów | brak: autonomy_level, AccountMode, limity AccountPolicy, cooldowny, SAFE MODE | test_policy_engine + research_run_budget | 2026-07-12 | reszta Etap 4 |
| UsageTracker (koszty) | VERIFIED | 95 | model_usage+COSTS.csv, dry_run flaga, koszt przy błędach researchu | równoległy append CSV nieodporny (przyszły worker) | tak + 3 realne runy | 2026-07-12 | eksport z DB przy Etapie 8 |
| ModelRouter | VERIFIED | 90 | zadanie→model z .env | scripts omijają router (P2-8) | tak | 2026-07-12 | P2-8 przy Etapie 0/1 |
| FakeLLMClient / FakeResearchClient | VERIFIED | 100 | deterministyczne dry_run/testy, scenariusze brzegowe | — | tak | 2026-07-12 | — |
| AnthropicLLMClient (tematy) | WORKING | 85 | odpowiedź→Usage→parse; pojedynczy zewnętrzny code fence; typowane provider/parse/schema errors; usage parse-error księgowane raz przez workflow | **nigdy nie uruchomiony realnie (NOT VERIFIED live)** | parser + klient SDK fake + workflow SQLite | 2026-07-12 | realny run tematów wyłącznie za osobną zgodą |
| AnthropicResearchClient (3 generacje metod) | WORKING | 88 | retry timeout-only z callbackiem budżetowym przed każdą próbą; usage timeoutu zapisywane przed retry, jeśli dostępne; capy i diagnostyka | `timeout-billed-unrecorded`; A2 = search-o-URL, nie fetch treści (P0-2c → Etap 2); B **NOT VERIFIED live** | tak (wstrzykiwane callery) | 2026-07-12 | Etap 2 |
| Estymator kosztów | VERIFIED | 85 | conservative+expected z 2 realnych obserwacji, margines ≥50% | dwie kalibracje (legacy z cennika vs staged stałe) — P2-1; kalibracja n=2 | tak | 2026-07-12 | ujednolicić przy Etapie 2 |
| Workflow tematów + dedup | VERIFIED | 90 | pełny przepływ dry_run, dedup lokalny, progi, SUCCESS-fix | realny run tematów nigdy nie wykonany | tak | 2026-07-12 | realny run po Etap 0 zad. 6 |
| Research staged A1/A2/B + resume | WORKING | 93 | flow, koszt, atomowy claim A2, jawny retry, pełna finalizacja COMPLETE+run+USED i fail-closed guard przed klientem | jawny recovery niepewnego A2 oraz race dwóch świeżych runów pozostają przyszłą decyzją; `research_runs.total_cost_usd` nadal cache; **cała ścieżka bez sukcesu na żywym API** | staged + candidate attempts + finalization + CLI | 2026-07-12 | Etap 0 zad. 7–8, potem (za osobną zgodą) run ADR-022 = zad. 9 |
| Research legacy (single, two-stage) | WORKING | 100 | działa, 24 testy | NIEZALECANY (ADR-016→020); do DEPRECATED po sukcesie staged live | tak | 2026-07-12 | Etap 2 zad. 6 |
| Walidacja + injection guard | VERIFIED | 90 | deterministyczna bramka, min_verified_sources, neutralizacja injection | wzorce EN-only (P2-7) | tak | 2026-07-12 | rozszerzenie przy Etapie 2 |
| Diagnostyka odpowiedzi | VERIFIED | 95 | raw+stop_reason per etap, potwierdzona na żywo | nadpisuje poprzednią próbę tego samego etapu (P2-13, świadome) | tak | 2026-07-12 | — |
| CLI `app/main.py` + runner | VERIFIED | 85 | run-topics, run-research (dry), blokada `--real` (P0-3) | docelowo jedyne wejście — scripts do wchłonięcia (Etap 1) | tak | 2026-07-12 | — |
| `scripts/run_capped_research.py` | VERIFIED | 94 | pre-flight deleguje do `PolicyEngine.check_run_budget`; estymata obejmuje `1+max_retries`; estimate-only bez klienta; resume uwzględnia zapisany usage | `--max-sources 0` znaczy „wszyscy" (P2-15) | black-box CLI + budget delegation | 2026-07-12 | bez zmian w Task 6 |
| Porty: Storage/Notification | VERIFIED / WORKING | 90/70 | kontrakty + adaptery używane wszędzie | — | pośrednie | 2026-07-12 | — |
| Porty: SecretStore/FileStore | SKELETON | 20 | kod adapterów istnieje | **martwy kod — zero wywołań** (config używa os.getenv wprost) | brak | 2026-07-12 | podpiąć w Etapie 8 (lub usunąć decyzją) |
| Porty: Browser/Scheduler | SKELETON | 10 | celowe stuby; DisabledBrowser blokuje każdą akcję | to zabezpieczenie, nie brak | — | 2026-07-12 | Etap 1 (scheduler), Etap 5 (browser) |
| Tabele bez kodu (content_items, interactions, target_items, approvals, metrics_daily, screenshots) | SKELETON | 5 | schemat od migracji 0001 | żaden kod ich nie dotyka | — | 2026-07-12 | Etapy 3–7 |
| Task queue / workers / scheduler | NOT_STARTED | 0 | — | — | — | — | Etap 1 |
| Content pipeline (artykuły/Notes) | NOT_STARTED | 0 | — | — | — | — | Etap 3 |
| Approval/autonomy + panel FastAPI | NOT_STARTED | 0 | — | — | — | — | Etap 4 |
| Publishing (Playwright/Substack) | NOT_STARTED | 0 | — | — | — | — | Etap 5 |
| Interakcje (komentarze/odpowiedzi) | NOT_STARTED | 0 | — | — | — | — | Etap 6 |
| Analytics + strategy engine | NOT_STARTED | 0 | — | — | — | — | Etap 7 |
| Backend API / frontend | NOT_STARTED | 0 | — | (panel = Etap 4; poza nim brak frontendu w planie MVP) | — | — | Etap 4 |

## Aktualne blokery

1. **Ukończenie zadania 8 Etapu 0** (`IMPLEMENTATION_ROADMAP.md`) — Tasks 1–7 są ukończone; walidacja przejść `mark_*` musi zostać wdrożona, przetestowana i udokumentowana przed kolejnym płatnym uruchomieniem.
2. **Run `9bbeb020` pozostaje niezmieniony w źródłowej bazie** — po migracji jego historyczne `EXTRACTION_FAILED` dostaną konserwatywną dolną granicę `attempts=1`; legalna droga prowadzi wyłącznie przez jawną komendę retry i nie jest uruchamiana przez zwykłe resume.
3. **Etap B syntezy nigdy nie wykonany na żywym API** — ostatni niezweryfikowany element ścieżki researchu; zostanie zweryfikowany dopiero przy zadaniu 9 Etapu 0.

## Ostatnie ważne decyzje

- **ADR-022 (PROPOSED):** konfiguracja pierwszego świeżego runu nastawionego na kompletną kartę (4 źródła = tolerancja 1 błędu; cap 0,55 USD) — do wykonania jako zadanie 9 Etapu 0, PO ukończeniu zadań 1–8 i za osobną zgodą właściciela.
- **ADR-021:** repo GitHub PRIVATE, main stabilny + branche dev.
- **ADR-020:** research staged A1/A2/B; **ADR-019:** trwałość etapów; **ADR-017/018:** cel = pełna autonomia operacyjna + anonimowa marka redakcyjna bez proaktywnego ujawniania AI (NO_REPLY, zero impersonacji).
- **2026-07-12 (ten audyt):** konsolidacja dokumentacji do 3 dokumentów źródła prawdy; stare plany w `docs/archive/superseded_plans/` (ADR-023).

## Etapy

- **Aktywny etap roadmapy:** Etap 0 — Stabilizacja (zadania 1–9).
- **Ostatni ukończony krok:** Etap 0 / zadanie 7 — ADR-001/002/003/005/006 zweryfikowane jako zgodne, wdrożone i niezastąpione, po czym ich status zmieniono z `PROPOSED` na `ACCEPTED`; historyczną numerację publikacji w ADR-005 zmapowano na aktualny Etap 5; **286 testów**, zero zmian kodu, zero API i koszt 0 USD.
- **Następne trzy zadania:**
  1. Walidacja przejść stanów `mark_*`.
  2. Realny run ADR-022 wyłącznie za osobną zgodą właściciela.
  3. Etap 1 dopiero po spełnieniu kryterium zakończenia Etapu 0.

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
