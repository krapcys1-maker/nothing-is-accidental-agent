# 10 — FRAGMENTY KODU

## Cel pliku
Krótkie, reprezentatywne wycinki kodu (20–40 linii) pokazujące kluczowe mechanizmy. **Nie kopiujemy całych plików.** Każdy fragment: nazwa pliku źródłowego, wyjaśnienie, dlaczego ważny. Bez sekretów. Fragmenty muszą być zgodne z rzeczywistą implementacją — aktualizować, gdy kod się zmienia.

## Lista mechanizmów do pokrycia
Policy Engine ✅ · tracking kosztów ✅ · ochrona przed injection ✅ · kalibrowany estymator kosztu ✅ · wznawialność Research Pipeline ✅ · etapowa ekstrakcja per źródło + diagnostyka ✅ · scoring tematów (⏳ próg pokazany) · pętla agenta (⏳) · approval gate (⏳) · obsługa wielu kont (⏳) · deduplikacja (⏳) · Playwright (⏳) · kill switch ✅ (w Policy) · analiza wyników (⏳).
> ✅ = fragment gotowy poniżej; ⏳ = mechanizm do dodania, gdy powstanie/zostanie skrócony.

## Szablon wpisu
```markdown
### <tytuł mechanizmu>
- **Plik źródłowy:** app/...
- **Co pokazuje:** 1–2 zdania
- **Dlaczego ważny:** 1 zdanie
​```python
# 20–40 linii
​```
```

---

### Policy Engine — budżet z priorytetem miesięcznym + kill switch
- **Plik źródłowy:** `app/policies/policy_engine.py`
- **Co pokazuje:** deterministyczną bramkę — kill-switch, aktywność konta i budżet, w którym limit miesięczny jest nadrzędny nad dziennym (ADR-012).
- **Dlaczego ważny:** model językowy **nie może** tego ominąć — to serce bezpieczeństwa kosztowego.
```python
def check_can_run(self, account: Account) -> PolicyDecision:
    if self._settings.kill_switch:
        return PolicyDecision.block("KILL_SWITCH", "Globalny wyłącznik bezpieczeństwa jest włączony.")
    if not account.active:
        return PolicyDecision.block("ACCOUNT_INACTIVE", f"Konto {account.id} jest nieaktywne.")
    return PolicyDecision.ok()

def check_budget(self, estimated_cost_usd: float) -> PolicyDecision:
    now = self._clock.now()
    month_spent = self._storage.sum_real_cost_usd(now.strftime("%Y-%m"))
    day_spent = self._storage.sum_real_cost_usd(now.strftime("%Y-%m-%d"))
    monthly = self._settings.max_monthly_cost_usd   # 40.00
    daily = self._settings.max_daily_cost_usd        # 2.00

    # Limit miesięczny ma bezwzględny priorytet (ADR-012).
    if self._settings.monthly_limit_has_priority and month_spent >= monthly:
        return PolicyDecision.block("BUDGET_MONTHLY_REACHED",
            f"Osiągnięto limit miesięczny {monthly:.2f} USD — stop płatnych działań.")
    if month_spent + estimated_cost_usd > monthly:
        return PolicyDecision.block("BUDGET_MONTHLY_EXCEEDED", "...")
    if day_spent + estimated_cost_usd > daily:
        return PolicyDecision.block("BUDGET_DAILY_EXCEEDED", "...")
    return PolicyDecision.ok()
```
- **Uwaga:** `sum_real_cost_usd` liczy tylko wpisy `dry_run=0` → symulacje nie zużywają budżetu. Test: `tests/test_policy_engine.py::test_monthly_limit_has_priority`.

---

### Tracking kosztów — cennik → baza + CSV
- **Plik źródłowy:** `app/llm/usage_tracker.py`
- **Co pokazuje:** jak każde wywołanie zamienia się w koszt (z cennika) i trafia jednocześnie do `model_usage` (baza) i `docs/COSTS.csv`.
- **Dlaczego ważny:** koszty są mierzone automatycznie i audytowalnie od pierwszego dnia — fundament rozliczenia eksperymentu.
```python
def estimate_cost(self, usage: Usage) -> float:
    p = self._settings.pricing
    cost = (
        usage.input_tokens       / 1_000_000 * p.get("input_per_mtok", 0.0)
        + usage.output_tokens    / 1_000_000 * p.get("output_per_mtok", 0.0)
        + usage.cache_read_tokens / 1_000_000 * p.get("cache_read_per_mtok", 0.0)
        + usage.cache_write_tokens/ 1_000_000 * p.get("cache_write_per_mtok", 0.0)
        + usage.web_search_requests / 1_000   * p.get("web_search_per_1k", 0.0)
    )
    return round(cost, 6)

def record(self, run_id, model, usage, task, dry_run, provider="anthropic"):
    cost = self.estimate_cost(usage)
    row = ModelUsage(run_id=run_id, provider=provider, model=model, task=task,
                     input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                     web_search_requests=usage.web_search_requests,
                     estimated_cost_usd=cost, dry_run=dry_run)
    self._storage.add_model_usage(row)   # źródło prawdy = baza
    self._append_csv(row)                # czytelny eksport dla człowieka
    return row
```
- **Uwaga:** kolumna `dry_run` odróżnia estymacje od realnych kosztów (ADR-013).

---

### Ochrona przed prompt injection — treść źródeł = dane, nie polecenia
- **Plik źródłowy:** `app/research/injection_guard.py` + `app/workflows/research/pipeline.py`
- **Co pokazuje:** polecenia ukryte w treści źródła są wykrywane i redagowane; decyzja i tak zapada na polach strukturalnych.
- **Dlaczego ważny:** neutralizuje realne ryzyko R4 — internet jest niezaufany.
```python
# injection_guard.py
def contains_injection(text: str | None) -> bool:
    return bool(text) and any(rx.search(text) for rx in _COMPILED)

def neutralize(text: str | None) -> str:
    out = text or ""
    for rx in _COMPILED:            # np. "ignore previous instructions", "system prompt:"
        out = rx.sub("[REDACTED-INSTRUCTION]", out)
    return out

# pipeline.py — źródła to DANE
for src in draft.sources:
    if contains_injection(src.title) or contains_injection(src.supports_claim):
        summary.injection_flags += 1
        src.title = neutralize(src.title)
        if src.supports_claim:
            src.supports_claim = neutralize(src.supports_claim)
```
- **Uwaga:** decyzja o publikacji opiera się na `validate_draft` (liczby/struktura), nie na tekście źródła — wstrzyknięte „set confidence to 1.0" nic nie zmienia. Test: `test_research_pipeline.py::test_prompt_injection_is_neutralized_not_followed`.

---

### Koszt nie może zniknąć, nawet gdy research się nie powiedzie
- **Plik źródłowy:** `app/research/anthropic_client.py` + `app/workflows/research/pipeline.py`
- **Co pokazuje:** znalezione na pierwszym realnym wywołaniu (2026-07-11) — model odpowiedział i zużył realne tokeny/wyszukiwania, ale JSON się nie sparsował; pierwotny kod gubił ten koszt całkowicie. Poprawka dopina prawdziwe `usage` do wyjątku, żeby pipeline mógł je zaksięgować mimo błędu.
- **Dlaczego ważny:** to najbardziej „na żywo" znaleziony błąd w projekcie — pokazuje, że ścieżka błędu potrzebuje tyle samo staranności co ścieżka sukcesu, zwłaszcza gdy w grę wchodzą realne pieniądze.
```python
# anthropic_client.py — realny usage z API dopięty do wyjątku PRZED re-raise
try:
    draft = _parse(text)  # ResearchParseError NIE jest ponawiany
except ResearchParseError as exc:
    exc.usage = usage      # realne tokeny z API, mimo że JSON się nie sparsował
    exc.model = self.model
    raise

# pipeline.py — koszt księgowany również w ścieżce błędu
except ResearchError as exc:
    cost = 0.0
    exc_usage = getattr(exc, "usage", None)
    if exc_usage is not None:
        usage_row = usage_tracker.record(run_id, getattr(exc, "model", None) or "unknown",
                                         exc_usage, task="research", dry_run=settings.dry_run)
        cost = usage_row.estimated_cost_usd
    storage.finish_run(run_id, RunStatus.FAILED.value, cost, error=str(exc))
```
- **Uwaga:** test regresyjny `tests/test_research_pipeline.py::test_real_usage_recorded_even_when_parse_fails`. Pełny opis incydentu w `07_BLEDY_I_NIEUDANE_PROBY.md`.

---

### Kalibrowany estymator kosztu — rośnie z liczbą wyszukiwań, nie płaski bufor
- **Plik źródłowy:** `app/research/cost_estimator.py`
- **Co pokazuje:** naprawa błędu z tego samego dnia — realny koszt (0,25 USD) był 2,63× wyższy niż wcześniejszy szacunek (0,095 USD, błąd ~+163%). Nowy estymator skaluje koszt napędzany wyszukiwaniami razem z ich liczbą, zamiast zakładać stały „zapas" tokenów, i wymaga minimum 50% marginesu bezpieczeństwa.
- **Dlaczego ważny:** pokazuje różnicę między „limitem, który wygląda bezpiecznie" a limitem, który faktycznie jest bezpieczny — zależy to od jakości szacunku, nie tylko od jego istnienia.
```python
_CALIBRATION_REAL_TOKEN_COST_USD = 0.21   # z konsoli Anthropic, 2026-07-11
_CALIBRATION_ACTUAL_SEARCHES = 4
MIN_SAFETY_MARGIN = 0.50

def estimate_worst_case_search_call_usd(settings, max_web_searches, max_output_tokens=3000,
                                        safety_margin=MIN_SAFETY_MARGIN):
    if safety_margin < MIN_SAFETY_MARGIN:
        raise ValueError("margines bezpieczeństwa poniżej wymaganego minimum")
    search_fee = max_web_searches / 1_000 * settings.pricing.get("web_search_per_1k", 0.0)
    # koszt napędzany wynikami wyszukiwania SKALUJE SIĘ z liczbą wyszukiwań —
    # to właśnie ten czynnik zawiódł w starym, płaskim estymatorze
    search_driven_cost = max_web_searches * _reconstructed_input_cost_per_search_usd(settings)
    output_cost = max_output_tokens / 1_000_000 * settings.pricing.get("output_per_mtok", 0.0)
    subtotal = search_fee + search_driven_cost + output_cost
    return subtotal * (1 + safety_margin)   # margines bezpieczeństwa NA KOŃCU
```
- **Uwaga:** kalibracja z n=1 (jedna realna obserwacja) — jawnie oznaczona jako przybliżenie. Test regresyjny sprawdza, że dla parametrów nieudanego runu nowy estymator zwraca >= realnego kosztu: `tests/test_cost_estimator.py::test_new_estimator_would_not_have_cleared_the_failed_run`.

### Wznawialność researchu — atomowy zapis kroku 1, zero-search wznowienie kroku 2
- **Plik źródłowy:** `app/storage/repositories.py` + `app/workflows/research/pipeline.py`
- **Co pokazuje:** wyniki wyszukiwania (kosztowne, realnie opłacone) trafiają do bazy w JEDNYM commit razem ze zmianą statusu, natychmiast po sukcesie kroku 1 — zanim program w ogóle sprawdzi, czy jest ich wystarczająco dużo. Wznowienie czyta źródła WYŁĄCZNIE z bazy i nigdy nie woła wyszukiwarki ponownie.
- **Dlaczego ważny:** zamyka lukę, którą sam podział na dwa kroki (ADR-016) jeszcze zostawiał otwartą — awarię procesu DOKŁADNIE między krokiem 1 a 2 (ADR-019).
```python
# repositories.py — jeden commit: źródła + status, żadnego stanu pośredniego
def mark_research_stage_a_success(self, research_run_id, sources):
    inserted = [self._insert_research_source(research_run_id, s) for s in sources]
    self._conn.execute(
        "UPDATE research_runs SET status=?, stage_a_completed_at=datetime('now') WHERE id=?",
        (ResearchRunStatus.SOURCE_COLLECTED.value, research_run_id),
    )
    self._conn.commit()          # źródła i status stają się trwałe razem, albo wcale
    return inserted

# pipeline.py — wznowienie: źródła z bazy, gather_sources NIGDY nie jest wołane
def resume_research_stage_b(research_run_id, account, *, storage, research_client, ...):
    research_run = storage.get_research_run(research_run_id)
    if research_run is None or research_run.status not in (
        ResearchRunStatus.SOURCE_COLLECTED, ResearchRunStatus.PARTIAL,
    ):
        raise ValueError(f"Run {research_run_id} nie jest wznawialny.")

    source_records = storage.list_research_sources(research_run_id)   # z bazy, nie z pamięci
    if len(source_records) < settings.research_min_sources:
        storage.mark_research_run_partial(research_run_id, error="still too few sources")
        return ResearchRunSummary(status="REJECT", reason="TOO_FEW_SOURCES", cost_usd=0.0)

    gathered = SourceGatheringResult(sources=[...], usage=Usage(), model="")
    card_draft, usage, model = research_client.synthesize_card(plan, gathered)  # zero web search
```
- **Uwaga:** test `test_resume_stage_b_never_calls_gather_sources_and_survives_restart` dowodzi tego dwoma sposobami naraz: klient zastępczy rzuca `AssertionError`, jeśli `gather_sources` w ogóle zostanie wywołane, a cały test buduje NOWE instancje `PolicyEngine`/`UsageTracker`/notifiera zamiast reużywać obiekty ze świeżego runu — symulując prawdziwy restart procesu. Pełny opis: `docs/CODE_EXAMPLES.md`, `docs/DECISIONS.md` ADR-019.

### Etapowa ekstrakcja per źródło — awaria jednego nie kasuje pozostałych
- **Plik źródłowy:** `app/workflows/research/pipeline.py` (`run_source_extraction`) + `app/storage/repositories.py`
- **Co pokazuje:** zamiast jednego wywołania zbierającego WSZYSTKIE źródła naraz (gdzie ucięcie odpowiedzi kasuje wszystko), każde źródło to OSOBNE wywołanie API, zapisywane do bazy natychmiast po przetworzeniu — błąd źródła numer 4 nie ma żadnego wpływu na źródła 1, 2 i 3.
- **Dlaczego ważny:** to bezpośrednia naprawa strukturalnej wady, która ujawniła się w drugim realnym teście (12.07) — nawet lekki schemat wciąż tracił WSZYSTKIE źródła przy jednym ucięciu.
```python
for candidate in kandydaci_do_ekstrakcji:
    if not budzet_pozwala():
        break   # pozostali kandydaci zostają "do zrobienia", można wznowić później

    try:
        wynik = klient.extract_source(plan, candidate)
    except BladParsowania as e:
        zapisz_realny_koszt_mimo_bledu(e)      # ten sam mechanizm co po incydencie 11.07
        oznacz_kandydata_jako_nieudanego(candidate.id, blad=str(e))
        continue   # <- pętla leci dalej, kolejne źródło nie wie i nie dba o los tego

    zapisz_zrodlo_natychmiast(candidate.id, wynik)   # commit TERAZ, nie na końcu pętli
```
- **Uwaga:** dwa testy dowodzą, że kolejność awarii nie ma znaczenia — jeden sprawdza awarię PIERWSZEGO źródła (pozostałe trzy przeżywają), drugi awarię CZWARTEGO (pierwsze trzy przeżywają). `tests/test_staged_research_extraction.py`.

### Diagnostyka — surowa odpowiedź modelu zapisywana prywatnie przy każdym błędzie
- **Plik źródłowy:** `app/research/diagnostics.py`
- **Co pokazuje:** oba dotychczasowe incydenty ucięcia odpowiedzi dawały tylko PRZYPUSZCZENIE przyczyny — teraz każda prawdziwa odpowiedź (udana i nieudana) trafia do prywatnego pliku razem z dokładnym powodem zatrzymania generacji, wprost z API.
- **Dlaczego ważny:** następnym razem będziemy WIEDZIEĆ, nie zgadywać.
```python
def zapisz_diagnostyke(folder_danych, run_id, etap, usage, surowa_odpowiedz, powod_zatrzymania):
    if tryb_probny or not surowa_odpowiedz:
        return   # tylko dla realnych wywołań — nic do zapisania dla danych zastępczych
    sciezka = folder_danych / "debug" / "research" / run_id / f"{etap}_raw_response.txt"
    # treść: run_id, etap, powod_zatrzymania, tokeny, surowa odpowiedź -- NIGDY klucz dostępu
    zapisz_plik(sciezka, ...)
```
- **Uwaga:** cały folder z danymi jest ignorowany przez git (nigdy nie trafia do repo). Testy potwierdzają: plik faktycznie powstaje przy błędzie, zawiera powód zatrzymania, i NIE zawiera żadnego sekretu.

## Do dodania (gdy mechanizmy powstaną lub zostaną skrócone)
- **Deduplikacja tematów** (`app/workflows/topics/dedup.py`) — Jaccard + SequenceMatcher, próg 0.72.
- **Scoring tematów** (`app/workflows/topics/discover.py`) — wagi 25/20/15/15/10/10/5, progi 75/65.
- **Pętla agenta / Run** (`app/orchestrator/runner.py`).
- **Approval gate**, **obsługa wielu kont** (scoping po `account_id`), **Playwright** (`BrowserPort`), **analiza wyników**.

## Powiązania
- `docs/CODE_EXAMPLES.md` (źródło), `docs/code-snippets/` (dłuższe wycinki), `code-snippets/` (kopie redakcyjne)

## E2-C — host binding zamiast drugiego DNS

Reprezentatywny kontrakt jest frozen i oddziela adres połączenia od tożsamości HTTP/TLS:

```python
@dataclass(frozen=True)
class BoundHttpTarget:
    url: str
    selected_address: str
    approved_addresses: tuple[str, ...]
    request_target: str
    host_header: str
    tls_server_name: str | None
```

Resolver tworzy ten obiekt raz dla initial URL. Transport łączy się z `selected_address`; `host_header` i `tls_server_name` zachowują nazwę. Przed konstrukcją realnego transportu root wymaga `ControlledFetchTransportAuthorization` wydanej przez storage po zużyciu L1. Pełny kod: `app/ports/controlled_fetch.py` i `app/storage/repositories.py`.

### 2026-07-19 — Ostatni gate przed writable open

```python
pre_open = _revalidate_source(
    source,
    initial=initial,
    canonical=canonical,
    quiescence_probe=effective_quiescence_probe,
    phase="immediate_pre_writable_open",
)
connection = _open_verified_writable(source, expected=pre_open)
```

Pierwszy wynik preflightu nie jest „przepustką na zawsze". Po snapshotcie źródło jest czytane ponownie, a po dwóch kontrolowanych oknach interposition jeszcze raz bezpośrednio przed `mode=rw`. Writable handle ponownie porównuje ledger i file identity przed migracją. Pełny kod: `app/operations/production_schema_migration.py`.

## 2026-07-23 — C3: wynik callera jako trwały, typowany fakt

```python
result = writer.write(request)
storage.record_content_writer_result(execution, intent, result)
storage.record_content_writer_usage(execution, intent, result.usage)
```

Sama kolejność jest tu ważniejsza niż liczba linii. Intent i canonical attempt istnieją przed callerem. Po powrocie najpierw utrwala się typowany result z fingerprintem. Dopiero potem settlement może bezpiecznie zostać wznowiony po restarcie. Jeśli proces zginie przed pierwszą z tych dwóch operacji, pipeline nie wykonuje drugiego calla automatycznie — kieruje stan do reconciliation.

Pełna implementacja znajduje się w `app/content/pipeline.py`, a walidacja zamkniętego result schema w `app/content/writer.py`.
