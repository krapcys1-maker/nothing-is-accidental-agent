# WEEK_29 — 2026-07-13 → 2026-07-19

- **Co zbudowano:** domknięto Etap 1, fundament evidence E1, offline integration E2-A i controlled real fetch foundation E2-B; E2-C przygotował capability-gated construction, aktywację YAML i immutable host binding jako kandydata do niezależnego review. Szczegóły: `docs/BUILD_LOG.md`.
- **Co działa:** trwały paid-provider lifecycle z exact-once, lokalne evidence i lineage, offline staged Research Card, jednorazowy approval controlled fetch, lifecycle attemptu i nowa bariera adresu bez DNS TOCTOU. Bieżący checkpoint E2-C: `1572/1572`, exact-once `378+389+394+411`, harness `13/13+13/13`.
- **Co nie działa / nie jest gotowe:** controlled-live Fetch pozostaje `NOT READY`; produkcja jest na `0014`, runtime kodu wymaga `0018`; brak formalnego review E2-C, migracji produkcji i zgody na pierwszy realny Fetch. Otwarte P2 są w `docs/ERRORS_AND_FAILURES.md`.
- **Największy błąd tygodnia:** utożsamienie wcześniejszej walidacji hostname z adresem rzeczywistego połączenia. Wniosek: wynik policy musi być wejściem transportu, nie tylko wcześniejszą obserwacją.
- **Najważniejsza decyzja:** ADR-106 — globalny gate może udostępniać zdolność, lecz dokładny request autoryzuje wyłącznie trwały L1; transport powstaje z capability po konsumpcji, a cel jest przypiętym IP.
- **Koszty:** nowa praca E2-C `0.000000 USD`; rzeczywisty ledger tygodnia/miesiąca po osobno autoryzowanych wcześniejszych requestach: `1.012590 USD`. Koszt/artykuł i koszt/subskrybent: brak danych publikacyjnych.
- **Czas człowieka:** nieagregowany w metrykę minut; decyzje i interwencje są opisane w `docs/HUMAN_INTERVENTIONS.md`.
- **Liczba interwencji człowieka:** nieagregowana ilościowo; obejmowała osobne autoryzacje/review/stop oraz formalne zamknięcia fal. Brak podstaw do uczciwego rozbicia liczbowego.
- **Wyniki publikacji:** brak nowej publikacji; metryki Substack nie były częścią prac.
- **Najlepsze screenshoty:** `SCREENSHOT REQUIRED` dla E2-C; screenshotu nie wykonano z powodu zakazu browsera i ryzyka ujawnienia lokalnych ścieżek.
- **Czego nauczył się agent:** capability nie zastępuje trwałej zgody, a kontrola DNS nie jest zakończona, dopóki transport nie używa dokładnie sprawdzonego adresu.
- **Co zmienimy w kolejnym tygodniu:** (1) niezależny review E2-C; (2) dopiero po decyzji właściciela osobny plan migracji produkcji `0014→0018`; (3) pierwszy realny Fetch wyłącznie po nowym approval L1 i jawnej globalnej aktywacji — bez łączenia tych decyzji.
