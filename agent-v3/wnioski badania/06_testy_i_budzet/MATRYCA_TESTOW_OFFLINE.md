# Matryca testów offline

| Własność | Poziom | Transport | Stan danych | Kryterium zaliczenia |
|---|---|---|---|---|
| brak ścieżki wykonawczej V3 -> V2 | static | brak | repo | zero aktywnych odwołań operacyjnych |
| brak sekretów w fixture mode | integration | fake env/session | temp | próba odczytu kończy test błędem |
| globalny capability gate | property | fake transport | temp | każda mutacja bez możliwości jest odrzucona przed adapterem |
| idempotency publikacji | integration | fake API | temp DB | timeout po zapisie nie powoduje drugiej mutacji |
| zamrożony budżet dnia | property | brak | temp DB | restart nie zmienia wylosowanego budżetu |
| pełne liczenie działań | unit/integration | fake ledger | temp | follow/subskrypcje i inne typy zmniejszają właściwe limity |
| fail-closed dziennika | integration | błędny writer | temp | awaria zapisu blokuje kolejną mutację |
| bezpieczny URL | property | fake DNS/HTTP | fixture | prywatne IP i redirect są blokowane |
| limit odpowiedzi | integration | streaming fixture | temp | klient przerywa po limicie bajtów |
| schema LLM | property | replay JSON | fixture | brak pola/typ/enum kończy etap kontrolowanym błędem |
| pochodzenie faktu | property | evidence fixture | temp DB | fakt bez pełnego łańcucha nie osiąga `READY_AUTONOMOUS` |
| rewizja bez nowego faktu | replay | fake LLM | fixture | wszystkie nowe fakty mają źródło, teza zachowana |
| pełna ponowna kontrola | integration | fake LLM | fixture | rewizja przechodzi wszystkie bramki od początku |
| kwarantanna | state machine | brak | temp DB | limit rewizji prowadzi do właściwego stanu, nigdy publikacji |
| cache contract | unit/property | brak | temp | zmiana promptu/modelu/schematu unieważnia cache |
| rezerwacja kosztu | unit | fake provider | temp DB | krok nie startuje bez dostępnej rezerwy |
| snapshoty metryk | integration | fake analytics | temp DB | 1h/24h/7d są append-only i nie zamieniają braku na zero |
| kohorta wyniku | property | synthetic cohort | temp DB | wynik względny używa właściwego typu i okresu |
| reguła uczona | simulation | synthetic history | temp DB | aktywacja dopiero po próbie, stabilności i kontrprzykładzie |
| rollback reguły | simulation | synthetic drift | temp DB | pogorszenie przekracza próg i automatycznie wycofuje wersję |
| brak efektów po teście | hermeticity | socket/file guards | temp | repo i `agent-v3/data` bez nowych plików |
