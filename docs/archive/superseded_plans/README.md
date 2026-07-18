# ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.

Ten katalog zawiera **historyczne** plany architektury, audyty i założenia projektu, zastąpione 2026-07-12 przez trzy dokumenty źródła prawdy w korzeniu repozytorium:

- `MASTER_ARCHITECTURE.md` — jedyna obowiązująca architektura,
- `IMPLEMENTATION_ROADMAP.md` — jedyna obowiązująca kolejność prac,
- `CURRENT_PROJECT_STATE.md` — jedyny obowiązujący obraz stanu projektu.

Rejestr decyzji (`docs/DECISIONS.md`) i dzienniki (`docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md` itd.) NIE są zarchiwizowane — pozostają obowiązującymi logami projektu.

## Zawartość archiwum i co je zastąpiło

| Plik (pierwotna lokalizacja) | Czym był | Wartość przeniesiona do |
|---|---|---|
| `ARCHITECTURE.md` (korzeń) | „Architektura wstępna V1" — pełny projekt docelowy sprzed kodu | MASTER_ARCHITECTURE §2–§8 |
| `IMPLEMENTATION_PLAN.md` (`docs/`) | plan MVP + specyfikacje (modele §B.3, DDL §B.4, porty §B.6, autonomia CZĘŚĆ D, stabilizacja researchu CZĘŚCI E–F) | MASTER_ARCHITECTURE §4–§7, IMPLEMENTATION_ROADMAP |
| `AUDYT_ARCHITEKTURY_2026-07-12.md` (`docs/`) | audyt architektury z findingami P0/P1/P2 | P0 naprawione w kodzie; P1/P2 → IMPLEMENTATION_ROADMAP (Etap 0–2) i CURRENT_PROJECT_STATE (długi) |
| `SUBSTACK_INTEGRATION.md` (`docs/architecture/`) | projekt integracji z kontem Substack | MASTER_ARCHITECTURE §8.2 |
| `IMPLEMENTATION_PROMPT.md` (korzeń) | pierwszy prompt startowy projektu | wartość historyczna (kronika) |
| `PROJEKT_AGENT_SUBSTACK_NIC_NIE_JEST_PRZYPADKOWE.md` (`zalozenia projektu/`) | pierwotne założenia eksperymentu (już wcześniej SUPERSEDED) | ADR-017/018, MASTER_ARCHITECTURE §7 |
| `ZALOZENIA_DLA_AGENTA_SUBSTACK_GROWTH_MASTER.md` (`zalzoewnia dla agenta/`) | pierwotny „master plan" wzrostu (już wcześniej SUPERSEDED) | ADR-001/002, config `growth_policy`, MASTER_ARCHITECTURE |
| `architecture_folder_README.md` (`docs/architecture/`) | spis dawnego katalogu architektury | — |

## Uwaga o odsyłaczach historycznych

Starsze wpisy w `docs/BUILD_LOG.md`, `docs/DECISIONS.md` i komentarzach kodu odwołują się do sekcji tych dokumentów (np. „IMPLEMENTATION_PLAN.md §B.3", „AUDYT… P0-2"). Te odsyłacze pozostają poprawne jako **kontekst historyczny** — pliki są tutaj — ale niczego z nich nie wolno wdrażać.
