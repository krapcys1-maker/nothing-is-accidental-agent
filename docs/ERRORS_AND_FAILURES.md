# ERRORS_AND_FAILURES

## 2026-08-14 — sufit, którego nie wolno podnieść: przegląd urwany w środku zdania kasuje kartę

- **Objaw:** `content 18` skończył na `REVIEWER_RESPONSE_NOT_JSON`. Reviewer nie odmówił i nie pomylił się merytorycznie — jego odpowiedź po prostu się skończyła w środku obiektu JSON, bo przekroczyła `8192` tokenów wyjścia. Cały opłacony przegląd poszedł do kosza, a wraz z nim karta badawcza za ~0.89 USD, bo `content_frozen_inputs.input_sha256` jest globalnie `UNIQUE` i nie zawiera `job_id`.
- **Dlaczego to nie jest „podnieś limit":** `8192` nie jest ustawieniem. Kwalifikowana deklaracja zdolności brzmi `32000/8192`; zmiana wymaga nowej **płatnej** kwalifikacji roli. Sufit jest twardy z tej samej strony, z której chroni budżet.
- **Prawdziwa zmienna:** wyjście reviewera rośnie z liczbą **segmentów**, a nie ze słowami. Artykuł 48-zdaniowy wrócił cały; artykuł tej samej długości pocięty na 64 zdania — nie. Przez to „krótszy tekst" nie jest zabezpieczeniem: styl krótkich zdań, który ta publikacja lubi, jest dokładnie tym, co przepełnia odpowiedź.
- **Pierwsza naprawa była zapasem, nie lekarstwem.** Przycięcie wymaganych pól wpisu z siedmiu do czterech (segment_id, classification, reason, outcome) dołożyło ~35% zapasu. To przesunęło ścianę, nie usunęło jej — i tak było opisane w handoverze.
- **Zamknięcie (ADR-155):** rozliczenie segmentów dzieli się na kilka płatnych wywołań, po ≤48 segmentów każde. Cały artykuł i cały pakiet dowodów idą w każdym wywołaniu, więc żaden kawałek nie ocenia zdania w oderwaniu od tekstu; werdykt całościowy zamawiany jest tylko raz.
- **Czego to nie naprawia — wprost:** sama utrata karty przy awarii terminalnej. Hasz zamrożonego wejścia nadal nie zawiera `job_id`, więc **każda** inna przyczyna awarii nadal kasuje kartę bezpowrotnie. Ta fala usuwa jedną z przyczyn, a nie skutek.
- **Wniosek ogólny:** limit, który zależy od kształtu treści, a nie od jej rozmiaru, nie da się obejść pisząc „mniej". Trzeba zmienić jednostkę pracy, a nie ilość pracy.
- **Drugi wniosek — cena zabezpieczenia:** dzielenie kosztuje pełne wejście w każdym kawałku. Job, którego cap nie pokrywa całego planu, jest teraz odrzucany **przed** pierwszym wywołaniem. To lepsze niż zapłacić za kawałek 1 i odbić się od budżetu na kawałku 2, ale nadal kończy się utratą karty. Cap dla ARTICLE trzeba dobierać do liczby zdań, nie tylko do liczby prób.
- **Koszt tej naprawy:** `0.00 USD`. Cała weryfikacja offline, na fałszywym transporcie.

## 2026-08-14 — dwa tematy bez karty researchu: cicha arytmetyka, nie awaria

- **Objaw:** tematy 58 i 68 mają opłacone discovery i udane pobrania, ale nie mają ani joba syntezy, ani karty. Nic nie zgłosiło błędu.
- **Przyczyna:** packer nie dzieli dokumentów, a pojedyncza duża strona potrafi sama przekroczyć limit wejścia `23 808` tokenów. Temat 58: trzy udane pobrania, ale trzecie to `48 743` znaki, czyli `24 388` tokenów — nie zmieści się **nigdy**, nawet samo. Zostają dwa źródła, poniżej progu trzech, więc `pack_research_corpus` rzuca `CorpusPackingError`, a `enqueue_evidence_research_if_ready` po cichu zwraca `None`. Temat 68 tak samo (`61 747` znaków, zostaje jedno źródło).
- **Dlaczego to bolało podwójnie:** taka strona nie tylko jest bezużyteczna, ale wcześniej zajęła jeden z sześciu slotów kandydata. Attrycja jest więc większa, niż sugeruje sam odsetek 403.
- **Wniosek ogólny:** próg „trzy źródła" mierzony po pobraniu, a nie po zmieszczeniu się w kopercie, daje fałszywe poczucie zapasu. Sukces pobrania nie jest tym samym co użyteczność.
- **Zamknięcie częściowe (ADR-150):** A1 prosi teraz o 10 kandydatów zamiast 6. To nie usuwa problemu dużych stron, tylko daje mu zapas. Liczenie „użytecznych" zamiast „pobranych" źródeł w pętli fetch zostaje w backlogu.

## 2026-08-14 — handover wskazał niewinną pętlę; usterka była w agregacie

- **Objaw:** reviewer v3 zwrócił `REWRITE_ONCE`, a writer nigdy nie wykonał próby 2. Job skończył `FAILED` / `CONTENT_EVALUATION_BLOCKED` przy `writer_attempts: 1`, przy wykorzystanym budżecie `0.28` z sufitu `2.00` — czyli koszt nie był przyczyną.
- **Błędna diagnoza w handoverze:** oba dokumenty przekazania wskazywały `app/content/pipeline.py` i pętlę `attempt_numbers = (1, 2)` jako miejsce usterki („coś zwiera po próbie 1"). Pętla była poprawna. Nigdy nie dostawała drugiej iteracji, bo job był terminalizowany w środku pierwszej — gałąź `BLOCK` robi `return` przed gałęzią rewrite'u.
- **Rzeczywista przyczyna:** 2 z 26 segmentów i nieudany document review trafiały do jednego wspólnego kubła `NO_OUT_OF_CORPUS_CLAIMS`, ten ustawiał `unsupported_ok=False`, a ewaluacja `UNSUPPORTED_CLAIMS` miała `failure_decision` przypięte na sztywno do `BLOCK`. W `aggregate_decision` `BLOCK` bije `REWRITE_ONCE`, więc werdykt reviewera był nadpisywany.
- **Wniosek ogólny:** dwie władze odpowiadające na to samo pytanie prędzej czy później odpowiedzą inaczej. Reviewer mówił „przepisz", agregat mówił „koniec", a ścieżka REVIEW-ONLY bramkowała się na tej pierwszej odpowiedzi — więc ręczny resume wolno robił to, czego automat odmawiał.
- **Drugi wniosek:** `NO_OUT_OF_CORPUS_CLAIMS` nadal niesie cztery różne rzeczy naraz (realny fail claim review, fail document review, deterministyczną heurystykę pokrycia leksykalnego i rozjazd self-reportu writera). Rozdzielenie ich na osobne bramki zostaje w backlogu — bramka mierząca cztery rzeczy nie potrafi powiedzieć, którą z nich zablokowała.
- **Własna regresja tej naprawy, złapana przed commitem — najważniejsza rzecz w tej fali.** Pierwsza wersja przyznawała rewrite każdej porażce claim-level przy próbie 1. Ale niekompletne claim accounting to dokładnie to, jak wygląda reviewer, który **odmówił, zwrócił nie-JSON albo inny model**. Zmiana zamieniała więc awarię providera w automatyczne drugie płatne wywołanie writera i reviewera — czyli w auto-retry płatnej operacji, czego `AGENTS.md` zabrania wprost, a kontrakt roli wymusza przez `max_retries=0`.
- **Jak to wyszło:** wąski przebieg na sześciu plikach był zielony (360/360) i to wystarczyło, żeby uwierzyć w naprawę. Dopiero pełna suita pokazała `F.F` na 2%: `test_b3_production_reviewer.py::test_C_provider_failure_is_terminal_without_retry` (`reviewer.calls` 1→2) i `::test_E_returned_model_mismatch_is_fail_closed`. Wniosek ogólny: przy zmianie decyzji bramki „testy dotkniętych plików" to zła definicja zakresu — dotknięte jest wszystko, co tę decyzję konsumuje.
- **Zamknięcie:** rewrite wymaga teraz `rewrite_available and verdict.claim_coverage_complete`. Nieczytelna odpowiedź reviewera nie jest opinią redakcyjną i nie kupuje drugiej próby.
- **Koszt tej naprawy:** `0.00 USD`. Zero wywołań płatnych, cała weryfikacja offline. Gdyby regresja przeszła, kosztowałaby realne pieniądze przy każdej awarii providera.

## 2026-08-13 — niezależny review `REJECT`: dwa obejścia reviewera

- **P1-1.** Wspólna quality gate odrzucała sprzeczność „to nie jest fakt, ale zawiera fakt", lecz **początkowa ścieżka REVIEW-ONLY jej nie uruchamia** — decyzję wyprowadzała z samych `outcome`. Kontrpróba: `ARGUMENT_OR_INFERENCE`/`NON_FACTUAL_PROSE` + `contains_external_fact=true` + `evidence_ids=[]` + `PASS` → `APPROVE` i `PENDING_APPROVAL`. Wniosek ogólny: inwariant zapisany w jednym konsumencie nie jest inwariantem systemu.
- **P1-2.** Trigger 0041 sprawdzał *liczbę* checków i `value!=1`. Sześć dowolnych nazw przechodziło, a ponieważ SQLite zwraca JSON `true` jako `1`, literalna liczba `1` też. Wniosek ogólny: w SQLite `json_each.value` nie odróżnia typów — do tego służy `json_each.type`.
- **Przy zamykaniu P1-1 ujawniła się własna regresja poprzedniej fali:** wymóg „grounded fact zawsze cytuje" uniemożliwiał zgłoszenie niepopartego twierdzenia faktycznego. Naprawione: uncited `EVIDENCE_GROUNDED_FACT` jest legalny wyłącznie jako `BLOCK`.
- **Content 5** trafił do `PENDING_APPROVAL` pod kontraktem v2 i **nie może przejść dalej** bez osobno autoryzowanego wycofania i ponownej oceny v3.
- **Dodatkowe kontrpróby persistent boundary przed naprawą:** publiczny ordinary settlement przyjął sprzeczny `APPROVE`; publiczny REVIEW-ONLY settlement przepuścił brak `decision`, null identity/fingerprint, pusty reason, nietekstowe evidence, duplikat/obcy segment i dodatkowe pole dokumentu. Po naprawie oba API odmawiają przed zapisem, a niezależne raw-UPDATE próby zatrzymują triggery.
- **Pierwszy pełny rerun po domknięciu settlementów:** 4 stare testy lifecycle tworzyły syntetyczny `ARTICLE_REVIEWER SUCCESS` bez draftu i z payloadem `b3-test`, więc nowy kontrakt poprawnie odrzucił fixture zanim test dotarł do ogólnej mechaniki lifecycle. Fixture przeniesiono na dozwoloną neutralną rolę `ARTICLE_PLAN`; jego 15/15 oraz finalny full `2771/2771` przechodzą. Walidacji reviewera nie osłabiono.
- **Ostatnia kontrpróba identity:** publiczny ordinary settlement wybierał ścisłą walidację na podstawie roli dostarczonej przez caller, nie z immutable reservation. SQL nadal blokował sprzeczny zapis, ale Python boundary można było ominąć do triggera przez etykietę `ARTICLE_PLAN`. Selekcja używa teraz `row.logical_role`, a exact identity wymaga także zgodności `execution.role`; maskowanie kończy się atomowo `CONTENT_REVIEW_RESULT_IDENTITY_MISMATCH`.
- **Przerwanie narzędziowe:** pierwszy zbiorczy focused run miał limit 60 s i został zakończony przez launcher bez wyniku produktu; identyczny rerun z poprawnym limitem dał 249/249.

## 2026-08-13 — pierwszy realny REVIEW-ONLY: `APPROVE` bez jakości artykułu

- Reviewer zwrócił `APPROVE` przy 29 segmentach `PASS`, mimo że tytuł obiecywał arytmetykę bunchingu, a tekst opisywał wadę metryki. Przyczyna: powierzchnia review obejmowała wyłącznie zdania `body`, więc tytuł nigdy nie był oceniany.
- 18 twierdzeń empirycznych/przyczynowych przeszło jako `ARGUMENT_OR_INFERENCE` (m.in. „almost nobody consults the timetable”, „metryka nie wykrywa bunchingu”, scoring zachęcający do pośpiechu, legal mandates i union rules, utrata przesiadki, headway control zatrzymujący punktualnego operatora). Klasa „inference” nie miała granicy wobec nowych faktów.
- Jeden `ARGUMENT_OR_INFERENCE` niósł `evidence_ids` mimo kontraktu „empty unless grounded”; parser sprawdzał tylko zakres, nie kardynalność — quality gate też nie, choć analogiczny warunek istniał dla `NON_FACTUAL_PROSE`.
- `APPROVE` sprawdzał wyłącznie claim accounting; nie istniała żadna bramka całodokumentowa, więc zgodność tytułu z treścią, realizacja obietnicy i spójność tezy nie były w ogóle pytaniem.
- Naprawa jest kontraktowa, nie punktowa: żaden z tych błędów nie może przejść w kolejnych artykułach. Szczegóły w ADR-147.

## 2026-08-13 — realne timeouty ujawniły brak resolvera dla dwóch ledgerów CONTENT

- Writer v1 trafił do `provider_attempts.NEEDS_RECONCILIATION`, a reviewerzy v4/v5 do terminalnego `role_provider_executions.NEEDS_VERIFICATION`; dotychczasowy resolver WAVE 1 obejmował inny kontrakt i nie potrafił audytowalnie rozstrzygnąć obu tych źródeł bez fikcyjnego actual cost.
- Zagregowany panel kosztów nie mapuje kosztu na v1/v4/v5. Nie wolno z niego wyprowadzać `CHARGED_KNOWN`, `NOT_CHARGED`, usage ani provider request ID.
- Naprawa jest konserwatywna: oddzielny immutable audit zalicza pełną rezerwę do budżetu, pozostawia faktyczny koszt nieznany i nigdy nie ponawia historycznego requestu. Produkcyjnych rekordów nie zmieniono.
- Pierwszy pełny suite po przesunięciu runtime floor na 0040 zakończył się 20 failures: stare testy drabiny kończyły jawne migracje na 0039 albo oczekiwały 39 elementów. Nie był to błąd resolvera. Bez osłabiania asercji doprowadzono te dokładne temp DB do 0040 i zaktualizowano kanoniczne listy; affected rerun przeszedł, a końcowa pełna suita zakończyła się `2652/2652 PASS`.

## 2026-08-13 — pięć MAJOR z niezależnego re-review PR #46

- Opus 5/Sonnet 5 odrzucają legacy `thinking.type=enabled` z `budget_tokens`; aktywny adapter wysyła teraz exact adaptive i osobny effort.
- CLI maskował trwały sukces przez `AttributeError` na trzech nieistniejących polach wyniku; pola są obecnie typowane i wyprowadzane z trwałych draftów/review executions.
- CLI regenerował czas approvala przy każdym invocation, więc resume konfliktował z immutable `approval_json`; autorytetem resume jest teraz istniejący wiersz SQLite.
- Automatyczny research enqueue nadal używał `4096` i arbitralnego `0.250000`; obecnie używa `8192` oraz pełnego capu/rezerwacji 23 808/8 192.
- Najwyższe sekcje dokumentacji konkurowały jako „bieżące” i wskazywały wcześniejszy head/schema. Starsze bloki oznaczono `HISTORYCZNY / SUPERSEDED`, bez przepisywania archiwum.

## 2026-08-13 — regresje ujawnione podczas domykania REVIEW-ONLY

- Pierwszy happy path ujawnił, że ogólny ledger traktował kanoniczny writer attempt 2 jako niedozwolony retry. Wyjątek zawężono do exact attempt 2 z aktywną sesją i trwałym initial `REWRITE_ONCE`.
- Pierwszy pełny suite ujawnił dwie regresje tekstu/kolejności triggerów SQLite. Trigger retry sprawdza teraz najpierw istnienie canonical writer extension, a ogólny komunikat nadal zawiera historyczne `transition command`; rerun zakończył się `2639/2639 PASS`.
- Niejednoznaczny writer i post-reviewer zostały odtworzone offline: oba kończą fail-closed, bez replayu, retry, kolejnego etapu i kosztu udawanego jako zero.

## 2026-08-13 — findings PR #46 naprawione offline przed re-review

- Root cause złego JSON v3 nie był możliwy do ustalenia, ponieważ failure nie zachowywał bezpiecznego response artifact; dodano SHA/rozmiar i bounded redacted text bez sekretów.
- Arbitralne `reason <= 12 słów` mogło unieważnić poprawną, płatną klasyfikację; limit pozostał instrukcją promptu, ale przestał być warunkiem strukturalnym.
- Reviewer używał non-streaming create mimo dwóch zewnętrznych connection failures; nowy stream czeka na final message i nie używa częściowej treści.
- Pierwsza regresja lokalna ujawniła brak thinking/effort dla istniejącego NOTE_WRITER oraz testy zakładające runtime `0038`; kontrakty uzupełniono, a historyczne testy kierują dokładne migracje przez właściwy floor.
- REVIEW-ONLY początkowo polegał na późniejszym quality gate dla fingerprintów/kompletności segmentów; parser graniczny wymusza teraz pełną bijekcję, exact fingerprint i dozwolone evidence IDs również w izolowanym resume.
- Nie wykonano żadnej próby online. Historyczne v1/v4/v5 nadal wymagają zewnętrznej rekonsyliacji i nie zostały zmienione.

## 2026-08-12 — controlled online E2E: bezpieczne failures przed finalnym draftem

- v1: writer przekroczył dawny timeout 30 s; wynik niejednoznaczny, `NEEDS_VERIFICATION`, brak retry.
- v2: output writera zatrzymany na 2048 tokenach i przekroczył starą rezerwę kosztową; usage `11029/2048`, `0.106345 USD`, brak dalszego calla.
- v3: writer zakończony (`11041/2599`, `0.120180 USD`), reviewer zużył `6416/4096`, `0.134480 USD`, lecz odpowiedź nie była wymaganym JSON-em; pipeline `FAILED`.
- v4: writer sukces (`0.107860 USD`), reviewer `APIConnectionError` bez usage/request ID; canonical recovery → `NEEDS_VERIFICATION`.
- v5: writer sukces (`0.121670 USD`), reviewer ponownie `APIConnectionError` mimo timeoutu 300 s; canonical recovery → `NEEDS_VERIFICATION`.
- W żadnej próbie nie było request retry, fallbacku, drugiego reviewera w tym samym jobie ani publikacji. Pierwszy pełny suite ujawnił stare asercje runtime 0034; poprawiono drabiny testowe, po czym rerun failures przeszedł `10/10`.

## 2026-08-12 — WAVE C5: siedem P2 z niezależnego review (ŻADNE nie jest blockerem C5)

> **Klasyfikacja.** Review WAVE C5 zakończył się `APPROVE WITH MINOR/P2` z **zerem blockerów**. Poniższe pozycje są findingami P2 — nie były i nie są blockerami C5. Dwie z nich właściciel wyznaczył jako warunek **przed pierwszym realnym `ARTICLE_RESEARCH`**; pozostałe pięć to zwykły backlog.

**Wymagane przed pierwszym realnym ARTICLE_RESEARCH:**

1. **Estymator 3,5 znaka/token może zaniżać liczbę tokenów dla cyrylicy/CJK.** Stała `CONSERVATIVE_CHARS_PER_TOKEN = 3.5` jest skalibrowana na kompaktowym JSON-ie ASCII (repo dokumentuje pomiar 4,49 znaka/token) i jest jedyną bramką envelope'u w `app/research/corpus_packer.py`. `canonicalize_text` zachowuje każdy znak niekontrolny, więc do korpusu może wejść dowolny Unicode. Pomiar reviewera na dokumentach, które packer **akceptuje** (3 × 25 109 znaków), przy zachowaniu własnej stałej repo 4,49 bajta/token: ASCII `0,78×`, polski z diakrytykami `0,86×` (oba konserwatywne — języki tego konta są bezpieczne), rosyjski `1,41×` (context ~41 731 vs 32 000), chiński `2,19×` (context ~60 304 vs 32 000). **Bariery ograniczające skutek:** osobne L1 dla każdego źródła (człowiek widzi URL przed pobraniem) oraz twardy `cap_usd=1.000000` sprawdzany przed callem — realny worst case CJK (~`0,46 USD`) mieści się pod capem. Prawdziwy tokenizer Claude nie mógł zostać uruchomiony offline (zakaz sieci), więc kwantyfikacja opiera się na ekspansji UTF-8. **Kierunek naprawy:** ograniczać bajty UTF-8, nie znaki.
2. **Wyjątek portu A1 może pozostawić attempt w `REQUEST_STARTED`.** W `app/workflows/research/source_discovery.py` ścieżka model-mismatch jawnie woła `mark_provider_attempt_needs_reconciliation`, ale wyjątek rzucony przez sam `port.discover()` (np. gdy model odpowie bez użycia web search) nie ma odpowiednika — attempt zostaje w `REQUEST_STARTED` i wymaga ręcznej rekoncyliacji. Kierunek jest fail-closed (stan nie jest ukrywany i blokuje dalsze operacje), lecz zachowanie jest niespójne z sąsiednią ścieżką.

**Zwykły backlog (nieblokujący):**

3. **Zakres obsługi wyjątku w corpus enqueue** — w `app/research/corpus_enqueue.py` brak authority/pricingu `ARTICLE_RESEARCH` rzuca `CorpusPackingError` **poza** własnym `try`, już po zacommitowaniu fetchu.
4. **Normalizacja URL-i z domyślnymi portami** — `canonical_source_identity` traktuje `https://x/a` i `https://x:443/a` jako różne tożsamości, więc ten sam zasób mógłby liczyć się jako dwa źródła wobec minimum trzech.
5. **Pozostała część findingu authority pricingowej** — bramka przyjmuje `binding OR plik`. Właściciel zaakceptował to jako prawidłowe (ADR-140); pozostaje wyłącznie uporządkowanie zapisu, nie zmiana zachowania.
6. **Sniffing schematu** — `PRAGMA table_info` decyduje o kształcie insertu capability, a `_role_policy_from_row` czyta nowe kolumny bez guardu. Nieosiągalne przy floor `0034`; ewentualna degradacja byłaby fail-closed.
7. **Float/Decimal oraz brakująca asercja topic reconciliation** — `summary.cost_usd = float(row[0])` używa `float` na pieniądzach wbrew dyscyplinie `Decimal`, a nowy E2E nie asercjonuje `runs.cost_usd == Σ model_usage` dla runu topic generation (reconciliation jest preexistująca i pokryta osobno).

## 2026-08-11 — Sonnet nie może zostać aktywowany dla roli przypisanej do Opusa

- **Objaw:** exact `claude-sonnet-5` jest w katalogu/configu, ale nie istnieje legalna sekwencja prowadząca do ACTIVE dla ARTICLE_RESEARCH bez zmiany polityki.
- **Root cause:** rola jest statycznie mapowana do OPUS, a trwała policy ma `allowed_family=OPUS`. Sonnet daje `ROLE_FAMILY_POLICY_INVALID` / `FAMILY_NOT_ALLOWED`.
- **Drugi brak:** brak production qualification caller/root dla Sonneta i brak jego trwałego registry/approval history.
- **Reakcja:** canary nie został wykonany, bo nawet PASS nie spełniłby następnego gate. Nie zmieniono kodu/policy i nie podstawiono Opusa. Koszt oraz external effects `0`.

## 2026-08-11 — Authoritative research zatrzymany przez brak ARTICLE_RESEARCH authority

- **Objaw:** Writer i Reviewer są ACTIVE/PASS, ale faktycznie wymagany research root ma osobną rolę `ARTICLE_RESEARCH` bez activation. Policy tej roli pozostaje `UNVERIFIED` i wymaga kwalifikacji.
- **Dokładna granica:** `freeze_model_for_intent` zwraca `ACTIVE_MODEL_MISSING`; dispatcher mapuje to na brak eligible active model authority przed konstrukcją klienta i API.
- **Druga odmowa:** temat #1 ma status `USED`; aktualny fresh durable force re-research jest legalny tylko z evidence input. Bez `--evidence-retrieval-id` skrypt zwraca `INVALID_CONFIGURATION`, a topic #1 nie ma właściwego retrieval/corpusu.
- **Reakcja:** nie tworzono joba ani approvalu „na próbę”, nie aktywowano roli ręcznie i nie uruchomiono innego tematu. Koszt i skutki zewnętrzne `0`.

## 2026-08-11 — C5 zatrzymany: żadna karta PROCEED nie ma authoritative lineage

- **Objaw:** karty #1 i #5 mają `publication_recommendation=PROCEED`, lecz content snapshot odmawia `CONTENT_EVIDENCE_INCOMPLETE` dla odpowiednio 2 i 5 confirmed claims; `evidence_source_lineage` ma 0 wierszy.
- **Znaczenie:** istniejące legacy `sources` nie są równoważne z fingerprintowanym lineage wymaganym przez aktualny C5. Nie wolno było ręcznie dopisać braków ani uruchomić nowego researchu.
- **Skutek:** operacja zatrzymana przed approvalem i providerem. Zero API, retry, fallbacku, kosztu i publikacji.
- **Próby operatorskie:** pierwszy immutable audit użył historycznej, nieistniejącej kolumny `schema_migrations.name` i został powtórzony poprawnie bez zapisu. Odczyt SQLite pozostawił pusty WAL i SHM; po kanonicznym potwierdzeniu braku uchwytów usunięto wyłącznie te sidecary, a ponowny quiescence PASS potwierdził brak WAL/SHM/journal. Pierwszy formatter diagnostyki błędnie odwołał się do `ContentSnapshotError.detail`; poprawiony odczyt użył `str(exc)` i nie mutował bazy.

## 2026-08-11 — Reviewer pominięty przez globalny ledger

- **Objaw:** flow z dwoma writerami i reviewerami rozliczał ARTICLE cap jako `0.081000 USD`, lecz `model_usage` i `runs.cost_usd` zawierały tylko writerów (`0.052000 USD`).
- **Root cause:** `settle_role_provider_execution` kończył zapis na osobnej tabeli, podczas gdy globalne bramki korzystały z `model_usage`.
- **Naprawa:** atomowy terminal + exact `model_usage`, globalne role reservations i migracja `0033` z integralnością/immutability.
- **Nieudane próby:** pierwszy focused run ujawnił fixture kończący migracje na `0032`; po dodaniu kroku `0032→0033` wyszedł zbyt silny warunek `jobs.run_id` dla legacy LOCAL fixture. Relację oparto na już egzekwowanym role execution/content lineage. Kolejne runy są zielone.
- **Walidacja pełna:** pierwsza próba full została przerwana przez techniczny timeout narzędzia `120 s` (`exit 124`), bez wyniku pytest. Powtórzony full z prawidłowym limitem ujawnił 21 mechanicznych oczekiwań starego headu/countu `0032/32`; po aktualizacji testów drabiny affected `354/354` i finalny full `2588/2588` są zielone.
- **Koszt/skutki:** `0.000000 USD`, wyłącznie temp DB i fake caller; produkcja nietknięta.

## 2026-08-11 — P2-1: jedyny full ujawnił 15 braków fixture authority

- Pierwszy affected run ujawnił dwa test-only problemy: subprocess nie zasiewał TOPIC_GENERATION authority, a syntetyczne referencje OPUS dla różnych providerów kolidowały. Referencje fake providerów rozdzielono, a subprocess dostał exact local authority.
- Jedyny pełny `pytest -q` (`627.2 s`) zakończył się `15 failed`. Trzynaście failure’ów pochodziło ze starych real-path fixture’ów, które po nowym fail-closed kontrakcie nie miały aktywnego ARTICLE_RESEARCH/TOPIC_GENERATION binding authority. Dwa pozostałe fake SDK response’y nie zwracały model ID/provenance lub używały starego założenia o lazy SDK construction.
- Nie osłabiono produkcyjnej bramki. Każdy fixture otrzymał jawny lokalny `ANTHROPIC` model/policy/qualification/activation albo pełny fake response. Po poprawce sześć dokładnie ujawnionych modułów przeszło `165/165`.
- Full nie został powtórzony, ponieważ właściciel wymagał dokładnie jednego pełnego przebiegu. Dlatego nie wolno przekształcić zielonych testów celowanych w twierdzenie o zielonym fullu; acceptance pozostaje jawnie zablokowane.

## 2026-08-11 — PRE-LIVE CONTENT UNBLOCK: próby, które nie były dowodem

- Najważniejsza samokontrola obaliła własne rozwiązanie B3. Lexical overlap może uznać zdanie za grounded po kilku wspólnych konceptach, nawet gdy końcówka dodaje nowy zewnętrzny fakt. To dokładnie trust boundary z ADR-123. `DeterministicClaimAccountingReviewer` usunięto; nie wolno było zamienić zielonych testów w fałszywą deklarację semantyki.
- Próba bezpośredniego użycia istniejącego `ARTICLE_REVIEWER` seamu także nie jest gotowym rozwiązaniem: `role_provider_executions` zapisuje terminalny rekord po callerze, ale nie ma durable `IN_FLIGHT` przed external effect. Crash w tym oknie pozwoliłby na replay i utratę kosztu. Zgłoszono to jako konkretny blocker zamiast dodawać surowy transport.

- Pierwszy integracyjny harness użył `Settings.model_copy`, choć fixture nie udostępniała takiego API; zastąpiono go `dataclasses.replace`. Inna wersja fixture zostawiła otwartą transakcję po ręcznym UPDATE i zderzyła się z kolejnym `BEGIN`; zapis testowy jawnie zatwierdzono przed startem pipeline.
- Pierwszy deterministyczny reviewer blokował trzy standardowe zdania fake draftu. Nie poluzowano quality gate globalnie: doprecyzowano jawne markery inferencji bez liczby/source appeal/proof assertion i dopisano instrukcję promptu, aby fakt pozostawał blisko nazwanego frozen evidence.
- Pierwszy test kolejności researchu użył nielegalnego `schedule_reason=PRE_LIVE_CONTENT_FLOW_CHECK`; storage poprawnie odmówił. Test powtórzono z istniejącym kontrolowanym kodem `WITHIN_EDITORIAL_WINDOW`.
- Pierwszy szeroki run ujawnił, że pamięć liczy pusty, niedokończony `content_item` jako wcześniejszy artykuł i że reviewer trafił również do offline Note. Pamięć contentu ograniczono do realnego body/draft, a produkcyjny reviewer do paid ARTICLE; stare kontrakty wróciły do zieleni.
- Pierwszy launcher większej suity miał limit 1 s, więc został przerwany i wygenerował wtórny `OSError` stdout. Wyniku nie przyjęto; powtórka z właściwym limitem przeszła.
- Pierwszy pełny suite zakończył się 1 failure po 649 s: novelty potraktowała bezpłatny `CONTROLLED_FETCH` jako real research tylko dlatego, że `dry_run=false`. Root cause naprawiono przez exact warunek `execution=durable_provider_v2`; test regresyjny + właściwy paid research przeszły 2/2, affected 473/473, a finalny full 2546/2546.
- Żadna nieudana próba nie wykonała sieci, API, browsera, publikacji, zapisu produkcyjnej DB ani operacji Git. Koszt wszystkich prób: `0.000000 USD`.

## 2026-08-10 — regresja po podniesieniu runtime schema do 0031

- **Pierwszy pełny przebieg:** 25 testów nie przeszło. Przyczyny były testowe: historyczne fixture Fable próbowały działać pod nową policy Opus, a stare asercje kończyły drabinę na 0030/30.
- **Naprawa:** historyczne kontrpróby Fable uruchamiają wyłącznie temp schema 0030; bieżące Opus flow używa 0031. Oczekiwania drabiny rozszerzono o jawny krok 0031. Nie poluzowano żadnego production gate.
- **Dodatkowa korekta:** wspólny Opus registry jest kwalifikowany raz z największą kopertą ARTICLE_WRITER, a następnie używany przez trzy role; zapobiega to zastąpieniu capability mniejszą kopertą reviewer’a.
- **Wpływ:** zero zapisów do produkcji, zero calli i kosztu. Historyczny Fable refusal pozostał nietknięty.

## 2026-08-10 — Fable odrzucił jednorazowy prompt kwalifikacyjny

- **Co się stało:** jedyny owner-authorized request `claude-fable-5` wrócił z `stop_reason=refusal`; returned model i provenance były zgodne, ale deterministyczny kontrakt słusznie nie uznał odpowiedzi za PASS.
- **Trwały wynik:** `FAIL / PROVIDER_REFUSAL`, usage `151 input / 3 output`, koszt `0.001660 USD`; approval skonsumowany, run i qualification result zapisane.
- **Bezpieczne zachowanie:** zero retry i fallbacku, zero drugiego requestu, capability i activation nie powstały, registry pozostał `CANDIDATE`, policy pozostała `UNVERIFIED`.
- **Wniosek:** transport i durable lifecycle zadziałały, ale model nie przeszedł kwalifikacji. To wynik operacyjny, nie awaria do automatycznego naprawiania ani podstawa do ponowienia bez nowej decyzji właściciela.

## 2026-08-10 — Nieobsługiwany `Copy-Item -NoClobber` przed produkcyjną migracją

- **Co nie zadziałało:** pierwsza próba utworzenia kopii bezpieczeństwa użyła parametru PowerShell `Copy-Item -NoClobber`, którego lokalna wersja cmdletu nie obsługuje.
- **Wpływ:** parser/binder zatrzymał polecenie przed utworzeniem pliku; produkcyjna baza nie została zmieniona, migracja nie rozpoczęła się.
- **Bezpieczne rozwiązanie:** utworzono nowy, unikalny target przez `.NET File.Copy(source, destination, overwrite:false)`, a następnie potwierdzono identyczny SHA i size. Nie nadpisano żadnego pliku.
- **Dalszy przebieg:** wszystkie 10 właściwych kroków migracji zakończyło się exit `0`; nie było retry ani częściowej awarii migracji.

## 2026-08-10 — Nieatomowy fallback migracji 0026/0027

- **Finding blokujący rehearsal:** happy path `0020→0030` działał, ale analiza runnera ujawniła, że `0026` i `0027` trafiają do fallbacku `executescript → osobny ledger insert → commit`. Awaria po zmianie schema mogła pozostawić head o jeden krok wstecz.
- **Root cause:** brak obu wersji w `_RUNNER_TRANSACTIONAL_MIGRATIONS`; ich SQL nie miał własnej transakcji ani self-ledgeringu.
- **Naprawa:** istniejący runner obejmuje teraz SQL i ledger jedną transakcją. Dwa failpointy potwierdziły pełny rollback, jednoznaczny reopen i skuteczny retry; świeży rehearsal zakończył się bez mismatchów.
- **Nieudane próby diagnostyczne:** pierwsza komenda PRE miała błąd parsera PowerShell spowodowany pustym elementem pipeline; późniejsza pomocnicza sonda nazw migracji miała błędne cudzysłowy wokół wyrażenia `rg`. W obu przypadkach parser zatrzymał komendę przed wykonaniem, więc nie powstał zapis ani dowód. Poprawione odczyty zastąpiły je w weryfikacji.
- **Pozostawione jawnie:** pełna suita nie została uruchomiona; P2-1…P2-6 i P2-DOC nie zostały naprawione w tej fali.

## Formalny wynik WAVE 1A po naprawach — 2026-07-16

- **Stan implementera:** po `W1A-R4-01` zadeklarowano `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`.
- **Niezależny finalny re-review:** odtworzył 1036/1036 i cztery partycje exact-once, potwierdził `compileall`/`git diff --check`, wykonał 149/149 własnych kontrprób `Worker.run_once`, 36/36 SQLite floor i 30/30 recovery/reaper/crash-window; zero osiągalnych MAJOR/CRITICAL. Werdykt: `APPROVE WITH MINOR/P2`.
- **Decyzja właściciela:** WAVE 1A formalnie `CLOSED — APPROVED WITH P2`. P2-1 i P2-2 pozostają jawne i nieblokujące. Etap 1 nadal `BLOCKED`, live API nadal `ZABRONIONE`.
- **Chronologia:** poniższe wpisy `REJECTED — MAJOR`, statusy kandydackie i baseline’y 894/980/982/1007 opisują wcześniejsze momenty procesu i pozostają historycznym rejestrem błędów, nie bieżącym statusem projektu.

## 2026-07-16 — WAVE 1A: CZWARTE niezależne review = `REJECTED — MAJOR` (`W1A-R4-01`) — worker omijał reconciliation

- **Kategoria:** SAFETY / failure-boundary completeness / budget integrity (MAJOR BLOCKING).
- **Kontrpróba reviewera:** prawdziwy `Worker.run_once`, przypięty research i lokalny `sqlite3.OperationalError` po `REQUEST_STARTED` kończyły job jako `FAILED`, pozostawiając attempt w `REQUEST_STARTED`. Taki attempt nie był widoczny w kolejce L1 ani rozstrzygalny przez resolver, zachowywał rezerwację i blokował budżet. Recovery nie pomagało, dopóki lease był żywy.
- **Root cause:** workerowy fallback wywoływał `fail_job_research_execution`, który terminalizował job/run/research_run bez odczytania aktywnego provider attemptu. Ochrona crash-window w recovery nie obejmowała lokalnej awarii obsłużonej przed utratą lease.
- **Naprawa:** jedna operacja `StoragePort.fail_or_escalate_job_research_execution` w `BEGIN IMMEDIATE` podejmuje decyzję na podstawie durable attemptu. Brak aktywnego attemptu zachowuje zwykłe `FAILED`; `RESERVED` i `REQUEST_STARTED` przechodzą do `NEEDS_RECONCILIATION` z rozłącznymi powodami, jednym eventem `AUTO_ESCALATION`, jobem `NEEDS_VERIFICATION` i zachowaną rezerwacją; ponowienie na `NEEDS_RECONCILIATION` jest idempotentne. Worker, pipeline, kontrolowana niepewność, błąd mark-reconciliation i heartbeat po granicy korzystają z tej samej operacji. Triggery SQLite blokują terminalne job/run/research_run przy `RESERVED`/`REQUEST_STARTED`.
- **Nieudana próba podczas walidacji:** pierwsze uruchomienie partycji ujawniło starsze testy, które oczekiwały, że surowy terminalny `UPDATE` przejdzie do słabszej walidacji lineage. Po dodaniu mocniejszej bariery SQLite właściwym kontraktem stał się wcześniejszy `IntegrityError` i pełny rollback. Testów nie usunięto ani nie osłabiono; zaktualizowano je, by wymagały silniejszego inwariantu.
- **Nieudana próba własnego harnessu:** pierwsza rozszerzona kontrpróba worker↔maintenance uruchomiła `Worker.run_once` w innym wątku na obiekcie storage utworzonym w wątku głównym. SQLite zgodnie z thread confinement nie dopuścił Workera do granicy, więc nieetykietowana asercja upadła; próba diagnostyczna dodatkowo pozostawiła chwilowo otwarty plik temp i cleanup zgłosił `WinError 32`. To był błąd harnessu, nie dowód poprawności ani defekt produktu. Katalog został jawnie zweryfikowany i usunięty. Poprawiony harness otwiera osobne połączenie w wątku Workera; wtedy Worker i recovery zbiegły do jednego `NEEDS_RECONCILIATION`, jednego eventu i jednego attemptu.
- **Granice:** P2-1 pozostaje fail-closed — normalization nie naprawia ani nie zatwierdza niespójnego fingerprintu, a resolver nadal odmawia. P2-2 bez nadmiernej deklaracji: StoragePort wykonuje resolver atomowo w jednej transakcji; SQLite wymusza spójny trwały stan końcowy; SQLite nie udowadnia pochodzenia wszystkich danych wobec arbitralnego uprzywilejowanego autora wielu tabel.
- **Dowód:** +29 testów (`1007 → 1036`), suite 1036/1036, partycje exact-once 248+253+267+268, 38 testów concurrency/race ×30, siedem plików krytycznych ×10, QA lineage ×10 bez wycieków oraz nowy E2E `Worker.run_once` w 10 świeżych procesach. Zero provider calli, sieci, API, browsera, publikacji i kosztu; chroniona baza niezmieniona. Status: `WAVE 1A — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; WAVE otwarta, Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## 2026-07-16 — WAVE 1A: TRZECIE niezależne review = `REJECTED — MAJOR` (W1A-AUD-04 przeklasyfikowany + dwa nowe MAJOR SQLite) — naprawione w jednej fali

- **Kategoria:** SAFETY / recovery completeness / durable-ledger integrity (MAJOR ×3).
- **W1A-AUD-04 (MAJOR BLOCKING, wcześniej P2):** po crashu i wygaśnięciu lease trwałe `RESERVED`/`REQUEST_STARTED` pozostawały niewidoczne dla `list-reconciliations`, nierozstrzygalne przez resolver („Only NEEDS_RECONCILIATION") i bezterminowo blokowały budżet; `REQUEST_STARTED` mógł kryć realny, niezaksięgowany koszt. Test audytowy utrwalał stuck state jako sukces — to nie było poprawne kryterium. **Naprawa:** recovery (`release_or_requeue_expired_leases`) w tej samej transakcji atomowo eskaluje oba crash-windows do `NEEDS_RECONCILIATION` z enumerowanym powodem (`LEASE_EXPIRED_BEFORE/AFTER_REQUEST_STARTED`) i append-only eventem `AUTO_ESCALATION`; idempotentne, serializowane przez `BEGIN IMMEDIATE` (dwa maintenance = dokładnie jedna eskalacja), nigdy przy żywym lease, nigdy dla terminali, bez retry/attemptu #2/providera; eskalacja unieważnia stary preview token; attempt bez `REQUEST_STARTED` (dowodliwie brak calla) może być rozstrzygnięty wyłącznie `NOT_CHARGED` (aplikacja + macierz stanów: `RECONCILED_SETTLED` wymaga startu requestu).
- **W1A-SQLITE-01 (MAJOR):** surowy `UPDATE` mógł ustawić `RECONCILED_RELEASED` przy `job=NEEDS_VERIFICATION`, `run=RUNNING`, `research_run=PENDING` i zerze eventów — terminalizacja attemptu nie wymagała pełnej atomowej terminalizacji lifecycle i historii. **Naprawa:** resolver flipuje attempt jako OSTATNIĄ trwałą mutację (`walidacja → lifecycle → usage/cache → FINAL_RESOLUTION → attempt`), a `0014` (in-place) dokłada trzy triggery terminalizacji: wymagany dokładnie zgodny event `FINAL_RESOLUTION` (status/resolution/operator/note), terminalny spójny lifecycle zgodny z execution resolution (FAILED/FAILED/FAILED bez karty albo DONE/SUCCESS/COMPLETE z kartą) ze zwolnioną rezerwacją i lease, oraz cache'e równe kanonowi (tolerancja pół kwantu 5e-7). Eventy (każdego typu) można dopisywać wyłącznie przy żywym `NEEDS_RECONCILIATION` — nigdy po terminalu.
- **W1A-SQLITE-02 (MAJOR):** po prawidłowym `RECONCILED_SETTLED` surowy SQLite mógł zmienić koszt `model_usage` (0.05 → 0.123456 przy cache'ach 0.05), a następnie usunąć wpis — łamiąc `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd` i kanon. **Naprawa:** kanoniczny `model_usage` rekoncyliowanego attemptu ma triggery no-UPDATE (każda kolumna) i no-DELETE; nowy wpis dla terminalnego attemptu jest niereprezentowalny (relacja + UNIQUE); `runs.cost_usd` i `research_runs.total_cost_usd` są zamrożone po terminalu.
- **W1A-AUD-01 (MINOR, domknięte):** błędy `OSError/RuntimeError/sqlite3.Error` podczas samego zapytania/formatowania/close w `list-reconciliations` → kontrolowany exit 6 (wcześniej traceback); `reconcile-attempt` dołożone `RuntimeError` i guarded close.
- **W1A-DOC-01 (MINOR, domknięte):** stale „980" w MASTER_ARCHITECTURE/IMPLEMENTATION_ROADMAP/ARTICLE_EVIDENCE/RESEARCH_LOG/opis-budowy — sweep do aktualnego baseline; historyczne 980/982 jawnie historyczne.
- **W1A-QA-01 (P2, domknięte):** `reconciliation_lineage_disproof.py` zostawiał katalogi `mkdtemp()`; teraz prefiksowane `nia-lineage-disproof-`, cleanup w `finally` także po wyjątku, twarda kontrola pozostałości w exit code + trwały test subprocess.
- **Dowód:** +25 trwałych testów (macierz eskalacji H1–H20: żywy/martwy lease, wyścig dwóch maintenance, reopen przed/po, widoczność queue+CLI, preview/stale-token, `NOT_CHARGED`-only dla byłego `RESERVED`, `CHARGE_UNKNOWN`/`CHARGED_KNOWN` dla byłego `REQUEST_STARTED`, budżet przed/po, brak retry/attemptu #2, rollback failpointów eskalacji, append-only `AUTO_ESCALATION`; macierz raw-SQLite: partial lifecycle, brak/niezgodny `FINAL_RESOLUTION`, rozjechany cache, mutacja/kasowanie/duplikat kanonu, zamrożone cache; ciek QA). Licznik **982 → 1007**, pełny suite 1007/1007, 4 partycje exact-once 4/4 exit 0, concurrency 33×30 = 30/30, pliki 10/10, QA 10/10 bez pozostałości, niezależne kontrpróby 5/5 (wyścig resolver↔eskalacja, heartbeat↔recovery, partial lifecycle, porzucona transakcja po reopen, budżet przed/po), `data/agent.db` byte-identical. Szczegóły: ADR-066. WAVE 1A = `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-16 — WAVE 1A: pełny audyt software-assurance working tree (W1A-AUD) — zero MAJOR/CRITICAL, trzy MINOR naprawione, jeden P2 report-only (status historyczny: trzecie review przeklasyfikowało AUD-04 na MAJOR — patrz wpis wyżej)

- **Kategoria:** AUDIT / CLI robustness / contract hygiene / lifecycle boundary.
- **Zakres:** pełny read-only audit HEAD `c25e125` + wszystkich niecommitowanych zmian (resolver, migracja 0014, CLI, testy, QA, dokumentacja) zlecony przez właściciela; autoryzowana jedna skonsolidowana fala napraw. Regresja wszystkich wcześniejszych findingów (W1A-RR-01…06, W1A-NEW-01/02, W1A-VERIFY-01/02) zweryfikowana niezależnie — wszystkie pozostają ZAMKNIĘTE.
- **W1A-AUD-01 (MINOR, naprawione):** `list-reconciliations` nie miało kontrolowanej obsługi `ConfigError`/`sqlite3.Error`/`OSError` — błąd konfiguracji lub storage kończył się surowym tracebackiem zamiast kontrolowanym exit code. Naprawa: symetryczna obsługa jak w `reconcile-attempt` (config → 3, storage → 6) + trwały test.
- **W1A-AUD-02 (MINOR, naprawione):** `ProviderAttemptReconciliationResult.version_token` było martwym polem — nigdy nieustawiane i niekonsumowane; sugerowało reviewerowi, że confirm zwraca świeży token. Usunięte; version token pochodzi wyłącznie z preview.
- **W1A-AUD-03 (MINOR, naprawione):** anotacja `actual_cost_usd: float | None` w `StoragePort` i `SqliteStorage` była niezgodna z faktycznym kontraktem — CLI świadomie przekazuje `str` dla dokładności Decimal. Teraz `float | str | None`.
- **W1A-AUD-04 (P2, REPORT-ONLY, styczne do otwartego P2-19):** attempt `RESERVED`/`REQUEST_STARTED` po twardym crashu procesu i wygaśnięciu lease (job → `NEEDS_VERIFICATION` przez recovery) jest **niewidoczny** dla `list-reconciliations` i **nierozwiązywalny** przez resolver (celowy kontrakt „Only NEEDS_RECONCILIATION may be resolved"); jego rezerwacja bezterminowo pomniejsza dzienny/miesięczny budżet (kierunek konserwatywny — zero ryzyka fail-open/nadpłaty; `REQUEST_STARTED` może jednak oznaczać realny, niezaksięgowany koszt providera — dokładnie klasa P2-19). Preview pozostaje oknem odczytu operatora. Rozszerzenie kontraktu resolvera (np. eskalacja `REQUEST_STARTED → NEEDS_RECONCILIATION` przy martwym lease) wymaga jawnej decyzji właściciela — nie zmieniono zrecenzowanego kontraktu. Trwały test dokumentujący granicę: `test_crashed_request_started_attempt_after_lease_expiry_is_fail_closed` *(historyczne: trzecie review odrzuciło ten kontrakt jako utrwalenie defektu; test zastąpiony macierzą eskalacji H1–H20 — patrz wpis wyżej)*.
- **Kontrpróby audytora (temp DB, safety kernel, świeże procesy):** replay terminalnej decyzji z innym note/operatorem/finansem → „already reconciled with different parameters", zero mutacji; granice half-quantum `0.0000004` (odrzucone) / `0.0000005 → 0.000001` / `0.0000015 → 0.000002` (ROUND_HALF_UP w ledgerze); ekstremalne koszty CLI `NaN`/`Infinity`/`-Infinity`/`not-a-number` → exit 4, `1e400` → kontrolowany exit 6 — wszystko bez mutacji.
- **Dowód:** licznik **980 → 982**; pełny suite 982/982; 4 partycje exact-once (237+241+254+250); concurrency 30/30; reconciliation+lineage files 10/10; `scripts/qa/reconciliation_lineage_disproof.py` 10/10; `compileall` i `git diff --check` czyste; `data/agent.db` byte-identical (SHA-256 `CAEDDA05…FEFB`). WAVE 1A = `CANDIDATE — AWAITING INDEPENDENT REVIEW`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A `W1A-VERIFY-02`: fail-open pełnego lineage (foreign `runs.account_id` / ANALYTICS workflow)

- **Kategoria:** SAFETY / accounting integrity / authorization (MAJOR, drugie niezależne review = `REJECTED — MAJOR`).
- **Kontrpróba (dokładna, odtworzona na temp DB):** `jobs.account_id` i `research_runs.account_id` = konto właściciela; `runs.account_id` = konto obce; `runs.workflow` = `ANALYTICS`.  Resolver zaakceptował reconciliation i terminalizował attempt→`RECONCILED_RELEASED`, job/run/research_run→`FAILED` (+1 event).  Dowód: `scripts/qa/reconciliation_lineage_disproof.py` (przed naprawą: LEAK; po naprawie: BLOCKED, zero mutacji).
- **Root cause:** `_reconciliation_state_row` nie czytał `runs.account_id`/`runs.workflow`/`jobs.kind`/`jobs.workflow`; walidacja sprawdzała tylko `research_runs` account/topic.  Brak weryfikacji pełnej relacji `provider_attempt → job → run → research_run → account → workflow → topic → durable intent`.  **Zielony baseline 955/955 (ADR-064) nie obejmował tego przypadku** — wprost pokazuje, że przejście suite nie dowodzi kompletności zakresu.
- **Naprawa (defense-in-depth):** (1) `_reconciliation_require_consistent_lineage` waliduje cały lineage przed mutacją; (2) version token v2 obejmuje wszystkie pola lineage (stale między preview a confirm ⇒ fail-closed); (3) trigger SQLite `provider_attempts_reconcile_requires_consistent_lineage` (0014 in-place) blokuje niespójną terminalizację (również `json_extract` payload↔job).  Fingerprint intentu pozostaje inwariantem aplikacyjnym (SQLite nie przelicza SHA-256) — udokumentowane.
- **Dowód:** `tests/test_reconciliation_lineage.py` (17 negatywnych rozjazdów, każdy = pełny brak mutacji; stale token 14–17; raw-trigger; pozytywne), `scripts/qa/reconciliation_lineage_disproof.py` 10/10 w świeżych procesach; licznik **955 → 980**, pełny suite 980/980, 4 partycje exact-once, concurrency 30/30, `data/agent.db` bez zmiany.  Szczegóły: ADR-065.  WAVE 1A = `CANDIDATE`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A `W1A-VERIFY-01`: niedeterministyczny test resolver↔reaper (flaky), nie fałszywy sukces

- **Kategoria:** TEST DETERMINISM / lifecycle completeness (SAFE — bez wpływu na bezpieczeństwo).
- **Objaw:** niezależna weryfikacja ADR-063 pokazała, że deklarowane „948 passed" nie było odtwarzalne — `test_resolver_interleaves_with_recovery_and_reaper_without_reviving_attempt` przechodził ~50% (3/6 w izolacji), reszta suite stabilna (947 passed + 1 flaky).
- **Root cause:** maintenance-reaper `reap_orphaned_stale_runs` ustawia osierocony stale run na `STOPPED`, gdy job pozostaje `NEEDS_VERIFICATION` (guard reapera nie blokuje — `NEEDS_VERIFICATION ∉ {QUEUED,LEASED,RUNNING}`), a resolver `EXECUTION_FAILED` akceptował tylko `run_status ∈ {RUNNING, FAILED}`. Kolejność wątków decydowała: resolver-first → run `RUNNING` → OK; reaper-first → run `STOPPED` → resolver fail-closed. Żadnego fałszywego `DONE`, dodatkowego usage ani attemptu #2 — wyłącznie flaky.
- **Naprawa (autoryzowana, minimalna):** `EXECUTION_FAILED` akceptuje `run_status ∈ {RUNNING, STOPPED, FAILED}` (wspólny `_EXECUTION_FAILED_RUN_STATUSES` w warunku i w CAS `UPDATE`, `COALESCE` zachowuje historię reaper/maintenance), atomowo `STOPPED → FAILED`; `RESULT_ALREADY_FINALIZED` i kontrakt finansowy bez zmian; `STOPPED` nigdy → `DONE`.
- **Dowód:** 7 nowych deterministycznych testów; flaky node **30/30**, plik **10/10**; pełny suite **955** offline, 4 partycje exact-once, 20/20 kontrprób BLOCKED, `data/agent.db` niezmieniona. Szczegóły: ADR-064. WAVE 1A = `CANDIDATE`; Etap 1 `BLOCKED`; live API `ZABRONIONE`.

## 2026-07-15 — WAVE 1A: niezależny audyt odrzucił pierwszą iterację (`REJECTED — MAJOR`), naprawa in place

- **Kategoria:** SAFETY / accounting integrity / durable proof.
- **Odrzucone findingi:** W1A-RR-01 (istniejący `model_usage` akceptowany po samym koszcie), W1A-RR-02 (`RESULT_ALREADY_FINALIZED` mógł użyć współdzielonej/cudzej karty), W1A-RR-03 (`CHARGE_UNKNOWN` nadpisywał operatora/notatkę — utrata historii), W1A-RR-04 (migracja 0014 dopuszczała puste pola audytu, nieznane wartości resolution, audyt w złych stanach i usunięcie terminalnego `RECONCILED_RELEASED`), W1A-RR-05 (sprzeczna dokumentacja), W1A-RR-06 (CLI bez trwałego stanu/version tokenu), W1A-NEW-01 (`CHARGED_KNOWN`/`NOT_CHARGED` + `MANUAL` = terminalny attempt z jobem na zawsze w `NEEDS_VERIFICATION`), W1A-NEW-02 (`CHARGED_KNOWN` + `MANUAL` zapisywał usage bez odświeżenia cache — rozjazd ledger↔cache).
- **Naprawa (jedna fala):** append-only `reconciliation_events` jako jedyna historia; pełna weryfikacja tożsamości istniejącego usage; wyłączna własność karty przez `UNIQUE research_runs(research_card_id)`; usunięty dead-end `MANUAL` (tylko z `CHARGE_UNKNOWN`); niezmienna spójność `SUM(model_usage)=runs.cost_usd=research_runs.total_cost_usd`; `CHARGED_KNOWN` wymaga kosztu>0; migracja 0014 poprawiona **in place** z pełnym kontraktem i surowymi wymuszeniami SQLite; CLI preview/confirm z version tokenem i kontrolowanymi exit codes.
- **Dowód:** **955 testów offline** (w tym negatywne testy surowego SQLite, tożsamość usage, wyłączna własność karty, macierz lifecycle, restart failpoints, współbieżność, subprocess), 0014 fresh/upgrade/rollback + `integrity_check`/`foreign_key_check`, `data/agent.db` bez zmiany. WAVE 1A = `CANDIDATE`; WAVE 0B = `CLOSED — APPROVED WITH P2`; Etap 1 `BLOCKED`; live API `ZABRONIONE`. Historyczne 894/13 są historyczne.

## 2026-07-15 — WAVE 1A: niepewnego kosztu nie wolno zamienić w retry

- **Kategoria:** SAFETY / accounting consistency.
- **Ryzyko:** `NEEDS_RECONCILIATION` łączy nieznany skutek finansowy z zatrzymanym jobem. Automatyczne zwolnienie rezerwacji, wpisanie zgadywanej kwoty albo nowe wywołanie providera mogłyby sfałszować historię kosztu.
- **Naprawa:** resolver L1 ma trzy jawne wyniki finansowe i trzy niezależne wyniki wykonawcze. Tylko `CHARGED_KNOWN` może dodać canonical `model_usage`; `NOT_CHARGED` jest odrzucane przy usage; `CHARGE_UNKNOWN` pozostaje nierozstrzygnięty. Failpointy po usage/attempt/run/research_run/job i przed commitem dowodzą pełnego rollbacku.
- **Dowód:** migracja 0014 rollback, `UNIQUE(request_id)` dla usage, konflikty operatorów, stale preview CLI, błędne kwoty i stanowe odmowy; po naprawie `REJECTED — MAJOR` **955 testów offline**, 14 migracji, bez API, sieci, kosztu lub zmiany chronionej bazy. (Historyczny wynik iteracji: 919.)
- **Status:** WAVE 1A `CANDIDATE — AWAITING INDEPENDENT REVIEW` (po naprawie); Etap 1 `BLOCKED`, live API `ZABRONIONE`.

### [2026-07-13] P1 — rozdzielona inicjalizacja RESEARCH tworzyła osierocone runy po crashu

- **Kategoria:** TECH
- **Co miało działać:** restart workera nie może tworzyć drugiego runu dla jednego joba RESEARCH.
- **Co się zepsuło:** crash po `create_run` i `create_research_run`, lecz przed `attach_job_run`, zostawiał `jobs.run_id=NULL`; recovery requeue’owało job i drugi worker tworzył drugi komplet.
- **Przyczyna:** trzy osobne commity nie utrzymywały inwariantu „run i research_run istnieją tylko wraz z `jobs.run_id`”.
- **Naprawa i dowód:** ADR-044 wprowadza jeden `BEGIN IMMEDIATE` dla run, research_run i CAS joba; failpointy przed i po commicie, reopen/recovery, fencing i `Barrier` potwierdzają brak duplikatu. Brak API, zmiany `data/agent.db` i kosztu rzeczywistego.

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

### [2026-07-12] Task 6 — koszt odpowiedzi tematów znikał po parse-error — [COST | DATA]

- **Co było nie tak:** klient tematów wykonywał `json.loads(text)` przed zbudowaniem `Usage`. Poprawnie zbilowana odpowiedź z uciętym lub wadliwym JSON-em przerywała funkcję, zanim usage mogło dotrzeć do workflow; run pozostawał bez kontrolowanej ścieżki `FAILED`.
- **Różnica błędów:** provider error przed odpowiedzią nie ma usage i nie wolno wymyślać kosztu. Parse/schema error po odpowiedzi ma już rzeczywiste usage i model, więc ich utrata byłaby fałszywą księgowością.
- **Naprawa:** response → `Usage` → text → parse; typowane provider/parse/schema errors; jeden ścisły zewnętrzny code fence; workflow zapisuje usage raz, ustawia `FAILED` i nie zapisuje topics.
- **Dlaczego bez retry:** wadliwy format odpowiedzi nie jest błędem transient. Automatyczne powtórzenie mogłoby zapłacić drugi raz bez usunięcia przyczyny.
- **Nieudana wersja podczas pracy:** pierwsza poprawka wciąż składała tekst przed `Usage`. Self-review sklasyfikował to jako P1 względem literalnego kontraktu i odwrócił kolejność przed finalną weryfikacją.
- **Dowód:** 35 testów topics i 286 całego suite, wyłącznie fake caller/fake SDK oraz SQLite; 0 USD, zero API.

### [2026-07-12] Task 8 — pierwsza macierz lifecycle odrzuciła legalne resume — [IMPLEMENTATION | TEST]

- **Co się zepsuło:** pierwszy celowany suite miał 4 failures. Staged A2 z `max_sources=0` legalnie zapisywał `DISCOVERY_COMPLETE→PARTIAL`, a kolejne jawne próby resume aktualizowały wynik tego samego ogólnego runu `FAILED→FAILED`; początkowa macierz obu kontraktów nie uwzględniła.
- **Dlaczego:** statusy są rozdzielone na ogólny audit `runs` i szczegółowy `research_runs`. Odczyt samego diagramu bez wszystkich callerów nie ujawnił, że resume zachowuje ten sam `run_id` i może zakończyć się kolejnym błędem bez cofania researchu do początku.
- **Naprawa:** staged PARTIAL dopuszcza `DISCOVERY_COMPLETE`, `EXTRACTION_IN_PROGRESS` i `PARTIAL`. `finish_run` dopuszcza FAILED→FAILED wyłącznie jako zapis następnej jawnej próby; identyczne powtórzenie jest no-op, a FAILED→SUCCESS i każdy inny konflikt terminali nadal są odrzucane.
- **Dowód:** 44 testy Task 8, 96 celowanych i 330 pełnych; race różnych terminali oraz konkurencyjnego resume ma dokładnie jeden statusowy UPDATE. Wszystko offline, bez API i kosztu.
- **Status:** FIXED przed niezależnym review.
- **Drobna nieudana próba testowa:** pierwszy trigger audytowy użył w body składni `INSERT ... DEFAULT VALUES`, której SQLite nie przyjął w tym kontekście. Zastąpiono ją równoważnym `VALUES (NULL)`; błąd nie dotyczył kodu produkcyjnego ani danych.

### [2026-07-13] Review Task 8: ogólny FAILED był przepisywalny, a test claimu nie był race — [AUDIT | TEST]

- **P1-1:** wyjątek FAILED→FAILED znajdował się w ogólnym `finish_run`, więc również niereseachowy terminalny run mógł zmienić koszt, błąd i timestamp. Oddzielono zwykłą finalizację od jawnego resume z pełną walidacją relacji oraz CAS.
- **P1-2:** dwa połączenia SQLite były użyte kolejno, nie równolegle. Test nie dowodził zachowania przy jednoczesnym snapshotcie PENDING. Zastąpił go deterministyczny `Barrier` i dwa wątki.
- **Nieudana pierwsza korekta race resume:** `BEGIN` przed SELECT tworzył upgrade-lock race i faktyczny `database is locked`. Diagnostyczny SELECT jest teraz poza transakcją zapisu, natomiast UPDATE ponownie sprawdza cały kontrakt oraz token CAS. Test nie łapie OperationalError — lock pozostaje porażką.
- **Wynik:** 337 testów, w tym oba race powtórzone 10 razy; 0 USD i brak API.
- **Status:** FIXED; oczekuje na krótkie końcowe review.

### [2026-07-13] Task 9: realne B wyczerpało max_tokens i zwróciło ucięty JSON — [LIVE API | PARSE | COST]

- **Run:** `c01171bc-7ff5-4b83-bbfa-c0b164137793`, flow staged, topic #2.
- **Co zadziałało:** A1 odkrył 4 kandydatów; wszystkie cztery A2 zakończyły się `end_turn`, EXTRACTED i VERIFIED. Każdy candidate miał `attempts=1`; zero retry.
- **Co się zepsuło:** B osiągnęło dokładnie 2200 output tokens i `stop_reason=max_tokens`. JSON urwał się wewnątrz stringa (`Unterminated string`, char 4224), więc parser poprawnie odmówił utworzenia karty. Nie jest to timeout ani błąd transient; automatyczny retry był zabroniony i nie nastąpił.
- **Koszt:** 0,170050 USD = A1 0,029243 + A2 0,127903 + B 0,012904. Całość jest w `model_usage`, `runs.cost_usd` jest zgodne; cap 0,55 USD zachowany.
- **Stan odzyskiwalny:** `research_runs=SOURCES_COMPLETE`, 4 VERIFIED, brak karty, temat SELECTED. Technicznie możliwe jest wyłącznie jawne resume B, ale wymaga nowej zgody i nie zostało wykonane.
- **Diagnostyka:** prywatny `B_raw_response.txt` potwierdza `max_tokens`, 1904 input, 2200 output, 0 search i długość 4489 znaków. Surowa treść nie jest kopiowana do repo.
- **Status:** OPEN; Task 9 i Etap 0 nieukończone.

### [2026-07-13] Task 9: proces zakończył się, ale ogólny run pozostał RUNNING — [LIFECYCLE | AUDIT]

- **Obserwacja:** po obsłużonym błędzie B CLI zakończyło pojedynczy run, lecz `runs.status=RUNNING`, `finished_at=NULL`, `error=NULL`; jedynie cache kosztu wynosi 0,170050 USD. Szczegółowy `research_runs` poprawnie wrócił do wznawialnego `SOURCES_COMPLETE` z opisem błędu.
- **Przyczyna w odczytanym kodzie:** ścieżka błędu świeżego `run_synthesis_from_cards` wywołuje `revert_to_sources_complete`, ale terminalizuje ogólny audit tylko wtedy, gdy istnieje snapshot jawnego resume.
- **Wpływ:** kanoniczne `model_usage` i `runs.cost_usd` są spójne, a źródła trwałe, lecz ogólny audit fałszywie sugeruje aktywny proces. `research_runs.total_cost_usd` pozostało 0,0 — to potwierdzenie znanego P2-2 (niekanoniczny cache), nie utrata usage. Stan wymaga niezależnego review przed kolejnym krokiem.
- **Działanie:** zgodnie z Task 9 nie zmieniono kodu, statusu ani bazy ręcznie; nie wykonano resume. Klasyfikacja ważności i ewentualna poprawka należą do osobnego review.

### 2026-07-13 — P1-1/P1-2 naprawione offline dla przyszłych wykonań; historyczny run bez mutacji

- **P1-1 przyczyna:** limit B=2200 pochodził z domyślnej wartości klienta/pipeline/CLI. Estymator przyjmował przekazany limit poprawnie, ale sam limit okazał się zbyt niski dla realnego schematu; klient próbował parsować odpowiedź mimo jednoznacznego `stop_reason=max_tokens`.
- **P1-1 poprawka:** jeden kanoniczny default 3000, jawny override CLI, zwięzłe limity pól promptu i `ResearchTruncatedError` przed JSON parse. Usage/raw/stop_reason zostają zachowane, bez auto-retry i częściowej karty. B=0,026250 USD conservative; fresh=0,516375 USD; resume z prior=0,196300 USD.
- **P1-2 przyczyna:** fresh ścieżka błędu wywoływała `revert_to_sources_complete`, lecz terminalizowała `runs` tylko dla explicit resume snapshot.
- **P1-2 poprawka:** fresh B failure wywołuje warunkowe `finish_run(...FAILED...)`; explicit resume zachowuje `finish_resumed_research_run` z CAS. Reopen SQLite potwierdza `FAILED`, `finished_at`, przyczynę, brak karty i nienaruszone `SOURCES_COMPLETE`.
- **Stan historyczny:** poprawka nie działa wstecz. `c01171bc` nadal ma RUNNING/NULL; nie wykonano raw SQL, repair ani resume. P2-2 pozostaje świadomym cache (`model_usage` jest kanonem), a P2-17/P2-18/P2-19 są poza zakresem.
- **Plan repair (NIEWYKONANY):** osobna, reviewowana komenda maintenance ma otworzyć repozytorium i w jednej kontrolowanej operacji lifecycle wywołać istniejące `finish_run(..., FAILED, 0.170050, error=...)`; nie jest potrzebna nowa migracja ani surowy SQL. Przed mutacją musi atomowo/tuż przed CAS potwierdzić dokładny run ID, konto i workflow RESEARCH, `runs=RUNNING/finished_at=NULL/error=NULL/cost_usd=0.170050`, `research_runs=staged/SOURCES_COMPLETE/card=NULL/topic=2`, topic SELECTED, 4 kandydatów EXTRACTED+VERIFIED, brak karty, 6 rekordów `model_usage` sumujących się do 0.170050 oraz ostatni Stage B FAILED z `stop_reason=max_tokens`; jakakolwiek rozbieżność = fail-closed.
- **Skutek repair:** zmienia wyłącznie audit `runs` na FAILED, ustawia `finished_at` i zachowuje pełną przyczynę `[synthesize_from_cards] ... stop_reason=max_tokens`; nie zmienia `model_usage`, `runs.cost_usd`, `research_runs.status`, `research_runs.total_cost_usd`, kandydatów, topic ani kart. Po operacji należy zapisać jawny log maintenance z preconditions/wynikiem, ponownie otworzyć SQLite, sprawdzić wszystkie inwarianty i dopiero w osobnym kroku prosić o zgodę na płatny resume B.

### 2026-07-13 — historyczny nieterminalny audit naprawiony kontrolowanym maintenance

- **Status:** FIXED dla runu `c01171bc-7ff5-4b83-bbfa-c0b164137793`; nie wykonano resume.
- **Dowód bezpieczeństwa:** backup i logiczny snapshot przed zmianą; wszystkie opisane wyżej preconditions ponownie sprawdzone wewnątrz `BEGIN IMMEDIATE`; brak triggerów na `runs`; warunkowy UPDATE wymagał właściwego ID, konta, workflow RESEARCH, statusu RUNNING, `finished_at/error IS NULL` i kosztu 0,170050. `rowcount=1`, `total_changes=1`; każda niezgodność powodowałaby rollback.
- **Zmiana:** wyłącznie `runs.status=FAILED`, `finished_at=2026-07-13 05:39:30 UTC` oraz pełny maintenance error z etapem `synthesize_from_cards`, `stop_reason=max_tokens` i wcześniejszym `ResearchParseError/truncated JSON`.
- **Niezmienione po reopen:** `runs.cost_usd=0,170050`; sześć `model_usage` o sumie 0,170050; `research_runs=SOURCES_COMPLETE`, `research_card_id=NULL`; topic #2 SELECTED; 4×EXTRACTED/VERIFIED/attempts=1; stage timestamps/log, account, karty i źródła. `integrity_check=ok`.
- **Granica:** naprawiono prawdziwość auditu, nie wynik researchu. Etap 0 nadal nieukończony, a resume wyłącznie B pozostaje osobnym potencjalnie płatnym działaniem wymagającym jawnej zgody.

### 2026-07-13 — resume B zakończone technicznie, karta odrzucona jakościowo

- **Call:** jedyne zatwierdzone B zakończyło się poprawnie (`stop_reason=end_turn`, 1904/2402 tokenów, 0 search, 0,013914 USD); nie wystąpił błąd providera ani parsera i nie wykonano retry.
- **Bramka jakości:** karta #2 otrzymała `publication_recommendation=REJECT` z powodami `THESIS_UNSUPPORTED` i `CLAIMS_WITHOUT_SOURCES`. To poprawna odmowa użycia materiału do treści, nie awaria lifecycle; COMPLETE/SUCCESS/USED i kryterium Etapu 0 pozostają spełnione.
- **P2-20:** `research_runs.error` po COMPLETE nadal zawiera parse-error pierwszego, nieudanego B. Pełna historia prób istnieje w `research_stage_results` (B FAILED, potem B SUCCESS), więc utrzymanie starego tekstu w polu bieżącego stanu może mylić konsumentów. Nie zmieniono kodu ani bazy; finding czeka na niezależne review.
- **Koszt:** run łącznie 0,183964 USD ≤ 0,20; dodatkowy B 0,013914 USD. Brak drugiego calla.

### 2026-07-13 — wszystkie błędy SDK Anthropic udawały timeout — [P1 | RETRY | COST]

- **Problem:** `_call_anthropic` przechwytywał każde `Exception` z `messages.create` i rzucał `ResearchTimeout`. Stałe odmowy 400/401/403/404/422 mogły więc zostać potraktowane jak transient i uruchomić kolejny potencjalnie płatny call.
- **Naprawa:** wyjątki SDK są mapowane na typy domenowe; retry jest jawnie dozwolone wyłącznie dla timeout, SDK-network, 429 i 500/502/503/504. Unknown i pozostałe statusy są terminalne dla próby. Parse, truncation, validation i budget error pozostają poza retry.
- **Regresja kosztowa:** każda kolejna próba przechodzi świeży callback budżetowy. Jeśli błąd niesie prawdziwe usage, zapis następuje raz przed retry; jeśli SDK go nie zwraca, system nie zapisuje fikcyjnego 0 USD.
- **Ryzyko rezydualne:** P2-19 pozostaje OPEN — timeout może być zbilowany bez lokalnego usage. Ten task nie dodaje rekonsyliacji billingowej ani rezerwacji globalnej.
- **Weryfikacja:** 382 testy offline, bez API i dodatkowego kosztu.

### 2026-07-13 — typed provider error tracił klasę w polach auditu — [P1 | AUDIT]

- **Objaw:** `ResearchInvalidRequestError(status_code=422, retryable=False)` kończył run poprawnie i księgował usage, lecz `runs.error`/`research_runs.error` zawierały tylko etap i komunikat.
- **Przyczyna:** każda ścieżka persystencji budowała własne `f"[stage] {exc}"` albo `str(exc)`.
- **Naprawa:** jeden bounded/redacting formatter dla run, research_run, stage i candidate audit. Nie zapisuje raw response, cause, request/response ani headers; zachowuje bezpieczne skalarne metadane.
- **Dowód:** plikowa SQLite po reopen: 422 = jeden call/jeden usage/FAILED/SELECTED/zero kart; 429 po wyczerpaniu = dwa calle/dwa usage bez dubla; `runs.cost_usd == sum(model_usage)`. Pełne **406 passed**, 0 USD, brak API.

### 2026-07-13 — dwa P1 po review: body SDK i nagi Bearer mogły wejść do auditu — [P1 | SECURITY]

- **Przyczyna:** `str(APIStatusError)` SDK Anthropic 0.116.0 zawiera body odpowiedzi; dodatkowo regex traktował `Bearer` jako sekret tylko przy poprzedzającej nazwie nagłówka.
- **Naprawa:** mapper nie używa już tekstu SDK dla komunikatu domenowego, lecz kontrolowanego statusu/klasy. Formatter redaguje każdy case-insensitive `Bearer <token>`.
- **Dowód:** marker body nie występuje w błędzie domenowym ani w `runs.error`, `research_runs.error`, stage/candidate audit; typ, `status_code`, `retryable` i `__cause__` pozostają. Testy offline: **411 passed**, koszt 0 USD, bez API.

### 2026-07-13 — F4: crash po B mógł zapisać kartę bez sukcesu lifecycle — [P1 | DURABILITY]

- **Scenariusz:** B commitował `research_cards` i `sources` przed wpisem B SUCCESS oraz finalizacją `research_runs`, `runs` i `topics`. Przerwanie tworzyło kartę bez COMPLETE/SUCCESS/USED.
- **Naprawa:** atomowy helper staged B, `BEGIN IMMEDIATE`, walidacja pełnego kontraktu i rollback całego zestawu. Testowane są crash points: karta, drugie źródło, audit B i lifecycle; po każdym zostaje poprzedni `SYNTHESIS_PENDING`.
- **Lekcja:** atomowość finalnego statusu nie wystarcza, gdy artefakt wyniku jest wcześniej zapisywany. Dane i ich semantyczne zatwierdzenie muszą upaść razem albo przetrwać razem.
- **Status:** naprawione offline; 420 passed, 0 USD, brak API. P2-17, P2-18 i P2-19 poza zakresem.

### 2026-07-13 — F4 po review: booleany nie są autoryzacją lifecycle — [P1 | DURABILITY]

- **Co nie działało:** caller mógł przekazać `allow_prior_complete_card` albo `allow_failed_run` i ominąć część preconditions. Force nie był utrwalony, więc po B failure dispatcher resume nie znał legalnego trybu. Macierz awarii obejmowała zbyt mało miejsc i nie zawsze sprawdzała bazę po reopen.
- **Jak naprawiono:** jeden typowany context i cztery tryby finalizacji; `0008` z trwałym markerem force per run; CAS resume (`FAILED`, `finished_at`, marker błędu, `SOURCES_COMPLETE`, B FAILED); fail-closed preflight przed B. Każdy z 13 punktów awarii po reopen pozostawia pre-finalization state.
- **Dodatkowa granica:** genericzny wpis stage nie może utworzyć staged `B SUCCESS`; jedynym writerem sukcesu jest helper transakcyjny. Brak UNIQUE dla staged B/card sources pozostaje udokumentowanym P2 dla jednego procesu SQLite z `BEGIN IMMEDIATE`, nie otwartą ścieżką biznesową.
- **Dowód:** force→failure→resume po osobnym połączeniu SQLite, odmowa przed providerem/usage dla błędnego markera lub timestampu CAS, account/topic/flow/status/VERIFIED, conflicts, no-op i concurrency jednego oraz dwóch runów. **446 passed**, bez API i 0 USD.

### 2026-07-13 — F4 końcowe review: COMPLETE akceptował sprzeczny execution mode — [P1 | DURABILITY]

- **Scenariusz:** zwykły FRESH run mógł powtórzyć identyczny payload jako `FORCE_RERESEARCH`; karta, źródła i koszt były zgodne, więc no-op wracał zanim sprawdzono mode.
- **Naprawa:** COMPLETE najpierw waliduje marker force i semantykę fresh/resume. Resume porównuje też trwały B FAILED z tym samym markerem i `finished_at` CAS; timestamp porażki B jest zapisywany z `runs.finished_at`.
- **Dowód:** konflikty fresh↔force, fresh→resume, force→force-resume bez historii oraz dwa CAS mismatch po reopen nie zmieniają żadnego rekordu, kosztu ani timestampu. **449 passed**, 0 USD, bez API.

### 2026-07-13 — F4 P1: publiczny legacy finalizer nadal otwierał staged sukces — [P1 | DURABILITY]

- **Scenariusz:** `finalize_research_success` przyjmował staged `SYNTHESIS_PENDING`, a `mark_research_run_complete` delegował do niego. Caller mógł przekazać kartę i koszt poza atomowym helperem; dla staged COMPLETE identyczny payload wpadał w legacy no-op. To obchodziło typed context, A2, B SUCCESS i kanon `model_usage`.
- **Naprawa:** blokada flow `staged` następuje po odczycie relacji, lecz przed walidacją karty, no-opem i mutacjami. Generic i alias rzucają ten sam `ResearchTopicIntegrityError`; audyt wykazał też możliwość samego staged `runs.SUCCESS` przez `finish_run`, więc ten ogólny helper odmawia staged SUCCESS/DRY_RUN. Tylko `finalize_staged_research_with_card` może zapisać staged sukces i jego koszt.
- **Dowód:** SYNTHESIS_PENDING, COMPLETE z identyczną kartą/kosztem, FAILED i arbitralny koszt generic oraz SYNTHESIS_PENDING/COMPLETE aliasu są odrzucone; tak samo SUCCESS/DRY_RUN przez `finish_run`. Po reopen nie zmieniają się karty, źródła, B SUCCESS, statusy, usage, cache kosztu, timestampy, błędy, card ID ani force marker. **454 passed**, 0 USD, bez API.

### 2026-07-13 — Etap 1: lease nie może znaczyć „spróbuj jeszcze raz” — [PREVENTED FAILURE]

- **Ryzyko:** odczyt QUEUED, a potem osobny UPDATE pozwala dwóm workerom zabrać ten sam job; osobne checki budżetu pozwalają dwóm jobom przekroczyć limit łącznie. Gorszy wariant dotyczy browsera: utrata lease po kliknięciu nie dowodzi, że publikacja nie nastąpiła.
- **Zabezpieczenie:** claim, enqueue i rezerwacja są pojedynczymi transakcjami `BEGIN IMMEDIATE` z rowcount/CAS. Partial UNIQUE blokuje drugi aktywny research job per account/topic. BROWSER po expiry idzie do NEEDS_VERIFICATION, nie do auto-retry; tylko LOCAL/RESEARCH przed efektem zewnętrznym mogą wrócić do QUEUED.
- **Dług świadomy:** nie ma jeszcze workera, więc queue nie wie jeszcze, kiedy future research przekroczył granicę płatnego calla; jego dispatcher musi przed tym mieć osobną, trwałą semantykę skutku. PolicyEngine nadal nie czyta `system_flags` runtime (P1-7 pozostaje otwarte do integracji).
- **Dowód:** Barrier/reopen dla 8 klas wyścigów, 0009 rollback oraz **463 passed**, bez API i kosztu.
## 2026-07-13 — P1: stary worker zapisywał research po utracie lease

- **Wykrycie:** niezależne review końcowej akceptacji restartu po ADR-044.
- **Scenariusz:** worker A claimował job i atomowo inicjalizował run. Po expiry recovery ustawiał `NEEDS_VERIFICATION`, ale A pozostawał wewnątrz synchronicznego pipeline’u. Ponieważ `add_model_usage`, aktualizacja cache kosztu, `finish_run`, `mark_research_run_failed`, `add_research_card` i `finalize_research_success` nie znały job ID ani lease ownera, stary proces mógł zmienić canonical stan po recovery.
- **Skutek:** możliwe usage/koszt, FAILED albo COMPLETE i karta zapisane przez proces bez aktualnego prawa wykonania; `complete_job` odrzucał starego ownera dopiero za późno. To był P1, nie kosmetyka guardu.
- **Naprawa:** ADR-045. Po atomowej inicjalizacji powstaje `JobExecutionContext`; każda jobowa mutacja single-flow używa krótkiego `BEGIN IMMEDIATE` i sprawdza pełny job→run→owner→fresh lease fence w tej samej transakcji. `StaleJobExecutionError` przerywa pipeline bez wtórnego failure write.
- **Dowód:** expiry przed recovery, pełna old-owner matrix po recovery, utrata lease podczas klienta i race dwóch połączeń. Po close→reopen snapshot jest identyczny, usage/card nie istnieją, run pozostaje DRY_RUN/PENDING, job jest pod kontrolą recovery, integrity `ok`.
- **Granica:** realny provider może naliczyć koszt mimo utraty lease podczas calla. Nie wolno wtedy pozwolić staremu workerowi zapisać canonical wynik; przyszłe rozliczenie wymaga idempotentnego ledgeru provider request ID. Nie implementowano go w tym offline zadaniu.

## 2026-07-13 — P1: czas lease pobrany przed `BEGIN IMMEDIATE` i CSV jako fałszywa granica trwałości

- **Wykrycie:** niezależne końcowe review Etapu 1 po ADR-045.
- **Scenariusz lease:** operacja startowała przed expiry, lecz czekała na cudzy SQLite write lock. Zamrożony czas sprzed czekania pozwalałby po zwolnieniu locka zatwierdzić `RUNNING`, heartbeat, inicjalizację lub terminalizację już wygasłego lease.
- **Scenariusz CSV:** `record_job` najpierw poprawnie commitował `model_usage` i koszt do SQLite, ale błąd appendu `COSTS.csv` propagował się do ogólnego catcha workera. Ten mógł sfinalizować sam job, pozostawiając run/research_run w aktywnym stanie.
- **Naprawa:** czas jest odczytywany dopiero po `BEGIN IMMEDIATE`; runtime przekazuje `Clock`. `COSTS.csv` po commicie jest best-effort i loguje wyłącznie kontrolowane ostrzeżenie. Nieoczekiwany wyjątek po inicjalizacji uruchamia atomową fenced terminalizację job/run/research_run.
- **Dowód:** 42 restart acceptance, w tym 7 lifecycle i 5 fenced-write testów real-thread/file-SQLite lock wait i reopen, race heartbeat↔recovery, CSV success/failure oraz unexpected pipeline error; pełny suite 683 passed, `integrity_check=ok`, koszt 0 USD.
- **Pozostawiony dług:** przed Etapem 8 decyzja KEEP/DEPRECATE/REMOVE dla eksportu `COSTS.csv`; nie budowano eksportera ani outboxa. Realny provider request po utracie lease nadal wymaga odrębnego idempotentnego ledgeru.

### Nieudane próby podczas naprawy

1. Pierwsze uruchomienie najwęższego testu zakończyło się błędem kolekcji `ImportError: JobExecutionContext` — zamierzony czerwony dowód, że kontrakt jeszcze nie istniał; nie zmieniło bazy.
2. Pierwsza regresja maintenance+scheduling+queue+storage miała 1 failure: stary test granicy scheduling przekazywał naïwny timestamp odczytany z SQLite jako `now`. Nowy kontrakt UTC ma takie dane odrzucać, więc test jawnie przywraca znaną strefę UTC na granicy adaptera; walidacji produkcyjnej nie poluzowano.
3. Nie wykonywano retry płatnej ani publikującej operacji. Obie porażki były lokalne, deterministyczne i kosztowały 0 USD.

## 2026-07-14 — P1: post-dispatch heartbeat mógł częściowo terminalizować sukces RESEARCH

- **Wykrycie:** literalny restart acceptance po poprzednich naprawach Etapu 1.
- **Scenariusz:** pipeline workera commitował kartę, źródła, `research_runs=COMPLETE`, run i topic, a następnie `Worker.run_once()` wywoływał jeszcze końcowy heartbeat oraz `complete_job`. Wyjątek z tej ogólnej ścieżki trafiał do szerokiego catcha i mógł wykonać samotne `fail_job`.
- **Skutek przed naprawą:** reprodukcja z awarią czwartego heartbeat dawała `worker=FAILED`, `job=FAILED`, a `run=DRY_RUN` i `research_run=COMPLETE`. Baza była technicznie poprawna, lecz lifecycle semantycznie sprzeczny.
- **Naprawa:** ADR-047. Finalizacja jobowego success zapisuje `jobs=DONE` w tym samym commicie co artefakt i lifecycle researchu. Typowany wynik dispatchera zatrzymuje worker przed dodatkowym heartbeat/complete/fail. Diagnostyka po commicie jest best-effort i nie zmienia kanonu SQLite.
- **Dowód:** test był czerwony przed zmianą i zielony po niej; failpointy przed job UPDATE, po nim oraz po commicie wykazują odpowiednio pełny rollback albo trwały pełny sukces. Dodatkowo failure transaction zachowuje primary error mimo błędu rollbacku, a rzeczywisty path katalogu `COSTS.csv` nie zmienia wyniku. 53 acceptance i 695 testów offline, `integrity_check=ok`, 0 USD.
- **Pozostawiony dług:** nie powstał outbox ani ledger provider request ID; CSV pozostaje utrzymanym eksportem best-effort do audytu przed Etapem 8.

## 2026-07-14 — P1: runtime nie walidował właściciela terminalizacji DispatchResult

- **Wykrycie:** końcowy pakiet review Etapu 1 po ADR-047.
- **Reprodukcja:** `DispatchResult(terminalization="WORKFLOW_TERMINALIZED")` przyjmował string. Po rzeczywistym atomic success worker nie rozpoznawał go przez identity, próbował post-terminal heartbeat, widział wyczyszczony lease i raportował `LOST_LEASE`, mimo że baza była już DONE/COMPLETE.
- **Drugi inwariant:** `WORKFLOW_FAILED` jest własnością workflow dopiero, gdy workflow atomowo zamknął job, run i research_run; worker nie może po nim wywołać generic `fail_job` ani zmienić canonical error.
- **Naprawa:** ADR-048 wymaga enumu w zamrożonym `DispatchResult`, a Worker waliduje obiekt i enum ponownie, przed guardem i przed każdą finalną mutacją. Contract error jest propagowany, nie mapowany na failure ani LOST_LEASE. Inserty karty/źródeł wymagają `rowcount == 1`; rollback failure zostaje secondary note.
- **Dowód:** literalny konstruktor był czerwony przed zmianą; atomic failure ma 0 generic `fail_job`. 58 acceptance i pełny suite 700 passed, reopen/snapshot/integrity poprawne, koszt 0 USD.
- **Nieudana lokalna regresja:** po wymaganiu jawnego wyniku siedem osiągalnych fake dispatcherów testowych zwracało `None`; testy heartbeat oczekiwały wtedy LOST_LEASE. Doprecyzowano je do jawnego `WORKER_MUST_COMPLETE`, bez zmiany produkcyjnej semantyki i bez dotykania bazy.

## 2026-07-14 — P0: SDK mogło wydać więcej niż jedna logiczna próba

- **Wykrycie:** niezależny audyt końcowego pakietu Etapu 1.
- **Problem:** konstrukcje `anthropic.Anthropic(...)` nie przekazywały `max_retries=0`, więc SDK mogło po timeout, błędzie połączenia, 429 albo 5xx wysłać następny płatny request. Klient research miał dodatkowo własną pętlę retry. Równolegle zwykłe `app.main` ufało `DRY_RUN=false`, a ceny zero/brakujące mogły obniżyć estymatę do zera przed realnym wywołaniem.
- **Skutek potencjalny:** jedna zatwierdzona próba mogła oznaczać więcej niż jedno żądanie i koszt niezgodny z pre-flightem; nie wykryto nowego realnego wydatku podczas tej naprawy.
- **Naprawa WAVE 0A:** SDK dostaje `max_retries=0` i dodatni timeout; klient wykonuje jedną próbę i propaguje typowany błąd. Normalne CLI i worker są fake/offline niezależnie od env. Tylko capped root z `--real` może utworzyć adapter, po fail-closed walidacji pięciu cen. Brak `--real` nie tworzy klienta. Estymata tematów została wyrównana do requestu 1500 tokenów outputu.
- **Dowód:** testy fake/spy obejmują SDK config, timeout/429/5xx z licznikiem jednej próby, normalne CLI/worker z realnym kluczem, brak `--real`, ceny missing/0/negative/NaN/inf, dry-run bez ceny i zgodność limitu. Kodowa regresja ma 14 testów WAVE 0A i pełny suite 714 passed. **Niezależny review: `APPROVED WITH P2`; P0-01, P1-01 i P1-02 są zamknięte, a WAVE 0A formalnie zamknięta. Etap 1 pozostaje BLOCKED przez pozostałe P1.**
- **Granice:** bez sieci, API, publikacji, browsera ani kosztu; nie dodano ledgeru provider request ID ani reconciliation. Naruszenie lokalnej bramki `data/agent.db` jest opisane poniżej.

## 2026-07-14 — Naruszenie bramki acceptance: test WAVE 0A otworzył domyślną bazę

- **Wykrycie:** porównanie SHA-256 po pełnej regresji WAVE 0A.
- **Przyczyna:** test normalnego CLI podmienił `app.main.load_settings`, ale wywoływany runner ładował ustawienia w swoim module. W rezultacie test użył domyślnej ścieżki `data/agent.db` i zapisał wyłącznie artefakty fake/dry-run zamiast bazy tymczasowej.
- **Zakres:** zapisano 10 powtarzalnych runów/research cardów/topiców i 20 wierszy usage fake/dry-run; nie wykonano sieci, API, publikacji ani płatnego requestu. `PRAGMA integrity_check=ok`, ale hash zmienił się z `C92D9565DDA322997DE0D6A78D3943336E58CD9261229949E0BCFE4E43F9A63C` na `77F84B30F9E53A1964EFA2A44E4DBF821848758FFF86A29DB7A028AA55A3B22B`.
- **Działanie:** test zastąpiono bezpośrednim wywołaniem runnera z jawnym `Settings` wskazującym bazę tymczasową; jego 14 testów i pełny suite 714 passed nie zmieniły już bieżącego hashu. Nie wykonano kolejnego zapisu do `data/agent.db` ani nie próbowano „naprawy” bez źródłowej kopii.
- **Blokada historyczna:** przeszukane lokalne kopie projektu, katalog tymczasowy i zachowane artefakty nie zawierały pliku o hash bazowym `C92D9565DDA322997DE0D6A78D3943336E58CD9261229949E0BCFE4E43F9A63C`.
- **Kontrolowane odtworzenie po review:** właściciel zatwierdził wariant `APPROVE WITH P2` (P0=0, P1=0). Forensic analysis zaklasyfikowała artefakty testu jako klasę A, sekwencje jako klasę B, a istniejące UPSERT/`topics.id=1` jako klasę C nieudowadnialną historycznie. Na osobnej kopii usunięto tylko A i przywrócono B, następnie po dwóch reopenach (`integrity_check=ok`, `foreign_key_check=[]`) podmieniono wyłącznie główny plik po zachowaniu backupów. Nowy baseline to `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`.
- **Wynik i granica dowodu:** nie stwierdzono utraty realnych danych: 13 wpisów `dry_run=0` nadal sumuje 0,684580 USD, a `c01171bc` ma 0,183964 USD, Card #2, cztery VERIFIED sources i siedem usage. Werdykt `NOT PROVABLY RESTORABLE` dla dawnego pliku pozostaje prawdziwy — ustanowiono nowy baseline logiczny, nie odzyskano bitowego snapshotu. **Incydent bazy jest zamknięty; nie jest to zamknięcie Etapu 1.**

## 2026-07-14 — prewencja: niejednoznaczny skutek providera po restartcie

- **Ryzyko:** timeout, connection error albo awaria procesu tuż po wysłaniu requestu mogły pozostawić koszt bez odpowiedzi/usage. Ponowienie z nowym losowym identyfikatorem mogłoby stworzyć drugi koszt, a zwolnienie całej rezerwacji przed rozstrzygnięciem zaniżyłoby dostępny budżet.
- **Zmiana WAVE 0B:** `provider_attempts` zapisuje stabilne request_id i maksymalną rezerwację przed SDK. Po przekroczeniu granicy `REQUEST_STARTED` nie ma automatycznego retry; nieznany wynik zachowuje rezerwację w `NEEDS_RECONCILIATION`. Znamy za to różnicę między błędem przed requestem, odpowiedzią z usage i potwierdzonym błędem bez usage.
- **Dowód:** offline ledger/race/reopen/pipeline/CLI tests na tymczasowej SQLite; testowy guard odrzuca prawdziwą ścieżkę `data/agent.db`. Nie wykonano API, sieci, browsera, publikacji ani kosztu. Status: `WAVE 0B CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; to nie jest dowód live ani zamknięcie Etapu 1.

## 2026-07-14 — niezależne review WAVE 0B: trzy findingi P1

- **P1 — obejście durable joba:** `run_two_stage_research_pipeline` i `run_staged_research_pipeline` pozwalały realnemu klientowi rozpocząć świeżą pracę bez joba, lease i request ledgeru. Naprawa zatrzymuje rzeczywistego providera przed pierwszym wywołaniem i wskazuje WAVE 1A; fake/dry-run pozostają testowalne offline.
- **P1 — lokalna tożsamość operation key:** identyczny klucz nie był globalnym kontraktem semanticznego intentu, a komunikat CLI zależał od wyścigu między odczytem i insertem. Naprawa używa globalnego `real-research:<operation_key>` oraz atomowego wyniku enqueue; różny payload daje jawne `OPERATION_KEY_CONFLICT`.
- **P1 — zbyt słaby ledger attemptów:** wcześniejszy schemat pozwalał zapisać nieprawidłowy stan, request_id lub nowy real usage bez powiązanego requestu. Migracja `0011` wymusza kształt stanów, przejścia i request-bound usage; historii nie udaje się rekonstrukcji, tylko oznacza ją `is_legacy_usage=1`.
- **Dowód naprawy:** testy negatywne SQLite, test migracji poprawnej/uszkodzonej historii, testy wyścigu operation key i budżetu z niezależnych konekcji oraz pełny suite 741 passed. Bez API, sieci, browsera, publikacji, kosztu i zmiany `data/agent.db`.

## 2026-07-14 — WAVE 0B.2: drugi REJECT ujawnił brak dowodu, nie brak happy path

- **P1-01:** niski poziom realnego klienta dopuszczał caller bez contextu/ID; teraz każda taka próba kończy się typowanym błędem przed callerem i `messages.create`.
- **P1-02:** operation key nie był pełnym snapshotem wykonania; canonical intent zapisuje konfigurację, a test worker parity dowodzi użycia snapshotu po zmianie ENV.
- **P1-03:** ledger wymagał rozróżnienia braku dawnych danych od sprzecznych danych. `0012` wycofuje migrację dla arbitralnego request_id, obcego runu i brakującego attemptu, zamiast ukrywać je jako legacy.
- **Wynik:** 752 testy offline, zero API/sieci/kosztu i niezmieniony baseline bazy. Pozostaje wymagane niezależne re-review; operator reconciliation i WAVE 1A nie zostały wdrożone.

## 2026-07-14 — WAVE 0B.3: równe stringi nie są dowodem identity ani świeżego lease

- **P1-01:** context i callback mogły zwrócić ten sam arbitralny `request_id`, a klient porównywał wyłącznie ich wzajemną równość. Naprawa wyprowadza ID z trwałych pól i odrzuca arbitralne, job/stage/attempt mismatch oraz separator w stage przed callerem.
- **P1-02:** asercja lease odczytywała stare `context.checked_at`; po realnym expiry caller mógł nadal ruszyć. Naprawa pobiera czas execution clock wewnątrz nowej transakcji storage, a druga asercja chroni samo `messages.create`.
- **Dowód:** 770 testów offline obejmuje expiry, granicę równą expiry, odnowienie, takeover, zmianę run/fence i `NEEDS_RECONCILIATION`; 0 API, sieci, browsera, publikacji i kosztu; baseline bazy niezmieniony.

## 2026-07-15 — P1: testowy kernel nie dziedziczył granic bezpieczeństwa do subprocessów

- **Kategoria:** SAFETY
- **Co się zepsuło:** monkeypatch w `conftest.py` chronił główny interpreter, lecz subprocess mógł ominąć ochronę przez `sqlite3.dbapi2`, URI SQLite, proxy/NO_PROXY albo konstrukcję realnego SDK. To nie wywołało sieci ani nie zmieniło bazy podczas tego zadania, ale naruszało wymagany dowód izolacji.
- **Naprawa:** test-only `sitecustomize.py` ładuje dziedziczony kernel przed collection oraz w subprocessach. Blokuje surowe SQLite dla pełnej kanonizacji ścieżki, socket/DNS/SDK i czyści sekrety oraz proxy; tymczasowe SQLite i fake SDK pozostają dostępne.
- **Dowód:** main/subprocess raw+dbapi2+URI, socket/DNS, SDK oraz scrub environment; 823 testy offline, 0 USD, bez API i z niezmienionym SHA baselineu.
- **Status:** FIXED; niezależny review WAVE 0B nadal wymagany.

## 2026-07-15 — P1: provider attempt nie wiązał trwałego intentu z ostatnią granicą callera

- **Kategoria:** SAFETY
- **Co się zepsuło:** attempt miał request identity i fresh lease, ale nie trwały fingerprint wszystkich pól execution intentu. Zmiana `jobs.payload_json` po rezerwacji mogła rozjechać payload z attemptem przed fake/SDK callerem.
- **Naprawa:** `0013` przechowuje niezmienny SHA-256 canonical `execution_intent`; finalna transakcja przed callerem liczy go ponownie. Rozbieżność lub malformed/missing intent zostawia attempt w `NEEDS_RECONCILIATION`, bez callera, usage, kosztu i settlementu. `--real --resume` jest odmówione przed SQLite i `ensure_account`.
- **Dowód:** model/provider/token/timeout/cap/pricing/workflow/mode/prompt/pipeline są parametryzowane jako późne zmiany; każda ma `caller=0`, `usage=0`, `cost=0` i typed code. Weryfikacja full suite: 823 offline, 0 USD, bez API/sieci/browsera.
- **Status:** FIXED; nie jest to deklaracja zamknięcia WAVE 0B.

## 2026-07-15 — W0B-REV-01–05: snapshot techniczny nie obejmował jeszcze całego requestu

- **Kategoria:** SAFETY / consistency.
- **Co znaleziono:** fingerprint trwałego intentu obejmował parametry techniczne, lecz realny prompt nadal czerpał `topic.question` i `account.niche` z mutowalnych obiektów. Finalna asercja nie weryfikowała pełnego lifecycle `runs` i `research_runs`; brakowało też testów stage, prompt inputs, restartu oraz wariantów safety kernela.
- **Naprawa:** `durable_research_intent_v2` utrwala kanoniczne prompt-input i stage, a worker buduje plan wyłącznie z niego. Finalna transakcja odmawia po każdej niezgodności job/run/research_run/attempt/intent i zachowuje started attempt do reconciliation. Kernel czyści lowercase secret i fail-closed odrzuca nielokalny SQLite URI authority.
- **Dowód historyczny przed W0B-REV-06:** 861 testów offline obejmuje osobne mutacje parametrów requestu, terminalne/niespójne runy i research_runs, reopen SQLite, fake caller `0`, usage/koszt/settlement `0` oraz brak attempt #2. Nie użyto API, sieci, browsera ani chronionej bazy.
- **Status:** FIXED technicznie; WAVE 0B pozostaje `CANDIDATE` do niezależnego re-review, Etap 1 = `BLOCKED`.

## 2026-07-15 — CRITICAL W0B-REV-06: limit requestu rozchodził się z rezerwacją

- **Kategoria:** SAFETY / accounting consistency.
- **Co się zepsuło:** durable intent dopuszczał dodatni `max_tokens`, a caller używał `intent.max_tokens`, lecz single pipeline wyliczał koszt i rezerwował attempt z niezależnym `max_output_tokens=3000`. Request z limitem większym od 3000 mógł więc otrzymać actual usage cost większy od reservation, a dawny settlement zapisywał go jako zwykły `SETTLED`.
- **Naprawa:** dispatcher przekazuje literalny persisted limit do pipeline; pipeline przekazuje go do estymatora, policy i rezerwacji. Settlement canonicalizuje obie kwoty do sześciu miejsc USD (`ROUND_HALF_UP`). Nadwyżka nie znika: w tej samej transakcji zapisuje się jeden usage i koszt runu, attempt przechodzi do `NEEDS_RECONCILIATION` z `PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION`, a typed outcome blokuje sukces i attempt #2.
- **Dowód historyczny po REV-06:** poprawne durable intenty 2999/3000/3001, reopen, mutacja po attempt, exact estimate/reservation/caller, rounding boundary oraz actual under/over są testowane wyłącznie fake callerami i tymczasową SQLite. Pełna regresja: 873 node IDs, rozłączne partycje 206+218+226+223, wszystkie zielone; 0 USD, bez API/sieci/browsera/publikacji.
- **Status:** FIXED technicznie; `WAVE 0B CANDIDATE — AWAITING INDEPENDENT RE-REVIEW`, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Operator reconciliation pozostaje przyszłą pracą i nie jest udawany przez automatyczny retry.

## 2026-07-15 — W0B-REV-09/10: kronika nie nadążała, a dwa sposoby roundingu mogły rozjechać pieniądze

- **Kategorie:** documentation integrity / accounting consistency.
- **Co znaleziono:** obowiązkowa kronika `opis-budowy-substack/` nie opisywała zamkniętych W0B-REV-06/07/08, historycznych liczników ani bezpiecznego snapshotu. Równocześnie estymator i `UsageTracker` używały Pythonowego banker's `round`, podczas gdy intent i storage używały `Decimal/ROUND_HALF_UP`.
- **Naprawa:** wspólny `app.core.money` realizuje literalny kontrakt `Decimal(str(value)) → quantize(0.000001, ROUND_HALF_UP)`. Przed zapisem i przy porównaniach estimate/reservation/actual każda kwota jest kanoniczna; suma komponentów powstaje przed pojedynczym roundingiem. Usunięto nieosiągalny fresh legacy provider block po return oraz nieużywaną stałą DB-API bez zmiany rootu paid execution.
- **Dowód historyczny:** granice `0.0000004/.5/.6`, `0.0000015`, `0.1234565`, `0.1234575`, cache read/write/web, storage cache, settlement równe oraz ±1 mikro-USD i fake caller → usage → settlement. Historycznie 887 testów, partycje 211+222+229+225; bez API/sieci/browsera/kosztu i bez zapisu do chronionej bazy.
- **Status:** W0B-REV-09 i W0B-REV-10 są technicznie zamknięte; wcześniejszy REJECT z CRITICAL W0B-REV-06 nie jest formalnie zastąpiony przez akceptację. WAVE 0B nadal `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`.

## 2026-07-15 — MAJOR W0B-RR-01: poprawny helper nie obejmował całego przepływu

- **Kategoria:** accounting consistency / review escape.
- **Co znaleziono:** `ROUND_HALF_UP` działał na granicach helpera, ale staged estimate najpierw kwantyzował koszt jednego źródła, potem mnożył publiczny float. Policy Engine, niektóre sumy persisted kwot, pipeline i check CLI także pozwalały, by float uczestniczył w decyzji. Wyniki `0.1 + 0.2` oraz wielokrotności pół-mikro-USD nie miały więc jednego dowodliwego kontraktu end-to-end.
- **Naprawa:** estymator przechowuje raw komponenty jako `Decimal` do jednej końcowej granicy; policy, storage, pipeline i CLI canonicalizują do `Decimal` przed sumą lub porównaniem. Zamiast SQL `SUM(REAL)` storage sumuje kanoniczne wiersze. Usunięto ponadto dwa martwe konstruktory klienta z prywatnych helperów resume; real resume nadal fail-closed, bez konstruktora i bez providera.
- **Dowód:** regresje `2×` i `3×0.0000005`, `0.1+0.2 == 0.3` dla policy, ledgeru i CLI, granice ±1 mikro-USD, estimator, budget, durable provider, execution intent, usage, settlement, storage, restart, migracje, maintenance i CLI resume. Pełny wynik: 894 testy, partycje 213+224+231+226, exact-once coverage i brak BOM; wyłącznie fake callery oraz tymczasowe SQLite.
- **Status:** FIXED technicznie; WAVE 0B pozostaje `CANDIDATE` do krótkiego niezależnego re-review, Etap 1 `BLOCKED`, live API `ZABRONIONE`. Nie wykonano API, sieci, browsera, kosztu ani zapisu do `data/agent.db`.

## 2026-07-15 — P2 checkpointu: rozbieżność inwentarza Git

- **Kategoria:** documentation / release-control accuracy.
- **Co znaleziono:** implementer zadeklarował 71 wpisów Git, lecz niezależny gate zliczył rzeczywisty stan jako 50 modified, 1 deleted i 21 untracked, czyli 72 wpisy.
- **Naprawa:** checkpoint używa wyłącznie inwentarza 72 i rozdziela zatwierdzony zakres do stage od plików chronionych pozostających unstaged.
- **Status:** `APPROVED WITH P2 — READY FOR CHECKPOINT`; nie jest to `CLOSED` przed commitem. Etap 1 `BLOCKED`, live API `ZABRONIONE`; nie wykonano API, sieci, browsera, kosztu ani mutacji `data/agent.db`.

## [2026-07-16] Skonsolidowany Etap 1 — błędne założenia wykryte w kontrpróbach

- **Kontekst:** pierwsza seria 16 nowych testów offline dla Task Scheduler, raportu read-only, migracji kopii i Unicode.
- **Nieudana próba 1:** test launchera szukał składni argumentów z podwójnymi cudzysłowami, podczas gdy prawidłowy PowerShell używał tablicy literałów w pojedynczych. To był błąd asercji, nie entrypointu; test zawężono do faktycznego kanonicznego argument list.
- **Nieudana próba 2:** test „SDK niezaładowane” sprawdzał absolutną nieobecność `anthropic` w `sys.modules`. Kernel bezpieczeństwa pytest może wstępnie zainstalować blokujący moduł testowy, więc warunek dawał false positive. Kontrpróba mierzy teraz wyłącznie nowe moduły załadowane przez import CLI; realny SDK nadal nie jest importowany.
- **Nieudana próba 3:** raport migracyjny opisywał rollback pojedynczym stringiem. Test oczekiwał dowodliwej struktury. Raport zmieniono na jawne `method=full_file_restore`, źródło backupu i zakaz reverse SQL.
- **Nieudana komenda walidacyjna:** pierwszy targeted run wskazał nieistniejący `tests/test_config.py` i zakończył się kodem 1 przed collection. Poprawiono listę plików; właściwy zestaw przeszedł 144/144.
- **Dodatkowa korekta przed testem:** pusty `IdleSettings` w Task Scheduler XML zastąpiono jawnymi `StopOnIdleEnd=false` i `RestartOnIdle=false`, aby nie polegać na niejednoznacznym default/schema parsera Windows.
- **Skutek:** brak API, sieci, SDK, browsera, publikacji i kosztu; brak zapisu/migracji `data/agent.db`. Findingi zamknięto przed pełną regresją.

## [2026-07-16] Rzeczywisty copy-preflight odrzucony przez istniejące sidecary SQLite

- **Próba:** po zielonej migracji syntetycznej bazy 0009 podjęto niezależną próbę utworzenia tymczasowej kopii rzeczywistych bajtów chronionej bazy, bez zamiaru jej podmiany.
- **Wynik:** procedura zatrzymała się przed kopiowaniem i przed otwarciem SQLite: wykryła `data/agent.db-wal` oraz odmówiła kodem 2. Sidecary mają timestamp 2026-07-15, sprzed bieżącego pakietu (`-wal` 0 B, `-shm` 32768 B).
- **Historyczna decyzja defensywna:** nie usunięto sidecarów, nie wykonano checkpointu i nie otwarto produkcyjnej bazy do zapisu. Późniejszy incydent migracyjny dowiódł, że sama obecność pustego WAL i poprawnego SHM nie jest błędem; wymaganie ich nieobecności zostało zastąpione przez ADR-072.
- **Wpływ aktualny:** obowiązuje pełny quiesce, WAL nieobecny lub 0 B, brak journala i brak driftu DB/WAL/SHM. Produkcja po pełnym rollbacku nadal ma 0009; druga migracja wymaga osobnej zgody.

## [2026-07-16] Technicznie poprawna migracja cofnięta przez niezamówiony warunek ABSENT

- **Kategoria:** PROCEDURE / safety false negative.
- **Co się wydarzyło:** kanoniczna migracja produkcyjna zastosowała dokładnie `0010`–`0014`; integrity, FK, ledger, wymagane tabele/triggery, 13 legacy proofs, koszt, historia i profil flag przeszły. Końcowy harness mimo to zwrócił FAIL, ponieważ wymagał `WAL=ABSENT` i `SHM=ABSENT`. Kontrolowany odczyt SQLite pozostawił legalny WAL 0 B i SHM 32768 B.
- **Skutek:** zgodnie z fail-closed kontraktem wykonano pełny restore DB/WAL/SHM. SHA, size i mtime wszystkich trzech plików niezależnie potwierdziły powrót do starego baseline'u i schematu 0009. Chwilowy SHA 0014 nie jest baseline'em.
- **Naprawa:** jeden executor dopuszcza WAL absent/0 B i obecny SHM, blokuje nonzero WAL/journal/process/handle/task oraz każdy drift, a istniejący zestaw DB/WAL/SHM zawsze backupuje i odtwarza jako całość. Produkcja nie jest otwierana przed backupem, rehearsal i ostatnim freshness gate. Jedyny profil flag pochodzi z `app.core.security_flags.SECURITY_FLAG_DEFAULTS`.
- **Dowód:** 14 kontrprób na bazach tymczasowych obejmuje wszystkie warianty sidecarów, drift, Git/confirmation, kanoniczny runner, wymuszony post-failure i bitowy restore. Druga migracja nie została wykonana; nowy baseline nie istnieje; bez API, kosztu, workera, browsera, tasków i Git.

## [2026-07-16] Druga zatwierdzona migracja odrzucona przez pierwszy gate quiesce

- **Kategoria:** CONTROLLED OPERATION / fail-closed before mutation.
- **Próba:** po poprawnym repository i baseline gate uruchomiono wyłącznie zacommitowany `execute-in-place` z literalnym confirmation i nowym workspace poza repozytorium.
- **Wynik:** executor odmówił na pierwszym quiesce: `processes=(17196, 34228), handles=(), tasks=()`. Polecenie zakończyło się przed utworzeniem workspace. Zgłoszone procesy nie istniały już podczas kontroli po zakończeniu.
- **Wpływ:** zero otwarcia produkcyjnej SQLite, backupu, rehearsal, migracji, flag, rollbacku i nowego baseline'u. DB/WAL/SHM pozostały bitowo i metadanymi identyczne ze starym baseline'em.
- **Działanie:** nie obchodzono probe'a, nie tworzono skryptu ad-hoc i nie wykonano ponownej próby. Wynik formalny: `MIGRATION REJECTED BEFORE MUTATION`; kolejne uruchomienie wymaga nowej zgody.

## [2026-07-16] Kontrpróby inline — pierwsze wywołanie utraciło cudzysłowy

- **Objaw:** trzy niezależne skrypty przekazane jako zmienna do `python -c` zostały zinterpretowane przez Windows/PowerShell bez wewnętrznych cudzysłowów i zakończyły się `SyntaxError`; nie uruchomiły logiki aplikacji.
- **Naprawa:** ten sam kod przekazano bez zapisu pliku przez stdin (`$code | python -`). Kontrpróby przeszły: read-only write zablokowany, baza temp byte/metadata unchanged, 5 flag UNKNOWN, maintenance UNKNOWN, 0 nowych importów SDK, systemowy real runner 0 calli, worker+maintenance nie zmieniły flag paid/browser.
- **Wpływ:** wyłącznie błąd quoting harnessu; bez dostępu do produkcyjnej bazy, API, sieci i kosztu.

## [2026-07-16] QP-01 — filtr quiesce wykrył własny proces potomny

- **Kategoria:** MIGRATION TOOLING / local process-filter false positive.
- **Kontekst:** przed ponowną próbą ręczny gate wykazał zero procesów projektu, zero uchwytów DB/WAL/SHM i zero tasków. Właściwy executor został uruchomiony dokładnie raz po ustawieniu poprawnego import path.
- **Wynik:** pierwszy gate executora odmówił z `processes=(15404,), handles=(), tasks=()`.
- **Identyfikacja:** PID `15404`, parent PID `10216`, `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`, creation UTC `2026-07-16T18:59:17.5919140Z`; reason match: command line zawiera resolved project root.
- **Przyczyna lokalna:** `_default_quiesce_probe` uruchamia potomny PowerShell z literalnym `$root` w jego własnej command line. Predykat skanujący `CommandLine.Contains($root)` wyklucza parent Python, lecz nie wyklucza bieżącego procesu potomnego, więc dopasowuje samego siebie.
- **Wcześniejszy błąd uruchomienia:** pierwsze polecenie launchera zakończyło się `ModuleNotFoundError: app` przed importem executora i przed wykonaniem jakiejkolwiek bramki; po ponownym potwierdzeniu czystego gate'u ustawiono repozytorium jako `PYTHONPATH`. Nie była to próba migracyjna ani mutacja.
- **Wpływ:** executor zatrzymał się przed workspace, backupem, rehearsal i otwarciem produkcyjnej SQLite. DB/WAL/SHM pozostały niezmienione, schema nadal `0009`, nowy baseline nie powstał.
- **Działanie:** zgodnie z instrukcją nie zmieniono kodu, nie wykonano pełnego audytu i nie uruchomiono executora ponownie. Finding pozostaje lokalny i otwarty do osobnego zadania.

## [2026-07-16] QP-01 — poprawka kandydacka zweryfikowanej tożsamości helpera

- **Naprawa:** skan PowerShell nie wybiera już blokujących PID-ów. Zwraca pełny snapshot, a Python rejestruje helper przez PID + parent PID + executable + creation time + nonce i dopiero potem klasyfikuje role.
- **Ochrona przed nadmiernym wykluczeniem:** wykluczenie nie dziedziczy się na potomków. Test umieszcza realny marker workera jako niezarejestrowanego potomka helpera i potwierdza STOP. Parent będący maintenance także blokuje.
- **Ochrona przed PID reuse i lingerem:** helper musi powstać w oknie czasowym bieżącego probe'a i zawierać jego nonce; timeout wykonuje terminate/kill z `communicate`. Test realnego helpera potwierdza, że PID po raporcie nie żyje.
- **Klasyfikacja root-only:** niezależny PowerShell z root w command line jest zachowany w diagnostyce jako `PROJECT_ROOT_COMMAND_LINE_ONLY`, ale nie blokuje bez roli aplikacyjnej. Brak pełnej tożsamości daje STOP.
- **Niezmienione blokady:** worker, maintenance, operator CLI, task projektu oraz uchwyt DB/WAL/SHM nadal zatrzymują. Proces bez project root, ale trzymający temp DB, został zatrzymany przez handle gate.
- **Weryfikacja:** dedykowane 13/13; dotychczasowe testy migracji 17/17; collect i pełny suite 1079/1079; partycje 259+264+277+279; exact-once 1079; `compileall` i `git diff --check` poprawne.
- **Wpływ:** tylko kod probe'a, jego serializowana diagnostyka, testy i dokumentacja. Produkcyjna baza nie została otwarta ani zmigrowana; live API i Windows Tasks nie zostały uruchomione.

## [2026-07-16] QP-01 — kontrpróba produkcyjna potwierdziła brak nawrotu

- **Próba:** jedna jawnie zatwierdzona migracja przez ten sam PowerShell → Python entrypoint → helper PowerShell, który wcześniej ujawniał self-detection.
- **Wynik:** trzy kolejne gate'y quiesce miały zero blocking processes, uchwytów i tasków. Helper za każdym razem miał `PROBE_REGISTERED_HELPER_IDENTITY` i nie pojawił się w blocking set.
- **Skutek:** QP-01 nie powtórzył się; migracja zakończyła się sukcesem bez rollbacku. Późniejszy niezależny review zatwierdził QP-01 i trwały stan schema 0014 wynikiem `APPROVE WITH MINOR/P2`; finding nie jest bieżącym blockerem.
- **Bezpieczeństwo:** nie obchodzono gate'ów i nie wykonywano drugiej próby. Brak live API, workera, maintenance, browsera, publikacji, tasków i operacji Git.

## 2026-07-16 — Niezależny review zamknął QP-01 bez usuwania historii odmów

- **Zakres:** reviewer sprawdził migrację `0009→0014`, trwały baseline, QP-01, dokumentację i zakres checkpointu bez modyfikowania repozytorium.
- **Wynik:** `APPROVE WITH MINOR/P2`; QP-01 `APPROVED`; produkcja `VERIFIED / SCHEMA 0014`; nowy baseline `VERIFIED`; brak CRITICAL i MAJOR/P1.
- **Kontrpróby:** 13/13 testów implementera i 23/23 niezależne kontrpróby QP-01; pełna regresja 1079/1079 i cztery partycje exact-once.
- **Historia zachowana:** rollback pierwszej migracji, odrzucone próby, PID 15404 i pierwotny status kandydacki pozostają w rejestrze jako chronologia. Zmieniono wyłącznie aktualny status.
- **Pozostałe P2:** synchronizacja statusów, selektywny `BUILD_LOG` i materializacja pochodzenia review; żaden nie jest findingiem technicznym MAJOR/P1.

### 2026-07-17 — WAVE LA-01: trzy blokery controlled live acceptance i ich naprawa

- **Blokery preflightu:** LA-01-A — wersjonowany cennik był jawnie przykładowy i nieautorytatywny (realny koszt czerpany z `.env`); LA-01-B — brak kanonicznego atomowego otwarcia flag i bezwarunkowego przywrócenia fail-closed (istniał tylko jednoflagowy `set_system_flag`); LA-01-C — canonical CLI utrwalał `max_tokens=3000` bez możliwości zamrożenia niższej wartości.
- **Naprawa:** autorytatywny `config/pricing_profiles.yaml` z `status: approved` + gate `--pricing-profile`; atomowy `apply_security_flag_profile` (jedna transakcja, `kill_switch` ostatni przy otwarciu / pierwszy przy zamknięciu); `--max-tokens` z zamkniętym kontraktem `[256, 8192]` i inwariantem CLI==persisted==provider==projekcja==raport.
- **Ryzyko crashu pomiędzy zmianami flag:** rozwiązane filesystem markerem O_EXCL `runtime/controlled_live_session.json`; niedomknięta sesja wymusza fail-closed przy następnym starcie i jest raportowana przez `operational-report`. Nie tworzy się mechanizmu, który po crashu pozostawia system otwarty bez trwałego śladu.
- **Świadome ograniczenie:** bare `worker --once` wykonałby durable real job, gdyby flagi były już otwarte; jedynym kodem otwierającym flagi paid/worker jest wrapper `controlled-live-once` (zawsze przywraca fail-closed), więc bez wrappera flagi pozostają fail-closed. Zapisano jako P2, nie jako MAJOR.
- **Dowód offline:** 48 nowych testów LA-01; pełny suite **1127/1127**; zero sieci/API/kosztu; produkcyjna baza niezmieniona. Realny controlled live acceptance NADAL niewykonany.

### 2026-07-17 — Niezależny review odrzucił pierwszą LA-01 (`REJECTED — MAJOR`), naprawa LA-01-R1

- **P1-01:** wrapper i dispatcher porównywały za mało pól pricing profile; ten sam ID z inną wersją/ceną/fingerprintem mógł przejść. **Root cause:** autoryzacja profilu została potraktowana jak lookup po ID zamiast niezmiennego kontraktu wykonania.
- **P1-02/P1-04:** status sukcesu nie był ściśle zależny od trwałego raportu, a raport mógł przejąć surowy tekst wyjątku. **Root cause:** finalizacja raportu i markera nie była osobną fail-closed maszyną stanów z sanitizerem.
- **P1-03/P2-03:** tekst `SUCCEEDED` nie dowodził ownership joba/requestu; bare worker mógł wygrać claim. **Root cause:** brak trwałego session fence obejmującego worker execution token.
- **P1-05:** recovery hardcodował brak startu requestu. **Root cause:** recovery nie czytał kanonicznego `provider_attempt` i `request_started_at`.
- **P1-06:** CLI zawierało placeholder zamiast pełnego composition root. **Root cause:** wrapper, worker i entrypoint nie były złożone przez jedną ścieżkę.
- **P2-01/P2-02/P2-04:** marker nie miał kompletnego kontraktu fsync, częściowe flagi można było otwierać pojedynczo, a aktywna dokumentacja opisywała odrzucony stan jako bieżący.
- **Naprawa:** ADR-079: pełny frozen pricing contract i projekcja z approved profile; dispatcher recheck; session/job/request/attempt/token fencing; walidacja durable evidence; sanitizer; raport przed marker clear; recovery bez retry; prawdziwy reopen; O_EXCL+fsync; pełny atomowy profil flag; kanoniczny CLI.
- **Nieudane próby podczas naprawy:** pierwszy focused run ujawnił konflikt `now`+`clock` w nowej metodzie recovery i stare helpery testowe otwierające flagi pojedynczo; pierwsza pełna regresja dała 1149/1151, bo dwa historyczne testy oczekiwały starszego reason textu/ambient estimate. Poprawiono przyczynę recovery i zaktualizowano testy do silniejszego kontraktu bez osłabiania blokad.
- **Końcowa kontrpróba obaliła kompozycję mimo zielonych testów:** capped enqueue nie zawierał `controlled_session`, podczas gdy realny wrapper wymagał jego dokładnej zgodności i nie mógł go dopisać. Skutek był bezpieczny (odmowa przed providerem), ale przyszły acceptance był niewykonalny. Naprawa: jeden deterministyczny helper tożsamości job/session używany przez enqueue i wrapper; test sukcesu przechodzi teraz przez kanoniczny enqueue i `allow_job_creation=false`.
- **Nieudane uruchomienia harnessu/gate:** jedna próba pełnego pytest została przerwana przez omyłkowy timeout 1 s, pierwsza próba partycji użyła nieobsługiwanego `--part/-q` zamiast `--index`, a pierwsze formatowanie pustej listy operacji Git wywołało niekończący kontroli błąd PowerShell `String.Join`. Były to błędy operatorskie bez mutacji danych; poprawne komendy zakończyły się 1151/1151, czterema zielonymi partycjami i czystym repository gate.
- **Dowód końcowy:** 1151/1151 offline; exact-once i cztery partycje 275/282/291/303. Zero realnego SDK/API, sieci, browsera, publikacji i kosztu. Produkcyjna baza nieotwierana do zapisu.

### 2026-07-17 — LA-01-R1 zatwierdzona; pozostaje open P2 sanitizera

- **Wynik review:** `APPROVE WITH MINOR/P2`; wszystkie P1 są zamknięte i finding nie blokuje checkpointu ani controlled live acceptance.
- **P2:** fallback `return str(value)` w `sanitize_report_payload` jest obecnie nieosiągalny dzięki zamkniętej walidacji typów, ale sam nie wykonuje ponownej sanitizacji. Rekomendowana późniejsza poprawka defense-in-depth: `return sanitize_report_payload(str(value))`.
- **Decyzja checkpointu:** nie zmieniać sanitizera poza reviewed diffem; zachować finding jawnie do przyszłej osobno zatwierdzonej poprawki.

### 2026-07-17 — Finalny preflight nie może zamrozić post-enqueue DB SHA bez enqueue

- **Objaw:** wszystkie dane pricing i koszt przechodzą walidację, ale w produkcyjnej bazie nie ma oczekiwanego joba. Realny wrapper ma `allow_job_creation=false`, więc komenda z bieżącym SHA zatrzyma się na `EXPECTED_JOB_MISSING`.
- **Przyczyna:** poprawna sekwencja LA-01-R1 rozdziela kanoniczny enqueue od wrappera. Enqueue zmienia stan SQLite, a wrapper wymaga fingerprintu bazy po tej zmianie. Bieżąca zgoda zakazuje enqueue, więc post-enqueue SHA jest jeszcze niepoznawalny.
- **Bezpieczny skutek:** live preflight ma status `BLOCKED`, nie wykonano gate, enqueue, flag, workera ani providera. Następny zakres musi jawnie zezwolić na enqueue bez API, po czym ponownie zamrozić read-only SHA i dopiero potem dopuścić dokładnie jeden request.
- **Nieudane helpery lokalne:** pierwsza walidacja read-only użyła nieistniejącej kolumny `accounts.display_name`, a kolejna historycznych nazw kluczy flag. Obie zakończyły się przed jakąkolwiek mutacją; po odczycie schematu poprawna walidacja przeszła. To błąd operatorskiego założenia, nie danych.

### 2026-07-17 — Jedyna komenda live zatrzymana przez wewnętrzny `PREFLIGHT_FAILED`

- **Objaw:** zewnętrzny hard preflight przeszedł wszystkie jawne warunki, gate diff był dokładny, lecz jedyna komenda `controlled-live-once` zakończyła się exit 1 i `PREFLIGHT_FAILED` po około dwóch sekundach.
- **Granica skutku:** provider boundary nie został osiągnięty (`provider_request_started=false`), nie powstał attempt, usage, run, research_run ani koszt. Job pozostaje `QUEUED` i nie może być wykonany bez nowej zgody.
- **Recovery:** flags były fail-closed natychmiast po odmowie; gate przywrócono do `False`; marker usunięty po trwałym raporcie. Raport zawiera wyłącznie klasę, zamknięty reason code, bezpieczny komunikat i diagnostic fingerprint.
- **Root cause:** nierozstrzygnięty. Trwały raport celowo nie ujawnia wewnętrznego detalu poza `PREFLIGHT_FAILED`. Nie uruchomiono ponownej próby diagnostycznej, ponieważ właściciel zakazał retry i drugiego uruchomienia.
- **Następny krok:** niezależny offline review ścieżki realnego preflightu i sposobu zachowania bezpiecznego, bardziej szczegółowego closed reason code; bez providera i bez mutacji joba.

### 2026-07-17 — LA-02: observer effect launchera i utracona diagnostyka — FIXED / APPROVED WITH MINOR/P2

- **Co miało działać:** canonical quiescence miał ignorować wyłącznie własny legalny launcher controlled-live, a przy prawdziwym blockerze raportować dokładny closed reason.
- **Co nie zadziałało:** dalszy PowerShell/cmd/bash przodek z literalnym `-m app.main controlled-live-once` dostał `APP_ROLE_OPERATOR_CLI → BLOCKING_APPLICATION_PROCESS → PROCESSES_PRESENT`. `default_quiescence_probe` usunął `process_diagnostics`, a `_safe_error` zastąpił inner code ogólnym `PREFLIGHT_FAILED`.
- **Dlaczego:** wyjątek opierał się na jednym bezpośrednim parent PID i allowliście executable (`powershell.exe`/`pwsh.exe`), nie na udowodnionym ancestry. Granica raportowa nie przenosiła typowanej diagnostyki wyjątku.
- **Jak naprawiono:** dokładny PID/PPID chain, kompletna identity, zgodny jednoznaczny entrypoint i monotoniczny creation time; tylko udowodnieni przodkowie są nonblocking. Inner reason, invariant/check order, blocking PIDs i redacted identities są trwałe. Dodano canonical standalone PASS/STOP bez storage/providera/gate'u.
- **Ile prób:** jedna wcześniej autoryzowana próba live (bez providera) ujawniła problem; zero ponownych prób live. Naprawa i wszystkie testy wyłącznie offline/temp DB.
- **Czego się nauczyliśmy:** samo fail-closed chroni skutki, ale nie wystarcza do operacyjnej diagnozy. Wyjątek procesu musi wynikać z relacji tożsamości, nie z nazwy shella; zewnętrzny status i wewnętrzny reason są odrębnymi polami.
- **Status:** root cause `CLOSED`; niezależny review wydał `APPROVE WITH MINOR/P2`; provider request nadal niewykonany, a druga próba nieautoryzowana.

### 2026-07-17 — Lokalne awarie harnessu podczas LA-02 — FIXED

- **Co miało działać:** pełny pytest i cztery partycje exact-once miały przejść jednym przebiegiem.
- **Co nie zadziałało:** pierwsze pełne `pytest` zostało przerwane przez omyłkowy 1-sekundowy timeout narzędzia. Pierwszy przebieg partycji 2 zatrzymał standalone PASS, bo automatyczny node ID parametryzowanego testu zawierał literalne `-m app.main ...`; długi command line parent runnera wyglądał dla fail-closed probe'a jak niezależny operator. Pierwszy końcowy helper immutable użył nieistniejącej kolumny `reconciliation_events.job_id`.
- **Dlaczego:** błąd operatorskiego limitu, dane testowe umieszczone przez pytest w nazwie procesu oraz błędne założenie o schemacie kolumny; nie były to wady produkcyjnego ancestry ani trwałych danych.
- **Jak naprawiono:** ponowiono pełny suite z właściwym limitem; parametry dostały neutralne jawne `ids`, bez osłabiania klasyfikatora; schemat odczytano przez immutable `PRAGMA table_info`, po czym poprawne zapytanie użyło `request_id`. Partycja 2, pełny subprocess standalone i finalny immutable gate przeszły.
- **Ile prób:** jeden przerwany full suite, jeden odrzucony przebieg partycji i jeden odrzucony helper read-only; wszystkie bez sieci, API i mutacji produkcji.
- **Checkpoint — read-only pomyłki operatorskie:** pierwsze wywołanie `operational-report` dostało nieobsługiwany argument `--db-path` i zakończyło się błędem parsera bez otwarcia bazy. Poprawne wywołanie bez argumentu zwróciło oczekiwany niezerowy `DEGRADED_UNKNOWN`, ponieważ schema 0014 nie utrwala timestampu maintenance; pozostałe pola raportu były poprawne. Nie wykonano retry live ani mutacji.
- **Czego się nauczyliśmy:** test quiescence obserwuje także harness. Nazwy przypadków są częścią środowiska procesu i nie powinny imitować realnych entrypointów, jeśli przypadek testuje czysty stan.
- **Status:** FIXED.

### 2026-07-17 — Mtime produkcyjnego SHM różni się między najwcześniejszym a końcowym gate'em — OPEN OBSERVATION

- **Co miało działać:** końcowy gate miał odtworzyć SHA/size/mtime DB/WAL/SHM z wejścia LA-02.
- **Co zaobserwowano:** main DB i WAL są identyczne w SHA/size/mtime. SHM ma identyczny SHA `FD4C9F…9389EB` i rozmiar 32768 B, ale najwcześniej zapisany mtime `07:55:01Z` różni się od końcowego `08:02:20Z`.
- **Granica dowodu:** canonical standalone zmierzył wszystkie trzy pliki przed/po i zwrócił `database_unchanged=true`; późniejszy odczyt SQLite `mode=ro&immutable=1` również zachował wszystkie SHA/size/mtime. Żaden z tych dwóch końcowych gate'ów nie spowodował driftu. Nie ustalono procesu, który wcześniej zmienił wyłącznie metadane SHM; nie wolno przypisywać przyczyny bez dowodu.
- **Wpływ:** durable main DB pozostaje SHA `5FF5DB…97B78`, schema 0014; WAL pusty; zawartość SHM byte-identical; job/attempts/usage/flags bez zmian. Obserwacja nie autoryzuje retry i powinna być widoczna reviewerowi.
- **Status:** OPEN OBSERVATION — metadata only; nie blokuje zatwierdzonego checkpointu LA-02 i nie autoryzuje live.
- **Checkpoint LA-02:** pierwszy standalone gate widział SHM mtime `2026-07-17T09:10:44.1065777Z`; po read-only kontrolach późniejszy gate widział `2026-07-17T09:26:57.3374625Z`. Interweniujące `operational-report` było jedynym poleceniem otwierającym produkcyjną SQLite i użyło `mode=ro`/`query_only`, ale nie przypisujemy mu przyczyny bez dowodu. DB, WAL i SHM zachowały dokładne SHA/rozmiary; późniejszy standalone przed/po oraz immutable query nie wykazały dalszego driftu. To nie jest zapis danych ani podstawa do retry.

### 2026-07-17 — P2-2: niezależny proces z pełnym tekstem komendy może wywołać false STOP — OPEN OBSERVATION

- **Obserwacja:** terminal, edytor lub shell niezwiązany z legalnym ancestry może mieć w command line pełny tekst planowanej komendy `controlled-live-once`. Klasyfikator nie ma dowodu, że to wyłącznie tekst pomocniczy, więc `PROCESSES_PRESENT` jest bezpiecznym wynikiem fail-closed.
- **Decyzja checkpointu:** nie zmieniać klasyfikatora. Przed przyszłym live zamknąć takie procesy i uruchomić standalone quiescence check z dokładnie tego samego launchera.
- **Warunek STOP:** każde `PROCESSES_PRESENT`, `STOP`, niepełna identity lub drift DB/WAL/SHM kończy operację. Live nie jest ponawiane bez nowej jawnej autoryzacji właściciela.
- **Status:** `OPEN OBSERVATION / DOCUMENTED`; nie jest blockerem checkpointu LA-02.

### 2026-07-17 — `DB_HANDLES_PRESENT`: wrapper wykrywał własne storage — FIXED

- **Co miało działać:** zero-sharing probe miał blokować obce uchwyty DB/WAL/SHM przed jednorazowym provider requestem.
- **Co nie działało:** `app.main` otwierał główne `SqliteStorage` przed `run_controlled_live_once`; `CreateFileW(..., dwShareMode=0)` deterministycznie widział własne połączenie jako blokadę.
- **Root cause:** błędna kolejność composition rootu (`open resource → probe → self-block`), nie wada Windows probe'a.
- **Naprawa:** wspólny standalone/wrapper probe działa pre-storage; po PASS wynik jest zamrożony, storage otwierane raz, a trwały stan rewalidowany przed markerem/flagami/providerem. Obce read-only/writable SQLite i WAL/SHM nadal STOP.
- **Dowód:** focused 71/71, full 1181/1181, fake CLI PASS, standalone PASS, test driftu i contention. Provider nie został użyty podczas diagnozy/naprawy.
- **Status:** false blocker `CLOSED`.

### 2026-07-17 — Pierwszy realny request: HTTP 200, ale niepoprawny JSON — TERMINAL / NO RETRY

- **Objaw:** jedyna autoryzowana komenda doszła do Anthropic i otrzymała HTTP 200, po czym pipeline zgłosił `ResearchParseError` (`Expecting property name enclosed in double quotes`).
- **Skutek trwały:** dokładnie jeden attempt #1, `REQUEST_STARTED`, jedno usage, `SETTLED=0.053182 USD`; job/run/research_run `FAILED`, brak Research Card, zero attemptu #2 i reconciliation.
- **Ochrona:** wrapper zwrócił `VALIDATION_FAILED_FAIL_CLOSED`; restore/reopen i marker clear potwierdzone; gate `False`, flags fail-closed. Nie wykonano ponowienia ani lokalnego „naprawiania” odpowiedzi poza durable lifecycle.
- **Status:** znany terminalny failure treści, nie false preflight blocker. Kolejny request wymaga nowej autoryzacji.

### 2026-07-17 — Pierwszy post-live helper read-only użył nieistniejących kolumn — FIXED

- **Objaw:** helper weryfikacyjny odpytał `research_runs.finished_at`, `provider_attempts.final_event` i `model_usage.web_searches`, których schema 0014 nie zawiera.
- **Skutek:** wyłącznie `sqlite3.OperationalError` w połączeniu `mode=ro&immutable=1`; bez mutacji, providera i retry.
- **Naprawa:** odczytano `PRAGMA table_info` i powtórzono immutable query z właściwymi kolumnami (`updated_at`, stan attemptu, `web_search_requests`).
- **Status:** błąd operatorskiego helpera `FIXED`; trwały wynik requestu bez zmian.

### 2026-07-17 — Historyczny single request nie zachował raw ani stop reason — EVIDENCE GAP CLOSED FOR FUTURE

- **Objaw:** durable ledger zna dokładne miejsce błędu parsera (`line 29 column 6 char 4376`), ale nie istnieje prywatny plik diagnostyczny dla runu `f74165fb-9677-4e6d-abfd-09607bd4dd78`.
- **Przyczyna:** stara `_default_caller` odbierała trzy elementy z `_call_anthropic`, po czym jawnie odrzucała `_stop_reason` i zwracała tylko text+usage. `_run_with_retry_and_parse` nie dopinał raw/stop reason do wyjątku, a single pipeline nie wywoływał `_record_diagnostics`.
- **Granica wiedzy:** `Expecting property name enclosed in double quotes` dowodzi błędu składni w określonej pozycji. Bez znaku i otoczenia nie rozstrzyga prose, fence, truncation, niezamknięcia ani innej klasy. Każde bardziej szczegółowe wyjaśnienie byłoby zgadywaniem.
- **Naprawa:** przyszła single response zachowuje raw/stop reason w tym samym jednym callu; pipeline po kanonicznej terminalizacji zapisuje prywatne `SINGLE_raw_response.txt` best-effort. `max_tokens` daje typowaną truncation wyłącznie przy jawnym stop reason.
- **Status:** historycznego evidence nie da się odtworzyć; luka jest zamknięta dla przyszłych odpowiedzi. Nie wykonano requestu diagnostycznego ani retry.

### 2026-07-17 — Deterministyczny session report nadpisywał poprzedni invocation — FIXED

- **Objaw:** ten sam operation key dawał ten sam `session_id` i tę samą ścieżkę `<session_id>.json`; nowszy wynik LA-03 zastąpił wcześniejszy raport preflight.
- **Przyczyna:** logiczna tożsamość sesji była równocześnie użyta jako tożsamość fizycznego invocation reportu.
- **Naprawa:** report key zawiera stabilny session, attempt discriminator, UTC timestamp i nonce. Provisional/final jednego invocation nadal promują jeden plik atomowo; osobne invocation tworzą osobne pliki. Marker zachowuje report key, a recovery wskazuje poprzedni.
- **Dowód:** test pierwszego `PREFLIGHT_FAILED` i drugiego terminalnego invocation dla tego samego operation key zachowuje dwa raporty; recovery tworzy trzeci odrębny report i wiąże prior key.
- **Status:** `FIXED`; istniejącego historycznego pliku nie przepisano ani nie sfabrykowano utraconej wersji.

### 2026-07-17 — Pierwsza pełna regresja P2: jedna stara fixture nie spełniała nowego schema contract — FIXED

- **Objaw:** full run zakończył się 1199/1200; `test_pipeline_infers_retry_count_from_anthropic_client` podał źródła bez jawnych `author_or_org` i `published_at`.
- **Przyczyna:** fixture opisywała wcześniejszy parser z defaultami, a nowy zamknięty kontrakt wymaga wszystkich kluczy i jawnego JSON null.
- **Naprawa:** uzupełniono wyłącznie fixture; nie osłabiono parsera. Drugi full run przeszedł 1200/1200, a cztery partycje `290+293+304+313` były zielone.
- **Dodatkowa nieudana kontrpróba:** pierwsze 14 przypadków użyło produkcyjnej klasy klienta bez durable attempt context i wszystkie poprawnie zatrzymały się przed fake callerem. Test dostał jawny test-local offline seam, bez zmiany production guard.
- **Status:** `FIXED`; zero sieci, API, kosztu i mutacji produkcji.

### 2026-07-17 — Końcowy helper integralności kopii użył historycznej nazwy kolumny flag — FIXED

- **Objaw:** po 210/210 focused tests, `compileall`, `diff --check` i zgodnym produkcyjnym hashu helper kopii rzucił `sqlite3.OperationalError: no such column: value`.
- **Przyczyna:** `system_flags` przechowuje JSON w `value_json`; helper założył skróconą nazwę `value` bez uprzedniego odczytu schematu.
- **Granica skutku:** błąd nastąpił na pliku tymczasowym po skopiowaniu bazy. Produkcyjny DB hash pozostał `5BEA9E…C6D10`, WAL/SHM nie istniały; nie było API, providera ani mutacji.
- **Naprawa:** immutable `PRAGMA table_info(system_flags)` potwierdziło kolumny; helper użył `json.loads(value_json)`. Powtórzenie: `integrity_check=ok`, `foreign_key_check=[]`, fail-closed flags, jeden terminalny job/attempt/usage, zero kart i identyczny hash kopii/produkcji.
- **Status:** `FIXED`; to błąd operatorskiego helpera, nie schematu ani danych.

### 2026-07-17 — Końcowy audyt PowerShell zatrzymał się na ostrzeżeniu LF→CRLF — FIXED

- **Objaw:** pierwsza zbiorcza komenda audytowa miała `$ErrorActionPreference = 'Stop'`; `git diff --check` wypisał na stderr wyłącznie ostrzeżenia o przyszłej konwersji LF→CRLF, które PowerShell potraktował jako wyjątek i przerwał helper.
- **Granica skutku:** Git zwrócił później kod `0`; nie stwierdzono błędu whitespace, nie zmieniono plików, stagingu ani historii Git. Nie było sieci, API, providera ani otwarcia produkcyjnej SQLite.
- **Naprawa:** powtórzono te same kontrole bez przerywania na samym stderr i oceniono jawne exit codes. Wynik: `git diff --check = 0`, staging pusty, brak aktywnej operacji Git, branch i HEAD bez zmian; hash produkcyjnej bazy nadal `5BEA9E…C6D10`, WAL/SHM nie istnieją.
- **Status:** `FIXED`; ostrzeżenia line-ending pozostają informacyjne.

### 2026-07-17 — Pierwszy review pakietu P2: `REJECT — MAJOR` — NIA-P2-RV-01…05

- **RV-01:** legalny 400-cyfrowy integer dochodził do `float(value)` i rzucał `OverflowError` poza typowaną ścieżką; po jednym `REQUEST_STARTED` brakowało usage/settlement, a fallback eskalował lifecycle.
- **RV-02:** prywatny `SINGLE_raw_response.txt` utrwalał raw verbatim, więc mógł zachować klucz, bearer, nazwany sekret, headers i nested exception.
- **RV-03:** fixture wrappera miała stały zegar, lecz enqueue używał bieżącego czasu systemowego; po przekroczeniu daty fixture job stawał się nieclaimable.
- **RV-04:** bare fence był przyjmowany; object+scalar trafiał do prose zamiast `multiple_json_values`; root scalar był prose zamiast schema.
- **RV-05:** niższe aktywne sekcje stanu projektu nadal przedstawiały pre-live baseline, koszt i brak wykonania acceptance jako stan bieżący.
- **Naprawa:** wyłącznie zamknięty zakres ADR-087; bez zmian schedulera, workera, storage, recovery, reconciliation, pricingu, migracji i ledgeru poza minimalnym spięciem wymaganych ścieżek.
- **Status:** technicznie naprawione i oczekujące niezależnego review; nie jest to `APPROVE` ani zamknięcie Etapu 1.

### 2026-07-17 — Iteracyjne regresje naprawy NIA-P2-RV — FIXED

- **Focused diagnostic:** pierwsza asercja wymagała pozostawienia tekstu `api_key=[REDACTED]`, podczas gdy kanoniczny sanitizer poprawnie usunął całe nazwane pole. Skorygowano test do właściwego wymagania: brak sekretu i brak wrażliwego pola.
- **Clock fixture:** pierwsza asercja porównywała aware UTC z naiwym UTC odczytanym przez istniejący adapter SQLite. Zmieniono wyłącznie reprezentację oczekiwaną; jawny czas i semantyka claimability pozostały bez zmian.
- **Pierwszy full suite po wspólnym sanitizerze:** cztery istniejące testy audit formattera nie znalazły bezpiecznych etykiet `authorization/api_key/token`, bo sanitizer diagnostyczny usuwał całe pola. Dodano w kanonicznej funkcji jawny tryb `preserve_safe_labels=True` używany tylko przez ustalony format audit error; wartości nadal są `[REDACTED]`, diagnostics/report używają trybu silniejszego.
- **Dowód po korekcie:** testy audit formattera 9/9, relevant diagnostic 21/21, focused parser/diagnostics 102/102, durable provider 94/94, controlled-live+LA-02 77/77 i ledger/usage/reconciliation 226/226.
- **Skutek:** wszystkie nieudane próby były offline na fake/temp DB; zero API, sieci, kosztu i mutacji produkcyjnej SQLite.

### 2026-07-17 — Pierwszy samodzielny counterprobe nie wskazał chronionej DB — FIXED

- **Objaw:** świeży proces z `NIA_TEST_MODE=1` zatrzymał się przed otwarciem tymczasowej SQLite komunikatem `NIA_TEST_MODE requires NIA_TEST_PROTECTED_DB`.
- **Przyczyna:** kontrpróba nie przekazała kernelowi jawnej kanonicznej ścieżki bazy, której ma zabraniać. Kernel zadziałał fail-closed; produkcyjna i tymczasowa baza nie zostały otwarte.
- **Naprawa:** powtórzono ten sam samodzielny skrypt z `NIA_TEST_PROTECTED_DB` wskazującym `data/agent.db`. Pięć kontrprób przeszło na temp DB/fake: huge integer→schema, pięć klas sekretów→redacted, jawny clock mimo symulowanego systemowego 2035→brak `JOB_NOT_CLAIMABLE`, object+true→multiple, bare fence→invalid fence.
- **Status:** `FIXED`; jest to dowód działania testowego safety kernela, nie finding produkcyjny.

### 2026-07-17 — Pierwszy końcowy audit copy użył nieistniejącego `provider_attempts.created_at` — FIXED

- **Objaw:** po zgodnym hashu kopii immutable helper wykonał `integrity_check`, lecz zatrzymał się przy porządkowaniu attemptów po kolumnie `created_at`, której tabela nie ma.
- **Granica skutku:** błąd wystąpił wyłącznie na kopii w zweryfikowanym katalogu tymczasowym. Kopia przed/po i źródło miały SHA `5BEA9E…C6D10`; WAL/SHM/journal nie istniały, a temp został usunięty.
- **Naprawa:** helper użył stabilnego lokalnego `rowid` wyłącznie do prezentacji. Powtórzenie dało `integrity_check=ok`, pusty FK check, 14 migracji, jeden job/run/research_run `FAILED`, jeden attempt `SETTLED`, brak karty/rezerwacji/lease i flags fail-closed.
- **Doprecyzowanie stanu:** tabela ma 19 wierszy `model_usage` łącznie, z czego 14 realnych (`dry_run=0`) sumuje się do `0.737762 USD`; aktywna linia `CURRENT_PROJECT_STATE.md` została skorygowana bez mutacji DB.

### 2026-07-17 — Controlled-live zablokowany przez zamknięty real gate — FAIL-CLOSED / NO REQUEST

- **Objaw:** wszystkie parametry, pricing, budżet, DB fingerprint, quiescence i durable stan przeszły read-only preflight, ale kanoniczny entrypoint nadal przekazuje `allow_execution=False` z `REAL_CONTROLLED_LIVE_ENABLED = False`.
- **Przyczyna:** właściciel zabronił zmian kodu. Obecna architektura nie ma oddzielnego, niekodowego runtime switcha dla real controlled-live; chwilowe przełączenie stałej byłoby zmianą kodu.
- **Bezpieczny skutek:** zatrzymanie przed enqueue i provider boundary. Provider calls/attempts/usage/koszt nowy = `0`; marker i nowy operator report nie powstały; DB i fail-closed flags pozostały niezmienione.
- **Błędy helperów:** pierwszy raport in-memory użył nieistniejącej metody `DurableResearchExecutionIntent.build`, drugi próbował serializować metodę `PricingProfile.fingerprint` zamiast jej wynik. Oba błędy były read-only, przed mutacją i bez SDK/API; trzecia, poprawiona próba immutable zakończyła się powodzeniem.
- **Sidecary po raporcie read-only:** `operational-report` uruchomiony po pierwszym quiescence `PASS` pozostawił `agent.db-wal` 0 B i `agent.db-shm` 32768 B z tym samym timestampem; główna DB zachowała SHA/rozmiar/mtime. Drugi canonical probe dał `PASS`, zero locked paths i zero project processes. Po dokładnej weryfikacji ścieżek oraz niezmiennych rozmiarów usunięto wyłącznie oba odtwarzalne sidecary; głównej DB nie usuwano ani nie zapisywano.
- **Werdykt:** `BLOCKED — LIVE PREFLIGHT DRIFT`; brak retry i brak automatycznego resume.

### 2026-07-17 19:18 UTC — Drugi controlled-live: HTTP 200 z `stop_reason=max_tokens` — TERMINAL FAILED

- **Objaw:** jedyny request osiągnął provider boundary i otrzymał HTTP 200, ale zakończył generację przy `max_tokens=1500`. Parser poprawnie zgłosił `ResearchTruncatedError(stop_reason=max_tokens)` zamiast próbować sparsować niepełną odpowiedź.
- **Lifecycle:** dokładnie jeden attempt i jedno usage; `REQUEST_STARTED→SETTLED`, koszt `0.060078 USD`; job/run/research_run terminalnie `FAILED`; brak Research Card, retry, repair calla, attemptu #2 i reconciliation.
- **Cleanup:** gate i wszystkie flags fail-closed, marker usunięty, lease/rezerwacja zwolnione, DB bez sidecarów.
- **Obserwacja diagnostyczna:** po truncation nie znaleziono nowego pliku w oczekiwanym `data/debug/research/<run_id>/`; nie wykonywano naprawy ani kolejnego requestu, zgodnie z zakazem P2 i retry.

### 2026-07-17 19:44 UTC — Controlled-live 3000: kompletna odpowiedź odrzucona przez schema — TERMINAL FAILED

- **Objaw:** jedyny request osiągnął provider boundary i otrzymał HTTP 200 z `stop_reason=end_turn`. Limit `max_tokens=3000` nie uciął odpowiedzi, ale walidator odrzucił `sources[0].supports_claim`, ponieważ kontrakt wymaga `string_or_null`.
- **Lifecycle:** dokładnie jeden attempt i jedno usage; `REQUEST_STARTED→SETTLED`, koszt `0.077160 USD`; job/run/research_run terminalnie `FAILED`; brak Research Card, retry, repair calla, attemptu #2 i reconciliation.
- **Cleanup:** gate i wszystkie flags fail-closed, marker usunięty, lease/rezerwacja zwolnione, DB bez WAL/SHM/journal.
- **Granica:** nie zmieniano parsera, promptu, schema ani limitów po wyniku i nie wykonywano drugiego requestu. Root cause tej próby jest kontraktem typu pola odpowiedzi, a nie truncation.
- **Nieudane helpery lokalne przed requestem:** dwa odczyty kontraktu identity błędnie założyły obiekt atrybutowy i klucz `request_id` zamiast słownika z `expected_request_id`; helper snapshotu importował nieistniejący `app.config`, a pierwszy PowerShellowy odczyt SHA użył niedostępnej metody `SHA256.HashData`. Wszystkie zakończyły się przed enqueue/providerem albo były wyłącznie read-only; poprawione odczyty nie utworzyły dodatkowej identity trwałej, attemptu ani requestu.

### 2026-07-17 — Rozwiązanie (kandydat) root cause `supports_claim` — PROMPT TYPE CONTRACT

- **Potwierdzenie z trwałej diagnostyki:** sanitizowany `SINGLE_raw_response.txt` runu pokazał `"supports_claim": true` (boolean) dla każdego źródła; kontrakt domenowy i schema to `string | null`. Wada leżała w promptcie (brak typu pola + myląca nazwa), nie w walidatorze.
- **Naprawa (tylko prompt, `_default_caller`):** `supports_claim` musi być JSON stringiem albo null (nigdy boolean/array/object/number), z przykładem; utwardzono też tę samą klasę dla `citable_numbers` (lista stringów, nie liczby). Schema, parser-walidator, lifecycle, settlement, retry, pricing i migracje bez zmian.
- **Weryfikacja:** +13 testów typu pola; pełny suite 1248, partycje 298+299+317+334; fake E2E odtwarza dokładnie ten błąd (boolean→terminalny `FAILED` z settlementem) i potwierdza sukces (string→Research Card). Zero requestu/sieci/kosztu; produkcyjna DB bajt-identyczna.
- **Status:** `CANDIDATE COMPLETE — AWAITING NARROW REVIEW`; kolejny live wymaga osobnej decyzji właściciela.

### 2026-07-17 20:46 UTC — Live po naprawie kontraktu: truncation przy 3000 — TERMINAL FAILED

- **Objaw:** jedyny request po niezależnym `APPROVE` naprawy promptu otrzymał HTTP 200, ale zakończył `stop_reason=max_tokens` przy `max_tokens=3000`. Ledger zapisał 16381 input, 3155 output i jeden web search.
- **Wynik parsera/schema:** typowany `ResearchTruncatedError`; parser nie próbował interpretować uciętego JSON, a schema validation nie została osiągnięta. Nie ma dowodu live ani sukcesu, ani porażki poprawionych typów `supports_claim`/`citable_numbers`.
- **Lifecycle:** dokładnie jeden attempt i jedno usage; `REQUEST_STARTED→SETTLED`, koszt `0.074312 USD`; job/run/research_run terminalnie `FAILED`; brak Research Card, retry, repair calla, attemptu #2 i reconciliation.
- **Cleanup:** gate i flags fail-closed, marker usunięty, lease/rezerwacja zwolnione, DB bez sidecarów; zaakceptowany wcześniejszy diff kodu/testów zachowany.
- **Nieudany helper read-only:** zbiorczy preflight `rg` zwrócił kod 1 przez nieistniejącą ścieżkę `app/research/dispatcher.py`; pozostałe odczyty zostały powtórzone poprawnie. Nie otworzył gate, nie zmienił DB i nie wykonał requestu.

### 2026-07-18 — Root cause zmiennego rozmiaru odpowiedzi — OUTPUT-SIZE CONTRACT (kandydat)

- **Rozróżnienie trzech żywych porażek:** (1) run `8bcf15e4`, `max_tokens=1500` → truncation (usage output 1667 > 1500); (2) run `65841541`, `max_tokens=3000` → `end_turn`, kompletny JSON 6697 znaków, terminalny schema failure `supports_claim` (kontrakt typu, nie rozmiar); (3) run `08aa35eb`, `max_tokens=3000` → truncation (usage output 3155 > 3000, widoczny JSON tylko 4038 znaków, ucięty przed `sources`). Porażka #2 ma inną przyczynę niż #1/#3; naprawa typu z #2 nie mogła zapobiec #3.
- **Fakt 1 (semantyka SDK, korekta diagnostyki):** `max_tokens` ogranicza KAŻDY segment generacji osobno, a `usage.output_tokens` to suma segmentów ("inclusive, authoritative total used for billing" — docstring lokalnego SDK). Web search dodaje segment przed wyszukiwaniem (~155–167 tokenów zmierzone w obu uciętych próbach), więc 1667>1500 i 3155>3000 są ZGODNE z kontraktem SDK — to nie jest błąd rozliczeń.
- **Fakt 2 (właściwy root cause):** zafakturowany output zawiera niewidoczne tokeny (wewnętrzne rozumowanie — `usage.output_tokens_details.thinking_tokens` w SDK — oraz bloki tool-use/cytowań), które liczą się do limitu segmentu, ale nie trafiają do `text`. Zmierzone: próba #2 ≈ 715–1237 tokenów narzutu; próba #3 ≈ 1963–2232 tokenów narzutu w segmencie finalnym przy IDENTYCZNYM promptcie. Ta wariancja sprawia, że stały limit 3000 nie może dawać stabilnego zakończenia — czasem mieści JSON + narzut (#2), a czasem nie (#3).
- **Naprawa (fala 2026-07-18):** jawny kontrakt rozmiaru `app/research/output_contract.py` (budżet liczności i długości każdego pola + sufit całej odpowiedzi 16000 znaków), prompt v3 z jawnym limitem dla każdego pola i wymogiem kompaktowego jednoliniowego JSON, deterministyczna walidacja fail-closed (`ResearchCardSizeContractError`, podklasa `ResearchSchemaError`: usage/settlement zachowane, terminalny `FAILED`, zero retry, zero cichego obcinania), `prompt_contract_version` v2→v3 (stare intenty fail-closed nieobsługiwane), pomiar `thinking_tokens` w Usage/diagnostyce oraz profil tokenowy `RESEARCH_CARD_MAX_TOKENS=6000` = 3198 (payload na granicach, konserwatywnie /3.5 znaka na token) + 2300 (najgorszy zmierzony narzut) + 502 marginesu. Kandydaci 3500/4000 są mniejsze niż suma dwóch realnych obserwacji; 5000 daje ujemny margines (3198+2300=5498).
- **Status:** `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`; live API pozostaje `FORBIDDEN UNTIL REVIEW APPROVE`.

## 2026-07-18 — Pozytywny live kontraktu rozmiaru; redakcyjne odrzucenie słabych źródeł

- **Nie jest awarią wykonania:** jedyny request zakończył się `end_turn`, przeszedł raw-size, JSON, schema, limity pól i injection guard; lifecycle `DONE/SUCCESS/COMPLETE`, karta `id=3` istnieje, attempt jest `SETTLED`.
- **Odrębny wynik redakcyjny:** `publication_recommendation=REJECT`, `reason=WEAK_SOURCES`. System poprawnie zachował kartę badawczą, ale nie rekomenduje jej publikacji; nie wolno utożsamiać sukcesu technicznego z jakością źródeł.
- **Helpery read-only:** import błędnej nazwy stałej `OUTPUT_TOKEN_MARGIN` i zapytanie o nieistniejącą kolumnę `research_sources.research_card_id` zakończyły pomocnicze odczyty; poprawiono je przez użycie właściwej stałej i immutable introspection. Jedna komenda `rg` zwróciła exit 1 z powodu braku dopasowania. Żaden przypadek nie dotknął provider boundary, nie zmienił DB i nie wywołał retry.
- **Granica:** zero attemptu #2, repair/fallback/verification i automatycznego resume; kolejne live wymaga nowej decyzji właściciela.

## 2026-07-18 — PR #1: crash po `SETTLED` nie miał legalnej naprawy lifecycle

- **Finding PR1-MAJ-001:** finansowy attempt był już poprawnie `SETTLED`, lecz crash przed terminalizacją job/run/research_run pozostawiał wykonanie zawieszone. Reaper słusznie nie cofał settlementu, ale nie miał odrębnego zdarzenia do odzyskania fazy wykonawczej.
- **Naprawa:** `EXECUTION_RECOVERY` w migracji `0015` rozdziela niezmienny finał finansowy od terminalizacji lifecycle. Warunki są egzekwowane zarówno w repozytorium, jak i przez triggery SQLite.
- **Nieudana kontrpróba implementacyjna:** pierwsza wersja walidacji cache traktowała `PENDING` research_run tak, jakby musiał już zawierać koszt terminalny. Test poprawnego crash-window wykrył to zaostrzenie; kontrakt skorygowano tak, aby preterminalny cache wynosił zero, a terminalny — dokładny koszt kanoniczny.
- **Regresja kompatybilności komunikatu:** pierwszy pełny suite miał jeden failure, bo nowy trigger zwracał bardziej precyzyjny tekst bez oczekiwanego tokenu `NEEDS_RECONCILIATION`. Komunikat uzupełniono bez osłabienia warunku; kolejny pełny suite przeszedł `1311/1311`.
- **Pozostałe findings:** PR1-MAJ-002 zdegradowano decyzją właściciela do cleanupu final tree bez przepisywania historii; PR1-MAJ-003 zamknięto przez przywrócenie jednego kanonicznego podręcznika. Żadne z tych działań nie dotknęło provider boundary ani produkcyjnej DB.

## 2026-07-18 — PR1-MAJ-005: runtime sam stosował migrację `0015` — FIXED / CANDIDATE

- **Finding i przyczyna:** fabryka runtime `SqliteStorage.open()` bezwarunkowo wykonywała `apply_migrations()`. Brakowało granicy autoryzacji między otwarciem aplikacji a zmianą schematu, więc baza `0014` była mutowana przed możliwością kontrolowanej odmowy.
- **Naprawa:** immutable exact-schema preflight przed writable connection, typowany STOP na wersji innej niż `0015`, brak tworzenia pliku/ledgera/sidecarów oraz osobne API/skrypt migracyjny exact `0014→0015`. Historyczny executor Etapu 1 pozostaje na `0014`.
- **Nieudane próby implementacyjne:** pierwszy targeted run ujawnił, że główna fixture i dwa QA tworzyły temp DB przez dawny efekt uboczny `open()`; po jawnej inicjalizacji pierwszy full suite wskazał jeszcze 10 takich setupów testowych. Poprawiono wyłącznie setupy, bez przywracania auto-migracji. Pierwszy helper dowodu został poprawnie zatrzymany przez safety kernel, bo nie aktywował wymaganej ochrony chronionej DB; ponowiono go z poprawnym kernelem wyłącznie na temp DB. Pierwsza funkcja zliczająca użyła zwykłego read-only SQLite i sama mogła utworzyć sidecary; zastąpiono ją `mode=ro&immutable=1`.
- **Nieudana próba partycji:** cztery partycje uruchomione równolegle wzajemnie pojawiły się w teście quiescence jako `PROCESSES_PRESENT`, przez co dwa przypadki oczekujące `DB_HANDLES_PRESENT` w jednej partycji prawidłowo odmówiły innym kodem. To błąd operatorskiej orkiestracji, nie produktu. Bez zmiany testu lub zabezpieczenia wszystkie partycje powtórzono sekwencyjnie i przeszły `318+322+339+349`.
- **Status:** `FIXED — CANDIDATE FOR INDEPENDENT RE-REVIEW`; produkcja nadal `0014`, migracja `0015` niewykonana, zero API/kosztu i bez merge.

## 2026-07-18 — PR1-MAJ-005-RR-01: writable connector mutował przed drugim schema gate — FIXED / CANDIDATE

- **Finding:** pierwsza naprawa PR1-MAJ-005 nadal miała race pomiędzy immutable preflightem i writable connect. Ogólny connector mógł odtworzyć usunięty plik i wykonywał `journal_mode=WAL` przed drugim gate’em.
- **Odtworzenie przed naprawą:** na temp `0015` usuniętym po preflight zwykły runtime utworzył nowy plik 4096 B przed `SchemaVersionUnavailable`. Na temp podmienionym na `0014` z journal DELETE zmieniły się SHA i mtime przed `SchemaVersionTooOld`.
- **Naprawa:** runtime-only `mode=rw` otwiera wyłącznie istniejący plik bez `mkdir` i PRAGMA; drugi gate działa na tym samym handle; przygotowanie writable następuje dopiero po PASS.
- **Kontrpróba po naprawie:** deletion nie odtwarza DB ani sidecarów; replacement zachowuje SHA/size/mtime/schema/ledger i nie dochodzi do przygotowania połączenia, runtime ani provider boundary. Stabilne `0014`/`0015` i missing DB zachowują kontrakt.
- **Nieudane próby / regresje tej rundy:** brak. Wszystkie targeted, full, partycje, trzy QA, compileall i diff check przeszły w pierwszym przebiegu po implementacji.
- **Status:** `FIXED — CANDIDATE FOR ONE NARROW INDEPENDENT RE-REVIEW`; produkcja nadal `0014`, `0015` niewykonana, Etap 2 `NOT STARTED`, live `NOT AUTHORIZED`, zero kosztu i bez merge.

## 2026-07-18 — Post-merge suite zależny od historycznej nazwy brancha — FIXED / CHECKPOINT CANDIDATE

- **Finding:** po merge PR #1 do `main` pełny suite zebrał 1331 testów, ale zakończył się `1330 passed, 1 failed`. `test_canonical_fake_subprocess_runs_cli_wrapper_worker_restore_and_report` przekazywał na sztywno `--expected-branch dev/first-successful-research-card`.
- **Dowód root cause:** na `main` controlled-live preflight poprawnie zwrócił `PREFLIGHT_FAILED`; osobne powtórzenie failing node dało ten sam wynik. Produkcyjny gate działał prawidłowo, a błąd leżał w testowym setupie.
- **Naprawa:** test odczytuje bieżący branch i HEAD z tego samego kontrolowanego repo, w którym uruchamia subprocess CLI. Nie zmieniono kodu produkcyjnego, runtime, storage ani providera.
- **Kontrpróba:** canonical subprocess test przechodzi, a `expected_branch="foreign"` nadal daje niezerowy wynik i nie uruchamia workera. Produkcyjna asercja branch mismatch pozostała niezmieniona.
- **Weryfikacja:** targeted `6/6`; collect/full `1331/1331`; exact-once `320+322+339+350`; QA lineage `10/10`, recovery `4/4`, schema gate `17/17`; compileall exit 0.
- **Status:** `FIXED — POST-MERGE CHECKPOINT CANDIDATE`; produkcja nadal `0014`, `0015` niezastosowana, Etap 2 `NOT STARTED`, live `NOT AUTHORIZED`, bez kosztu i bez merge nowego PR.

## 2026-07-18 — ETAP 2 / WAVE E1: niezależny review PR #3 = `REJECT` (E1-B01…B04) — naprawione w jednej fali (ADR-100)

- **Kategoria:** INTEGRITY / evidence floor overclaim (pierwszy kandydat E1 twierdził, że surowy SQLite bez FK nie zapisze niespójnego evidence; review obalił to czterema kontrprzykładami).
- **E1-B01:** `length()`/`substr()` SQLite zatrzymują się na pierwszym NUL w TEXT — przemycony NUL w `canonical_text` desynchronizował offsety SQL od Python slicing, a `canonical_chars = length(...)` dawało się spełnić deklaracją długości sprzed NUL. Naprawa: podłogi `instr(CAST(x AS BLOB), x'00')=0` + `typeof='text'` na `canonical_text`/`excerpt_text`/`claim_text`; exploit odtworzony wprost w regresji.
- **E1-B02:** schema pilnowała tylko FORMATU hashy (hex-64) — fałszywy `canonical_sha256`/`claim_sha256` przechodził, a `add_evidence_retrieval` przyjmowało gotowe hashe od wywołującego; caller-controlled `claim_sha256` omijał idempotencję (kontrpróba `logical_duplicate_alt_claim_hash`). Naprawa: triggery przeliczające hashe przez `evidence_sha256_hex` (fail-closed bez funkcji), publiczny zapis wyłącznie z `FetchedDocument`, unikalność logicznej tożsamości `(retrieval_id, claim_text, start, end)`; `raw_sha256`/`extracted_sha256` udokumentowane uczciwie jako audit metadata recordera (SQLite nie dowodzi ich pochodzenia).
- **E1-B03:** encje evidence nie miały właściciela — brak `account_id`, globalne odczyty, cudzy `retrieval_id` używalny między kontami. Naprawa: `account_id NOT NULL REFERENCES accounts(id)` w obu tabelach, trigger lineage tego samego konta (działa przy FK OFF), całe API repozytorium wymaga jawnego `account_id`.
- **E1-B04:** ekstraktor HTML podawał statycznie ukryte poddrzewa (`hidden`, `aria-hidden="true"`, inline `display:none`/`visibility:hidden`) jako treść cytowalną. Naprawa: pomijanie całych ukrytych poddrzew wąskim deterministycznym parserem inline (bez CSS/JS), fail-closed przy niedomkniętym ukrytym elemencie.
- **Nieudane próby / regresje tej rundy:** pierwsze uruchomienie partycji exact-once padło na CRLF w listach plików (znana pułapka `tr -d '\r'`) — poprawione bez zmian kodu.
- **Weryfikacja:** collect/full `1454/1454`; exact-once `366+372+406+310` (1454 unikalne node ID, 0 dup, 0 skip); QA evidence floor `35/35`, schema gate `21/21`, recovery `4/4`, lineage `10/10`; własny harness naprawy `22/22`; migracje `0001–0015` byte-identical z `origin/main`.
- **Status:** `FIXED — REPAIR CANDIDATE, AWAITING INDEPENDENT RE-REVIEW`; P2 z review świadomie NIE naprawione (backlog); produkcja `0014` byte-identical, `0015`/`0016` niezastosowane; live `NOT AUTHORIZED`; zero kosztu; bez merge.

## 2026-07-18 — E1-RR-P2-01: historyczny rozkład partycji nie jest rozkładem post-merge

- **Kategoria:** DOCUMENTATION / REPRODUCIBILITY — MINOR/P2, nieblokujące.
- **Obserwacja:** historyczne wpisy implementera po naprawie B01–B04 podają `366+372+406+310=1454`. Na zmergowanym `main` kanoniczny runner zwrócił `352+355+366+381=1454`.
- **Wpływ:** wyłącznie odtwarzalność liczbowego podziału między partycjami; bez wpływu na evidence integrity, account isolation, migrację lub runtime. `--verify` potwierdził 1454 unikalne node ID, zero luk i duplikatów, a wszystkie cztery partycje zakończyły się exit 0.
- **Decyzja:** nie przepisywać historycznych raportów implementera; aktywne dokumenty używają wyniku post-merge, a starszy rozkład jest jawnie oznaczony jako historyczny. P2 pozostaje nieblokującym zapisem różnicy odtwarzalności; ta formalizacja nie zmienia runnera i nie otwiera żadnego innego P2.
- **Granice:** bez zmian testu partycjonującego, kodu, migracji, konfiguracji i bazy; nie naprawiano innych P2.
## 2026-07-18 — E2-A: pierwszy full suite ujawnił 11 nieaktualnych oczekiwań liczby migracji

- **Objaw:** po dodaniu `0017` pełna suita miała 11 failure; wszystkie oczekiwały listy kończącej się na `0016` lub liczby 16.
- **Root cause:** historyczne testy migracji i operational report miały literalny poprzedni runtime count; kod produktu E2-A i targeted acceptance były zielone.
- **Naprawa:** oczekiwania rozszerzono o addytywne `0017`; operational report używa teraz kanonicznej liczby migracji i dokładnego `RUNTIME_SCHEMA_VERSION`, zamiast starego hardcode `15`.
- **Koszt/skutki zewnętrzne:** `0.000000 USD`; tylko tymczasowe bazy, bez sieci i bez produkcyjnej mutacji.

## 2026-07-18 — E2-A: równoległe partycje kolidują z testami quiescence

- **Objaw:** pierwsza próba uruchomienia czterech partycji jednocześnie dała failure w Windows-only LA-02: oczekiwane `DB_HANDLES_PRESENT`, otrzymane `PROCESSES_PRESENT`.
- **Root cause:** test quiescence prawidłowo wykrył trzy pozostałe procesy pytest. Partycje są exact-once pod względem node ID, ale ta suita nie może być wykonywana współbieżnie, bo obecność obcego procesu jest częścią testowanego kontraktu.
- **Rozstrzygnięcie:** bez zmian kodu; wszystkie cztery partycje powtórzono sekwencyjnie. Po dodaniu dwóch końcowych regresji bieżący exact-once wynik to `357+361+369+387=1474`.

## 2026-07-18 — E2-A: trzy P2 z niezależnego review (formalne zamknięcie, ADR-103)

Niezależny review WAVE E2-A wydał `APPROVE WITH MINOR/P2`. Trzy findings przyjęto jako P2 bez naprawy w tej fali; żaden nie ma kosztu, nie tworzy fałszywego sukcesu i nie wywołuje działania zewnętrznego. Rejestr utrzymuje ich widoczność oraz warunki ponownej oceny; formalne zamknięcie E2-A jest wyłącznie dokumentacyjne.

- **`E2-A-P2-01` — QA harness nie aktywuje sam safety kernela.** Zakres: `scripts/qa/e2a_lineage_disproof.py`. Skrypt nie aktywuje samodzielnie safety kernela; przy niepełnym ENV zatrzymuje się fail-closed przed wykonaniem sond. Wpływ: brak wpływu na runtime produktu, brak kosztu, brak wpływu na produkcyjną bazę; problem ergonomii i spójności QA. Status: **`OPEN P2 / BACKLOG`**.
- **`E2-A-P2-02` — shape-invalid payload i `NEEDS_VERIFICATION`.** Niepoprawny strukturalnie payload zmieniony poza wspieranym flow po przypięciu runu może zakończyć się `NEEDS_VERIFICATION` zamiast `FAILED`. Wpływ: brak kosztu, brak fałszywego sukcesu, brak działania zewnętrznego; stan wymaga operatora; istnieje skuteczna bariera i operatorski sposób obsługi. Status: **`ACCEPTED P2`**.
- **`E2-A-P2-03` — brak SQL-owej niemutowalności `jobs.payload_json`.** `jobs.payload_json` nie posiada triggera blokującego UPDATE po enqueue; aktualne wspierane flow ponownie waliduje payload i odrzuca niespójny stan. Wpływ obecnie: brak potwierdzonego problemu w offline E2-A, brak kosztu, brak fałszywego sukcesu, composition roots działają fail-closed. **MUST REASSESS BEFORE:** paid staged recovery; realny staged provider; controlled-live; działanie zewnętrzne zależne od trwałego intentu. Status: **`OPEN P2 — FUTURE PAID/LIVE GATE`**.
- **Granice:** żaden P2 nie był naprawiany; bez zmian kodu, testów, migracji, konfiguracji i produkcyjnej bazy.

## 2026-07-19 — E2-B: napotkane usterki podczas budowy Controlled Fetch Foundation (wszystkie naprawione w tej fali)

- **Nieaktualne oczekiwania liczby migracji (17→18).** Po dodaniu `0018` cztery pinowane listy migracji i trzy asercje liczby (`test_evidence_migration.py`, `test_runtime_schema_gate.py`, `test_operational_report.py`, `test_research_run_flow.py`, `test_wave0b_durable_provider.py`) oczekiwały `17`. Naprawa: zaktualizowano oczekiwania do `18` i przeniesiono runtime gate na `0018` (nazwa testu `test_runtime_schema_version_is_the_controlled_fetch_migration`); baza `0017` jest teraz `TOO_OLD` dla runtime. Wpływ: wyłącznie testy; brak zmian produkcyjnej bazy.
- **Klasyfikacja `240.0.0.0/4`: reserved vs private.** `ipaddress` klasyfikuje ten zakres jednocześnie jako `is_reserved` i `is_private`; pierwsza wersja `_classify_address` zwracała `ADDRESS_PRIVATE` zamiast dokładniejszego `ADDRESS_RESERVED`. Naprawa: kolejność sprawdzeń stawia `is_reserved` przed `is_private`. Wpływ: wyłącznie etykieta odrzucenia; oba i tak fail-closed.
- **Policy `SYSTEM_SCHEDULER_OFFLINE_ONLY` dla controlled fetch.** Pierwszy acceptance uruchamiał workera z `--offline-only` (kopiując wzorzec E2-A dry-run), ale controlled fetch jest akcją zewnętrzną `dry_run=false`, więc system-schedulerowy worker poprawnie odmawiał. To NIE jest usterka kodu — to poprawne fail-closed; test poprawiono, by zwykły worker CLI wykonywał fetch, a osobny test potwierdza, że `--offline-only` nadal odmawia bez konsumpcji zgody i bez attemptu/retrievalu.
- **Podwójna podłoga przy próbie drugiej terminalizacji SUCCEEDED attemptu.** Test podwójnej terminalizacji trafiał najpierw w trigger `controlled_fetch_attempts_failed_retrieval_consistent` (SUCCEEDED ma retrieval OK, a FAILED wymaga FAILED-retrievalu) zamiast w oczekiwany trigger zamkniętego lifecycle. To poprawne zachowanie (obie podłogi bronią inwariantu); test dopuszcza teraz oba komunikaty i dodatkowo weryfikuje odrzucenie cofnięcia do REQUEST_STARTED oraz DELETE.
- **Granice:** wszystkie usterki napotkane i naprawione w tej fali; produkcyjna baza niezmieniona; koszt `0.000000 USD`.

## 2026-07-19 — E2-B: findings z niezależnego review (formalne zamknięcie, ADR-105)

Niezależny review WAVE E2-B wydał `APPROVE WITH MINOR/P2`. Findings są jawne i nieblokujące dla zamknięcia E2-B; żaden nie występuje w osiągalnym wspieranym runtime flow z konkretnym wpływem i bez skutecznej bariery. Formalne zamknięcie E2-B jest wyłącznie dokumentacyjne.

- **`E2B-F-01` — bezpośrednia ręczna konstrukcja realnego transportu poza wspieranym composition root.** Dowolny własny kod Python może zaimportować i skonstruować `RealControlledHttpTransport`/`ControlledHttpFetch` poza storage/CLI/Workerem/Dispatcherem i dojść do `opener.open()` (w kontrpróbie opener był podstawiony — realnej sieci nie było). `REAL_CONTROLLED_FETCH_ENABLED=False` chroni funkcję `resolve_controlled_fetch_port` (jedyny wspierany root), nie sam import klasy. Bariera: gate `False` + brak wykazanej propagacji przez CLI→Worker→Dispatcher→workflow. Klasyfikacja: **NIE blokuje zamknięcia E2-B; blokuje controlled-live; documentation overclaim (P2)** — dokumentacja nie może twierdzić absolutnie, że klasy nie da się skonstruować ani że realny transport „nie jest nigdzie wykonywany".
- **`E2B-F-02` — kontrola aktualności rozstrzygniętego hosta (TOCTOU DNS).** Realny `urllib` rozstrzyga nazwę samodzielnie przy połączeniu po walidacji przez wstrzyknięty resolver. Bariera: gate `False` (realny `urllib` nie startuje w E2-B). Klasyfikacja: **blokuje controlled-live; nie blokuje zamknięcia**.
- **`E2B-F-03` — `REAL_CONTROLLED_FETCH_ENABLED=False` jako globalny deny-all.** Stała modułowa, nie czytana z ENV; aktywacja wymaga dziś edycji kodu `False→True`. Docelowo runtime'owa jednorazowa zgoda właściciela, nie edycja kodu na każdy request. Klasyfikacja: **blokuje controlled-live; nie blokuje zamknięcia fundamentu**.
- **`E2B-F-04` — ogólny enqueue może utrwalić strukturalnie niepoprawny payload `controlled_fetch_v1`.** Skuteczna późniejsza bariera: approval L1 odrzuca job przed attemptem i transportem (brak zgody, attemptu, transportu, fałszywego sukcesu i kosztu). Klasyfikacja: **`MINOR/P2 — defense-in-depth`**.
- **`E2B-F-05` — harness wymaga UTF-8 na Windows.** Przy domyślnym `cp1252` `scripts/harness/e2b_refutation_harness.py` zatrzymał się na `UnicodeEncodeError`; z `PYTHONIOENCODING=utf-8` przeszedł `13/13`. Brak wpływu na runtime produktu. Klasyfikacja: **`P2 — QA ergonomics`**.
- **`E2B-OBS-02` — wspólna allowlista portów 80/443 dla obu schematów** (`http://host:443`, `https://host:80` dopuszczone). Świadomy kontrakt (allowlista standardowych portów web, niezależna od schematu), nie błąd. Klasyfikacja: **informational / non-blocking**.
- **Granice:** żaden finding nie był naprawiany w tej fali; bez zmian kodu, testów, migracji, konfiguracji i produkcyjnej bazy.

## 2026-07-19 — E2-C: nieudane próby i regresje wykryte podczas implementacji

- **Pierwszy targeted run: 15 failures.** Cztery testy adaptera nadal oczekiwały publicznego `RealControlledHttpTransport`, stałej `REAL_CONTROLLED_FETCH_ENABLED` i factory przyjmującego intent zamiast capability; pozostałe failures pełnego flow miały wspólny root cause: model approvalu odczytany z SQLite miał naive `expires_at`, a nowy storage check porównywał go z aware UTC. Naprawa: testy przepisano na nowy kontrakt, a ważność storage jest ponownie sprawdzana na kanonicznych persisted timestamps; capability dostaje jawnie znormalizowany UTC expiry. Targeted wrócił do zieleni.
- **Pierwszy test capability użył `lease.id`.** `claim_next_job` zwraca `JobLease`, więc poprawna tożsamość to `lease.job.id`. Test zatrzymał się przed mutacją lifecycle; asercję naprawiono i sonda przeszła.
- **Harness E2-B na domyślnym Windows `cp1252` zakończył się `UnicodeEncodeError`.** To istniejący `E2B-F-05`, jawnie poza zakresem E2-C. Kod harnessu encodingowego nie został naprawiony; zgodnie z historycznym kontraktem walidację uruchomiono z `PYTHONUTF8=1`, uzyskując `13/13`.
- **Dwie błędne próby immutable raportu DB.** Pierwsza użyła nieistniejącej nazwy `schema_versions` zamiast `schema_migrations`; druga miała błąd quoting w jednowierszowym pomocniku odczytującym sqlite_master. Obie były otwarciami `mode=ro&immutable=1`, nie mogły mutować bazy i nie utworzyły sidecarów. Końcowy poprawny odczyt: 14 migracji, latest `0014_provider_attempt_reconciliation`, integrity `ok`, FK violations `0`, hash/size zgodne.
- **Końcowe helpery raportujące wymagały korekty na Windows.** Pierwszy collector odziedziczył projektowy quiet output pytest i nie zobaczył node ID; po wymuszeniu `addopts=` domyślne, nieczułe na wielkość liter `Sort-Object -Unique` fałszywie skleiło parametry `[hidden]` i `[HIDDEN]`. Porównanie `StringComparer.Ordinal` potwierdziło `1572` wpisy, `1572` unikalne i `0` duplikatów. Trzy kolejne jednowierszowe warianty immutable checka utraciły cudzysłowy na granicy PowerShell/Windows argv i zakończyły się `SyntaxError` przed otwarciem DB. Poprawne wywołanie z jednym zewnętrznym quotingiem przeszło: 14 migracji, latest `0014_provider_attempt_reconciliation`, integrity `ok`, FK `0`; hash, rozmiar i brak sidecarów pozostały zgodne.
- **Zbiorczy replay źle uciekł ścieżkę sidecarów.** Trzy wywołania `Test-Path` zakończyły się niekończącym błędem PowerShell, więc mimo kodu procesu `0` nie zostały uznane za dowód. Osobna poprawiona kontrola literalnych ścieżek potwierdziła brak WAL/SHM/journal; helper nie wykonał zapisu ani operacji na DB.
- **Jedna mechaniczna próba patcha transportu nie dopasowała kontekstu.** Powodem było wyświetlenie UTF-8 w domyślnym kodowaniu PowerShell jako mojibake; patch nie zastosował żadnej części. Plik odczytano jawnie jako UTF-8 i ponowiono w małych hunkach.
- **Skutki zewnętrzne i koszt:** brak. Wszystkie testy używały fake callerów/resolverów/transportów i tymczasowych baz; zero realnego DNS/socketu/HTTP/API/providera/browsera/publikacji, koszt `0.000000 USD`; produkcja pozostała byte-identical.

## 2026-07-19 — E2-C: findings po niezależnym review i formalnym zamknięciu (ADR-107)

Niezależny review PR #9 wydał `APPROVE WITH MINOR/P2`. Po merge i zielonym checkpointcie właściciel formalnie zamknął E2-C. To zamknięcie dokumentacyjne nie naprawia P2 i nie zmienia kodu.

- **`E2B-F-01` — status:** `TECHNICALLY CLOSED IN MERGED E2-C`. Wspierany flow wymaga storage-issued capability po atomowym zużyciu dokładnego approval L1, a realny transport powstaje przez kontrolowany composition root. Granica nie obejmuje autora dowolnego własnego kodu Python.
- **`E2B-F-02` — status:** `TECHNICALLY CLOSED IN MERGED E2-C`. Immutable `BoundHttpTarget` wiąże transport z numerycznym adresem, który przeszedł politykę; transport nie wykonuje ponownego DNS, a każdy redirect przechodzi nowe pełne wiązanie.
- **`E2B-F-03` — status:** `TECHNICALLY CLOSED IN MERGED E2-C`. Globalna dostępność jest strict booleanem YAML domyślnie `false`, bez aktywacji przez ENV; konfiguracja nie zastępuje approval L1 konkretnego joba.
- **`E2B-F-04`:** pozostaje `MINOR/P2 — defense-in-depth`; nienaprawione.
- **`E2B-F-05`:** pozostaje `P2 — QA ergonomics`; nienaprawione.
- **`E2B-OBS-02`:** pozostaje informational / non-blocking.
- **`PR8-DOC-P2-01`:** pozostaje `P2`; nienaprawione.
- **`F-DOC-01`:** pozostaje `P2` dokładności raportowania. Review skorygował opis skali diffu do 34 plików i około `+2000/-165`; nie wpływa to na techniczny wynik E2-C.
- **`F-01-RESIDUAL`:** pozostaje `P2` poza wspieranym runtime. Prywatność nazw i pieczęć factory nie są granicą bezpieczeństwa wobec uprzywilejowanego autora dowolnego Pythona; prawidłowe twierdzenie brzmi: „Realny transport jest chroniony w granicach wspieranego runtime i composition roots.”
- **Nieudana próba helpera dokumentacyjnego:** read-only polecenie do porównania wcześniejszego zamknięcia złożyło niepoprawny zakres PowerShell/Git (`$base..$head`) i zwróciło wyłącznie pomoc `git diff`. Nie wykonało mutacji; dane odczytano ponownie poprawnym poleceniem.
- **Pierwsza końcowa sonda immutable SQLite utraciła cudzysłowy na granicy PowerShell/argv.** Python zakończył się `SyntaxError` przed wywołaniem `sqlite3.connect`, więc baza nie została otwarta ani zmieniona. Powtórzenie z kodem przekazanym jako jeden argument otworzyło wyłącznie `mode=ro&immutable=1` i potwierdziło 14 migracji, latest `0014_provider_attempt_reconciliation`, integrity `ok`, FK `0` oraz brak sidecarów.
- **Granice i produkcja:** bez napraw P2, bez pełnej suity, bez zmian kodu/testów/migracji/config/runtime/DB. Produkcja pozostaje `0014`, runtime wymaga `0018`; controlled-live = `NOT READY`; następna operacja = `NOT STARTED`.

## 2026-07-19 — Production Schema Migration Orchestrator: blockery i nieudane próby

- **Brak jednego rootu:** istniejące cztery CLI jednostopniowe potrafiły wykonać poprawne migracje, lecz nie tworzyły jednego owner-approved flow z SHA/size/snapshotem i finalnym raportem. Root cause nie leżał w SQL `0015–0018`; migracji nie zmieniono.
- **Nieaktualny QA:** runtime od E2-B wymaga `0018`, ale skrypt disproof kończył drabinę na `0017` i otwierał ją jako runtime. Zmieniono wyłącznie to założenie i dodano wymaganą odmowę future; wynik `30/30`.
- **Pierwszy targeted run: 2 failures.** Test „wrong path" utworzył dwie deterministycznie identyczne puste bazy w tej samej sekundzie, więc SHA/size nie odróżniały ścieżek; kontrpróbę poprawiono trwałą zmianą `user_version`. Test corruption po celowym uszkodzeniu `sqlite_master.rootpage` próbował jeszcze przełączyć journal mode i sam zatrzymywał się na `malformed schema`; zbędny krok usunięto. Oba błędy dotyczyły fixture, nie orchestratora; produkcja nie była otwierana.
- **Pierwsza ręczna sonda modułu:** użyła `from ... import *` i próbowała wywołać prywatny helper `_capture_file_state`, więc zakończyła się `NameError` przed migracją. Powtórzenie z publicznym API na temp DB przeszło `0014→0018`; nie dotknęło produkcji.
- **Windows file identity:** `os.fstat().st_ctime_ns` i `Path.stat().st_ctime_ns` mogą prezentować różne reprezentacje czasu utworzenia dla tego samego uchwytu. Stabilność otwartego pliku oparto na dev/inode/size/mtime/nlink + SHA, a ctime pozostaje składnikiem porównania kolejnych path-state snapshotów. Targeted wrócił do zieleni.
- **Nieblokujące ostrzeżenie:** sekwencyjne partycje raportują `PytestAssertRewriteWarning` dla wcześniej zaimportowanego `anyio`; wszystkie cztery partycje zakończyły się kodem `0`, exact-once cover jest pełny. Brak wpływu na testy produktu.
- **Skutki/koszt:** wszystkie nieudane próby działały na nowych temp DB albo kończyły się przed zapisem. Zero aplikacyjnej sieci, DNS, socketów, HTTP, API, providera, browsera, publikacji i kosztu. Produkcja pozostała byte-identical.

## 2026-07-19 — Post-merge PR #11: interferencja pierwszego przebiegu pełnej suity + findings review (ADR-109)

- **Interferencja pierwszej pełnej suity (operational test interference / procedural lesson, nie blocker produktu):** pierwszy post-merge przebieg dał `1628/1630`. Dwa failures w `tests/test_la02_quiescence.py` (foreign SQLite handle `[writable]`, foreign sidecar handle `[-wal]`) dotyczyły wyłącznie reason code sondy quiescence: oczekiwano `DB_HANDLES_PRESENT`, otrzymano `PROCESSES_PRESENT`, bo równolegle działały procesy acceptance orchestratora (m.in. realny CLI z systemową inwentaryzacją procesów), które sonda poprawnie policzyła jako obce procesy projektu. Flow zatrzymał się fail-closed (`status=STOP`, exit 2) w obu przypadkach. Testy w izolacji przeszły `2/2`; czysty pełny rerun bez równoległej aktywności dał `1630/1630`, zero skipped. Plik testowy nie był zmieniany w PR #11, a identyczne drzewo przechodziło `1630/1630` przed merge — defektu zmergowanego kodu nie zidentyfikowano. **Lekcja proceduralna:** nie uruchamiać acceptance z sondą procesów równolegle z testami LA-02.
- **F-PR11-01 (zaakceptowane P2, nienaprawiane):** raport implementera deklarował diff `+2251/−106`; rzeczywisty i zatwierdzony wynik to 28 plików, `+2182/−37` (zgodnie w `git diff` i GitHub API). Recydywa klasy reporting accuracy.
- **F-PR11-02 (zaakceptowane P2, nienaprawiane):** README podaje nieaktualną liczbę testów; istniejący dokumentacyjny P2 poza minimalnym zakresem tej fali.
- **F-PR11-03 (zaakceptowane P2, nienaprawiane):** przy resume z `0015–0017` CLI nadal wymaga literalnej wartości `--expected-from-version 0014_provider_attempt_reconciliation` (semantyka = początek drabiny, nie bieżący szczebel). Bariera bezpieczeństwa pozostaje kompletna: aktualny SHA-256, aktualny rozmiar, exact ledger, nowy snapshot, jawna flaga confirmation i `resume_requirements` w raporcie błędu wiążą zgodę z dokładnym bieżącym plikiem.
- **Obserwacje (zachowane, informational):** `OBS-PR11-01` — failpoint przed finalną walidacją daje STOP z jawnym durable `0018` i `safe_owner_resume=false`, rerun = `ALREADY_AT_TARGET`; `OBS-PR11-02` — po awarii finalnej walidacji raport podaje durable `0018` udowodnione na writable handle po COMMIT, a status `MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT` wymusza ocenę operatora; `OBS-PR11-03` — domknięcie okna connect→pierwszy zapis opiera się na semantyce współdzielenia plików wspieranego Windows plus weryfikacji ledger+identity na już otwartym uchwycie.
- **Granica:** wcześniejsze otwarte findings projektu pozostają bez zmian. Produkcja przed i po byte-identical `0014`; koszt `0.000000 USD`.

## 2026-07-22 — F1-BLOCK-01: finansowo zakończony request blokował lifecycle topic-generation

- **Objaw:** po crashu po `model_usage` i `provider_attempt=SETTLED`, lecz przed scoringiem, job/run pozostawały nieterminalne. Reaper przenosił job do `NEEDS_VERIFICATION`, maintenance go nie domykało, resolver odrzucał stan, konto pozostawało zablokowane, a retry było zabronione.
- **Root cause:** `_recover_settled_execution_attempts` jawnie obejmowało tylko RESEARCH; `_reconciliation_assert_settled_execution_cache_prestate` używało `_research_usage_total`; trigger `EXECUTION_RECOVERY` wymagał `research_run`. Legalne usage `task='topics'` nie miało wspieranej drogi wykonawczej.
- **Pierwsza kontrpróba:** nowy fake caller odtworzył rzeczywisty crash window i przed naprawą maintenance zwróciło zero recovery. To był oczekiwany czerwony dowód blockera, nie awaria zewnętrzna.
- **Nieudana iteracja naprawy:** pierwsza wersja dodatkowych triggerów blokowała także zwykłą finalizację success/parse/scoring bez stanu `NEEDS_VERIFICATION`. Testy topic-generation ujawniły zbyt szeroką podłogę; triggery usunięto, a ochrona pozostała ograniczona do `EXECUTION_RECOVERY` i istniejącej bramki recovery.
- **Naprawa:** polimorficzny kanon usage i polimorficzne, atomowe `EXECUTION_RECOVERY` dla ściśle walidowanego `TOPIC_GENERATION`; attempt/usage/koszt są niezmienne, run/job kończą jako `FAILED`, rezerwacja i blokada konta znikają. Resolver obsługuje wyłącznie `CHARGED_KNOWN + EXECUTION_FAILED`.
- **Dowód końcowy:** `1821/1821`, 0 skipped/xfail; crash/reopen/maintenance/replay/resolver/failpoint i surowe SQLite floors zielone. Produkcja nietknięta, koszt `0.000000 USD`.

## 2026-07-22 — Publiczny controlled-live TOPIC_GENERATION: blocker i dwie nieudane próby lokalne

- **Historyczny preflight `BLOCKED` (poprawne zachowanie):** przed tą falą publiczny `worker --once` mógł użyć tylko queue-wide `claim_next_job`. Wewnętrzne `target_job_id`/`claim_specific_job` istniały, ale nie były dostępne przez publiczny, policy-gated root dla `TOPIC_GENERATION`. Preflight zatrzymał operację przed enqueue/requestem; nie wolno przepisywać go jako PASS.
- **Błędna pierwsza sonda schema:** read-only immutable zapytanie użyło nieistniejącej nazwy `schema_version` zamiast `schema_migrations` i otrzymało `no such table`. Po sprawdzeniu migracji zapytanie poprawiono. Obie operacje były bez zapisu; produkcyjny SHA/rozmiar/sidecary nie zmieniły się.
- **Przeciek ścieżki kosztów w fake subprocess:** pierwsza wersja testowego subprocessu kierowała temp DB i fake caller do katalogu testowego, ale odziedziczyła projektowy `docs/COSTS.csv`; trzy syntetyczne wiersze `topics` trafiły do diffu. Zostały natychmiast zidentyfikowane i usunięte, a test mode wiąże teraz również `costs_csv_path` z temp runtime. Powtórzenie potwierdziło stabilny hash pliku. Nie było realnego usage, kosztu ani zewnętrznego requestu.
- **Klasyfikacja:** dwa ostatnie zdarzenia to błędy narzędziowe/test-fixture, nie defekty produkcyjnej bazy. Oba zostały zachowane w historii audytowej, a końcowa pełna suita ma `1854/1854`.
- **Pierwsze wywołanie końcowego audytu SQLite:** kod przekazany przez `python -c` ponownie utracił cudzysłowy na granicy PowerShell/argv i zakończył się `SyntaxError` przed `sqlite3.connect`. Hash/rozmiar/sidecary były już zgodne; schema/integrity/FK sprawdzono ponownie kodem podanym przez stdin. Nieudana sonda nie otworzyła ani nie zmieniła bazy.
## 2026-07-23 — obserwacja po successful controlled-live: trwałe puste sidecary WAL/SHM

- **Klasyfikacja:** obserwacja operacyjna, nie failure requestu i nie reconciliation.
- **Fakt:** po terminalnym `SUCCESS` i zamknięciu storage plik `agent.db-wal` miał `0 B`, a `agent.db-shm` `32768 B`. Główna baza zawiera pełny wynik, integrity = `ok`, FK = `0`, aktywne locki = `0`, a standalone quiescence = `PASS`.
- **Działanie:** sidecarów nie usuwano, nie checkpointowano ręcznie i nie wykonywano kolejnego writable open. Stan został jawnie zachowany do oceny kolejnej operacji, która wymaga ich braku.
- **Wpływ:** brak wpływu na zakończony request, settlement, usage, topics i restore flag. Przyszła operacja z twardym warunkiem „sidecary absent” musi wykonać nowy preflight i osobno zdecydować o bezpiecznym cleanupie.
- **Nieudane sondy operatora formalnego zamknięcia:** dwie komendy metadanych PowerShell zakończyły się błędem parsera przez pusty element pipeline, a jedna próba opakowania sondy SQLite w warstwie orkiestracji zakończyła się `SyntaxError` przed uruchomieniem powłoki. Żadna z tych prób nie otworzyła ani nie zmieniła bazy. Poprawione sondy potwierdziły oczekiwany SHA/size/sidecary oraz read-only `mode=ro&immutable=1`, schema/integrity/FK/counts; klasyfikacja: proceduralne błędy polecenia, bez wpływu na produkt i formalne zamknięcie.

## 2026-07-23 — WAVE C1: czerwone przebiegi i ich rozstrzygnięcie

- **Pierwszy targeted C1: 9 failures.** Jeden root cause był kontraktem upgrade: legacy `content_items.DRAFT` bez `research_card_id` nie przechodził nowego CHECK. Zachowano historyczny DRAFT jako jawny wyjątek kompatybilności, przy czym atomowe C1 API nie pozostawia go po COMMIT. Drugi failure był prawidłowym opakowaniem wyjątku SQLite UDF jako `OperationalError`; test skorygowano. Pozostałe siedem pochodziło ze wspólnego research-only timestamp gate, który minimalnie rozszerzono o typowany `CONTENT + ARTICLE|NOTE`. Rerun: zielony.
- **Pierwszy touched regression: 2 failures.** Test migracji 0020 uruchamiał domyślny runner aż do nowego runtime 0021, a operational report oczekiwał 20 migracji. Test 0020 ograniczono jawnie `through=0020`, a runtime expectation zmieniono na 21. Rerun touched suite: zielony.
- **Pierwsza pełna suita: 3 failures.** Jeden prawdziwy stale test otwierał runtime bez jawnego szczebla `0020→0021`; dodano osobny migrator wymagający `--confirm-0020-to-0021`. Dwa pozostałe failures (`REPORT_WRITE_FAILED_RECOVERY_REQUIRED`) były artefaktem zbyt długiego Windows `--basetemp`, nie defektem produktu: oba przeszły razem z migracją `3/3` na krótkiej ścieżce; pełny rerun na krótkiej ścieżce dał `1893/1893`.
- **Drobne próby narzędziowe:** dwa patche nie dopasowały kontekstu i jedno read-only `rg` miało błąd quoting PowerShell. Nie zmieniły plików ani baz; po odczycie dokładnego kontekstu wykonano poprawne patche.
- **Historyczna klasyfikacja implementera pierwszego kandydata:** zadeklarowano blocker C1 = brak. Niezależny review później obalił tę ocenę wynikiem `REJECT — MAJOR` i trzema findings MAJOR; bieżący stan opisuje następny wpis. Otwarty `C1-P2-01`: legacy DRAFT bez C1 identity pozostaje dopuszczony wyłącznie dla zgodności danych historycznych; C1 storage nie używa go jako wykonywalnego content intentu. Produkcja nietknięta; zero sieci/API/browsera/publikacji/kosztu.

## 2026-07-23 — C1 independent review `REJECT — MAJOR` i jedyna fala naprawcza

- **Finding MAJOR-01:** content snapshot odtwarzał lineage przez `claim_text`/`supports_claim` i URL zamiast jawnego `evidence_source_lineage`. Reprodukcja wykazała fałszywe dopasowania dla powtórzonego tekstu, wspólnego URL i excerptu innego claimu. Naprawa: tylko trwałe IDs+fingerprint, brak heurystycznego backfillu, drugi recheck w transakcji startu.
- **Finding MAJOR-02:** generyczne terminalizatory oraz raw `content_runs` mogły rozdzielić job/run/content_run/content_item; replay sprawdzał no-op zbyt wcześnie, a context nie niósł niezależnej generacji. Naprawa: monotoniczny fence, append-only transition command i odmowa wszystkich generycznych terminalizatorów CONTENT.
- **Finding MAJOR-03:** extension mogło nie być ścisłym parentem kanonicznego provider attemptu. Naprawa: pełna identity, request derivation, deferred FK, parent-trigger, atomowy insert pary i content-specific usage trigger.
- **Findings MINOR:** workflow ARTICLE/NOTE nie było porównywane na czterech durable rows; dokumenty przedwcześnie deklarowały brak blockerów. Oba zaadresowano w kandydacie i aktywnych dokumentach.
- **Czerwone przebiegi podczas repair:** początkowo wykryto brakujący `stage`/nadmiar placeholdera, liczniki fixture obejmujące pomocniczy research run, starą asercję provider-disabled, niepełny SELECT recovery i brak scope w triggerze raw job/run. Każdy przypadek został zachowany jako test lub skorygowany kontrakt; końcowe 69/69 targeted oraz pełna suita są zielone.
- **Drobna próba narzędziowa po QA:** jedna komenda read-only użyła operatora `||`, którego bieżący Windows PowerShell nie obsługuje jako separatora. Parser odmówił przed uruchomieniem `rg`, compileall lub Git; poprawiona sekwencja z jawnym `$LASTEXITCODE` przeszła. Brak zmiany danych i wpływu na wynik produktu.
- **Pozostająca obserwacja QA:** collect zawiera 1923 przypadki, lecz 1922 różne tekstowo node IDs z jedną zastaną kolizją ID w `test_evidence_foundation.py` (`hidden`/`HIDDEN`). To istniejąca ergonomia parametryzacji poza C1; oba przypadki są wykonywane, pełna suita ma 1923/1923. Nie zmieniano nieskopowanego pliku.
- **Klasyfikacja końcowa implementera:** naprawy są kandydackie, findings formalnie pozostają otwarte do niezależnego re-review. Brak nowego znanego blockera funkcjonalnego w zakresie pięciu findings; `C1-P2-01` oraz zastana kolizja node ID pozostają P2/QA. Produkcja nietknięta; zero sieci/API/browsera/publikacji/kosztu.

## 2026-07-23 — WAVE C2: czerwone przebiegi, kontrpróby i P2

- **Pierwszy C2 happy path ARTICLE/NOTE:** oba fake fixtures trafiały w `REWRITE_ONCE`, bo techniczny artykuł przekraczał własny zakres długości, a Note była krótsza niż minimum. Nie obchodzono evaluatorów; zmniejszono liczbę deterministycznych akapitów ARTICLE i dodano evidence-led zdanie do Note. Rerun obu typów: `PENDING_APPROVAL`.
- **Pierwsza pełna suita:** 3 failures przy 1945 przypadkach. Historyczny test drabiny próbował otworzyć runtime po 0021, a operational report i runtime-gate test oczekiwały 21 migracji. Root cause: nowy runtime floor `0022` nie został jeszcze dopisany do jawnej drabiny QA. Dodano `scripts/migrate_schema_0022.py` z obowiązkowym confirmation i zmieniono dwa dokładne liczniki na 22. Targeted rerun `3/3`, czysty full rerun `1945/1945`.
- **Końcowa próba collect:** pierwsza komenda odziedziczyła projektowe `addopts=-q`, a dodatkowe `-q` ukryło listę node IDs mimo kodu wyjścia 0. Pustego outputu nie uznano za dowód; powtórka z `-o addopts= --collect-only -q` policzyła `1945` case-sensitive unique IDs i `0` duplikatów.
- **Obalone hipotezy awarii:** restart w czterech checkpointach nie duplikuje canonical attemptu; stary generation fence po takeover nie zapisuje; dwa targeted workery dają dokładnie `DONE + IDLE`; external-effect marker nadal eskaluje do `NEEDS_VERIFICATION`; hard unsupported/personal findings nie otwierają rewrite; druga prośba o rewrite kończy trwale bez próby #3.
- **`C2-P2-01`:** canonical `provider_attempts.reserved_amount_usd` ma historyczny CHECK `>0`. Fake attempt przechowuje strukturalne `0.000001`, ale writer intent ma cap 0, job nie ma budget hold, usage/actual/run cost są dokładnie `0.000000`. Przebudowa globalnego ledgera była poza zakresem i zwiększałaby ryzyko.
- **`C2-P2-02`:** C1 blokuje generic heartbeat dla CONTENT. Targeted fake flow działa pod krótkim bounded lease i jest deterministyczny; przed długim lub realnym writerem trzeba dodać dedykowany heartbeat wiążący execution generation. To gate C5, nie luka otwierająca koszt w C2.
- **`C2-P2-03/04`:** Notes style jest provisional; techniczne provider/API IDs/availability/pricing są `UNVERIFIED`. Realny caller odmawia, więc braki są fail-closed i blokują C5.
- **Klasyfikacja:** brak znanego blockera C2 offline po czystym rerunie; status wyłącznie kandydacki do niezależnego review. Produkcja, raw style source i external systems pozostały nietknięte; koszt `0.000000 USD`.

## 2026-07-23 — WAVE C3: czerwone przebiegi, rollback i próby narzędziowe

- **Pierwsza wersja migracji 0023:** rebuild tworzył FK z `content_writer_attempts` do tymczasowej nazwy `content_writer_intents_v3`; po rename SQLite zachował nieprawidłowe odwołanie. Migrację poprawiono przez tymczasowy backup attempts, rebuild/rename intentu i dopiero potem odtworzenie attempts z FK do finalnej tabeli. Nowy test failpoint dowodzi wspólnego rollbacku schema+ledger i przywrócenia PRAGMA.
- **Pierwszy focused C2 rerun:** nowe klasy błędów routingu nie zachowywały historycznego typu `RealContentWriterUnavailable`; oraz fake writer nie implementował wstępnie całego rozszerzonego result contract. Przywrócono kompatybilne dziedziczenie i adapter fake bez osłabiania fail-closed C3. Końcowy C2+C3: `48/48`.
- **Pierwsza pełna suita została przerwana przez limit launchera 120 s, nie przez failure produktu.** Rerun z dłuższym wykonaniem ujawnił stare oczekiwania `22` migracji; zaktualizowano wyłącznie jawne drabiny/liczniki na runtime `0023`. Kolejny czysty pełny przebieg zakończył się `1971/1971`.
- **Podwójny quiet ukrył finalną linię podsumowania.** `pyproject.toml` ma `addopts=-q`, a polecenie dodało drugie `-q`; output zawierał wyłącznie 100% kropek. Nie zgadywano liczby: osobny `--collect-only -q -o addopts=` policzył `1971` node IDs, `1971` case-sensitive unique i `0` duplikatów.
- **Dwie nieproduktowe próby operatorskie:** pierwsze background `Start-Process` z dynamicznymi ścieżkami temp zostało odrzucone przez policy przed uruchomieniem; uproszczony jawny wariant wystartował poprawnie. Później read-only `Get-Date -AsUTC` nie zadziałał w tej wersji PowerShell; pozostałe komendy odczytowe i Git wykonały się poprawnie. Żadne z tych zdarzeń nie otworzyło bazy, sieci ani providera i nie zmieniło danych projektu.
- **Pierwsza sonda POST sidecarów miała niepoprawne wyrażenie PowerShell:** `if` umieszczone w nawiasie wartości obiektu zostało potraktowane jak polecenie. Hash/size i immutable SQLite query zdążyły przejść, ale wyniku sidecarów nie uznano za dowód. Poprawiony wariant z osobną zmienną potwierdził WAL `0 B`, SHM `32768 B`, journal absent; brak mutacji.
- **Kontrpróby zakończone zgodnie z projektem:** missing provider/model/pricing/availability/secret odmawia przed SDK; timeout/429/5xx/auth/invalid request nie retry'ują; parse/truncation/schema zachowują usage i settlement; call-returned bez durable result nie wykonuje drugiego calla i kończy `NEEDS_RECONCILIATION/NEEDS_VERIFICATION`; old fence, dwa workery, podwójny settlement i trzecia próba są blokowane.
- **Otwarte gates/P2, nie blockery kandydata offline:** brak niezależnego review; actual provider/model/pricing/availability `UNVERIFIED`; Notes `PROVISIONAL`; strukturalny zero-cost reservation floor; dedykowany heartbeat do ponownej oceny przed C5/dłuższym timeoutem. Produkcja i raw style source pozostały nietknięte, koszt `0.000000 USD`.

## 2026-07-24 — WAVE C4: próby narzędziowe i regresje wersji schematu

- **Pierwsza sonda metadanych PRE:** złożone wyrażenie PowerShell miało błąd parsowania. Komenda zatrzymała się przed otwarciem plików i nie dostarczyła dowodu; poprawiony wariant potwierdził Git, produkcję immutable/query-only i wyłącznie metadane prywatnego stylu.
- **Pierwsza pełna suita:** launcher przerwał przebieg po około 123 s i zgłosił wtórny `OSError` strumienia outputu. Nie uznano tego za wynik produktu. Rerun z dłuższym timeoutem doszedł do testów i ujawnił 10 nieaktualnych oczekiwań numeru/listy migracji.
- **Pierwsza celowana regresja:** 8 historycznych testów nadal oczekiwało runtime 0023 albo starego tekstu triggera. Zaktualizowano wyłącznie jawne drabiny/liczniki i zgodny komunikat SQL; rerun `8/8`.
- **Druga pełna regresja:** 10 failures dotyczyło wyłącznie oczekiwań 23 migracji w operational report, legacy `apply_migrations` listach i CLI ladder kończącej się na 0023. Po dopisaniu jawnego kroku 0024 dokładny rerun dał `10/10`.
- **Czysty wynik:** `python -m pytest -q` zakończył się exit 0 przy 1994 zebranych przypadkach. Osobny collect policzył 1994 case-sensitive unique IDs, 0 duplikatów i +23 wobec baseline 1971. Podwójny quiet ponownie ukrył linię liczbową pełnego przebiegu, dlatego liczba pochodzi z exact collect, nie z domysłu.
- **Kontrpróby:** drift autonomy, evaluation, policy version i thresholds nie może utrzymać wcześniejszego approve; hard violation high score odrzuca; brak/duplikat/sprzeczność/zła wersja evaluations i replaced draft fail closed; stale fence, równoległy worker, sprzeczny replay, raw SQLite mutation i błąd po applied są blokowane lub rollbackowane bez częściowego audytu.
- **Otwarte, celowo nienaprawiane:** osiem P2 właściciela bez zmian; PRE-C5 gate `NOT STARTED`. Brak nowego znanego blockera kandydata C4 offline; formalna ocena należy do niezależnego review.
- **Próba compile cache cleanup:** jedna złożona komenda z bezpiecznym temp path i rekurencyjnym usunięciem przekierowanego cache została zatrzymana przez policy narzędzia przed uruchomieniem. Wymagany `python -m compileall -q app scripts` wykonano następnie z `PYTHONPYCACHEPREFIX` poza workspace (exit 0), a `git diff --check` osobno (exit 0). Nie powstał workspace `__pycache__` z tego kroku.
- **Pierwsza sonda produkcji POST:** immutable/query-only query użyła nieistniejącej kolumny `system_flags.value`; SQLite odmówił bez zapisu. Read-only `PRAGMA table_info` wskazało `value_json`, a pełna powtórka potwierdziła identyczny SHA/size/schema/counts/flags/integrity/FK i sidecary.
- **Cleanup `.pyc`:** inwentarz po timestampie brancha wskazał 22 ignorowane cache files utworzone lub odświeżone przez pytest. Zarówno dynamiczna, jak i pojedyncza jawna próba `Remove-Item` zostały zablokowane przez policy narzędzia przed usunięciem. Nie użyto `git clean` ani obejścia innym shellem. Git nie widzi żadnego z tych plików jako untracked; nie powstały nowe `.db/.sqlite/.log/.tmp`, sidecary, wyniki collect/full ani scratchpady. Cache pozostaje jawnym nieproduktowym artefaktem testowym do lokalnego cleanupu poza tą sesją.

## 2026-08-09 — PRE5-RR-01: odrzucony model rozwiązania i nieszkodliwe błędy sond

- **Odrzucony model rozwiązania:** poprzednia naprawa claim gate nadal klasyfikowała fakty za pomocą skończonego zbioru sygnałów (role, instytucje, reporting verbs, named actors, liczby), a wszystko pozostałe domyślnie zwalniała jako stylistyczne. Kontrpróby logistyki, infrastruktury, ekonomii, zachowania instytucji, historii, właściwości fizycznych, reguł operacyjnych, przyczynowości, encji, supply chain, market structure, software operation i energy system potwierdziły strukturalny false-negative. Rozwiązanie usunięto zamiast rozszerzać słownik; zastąpił je pełny claim accounting wszystkich segmentów.
- **Pierwsza sonda schema PRE:** immutable/read-only query założyło kolumnę `schema_migrations.name`; SQLite zwrócił `no such column: name`. `PRAGMA table_info` wykazało faktyczne `version, applied_at`; poprawiona sonda potwierdziła 20 migracji i `0020_topic_generation_lifecycle`. Bez zapisu i bez zmiany hashy/sidecarów.
- **Pierwsza komenda metadanych PRE:** użyto operatora PowerShell `??`, nieobsługiwanego w tej powłoce. Parser zatrzymał polecenie przed wykonaniem. Poprawiona wersja zebrała wymagane metadane.
- **Pierwszy licznik collect:** parser stdout oczekiwał listy node IDs, lecz konfiguracja quiet podała tylko podsumowania per plik; wynik `0` był nieważny. Powtórka z hookiem kolekcji policzyła exact IDs i duplikaty.
- **Dwie komendy regresji:** robocza lista zawierała nieistniejące nazwy `test_prec5_e3_closure.py`/`test_prec5_repair_regressions.py`, a następnie stare nazwy modułów C2/C3/C4. Pytest zatrzymał się przed kolekcją. Po odczycie faktycznego katalogu poprawne runy dały PRE-C5 `108/108` i zakres `436/436`.
- **Pierwszy pełny run:** limit procesu ustawiono omyłkowo na `1 s`; launcher przerwał pytest i zgłosił wtórny błąd stdout. Nie uznano tego za wynik testów. Identyczny run z właściwym limitem zakończył się `2102/2102` w `367.7 s`.
- **Wpływ:** wszystkie zdarzenia były lokalne, offline i bezprodukcyjne. Nie wykonano sieci, API, publikacji, zapisu do produkcji ani operacji Git. Rzeczywisty koszt `0.000000 USD`.

## 2026-08-09 — Question semantic boundary: dwa odrzucenia i błędy narzędziowe

- **Dwa odrzucenia poprzedniej fali:** pierwsze rozwiązanie `predicate + concrete referent` zakończyło się `REJECT — MAJOR`; jedyna dozwolona naprawa z `_CONTENTLESS_QUESTION_VOCABULARY` również zakończyła się `REJECT — MAJOR`. Według przekazanego re-review `34/38` factual questions przechodziło jako `NON_FACTUAL_PROSE`, a pięć reprezentatywnych przypadków osiągnęło pełne `9/9 PASS`. Nie wykonano trzeciej poprawki; kandydat został usunięty w jawnie autoryzowanym zakresie.
- **Root cause:** blacklist/whitelist/vocabulary, referent i predicate próbowały udowodnić brak znaczenia przez skończony opis języka. Membership nie dowodzi braku factual proposition; każda taka heurystyka ma fail-open dopełnienie.
- **Fingerprint manifestu:** pierwsza sonda poprawnie policzyła główne SHA, lecz końcowy `SHA256.HashData` nie istnieje w lokalnej wersji .NET. Niepełnego wyniku manifestu nie przyjęto; powtórka użyła `SHA256.Create().ComputeHash` i dała `f5bf2971…55f66c`. Bez mutacji.
- **Collect PRE:** pierwsze parsowanie zwróciło pozorne `0`, ponieważ projektowe `addopts=-q` plus jawne `-q` pokazały per-file counts zamiast node IDs. Powtórka z `-o addopts=` dała prawidłowe `2102` exact unique i `0` exact duplicates. Dodatkowa sonda opcjonalnych plików konfiguracji zakończyła `rg` kodem 1 dla nieistniejących paths; sam collect był poprawny, ale wynik tej złożonej komendy nie został użyty jako checkpoint.
- **Full suite:** pierwsza próba miała omyłkowy limit procesu `1 s`, została przerwana przez launcher i zgłosiła wtórny `OSError` stdout. Nie uznano jej za failure produktu. Identyczny przebieg z poprawnym limitem zakończył się `2285/2285` w `358.89 s`.
- **Wpływ:** wszystkie zdarzenia były lokalne, offline i bezprodukcyjne. Produkcja i style corpus zachowały dokładne SHA/size/mtime/sidecary; koszt `0.000000 USD`.

## 2026-08-09 — Repair question-marker-anywhere: MAJOR i próby narzędziowe

- **Finding produktu:** kandydat chronił tylko `text.endswith("?")`. Segmenty z `?!`, `?.`, `?;`, `?...` albo zamykającym znakiem po `?` mogły wejść w stary fallback transition/predicate/length i przejść jako `NON_FACTUAL_PROSE`. Wszystkie pięć przekazanych MAJOR examples odtworzono PRE jako claim-gate PASS. Naprawa sprawdza wyłącznie obecność `?` lub `？` w segmencie; POST wszystkie blokują.
- **Wildcard PRE-C5:** PowerShell przekazał `tests\test_prec5_*.py` dosłownie do pytest, więc próba zakończyła się przed kolekcją komunikatem `file or directory not found`. Powtórka z listą rozwiniętą przez `Get-ChildItem` dała `328/328`.
- **Pierwszy full run:** limit launchera ustawiono omyłkowo na `1 s`; proces został przerwany i zgłosił wtórny `OSError` stdout. Nie uznano tego za failure produktu. Powtórka z właściwym limitem dała `2322/2322` w `360.56 s`.
- **Pierwszy exact-unique parser:** PowerShell `Group-Object` porównuje case-insensitive, więc błędnie raportował `2321` dla znanej pary `[hidden]/[HIDDEN]`. Komparator .NET `StringComparer.Ordinal` potwierdził `2322` exact unique i `0` exact duplicates; casefold `2321` pozostaje jawnym P2 poza zakresem.
- **Wpływ:** zdarzenia były lokalne i bezprodukcyjne; żadna próba nie użyła sieci, API, browsera, publikacji ani produkcyjnego zapisu. Koszt `0.000000 USD`.

## 2026-08-09 — Model-family core: drabina migracji musiała dojść do 0027

- Pierwsze pełne przebiegi po dodaniu `0027` ujawniły wyłącznie jawne, historyczne oczekiwania zatrzymane na `0026`: listy migracji w research/durable-provider tests, canonical migration count, latest runtime schema oraz operational report. Nie zmieniono znaczenia starych migracji; dopisano dokładny krok `0027` i poprawiono tylko liczniki/latest expectations.
- Pierwsza zbiorcza sonda inwentarza miała błędnie złożoną ścieżkę PowerShell i nie została przyjęta jako dowód. Powtórzono ją osobnymi read-only checks; nie otworzyła produkcji do zapisu i nie dotknęła sieci.
- Ostatnie uszczelnienie migracji zastąpiło placeholdery fingerprintów seed policies rzeczywistymi fingerprintami kontraktów oraz użyło SQL `IS NOT` w triggerze stabilnej roli, aby brakujące pola JSON również blokowały. Po zmianie ponowiono nowe testy, affected i pełną suitę.
- Wynik końcowy: new `31/31`, affected `748/748`, full `2353/2353`, collect/exact unique `2353/2353`, exact duplicates `0`, compile/diff PASS. Brak nierozwiązanego failure implementacji; realny discovery/provider/qualification pozostaje świadomie niewdrożony, nie zamaskowany jako sukces.

## 2026-08-10 — C5 provider contract: wykryte i naprawione regresje QA

- **Pierwszy affected run:** nowe Fable retention precondition poprawnie zablokowało historyczne fake fixtures, które wcześniej nie miały takiego evidence. Fixtures rozszerzono o jawne, request-scoped fake acceptance; osobne testy braku/złej/wygasłej ewidencji nadal omijają helper i dowodzą caller `0`/cost `0`.
- **Pierwsza pełna suita:** 13 failures dotyczyło drabiny schematu i surowych testów migracji. Pierwsza wersja `0030` próbowała przeliczyć fingerprint przez aplikacyjną funkcję SQLite, lecz runner nie gwarantował jej na każdym raw connection. Po przejściowej próbie zachowania starego JSON audyt wykazał niespójność: kolumny mówiłyby `global/standard_only`, a payload nadal `GLOBAL_DEFAULT`. Finalna naprawa rejestruje istniejącą deterministyczną funkcję hash w samym runnerze, kanonicznie przepisuje historyczny `runtime_shape` i przelicza fingerprint. Test seeda realny shape `0029`, migruje go i porównuje JSON/kolumny/hash. Jawne oczekiwania ladder zaktualizowano z `0029` do `0030`; końcowy full po tej korekcie przeszedł `2481/2481` w `509,91 s`.
- **Collect — pozorny duplikat:** pierwsza sonda użyła domyślnie case-insensitive `Sort-Object`/`Group-Object` i błędnie złączyła istniejące case-distinct node IDs `[hidden]` i `[HIDDEN]`, raportując `2480` unique/1 group. Powtórka z `StringComparer.Ordinal` i `Group-Object -CaseSensitive` potwierdziła `2481` exact unique i `0` exact duplicate groups.
- **Nieszkodliwe próby narzędziowe:** kilka wczesnych sond PowerShell/`rg` miało błąd składni albo niepasujący wildcard, a próby punktowego patchowania katalogu nie trafiały przez encoding/context. Wyników nie przyjęto jako dowodu; polecenia powtórzono poprawnie. Nie doszło do sieci, API, zapisu produkcji ani operacji Git.
- **Wynik:** brak nierozwiązanego failure implementacji. Otwarte są decyzja właściciela o retencji oraz niezależny review — to nie są zamaskowane sukcesy ani defekty kodu.

## 2026-08-10 — Fable authority package: brak external policy reference i granica walidacji

- **Finding:** aktywne repo ma wewnętrzne markery owner-verified catalogue, ale nie ma prawdziwego external `provider_policy_ref` dla 30-dniowej retencji Fable. Fixtures zawierają tylko zabronione jako authority `fake://...`.
- **Granica kodu:** SQL poprawnie zamraża exact `provider_policy_ref` w kolumnie/JSON/fingerprint i odrzuca ich rozjazd, lecz pole jest tylko opaque stringiem długości `1..500`, bez URL/domain/FK/source-fingerprint validation. Spójny zmyślony ref byłby technicznie legalny, dlatego nie został użyty jako production candidate.
- **Dodatkowy brak authority:** production `ARTICLE_WRITER` policy nadal jest bootstrapowo `UNVERIFIED`; bez osobnej autoryzacji deterministycznego update nie przejdzie późniejsza activation.
- **Nieszkodliwa próba narzędziowa:** pierwsza read-only sonda FK miała błąd nawiasów w inline Python i zakończyła się przed otwarciem połączenia. Powtórka poprawnie odczytała production przez `mode=ro&immutable=1`; żadnego zapisu ani skutku ubocznego.
- **Status:** pakiet offline jest gotowy do owner input; real qualification pozostaje zablokowana. Nie naprawiano kodu ani schema.
