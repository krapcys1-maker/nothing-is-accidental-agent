# ERRORS_AND_FAILURES

## Formalny wynik WAVE 1A po naprawach — 2026-07-16

- **Stan implementera:** po `W1A-R4-01` zadeklarowano `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`.
- **Niezależny finalny re-review:** odtworzył 1036/1036 i cztery partycje exact-once, potwierdził `compileall`/`git diff --check`, wykonał 149/149 własnych kontrprób `Worker.run_once`, 36/36 SQLite floor i 30/30 recovery/reaper/crash-window; zero osiągalnych MAJOR/CRITICAL. Werdykt: `APPROVE WITH MINOR/P2`.
- **Decyzja właściciela:** WAVE 1A formalnie `CLOSED — APPROVED WITH P2`. P2-1 i P2-2 pozostają jawne i nieblokujące. Etap 1 nadal `BLOCKED`, live API nadal `ZABRONIONE`.
- **Chronologia:** poniższe wpisy `REJECTED — MAJOR`, statusy kandydackie i baseline’y 894/980/982/1007 opisują wcześniejsze momenty procesu i pozostają historycznym rejestrem błędów, nie bieżącym statusem projektu.

## 2026-07-16 — WAVE 1A: CZWARTE niezależne review = `REJECTED — MAJOR` (`W1A-R4-01`) — worker omijał reconciliation

- **Kategoria:** SAFETY / failure-boundary completeness / budget integrity (MAJOR BLOCKING).
- **Kontrpróba reviewera:** prawdziwy `Worker.run_once`, przypięty research i lokalny `sqlite3.OperationalError` po `REQUEST_STARTED` kończyły job jako `FAILED`, pozostawiając attempt w `REQUEST_STARTED`. Taki attempt nie był widoczny w kolejce L1 ani rozstrzygalny przez resolver, zachowywał rezerwację i blokował budżet. Recovery nie pomagało, dopóki lease był żywy.
- **Root cause:** workerowy fallback wywoływał `fail_job_research_execution`, który terminalizował job/run/research_run bez odczytania aktywnego provider attemptu. Ochrona crash-window w recovery nie obejmowała lokalnej awarii obsłużonej przed utratą lease.
- **Naprawa:** jedna operacja `StoragePort.fail_or_escalate_job_research_execution` w `BEGIN IMMEDIATE` podejmuje decyzję na podstawie durable attemptu. Brak aktywnego attemptu zachowuje zwykłe `FAILED`; `RESERVED` i `REQUEST_STARTED` przechodzą do `NEEDS_RECONCILIATION` z rozłącznymi powodami, jednym eventem `AUTO_ESCALATION`, jobem `NEEDS_VERIFICATION` i zachowaną rezerwacją; ponowienie na `NEEDS_RECONCILIATION` jest idempotentne. Worker, pipeline, kontrolowana niepewność, błąd mark-reconciliation i heartbeat po granicy korzystają z tej samej operacji. Triggery SQLite blokują terminalne job/run/research_run przy `RESERVED`/`REQUEST_STARTED`.
- **Nieudana próba podczas walidacji:** pierwsze uruchomienie partycji ujawniło starsze testy, które oczekiwały, że surowy terminalny `UPDATE` przejdzie do słabszej walidacji lineage. Po dodaniu mocniejszej bariery SQLite właściwym kontraktem stał się wcześniejszy `IntegrityError` i pełny rollback. Testów nie usunięto ani nie osłabiono; zaktualizowano je, by wymagały silniejszego inwariantu.
- **Nieudana próba własnego harnessu:** pierwsza rozszerzona kontrpróba worker↔maintenance uruchomiła `Worker.run_once` w innym wątku na obiekcie storage utworzonym w wątku głównym. SQLite zgodnie z thread confinement nie dopuścił Workera do granicy, więc nieetykietowana asercja upadła; próba diagnostyczna dodatkowo pozostawiła chwilowo otwarty plik temp i cleanup zgłosił `WinError 32`. To był błąd harnessu, nie dowód poprawności ani defekt produktu. Katalog został jawnie zweryfikowany i usunięty. Poprawiony harness otwiera osobne połączenie w wątku Workera; wtedy Worker i recovery zbiegły do jednego `NEEDS_RECONCILIATION`, jednego eventu i jednego attemptu.
- **Granice:** P2-1 pozostaje fail-closed — normalization nie naprawia ani nie zatwierdza niespójnego fingerprintu, a resolver nadal odmawia. P2-2 bez nadmiernej deklaracji: StoragePort wykonuje resolver atomowo w jednej transakcji; SQLite wymusza spójny trwały stan końcowy; SQLite nie udowadnia pochodzenia wszystkich danych wobec arbitralnego uprzywilejowanego autora wielu tabel.
- **Dowód:** +29 testów (`1007 → 1036`), suite 1036/1036, partycje exact-once 248+253+267+268, 38 testów concurrency/race ×30, siedem plików krytycznych ×10, QA lineage ×10 bez wycieków oraz nowy E2E `Worker.run_once` w 10 świeżych procesach. Zero provider calli, sieci, API, browsera, publikacji i kosztu; chroniona baza niezmieniona. Status: `WAVE 1A — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; WAVE otwarta, Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## 2026-07-16 — WAVE 1A: TRZECIE niezależne review = `REJECTED — MAJOR` (W1A-AUD-04 przeklasyfikowany + dwa nowe MAJOR SQLite) — naprawione w jednej fali

- **Kategoria:** SAFETY / recovery completeness / durable-ledger integrity (MAJOR ×3).
- **W1A-AUD-04 (MAJOR BLOCKING, wcześniej P2):** po crashu i wygaśnięciu lease trwałe `RESERVED`/`REQUEST_STARTED` pozostawały niewidoczne dla `list-reconciliations`, nierozstrzygalne przez resolver („Only NEEDS_RECONCILIATION") i bezterminowo blokowały budżet; `REQUEST_STARTED` mógł kryć realny, niezaksięgowany koszt. Test audytowy utrwalał stuck state jako sukces — to nie było poprawne kryterium. **Naprawa:** recovery (`release_or_requeue_expired_leases`) w tej samej transakcji atomowo eskaluje oba crash-windows do `NEEDS_RECONCILIATION` z enumerowanym powodem (`LEASE_EXPIRED_BEFORE/AFTER_REQUEST_STARTED`) i append-only eventem `AUTO_ESCALATION`; idempotentne, serializowane przez `BEGIN IMMEDIATE` (dwa maintenance = dokładnie jedna eskalacja), nigdy przy żywym lease, nigdy dla terminali, bez retry/attemptu #2/providera; eskalacja unieważnia stary preview token; attempt bez `REQUEST_STARTED` (dowodliwie brak calla) może być rozstrzygnięty wyłącznie `NOT_CHARGED` (aplikacja + macierz stanów: `RECONCILED_SETTLED` wymaga startu requestu).
- **W1A-SQLITE-01 (MAJOR):** surowy `UPDATE` mógł ustawić `RECONCILED_RELEASED` przy `job=NEEDS_VERIFICATION`, `run=RUNNING`, `research_run=PENDING` i zerze eventów — terminalizacja attemptu nie wymagała pełnej atomowej terminalizacji lifecycle i historii. **Naprawa:** resolver flipuje attempt jako OSTATNIĄ trwałą mutację (`walidacja → lifecycle → usage/cache → FINAL_RESOLUTION → attempt`), a `0014` (in-place) dokłada trzy triggery terminalizacji: wymagany dokładnie zgodny event `FINAL_RESOLUTION` (status/resolution/operator/note), terminalny spójny lifecycle zgodny z execution resolution (FAILED/FAILED/FAILED bez karty albo DONE/SUCCESS/COMPLETE z kartą) ze zwolnioną rezerwacją i lease, oraz cache'e równe kanonowi (tolerancja pół kwantu 5e-7). Eventy (każdego typu) można dopisywać wyłącznie przy żywym `NEEDS_RECONCILIATION` — nigdy po terminalu.
- **W1A-SQLITE-02 (MAJOR):** po prawidłowym `RECONCILED_SETTLED` surowy SQLite mógł zmienić koszt `model_usage` (0.05 → 0.123456 przy cache'ach 0.05), a następnie usunąć wpis — łamiąc `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd` i kanon. **Naprawa:** kanoniczny `model_usage` rekoncyliowanego attemptu ma triggery no-UPDATE (każda kolumna) i no-DELETE; nowy wpis dla terminalnego attemptu jest niereprezentowalny (relacja + UNIQUE); `runs.cost_usd` i `research_runs.total_cost_usd` są zamrożone po terminalu.
- **W1A-AUD-01 (MINOR, domknięte):** błędy `OSError/RuntimeError/sqlite3.Error` podczas samego zapytania/formatowania/close w `list-reconciliations` → kontrolowany exit 6 (wcześniej traceback); `reconcile-attempt` dołożone `RuntimeError` i guarded close.
- **W1A-DOC-01 (MINOR, domknięte):** stale „980" w MASTER_ARCHITECTURE/IMPLEMENTATION_ROADMAP/ARTICLE_EVIDENCE/RESEARCH_LOG/opis-budowy — sweep do aktualnego baseline; historyczne 980/982 jawnie historyczne.
- **W1A-QA-01 (P2, domknięte):** `reconciliation_lineage_disproof.py` zostawiał katalogi `mkdtemp()`; teraz prefiksowane `nia-lineage-disproof-`, cleanup w `finally` także po wyjątku, twarda kontrola pozostałości w exit code + trwały test subprocess.
- **Dowód:** +25 trwałych testów (macierz eskalacji H1–H20: żywy/martwy lease, wyścig dwóch maintenance, reopen przed/po, widoczność queue+CLI, preview/stale-token, `NOT_CHARGED`-only dla byłego `RESERVED`, `CHARGE_UNKNOWN`/`CHARGED_KNOWN` dla byłego `REQUEST_STARTED`, budżet przed/po, brak retry/attemptu #2, rollback failpointów eskalacji, append-only `AUTO_ESCALATION`; macierz raw-SQLite: partial lifecycle, brak/niezgodny `FINAL_RESOLUTION`, rozjechany cache, mutacja/kasowanie/duplikat kanonu, zamrożone cache; ciek QA). Licznik **982 → 1007**, pełny suite 1007/1007, 4 partycje exact-once 4/4 exit 0, concurrency 33×30 = 30/30, pliki 10/10, QA 10/10 bez pozostałości, niezależne kontrpróby 5/5 (wyścig resolver↔eskalacja, heartbeat↔recovery, partial lifecycle, porzucona transakcja po reopen, budżet przed/po), `data/agent.db` byte-identical. Szczegóły: ADR-066. WAVE 1A = `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-16 — WAVE 1A: pełny audyt software-assurance working tree (W1A-AUD) — zero MAJOR/CRITICAL, trzy MINOR naprawione, jeden P2 report-only (status historyczny: trzecie review przeklasyfikowało AUD-04 na MAJOR — patrz wpis wyżej)

- **Kategoria:** AUDIT / CLI robustness / contract hygiene / lifecycle boundary.
- **Zakres:** pełny read-only audit HEAD `c25e125` + wszystkich niecommitowanych zmian (resolver, migracja 0014, CLI, testy, QA, dokumentacja) zlecony przez właściciela; autoryzowana jedna skonsolidowana fala napraw. Regresja wszystkich wcześniejszych findingów (W1A-RR-01…06, W1A-NEW-01/02, W1A-VERIFY-01/02) zweryfikowana niezależnie — wszystkie pozostają ZAMKNIĘTE.
- **W1A-AUD-01 (MINOR, naprawione):** `list-reconciliations` nie miało kontrolowanej obsługi `ConfigError`/`sqlite3.Error`/`OSError` — błąd konfiguracji lub storage kończył się surowym tracebackiem zamiast kontrolowanym exit code. Naprawa: symetryczna obsługa jak w `reconcile-attempt` (config → 3, storage → 6) + trwały test.
- **W1A-AUD-02 (MINOR, naprawione):** `ProviderAttemptReconciliationResult.version_token` było martwym polem — nigdy nieustawiane i niekonsumowane; sugerowało reviewerowi, że confirm zwraca świeży token. Usunięte; version token pochodzi wyłącznie z preview.
- **W1A-AUD-03 (MINOR, naprawione):** anotacja `actual_cost_usd: float | None` w `StoragePort` i `SqliteStorage` była niezgodna z faktycznym kontraktem — CLI świadomie przekazuje `str` dla dokładności Decimal. Teraz `float | str | None`.
- **W1A-AUD-04 (P2, REPORT-ONLY, styczne do otwartego P2-19):** attempt `RESERVED`/`REQUEST_STARTED` po twardym crashu procesu i wygaśnięciu lease (job → `NEEDS_VERIFICATION` przez recovery) jest **niewidoczny** dla `list-reconciliations` i **nierozwiązywalny** przez resolver (celowy kontrakt „Only NEEDS_RECONCILIATION may be resolved"); jego rezerwacja bezterminowo pomniejsza dzienny/miesięczny budżet (kierunek konserwatywny — zero ryzyka fail-open/nadpłaty; `REQUEST_STARTED` może jednak oznaczać realny, niezaksięgowany koszt providera — dokładnie klasa P2-19). Preview pozostaje oknem odczytu operatora. Rozszerzenie kontraktu resolvera (np. eskalacja `REQUEST_STARTED → NEEDS_RECONCILIATION` przy martwym lease) wymaga jawnej decyzji właściciela — nie zmieniono zrecenzowanego kontraktu. Trwały test dokumentujący granicę: `test_crashed_request_started_attempt_after_lease_expiry_is_fail_closed` *(historyczne: trzecie review odrzuciło ten kontrakt jako utrwalenie defektu; test zastąpiony macierzą eskalacji H1–H20 — patrz wpis wyżej)*.
- **Kontrpróby audytora (temp DB, safety kernel, świeże procesy):** replay terminalnej decyzji z innym note/operatorem/finansem → „already reconciled with different parameters", zero mutacji; granice half-quantum `0.0000004` (odrzucone) / `0.0000005 → 0.000001` / `0.0000015 → 0.000002` (ROUND_HALF_UP w ledgerze); ekstremalne koszty CLI `NaN`/`Infinity`/`-Infinity`/`not-a-number` → exit 4, `1e400` → kontrolowany exit 6 — wszystko bez mutacji.
- **Dowód:** licznik **980 → 982**; pełny suite 982/982; 4 partycje exact-once (237+241+254+250); concurrency 30/30; reconciliation+lineage files 10/10; `scripts/qa/reconciliation_lineage_disproof.py` 10/10; `compileall` i `git diff --check` czyste; `data/agent.db` byte-identical (SHA-256 `CAEDDA05…FEFB`). WAVE 1A = `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A `W1A-VERIFY-02`: fail-open pełnego lineage (foreign `runs.account_id` / ANALYTICS workflow)

- **Kategoria:** SAFETY / accounting integrity / authorization (MAJOR, drugie niezależne review = `REJECTED — MAJOR`).
- **Kontrpróba (dokładna, odtworzona na temp DB):** `jobs.account_id` i `research_runs.account_id` = konto właściciela; `runs.account_id` = konto obce; `runs.workflow` = `ANALYTICS`.  Resolver zaakceptował reconciliation i terminalizował attempt→`RECONCILED_RELEASED`, job/run/research_run→`FAILED` (+1 event).  Dowód: `scripts/qa/reconciliation_lineage_disproof.py` (przed naprawą: LEAK; po naprawie: BLOCKED, zero mutacji).
- **Root cause:** `_reconciliation_state_row` nie czytał `runs.account_id`/`runs.workflow`/`jobs.kind`/`jobs.workflow`; walidacja sprawdzała tylko `research_runs` account/topic.  Brak weryfikacji pełnej relacji `provider_attempt → job → run → research_run → account → workflow → topic → durable intent`.  **Zielony baseline 955/955 (ADR-064) nie obejmował tego przypadku** — wprost pokazuje, że przejście suite nie dowodzi kompletności zakresu.
- **Naprawa (defense-in-depth):** (1) `_reconciliation_require_consistent_lineage` waliduje cały lineage przed mutacją; (2) version token v2 obejmuje wszystkie pola lineage (stale między preview a confirm ⇒ fail-closed); (3) trigger SQLite `provider_attempts_reconcile_requires_consistent_lineage` (0014 in-place) blokuje niespójną terminalizację (również `json_extract` payload↔job).  Fingerprint intentu pozostaje inwariantem aplikacyjnym (SQLite nie przelicza SHA-256) — udokumentowane.
- **Dowód:** `tests/test_reconciliation_lineage.py` (17 negatywnych rozjazdów, każdy = pełny brak mutacji; stale token 14–17; raw-trigger; pozytywne), `scripts/qa/reconciliation_lineage_disproof.py` 10/10 w świeżych procesach; licznik **955 → 980**, pełny suite 980/980, 4 partycje exact-once, concurrency 30/30, `data/agent.db` bez zmiany.  Szczegóły: ADR-065.  WAVE 1A = `CANDIDATE`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A `W1A-VERIFY-01`: niedeterministyczny test resolver↔reaper (flaky), nie fałszywy sukces

- **Kategoria:** TEST DETERMINISM / lifecycle completeness (SAFE — bez wpływu na bezpieczeństwo).
- **Objaw:** niezależna weryfikacja ADR-063 pokazała, że deklarowane „948 passed" nie było odtwarzalne — `test_resolver_interleaves_with_recovery_and_reaper_without_reviving_attempt` przechodził ~50% (3/6 w izolacji), reszta suite stabilna (947 passed + 1 flaky).
- **Root cause:** maintenance-reaper `reap_orphaned_stale_runs` ustawia osierocony stale run na `STOPPED`, gdy job pozostaje `NEEDS_VERIFICATION` (guard reapera nie blokuje — `NEEDS_VERIFICATION ∉ {QUEUED,LEASED,RUNNING}`), a resolver `EXECUTION_FAILED` akceptował tylko `run_status ∈ {RUNNING, FAILED}`. Kolejność wątków decydowała: resolver-first → run `RUNNING` → OK; reaper-first → run `STOPPED` → resolver fail-closed. Żadnego fałszywego `DONE`, dodatkowego usage ani attemptu #2 — wyłącznie flaky.
- **Naprawa (autoryzowana, minimalna):** `EXECUTION_FAILED` akceptuje `run_status ∈ {RUNNING, STOPPED, FAILED}` (wspólny `_EXECUTION_FAILED_RUN_STATUSES` w warunku i w CAS `UPDATE`, `COALESCE` zachowuje historię reaper/maintenance), atomowo `STOPPED → FAILED`; `RESULT_ALREADY_FINALIZED` i kontrakt finansowy bez zmian; `STOPPED` nigdy → `DONE`.
- **Dowód:** 7 nowych deterministycznych testów; flaky node **30/30**, plik **10/10**; pełny suite **955** offline, 4 partycje exact-once, 20/20 kontrprób BLOCKED, `data/agent.db` niezmieniona. Szczegóły: ADR-064. WAVE 1A = `CANDIDATE`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A: niezależny audyt odrzucił pierwszą iterację (`REJECTED — MAJOR`), naprawa in place

- **Kategoria:** SAFETY / accounting integrity / durable proof.
- **Odrzucone findingi:** W1A-RR-01 (istniejący `model_usage` akceptowany po samym koszcie), W1A-RR-02 (`RESULT_ALREADY_FINALIZED` mógł użyć współdzielonej/cudzej karty), W1A-RR-03 (`CHARGE_UNKNOWN` nadpisywał operatora/notatkę — utrata historii), W1A-RR-04 (migracja 0014 dopuszczała puste pola audytu, nieznane wartości resolution, audyt w złych stanach i usunięcie terminalnego `RECONCILED_RELEASED`), W1A-RR-05 (sprzeczna dokumentacja), W1A-RR-06 (CLI bez trwałego stanu/version tokenu), W1A-NEW-01 (`CHARGED_KNOWN`/`NOT_CHARGED` + `MANUAL` = terminalny attempt z jobem na zawsze w `NEEDS_VERIFICATION`), W1A-NEW-02 (`CHARGED_KNOWN` + `MANUAL` zapisywał usage bez odświeżenia cache — rozjazd ledger↔cache).
- **Naprawa (jedna fala):** append-only `reconciliation_events` jako jedyna historia; pełna weryfikacja tożsamości istniejącego usage; wyłączna własność karty przez `UNIQUE research_runs(research_card_id)`; usunięty dead-end `MANUAL` (tylko z `CHARGE_UNKNOWN`); niezmienna spójność `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd`; `CHARGED_KNOWN` wymaga kosztu>0; migracja 0014 poprawiona **in place** z pełnym kontraktem i surowymi wymuszeniami SQLite; CLI preview/confirm z version tokenem i kontrolowanymi exit codes.
- **Dowód:** **955 testów offline** (w tym negatywne testy surowego SQLite, tożsamość usage, wyłączna własność karty, macierz lifecycle, restart failpoints, współbieżność, subprocess), 0014 fresh/upgrade/rollback + `integrity_check`/`foreign_key_check`, `data/agent.db` bez zmiany. WAVE 1A = `CANDIDATE`; WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 `BLOCKED`; live API `ZABRONIONE`. Historyczne 894/13 są historyczne.

## 2026-07-15 — WAVE 1A: niepewnego kosztu nie wolno zamienić w retry

- **Kategoria:** SAFETY / accounting consistency.
- **Ryzyko:** `NEEDS_RECONCILIATION` łączy nieznany skutek finansowy z zatrzymanym jobem. Automatyczne zwolnienie rezerwacji, wpisanie zgadywanej kwoty albo nowe wywołanie providera mogłyby sfałszować historię kosztu.
- **Naprawa:** resolver L1 ma trzy jawne wyniki finansowe i trzy niezależne wyniki wykonawcze. Tylko `CHARGED_KNOWN` może dodać canonical `model_usage`; `NOT_CHARGED` jest odrzucane przy usage; `CHARGE_UNKNOWN` pozostaje nierozstrzygnięty. Failpointy po usage/attempt/run/research_run/job i przed commitem dowodzą pełnego rollbacku.
- **Dowód:** migracja 0014 rollback, `UNIQUE(request_id)` dla usage, konflikty operatorów, stale preview CLI, błędne kwoty i stanowe odmowy; po naprawie `REJECTED — MAJOR` **955 testów offline**, 14 migracji, bez API, sieci, kosztu lub zmiany chronionej bazy. (Historyczny wynik iteracji: 919.)
- **Status:** WAVE 1A `CANDIDATE — AWAITING INDEPENDENT REVIEW` (po naprawie); Etap 1 `BLOCKED`, live API `ZABRONIONE`.

### [2026-07-13] P1 — rozdzielona inicjalizacja RESEARCH tworzyła osierocone runy po crashu

- **Kategoria:** TECH
- **Co miało działać:** restart workera nie może tworzyć drugiego runu dla jednego joba RESEARCH.
- **Co się zepsuło:** crash po `create_run` i `create_research_run`, lecz przed `attach_job_run`, zostawiał `jobs.run_id=NULL`; recovery requeue’owało job i drugi worker tworzył drugi komplet.
- **Przyczyna:** trzy osobne commity nie utrzymywały inwariantu „run i research_run istnieją tylko wraz z `jobs.run_id`”.
- **Naprawa i dowód:** ADR-044 wprowadza jeden `BEGIN IMMEDIATE` dla run, research_run i CAS joba; failpointy przed i po commicie, reopen/recovery, fencing i `Barrier` potwierdzają brak duplikatu. Brak API, zmiany `data/agent.db` i kosztu rzeczywistego.

## Cel

Rejestr błędów, awarii, nieudanych uruchomień i sytuacji, w których system zachował się źle lub wymagał zatrzymania. Służy trzem rzeczom: (1) nauce i poprawie, (2) uczciwemu materiałowi do końcowego artykułu na „Chaos Engine" (błędy są częścią eksperymentu), (3) mierzeniu, jak często agent zawodzi i dlaczego. Odróżniamy błąd techniczny (wyjątek, awaria selektora) od błędu jakościowego (halucynacja źródła, słaby komentarz, powtarzalność).

## Zasady

- Jeden wpis = jedno zdarzenie.
- Zapisz też błędy „ciche" (np. przekroczony budżet zatrzymał run — to działanie zabezpieczenia, ale warto odnotować).
- Bez sekretów w treści błędu (zanonimizuj klucze/tokeny w stack trace).
- Powiąż z ryzykiem z planu (R1–R12), jeśli pasuje.

## Kategorie

`TECH` (wyjątek/awaria), `BROWSER` (Substack UI/sesja), `QUALITY` (halucynacja/styl/duplikat), `COST` (budżet), `SAFETY` (kill-switch/stop-condition), `INJECTION` (prompt injection), `ACCOUNT` (pomyłka konta).

## Szablon wpisu

```markdown
### [YYYY-MM-DD HH:MM] Krótki tytuł błędu
- **Kategoria:** TECH | BROWSER | QUALITY | COST | SAFETY | INJECTION | ACCOUNT
- **Ryzyko z planu:** R? (lub —)
- **Konto / run_id:** account_id / run uuid (jeśli dotyczy)
- **Co miało działać:** oczekiwane zachowanie
- **Co się zepsuło:** widoczny objaw
- **Pełny komunikat błędu:** ``` stack trace / komunikat (ZANONIMIZUJ klucze/tokeny) ```
- **Prawdopodobna przyczyna:** ustalona lub hipoteza
- **Sposób naprawy:** co zrobiono, by naprawić
- **Liczba prób:** ile podejść zanim zadziałało (lub „nadal OPEN")
- **Czy może się powtórzyć:** tak/nie + kiedy; czy dodano zabezpieczenie/test
- **Wpływ na harmonogram / koszt:** ile czasu stracone / czy była strata kosztu USD
- **Status:** OPEN | FIXED | WORKAROUND | WONTFIX
```

---

## Znane problemy (stan na 2026-07-11)

### [2026-07-11] Brak ochrony pliku `.env` przed commitem
- **Kategoria:** SAFETY
- **Ryzyko z planu:** R1
- **Konto / run_id:** —
- **Co miało działać:** klucz API w lokalnym `.env` jest w porządku; repo powinno gwarantować, że `.env` nigdy nie trafi do commitów.
- **Co się zepsuło:** brakowało `.gitignore` i `.env.example` — czyli mechanizmu chroniącego przed przypadkowym zacommitowaniem/udostępnieniem `.env`. **Problemem nie jest obecność klucza w `.env`, lecz brak ochrony przed commitem.**
- **Pełny komunikat błędu:** — (nie błąd runtime, ryzyko konfiguracyjne)
- **Prawdopodobna przyczyna:** repo powstało bez pliku `.gitignore`.
- **Sposób naprawy:** utworzenie `.gitignore` (ignoruje `.env`, `data/`, `config/accounts.yaml`, `config/growth_policy.yaml`, artefakty Pythona) oraz `.env.example` z placeholderami. Klucza nie kopiowano do żadnego dokumentu, logu, screenshotu ani pliku przykładowego. Wykonane w Etapie 0.
- **Liczba prób:** 1
- **Czy może się powtórzyć:** nie, o ile `.gitignore` pozostaje; przy inicjalizacji git zweryfikować `git status` (brak `.env` na liście).
- **Wpływ na harmonogram / koszt:** brak (wykryte przed jakimkolwiek commitem i przed płatnym użyciem).
- **Status:** FIXED (ochrona dodana). Uwaga rezydualna: jeśli repo będzie kiedyś publiczne, przed publikacją i tak zalecana rotacja klucza — właściciel świadomie odłożył rotację.

### [2026-07-11 19:30] Błędny import w teście pipeline (złapany przed uruchomieniem)
- **Kategoria:** TECH
- **Ryzyko z planu:** —
- **Konto / run_id:** —
- **Co miało działać:** test `test_research_pipeline.py` importuje kod walidacji.
- **Co się zepsuło:** użyto ścieżki `app.workflows.research.validation` zamiast `app.research.validation`.
- **Pełny komunikat błędu:** `ModuleNotFoundError` (potencjalny — wychwycony podczas pisania przed pełnym runem).
- **Prawdopodobna przyczyna:** walidacja leży w pakiecie `app/research/`, nie `app/workflows/research/`.
- **Sposób naprawy:** poprawiono import na `app.research.validation`.
- **Liczba prób:** 1.
- **Czy może się powtórzyć:** możliwe przy dużej liczbie modułów; mityguje to uruchamianie pełnego `pytest` przed uznaniem etapu za zamknięty.
- **Wpływ na harmonogram / koszt:** brak (naprawione przed pierwszym runem, 0 USD).
- **Status:** FIXED

### [2026-07-11 19:09 UTC] Pierwsze realne wywołanie Anthropic — ucięty JSON, research odrzucony
- **Kategoria:** TECH
- **Ryzyko z planu:** R6 (pośrednio — bramka jakości zadziałała poprawnie i NIE przepuściła niepełnego wyniku)
- **Konto / run_id:** nothing_is_accidental / `1b649314-27cf-4b29-857e-287175664a3f`
- **Co miało działać:** pierwsze kontrolowane, realne (płatne) wywołanie `AnthropicResearchClient` dla tematu #2 „What really happens to your suitcase after check-in" (cap 0.30 USD, max 6 web searchy, max 1 retry, zatwierdzone jawnie przez właściciela) miało zwrócić poprawny JSON z pełną Research Card.
- **Co się zepsuło:** model zwrócił długą odpowiedź (>8100 znaków), ale JSON został ucięty w połowie stringa — najbardziej prawdopodobna przyczyna: model wyczerpał `max_tokens=3000` zanim skończył emitować pełną strukturę (dużo pól + do 6 źródeł ze szczegółami).
- **Pełny komunikat błędu:** `Niepoprawny JSON z modelu: Unterminated string starting at: line 67 column 7 (char 8109)`
- **Prawdopodobna przyczyna:** `max_tokens=3000` w `app/research/anthropic_client.py` jest za niskie dla „pełnej" Research Card przy realnym, bogatym wyniku z 6 wyszukiwaniami (w przeciwieństwie do `FakeResearchClient`, który zawsze zwraca krótki, z góry ustalony JSON).
- **Sposób naprawy:** ZGODNIE Z POLECENIEM WŁAŚCICIELA **nie ponowiono** automatycznie (błąd parsowania z definicji nie jest retry'owany — to zadziałało poprawnie, `call_count == 1`). Naprawa merytoryczna (wyższy `max_tokens` i/lub bardziej zwięzły prompt) jest **rekomendacją na następną, osobno zatwierdzoną próbę**, nie została wdrożona teraz.
- **Liczba prób:** 1 (zgodnie z jawnym limitem — bez auto-retry pełnego wywołania).
- **Czy może się powtórzyć:** tak, dopóki `max_tokens` nie zostanie podniesiony lub prompt nie będzie wymuszał bardziej zwięzłego JSON-a. Dodano defensywne czyszczenie code-fence (`_strip_code_fence`) na wypadek innej przyczyny nieudanego parsowania, ale to nie adresuje przycięcia przez limit tokenów.
- **Wpływ na harmonogram / koszt:** research dla tematu #2 nie powstał (Research Card nie została utworzona — bramka jakości poprawnie nie przepuściła niepełnego wyniku). **Koszt (potwierdzony w konsoli Anthropic, później tego samego dnia): 0.25 USD** (0.21 USD tokeny + 0.04 USD web search) — patrz wpis „Realny koszt zgubiony..." niżej.
- **Status:** OPEN (wymaga osobno zatwierdzonej kolejnej próby); mechanizm nie-ponawiania zadziałał zgodnie z założeniem. **Naprawa architektoniczna wdrożona 2026-07-11 tego samego dnia:** dwuetapowy pipeline (`gather_sources` + `synthesize_card`, ADR-016) z lżejszymi schematami JSON w każdym etapie — zmniejsza ryzyko ucięcia bez samego tylko podnoszenia `max_tokens`. Kolejna próba nadal wymaga osobnej zgody właściciela.

### [2026-07-11 19:09 UTC] Realny koszt zgubiony przy błędzie parsowania (bug w księgowaniu)
- **Kategoria:** COST
- **Ryzyko z planu:** R7 (kontrola kosztów) — wykryte PRZEZ pierwszy realny run, nie wcześniej, bo dry_run/testy nigdy nie ćwiczyły tej ścieżki z prawdziwym `usage`.
- **Konto / run_id:** nothing_is_accidental / `1b649314-27cf-4b29-857e-287175664a3f`
- **Co miało działać:** każde realne (płatne) wywołanie Anthropic — udane czy nie — powinno zapisać rzeczywiste zużycie tokenów/web search i koszt w `model_usage` + `docs/COSTS.csv`.
- **Co się zepsuło:** `AnthropicResearchClient.run_research()` pobierał `(text, usage)` od `_caller`, ale gdy `_parse(text)` rzucał `ResearchParseError`, wyjątek propagował się natychmiast — `usage` (realne tokeny zwrócone przez API) nigdy nie docierał do `UsageTracker.record(...)`. `run_research_pipeline` w bloku `except ResearchError` zapisywał `cost_usd=0.0` na sztywno. Efekt: realne, płatne wywołanie API zostało zarejestrowane w bazie jako koszt **0.00 USD** — de facto zniknęło z księgowości lokalnej, mimo że Anthropic faktycznie naliczył koszt na koncie.
- **Pełny komunikat błędu:** brak wyjątku — to cichy błąd księgowy (`runs.cost_usd=0.0`, zero wierszy w `model_usage` dla tego `run_id`), wykryty ręczną inspekcją bazy po runie.
- **Prawdopodobna przyczyna:** ścieżka błędu w pipeline nie była nigdy ćwiczona z realnym `usage` — testy jednostkowe/pipeline używały wyłącznie `FakeResearchClient` (zawsze sukces) lub wstrzykniętego callera bez scenariusza "sukces API + błąd parsowania".
- **Sposób naprawy:** (1) `ResearchError` (i podklasy `ResearchTimeout`/`ResearchParseError`) niosą teraz opcjonalne `usage`/`model`; (2) `AnthropicResearchClient._default_caller`/`run_research` dopina realny `usage` do `ResearchParseError` przed re-raise; (3) `run_research_pipeline` w bloku `except ResearchError` sprawdza `getattr(exc, "usage", None)` i jeśli jest — księguje realny koszt przez `usage_tracker.record(...)` zanim zwróci błąd. Dodano 3 testy regresyjne (`test_invalid_json_still_carries_real_usage`, `test_web_search_max_uses_passed_to_tool_spec`, `test_real_usage_recorded_even_when_parse_fails`) — **47 testów zielonych** po naprawie.
- **Liczba prób:** 1 (znalezione i naprawione od razu po pierwszym realnym runie, bez dodatkowego płatnego wywołania — naprawa i testy używają wyłącznie klientów zastępczych).
- **Czy może się powtórzyć:** nie dla tej konkretnej ścieżki (pokryte testem regresyjnym). Otwarte ryzyko rezydualne: jeśli błąd wystąpi w INNYM miejscu niż `_parse()` (np. między `client.messages.create()` a odczytem `message.usage`), realny `usage` może nadal nie zostać przechwycony — do rozważenia przy kolejnych realnych runach.
- **Wpływ na harmonogram / koszt:** w momencie wystąpienia — **dokładny rzeczywisty koszt tego JEDNEGO wywołania nie był znany** lokalnie, bug uniemożliwił jego zapisanie. **AKTUALIZACJA (2026-07-11, później tego samego dnia):** właściciel zweryfikował rzeczywisty koszt w konsoli Anthropic i podał dokładną kwotę: **0.25 USD** (0.21 USD tokeny + 0.04 USD web search, 4 wyszukiwania). Baza danych i `docs/COSTS.csv` zostały skorygowane z „0.00 USD"/„górna granica ≈0.095 USD" na potwierdzone **0.25 USD** (przez `model_usage` + `runs.cost_usd`, istniejącymi metodami repozytorium, bez SQL poza nimi).
- **Status:** FIXED (mechanizm ORAZ historyczna kwota — obie strony incydentu domknięte). Zobacz też oddzielny wpis „Pre-flight cost estimator underestimated the real cost" niżej — to inny błąd (estymacja PRZED wywołaniem), wykryty przy okazji weryfikacji tej kwoty.

### [2026-07-11] Pre-flight cost estimator underestimated the real cost
- **Kategoria:** COST
- **Ryzyko z planu:** R7 (kontrola kosztów)
- **Konto / run_id:** nothing_is_accidental / `1b649314-27cf-4b29-857e-287175664a3f`
- **Co miało działać:** pesymistyczny szacunek kosztu PRZED wywołaniem (`scripts/run_capped_research.py`, ówczesna `_preflight_worst_case_usd`) miał być bezpieczną GÓRNĄ GRANICĄ rzeczywistego kosztu — czyli realny koszt nie powinien go przekroczyć.
- **Co się zepsuło:** po weryfikacji w konsoli Anthropic okazało się, że rzeczywisty koszt (**0.25 USD**) był **wyższy** niż pesymistyczny szacunek (**0.095 USD**), który miał być górną granicą. Dane:
  - estimated maximum: **0.095 USD**
  - actual total: **0.25 USD**
  - difference: **+0.155 USD**
  - actual/estimate ratio: **2.63×**
  - estimation error: **≈+163%**
- **Pełny komunikat błędu:** brak wyjątku — to błąd modelu estymacji, nie awaria kodu; wykryty przez porównanie z rzeczywistą kwotą z panelu dostawcy.
- **Prawdopodobna przyczyna:** stary estymator zakładał **płaski, niezależny od liczby wyszukiwań** bufor `input_tokens=20000` jako „hojny" zapas na treść zwracaną przez web search. W praktyce treść wyników wyszukiwania (i związane z tym wielokrokowe przetwarzanie po stronie serwera przy korzystaniu z narzędzia web search) generuje koszt tokenów, który **rośnie z liczbą wyszukiwań**, a nie jest stałą wielkością — płaski bufor 20 000 tokenów okazał się rzędu wielkości za mały przy 4 realnych wyszukiwaniach.
- **Kluczowe wyjaśnienie architektoniczne:** `--max-cost-usd` (i pochodne capy w kodzie) **nigdy nie były twardym limitem egzekwowanym W TRAKCIE pojedynczego żądania API** — Anthropic nie oferuje przerwania pojedynczego, niestreamowanego wywołania w połowie po przekroczeniu kwoty. `--max-cost-usd` to i pozostaje **kontrola PRZED startem, oparta na estymacji** — jeśli estymacja jest zła, kontrola nie chroni tak, jak się wydaje. Realną, twardą górną granicę per-wywołanie wyznaczają WYŁĄCZNIE parametry przekazane do API: `max_tokens` (output) i `max_uses` (web search) — te NIE zawiodły (wywołanie zmieściło się w zatwierdzonym limicie 0.30 USD), zawiodła tylko ich wyceną PRZED wywołaniem.
- **Sposób naprawy:** nowy moduł `app/research/cost_estimator.py` — estymacja skalowana z liczbą wyszukiwań (nie płaski bufor), skalibrowana z tej jedynej realnej obserwacji (0.21 USD tokenów / 4 wyszukiwania), z **wymaganym minimalnym marginesem bezpieczeństwa 50%** (funkcja rzuca `ValueError` poniżej minimum). Dodatkowo: pipeline podzielony na dwa etapy (`gather_sources` / `synthesize_card`, ADR-016) — etap zbierania źródeł ograniczony do max 4 wyszukiwań (z 6) i lżejszego schematu JSON, etap syntezy nie używa web search wcale (koszt inputu pod pełną kontrolą, nie zależny od treści wyników wyszukiwania).
- **Liczba prób:** 1 (błąd znaleziony przy weryfikacji pierwszego realnego runu; naprawa i cała nowa logika przetestowane wyłącznie lokalnie, bez dodatkowego płatnego wywołania).
- **Czy może się powtórzyć:** ryzyko zredukowane, nie wyeliminowane — nowy estymator nadal jest kalibrowany z **n=1** (jedna realna obserwacja). Test regresyjny (`tests/test_cost_estimator.py::test_new_estimator_would_not_have_cleared_the_failed_run`) pilnuje, żeby estymator dla parametrów tamtego runu nigdy nie zwrócił wartości poniżej realnego kosztu. Estymator wymaga doprecyzowania po kolejnych realnych runach (więcej punktów kalibracyjnych).
- **Wpływ na harmonogram / koszt:** 0.00 USD (naprawa i testy offline). Opóźnia kolejne realne wywołanie do czasu nowej, osobnej zgody właściciela — świadomie, zgodnie z poleceniem „nie wykonuj jeszcze drugiego płatnego wywołania".
- **Status:** FIXED (nowy estymator + dwuetapowy pipeline), z jawnie udokumentowanym ryzykiem rezydualnym (kalibracja n=1).

### [2026-07-12] Wyniki etapu A istniały tylko w pamięci procesu (ryzyko utraty przy awarii między etapami)
- **Kategoria:** COST
- **Ryzyko z planu:** R7 (kontrola kosztów) — ryzyko wykryte i naprawione PROAKTYWNIE, bez realnego incydentu (nie doszło do faktycznej utraty danych; to analiza architektury po incydencie z Etapu 1C/1D).
- **Konto / run_id:** — (dotyczy architektury, nie konkretnego runu)
- **Co miało działać:** dwuetapowy pipeline (`gather_sources` + `synthesize_card`, ADR-016) miał chronić przed utratą kosztownych wyników web search przy błędzie finalnego parsowania.
- **Co się zepsuło:** ochrona działała TYLKO wewnątrz jednego wywołania funkcji `run_two_stage_research_pipeline` — wyniki etapu A (`SourceGatheringResult`) istniały wyłącznie jako zmienna w pamięci procesu Python między wywołaniem etapu A a etapu B. Awaria procesu MIĘDZY etapami (crash, restart maszyny, zamknięty terminal, przerwane zasilanie) nadal traciłaby realnie opłacone wyniki wyszukiwania — dokładnie ten sam rodzaj straty co przy incydencie z 2026-07-11, tylko przesunięty o jeden poziom głębiej w architekturze (z „wewnątrz jednego wywołania API" na „między dwoma wywołaniami API tego samego runu").
- **Pełny komunikat błędu:** brak — wykryte analizą architektury, nie przez faktyczną awarię.
- **Prawdopodobna przyczyna:** dwuetapowy podział (ADR-016) rozwiązał ryzyko ucięcia JSON-a WEWNĄTRZ jednego wywołania, ale nie zaadresował trwałości stanu MIĘDZY etapami — brak było tabeli/mechanizmu do zapisania wyników etapu A do bazy przed przejściem do etapu B.
- **Sposób naprawy:** ADR-019 — nowe tabele `research_runs`/`research_sources`/`research_stage_results` (migracja `0004_research_resumability.sql`); `run_two_stage_research_pipeline` teraz zapisuje źródła ATOMOWO do bazy natychmiast po sukcesie etapu A (`mark_research_stage_a_success`, pojedynczy commit), zanim jeszcze sprawdzi próg minimalnej liczby źródeł; nowa funkcja `resume_research_stage_b()` pozwala wznowić WYŁĄCZNIE etap B z danych w bazie, bez ponownego (kosztownego) web search. Pokryte 10 testami w `tests/test_research_resumability.py`, w tym testem symulującym prawdziwy restart procesu (całkowicie nowe instancje `PolicyEngine`/`UsageTracker`/notifiera, jedyny łącznik ze starym stanem to `research_run_id` z bazy).
- **Liczba prób:** 1 (zaprojektowane i przetestowane od razu poprawnie na klientach zastępczych).
- **Czy może się powtórzyć:** nie dla scenariusza „awaria między etapem A i B" (teraz pokryte trwałym zapisem + testem). Ryzyko rezydualne: awaria W TRAKCIE zapisu do bazy (między `INSERT` źródeł a `UPDATE` statusu) — zminimalizowane przez wykonanie obu operacji w jednym commit/transakcji (`mark_research_stage_a_success`), więc SQLite gwarantuje atomowość (albo obie operacje się powiodą, albo żadna).
- **Wpływ na harmonogram / koszt:** 0.00 USD (naprawa proaktywna, offline, brak realnej straty — do żadnej faktycznej awarii między etapami nie doszło).
- **Status:** FIXED (zanim spowodowało realny incydent).

### [2026-07-12] Brakujący atrybut w pomocniczej klasie testowej (złapane przed uznaniem testów za zielone)
- **Kategoria:** TECH
- **Ryzyko z planu:** —
- **Konto / run_id:** —
- **Co miało działać:** `tests/test_research_resumability.py::test_resume_refuses_when_still_too_few_sources` używa pomocniczej klasy `_GatherForbiddenClient`, która powinna liczyć wywołania `synthesize_card`, żeby test mógł potwierdzić „zero wywołań API przy odmowie wznowienia".
- **Co się zepsuło:** klasa definiowała tylko nadpisanie `gather_sources` (rzucające `AssertionError`, jeśli w ogóle wywołane), ale nie miała atrybutu `synthesize_calls` ani nadpisania `synthesize_card` do jego zliczania.
- **Pełny komunikat błędu:** `AttributeError: '_GatherForbiddenClient' object has no attribute 'synthesize_calls'`
- **Prawdopodobna przyczyna:** klasa pomocnicza napisana pod kątem jednego zachowania (blokada `gather_sources`), a test sprawdzał drugie (licznik wywołań `synthesize_card`) — niedopatrzenie przy pisaniu fixture'a, nie błąd w kodzie produkcyjnym.
- **Sposób naprawy:** dodano `__init__` z `self.synthesize_calls = 0` oraz nadpisanie `synthesize_card`, które inkrementuje licznik przed delegacją do klasy bazowej.
- **Liczba prób:** 1 (naprawione od razu po pierwszym uruchomieniu testu).
- **Czy może się powtórzyć:** tak, przy kolejnych pomocniczych klasach testowych — mitygacja: uruchamianie pełnego `pytest` przed uznaniem podzadania za zamknięte (praktyka już stosowana).
- **Wpływ na harmonogram / koszt:** brak (błąd wyłącznie w kodzie testowym, wykryty i naprawiony przed jakimkolwiek realnym wywołaniem, 0 USD).
- **Status:** FIXED

### [2026-07-12 03:30 UTC] Drugi realny test — tym razem etap A (gather_sources) zwrócił ucięty JSON, nie etap B
- **Kategoria:** TECH
- **Ryzyko z planu:** R6 (pośrednio — bramka jakości/status poprawnie NIE utworzyła stanu wznawialnego dla niepełnych danych)
- **Konto / run_id:** nothing_is_accidental / `2a3b4bb9-772e-4340-808a-2bc61b28aacf`
- **Co miało działać:** drugie, jawnie zatwierdzone przez właściciela, realne wywołanie nowej (wznawialnej) architektury dwuetapowej dla tematu #2 (cap 0,45 USD) miało albo dokończyć pełną Research Card, albo — w razie awarii etapu B — pozwolić na czyste wznowienie etapu B.
- **Co się zepsuło:** awaria wystąpiła w **etapie A** (`gather_sources`), nie w etapie B: `Unterminated string starting at: line 39 column 9 (char 2763)`. To inny punkt awarii niż przy pierwszym incydencie (11.07, tam padł ówczesny jedyny/jednoetapowy krok przy ~8100 znaku) — tu ucięcie nastąpiło dużo wcześniej (znak 2763), mimo mniejszego, „lżejszego" schematu etapu A zaprojektowanego właśnie po to, żeby zredukować to ryzyko.
- **Pełny komunikat błędu:** `Niepoprawny JSON z modelu (gather_sources): Unterminated string starting at: line 39 column 9 (char 2763)`
- **Prawdopodobna przyczyna (niepotwierdzona ostatecznie):** `--gather-max-tokens` ma domyślną wartość **1200** — prawdopodobnie wciąż za nisko na pełny wynik 4 web searchy (adresy, tytuły, autorzy/organizacje, daty, typy źródeł, fakty per źródło). Nie mamy zapisanej surowej (nieudanej) odpowiedzi modelu do jednoznacznej weryfikacji tej hipotezy — do rozważenia: logowanie surowej odpowiedzi przy błędzie parsowania, wyłącznie do celów diagnostycznych, z uwagą na ewentualne dane wrażliwe w treści.
- **Sposób naprawy:** ŚWIADOMIE NIE WYKONANO w ramach tego zdarzenia — zgodnie z ustalonym trybem pracy (jeden realny test, zero automatycznych ponowień, zatrzymanie i raport). Ewentualne podniesienie `--gather-max-tokens` wymaga osobnej decyzji właściciela i osobno zatwierdzonej kolejnej próby.
- **Liczba prób:** 1 (dokładnie tyle, ile zatwierdzone; zero automatycznych retry — błąd parsowania JSON nie jest błędem technicznym w rozumieniu projektu, więc mechanizm retry poprawnie się nie uruchomił).
- **Czy może się powtórzyć:** tak, dopóki źródło ucięcia nie zostanie potwierdzone i zaadresowane. Ważna, POZYTYWNA różnica względem pierwszego incydentu: mechanizm ochrony wyników i kosztu zadziałał tym razem dokładnie tak, jak zaprojektowano — `research_runs.status=FAILED` (nie `PARTIAL`, poprawnie: etap A nie wyprodukował żadnych trwałych źródeł, więc nie ma czego oznaczać jako częściowe ani czego wznawiać), `research_sources` puste (zero wierszy, zgodnie z oczekiwaniem), a mimo to **realne zużycie (tokeny, web searche, koszt) zostało w pełni zachowane** w `runs.cost_usd` i `model_usage` — dokładnie ten mechanizm, który zawiódł przy pierwszym incydencie (11.07) i został wtedy naprawiony, potwierdził się teraz na żywo, w NOWEJ ścieżce kodu (etap A, nie stary pojedynczy research).
- **Wpływ na harmonogram / koszt:** **realny koszt: 0,123823 USD** — potwierdzony bezpośrednio w bazie (`model_usage`: input_tokens=75728, output_tokens=1619, web_search_requests=4/4). Znacząco NIŻSZY niż pesymistyczny szacunek etapu A (0,3615 USD) i szacunek łączny A+B (0,3817 USD) — w przeciwieństwie do pierwszego incydentu, tym razem estymator był bezpiecznie zawyżony, nie zaniżony. Łączny realny koszt eksperymentu do tej pory: **0,373823 USD** (0,93% budżetu miesięcznego 40 USD).
- **Status:** OPEN → **AKTUALIZACJA 2026-07-12 (ta sama sesja, później):** właściciel ocenił, że hipoteza „podnieś `--gather-max-tokens`" sama w sobie **nie jest wystarczającym rozwiązaniem** — trafna diagnoza: to wada STRUKTURALNA (jeden JSON obejmujący WSZYSTKIE źródła naraz, więc ucięcie w dowolnym miejscu kasuje wszystkie razem), nie wada jednego parametru. Podniesienie limitu tylko przesuwałoby próg ucięcia, nie usuwałoby przyczyny. Zamiast tego: pełna przebudowa etapu zbierania źródeł na A1 (discovery, tylko lista URL) + A2 (JEDNO źródło NA WYWOŁANIE, zapisywane do bazy natychmiast) — patrz `docs/DECISIONS.md` ADR-020. Dodatkowo zbudowano diagnostykę (`app/research/diagnostics.py`) zapisującą surową odpowiedź i `stop_reason` przy KAŻDYM realnym błędzie — przyszłe incydenty tego typu będą miały jednoznaczną, nie tylko domniemaną przyczynę. **Mechanizm architektoniczny: FIXED** (12 nowych testów, `tests/test_staged_research_extraction.py`). **Wciąż OPEN:** nowa architektura nie została jeszcze zweryfikowana na żywym API — plan małego testu w `IMPLEMENTATION_PLAN.md` CZĘŚĆ F.9, czeka na osobną zgodę.

### [2026-07-12] Pierwsza próba diagnostyczna A2 zatrzymana lokalnie przez niezgodność anthropic/httpx
- **Kategoria:** TECH
- **Ryzyko z planu:** R7 (pośrednio — diagnostyka kosztu i limitu A2)
- **Konto / run_id:** nothing_is_accidental / `9bbeb020-bf46-472f-b68c-3a9c6c85cabb`
- **Co miało działać:** pojedyncza, jawnie zatwierdzona diagnostyka oczekującego kandydata `id=3` z jednorazowym sufitem `max_tokens=5000` miała sprawdzić, ile miejsca potrzebuje poprawna odpowiedź A2. Kandydaci `id=1` i `id=2`, wcześniej oznaczeni `EXTRACTION_FAILED`, nie mieli być ponawiani (P1-5 pozostaje poza zakresem).
- **Co się zepsuło:** pierwsze podejście zakończyło się lokalnie podczas konstruowania klienta HTTP, zanim wysłano jakiekolwiek żądanie do Anthropic.
- **Pełny komunikat błędu:** `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`
- **Prawdopodobna przyczyna:** `anthropic==0.37.1` było niezgodne z `httpx==0.28.1`; stary SDK przekazywał usunięty w tej wersji httpx argument `proxies`.
- **Sposób naprawy:** w izolowanym `.venv` projektu podniesiono `anthropic` do **0.116.0**. Ta wersja spełnia istniejący wymóg `pyproject.toml`: `anthropic>=0.40`, więc wymogu nie zmieniano. `pip` zgłosił niezależne ostrzeżenie zgodności dotyczące `open-interpreter`, który wymaga `anthropic<0.38`; nie modyfikowano ani nie naprawiano `open-interpreter`, ponieważ nie należy do zakresu tego projektu/zadania. Końcowa lokalna weryfikacja środowiska projektowego: `anthropic==0.116.0`, `httpx==0.28.1`.
- **Liczba prób:** 2 łącznie: 1 zatrzymana lokalnie (zero requestów), następnie 1 udana diagnostyka API po poprawieniu SDK.
- **Czy może się powtórzyć:** nie w projektowym `.venv` z obecnymi wersjami; `pyproject.toml` nadal dopuszcza kompatybilne nowsze wydania `anthropic` zgodnie z istniejącą polityką zależności.
- **Wpływ na harmonogram / koszt:** pierwsze, lokalnie przerwane podejście wykonało **zero wywołań API i kosztowało 0,00 USD**. Następna diagnostyka API kosztowała osobno **0,028969 USD**.
- **Status:** FIXED w izolowanym środowisku projektu; konflikt pakietu `open-interpreter` świadomie poza zakresem.

### [2026-07-12] Diagnostyka A2 potwierdziła, że default 500 jest za niski; sufit 5000 był jednorazowy
- **Kategoria:** TECH | COST
- **Ryzyko z planu:** R6, R7
- **Konto / run_id:** nothing_is_accidental / `9bbeb020-bf46-472f-b68c-3a9c6c85cabb`, source candidate `id=3`
- **Co miało działać:** pojedyncza diagnostyka jednego niepróbowanego wcześniej kandydata miała oddzielić problem zbyt niskiego limitu odpowiedzi od problemu samego źródła, bez implementowania retry dla kandydatów 1 i 2.
- **Wynik:** odpowiedź zakończyła się poprawnie (`stop_reason=end_turn`), z `input_tokens=14 394`, `output_tokens=915`, `web_search_requests=1`, `verification_status=VERIFIED` i `source_quality_score=0.55`. To dowodzi, że stary produkcyjny limit 500 był niewystarczający dla realnej, poprawnej odpowiedzi A2 tego kandydata. **Nie dowodzi**, że kandydaci 1 i 2 potrzebowaliby dokładnie 915 tokenów — nie zostali ponowieni.
- **Decyzja:** `max_tokens=5000` było wyłącznie jednorazowym sufitem diagnostycznym. Produkcyjny default podniesiono z 500 do **1500**, zachowując jawny override CLI.
- **Koszt:** koszt samego wywołania diagnostycznego = **0,028969 USD**. Skumulowany koszt istniejącego runu po tym wywołaniu = **0,126793 USD** (`0,097824 + 0,028969`). Tych wartości nie wolno utożsamiać. Skumulowany realny koszt całego projektu po diagnostyce = **0,500616 USD**.
- **Estymacja:** conservative estimate **0,1256 USD** był bezpieczny, ale około **4,34× wyższy** od faktycznego kosztu tej jednej diagnostyki (0,028969 USD). Był celowo ostrożnym sufitem, nie trafną prognozą; nie opisujemy go jako „dokładnego".
- **Status:** FIXED dla domyślnego limitu A2 i podsumowania CLI; P1-5 (retry `EXTRACTION_FAILED`) nadal świadomie NIEZAIMPLEMENTOWANE.

### [2026-07-12] Pierwszy skan sekretów przed inicjalizacją Git użył metody niedostępnej w lokalnym PowerShellu
- **Kategoria:** TECH
- **Ryzyko z planu:** R1 (ochrona sekretów przed publikacją repozytorium)
- **Konto / run_id:** —
- **Co miało działać:** skan wszystkich tekstowych kandydatów do pierwszego commita miał raportować wyłącznie ścieżkę, numer linii i kategorię trafienia, nigdy wartość potencjalnego sekretu.
- **Co się zepsuło:** lokalny Windows PowerShell nie udostępniał `[System.IO.Path]::GetRelativePath`, więc pierwsza wersja skryptu generowała błędy dla ścieżek i jej końcowego wyniku `0` nie można było uznać za wiarygodny.
- **Pełny komunikat błędu:** `Method invocation failed because [System.IO.Path] does not contain a method named 'GetRelativePath'.`
- **Prawdopodobna przyczyna:** różnica wersji .NET/PowerShell względem środowiska, dla którego napisano pierwszą wersję jednorazowego skryptu audytowego.
- **Sposób naprawy:** ścieżki względne wyliczono bezpiecznie przez odjęcie prefiksu absolutnego katalogu projektu; skan powtórzono od zera. Poprawny przebieg objął 124 tekstowe pliki kandydackie i znalazł 12 trafień do ręcznej klasyfikacji — wszystkie były placeholderem w `.env.example` albo nazwami parametrów/zmiennych w kodzie. Zero prawdziwych sekretów i zero trafień formatów kluczy prywatnych/API.
- **Liczba prób:** 2.
- **Czy może się powtórzyć:** tak przy ponownym użyciu niekompatybilnej metody; naprawiona wersja nie zależy od `GetRelativePath`.
- **Wpływ na harmonogram / koszt:** kilka minut; 0 USD; żadna treść sekretu nie została wypisana ani wysłana.
- **Status:** FIXED przed stagingiem i przed jakimkolwiek push.

### [2026-07-12] Regex z alternacją został źle zacytowany w PowerShell podczas offline audytu A1/A2/B
- **Kategoria:** TECH
- **Ryzyko z planu:** —
- **Konto / run_id:** —
- **Co miało działać:** `rg` miał jednorazowo zindeksować funkcje, flagi bezpieczeństwa i testy związane z staged research.
- **Co się zepsuło:** podwójne cudzysłowy pozwoliły PowerShellowi potraktować znak `|` we fragmencie regexu `research_(discover|extract|...)` jako operator potoku/polecenie.
- **Pełny komunikat błędu:** `discover : The term 'discover' is not recognized as the name of a cmdlet...`
- **Prawdopodobna przyczyna:** quoting powłoki, nie błąd kodu projektu.
- **Sposób naprawy:** cały regex przekazano `rg` w pojedynczych cudzysłowach; powtórzone wyszukiwanie zakończyło się poprawnie.
- **Liczba prób:** 2.
- **Czy może się powtórzyć:** tak przy użyciu niebezpiecznego quoting w PowerShell; mitygacja: pojedyncze cudzysłowy dla regexów zawierających `|`.
- **Wpływ na harmonogram / koszt:** poniżej minuty, 0 USD, zero modyfikacji plików/bazy i zero wywołań API.
- **Status:** FIXED.
## 2026-07-12 — final verification pointed at the wrong SQLite filename

- **Expected:** perform a read-only confirmation that topic 2 still had the existing `FAILED` and `PARTIAL` research runs.
- **Failure:** the helper command opened `data/nothing_is_accidental.db` instead of configured `data/agent.db`; SQLite created an empty 0-byte file and the query failed with `no such table: research_runs`.
- **Cause:** the database filename was assumed instead of read from `app/core/config.py`.
- **Recovery:** removed only the newly created empty file, then repeated the read-only query against `data/agent.db`.
- **Result:** 2 runs remain unchanged (`FAILED`, `PARTIAL`); no status or application data was modified; no API call and no cost.
- **Prevention:** resolve `settings.db_path` or inspect configuration before diagnostic SQLite commands.

### [2026-07-12] Pomocniczy odczyt SQLite — quoting PowerShell i kodowanie konsoli

- **Kategoria:** TECH / narzędzie lokalne; kod aplikacji nie był wykonywany.
- **Co miało działać:** read-only inwentaryzacja historycznych runów i sygnałów potrzebnych do backfillu migracji 0006.
- **Co się zepsuło:** trzy warianty `python -c` zakończyły się `SyntaxError`, ponieważ PowerShell usunął lub rozbił cudzysłowy zagnieżdżonego SQL. Po przejściu na skrypt podawany przez stdin pierwszy odczyt zatrzymał się na `UnicodeEncodeError` konsoli cp1252 przy polskim tekście błędu.
- **Przyczyna:** cytowanie wielowarstwowe PowerShell→Python→SQL oraz domyślne kodowanie konsoli, nie dane ani aplikacja.
- **Naprawa:** kod przekazano przez PowerShell here-string do stdin Pythona i ustawiono `sys.stdout.reconfigure(encoding='utf-8')`.
- **Wynik:** pełny odczyt zakończony poprawnie; potem migracja przeszła na pamięciowej kopii bazy. Źródłowy `data/agent.db` pozostał niezmieniony.
- **Liczba prób:** 5 łącznie (3 błędy cytowania, 1 błąd kodowania, 1 sukces).
- **Koszt / skutki:** 0 USD, zero API, zero nowych rekordów i zero zmian statusów.
- **Zapobieganie:** przy dłuższym SQL na Windows używać stdin/here-string i jawnego UTF-8 zamiast wielokrotnie zagnieżdżonego `python -c`.

### [2026-07-12] Etap 0 / zadanie 1 — błędy wykryte w review przed commitem

- **Kategoria:** IMPLEMENTATION / MIGRATION / SAFETY; wykryte przed wdrożeniem i przed commitem.
- **Co było błędne:** pierwszy wariant backfillu single dopuszczał prefiks UUID, `current_state` i czasowe dopasowanie karty; refaktor CLI usunął wcześniejszą walidację dozwolonych statusów resume; roadmapa błędnie nazywała przebudowę tabeli migracją addytywną z rollbackiem przez sam powrót do starego commita.
- **Scenariusz ryzyka:** obca instalacja lub niejednoznaczna historia mogła dostać błędny flow/kartę; `--estimate-only` albo realne resume mogło wejść w helper dla terminalnego `FAILED`/`COMPLETE`; stary kod po 0006 próbowałby insertu bez obowiązkowego `flow`.
- **Naprawa:** dokładna mapa pełny UUID+konto+topic(+karta), wyłącznie strukturalne sygnały dla two-stage/staged, walidacja flow→status przed jakąkolwiek pracą CLI oraz poprawiona procedura rollbacku.
- **Dowód:** 70 testów celowanych i 127 pełnych; testy black-box potwierdzają zero wywołań helperów/klienta po odmowie, a migracyjne obejmują brak znanych UUID, konflikt, czystą/pustą bazę oraz integralność schematu.
- **Wpływ / koszt:** brak wpływu na dane produkcyjne — migracja nie została zastosowana do źródłowej bazy; 0 USD, zero API, Playwrighta i researchu.
- **Status:** FIXED; oczekuje na drugi review właściciela.

### [2026-07-12] Etap 0 / zadanie 2 — nieatomowy zapis usage i cache'a kosztu wykryty przez review

- **Kategoria:** COST / TECH
- **Ryzyko z planu:** P1-2 (spójność księgi runów)
- **Konto / run_id:** — (odtworzone wyłącznie na tymczasowej, plikowej bazie SQLite)
- **Co miało działać:** po każdym trwałym zapisie researchowego `model_usage`, `runs.cost_usd` ma wskazywać dokładnie tę samą kanoniczną sumę, także po restarcie procesu.
- **Co się zepsuło:** `add_model_usage()` zatwierdzał INSERT osobnym commitem, a pipeline wywoływał synchronizację cache'a dopiero później. Diagnostyka odtworzyła stan po przerwaniu między krokami: `persisted_usage=0.123456`, `persisted_run_cache=0.000000`.
- **Prawdopodobna przyczyna:** granica transakcji była w warstwie `UsageTracker`/repozytorium przed późniejszym helperem pipeline'u, więc `finally` chronił zwykłe wyjątki po zapisie usage, ale nie awarię procesu ani błąd samego późniejszego UPDATE.
- **Sposób naprawy:** dla tasków researchowych `SqliteStorage.add_model_usage()` wykonuje teraz jednym `BEGIN`/commit: INSERT `model_usage`, kanoniczną sumę wpisów researchu po `run_id` oraz absolutny UPDATE `runs.cost_usd`. Wyjątek podczas UPDATE wycofuje INSERT i cache; `sync_run_cost_from_research_usage()` pozostaje osobną, idempotentną naprawą no-call/resume.
- **Dowód regresji:** test na plikowej bazie potwierdza zgodność po reopen; trigger SQLite wymusza błąd między INSERT i UPDATE, po reopen nie ma nowego usage ani częściowej zmiany cache'a. Dodatkowe testy obejmują zero usage, dry-run, kilka wpisów, A1/B error bez usage i wielokrotny no-call resume.
- **Liczba prób:** 1 diagnostyka lokalna + poprawka offline; zero wywołań API.
- **Czy może się powtórzyć:** nie dla tej granicy INSERT research usage → cache, ponieważ oba zapisy są atomowe i pokryte testem rollbacku. Pozostaje znane, nieusuwalne ryzyko timeoutu zafakturowanego bez lokalnego `usage`.
- **Wpływ na harmonogram / koszt:** 0 USD; nie zmodyfikowano bazy projektu ani żadnego realnego runu.
- **Status:** FIXED; oczekuje na drugi review przed commitem.

### [2026-07-12] Test migracji po dodaniu 0007 zakładał nieaktualną listę wersji
- **Kategoria:** TEST / IMPLEMENTATION; nie dotyczyło kodu produkcyjnego ani danych.
- **Co się zepsuło:** pierwszy celowany przebieg po dodaniu migracji 0007 miał 5 czerwonych asercji w `tests/test_research_run_flow.py`: testy 0006 oczekiwały dokładnie `['0006_research_run_flow']`, podczas gdy mechanizm migracji poprawnie zastosował także `0007_candidate_attempts`.
- **Przyczyna:** testy sprawdzały kompletną listę migracji po schemacie 0005, lecz nie zostały jeszcze rozszerzone o kolejną addytywną wersję.
- **Naprawa:** zaktualizowano oczekiwane listy oraz dodano osobny test 0007 dla kolumny/defaultu danych historycznych i obu pragma integrity.
- **Liczba prób / wpływ:** 1 wykrycie offline; po poprawce 76 testów celowanych i 153 pełne zielone. Zero API, zmian źródłowej bazy i kosztu.
- **Status:** FIXED.

### [2026-07-12] Review Task 3 wykrył, że licznik próby nie wystarcza bez claimu i ledgeru atomowego
- **Kategoria:** IMPLEMENTATION / MIGRATION / SAFETY; odtworzone wyłącznie offline na SQLite.
- **Co się zepsuło:** historyczny `EXTRACTION_FAILED` z `attempts=0` dostawał dwa nowe retry przy capie 2; `PENDING` już na capie można było inkrementować dalej; crash po inkremencie nie odróżniał niepewnego calla od nieprzetworzonego kandydata. Osobno `COMMIT` migracji następował przed wpisem wersji, więc błąd ledgeru pozostawiał zmieniony schema bez rejestru.
- **Reprodukcje:** review odtworzył co najmniej trzy faktyczne calle dla historycznego failed przy capie 2, increment `2 → 3`, odmowę higher-cap dla `PARTIAL_EXHAUSTED` oraz `duplicate column` po braku wpisu ledgeru.
- **Naprawa:** lower-bound backfill 0/1, atomowy claim do `EXTRACTION_IN_PROGRESS`, odmowa zwykłego resume dla niepewnego wyniku, jawne higher-cap reopen, warunki przejść statusu, izolacja konta i jedna transakcja runnera dla 0007+ledgeru.
- **Dowód:** 87 testów celowanych i **164** pełne; test triggera potwierdza rollback kolumny oraz ledgeru razem. Zero API, bazy źródłowej i kosztu.
- **Status:** FIXED; oczekuje na drugie review przed commitem.

### [2026-07-12] P2 po drugim review Task 3 — ujemne attempts może ominąć cap
- **Kategoria:** DATA INTEGRITY / DEFENSE IN DEPTH; normalny kod nie tworzy wartości ujemnych.
- **Scenariusz:** ręcznie uszkodzony `PENDING_EXTRACTION` z `attempts=-1` przy capie 2 spełnia `attempts < cap`; claim przechodzi i zapisuje `attempts=0`, umożliwiając więcej rezerwacji niż deklarowany cap.
- **Wpływ:** brak na poprawne dane po migracji 0007 i normalne ścieżki zapisu; ryzyko dotyczy uszkodzonego lub ręcznie zmienionego rekordu.
- **Docelowa poprawka:** `attempts >= 0` w warunku claimu, `Field(ge=0)`, test regresyjny i ewentualnie CHECK constraint w kolejnej migracji.
- **Status:** OPEN / P2; świadomie niepoprawiane przed commitem Task 3 zgodnie z decyzją właściciela.

### [2026-07-12] Zapobieżony koszt: COMPLETE nie może wyglądać jak kandydat do zwykłego retry — [SAFETY]
- **Ryzyko przed Task 4:** `TopicStatus.USED` istniał, ale nie był ustawiany. Temat z kompletną kartą mógł wejść w drugi świeży flow bez świadomego potwierdzenia kosztu.
- **Zabezpieczenie:** transakcyjne `COMPLETE → USED` oraz bramka po `research_runs.status=COMPLETE` i istniejącej karcie; w CLI odmowa następuje przed konstrukcją klienta API.
- **Weryfikacja:** test zakazuje konstrukcji klienta dla kompletnej karty, a pełna regresja kończy się `169 passed`.
- **Wynik:** nie było wywołania API, kosztu ani zmiany bazy źródłowej. Jawny `--force-re-research` pozostaje jedyną drogą nowej, potencjalnie płatnej próby.

### [2026-07-12] Review Task 4: atomowość dwóch statusów nie wystarczyła — [SAFETY]
- **Co wykryto:** karta innego tematu mogła zostać przypięta do COMPLETE, a błąd ustawienia USED pozostawiał wcześniej zatwierdzony `runs.SUCCESS` i osieroconą kartę.
- **Naprawa:** jedna transakcja finalizacji waliduje card-topic-account i obejmuje COMPLETE, terminalny run oraz USED; trigger SQLite i reopen potwierdzają rollback każdego końcowego UPDATE.
- **Dodatkowa ochrona:** uszkodzony COMPLETE lub USED bez poprawnej karty jest błędem integralności fail-closed. Standardowy runner sprawdza guard przed konstrukcją klienta.
- **Ryzyko odłożone (P2-17):** dwa równoległe świeże procesy nadal wymagają przyszłego claimu/lease per temat.
- **Wynik:** **186 passed**, 0 USD, zero API i brak zmiany bazy źródłowej.

### [2026-07-12] Drugie review Task 4: atomowość nie zapewnia idempotencji — [SAFETY]

- **Co wykryto:** ponowne wywołanie poprawnie atomowej finalizacji nadal wykonywało bezwarunkowe UPDATE. Reprodukcja przepięła `research_card_id` 1→2 i zmieniła koszt 0,1→0,9 USD, niszcząc audytowalność ukończonego runu.
- **Dlaczego:** transakcja gwarantowała „wszystko albo nic” dla jednego wykonania, lecz nie porównywała nowego żądania z już utrwalonym COMPLETE.
- **Naprawa:** identyczny COMPLETE jest no-op bez UPDATE; sprzeczny payload i częściowo uszkodzony COMPLETE są odrzucane. Pierwsza finalizacja ma dozwolone stany wejściowe, jawny status terminalny, warunkowe UPDATE i kontrolę `rowcount`.
- **Braki testów wykryte przez review:** SELECTED+COMPLETE, mieszana historia runów, force wobec korupcji i złego konta, błędny forced run oraz pełna macierz refinalizacji. Wszystkie dodano dla właściwych wejść runnera/CLI i trzech flow.
- **Nieudana iteracja lokalna:** pierwszy zbyt wąski guard statusu `runs` odrzucił legalne jawne wznowienie legacy Stage B ze stanu FAILED; doprecyzowano wyłącznie dozwolone przejście TWO_STAGE po zachowaniu źródeł. Był to błąd testowy/implementacyjny offline, bez API i kosztu.
- **Wynik:** **206 passed**, 0 USD, zero API; P2-17 pozostaje świadomie otwarte.

### [2026-07-12] Trzecie review Task 4: kod obsługiwał przypadki, lecz brakowało dowodów regresyjnych — [TEST]

- **Co wykryto:** implementacja prawidłowo odrzucała konflikt Stage B, błędny timestamp flow i kartę obcego topicu/konta, ale testy nie wywoływały tych przypadków wprost. Testy account mismatch sprawdzały tylko licznik `runs`, nie cały wymagany zestaw tabel.
- **Naprawa:** dodano sześć trwałych regresji z reopen SQLite oraz pełne liczniki `runs`, `research_runs`, `model_usage`, `research_cards` w runnerze i capped CLI. Kod produkcyjny nie wymagał zmiany.
- **Wynik:** **212 passed**, 0 USD i zero API. Różnica „kod zachowuje się poprawnie” vs „test dowodzi kontraktu” pozostaje materiałem do artykułu.

### [2026-07-12] P2-18 — dokładne porównanie kosztów float w idempotentnym no-op

- **Finding:** `finalize_research_success()` porównuje utrwalone koszty z payloadem przez dokładne `float == float`; `0.1 + 0.2` może różnić się binarnie od `0.3`.
- **Wpływ:** bezpieczna fałszywa odmowa i rollback; brak ryzyka przepisania karty, kosztu lub timestampów.
- **Docelowy kierunek:** najmniejsza jednostka pieniężna, `Decimal` albo jawna tolerancja zgodna z kanoniczną sumą `model_usage`.
- **Status:** OPEN / P2; świadomie niezmieniane w Task 4. P2-17 pozostaje osobno otwarte.

### [2026-07-12] Task 5 — timeout-billed-unrecorded — [COST]

- **Ryzyko rezydualne:** provider może naliczyć koszt, mimo że lokalny timeout nastąpił przed otrzymaniem odpowiedzi zawierającej usage.
- **Skutek:** brak wiarygodnych danych do `model_usage`; lokalny budżet może chwilowo zaniżać rzeczywiste rozliczenie. System nie zapisuje sztucznego usage i nie udaje, że zna koszt.
- **Mitygacje:** niskie `max_retries`; worst-case `base × (1 + max_retries)`; świeży re-check z `model_usage` przed każdą próbą; niski cap per-run. Późniejsza rekonsyliacja z billingiem providera pozostaje poza Task 5.
- **Testowany przypadek sąsiedni:** jeśli timeout niesie usage, jest ono zapisywane przed re-checkiem retry; odmowa daje dokładnie jeden call i zachowuje pierwszy wpis.
- **Koszt zadania:** 0 USD; wyłącznie fake callery, zero API.

### [2026-07-12] Review Task 5: cap nie był jeszcze kontraktem fail-closed — [SAFETY | COST]

- **Co wykryto:** `run_cap_usd=None` wyłączało cap realnego pipeline; resume dodawało nowy allowance do już wydanego kosztu; ownership konta sprawdzano po odczycie usage; NaN/Infinity limitów przechodziły jako `OK`.
- **Wpływ:** wspierany CLI przekazywał cap, ale kontrakt biblioteczny i wielokrotne resume nie gwarantowały stałej granicy całego runu.
- **Naprawa:** brak capu realnego researchu jest błędem przed callem; cap resume jest absolutny; account guard poprzedza koszt/klienta; uszkodzony stan budżetu odmawia.
- **Regresje:** A1/A2/B utrwalają usage timeoutu i blokują attempt 2; B wraca do `SOURCES_COMPLETE`; obce konto nie synchronizuje kosztu ani nie tworzy klienta.
- **Status:** FIXED offline; `timeout-billed-unrecorded` pozostaje rezydualnym P2, nie jest uznane za rozwiązane.

### [2026-07-12] Task 6 — koszt odpowiedzi tematów znikał po parse-error — [COST | DATA]

- **Co było nie tak:** klient tematów wykonywał `json.loads(text)` przed zbudowaniem `Usage`. Poprawnie zbilowana odpowiedź z uciętym lub wadliwym JSON-em przerywała funkcję, zanim usage mogło dotrzeć do workflow; run pozostawał bez kontrolowanej ścieżki `FAILED`.
- **Różnica błędów:** provider error przed odpowiedzią nie ma usage i nie wolno wymyślać kosztu. Parse/schema error po odpowiedzi ma już rzeczywiste usage i model, więc ich utrata byłaby fałszywą księgowością.
- **Naprawa:** response → `Usage` → text → parse; typowane provider/parse/schema errors; jeden ścisły zewnętrzny code fence; workflow zapisuje usage raz, ustawia `FAILED` i nie zapisuje topics.
- **Dlaczego bez retry:** wadliwy format odpowiedzi nie jest błędem transient. Automatyczne powtórzenie mogłoby zapłacić drugi raz bez usunięcia przyczyny.
- **Nieudana wersja podczas pracy:** pierwsza poprawka wciąż składała tekst przed `Usage`. Self-review sklasyfikował to jako P1 względem literalnego kontraktu i odwrócił kolejność przed finalną weryfikacją.
- **Dowód:** 35 testów topics i 286 całego suite, wyłącznie fake caller/fake SDK oraz SQLite; 0 USD, zero API.

### [2026-07-12] Task 8 — pierwsza macierz lifecycle odrzuciła legalne resume — [IMPLEMENTATION | TEST]

- **Co się zepsuło:** pierwszy celowany suite miał 4 failures. Staged A2 z `max_sources=0` legalnie zapisywał `DISCOVERY_COMPLETE→PARTIAL`, a kolejne jawne próby resume aktualizowały wynik tego samego ogólnego runu `FAILED→FAILED`; początkowa macierz obu kontraktów nie uwzględniła.
- **Dlaczego:** statusy są rozdzielone na ogólny audit `runs` i szczegółowy `research_runs`. Odczyt samego diagramu bez wszystkich callerów nie ujawnił, że resume zachowuje ten sam `run_id` i może zakończyć się kolejnym błędem bez cofania researchu do początku.
- **Naprawa:** staged PARTIAL dopuszcza `DISCOVERY_COMPLETE`, `EXTRACTION_IN_PROGRESS` i `PARTIAL`. `finish_run` dopuszcza FAILED→FAILED wyłącznie jako zapis następnej jawnej próby; identyczne powtórzenie jest no-op, a FAILED→SUCCESS i każdy inny konflikt terminali nadal są odrzucane.
- **Dowód:** 44 testy Task 8, 96 celowanych i 330 pełnych; race różnych terminali oraz konkurencyjnego resume ma dokładnie jeden statusowy UPDATE. Wszystko offline, bez API i kosztu.
- **Status:** FIXED przed niezależnym review.
- **Drobna nieudana próba testowa:** pierwszy trigger audytowy użył w body składni `INSERT ... DEFAULT VALUES`, której SQLite nie przyjął w tym kontekście. Zastąpiono ją równoważnym `VALUES (NULL)`; błąd nie dotyczył kodu produkcyjnego ani danych.

### [2026-07-13] Review Task 8: ogólny FAILED był przepisywalny, a test claimu nie był race — [AUDIT | TEST]

- **P1-1:** wyjątek FAILED→FAILED znajdował się w ogólnym `finish_run`, więc również niereseachowy terminalny run mógł zmienić koszt, błąd i timestamp. Oddzielono zwykłą finalizację od jawnego resume z pełną walidacją relacji oraz CAS.
- **P1-2:** dwa połączenia SQLite były użyte kolejno, nie równolegle. Test nie dowodził zachowania przy jednoczesnym snapshotcie PENDING. Zastąpił go deterministyczny `Barrier` i dwa wątki.
- **Nieudana pierwsza korekta race resume:** `BEGIN` przed SELECT tworzył upgrade-lock race i faktyczny `database is locked`. Diagnostyczny SELECT jest teraz poza transakcją zapisu, natomiast UPDATE ponownie sprawdza cały kontrakt oraz token CAS. Test nie łapie OperationalError — lock pozostaje porażką.
- **Wynik:** 337 testów, w tym oba race powtórzone 10 razy; 0 USD i brak API.
- **Status:** FIXED; oczekuje na krótkie końcowe review.

### [2026-07-13] Task 9: realne B wyczerpało max_tokens i zwróciło ucięty JSON — [LIVE API | PARSE | COST]

- **Run:** `c01171bc-7ff5-4b83-bbfa-c0b164137793`, flow staged, topic #2.
- **Co zadziałało:** A1 odkrył 4 kandydatów; wszystkie cztery A2 zakończyły się `end_turn`, EXTRACTED i VERIFIED. Każdy candidate miał `attempts=1`; zero retry.
- **Co się zepsuło:** B osiągnęło dokładnie 2200 output tokens i `stop_reason=max_tokens`. JSON urwał się wewnątrz stringa (`Unterminated string`, char 4224), więc parser poprawnie odmówił utworzenia karty. Nie jest to timeout ani błąd transient; automatyczny retry był zabroniony i nie nastąpił.
- **Koszt:** 0,170050 USD = A1 0,029243 + A2 0,127903 + B 0,012904. Całość jest w `model_usage`, `runs.cost_usd` jest zgodne; cap 0,55 USD zachowany.
- **Stan odzyskiwalny:** `research_runs=SOURCES_COMPLETE`, 4 VERIFIED, brak karty, temat SELECTED. Technicznie możliwe jest wyłącznie jawne resume B, ale wymaga nowej zgody i nie zostało wykonane.
- **Diagnostyka:** prywatny `B_raw_response.txt` potwierdza `max_tokens`, 1904 input, 2200 output, 0 search i długość 4489 znaków. Surowa treść nie jest kopiowana do repo.
- **Status:** OPEN; Task 9 i Etap 0 nieukończone.

### [2026-07-13] Task 9: proces zakończył się, ale ogólny run pozostał RUNNING — [LIFECYCLE | AUDIT]

- **Obserwacja:** po obsłużonym błędzie B CLI zakończyło pojedynczy run, lecz `runs.status=RUNNING`, `finished_at=NULL`, `error=NULL`; jedynie cache kosztu wynosi 0,170050 USD. Szczegółowy `research_runs` poprawnie wrócił do wznawialnego `SOURCES_COMPLETE` z opisem błędu.
- **Przyczyna w odczytanym kodzie:** ścieżka błędu świeżego `run_synthesis_from_cards` wywołuje `revert_to_sources_complete`, ale terminalizuje ogólny audit tylko wtedy, gdy istnieje snapshot jawnego resume.
- **Wpływ:** kanoniczne `model_usage` i `runs.cost_usd` są spójne, a źródła trwałe, lecz ogólny audit fałszywie sugeruje aktywny proces. `research_runs.total_cost_usd` pozostało 0,0 — to potwierdzenie znanego P2-2 (niekanoniczny cache), nie utrata usage. Stan wymaga niezależnego review przed kolejnym krokiem.
- **Działanie:** zgodnie z Task 9 nie zmieniono kodu, statusu ani bazy ręcznie; nie wykonano resume. Klasyfikacja ważności i ewentualna poprawka należą do osobnego review.

### 2026-07-13 — P1-1/P1-2 naprawione offline dla przyszłych wykonań; historyczny run bez mutacji

- **P1-1 przyczyna:** limit B=2200 pochodził z domyślnej wartości klienta/pipeline/CLI. Estymator przyjmował przekazany limit poprawnie, ale sam limit okazał się zbyt niski dla realnego schematu; klient próbował parsować odpowiedź mimo jednoznacznego `stop_reason=max_tokens`.
- **P1-1 poprawka:** jeden kanoniczny default 3000, jawny override CLI, zwięzłe limity pól promptu i `ResearchTruncatedError` przed JSON parse. Usage/raw/stop_reason zostają zachowane, bez auto-retry i częściowej karty. B=0,026250 USD conservative; fresh=0,516375 USD; resume z prior=0,196300 USD.
- **P1-2 przyczyna:** fresh ścieżka błędu wywoływała `revert_to_sources_complete`, lecz terminalizowała `runs` tylko dla explicit resume snapshot.
- **P1-2 poprawka:** fresh B failure wywołuje warunkowe `finish_run(...FAILED...)`; explicit resume zachowuje `finish_resumed_research_run` z CAS. Reopen SQLite potwierdza `FAILED`, `finished_at`, przyczynę, brak karty i nienaruszone `SOURCES_COMPLETE`.
- **Stan historyczny:** poprawka nie działa wstecz. `c01171bc` nadal ma RUNNING/NULL; nie wykonano raw SQL, repair ani resume. P2-2 pozostaje świadomym cache (`model_usage` jest kanonem), a P2-17/P2-18/P2-19 są poza zakresem.
- **Plan repair (NIEWYKONANY):** osobna, reviewowana komenda maintenance ma otworzyć repozytorium i w jednej kontrolowanej operacji lifecycle wywołać istniejące `finish_run(..., FAILED, 0.170050, error=...)`; nie jest potrzebna nowa migracja ani surowy SQL. Przed mutacją musi atomowo/tuż przed CAS potwierdzić dokładny run ID, konto i workflow RESEARCH, `runs=RUNNING/finished_at=NULL/error=NULL/cost_usd=0.170050`, `research_runs=staged/SOURCES_COMPLETE/card=NULL/topic=2`, topic SELECTED, 4 kandydatów EXTRACTED+VERIFIED, brak karty, 6 rekordów `model_usage` sumujących się do 0.170050 oraz ostatni Stage B FAILED z `stop_reason=max_tokens`; jakakolwiek rozbieżność = fail-closed.
- **Skutek repair:** zmienia wyłącznie audit `runs` na FAILED, ustawia `finished_at` i zachowuje pełną przyczynę `[synthesize_from_cards] ... stop_reason=max_tokens`; nie zmienia `model_usage`, `runs.cost_usd`, `research_runs.status`, `research_runs.total_cost_usd`, kandydatów, topic ani kart. Po operacji należy zapisać jawny log maintenance z preconditions/wynikiem, ponownie otworzyć SQLite, sprawdzić wszystkie inwarianty i dopiero w osobnym kroku prosić o zgodę na płatny resume B.

### 2026-07-13 — historyczny nieterminalny audit naprawiony kontrolowanym maintenance

- **Status:** FIXED dla runu `c01171bc-7ff5-4b83-bbfa-c0b164137793`; nie wykonano resume.
- **Dowód bezpieczeństwa:** backup i logiczny snapshot przed zmianą; wszystkie opisane wyżej preconditions ponownie sprawdzone wewnątrz `BEGIN IMMEDIATE`; brak triggerów na `runs`; warunkowy UPDATE wymagał właściwego ID, konta, workflow RESEARCH, statusu RUNNING, `finished_at/error IS NULL` i kosztu 0,170050. `rowcount=1`, `total_changes=1`; każda niezgodność powodowałaby rollback.
- **Zmiana:** wyłącznie `runs.status=FAILED`, `finished_at=2026-07-13 05:39:30 UTC` oraz pełny maintenance error z etapem `synthesize_from_cards`, `stop_reason=max_tokens` i wcześniejszym `ResearchParseError/truncated JSON`.
- **Niezmienione po reopen:** `runs.cost_usd=0,170050`; sześć `model_usage` o sumie 0,170050; `research_runs=SOURCES_COMPLETE`, `research_card_id=NULL`; topic #2 SELECTED; 4×EXTRACTED/VERIFIED/attempts=1; stage timestamps/log, account, karty i źródła. `integrity_check=ok`.
- **Granica:** naprawiono prawdziwość auditu, nie wynik researchu. Etap 0 nadal nieukończony, a resume wyłącznie B pozostaje osobnym potencjalnie płatnym działaniem wymagającym jawnej zgody.

### 2026-07-13 — resume B zakończone technicznie, karta odrzucona jakościowo

- **Call:** jedyne zatwierdzone B zakończyło się poprawnie (`stop_reason=end_turn`, 1904/2402 tokenów, 0 search, 0,013914 USD); nie wystąpił błąd providera ani parsera i nie wykonano retry.
- **Bramka jakości:** karta #2 otrzymała `publication_recommendation=REJECT` z powodami `THESIS_UNSUPPORTED` i `CLAIMS_WITHOUT_SOURCES`. To poprawna odmowa użycia materiału do treści, nie awaria lifecycle; COMPLETE/SUCCESS/USED i kryterium Etapu 0 pozostają spełnione.
- **P2-20:** `research_runs.error` po COMPLETE nadal zawiera parse-error pierwszego, nieudanego B. Pełna historia prób istnieje w `research_stage_results` (B FAILED, potem B SUCCESS), więc utrzymanie starego tekstu w polu bieżącego stanu może mylić konsumentów. Nie zmieniono kodu ani bazy; finding czeka na niezależne review.
- **Koszt:** run łącznie 0,183964 USD ≤ 0,20; dodatkowy B 0,013914 USD. Brak drugiego calla.

### 2026-07-13 — wszystkie błędy SDK Anthropic udawały timeout — [P1 | RETRY | COST]

- **Problem:** `_call_anthropic` przechwytywał każde `Exception` z `messages.create` i rzucał `ResearchTimeout`. Stałe odmowy 400/401/403/404/422 mogły więc zostać potraktowane jak transient i uruchomić kolejny potencjalnie płatny call.
- **Naprawa:** wyjątki SDK są mapowane na typy domenowe; retry jest jawnie dozwolone wyłącznie dla timeout, SDK-network, 429 i 500/502/503/504. Unknown i pozostałe statusy są terminalne dla próby. Parse, truncation, validation i budget error pozostają poza retry.
- **Regresja kosztowa:** każda kolejna próba przechodzi świeży callback budżetowy. Jeśli błąd niesie prawdziwe usage, zapis następuje raz przed retry; jeśli SDK go nie zwraca, system nie zapisuje fikcyjnego 0 USD.
- **Ryzyko rezydualne:** P2-19 pozostaje OPEN — timeout może być zbilowany bez lokalnego usage. Ten task nie dodaje rekonsyliacji billingowej ani rezerwacji globalnej.
- **Weryfikacja:** 382 testy offline, bez API i dodatkowego kosztu.

### 2026-07-13 — typed provider error tracił klasę w polach auditu — [P1 | AUDIT]

- **Objaw:** `ResearchInvalidRequestError(status_code=422, retryable=False)` kończył run poprawnie i księgował usage, lecz `runs.error`/`research_runs.error` zawierały tylko etap i komunikat.
- **Przyczyna:** każda ścieżka persystencji budowała własne `f"[stage] {exc}"` albo `str(exc)`.
- **Naprawa:** jeden bounded/redacting formatter dla run, research_run, stage i candidate audit. Nie zapisuje raw response, cause, request/response ani headers; zachowuje bezpieczne skalarne metadane.
- **Dowód:** plikowa SQLite po reopen: 422 = jeden call/jeden usage/FAILED/SELECTED/zero kart; 429 po wyczerpaniu = dwa calle/dwa usage bez dubla; `runs.cost_usd == sum(model_usage)`. Pełne **406 passed**, 0 USD, brak API.

### 2026-07-13 — dwa P1 po review: body SDK i nagi Bearer mogły wejść do auditu — [P1 | SECURITY]

- **Przyczyna:** `str(APIStatusError)` SDK Anthropic 0.116.0 zawiera body odpowiedzi; dodatkowo regex traktował `Bearer` jako sekret tylko przy poprzedzającej nazwie nagłówka.
- **Naprawa:** mapper nie używa już tekstu SDK dla komunikatu domenowego, lecz kontrolowanego statusu/klasy. Formatter redaguje każdy case-insensitive `Bearer <token>`.
- **Dowód:** marker body nie występuje w błędzie domenowym ani w `runs.error`, `research_runs.error`, stage/candidate audit; typ, `status_code`, `retryable` i `__cause__` pozostają. Testy offline: **411 passed**, koszt 0 USD, bez API.

### 2026-07-13 — F4: crash po B mógł zapisać kartę bez sukcesu lifecycle — [P1 | DURABILITY]

- **Scenariusz:** B commitował `research_cards` i `sources` przed wpisem B SUCCESS oraz finalizacją `research_runs`, `runs` i `topics`. Przerwanie tworzyło kartę bez COMPLETE/SUCCESS/USED.
- **Naprawa:** atomowy helper staged B, `BEGIN IMMEDIATE`, walidacja pełnego kontraktu i rollback całego zestawu. Testowane są crash points: karta, drugie źródło, audit B i lifecycle; po każdym zostaje poprzedni `SYNTHESIS_PENDING`.
- **Lekcja:** atomowość finalnego statusu nie wystarcza, gdy artefakt wyniku jest wcześniej zapisywany. Dane i ich semantyczne zatwierdzenie muszą upaść razem albo przetrwać razem.
- **Status:** naprawione offline; 420 passed, 0 USD, brak API. P2-17, P2-18 i P2-19 poza zakresem.

### 2026-07-13 — F4 po review: booleany nie są autoryzacją lifecycle — [P1 | DURABILITY]

- **Co nie działało:** caller mógł przekazać `allow_prior_complete_card` albo `allow_failed_run` i ominąć część preconditions. Force nie był utrwalony, więc po B failure dispatcher resume nie znał legalnego trybu. Macierz awarii obejmowała zbyt mało miejsc i nie zawsze sprawdzała bazę po reopen.
- **Jak naprawiono:** jeden typowany context i cztery tryby finalizacji; `0008` z trwałym markerem force per run; CAS resume (`FAILED`, `finished_at`, marker błędu, `SOURCES_COMPLETE`, B FAILED); fail-closed preflight przed B. Każdy z 13 punktów awarii po reopen pozostawia pre-finalization state.
- **Dodatkowa granica:** genericzny wpis stage nie może utworzyć staged `B SUCCESS`; jedynym writerem sukcesu jest helper transakcyjny. Brak UNIQUE dla staged B/card sources pozostaje udokumentowanym P2 dla jednego procesu SQLite z `BEGIN IMMEDIATE`, nie otwartą ścieżką biznesową.
- **Dowód:** force→failure→resume po osobnym połączeniu SQLite, odmowa przed providerem/usage dla błędnego markera lub timestampu CAS, account/topic/flow/status/VERIFIED, conflicts, no-op i concurrency jednego oraz dwóch runów. **446 passed**, bez API i 0 USD.

### 2026-07-13 — F4 końcowe review: COMPLETE akceptował sprzeczny execution mode — [P1 | DURABILITY]

- **Scenariusz:** zwykły FRESH run mógł powtórzyć identyczny payload jako `FORCE_RERESEARCH`; karta, źródła i koszt były zgodne, więc no-op wracał zanim sprawdzono mode.
- **Naprawa:** COMPLETE najpierw waliduje marker force i semantykę fresh/resume. Resume porównuje też trwały B FAILED z tym samym markerem i `finished_at` CAS; timestamp porażki B jest zapisywany z `runs.finished_at`.
- **Dowód:** konflikty fresh↔force, fresh→resume, force→force-resume bez historii oraz dwa CAS mismatch po reopen nie zmieniają żadnego rekordu, kosztu ani timestampu. **449 passed**, 0 USD, bez API.

### 2026-07-13 — F4 P1: publiczny legacy finalizer nadal otwierał staged sukces — [P1 | DURABILITY]

- **Scenariusz:** `finalize_research_success` przyjmował staged `SYNTHESIS_PENDING`, a `mark_research_run_complete` delegował do niego. Caller mógł przekazać kartę i koszt poza atomowym helperem; dla staged COMPLETE identyczny payload wpadał w legacy no-op. To obchodziło typed context, A2, B SUCCESS i kanon `model_usage`.
- **Naprawa:** blokada flow `staged` następuje po odczycie relacji, lecz przed walidacją karty, no-opem i mutacjami. Generic i alias rzucają ten sam `ResearchTopicIntegrityError`; audyt wykazał też możliwość samego staged `runs.SUCCESS` przez `finish_run`, więc ten ogólny helper odmawia staged SUCCESS/DRY_RUN. Tylko `finalize_staged_research_with_card` może zapisać staged sukces i jego koszt.
- **Dowód:** SYNTHESIS_PENDING, COMPLETE z identyczną kartą/kosztem, FAILED i arbitralny koszt generic oraz SYNTHESIS_PENDING/COMPLETE aliasu są odrzucone; tak samo SUCCESS/DRY_RUN przez `finish_run`. Po reopen nie zmieniają się karty, źródła, B SUCCESS, statusy, usage, cache kosztu, timestampy, błędy, card ID ani force marker. **454 passed**, 0 USD, bez API.

### 2026-07-13 — Etap 1: lease nie może znaczyć „spróbuj jeszcze raz” — [PREVENTED FAILURE]

- **Ryzyko:** odczyt QUEUED, a potem osobny UPDATE pozwala dwóm workerom zabrać ten sam job; osobne checki budżetu pozwalają dwóm jobom przekroczyć limit łącznie. Gorszy wariant dotyczy browsera: utrata lease po kliknięciu nie dowodzi, że publikacja nie nastąpiła.
- **Zabezpieczenie:** claim, enqueue i rezerwacja są pojedynczymi transakcjami `BEGIN IMMEDIATE` z rowcount/CAS. Partial UNIQUE blokuje drugi aktywny research job per account/topic. BROWSER po expiry idzie do NEEDS_VERIFICATION, nie do auto-retry; tylko LOCAL/RESEARCH przed efektem zewnętrznym mogą wrócić do QUEUED.
- **Dług świadomy:** nie ma jeszcze workera, więc queue nie wie jeszcze, kiedy future research przekroczył granicę płatnego calla; jego dispatcher musi przed tym mieć osobną, trwałą semantykę skutku. PolicyEngine nadal nie czyta `system_flags` runtime (P1-7 pozostaje otwarte do integracji).
- **Dowód:** Barrier/reopen dla 8 klas wyścigów, 0009 rollback oraz **463 passed**, bez API i kosztu.
## 2026-07-13 — P1: stary worker zapisywał research po utracie lease

- **Wykrycie:** niezależne review końcowej akceptacji restartu po ADR-044.
- **Scenariusz:** worker A claimował job i atomowo inicjalizował run. Po expiry recovery ustawiał `NEEDS_VERIFICATION`, ale A pozostawał wewnątrz synchronicznego pipeline’u. Ponieważ `add_model_usage`, aktualizacja cache kosztu, `finish_run`, `mark_research_run_failed`, `add_research_card` i `finalize_research_success` nie znały job ID ani lease ownera, stary proces mógł zmienić canonical stan po recovery.
- **Skutek:** możliwe usage/koszt, FAILED albo COMPLETE i karta zapisane przez proces bez aktualnego prawa wykonania; `complete_job` odrzucał starego ownera dopiero za późno. To był P1, nie kosmetyka guardu.
- **Naprawa:** ADR-045. Po atomowej inicjalizacji powstaje `JobExecutionContext`; każda jobowa mutacja single-flow używa krótkiego `BEGIN IMMEDIATE` i sprawdza pełny job→run→owner→fresh lease fence w tej samej transakcji. `StaleJobExecutionError` przerywa pipeline bez wtórnego failure write.
- **Dowód:** expiry przed recovery, pełna old-owner matrix po recovery, utrata lease podczas klienta i race dwóch połączeń. Po close→reopen snapshot jest identyczny, usage/card nie istnieją, run pozostaje DRY_RUN/PENDING, job jest pod kontrolą recovery, integrity `ok`.
- **Granica:** realny provider może naliczyć koszt mimo utraty lease podczas calla. Nie wolno wtedy pozwolić staremu workerowi zapisać canonical wynik; przyszłe rozliczenie wymaga idempotentnego ledgeru provider request ID. Nie implementowano go w tym offline zadaniu.

## 2026-07-13 — P1: czas lease pobrany przed `BEGIN IMMEDIATE` i CSV jako fałszywa granica trwałości

- **Wykrycie:** niezależne końcowe review Etapu 1 po ADR-045.
- **Scenariusz lease:** operacja startowała przed expiry, lecz czekała na cudzy SQLite write lock. Zamrożony czas sprzed czekania pozwalałby po zwolnieniu locka zatwierdzić `RUNNING`, heartbeat, inicjalizację lub terminalizację już wygasłego lease.
- **Scenariusz CSV:** `record_job` najpierw poprawnie commitował `model_usage` i koszt do SQLite, ale błąd appendu `COSTS.csv` propagował się do ogólnego catcha workera. Ten mógł sfinalizować sam job, pozostawiając run/research_run w aktywnym stanie.
- **Naprawa:** czas jest odczytywany dopiero po `BEGIN IMMEDIATE`; runtime przekazuje `Clock`. `COSTS.csv` po commicie jest best-effort i loguje wyłącznie kontrolowane ostrzeżenie. Nieoczekiwany wyjątek po inicjalizacji uruchamia atomową fenced terminalizację job/run/research_run.
- **Dowód:** 42 restart acceptance, w tym 7 lifecycle i 5 fenced-write testów real-thread/file-SQLite lock wait i reopen, race heartbeat↔recovery, CSV success/failure oraz unexpected pipeline error; pełny suite 683 passed, `integrity_check=ok`, koszt 0 USD.
- **Pozostawiony dług:** przed Etapem 8 decyzja KEEP/DEPRECATE/REMOVE dla eksportu `COSTS.csv`; nie budowano eksportera ani outboxa. Realny provider request po utracie lease nadal wymaga odrębnego idempotentnego ledgeru.

### Nieudane próby podczas naprawy

1. Pierwsze uruchomienie najwęższego testu zakończyło się błędem kolekcji `ImportError: JobExecutionContext` — zamierzony czerwony dowód, że kontrakt jeszcze nie istniał; nie zmieniło bazy.
2. Pierwsza regresja maintenance+scheduling+queue+storage miała 1 failure: stary test granicy scheduling przekazywał naïwny timestamp odczytany z SQLite jako `now`. Nowy kontrakt UTC ma takie dane odrzucać, więc test jawnie przywraca znaną strefę UTC na granicy adaptera; walidacji produkcyjnej nie poluzowano.
3. Nie wykonywano retry płatnej ani publikującej operacji. Obie porażki były lokalne, deterministyczne i kosztowały 0 USD.

## 2026-07-14 — P1: post-dispatch heartbeat mógł częściowo terminalizować sukces RESEARCH

- **Wykrycie:** literalny restart acceptance po poprzednich naprawach Etapu 1.
- **Scenariusz:** pipeline workera commitował kartę, źródła, `research_runs=COMPLETE`, run i topic, a następnie `Worker.run_once()` wywoływał jeszcze końcowy heartbeat oraz `complete_job`. Wyjątek z tej ogólnej ścieżki trafiał do szerokiego catcha i mógł wykonać samotne `fail_job`.
- **Skutek przed naprawą:** reprodukcja z awarią czwartego heartbeat dawała `worker=FAILED`, `job=FAILED`, a `run=DRY_RUN` i `research_run=COMPLETE`. Baza była technicznie poprawna, lecz lifecycle semantycznie sprzeczny.
- **Naprawa:** ADR-047. Finalizacja jobowego success zapisuje `jobs=DONE` w tym samym commicie co artefakt i lifecycle researchu. Typowany wynik dispatchera zatrzymuje worker przed dodatkowym heartbeat/complete/fail. Diagnostyka po commicie jest best-effort i nie zmienia kanonu SQLite.
- **Dowód:** test był czerwony przed zmianą i zielony po niej; failpointy przed job UPDATE, po nim oraz po commicie wykazują odpowiednio pełny rollback albo trwały pełny sukces. Dodatkowo failure transaction zachowuje primary error mimo błędu rollbacku, a rzeczywisty path katalogu `COSTS.csv` nie zmienia wyniku. 53 acceptance i 695 testów offline, `integrity_check=ok`, 0 USD.
- **Pozostawiony dług:** nie powstał outbox ani ledger provider request ID; CSV pozostaje utrzymanym eksportem best-effort do audytu przed Etapem 8.

## 2026-07-14 — P1: runtime nie walidował właściciela terminalizacji DispatchResult

- **Wykrycie:** końcowy pakiet review Etapu 1 po ADR-047.
- **Reprodukcja:** `DispatchResult(terminalization="WORKFLOW_TERMINALIZED")` przyjmował string. Po rzeczywistym atomic success worker nie rozpoznawał go przez identity, próbował post-terminal heartbeat, widział wyczyszczony lease i raportował `LOST_LEASE`, mimo że baza była już DONE/COMPLETE.
- **Drugi inwariant:** `WORKFLOW_FAILED` jest własnością workflow dopiero, gdy workflow atomowo zamknął job, run i research_run; worker nie może po nim wywołać generic `fail_job` ani zmienić canonical error.
- **Naprawa:** ADR-048 wymaga enumu w zamrożonym `DispatchResult`, a Worker waliduje obiekt i enum ponownie, przed guardem i przed każdą finalną mutacją. Contract error jest propagowany, nie mapowany na failure ani LOST_LEASE. Inserty karty/źródeł wymagają `rowcount == 1`; rollback failure zostaje secondary note.
- **Dowód:** literalny konstruktor był czerwony przed zmianą; atomic failure ma 0 generic `fail_job`. 58 acceptance i pełny suite 700 passed, reopen/snapshot/integrity poprawne, koszt 0 USD.
- **Nieudana lokalna regresja:** po wymaganiu jawnego wyniku siedem osiągalnych fake dispatcherów testowych zwracało `None`; testy heartbeat oczekiwały wtedy LOST_LEASE. Doprecyzowano je do jawnego `WORKER_MUST_COMPLETE`, bez zmiany produkcyjnej semantyki i bez dotykania bazy.

## 2026-07-14 — P0: SDK mogło wydać więcej niż jedna logiczna próba

- **Wykrycie:** niezależny audyt końcowego pakietu Etapu 1.
- **Problem:** konstrukcje `anthropic.Anthropic(...)` nie przekazywały `max_retries=0`, więc SDK mogło po timeout, błędzie połączenia, 429 albo 5xx wysłać następny płatny request. Klient research miał dodatkowo własną pętlę retry. Równolegle zwykłe `app.main` ufało `DRY_RUN=false`, a ceny zero/brakujące mogły obniżyć estymatę do zera przed realnym wywołaniem.
- **Skutek potencjalny:** jedna zatwierdzona próba mogła oznaczać więcej niż jedno żądanie i koszt niezgodny z pre-flightem; nie wykryto nowego realnego wydatku podczas tej naprawy.
- **Naprawa WAVE 0A:** SDK dostaje `max_retries=0` i dodatni timeout; klient wykonuje jedną próbę i propaguje typowany błąd. Normalne CLI i worker są fake/offline niezależnie od env. Tylko capped root z `--real` może utworzyć adapter, po fail-closed walidacji pięciu cen. Brak `--real` nie tworzy klienta. Estymata tematów została wyrównana do requestu 1500 tokenów outputu.
- **Dowód:** testy fake/spy obejmują SDK config, timeout/429/5xx z licznikiem jednej próby, normalne CLI/worker z realnym kluczem, brak `--real`, ceny missing/0/negative/NaN/inf, dry-run bez ceny i zgodność limitu. Kodowa regresja ma 14 testów WAVE 0A i pełny suite 714 passed. **Niezależny review: `APPROVED WITH P2`; P0-01, P1-01 i P1-02 są zamknięte, a WAVE 0A formalnie zamknięta. Etap 1 pozostaje BLOCKED przez pozostałe P1.**
- **Granice:** bez sieci, API, publikacji, browsera ani kosztu; nie dodano ledgeru provider request ID ani reconciliation. Naruszenie lokalnej bramki `data/agent.db` jest opisane poniżej.

## 2026-07-14 — Naruszenie bramki acceptance: test WAVE 0A otworzył domyślną bazę

- **Wykrycie:** porównanie SHA-256 po pełnej regresji WAVE 0A.
- **Przyczyna:** test normalnego CLI podmienił `app.main.load_settings`, ale wywoływany runner ładował ustawienia w swoim module. W rezultacie test użył domyślnej ścieżki `data/agent.db` i zapisał wyłącznie artefakty fake/dry-run zamiast bazy tymczasowej.
- **Zakres:** zapisano 10 powtarzalnych runów/research cardów/topiców i 20 wierszy usage fake/dry-run; nie wykonano sieci, API, publikacji ani płatnego requestu. `PRAGMA integrity_check=ok`, ale hash zmienił się z `C92D9565DDA322997DE0D6A78D3943336E58CD9261229949E0BCFE4E43F9A63C` na `77F84B30F9E53A1964EFA2A44E4DBF821848758FFF86A29DB7A028AA55A3B22B`.
- **Działanie:** test zastąpiono bezpośrednim wywołaniem runnera z jawnym `Settings` wskazującym bazę tymczasową; jego 14 testów i pełny suite 714 passed nie zmieniły już bieżącego hashu. Nie wykonano kolejnego zapisu do `data/agent.db` ani nie próbowano „naprawy” bez źródłowej kopii.
- **Blokada historyczna:** przeszukane lokalne kopie projektu, katalog tymczasowy i zachowane artefakty nie zawierały pliku o hash bazowym `C92D9565DDA322997DE0D6A78D3943336E58CD9261229949E0BCFE4E43F9A63C`.
- **Kontrolowane odtworzenie po review:** właściciel zatwierdził wariant `APPROVE WITH P2` (P0=0, P1=0). Forensic analysis zaklasyfikowała artefakty testu jako klasę A, sekwencje jako klasę B, a istniejące UPSERT/`topics.id=1` jako klasę C nieudowadnialną historycznie. Na osobnej kopii usunięto tylko A i przywrócono B, następnie po dwóch reopenach (`integrity_check=ok`, `foreign_key_check=[]`) podmieniono wyłącznie główny plik po zachowaniu backupów. Nowy baseline to `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.
- **Wynik i granica dowodu:** nie stwierdzono utraty realnych danych: 13 wpisów `dry_run=0` nadal sumuje 0,684580 USD, a `c01171bc` ma 0,183964 USD, Card #2, cztery VERIFIED sources i siedem usage. Werdykt `NOT PROVABLY RESTORABLE` dla dawnego pliku pozostaje prawdziwy — ustanowiono nowy baseline logiczny, nie odzyskano bitowego snapshotu. **Incydent bazy jest zamknięty; nie jest to zamknięcie Etapu 1.**

## 2026-07-14 — prewencja: niejednoznaczny skutek providera po restartcie

- **Ryzyko:** timeout, connection error albo awaria procesu tuż po wysłaniu requestu mogły pozostawić koszt bez odpowiedzi/usage. Ponowienie z nowym losowym identyfikatorem mogłoby stworzyć drugi koszt, a zwolnienie całej rezerwacji przed rozstrzygnięciem zaniżyłoby dostępny budżet.
- **Zmiana WAVE 0B:** `provider_attempts` zapisuje stabilne request_id i maksymalną rezerwację przed SDK. Po przekroczeniu granicy `REQUEST_STARTED` nie ma automatycznego retry; nieznany wynik zachowuje rezerwację w `NEEDS_RECONCILIATION`. Znamy za to różnicę między błędem przed requestem, odpowiedzią z usage i potwierdzonym błędem bez usage.
- **Dowód:** offline ledger/race/reopen/pipeline/CLI tests na tymczasowej SQLite; testowy guard odrzuca prawdziwą ścieżkę `data/agent.db`. Nie wykonano API, sieci, browsera, publikacji ani kosztu. Status: `WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; to nie jest dowód live ani zamknięcie Etapu 1.

## 2026-07-14 — niezależne review WAVE 0B: trzy findingi P1

- **P1 — obejście durable joba:** `run_two_stage_research_pipeline` i `run_staged_research_pipeline` pozwalały realnemu klientowi rozpocząć świeżą pracę bez joba, lease i request ledgeru. Naprawa zatrzymuje rzeczywistego providera przed pierwszym wywołaniem i wskazuje WAVE 1A; fake/dry-run pozostają testowalne offline.
- **P1 — lokalna tożsamość operation key:** identyczny klucz nie był globalnym kontraktem semanticznego intentu, a komunikat CLI zależał od wyścigu między odczytem i insertem. Naprawa używa globalnego `real-research:<operation_key>` oraz atomowego wyniku enqueue; różny payload daje jawne `OPERATION_KEY_CONFLICT`.
- **P1 — zbyt słaby ledger attemptów:** wcześniejszy schemat pozwalał zapisać nieprawidłowy stan, request_id lub nowy real usage bez powiązanego requestu. Migracja `0011` wymusza kształt stanów, przejścia i request-bound usage; historii nie udaje się rekonstrukcji, tylko oznacza ją `is_legacy_usage=1`.
- **Dowód naprawy:** testy negatywne SQLite, test migracji poprawnej/uszkodzonej historii, testy wyścigu operation key i budżetu z niezależnych konekcji oraz pełny suite 741 passed. Bez API, sieci, browsera, publikacji, kosztu i zmiany `data/agent.db`.

## 2026-07-14 — WAVE 0B.2: drugi REJECT ujawnił brak dowodu, nie brak happy path

- **P1-01:** niski poziom realnego klienta dopuszczał caller bez contextu/ID; teraz każda taka próba kończy się typowanym błędem przed callerem i `messages.create`.
- **P1-02:** operation key nie był pełnym snapshotem wykonania; canonical intent zapisuje konfigurację, a test worker parity dowodzi użycia snapshotu po zmianie ENV.
- **P1-03:** ledger wymagał rozróżnienia braku dawnych danych od sprzecznych danych. `0012` wycofuje migrację dla arbitralnego request_id, obcego runu i brakującego attemptu, zamiast ukrywać je jako legacy.
- **Wynik:** 752 testy offline, zero API/sieci/kosztu i niezmieniony baseline bazy. Pozostaje wymagane niezależne re-review; operator reconciliation i WAVE 1A nie zostały wdrożone.

## 2026-07-14 — WAVE 0B.3: równe stringi nie są dowodem identity ani świeżego lease

- **P1-01:** context i callback mogły zwrócić ten sam arbitralny `request_id`, a klient porównywał wyłącznie ich wzajemną równość. Naprawa wyprowadza ID z trwałych pól i odrzuca arbitralne, job/stage/attempt mismatch oraz separator w stage przed callerem.
- **P1-02:** asercja lease odczytywała stare `context.checked_at`; po realnym expiry caller mógł nadal ruszyć. Naprawa pobiera czas execution clock wewnątrz nowej transakcji storage, a druga asercja chroni samo `messages.create`.
- **Dowód:** 770 testów offline obejmuje expiry, granicę równą expiry, odnowienie, takeover, zmianę run/fence i `NEEDS_RECONCILIATION`; 0 API, sieci, browsera, publikacji i kosztu; baseline bazy niezmieniony.

## 2026-07-15 — P1: testowy kernel nie dziedziczył granic bezpieczeństwa do subprocessów

- **Kategoria:** SAFETY
- **Co się zepsuło:** monkeypatch w `conftest.py` chronił główny interpreter, lecz subprocess mógł ominąć ochronę przez `sqlite3.dbapi2`, URI SQLite, proxy/NO_PROXY albo konstrukcję realnego SDK. To nie wywołało sieci ani nie zmieniło bazy podczas tego zadania, ale naruszało wymagany dowód izolacji.
- **Naprawa:** test-only `sitecustomize.py` ładuje dziedziczony kernel przed collection oraz w subprocessach. Blokuje surowe SQLite dla pełnej kanonizacji ścieżki, socket/DNS/SDK i czyści sekrety oraz proxy; tymczasowe SQLite i fake SDK pozostają dostępne.
- **Dowód:** main/subprocess raw+dbapi2+URI, socket/DNS, SDK oraz scrub environment; 823 testy offline, 0 USD, bez API i z niezmienionym SHA baselineu.
- **Status:** FIXED; niezależny review WAVE 0B nadal wymagany.

## 2026-07-15 — P1: provider attempt nie wiązał trwałego intentu z ostatnią granicą callera

- **Kategoria:** SAFETY
- **Co się zepsuło:** attempt miał request identity i fresh lease, ale nie trwały fingerprint wszystkich pól execution intentu. Zmiana `jobs.payload_json` po rezerwacji mogła rozjechać payload z attemptem przed fake/SDK callerem.
- **Naprawa:** `0013` przechowuje niezmienny SHA-256 canonical `execution_intent`; finalna transakcja przed callerem liczy go ponownie. Rozbieżność lub malformed/missing intent zostawia attempt w `NEEDS_RECONCILIATION`, bez callera, usage, kosztu i settlementu. `--real --resume` jest odmówione przed SQLite i `ensure_account`.
- **Dowód:** model/provider/token/timeout/cap/pricing/workflow/mode/prompt/pipeline są parametryzowane jako późne zmiany; każda ma `caller=0`, `usage=0`, `cost=0` i typed code. Weryfikacja full suite: 823 offline, 0 USD, bez API/sieci/browsera.
- **Status:** FIXED; nie jest to deklaracja zamknięcia WAVE 0B.

## 2026-07-15 — W0B-REV-01–05: snapshot techniczny nie obejmował jeszcze całego requestu

- **Kategoria:** SAFETY / consistency.
- **Co znaleziono:** fingerprint trwałego intentu obejmował parametry techniczne, lecz realny prompt nadal czerpał `topic.question` i `account.niche` z mutowalnych obiektów. Finalna asercja nie weryfikowała pełnego lifecycle `runs` i `research_runs`; brakowało też testów stage, prompt inputs, restartu oraz wariantów safety kernela.
- **Naprawa:** `durable_research_intent_v2` utrwala kanoniczne prompt-input i stage, a worker buduje plan wyłącznie z niego. Finalna transakcja odmawia po każdej niezgodności job/run/research_run/attempt/intent i zachowuje started attempt do reconciliation. Kernel czyści lowercase secret i fail-closed odrzuca nielokalny SQLite URI authority.
- **Dowód historyczny przed W0B-REV-06:** 861 testów offline obejmuje osobne mutacje parametrów requestu, terminalne/niespójne runy i research_runs, reopen SQLite, fake caller `0`, usage/koszt/settlement `0` oraz brak attempt #2. Nie użyto API, sieci, browsera ani chronionej bazy.
- **Status:** FIXED technicznie; WAVE 0B pozostaje `CANDIDATE` do niezależnego re-review, Etap 1 = `BLOCKED`.

## 2026-07-15 — CRITICAL W0B-REV-06: limit requestu rozchodził się z rezerwacją

- **Kategoria:** SAFETY / accounting consistency.
- **Co się zepsuło:** durable intent dopuszczał dodatni `max_tokens`, a caller używał `intent.max_tokens`, lecz single pipeline wyliczał koszt i rezerwował attempt z niezależnym `max_output_tokens=3000`. Request z limitem większym od 3000 mógł więc otrzymać actual usage cost większy od reservation, a dawny settlement zapisywał go jako zwykły `SETTLED`.
- **Naprawa:** dispatcher przekazuje literalny persisted limit do pipeline; pipeline przekazuje go do estymatora, policy i rezerwacji. Settlement canonicalizuje obie kwoty do sześciu miejsc USD (`ROUND_HALF_UP`). Nadwyżka nie znika: w tej samej transakcji zapisuje się jeden usage i koszt runu, attempt przechodzi do `NEEDS_RECONCILIATION` z `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION`, a typed outcome blokuje sukces i attempt #2.
- **Dowód historyczny po REV-06:** poprawne durable intenty 2999/3000/3001, reopen, mutacja po attempt, exact estimate/reservation/caller, rounding boundary oraz actual under/over są testowane wyłącznie fake callerami i tymczasową SQLite. Pełna regresja: 873 node IDs, rozłączne partycje 206+218+226+223, wszystkie zielone; 0 USD, bez API/sieci/browsera/publikacji.
- **Status:** FIXED technicznie; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Operator reconciliation pozostaje przyszłą pracą i nie jest udawany przez automatyczny retry.

## 2026-07-15 — W0B-REV-09/10: kronika nie nadążała, a dwa sposoby roundingu mogły rozjechać pieniądze

- **Kategorie:** documentation integrity / accounting consistency.
- **Co znaleziono:** obowiązkowa kronika `opis-budowy-substack/` nie opisywała zamkniętych W0B-REV-06/07/08, historycznych liczników ani bezpiecznego snapshotu. Równocześnie estymator i `UsageTracker` używały Pythonowego banker's `round`, podczas gdy intent i storage używały `Decimal/ROUND_HALF_UP`.
- **Naprawa:** wspólny `app.core.money` realizuje literalny kontrakt `Decimal(str(value)) → quantize(0.000001, ROUND_HALF_UP)`. Przed zapisem i przy porównaniach estimate/reservation/actual każda kwota jest kanoniczna; suma komponentów powstaje przed pojedynczym roundingiem. Usunięto nieosiągalny fresh legacy provider block po return oraz nieużywaną stałą DB-API bez zmiany rootu paid execution.
- **Dowód historyczny:** granice `0.0000004/.5/.6`, `0.0000015`, `0.1234565`, `0.1234575`, cache read/write/web, storage cache, settlement równe oraz ±1 mikro-USD i fake caller → usage → settlement. Historycznie 887 testów, partycje 211+222+229+225; bez API/sieci/browsera/kosztu i bez zapisu do chronionej bazy.
- **Status:** W0B-REV-09 i W0B-REV-10 są technicznie zamknięte; wcześniejszy REJECT z CRITICAL W0B-REV-06 nie jest formalnie zastąpiony przez akceptację. WAVE 0B nadal `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## 2026-07-15 — MAJOR W0B-RR-01: poprawny helper nie obejmował całego przepływu

- **Kategoria:** accounting consistency / review escape.
- **Co znaleziono:** `ROUND_HALF_UP` działał na granicach helpera, ale staged estimate najpierw kwantyzował koszt jednego źródła, potem mnożył publiczny float. Policy Engine, niektóre sumy persisted kwot, pipeline i check CLI także pozwalały, by float uczestniczył w decyzji. Wyniki `0.1 + 0.2` oraz wielokrotności pół-mikro-USD nie miały więc jednego dowodliwego kontraktu end-to-end.
- **Naprawa:** estymator przechowuje raw komponenty jako `Decimal` do jednej końcowej granicy; policy, storage, pipeline i CLI canonicalizują do `Decimal` przed sumą lub porównaniem. Zamiast SQL `SUM(REAL)` storage sumuje kanoniczne wiersze. Usunięto ponadto dwa martwe konstruktory klienta z prywatnych helperów resume; real resume nadal fail-closed, bez konstruktora i bez providera.
- **Dowód:** regresje `2×` i `3×0.0000005`, `0.1+0.2 == 0.3` dla policy, ledgeru i CLI, granice ±1 mikro-USD, estimator, budget, durable provider, execution intent, usage, settlement, storage, restart, migracje, maintenance i CLI resume. Pełny wynik: 894 testy, partycje 213+224+231+226, exact-once coverage i brak BOM; wyłącznie fake callery oraz tymczasowe SQLite.
- **Status:** FIXED technicznie; WAVE 0B pozostaje `CANDIDATE` do krótkiego niezależnego re-review, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Nie wykonano API, sieci, browsera, kosztu ani zapisu do `data/agent.db`.

## 2026-07-15 — P2 checkpointu: rozbieżność inwentarza Git

- **Kategoria:** documentation / release-control accuracy.
- **Co znaleziono:** implementer zadeklarował 71 wpisów Git, lecz niezależny gate zliczył rzeczywisty stan jako 50 modified, 1 deleted i 21 untracked, czyli 72 wpisy.
- **Naprawa:** checkpoint używa wyłącznie inwentarza 72 i rozdziela zatwierdzony zakres do stage od plików chronionych pozostających unstaged.
- **Status:** `APPROVED WITH P2 — READY FOR CHECKPOINT`; nie jest to `CLOSED` przed commitem. Etap 1 `BLOCKED`, live API `ZABRONIONE`; nie wykonano API, sieci, browsera, kosztu ani mutacji `data/agent.db`.

## [2026-07-16] Skonsolidowany Etap 1 — błędne założenia wykryte w kontrpróbach

- **Kontekst:** pierwsza seria 16 nowych testów offline dla Task Scheduler, raportu read-only, migracji kopii i Unicode.
- **Nieudana próba 1:** test launchera szukał składni argumentów z podwójnymi cudzysłowami, podczas gdy prawidłowy PowerShell używał tablicy literałów w pojedynczych. To był błąd asercji, nie entrypointu; test zawężono do faktycznego kanonicznego argument list.
- **Nieudana próba 2:** test „SDK niezaładowane” sprawdzał absolutną nieobecność `anthropic` w `sys.modules`. Kernel bezpieczeństwa pytest może wstępnie zainstalować blokujący moduł testowy, więc warunek dawał false positive. Kontrpróba mierzy teraz wyłącznie nowe moduły załadowane przez import CLI; realny SDK nadal nie jest importowany.
- **Nieudana próba 3:** raport migracyjny opisywał rollback pojedynczym stringiem. Test oczekiwał dowodliwej struktury. Raport zmieniono na jawne `method=full_file_restore`, źródło backupu i zakaz reverse SQL.
- **Nieudana komenda walidacyjna:** pierwszy targeted run wskazał nieistniejący `tests/test_config.py` i zakończył się kodem 1 przed collection. Poprawiono listę plików; właściwy zestaw przeszedł 144/144.
- **Dodatkowa korekta przed testem:** pusty `IdleSettings` w Task Scheduler XML zastąpiono jawnymi `StopOnIdleEnd=false` i `RestartOnIdle=false`, aby nie polegać na niejednoznacznym default/schema parsera Windows.
- **Skutek:** brak API, sieci, SDK, browsera, publikacji i kosztu; brak zapisu/migracji `data/agent.db`. Findingi zamknięto przed pełną regresją.

## [2026-07-16] Rzeczywisty copy-preflight odrzucony przez istniejące sidecary SQLite

- **Próba:** po zielonej migracji syntetycznej bazy 0009 podjęto niezależną próbę utworzenia tymczasowej kopii rzeczywistych bajtów chronionej bazy, bez zamiaru jej podmiany.
- **Wynik:** procedura zatrzymała się przed kopiowaniem i przed otwarciem SQLite: wykryła `data/agent.db-wal` oraz odmówiła kodem 2. Sidecary mają timestamp 2026-07-15, sprzed bieżącego pakietu (`-wal` 0 B, `-shm` 32768 B).
- **Decyzja defensywna:** nie usunięto sidecarów, nie wykonano checkpointu i nie otwarto produkcyjnej bazy do zapisu. Przyszły live-preflight wymaga osobno zatwierdzonego zatrzymania procesów, wyjaśnienia właściciela sidecarów i kontrolowanego checkpointu przed kopią.
- **Wpływ:** nie blokuje implementacji copy-only narzędzia ani testu na produkcyjnie ukształtowanej bazie tymczasowej; pozostaje jawnym warunkiem przed rzeczywistą migracją produkcyjną, która i tak należy do kryterium acceptance. Produkcyjna migracja nie została wykonana.

## [2026-07-16] Kontrpróby inline — pierwsze wywołanie utraciło cudzysłowy

- **Objaw:** trzy niezależne skrypty przekazane jako zmienna do `python -c` zostały zinterpretowane przez Windows/PowerShell bez wewnętrznych cudzysłowów i zakończyły się `SyntaxError`; nie uruchomiły logiki aplikacji.
- **Naprawa:** ten sam kod przekazano bez zapisu pliku przez stdin (`$code | python -`). Kontrpróby przeszły: read-only write zablokowany, baza temp byte/metadata unchanged, 5 flag UNKNOWN, maintenance UNKNOWN, 0 nowych importów SDK, systemowy real runner 0 calli, worker+maintenance nie zmieniły flag paid/browser.
- **Wpływ:** wyłącznie błąd quoting harnessu; bez dostępu do produkcyjnej bazy, API, sieci i kosztu.
