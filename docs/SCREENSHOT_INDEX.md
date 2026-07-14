# SCREENSHOT_INDEX

## Cel

Indeks wszystkich screenshotów eksperymentu. Screenshoty są dowodem działania i materiałem do końcowego artykułu. Pliki leżą w `docs/screenshots/`. Ten plik to czytelny spis; przy automatyzacji przeglądarki źródłem prawdy dla zrzutów systemowych jest też tabela `screenshots` w bazie.

## Lokalizacja i nazewnictwo

- Katalog: `docs/screenshots/`
- Konwencja nazw: `YYYY-MM-DD_HHMM_opis-etapu.png`
- Przykład: `2026-07-11_1840_first-article-generated.png`

## Co warto uchwycić (checklist etapów)

- [ ] pierwsza działająca wersja systemu
- [ ] panel zatwierdzania
- [ ] pierwsza wygenerowana publikacja (artykuł)
- [ ] pierwsza Note
- [ ] pierwszy komentarz
- [ ] pierwszy błąd Playwrighta
- [ ] pierwsze udane logowanie (ręczne)
- [ ] pierwsza publikacja
- [ ] statystyki
- [ ] koszty
- [ ] zmiana strategii
- [ ] porównanie wersji przed i po poprawie

## Zasady bezpieczeństwa (bezwzględne)

Nigdy nie zapisuj na screenshotach: kluczy API, haseł, zawartości `.env`, danych logowania, prywatnych wiadomości, wrażliwych danych osobowych. Jeśli taki element trafi na zrzut — usuń plik i odnotuj to.

## Gdy nie mogę wykonać screenshota samodzielnie

1. Dodaj wpis do tego pliku z oznaczeniem **SCREENSHOT REQUIRED**.
2. Opisz dokładnie, jaki ekran otworzyć.
3. Wskaż, co ma być widoczne.
4. Powiadom użytkownika w odpowiedzi.

## Szablon wpisu

```markdown
### [YYYY-MM-DD HH:MM] opis-etapu
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_opis-etapu.png
- **Data:** YYYY-MM-DD
- **Co pokazuje:** ...
- **Dlaczego ważny:** ...
- **Etap projektu:** np. Etap 3 — panel zatwierdzania
- **Status:** DONE | SCREENSHOT REQUIRED
```

---

## Wpisy — SCREENSHOT REQUIRED (stan początkowy, do zrobienia TERAZ)

> Te zrzuty dokumentują punkt zerowy eksperymentu. Nie czekamy na Etap 4 — rób je już teraz. Przy każdym: co otworzyć, co ma być widoczne, czego NIE może być widać.

### [—] 01_initial-folder-structure
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_initial-folder-structure.png
- **Co pokazuje:** początkową strukturę folderów projektu (drzewo `docs/`, `app/`, `config/`, `tests/`, `scripts/`, `data/`).
- **Dlaczego ważny:** „przed" dla porównania, jak rozrastał się projekt; materiał do chronologii.
- **Etap projektu:** Etap 0
- **CO OTWORZYĆ:** eksplorator plików lub edytor (np. VS Code) z rozwiniętym drzewem folderu `C:\Users\user\Desktop\agent project`.
- **CO MA BYĆ WIDOCZNE:** nazwy folderów i plików najwyższego poziomu + rozwinięte `docs/`.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** otwartego pliku `.env` ani jego treści; żadnego klucza API w terminalu/panelu; ścieżek z wrażliwymi danymi.
- **Status:** SCREENSHOT REQUIRED

### [—] 02_nia-profile
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_nia-profile.png
- **Co pokazuje:** założony profil publikacji „Nothing Is Accidental" (widok główny profilu/strony publikacji).
- **Dlaczego ważny:** baseline konta przed startem agenta.
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** publiczną stronę profilu „Nothing Is Accidental" — najlepiej w oknie **wylogowanym** (tryb incognito), żeby nie było widać panelu właściciela.
- **CO MA BYĆ WIDOCZNE:** nazwa publikacji, ogólny wygląd strony.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** paska zalogowanego konta, adresu e-mail, ustawień, dashboardu, danych subskrybentów.
- **Status:** SCREENSHOT REQUIRED

### [—] 03_bio-and-handle
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_bio-and-handle.png
- **Co pokazuje:** bio publikacji („Explaining the hidden systems, incentives and decisions behind ordinary things.") oraz handle/URL (np. `nothingisaccidental.substack.com`).
- **Dlaczego ważny:** dokumentuje pozycjonowanie na starcie (bio + adres).
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** publiczny profil (wylogowany) z widocznym bio i adresem w pasku przeglądarki.
- **CO MA BYĆ WIDOCZNE:** tekst bio + handle/URL publikacji.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** prywatnego e-maila, ustawień konta, danych logowania.
- **Status:** SCREENSHOT REQUIRED

### [—] 04_profile-avatar
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_profile-avatar.png
- **Co pokazuje:** grafikę profilową / logo publikacji (avatar, ewentualnie grafikę nagłówkową).
- **Dlaczego ważny:** identyfikacja wizualna na starcie — porównanie, jak zmienia się branding.
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** profil publiczny; kadr na avatar/logo (i banner, jeśli jest).
- **CO MA BYĆ WIDOCZNE:** sama grafika profilowa i nazwa.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** danych osobowych, e-maila, panelu ustawień.
- **Status:** SCREENSHOT REQUIRED

### [—] 05_first-architecture
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-architecture.png
- **Co pokazuje:** pierwszą architekturę systemu (diagram/sekcja z `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §B.1` lub `docs/archive/superseded_plans/ARCHITECTURE.md §5`).
- **Dlaczego ważny:** „architektura na papierze" na starcie — do porównania z tym, co realnie zbudowano (`ARCHITECTURE_EVOLUTION.md`).
- **Etap projektu:** V0
- **CO OTWORZYĆ:** `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` (sekcja architektury) w edytorze/podglądzie Markdown.
- **CO MA BYĆ WIDOCZNE:** diagram warstw / mermaid architektury.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** żadnego otwartego `.env`, kluczy, terminala z sekretami.
- **Status:** SCREENSHOT REQUIRED

### [—] 06_first-implementation-plan
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-implementation-plan.png
- **Co pokazuje:** pierwszy plan implementacji (nagłówek + spis sekcji `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md`).
- **Dlaczego ważny:** punkt odniesienia „plan vs rzeczywistość".
- **Etap projektu:** V0
- **CO OTWORZYĆ:** `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` — góra dokumentu / spis części A–C.
- **CO MA BYĆ WIDOCZNE:** tytuł, data, struktura planu.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** sekretów, kluczy, prywatnych danych.
- **Status:** SCREENSHOT REQUIRED

## Wpisy — planowane w kolejnych etapach

### [—] first-working-version
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-working-version.png
- **Co pokazuje:** pierwsze uruchomienie walking skeleton (log/CLI z ocenionymi tematami + kosztem).
- **Dlaczego ważny:** pierwszy dowód, że rdzeń działa.
- **Etap projektu:** Etap 1
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** klucza API w terminalu (maskować `ANTHROPIC_API_KEY`).
- **Status:** SCREENSHOT REQUIRED (powstanie po uruchomieniu walking skeleton)

### [2026-07-12] private-github-repository
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_private-github-repository.png
- **Co pokazuje:** stronę główną repozytorium `nothing-is-accidental-agent` z widocznym oznaczeniem **Private** oraz listę branchy `main` i `dev/a2-stabilization`.
- **Dlaczego ważny:** dowód, że pierwszy zewnętrzny backup projektu powstał jako prywatny i że praca rozwojowa została oddzielona od stabilnego `main`.
- **Etap projektu:** Etap 1N — Git/GitHub.
- **CO OTWORZYĆ:** prywatne repozytorium GitHub; osobno dropdown/listę branchy, jeśli obie nazwy nie mieszczą się na jednym ekranie.
- **CO MA BYĆ WIDOCZNE:** nazwa repozytorium, badge `Private`, branche `main` i `dev/a2-stabilization`.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** tokenów GitHub, adresu e-mail, ustawień konta, `.env`, terminala z danymi uwierzytelnienia ani prywatnych informacji profilu.
- **Status:** SCREENSHOT REQUIRED (nie używano przeglądarki/Playwrighta w tym zadaniu)

### [2026-07-12] first-research-card-offline-preflight
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-research-card-offline-preflight.png
- **Co pokazuje:** terminal z wynikiem `--estimate-only`, tabelą kosztów A1/A2/B, łącznym kosztem oczekiwanym 0,201280 USD, konserwatywnym 0,510375 USD i limitem 0,55 USD.
- **Dlaczego ważny:** dokumentuje moment, w którym pełny realny run był gotowy do świadomej akceptacji, ale nie został jeszcze uruchomiony.
- **Etap projektu:** Etap 1O — offline preflight pierwszej kompletnej Research Card.
- **CO OTWORZYĆ:** terminal i ponownie wykonać wyłącznie bezpłatną komendę z `--estimate-only`.
- **CO MA BYĆ WIDOCZNE:** tryb `three-stage`, limity źródeł/wyszukiwań/retry, rozbicie A1/A2/B i komunikat o zerowym koszcie estimate-only.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** wartości klucza API, `.env`, danych uwierzytelnienia, surowych odpowiedzi diagnostycznych ani prywatnych danych.
- **Status:** SCREENSHOT REQUIRED (zgodnie z zakazem nie używano Playwrighta ani przeglądarki)

### [2026-07-12] task3-attempts-recovery-audit
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_task3-attempts-recovery-audit.png
- **Co pokazuje:** bezpieczny, zanonimizowany dowód historycznego runu PARTIAL: failed candidates z lower-bound `attempts`, wynik jawnego `retry-failed-candidates`, ewentualne `PARTIAL_EXHAUSTED → PARTIAL` po wyższym capie oraz niezmienione `model_usage`/koszt.
- **Dlaczego ważny:** pokazuje granicę między bezpłatną decyzją recovery a osobnym, potencjalnie płatnym resume.
- **Etap projektu:** Etap 0 / Task 3 po korekcie review.
- **CO OTWORZYĆ:** wyłącznie bezpieczną, lokalną kopię/dry fixture albo późniejszy widok administracyjny; nie uruchamiać API ani retry na bazie źródłowej tylko dla zrzutu.
- **CO MA BYĆ WIDOCZNE:** statusy kandydatów, cap, liczba resetów, status runu oraz brak nowego usage/kosztu.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** URL-i prywatnych, kluczy, `.env`, danych konta, treści źródeł ani terminala z sekretami.
- **Status:** SCREENSHOT REQUIRED (nie ma jeszcze bezpiecznego materiału wizualnego; Playwrighta nie używano).

### [2026-07-12] task4-topic-used-research-guard
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task4-topic-used-research-guard.png`
- **Co pokazuje:** lokalny fixture po COMPLETE: `topics.status=USED`, następnie odmowę świeżego researchu bez flagi oraz jawny komunikat `--force-re-research`; bez kluczy i bez surowych źródeł.
- **Dlaczego ważny:** odróżnia bezpłatne wznowienie istniejącej pracy od nowej, świadomie ryzykownej próby płatnej.
- **Status:** SCREENSHOT REQUIRED — w zadaniu nie uruchamiano przeglądarki ani API.

### [2026-07-12] task4-finalization-integrity-after-review
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task4-finalization-integrity-after-review.png`
- **Co pokazuje:** lokalny fixture po reopen: poprawną relację run–topic–card, a następnie rollback wymuszony triggerem, bez częściowego SUCCESS/COMPLETE/USED.
- **Dlaczego ważny:** dokumentuje różnicę między atomowością dwóch statusów a atomowością całej finalizacji.
- **Status:** SCREENSHOT REQUIRED — wykonano wyłącznie testy SQLite, bez przeglądarki i API.

### [2026-07-12] task5-retry-budget-matrix
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task5-retry-budget-matrix.png`
- **Co pokazuje:** terminal z celowanymi testami callbacku/PolicyEngine i pełnym wynikiem `257 passed`, w tym A1/A2/B deny attempt 2, bez sekretów i danych API.
- **Dlaczego ważny:** dowodzi, że retry jest blokowane przed drugim callem, a CLI korzysta z centralnej polityki.
- **Status:** SCREENSHOT REQUIRED — w tej pracy nie uruchamiano Playwrighta ani przeglądarki.

### [2026-07-12] task6-topics-parser-ledger
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task6-topics-parser-ledger.png`
- **Co pokazuje:** terminal z testami parsera/klienta/workflow topics (`35 passed`) oraz pełnym wynikiem `286 passed`; bez kluczy, `.env` i odpowiedzi realnego providera.
- **Dlaczego ważny:** dowodzi, że malformed JSON zachowuje dostępne usage, kończy run `FAILED` i nie zapisuje częściowych tematów.
- **Status:** SCREENSHOT REQUIRED — nie używano Playwrighta ani przeglądarki; bezpieczny screenshot może powstać później z testów offline.

### [2026-07-12] task8-lifecycle-transition-race
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task8-lifecycle-transition-race.png`
- **Co pokazuje:** bezpieczny terminal z wynikiem 44 testów Task 8, race terminalnych UPDATE/resume i pełnym `330 passed`; bez danych źródłowej bazy.
- **Dlaczego ważny:** pokazuje, że stan źródłowy jest warunkiem tego samego UPDATE, tylko jeden konkurent wygrywa, a odrzucona mutacja nie zostawia częściowego zapisu po reopen.
- **Status:** SCREENSHOT REQUIRED — zgodnie z zakazem nie używano Playwrighta ani przeglądarki; screenshot może powstać później wyłącznie z testów offline.

### [2026-07-13] task9-real-run-a1-a2-success-b-max-tokens
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task9-real-run-a1-a2-success-b-max-tokens.png`
- **Co pokazuje:** zanonimizowany terminal lub bezpieczny raport DB: run_id, A1 SUCCESS, 4×A2 SUCCESS/VERIFIED, B FAILED z `stop_reason=max_tokens`, koszt 0,170050 USD i cap 0,55 USD. Bez surowej odpowiedzi, klucza API i zawartości `.env`.
- **Dlaczego ważny:** dowodzi jednocześnie trwałości opłaconych etapów, poprawnego księgowania kosztu oraz uczciwego nieogłoszenia Etapu 0 jako ukończonego.
- **Status:** SCREENSHOT REQUIRED — w Task 9 nie używano Playwrighta ani przeglądarki; screenshot ma zostać wykonany ręcznie po review z bezpiecznego widoku, nie z prywatnego raw response.

### SS-TASK9-FIX — offline regresja truncation i lifecycle
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task9-offline-truncation-lifecycle-tests.png`
- **Co pokazuje:** zanonimizowany wynik `174 passed` testów celowanych (włącznie z cost ledger, prior usage liczone raz i zachowaniem JSONL A1) oraz `351 passed` pełnego suite, bez danych raw/API.
- **Status:** SCREENSHOT REQUIRED — w zadaniu nie uruchamiano Playwrighta ani nie tworzono automatycznie obrazu; obecny dowód to log testów i diff kodu.

### [2026-07-13] task9-controlled-status-repair
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task9-controlled-status-repair.png`
- **Co pokazuje:** zanonimizowany raport maintenance: spełnione preconditions, `rowcount=1`, zmianę tylko `status`/`finished_at`/`error`, niezmienione `SOURCES_COMPLETE`, 4× VERIFIED, 6 usage i koszt 0,170050 USD.
- **Dlaczego ważny:** dokumentuje, że historyczny audit został naprawiony kontrolowanie, bez zmiany danych researchu, kosztu ani uruchomienia resume.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** surowej odpowiedzi providera, treści `.env`, kluczy, URL-i źródeł ani danych uwierzytelnienia.
- **Status:** SCREENSHOT REQUIRED — zgodnie z zakazem nie używano Playwrighta; dowodem bieżącym są snapshoty logiczne, SHA-256 i log operacji.

### [2026-07-13] task9-first-real-card-resume-b
- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_task9-first-real-card-resume-b.png`
- **Co pokazuje:** bezpieczny raport po reopen: run SUCCESS, research COMPLETE, topic USED, card #2, 4 VERIFIED, `stop_reason=end_turn`, jeden nowy usage B 0,013914 USD i łączny koszt 0,183964/0,20 USD; obok jakościowe REJECT bez treści raw response.
- **Dlaczego ważny:** dokumentuje pierwsze spełnienie kryterium Etapu 0 oraz rozdzielenie sukcesu technicznego od odmowy redakcyjnej.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** klucza API, `.env`, prywatnej diagnostyki raw, danych uwierzytelnienia ani panelu zewnętrznego konta.
- **Status:** SCREENSHOT REQUIRED — Playwrighta nie używano; screenshot może powstać później wyłącznie z zanonimizowanego lokalnego raportu.

### 2026-07-13 — F4: dowód atomowej finalizacji staged B

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_f4-staged-finalization-rollback.png`
- **Co ma pokazywać:** zanonimizowany wynik lokalnego testu/reopen: fault injection po drugim źródle lub lifecycle, brak `research_cards`, `sources` i B SUCCESS, a `research_runs` nadal `SYNTHESIS_PENDING`; osobny fragment dla jednego zwycięzcy dwóch SQLite connections.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, klucza API, raw response, danych realnej bazy albo konta zewnętrznego.
- **Status:** SCREENSHOT REQUIRED — tego zadania nie wolno było łączyć z Playwrightem ani API; materiał może powstać wyłącznie z lokalnej, syntetycznej bazy testowej.

### 2026-07-13 — F4: trwały force i pełna macierz rollbacku

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_f4-typed-context-reopen-matrix.png`
- **Co ma pokazywać:** zanonimizowany raport z syntetycznej plikowej SQLite: force marker po reopen, odmowę preflight przed klientem oraz tabelę 13 fault points z brakiem karty/źródeł/B SUCCESS/COMPLETE/USED i niezmienionym usage.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, klucza API, raw response, danych historycznej bazy ani zewnętrznego konta.
- **Status:** SCREENSHOT REQUIRED — testy wykonały wyłącznie lokalne dane; Playwright i API są poza zakresem.

### 2026-07-13 — F4: terminalny no-op waliduje execution mode

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_f4-terminal-mode-noop.png`
- **Co ma pokazywać:** zanonimizowany wynik lokalnych testów: FRESH→FRESH i FORCE→FORCE jako no-op oraz fresh/force/resume conflicts po reopen bez zmiany timestampów, kosztu, runu, research_runu ani topicu.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, kluczy API, raw response, historycznej bazy i zewnętrznego konta.
- **Status:** SCREENSHOT REQUIRED — brak Playwrighta i API; materiał może powstać tylko z syntetycznej SQLite testowej.
### 2026-07-13 — Etap 1: old-owner research fencing P1

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_stage1-old-owner-fencing-matrix.png`
- **Co ma pokazywać:** zanonimizowany raport z syntetycznej plikowej SQLite: job po expiry/recovery w `NEEDS_VERIFICATION`, każda próba starego ownera odrzucona, przed/po identyczny snapshot run/research_run/usage/card/koszt/timestamps oraz `integrity_check=ok`; obok wynik race dwóch połączeń.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, kluczy, danych prawdziwej bazy, treści provider response, danych zewnętrznego konta ani identyfikatorów realnych runów.
- **Status:** SCREENSHOT REQUIRED — zadanie nie używało browsera ani Playwrighta; dowodem bieżącym są deterministyczne testy na syntetycznej SQLite, reopen i SHA-256 prawdziwej bazy.

### 2026-07-13 — Etap 1: post-lock lease i pochodny koszt

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_stage1-post-lock-lease-csv.png`
- **Co ma pokazywać:** zanonimizowany raport z syntetycznej plikowej SQLite: mutacja rozpoczęta przed expiry blokuje się na `BEGIN IMMEDIATE`, po przesunięciu zegara jest odrzucona bez zmiany snapshotu; obok job/run/research_run kończące się poprawnie mimo kontrolowanej awarii appendu `COSTS.csv`.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, kluczy, danych prawdziwej bazy, raw response, ścieżek prywatnych ani danych zewnętrznego konta.
- **Status:** SCREENSHOT REQUIRED — brak Playwrighta i API; dowodem są testy na syntetycznej SQLite, reopen, `PRAGMA integrity_check` i niezmieniony hash prawdziwej bazy.

### 2026-07-14 — Etap 1: atomowy sukces RESEARCH obejmuje job

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_stage1-workflow-terminalization.png`
- **Co ma pokazywać:** zanonimizowany raport z syntetycznej plikowej SQLite po reopen: jedna karta i komplet źródeł, `research_run=COMPLETE`, terminalny run, topic `USED`, `job=DONE`, brak ownera/lease/error; obok failpoint przed i po `UPDATE jobs SET status='DONE'`, w obu przypadkach brak częściowego sukcesu.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, kluczy, danych prawdziwej bazy, raw response, prywatnych ścieżek ani danych konta zewnętrznego.
- **Status:** SCREENSHOT REQUIRED — dowodem bieżącym są deterministyczne testy file-SQLite, reopen i `PRAGMA integrity_check`; browser, Playwright i API nie były używane.

### 2026-07-14 — Etap 1: zamknięty kontrakt DispatchResult

- **Plik:** `docs/screenshots/YYYY-MM-DD_HHMM_stage1-dispatch-contract.png`
- **Co ma pokazywać:** zanonimizowany raport z syntetycznej file-SQLite: atomic failure z `generic fail_job=0`; odrzucony string terminalizacji bez heartbeat/complete/fail/LOST; osobny atomic success pozostający `job=DONE`, `research_run=COMPLETE`, topic `USED` i z kartą po reopen.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** `.env`, kluczy, danych prawdziwej bazy, raw response, prywatnych ścieżek ani danych konta zewnętrznego.
- **Status:** SCREENSHOT REQUIRED — zadanie wykonało tylko testy offline i nie używało browsera, Playwrighta ani API.
