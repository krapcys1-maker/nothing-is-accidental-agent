# 09 — KOSZTY

## Cel pliku
Pełny obraz kosztów: API, web search, grafiki, koszt jednego artykułu, koszt jednego Research Card, koszt jednego subskrybenta, czas człowieka, koszt tygodnia i całego eksperymentu. Źródło prawdy liczbowej: tabela `model_usage` w bazie + `docs/COSTS.csv`. Tu jest wersja narracyjna + agregaty.

> **Aktualizacja 2026-07-11 (później tego samego dnia):** właściciel zweryfikował w konsoli Anthropic dokładny koszt pierwszego realnego wywołania: **0,25 USD** (0,21 USD tokeny + 0,04 USD web search). Zastępuje to wcześniejsze „0,00 USD" i „górna granica ≈0,095 USD" wszędzie w tym pliku. Przy okazji wyszło na jaw, że nasz szacunek PRZED wywołaniem był zaniżony o ~163% — naprawiony (patrz sekcja „Naprawa estymatora kosztu" niżej i `07_BLEDY_I_NIEUDANE_PROBY.md`).

## Szablon wpisu (agregat tygodniowy)
```markdown
### Tydzień <YYYY-Www>
- **Koszt API (model):**
- **Koszt web search:**
- **Koszt grafik:**
- **Liczba artykułów / Research Cards / Notes / komentarzy:**
- **Koszt na artykuł / na Research Card / na subskrybenta:**
- **Czas człowieka:**
- **Razem tydzień:**
```

---

## Budżet i polityka
- **Limit dzienny:** 2.00 USD. **Limit miesięczny:** 40.00 USD — **nadrzędny** (stop przy `month_to_date ≥ 40`, ADR-012).
- Budżet liczy **tylko wpisy realne** (`dry_run=0`); estymacje dry_run nie zużywają budżetu.
- Szacowany realistyczny koszt 30-dniowego testu (z założeń): **~20–55 USD** (bez czasu budowy).

## Rozbicie szacunków miesięcznych (z planu)
| Pozycja | Zakres/mies. | Uwagi |
|---|---|---|
| Model językowy (Anthropic) | 8–20 USD | `ModelRouter` + prompt caching obniżają koszt |
| Web search (research) | 3–10 USD | liczone per request w `model_usage` |
| Grafiki | ~0 USD w MVP | SVG-only (ADR-003) |
| Substack | 0 USD | — |
| VPS | 0 USD w MVP | lokalnie; chmura później |
| **Razem** | **~11–30 USD/mies.** | twardy sufit 40 USD |

## Dotychczasowe koszty (szacunki dry_run, 2026-07-11)
Z `docs/COSTS.csv` (realny koszt każdej pozycji = 0.00 USD; kolumna to **estymacja**):

| Zadanie | Model | Input tok. | Output tok. | Web search | Szac. koszt USD | Uwaga |
|---|---|---|---|---|---|---|
| audit-and-docs | — | 0 | 0 | 0 | 0.00 | audyt + dokumentacja, brak wywołań |
| topics (run 1) | claude-haiku-4-5 | 1200 | 600 | 0 | 0.0042 | dry_run estimate |
| topics (run 2) | claude-haiku-4-5 | 1200 | 600 | 0 | 0.0042 | dry_run estimate |
| research | claude-sonnet-5 | 3200 | 1200 | 4 | 0.0492 | dry_run estimate (web search dominuje) |
| topics (run 3) | claude-haiku-4-5 | 1200 | 600 | 0 | 0.0042 | dry_run estimate |
| research (REALNY, nieudany) | claude-sonnet-5 | n/d* | n/d* | 4 | **0.2500** | **REALNE wywołanie, POTWIERDZONE w konsoli Anthropic** (0,21 USD tokeny + 0,04 USD web search) — JSON ucięty, Research Card nie powstała, ale koszt jest realny i zmierzony |

*Rozbicie input/output tokenów nie jest dostępne na tym poziomie szczegółowości — panel Anthropic pokazał sumy kategorii (tokeny / web search), nie surowe liczby tokenów. Liczba wyszukiwań (4) wywnioskowana z 0,04 USD ÷ 0,01 USD/wyszukiwanie.

- **Suma szacunków dry_run:** ~0.062 USD. **Suma potwierdzona (zmierzona) realna: 0,25 USD.** To pierwszy prawdziwy wydatek w tym eksperymencie — 0,625% zatwierdzonego budżetu miesięcznego (40 USD).

## Koszty jednostkowe
- **Koszt jednego Research Card (dry_run, szacunek):** ~**0.05–0.12 USD** (dominuje web search; zależny od liczby zapytań i tokenów).
- **Koszt jednej REALNEJ, ale NIEUDANEJ próby Research Card (zmierzony, 2026-07-11):** **0,25 USD** — ważna liczba: pokazuje, że nawet nieudany research (bez finalnej karty) kosztuje niemal tyle, ile zakładaliśmy dla udanego. Poprzedni szacunek PRZED wywołaniem: 0,095 USD — **realny koszt był 2,63× wyższy (błąd ~+163%)**.
- **Koszt jednego scoringu tematów (batch):** ~**0.004 USD** (tani model, bez web search).
- **Koszt jednego artykułu:** **do zmierzenia** — pojawi się dopiero, gdy powstanie generator artykułów (draft + 3 audyty; wiele wywołań mocnego modelu). Wstępny rząd wielkości: kilkanaście–kilkadziesiąt centów za artykuł.
- **Koszt jednego subskrybenta:** **do zmierzenia** — wymaga realnej publikacji i metryk (Etap 4+). To jedna z kluczowych liczb końcowego artykułu.

## Naprawa estymatora kosztu (2026-07-11, ta sama sesja)
Po potwierdzeniu realnej kwoty (0,25 USD) zbudowano **kalibrowany estymator** (`app/research/cost_estimator.py`), który liczy koszt wyszukiwań proporcjonalnie do ich liczby (a nie jako stały „zapas"), z wymaganym marginesem bezpieczeństwa ≥50%. Jednocześnie podzielono research na **dwa kroki**: krok 1 (tylko szuka i zbiera fakty) i krok 2 (tylko analizuje już zebrane dane, zero wyszukiwania). Projekcja nowego podejścia:

| Krok | Web search | Szacowany koszt |
|---|---|---|
| Krok 1 — zbieranie źródeł | max 4 | ~0,36 USD |
| Krok 2 — analiza (zero wyszukiwania) | 0 | ~0,02 USD |
| **Razem (proponowany limit: 0,45 USD)** | | **~0,38 USD** |

Dla porównania: przeliczony na nowo (poprawny) szacunek dla STAREGO, jednokrokowego podejścia (te same ustawienia co nieudana próba) wynosi ~0,55 USD — nowe, dwuetapowe podejście jest **o ok. 31% tańsze** w najgorszym przypadku. **Żadne z tych wywołań jeszcze się nie odbyło** — to projekcja, nie zmierzony koszt; czeka na osobną zgodę właściciela.

## Stabilizacja wznawialności (2026-07-12) — bez zmian w sposobie liczenia kosztu
Etap „pełna wznawialność" (ADR-019) **nie zmienił** samego estymatora — liczby z sekcji wyżej wciąż obowiązują. Zmieniło się to, CO dzieje się z wynikami kroku 1, jeśli krok 2 się nie powiedzie: zamiast tracić je i zaczynać od zera, teraz można wznowić WYŁĄCZNIE krok 2 (bez ponownego, kosztownego wyszukiwania). To dodaje nową, tańszą pozycję kosztową:

| Scenariusz | Web search | Szacowany koszt |
|---|---|---|
| Pełna karta researchu od zera (krok 1 + krok 2) | ≤4 | ~0,38 USD |
| **Samo wznowienie kroku 2** (po awarii/błędzie kroku 1→2, źródła już w bazie) | **0** | **~0,02 USD** |

Praktyczne znaczenie: jeśli krok 2 zawiedzie (np. znowu ucięta odpowiedź) już PO opłaceniu kroku 1 (~0,36 USD), nie trzeba płacić za wyszukiwanie drugi raz — wznowienie kosztuje tylko ~0,02 USD zamiast ~0,38 USD od nowa. To bezpośrednia odpowiedź na ryzyko z `07_BLEDY_I_NIEUDANE_PROBY.md` („wyniki kroku 1 istniały tylko w pamięci"). **Zero nowych realnych wywołań wykonano w ramach tego etapu** — 73 testy zielone, wyłącznie na klientach zastępczych.

## Drugi realny test (2026-07-12 03:30 UTC) — zmierzony koszt niższy niż szacunek
Właściciel zatwierdził jeden kontrolowany realny test nowej architektury (`--topic-id 2 --mode two-stage --max-cost-usd 0.45`). Wynik: **krok 1 (zbieranie źródeł) nie zwrócił poprawnego JSON-a** — karta researchu znowu nie powstała. Mimo to koszt jest w pełni zmierzony i zapisany, bo mechanizm zachowania realnego zużycia przy błędzie (naprawiony po pierwszym incydencie) zadziałał poprawnie:

| Wielkość | Wartość |
|---|---|
| input_tokens | 75 728 |
| output_tokens | 1 619 |
| web_search_requests | 4 / 4 (cap wykorzystany w pełni) |
| **koszt rzeczywisty** | **0,123823 USD** |
| szacunek kroku 1 (pesymistyczny, z marginesem +50%) | 0,3615 USD |
| cap tego uruchomienia | 0,45 USD |

**Realny koszt był NIŻSZY od szacunku** (≈34% szacunku kroku 1) — odwrotnie niż przy pierwszym incydencie (11.07), gdzie realny koszt przebił szacunek o +163%. To dobra wiadomość o samym estymatorze: tym razem margines bezpieczeństwa zadziałał we właściwą stronę, nie kosztem złudnego poczucia bezpieczeństwa.

**Łączny realny koszt eksperymentu po dwóch próbach: 0,373823 USD** (0,25 + 0,123823), czyli **0,93% budżetu miesięcznego** (40 USD) — a wciąż nie mamy ani jednej udanej, kompletnej karty researchu. Uczciwy wniosek do artykułu: sam koszt research pipeline'u jest bardzo dobrze kontrolowany (poniżej 1% budżetu po dwóch próbach), ale **niezawodność** (czy w ogóle powstaje finalny wynik) to osobny, jeszcze nierozwiązany problem.

## Nowy estymator: dwie realne obserwacje zamiast jednej (2026-07-12, przebudowa architektury)
Po drugim realnym teście mamy już DWA prawdziwe punkty danych zamiast jednego — i różnią się między sobą znacząco:

| Próba | Koszt „na wyszukiwanie" | Pewność |
|---|---|---|
| 11.07 (stary, jednokrokowy) | ~0,04875 USD | wyliczone pośrednio (nie mieliśmy dokładnego rozbicia) |
| 12.07 (krok „zbierz źródła") | ~0,020956 USD | **zmierzone wprost** z bazy (dokładne liczby tokenów) |

Różnica ~2,3× między dwiema próbami pokazuje uczciwie, że nawet dwie realne obserwacje to wciąż przybliżenie — różne tematy mogą zwracać różną ilość treści z wyszukiwania. Dlatego nowy sposób liczenia kosztu **pokazuje obie wersje naraz**, zamiast jednej liczby:
- **„Bezpieczny sufit"** — do bramki, która decyduje, czy wolno zapłacić (używa WYŻSZEJ z dwóch obserwacji + margines bezpieczeństwa, celowo ostrożny).
- **„Środkowy szacunek"** — do pokazania człowiekowi, ile prawdopodobnie naprawdę wyjdzie (używa NOWSZEJ, dokładniej zmierzonej obserwacji, bez marginesu).

**Dlaczego to ważne:** to bezpośrednia odpowiedź na błąd z 11.07 („traktowaliśmy jeden szacunek jak pewnik") — teraz jawnie pokazujemy, że nawet „bezpieczny sufit" to nie to samo, co „ile naprawdę zapłacimy".

## Nowe projekcje po przebudowie architektury (krok 1 rozbity na szukanie + czytanie per źródło)

| Konfiguracja | Bezpieczny sufit | Środkowy szacunek |
|---|---|---|
| Domyślna (nowa architektura, A2=1500) | 0,4110 USD | 0,1628 USD |
| Historyczny mały wariant (2 wyszukiwania, 2 źródła, bez wyszukiwania per źródło, A2=1500) | **0,2235 USD** | 0,0934 USD |

Ciekawy szczegół: koszt CZYTANIA pojedynczego źródła (bez dodatkowego wyszukiwania — tylko na podstawie adresu/tytułu z kroku „szukanie") jest bardzo mały (grosze), bo nie ma w nim opłaty za wyszukiwanie — to dlatego mały proponowany test może pozwolić sobie na 2 źródła, mieszcząc się wygodnie w limicie 0,25 USD. **Zero nowych realnych wywołań wykonano przy tej przebudowie** — 85 testów zielonych, wyłącznie na danych zastępczych.

## Diagnostyka limitu A2 (2026-07-12) — koszt calla ≠ koszt runu

Pierwsze podejście zatrzymało się lokalnie przed requestem z powodu niezgodności `anthropic==0.37.1` / `httpx==0.28.1` (`proxies`). Koszt: **0,00 USD**. Po aktualizacji projektowego SDK do 0.116.0 wykonana wcześniej, zatwierdzona diagnostyka kandydata `id=3` dała:

| Wielkość | Wartość |
|---|---:|
| input_tokens | 14 394 |
| output_tokens | 915 |
| web_search_requests | 1 |
| stop_reason | end_turn |
| **koszt samego calla diagnostycznego** | **0,028969 USD** |
| **koszt skumulowany istniejącego runu po callu** | **0,126793 USD** |
| **realny koszt całego projektu po callu** | **0,500616 USD** |

Jednorazowe `max_tokens=5000` było wyłącznie sufitem diagnostycznym; produkcyjny default ustawiono na 1500. Kandydatów 1 i 2 nie ponawiano. Conservative estimate 0,1256 USD był bezpieczny, ale około **4,34×** wyższy od faktycznej ceny calla 0,028969 USD — nie był dokładną prognozą.

## Czas człowieka
- Dotychczas: sesja planistyczna + przeglądy etapów (2026-07-11). Do systematycznego pomiaru od Etapu 2 (akceptacje treści).
- Metryka docelowa: **minuty człowieka / artykuł** oraz **minuty człowieka / dzień**.

## Offline preflight pierwszej pełnej Research Card (2026-07-12)

Konfiguracja estimate-only: świeży run trzyetapowy, A1 z 1 wyszukiwaniem, maksymalnie 4 źródła, A2 z 1 wyszukiwaniem i 1500 tokenami na źródło, bez retry, normalny etap B.

| Etap | Oczekiwany | Konserwatywny |
|---|---:|---:|
| A1 | 0,033956 USD | 0,092625 USD |
| A2 × 4 | 0,153824 USD | 0,397500 USD |
| B | 0,013500 USD | 0,020250 USD |
| **Razem** | **0,201280 USD** | **0,510375 USD** |

Rekomendowany zatwierdzany cap: **0,55 USD**. Maksymalna liczba wyszukiwań wynikająca z konfiguracji to 5: jedno w A1 oraz po jednym dla najwyżej czterech źródeł A2. Jest to wyłącznie kalkulacja przed decyzją właściciela; nie wykonano żadnego API, więc koszt zadania wynosi 0,000000 USD, `docs/COSTS.csv` pozostaje bez nowego wiersza, a realny koszt projektu pozostaje 0,500616 USD.

## Koszt całego eksperymentu (na żywo, do domknięcia po 30 dniach)
| Składnik | Stan |
|---|---|
| **Realny koszt API do dziś (zmierzony, potwierdzony w bazie)** | **0,684580 USD** |
| Szacunek dry_run do dziś (nie liczy się do budżetu) | ~0.062 USD |
| Prognoza 30 dni | ~20–55 USD |
| Wykorzystanie budżetu miesięcznego (40 USD) | 1,71% |
| Kompletne strukturalnie Research Cards | **1** (karta #2: `research_runs.status=COMPLETE`, 4 źródła VERIFIED) |
| Research Cards zaakceptowane przez quality gate | **0** (karta #2: `REJECT` — `THESIS_UNSUPPORTED`, `CLAIMS_WITHOUT_SOURCES`) |
| Research Cards gotowe do publikacji | **0** |
| Czas budowy (człowiek) | do policzenia osobno |

**Zrobione:** wszystkie znane realne koszty są zapisane w bazie i `COSTS.csv`; call diagnostyczny (0,028969 USD) jest jawnie oddzielony od skumulowanego kosztu runu (0,126793 USD). Istnieje jedna kompletna strukturalnie realna karta researchu (#2), lecz quality gate nadał jej `REJECT`, dlatego żadna karta nie jest gotowa do publikacji. **Wciąż otwarte:** P1-5 i prawdziwy fetch źródła pozostają niezbudowane.

**Task 8:** 0,000000 USD. Wykonano wyłącznie lokalne zmiany kodu, SQLite i testy race; nie było API, researchu ani generowania tematów.

**Task 9:** 0,183964 USD za jeden staged run i późniejszy, osobno zatwierdzony resume B: A1 0,029243; cztery A2 łącznie 0,127903; pierwsze B 0,012904; udany resume B 0,013914. Resume wykorzystał 91,98% absolutnego capu 0,20 USD. Pięć searchy tylko w A1/A2, zero retry. Księga `model_usage`, `docs/COSTS.csv`, `runs.cost_usd` i `research_runs.total_cost_usd` są zgodne; kompletna karta #2 powstała, ale jakościowo ma REJECT.

## Jak koszty trafiają tutaj
Automatycznie: `UsageTracker` liczy koszt z cennika i dopisuje wiersz do `model_usage` (baza) **oraz** do `docs/COSTS.csv`. Ten plik (`09_KOSZTY.md`) agreguje je narracyjnie po każdym większym etapie i po każdym tygodniu (patrz `weekly-summaries/`).

## Powiązania
- `docs/COSTS.csv` (źródło), `app/llm/usage_tracker.py` (mechanizm), `10_FRAGMENTY_KODU.md` (fragment)
- `docs/DECISIONS.md` ADR-012/013, `weekly-summaries/`

### 2026-07-13 — koszt poprawki offline

- Nowe wywołania API: **0**; dodatkowy koszt: **0 USD**. Do `docs/COSTS.csv` nie dodano wiersza udającego realne usage.
- Historyczny Task 9 pozostaje **0,170050 USD**.
- Nowy limit B=3000: expected **0,017500 USD**, conservative **0,026250 USD**; fresh worst-case **0,516375 USD**, projected resume z prior usage **0,196300 USD**.

### 2026-07-13 — koszt kontrolowanego repair auditu

- Operacja była wyłącznie lokalna: **0,000000 USD**, bez API i resume.
- Nie zmieniono sześciu wpisów `model_usage` ani `runs.cost_usd`; historyczny koszt Task 9 pozostaje **0,170050 USD**.

### 2026-07-13 — koszt jedynego resume B

- Prior usage: **0,170050 USD**; conservative B: **0,026250 USD**; projected: **0,196300 USD**; cap całego runu: **0,20 USD**.
- Rzeczywisty nowy B: **0,013914 USD** (1904 input, 2402 output, zero search). Łączny Task 9: **0,183964 USD**, czyli 91,98% capu; zapas po fakcie **0,016036 USD**.
- Łączny realny koszt projektu: **0,684580 USD**, czyli 1,71% miesięcznego budżetu 40 USD. Siedem usage Task 9 i cache runu są zgodne; nie było retry ani drugiego calla.

### 2026-07-16 — skonsolidowany pakiet Etapu 1

- Koszt nowej pracy: **0,000000 USD**.
- Nie wykonano API, realnego SDK, web search, browsera ani publikacji.
- Migracja kopii sprawdza, że historyczne **0,684580 USD** pozostaje dokładnie tą samą kwotą przed i po `0009→0014`; nie dopisuje nowego usage.

### 2026-07-17 — zatwierdzony cap przyszłego controlled live

- Koszt bieżącego preflightu: **0,000000 USD**; bez providera, SDK i web search.
- Dla `max_tokens=1500` i jednego web search kod `Decimal` wyliczył: input-calibration `0,045000`, output max `0,015000`, search `0,010000`, projected `0,070000`, pessimistic z marginesem 50% `0,105000 USD`.
- Zatwierdzony cap wynosi `0,120000 USD`, więc zapas planu to `0,015000 USD`. Historyczny koszt miesiąca pozostaje `0,684580 USD`; maksymalny dopuszczony wzrost dla tej jednej operacji to `0,120000 USD`, ale nic nie zostało naliczone.

### 2026-07-17 — jedyna komenda live zatrzymana przed kosztem

- Rzeczywisty nowy koszt: **0,000000 USD**.
- Wrapper zakończył się `PREFLIGHT_FAILED` z `provider_request_started=false`; provider attempts i usage pozostały zerowe.
- Koszt miesiąca pozostał dokładnie **0,684580 USD**. Projected `0,070000` i pessimistic `0,105000 USD` nie stały się rachunkiem.

### 2026-07-17 — LA-02, naprawa bez requestu

- Rzeczywisty koszt WAVE LA-02: **0,000000 USD**.
- 1174 testy, Windows process snapshots i standalone subprocessy działały lokalnie na fake callerach i temp DB; nie użyto API, SDK ani web search.
- Job live pozostał `QUEUED/attempts=0`; brak provider attemptu i usage oznacza, że koszt miesiąca nadal wynosi **0,684580 USD**.

### 2026-07-17 — checkpoint LA-02 i P2 cleanup

- Rzeczywisty koszt checkpointu: **0,000000 USD**.
- Nie wykonano provider requestu, SDK, web search, browsera ani publikacji; nie powstał attempt ani usage.
- Koszt miesiąca pozostaje **0,684580 USD**. Planowane `0,070000`/`0,105000` i cap `0,120000 USD` nadal nie są rachunkiem ani zgodą na wydatek.

### 2026-07-17 — pierwszy request LA-03

- Rzeczywisty koszt: **0,053182 USD** przy capie `0,120000 USD` i rezerwacji `0,105000 USD`.
- Usage: 13306 input tokens, 1657 output tokens, jeden web search; dokładnie jeden attempt i zero retry.
- Provider zwrócił HTTP 200, ale niepoprawny JSON nie dał Research Card. Koszt został poprawnie rozliczony jako `SETTLED`, a job zakończył się `FAILED`.
- Miesięczny koszt wzrósł z **0,684580** do **0,737762 USD**. Niewykorzystana część rezerwacji została zwolniona.

### 2026-07-17 — P2 po review LA-03

- Forensics, parser matrix, historyczne raporty i frozen pre-storage wykonano offline: **0,000000 USD**.
- Nie było web search, provider requestu, retry, repair calla ani attemptu #2.
- Miesięczny koszt pozostaje **0,737762 USD**. Koszt historycznego failed requestu nie został usunięty ani policzony drugi raz.

## 2026-07-17 — Koszt naprawy NIA-P2-RV

- Nowe płatne wywołania: **0**.
- Koszt fali: **0,000000 USD**.
- Wszystkie próby korzystały z fake callerów i tymczasowych SQLite. Miesięczna suma pozostaje **0,737762 USD**; istniejącego usage nie zmieniono ani nie zdublowano.

## 2026-07-17 — Zablokowany controlled-live

Nowy koszt: `0.000000 USD`. Provider calls: 0; nowe usage: 0. Suma miesiąca pozostała `0.737762 USD`. Cap `0.105000 USD` został zweryfikowany, ale nie zarezerwowany, ponieważ zatrzymanie nastąpiło przed enqueue.

## 2026-07-18 — Fala kontraktu rozmiaru: 0 USD

Nowy koszt: `0.000000 USD` (zero requestów, fake callery i tymczasowe bazy). Suma miesiąca bez zmian: `0.949312 USD`. Następna próba — dopiero po niezależnym APPROVE i nowej zgodzie — ma wyliczony pesymistyczny sufit `0.172500 USD` (6000 tokenów, jeden web search, rekomendowany cap `0.20 USD`); nawet w najgorszym wariancie miesiąc zamknąłby się na `1.121812 USD` z 40 USD budżetu.

## 2026-07-18 — Naprawa PR #1: 0 USD

Implementacja recovery po `SETTLED`, 1311 testów, cztery partycje i skrypty QA użyły wyłącznie fake callerów i tymczasowych SQLite. Nowy koszt: `0.000000 USD`; suma miesiąca pozostaje `1.012590 USD`. Nie było provider calla, web search, browsera ani publikacji.

## 2026-07-19 — E2-C live-readiness: 0 USD

Pełna suita 1572, cztery partycje exact-once oraz harnessy E2-C `13/13` i E2-B `13/13` użyły wyłącznie fake resolverów, transportów/callerów i tymczasowych baz. Nowy koszt: `0.000000 USD`; suma miesiąca pozostaje `1.012590 USD`. Realny Fetch, DNS, HTTP, API, provider, browser i publikacja: 0.

## 2026-07-19 — Production Schema Migration Orchestrator: 0 USD

58 testów orchestratora, pełna suita/exact-once 1630, partycje `390+398+412+430`, QA i harnessy wykonały wyłącznie lokalne operacje na nowych temp SQLite. Nowy koszt: `0.000000 USD`; suma miesiąca pozostaje `1.012590 USD`. Produkcyjnej migracji, API, sieci, providera, browsera i publikacji: 0.

## 2026-07-22 — Targetowany entrypoint topic-generation: 0 USD

33 nowe testy i pełna suita 1854 użyły tylko fake callerów i nowych temp SQLite. Nowy koszt: `0.000000 USD`; nie wykonano controlled-live, API, SDK, sieci, browsera, publikacji ani migracji. Trzy syntetyczne rows utworzone chwilowo przez błędną ścieżkę fake fixture usunięto — nie były actual usage i nie zmieniają ledgeru.

## 2026-07-23 — Pierwszy targetowany TOPIC_GENERATION live: 0,013128 USD

Przed requestem estymata wynosiła `0.016202 USD`, pesymistyczny koszt i cap `0.024303 USD`. Rzeczywiste usage: 219 input, 1269 output, cache `0/0`, web search `0`; actual `0.013128 USD`. Dzienny ledger po operacji: `0.013128 USD`; miesięczny runtime ledger: `1.200044 USD`. Nie było retry ani drugiego attemptu.
## 2026-07-23 — WAVE C2

Koszt implementacji i QA C2 w ledgerze modelowym: `0.000000 USD`. Wszystkie writer attempts były fake, usage miało `dry_run=1`, a canonical actual cost wynosił zero. Nie wykonano realnego requestu ani kontrolowanego live.

## 2026-07-23 — WAVE C3

Koszt implementacji i QA C3: `0.000000 USD`. Wszystkie provider-ready próby używały fake SDK i fake callerów; usage, actual cost i run cost były dokładnie zerowe. Nie użyto realnych cen, API, sieci ani controlled-live.

## 2026-07-24 — WAVE C4

Koszt implementacji i QA C4: `0.000000 USD`. Granica decyzji działa na już utrwalonych artefaktach C3 i nie przyjmuje writera, callera ani SDK. Liczniki provider attempts, usage, settlementu i kosztu były identyczne przed i po decyzji. Produkcyjna baza nie została zmigrowana.

## 2026-08-09 — Question semantic boundary

Koszt implementacji i QA: `0.000000 USD`. 183 nowe przypadki kontraktu, 291 PRE-C5, 362 affected i 2285 pełnej suity wykonały się wyłącznie lokalnie z fake reviewerami i temp SQLite. Nie wykonano API, sieci, SDK, browsera, publikacji ani migracji produkcji.
