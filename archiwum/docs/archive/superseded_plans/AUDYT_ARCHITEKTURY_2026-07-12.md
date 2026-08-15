> **ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.**
> Dokument historyczny (zarchiwizowany 2026-07-12). Obowiazuja wylacznie: MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md (korzen repozytorium) oraz rejestr decyzji docs/DECISIONS.md.

# AUDYT ARCHITEKTURY — „Nothing Is Accidental"

**Data:** 2026-07-12 · **Zakres:** całe repozytorium (kod, migracje, konfiguracja, docs/, opis-budowy-substack/, testy) · **Tryb:** wyłącznie odczyt — zero zmian w kodzie, zero wywołań API, zero Playwrighta, zero publikacji.

**Stan wyjściowy w liczbach:** 41 plików `.py` w `app/`, 5 migracji SQLite, 85 testów (wszystkie zielone), 2 realne płatne wywołania API (0,373823 USD łącznie, 0 udanych Research Card), 20 ADR-ów.

---

## 1. Executive summary

Projekt jest w **dobrej kondycji jak na swoją fazę** — ale audyt znalazł **3 problemy klasy P0**, z których jeden (P0-3) to dziś najgroźniejsza pojedyncza komenda w repo, a drugi (P0-2) unieważnia sens zaproponowanego małego realnego testu w jego obecnej konfiguracji.

**Co jest mocne:**
- Warstwa research (temat → Research Card) jest jedyną w pełni zbudowaną częścią docelowego przepływu — i jest w niej widoczna dyscyplina: trzy kolejne przebudowy (ADR-016/019/020) każdorazowo adresowały realny, zmierzony problem; koszty przy błędach nie giną; wznawialność jest testowana symulowanym restartem procesu, nie reużytym stanem.
- Kanon kosztów (`model_usage` + `dry_run` flaga) jest zdrowy: budżet liczy wyłącznie realne wpisy, obie realne porażki mają pełne, poprawne kwoty.
- Izolacja kont (account_id wszędzie), ochrona sekretów (.gitignore, zero haseł), injection guard jako dane-nie-polecenia — fundamenty bezpieczeństwa są na miejscu.
- Ports/Protocol layer daje realną (nie tylko deklarowaną) drogę local → VPS.

**Co jest słabe:**
- **Model stanów `runs` jest zepsuty u podstaw:** `RunStatus.SUCCESS` nie jest zapisywany NIGDZIE w kodzie — każdy udany realny run zakończy się terminalnym statusem `RUNNING` (potwierdzone w kodzie i w bazie: 0 wierszy SUCCESS). Nie wybuchło tylko dlatego, że żaden realny run jeszcze się nie powiódł.
- **`python -m app.main run-research --real` to niekontrolowana ścieżka kosztowa:** używa przestarzałego jednoetapowego pipeline'u, konstruuje klienta **bez `max_uses`** (nieograniczona liczba web searchy w jednym wywołaniu) i bez per-run capu. Wszystkie zabezpieczenia z dwóch incydentów żyją tylko w `scripts/run_capped_research.py`.
- **Etap A2 nie czyta źródeł — pyta model o opinię o URL-u.** Nie ma web fetch; przy `--max-web-searches-per-source 0` (konfiguracja zaproponowanego małego testu!) ekstrakcja to w 100% wiedza modelu, model **sam sobie przyznaje** `VERIFIED`, a bramka jakości liczy `UNVERIFIED` do minimum źródeł. Karta może przejść walidację bez jednego dowodu.
- Policy Engine pokrywa 3 z ~14 obowiązków z dokumentacji (kill-switch, active, budżet globalny). `autonomy_level`, `allowed_actions`, limity per konto, cooldowny, SAFE MODE — wszystko to dziś martwe pola/konfiguracja bez egzekucji (świadomie planowane, ale audyt musi to nazwać wprost).
- Wszystko poniżej Research Card w docelowym przepływie (artykuły, audyty, Notes, interakcje, scheduler, Playwright, metryki, strategia) **nie istnieje w kodzie** — istnieje wyłącznie jako specyfikacja. To nie zarzut (taka jest faza), ale mapa pokrycia musi być jawna.

**Rekomendacja nadrzędna:** przed JAKIMKOLWIEK kolejnym płatnym wywołaniem domknąć P0-1/P0-2/P0-3 (wszystkie naprawialne offline, łącznie ~pół dnia pracy z testami). Architektury NIE przepisywać — modularny monolit z portami jest właściwy; problemy są punktowe, nie systemowe.

---

## 2. Diagram obecnej architektury (stan faktyczny kodu, nie planu)

```
                       ┌────────────────────────────────────────────────┐
 WEJŚCIA (2 równoległe,│  scripts/run_capped_research.py                │  ← jedyne wejście z capem
 NIErówne bezpieczeń.) │  (pre-flight, cap, estimate-only, --resume)    │
                       └──────────────┬─────────────────────────────────┘
 ┌────────────────────────────┐       │
 │ app/main.py → orchestrator/│       │   ★ P0-3: --real bez capu, bez max_uses,
 │ runner.py (run-topics,     │───────┤      stary jednoetapowy pipeline
 │ run-research [--real])     │       │
 └────────────────────────────┘       ▼
                    ┌──────────────────────────────────────────┐
                    │ workflows/                               │
                    │  topics/discover (+dedup lokalny)        │
                    │  research/pipeline:                      │
                    │   • run_research_pipeline (legacy 1-call)│
                    │   • run_two_stage (legacy-2, ADR-016/019)│
                    │   • staged A1/A2/B (ADR-020) + resume    │
                    └───────┬──────────────────┬───────────────┘
                            │                  │
              ┌─────────────▼───┐   ┌──────────▼─────────────────────┐
              │ policies/       │   │ research/                      │
              │ PolicyEngine:   │   │  anthropic_client (3 rodziny   │
              │  kill_switch    │   │   metod), fake_client,         │
              │  account.active │   │  validation, injection_guard,  │
              │  budżet D/M     │   │  cost_estimator (2 kalibracje),│
              │  progi tematów  │   │  diagnostics (raw+stop_reason) │
              └─────────────────┘   └──────────┬─────────────────────┘
                            │                  │ llm/ (Router, UsageTracker,
                            ▼                  ▼  Fake/Anthropic dla tematów)
                    ┌──────────────────────────────────────────┐
                    │ storage/ SqliteStorage (StoragePort)     │
                    │  5 migracji; runs+research_runs(+flow?★) │
                    │  research_sources | research_source_     │
                    │  candidates | model_usage (KANON kosztów)│
                    └──────────────────────────────────────────┘
   PORTY-STUBY (celowo wyłączone): BrowserPort(Disabled) · SchedulerPort(Stub)
   MARTWE TABELE (schemat bez kodu): content_items · interactions · target_items
                                     approvals · metrics_daily · screenshots
   NIE ISTNIEJE (tylko dokumentacja): artykuły/audyty · Notes · komentarze ·
                                     scheduler · Playwright · metryki · strategia · UI
```

## 3. Diagram rekomendowanej architektury (docelowy, ewolucja — nie rewolucja)

```
                 ┌───────────────────────────────────────────────┐
                 │ JEDNO wejście operacyjne: app/main.py         │
                 │ (subkomendy delegują do wspólnych runnerów;   │
                 │  scripts/ = cienkie aliasy, nie druga logika) │
                 └──────────────────────┬────────────────────────┘
                                        ▼
                 ┌───────────────────────────────────────────────┐
                 │ scheduler/ (nowy): tabela jobs + worker loop  │
                 │ lease/lock · earliest_run_at/deadline/priority│
                 │ idempotency_key · powód wybranej godziny      │
                 └──────────────────────┬────────────────────────┘
                                        ▼
      ┌─────────────────────────────────────────────────────────────┐
      │ orchestrator/: pojedynczy punkt egzekucji ProposedAction    │
      │  KAŻDA akcja: PolicyEngine.check(action_ctx) → wykonaj →    │
      │  zapisz skutek → potwierdź                                  │
      └───────┬─────────────────────────────────────────────────────┘
              ▼
      ┌───────────────────────────┐    ┌──────────────────────────────┐
      │ PolicyEngine (rozszerzony)│    │ workflows/ (bez zmian granic)│
      │ + autonomy_level gate     │    │ research: TYLKO staged A1/A2/B│
      │ + allowed_actions         │    │ (legacy oznaczone deprecated,│
      │ + limity per konto/dzień  │    │  usunięte po sukcesie live)  │
      │ + per-run cost cap        │    │ + articles/notes/comments    │
      │ + cooldown/duplicate-pub  │    │   (kolejne fazy)             │
      │ + SAFE MODE (DB-flaga,    │    └──────────────────────────────┘
      │   czytana runtime)        │
      └───────────────────────────┘
      storage/: model_usage = jedyny kanon kosztu (reszta = cache oznaczony);
      research_runs.flow ('single'|'two_stage'|'staged'); WAL + busy_timeout;
      runtime-artefakty → data/, eksport do docs/ osobnym krokiem
```

Kluczowe różnice względem stanu obecnego: (1) jedno wejście zamiast dwóch o różnym poziomie bezpieczeństwa, (2) Policy Engine faktycznie centralny (wszystkie akcje przez jeden `check`), (3) kolumna `flow` zamiast zgadywania przepływu po zawartości tabel, (4) scheduler jako kolejka w SQLite, nie cron-w-pamięci.

---

## 4. Pełny przepływ danych (od tematu do metryk)

**Zbudowane (kod + testy):**
```
[CLI] → PolicyEngine(can_run, budżet) → LLM generate_and_score_topics
  → scoring wagami (config) → dedup lokalny (Jaccard+SequenceMatcher)
  → topics(status: DISCOVERED→SELECTED/SCORED/REJECTED/DUPLICATE) [SQLite]
  → model_usage + COSTS.csv

[CLI] SELECTED topic → research (3 przepływy, zalecany staged):
  A1 discover (web search, JSONL) → research_source_candidates [zapis atomowy]
  A2 extract (per źródło, zapis NATYCHMIAST po każdym, budżet przed każdym)
  B synthesize (zero search, z kart w bazie) → research_cards + sources
  → walidacja deterministyczna (validate_draft) → RESEARCH_LOG.md
  koszty: model_usage per etap (task=research_discover/extract/synthesize_cards)
```

**Niezbudowane (tylko specyfikacja):** article draft → fact/style/growth audit → final → Notes → interaction selection → scheduler → Playwright → Substack → metrics → strategy update. Tabele `content_items`/`interactions`/`target_items`/`approvals`/`metrics_daily`/`screenshots` istnieją od migracji 0001, ale **żaden kod ich nie dotyka**.

**Gdzie dane są tworzone/walidowane/zapisywane — ocena:**
- Jedno źródło prawdy kosztów: **TAK** (`model_usage`), ale z dwoma mylącymi cache'ami (P2-2): `runs.cost_usd` (nieaktualizowany w kilku ścieżkach staged) i `research_runs.total_cost_usd` (wypełniany TYLKO przy COMPLETE).
- Duplikaty danych: `COSTS.csv` = świadomy eksport (OK, udokumentowane); `sources` vs `research_sources` vs `research_source_candidates` = trzy tabele źródeł dla trzech przepływów — akceptowalne przejściowo, wymaga planu konsolidacji po wygaszeniu legacy (sekcja 23: NIE teraz).
- Idempotentność etapów: A2 wznowienie — **TAK** (czyta tylko PENDING_EXTRACTION); discovery — **NIE** (drugi run na tym samym temacie tworzy nowy research_run i płaci ponownie — brak guardu, P1-6); retry — **częściowo** (patrz P1-3).
- Retry a podwójny koszt: timeout-retry w kliencie to **nowe płatne wywołanie bez ponownego budżet-checku** (P1-3). Podwójna publikacja: nie dotyczy jeszcze (brak publikacji), ale projekt schedulera musi to wykluczyć z góry (sekcja 8).

---

## 5. Krytyczne błędy P0

### P0-1 · Terminalny status `RUNNING` przy każdym udanym realnym runie (SUCCESS nigdy nie zapisywany)
- **Severity:** P0 (odpali się deterministycznie przy pierwszym sukcesie — czyli przy zatwierdzonym kolejnym teście).
- **Pliki:** [pipeline.py:256](app/workflows/research/pipeline.py) (`run_research_pipeline`), :513 (`run_two_stage`), :695 (`resume_research_stage_b`), :1151 (`run_synthesis_from_cards`), [discover.py:132](app/workflows/topics/discover.py).
- **Opis:** wszystkie ścieżki sukcesu wołają `finish_run(run_id, run_status.value, …)`, gdzie `run_status = DRY_RUN if dry_run else RUNNING`. W dry_run terminal to poprawnie `DRY_RUN`; w realnym runie terminal to… `RUNNING`. `RunStatus.SUCCESS` istnieje w enumie i w dokumentacji (§B.3), ale **nie ma ani jednego miejsca w kodzie, które by go zapisało**. Potwierdzone w bazie: 0 wierszy SUCCESS (oba realne runy = FAILED, więc nikt tego jeszcze nie zobaczył).
- **Przykład:** po udanym małym teście F.9 wiersz `runs` będzie miał `status='RUNNING'`, `finished_at` ustawione — stan wewnętrznie sprzeczny; każda przyszła rekonsyliacja „znajdź zawieszone RUNNING i posprzątaj" ubije/przeliczy zdrowe runy.
- **Ryzyko:** trwałe zanieczyszczenie księgi runów od pierwszego sukcesu; fałszywe alarmy przyszłego stale-run-reapera; mylące raporty panelu.
- **Rekomendacja:** na ścieżkach sukcesu zapisywać `RunStatus.SUCCESS` gdy `not settings.dry_run` (DRY_RUN zostaje bez zmian — 4 testy na tym polegają i słusznie); dopisać test `real-mode success → SUCCESS`.
- **Kolejność:** naprawa #2 (po P0-3, przed jakimkolwiek realnym wywołaniem).

### P0-2 · A2 „extraction" nie czyta źródła — wiedza modelu może w całości zastąpić dowód, a model sam sobie przyznaje VERIFIED
- **Severity:** P0 (unieważnia epistemiczny cel researchu ORAZ sens zaproponowanego małego testu w konfiguracji `--max-web-searches-per-source 0`).
- **Pliki:** [anthropic_client.py](app/research/anthropic_client.py) (`_default_extract_caller`, `_parse_source_card`), [validation.py:41-43](app/research/validation.py), [pipeline.py](app/workflows/research/pipeline.py) (`run_source_extraction`).
- **Opis (trzy nakładające się luki):**
  1. A2 używa **web_search** z zapytaniem „o URL", nie **web_fetch** treści URL-a — docelowy przepływ mówi „A2 fetch and extraction per source", dokumentacja (§7.2, ARCHITECTURE §8) wymienia „web fetch", kod go nie ma. Wyszukiwarka może zwrócić cokolwiek o domenie, niekoniecznie treść tej strony.
  2. Przy `max_uses=0` prompt jawnie każe polegać na „general knowledge" — i prosi model, by **sam ocenił** `verification_status: VERIFIED|UNVERIFIED|FAILED`. Nic deterministycznego nie wymusza `UNVERIFIED`, gdy model nie miał żadnego narzędzia do weryfikacji. Samoocena modelu = dokładnie to, przed czym projekt miał chronić („wiedza modelu nie zastępuje evidence").
  3. `validate_draft` liczy do `min_sources` wszystkie źródła z `verification != FAILED` — czyli **UNVERIFIED liczy się tak samo jak VERIFIED**. Karta zbudowana w 100% z niezweryfikowanych twierdzeń przechodzi bramkę PROCEED, jeśli scoring/confidence (też samoocena modelu!) są powyżej progów.
- **Przykład:** zaproponowany mały test (`--discovery-max-searches 2 --max-sources 2 --max-web-searches-per-source 0 --max-cost-usd 0.25`) wyprodukuje 2 karty źródeł czysto z wiedzy modelu; jeśli model wpisze `VERIFIED` i `source_quality_score=0.8`, powstanie „pozytywna" Research Card bez jednego faktycznego kontaktu z treścią źródła — test „przejdzie", nie dowodząc niczego o researchu.
- **Ryzyko:** halucynowane źródła z etykietą VERIFIED w bazie; przyszłe artykuły budowane na kartach bez dowodów; ryzyko R6 (halucynacje źródeł) formalnie „mitygowane", realnie otwarte.
- **Rekomendacja (deterministyczna, nie promptowa):** (a) gdy A2 działa z `max_uses=0` → parser/pipeline **wymusza** `verification=UNVERIFIED` niezależnie od odpowiedzi modelu; (b) `validate_draft` dostaje próg `min_verified_sources` (config; dla realnych runów ≥ min_sources) — UNVERIFIED przestaje wystarczać do PROCEED; (c) docelowo: web_fetch treści URL-a w A2 (narzędzie web fetch API albo lokalny fetcher za portem) — dopiero wtedy nazwa „fetch and extraction" jest prawdziwa; (d) mały test realny zmienić na `--max-web-searches-per-source 1` (koszt: patrz sekcja 24).
- **Kolejność:** naprawa #3.

### P0-3 · `python -m app.main run-research --real` = przestarzały pipeline bez limitu wyszukiwań i bez capu
- **Severity:** P0 (jedna, udokumentowana w `--help` komenda potrafi dziś wydać nieograniczoną-w-praktyce kwotę w jednym wywołaniu).
- **Pliki:** [runner.py:38-50](app/orchestrator/runner.py) (`_build_research_client`), [runner.py:105](app/orchestrator/runner.py) (`run_research` → `run_research_pipeline`), [main.py:111](app/main.py).
- **Opis:** `_build_research_client` tworzy `AnthropicResearchClient` **bez `max_web_searches`** → `None` → spec narzędzia web_search idzie do API **bez `max_uses`** (model może wyszukiwać dowolnie wiele razy w jednym turnie). Do tego `run_research` woła **jednoetapowy** `run_research_pipeline` (ten, który zawiódł 11.07 i jest opisany jako NIEZALECANY), bez per-run capu, bez `--estimate-only`, bez pre-flightu. Jedyna bramka to `check_budget(0.55)` przeciw limitom globalnym (2 USD/dzień) — czyli realne wywołanie może kosztować wielokrotność estymaty, zanim cokolwiek je zauważy. Wszystkie lekcje z dwóch incydentów (capy, max_uses=4, dwuetapowość, estimate-only) żyją wyłącznie w `scripts/run_capped_research.py` — main.py ich nie zna.
- **Przykład:** `python -m app.main run-research --topic-id 2 --real` → jednoetapowy research z nieograniczonym web search; przy 12+ wyszukiwaniach koszt tokenów napędzanych wynikami może przebić dzienny budżet w JEDNYM żądaniu (bramka sprawdzała 0.55).
- **Ryzyko:** finansowe (niekontrolowany koszt pojedynczego żądania — dokładnie klasa incydentu #1, tylko bez sufitu `max_uses`, który wtedy uratował sytuację) + regres procesowy (omija cały wypracowany reżim testów).
- **Rekomendacja:** minimalna, bez przebudowy: w `runner.run_research` przy `force_real=True` — twardy STOP z komunikatem „użyj scripts/run_capped_research.py" ALBO delegacja do staged pipeline'u z domyślnymi capami i jawnym potwierdzeniem. Docelowo (sekcja 16): jedno wejście.
- **Kolejność:** naprawa #1 (najprostsza, najgroźniejsza).

---

## 6. Ważne błędy P1

### P1-1 · `resume_staged_research` nie sprawdza przepływu dla współdzielonego statusu PARTIAL — cross-flow contamination
- **Pliki:** [pipeline.py](app/workflows/research/pipeline.py) (`resume_staged_research`, `run_source_extraction`), [run_capped_research.py](scripts/run_capped_research.py) (`_detect_flow` — chroni tylko CLI).
- **Opis:** PARTIAL jest wspólny dla przepływu legacy (gather/synthesize) i staged. Wywołanie `resume_staged_research` na legacy-PARTIAL runie przechodzi walidację statusu, po czym: `mark_extraction_in_progress` przestawia status legacy-runa, pętla nie znajduje kandydatów (0 w `research_source_candidates`), próg oblewa → `mark_research_run_partial` + `finish_run(FAILED, …)` **nadpisują pola `error` obu tabel myląca treścią** („Za mało wyekstrahowanych źródeł (0 < 3) po etapie A2") i przestawiają `runs.status`. Run pozostaje technicznie wznawialny legacy-ścieżką, ale jego diagnostyka jest zniszczona. CLI broni się `_detect_flow` (sniffing zawartości tabel) — biblioteka nie broni się wcale.
- **Ryzyko:** korupcja stanu/diagnostyki przy programistycznym użyciu (panel, scheduler); sniffing tabel jako mechanizm rozstrzygania to dług, nie rozwiązanie.
- **Rekomendacja:** migracja 0006: `research_runs.flow TEXT NOT NULL DEFAULT 'two_stage'` (backfill: `staged` gdzie istnieją candidates, `single` dla runu 1b649314); wszystkie funkcje resume walidują flow; `_detect_flow` znika.

### P1-2 · Osierocone `RUNNING` + `runs.cost_usd=0` mimo realnych kosztów (ścieżki staged bez `finish_run`)
- **Pliki:** [pipeline.py](app/workflows/research/pipeline.py): `run_source_discovery` (sukces — brak finish_run), `run_source_extraction` (ścieżka SOURCES_COMPLETE — brak finish_run), `run_synthesis_from_cards` (ścieżka błędu — brak finish_run).
- **Opis:** w przepływie staged wiersz `runs` jest domykany TYLKO przy pełnym sukcesie B albo przy partial-po-ekstrakcji. Scenariusz „A1 OK → A2 OK (SOURCES_COMPLETE) → B pada → operator odkłada wznowienie": `runs.status=RUNNING`, `finished_at=NULL`, `cost_usd=0.0` — a w `model_usage` siedzą realne koszty trzech wywołań. Budżet jest bezpieczny (liczy z model_usage), ale księga runów kłamie — to ta sama klasa problemu co incydent #1 („koszt znika z widoku"), tylko w tabeli-cache zamiast w kanonie.
- **Rekomendacja:** każda funkcja etapu aktualizuje `runs.cost_usd` (suma z `get_research_usage`) przy KAŻDYM wyjściu; status `runs` przy „etap zakończony, przepływ trwa" — jawny (np. current_state + status RUNNING tylko gdy proces faktycznie żyje, albo nowy status `SUSPENDED`); minimum: cost_usd zawsze świeży.

### P1-3 · Retry timeoutu = nowe płatne wywołanie poza estymatą i bez ponownego budżet-checku; timeout może zgubić realny koszt
- **Pliki:** [anthropic_client.py](app/research/anthropic_client.py) (`_run_with_retry_and_parse`, `_run_with_retry_and_parse_v2`), estymator.
- **Opis:** pętla retry (dla `ResearchTimeout`) wykonuje do `max_retries+1` płatnych wywołań, ale (a) bramka budżetowa widziała estymatę JEDNEGO wywołania, (b) estymator nigdzie nie mnoży przez liczbę prób, (c) timeout po stronie klienta nie niesie `usage` — jeśli serwer żądanie faktycznie przetworzył i zbilował, koszt jest realny, a lokalnie niewidoczny (znana, nieusuwalna do końca luka — ale dziś NIEudokumentowana w ERRORS_AND_FAILURES jako ryzyko rezydualne).
- **Rekomendacja:** worst-case estymaty ×(1+max_retries) w bramkach; przed każdą próbą retry — ponowny `check_budget`; wpis o resztkowym ryzyku „timeout-billed-unrecorded" w dokumentacji ryzyk.

### P1-4 · Per-run cost cap nie istnieje w bibliotece — tylko w jednym skrypcie
- **Pliki:** [policy_engine.py](app/policies/policy_engine.py), [run_capped_research.py](scripts/run_capped_research.py) (`_preflight_stop` duplikuje logikę budżetu Policy Engine).
- **Opis:** dokumentacja obiecuje „koszt pojedynczego runu" pod kontrolą Policy Engine; realnie cap per-run to porównanie w skrypcie CLI. Dodatkowo CLI reimplementuje sumowanie budżetu (druga kopia logiki — mogą się rozjechać).
- **Rekomendacja:** `PolicyEngine.check_run_budget(estimated_run_total, cap)` + wywołanie w pipeline'ach; CLI deleguje zamiast liczyć samodzielnie.

### P1-5 · Stany bez wyjścia: EXTRACTION_FAILED na zawsze, PARTIAL-wyczerpany bez ścieżki dalej
- **Pliki:** [repositories.py](app/storage/repositories.py), [pipeline.py](app/workflows/research/pipeline.py).
- **Opis:** (a) kandydat `EXTRACTION_FAILED` nie ma żadnej drogi powrotu do PENDING_EXTRACTION — nawet po błędzie przejściowym (timeout); (b) run PARTIAL, w którym wszyscy kandydaci są już przetworzeni, a EXTRACTED < min: `resume` wykonuje pustą pętlę, ponownie stempluje PARTIAL i FAILED (kolejny zapis, zero API) — stan trwale nie do opuszczenia, bez rozróżnienia od PARTIAL-wznawialnego; (c) brak „dodaj kandydatów" (re-discovery) jako świadomej, osobnej operacji.
- **Rekomendacja:** kolumna `attempts` na kandydacie + operacja `retry-failed-candidates` (jawna, capowana); status `PARTIAL_EXHAUSTED` (terminalny) gdy 0 PENDING i EXTRACTED < min; resume na PARTIAL_EXHAUSTED → czytelna odmowa.

### P1-6 · Cykl życia tematu urwany: USED nigdy nie ustawiane, brak guardu przed wielokrotnym płatnym researchem tego samego tematu
- **Pliki:** [models.py](app/models.py) (`TopicStatus.USED` — martwe), [pipeline.py](app/workflows/research/pipeline.py) (żaden przepływ nie zmienia statusu tematu), [runner.py](app/orchestrator/runner.py) (wybiera „najlepszy SELECTED" bez sprawdzenia istniejących kart).
- **Opis:** temat #2 był płatnie researchowany 2× (świadomie), ale systemowo NIC nie stoi na przeszkodzie trzeciemu, czwartemu… `run-research` bez `--topic-id` zawsze weźmie tego samego lidera rankingu. Dokumentacja (§7.1) wręcz zakłada dedup „vs topics.status=USED" — który nigdy nie następuje.
- **Rekomendacja:** po `mark_research_run_complete` → `topics.status=USED`; przed startem researchu → jeśli temat ma już COMPLETE kartę: wymagaj jawnej flagi `--force-re-research`.

### P1-7 · KILL_SWITCH nie działa w runtime — czytany raz, z .env, przy starcie procesu
- **Pliki:** [config.py](app/core/config.py) (`load_settings` → snapshot), [policy_engine.py](app/policies/policy_engine.py) (czyta `settings.kill_switch` — zamrożoną wartość).
- **Opis:** „kto może zatrzymać moduł?" — dziś: wyłącznie Ctrl+C. Zmiana KILL_SWITCH=true w .env nie wpływa na trwający proces (np. pętlę A2 z 10 kandydatami). Dla dzisiejszych krótkich runów CLI to akceptowalne; dla schedulera/panelu — dyskwalifikujące.
- **Rekomendacja (na etap schedulera, zaprojektować już teraz):** kill-switch i SAFE MODE jako wiersz w DB (`system_flags`), czytany przez PolicyEngine przy KAŻDYM checku (w pętli A2 już jest check per źródło — wystarczy, że check czyta świeży stan).

### P1-8 · SQLite bez WAL/busy_timeout — zablokuje się przy pierwszym współbieżnym czytelniku (panel/scheduler)
- **Pliki:** [db.py:10-16](app/storage/db.py).
- **Opis:** `connect()` nie ustawia `journal_mode=WAL` ani `busy_timeout`; domyślny journal + brak timeoutu = `database is locked` przy panelu FastAPI czytającym w trakcie zapisu workera. Lokalnie-sekwencyjnie niewidoczne; na VPS z 2 procesami — natychmiastowe.
- **Rekomendacja:** `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` w `connect()` (2 linie, zero ryzyka dla obecnych testów).

### P1-9 · Jeden enum statusów dla trzech przepływów + rozstrzyganie przepływu przez sniffing tabel
- **Pliki:** [models.py](app/models.py) (`ResearchRunStatus` — 10 wartości dwóch generacji), [run_capped_research.py](scripts/run_capped_research.py) (`_detect_flow`).
- **Opis:** źródłowa przyczyna P1-1. `PARTIAL/COMPLETE/FAILED` współdzielone celowo, ale bez pola rozstrzygającego przepływ każda funkcja musi „zgadywać po danych".
- **Rekomendacja:** jak w P1-1 — kolumna `flow`. (Jedno rozwiązanie zamyka oba findingi.)

### P1-10 · Policy Engine: 3 z ~14 obowiązków; autonomy_level/allowed_actions/AccountPolicy — martwa konfiguracja
- **Pliki:** [policy_engine.py](app/policies/policy_engine.py) (78 linii), [models.py](app/models.py) (Account.autonomy_level, allowed_actions, AccountPolicy — nigdzie nie czytane poza konstrukcją), ARCHITECTURE §6.4, PLAN §B.1.
- **Opis:** zaimplementowane: kill-switch (statyczny — P1-7), account.active, budżet D/M, progi tematów. Brak: poziom autonomii, tryb konta (COMMENT_ONLY nic nie blokuje!), limity akcji (daily_comment_limit itd.), cooldown, duplicate prevention (poza tematami), SAFE MODE, jakiekolwiek bramki publikacji/komentarzy/lajków/subskrypcji/strategii. Dokumentacja opisuje to jako plan (CZĘŚĆ D) — ale ARCHITECTURE §6.4 i PLAN §B.1 pkt 2 mówią o Policy Engine w czasie teraźniejszym, jakby stał przed „każdą akcją". Dziś przed każdą akcją stoi w 20%.
- **Ścieżki omijające Policy Engine (pełna lista, stan dzisiejszy):**
  1. `main.py run-research --real` — omija cap i max_uses (P0-3) — budżet globalny sprawdzany, reszta nie;
  2. retry w kliencie — płatne wywołania bez ponownego checku (P1-3);
  3. bezpośrednia konstrukcja `AnthropicResearchClient` + wywołanie metod (biblioteka nie wymusza bramki — akceptowalne dla warstwy klienta, ale trzeba to nazwać: **jedyną realną bramką jest dyscyplina wywołującego**);
  4. `UsageTracker.record` przyjmie każdy koszt post-factum (to poprawne — księgowość nie może odmawiać — ale znaczy, że limit NIE jest limitem w locie; dokumentacja od ADR-016 mówi to uczciwie).
- **Rekomendacja:** przy wdrażaniu każdej nowej klasy akcji (artykuł/Note/komentarz/publikacja) — NAJPIERW check w Policy Engine (autonomy_level + mode + limity), potem generator. Nie budować generatorów przed bramkami.

---

## 7. Usprawnienia P2

| # | Problem | Pliki | Rekomendacja |
|---|---|---|---|
| P2-1 | Dwie kalibracje estymatora (legacy liczy z cennika w runtime, staged ma stałe 0.04875/0.020956) — rozjadą się przy zmianie cen w .env | cost_estimator.py | jedna tabela kalibracji, obie rodziny funkcji czytają z niej |
| P2-2 | Koszt w 3 miejscach: model_usage (kanon), runs.cost_usd (cache, dziury — P1-2), research_runs.total_cost_usd (tylko COMPLETE) | repositories.py | zadeklarować kanon w docstrings; cache zawsze-świeży albo usunięty z odczytów |
| P2-3 | COSTS.csv: równoległy append może przeplatać wiersze; ręczne komentarze `#` — OK dla pandas, ale brak rekonsyliacji z DB | usage_tracker.py | okresowy eksport z DB zamiast append-on-write (przy VPS) |
| P2-4 | Budżet dzienny wg dnia UTC, właściciel działa w Europe/Warsaw | policy_engine.py | świadoma decyzja: zostawić UTC (udokumentować) albo strefa z configu |
| P2-5 | Migracje: `executescript` bez transakcji — częściowa awaria pliku = schemat w połowie + brak wpisu wersji = zakleszczenie | db.py | BEGIN/COMMIT wokół każdej migracji; test na powtórne aplikowanie |
| P2-6 | RESEARCH_LOG.md dostaje wpis tylko przy powstaniu karty — nieudane realne runy (najciekawsze dla kroniki!) nie są logowane automatycznie | docs_writer.py | writer także dla ścieżek błędu (status+koszt) |
| P2-7 | injection_guard: wzorce EN-only, URL-e nieskanowane, lista statyczna | injection_guard.py | rozszerzyć przy wdrożeniu web_fetch (wtedy wektor rośnie) |
| P2-8 | scripts/ używa `settings.model_quality` wprost — ModelRouter ominięty | run_capped_research.py | `router.model_for("research")` |
| P2-9 | Higiena dokumentów: ADR-001/002/003/005/006 wiecznie PROPOSED; §B.1 „sufit = LEVEL_1" i §B.3 (komentarze przy AutonomyLevel) bez banera ADR-017; CZĘŚĆ E.7 stara tabela kosztów bez SUPERSEDED; §B.3 Topic bez DUPLICATE | DECISIONS.md, IMPLEMENTATION_PLAN.md | jednorazowy przegląd statusów + banery |
| P2-10 | `SqliteStorage.open` migruje bazę przy każdym otwarciu (nawet `--estimate-only`) | repositories.py | na VPS: jawny krok `migrate` w deploy; lokalnie zostawić |
| P2-11 | Runtime pisze do `docs/` (COSTS.csv, RESEARCH_LOG.md) — w Dockerze wymaga wolumenu na katalog repo | usage_tracker.py, docs_writer.py | runtime → `data/`, eksport/sync do docs osobno (dopiero przy VPS) |
| P2-12 | Brak prompt cachingu — N×A2 dzieli identyczny system prompt | anthropic_client.py | cache_control przy skalowaniu (po udanym małym teście) |
| P2-13 | Diagnostyka nadpisuje plik przy ponownej próbie tego samego etapu (np. drugi retry B) — zostaje tylko ostatnia | diagnostics.py | dopisywać numer próby do nazwy (świadomie odłożone — udokumentowane w docstringu) |
| P2-14 | `research_stage_results.started_at≈finished_at` (wstawiane po fakcie) — log nie mierzy czasu etapu | repositories.py | przekazywać started_at z pipeline'u |
| P2-15 | `_run_resume_staged`: `if args.max_sources` — wartość 0 znaczy „wszyscy" zamiast „nikt" | run_capped_research.py | `is not None` |

---

## 8. Sprzeczności kod ↔ dokumentacja (pełna lista)

1. **`RunStatus.SUCCESS`** — §B.3 definiuje, kod nigdy nie zapisuje (P0-1).
2. **„web fetch"** — §7.2 i ARCHITECTURE §8 wymieniają jako narzędzie researchu; kod nie ma web fetch nigdzie (P0-2).
3. **„PolicyEngine stoi przed każdą akcją zewnętrzną i każdym wydatkiem"** (§B.1 pkt 2) — retry i main.py --real przeczą (P0-3, P1-3).
4. **`topics.status=USED`** — §7.1 dedupuje względem USED; kod nigdy nie ustawia USED (P1-6). §B.3 z kolei nie zna DUPLICATE, który kod ma od migracji 0002.
5. **§B.1 „Autonomia MVP: sufit = LEVEL_1… publikacja zawsze za akceptacją"** — sprzeczne z ADR-017 zapisanym niżej w tym samym pliku; §B.8 dostał baner aktualizacyjny, §B.1 nie.
6. **§B.3 komentarze `AutonomyLevel`** („LEVEL_2 auto wybrane Notes; LEVEL_3 poza MVP") — stara semantyka sprzed ADR-017, nieaktualizowana.
7. **ARCHITECTURE §6.2** — PromptRegistry, ToolRegistry, PromptCacheManager: nie istnieją (plan przedstawiany w czasie teraźniejszym).
8. **ARCHITECTURE §19 / PLAN §B.2 struktura folderów** — `app/tools/`, `app/scheduler/`, `app/secrets/`, `app/notifications/`, `app/ui/`, `workflows/articles|notes|comments|analytics|evidence` nie istnieją; porty secret/notification żyją w `app/ports/` (inna lokalizacja niż plan).
9. **StoragePort z §B.6** (generyczne add/get/list/update/count/transaction z obowiązkowym account_id w każdej metodzie) vs kod (konkretne metody; część bez account_id — np. `get_research_run`, `finish_run`) — kod jest LEPSZY (typowane metody), ale niezgodny ze specyfikacją; specyfikację zaktualizować, nie kod.
10. **CZĘŚĆ E.7 tabela kosztów** (0,36/0,02/0,38) — nadpisana przez F.8, bez banera SUPERSEDED.
11. **ADR-001/002/003/005/006 status PROPOSED** — od dawna wdrożone i traktowane jako obowiązujące.
12. **model_usage w ARCHITECTURE §18** — bez kolumn `task`/`dry_run`, które kod ma i na których wisi cała logika budżetu (dry_run) i rozdziału etapów (task).
13. **§B.10 plan testów** — „ProposedAction z niezgodnym account_id jest odrzucany": ProposedAction nie istnieje w kodzie w ogóle (żaden plik go nie definiuje poza specyfikacją).
14. **Dokumenty SUPERSEDED** (`zalozenia projektu/…`, `zalzoewnia dla agenta/…`) — poprawnie oznaczone i nietraktowane jako źródło prawdy ✅ (zgodne z wymogiem audytu).

---

## 9. Problemy w modelu stanów (+ proponowane maszyny)

**Zdiagnozowane defekty:** P0-1 (RUNNING jako terminal sukcesu), P1-2 (osierocone RUNNING bez rekonsyliacji), P1-5 (EXTRACTION_FAILED i PARTIAL-exhausted bez wyjścia), P1-9 (dwa przepływy w jednym enumie), niebezpieczne przejście `mark_extraction_in_progress` bez walidacji przepływu (P1-1), podwójne stemplowanie FAILED przy pustym resume.

**Proponowane maszyny stanów (docelowe):**

```
runs.status:      RUNNING → SUCCESS | FAILED | STOPPED     (DRY_RUN: terminal osobny)
                  + reaper: RUNNING starszy niż X i bez procesu → STOPPED(stale)

topics:           DISCOVERED → SCORED|SELECTED|REJECTED|DUPLICATE
                  SELECTED → USED (po COMPLETE research)   [nowe przejście — P1-6]

research_runs (flow='staged'):
  DISCOVERY_PENDING → DISCOVERY_COMPLETE → EXTRACTION_IN_PROGRESS
    → SOURCES_COMPLETE ⇄ SYNTHESIS_PENDING → COMPLETE
    → PARTIAL (są PENDING_EXTRACTION → wznawialne)
    → PARTIAL_EXHAUSTED (0 pending, extracted<min — terminal)   [nowy status]
  DISCOVERY_PENDING → FAILED (terminal)

source_candidates: PENDING_EXTRACTION → EXTRACTED | EXTRACTION_FAILED
                   EXTRACTION_FAILED → PENDING_EXTRACTION (tylko jawny retry, attempts<cap) [nowe]

content_items (przyszłe): DRAFT → PENDING_APPROVAL → APPROVED → QUEUED → PUBLISHING
                   → NEEDS_VERIFICATION → PUBLISHED | UNCERTAIN | FAILED
                   (UNCERTAIN = skutek niepotwierdzony; NIGDY auto-retry publikacji)

SAFE MODE (przyszłe): flaga systemowa (DB), ortogonalna do statusów; wejście automatyczne
                   (progi błędów), wyjście WYŁĄCZNIE ręczne; PolicyEngine czyta przy każdym checku.
```

Zasada przekrojowa: **każde przejście przez metodę repozytorium z walidacją stanu poprzedniego** (dziś `mark_*` wykonują ślepy UPDATE — np. `mark_research_run_partial` przestawi także COMPLETE, gdyby ktoś go wywołał). Dodać `WHERE status IN (...)` + zwrot liczby zmienionych wierszy.

## 10. Problemy z resumability i idempotency

- Wznawialność A2 i B: **dobra i przetestowana** (łącznie z symulacją restartu) ✅.
- Idempotencja discovery: **brak** — ponowny start na tym samym temacie = nowy pełny płatny cykl (P1-6).
- Idempotencja resume na wyczerpanym PARTIAL: pusta pętla ponownie stempluje stany (P1-5) — nieszkodliwa kosztowo, szkodliwa dla audytu.
- Brak **locków**: dwa równoległe procesy mogą wziąć tych samych PENDING_EXTRACTION kandydatów → podwójny koszt ekstrakcji (zapis idempotentny, koszt nie). Lokalnie-ręcznie znikome; wymóg dla schedulera (sekcja 8/16: leases).
- Brak rekonsyliacji po crashu: nic nie sprząta wierszy RUNNING po zabitym procesie (P1-2).
- Migracje nieodporne na częściową awarię (P2-5).

## 11. Problemy z kosztami

- Kanon (model_usage) zdrowy; koszty przy sukcesie/błędzie/partial zapisywane we wszystkich przepływach research ✅ (dwa realne incydenty to potwierdziły).
- **Cache'e kosztu niespójne** (P1-2/P2-2). **Retry poza estymatą** (P1-3). **Timeout może być zbilowany i niezapisany** (P1-3 — udokumentować jako ryzyko rezydualne).
- Estymacja vs koszt rzeczywisty: rozdzielone poprawnie (conservative/expected + jawne „to nie jest hard cap") ✅ — wymóg audytu spełniony przez ADR-016/020.
- Dwie kalibracje (P2-1). Cache tokens: przechwytywane w v2 (+topics), wyceniane w UsageTracker ✅, ale nieużywane aktywnie (P2-12).
- Koszt per source/karta: policzalne z model_usage per task ✅; brak widoku/raportu agregującego (przyszły panel).
- Budżet miesięczny nadrzędny: egzekwowany ✅; okno dzienne w UTC (P2-4).

## 12. Problemy z Policy Engine

Patrz P1-10 (pokrycie 3/14, martwe pola konta, lista ścieżek omijających), P1-7 (kill-switch nie-runtime), P1-4 (brak per-run cap). Dodatkowo: `AccountMode.COMMENT_ONLY/DRAFT_ONLY/RESEARCH_ONLY` — tryby zdefiniowane, żaden check ich nie egzekwuje (dziś nieszkodliwe — nie ma akcji do blokowania — ale bramka musi powstać PRZED generatorami treści, nie po).

## 13. Problemy z A1/A2/B

- Podział ról **logiczny i dobrze przetestowany** (12 testów; częściowe wyniki zachowywane; B ponawialny bez fetchu; injection neutralizowany na wejściu A1 i wyjściu A2/B) ✅.
- **A1 nie robi za dużo** ✅ (tylko URL+title, JSONL).
- **A2 nie czyta treści źródła** — search-o-URL zamiast fetch (P0-2.1); przy 0 searchy — czysta wiedza modelu z samooceną VERIFIED (P0-2.2).
- **„Każde twierdzenie ma źródło i dowód"** — strukturalnie: twierdzenie→URL jest; **dowód** (treść, z której pochodzi) — nie jest utrwalany żaden fragment/cytat. Rekomendacja na po-fetchu: pole `evidence_excerpt` per twierdzenie (krótki cytat + offset), co uczyni fact-audit artykułów wykonalnym.
- Surowe dane źródeł w dokumentacji: **nie** — raw responses idą do `data/debug/` (gitignored), do docs trafiają tylko podsumowania ✅.
- `research_min_sources` znaczy 3 różne rzeczy w 3 przepływach (surowe zebrane / EXTRACTED / nie-FAILED w karcie) — ujednolicić przy P0-2(b).

## 14. Problemy z przyszłym Playwrightem (ocena planu — bez uruchamiania)

Plan (SUBSTACK_INTEGRATION.md + BrowserPort) jest **zasadniczo dobry**: dedykowany profil ✅, trwała sesja ✅, ręczne pierwsze logowanie ✅, screenshot ✅, stop-conditions sesji/UI ✅, brak nieudokumentowanych endpointów ✅. Luki do domknięcia PRZED implementacją:
1. **Idempotencja publikacji nie jest zaprojektowana**: brak `idempotency_key`/sprawdzenia „czy ten content już wisi" przed kliknięciem; §7.6 nie ma kroku „verify-before-publish".
2. **Wynik niepewny**: brak statusu `UNCERTAIN` (klik wykonany, potwierdzenia brak — np. timeout po submit). Reguła musi brzmieć: **UNCERTAIN nigdy nie jest retry'owane automatycznie** — wymaga odczytu stanu (czy post istnieje?) lub człowieka. To samo ryzyko co „timeout w API może być zbilowany" — tu „timeout w przeglądarce może być opublikowany".
3. **Pojedynczy Chromium**: nigdzie nie zapisany jako inwariant — scheduler musi serializować joby browserowe (jeden worker/lease na kind=browser).
4. `max_consecutive_browser_errors: 3` istnieje w configu — bez konsumenta; podpiąć pod SAFE MODE.
5. Screenshot PO każdej akcji jest w planie; dodać screenshot PRZY BŁĘDZIE jako obowiązkowy, z zapisem do `screenshots` (tabela czeka od 0001).

## 15. Problemy z migracją na VPS

- **Przenośność kodu: dobra.** Zero absolutnych ścieżek Windows (PROJECT_ROOT z położenia pliku; pathlib wszędzie; `reconfigure(utf-8)` jest no-op na Linuksie; testy nie zależą od Windows).
- Do zrobienia (kolejność przy fazie VPS): WAL+busy_timeout (P1-8, można od razu), runtime-writes poza repo (P2-11), jawny krok migracji (P2-10), backup SQLite (`VACUUM INTO`/`.backup` przed oknami publikacji — dziś BRAK jakiegokolwiek backupu), rotacja logów (LogNotification → stdout: na VPS journald wystarczy na start), healthcheck (dopiero z panelem/schedulerem), Dockerfile (python:3.12-slim + `playwright install --with-deps chromium`, wolumeny: `/app/data`, `/app/config`; browser-profile w wolumenie), `.env` → env vars kontenera (SecretStorePort już to abstrahuje ✅).
- **SQLite na VPS jest OK** dla tej skali (jeden worker + panel readonly z WAL). Postgres = dopiero gdy pojawi się realna współbieżność zapisu. Nie przyspieszać tej migracji.

## 16. Proponowany docelowy podział modułów

Bez zmian granic istniejących modułów (core/llm/policies/research/workflows/storage/ports — zostają). Dodać w kolejności faz:
- `app/scheduler/` — tabela `jobs` + worker (sekcja 18); ZANIM Playwright.
- `app/browser/` — adapter BrowserPort (Playwright) + `browser_actions` log.
- `app/workflows/articles|notes|comments/` — każdy startuje od bramki Policy, nie od generatora.
- `app/metrics/` — kolektor → `metrics_daily` (tabela czeka).
- `app/ui/` — panel FastAPI (readonly + approvals + kill-switch DB-flag).
Skonsolidować: `scripts/run_capped_research.py` → cienki wrapper na wspólny runner w `app/` (jedno wejście, P0-3).

## 17. Proponowane interfejsy między modułami

- **Scheduler → Orchestrator:** `execute(job) -> JobResult` ; job niesie `idempotency_key`, `account_id`, `kind`, `payload`.
- **Orchestrator → PolicyEngine:** JEDEN punkt: `check(action: ProposedAction, ctx: PolicyContext) -> PolicyDecision` (ctx: konto+poziom+liczniki+flagi systemowe z DB). Istniejące `check_can_run/check_budget` stają się wewnętrznymi składnikami.
- **Workflows → StoragePort:** bez zmian (typowane metody; specyfikację §B.6 dostosować do kodu, nie odwrotnie).
- **Research → FetchPort (nowy, mały):** `fetch(url) -> FetchedDocument(text, status, retrieved_at)` — adapter: narzędzie web_fetch API teraz, lokalny fetcher później; A2 dostaje treść zamiast „opinii o URL-u" (P0-2c).
- **Browser → skutek:** każda metoda publikująca zwraca `ActionOutcome(status: CONFIRMED|UNCERTAIN|FAILED, external_url?, screenshot_path)` — nigdy gołe str.

## 18. Proponowane tabele i statusy (delta względem stanu)

```sql
-- 0006 (przy P1-1/P1-9):
ALTER TABLE research_runs ADD COLUMN flow TEXT NOT NULL DEFAULT 'two_stage';
-- backfill: 'staged' gdzie EXISTS candidates; 'single' dla 1b649314

-- 0007 (przy P1-5):
ALTER TABLE research_source_candidates ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
-- + status 'PARTIAL_EXHAUSTED' w research_runs (wartość, nie kolumna)

-- 0008 (przy schedulerze):
CREATE TABLE jobs (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, account_id TEXT NOT NULL,
  payload_json TEXT, status TEXT NOT NULL DEFAULT 'QUEUED',   -- QUEUED|LEASED|DONE|FAILED|CANCELLED
  priority INTEGER NOT NULL DEFAULT 100,
  earliest_run_at TEXT, deadline_at TEXT,
  idempotency_key TEXT UNIQUE,                 -- klucz anty-dublowej publikacji
  lease_owner TEXT, lease_expires_at TEXT,     -- job lock; restart = wygasły lease
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
  schedule_reason TEXT,                        -- "powód wybranej godziny"
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE system_flags (                    -- kill-switch/SAFE MODE runtime (P1-7)
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT, reason TEXT
);
-- content_items: statusy jak w sekcji 9 (QUEUED/PUBLISHING/NEEDS_VERIFICATION/UNCERTAIN)
```

Scheduler-worker: jedna pętla; `SELECT … WHERE status='QUEUED' AND earliest_run_at<=now ORDER BY priority, deadline` → lease (UPDATE z warunkiem) → egzekucja → DONE/FAILED; kind='browser' serializowany globalnie (jeden lease naraz); okna redakcyjne z configu filtrują earliest_run_at; po restarcie: wygasłe lease wracają do QUEUED — publikacyjne joby wracają jako **NEEDS_VERIFICATION**, nie „wykonaj ponownie".

## 19. Plan napraw w kolejności (+ 20. wpływ na kod, + 21. pliki)

| # | Naprawa | Wpływ na istniejący kod | Pliki | Rozmiar |
|---|---|---|---|---|
| 1 | **P0-3**: zablokować `main.py run-research --real` (STOP z komunikatem) | zero ryzyka; 1 test dochodzi | runner.py, main.py, test | XS |
| 2 | **P0-1**: SUCCESS na sukcesie (real), DRY_RUN bez zmian | 5 miejsc `finish_run`; testy dry_run nietknięte | pipeline.py, discover.py, +testy | S |
| 3 | **P0-2a/b**: wymuszenie UNVERIFIED przy 0-search + próg `min_verified_sources` w walidacji (config, egzekwowany w realnych runach) | walidacja dostaje 1 parametr; fake'i już zwracają VERIFIED — testy stabilne | anthropic_client.py, validation.py, pipeline.py, config, +testy | S |
| 4 | **P1-1/P1-9**: migracja 0006 `flow` + guardy resume; usunięcie `_detect_flow` | resume-funkcje: +walidacja; CLI: −sniffing | migracja, models, repositories, pipeline, CLI, +testy | M |
| 5 | **P1-2**: `runs.cost_usd` świeży przy każdym wyjściu etapu; polityka statusu między-etapowego | staged funkcje: po 1-2 linie | pipeline.py, +testy | S |
| 6 | **P1-3**: estymata ×(1+retries) + re-check budżetu przed retry + wpis ryzyka rezydualnego | bramki: mnożnik; klient: callback checku | cost_estimator, anthropic_client, pipeline, ERRORS_AND_FAILURES | S/M |
| 7 | **P1-4**: `check_run_budget` w PolicyEngine; CLI deleguje | −duplikacja w CLI | policy_engine, run_capped_research, +testy | S |
| 8 | **P1-6**: topics→USED po COMPLETE + guard re-researchu | discover/pipeline/runner po 1 zmianie | pipeline, runner, +testy | S |
| 9 | **P1-5**: attempts + PARTIAL_EXHAUSTED + jawny retry-failed | migracja 0007 | migracja, models, repositories, pipeline, CLI, +testy | M |
| 10 | **P1-8**: WAL+busy_timeout | 2 linie, zero ryzyka | db.py | XS |
| 11 | **P2-9**: higiena dokumentów (banery, statusy ADR) | tylko docs | DECISIONS, IMPLEMENTATION_PLAN | S |
| 12 | **P0-2c (faza 2)**: FetchPort + realny fetch w A2 + evidence_excerpt | nowy port; A2 prompt/parser | ports/fetch.py (nowy), anthropic_client, base, pipeline, migracja | M/L |
| 13 | **P1-7**: system_flags + runtime kill-switch (razem ze schedulerem) | PolicyEngine czyta DB | migracja 0008, policy_engine | M |

Pozycje 1-3 = **bloker przed kolejnym płatnym wywołaniem**. Pozycje 4-8 = przed kolejną serią realnych testów. 9-13 = przed odpowiednimi fazami.

## 22. Testy do dodania

1. `real-mode success → runs.status=SUCCESS` (P0-1) — dziś ŻADEN test nie wykonuje ścieżki sukcesu z dry_run=False.
2. `extraction z max_uses=0 → wszystkie karty UNVERIFIED niezależnie od odpowiedzi modelu` + `validate: same UNVERIFIED → REJECT` (P0-2).
3. `main.py run-research --real → STOP` (P0-3).
4. `resume_staged na legacy-PARTIAL → ValueError` i odwrotnie (P1-1, po kolumnie flow).
5. `runs.cost_usd == sum(model_usage)` po każdej ścieżce staged, w tym B-failure (P1-2).
6. Retry-budget: drugi attempt blokowany, gdy budżet wyczerpany między próbami (P1-3).
7. Stan-tranzycje: macierz dozwolonych przejść research_runs (każde `mark_*` na złym stanie poprzednim → odmowa) — po dodaniu walidacji.
8. Concurrency: dwa równoległe `run_source_extraction` na tym samym runie nie ekstrahują tego samego kandydata dwukrotnie (po lockach; do tego czasu — test dokumentujący obecne zachowanie).
9. Migration idempotency: częściowo-zaaplikowana migracja nie zakleszcza runnera (P2-5).
10. Topic USED: drugi research na COMPLETE temacie odmawia bez `--force` (P1-6).
11. Duplicate publication (faza browser): ten sam idempotency_key → drugi job odrzucony; outcome UNCERTAIN → zero auto-retry.
12. SAFE MODE (faza flag): flaga w DB zatrzymuje następny check w trwającej pętli A2.
13. Pełny E2E dry-run: topics → staged research → (przyszły) draft — jeden test integracyjny przez wszystkie workflow (dziś topics i research testowane osobno).
14. Budżet-race: koszt dopisany między checkiem a recordem nie łamie miesięcznego nadrzędnego (dokumentujący).

## 23. Czego NIE przebudowywać teraz

- **Nie usuwać** legacy pipeline'ów (single, two-stage) ani ich 24 testów — do wygaszenia dopiero po udanym realnym runie staged (deprecation, potem osobna decyzja).
- **Nie konsolidować** trzech tabel źródeł — po wygaszeniu legacy, nie przed.
- **Nie wdrażać** Postgres, Dockera, mikroserwisów, kolejek zewnętrznych — SQLite+WAL i modularny monolit wystarczą daleko poza obecną skalę.
- **Nie pisać** generatorów artykułów/Notes/komentarzy przed bramkami Policy dla tych akcji (kolejność: bramka → generator).
- **Nie przepisywać** StoragePort pod generyczną specyfikację §B.6 — kod jest lepszy; poprawić specyfikację.
- **Nie ruszać** warstwy dokumentacji historycznej (SUPERSEDED działa poprawnie).
- **Nie optymalizować** prompt cachingiem przed potwierdzeniem architektury na żywo.

## 24. Najbliższy bezpieczny etap implementacyjny

**Krok 1 (offline, ~0,5 dnia):** naprawy #1-3 z sekcji 19 (P0-3, P0-1, P0-2a/b) + testy 1-3 z sekcji 22. Zero API, zero ryzyka regresu (85 testów musi zostać zielonych).

**Krok 2 (jeden mały realny test — wymaga osobnej zgody):** konfiguracja ZMIENIONA względem F.9, bo audyt wykazał, że wariant z `--max-web-searches-per-source 0` nie dowodzi researchu (P0-2):

```
python scripts/run_capped_research.py --topic-id 2 \
  --discovery-max-searches 1 --max-sources 2 --max-web-searches-per-source 1 \
  --max-cost-usd 0.30
```
Projekcja: conservative ≈ 0,297 USD (mieści się w capie 0,30), expected ≈ 0,115 USD. Test dowodzi wtedy: mechaniki A1/A2/B na żywo ORAZ ekstrakcji z realnym wyszukiwaniem per źródło ORAZ poprawnego SUCCESS-statusu (po naprawie P0-1).

**Krok 3 (offline):** naprawy #4-8 (flow, koszty-cache, retry-budget, per-run cap, topic USED).

Dopiero po tym: generator artykułów — zaczynając od bramki Policy (autonomy/mode/limity), nie od promptów.

---

*Audyt wykonany w trybie tylko-do-odczytu. Żaden plik kodu nie został zmieniony. Raport czeka na decyzję właściciela.*
