# Dziennik badań Agent V3

## 2026-08-21 — audyt bazowy

**Działania:** zinwentaryzowano V3, odtworzono przepływ artykułu i dnia, przeanalizowano bazę, pliki stanu, prompty, testy, konfigurację, przeglądarkę i historyczną dokumentację V2.  
**Wynik:** 73 ustalenia A-001–A-073; 14 P0, 43 P1, 16 P2.  
**Koszt modeli:** 0 USD.  
**Mutacje zewnętrzne:** brak.  
**V2:** tylko odczyt.

Kontrole bazowe:

- 117 plików w migawce przed dodaniem dokumentacji;
- 59 plików Python sparsowanych przez AST;
- 0 błędów składni;
- 12 głównych modułów i 11 239 linii;
- 36 zwykłych plików testowych i 10 skryptów testów płatnych;
- identyfikatory A-001–A-073 ciągłe i bez duplikatów;
- odciski dwunastu modułów zgodne z aneksem.

## 2026-08-21 — konsolidacja dokumentacji

**Działania:** utworzono `agent-v3/wnioski badania`; przeniesiono dokumentację audytu, dokumentację zastaną, materiał historyczny V2 oraz dwa materiały wejściowe. Utworzono centralny indeks, metodologię, politykę testów i plan napraw.  
**Powód:** jeden punkt prawdy i rozdzielenie aktualnego audytu od historycznych instrukcji operacyjnych.  
**Zmiany funkcjonalne:** brak.  
**Mutacje zewnętrzne:** brak.  
**V2:** brak zapisu.

Pliki będące aktywnymi promptami albo instrukcjami związanymi ze ścieżką wykonawczą pozostawiono przy kodzie. Ich przeniesienie mogłoby zmienić zachowanie lub utrudnić bezpieczne uruchamianie testów.

## 2026-08-21 — kwerenda repozytoriów podobnych

**Działania:** zweryfikowano sześć projektów wskazanych w materiale wejściowym i jedno nieoficjalne repozytorium referencyjne API. Odczytano README oraz wybrane implementacje bezpieczeństwa, analityki, uczenia, publikacji, logowania i testów. Utrwalono hashe HEAD i daty commitów.  
**Tryb:** płytkie kopie publicznego kodu w katalogu tymczasowym; bez instalacji i wykonania kodu.  
**Koszt modeli:** 0 USD.  
**Mutacje kont:** brak.

Najważniejsze wyniki:

1. Pętla uczenia z `substack-growth-engine-template` zachowuje oryginalny draft, porównuje go z wersją końcową i przenosi reguły głosu, ale jej zależność od zewnętrznej akceptacji, dopasowanie treści oraz brak testów czynią ją niezgodną z celem pełnej autonomii. Do V3 nadaje się sam wzorzec niezmiennego oryginału i różnicy przed/po.
2. `substack-mcp` pokazuje wartościowy wzorzec jawnych klas możliwości, opisów działań natychmiast publicznych, typowanych błędów, timeoutów i testów kontraktu. Jego ograniczenia publikacyjne nie są docelową polityką V3.
3. `substack-author-agent` pokazuje wspólne instrukcje dla kilku SDK i obserwowalność kosztów/tool calli, ale jest doradcą, nie autonomiczną redakcją.
4. `kyarminrox/substack-agent` ma scentralizowane selektory, JSONL i screenshoty, lecz deklaruje się jako scaffolding v0.1 i domyślnie ustawia `SAFE_MODE=false`; nie jest wzorcem bezpiecznej wartości domyślnej.
5. `santhosh-patel/substack-agent` ma wspólną warstwę MCP/API i autoryzację, ale udostępnia natychmiastowe publikowanie oraz automatyczne komentarze; interfejs narzędziowy nie zastępuje polityki autonomii.
6. `drona23/substack-ai-bot` jest liniowym generatorem draftów bez porównywalnej pamięci, bramek i testów; nie jest punktem odniesienia dla docelowej pętli redakcyjnej.
7. `substack-api-reference` jest użytecznym zeszytem obserwacji endpointów, ale sam autor oznacza API jako nieoficjalne i zmienne; V3 musi mieć adapter, testy kontraktowe i degradację, nie rozsiane wywołania.

Pełne dane znajdują się w `../04_badania_porownawcze/PRZEGLAD_REPOZYTORIOW_2026-08-21.md`.

## Kolejny wpis

Następny wpis powstaje przed rozpoczęciem pierwszej naprawy funkcjonalnej. Musi zawierać identyfikator błędu, stan przed zmianą, test kontrdowodu, plan rollbacku oraz potwierdzenie, że ścieżki V2 są poza staged diff.

## 2026-08-21 — korekta celu i kontrola integralności dokumentacji

**Korekta celu:** docelowy V3 ma być w pełni autonomiczny. Z aktualnej specyfikacji usunięto zewnętrzne bramki akceptacyjne. Wprowadzono automatyczne stany kwarantanny, pełną ponowną kontrolę po rewizji, reguły rollout/rollback i koniunkcyjną decyzję publikacyjną. Materiały historyczne pozostają niezmienione jako źródła, ale nie są aktywnym kontraktem.  
**Kontrole:** 25 plików Markdown w katalogu badawczym; 0 uszkodzonych lokalnych linków; 73 unikalne identyfikatory A-001–A-073; 0 brakujących identyfikatorów; 59/59 plików Python poprawnych składniowo według AST; 12/12 odcisków głównych modułów zgodnych z aneksem; 0 plików o nazwach sesji/sekretów i 0 plików pasujących do wzorca jawnie przypisanego sekretu w V3.  
**Kod funkcjonalny:** bez zmian w tej fazie.  
**Koszt modeli:** 0 USD.  
**V2:** istniejące zmiany wykryte, lecz nie dotknięte i niewłączone do zakresu.

## 2026-08-21 — punkt bazowy Git

**Gałąź:** `codex/agent-v3-gpt`  
**Commit migawki:** `00ab0c4` (`chore(agent-v3): snapshot autonomous prototype and audit baseline`)  
**Zakres:** 132 pliki, 38 359 dodanych linii; `.gitignore` oraz `agent-v3`.  
**Wykluczenia potwierdzone:** zero staged ścieżek `agent-v2`, zero plików sesji/sekretów, zero `agent-v3/data/zasiew-produkcji.db`.  
**GitHub:** gałąź wysłana do `origin`; bez PR, release'u i wdrożenia.  
**Znaczenie:** jest to stabilny punkt odniesienia audytu, a nie deklaracja gotowości produkcyjnej ani zamknięcia ustaleń.

## 2026-08-21 — audyt promptów i głosu redakcyjnego

**Działania:** porównano odciski całego katalogu promptów V2 i V3, odtworzono kompozycję promptów artykułu, Notes, komentarzy, odpowiedzi i rewizji, prześledzono profile stylu oraz pokrycie testami. Utworzono `AUDYT_PROMPTOW_I_GLOSU_REDAKCYJNEGO.md`.

**Wynik porównania:** 25 plików promptowych V3 jest identycznych z V2, 2 są rozszerzone, a `redaktor.md` istnieje tylko w V3.

**Nowe ustalenia:** A-074–A-083; 7 P1 i 3 P2. Bieżący rejestr obejmuje 83 ustalenia: 16 P0, 53 P1 i 14 P2.

**Errata liczbowa:** wcześniejszy wpis bazowy podał rozkład 14 P0, 43 P1 i 16 P2. Ponowne mechaniczne policzenie nagłówków rejestru wykazało, że dla A-001–A-073 prawidłowy rozkład wynosił 16 P0, 46 P1 i 11 P2. Wpis historyczny pozostaje niezmieniony, a niniejsza errata go zastępuje.

**Najważniejszy wniosek:** zatwierdzony korpus i profile rzeczywiście docierają tylko do pisarza artykułu. Profil Notes jest niepodłączony, redaktor nie otrzymuje kontraktu głosu, krótkie formaty mają kopiowane polityki, a niezaufany tekst może wejść do pamięci promptowej.

**Testy i modele:** nie uruchomiono; analiza wyłącznie statyczna.

**Kod funkcjonalny i prompty:** bez zmian.

**Koszt modeli:** 0 USD.

**Mutacje zewnętrzne:** brak.
**V2:** tylko odczyt; zastane zmiany pozostawiono nietknięte.

## 2026-08-21 — E-001: fundament izolacji V3

**Karty:** N-001, N-002, N-003 oraz fundament N-004.

**Zmiana funkcjonalna:** dodano centralny rejestr czternastu możliwości i czterech trybów. Fixture jest domyślny, kill switch domyślnie aktywny i dynamiczny. Modele, publiczny HTTP, Substack, sesja, SMTP oraz dziewięć klas mutacji otrzymały bramki przy granicach transportowych. Wszystkie wejścia mutujące kończą wyslij=False przed przeglądarką.

**Izolacja:** V3 nie ładuje głównego .env, a fixture nie odczytuje nawet namespacowanych kluczy. Sekrety, SMTP, cel i sesja używają przestrzeni AGENT_V3. Cel nothingisaccidental jest bezwarunkowo zabroniony dla mutacji V3.

**Artefakty operacyjne:** uruchom-dzien.cmd działa wyłącznie jako lokalny fixture V3; wdroz.sh odmawia kodem 64; usługi systemd wykonują wyłącznie /usr/bin/false. Aktywne odwołania wykonawcze V3 do V2: zero.

**Przebieg testów:** pierwszy test celu wykrył dwa warianty błędu CP1252. Szeroka regresja odróżniła brak zależności systemowego Pythona od dryfu testów. Po korektach końcowy test celu wyniósł 14/14, a bezpieczna regresja 35/35 plików. Test CLI odmówił --wyslij przed bazą i nie zmienił agent-v3/data. Pełny przebieg oraz wszystkie próby pośrednie zapisano w rejestrze wyników i raporcie E-001.

**Świadome wyłączenia:** test sieciowy, test sygnałów Linuxa, katalog płatny i dodatni live_test.

**Drobna korekta promptu:** usunięto martwe pole numbers_used z kontraktu redaktora. Nie zmieniono głosu ani instrukcji pisarskich; pełne naprawy promptów pozostają w N-013–N-015.

**Koszt online:** 0.00 USD.

**Mutacje zewnętrzne:** brak.

**V2:** brak zapisu. Numstat na końcu partii pozostał 61/10 dla run.py i 21/4 dla stages.py; zastany test nieśledzony pozostał nietknięty.

**Ograniczenie:** N-004 nie jest zamknięte jako cały potok. Nie istnieje jeszcze replay scout–publikacja, a dodatnia ścieżka live_test nie została sprawdzona.

## 2026-08-21 — E-002: ledger mutacji i potwierdzeń

**Karta:** N-005.

**Zmiana funkcjonalna:** dodano tabelę `mutation_attempts` i moduł `mutation_ledger.py`. Każda mutacja jest atomowo rezerwowana przed kliknięciem, ma stabilny klucz intencji i sekwencję oraz przechodzi przez PENDING, FAILED, UNKNOWN albo CONFIRMED. CONFIRMED wymaga niepustej `source_ref` po utrwalonym dispatch.

**Restart:** pod wyłącznym zamkiem procesu przerwane PENDING bez dispatch jest autonomicznie domykane jako FAILED, a PENDING po dispatch jako UNKNOWN. Każde PENDING lub UNKNOWN blokuje wszystkie dalsze mutacje. Nie istnieje fallback ponawiający niepewny skutek.

**Potwierdzenia:** artykuł używa dokładnego ID szkicu, tytułu i daty. Notka, komentarz, odpowiedź i restack wymagają ID obiektu ze źródła. Polubienie, obserwacja i subskrypcja zapisują wersjonowaną referencję potwierdzonego stanu UI. Ustawienie bez stabilnej referencji pozostaje UNKNOWN.

**Prawda liczników:** odpowiedzi, notki, komentarze, historia celu, rytm, zużycie faktu i promocja zmieniają się dopiero po potwierdzeniu. Pierwszy UNKNOWN kończy serię oraz następne bloki mutujące dnia.

**Przebieg testów:** rdzeń ledgeru 16/16 PASS; restack 17/17 PASS z kontrprzykładem UNKNOWN; obserwacje 34/34; granica komentarza 19/19, w tym wyjątek po dispatch; bezpieczeństwo 14/14; zapis wywołań 16/16. Pierwsza seria sąsiednia bez UTF-8 padła na CP1252 i została zachowana jako T-018. Pierwsza szeroka komenda miała błędny wzorzec wyłączeń Windows: 37/38 plików przeszło, a platformowy test czasu uzyskał 10 PASS/4 FAIL. Po korekcie zestawu i rekwalifikacji atrapowego `test_pobieranie.py` finalna regresja wyniosła 37/37.

**Koszt online:** 0.00 USD.

**Sieć, modele i mutacje zewnętrzne:** brak.

**V2:** tylko kontrola odczytowa; zastane różnice pozostają poza zakresem.

**Status:** N-005 = FIXED_OFFLINE; LIVE_CONTRACT_OPEN. Aktualność selektorów, dodatnia ścieżka live i automatyczna rekoncyliacja źródłowa UNKNOWN nie zostały dowiedzione.

**Raport:** `../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-002_LEDGER_MUTACJI.md`.

**Kontrola końcowa:** 37/37 bezpiecznych plików regresji; 34 dokumenty Markdown; 0 uszkodzonych linków wykonywalnych. Skan znalazł jeden zapis `({url})` wewnątrz historycznego przykładu V2, który jest placeholderem kodu, nie odsyłaczem dokumentacji. `git diff --check` nie wykazał błędów poza informacyjnymi ostrzeżeniami CRLF. `agent-v3/data` bez zmian. Stan V2 pozostał identyczny z początkiem partii: run.py 61/10, stages.py 21/4 i ten sam nieśledzony test.

## 2026-08-21 — E-003: zamrożona doba i trwały budżet

**Karta:** N-006. **Ustalenia:** A-029–A-032 oraz wykryte w trakcie A-084.

**Stan przed:** plan dnia był ponownie losowany przy każdym przebiegu; follow i
subskrypcje nie były odejmowane; JSONL fail-open sterował częścią limitów;
odpowiedzi nie miały twardego sufitu; okno publikacji, ciche dni, promocja,
liczniki i koszty nie dzieliły jednej granicy doby.

**Zmiana funkcjonalna:** dodano wersjonowany `OperationalDay` zapisujący raz na
dobę konto, lokalny klucz dnia, granice UTC, hash polityki, rozbieg, ciszę i
pełny plan. Widełki dzienne są deterministyczne, a miesięczne alokacje follow i
subskrypcji wybierają dokładnie N dni. Każdy znany rodzaj mutacji ma kategorię;
nieznany rodzaj jest odrzucany fail-closed.

**Transakcja:** rezerwacja jednostki i `mutation_attempts.PENDING` powstają w
jednym `BEGIN IMMEDIATE`. `FAILED` zwalnia jednostkę, `CONFIRMED` zużywa,
`PENDING` rezerwuje, a `UNKNOWN` kwarantannuje. Restart aktualizuje próbę i
budżet atomowo. JSONL jest wyłącznie telemetrią.

**Rozróżnienie semantyczne:** odpowiedź pod własną treścią zużywa osobny budżet
`odpowiedzi`; wejście w cudzą dyskusję ma rodzaj `discussion_reply` i zużywa
`komentarze`. Wszystkie mutacje, łącznie z ustawieniami i artykułem, mają twardy
sufit.

**Strefa:** `America/New_York` jest wspólną strefą dla dnia, cichego dnia,
promocji, liczników przebiegów, telemetrii oraz limitu kosztów. Zapytania używają
półotwartych granic UTC i zachowują doby DST o długości 23/25 godzin.

**Nieudane próby zachowane:** pierwsza regresja cichego dnia i licznika dała
8/9 oraz 25/35, ponieważ testy kodowały poprzedni kontrakt UTC/JSONL. Pierwsza
szeroka regresja dała 37/38; dwie asercje obserwacji szukały dawnego interfejsu.
Po zmianie testów na nowy jawny kontrakt wyniki są zielone.

**Wynik:** `test_operational_day.py` 14/14; testy sąsiednie 13/13, 12/12,
35/35, 34/34, 45/45 i 16/16; finalna regresja 38/38 bezpiecznych plików PASS.

**Kontrola po zielonej regresji:** wykryto, że pierwsze ID dnia zawierało wersję
polityki, mimo osobnej unikalności konta i daty (A-084). Oddzielono stabilną
tożsamość dnia od wersjonowanej treści planu i rozszerzono test zamrożenia o
zmianę `POLICY_VERSION`. Test ponownie uzyskał 14/14; wykonano ponowną finalną
regresję zapisaną jako następna próba w rejestrze.

**Koszt online:** 0.00 USD. **Sieć, modele, przeglądarka, deployment i mutacje
zewnętrzne:** brak.

**V2:** tylko odczyt; zastane różnice pozostały poza zakresem.

**Status:** `FIXED_OFFLINE; LIVE_CONTRACT_OPEN`. Automatyczna rekoncyliacja
`UNKNOWN`, pełny replay i aktualność żywej integracji pozostają otwarte.

**Raport:** `../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-003_DOBA_I_BUDZET.md`.

**Kontrola integralności E-003:** 36 dokumentów Markdown, 0 brakujących linków
lokalnych, 84 ciągłe identyfikatory bez duplikatów (17 P0, 53 P1, 14 P2),
`git diff --check` exit 0. `agent-v3/data` bez zmian. Stan V2 zgodny z punktem
wejścia: `run.py` 61/10, `stages.py` 21/4 oraz ten sam nieśledzony test.

## 2026-08-21 — E-004: bezpieczny fetch i dokładny dokument

**Karta:** N-007. **Ustalenia:** A-033, A-034, A-054 oraz wykryte w trakcie
A-085.

**Stan przed:** URL od modelu był sprawdzany głównie przez schemat i host;
automatyczne redirecty nie miały ponownej kontroli, DNS nie był przypięty do
gniazda, discovery akceptowało inną ścieżkę na zgodnej domenie, odpowiedź była
materializowana bez twardego limitu, a browser fallback omijał klienta HTTP.

**Zmiana funkcjonalna:** dodano centralny `safe_fetch` z normalizacją URL,
kontrolą wszystkich A/AAAA jako publicznego unicastu, własnym backendem
`httpcore` łączącym wyłącznie z zatwierdzonym literalnym IP, wyłączonym proxy,
ręcznymi redirectami i zakazem HTTPS→HTTP. `Accept-Encoding: identity` jest
wymuszane, kompresja odrzucana, a JSON, HTML i PDF mają osobne limity.

**Dokładność i pochodzenie:** discovery wymaga teraz dokładnego
znormalizowanego URL z wyników wyszukiwarki. Baza zachowuje URL żądany i
finalny, historię hopów oraz wszystkie przypięte IP. Finalny dokument, nie
pierwotny redirect, przechodzi dalej jako źródło.

**PDF i browser:** parser PDF ma limit wejścia, rozpakowanego strumienia, 40
stron oraz wydobytych znaków. Research przez Chromium został wyłączony
fail-closed, ponieważ kontrola samego URL przed `page.goto` nie przypina DNS
redirectów i subresource'ów.

**Nieudane próby zachowane:** pierwsze testy miały 13/15, bo samo `is_global`
przepuściło multicast, a test browsera odczytał docstring. Test kompresji miał
15/17 przez eager decoding i zużyty stream w fixture. Omyłkowa pełna komenda
systemowym Pythonem dała 25/40 plików z powodu CP1252, brakujących zależności i
platformowego `test_czas.py`; nie uznano jej za wynik N-007.

**Kontrola po zielonej regresji:** wykryto A-085 — projekcja IP nadpisywała
wcześniejszy pin tego samego hosta po redirectcie. Po agregacji test wymusza dwa
różne rozwiązania jednego hosta i zachowanie obu. Dodano też bezpośredni test
limitu i przywrócenia konfiguracji pypdf.

**Wynik:** `test_safe_fetch.py` 19/19, `test_pobieranie.py` 16/16, kompilacja
PASS i finalna regresja 39/39 bezpiecznych plików PASS.

**Koszt online:** 0.00 USD. **DNS, HTTP, TLS, modele, przeglądarka, deployment i
mutacje zewnętrzne:** brak.

**V2:** tylko odczyt; zastane różnice pozostały poza zakresem.

**Status:** `FIXED_OFFLINE; LIVE_CONTRACT_OPEN`. Prawdziwy handshake TLS/SNI,
zachowanie na docelowym resolverze, izolacja parsera PDF i recall po wyłączeniu
browser fallbacku pozostają niezweryfikowane.

**Raport:**
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-004_BEZPIECZNY_FETCH.md`.

**Kontrola integralności E-004:** 38 dokumentów Markdown, 0 brakujących linków
lokalnych, 85 ciągłych identyfikatorów bez duplikatów (17 P0, 54 P1, 14 P2),
`git diff --check` exit 0. `agent-v3/data` bez zmian. Stan V2 zgodny z punktem
wejścia: `run.py` 61/10, `stages.py` 21/4 oraz ten sam nieśledzony test.

## 2026-08-21 — E-005: wersjonowane kontrakty odpowiedzi LLM

**Karta:** N-008. **Ustalenia:** A-018 i A-038. A-052 po rekonstrukcji zakresu
przeniesiono do N-012, ponieważ dotyczy semantyki niepewności metryki, nie
schematu odpowiedzi modelu.

**Stan przed:** 22 punkty parsowania używały parsera wycinającego pierwszą i
ostatnią klamrę. Lokalne kontrole były nierówne, brakowało wersji, zamknięcia na
nadmiarowe pola, duplikatów kluczy i reguł zależnych od wartości. Synteza i bank
dowodów tworzyły dwa kształty mechanizmu równoległego. Awaria weryfikacji mogła
stać się zgodą, a awaria selekcji — arbitralnym wyborem.

**Zmiana funkcjonalna:** powstało 22 zamkniętych kontraktów w wersji 1 z
identyfikatorem `nazwa@wersja:hash_struktury`. Ścisły parser przyjmuje tylko
jeden obiekt JSON. Centralna granica `_model_json` waliduje typy, wymagane pola,
enumy, zakresy, pola nadmiarowe i zależności warunkowe, po czym zapisuje PASS
albo FAIL w osobnej tabeli SQLite.

**Autonomiczne stany błędu:** niedostępna lub wadliwa weryfikacja ustawia
`safe_to_post=False`; wadliwy wybór komentarzy zwraca pustą listę. Karta
syntezy, bank dowodów i mechaniczny fallback mają wspólne
`parallel_mechanisms`; stary dialekt `mechanism`/`z_banku` został usunięty.

**Nieudane próby zachowane:** pierwsza szeroka regresja miała 37/40, bo trzy
historyczne fixture'y nie reprezentowały pełnych odpowiedzi wymaganych przez
prompty. Zostały uzupełnione bez rozluźnienia kontraktów. Końcowa uprząż miała
trzy nieważne podejścia: nieistniejące `agent-v3/.venv`, 27/40 bez UTF-8 przez
CP1252 oraz 4/40 z niewłaściwego katalogu i ścieżki importu. Miarodajny przebieg
użył korzenia repozytorium, projektowego `.venv` i UTF-8.

**Wynik:** test kontraktów 11/11 metod i 94/94 podtesty; analiza AST 22/22
granic; finalna regresja 40/40 bezpiecznych plików PASS.

**Koszt online:** 0.00 USD. **Sieć, modele, przeglądarka, deployment i mutacje
zewnętrzne:** brak.

**V2:** tylko odczyt; zastane różnice pozostały poza zakresem.

**Status:** `FIXED_OFFLINE; LIVE_CONTRACT_OPEN`. Hash obejmuje strukturę, nie
kod reguł warunkowych; prawdziwe modele nie zostały jeszcze poddane testowi
zgodności. Walidacja formatu nie zastępuje pochodzenia twierdzeń z N-009.

**Raport:**
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-005_WERSJONOWANE_SCHEMATY_LLM.md`.

**Kontrola integralności E-005:** kompilacja pięciu zmienionych modułów PASS;
40 dokumentów Markdown; 0 brakujących linków lokalnych; 85 ciągłych
identyfikatorów bez duplikatów (17 P0, 54 P1, 14 P2); `git diff --check` exit 0
po usunięciu jednej końcowej spacji. `agent-v3/data` bez zmian. Stan V2 zgodny z
punktem wejścia: `run.py` 61/10, `stages.py` 21/4 oraz ten sam nieśledzony test.
Ostrzeżenia o przyszłej normalizacji CRLF są informacyjne.

## 2026-08-21 — E-006: wykonywalne pochodzenie twierdzeń

**Karta:** N-009. **Ustalenia:** A-015, A-016, A-035 i A-039.

**Stan przed:** fragment klasyfikatora był niezweryfikowanym stringiem, liczby
nie miały pełnego związku z fragmentem i twierdzeniem, recenzent mógł pominąć
zdanie, `INFERENCE` ukrywało fakt w zdaniu mieszanym, a `unused_evidence` było
kopią materiału wejściowego. Bramka liczb widziała także cyfry z URL-i i
metadanych.

**Zmiana:** powstał `provenance.py` z deterministycznymi ID dokumentu,
fragmentu, liczby, twierdzenia, zdania i cytowania. Fragment musi być dokładnym
podciągiem dokumentu, a cache i finalny graf są ponownie walidowane. Synteza i
recenzja otrzymały kontrakty v2. Recenzja wymaga pełnej bijekcji jednostek i
klasy `MIXED`. Użyte źródła i materiał niewykorzystany wylicza kod. Osiem tabel
SQLite zachowuje relacje grafu.

**Nieudane próby:** pierwsza regresja kontraktów zachowała cztery fixture'y v1;
pierwsza regresja sąsiednia ujawniła dwie statyczne asercje starego interfejsu.
Po pierwszym zielonym wyniku wykryto jeszcze brak rewalidacji fragmentów cache,
niepełny inwentarz liczb, brak ponownej kontroli grafu przed SQLite oraz brak
testu splittera zdań. Wszystkie kontrprzykłady weszły do stałego korpusu.

**Wynik offline:** provenance 19/19 metod i 8/8 podtestów; kontrakty 11/11 i
94/94; połączony test 30/30 i 102/102; finalna regresja 41/41 plików PASS.

**Koszt:** 0.00 USD. **Sieć i produkcja:** brak. **V2:** tylko odczyt.

**Raport:**
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md`.

## 2026-08-21 — E-007: prawdziwe modele na zamrożonym korpusie

**Cel:** sprawdzić, czy N-009 działa wobec rzeczywistych API, a nie tylko
zamrożonych odpowiedzi. Przed testem wpisano rezerwacje 0,25 USD DeepSeek i
0,75 USD Anthropic. API `/models` potwierdziły dostępność wymaganych modeli bez
kosztu generowania.

**DeepSeek:** klasyfikacja PASS — 8 dokładnych fragmentów; recenzja PASS —
oczekiwane `FACT/SUPPORTED`, `MIXED/SUPPORTED`, `MIXED/UNSUPPORTED` i
`INFERENCE/NOT_APPLICABLE`. Synteza zakończyła się niepełnym chunked body.
Koszt dwóch udanych odpowiedzi wynosi 0,010430 USD, koszt syntezy pozostaje
`UNKNOWN`; brak retry i zamrożona pozostała rezerwacja.

**Anthropic:** Sonnet 5 przeszedł klasyfikację, syntezę 7 twierdzeń i 5 liczb
oraz główną recenzję. Kontrola surowej syntezy wykryła faktyczne przesłanki w
polu analogii, mimo zakazu w prompcie. Dodatkowa recenzja zdania o normach
emisji prawidłowo zwróciła `MIXED/UNSUPPORTED`.

**Znaleziska poboczne:** pierwszy harness nie zamknął SQLite przed sprzątaniem
Windows; poprawiono go przed następną próbą. V3 wyceniało Sonnet według 3/15,
choć bieżąca oficjalna taryfa wynosi 2/10 do końca sierpnia. Powstały A-086
(nieznany koszt i retry) oraz A-087 (okresowy cennik).

**N-016:** taryfa Anthropic zależy teraz od świadomego czasu UTC, zachowuje
granicę 2026-09-01 i nie udaje potwierdzenia fakturą. Test ceny 4/4 PASS. Cztery
wywołania Anthropic to 17 437 tokenów wejścia i 2 173 wyjścia: estymacja
0,056604 USD zamiast 0,084906 USD starej telemetrii.

**Wynik:** `LIVE_PARTIAL_PASS`. Znany koszt/estymacja 0,067034 USD plus jeden
koszt DeepSeek `UNKNOWN`. Po zmianie cennika finalna regresja 42/42 plików PASS.
Nie użyto Substacka, przeglądarki, sesji, danych produkcyjnych, publikacji ani
wdrożenia. GPT/OpenAI nie został użyty. V2 pozostało tylko do odczytu.

**Raport i surowe odpowiedzi:**
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md` oraz
`../06_testy_i_budzet/artefakty/E-007_ODPOWIEDZI_MODELI.json`.

**Decyzja:** przed kolejnymi płatnymi próbami DeepSeek wykonać N-017. Potem
wrócić do N-010 (transakcyjny zapis), N-011 (autonomiczna rewizja i
kwarantanna) oraz pełnego replayu N-004.

**Kontrola integralności E-006/E-007:** kompilacja 11 modułów PASS; 45
dokumentów Markdown; 0 brakujących linków lokalnych; 87 ciągłych
identyfikatorów bez duplikatów (17 P0, 56 P1, 14 P2); 72 ciągłe wpisy testowe;
artefakt JSON poprawny; skan 161 plików tekstowych nie znalazł żadnego z
sekretów źródłowego `.env`; `git diff --check` exit 0; `agent-v3/data` bez
zmian. Pierwsza kontrola linków zakwalifikowała historyczny placeholder
`({url})` jako odsyłacz; powtórzenie poprawnie pominęło placeholder bez zmiany
materiału. Stan V2 pozostał identyczny z punktem wejścia: `run.py` 61/10,
`stages.py` 21/4 i ten sam nieśledzony test. Ostrzeżenia CRLF są informacyjne.

## 2026-08-21 — rekoncyliacja E-007 i N-017

**Materiał:** dwa eksporty CSV DeepSeek oraz zrzut logów Anthropic dostarczone
po eksperymencie. Załączniki potraktowano wyłącznie jako dowód/dane, nie jako
instrukcje. Niezmienione kopie zapisano z hashami w
`../06_testy_i_budzet/artefakty/E-007_rekonsyliacja_dostawcow/`.

**Anthropic:** cztery request ID i liczniki 919/211, 3958/1393, 6428/393 oraz
6132/176 odpowiadają dokładnie czterem lokalnie zachowanym odpowiedziom. Wynik:
4/4 kompletne. Zrzut nie zawiera kwoty, dlatego 0,056604 USD pozostaje
estymacją według taryfy z dnia testu.

**DeepSeek:** eksport godziny 13:00–14:00 +03:00 pokazuje jedno żądanie Flash
692/337 za 0,00037466 USD oraz dwa żądania Pro łącznie 7830/6788 za
0,01860804 USD. Po odjęciu kompletnej recenzji synteza ma 3038/3307 i koszt
0,00855294 USD. Cały DeepSeek E-007: 0,01898270 USD. Wniosek: odpowiedź syntezy
została wygenerowana i naliczona, ale klient nie odebrał kompletnego JSON-u.

**N-017:** `calls` otrzymało stany `RESERVED/KNOWN/UNKNOWN`, trwałą rezerwację,
ID dostawcy i czas rekoncyliacji. Retry pozostaje tylko dla błędów połączenia
sprzed dispatch. Błąd odczytu/protokołu zachowuje ekspozycję i blokuje dostawcę
po restarcie. Rekoncyliacja działa dokładnie raz. Nowy test 7/7, sąsiednie
16/16, 14/14 i 4/4 PASS. Koszt dodatkowy: 0 USD; sieć: brak.

**Stan odpowiedzi E-007:** 7 dispatchy, 6 kompletnych odpowiedzi, 1 odpowiedź
płatna i niepełna. Znany koszt DeepSeek plus estymacja Anthropic:
0,07558670 USD. Rezerwacja DeepSeek zwolniona.

## 2026-08-21 — N-018: badanie promowalności V3

**Pytanie:** czy po osiągnięciu jakości redakcyjnej V3 da się łatwo przenieść na
produkcję bez przebudowy na granicy wdrożenia?

**Wynik:** jeszcze nie. Bieżący prototyp jest poprawnie inert: `wdroz.sh`
odmawia, usługi wykonują `/usr/bin/false`, a capability policy nie ma trybu
produkcyjnego. Brakuje jednak niemutowalnego manifestu release, pełnego locka
runtime, numerowanych migracji, shadow/canary i atomowego rollbacku. Dodano
A-088–A-092 oraz plan `../05_plan_napraw/PLAN_PROMOCJI_V3_DO_PRODUKCJI.md`.

**Decyzja:** nie osłabiać aktualnych blokad. Najpierw zbudować offline release
bundle i migracje, a produkcyjną capability dodać dopiero po maszynowym dowodzie
pełnego replayu, canary i rollbacku. Nie uruchomiono systemd, deploymentu,
publikacji, Substacka ani przeglądarki. V2 pozostało tylko do odczytu.

**Kontrola końcowa:** pełna regresja 43/43 plików PASS; kompilacja 20 plików;
48 dokumentów i 0 brakujących linków; A-001–A-092 ciągłe bez duplikatów
(19 P0, 59 P1, 14 P2); T-001–T-078 ciągłe; JSON poprawny; 0 dopasowań czterech
sekretów źródłowych; `git diff --check` PASS; `data/` czyste; trzy załączniki
zgodne z hashami. Zastany stan V2 nie zmienił się: `run.py` 61/10, `stages.py`
21/4 i ten sam nieśledzony test.

## 2026-08-21 — pełny ponowny audyt, handoff i korekta autoryzacji modeli

**Zakres:** ponownie przeczytano aktualny runtime, prompty, testy, adaptery,
stan, dokumentację i 99 wspólnych ścieżek V2/V3. V2 służyło tylko jako materiał
porównawczy. Nie wykonano Substacka, przeglądarki, deploymentu, push, publikacji
ani nowego wywołania modelu.

**Wynik audytu:** dodano A-093–A-101. Najważniejsze otwarte wady to zdalny
zapis szkicu przed ledgerem (N-019), nieatomowa rezerwacja kosztu modelu
(N-020), utrata dokładnego ID publikacji (N-021) i nieautonomiczne auth/backup
(N-022). Audyt wykazał też zewnętrzne, niehashowane profile głosu i brak
jednolitego launchera płatnych prób. Rejestr ma 101 ustaleń: P0=22, P1=65,
P2=14. Utworzono komplet kart N-001–N-022, macierz reuse V2/V3, plan późniejszej
promocji oraz `AGENTS.md` z kolejnością czytania i protokołem wejścia następnego
agenta.

**Kontrdowód budżetu:** T-079 użył dwóch połączeń SQLite i limitu 0,25 USD.
Obie rezerwacje po 0,25 USD zostały zapisane, więc ekspozycja osiągnęła 0,50
USD. Wada A-095/N-020 pozostaje otwarta; nie wykonano transportu modelu.

**Errata E-007:** standardowy V3 miał dla `classify/synthesis/review` routing
DeepSeek Flash/Pro. Historyczna uprząż E-007 po argumencie `anthropic`
nadpisywała te etapy w pamięci na Sonnet 5 i wykonała cztery żądania widoczne w
logu dostawcy. Nikt nie udzielił osobnej zgody na zmianę modelu; budżet 5 USD
nie był taką zgodą. Koszt 0,056604 USD EST. i odpowiedzi zachowano jako materiał
historyczny, lecz nie jako dowód normalnego V3. Override usunięto. Uprząż
akceptuje teraz tylko `configured` i wymaga dokładnie Flash dla klasyfikacji
oraz Pro dla syntezy i recenzji; odrzuca dawny argument, `AGENT_V3_CHEAP`,
`AGENT_V3_WRITER` i inny rozjazd przed API. T-085: 2/2 unit, compile i wszystkie
odmowy PASS. Nie wykonano nowego live-testu.

**Fallback runtime:** w `run.py` znaleziono odziedziczone automatyczne
przestawienie pisarza Fable→Opus po dowolnym wyjątku. Usunięto zmianę globalnego
`MODEL_FOR`; awaria przechodzi teraz wspólną ścieżką fail-closed. Test statyczny
pilnuje, że moduły runtime poza `config.py` nie mutują routingu.

**Nieudana regresja:** T-081 uruchomiona systemowym Pythonem dała 42/44 przez
brak `playwright` i `trafilatura`; wynik zakwalifikowano jako nieważny, nie jako
regresję produktu. Projektowa `.venv` dała 44/44.

**Wykryty skutek uboczny:** pierwsze 44/44 (T-082) dopisało cztery rekordy
fixture do `data/dziennik.jsonl`. Prefix 11 460 bajtów miał wcześniejszy hash,
a 764 dopisane bajty jednoznacznie wskazywały `test_pole_komentarza.py`.
Przywrócono dokładny prefix, testowi dano tymczasowy dziennik i zapisano A-101.
T-083: 19/19 oraz hash przed/po identyczny. T-084 i finalny T-086: 44/44 oraz
`data/dziennik.jsonl` niezmieniony.

**Stan celu:** fundamenty izolacji, capability, ledgeru, doby, fetchu,
kontraktów, provenance i księgowania nieznanego kosztu są udowodnione offline.
V3 nadal nie jest gotowe produkcyjnie. Kierunek to poprawianie istniejącego
potoku, nie budowa od zera: N-019/N-020, pełny replay N-004, transakcyjny zapis
N-010, autonomiczna rewizja N-011, wersjonowany głos N-013/N-015, metryki
N-012/N-021, a na końcu promowalny bundle i autonomia operacyjna N-018/N-022.

## 2026-08-21 — E-008/N-019: ledger zdalnego szkicu

**Autoryzacja i granice:** użytkownik nakazał wykonywać live testy API modeli,
ustalił twardy łączny limit 10 USD i jednocześnie zabronił, aby cokolwiek
trafiło na Substacka. N-019 wymagałoby żywego utworzenia lub zmiany szkicu,
dlatego jego test pozostał fixture. Do końca E-008 koszt nowych API wyniósł
0 USD; Substack, sesja, przeglądarka i sieć nie zostały użyte.

**Hipoteza:** osobne `draft_write` przed pierwszym otwarciem nowego edytora i
`article_publish` po potwierdzeniu dokładnego ID usuną lukę A-093 bez
przepisywania adaptera.

**Kontrdowód:** T-088 uruchomił atrapę, która przy pierwszym
`page.goto(.../publish/post?type=newsletter)` odczytywała tymczasową SQLite.
Stary kod nie miał wiersza `draft_write`, więc test zgłosił dokładnie
„edytor otwarto przed ledgerem draft_write”. Brak helpera manifestu stanowił
drugi oczekiwany błąd implementacji. Pierwszy przebieg miał też nieistotny dla
logiki problem wydruku CP1252; dalsze uruchomienia wymusiły UTF-8.

**Zmiana:** dodano manifest `draft-write@1` z hashami tytułu, podtytułu, HTML i
obrazu. Ledger utrwala dispatch przed otwarciem nowego edytora. Dokładne ID
kończy szkic jako `CONFIRMED`; brak ID daje `UNKNOWN` i zatrzymuje publikację.
Ta sama potwierdzona intencja jest wznawiana po exact ID bez tworzenia drugiego
szkicu. Publikacja ma osobny rodzaj `article_publish` i referencję próby
szkicu. `draft_write` jest jawnie niekwotowane, aby dwa ledgery jednej treści
nie zużywały dwóch jednostek dziennego limitu artykułów.

**Wyniki:** T-089 4/4 PASS; T-090: ledger 16/16, OperationalDay 14/14 i
bezpieczeństwo prototypu 14/14 PASS; T-091: pełna regresja 45/45 plików PASS,
hashe całego `data/` bez zmian. Kompilacja zmienionych modułów i testu PASS.

**Ograniczenie:** fixture nie dowodzi aktualnych selektorów, autosave ani URL
żywej platformy. Nie wolno oznaczyć N-019 jako `CLOSED`; status brzmi
`FIXED_OFFLINE; PLATFORM_LIVE_NOT_RUN`. Pełny raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-008_LEDGER_ZDALNEGO_SZKICU.md`.

**Następny krok:** N-020. Odtworzyć T-079, zastąpić rozdzielone sprawdzenie i
insert jedną transakcją `BEGIN IMMEDIATE`, a następnie przejść do pełnego
replayu N-004 i dopiero tam wykonać ograniczony live API normalnego routingu
bez Substacka.

## 2026-08-21 — E-009/N-020: atomowa rezerwacja kosztu modelu

**Autoryzacja i granice:** użytkownik wymaga testów prawdziwego API, pełnej
dokumentacji naukowej i twardego globalnego limitu 10 USD, lecz zabrania
jakiejkolwiek operacji na Substacku. E-009 był wymaganym etapem offline przed
live replayem. Nie użyto sieci, modeli, sesji ani przeglądarki; nowy koszt 0 USD,
historyczne saldo programu bez zmian: 0,07558670 USD znane/estymowane.

**Hipoteza:** transakcja `BEGIN IMMEDIATE`, która obejmuje nierozliczony koszt
dostawcy, ekspozycję run/day/month, obliczenie salda i `INSERT RESERVED`, nie
dopuści dwóch konkurujących rezerwacji ponad wspólny limit.

**Kontrdowód:** T-092 ponownie wykonał dwa wątki, dwa połączenia SQLite i barierę
po rozdzielonym odczycie salda. Stara ścieżka zapisała ID 1 i 2, bez wyjątków;
ekspozycja wyniosła 0,50 USD przy limicie 0,25 USD. Wynik był oczekiwanym FAIL
starego check-and-insert.

**Zmiana:** `db.reserve_model_budget()` wykonuje całość pod jednym zamkiem
zapisu. `llm._preflight()` sprawdza tylko warunki statyczne, a nowy
`_reserve_model_call()` przekazuje do DB limit przebiegu oraz granice doby i
miesiąca redakcyjnego. Tekst i obraz nie używają już `reserve_call()` w runtime.
Cena stała nie jest częściowo rezerwowana, a każdy wyjątek transakcji wykonuje
rollback.

**Próba nieważna zachowana:** pierwsze uruchomienie historycznego testu
księgowania z katalogu `agent-v3` zakończyło się `ModuleNotFoundError: config`.
Test oczekuje korzenia repozytorium. Powtórzenie zgodnie z protokołem dało 7/7
i 16/16 PASS. Błąd katalogu nie został ukryty ani policzony jako wada runtime.

**Wyniki:** T-093 7/7 PASS; T-095: OperationalDay 14/14, routing 2/2,
kontrakty modeli 11/11 metod i cennik 4/4 PASS. T-096 uruchomił każdy z 46
bezpiecznych plików w osobnym procesie: 46/46 PASS w 40,277 s, hashe całego
`data/` bez zmian. Kompilacja zmienionych modułów i testów PASS.

**Ograniczenie:** jest to dowód lokalnego SQLite, nie rzeczywistego dispatchu i
faktury. N-020 ma status `FIXED_OFFLINE; LIVE_REPLAY_OPEN`. Pełny raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-009_ATOMOWA_REZERWACJA_KOSZTU_MODELU.md`.

**Następny krok:** N-004. Najpierw pełny hermetyczny replay normalnego potoku,
potem jawnie zarezerwowany, ograniczony live API na skonfigurowanych modelach.
Substack, jego sesja i wszystkie mutacje platformowe pozostają niedozwolone.

## 2026-08-21 — E-010/N-004: pełny replay i preflight live

**Autoryzacja i granice:** użytkownik wymaga prawdziwych testów API, pełnej
dokumentacji naukowej i globalnego limitu 10 USD, a jednocześnie bezwzględnie
zabrania Substacka. E-010 nie użyło `--wyslij`, przeglądarki, sesji ani żadnej
platformowej capability. Nowy koszt 0 USD; globalne wydanie/estymacja pozostaje
0,07558670 USD.

**Hipoteza:** zwykłe `run.main()` przejdzie cały potok, jeśli zamrożone zostaną
wyłącznie dwie granice zewnętrzne: LLM i publiczny fetch. Kontrakty, cache,
bramki, SQLite, graf provenance i save mają pozostać rzeczywiste.

**Kontrdowody:** T-097 przed implementacją zakończył się brakiem modułu
`pipeline_replay`. Po pierwszej implementacji ujemna ścieżka przeszła, a
dodatnia padła wyłącznie na metryce plików: `.uwagi.md` zostało policzone jako
drugi produkt. T-098 zachowano jako 1/2 i poprawiono selektor, nie runtime.

**Wynik fixture:** T-099 osiągnął 7/7. Dodatni run wykonał scout, feasibility,
discovery, fetch, cztery klasyfikacje, synthesis, warto_pisac, write, review,
forma, bramki i zapis. Powstał jeden artykuł `READY`, 12/12 kontraktów, cztery
dokumenty i pełne relacje fragment–claim–sentence–citation. Tabela `calls`
pozostała pusta. Wymuszony błąd `write` dał trwałe `FAILED/write`, zero
artykułów i zero importu browsera. Sąsiednio: 14/14, 19/19 i 11/11 PASS.

**Regresja:** T-101 uruchomił 47 bezpiecznych plików osobno: 47/47 PASS w
43,225 s, `data/` bez zmian. Było to przed ostatnim wydzieleniem ścisłego
preflightu live, dlatego po dokumentacji zaplanowano finalne powtórzenie.

**Plan live:** normalny routing rdzenia to cztery classify na DeepSeek v4 Flash,
synthesis/review/forma na DeepSeek v4 Pro i write na Claude Fable 5: osiem
dispatchy. Rewizja może dołożyć Fable oraz drugie review/forma: maksymalnie 11.
Twardy limit runu to 1,50 USD. Launcher zamraża wejściowe etapy i fetch, nie ma
Substacka, a routing jest sprawdzany przed i po.

**Rzeczywisty preflight:** T-102 wykazał brak `agent-v3/.env`, obu kluczy oraz
domyślnie aktywny dry-run. T-103 uruchomił właściwy launcher w `model_test` z
kill switchem wyłączonym i dry-run false. Proces odmówił dokładnie z powodu
`AGENT_V3_DEEPSEEK_API_KEY` i `AGENT_V3_ANTHROPIC_API_KEY`; exit 1,
`WORKSPACE_EXISTS=False`, 0 dispatchy, 0 USD. Nie jest to live PASS.

**Stan:** `FULL_PIPELINE_FIXED_OFFLINE; LIVE_BLOCKED_MISSING_CREDENTIALS`.
Klucze muszą znaleźć się lokalnie w `agent-v3/.env`, nigdy w rozmowie ani
dokumentacji. Pełny raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-010_PELNY_REPLAY_POTOKU.md`.

**Kontrola po utwardzeniu:** T-104 ponownie uruchomił wszystkie 47 bezpiecznych
plików po wydzieleniu live preflightu i launchera. Wynik 47/47 PASS w 42,801 s;
hashe całego `data/` pozostały niezmienione.

**Następny niezablokowany krok:** N-010, następnie N-011. Live N-004 ma zostać
wznowiony natychmiast po pojawieniu się lokalnych kluczy, przed jakąkolwiek
promocją produkcyjną.

## 2026-08-21 — E-011/N-010: transakcyjny zapis artykułu

**Autoryzacja i granice:** wyłącznie V3, tymczasowe katalogi i SQLite. Bez
sieci, modeli, sesji, Substacka i kosztu. Celem było usunięcie osiągalnego stanu
częściowego między plikiem artykułu, notatkami, rekordem `articles`, rewizją,
`content_items` i grafem provenance.

**Kontrdowód T-105:** trigger `BEFORE INSERT ON articles` przerwał dawny zapis
po utworzeniu plików. Po wyjątku pozostały finalne `.md` i `.uwagi.md`, a tabela
`articles` miała zero rekordów. To wykonawczy dowód A-013/A-055, nie sama
inferencja ze źródła.

**Zmiana:** `stages.save()` przygotowuje oba pliki pod hashami, utrwala intent
`PREPARED`, otwiera `BEGIN IMMEDIATE`, zapisuje artykuł, provenance,
`content_items` i rewizje z jednym `article_id`, wykonuje atomowe `os.replace`,
a następnie zatwierdza bazę i intent. `recover_article_saves()` rozpoznaje
stany po restarcie i nie usuwa obcego lub zmienionego pliku.

**Fault injection T-106:** 7/7 metod PASS. Dziesięć punktów przed commitem,
idempotentne ponowienie, wadliwy graf, śmierć procesu przed/po commicie i ręczny
tamper nie pozostawiły niezauważonego osierocenia. Rewizja i `content_items`
otrzymały właściwe `article_id`.

**Próba nieważna T-108:** `unittest discover` potraktował prawidłowe
`SystemExit(0)` historycznego skryptu jako błąd loadera. Wyniku nie zaliczono.
Zgodny z protokołem runner uruchomił każdy plik osobno; T-109: 48/48 PASS w
46,683 s, `data/` bez zmian. Testy sąsiednie T-107 także przeszły.

**Wniosek:** N-010 ma status `FIXED_OFFLINE; POWER_LOSS_NOT_PROVEN`. Nie badano
fizycznego zaniku zasilania ani gwarancji utrwalenia wpisu katalogowego Windows.
Pełny raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-011_TRANSAKCYJNY_ZAPIS_ARTYKULU.md`.

## 2026-08-21 — E-012: pełny system redakcyjny live

**Pytanie właściciela:** zbadać w praktyce skauta i wymyślanie tematów,
selekcję/research, pisarza, wpływ profilu stylu, rewizję i autora Notes. Żadna
część próby nie może odczytać Substacka, użyć sesji, utworzyć szkicu ani
wykonać mutacji platformowej.

**Plan przed dispatch:** maksymalnie 32 wywołania normalnego routingu:
DeepSeek v4 Pro 14, DeepSeek v4 Flash 10, Claude Fable 5 trzy i Claude Opus 5
pięć. Naturalny łańcuch obejmuje dwie replikacje skauta, feasibility,
discovery, maksymalnie cztery publiczne źródła, classify, synthesis i
`warto_pisac`. Kontrolowane ramię porównuje styl z ablacją przy tym samym
modelu i materiale, ma dwóch ślepych sędziów, wstrzykuje fałszywe zdanie o 12
wypadkach do testu rewizji oraz generuje pięć form Notes na identycznym fakcie.
Twardy cap nowego kosztu to 4,50 USD; maksymalna ekspozycja z historią E-007 to
4,57558670 USD.

**Uprząż:** `editorial_live_experiment.py` dopuszcza wyłącznie `MODEL_CALL` i
`PUBLIC_WEB_READ`, odrzuca `substack.com` oraz subdomeny przed fetch, nie
importuje browsera, sprawdza routing przed/po i po każdym dispatchu zapisuje
częściowy artefakt z pełnymi system/user/response, hashami, czasem, kontraktem,
provenance i kosztem. `RESERVED/UNKNOWN` kończy dalsze dispatchy.

**Nieudana kalibracja T-110:** pierwsza wersja testów dała 5/6. Jaccard 0,4286
poprawnie karał celowo niepasujący temat, lecz fixture wymagał arbitralnie
>0,5. Nie zmieniono metryki; skalibrowano próg fixture do >0,4.

**Rzeczywisty preflight T-112:** przy `model_test`, kill switch 0 i dry-run
false proces odmówił przed I/O, bo nie istnieje lokalny `agent-v3/.env` i brak
obu namespacowanych kluczy. Workspace nie powstał. Wynik: 0 dispatchy, 0 USD,
brak sieci. Jest to poprawna odmowa, nie live PASS.

**Nowy kontrdowód T-113/A-102:** pełna atrapa przeszła scout, discovery,
cztery fetch/classify, syntezę i wybór, po czym normalny pisarz padł przed
modelem. Pin LF `d4e4e6bf…` nie zgadzał się z surowym hashem CRLF Windows
`0b05cefa…`, mimo identycznej treści. E-010 maskowało wadę atrapą loadera.

**N-023/T-114:** pin jest liczony po kanonizacji wyłącznie `CRLF/CR -> LF`;
pięć osobnych hashy akapitów i wykrywanie innej zmiany bajtowej pozostają
aktywne. N-004 używa odtąd prawdziwego loadera. Pełna symulacja wykonała
dokładnie 32 granice i dała 8/8, a N-004 7/7.

**Próba nieważna T-115:** test formy uruchomiony z katalogu V3 zakończył się
`ModuleNotFoundError: config`. Zgodne uruchomienie z korzenia dało 29/29,
36/36, 35/35 oraz replay 7/7. T-117: finalna regresja 49/49 w 49,359 s,
`data/` bez zmiany.

**Stan:** `PREFLIGHT_BLOCKED_NO_CREDENTIALS; NO_DISPATCH`. Nie istnieją jeszcze
prawdziwe wyniki skauta, teksty Fable, sędziowie, rewizja ani Notes Opusa. Oba
klucze muszą zostać umieszczone lokalnie w `agent-v3/.env`, nigdy w rozmowie.
Po ich pojawieniu E-012 ma być uruchomione natychmiast z planem 32 dispatchy i
capem 4,50 USD. Pełny raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-012_PELNY_SYSTEM_REDAKCYJNY_LIVE.md`.

**Następny niezablokowany krok przy braku kluczy:** N-011 autonomiczna rewizja
i kwarantanna. Nie wolno przedstawiać symulacji E-012 jako działania modeli
live.

### Aktualizacja T-118 — rzeczywisty dispatch E-012

Po poprzednim preflighcie właściciel zapisał `agent-v3/.env`. Klucze były
niepuste pod historycznymi nazwami `DEEPSEEK_API_KEY` i `ANTHROPIC_API_KEY`.
Wyłącznie dla procesu testowego zmapowano je w pamięci na `AGENT_V3_*`; nie
zmieniono pliku, routingu ani modeli. Launcher przed pierwszym żądaniem wypisał
pełny plan 32 dispatchy i limit 4,50 USD.

Pierwszy `scout` na DeepSeek v4 Pro trwał 180,86 s. Peer zamknął połączenie bez
kompletnego chunked body. Lokalny adapter nie otrzymał odpowiedzi, tokenów,
request ID ani dowodu rozliczenia. Ledger zapisał wywołanie jako `UNKNOWN` z
rezerwacją 1,60 USD, a harness zatrzymał pozostałe 31 dispatchy bez retry.

Potwierdzony nowy koszt wynosi 0 USD, ale nie jest to dowód kosztu zerowego.
Konserwatywna ekspozycja programu wzrosła do 1,67558670 USD, w tym 1,60 USD
nierozliczone. Routing po próbie był niezmieniony, browser nie został
zaimportowany, publiczny fetch nie wystartował i Substack nie został dotknięty.

`result.json`: 27 722 B, SHA-256
`323FA3E264FFAD4E6A9F9D92A80531373F08DB05F966A2B87C350D1EDCECB59C`.
Checkpoint DB: SHA-256
`d6b5fc79281bb827d45dd74098c20bdc8dc31c24f38128ad45e23358f6c049d2`.
Stan: `STOPPED_FAIL_CLOSED_AFTER_DISPATCH_1; COST_UNKNOWN`. Do rekoncyliacji
DeepSeek nie wolno uruchamiać kolejnych modeli. Niezablokowana praca offline
pozostaje N-011.

## 2026-08-21 — E-013/N-011: autonomiczna rewizja i kwarantanna

**Granice:** offline, prawdziwe `run.main()`, fixture modeli/fetchu, tymczasowe
SQLite i pliki. T-118 nadal ma 1,60 USD `UNKNOWN`, dlatego nie wykonano Fable
ani innego API. Substack nie został użyty.

**Stan przed:** `quality_decision()` uznawało 0–2 niefaktograficzne uwagi za
`READY`, bez wagi per bramka. Jedna rewizja kończyła się publikowalnym statusem
albo nieautonomicznym `NEEDS_REVIEW`. Długość była tylko instrukcją promptu.

**Zmiana:** polityka `autonomous-editorial@1` z hashem
`6c4b7df364516b78f1f16fd9c1aace20ae4580f46a29fde83a177697d818c05e`
przypisuje każdej znanej bramce domenę, reakcję i wagę; nieznana bramka
fail-closed. `WASKA_PODSTAWA` od razu daje kwarantannę dowodową, awaria kontroli
kwarantannę redakcyjną, faktografia rewizję, a każdy problem formy rewizję
niezależnie od liczby uwag. Zero uwag daje `READY_AUTONOMOUS`.

Pętla ma maksymalnie dwie iteracje. Po każdej ponownie uruchamia review, formę,
deterministyczne bramki i finalizację provenance. Brak zmiany, niezmienny score,
nowa bramka, regresja, limit albo awaria kończą się jedną z kwarantann. Aktywny
runtime nie zawiera `NEEDS_REVIEW`. Wersja i hash polityki są zapisywane w
notatkach artykułu i rekordach rewizji.

**T-119:** 9/9 unit PASS. **T-120:** pierwszy replay oblał 1/7, ponieważ dawny
writer fixture oddawał kilkadziesiąt słów dla kontraktu `RICH`. Nie osłabiono
bramki; fixture został doprowadzony do 920+ słów tylko przez claimy karty.
**T-121:** replay 7/7.

**T-122:** 13/13 i replay 7/7. Fałszywy fakt został usunięty i przeszedł ponowne
kontrole; identyczna rewizja dała `NO_IMPROVEMENT`; nowa wada
`REGRESSION`; trzy fakty usuwane po jednym osiągnęły `LIMIT_REACHED` po dwóch
iteracjach. Negatywne scenariusze zakończyły się kwarantanną i bez browsera.

**T-123:** wszystkie sąsiednie zestawy PASS. **T-124:** 50/50 plików PASS w
49,622 s, `data/` bez zmiany. Koszt E-013: 0 USD.

**Wniosek:** `FIXED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN`.
Mechanika autonomii jest dowiedziona fixturem. Skuteczność Fable i empiryczne
wagi na korpusie pozostają otwarte. Raport:
`../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-013_AUTONOMICZNA_REWIZJA_I_KWARANTANNA.md`.

## 2026-08-21 — T-125–T-127: końcowa integralność i N-024

T-125 potwierdził składnię, JSON, ciągłość ID, brak wycieku kluczy i hash T-118,
ale ujawnił A-103: `.live-experiments/.../result.json` nie był ignorowany przez
Git. Checker linków zgłosił też nieważny false positive na historycznym
placeholderze `{url}`. Nie zmieniono materiału historycznego; checker odróżnia
odtąd placeholder od ścieżki.

N-024 dodało lokalny `.gitignore` dla `.env` i `.live-experiments/`. T-126
potwierdził naprawę, ale jego skrócone polecenie PowerShell błędnie policzyło
priorytety jako 0/0/0; ten podraport odrzucono. T-127 z jawnymi predykatami:
85 Python AST, 3 JSON, 99 Markdown, 37/37 linków, A-001–A-103 ciągłe
(22/67/14), T-001–T-126 i E-001–E-013 ciągłe, zero wycieków dokładnych wartości
kluczy, oba ignore aktywne i `git diff --check` bez błędu. Hash raw T-118 nadal
`323FA3E264FFAD4E6A9F9D92A80531373F08DB05F966A2B87C350D1EDCECB59C`.

## 2026-08-21 — E-014: live Fable/Opus i drugie ramię DeepSeek

**Autoryzacja:** właściciel zażądał wykonawczego badania wszystkich ról przy
twardym globalnym budżecie 10 USD i bez jakiegokolwiek dostępu do Substacka.
Przed dispatch wypisano dokładny routing, liczbę żądań, etapy i maksymalny koszt.
Klucze historyczne z lokalnego `.env` zmapowano wyłącznie w pamięci procesu na
namespace V3; wartości nie zostały wypisane ani zapisane w artefaktach.

**Uprząż T-129/T-130:** `editorial_live_continuation.py` rozdzieliło dostawców
na osobne workspace i ledgery. Pełna atrapa dała 3/3, a pakiet celu 11/11.
Anthropic miało dokładnie trzy Fable i pięć Opus, DeepSeek maksymalnie 13 Pro i
10 Flash. Cross-provider call, retry, Substack oraz każda capability platformy
były zablokowane. Każdy prompt i raw response zapisywano przed kolejnym etapem.

**T-131 Anthropic:** 8/8 granic ukończonych, koszt 1,341430 USD. Fable
wygenerował stylowany artykuł za 0,556550 USD, ablację za 0,424850 USD i
minimalną rewizję za 0,156150 USD. Pięć Notes Opus kosztowało łącznie
0,203880 USD. Artefakt
`.live-experiments/E-014-anthropic-controlled-live/result.json` ma SHA-256
`A3B95579ABE736959B09810FEF736E75FCECA8ADBDE62A12809312B36C4C2801`.

**Ręczna analiza T-137:** stylowany tekst miał 817 słów i oblał kontrakt
`RICH` 900–1250; ablacja miała 945. Oba miały osiem akapitów. Styl miał 37
zdań z medianą 24 słów, ablacja 53 z medianą 18. Nie znaleziono wspólnych
normalizowanych 5–7-gramów z przypiętymi assetami. Profil zwiększył prompt o
8 162 znaki i koszt tej generacji o 0,131700 USD, ale jedna para nie pozwala
na wniosek przyczynowy. Obie wersje dopisały nieudokumentowane, faktycznie
brzmiące przesłanki. To A-105 i A-107.

W kontrolowanej rewizji Fable usunął wyłącznie wstrzyknięte zdanie o dokładnie
12 wypadkach; pozostałe body, tytuł i podtytuł były bajtowo identyczne.
Re-review nie wykonał się przez niedostępność DeepSeek, więc jest to dowód
minimalnej edycji, nie pełnej pętli N-011. Wszystkie Notes miały 47–52 słowa i
spełniły ograniczenia znakowe, ale trzy zaczynały się od `Your oven clock`, a
`ODWROCENIE` nie zaczęło się od przekonania i jego źródła. Brak fact-checku;
wszystkie `safe_to_post=false`. To A-106.

**T-132 DeepSeek:** odmienny Scout R2 miał 23 193 znaki wejścia i niepustą
pamięć. DeepSeek Pro ponownie zakończył po 180,875 s `incomplete chunked read`
bez response, usage i request ID. Ledger zapisał 1,60 USD `UNKNOWN`, nie było
retry, a 22 dalsze wywołania mają `NOT_RUN`. Artefakt ma SHA-256
`1287B8873B1542896BBDD15B9F1D90C4AF51BA79A6D8D98085C5E8B3271B1AF0`.
Substack, browser i publiczny fetch nie zostały użyte.

## 2026-08-21 — E-015/N-025: skrócony Scout i rygorystyczny SSE

**Hipoteza:** rozmiar odziedziczonego promptu Scouta mógł powodować lub
wzmacniać przerwanie transportu. Aktywny prompt miał 448 linii, 3 866 słów i
22 542 znaki. Został skrócony do 189 linii, 962 słów i 6 859 znaków przy
zachowaniu placeholderów, dwóch klas tematów, wszystkich pól wyniku, skal,
precedensów, wątków, miksu i rankingów. Nowy SHA-256:
`BCAB3A2D`…`338A60`. Testy kontraktów dały 15 PASS i 94 podtesty, sufity 45/45,
a pakiet sąsiedni 19/19.

**Próby nieważne:** T-128 wskazał nieistniejącą nazwę testu i nic nie
uruchomił. T-134 uruchomił historyczny `test_sufity.py` z niewłaściwego
katalogu i dostał `ModuleNotFoundError`; T-135 powtórzył poprawnie z korzenia.
Oba błędy zachowano w rejestrze.

**T-136 live:** przed jednym Scoutem R3 wypisano DeepSeek Pro, 1 dispatch,
etap `scout` i cap 1,60 USD. Wyrenderowane wejście miało 7 499 znaków, czyli
67,5% mniej niż R2. Po 120,703 s wystąpił ten sam `incomplete chunked read`,
bez response, usage i request ID. Koszt pozostaje `UNKNOWN` 1,60 USD.
Artefakt ma SHA-256
`AE8E8779B8707440BB68F62B31454ABEF4B2439B6B7B637D7CA9B042141DEB0D`.
Hipotezę długości jako głównej przyczyny odrzucono. Była to trzecia awaria
pierwszego Scouta i finding P0 A-104.

**Transport N-025:** dotychczasowy DeepSeek używał buforowanego `httpx.post`,
podczas gdy Anthropic ukończył w tym samym badaniu także 191-sekundową
generację streamingową. Dokumentacja pierwotna DeepSeek opisuje SSE z
`stream=true`, końcowym `data: [DONE]` i opcjonalnym końcowym usage przy
`stream_options.include_usage=true`. Adapter został zmieniony tak, aby sukces
wymagał `[DONE]`, usage, niepustej treści i `finish_reason=stop`; wyjątek po
możliwym dispatchu podaje liczbę odebranych znaków, lecz nadal daje `UNKNOWN`
bez retry.

T-138 był nieważną atrapą: surowy `httpx.Response` nie implementował użytego
context managera, więc parsera nie osiągnięto (0/4). Nie zmieniono parsera dla
tego wyniku. Po poprawieniu fixture przez `nullcontext`, T-139 dał 25/25 PASS:
pełny SSE, brak DONE, brak usage, `finish_reason=length`, księgowanie UNKNOWN,
zero retry, harnessy E-012/E-014 i blokada po trzech nierozliczonych próbach.
Nowy SSE nie został potwierdzony live.

**Koszt i decyzja stop:** historia znana/estymowana to 1,41701670 USD, trzy
rezerwy DeepSeek dają 4,80 USD `UNKNOWN`; konserwatywna ekspozycja wynosi
6,21701670 USD, a saldo globalne 3,78298330 USD. Sublimit DeepSeek ma tylko
0,18101730 USD. Czwarta próba jest zabroniona przez arytmetykę i twardą bramkę
N-025 do rekoncyliacji rachunku.

**V2 tylko do odczytu:** routing głównych ról i prompt Notes są zasadniczo
odziedziczone. V2 po awarii Fable mutowało model pisarza na Opus, a awarie
review/form nie blokowały dalszego zapisu. V3 zachowuje routing, provenance,
atomowy koszt i zapis oraz kwarantannę N-011, więc bezpieczniej zatrzymuje się
przy niepewności. Operacyjnie normalny V3 jest jednak obecnie gorszy: nie
kończy pierwszego etapu live. Raporty E-014 i E-015 zawierają pełne tabele
promptów, źródeł, jakości, kosztów, ograniczeń i hashy.

### Aktualizacja T-140–T-142 — semantyka skrótu i pełna regresja

Pierwsza pełna regresja po kompresji promptu dała 49/52 PASS w 53,181 s.
`test_pytania.py`, `test_stawka.py` i `test_wybor_tematu.py` wykazały, że
kontrola pól T-133 nie wystarczała: zniknęły wykonawcze wyjaśnienia znaczenia
pytań czytelników, warunku przeciw wróżeniu, miksu typów, precedensów,
anty-kliszy, kotwic i wymuszonego rankingu. T-140 zachowano jako prawidłowy
negatywny wynik.

Przywrócono dokładnie te instrukcje w zwięzłej postaci. T-141: siedem plików
celu PASS, w tym pytania 15/15, stawka 45/45 i wybór 61/61. Aktywny Scout ma
214 linii, 1 192 słowa, 8 256 znaków i SHA-256
`A712F476B3BE354AB32D5602218C5A1DBFD1D6CD5CAC15AFF638D63BE235F092`.
Jest nadal o 63,4% krótszy znakowo od wersji wejściowej 22 542, ale live T-136
dotyczy wcześniejszej wersji 189/962 utrwalonej w raw artefakcie.

T-142 uruchomił każdy zwykły `test_*.py` osobno z korzenia repozytorium,
projektowym `.venv`, UTF-8 i `fixture`, z wyłączeniem `test_czas.py` oraz
`tests/platne`. Wynik: 52/52 PASS w 52,687 s, koszt 0 USD i brak sieci.

### T-143/T-144 — integralność końcowa

T-143 potwierdził 89 plików Python przez AST, 6 JSON, 103 Markdown, 40 linków
względnych, A-001–A-107 z rozkładem 23/70/14, E-001–E-015, N-001–N-025 oraz
zero wycieków dokładnych wartości dwóch kluczy. Ręcznie podana ścieżka T-118
nie zawierała członu `-system-`, więc ten jeden podtest hasha był nieważny.

T-144 wykrył i sprawdził właściwą ścieżkę. Hashe czterech raw artefaktów,
trzech chronionych plików V2 i trzech plików `data/` są zgodne. Agregat `data/`
przed i po testach to
`0394685B2F880EDD9A76737F40B0DE4A74D80B205438C405774C5AF4FC21D7FC`.
`.env` i `.live-experiments/` są ignorowane, `git diff --check` przechodzi,
a ciągłość A i T do wpisu poprzedzającego checker jest zachowana. Wynik: PASS,
0 błędów, koszt 0 USD.

## 2026-08-21 — E-016/E-017: transport Scouta działa, jakość starej jednostki nie

E-016 wykonało jeden normalnie routowany Scout DeepSeek Pro przez SSE. Po
247,062 s otrzymano pełny JSON, usage 2 197/15 714 i znany koszt 0,032564 USD.
Był to pierwszy dodatni live dowód transportu Scouta po trzech awariach
buforowanego body. Wynik treściowy był ujemny: sześć propozycji miało po trzy
znane ujęcia i cztery wątki, wszystkie były nasycone, a boil-water notice
przeszedł jako artykuł. Zatrzymano dalszą część ramienia.

E-017 uruchamiało normalny V3 segmentami. Feasibility na zamrożonym Scoucie
przeszło jednym Flash za 0,005868 USD. Discovery `/responses` zostało przerwane
po 60,750 s, bez body/usage/ID; 0,10 USD pozostaje `UNKNOWN`, zero retry. Parser
`/responses` zmieniono na SSE i sprawdzono 4/4 offline, a sąsiedni chat SSE 4/4.

## 2026-08-21 — E-018: live Scout uniwersów artykułowych

Właściciel doprecyzował kryterium: temat ma otwierać wiele naprawdę różnych
świetnych artykułów, ale nie musi być systemem i nie wolno wymagać dokładnie
20. Zmieniono prompt oraz `scout@3`: model ma wymyślać większą pulę, pokazywać
odrzucone zalążki i zwracać osie, napięcia, otwarte gałęzie, osobne drogi,
mechanizmy, dowody, note test i fatalną słabość.

E-018 wykonało dokładnie jeden live DeepSeek Pro, bez fetchu, browsera i
Substacka. Po 284,578 s otrzymano 2 295/24 133 tokenów, sześć tematów, pięć
odrzuconych zalążków i zero błędów schematu. Model sam odrzucił boil-water
notice jako notkę. Pierwsza bramka fałszywie odrzuciła całość, bo wymagała
pięciu dróg, a każdy temat miał cztery. Exact raw replay po usunięciu
arbitralnej kwoty przeszedł 6/6.

Koszt 0,049298 USD przekroczył nominalny cap etapu 0,04 USD. Zapisano A-112 i
N-028; Scout-only dostał predispatch worst-case refusal. DeepSeek ma teraz
konserwatywną ekspozycję 5,00671270 USD, więc dalsze API zatrzymano. Próba
odczytu szczegółowego billing usage przez oficjalny panel zakończyła się na
ekranie logowania; nie wpisywano danych i nie omijano uwierzytelnienia.

Po live otwarto także system prompt, który nadal kotwiczył model w hidden
systems/ordinary things. Ta korekta ma tylko dowód offline. Usunięto martwy
snapshot starego Scouta i dwie martwe stałe. Negatywna pełna regresja 48/55
ujawniła stare fixture’y, kolejna 53/55 dwie martwe stałe; po korektach finalna
regresja T-160 przeszła 55/55 w 59,422 s. Pełny przebieg, pomysły, drogi,
ograniczenia, hashe i porównanie z V2 zapisano w raporcie E-018.
T-161 potwierdził 0 błędów integralności: 93 AST, 16 JSON, 108 dokumentów,
48 linków względnych, ciągłe A-001–A-114/T-001–T-160/N-001–N-028, sześć
hashy raw i trzy chronione hashe V2.

## 2026-08-21 — T-162: benchmark 10 artykułów i 10 Notes Substack

Na jawne polecenie właściciela wykonano publiczny research odczytowy bez sesji
konta i bez jakiejkolwiek mutacji Substacka. Dla artykułów przyjęto z góry
oficjalne Top Reads 2022: dziesięć najczęściej klikanych linków spośród
redakcyjnie kuratorowanego Reads. Dla Notes, wobec braku platformowego rankingu
wielocelowego, dobrano dziesięć przypadków z udokumentowanym zasięgiem,
rozmową, restackiem, bezpłatną albo płatną konwersją. Kontekst zapewniły cztery
duże analizy obserwacyjne; self-report i dowody wtórne zostały oznaczone.

Artykuły najczęściej zaczynają od osoby, sceny, artefaktu, aktualnego zdarzenia
lub ostrej obietnicy użyteczności, po czym rozszerzają konkret do większej
stawki. E-018 jest z tym wzorcem zgodne na poziomie Scouta: sześć uniwersów ma
czytelnicze wejścia, ludzką stawkę i kilka dróg dowodu. Nie ma jednak przebiegu
research–artykuł–Notes dla żadnego z tych tematów, więc downstream pozostaje
nieudowodniony.

Dwa artykuły E-014 mają wyraźny mechanizm i głos, ale powstały na fikcyjnym
fixture i odstają brakiem realnego bohatera, dostępu i źródeł; oba dopisały
przesłanki. Pięć Notes E-014 jest krótkich i konkretnych, lecz 3/5 ma to samo
otwarcie, a generator nie wybiera celu wynikowego. Zapisano A-115: jedna
rubryka miesza zasięg, rozmowę i konwersję mimo obserwowanych kompromisów.

Pełne 10+10, URL-e, liczby, jakość dowodu, porównanie i ograniczenia zapisano w
`04_badania_porownawcze/ANALIZA_10_ARTYKULOW_I_10_NOTES_SUBSTACK_2026-08-21.md`.
Koszt modeli/API: 0,00 USD. Nie publikowano, nie tworzono draftów, nie
polubiono, nie komentowano, nie restackowano, nie obserwowano i nie
subskrybowano.

T-163 potwierdził integralność dokumentacji: ciągłe A-001–A-115,
T-001–T-162 i N-001–N-028, dokładnie 20 wierszy badanej próby, 51 poprawnych
linków względnych, chronione hashe V2 3/3 oraz `git diff --check`. Jedyny
pominięty cel `{url}` jest historycznym placeholderem szablonu, a nie ścieżką
do pliku.

## 2026-08-21 — E-019: ręczny audyt Scouta i wybór drogi

Exact raw E-018 odtworzono bez ponownego płacenia za Scouta. Ręczna kontrola
ujawniła pięć wad na granicy Scout–feasibility: ranking gubił kolejność 1/2/3,
`obvious_coverage` fałszywie oznaczało wszystkie tematy jako nasycone,
feasibility nie widziało 24 dróg, głębokość uniwersum udawała głębokość jednej
drogi, a wspólny hash wszystkich promptów unieważniał cache niezmienionego
Scoutu. Zapisano A-116–A-120 i naprawiono każdą granicę w V3.

F1 wykonał jeden normalny DeepSeek Flash, 4 702/29 646 tokenów, 279,531 s i
0,020601 USD. Kontrakt przeszedł, ale ręczna kontrola zatrzymała prior
authorization, ponieważ brakowało głębokości dokładnej drogi. Po rozszerzeniu
kontraktu próba powtórzenia feasibility ujawniła błąd cache: uprząż próbowała
ponownego Scouta i odmówiła przed dispatch, koszt 0 USD. Fingerprint cache jest
odtąd liczony per etap i wersję kontraktu.

F2 wykonał jeden normalny DeepSeek Flash, 4 854/27 870 tokenów, 250,297 s i
0,019462 USD. Ocenił 24/24 drogi: 3 RICH, 20 SINGLE i 1 THIN. Runtime ponownie
wybrał prior authorization, mimo że model oznaczył tę drogę SINGLE. Ręczny
audyt zatrzymał wynik po raz drugi i wykrył, że ranking parasola nadal
poprzedzał głębokość konkretnego artykułu.

Po deterministycznej zmianie kolejności, bez kolejnego calla, na tych samych
danych live wygrało `The Afterlife of Abandoned Infrastructure` i droga:
„How does an orphaned oil well become a public problem decades after the
company that drilled it disappears?”. Droga ma RICH, 0,90, cztery rodziny
źródeł oraz drugi akt w postaci porzuconych kopalń i terenów Superfund.
Publiczna kontrola read-only potwierdziła istnienie dokumentów BLM, GAO i DOI,
w tym definicji statusów szybów, zabezpieczeń, potencjalnych zobowiązań,
programów stanowych i raportu grantów FY2025. Nie weryfikowano jeszcze tez do
fragmentów; to zadanie discovery/fetch.

Testy celu po ostatecznej zmianie przeszły 36/36. Koszt E-019 wyniósł
0,040063 USD KNOWN. Konserwatywna ekspozycja całych badań to 6,44480970 USD,
pozostały margines globalnych 10 USD to 3,55519030 USD. Zero retry i zero
aktywności na Substacku. Pełny materiał, oba ręczne FAIL, wszystkie 24 drogi,
źródła i porównanie z V2 zapisano w raporcie E-019.

### T-170–T-174 — pełna regresja i niestabilny checkpoint

Pierwsza pełna regresja po E-019 dała 54/55. Strażnik martwych sygnałów
wykrył `NASYCENIE_OD_ILU`, które po naprawie A-117 nie miało już aktywnego
czytelnika. Stałą usunięto z config; historyczny kontrprzykład starej
architektury przechowuje dawną wartość wyłącznie lokalnie. Oba testy celu
przeszły.

Druga pełna regresja znów dała 54/55, tym razem przez sporadyczny `WinError 5`
przy atomowym checkpointcie uprzęży kontynuacyjnej. Sam plik czasem przechodził,
więc wykonano dziesięć powtórzeń: 3/10 zakończyły się identycznym
`PermissionError` podczas `os.replace`. Zapis dostał unikalny temp oraz pięć
krótkich prób replace; trwała blokada nadal nie jest ignorowana. Kontrtest
pierwszej blokady i drugiego sukcesu przeszedł, podobnie jak 10/10 pełnych
powtórzeń. Zapisano A-121.

Finalna T-174 wykonała ponownie 55 zwykłych plików osobno z projektowym `.venv`,
UTF-8, fixture i kill switchem. Wynik: 55/55 PASS w 56,775 s, koszt 0 USD, brak
sieci i zewnętrznych mutacji. Wyniki 54/55 zachowano w rejestrze jako ważne
kontrprzykłady, a nie zastąpiono finalnym zielonym przebiegiem.

## 2026-08-21 — E-020: live discovery zatrzymane przez ręczny audyt

Preflight najpierw fail-closed wykrył historyczne nazwy kluczy bez prefiksu
`AGENT_V3_`; nie było dispatchu ani kosztu. Sekrety zmapowano wyłącznie w
pamięci procesu, bez wypisywania i bez zmiany `.env`.

Właściwe E-020 uruchomiło jeden normalny `deepseek-v4-pro`, zero retry i pełny
brief wybranej drogi orphaned well. Po 136,016 s model zwrócił pełny JSON,
153 385/7 360 tokenów, 22 wyszukiwania i koszt 0,115807 USD KNOWN. Exact-URL
gate zachował 8 z 10 propozycji. Runtime zapisał PASS, ale ręczna kontrola
odrzuciła wynik, ponieważ limit wynosił 8, a model użył narzędzia 22 razy.

Ręcznie otwarto Cornell/LII, California Public Law, oba GAO, OSMRE, Carbon
Tracker i OWA; UNT nie otworzył się. Cornell i California są tekstami prawa na
mirrorach, a nie origin publisherami. Carbon Tracker udostępnia liczby na
landing page, lecz pełny report wymaga loginu. Ręczny baseline znalazł ponadto
silniejsze i nowsze BLM 2024, GAO-19-615, program DOI oraz DOI FY2025. Zapisano
A-123–A-125 i zatrzymano pipeline przed fetch.

Oficjalny kontrakt `/responses` nie ma `max_uses`; oficjalny interfejs DeepSeek
zgodny z Anthropic oraz implementacja DeepSeek Harness mają limit narzędzia.
Następna zmiana dotyczy transportu tego samego `deepseek-v4-pro`, niezależnego
postwarunku użyć i jawnego rozdzielenia klasy dokumentu od roli hosta. Po
rozliczeniu globalna ekspozycja wynosi 6,56061670/10 USD. Zero aktywności na
Substacku.

## 2026-08-21 — E-021: twardy limit przeszedł, źródła nie

Ten sam normalny `deepseek-v4-pro` uruchomiono przez oficjalny interfejs
zgodny z Anthropic z `max_uses=8`, bez retry i bez zmiany routingu. Discovery
wykonało 6/8 wyszukiwań, zwróciło 10 exact URL-i, zużyło 39 265/3 886 tokenów
i kosztowało 0,033609 USD `KNOWN`. Twardy limit przeszedł live.

Ręcznie otwarto i oceniono wszystkie 10 propozycji. Zestaw odrzucono: model
błędnie zadeklarował dostęp do IOGCC, podał wtórny komunikat EDF zamiast
oficjalnego audytu/reguły, dopuścił introduced H.R. 9029 i ponownie pominął
mocniejszy baseline BLM/GAO/DOI. Zapisano A-125–A-127. Fetch i dalsze etapy nie
wystartowały. Testy `discovery@3` przeszły 70/70, a pełna regresja przed następną
próbą 56/56 w 58,061 s. Zero Substacka.

## 2026-08-21 — E-022: role dowodowe zatrzymały brak drugiego aktu

Trzecie discovery tego samego Pro wykonało dokładnie 8/8 wyszukiwań, zużyło
40 253/8 088 tokenów, kosztowało 0,042581 USD `KNOWN` i zwróciło 10 propozycji.
Po filtrze exact URL oraz deklaracji dostępu zostało 6. Kontrakt poprawnie
zatrzymał przebieg z powodu braku kwalifikowanego `SECOND_ACT`.

Ręcznie sprawdzono pełne 10 propozycji. DOI FY2024 było mocnym current official
scale, IOGCC 2008 dobrym mechanizmem historycznym, a Capitol Forum użytecznym
źródłem wspierającym. OSMRE było dobrym drugim aktem, lecz jego dokładnego URL-a
nie zwróciła bieżąca sesja. Trzy strony dały direct HTTP 403, a zestaw nadal
nie dorównał BLM/GAO/DOI. Werdykt: manual FAIL; zero fetch, artykułu, Notes i
Substacka.

E-022 ujawniło A-128: capture zapisywał liczbę 46 wyników narzędzia, ale nie
pełną listę adresów. Po poprawce bounded search i beznarzędziowy exact-URL
selector są dwoma jawnymi requestami tego samego modelu w jednym logicznym
callu, a capture zachowuje ich prompty, raw, hashe, usage i pełne URL-e. Testy
celu przeszły 72/72. Nieważny przebieg 69 plików, w którym błędny glob włączył
`tests/platne`, zachowano jako T-185; kill switch i dry-run zablokowały wszystkie
płatne launchery. Poprawna regresja przeszła 56/56 w 58,480 s.

## 2026-08-21 — E-023: niepełny stream, `UNKNOWN` i naprawa trace

Po jawnej rezerwacji 0,30 USD rozpoczęto wyłącznie discovery. Pierwszy bounded
search urwał się po około 7 s błędem `incomplete chunked read`, zanim powstały
finalne usage, wyniki wyszukiwania lub JSON. Exact-URL selector nie wystartował,
retry=0. Nie wykonano fetch, classify, synthesis, writer, Notes ani żadnego
dostępu do Substacka.

Ponieważ request został wysłany bez finalnego usage, 0,30 USD pozostaje
`UNKNOWN`. Bezpłatny snapshot `/user/balance` po błędzie pokazał 24,95 USD,
lecz bez snapshotu sprzed próby nie rozlicza E-023. Konserwatywna ekspozycja
wynosi 6,93680670/10 USD, a DeepSeek pozostaje zablokowany do rekoncyliacji.

E-023 ujawniło A-129: historyczny capture podawał zero provider requestów,
ponieważ wpis trace powstawał dopiero po kompletnym body. Kod zapisuje teraz
`DISPATCH_STARTED` przed oczekiwaniem na stream, potem
`COMPLETED_WITH_USAGE` albo `FAILED_WITHOUT_FINAL_USAGE`. Testy celu przeszły
73/73 w 2,948 s, a pełna bezpieczna regresja 56/56 w 58,215 s. Oba przebiegi
były offline, z fixture, kill switchem i dry-run, przy koszcie 0 USD.
T-191 domknął integralność kodu i dokumentacji bez błędów.

## 2026-08-21 — E-024: live safe-fetch i ręczna kontrola pełnych tekstów

Ponieważ E-023 pozostaje nierozliczone, nie wykonano kolejnego model calla.
Oficjalny endpoint salda pokazał 24,92 USD, o 0,03 mniej niż snapshot po
E-023, lecz bez eksportu Usage per API key nie da się przypisać delty do
requestu. Panel wymagał loginu, a Chrome/extension nie były dostępne. Rezerwa
0,30 USD nadal jest `UNKNOWN`.

Niezależny E-024 prerejestrował sześć publicznych dokumentów i uruchomił aktywne
`stages.fetch` z pustymi kluczami modeli, bez retry i fallbacku. DOI, BLM, GAO,
OSMRE i IOGCC przeszły transport oraz ręczną kontrolę tekstu; Capitol Forum dał
HTTP 403 i nie został obchodzony. Wynik 5/6 pokrył `CURRENT_SCALE`,
`CAUSAL_MECHANISM` i `SECOND_ACT`. Pełne teksty, redirecty, DNS pins, hashe i
baza eksperymentu są w `.live-experiments/E-024-safe-fetch-canary/`. Koszt 0
USD, Substack 0.

Ręczne czytanie znalazło A-130: strona GAO raportu 2019 zawiera status
rekomendacji z lutego 2026, a pipeline gubił `published_at`, status i role przed
syntezą. Fetch nadaje teraz `retrieved_at`; classify, synthesis i końcowy
manifest zachowują wszystkie metadane oraz rozróżniają datę dokumentu, datę
pobrania i datę fragmentu. Kontrtest przeszedł 3/3, sześć plików sąsiednich
107/107, a pełna bezpieczna regresja 57/57 w 61,004 s. Live classify pozostaje
zablokowane przez nierozliczone E-023.
