# N-005 — ledger prób i potwierdzeń

## Metryka

- **Ustalenia:** A-005, A-006, A-060, A-069
- **Status:** FIXED_OFFLINE; LIVE_CONTRACT_OPEN
- **Start:** 2026-08-21
- **Baza:** codex/agent-v3-gpt, commit 57a9474362b8fa6d120027aa54afe1a918b65b0f
- **Zakres V3:** db.py, mutation_ledger.py, browser.py, run.py, testy i dokumentacja
- **V2:** brak zmian

## Hipoteza

Jeżeli każda mutacja zostanie trwale zarezerwowana przed kliknięciem, oznaczona jako wysłana bezpośrednio przed kliknięciem i uznana za sukces wyłącznie z referencją potwierdzającą ze źródła, to timeout i restart nie spowodują automatycznego duplikatu. Kontrdowodem jest druga rezerwacja dla klucza w stanie PENDING, UNKNOWN albo CONFIRMED albo sukces bez `source_ref`.

## Stan przed

- dziennik JSONL powstaje dopiero po kliknięciu i może cicho nie zapisać się wcale;
- brak wpisu nie odróżnia niewykonanej próby od procesu przerwanego po mutacji;
- potwierdzenie artykułu używa podobieństwa tytułu, nie ID bieżącego szkicu;
- run.py zwiększa część liczników po próbie, niezależnie od potwierdzenia;
- restart może ponowić działanie o nieznanym skutku.

## Maszyna stanów

- PENDING — trwała rezerwacja istnieje; brak dowodu, że wywołano mutację;
- CONFIRMED — źródło zwróciło ID obiektu albo ujawniło jednoznaczną, wersjonowaną referencję stanu zgodną z próbą;
- UNKNOWN — mutację wysłano, lecz nie uzyskano jednoznacznego potwierdzenia;
- FAILED — awaria nastąpiła przed wysłaniem mutacji.

PENDING, UNKNOWN i CONFIRMED blokują kolejną próbę tego samego klucza. Dowolne nierozstrzygnięte PENDING lub UNKNOWN blokuje również inne mutacje. Tylko FAILED może utworzyć następną sekwencję.

## Klucz idempotencji

SHA-256 z wersjonowanego obiektu: wersja kontraktu, konto testowe, rodzaj mutacji, kanoniczny cel i hash treści. Klucz nie zawiera czasu, dlatego restart nie tworzy nowej tożsamości działania.

## Test kontrdowodu

- rezerwacja jest widoczna z drugiego połączenia przed dispatch;
- PENDING, UNKNOWN i CONFIRMED blokują duplikat;
- FAILED pozwala na nową sekwencję;
- wyjątek przed dispatch daje FAILED;
- wyjątek po dispatch daje UNKNOWN;
- confirm bez dispatch lub bez source_ref jest zabroniony;
- awaria zapisu ledgeru następuje przed atrapą kliknięcia;
- artykuł nie może zostać potwierdzony tylko podobnym tytułem.
- restart przed dispatch daje FAILED, a po dispatch daje UNKNOWN;
- UNKNOWN zatrzymuje serię i dalsze bloki mutujące;
- niepotwierdzone wyniki nie zwiększają liczników ani historii celu.

## Rollback

Kod można odłączyć od przeglądarki, ale tabeli nie należy usuwać ani przepisywać. Jest append-only dowodem prób.

## Dowody po zmianie

- tabela `mutation_attempts` przechowuje ID próby, wersjonowany klucz, sekwencję, konto, rodzaj, cel, hash treści, czasy przejść, stan, `source_ref`, błąd i metadane;
- `BEGIN IMMEDIATE` łączy sprawdzenie i rezerwację w jedną sekcję krytyczną;
- odzyskiwanie działa dopiero po wyłącznym zamku procesu;
- restart przed utrwalonym dispatch kończy próbę jako FAILED i pozwala na sekwencję 2;
- restart po dispatch kończy próbę jako UNKNOWN i uruchamia globalną kwarantannę mutacji;
- artykuł wymaga dokładnego ID szkicu, dokładnego tytułu i daty;
- komentarz, notka, odpowiedź i restack wymagają ID obiektu ze źródła;
- polubienie, obserwacja i subskrypcja używają wersjonowanej referencji potwierdzonego stanu UI;
- ustawienie bez stabilnej referencji pozostaje UNKNOWN;
- test ledgeru: 16/16 PASS;
- test granicy komentarza: 19/19 PASS, w tym wyjątek po dispatch zachowujący UNKNOWN i ID próby;
- test pętli restacku: 17/17 PASS, w tym kontrprzykład UNKNOWN;
- pełna bezpieczna regresja: 37/37 plików PASS;
- koszt online: 0 USD; sieć i mutacje zewnętrzne: brak.

## Wynik i ograniczenie

Hipoteza utrzymana offline. Dodatni test live nie został wykonany, więc aktualności selektorów i endpointów nie uznano za dowiedzioną. Automatyczna rekoncyliacja źródłowa stanu UNKNOWN pozostaje otwarta; bieżący kontrakt bezpiecznie poddaje wszystkie mutacje kwarantannie zamiast zgadywać albo ponawiać.

Pełny raport: `../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-002_LEDGER_MUTACJI.md`.

## Odciski końcowe SHA-256

- `mutation_ledger.py`: `403c78700b9ab61e329b4abc24eb5de4e8d083df003d08429631f1f7ac7a5a22`;
- `db.py`: `6c55f134e2e3a0339f822f2d7bd39a7d69841afbed196fd7ef857f8408f3e0f1`;
- `browser.py`: `fba1f68158c5e9eb430f9b0f9e08c17fe25cc13293841545acf9c02f0cb7101b`;
- `run.py`: `cf1376f898c5ca4d8557254d35c24645987009b4f60728194da5f56dd7b2570e`;
- `tests/test_mutation_ledger.py`: `9548a0632dc87f24460b7bb695ab7550d9b8651434a1efc93b3ef1f444434da1`;
- `tests/test_pole_komentarza.py`: `e9946f1685718de34463ec696122a7a18665da0ab61ab1c7bfb7f94cd5f249ee`;
- `tests/test_restack_petla.py`: `9d48e909a4e4a753e748d0a17f5781a8e1f4525a53aeeb30f445974bfd2b5594`.
