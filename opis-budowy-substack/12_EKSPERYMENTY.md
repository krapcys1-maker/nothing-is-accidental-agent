# 12 — EKSPERYMENTY

## Cel pliku
Rejestr testów wzrostowych. Każdy: hipoteza, zmienna, okres, metryka sukcesu, wynik, ograniczenia, decyzja po teście. Zasady: jedna główna zmienna naraz, minimum 7 dni, nie zmieniać strategii po jednym poście, zapisać hipotezę **przed** testem.

## Szablon wpisu
```markdown
### EXP-XX — <tytuł>
- **Hipoteza:**
- **Zmienna (jedna):**
- **Grupa/warianty:**
- **Okres:** od–do (≥7 dni)
- **Metryka sukcesu:**
- **Wynik:**
- **Ograniczenia:**
- **Decyzja po teście:**
- **Status:** PLANNED | RUNNING | DONE
```

---

## Stan: brak uruchomionych eksperymentów
Eksperymenty wzrostowe wymagają **realnej publikacji i ruchu** (Etap 4+). Na 2026-07-11 nie ma jeszcze żadnego — poniżej **backlog hipotez** gotowych do uruchomienia, gdy publikacja ruszy.

## Backlog hipotez (PLANNED)

### EXP-01 — Tytuł pytający vs twierdzący
- **Hipoteza:** tytuł w formie pytania („Dlaczego…?") daje wyższy open rate niż twierdzący.
- **Zmienna:** forma tytułu. **Metryka:** open rate / CTR. **Okres:** ≥7 dni, kilka artykułów.
- **Status:** PLANNED.

### EXP-02 — Note z grafiką vs bez grafiki
- **Hipoteza:** Note z prostym diagramem SVG zbiera więcej reakcji/restacków niż sam tekst.
- **Zmienna:** obecność grafiki. **Metryka:** reakcje + restacki na Note. **Status:** PLANNED.

### EXP-03 — Krótki vs średni komentarz
- **Hipoteza:** komentarz 2–3 zdania z jednym mechanizmem daje więcej odpowiedzi/wejść na profil niż dłuższy.
- **Zmienna:** długość komentarza. **Metryka:** replies + profile_visits. **Status:** PLANNED.

### EXP-04 — Publikacja rano vs wieczorem
- **Hipoteza:** pora publikacji wpływa na open rate i pierwsze reakcje.
- **Zmienna:** godzina. **Metryka:** open rate w pierwszych 24h. **Status:** PLANNED.

### EXP-05 — Temat „usługi" vs „przedmioty"
- **Hipoteza:** tematy o usługach (ceny biletów, kolejki) angażują bardziej niż o przedmiotach (QWERTY, kod kreskowy).
- **Zmienna:** kategoria tematu. **Metryka:** komentarze + subskrypcje przypisane. **Status:** PLANNED.

### EXP-06 — Opening „liczba" vs „sprzeczność"
- **Hipoteza:** otwarcie zaskakującą liczbą trzyma czytelnika lepiej niż otwarcie sprzecznością.
- **Zmienna:** typ otwarcia. **Metryka:** czas czytania / dotarcie do końca. **Status:** PLANNED.

## Eksperymenty dot. autonomii (nowe, po ADR-017)
Te „eksperymenty" nie testują treści, tylko samą zdolność systemu do bezpiecznego działania bez człowieka w pętli — to inny rodzaj testu, ale równie ważny dla pytania badawczego projektu.

### EXP-07 — Test wyłącznika SAFE MODE
- **Hipoteza:** SAFE MODE poprawnie wykrywa każdy zdefiniowany trigger (§D.7 planu) i blokuje publikację/komentarze/lajki/subskrypcje, nie blokując researchu.
- **Zmienna:** typ triggera (błędy Playwrighta, wygasła sesja, próg kosztu, wysoki wskaźnik odrzuceń, nietypowa odpowiedź platformy).
- **Metryka sukcesu:** 100% triggerów wykrytych; zero fałszywych negatywów; zero auto-wznowienia bez jawnego resetu.
- **Status:** PLANNED (wymaga zbudowania SAFE MODE — nie zbudowane).

### EXP-08 — Test przejścia LEVEL_1 → LEVEL_2
- **Hipoteza:** po spełnieniu warunków (`docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.3`) system może bezpiecznie działać bez ręcznej akceptacji pojedynczych Notes/komentarzy, utrzymując jakość porównywalną z LEVEL_1.
- **Zmienna:** poziom autonomii (LEVEL_1 z ręczną akceptacją vs LEVEL_2 bez niej, przy tych samych progach scoringu).
- **Metryka sukcesu:** wskaźnik odrzuceń/ukryć po publikacji na LEVEL_2 nie wyższy niż na LEVEL_1; zero naruszeń limitów.
- **Okres:** minimum kilka dni po przejściu, zanim wyciągniemy wnioski.
- **Status:** PLANNED (wymaga osiągnięcia warunków przejścia).

## Ograniczenia metodologiczne (ważne dla uczciwości wyników)
- Substack **nie daje** pełnej atrybucji subskrypcji — część metryk (np. „subskrypcje z komentarzy") będzie **estymacją** oznaczoną `is_estimated`.
- Mały wolumen na starcie = duża wariancja; unikać wniosków po jednym poście.
- Nie zmieniać wielu zmiennych naraz.

## Powiązania
- `docs/experiments/_TEMPLATE.md` (szablon techniczny), `13_WYNIKI_SUBSTACKA.md`, `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` §A.9 (atrybucja)

### [2026-07-13] Eksperyment: czy staged resume zachowa płatne A1/A2

- **Hipoteza:** po uciętym B oficjalny resume ze stanu SOURCES_COMPLETE wykona tylko jedno B, nie dublując discovery/extraction ani prior usage.
- **Kontrola:** run `c01171bc`, 4 VERIFIED, prior 0,170050, `max_retries=0`, B=3000, absolutny cap 0,20; pełny read-only preflight i PolicyEngine przed klientem.
- **Wynik:** dokładnie jeden nowy usage `research_synthesize_cards`, zero search, 1904/2402 tokenów, 0,013914 USD; A1/A2 bez nowych wpisów. SUCCESS/COMPLETE/USED, card #2.
- **Wniosek:** hipoteza potwierdzona technicznie; karta jakościowo REJECT, więc odporność wykonawcza nie zastępuje bramki dowodowej.

## [2026-07-13] Proponowane eksperymenty redakcyjne — bez uruchomienia

Blueprint dodaje propozycje EXP-G1–EXP-G5: typ otwarcia, format Note, pojedynczy CTA, tytuł i rotację formatów. Każdy zmienia jedną zmienną, ma minimalny czas lub n≥30 i nie może obchodzić fact audit, SEO contractu ani granic autonomii.

Wynik przy n<30 będzie oznaczany **SIGNAL, NOT PROOF**. To opis przyszłego Etapu 7, nie wykonany test i nie podstawa do zmiany strategii.

## [2026-07-13] E1–E10 z raportu Fable — backlog, nie wyniki

Pełny raport zapisuje dziesięć proponowanych eksperymentów E1–E10 wraz z hipotezą, zmienną, metryką, minimalnym czasem, kryterium decyzji i ryzykiem małej próby. Są one zmapowane na Etap 7 i nie uruchomiono żadnego z nich. Reguła pozostaje bez zmian: `n < 30 = SIGNAL, NOT PROOF`.

## [2026-07-13] Kontrola utrzymaniowa Etapu 1 — nie jest eksperymentem redakcyjnym

`MaintenanceRunner` testuje tylko trwałość lokalnego recovery/reapera: kolejność recovery→reaper, brak nakładających się cykli, fail-closed błędów z zachowaniem primary/cleanup diagnostic oraz zachowanie SQLite po close→reopen w dwóch połączeniach. Nie generuje treści, nie publikuje i nie mierzy reakcji odbiorców, dlatego nie jest wynikiem ani uruchomieniem EXP-01–EXP-08, E1–E10 lub eksperymentu wzrostowego. Status techniczny: one-shot/poll VERIFIED OFFLINE; system scheduler/service NOT_STARTED. Polityka okien redakcyjnych została później zweryfikowana offline jako osobna kontrola techniczna poniżej; koszt 0 USD.

## [2026-07-13] Polityka okien redakcyjnych — kontrola techniczna, nie eksperyment

Deterministyczne wyznaczenie `earliest_run_at` i `schedule_reason` przed enqueue nie tworzy artykułu, Note’a, publikacji ani wariantu E1–E10. Testuje wyłącznie lokalną regułę: IANA/DST, okno, czas wskazany przez operatora i eligibility claimu. Job oczekujący nie jest uruchamiany ani obserwowany na Substacku, więc nie istnieje hipoteza, metryka ani wynik eksperymentu. Status techniczny: polityka okien i claim eligibility VERIFIED OFFLINE; koszt 0 USD.

## [2026-07-13] Final restart acceptance — kontrola techniczna, nie eksperyment wzrostowy

To nie jest test odbiorców ani publikacji. Zbiór 14 scenariuszy odtwarzał wyłącznie lokalne stany SQLite: crash przed commitem i po nim, recovery, stale-owner fencing, future-job boundary, parity direct service–worker i integrity. Najważniejszy wynik: atomowa inicjalizacja run/research_run/`job.run_id` nie zostawia osieroconego kompletu i nie tworzy dubla po restarcie.

Nie zmieniły się żadne metryki Substacka, nie wykonano API ani realnego researchu, a koszt rzeczywisty wyniósł 0 USD. Wynik techniczny: Etap 1 candidate complete, awaiting independent review; system scheduler/service nadal NOT_STARTED.
## [2026-07-13] Old-owner fencing — kontrola bezpieczeństwa, nie eksperyment

Macierz 26 restart acceptance tests nie uruchamia hipotezy redakcyjnej ani wariantu wzrostowego. Sprawdza wyłącznie lokalny inwariant: po expiry/recovery stary worker nie zapisze usage, kosztu, karty ani terminalnego statusu, a recovery i stale write na dwóch połączeniach SQLite nie mogą oba wygrać.

Nie wykonano API, browsera, publikacji, researchu live ani obserwacji odbiorców. Wynik techniczny: 667 testów zielonych, Etap 1 candidate awaiting independent review, koszt 0 USD. EXP-01–EXP-08 i E1–E10 pozostają nieuruchomione.

## [2026-07-13] Post-lock lease i CSV — kontrola techniczna, nie eksperyment

Siedem scenariuszy odpala operacje kolejki przed expiry i blokuje je na prawdziwym `BEGIN IMMEDIATE`, aby zegar przekroczył expiry przed dopuszczeniem zapisu. Osobne testy sprawdzają race heartbeat↔recovery, awarię pochodnego `COSTS.csv` i atomowy failure po inicjalizacji. To test praw zapisu i trwałości, nie wariant treści, hipoteza wzrostowa ani obserwacja odbiorców.

Nie uruchomiono API, browsera, publikacji ani realnego researchu. Wynik: 42 restart acceptance, 683 testy, `integrity_check=ok`, koszt 0 USD; Etap 1 pozostaje candidate awaiting independent review. EXP-01–EXP-08 i E1–E10 nie zmieniły statusu.

## [2026-07-14] Zamknięty wynik dispatchu — kontrola techniczna, nie eksperyment wzrostowy

Test nie mierzył odbiorców ani treści. Na syntetycznej plikowej SQLite odtworzono kontrolowany failure RESEARCH, błędny string zamiast enumu oraz świadomie uszkodzony wynik po realnym atomic success. Badano wyłącznie inwariant: po terminalizacji workflow worker nie ma prawa do dalszego canonical write.

Wynik: `WORKFLOW_FAILED` nie wywołuje generic `fail_job`; malformed result kończy się jawnym błędem kontraktu bez heartbeat, completion, failure albo `LOST_LEASE`; atomic success pozostaje DONE/COMPLETE/USED z kartą po reopen. Dodatkowy fault test zachowuje primary error, gdy rollback sam zawodzi. 58 acceptance i pełny suite 700 passed, `integrity_check=ok`, koszt 0 USD. Nie uruchomiono API, browsera, publikacji ani realnego researchu; EXP-01–EXP-08 i E1–E10 pozostają PLANNED.

## [2026-07-14] Zamknięcie WAVE 0A nie jest eksperymentem

Niezależne review potwierdziło P0=0 i P1=0 dla WAVE 0A, a kontrola bazy potwierdziła zachowanie realnych danych po logicznym odtworzeniu. To wciąż nie jest eksperyment z odbiorcami, wzrostem ani publikacją: nie użyto API, browsera, sieci ani kosztu. WAVE 0A została formalnie zamknięta jako **APPROVED WITH P2**; Etap 1 pozostaje BLOCKED przez inne P1, a E1–E10 nie zmieniają statusu.

## 2026-08-09 — Kontrpróba pytań, nie eksperyment publikacyjny

Lokalna macierz 50 factual, 25 non-factual oraz 55 dodatkowych question forms badała wyłącznie inwariant claim accounting. Wynik: zero prose shortcuts dla pytań, zachowana honest-inference route i jawna trust boundary. Nie było odbiorców, wariantu treści, publikacji, sieci ani kosztu; EXP-01–EXP-08 pozostają bez zmiany.
