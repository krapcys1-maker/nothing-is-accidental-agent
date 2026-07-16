# Etap 1 — kontrolowana migracja produkcyjnej bazy 0009 → 0014 po QP-01

Data: 2026-07-16
Repozytorium: `C:\Users\user\Desktop\agent project`
Branch: `dev/first-successful-research-card`
HEAD: `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`

## 1. Autoryzacja i granice

Właściciel zatwierdził dokładnie jedną próbę pakietowego executora `run_stage1_in_place_migration` z obowiązkowym `--confirm-in-place-production-migration`. Wykorzystano ten sam realny flow, który ujawnił QP-01: PowerShell uruchomiony z katalogu repozytorium → interpreter `C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe` → `scripts/prepare_stage1_db_migration.py execute-in-place` → helper PowerShell probe'a.

Nie wykonywano review, pełnego audytu, zmian kodu, drugiej próby, live API, workera, maintenance, browsera, publikacji, rejestracji Windows Tasks ani operacji zapisujących Git.

## 2. Gate wejściowy

- branch i HEAD: zgodne z autoryzacją;
- upstream: `origin/dev/first-successful-research-card`, ahead/behind `0/0`;
- staging: pusty;
- aktywne operacje Git: brak;
- procesy projektu, worker, maintenance i operator CLI: brak;
- zadania Windows projektu: brak;
- `data/agent.db-journal`: brak;
- `data/agent.db-wal`: obecny, 0 B;
- `runtime/`: brak.

Stary baseline przed próbą:

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB` | 294912 B | `2026-07-14T15:59:24.9521212Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-15T12:32:45.2933821Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-15T12:41:22.0340065Z` |

## 3. Jedyna próba executora

Executor zakończył się kodem 0 i komunikatem:

```text
IN-PLACE MIGRATION: PASSED — NEW SCHEMA-0014 BASELINE ESTABLISHED
```

Nie wykonano i nie wolno wykonywać drugiej próby w tej sesji.

## 4. Dowód usunięcia QP-01

W każdym z trzech gate'ów — initial, after-backup i pre-mutation — wynik był taki sam:

- blocking processes: 0;
- blocking DB/WAL/SHM handles: 0;
- project Windows tasks: 0;
- helper classification: `PROBE_HELPER`;
- helper reason code: `PROBE_REGISTERED_HELPER_IDENTITY`;
- helper blocking: false.

Helper PowerShell pozostał widoczny i w pełni opisany, lecz nie został błędnie sklasyfikowany jako obcy proces projektu. Nie poluzowano wykrywania realnych ról aplikacyjnych ani uchwytów bazy.

## 5. Backup, rehearsal i migracja

Executor:

1. utworzył i zweryfikował pełny backup schema 0009;
2. wykonał rehearsal na kopii;
3. ponownie sprawdził quiesce i świeżość plików;
4. zastosował kolejno migracje 0010, 0011, 0012, 0013 i 0014;
5. zainicjalizował kanoniczne flagi fail-closed;
6. wykonał post-verification;
7. ustanowił nowy baseline.

Backup został zweryfikowany jako niezmieniony po migracji.

## 6. Kryteria sukcesu

| Kryterium | Wynik |
|---|---:|
| migracje | 14 (`0001`–`0014`) |
| zastosowane w tej próbie | `0010`–`0014` |
| triggery | 35/35 |
| legacy proofs | 13 |
| historyczny koszt realny | `0.684580 USD`, bez zmiany |
| jobs | 0 |
| provider_attempts | 0 |
| reconciliation_events | 0 |
| integrity_check | `ok` |
| foreign_key_check | `[]` |

Historyczne tabele pozostały zgodne z pre-migration snapshotem executora:

- `runs`: 9 wierszy, SHA-256 `24832880A3A896239E8296EF4756416C225148E1928D6D6C73D743D9A43CD003`;
- `research_runs`: 5 wierszy, SHA-256 `8CC53B886305224831C9FF0F05A2FBD75AC2B470FF2A3908BD78A9CD1E566132`.

Kanoniczne flagi:

```text
kill_switch=true
safe_mode=true
worker_enabled=false
paid_actions_enabled=false
browser_actions_enabled=false
```

## 7. Nowy baseline

Status baseline'u: `NEW_SCHEMA_0014_BASELINE_ESTABLISHED`.

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `630E3411F2FDFBD232F593DC7E7F3B0DF3EB8125274365815CDBDBC2A3C036A6` | 335872 B | `2026-07-16T19:42:25.5377560Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-16T19:42:25.5417557Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-16T19:42:25.5507558Z` |

## 8. Artefakty executora

Workspace poza repozytorium:

`C:\Users\user\Desktop\agent-project-backups\stage1-second-migration-20260716-ddc3c63190eb82bc-attempt-4`

Zawiera:

- `verified-full-backup-schema-0009\`;
- `stage1-in-place-migration-report.json`;
- `stage1-new-baseline.json`.

## 9. Repository gate po migracji

- branch: `dev/first-successful-research-card`, bez zmiany;
- HEAD: `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`, bez zmiany;
- upstream: `origin/dev/first-successful-research-card`, ahead/behind `0/0`;
- staging: pusty;
- aktywne operacje Git: brak;
- procesy projektu: 0;
- zadania Windows projektu: 0;
- `runtime/`: brak;
- `data/agent.db-journal`: brak;
- `git diff --check`: exit 0.

Pełny `git status` pozostał dirty i zawiera 22 wpisy. Są to wcześniejsze, niestage'owane zmiany QP-01/innych prac oraz aktualizacje dokumentacyjne tego kontrolowanego wykonania. Żaden plik nie został dodany do stagingu, commitowany ani wypchnięty.

## 10. Granice wyniku

- live API: niewykonane;
- nowy koszt: 0 USD;
- worker/maintenance/browser/publikacja: niewykonane;
- Windows Tasks: niezarejestrowane i niezmienione;
- Git stage/commit/push/PR/merge: niewykonane;
- Etap 1: `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`.

## 11. Wynik

**MIGRATION COMPLETE — NEW BASELINE ESTABLISHED**

## 12. Późniejszy niezależny review

Właściciel dostarczył ukończony niezależny review trwałego wyniku migracji i QP-01. Reviewer nie modyfikował repozytorium. Werdykt `APPROVE WITH MINOR/P2` potwierdził produkcję jako `VERIFIED / SCHEMA 0014`, nowy baseline jako `VERIFIED` i QP-01 jako `APPROVED`. Review potwierdził także 18 zgodnych digestów historycznych, 23/23 niezależne kontrpróby QP-01 i brak CRITICAL oraz MAJOR/P1. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`; live API pozostaje zabronione.
