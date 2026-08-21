# Agent V3 — centralny indeks badań i dokumentacji

**Stan:** prototyp badawczy; audyt i projektowanie napraw, bez wdrożenia  
**Data konsolidacji:** 2026-08-21  
**Gałąź robocza:** `codex/agent-v3-gpt`  
**Commit bazowej migawki:** `00ab0c4`  
**Zakres zapisu:** wyłącznie `agent-v3` oraz związany z nim wpis w głównym `.gitignore`  
**Materiał porównawczy:** `agent-v2` wyłącznie do odczytu

## Cel katalogu

Ten katalog jest jednym punktem prawdy o badaniu Agent V3. Zawiera:

- opis działania agenta;
- kompletny audyt i rejestr błędów;
- materiały historyczne i hipotezy wejściowe;
- porównanie z publicznymi repozytoriami;
- plan napraw wykonywanych błąd po błędzie;
- politykę testów i kosztów;
- dziennik badań, wersje badanego korpusu i zasady replikacji.

Nie jest to instrukcja uruchamiania produkcji. Żaden dokument w tym katalogu nie upoważnia do publikowania, wdrażania usług, uruchamiania timerów ani korzystania z żywej sesji Substack.

## Najkrótsza odpowiedź: gdzie jesteśmy

V3 nie trzeba projektować od zera. Rdzeń research–synteza–pisanie–recenzja–bramki–dystrybucja jest rozbudowany, ale system nie jest jeszcze wiarygodną autonomiczną redakcją. Audyt wykazał 73 ustalenia. Najpilniejsze dotyczą izolacji prototypu od produkcji, potwierdzania rzeczywistych skutków, stałości limitów, bezpieczeństwa pobierania URL, pochodzenia twierdzeń i niekontrolowanych mutacji przy `wyslij=False`.

W tej fazie nie rozpoczęto napraw funkcjonalnych. Najpierw utrwalamy stan, dowody, kolejność prac oraz bezpieczny protokół testowania.

## Zalecana kolejność czytania

1. [`01_audyt/DOKUMENTACJA_AUDYTU.md`](01_audyt/DOKUMENTACJA_AUDYTU.md) — skrót wyniku audytu.
2. [`01_audyt/MAPA_DZIALANIA_AGENTA_V3.md`](01_audyt/MAPA_DZIALANIA_AGENTA_V3.md) — jak agent działa i gdzie przebiegają granice odpowiedzialności.
3. [`01_audyt/MONOGRAFIA_AUDYTOWA_V3.md`](01_audyt/MONOGRAFIA_AUDYTOWA_V3.md) — pełna praca audytowa.
4. [`01_audyt/SPOSTRZEZENIA_AUDYTOWE.md`](01_audyt/SPOSTRZEZENIA_AUDYTOWE.md) — 73 ustalenia z priorytetami.
5. [`04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md`](04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md) — zweryfikowane inspiracje z publicznego kodu.
6. [`05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md`](05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md) — kolejność poprawiania V3 błąd po błędzie.
7. [`06_testy_i_budzet/POLITYKA_TESTOW_I_BUDZETU.md`](06_testy_i_budzet/POLITYKA_TESTOW_I_BUDZETU.md) — co wolno uruchamiać i za ile.
8. [`07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md`](07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md) — metoda, poziomy dowodu i ograniczenia.

## Struktura katalogu

| Katalog | Rola | Status epistemiczny |
|---|---|---|
| `01_audyt/` | wynik audytu, mapa systemu, 73 ustalenia, aneks techniczny | obserwacja kodu i wnioski audytora |
| `02_dokumentacja_zastana/` | dokumenty skopiowane lub przeniesione z wcześniejszego etapu projektu | materiał historyczny; nie zawsze aktualny kontrakt V3 |
| `03_materialy_wejsciowe/` | wcześniejsze propozycje i notatki z internetu wraz z ich krytyczną analizą | źródło hipotez, nie dowód |
| `04_badania_porownawcze/` | datowane badanie publicznych repozytoriów | dowód źródłowy + jawne inferencje |
| `05_plan_napraw/` | uporządkowany backlog i protokół pojedynczej naprawy | plan przyszłych zmian |
| `06_testy_i_budzet/` | matryca testów, budżety i księga wydatków | obowiązująca polityka eksperymentów |
| `07_dziennik_badan/` | chronologia, metoda, migawki i decyzje | ślad replikacyjny |

## Dokumentacja zastana

Dokumenty w `02_dokumentacja_zastana/` zostały zachowane, ponieważ opisują genezę i wcześniejszy model działania. Nie wolno automatycznie traktować ich jako aktualnej instrukcji V3. Szczególnie ostrożnie należy czytać pliki z nazwą V2, komendy wdrożeniowe i stwierdzenia, że „nic nie blokuje”. Aktualny stan ustala audyt, a nie wiekowy opis.

## Dokumentacja operacyjna pozostawiona przy kodzie

Niektóre pliki Markdown są jednocześnie wejściami wykonywalnymi albo instrukcjami ściśle związanymi z lokalizacją kodu. Nie zostały przeniesione, aby nie zmienić zachowania prototypu:

- `agent-v3/prompts/*.md` — aktywne prompty i polityki treści;
- `agent-v3/tests/URUCHOM.md` — instrukcja testów lokalnych;
- `agent-v3/tests/platne/PRZECZYTAJ.md` — ostrzeżenia przy testach płatnych;
- `agent-v3/pomiary/PRZECZYTAJ.md` — instrukcja pomiaru sieciowego;
- pliki Markdown w `tests/fixtures/` — dane testowe, nie dokumentacja projektu.

Są skatalogowane w aneksie audytu i pozostają częścią badanego korpusu.

## Zasady nadrzędne

1. V2 jest materiałem porównawczym i nie wolno go modyfikować, formatować, stage'ować ani commitować.
2. Naprawy mogą dotyczyć tylko V3.
3. Offline jest domyślnym trybem testu.
4. Dostęp do internetu nie oznacza zgody na zmianę konta zewnętrznego.
5. Nie wolno publikować, tworzyć żywych draftów, lajkować, komentować, restackować, obserwować, subskrybować ani wdrażać produkcji.
6. Każda naprawa ma własną hipotezę, test kontrdowodu, test regresji i wpis w dzienniku.
7. „Kliknięto” nie znaczy „wykonano”; sukces wymaga potwierdzenia u źródła i powiązania z konkretną próbą.
8. Brak danych nie może być zapisywany jako zero ani sukces.
9. Reguły redakcyjne mogą aktualizować się autonomicznie wyłącznie po spełnieniu wersjonowanego kontraktu: minimalna próba, stabilność w czasie, kontrprzykład, ograniczony rollout i automatyczny rollback.
10. Dokumenty rozróżniają fakt, inferencję, hipotezę i decyzję projektową.

## Konwencja dowodowa

- **Fakt F** — bezpośrednio odtworzony z lokalnego kodu, testu, historii Git albo wskazanego źródła pierwotnego.
- **Inferencja I** — logiczny wniosek z jednego lub kilku faktów; musi być oznaczony jako wniosek.
- **Hipoteza H** — przypuszczenie wymagające eksperymentu.
- **Decyzja D** — świadomy wybór projektowy, którego nie da się wyprowadzić wyłącznie z danych.

## Stan Git i publikacji

Gałąź `codex/agent-v3-gpt` jest gałęzią prototypową. Samo zapisanie kodu i dokumentacji na GitHubie nie jest wdrożeniem produkcyjnym. Nie wolno jednak tworzyć automatyzacji, release'u, obrazu produkcyjnego ani uruchamiać skryptów wdrożeniowych w ramach tej gałęzi.

Commit `00ab0c4` jest punktem bazowym badanego prototypu. Nie oznacza, że 73 ustalenia zostały naprawione; oznacza, że ich przedmiot ma stabilny identyfikator w historii.

Do commitu wolno włączać tylko potwierdzone ścieżki V3 oraz związane z V3 reguły ignorowania danych. Istniejące zmiany w `agent-v2` są poza zakresem.

## Następny krok

Po zamknięciu dokumentacji pierwszą zmianą funkcjonalną powinna być izolacja V3: globalna blokada wszystkich możliwości zapisu zewnętrznego i hermetyczny transport fixture/offline. Docelowa wersja pozostaje w pełni autonomiczna; decyzje publikacyjne podejmuje kod na podstawie dowodliwych bramek, a stany niepewne przechodzą do automatycznej kwarantanny zamiast do publikacji.
