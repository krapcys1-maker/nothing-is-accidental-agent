> **ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.**
> Dokument historyczny (zarchiwizowany 2026-07-12). Obowiazuja wylacznie: MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md (korzen repozytorium) oraz rejestr decyzji docs/DECISIONS.md.

# docs/architecture/

## Cel

Dokumenty architektoniczne eksperymentu: decyzje strukturalne, diagramy, opisy integracji. Pełny plan techniczny jest w `docs/IMPLEMENTATION_PLAN.md`; tutaj trzymamy dokumenty szczegółowe i pochodne.

## Zawartość

- `SUBSTACK_INTEGRATION.md` — architektura integracji z istniejącym kontem „Nothing Is Accidental" (profil Playwright, logowanie ręczne, brak publikacji na obecnym etapie).

## Co dodać później (uzupełniane w miarę budowy)

- `DATA_MODEL.md` — wyeksportowany schemat bazy + diagram relacji (gdy powstanie migracja `0001`).
- `PORTS.md` — finalne kontrakty portów po implementacji.
- `SECURITY.md` — model zagrożeń, obsługa sekretów, prompt injection.
- diagramy (`*.excalidraw` / `*.svg` / `*.png`) — gdy pojawi się pierwsza działająca wersja.
