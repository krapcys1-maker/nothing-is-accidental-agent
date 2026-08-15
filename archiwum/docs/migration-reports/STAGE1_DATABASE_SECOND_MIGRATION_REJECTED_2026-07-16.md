# Druga kontrolowana migracja produkcyjnej bazy Etapu 1 — raport odrzucenia

Data operacji: 2026-07-16

Repozytorium: `<project-root>`

Branch: `dev/first-successful-research-card`

HEAD: `ddc3c63190eb82bca171174dc7ee70c2d0a1ec15`

## 1. Zgoda właściciela

Właściciel jawnie zatwierdził jedno uruchomienie wyłącznie zacommitowanego `run_stage1_in_place_migration`, wraz z pełnym quiesce, backupem, rehearsal i ewentualną migracją produkcji `0009→0014`. Live API, SDK, worker, maintenance, browser, publikacja, Windows Task Scheduler i operacje Git pozostały zabronione.

## 2. Repository gate przed

- branch i HEAD: zgodne;
- upstream: `origin/dev/first-successful-research-card`;
- ahead/behind: `0/0`;
- staging: pusty;
- aktywne operacje Git: `0`;
- dirty state: dokładnie osiem wcześniejszych chronionych wpisów;
- runtime: nie istnieje;
- zadania Windows projektu: `0`;
- procesy projektu wykryte przed uruchomieniem: `0`;
- `agent.db-journal`: nie istnieje.

## 3. Stary baseline

| Plik | SHA-256 | Rozmiar | mtime UTC |
|---|---|---:|---|
| `data/agent.db` | `CAEDDA05B4E9BCA70346031F5812D5EA38C4A7390D1E52E22FDFA12AF4EBFEFB` | 294912 B | `2026-07-14T15:59:24.9521212Z` |
| `data/agent.db-wal` | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` | 0 B | `2026-07-15T12:32:45.2933821Z` |
| `data/agent.db-shm` | `FD4C9FDA9CD3F9AE7C962B0DDF37232294D55580E1AA165AA06129B8549389EB` | 32768 B | `2026-07-15T12:41:22.0340065Z` |

## 4. Quiesce

Executor został uruchomiony z literalnym `--confirm-in-place-production-migration`. Pierwszy zatwierdzony gate zwrócił:

```text
Full quiescence was not proven: processes=(17196, 34228), handles=(), tasks=().
```

Operacja została odrzucona fail-closed. Oba PID-y nie istniały już podczas kontroli po zakończeniu polecenia. Ich tożsamości nie rekonstruowano po fakcie i nie zastępowano zatwierdzonego probe'a własnym kryterium.

## 5. Backup i manifest

Nie utworzono. Gate quiesce występuje przed `workspace.mkdir`; wybrany nowy workspace pozostał nieobecny.

## 6. Trzy fingerprinty

- fingerprint przed backupem: zgodny ze starym baseline'em;
- fingerprint po backupie: nie dotyczy, backup nie rozpoczął się;
- fingerprint bezpośrednio przed mutacją: nie dotyczy, mutacja nie rozpoczęła się;
- fingerprint kontrolny po odrzuceniu: dokładnie zgodny ze starym baseline'em dla DB/WAL/SHM.

## 7. Rehearsal

Nie rozpoczął się. Produkcyjna SQLite nie została otwarta.

## 8. Produkcyjna migracja

Nie rozpoczęła się. Nie zastosowano `0010`–`0014` i nie wykonano żadnego SQL.

## 9. Post-verification

Nie dotyczy migracji. Kontrola braku mutacji potwierdziła stary fingerprint, brak journala, workspace i runtime.

## 10. Dane historyczne i koszt

Nie zostały otwarte ani zapisane. Bitowo identyczny główny DB pozostaje dowodem zachowania starego stanu i kosztu `0.684580 USD`. Koszt operacji: `0 USD`.

## 11. System flags

Nie zainicjalizowano. Produkcja pozostaje w stanie schematu `0009` sprzed migracji.

## 12. Nowy baseline

Nie ustanowiono. Obowiązuje nadal stary baseline schema `0009`.

## 13. Stan WAL/SHM

- WAL: obecny, 0 B, SHA i mtime bez zmian;
- SHM: obecny, 32768 B, SHA i mtime bez zmian;
- ich obecność nie spowodowała odrzucenia;
- journal: nieobecny.

## 14. Rollback

Nie był potrzebny, ponieważ executor zakończył się przed backupem i przed mutacją. Nie wykonano reverse SQL ani restore.

## 15. Repository gate po

- branch, HEAD i upstream: bez zmian, `0/0`;
- staging: pusty;
- operacje Git: brak;
- runtime i zadania Windows: brak;
- DB/WAL/SHM: dokładnie stary baseline;
- brak API, SDK, workera, maintenance, browsera, publikacji i kosztu;
- dirty state rozszerzono wyłącznie o jawnie dozwoloną dokumentację tej operacji.

## 16. Stan formalny Etapu 1

**MIGRATION REJECTED BEFORE MUTATION**

Produkcja pozostaje na schemacie `0009`. Nowy baseline nie istnieje. Automatyczna kolejna próba nie została wykonana i wymaga nowej zgody właściciela. Etap 1 pozostaje `OPEN / BLOCKED PENDING CONTROLLED LIVE ACCEPTANCE`; live API pozostaje `FORBIDDEN`.
