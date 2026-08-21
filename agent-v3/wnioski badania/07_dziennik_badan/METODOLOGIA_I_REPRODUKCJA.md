# Metodologia badania i protokół reprodukcji

**Wersja:** 1.0  
**Data:** 2026-08-21  
**Przedmiot:** Agent V3  
**Typ badania:** audyt statyczny, rekonstrukcja architektury, analiza porównawcza kodu źródłowego i projekt przyszłych eksperymentów

## 1. Pytanie badawcze

Główne pytanie brzmi: jakie minimalne, ewolucyjne zmiany przekształcą istniejący Agent V3 z generatora i automatu dystrybucyjnego w wiarygodny system redakcyjny, bez przepisywania go od zera i bez ryzyka naruszenia produkcji?

Pytania pomocnicze:

1. Które mechanizmy V2/V3 są rzeczywiście wykonywane, a które istnieją tylko w dokumentacji, promptach lub szkielecie bazy?
2. Gdzie agent myli zamiar albo próbę z potwierdzonym skutkiem?
3. Czy granica prototyp–produkcja jest pełna i możliwa do udowodnienia?
4. Czy materiał źródłowy zachowuje pochodzenie aż do zdania finalnego?
5. Czy rewizja zmienia tekst na podstawie jawnych uwag i czy można dowieść braku regresji?
6. Czy wyniki publikacji mogą być mierzone porównywalnie bez optymalizacji pod jeden wskaźnik zaangażowania?
7. Jakie wzorce z publicznych projektów są przenośne do V3, a jakie wymagają osobnego eksperymentu?

## 2. Korpus

Korpus podstawowy obejmuje katalog `agent-v3` w stanie utrwalonym 2026-08-21. Katalog `agent-v2` jest korpusem porównawczym tylko do odczytu. Publiczne repozytoria są źródłami porównawczymi, a nie bibliotekami automatycznie włączanymi do V3.

Pierwotna migawka audytu obejmowała 117 plików V3. Późniejsza konsolidacja dokumentacji zwiększa liczbę plików, ale nie zmienia odcisków dwunastu głównych modułów zapisanych w aneksie. Każda przyszła zmiana kodu ma otrzymać osobny wpis przed/po.

## 3. Metody

### 3.1. Inwentaryzacja

- lista plików i ich role;
- liczba modułów, testów, promptów i linii;
- identyfikacja danych trwałych oraz plików mogących zawierać stan żywy;
- odciski SHA-256 głównych modułów.

### 3.2. Analiza statyczna

- parsowanie AST wszystkich plików Python bez importowania modułów;
- śledzenie przepływu od punktów wejścia do operacji sieciowych i zapisu;
- porównanie parametrów konfiguracji z rzeczywistymi konsumentami;
- inspekcja szerokich wyjątków, stanów częściowych i zachowań fail-open;
- analiza kontraktów JSON i promptów modelowych.

### 3.3. Rekonstrukcja stanów

Dla ścieżki artykułu, rutyny dnia, budżetu, źródeł, cache, rewizji i metryk odtworzono:

`wejście -> stan przed -> operacja -> dowód powodzenia -> zapis -> stan po -> ścieżka awarii`

Jeżeli kod zapisuje sukces bez dowodu powodzenia, ustalenie traktuje się jako defekt niezawodności.

### 3.4. Analiza porównawcza

Publiczne repozytoria zbadano na poziomie README i wybranych plików implementacji. Dla każdego utrwalono pełny hash HEAD, datę commitu, liczbę śledzonych plików i liczbę plików testowych wykrytych konwencją nazw. Nie wykonywano kodu obcego ani nie instalowano jego zależności.

Analiza nie przyznaje ocen punktowych. Repozytoria rozwiązują różne problemy, więc liczby typu „autonomia 9/10” byłyby pozorną precyzją bez wspólnego zadania, datasetu i procedury oceny.

### 3.5. Testowanie przyszłych napraw

Hierarchia dowodu, od najtańszego:

1. kontrola statyczna;
2. test jednostkowy z fixture;
3. test właściwości lub kontrdowodu;
4. test integracyjny z fałszywym transportem i tymczasową bazą;
5. test porównawczy modeli na zamrożonym korpusie;
6. test sieciowy tylko do odczytu;
7. test na środowisku zewnętrznym bez możliwości mutacji.

Poziom 7 nie jest obecnie dostępny dla Substack, ponieważ użycie żywej sesji i część trybów „dry run” nadal może zmieniać zdalny draft.

## 4. Kryterium uznania ustalenia

Ustalenie trafia do rejestru, jeżeli spełnia co najmniej jeden warunek:

- istnieje konkretna ścieżka wykonania prowadząca do błędnego stanu;
- dokumentacja deklaruje zachowanie sprzeczne z kodem;
- kontrola bezpieczeństwa nie obejmuje wszystkich możliwości mutacji;
- wynik, koszt albo działanie może być zapisane bez identyfikowalnego dowodu;
- test nie odróżnia implementacji poprawnej od wadliwej;
- stan może pozostać częściowy bez jawnej procedury rekoncyliacji.

Priorytet:

- **P0** — możliwa nieautoryzowana mutacja, publikacja, fałszywy zapis sukcesu, obejście limitu lub istotna utrata bezpieczeństwa;
- **P1** — wada wiarygodności redakcyjnej, danych, pomiaru, kosztów albo testowalności;
- **P2** — dług techniczny lub dokumentacyjny zwiększający ryzyko przyszłej pomyłki.

## 5. Kontrola stronniczości

- Materiał historyczny V2 nie jest traktowany jako dowód aktualnego działania V3.
- Deklaracje w README projektów zewnętrznych sprawdza się w kodzie, jeśli wniosek ma wpływać na plan V3.
- Liczba gwiazdek, commitów i szerokość listy funkcji nie są miarą jakości redakcyjnej.
- Brak publicznego repozytorium nie dowodzi braku rozwiązania prywatnego lub komercyjnego.
- Brak błędu składni nie dowodzi poprawności semantycznej.
- Przejście testów jednostkowych nie dowodzi bezpieczeństwa żywej integracji.
- Opinie o jakości tekstu muszą mieć zamrożony korpus, rubrykę i ślepą lub co najmniej losową kolejność próbek.

## 6. Replikacja audytu lokalnego

Bezpieczna replikacja nie importuje V3 i nie dotyka `data/`:

1. zanotuj `git status --short --branch`;
2. policz pliki za pomocą `rg --files agent-v3`;
3. sparsuj źródła Python przez `ast.parse` jako tekst;
4. wylicz SHA-256 głównych modułów;
5. sprawdź ciągłość identyfikatorów A-001–A-073;
6. sprawdź, czy żaden test wybrany do uruchomienia nie importuje modułu uruchamiającego przeglądarkę, sieć lub bazę w stałej ścieżce;
7. użyj tymczasowego katalogu danych i jawnie wyłączonych transportów.

Dokładne odciski i liczby bazowe znajdują się w `../01_audyt/ANEKS_TECHNICZNY_AUDYTU_V3.md`.

## 7. Replikacja kwerendy zewnętrznej

Repozytoria pobrano jako płytkie kopie `--depth 1 --filter=blob:none` do katalogu tymczasowego. Dla każdego wykonano wyłącznie odczyt:

- `git log -1 --format='%H|%cI|%s'`;
- `git ls-files`;
- wyszukiwanie `rg` w README, kodzie bezpieczeństwa, analityki, testów i publikacji;
- odczyt wybranych implementacji.

Nie uruchamiano `npm install`, `pip install`, testów, serwerów, przeglądarek ani skryptów badanych repozytoriów.

## 8. Ograniczenia

Audyt statyczny może znaleźć ścieżkę błędu, lecz nie estymuje jej częstości w produkcji. Analiza publicznych repozytoriów jest migawką z jednego dnia. Substack używa nieoficjalnych endpointów, więc zachowanie może zmienić się bez wersjonowanego kontraktu. Jakość redakcyjna V3 nie została jeszcze zmierzona na ślepym korpusie; nie wolno jej wywnioskować z liczby promptów, etapów ani asercji.

## 9. Kryterium zakończenia projektu

Agent będzie można nazywać działającym redakcyjnie dopiero wtedy, gdy:

- każda możliwość zewnętrzna ma jawny typ, politykę i nieomijalną blokadę;
- potok offline odtwarza pełny przebieg bez sieci i bez sekretów;
- sukces działań jest powiązany z konkretną próbą i potwierdzeniem u źródła;
- tekst zachowuje pochodzenie twierdzeń oraz historię rewizji;
- wyniki są mierzone w stałych horyzontach i względem właściwej kohorty;
- reguły uczone z wyników wymagają wielu obserwacji, automatycznej walidacji, ograniczonego rollout'u i automatycznego rollbacku;
- testy dowodzą własności, a nie tylko wybranych przykładów;
- test bezpieczeństwa wykazuje brak mutacji zewnętrznych w trybie prototypowym.
