> **ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.**
> Dokument historyczny (zarchiwizowany 2026-07-12). Obowiazuja wylacznie: MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md (korzen repozytorium) oraz rejestr decyzji docs/DECISIONS.md.

# Pierwszy prompt do Claude Code / Cowork

Przeczytaj wszystkie dokumenty i konfiguracje w tym folderze.

Nie zaczynaj od budowania całego systemu.

Najpierw:

1. przeanalizuj ARCHITECTURE.md,
2. porównaj go z pozostałymi dokumentami projektu,
3. wskaż konflikty, luki i ryzyka,
4. przygotuj finalną strukturę folderów,
5. przygotuj modele Pydantic,
6. przygotuj schemat SQLite i migracje,
7. przygotuj interfejsy portów:
   - SchedulerPort,
   - StoragePort,
   - BrowserPort,
   - SecretStorePort,
   - FileStorePort,
   - NotificationPort,
8. przygotuj plan testów,
9. przygotuj roadmapę implementacji w małych etapach.

Utwórz plik docs/IMPLEMENTATION_PLAN.md.

Nie wdrażaj jeszcze publikowania na Substacku.
Nie wpisuj haseł ani kluczy do kodu.
Nie uznawaj zadania za zakończone bez aktualizacji:
- docs/BUILD_LOG.md,
- docs/DECISIONS.md,
- docs/ARTICLE_EVIDENCE.md.

Po przygotowaniu planu zatrzymaj się i czekaj na akceptację.
