# 06 — DECYZJE PROJEKTOWE

## Cel pliku
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
