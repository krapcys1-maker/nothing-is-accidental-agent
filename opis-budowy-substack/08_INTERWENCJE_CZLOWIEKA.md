# 08 — INTERWENCJE CZŁOWIEKA

> **2026-07-17 — checkpoint LA-02:** właściciel przekazał `APPROVE WITH MINOR/P2` i pozwolił wyłącznie na P2 cleanup, jeden selektywny commit oraz push bieżącej gałęzi. Jednocześnie utrzymał zakaz live/API/SDK/providera/browsera/publikacji/kosztu, zmiany gate/flags/DB, nowego enqueue, PR i merge. P2-2 pozostaje otwartą obserwacją; druga próba nie jest autoryzowana.

> **2026-07-17 — decyzja LA-01-R1:** właściciel przekazał werdykt niezależnego review `REJECTED — MAJOR` i autoryzował jedną pełną falę napraw P1-01…P1-06/P2-01…P2-04. Jednocześnie zabronił realnego API/SDK, sieci, browsera, publikacji, kosztu, produkcyjnych zapisów, Windows Tasks i operacji Git. Wynik kandydacki: 1151/1151 offline; realny controlled acceptance pozostaje niewykonany.

> **2026-07-17 — review i checkpoint LA-01-R1:** kolejny niezależny review zatwierdził naprawę jako `APPROVE WITH MINOR/P2`; właściciel autoryzował jeden selektywny commit i push bieżącej gałęzi. Open P2 sanitizera pozostaje jawny, nieblokujący i poza reviewed diffem. Prywatne instrukcje oraz wcześniejszy blok BUILD_LOG pozostają lokalne. Ta decyzja nie autoryzuje live acceptance ani realnego API.

> **2026-07-17 — ceny i granice przyszłego acceptance:** właściciel zatwierdził konkretny profil Anthropic/Sonnet 5, topic `3`, `1500` tokenów, jeden web search i cap `0.12 USD`, ale wyłącznie do utworzenia lokalnego profilu i preflightu. Jawnie nie zezwolił na gate, enqueue, flagi, workera, API, retry ani Git. Preflight uszanował tę granicę: profil jest gotowy, wykonanie pozostaje zablokowane do osobnej decyzji i post-enqueue fingerprintu.

> **2026-07-17 — dokładnie jedna autoryzowana komenda:** właściciel zatwierdził istniejący job/request/session i jeden provider boundary, bez retry ani attemptu #2. Komenda zakończyła się jednak `PREFLIGHT_FAILED` przed providerem. Zgodnie z decyzją człowieka nie uruchomiono jej drugi raz; gate przywrócono do `False`, flags pozostały fail-closed, a wynik czeka na niezależny review.

> **Formalne zamknięcie WAVE 1A (2026-07-16):** implementer zadeklarował `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; niezależny reviewer odtworzył 1036/1036 i wykonał własne kontrpróby (149/149 `Worker.run_once`, 36/36 SQLite floor, 30/30 recovery/reaper/crash-window), po czym wydał `APPROVE WITH MINOR/P2`. Właściciel formalnie zamknął WAVE 1A jako `CLOSED — APPROVED WITH P2`. P2-1 i P2-2 pozostają jawne, lecz nieblokujące. Etap 1 nadal `BLOCKED`, live API nadal `ZABRONIONE`; Etap 2 nie został rozpoczęty.

## [2026-07-16] DECYZJA STRATEGICZNA — formalne zamknięcie WAVE 1A

- **Co agent chciał zrobić:** przekazać naprawę `W1A-R4-01` jako kandydata do niezależnego review, bez samodzielnego zamknięcia WAVE.
- **Dlaczego człowiek zareagował:** dopiero niezależne odtworzenie testów i własne kontrpróby reviewera dały podstawę do formalnej decyzji.
- **Co zmieniono:** właściciel przyjął werdykt `APPROVE WITH MINOR/P2` i zamknął wyłącznie WAVE 1A; P2-1/P2-2 pozostają opisanymi granicami.
- **Efekt:** WAVE 1A = `CLOSED — APPROVED WITH P2`; Etap 1 = `BLOCKED`; live API = `ZABRONIONE`.
- **Czas człowieka:** nie podano; interwencja była formalną decyzją zakresową.

> **Historyczna aktualizacja po czwartym review, przed finalnym re-review (2026-07-16):** właściciel przekazał dokładną kontrpróbę `W1A-R4-01` i autoryzował pełną naprawę systemową, testy oraz dokumentację, jednocześnie utrzymując zakaz sieci, providera, kosztu, zapisu do chronionej bazy i operacji Git. Człowiek wymusił test przez prawdziwy `Worker.run_once`, pełną mapę ścieżek terminalnych i niezależną próbę obalenia. Efekt: centralna atomowa granica, defense-in-depth SQLite i **1036 testów offline**. Na tym historycznym etapie człowiek nie zatwierdził ani nie zamknął WAVE: status implementera brzmiał `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`, live API `ZABRONIONE`.

> **Post-migration review QP-01 (2026-07-16):** właściciel dostarczył ukończony niezależny review z werdyktem `APPROVE WITH MINOR/P2`. Reviewer nie modyfikował repozytorium; implementer checkpointu nie wykonywał review. QP-01 jest `APPROVED`, produkcja `VERIFIED / SCHEMA 0014`, nowy baseline `VERIFIED`. Człowiek zezwolił na checkpoint po wykluczeniu prywatnych zmian, utrzymując Etap 1 `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE` i zakaz live API.

## [2026-07-16] POPRAWKA KODU — czwarty niezależny reject

- **Co agent chciał zrobić:** uznać lokalny wyjątek wykonania za zwykłe niepowodzenie joba.
- **Dlaczego człowiek zareagował:** kontrpróba pokazała, że rozpoczęty attempt pozostaje poza kolejką operatora i nadal blokuje budżet.
- **Co zmieniono:** każda terminalna decyzja przypiętego researchu przechodzi przez StoragePort, który sprawdza durable attempt; SQLite blokuje obejście.
- **Efekt:** `RESERVED`/`REQUEST_STARTED` są widoczne jako reconciliation, bez retry i bez provider calla; pełny suite 1036/1036.
- **Czas człowieka:** nie podano; interwencja obejmowała decyzję zakresową i warunki akceptacji, nie ręczne rozstrzygnięcie danych produkcyjnych.

> **Stan checkpointu:** właściciel przekazał wynik `APPROVE WITH MINOR/P2` i zlecił wyłącznie staging oraz walidację. WAVE 0B = `APPROVED WITH P2 — READY FOR CHECKPOINT`; bez commita, pushu, PR lub merge.
>
> **Aktualizacja WAVE 1A (2026-07-15):** powyższy checkpoint WAVE 0B jest historyczny. Właściciel zlecił naprawę odrzuconej fali WAVE 1A (`REJECTED — MAJOR`) wyłącznie offline, bez stagingu/commita/pushu/PR/merge. WAVE 0B = `CLOSED — APPROVED WITH P2`; WAVE 1A = `CANDIDATE`. **980 testów offline, 14 migracji**; historyczne 894/13 i `READY FOR CHECKPOINT` są historyczne. Etap 1 `BLOCKED`, live API `ZABRONIONE`.
>
> **Aktualizacja audyt (2026-07-16):** właściciel zlecił pełny audyt software-assurance całego working tree z autoryzacją jednej fali napraw. Wynik: zero MAJOR/CRITICAL, trzy MINOR naprawione (kontrolowane błędy CLI `list-reconciliations`, martwe pole `version_token`, anotacja typu kosztu), jeden P2 report-only (stuck attempt po crashu i wygaśnięciu lease — konserwatywny, wymaga decyzji właściciela). Testy **980 → 982**, chroniona baza byte-identical. WAVE 1A nadal `CANDIDATE — AWAITING INDEPENDENT REVIEW`.
>
> **Aktualizacja po trzecim review (2026-07-16):** niezależny reviewer przeklasyfikował stuck attempt na **MAJOR BLOCKING** i wykazał dwa kolejne MAJOR na surowym SQLite (terminalizacja bez pełnego lifecycle/eventu; mutowalny kanon kosztu po settlement). Właściciel autoryzował pełną falę naprawczą: recovery eskaluje oba crash-windows do kolejki operatora z trwałym audytem `AUTO_ESCALATION`; nigdy-niestartowany request może być rozstrzygnięty wyłącznie `NOT_CHARGED`; terminalizacja attemptu wymaga na poziomie SQLite pełnego spójnego stanu końcowego, a kanon i cache są po niej zamrożone. Testy **982 → 1007**, chroniona baza byte-identical. WAVE 1A nadal `CANDIDATE — AWAITING INDEPENDENT REVIEW`; decyzja o człowieku pozostaje w środku pętli: automat tylko eskaluje i czeka na operatora.

## Cel pliku

> **Aktualizacja:** WAVE 0B i WAVE 1A są `CLOSED — APPROVED WITH P2`. WAVE 1A nadal wymaga operatora L1 w przewidzianych stanach P2; jej formalne zamknięcie nie zamyka Etapu 1. Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## [2026-07-15] Decyzja człowieka pozostaje częścią reconciliation

Właściciel zezwolił na narzędzie, nie na automatyczną decyzję. Operator musi podać account, attempt, wynik finansowy, wynik wykonawczy, własną identyfikację i notatkę, a CLI najpierw pokazuje podgląd. Ta interwencja jest celowa: system nie może sam zdecydować, czy zaginiona odpowiedź dostawcy oznacza koszt zero, koszt znany czy koszt nadal nieznany.
Rejestr każdej sytuacji, w której **człowiek** wkroczył: odrzucił temat, poprawił artykuł/Note/komentarz, zatrzymał publikację, zmienił strategię, poprawił kod, zmienił poziom autonomii albo użył kill switcha. Dla każdej: co agent chciał zrobić, dlaczego człowiek zareagował, co zmieniono, jaki efekt, ile czasu. To bezpośredni pomiar odpowiedzi na pytanie eksperymentu: **ile nadzoru agent naprawdę potrzebuje.**

> **Ważne rozróżnienie (ADR-017):** dwa typy interwencji mają zupełnie inną trajektorię oczekiwaną w czasie. **Zmiana poziomu autonomii** i **decyzje strategiczne** pozostają na stałe rolą człowieka — to nie ma zniknąć, docelowo to JEDYNA trwała bramka „per decyzja" (nie per treść). **Poprawki pojedynczych treści** (artykuł/Note/komentarz) i **odrzucenia tematów** powinny z czasem **maleć** w miarę przechodzenia na wyższe poziomy autonomii — to jest dokładnie to, co ten plik ma pokazać liczbowo. Jeśli po przejściu na LEVEL_2 poprawki treści nie maleją, to sygnał, że progi jakości (scoring) są ustawione za nisko, nie że trzeba wrócić do ręcznej akceptacji na stałe.

## Szablon wpisu
```markdown
### [YYYY-MM-DD] <typ interwencji>
- **Co agent chciał zrobić:**
- **Dlaczego człowiek zareagował:**
- **Co zmieniono:**
- **Efekt:**
- **Czas człowieka:**
```
Typy: DECYZJA STRATEGICZNA · ODRZUCENIE TEMATU · POPRAWKA ARTYKUŁU · POPRAWKA NOTE · POPRAWKA KOMENTARZA · STOP PUBLIKACJI · ZMIANA AUTONOMII · POPRAWKA KODU · KILL SWITCH · LOGIN.

---

## Faza dotychczasowa — charakter interwencji
Na obecnym etapie (przed generacją treści i publikacją) interwencje człowieka miały charakter **strategiczno-decyzyjny i bramkujący**, nie redakcyjny. Właściciel nie poprawiał jeszcze żadnego tekstu (bo żaden nie powstał), za to podjął kluczowe decyzje kierunkowe i wielokrotnie **zatrzymał** agenta przed kosztem/publikacją.

### [2026-07-11] DECYZJE STRATEGICZNE (pakiet startowy)
- **Co agent chciał zrobić / zaproponował:** rekomendacje z audytu (m.in. wybór poziomu autonomii, panelu, polityki budżetu, obsługi klucza, zakresu MVP).
- **Dlaczego człowiek zareagował:** to decyzje właścicielskie, nie techniczne — wymagały wyboru człowieka.
- **Co zmieniono / ustalono:** MVP tylko na koncie `nothing_is_accidental` (ADR-007); nisza żony = astrologia (ADR-008); panel = FastAPI (ADR-009); docelowy sufit autonomii = LEVEL_2 z bramkowaniem (ADR-004); klucz — tylko `.gitignore`, bez rotacji (ADR-010); budżet 2/dzień, 40/mies. z priorytetem miesięcznym (ADR-012); integracja z istniejącym kontem przez Playwright po ręcznym logowaniu (ADR-011).
- **Efekt:** jednoznaczny kierunek MVP; zamknięcie wszystkich decyzji otwartych z audytu.
- **Czas człowieka:** przegląd i decyzje w ramach sesji planistycznej (dzień 2026-07-11).

### [2026-07-11] STOP przed kosztem — trzy zatrzymania
- **Co agent chciał zrobić:** przejść dalej po każdym etapie (po planie → do kodu; po skeletonie → do researchu; po researchu → do pierwszego **płatnego** wywołania Anthropic).
- **Dlaczego człowiek zareagował:** twarda zasada projektu — nie kodować przed akceptacją, nie wydawać budżetu bez zgody, zatrzymać się i czekać.
- **Co zmieniono:** po każdym etapie agent **zatrzymał się** i czekał; realne API pozostało nieuruchomione (dostępne przez `--real`, świadomie nieużyte).
- **Efekt:** 0.00 USD realnego kosztu; pełna kontrola tempa; brak niespodzianek kosztowych.
- **Czas człowieka:** decyzja „idź dalej / czekaj" po każdym etapie.

### [2026-07-11] POPRAWKA KODU (drobna, wychwycona samodzielnie)
- **Co agent chciał zrobić:** dostarczyć działający pipeline researchu.
- **Dlaczego reakcja:** błędny import w teście (`app.workflows.research.validation` zamiast `app.research.validation`).
- **Co zmieniono:** poprawiony import (wychwycony przed runem, nie wymagał interwencji właściciela).
- **Efekt:** 44 testy przechodzą.
- **Czas człowieka:** 0 (samonaprawa) — odnotowane dla pełności.

### [2026-07-11] DECYZJA STRATEGICZNA — doprecyzowanie celu: pełna autonomia (ADR-017)
- **Co agent chciał zrobić / co sugerowała dotychczasowa dokumentacja:** dokumentacja (macierz akceptacji, ADR-004, większość plików `opis-budowy-substack/`) zaczęła sugerować, że ręczna akceptacja każdej pojedynczej akcji jest stanem docelowym systemu.
- **Dlaczego człowiek zareagował:** to nieporozumienie względem pierwotnego celu eksperymentu — właściciel chciał agenta, który SAMODZIELNIE prowadzi konto (LEVEL_3), nie asystenta generującego wyłącznie szkice do klikania.
- **Co zmieniono:** pełna redefinicja dokumentacji (ARCHITECTURE.md, IMPLEMENTATION_PLAN.md CZĘŚĆ D, ADR-017, komplet plików opis-budowy-substack/) — jawna specyfikacja czterech poziomów autonomii, warunków przejścia, Autonomous Interaction Engine, SAFE MODE. **Zero kodu w ramach tej interwencji** — wyłącznie korekta dokumentacji, zgodnie z jawnym poleceniem właściciela „zatrzymaj się i poczekaj na zgodę przed kodowaniem".
- **Efekt:** spójna definicja celu w całej dokumentacji; gotowy, szczegółowy plan wdrożenia LEVEL_2/LEVEL_3, jeszcze niezaimplementowany.
- **Czas człowieka:** jedna, precyzyjna wiadomość z pełną specyfikacją oczekiwań (poziomy, warunki przejścia, scoring, SAFE MODE) — dużo bardziej efektywne niż punktowe poprawki, bo skorygowało założenie u źródła, zanim wpłynęło na kod.

---

## Interwencje jeszcze nieodnotowane (spodziewane w kolejnych etapach)
- **ODRZUCENIE TEMATU / POPRAWKA ARTYKUŁU/NOTE/KOMENTARZA** — pojawią się dopiero, gdy powstaną treści (Etap 2+). To będzie kluczowy materiał: ile % treści agenta przechodzi bez poprawek.
- **LOGIN** — jednorazowe ręczne logowanie do Substacka (Etap 4), zapisywane tu i w `docs/HUMAN_INTERVENTIONS.md`.
- **KILL SWITCH / STOP PUBLIKACJI** — dotąd nieużyte w sensie awaryjnym.

## Metryki nadzoru (do wypełniania)
| Metryka | Wartość na 2026-07-11 |
|---|---|
| Decyzje strategiczne człowieka | 9 (ADR-004/007/008/009/010/011/012/017 + zakres) |
| Zatrzymania przed kosztem/publikacją | 3 |
| Zmiany poziomu autonomii (formalne) | 0 (wciąż LEVEL_0/LEVEL_1 — plan przejść dopiero zdefiniowany, ADR-017) |
| Odrzucone tematy | — (brak generacji) |
| Poprawki treści (art./Note/komentarz) | — (brak generacji) |
| Użycia kill switcha (awaryjne) | 0 |
| Łączny czas człowieka | do uzupełnienia (sesja planistyczna 1 dzień) |

**Do śledzenia od LEVEL_2:** wskaźnik poprawek treści powinien maleć wraz z dojrzewaniem scoringu — to kluczowa metryka odpowiadająca na pytanie eksperymentu wprost.

## Powiązania
- `docs/HUMAN_INTERVENTIONS.md` (źródło), `06_DECYZJE_PROJEKTOWE.md`, `09_KOSZTY.md`

### [2026-07-12] Zgoda na Task 4
- Właściciel dopuścił wyłącznie ustawienie `USED`, jawny force re-research i regresje; zachował zakaz API oraz automatycznych płatnych ponowień.
- Efekt: Task 4 wykonano offline, bez realnego researchu i bez zmian bazy źródłowej.

### [2026-07-12] Zgoda na korektę Task 4 po review
- Właściciel ograniczył poprawkę do czterech P1, fail-closed i dokumentacji; race condition pozostawił jako P2.
- Efekt: pełna finalizacja i regresje wykonane offline, bez API, commita, pushu ani Task 5.

### [2026-07-12] Zgoda na wyłącznie Task 5
- Właściciel zatwierdził centralny budżet i retry callback, wymagając pełnych testów offline.
- Granice: bez API, realnego researchu, Task 6, commita i pushu; P2-17 i P2-18 bez zmian.
- Efekt: 242 testy, koszt 0 USD, working tree pozostawiony do review.

### [2026-07-12] Właściciel nakazał poprawić findings, nie tylko wydać REJECT
- Review znalazło pięć P1 w Task 5; właściciel jawnie rozszerzył pracę o ich natychmiastową korektę i regresje.
- Efekt: 257 testów, bez API, commita, pushu, Task 6 i zmian P2-17/P2-18.

### [2026-07-12] Zgoda na Task 6 z obowiązkowym self-review
- Właściciel zatwierdził wyłącznie wyrównanie klienta tematów: usage przed parse, ścisły code fence, typowane błędy i trwały `FAILED` bez częściowych topics.
- Polecenie wymagało poprawienia każdego znalezionego P0/P1 przed raportem i pozostawienia working tree bez commita/pushu.
- Efekt: self-review poprawił kolejność text/usage; 286 testów offline, koszt 0 USD, brak API, Task 7 nierozpoczęty.

### [2026-07-12] Zgoda na Task 8 i zakaz rozpoczęcia Task 9
- Właściciel zatwierdził pełną inwentaryzację statusów, atomowe guardy, typowane błędy, race/reopen tests i poprawę każdego P0/P1.
- Granice: bez API, realnego researchu, Playwrighta, migracji bez konieczności, commita i pushu; P2-17/P2-18/P2-19 bez zmian.
- Efekt: ADR-027, 44 nowe testy i 330 pełnych; working tree pozostawiony do niezależnego review.

### [2026-07-13] Właściciel ograniczył korektę do dwóch P1 Task 8
- Zakres: osobny kontrakt nieudanego research resume oraz rzeczywiście równoległy candidate claim.
- Zakazy utrzymane: bez API, realnego researchu, Playwrighta, Task 9, Etapu 1, commita i pushu; P2-17/P2-18/P2-19 bez zmian.
- Efekt: oba P1 poprawione, 337 testów offline, working tree pozostawiony do krótkiego review.

### [2026-07-13] Właściciel zatwierdził dokładnie jeden płatny Task 9
- Zakres: topic #2, staged A1/A2/B, cap 0,55 USD, `max_retries=0`, dokładna komenda ADR-022.
- Zakazy: bez drugiego runu, retry, resume, force, Playwrighta, publikacji, Etapu 1, commita i pushu.
- Efekt: A1 i 4×A2 sukces; B `max_tokens`/parse-error; koszt 0,170050 USD. Codex zatrzymał się po pierwszym runie i pozostawił dokumentację do review.

### [2026-07-13] Właściciel ograniczył naprawę do pracy offline
- Dozwolone: kod, fake callery, plikowa SQLite, testy i dokumentacja.
- Niedozwolone: API, resume, drugi run, ręczna zmiana realnej bazy, Playwright, publikacja, commit i push.
- Efekt: 351 testów zielonych, koszt 0 USD; osobna zgoda nadal potrzebna zarówno na repair auditu, jak i późniejszy płatny resume B.

### [2026-07-13] Właściciel osobno zatwierdził lokalny repair auditu
- Dozwolone: backup, pełne preconditions, warunkowa zmiana `RUNNING → FAILED`, `finished_at`, audytowalny `error` i weryfikacja po reopen.
- Niedozwolone: API, resume, retry, A1, A2, B, drugi run oraz jakakolwiek zmiana kosztu lub danych researchu.
- Efekt: jeden rekord zmieniony (`rowcount=1`), koszt historyczny nadal 0,170050 USD, koszt operacji 0 USD; staged research jest gotowy tylko do osobno zatwierdzonego resume B.

### [2026-07-13] Właściciel zatwierdził dokładnie jeden płatny resume B
- Dozwolone: oficjalny resume istniejącego runu, wyłącznie synteza B, 3000 tokenów, zero retry, absolutny cap 0,20 USD.
- Niedozwolone: nowy run, A1/A2, discovery/extraction, force, drugi B, Playwright, publikacja i Etap 1.
- Efekt: jeden call `end_turn`, 0,013914 USD; finalny run 0,183964 USD, card #2 i zamknięcie Etapu 0. Jakościowe REJECT zachowano bez obchodzenia bramki.

### [2026-07-13] Właściciel zezwolił na pierwszy blocker przygotowawczy Etapu 1
- Dozwolone: typowane mapowanie błędów Anthropic, zamknięta polityka retry, testy offline i dokumentacja.
- Niedozwolone: API, research/resume, scheduler, jobs, workery, rezerwacje budżetowe, commit i push przed niezależnym review.
- Efekt: kontrakt gotowy w working tree, 382 testy, koszt 0 USD; infrastruktura wykonawcza Etapu 1 nadal nie powstała.

## [2026-07-14] Właściciel zlecił WAVE 0B

- Zakres: trwałe request_id, operation-key, job-only fresh real research, atomowa rezerwacja przed providerem i fail-closed reconciliation.
- Zakazy: API, sieć, browser, publikacja, koszt, modyfikacja `data/agent.db`, WAVE 1, commit, push i merge.
- Stan przekazania: `WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; Etap 1 nie jest zamknięty.

## 2026-07-14 — Właściciel zawęża naprawę WAVE 0B.1

Właściciel zlecił usunięcie dokładnie trzech P1 z niezależnego review oraz tylko bezpośrednio związanych testów P2. Zakres wykluczał API, sieć, browser, publikację, płatne akcje, zapis produkcyjnej bazy i rozpoczęcie WAVE 1A. Rezultat pozostaje kandydatem do niezależnego ponownego review, nie decyzją o zamknięciu etapu.

## 2026-07-15 — Właściciel zlecił jedną końcową falę W0B-REV-09/10

- Zakres: ujednolicić rounding kosztów, dopisać regresje graniczne i uzupełnić kronikę; P2 usunąć wyłącznie po dowodzie nieosiągalności lub braku użycia.
- Zakazy: API, sieć, browser, realny provider, koszt, zapis lub migracja `data/agent.db`, stage, commit, push, PR i merge.
- Granica decyzji: nie wolno zamknąć WAVE 0B ani Etapu 1. Wynik ma być przekazany do niezależnego re-review.

## 2026-07-15 — Właściciel zlecił domknięcie W0B-RR-01 / W0B-CLEAN-01

- Zakres: usunąć tylko potwierdzoną lukę w agregacji round-half-up i decyzjach finansowych oraz dwa martwe konstruktory klienta w prywatnym resume; dodać regresje graniczne i zaktualizować dokumentację po testach.
- Zakazy: API, sieć, browser, realny SDK/provider, koszt, zmiana `data/agent.db`, zmiana lifecycle, request identity, `max_tokens`, schematu lub migracji, stage, commit, push, PR i merge.
- Granica decyzji: po walidacji working tree ma wrócić do krótkiego niezależnego re-review. WAVE 0B i Etap 1 nie są zamykane.

## 2026-07-16 — człowiek rozdzielił „gotowe technicznie” od „wolno uruchomić”

- Właściciel wybrał minimalny Windows Task Scheduler, ale nie zezwolił na rejestrację zadań.
- Zezwolił na przygotowanie i test migracji tylko na kopii; nie zezwolił na migrację ani podmianę `data/agent.db`.
- Live API, real SDK, browser, publikacja i koszt pozostały zabronione. Osobna przyszła zgoda ma obejmować dokładnie jeden job, jeden request, twardy cap i `max_retries=0`.
- Końcowy status implementera jest kandydacki. Formalne zamknięcie Etapu 1 pozostaje decyzją właściciela po niezależnym review i live acceptance.

## 2026-07-17 — człowiek odseparował naprawę obserwatora od prawa do ponowienia

- Właściciel pozwolił naprawić tylko observer effect, diagnostykę i standalone check oraz uruchomić testy na temp DB/fake callerach.
- Nie pozwolił włączyć gate'u, zmieniać flags, uruchamiać workera, providera lub drugiej próby controlled-live. Nie zezwolił też na sieć, browser, publikację, koszt ani Git.
- Wymusił testy legalnych launcherów i realnych blokerów, w tym drugiego entranta, workera, PID reuse, holdera DB oraz wycieku sekretu.
- Wynik pozostaje kandydatem LA-02 do niezależnego review. Nawet zielone 1174 testy nie zastępują nowej autoryzacji operacyjnej.

## 2026-07-17 — człowiek zamknął review LA-02, ale nie otworzył live

- Przyjęty werdykt: `APPROVE WITH MINOR/P2`; root cause `PROCESSES_PRESENT` uznany za `CLOSED`.
- Dozwolone: aktualizacja bieżącej dokumentacji, procedura P2-2, dokładna reguła ignore pricing profile, pełne testy offline, selektywny commit i push tej gałęzi.
- Niedozwolone: `controlled-live-once`, provider, SDK, sieć wykonawcza, nowy job, zmiana flags/gate, produkcyjny zapis, PR i merge.
- Następna decyzja właściciela może nastąpić dopiero po standalone quiescence check z tego samego launchera; każde `PROCESSES_PRESENT` zużywa plan i kończy się STOP.

## 2026-07-17 — człowiek zezwolił dojść do pierwszego requestu, ale tylko raz

- Właściciel zlecił naprawianie kolejnych false STOP-ów aż wrapper przejdzie preflight i wykona dokładnie jeden rzeczywisty request.
- Nie pozwolił wyłączyć żadnego zabezpieczenia: attempt #1, retry 0, cap 0,12 USD, request identity, ledger, settlement, lease, fence, marker i reconciliation pozostały obowiązkowe.
- Po `REQUEST_STARTED` autoryzacja została zużyta. Niepoprawny JSON i brak Research Card nie dają prawa do drugiego calla.
- Wynik: exactly one request, koszt 0,053182 USD, job terminalny `FAILED`, gate i flagi fail-closed, browser/publikacja/Git niewykonane.

## 2026-07-17 — człowiek zaakceptował review, ale nie wydał drugiej zgody live

- Właściciel przekazał `APPROVE WITH MINOR/P2` dla LA-03 i zlecił naprawę trzech P2 wyłącznie offline.
- Zażądał, by brak raw/stop reason został nazwany brakiem dowodu, nie pretekstem do ponownego requestu.
- Utrzymał granicę: terminalny job ma jeden wykorzystany attempt i nie może być retry'owany. Następny call wymaga nowej decyzji i nowego dozwolonego joba.
- Wynik P2 to kandydat do kolejnego niezależnego review, nie samodzielne zatwierdzenie i nie zamknięcie Etapu 1.

## 2026-07-17 — Właściciel ograniczył naprawę po `REJECT — MAJOR`

- Naprawić dokładnie NIA-P2-RV-01…05 i nie otwierać innych P2.
- Używać wyłącznie fake callerów/SDK seam i tymczasowych baz; zero sieci, kosztu, browsera, publikacji, produkcyjnego joba i operacji Git.
- Zachować produkcyjną DB/WAL/SHM byte-identical oraz nie dotykać chronionych prywatnych plików.
- Wynik może mieć tylko status `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; Etap 1 pozostaje otwarty.

## 2026-07-17 — Człowiek zezwolił na request, ale nie na zmianę gate

Granice decyzji były celowo węższe niż technicznie potrzebne do uruchomienia bieżącego entrypointu: jeden request był dozwolony, zmiana kodu nie. Operator nie potraktował celu jako zgody dorozumianej na `False→True→False`; zakończył przed enqueue z `BLOCKED — LIVE PREFLIGHT DRIFT`. Następny przebieg wymaga nowej decyzji, nie automatycznego resume.
