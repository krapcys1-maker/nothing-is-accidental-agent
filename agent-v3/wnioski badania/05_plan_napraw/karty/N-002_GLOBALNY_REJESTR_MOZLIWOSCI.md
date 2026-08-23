# N-002 — globalny rejestr możliwości

## Metryka

- **Ustalenia:** A-003, A-004, A-023, A-056, A-058, A-059
- **Status:** FIXED_OFFLINE
- **Start:** 2026-08-21
- **Baza:** codex/agent-v3-gpt, commit 57a9474362b8fa6d120027aa54afe1a918b65b0f
- **Zakres V3:** capabilities.py, run.py, browser.py, llm.py, alarm.py
- **V2:** brak zmian

## Hipoteza

Jeżeli każda granica zewnętrzna i mutacja otrzyma centralną, dynamicznie sprawdzaną możliwość, lokalna flaga nie wystarczy do działania. Kontrdowodem jest mutacja bez bramki albo bramka sprawdzana tylko podczas startu.

## Stan przed

- KILL_SWITCH zatrzymuje tylko LLM, nie przeglądarkę ani SMTP;
- naprawde_wyslac sprawdza tylko statyczne DRY_RUN;
- znacznik kopii działa wyłącznie przez główne CLI;
- wyslij=False wypełnia żywe edytory i może utworzyć zdalny draft artykułu.

## Projekt kontraktu

Tryby: fixture — zero sieci; model_test — modele i publiczny odczyt; live_read_only — także odczyt Substacka; live_test — mutacje wyłącznie na odseparowanym koncie testowym. Wyłącznik jest odczytywany przy każdym żądaniu możliwości i domyślnie aktywny.

## Test kontrdowodu

- macierz tryb × możliwość;
- dynamiczny kill switch;
- odmowa live_test bez osobnego handle, znacznika i potwierdzenia maszynowego;
- bezwarunkowy zakaz mutacji celu nothingisaccidental;
- każda funkcja mutująca z wyslij=False kończy się bez przeglądarki.

## Minimalna zmiana i rollback

Jeden niezależny moduł polityki; bramki przy transporcie i mutacji; brak procesu zatwierdzania. Rollback usuwa moduł i cofa wyłącznie importy V3.

## Dowody po zmianie

- powstał capabilities.py z czterema trybami i czternastoma klasami możliwości;
- kill switch jest dynamiczny i domyślnie aktywny;
- bramki objęły modele, publiczny HTTP, odczyt Substacka, zapis sesji, SMTP i dziewięć klas mutacji;
- wszystkie dziesięć wejść mutujących kończy wyslij=False przed sesją i przeglądarką;
- CLI odmawia --wyslij przed zamkiem i bazą; kod wyjścia 1, drzewo agent-v3/data bez zmian;
- konto nothingisaccidental jest bezwarunkowo zabronione dla mutacji V3;
- live_test wymaga zgodnych handle, znacznika prototypu, aktywnego trybu, wyłączonego kill switcha i dokładnego tokenu maszynowego;
- test celu: 14/14 PASS; pełna regresja: 35/35 plików PASS;
- koszt online: 0 USD; nie uruchomiono live_test.

Odcisk capabilities.py po zmianie: 0672d0782dc7762381155505c6eb3e96b67c0d4cea322c57a2440500358b34ee.

## Wynik

Hipoteza utrzymana offline. Kontrakt odmowy jest dowiedziony; pozytywna ścieżka przeglądarkowa live_test pozostaje do osobnego eksperymentu na odseparowanym koncie.
