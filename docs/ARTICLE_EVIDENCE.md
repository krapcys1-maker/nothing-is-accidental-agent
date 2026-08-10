# ARTICLE_EVIDENCE

## Sekcja B — 2026-08-10: „Schema i ledger muszą mówić prawdę razem”

- **Fakt:** migracja może przejść cały happy path, a mimo to mieć niebezpieczne okno awarii: schema jest już trwałe, lecz kanoniczny ledger nadal wskazuje poprzedni head.
- **Decyzja:** `0026` i `0027` korzystają z jednej istniejącej transakcji runnera dla SQL i `schema_migrations`; po kontrolowanym błędzie oba elementy cofają się razem.
- **Dowód:** failpoint, zamknięcie połączenia, reopen i retry dla obu migracji; 4/4 nowych, 74/74 affected oraz świeży rehearsal `0020→0030` z zachowaniem danych 32 tabel i zerem mismatchów.
- **Zdanie robocze:** „System migracyjny nie jest spójny dlatego, że doszedł do końca. Jest spójny wtedy, gdy po przerwaniu potrafi jednoznacznie powiedzieć, czego jeszcze nie zrobił.”

## Sekcja B — 2026-07-16: „Błąd obsłużony może być groźniejszy niż crash”

- **Fakt:** czwarty niezależny review pokazał, że proces nie musiał się zawiesić, aby zgubić drogę do rozliczenia. Lokalny błąd został „poprawnie” złapany przez Workera, lecz fallback zamknął job jako `FAILED` i pozostawił rozpoczętą próbę poza kolejką operatora.
- **Decyzja:** terminalizacja researchu nie jest już lokalną decyzją Workera. Jedna atomowa granica sprawdza durable provider attempt: bez próby kończy wykonanie, a przy `RESERVED`/`REQUEST_STARTED` eskaluje do widocznego reconciliation i zachowuje rezerwację do decyzji człowieka.
- **Dowód:** dokładna kontrpróba przez `Worker.run_once`, 29 nowych testów i baseline **1036/1036**; ten sam inwariant sprawdzony przez reopen, recovery, reaper, resolver, budżet, surowy SQLite i 30-krotne wyścigi. Zero provider calli i kosztu.
- **Zdanie robocze:** „Najgroźniejsza awaria nie zawsze zabija proces. Czasem zostawia zielony log, zamknięty job i rachunek, którego nikt nie potrafi już rozstrzygnąć.”

## Sekcja B — 2026-07-15: „Rachunek nie jest jeszcze wynikiem"

- **Fakt:** po niepewnym callu system może wiedzieć, że zapłacił, nie wiedząc, czy powstała użyteczna karta; albo mieć kartę, której koszt wymaga jeszcze udowodnienia.
- **Decyzja:** WAVE 1A rozdziela trzy decyzje o pieniądzach od trzech decyzji o wykonaniu. Jedyna księga kosztu to `model_usage`; `CHARGE_UNKNOWN` pozostaje uczciwym brakiem wiedzy. Operator nie dostaje przycisku retry ani tworzenia wyniku.
- **Dowód:** migracja 0014 (poprawiana in place po kolejnych `REJECTED — MAJOR`), append-only `reconciliation_events`, pełna tożsamość usage, wyłączna własność karty, pełna walidacja lineage (`W1A-VERIFY-02`), centralna granica failure→reconciliation (`W1A-R4-01`), atomic resolver, **1036 testów offline**, rollback po każdym istotnym kroku, dwa konkurencyjne połączenia i niezmieniona chroniona baza. (Historyczne 1007/919/894/948/955 to wcześniejsze iteracje.)
- **Zdanie robocze:** „Najłatwiej oszukać system nie wtedy, gdy zgubi rachunek, lecz wtedy, gdy z rachunku próbuje zrobić wynik."

## Cel

Zbiornik wyselekcjonowanego, cytowalnego materiału dowodowego. Rozdzielony na dwa niezależne strumienie, bo obsługują dwa różne teksty:

- **Sekcja A — Evidence for publication content:** dowody i materiał źródłowy pod treści samej publikacji „Nothing Is Accidental" (artykuły, Notes) — czyli to, co uwiarygadnia konkretne twierdzenia w tekstach po angielsku.
- **Sekcja B — Evidence for the final Chaos Engine case study:** materiał do końcowego artykułu o eksperymencie **„Dałem agentowi AI 30 dni, własny Substack i budżet 40 dolarów"** — chronologia, koszty, błędy, decyzje, wzrost.

To nie jest dziennik bieżący (od tego są BUILD_LOG / ERRORS / RESEARCH_LOG / METRICS_LOG) — tu ląduje esencja. Per-artykułowe dowody źródłowe (źródła, fakty) mają dom w `RESEARCH_LOG.md`; sekcja A linkuje do nich i wybiera najmocniejsze.

**Nie piszemy żadnego z tych tekstów teraz.** Zbieramy amunicję na bieżąco.

## Zasady

- Dodawaj pozycję, gdy zdarzy się coś wartościowego dla narracji (dobry lub zły przykład).
- Każda liczba z kontekstem i źródłem (link do wpisu w COSTS/METRICS/ERRORS).
- Zachowuj też porażki — są najlepszym materiałem.
- Bez sekretów i danych osobowych.

## Sekcja A — Evidence for publication content

Dowody pod treści publikacji „Nothing Is Accidental" (artykuły, Notes). Cel: żadne twierdzenie nie idzie do publikacji bez pokrycia.

### A1. Najmocniejsze źródła per temat
_(link do RESEARCH_LOG.md; wybór 1–3 najlepszych źródeł)_

### A2. Cytowalne liczby (z kontekstem)
_(liczba — baza/okres/jednostka/źródło; gotowe do wstawienia w tekst)_

### A3. Mechanizmy wyjaśnione dobrze
_(fragmenty, w których agent trafnie rozłożył zjawisko na system)_

### A4. Sprzeczności i niepewności ujawnione uczciwie
_(miejsca, gdzie tekst przyznał granice wiedzy — dowód rzetelności)_

### A5. Odrzucone twierdzenia / wychwycone halucynacje
_(co odpadło na audycie faktów i dlaczego)_

### A6. Dobre i słabe tytuły/otwarcia
_(warianty + który wybrano i dlaczego)_

---

## Sekcja B — Evidence for the final Chaos Engine case study

Materiał do końcowego artykułu o eksperymencie („30 dni, własny Substack, ~40 USD").

### 1. Chronologia i kamienie milowe
_(najważniejsze momenty: pierwsza wersja, pierwsza publikacja, pierwszy subskrybent…)_

### 2. Najważniejsze decyzje
_(link do DECISIONS.md — ADR-XXX; dlaczego były ważne)_

### 3. Największe błędy i awarie
_(link do ERRORS_AND_FAILURES.md; co poszło nie tak i czego nauczyło)_

### 4. Najbardziej zaskakujące wyniki
_(kontrintuicyjne dane o wzroście lub jakości)_

### 5. Gdzie agent był lepszy od człowieka
_(konkretne przypadki + dowód)_

### 6. Gdzie agent bez człowieka sobie nie poradził
_(konkretne przypadki + interwencja z HUMAN_INTERVENTIONS.md)_

### 7. Prawdziwe koszty
_(podsumowanie z COSTS.csv: koszt/artykuł, koszt/subskrybent — oznacz estymacje)_

### 8. Czas pracy człowieka
_(suma z HUMAN_INTERVENTIONS.md / METRICS_LOG.md)_

### 9. Dane o wzroście
_(kluczowe liczby z METRICS_LOG.md)_

### 10. Przykłady dobrych i złych komentarzy
_(cytaty + dlaczego dobry/zły)_

### 11. Przykłady dobrych i złych tematów
_(temat + score + jak wypadł)_

### 12. Przykłady odrzuconych grafik
_(opis + powód odrzucenia; SVG w MVP)_

### 13. Cytowalne liczby
_(liczba — baza/okres/jednostka/źródło)_

### 14. Najlepsze screenshoty
_(nazwy plików z SCREENSHOT_INDEX.md)_

### 15. Plan vs rzeczywistość
_(gdzie IMPLEMENTATION_PLAN.md się sprawdził, a gdzie nie)_

## Szablon pojedynczej pozycji

```markdown
- **[YYYY-MM-DD] Tytuł materiału** (sekcja: nr)
  - Co to jest: ...
  - Dlaczego trafi do artykułu: ...
  - Dowód / źródło: link do wpisu (ERRORS/COSTS/METRICS/SCREENSHOT/DECISIONS)
  - Cytowalna liczba lub cytat (jeśli jest): ...
```

---

## Zebrany materiał — Sekcja A (publikacja)

_(brak — pierwsze pozycje pojawią się przy pierwszym researchu/artykule)_

## Zebrany materiał — Sekcja B (case study)

- **[2026-07-11] Pipeline researchu z bramką jakości i ochroną przed prompt injection** (sekcja: 4, 5)
  - Co to jest: agent prowadzi research (web search), buduje Research Card, ale deterministyczna bramka może go odrzucić (za mało źródeł, teza bez poparcia, sprzeczne źródła), a treść stron jest traktowana jako niezaufana.
  - Dlaczego trafi do artykułu: pokazuje, gdzie autonomia jest kontrolowana — model nie decyduje sam o jakości, a próba „prompt injection" ze strony nie zmienia jego decyzji.
  - Dowód / źródło: docs/DECISIONS.md ADR-015, docs/CODE_EXAMPLES.md (injection), tests/test_research_pipeline.py.
  - Cytowalna liczba: koszt jednego symulowanego researchu ~0.0492 USD (dry_run, z 4 web searchami); 44 testy zielone.

- **[2026-07-11] Deduplikacja bez dodatkowego kosztu** (sekcja: 2)
  - Co to jest: agent nie zapisuje ponownie tego samego/parafrazowanego tematu; dedup jest lokalny (0 USD).
  - Dlaczego trafi do artykułu: przykład decyzji „taniej i deterministycznie zamiast płatnego modelu".
  - Dowód / źródło: docs/DECISIONS.md ADR-014, live: powtórny `run-topics` → DUPLICATE=6.

- **[2026-07-11] Pierwsze realne wywołanie: JSON ucięty + odkryty bug księgowania kosztu + błędny estymator (naprawione tego samego dnia)** (sekcja: 3, 5, 6)
  - Co to jest: pierwsza, jawnie zatwierdzona przez właściciela, realna (płatna) próba researchu (temat „suitcase after check-in") dotarła do API i użyła web search, ale zwróciła ucięty JSON — Research Card nie powstała. Ujawniło to DWA błędy: (1) realny koszt takiego nieudanego wywołania w ogóle nie trafiał do księgowości (`cost_usd=0.00` mimo realnego wywołania) — naprawione od razu; (2) po zweryfikowaniu w konsoli Anthropic okazało się, że rzeczywisty koszt (0.25 USD) był 2,63× wyższy niż pesymistyczny szacunek sprzed wywołania (0.095 USD, błąd ~+163%) — estymator naprawiony, pipeline przebudowany na dwuetapowy (gather_sources + synthesize_card, ADR-016).
  - Dlaczego trafi do artykułu: to najbardziej autentyczny dotychczasowy przykład „gdzie agent (i jego twórca) zawiódł" — zderzenie planu z rzeczywistością API, DWIE osobne pomyłki (księgowa i estymacyjna) znalezione i naprawione na żywo, z testami regresyjnymi, bez ukrywania żadnej z nich. Mocny materiał do „Artykułu 8: Gdzie agent zawiódł" i „Artykułu 7: Ile kosztuje" (pokazuje zarówno jak koszt może „zniknąć" bez dyscypliny księgowej, jak i jak zawodny bywa szacunek kosztu PRZED wywołaniem).
  - Dowód / źródło: docs/ERRORS_AND_FAILURES.md (3 wpisy: 19:09 UTC „ucięty JSON", 19:09 UTC „realny koszt zgubiony", „Pre-flight cost estimator underestimated the real cost"), docs/BUILD_LOG.md (Etap 1C + Etap 1D), docs/DECISIONS.md ADR-016, docs/COSTS.csv (skorygowany wiersz z realną kwotą), tests/test_cost_estimator.py, tests/test_research_two_stage_pipeline.py.
  - Cytowalna liczba: cap runu 0.30 USD; **rzeczywisty koszt: 0.25 USD** (potwierdzony w konsoli Anthropic); pierwotny szacunek 0.095 USD, błąd +163%; 63 testy zielone po obu naprawach (było 44 przed incydentem).

- **[2026-07-12] Jedna diagnostyka rozdzieliła trzy różne liczby kosztu** (sekcja: 3, 7, 13, 15)
  - Co to jest: pierwsze podejście nie wyszło poza komputer (stary `anthropic==0.37.1` przekazywał usunięty argument `proxies` do `httpx==0.28.1`) i kosztowało 0 USD. Po aktualizacji projektowego SDK do 0.116.0 pojedyncza diagnostyka kandydata `id=3` zakończyła się poprawnie przy 915 output tokens. Jednorazowe `max_tokens=5000` było tylko sufitem diagnostycznym; produkcyjny default ustalono na 1500. Kandydatów 1 i 2 nie ponawiano.
  - Dlaczego trafi do artykułu: pokazuje, jak łatwo pomylić koszt jednego calla z kosztem skumulowanym runu oraz jak „bezpieczny sufit" kosztowy może być użyteczny, choć bardzo niedokładny.
  - Dowód / źródło: `docs/ERRORS_AND_FAILURES.md` (wpisy o SDK i diagnostyce A2), `docs/BUILD_LOG.md` Etap 1M, `docs/COSTS.csv` (wiersz source candidate `id=3`).
  - Cytowalne liczby: lokalna porażka = **0,00 USD**; diagnostyczny call = **0,028969 USD**; skumulowany koszt runu = **0,126793 USD**; skumulowany realny koszt projektu = **0,500616 USD**; conservative estimate 0,1256 USD = około **4,34×** kosztu calla, więc bezpieczny, lecz nie „dokładny".

- **[2026-07-12] Pierwszy prywatny snapshot projektu na GitHub** (sekcja: 1, 2, 14)
  - Co to jest: po audycie sekretów projekt dostał pierwszy commit (`df418dd`) na `main`, prywatne repozytorium GitHub i osobny branch `dev/a2-stabilization`.
  - Dlaczego trafi do artykułu: wyznacza odtwarzalny punkt początkowy eksperymentu i pokazuje, że bezpieczeństwo danych było częścią procesu, nie porządkiem dodanym po fakcie.
  - Dowód / źródło: `docs/BUILD_LOG.md` Etap 1N, ADR-021, przyszły screenshot `private-github-repository` w `docs/SCREENSHOT_INDEX.md`.
  - Cytowalna liczba: 125 plików w initial commit; 124 staged pliki tekstowe przeskanowane; 0 realnych sekretów; 102 testy zielone.

- **[2026-07-12] Ile kosztuje próba zdobycia pierwszej kompletnej Research Card — zanim wydamy pieniądze** (sekcja: 2, 7, 13, 15)
  - Co to jest: offline pre-flight świeżego A1/A2/B z czterema źródłami, jednym searchem na źródło, A2=1500 i retry=0.
  - Dlaczego trafi do artykułu: pokazuje różnicę między expected (typowy punkt odniesienia), conservative (bramka z marginesem) i approved cap; dokumentuje też decyzję, by kupić tolerancję jednej awarii A2 czwartym źródłem.
  - Dowód / źródło: `scripts/run_capped_research.py --estimate-only`, `docs/BUILD_LOG.md` Etap 1O, ADR-022.
  - Cytowalne liczby: A1 0,033956/0,092625 USD; A2×4 0,153824/0,397500; B 0,013500/0,020250; TOTAL expected **0,201280**, conservative **0,510375**, proponowany cap **0,55 USD**; pełny test suite 102 passed; koszt przygotowania 0 USD.

- **[2026-07-12] Cache kosztu nie może być drugim księgowym** (sekcja: 5, 7)
  - Co to jest: po rozbiciu researchu na A1/A2/B pojedynczy run może zakończyć się w wielu miejscach. `runs.cost_usd` jest wygodnym podsumowaniem, ale jedynym kanonem pozostaje append-only `model_usage`; dla researchu INSERT usage i absolutne ustawienie cache'a na aktualną sumę należą do jednej transakcji SQLite.
  - Dlaczego trafi do artykułu: to mały, konkretny przykład rozróżnienia między księgą zdarzeń a stanem pochodnym — szczególnie ważny przy awarii po płatnym callu albo wznowieniu procesu.
  - Dowód / źródło: `app/storage/repositories.py`, `app/workflows/research/pipeline.py`, `tests/test_staged_research_extraction.py`, BUILD_LOG Etap 0 / zadanie 2.
  - Cytowalne liczby: **139** testów zielonych; **12** regresji Task 2 i poprawek po review; WAL potwierdzany dla połączeń plikowych, timeout **5000 ms**; koszt implementacji/testów **0 USD**.

- **[2026-07-12] Retry nie może udawać zwykłego wznowienia** (Etap 0 / Task 3)
  - Fakt: historyczny run `9bbeb020` miał dwa `EXTRACTION_FAILED`; zwykłe resume odczytywało wyłącznie pending, więc nie mogło potajemnie spróbować jeszcze raz ani domknąć brakujących źródeł.
  - Decyzja: `attempts` liczy rozpoczęte A2; retry jest osobną komendą, domyślny cap to 2 próby łącznie, a sam reset nie tworzy `model_usage` ani kosztu.
  - Kontrast do wykorzystania w artykule: bezpieczeństwo nie polega na zakazie retry, lecz na tym, aby moment podjęcia ryzyka i jego limit były widoczne oraz świadome.
  - Dowód: migracja 0007 zastosowana na pamięciowej kopii bazy (`integrity_check=ok`, `foreign_key_check=[]`), 14 nowych regresji, **153 passed**, koszt **0 USD**, zero API i realnego researchu.

- **[2026-07-12] Licznik nie jest dowodem, że request się wydarzył** (korekta Task 3 po review)
  - Fakt: inkrementacja „tuż przed callem” tworzy crash-window; bez osobnego stanu zwykłe resume nie rozróżnia nieprzetworzonego źródła od requestu o nieznanym skutku.
  - Decyzja: `attempts` to zarezerwowana próba, a `EXTRACTION_IN_PROGRESS` jest uczciwym zapisem niepewności. Historyczne statusy dają tylko dolną granicę 0/1, nie wymyśloną historię.
  - Kontrast do artykułu: system nie stał się bezpieczny dlatego, że dodał licznik; stał się bezpieczniejszy, gdy przestał udawać wiedzę o skutku przerwanego działania.
  - Dowód: reprodukcje `2→3`, historyczne ≥3 calle przy capie 2 oraz rollback DDL+ledgeru; 87 testów celowanych, **164 passed**, 0 USD i zero API.

- **[2026-07-12] Słowo „complete” zmienia ekonomię następnego kliknięcia** (Etap 0 / Task 4)
  - Fakt: kompletna karta nie jest „kolejnym kandydatem do retry”. Drugi świeży research może kosztować, więc system ustawia temat jako `USED` i odmawia przed klientem API.
  - Decyzja: tylko jawne `--force-re-research` otwiera nowy run; force nie omija budżetu, capu, kill switcha ani polityki.
  - Kontrast do artykułu: dobre zabezpieczenie nie zabrania działania na zawsze — sprawia, że kosztowna decyzja jest nazwana, widoczna i audytowalna.
  - Dowód: trzy flow aktualizują `USED`; test CLI zabrania nawet konstrukcji klienta bez force; **169 passed**, 0 USD i zero API.

- **[2026-07-12] Atomowość nie kończy się na dwóch kolumnach** (korekta Task 4 po review)
  - Fakt: `COMPLETE → USED` może nadal zostawić fałszywy sukces, jeśli karta należy do innego tematu albo `runs.SUCCESS` został zatwierdzony poza transakcją końcową.
  - Decyzja: jedna finalizacja waliduje run–topic–card–account i razem zapisuje COMPLETE, terminalny run oraz USED; uszkodzony USED/COMPLETE zatrzymuje się fail-closed, nawet przy force.
  - Kontrast do artykułu: transakcja nie jest nazwą dla dwóch UPDATE. Jej granica musi obejmować cały sens biznesowy zdarzenia.
  - Dowód: trwały rollback triggerów SQLite po reopen dla single/two-stage/staged, pre-guard runnera i **186 passed**, 0 USD, zero API.

- **[2026-07-12] Atomowość i idempotencja odpowiadają na dwa różne pytania** (drugie review Task 4)
  - Fakt: jedna transakcja chroniła pierwszą finalizację, ale jej ponowienie mogło przepiąć kartę 1→2 oraz koszt 0,1→0,9 USD.
  - Decyzja: identyczne powtórzenie jest no-op bez dotknięcia timestampów; każda różnica albo uszkodzony COMPLETE jest odmową z rollbackiem.
  - Kontrast do artykułu: „wszystko albo nic” nie znaczy „drugi raz niczego nie zmieni”. Audytowalny system potrzebuje obu własności osobno.
  - Dowód: plikowa SQLite z reopen, pełna macierz refinalizacji i force/failure dla trzech flow; **206 passed**, koszt 0 USD.

- **[2026-07-12] Poprawny kod bez testu nadal nie jest zamkniętym kontraktem** (trzecie review Task 4)
  - Fakt: kod już odrzucał sprzeczny Stage B oraz obcy topic/account, ale review słusznie nie uznało zachowania za udowodnione bez jawnych regresji i pełnych liczników tabel.
  - Dowód: negatywna macierz single/two-stage/staged, plikowa SQLite z reopen, karty obcego topicu/konta i cztery liczniki po odmowie; **212 passed**, 0 USD, zero API.
  - P2 do przyszłego tekstu: dokładne `float == float` może fałszywie odrzucić idempotentny koszt (`0.1 + 0.2` vs `0.3`), ale fail-closed nie pozwala nadpisać historii.

- **[2026-07-12] Pre-flight nie chroni przed drugim rachunkiem** (Etap 0 / Task 5)
  - Materiał: retry timeoutu jest osobnym potencjalnie płatnym callem; przy `base=0.08 USD` i `max_retries=2` worst-case wynosi `0.24 USD`, nie `0.16 USD`.
  - Decyzja: jedna polityka w bibliotece, callback przed każdą próbą i odczyt aktualnego `model_usage`; CLI nie ma własnej matematyki limitów.
  - Uczciwe ograniczenie: `timeout-billed-unrecorded` — brak usage nie dowodzi braku opłaty, a system nie wymyśla kosztu.
  - Zwrot narracyjny po review: „cap per-run” nie jest capem, jeśli resume przelicza go jako dotychczasowy koszt plus nowy kredyt; green suite nie testował tej semantyki.
  - Dowód: ADR-026, `tests/test_research_run_budget.py`, BUILD_LOG Task 5; **257 passed**, koszt 0 USD, brak API.

- **[2026-07-12] Rachunek może zniknąć między odpowiedzią a nawiasem klamrowym** (Etap 0 / Task 6)
  - Materiał: provider zdążył zwrócić odpowiedź i usage, ale `json.loads` padał wcześniej niż kod budujący lokalny rekord kosztu.
  - Decyzja: kolejność ma znaczenie biznesowe — response → `Usage` → parse. Parser error niesie usage/model do workflow; provider error bez odpowiedzi nie tworzy fikcyjnego kosztu.
  - Code fence: `````json````` jest częstym, nieszkodliwym opakowaniem odpowiedzi modelu. System zdejmuje dokładnie jeden pełny fence, lecz nie wycina tekstu przed/po JSON-ie i nie „naprawia” uciętych danych.
  - Dlaczego bez retry: zły format nie jest timeoutem; drugi call oznaczałby drugi możliwy rachunek zamiast deterministycznej odmowy.
  - Dowód: fake SDK, rzeczywista SQLite, jeden `model_usage`, `runs.FAILED`, zero topics; **286 passed**, koszt 0 USD, brak API.

- **[2026-07-12] Decyzja wdrożona, ale nadal „proponowana”** (Etap 0 / Task 7)
  - Materiał: pięć ADR-ów od tygodni sterowało configiem, granicami MVP, publikacją i izolacją kont, lecz rejestr nadal nazywał je `PROPOSED`.
  - Metoda: każdy wpis porównano z trzema źródłami prawdy i kodem/configiem; status zmieniono dopiero po potwierdzeniu wdrożenia oraz braku nowszego ADR supersedującego decyzję.
  - Ciekawy przypadek: ADR-005 mówił historycznie o publikacji „od Etapu 4”, podczas gdy skonsolidowana roadmapa przeniosła adapter publikacyjny do Etapu 5. To zmiana numeracji, nie decyzji bezpieczeństwa — system nadal fizycznie nie publikuje.
  - Dowód: pięć statusów `ACCEPTED`, jawna tabela weryfikacji w `docs/DECISIONS.md`, **286 passed**, zero zmian kodu, 0 USD i brak API.

- **[2026-07-12] Status to porównanie i zapis, nie dwa osobne kroki** (Etap 0 / Task 8)
  - Materiał: ślepy `UPDATE ... WHERE id=?` pozwala spóźnionemu procesowi nadpisać stan, który zdążył już przejść dalej. Poprzedzający SELECT nie rozwiązuje race, bo prawda może zmienić się między zapytaniami.
  - Decyzja: warunek źródłowego statusu jest częścią tego samego UPDATE, a `rowcount` staje się wynikiem próby przejścia. Po zerze wierszy system odczytuje stan wyłącznie dla diagnostyki i odmawia typowanym błędem.
  - Kontrast: idempotencja nie oznacza „ignoruj rowcount=0”. Każdy no-op jest jawnym kontraktem; resume może mieć inną regułę niż terminalna finalizacja.
  - Dowód: dwa połączenia do plikowej SQLite, jeden zwycięzca terminalizacji, resume i claimu, rollback Stage A/A1 sprawdzony po reopen; **330 passed**, 0 USD, brak API.

- **[2026-07-13] Dwa połączenia nie tworzą jeszcze wyścigu** (korekta review Task 8)
  - Materiał: wcześniejszy test uruchamiał drugi claim dopiero po commicie pierwszego, więc dowodził tylko odmowy dla starego snapshotu. `Barrier` wymusił rzeczywiście wspólny start dwóch osobnych połączeń.
  - Druga lekcja: wyjątek nazwany „resume” nie jest jawny, jeśli siedzi w ogólnym helperze terminalizacji. Nowy helper wymaga kompletnej relacji researchu i tokenu CAS sprzed próby.
  - Nieudana iteracja: transakcja rozpoczęta przed SELECT dała lock upgrade zamiast domenowego konfliktu. Warunkowy UPDATE bez wcześniejszego read-locka dał jednego zwycięzcę i typowaną odmowę drugiego.
  - Dowód: oba race tests ×10, stan po reopen, `attempts=1`, `EXTRACTION_IN_PROGRESS`; **337 passed**, 0 USD, brak API.

- **[2026-07-13] Cztery poprawne źródła nadal nie są kartą** (Etap 0 / Task 9)
  - Materiał: pierwszy realny staged run przeszedł A1 i cztery niezależne A2; wszystkie źródła zostały EXTRACTED/VERIFIED. Dopiero B wyczerpało 2200 tokenów i urwało JSON wewnątrz stringa.
  - Liczby: conservative 0,510375 USD, cap 0,55 USD, koszt rzeczywisty 0,170050 USD; A1 0,029243, A2 0,127903, B 0,012904; 5 web searchy, zero retry.
  - Zwrot narracyjny: trwałość etapów zadziałała — cztery opłacone karty źródłowe nie zniknęły. Jednocześnie sukces podzadań nie pozwala ogłosić sukcesu produktu: brak Research Card oznacza REJECT.
  - Dodatkowy finding: proces się skończył, ale ogólny audit pozostał RUNNING. To dobry przykład różnicy między odzyskiwalnością danych a prawdziwością statusu.
  - Dowód: run `c01171bc-7ff5-4b83-bbfa-c0b164137793`, sześć wpisów `model_usage`, prywatne nagłówki diagnostyki z `stop_reason`; brak retry/resume/publikacji.

- **2026-07-13 — naprawa po prawdziwym rachunku, lecz bez kolejnego rachunku:**
  - Incydent rozdzielono na dwa P1: semantyczny truncation (`max_tokens`) i nieprawdziwy audit `RUNNING`.
  - Minimalna korekta: limit 3000 (+36%), zwięzły schema prompt, zero auto-retry; conservative B 0,026250 USD, fresh 0,516375 USD, projected resume 0,196300 USD.
  - Test na plikowej SQLite dowodzi, że źródła zostają w `SOURCES_COMPLETE`, audit kończy się `FAILED`, a karta nie powstaje częściowo; osobne testy zachowują salvage JSONL A1 i liczą prior usage dokładnie raz. 351 testów offline, koszt dodatkowy 0 USD.
  - Historycznej bazy nie „upiększono”; plan repair jest osobnym, audytowalnym krokiem wymagającym zgody. To dowód, że dokumentacja odróżnia naprawiony kod od naprawionych danych.

- **[2026-07-13] Historia poprawiona jawnie, nie po cichu** (sekcja: 3, 6, 15)
  - Materiał: po osobnej zgodzie właściciela wykonano lokalną operację maintenance na historycznym runie Task 9. Backup SQLite, SHA-256, snapshoty logiczne i warunkowy UPDATE pozwoliły wykazać, że zmieniły się tylko `runs.status`, `runs.finished_at` i `runs.error`.
  - Liczby: `rowcount=1`; 4 candidates nadal EXTRACTED/VERIFIED, 6 wpisów usage nadal sumuje się do 0,170050 USD, brak Research Card; dodatkowy koszt 0 USD.
  - Dlaczego trafi do artykułu: pokazuje różnicę między korektą prawdziwości auditu a przepisywaniem historii. Opłacone dane i wznawialny `SOURCES_COMPLETE` zostały zachowane, lecz zakończony proces nie figuruje już jako `RUNNING`.
  - Dowód: `docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md`, `docs/HUMAN_INTERVENTIONS.md`; bez API i bez resume.

- **[2026-07-13] Pierwsza realna karta powstała dzięki resume, ale sama powiedziała „nie publikuj”** (sekcja: 3, 4, 6, 7, 15)
  - Materiał: po zachowaniu czterech opłaconych źródeł i jawnym repairze auditu wykonano dokładnie jedno B. `end_turn` przy 2402 tokenach utworzył kartę #2 bez powtarzania A1/A2.
  - Liczby: prior 0,170050; conservative B 0,026250; projected 0,196300; nowy B 0,013914; run 0,183964 przy capie 0,20; 4 VERIFIED, 7 usage.
  - Zwrot narracyjny: sukces infrastruktury nie oznacza zgody redakcyjnej. Lifecycle osiągnął COMPLETE/SUCCESS/USED i zamknął Etap 0, lecz deterministyczna bramka nadała karcie REJECT (`THESIS_UNSUPPORTED`, `CLAIMS_WITHOUT_SOURCES`).
  - Dowód: run `c01171bc-7ff5-4b83-bbfa-c0b164137793`, card #2, `docs/RESEARCH_LOG.md`, `docs/COSTS.csv`; dokładnie jeden call, zero retry/search.

- **[2026-07-13] „Timeout” nie jest nazwą na każdy błąd** (sekcja: 3, 6, 15)
  - Materiał: jedna szeroka klauzula `except Exception` zmieniała błędne żądanie i zły klucz w tę samą kategorię co zerwane połączenie. Dla ręcznego CLI było to ryzyko; dla przyszłego workera stałoby się mechanizmem automatycznego powtarzania płatnych błędów.
  - Decyzja: domyślną odpowiedzią jest „nie ponawiaj”. Tylko timeout, błąd połączenia sklasyfikowany przez SDK, 429 i cztery wskazane statusy 5xx otwierają możliwość retry — nadal po kontroli budżetu.
  - Granica wiedzy: brak usage w wyjątku nie oznacza kosztu 0. P2-19 pozostaje uczciwie otwarte zamiast zasłoniętego sztucznym rekordem.
  - Dowód: ADR-029, fake SDK, testy A1/A2/B i ledgeru; 382 passed, zero API, koszt 0 USD.

- **[2026-07-13] Karta bez statusu to jeszcze nie wynik** (sekcja: 3, 6, 15)
  - Materiał: po B system potrafił zapisać kartę i źródła, a dopiero potem próbował powiedzieć bazie, że research się zakończył. Jeden crash rozjeżdżał artefakt i jego znaczenie.
  - Decyzja: jedna transakcja obejmuje kartę, każde źródło, B SUCCESS, COMPLETE, terminalny run oraz USED. Testy psują drugi insert źródła i lifecycle; po reopen nie ma pół artefaktu.
  - Zwrot narracyjny: „zapisano odpowiedź” nie znaczy „zapisano wynik”. Status nadaje odpowiedzi znaczenie, więc dane i status muszą upaść razem albo przetrwać razem.
  - Dowód: ADR-030, `tests/test_staged_finalization_atomic.py`, 420 testów offline, 0 USD, bez API.

- **[2026-07-13] Zgoda, której nie da się zapamiętać tylko na chwilę** (sekcja: 3, 6, 15)
  - Materiał: transakcja potrafiła ocalić bazę, ale jej uprawnienie mogły rozszerzyć dwa zwykłe booleany. Po awarii B informacja, że run był świadomie forced, znikała z procesu razem z pamięcią.
  - Decyzja: force jest zapisem per run, resume porównuje trwały ślad nieudanego B, a przed następnym potencjalnym kosztem system wykonuje niemutujący preflight. Pomyłka nie robi „spróbuj mimo wszystko”; nie wywołuje nawet klienta.
  - Dowód: 13 crash points z zamknięciem i reopen SQLite, force→failure→resume oraz test braku usage po odmowie. Kolejność tych samych źródeł nie zmienia wyniku — dowód jest zbiorem, nie przypadkiem kolejności listy.
  - Koszt: 0 USD; 446 testów offline, bez API.
- **[2026-07-13] Lease nie jest sugestią dla wątku, tylko prawem do każdego zapisu** (sekcja: 3, 6, 15)
  - Materiał: pierwsza naprawa restartu scaliła trzy commity inicjalizacji, lecz niezależne review przesunęło crash o kilka linijek dalej. Stary proces po expiry nadal mógł dopisać usage, koszt, FAILED albo kartę, zanim worker sprawdził in-memory guard.
  - Decyzja: zamknięty context powstaje dopiero po atomowym związaniu joba z runem. Każdy kolejny zapis bierze SQLite write lock, dopiero wtedy odczytuje canonical UTC i atomowo sprawdza job, run, owner, expiry oraz stan wykonawczy. Odmowa nie tworzy nawet „pomocniczego” FAILED.
  - Zwrot narracyjny: heartbeat mówi procesowi, co prawdopodobnie jest prawdą; transakcja rozstrzyga, kto naprawdę ma prawo zmienić historię. Test dwóch połączeń dowodzi, że recovery i stary zapis nie mogą oba wygrać.
  - Granica wiedzy: realny provider może naliczyć koszt po utracie lease. System celowo nie fałszuje wtedy canonical ledgeru; osobny idempotentny rejestr request ID pozostaje przyszłą pracą przed paid workerem.
  - Dowód: ADR-045, 26 restart acceptance, full 667, close→reopen/integrity, koszt 0 USD, hash prawdziwej bazy bez zmiany.

- **[2026-07-13] „Chwila” musi być pobrana po zdobyciu prawa do zapisu** (sekcja: 3, 6, 15)
  - Materiał: test zaczyna mutację przed expiry, zatrzymuje ją na prawdziwym write locku SQLite, przesuwa zegar i zwalnia lock dopiero po expiry. Dawny timestamp nie może już dać prawa do heartbeat ani terminalizacji.
  - Zwrot narracyjny: zegar nie jest neutralnym parametrem; w systemie współbieżnym miejsce jego odczytu określa, kto ma prawo zmienić historię.
  - Drugi wniosek: plik `COSTS.csv` nie jest księgą główną. Gdy append po commitcie zawodzi, job nadal kończy się zgodnie z SQLite, a błąd zostaje widoczny jako ostrzeżenie, nie jako fałszywa awaria procesu.
  - Dowód: ADR-046, 42 restart acceptance, full 683, close→reopen/integrity, koszt 0 USD, hash prawdziwej bazy bez zmiany.

- **[2026-07-14] „Sukces” nie może potrzebować ostatniego, ryzykownego kroku** (sekcja: 3, 6, 15)
  - Materiał: pipeline zdążył zapisać kartę i COMPLETE, ale worker miał jeszcze wykonać heartbeat oraz zwykłe zakończenie joba. Awaria tego epilogu mogła zostawić job FAILED obok trwałego sukcesu researchu.
  - Decyzja: jedna transakcja obejmuje artefakt, lifecycle researchu oraz `jobs=DONE`; typowany wynik dispatchera mówi workerowi, czy wolno mu jeszcze dotknąć lifecycle. Po sukcesie RESEARCH nie ma już dodatkowego heartbeat, complete ani fail.
  - Zwrot narracyjny: najgroźniejsze rozjazdy nie powstają zawsze w środku złożonej operacji. Czasem tworzy je „ostatnia porządkowa linijka”, która próbuje dopisać drugie zakończenie do historii już zatwierdzonej.
  - Dowód: ADR-047, literalny test czerwony→zielony, 53 restart acceptance, failpointy po obu stronach UPDATE joba, crash po commicie, reopen/integrity i full 695; brak API, browsera, publikacji i kosztu.

- **[2026-07-14] „Typ” jest obietnicą, dopóki nie spotka złego stringa** (sekcja: 3, 6, 15)
  - Materiał: po naprawie sukcesu pozostała szczelina w najmniejszym komunikacie między modułami. `DispatchResult` wyglądał jak typowany, ale runtime przyjmował string. Jedna zła wartość mogła uruchomić porządkowy heartbeat po pełnym commicie i zmienić opowieść workera na fałszywe „lost lease”.
  - Decyzja: rezultat nie ma domyślnego właściciela. Konstruktor i Worker sprawdzają ten sam zamknięty enum, a zły komunikat nie może naprawiać historii przez kolejny zapis — musi przerwać proces jawnie i bez mutacji.
  - Zwrot narracyjny: niezawodność nie kończy się w momencie commitu. Kończy się dopiero wtedy, gdy każdy późniejszy komponent rozumie, że nie wolno mu już niczego „posprzątać”.
  - Dowód: ADR-048, literalny czerwony string, atomic failure z 0 generic `fail_job`, 58 restart acceptance, reopen/integrity i full 700; bez API, browsera, publikacji i kosztu.

## 2026-07-14 — Materiał: „Dlaczego stary rekord nie powinien udawać nowego dowodu”

- Niezależne review ujawniło trzy niewidoczne w happy path ryzyka: obejście durable granicy, lokalny operation key i ledger bez wystarczających ograniczeń.
- Konkretny ślad techniczny: migracja 0011 nie dopisuje zmyślonych relacji do dawnych usage, lecz oznacza je `is_legacy_usage=1`; przyszłe realne usage wymaga request_id rozpoczętego attemptu.
- Kontrast narracyjny: ograniczenie systemu („WAVE 1A dopiero później”) jest sukcesem bezpieczeństwa, nie brakiem funkcji. Status materiału: offline candidate, wymaga niezależnego re-review przed publicznym twierdzeniem o zamknięciu.

## 2026-07-14 — Materiał: „Dowód musi dotrzeć aż do ostatniego calla”

- Fakt: drugi review nie podważył happy path, lecz ujawnił, że opłacony caller nadal mógł ominąć dowód trwałej próby, a stary rekord mógł ukryć sprzeczność jako legacy.
- Zwrot: poprawka nie dodała retry; dodała odmowę przed callerem, snapshot intencji i migrację, która woli rollback od wymyślonej historii.
- Dowód: 752 testy offline, context gate `caller=0`, migration rollback i parse-error settlement; 0 USD oraz bez API.
- Granica: realne A1/A2/B, resume i operator reconciliation nadal nie istnieją. Materiał nie jest ogłoszeniem ukończenia WAVE 0B.

## 2026-07-14 — Materiał: „Dwie zgodne etykiety nie są jeszcze tożsamością”

- Fakt: re-review znalazł przypadek, w którym dwie równe, lecz arbitralne etykiety requestu mogły przekroczyć bramkę.
- Zwrot: poprawka nie naprawia etykiety — wylicza ją z joba, etapu i numeru próby, a potem sprawdza ją ponownie tuż przed SDK względem świeżego lease.
- Dowód: 770 testów offline, arbitralne/mismatched ID `caller=0`, dokładny `Idempotency-Key`, expiry/takeover `messages.create=0`; 0 USD i bez API.

## 2026-07-15 — Materiał: „Test nie jest bezpieczny, dopóki jego dziecko nie jest bezpieczne”

- Fakt: izolacja w jednym interpreterze nie chroni procesu uruchomionego przez test. Ścieżka bazy może mieć URI, kod może użyć `dbapi2`, a proxy może przeżyć pod małą literą.
- Decyzja: kernel startuje przed collection przez `sitecustomize`, dziedziczy tylko testową konfigurację do subprocessów, rozpoznaje kanoniczny `data/agent.db` i blokuje sieć, DNS oraz realny SDK bez blokowania tymczasowej SQLite.
- Dowód: raw SQLite/dbapi2/URI, socket/DNS/SDK, sekrety i proxy w parent/subprocess oraz 823 testy offline; 0 USD, brak API/browsera/publikacji, baseline bazy niezmieniony.
- Zwrot narracyjny: bezpieczeństwo testu nie jest właściwością testu, lecz całego drzewa procesów, które może uruchomić.

## 2026-07-15 — Materiał: „Idempotency-Key nie opisuje całej obietnicy”

- Fakt: stabilny identyfikator requestu mówi, która próba jest wykonywana, ale nie dowodzi, że wszystkie parametry tej próby nadal są takie same.
- Decyzja: attempt przechowuje canonical fingerprint całego `execution_intent`; tuż przed callerem system porównuje trwały snapshot z aktualnym payloadem. Różnica nie „naprawia” się retry, tylko zostaje jako `NEEDS_RECONCILIATION`.
- Dowód: dziesięć klas późnej zmiany ma `caller=0`, usage/koszt 0 i brak settlementu; semantycznie równy JSON zachowuje fingerprint. Real resume A2/B jest odmówione przed mutacją.

## 2026-07-15 — Materiał: „Zamrożony prompt nie jest skrótem do zamrożonej rzeczywistości”

- Fakt: request może mieć stabilny identyfikator, a mimo to po enqueue zmienić znaczenie, jeśli prompt powstaje ponownie z żywego pytania tematu albo niszy konta.
- Decyzja: trwały intent przechowuje kanoniczne dane wejściowe promptu i stage; worker nie odbudowuje requestu z mutowalnych tabel. Bieżący source może tylko wykazać drift i zatrzymać caller, nie podmienić treść requestu.
- Dowód historyczny przed W0B-REV-06: 861 testów offline, osobne mutacje question/niche, parametrów providera i lifecycle dają `caller=0`, usage/koszt/settlement=0 i brak attempt #2; reopen SQLite zachowuje ten sam snapshot. Bez API, browsera i kosztu.
- Status materiału: techniczny kandydat, nie ogłoszenie zamknięcia WAVE 0B ani Etapu 1.

## 2026-07-15 — Materiał: „Jedna liczba w żądaniu nie może znaczyć czego innego w rachunku”

- Fakt: system trwałe zapisywał limit `max_tokens` i przekazywał go do callera, ale koszt przed requestem nadal był liczony jak dla stałego limitu 3000. To tworzyło możliwość realnego usage większego od rezerwacji.
- Decyzja: jedna wartość z durable intentu przechodzi przez request → estimate → policy → reservation → usage → settlement. Kwoty są porównywane po canonicalizacji do sześciu miejsc; nadwyżka zostaje w ledgerze, lecz nie może zostać cichym sukcesem.
- Zwrot narracyjny: bezpieczny system nie mówi „rezerwacja była tylko przybliżeniem”. Gdy rachunek przekracza obietnicę, zachowuje dowód rachunku i zatrzymuje dalsze działanie do reconciliation.
- Dowód historyczny po W0B-REV-06: fake caller, tymczasowa SQLite, restart limitu 2999/3000/3001, mutacje snapshotu, rounding boundary, `NEEDS_RECONCILIATION`, brak attempt #2; 873 offline testy w czterech rozłącznych partycjach. Zero API, sieci, kosztu, browsera i publikacji.
- Status materiału: WAVE 0B pozostaje `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`; to materiał do niezależnego re-review, nie deklaracja zakończenia.

## 2026-07-15 — Materiał: „Pół centa w siódmym miejscu potrafi zmienić historię”

- Fakt: po zamknięciu luki `max_tokens` audyt wykrył rozbieżność mniejszą niż mikrodolar: część systemu używała banker's rounding, a ledger już `ROUND_HALF_UP`. To nie był powód do nowej architektury, tylko do jednej definicji pieniędzy.
- Zwrot: trzy mikroskopijne składniki po `0.0000005` nie są trzema osobno zaokrąglonymi rachunkami. Najpierw stają się `0.0000015`, potem jednym `0.000002` — i ta kolejność jest częścią obietnicy systemu.
- Dowód historyczny: 887 offline testów, partycje 211+222+229+225, cache read/write/web, rezerwacja ±1 mikro-USD oraz fake caller → usage → settlement. Kronika przyznała, że 770/823/861/873 były wynikami historycznymi, nie bieżącym stanem.
- Granica: WAVE 0B pozostaje `CANDIDATE`, Etap 1 `BLOCKED`, live API `ZABRONIONE`; nie było API, sieci, browsera, publikacji ani kosztu.

## 2026-07-15 — Dowód: checkpoint nie jest zamknięciem

- Fakt: niezależny końcowy review zaakceptował WAVE 0B jako `APPROVED WITH P2 — READY FOR CHECKPOINT`, bez findingów MAJOR i CRITICAL.
- Dowód: 894 testy offline, partycje 213/224/231/226, 13 migracji, `durable_research_intent_v2`, jeden aktywny durable paid-execution flow i niezmieniony hash chronionej bazy.
- Granica: formalne `CLOSED` nie następuje przed commitem; Etap 1 pozostaje `BLOCKED`, a live API `ZABRONIONE`.

## 2026-07-15 — Materiał: „Zaokrąglenie nie może nastąpić za wcześnie”

- Fakt: niezależny review zauważył, że poprawna reguła w jednym helperze nie wystarcza, jeśli system zaokrągla koszt jednego źródła, a dopiero potem go mnoży lub porównuje przez float.
- Zwrot: `0.0000005` dwa razy daje `0.000001`, trzy razy daje `0.000002`. To nie są trzy osobne paragony; to jedna suma, która dopiero na końcu staje się kwotą.
- Dowód: 894 testy offline, partycje 213+224+231+226, przypadki `0.1+0.2` dla policy, ledgeru i CLI, bez sieci, API, kosztu lub prawdziwej bazy.
- Granica: nie powstał nowy workflow ani nowy attempt. `max_tokens` nadal jest jednym źródłem estimate/rezerwacji/callera, a actual ponad rezerwacją nadal kończy się `NEEDS_RECONCILIATION` z jednym usage.

## 2026-07-16 — Materiał: „Automatyzacja zaczyna się od prawa do odmowy”

- Systemowy scheduler nie dostał własnej logiki. Umie wyłącznie uruchomić istniejący worker i maintenance; overlap jest blokowany przez `IgnoreNew`, a real research dodatkowym `--offline-only` przed runnerem.
- Raport operacyjny jest ciekawszy tam, gdzie odmawia zgadywania: brak trwałego czasu maintenance i brak flag nie stają się zerem/false, tylko widocznym `UNKNOWN/BLOCKED`.
- Migracja produkcyjna została rozbita na dowód na kopii i osobną decyzję o zmianie źródła. Backup jest identycznym plikiem, koszt historyczny musi pozostać `0.684580`, drugi przebieg migracji ma być no-op, a rollback oznacza pełne odtworzenie pliku, nie „odkręcanie” SQL-em.
- Kontrast narracyjny: `CANDIDATE COMPLETE` nie znaczy `CLOSED`. Brakujący live acceptance jest jawnie nazwanym warunkiem, nie ukrytym „pozostałym P1”.
- Dowód: nowe testy Task Scheduler/report/migration/Unicode, pełna regresja i partycje offline, brak API/sieci/SDK/browsera/publikacji, koszt 0 USD, chroniona baza niezmieniona.

## 2026-07-17 — Materiał: „Sukces jest zdarzeniem trwałym, nie napisem w pamięci”

- Pierwszy wrapper wyglądał bezpiecznie, dopóki review nie odłączył napisu `SUCCEEDED` od prawdziwego joba, odebrał możliwość zapisania raportu i zmienił cennik pod tym samym ID. Wszystkie trzy kontrpróby ujawniły tę samą wadę: system ufał nazwie, a nie pełnej tożsamości.
- LA-01-R1 wiąże cenę, job, request, attempt i worker fence z jednym trwałym planem. Sukces istnieje dopiero, gdy nowe połączenie widzi terminalny lifecycle, jeden usage, zgodny settlement, zamknięte flagi i raport zapisany przed usunięciem markera.
- Recovery nie może „uspokajać” historii. Jeżeli `request_started_at` istnieje, wynik może być nieznany; zapis przechodzi do reconciliation bez retry.
- Dowód: 1151/1151 offline, exact-once 275+282+291+303; kontrpróby foreign result, bare claim, brak usage/settlement, report failure, marker failure, sekret w wyjątku i `REQUEST_STARTED`. Zero sieci/API/kosztu; realny acceptance niewykonany.
- Ostatnia kontrpróba po zielonej regresji pokazała jeszcze jedną użyteczną lekcję: osobno poprawny enqueue i osobno poprawny wrapper mogą razem tworzyć system, którego nie da się uruchomić. Enqueue nie zapisywał kontraktu sesji wymaganego później przez wrapper. Dopiero wspólna deterministyczna tożsamość i test pełnej ścieżki `enqueue → wrapper bez prawa tworzenia joba → fake worker` stały się dowodem kompozycji.
- Niezależny review zatwierdził LA-01-R1 z jednym P2, który nie jest osiągalnym naruszeniem: ostatni fallback sanitizera powinien mimo to ponownie przepuścić tekst przez redactor. To materiał o różnicy między findingiem blokującym a świadomym defense-in-depth — oraz o tym, dlaczego checkpoint nie powinien przemycać nawet rozsądnej poprawki spoza reviewed diffu.

## 2026-07-17 — Materiał: „Zamrożony plan ma dwa odciski czasu”

- Właściciel zatwierdził konkretne ceny i limit `0.12 USD`; kod wyliczył `0.070000` projected oraz `0.105000` pessimistic, z `0.015000` zapasu.
- Mimo kompletnego cennika system odmówił deklaracji `READY`: job jeszcze nie istnieje, a jego enqueue zmieni bazę, której SHA jest częścią późniejszego kontraktu wrappera.
- Zwrot narracyjny: preflight przed enqueue może zatwierdzić zamiar, ale nie może udawać preflightu po enqueue. Bezpieczna automatyzacja zachowuje tę różnicę jako blocker zamiast wpisywać wygodny, lecz nieprawdziwy hash.
- Dowód: lokalny profil `Decimal`, dwa fingerprinty, 70 testów offline, produkcyjna baza bez zmian, koszt 0 USD i zero provider requestów.

## 2026-07-17 — Materiał: „Najbezpieczniejszy live request to ten, który nie przekroczył progu”

- Wszystkie jawne bramki operatora przeszły, lecz wewnętrzna maszyna wrappera nadal odmówiła przed provider boundary. To nie jest sukces acceptance, ale jest sukcesem zasady fail-closed: zero requestów, attempts, usage i kosztu.
- Trwały raport nie zachował surowego wyjątku ani promptu; zachował closed reason code, klasę i fingerprint diagnostyczny. Ceną tej sanitizacji jest brak szczegółowego root cause w raporcie operatorskim.
- Job pozostał `QUEUED`, więc brak provider requestu nie oznacza, że można „spróbować jeszcze raz”. Autoryzacja była jednorazowa i została zużyta przez komendę, nie przez rachunek providera.

## 2026-07-17 — Materiał: „Obserwator był jednym z procesów”

- Pierwsza live próba nie przegrała u providera. Przegrała dlatego, że PowerShell/cmd/bash, który uruchomił wrapper, zawierał w swoim command line nazwę tego wrappera. Strażnik uznał własny łańcuch za obcego operatora.
- Zbyt szeroka naprawa — „ignoruj controlled-live-once” — ukryłaby drugi entrant i niezależnego operatora. Właściwy dowód to relacja: PID→PPID, pełna identity, creation time i ten sam jednoznaczny entrypoint. Nazwa shella nie jest tożsamością.
- Druga lekcja dotyczy raportowania: outer `PREFLIGHT_FAILED` opisuje etap, inner `PROCESSES_PRESENT` opisuje przyczynę. Usunięcie drugiego kodu nie zwiększa bezpieczeństwa; tylko odbiera operatorowi możliwość diagnozy. Redakcja sekretów i diagnostyka mogą współistnieć.
- Standalone check sprawdza ten sam canonical probe bez storage, providera i gate'u. Testy pokazują `PASS` dla legalnego ancestry i `STOP` dla prawdziwego testowego workera, zachowując DB byte-identical.
- Dowód: 21 nowych przypadków LA-02, regresja fake controlled-live ancestry i pełny suite 1174/1174; zero API, kosztu i drugiej live próby. Job nadal czeka w `QUEUED/attempts=0` — poprawka kodu nie jest autoryzacją operacji.

## 2026-07-17 — Materiał: „Review zamyka przyczynę, nie otwiera bramki”

- Niezależny review zatwierdził LA-02 jako `APPROVE WITH MINOR/P2`, więc techniczny root cause `PROCESSES_PRESENT` jest zamknięty. To nie zmieniło ani jednej flagi, joba czy attemptu.
- P2-2 pokazuje różnicę między poprawnością klasyfikatora a higieną operacyjną. Niezależny terminal lub edytor z pełnym tekstem komendy może wyglądać jak realny konkurent i prawidłowo wywołać fail-closed `STOP`; dlatego przyszły standalone check musi przejść z tego samego launchera po zamknięciu takich procesów.
- Checkpoint zachowuje najważniejszą granicę: provider request `NOT EXECUTED`, druga próba `NOT AUTHORIZED`, job `QUEUED/attempts=0`, gate `False`, flags fail-closed i koszt `0.000000 USD`.
- Dowód repozytoryjny: 1174/1174 offline, exact-once `284+284+298+308`, jawna procedura P2-2 i dokładna reguła ignore dla lokalnego pricing profile bez ukrywania innych plików YAML.

## 2026-07-17 — Materiał: „Strażnik zablokował własny klucz do drzwi”

- Drugi false STOP nie pochodził od obcego procesu. Wrapper najpierw otwierał SQLite, a potem pytał Windows, czy ktokolwiek trzyma SQLite. Odpowiedź „tak” była poprawna; błędna była kolejność pytań.
- Naprawa nie wyłączyła czujnika. Przeniosła go przed otwarcie zasobu, a po PASS zamroziła dowód i ponownie sprawdziła trwały stan. Testy z obcym read-only/writable DB oraz WAL/SHM nadal kończą się STOP.
- Pierwszy request pokazuje drugą warstwę fail-closed: HTTP 200 nie oznacza sukcesu produktu. Niepoprawny JSON dał terminalny `FAILED`, ale koszt nie zniknął — `REQUEST_STARTED`, usage i settlement zostały zachowane dokładnie raz.
- Liczby: 1181/1181 offline, jeden realny request, 13306 input + 1657 output + jeden search, `0.053182 USD`, zero retry, job `FAILED`, gate/flags zamknięte.

## 2026-07-17 — Gdy system wie, gdzie parser upadł, ale nie wie dlaczego

- Najmocniejszy motyw: ledger zachował koszt, request identity i terminalizację idealnie, lecz starsza granica diagnostyczna wyrzuciła dwa małe pola — raw response i stop reason. `line 29 column 6` brzmi precyzyjnie, ale nie wystarcza do uczciwego opisania znaku ani przyczyny.
- Dowód epistemiczny: brak katalogu diagnostycznego konkretnego runu i jawne `_stop_reason` odrzucone w `_default_caller`. Wniosek redakcyjny: dokładność lokalizacji nie jest tym samym co kompletność dowodu.
- Motyw architektoniczny: stable identity i historyczna identity nie powinny być jednym kluczem. Deterministyczny session ID ułatwia fencing, ale bez invocation discriminator niszczył starszy raport. Rozdzielenie tych ról zachowuje i idempotencję, i historię.
- Kontrpróby: 14 klas odpowiedzi, każda dokładnie jeden caller; parse/schema/truncation po fake durable boundary tworzą jedno usage i jeden settlement. 1200/1200, partycje `290+293+304+313`.
- Cytowalna zasada: „Nie naprawiaj odpowiedzi drugim requestem, jeśli kontrakt obiecuje dokładnie jeden request; popraw dowód i parser przed następną osobną autoryzacją.”
- Koszt nowej pracy: `0.000000 USD`; historyczny koszt requestu pozostaje `0.053182 USD`, suma miesiąca `0.737762 USD`.
- Zwrot narracyjny: system może jednocześnie osiągnąć cel infrastrukturalny „pierwszy provider request” i nie osiągnąć celu redakcyjnego „Research Card”. Dobre statusy muszą umieć powiedzieć obie rzeczy naraz.

## 2026-07-17 — Materiał: „Plik prywatny też jest granicą bezpieczeństwa”

- Finding: gitignore chroni repozytorium, ale nie chroni lokalnego dysku przed utrwaleniem bearer tokenu, headers ani sekretu schowanego w nested exception.
- Naprawa: operator report, prywatna diagnostyka i trwały błąd przechodzą przez jeden rekurencyjny sanitizer; zapis diagnostyczny ma ten sam atomowy rytuał temp→fsync→replace→directory fsync, a jego awaria nie zmienia ledgeru ani lifecycle.
- Drugi finding pokazuje granicę typów: legalny JSON może zawierać liczbę zbyt dużą dla `float`. Walidacja `Decimal` przed konwersją sprawia, że błąd danych pozostaje błędem schema, a dokładnie jedno usage i settlement nie znikają.
- Dowód: 28 przypadków parsera, durable huge/non-finite score, pięć klas sekretów i cztery failpointy; 1235/1235 oraz exact-once `294+299+311+331`, koszt `0.000000 USD`.
- Granica: to kandydat po wcześniejszym `REJECT — MAJOR`, nie zatwierdzenie. Etap 1 pozostaje otwarty i kolejny request jest zabroniony.

## 2026-07-17 — Materiał: „Zgoda na request nie jest zgodą na zmianę przełącznika”

- Wszystkie techniczne warunki requestu mogły być poprawne jednocześnie: quiescence PASS, model i pricing zgodne, budżet dostępny, koszt maksymalny policzony co do mikrocenta, brak lease i rezerwacji. Mimo to request nie był legalnie osiągalny, bo kodowy gate pozostał `False`.
- Najważniejsza granica operatorska: tymczasowa zmiana `False→True→False` nie przestaje być zmianą kodu tylko dlatego, że po operacji diff znika. Jawny zakaz właściciela ma pierwszeństwo przed oczekiwanym pozytywnym wynikiem.
- Cytowalny rezultat: zero heroicznego obejścia, zero „tylko jednej małej zmiany”, zero requestu. System zakończył `BLOCKED — LIVE PREFLIGHT DRIFT`, zachowując DB i koszt miesiąca bez zmian.

## 2026-07-17 — Materiał: „HTTP 200 może znaczyć pełne rozliczenie i zero wyniku”

- Późniejsza decyzja właściciela legalnie otworzyła gate dokładnie na jeden request. Sieć odpowiedziała sukcesem transportowym HTTP 200, ale `stop_reason=max_tokens` dowiódł niepełnej odpowiedzi; parser odmówił tworzenia karty.
- Ledger zachował to, co nieodwracalne: 16704 input, 1667 output, jeden search i `0.060078 USD`. Produkt zachował to, co ważniejsze: brak pozornego sukcesu, zero retry i terminalny `FAILED`.
- Cytowalna zasada: „Płatność za pełny request nie jest dowodem pełnej odpowiedzi; HTTP 200 nie jest zgodą na dokończenie jej drugim requestem.”

## 2026-07-17 — Materiał: „Większy limit rozwiązał ucięcie, nie kontrakt danych”

- Osobno autoryzowany request zwiększył `max_tokens` z 1500 do 3000. Tym razem provider zakończył `end_turn` przy 2727 output tokens, więc poprzedni problem truncation rzeczywiście nie wystąpił.
- Kompletność transportowa i długość odpowiedzi nie gwarantują jednak zgodności schema: `sources[0].supports_claim` miało zły typ. Fail-closed validator odmówił utworzenia Research Card, zachowując jedno usage, settlement i terminalny failure.
- Ledger: 19945 input, 2727 output, jeden search, `0.077160 USD`; zero retry. Cytowalna zasada: „Więcej miejsca na odpowiedź usuwa sufit, ale nie zastępuje kontraktu typów.”

## 2026-07-17 — Materiał: „Naprawiona schema nie pomaga odpowiedzi, która nie dobiegła do końca”

- Narrow review zatwierdził jawne typy `supports_claim` i `citable_numbers`, ale kolejny osobno autoryzowany request znów zakończył się `max_tokens` przy limicie 3000. Naprawiony kontrakt nie został więc sprawdzony live — walidator nigdy nie dostał kompletnego obiektu.
- Ledger zachował jednoznaczne minimum: jeden request, 16381 input, 3155 output, jeden search, `0.074312 USD`, jedno usage i settlement; zero retry i brak karty.
- Cytowalna zasada: „Poprawny kontrakt ocenia kompletną odpowiedź; truncation zatrzymuje eksperyment wcześniej i nie daje prawa do drugiego requestu.”

## 2026-07-18 — Materiał: „Pierwsza karta to jeszcze nie materiał do publikacji”

- Wyliczony kontrakt 6000 tokenów zakończył odpowiedź naturalnie: jeden request, `end_turn`, 4928 znaków raw, poprawny JSON/schema/limity i trwale zapisana Research Card. Ledger: 16834 input, 1961 output, 51 thinking, jeden search, `0.063278 USD`.
- Ten sam pipeline odrzucił kartę redakcyjnie jako `WEAK_SOURCES`. To pożądane rozdzielenie: infrastruktura może działać poprawnie, a gate jakości nadal może powiedzieć „nie publikuj”.
- Cytowalna zasada: „Pierwszy kompletny artefakt jest dowodem działania pipeline'u, nie automatycznie dowodem jakości materiału.”

## 2026-07-18 — Materiał: „Pięć warstw jednego zatwierdzenia”

- Implementer może zadeklarować sukces i pokazać pełny suite, ale nie zatwierdza własnej pracy. Niezależny reviewer może wykonać własne 223 kontrpróby i wydać `APPROVE`, ale nie podejmuje decyzji produktowej. Dopiero właściciel formalnie przyjmuje bramkę.
- Bieżący przykład rozdziela pięć faktów: deklarację implementera, 1288 testów implementera, 223 testy reviewera, niezależny werdykt i decyzję właściciela. To chroni przed zamianą jednego zielonego logu w nieograniczoną autoryzację.
- Bramka positive-live została przyjęta, ale Etap 2 nie został rozpoczęty, a browser, publikacja i kolejny request pozostają zablokowane. Cytowalna zasada: „Potwierdzona zdolność systemu nie jest jeszcze zgodą na jej ponowne użycie.”

## 2026-07-18 — Materiał: „Pieniądze rozliczone, praca niedokończona”

- Najtrudniejsze okno awarii pojawia się po trwałym rozliczeniu kosztu, lecz przed zapisaniem terminalnego wyniku procesu. Cofnięcie `SETTLED` groziłoby podwójnym kosztem; pozostawienie joba w ruchu blokowałoby kolejkę.
- Rozwiązaniem nie jest retry finansowy, lecz osobny append-only dowód wykonawczy: `EXECUTION_RECOVERY`. Koszt i usage pozostają nietykalne, a lifecycle kończy się wyłącznie po sprawdzeniu karty, lineage, fence, rezerwacji i cache.
- Cytowalna zasada: „Terminalny stan pieniędzy i terminalny stan pracy to dwa różne fakty; awaria między nimi wymaga dowodu, nie ponownej płatności.”

## 2026-07-18 — Materiał: „Uruchomienie programu nie jest zgodą na zmianę danych”

- Finding PR1-MAJ-005 pokazał, że wygodna fabryka SQLite łączyła dwie różne decyzje: otwarcie aplikacji i migrację schematu. Zwykły start mógł automatycznie zastosować `0015` do bazy `0014`.
- Po naprawie runtime najpierw wykonuje immutable exact-version check i odmawia bez zmiany SHA, rozmiaru, mtime, ledgera i sidecarów. Migracja ma osobny, jawny root, konkretny plik docelowy i exact preflight.
- Cytowalna zasada: „Kompatybilność schematu jest warunkiem startu; migracja jest osobną autoryzowaną operacją, nigdy skutkiem ubocznym `open()`.”

## 2026-07-19 — Materiał: „Sprawdzić adres to za mało — trzeba połączyć się z tym samym”

- Finding E2B-F-02 pokazał pozornie bezpieczny układ: lokalny resolver sprawdzał publiczny IP, ale później biblioteka HTTP rozwiązywała hostname drugi raz. Między tymi krokami cel mógł się zmienić, więc poprawna walidacja nie była jeszcze dowodem poprawnego połączenia.
- E2-C zastępuje dwa luźne kroki jednym trwałym w wykonaniu faktem: immutable `BoundHttpTarget` niesie dokładny numeryczny IP, który przeszedł politykę; transport łączy się z nim bez DNS, zachowując nazwę tylko w HTTP Host i TLS SNI. Redirect nie dziedziczy starego pozwolenia — dostaje nowe wiązanie.
- Druga lekcja dotyczy zgody: globalny boolean mówi jedynie „zdolność może istnieć", a nie „ten request jest dozwolony". Factory wymaga capability wydanej przez storage dopiero po atomowym zużyciu L1 konkretnego joba i intentu.
- Dowód: `1572/1572`, exact-once `378+389+394+411`, 13/13 nowych kontrprób i 13/13 regresyjnych; jawne failpointy czterech okien lifecycle `4/4`; zero realnej sieci i koszt `0.000000 USD`.
- Cytowalna zasada: „Nie wystarczy sprawdzić, dokąd prowadzi nazwa. Bezpieczeństwo zaczyna się wtedy, gdy przewód prowadzi dokładnie do adresu, który sprawdziłeś.”
- Granica: to kandydat do niezależnego review, nie zgoda na otwarcie przewodu. Produkcja nadal ma schema `0014`; controlled-live pozostaje `NOT READY`.

## 2026-07-19 — Materiał: „Backup nie zamyka wyścigu”

- Najbardziej zdradliwa luka nie leżała w SQL migracji, lecz między poprawnym preflightem a chwilą otwarcia pliku do zapisu. Snapshot mógł być idealny, a źródłowa baza już inna.
- Orchestrator wiąże zgodę z path/SHA/size, robi zweryfikowany snapshot, po czym odrzuca wcześniejszy wynik i jeszcze raz czyta tożsamość pliku, ledger i sidecary. Ostatni pełny gate następuje po obu oknach failpoint i bezpośrednio przed `mode=rw`.
- WAL, SHM i journal nie są „śmieciami do posprzątania", tylko dowodem, że założenie o spokojnym pliku może być fałszywe. System ich nie usuwa ani nie scala; zatrzymuje się i oddaje decyzję operatorowi.
- Druga lekcja: cztery poprawne transakcje nie tworzą magicznie jednej transakcji. Raport mówi prawdę: które szczeble są trwałe, który nie został wykonany i że resume wymaga nowego SHA, snapshotu oraz zgody.
- Dowód: 18 okien failpoint, 58/58 testów orchestratora, pełne/exact-once 1630/1630; produkcja pozostała bajtowo identyczna na `0014`.
- Cytowalna zasada: „Backup chroni stan sprzed operacji. Dopiero ponowne sprawdzenie chroni decyzję, że wolno ją zacząć.”

## 2026-07-22 — Materiał: „Rozliczony request nie może stać się martwym jobem”

- Crash po zapisie usage i `SETTLED`, lecz przed scoringiem tematów, pokazał granicę między nieodwracalnym faktem finansowym a niedokończonym lifecycle. Cofnięcie settlementu albo retry groziłoby drugim kosztem; pozostawienie joba blokowało konto bez operator route.
- Naprawa nie tworzy drugiego ledgera. Jedno kanoniczne usage pozostaje źródłem kosztu, attempt pozostaje `SETTLED`, a osobny append-only event wykonawczy kończy run/job jako `FAILED` dopiero po sprawdzeniu frozen intentu, approval, lineage, braku attemptu #2 i braku wyniku topiców.
- Kontrpróba z generated_topics dowodzi granicy wiedzy: recovery odmawia, jeśli istnieje choć ślad wyniku. Atomowa finalizacja aplikacyjna pokazuje zarazem, że wspierany crash w jej środku cofa topics i generated_topics razem.
- Dowód: 23 nowe przypadki; `1821/1821`, brak skip/xfail; koszt `0.000000 USD`; produkcja niezmieniona.
- Cytowalna zasada: „Kiedy pieniądze są już faktem, naprawia się lifecycle — nie historię płatności.”

## 2026-07-22 — Materiał: „Zgoda na job nie jest zgodą na kolejkę”

- Wewnętrzny worker już umiał wskazać konkretny job, ale publiczny root wystawiał tylko queue-wide claim. To wystarczyło, by poprawny preflight odmówił realnego requestu: approval jednego joba nie dawała dowodu, że wykonany zostanie właśnie on.
- Nowy root wiąże decyzję operatora z jobem, kontem, pełnym intentem, modelem, tokenami, capem, liczbą kandydatów, schema/SHA bazy i stanem Git. Dopiero potem otwiera ograniczony profil policy i wykonuje jedno `run_once` przez `claim_specific_job`.
- Recovery snapshotu flag jest osobnym kontraktem od recovery płatnego attemptu. Restart może przywrócić flagi, ale nie może automatycznie uruchomić providera, maintenance ani retry.
- Kontrpróba dwóch jobów i replay pokazała granicę: tylko zatwierdzony target zmienił stan, drugi pozostał nietknięty, a powtórzenie nie wykonało drugiego calla. Dowód: 33 nowe przypadki i `1854/1854`, zero realnej sieci i kosztu.
- Cytowalna zasada: „Pozwolenie na jeden numer nie otwiera całej kolejki; publiczny przycisk musi wskazywać ten sam rekord, który podpisał człowiek.”

## 2026-07-23 — Materiał: „Bezpieczny sukces jest nudny w najlepszy możliwy sposób”

- Pierwszy targetowany controlled-live wykonał dokładnie to, co obiecywał kontrakt: jeden job, jeden approval, jeden request, jeden settlement i jeden usage. Nie uruchomił researchu, wyszukiwania, browsera, publikacji, maintenance ani retry.
- Pesymistyczny cap wynosił `0.024303 USD`; rzeczywisty koszt `0.013128 USD` przy 219 tokenach wejścia i 1269 wyjścia. To pokazuje różnicę między bezpieczną rezerwacją a rozliczonym faktem.
- Dwa tematy powstały atomowo z terminalizacją; selected topic `21` dotyczy ukrytej logistyki przydziału gate’ów lotniskowych. Approval został zużyty i nie może autoryzować replay.
- Report zachował najważniejszy dowód negatywny: `provider_retry_performed=false`, `maintenance_performed=false`, browser flag false, a wszystkie flagi po wykonaniu są identyczne jak przed nim.
- Cytowalna zasada: „Najlepszy controlled-live nie wygląda jak magia. Wygląda jak jeden podpis, jeden rachunek i zero niedopowiedzeń.”

## 2026-07-23 — Materiał pierwszego, później odrzuconego kandydata: „Szkic nie powinien pamiętać ruchomej przeszłości”

- C1 zaczyna content nie od promptu, lecz od zamrożenia dowodu. Karta PROCEED, jej potwierdzone claimy, verified sources, dokładne excerpts, retrieval IDs, URL-e i fingerprinty tworzą jeden kanoniczny snapshot z hashem.
- Przed runem i każdą ważną mutacją system ponownie buduje obraz z bieżących tabel. Zmiana choćby working thesis, source claim, URL-a lub retrieval fingerprintu nie jest „nowszą wersją danych” — jest driftem, który zatrzymuje wykonanie.
- 27 niedozwolonych krawędzi maszyny stanów zostało zaatakowanych bezpośrednio w SQLite. Identyczny terminalny replay jest bezpiecznym no-op, ale sprzeczny wynik nie może przepisać historii.
- Najważniejszy dowód negatywny: content job istnieje, lecz zwykły worker go nie wybiera; przyszły paid intent można zapisać, ale attempt jest odrzucany niezależnie przez storage i trigger. Fundament nie udaje jeszcze generatora.
- Cytowalna zasada: „Treść można przepisać. Dowodu, z którego powstała, nie wolno po cichu podmienić.”

## 2026-07-23 — Materiał: „Tekst jest dowodem dopiero wtedy, gdy ma trwały adres”

- Niezależny review pierwszego C1 pokazał trzy pozornie różne luki, które miały wspólny rdzeń: system ufał podobieństwu zamiast tożsamości. Ten sam tekst claimu, ten sam URL albo ten sam terminalny status nie dowodzą, że chodzi o ten sam rekord, lease lub request.
- Fala naprawcza zastąpiła podobieństwo trwałymi adresami. Claim ma jawne ID i ordinal, evidence ma dokładne source/excerpt/retrieval/candidate/run/job, wykonanie ma monotoniczną generację, a provider extension ma ten sam wyprowadzony request ID co kanoniczny parent.
- Terminalizacja nie jest już sekwencją czterech „prawie atomowych” helperów. Jeden append-only command weryfikuje ownera, lease, generation, konto, workflow i wszystkie relacje, po czym SQL zmienia komplet albo nic.
- 25 kontrprób obejmuje powtórzony tekst, wspólny URL, obcy excerpt, stary owner po takeover, wygasły replay, ABA z tym samym owner string, obce LOCAL/RESEARCH/TOPIC attempts i równoległe terminalizacje na dwóch połączeniach.
- Dowód kandydacki: 69/69 C1, full 1923/1923, produkcja nadal 0020 i 0 USD. Status pozostaje `AWAITING INDEPENDENT RE-REVIEW`; implementer nie zamyka własnych findings.
- Cytowalna zasada: „Podobieństwo pomaga szukać. Tożsamość pozwala bezpiecznie działać.”

## 2026-07-23 — Materiał: „Jedna poprawka jest polityką, nie pętlą”

- C2 nie traktuje rewrite jako zwykłego retry. Pierwszy draft ma osobny trwały intent, canonical attempt, usage, fingerprint i dziewięć evaluations. Dopiero kompletna decyzja `REWRITE_ONCE` otwiera dokładnie drugi intent związany z fingerprintem pierwszego draftu i konkretnymi findings.
- Próba druga nie zmienia route key i nie uruchamia fallbacku. Ponowny `REWRITE_ONCE` albo `BLOCK` kończy content jako `FAILED`; próba #3 jest niereprezentowalna przez kontrakt Pythona i podłogi SQLite.
- Cztery wymuszone restarty pokazały różnicę między checkpointem a efektem zewnętrznym: brief, fake request start, settled draft i rewrite decision można bezpiecznie wznowić bez podwójnego canonical parenta; marker możliwego skutku zewnętrznego nadal wymusza `NEEDS_VERIFICATION`.
- Koszt fake usage i actual cost wynosi `0.000000`; pozytywny reservation floor w starym ledgerze jest wyłącznie strukturalny i jawnie udokumentowany.
- Cytowalna zasada: „Poprawka jest nową wersją tekstu, ale nie nową zgodą na nieskończoną próbę.”

## 2026-07-23 — Materiał: „Profil stylu powinien być mapą, nie walizką”

- Prywatny korpus pozostał lokalny i gitignored. Runtime nie czyta go, a writer otrzymuje tylko krótki, wersjonowany profil wysokiego poziomu i negative profile.
- Lokalna analiza nie znalazła wiarygodnego zestawu odrębnych Notes. Zamiast fabrykować pochodzenie, profil Notes ma jawny status `PROVISIONAL`.
- Profile opisują ruch od konkretu do systemu, rytm, evidence, kontrargument i zakończenie, ale zakazują imitowania konkretnego autora, kopiowania charakterystycznych fraz i tworzenia fałszywej autobiografii.
- Cytowalna zasada: „Prywatne wzorce mają nauczyć system kierunku, nie podróżować z każdym promptem.”

## 2026-07-23 — Materiał: „Odpowiedź modelu nie jest jeszcze szkicem”

- C3 rozdziela trzy fakty, które łatwo zlać w jeden: logical route produktu, techniczna konfiguracja providera oraz trwały wynik próby. Nazwa „Fable 5” nie staje się przez to API model ID, a brak modelu lub pricingu zatrzymuje flow przed SDK.
- Caller może zwrócić tekst i usage, lecz pipeline nie uznaje jeszcze sukcesu. Najpierw powstaje typowany append-only result: JSON musi przejść zamknięty schema contract, evidence IDs muszą należeć do zamrożonego manifestu, stop reason nie może oznaczać truncation, a route/model/provider muszą zgadzać się z intentem.
- Najważniejsze okno awarii jest między powrotem callera a utrwaleniem rezultatu. System nie zgaduje, czy wolno powtórzyć kosztowny efekt; zostawia attempt do reconciliation i content w `NEEDS_VERIFICATION`. Gdy result zdążył się utrwalić, lecz settlement nie, restart kończy księgowanie bez drugiego calla.
- Prywatny korpus stylu nie podróżuje w promptach. Runtime używa wyłącznie krótkich profili pochodnych, a kanoniczny prompt zakazuje fikcyjnej autobiografii i traktuje źródła internetowe jako dane, nigdy instrukcje.
- Dowód kandydacki: 26/26 C3, 463/463 regresji i 1971/1971 pełnej suity; wszystko na fake SDK/caller i temp SQLite, za `0.000000 USD`. C3 czeka na niezależny review; pierwszy realny tekst pozostaje zadaniem C5.
- Cytowalna zasada: „Model może zwrócić słowa. Dopiero walidacja, ledger i recovery czynią z nich bezpieczny szkic.”

## 2026-07-24 — Materiał: „Autonomia zaczyna się od odmowy starej decyzji”

- C4 pokazuje, że autonomia nie jest booleanem „sam zatwierdzaj”. To funkcja trwałego poziomu, trybu konta, typu treści, jawnej policy, kompletnego zestawu ocen, twardych zakazów i wersjonowanego progu.
- Najważniejszy artefakt to nie samo `APPROVED`, lecz preimage decyzji: dokładny draft, dziewięć evaluations, lineage, account/autonomy/mode i threshold version składają się na fingerprint. Zmiana któregokolwiek faktu unieważnia wcześniejsze rozstrzygnięcie.
- System sprawdza ten snapshot ponownie pod write lockiem i execution fence. Dzięki temu decyzja „approve” policzona dla LEVEL_3 nie przechodzi po zmianie konta na LEVEL_1, a drugi worker nie dopisuje przeciwnego wyniku.
- Append-only audit i lifecycle są jednym commitem. Kontrolowana awaria po apply cofa decision row, approval i status razem; nie istnieje stan „zatwierdzone bez audytu” ani „audit approve, ale lifecycle nieokreślony”.
- C4 nie wywołuje modelu. Provider attempts, usage, settlement i koszt są identyczne przed i po decision boundary; to rozdziela wydanie słów przez C3 od politycznej decyzji, co z nimi zrobić.
- Dowód kandydacki: 23/23 C4 i 1994/1994 całej suity; 1994 unikalne node IDs, zero duplikatów i +23 wobec baseline. Produkcja pozostała na 0020, a kandydat czeka na niezależny review.
- Cytowalna zasada: „Bez fingerprintu autonomia pamięta wynik. Z fingerprintem pamięta, dla jakiego świata ten wynik był prawdziwy.”

## 2026-08-09 — Materiał: „Każde zdanie musi mieć adres”

- Pierwsza naprawa PRE-C5 nadal przepuszczała fakty, których nie obejmował słownik „faktualnych” sygnałów. To ujawniło błąd modelu rozwiązania: detektor podejrzanych zdań próbuje opisać nieskończone dopełnienie języka.
- Nowy kontrakt nie zgaduje, które zdanie warto sprawdzić. Najpierw deterministycznie numeruje wszystkie segmenty ARTICLE, a potem wymaga jednego i tylko jednego rekordu rozliczenia dla każdego z nich. Brak rekordu jest ustaleniem audytowym, nie ciszą.
- Reviewer ma trzy możliwości: fakt z evidence, argument/inferencja bez nowego faktu albo naprawdę non-factual pytanie/przejście. Fakt bez evidence, inferencja przemycająca fakt i deklaratywne zdanie nazwane „prozą” są odmową.
- PASS nie usuwa śladów kontroli. Ledger zapisuje identity/fingerprint segmentu, klasyfikację, reason, evidence, outcome, completeness i wersję reviewera — dzięki temu można później odtworzyć nie tylko wynik, ale pełne pokrycie tekstu.
- Druga połowa tej samej lekcji dotyczy pieniędzy: koszt ponad rezerwację nie może zostać „do wyjaśnienia” tylko w attempt ledgerze, podczas gdy job wygląda na aktywny. Usage, koszt, reconciliation i terminalny stan CONTENT muszą stać się widoczne razem.
- Kontrpróba zapisała dokładnie jedno syntetyczne usage `0.075000 USD`, zero settlementów i jeden reconciliation; content/job od razu trafiły do `NEEDS_VERIFICATION`, a późniejszy reaper niczego nie zmienił.
- Cytowalna zasada: „Jeśli zdanie nie ma rekordu, nie zostało sprawdzone. Jeśli koszt nie ma terminalnego stanu, nie został rozliczony.”

## 2026-08-09 — Materiał: „Pytajnik nie usuwa odpowiedzialności za znaczenie”

- Dwa kolejne rozwiązania przegrały z tym samym błędem w różnych kostiumach. Pierwsze szukało predykatu i konkretnego referentu. Drugie dopuściło zamknięty słownik pytań uznanych za „bez treści”. Oba próbowały z języka wyciąć skończoną wyspę bezpieczeństwa.
- Re-review pokazał, dlaczego to niemożliwe: krótkie `Who did it?`, `Where is it?` i `When was it done?` niosą factual proposition mimo braku słów, które wcześniejszy detektor uważał za konkret. Lexical membership nie jest dowodem braku znaczenia.
- Nowa granica jest prostsza: pytanie ARTICLE nigdy nie dostaje prose shortcut. Reviewer musi wziąć odpowiedzialność za decyzję — fakt z evidence, external fact blokujący jako inference albo uczciwa inferencja bez nowego faktu.
- Konserwatyzm nie zabija retoryki. Dwadzieścia pięć pytań non-factual i 25 dodatkowych controls zachowało drogę honest inference. Zakazana jest jedna wygodna etykieta, nie samo pytanie.
- Najważniejszy negatywny dowód jest jawny: jeśli przyszły reviewer skłamie, deterministic layer nie odtworzy semantyki regexem. Bezpieczeństwo przesuwa się do realnej niezależności i jakości reviewera — dokładnie tam, gdzie leży znaczenie.
- Cytowalna zasada: „Pytajnik może zmienić ton zdania. Nie może wymazać obowiązku rozliczenia tego, co zdanie twierdzi.”

### Dopisek po niezależnym `REJECT — MAJOR`

- Pierwszy prosty kontrakt nadal miał szczelinę mechaniczną: sprawdzał, czy pytajnik jest ostatnim znakiem. `?!`, `?...` albo pytajnik przed zamykającym cudzysłowem odzyskiwał więc stary shortcut, choć znaczenie zdania się nie zmieniało.
- Naprawa nie potrzebowała lepszego rozumienia języka. Potrzebowała dokładniejszej granicy syntaktycznej: obecność markera w segmencie, nie jego pozycja. Sweep 216 kombinacji dał zero przecieków, a pytania retoryczne zachowały honest-inference route.
- Cytowalna zasada: „Granica bezpieczeństwa nie może zależeć od tego, czy po pytajniku stoi wykrzyknik.”

## 2026-08-09 — Materiał: „Najnowszy model nie jest jeszcze wybranym modelem”

- Wersjonowany route key mieszał trzy różne decyzje: co system chce zrobić, jakiej rodziny potrzebuje i jaki dokładny model API jest dziś dostępny. Rozdzielenie stabilnej roli od rodziny, wersji i technicznego ID pozwala zmieniać ostatni element bez przepisywania znaczenia pierwszego.
- Automatyczna promocja nie oznacza „bierz najnowszy”. Kandydat musi przejść availability, każdy wymiar ceny, capabilities i osobną kwalifikację. Nowsza wersja z `FAIL` albo choć jednym wymiarem ponad ceiling zostaje nieaktywna.
- Najważniejsza granica czasowa biegnie przez intencję. Promocja dotyczy przyszłych decyzji; istniejący intent pamięta stary provider/model/pricing/qualification/capability snapshot i restart nie ma prawa rozwiązać go ponownie.
- Dwa procesy mogą zobaczyć tego samego kandydata, ale write lock i pojedyncza aktywacja sprawiają, że tylko jeden zapisuje promotion audit. Drugi otrzymuje idempotentne `NO_CHANGE`.
- Brak realnego catalogue adaptera jest jawny. Fake N→N+1 dowodzi mechanizmu orkiestracji, nie istnienia, ceny ani jakości przyszłego modelu.
- Cytowalna zasada: „Nowy numer jest kandydatem. Dopiero dowód jakości, ceny i zgodności czyni go wyborem.”

## 2026-08-10 — Materiał: „Domyślna wartość to cudza decyzja”

- Provider default wygląda jak brak decyzji, ale faktycznie pozwala workspace ustalić geografię i tier. Jawne `global`/`standard_only` zamienia niewidoczny kontekst konta w wersjonowany kontrakt requestu.
- Odpowiedź HTTP 200 również nie jest jeszcze sukcesem: provenance może ujawnić `us` albo `priority`, a `stop_reason=refusal` oznacza, że provider odmówił wykonania zadania. System zachowuje rachunek, lecz odmawia przypisania sukcesu.
- Retencja pokazuje różnicę między wyborem narzędzia a akceptacją jego warunków. Fable może być preferowanym modelem, ale dopóki właściciel nie zaakceptuje dokładnego 30-dniowego warunku dla konkretnego approvalu/requestu, caller pozostaje nieosiągalny.
- Daty marketingowe nie zawsze są timestampami technicznymi. Deterministyczna granica UTC może być potrzebna w kodzie, ale uczciwa proweniencja musi nazwać ją lokalną normalizacją, nie słowami providera.
- Liczby do narracji: C5 global/standard `0.938880 USD`; niedozwolony US 1.1× `1.032768 USD`; różnica uzasadnia gate, ale nie tworzy alternatywnej ścieżki budżetowej.
- Cytowalna zasada: „Jeżeli kontrakt nie nazywa geografii, tieru i warunków retencji, decyzja nadal istnieje — tylko podjął ją ktoś poza systemem.”
