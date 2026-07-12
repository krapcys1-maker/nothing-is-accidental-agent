# ERRORS_AND_FAILURES

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
