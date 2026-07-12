# ARTICLE_EVIDENCE

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
