# MASTER_ARCHITECTURE — Nothing Is Accidental Agent

> **STATUS: JEDYNE ŹRÓDŁO PRAWDY O ARCHITEKTURZE.**
> Data: 2026-07-12 · Wersja: 1.0 · Zastępuje: `ARCHITECTURE.md` (V1), `docs/IMPLEMENTATION_PLAN.md` (CZĘŚCI A–F), `docs/AUDYT_ARCHITEKTURY_2026-07-12.md`, `docs/architecture/SUBSTACK_INTEGRATION.md` — wszystkie przeniesione do `docs/archive/superseded_plans/`.
>
> Kolejność prac: `IMPLEMENTATION_ROADMAP.md`. Aktualny stan: `CURRENT_PROJECT_STATE.md`. Rejestr decyzji (ADR): `docs/DECISIONS.md` (nadal obowiązujący — ten dokument konsoliduje decyzje, nie zastępuje rejestru).
>
> Każde twierdzenie o stanie obecnym w tym dokumencie zostało zweryfikowane w kodzie, testach (127 passed, 2026-07-12) lub bazie `data/agent.db`. Twierdzenia niezweryfikowane oznaczono `NOT VERIFIED`.

---

## 1. Aktualny stan architektury (stan faktyczny kodu, nie planu)

### 1.1. Co istnieje i jest kompletne (uruchomione + przetestowane)

| Element | Pliki | Dowód |
|---|---|---|
| Konfiguracja (.env + YAML, zero ścieżek absolutnych) | `app/core/config.py` | testy + 3 realne runy |
| Modele domenowe (Pydantic v2) | `app/models.py` | testy |
| SQLite + 6 migracji + repozytoria | `app/storage/` | `tests/test_storage.py`, `tests/test_research_run_flow.py` i in. |
| Policy Engine (kill-switch, aktywność konta, budżet dzienny/miesięczny z priorytetem miesięcznym ADR-012, progi tematów) | `app/policies/policy_engine.py` | `tests/test_policy_engine.py` |
| Księgowanie kosztów (model_usage + COSTS.csv, flaga dry_run) | `app/llm/usage_tracker.py` | 3 realne incydenty potwierdziły poprawność |
| Pipeline tematów (generacja+scoring+dedup+progi) | `app/workflows/topics/` | testy; realnie NIGDY nie uruchomiony (`NOT VERIFIED` na żywym API) |
| Deduplikacja tematów (lokalna, bez kosztu, ADR-014) | `app/workflows/topics/dedup.py` | `tests/test_dedup.py` |
| Research etapowy A1/A2/B (ADR-020) + wznawialność po restarcie | `app/workflows/research/pipeline.py` | 12+ testów; na żywo: A1 ✅, A2 1× sukces (diagnostyka), B `NOT VERIFIED` na żywo |
| Bramka jakości researchu (deterministyczna, min_verified_sources) | `app/research/validation.py` | testy |
| Injection guard (treść źródeł = dane, nie polecenia) | `app/research/injection_guard.py` | testy |
| Kalibrowany estymator kosztów (2 realne obserwacje, margines ≥50%) | `app/research/cost_estimator.py` | testy + 3 realne runy |
| Diagnostyka surowych odpowiedzi (stop_reason wprost z API) | `app/research/diagnostics.py` | potwierdzona na żywo (Etap 1L) |
| CLI + jedyne bezpieczne wejście realnego researchu | `app/main.py`, `scripts/run_capped_research.py` | 3 realne użycia |
| Naprawy P0 z audytu 12.07 (SUCCESS-status, wymuszone UNVERIFIED, blokada `--real`) | pipeline, validation, runner | 7 testów regresyjnych |

### 1.2. Co jest częściowe

- **Policy Engine** — pokrywa ~3 z ~14 docelowych obowiązków. Brak: egzekucji `autonomy_level`, `AccountMode` (COMMENT_ONLY niczego nie blokuje), limitów per konto (`AccountPolicy` — martwa konfiguracja), cooldownów, capu per-run w bibliotece (żyje tylko w CLI), SAFE MODE, runtime kill-switch (czytany raz z .env przy starcie).
- **Klient Anthropic dla tematów** (`app/llm/anthropic_client.py`) — kompletny kod, ale: nigdy nie uruchomiony realnie, brak testów parsera, **nie księguje kosztu przy błędzie parsowania JSON** (w przeciwieństwie do klienta researchu), brak zdejmowania code fence. Do wyrównania z klientem researchu przed pierwszym realnym użyciem.
- **Maszyna stanów researchu** — Etap 0 / Task 1 ukończony: działa z jawnym, trwałym `research_runs.flow`, walidacją cross-flow i flow→status przed resume; `_detect_flow` nie istnieje. Nadal `EXTRACTION_FAILED` nie ma drogi powrotu (run `9bbeb020` trwale niedomykalny), a `runs.cost_usd` nie jest odświeżany w części ścieżek staged.

### 1.3. Co jest tylko szkieletem

- `BrowserPort` (`DisabledBrowser` — celowo blokuje każdą akcję), `SchedulerPort` (`StubScheduler`).
- Tabele bez żadnego kodu, który je czyta/pisze (schemat od migracji 0001): `content_items`, `interactions`, `target_items`, `approvals`, `metrics_daily`, `screenshots`.

### 1.4. Co jest błędne lub nieużywane (martwy kod)

- `EnvSecretStore` i `LocalFileStore` — zdefiniowane, zero wywołań w całym repo (config czyta `os.getenv` bezpośrednio).
- `TopicStatus.USED` — nigdy nie ustawiany (P1-6: brak guardu przed wielokrotnym płatnym researchem tego samego tematu).
- `RunStatus.STOPPED` — nigdy nie zapisywany (zarezerwowany dla przyszłego reapera).
- Legacy pipeline'y researchu (`run_research_pipeline` jednoetapowy, `run_two_stage_research_pipeline`) — działają i mają testy, ale są NIEZALECANE (ADR-016→020); do wygaszenia po pierwszym sukcesie staged na żywo.

### 1.5. Duplikacja logiki

- **Bramka budżetowa**: `PolicyEngine.check_budget` (biblioteka) vs `_preflight_stop` w `scripts/run_capped_research.py` (druga kopia sumowania budżetu + cap per-run istniejący TYLKO tam).
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
| **Scheduler** (`app/scheduler/`, przyszły) | tabela `jobs` + pętla workera; wybór zadania wg priority/earliest_run_at/deadline; okna redakcyjne | nie wykonuje akcji sam — deleguje do orchestratora | NOT_STARTED |
| **Task queue** | ta sama tabela `jobs` (kolejka = scheduler w SQLite, nie osobny system) | brak zewnętrznego brokera | NOT_STARTED |
| **Workers** | jeden proces workera; lease z wygasaniem; `kind='browser'` serializowany (jeden Chromium — inwariant) | brak puli procesów w MVP | NOT_STARTED |
| **Research engine** (`app/research/`, `app/workflows/research/`) | A1 discovery → A2 per-source extraction (z fetch treści — docelowo) → B synthesis; wznawialność; evidence | nie pisze artykułów; nie publikuje | WORKING |
| **Content planner** | wybór: artykuł vs Note, harmonogram treści z research cards PROCEED | nie generuje treści | NOT_STARTED |
| **Writing engine** (`app/workflows/content/`, przyszły) | draft artykułu/Note wg `instrukcja dla pisania artykulow/`; rewrite po audytach | nie publikuje; startuje ZAWSZE od bramki Policy | NOT_STARTED |
| **Quality scoring** | 3 deterministyczne audyty (fact/style/growth) + progi z configu; scoring gates dla autonomii | samoocena modelu nigdy nie jest jedyną bramką | NOT_STARTED |
| **Evidence & citation handling** | każde twierdzenie → źródło + `evidence_excerpt` (cytat z treści źródła po fetch); citable_numbers z kontekstem | wiedza modelu nie zastępuje dowodu (P0-2) | PARTIAL (twierdzenie→URL jest; excerpt brak) |
| **Memory** | SQLite jako pamięć trwała (topics/cards/content/metrics); brak osobnego vector-store w MVP | — | WORKING (w zakresie zbudowanym) |
| **Strategy engine** | analiza metryk → `strategy_decisions` (log) → korekty parametrów w configu, nigdy „po cichu" | nie zmienia polityk bezpieczeństwa | NOT_STARTED |
| **Analytics** | kolektor metryk → `metrics_daily`; estymacje jawnie oznaczane | — | NOT_STARTED (tabela czeka) |
| **Budget & cost control** | `model_usage` = JEDYNY kanon kosztu; PolicyEngine gate przed KAŻDYM płatnym wywołaniem; cap per-run w bibliotece | `runs.cost_usd`/`research_runs.total_cost_usd` = cache, nigdy podstawa decyzji | WORKING (cap per-run tylko w CLI — dług) |
| **Model provider abstraction** (`app/llm/`, `app/research/base.py`) | Protocole `LLMClient`/`ResearchClient`; `ModelRouter` (zadanie→model z .env); Fake dla dry_run | logika biznesowa nie zna nazw modeli ani SDK | WORKING (sekcja 6) |
| **Publication adapters** | `PublicationChannelPort` — wspólny kontrakt kanałów (sekcja 8) | rdzeń nie zna Substacka | NOT_STARTED |
| **Substack adapter** | Playwright, dedykowany profil per konto, ręczne logowanie (magic-link), screenshoty, stop-conditions | nigdy auto-login, nigdy zapis hasła, brak prywatnych endpointów | NOT_STARTED (projekt: sekcja 8.2) |
| **Approval & autonomy** | poziomy LEVEL_0–3 (ADR-017), macierz akcji×poziom, tabela `approvals`, SAFE MODE | autonomia dotyczy WYKONANIA, nie ujawniania natury agenta (ADR-018) | NOT_STARTED (specyfikacja: sekcja 7) |
| **Audit log** | `runs` + `research_stage_results` + `autonomous_decisions` (przyszła) + `HUMAN_INTERVENTIONS.md`; każda decyzja/koszt/błąd/interwencja zapisywalna | — | PARTIAL |
| **Retry system** | retry TYLKO błędów transient (timeout), twardy limit prób, re-check budżetu przed każdą próbą, estymata ×(1+retries); błąd parsowania NIGDY nie jest ponawiany | ŻADNEGO auto-retry publikacji (UNCERTAIN → człowiek/odczyt stanu) | PARTIAL (re-check budżetu przed retry — dług P1-3) |
| **Failure recovery** | stany trwałe w SQLite po każdym etapie; wznowienie po restarcie czyta BAZĘ, nie pamięć; reaper osieroconych RUNNING | — | WORKING dla researchu; reaper NOT_STARTED |
| **Configuration system** | `.env` (sekrety, modele, tryby) + `config/*.yaml` (polityki, wagi, limity); wartości NIGDY w kodzie | — | WORKING |
| **Secrets management** | `.env` + `.gitignore` (ADR-010); docelowo przez `SecretStorePort` (adapter istnieje, nieużywany — podpiąć zamiast `os.getenv`) | zero haseł Substacka gdziekolwiek | WORKING (adapter martwy — dług) |
| **Backend API / frontend** | panel FastAPI, localhost-only (ADR-009): readonly stan + approvals + kill-switch (flaga DB) | brak wystawiania na sieć publiczną w MVP | NOT_STARTED |
| **Database** | SQLite + migracje plikowe; WAL + busy_timeout (do włączenia); backup przed oknami publikacji | Postgres poza zakresem do czasu realnej współbieżności | WORKING |

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
`[P] check(action=CREATE_ARTICLE: mode+autonomy+limity) → planner wybiera kartę PROCEED → [$] draft (wg podręcznika stylu) → [$|lokalnie] 3 audyty: fact (każde twierdzenie vs evidence_excerpt karty), style (podręcznik + deterministyczne reguły), growth (tytuł/lead/struktura) → wynik < progu? → [$] rewrite (max N iteracji z configu) → [DB] content_items: DRAFT→PENDING_APPROVAL`

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
`discovery targetów (read-only) → scoring komentarza (specyfikacja D.5 ze starego planu — do przeniesienia do configu) → [P] check(COMMENT: daily_comment_limit, max_per_author_per_day, link_ratio) → generacja → approval wg poziomu → publikacja jak 3.6 → odpowiedzi czytelników: te same limity + zasada NO_REPLY dla pytań o tożsamość (ADR-018)`

### 3.8. Analiza wyników → zmiana strategii (DOCELOWE, Etap 7)
`kolektor metryk (read-only, Playwright) → [DB] metrics_daily (estymacje oznaczone) → tygodniowa analiza → [DB] strategy_decisions (problem→dane→decyzja→oczekiwany efekt) → korekta parametrów treści/harmonogramu w configu → NIGDY zmiana polityk bezpieczeństwa`

### 3.9. Obsługa błędów (OBOWIĄZUJE WSZĘDZIE)
- Timeout = transient → retry z twardym limitem; przed KAŻDĄ próbą ponowny `[P]` budżetu (docelowo — dziś dług P1-3).
- Błąd parsowania JSON = NIE-transient → zero retry, diagnostyka (surowa odpowiedź + stop_reason do `data/debug/`), run FAILED/PARTIAL.
- Każdy etap zostawia stan trwały w SQLite → wznowienie po restarcie zawsze z bazy.
- Kolejne błędy tej samej klasy ≥ progu → SAFE MODE (wejście automatyczne, wyjście TYLKO ręczne).

### 3.10. Rozliczanie kosztów — również nieudanych wywołań (ZBUDOWANE dla researchu)
Wyjątek `ResearchError` niesie `usage`/`model` z udanego wywołania API, którego wynik nie dał się sparsować → pipeline księguje koszt do `model_usage` ZANIM zwróci błąd. Potwierdzone na żywo 3×. **Ryzyko rezydualne (nieusuwalne):** timeout po stronie klienta może być zbilowany serwerowo bez lokalnego `usage` — mitygacja: `max_retries=0/1` + niskie capy. **Dług:** klient tematów nie ma tego mechanizmu (sekcja 1.2).

---

## 4. Model danych

Kanon: **`model_usage` = jedyne źródło prawdy o koszcie** (`dry_run=0` → budżet). `runs.cost_usd`, `research_runs.total_cost_usd` = cache. **Izolacja kont: `account_id` obowiązkowy w każdej encji per-konto.**

### 4.1. Encje istniejące (migracje 0001–0006)

| Encja | Przeznaczenie | Kluczowe pola | Statusy | Relacje / idempotencja |
|---|---|---|---|---|
| `accounts` + `account_policies` | publikacja/konto + jej limity (= **publication** w nomenklaturze docelowej) | id, mode, autonomy_level, active; limity dzienne/tygodniowe | mode: FULL_PUBLICATION/COMMENT_ONLY/DRAFT_ONLY/RESEARCH_ONLY | upsert po id (idempotentne `ensure_account`) |
| `topics` | temat (= **topic**) | account_id, title, question, score, score_breakdown, duplicate_of, rejection_reason | DISCOVERED→SCORED/SELECTED/REJECTED/DUPLICATE→USED | dedup lokalny per konto przed insertem |
| `runs` | przebieg workflow (= **audit event** poziomu runu) | id (uuid), workflow, status, cost_usd (cache), error | RUNNING→SUCCESS/FAILED/STOPPED; DRY_RUN | id generowany raz, przekazywany wszędzie |
| `research_runs` | maszyna stanów researchu (= **research task**); id = runs.id (rozszerzenie 1:1) | flow, status, stage_*_completed_at, research_card_id, error | patrz sekcja 5 | koszt przez model_usage.run_id — bez własnej tabeli kosztów |
| `research_source_candidates` | kandydat A1 ewoluujący w Source Card po A2 (= **source** + **claim** w postaci supported_claims_json) | url, title, supported_claims, numeric_facts, verification_status, quality, extraction_error | PENDING_EXTRACTION→EXTRACTED/EXTRACTION_FAILED | zapis NATYCHMIAST per źródło; wznowienie czyta tylko PENDING |
| `research_sources` | trwałe źródła STAREGO przepływu (legacy) | jak wyżej, bez statusu per źródło | — | do konsolidacji po wygaszeniu legacy |
| `research_cards` + `sources` | karta badawcza (= **research card**) + źródła finalne | question, working_thesis, confirmed/uncertain_claims, contradictions, confidence, recommendation | PROCEED/REVISE/REJECT (rekomendacja) | karta zapisywana też po odrzuceniu |
| `research_stage_results` | log KAŻDEJ próby etapu (= **retry**/**failure** log researchu) | stage (A/A1/A2/B), status, error | SUCCESS/FAILED | append-only |
| `model_usage` | wywołanie modelu (= **model call** + **cost record**) | run_id, task, tokeny, web_search_requests, estimated_cost_usd, dry_run | — | append-only; koszt zapisywany TAKŻE przy błędzie |
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
| `jobs` (= **publication job** i każde inne zadanie kolejki) | 1 | kind, account_id, payload_json, status (QUEUED/LEASED/DONE/FAILED/CANCELLED), priority, earliest_run_at, deadline_at, **idempotency_key UNIQUE**, lease_owner, lease_expires_at, attempts, last_error, schedule_reason |
| `system_flags` | 1 | kill-switch/SAFE MODE runtime (key, value, reason, updated_at) — czytane przy KAŻDYM checku Policy |
| `research_source_candidates.attempts` (kolumna) | 0 | jawny, capowany retry nieudanych kandydatów |
| `evaluations` (= **evaluation**) | 3 | wynik audytu treści: content_id, kind (fact/style/growth), score, findings_json |
| `autonomous_decisions` | 4 | log każdej decyzji podjętej bez człowieka: action, inputs, thresholds, outcome |
| `strategy_decisions` (= **strategy decision**) | 7 | data, problem, dane wejściowe, decyzja, oczekiwany efekt, wynik po fakcie |

### 4.3. Zasady idempotencji (obowiązujące)

1. Operacje płatne: nigdy nie powtarzaj automatycznie etapu, który zostawił trwały wynik (resume wykonuje wyłącznie NASTĘPNY etap).
2. Publikacja: `idempotency_key` + verify-before-publish + wynik UNCERTAIN nigdy nie jest retry'owany automatycznie.
3. Zapisy stanu: przejście statusu + dane w JEDNEJ transakcji (wzór: `mark_research_stage_a_success`).
4. Każde `mark_*` docelowo waliduje stan poprzedni (`WHERE status IN (...)` + liczba zmienionych wierszy) — dziś ślepy UPDATE (dług).

---

## 5. Maszyny stanów (dozwolone przejścia — inne są błędem)

```
runs.status:
  RUNNING → SUCCESS | FAILED | STOPPED          (DRY_RUN = osobny terminal dla dry_run)
  reaper (Etap 1): RUNNING starszy niż X bez żywego procesu → STOPPED(stale)

topics.status:
  DISCOVERED → SCORED | SELECTED | REJECTED | DUPLICATE
  SELECTED → USED   (po COMPLETE researchu — do wdrożenia w Etapie 0, P1-6)

research_runs.status (flow='staged'):
  DISCOVERY_PENDING → DISCOVERY_COMPLETE → EXTRACTION_IN_PROGRESS
    → SOURCES_COMPLETE ⇄ SYNTHESIS_PENDING → COMPLETE
    → PARTIAL            (są PENDING_EXTRACTION → wznawialne: wyłącznie A2)
    → PARTIAL_EXHAUSTED  (0 pending, EXTRACTED < min — TERMINAL; do dodania, P1-5)
  DISCOVERY_PENDING → FAILED (terminal)
  (flow='two_stage', legacy: PENDING → SOURCE_COLLECTED → COMPLETE | PARTIAL | FAILED)

research_source_candidates.status:
  PENDING_EXTRACTION → EXTRACTED | EXTRACTION_FAILED
  EXTRACTION_FAILED → PENDING_EXTRACTION   (TYLKO jawny retry, attempts < cap; do dodania, P1-5)

content_items.status (docelowe, Etap 3–5):
  DRAFT → PENDING_APPROVAL → APPROVED → QUEUED → PUBLISHING
    → PUBLISHED | UNCERTAIN | FAILED
  PENDING_APPROVAL → REJECTED (→ DRAFT po poprawkach)
  UNCERTAIN: wyjście WYŁĄCZNIE przez odczyt stanu lub człowieka — NIGDY auto-retry

jobs.status (docelowe, Etap 1):
  QUEUED → LEASED → DONE | FAILED       LEASED --(lease wygasł)--> QUEUED
  (joby publikacyjne po wygaśnięciu lease → NEEDS_VERIFICATION, nie ponowne wykonanie)

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
| Timeout | per klient (`timeout_seconds` z configu), traktowany jako transient | ZBUDOWANE |
| Retry | max_retries z configu; tylko transient; parse error NIGDY; docelowo re-check budżetu przed każdą próbą i estymata ×(1+retries) | CZĘŚCIOWE (P1-3) |
| Limit tokenów | `max_tokens` per wywołanie, per etap, z CLI/configu (A1=600, A2=1500, B=2200) — to REALNY limit kosztu w locie, nie estymata | ZBUDOWANE |
| Structured output | JSON/JSONL + parsery defensywne (`_strip_code_fence`, JSONL per linia — ucięta linia pomijana); walidacja pól z defaultami | ZBUDOWANE |
| Walidacja JSON | parse error → wyjątek z `usage`+`raw_text`+`stop_reason` → koszt zaksięgowany, diagnostyka zapisana | ZBUDOWANE (research); DŁUG (topics) |
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
- **Cap pojedynczej akcji:** `--max-cost-usd` per run (pesymistyczna estymata, margines ≥50%) — dziś tylko w CLI; do przeniesienia do `PolicyEngine.check_run_budget` (Etap 0). Realny limit w locie = `max_tokens` + `max_uses` (Anthropic nie przerywa wywołania po kwocie — udokumentowane wprost).
- **Limity publikacji/interakcji:** `AccountPolicy` (daily_comment_limit=5, daily_note_limit=2, weekly_article_limit=2, max_per_author_per_day=1, link_ratio) — skonfigurowane, egzekucja w Etapie 4 (PRZED generatorami treści, nie po).
- **Kill switch:** `KILL_SWITCH` w .env (sprawdzany przez PolicyEngine) — dziś snapshot przy starcie; docelowo flaga w `system_flags` czytana przy każdym checku (Etap 1).
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

Obowiązujące ADR-y: 001–022 (statusy PROPOSED dla 001/002/003/005/006 traktować jako ACCEPTED — wdrożone od tygodni; higiena statusów w Etapie 0). Kluczowe decyzje i nowe rozstrzygnięcia tego dokumentu:

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

---

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
