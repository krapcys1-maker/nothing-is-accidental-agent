# RESEARCH_LOG

## 2026-08-11 — P2-1 provider contract alignment (offline code tracing)

- Prześledzono lokalnie production composition roots TOPIC_GENERATION i ARTICLE_RESEARCH od CLI/Worker/Dispatcher do finalnego callera. Finding potwierdzony: oba omijały canonical adapter/binding authority.
- Nie wykonano researchu internetowego ani providerowego. Jedyny research smoke był deterministycznym E3 na temp SQLite z fake SDK i syntetycznym evidence corpusem; koszt `0.000000 USD`.

## 2026-08-11 — offline analiza blockerów PRE-LIVE CONTENT FLOW

- **Zakres:** wyłącznie aktualny kod, testy i immutable odczyt stanu produkcyjnego; bez internetu, nowych źródeł, model calla i web search.
- **Ustalenie o reviewerze:** `ClaimAccountingReviewPort` wymaga semantycznego independent reviewera. Deterministic layer potrafi sprawdzić completeness, identity, evidence IDs i sprzeczności klas, ale lexical overlap nie dowodzi, że zdanie nie dodało faktu. ADR-122/123 jest nadrzędny.
- **Ustalenie o novelty:** istniejące `topics`, `question`, `research_cards.working_thesis/thesis`, `content_items` i `content_drafts` wystarczają do trwałej pamięci bez migracji i zewnętrznej infrastruktury. Pusty content item nie jest wcześniejszym artykułem.
- **Ustalenie o ordering:** wspólna granica przed paid research istnieje w dispatcherze, a przed provider writerem w content pipeline. Controlled fetch musi pozostać poza tą płatną bramką.
- **Wpływ:** ADR-134, implementacja kandydacka B1/B2/B4/B5 i jawny blocker B3. To analiza techniczna, nie research do publikacji i nie authority do realnego uruchomienia.

## 2026-08-10 — offline authority check dla Opus ARTICLE_WRITER

- **Zakres:** wyłącznie current repo i produkcyjna DB otwarta immutable/read-only; bez internetu i bez nowego researchu źródłowego.
- **Ustalenie:** repo zawiera wystarczający owner-verified frozen catalogue contract dla `OPUS/5/claude-opus-5`, pricing ref `anthropic-opus-5-standard-2026-08`, pełne ceny i runtime provenance `global/standard_only→global/standard`.
- **Wniosek:** routing core już obsługuje rodzinę Opus; wymagane były tylko policy switch, minimalna generalizacja Fable-specific qualification caller oraz nowy forward-only SQL floor. Dokumentacja nie jest qualification authority, dlatego Opus pozostaje fail-closed.

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

## 2026-07-17 — Real pricing profile i live acceptance preflight

- **Zakres:** wyłącznie lokalna walidacja cennika, odczyt topicu `3` i stanu operacyjnego bazy w trybie read-only; bez researchu treściowego i bez web search.
- **Wynik:** topic `Why supermarkets put essentials at the back` pozostaje `SELECTED`, bez Research Card. Nie utworzono joba ani attemptu.
- **Koszt:** `0.000000 USD`; provider, SDK i sieć nie zostały użyte. Projected `0.070000` i pessimistic `0.105000 USD` są planem przyszłej operacji, nie poniesionym kosztem.

## 2026-07-17 — Jedyna autoryzowana komenda live zatrzymana przed providerem

- **Zakres:** wrapper uruchomiono dokładnie raz dla topicu `3`; wewnętrzny preflight zwrócił `PREFLIGHT_FAILED` przed requestem.
- **Wynik researchu:** brak run/research_run, brak źródeł i Research Card; topic pozostaje `SELECTED`.
- **Koszt:** `0.000000 USD`; provider attempts i usage równe zero, miesięczny koszt nadal `0.684580 USD`.

## 2026-07-17 — LA-02 offline, bez researchu treściowego

- **Zakres:** lokalna analiza kodu i procesów, fake callery oraz tymczasowe bazy; nie wykonywano web search ani researchu treściowego.
- **Wynik:** przyczyna `PROCESSES_PRESENT` zamknięta kandydacko przez ancestry contract; żadnego źródła, runu, Research Card ani provider requestu.
- **Koszt:** `0.000000 USD`; job produkcyjny pozostaje `QUEUED/attempts=0`, provider attempts/usage=0.

## 2026-07-17 — Checkpoint LA-02 po niezależnym review

- **Zakres:** formalna materializacja `APPROVE WITH MINOR/P2`, P2 cleanup, pełne testy offline i selektywny Git; bez researchu treściowego, web search, providera, browsera i publikacji.
- **Wynik:** nie powstał run, research_run, źródło ani Research Card. Produkcyjny job pozostaje `QUEUED/attempts=0`; provider request, attempts i usage są zerowe.
- **Koszt:** `0.000000 USD`; Etap 1 pozostaje otwarty do nowej decyzji właściciela po standalone quiescence check.

## 2026-07-17 — LA-03: pierwszy durable provider request

- **Zakres:** topic `3`, provider Anthropic, model `claude-sonnet-5`, maks. 1500 tokenów, jeden web search, cap `0.12 USD`, attempt #1, zero retry.
- **Preflight:** canonical standalone i real pre-storage check PASS; DB SHA wejściowe `5FF5DB…97B78`, dokładnie jeden claimable job, approved pricing fingerprint `1b98c7…4062`, flags fail-closed, brak attemptów/usage/lease/rezerwacji/markera.
- **Request:** dokładnie jeden HTTP 200; usage 13306 input, 1657 output, jeden web search, koszt `0.053182 USD`.
- **Wynik researchu:** odpowiedź nie była poprawnym JSON-em; `ResearchParseError` zakończył run i research_run jako `FAILED`, bez źródeł/karty wynikowej i bez retry.
- **Trwały ledger:** attempt #1 `SETTLED`, `request_started_at` obecny, jedno usage, brak attemptu #2/reconciliation, spójny koszt run/research_run `0.053182 USD`.
- **Stan końcowy:** job `FAILED/attempts=1`; marker absent; flags/gate fail-closed; post-live DB SHA `5BEA9E…C6D10`; kolejny request nieautoryzowany.

## 2026-07-17 — Forensics odpowiedzi LA-03 i offline parser matrix

- **Zakres:** wyłącznie immutable query produkcyjnego ledgeru, odczyt sanitizowanego raportu i analiza kodu parsera/diagnostyki; zero web search, providera i nowego researchu.
- **Trwały dowód:** request `…:research:1`, run `f74165fb-9677-4e6d-abfd-09607bd4dd78`, attempt #1 `SETTLED`, usage 13306 input / 1657 output / 1 search / `0.053182 USD`, parse error `line 29 column 6 char 4376`.
- **Brak dowodu:** nie ma `data/debug/research/<run_id>/`; single caller odrzucił stop reason i nie zachował raw. Konkretna forma wadliwej odpowiedzi pozostaje niepoznawalna. Nie wykonano ponownego requestu.
- **Reprodukcja offline:** 14 klas fake response obejmuje good JSON, jeden pełny fence, prose before/after, dwa obiekty, truncated/unclosed, missing/bad fields/types/root/fence i `stop_reason=max_tokens`. Każdy przypadek ma caller count=1; failures mają zero retry/attemptu #2.
- **Ledger test:** parse/schema/truncation na temp durable flow mają dokładnie jedno usage, jeden `SETTLED` i terminalny `FAILED`, bez Research Card i reconciliation.
- **Koszt nowy:** `0.000000 USD`; suma historyczna pozostaje `0.737762 USD`.

## 2026-07-17 — Naprawa NIA-P2-RV-01…05 bez researchu treściowego

- **Zakres:** fake response, fake SDK/callery i tymczasowe SQLite; nie wykonano web search, providera ani nowego researchu.
- **Wynik:** parser, score validation, diagnostic sanitizer i jawny zegar zostały sprawdzone offline; nie powstał run, źródło ani Research Card w produkcji.
- **Koszt:** `0.000000 USD`; historyczne usage i suma miesiąca `0.737762 USD` nie zmieniły się.

## 2026-07-17 — Nowy controlled-live zatrzymany przed researchem

- **Zakres:** read-only preflight planowanego pojedynczego requestu `claude-sonnet-5`, bez web search i bez provider calla.
- **Wynik:** canonical quiescence `PASS`, pricing i budżet zgodne, ale real gate pozostał `False`, a właściciel zabronił zmiany kodu. Nie utworzono joba, runu, research_runu, źródła ani Research Card.
- **Koszt:** `0.000000 USD`; miesięczny realny koszt nadal `0.737762 USD`.
- **Status:** `BLOCKED — LIVE PREFLIGHT DRIFT`; zero retry i automatycznego resume.

## 2026-07-17 19:18 UTC — Jednorazowy controlled-live zakończony truncation

- **Tożsamość:** operation `positive-live-20260717-dc1c29aa0b3640c6`, job `real-research-9f244684711acf4f82a07da8d4a139ea`, run/research_run `8bcf15e4-c4e9-48ed-95f7-64f0b93fcee5`, request `…:research:1`.
- **Request:** Anthropic `claude-sonnet-5`, HTTP 200, `max_tokens=1500`, 1 web search, `stop_reason=max_tokens`; 16704 input i 1667 output tokens.
- **Wynik:** `ResearchTruncatedError`, brak Research Card; job/run/research_run `FAILED`; attempt `SETTLED`, koszt `0.060078 USD`, miesięcznie `0.797840 USD`.
- **Granice:** zero retry, repair/fallback/verification requestu i attemptu #2.

## 2026-07-17 19:44 UTC — Jednorazowy controlled-live 3000 zakończony schema failure

- **Tożsamość:** operation `positive-live-3000-20260717-9dcb59eef3674138`, job `real-research-e33abc717c655c7c7b6abeccd43554f3`, run/research_run `65841541-10c9-4aa6-aee8-8fe1161d8f85`, request `…:research:1`.
- **Request:** Anthropic `claude-sonnet-5`, HTTP 200, `max_tokens=3000`, 1 web search, `stop_reason=end_turn`; 19945 input i 2727 output tokens.
- **Wynik:** `ResearchSchemaError` dla `sources[0].supports_claim` (`expected=string_or_null`), brak Research Card; job/run/research_run `FAILED`; attempt `SETTLED`, koszt `0.077160 USD`, miesięcznie `0.875000 USD`.
- **Granice:** zero retry, repair/fallback/verification requestu, attemptu #2 i zmian parsera/schema/promptu.

## 2026-07-17 20:46 UTC — Live po naprawie kontraktu zakończony truncation

- **Tożsamość:** operation `positive-live-contract-20260717-ee093a1d54cd4111`, job `real-research-85151c312b180759cd2387c5458f1248`, run/research_run `08aa35eb-a87c-4ec0-bf3c-b2d608165e85`, request `…:research:1`.
- **Request:** Anthropic `claude-sonnet-5`, HTTP 200, `max_tokens=3000`, 1 web search, `stop_reason=max_tokens`; 16381 input i 3155 output tokens.
- **Wynik:** `ResearchTruncatedError` przed schema validation, brak Research Card; job/run/research_run `FAILED`; attempt `SETTLED`, koszt `0.074312 USD`, miesięcznie `0.949312 USD`.
- **Granice:** zero retry, repair/fallback/verification requestu i attemptu #2; poprawione kontrakty `supports_claim`/`citable_numbers` nie zostały ocenione live.

## 2026-07-18 04:48 UTC — Pierwszy kompletny Research Card z controlled-live

- **Tożsamość:** operation `positive-live-output-size-20260718-09fe2f3684f14919`, job `real-research-b153efbd48d44e0e6388ec98e5e7afb0`, run `bd0dd102-2526-4b2d-8c04-6b96ed9f8ef6`, request `…:research:1`, karta `id=3` dla topic `3`.
- **Request:** Anthropic `claude-sonnet-5`, prompt v3, HTTP 200, `max_tokens=6000`, 1 web search, `stop_reason=end_turn`; 16834 input, 1961 output, `thinking_tokens=51`, raw payload 4928 znaków.
- **Wynik techniczny:** raw-size, JSON, schema, limity pól i injection guard przeszły; pięć źródeł; job `DONE`, run `SUCCESS`, research_run `COMPLETE`, attempt `SETTLED`.
- **Ocena redakcyjna:** `REJECT/WEAK_SOURCES`; karta pozostaje dowodem poprawności pipeline'u, nie rekomendacją publikacji.
- **Koszt/granice:** `0.063278 USD`, miesiąc `1.012590 USD`; dokładnie jeden attempt/provider request, zero retry, repair, fallbacku i drugiego live.

## 2026-07-18 — Niezależne potwierdzenie positive-live bez nowego researchu

- **Zakres:** niezależny końcowy review trwałego wyniku i zaakceptowanego working tree; 223/223 własnych wąskich testów, exact-once, zero CRITICAL/MAJOR/nowych MINOR.
- **Rozróżnienie testów:** reviewer nie uruchamiał ponownie pełnego 1288; potwierdził bajtową identyczność kodu/testów z wcześniej zaakceptowanym wynikiem implementera 1288/1288 i partycjami `306+312+328+342`.
- **Decyzja:** reviewer wydał `APPROVE`, a właściciel formalnie przyjął positive-live gate w ADR-095. Karta `id=3` pozostaje redakcyjnie `REJECT/WEAK_SOURCES`.
- **Koszt i granice:** nowy research/provider call/usage/koszt = `0`; miesięczny ledger pozostaje `1.012590 USD`; kolejny live `NOT AUTHORIZED`, Etap 2 `NOT STARTED`.

## 2026-07-18 — Fala naprawcza PR #1 bez nowego researchu

- **Zakres:** deterministyczne testy odzyskiwania lifecycle po `SETTLED`, final-tree cleanup oraz dokumentacja; fake callery i tymczasowe bazy SQLite.
- **Research/provider:** zero zapytań, web search, SDK, requestów, usage i nowych kart. Nie użyto materiału zewnętrznego.
- **Koszt i stan:** `0.000000 USD`; miesięczny ledger pozostaje `1.012590 USD`; Etap 2 `NOT STARTED`, kolejny live `NOT AUTHORIZED`.

## 2026-07-18 — PR1-MAJ-005 bez nowego researchu

- **Zakres:** wyłącznie offline schema-gate, jawny migrator i kontrpróby na tymczasowych SQLite; żadnych danych internetowych ani materiału researchowego.
- **Research/provider:** zero API, SDK, providera, web search, requestów, usage i nowych kart.
- **Koszt i stan:** `0.000000 USD`; miesięczny ledger pozostaje `1.012590 USD`; produkcja nadal schema `0014`, Etap 2 `NOT STARTED`, kolejny live `NOT AUTHORIZED`.

## 2026-07-19 — E2-C bez nowego researchu

- **Zakres:** wyłącznie lokalna implementacja i deterministyczna walidacja runtime capability, aktywacji YAML i host bindingu controlled fetch.
- **Research/provider:** zero danych internetowych, web search, DNS, HTTP, API, SDK providera, usage i Research Card; test transportu użył wyłącznie in-memory fake socket/TLS/HTTP callerów.
- **Dowód:** pełna suita `1572/1572`, exact-once `378+389+394+411`, harness E2-C `13/13` i E2-B `13/13`; produkcja `0014` byte-identical.
- **Koszt i granica:** `0.000000 USD`; miesięczny ledger pozostaje `1.012590 USD`; controlled-live = `NOT READY`, pierwszy realny Fetch nadal nieautoryzowany.

## 2026-07-19 — Production Schema Migration Orchestrator bez nowego researchu

- **Zakres:** wyłącznie lokalna implementacja, syntetyczne failpointy i deterministyczne testy na nowych tymczasowych SQLite.
- **Research/provider:** zero danych internetowych, web search, DNS, socketów, HTTP, API, SDK providera, usage i Research Card. Nie wykonywano Fetch ani migracji produkcji.
- **Dowód:** orchestrator `58/58`, pełna suita/exact-once `1630/1630`, partycje `390+398+412+430`, runtime QA `30/30`, harnessy E2-B/E2-C `13/13+13/13`; produkcja `0014` byte-identical.
- **Koszt:** `0.000000 USD`; miesięczny ledger pozostaje `1.012590 USD`.

## 2026-07-22 — F1-BLOCK-01 bez nowego researchu

- **Zakres:** deterministyczne odtworzenie crash window i walidacja recovery na fake callerach oraz nowych temp SQLite.
- **Research/provider:** zero danych internetowych, web search, DNS/HTTP, API, realnego SDK, provider requestów i nowych topiców z modelu.
- **Dowód:** collect/full `1821/1821`, 0 skipped/xfail; produkcyjna DB tylko immutable read-only i niezmieniona.
- **Koszt:** `0.000000 USD`; historyczne rzeczywiste wpisy ledgeru pozostają bez zmian.

## 2026-07-22 — Publiczny entrypoint TOPIC_GENERATION bez nowego researchu

- **Zakres:** lokalna kompozycja istniejącego durable topic-generation, policy gates, recovery marker i testy targetowania dokładnego joba.
- **Research/provider:** zero web search, DNS/HTTP, API, realnego SDK, provider requestów i produkcyjnych tematów; wyłącznie fake callery oraz nowe temp SQLite.
- **Dowód:** 33 nowe przypadki, collect/full `1854/1854`, 0 skipped/xfail; istniejący research controlled-live i pozostałe composition roots pozostają zielone.
- **Koszt:** `0.000000 USD`; controlled-live nie wykonano, historyczny ledger bez zmian.

## 2026-07-23 — Pierwszy realny controlled-live TOPIC_GENERATION

- **Tożsamość:** job `topic-generation-037eb2d3db158a70791e30064ad95403`, request `…:topics:1`, run `4cf8c448-5358-43c6-9d47-e5daf6d0f040`, intent `019b1022…c1d`.
- **Request:** dokładnie jeden HTTP 200 do Anthropic, model `claude-sonnet-5`, 2 kandydatów, max 1500 tokenów, timeout 60 s, zero retry i zero web search.
- **Usage/koszt:** 219 input, 1269 output, cache read/write `0/0`, search `0`; `0.013128 USD` przy capie `0.024303 USD`.
- **Wynik:** job `DONE`, run `SUCCESS`, attempt #1 `SETTLED`, approval consumed, usage count 1, reconciliation false. Utworzono topics `20` i `21`; selected `21` — „Why Your Flight's Gate Number Isn't Random: The Hidden Logistics of Airport Gate Assignment”.
- **Granice:** nie wykonano Fetch, browsera, publikacji, maintenance, retry ani attemptu #2; flagi wróciły fail-closed.
## 2026-07-23 — Lokalna analiza prywatnego korpusu stylu dla C2

- **Zakres:** wyłącznie offline analiza strukturalna `data/style-references/articles/article_style_samples_v1.txt`; bez sieci, API, providera i bez ujawniania raw content.
- **Integralność PRE:** plik obecny; `57561 B`; SHA-256 `0b05cefa6701e6447c44810b686828a83c19ca7ffb29066778a13c24207acb1d`.
- **Metoda:** agregaty lokalne dotyczące linii, akapitów, zdań, długości zdań, pierwszej osoby, pytań, em dash, nagłówków/separatorów i sygnałów odrębnych Notes. Żadne pełne zdanie źródłowe nie zostało wpisane do logu.
- **Wynik:** 226 linii, 108 akapitów, 9418 słów, 392 zdania; mediana długości zdania 21 słów, p90 43; brak wiarygodnych separatorów wielu próbek i brak wystarczającego, odrębnego korpusu Notes. Konserwatywna liczba rozpoznanych próbek = 1.
- **Decyzja:** powstały wysokopoziomowe profile ARTICLE i negative; Notes = `PROVISIONAL`. Profile nie imitują konkretnego autora, nie zawierają długich cytatów i nie są wejściem do detektorów AI.
- **Koszt i skutki:** `0.000000 USD`; raw source pozostał gitignored i poza runtime/repo.

## 2026-07-24 — WAVE C4 bez researchu

- **Zakres:** wyłącznie implementacja offline decyzji na już utrwalonych artefaktach C3; nie wykonano researchu treściowego, web search, Fetch ani odczytu prywatnego korpusu.
- **Wynik:** brak nowych Research Cards, źródeł, retrievali, excerptów i kosztów. C4 nie zmienia research pipeline'u.
- **Koszt:** `0.000000 USD`; wpis służy jawnej ewidencji braku researchu, nie przedstawia wyniku badawczego.

## 2026-08-09 — Offline counterresearch question semantic boundary

- **Zakres:** bez web search, Fetch, API i zewnętrznego researchu. Badanie miało charakter wyłącznie lokalnej kontrpróby semantycznego kontraktu pytań na fake reviewerze i syntetycznych ARTICLE fixtures.
- **Macierze:** 50 factual questions obejmujących who/what/where/when/why/which/how, quantity, yes/no, active/passive/perfect/modal/negative/tag/embedded, named/bare plural/possession/comparison/existential/identity/state/location/time oraz rhetorical tails; 25 pytań retorycznych, normatywnych, hipotetycznych, stylistycznych i wartościujących.
- **Wynik:** każde factual question blokuje jako `NON_FACTUAL_PROSE`, jako inference z external fact oraz jako grounded fact bez evidence; każde może przejść z właściwym in-package evidence. Wszystkie 25 non-factual questions przechodzi jako honest inference. Pięć supported ARTICLE cases utrwala dokładny FAIL audit; grounded controls i rhetorical honest-inference control mogą osiągnąć `9/9 PASS`.
- **Kontrpróba dodatkowa:** 55 nowych question forms, bez kopii głównych macierzy; `0` pytań przeszło jako `NON_FACTUAL_PROSE`, a wszystkie non-factual controls zachowały honest-inference route.
- **Granica:** factual question błędnie nazwane honest inference może przejść; to celowo udokumentowany `SEMANTIC REVIEWER TRUST BOUNDARY`, nie finding deterministic layer.
- **Koszt:** `0.000000 USD`; brak nowych Research Cards, źródeł, retrievali i excerptów.

## 2026-08-09 — Lokalna kontrapróba marker-anywhere po MAJOR-1

- **Zakres:** bez web search, Fetch, API i zewnętrznego researchu. Sprawdzono syntetycznie wyłącznie obecność interpunkcyjnego markera pytania w segmentach ARTICLE.
- **Macierz:** 8 prefiksów (brak, Now, First, Next, Instead, Meanwhile, For now, A step back) × 3 question bodies × 9 terminatorów (`?`, `?!`, `??`, `?.`, `?;`, `?...`, quote, `)`, `]`) = `216` kombinacji.
- **Wynik:** `0` kombinacji przeszło claim gate jako `NON_FACTUAL_PROSE`; pięć potwierdzonych MAJOR examples blokuje również w supported ARTICLE flow. Minimum 25 niezależnych non-factual controls nadal przechodzi jako honest inference.
- **Granica:** badanie nie klasyfikuje znaczenia, nie dodaje vocabulary ani parsera i nie zmienia trust boundary reviewera. Koszt `0.000000 USD`; brak nowych artefaktów researchowych.

## 2026-08-09 — Offline qualification fixtures model-family core

- **Zakres:** nie wykonano researchu internetowego, provider catalogue discovery ani benchmarku realnego modelu. Użyto wyłącznie syntetycznych kandydatów, fake catalogue source, fake qualification runner i lokalnych wyników `UNQUALIFIED|PASS|FAIL`.
- **Macierz:** wersje `5`, `5.1`, `5.2`, `6`; availability/pricing/capability/qualification PASS i wszystkie wymagane odmowy; N+1 PASS, N+1 FAIL, droższe N+1, obca rodzina, dwa procesy promotion, restart i frozen intent.
- **Wynik:** fake N→N+1 promocja działa tylko po wszystkich politykach; model niekwalifikowany nie osiąga technical caller boundary; runtime provider failure nie przełącza bindingu. To dowód kontraktu orkiestracji, nie rzeczywistej jakości modelu.
- **Granica:** realne technical IDs, availability, ceny, catalogue adapter i controlled qualification pozostają `UNVERIFIED`/niewdrożone. Koszt `0.000000 USD`; brak nowych Research Cards, sources, retrievals i excerpts.

## 2026-08-10 — Lokalna weryfikacja kontraktu Anthropic dla C5

- **Źródła i granica:** bez internetu, Fetch, browsera i API. Użyto przekazanego przez właściciela provider preflightu z oficjalnej dokumentacji Anthropic (data 2026-08-10) oraz read-only introspekcji lokalnie zainstalowanego `anthropic-sdk 0.116.0`; nie tworzono klienta i nie czytano `.env`.
- **SDK shape:** `Messages.create` obsługuje `inference_geo` i `service_tier`; returned Usage ma opcjonalne pola o tych nazwach, a service-tier enum zwrotny to `standard|priority|batch`. Dlatego request żąda `global`/`standard_only`, a response — jeżeli dostarcza pola — potwierdza `global`/`standard`.
- **Modele/ceny:** snapshot pozostaje zgodny z merged catalogue: Opus `claude-opus-5` `$5/$25`, Fable `claude-fable-5` `$10/$50`, Sonnet `claude-sonnet-5` promo `$2/$10` przez 2026-08-31 i `$3/$15` od 2026-09-01. Dokładny UTC timestamp granicy Sonnet nie jest provider claim.
- **Kontrpróby:** syntetyczne workspace/env `us`, dostępność Priority, returned `us`/`priority`, brak/zły/wygasły retention acceptance, Fable refusal, returned-model mismatch i self-reported caller cost nie obchodzą bramek. Wszystkie dane i zapisy wyłącznie fake/temp.
- **Wynik/koszt:** kontrakt potwierdzony offline; brak nowych Research Cards/sources/retrievals/excerpts; `0.000000 USD`.

## 2026-08-10 — Repo-only Fable qualification authority trace

- **Zakres:** zero browsera, sieci, Fetch i provider API. Przeszukano wyłącznie aktywne repo, kod, schema `0030`, dokumentację oraz produkcję immutable.
- **Wynik danych:** deterministic registry ID `model-cda2f1745d0f0d6061f9552705edf78e`, exact pricing fingerprint `ee36e134…d80f0`, catalogue evidence fingerprint `70b212b7…b2f`, qualification envelope `13952/2048` i worst-case Fable cap candidate `0.241920`.
- **Źródła:** nie znaleziono prawdziwego external `provider_policy_ref`; wewnętrzne `anthropic-owner-verified-2026-08-09` nie jest external locatorem. Wymagany jest owner-supplied verified reference.
- **Kontrpróby:** synthetic positive/negative authority flows na nowych temp DB; caller max once, frozen price settlement, one-shot, exact target/expiry/retention gates i brak pre-effect partial state potwierdzone. Istniejące regression modules przeszły.
- **Koszt:** `0.000000 USD`; brak nowych Research Cards, sources, retrievals i excerpts.
