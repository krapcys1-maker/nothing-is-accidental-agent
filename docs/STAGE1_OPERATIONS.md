# Etap 1 — operacje lokalne, scheduler i migracja produkcyjna

Status: **`POST-MIGRATION REVIEW — APPROVE WITH MINOR/P2`; QP-01 = `APPROVED`; produkcja = `VERIFIED / SCHEMA 0014`; nowy baseline = `VERIFIED`.** Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`. Live API jest zabronione. Ten dokument nie jest zgodą na rejestrację zadań systemowych, ponowną migrację ani wywołanie providera.

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

### Wynik drugiej zatwierdzonej próby — 2026-07-16

Jednorazowo zatwierdzone uruchomienie zacommitowanego executora na HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15` zostało odrzucone na pierwszej bramce quiesce:

```text
STAGE 1 MIGRATION: failed closed: Full quiescence was not proven:
processes=(17196, 34228), handles=(), tasks=().
```

Był to wynik **`MIGRATION REJECTED BEFORE MUTATION`**. Bramka następuje przed utworzeniem workspace, backupem, otwarciem kopii i produkcyjnej SQLite, dlatego nie powstały backup, rehearsal ani manifest nowego baseline'u. Kontrola po zakończeniu wykazała nieobecność obu przejściowych PID-ów, brak procesów projektu, journala, runtime i tasków oraz dokładnie niezmienione SHA/size/mtime DB/WAL/SHM. Produkcja pozostaje na `0009`; rollback nie był potrzebny. Nie wolno automatycznie ponawiać tej próby; następne uruchomienie wymaga nowej zgody właściciela.

### Wynik ponownej próby po clean quiesce — 2026-07-16

Przed poleceniem potwierdzono czysty quiesce: brak procesów projektu, uchwytów DB/WAL/SHM, operatora CLI, workera, maintenance i zadań Windows projektu. Branch i HEAD były zgodne, a DB/WAL/SHM odpowiadały staremu baseline'owi. Jedna faktyczna próba executora zakończyła się:

```text
STAGE 1 MIGRATION: failed closed: Full quiescence was not proven:
processes=(15404,), handles=(), tasks=().
```

Zarejestrowany proces:

| Pole | Wartość |
|---|---|
| PID | `15404` |
| Parent PID | `10216` |
| Executable | `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` |
| Creation time UTC | `2026-07-16T18:59:17.5919140Z` |
| Reason match | `CommandLine contains resolved project root` |
| Command line | `powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop';$root='C:\Users\user\Desktop\agent project';$self=10216;..."` |

Finding `QP-01`: jest to proces potomny uruchomiony przez `_default_quiesce_probe`. Probe wyklucza parent Python przez `$self=10216`, lecz jego własny potomny PowerShell ma w command line literalny `$root`; predykat `CommandLine.Contains($root)` dopasowuje więc sam proces sprawdzający. Pełna command line jest zachowana w raporcie `docs/migration-reports/STAGE1_DATABASE_RETRY_QUIESCE_PROCESS_IDENTIFIED_2026-07-16.md`.

Odrzucenie nastąpiło przed utworzeniem workspace i przed otwarciem SQLite. Nie wykonano backupu, rehearsal, migracji, inicjalizacji flag, rollbacku ani nowego baseline'u. Nie wykonano kolejnej próby i nie zmieniono filtra. Wynik: **`MIGRATION REJECTED — QUIESCE PROCESS IDENTIFIED`**.

### Kontrakt klasyfikacji procesów po QP-01

Poprawiony probe nie pozwala PowerShellowi samodzielnie rozstrzygać, co jest procesem projektu. Helper zwraca atomowy snapshot `Win32_Process` zawierający PID, parent PID, executable, command line i creation time oraz listę tasków. Python zna własny PID i parent PID, rejestruje PID uruchomionego przez siebie helpera z jednorazowym nonce i akceptuje wykluczenie helpera dopiero po zgodności:

- reported PID = PID zwrócony przez `Popen`;
- parent PID helpera = current Python PID;
- executable = `powershell.exe` albo `pwsh.exe`;
- command line zawiera nonce tej instancji;
- creation time mieści się w oknie tej instancji probe'a.

Nie istnieje wykluczenie „wszystkich potomków”. Niezarejestrowany potomek helpera jest klasyfikowany od początku i realny worker nadal blokuje. Direct parent launcher jest nieblokujący tylko jako jawny launcher; parent będący workerem lub maintenance blokuje. Dokładnie zarejestrowany helper dostaje `PROBE_REGISTERED_HELPER_IDENTITY` i nie może zostać zablokowany samym `PROJECT_ROOT_COMMAND_LINE_ONLY`.

Zamknięte blocking reason codes:

| Reason code | Skutek |
|---|---|
| `APP_ROLE_WORKER` | STOP |
| `APP_ROLE_MAINTENANCE` | STOP |
| `APP_ROLE_OPERATOR_CLI` | STOP |
| `PROCESS_IDENTITY_INCOMPLETE` | STOP dla procesu kandydującego |
| `APPLICATION_HOST_COMMAND_LINE_UNREADABLE` | STOP |
| uchwyt DB/WAL/SHM | STOP przez niezależny file-handle gate |
| task wskazujący repozytorium | STOP |

`PROJECT_ROOT_COMMAND_LINE_ONLY` jest pełną, raportowaną obserwacją nieblokującą, jeżeli proces ma kompletną tożsamość i nie ma roli aplikacyjnej. Dzięki temu dwa równoległe probe'y nie blokują się wzajemnie. Każdy blocking process jest renderowany z pełną tożsamością i reason codes także wtedy, gdy zniknie przed obsługą błędu.

Historyczny status bezpośrednio po implementacji QP-01 brzmiał **`CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`** i nie stanowił zgody na migrację; produkcja miała wtedy schemat `0009`. Późniejszy niezależny review zatwierdził QP-01, a osobno autoryzowana kontrolowana próba ustanowiła schema `0014` i nowy baseline.

### Wynik jednej kontrolowanej próby po QP-01 — sukces

Właściciel udzielił osobnej zgody na dokładnie jedną próbę. Użyto tego samego entrypointu `scripts/prepare_stage1_db_migration.py execute-in-place`, interpretera `C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe`, CWD repozytorium i subprocess flow PowerShell → Python → helper PowerShell.

Każdy z trzech gate'ów miał:

```text
blocking_processes=0
locked_paths=0
scheduled_tasks=0
helper_classification=PROBE_HELPER
helper_reason=PROBE_REGISTERED_HELPER_IDENTITY
```

QP-01 nie powtórzył się. Executor zweryfikował backup starego zestawu bez driftu, przeprowadził rehearsal, zastosował `0010`–`0014` w produkcji i zakończył post-verification. Wynik:

- dokładnie 14 migracji i 35 triggerów;
- `integrity_check=ok`, `foreign_key_check=[]`;
- 13 legacy proofs i koszt `0.684580` USD bez zmiany;
- historyczne tabele bez zmiany, w tym `runs` 9 wierszy i `research_runs` 5;
- 0 jobs, 0 provider attempts, 0 reconciliation events;
- `kill_switch=true`, `safe_mode=true`, worker/paid/browser `false`;
- brak live API, workera, paid/browser actions i zmian Windows Tasks.

Nowy baseline:

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6` | 335872 B | `2026-07-16T19:42:25.5377560Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-16T19:42:25.5417557Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-16T19:42:25.5507558Z` |

Backup, report i baseline znajdują się poza repozytorium w `C:\Users\user\Desktop\agent-project-backups\stage1-second-migration-20260716-ddc3c63190eb82bc-attempt-4`. Migracji nie wolno ponawiać w tej sesji. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.

### Niezależny review trwałego wyniku migracji i QP-01

Właściciel dostarczył ukończony niezależny review bazowego HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`. Reviewer nie modyfikował repozytorium. Werdykt `APPROVE WITH MINOR/P2` potwierdził QP-01, schema `0014`, baseline `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`, 14 migracji, 35/35 triggerów, 13 legacy proofs, 18 zgodnych digestów historycznych, `integrity_check=ok`, pusty `foreign_key_check`, koszt `0.684580` USD oraz 0/0/0 jobs/provider attempts/reconciliation events.

Review obejmował 13/13 testów implementera QP-01, 23/23 niezależne kontrpróby, pełny suite 1079/1079 i partycje 259+264+277+279. Checkpoint jest autoryzowany po wykluczeniu chronionych zmian użytkownika. Review nie zamyka Etapu 1, nie zezwala na live API i nie jest zgodą na ponowną migrację ani rejestrację Windows Tasks.
