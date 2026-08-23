# E-009 — atomowa rezerwacja kosztu modelu

## Abstrakt

Eksperyment sprawdził A-095/N-020: czy limit kosztu i zapis ekspozycji modelu
mogą zostać wykonane jako jedna operacja SQLite odporna na dwa równoległe
procesy. Kontrdowód starego interfejsu zapisał dwie rezerwacje po 0,25 USD przy
limicie 0,25 USD, osiągając 0,50 USD ekspozycji. Po zmianie dokładnie jedna z
dwóch konkurujących rezerwacji przechodzi, test celu ma wynik 7/7 PASS, testy
sąsiednie przechodzą, a pełna regresja obejmuje 46/46 plików. Hashe całego
`data/` nie zmieniły się. Nie użyto sieci, modeli, przeglądarki, sesji ani
Substacka; koszt wyniósł 0 USD.

## 1. Pytanie i hipotezy

Pytanie: czy suma kosztu `KNOWN` oraz ekspozycji `RESERVED/UNKNOWN` może zawsze
pozostać w limitach run/day/month, także gdy dwa niezależne połączenia próbują
zarezerwować koszt jednocześnie?

- **H1:** `BEGIN IMMEDIATE` obejmujące odczyt ekspozycji i `INSERT RESERVED`
  serializuje konkurujące zapisy.
- **H2:** limit doby i miesiąca działa między różnymi `run_id`, a limit run
  działa wewnątrz jednego przebiegu.
- **H3:** `UNKNOWN` lub `RESERVED` tego samego dostawcy blokuje nową rezerwację
  w tej samej transakcji.
- **H4:** wyjątek przy `INSERT` wykonuje rollback i nie zostawia martwego
  `RESERVED`.
- **H5:** etap o cenie stałej przechodzi tylko wtedy, gdy cała dokładna cena
  mieści się w wolnym saldzie; rezerwacja tekstu nigdy nie zaokrągla w górę.

## 2. Środowisko i granice

- Windows, projektowa `.venv`, `PYTHONIOENCODING=utf-8`;
- prawdziwe SQLite w katalogach tymczasowych, osobne połączenie na wątek;
- dwa wątki startujące z bariery dla kontrdowodu współbieżności;
- pełna regresja uruchamiana z korzenia repozytorium, jeden plik na proces;
- wyłączone: `test_czas.py` oraz `tests/platne/`;
- brak transportu HTTP, kluczy API, modelu, Substacka i trwałych mutacji danych.

## 3. Stan przed i kontrdowód

Odciski zapisane przed zmianą:

| Plik | SHA-256 przed |
|---|---|
| `llm.py` | `893E138B13D1D8A7BBDC9EC3F438BD34E747950EF23B38D7C4356D66C12FF407` |
| `db.py` | `4F56D9003E71500FB6E6C04D0DE9AF96F78AEFC8F57B88EBCACEF2DC7DE65173` |
| `operational_day.py` | `D597D5C18C18E72297C5CAE623BDEBAB07427F119F67A94BDE6C123C013C665A` |
| `tests/test_model_call_accounting.py` | `C23966F32176263FF1FE1495F1CE5C77A517DCC41E0EC5511823EE614B38C0E7` |
| `tests/test_zapis_wywolania.py` | `969ACAA40717462684B63201E404B875912C1285E0F9409B089EAAB6BCA822A9` |

T-092 powtórzył mechanizm T-079 przeciw rozdzielonemu sprawdzeniu i
`reserve_call()`. Dwa połączenia odczytały to samo saldo. Wynik
`successes=[1, 2]`, brak wyjątków i ekspozycja 0,50 USD obaliły własność przy
limicie 0,25 USD. To oczekiwany FAIL starej implementacji, a nie awaria
uprzęży.

## 4. Minimalna zmiana

1. `db.reserve_model_budget()` otwiera `BEGIN IMMEDIATE`, a następnie w jednej
   transakcji sprawdza nierozliczony koszt dostawcy, ekspozycję run/day/month,
   oblicza najniższe wolne saldo i wstawia `RESERVED` albo odmawia.
2. `llm._preflight()` zachowuje statyczne kontrole kluczy, cennika i kontraktu
   tokenów. Kontrole finansowe usunięto z preflightu, aby nie tworzyły pozoru
   atomowości przed właściwą transakcją.
3. `llm._reserve_model_call()` wyznacza granice doby redakcyjnej i miesiąca,
   przekazuje trzy limity do DB i tłumaczy odmowę na `BudgetExceeded`.
4. `call()` i `obraz()` używają wyłącznie nowej operacji. Stare
   `db.reserve_call()` pozostaje niskopoziomowym interfejsem testów i
   rekoncyliacji; runtime go nie wywołuje.
5. Cena obrazu jest rezerwowana dokładnie. Dla tekstu kwota jest ograniczana
   do obliczonego salda i nie jest zaokrąglana ponad nie.
6. Każdy wyjątek w transakcji wykonuje rollback. Funkcja odmawia pracy na
   połączeniu z cudzą aktywną transakcją, aby nie zatwierdzić jej efektów.

## 5. Wyniki

| Test | Wynik | Dowód |
|---|---|---|
| T-092 | FAIL zgodnie z hipotezą starej wady | dwie rezerwacje; 0,50 USD przy limicie 0,25 USD |
| T-093 | 7/7 PASS | run/day/month, provider UNKNOWN, rollback, cena stała, brak starej ścieżki runtime |
| T-094 | ERROR nieważnej komendy, potem PASS | start z `agent-v3` nie znalazł `config`; poprawny protokół z korzenia repo dał 7/7 i 16/16 |
| T-095 | 14/14 + 2/2 + 11/11 + 4/4 PASS | doba, routing, kontrakty modeli i cennik |
| T-096 | 46/46 plików PASS | pełna regresja offline w 40,277 s; `data/` bez zmiany hashy |

T-094 zachowuje błąd katalogu roboczego jako wynik metodologiczny. Nie jest to
regresja produktu: historyczne testy importują moduły przy założeniu startu z
korzenia repozytorium, co jest częścią protokołu replikacji.

Odciski po implementacji:

| Plik | SHA-256 po |
|---|---|
| `db.py` | `6994BDEBAB4D91B09F98F9C25ACD2E3D0426604E9AD81A4462454F9813D49D5E` |
| `llm.py` | `D785386C9BE4159AC8CA613B77809DE9E4D72925F353D04EBE51DA71010E9206` |
| `tests/test_atomic_model_budget.py` | `B5419F3CB54DC6EEA4B09D03B54824EFAAA7E15B8E78D50CC2388C4B47206D0C` |
| `tests/test_model_call_accounting.py` | `65C960A39568F414F22C94D2EA3F472CBF9400C1A65B4E78614D6DF3065BDCCB` |
| `tests/test_zapis_wywolania.py` | `969ACAA40717462684B63201E404B875912C1285E0F9409B089EAAB6BCA822A9` |

## 6. Ograniczenia i kryterium obalenia

Eksperyment dowodzi serializacji na lokalnym SQLite i ścieżki runtime na
poziomie kodu oraz fixture. Nie dowodzi zachowania na sieciowym systemie
plików, odporności na awarię systemu operacyjnego w każdej instrukcji SQLite
ani zgodności naliczenia z prawdziwą fakturą dostawcy. Ta ostatnia własność
wymaga kontrolowanego live replayu N-004 i rekoncyliacji.

Wynik obali dowolny kontrprzykład, w którym równoległe procesy przekroczą limit,
nowa rezerwacja przejdzie przy koszcie `UNKNOWN/RESERVED` dostawcy, wyjątek
zostawi martwy rekord, cena stała zostanie częściowo zarezerwowana albo runtime
wróci do rozdzielonego check-and-insert.

## 7. Wniosek

A-095/N-020 otrzymuje status `FIXED_OFFLINE; LIVE_REPLAY_OPEN`. Kryterium
atomowości lokalnej zostało spełnione. Następny eksperyment to pełny
hermetyczny replay N-004, po którym wolno wykonać ograniczony test API na
normalnym routingu V3. Test API nie może otworzyć Substacka ani jego sesji.
