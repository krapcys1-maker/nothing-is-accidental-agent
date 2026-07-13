# RESEARCH_LOG

## Cel

Dziennik każdego researchu prowadzonego przez agenta. Dla każdego tematu zapisujemy pytanie badawcze, źródła, najważniejsze fakty, elementy niepewne, sprzeczności między źródłami, wniosek oraz wpływ researchu na artykuł/Note/komentarz/decyzję strategiczną. To zabezpieczenie przed halucynacjami (ryzyko R6) i pamięć źródeł. Powiązanie z bazą: `research_cards` + `sources` (źródło prawdy). Materiał najwyższej wartości trafia dodatkowo do `ARTICLE_EVIDENCE.md`.

## Zasady

- Jeden wpis = jeden research (jeden temat / jedno pytanie badawcze).
- Źródła pierwotne przed wtórnymi; zawsze sprawdzona data publikacji **i** data opisywanych danych.
- Odróżniaj fakt od interpretacji; oznaczaj niepewność jawnie.
- Żadnych wymyślonych źródeł, cytatów ani liczb. Luka jest lepsza niż zmyślony szczegół.
- Minimum 3 sensowne źródła, zanim research zasili artykuł.

## Szablon wpisu

```markdown
### [YYYY-MM-DD] Temat
- **Konto:** account_id (MVP: nothing_is_accidental)
- **Powiązanie:** research_card #.. / topic #.. / content_item #.. (jeśli są)
- **Pytanie badawcze:** jedno zdanie
- **Źródła:**
  1. [Tytuł](URL) — typ (PRIMARY/SECONDARY/DATA), data publikacji / data danych — co wnosi
  2. ...
  3. ...
- **Najważniejsze fakty (potwierdzone):** lista
- **Elementy niepewne:** lista (co źródła NIE rozstrzygają)
- **Sprzeczności między źródłami:** opis + możliwa przyczyna (metodologia/okres/populacja)
- **Wniosek (teza robocza):** jedno–dwa zdania
- **Confidence:** 0.0–1.0
- **Wpływ:** na co to poszło (artykuł / Note / komentarz / decyzja strategiczna) i jak zmieniło treść
```

---

## Wpisy

> Wpisy poniżej są dopisywane automatycznie po każdym researchu (dry_run oznaczony w treści).

### [2026-07-11] Why airline ticket prices change every few hours
- **Konto:** nothing_is_accidental
- **Powiązanie:** research_card #1 / topic #1
- **Pytanie badawcze:** What pricing system makes fares move so often?
- **Źródła:**
  1. [How airline revenue management works](https://example.org/dynamic-pricing-primer) — PRIMARY, 2023-05-10 — wspiera: Airlines use dynamic pricing engines
  2. [Observed fare update frequency dataset](https://data.example.gov/fare-updates) — DATA, 2022-11-01 — wspiera: Fares update as demand and inventory signals change
  3. [Why ticket prices move so often](https://example.com/airline-pricing-explainer) — SECONDARY, 2024-02-20 — wspiera: Airlines use dynamic pricing engines
- **Najważniejsze fakty (potwierdzone):** Airlines use dynamic pricing engines, Fares update as demand and inventory signals change
- **Elementy niepewne:** Exact repricing cadence varies by carrier and route.
- **Sprzeczności między źródłami:** —
- **Wniosek (teza robocza):** Ticket prices change because revenue-management systems continuously re-price seats against forecast demand and remaining inventory.
- **Confidence:** 0.78  |  **Source quality:** 0.8
- **Rekomendacja:** PROCEED
- **Wpływ:** dry-run/demonstracja pipeline researchu.

### [2026-07-11] What really happens to your suitcase after check-in — PIERWSZA REALNA PRÓBA (nieudana, ręczny wpis)
- **Konto:** nothing_is_accidental
- **Powiązanie:** topic #2 (SELECTED, score 85.25) / run `1b649314-27cf-4b29-857e-287175664a3f`
- **Pytanie badawcze:** What is the hidden logistics chain behind checked luggage?
- **Źródła:** brak — model zwrócił odpowiedź (>8100 znaków, realnie użył web search), ale JSON został ucięty w połowie stringa przed pełnym wypisaniem listy źródeł; parsowanie nie powiodło się, więc żadne źródło nie zostało wyodrębnione ani zapisane.
- **Najważniejsze fakty (potwierdzone):** nieznane — niedostępne z powodu nieudanego parsowania.
- **Elementy niepewne:** cała treść odpowiedzi poza tym, że dotarła i była długa; surowy tekst nie został nigdzie zalogowany, więc nie da się go odtworzyć retrospektywnie (zidentyfikowana luka: warto logować surową odpowiedź modelu również przy błędzie parsowania — rekomendacja na przyszłość, niewdrożona teraz).
- **Sprzeczności między źródłami:** nie dotyczy (brak źródeł do porównania).
- **Wniosek (teza robocza):** nie dotyczy — research nie dostarczył użytecznego draftu.
- **Confidence:** nie dotyczy (walidacja nigdy nie doszła do etapu oceny — pipeline zatrzymał się na etapie parsowania).
- **Rekomendacja:** REJECT (brak poprawnego draftu; bramka jakości nie została nawet uruchomiona, bo nie było czego walidować).
- **Rzeczywisty koszt (potwierdzony w konsoli Anthropic, 2026-07-11, później tego samego dnia):** **0.25 USD** = 0.21 USD tokeny + 0.04 USD web search (4 wyszukiwania). Pierwotny pre-flight szacunek: 0.095 USD — realny koszt był **2,63× wyższy** (błąd ~+163%). Zmieściło się w zatwierdzonym limicie 0.30 USD, z zapasem 0.05 USD.
- **Wpływ:** REALNE (płatne) wywołanie Anthropic — nie dry-run. Zero artykułu/Note/komentarza z tego wyszło. Ujawniło i doprowadziło do naprawy dwóch realnych problemów: (1) bug księgowania kosztu przy błędzie parsowania (patrz `ERRORS_AND_FAILURES.md`, wpis 2026-07-11 19:09 UTC „Realny koszt zgubiony..."), (2) błędny (zaniżony) estymator kosztu PRZED wywołaniem (patrz `ERRORS_AND_FAILURES.md`, wpis „Pre-flight cost estimator underestimated the real cost"). Doprowadziło też do przebudowy pipeline'u na wersję dwuetapową (`gather_sources` + `synthesize_card`, ADR-016) z kalibrowanym estymatorem. Temat #2 pozostaje SELECTED — może zostać ponownie podjęty w osobno zatwierdzonej kolejnej próbie (tryb `two-stage`, projekcja kosztu ~0.38 USD w capie 0.45 USD).

### [2026-07-13] What really happens to your suitcase after check-in — TASK 9, STAGED A1/A2 SUKCES, B NIEUDANE
- **Konto:** nothing_is_accidental
- **Powązanie:** topic #2 / run i research_run `c01171bc-7ff5-4b83-bbfa-c0b164137793` / brak research_card
- **Pytanie badawcze:** What is the hidden logistics chain behind checked luggage?
- **Dokładna komenda:** `python scripts/run_capped_research.py --topic-id 2 --mode three-stage --discovery-max-searches 1 --max-sources 4 --max-web-searches-per-source 1 --extraction-max-tokens 1500 --max-retries 0 --max-cost-usd 0.55`
- **Pre-flight:** expected 0,201280 USD; conservative 0,510375 USD; cap 0,550000 USD; dziennie przed runem 0,000000/2,00 USD; miesięcznie 0,500616/40,00 USD; kill switch wyłączony; konto aktywne; temat SELECTED; zero retry.
- **Źródła A2 (wszystkie EXTRACTED/VERIFIED, attempts=1):**
  1. [Checked Baggage: Where Does It Go In The Airport & How Does The System Work?](https://simpleflying.com/checked-baggage-journey-analysis/) — SECONDARY, Simple Flying, 2024-03-12; candidate #5; jakość 0,62; koszt calla 0,049405 USD.
  2. [The journey of a suitcase - More than meets the eye](https://www.easa.europa.eu/en/light/topics/journey-suitcase) — PRIMARY, EASA; data nieustalona; candidate #6; jakość 0,80; koszt calla 0,028891 USD.
  3. [The hidden complexity behind your luggage](https://www.airport-suppliers.com/supplier-press-release/the-hidden-complexity-behind-your-luggage-the-engineering-and-systems-behind-modern-airport-baggage-handling/) — OTHER, Airport Suppliers, 2024-08-01; candidate #7; jakość 0,45; koszt calla 0,028620 USD.
  4. [The hidden highway beneath your suitcase](https://www.fly2houston.com/airport-business/newsroom/articles/item/the-hidden-highway-beneath-your-suitcase/) — PRIMARY, Houston Airports, 2025-12-17; candidate #8; jakość 0,80; koszt calla 0,020987 USD.
- **Wyniki etapów:** A1 SUCCESS (`end_turn`, 1 search, 0,029243 USD); A2 4/4 SUCCESS (`end_turn`, 4 searches, 0,127903 USD); B FAILED (`max_tokens`, 2200 output tokens, zero search, 0,012904 USD).
- **Błąd:** `ResearchParseError` — `Unterminated string starting at line 29 column 18 (char 4224)`. Surowa odpowiedź i metadane są prywatnie w `data/debug/research/<run_id>/`; nie trafiają do repo.
- **Stan trwały:** `research_runs=SOURCES_COMPLETE`, `runs=RUNNING` bez `finished_at`, topic SELECTED, 4 VERIFIED, brak karty. Run jest technicznie wznawialny wyłącznie od B, ale nie wykonano resume ani drugiego calla.
- **Rzeczywisty koszt:** **0,170050 USD**, zgodny z sumą 6 wpisów `model_usage` i `runs.cost_usd`; 30,92% capu 0,55 USD.
- **Najważniejsze fakty / teza / sprzeczności / confidence:** niezatwierdzone do użycia — synteza nie utworzyła Research Card. Cztery karty źródłowe pozostają trwałym materiałem wejściowym, nie finalnym wnioskiem.
- **Rekomendacja:** REJECT dla wyniku Task 9; Etap 0 pozostaje aktywny. Każdy kolejny płatny krok wymaga osobnej zgody.
- **Wpływ:** zero artykułu, publikacji i działań zewnętrznych poza sześcioma zatwierdzonymi requestami researchu w ramach jednego runu.

#### Korekta techniczna po analizie offline (bez nowego researchu)

Nie wykonano nowego calla ani resume. Przyczyną B był wyczerpany limit 2200, nie losowy parse error. Przyszłe B użyje jawnego defaultu 3000, typowanego truncation bez retry i pełnego pre-flightu (B conservative 0,026250 USD; projected z dotychczasowym usage 0,196300 USD). Historyczny wynik, cztery VERIFIED, koszt 0,170050 USD i brak Research Card pozostają bez zmian. Repair auditu i resume wymagają osobnych zgód.
