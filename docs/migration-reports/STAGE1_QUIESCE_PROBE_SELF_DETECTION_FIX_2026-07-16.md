# Lokalna poprawka quiesce probe — self-detection child PowerShell

Data: 2026-07-16
Branch: `dev/first-successful-research-card`
Bazowy HEAD: `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`
Status implementera po poprawce: `CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`
Aktualny status po dostarczonym niezależnym review: `QP-01 APPROVED / APPROVE WITH MINOR/P2`

## 1. Potwierdzona przyczyna

`_default_quiesce_probe` uruchamiał PowerShell z literalnym `project_root` we własnej command line, po czym ten sam PowerShell wybierał każdy proces spełniający `CommandLine.Contains(project_root)`. Wykluczony był parent Python, lecz nie child PowerShell. PID `15404` został więc wykryty przez proces, który sam go reprezentował.

## 2. Zmienione pliki techniczne

- `app/operations/stage1_migration.py` — snapshot procesów, walidacja helpera, klasyfikacja, fail-closed cleanup i serializowana diagnostyka;
- `tests/test_stage1_quiesce_probe.py` — 13 regresji oraz kontrprób Windows/temp DB.

Pozostałe zmiany dotyczą wyłącznie wymaganej dokumentacji projektu. Executor, migrator, migracje SQL, storage i produkcyjna baza nie zostały zmienione.

## 3. Nowy kontrakt klasyfikacji

PowerShell nie podejmuje decyzji blokującej. Zwraca jeden snapshot `Win32_Process` z:

- PID;
- parent PID;
- executable;
- command line;
- creation time UTC.

Python dodaje classification, reason codes i blocking. Realne role aplikacyjne mają zamknięte kody:

- `APP_ROLE_WORKER`;
- `APP_ROLE_MAINTENANCE`;
- `APP_ROLE_OPERATOR_CLI`.

Proces z kompletną tożsamością i wyłącznie ścieżką repozytorium ma `PROJECT_ROOT_COMMAND_LINE_ONLY` i jest raportowany bez automatycznego STOP. Niepełna tożsamość kandydata lub nieczytelna command line hosta aplikacyjnego blokuje fail-closed.

## 4. Śledzenie helper PID

Każda instancja probe'a rejestruje PID zwrócony przez `subprocess.Popen` oraz jednorazowy nonce. Helper jest uznany za własny wyłącznie wtedy, gdy równocześnie:

1. PID payloadu jest równy PID z `Popen`;
2. parent PID helpera jest równy current Python PID;
3. executable jest PowerShellem;
4. command line zawiera nonce;
5. creation time należy do okna bieżącej instancji.

Wykluczenie dotyczy tylko zarejestrowanych helper PID-ów. Nie obejmuje automatycznie ich dzieci. Timeout zawsze wykonuje terminate, następnie kill w razie potrzeby, i `communicate`.

## 5. Test regresyjny

Rzeczywisty test subprocess odtwarza:

```text
Python pytest process
  -> _default_quiesce_probe
    -> child powershell.exe
       command line contains resolved project root
```

Wynik: child ma `PROBE_REGISTERED_HELPER_IDENTITY`, pełną tożsamość, `blocking=false` i nie występuje w `project_process_ids`. Po zwróceniu raportu jego PID nie jest aktywny.

Osobne realne subprocessy z `-m app.main worker`, `maintain` i `operational-report` pozostają blocking.

## 6. Kontrpróby

| Przypadek | Wynik |
|---|---|
| current Python migratora | PASS / nie blokuje siebie |
| parent PowerShell launchera | PASS / jawny kontrakt launchera |
| zarejestrowany child PowerShell | PASS / nie blokuje |
| helper z project root w command line | PASS / nie blokuje |
| niezależny PowerShell, tylko project root | raportowany jako root-only, nie blokuje |
| worker | STOP |
| maintenance | STOP |
| operator CLI | STOP |
| proces bez project root z uchwytem do temp DB | STOP przez handle gate |
| root-only bez roli | reason code, bez automatycznego STOP |
| proces krótkotrwały | pełna tożsamość zachowana po zakończeniu |
| dwa równoległe probe'y | PASS / nie blokują się |
| brak obcych procesów i uchwytów | quiesce PASS |
| niezarejestrowany worker-potomek helpera | STOP; brak dziedzicznego wykluczenia |
| stary creation time przy tym samym helper PID | STOP; ochrona PID reuse |
| nieczytelna command line Python/PowerShell | STOP fail-closed |

## 7. Pełny suite

- `python -m pytest --collect-only -q`: **1079**;
- `python -m pytest`: **1079 passed**;
- dedykowane probe tests: **13 passed**;
- istniejące testy migracji: **17 passed**;
- exact-once verify: **1079 node IDs**;
- partycje: **259 + 264 + 277 + 279 = 1079**, wszystkie exit 0;
- `python -m compileall -q app scripts tests`: exit 0;
- `git diff --check`: exit 0.

## 8. Stan DB/WAL/SHM

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB` | 294912 B | `2026-07-14T15:59:24.9521212Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-15T12:32:45.2933821Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-15T12:41:22.0340065Z` |

Testy używały wyłącznie tymczasowych plików. Produkcyjna SQLite nie została otwarta ani zmigrowana.

## 9. Repository gate

Przed zmianą: branch i HEAD zgodne, upstream `0/0`, staging pusty, brak aktywnej operacji Git; wcześniejszy dirty state rozpoznany i zachowany.

Po zmianie: branch `dev/first-successful-research-card` i HEAD `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15` bez zmian, upstream `0/0`, staging pusty, brak aktywnej operacji Git, procesów i tasków projektu, runtime oraz journala. Status zawiera 19 wpisów: wcześniejsze zmiany użytkownika/dokumentacji oraz jawny zakres tej poprawki; brak plików `data/`, `.env` i runtime. `git diff --check` zakończył się kodem 0.

## Granice

Nie wykonano sieci, API, SDK, browsera, publikacji, kosztu, Windows Tasks, migracji produkcyjnej, stage, commita, pushu, PR ani merge.

## Późniejszy dowód produkcyjny

W jednej osobno zatwierdzonej próbie produkcyjnej tego samego dnia poprawiony probe przeszedł wszystkie trzy gate'y executora. Helper PowerShell został zachowany w diagnostyce jako `PROBE_HELPER` / `PROBE_REGISTERED_HELPER_IDENTITY`, lecz nie pojawił się w `blocking_processes`. Nie wykryto realnego procesu projektu ani holdera DB/WAL/SHM. QP-01 nie powtórzył się, a executor ustanowił nowy baseline schema 0014. Szczegóły zawiera `docs/migration-reports/STAGE1_DATABASE_MIGRATION_SUCCESS_2026-07-16.md`.

Niezależny review dostarczony później przez właściciela wykonał 23/23 własne kontrpróby obok 13/13 testów implementera i zatwierdził QP-01 wynikiem `APPROVE WITH MINOR/P2`. Reviewer nie modyfikował repozytorium. Historyczny status kandydacki powyżej pozostaje częścią chronologii.
