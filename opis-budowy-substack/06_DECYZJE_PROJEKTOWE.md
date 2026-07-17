# 06 — DECYZJE PROJEKTOWE

> **Stan bieżący LA-02 (2026-07-17):** `APPROVED WITH MINOR/P2 — CHECKPOINTED`; root cause `PROCESSES_PRESENT = CLOSED`; P2-2 false STOP = `OPEN OBSERVATION / DOCUMENTED`. Dowód: **1174/1174**, exact-once **284+284+298+308**, schema 0014, job `QUEUED/attempts=0`, provider request niewykonany, gate `False`, flags fail-closed. Etap 1 jest otwarty i czeka na nową autoryzację dopiero po standalone quiescence check z tego samego launchera.

> **Stan bieżący LA-01-R1 (2026-07-17):** pierwsza LA-01 = `REJECTED — MAJOR`; LA-01-R1 = `APPROVED WITH MINOR/P2 — CHECKPOINT AUTHORIZED`. Wybrano pełny frozen pricing contract (`Decimal`), trwałe session/job/request/attempt/token fencing, raport przed marker clear, recovery bez retry, prawdziwy reopen i wyłącznie pełny atomowy profil pięciu flag. Open P2 rekurencyjnej sanitizacji fallbacku jest jawny, nieblokujący i nie jest dokładany do reviewed diffu. Bieżący dowód to **1151/1151**, schema produkcji `0014`, 14 migracji. Live API i controlled acceptance niewykonane; Etap 1 otwarty.

### D-67: Durable provider attempt ma pierwszeństwo przed workerowym fallbackiem (→ ADR-067)

- **Problem:** Worker potrafił obsłużyć lokalny wyjątek przez terminalne `FAILED`, nie zauważając pozostawionego `RESERVED`/`REQUEST_STARTED`; operator nie widział próby, a rezerwacja blokowała budżet.
- **Opcje:** poprawić tylko jeden wyjątek; dodać kolejny etap recovery; albo scentralizować każdą terminalną decyzję researchu i dołożyć barierę SQLite.
- **Wybór:** jedna operacja StoragePort w transakcji `BEGIN IMMEDIATE`, używana przez Worker i pipeline, plus lifecycle guardy SQLite.
- **Dlaczego:** poprawność zależy od durable stanu attemptu, nie od klasy wyjątku ani lokalnej wiedzy wywołującego.
- **Zalety / Wady / Ryzyka:** spójna, idempotentna eskalacja i brak retry; większa złożoność macierzy stanów. P2-1 pozostaje fail-closed, a SQLite zapewnia floor trwałego stanu, nie dowód pochodzenia przeciw uprzywilejowanemu autorowi wielu tabel.
- **Kto podjął:** człowiek autoryzował zakres po niezależnym review; implementacja zgodna z tą decyzją.
- **Zmieniona później:** nie.

> **Stan decyzji checkpointu:** niezależny końcowy review ustanowił `WAVE 0B APPROVED WITH P2 — READY FOR CHECKPOINT`. Commit wymaga osobnej autoryzacji, push kolejnej; Etap 1 `BLOCKED`, live API `ZABRONIONE`.
>
> **Aktualizacja WAVE 1A (2026-07-15):** powyższy checkpoint WAVE 0B jest historyczny. WAVE 0B = `CLOSED — APPROVED WITH P2`; WAVE 1A = `CANDIDATE` po naprawie odrzucenia `REJECTED — MAJOR` (append-only `reconciliation_events`, pełna tożsamość usage, wyłączna własność Research Card, brak dead-endu `MANUAL`, spójność ledger↔cache, CLI preview/confirm z version tokenem, pełna walidacja lineage `W1A-VERIFY-02`). **980 testów offline, 14 migracji**; historyczne 894/13/948/955 i `READY FOR CHECKPOINT` są historyczne. Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## Cel pliku

> **Aktualizacja:** WAVE 0B = `CLOSED — APPROVED WITH P2`; ADR-062 wprowadza WAVE 1A jako kandydat do niezależnego review. Etap 1 `BLOCKED`, live API `ZABRONIONE`.

### D-62: Rachunek i wynik są dwiema decyzjami (↔ ADR-062)

Operator L1 wybiera osobno fakt finansowy i fakt wykonawczy. `model_usage` pozostaje jedyną księgą kosztu, dlatego stan reconciled przechowuje wyłącznie audit decyzji. Nieznany koszt nie jest usterką do automatycznego obejścia: zostaje rezerwacją i blokadą. Wynik `DONE` wymaga już istniejącej, prawidłowo powiązanej karty, nie samego rozliczenia. WAVE 1A nie dostaje providera, retry ani attemptu #2.
Redakcyjny zapis **każdej ważnej decyzji**: problem, opcje, wybór, dlaczego, zalety, wady, ryzyka, kto podjął, czy zmieniona później. Pełny, techniczny rejestr ADR jest w `docs/DECISIONS.md` — tu jest wersja narracyjna do artykułów.

## Szablon wpisu
```markdown
### D-XX: <tytuł>  (↔ ADR-XXX)
- **Problem:**
- **Opcje:**
- **Wybór:**
- **Dlaczego:**
- **Zalety / Wady / Ryzyka:**
- **Kto podjął:** człowiek | Claude | wspólnie
- **Zmieniona później:** nie | tak → D-YY
```

---

### D-01: Źródło prawdy dla wag scoringu tematów (↔ ADR-001)
- **Problem:** trzy dokumenty podawały różne wagi scoringu.
- **Opcje:** A) ARCHITECTURE/`growth_policy.yaml` (25/20/15/15/10/10/5); B) PROJEKT; C) MASTER.
- **Wybór:** A.
- **Dlaczego:** spójność z plikiem konfiguracyjnym, który staje się kodem — jedno źródło prawdy.
- **Ryzyka:** inne dokumenty pozostają jako „inspiracja"; trzeba pilnować, by nikt nie kodował z nich.
- **Kto podjął:** Claude (rekomendacja audytu). **Zmieniona później:** nie.

### D-02: Funkcja celu wzrostu (↔ ADR-002)
- **Problem:** ARCHITECTURE/YAML (45/20/15/10/5/5) vs MASTER (40/20/15/10/10/5 + konwersja).
- **Wybór:** ARCHITECTURE/`growth_policy.yaml`.
- **Dlaczego:** „konwersja profil→subskrypcja" nie jest wiarygodnie mierzalna na Substacku → nie może być składnikiem twardej funkcji celu.
- **Konsekwencja:** konwersja liczona jako metryka pomocnicza oznaczona jako **estymacja**. **Zmieniona później:** nie.

### D-03: Grafiki tylko SVG w MVP (↔ ADR-003)
- **Problem:** wizja zakładała fotorealistyczne „cinematic editorial images"; podejście Anthropic-only daje tylko SVG→PNG.
- **Wybór:** SVG-only za interfejsem `ImageProvider`; fotorealizm poza MVP.
- **Zalety:** zero kosztu grafik, pełna kontrola, brak ryzyka „dziwnych" obrazów. **Wady:** mniej „efektowne" okładki. **Ryzyko:** rozjazd z pierwotną wizją wizualną (świadomy). **Zmieniona później:** nie.

### D-04: Docelowy sufit autonomii = LEVEL_2 z bramkowaniem (↔ ADR-004)
- **Problem:** jak wysoko celować z autonomią bez utraty bezpieczeństwa.
- **Wybór:** cel = LEVEL_2 (auto-publikacja wybranych *typów* Notes), ale **za twardą bramką**: włącza się dopiero po Etapie 4, ≥1 tygodniu stabilnej jakości i jawnym przełączniku właściciela. Artykuły i komentarze **zawsze** za akceptacją — **na etapie startowym**.
- **Dlaczego:** architektura ma od razu wspierać cel, ale start musi być bezpieczny (efektywnie LEVEL_1/dry_run).
- **Kto podjął:** **człowiek (właściciel).** **Zmieniona później:** **doprecyzowana przez D-17 (ta sama data, później tego dnia)** — „artykuły/komentarze zawsze za akceptacją" opisywało fazę startową, nie architekturę docelową. Sedno D-04 (bezpieczny, stopniowy start) zostaje bez zmian.

### D-05: Brak publikacji w MVP-0 (↔ ADR-005)
- **Problem:** DoD zakłada publikację, ale `IMPLEMENTATION_PROMPT` zakazuje wdrażania publikacji teraz.
- **Wybór:** Etapy 0–3 offline (dry_run); publikacja od Etapu 4 i tylko po jawnej zgodzie.
- **Zaleta:** pierwszy MVP produkuje szkice do akceptacji, nic nie publikuje — zero ryzyka reputacyjnego. **Zmieniona później:** nie.

### D-06: Jedna baza SQLite ze scopingiem po account_id (↔ ADR-006)
- **Problem:** izolacja kont vs prostota raportów.
- **Wybór:** jedna baza; obowiązkowy `account_id` w `StoragePort`; testy izolacji.
- **Ryzyko:** pojedynczy zapomniany filtr = wyciek między kontami → pokryte testami izolacji. **Zmieniona później:** nie.

### [2026-07-12] Task 7: status rejestru dogonił stan projektu

ADR-001, ADR-002, ADR-003, ADR-005 i ADR-006 przez kolejne zadania działały jak decyzje przyjęte: wagi tematów pochodziły z configu, funkcja celu miała jedno źródło, MVP nie korzystał z zewnętrznego generatora grafik, publikacja była fizycznie wyłączona, a dane kont trafiały do jednej SQLite z izolacją. Rejestr nadal opisywał je jako `PROPOSED`.

Każdą decyzję sprawdzono osobno względem architektury, roadmapy, bieżącego stanu i repozytorium. Nie znaleziono nowszego ADR, który zastępowałby którąkolwiek z pięciu. Jedyna pozorna sprzeczność dotyczyła ADR-005: stare „od Etapu 4” pochodziło sprzed konsolidacji numeracji. W aktualnej roadmapie właściwa publikacja jest Etapem 5, lecz zasada bezpieczeństwa pozostaje ta sama — nic nie publikuje się wcześniej ani bez zgody właściciela.

Statusy zmieniono na `ACCEPTED` bez przepisywania historycznego uzasadnienia. Task 7 nie dotknął kodu, kosztował 0 USD i nie wykonał API.

### D-07: Zakres MVP = jedno konto (↔ ADR-007)
- **Problem:** trzy konta w architekturze, ale start ma być prosty.
- **Wybór:** MVP obsługuje wyłącznie `nothing_is_accidental`; `owner_account`/`wife_account` pozostają `active: false`.
- **Kto podjął:** **człowiek (właściciel).** **Zmieniona później:** nie (architektura wielokontowa zostaje, tylko nieaktywna).

### D-08: Nisza konta żony = astrologia (↔ ADR-008)
- **Problem:** `wife_account.niche` było puste — discovery komentarzy nie miałoby czego szukać.
- **Wybór:** nisza = astrologia; konto nadal wyłączone do czasu po MVP.
- **Kto podjął:** **człowiek (właściciel).** **Zmieniona później:** nie.

### D-09: Panel = FastAPI + prosty frontend (↔ ADR-009)
- **Problem:** Streamlit vs FastAPI.
- **Wybór:** FastAPI + prosty frontend, tylko localhost.
- **Dlaczego:** bliżej docelowej architektury i łatwiejsza migracja do chmury / API akceptacji. **Wada:** więcej pracy na starcie. **Kto podjął:** **człowiek.** **Zmieniona później:** nie.

### D-10: Klucz API — tylko `.gitignore`, bez rotacji teraz (↔ ADR-010)
- **Problem:** realny klucz w `.env`, brak `.gitignore`.
- **Wybór:** dodać `.gitignore` + `.env.example`; **nie** rotować klucza na tym etapie.
- **Ryzyko rezydualne (otwarte):** jeśli klucz gdzieś już trafił (kopia/backup), przed publicznym udostępnieniem repo **zalecana rotacja**. Utrzymane jako R1. **Kto podjął:** **człowiek (świadomie).** **Zmieniona później:** nie (pozycja otwarta).

### D-11: Integracja z istniejącym kontem Substack (↔ ADR-011)
- **Problem:** jak podłączyć agenta do konta, które już istnieje.
- **Opcje:** A) utworzyć nowe konto; B) połączyć się z istniejącym przez dedykowany profil Playwright po ręcznym logowaniu.
- **Wybór:** B.
- **Dlaczego:** konto istnieje; logowanie magic-linkiem = brak hasła do przechowania; pełna izolacja sesji; człowiek kontroluje uwierzytelnienie.
- **Ryzyka:** wygaśnięcie sesji, zmiany UI, ToS automatyzacji — mitygowane stop-conditions i brakiem publikacji teraz. **Kto podjął:** **człowiek.** **Zmieniona później:** nie.

### D-12: Budżet — miesięczny limit ma bezwzględny priorytet (↔ ADR-012)
- **Problem:** 2 USD/dzień × 30 = 60 USD > 40 USD/miesiąc — arytmetyczna niespójność.
- **Opcje:** A) obniżyć dzienny do ~1.30; B) zostawić 2.00/dzień + 40/mies., ale miesięczny nadrzędny (stop przy `month_to_date ≥ 40`).
- **Wybór:** B.
- **Dlaczego:** twardy sufit miesięczny + prostota. **Kto podjął:** **człowiek.** **Zmieniona później:** nie.

### D-13: Mechanizm dry_run + kolumna `model_usage.dry_run` (↔ ADR-013)
- **Problem:** jak zademonstrować „jedno wywołanie Anthropic" bez wydawania budżetu i bez sieci w testach.
- **Wybór:** dwa klienty (`FakeLLMClient` dry_run / `AnthropicLLMClient` realny, `--real`); kolumna `dry_run`; budżet sumuje tylko wpisy realne.
- **Dlaczego:** zero kosztu i sieci w MVP-0; realne wywołanie „o jeden przełącznik dalej"; testy szybkie i powtarzalne. **Kto podjął:** Claude (zgodnie z zasadą „bez realnych kosztów bez zgody"). **Zmieniona później:** nie.

### D-14: Deduplikacja tematów lokalna, bez płatnego modelu (↔ ADR-014)
- **Problem:** wykrywać duplikaty bez dodatkowego kosztu na każde sprawdzenie.
- **Opcje:** A) embeddingi (płatne per temat); B) lokalnie: znormalizowany tytuł + Jaccard + SequenceMatcher, próg z configu (0.72).
- **Wybór:** B (wymóg właściciela: „nie płać, jeśli można lokalnie").
- **Ryzyko:** próg to kompromis (odległe parafrazy mogą umknąć). **Kto podjął:** Claude wg wymagań właściciela. **Zmieniona później:** nie.

### D-15: Bramka jakości researchu + ochrona przed prompt injection (↔ ADR-015)
- **Problem:** model może halucynować i może być celem iniekcji z treści www.
- **Wybór:** twarda, deterministyczna walidacja **poza** modelem + guard neutralizujący polecenia w treści źródeł; decyzja opiera się na polach strukturalnych, nie na tekście źródła.
- **Zalety:** powtarzalna jakość, odporność na injection, pełny audyt. **Kto podjął:** Claude wg wymagań właściciela. **Zmieniona później:** nie.

### D-16: Dwuetapowy research (gather_sources + synthesize_card) zamiast jednego wywołania (↔ ADR-016)
- **Problem:** pierwsze realne wywołanie (jednoetapowe) kosztowało realnie 0,25 USD przy szacunku 0,095 USD (błąd ~+163%) i zakończyło się uciętym JSON-em — model próbował naraz szukać, czytać i syntetyzować pełną kartę w jednym wywołaniu.
- **Opcje:** A) tylko podnieść limit długości odpowiedzi modelu; B) podzielić research na dwa węższe wywołania — zbieranie źródeł osobno od analizy.
- **Wybór:** B (na polecenie właściciela).
- **Dlaczego:** samo podniesienie limitu nie usuwa przyczyny (zbyt wiele naraz w jednym wywołaniu), tylko przesuwa próg awarii. Podział pozwala też TANIO odrzucić słaby research po pierwszym kroku, zanim zapłacimy za drugi.
- **Zalety:** mniejsze ryzyko ucięcia w każdym z dwóch węższych wywołań; tania bramka wczesnego wyjścia; koszt drugiego kroku pod pełną kontrolą (zero wyszukiwania). **Wady/ryzyka:** więcej ruchomych części; oszczędność kosztu jest umiarkowana (~31% w projekcji) — główna korzyść to stabilność, nie tylko cena, i to jest jawnie tak opisane, nie sprzedawane jako więcej niż jest.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude. **Zmieniona później:** nie.

### D-17: Docelowym trybem projektu jest pełna autonomia operacyjna (↔ ADR-017)
- **Problem:** dokumentacja (macierz akceptacji, D-04, większość plików `opis-budowy-substack/`) zaczęła sugerować, że ręczna akceptacja KAŻDEJ akcji jest stanem docelowym — to było błędne odczytanie celu projektu.
- **Opcje:** A) system docelowo pozostaje asystentem generującym wyłącznie propozycje do ręcznego zatwierdzania; B) system docelowo prowadzi konto w pełni autonomicznie (LEVEL_3), a ręczna akceptacja jest mechanizmem fazy startowej i bramką przy zmianie poziomu autonomii.
- **Wybór:** B.
- **Dlaczego:** to był cel od początku — eksperyment sprawdza, czy agent potrafi SAMODZIELNIE prowadzić publikację, nie czy potrafi przygotowywać szkice do zatwierdzenia. „Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta."
- **Zalety:** zgodność z pierwotnym celem eksperymentu; wymusza budowę realnych mechanizmów jakości (scoring, SAFE MODE, log każdej decyzji) zamiast polegania wyłącznie na człowieku jako filtrze.
- **Wady/ryzyka:** wyższe ryzyko przy przejściu na LEVEL_2/3 (błąd trafia na żywą platformę bez człowieka w pętli na bieżąco) — mitygowane twardymi, mierzalnymi warunkami przejścia i SAFE MODE, oba wymagające jawnej zgody właściciela przy KAŻDYM podniesieniu poziomu.
- **Co się NIE zmienia:** zakaz wiadomości prywatnych i inicjowania kontaktu z innymi autorami — bezwzględny na każdym poziomie. *(Punkt o publicznym ujawnianiu AI, który tu pierwotnie stał, był błędny — poprawiony przez D-18 poniżej, ta sama data, później.)*
- **Kto podjął:** **człowiek (właściciel).** **Zmieniona później:** tak → **D-18** (2026-07-11, później tego dnia) — punkt „Co się NIE zmienia" błędnie zakładał publiczne ujawnienie AI; treść powyżej już poprawiona.

### D-18: Publiczna tożsamość publikacji i brak proaktywnego ujawniania automatyzacji (↔ ADR-018)
- **Problem:** D-17/ADR-017 błędnie założyły, że publikacja ma jawnie ujawniać AI-autorstwo na każdym poziomie autonomii. To był błąd w drugą stronę — konto publiczne nigdy nie miało tego robić proaktywnie.
- **Opcje:** A) publiczne ujawnienie AI w bio/materiałach (poprzednie, błędne założenie); B) konto działa jako anonimowa marka redakcyjna — bez proaktywnego ujawniania automatyzacji, ale też bez podszywania się pod konkretną osobę czy fikcyjnej biografii; prawda zostaje w prywatnej dokumentacji do osobnej decyzji właściciela.
- **Wybór:** B.
- **Dlaczego:** konto ma funkcjonować jak zwyczajna, anonimowa publikacja redakcyjna, nie jak eksponat eksperymentu od pierwszego dnia. Brak ujawnienia ≠ podszywanie się pod kogoś — nie ma fikcyjnego autora, fikcyjnej biografii ani fikcyjnych doświadczeń, jest tylko brak deklaracji, kto/co pisze.
- **Zalety:** czystszy eksperyment (mierzy się odbiór treści, nie „ciekawostkę o AI"); konto nie traci wiarygodności, zanim jakość zostanie udowodniona; prywatna dokumentacja i tak zachowuje pełną prawdę do przyszłej serii artykułów.
- **Wady/ryzyka:** pytanie wprost „czy jesteś botem?" wymaga jasnej zasady (rozwiązane: NO_REPLY, nigdy kłamstwo — patrz `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.5a`); zgodność z aktualnymi zasadami Substacka dot. treści AI pozostaje do zweryfikowania przez właściciela przed realną publikacją (Etap 4) — nie zakładam tego samodzielnie.
- **Kto podjął:** **człowiek (właściciel).** **Zmieniona później:** nie.

---

## Decyzje otwarte
**Otwarte do weryfikacji przez właściciela (nie rozstrzygam sam):** zgodność polityki braku ujawniania AI-autorstwa z aktualnym regulaminem Substacka — przed Etapem 4 (realna publikacja). Poza tym: **brak** innych otwartych pozycji z audytu. Jedyna utrzymywana pozycja ryzyka: **rotacja klucza API** (D-10/R1) przed ewentualnym publicznym udostępnieniem repo.

### D-27: stan źródłowy należy do UPDATE, nie do wcześniejszego SELECT
- **Problem:** dwa procesy mogły przeczytać ten sam status, po czym spóźniony zapisywał wynik na nowszym stanie.
- **Wybór:** każdy istniejący helper statusowy używa `status IN (...)`, właściwego flow i kontroli `rowcount`; po konflikcie odmawia typowanym błędem. Dane dodatkowe i status pozostają jedną transakcją.
- **Idempotencja:** no-op jest jawny per operacja. Resume zachowuje szczególne, zatwierdzone przejścia; retry kandydatur i reopen exhausted pozostają dostępne tylko przez osobny kontrakt.
- **Kto podjął:** właściciel zatwierdził Task 8; wykonanie i self-review: Codex. Pełny zapis: ADR-027.

### Korekta D-27 po review: jawny resume ma osobny kontrakt
- `finish_run` nie przepisuje terminalnego FAILED.
- `finish_resumed_research_run` wymaga workflow RESEARCH, wspólnego konta runu, research_runu i tematu, właściwego flow/statusu oraz tokenu `finished_at` odczytanego przed próbą.
- CAS w UPDATE rozstrzyga konkurencyjne zakończenia; drugi wynik jest konfliktem, nie cichym sukcesem ani lockiem uznanym przez test.
- Równoległość candidate jest dowodzona przez `Barrier`, nie przez sam fakt użycia dwóch połączeń.

## Powiązania
- `docs/DECISIONS.md` (pełne ADR-001…018), `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` (załącznik rozbieżności, CZĘŚĆ D, §D.5a)

### D-25: Kompletna karta wymaga jawnej decyzji o nowym koszcie (↔ ADR-025)
- **Problem:** po udanym researchu ten sam temat mógłby przypadkiem wejść w kolejny świeży, płatny run.
- **Wybór:** `COMPLETE` atomowo ustawia temat jako `USED`; świeży run z istniejącą kartą wymaga `--force-re-research`. Wznowienie nie przyjmuje tej flagi.
- **Dlaczego:** odzyskanie przerwanego runu i rozpoczęcie nowej próby to różne decyzje kosztowe. Druga musi być widoczna, ale nie może osłabiać pozostałych bramek.
- **Kto podjął:** człowiek zatwierdził zakres Task 4; wykonanie: Codex.

### Korekta D-25 po review: karta musi być kartą tego tematu
- **Problem:** sama referencja do istniejącej karty nie dowodziła, że należy ona do finalizowanego runu; osobny commit terminalnego runu zostawiał częściowy sukces po awarii.
- **Wybór:** kanoniczna finalizacja porównuje run–topic–card–account i obejmuje COMPLETE, terminalny run oraz USED jedną transakcją. Force omija wyłącznie poprawną blokadę duplikatu; nigdy uszkodzoną relację.
- **Ryzyko odłożone:** równoległe świeże procesy potrzebują później claimu/lease per temat (P2-17).

### Druga korekta D-25: identyczne powtórzenie = no-op, sprzeczne = odmowa

- **Problem:** atomowa finalizacja nadal pozwalała drugim wywołaniem przepiąć ukończony run do innej karty oraz nadpisać koszt i timestampy.
- **Wybór:** identyczny COMPLETE kończy się bez mutacji; inna karta, koszt, terminalny status, Stage B lub uszkodzona relacja powodują błąd integralności i rollback.
- **Dlaczego:** atomowość odpowiada, czy pojedyncza operacja zapisze się w całości. Idempotencja odpowiada, czy jej bezpieczne powtórzenie zachowa pierwotny audyt.
- **Dowód:** reopen SQLite i 206 testów; koszt 0 USD.

### Task 5 — jedna polityka budżetowa, klient bez wiedzy o bazie
Odrzucono wbudowanie SQLite i `PolicyEngine` do klienta Anthropic. Workflow przekazuje prosty callback przed próbą oraz callback utrwalenia dostępnego usage timeoutu. Klient zna numer próby i koszt nadchodzącego calla, ale nie zna magazynu danych ani limitów produktu. Decyzję opisuje ADR-026.

Po review doprecyzowano: realny pipeline bez capu odmawia, cap resume jest absolutny, a nie „dotychczas wydane + nowy limit”. To ostatnie rozróżnia limit całego zdarzenia od odnawialnego kredytu.

### D-28: jeden realny run ADR-022, bez automatycznego ratowania wyniku
- **Problem:** do zamknięcia Etapu 0 potrzebna była pierwsza realna karta, ale każdy etap staged jest płatny i może pozostawić trwały wynik częściowy.
- **Wybór:** właściciel zatwierdził dokładnie jeden świeży run: A1=1 search, A2 maks. 4×1 search/1500 tokenów, B=2200 tokenów, `max_retries=0`, cap 0,55 USD. Bez resume, force i drugiego runu.
- **Wynik decyzji:** A1/A2 sukces, B `max_tokens`/parse-error, koszt 0,170050 USD. Granica zadziałała: proces nie został ponowiony, mimo że cztery VERIFIED czynią B technicznie wznawialnym.
- **Kto podjął:** człowiek; wykonanie i zatrzymanie po pierwszym runie: Codex.

### [2026-07-13] Ucięte B jest terminalne dla auditu, lecz wznawialne dla researchu

- `max_tokens` ma własny typ błędu i nigdy nie jest automatycznie retry'owane.
- Domyślny limit B rośnie z 2200 do 3000, pozostaje jawny w CLI i jest liczony w capie: 0,026250 USD conservative; cały fresh plan 0,516375 < 0,55.
- Porażka kończy `runs=FAILED`, ale zachowuje `research_runs=SOURCES_COMPLETE`; jawny resume robi tylko B i używa CAS.
- Realny run historyczny nie został naprawiony w bazie. Repair oraz resume są dwiema osobnymi decyzjami człowieka.

### [2026-07-13] D-32–D-36: redakcja ma prawo powiedzieć „nie teraz”

- **Wybór:** decyzje ADR-032–036 ustanawiają modularny system redakcyjny, `SKIP`, izolację NIA/build logu, oddzielne metryki follows i subscribers oraz rozdzielenie lokalnych Notes (Etap 3) od publicznych Notes/komentarzy (Etap 6).
- **Granica:** blueprint jest propozycją, nie wdrożeniem. Nie zmieniono promptu stylu, kodu, bazy, migracji ani poziomu autonomii.
- **Dlaczego:** tempo publikacji nie może wymuszać słabej tezy, niezweryfikowanego claimu ani mieszania dwóch odrębnych tożsamości redakcyjnych.
- **Dokument:** `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`.

### [2026-07-13] Korekta D-31: idempotencja nie jest przepustką do innego trybu

- **Problem:** COMPLETE/no-op akceptował identyczny wynik bez uprzedniego sprawdzenia, czy caller podaje ten sam execution mode.
- **Wybór:** mode, marker force i resume CAS są walidowane przed porównaniem payloadu. Terminalne powtórzenie jest legalne tylko dla tego samego trwałego kontraktu.
- **Granica:** nie dodano migracji ani nowej automatyki; P2 dotyczące UNIQUE, multizbiorów i pozostałych długów nie zostały zmienione.

### [2026-07-13] Pełny raport Fable pozostaje źródłem zewnętrznym, nie decyzją implementacyjną

- **Wybór:** pełny raport zapisujemy w jednym miejscu (`docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md`), a blueprint zawiera tylko mapę statusów i etapów.
- **Granica:** [OF]/[TW]/[AN]/[WN] zachowują znaczenie dowodowe; kosztorysy są `COST ESTIMATES — UNVALIDATED`; żadna pozycja nie staje się `IMPLEMENTED` bez kodu lub trwałej konfiguracji.

### [2026-07-13] Korekta D-31: genericzna finalizacja jest legacy-only

- **Problem:** historyczny `finalize_research_success` i jego alias pozwalały wywołać staged finał poza typowanym contextem i atomowym helperem.
- **Wybór:** `single` i `two_stage` zachowują publiczny genericzny finalizer; każdy `staged`, także COMPLETE i FAILED, jest odrzucany przed no-opem i użyciem kosztu. Audyt obejmuje też `finish_run`: staged SUCCESS/DRY_RUN są odrzucone, a legalne FAILED pozostaje dostępne dla obsługi błędów. Wyłącznie `finalize_staged_research_with_card` ma prawo utrwalić kartę, źródła, B SUCCESS, COMPLETE/SUCCESS/USED oraz kanoniczny koszt `model_usage`.
- **Granica:** nie dodano tabeli, migracji, workerów ani automatyki; P2 dotyczące constraintów pozostają bez zmian.

### [2026-07-13] D-37: lease jest prawem do pracy, nie dowodem wykonania

- **Problem:** worker bez trwałego claimu może zdublować zadanie, a wygasły lease browsera nie mówi, czy efekt publiczny już powstał. Niezależne pre-flighty budżetu też nie chronią przed sumą równoległych decyzji.
- **Wybór:** `jobs` dostaje UNIQUE idempotency, partial UNIQUE aktywnego research per account/topic i atomowy claim w `BEGIN IMMEDIATE`. `attempts` liczy udane claimy, a `external_effect_started_at` jest trwałą granicą przed pierwszym skutkiem. Browser/publication-like lub job po tym markerze po expiry zawsze przechodzi do `NEEDS_VERIFICATION`; tylko lokalne/research bez markera mogą wrócić do QUEUED. Rezerwacja liczy `model_usage` plus wszystkie aktywne rezerwacje w tej samej transakcji.
- **Granica:** to storage foundation, nie worker ani Policy runtime. Rezerwacja nie jest wydatkiem; `model_usage` pozostaje kanonem. Brak/uszkodzenie bezpieczeństwa w `system_flags` jest fail-closed.
- **Dowód:** migracja 0009 oraz testy Barrier/reopen dla claimu, idempotency, topic locku, rezerwacji, heartbeat/recovery, completion/recovery i cancel/claim; 463 testy offline, 0 USD.

### [2026-07-13] D-38: worker otrzymuje tylko zamknięty język zadań

- **Problem:** sama trwała kolejka nie mówi, kto i na jakich zasadach wykonuje payload. Dynamiczna nazwa funkcji albo `dry_run=false` w JSON-ie zamieniłyby worker w boczne wejście do API lub browsera.
- **Wybór:** jeden worker używa claimu, lifecycle i heartbeat z repozytorium; dispatcher przyjmuje tylko `LOCAL/ANALYTICS` noop oraz `RESEARCH/RESEARCH` z dokładnym `account_id`, `topic_id`, `dry_run=true`. Każdy job przechodzi runtime PolicyEngine, który odczytuje pięć flag SQLite bez cache. Run researchu wiąże się z jobem przez CAS zaraz po utworzeniu.
- **Granica:** paid i browser/public są bezwarunkowo BLOCKED; brak flagi lub uszkodzony JSON blokują; nie ma dynamicznych importów, API, sieci, resume, reapera runs ani automatycznego retry po niepewnym skutku.
- **Dowód:** 19 testów offline, w tym Barrier/reopen, heartbeat, lost lease, recovery, backoff pustej kolejki i CLI temp DB; pełny suite 489 passed, 0 USD.

### [2026-07-13] D-39: przypięty run po awarii jest sygnałem do zatrzymania

- **Problem:** po crashu między CAS `job.run_id` a terminalizacją job mógł wrócić do QUEUED. Nie tworzył dubla od razu, ale nowy worker nie ma bezpiecznego resume tego samego runu i nie może zaczynać od zera.
- **Wybór:** `attach_job_run` wymaga zgodnej relacji RESEARCH job→run→research_run dla tego samego account/topicu i flow `single`. Po expiry RESEARCH bez `run_id` może wrócić do QUEUED; z przypiętym `run_id` przechodzi do `NEEDS_VERIFICATION`, zachowując run i rezerwację. Terminalny sukces nie jest zgadywany.
- **Granica:** brak realnego resume, reapera runs, API, paid/browser workera i manualnego UI. Reconciliation pozostaje osobnym krokiem.
- **Dowód:** literalna macierz relation/CAS i recovery z reopen oraz dwoma workerami recovery; pełny suite 512 passed, 0 USD.

### [2026-07-13] D-40: reaper kończy audit, nie pracę za workera

- **Problem:** `RUNNING` po crashu był stanem otwartym bez żywego procesu. Zatrzymanie go przed recovery joba mogłoby jednak zostawić job gotowy do działania przy runie już STOPPED.
- **Wybór:** ręczna komenda najpierw robi recovery jobów, następnie atomowo zatrzymuje stale run tylko bez joba `QUEUED`, `LEASED` lub `RUNNING`. RESEARCH z trwałym `run_id` zostaje `NEEDS_VERIFICATION`; reaper może zamknąć audit, ale nie wznawia pipeline’u ani nie zwalnia rezerwacji.
- **Granica:** nie ma cyklicznego schedulera, realnego resume, API, paid/browser workera ani UI reconciliation. `JobRunRelationError` nie wypisuje surowego ID joba do trwałego komunikatu.
- **Dowód:** dwa reapery i terminalizacje konkurują przez plikową SQLite/Barrier/CAS, reaper blokuje się przed recovery wygasłego lease, jest reopen/integrity i CLI temp DB; pełny suite 529 passed, 0 USD.

### [2026-07-13] D-41: heartbeat pilnuje lease, nie wyniku pracy

- **Problem:** checkpoint przed i po synchronicznym dispatchu nie wystarcza, gdy sama praca trwa dłużej niż lease. Wątek heartbeat nie może też współdzielić zwykłego połączenia SQLite workera.
- **Wybór:** na czas dispatchu worker uruchamia niedaemonowy guard z osobnym storage, stop eventem i `join`. Guard wywołuje istniejące `heartbeat_job_lease`; lease 60 s i interwał 20 s są jawne w kompozycji. Foreign/expired owner pozostaje odrzucony przez istniejący CAS.
- **Granica:** utrata lease lub błąd guarda blokuje `DONE`; utrata lease wygrywa z błędem dispatchu. Nie ma retry, nowej migracji, API, paid/browser, realnego resume, cyklicznego reapera ani okien redakcyjnych.
- **Dowód:** 15 testów Event/Barrier bez `sleep`, pełny suite 548 passed, hash `data/agent.db` bez zmiany, koszt 0 USD.

### [2026-07-13] D-41a: bounded lifecycle jest częścią decyzji heartbeat

- **Korekta:** poprzedni wpis opisuje wariant sprzed review P1. Guard działa w osobnym wątku daemon wyłącznie jako osłona procesu. Worker zawsze wykonuje stop event, `wake`, bounded join z timeoutem i kontrolę `is_alive()`. Normalnie wątek kończy się i zostaje dołączony; timeout może pozostawić go żywego do odblokowania infrastruktury, ale blokuje `DONE`. Po odblokowaniu guard widzi stop event przed kolejnym heartbeat.
- **Trwałość:** `lost_lease` i `failure` są in-memory. SQLite oraz recovery/reconciliation rozstrzygają później trwały stan joba.
- **Dowód po korekcie:** 15 pierwotnych testów periodic heartbeat + 11 testów bounded lifecycle/P1 = 26 bezpośrednich testów heartbeat; `test_worker_runtime.py` 59 passed, pełny suite 566 passed, hash `data/agent.db` bez zmiany, koszt 0 USD.

### [2026-07-13] D-42: maintenance sprząta kolejkę, ale nie prowadzi jej

- **Problem:** jednorazowy reaper potrzebował jawnego wywołania. Pętla utrzymaniowa mogłaby łatwo przejąć rolę workera, obejść flagi albo zacząć retry’ować błędy infrastruktury.
- **Wybór:** osobny `MaintenanceRunner` w każdym cyklu otwiera osobne SQLite, bierze jeden czas, wykonuje recovery lease przed stale-run reaperem i kontrolowanie zamyka połączenie. One-shot robi jeden cykl; poll startuje natychmiast, czeka stały interwał po ukończonym cyklu i zatrzymuje się fail-closed przy błędzie. Przy błędzie operacji razem z `close()` zachowany zostaje primary error oraz secondary cleanup error; samo `close()` po udanym przebiegu kończy cykl błędem. Dwa runnery polegają na istniejącym SQLite `BEGIN IMMEDIATE` i CAS, bez globalnego locka.
- **Granica historyczna D-42:** brak claimu, dispatchu, researchu, resume, API, działań paid/browser/public, nowych migracji i cron/service/autostartu. W chwili tej decyzji okna redakcyjne nie były wdrożone; ich późniejszą, odrębną politykę opisuje D-43. Maintenance celowo działa przy worker disabled/safe/kill, bo jest wyłącznie safety cleanup. One-shot i poll są VERIFIED OFFLINE; scheduler systemowy pozostaje NOT_STARTED.
- **Dowód:** 26 testów Event/Barrier/fake waiter/injected clock/temp SQLite, w tym aktywny Event waiter, double failure primary/cleanup, `KeyboardInterrupt` z realnym cleanupem, RESEARCH `run_id`+rezerwacja, flags bez mutacji i close→reopen po wyścigu; pełny suite 592 passed, hash prawdziwej bazy bez zmiany, 0 USD.

### [2026-07-13] D-43: harmonogram jest polityką zapisu, nie zachowaniem workera

- **Problem:** sama kolumna `earliest_run_at` nie mówiła, kto wybiera czas, w jakiej strefie, co dzieje się w DST ani czy przyszły job może zostać przypadkiem przejęty przez workera.
- **Wybór:** czysty `SchedulingPolicy` otrzymuje czas i jawne okna IANA z konfiguracji, bez bazy, sieci i domyślnej strefy systemu. Zwraca UTC `earliest_run_at` oraz jeden kod z krótkiego, zamkniętego słownika. Niepoprawne/nakładające się okna, brak konfiguracji i czas przeszły są odmową. Ambiguous DST wybiera wcześniejszą chwilę, a nieistniejący lokalny start przesuwa się tuż za lukę.
- **Egzekwowanie:** tylko centralny enqueuer buduje nowy job; repozytorium nie przyjmuje dowolnego `schedule_reason`. Ten sam atomowy claim sprawdza `earliest_run_at <= now`, zatem oczekujący job nie dostaje lease ani próby. Idempotency porównuje stabilną intencję wykonawczą, a harmonogram jest niezmiennym wynikiem pierwszego enqueue: retry po zmianie czasu lub polityki zwraca pierwszy job, nie przelicza historii i nie tworzy dubla.
- **Granica:** `enqueue-research` tworzy wyłącznie RESEARCH `dry_run`; nie ma opcji realnej, dispatchu, API, sieci, paid/browser/public workera, systemowego schedulera ani realnego resume. Nie dodano migracji, ponieważ wymagane pola i indeks są w `0009`.
- **Dowód:** 49 testów scheduling obejmuje IANA/DST, persistence/reopen, eligibility, reason, stabilną idempotencję po zmianie czasu/polityki, konflikty intencji, dwa połączenia SQLite z Barrier oraz `Worker.run_once()` dla future/boundary; pełny suite 641 test cases passed, hash prawdziwej bazy bez zmiany, koszt 0 USD.

### [2026-07-13] D-44: komplet execution musi mieć jedną granicę trwałości

- **Problem:** `create_run`, `create_research_run` i `attach_job_run` miały osobne commity. Awaria między nimi pozostawiała aktywny komplet bez `jobs.run_id`, a recovery mogło utworzyć drugi run.
- **Wybór:** jedna operacja `initialize_research_run_for_job` w `BEGIN IMMEDIATE`: walidacja RESEARCH joba, aktywnego statusu, ownera i świeżego lease; następnie INSERT run, INSERT research_run i CAS joba z `run_id IS NULL`. Tylko po wszystkich trzech zmianach następuje commit. Gdy job już ma run_id, adapter waliduje i zwraca istniejący komplet bez nowego INSERT.
- **Granica:** crash przed commitem rollbackuje komplet; crash po commicie nie jest zgadywany z pamięci i prowadzi po reopen do istniejącego kontraktu `NEEDS_VERIFICATION`. Nie ma adopcji sierot, auto-cleanupu, auto-resume, migracji, API ani akcji publicznej.
- **Dowód:** failpointy po INSERT run, przed CAS i po commicie, idempotencja, fencing, dwa połączenia SQLite/Barrier, parity i future boundary; 14 acceptance scenarios, pełny suite 655 passed, 0 USD.
### [2026-07-13] D-45: lease musi ogrodzić skutek, nie tylko wejście

- **Problem:** atomowa inicjalizacja nie zabraniała staremu procesowi późniejszych zapisów usage, kosztu, błędu, karty i terminalnego statusu.
- **Wybór:** `JobExecutionContext` powstaje dopiero z udanego związania job→run. Worker-only mutacje sprawdzają job ID, run ID, ownera, świeży lease, `LEASED|RUNNING`, kind/workflow i relację researchu w tej samej transakcji co zapis. Czas jest próbkowany po uzyskaniu SQLite write locka i normalizowany do UTC.
- **Semantyka odmowy:** `StaleJobExecutionError` kończy pipeline jako utratę lease. Nie zapisuje FAILED „na pocieszenie”, nie retry’uje i oddaje trwałe rozstrzygnięcie recovery. Manualne pipeline’y bez joba pozostają osobną ścieżką.
- **Granica:** offline dry-run = verified. Paid/live i browser/public nadal zablokowane. Realny koszt po utracie lease wymaga przyszłego idempotentnego ledgeru provider request ID.
- **Dowód:** 26 acceptance, old-owner matrix, expiry przed recovery, race dwóch SQLite connections, close→reopen/integrity; full 667, 0 USD.

### [2026-07-13] D-46: czas jest częścią fence, a CSV nie jest kanonem

- **Problem:** timestamp pobrany przed write lockiem mógł przeżyć oczekiwanie dłuższe niż pozostały lease. Dodatkowo błąd pomocniczego appendu `COSTS.csv` po trwałym commicie SQLite mógł uruchomić niewłaściwą ścieżkę failure workera.
- **Wybór:** chronione operacje lifecycle pobierają czas dopiero po `BEGIN IMMEDIATE` przez `Clock`; aktywna granica to `>=`, recovery to `<`. SQLite `model_usage` jest jedyną księgą kosztu; CSV jest best-effort, odtwarzalnym eksportem z kontrolowanym warningiem. Nieoczekiwany wyjątek po inicjalizacji używa jednej fenced transakcji dla `jobs/runs/research_runs=FAILED`.
- **Granica:** bez outboxa, eksportera, retry CSV, migracji, API, działań paid/browser/public lub zmian prawdziwej bazy. Przed Etapem 8 wymagany audyt KEEP/DEPRECATE/REMOVE dla CSV.
- **Dowód:** 7 lifecycle i 5 fenced-write testów lock-wait na file SQLite, race heartbeat↔recovery, CSV success/failure i atomic unexpected failure; 42 acceptance, full 683, 0 USD.

### [2026-07-14] D-47: wynik dispatchu jest prawem do dotknięcia końca historii

- **Problem:** enum zapisany tylko jako adnotacja typu był przepuszczalny dla stringa. Worker rozpoznawał wyłącznie tożsamość enumu, więc po zakończonej już transakcji mógł potraktować zły wynik jak lokalne zadanie i spróbować kolejnego heartbeat. Drugi błąd był bardziej subtelny: `WORKFLOW_FAILED` musi oznaczać ten sam pełny, atomowy koniec co sukces — nie zaproszenie do dodatkowego `fail_job`.
- **Wybór:** `DispatchResult` wymaga jawnego trybu i sprawdza go przy konstrukcji. Worker sprawdza ponownie obiekt i enum, rozgałęzia trzy znane tryby bez domyślnego fallbacku oraz propaguje wadliwy wynik jako błąd kontraktu bez zapisu. Workflow-owning success zwraca DONE, workflow-owning failure zwraca FAILED, a zwykłe domknięcie pozostaje wyłącznie prawem LOCAL.
- **Dodatkowa granica:** karta i każde źródło muszą potwierdzić pojedynczy INSERT przez `rowcount`; brak dowodu jednego rekordu rollbackuje cały sukces. Błąd rollbacku może być tylko przypisem do błędu pierwotnego, nigdy jego zamiennikiem.
- **Dowód:** literalny string był czerwony przed zmianą; po niej 58 restart acceptance i pełny suite 700 passed potwierdzają brak heartbeat/complete/fail/LOST po malformed result, spójny atomic failure i reopen/integrity. Koszt 0 USD, bez API, browsera lub publikacji.

### [2026-07-14] D-49–D-51: jedna zgoda, jeden root i uczciwe zamknięcie

- **Problem:** biblioteka providera mogła powtórzyć request bez nowej zgody, zwykłe CLI mogło złożyć realny adapter, a niepełny cennik mógł przepuścić request z pozornym kosztem zero. Równocześnie test bezpieczeństwa zapisał fake/dry-run artefakty do domyślnej bazy.
- **Wybór:** każdy SDK ma `max_retries=0` i dodatni timeout, normalne rooty są zawsze fake/offline, a jedyny realny root wymaga `--real` oraz pełnych cen. Incydent bazy odtwarzamy logicznie tylko z identyfikowalnych rekordów testowych; nie udajemy odzyskania bitowego snapshotu. Nowy SHA baseline to `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.
- **Decyzja o statusie:** niezależne review zamknęło P0-01, P1-01 i P1-02. WAVE 0A jest **APPROVED WITH P2** i formalnie zamknięta; Etap 1 nadal jest BLOCKED przez inne P1.
- **Backlog:** mocniejszy regression test na granicy `messages.create`, pełna parametryzacja pricingu i poprawna kolejność aktualizacji dokumentacji.

## D-52 — request_id nie jest operation-key (WAVE 0B)

- **Decyzja:** operation-key opisuje intencję operatora i idempotencję enqueue; request_id opisuje pojedynczą próbę dostawcy i jest trwałym `job_id:stage:attempt_no`. Oba nie mogą być losowe ani zależne od czasu.
- **Granica:** rezerwacja maksymalnego kosztu, request state i zapis usage są kontrolowane przez SQLite/fence. Timeout, connection i unknown zatrzymują automatyczne ponowienie; WAVE 1 ma dopiero rozszerzyć tę zasadę na staged flow, real resume i ekran reconciliacji.
- **Status:** `WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; bez API, sieci, browsera, publikacji i zmiany prawdziwej bazy.

## D-053 — Niepewnej historii nie „naprawiamy” przez wymyślenie powiązań

Migracja 0011 egzekwuje request-bound usage dla nowych realnych wywołań. Stare rekordy, dla których nie ma dowodu powiązania z attemptem, dostają jawny znacznik `is_legacy_usage=1`. To mniej wygodne niż fikcyjny foreign key, ale chroni wiarygodność historii. Status decyzji: WAVE 0B.1 candidate complete, oczekuje na niezależny re-review.

## D-059 — kwota jest kontraktem, nie formatowaniem (W0B-REV-10)

- **Decyzja:** wszystkie aktywne obliczenia USD stosują `Decimal(str(value)) → quantize(Decimal("0.000001"), ROUND_HALF_UP)`. Dotyczy to durable intentu, estymatora, `UsageTracker`, projekcji pipeline, rezerwacji, porównań actual/reserved, sum usage i cache kosztu. Składniki są sumowane przed pojedynczą granicą rounding.
- **Powód:** Pythonowy banker's `round` w estimatorze i trackerze był sprzeczny z intentem/storage i mógł rozdzielić estimate, reservation oraz settlement na granicy pół-kwantu.
- **Granica:** nie zmieniono `max_tokens`, retry, lifecycle, attempt #2 ani paid rootu. Przy over-reservation nadal zostaje jeden usage i `NEEDS_RECONCILIATION`, bez SUCCESS lub karty. Usunięto wyłącznie blok legacy fresh providera po return i nieużywaną stałą DB-API.
- **Status:** W0B-REV-09/10 technicznie zamknięte; 887 testów offline to wynik historyczny, 13 migracji. WAVE 0B `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## D-060 — granica kwoty jest po agregacji, nie po komponencie (W0B-RR-01)

- **Decyzja:** `Decimal(str(value))` jest typem wewnętrznym od wejścia kwoty przez raw staged estimate, policy, ledger, pipeline i CLI. Jedno `quantize(Decimal("0.000001"), ROUND_HALF_UP)` następuje dopiero na granicy kontraktu; `float` może być wyłącznie wyjściem zgodności po tej granicy.
- **Powód:** wcześniejszy kontrakt poprawnie opisywał helper, lecz staged mnożył już publicznie zaokrąglony koszt, a kilka decyzji nadal używało float. To mogło rozdzielić wynik `2×`/`3×0.0000005` albo `0.1+0.2` od tego samego limitu.
- **Granica:** bez zmian `max_tokens`, lifecycle, request identity, attempt #2, schematu lub migracji. `actual_cost > reservation` nadal zachowuje jeden usage i ustawia `NEEDS_RECONCILIATION`; real resume nadal odmawia przed klientem.
- **Status:** 894 testy offline, 13 migracji, WAVE 0B `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`; decyzja wymaga krótkiego niezależnego re-review, nie jest zamknięciem fali.

## D-069/070/071 — launcher, kryterium zamknięcia i migracja przez kopię

- **Launcher:** Windows Task Scheduler tylko uruchamia kanoniczne one-shot entrypointy. Systemowy worker ma dodatkowe `--offline-only`; nie ustawia flags i nie może dotrzeć do paid runnera. Rejestracja każdego zadania wymaga osobnej zgody.
- **Kryterium:** techniczna kompletność nie jest formalnym `CLOSED`. Przed zamknięciem pozostają: review pakietu, kontrolowana migracja i baseline, jeden live job/request z capem i `max_retries=0`, review trwałego wyniku, brak MAJOR/CRITICAL i decyzja właściciela.
- **Migracja:** źródło pozostaje nietknięte; pełny backup jest dowodem i jedyną drogą rollbacku. Kandydat musi zachować cost/legacy/integrity, a paid/browser flags pozostają false. Produkcyjna migracja nie została wykonana.
## D-084 — Review techniczne nie jest autoryzacją operacyjną

- **Decyzja:** przyjąć `APPROVE WITH MINOR/P2` dla LA-02 i zamknąć root cause, ale pozostawić drugą próbę controlled-live nieautoryzowaną.
- **P2-2:** nie rozszerzać wyjątku klasyfikatora. Inny terminal/edytor/shell z pełnym tekstem komendy może wywołać bezpieczny false STOP; operator ma zamknąć takie procesy i wykonać standalone check z tego samego launchera.
- **P2-3:** ignorowany jest dokładnie `config/pricing_profiles.yaml`, nie wszystkie `config/*.yaml`.
- **Granica:** checkpoint nie zmienia DB, joba, flag, gate'u, providera ani kosztu. Etap 1 pozostaje `OPEN`.
