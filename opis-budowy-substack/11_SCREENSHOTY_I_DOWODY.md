# 11 — SCREENSHOTY I DOWODY

> **2026-08-11 — PRE-LIVE CONTENT UNBLOCK:** `SCREENSHOT REQUIRED`. Bezpieczny diagram powinien pokazać targetowany approval/cap → dispatcher → `CONTENT_INDEPENDENT_REVIEW_UNAVAILABLE` przed writerem, obok brakującego durable ARTICLE_REVIEWER lifecycle, ordinary worker BLOCK i sześciu kontrprób novelty. Dowód tekstowy: 6/6 nowych, 473/473 affected, 2546/2546 full/collect, zero SDK/usage/kosztu w końcowym root, production DB PRE=POST.

> **2026-08-10 — produkcyjna migracja 0020→0030:** `SCREENSHOT REQUIRED`. Bezpieczny kadr powinien pokazać wyłącznie zanonimizowane liczniki: PRE `0020/20`, POST `0030/30`, integrity `ok`, FK `0`, preserve-state `211/2390/0`, retention acceptance `0`. Dowód tekstowy obejmuje byte-identical backup, 10 kroków exit `0`, brak sidecarów po close i zero kosztu.

> **2026-08-10 — MIGRATION TRANSACTIONALITY REPAIR 0026/0027:** `SCREENSHOT REQUIRED`. Browser był zabroniony. Bezpieczny kadr powinien pokazać failpoint → wspólny rollback schema/ledger → reopen → retry dla obu migracji oraz końcowe `0030/30`, integrity `ok`, FK `0`, preserve-state mismatch `0` i retention acceptance `0`. Dowód tekstowy: 4/4 nowych i 74/74 affected, koszt zero, produkcja i styl nietknięte.

## Cel pliku
Indeks screenshotów i dowodów. Każdy dowód: nazwa, data, opis, powiązany etap, informacja czy nadaje się do artykułu. Pliki graficzne trzymamy w `screenshots/` (obok tego pliku) oraz w `docs/screenshots/`. Tu jest indeks + lista **braków do zrobienia**.

> Zasada: screenshot **nie może** zawierać sekretów (kluczy, tokenów, cookies, danych logowania, adresu e-mail w kadrze).

## Szablon wpisu
```markdown
### SS-XX — <nazwa>
- **Plik:** screenshots/<nazwa>.png
- **Data:** YYYY-MM-DD
- **Opis:** co widać
- **Powiązany etap:** V1 / Etap 2 / ...
- **Do artykułu:** tak / nie / może
- **Status:** ZROBIONY | SCREENSHOT REQUIRED
```

---

## Stan: brak plików graficznych
Na 2026-07-11 **nie wykonano jeszcze żadnego screenshotu** — dotychczasowa praca to dokumentacja i kod uruchamiany w terminalu (dry_run). Poniżej lista dowodów **do zrobienia** (oznaczone `SCREENSHOT REQUIRED`). To dla właściciela lista „co teraz sfotografować".

## Dowody DO ZROBIENIA (priorytet do pierwszego artykułu)

### SS-01 — Struktura projektu — **SCREENSHOT REQUIRED**
- **Co uchwycić:** drzewo folderów `app/`, `docs/`, `opis-budowy-substack/`, `config/`, `tests/` (np. widok w eksploratorze lub `tree`). Bez zawartości `.env`.
- **Etap:** V2. **Do artykułu:** tak (pokazuje skalę i porządek).

### SS-02 — Testy przechodzą (44 passed) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wynik `pytest` z „44 passed".
- **Etap:** V2. **Do artykułu:** tak (dowód, że kod działa i jest testowany).

### SS-03 — Pierwszy scoring tematów — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wyjście `python -m app.main run-topics --count 6` (SELECTED=3, SCORED=2, REJECTED=1) z widocznymi punktami.
- **Etap:** V1. **Do artykułu:** tak.

### SS-04 — Deduplikacja w akcji (DUPLICATE=6) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** powtórny `run-topics` pokazujący wykryte duplikaty.
- **Etap:** V2. **Do artykułu:** może.

### SS-05 — Pierwszy Research Card — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wynik `run-research` (dry_run): karta z tezą, 3 źródła VERIFIED, PROCEED, injection flags 0.
- **Etap:** V2. **Do artykułu:** tak (serce researchu).

### SS-06 — Rejestr kosztów (`COSTS.csv`) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** zawartość `docs/COSTS.csv` — wiersze „dry_run estimate (no real charge)" ORAZ skorygowany wiersz z realną kwotą 0,25 USD (potwierdzoną w konsoli Anthropic).
- **Etap:** V1/V2/V3. **Do artykułu:** tak (uczciwość kosztowa — od szacunków dry_run po pierwszy prawdziwy wydatek).

### SS-07 — Fragment Policy Engine (kod) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** `check_budget` z komentarzem o priorytecie miesięcznym.
- **Etap:** V1. **Do artykułu:** może (dobra ilustracja „strażnika").

### SS-08 — Pierwsze realne wywołanie: pre-flight + wynik (nieudany) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** pełne wyjście `scripts/run_capped_research.py --topic-id 2 --max-cost-usd 0.30 --max-web-searches 6 --max-retries 1` — sekcje PRE-FLIGHT CHECKS i WYNIK (błąd JSON widoczny, klucz API NIE widoczny — tylko `True`/nazwa modelu). Bezpieczne do publikacji bez redakcji.
- **Etap:** Etap 1C. **Do artykułu:** tak — najmocniejszy dotychczasowy dowód „prawdziwa próba, prawdziwa porażka, pełna kontrola".

### SS-09 — 47 testów po naprawie buga kosztowego — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wynik `pytest` pokazujący „47 passed" (było 44), najlepiej razem z listą nowych testów (`test_real_usage_recorded_even_when_parse_fails` itd.).
- **Etap:** Etap 1C. **Do artykułu:** tak.

### SS-10-koszt — Wiersz COSTS.csv dla realnego wywołania — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wiersz w `docs/COSTS.csv` dla run_id `1b649314-...` — **zaktualizuj po korekcie**: teraz zawiera realną, potwierdzoną kwotę 0,25 USD (nie górną granicę).
- **Etap:** Etap 1C/1D. **Do artykułu:** tak (ilustruje uczciwość księgową — od „nieznane" do potwierdzonej liczby, bez zgadywania).

### SS-11-db — Bezpieczne podsumowanie wpisu w bazie (run + korekta kosztu) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wynik zapytania do `runs` dla run_id `1b649314-...` PRZED korektą (status=FAILED, cost_usd=0.0) i PO korekcie (cost_usd=0.25) — bez żadnych danych logowania, bez klucza. Pokazuje dokładnie to, co poszło nie tak w bazie i jak zostało naprawione.
- **Etap:** Etap 1C/1D. **Do artykułu:** może (bardziej techniczny dowód, dobry do artykułu 4 lub 8).

### SS-12-estymator — Projekcja kosztu dwuetapowego researchu (`--estimate-only`) — **SCREENSHOT REQUIRED**
- **Co uchwycić:** wyjście `scripts/run_capped_research.py --topic-id 2 --estimate-only` — pokazuje rozbicie kosztu etapu 1/etapu 2/razem, bez żadnego wywołania API (zero kosztu).
- **Etap:** Etap 1D. **Do artykułu:** tak (dobry dowód na „naprawiliśmy to, zanim wydaliśmy kolejnego centa").

## Dowody DO ZROBIENIA (kolejne etapy — jeszcze niemożliwe)
- **SS-10** Panel FastAPI (kolejka akceptacji) — po Etapie 3. `SCREENSHOT REQUIRED`
- **SS-11** Pierwszy szkic artykułu — po Etapie 2 (generator). `SCREENSHOT REQUIRED`
- **SS-12** Pierwsze logowanie do Substacka (login-success, bez danych w kadrze) — po Etapie 4. `SCREENSHOT REQUIRED`
- **SS-13** Pierwsza publikacja — po jawnej zgodzie, Etap 4+. `SCREENSHOT REQUIRED`
- **SS-14** Pierwsze statystyki publikacji — Etap 5. `SCREENSHOT REQUIRED`
- **SS-15** Pierwszy subskrybent — po publikacji. `SCREENSHOT REQUIRED`
- **SS-16** Pierwsza zmiana strategii (raport tygodniowy) — po ≥7 dniach. `SCREENSHOT REQUIRED`
- **SS-Task8** Lifecycle race — terminal z 44 testami Task 8 oraz pełnym `330 passed`, bez danych produkcyjnej bazy. `SCREENSHOT REQUIRED`; w zadaniu nie użyto Playwrighta.
- **SS-Task9** Pierwszy realny staged run — bezpieczny widok statusów A1/A2/B, 4 VERIFIED, `max_tokens`, koszt 0,170050 USD i cap 0,55 USD; bez raw response i sekretów. `SCREENSHOT REQUIRED`; do wykonania ręcznie po review, bez Playwrighta.

## Podsumowanie
- Dowodów zrobionych: **0**.
- Dowodów do zrobienia teraz (możliwych dziś): **10** (SS-01…SS-09 + SS-10-koszt).
- Dowodów odłożonych do kolejnych etapów: **7** (SS-10…SS-16 — numeracja etapowa, patrz sekcja niżej; SS-10-koszt to inny wpis, oznaczony słownie, żeby nie kolidować z SS-10 panelu).

## Powiązania
- `docs/SCREENSHOT_INDEX.md` (indeks techniczny), `screenshots/` (pliki), `16_MATERIAL_DO_PIERWSZEGO_ARTYKULU.md`

### Task 9 — dowód poprawki offline

Logi testów pokazują 174/174 testy celowane (włącznie z cost ledger, prior usage liczone raz i zachowaniem JSONL A1) oraz 351/351 pełnego suite. Screenshot pozostaje oznaczony `SCREENSHOT REQUIRED`: nie użyto Playwrighta ani przeglądarki i nie wolno eksponować prywatnego raw response. Dowodem trwałym przed screenshotem są testy, diff oraz wpis `SS-TASK9-FIX` w indeksie.

### Task 9 — dowód kontrolowanej naprawy statusu

`SCREENSHOT REQUIRED`: bezpieczny kadr może później pokazać jedynie zanonimizowane preconditions, `rowcount=1`, trzy zmienione pola i niezmienne agregaty kosztu/researchu. Playwrighta nie użyto. Obecny dowód stanowią SHA-256 backupu i bazy, logiczne snapshoty przed/po oraz wpis `task9-controlled-status-repair` w `docs/SCREENSHOT_INDEX.md`.

### Task 9 — pierwsza realna karta po resume B

`SCREENSHOT REQUIRED`: zanonimizowany lokalny raport powinien pokazać SUCCESS/COMPLETE/USED, card #2, 4 VERIFIED, `end_turn`, koszt nowego B 0,013914 i runu 0,183964/0,20 USD oraz jakościowe REJECT. Nie użyto Playwrighta ani przeglądarki; obecnym dowodem są SQLite po reopen, usage ledger i wpis `task9-first-real-card-resume-b` w indeksie.

### 2026-07-16 — skonsolidowany Etap 1

`SCREENSHOT REQUIRED` dopiero po niezależnym review. Bezpieczny kadr powinien pokazać: oba polecenia `plan` z `SYSTEM TASK NOT REGISTERED`, raport read-only z jawnym `UNKNOWN/BLOCKED`, copy-preflight na kopii z 14 migracjami/13 legacy/0,684580 i końcową weryfikację niezmiennego baselineu. Nie może pokazywać `.env`, danych bazy, prywatnych ścieżek ani sugerować, że zadania zarejestrowano lub produkcję zmigrowano.

### 2026-07-17 — LA-03 i pierwszy request

`SCREENSHOT REQUIRED`: zanonimizowany kadr powinien pokazać 1181/1181, fake CLI success, standalone PASS oraz bezpieczny trwały summary jednego attemptu: `REQUEST_STARTED`, `SETTLED`, 0,053182 USD, job/run/research_run `FAILED`, marker absent, flags i gate fail-closed, zero retry. Nie może zawierać klucza, promptu, raw response, execution tokenu ani pełnych command lines. Obrazu nie wykonano, bo przeglądarka była zabroniona, a terminal zawierał prywatne ścieżki.

### 2026-07-17 — P2 po review LA-03

`SCREENSHOT REQUIRED`: bezpieczny kadr powinien pokazać 1200/1200, partycje `290+293+304+313`, 14-case matrix oraz dwa różne report filenames zaczynające się tym samym session ID. Nie może pokazywać raw response, prywatnego katalogu debug, promptu, `.env`, pricing profile ani pełnej ścieżki chronionych plików. W tej fali obraz nie powstał; dowód pozostaje tekstowy i testowy.

## 2026-07-17 — Dowód naprawy NIA-P2-RV

`SCREENSHOT REQUIRED`: bezpieczny kadr może pokazać wyłącznie 1235/1235, partycje `294+299+311+331` i zanonimizowane wyniki kontrprób huge score, secret sanitizer, jawnego clocka, object+true oraz bare fence. Nie może zawierać raw payloadu sekretów, `.env`, pełnych command lines, produkcyjnej bazy ani prywatnych plików. Obraz nie powstał; mocniejszym dowodem są deterministyczne testy i byte-identical DB.

### 2026-07-17 — Gate pozostał zamknięty

`SCREENSHOT REQUIRED`: bezpieczny kadr może później pokazać quiescence `PASS`, zanonimizowany DB hash/rozmiar, pricing/cap, fail-closed flags i `REAL_CONTROLLED_LIVE_ENABLED=false`, bez `.env`, klucza, command lines i danych SQLite. Obrazu nie wykonano, bo browser był zabroniony.

### 2026-07-18 — Recovery po `SETTLED`

`SCREENSHOT REQUIRED`: bezpieczny kadr powinien pokazać `1311/1311`, partycje `314+319+333+345`, QA `4/4`, pusty finalny diff katalogu podręcznika względem `main` i niezmienny hash produkcyjnej DB. Nie może zawierać prywatnych ścieżek, `.env`, tokenów ani zawartości bazy. Dowodem tej fali pozostają logi testowe i kontrole Git/SQLite.

### 2026-07-19 — E2-C: sprawdzony adres trafia do transportu

`SCREENSHOT REQUIRED`: bezpieczny, zanonimizowany kadr powinien pokazać `1572/1572`, exact-once `378+389+394+411`, harnessy E2-C `13/13` i E2-B `13/13`, failpointy `4/4` oraz kontrpróbę: jeden resolver call, ten sam publiczny `selected_address` w fake transporcie, zachowany Host/SNI. Obrazu nie wykonano z powodu zakazu browsera i prywatnych ścieżek terminala. Nie wolno pokazać `.env`, pełnej bazy, prawdziwego przyszłego URL ani sugerować wykonanego Fetch.

### 2026-07-19 — Orchestrator migracji odmawia na późnym sidecarze

`SCREENSHOT REQUIRED`: bezpieczny kadr powinien pokazać `58/58`, full/exact-once `1630/1630`, partycje `390+398+412+430`, QA `30/30` oraz kontrpróbę z syntetycznym `-journal` utworzonym tuż przed writable open: `STALE_DATABASE_STATE`, brak migracji, sidecar nadal istnieje. Obrazu nie wykonano z powodu zakazu browsera i prywatnych ścieżek. Nie wolno pokazywać pełnego production SHA/path, `.env`, zawartości DB/snapshotu ani sugerować wykonanej migracji.

### 2026-07-22 — Jeden zatwierdzony job, drugi nietknięty

`SCREENSHOT REQUIRED`: zanonimizowany kadr powinien pokazać dwa joby w temp DB, jeden targetowany przez `claim_specific_job`, drugi nadal `QUEUED/attempts=0`, replay z zerem drugich requestów, restore pięciu flag oraz wynik `1854/1854`. Produkcja może być pokazana tylko jako skrócony hash, schema 0020, integrity/FK i brak sidecarów. Obrazu nie wykonano z powodu zakazu browsera i prywatnych bindingów; kadr nie może zawierać `.env`, promptu, approvalu, danych DB ani sugerować wykonanego live.

### 2026-07-23 — Jeden prawdziwy request i pełny durable checkpoint

`SCREENSHOT REQUIRED`: bezpieczny kadr powinien pokazać tylko zanonimizowane `SUCCESS`, HTTP 200, attempt 1 `SETTLED`, usage 1, cost `0.013128 USD`, generated 2, selected topic `21`, reconciliation false i identyczne fail-closed flags przed/po. Nie może zawierać `.env`, klucza, promptu, raw response, pełnych fingerprintów ani lokalnych ścieżek. Obrazu nie wykonano, ponieważ browser był zabroniony.
## 2026-07-23 — WAVE C2

`SCREENSHOT REQUIRED`. Screenshotu nie wykonano z powodu zakazu browsera i ryzyka ujawnienia lokalnych ścieżek lub prywatnego źródła stylu. Dowód tekstowy: C2 `22/22`, full/collect/exact unique `1945/1945`, zero skipped/xfail, koszt zero, produkcja nadal 0020.

## 2026-07-23 — WAVE C3

`SCREENSHOT REQUIRED`. Browser był zabroniony, a terminal zawiera prywatne ścieżki i fingerprinty. Bezpieczny kadr powinien pokazać logical route → jawna konfiguracja → fake SDK/caller → append-only result → usage/settlement → `PENDING_APPROVAL` oraz osobno odmowę missing config przed SDK i recovery bez drugiego calla.

Dowód tekstowy: C3 `26/26`, regresja `463/463`, full/collect/exact unique `1971/1971`, zero duplikatów/skipped/xfail/errors, koszt zero, produkcja nadal 0020. Kadr nie może zawierać raw style source, `.env`, secretu, draftu ani sugerować approvalu, merge, realnego API lub rozpoczęcia C4/C5.

## 2026-07-24 — WAVE C4

`SCREENSHOT REQUIRED`. Screenshotu nie wykonano: browser był zabroniony, a terminal zawiera pełne ścieżki i fingerprinty. Bezpieczny kadr powinien pokazać zanonimizowany flow current draft/evaluations/policy → Policy Engine → revalidation/fence → append-only audit → human-required albo autonomous outcome.

Dowód tekstowy: C4 `23/23`, full/collect/unique `1994/1994`, zero duplikatów/skipped/xfail/failures/errors, koszt zero, produkcja nadal 0020, kod 0024. Kadr nie może zawierać private style content, `.env`, promptu/draftu ani sugerować niezależnego approvalu lub zamknięcia C4.

## 2026-08-09 — Question semantic boundary

`SCREENSHOT REQUIRED`. Bezpieczny kadr powinien pokazać zanonimizowaną macierz question × reviewer output i dokładny durable audit pięciu supported ARTICLE cases. Browser był zabroniony; dowód tekstowy to 183/183, PRE-C5 291/291, affected 362/362, full/collect 2285/2285, produkcja i styl byte-identical, koszt zero. Bez `.env`, raw corpus, draftu, evidence content i pełnych ścieżek/hashów.

## 2026-08-09 — Model-family routing core

`SCREENSHOT REQUIRED`. Bezpieczny kadr powinien pokazać role→family→wersje 5/5.1/5.2/6→gates→jedno ACTIVE, stary frozen intent na N i nowy na N+1 oraz współbieżne `PROMOTED + NO_CHANGE`. Dowód tekstowy: new 31/31, affected 748/748, full/collect 2353/2353, exact duplicates 0, koszt zero. Bez `.env`, realnych model IDs/cen, produkcyjnych danych i sugestii realnego discovery, C5 lub approvalu.
