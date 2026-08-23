# E-001 — fundament izolacji prototypu Agent V3

## Streszczenie

Eksperyment sprawdzał, czy prototyp V3 można konstrukcyjnie odciąć od produkcyjnego V2, sekretów, sesji, sieci i mutacji, zachowując możliwość późniejszych testów na odseparowanym koncie. Wprowadzono centralny rejestr możliwości, rozłączne tryby wykonania, namespacowane sekrety i lokalny podgląd bez przeglądarki. Test celu przeszedł 14/14 przypadków, a pełna bezpieczna regresja 35/35 plików. Nie wykonano połączenia sieciowego ani testu live. Koszt wyniósł 0 USD.

## 1. Pytania badawcze

1. Czy dowolne wejście mutujące V3 może ominąć główne CLI?
2. Czy fixture może odczytać sekret odziedziczony z procesu lub pliku?
3. Czy wyslij=False może otworzyć zalogowaną przeglądarkę albo utworzyć draft?
4. Czy aktywne artefakty V3 mogą uruchomić V2 albo wdrożenie?
5. Czy zmiana zachowuje dotychczasowe kontrakty modułów V3?

## 2. Hipotezy

- H1: centralna bramka przy granicy transportowej odrzuci każdą niedozwoloną możliwość;
- H2: fixture nie odczyta sekretu nawet po jawnym ustawieniu namespacowanej zmiennej;
- H3: wszystkie wejścia mutujące z wyslij=False zakończą się przed atrapą przeglądarki;
- H4: skrypty i usługi V3 nie będą zawierały aktywnego odwołania do V2 ani flagi publikacji;
- H5: bezpieczna regresja zakończy się bez niezaliczonych plików testowych.

## 3. Zmienne i operacjonalizacja

### Zmienne niezależne

- tryb: fixture, model_test, live_read_only, live_test;
- stan kill switcha;
- handle celu: brak, konto testowe, konto produkcyjne, konto niezgodne;
- obecność znacznika prototypu;
- obecność dokładnego tokenu live_test;
- parametr wyslij.

### Zmienne zależne

- zgoda lub CapabilityDenied;
- liczba uruchomień atrapy przeglądarki;
- widoczność sentinela sekretu w podprocesie;
- kod wyjścia CLI i wdroz.sh;
- zmiana drzewa agent-v3/data;
- wynik każdego pliku regresji.

## 4. Metoda

Test celu używa standardowej biblioteki unittest. Granice sesji i przeglądarki zastąpiono funkcją rzucającą AssertionError. Konfigurację sekretów badano w nowych procesach Pythona z kontrolowanym środowiskiem. Artefakty wdrożeniowe badano statycznie i przez bezpieczne uruchomienie skryptu odmowy. Regresję wykonano interpreterem z projektowego .venv.

Z regresji wyłączono:

- test_pobieranie.py — jawnie sieciowy;
- test_czas.py — wymaga semantyki sygnałów Linuxa;
- tests/platne — prawdziwe wywołania modeli.

Wyłączenia ustalono przed testem, nie po obserwacji wyników.

## 5. Wyniki

| Miara | Wynik |
|---|---:|
| Test celu po rozszerzeniu | 14/14 PASS |
| Mutujące wejścia z lokalnym podglądem | 10/10 bez przeglądarki |
| Klasy możliwości w fixture | 14/14 odrzucone |
| Klasy mutacji w produkcyjnym celu | 9/9 odrzucone |
| Pliki bezpiecznej regresji | 35/35 PASS |
| Test CLI --wyslij | odmowa, kod 1 |
| Zmiana agent-v3/data po odmowie CLI | brak |
| Test wdroz.sh | odmowa, kod 64 |
| Aktywne odwołania wykonawcze V3 do V2 | 0 |
| Wywołania sieciowe | 0 |
| Koszt modeli | 0.00 USD |

## 6. Nieudane próby i ich wartość

Pierwszy test celu zakończył się wynikiem 12 PASS i 1 ERROR: komunikat lokalnego podglądu nie mieścił się w CP1252. Po pierwszej korekcie błąd powtórzył się, ponieważ nazwa działania nadal zawierała znak spoza kodowania. Dopiero kanonizacja etykiety do ASCII dała 13/13 PASS. To dowodzi, że test odróżniał implementacje i wykrył realną wadę ścieżki Windows.

Pierwsza szeroka regresja uruchomiona systemowym Pythonem dała 28/35 plików, między innymi przez brak zależności obecnych w projektowym .venv. Ponowienie we właściwym środowisku dało 29/35. Pozostałe błędy ujawniły dryf fixture'ów promptów, typ wyjątku bazy, martwe pole odpowiedzi redaktora i zbyt dokładne sprawdzenie tekstu wywołania. Po naprawie kontraktów wynik wyniósł 35/35.

Test restacku początkowo badał przypadkiem weryfikację konta i potwierdzenie sieciowe zamiast zegara pętli. Po odizolowaniu tych granic atrapa zbadała deklarowaną własność i uzyskała 14/14.

## 7. Zagrożenia trafności

- Testy dowodzą odmowy i lokalnego zachowania, ale nie zgodności selektorów z bieżącym interfejsem Substacka.
- Dodatnia ścieżka live_test nie została wykonana.
- Pełna regresja nie jest pełnym przejściem potoku na replay LLM i browser fixture.
- Statyczny skan nie zastępuje analizy przepływu informacji; dlatego jest łączony z testami dynamicznymi.
- Konto produkcyjne jest blokowane stałą w kodzie. Zmiana tożsamości produkcji wymaga aktualizacji kontraktu i testu.

## 8. Wniosek

H1–H4 utrzymano dla badanego korpusu. H5 utrzymano dla bezpiecznej regresji 35 plików. Nie ma podstaw do twierdzenia, że cały potok redakcyjny działa hermetycznie od scouta do publikacji; potrzebny jest osobny adapter fixture/replay. Nie ma też podstaw do testu na koncie produkcyjnym. Następna logiczna karta to N-004 pełny potok fixture albo N-005 ledger prób, zanim rozpocznie się dodatnia mutacja live_test.

## 9. Errata klasyfikacji testu

W E-001 `test_pobieranie.py` sklasyfikowano jako sieciowy. Inspekcja podczas E-002 wykazała, że transport przeglądarki jest w tym pliku całkowicie zastąpiony atrapami. Historyczny wynik 35/35 pozostaje prawdziwym wynikiem ówczesnego wybranego zbioru, ale powód wyłączenia tego pliku był nieaktualny. W E-002 test przywrócono do korpusu offline, który uzyskał 37/37.
