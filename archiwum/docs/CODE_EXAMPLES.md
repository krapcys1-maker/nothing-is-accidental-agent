# CODE_EXAMPLES

## Cel

Zbiór krótkich, samodzielnych fragmentów kodu ilustrujących **kluczowe mechanizmy** systemu (Policy Engine, tracking kosztów, porty, przepływy). Służy dwóm celom: (1) szybkie wprowadzenie dla każdego, kto czyta repo, (2) gotowy materiał do końcowego artykułu na „Chaos Engine" (pokazanie, jak działa deterministyczna bramka i liczenie kosztów). Dłuższe pliki źródłowe trzymamy w `docs/code-snippets/`; tu lądują skrócone, opisane wycinki.

## Zasady

- Fragment musi być czytelny bez reszty repo (krótki, z komentarzem po co jest).
- Kod zgodny z rzeczywistą implementacją (aktualizuj, gdy kod się zmienia).
- Bez sekretów: żadnych kluczy, tokenów, realnych danych.
- Każdy fragment ma nagłówek: czego dotyczy, z którego pliku pochodzi, co pokazuje.

## Szablon wpisu

```markdown
### [YYYY-MM-DD] Tytuł fragmentu
- **Dotyczy:** np. Policy Engine — kontrola budżetu
- **Plik źródłowy:** app/policies/policy_engine.py
- **Co pokazuje:** jedno–dwa zdania

​```python
# ...krótki fragment (10–40 linii)...
​```

- **Uwagi:** kontekst, ograniczenia, powiązania
```

---

## Fragmenty

### [2026-07-11] Policy Engine — budżet z priorytetem miesięcznym
- **Dotyczy:** deterministyczna bramka kosztów (ADR-012)
- **Plik źródłowy:** app/policies/policy_engine.py
- **Co pokazuje:** limit miesięczny jest nadrzędny nad dziennym; po jego osiągnięciu wszystkie płatne działania są zatrzymywane. Model językowy nie może tego ominąć — decyzja jest czysto deterministyczna.

```python
def check_budget(self, estimated_cost_usd: float) -> PolicyDecision:
    now = self._clock.now()
    month_spent = self._storage.sum_real_cost_usd(now.strftime("%Y-%m"))
    day_spent = self._storage.sum_real_cost_usd(now.strftime("%Y-%m-%d"))
    monthly = self._settings.max_monthly_cost_usd   # 40.00
    daily = self._settings.max_daily_cost_usd        # 2.00

    # Limit miesięczny ma bezwzględny priorytet (ADR-012).
    if self._settings.monthly_limit_has_priority and month_spent >= monthly:
        return PolicyDecision.block("BUDGET_MONTHLY_REACHED",
                                    "Osiągnięto limit miesięczny — stop wszystkich płatnych działań.")
    if month_spent + estimated_cost_usd > monthly:
        return PolicyDecision.block("BUDGET_MONTHLY_EXCEEDED", "...")
    if day_spent + estimated_cost_usd > daily:
        return PolicyDecision.block("BUDGET_DAILY_EXCEEDED", "...")
    return PolicyDecision.ok()
```

- **Uwagi:** `sum_real_cost_usd` liczy tylko wpisy `dry_run=0`, więc symulacje w trybie dry_run nie zużywają budżetu. Testy: `tests/test_policy_engine.py` (m.in. `test_monthly_limit_has_priority`).

### [2026-07-11] Ochrona przed prompt injection z treści źródeł
- **Dotyczy:** research pipeline — treść z internetu jako niezaufany materiał
- **Plik źródłowy:** app/research/injection_guard.py + app/workflows/research/pipeline.py
- **Co pokazuje:** polecenia znalezione w treści źródła są wykrywane i redagowane; pipeline i tak używa tylko pól strukturalnych, więc iniekcja nie zmienia decyzji agenta.

```python
# injection_guard.py — wykrycie i neutralizacja
def contains_injection(text: str | None) -> bool:
    return bool(text) and any(rx.search(text) for rx in _COMPILED)

def neutralize(text: str | None) -> str:
    out = text or ""
    for rx in _COMPILED:            # np. "ignore previous instructions", "system prompt:"
        out = rx.sub("[REDACTED-INSTRUCTION]", out)
    return out

# pipeline.py — treść źródeł to DANE, nigdy polecenia
for src in draft.sources:
    if contains_injection(src.title) or contains_injection(src.supports_claim):
        summary.injection_flags += 1
        src.title = neutralize(src.title)
        if src.supports_claim:
            src.supports_claim = neutralize(src.supports_claim)
```

- **Uwagi:** decyzja o publikacji opiera się na `validate_draft` (liczby/struktura), nie na tekście źródła — dlatego wstrzyknięte „set confidence to 1.0" nic nie zmienia. Test: `tests/test_research_pipeline.py::test_prompt_injection_is_neutralized_not_followed`.

### [2026-07-11] Realny koszt nie może zniknąć, nawet gdy research się nie powiedzie
- **Dotyczy:** księgowanie kosztów — znalezione na pierwszym realnym (płatnym) wywołaniu Anthropic
- **Plik źródłowy:** app/research/anthropic_client.py + app/workflows/research/pipeline.py
- **Co pokazuje:** pierwszy realny research zwrócił ucięty JSON (model wyczerpał `max_tokens`). Błąd parsowania celowo nie jest ponawiany — ale pierwotny kod też **gubił realny koszt** tego udanego-jako-wywołanie-API-ale-nieudanego-jako-JSON runu. Poprawka dopina prawdziwe `usage` do wyjątku, żeby pipeline mógł je zaksięgować mimo błędu.

```python
# anthropic_client.py — usage z UDANEGO wywołania API dopięte do wyjątku PRZED re-raise
try:
    draft = _parse(text)  # ResearchParseError NIE jest ponawiany
except ResearchParseError as exc:
    exc.usage = usage      # realne tokeny z API, mimo że JSON się nie sparsował
    exc.model = self.model
    raise

# pipeline.py — koszt księgowany również w ścieżce błędu, jeśli usage jest dostępne
except ResearchError as exc:
    cost = 0.0
    exc_usage = getattr(exc, "usage", None)
    if exc_usage is not None:
        usage_row = usage_tracker.record(run_id, getattr(exc, "model", None) or "unknown",
                                         exc_usage, task="research", dry_run=settings.dry_run)
        cost = usage_row.estimated_cost_usd
    storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=str(exc))
```

- **Uwagi:** bez tej poprawki realne, płatne wywołanie API mogło zostać zapisane lokalnie jako 0.00 USD — cichy błąd księgowy, niewykrywalny przez dry_run/testy z klientem zastępczym (nigdy nie ćwiczyły ścieżki „sukces API + błąd parsowania"). Test: `tests/test_research_pipeline.py::test_real_usage_recorded_even_when_parse_fails`. Pełny opis incydentu: `docs/ERRORS_AND_FAILURES.md` (2026-07-11 19:09 UTC).

### [2026-07-11] Kalibrowany estymator kosztu — skalowany z liczbą wyszukiwań, nie płaski bufor
- **Dotyczy:** naprawa błędu estymacji (realny koszt 0.25 USD wobec szacunku 0.095 USD, błąd ~+163%)
- **Plik źródłowy:** app/research/cost_estimator.py
- **Co pokazuje:** koszt napędzany wynikami wyszukiwania rośnie z LICZBĄ wyszukiwań, więc estymator skaluje per-search, zamiast zakładać stały bufor tokenów. Margines bezpieczeństwa jest wymagany (błąd poniżej minimum rzuca wyjątek).

```python
_CALIBRATION_REAL_TOKEN_COST_USD = 0.21   # z konsoli Anthropic (2026-07-11)
_CALIBRATION_ACTUAL_SEARCHES = 4
_CALIBRATION_MAX_OUTPUT_TOKENS = 3000
MIN_SAFETY_MARGIN = 0.50

def _reconstructed_input_cost_per_search_usd(settings: Settings) -> float:
    price_output = settings.pricing.get("output_per_mtok", 5.0)
    reconstructed_output_cost = _CALIBRATION_MAX_OUTPUT_TOKENS / 1_000_000 * price_output
    reconstructed_input_cost = max(0.0, _CALIBRATION_REAL_TOKEN_COST_USD - reconstructed_output_cost)
    return reconstructed_input_cost / _CALIBRATION_ACTUAL_SEARCHES

def estimate_worst_case_search_call_usd(settings, max_web_searches, max_output_tokens=3000,
                                        safety_margin=MIN_SAFETY_MARGIN) -> WorstCaseEstimate:
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError(f"safety_margin poniżej wymaganego minimum ({MIN_SAFETY_MARGIN}).")
    p = settings.pricing
    search_fee = max_web_searches / 1_000 * p.get("web_search_per_1k", 0.0)
    search_driven_token_cost = max_web_searches * _reconstructed_input_cost_per_search_usd(settings)
    output_cost = max_output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)
    subtotal = search_fee + search_driven_token_cost + output_cost
    return WorstCaseEstimate(..., total_usd=round(subtotal * (1 + safety_margin), 6))
```

- **Uwagi:** kalibracja z n=1 (jedna realna obserwacja) — jawnie oznaczona jako przybliżenie do doprecyzowania. Test regresyjny: `tests/test_cost_estimator.py::test_new_estimator_would_not_have_cleared_the_failed_run` — dla parametrów nieudanego runu (max_uses=6, max_tokens=3000) nowy estymator MUSI zwrócić >= realnego kosztu (0.25 USD).

### [2026-07-12] Atomowy zapis wyników etapu A — źródła nigdy nie zostają „w pamięci"
- **Dotyczy:** wznawialność Research Pipeline (ADR-019) — trwałość między etapem A i etapem B
- **Plik źródłowy:** app/storage/repositories.py + app/workflows/research/pipeline.py
- **Co pokazuje:** wyniki web search (kosztowne, realnie opłacone) są zapisywane do bazy w JEDNYM commit razem ze zmianą statusu, natychmiast po sukcesie etapu A — zanim pipeline w ogóle sprawdzi, czy źródeł jest wystarczająco dużo do kontynuacji.

```python
# repositories.py — jeden commit: źródła + status, żadnego stanu pośredniego
def mark_research_stage_a_success(
    self, research_run_id: str, sources: list[ResearchSourceRecord]
) -> list[ResearchSourceRecord]:
    cur = self._conn.cursor()
    inserted = [self._insert_research_source(research_run_id, s) for s in sources]
    cur.execute(
        "UPDATE research_runs SET status=?, stage_a_completed_at=datetime('now'), "
        "updated_at=datetime('now') WHERE id=?",
        (ResearchRunStatus.SOURCE_COLLECTED.value, research_run_id),
    )
    self._conn.commit()          # źródła i status stają się trwałe razem, albo wcale
    return inserted

# pipeline.py — zapis natychmiast po etapie A, PRZED progiem "czy wystarczy źródeł"
gathered = research_client.gather_sources(plan, max_searches=settings.research_max_web_searches)
injection_flags = _neutralize_sources_in_place(gathered.sources)

storage.mark_research_stage_a_success(run_id, [
    ResearchSourceRecord(research_run_id=run_id, url=s.url, title=s.title,
                          author_or_org=s.author_or_org, published_at=s.published_at,
                          source_type=s.source_type, key_facts=list(s.key_facts),
                          verification_status=s.verification)
    for s in gathered.sources
])
storage.add_research_stage_result(run_id, ResearchStageName.A, ResearchStageStatus.SUCCESS)

if len(gathered.sources) < settings.research_min_sources:
    storage.mark_research_run_partial(run_id, error="too few sources after stage A")
    return  # etap B (płatny) w ogóle nie jest wołany — źródła i tak zostają w bazie
```

- **Uwagi:** SQLite gwarantuje, że `INSERT` źródeł i `UPDATE` statusu albo powiodą się oba, albo żaden — nie ma stanu „źródła zapisane, ale status wciąż PENDING". To zamyka lukę architektoniczną: dwuetapowy podział (ADR-016) chronił przed uciętym JSON-em WEWNĄTRZ jednego wywołania, ale nie chronił przed awarią procesu MIĘDZY etapem A i B — ta poprawka adresuje właśnie to. Test: `tests/test_research_resumability.py::test_stage_a_success_persists_research_run_and_sources`.

### [2026-07-12] Wznowienie etapu B — zero web search, dowód na poziomie testu
- **Dotyczy:** wznawialność Research Pipeline (ADR-019) — `resume_research_stage_b`
- **Plik źródłowy:** app/workflows/research/pipeline.py
- **Co pokazuje:** wznowienie czyta źródła WYŁĄCZNIE z bazy i nigdy nie woła `gather_sources` — więc nie ponawia kosztownego web search, nawet jeśli etap B trzeba powtórzyć kilka razy.

```python
def resume_research_stage_b(research_run_id: str, account: Account, *, settings, storage,
                            research_client, usage_tracker, policy, notifier, clock=None,
                            research_log=None) -> ResearchRunSummary:
    research_run = storage.get_research_run(research_run_id)
    if research_run is None or research_run.status not in (
        ResearchRunStatus.SOURCE_COLLECTED, ResearchRunStatus.PARTIAL,
    ):
        raise ValueError(f"Run {research_run_id} nie jest wznawialny (status={research_run and research_run.status}).")

    source_records = storage.list_research_sources(research_run_id)
    if len(source_records) < settings.research_min_sources:
        # Etap B nie szuka, więc nie ma jak naprawić "za mało źródeł" — odmowa BEZ wołania API.
        storage.mark_research_run_partial(research_run_id, error="still too few sources for stage B")
        return ResearchRunSummary(status="REJECT", reason="TOO_FEW_SOURCES", cost_usd=0.0)

    gathered = SourceGatheringResult(
        sources=[GatheredSource(url=r.url, title=r.title, author_or_org=r.author_or_org,
                                published_at=r.published_at, source_type=r.source_type,
                                key_facts=r.key_facts, verification=r.verification_status)
                for r in source_records],
        usage=Usage(), model="",   # nieużywane przez synthesize_card — tylko gather_sources je produkuje
    )
    # UWAGA: `research_client.gather_sources(...)` NIGDY nie jest tu wołane.
    card_draft, usage, model = research_client.synthesize_card(plan, gathered)
    ...
```

- **Uwagi:** test `test_resume_stage_b_never_calls_gather_sources_and_survives_restart` dowodzi tego na dwóch poziomach: (1) klient zastępczy rzuca `AssertionError`, jeśli `gather_sources` w ogóle zostanie wywołane, (2) cały test konstruuje NOWE instancje `PolicyEngine`/`UsageTracker`/notifiera zamiast reużywać obiekty ze świeżego runu — symulując prawdziwy restart procesu, w którym jedynym łącznikiem ze starym stanem jest `research_run_id` zapisane w bazie.

### [2026-07-12] Przebudowa Stage A: per-źródło ekstrakcja zamiast jednego JSON-a na wszystkie źródła
- **Dotyczy:** naprawa strukturalna po drugim realnym incydencie (0,123823 USD, ucięty JSON w `gather_sources` mimo lekkiego schematu) — ADR-020
- **Plik źródłowy:** app/workflows/research/pipeline.py (`run_source_extraction`) + app/storage/repositories.py
- **Co pokazuje:** zamiast jednego wywołania zbierającego WSZYSTKIE źródła naraz (gdzie ucięcie kasuje wszystko), etap A2 robi JEDNO wywołanie NA ŹRÓDŁO, zapisując wynik do bazy natychmiast — błąd źródła N nie wpływa na 1..N-1, bo są już bezpiecznie w bazie, zanim źródło N w ogóle zaczęło się przetwarzać.

```python
# pipeline.py — pętla A2: budżet sprawdzany PRZED KAŻDYM źródłem, błąd NIE przerywa pętli
for candidate_record in pending:
    budget = policy.check_budget(per_source_estimate.conservative_usd)
    if not budget.allowed:
        summary.blocked = True  # pozostali kandydaci zostają PENDING_EXTRACTION, można wznowić
        break

    candidate = SourceCandidate(url=candidate_record.url, title=candidate_record.title)
    try:
        extraction = research_client.extract_source(plan, candidate)
    except ResearchError as exc:
        # Realny koszt zachowany MIMO błędu (ten sam mechanizm co przy incydencie 11.07).
        if exc.usage is not None:
            usage_tracker.record(research_run_id, exc.model or "unknown", exc.usage,
                                 task="research_extract", dry_run=settings.dry_run)
        storage.mark_source_candidate_failed(candidate_record.id, error=str(exc))
        failed_now += 1
        continue  # <- KLUCZOWE: pętla leci dalej, źródło N+1 nie wie i nie dba o los źródła N

    storage.update_source_candidate_extracted(candidate_record.id, title=extraction.card.title, ...)
    extracted_now += 1

# repositories.py — commit PO KAŻDYM źródle, nie na końcu pętli
def update_source_candidate_extracted(self, candidate_id: int, *, title, ...) -> None:
    self.conn.execute("UPDATE research_source_candidates SET ... WHERE id=?", (..., candidate_id))
    self.conn.commit()   # <- natychmiast, źródło N+1 nie czeka i nie zagraża temu zapisowi
```

- **Uwagi:** test `test_fourth_source_extraction_fails_first_three_preserved` (4 kandydatów, 4-ty pada) i `test_first_source_extraction_fails_others_unaffected` (1-szy pada) dowodzą, że kolejność i pozycja awarii nie ma znaczenia — zawsze przetrwają wszystkie źródła OPRÓCZ tego jednego, które faktycznie zawiodło. `tests/test_staged_research_extraction.py`.

### [2026-07-12] Diagnostyka: surowa odpowiedź i stop_reason zapisywane przy KAŻDYM realnym błędzie
- **Dotyczy:** oba dotychczasowe incydenty ucięcia JSON-a (11.07, 12.07) dawały tylko HIPOTEZĘ przyczyny — nie było zapisanej surowej odpowiedzi ani `stop_reason` z API do jednoznacznej weryfikacji.
- **Plik źródłowy:** app/research/diagnostics.py + app/research/anthropic_client.py
- **Co pokazuje:** `_call_anthropic` teraz zwraca też `message.stop_reason`; pipeline zapisuje surową treść + tę informację do prywatnego pliku, TYLKO dla realnych wywołań (nigdy dla FakeResearchClient/dry_run) i TYLKO treść odpowiedzi + liczby — nigdy klucz API ani nagłówki.

```python
# anthropic_client.py — stop_reason przechwytywany przy KAŻDYM wywołaniu
def _call_anthropic(self, client, prompt, *, tools, max_tokens):
    message = client.messages.create(model=self.model, max_tokens=max_tokens, ...)
    text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    stop_reason = getattr(message, "stop_reason", None)   # np. "max_tokens" / "end_turn"
    return text, usage, stop_reason

# diagnostics.py — zapis TYLKO dla realnych wywołań, zero sekretów
def write_diagnostics(data_dir: Path, diag: ResponseDiagnostics) -> Path:
    run_dir = data_dir / "debug" / "research" / diag.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{diag.stage}_raw_response.txt"   # np. "A2_source_17_raw_response.txt"
    path.write_text(f"stop_reason: {diag.stop_reason}\n...\n{diag.raw_response}", encoding="utf-8")
    return path

# pipeline.py — wywołane TYLKO gdy dry_run=False i jest coś do zapisania
def _record_diagnostics(settings, run_id, stage, *, usage, raw_text, stop_reason, ...):
    if settings.dry_run or not raw_text:
        return
    write_diagnostics(settings.data_dir, ResponseDiagnostics(run_id=run_id, stage=stage, ...))
```

- **Uwagi:** `data/` jest w całości w `.gitignore` (`data/*`), plus jawna reguła `data/debug/` dla czytelności. Testy: `test_raw_response_and_stop_reason_saved_on_extraction_error`, `test_diagnostics_file_contains_no_secrets`, `test_no_diagnostics_written_in_dry_run`.

### [2026-07-12] JSONL zamiast jednego JSON-a — uszkodzona linia nie kasuje reszty
- **Dotyczy:** etap A1 (discover_sources) — nawet NAJLŻEJSZY schemat (same URL-e) mógłby się teoretycznie uciąć przy długiej liście kandydatów; JSONL sprawia, że ucięcie kasuje tylko OSTATNI rekord, nie całą listę.
- **Plik źródłowy:** app/research/anthropic_client.py (`_parse_discovery_candidates_jsonl`)
- **Co pokazuje:** parser NIE rzuca błędu na pierwszą uszkodzoną linię — pomija ją i kontynuuje, zwracając błąd tylko, gdy ZERO linii dało się sparsować.

```python
def _parse_discovery_candidates_jsonl(text: str) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    for line in _strip_code_fence(text).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue   # <- uszkodzona/ucięta linia (najczęściej OSTATNIA) pomijana, nie fatalna
        if not isinstance(obj, dict) or not obj.get("url"):
            continue
        candidates.append(SourceCandidate(url=obj["url"], title=obj.get("title")))
    if not candidates:
        raise ResearchParseError("Brak poprawnych kandydatów w odpowiedzi JSONL.")
    return candidates
```

- **Uwagi:** testy `test_jsonl_truncated_last_record_keeps_earlier_ones` (ucięty ostatni rekord — 2 z 3 zachowane) i `test_jsonl_broken_middle_line_is_skipped_not_fatal` (uszkodzona linia W ŚRODKU też nie jest fatalna, bardziej liberalne niż wymagane minimum).
