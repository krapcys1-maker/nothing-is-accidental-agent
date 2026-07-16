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

## Kontrolowana migracja produkcyjnej bazy `0009→0014`

Stan obowiązujący po pierwszej próbie z 2026-07-16:

- pierwsza migracja była technicznie poprawna: kanoniczny runner zastosował dokładnie `0010`–`0014`, a wszystkie kontrole schematu, danych, kosztu, triggerów i flag przeszły;
- rollback uruchomił wyłącznie niezamówiony warunek `WAL=ABSENT` i `SHM=ABSENT`; kontrolowany odczyt SQLite prawidłowo pozostawił pusty WAL i SHM;
- pełny restore DB/WAL/SHM został niezależnie zweryfikowany bitowo i metadanymi;
- chroniona `data/agent.db` nadal ma schemat `0009` i stary obowiązujący SHA-256 `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`;
- nowy baseline nie istnieje; chwilowego SHA po pierwszej migracji nie wolno używać;
- druga migracja nie została wykonana i wymaga nowej, osobnej zgody właściciela.

### Jedyny kanoniczny kontrakt sidecarów i flag

`agent.db-wal` może być nieobecny albo mieć dokładnie 0 B. Niezerowy WAL blokuje operację. `agent.db-shm` może istnieć i jest raportowany wraz z SHA, rozmiarem i mtime; jego obecność nie jest błędem. `agent.db-journal`, proces projektu, aktywny uchwyt albo zadanie systemowe wskazujące repozytorium blokuje operację. Baseline wymaga SHA głównego DB; WAL/SHM są metadanymi stanu plików, które muszą pozostać bez driftu pomiędzy bramkami i wejść do backupu/restore.

Jedyny profil inicjalizowany po migracji pochodzi z `app.core.security_flags.SECURITY_FLAG_DEFAULTS`:

| Flaga | Wartość |
|---|---|
| `kill_switch` | `true` |
| `safe_mode` | `true` |
| `worker_enabled` | `false` |
| `paid_actions_enabled` | `false` |
| `browser_actions_enabled` | `false` |

### Kanoniczne narzędzie

`scripts/prepare_stage1_db_migration.py` jest jedynym opakowanym entrypointem. Akcja `plan` nie tworzy plików i nie otwiera bazy:

```powershell
python scripts/prepare_stage1_db_migration.py plan `
  --source-db data/agent.db `
  --workspace C:\Users\user\Desktop\agent-project-backups\stage1-second-migration `
  --expected-branch dev/first-successful-research-card `
  --expected-head 0658e8b221b99bcdaa549cf538ee140a9dc02613 `
  --expected-source-sha256 CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB `
  --expected-source-size 294912 `
  --expected-source-mtime-utc 2026-07-14T15:59:24.9521212Z
```

Akcja `execute-in-place` jest niedostępna bez literalnego `--confirm-in-place-production-migration`. Samo istnienie kodu i tego dokumentu nie stanowi zgody na jej użycie. Po osobnej zgodzie właściciela executor wykonuje kolejno i fail-closed:

1. sprawdza jawne potwierdzenie oraz dokładny branch/HEAD;
2. bez otwierania SQLite sprawdza stary SHA/size/mtime DB, stan WAL/SHM i brak journala;
3. dowodzi pełnego quiesce: brak procesów projektu, uchwytów i zadań systemowych;
4. kopiuje i bitowo/metadanymi weryfikuje cały istniejący zestaw DB/WAL/SHM poza repozytorium;
5. ponownie fingerprintuje źródło po backupie i blokuje każdy drift;
6. na świeżej kopii backupu wykonuje rehearsal kanonicznym `app.storage.db.apply_migrations`, dokładnie `0010`–`0014`, a drugi przebieg musi być no-op;
7. weryfikuje `integrity_check`, FK, ledger 14 migracji, wymagane triggery, 13 legacy proofs, historię, koszt `0.684580` i jedyny profil flag;
8. bezpośrednio przed mutacją ponawia branch/HEAD, quiesce oraz fingerprint DB/WAL/SHM i odrzuca drift;
9. dopiero wtedy otwiera produkcję, używa tego samego kanonicznego runnera i inicjalizuje profil flag;
10. po zamknięciu połączenia wykonuje pełną weryfikację i dopiero wtedy zapisuje nowy wymagany SHA głównej bazy;
11. przy dowolnym błędzie po otwarciu produkcji odtwarza pełny zestaw DB/WAL/SHM ze zweryfikowanego backupu i sprawdza identyczność;
12. nigdy nie używa reverse SQL, nie uruchamia workera/API/browsera, nie rejestruje zadań i nie wykonuje płatnej akcji.

Pomocniczy `execute-copy-preflight` pozostaje wyłącznie rehearsal na kopii i nie jest alternatywnym executorem produkcyjnym. Nie wolno tworzyć ad-hoc skryptów, ręcznej listy migracji ani drugiego profilu flag.

Rollback produkcji jest wyłącznie pełnym odtworzeniem zweryfikowanego zestawu DB/WAL/SHM przy zatrzymanych procesach. Zabronione są reverse `UPDATE`, `DELETE`, ręczna edycja `schema_migrations` i częściowe odtwarzanie samego `agent.db`.
