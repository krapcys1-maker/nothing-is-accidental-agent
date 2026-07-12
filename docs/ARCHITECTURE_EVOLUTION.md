# ARCHITECTURE_EVOLUTION

## Cel

Zapis **jak zmieniała się architektura** w czasie: od wersji na papierze do tego, co realnie zbudowano. Dokumentuje różnicę między planem a rzeczywistością, porzucone pomysły i powody zmian. Każda „wersja" architektury dostaje wpis z datą, opisem i diagramem faktycznie działającego systemu (nie docelowego). To jeden z najcenniejszych materiałów do końcowego artykułu — pokazuje ewolucję, nie tylko efekt.

## Zasady

- Dokumentuj stan **faktyczny**, nie docelowy (docelowy jest w `IMPLEMENTATION_PLAN.md`).
- Każdy większy etap = nowa wersja (V0, V1, …) z diagramem tego, co realnie działa.
- Zapisuj, co z planu **odpadło** lub zostało zmienione i dlaczego (link do `DECISIONS.md`).

## Szablon wpisu

```markdown
## Vx — [YYYY-MM-DD] Nazwa etapu
- **Co realnie działa:** komponenty, które są zbudowane i przetestowane
- **Czego jeszcze nie ma:** świadome luki
- **Zmiany względem planu:** co poszło inaczej + ADR
- **Diagram (stan faktyczny):**
​```
...ASCII/mermaid diagram TYLKO tego, co działa...
​```
```

---

## Wersje

## V0 — [2026-07-11] Architektura na papierze (przed kodem)
- **Co realnie działa:** nic w kodzie — to stan wyjściowy. Istnieją: pełna architektura docelowa (`IMPLEMENTATION_PLAN.md`), założenia, konfiguracje przykładowe, dokumentacja eksperymentu.
- **Czego jeszcze nie ma:** żadnego kodu (`app/` nie istnieje), bazy, klienta Anthropic, Policy Engine.
- **Zmiany względem planu:** brak — punkt zerowy.
- **Diagram (stan faktyczny):**
```
[dokumenty i konfiguracje]  ->  (brak warstwy wykonawczej)
docs/ + config/*.example.yaml + .env(lokalny)
```

## V1 — [2026-07-11] Walking skeleton (Etap 0/1)
- **Co realnie działa:** konfiguracja (`.env` + YAML, bez ścieżek absolutnych), SQLite z migracją `0001`, `PolicyEngine` (kill-switch, aktywność konta, budżet z priorytetem miesięcznym, progi scoringu), `UsageTracker` (koszt → `model_usage` + `docs/COSTS.csv`), `ModelRouter` (modele z `.env`), przepływ generacji+oceny tematów w `dry_run` z klientem zastępczym, CLI `run-topics`, 16 testów jednostkowych.
- **Czego jeszcze nie ma:** realnego wywołania Anthropic (kod gotowy, uruchamiane przez `--real`), researchu, artykułów/Notes, komentarzy, panelu FastAPI, Playwrighta/publikacji, deduplikacji tematów.
- **Zmiany względem planu:** dodano kolumnę `model_usage.dry_run` (odróżnia estymacje dry_run od realnych kosztów w budżecie) — refinement, ADR-013. Porty Scheduler/Browser jako świadome stuby (`DisabledBrowser` blokuje akcje na Substacku). Wagi scoringu i priorytet budżetu przeniesione do `config/growth_policy`.
- **Diagram (stan faktyczny — tylko to, co działa):**
```
  python -m app.main run-topics   (CLI, dry_run)
              │
              ▼
        orchestrator.runner ──► load_settings(.env + growth_policy.yaml)
              │
              ▼
     workflows/topics/discover
        │         │            │
        ▼         ▼            ▼
  PolicyEngine  FakeLLMClient  UsageTracker
  (can_run,     (deterministy- (estimate_cost)
   budget,       czne tematy         │
   progi)        + usage)            ▼
        │            │        model_usage (SQLite)
        ▼            ▼        + docs/COSTS.csv
        └──►  SqliteStorage (topics, runs) ◄──┘

  [DisabledBrowser] — celowo wyłączony (zero akcji na Substacku)
  [StubScheduler]   — uruchamianie ręczne
```

## V2 — [2026-07-11] Deduplikacja tematów + Research Pipeline (Etap 1A/1B)
- **Co realnie działa:** lokalna deduplikacja tematów (znormalizowany tytuł + Jaccard/SequenceMatcher, per account, status DUPLICATE + duplicate_of + reason); pełny research pipeline (plan → web search → źródła → analiza → Research Card → walidacja jakości → SQLite → auto-dokumentacja) w `dry_run`; deterministyczna bramka jakości; ochrona przed prompt injection; `FakeResearchClient` (scenariusze) i `AnthropicResearchClient` (retry/timeout/parse, testowalny bez sieci); auto-wpisy do `RESEARCH_LOG.md` i `COSTS.csv`; 44 testy.
- **Czego jeszcze nie ma:** realnego wywołania Anthropic (gotowe, `--real`), artykułów/Notes/komentarzy, panelu FastAPI, Playwrighta/publikacji.
- **Zmiany względem planu:** migracje 0002 (dedup) i 0003 (pola Research Card + źródeł); klient researchu z wstrzykiwanym callerem (testowalność retry/timeout bez sieci) — ADR-014/015.
- **Diagram (stan faktyczny — pipeline researchu):**
```
  run-research (CLI, dry_run)  ─►  wybór tematu SELECTED z SQLite
         │
         ▼
  workflows/research/pipeline
    │  1. PolicyEngine.check_can_run
    │  2. build_research_plan (lokalnie)
    │  3. PolicyEngine.check_budget  ◄── STOP przed web search, jeśli budżet przekroczony
    │  4. ResearchClient.run_research ──► FakeResearchClient (dry_run)
    │                                     AnthropicResearchClient (--real, web search, retry/timeout)
    │  5. injection_guard  ── neutralizuje polecenia w treści źródeł (dane ≠ instrukcje)
    │  6. UsageTracker ──► model_usage (web_search_requests) + docs/COSTS.csv
    │  7. validate_draft ── bramka jakości → PROCEED / REJECT + reasons
    │  8. SqliteStorage ──► research_cards + sources
    │  9. docs_writer ──► docs/RESEARCH_LOG.md
    ▼
  ResearchRunSummary (rekomendacja, źródła, koszt, injection_flags)
```

## V3 — [2026-07-11] Dwuetapowy research + kalibrowany estymator (Etap 1D, ADR-016)
- **Co realnie działa:** `run_two_stage_research_pipeline` — etap 1 (`gather_sources`: tylko web search + zbieranie źródeł/faktów, max 4 wyszukiwania, lekki schemat) → tania bramka wczesnego wyjścia (za mało źródeł = STOP, etap 2 NIE jest wołany) → etap 2 (`synthesize_card`: tylko analiza z już zebranych danych, zero web search). Budżet sprawdzany PRZED każdym etapem osobno, kalibrowanym estymatorem (`app/research/cost_estimator.py`, margines bezpieczeństwa wymagany >=50%). Stary jednoetapowy pipeline zachowany (oznaczony jako niezalecany), jego pre-estymat budżetu również przełączony na nowy estymator. `scripts/run_capped_research.py` przepisany: domyślnie `--mode two-stage`, nowa flaga `--estimate-only` (pokazuje projekcję kosztu obu etapów, zero wywołań API). 16 nowych testów (63 razem).
- **Czego jeszcze nie ma:** realnego uruchomienia dwuetapowego pipeline'u (zbudowane i przetestowane lokalnie, ale nieużyte na żywym API — wymaga nowej, osobnej zgody właściciela).
- **Zmiany względem planu:** powód zmiany — pierwsze realne wywołanie jednoetapowe (V2, Etap 1C) kosztowało realnie 0.25 USD wobec szacunku 0.095 USD (błąd ~+163%, potwierdzone w konsoli Anthropic) i zakończyło się uciętym JSON-em. ADR-016 dokumentuje decyzję i uzasadnienie. Ważne zastrzeżenie architektoniczne udokumentowane w `docs/ERRORS_AND_FAILURES.md`: `--max-cost-usd` NIGDY nie był twardym limitem egzekwowanym w trakcie pojedynczego żądania API (Anthropic nie oferuje przerwania w połowie) — to kontrola PRZED startem, oparta na estymacji; realną górną granicę per-wywołanie wyznaczają wyłącznie `max_tokens`/`max_uses` przekazane do API.
- **Diagram (stan faktyczny — dwuetapowy pipeline):**
```
  run_capped_research.py --mode two-stage --estimate-only   (ZERO wywołań API)
              │
              ▼
  cost_estimator.estimate_worst_case_search_call_usd(etap1) + estimate_no_search_call_usd(etap2)
              │
              ▼  (jeśli w capie — dopiero wtedy realne wywołania, po osobnej zgodzie)
  run_two_stage_research_pipeline
    │  1. PolicyEngine.check_can_run
    │  2. build_research_plan (lokalnie)
    │  3. PolicyEngine.check_budget (kalibrowany szacunek etapu 1)  ◄── STOP przed etapem 1
    │  4. gather_sources (TYLKO web search, max 4, lekki schemat) ──► koszt zaksięgowany
    │  5. injection_guard na źródłach/faktach
    │  6. za mało źródeł? ──► STOP tutaj, etap 2 NIE jest wołany (oszczędność)
    │  7. PolicyEngine.check_budget (szacunek etapu 2)  ◄── STOP przed etapem 2
    │  8. synthesize_card (ZERO web search, analiza z zebranych danych) ──► koszt zaksięgowany
    │  9. validate_draft (ta sama bramka jakości co w V2)
    │ 10. SqliteStorage ──► research_cards + sources (suma kosztu = etap1+etap2)
    ▼
  ResearchRunSummary
```

## [2026-07-11] Redefinicja stanu DOCELOWEGO (nie nowa wersja — meta-wpis)
Ta sekcja celowo nie jest kolejną wersją „Vx" — zgodnie z zasadą tego pliku dokumentujemy tu wyłącznie stan **faktyczny**, a poniższe jest korektą **celu**, nie nowym zbudowanym kodem. Właściciel doprecyzował (ADR-017, `docs/DECISIONS.md`), że architektura docelowa to **LEVEL_3 — pełna autonomia operacyjna** (agent samodzielnie prowadzi konto), a ręczna akceptacja każdej akcji, którą sugerowała dotychczasowa dokumentacja (macierz `IMPLEMENTATION_PLAN.md §B.8`, ADR-004), była opisem **fazy startowej**, nie architektury końcowej. Pełna specyfikacja docelowego stanu (LEVEL_0–3, warunki przejść, Autonomous Interaction Engine, scoring komentarzy/subskrypcji, SAFE MODE) — `docs/IMPLEMENTATION_PLAN.md` CZĘŚĆ D. **Stan faktyczny kodu na dziś się nie zmienił** — to wciąż V3 opisane wyżej; żaden nowy kod, Playwright ani wywołanie API nie powstały w ramach tej redefinicji.
