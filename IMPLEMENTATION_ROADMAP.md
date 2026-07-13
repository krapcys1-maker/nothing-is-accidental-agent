# IMPLEMENTATION_ROADMAP — Nothing Is Accidental Agent

> **STATUS: JEDYNA OBOWIĄZUJĄCA KOLEJNOŚĆ DALSZYCH PRAC.**
> Data: 2026-07-13 · Architektura docelowa: `MASTER_ARCHITECTURE.md` · Stan bieżący: `CURRENT_PROJECT_STATE.md`.
> Zastępuje plany etapów z `docs/IMPLEMENTATION_PLAN.md` (§B.11, CZĘŚCI D–F) i plan napraw z audytu 12.07 — oba w `docs/archive/superseded_plans/`.
>
> **ETAP 0 ZAKOŃCZONY. NASTĘPNY ETAP: 1 (NIEROZPOCZĘTY).** Nie zaczynaj etapu N+1 przed spełnieniem kryteriów zakończenia etapu N. Każde realne (płatne lub publikujące) uruchomienie wymaga osobnej, jawnej zgody właściciela — zawsze.

Oznaczenia P0-x/P1-x/P2-x pochodzą z audytu 2026-07-12 (zarchiwizowany; findingi przeniesione tutaj i do `CURRENT_PROJECT_STATE.md`). ✅ = już wykonane (nie jest zadaniem).

---

## Etap 0 — Stabilizacja obecnego projektu (ZAKOŃCZONY 2026-07-13)

- **Cel — OSIĄGNIĘTY:** domknięto znane wady wykonawcze researchu i uzyskano pierwszą kompletną, realną Research Card z terminalnym `SUCCESS`.
- **Uzasadnienie:** wcześniejsze realne próby kończyły się bez kompletnej karty. Kontrolowany staged run `c01171bc` zachował A1/A2 po pierwszym błędzie B, a następnie za osobną zgodą wznowił wyłącznie B i spełnił kryterium etapu bez powtarzania opłaconych etapów.
- **Zależności:** brak.
- **Już wykonane w tym etapie ✅:** testy 102/102 zielone; naprawy P0-1 (SUCCESS), P0-2a/b (wymuszone UNVERIFIED + `min_verified_sources`), P0-3 (blokada `run-research --real`) — z testami regresyjnymi; diagnostyka raw+stop_reason; default A2=1500; konsolidacja dokumentacji (ten zestaw dokumentów).
- **Pliki/moduły:** `app/storage/migrations/`, `app/storage/repositories.py`, `app/models.py`, `app/workflows/research/pipeline.py`, `app/orchestrator/runner.py`, `app/policies/policy_engine.py`, `app/research/cost_estimator.py`, `app/storage/db.py`, `scripts/run_capped_research.py`, testy.

### Zadania (w tej kolejności)

1. ✅ **[P1-1/P1-9] Migracja `0006_research_run_flow.sql` — WYKONANE 2026-07-12:** kolumna `research_runs.flow` ('single'|'two_stage'|'staged') NOT NULL bez defaultu + deterministyczny backfill; wszystkie istniejące funkcje resume walidują flow, a CLI także dozwolony status przed jakąkolwiek pracą; `_detect_flow` usunięte z CLI; 127 testów zielonych.
2. ✅ **[P1-2 + P1-8] Spójność księgi runów — WYKONANE 2026-07-12:** researchowy INSERT `model_usage`, kanoniczna suma i absolutny UPDATE `runs.cost_usd` są jedną transakcją; idempotentny helper pozostaje dla no-call/resume. A1/A2/B synchronizują cache przy każdym wyjściu bez zmiany statusu. `connect()` ustawia najpierw `busy_timeout=5000`, potem potwierdzone `journal_mode=WAL` dla bazy plikowej; 139 testów zielonych.
3. ✅ **[P1-5] Migracja `0007_candidate_attempts.sql` — WYKONANE 2026-07-12, poprawione po review:** `attempts` = liczba atomowo zarezerwowanych A2; historyczne `EXTRACTED`/`EXTRACTION_FAILED` dostają konserwatywną dolną granicę 1, a `PENDING` 0. Claim wymaga `attempts < cap` i prowadzi przez `EXTRACTION_IN_PROGRESS`, który po awarii blokuje zwykłe resume. Jawne `retry-failed-candidates` resetuje wyłącznie eligible failed, jest izolowane kontem i może odblokować `PARTIAL_EXHAUSTED` do `PARTIAL` po podniesieniu capu; brak API i kosztu. Migracja 0007 oraz ledger są jedną transakcją runnera. Domyślny cap=2 oznacza pierwszą próbę + jedno ręczne retry; `PARTIAL_EXHAUSTED` pozostaje terminalny dla zwykłego resume. 164 testy zielone.
4. ✅ **[P1-6] Cykl życia tematu — WYKONANE 2026-07-12, poprawione po trzech review:** legacy `finalize_research_success` weryfikuje run–topic–card–account i w jednej transakcji ustawia COMPLETE, jawnie oczekiwany terminalny `runs.status` oraz `topics.status=USED` dla `single`/`two_stage`; identyczne powtórzenie jest no-op bez UPDATE, a inna karta, koszt, status lub uszkodzony COMPLETE są odrzucane bez mutacji. Flow `staged` finalizuje wyłącznie `finalize_staged_research_with_card`; nie może przejść przez publiczny legacy finalizer ani jego alias. Świeży research z poprawną kompletną kartą jest blokowany przed klientem, a USED/COMPLETE bez poprawnej relacji zatrzymuje się fail-closed, także z force. Tylko jawne `--force-re-research` omija poprawną blokadę re-researchu; `--resume` nie przyjmuje tej flagi. Pełna macierz obejmuje SELECTED+COMPLETE, historię FAILED/PARTIAL/COMPLETE, force wobec korupcji, account mismatch z czterema licznikami, błędy wymuszonych runów oraz negatywne flow↔Stage B i karty obcego topicu/konta; **212 testów zielonych**. Dokładne porównanie kosztu float pozostaje fail-closed P2-18.
5. ✅ **[P1-3 + P1-4] Budżet szczelny — WYKONANE 2026-07-12, poprawione po pełnym review:** estymata ×(1+max_retries), re-check z `model_usage` przed każdą próbą, obowiązkowy cap dla realnego pipeline, absolutny cap resume, walidacja run–account przed usage, centralny `PolicyEngine.check_run_budget` z fail-closed dla niepoprawnego stanu oraz jawne `timeout-billed-unrecorded`; 257 testów offline.
6. ✅ **[nowe, z tego audytu] Wyrównanie klienta tematów — WYKONANE 2026-07-12:** `AnthropicLLMClient` buduje `Usage` przed parsowaniem, zachowuje usage/model w typowanych błędach parse/schema, rozróżnia błąd providera bez odpowiedzi, zdejmuje dokładnie jeden kompletny zewnętrzny code fence, a workflow księguje dostępny koszt raz i kończy run `FAILED` bez częściowych topics; **286 testów offline**, zero API i 0 USD.
7. ✅ **[P2-9] Higiena rejestru decyzji — WYKONANE 2026-07-12:** ADR-001/002/003/005/006 zweryfikowane względem architektury, roadmapy, bieżącego stanu i wdrożenia, następnie oznaczone `ACCEPTED`. Historyczne mapowanie publikacji w ADR-005 doprecyzowano do aktualnego Etapu 5 bez zmiany meritum; brak sprzeczności, zero zmian kodu, 286 testów offline i 0 USD.
8. ✅ **Walidacja przejść stanów — WYKONANE 2026-07-13, poprawione po review:** pełna inwentaryzacja objęła `runs`, `research_runs`, `topics` i `research_source_candidates`; `research_sources` nie mają lifecycle statusu, a przyszłe `content_items`/`approvals`/`interactions` nie mają używanych helperów. Każdy istniejący statusowy UPDATE ma warunek `status IN (...)` (oraz `flow`, gdy wymagany), kontrolę `rowcount`, atomowy rollback i typowany `LifecycleTransitionError` albo zachowany `ResearchTopicIntegrityError`. `finish_run` nie przepisuje FAILED; wyłącznie jawny research resume używa osobnego helpera z pełną walidacją relacji i CAS. Race terminalizacji, resume i candidate claim są rzeczywiście równoległe na osobnych połączeniach SQLite z `Barrier`; **337 testów offline**, zero API i 0 USD.
9. ✅ **Realny run researchu — WYKONANE 2026-07-13:** świeży staged run ADR-022 wykonał A1 i 4×A2, a pierwsze B zakończyło się `stop_reason=max_tokens`, zachowując `SOURCES_COMPLETE`. Po osobnym, zatwierdzonym repair auditu właściciel zezwolił na dokładnie jeden resume B z `--synthesize-max-tokens 3000 --max-retries 0 --max-cost-usd 0.20`. Centralny PolicyEngine dopuścił projekcję 0,196300 USD. Jedyny call B zakończył się `end_turn`, 1904/2402 tokenów, zero search, kosztem 0,013914 USD. Run osiągnął `SUCCESS`, research `COMPLETE`, topic `USED`, karta #2 ma 4 VERIFIED, a łączny koszt 0,183964 USD pozostał poniżej capu. Karta jakościowo ma rekomendację `REJECT` (`THESIS_UNSUPPORTED`, `CLAIMS_WITHOUT_SOURCES`), co blokuje użycie jej do treści, ale nie narusza technicznego kryterium zakończenia Etapu 0. Nie wykonano retry, A1/A2, nowego runu ani Etapu 1.

- **Migracje:** 0006 ma własną transakcję; 0007 jest transakcyjna razem z wpisem `schema_migrations`, kontrolowana przez runner.
- **Testy:** resume cross-flow → ValueError (obie strony); `runs.cost_usd == sum(model_usage)` po każdej ścieżce staged (w tym B-failure); retry-failed z capem attempts; PARTIAL_EXHAUSTED terminalny; topic USED + `--force-re-research`; drugi attempt zablokowany gdy budżet wyczerpany między próbami; macierz dozwolonych przejść `mark_*`; parser topics z fence/uciętym JSON + księgowanie kosztu.
- **Kryteria akceptacji:** wszystkie dotychczasowe 102 testy + nowe zielone; run `9bbeb020` da się jawnie ponowić albo zamknąć jako PARTIAL_EXHAUSTED; `_detect_flow` nie istnieje.
- **Kryterium zakończenia etapu — SPEŁNIONE 2026-07-13:** istnieje realna Research Card #2 z `research_runs.status=COMPLETE`, `runs.status=SUCCESS`, 4 źródłami VERIFIED i kosztem 0,183964 ≤ 0,20 USD; potwierdzone po reopen bazy i opisane w `docs/RESEARCH_LOG.md`.
- **Ryzyka:** kolejna porażka realnego runu (mitygacja: retry-failed-candidates sprawia, że częściowa porażka przestaje być terminalna); backfill flow błędnie sklasyfikuje historyczny run (w bazie są 4 historyczne runy workflow research, z czego przed migracją tylko 2 miały rekord w `research_runs`; dwa znane runy single są mapowane po pełnym UUID, koncie i temacie, a pozostałe wyłącznie po jednoznacznych śladach strukturalnych).
- **Rollback:** 0006 przebudowuje `research_runs` i po migracji baza wymaga kodu świadomego obowiązkowego pola `flow`; sam powrót do poprzedniego commita nie jest kompatybilnym rollbackiem i spowoduje błędy `NOT NULL` przy nowych insertach starego kodu. Cofnięcie 0006 wymaga odtworzenia kopii bazy sprzed migracji albo osobnej migracji odwrotnej. 0007 jest addytywne: wcześniejszy kod ignoruje dodatkową kolumnę, a fizyczne usunięcie `attempts` wymaga osobnej migracji przebudowującej tabelę, nie resetu pliku bazy.
- **Nie wolno zmieniać:** legacy pipeline'ów (poza dopisaniem walidacji flow), trzech tabel źródeł, semantyki DRY_RUN, promptów researchu (działają — zmiany promptów tylko z osobnym uzasadnieniem), `.env`/cennika.

---

## Etap 1 — Fundament wykonawczy (scheduler, kolejka, workers)

- **Cel:** przejście z „człowiek uruchamia komendy" na „system sam wykonuje zakolejkowane zadania" — bez utraty ani zdublowania żadnego płatnego działania.
- **Uzasadnienie:** wszystko od Etapu 3 wzwyż (treści, publikacja, interakcje, metryki) wymaga zadań cyklicznych i odporności na restart; audyt wskazał brak locków i reapera jako warunek wstępny współbieżności.
- **Zależności:** Etap 0.
- **Pliki/moduły:** NOWY `app/scheduler/` (worker, lease, wybór jobów), migracja `0009_jobs_system_flags.sql`, `app/policies/policy_engine.py` (flagi z DB), `app/main.py` (subkomenda `worker`), `app/orchestrator/`.
- **Zadania:**
  0. **Blockery przed płatnymi workerami — GOTOWE OFFLINE, oczekują na niezależne review (2026-07-13):** (a) `AnthropicResearchClient` mapuje wyjątki SDK na typy domenowe; retry obejmuje wyłącznie timeout, SDK-network, 429 i 500/502/503/504, a 4xx/unknown/parse/truncation/validation są fail-closed; (b) staged B używa jednego `BEGIN IMMEDIATE`: karta, wszystkie źródła, B SUCCESS, COMPLETE, terminalny run i topic USED powstają albo nie powstaje nic. Jedyną publiczną ścieżką tego sukcesu jest `finalize_staged_research_with_card`; `finalize_research_success` i alias legacy odrzucają `staged`, a ogólny `finish_run` odmawia staged `SUCCESS`/`DRY_RUN`, zanim dotkną terminalnego lifecycle lub użyją przekazanego kosztu. Identyczne powtórzenie helpera jest no-opem wyłącznie po ponownej walidacji typed context: mode, marker force i snapshot resume/CAS; jego koszt jest kanoniczną sumą `model_usage`. `0008` utrwala force per run, a preflight działa przed B. **454 testy**, 0 USD, brak API. Bez scheduler/jobs/workerów/rezerwacji budżetowych.
  1. Tabela `jobs` (schemat: MASTER_ARCHITECTURE §4.2) + `system_flags`.
  2. Pętla workera: `SELECT ... WHERE status='QUEUED' AND earliest_run_at<=now ORDER BY priority, deadline` → lease (UPDATE warunkowy) → egzekucja przez orchestrator → DONE/FAILED; wygasłe lease wracają do QUEUED.
  3. Idempotencja: `idempotency_key UNIQUE`; joby „publikacyjne" (przyszłe) po wygaśnięciu lease → NEEDS_VERIFICATION, nigdy ponowne wykonanie.
  4. Retry/dead-letter: `attempts` + cap z configu; po przekroczeniu → FAILED z `last_error` (dead-letter = FAILED + raport w panelu/CLI); timeout jobu.
  5. Kill-switch/SAFE MODE runtime: PolicyEngine czyta `system_flags` przy KAŻDYM checku (P1-7).
  6. Reaper: `runs.status=RUNNING` starsze niż X bez żywego procesu → STOPPED(stale).
  7. Okna redakcyjne (godziny działań) z `growth_policy` → filtr `earliest_run_at`; `schedule_reason` przy każdym jobie.
- **Migracje:** 0009 (`jobs` + `system_flags`).
- **Testy:** dwa workery nie biorą tego samego joba (lease); wygasły lease wraca do QUEUED; kill-switch w DB zatrzymuje NASTĘPNY check w trwającej pętli A2; reaper nie ubija żywych runów; dead-letter po capie prób; pełne logowanie kosztów/błędów jobów.
- **Kryteria akceptacji/zakończenia:** research da się zakolejkować i wykonać przez workera (dry_run) z identycznym wynikiem jak z CLI; restart w połowie nie gubi ani nie dubluje żadnego etapu.
- **Ryzyka:** współbieżność SQLite (mitygacja: WAL z Etapu 0, jeden worker, lease); nadmierna komplikacja (mitygacja: ZERO zewnętrznych zależności — czysty SQLite).
- **Rollback:** worker to nowy, osobny punkt wejścia — wyłączenie go przywraca dokładnie dzisiejszy tryb ręczny.
- **Nie wolno zmieniać:** pipeline'ów researchu (worker je WOŁA, nie modyfikuje), kanonu kosztów, semantyki resume.

---

## Etap 2 — Research pipeline: dowód zamiast opinii (dokończenie)

- **Cel:** A2 czyta TREŚĆ źródła (nie „opinię o URL-u") i utrwala dowód per twierdzenie; kontrola sprzeczności; porządki po legacy.
- **Uzasadnienie:** P0-2c — bez fetch treści nazwa „extraction" jest na wyrost, a przyszły fact-audit artykułów (Etap 3) nie ma na czym pracować.
- **Zależności:** Etap 0 (pierwszy sukces staged na żywo); niezależny od Etapu 1 (może iść równolegle, ale nie przed Etapem 0).
- **Pliki/moduły:** NOWY `app/ports/fetch.py` (`FetchPort: fetch(url) -> FetchedDocument(text, status, retrieved_at)`), `app/research/anthropic_client.py` (A2 z narzędziem web_fetch API albo treścią z FetchPort w prompcie), `app/research/base.py`, migracja 0010 (`evidence_excerpt` per twierdzenie), `app/research/injection_guard.py`.
- **Zadania:**
  1. FetchPort + adapter (narzędzie web_fetch Anthropic API jako pierwszy wybór; lokalny fetcher jako drugi adapter później).
  2. A2: ekstrakcja Z TREŚCI; `evidence_excerpt` (krótki cytat + kontekst) per supported_claim; `VERIFIED` TYLKO gdy treść była faktycznie pobrana.
  3. Ujednolicenie semantyki `research_min_sources` (jedno znaczenie: liczba źródeł EXTRACTED+VERIFIED wymagana do B).
  4. Re-discovery jako jawna, osobna, capowana operacja („dodaj kandydatów do istniejącego runu") — domyka lukę „PARTIAL bez wyjścia mimo retry".
  5. Rozszerzenie injection guard (wektor rośnie wraz z fetch pełnych treści): wzorce wielojęzyczne, skan URL-i.
  6. Wygaszenie legacy: po ≥2 sukcesach staged na żywo — oznaczenie `run_research_pipeline`/`run_two_stage_research_pipeline` jako DEPRECATED (docstring + warning), plan konsolidacji tabel źródeł (osobna decyzja przed usunięciem czegokolwiek).
  7. Detekcja sprzeczności: pole `contradictions` + `contradictions_block` już istnieją — dodać test na realnym schemacie B i regułę „sprzeczność między evidence_excerpt dwóch źródeł → flaga do REVISE".
- **Migracje:** 0010 (evidence per claim).
- **Testy:** A2 bez fetch → wymuszone UNVERIFIED (już jest — rozszerzyć o ścieżkę fetch-failed); excerpt trafia do bazy i do karty; injection w pobranej treści neutralizowany; re-discovery nie dubluje kandydatów (dedup po URL).
- **Kryteria zakończenia:** realna karta, w której KAŻDE confirmed_claim ma źródło + evidence_excerpt z pobranej treści; koszt fetch w kanonie kosztów.
- **Ryzyka:** wzrost kosztu A2 (mitygacja: estymator rozszerzony o fetch, capy bez zmian); web_fetch może nie działać dla części stron (mitygacja: verification_status=FAILED, nie udawanie sukcesu).
- **Rollback:** flaga configu `research_fetch_enabled=false` przywraca dzisiejsze zachowanie A2.
- **Nie wolno zmieniać:** struktury A1/B, maszyny stanów (poza nową operacją re-discovery), bramek budżetowych.

---

## Etap 3 — Content pipeline (artykuły i Notes — BEZ publikacji)

- **Cel:** z karty PROCEED powstaje artykuł/Note przechodzący 3 deterministyczne audyty, zapisany jako `content_items.DRAFT→PENDING_APPROVAL`. Zero publikacji.
- **Uzasadnienie:** to pierwszy krok w stronę wartości użytkowej; tabela `content_items` czeka od migracji 0001.
- **Zależności:** Etap 0 + Etap 2 (fact-audit wymaga evidence_excerpt). Minimalna bramka Policy dla akcji CREATE_* — wdrażana TU, przed generatorami (zasada: bramka → generator).
- **Pliki/moduły:** NOWY `app/workflows/content/` (planner, writer, audits, rewriter), `app/policies/policy_engine.py` (check dla CREATE_ARTICLE/CREATE_NOTE: mode, limity tworzenia), repozytoria content_items, `instrukcja dla pisania artykulow/CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md` jako podręcznik stylu (wejście do promptów + reguł deterministycznych).
- **Zadania:** planner (artykuł vs Note wg score tematu — progi już w configu); writer (draft z karty, każde twierdzenie linkowane do claim+excerpt); audyt faktów (deterministyczny: każde twierdzenie w tekście musi mapować się na claim karty; twierdzenia bez pokrycia → obniżenie score/REVISE); audyt stylu (podręcznik + mierzalne reguły: długości, struktura, zakazane frazy); audyt growth (tytuł/lead/CTA wg polityk); pętla rewrite (max N z configu); duplicate detection vs istniejące content_items (ten sam mechanizm co dedup tematów); scoring końcowy + zapis evaluations.
- **Doprecyzowanie dokumentacyjne:** Article Brief, A1–A9, N1–N16 wyłącznie lokalnie/dry-run, Fact/Style/Growth Audit, SEO metadata i diversity memory są opisane jako PLANNED/PROPOSED w `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`; pełny materiał referencyjny jest w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md` (EXTERNAL STRATEGIC RESEARCH — NOT IMPLEMENTED). Negatywna bramka kończy się `SKIP` z reason code; nie publikuje ani nie tworzy automatycznej treści zastępczej.
- **Migracje:** 0011 (`evaluations`; ewentualne braki kolumn content_items).
- **Testy:** E2E dry-run topics→research→draft→audyty→PENDING_APPROVAL (pierwszy pełny test integracyjny przez wszystkie workflow); twierdzenie bez pokrycia w karcie → REVISE; duplikat treści wykryty; koszt każdego wywołania w kanonie; Policy blokuje CREATE_ARTICLE dla konta COMMENT_ONLY.
- **Kryteria zakończenia:** pełny łańcuch dry-run zielony; ≥1 realny artykuł-draft z audytami (za zgodą właściciela) oceniony przez człowieka jako publikowalny.
- **Ryzyka:** jakość stylu (mitygacja: podręcznik + iteracje z właścicielem na dry-runach); koszt generacji (mitygacja: te same bramki budżetowe i capy per-run).
- **Rollback:** moduł content jest addytywny; nieużywanie go przywraca stan Etapu 2.
- **Nie wolno zmieniać:** research pipeline'u, `DisabledBrowser` (publikacja nadal fizycznie niemożliwa).

---

## Etap 4 — Approval i autonomy (bramki przed publikacją)

- **Cel:** kompletny, egzekwowany system poziomów autonomii, akceptacji i SAFE MODE — ZANIM powstanie jakakolwiek możliwość publikacji.
- **Uzasadnienie:** publikacja bez działających bramek = niekontrolowane ryzyko reputacyjne; dziś `autonomy_level`/`AccountMode`/`AccountPolicy` to martwa konfiguracja (P1-10).
- **Zależności:** Etap 1 (system_flags, jobs), Etap 3 (jest co zatwierdzać).
- **Pliki/moduły:** `app/policies/policy_engine.py` (centralny `check(action, ctx)`), repozytoria approvals, NOWY `app/ui/` (panel FastAPI localhost: readonly stan + approvals + kill-switch), migracja 0012 (`autonomous_decisions`).
- **Zadania:** macierz akcja×poziom×tryb konta; egzekucja WSZYSTKICH limitów AccountPolicy (daily_comment_limit, daily_note_limit, weekly_article_limit, max_per_author_per_day, link_ratio); cooldowny; scoring gates (auto-approve TYLKO ≥ progu + log autonomous_decisions); SAFE MODE (progi błędów z configu, wejście auto, wyjście ręczne przez panel); approvals workflow w panelu; per-akcja cap kosztu w bibliotece (dokończenie P1-4).
- **Migracje:** 0012 (`autonomous_decisions`).
- **Testy:** każda kombinacja poziom×akcja z macierzy; limit dzienny blokuje N+1-szą akcję; SAFE MODE zatrzymuje trwającą pętlę przy następnym checku; auto-approve poniżej progu ODMAWIA; wszystkie decyzje autonomiczne logowane.
- **Kryteria zakończenia:** żadna akcja zewnętrzna nie może wykonać się z pominięciem `PolicyEngine.check` (test architektoniczny: orchestrator jest jedynym wołającym porty); panel pozwala zatwierdzić/odrzucić draft.
- **Ryzyka:** panel = pierwszy współbieżny czytelnik bazy (mitygacja: WAL już włączony w Etapie 0).
- **Rollback:** poziom autonomii w configu z powrotem na LEVEL_0/1; panel można wyłączyć.
- **Nie wolno zmieniać:** zasad ADR-018 (NO_REPLY, brak ujawniania) — one nie podlegają poziomom autonomii.

---

## Etap 5 — Publishing (Substack adapter)

- **Cel:** stabilna, idempotentna publikacja zatwierdzonych treści na Substacku z weryfikacją skutku.
- **Uzasadnienie:** pierwsza realna wartość zewnętrzna eksperymentu; wszystkie poprzednie etapy istnieją po to, żeby ten był bezpieczny.
- **Zależności:** Etapy 1+3+4 W CAŁOŚCI. Jawna zgoda właściciela + weryfikacja ToS Substacka (otwarty punkt z ADR-018) PRZED pierwszą publikacją.
- **Pliki/moduły:** NOWY `app/browser/` (adapter `PublicationChannelPort`/`BrowserPort` na Playwright), `app/workflows/publishing/`, tabela `screenshots` (wreszcie używana), `jobs` kind='browser'.
- **Zadania:** persistent context per konto + procedura pierwszego RĘCZNEGO logowania (MASTER §8.2); `is_logged_in` + stop-conditions; publish z `idempotency_key` + verify-before-publish + potwierdzenie odczytem stanu + screenshot; status UNCERTAIN bez auto-retry; recovery po częściowym błędzie (NEEDS_VERIFICATION po wygasłym lease); serializacja jobów browser (jeden Chromium); `max_consecutive_browser_errors` → SAFE MODE; drugi adapter `FileExportChannel` jako test szczelności kontraktu portu.
- **Migracje:** 0013 (kolumny weryfikacji publikacji w content_items/jobs, jeśli brakujące).
- **Testy:** dubel idempotency_key odrzucony; UNCERTAIN nigdy nie retry'owany automatycznie; crash po kliknięciu a przed potwierdzeniem → NEEDS_VERIFICATION; adapter plikowy przechodzi ten sam kontrakt testowy co Substack (contract tests portu).
- **Kryteria zakończenia:** ≥1 realna publikacja Note za akceptacją, potwierdzona odczytem stanu + screenshot; zero dubli w całej historii jobów.
- **Ryzyka:** zmiany UI Substacka (stop-conditions + selektory w jednym miejscu); ToS (weryfikacja przed startem, decyzja właściciela); ban/rate-limiting (limity z Etapu 4 + wolny start).
- **Rollback:** kill-switch/SAFE MODE; wyłączenie workera browser; treści pozostają w APPROVED.
- **Nie wolno zmieniać:** zasady „UNCERTAIN ≠ retry"; zakazu auto-loginu; braku zapisu haseł.

---

## Etap 6 — Interakcje (czytanie, komentarze, odpowiedzi)

> Doprecyzowanie: wybór i publiczna obsługa Notes oraz K1–K8 (komentarze), odpowiedzi i restacki należą do tego etapu, nie do Etapu 3. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` (PLANNED/PROPOSED); wartości, dane i koszty z raportu Fable pozostają zewnętrzną, mieszaną weryfikacyjnie propozycją.

- **Cel:** kontrolowane uczestnictwo w ekosystemie: czytanie, komentarze, odpowiedzi czytelnikom, subskrypcje — w limitach i z pełnym logiem.
- **Zależności:** Etap 5 (ta sama warstwa przeglądarki i te same bramki).
- **Pliki/moduły:** NOWY `app/workflows/interactions/` (discovery targetów, scoring, generacja, odpowiedzi), tabele `target_items`/`interactions` (wreszcie używane).
- **Zadania:** read-only discovery (feed/szukajki) → target_items ze score; scoring komentarza (specyfikacja przeniesiona ze starego planu D.5 do configu); generacja komentarza (bramka Policy → generator); odpowiedzi na komentarze pod własnymi treściami; scoring subskrypcji (D.6); NO_REPLY dla pytań o tożsamość (ADR-018 — deterministyczny klasyfikator + brak odpowiedzi w wątku); limity częstotliwości (daily_comment_limit, max_per_author_per_day, cooldowny per autor); polityki bezpieczeństwa: zero DM, zero inicjowania kontaktu, zero linków ponad link_ratio.
- **Testy:** limit per autor egzekwowany; identity-question → brak odpowiedzi + log; komentarz poniżej progu scoringu nie wychodzi z DRAFT.
- **Kryteria zakończenia:** tydzień działania na LEVEL_1/2 bez przekroczenia żadnego limitu i bez interwencji krytycznej.
- **Ryzyka:** odbiór społeczny komentarzy (wolumen minimalny na starcie, jakość > ilość); moderacja Substacka (cooldown po ukrytym komentarzu — stop-condition).
- **Rollback:** wyłączenie kind='interaction' w schedulerze.
- **Nie wolno zmieniać:** bezwzględnych zakazów z MASTER §7.2/§7.3.

---

## Etap 7 — Analytics i strategy loop

> Doprecyzowanie: metryki per content item, rozdzielone followers/free subscribers/paid subscribers/engaged subscribers, estymowana atrybucja (`is_estimated`), eksperymenty i weekly strategy należą do tego etapu. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` (PLANNED/PROPOSED); nie istnieje jeszcze kolektor ani wynik eksperymentu.

- **Cel:** system mierzy skutki własnych działań i koryguje strategię na podstawie danych, z pełnym logiem decyzji.
- **Zależności:** Etap 5 (są publikacje do mierzenia); Etap 6 wzbogaca dane, nie blokuje.
- **Pliki/moduły:** NOWY `app/metrics/` (kolektor → metrics_daily), NOWY `app/workflows/strategy/`, migracja `0014_strategy_decisions.sql`.
- **Zadania:** kolektor metryk (read-only Playwright; estymacje oznaczane `is_estimated`); attribution (metryka↔treść po external_url/dacie); tygodniowy raport (docs/weekly-reports/ — automatyczny szkic); ocena skuteczności vs funkcja celu wzrostu (wagi z growth_policy, ADR-002); strategy engine: propozycje korekt parametrów treści/harmonogramu → `strategy_decisions` (problem→dane→decyzja→oczekiwany efekt→wynik po fakcie); korekty wchodzą przez config, NIGDY w politykę bezpieczeństwa; na LEVEL<3 zmiany strategii wymagają akceptacji.
- **Testy:** attribution deterministyczna na danych syntetycznych; strategia nie może zmienić limitów bezpieczeństwa (test negatywny); każdy wpis strategii kompletny.
- **Migracje:** 0014 (`strategy_decisions`).
- **Kryteria zakończenia:** ≥2 cykle tygodniowe z raportem i ≥1 udokumentowaną, zamkniętą pętlą decyzja→efekt.
- **Ryzyka:** za mało danych do wniosków (mitygacja: decyzje oznaczane confidence, minimalne progi próby).
- **Rollback:** strategia w trybie „proponuj, nie stosuj".

---

## Etap 8 — Productization readiness (self-hosted)

- **Cel:** projekt instalowalny przez kogoś innego niż autor: konfiguracja wielu publikacji, Docker, VPS, diagnostyka.
- **Zależności:** Etapy 1–7 stabilne (≥1 miesiąc działania).
- **Zadania:** aktywacja multi-konta (izolacja już testowana — ADR-006/007); Dockerfile (python:3.12-slim + playwright chromium; wolumeny `/app/data`, `/app/config`; profile przeglądarki w wolumenie); `.env` → zmienne środowiskowe kontenera (podpięcie `EnvSecretStore` zamiast rozproszonego `os.getenv`); runtime-writes poza repo (COSTS.csv/RESEARCH_LOG → `data/`, eksport do docs osobnym krokiem — P2-11); jawny krok `migrate` w deployu (P2-10); backup SQLite (`VACUUM INTO` przed oknami publikacji); healthcheck + diagnostyka (`doctor` CLI); eksport/import konfiguracji publikacji; dokument instalacji na VPS; separacja danych klientów = izolacja per instancja (jedna instalacja = jeden właściciel; multi-tenant POZA zakresem).
- **Kryteria zakończenia:** czysta instalacja z README na świeżym VPS kończy się działającym dry-runem w <30 minut.
- **Ryzyka:** dryf konfiguracji lokalna↔kontener (mitygacja: jeden loader konfiguracji, testy na obu ścieżkach).
- **Rollback:** tryb lokalny pozostaje pierwszorzędny; Docker to opakowanie, nie zależność.

---

## AKTUALNY ETAP: **Etap 1** (rozpoczęty wyłącznie od blockera kontraktu providera)

Etap 0 spełnił kryterium zakończenia 2026-07-13. Wdrożono offline pierwszy blocker przed płatnymi workerami: typed Anthropic errors i bezpieczny retry (ADR-029) oraz poprawioną atomową finalizację staged B (ADR-030/031), pozostawione do niezależnego review. Publiczne finalizery legacy nie mogą już finalizować `staged`; robi to wyłącznie atomowy helper z kosztem z `model_usage`. Scheduler, kolejka, workery, migracja jobs/system_flags (następna numeracja: `0009`) i rezerwacje budżetowe nie zostały rozpoczęte i wymagają osobnych zadań właściciela; `0008` jest już zarezerwowane dla trwałego markera force staged runu.
