# N-006 — zamrożona doba operacyjna i trwały budżet

## Metryka

- **Ustalenia:** A-029, A-030, A-031, A-032, A-084
- **Status:** FIXED_OFFLINE; LIVE_CONTRACT_OPEN
- **Start:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** config.py, db.py, operational_day.py, mutation_ledger.py, stages.py, run.py, browser.py, testy i dokumentacja
- **V2:** wyłącznie odczyt; stan początkowy 61/10 run.py, 21/4 stages.py i zastany nieśledzony test

## Hipoteza

Jeżeli początek i koniec doby zostaną wyprowadzone z jednej jawnej strefy redakcyjnej, plan limitów zostanie zapisany raz na dobę, a każda mutacja atomowo zarezerwuje jednostkę budżetu razem z próbą, to restart, współbieżność, awaria dziennika JSONL ani północ UTC nie zwiększą dostępnego wolumenu.

Kontrdowodem jest drugi plan dla tego samego konta i dnia, rezerwacja ponad limit, ponowne udostępnienie jednostki po UNKNOWN, różny dzień dla dwóch chwil należących do tej samej doby redakcyjnej albo brak kategorii dla którejkolwiek mutacji.

## Stan przed

- `stages.budzet_dnia()` losuje nowy plan przy każdym przebiegu;
- follow i subskrypcje nie występują w wyniku `ile_dzis_wystawione()`, więc ich zużycie jest zawsze odejmowane od zera;
- komentarze, lajki i restacki zależą od JSONL, którego zapis i odczyt są fail-open;
- okno publikacji używa `America/New_York`, a liczniki, cichy dzień, przebiegi i promocja daty UTC;
- odpowiedzi nie mają twardego limitu operacyjnego;
- budżet i ledger mutacji nie są jedną transakcją.

## Projektowany kontrakt

1. Jedna `EDITORIAL_TIMEZONE`, początkowo zgodna z `PUBLISH_TIMEZONE`.
2. `OperationalDay` zawiera konto, lokalny klucz dnia, granice UTC, wersję polityki, stan rozbiegu, cichy dzień i niezmienny JSON limitów.
3. Limity dzienne są deterministyczne dla konta, dnia i wersji polityki.
4. Limity miesięczne follow/subskrypcji wybierają dokładnie N dni miesiąca, nie wykonują nowego losowania przy każdym przebiegu.
5. Każdy rodzaj mutacji ma dokładnie jedną kategorię budżetu.
6. Rezerwacja budżetu i utworzenie `mutation_attempts.PENDING` są atomowe.
7. FAILED zwalnia jednostkę; CONFIRMED zużywa; PENDING i UNKNOWN nadal ją zajmują.
8. JSONL pozostaje telemetrią i nie wpływa na możliwość wykonania mutacji.

## Plan testów kontrdowodu

- ta sama doba po obu stronach północy UTC daje ten sam ID i plan;
- przejście lokalnej północy daje nowy dzień;
- granice DST mają 23 albo 25 godzin bez utraty daty;
- dwa połączenia widzą ten sam zamrożony plan;
- zmiana wersji polityki w środku dnia nadal odczytuje istniejący plan;
- dokładnie limit rezerwacji przechodzi, następna jest odrzucona;
- FAILED zwalnia, UNKNOWN nie zwalnia;
- restart zachowuje zużycie;
- follow i subskrypcje są widoczne w trwałym bilansie;
- wszystkie rodzaje mutacji mają kategorię;
- awaria JSONL nie zmienia bilansu SQLite;
- pełna regresja offline pozostaje zielona.

## Rollback

Kod można odłączyć od ścieżki wykonawczej, ale tabel `operational_days` i `action_budget_reservations` nie należy usuwać ani przepisywać. Są dowodem historycznych planów i rezerwacji.

## Odciski przed zmianą

- `config.py`: `8d275dbb1f235f65e5fa1430dd3f3ff35a6d85f52c364e1a2bd9236196741f5a`;
- `stages.py`: `b2ffec049e0a0e8cba376eaf40525caf49af6825f6a4062edfcf76aa98081049`;
- `run.py`: `cf1376f898c5ca4d8557254d35c24645987009b4f60728194da5f56dd7b2570e`;
- `browser.py`: `fba1f68158c5e9eb430f9b0f9e08c17fe25cc13293841545acf9c02f0cb7101b`;
- `db.py`: `6c55f134e2e3a0339f822f2d7bd39a7d69841afbed196fd7ef857f8408f3e0f1`;
- `mutation_ledger.py`: `403c78700b9ab61e329b4abc24eb5de4e8d083df003d08429631f1f7ac7a5a22`.

## Dowody po zmianie

- `test_operational_day.py`: 14/14 PASS. Pokrycie: północ UTC i lokalna,
  23-/25-godzinna doba DST, granica miesiąca, niezmienność planu, dokładna
  alokacja miesięczna, komplet kategorii, limit, FAILED, UNKNOWN, restart,
  współbieżność, awaria JSONL i koszt w dobie redakcyjnej.
- Testy sąsiednie po aktualizacji kontraktu: ciche dni 13/13, promocja 12/12,
  licznik 35/35, obserwacje 34/34, stawki 45/45, zapis wywołań 16/16.
- Finalna bezpieczna regresja: 38/38 plików PASS. Wyłączono platformowy
  `test_czas.py` oraz osobny katalog testów płatnych.
- Pierwsze uruchomienia nie zostały wymazane: historyczne testy dnia dały
  8/9 i 25/35, a pierwsza szeroka regresja 37/38. Przyczyną były stare
  założenia UTC/JSONL i statyczne szukanie dawnego interfejsu budżetu.
- Kontrola po pierwszej zielonej regresji ujawniła A-084: wersja polityki była
  częścią ID dnia i kolidowała z unikalnością `(account, day_key)`. Po
  oddzieleniu tożsamości dnia od wersji test zmiany polityki przechodzi 14/14.
- Kompilacja dziesięciu zmienionych modułów i testu: PASS.
- Koszt online: 0.00 USD. Sieć, modele, przeglądarka, mutacje i deployment:
  nieuruchomione.

## Odciski po zmianie

- `config.py`: `c9c5f5c7c6d8f0a25420d914d0d834bb6398738c4f42c7fa07e7f4d567decc4f`;
- `operational_day.py`: `596c8e14bfb380cd0ff13dba208135f9efe9db0c79cbd352da9ad6d04bf8f03c`;
- `db.py`: `b648d129f156ca20065867cfd381dac4b2be32e7405c2d60177bcf20cf81ccb1`;
- `mutation_ledger.py`: `333e17e445ee90cfc497bf913a1403650b7d639d613aa9f6a44260fb73c9ae55`;
- `browser.py`: `8ba79d26fa199605e1fe682827d049beea6c160a4ebe409343d36594e47f5986`;
- `stages.py`: `cb2bce3d96df5f3658a0a1bca263400a8b12e7589612c38832b82cbc52e807e5`;
- `run.py`: `aa4254c25a1b1a6fa28087fd12beed83feaa41ef703917eda493906f3563d3f5`;
- `llm.py`: `711c9517c0db5a3889768e48645b7a21d9b0758482a4828d42c29657083a3e6e`;
- `alarm.py`: `41c7c5ad493b912a4e90d7d83e18ac26cd5ae6fe66307e3f8834e8ee228fdc60`;
- `tests/test_operational_day.py`: `56dd022d281229c510c4455344a865f7d77c6c8b66aef5e0f8116c721236ee3b`.

## Ograniczenia

- Status nie oznacza gotowości live ani aktualności selektorów platformy.
- `UNKNOWN` nadal wymaga przyszłej automatycznej rekoncyliacji źródłowej;
  obecnie bezpiecznie zatrzymuje wszystkie mutacje.
- Nie wykonano pełnego replayu scout–publikacja ani dodatniego `live_test`.
- Zmiana polityki w środku dnia celowo nie modyfikuje już utworzonego planu;
  zaczyna obowiązywać od następnej doby redakcyjnej.

Pełny opis eksperymentu: `../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-003_DOBA_I_BUDZET.md`.
