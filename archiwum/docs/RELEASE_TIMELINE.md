# RELEASE_TIMELINE

## Cel

Oś czasu wydań i kamieni milowych eksperymentu — zwięzła chronologia „co i kiedy zaczęło działać". W przeciwieństwie do `BUILD_LOG.md` (szczegółowy dziennik każdego zadania) to widok z lotu ptaka: daty, wersje, jednozdaniowe podsumowania. Podstawa sekcji „chronologia" w końcowym artykule.

## Zasady

- Jeden wpis = jeden kamień milowy lub wersja.
- Data absolutna; wersja (V0, V1…) spójna z `ARCHITECTURE_EVOLUTION.md`.
- Krótko: jedno–dwa zdania na wpis.
- Odnotowuj też ślizgi terminów (planowane vs faktyczne) — to materiał „plan vs rzeczywistość".

## Szablon wpisu

```markdown
### [YYYY-MM-DD] Vx — Nazwa kamienia milowego
- **Status:** PLANNED | DONE | SLIPPED
- **Podsumowanie:** jedno–dwa zdania, co osiągnięto.
- **Planowana data (jeśli inna):** YYYY-MM-DD
- **Powiązania:** BUILD_LOG / ARCHITECTURE_EVOLUTION / DECISIONS
```

---

## Oś czasu

### [2026-07-11] V0 — Dokumentacja i plan
- **Status:** DONE
- **Podsumowanie:** audyt założeń, `IMPLEMENTATION_PLAN.md`, pełna struktura dokumentacji eksperymentu; architektura integracji z istniejącym kontem. Zero kodu.
- **Powiązania:** BUILD_LOG (wpis 2026-07-11), ARCHITECTURE_EVOLUTION V0.

### [2026-07-11] V1 — Etap 0 + walking skeleton
- **Status:** DONE
- **Podsumowanie:** higiena repo (.gitignore/.env.example/pyproject), szkielet `app/` ze stubami portów, działający walking skeleton (generacja i ocena tematów, Policy Engine, SQLite, tracking kosztów, dry_run) z testami jednostkowymi.
- **Powiązania:** BUILD_LOG (wpis Etap 0/1), ARCHITECTURE_EVOLUTION V1.

### [2026-07-11] V2 — Deduplikacja tematów + Research Pipeline
- **Status:** DONE
- **Podsumowanie:** lokalna deduplikacja tematów (bez płatnego modelu) oraz pełny research pipeline z bramką jakości Research Card, ochroną przed prompt injection i klientami Fake/Anthropic; 44 testy; dry_run bez płatnych wywołań.
- **Powiązania:** BUILD_LOG (wpis 1A/1B), ARCHITECTURE_EVOLUTION V2, DECISIONS ADR-014/015.

### [2026-07-11 19:09 UTC] V2.1 — Pierwsze realne wywołanie Anthropic
- **Status:** DONE (jako kontrolowany eksperyment) / research SLIPPED (Research Card nie powstała)
- **Podsumowanie:** jedno, zatwierdzone i capnięte (0.30 USD) realne wywołanie dla tematu #2. Dotarło do API, użyło web search, ale JSON został ucięty — REJECT. Odkryto i naprawiono bug gubiący realny koszt przy błędzie parsowania. Rzeczywisty koszt (zweryfikowany później w konsoli Anthropic): **0.25 USD**.
- **Powiązania:** BUILD_LOG (Etap 1C), ERRORS_AND_FAILURES (2× wpis 19:09 UTC).

### [2026-07-11] V3 — Dwuetapowy research + kalibrowany estymator (Etap 1D)
- **Status:** DONE (kod + testy) / realne uruchomienie PLANNED (wymaga nowej zgody)
- **Podsumowanie:** po weryfikacji, że pesymistyczny szacunek (0.095 USD) był 2,63× niższy od realnego kosztu (0.25 USD, błąd ~+163%), zbudowano kalibrowany estymator (`app/research/cost_estimator.py`) i przebudowano pipeline na dwuetapowy (`gather_sources` + `synthesize_card`, ADR-016) z tanią bramką wczesnego wyjścia. 63 testy (było 47). Projekcja nowego podejścia: ~0.38 USD (oba etapy), cap 0.45 USD. Żadnego kolejnego płatnego wywołania nie wykonano w ramach tego etapu.
- **Powiązania:** BUILD_LOG (Etap 1D), ARCHITECTURE_EVOLUTION V3, DECISIONS ADR-016, ERRORS_AND_FAILURES („Pre-flight cost estimator underestimated the real cost").
