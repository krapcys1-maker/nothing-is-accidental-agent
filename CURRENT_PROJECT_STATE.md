# CURRENT_PROJECT_STATE — Nothing Is Accidental Agent

> **STATUS: JEDYNY OBOWIĄZUJĄCY OBRAZ STANU PROJEKTU.**
> Data weryfikacji: **2026-07-12** (pełny odczyt kodu + `python -m pytest` → **102 passed** + inspekcja `data/agent.db`).
> Architektura: `MASTER_ARCHITECTURE.md` · Kolejność prac: `IMPLEMENTATION_ROADMAP.md`.
> Aktualizować przy każdej zmianie stanu modułu; statusy tylko z zestawu: `NOT_STARTED / SKELETON / PARTIAL / WORKING / VERIFIED / BLOCKED / DEPRECATED`. `VERIFIED` wyłącznie dla kodu URUCHOMIONEGO i przetestowanego.

## Liczby kontrolne (zweryfikowane)

- Testy: **102 passed** (offline, deterministyczne, bez sieci). Gałąź: `dev/first-successful-research-card`.
- Realny koszt projektu: **0,500616 USD** (6 wpisów `model_usage` z `dry_run=0`; limit miesięczny 40 USD → wykorzystane 1,25%).
- Realne próby researchu: **3** (+1 diagnostyka pojedynczego źródła) — **0 ukończonych Research Card na żywym API** (1 karta istnieje wyłącznie z dry_run).
- Baza: runs = 4×DRY_RUN + 3×FAILED (zero osieroconych RUNNING); research_runs = 1×FAILED, 1×PARTIAL (`9bbeb020`, niedomykalny bez P1-5); topics = 6×SELECTED, 4×SCORED, 2×REJECTED, 6×DUPLICATE.
- Publikacje na Substacku: **0** (fizycznie zablokowane przez `DisabledBrowser`).

## Tabela stanu modułów

| Moduł | Status | % | Co działa | Co nie działa / znane błędy | Testy | Ostatnia weryfikacja | Następny krok |
|---|---|---|---|---|---|---|---|
| Konfiguracja (`app/core/config.py`) | VERIFIED | 90 | .env+YAML, zero ścieżek absolutnych, fallback na *.example | kill-switch czytany raz przy starcie (runtime — Etap 1) | pośrednie (fixtures) | 2026-07-12 | bez zmian do Etapu 1 |
| Modele domenowe (`app/models.py`) | VERIFIED | 90 | wszystkie enumy/modele zbudowanej części | `TopicStatus.USED`, `RunStatus.STOPPED` — martwe wartości | tak | 2026-07-12 | USED w Etapie 0 (P1-6) |
| Storage SQLite + 5 migracji | VERIFIED | 85 | repozytoria, migracje, atomowe przejścia stanu researchu | `mark_*` bez walidacji stanu poprzedniego; brak WAL/busy_timeout; migracje bez transakcji | test_storage + inne | 2026-07-12 | Etap 0 zad. 2 i 8 |
| Policy Engine | PARTIAL | 25 | kill-switch (statyczny), active, budżet D/M (miesięczny nadrzędny), progi tematów | brak: autonomy_level, AccountMode, limity AccountPolicy, cooldowny, cap per-run, SAFE MODE | test_policy_engine | 2026-07-12 | check_run_budget (Etap 0 zad. 5); reszta Etap 4 |
| UsageTracker (koszty) | VERIFIED | 95 | model_usage+COSTS.csv, dry_run flaga, koszt przy błędach researchu | równoległy append CSV nieodporny (przyszły worker) | tak + 3 realne runy | 2026-07-12 | eksport z DB przy Etapie 8 |
| ModelRouter | VERIFIED | 90 | zadanie→model z .env | scripts omijają router (P2-8) | tak | 2026-07-12 | P2-8 przy Etapie 0/1 |
| FakeLLMClient / FakeResearchClient | VERIFIED | 100 | deterministyczne dry_run/testy, scenariusze brzegowe | — | tak | 2026-07-12 | — |
| AnthropicLLMClient (tematy) | PARTIAL | 50 | kompletny kod wywołania | **nigdy nie uruchomiony realnie (NOT VERIFIED live)**; brak księgowania kosztu przy błędzie parsowania; brak strip code fence; brak testów parsera | brak | 2026-07-12 | Etap 0 zad. 6 |
| AnthropicResearchClient (3 generacje metod) | WORKING | 80 | retry(timeout-only), koszt przy parse-error, capy tokenów/searchy, diagnostyka raw+stop_reason | retry bez re-checku budżetu (P1-3); A2 = search-o-URL, nie fetch treści (P0-2c → Etap 2); live: A1 ✅, A2 1×✅ (diagnostyka), B **NOT VERIFIED live** | tak (wstrzykiwane callery) | 2026-07-12 | Etap 0 zad. 5, potem Etap 2 |
| Estymator kosztów | VERIFIED | 85 | conservative+expected z 2 realnych obserwacji, margines ≥50% | dwie kalibracje (legacy z cennika vs staged stałe) — P2-1; kalibracja n=2 | tak | 2026-07-12 | ujednolicić przy Etapie 2 |
| Workflow tematów + dedup | VERIFIED | 90 | pełny przepływ dry_run, dedup lokalny, progi, SUCCESS-fix | realny run tematów nigdy nie wykonany | tak | 2026-07-12 | realny run po Etap 0 zad. 6 |
| Research staged A1/A2/B + resume | WORKING | 75 | pełny przepływ + wznowienia z bazy po restarcie; P0-1/2a/2b naprawione | brak retry EXTRACTION_FAILED (P1-5); PARTIAL współdzielony bez `flow` (P1-1/9); `runs.cost_usd` dziury (P1-2); brak guardu re-researchu (P1-6); **cała ścieżka bez sukcesu na żywym API** | 12+ testów | 2026-07-12 | Etap 0 zad. 1–8, potem (za osobną zgodą) run ADR-022 = zad. 9 |
| Research legacy (single, two-stage) | WORKING | 100 | działa, 24 testy | NIEZALECANY (ADR-016→020); do DEPRECATED po sukcesie staged live | tak | 2026-07-12 | Etap 2 zad. 6 |
| Walidacja + injection guard | VERIFIED | 90 | deterministyczna bramka, min_verified_sources, neutralizacja injection | wzorce EN-only (P2-7) | tak | 2026-07-12 | rozszerzenie przy Etapie 2 |
| Diagnostyka odpowiedzi | VERIFIED | 95 | raw+stop_reason per etap, potwierdzona na żywo | nadpisuje poprzednią próbę tego samego etapu (P2-13, świadome) | tak | 2026-07-12 | — |
| CLI `app/main.py` + runner | VERIFIED | 85 | run-topics, run-research (dry), blokada `--real` (P0-3) | docelowo jedyne wejście — scripts do wchłonięcia (Etap 1) | tak | 2026-07-12 | — |
| `scripts/run_capped_research.py` | VERIFIED | 85 | pre-flight, capy, estimate-only, resume obu przepływów | duplikuje logikę budżetu (P1-4); sniffing `_detect_flow` (P1-1); `--max-sources 0` znaczy „wszyscy" (P2-15) | częściowe | 2026-07-12 | Etap 0 zad. 1 i 5 |
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

1. **Ukończenie zadań 1–8 Etapu 0** (`IMPLEMENTATION_ROADMAP.md`) — naprawy wykonawcze researchu (flow, koszty, retry kandydatów, USED, szczelny budżet, klient tematów, higiena ADR, walidacja przejść stanów) muszą zostać wdrożone, przetestowane i udokumentowane PRZED jakimkolwiek kolejnym płatnym uruchomieniem. Dopiero po ich zakończeniu potrzebna będzie **osobna zgoda właściciela** na realny run ADR-022 (zadanie 9, cap 0,55 USD) — offline pre-flight tego runu jest gotowy (BUILD_LOG Etap 1O), ale run NIE jest obecnie do wykonania.
2. **Run `9bbeb020` (PARTIAL) niedomykalny** — 2 kandydatów EXTRACTION_FAILED bez drogi powrotu; nawet pełne wznowienie da max 2<3 źródeł. Usuwane przez zadanie 3 Etapu 0 (P1-5).
3. **Etap B syntezy nigdy nie wykonany na żywym API** — ostatni niezweryfikowany element ścieżki researchu; zostanie zweryfikowany dopiero przy zadaniu 9 Etapu 0.

## Ostatnie ważne decyzje

- **ADR-022 (PROPOSED):** konfiguracja pierwszego świeżego runu nastawionego na kompletną kartę (4 źródła = tolerancja 1 błędu; cap 0,55 USD) — do wykonania jako zadanie 9 Etapu 0, PO ukończeniu zadań 1–8 i za osobną zgodą właściciela.
- **ADR-021:** repo GitHub PRIVATE, main stabilny + branche dev.
- **ADR-020:** research staged A1/A2/B; **ADR-019:** trwałość etapów; **ADR-017/018:** cel = pełna autonomia operacyjna + anonimowa marka redakcyjna bez proaktywnego ujawniania AI (NO_REPLY, zero impersonacji).
- **2026-07-12 (ten audyt):** konsolidacja dokumentacji do 3 dokumentów źródła prawdy; stare plany w `docs/archive/superseded_plans/` (ADR-023).

## Etapy

- **Aktywny etap roadmapy:** Etap 0 — Stabilizacja (zadania 1–9).
- **Ostatni ukończony krok:** Etap 1O (offline pre-flight runu ADR-022) + naprawy P0-1/2/3 (Etap 1K) + konsolidacja dokumentacji (ten audyt).
- **Następne trzy zadania:**
  1. Migracja 0006 `research_runs.flow` + walidacja przepływu w resume + usunięcie `_detect_flow`.
  2. `runs.cost_usd` świeży przy każdym wyjściu etapu staged + WAL/busy_timeout w `db.py`.
  3. Migracja 0007 `attempts` + `retry-failed-candidates` + status `PARTIAL_EXHAUSTED`.

## Znane długi techniczne (poza blokerami; numeracja z audytu 12.07)

| # | Dług | Plan |
|---|---|---|
| P1-3/P1-4 | retry poza estymatą i bez re-checku budżetu; cap per-run tylko w CLI (zduplikowana logika budżetu) | Etap 0 zad. 5 |
| P1-7 | kill-switch nie działa w runtime (snapshot z .env) | Etap 1 (system_flags) |
| P2-1 | dwie kalibracje estymatora (rozjazd przy zmianie cen w .env) | Etap 2 |
| P2-2 | koszt w 3 miejscach (model_usage=kanon; runs.cost_usd i research_runs.total_cost_usd=cache z dziurami) | Etap 0 zad. 2 deklaruje kanon |
| P2-4 | budżet dzienny wg dnia UTC (właściciel w Europe/Warsaw) | decyzja: zostaje UTC — udokumentowane |
| P2-5 | migracje bez transakcji (częściowa awaria = zakleszczenie) | nowe migracje od 0006 z BEGIN/COMMIT |
| P2-6 | RESEARCH_LOG.md tylko przy sukcesie (nieudane realne runy nielogowane automatycznie) | Etap 2 |
| P2-7 | injection guard EN-only, URL-e nieskanowane | Etap 2 (przy fetch) |
| P2-8 | scripts używają settings.model_quality zamiast ModelRouter | Etap 0/1 |
| P2-9 | ADR-001/002/003/005/006 wiecznie PROPOSED | Etap 0 zad. 7 |
| P2-10/P2-11 | migracja przy każdym otwarciu bazy; runtime pisze do docs/ | Etap 8 |
| P2-12 | brak prompt cachingu (N×A2 dzieli system prompt) | po sukcesie live |
| P2-13/P2-14 | diagnostyka nadpisuje poprzednią próbę; stage log nie mierzy czasu | świadomie odłożone |
| P2-15 | `--max-sources 0` znaczy „wszyscy" | Etap 0 przy zad. 1 |
| nowy | AnthropicLLMClient bez księgowania kosztu przy parse-error, bez testów | Etap 0 zad. 6 |
| nowy | EnvSecretStore/LocalFileStore = martwy kod | Etap 8 (podpiąć) albo usunąć decyzją |
| znany | lokalne `.venv`: open-interpreter wymaga anthropic<0.38 przy zainstalowanym 0.116 (ostrzeżenie pip, poza projektem) | obserwować |
| rezydualny | timeout API może być zbilowany bez lokalnego usage (nieusuwalne) | mitygacja: max_retries 0/1 + capy |
