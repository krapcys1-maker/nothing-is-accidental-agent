# timeline/

## Cel
Oś czasu projektu — chronologia kamieni milowych „co i kiedy zaczęło działać". Widok z lotu ptaka (nie szczegółowy dziennik — ten jest w `05_BUDOWA_KROK_PO_KROKU.md` i `docs/BUILD_LOG.md`). Tu trzymamy krótkie wpisy oraz ewentualne eksporty grafik osi czasu do artykułów.

## Format wpisu
`[YYYY-MM-DD] Vx — nazwa — jedno zdanie — status (DONE/PLANNED/SLIPPED)`

---

## Oś czasu (stan 2026-07-11)

- **[2026-07-11] V0 — Dokumentacja i plan — DONE.** Audyt założeń, `IMPLEMENTATION_PLAN.md`, pełna struktura `docs/`, architektura integracji z istniejącym kontem. Zero kodu.
- **[2026-07-11] V1 — Etap 0 + walking skeleton — DONE.** Higiena repo, szkielet `app/`, generacja+ocena tematów, Policy Engine, SQLite, tracking kosztów, dry_run, 16 testów.
- **[2026-07-11] V2 — Deduplikacja tematów + Research Pipeline — DONE.** Lokalna dedup (bez płatnego modelu), pełny research pipeline z bramką jakości Research Card, ochrona przed prompt injection, klienci Fake/Anthropic, 44 testy.
- **[2026-07-11 19:09 UTC] V2.1 — Pierwsze realne wywołanie Anthropic — DONE (research nieudany, bug naprawiony).** Właściciel zatwierdził jedno, capnięte na 0.30 USD wywołanie. Dotarło do API, użyło web search, ale JSON został ucięty — Research Card nie powstała. Znaleziono i naprawiono bug gubiący realny koszt przy błędzie parsowania. 47 testów (było 44). Dokładny koszt tej próby nieznany co do centa (górna granica ~0.095 USD) — do weryfikacji w konsoli Anthropic.
- **[—] V3 — Generator artykułów/Notes + panel FastAPI — PLANNED.** Nie rozpoczęte; czeka na kolejną zgodę właściciela (w tym: czy ponowić realny research z podniesionym limitem odpowiedzi).
- **[—] Etap 4 — Warstwa przeglądarki (Playwright), logowanie ręczne, odczyt — PLANNED.** Publikacja tylko po jawnej zgodzie.
- **[—] Etap 5 — Pipeline komentarzy + metryki — PLANNED.**

## Powiązania
- `docs/RELEASE_TIMELINE.md` (źródło), `05_BUDOWA_KROK_PO_KROKU.md`
