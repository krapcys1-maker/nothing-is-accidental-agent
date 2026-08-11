# SCREENSHOT_INDEX

## 2026-08-11 — Reviewer global ledger repair

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, bo zakres wyklucza browser, a właściwym dowodem są triggery i testy temp DB.
- **Co powinien pokazać:** `role reservation → external effect → terminal role execution + model_usage (atomowo) → runs.cost_usd`, z daily/monthly gate przed callerem.
- **Dowód tekstowy:** reviewer/lifecycle `31/31`, migration/content/provider `130/130`, explicit ladder `1/1`, affected po pełnej aktualizacji migracji `354/354`, full/collect `2588/2588` w `695.1 s`; koszt `0.000000 USD`; produkcja bez migracji.

## 2026-08-11 — P2-1 TOPIC_GENERATION / ARTICLE_RESEARCH provider alignment

- **Status:** `SCREENSHOT REQUIRED`; browser i obrazy produkcyjnych danych były zabronione. Niezależny werdykt dla reviewed head: `APPROVE WITH MINOR/P2`, zero blockerów runtime.
- **Co ma pokazywać:** dwa rooty `TOPIC_GENERATION job` i `ARTICLE_RESEARCH job` zbiegające do `frozen role binding → canonical Anthropic contract → one fake SDK call`; pola `ANTHROPIC/global/standard_only/FORBIDDEN/0/0`; obok fail-before-SDK dla contract drift i returned-model mismatch bez fallbacku.
- **Dowód tekstowy:** new `11/11`, affected `223/223`, E3 `PROCEED + 3 lineage + prepare_content_job`. Historyczne `2578 passed / 15 fixture failures` oraz `2593/2593` pochodzą z przedcommitowego working tree i nie są checkpointem commita PR. Autorytatywny niezależny checkpoint reviewed head `5b9969edd1177154e7474a3374edf16c41693140`: `2587 collected / 2587 passed / 0 failed / 0 skipped`.
- **Warunki bezpieczeństwa:** bez `.env`, API key, surowej DB, pełnych promptów/evidence, realnego SDK/API i publikacji. Dwa dodatkowe testy authority oraz pozostałe P2 są nieblokującym backlogiem, nie warunkiem merge; `APPROVE WITH MINOR/P2` nie zamyka Etapu 3 ani nie daje live readiness.

## 2026-08-11 — PRE-LIVE CONTENT UNBLOCK B1–B5

- **Status:** `SCREENSHOT REQUIRED`; zadanie zabraniało browsera, realnego flow i eksponowania produkcyjnych danych, więc nie wykonano obrazu.
- **Co ma pokazywać:** zanonimizowany flow `controlled root → reviewer unavailable → BLOCK przed writerem/kosztem`; obok kandydacki ProductionArticleWriter, ordinary worker `BLOCK`, sześć wyników novelty oraz ordering `duplicate → runner/writer calls=0`.
- **Dowód tekstowy:** nowe 6/6, affected 473/473, full/collect 2546/2546; root bez semantic reviewera: SDK/transport/usage/attempt `0`, approval nieskonsumowany; novelty i bounded final topic prompt przechodzą. B3 pozostaje jawnie zablokowane.
- **Warunki bezpieczeństwa:** bez `.env`, sekretów, surowej produkcyjnej DB, prywatnego korpusu, pełnych promptów i sugestii, że B3 albo live flow są gotowe.

## 2026-08-10 — OPUS ARTICLE_WRITER SWITCH

- **Status:** `SCREENSHOT REQUIRED`; browser i obrazy produkcji były zabronione.
- **Co ma pokazywać:** historyczny Fable `FAIL/PROVIDER_REFUSAL` po lewej; policy switch `ARTICLE_WRITER→OPUS` pośrodku; po prawej fail-closed `UNVERIFIED / no activation / no new binding` oraz osobne przyszłe bramki migration→qualification→activation.
- **Dowód tekstowy:** test migracji 0030→0031 zachowujący Fable run/result i frozen binding, test fake Opus composition root, mismatch/cost gates, produkcyjne PRE=POST SHA/integrity/FK/sidecars.
- **Warunki bezpieczeństwa:** bez sekretów, raw DB, `.env`, prywatnego korpusu stylu i sugestii, że Opus jest qualified/ACTIVE/live-ready.

## 2026-08-10 — Pierwsza realna kwalifikacja Fable

- **Status:** `SCREENSHOT REQUIRED`; podczas realnego calla nie uruchamiano browsera ani przechwytywania ekranu, aby nie ryzykować ujawnienia sekretu lub danych produkcyjnych.
- **Co ma pokazywać:** zanonimizowany przepływ exact approval + retention → atomic consume/IN_FLIGHT → jeden provider call → `FAIL / PROVIDER_REFUSAL` → terminal settlement; obok usage `151/3`, koszt `0.001660 USD`, capability `0`, activation `0`, policy `UNVERIFIED`.
- **Dowód tekstowy:** trwały run i qualification result, POST integrity `ok`, FK `0`, brak sidecarów, zero retry/fallbacku/drugiego requestu.
- **Warunki bezpieczeństwa:** bez `.env`, API key, pełnej odpowiedzi providera, surowej bazy, owner identity i prywatnego korpusu stylu.

## 2026-08-10 — Fable qualification authority package

- **Status:** `SCREENSHOT REQUIRED`; browser i obrazy produkcji były zabronione, więc nie utworzono screenshotu.
- **Co ma pokazywać:** zanonimizowany authority graph catalogue → registry/pricing/evidence → approval + exact retention acceptance → atomic consume/IN_FLIGHT → caller once → terminal run → capability/result → activation; obok negative gates z caller `0` i production PRE=POST.
- **Dowód tekstowy:** `docs/FABLE_QUALIFICATION_AUTHORITY_PACKAGE_2026-08-10.md`, temp rehearsal PASS, istniejące testy trzech modułów PASS, production SHA/schema/counts bez zmian, koszt `0.000000 USD`.
- **Warunki bezpieczeństwa:** bez `.env`, danych produkcyjnych, prawdziwego policy ref, owner identity, sekretów, realnego acceptance/API/qualification i sugestii C5.

## 2026-08-10 — Produkcyjna migracja 0020→0030

- **Status:** `SCREENSHOT REQUIRED`; nie wykonano obrazu zawierającego prywatne ścieżki lub dane produkcyjne.
- **Co ma pokazywać:** zanonimizowany PRE `0020/20` → dziesięć jawnie potwierdzonych kroków → POST `0030/30`, integrity `ok`, FK `0`, preserve-state `211 rows / 2390 cells / 0 mismatches`, retention acceptance `0`.
- **Dowód tekstowy:** backup byte-identical, wszystkie kroki exit `0`, produkcja po reopen spójna, styl niezmieniony, koszt zero.
- **Warunki bezpieczeństwa:** bez `.env`, danych biznesowych, pełnych ścieżek, raw DB, hashów prywatnych artefaktów i sugestii C5/live readiness.

## 2026-08-10 — MIGRATION TRANSACTIONALITY REPAIR 0026/0027

- **Status:** `SCREENSHOT REQUIRED`; browser był zabroniony i nie powstał nowy obraz.
- **Co ma pokazywać:** bezpieczny diagram dwóch sekwencji: `0025 → SQL 0026 → failpoint → rollback do 0025 → reopen → retry → 0026` oraz analogicznie `0026 → 0027`; obok wynik świeżego rehearsal `0030/30`, integrity `ok`, FK `0`, preserve-state mismatch `0`, retention acceptance `0`.
- **Dowód tekstowy:** nowe `4/4`, affected `74/74`, produkcja i styl niezmienione, koszt `0.000000 USD`.
- **Warunki bezpieczeństwa:** bez `.env`, sekretów, surowych danych produkcyjnych, prywatnego stylu, pełnych ścieżek i sugestii niezależnego approvalu.

## 2026-07-16 — W1A-R4-01 / czwarty niezależny reject

- **Status:** `SCREENSHOT REQUIRED` — w tej fali nie uruchamiano browsera ani interfejsu zewnętrznego.
- **Co ma pokazywać:** terminal offline z trzema dowodami bez sekretów: pełny suite 1036/1036, partycje exact-once 248+253+267+268 oraz niezależną kontrpróbę `Worker.run_once`, w której `REQUEST_STARTED` po lokalnym błędzie staje się widocznym `NEEDS_RECONCILIATION` bez attemptu #2 i bez provider calla.
- **Warunki bezpieczeństwa:** wyłącznie temp DB/fake; bez `.env`, kluczy, zawartości `data/` i danych konta; status `WAVE 1A — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW` musi być widoczny bez sugestii zamknięcia WAVE lub odblokowania Etapu 1.

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

## 2026-07-14 — WAVE 0B.1 durable-boundary verification

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** terminal z wynikiem offline `741 passed`, `PRAGMA integrity_check=ok`, pustym `foreign_key_check` oraz niezmienionym SHA-256 `data/agent.db`.
- **Dlaczego nie utworzono teraz:** zadanie zakazywało browsera i zmian w danych, a dowodem wdrożeniowym są powtarzalne testy oraz log terminala; nie wykonano zrzutu mogącego przypadkowo ujawnić dane lokalne.

## 2026-07-14 — WAVE 0B.2 provider-ledger hardening

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal: `752 passed`, `integrity_check=ok`, pusty `foreign_key_check`, hash baselineu oraz testy migration rollback/context gate bez requestu sieciowego.
- **Czego nie może pokazać:** `.env`, kluczy, danych historycznej bazy, raw provider response ani prywatnych ścieżek.
- **Dlaczego nie utworzono teraz:** zadanie było offline-only i nie używało browsera ani Playwrighta; dowodem są testy i logi terminala.

## 2026-07-14 — WAVE 0B.3 derived identity / fresh lease verification

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal: `770 passed`, arbitrary identity `caller=0`, exact expiry/renewal/takeover results, `messages.create=0` po takeover, `integrity_check=ok`, pusty `foreign_key_check` i baseline SHA.
- **Czego nie może pokazać:** `.env`, kluczy, danych historycznej bazy, raw provider response ani prywatnych ścieżek.
- **Dlaczego nie utworzono teraz:** zadanie zakazywało browsera i działań zewnętrznych; dowodem są deterministyczne testy offline.

## 2026-07-15 — WAVE 0B corrective closeout: procesy testowe, snapshot requestu i lifecycle

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal historycznej weryfikacji przed W0B-REV-06: collect/full `861 passed`, wynik subprocessów raw SQLite/dbapi2/URI, socket/DNS/SDK i scrub lowercase environment; dalej macierz question/niche/stage i parametrów intentu oraz run/research_run z `caller=0`, usage/koszt/settlement 0, `NEEDS_RECONCILIATION`, reopen SQLite, odmowę A2/B `--real --resume`, `integrity_check=ok`, pusty `foreign_key_check` i hash baselineu.
- **Czego nie może pokazać:** `.env`, kluczy, wartości proxy, danych historycznej bazy, raw provider response, prywatnych ścieżek ani danych zewnętrznego konta.
- **Dlaczego nie utworzono teraz:** zakres zakazuje browsera i sieci; aktualnym dowodem są deterministyczne testy na syntetycznych bazach oraz read-only kontrole baselineu.

## 2026-07-15 — W0B-REV-06: trwały limit i fail-closed settlement

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal z **historycznym** collect/full `873`, czterema rozłącznymi grupami 206+218+226+223 oraz wynikiem `PARTITION COVERAGE OK`; dalej syntetyczną SQLite z `max_tokens` 2999/3000/3001 po reopen, exact estimate/reservation/caller, settlement `<=` jako `SETTLED` i settlement `>` jako `NEEDS_RECONCILIATION` z jednym usage oraz brakiem attempt #2.
- **Czego nie może pokazać:** `.env`, kluczy API, raw provider response, danych `data/agent.db`, prywatnych ścieżek, wartości proxy ani danych konta zewnętrznego.
- **Dlaczego nie utworzono teraz:** zakres zabraniał browsera, sieci i API; dowodem są wyłącznie fake callery, tymczasowe bazy, testy deterministyczne oraz read-only kontrola baselineu.

## 2026-07-15 — W0B-REV-09/10: końcowa weryfikacja kroniki i ROUND_HALF_UP

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal z historycznym collect/full **887**, partycjami **211+222+229+225**, `PARTITION COVERAGE OK`; obok syntetyczny raport granic `0.0000004/.5/.6`, cache read/write/web i settlement exact/±0.000001. Opis musi wymienić `Decimal(str(value)) → 0.000001/ROUND_HALF_UP`, `durable_research_intent_v2`, 13 migracji, WAVE 0B `CANDIDATE`, Etap 1 `BLOCKED` i live API `ZABRONIONE`.
- **Czego nie może pokazać:** `.env`, kluczy, danych `data/agent.db`, raw provider response, prywatnych ścieżek ani danych konta zewnętrznego.
- **Dlaczego nie utworzono teraz:** zakres był offline-only; dowodem są fake callery, tymczasowe SQLite i read-only hash/integrity baselineu.

## 2026-07-16 — skonsolidowany pakiet końcowy Etapu 1

- **Status:** `SCREENSHOT REQUIRED` po niezależnym review; w bieżącym zadaniu nie tworzono screenshotu.
- **Co powinien pokazać:** zanonimizowany terminal z nowym collect/full suite, weryfikacją czterech partycji, `compileall`, `git diff --check`, planem obu zadań systemowych zakończonym `SYSTEM TASK NOT REGISTERED`, read-only raportem z `UNKNOWN/BLOCKED`, copy-preflightem 0009→0014 na kopii oraz niezmienionym SHA/size/mtime chronionej bazy.
- **Czego nie może pokazać:** `.env`, kluczy/proxy, zawartości historycznej bazy, raw provider response, prywatnych danych konta ani plików instrukcji pisania.
- **Dlaczego nie utworzono:** zakres zakazywał browsera i działań zewnętrznych, a dowodem są logi/testy offline. Screenshot nie może sugerować rejestracji Task Scheduler, migracji produkcji ani wykonania live API.

## 2026-07-15 — Formalny checkpoint WAVE 0B

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal z branch/HEAD/upstream, inwentarzem 50/1/21 = 72, stagingiem zatwierdzonych plików, `894 collected/passed`, partycjami 213/224/231/226, `compileall`, `git diff --cached --check` oraz niezmienionym SHA/rozmiarem/mtime chronionej bazy. Opis wymienia `APPROVED WITH P2 — READY FOR CHECKPOINT`, 13 migracji, `ROUND_HALF_UP`, `durable_research_intent_v2`, jeden aktywny durable paid-execution flow, Etap 1 `BLOCKED` i live API `ZABRONIONE`.
- **Czego nie może pokazać:** `.env`, kluczy, danych `data/agent.db`, raw provider response, prywatnych ścieżek ani danych konta zewnętrznego.
- **Dlaczego nie utworzono teraz:** bieżące polecenie wymaga formalnego stagingu i walidacji, nie tworzenia artefaktu graficznego; dowody pozostają tekstowe i read-only.

## 2026-07-15 — W0B-RR-01: Decimal do końca i cleanup resume

- **Status:** `SCREENSHOT REQUIRED`.
- **Co powinien pokazać:** zanonimizowany terminal z collect/full **894**, partycjami **213+224+231+226**, `PARTITION COVERAGE OK`, `compileall` i `git diff --check`; raport granic `2×`/`3×0.0000005`, `0.1+0.2` wobec `0.3` w policy/ledgerze/CLI, settlement ±1 mikro-USD oraz statyczną asercję braku konstruktora klienta w helperach resume. Opis wymienia 13 migracji, `durable_research_intent_v2`, jeden `max_tokens` dla estimate/rezerwacji/callera, `NEEDS_RECONCILIATION` po nadwyżce, WAVE 0B `CANDIDATE`, Etap 1 `BLOCKED` i live API `ZABRONIONE`.
- **Czego nie może pokazać:** `.env`, kluczy, danych `data/agent.db`, raw provider response, prywatnych ścieżek ani danych konta zewnętrznego.
- **Dlaczego nie utworzono teraz:** zakres był offline-only; dowodem są fake callery, tymczasowe SQLite i read-only hash/integrity baselineu.

## 2026-07-17 — LA-01-R1 po `REJECTED — MAJOR`

- **Status:** `SCREENSHOT REQUIRED` dopiero po niezależnym review; w tej fali nie tworzono obrazu.
- **Co powinien pokazać:** zanonimizowany terminal z `1151 passed`, `PARTITION COVERAGE OK: 1151`, partycjami `275+282+291+303`, `compileall` i `git diff --check`; obok syntetyczny raport fake controlled session z `COMPLETED_FAIL_CLOSED`, jednym attemptem/usage/settlementem, usuniętym markerem i redacted prompt/sekretem.
- **Czego nie może pokazać:** `.env`, API keys, Authorization, promptu, provider payloadu, zawartości `data/agent.db`, chronionych instrukcji pisania ani prywatnych ścieżek.
- **Dlaczego nie utworzono:** wymagany zakres zakazywał browsera i używał wyłącznie fake workera oraz baz tymczasowych. Dowodem są deterministyczne testy i fingerprinty; realny live acceptance nie został wykonany.

## 2026-07-17 — Checkpoint LA-01-R1 po `APPROVE WITH MINOR/P2`

- **Status:** `SCREENSHOT REQUIRED` po pushu; w bieżącym checkpointcie nie tworzono obrazu.
- **Co powinien pokazać:** zanonimizowany `git show --name-status --format=fuller`, upstream `0/0`, staging pusty, prywatny blok BUILD_LOG i katalog instrukcji pozostające lokalnie oraz niezmienione fingerprinty DB/WAL/SHM.
- **Czego nie może pokazać:** remote URL z credentialami, `.env`, kluczy, zawartości produkcyjnej bazy, promptów, chronionych instrukcji ani prywatnego bloku użytkownika.

## 2026-07-17 — Real pricing profile i finalny preflight

- **Status:** `SCREENSHOT REQUIRED` po osobno autoryzowanym enqueue i ponownym zamrożeniu SHA; teraz obrazu nie utworzono.
- **Co powinien pokazać:** zanonimizowany resolver `approved`, typy `Decimal`, pricing fingerprint, projected/pessimistic/cap, topic `3`, dokładnie jeden post-enqueue claimable job, nowy DB SHA, fail-closed flags i `REAL_CONTROLLED_LIVE_ENABLED=false` przed decyzją właściciela.
- **Czego nie może pokazać:** `.env`, klucza API, promptu/question, worker execution tokenu, provider payloadu, danych prywatnych, zawartości produkcyjnej bazy ani chronionych instrukcji.
- **Dlaczego nie utworzono:** bieżący zakres zakazuje enqueue, gate i provider requestu; screenshot przed post-enqueue fingerprintem mógłby fałszywie sugerować finalną gotowość.

## 2026-07-17 — Jedyna autoryzowana komenda live: `PREFLIGHT_FAILED`

- **Status:** `SCREENSHOT REQUIRED` dla niezależnego review; nie utworzono go w trakcie próby.
- **Co powinien pokazać:** zanonimizowany wynik zewnętrznego preflight PASS, dokładny gate diff 1/1, pojedynczy `CONTROLLED-LIVE-ONCE: PREFLIGHT_FAILED`, trwały raport z `provider_request_started=false` i `marker_cleared=true`, końcowe flags fail-closed oraz gate `False` bez diffu.
- **Czego nie może pokazać:** `.env`, API key, prompt/question, execution token, provider payload ani zawartość produkcyjnej SQLite.

## 2026-07-17 — WAVE LA-02 ancestry i diagnostics

- **Status:** `SCREENSHOT REQUIRED` dla niezależnego review; obrazu nie tworzono w lokalnej fali.
- **Co powinien pokazać:** zanonimizowany wynik `1174 passed`, exact-once partycji, standalone `PASS` na temp DB i `STOP` z realnym testowym workerem, durable fake report z outer `PREFLIGHT_FAILED`, inner `PROCESSES_PRESENT`, blocking PIDs, ancestry i `[REDACTED]`.
- **Czego nie może pokazać:** `.env`, API key, prompt/question, pełnych command lines z prywatnymi wartościami, execution tokenu, provider payloadu, zawartości produkcyjnej SQLite ani chronionych instrukcji.
- **Dlaczego nie utworzono:** dowodem są deterministyczne testy/subprocessy i fingerprinty; screenshot nie jest potrzebny do implementacji, a mógłby ujawnić lokalne command lines. Browser i publikacja pozostają zabronione.

## 2026-07-17 — Checkpoint LA-02 po `APPROVE WITH MINOR/P2`

- **Status:** `SCREENSHOT REQUIRED`; w checkpointcie nie tworzono obrazu.
- **Co powinien pokazać:** zanonimizowany terminal z `1174 collected`, `1174 passed`, partycjami `284+284+298+308`, exact-once `1174`, `compileall`, `git diff --check`, listą staged files, regułą `git check-ignore -v config/pricing_profiles.yaml`, commitem checkpointu i upstream `0/0`; obok read-only gate z DB SHA `5FF5DB…97B78`, schema 0014, jobem `QUEUED/attempts=0`, attempts/usage 0, gate `False`, markerem absent i flagami fail-closed.
- **Czego nie może pokazać:** treści lokalnego pricing profile, `.env`, kluczy, pełnych command lines, promptu/question, DB contents, runtime reportów, prywatnego `BUILD_LOG` ani chronionych instrukcji pisania.
- **Dlaczego nie utworzono:** dowody są tekstowe i deterministyczne; screenshot command lines mógłby ujawnić dane lokalne. Brak obrazu nie zmienia werdyktu review ani braku autoryzacji live.

## 2026-07-17 — LA-03 i pierwszy realny durable request

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie utworzono podczas operacji.
- **Co powinien pokazać:** zanonimizowany focused 71/71, full 1181/1181, exact-once cover 1181, fake CLI `COMPLETED_FAIL_CLOSED`, standalone PASS oraz trwały live summary: exactly one attempt #1, `REQUEST_STARTED`, `SETTLED`, usage `0.053182 USD`, job/run/research_run `FAILED`, marker absent, flags/gate fail-closed, zero retry/attemptu #2.

## 2026-07-17 — P2 po review LA-03

- **Status:** `SCREENSHOT REQUIRED` — w tym zakresie nie wykonano screenshota, aby nie ryzykować pokazania prywatnej odpowiedzi, promptu, ścieżek debug ani lokalnych sekretów.
- **Co powinien pokazać:** wyłącznie zanonimizowany wynik 1200/1200, exact-once `290+293+304+313`, 14-case parser matrix, test dwóch odrębnych report filenames dla jednego session ID oraz końcowy DB hash `5BEA9E…C6D10` zgodny przed/po.
- **Czego nie pokazywać:** `data/debug/`, raw response, `.env`, pricing profile, pełny prompt/question, token/API headers, chronione instrukcje pisania i command line mogące zawierać sekrety.
- **Dowód tekstowy:** `docs/BUILD_LOG.md`, ADR-086, wynik pytest i końcowy integrity audit. Nie wykonano nowego provider requestu.
- **Czego nie może pokazać:** `.env`, klucza API, promptu/question, provider payloadu/raw response, execution fence, pełnych command lines, treści lokalnego pricing profile ani prywatnych plików użytkownika.
- **Dlaczego nie utworzono:** przeglądarka i publikacja były zabronione; terminal zawierał prywatne ścieżki i potencjalnie wrażliwe command lines. Dowodem są trwały raport, immutable SQLite i testy.

## 2026-07-17 — Naprawa NIA-P2-RV-01…05 po `REJECT — MAJOR`

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie tworzono w fali offline.
- **Co powinien pokazać:** zanonimizowane 1235/1235, partycje `294+299+311+331`, kontrpróby huge score/object+true/bare fence/jawnego clocka oraz potwierdzenie braku pięciu klas sekretów w diagnostic/report/SQLite/logach.
- **Czego nie może pokazać:** surowego payloadu sekretów, `.env`, raw response, pełnych command lines, pricing profile, zawartości produkcyjnej DB ani chronionych plików użytkownika.
- **Dlaczego nie utworzono:** screenshot nie wzmacnia deterministycznego dowodu, a mógłby utrwalić prywatne ścieżki lub wartości użyte w próbach. Browser pozostawał zabroniony.

## 2026-07-17 — Controlled-live zatrzymany na kodowym gate

- **Status:** `SCREENSHOT REQUIRED`; screenshotu nie wykonano, ponieważ browser był jawnie zabroniony.
- **Co powinien pokazać:** zanonimizowane branch/HEAD/upstream `0/0`, staging pusty, quiescence `PASS`, DB `5BEA9E…C6D10`/`335872 B` bez sidecarów, pricing `0.070000/0.105000`, koszt miesiąca `0.737762`, flags fail-closed oraz tracked `REAL_CONTROLLED_LIVE_ENABLED=false`; obok `provider_request_started=false` i brak nowego joba/reportu.
- **Czego nie może pokazać:** `.env`, API key, prompt/question, pełnych command lines, pricing file contents, execution tokenu ani zawartości SQLite.

## 2026-07-17 19:18 UTC — Drugi controlled-live, terminalne truncation

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser był zabroniony.
- **Co powinien pokazać:** zanonimizowane minimal gate diff `1/1`, jeden HTTP 200, `stop_reason=max_tokens`, attempt `SETTLED`, usage `0.060078 USD`, job/run/research_run `FAILED`, brak karty, gate/flags fail-closed i brak sidecarów.
- **Czego nie może pokazać:** `.env`, klucza, promptu, raw/truncated response, execution tokenu, pełnych command lines ani zawartości DB.

## 2026-07-18 — PR1-MAJ-005 runtime schema gate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ dowodem jest wynik CLI/testów, a screenshot terminala mógłby ujawnić lokalne ścieżki. Browser nie był używany.
- **Co powinien pokazać:** zanonimizowane: temp DB `0014`, typowany `SCHEMA_VERSION_TOO_OLD`, identyczny SHA/size/mtime/ledger przed i po, brak WAL/SHM/journal, jawna migracja temp `0014→0015`, runtime PASS na `0015`, 1328/1328 i QA `8/8`.
- **Czego nie może pokazać:** lokalnych ścieżek, `.env`, kluczy, treści produkcyjnej DB, raw response ani identyfikatorów prywatnego środowiska.

## 2026-07-18 — PR #1 recovery po `SETTLED`

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ dowodem są deterministyczne testy, a terminal zawiera prywatne ścieżki robocze.
- **Co powinien pokazać:** zanonimizowane `1311/1311`, partycje `314+319+333+345`, QA recovery `4/4`, pusty finalny diff katalogu podręcznika względem `main` i niezmienny hash produkcyjnej DB.
- **Czego nie może pokazać:** `.env`, kluczy, execution tokenów, danych SQLite, pełnych ścieżek użytkownika ani pełnych command lines.

## 2026-07-18 04:48 UTC — Pozytywny controlled-live Research Card

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser i publikacja były jawnie zabronione, a terminal zawiera prywatne ścieżki.
- **Co powinien pokazać:** zanonimizowane: jeden HTTP 200/`end_turn`, raw 4928≤16000, usage 16834/1961/51, jeden search, koszt `0.063278 USD`, karta `id=3`, lifecycle `DONE/SUCCESS/COMPLETE`, attempt `SETTLED`, gate/flags fail-closed i brak sidecarów.
- **Czego nie może pokazać:** `.env`, klucza, promptu, raw response, treści karty/źródeł, execution tokenu, pełnych command lines ani zawartości DB.

## 2026-07-17 19:44 UTC — Controlled-live 3000, terminalny schema failure

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser był zabroniony, a terminal zawiera prywatne ścieżki.
- **Co powinien pokazać:** zanonimizowane minimal gate diff `1/1`, jeden HTTP 200, `stop_reason=end_turn`, attempt `SETTLED`, usage `0.077160 USD`, schema failure pola `sources[0].supports_claim`, job/run/research_run `FAILED`, brak karty, gate/flags fail-closed i brak sidecarów.
- **Czego nie może pokazać:** `.env`, klucza, promptu, raw response, execution tokenu, pełnych command lines ani zawartości DB.

## 2026-07-17 20:46 UTC — Live po naprawie kontraktu, terminalne truncation

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser był zabroniony, a terminal zawiera prywatne ścieżki.
- **Co powinien pokazać:** zanonimizowane gate diff `1/1`, jeden HTTP 200, `stop_reason=max_tokens` przy limicie 3000, attempt `SETTLED`, usage `0.074312 USD`, `ResearchTruncatedError` przed schema, job/run/research_run `FAILED`, brak karty, gate/flags fail-closed i brak sidecarów.
- **Czego nie może pokazać:** `.env`, klucza, promptu, raw/truncated response, execution tokenu, pełnych command lines ani zawartości DB.

## 2026-07-19 — E2-C controlled fetch live-readiness candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser był zabroniony, a dowodem są deterministyczne logi/testy i trwałe inwarianty.
- **Co powinien pokazać:** zanonimizowane `1572/1572`, exact-once `378+389+394+411`, harness E2-C `13/13`, E2-B `13/13`, failpointy `4/4`, `compileall`/`git diff --check` PASS oraz produkcyjne `0014`, 14 migracji, SHA `9906AF…060836`, `364544 B`, integrity `ok`, FK `0`, sidecary `0`.
- **Dodatkowy kadr techniczny:** kontrpróba, w której resolver zwraca publiczny IP tylko raz, fake transport otrzymuje dokładnie ten sam `selected_address`, Host/SNI zachowują hostname, a zmiana resolvera przed requestem nie zmienia celu; obok odrzucenie forged capability i niespójnego bindingu.
- **Czego nie może pokazać:** `.env`, kluczy, cookies, pełnych lokalnych ścieżek, treści produkcyjnej SQLite, realnego URL przyszłego requestu, surowych payloadów ani danych logowania. Nie może sugerować `APPROVE`, gotowości live ani wykonanego realnego Fetch.

## 2026-07-19 — Production Schema Migration Orchestrator candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ browser był zabroniony, a terminal zawiera pełne lokalne ścieżki i fingerprinty operacyjne.
- **Co powinien pokazać:** zanonimizowany kontrakt CLI, `58/58`, full/exact-once `1630/1630`, partycje `390+398+412+430`, QA `30/30`, harnessy `13/13+13/13`, compile/diff PASS oraz produkcyjne `0014`, 14 migracji, SHA skrócone `9906AF…060836`, `364544 B`, integrity `ok`, FK `0`, sidecary `0`.
- **Dodatkowy kadr:** syntetyczny sidecar pojawiający się między snapshotem a writable open kończy się `STALE_DATABASE_STATE`/`WAL_PRESENT` bez migracji i bez usunięcia pliku; obok failpoint podczas `0017` pokazuje trwałe `0016` i bezpieczny owner-approved resume.
- **Czego nie może pokazać:** `.env`, pełnego SHA przyszłej autoryzacji, zawartości produkcyjnej DB/snapshotu, prywatnych ścieżek, command lines ani danych logowania. Nie może sugerować wykonanej migracji, `APPROVE`, zamknięcia Etapu 2 ani controlled-live readiness.

## 2026-07-22 — F1-BLOCK-01 / TOPIC_GENERATION settled recovery

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres jawnie zabraniał browsera, a log terminala zawiera lokalne ścieżki i identyfikatory operacyjne.
- **Co powinien pokazać:** zanonimizowaną sekwencję fake caller → `SETTLED`/usage=1 → reopen → maintenance → run/job `FAILED` → drugi maintenance no-op → Worker `IDLE` → nowy enqueue; obok publiczny resolver, odrzucenie innego kosztu/`NOT_CHARGED`/`CHARGE_UNKNOWN`, failpoint rollback oraz wynik `1821/1821`.
- **Czego nie może pokazać:** `.env`, sekretów, pełnych lokalnych ścieżek, zawartości produkcyjnej DB, request payloadów ani danych logowania. Nie może sugerować approvalu, merge'u, migracji produkcji, live verification ani zamknięcia Etapu 2.

## 2026-07-22 — Publiczny `controlled-live-topic-generation` candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres zabrania browsera, a terminal zawiera prywatne ścieżki i pełne fingerprinty operacyjne.
- **Co powinien pokazać:** zanonimizowane targetowanie jednego joba przez `claim_specific_job`, dwa joby na temp DB z drugim nadal `QUEUED/attempts=0`, replay z zerem drugich calli, restore pięciu flag po failpoincie, rozłączne exit codes oraz `1854/1854`, 0 skipped/xfail.
- **Stan produkcji na kadrze:** wyłącznie skrócony SHA `8f987c…8730af`, schema 0020, `696320 B`, integrity `ok`, FK `0`, sidecary `0`, z adnotacją `mode=ro&immutable=1` i `CONTROLLED-LIVE NOT EXECUTED`.
- **Czego nie może pokazać:** `.env`, kluczy, pełnych lokalnych ścieżek/SHA bindingu, promptu, intent preimage, approvalu, danych SQLite ani fake fixture. Nie może sugerować `APPROVE`, wykonanego requestu, zamknięcia Etapu 2 lub potwierdzonej LEVEL_3 readiness.

## 2026-07-23 — Pierwszy successful controlled-live TOPIC_GENERATION

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres jawnie zabraniał browsera, a terminal zawiera pełne lokalne bindingi.
- **Co powinien pokazać:** zanonimizowany checkpoint `SUCCESS`, attempt count 1 / `SETTLED`, usage count 1, job `DONE`, run `SUCCESS`, approval consumed, generated topics 2, selected topic `21`, actual cost `0.013128 USD`, search `0`, reconciliation false i policy flags restored.
- **Stan produkcji na kadrze:** skrócony SHA `91f593…56a1f`, schema 0020, integrity `ok`, FK `0`; osobno jawna obserwacja pustego WAL `0 B` i SHM `32768 B`, quiescence `PASS`.
- **Czego nie może pokazać:** `.env`, klucza API, pełnego promptu/intentu, lokalnych ścieżek, pełnych fingerprintów, zawartości SQLite ani surowej odpowiedzi. Nie może sugerować kolejnej zgody, publikacji, zamknięcia Etapu 2 ani LEVEL_3.

## 2026-07-23 — WAVE C1 repair candidate po `REJECT — MAJOR`

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ fala naprawcza jawnie zabrania browsera, a terminal zawiera lokalne ścieżki i fingerprint produkcyjnej bazy. Pierwszy niezależny review = `REJECT — MAJOR`; bieżący wynik = `C1 REPAIR CANDIDATE COMPLETE — AWAITING INDEPENDENT RE-REVIEW`.
- **Co powinien pokazać:** zanonimizowaną relację jawnych durable IDs Research Card/confirmed claim/source/excerpt/retrieval → frozen fingerprint → held CONTENT job; generation fence i jedną command boundary czterech lifecycle rows; kanoniczny provider parent + ścisłe extension 1:1; 25/25 kontrprób, 69/69 C1, collect 1923 / 1922 różne tekstowo node IDs, full 1923/1923, compile/diff PASS.
- **Stan produkcji na kadrze:** wyłącznie skrócony SHA `91f593…56a1f`, schema 0020, `700416 B`, integrity `ok`, FK `0`, WAL `0 B`, SHM `32768 B`, journal absent, z adnotacją `mode=ro&immutable=1` i `PRODUCTION MIGRATION NOT EXECUTED`.
- **Czego nie może pokazać:** `.env`, kluczy, pełnych lokalnych ścieżek, pełnych hashy/input preimages, treści karty lub evidence, danych SQLite ani command lines. Nie może sugerować approvalu, formalnego zamknięcia findings, wygenerowanej treści, C2, migracji produkcji, controlled-live, operacji Git lub zamknięcia Etapu 3.
## 2026-07-23 — WAVE C2 offline content pipeline candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres jawnie zabrania browsera, a screenshot terminala mógłby ujawnić lokalne ścieżki, pełne SHA lub prywatne źródło stylu.
- **Co powinien pokazać:** zanonimizowany flow Research Card `PROCEED` → frozen evidence → Content Plan → Article/Note Brief → fake writer intent → canonical attempt/zero-cost usage → draft → 9 evaluations → opcjonalnie jedna poprawka → `PENDING_APPROVAL`; route keys Fable 5/Sonnet 5 i jawne `UNVERIFIED` dla technicznych IDs/pricing.
- **Dowód tekstowy zastępczy:** C2 `22/22`; full/collect/exact unique `1945/1945`; zero duplikatów, skipped i xfail; produkcja nadal `0020`; koszt `0.000000 USD`.
- **Czego nie może pokazać:** raw style source, `.env`, sekrety, pełne lokalne ścieżki, produkcyjne rekordy, prawdziwy artykuł, dane API ani sugestię approvalu/merge/C3–C5.

## 2026-07-23 — WAVE C3 provider-ready writer candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres jawnie zabrania browsera, a terminal zawiera lokalne ścieżki i pełne fingerprinty.
- **Co powinien pokazać:** zanonimizowany flow logical ARTICLE/NOTE route → jawna konfiguracja provider/model/pricing → deterministic prompt fingerprint → jeden fake SDK/caller call → append-only provider result → jedno usage/settlement → draft/evaluations → `PENDING_APPROVAL`; obok fail-closed missing config przed SDK oraz call-returned/przed-result → `NEEDS_RECONCILIATION` bez drugiego calla.
- **Dowód tekstowy zastępczy:** C3 `26/26`; regresja `463/463`; full/collect/exact unique `1971/1971`; exact duplicates/skipped/xfail/errors `0`; compile/diff PASS; koszt `0.000000 USD`.
- **Stan produkcji na kadrze:** wyłącznie skrócony SHA `91f593…56a1f`, schema `0020`, `700416 B`, integrity `ok`, FK `0`, WAL `0 B`, SHM `32768 B`, journal absent; jawne `mode=ro&immutable=1`, `PRODUCTION MIGRATION NOT EXECUTED`.
- **Czego nie może pokazać:** raw style source, `.env`, secret/provider key, prompt/body/draft, pełnych hashy/ścieżek, danych SQLite ani fake fixture. Nie może sugerować niezależnego approvalu, commita/merge, realnego API, controlled-live, prawdziwego artykułu, C4/C5 ani zamknięcia C3.

## 2026-07-24 — WAVE C4 autonomous content decision candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres zabrania browsera, a terminal zawiera pełne lokalne ścieżki, hashe i szczegóły temp SQLite.
- **Co powinien pokazać:** zanonimizowany wspierany flow entrypoint → Worker → Dispatcher → C2/C3 → C4 PolicyEngine → snapshot/fingerprint → fenced transaction → append-only decision → `PENDING_APPROVAL|APPROVED|REJECTED|NEEDS_VERIFICATION|FAILED`; obok macierz LEVEL_1 human-required i LEVEL_3 offline autonomous.
- **Dowód tekstowy zastępczy:** C4 `23/23`; full/collect/unique `1994/1994`; 0 duplicates/skipped/xfail/failures/errors; produkcja nadal `0020`; kod `0024`; koszt `0.000000 USD`.
- **Stan produkcji na kadrze:** wyłącznie skrócony SHA `91f593…56a1f`, `700416 B`, 20 migracji/latest 0020, integrity `ok`, FK `0`, WAL `0 B`, SHM `32768 B`, journal absent; jawne `mode=ro&immutable=1`, `PRODUCTION MIGRATION NOT EXECUTED`.
- **Czego nie może pokazać:** `.env`, sekrety, private style content, draft/body/prompt, produkcyjne rekordy, pełne hashe/ścieżki ani sugestię niezależnego approvalu, zamknięcia C4, C5, API, publikacji lub merge.

## 2026-08-09 — PRE-C5 claim accounting & cost-cap candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres zabrania browsera, a terminal zawiera lokalne ścieżki i pełne fingerprinty. Dowód tekstowy i testy zastępują obraz w tej sesji.
- **Co powinien pokazać:** zanonimizowaną tabelę segmentów ARTICLE z ordinal/segment ID, trzema dozwolonymi klasyfikacjami, reason, evidence i kompletnym PASS/FAIL; obok fail-closed missing/duplicate/unknown/reviewer error. Drugi panel: reservation `0.050000` → jedno usage/actual `0.075000` → attempt `NEEDS_RECONCILIATION` → content/job `NEEDS_VERIFICATION` + run `STOPPED` → reaper no-op.
- **Dowód tekstowy zastępczy:** nowy moduł `38/38`, PRE-C5 `108/108`, zakres `436/436`, full `2102/2102`; produkcja `0020` i koszt rzeczywisty `0.000000 USD`.
- **Czego nie może pokazać:** `.env`, sekretów, raw style corpus, draftu/promptu, treści evidence, danych produkcyjnej SQLite, pełnych ścieżek/hashów ani sugestii niezależnego approvalu, C5/live readiness, publikacji lub operacji Git.

## 2026-08-09 — PRE-C5 question semantic boundary candidate

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres zabrania browsera, a terminal zawiera lokalne ścieżki i pełne fingerprinty. Dowód tekstowy i testy zastępują obraz w tej sesji.
- **Co powinien pokazać:** zanonimizowaną macierz `question × reviewer output`: `NON_FACTUAL_PROSE → BLOCK`, `ARGUMENT_OR_INFERENCE/true → BLOCK`, grounded bez evidence → BLOCK, grounded z in-package evidence → PASS; obok non-factual `honest_inference → PASS` i jawny trust-boundary control.
- **Dowód tekstowy zastępczy:** question module `183/183`, PRE-C5 `291/291`, affected `362/362`, full/collect/exact unique `2285/2285`, exact duplicates `0`, compile/diff PASS. Produkcja i style corpus PRE=POST byte-identical; koszt `0.000000 USD`.
- **Czego nie może pokazać:** `.env`, sekretów, raw style corpus, draftu/promptu/evidence content, danych produkcyjnej SQLite, pełnych lokalnych hashy/ścieżek ani sugestii approvalu, realnego reviewera, C5/live readiness, publikacji lub operacji Git.

## 2026-08-09 — PRE-C5 question marker repair

- **Status:** `SCREENSHOT REQUIRED`; screenshotu nie wykonano, ponieważ naprawa zabrania browsera, a terminal zawiera pełne lokalne ścieżki i fingerprinty. Dowód tekstowy i testy są właściwym artefaktem tej sesji.
- **Co powinien pokazać:** zanonimizowane PRE `endswith("?")` kontra POST `?/？ anywhere`, warianty `?!`, `?.`, `?;`, `?...`, quote/bracket oraz pięć MAJOR examples: wrong `NON_FACTUAL_PROSE → BLOCK`; obok sweep `216 → 0 leaks` i kontrole grounded/honest inference.
- **Dowód tekstowy zastępczy:** module `220/220`, PRE-C5 `328/328`, affected `399/399`, full/collect/exact unique `2322/2322`, compile/diff PASS; produkcja i styl byte-identical; koszt `0.000000 USD`.
- **Czego nie może pokazać:** sekretów, raw style content, danych produkcyjnej SQLite, pełnych ścieżek/hashów ani sugestii approvalu, C5/live readiness, publikacji lub operacji Git.

## 2026-08-09 — PRE-C5 model-family routing & qualification core

- **Status:** `SCREENSHOT REQUIRED`; obrazu nie wykonano, ponieważ zakres zabrania browsera, a właściwym dowodem są deterministyczne testy i trwałe rekordy na temp DB.
- **Co powinien pokazać:** zanonimizowany flow role → allowed family → candidates 5/5.1/5.2/6 → availability/pricing/capability/qualification gates → pojedynczy ACTIVE; obok N+1 PASS promotion, FAIL/over-ceiling/innej family BLOCK, dwa procesy `PROMOTED + NO_CHANGE`, stary frozen intent na N i nowy na N+1.
- **Dowód tekstowy zastępczy:** new `31/31`, affected `748/748`, full/collect/exact unique `2353/2353`, exact duplicates `0`, compile/diff PASS; produkcja nadal `0020`, koszt `0.000000 USD`.
- **Czego nie może pokazać:** `.env`, sekretów, raw style corpus, danych produkcyjnej SQLite, pełnych ścieżek/fingerprintów ani sugerować realnego catalogue discovery, realnej kwalifikacji, aktywnego modelu, API, C5, publikacji, approvalu lub operacji Git.

## 2026-08-10 — C5 provider contract freeze

- **Status:** `SCREENSHOT REQUIRED`; screenshotu nie wykonano, ponieważ fala zakazuje browsera/runtime sieci, a właściwym dowodem są deterministyczne fake SDK fixtures i temp DB ledgers.
- **Co powinien pokazać:** request kwargs `inference_geo=global`, `service_tier=standard_only`; returned `global/standard → legal`, `us|priority → NEEDS_VERIFICATION`; brak retention evidence → caller `0`; refusal → caller `1`, usage/cost zachowane, PASS/capability/retry/fallback/caller2 `0`.
- **Dowód tekstowy zastępczy:** new `22/22`, affected `330/330`, full/collect `2481/2481`, exact duplicates `0`, compile/diff PASS; production `0020`, actual cost `0.000000 USD`.
- **Czego nie może pokazać:** `.env`, sekretów, workspace settings Anthropic, raw style corpus, danych produkcyjnej SQLite, realnego retention acceptance, realnego requestu/API, C5, publikacji ani operacji Git.
