# E-003 — jedna doba redakcyjna i transakcyjny budżet autonomicznych działań

## Abstrakt

Eksperyment badał, czy Agent V3 zachowuje stały wolumen działań po restarcie,
równoległym uruchomieniu, awarii pomocniczego JSONL oraz na granicach UTC i
zmiany czasu. Stan bazowy nie spełniał tej własności: plan był losowany przy
każdym przebiegu, dwie klasy działań nie miały licznika, a trzy klasy zależały
od zapisu fail-open. Wprowadzono wersjonowany `OperationalDay` oraz atomową
rezerwację jednostki budżetu razem z trwałą próbą mutacji. Czternaście testów
kontrdowodu i finalna regresja 38 plików offline nie wykazały naruszenia
projektowanego kontraktu. Wynik ma status `FIXED_OFFLINE`; nie dowodzi
aktualności selektorów ani skuteczności transportu zewnętrznego.

## 1. Pytanie badawcze

Czy dla jednego konta i jednej lokalnej doby redakcyjnej istnieje dokładnie
jeden niezmienny plan, którego żadna awaria procesu, współbieżność, stan
`UNKNOWN`, awaria JSONL ani północ UTC nie może zwiększyć?

Pytanie pomocnicze: czy wszystkie autonomiczne mutacje, w tym odpowiedzi,
obserwacje, subskrypcje i ustawienia, mają jawny twardy sufit?

## 2. Ustalenia bazowe

- **A-029:** `stages.budzet_dnia()` ponownie losował widełki przy każdym
  przebiegu.
- **A-030:** follow i subskrypcje były planowane, lecz nie odejmowane od
  wykonania.
- **A-031:** zapis i odczyt JSONL były fail-open, chociaż plik decydował o
  dostępnym wolumenie komentarzy, lajków i restacków.
- **A-032:** okno publikacji używało `America/New_York`, a liczniki, promocja,
  cichy dzień i limity kosztowe używały daty UTC.
- Odpowiedzi miały priorytet semantyczny interpretowany jako brak twardego
  limitu.
- Próba mutacji i jej dzienny limit nie tworzyły jednej transakcji.
- **A-084, wykryte podczas kontroli E-003:** pierwsza implementacja zawarła
  wersję polityki w ID dnia, co przy aktualizacji kodu kolidowało z unikalnością
  konta i daty zamiast zachować plan.

## 3. Hipotezy

**H1. Stałość planu.** Ten sam `(account, editorial_date, policy_version)`
zawsze odczyta ten sam utrwalony plan, także po zmianie konfiguracji w trakcie
dnia.

**H2. Nieprzekraczalność.** Suma jednostek w stanach `RESERVED`, `CONSUMED` i
`QUARANTINED` nigdy nie przekroczy zapisanego limitu kategorii.

**H3. Konserwatywna awaria.** `FAILED` przed dispatch zwolni jednostkę, natomiast
`UNKNOWN` po dispatch zachowa ją i zatrzyma dalsze mutacje.

**H4. Jedna strefa.** Dwie chwile po obu stronach północy UTC, ale należące do
tej samej daty nowojorskiej, otrzymają ten sam dzień; doby zmiany czasu będą
miały odpowiednio 23 i 25 godzin.

**H5. Niezależność od telemetrii.** Uszkodzenie JSONL nie zmieni bilansu SQLite.

Hipotezę obala dowolny kontrprzykład: drugi plan tego samego dnia, dodatkowa
rezerwacja ponad limit, zwolnienie `UNKNOWN`, utrata limitu po restarcie albo
różne identyfikatory jednej doby redakcyjnej.

## 4. Projekt systemu

### 4.1. OperationalDay

Tabela `operational_days` przechowuje:

- stabilne ID wyprowadzone z konta, dnia, strefy i wersji polityki;
- lokalny `day_key` oraz jawne półotwarte granice UTC `[starts_at, ends_at)`;
- `policy_version` i hash konfiguracji;
- zamrożony stan rozbiegu oraz cichego dnia;
- pełny JSON limitów.

Plan powstaje w `BEGIN IMMEDIATE` i po pierwszym zapisie nie jest przeliczany.
Losowość widełek jest deterministyczna. Miesięczne widełki follow i
subskrypcji najpierw wyznaczają jedno N dla miesiąca, a następnie wybierają
dokładnie N deterministycznie uporządkowanych dni.

Tożsamość dnia nie zawiera wersji polityki. Wersja i hash opisują zamrożoną
treść wiersza, ale aktualizacja kodu w środku doby nie może utworzyć drugiej
tożsamości tego samego `(account, day_key)`.

### 4.2. Kategorie działań

| Rodzaj próby | Kategoria budżetu |
|---|---|
| `article` | `artykuly` |
| `note` | `notki` |
| `comment`, `discussion_reply` | `komentarze` |
| `reply`, `article_reply` | `odpowiedzi` |
| `like` | `lajki` |
| `restack` | `restacki` |
| `obserwacja` | `follow` |
| `subskrypcja` | `subskrypcje` |
| `settings` | `ustawienia` |

Rozdzielenie `discussion_reply` od `reply` jest wynikiem badania, nie zmianą
nazwy dla estetyki. Pierwsze oznacza aktywność pod cudzą treścią i zużywa pulę
komentarzy. Drugie jest odpowiedzią pod własną treścią i zużywa priorytetową,
lecz nadal ograniczoną pulę odpowiedzi.

### 4.3. Atomowa rezerwacja

`mutation_ledger.reserve()` wykonuje w jednej transakcji:

1. kontrolę duplikatu i globalnej kwarantanny;
2. odczyt lub utworzenie dnia;
3. kontrolę i zapis jednostki `RESERVED`;
4. zapis `mutation_attempts.PENDING`;
5. commit przed dispatch.

Przejścia końcowe próby i budżetu także należą do jednej transakcji:

| Próba | Rezerwacja | Znaczenie |
|---|---|---|
| `PENDING` | `RESERVED` | jednostka zajęta przed skutkiem |
| `FAILED` | `RELEASED` | brak dispatch; jednostka wraca |
| `UNKNOWN` | `QUARANTINED` | skutek niepewny; jednostka pozostaje zajęta |
| `CONFIRMED` | `CONSUMED` | skutek potwierdzony; jednostka zużyta |

### 4.4. Jedna strefa czasu

`EDITORIAL_TIMEZONE` jest jawnie równa `America/New_York`. Ten kontrakt obejmuje
plan działania, liczenie ukończonych przebiegów, cichy dzień, promocję artykułu,
telemetrię dzienną oraz dobowe i miesięczne limity kosztów. W bazie nadal
zapisywane są znaczniki UTC; strefa określa wyłącznie właściwe granice zapytań.

## 5. Metoda

Warstwa eksperymentalna używała wyłącznie tymczasowych baz SQLite, atrap i
lokalnych plików. Nie uruchomiono przeglądarki, sieci, modeli ani skryptów
wdrożenia. Zmienną niezależną były chwile względem północy/DST, stan próby,
awaria pliku oraz konkurujące połączenia. Zmiennymi zależnymi były ID dnia,
zapisany plan, suma księgowana, stan rezerwacji i wynik odmowy.

Test współbieżności uruchomił dwa wątki z osobnymi połączeniami i jednoczesną
próbą zajęcia jedynej jednostki `ustawienia`. Oczekiwany rozkład wyników wynosił
dokładnie jeden `reserved` i jeden `exhausted`.

## 6. Przebieg prób

### Próba 1 — testy nowego kontraktu

Pierwsza wersja zestawu N-006 wraz z dotychczasowym ledgerem i izolacją dała
42/42 PASS. Obejmowała północ lokalną, DST, zamrożenie planu, miesięczne
alokacje, limit, `FAILED`, `UNKNOWN`, restart, współbieżność i awarię JSONL.

Po pierwszej pełnej zielonej regresji przegląd inwariantów wykrył A-084. Test
zamrożenia rozszerzono o zmianę `POLICY_VERSION`; przed poprawką scenariusz
prowadziłby do konfliktu unikalności, po poprawce zwraca ten sam plan.

### Próba 2 — regresja testów historycznych

Starsze testy ujawniły własne założenia sprzed eksperymentu:

- ciche dni: 8 PASS, 1 FAIL, bo test szukał wywołania funkcji zamiast
  utrwalonego `quiet_day`;
- promocja: 12/12 PASS;
- licznik dnia: 25 PASS, 10 FAIL, bo symulacja nadal zapisywała JSONL i tworzyła
  przebiegi według daty UTC.

Nie interpretowano tego jako awarii implementacji. Testy przepisano na nowy,
jawny kontrakt: lokalne godziny ze strefą, granice OperationalDay i snapshot
ledgeru. Powtórzenie dało odpowiednio 13/13, 12/12 i 35/35 PASS.

### Próba 3 — szeroka regresja

Pierwszy szeroki przebieg: 37/38 plików PASS. `test_obserwacje.py` miał 32 PASS
i 2 FAIL, ponieważ statycznie szukał `budzet["follow"]`, podczas gdy nowa ścieżka
korzysta z przydziału bieżącego przebiegu `na_teraz`. Po skorygowaniu testu do
rzeczywistego interfejsu wynik wyniósł 34/34.

### Próba 4 — rozszerzenie granic kosztowych

Kontrola A-032 wykazała, że również limit kosztowy i alarm nadaktywności używały
UTC. Dodano zapytanie przedziałowe i granice miesiąca w strefie redakcyjnej.
Rozszerzony zestaw `test_operational_day.py` uzyskał 14/14 PASS; regresje
obserwacji, stawek i zapisu wywołań uzyskały 34/34, 45/45 i 16/16 PASS.

### Próba 5 — finalna regresja

Finalny wynik: 38/38 plików PASS. Zestaw wyłącza tylko platformowy
`test_czas.py`; testy płatne znajdują się w osobnym podkatalogu i nie były
uruchamiane.

Po korekcie A-084 wykonano cały zestaw ponownie: test OperationalDay 14/14 i
bezpieczna regresja 38/38 plików PASS (T-034).

## 7. Wyniki względem hipotez

| Hipoteza | Kontrdowód | Wynik offline |
|---|---|---|
| H1 stałość | dwa połączenia i zmiana widełek po utworzeniu planu | nie znaleziono |
| H2 limit | dwie konkurujące rezerwacje limitu 1 | 1 sukces, 1 odmowa |
| H3 awaria | restart przed i po dispatch | `RELEASED` / `QUARANTINED` |
| H4 strefa | północ UTC/lokalna, 23 h i 25 h, granica miesiąca | zgodne |
| H5 JSONL | ścieżka dziennika ustawiona na katalog | bilans SQLite bez zmian |

## 8. Zagrożenia trafności

- SQLite na pojedynczym komputerze nie dowodzi zachowania rozproszonego
  magazynu; V3 obecnie używa SQLite, więc test odpowiada realnej architekturze.
- Test nie symuluje zabicia procesu pomiędzy każdym pojedynczym bajtem zapisu;
  polega na transakcyjności SQLite i osobno bada restart przed/po dispatch.
- Deterministyczna alokacja miesięczna dowodzi liczby dni, nie jakości doboru
  wolumenu dla platformy.
- Brak testu live oznacza, że rodzaje prób i `source_ref` mogą wymagać adaptacji
  po zmianie interfejsu platformy.
- `UNKNOWN` pozostaje globalną kwarantanną bez automatycznej rekoncyliacji
  źródłowej. Jest to bezpieczne ograniczenie, ale może zatrzymać aktywność.

## 9. Ograniczenia i dalsza praca

N-006 nie domyka pełnego replayu scout–publikacja (N-004), bezpiecznego fetchu
(N-007) ani rekoncyliacji `UNKNOWN`. Nie dowodzi też redakcyjnej jakości treści.
Następny logiczny P0 to N-007: blokada prywatnych adresów, redirectów i
nieograniczonego pobierania przed pracą nad schematami oraz głosem.

## 10. Koszt i efekty zewnętrzne

- modele: 0.00 USD;
- sieć: brak;
- przeglądarka: brak;
- mutacje kont zewnętrznych: brak;
- wdrożenie: brak;
- V2: wyłącznie odczyt stanu Git; brak zapisu.

Kontrola dokumentacyjna: 36 plików Markdown, zero brakujących lokalnych linków,
84 ciągłe ID ustaleń bez duplikatów oraz czysty `git diff --check` (ostrzeżenia
CRLF są informacyjne). Katalog `agent-v3/data` pozostał bez zmian.

## 11. Wniosek

A-029–A-032 mają kontrdowody na poziomie offline. Dzienny wolumen nie jest już
wyprowadzany z ponownego losowania ani pomocniczego JSONL. Każda znana mutacja
ma twardą kategorię, a jednostka limitu dzieli los trwałej próby w tej samej
transakcji. Wynik uzasadnia status `FIXED_OFFLINE`, nie status gotowości live.
