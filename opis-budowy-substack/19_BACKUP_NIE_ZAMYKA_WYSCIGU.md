# Backup nie zamyka wyścigu

## Problem

Kod aplikacji wymagał już schematu `0018`, a produkcyjna baza nadal miała `0014`. Istniały cztery poprawne polecenia migracji — po jednym na każdy szczebel — ale nie istniała jedna kontrolowana operacja, która wiązałaby zgodę właściciela z dokładnym plikiem, jego SHA i rozmiarem, snapshotem oraz finalnym dowodem.

Najważniejsza luka była czasowa. Preflight mógł zobaczyć poprawną bazę. Snapshot mógł być byte-identical. Potem, przed writable open, plik mógł zostać podmieniony albo mógł pojawić się WAL, SHM czy journal. Wcześniejszy wynik nadal wyglądał dobrze, lecz dotyczył już przeszłości.

## Kontrakt

Nowy CLI obsługuje wyłącznie `0014→0018`. Nie jest ogólnym narzędziem do dowolnych wersji. Wymaga:

- absolutnego kanonicznego path;
- dokładnego SHA-256 i rozmiaru;
- stałej wersji początkowej i docelowej;
- nowego snapshotu poza repo;
- jawnej flagi potwierdzającej dokładnie tę drabinę.

Brak któregokolwiek elementu kończy się przed snapshotem i przed migracją.

## Sidecar to dowód, nie śmieć

Obecność `-wal`, `-shm` albo `-journal` oznacza kontrolowany STOP. Orchestrator nie usuwa tych plików, nie próbuje checkpointu i nie uznaje ich zniknięcia po fakcie za dowód wcześniejszej quiescence. Reason code zachowuje dokładną przyczynę.

## Snapshot i druga kontrola

Snapshot powstaje ekskluzywnie, bez nadpisania. Jest fsyncowany, hashowany, otwierany immutable i sprawdzany pod kątem ledgera, integrity i foreign keys. Dopiero potem źródło jest czytane od nowa.

Po dwóch jawnych oknach failpoint następuje ostatni pełny gate bezpośrednio przed `mode=rw`. Writable handle ponownie czyta ledger i porównuje file identity, zanim rozpocznie migrację. Drift daje `STALE_DATABASE_STATE`.

## Uczciwe recovery

Każda migracja `0015–0018` zachowuje własną transakcję schema+ledger. To nie jest jedna atomowa transakcja całej drabiny. Failpoint wewnątrz bieżącego kroku wycofuje ten krok, ale wcześniejsze ukończone szczeble pozostają trwałe.

Raport podaje ostatnią trwałą wersję i następny niewykonany krok. Wznowienie z `0015–0017` wymaga nowego SHA, rozmiaru, snapshotu i zgody właściciela. Nie ma auto-retry. Baza `0018` zwraca `ALREADY_AT_TARGET` bez mutacji.

## Dowód i granice

Orchestrator przeszedł 58/58 testów, w tym 18 okien failpoint. Pełna suita i exact-once: `1630/1630`; partycje `390+398+412+430`; QA runtime `30/30`; dwa harnessy po `13/13`.

Wszystkie zapisy trafiły do nowych temp DB. Produkcyjna baza pozostała na `0014`, byte-identical z wejściowym SHA i rozmiarem. Nie było sieci, API, providera, browsera, publikacji ani kosztu.

Status: `PRODUCTION MIGRATION ORCHESTRATOR — CANDIDATE COMPLETE, AWAITING INDEPENDENT REVIEW`. To nie jest zgoda na migrację produkcji ani controlled-live.
