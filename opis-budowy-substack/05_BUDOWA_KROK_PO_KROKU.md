# 05 — BUDOWA KROK PO KROKU

> **Stan bieżący LA-02 (2026-07-17):** niezależny review wydał `APPROVE WITH MINOR/P2`; root cause `PROCESSES_PRESENT` jest zamknięty, a checkpoint obejmuje 1174/1174 offline i exact-once `284+284+298+308`. P2-2 false STOP pozostaje udokumentowaną obserwacją. Provider request nie został wykonany, job nadal `QUEUED/attempts=0`, gate `False`, flagi fail-closed, a druga próba nie jest autoryzowana. Etap 1 pozostaje otwarty do nowej decyzji właściciela po standalone quiescence check z tego samego launchera.

> **Aktualizacja LA-01-R1 (2026-07-17):** pierwsza LA-01 została odrzucona jako `REJECTED — MAJOR`. Naprawa zmieniła definicję sukcesu: cena, sesja, job, request, attempt i worker fence tworzą jeden zamrożony kontrakt; kanoniczny enqueue zapisuje go przez ten sam deterministyczny helper, z którego korzysta wrapper bez prawa tworzenia realnego joba. Po wykonaniu nowe połączenie musi zobaczyć jeden usage, zgodny settlement i terminalny lifecycle. Sanitizowany raport jest fsyncowany przed usunięciem markera, a `REQUEST_STARTED` pozostaje możliwym nieznanym skutkiem bez retry. Niezależny review zatwierdził falę jako `APPROVE WITH MINOR/P2`; jedyny open P2 sanitizera jest nieblokującą rekomendacją. Dowód: **1151/1151 offline**, exact-once **275+282+291+303**. Produkcja ma schema 0014 i 14 migracji; realny live acceptance nie został wykonany, koszt 0 USD, Etap 1 pozostaje otwarty do acceptance.

> **Aktualizacja finalnego preflightu (2026-07-17):** właściciel podał konkretny cennik i twardy cap. Kod zaakceptował profil `Decimal` i policzył `0.070000 USD` projected oraz `0.105000 USD` pessimistic przy capie `0.120000 USD`. System nadal odmówił statusu live `READY`: kanoniczny wrapper wymaga joba utrwalonego przed startem, a zakaz enqueue uniemożliwia poznanie finalnego post-enqueue SHA bazy. To celowa granica dowodu, nie awaria providera. Nie było API, sieci ani kosztu.

> **Aktualizacja jedynej próby live (2026-07-17):** po osobnym enqueue i zamrożeniu SHA właściciel pozwolił uruchomić wrapper dokładnie raz. Wszystkie jawne kontrole przeszły, ale wewnętrzny preflight odmówił przed providerem. Nie powstał attempt ani rachunek; raport został zapisany, marker usunięty, flags i gate zamknięte. Próby nie powtórzono. To wynik `LIVE ACCEPTANCE FAILED — INVARIANT BREACH`, nie częściowy sukces.

> **Krok `W1A-R4-01` (2026-07-16):** po czwartym `REJECTED — MAJOR` odtworzyliśmy prawdziwym `Worker.run_once` stan `job=FAILED` + `attempt=REQUEST_STARTED`. Zmapowaliśmy wszystkie terminalne ścieżki i zastąpiliśmy workerowy fallback centralną decyzją StoragePort: bez attemptu normalne `FAILED`, z `RESERVED`/`REQUEST_STARTED` widoczne reconciliation, zachowana rezerwacja i zero drugiej próby. Triggery SQLite zabezpieczają job/run/research_run. Dowód: +29 testów, **1036/1036**, partycje 248+253+267+268, race ×30, krytyczne pliki i QA ×10. WAVE pozostaje otwarta i czeka na niezależny review; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

### [2026-07-16] Etap WAVE 1A — systemowa naprawa granicy failure→reconciliation
- **Co chcieliśmy osiągnąć:** usunąć stan, w którym obsłużony lokalny błąd chowa rozpoczętą próbę providera poza operatorem, a budżet pozostaje zablokowany.
- **Co zbudowaliśmy:** atomową operację `fail_or_escalate_job_research_execution`, jawne outcomes, dwa powody eskalacji, spójny Worker/pipeline oraz lifecycle guardy w migracji 0014.
- **Jak to działa:** durable attempt decyduje o wyniku; `RESERVED`/`REQUEST_STARTED` nigdy nie są terminalizowane razem z lifecycle, tylko trafiają do `NEEDS_RECONCILIATION`.
- **Jak przetestowane:** prawdziwy Worker z fake dispatcherem, temp DB, błędy SQLite/runtime/OS/heartbeat, reopen/recovery/reaper/resolver/budżet/raw SQL i concurrency; pełny suite 1036.
- **Wynik:** kandydat do niezależnego review, bez sieci, providera i kosztu.
- **Co jeszcze nie działa:** niezależny reviewer nie zatwierdził WAVE; P2-1 i granica P2-2 pozostają jawne.
- **Następny krok:** niezależny re-review; WAVE otwarta, Etap 1 zablokowany.

> **Checkpoint WAVE 0B:** `APPROVED WITH P2 — READY FOR CHECKPOINT`, na podstawie 894 testów offline i partycji 213/224/231/226. Rzeczywisty inwentarz wynosi 72 wpisy; Etap 1 `BLOCKED`, live API `ZABRONIONE`, bez `CLOSED` przed commitem.
>
> **Aktualizacja WAVE 1A (2026-07-15):** powyższy checkpoint WAVE 0B jest historyczny. WAVE 0B = `CLOSED — APPROVED WITH P2`; WAVE 1A = `CANDIDATE` po naprawie odrzucenia `REJECTED — MAJOR` (append-only `reconciliation_events`, pełna tożsamość usage, wyłączna własność Research Card, brak dead-endu `MANUAL`, spójność ledger↔cache, CLI preview/confirm z version tokenem). **980 testów offline, 14 migracji**; historyczne 894/13 i `READY FOR CHECKPOINT` są historyczne. Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## Cel pliku

> **Aktualizacja WAVE 1A:** WAVE 0B = `CLOSED — APPROVED WITH P2`; WAVE 1A pozostaje `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW` po `W1A-R4-01`, nie zamknięciem WAVE ani Etapu 1. 14 migracji, **1036 testów offline**, live API `ZABRONIONE`.
>
> **Krok `W1A-VERIFY-01` (2026-07-15):** resolver `EXECUTION_FAILED` domyka teraz run zatrzymany przez maintenance-reapera (`STOPPED → FAILED`) w tej samej atomowej transakcji, co reszta rozstrzygnięcia — bez wskrzeszania runu, `DONE` ani drugiej próby. Dodano 7 deterministycznych testów wyścigu resolver↔reaper; suite 948 → **955**.

## 2026-07-15 — WAVE 1A: ręczne domknięcie niepewnej próby

Najpierw sprawdziliśmy, gdzie po timeoutie zostaje rezerwacja: attempt `NEEDS_RECONCILIATION`, job `NEEDS_VERIFICATION`, a worker nie ma prawa wrócić do calla. Następnie dodaliśmy migrację 0014 i jedną transakcję operatorską. Testy psują ją po usage, attempt, runie, research_runie i jobie; po reopen nie zostaje pół rozstrzygnięcia. CLI najpierw tylko pokazuje plan, a zapis następuje wyłącznie z `--confirm`. Żaden z tych kroków nie uruchamia SDK, nie tworzy Research Card i nie robi attemptu #2.
Pełna **chronologia** budowy. Po każdym większym etapie: co chcieliśmy osiągnąć, co zbudowaliśmy, jakie pliki powstały, jak to działa, jak przetestowaliśmy, jaki był wynik, co jeszcze nie działa, jaki jest następny krok. **Nie zapisujemy tylko efektu końcowego — zachowujemy przebieg.**

## Szablon wpisu
```markdown
### [YYYY-MM-DD HH:MM] Etap X — <nazwa>
- **Co chcieliśmy osiągnąć:**
- **Co zbudowaliśmy:**
- **Pliki, które powstały:**
- **Jak to działa:**
- **Jak przetestowane:**
- **Wynik:**
- **Co jeszcze nie działa:**
- **Następny krok:**
```

---

### [2026-07-11 16:35] Etap „0-dok" — Audyt + struktura dokumentacji
- **Co chcieliśmy osiągnąć:** ustalić stan wyjściowy i założyć pełną dokumentację, zanim powstanie kod.
- **Co zbudowaliśmy:** audyt trzech dokumentów źródłowych + `ARCHITECTURE.md`; `docs/IMPLEMENTATION_PLAN.md` (plan MVP z modelami danych, schematem bazy, portami); komplet logów `docs/` (BUILD_LOG, DECISIONS, ERRORS_AND_FAILURES, HUMAN_INTERVENTIONS, ARTICLE_EVIDENCE, RESEARCH_LOG, METRICS_LOG, SCREENSHOT_INDEX, COSTS.csv, ARCHITECTURE_EVOLUTION, RELEASE_TIMELINE) + `architecture/SUBSTACK_INTEGRATION.md`.
- **Pliki, które powstały:** `docs/**` (kilkanaście plików + szablony).
- **Jak to działa:** dokumentacja opisowa; źródłem prawdy technicznej jest `docs/`.
- **Jak przetestowane:** przegląd spójności z założeniami; zestawienie rozbieżności między dokumentami (załącznik w planie).
- **Wynik:** kompletna struktura dokumentacji; architektura integracji z **istniejącym** kontem opisana; zero kodu, zero publikacji, 0.00 USD.
- **Co jeszcze nie działa:** żaden kod (`app/` nie istniał).
- **Następny krok:** czekać na akceptację właściciela → Etap 0.

### [2026-07-11 18:20] Etap 0 + Walking skeleton (V1)
- **Co chcieliśmy osiągnąć:** bezpieczny szkielet repo + najmniejszy działający pionowy przekrój (generacja i ocena tematów, Policy Engine, SQLite, koszty), w `dry_run`, bez akcji na Substacku.
- **Co zbudowaliśmy:**
  - **Etap 0 (higiena):** `.gitignore`, `.env.example`, `pyproject.toml`; struktura `app/` (core, llm, policies, workflows, storage, ports, orchestrator), `tests/`, `scripts/`, `data/`; stuby portów (Scheduler/Browser wyłączone; SecretStore/FileStore/Notification/Storage działające). Bez Playwrighta i publikacji.
  - **Walking skeleton:** konfiguracja z `.env` + `config/*.yaml`, migracja `0001_init.sql`, `AnthropicClient` (leniwy import) + `FakeLLMClient` (dry_run), `ModelRouter` (modele z `.env`), `UsageTracker` (koszt → `model_usage` + `COSTS.csv`), `PolicyEngine` (kill-switch, aktywność, budżet z priorytetem miesięcznym, progi), przepływ `topics/discover`, CLI `python -m app.main run-topics`.
- **Pliki, które powstały:** `.gitignore`, `.env.example`, `pyproject.toml`, `app/**` (22 pliki), `tests/**` (6 plików), `scripts/**`, `data/.gitkeep`; aktualizacje `config/growth_policy.example.yaml`, `docs/COSTS.csv`, `docs/CODE_EXAMPLES.md`, `docs/ARCHITECTURE_EVOLUTION.md`, `docs/DECISIONS.md` (ADR-012/013).
- **Jak to działa:** `run-topics` generuje i ocenia tematy, zapisuje do SQLite, liczy szacowany koszt; w dry_run używa klienta zastępczego (bez sieci/kosztu).
- **Jak przetestowane:** `pytest` = **16 passed**. `run-topics --count 6` → 6 tematów (SELECTED=3, SCORED=2, REJECTED=1), koszt ~0.0042 USD (szacunek dry_run), `real_cost_month=0`.
- **Wynik:** Anthropic jako silnik + liczenie kosztów + Policy działają end-to-end w trybie próbnym.
- **Co jeszcze nie działa:** research, artykuły/Notes, komentarze, panel, Playwright/publikacja, realne API (dostępne przez `--real`, świadomie nieużyte); brak deduplikacji między uruchomieniami.
- **Następny krok:** **STOP przed research pipeline** — czekać na potwierdzenie.

### [2026-07-11 19:40] Etap 1A (deduplikacja) + Etap 1B (Research Pipeline) (V2)
- **Co chcieliśmy osiągnąć:** (1A) nie zapisywać duplikatów tematów; (1B) pełny pipeline researchu SELECTED → Research Card z bramką jakości, ochroną przed prompt injection i testami. Bez płatnych wywołań.
- **Co zbudowaliśmy:**
  - **1A:** `TopicDeduplicator` (znormalizowany tytuł + Jaccard/SequenceMatcher, próg z configu). Duplikat → `status=DUPLICATE` + `duplicate_of` + `rejection_reason`; dedup per `account_id` i wewnątrz batcha. Migracja `0002`.
  - **1B:** `app/research/` (base, injection_guard, validation, fake_client, anthropic_client) + `app/workflows/research/` (pipeline, docs_writer). Research Card z pełnym zestawem pól; źródła z metadanymi i statusem weryfikacji. Bramka jakości (min. 3 źródła, teza poparta, twierdzenia ze źródłami, progi confidence/jakości, brak wymogu osobistego doświadczenia, brak nieusuwalnych sprzeczności). Guard iniekcji. Migracja `0003`. Auto-wpis do `RESEARCH_LOG.md` i `COSTS.csv`.
  - Klienci: `FakeResearchClient` (scenariusze), `AnthropicResearchClient` (retry z limitem, timeout, parsowanie JSON, tracking web_search) — testowalny bez sieci przez wstrzykiwany caller. **Realne API nieuruchomione.**
- **Pliki, które powstały:** `app/workflows/topics/dedup.py`, `app/research/**`, `app/workflows/research/**`, migracje `0002`/`0003`, `models.py`, `config.py`, `storage/repositories.py`, `ports/storage.py`, `workflows/topics/discover.py`, `orchestrator/runner.py`, `main.py`; testy: `test_dedup.py`, `test_topics_dedup_workflow.py`, `test_injection_guard.py`, `test_research_validation.py`, `test_research_anthropic_client.py`, `test_research_pipeline.py`.
- **Jak to działa:** `run-research` (dry_run) bierze temat SELECTED, buduje kartę, sprawdza budżet przed web search, neutralizuje ewentualne iniekcje, waliduje jakość, zapisuje do bazy i dopisuje do logów.
- **Jak przetestowane:** `pytest` = **44 passed**. `run-topics` (powtórnie) → DUPLICATE=6. `run-research` (dry_run) → Research Card PROCEED, 3 źródła VERIFIED, injection flags 0, koszt ~0.0492 USD (szacunek).
- **Wynik:** działający, przetestowany research pipeline w trybie próbnym; pełna ścieżka temat → karta researchu z audytem jakości.
- **Co jeszcze nie działa:** realne wywołanie Anthropic, generator artykułów/Notes/komentarzy, panel FastAPI, Playwright/publikacja.
- **Następny krok:** **STOP przed pierwszym płatnym wywołaniem Anthropic** — czekać na zgodę.

### [2026-07-11 19:09 UTC] Etap 1C — pierwsze realne wywołanie Anthropic (nieudane) + naprawa buga kosztowego
- **Co chcieliśmy osiągnąć:** jedno, ściśle ograniczone, realne (płatne) wywołanie research pipeline dla tematu „What really happens to your suitcase after check-in" — zatwierdzone przez właściciela z twardymi limitami: cap kosztu 0.30 USD, max 6 web searchy, max 1 retry (tylko błąd techniczny), bez publikacji/artykułu/Playwrighta.
- **Co zbudowaliśmy:**
  - Dopisaliśmy brakujące zabezpieczenia, których kod jeszcze nie miał: twardy cap liczby web searchy (`max_uses` w wywołaniu API) i pesymistyczny sufit kosztu sprawdzany PRZED wywołaniem.
  - Utworzyliśmy izolowane środowisko `.venv` tylko dla tego projektu (globalny pakiet `anthropic` był współdzielony z innymi narzędziami na komputerze i miał za starą wersję — nie ruszaliśmy go, żeby nic nie zepsuć poza projektem).
  - Napisaliśmy `scripts/run_capped_research.py` — skrypt, który sprawdza klucz/budżet/limity PRZED jakimkolwiek wywołaniem i przerywa, jeśli coś przekracza limity.
- **Jakie pliki powstały:** `scripts/run_capped_research.py`, zmiany w `app/research/anthropic_client.py`, `app/research/base.py`, `app/workflows/research/pipeline.py`, `app/workflows/research/docs_writer.py`, `.venv/` (lokalne, poza repo).
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` sekcja 3.
- **Jak zostało przetestowane:** dwie „próby generalne" bez wydawania pieniędzy (zły numer tematu, za niski limit kosztu) — obie poprawnie zatrzymały się przed wywołaniem API. Potem jedno realne wywołanie.
- **Jaki był wynik:** wywołanie **dotarło** do modelu i użyło wyszukiwarki, ale odpowiedź została ucięta w połowie — karta researchu nie powstała (REJECT). Znaleźliśmy przy tym osobny, poważniejszy problem: koszt tego nieudanego, ale realnego wywołania **nie zapisywał się** w naszej księgowości (wyglądało jakby kosztowało 0.00 USD). Naprawiliśmy to od razu i dopisaliśmy 3 testy pilnujące, żeby się nie powtórzyło — **47 testów zielonych** (było 44).
- **Co jeszcze nie działa:** nie mamy jeszcze ani jednej udanej, realnej Research Card. W momencie zamknięcia tego etapu dokładny koszt tej jednej próby nie był znany co do centa (bug istniał w momencie tego runu) — była tylko górna granica (~0.095 USD) i zalecenie sprawdzenia w panelu Anthropic. **[Zaktualizowano w Etapie 1D poniżej: realny koszt = 0.25 USD.]**
- **Następny krok:** wykonany — patrz Etap 1D.

### [2026-07-11] Etap 1D — korekta realnego kosztu + naprawa estymatora + dwuetapowy research
- **Co chcieliśmy osiągnąć:** właściciel sprawdził w panelu Anthropic dokładny koszt Etapu 1C (0,25 USD — znacznie więcej niż nasz szacunek 0,095 USD) i polecił: wpisać wszędzie realną kwotę, opisać to jako nowy błąd, naprawić sposób szacowania kosztu PRZED kolejnym płatnym wywołaniem, podzielić research na dwa mniejsze kroki — i **nie** wykonywać jeszcze drugiej płatnej próby, tylko pokazać nowe wyliczenia.
- **Co zbudowaliśmy:**
  - Wpisaliśmy realny koszt (0,25 USD) do bazy i wszystkich dokumentów, zastępując „0,00 USD" i „nieznany, górna granica ≈0,095 USD".
  - Zbudowaliśmy **nowy sposób liczenia kosztu z wyprzedzeniem** — zamiast zgadywać jedną, stałą liczbę „na oko", nowy sposób rośnie wraz z liczbą planowanych wyszukiwań (bo to one, jak się okazało, najbardziej napędzają koszt) i ma wbudowany wymagany margines bezpieczeństwa (minimum 50% zapasu).
  - **Podzieliliśmy research na dwa mniejsze kroki** zamiast jednego dużego: krok 1 tylko szuka i zbiera fakty (i jeśli znajdzie za mało źródeł, **kończymy tam, nie płacąc za krok 2**); krok 2 tylko analizuje to, co już zebrano — bez ponownego szukania w internecie, więc jego koszt jest dużo łatwiejszy do przewidzenia.
  - Zaktualizowaliśmy skrypt do uruchamiania researchu — teraz domyślnie używa dwóch kroków i ma tryb „pokaż mi tylko wyliczenie, nic nie uruchamiaj" (`--estimate-only`), żeby dało się sprawdzić koszt bez wydawania pieniędzy.
- **Jakie pliki powstały:** `app/research/cost_estimator.py` (nowy), zmiany w `app/research/base.py`, `app/research/anthropic_client.py`, `app/research/fake_client.py`, `app/workflows/research/pipeline.py`, przepisany `scripts/run_capped_research.py`; nowe testy: `tests/test_cost_estimator.py`, `tests/test_research_two_stage_pipeline.py`.
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` sekcja 3 (zaktualizowana).
- **Jak zostało przetestowane:** wyłącznie lokalnie, zero wywołań do prawdziwego API. Uruchomiliśmy `--estimate-only` i sprawdziliśmy, że pokazuje liczby bez łączenia się z internetem. Dopisaliśmy testy sprawdzające, że nowy sposób liczenia NIE popełniłby tego samego błędu co poprzedni (dla tych samych ustawień co nieudana próba, nowy szacunek wychodzi wyżej niż realny koszt — czyli byłby bezpieczny).
- **Jaki był wynik:** **63 testy zielone** (było 47). Nowe wyliczenie dla dwóch kroków: krok 1 (zbieranie) ≈ 0,36 USD, krok 2 (analiza) ≈ 0,02 USD, razem **≈ 0,38 USD** — to o ok. 31% mniej niż przeliczony na nowo szacunek dla starego, jednokrokowego podejścia (≈ 0,55 USD).
- **Co jeszcze nie działa:** nowy, dwuetapowy sposób nie został jeszcze wypróbowany na prawdziwym API — czekamy na osobną zgodę właściciela.
- **Następny krok:** decyzja właściciela — czy zatwierdzić kolejną, realną próbę w nowym, dwuetapowym trybie (proponowany limit ~0,45 USD).

### [2026-07-11] Etap 1E — doprecyzowanie celu: pełna autonomia jako stan docelowy (ADR-017)
- **Co chcieliśmy osiągnąć:** właściciel zauważył, że dokumentacja zaczęła sugerować, jakby ręczna akceptacja każdej akcji była stanem docelowym systemu — to była nieporozumienie. Trzeba było to skorygować w całej dokumentacji, zanim ruszymy dalej z kodem.
- **Co zbudowaliśmy:** **żadnego kodu — to zadanie było wyłącznie dokumentacyjne**, zgodnie z jawnym poleceniem właściciela. Wykonaliśmy: audyt wszystkich miejsc sugerujących „akceptacja na stałe"; pełną specyfikację czterech poziomów autonomii (LEVEL_0 dry_run → LEVEL_1 kontrolowane testy → LEVEL_2 pierwszy realny poziom autonomiczny → LEVEL_3 pełna autonomia operacyjna); diagram przejść; mierzalne warunki przejścia między poziomami; plan modułu Autonomous Interaction Engine (czytanie, ocena, komentowanie, lajkowanie, subskrybowanie innych publikacji); scoring komentarzy i subskrypcji; specyfikację SAFE MODE (automatyczne wyhamowanie przy sygnałach problemu); listę nowych tabel SQLite, opcji konfiguracyjnych, testów i wpływu na budżet.
- **Ważne zastrzeżenie (poprawione w Etapie 1F poniżej):** w tym etapie błędnie zapisaliśmy, że publikacja ma jawnie ujawniać AI-autorstwo na każdym poziomie. Właściciel to skorygował tego samego dnia, później — patrz Etap 1F. Zakaz wiadomości prywatnych i inicjowania kontaktu z innymi autorami pozostaje bezwzględny (to się nie zmieniło).
- **Jakie pliki powstały/zmieniły się:** `docs/IMPLEMENTATION_PLAN.md` (nowa CZĘŚĆ D, poprawiona macierz akceptacji §B.8), `docs/DECISIONS.md` (ADR-017, doprecyzowanie ADR-004), `ARCHITECTURE.md` §4, `docs/ARCHITECTURE_EVOLUTION.md` (wpis meta), oraz komplet plików `opis-budowy-substack/` z tej listy.
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` punkt 12.
- **Jak zostało przetestowane:** nie dotyczy — praca czysto dokumentacyjna/planistyczna.
- **Jaki był wynik:** spójna, jednoznaczna definicja celu w całej dokumentacji; gotowy plan do wdrożenia (jeszcze nie zaimplementowany).
- **Co jeszcze nie działa:** nic z CZĘŚCI D nie jest zbudowane — to plan, nie kod. Playwright nadal wyłączony, żadne wywołanie API nie zostało wykonane w ramach tego zadania.
- **Następny krok:** czekamy na zgodę właściciela na rozpoczęcie implementacji (kolejność zależy od decyzji właściciela — najpierw prawdopodobnie generator artykułów/Notes/komentarzy offline, LEVEL_0→1, zanim zajmiemy się mechaniką LEVEL_2).

### [2026-07-11] Etap 1F — korekta: BRAK publicznego ujawniania AI (ADR-018)
- **Co chcieliśmy osiągnąć:** Etap 1E błędnie założył, że publikacja będzie jawnie ujawniać AI-autorstwo w bio i materiałach na każdym poziomie autonomii. Właściciel to skorygował tego samego dnia, później: konto publiczne „Nothing Is Accidental" ma działać jako **anonimowa marka redakcyjna**, bez proaktywnego ujawniania automatyzacji — ale też bez podszywania się pod konkretną, fikcyjną osobę.
- **Co zbudowaliśmy:** **żadnego kodu — ponownie wyłącznie dokumentacja**, zgodnie z jawnym poleceniem właściciela. Wykonaliśmy dwuetapowo: (1) pełny audyt wszystkich publicznych wzmianek o AI/bocie/automatyzacji w projekcie, pokazany właścicielowi PRZED wprowadzeniem zmian; (2) po zatwierdzeniu — poprawki w plikach specyfikacji i kronice, nowy ADR-018, pełna specyfikacja zasady „IDENTITY_DISCLOSURE_QUESTION / NO_REPLY" (co robi agent, gdy ktoś wprost zapyta „czy jesteś botem?" — nie odpowiada, nie potwierdza, **nie kłamie**, tylko loguje prywatnie), tabela „Powierzchnia / Ujawnienie AI", oraz jawny zakaz technicznego maskowania automatyzacji (bez zmiany fingerprintu, bez obchodzenia CAPTCHA, bez rotacji kont) — nieregularny rytm publikacji to wyłącznie higiena redakcyjna, nie unikanie wykrycia.
- **Jakie pliki powstały/zmieniły się:** `docs/DECISIONS.md` (ADR-018), `docs/IMPLEMENTATION_PLAN.md` (poprawka reguł twardych + nowa sekcja §D.5a + §D.4a), `ARCHITECTURE.md` §4, `opis-budowy-substack/02_POMYSL_NA_PUBLIKACJE.md` (usunięcie proponowanego bio z ujawnieniem AI) oraz komplet plików `opis-budowy-substack/` z tej listy (ten plik, 00, 01, 03, 04, 06, 16). Do dwóch historycznych dokumentów źródłowych (`zalozenia projektu/...`, `zalzoewnia dla agenta/...`) dodano notatkę SUPERSEDED, bez zmiany ich treści.
- **Jak to działa:** patrz `01_CEL_I_ZALOZENIA.md` (nowa sekcja „Powierzchnie i ujawnienie AI") i `04_JAK_DZIALA_AGENT.md` punkt 12 (zaktualizowany).
- **Jak zostało przetestowane:** nie dotyczy — praca czysto dokumentacyjna. Pełny re-audyt całego projektu wykonany na końcu (lista trafień z etykietami PRIVATE_CURRENT/HISTORICAL_SUPERSEDED/PUBLIC_ERROR) — potwierdza brak pozostałych publicznych ujawnień.
- **Jaki był wynik:** bio i cała gotowa treść publiczna nie zawierają żadnej wzmianki o AI; jedyne obowiązujące bio to istniejące, już opublikowane, bez zmian. Cała prawda o automatyzacji pozostaje w dokumentacji prywatnej.
- **Co jeszcze nie działa:** nic z tego nie jest zaimplementowane w kodzie — `IDENTITY_DISCLOSURE_QUESTION`/`NO_REPLY` i zakaz maskowania technicznego to na razie specyfikacja, nie działający mechanizm.
- **Następny krok:** czekamy na zgodę właściciela na rozpoczęcie implementacji.

### [2026-07-12] Etap 1G — stabilizacja Research Pipeline: pełna wznawialność (ADR-019)
- **Co chcieliśmy osiągnąć:** właściciel polecił ustabilizować dwuetapowy research PRZED przejściem do generatora artykułów/Notes/komentarzy/Playwrighta: nigdy nie tracić wyników wyszukiwania przy błędzie drugiego kroku, poprawnie śledzić realny koszt, zapisywać wyniki częściowe trwale, umożliwić wznowienie wyłącznie drugiego kroku bez powtarzania wyszukiwania. Bez płatnego wywołania API.
- **Co zbudowaliśmy:**
  - Nową część bazy danych: „karta stanu" researchu (`research_runs` — status: czeka / źródła zebrane / częściowy / gotowy / nieudany), trwały zapis znalezionych źródeł (`research_sources`), log każdej próby każdego kroku (`research_stage_results`).
  - Zmianę w pierwszym kroku: wyniki wyszukiwania są teraz zapisywane na trwałe **natychmiast po sukcesie**, w jednej nierozdzielnej operacji razem ze zmianą statusu — zanim program w ogóle sprawdzi, czy źródeł jest wystarczająco dużo.
  - Nową funkcję **wznów wyłącznie krok drugi** — czyta źródła z bazy, nigdy nie woła wyszukiwarki ponownie; jeśli źródeł nadal za mało, odmawia bez łączenia się z API (bo krok drugi i tak nie szuka, więc nie naprawi tego problemu).
  - Zaktualizowaliśmy skrypt uruchamiający research o nową opcję „wznów ten konkretny research po jego identyfikatorze".
  - Napisaliśmy 10 nowych testów, w tym jeden, który udowadnia odporność na prawdziwy restart programu: symuluje ponowne uruchomienie od zera (zupełnie nowe obiekty w pamięci) i sprawdza, że wznowienie mimo to działa poprawnie, bazując wyłącznie na tym, co zapisane w bazie.
- **Jakie pliki powstały:** nowa migracja bazy `0004_research_resumability.sql`, zmiany w `app/models.py`, `app/storage/repositories.py`, `app/ports/storage.py`, `app/workflows/research/pipeline.py` (nowa funkcja `resume_research_stage_b`), `scripts/run_capped_research.py` (nowa opcja `--resume`), nowy plik testów `tests/test_research_resumability.py`, `docs/DECISIONS.md` (ADR-019), `docs/IMPLEMENTATION_PLAN.md` (nowa CZĘŚĆ E).
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` sekcja 3 (zaktualizowana, akapit „stabilizacja: wyniki wyszukiwania nigdy już nie wiszą tylko w pamięci").
- **Jak zostało przetestowane:** wyłącznie na klientach zastępczych (bez sieci) + migracja sprawdzona lokalnie. Scenariusze: poprawny krok 1, poprawny krok 2, ucięta odpowiedź w kroku 2 (źródła zachowane), wznowienie nigdy nie woła wyszukiwarki i przeżywa symulowany restart, realny koszt zachowany przy błędzie, poprawne sumowanie kosztu obu kroków przez wznowienie, blokada budżetowa przed krokiem 1, blokada budżetowa przed wznowieniem kroku 2, odmowa wznowienia gdy wciąż za mało źródeł, błąd przy nieznanym identyfikatorze researchu.
- **Jaki był wynik:** **73 testy zielone** (było 63). Migracja bazy zweryfikowana. Skrypt poprawnie odmawia bez argumentów i zatrzymuje się przed wywołaniem API przy nieznanym identyfikatorze wznowienia.
- **Co jeszcze nie działa:** nowa architektura nie została jeszcze wypróbowana na prawdziwym API (wymaga osobnej zgody właściciela — plan w `docs/IMPLEMENTATION_PLAN.md` CZĘŚĆ E.8); generator artykułów/Notes/komentarzy, panel FastAPI, Playwright/publikacja nadal niezbudowane.
- **Następny krok:** czekamy na zgodę właściciela na jeden kontrolowany realny test nowej architektury.

### [2026-07-12 03:30 UTC] Etap 1H — drugi realny test: tym razem zawiódł krok 1, nie krok 2
- **Co chcieliśmy osiągnąć:** wypróbować nową, wznawialną architekturę (Etap 1G) na żywym API — plan zakładał uruchomienie obu kroków, a w razie awarii kroku 2, wznowienie WYŁĄCZNIE jego, bez ponownego szukania.
- **Co zbudowaliśmy:** nic nowego — to był czysto testowy, realny (płatny) przebieg zatwierdzonej wcześniej architektury, nie praca kodowa.
- **Pliki, które powstały:** brak zmian w kodzie; tylko wpisy dokumentacyjne (ten plik, `07`, `09`, `16`, `docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md`) + automatyczny zapis do bazy i `docs/COSTS.csv`.
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` sekcja 3.
- **Jak przetestowane:** pre-flight (`--estimate-only`, zero kosztu) potwierdził klucz/budżet/projekcję, dopiero potem realne wywołanie `--topic-id 2 --mode two-stage --max-cost-usd 0.45`.
- **Wynik:** krok 1 (zbieranie źródeł) **nie zwrócił poprawnego JSON-a** — inny scenariusz niż planowany (spodziewaliśmy się ewentualnej awarii kroku 2). Skoro to krok 1 zawiódł, architektura poprawnie rozpoznała, że **nie ma czego wznawiać** (nie ma trwałych źródeł do zapisania) i oznaczyła research jako w pełni nieudany, a nie „częściowy". Mimo to **prawdziwy koszt (0,123823 USD, 4/4 wyszukiwania wykorzystane) został poprawnie zapisany** — dokładnie to zabezpieczenie, które zawiodło przy pierwszej realnej próbie (11.07) i zostało wtedy naprawione, teraz zadziałało bez zarzutu, na nowej ścieżce kodu. System **nie próbował ponownie sam z siebie**, zgodnie z zasadą „jedno uruchomienie, stop".
- **Dobra wiadomość liczbowa:** realny koszt (0,123823 USD) wyszedł **niżej** niż nasz „bezpieczny" szacunek (0,3615 USD dla samego kroku 1) — w przeciwieństwie do pierwszego incydentu, tym razem margines bezpieczeństwa zadziałał we właściwym kierunku.
- **Co jeszcze nie działa:** wciąż nie mamy ani jednej udanej, realnej pełnej karty researchu w nowej architekturze; hipoteza przyczyny (limit długości odpowiedzi kroku 1, domyślnie 1200, może wciąż być za ciasny na 4 wyszukiwania) niepotwierdzona ostatecznie; ścieżka „wznów tylko krok 2" nadal niesprawdzona na żywym API (tylko na danych testowych).
- **Następny krok:** zatrzymuję się i czekam na decyzję właściciela — podnieść limit długości odpowiedzi kroku 1 i spróbować ponownie (nowa, osobna zgoda), czy zbadać przyczynę inaczej.

---

### [2026-07-12] Etap 1I — pierwszy krok researchu rozbity na „szukanie" i „czytanie pojedynczego źródła" (ADR-020)
- **Co chcieliśmy osiągnąć:** właściciel ocenił, że samo podniesienie limitu długości odpowiedzi pierwszego kroku (rekomendacja po Etapie 1H) nie wystarczy — trzeba przebudować sam krok tak, żeby nie zależał od jednej wielkiej odpowiedzi obejmującej wszystkie źródła naraz, i żeby częściowe wyniki nigdy nie znikały.
- **Co zbudowaliśmy:**
  - **Diagnostyka:** każda prawdziwa odpowiedź modelu (udana i nieudana) zapisywana do prywatnego pliku na dysku — treść odpowiedzi, powód zatrzymania generacji (wprost z API, nie zgadywany), liczba zużytych tokenów, miejsce błędu. Nigdy nie trafia do repo (cały folder jest zignorowany przez git), nigdy nie zawiera klucza dostępu.
  - **Krok „szukanie" (1a):** agent TYLKO wyszukuje i zwraca krótką listę adresów-kandydatów z tytułami — bez żadnej analizy. Zapisywane do bazy natychmiast.
  - **Krok „czytanie pojedynczego źródła" (1b):** każde źródło z listy analizowane OSOBNYM, niezależnym zapytaniem do modelu (autor, data, 2-4 twierdzenia, liczby razem z ich kontekstem, ocena jakości) — i zapisywane do bazy NATYCHMIAST po każdym, zanim program zajmie się kolejnym źródłem.
  - **Nowy format odpowiedzi dla listy kandydatów:** zamiast jednej dużej listy w jednym bloku, każdy kandydat to osobna, samodzielna linijka — jeśli ostatnia linijka się urwie, tracimy TYLKO ją, reszta zostaje.
  - **Nowe, dużo mniejsze limity długości odpowiedzi** dla obu kroków (uzasadnienie liczbowe w dokumentacji technicznej) — krok syntezy (trzeci, niezmieniony) zostawiony bez zmian, bo nigdy nie był przyczyną żadnej z dwóch dotychczasowych awarii.
  - **Nowy sposób liczenia kosztu z wyprzedzeniem**, oparty teraz na DWÓCH prawdziwych próbach (nie jednej) — pokazujemy osobno „bezpieczny sufit" i „ile prawdopodobnie wyjdzie", żeby nie powtórzyć błędu z pierwszego incydentu (przyjęcie estymacji za pewnik).
  - Napisaliśmy 12 nowych testów sprawdzających m.in.: czy awaria czwartego źródła zostawia pierwsze trzy nietknięte; czy to samo dzieje się, gdy zawiedzie PIERWSZE źródło (nie tylko ostatnie); czy wznowienie po symulowanym restarcie kontynuuje dokładnie tam, gdzie się skończyło; czy plik diagnostyczny nigdy nie zawiera sekretów.
- **Pliki, które powstały:** nowy moduł diagnostyki, zmiany w module klienta researchu i klienta zastępczego, nowa migracja bazy (nowa tabela na kandydatów/źródła), zmiany w modelach danych i repozytorium, nowe funkcje w module przepływu researchu, zaktualizowany skrypt do uruchamiania researchu, nowy plik testów, `docs/DECISIONS.md` (ADR-020), `docs/IMPLEMENTATION_PLAN.md` (nowa CZĘŚĆ F).
- **Jak to działa:** patrz `04_JAK_DZIALA_AGENT.md` sekcja 3 (zaktualizowana, akapit „pierwszy krok rozbity na szukanie i czytanie pojedynczego źródła").
- **Jak zostało przetestowane:** wyłącznie na klientach zastępczych (bez sieci). Scenariusze: pełna dobra ścieżka od początku do końca, awaria pierwszego źródła, awaria czwartego źródła, wznowienie po symulowanym restarcie, wznowienie trzeciego kroku (syntezy) nigdy nie wywołuje ponownie pierwszych dwóch kroków, uszkodzony ostatni wiersz listy kandydatów, zachowanie kosztu przy każdym typie błędu, brak sekretów w plikach diagnostycznych, brak plików diagnostycznych w trybie próbnym.
- **Jaki był wynik:** **85 testów zielonych** (było 73, +12 nowych, zero regresji w starszych ścieżkach — stary, dwuetapowy sposób nadal działa i jest dostępny, tylko już niezalecany).
- **Co jeszcze nie działa:** nowa architektura nie została jeszcze wypróbowana na prawdziwym API — plan małego, tańszego testu (2 wyszukiwania, 2 źródła, limit 0,25 USD) w dokumentacji technicznej, czeka na osobną zgodę właściciela.
- **Następny krok:** czekamy na zgodę właściciela na mały, kontrolowany realny test nowej architektury.

### [2026-07-12] Etap 1J — pełny audyt architektury: system skontrolował sam siebie (zero zmian w kodzie)
- **Co chcieliśmy osiągnąć:** właściciel zlecił pełny, niezależny przegląd całego projektu — nie „czy testy przechodzą", tylko „czy to wszystko składa się w jeden spójny, bezpieczny system": logika, stany, koszty, granice modułów, gotowość na serwer, sprzeczności między kodem a dokumentacją.
- **Co zbudowaliśmy:** nic — celowo. Audyt był w trybie wyłącznie-do-odczytu; jedynym produktem jest raport (`docs/AUDYT_ARCHITEKTURY_2026-07-12.md`, 24 sekcje).
- **Jaki był wynik (uczciwie):** mimo 85 zielonych testów audyt znalazł **3 błędy krytyczne**, które nie wybuchły tylko dlatego, że żaden realny research jeszcze się nie POWIÓDŁ: (1) system w ogóle nie umie zapisać statusu „sukces" — pierwszy udany realny run zostałby na zawsze oznaczony jako „w trakcie"; (2) krok „czytania źródła" wcale nie czyta źródła — pyta model o opinię o adresie, a model sam sobie wystawia ocenę „zweryfikowane"; zaproponowany wcześniej mały test (bez wyszukiwania per źródło) niczego by więc nie dowiódł i został w raporcie ZMIENIONY; (3) w projekcie wciąż istnieje jedna „stara" komenda, która potrafi uruchomić research bez żadnego z zabezpieczeń wypracowanych po obu incydentach — z nieograniczoną liczbą wyszukiwań w jednym wywołaniu. Do tego 10 problemów ważnych i 15 usprawnień, plus 14 skatalogowanych rozjazdów kod↔dokumentacja.
- **Najciekawszy wniosek do artykułu:** *zielone testy mierzą to, co ktoś pomyślał, żeby sprawdzić — audyt szuka tego, o czym nikt nie pomyślał.* Wszystkie trzy błędy krytyczne leżały w miejscach, których 85 testów w ogóle nie odwiedzało (ścieżka sukcesu w trybie realnym, samoocena modelu, zapomniane wejście CLI).
- **Co dalej:** STOP — raport czeka na decyzję właściciela. Rekomendacja: trzy naprawy krytyczne (offline, tanie) PRZED jakimkolwiek kolejnym płatnym wywołaniem.

### [2026-07-12] Etap 1K — naprawa trzech błędów krytycznych z audytu (zero API, zero Playwrighta)
- **Co chcieliśmy osiągnąć:** właściciel zatwierdził naprawę WYŁĄCZNIE trzech błędów krytycznych z Etapu 1J (nie ważnych, nie usprawnień) — najmniejszą możliwą zmianą, bez przebudowy architektury, bez usuwania starszych, działających ścieżek researchu, w pełni offline.
- **Co zbudowaliśmy — trzy naprawy:**
  1. **„Nieograniczona" komenda researchu.** Przyczyna: jedna z dwóch dróg uruchomienia realnego researchu (starsza, wbudowana w główny program) nie miała ANI limitu liczby wyszukiwań w internecie, ANI górnego limitu kosztu — wszystkie zabezpieczenia wypracowane po obu dotychczasowych incydentach żyły wyłącznie w osobnym, dedykowanym skrypcie. Naprawa: ta starsza droga teraz **natychmiast się zatrzymuje** z jasnym komunikatem, zanim cokolwiek zrobi — wskazuje na właściwy, bezpieczny skrypt.
  2. **Brak statusu „sukces".** Przyczyna: system od samego początku projektu potrafił zapisać tylko „w trakcie", „nieudany" i „tryb próbny" — nigdy „udany" dla prawdziwego, płatnego uruchomienia. Nikt tego nie zauważył, bo żadna z dwóch dotychczasowych realnych prób się nie powiodła. Sprawdziliśmy wprost w bazie danych: zero zapisanych „sukcesów" w całej historii projektu. Naprawa: pięć miejsc w kodzie, które kończą udany przebieg, teraz poprawnie zapisują „sukces" dla prawdziwych uruchomień (tryb próbny bez zmian).
  3. **Samoocena modelu zamiast dowodu.** Przyczyna: krok „czytania pojedynczego źródła" (z Etapu 1I) w rzeczywistości NIE czyta treści strony — pyta model o adres internetowy. Gdy nie miał w ogóle dostępu do wyszukiwania (dokładnie tak, jak w PIERWOTNIE proponowanym małym teście), model i tak sam sobie przyznawał ocenę „zweryfikowane", a reguła jakości traktowała „niezweryfikowane" tak samo jak „zweryfikowane" — karta bez jednego realnego dowodu mogła przejść bramkę. Naprawa (deterministyczna, nie „lepsza prośba do modelu"): (a) gdy narzędzia weryfikacji faktycznie nie było, system SAM wymusza etykietę „niezweryfikowane", niezależnie od tego, co napisał model; (b) nowa reguła: dla prawdziwych (płatnych) uruchomień liczą się do progu WYŁĄCZNIE źródła faktycznie zweryfikowane, nie każde niepotwierdzone-ale-nie-odrzucone.
- **Czego świadomie NIE zrobiliśmy:** prawdziwego pobierania treści strony ([P0-2c w raporcie audytu] — to osobna, większa zmiana, poza zakresem tego zadania); żadnej z 10 ważnych ani 15 drobnych rzeczy z raportu; żadnej przebudowy; nie usunęliśmy ani jednej starszej, działającej ścieżki researchu.
- **Pliki, które się zmieniły:** 5 plików źródłowych (bez nowych) — moduł uruchamiania programu, główny plik programu (tylko tekst pomocy), moduł przepływu researchu, moduł przepływu tematów, moduł reguł jakości. Zero nowych plików źródłowych.
- **Jak zostało przetestowane:** 7 nowych testów w 4 plikach (jeden nowy plik testowy) — po jednym teście na każdą z trzech napraw plus dodatkowe warianty (m.in. dowód „na żywo": klient zastępczy CELOWO twierdzi „zweryfikowane", a mimo to system i tak zapisuje „niezweryfikowane" i odrzuca kartę — dokładnie odtworzony scenariusz z pierwotnie proponowanego małego testu, który po naprawie poprawnie kończy się odrzuceniem zamiast fałszywym sukcesem). Dodatkowo ręcznie sprawdzono w terminalu, że „nieograniczona" komenda faktycznie się zatrzymuje.
- **Jaki był wynik:** **92 testy zielone** (było 85, +7 nowych, **zero regresji** — wszystkie stare testy, w tym te dla dwóch starszych, wciąż dostępnych sposobów prowadzenia researchu, przeszły bez żadnej zmiany).
- **Potwierdzenie:** zero wywołań prawdziwego API, zero Playwrighta, zero nowej realnej próby researchu — wyłącznie kod, testy na danych zastępczych i jedno ręczne sprawdzenie w terminalu (które samo zatrzymało się, zanim dotknęło czegokolwiek prawdziwego).
- **Co jeszcze nie działa (ważne zastrzeżenie):** to jest **zabezpieczenie**, nie ostateczne rozwiązanie jakości źródeł. Nawet gdy wyszukiwanie JEST włączone, krok czytania źródła wciąż nie pobiera samej strony — opiera się na wynikach wyszukiwarki „o" adresie, nie na jego treści. Ta naprawa gwarantuje tylko, że system się nie oszukuje, gdy narzędzia weryfikacji w ogóle zabrakło — nie podnosi jakości weryfikacji tam, gdzie wyszukiwanie działa. Prawdziwe pobieranie treści strony zostaje jako osobne, świadomie odłożone zadanie.
- **Następny krok:** czekamy na decyzję właściciela — mały, kontrolowany realny test (teraz bezpieczniejszy dzięki tym trzem naprawom), czy najpierw któraś z ważnych (nie krytycznych) pozycji z raportu audytu.

### [2026-07-12] Etap 1L — trzeci realny test: bezpieczna obsługa błędu potwierdzona na żywo, przyczyna ucięcia wreszcie PEWNA (część naprawek z Etapu 1K wciąż nieprzetestowana na API)
- **Co chcieliśmy osiągnąć:** właściciel zatwierdził dokładnie tę konfigurację małego testu, którą audyt zaproponował po naprawach z Etapu 1K — sprawdzić na żywym API, czy trzy naprawy bezpieczeństwa faktycznie działają, nie tylko na danych zastępczych.
- **Dokładna komenda:** `python scripts/run_capped_research.py --topic-id 2 --discovery-max-searches 1 --max-sources 2 --max-web-searches-per-source 1 --max-cost-usd 0.30`, poprzedzona darmowym `--estimate-only` (sufit 0,2966 USD, środkowy szacunek 0,1144 USD — oba pokazane PRZED wydaniem grosza).
- **Co się wydarzyło:** krok „szukanie" — sukces, 4 kandydatów, czysty koniec generacji. Krok „czytanie źródła" — **OBIE próbowane próby (limit 2) zakończyły się urwaną odpowiedzią** — i po raz pierwszy w całym projekcie wiemy to NA PEWNO, nie z domysłu: każda odpowiedź niesie teraz wprost z API powód zatrzymania generacji, a w obu przypadkach brzmiał on „osiągnięto limit długości odpowiedzi". Trzeci krok (synteza) **nigdy się nie uruchomił** — mieliśmy 0 gotowych źródeł, a potrzeba minimum 3, więc system poprawnie oszczędził koszt syntezy zamiast płacić za nią na próżno.
- **Rzeczywisty koszt: 0,097824 USD** — jedna trzecia limitu 0,30 USD, mniej nawet niż środkowy szacunek. Cap nienaruszony, potwierdzone dwa razy (przez sam skrypt i niezależnie przez sumę w bazie danych).
- **Rozbicie kosztu:** szukanie (1 wyszukiwanie) = 0,026636 USD; czytanie źródła nr 1 (nieudane) = 0,037919 USD; czytanie źródła nr 2 (nieudane) = 0,033269 USD.
- **Stany końcowe — dokładnie zgodnie z projektem:** ogólny status runu: „nieudany" (NIGDY „w trakcie" — to właśnie miała pilnować pierwsza z trzech naprawek, choć akurat tym razem nie musiała nawet zadziałać, bo to nie był sukces). Szczegółowy status researchu: „częściowy, wznawialny" (2 z 4 kandydatów wciąż czeka na próbę).
- **Zero źródeł zweryfikowanych, zero kart researchu.** Wszystkie 4 kandydaci mają etykietę „niezweryfikowane" — nie dlatego, że system to WYMUSIŁ (druga naprawka z Etapu 1K nie musiała się tu włączyć, bo wyszukiwanie było włączone), tylko dlatego, że próba analizy się po prostu nie udała. **Żadna karta researchu nie powstała — system poprawnie nie zapłacił za syntezę z niewystarczających danych.** To jest właśnie to, co miała pilnować trzecia naprawka, i choć w tym konkretnym przebiegu zadziałał wcześniejszy mechanizm (za mało źródeł, więc synteza się w ogóle nie zaczęła), efekt końcowy jest ten sam: żadnej fałszywej karty w bazie.
- **Dwa nowe, uczciwe znaleziska (żadne nie jest błędem bezpieczeństwa):**
  1. **Kosmetyczny błąd wyświetlania** — podsumowanie w terminalu pokazało „0 tokenów, brak modelu" mimo realnego zużycia. Sama baza danych ma komplet poprawnych liczb (patrz tabela w `docs/BUILD_LOG.md`) — to tylko funkcja podsumowująca krok „czytanie źródła" zapomina przepisać te konkretne pola do wyniku, nic więcej. Nie naprawialiśmy — nikt o to nie prosił.
  2. **Odsłonięta granica wznawialności.** Ten konkretny research MOŻNA technicznie wznowić, ale wznowienie spróbuje TYLKO dla 2 kandydatów, którzy nigdy nie byli próbowani — nie ma dziś żadnego sposobu, żeby ponowić próbę dla 2 kandydatów, którzy już zawiedli. Nawet gdyby oba pozostałe się udały, dałoby to najwyżej 2 źródła — wciąż o jedno za mało. Ten konkretny research nie da się dziś doprowadzić do końca bez albo naprawienia „ponawiania nieudanych prób", albo umożliwienia dodatkowego szukania nowych kandydatów w tym samym researchu (dziś architektura na to nie pozwala — szukanie dzieje się tylko raz, na starcie).
- **Jak to działa:** patrz `docs/BUILD_LOG.md` (Etap 1L) dla pełnego rozbicia liczb i tabeli kosztów.
- **Jak zostało przetestowane:** to BYŁ test — jedno, w pełni kontrolowane, zatwierdzone realne uruchomienie, poprzedzone darmowym podglądem estymacji.
- **Jaki był wynik (precyzyjnie — co naprawdę sprawdziliśmy, a czego nie):** ten test potwierdził na żywo TYLKO część naprawek z Etapu 1K, i trzeba to nazwać uczciwie, nie na wyrost. Faktycznie sprawdzone na prawdziwym API: bezpieczna obsługa błędu (żaden run nie utknął w stanie pośrednim, mimo dwóch kolejnych awarii pod rząd), pełne i poprawne zaksięgowanie kosztu mimo tych awarii, oraz zapobieżenie fałszywej karcie (system nie zapłacił za syntezę, skoro źródeł było za mało). NIE sprawdzone na żywo w tym teście: zapis statusu „sukces" (bo nie było żadnego sukcesu do oznaczenia), wymuszenie „niezweryfikowane" przy zerowym dostępie do wyszukiwania (bo w tym teście wyszukiwanie było włączone, więc ten fragment kodu się nie uruchomił), oraz próg minimalnej liczby zweryfikowanych źródeł przy prawdziwej syntezie (bo synteza w ogóle się nie zaczęła). Te trzy elementy nadal mają potwierdzenie WYŁĄCZNIE z danych zastępczych (7 testów z Etapu 1K), nie z prawdziwego API — to zostaje do sprawdzenia przy przyszłym udanym (albo inaczej nieudanym) realnym uruchomieniu. Przy okazji: mechanizm diagnostyczny z Etapu 1I zadziałał dokładnie tak, jak zaplanowano — pierwszy raz w projekcie przyczyna ucięcia odpowiedzi jest PEWNA (limit długości odpowiedzi kroku „czytanie źródła" — domyślnie 500 — okazał się za ciasny; realne zużycie wyniosło 640 i 653), nie zgadywana.
- **Co jeszcze nie działa:** wciąż zero udanych, pełnych kart researchu po trzech realnych próbach. Przyczyna tej konkretnej porażki jest już znana i naprawialna (podnieść limit długości odpowiedzi kroku czytania źródła). Ponawianie nieudanych prób pojedynczych źródeł — wciąż nie istnieje.
- **Następny krok:** czekamy na decyzję właściciela — podnieść limit i spróbować ponownie (nowa, osobna zgoda), czy najpierw dodać możliwość ponawiania nieudanych prób.

### [2026-07-12] Etap 1M — diagnostyka trzeciego kandydata, limit A2=1500 i poprawne podsumowanie CLI
- **Co chcieliśmy osiągnąć:** sprawdzić, czy limit 500 jest rzeczywistą przyczyną ucięcia A2, a następnie ustawić rozsądny default produkcyjny i naprawić kosmetyczne podsumowanie terminala — bez dodawania retry dla dwóch wcześniej nieudanych kandydatów.
- **Pierwsza próba diagnostyczna:** zatrzymała się lokalnie, zanim wysłano request. Stary pakiet `anthropic==0.37.1` był niezgodny z `httpx==0.28.1` i przekazywał usunięty argument `proxies`. Koszt: **0,00 USD**, zero API. W izolowanym środowisku projektu podniesiono `anthropic` do 0.116.0 (spełnia istniejące `anthropic>=0.40`). Ostrzeżenia `pip` dotyczącego niezależnego `open-interpreter` nie naprawiano, bo ten pakiet jest poza projektem.
- **Udana diagnostyka:** użyto wyłącznie oczekującego kandydata `id=3`. Kandydaci 1 i 2 NIE zostali ponowieni. Jednorazowy sufit 5000 służył tylko do pomiaru i nigdy nie był proponowany jako default. Odpowiedź skończyła się naturalnie (`end_turn`) przy 915 tokenach wyjścia: input 14 394, 1 wyszukiwanie, VERIFIED, jakość 0,55.
- **Koszty — trzy różne poziomy:** sam diagnostyczny call kosztował **0,028969 USD**; cały istniejący run miał po nim koszt skumulowany **0,126793 USD**; cały projekt — **0,500616 USD**. Conservative estimate 0,1256 USD był bezpieczny, ale około 4,34 razy wyższy od ceny calla, więc nie był dokładną prognozą.
- **Co zmieniliśmy:** produkcyjny default limitu A2 podniesiono z 500 do **1500** we wszystkich realnych źródłach wartości; jawny override CLI nadal działa. Podsumowanie A2 agreguje teraz model, input/output tokens, web search i koszt WSZYSTKICH calli A2 z bieżącego uruchomienia. Skumulowane księgowanie całego runu nadal pozostaje w bazie.
- **Jak przetestowane:** 30 testów celowanych i pełne **102 testy** — wszystkie zielone. Testy obejmują default, override, wiele źródeł, błąd jednego źródła, PARTIAL z wcześniejszym kosztem A1 oraz niezmienione dry_run.
- **Czego nie zrobiliśmy:** żadnego nowego ani wznowionego research runu podczas dokończenia; zero API i zero Playwrighta; brak ręcznych zmian statusów; brak P1-5. Nie twierdzimy, że kandydaci 1 i 2 potrzebowaliby dokładnie 915 tokenów — nie zostali ponowieni.
- **Następny krok:** kolejny kontrolowany realny run może użyć bezpieczniejszego defaultu 1500, ale nadal wymaga osobnej zgody. Istniejący PARTIAL nie stanie się kompletny bez osobnego rozwiązania P1-5 lub dodatkowych kandydatów.

---

### [2026-07-12] Etap 1O — bezpieczna konfiguracja pierwszej kompletnej Research Card

Cel: przygotować całkowicie offline świeży, trzyetapowy run A1/A2/B, bez jego uruchamiania.

Konfiguracja: A1 ma najwyżej 1 wyszukiwanie i 600 tokenów wyjścia; maksymalnie 4 źródła; każde A2 ma najwyżej 1 wyszukiwanie i 1500 tokenów wyjścia; max_retries=0; B ma 2200 tokenów wyjścia i 2500 tokenów kontekstu; wyłącznie mode=three-stage, bez resume.

Cztery źródła dają minimalny zapas odporności: synteza wymaga co najmniej trzech udanych ekstrakcji, więc pojedynczy błąd A2 nie musi przerwać runu.

| Etap | Oczekiwany | Konserwatywny |
|---|---:|---:|
| A1 | 0,033956 USD | 0,092625 USD |
| A2 (4 źródła) | 0,153824 USD | 0,397500 USD |
| B | 0,013500 USD | 0,020250 USD |
| Razem | 0,201280 USD | 0,510375 USD |

Rekomendowany limit akceptacyjny wynosi 0,55 USD. Jest o 0,039625 USD (7,76%) wyższy od konserwatywnej kalkulacji, która sama zawiera 50% marginesu.

Weryfikacja offline: 102 passed; estimate-only nie wykonał API ani nie utworzył runu; test timeoutu potwierdził jedno wywołanie przy max_retries=0; odczyt bazy potwierdził, że istniejący run PARTIAL pozostał bez zmian.

Ryzyka: A2 nadal wyszukuje adres URL zamiast pobierać stronę; limit kosztu jest kontrolą przed startem, a nie bezpiecznikiem w trakcie; timeout może mieć nieznany koszt; bez P1-5 dwa błędy A2 uniemożliwią B; etap B nie ma jeszcze realnego sukcesu.

Koszt etapu: 0,000000 USD. Nie wykonano API, Playwrighta, startu ani wznowienia runu.

Werdykt: READY FOR OWNER APPROVAL.

## Etap 1P — wielki porządek w dokumentacji (2026-07-12)

Po trzech nieudanych realnych próbach researchu i serii napraw projekt miał już cztery
równoległe dokumenty opisujące „docelową architekturę" — z różnych dat, częściowo sprzeczne.
Właściciel zlecił pełny audyt architektury i konsolidację: od teraz obowiązują dokładnie trzy
dokumenty w korzeniu repo (MASTER_ARCHITECTURE.md — architektura, IMPLEMENTATION_ROADMAP.md —
kolejność prac, CURRENT_PROJECT_STATE.md — rzeczywisty stan), a wszystkie stare plany i audyty
wylądowały w docs/archive/superseded_plans/ z banerem „ARCHIVED — NOT A SOURCE OF TRUTH".

Audyt zweryfikował stan wyłącznie z kodu, testów i bazy (102 testy zielone, 0,500616 USD
realnego kosztu, zero publikacji). Ciekawostka procesowa: audyt znalazł też dwa nowe drobiazgi —
klient tematów nie księguje kosztu przy błędzie parsowania (klient researchu robi to od
incydentu 11.07), a dwa adaptery portów okazały się martwym kodem. Zero zmian w logice
aplikacji; następny krok to Etap 0 roadmapy i — po osobnej zgodzie — run z limitem 0,55 USD.

Wniosek do serii: agentowa dokumentacja rozrasta się szybciej niż kod i po tygodniu potrafi
kłamać. Lekarstwem nie jest „więcej dokumentów", tylko jeden jawny kanon + archiwum z twardym
ostrzeżeniem.

## Etap 0 / zadanie 1 — system przestał zgadywać własny rodzaj researchu (2026-07-12)

Wspólny status `PARTIAL` oznaczał dotąd dwie różne rzeczy: niedokończony stary research dwuetapowy albo niedokończony nowy A1/A2/B. Skrypt rozstrzygał to, zaglądając do dwóch tabel i zgadując po tym, gdzie znalazł rekordy. To działało tylko tak długo, jak dane były kompletne i niejednoznaczność nie trafiła na kolejny przypadek brzegowy.

Migracja 0006 dodała obowiązkowe pole `flow`: `single`, `two_stage` albo `staged`. Nie ma wartości domyślnej — każdy nowy pipeline musi nazwać swój przepływ w chwili tworzenia runu. Po review usunęliśmy ryzykowne skróty: dwa znane runy single są mapowane tylko po pełnym UUID, koncie i topicu (jeden także po dokładnej karcie), a two-stage i staged wyłącznie po trwałych śladach strukturalnych w taskach, etapach i właściwych tabelach źródeł. Status, `current_state`, prefiks UUID i czas powstania karty nie decydują o flow. Przy sygnałach sprzecznych albo niepełnych migracja wycofuje transakcję.

Próba na pamięciowej kopii prawdziwej bazy dała pełną, deterministyczną historię: dwa runy single (w tym pierwsza płatna porażka `1b649314`), jeden two-stage i jeden staged. Zero naruszeń kluczy obcych, a źródłowa baza pozostała nietknięta. Wszystkie funkcje wznowienia porównują zapisany flow; CLI dodatkowo odrzuca niedozwolony status jeszcze przed usage, estymacją, klientem i nawet ścieżką estimate-only. `_detect_flow` zniknęło z kodu.

Testy wzrosły z 102 do **127 zielonych** (70 testów celowanych). Nowe przypadki obejmują black-box CLI, czystą i pustą bazę, brak lokalnych historycznych UUID, konflikt klasyfikacji oraz zachowanie schematu, indeksów, triggerów i integralności. Koszt zadania: 0 USD; zero API, Playwrighta i prawdziwych runów. Zadania 2–9 Etapu 0 pozostały wtedy nietknięte.

## Etap 0 / zadanie 2 — licznik kosztu przestał pamiętać tylko ostatni etap (2026-07-12)

Po podziale researchu na A1, A2 i B koszt jednego runu powstaje kawałkami. Łatwo byłoby dopisywać ostatnią kwotę do pola podsumowującego — a wtedy restart, częściowa ekstrakcja albo wyjątek po zapisie usage mogłyby stworzyć drugi, niespójny rachunek. Zamiast tego `model_usage` pozostaje księgą zdarzeń, a `runs.cost_usd` jest zawsze ustawiane na aktualną sumę zapisów dla danego runu. Ponowne wykonanie synchronizacji niczego nie dolicza drugi raz.

Przy okazji centralne połączenie SQLite dostało tryb WAL i pięciosekundowe oczekiwanie na blokadę. To nie tworzy jeszcze workera ani nie rozwiązuje wszystkich przyszłych problemów współbieżności, ale eliminuje najprostszy konflikt czytelnika z pisarzem przed kolejnymi etapami projektu.

Pierwsza weryfikacja przed niezależnym review objęła udany pełny run, błędy A1 i B, częściową/wznowioną A2, odrzucenie po płatnej syntezie, dry-run, brak nowego calla oraz wyjątek już po zapisaniu usage: **131 zielonych testów**, 0 USD, zero API i zero Playwrighta. Końcowy wynik po korekcie P1 podano poniżej.

### Korekta po niezależnym review: jedna transakcja dla rachunku i podsumowania

Review znalazł ważną lukę ukrytą między dwoma poprawnymi fragmentami kodu: wpis `model_usage` był zatwierdzany wcześniej niż odświeżenie `runs.cost_usd`. Na tymczasowej bazie dało się po restarcie zobaczyć `0.123456` w księdze i `0.000000` w podsumowaniu runu. To nie był błąd estymacji ani utrata kanonicznego zapisu, ale cache mógł trwale zostać w tyle.

Poprawka przeniosła granicę transakcji do repozytorium. Dla researchu INSERT usage, ponowne zsumowanie wszystkich wpisów runu i absolutny UPDATE cache'a dzieją się przed jednym commitem. Jeśli UPDATE zawiedzie, SQLite wycofuje również nowy wpis usage. Stary helper został zachowany dla wznowienia bez nowego calla oraz naprawy już istniejącego cache'a.

Dodano test rollbacku wymuszony triggerem SQLite, reopen plikowej bazy, zero usage, błędy A1/B bez usage, dry-run i wielokrotny no-call resume. Przy okazji połączenie SQLite najpierw ustawia timeout, a dla bazy plikowej potwierdza aktywny WAL. Końcowy wynik: **139 zielonych testów**, 0 USD, zero API i zero Playwrighta.

---

## Stan bieżący (2026-07-12)
Zbudowane i przetestowane: Etap 0 + walking skeleton + Etap 1A + Etap 1B + Etap 1C (pierwsza realna próba, nieudana + naprawiony bug kosztowy) + Etap 1D (realny koszt = 0,25 USD wpisany wszędzie, nowy sposób liczenia kosztu, research podzielony na dwa kroki) + Etap 1E (doprecyzowanie celu: pełna autonomia, dokumentacja, zero kodu) + Etap 1F (korekta: brak publicznego ujawniania AI, ADR-018, zasada NO_REPLY, zero kodu) + Etap 1G (pełna wznawialność researchu, ADR-019, zero kodu poza researchem) + Etap 1H (drugi realny test — awaria kroku 1, mechanizmy bezpieczeństwa potwierdzone na żywo) + Etap 1I (przebudowa kroku 1 na szukanie + czytanie pojedynczego źródła, diagnostyka, ADR-020) + Etap 1J (pełny audyt architektury, zero zmian w kodzie, 3 błędy krytyczne znalezione) + Etap 1K (naprawa trzech błędów krytycznych z audytu, zero API) + Etap 1L (trzeci realny test — bezpieczna obsługa błędu i księgowanie kosztu potwierdzone na żywo) + Etap 1M (udana diagnostyka kandydata 3, produkcyjny default A2=1500, naprawione podsumowanie CLI) + Etap 0 zadanie 1 (jawny flow, migracja 0006, bezpieczne resume) + Etap 0 zadanie 2 (atomowy cache kosztu staged, WAL i busy timeout). **139 testów przechodzi.** Dotychczas wykonano cztery zatwierdzone płatne operacje/testy researchu, obejmujące łącznie sześć requestów API; żadna pełna Research Card jeszcze nie powstała. **Łączny realny koszt: 0,500616 USD**, potwierdzony w bazie. Zero publikacji.

**Aktualizacja Etap 1O:** świeży run A1/A2/B dla tematu 2 został przygotowany, lecz nie uruchomiony. Koszt oczekiwany to 0,201280 USD, konserwatywny 0,510375 USD, a proponowany limit akceptacyjny 0,55 USD.

## Etap 0 / Task 3 — retry, które nie dzieje się samo (2026-07-12)

Po poprzednim etapie `9bbeb020` był częściowym runem z dwoma błędami A2, ale system umiał wznawiać tylko źródła, których nigdy nie próbował. To bezpieczne w jednym sensie — nie kupował kolejnych prób po cichu — lecz pozostawiało brak jawnej drogi naprawy.

Dodaliśmy więc licznik `attempts` do każdego kandydata. To nie jest licznik „błędów” ani „retry”: oznacza rozpoczęte wywołania A2 i rośnie tuż przed call'em. Nowa komenda resetuje wyłącznie failed poniżej capu do pending; nie uruchamia modelu, a następne A2 wymaga osobnego resume. Domyślny cap 2 oznacza jedną pierwszą próbę i co najwyżej jedno ręczne ponowienie.

Jeżeli nie ma pending ani failed poniżej capu, a źródeł nadal jest za mało, run przechodzi do `PARTIAL_EXHAUSTED`. To uczciwy terminalny wynik, nie fałszywa obietnica, że zwykłe resume „może coś jeszcze zrobi”. Testy obejmują migrację na pamięciowej kopii prawdziwej bazy, sukces/błąd, drugi attempt, cap, idempotencję, CLI i odmowę terminalnego resume: **153 testy zielone**, koszt 0 USD, zero API, Playwrighta i realnego researchu. Produkcyjna baza nie została zmieniona.

### Korekta po review: sam licznik nie mówi, co stało się z requestem

Niezależne review zatrzymało ten wariant przed commitem. Historyczne zero było zbyt optymistyczne: status failed już dowodził co najmniej jednej próby. Jeszcze ważniejsze było okno między inkrementacją a wynikiem calla. Po awarii rekord nadal wyglądał jak `PENDING`, więc zwykłe resume mogło nieświadomie zrobić drugi request.

Poprawka nadała temu stanowi nazwę: `EXTRACTION_IN_PROGRESS`. Jedna atomowa operacja rezerwuje próbę, podnosi `attempts` tylko poniżej capu i odbiera kandydat drugiemu wykonawcy. Jeżeli proces znika, system nie zgaduje wyniku i odmawia zwykłego resume. `attempts` nie oznacza już „na pewno wykonanych calli”, lecz uczciwie: „zarezerwowane próby”. Historyczne dane dostają dolną granicę 0 lub 1.

Review znalazł też, że terminalność zależała od zmiennego parametru. Teraz wyższy cap może być świadomą, bezpłatną komendą, która odblokowuje exhausted run do `PARTIAL`; sam resume nadal tego nie robi. Do tego DDL migracji i wpis w ledgerze są jedną transakcją. Wynik po poprawce: **164 testy zielone**, 0 USD, zero API, Playwrighta i zmian bazy źródłowej.

**Task 4 (2026-07-12):** zakończony research ma teraz drugi, mały skutek: temat przechodzi w `USED`. To nie blokada na zawsze. Jeśli naprawdę chcemy sprawdzić temat od nowa, komenda musi wprost powiedzieć `--force-re-research`. Bez tego program zatrzymuje się, zanim policzy budżet, utworzy run lub zbuduje klienta API. Force nadal przechodzi wszystkie zwykłe bramki; nie jest ukrytym retry. Testy objęły single, two-stage, staged i CLI: **169 passed**, 0 USD, zero API.

### Korekta po niezależnym review: „atomowo” znaczy cały finał

Review zbudowało celowo złą relację: run jednego tematu dostał kartę drugiego. Baza zaakceptowała ją, bo zwykły foreign key sprawdza tylko istnienie karty. Drugi eksperyment zatrzymał UPDATE `USED`; para COMPLETE/USED wróciła poprawnie, ale wcześniej zapisany `runs.SUCCESS` i karta zostały. To był sukces tylko z nazwy.

Poprawka wprowadziła jedną końcową operację. Najpierw sprawdza ona, czy run, temat, karta i konto mówią o tym samym obiekcie. Dopiero potem, w jednej transakcji, zapisuje COMPLETE, terminalny run i USED. Uszkodzony USED albo COMPLETE nie jest już interpretowany jako „nic tu nie ma”: system zatrzymuje się fail-closed, także gdy ktoś poda force. Standardowy runner sprawdza to zanim zbuduje nawet klienta zastępczego. **186 testów**, 0 USD, zero API.

### Druga korekta Task 4: bezpieczna transakcja też może być niebezpieczna po raz drugi

Drugie review powtórzyło finalizację już ukończonego runu. Pierwsza zapisała kartę 1 i koszt 0,1; druga bez oporu przepięła go na kartę 2 i koszt 0,9. Wszystko odbyło się atomowo — tylko że atomowo zmieniliśmy historię. To pokazało różnicę: atomowość chroni granicę jednego zapisu, idempotencja chroni jego znaczenie przy powtórzeniu.

Od tej korekty identyczne powtórzenie nie wykonuje żadnego UPDATE. Inna karta, koszt, status terminalny, semantyka etapu B lub uszkodzony COMPLETE kończą się odmową i rollbackiem. Uzupełniono też pominięte scenariusze: SELECTED z COMPLETE, mieszane historie, force wobec korupcji i złego konta oraz nieudany forced run w każdym flow. **206 testów zielonych**, 0 USD, zero API.

### Trzecie review Task 4: kod potrafił, ale test jeszcze tego nie dowodził

Review nie znalazło nowego błędu w finalizacji. Mimo to odrzuciło zmianę, ponieważ brakowało jawnych dowodów dla negatywnej macierzy Stage B, karty obcego topicu/konta oraz pełnych liczników tabel po odmowie. To ważna różnica: przeczytanie warunku w kodzie nie zastępuje testu, który uruchamia go na prawdziwej SQLite i sprawdza stan po reopen.

Dopisane sześć regresji przeszło bez zmiany kodu produkcyjnego. Runner i capped CLI porównują teraz cztery tabele po account mismatch. Pełny wynik to **212 testów**, koszt 0 USD i zero API. Pozostał jawny P2: koszt no-op jest porównywany dokładnym `float == float`, więc równoważna kwota o innej reprezentacji binarnej może zostać bezpiecznie odrzucona.

**Stan planu w chwili trzeciego review Task 4:** następne było wyrównanie klienta tematów (Task 6); prawdziwe pobieranie treści źródła (P0-2c) i pierwszy kompletny realny Research Card pozostawały późniejsze oraz zależne od osobnej zgody.

### Task 6: rachunek zapisany przed próbą zrozumienia odpowiedzi

Klient tematów miał prostą, ale kosztowną w skutkach kolejność: najpierw próbował sparsować JSON, a dopiero później budował obiekt usage. Jeśli odpowiedź była ucięta, `json.loads` przerywał funkcję i lokalna księga zachowywała się tak, jakby płatnego wywołania nie było.

Nowa kolejność brzmi: odpowiedź providera, natychmiast `Usage`, dopiero potem tekst i parser. Błąd formatu przenosi usage oraz model do workflow, które zapisuje koszt raz, kończy run jako `FAILED` i nie tworzy nawet jednego częściowego tematu. Błąd providera przed odpowiedzią pozostaje innym przypadkiem: nie ma wiarygodnego usage, więc system nie wymyśla zera ani fikcyjnego rachunku.

Parser toleruje jedną rzecz, którą modele robią często: opakowanie poprawnego JSON-u w pojedynczy fence ` ```json `. Nie toleruje tekstu przed lub po danych, pustego albo niedomkniętego fence ani uciętego JSON-u. Parse error nie jest retry'owany — drugi call byłby drugim potencjalnym kosztem, nie naprawą pierwszej odpowiedzi.

Self-review znalazł, że pierwsza poprawka nadal składała tekst przed obiektem usage. Testy były zielone, ale kontrakt nie był spełniony literalnie. Kolejność poprawiono i udowodniono przez fałszywy moduł SDK. Wynik: **286 testów**, 0 USD, zero API, researchu i Playwrighta.

**Następne (niezbudowane):** Task 7 — higiena statusów ADR; Task 8 — walidacja przejść `mark_*`; realny run dopiero później i za osobną zgodą.

### Task 8: przejście statusu stało się pojedynczą operacją

Inwentaryzacja znalazła ślepe UPDATE-y w ogólnych runach, etapach researchu i części helperów kandydatów. Od tej zmiany status nie jest najpierw odczytywany, a potem bezwarunkowo zapisywany. Poprzedni stan jest częścią tego samego UPDATE, a liczba zmienionych wierszy mówi, czy proces naprawdę wygrał prawo do przejścia.

Najciekawsza korekta przyszła z istniejących testów: resume używa tego samego `run_id`, więc kolejna jawna próba może zakończyć się `FAILED→FAILED`, a staged A2 może legalnie przejść `DISCOVERY_COMPLETE→PARTIAL`, gdy nie próbuje żadnego źródła. Reguły doprecyzowano bez zezwalania na cofanie COMPLETE ani zmianę jednego terminala na drugi; konkurencyjne resume używa compare-and-swap poprzedniego payloadu. Wynik: **330 testów**, 0 USD, zero API; Task 9 nie został rozpoczęty.

### Korekta Task 8 po końcowym review: wyjątek musi mieć własne wejście

Review zauważyło, że nazwanie gałęzi w ogólnym `finish_run` „resume” niczego nie ograniczało. Każdy FAILED mógł wejść w ten kod. Po korekcie zwykły terminalny run jest niezmienny, a nieudane resume researchu ma osobną operację wymagającą całej relacji, właściwego flow/statusu i snapshotu sprzed próby.

Drugi P1 dotyczył dowodu: dwa połączenia wykonane kolejno nie są wyścigiem. Nowy test uruchamia dwa wątki przez `Barrier`; jedno wygrywa claim, drugie dostaje konflikt, a po reopen baza pokazuje dokładnie jedną próbę. Pełny wynik: **337 testów**, 0 USD, zero API.

### Task 9: pierwszy pełny staged run dotarł do B, ale nie utworzył karty

Właściciel zatwierdził jeden run topic #2 z capem 0,55 USD i zerem retry. Pre-flight policzył conservative 0,510375 USD. A1 odkrył cztery kandydaty, a cztery osobne A2 zakończyły się sukcesem i zapisały cztery VERIFIED. Dopiero synteza B wykorzystała pełne 2200 tokenów, zwróciła `stop_reason=max_tokens` i ucięty JSON.

Trwałość zadziałała: wszystkie opłacone źródła i sześć wpisów usage pozostały w bazie, a koszt 0,170050 USD jest zgodny z cache runu. Jednocześnie brak karty oznacza, że Task 9 i Etap 0 nie są ukończone. Nie wykonano drugiej próby ani resume. Odczyt po procesie ujawnił też nieterminalny ogólny `RUNNING`; zapisano go do review bez poprawiania kodu.

## Powiązania
- `docs/BUILD_LOG.md` (źródło), `docs/ARCHITECTURE_EVOLUTION.md`, `docs/RELEASE_TIMELINE.md`
- `timeline/` (oś czasu do wyeksportowania)

### 2026-07-12 — Task 5: budżet sprawdzany przed każdą próbą
Pre-flight przed pierwszym callem okazał się konieczny, ale niewystarczający. Timeout może uruchomić drugi płatny call, dlatego koszt jednej próby jest mnożony przez `1 + max_retries`, a tuż przed każdą próbą system ponownie czyta kanoniczne `model_usage`. Review wykryło jeszcze, że brak capu był akceptowany przez bibliotekę, a resume podnosiło domyślny cap wraz z kosztem. Po korekcie cap jest obowiązkowy dla realnego calla i absolutny dla resume. Wynik: 257 testów offline, 0 USD.

### 2026-07-13 — Task 9: naprawa po pierwszym realnym B, bez ponowienia

Realne A1 i cztery A2 przetrwały, lecz B wyczerpało 2200 tokenów i urwało JSON. Offline dodano osobny błąd truncation, limit 3000 poparty estymatą oraz krótsze pola promptu. Błąd nie uruchamia retry: zapisuje usage raz, nie tworzy karty, zostawia research w `SOURCES_COMPLETE`, a ogólny audit kończy `FAILED` z czasem i przyczyną. Salvage poprawnych linii JSONL A1 pozostał bez zmian, a prior usage jest liczony dokładnie raz. Historycznej bazy nie zmieniono. 174 testy celowane (włącznie z cost ledger) i 351 pełnych przeszło bez API; 0 USD.

### 2026-07-13 — kontrolowana naprawa historycznego auditu

Po osobnej zgodzie właściciela utworzono backup SQLite i snapshoty wszystkich rekordów powiązanych z runem. W transakcji `BEGIN IMMEDIATE` ponownie sprawdzono konto, topic, staged `SOURCES_COMPLETE`, cztery VERIFIED, sześć wpisów usage, koszt 0,170050 USD oraz ślad `max_tokens`/truncation. Warunkowy UPDATE z CAS zmienił dokładnie jeden rekord i tylko trzy pola: `runs.status`, `finished_at`, `error`. Po zamknięciu i ponownym otwarciu bazy hash każdego pozostałego zbioru był identyczny. Nie wykonano API ani resume; dodatkowy koszt 0 USD.

### 2026-07-13 — jedno B domknęło run bez powtarzania A1/A2

Po trzeciej, osobnej zgodzie — tym razem na płatny resume — preflight potwierdził sześć wcześniejszych usage i 0,170050 USD. PolicyEngine dopuścił projected 0,196300 przy absolutnym capie 0,20. Oficjalna komenda wykonała wyłącznie B z limitem 3000 i zerem retry. Odpowiedź zakończyła się `end_turn`, 1904/2402 tokenów, zero search; nowy koszt 0,013914 USD. Finalizacja ustawiła SUCCESS/COMPLETE/USED i kartę #2 z czterema VERIFIED. Karta jakościowo dostała REJECT, więc Etap 0 zakończył się dowodem działającego systemu, a nie materiałem gotowym do publikacji. Etapu 1 nie rozpoczęto.

### 2026-07-13 — pierwszy bezpłatny blocker przed workerami Etapu 1

Przed zbudowaniem kolejki zajrzeliśmy do najniższej warstwy płatnego calla. Był tam szeroki `except Exception`, który nazywał timeoutem zarówno zerwane połączenie, jak i zły klucz, brak uprawnień czy błędne żądanie. Dodaliśmy typy dla timeout/network/429/5xx/401/403/400–422/404/unknown. Automatyczne ponowienie jest możliwe tylko dla jawnej listy transient i zawsze zaczyna się od kolejnej kontroli budżetu. Brak usage nie jest zapisywany jako koszt zero; P2-19 pozostaje otwarte. 382 testy przeszły offline, koszt 0 USD. Nie powstał scheduler, job, worker ani migracja; kod czeka na niezależne review bez commita.

Kolejne review znalazło drobny, lecz ważny P1: typ istniał w pamięci, ale audit przechowywał tylko jego komunikat. Wspólny formatter zapisuje teraz np. `[discover_sources] ResearchInvalidRequestError(status_code=422, retryable=False): ...` w runie, research_runie i logu etapu. Nie kopiuje raw response ani obiektów SDK, redaguje sekrety i ogranicza długość. 406 testów przeszło offline; retry, koszt i lifecycle nie zmieniły się.

Ostatnie review wykazało jeszcze dwie szczeliny: SDK wkładało body do własnego tekstu błędu, a samotny `Bearer token` omijał regex. Mapper nie przenosi już tekstu SDK — zostawia wyłącznie klasę i status — a audit redaguje każdy wariant Bearer. Marker syntetycznego body nie dotarł do SQLite; 411 testów przeszło offline, bez API i kosztu.

## 2026-07-13 — Karta nie może przeżyć własnego zakończenia

Po syntezie B nie wystarczało już, że baza potrafiła ustawić `COMPLETE` i `USED` atomowo. Karta i jej źródła były zapisywane wcześniej, w osobnych commitach. Awaria po drugim źródle mogła zostawić materiał bez zakończonego runu.

Nowy krok kończy staged B jednym zapisem transakcyjnym: najpierw sprawdza relację run–research_run–temat–konto, koszt i karty A2; potem zapisuje kartę, wszystkie źródła, B SUCCESS oraz razem COMPLETE, terminalny run i USED. Testy psują każdy z tych momentów. Po reopen SQLite nie ma wtedy ani połowy karty, ani fałszywego sukcesu.

To była wyłącznie praca offline: 420 testów, brak API, brak realnego researchu i koszt 0 USD. Scheduler, joby i workery nadal nie powstały.

## 2026-07-13 — Transakcja potrzebuje też pamięci o zgodzie

Pierwsza poprawka umiała już cofnąć połowę zapisu, ale wciąż pytała proces o dwie rzeczy, których proces nie powinien sam rozstrzygać: czy wolno ponownie użyć tematu i czy wolno podnieść nieudany run. Dwa booleany były wygodne, lecz ich wygoda była myląca — po restarcie nie było wiadomo, czy force naprawdę należał do tego runu.

Dlatego force zapisuje się teraz przy konkretnym `research_run`, a finał dostaje jeden typowany kontekst: świeży, wznowiony B, forced albo forced-wznowiony B. Resume niesie snapshot poprzedniej porażki i porównuje go ponownie z bazą. Gdy temat, konto, marker błędu albo wcześniejsza karta nie pasują, preflight zatrzymuje się przed clientem i przed nowym usage.

Testy nie zatrzymały się na „błąd po drugim źródle”. Wstrzyknęły awarię w trzynastu miejscach, zamknęły SQLite i otworzyły ją od nowa. Za każdym razem baza pamiętała dokładnie stan sprzed próby. Równie ważne: zmiana kolejności tych samych źródeł nie jest nowym wynikiem. Forced resume przechodzi też przez osobne połączenie SQLite, a stary timestamp CAS zatrzymuje preflight. **446 testów**, 0 USD, bez API, researchu, schedulerów, jobów i workerów; zmiany czekają na niezależne review.

## 2026-07-13 — Najpierw język systemu, potem system

Zanim powstanie content pipeline, opisaliśmy jego granice w `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`. To nie jest generator ani plan publikowania. To słownik, który rozdziela artykuły A1–A9, lokalne Notes N1–N16, publiczne działania Etapu 6 i metryki Etapu 7.

Najważniejsza reguła brzmi banalnie, ale chroni przed rytmem udającym strategię: harmonogram tworzy kandydatów, nie obowiązek. Słaby materiał ma dostać `SKIP` z nazwanym powodem, a nie automatycznego następcę. NIA i build log dostają też osobne konta, głosy, pamięć i metryki; techniczna historia projektu nie może przypadkiem wejść do publicznego głosu NIA.

Praca była wyłącznie dokumentacyjna: brak kodu, migracji, bazy, API, publikacji, commita i kosztu. Pełny system pozostaje planem na Etapy 3, 6 i 7.

## 2026-07-13 — „Nic nie zmieniam” też może być błędem

Końcowe review F4 znalazło paradoks idempotencji. Finalizer niczego nie zapisywał przy powtórzeniu COMPLETE, ale sprawdzał zgodność karty przed pytaniem, czy caller ma prawo nazwać ten run force albo resume. Brak mutacji nie był więc dowodem poprawności kontraktu.

Naprawa przesunęła walidację mode przed no-op. Świeży i forced run muszą nadal pasować do trwałego markera; resume dodatkowo pokazuje wcześniejszą porażkę B z tym samym markerem i timestampem CAS. Testy po reopen potwierdzają, że zły mode nie zmienia nawet timestampu. **449 testów**, zero API i 0 USD.

## 2026-07-13 — Raport nie jest jeszcze systemem

Pełny raport Fable dostał własny snapshot, zamiast kolejnego skrótu. Osobno zapisaliśmy to, co raport twierdzi, i to, co projekt naprawdę ma: jego dane są mieszane, kosztorysy niewalidowane, a formaty, routing, Notes i metryki należą dopiero do przyszłych etapów. To ważne rozdzielenie — dokument może pokazać kierunek, ale nie może udawać działającego generatora ani rosnącego konta.

## 2026-07-13 — Jeden publiczny skrót nie może być bocznym wejściem

Po poprzednich poprawkach staged B miało prawidłowy atomowy finał, ale starszy skrót do finalizacji nadal umiał przyjąć ten sam flow. To wyglądało niewinnie: dostawał kartę i koszt, ustawiał statusy, a przy COMPLETE nawet grzecznie zwracał no-op. Właśnie to było błędem — omijał kontekst fresh/resume/force, sprawdzenie A2 i wspólną transakcję karty, źródeł oraz B SUCCESS.

Teraz `finalize_research_success` i jego alias są czytelnie legacy: tylko `single` i `two_stage`. Każdy staged run — oczekujący, ukończony lub nieudany — kończy się typowanym błędem zanim kod użyje kosztu albo dotknie lifecycle. Audyt znalazł jeszcze ogólny `finish_run`, który potrafił wpisać samo staged `SUCCESS` lub `DRY_RUN`; dla tych dwóch wyników też odmawia, nie blokując zapisu porażki. Jedyny finał staged pozostaje w helperze, który sam liczy koszt z `model_usage`.

Testy zamykają bazę i otwierają ją od nowa po każdej odmowie. Porównują kartę, źródła, audit B, usage, koszty, timestampy, błędy, ID karty i marker force. Legacy dalej działa. Wynik: **454 testy**, brak API, realnego researchu, migracji i koszt **0 USD**; zmiany nadal czekają na niezależne review.

## 2026-07-13 — Kolejka zaczyna się od odmowy dubla

Worker jeszcze nie istnieje, ale jego przyszły błąd można było zobaczyć zawczasu: dwa procesy patrzą na ten sam pusty job, oba uznają go za swój, a potem każdy ma uczciwie wyglądający log. To nie jest problem kolejki w pamięci, tylko problem trwałego prawa do działania.

Dlatego najpierw powstała sama granica: job ma klucz idempotencji, research ma jeden aktywny temat na konto, a lease bierze się i przedłuża wyłącznie atomowo. Gdy lease browsera znika, system nie udaje, że wie, czy kliknięcie zaszło — zapisuje `NEEDS_VERIFICATION`. Zwykły lokalny krok może wrócić do kolejki, ale tylko przed wyczerpaniem prób.

Druga granica jest finansowa. Rezerwacja nie udaje kosztu i nie zmienia `model_usage`; tylko blokuje miejsce w limicie, zanim dwa przyszłe joby osobno uznają, że stać je na ten sam dolar. Dziewięć nowych testów używa osobnych SQLite, bariery i reopen. **463 testy**, zero API i 0 USD. Worker pozostaje następnym, osobnym krokiem.

## 2026-07-13 — Worker może być mały, jeśli umie odmówić

Następny krok nie zamienił kolejki w autonomiczny automat od wszystkiego. Jeden worker bierze najwyżej jeden job, a dispatcher zna tylko dwa bezpieczne zdania: lokalne „nic nie rób” oraz research z dosłownym `dry_run=true`. Nie rozumie nazw funkcji, modułów, ścieżek ani opcji, które ktoś mógłby przemycić w JSON-ie.

Przed każdym jobem pyta bazę o pięć flag. Brak flagi jest odmową, uszkodzony JSON jest odmową, safe mode jest odmową. To ważniejsze niż wygodny default: worker może zatrzymać się zbyt wcześnie, ale nie może przypadkiem zacząć płatnego researchu albo kliknąć w publiczny interfejs. Nawet gdy flaga paid/browser byłaby ustawiona, ten etap wciąż odmawia obu klas akcji.

Research nie dostał drugiego pipeline'u. Worker wszedł przez istniejący offlineowy punkt i użył FakeResearchClienta; zaraz po powstaniu runu zapisał jego ID w jobie przez CAS. Jeśli lease zniknie, worker nie może już powiedzieć „DONE”. Jeśli poprzedni proces zniknął przed skutkiem zewnętrznym, istniejąca recovery oddaje bezpieczny job kolejce; po markerze skutku pozostaje `NEEDS_VERIFICATION`.

To nadal nie jest dowód gotowości do działania na zewnątrz. Jest dowód lokalny: **19 nowych testów**, dwa połączenia SQLite z barierą, restart/reopen, heartbeat, utrata lease i kontrolowane oczekiwanie pustej kolejki; pełny suite ma **489 testów**. API, sieć, realna baza, paid/browser i koszt pozostały nietknięte: **0 USD**.

### 2026-07-13 — Odczyt zegara przenieśliśmy za drzwi SQLite

Końcowe review znalazło detal, który w systemie współbieżnym nie był detalem: część operacji zapamiętywała „teraz”, a dopiero potem czekała na write lock. Jeśli lease kończył się podczas czekania, stary czas mógłby udawać świeże uprawnienie. Każda chroniona operacja lifecycle, recovery i rezerwacji bierze więc `Clock.now()` dopiero po `BEGIN IMMEDIATE`; granica pozostała prosta: owner ma prawo dokładnie do `lease_expires_at >= now`, recovery działa dopiero dla `< now`.

Drugi problem dotyczył pliku, który wyglądał jak księga, choć nią nie jest. `model_usage` w SQLite jest kanonem. `COSTS.csv` powstaje po commitcie jako wygodny, odtwarzalny eksport; kontrolowana awaria appendu daje ostrzeżenie, nie może już zmienić poprawnego wyniku researchu. Trzeci P1 domknął nietypowy wyjątek po utworzeniu runu: zamiast zakończyć sam job, worker atomowo ustawia job, run i research_run na `FAILED`.

Testy użyły prawdziwych wątków, osobnych połączeń plikowej SQLite i kontrolowanego zegara: operacja startowała przed expiry, blokowała się na locku, zegar przechodził za granicę, a po zwolnieniu locka nie mogła nic zapisać. Ta sama próba obejmuje fenced usage, success, failure oraz rezerwację/zwolnienie. Jest też test heartbeat↔recovery, dwa testy awarii CSV i reopen z `integrity_check=ok`. Wynik: **42 restart acceptance**, **683 testy** pełnego suite, 0 USD, bez API, browsera, publikacji ani zmiany prawdziwej bazy. Etap 1 wraca tylko do **candidate complete, awaiting independent review**.

## 2026-07-13 — Sam identyfikator runu jest już historią, nie zaproszeniem do retry

Kolejna mała korekta dotyczy chwili między powstaniem researchu a końcem joba. Worker zdążył utworzyć run i zapisać jego ID, ale mógł zniknąć zanim zapisał `DONE`. Dawniej recovery oddałoby taki job kolejce, a nowy worker musiałby wybierać między ponownym researchiem i ślepą odmową.

Wybraliśmy trzecią drogę: `run_id` zostaje trwałym śladem, a job przechodzi do `NEEDS_VERIFICATION` z krótkim reason code. Rezerwacja budżetu też zostaje, bo system nie zgaduje, czy etap nie zdążył zrobić czegoś istotnego. Nie ma tu resume, nie ma nowego API i nie ma automatycznej naprawy stanu — jest świadome zatrzymanie przed dublem.

Przy okazji CAS przestał znaczyć tylko „to samo konto”. Przed przypięciem SQLite sprawdza rodzaj joba, workflow, topic, workflow runu oraz właściwy wpis `research_runs`. Testy symulują nie ten topic, konto, flow, owner i wygasły lease; po każdym przypadku baza jest otwierana ponownie. Wynik: **512 testów**, zero sieci, API i koszt **0 USD**.

## 2026-07-13 — Zatrzymanie osieroconego runu nie jest wznowieniem

Gdy proces znikał w połowie pracy, rekord `RUNNING` mógł zostać w bazie bez końca. Nowy reaper nie zgaduje wyniku i nie budzi researchu ponownie. Dostaje jawny próg wieku, najpierw prosi kolejkę o recovery lease, a dopiero potem może wpisać `STOPPED` z krótkim reasonem audytowym.

Najważniejszy hamulec jest celowo nudny: run z jobem `QUEUED`, `LEASED` albo `RUNNING` nie jest dotykany. Po wygasłym lease przypięty research staje się `NEEDS_VERIFICATION`; wtedy run można zamknąć, ale rezerwacja zostaje i worker nie ma czego claimować. Dwa reapery i terminalizacja ścigają się na SQLite przez CAS, więc kończy się dokładnie jeden stan.

Komenda `reap-runs --once --stale-after-seconds X` jest osobnym, ręcznie wywoływanym narzędziem offline. Nie uruchamia API, nie startuje workera, nie jest schedulerem i nie jest resume. Po tej korekcie suite ma **529 testów**, nadal przy koszcie **0 USD**.

## 2026-07-13 — Długi job nie może zgubić prawa do pracy

Worker potrafił już przypomnieć o lease przed i po pracy, ale między tymi punktami mógł wykonywać synchroniczny dispatch długo na tyle, by prawo do joba wygasło. Nie dodaliśmy drugiej kolejki ani nowej definicji lease. Zamiast tego na czas dispatchu powstaje mały, niedaemonowy strażnik z własnym połączeniem SQLite. Co dwadzieścia sekund prosi istniejący atomowy heartbeat o przedłużenie sześćdziesięciosekundowego lease, a potem zawsze kończy i czeka na własny wątek.

To nie jest mechanizm ratowania pracy za wszelką cenę. Jeśli lease przejął ktoś inny albo już wygasł, strażnik nie może go wskrzesić. Worker nie zapisuje wtedy `DONE`; nawet gdy dispatcher równocześnie zgłasza własny błąd, utrata lease ma pierwszeństwo. Nie ma retry dispatchu, API, sieci, realnego researchu ani testu na publicznym koncie.

Piętnaście testów sterowanych Event/Barrier sprawdziło długi dispatch, recovery, obcego właściciela, wygaśnięcie, zamknięcie wątku, pustą kolejkę i offlineowy research dry-run. Pełny suite ma **548 testów**, a hash prawdziwej bazy przed i po jest identyczny. Koszt: **0 USD**.

## 2026-07-13 — Korekta P1: strażnik nie może zatrzymać procesu

Powyższy wpis opisuje pierwszy wariant strażnika. Po review P1 wątek jest daemonem wyłącznie jako ostatnia osłona procesu, nie jako zastępstwo sprzątania. Worker nadal zawsze ustawia stop event, budzi waiter, czeka tylko przez ograniczony timeout i sprawdza, czy wątek nadal żyje. Zwykle strażnik kończy się i zostaje dołączony. Jeżeli factory, heartbeat, waiter albo `close` pozostają zablokowane, timeout nie czeka dalej: worker nie może wtedy zapisać `DONE`, a odblokowany później strażnik widzi stop event, zanim wykona kolejny heartbeat.

`lost_lease` i `failure` żyją tylko w pamięci strażnika. Stan trwały pozostaje w SQLite, a nierozstrzygnięte sytuacje trafiają do recovery/reconciliation. Pierwotnych **15** testów periodic heartbeat uzupełniło **11** testów bounded start/stop i błędów infrastrukturalnych: razem **26** bezpośrednich testów heartbeat. `test_worker_runtime.py` ma **59 passed**, pełny suite **566 passed**, hash `data/agent.db` pozostał identyczny, bez API, sieci i researchu. Koszt: **0 USD**.

## 2026-07-13 — Sprzątanie po awarii nie musi uruchamiać pracy

Jednorazowy reaper umiał odzyskać wygasły lease i zatrzymać stary run, ale nie był wygodnym, kontrolowanym mechanizmem utrzymania. Dodaliśmy więc osobny `MaintenanceRunner`, a nie drugi worker. Każdy przebieg otwiera własną SQLite, bierze jeden czas, najpierw prosi istniejące recovery o uporządkowanie jobów, dopiero potem przekazuje próg do istniejącego reapera i kontrolowanie zamyka połączenie. Jeśli sama operacja i `close()` zawodzą razem, komunikat zachowuje pierwotny błąd operacji oraz dodatkowy błąd cleanupu; samo nieudane zamknięcie także nie może udawać sukcesu.

`maintain --once` robi dokładnie jeden przebieg. `maintain --poll` zaczyna od razu, czeka stały interwał dopiero po zakończonym cyklu i nigdy nie nakłada cykli na siebie. Stop event, zły próg, błąd factory, recovery, reapera, close albo waitera kończą pętlę zamiast uruchamiać retry. To nadal nie jest cron ani usługa działająca sama po starcie.

Najważniejsza granica pozostała nudna: maintenance nie claimuje jobów, nie uruchamia workera, researchu ani resume i nie zgaduje sukcesu. Działa nawet przy wyłączonym workerze, safe mode i kill switchu, bo porządkowanie trwałego audytu nie jest akcją zewnętrzną. **26 deterministycznych testów** obejmuje kolejność, active Event wait, błędy primary/cleanup, cleanup po `KeyboardInterrupt`, rezerwację/run_id, dwa połączenia SQLite po close→reopen i CLI; pełny suite ma **592 passed**. Bez API, sieci, zmiany realnej bazy i kosztu: **0 USD**.

## 2026-07-13 — Godzina joba staje się decyzją, zanim kolejka go zobaczy

Kolejka miała już pole na najwcześniejszą godzinę uruchomienia, lecz sama liczba w bazie nie tworzy jeszcze harmonogramu. Nowa polityka wybiera tę godzinę **przed** zapisem joba: dostaje jawny czas „teraz”, strefę IANA oraz listę lokalnych okien redakcyjnych. Jeśli bieżąca chwila mieści się w oknie, job może wejść do kolejki od razu; jeśli nie, trafia na początek następnego. Wskazana przyszła godzina zostaje zachowana tylko wtedy, gdy należy do okna. Czas z przeszłości jest odmową, nie pretekstem do cichego „uruchom teraz”.

To ważne zwłaszcza w dni zmiany czasu. Niejednoznaczna godzina jesienią ma z góry wybraną wcześniejszą interpretację, a nieistniejący start wiosną przesuwa się do pierwszej prawdziwej minuty po luce. Wszystko jest zapisywane w UTC wraz z krótkim kodem przyczyny, a nie wolnym komentarzem. Dopiero atomowy claim sprawdza, czy `earliest_run_at` już nadeszło. Job czekający nie dostaje lease, nie zwiększa attempts i nie uruchamia workera.

Dodana komenda tworzy wyłącznie lokalny job researchu z `dry_run=true`; nie ma trybu realnego, dispatchu, API, sieci ani researchu. **31 testów** sprawdza okna, weekend, DST, zapis/reopen, współbieżność SQLite i idempotencję; pełny suite ma **623 test cases passed**. Nie zmieniono migracji ani prawdziwej bazy. Koszt: **0 USD**.

## 2026-07-13 — Trzy commity to nie jedna historia

Końcowy test restartu znalazł wadę, której zwykłe zielone testy nie pokazały. Worker najpierw trwale zapisywał run, potem jego researchowy odpowiednik, a dopiero na końcu wpisywał ID do joba. Gdy proces znikał w tej szczelinie, baza miała dwa osierocone rekordy, a kolejny worker — całkiem logicznie, lecz błędnie — tworzył drugi komplet.

Naprawa nie szuka „podobnego” runu i niczego nie sprząta po cichu. Jedna operacja `initialize_research_run_for_job` otwiera `BEGIN IMMEDIATE`, sprawdza prawo workera do lease, tworzy oba rekordy i wykonuje CAS `jobs.run_id IS NULL`; dopiero wtedy commit. Przerwanie przed commitem zostawia nic. Przerwanie po nim zostawia jeden, jasno przypięty komplet, który po expiry trafia do `NEEDS_VERIFICATION`, nie do powtórnego researchu.

Czternaście deterministycznych scenariuszy użyło plikowej SQLite, nowych runtime’ów po reopen, failpointów SQL oraz dwóch połączeń z `Barrier`. Sprawdziły też parity bezpośredniej usługi i workera, fencing starego ownera i granicę joba przyszłego. Pełny suite: **655 passed**. Nie było API, sieci, publikacji ani realnego kosztu. Etap 1 jest **candidate complete, awaiting independent review**.
## 2026-07-13 — Drugi P1 był sześć linijek za pierwszym

Pierwsza poprawka sprawiła, że job, run i research_run powstawały razem. Niezależne review zadało jednak lepsze pytanie: co może zrobić stary proces już po tym commicie? Odpowiedź była niewygodna. Zanim główny worker wracał z dispatchera i oglądał swój guard, pipeline potrafił dopisać usage, koszt, FAILED albo całą kartę. Lease wygasł, recovery przejęło historię, ale stary kod nadal miał zwykłe metody zapisu.

Naprawa nie polega na częstszym pytaniu wątku heartbeat. Po atomowej inicjalizacji powstaje zamknięty context z jobem, ownerem, runem i zegarem. Każdy zapis jobowego researchu otwiera SQLite `BEGIN IMMEDIATE`, dopiero po zdobyciu locka pobiera aktualny czas UTC i sprawdza pełną relację. Jeśli owner jest stary, lease wygasł albo job jest już `NEEDS_VERIFICATION`, pipeline kończy się bez usage, bez kosztu, bez FAILED i bez karty.

Macierz 26 scenariuszy psuje execution przed recovery, po recovery i podczas klienta. Dwa połączenia ruszają jednocześnie z recovery i stale write; oba nie mogą wygrać. Osobne failpointy psują moment po CAS i sam rollback, a pierwotny błąd nadal pozostaje pierwotny. Pełny suite ma 667 zielonych testów. Bez API, browsera i realnego researchu; koszt 0 USD. Etap 1 wraca tylko do **candidate complete, awaiting independent review**.

## 2026-07-14 — Sukces nie może mieć epilogu, który go unieważnia

Ostatni P1 był zdradliwie krótki. Pipeline RESEARCH umiał już atomowo zapisać kartę, źródła, wynik runu i zużyty temat. Po powrocie do workera następował jednak „porządkowy” heartbeat i zwykłe `complete_job`. To były dwa dodatkowe miejsca, w których po trwałym sukcesie mógł pojawić się wyjątek. Szeroki catch potrafił wtedy oznaczyć sam job jako FAILED — baza nie była uszkodzona technicznie, lecz opowiadała dwie sprzeczne historie.

Granica sukcesu została więc przesunięta tam, gdzie należy: do jednej transakcji SQLite. `finalize_job_research_execution` zapisuje teraz także `jobs=DONE`, końcowe czasy, wyczyszczony lease i zwolnioną rezerwację. Dispatcher zwraca mały, typowany wynik: workflow może powiedzieć, że sam zakończył lifecycle; tylko workflow wymagający ogólnego zakończenia oddaje tę pracę workerowi. Dlatego LOCAL nadal przechodzi przez generic completion, ale RESEARCH po commicie nie wykonuje już dodatkowego heartbeat, complete ani fail.

Test najpierw wymusił błąd czwartego heartbeat i był czerwony. Po naprawie sprawdza 53 scenariusze: awarie przed i po UPDATE joba, crash po commicie, pełną macierz wygasłego ownera przed recovery, zegar claimu po write locku oraz prawdziwy błąd ścieżki katalogu dla `COSTS.csv`. Wszystko działa wyłącznie na plikowej SQLite i fake researchu: **695 testów zielonych**, `integrity_check=ok`, bez API, browsera, publikacji i realnego researchu. Koszt tej pracy: **0 USD**. Etap 1 pozostaje **candidate complete, awaiting independent review**.

## 2026-07-14 — Jedna zgoda nie może zamienić się w trzy żądania

Następny audyt nie kwestionował już kolejki. Znalazł coś wcześniejszego: moment, w którym program oddaje sterowanie bibliotece dostawcy. Jedna linia bez jawnego ustawienia retry znaczyła, że SDK mogło po timeout albo 429 spróbować jeszcze raz. Dla zwykłej aplikacji bywa to wygodne. Dla systemu z limitem dziennym i osobną zgodą na każde płatne wywołanie jest to ukryte drugie „tak”.

WAVE 0A odjęła temu miejscu domysły. Każdy klient SDK dostaje zero retry i skończony timeout. Sam klient research też nie przechodzi drugi raz przez własną pętlę. Zwykłe komendy i worker stały się bezwarunkowo offline, nawet gdy środowisko przypadkiem zawiera klucz i `DRY_RUN=false`. Realny adapter może powstać tylko z jednej, jawnej komendy capped z `--real`; bez tej flagi zostaje estymata, nie klient. Cennik jest teraz bramką, a nie ozdobą: brak, zero, liczba ujemna, `NaN` lub nieskończoność zatrzymują realny run przed konstrukcją adaptera.

To nie zamyka Etapu 1. To przywraca znaczenie słowu „jedna próba”, ale ten etap naprawy przypomniał jeszcze jedną rzecz: test też może naruszyć granicę, którą ma sprawdzać. Pierwsza wersja testu zwykłego CLI nie przekazała ustawień aż do runnera i zapisała fake/dry-run artefakty do domyślnej bazy. Test został odizolowany, nie było sieci, API, publikacji ani kosztu, lecz nie znaleziono bitowej kopii poprzedniego pliku.

Po forensic review właściciel zatwierdził wariant **APPROVE WITH P2**. Nie próbowaliśmy udawać, że odnaleźliśmy dawną wersję pliku. Zamiast tego na osobnej kopii usunęliśmy tylko rekordy, które potrafiliśmy nazwać po ID i powiązać z testem, odtworzyliśmy cztery sekwencje, a potem dwa razy otworzyliśmy wynik tylko do odczytu. Zachowały się wszystkie prawdziwe ślady: trzynaście wpisów kosztowych o łącznej wartości 0,684580 USD oraz run `c01171bc` z kartą #2, czterema zweryfikowanymi źródłami i siedmioma wpisami usage. Dopiero wtedy, po backupie stanu po incydencie, kandydat zastąpił główny plik bazy.

Nowy baseline ma SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`. To **logiczne** odtworzenie, nie magiczne cofnięcie historii bajt po bajcie: brak starego snapshotu pozostaje faktem. Nie stwierdziliśmy utraty realnych danych.

Po niezależnym review WAVE 0A została formalnie zamknięta jako **APPROVED WITH P2**. Trzy punkty, które wymagały tej fali — P0-01 o ukrytej próbie SDK oraz P1-01/P1-02 o niejawnej ścieżce realnej i fail-open pricingu — są zamknięte. To nie jest jednak finał Etapu 1: pozostałe P1 nadal go blokują. Do backlogu trafiają trzy mniejsze rzeczy: twardszy test dokładnie na granicy `messages.create`, pełne wyprowadzenie cen do parametrów i poprawna kolejność aktualizowania dokumentów. Tak wygląda uczciwe zamknięcie: nie „wszystko gotowe”, tylko dokładnie wiadomo, co zostało domknięte, co nie, i dlaczego.

### [2026-07-14] WAVE 0B — od „uruchom” do trwałej intencji

Świeży `--real` nie robi już researchu w tym samym procesie. Po pricing/pre-flight zapisuje tylko durable job i wypisuje jego identyfikator; ten sam `--operation-key` wraca do tego samego joba. Dopiero leased worker może przekroczyć granicę providera. Tuż przed nią powstaje atomowa rezerwacja oraz request_id, a po odpowiedzi usage rozlicza dokładny koszt w tym samym ledgerze. Nieznany wynik nie jest pretekstem do drugiego pytania — zostaje do ręcznej reconciliacji. Zrobiliśmy wyłącznie testy offline na bazach tymczasowych; nie było API ani kosztu. **`WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`**. Nie oznacza to zakończenia Etapu 1 ani gotowości realnego staged/resume.

## 2026-07-14 — Mała naprawa, dużo granic

Naprawa WAVE 0B.1 nie dodała kolejnego „sprytnego retry”. Zablokowała świeże realne wejścia bez durable joba, uczyniła operation key globalnym identity intentu i przebudowała constraints ledgeru. Testy obejmują zarówno poprawne ścieżki, jak i próby wstawienia niemożliwych stanów, wyścig dwóch procesów oraz historię, której nie wolno udawać, że jest kompletna.

## 2026-07-14 — WAVE 0B.2: ostatnia bramka jest przed callem

Drugi niezależny REJECT przesunął uwagę z kolejki na ostatnią linię przed płatnym requestem. Nie wystarczało, że workflow zwykle tworzył attempt: sam realny klient musi odmówić bez typowanego contextu, request_id i potwierdzenia `REQUEST_STARTED`. To zamyka drogę przez bezpośredni import, a nie tylko przez poprawny CLI.

Równolegle job przestał być poleceniem „uruchom research kiedyś”. Zawiera snapshot modelu, timeoutu, tokenów, cennika i wersji kontraktu; worker nie może po restarcie cicho przyjąć nowych ustawień środowiska. Migracja 0012 rozróżnia brak dawnych danych od sprzeczności: tylko pierwszy przypadek jest legacy, drugi zatrzymuje upgrade rollbackiem. Wszystko sprawdzone offline (752 testy, 0 USD); ten historyczny kandydat został później zastąpiony przez WAVE 0B.3.

## 2026-07-14 — WAVE 0B.3: czas z wczoraj nie może pozwolić na request jutro

Trzecia fala nie zmieniła kolejki ani budżetu. Pokazała coś mniejszego i groźniejszego: dwa równe napisy mogą być równie błędne, a timestamp zbudowany minutę wcześniej nie jest pozwoleniem na wysłanie requestu minutę później. Request ID jest teraz literalnie wyliczany z joba, etapu i numeru próby. Lease jest sprawdzany jeszcze raz z bieżącego zegara execution w transakcji tuż przed SDK.

To nie dodało ani jednego retry ani żadnej funkcji WAVE 1A. Dodało odmowę: arbitralne identity, expiry, takeover, zmieniony fence i `NEEDS_RECONCILIATION` kończą się przed callerem. Testy offline: 770, koszt: 0 USD. Status pozostaje kandydatem do niezależnego re-review.

## 2026-07-15 — Prompt też jest częścią obietnicy requestu

Końcowe review WAVE 0B znalazło prostą, lecz ważną lukę. System umiał zamrozić model, cennik i limit tokenów, ale nadal mógł wziąć pytanie i niszę z bieżącego obiektu już po enqueue. To znaczyło, że hash opisywał jedną obietnicę, a caller mógł dostać drugą.

Nie zapisaliśmy gotowego tekstu promptu ani dwóch równoległych wersji prawdy. Zapisujemy kanoniczne dane wejściowe promptu — pytanie, niszę, głębokość i guidance — razem ze stage oraz pełnym kontraktem requestu. Worker tworzy z nich plan po restarcie. Jeśli bieżący temat lub konto odpłyną od snapshotu, system nie „odświeża” promptu; zatrzymuje request przed fake callerem i zostawia attempt do reconciliation.

Druga połowa naprawy to kontrola historii tuż przed granicą callera. Jedna krótka transakcja sprawdza już nie tylko lease, lecz cały łańcuch job → run → research_run → attempt → intent. Terminalny run, brak research_run, zły flow, timestamp etapu albo zmieniony payload nie mogą zostawić usage, kosztu ani settlementu. Macierz 861 testów działała wyłącznie na fake callerach i tymczasowych SQLite; chroniona baza zachowała ten sam hash. To nadal nie jest formalne zamknięcie WAVE 0B: materiał czeka na niezależny re-review.

## 2026-07-15 — WAVE 0B: trzy stare liczniki, jedna aktualna liczba

**HISTORYCZNE:** 2026-07-14 wynik W0B-REV-05 wynosił 770 testów; 2026-07-15 procesowy kernel i trwały intent dały 823; bezpośrednio przed W0B-REV-06 pełny lifecycle miał 861. Po naprawie limitu requestu W0B-REV-06 historyczna kontrola miała 873 testy i partycje 206/218/226/223. Każda z tych liczb opisuje zakończony moment, nie bieżący working tree.

Wcześniejszy REJECT obejmował CRITICAL W0B-REV-06: `max_tokens` zapisywał się i docierał do callera, ale rezerwacja wciąż liczyła stałe 3000. Poprawka poprowadziła jedną trwałą wartość przez `intent.max_tokens → caller → estimate → policy → reservation → usage → settlement`. Jeśli actual przekracza rezerwację, jedna transakcja utrwala dokładnie jeden usage, ustawia `NEEDS_RECONCILIATION` i kod `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION`; nie ma SUCCESS, Research Card ani attempt #2. W0B-REV-06/07/08 są technicznie zamknięte; ówczesny audyt Claude’a, poprzedzający bieżący re-review W0B-RR-01, nie znalazł nowego CRITICAL ani MAJOR w kodzie.

## 2026-07-15 — W0B-REV-09/10: kronika i arytmetyka muszą mówić to samo

W0B-REV-09 był niewygodny, lecz prosty: ta obowiązkowa kronika nie nadążyła za naprawami. W0B-REV-10 był jeszcze mniejszy: estymator i `UsageTracker` zaokrąglały Pythonowym `round`, gdy intent i storage używały `ROUND_HALF_UP`. Nie powstał drugi paid pipeline. Zamiast tego wspólny helper ustalił jedną regułę: `Decimal(str(value)) → quantize(Decimal("0.000001"), ROUND_HALF_UP)`. Najpierw sumujemy małe składniki, potem raz przekraczamy granicę kwoty; cache kosztu, rezerwacja, usage i settlement widzą tę samą wartość.

Usunięto też tylko dwa potwierdzone śmieciowe ślady: legacy fresh-provider block znajdował się po bezwarunkowym `return`, a `_ORIGINAL_DBAPI2_CONNECT` nie miał żadnego użycia. Świeży real nadal tylko enqueuje, real resume nadal odmawia, a dispatcher pozostał jedynym rootem realnego klienta.

Historyczny runner W0B-REV-09/10 użył pełnego SHA-256 każdego UTF-8 node ID, potraktowanego jako big-endian integer modulo 4. Pokrycie exact-once wyniosło **211 / 222 / 229 / 225 = 887**, bez BOM, duplikatów, pominięć ani nadmiarowych node IDs. Granice `0.0000004/.5/.6`, `0.0000015`, `0.1234565`, `0.1234575`, cache read/write/web, storage, settlement ±1 mikro-USD i fake caller → usage → settlement są testowane wyłącznie na fake callerach i tymczasowych SQLite. WAVE 0B pozostaje `CANDIDATE` do niezależnego re-review; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

Bezpieczny snapshot przed naprawą tokenów: `%USERPROFILE%\Desktop\agent-project-snapshots\wave0b-pre-token-fix-20260715-112833`. Niepełny snapshot `wave0b-pre-token-fix-20260715-112526` jest oznaczony **NIE UŻYWAĆ**. Chroniona baza nie została zmieniona.

## 2026-07-15 — W0B-RR-01: ostatnie zaokrąglenie jest jedynym zaokrągleniem

Niezależny re-review znalazł MAJOR ukryty między modułami: koszt pojedynczego źródła był już skwantyzowany, gdy potem mnożono go dla staged research. Policy, persisted sumy i CLI również nie wszędzie odcinały float przed decyzją. Naprawa nie zrobiła nowej architektury. Zostawiła składowe jako `Decimal`, mnoży je i sumuje tam, gdzie są jeszcze surowe, a raz `ROUND_HALF_UP` zamyka publiczną kwotę. Dwa razy `0.0000005` kończą jako `0.000001`, trzy razy jako `0.000002`.

Po tej zmianie pełny runner ma **894** testy: **213 / 224 / 231 / 226**, dokładnie raz każdy UTF-8 node ID przez pełny SHA-256 modulo 4, bez BOM, duplikatów, pominięć i nadmiaru. Testy używają fake callerów i tymczasowych SQLite. `max_tokens` pozostaje wspólną wartością dla estimate, rezerwacji i callera; nadwyżka actual nadal daje jeden usage oraz `NEEDS_RECONCILIATION`. WAVE 0B pozostaje `CANDIDATE`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-16 — systemowy zegar dostał prawo tylko do uruchomienia istniejących drzwi

Końcowy pakiet Etapu 1 nie dodał nowego schedulera domenowego. Windows Task Scheduler dostał dwa launchery: jeden uruchamia worker dokładnie raz w trybie `--offline-only`, drugi wykonuje jeden cykl recovery→reaper. Jawny Python i katalog roboczy eliminują przypadkowe uruchomienie innego środowiska, `IgnoreNew` blokuje overlap, a stdout/stderr trafiają do lokalnego `runtime/logs/`. Żadnego zadania nie zarejestrowano.

Równolegle powstał raport, który otwiera SQLite wyłącznie read-only i mówi `UNKNOWN/BLOCKED`, gdy nie ma dowodu. Procedura migracyjna robi backup i kandydata, migruje tylko kopię `0009→0014`, zachowuje 13 legacy usage i 0,684580 USD oraz przygotowuje pięć wyłączonych flag. Produkcyjny plik pozostał na 0009. Dowód: 1052/1052 testy offline i exact-once coverage czterech partycji. Status: `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; Etap 1 nie jest zamknięty, live API zabronione.

## 2026-07-16 — jedna procedura migracji musi umieć także bezpiecznie przegrać

Późniejsza pierwsza próba produkcyjna przeszła technicznie, ale została cofnięta, ponieważ dodatkowy test błędnie wymagał fizycznej nieobecności WAL i SHM. Pełny restore przywrócił i bitowo potwierdził schemat 0009. To zmieniło procedurę, nie stan Etapu 1: druga próba nadal nie została zatwierdzona ani wykonana.

Istniejący moduł i CLI dostały jeden executor in-place. Zanim otworzy źródłową SQLite, musi potwierdzić zgodę, branch/HEAD, stary fingerprint, ciszę procesów/uchwytów/tasków, pełny backup DB/WAL/SHM, poprawny rehearsal i brak driftu. Pusty WAL oraz obecny SHM są legalne; niezerowy WAL lub journal zatrzymują. Po otwarciu każdy błąd uruchamia pełny restore plików, nigdy reverse SQL. Storage i migracja korzystają z jednego profilu: `kill_switch` i `safe_mode` są prawdziwe, worker/paid/browser fałszywe. Całość powstała i jest testowana na bazach tymczasowych; produkcyjna baza pozostała na 0009, bez nowego baseline'u, API i zadań Windows.

Gdy migracja została już wykonana, przygotowano ostatni brakujący element przed jednym kontrolowanym testem na żywo: bezpieczny sposób, w jaki człowiek może otworzyć i natychmiast zamknąć tryb płatny. Najpierw rozdzielono pytanie o cenę od pliku sekretów: powstał osobny, wersjonowany cennik, w którym każdy profil ma jawny status — przykładowy albo zatwierdzony — oraz przypisany model. Dopóki właściciel ręcznie nie wpisze i nie oznaczy konkretnych cen jako zatwierdzone, żadne realne uruchomienie nie startuje. Następnie limit długości pojedynczej odpowiedzi przestał być zaszyty na sztywno: można go teraz świadomie ustawić niżej, a ta sama liczba przechodzi identycznie przez zapis zlecenia, żądanie i szacunek kosztu.

Sercem tego kroku jest jedno polecenie, które prowadzi cały przebieg za rękę. Sprawdza gałąź, wersję kodu i odcisk bazy, upewnia się, że nic nie działa w tle, że istnieje dokładnie jedno oczekiwane zadanie i że nie ma miejsca na drugą próbę ani na przeglądarkę. Dopiero wtedy — w jednej niepodzielnej operacji i z wyłącznikiem zdejmowanym na końcu — otwiera minimalny profil, wykonuje dokładnie jeden cykl, a w bloku „na pewno" przywraca stan zamknięty, tym razem z wyłącznikiem ustawianym jako pierwszy. Jeśli program padnie pomiędzy zmianami, zostawiony ślad w katalogu roboczym wymusza zamknięcie przy następnym starcie i jest widoczny w raporcie. W tej fali cały ten mechanizm istnieje, jest w całości przetestowany na atrapach i tymczasowych bazach, ale realne wykonanie pozostaje wyłączone — to wciąż kandydat czekający na niezależny przegląd i osobną zgodę.

## 2026-07-17 — launcher dostał akt urodzenia, nie immunitet

Pierwsza zgoda live skończyła się jeszcze przed providerem. Strażnik procesów zobaczył w command line własnych przodków nazwę `controlled-live-once` i uznał ich za konkurencyjnego operatora. Najłatwiejsza poprawka — ignorować ten tekst — ukryłaby także prawdziwe drugie uruchomienie. Zamiast allowlisty PowerShella powstał więc dowód pokrewieństwa: każdy wykluczany przodek musi być dokładnym parentem w jednym snapshotcie, mieć pełną tożsamość, właściwy czas powstania i ten sam jednoznaczny entrypoint. Cmd, bash i PowerShell nie dostają specjalnych praw tylko za nazwę.

Do tego dołożono drugi, niezależny wymiar: raport odmowy. „Preflight failed” mówi, gdzie system się zatrzymał; „processes present” mówi dlaczego. Oba kody są teraz zachowane, razem z PID-ami, klasyfikacją, powodami i informacją, czy proces należał do udowodnionego ancestry. Command line przechodzi redakcję sekretów i promptów. Osobne polecenie może uruchomić dokładnie ten sam probe i zwrócić PASS/STOP bez otwierania bazy, tworzenia providera czy zmiany wyłączników. Review zatwierdził LA-02, ale nadal nie jest to przycisk „spróbuj ponownie”: druga zgoda nie istnieje.
## 2026-07-17 — Checkpoint LA-02 zamknął kod, nie kolejkę

Review zatwierdził ancestry i diagnostykę bez potrzeby drugiego live. P2 cleanup nie dotykał klasyfikatora: ujednolicił liczby testów i statusy, dopisał procedurę false STOP oraz ukrył wyłącznie lokalny pricing profile dokładną regułą `.gitignore`.

Najważniejszy stan nie zmienił się ani o krok: provider request nie powstał, job wciąż ma `QUEUED/attempts=0`, gate jest `False`, a pięć flag pozostaje fail-closed. Checkpoint kończy LA-02 jako artefakt techniczny; nie zamienia jej w prawo do uruchomienia.

Przed przyszłą decyzją operator musi zamknąć procesy, które mogą nieść pełny tekst komendy, i z tego samego launchera uruchomić standalone quiescence check. Każdy `PROCESSES_PRESENT` kończy próbę jeszcze przed autoryzacją live.

## 2026-07-17 — Najpierw sprawdź klamkę, potem otwórz drzwi

Kolejny blocker był jeszcze bardziej dosłowny. Program otwierał bazę, a potem pytał system operacyjny, czy baza jest otwarta. Windows odpowiadał poprawnie: tak. Composition root brał własne połączenie za obcy uchwyt i nigdy nie mógł dojść do providera.

Sekwencję rozdzielono na dwie fazy. Najpierw ten sam canonical probe co w standalone sprawdza procesy, taski oraz DB/WAL/SHM bez otwierania SQLite. Dopiero PASS pozwala otworzyć główne storage. Potem system sprawdza ponownie SHA, schema, job, ceny, intent i flagi, tworzy marker i dopiero po drugim rechecku otwiera minimalny profil wykonania. Obcy read-only lub writable SQLite i osobne uchwyty WAL/SHM nadal blokują.

Po 1181 testach, pełnym fake CLI i standalone PASS jedna autoryzowana komenda dotarła do Anthropic dokładnie raz. HTTP 200 nie dał jednak karty: model zwrócił niepoprawny JSON. Ledger zachował `REQUEST_STARTED`, jedno usage i settlement 0,053182 USD, a job zakończył się `FAILED`. Infrastruktura osiągnęła pierwszy provider request; redakcja nie dostała jeszcze Research Card.

## 2026-07-17 — Jedna odpowiedź dostała własny kontrakt i własną teczkę

Review zatwierdził lifecycle LA-03, ale wskazał, że deterministyczny numer sesji pełnił dwie role naraz. Dobrze identyfikował tę samą logiczną operację, źle identyfikował kolejne fizyczne uruchomienia: każde trafiało do tego samego pliku i mogło przykryć poprzedni raport. Teraz nazwa teczki zachowuje stabilny session, lecz dodaje attempt, czas UTC i nonce. Idempotencja nie zjada historii.

Druga zmiana dotyczy odpowiedzi modelu. System przyjmuje jeden obiekt JSON albo jeden kompletny fence i niczego nie wycina ze środka prose. Każde pole ma jawny typ, a truncation jest nazywana truncation tylko wtedy, gdy provider naprawdę zwróci `stop_reason=max_tokens`. Raw i stop reason trafiają do prywatnej diagnostyki po tym samym jednym callu. W czternastu kontrpróbach caller nigdy nie został wywołany drugi raz.

Ostatni detal jest czysto kompozycyjny: wrapper nie może już sam wymyślić probe'a po otwarciu bazy. Musi dostać zamrożony wynik sprawdzenia wykonanego wcześniej. 1200 testów i cztery partycje potwierdzają całość offline. Nie powstał nowy request ani nowy koszt; Etap 1 nadal jest otwarty.

## 2026-07-17 — Naprawa po odrzuceniu pierwszego pakietu P2

Review wykazał, że ogromny legalny numer JSON mógł wyjść poza typowaną ścieżkę i ominąć księgowanie. Score jest teraz sprawdzany jako `Decimal` przed konwersją. Ten sam pakiet zaostrzył fence do literalnego `json`, rozpoznaje drugi scalar przez `raw_decode`, używa jednego jawnego czasu enqueue/wrappera oraz wspólnego sanitizera dla raportu i diagnostyki.

Diagnostic zapisuje sanitizowaną treść przez temp, file fsync, replace i directory fsync. Awaria każdego z tych kroków pozostaje best-effort: jedno usage, settlement i terminalny `FAILED` nie zmieniają się. Dowód kandydacki to 1235 testów i partycje `294+299+311+331`; zero nowego requestu i kosztu.

## 2026-07-17 — Pozytywny live zatrzymany przed pierwszą mutacją

Właściciel zatwierdził dokładnie jeden nowy request z pessimistic capem `0.105000 USD`, ale równocześnie zabronił zmian kodu. Preflight potwierdził branch/HEAD, czystą strefę chronionego kodu, approved pricing, budżet, fail-closed flags i canonical quiescence `PASS`. Tracked composition root nadal miał `REAL_CONTROLLED_LIVE_ENABLED = False`; bez zmiany kodu nie dało się przekazać `allow_execution=True`. Operacja zatrzymała się przed enqueue, markerem, workerem i SDK. DB pozostała `5BEA9E…C6D10`, nowy koszt `0.000000 USD`, werdykt `BLOCKED — LIVE PREFLIGHT DRIFT`.

## 2026-07-17 19:18 UTC — Późniejsza decyzja L1 i dokładnie jeden request

Właściciel jawnie zastąpił wcześniejszą interpretację i zezwolił implementerowi na minimalne `False→True→False`. Powstał nowy durable job, a canonical wrapper wykonał dokładnie jeden request Anthropic. HTTP 200 zakończył się `stop_reason=max_tokens`; parser zwrócił `ResearchTruncatedError`, więc karty nie utworzono. Koszt `0.060078 USD` został rozliczony raz, attempt ma `SETTLED`, wszystkie trzy stany wykonawcze są `FAILED`, a gate, flags, marker, lease i rezerwacja zostały domknięte. Nie wykonano retry.

## 2026-07-17 19:44 UTC — Większy sufit odsłonił drugi rodzaj granicy

Właściciel osobno autoryzował jeden request z `max_tokens=3000` i capem `0.127500 USD`. Tym razem Anthropic zakończył naturalnie (`stop_reason=end_turn`) przy 2727 output tokens, więc odpowiedź nie była ucięta. Nie stała się jednak poprawnym artefaktem: pole `sources[0].supports_claim` nie spełniło kontraktu `string_or_null` i fail-closed validator odmówił zapisania Research Card.

System rozliczył dokładnie jedną próbę: 19945 input, 2727 output, jeden search i `0.077160 USD`; attempt jest `SETTLED`, a job/run/research_run `FAILED`. Gate wrócił do `False` przed analizą, flags są fail-closed, marker zniknął, baza nie ma sidecarów. Nie wykonano retry ani naprawy odpowiedzi drugim requestem.

## 2026-07-17 20:46 UTC — Naprawiony kontrakt nie dostał kompletnej odpowiedzi

Po niezależnym `APPROVE` naprawy typów promptu właściciel autoryzował jeden nowy request z `max_tokens=3000`. Tym razem eksperyment nie dotarł do miejsca, które miał sprawdzić: Anthropic zakończył HTTP 200 z `stop_reason=max_tokens`, a parser poprawnie nazwał wynik `ResearchTruncatedError` zamiast walidować fragment JSON. Typy `supports_claim` i `citable_numbers` nie zostały więc ocenione live.

System rozliczył dokładnie jedną próbę: 16381 input, 3155 output, jeden search i `0.074312 USD`. Attempt jest `SETTLED`, job/run/research_run `FAILED`, karta nie powstała. Gate wrócił do `False` przed analizą, flags są fail-closed, marker zniknął, baza nie ma sidecarów. Nie wykonano retry ani drugiego requestu.

## 2026-07-18 — Kontrakt rozmiaru odpowiedzi zamiast zgadywania limitu

Po trzech realnych próbach, w których dwa razy odpowiedź została ucięta mimo różnych limitów, przestaliśmy podnosić `max_tokens` na wyczucie. Fala offline prześledziła cały płatny flow (limit pochodzi wyłącznie z zamrożonego intentu — żadna warstwa go nie nadpisuje) i z zapisanych surowych odpowiedzi wyliczyła dwie rzeczy: limit działa osobno na każdy segment generacji (dlatego usage 3155 przy limicie 3000 to nie błąd rozliczeń), a rachunek za output obejmuje niewidoczne tokeny wewnętrznego rozumowania i cytowań — od ~0,7k do ~2,2k tokenów przy identycznym prompcie.

Rozwiązanie ma trzy warstwy: prompt v3 z jawnym limitem liczności i długości każdego pola karty (kompaktowy jednoliniowy JSON, priorytet domknięcia obiektu nad szczegółami), deterministyczna walidacja po naszej stronie (przekroczenie = typowany błąd, koszt zaksięgowany, zero retry i zero cichego obcinania) oraz wyliczony profil: 6000 tokenów = 3198 (payload dokładnie na granicach kontraktu) + 2300 (najgorszy zmierzony niewidoczny narzut) + 502 marginesu. Do tego pomiar `thinking_tokens` w diagnostyce — następne ucięcie będzie policzalne, nie zgadywane. Regresja wzrosła z 1248 do 1288 testów; produkcyjna baza pozostała bajt-identyczna, a live czeka na niezależny review.

## 2026-07-18 04:48 UTC — Pierwsza kompletna karta, nadal bez automatycznej publikacji

Niezależny review zamknął falę z sześcioma nieblokującymi uwagami P2, a właściciel dopuścił dokładnie jeden request. Tym razem limit nie został zgadnięty: prompt v3 dostał 6000 tokenów i jeden search. Anthropic zakończył `end_turn`; odpowiedź miała 4928 znaków, przeszła parser, schema, wszystkie limity pól i bramkę injection. Po raz pierwszy realny pipeline zapisał Research Card — job, run i research_run zakończyły się odpowiednio `DONE`, `SUCCESS` i `COMPLETE`.

To nie był jednak skrót do publikacji. Karta zawierała pięć źródeł, lecz gate redakcyjny wydał `REJECT/WEAK_SOURCES`. System udowodnił więc dwie rzeczy naraz: potrafi bez retry utworzyć kompletny artefakt i potrafi odmówić rekomendacji, gdy jakość dowodów jest za słaba. Jedyny request kosztował `0.063278 USD`; gate wrócił do `False`, a kolejna próba nie jest autoryzowana.

## 2026-07-18 — Niezależne potwierdzenie nie jest przyciskiem „uruchom ponownie”

Po wyniku technicznym implementera przyszedł osobny review. Reviewer nie udawał, że wykonał drugi pełny suite: uruchomił 223 własne wąskie testy, sprawdził exact-once oraz bajtową identyczność kodu i testów z wcześniej zaakceptowanym wynikiem 1288/1288. Nie znalazł CRITICAL, MAJOR ani nowego MINOR i wydał `APPROVE`. Dopiero potem właściciel formalnie przyjął positive-live gate Etapu 2.

To zamknięcie jest granicą dowodową, nie startem kolejnego etapu. Etap 2 nadal nie ruszył, następny request nie jest autoryzowany, browser i publikacja pozostają zablokowane, a gate i pięć flag są fail-closed. Working tree może przejść do checkpointu dopiero po osobnej zgodzie właściciela na commit.

## 2026-07-18 — Naprawa okna awarii po rozliczeniu

Końcowy review PR #1 znalazł okno, w którym attempt był już finansowo `SETTLED`, ale crash mógł przerwać zapis terminalnych stanów joba i runów. Nowa migracja `0015` wprowadza osobne zdarzenie `EXECUTION_RECOVERY`: nie dotyka kosztu ani usage, tylko domyka lifecycle po sprawdzeniu kanonicznego wyniku, lineage i braku żywego fence. Zgodne powtórzenie jest idempotentne, a każdy konflikt zatrzymuje naprawę.

Właściciel nie wymagał przepisywania historii prywatnego brancha. Zamiast tego końcowe drzewo przywrócono do jednego kanonicznego podręcznika pisania zgodnego z `main`. Kandydat przeszedł 1311 testów, cztery partycje i niezależne kontrpróby; nie uruchomiono providera, produkcyjnej migracji, browsera ani publikacji.

## 2026-07-18 — Otwarcie programu nie może być zgodą na migrację

Kolejny review pokazał prosty, ale poważny błąd granicy: zwykłe otwarcie SQLite uruchamiało wszystkie brakujące migracje. To oznaczało, że kod potrzebujący nowej tabeli mógł sam zmienić produkcję z `0014` na `0015`, choć właściciel zatwierdził dotąd tylko kod i wymagał osobnej decyzji dla danych.

Rozdzieliliśmy te czynności. Runtime najpierw zagląda do istniejącego ledgera w trybie immutable. Jeżeli nie widzi dokładnie wersji, dla której został zbudowany, zatrzymuje się zanim powstanie worker, job, marker, zmiana flag lub możliwość dotarcia do providera. Samo `open()` nie zakłada już bazy i nie „pomaga” przez migrację. Utworzenie nowej bazy oraz przejście `0014→0015` mają jawne, osobno nazwane wejścia; drugie wymaga konkretnej ścieżki i potwierdzenia, stosuje tylko jedną migrację i bezpiecznie rozpoznaje powtórzenie.

Najważniejsza kontrpróba odtworzyła wcześniejszy błąd na kopii tymczasowej: zapisaliśmy SHA, rozmiar, mtime, ledger i brak sidecarów schematu `0014`, uruchomiliśmy zwykły runtime i dostaliśmy typowaną odmowę. Każdy bajt oraz wszystkie liczniki pozostały takie same. Pełny wynik wzrósł do 1328 testów, cztery sekwencyjne partycje dały `318+322+339+349`, a trzy QA zakończyły się `8/8`, `4/4` i `10/10`. Produkcyjna baza nadal ma `0014`; nie uruchomiliśmy migracji, API, browsera ani publikacji. To nadal kandydat do niezależnego review, nie zgoda na merge.

## 2026-07-18 — Druga bramka musi być przed pierwszą mutacją

Wąski re-review znalazł jeszcze jedną szczelinę. Pierwsza kontrola była bezpieczna i immutable, ale zaraz po niej używaliśmy zwykłego połączenia SQLite. Gdy w tej krótkiej przerwie plik znikał, SQLite zakładał nową pustą bazę. Gdy plik został podmieniony na starszy, program mógł przełączyć jego journal mode, zanim druga kontrola powiedziała „stop”. Odmowa była poprawna, lecz przychodziła o jedną mutację za późno.

Poprawka jest mała: runtime otwiera teraz wyłącznie istniejący plik przez `mode=rw`, bez tworzenia katalogu, bazy i bez PRAGMA. Na dokładnie tym uchwycie ponownie czyta ledger. Dopiero schema `0015` pozwala przygotować połączenie do zapisu. Test usunięcia kończy się bez odtworzonego pliku; test podmiany zachowuje identyczne SHA, rozmiar, mtime, ledger i brak sidecarów. Worker i granica providera nie powstają.

Pełny suite ma teraz 1331 testów, cztery sekwencyjne partycje `320+322+339+350`, a QA schema gate `17/17`. Produkcyjna baza pozostała na `0014` i nie została otwarta do zapisu. Nie było API, kosztu, browsera, publikacji ani merge. PR #1 jest wyłącznie kandydatem do jednego wąskiego re-review tej kolejności: preflight → `mode=rw` → drugi gate → PRAGMA.

## 2026-07-18 — Merge zamknął branch, ale test nadal w nim mieszkał

Niezależny re-review wydał `APPROVE`, a PR #1 trafił do `main` jako merge commit `548cc65cad70eaef631fafff7c350845984d18e6`. Kod i historia przeszły poprawnie, produkcyjna baza pozostała na `0014`, lecz pierwszy pełny suite już na `main` dał jeden failure. Nie zawiódł system bezpieczeństwa — przeciwnie, zadziałał dokładnie tak, jak miał. Test przekazał mu na sztywno starą nazwę `dev/first-successful-research-card`, więc branch gate odpowiedział „nie”.

Mały checkpoint nie poluzował bramki. Test najpierw pyta kontrolowane repo, jaki branch i HEAD naprawdę symuluje, a potem przekazuje te wartości do subprocessu. Osobna negatywna próba nadal podaje obcy branch i potwierdza, że worker nie rusza. Dzięki temu test sprawdza kontrakt, nie pamiątkę po zakończonym branchu.

Po poprawce wrócił pełny wynik 1331/1331, exact-once `320+322+339+350`, QA `10/10`, `4/4` i `17/17`. Historyczny branch pozostaje zachowany, ale technicznie zakończony; każda kolejna praca zaczyna się na nowym branchu z `main`. Etap 2 nadal nie wystartował, live nie jest autoryzowany, migracja `0015` nie została zastosowana, a produkcyjna DB jest bajtowo identyczna.

## 2026-07-18 — Dowód zamiast opinii dostaje fundament: cytat musi wskazać bajty

Etap 2 ruszył od najmniejszej rzeczy, która czyni „weryfikację" prawdziwą: od trwałego zapisu tego, co faktycznie pobrano. Do tej pory model mógł oznaczyć źródło jako zweryfikowane, a system nie miał żadnego sposobu, żeby to sprawdzić — treść strony nigdy nie przechodziła przez nasze ręce. Pierwsza fala Etapu 2 odwraca ten układ. Powstała warstwa evidence: każdy retrieval zapisuje URL żądany i końcowy, status, typ treści, rozmiary, flagę ucięcia oraz hashe całego łańcucha pochodzenia — od surowych bajtów, przez wyekstrahowany tekst, po jeden kanoniczny tekst do cytowania.

Najważniejsza decyzja tej fali brzmi: istnieje dokładnie jedna funkcja kanonizacji tekstu, a offsety każdego cytatu wskazują wyłącznie utrwalony tekst kanoniczny. Excerpt nie jest „mniej więcej tym, co było na stronie" — jest dokładnym fragmentem od znaku X do znaku Y zapisanego kanonu, co można przeliczyć w każdej chwili. Weryfikator nie ufa niczemu zadeklarowanemu: sam przelicza długość i hash, sprawdza zakres, długość cytatu i to, czy cytat nie sięga w ucięty ogon dokumentu. Te same reguły zostały wkompilowane w triggery SQLite, więc nawet surowy zapis do bazy z pominięciem aplikacji nie umie utrwalić niespójnego dowodu — łącznie z próbami update'u i delete'u, bo historia evidence jest append-only.

Po drodze kontrpróby złapały klasyczną pułapkę SQL: warunek CHECK z wartością NULL nie jest fałszywy, tylko „nieznany", a „nieznany" przechodzi. Wiersz „OK" bez statusu HTTP prześlizgiwał się przez podłogę. Uszczelnienie to jedna linia (`IS NOT NULL` przed `BETWEEN`), ale znaleziona przez próbę obalenia własnego rozwiązania, nie przez czytanie kodu.

Celowo NIE zrobiliśmy dwóch rzeczy. Pipeline researchu nie został podłączony — dzisiejsze runy zachowują się identycznie jak wczoraj, a przełączenie `VERIFIED` na lokalny dowód to osobna fala z osobnym review. Nie powstał też realny adapter sieciowy: port fetch istnieje, ale jedyne implementacje to deterministyczny fake do testów i fail-closed placeholder, dokładnie jak w warstwie przeglądarki. Suita urosła z 1331 do 1408 testów, cztery partycje dają `339+342+356+371`, nowy skrypt QA obala 21 ataków na podłogi evidence, a produkcyjna baza pozostała bajtowo identyczna na schemacie `0014` — migracje `0015` i `0016` czekają na osobną decyzję właściciela.

## 2026-07-18 — Recenzent obalił nasz fundament czterema ciosami. I bardzo dobrze

Niezależny review pierwszej fali evidence nie przyszedł z gratulacjami. Przyszedł z czterema kontrprzykładami i werdyktem „odrzucone". Każdy z nich obalał zdanie, które sami napisaliśmy z dumą: „surowy zapis do bazy nie umie utrwalić niespójnego dowodu".

Pierwszy cios: znak NUL. SQLite liczy znaki tekstu tylko do pierwszego NUL — Python widzi cały tekst. Wystarczyło przemycić NUL do kanonu, a nasze „dokładne offsety" wskazywały w SQL co innego niż w Pythonie. Drugi: hashe. Baza pilnowała tylko, żeby hash WYGLĄDAŁ jak hash — 64 znaki hex. Fałszywy, ale ładny, przechodził. Trzeci: duplikaty. Unikalność cytatu opierała się o hash claimu podany przez piszącego, więc ten sam cytat z podmienionym hashem wchodził drugi raz. Czwarty: ekstraktor tekstu grzecznie czytał treść, którą sama strona deklarowała jako ukrytą — `hidden`, `display:none` — i podawał ją jako cytowalną.

Naprawa była jedną falą i jednym commitem. NUL jest teraz zakazany na poziomie schematu (sprawdzamy surowe bajty tekstu, nie zawodne `length()`). Hash kanonu i hash claimu przelicza sama baza — trigger woła deterministyczną funkcję rejestrowaną na każdym kontrolowanym połączeniu; kto jej nie ma, nie zapisze nic, kto ją ma, nie zapisze kłamstwa. Unikalność cytatu opiera się o rzeczywisty tekst claimu, nie o pole pochodne. Ukryte poddrzewa HTML wypadają z ekstrakcji w całości. Przy okazji dowód dostał właściciela: każdy retrieval i excerpt należy do konkretnego konta, a cudzego retrievalu nie da się ani odczytać, ani zacytować — nawet surowym SQL-em z wyłączonymi kluczami obcymi.

Równie ważne jest to, czego NIE naprawialiśmy: recenzent zgłosił też drobniejsze uwagi (progi długości cytatu, strefa czasowa, znaczenie jednego pola rozmiaru) — zostały świadomie w backlogu, bo fala naprawcza, która „przy okazji" poprawia wszystko, przestaje być weryfikowalna. Jesteśmy też uczciwi co do granic: hashe surowych bajtów i ekstrakcji to metadane audytowe naszego recordera, nie samosprawdzający się dowód w SQLite — bo samych surowych bajtów w bazie nie ma. Suita urosła z 1408 do 1454 testów, harness QA obala teraz 35 ataków zamiast 21, a produkcyjna baza nie drgnęła o bajt. Fala wraca do tego samego recenzenta.
