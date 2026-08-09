# WEEK_32 — 2026-08-03 → 2026-08-09

- **Co zbudowano:** kandydat technicznych bramek PRE-C5, jego naprawy, claim accounting/cost-cap closure oraz nowa fala question semantic boundary po dwóch odrzuceniach heurystyki; szczegóły w `docs/BUILD_LOG.md`.
- **Co działa:** każde pytanie ARTICLE jest exactly-once rozliczane i nie może przejść jako `NON_FACTUAL_PROSE`; factual questions z evidence oraz non-factual honest inferences mają poprawne ścieżki. Pełna suita `2285/2285`.
- **Co nie działa:** nie istnieje jeszcze realny independent semantic reviewer; jawna trust boundary pozostaje do następnej fali. PRE-C5 QUALITY GATE i C5 są `NOT STARTED`; provider/model/pricing pozostają niewdrożone.
- **Największy błąd tygodnia:** dwie kolejne wersje próbowały dowodzić braku znaczenia pytania — najpierw predicate/referent, potem vocabulary. Re-review drugiej wydał `REJECT — MAJOR`. Wniosek: semantyka należy do reviewera, a deterministic layer egzekwuje kontrakt.
- **Najważniejsza decyzja:** ADR-123 — pytanie ARTICLE nie ma deterministic prose shortcut; trust boundary reviewera jest jawna i nie będzie łatana regexami.
- **Koszty:** `0.000000 USD`; jawny komentarz tej fali dopisano do `docs/COSTS.csv`. Koszt/artykuł i koszt/subskrybent: nie dotyczy.
- **Czas człowieka:** nie mierzono; nie należy go estymować.
- **Liczba interwencji człowieka:** właściciel podjął nową decyzję zakresową po dwóch odrzuceniach, autoryzował wyłącznie usunięcie znanego kandydata i utworzenie brancha; zero publikacyjnych akceptacji, edycji i stopów.
- **Wyniki publikacji:** nie mierzono; publikacji nie wykonano.
- **Najlepsze screenshoty:** `SCREENSHOT REQUIRED` dla zanonimizowanej macierzy question × reviewer output; obrazu nie wykonano w tej sesji.
- **Czego nauczył się agent:** kompletność segmentów nie wystarcza, jeśli klasyfikacja pytania ma fail-open shortcut. Deterministyczna warstwa ma weryfikować strukturę odpowiedzi reviewera, nie odtwarzać jego semantykę.
- **Co zmienimy w kolejnym tygodniu:** wykonać dokładnie jeden niezależny review; dopiero po jego wyniku rozważyć osobną falę realnego reviewera. Nie rozpoczynać C5, API ani publikacji bez nowej zgody.

## Checkpoint naprawczy 2026-08-09

- Niezależny review znalazł MAJOR w końcówkowym `text.endswith("?")`. Jedyna naprawa egzekwuje `?`/`？` w dowolnej pozycji segmentu i pozostaje czysto syntaktyczna.
- Dowód POST: question `220/220`, PRE-C5 `328/328`, affected `399/399`, full/collect `2322/2322`, sweep `216` z `0` leaks, produkcja/style bez zmian, koszt `0.000000 USD`.
- Status tygodnia: `PRE-C5 QUESTION SEMANTIC BOUNDARY CONTRACT — REPAIR CANDIDATE COMPLETE — AWAITING RE-REVIEW`; C5 nadal `NOT STARTED`.
