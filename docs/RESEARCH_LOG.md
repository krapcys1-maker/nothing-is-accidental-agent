# RESEARCH_LOG

## 2026-07-15 — WAVE 1A offline evidence: reconciliation is not research

- **Zakres:** bez nowych źródeł, kart, calli modeli, sieci lub kosztu. To dowód operacyjny przed przyszłym durable-real wykonaniem, nie wynik researchu.
- **Ustalenie:** koszt znanej próby żyje wyłącznie w `model_usage`; rezultat pipeline'u musi istnieć niezależnie, zanim operator potwierdzi `DONE`. Nieznana opłata pozostaje blokadą, a nie zaproszeniem do retry.
- **Dowód techniczny:** 0014 fresh/upgrade/rollback + `integrity_check`/`foreign_key_check`, atomic `BEGIN IMMEDIATE`, reopen/failpointy, append-only `reconciliation_events`, wyłączna własność karty, pełna walidacja lineage, centralna granica Worker failure→reconciliation (`W1A-R4-01`) i dwa połączenia SQLite; po czterech niezależnych falach weryfikacji **1036 testów offline**, `data/agent.db` bez zmiany. (Historyczne wyniki iteracji: 1007/980/955/948/919/894.)
- **Poprawka `W1A-VERIFY-01` (ADR-064):** resolver `EXECUTION_FAILED` rozstrzyga osierocony run zreapowany do `STOPPED` (`STOPPED → FAILED` atomowo, bez wskrzeszenia/`DONE`/attemptu #2); dowód niezmienności ledger↔cache i wyłącznej karty utrzymany. Licznik 948 → **955** (+7 deterministycznych testów), flaky node 30/30, plik 10/10.
- **Poprawka `W1A-VERIFY-02` (ADR-065):** przed rozliczeniem operator musi mieć spójny cały lineage `attempt→job→run→research_run→account→workflow→topic→intent`.  Wcześniej foreign `runs.account_id`/`workflow=ANALYTICS` był fail-open (nieobjęty 955/955); teraz aplikacja + version token v2 + trigger SQLite wymuszają zgodność, a każda niespójność jest fail-closed bez mutacji.  Licznik 955 → **980** (+25 testów lineage; `scripts/qa/reconciliation_lineage_disproof.py` 10/10).
- **Status:** WAVE 1A candidate only; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## Cel

Dziennik każdego researchu prowadzonego przez agenta. Dla każdego tematu zapisujemy pytanie badawcze, źródła, najważniejsze fakty, elementy niepewne, sprzeczności między źródłami, wniosek oraz wpływ researchu na artykuł/Note/komentarz/decyzję strategiczną. To zabezpieczenie przed halucynacjami (ryzyko R6) i pamięć źródeł. Powiązanie z bazą: `research_cards` + `sources` (źródło prawdy). Materiał najwyższej wartości trafia dodatkowo do `ARTICLE_EVIDENCE.md`.

## Zasady

- Jeden wpis = jeden research (jeden temat / jedno pytanie badawcze).
- Źródła pierwotne przed wtórnymi; zawsze sprawdzona data publikacji **i** data opisywanych danych.
- Odróżniaj fakt od interpretacji; oznaczaj niepewność jawnie.
- Żadnych wymyślonych źródeł, cytatów ani liczb. Luka jest lepsza niż zmyślony szczegół.
- Minimum 3 sensowne źródła, zanim research zasili artykuł.

## Szablon wpisu

```markdown
### [YYYY-MM-DD] Temat
- **Konto:** account_id (MVP: nothing_is_accidental)
- **Powiązanie:** research_card #.. / topic #.. / content_item #.. (jeśli są)
- **Pytanie badawcze:** jedno zdanie
- **Źródła:**
  1. [Tytuł](URL) — typ (PRIMARY/SECONDARY/DATA), data publikacji / data danych — co wnosi
  2. ...
  3. ...
- **Najważniejsze fakty (potwierdzone):** lista
- **Elementy niepewne:** lista (co źródła NIE rozstrzygają)
- **Sprzeczności między źródłami:** opis + możliwa przyczyna (metodologia/okres/populacja)
- **Wniosek (teza robocza):** jedno–dwa zdania
- **Confidence:** 0.0–1.0
- **Wpływ:** na co to poszło (artykuł / Note / komentarz / decyzja strategiczna) i jak zmieniło treść
```

---

## Wpisy

> Wpisy poniżej są dopisywane automatycznie po każdym researchu (dry_run oznaczony w treści).

### [2026-07-11] Why airline ticket prices change every few hours
- **Konto:** nothing_is_accidental
- **Powiązanie:** research_card #1 / topic #1
- **Pytanie badawcze:** What pricing system makes fares move so often?
- **Źródła:**
  1. [How airline revenue management works](https://example.org/dynamic-pricing-primer) — PRIMARY, 2023-05-10 — wspiera: Airlines use dynamic pricing engines
  2. [Observed fare update frequency dataset](https://data.example.gov/fare-updates) — DATA, 2022-11-01 — wspiera: Fares update as demand and inventory signals change
  3. [Why ticket prices move so often](https://example.com/airline-pricing-explainer) — SECONDARY, 2024-02-20 — wspiera: Airlines use dynamic pricing engines
- **Najważniejsze fakty (potwierdzone):** Airlines use dynamic pricing engines, Fares update as demand and inventory signals change
- **Elementy niepewne:** Exact repricing cadence varies by carrier and route.
- **Sprzeczności między źródłami:** —
- **Wniosek (teza robocza):** Ticket prices change because revenue-management systems continuously re-price seats against forecast demand and remaining inventory.
- **Confidence:** 0.78  |  **Source quality:** 0.8
- **Rekomendacja:** PROCEED
- **Wpływ:** dry-run/demonstracja pipeline researchu.

### [2026-07-11] What really happens to your suitcase after check-in — PIERWSZA REALNA PRÓBA (nieudana, ręczny wpis)
- **Konto:** nothing_is_accidental
- **Powiązanie:** topic #2 (SELECTED, score 85.25) / run `1b649314-27cf-4b29-857e-287175664a3f`
- **Pytanie badawcze:** What is the hidden logistics chain behind checked luggage?
- **Źródła:** brak — model zwrócił odpowiedź (>8100 znaków, realnie użył web search), ale JSON został ucięty w połowie stringa przed pełnym wypisaniem listy źródeł; parsowanie nie powiodło się, więc żadne źródło nie zostało wyodrębnione ani zapisane.
- **Najważniejsze fakty (potwierdzone):** nieznane — niedostępne z powodu nieudanego parsowania.
- **Elementy niepewne:** cała treść odpowiedzi poza tym, że dotarła i była długa; surowy tekst nie został nigdzie zalogowany, więc nie da się go odtworzyć retrospektywnie (zidentyfikowana luka: warto logować surową odpowiedź modelu również przy błędzie parsowania — rekomendacja na przyszłość, niewdrożona teraz).
- **Sprzeczności między źródłami:** nie dotyczy (brak źródeł do porównania).
- **Wniosek (teza robocza):** nie dotyczy — research nie dostarczył użytecznego draftu.
- **Confidence:** nie dotyczy (walidacja nigdy nie doszła do etapu oceny — pipeline zatrzymał się na etapie parsowania).
- **Rekomendacja:** REJECT (brak poprawnego draftu; bramka jakości nie została nawet uruchomiona, bo nie było czego walidować).
- **Rzeczywisty koszt (potwierdzony w konsoli Anthropic, 2026-07-11, później tego samego dnia):** **0.25 USD** = 0.21 USD tokeny + 0.04 USD web search (4 wyszukiwania). Pierwotny pre-flight szacunek: 0.095 USD — realny koszt był **2,63× wyższy** (błąd ~+163%). Zmieściło się w zatwierdzonym limicie 0.30 USD, z zapasem 0.05 USD.
- **Wpływ:** REALNE (płatne) wywołanie Anthropic — nie dry-run. Zero artykułu/Note/komentarza z tego wyszło. Ujawniło i doprowadziło do naprawy dwóch realnych problemów: (1) bug księgowania kosztu przy błędzie parsowania (patrz `ERRORS_AND_FAILURES.md`, wpis 2026-07-11 19:09 UTC „Realny koszt zgubiony..."), (2) błędny (zaniżony) estymator kosztu PRZED wywołaniem (patrz `ERRORS_AND_FAILURES.md`, wpis „Pre-flight cost estimator underestimated the real cost"). Doprowadziło też do przebudowy pipeline'u na wersję dwuetapową (`gather_sources` + `synthesize_card`, ADR-016) z kalibrowanym estymatorem. Temat #2 pozostaje SELECTED — może zostać ponownie podjęty w osobno zatwierdzonej kolejnej próbie (tryb `two-stage`, projekcja kosztu ~0.38 USD w capie 0.45 USD).

### [2026-07-13] What really happens to your suitcase after check-in — TASK 9, STAGED A1/A2 SUKCES, B NIEUDANE
- **Konto:** nothing_is_accidental
- **Powązanie:** topic #2 / run i research_run `c01171bc-7ff5-4b83-bbfa-c0b164137793` / brak research_card
- **Pytanie badawcze:** What is the hidden logistics chain behind checked luggage?
- **Dokładna komenda:** `python scripts/run_capped_research.py --topic-id 2 --mode three-stage --discovery-max-searches 1 --max-sources 4 --max-web-searches-per-source 1 --extraction-max-tokens 1500 --max-retries 0 --max-cost-usd 0.55`
- **Pre-flight:** expected 0,201280 USD; conservative 0,510375 USD; cap 0,550000 USD; dziennie przed runem 0,000000/2,00 USD; miesięcznie 0,500616/40,00 USD; kill switch wyłączony; konto aktywne; temat SELECTED; zero retry.
- **Źródła A2 (wszystkie EXTRACTED/VERIFIED, attempts=1):**
  1. [Checked Baggage: Where Does It Go In The Airport & How Does The System Work?](https://simpleflying.com/checked-baggage-journey-analysis/) — SECONDARY, Simple Flying, 2024-03-12; candidate #5; jakość 0,62; koszt calla 0,049405 USD.
  2. [The journey of a suitcase - More than meets the eye](https://www.easa.europa.eu/en/light/topics/journey-suitcase) — PRIMARY, EASA; data nieustalona; candidate #6; jakość 0,80; koszt calla 0,028891 USD.
  3. [The hidden complexity behind your luggage](https://www.airport-suppliers.com/supplier-press-release/the-hidden-complexity-behind-your-luggage-the-engineering-and-systems-behind-modern-airport-baggage-handling/) — OTHER, Airport Suppliers, 2024-08-01; candidate #7; jakość 0,45; koszt calla 0,028620 USD.
  4. [The hidden highway beneath your suitcase](https://www.fly2houston.com/airport-business/newsroom/articles/item/the-hidden-highway-beneath-your-suitcase/) — PRIMARY, Houston Airports, 2025-12-17; candidate #8; jakość 0,80; koszt calla 0,020987 USD.
- **Wyniki etapów:** A1 SUCCESS (`end_turn`, 1 search, 0,029243 USD); A2 4/4 SUCCESS (`end_turn`, 4 searches, 0,127903 USD); B FAILED (`max_tokens`, 2200 output tokens, zero search, 0,012904 USD).
- **Błąd:** `ResearchParseError` — `Unterminated string starting at line 29 column 18 (char 4224)`. Surowa odpowiedź i metadane są prywatnie w `data/debug/research/<run_id>/`; nie trafiają do repo.
- **Stan trwały:** `research_runs=SOURCES_COMPLETE`, `runs=RUNNING` bez `finished_at`, topic SELECTED, 4 VERIFIED, brak karty. Run jest technicznie wznawialny wyłącznie od B, ale nie wykonano resume ani drugiego calla.
- **Rzeczywisty koszt:** **0,170050 USD**, zgodny z sumą 6 wpisów `model_usage` i `runs.cost_usd`; 30,92% capu 0,55 USD.
- **Najważniejsze fakty / teza / sprzeczności / confidence:** niezatwierdzone do użycia — synteza nie utworzyła Research Card. Cztery karty źródłowe pozostają trwałym materiałem wejściowym, nie finalnym wnioskiem.
- **Rekomendacja:** REJECT dla wyniku Task 9; Etap 0 pozostaje aktywny. Każdy kolejny płatny krok wymaga osobnej zgody.
- **Wpływ:** zero artykułu, publikacji i działań zewnętrznych poza sześcioma zatwierdzonymi requestami researchu w ramach jednego runu.

#### Korekta techniczna po analizie offline (bez nowego researchu)

Nie wykonano nowego calla ani resume. Przyczyną B był wyczerpany limit 2200, nie losowy parse error. Przyszłe B użyje jawnego defaultu 3000, typowanego truncation bez retry i pełnego pre-flightu (B conservative 0,026250 USD; projected z dotychczasowym usage 0,196300 USD). Historyczny wynik, cztery VERIFIED, koszt 0,170050 USD i brak Research Card pozostają bez zmian. Repair auditu i resume wymagają osobnych zgód.

#### Kontrolowany repair auditu (2026-07-13, bez researchu/API)

Za osobną zgodą właściciela wykonano lokalną operację maintenance dla tego samego runu. Po backupie i ponownym sprawdzeniu relacji run–research–topic–account, 4×EXTRACTED/VERIFIED `attempts=1`, sześciu wpisów usage, sumy 0,170050 USD, FAILED Stage B oraz prywatnej diagnostyki `stop_reason=max_tokens`, warunkowy UPDATE zmienił wyłącznie `runs.status RUNNING→FAILED`, `finished_at=2026-07-13 05:39:30 UTC` i `runs.error`. `rowcount=1`, `total_changes=1`. Research pozostał `SOURCES_COMPLETE`, topic `SELECTED`, brak karty; koszt i usage bez zmian. Nie wykonano resume ani A1/A2/B. Techniczna gotowość do resume wyłącznie B nie jest zgodą na płatny call.

### [2026-07-13] What really happens to your suitcase after check-in
- **Konto:** nothing_is_accidental
- **Powiązanie:** research_card #2 / topic #2
- **Pytanie badawcze:** What is the hidden logistics chain behind checked luggage?
- **Źródła:**
  1. [Checked Baggage: Where Does It Go In The Airport & How Does The System Work?](https://simpleflying.com/checked-baggage-journey-analysis/) — SECONDARY, 2024-03-12 — wspiera: Automated sensor-based routing and scale of Denver's BHS infrastructure (DCVs, track, conveyors).
  2. [The journey of a suitcase - More than meets the eye](https://www.easa.europa.eu/en/light/topics/journey-suitcase) — PRIMARY, unknown — wspiera: Regulatory weight-and-balance logic, ULD building, dangerous goods separation, and transfer bag re-screening/re-sorting.
  3. [The hidden complexity behind your luggage ~ The engineering and systems behind modern airport baggage handling](https://www.airport-suppliers.com/supplier-press-release/the-hidden-complexity-behind-your-luggage-the-engineering-and-systems-behind-modern-airport-baggage-handling/) — OTHER, 2024-08-01 — wspiera: Engineering design details of conveyor geometry, diverters, and automated bag-centring before security scanning.
  4. [The hidden highway beneath your suitcase](https://www.fly2houston.com/airport-business/newsroom/articles/item/the-hidden-highway-beneath-your-suitcase/) — PRIMARY, 2025-12-17 — wspiera: Physical scale and infrastructure investment of a new BHS (steel bridge, conveyor network length, processing capacity) at IAH.
- **Najważniejsze fakty (potwierdzone):** Baggage handling systems use automated tag-scanning at check-in to determine routing (SimpleFlying, Airport Suppliers, Fly2Houston)., Bags move through networks of conveyors, diverters, and sensors rather than a single simple belt (all four sources)., Bags are consolidated into pallets, carts, or Unit Load Devices (ULDs) before being transported to aircraft (SimpleFlying, EASA)., Arriving bags are automatically re-sorted to separate connecting-flight bags from baggage-claim bags (SimpleFlying, EASA)., Large-scale BHS infrastructure (tracks, conveyors, steel structures) represents major engineering investment (Denver: 19mi track, 5mi conveyors, 4000+ DCVs; IAH: 1.5-mile conveyor network, 157-ft steel bridge).
- **Elementy niepewne:** Specific engineering design choices, like avoidance of 90-degree diverters and use of optimized angles, are asserted by only one lower-quality source (Airport Suppliers, quality=0.45)., Claims about EASA-regulated weight-and-balance manuals dictating bag placement are plausible but only sourced from a single site without independent verification., The degree to which automated guided vehicles (AGVs) are 'increasingly' used industry-wide is asserted without supporting data.
- **Sprzeczności między źródłami:** —
- **Wniosek (teza robocza):** Behind the simple counter drop-off, checked luggage travels through a highly automated, engineered logistics network of scanners, conveyors, diverters, and vehicles that route, screen, and consolidate bags into loadable units before they ever reach the aircraft — a system whose scale and precision most passengers never see.
- **Confidence:** 0.72  |  **Source quality:** 0.67
- **Rekomendacja:** REJECT (powód: THESIS_UNSUPPORTED; CLAIMS_WITHOUT_SOURCES)
- **Wpływ:** REALNE wywołanie Anthropic (płatne) — łączny koszt runu 0.183964 USD.

#### Kontrolowany resume wyłącznie B — audit wykonania

- **Jawna zgoda i komenda:** właściciel zatwierdził dokładnie jeden call B: `python scripts/run_capped_research.py --resume c01171bc-7ff5-4b83-bbfa-c0b164137793 --account nothing_is_accidental --synthesize-max-tokens 3000 --forwarded-context-tokens 2500 --max-retries 0 --max-cost-usd 0.20`.
- **Preflight:** branch/HEAD/upstream/working tree i 351 testów zgodne; staged/SOURCES_COMPLETE, topic #2 SELECTED, 4×EXTRACTED/VERIFIED/attempts=1, brak karty, 6 usage = 0,170050 USD. PolicyEngine dopuścił conservative B 0,026250 i projected total 0,196300 ≤ 0,20 USD; kill switch false, konto aktywne, budżety D/M pozwalały.
- **Jedyny nowy call:** `stop_reason=end_turn`, input/output 1904/2402, zero web search, koszt B 0,013914 USD; bez retry i bez A1/A2. Siedem wpisów usage sumuje się do 0,183964 USD i dokładnie odpowiada `runs.cost_usd` oraz `research_runs.total_cost_usd`.
- **Stan po reopen:** `runs=SUCCESS`, `research_runs=COMPLETE`, `stage_b_completed_at=2026-07-13 05:57:57 UTC`, topic `USED`, research_card #2, 4 źródła VERIFIED. Karta jest kompletna, ale bramka jakości zwróciła `REJECT` (`THESIS_UNSUPPORTED`, `CLAIMS_WITHOUT_SOURCES`), więc nie wolno użyć jej do treści.
- **Zamknięcie:** techniczne kryterium Etapu 0 zostało spełnione. Etap 1 nie został rozpoczęty. `research_runs.error` zachował historyczny parse-error pierwszego B — jawny P2-20 do review, bez mutacji w tej pracy.

## 2026-07-14 — WAVE 0B.2 offline verification

- **Zakres:** wyłącznie syntetyczne SQLite i injected callery; brak researchu, API, sieci oraz kosztu.
- **Dowód:** durable parse-error zachowuje usage i rozlicza jeden attempt; worker po zmianie ENV korzysta z persisted intentu; migracja 0012 wycofuje sprzeczną historię.
- **Stan historyczny:** wynik WAVE 0B.2 został zastąpiony przez WAVE 0B.3; żadnego wpisu researchu ani kosztu nie dopisano.

## 2026-07-14 — WAVE 0B.3 offline verification

- **Zakres:** syntetyczne SQLite, injected callery i fake SDK; bez researchu, API, sieci oraz kosztu.
- **Dowód:** derived `request_id` blokuje arbitralne identity przed callerem, a storage używa świeżego execution clock dla expiry/renewal/takeover/fence/reconciliation.
- **Stan:** `WAVE 0B.3 CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`; 770 testów offline, żadnego wpisu researchu ani kosztu nie dopisano.

## 2026-07-15 — Formalny checkpoint WAVE 0B

- **Zakres:** wyłącznie kontrola repozytorium i staging zatwierdzonego zakresu; brak researchu, API, sieci, browsera i kosztu.
- **Podstawa:** niezależny końcowy review potwierdził 894/894 testów i partycje 213/224/231/226; chroniona baza pozostała identyczna.
- **Stan:** `WAVE 0B APPROVED WITH P2 — READY FOR CHECKPOINT`; Etap 1 `BLOCKED`, live API `ZABRONIONE`. Formalne zamknięcie wymaga przyszłego, osobno autoryzowanego commita.

## 2026-07-17 — LA-01-R1 offline verification

- **Zakres:** wyłącznie testy kontraktu wykonania na fake workerach/callerach i tymczasowych SQLite; nie prowadzono researchu treściowego ani wyszukiwania.
- **Dowód:** 1151/1151 oraz exact-once 275+282+291+303; pełny frozen pricing, ownership/fencing, durable report, recovery bez retry i prawdziwy reopen.
- **Koszt i stan:** 0 USD; bez API/SDK/sieci. Nie powstał Research Card z realnego providera i nie wykonano controlled live acceptance.

## 2026-07-17 — Checkpoint LA-01-R1 po niezależnym review

- **Zakres:** formalna materializacja werdyktu, selektywny staging, testy i Git; bez researchu treściowego, providera, browsera i publikacji.
- **Wynik review:** `APPROVE WITH MINOR/P2`; open P2 sanitizera jest nieblokującą rekomendacją.
- **Koszt:** 0 USD; żadnego wpisu model usage ani Research Card.
