# DECISIONS (Architecture Decision Log)

## Cel

Rejestr decyzji projektowych i architektonicznych — zwłaszcza tych rozstrzygających rozbieżności między dokumentami. Każda decyzja opisuje kontekst, rozważane opcje, wybór i konsekwencje. To „dlaczego" systemu; „co i kiedy" jest w `BUILD_LOG.md`. Decyzje otwarte (czekające na właściciela) trzymamy w sekcji „Otwarte" i zamykamy po akceptacji.

## Zasady

- Jedna decyzja = jeden wpis z numerem `ADR-XXX`.
- Status: PROPOSED / ACCEPTED / REJECTED / SUPERSEDED (przez ADR-YYY).
- Rozstrzygnięcia rozbieżności między dokumentami zawsze wskazują „źródło prawdy".

## Szablon wpisu

```markdown
### ADR-XXX: Tytuł decyzji
- **Data:** YYYY-MM-DD
- **Status:** PROPOSED | ACCEPTED | REJECTED | SUPERSEDED
- **Czego dotyczyła:** jaki problem / jaka rozbieżność
- **Rozważane opcje:** A) ... B) ... C) ...
- **Decyzja i uzasadnienie:** co wybrano i dlaczego
- **Zalety:** ...
- **Ryzyka:** ...
- **Kto podjął:** Claude | człowiek | wspólnie
- **Zmieniona później:** nie | tak → ADR-YYY (kiedy i dlaczego)
- **Powiązania:** ADR-..., MASTER_ARCHITECTURE.md §..., IMPLEMENTATION_ROADMAP.md Etap ...
```

> Uwaga (2026-07-12, ADR-023): powiązania w historycznych wpisach ADR-001..022 wskazują na dokumenty zarchiwizowane w `docs/archive/superseded_plans/` (IMPLEMENTATION_PLAN.md, ARCHITECTURE.md, SUBSTACK_INTEGRATION.md) — pozostają jako kontekst historyczny; nowe wpisy odwołują się do dokumentów źródła prawdy.

> Wcześniejsze wpisy ADR-001..010 używają skróconej formy (Kontekst/Opcje/Decyzja/Konsekwencje). Nowe wpisy stosują pola powyżej.

---

## Decyzje architektoniczne

### ADR-001: Źródło prawdy dla wag scoringu tematów
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** trzy dokumenty podają różne wagi scoringu tematu (ARCHITECTURE/YAML vs PROJEKT vs MASTER).
- **Opcje:** A) ARCHITECTURE/growth_policy.yaml (25/20/15/15/10/10/5) B) PROJEKT (25/25/20/10/10/10) C) MASTER.
- **Decyzja:** A — spójne z plikiem konfiguracyjnym, który będzie kodem.
- **Konsekwencje:** PROJEKT/MASTER traktowane jako inspiracja; wagi tylko z configu.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.1, załącznik rozbieżności.

### ADR-002: Źródło prawdy dla funkcji celu wzrostu
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** ARCHITECTURE/YAML (45/20/15/10/5/5) vs MASTER (40/20/15/10/10/5 + konwersja).
- **Decyzja:** ARCHITECTURE/growth_policy.yaml.
- **Konsekwencje:** „konwersja profil→subskrypcja" liczona jako metryka pomocnicza oznaczona jako estymacja, nie składnik funkcji celu.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.1, A.9.

### ADR-003: Grafiki SVG-only w MVP
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** MASTER/PROJEKT chcą obrazów „cinematic editorial"; Anthropic-only daje tylko SVG→PNG.
- **Decyzja:** MVP = SVG-only za interfejsem `ImageProvider`; zewnętrzny generator poza MVP.
- **Konsekwencje:** okładki/diagramy zamiast fotorealizmu; brak kosztu grafik w MVP.
- **Powiązania:** IMPLEMENTATION_PLAN.md §A.4, §B.1.

### ADR-004: Docelowy sufit autonomii MVP = LEVEL_2 (z bramkowaniem)
- **Data:** 2026-07-11
- **Status:** ACCEPTED, **doprecyzowana przez ADR-017 (ta sama data, później)** — patrz niżej. Sedno ADR-004 (bezpieczny, stopniowy start) pozostaje w mocy; semantyka „artykuły/komentarze zawsze człowiek" była opisem **fazy startowej**, nie stanu docelowego.
- **Kontekst:** właściciel wybrał celowanie od razu w LEVEL_2 (auto-publikacja wybranych typów Notes). PROJEKT/MASTER nadal wymagają akceptacji KAŻDEGO artykułu i KAŻDEGO komentarza na starcie.
- **Decyzja:** startowy sufit MVP = LEVEL_2 rozumiane wąsko: auto-publikacja tylko wcześniej zatwierdzonych *typów* Notes; artykuły, komentarze, linki, restacki — człowiek **na etapie startowym**. *(Docelowa, szersza semantyka LEVEL_2/LEVEL_3 — patrz ADR-017.)*
- **Bramkowanie (twarde):** auto-publikacja Notes NIE włącza się, dopóki (a) nie działa warstwa przeglądarki (Etap 4), (b) nie ma ≥1 tygodnia stabilnej jakości szkiców, (c) właściciel nie włączy jej jawnym przełącznikiem. Do tego czasu efektywny poziom = LEVEL_1 (dry_run, wszystko za akceptacją).
- **Konsekwencje:** architektura i Policy Engine od początku wspierają LEVEL_2, ale start jest bezpieczny; żaden pierwszy etap nic nie publikuje.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.8, CZĘŚĆ D, ADR-005, **ADR-017**.

### ADR-005: Brak publikacji na Substacku w MVP-0
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** `IMPLEMENTATION_PROMPT.md` zakazuje wdrażania publikacji; DoD §23 zakłada publikację jako cel końcowy.
- **Decyzja:** Etapy 0–3 offline (dry_run), publikacja dopiero od Etapu 4 i tylko po wyraźnej zgodzie właściciela.
- **Konsekwencje:** pierwszy MVP produkuje szkice do akceptacji, nie publikuje.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.11.

### ADR-006: Jedna baza SQLite ze scopingiem po account_id
- **Data:** 2026-07-11
- **Status:** ACCEPTED (zweryfikowane 2026-07-12, Etap 0 / Task 7)
- **Kontekst:** izolacja kont vs prostota raportów.
- **Decyzja:** jedna baza; obowiązkowy `account_id` w StoragePort; testy izolacji.
- **Konsekwencje:** prostsze raporty, ryzyko wycieku między kontami przy błędzie — pokryte testami.
- **Powiązania:** IMPLEMENTATION_PLAN.md §A.6, §B.9, §B.10.

#### Weryfikacja wdrożenia ADR-001/002/003/005/006 — Etap 0 / Task 7

- **ADR-001:** `config/growth_policy.example.yaml` jest kanonem wag 25/20/15/15/10/10/5; `load_settings()` ładuje je do `Settings.topic_scoring_weights`, a workflow tematów używa ich w `compute_weighted_score`. Brak nowszego ADR zmieniającego te wagi.
- **ADR-002:** funkcja celu i wagi 45/20/15/10/5/5 są zapisane w jedynym bieżącym `growth_policy`; analytics/strategy loop jest dopiero Etapem 7 roadmapy, ale nie istnieje konkurencyjne źródło ani nowsza decyzja zmieniająca kontrakt.
- **ADR-003:** bieżący MVP nie ma zewnętrznego generatora rasterowego ani kosztu grafik; decyzja pozostaje ograniczeniem zakresu. `ImageProvider` będzie potrzebny dopiero przy implementacji modułu grafik — jego brak dziś nie oznacza wdrożenia alternatywnej drogi.
- **ADR-005:** brak publikacji jest faktycznie wymuszony (`DisabledBrowser`, zero kodu publikacyjnego i zero publikacji). Historyczne określenie „od Etapu 4” pochodzi sprzed konsolidacji roadmapy; aktualne mapowanie z `IMPLEMENTATION_ROADMAP.md` lokuje właściwą publikację w **Etapie 5**. Zmieniła się numeracja, nie meritum: publikacja dopiero po wcześniejszych bramkach i osobnej zgodzie właściciela.
- **ADR-006:** aplikacja używa jednej bazy SQLite; encje i operacje per-konto są scopowane bezpośrednim `account_id` albo zweryfikowaną relacją przez temat/run. Repozytoria i testy izolacji obejmują topics, research cards, runy, usage i finalizację.
- **Wynik:** wszystkie pięć decyzji pozostaje zgodnych z `MASTER_ARCHITECTURE.md`, `IMPLEMENTATION_ROADMAP.md` i `CURRENT_PROJECT_STATE.md`; żadna nie została zastąpiona nowszym ADR. Nie znaleziono sprzeczności P1.

### ADR-007: Zakres MVP = jedno konto (nothing_is_accidental)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** właściciel: „narazie agent ma działać tylko na koncie tym nowym".
- **Decyzja:** MVP obsługuje wyłącznie `nothing_is_accidental`. `owner_account` i `wife_account` pozostają `active: false`. Architektura wielokontowa zostaje (porty, account_id, izolacja), ale nie jest aktywowana w pierwszym etapie.
- **Konsekwencje:** prostszy, szybszy pierwszy etap; testy izolacji wielokontowej i tak piszemy, by włączenie kolejnych kont było bezpieczne.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.9, §B.11.

### ADR-008: Nisza konta żony = astrologia (nieaktywne w MVP)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** `wife_account.niche` było puste.
- **Decyzja:** nisza = astrologia; konto pozostaje `active: false` do czasu po MVP jednego konta.
- **Konsekwencje:** wartość zapisana na przyszłość; discovery komentarzy dla żony będzie miało punkt startu, gdy konto zostanie włączone.
- **Powiązania:** ADR-007.

### ADR-009: Panel = FastAPI + prosty frontend
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** wybór między Streamlit a FastAPI.
- **Decyzja:** FastAPI + prosty frontend, dostęp tylko przez localhost.
- **Konsekwencje:** więcej pracy na starcie, ale bliżej docelowej architektury i łatwiejsza migracja do chmury / dodanie API akceptacji.
- **Powiązania:** IMPLEMENTATION_PLAN.md §B.2 (`app/ui/`), Etap 3.

### ADR-010: Klucz API — tylko `.gitignore`, bez rotacji teraz
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Kontekst:** realny klucz w `.env`; właściciel wybrał na razie tylko zabezpieczenie repo.
- **Decyzja:** dodać `.gitignore` (z `.env`, `data/`, `config/accounts.yaml`, `config/growth_policy.yaml`) i `.env.example` (placeholdery). Klucza nie rotujemy na tym etapie.
- **Konsekwencje:** repo nie wyeksponuje klucza przy commitcie. **Ryzyko rezydualne pozostaje**, jeśli klucz już gdzieś trafił (kopia pliku, backup) — do rotacji przed pierwszym publicznym udostępnieniem repo. Pozycja utrzymana jako otwarta w ERRORS_AND_FAILURES (R1).
- **Powiązania:** ERRORS_AND_FAILURES.md (R1), Etap 0.

### ADR-011: Integracja z istniejącym kontem Substack (bez tworzenia nowego)
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** sposób podłączenia agenta do konta „Nothing Is Accidental", które już istnieje.
- **Rozważane opcje:** A) utworzyć nowe konto dla agenta; B) połączyć się z istniejącym kontem przez dedykowany profil Playwright po ręcznym logowaniu.
- **Decyzja i uzasadnienie:** B. Konto istnieje (bio: „Explaining the hidden systems, incentives and decisions behind ordinary things.", język EN); nie tworzymy nowego. Integracja przez osobny persistent context Playwright w `data/browser-profiles/nothing_is_accidental/`; logowanie ręczne (magic-link), bez auto-logowania i bez zapisu hasła.
- **Zalety:** brak hasła do przechowania; pełna izolacja sesji; człowiek kontroluje uwierzytelnienie.
- **Ryzyka:** wygaśnięcie sesji, zmiany UI (R2/R3), ToS automatyzacji (R11) — mitygowane stop-conditions i brakiem publikacji na obecnym etapie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** docs/architecture/SUBSTACK_INTEGRATION.md, ADR-005, IMPLEMENTATION_PLAN.md §B.6/§B.9.

### ADR-012: Polityka budżetu — miesięczny limit ma bezwzględny priorytet
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** relacja limitu dziennego i miesięcznego oraz zachowanie po przekroczeniu.
- **Rozważane opcje:** A) obniżyć limit dzienny do ~1.30; B) zostawić 2.00/dzień i 40.00/miesiąc, ale miesięczny nadrzędny.
- **Decyzja i uzasadnienie:** B. Limit dzienny = **2.00 USD**, miesięczny = **40.00 USD**. **Limit miesięczny ma bezwzględny priorytet**: po osiągnięciu 40.00 USD w danym miesiącu wszystkie płatne działania zostają zatrzymane, niezależnie od limitu dziennego. Policy Engine sprawdza `month_to_date` przed każdym płatnym wywołaniem.
- **Zalety:** twardy sufit kosztu miesięcznego; prostota (nie trzeba zaniżać dziennego).
- **Ryzyka:** w skrajnym scenariuszu dzienny sufit pozwala teoretycznie na 60 USD/mies. — dlatego to miesięczny limit jest egzekwowany jako nadrzędny (blokada), a dzienny to dodatkowe ograniczenie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** growth_policy.example.yaml, IMPLEMENTATION_PLAN.md §A.7, app/policies/policy_engine.py.

### ADR-013: Mechanizm dry_run i kolumna model_usage.dry_run
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** jak realizować „jedno wywołanie Anthropic" w trybie dry_run bez wydawania budżetu i bez zależności sieciowej w testach.
- **Rozważane opcje:** A) realne płatne wywołanie API już w walking skeleton; B) w dry_run klient zastępczy (`FakeLLMClient`) bez sieci/kosztu, koszt zapisany jako estymacja oflagowana `dry_run`.
- **Decyzja i uzasadnienie:** B. Interfejs `LLMClient` ma dwie implementacje: `FakeLLMClient` (dry_run, deterministyczny) i `AnthropicLLMClient` (realny, `--real`). Dodano kolumnę `model_usage.dry_run`; budżet (`sum_real_cost_usd`) sumuje tylko wpisy realne. Uzasadnienie: nie wydajemy budżetu bez wyraźnej zgody, testy są offline i deterministyczne, a mechanizm kosztów jest w pełni zademonstrowany.
- **Zalety:** zero kosztu i sieci w MVP-0; realne wywołanie o jeden przełącznik dalej; testy szybkie i powtarzalne.
- **Ryzyka:** estymowany koszt dry_run ≠ realny (świadomie oznaczony jako „szacunek dry_run").
- **Kto podjął:** Claude (zgodnie z zasadą „bez realnych kluczy/kosztów bez zgody" i wobec sformułowania „rzeczywisty lub szacowany koszt").
- **Zmieniona później:** nie.
- **Powiązania:** app/llm/fake_client.py, app/llm/usage_tracker.py, IMPLEMENTATION_PLAN.md §B.4.

### ADR-014: Deduplikacja tematów lokalna (bez płatnego modelu)
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** jak wykrywać duplikaty tematów bez dodatkowego kosztu na każde sprawdzenie.
- **Rozważane opcje:** A) embeddingi/model semantyczny (płatny per temat); B) lokalny deterministyczny: znormalizowany tytuł + Jaccard tokenów + SequenceMatcher, próg z configu.
- **Decyzja i uzasadnienie:** B. Wymóg właściciela: „nie używaj dodatkowego płatnego wywołania, jeśli można lokalnie". Dedup w obrębie `account_id`; duplikat zapisywany jako `status=DUPLICATE` z `duplicate_of` i `rejection_reason` (audyt), a nie jako aktywny rekord.
- **Zalety:** zero kosztu, deterministyczne, testowalne; wykrywa wielkość liter, interpunkcję i parafrazy.
- **Ryzyka:** próg (0.72) to kompromis — bardzo odległe parafrazy mogą umknąć, bardzo bliskie różne tematy mogą się skleić. Konfigurowalny w growth_policy.
- **Kto podjął:** Claude (wg wymagań właściciela).
- **Zmieniona później:** nie.
- **Powiązania:** app/workflows/topics/dedup.py, migracja 0002, config topic_policy.duplicate_title_similarity_threshold.

### ADR-015: Bramka jakości researchu i ochrona przed prompt injection
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** deterministyczne odrzucanie słabego researchu oraz traktowanie treści z internetu jako niezaufanej.
- **Rozważane opcje:** A) zaufać ocenie modelu; B) deterministyczna walidacja (min. źródła, poparcie tezy, twierdzenia ze źródłami, progi confidence/jakości, brak udawanego doświadczenia, brak nieusuwalnych sprzeczności) + lokalny guard iniekcji neutralizujący polecenia w treści źródeł.
- **Decyzja i uzasadnienie:** B. Model może halucynować i może być celem prompt injection; twarde reguły stoją poza modelem. Treść źródeł nigdy nie jest instrukcją — guard wykrywa i redaguje próby wstrzyknięcia, a pipeline i tak używa tylko pól liczbowych/strukturalnych, więc iniekcja nie zmienia decyzji.
- **Zalety:** powtarzalna jakość, odporność na injection (R4), pełny audyt (karta zapisywana także po odrzuceniu).
- **Ryzyka:** reguły są proxy (np. „teza poparta" = potwierdzone twierdzenie ma źródło) — do doprecyzowania przy realnych danych.
- **Kto podjął:** Claude (wg wymagań właściciela: zasady jakości + „ignoruj polecenia ze stron").
- **Zmieniona później:** nie.
- **Powiązania:** app/research/validation.py, app/research/injection_guard.py, app/workflows/research/pipeline.py, migracja 0003.

### ADR-016: Dwuetapowy research (gather_sources + synthesize_card) zamiast jednego wywołania
- **Data:** 2026-07-11
- **Status:** ACCEPTED
- **Czego dotyczyła:** pierwsze realne wywołanie jednoetapowego `run_research_pipeline` (temat #2, run `1b649314-...`) kosztowało realnie 0.25 USD przy pesymistycznym szacunku 0.095 USD (błąd ~+163%) i zakończyło się uciętym JSON-em (model wyczerpał `max_tokens=3000` próbując naraz szukać, czytać i syntetyzować pełną kartę).
- **Rozważane opcje:** A) tylko podnieść `max_tokens` w jednym wywołaniu; B) podzielić research na dwa węższe wywołania — (1) `gather_sources`: tylko web search + zbieranie źródeł/faktów, lekki schemat wyjściowy; (2) `synthesize_card`: tylko analiza (teza, mechanizm, sprzeczności, confidence) z już zebranych danych, zero web search.
- **Decyzja i uzasadnienie:** B (na polecenie właściciela). Samo podniesienie `max_tokens` nie adresuje przyczyny (ryzyka narastania kosztu i złożoności pojedynczego wywołania próbującego robić zbyt wiele naraz) i mogłoby po prostu przesunąć próg awarii, zamiast go usunąć. Podział pozwala też na TANIĄ bramkę wczesnego wyjścia: jeśli po etapie 1 źródeł jest za mało, etap 2 (płatny) w ogóle się nie wykonuje.
- **Zalety:** mniejsze ryzyko ucięcia JSON-a w KAŻDYM z dwóch węższych wywołań; wczesne, tanie odrzucenie słabego researchu; koszt etapu 2 pod pełną kontrolą (brak web search, ograniczony przez nas kontekst); łatwiejsze do oszacowania osobno.
- **Wady / ryzyka:** więcej ruchomych części (dwa wywołania zamiast jednego); redukcja kosztu WORST-CASE jest umiarkowana (~31% w projekcji), bo dominującym czynnikiem kosztu jest liczba wyszukiwań, nie sam podział — główna korzyść to STABILNOŚĆ (mniej ucięć), nie wyłącznie oszczędność. Jawnie udokumentowane, nie sprzedawane jako coś więcej niż jest.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** app/research/cost_estimator.py, app/research/anthropic_client.py (`gather_sources`/`synthesize_card`), app/workflows/research/pipeline.py (`run_two_stage_research_pipeline`), docs/ERRORS_AND_FAILURES.md („Pre-flight cost estimator underestimated the real cost").

### ADR-017: Docelowym trybem projektu jest pełna autonomia operacyjna
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela — doprecyzowanie, nie zwrot)
- **Czego dotyczyła:** audyt wykazał, że dokumentacja (macierz akceptacji `IMPLEMENTATION_PLAN.md §B.8`, semantyka ADR-004, większość `opis-budowy-substack/`) zaczęła sugerować, że ręczna akceptacja KAŻDEJ akcji jest stanem docelowym systemu, a nie fazą startową. Właściciel doprecyzował, że tak nie jest.
- **Rozważane opcje:** A) system docelowo pozostaje asystentem generującym wyłącznie propozycje do ręcznego zatwierdzania; B) system docelowo prowadzi konto w pełni autonomicznie (LEVEL_3), a ręczna akceptacja jest mechanizmem fazy startowej i bramką przy przejściu między poziomami autonomii, nie stałym elementem architektury.
- **Decyzja i uzasadnienie:** B. **„Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta."** Rolę audytowalności na poziomach autonomicznych (LEVEL_2/LEVEL_3) przejmuje deterministyczny scoring + Policy Engine + pełny log każdej decyzji (`autonomous_decisions`), nie ręczny klik człowieka.
- **Zalety:** zgodność z pierwotnym celem eksperymentu („czy agent potrafi SAMODZIELNIE prowadzić publikację" — nie „czy potrafi przygotowywać szkice do zatwierdzenia"); jaśniejsza narracja do serii artykułów; wymusza budowę realnych mechanizmów jakości (scoring, SAFE MODE) zamiast polegania na człowieku jako jedynym filtrze.
- **Ryzyka:** wyższe ryzyko reputacyjne/jakościowe przy przejściu na LEVEL_2/3 (błąd trafia na żywą platformę bez człowieka w pętli) — mitygowane twardymi, mierzalnymi warunkami przejścia (`IMPLEMENTATION_PLAN.md §D.3`) i SAFE MODE (`§D.7`), obie wymagające jawnej zgody właściciela przy KAŻDYM podniesieniu poziomu.
- **Co się NIE zmienia:** brak publicznego ujawnienia automatyzacji jest obowiązkowym założeniem eksperymentu. Informacja o AI pozostaje wyłącznie w prywatnej dokumentacji do czasu osobnej decyzji właściciela — to pozostaje niezmienne na każdym poziomie autonomii; autonomia dotyczy WYKONANIA, nie publicznego ujawniania natury agenta. Zakaz wiadomości prywatnych i inicjowania kontaktu z innymi autorami — pozostaje bezwzględny na każdym poziomie.
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** tak → **ADR-018** (2026-07-11, ta sama data, później) doprecyzowuje punkt „Co się NIE zmienia" powyżej — pierwotna wersja tego ADR błędnie zakładała PUBLICZNE ujawnienie AI; poprawiona treść powyżej już to odzwierciedla.
- **Powiązania:** `IMPLEMENTATION_PLAN.md` CZĘŚĆ D (pełna specyfikacja LEVEL_0-3, warunki przejścia, Autonomous Interaction Engine, scoring komentarzy/subskrypcji, SAFE MODE), doprecyzowuje ADR-004, **doprecyzowana przez ADR-018**.

### ADR-018: Publiczna tożsamość publikacji i brak proaktywnego ujawniania automatyzacji
- **Data:** 2026-07-11
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** ADR-017 błędnie założył, że „publikacja jawnie jako agent AI" pozostaje niezmienna na każdym poziomie autonomii. Właściciel doprecyzował, że to nieporozumienie w drugą stronę — konto publiczne nigdy nie miało proaktywnie ujawniać automatyzacji; to założenie z pierwotnych dokumentów źródłowych (`zalozenia projektu/...`, `zalzoewnia dla agenta/...`) zostaje tym ADR jawnie uchylone dla warstwy publicznej.
- **Rozważane opcje:** A) publikacja jawnie ujawnia AI-autorstwo w bio/materiałach (poprzednie, błędne założenie ADR-017 i dokumentów źródłowych); B) publikacja działa jako anonimowa marka redakcyjna, bez proaktywnego ujawniania automatyzacji, bez podszywania się pod konkretną osobę i bez fikcyjnej biografii; informacja o AI zostaje wyłącznie w prywatnej dokumentacji do osobnej decyzji właściciela.
- **Decyzja i uzasadnienie:** B.

  > Publiczne konto „Nothing Is Accidental" działa jako anonimowa marka redakcyjna bez proaktywnego ujawniania, że prowadzi je agent AI. Informacja o automatyzacji pozostaje w prywatnej dokumentacji projektu do czasu osobnej decyzji właściciela o ujawnieniu eksperymentu.
  >
  > Agent:
  > - nie tworzy fikcyjnej osoby,
  > - nie wymyśla biografii,
  > - nie przypisuje sobie osobistych doświadczeń,
  > - nie udaje konkretnego człowieka,
  > - nie oznacza publicznych treści jako AI-generated,
  > - nie informuje publicznie o eksperymencie.
  >
  > Pytania o tożsamość systemu są ignorowane zgodnie z zasadą **IDENTITY_DISCLOSURE_QUESTION** (pełna specyfikacja: `IMPLEMENTATION_PLAN.md §D.5a`).

  Uzasadnienie: konto ma funkcjonować jak zwyczajna, anonimowa publikacja redakcyjna — nie jak eksponat eksperymentu. Odróżnienie kluczowe: **brak ujawnienia ≠ podszywanie się pod kogoś.** Nie ma fikcyjnego autora, fikcyjnej biografii, fikcyjnych doświadczeń ani fikcyjnego zdjęcia — jest tylko brak deklaracji, kto/co pisze. Analogicznie do wielu anonimowych/zespołowych newsletterów i publikacji redakcyjnych działających bez podpisu personalnego.

- **Powierzchnie i ujawnienie AI:**

  | Powierzchnia | Ujawnienie AI |
  |---|---|
  | `docs/` | TAK |
  | `opis-budowy-substack/` | TAK |
  | prywatne logi | TAK |
  | prywatna baza SQLite | TAK |
  | prywatne raporty kosztów i błędów | TAK |
  | bio Nothing Is Accidental | NIE |
  | About Nothing Is Accidental | NIE |
  | artykuły | NIE |
  | Notes | NIE |
  | komentarze | NIE |
  | odpowiedzi | NIE |
  | restacki | NIE |
  | publiczne grafiki i podpisy | NIE |
  | wiadomości powitalne | NIE |
  | drugie konto właściciela | wyłącznie po osobnej decyzji właściciela |

- **Zalety:** konto funkcjonuje jak zwyczajna, wiarygodna publikacja redakcyjna — nie traci wiarygodności treści, zanim jakość zostanie realnie udowodniona; czystszy eksperyment (mierzy się odbiór treści, nie efekt „ciekawostki o AI"); pełna prywatna dokumentacja i tak zachowuje całą prawdę na potrzeby przyszłej serii artykułów.
- **Ryzyka:**
  1. Bezpośrednie pytanie o naturę konta może zostać różnie odebrane przy braku odpowiedzi — zaadresowane zasadą NO_REPLY (nigdy kłamstwa, tylko brak odpowiedzi w tym wątku, patrz `§D.5a`).
  2. **Otwarte, niezweryfikowane przeze mnie:** aktualne zasady Substacka dot. ujawniania treści AI-generated mogą nakładać własne wymagania, niezależne od tej decyzji. Rekomendacja: właściciel weryfikuje ToS Substacka przed Etapem 4 (realna publikacja) — nie zakładam samodzielnie, że jest to zgodne z regulaminem platformy.
  3. Ryzyko reputacyjne przy ewentualnym późniejszym ujawnieniu — zarządzane tym, że ujawnienie nastąpi świadomie, na warunkach właściciela, z pełną, uczciwą dokumentacją jako dowodem dobrej wiary (nic nie jest ukrywane ZE ZŁEJ WOLI — jest odłożone do właściwego momentu).
- **Kto podjął:** człowiek (właściciel).
- **Zmieniona później:** nie.
- **Powiązania:** doprecyzowuje ADR-017 (punkt „Co się NIE zmienia"), `IMPLEMENTATION_PLAN.md §D.5a` (IDENTITY_DISCLOSURE_QUESTION, pełna specyfikacja), `zalozenia projektu/...` i `zalzoewnia dla agenta/...` (oznaczone SUPERSEDED w części o obowiązkowym publicznym ujawnianiu).

### ADR-019: Trwały zapis etapu 1 (research_sources) — resumability Research Pipeline
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** dwuetapowy research (ADR-016) rozdzielił search od syntezy, ale wyniki etapu 1 (`gather_sources`) żyły tylko w pamięci procesu w trakcie jednego wywołania funkcji. Awaria procesu MIĘDZY etapem 1 a 2 (np. restart, crash, zamknięcie terminala) nadal traciła realnie opłacone wyniki wyszukiwania — dokładnie ten sam problem co przy pierwszym incydencie (2026-07-11), tylko przesunięty o jeden poziom głębiej.
- **Rozważane opcje:** A) zostawić jak jest — dwuetapowy podział wystarczająco redukuje ryzyko; B) zapisywać wyniki etapu 1 trwale do SQLite NATYCHMIAST po sukcesie, zanim zaczniemy etap 2, plus formalny stan maszyny stanów (PENDING/SOURCE_COLLECTED/PARTIAL/COMPLETE/FAILED) i osobna funkcja do wznowienia WYŁĄCZNIE etapu 2 bez ponownego web search.
- **Decyzja i uzasadnienie:** B, na wyraźne polecenie właściciela. Nowe tabele: `research_runs` (stan, rozszerzenie 1:1 istniejącej `runs` — to samo `id`), `research_sources` (trwałe źródła etapu 1), `research_stage_results` (log każdej próby każdego etapu). Świadomie **bez** nowej fizycznej tabeli „research_usage" — koszt per etap już mieści się w istniejącej `model_usage` (`task='research_gather'|'research_synthesize'`, `run_id` wskazuje na `research_runs.id`); osobna tabela dublowałaby księgowanie kosztów zamiast je rozszerzać.
- **Zalety:** żaden realnie opłacony web search nie ginie, niezależnie od tego, na jakim kroku coś pójdzie źle; wznowienie etapu 2 nie kosztuje nic za wyszukiwanie (tylko syntezę); pełny log prób (audytowalność); dwie tanie bramki obronne (za mało źródeł -> odmowa wznowienia bez wołania API; budżet sprawdzany osobno przed wznowieniem).
- **Ryzyka:** więcej tabel/stanu do utrzymania; dualizm statusów (`runs.status` ogólny: RUNNING/FAILED/DRY_RUN vs `research_runs.status` szczegółowy: PARTIAL/SOURCE_COLLECTED/...) wymaga uwagi przy czytaniu logów — udokumentowane wprost w kodzie i tu.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** migracja `app/storage/migrations/0004_research_resumability.sql`, `app/workflows/research/pipeline.py` (`run_two_stage_research_pipeline` — zmiany, `resume_research_stage_b` — nowa funkcja), `tests/test_research_resumability.py` (10 testów), `IMPLEMENTATION_PLAN.md` CZĘŚĆ E.

### ADR-020: Etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis) zamiast jednego wywołania na WSZYSTKIE źródła
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** drugi realny, kontrolowany test dwuetapowego researchu (ADR-016/019, temat #2, run `2a3b4bb9-772e-4340-808a-2bc61b28aacf`) pokazał, że etap 1 (`gather_sources`) — mimo lekkiego schematu i mimo trwałego zapisu (ADR-019) — nadal jest zbyt kruchy: model zwrócił niesparsowalny JSON już przy 4 planowanych źródłach (`Unterminated string... char 2763`). Przyczyna strukturalna: JEDEN JSON obejmujący WSZYSTKIE źródła naraz oznacza, że ucięcie w DOWOLNYM miejscu kasuje WSZYSTKIE źródła razem, nie tylko ostatnie — samo podniesienie `max_tokens` (rekomendacja po incydencie 1) nie usuwa tej strukturalnej wady, tylko przesuwa próg, przy którym się ujawni.
- **Rozważane opcje:** A) tylko podnieść `gather_max_tokens` (1200→wyżej) i zostawić architekturę jednego wywołania na wszystkie źródła; B) rozbić etap „zbierania źródeł" na DWA pod-etapy: A1 (`discover_sources`, TYLKO web search + krótka lista kandydatów URL, JSONL, zero analizy) i A2 (`extract_source`, JEDNO źródło na wywołanie API, zapisywane do bazy NATYCHMIAST po każdym — sukces LUB błąd).
- **Decyzja i uzasadnienie:** B, na wyraźne polecenie właściciela, z jawnym stwierdzeniem „samo podniesienie gather_max_tokens nie jest wystarczającym rozwiązaniem" — potwierdzone przez to, że nowy, mniejszy schemat A1 (same URL-e) nadal teoretycznie mógłby się uciąć przy bardzo długiej liście kandydatów, ALE ucięcie A1 kasuje tylko listę kandydatów (tanie, bez analizy) — nigdy wyekstrahowane dane, bo te powstają WYŁĄCZNIE per-źródło w A2, każde jako osobny, mały, niezależny zapis. To eliminuje strukturalną wadę „jeden ucięty JSON = wszystkie źródła stracone", zamiast tylko oddalać próg ucięcia.
- **Dodatkowe elementy tej decyzji:**
  - **Diagnostyka** (`app/research/diagnostics.py`): każda REALNA odpowiedź modelu (sukces i błąd) zapisywana do prywatnego pliku `data/debug/research/<run_id>/<stage>_raw_response.txt` (run_id, stage, `stop_reason`, tokeny, długość odpowiedzi, surowa treść, miejsce błędu parsowania) — bez tego oba dotychczasowe incydenty ucięcia JSON-a dawały tylko HIPOTEZĘ przyczyny. Cały `data/` jest w `.gitignore`; zero sekretów w plikach (tylko treść odpowiedzi + metadane liczbowe).
  - **`stop_reason` z API** — `_call_anthropic` teraz zwraca też `message.stop_reason` (np. `max_tokens`/`end_turn`), więc przyszłe ucięcia będzie można potwierdzić WPROST, nie domysłem z pozycji znaku błędu.
  - **JSONL zamiast jednego JSON-a dla A1** — kandydaci to jeden obiekt JSON NA LINIĘ; uszkodzona/ucięta linia (najczęściej ostatnia) jest pomijana, zachowując wszystkie poprawne rekordy sprzed niej — zamiast odrzucać całą odpowiedź przy jednym złym rekordzie.
  - **Limity tokenów per wywołanie** (uzasadnienie liczbowe w `IMPLEMENTATION_PLAN.md` CZĘŚĆ F): A1=600 (lista URL-i, była 1200 na PEŁNE fakty wielu źródeł), A2 pierwotnie=500 (JEDNO źródło), B pierwotnie=2200. **Aktualizacja 2026-07-12 po diagnostyce:** produkcyjny default A2 został podniesiony z 500 do **1500**. Jednorazowe `max_tokens=5000` służyło wyłącznie jako sufit diagnostyczny dla kandydata `id=3` i nie jest wartością domyślną. Udana odpowiedź zakończyła się `stop_reason=end_turn` przy 915 output tokens; kandydatów 1 i 2 nie ponowiono, więc nie twierdzimy, że wymagały dokładnie tej samej długości. **Aktualizacja 2026-07-13 (ADR-028):** po realnym ucięciu B przy 2200 produkcyjny default B wynosi 3000 i jest objęty estymatorem/capem.
  - **Nowy estymator kosztu z DWÓCH realnych obserwacji** (nie jednej): incydent 1 (11.07, rekonstrukcja) i incydent 2 (12.07, pomiar wprost) różnią się ~2.3x per-search — estymator POKAZUJE OBA („conservative" sufit z marginesem, oparty na wyższej/starszej obserwacji; „expected" środkowy szacunek z pomiaru wprost, bez marginesu) zamiast jednej liczby, żeby nie powtórzyć błędu „estymacja = przewidywany koszt".
- **Zalety:** awaria źródła N nie ma ŻADNEGO wpływu na źródła 1..N-1 (zapisane niezależnie, natychmiast); wznowienie ekstrakcji kontynuuje dokładnie od pierwszego nieprzetworzonego kandydata (nawet po restarcie procesu); koszt per źródło jest mały, przewidywalny i niezależnie księgowany; diagnostyka pozwala PIERWSZY RAZ potwierdzić przyczynę ucięcia zamiast zgadywać.
- **Ryzyka:** więcej pojedynczych wywołań API (N źródeł = N wywołań zamiast 1) — koszt per-search-fee ($0.01) mnoży się przez liczbę źródeł, częściowo kompensowane bardzo małym `max_output_tokens` per wywołanie; więcej stanów w maszynie stanów (`DISCOVERY_PENDING/COMPLETE`, `EXTRACTION_IN_PROGRESS`, `SOURCES_COMPLETE`, `SYNTHESIS_PENDING` — dodane OBOK istniejących `PARTIAL/COMPLETE/FAILED`, które są świadomie WSPÓLNE dla starego i nowego przepływu); kalibracja estymatora nadal opiera się na n=2, jawnie oznaczone jako przybliżenie.
- **Co NIE zostało zmienione:** stary dwuetapowy przepływ (`run_two_stage_research_pipeline`, `resume_research_stage_b`, ADR-016/019) pozostaje w kodzie, NIEZALECANY, ale w pełni działający i pokryty swoimi 17 testami (nie usuwamy działającego, przetestowanego kodu — supersede, nie usuń, ta sama zasada co przy ADR-017→018). Tabela `research_sources` (migracja 0004) też zostaje nietknięta.
- **Kto podjął:** człowiek (właściciel), wykonanie: Claude.
- **Zmieniona później:** limit B i semantykę truncation/lifecycle doprecyzował ADR-028 po realnym Task 9; podział A1/A2/B pozostaje bez zmian.
- **Powiązania:** `app/research/diagnostics.py` (nowy), `app/research/base.py` (nowe typy: `SourceCandidate`, `DiscoveryResult`, `SourceCardDraft`, `ExtractionResult`), `app/research/anthropic_client.py` (`discover_sources`/`extract_source`/`synthesize_from_cards`), migracja `0005_staged_source_extraction.sql`, `app/workflows/research/pipeline.py` (`run_source_discovery`/`run_source_extraction`/`run_synthesis_from_cards`/`run_staged_research_pipeline`/`resume_staged_research`), `tests/test_staged_research_extraction.py` (12 testów), `IMPLEMENTATION_PLAN.md` CZĘŚĆ F, `ERRORS_AND_FAILURES.md` (oba incydenty 11.07/12.07).

### ADR-021: Prywatne repozytorium GitHub i strategia branchy main/dev
- **Data:** 2026-07-12
- **Status:** ACCEPTED (decyzja właściciela)
- **Czego dotyczyła:** pierwsze objęcie całego projektu kontrolą wersji i bezpieczna publikacja kodu poza komputerem lokalnym.
- **Rozważane opcje:** A) repozytorium publiczne; B) repozytorium prywatne z `main` jako stabilnym punktem odniesienia i osobnym branchem rozwojowym; C) wyłącznie lokalny Git bez GitHub.
- **Decyzja i uzasadnienie:** B. Repozytorium `krapcys1-maker/nothing-is-accidental-agent` jest **PRIVATE**. Pierwszy stabilny snapshot znajduje się na `main`; dalsza praca A2 odbywa się na `dev/a2-stabilization`, bez automatycznego merge do `main`. Publiczność repozytorium jest zakazana bez osobnej przyszłej decyzji właściciela.
- **Zalety:** historia zmian i backup poza komputerem; stabilny `main`; izolacja pracy rozwojowej; ograniczenie dostępu do kodu i prywatnej dokumentacji projektu.
- **Ryzyka:** sama prywatność GitHub nie zastępuje higieny sekretów. Dlatego przed pierwszym commitem rozszerzono `.gitignore`, przeskanowano staged content oraz jawnie zweryfikowano brak `.env`, baz, diagnostyki, profili przeglądarki i danych sesji.
- **Kto podjął:** człowiek (właściciel); wykonanie: Codex.
- **Zmieniona później:** nie.
- **Powiązania:** `.gitignore`, `docs/BUILD_LOG.md` Etap 1N, `docs/ERRORS_AND_FAILURES.md` (pierwsza nieudana próba skanu sekretów).

### ADR-022: Konfiguracja pierwszego świeżego runu nastawionego na kompletną Research Card
- **Data:** 2026-07-12
- **Status:** ACCEPTED / EXECUTED 2026-07-13 — właściciel jawnie zatwierdził dokładnie jeden realny run z capem 0,55 USD
- **Czego dotyczyła:** wybór najmniejszej konfiguracji A1/A2/B, która daje tolerancję jednego błędu A2 i nadal może osiągnąć próg 3 zweryfikowanych źródeł.
- **Rozważane opcje:** A) 3 źródła — najtaniej, ale zero tolerancji błędu; B) 4 źródła — jedna możliwa porażka i nadal 3 źródła do B; C) 5+ źródeł — większa tolerancja kosztem dodatkowych płatnych calli bez obecnego uzasadnienia.
- **Decyzja i uzasadnienie:** proponowane B: świeży `three-stage`, A1 1 search/600 tokens, A2 max 4 źródła × 1 search × 1500 tokens, zero retry, B 2200 tokens/2500 forwarded context, approved cap 0,55 USD. Expected=0,201280 USD; conservative=0,510375 USD. Komenda używa `--topic-id 2`, nie `--resume`, więc nie dotyka istniejącego PARTIAL.
- **Zalety:** jedna awaria A2 nie blokuje automatycznie syntezy; maksymalnie 5 searchy; brak automatycznych ponowień; wszystkie granice jawne w CLI; conservative mieści się w dziennym/miesięcznym budżecie.
- **Ryzyka:** cap jest wyłącznie bramką pre-flight; P0-2c/P1-2/P1-3/P1-4/P1-5 pozostają; B nie ma jeszcze potwierdzenia na żywym API. Search-o-URL nie jest dowodem bezpośredniego odczytu strony.
- **Kto podjął:** Codex przygotował propozycję na podstawie parametrów właściciela; decyzja o realnym wydatku należy do właściciela.
- **Zmieniona później:** wykonana 2026-07-13 bez zmiany parametrów. A1 i 4×A2 zakończyły się sukcesem; B zwróciło ucięty JSON (`stop_reason=max_tokens`) po 2200 tokenach. Koszt 0,170050 USD; brak retry/resume/force; kryterium końca Etapu 0 nie zostało osiągnięte.
- **Powiązania:** `docs/BUILD_LOG.md` Etap 1O, `docs/IMPLEMENTATION_PLAN.md` F.10, audyt P0-2/P1-2..6.

### ADR-023: Konsolidacja dokumentacji architektonicznej do trzech dokumentów źródła prawdy
- **Data:** 2026-07-12
- **Status:** ACCEPTED (na polecenie właściciela — pełny audyt architektury + porządkowanie dokumentów)
- **Czego dotyczyła:** w repo narosły równoległe dokumenty architektury/planów (ARCHITECTURE.md V1, IMPLEMENTATION_PLAN.md CZĘŚCI A–F, audyt 12.07, SUBSTACK_INTEGRATION.md, dwa pierwotne dokumenty założeń) — częściowo sprzeczne (14 rozbieżności kod↔dokumentacja z audytu), co groziło wprowadzeniem kolejnego modelu w błąd.
- **Rozważane opcje:** A) aktualizować wszystkie istniejące dokumenty równolegle; B) jeden zestaw źródła prawdy (`MASTER_ARCHITECTURE.md` + `IMPLEMENTATION_ROADMAP.md` + `CURRENT_PROJECT_STATE.md` w korzeniu) + jedno archiwum `docs/archive/superseded_plans/` z banerem „ARCHIVED — NOT A SOURCE OF TRUTH".
- **Decyzja i uzasadnienie:** B. Wartościowa treść starych dokumentów (model danych, autonomia CZĘŚĆ D, stabilizacja researchu E–F, projekt integracji Substack, findingi audytu P0/P1/P2) została przeniesiona/zmapowana do nowych dokumentów; sprzeczności rozstrzygnięte na rzecz stanu opisanego w MASTER_ARCHITECTURE (zasada: obowiązuje kod tam, gdzie kod był lepszy od specyfikacji). Dzienniki (BUILD_LOG, DECISIONS, ERRORS_AND_FAILURES, HUMAN_INTERVENTIONS, COSTS, RESEARCH_LOG) i kronika `opis-budowy-substack/` NIE są archiwizowane — to logi, nie plany. README dostał sekcję „Source of Truth"; AGENTS.md dostał baner z trzema korektami (nadrzędność GROWTH_MASTER uchylona; jawność AI wg ADR-018; akceptacje wg ADR-017). Odsyłacze w kodzie do przeniesionych plików zaktualizowane do ścieżek archiwum (zero zmian logiki; 102 testy zielone przed i po).
- **Zalety:** jeden obowiązujący obraz architektury/planu/stanu; koniec konkurencyjnych roadmap; następny model zaczyna bez zgadywania.
- **Ryzyka:** historyczne odsyłacze „§B.x" w starych wpisach BUILD_LOG/DECISIONS prowadzą teraz do archiwum — oznaczone w README archiwum jako kontekst historyczny, nie wytyczne.
- **Kto podjął:** człowiek (właściciel) — polecenie audytu i konsolidacji; wykonanie: Claude.
- **Zmieniona później:** nie.
- **Powiązania:** MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md, docs/archive/superseded_plans/README.md, ADR-017/018/020/022.

### ADR-024: Jawne, capowane ponowienie A2 zamiast automatycznego retry
- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres i granice wskazane przez właściciela w Task 3)
- **Czego dotyczyła:** historyczny run `9bbeb020` zawiera nieudane kandydaty A2, lecz status `EXTRACTION_FAILED` nie miał drogi powrotu. Zwykłe resume czytało tylko `PENDING_EXTRACTION`, więc częściowy run mógł pozostać niezamykalny.
- **Rozważane opcje:** A) automatycznie resetować każdy failed podczas resume; B) zwiększać retry klienta przez `--max-retries`; C) zapisywać liczbę rozpoczętych A2 i resetować failed wyłącznie przez osobną, jawną operację z limitem.
- **Decyzja i uzasadnienie:** C, doprecyzowane po niezależnym review. `attempts` oznacza liczbę **atomowo zarezerwowanych/rozpoczętych** prób A2, nie gwarancję dotarcia calla do providera. Jeden warunkowy claim wymaga `PENDING_EXTRACTION` i `attempts < cap`, zwiększa licznik i ustawia `EXTRACTION_IN_PROGRESS`; sukces/błąd przechodzą stamtąd do `EXTRACTED`/`EXTRACTION_FAILED`. Awaria po claimie lub callu zostawia jawny stan niepewny, którego zwykłe resume nie ponawia. Migracja zapisuje historyczne `PENDING=0`, `EXTRACTED=1`, `EXTRACTION_FAILED=1` jako konserwatywną dolną granicę, nie pełną historię. `--retry-failed-candidates` wymaga `--resume`, wybranego zgodnego konta i nie tworzy klienta ani `model_usage`. Domyślny cap `--max-extraction-attempts=2` oznacza pierwszą próbę i najwyżej jedno świadomie uruchomione retry; jest niezależny od technicznego `--max-retries` klienta.
- **PARTIAL_EXHAUSTED:** gdy EXTRACTED < minimum i nie ma legalnego `PENDING`/failed poniżej aktualnego capu, run otrzymuje status terminalny dla zwykłego resume. Tylko jawne `retry-failed-candidates`, uruchomione z wyższym capem, może atomowo zresetować eligible failed i przejść `PARTIAL_EXHAUSTED → PARTIAL`; bez eligible failed status nie zmienia się.
- **Migracja:** od 0007 runner obejmuje jednym `BEGIN IMMEDIATE` DDL/backfill oraz wpis `schema_migrations`; crash lub błąd ledgeru wycofuje oba elementy. Plik 0007 nie otwiera własnej transakcji, starsze migracje zachowują historyczny kontrakt.
- **Zalety:** koszt dodatkowego calla nigdy nie jest ukryty za zwykłym resume; cap jest egzekwowany przy samym claimie; reset i odblokowanie są bezpłatne oraz idempotentne; testy dokumentują backfill, crash-window, konkurencyjny claim, dynamiczny cap, rollback migracji i CLI.
- **Ryzyka:** `EXTRACTION_IN_PROGRESS` celowo wymaga przyszłej, jawnej decyzji recovery; nie wprowadzono automatycznego timeoutowego recovery ani workera. Re-discovery pozostaje osobnym zakresem Etapu 2.
- **Kto podjął:** właściciel zatwierdził granice Task 3; wykonanie: Codex.
- **Zmieniona później:** nie.
- **Powiązania:** migracja `0007_candidate_attempts.sql`, `pipeline.retry_failed_source_candidates`, `scripts/run_capped_research.py`, `tests/test_candidate_attempts.py`.

---

### ADR-025: Ponowny research kompletnej karty tylko po jawnym force

- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres wskazany przez właściciela w Etapie 0 / Task 4)
- **Problem:** drugi świeży research tego samego tematu może ponownie wydać budżet i nadpisać znaczenie cyklu życia tematu, choć kompletna karta już istnieje.
- **Decyzja:** po korekcie niezależnego review kanoniczna finalizacja waliduje, że karta należy do tego samego tematu i konta, a w jednej transakcji zapisuje COMPLETE, terminalny `runs.status` oraz `topics.status=USED`. Każdy świeży flow najpierw sprawdza poprawność trwałej relacji; `USED`/COMPLETE bez poprawnej karty kończy się błędem integralności fail-closed, także z force. Wyłącznie jawne `--force-re-research` zezwala na kolejny poprawny świeży run; nie omija kill switcha, capu, budżetu ani walidacji. Flaga jest niedozwolona z `--resume`.
- **Dlaczego:** wznowienie istniejącego, niepełnego runu jest odzyskiwaniem już rozpoczętej pracy; nowy research kompletnej karty to osobna, potencjalnie płatna decyzja. Nie wolno ukrywać jej jako automatycznego retry.
- **Kto podjął:** właściciel zatwierdził zadanie i granice; wykonanie: Codex.
- **Ryzyko:** force może świadomie utworzyć następną kartę tego samego tematu; audyt pozostaje zachowany przez osobny `research_run` i kartę. Nie uruchamia się automatycznie.
- **Powiązania:** `app/storage/repositories.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`, `tests/test_research_research_guard_cli.py`.

#### Korekta ADR-025 po drugim review

- **Problem:** atomowa pierwsza finalizacja nadal nie była idempotentna. Drugie wywołanie mogło przepiąć ten sam run z karty 1 na kartę 2 i zmienić koszt z 0,1 na 0,9 USD wraz z timestampami.
- **Doprecyzowana decyzja:** wywołujący przekazuje oczekiwany terminalny `runs.status`. Jeśli utrwalony COMPLETE jest identyczny (ten sam run, karta, koszt, terminalny status, semantyka Stage B, poprawne konto i temat, topic USED), funkcja kończy się bez żadnego UPDATE. Każda różnica lub częściowo uszkodzony COMPLETE powoduje `ResearchTopicIntegrityError` i zero mutacji. Pierwsza finalizacja używa warunkowych UPDATE wyłącznie z dozwolonych stanów i sprawdza `rowcount`.
- **Uzasadnienie:** atomowość chroni przed częściowym zapisem jednego wykonania; idempotencja chroni przed zmianą znaczenia już zatwierdzonego zdarzenia podczas powtórzenia. Audytowalny wynik nie może być przepinany po fakcie.
- **Weryfikacja:** plikowa SQLite z reopen; identyczne powtórzenie oraz konflikty karty, kosztu i statusu dla single/two-stage/staged; **206 testów**, koszt 0 USD.

---

### ADR-026: Jedna polityka budżetowa dla pre-flightu i każdej próby researchu

- **Data:** 2026-07-12
- **Status:** ACCEPTED (zakres wskazany przez właściciela w Etapie 0 / Task 5)
- **Problem:** CLI liczyło cap oraz limity D/M niezależnie od biblioteki, a klient mógł ponowić timeout bez nowego odczytu kosztu. Estymata jednej próby nie obejmowała `1 + max_retries`.
- **Decyzja:** kanonem jest `PolicyEngine.check_run_budget(estimated_total, cap, current_run_cost, account)`. `estimated_total` oznacza projekcję całego runu, `current_run_cost` pochodzi z `model_usage`; do globalnej sumy dodawany jest tylko koszt przyszły, bo zapisany usage już w niej jest. Miesięczny limit ma priorytet ADR-012. Workflow przekazuje klientowi callback przed każdą próbą i callback zapisu usage timeoutu przed retry, jeśli usage istnieje. Budget i parse error nie są retry’owane.
- **Estymata:** każdy etap/call liczy `base × (1 + max_retries)`; A2 stosuje mnożnik osobno dla każdego źródła. `max_retries` pozostaje niezależny od `max_extraction_attempts` ADR-024.
- **Odrzucone warianty:** PolicyEngine/SQLite wewnątrz klienta (złe sprzężenie); sama bramka CLI (możliwa do ominięcia); sztuczne usage dla timeoutu bez danych (fałszywa księgowość).
- **Ryzyko:** `timeout-billed-unrecorded` — provider może naliczyć koszt bez zwrócenia usage; rekonsyliacja z billingiem jest poza Task 5.
- **Kto podjął:** właściciel zatwierdził zakres; wykonanie: Codex.
- **Powiązania:** `app/policies/policy_engine.py`, `app/research/cost_estimator.py`, `app/research/anthropic_client.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`, `tests/test_research_run_budget.py`.

#### Korekta ADR-026 po pełnym review

- `run_cap_usd=None` jest dozwolone tylko w dry-run/non-research; realny pipeline odmawia przed utworzeniem runu i callerem.
- Domyślny cap resume jest absolutny (`0.05` legacy, `0.20` staged), nie `prior_cost + allowance`; jawna flaga może świadomie wskazać inny absolutny cap.
- Ownership `research_run.account_id` jest sprawdzane przed `model_usage`, synchronizacją cache, preflightem i klientem.
- NaN/Infinity/ujemne wartości limitów lub sum storage powodują `BUDGET_INVALID_STATE`, nie allow.
- Weryfikacja: timeout+usage+deny attempt 2 osobno dla A1/A2/B, stan B wraca do SOURCES_COMPLETE; 257 testów offline.

### ADR-027: Status zmienia wyłącznie atomowe przejście z jawnego stanu źródłowego

- **Data:** 2026-07-12
- **Status:** ACCEPTED
- **Kontekst:** inwentaryzacja Task 8 wykazała, że część helperów `runs`, `research_runs` i kandydatów źródeł wykonywała `UPDATE ... WHERE id=?` bez sprawdzenia poprzedniego statusu. Równoległy albo spóźniony proces mógł więc cofnąć nowszy stan lub dopisać pola do niedozwolonego przejścia.
- **Decyzja:** każda istniejąca repozytoryjna mutacja statusu zawiera w tym samym UPDATE `status IN (...)`; research dodatkowo warunkuje `flow`. Sukces wymaga `rowcount=1`. Zero wierszy oznacza brak rekordu, konflikt albo niedozwolony stan i daje `LifecycleTransitionError` zawierający encję, ID, cel, dozwolone źródła i aktualny stan. Kanoniczna finalizacja Task 4 zachowuje silniejszy `ResearchTopicIntegrityError`.
- **Atomowość:** dane towarzyszące statusowi są w tej samej transakcji. Niedozwolony Stage A/A1 nie pozostawia źródeł ani kandydatów; testy sprawdzają stan po ponownym otwarciu plikowej SQLite.
- **Idempotencja:** identyczna finalizacja COMPLETE, terminalizacja runu, `mark_extraction_in_progress` i identyczny zapis PARTIAL są no-op. Kolejny jawny resume może zaktualizować `FAILED→FAILED` w `runs` albo błąd `PARTIAL→PARTIAL`; pozostałe powtórzenia terminalne są odrzucane. `PARTIAL_EXHAUSTED→PARTIAL` i `EXTRACTION_FAILED→PENDING_EXTRACTION` istnieją wyłącznie w jawnym kontrakcie retry.
- **Zakres tabel:** `topics.SELECTED→USED` pozostaje wyłącznie częścią `finalize_research_success`; `research_sources` nie mają lifecycle statusu. `content_items`, approvals i interactions nie mają dziś używanych helperów, więc nie dodano logiki przyszłych etapów.
- **Weryfikacja:** 44 literalne testy Task 8 plus regresje Tasks 1–7; race dwóch terminalizacji runu, konkurencyjnego resume i równoległego claimu kandydata na plikowej SQLite; pełne **330 passed** offline. Zero API, realnego researchu, Playwrighta i kosztu.
- **Poza zakresem:** P2-17, P2-18 i P2-19 pozostają bez zmian; nie dodano migracji, workera, lease ani Task 9.
- **Powiązania:** `app/ports/storage.py`, `app/storage/repositories.py`, `tests/test_status_transitions.py`, ADR-024/025/026, MASTER §5.

### ADR-028: Ucięcie syntezy jest terminalną, lecz wznawialną porażką auditu

- **Data:** 2026-07-13
- **Status:** ACCEPTED (kontrakt naprawczy zlecony przez właściciela po pierwszym realnym Task 9)
- **Kontekst:** realny etap B runu `c01171bc-7ff5-4b83-bbfa-c0b164137793` zakończył generację dokładnie przy 2200 tokenach (`stop_reason=max_tokens`), urwał JSON i pozostawił główny `runs=RUNNING`, choć proces już się zakończył. Usage 1904/2200 i koszt zostały zachowane, 4 źródła pozostały VERIFIED.
- **Decyzja:** `stop_reason=max_tokens` jest rozpoznawane przed parserem jako `ResearchTruncatedError`, przenosi usage/model/raw response/stop_reason i nigdy nie uruchamia automatycznego retry. Domyślny, jawny i nadpisywalny limit B wynosi 3000 tokenów; prompt ogranicza długość pól bez usuwania wymaganej treści. Estymator i każda bramka budżetowa używają dokładnie przekazanego limitu.
- **Lifecycle:** po kontrolowanym fresh B failure `runs` przechodzi do `FAILED` z `finished_at`, przyczyną i kanonicznym kosztem z `model_usage`; `research_runs` wraca do `SOURCES_COMPLETE`, karta nie powstaje, topic pozostaje SELECTED. Późniejszy jawny resume wykonuje wyłącznie B i kończy audit przez istniejący `finish_resumed_research_run` z CAS.
- **Pomiar i koszt:** 3000 daje 36% zapasu względem zaobserwowanych 2200. Dla cen ADR-022 B ma expected 0,017500 USD i conservative 0,026250 USD; pełny fresh staged worst-case rośnie do 0,516375 USD i pozostaje poniżej capu 0,55 USD. Dla prior usage 0,170050 USD projected resume wynosi 0,196300 USD, poniżej absolutnego capu 0,20 USD. `max_retries=0` nie dodaje mnożnika.
- **Dane historyczne:** kodu naprawczego nie użyto do mutacji realnej bazy. Run `c01171bc` pozostaje historycznie RUNNING do osobno zatwierdzonej, warunkowej operacji lifecycle; nie wolno naprawiać go surowym SQL ani łączyć repair z płatnym resume.
- **P2-2:** `model_usage` pozostaje jedynym kanonem kosztu. `research_runs.total_cost_usd=0.0` jest znanym cache i nie było naprawiane w tym zadaniu.
- **Weryfikacja:** 174 testy celowane (włącznie z cost ledger, prior usage liczone raz i zachowanie JSONL A1) i 351 pełnego suite, offline; plikowa SQLite z reopen, brak API i koszt dodatkowy 0 USD.
- **Powiązania:** ADR-020/022/026/027, `app/research/base.py`, `app/research/anthropic_client.py`, `app/workflows/research/pipeline.py`, `scripts/run_capped_research.py`.

### ADR-029: Retry Anthropic wyłącznie na podstawie zamkniętej taksonomii błędów

- **Data:** 2026-07-13
- **Status:** ACCEPTED (właściciel wskazał ten kontrakt jako pierwszy blocker infrastrukturalny Etapu 1)
- **Kontekst:** wspólna ścieżka `messages.create` mapowała każdy wyjątek SDK na `ResearchTimeout`. W efekcie błędy trwałe, w tym 400/401/403/404/422, mogły wejść w techniczny retry i spowodować drugi płatny call przed przyszłymi workerami.
- **Decyzja:** domenowy `ResearchProviderError` ma jawne `retryable=False` domyślnie. Typy obejmują timeout, SDK-classified connection/network, rate limit 429, provider 5xx, authentication 401, permission 403, invalid request 400/422, not found 404 oraz unknown. Retry wolno wykonać tylko dla timeoutu, SDK-network, 429 i wybranych 5xx: 500/502/503/504. Inne 5xx oraz każdy błąd nieznany są fail-closed.
- **Błędy treści:** `ResearchParseError`, `ResearchTruncatedError`, validation error i budget denial nie są błędami providera i nigdy nie uruchamiają automatycznego retry. A1/A2/B zachowują konkretny typ wyjątku.
- **Koszt:** każda próba, także retry, zaczyna się od workflow-owned budget callback. Jeśli wyjątek niesie prawdziwe `Usage`, callback retry zapisuje je raz i usuwa z wyjątku; bez usage nie powstaje rekord o koszcie 0. P2-19 (`timeout-billed-unrecorded`) pozostaje otwarte i nie jest naprawiane heurystyką.
- **Trwały audit:** jeden formatter zapisuje etap, nazwę klasy domenowej oraz dostępne `status_code`, `retryable` i `stop_reason` identycznie w `runs.error`, `research_runs.error`, stage logu i candidate error. Mapper SDK tworzy komunikat wyłącznie z kontrolowanej klasy/statusu, nigdy z `str(APIStatusError)` zawierającego body. Formatter nie serializuje `raw_text`, body, cause, obiektu SDK, request/response ani headers i redaguje wzorce sekretów, w tym samodzielne `Bearer <token>`.
- **Granice:** brak fallbacku modelu, backoffu/schedulera, jobów, workerów, lease, migracji i globalnych rezerwacji budżetu. Nie wykonano API.
- **Weryfikacja:** fake SDK i injected callers; literalne 504, 15 kombinacji A1/A2/B×typ, retry/no-retry, budget denial, ledger oraz typed audit po reopen SQLite. Syntetyczny `APIStatusError` z `RAW_RESPONSE_MARKER` nie trafia do żadnego audit field, a warianty `Bearer <token>` są redagowane; **411 passed** offline, koszt 0 USD.
- **Powiązania:** ADR-026/028, MASTER §3.9/3.10/6, `app/research/base.py`, `app/research/anthropic_client.py`.

## Decyzje otwarte (wymagają właściciela)

- **brak** — wszystkie pozycje otwarte z audytu zostały rozstrzygnięte (OPEN-1..5 → ADR-004/007/008/009/010, OPEN-4 → ADR-012).

### ADR-030: Staged B finalizuje kartę i lifecycle w jednej transakcji

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone offline, oczekuje na niezależne review.
- **Problem:** poprzednia ścieżka B commitowała kolejno kartę, źródła, stage result i lifecycle. Awaria między krokami mogła pozostawić kartę bez COMPLETE/SUCCESS/USED.
- **Decyzja:** `StoragePort.finalize_staged_research_with_card` jest jedyną ścieżką sukcesu staged B. W `BEGIN IMMEDIATE` waliduje run–research_run–topic–account, flow/stany, kanoniczny koszt `model_usage`, kandydatów A2 i minimum źródeł; następnie zapisuje kartę, wszystkie źródła, B SUCCESS, COMPLETE, terminalny run i USED. Każdy błąd robi rollback.
- **Idempotencja:** identyczna finalizacja COMPLETE jest no-opem, a różnica payloadu/kosztu/lifecycle jest błędem integralności.
- **Wyjątki jawne:** tylko workflow z `--force-re-research` może finalizować następny run dla USED z wcześniejszą kartą, a tylko jawne resume B może podnieść własny `runs=FAILED`; kontrakt finalizera nie przyjmuje już niezależnych flag, lecz jeden typowany context walidowany ponownie z SQLite.
- **Jakość:** karta REJECT pozostaje kompletnym artefaktem audytowym; minimum VERIFIED blokuje wynik pozytywny, nie utrwalenie uczciwego REJECT po A2 bez realnej weryfikacji.
- **Weryfikacja:** fault injection dla insertu karty, drugiego źródła, B SUCCESS i lifecycle; reopen/integrity_check; no-op i konflikt; dwa połączenia SQLite z `Barrier`; regresje fresh, force i resume B. **446 passed**, 0 USD, brak API.

### ADR-031: Autoryzacja finalizacji staged B jest trwała i typowana

- **Data:** 2026-07-13
- **Status:** ACCEPTED / wdrożone offline, oczekuje na niezależne review.
- **Kontekst:** ADR-030 usunęło częściowy zapis, ale jego dwa luźne parametry mogły rozszerzyć legalny lifecycle przez pamięć procesu. Fresh force po późniejszym B failure nie miał też trwałego śladu, z którego dispatcher resume mógł odtworzyć uprawnienie.
- **Decyzja:** port przyjmuje jeden `StagedFinalizationContext` z trybem `FRESH`, `RESUME_B`, `FORCE_RERESEARCH` albo `FORCE_RERESEARCH_RESUME_B`. `0008_staged_force_reresearch.sql` dodaje `research_runs.is_force_reresearch NOT NULL DEFAULT 0`; historyczne runy nie dostają force retrospektywnie. Resume wymaga snapshotu `runs=FAILED`, `finished_at`, markera błędu, `research_runs=SOURCES_COMPLETE` oraz trwałego B FAILED o tym samym markerze. Repozytorium rewaliduje cały snapshot w SQLite przed B i drugi raz w transakcji po `SYNTHESIS_PENDING`.
- **Preflight i granice:** niemutujący preflight odmawia przed clientem/providerem i usage, gdy mode, konto, topic, flow, wcześniejsza karta, force albo CAS są sprzeczne. Genericzny audit nie może dopisać `B SUCCESS` do flow staged; tylko atomowy helper może to zrobić. Brak UNIQUE dla B SUCCESS/card sources pozostaje P2 wyłącznie dla obecnego modularnego monolitu: helper ma jedyną staged ścieżkę sukcesu, `BEGIN IMMEDIATE` i CAS, a kolejność źródeł jest niedomenowa (porównywana jako multiset). Nie dodano workera, zewnętrznego writer-a ani constraintu dla przyszłej architektury wieloprocesowej.
- **Weryfikacja:** force → B failure → resume odtwarza trwały mode po osobnym połączeniu SQLite; błędny marker lub timestamp snapshotu zatrzymuje preflight przed providerem i bez nowego usage. Pełne 13 fault points po zamknięciu i reopen plikowej SQLite odtwarza dokładnie stan sprzed finalizacji; testy obejmują account/topic/flow/status/VERIFIED, source/topic/cost conflicts, idempotencję bez timestampów, pojedynczy i dwa różne runy równolegle oraz rollback migracji 0008. **446 passed**, brak API i koszt 0 USD.

#### Korekta ADR-031 po końcowym review F4: terminalny no-op waliduje mode

- **Problem:** gałąź istniejącego `COMPLETE` porównywała payload przed walidacją `StagedFinalizationContext`. Przez to identyczny FRESH run mógł zaakceptować `FORCE_RERESEARCH` jako bezmutacyjny no-op.
- **Decyzja:** przed każdym terminalnym no-opem repozytorium waliduje trwały mode: `is_force_reresearch`, dozwoloną semantykę fresh/resume, `research_runs.error` oraz wpis B FAILED z tym samym markerem i snapshotem `finished_at` dla resume. FRESH nie może udawać resume, force nie może udawać fresh, a `COMPLETE` nie jest aliasem omijającym context.
- **Trwałość snapshotu:** wpis B FAILED przy staged failure dostaje timestamp trwałego `runs.finished_at`; nie dodano tabeli ani migracji.
- **Weryfikacja:** FRESH→FRESH i FORCE→FORCE są no-op; FRESH→FORCE, FRESH→RESUME, FORCE→FRESH, FORCE→force-resume bez snapshotu oraz resume z błędnym timestampem/markerem są konfliktami po reopen, bez zmiany rekordów lub timestampów. **449 passed**, 0 USD, brak API.

#### Korekta ADR-031 P1 F4: publiczny finalizer legacy nie ma prawa finalizować staged

- **Problem:** `finalize_research_success` oraz kompatybilny `mark_research_run_complete` nadal przyjmowały `staged/SYNTHESIS_PENDING`. Omijały przez to typed context, walidację kandydatów, atomowy zapis karty i źródeł oraz kanoniczny koszt `model_usage`; dla `COMPLETE` mogły zwrócić legacy no-op.
- **Decyzja:** oba publiczne finalizery są ograniczone do `single` i `two_stage`. Każdy `staged` — `SYNTHESIS_PENDING`, `COMPLETE` lub `FAILED` — dostaje `ResearchTopicIntegrityError` po odczycie relacji, lecz przed no-opem, payloadem, lifecycle i użyciem kosztu. Audyt alternatywnej ścieżki wykazał też, że ogólny `finish_run` mógł wpisać staged `SUCCESS`/`DRY_RUN`; teraz odmawia tych dwóch sukcesów, zachowując legalne ścieżki `FAILED`. Wyłączną publiczną ścieżką staged sukcesu pozostaje `finalize_staged_research_with_card`; tylko ona zapisuje kartę, źródła, B SUCCESS, COMPLETE/SUCCESS/USED i pobiera koszt z kanonicznej sumy `model_usage`.
- **Weryfikacja:** literalne regresje generic i aliasu obejmują arbitralny koszt, identyczną kartę/koszt w COMPLETE oraz FAILED; dwa targety `finish_run` staged też są odrzucone. Po zamknięciu i reopen SQLite snapshot kart, źródeł, auditu B, research_run/run/topic, usage, cache kosztu, timestampów, błędów, card ID i force markera jest identyczny; legacy `single`/`two_stage` oraz ich idempotentny no-op pozostają działające. **454 passed**, 0 USD, brak API.

### ADR-032: Modular Editorial System

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; implementacja PLANNED od Etapu 3).
- **Decyzja:** docelowy system redakcyjny składa się z niezależnych modułów: factual constitution, voice profile, format, Article Brief, diversity memory, fact/style/growth audit i SEO/discovery metadata. Obecny podręcznik stylu pozostaje źródłem do modularizacji, nie pojedynczym docelowym promptem.
- **Granica:** moduły nie uruchamiają modelu, nie zmieniają schematu, nie publikują i nie osłabiają evidence/Policy.
- **Powiązania:** `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`, Etap 3, ADR-017/018.

### ADR-033: Right to SKIP

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; egzekwowanie PLANNED).
- **Decyzja:** harmonogram tworzy kandydatów, nie obowiązek. Negatywna bramka kończy się `SKIP` z reason code; nie jest błędem joba i nie uruchamia automatycznego zastępstwa. Minimalne reason codes: `INSUFFICIENT_EVIDENCE`, `WEAK_THESIS`, `DUPLICATE_ANGLE`, `STYLE_REPETITION`, `REPUTATIONAL_RISK`, `LOW_EDITORIAL_VALUE`, `QUALITY_GATE_REJECTED`.
- **Dlaczego:** cadence nie może omijać jakości ani lineage.
- **Powiązania:** blueprint §6, Etap 3 i Etap 6.

### ADR-034: NIA and Build Log Account Isolation

- **Data:** 2026-07-13
- **Status:** ACCEPTED (decyzja dokumentacyjna; obsługa danych PLANNED).
- **Decyzja:** NIA i publiczny build log mają odrębne `account_id`, voice profiles, diversity memory, strategie i metryki. Materiały techniczne projektu nie trafiają do promptów NIA; transfer między kontami wymaga jawnej decyzji człowieka.
- **Dlaczego:** ochrona anonimowej tożsamości NIA z ADR-018 oraz rozdzielenie celów redakcyjnych.
- **Powiązania:** blueprint §1–2, ADR-017/018.

### ADR-035: Followers and Subscribers Are Separate Metrics

- **Data:** 2026-07-13
- **Status:** ACCEPTED (definicje dokumentacyjne; kolektor i raportowanie PLANNED w Etapie 7).
- **Decyzja:** `followers`, `free_subscribers`, `paid_subscribers` i `engaged_subscribers` są osobnymi metrykami. Follows nie są raportowane jako subskrypcje. Nieobserwowalna atrybucja ma flagę `is_estimated` oraz opis metody i ograniczeń danych.
- **Powiązania:** blueprint §10–11, Etap 7.

### ADR-036: Notes Generation in Stage 3, Public Notes Operations in Stage 6

- **Data:** 2026-07-13
- **Status:** ACCEPTED (podział zakresu; implementacja PLANNED).
- **Decyzja:** Etap 3 tworzy artykuły i Notes lokalnie/dry-run wraz z audytami, metadata i diversity memory, bez publicznej publikacji Notes. Etap 6 wybiera Notes do publikacji oraz realizuje harmonogram, komentarze, odpowiedzi i restacki zgodnie z Policy, antyspamem, `NO_REPLY` i autonomią.
- **Granica:** żadna publiczna akcja nie wynika automatycznie z wygenerowania draftu; metryki i eksperymenty należą do Etapu 7.
- **Powiązania:** blueprint §5 i §12, roadmapa Etapy 3/6/7, ADR-017/018.

#### Integracja pełnego raportu Fable

- **Status:** dokumentacyjna korekta kompletności, nie nowa decyzja wykonawcza.
- **Decyzja dokumentacyjna:** pełny materiał źródłowy Fable jest utrwalony wyłącznie w `docs/research/FABLE_GROWTH_EDITORIAL_REPORT.md`, z oznaczeniami [OF]/[TW]/[AN]/[WN], statusem `NOT IMPLEMENTED` oraz ostrzeżeniem `COST ESTIMATES — UNVALIDATED`. `docs/CONTENT_AND_GROWTH_BLUEPRINT.md` mapuje wszystkie 16 sekcji raportu na Etapy 2/3/6/7 i statusy DECIDED/PROPOSED/PLANNED/DEFERRED.
- **Granica:** nie przyjęto jako faktu danych anegdotycznych ani wniosków Fable; nie zmieniono kodu, polityki, poziomu autonomii ani instrukcji pisania.
