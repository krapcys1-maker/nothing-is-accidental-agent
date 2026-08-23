# N-018 — promowalny artefakt V3

## Metryka

- **Ustalenia:** A-089–A-092, A-094, A-100
- **Status:** FOUNDATION_DOCUMENTED; IMPLEMENTATION_OPEN
- **Data:** 2026-08-21
- **Zakres:** release manifest, runtime lock, migracje, shadow/canary, atomowe
  przełączenie i rollback
- **V2:** wyłącznie odczyt; zakaz zapisu

## Problem

Prototyp jest celowo niewdrażalny: `wdroz.sh` odmawia, a usługi systemd wykonują
`/usr/bin/false`. To chroni bieżącą pracę, ale nie istnieje jeszcze bezpieczna
zamiana przebadanego V3 w produkcyjny release. Edycja tych plików „na gotowo”
tworzyłaby nowy, nieprzetestowany wariant właśnie na granicy produkcji.

## Hipoteza

Jeżeli kod, zależności, prompty, schemat i dowody testów zostaną związane jednym
niemutowalnym manifestem, a osobny kontroler wykona migrację na kopii,
shadow/canary, maszynowe bramki i atomowy rollback, to późniejsza promocja będzie
jedną odtwarzalną operacją bez przebudowy kodu w chwili wdrożenia.

## Kolejność implementacji

1. `agent-v3-release@1` — kanoniczny manifest i hashe plików oraz profili głosu.
2. Lock zależności przechodnich z hashami, wersją Pythona i Chromium.
3. `schema_version` i numerowane migracje z testem backup/restore.
4. Offline builder release bundle; bez sekretów i bez katalogu `data`.
5. Preflight uruchamiany na niemutowalnym bundle.
6. Profile shadow/canary z tym samym artefaktem.
7. Dwu-slotowe, atomowe przełączenie `current` i automatyczny rollback.
8. Dopiero po dodatnim dowodzie osobny profil produkcyjnych capabilities.

## Kontrdowody wymagane do zamknięcia

- zmiana jednego bajtu po zbudowaniu manifestu blokuje promocję;
- brak/transitive drift zależności blokuje start;
- migracja niepełna lub powtórzona nie uszkadza bazy i nie uruchamia procesu;
- dwie wersje nie mogą równolegle dispatchować;
- `UNKNOWN` kosztu lub mutacji automatycznie zatrzymuje canary;
- błędne account ID blokuje przed pierwszą mutacją;
- awaria po przełączeniu wraca do poprzedniego slotu bez `git reset --hard`;
- release bundle nie zawiera sekretów, sesji, V2 ani danych roboczych;
- izolowany bundle zawiera wszystkie aktywne profile głosu i odmawia przy
  niezgodnym hashu;
- brak wspieranego odnowienia auth/backupu blokuje profil produkcyjny;
- pełny replay N-004 oraz N-010/N-011 przechodzą na dokładnym bundle.

## Bieżący rezultat

Powstał pełny projekt w `../PLAN_PROMOCJI_V3_DO_PRODUKCJI.md`. Nie dodano
wykonywalnej ścieżki wdrożenia i nie osłabiono zabezpieczeń prototypu. N-018 nie
może zostać zamknięte przed N-019/N-020, N-004, N-010, N-011, N-022 oraz
numerowanymi migracjami.
