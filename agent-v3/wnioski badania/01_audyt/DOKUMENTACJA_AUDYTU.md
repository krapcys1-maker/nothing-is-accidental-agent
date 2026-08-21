# Dokumentacja audytu Agent V3 — indeks

**Stan:** audyt statyczny, bez wdrożenia i bez zmian funkcjonalnych w fazie audytu  
**Data:** 2026-08-21

Centralny indeks całego programu badawczego znajduje się w [`../00_INDEKS_DOKUMENTACJI.md`](../00_INDEKS_DOKUMENTACJI.md). Ten plik indeksuje wyłącznie korpus audytu bazowego.

## Zalecana kolejność czytania

1. `MONOGRAFIA_AUDYTOWA_V3.md` — syntetyczny opis problemu, metoda, architektura, odpowiedzi na pytania badawcze i protokół przyszłych eksperymentów.
2. `SPOSTRZEZENIA_AUDYTOWE.md` — żywy rejestr 73 szczegółowych ustaleń P0/P1/P2.
3. `ANEKS_TECHNICZNY_AUDYTU_V3.md` — materiał replikacyjny: odciski plików, słownik dziesięciu tabel, magazyny stanu, kontrakty etapów, testy i macierz epistemiczna.

## Co oznacza obecny wynik

V3 ma wartościowy istniejący rdzeń i nie powinien być projektowany od zera. Nie jest jednak jeszcze bezpiecznym autonomicznym systemem redakcyjnym. Najpierw trzeba uczynić sprawdzalnymi granice, które już istnieją:

- prototyp kontra produkcja;
- intencja kontra potwierdzony skutek;
- źródło kontra twierdzenie i zdanie;
- szkic kontra tekst dopuszczony do publikacji;
- wynik treści kontra obserwacja redakcyjna;
- brak danych kontra awaria kontraktu.

## Najważniejsze ustalenia P0

- artefakty operacyjne w V3 nadal wskazują produkcyjny V2 i `--wyslij`;
- V3 może odczytywać wspólny `.env` i żywą sesję;
- marker prototypu i kill switch nie obejmują każdej mutacji;
- budżet dnia zmienia się między przebiegami i nie odejmuje follow/subskrypcji;
- awaria dziennika może bezgłośnie wyłączyć ograniczenia wolumenu;
- dzień publikacyjny i dzień limitów używają różnych stref czasowych;
- URL modelu nie ma ochrony DNS/IP/redirect przed zasobami prywatnymi;
- klasyfikacja inferencji może ukryć faktograficzną przesłankę;
- `wyslij=False` nadal może utworzyć lub zmienić zdalny draft;
- potwierdzenie artykułu używa podobieństwa tytułu, nie ID bieżącej próby.

Pełne mechanizmy i dowody znajdują się pod identyfikatorami A-001–A-073.

## Czego audyt nie robił

- nie uruchamiał V3;
- nie importował modułów agenta;
- nie wywoływał modeli ani sieci;
- nie otwierał przeglądarki i sesji;
- nie uruchamiał testów mogących zapisywać stan;
- nie wykonywał skryptów wdrożenia ani usług;
- nie modyfikował V2;
- nie usuwał zastanych plików;
- nie publikował niczego.

## Kontrole wykonane

- inwentaryzacja 117 plików;
- analiza AST 59 plików Python: zero błędów składni;
- odtworzenie przepływu artykułu, rutyny dnia i zależności modułów;
- inspekcja dziesięciu tabel oraz magazynów JSON/JSONL/Markdown/cache;
- analiza promptów i pól kontraktów modeli;
- replikacja znanych defektów V2 na kodzie V3;
- kontrola 73 identyfikatorów: ciągłe, bez duplikatów;
- kontrola SHA-256 dwunastu modułów: zgodne z aneksem;
- kontrola katalogu danych: tylko `.gitkeep` i zastany pusty `zasiew-produkcji.db`.

## Ważna informacja o stanie prototypu

Przed zawężeniem zadania do samego audytu w V3 powstały częściowe zmiany prototypowe. Nie zostały zatwierdzone ani zweryfikowane i nie są w tej dokumentacji przedstawiane jako gotowa naprawa. Odciski w aneksie identyfikują dokładnie kod, który został zbadany.

## Następna faza — zatwierdzony kierunek

Pierwsza faza implementacyjna ogranicza się do izolacji i hermetycznego trybu fixture/offline. Nie dodaje nowych publikacji ani analytics. Docelowym wymaganiem jest pełna autonomia: automatyczna decyzja, rewizja, kwarantanna, publikacja, pomiar i uczenie bez osobnej bramki akceptacyjnej. Sekwencja znajduje się w `../05_plan_napraw/REJESTR_BLEDOW_I_PLAN_NAPRAW.md`.
