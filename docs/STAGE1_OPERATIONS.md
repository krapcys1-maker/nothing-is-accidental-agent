# Etap 1 — operacje lokalne, scheduler i migracja produkcyjna

Status: **`CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`**. Etap 1 pozostaje otwarty i zablokowany do kontrolowanego live acceptance. Live API jest zabronione. Ten dokument nie jest zgodą na rejestrację zadań systemowych, migrację produkcji ani wywołanie providera.

## Minimalny Windows Task Scheduler

Task Scheduler jest wyłącznie launcherem istniejących entrypointów. Logika eligibility, claimu, lease, Policy Engine, recovery i reapera pozostaje w aplikacji. Nie ma nowego daemona, Windows Service, brokera ani biblioteki schedulerowej.

Generowane zadania:

| Zadanie | Częstotliwość | Kanoniczny entrypoint | Granica |
|---|---:|---|---|
| `NothingIsAccidental-WorkerOffline` | 1 minuta | `python -m app.main worker --once --offline-only` | `--offline-only` blokuje real research niezależnie od runtime flags |
| `NothingIsAccidental-Maintenance` | 5 minut | `python -m app.main maintain --once --stale-after-seconds 300` | tylko recovery → reaper; bez claimu i dispatchu |

Oba zadania używają jawnego interpretera bieżącego środowiska, `C:\Users\user\Desktop\agent project` jako `WorkingDirectory`, konta interaktywnego bez podwyższania uprawnień, `MultipleInstancesPolicy=IgnoreNew`, braku schedulerowego retry oraz braku hard-kill timeoutu. `ExecutionTimeLimit=PT0S` jest celowe: Task Scheduler nie może przerwać wątku w trakcie zapisu SQLite. Stdout/stderr trafiają do gitignored `runtime/logs/`; launchery propagują exit code procesu, a własny błąd launchera zwraca 70. Nie zapisują ani nie zmieniają `system_flags`.

Plan bez rejestracji:

```powershell
python scripts/manage_windows_tasks.py plan --task worker
python scripts/manage_windows_tasks.py plan --task maintenance
```

Instalacja wymaga osobnej zgody właściciela dla każdego zadania i jest wykonywana pojedynczo:

```powershell
python scripts/manage_windows_tasks.py install --task worker --confirm-register-system-task
python scripts/manage_windows_tasks.py install --task maintenance --confirm-register-system-task
```

Weryfikacja i usuwanie również działają per zadanie:

```powershell
python scripts/manage_windows_tasks.py verify --task worker
python scripts/manage_windows_tasks.py verify --task maintenance
python scripts/manage_windows_tasks.py remove --task worker --confirm-remove-system-task
python scripts/manage_windows_tasks.py remove --task maintenance --confirm-remove-system-task
```

W bieżącym pakiecie uruchomiono wyłącznie `plan` i testy czystego XML/argumentów. Nie wykonano `install`, `verify` ani `remove`; żadne zadanie systemowe nie zostało zarejestrowane.

## Attempts, lease i timeout

`jobs.attempts` zwiększa się w tej samej transakcji co claim `QUEUED→LEASED`. Claim wybiera tylko `attempts < max_attempts`. Recovery po expiry requeue'uje wyłącznie bezpieczny job poniżej capu; job po capie kończy się `FAILED`, a niepewny efekt lub przypięty research przechodzi do `NEEDS_VERIFICATION`/reconciliation bez auto-retry. Domyślne `Job.max_attempts` i `ScheduledJobRequest.max_attempts` wynoszą 1. Bezpieczny composition root enqueue czyta typowane `growth_policy.worker_policy.default_max_attempts`; płatny durable enqueue nadal wymusza 1.

Znaczenia timeoutów są rozłączne:

- provider timeout ogranicza jedno synchroniczne żądanie SDK;
- lease duration (produkcyjnie 60 s) wyznacza trwałe prawo do pracy;
- heartbeat interval (20 s) odnawia to prawo z osobnego połączenia;
- bounded join guarda (5 s) ogranicza cleanup wątku i blokuje fałszywe `DONE`;
- poll interval steruje wyłącznie odstępem pomiędzy iteracjami.

Globalny timeout dispatchu jest descope/P2. Python nie potrafi bezpiecznie przerwać synchronicznego wątku dokładnie na granicy transakcji SQLite; drugi watchdog mógłby stworzyć fałszywą terminalizację. Nie zmienia to provider timeoutu ani trwałego recovery po lease.

## Read-only raport operacyjny

```powershell
python -m app.main operational-report
```

Raport otwiera istniejący plik w SQLite URI `mode=ro`, włącza `query_only` i nie uruchamia migracji. Nie tworzy SDK ani providera, nie claimuje jobów, nie uruchamia workera i nie zapisuje bazy. Pokazuje liczbę jobów per status, aktywne lease, `NEEDS_VERIFICATION`, `NEEDS_RECONCILIATION`, aktywne rezerwacje i ich sumę, pięć runtime flags oraz wersje migracji. Brakująca tabela, flaga albo uszkodzony stan to `UNKNOWN/BLOCKED` z efektywną wartością fail-closed, nigdy fałszywe zero.

Schemat 0014 nie ma trwałego timestampu ukończenia cyklu maintenance, dlatego `last_maintenance_at=UNKNOWN/BLOCKED`. Nie jest wyprowadzany z `jobs.updated_at`.

Exit codes: 0 = kompletny raport bez UNKNOWN; 2 = raport odczytany, ale zdegradowany przez UNKNOWN/BLOCKED; 3 = błąd konfiguracji; 6 = kontrolowany błąd storage/OS. Przy obecnym schemacie brak timestampu maintenance oznacza kontrolowany kod 2.

## Pierwsza migracja produkcyjnej bazy `0009→0014`

Stan rozdzielony jawnie:

- kod obsługuje 14 migracji (`0001`–`0014`);
- chroniona `data/agent.db` ma obecnie 9 wpisów `schema_migrations`;
- produkcyjna migracja nie została wykonana;
- przyszła migracja i zamiana pliku wymagają osobnej zgody właściciela.

Plan bez otwarcia bazy i bez tworzenia plików:

```powershell
python scripts/prepare_stage1_db_migration.py plan `
  --source-db data/agent.db `
  --workspace C:\stage1-db-preflight `
  --expected-branch dev/first-successful-research-card `
  --expected-head 637d1f21fbac164d7f78b11590facc7098182559 `
  --expected-source-sha256 CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB `
  --expected-source-size 294912 `
  --expected-source-mtime-utc 2026-07-14T15:59:24.9521212Z
```

Po osobnej zgodzie wyłącznie na copy-preflight używa się `execute-copy-preflight` i `--confirm-copy-preflight-only`. Workspace musi być pusty, poza katalogiem źródłowej bazy. Procedura fail-closed:

1. sprawdza branch/HEAD oraz zatwierdzone SHA-256, rozmiar i mtime źródła;
2. odmawia przy sidecarach `-wal`/`-shm`;
3. tworzy pełny backup `copy2` i weryfikuje jego identyczny SHA/rozmiar/mtime;
4. sprawdza `integrity_check=ok` i pusty `foreign_key_check` backupu;
5. tworzy osobną candidate copy, wymaga dokładnie migracji `0001`–`0009`, a następnie stosuje dokładnie `0010`–`0014`;
6. ponawia migrator i wymaga no-opu;
7. sprawdza 14 wpisów, zamknięty zbiór wymaganych triggerów, 13 legacy proofs i niezmieniony koszt `0.684580` USD;
8. inicjalizuje wyłącznie na kandydacie: `kill_switch=false`, `worker_enabled=false`, `safe_mode=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`;
9. ponawia integrity/FK, liczy nowy SHA kandydata i dowodzi, że źródło oraz backup nie zmieniły się;
10. zapisuje lokalny JSON report. Nigdy nie podmienia produkcyjnej bazy.

Po review raportu osobna decyzja migracyjna musi zatrzymać worker/maintenance, ponownie sprawdzić tożsamość plików i dopiero kontrolowanie ustanowić zweryfikowanego kandydata jako produkcyjną bazę. Nowy SHA staje się baseline wyłącznie po ponownych integrity/FK, odczycie 14 migracji/flag i jawnej akceptacji właściciela. Rejestracja systemowego workera następuje później, osobną decyzją.

Próba copy-preflight rzeczywistych bajtów z 2026-07-16 została prawidłowo odrzucona przed kopiowaniem, ponieważ obok chronionej bazy istnieją sidecary `agent.db-wal` (0 B) i `agent.db-shm` (32768 B) z 2026-07-15. Nie zostały usunięte ani checkpointowane. Przed przyszłą próbą właściciel musi osobno zatwierdzić quiesce procesów i bezpieczne rozstrzygnięcie sidecarów; nie wolno omijać tej bramki przez kopiowanie samego głównego pliku.

Rollback jest wyłącznie pełnym odtworzeniem zweryfikowanego backupu przy zatrzymanych procesach, a następnie ponowną weryfikacją SHA/integrity/FK. Zabronione jest ręczne cofanie migracji przez `UPDATE`, `DELETE` lub edycję `schema_migrations`.
