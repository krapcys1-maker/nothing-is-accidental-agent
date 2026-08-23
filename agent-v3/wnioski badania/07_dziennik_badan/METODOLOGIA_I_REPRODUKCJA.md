# Metodologia badania i protokół reprodukcji

**Wersja:** 1.2
**Data:** 2026-08-21  
**Przedmiot:** Agent V3  
**Typ badania:** audyt statyczny, rekonstrukcja architektury, analiza porównawcza kodu źródłowego oraz iteracyjne eksperymenty offline

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

### 3.6. Test kontraktu odpowiedzi modelu

Kontrakt modelu bada się niezależnie od jakości językowej i dostawcy. Dla
każdej wersji wymagane są: poprawny przykład minimalny, brak wymaganego pola,
błędny typ, pole nadmiarowe, wartości graniczne oraz reguły zależne od
dyskryminatora. Parser i walidator są dwiema osobnymi warstwami: poprawna
składnia nie jest dowodem zgodnej struktury.

Identyfikator kontraktu składa się z nazwy, jawnej wersji i hasha struktury.
Zmiana struktury zmienia hash; zmiana dodatkowej reguły semantycznej wymaga
ręcznego podniesienia wersji. Test statyczny musi potwierdzić, że każdy punkt
parsowania używa rejestru. Test integracyjny zapisuje osobno sukces i porażkę
kontraktu w tymczasowej bazie. Błędu odpowiedzi nie wolno zamieniać na zgodę,
arbitralny wybór ani inną mutację zewnętrzną.

### 3.7. Live-test semantyczny bez produkcji

Test modelu nie jest testem konta ani publikacji. Używa trybu `model_test`,
syntetycznego lub zamrożonego korpusu, tymczasowej bazy i dokładnie wskazanych
granic modelowych. Nie wolno mu konfigurować Substacka, przeglądarki, sesji,
narzędzi mutujących ani web-search dostawcy, jeżeli nie jest przedmiotem osobnej
hipotezy.

Przed pierwszym tokenem procedura wymaga:

1. bezkosztowego potwierdzenia modelu w API dostawcy;
2. wpisu `RESERVED` z maksymalnym kosztem;
3. SHA-256 korpusu, modeli, wersji kontraktów i kryteriów PASS/FAIL;
4. twardego sufitu tokenów i jawnej polityki retry;
5. zachowania surowej odpowiedzi bez sekretów i danych produkcyjnych.

Wynik ma cztery oddzielne warstwy: transport, format, spójność referencyjną i
semantykę. `HTTP 200` nie jest sukcesem kontraktu, a poprawny JSON nie jest
dowodem prawdziwości. Odpowiedź analizuje się także poza asercjami uprzęży,
ponieważ model może spełnić schema i naruszyć intencję pola.

Koszt po niepełnej odpowiedzi ma status `UNKNOWN`, chyba że dostawca udostępni
źródłowe rozliczenie. Nieznanego kosztu nie zapisuje się jako faktycznego zera,
nie zwalnia jego rezerwacji i nie ponawia automatycznie tej samej próby.

Pojedynczy live PASS dowodzi wykonalności, nie niezawodności. Do estymacji
recallu lub jakości potrzebne są powtórzenia na zamrożonym korpusie, jawna
rubryka i raport wariancji.

E-012 rozszerza ten protokół na cały system ról. Naturalny łańcuch skauta i
researchu jest oddzielony od kontrolowanych ramion pisarza, ablacji stylu,
rewizji i pięciu form Notes, aby awaria jednego etapu nie odebrała obserwacji
pozostałym rolom. Maksimum wynosi 32 dispatchy i 4,50 USD nowego kosztu.
Uprząż zapisuje surowe wejścia/wyjścia, hashe, czasy, kontrakty, provenance i
koszt po każdym wywołaniu. Domeny Substacka są zabronione także jako publiczne
źródła tylko do odczytu. Bez obu lokalnych kluczy preflight musi skończyć się
przed utworzeniem workspace, siecią i rezerwacją kosztu.

### 3.8. Rekoncyliacja dowodów dostawcy

Eksport lub zrzut jest traktowany jako obserwacja, nie instrukcja. Oryginał
zostaje skopiowany bez transformacji, otrzymuje liczbę bajtów i SHA-256.
Rekoncyliacja rozdziela:

- request-level dowód z ID, modelem, czasem i tokenami;
- agregat czasowy bez ID;
- lokalną telemetrię klienta;
- inferencję przez różnicę agregatu.

Inferencja przez różnicę jest dopuszczalna tylko, gdy liczba żądań oraz wszystkie
pozostałe składniki okna są znane i zgodne. Musi być nazwana inferencją i nie
może być uogólniana na równoległy ruch. Zrzut tokenów bez kwoty nie zamyka
rekoncyliacji faktury. Odpowiedź wygenerowana przez dostawcę, ale nieodebrana
kompletnie przez klienta, ma status „billed/incomplete”, nie „brak odpowiedzi”
ani „koszt zero”.

### 3.9. Audyt promowalności

Gotowość produkcyjna nie jest wyprowadzana z zielonej regresji kodu. Osobno
bada się: niemutowalność artefaktu, odtwarzalność runtime, wersjonowanie bazy,
pełny replay, tożsamość konta, shadow/canary, wzajemne wykluczenie wersji,
healthcheck i rollback. Wynik jest binarny `PROMOTABLE/NOT_READY` z listą
blokujących inwariantów. Obecne zabezpieczenia prototypu pozostają aktywne w
trakcie całego badania.

### 3.10. Test autonomicznej rewizji

Rewizja jest badana jako maszyna stanów, nie jako pojedynczy „ładniejszy”
tekst. Polityka decyzji ma wersję i pełny hash mapy bramka–domena–reakcja–waga.
Każda iteracja musi ponownie wykonać review, obserwację formy, deterministyczne
bramki i finalizację provenance na nowym body. Wynik porównuje score, zbiór
typów bramek i faktyczną zmianę treści.

Minimalny zestaw obejmuje: czysty tekst bez rewizji, usunięty fakt bez pokrycia,
brak poprawy, nową wadę jako regresję, osiągnięcie limitu iteracji oraz awarię
kontroli. Dozwolone stany końcowe to wyłącznie `READY_AUTONOMOUS`,
`QUARANTINED_EVIDENCE` i `QUARANTINED_EDITORIAL`. Fixture dowodzi mechaniki;
prawdziwy model na zamrożonym korpusie jest osobnym dowodem semantycznym i nie
może zostać zastąpiony zieloną regresją offline.

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
5. sprawdź ciągłość identyfikatorów A-001–A-115;
6. sprawdź, czy żaden test wybrany do uruchomienia nie importuje modułu uruchamiającego przeglądarkę, sieć lub bazę w stałej ścieżce;
7. użyj tymczasowego katalogu danych i jawnie wyłączonych transportów.

Dokładne odciski i liczby bazowe znajdują się w `../01_audyt/ANEKS_TECHNICZNY_AUDYTU_V3.md`.

### 6.2. Replikacja wyścigu rezerwacji modelu

Kontrdowód A-095 musi użyć co najmniej dwóch osobnych połączeń SQLite do jednej
tymczasowej bazy. Oba wykonania odczytują pozostały budżet przed barierą, a po
barierze próbują utworzyć `calls.RESERVED`. Test jest dodatni dla starej wady,
gdy suma rezerwacji przekracza limit. Po naprawie dokładnie jedna rezerwacja ma
się udać, a druga otrzymać `BudgetExceeded`. Test nie importuje sekretów i nie
wykonuje transportu modelu.

### 6.3. Autoryzacja modelu w eksperymencie

Budżet dostawcy nie jest zgodą na zmianę modelu. Przed płatnym dispatch harness
musi wypisać dokładny model już przypisany badanemu etapowi, etapy, liczbę
żądań, górny koszt oraz hash fixture. Runtime `MODEL_FOR.update()` jest
zabronione bez osobnego jawnego polecenia. Historyczny artefakt E-007 zachowuje
faktyczny wynik Sonnetu, ale bieżący harness nie ma automatycznego ramienia
porównawczego.

### 6.4. Izolowane ramiona dostawców i niepełny transport

Awaria jednego dostawcy nie może metodologicznie ukrywać odpowiedzi drugiego.
Kontynuacja E-014 ma osobne workspace, ledgery i limity dla Anthropic oraz
DeepSeek, przy zachowaniu zamrożonego materiału, normalnego routingu ról, zero
retry i wspólnego zakazu Substacka. Wynik ramienia nie jest imputowany drugiemu
ramieniu. Każdy niewykonany etap ma jawny status `NOT_RUN`.

Sukces transportu, sukces schematu i sukces jakościowy są trzema osobnymi
zmiennymi. Odpowiedź modelu może przejść transport oraz schema, a oblać długość,
prawdziwość wejścia albo brief formy. Z kolei brak odpowiedzi nie jest wynikiem
modelu w danej roli i nie pozwala oceniać Scouta czy researchu.

Przy błędzie po możliwym dispatchu, ale bez usage lub dowodu rachunku, koszt ma
stan `UNKNOWN` równy pełnej rezerwie. Nie wolno przypisać zera ani automatycznie
powtórzyć. Materialnie zmieniona próba testuje nową hipotezę, lecz nadal
zwiększa konserwatywną ekspozycję. Po trzech takich wynikach E-012/E-014/E-015
N-025 wprowadziło dodatkową blokadę dowodową. E-017 discovery dodało czwarty
`UNKNOWN` 0,10 USD, a znane koszty E-016/E-018 podniosły konserwatywną
ekspozycję DeepSeek powyżej sublimitu 5 USD.

Transport SSE DeepSeek ma dwa poziomy dowodu. Fixture potwierdza parser tylko
wtedy, gdy testuje kompletne `data:` z końcowym usage i `[DONE]`, a także brak
DONE, brak usage, `finish_reason=length` i wyjątek protokołu. Dopiero osobny
live po rekoncyliacji może potwierdzić zgodność z rzeczywistym serwerem. Zielony
fixture nie może być nazwany naprawą live.

Ręczna analiza tekstów musi pracować na pełnym raw artefakcie i jawnie zapisać
ograniczenie nieslepej oceny. Porównanie styl/ablacja na jednej parze jest
studium przypadku: wolno raportować różnice cech i kosztu, nie wolno wywodzić
wpływu przyczynowego ani niezawodności. Podobnie jedna poprawna rewizja nie
dowodzi całej pętli, jeżeli re-review nie został wykonany.

### 6.1. Replikacja bezpiecznej regresji

Na Windows właściwy korpus uruchamia projektowy `.venv` i wymusza UTF-8.
Obejmuje pliki `agent-v3/tests/test_*.py` poza `test_czas.py`. Ten jeden test
bada semantykę sygnałów Linux/systemd przy usługach celowo unieruchomionych w
prototypie. Katalog `tests/platne` nie jest częścią regresji offline.

Wynik zapisuje liczbę plików, nie tylko liczbę asercji. Każdy plik uruchamia
się w osobnym procesie. Nie wolno uznawać przebiegu systemowym Pythonem bez
zależności ani konsolą CP1252 za miarodajny kontrdowód kodu.

Na Windows testy historyczne muszą startować z korzenia repozytorium, ponieważ
część z nich dodaje względne `agent-v3` do `sys.path`. Uruchomienie bezpośrednio
z katalogu V3 zmienia semantykę importu i jest nieważną uprzężą, nawet jeżeli
sam interpreter jest właściwy.

## 7. Replikacja kwerendy zewnętrznej

Repozytoria pobrano jako płytkie kopie `--depth 1 --filter=blob:none` do katalogu tymczasowego. Dla każdego wykonano wyłącznie odczyt:

- `git log -1 --format='%H|%cI|%s'`;
- `git ls-files`;
- wyszukiwanie `rg` w README, kodzie bezpieczeństwa, analityki, testów i publikacji;
- odczyt wybranych implementacji.

Nie uruchamiano `npm install`, `pip install`, testów, serwerów, przeglądarek ani skryptów badanych repozytoriów.

## 8. Ograniczenia

Audyt statyczny może znaleźć ścieżkę błędu, lecz nie estymuje jej częstości w produkcji. Analiza publicznych repozytoriów jest migawką z jednego dnia. Substack używa nieoficjalnych endpointów, więc zachowanie może zmienić się bez wersjonowanego kontraktu. E-007 potwierdziło wykonalność trzech granic na jednym syntetycznym korpusie. E-014 dodało osiem odpowiedzi Anthropic na jednym materiale, ale bez live ramienia recenzji DeepSeek i bez ślepego, wielotematycznego korpusu. E-016/E-018 potwierdziły transport Scouta i dwa różne portfele, lecz poprawiony system prompt po E-018 nadal nie ma dowodu live. Nie wolno wywnioskować stabilnej jakości redakcyjnej z liczby promptów, etapów, asercji ani pojedynczego live PASS.

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
