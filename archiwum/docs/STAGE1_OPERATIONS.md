# Etap 1 — operacje lokalne, scheduler i migracja produkcyjna

Status: **`POST-MIGRATION REVIEW — APPROVE WITH MINOR/P2`; QP-01 = `APPROVED`; produkcja = `VERIFIED / SCHEMA 0014`; pierwsza LA-01 = `REJECTED — MAJOR`; LA-01-R1 i LA-02 = `APPROVED WITH MINOR/P2 — CHECKPOINTED`; LA-03 = `APPROVE WITH MINOR/P2`; P2 po LA-03 (NIA-P2-RV-01…05) = `APPROVE WITH MINOR/P2`.** Root causes `PROCESSES_PRESENT` i `DB_HANDLES_PRESENT` są `CLOSED`; P2-2 false STOP pozostaje `OPEN OBSERVATION / DOCUMENTED`. **Etap 1 = `CLOSED`** (formalna decyzja właściciela 2026-07-17, ADR-088); pierwszy realny durable request został rozliczony bez Research Card, co nie było bramką zamknięcia. Live API jest zabronione bez nowej, oddzielnej zgody właściciela. Terminalny job `real-research-09fd6a30e07e63e96699ca002dbaead4` nie może być ponawiany; ten dokument nie jest zgodą na rejestrację zadań systemowych, migrację, nowy controlled-live ani wywołanie providera.

## Minimalny Windows Task Scheduler

Task Scheduler jest wyłącznie launcherem istniejących entrypointów. Logika eligibility, claimu, lease, Policy Engine, recovery i reapera pozostaje w aplikacji. Nie ma nowego daemona, Windows Service, brokera ani biblioteki schedulerowej.

Generowane zadania:

| Zadanie | Częstotliwość | Kanoniczny entrypoint | Granica |
|---|---:|---|---|
| `NothingIsAccidental-WorkerOffline` | 1 minuta | `python -m app.main worker --once --offline-only` | `--offline-only` blokuje real research niezależnie od runtime flags |
| `NothingIsAccidental-Maintenance` | 5 minut | `python -m app.main maintain --once --stale-after-seconds 300` | tylko recovery → reaper; bez claimu i dispatchu |

Oba zadania używają jawnego interpretera bieżącego środowiska, `<project-root>` jako `WorkingDirectory`, konta interaktywnego bez podwyższania uprawnień, `MultipleInstancesPolicy=IgnoreNew`, braku schedulerowego retry oraz braku hard-kill timeoutu. `ExecutionTimeLimit=PT0S` jest celowe: Task Scheduler nie może przerwać wątku w trakcie zapisu SQLite. Stdout/stderr trafiają do gitignored `runtime/logs/`; launchery propagują exit code procesu, a własny błąd launchera zwraca 70. Nie zapisują ani nie zmieniają `system_flags`.

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

## LA-02 — standalone quiescence check przed nową autoryzacją

Status techniczny: **`APPROVED WITH MINOR/P2 — CHECKPOINTED`**. Root cause pierwszej odmowy jest zamknięty. Poniższa procedura jest obowiązkowa, ale nie stanowi autoryzacji live.

Pierwsza autoryzowana próba controlled-live została zatrzymana przez wewnętrzny check nr 6: `QUIESCENCE_PROJECT_PROCESSES / PROCESSES_PRESENT`. Provider request nie rozpoczął się. Własny PowerShell/cmd/bash launcher wrappera zawierający tekst `-m app.main controlled-live-once` był traktowany jak niezależny operator; stary raport nie zachował blocking PID ani reason codes.

Canonical check diagnostyczny:

```powershell
python -m app.main controlled-live-quiescence-check --db-path data/agent.db
```

Komenda zwraca jedną sanitizowaną strukturę JSON i linię `CONTROLLED-LIVE-QUIESCENCE: PASS|STOP`. Używa dokładnie `default_quiescence_probe` z controlled-live i tego samego klasyfikatora Stage 1. Fingerprintuje main DB i opcjonalne WAL/SHM przed i po, ale nie otwiera SQLite ani `SqliteStorage`, nie czyta/zmienia flags, nie tworzy joba, attemptu, usage, providera, workera lub session marker i nie wymaga `REAL_CONTROLLED_LIVE_ENABLED`. `PASS` nie jest autoryzacją requestu; służy wyłącznie jako część przyszłego preflightu.

### Procedura operacyjna P2-2 — false STOP

1. Zamknąć wszystkie inne terminale, edytory, shelle i procesy pomocnicze, które mogą mieć w command line pełny tekst planowanej komendy `controlled-live-once`. Samo pozostawienie takiego tekstu w niezależnym procesie może legalnie wywołać fail-closed false STOP.
2. Z tego samego launchera i tego samego łańcucha shelli, który miałby później uruchomić live, wykonać wyłącznie `python -m app.main controlled-live-quiescence-check --db-path data/agent.db`.
3. Wymagać `CONTROLLED-LIVE-QUIESCENCE: PASS`, `reason_code=QUIESCENT`, pustych `project_process_ids`, `locked_paths` i `scheduled_tasks` oraz `database_unchanged=true`.
4. Każde `PROCESSES_PRESENT`, każdy `STOP`, brak pełnej identity albo drift DB/WAL/SHM traktować jako bezwarunkowy `STOP`. Nie omijać, nie reinterpretować i nie uruchamiać live w tej samej autoryzacji.
5. Po każdym `STOP` nie ponawiać live. Nowa próba wymaga nowej, jawnej autoryzacji właściciela po ponownym zamrożeniu całego gate'u.

P2-2 pozostaje **`OPEN OBSERVATION / DOCUMENTED`**: procedura ogranicza ryzyko operacyjne, ale w tym checkpointcie nie zmieniono już logiki klasyfikatora. Observation nie blokuje checkpointu LA-02 i nie daje prawa do live.

Wykluczenie launchera wymaga wszystkich dowodów: bieżący current PID, dokładne kolejne PID/PPID, kompletne executable/command line/creation time, jednoznaczny identyczny entrypoint oraz nieodwróconą kolejność creation time. Nazwa `powershell.exe`, `pwsh.exe`, `cmd.exe`, `bash.exe` lub innego shella sama nie wystarcza. Zarejestrowany helper ma dodatkowo nonce i zgodność czasu z oknem probe'a. Niezależny operator z identyczną komendą, drugi controlled-live, worker, maintenance, scheduler/operator CLI, niezarejestrowany potomek, holder DB, Windows Task, PID reuse, cycle i niepełna identity zawsze dają `STOP` albo fail-closed probe error.

Przy odmowie właściwego wrappera trwały raport ma zewnętrzny `reason_code=PREFLIGHT_FAILED`, a `error.reason_code=PROCESSES_PRESENT`, `outer_reason_code=PREFLIGHT_FAILED`, `failing_invariant`, `check_order`, deterministyczne `blocking_process_ids`, identity procesów, `belongs_to_probe_ancestry` i fingerprinty. Command lines przechodzą redakcję API key/Authorization/token/secret/password/prompt/question/guidance/payload oraz wartości wrażliwych ENV. Raport nigdy nie jest powodem do retry.

Stan po checkpointcie LA-02: real gate `False`, flags fail-closed, job `real-research-09fd6a30e07e63e96699ca002dbaead4` nadal `QUEUED/attempts=0`, provider attempts/usage=0, schema `0014`, post-enqueue DB SHA `5FF5DBA3FA57A2DFBB8B638DD7E6CC9E84825A96C6080AA17F8A05B188D97B78`. Następny krok to standalone quiescence check z tego samego launchera i dopiero potem nowa jawna zgoda właściciela.

## Stan po LA-03 i kontrakt przyszłego osobno autoryzowanego invocation

Historyczny job wykonał exactly one attempt i jest terminalny `FAILED/max_attempts=1`; jego request ma trwałe `REQUEST_STARTED`, jedno usage i `SETTLED=0.053182 USD`. Nie wolno uruchamiać go ponownie. Ewentualny przyszły controlled-live wymaga osobnej decyzji właściciela, nowego dozwolonego operation/job, nowego post-enqueue SHA oraz standalone PASS.

Production CLI zawsze wykonuje canonical quiescence/DB-WAL-SHM check przed `SqliteStorage.open`, zamraża cały payload i jawnie przekazuje go do `run_controlled_live_once`. Wrapper nie ma `quiescence_probe=None` ani fallbacku uruchamianego po open. Brak/None payloadu jest błędem konstrukcji przed worker/provider boundary.

Raport nie ma już nazwy `<session_id>.json`. Format to `<session_id>--attempt-1-<UTC timestamp>-<nonce>.json`; recovery używa `recovery-...`. Stable session wiąże logiczną operację, a invocation discriminator zachowuje historię. Marker niesie `report_key`; provisional/final jednego invocation promują ten sam plik atomowo, lecz kolejne invocation nie nadpisują się.

Jedna provider response przechodzi jeden zamknięty parser. Dozwolony jest dokładnie jeden JSON object lub jeden kompletny zewnętrzny fence. Prose, dwa obiekty, niepełny fence, brak pola albo zły typ kończą się fail-closed po tym samym jednym usage/settlement; `stop_reason=max_tokens` jest typowaną truncation. Nie istnieje repair request, retry ani attempt #2. Raw/stop reason są zapisywane wyłącznie prywatnie w `data/debug/research/<run_id>/SINGLE_raw_response.txt` i nigdy nie trafiają do raportu operatorskiego.

## Kontrolowana migracja produkcyjnej bazy `0009→0014`

Historyczny stan bezpośrednio po pierwszej, później cofniętej próbie z 2026-07-16 (nie jest stanem bieżącym):

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
  --workspace %USERPROFILE%\Desktop\agent-project-backups\stage1-second-migration `
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
| Command line | `powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop';$root='<project-root>';$self=10216;..."` |

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

Właściciel udzielił osobnej zgody na dokładnie jedną próbę. Użyto tego samego entrypointu `scripts/prepare_stage1_db_migration.py execute-in-place`, interpretera `<python-path>`, CWD repozytorium i subprocess flow PowerShell → Python → helper PowerShell.

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

Backup, report i baseline znajdują się poza repozytorium w `%USERPROFILE%\Desktop\agent-project-backups\stage1-second-migration-20260716-ddc3c63190eb82bc-attempt-4`. Migracji nie wolno ponawiać w tej sesji. (Stan historyczny na 2026-07-16: Etap 1 pozostawał wtedy `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`. Etap 1 został formalnie zamknięty 2026-07-17 — patrz nagłówek dokumentu i ADR-088.)

### Niezależny review trwałego wyniku migracji i QP-01

Właściciel dostarczył ukończony niezależny review bazowego HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`. Reviewer nie modyfikował repozytorium. Werdykt `APPROVE WITH MINOR/P2` potwierdził QP-01, schema `0014`, baseline `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`, 14 migracji, 35/35 triggerów, 13 legacy proofs, 18 zgodnych digestów historycznych, `integrity_check=ok`, pusty `foreign_key_check`, koszt `0.684580` USD oraz 0/0/0 jobs/provider attempts/reconciliation events.

Review obejmował 13/13 testów implementera QP-01, 23/23 niezależne kontrpróby, pełny suite 1079/1079 i partycje 259+264+277+279. Checkpoint jest autoryzowany po wykluczeniu chronionych zmian użytkownika. Review nie zamyka Etapu 1, nie zezwala na live API i nie jest zgodą na ponowną migrację ani rejestrację Windows Tasks.

## WAVE LA-01-R1 — kanoniczny operator controlled live acceptance (2026-07-17)

Pierwsza LA-01 została odrzucona przez niezależny review (`REJECTED — MAJOR`, P1-01…P1-06, P2-01…P2-04). LA-01-R1 przeszła niezależny review z wynikiem `APPROVE WITH MINOR/P2`; wszystkie P1 są zamknięte, a checkpoint jest dozwolony. **Realne wykonanie pozostaje zablokowane** (`REAL_CONTROLLED_LIVE_ENABLED=false`); `controlled-live-once` odmawia przed otwarciem profilu i nie woła API.

Kanoniczny entrypoint przyszłego, osobno autoryzowanego użycia: `python -m app.main controlled-live-once --account ... --topic-id N --operation-key K --model M --pricing-profile PID --max-tokens T --max-web-searches W --max-cost-usd C --expected-db-sha SHA --expected-schema 0014 --expected-branch BRANCH --expected-head HEAD --max-attempts 1 --max-retries 0`.

Przed uruchomieniem realnego wrappera job musi zostać wcześniej utrwalony wyłącznie przez `scripts/run_capped_research.py --real` z tym samym operation key i zatwierdzonym profilem. Enqueue zapisuje pełny `controlled_session`, a wrapper przez ten sam deterministyczny helper wyprowadza identyczne job/request/attempt/fence i wymaga dokładnego porównania. Wrapper realny nie tworzy joba. Automatyczne utworzenie joba istnieje wyłącznie w procesie z obiema zmiennymi `NIA_TEST_MODE=1` i `NIA_CONTROLLED_LIVE_FAKE=1`, na jawnej tymczasowej bazie różnej od `data/agent.db`.

Sekwencja: canonical pre-storage quiescence/handle check bez SQLite → zamrożenie payloadu → otwarcie głównego storage → pełny durable preflight (branch/HEAD/schema/DB SHA, frozen quiescence, brak lease/rezerwacji, dokładnie jeden expected claimable job, `earliest_run_at≤now`, `max_attempts=1`, `max_retries=0`, pełny frozen pricing) → marker O_EXCL + fsync → drugi identyczny durable recheck → atomowe otwarcie pełnego profilu pięciu flag (`kill_switch` OSTATNI) → jeden worker z trwałym session/job/request/attempt/token fence → bezwarunkowe restoration (`kill_switch` PIERWSZY) → zamknięcie storage i nowe połączenie → walidacja job/run/research_run/attempt/usage/settlement/lease/rezerwacji → sanitizacja → trwały invocation report + fsync → dopiero potem unlink markera + fsync katalogu → finalna promocja raportu.

Sukces wymaga zgodnego expected joba, requestu, attemptu #1, execution fence, dokładnie jednego `SETTLED`, jednego canonical usage, zgodnego settlementu, terminalnych stanów i braku lease/rezerwacji. Sam tekst `SUCCEEDED` nie wystarcza. Brak raportu, błąd report write, błąd marker clear, brak usage/settlement, attempt #2 albo obcy wynik dają niezerowy exit i brak formalnego `COMPLETED`.

Recovery odczytuje trwały `provider_attempt` i `request_started_at`. `REQUEST_STARTED` jest raportowany jako możliwy unknown provider outcome, eskalowany do `NEEDS_RECONCILIATION` bez retry; marker jest usuwany dopiero po trwałym raporcie recovery. `operational-report` pozostaje read-only.

Autorytatywny cennik: przed realnym enqueue właściciel musi ręcznie wpisać zweryfikowane ceny do nieśledzonego `config/pricing_profiles.yaml`, oznaczyć `status: approved`, podać niepuste `approved_by`, wersję, model, walutę i jednostki, oraz wskazać profil przez `--pricing-profile`. Ceny są parsowane jako `Decimal` i nie są pobierane z internetu. `.env` ani ambient `settings.pricing` nie autoryzują realnej projekcji.

Dowód zatwierdzony przez review: `1151/1151` offline, exact-once `275+282+291+303`, zero live API, sieci i kosztu. Open P2: nieosiągalny fallback `sanitize_report_payload` powinien rekurencyjnie sanitizować `str(value)`; rekomendacja jest nieblokująca i nie jest częścią tego checkpointu. Controlled live acceptance nie został wykonany.

### Finalny pricing preflight 2026-07-17 — profil gotowy, runtime zablokowany

Zatwierdzony profil lokalny: `anthropic-sonnet-5-intro-2026-07`, wersja `sonnet-5-intro-pricing-valid-through-2026-08-31`, model `claude-sonnet-5`, fingerprint `1b98c7c9656c5b7791ac4f8eb189d538386c31f52b760920a3f2d89f78bb4062`. Dla topicu `3`, `max_tokens=1500`, jednego web search i capu `0.12 USD` frozen projected wynosi `0.070000`, a pessimistic `0.105000 USD`.

Planowana tożsamość jest deterministyczna: job `real-research-09fd6a30e07e63e96699ca002dbaead4`, request `real-research-09fd6a30e07e63e96699ca002dbaead4:research:1`, attempt `1`. Produkcyjna baza nie zawiera jeszcze tego joba, ponieważ właściciel zakazał enqueue. Nie wolno wykonać wrappera z pre-enqueue SHA `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6`: wrapper zatrzyma się na braku joba, a po enqueue SHA musi zostać ponownie odczytany i jawnie zamrożony.

Po przyszłej osobnej zgodzie kolejność jest bezwzględna: (1) jednorazowa zmiana `REAL_CONTROLLED_LIVE_ENABLED = False` na `True`; (2) kanoniczny enqueue bez providera z tym samym operation key; (3) zamknięcie procesu enqueue i read-only repository/database gate; (4) wpisanie uzyskanego post-enqueue SHA do poniższej komendy; (5) ponowne potwierdzenie właściciela dla dokładnie jednego requestu; (6) pojedyncze uruchomienie wrappera. Jeżeli zmieni się HEAD, schema, topic, profil, fingerprint, claimable jobs, lease, rezerwacja, marker albo flagi, plan jest nieważny.

```powershell
python -m app.main controlled-live-once `
  --account nothing_is_accidental `
  --topic-id 3 `
  --operation-key stage1-live-acceptance-20260717 `
  --model claude-sonnet-5 `
  --pricing-profile anthropic-sonnet-5-intro-2026-07 `
  --max-tokens 1500 `
  --max-web-searches 1 `
  --max-cost-usd 0.12 `
  --expected-db-sha POST_ENQUEUE_SHA_NOT_YET_AUTHORIZED_OR_KNOWN `
  --expected-schema 0014 `
  --expected-branch dev/first-successful-research-card `
  --expected-head af17ce21ffcebe25d619e1f8bf186a5c7affba12 `
  --max-attempts 1 `
  --max-retries 0
```

To jest zamrożony szkielet parametrów, nie gotowa komenda wykonawcza: placeholder DB SHA jest celowym blockerem. Nie wolno zastępować go dynamicznym hashem pobranym w tym samym poleceniu, bo zniosłoby to niezależną bramkę operatora.

#### Wynik jedynej autoryzowanej komendy — 2026-07-17

Job został osobno enqueue’owany, a post-enqueue SHA zamrożono jako `5FF5DBA3FA57A2DFBB8B638DD7E6CC9E84825A96C6080AA17F8A05B188D97B78`. Właściciel autoryzował dokładnie jedną komendę. Zewnętrzny hard preflight przeszedł, gate zmieniono wyłącznie `False→True`, a diff wynosił 1/1. Komenda zakończyła się `PREFLIGHT_FAILED` przed provider boundary.

Historycznie raport `runtime/controlled_live_reports/99f52dd3889688440ef8dc8f26f5e318.json` potwierdzał `provider_request_started=false`, lecz deterministyczna ścieżka została później nadpisana wynikiem LA-03 dla tej samej operation identity. ADR-082 zachowuje stan pierwszej odmowy; utraconego pliku nie rekonstruujemy. Nowy invocation-specific naming zapobiega takim nadpisaniom. **Terminalnego joba nie uruchamiać ponownie.**
