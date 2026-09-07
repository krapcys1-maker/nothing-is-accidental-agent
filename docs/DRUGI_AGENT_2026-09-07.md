# Drugi agent na tym samym serwerze — co sprawdziłem i jak go postawić

7 września 2026. Pytanie właściciela: czy da się dołożyć drugiego agenta,
piszącego na **inne** konto Substacka, i czy nic nie będzie sobie przeszkadzać.

## Krótka odpowiedź

Tak. Serwer to udźwignie bez zająknięcia, większość stanu rozdziela się sama,
a trzy rzeczy, które się nie rozdzielały, są już poprawione (`653380f`).
Zostaje **jedna decyzja do podjęcia świadomie: budżet.**

## Serwer

| | |
|---|---|
| RAM | 11,7 GB, wolne **9,7 GB** |
| rdzenie | 6 |
| dysk | 89 GB wolnego |
| obciążenie | **0,05** |
| szczyt pamięci przebiegu | 265–475 MB |

Miejsca starczy na wielu takich agentów.

## Co rozdziela się samo

`DATA_DIR = AGENT_DIR / "data"` liczy się od położenia katalogu, więc **druga
kopia repozytorium** dostaje własne: zamek `agent.lock`, bazę, dziennik, bank
kandydatów, sesję przeglądarki, stan serii i `.env`. Zamek siedzi w `DATA_DIR`,
więc agenci **nie będą się blokować** — pobiegną równolegle.

## Co poprawiłem, bo się nie rozdzielało

**1. Uchwyt konta był zapisany dwa razy.** `config.SUBSTACK_HANDLE` służył
adresom publikacji (`uchwyt.substack.com`), a `browser.PROFIL_HANDLE` adresom
profilu (`/@uchwyt/followers`) — obie stałe miały tę samą wartość wpisaną
ręcznie. Zmiana jednej bez drugiej znaczy, że agent **sprawdza jeden profil,
a publikuje na drugim**, i nie mówi o tym ani słowa, bo obie ścieżki działają
poprawnie osobno. To była wada niezależna od drugiego agenta.

**2. Nazwa marki była wpisana w dziewięciu promptach.** Drugi agent pisałby
cudzym nazwiskiem. Idzie teraz jako pole `{marka}`, wstawiane przez `_prompt`
przy każdym wywołaniu.

**3. Sufit miesięczny był stałą.** Druga kopia musiałaby mieć zmieniony **kod**.
Teraz ze środowiska, z bezpiecznym powrotem: literówka albo wartość ujemna
zostawiają wartość domyślną, zamiast wyzerować sufit i uciszyć konto na miesiąc.
Wrześniowa podwyżka do 150 USD też jest ze środowiska — była decyzją o **tym**
koncie, więc drugi agent nie ma jej dziedziczyć.

**Wartości domyślne nietknięte.** Bez zmiennych środowiskowych konto zachowuje
się dokładnie jak dotąd: uchwyt `nothingisaccidental`, marka `Nothing Is
Accidental`, sufit 40, podwyżka 150 do 30 września, 40 od października.

## Jedna rzecz, której to NIE rozwiązuje

**Budżet jest per kopia, nie per karta.** Wydatki liczy `llm._preflight` przez
`db.spent_usd`, czyli z **własnej bazy** danej kopii. Dwaj agenci mają więc
**dwa pełne sufity** i żaden nie widzi wydatków drugiego — rachunek podwaja się
po cichu, bez linii w logu. Ostrzeżenie stoi przy `config.sufit_miesieczny`.

Wspólne liczenie wymagałoby wspólnej bazy i tego nie ma.

## Jak postawić drugiego agenta

1. **Druga kopia repozytorium** w innym katalogu, np.
   `~/drugi-agent`. Własne `.venv`.
2. **Własny `.env`** z kluczami i tymi czterema pozycjami:

       SUBSTACK_HANDLE=uchwytdrugiegokonta
       MARKA=Nazwa Drugiej Publikacji
       MONTHLY_LIMIT_USD=25
       PODWYZKA_MIESIECZNA_USD=0

   Ostatnia linia jest ważna — bez niej drugi agent odziedziczy wrześniową
   podwyżkę do 150 USD do 30 września.
   **Sufity ustaw tak, żeby SUMA miała sens**, bo nie widzą się nawzajem.
3. **Własna sesja Substacka** — zalogowanie zapisuje `storage-state.json`
   w `DATA_DIR` drugiej kopii, więc nie koliduje.
4. **Własna jednostka systemd** z `WorkingDirectory` na nowy katalog
   i **przesuniętym `OnCalendar`**. Dzisiejszy zegar: 11:20, 17:00, 19:20,
   21:30, 23:40 UTC. Rozsunięcie jest darmowe, więc nie ma powodu startować
   obu o tej samej minucie.

## Czego bym NIE robił

**Dwóch agentów na jednym koncie.** Cała ochrona przed powtórkami jest zapięta
na `DATA_DIR`: pamięć wystawionych notek, `gdzie_komentowalismy.json`, bramki
rytmu, zapora wspólnej nazwy własnej. Dwaj agenci nie widzieliby się nawzajem
— napisaliby o tych samych faktach, złamali odstępy między notkami i
skomentowali dwa razy pod tym samym wpisem.

## Pomyłka, którą po drodze zrobiłem i wycofałem

`test_podlogi_z_pamieci` zaczął oblewać na serwerze, a przechodzić lokalnie.
Porównałem go na commicie sprzed moich zmian **w drzewie roboczym `git
worktree`** — przeszedł, więc uznałem winę za swoją. **Drzewo robocze nie ma
katalogu `data`** (dziennik nie jest w gicie), więc przechodzi tam każdy
commit; porównanie mierzyło obecność dziennika, nie wersję kodu.

Prawdziwa przyczyna: `comment_on` sortuje kandydatów po tym, czy powtarzają
otwarcie ostatnich wpisów, a to czyta **żywy dziennik produkcji** (889 wpisów).
Test jest już odcięty przez `uzyj_katalogu_danych`.

**Nauka:** żeby porównać dwie wersje kodu, muszą mieć te same dane. Drzewo
robocze bez `data/` porównuje coś innego, niż się wydaje.
