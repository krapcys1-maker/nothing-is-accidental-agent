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
