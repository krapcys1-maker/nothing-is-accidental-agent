# Kontrolowana migracja produkcyjnej bazy Etapu 1 — raport

Data operacji: 2026-07-16
Repozytorium: `<project-root>`
Branch: `dev/first-successful-research-card`
HEAD: `0658e8b221b99bcdaa549cf538ee140a9dc02613`

## Wynik formalny

**MIGRATION FAILED — FULL ROLLBACK COMPLETE**

Produkcja została chwilowo zmigrowana kanonicznym `app.storage.db.apply_migrations` z `0009` do `0014`, lecz końcowy skrypt weryfikacyjny zawierał dodatkowy, błędny warunek wymagający nieobecności WAL/SHM. Sam kontrolowany odczyt SQLite w trybie WAL utworzył ponownie puste sidecary. Wszystkie merytoryczne kontrole bazy były zielone, ale zgodnie z bezwzględnym kontraktem właściciela każdy wynik `FAIL` po mutacji wymaga pełnego restore. Odtworzono zweryfikowany zestaw `agent.db`, `agent.db-wal` i `agent.db-shm`.

Nowy baseline **nie został ustanowiony**. Nie wolno traktować chwilowego SHA zmigrowanej bazy jako obowiązującego baseline.

## 1. Zgoda właściciela

Właściciel jawnie zatwierdził jedną kontrolowaną migrację produkcyjnej bazy `data/agent.db` z `0009` do `0014`, pełny backup DB/WAL/SHM, rehearsal, inicjalizację pięciu flag fail-closed oraz pełny restore w razie dowolnego niepowodzenia po mutacji. Live API, worker paid, browser, publikacja, Windows Task Scheduler oraz operacje Git pozostały zabronione.

## 2. Repository gate przed

- branch: `dev/first-successful-research-card`;
- HEAD: `0658e8b221b99bcdaa549cf538ee140a9dc02613`;
- upstream: `origin/dev/first-successful-research-card`;
- ahead/behind: `0/0`;
- staging: pusty;
- aktywne operacje Git: brak;
- dirty state: dokładnie 8 wcześniejszych plików chronionych;
- runtime: nie istniał.

## 3. Quiesce

- procesy Python: `0`;
- worker/maintenance/operator CLI: `0`;
- procesy zgłoszone przez Windows Restart Manager dla DB/WAL/SHM: `0`;
- wyłączne uchwyty do DB/WAL/SHM: `3/3` uzyskane;
- zadania `NothingIsAccidental-WorkerOffline` i `NothingIsAccidental-Maintenance`: niezarejestrowane;
- ręczny checkpoint produkcji: niewykonany.

## 4. Stary baseline

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB` | 294912 B | `2026-07-14T15:59:24.9521212Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-15T12:32:45.2933821Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-15T12:41:22.0340065Z` |

## 5. Backup

Zweryfikowany backup znajduje się poza repozytorium i poza `data/`:

`%USERPROFILE%\Desktop\agent-project-backups\stage1-db-20260716T1731542164698Z-CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB-0658e8b221b99bcdaa549cf538ee140a9dc02613`

Manifest: `backup-manifest.json`
SHA-256 manifestu: `0B2AA2CFE4DBD7CB28D7C9A605701DA4697204BA30D08B6CC59673860667B3FC`
Status backupu: `VALID`.

Źródło nie zmieniło SHA, rozmiaru ani mtime między preflightem i zakończeniem kopiowania. Wszystkie trzy pliki backupu były identyczne ze źródłem.

## 6. Weryfikacja kopii 0009

Końcowa wersja kontroli kopii: `PASS`.

- `integrity_check = ok`;
- `foreign_key_check = []`;
- dokładnie 9 migracji, ostatnia `0009_jobs_system_flags`;
- 18 wpisów `model_usage`, w tym 13 realnych;
- historyczny koszt `0.684580 USD`;
- 9 runów, digest rekordów `B31106324F5A5E012D02F89219FC97EF0AA9EAEDCAF288A9299E7C0F3837EA75`;
- 5 research_runs, digest rekordów `3B83523B3D72075450A99E54B35923DBEACEE50ADEB28422AA3C3630C9E558C4`;
- 0 jobów i 0 system_flags;
- brak tabel `provider_attempts`, `legacy_model_usage_proofs` i `reconciliation_events`.

Pierwszy raport kontrolny miał błędnie ręcznie wpisane nazwy migracji 0001–0005 i został zachowany jako nieudana próba. Wersja v2 pobrała oczekiwany ledger bezpośrednio z `SOURCE_MIGRATIONS` i przeszła.

Raport v2: `source-0009-verification-report-v2.json`
SHA-256: `1E14F875596C1FAE3C8048A85A7AF70D8F16DE71F58B5EADCA51916AD9CE5C73`.

## 7. Rehearsal

Pierwszy rehearsal został zatrzymany wyłącznie na kopii przez błędną nazwę kolumny `lease_until`; schemat używa `lease_expires_at`. Kopii po tej próbie nie użyto ponownie.

Pełny rehearsal v2 na świeżej kopii zakończył się `PASS`:

- zastosowane dokładnie `0010`–`0014`;
- dokładnie 14 wpisów `schema_migrations`;
- drugi przebieg migratora: no-op;
- wszystkie 3 wymagane tabele obecne;
- 35/35 wymaganych triggerów;
- 13 legacy proofs;
- 18/13 wpisów usage bez zmian;
- koszt `0.684580 USD` bez zmian;
- digests runów i research_runs bez zmian;
- 0 jobów, provider attempts, reconciliation events i aktywnych lease;
- flags: `kill_switch=true`, `safe_mode=true`, `worker_enabled=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`;
- integrity/FK po reopen: `ok` / `[]`.

Raport: `rehearsal-0014-report-v2.json`
SHA-256: `2AC8EA5A0DFD6C3AB3E48BB86B961E52356EDE0ED027CA01A8CEC41694402CE2`.

## 8. Chwilowa migracja produkcyjna

Kanoniczny migrator zastosował dokładnie `0010`–`0014`, a następnie w osobnej transakcji utworzono pięć flag profilu fail-closed. Połączenie zamknięto. Nie wykonano ręcznego checkpointu ani innych zapisów.

Raport wykonania: `production-migration-execution-report.json`
SHA-256: `351C24AEF2957A568E52EE971A7BF68B78C969DF274CE571DC5D3A1E1F1A2B34`.

Chwilowy, **nieobowiązujący** fingerprint po migracji i przed rollbackiem:

- SHA-256: `862E367F1F71448EA37C7B7F21987375CC714E700E07FA3A9B15FAF88EEB2230`;
- rozmiar: `335872 B`;
- mtime UTC: `2026-07-16T17:38:40.6288248Z`.

## 9. Weryfikacja po migracji i przyczyna rollbacku

Wszystkie kontrole merytoryczne przeszły:

- 14 migracji;
- integrity `ok` i FK `[]`;
- 3 wymagane tabele i 35/35 triggerów;
- 13 legacy proofs;
- 18/13 wpisów usage, koszt `0.684580 USD`;
- historyczne runy i research_runs bez zmian;
- wymagane flags fail-closed;
- 0 jobów, aktywnych lease, provider attempts, reconciliation events i live requests.

Raport otrzymał jednak `FAIL`, ponieważ dodatkowa kontrola implementacyjna wymagała `WAL=ABSENT` i `SHM=ABSENT`. Nie był to wymóg właściciela; właściciel wymagał zapisania ich stanu. Odczyt read-only w trybie WAL prawidłowo utworzył puste sidecary: WAL 0 B i SHM 32768 B. Ten nadmiarowy warunek był błędem procedury wykonawczej.

Raport: `production-post-verification-report.json`
SHA-256: `D82DD3FA2D5A0D15721852AA303B3989EBFA1996858AF78246859F4FE3F207F1`.

## 10. Rollback

Zgodnie z instrukcją właściciela nie wykonywano reverse SQL, `UPDATE`, `DELETE` ani edycji `schema_migrations`. Przy pełnym quiesce odtworzono komplet:

- `agent.db`;
- `agent.db-wal`;
- `agent.db-shm`.

Po restore wszystkie trzy SHA, rozmiary i mtime są identyczne ze starym baseline. Brak `agent.db-journal`, otwartych uchwytów i procesów projektu.

**Rollback: FULL ROLLBACK COMPLETE.**

## 11. Repository gate po rollbacku

- branch i HEAD bez zmian;
- upstream `0/0`;
- staging pusty;
- aktywne operacje Git: brak;
- brak runtime artifacts;
- brak zadań Windows;
- brak live API, browsera, publikacji i kosztu;
- dirty state poza tym raportem obejmuje wyłącznie wcześniejsze pliki chronione.

## 12. Status formalny

- produkcyjna baza: ponownie `0009`;
- obowiązujący SHA: `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB`;
- nowy baseline: **NIEUSTANOWIONY**;
- Etap 1: `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`;
- live API: `FORBIDDEN`;
- ponowna migracja wymaga nowej, jawnej zgody właściciela.

## 13. Skonsolidowana poprawka procedury przed drugą próbą

Po analizie incydentu usunięto niezamówiony warunek `WAL=ABSENT`/`SHM=ABSENT`. Obowiązujący kontrakt dopuszcza WAL nieobecny albo 0 B oraz obecny SHM; niezerowy WAL, rollback journal, proces/uchwyt/task projektu lub drift któregokolwiek z DB/WAL/SHM blokuje operację. SHA głównego DB pozostaje wymaganym baseline'em, natomiast sidecary są raportowanymi metadanymi spójności i pełnego restore.

Powstał jeden opakowany, fail-closed executor w istniejącym module i CLI. Wymaga jawnego potwierdzenia, dokładnego branch/HEAD i starego baseline'u; przed otwarciem produkcyjnej SQLite wykonuje pełny quiesce, zweryfikowany backup całego zestawu plików, rehearsal przez kanoniczny migrator i trzy bramki świeżości. Jedyny profil flag to: `kill_switch=true`, `safe_mode=true`, `worker_enabled=false`, `paid_actions_enabled=false`, `browser_actions_enabled=false`. Dowolny błąd po rozpoczęciu operacji na produkcji wymusza pełne odtworzenie DB/WAL/SHM; reverse SQL nie jest obsługiwany.

Poprawkę sprawdzono wyłącznie na tymczasowych bazach: 14/14 kontrprób, collect/full suite 1066/1066, exact-once 1066, cztery wykonane partycje 256/261/275/274, `compileall` i `git diff --check`. **Druga migracja nie została wykonana.** Produkcyjna baza nadal ma schemat `0009`, stary baseline pozostaje obowiązujący, a nowy baseline nie został ustanowiony. Osobna zgoda właściciela i niezależny review poprawionego narzędzia nadal są wymagane. Nie wykonano live API, workera, browsera, Task Schedulera ani operacji Git.
