# 07 — BŁĘDY I NIEUDANE PRÓBY

## Cel pliku
Uczciwy rejestr błędów i nieudanych prób: błędy kodu, API, złe decyzje agenta, słabe teksty/komentarze, problemy z Playwrightem/Substackiem, przekroczenia limitów, koszty, rzeczy do przebudowy. **Bez ukrywania porażek** — to jeden z najcenniejszych materiałów do artykułu.

Każdy wpis: co miało działać · co nie zadziałało · dlaczego · jak naprawiono · ile prób · czego się nauczyliśmy.

## Szablon wpisu
```markdown
### [YYYY-MM-DD] <tytuł> — [TECH|BROWSER|QUALITY|COST|SAFETY|INJECTION|ACCOUNT]
- **Co miało działać:**
- **Co nie zadziałało:**
- **Dlaczego:**
- **Jak naprawiono:**
- **Ile prób:**
- **Czego się nauczyliśmy:**
- **Status:** OPEN | FIXED | WORKAROUND
```

---

### [2026-07-11] Brak ochrony pliku `.env` przed commitem — [SAFETY / R1]
- **Co miało działać:** klucz API w lokalnym `.env` jest OK, ale repo musi gwarantować, że `.env` nigdy nie trafi do commitu.
- **Co nie zadziałało:** repo powstało **bez `.gitignore` i bez `.env.example`** — brakowało mechanizmu chroniącego przed przypadkowym zacommitowaniem. (Problemem nie jest obecność klucza w `.env`, lecz brak ochrony.)
- **Dlaczego:** repo zainicjowane bez higieny.
- **Jak naprawiono:** utworzono `.gitignore` (ignoruje `.env`, `data/`, `config/accounts.yaml`, `config/growth_policy.yaml`, artefakty Pythona) i `.env.example` z placeholderami. Klucza **nie** kopiowano do żadnego dokumentu/logu/screenshotu.
- **Ile prób:** 1.
- **Czego się nauczyliśmy:** higiena repo to pierwszy krok, przed jakimkolwiek kodem. Przy `git init` zweryfikować `git status` (brak `.env` na liście).
- **Status:** FIXED. **Uwaga rezydualna (OTWARTE, R1):** jeśli repo kiedyś stanie się publiczne — przed publikacją zalecana **rotacja klucza** (właściciel świadomie ją odłożył, ADR-010).

### [2026-07-11 19:30] Błędny import w teście pipeline — [TECH]
- **Co miało działać:** test `test_research_pipeline.py` importuje kod walidacji.
- **Co nie zadziałało:** użyto ścieżki `app.workflows.research.validation` zamiast `app.research.validation` → groził `ModuleNotFoundError`.
- **Dlaczego:** walidacja leży w pakiecie `app/research/`, nie `app/workflows/research/`.
- **Jak naprawiono:** poprawiono import; wychwycone podczas pisania, przed pełnym runem.
- **Ile prób:** 1.
- **Czego się nauczyliśmy:** uruchamiać pełny `pytest` przed uznaniem etapu za zamknięty — tanie zabezpieczenie przy rosnącej liczbie modułów.
- **Status:** FIXED (0 USD, brak wpływu na harmonogram).

### [2026-07-11 19:09 UTC] Pierwsza realna próba researchu — ucięty JSON — [TECH]
- **Co miało działać:** jedno, jawnie zatwierdzone przez właściciela, realne (płatne) wywołanie Anthropic dla tematu „What really happens to your suitcase after check-in" (cap 0.30 USD, max 6 web searchy, max 1 retry) miało zwrócić kompletną kartę researchu.
- **Co nie zadziałało:** model naprawdę odpowiedział i naprawdę użył wyszukiwarki — ale jego odpowiedź (JSON) została ucięta w połowie, zanim skończył pisać. System poprawnie rozpoznał to jako błąd formatu (nie „spróbuj ponownie") i **nie ponowił** wywołania automatycznie — zgodnie z zasadą, że tylko błędy techniczne (np. timeout) są ponawiane, a błąd formatu nie.
- **Dlaczego:** najbardziej prawdopodobna przyczyna — limit długości odpowiedzi modelu (3000 „tokenów") okazał się za krótki na pełną kartę researchu z 6 wyszukiwaniami i wieloma źródłami. `FakeResearchClient` (używany dotąd w testach) zawsze zwracał krótką, gotową odpowiedź — więc ten problem nigdy wcześniej się nie ujawnił.
- **Jak naprawiono:** NIE ponowiliśmy automatycznie (zgodnie z poleceniem właściciela — „jedno uruchomienie i stop"). Naprawa merytoryczna: zamiast tylko podnosić limit długości odpowiedzi, **podzieliliśmy research na dwa mniejsze kroki** (patrz wpis „Estymator kosztu..." niżej i `05_BUDOWA_KROK_PO_KROKU.md`, Etap 1D) — każdy krok ma węższe zadanie i mniejsze ryzyko ucięcia.
- **Ile prób:** 1 (dokładnie tyle, ile było zatwierdzone).
- **Czego się nauczyliśmy:** klient zastępczy (fake) używany w testach jest zbyt „grzeczny" — nie ćwiczy sytuacji, w których prawdziwy model pisze więcej niż się spodziewaliśmy. Trzeba testować z bardziej realistycznymi (długimi) danymi, zanim zaufa się limitom ustawionym „na oko".
- **Status:** OPEN (naprawa architektoniczna gotowa i przetestowana lokalnie — dwuetapowy research; temat #2 pozostaje gotowy do ponownej, osobno zatwierdzonej próby w nowym trybie).

### [2026-07-11 19:09 UTC] Realny koszt zniknął z księgowości przy nieudanym researchu — [COST]
- **Co miało działać:** każde realne, płatne wywołanie API — udane czy nie — miało zostać zapisane z prawdziwą liczbą tokenów, liczbą wyszukiwań i kosztem w USD.
- **Co nie zadziałało:** kiedy powyższy błąd (ucięty JSON) wystąpił, kod „gubił" informację o tym, ile faktycznie tokenów i wyszukiwań zużyło to wywołanie. W efekcie w naszej bazie i w rejestrze kosztów to realne, płatne wywołanie wyglądało tak, jakby kosztowało **0.00 USD** — mimo że naprawdę zapytaliśmy płatne API firmy Anthropic.
- **Dlaczego:** błąd (JSON się nie sparsował) „przerywał" program w miejscu, zanim zdążył zapisać, ile faktycznie kosztowało wywołanie, które go poprzedziło.
- **Jak naprawiono:** przebudowaliśmy kod tak, żeby informacja o realnym zużyciu „trzymała się" błędu i docierała do miejsca, które zapisuje koszty, nawet gdy reszta się nie powiodła. Dopisaliśmy 3 nowe testy pilnujące dokładnie tej sytuacji, żeby nie powtórzyła się niezauważona.
- **Ile prób:** 1 (znalezione i naprawione od razu, bez dodatkowego wydawania pieniędzy — naprawa i testy używają wyłącznie danych testowych, nie prawdziwego API).
- **Czego się nauczyliśmy:** to bardzo pouczający błąd dla całego eksperymentu — **łatwo stracić z oczu prawdziwy koszt, jeśli księgowanie kosztu i obsługa błędu nie są tak samo starannie przemyślane jak „happy path"**. Dla projektu, którego jednym z celów jest policzyć koszt co do centa, to dokładnie ten typ błędu, który trzeba było znaleźć i pokazać uczciwie, a nie zamieść pod dywan.
- **Status:** FIXED (mechanizm i testy). **Aktualizacja 2026-07-11 (później tego samego dnia):** właściciel zweryfikował dokładną kwotę w panelu Anthropic — **realny koszt to 0,25 USD** (0,21 USD tokeny + 0,04 USD wyszukiwanie). Baza i wszystkie dokumenty poprawione z „0,00 USD"/„górna granica ≈0,095 USD" na tę potwierdzoną wartość.

### [2026-07-11] Estymator kosztu PRZED wywołaniem zaniżył realną cenę o ~163% — [COST]
- **Co miało działać:** liczba, którą pokazujemy PRZED wysłaniem zapytania do API, miała być bezpieczną **górną granicą** — czyli prawdziwy koszt nigdy nie powinien jej przekroczyć.
- **Co nie zadziałało:** po sprawdzeniu w panelu Anthropic okazało się, że prawdziwy koszt (0,25 USD) był **wyższy** niż nasza „górna granica" (0,095 USD) — czyli szacunek w ogóle nie spełniał swojej roli. Liczby: szacunek 0,095 USD, realny koszt 0,25 USD, różnica +0,155 USD, realny koszt **2,63×** wyższy niż szacunek, błąd szacunku ok. **+163%**.
- **Dlaczego:** stary sposób liczenia zakładał jeden, stały „zapas" na treść zwracaną przez wyszukiwarkę internetową, niezależnie od tego, ile razy model faktycznie szukał. W praktyce im więcej wyszukiwań, tym więcej tekstu wraca do modelu jako dodatkowy kontekst — czyli koszt **rośnie z liczbą wyszukiwań**, a nie jest stałą wielkością. Płaski zapas okazał się rzędu wielkości za mały.
- **Ważne wyjaśnienie:** limit kosztu, który ustawialiśmy przed wywołaniem, **nigdy nie był** „twardym hamulcem" działającym W TRAKCIE pojedynczego zapytania do API — dostawca (Anthropic) nie pozwala przerwać pojedynczego zapytania w połowie po przekroczeniu kwoty. To był i pozostaje **szacunek sprawdzany PRZED startem** — jeśli szacunek jest zły, ta kontrola nie chroni tak dobrze, jak się wydawało. Prawdziwą górną granicę wyznaczają tylko dwa ustawienia faktycznie wysyłane do API: maksymalna długość odpowiedzi i maksymalna liczba wyszukiwań — te zadziałały poprawnie (nie przekroczyliśmy zatwierdzonego limitu 0,30 USD), zawiodło tylko ich wcześniejsze wyliczenie.
- **Jak naprawiono:** zbudowaliśmy nowy sposób liczenia, który rośnie razem z liczbą planowanych wyszukiwań (a nie zakłada stałego zapasu) i ma wymagany margines bezpieczeństwa co najmniej 50%. Dodatkowo podzieliliśmy research na dwa mniejsze kroki (zbieranie źródeł osobno od analizy) — to zmniejsza ryzyko powtórki błędu z ucięciem, bo każdy krok robi mniej naraz.
- **Ile prób:** 1 (błąd znaleziony przy weryfikacji pierwszej realnej próby; cała naprawa i nowe testy zrobione wyłącznie lokalnie, bez wydawania kolejnych pieniędzy).
- **Czego się nauczyliśmy:** szacunek „na oko" bez oparcia w realnych danych jest ryzykowny, zwłaszcza gdy w grę wchodzą prawdziwe pieniądze. Jedna realna obserwacja to za mało, żeby ufać szacunkowi bezgranicznie — dlatego nowy sposób liczenia jest jawnie oznaczony jako przybliżenie „do doprecyzowania po kolejnych realnych próbach", nie jako ostateczna prawda.
- **Status:** FIXED (nowy sposób liczenia + podział na dwa kroki), z jawnie przyznanym ryzykiem: kalibracja wciąż opiera się tylko na jednej realnej próbie.

### [2026-07-12] Wyniki pierwszego kroku researchu istniały tylko w pamięci — ryzyko utraty przy awarii między krokami — [COST]
- **Co miało działać:** podział researchu na dwa kroki (Etap 1D) miał chronić przed utratą kosztownych wyników wyszukiwania przy błędzie finalnej analizy.
- **Co nie zadziałało:** ta ochrona działała TYLKO wewnątrz jednego, ciągłego uruchomienia programu — wyniki pierwszego kroku (znalezione źródła) istniały wyłącznie jako dane „w locie", dopóki program nie skończył też drugiego kroku. Awaria komputera/procesu dokładnie MIĘDZY tymi dwoma krokami (zamknięty terminal, restart, przerwa w zasilaniu) nadal skasowałaby już opłacone wyniki wyszukiwania — dokładnie ten sam rodzaj straty co przy pierwszym incydencie (2026-07-11), tylko przesunięty o jeden poziom głębiej.
- **Dlaczego:** podział na dwa kroki rozwiązał ryzyko ucięcia odpowiedzi WEWNĄTRZ jednego wywołania, ale nikt jeszcze nie zbudował miejsca do zapisania wyników kroku 1 na trwałe PRZED przejściem do kroku 2.
- **Jak naprawiono:** to nie był jeszcze faktyczny incydent (nie doszło do realnej straty) — znaleźliśmy tę lukę proaktywnie, analizując architekturę, i zamknęliśmy ją PRZED kolejną realną próbą. Wyniki kroku 1 są teraz zapisywane na trwałe (do bazy) natychmiast po sukcesie, w jednej nierozdzielnej operacji razem ze zmianą statusu — więc nie ma stanu pośredniego, w którym źródła są znalezione, ale nigdzie nie zapisane. Dodano możliwość wznowienia wyłącznie kroku 2 z zapisanych danych, bez ponownego szukania. Szczegóły: `05_BUDOWA_KROK_PO_KROKU.md` Etap 1G, `docs/DECISIONS.md` ADR-019.
- **Ile prób:** 1 (zaprojektowane i przetestowane poprawnie od razu, na klientach zastępczych).
- **Czego się nauczyliśmy:** naprawienie jednego problemu (ucięcie odpowiedzi) czasem tylko przesuwa podobne ryzyko na inny poziom architektury (tu: z „wewnątrz wywołania" na „między wywołaniami tego samego procesu) — warto po każdej naprawie zapytać „a co, jeśli padnie dokładnie TERAZ, w tym nowym miejscu?".
- **Status:** FIXED, zanim doprowadziło do realnej straty.

### [2026-07-12] Brakujący licznik w pomocniczej klasie testowej — [TECH]
- **Co miało działać:** jeden z nowych testów wznawialności miał sprawdzić, że przy odmowie wznowienia (bo wciąż za mało źródeł) program NIE woła płatnego API ani razu.
- **Co nie zadziałało:** pomocnicza klasa użyta w teście nie miała licznika wywołań — test padał błędem braku atrybutu, zanim zdążył cokolwiek sprawdzić.
- **Dlaczego:** klasa pomocnicza była napisana pod kątem innego zachowania (blokady pierwszego kroku), nie pod kątem liczenia wywołań drugiego kroku — przeoczenie przy pisaniu testu, nie błąd w kodzie produkcyjnym.
- **Jak naprawiono:** dodano licznik i nadpisanie odpowiedniej metody w klasie pomocniczej.
- **Ile prób:** 1.
- **Czego się nauczyliśmy:** drobne, ale częste źródło marnowanego czasu — pomocnicze klasy testowe trzeba dopasować dokładnie do tego, co dany test sprawdza, nie tylko do ogólnego scenariusza.
- **Status:** FIXED (0 USD, brak wpływu na harmonogram).

### [2026-07-12 03:30 UTC] Drugi realny test — awaria kroku 1 (nie kroku 2, jak planowaliśmy) — [TECH]
- **Co miało działać:** drugie, zatwierdzone przez właściciela, realne wywołanie nowej wznawialnej architektury (cap 0,45 USD) — plan zakładał, że jeśli coś padnie, to raczej krok 2 (analiza), co pozwoliłoby pokazać na żywo wznowienie samego kroku 2.
- **Co nie zadziałało:** zamiast tego padł **krok 1** (zbieranie źródeł) — model znowu zwrócił odpowiedź uciętą w połowie (JSON nieparsowalny), tym razem dużo wcześniej niż przy pierwszej próbie z 11.07, mimo że krok 1 ma celowo lżejszy, węższy schemat niż tamten stary, jednokrokowy research.
- **Dlaczego:** najbardziej prawdopodobna (ale niepotwierdzona ostatecznie) przyczyna: limit długości odpowiedzi kroku 1 (domyślnie 1200 „tokenów") wciąż za ciasny na pełny wynik 4 wyszukiwań. Nie zapisujemy surowej, nieudanej odpowiedzi modelu — więc nie da się tego stwierdzić ze 100% pewnością bez kolejnej próby z podniesionym limitem.
- **Jak naprawiono:** świadomie NIE naprawiono w ramach tego zdarzenia — zgodnie z ustaloną zasadą „jedno uruchomienie, zero automatycznych ponowień, zatrzymaj się i zgłoś wynik". Ewentualna zmiana limitu i kolejna próba wymaga osobnej zgody właściciela.
- **Ile prób:** 1 (dokładnie tyle, ile zatwierdzone).
- **Czego się nauczyliśmy:** to jednocześnie zła i dobra wiadomość. Zła: podział na dwa kroki (Etap 1D) i tak nie wyeliminował do końca ryzyka ucięcia odpowiedzi — tylko zmniejszył jego zasięg. Dobra, ważniejsza: **wszystkie mechanizmy bezpieczeństwa zbudowane właśnie na wypadek takiej sytuacji zadziałały bez zarzutu** — status poprawnie „nieudany" (nie fałszywie „częściowy"), zero źródeł błędnie zapisanych, a realny koszt (0,123823 USD) i tak trafił do księgowości, mimo całkowitej porażki kroku 1. To dokładnie ten mechanizm, którego brakowało przy pierwszej próbie 11.07 — teraz sprawdzony na żywo, w nowym miejscu kodu, i zadziałał.
- **Status:** OPEN → **AKTUALIZACJA (ta sama sesja, później):** właściciel ocenił hipotezę „po prostu podnieś limit" jako niewystarczającą — trafna diagnoza: problem jest strukturalny (jedna odpowiedź na wszystkie źródła naraz), nie kwestia jednej liczby. Krok 1 przebudowany na „szukanie" (tylko lista adresów) + „czytanie pojedynczego źródła" (każde źródło osobnym, niezależnym zapytaniem, zapisywane natychmiast) — patrz wpis „Krok 1 rozbity na szukanie i czytanie pojedynczego źródła" niżej. Mechanizm ochrony statusu/kosztu nadal oceniany jako działający poprawnie — to on właśnie umożliwił bezpieczne wykrycie i naprawienie tego problemu bez utraty danych czy pieniędzy.

### [2026-07-12, ta sama sesja, później] Krok 1 rozbity na „szukanie" i „czytanie pojedynczego źródła" — naprawa strukturalna, nie kolejna łatka — [TECH]
- **Co miało działać:** poprzedni wpis (wyżej) zakończył się rekomendacją „podnieś limit długości odpowiedzi kroku 1 i spróbuj ponownie".
- **Co nie zadziałało / co postanowiliśmy zrobić inaczej:** właściciel zauważył, że to zbyt płytka naprawa — nawet z wyższym limitem, krok 1 nadal zwracałby JEDNĄ dużą odpowiedź obejmującą wszystkie źródła naraz, więc ucięcie w dowolnym miejscu wciąż kasowałoby wszystko, tylko przy nieco większej liczbie źródeł niż poprzednio. To przesuwanie progu awarii, nie usuwanie przyczyny.
- **Dlaczego (diagnoza tym razem trafna od razu):** konstrukcja „jedna odpowiedź = wiele źródeł" jest z natury krucha, niezależnie od limitu długości.
- **Jak naprawiono:** krok 1 rozbity na dwa niezależne pod-kroki: „szukanie" (agent zwraca tylko krótką listę adresów-kandydatów, zero analizy, każdy kandydat w osobnej linijce) i „czytanie pojedynczego źródła" (KAŻDE źródło to osobne, niezależne zapytanie do modelu, zapisywane do bazy natychmiast po przetworzeniu). Dodatkowo: każda prawdziwa odpowiedź modelu jest teraz zapisywana do prywatnego pliku diagnostycznego (treść + powód zatrzymania generacji wprost z API), żeby przyszłe podobne sytuacje dało się potwierdzić, nie tylko podejrzewać.
- **Ile prób:** 0 realnych (cała naprawa i 12 nowych testów zbudowane i sprawdzone wyłącznie na danych zastępczych, bez wydania ani centa).
- **Czego się nauczyliśmy:** to ważna lekcja o różnicy między „załataniem objawu" a „naprawieniem przyczyny" — podniesienie limitu naprawiłoby TEN konkretny test, ale nie następny, przy nieco większej liczbie źródeł. Rozbicie na osobne, niezależne wywołania per źródło usuwa całą KLASĘ tego problemu, nie tylko ten jeden przypadek.
- **Status:** FIXED architektonicznie (12 nowych testów). Wciąż OPEN: brak jeszcze potwierdzenia na żywym API — mały, tani test zaproponowany, czeka na zgodę.

### [2026-07-12] Diagnostyka A2 najpierw padła lokalnie przez niezgodność SDK — [TECH]
- **Co miało działać:** pojedyncza diagnostyka oczekującego kandydata `id=3`, bez ponawiania nieudanych kandydatów 1 i 2.
- **Co nie zadziałało:** `anthropic==0.37.1` próbował przekazać `httpx==0.28.1` usunięty argument `proxies`; program zatrzymał się przed requestem.
- **Jak naprawiono:** projektowe `.venv` dostało `anthropic==0.116.0`, które spełnia istniejące `anthropic>=0.40`. Ostrzeżenia o wymaganiu `anthropic<0.38` przez niezależny `open-interpreter` nie naprawiano — poza zakresem.
- **Koszt:** **0,00 USD**, zero API dla lokalnej porażki.
- **Status:** FIXED w izolowanym środowisku projektu.

### [2026-07-12] Limit A2=500 potwierdzony jako za niski; 5000 było tylko diagnostyczne — [TECH/COST]
- **Co zadziałało:** po poprawie SDK kandydat `id=3` zakończył się `end_turn`: input 14 394, output 915, 1 search, VERIFIED, quality 0,55. Kandydatów 1 i 2 NIE ponawiano, więc nie znamy ich dokładnego zapotrzebowania na output.
- **Jak naprawiono:** produkcyjny default ustawiono na **1500**, z zachowanym override CLI. Jednorazowe 5000 było tylko szerokim sufitem pomiarowym, nie defaultem.
- **Koszt:** call diagnostyczny **0,028969 USD**; cały run po nim **0,126793 USD**; cały projekt **0,500616 USD**. Conservative estimate 0,1256 USD był bezpieczny, lecz ~4,34× wyższy od calla — nie był dokładny.
- **Dodatkowy błąd naprawiony offline:** podsumowanie CLI A2 agreguje teraz model, tokeny, search i koszt wszystkich A2 w bieżącej inwokacji; baza nadal przechowuje koszt skumulowany runu. Pełny `pytest`: **102 passed**.
- **Status:** FIXED dla limitu/podsumowania; P1-5 retry nadal OPEN i niezaimplementowane.

---

### [2026-07-12] PowerShell potraktował alternację regexu jak potok

- **Co miało działać:** lokalne wyszukanie odwołań do staged research i zabezpieczeń.
- **Co się zepsuło:** wzorzec zawierający znak `|` został przekazany w podwójnych cudzysłowach; PowerShell zinterpretował jego fragment jak kolejne polecenie i zgłosił błąd `discover: The term 'discover' is not recognized`.
- **Przyczyna:** niewłaściwe cytowanie wyrażenia regularnego w powłoce, nie błąd aplikacji.
- **Naprawa:** wzorzec uruchomiono ponownie w pojedynczych cudzysłowach.
- **Liczba prób:** 2; druga zakończona sukcesem.
- **Skutek:** brak zmian danych, brak API, koszt 0,000000 USD.
- **Ryzyko powtórki:** niskie, jeśli regexy z alternacją są cytowane pojedynczo.

### [2026-07-12] Kontrola odczytowa wskazała błędną nazwę bazy SQLite

- **Co miało działać:** końcowe potwierdzenie, że statusy istniejących runów nie zmieniły się.
- **Co się zepsuło:** polecenie wskazało `data/nothing_is_accidental.db` zamiast skonfigurowanego `data/agent.db`; SQLite utworzył pusty plik i zwrócił `no such table: research_runs`.
- **Naprawa:** usunięto wyłącznie nowo utworzony pusty plik i powtórzono odczyt na poprawnej bazie.
- **Wynik:** nadal dokładnie 2 runy (`FAILED`, `PARTIAL`), bez zmiany statusów lub danych; zero API i kosztu.
- **Zapobieganie:** ścieżkę do bazy brać z konfiguracji, nie zakładać jej nazwy.

### [2026-07-12] Stary test migracji pomylił nową wersję schematu z błędem migracji — [TEST]
- **Co miało działać:** po dodaniu 0007 istniejące testy flow miały nadal potwierdzać bezpieczne zastosowanie migracji od schematu 0005.
- **Co nie zadziałało:** pięć testów oczekiwało listy z samym `0006_research_run_flow`; rzeczywisty wynik poprawnie zawierał także `0007_candidate_attempts`.
- **Dlaczego:** test był zbyt literalnie związany z liczbą kolejnych migracji, choć jego intencją było sprawdzenie zachowania 0006.
- **Jak naprawiono:** rozszerzono oczekiwane listy i dopisano osobny test 0007 dla `attempts=0` w danych historycznych, `integrity_check` i `foreign_key_check`.
- **Wynik:** 153 testy zielone; to błąd testu wykryty offline, bez API, bazy produkcyjnej i kosztu.

### [2026-07-12] Review pokazał, że `attempts=0` i osobny COMMIT nie są neutralne — [SAFETY]
- **Co miało działać:** cap 2 miał oznaczać pierwszą próbę i jedno retry, a migracja miała być ponawialna po awarii.
- **Co nie działało:** historyczny failed z zerem dostawał dwa kolejne retry; rekord pending po przerwaniu mógł przekroczyć cap; schema mógł zostać zmieniony przed wpisem wersji.
- **Dlaczego:** zero nie kodowało dolnej granicy znanej ze statusu, a licznik bez stanu in-progress nie opisywał niepewnego wyniku zewnętrznego calla. DDL i ledger miały osobne commity.
- **Jak naprawiono:** backfill 0/1, warunkowy claim do `EXTRACTION_IN_PROGRESS`, jawny higher-cap reopen i jedna transakcja migration runnera. Trigger SQLite sprawdza rollback schema razem z ledgerem.
- **Wynik:** 164 testy zielone, 0 USD, zero API i bez dotykania źródłowej bazy.

## Kategoria „jeszcze nieodkryte" (świadome luki, spodziewane błędy)
Te pozycje **jeszcze się nie wydarzyły**, bo nie doszliśmy do odpowiednich etapów. Zapisujemy je jako spodziewane pola ryzyka, żeby uczciwie pokazać, czego się obawiamy (ryzyka R2–R12 z planu):
- **[BROWSER/R2/R3]** zmiany UI Substacka, wygaśnięcie sesji / 2FA — spodziewane przy Etapie 4.
- **[QUALITY/R6/R12]** halucynacje źródeł, powtarzalność stylu — pierwsze realne dane pojawią się po pierwszym płatnym researchu i pierwszych szkicach.
- **[INJECTION/R4]** prawdziwa próba prompt injection z treści internetowej — mechanizm obronny zbudowany, ale nietestowany na żywych danych.
- ~~**[COST/R7]** realny rozjazd „szacunek dry_run vs faktyczny koszt" — pojawi się przy pierwszym `--real`.~~ **WYDARZYŁO SIĘ i jest udokumentowane wyżej** (0,095 USD szacunek vs 0,25 USD realnie, błąd +163%) — ryzyko potwierdzone, naprawa wdrożona.
- **[ACCOUNT/R10]** pomyłka konta — chronione przez `account_id` w każdej akcji; test izolacji obowiązkowy przed włączeniem drugiego konta.
- **[DATA/P2]** ujemne `attempts` w ręcznie uszkodzonym rekordzie może ominąć cap; normalny kod takich wartości nie tworzy. Plan: dolna granica w claimie/modelu i ewentualny CHECK constraint.

## Podsumowanie liczbowe (stan 2026-07-12, po diagnostyce limitu A2)
- Błędy techniczne/kosztowe wykryte i naprawione: **10** (wcześniejsze 8 + lokalna niezgodność `anthropic/httpx` + błędne, niepełne podsumowanie usage/kosztu A2 w CLI). Osobno skorygowano zbyt niski default A2 z 500 do 1500 po diagnostyce.
- Złe decyzje agenta / słabe teksty / złe komentarze: **0** (nie doszliśmy do generacji treści).
- Zatwierdzone płatne operacje/testy researchu: **4**, obejmujące łącznie **6 requestów API** (1 + 1 + 3 + 1). Pełna Research Card wciąż nie powstała. **Łączny realny koszt: 0,500616 USD**. Pierwsza lokalna próba diagnostyczna SDK nie dotarła do API i kosztowała 0 USD.
- Dokładność wcześniejszego szacunku kosztu: pierwsza próba — **błąd ~+163%** (szacunek 0,095 vs realne 0,25 USD, zaniżony). Druga próba — odwrotnie: szacunek (0,3615 USD) był **wyższy** niż realny koszt (0,123823 USD) — margines bezpieczeństwa zadziałał we właściwą stronę. Nowy estymator (po przebudowie) kalibrowany z OBU tych obserwacji naraz, pokazuje osobno „bezpieczny sufit" i „środkowy szacunek".
- Testy po wszystkich naprawach: **102 zielone**, zero regresji.
- Przebudowy: **3 architektoniczne** (ADR-016/019/020) + drobniejsze refinements (dry_run, zachowanie usage przy błędzie, estymator, diagnostyka, default A2=1500 i agregacja CLI). Nadal brak pełnej realnej Research Card; P1-5 i prawdziwy fetch źródła pozostają otwarte.

## Powiązania
- `docs/ERRORS_AND_FAILURES.md` (źródło), `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` §B.12 (ryzyka R1–R12)
- `08_INTERWENCJE_CZLOWIEKA.md`, `14_WNIOSKI_CZASTKOWE.md`

### [2026-07-12] Potencjalna powtórka kosztu po sukcesie — zatrzymana przed API
- **Ryzyko:** system umiał stworzyć kartę, ale nie odróżniał później kompletnego wyniku od tematu gotowego do zwykłego świeżego researchu.
- **Naprawa:** `USED` jest ustawiane razem z COMPLETE; brak force kończy CLI zanim powstanie klient API.
- **Dowód:** 169 testów, w tym odmowa przed konstrukcją klienta; 0 USD i zero API.

### [2026-07-12] Pierwsza poprawka Task 4 była za wąska — znalezione offline
- **Co nie działało:** COMPLETE mogło wskazać kartę innego tematu; błąd ostatniego UPDATE zostawiał wcześniej zatwierdzony `runs.SUCCESS`.
- **Naprawa:** walidacja relacji card-topic-account i jedna granica transakcji dla COMPLETE, terminalnego runu i USED.
- **Dowód:** trigger SQLite + reopen dla trzech flow, **186 passed**, 0 USD i zero API.

### [2026-07-12] Druga finalizacja przepisywała historię ukończonego runu — [SAFETY]

- **Co nie działało:** po poprawnym COMPLETE drugie wywołanie mogło zmienić kartę 1→2, koszt 0,1→0,9 i timestampy.
- **Dlaczego:** pierwsza poprawka zapewniała atomowość, ale nie rozpoznawała powtórzenia ani konfliktu z utrwalonym wynikiem.
- **Jak naprawiono:** identyczny payload jest no-op; sprzeczny lub uszkodzony COMPLETE jest odrzucany bez mutacji. Dodano brakującą macierz guard/force/failure dla wszystkich flow.
- **Nieudana próba podczas poprawki:** pierwszy guard był zbyt ścisły dla legalnego wznowienia legacy Stage B ze stanu FAILED; zawężono wyjątek wyłącznie do jawnego resume TWO_STAGE z zachowanymi źródłami.
- **Wynik:** **206 testów**, 0 USD, zero API i realnego researchu.

### [2026-07-12] Trzecie review: brak testu to brak dowodu kontraktu — [TEST]

- **Co nie działało:** kod prawidłowo obsługiwał konflikt Stage B i obce karty, lecz testy nie pokrywały tych ścieżek wprost; account mismatch liczył tylko `runs`.
- **Jak naprawiono:** sześć testów SQLite z reopen oraz cztery liczniki tabel dla runnera i capped CLI. Kod produkcyjny pozostał nietknięty.
- **Wynik:** 212 testów, 0 USD, zero API.

### [2026-07-12] P2-18: dokładne `float == float` może fałszywie odrzucić no-op — [DATA]

- **Ryzyko:** `0.1 + 0.2` i `0.3` mogą mieć inną reprezentację binarną.
- **Wpływ:** wyłącznie bezpieczna odmowa; brak nadpisania danych.
- **Plan późniejszy:** najmniejsza jednostka, `Decimal` albo tolerancja zgodna z `model_usage`. Nie naprawiano w Task 4.

### Task 5 — dwa rodzaje niewiedzy o timeoutach
Jeśli timeout zwraca usage, zapisujemy je przed decyzją o retry. Jeśli nie zwraca, provider nadal może naliczyć koszt — `timeout-billed-unrecorded`. Nie dopisujemy fikcyjnego usage. Pierwsza implementacja miała też niebezpieczny skrót: `dry_run=True` omijało kontrolę limitów; istniejące testy wykryły fail-open i skrót usunięto.

Pełne review znalazło kolejne trzy luki: opcjonalny cap realnego pipeline, rosnący cap resume oraz NaN/Infinity limitów kończące się `OK`. Wszystkie poprawiono fail-closed i pokryto regresjami; rezydualne ryzyko providera pozostało jawne.
