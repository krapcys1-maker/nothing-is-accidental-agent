# E-018 — Scout: od ciekawostki do uniwersum artykułowego

**Data:** 2026-08-21  
**Status:** `LIVE_TRANSPORT_AND_SCHEMA_PASS; QUALITY_REPLAY_PASS; POST_LIVE_PROMPT_FIX_OFFLINE; COST_CAP_BREACH`  
**Zakres:** wyłącznie Scout i jego bezpieczna uprząż  
**Substack:** zero odczytu, sesji, szkicu, zapisu i publikacji

## 1. Pytanie badawcze

Czy Scout V3 potrafi nie tylko odnaleźć jedną ciekawostkę albo procedurę, lecz
wymyślić temat będący dużym polem redakcyjnym: z niezależnymi pytaniami,
różnymi mechanizmami, różnymi rodzajami dowodu, realnymi napięciami i kilkoma
możliwymi odpowiedziami?

W eksperymencie nie przyjęto magicznej liczby możliwych artykułów. Dziewiętnaście
dobrych dróg nie jest gorsze od dwudziestu, a czterdzieści wariantów jednego
nagłówka nie dowodzi głębi. Maszynowe minima służą wyłącznie wykryciu oczywistej
notki rozbitej na podpunkty; nie są oceną jakości pomysłu.

## 2. Kontrasty kalibracyjne

- Właściwy rozmiar: „co stałoby się, gdyby bańka inwestycji w AI pękła teraz?” —
  osobne pytania o rynek, prywatny kapitał, pracę, energię, infrastrukturę,
  politykę, kulturę, zarażenie innych sektorów, przegranych i tempo odbudowy.
- Zbyt mały rozmiar: „co dzieje się po dodatnim wyniku próbki wody?” — jedna
  procedura, którą można uczciwie streścić w kilku zdaniach. Rozdzielenie jej
  na osobę dzwoniącą, podpisującą i odwołującą alert nie tworzy trzech artykułów.
- Temat nie musi być systemem, procedurą ani przedmiotem. Może zaczynać się od
  ekonomii, pracy, nauki, historii, kultury, tożsamości, technologii, władzy,
  kontrfaktycznego założenia, konfliktu albo ludzkiego doświadczenia.

## 3. Chronologia dowodu live

### E-016 — transport działa, stary Scout jakościowo nie działa

Pierwszy prawidłowy canary SSE ukończył jeden normalnie routowany
`deepseek-v4-pro`: 2 197 tokenów wejścia, 15 714 wyjścia, 247,062 s,
0,032564 USD. Transport, usage i JSON przeszły. Scout oddał sześć propozycji:

1. decyzja o boil-water notice;
2. zwrot sklepowy jako wynik fraud score;
3. ocena sanitarna restauracji jako migawka;
4. przejazd pociągu za czerwony sygnał;
5. zakres wycofania partii żywności;
6. jeden respirator i dwóch pacjentów.

Każdy temat miał dokładnie cztery wątki i trzy znane ujęcia; wszystkie sześć
sam kod oznaczył jako nasycone, po czym względny ranking nadal wybierał
„najlepszy”. Szczególnie boil-water notice jest dobrą notką lub jednym
explainerem, nie dużym uniwersum artykułowym. Wynik E-016 jest zatem dodatnim
dowodem transportu i ujemnym dowodem jakości starej architektury Scouta.

Artefakt: `.live-experiments/E-016-scout-sse-canary/result.json`, SHA-256
`2EC909C56AFABCE031F741F34753370E3127156E27073A423454D1D2DAB3E504`.

### E-017 — segmentacja normalnego V3

Na zamrożonym wyniku E-016 normalny etap feasibility przeszedł jednym
`deepseek-v4-flash`: 511 tokenów wejścia, 8 709 wyjścia, 0,005868 USD. Nie
naprawia to słabego tematu; dowodzi tylko, że następny etap umie znaleźć
dokumenty do proceduralnego pytania.

Discovery wykonało jedno normalne żądanie `/responses`, które zostało przerwane
po 60,750 s bez kompletnego body i usage. Rezerwacja 0,10 USD pozostaje
`UNKNOWN`; zero retry. Następnie oba parsery SSE `/responses` i
`/chat/completions` przeszły po 4/4 testy offline. Dodatni live discovery jest
otwarty i zablokowany budżetowo.

### E-018 — jeden Scout po zmianie jednostki pracy

Uprząż wykonała dokładnie jeden logiczny `scout`, zero retry, bez publicznego
fetchu, browsera i Substacka. Routing pozostał niezmieniony. Model
`deepseek-v4-pro` ukończył SSE po 284,578 s:

| Metryka | Wynik |
|---|---:|
| tokeny wejścia | 2 295 |
| tokeny wyjścia | 24 133 |
| koszt KNOWN | 0,049298 USD |
| web search | 0 |
| błędy kontraktu JSON | 0 |
| finalne tematy | 6 |
| odrzucone zalążki | 5 |

Pierwsza bramka semantyczna oznaczyła przebieg jako FAIL wyłącznie dlatego,
że ówczesny kod wymagał pięciu dróg artykułowych, a każdy temat miał cztery.
Każdy miał jednocześnie pięć osi, trzy napięcia, trzy otwarte gałęzie, cztery
różne mechanizmy, cztery rodziny dowodu i cztery nieoczywiste połączenia.
Wymóg pięciu był arbitralny. Po zastąpieniu go jedynie grubą zaporą przed jedną
odpowiedzią dokładnie ten sam, niezmieniony response przeszedł rzeczywistą
funkcję `stages.scout`: 6/6 `pole_redakcyjne=true`.

To jest replay odpowiedzi live, nie drugie wywołanie modelu.

## 4. Pełny ślad replikacyjny E-018

| Artefakt | SHA-256 |
|---|---|
| `model-captures.json` — pełny system prompt, user prompt i raw response | `841BCE55FF7571A2D2E6A4D5AF6CE0390A826F5A37EAA711CBA3151D8196C395` |
| `segment-scout-live-only-result.json` | `CFF124977AE9BD54D9A214FF0578673E520FA96C173F2A9315ACCC8C303E6E5A` |
| `manifest.json` | `EC4EF6204E3EA5B27B798790E42D1F6D3AADE92EB9B7E97A9F93D5E9DE815ECA` |
| raw response wewnątrz capture | `7240511AD38593B9D40C785565836842FDF40AD020BB1126494F26EAC1B876F4` |
| wyrenderowany user prompt live | `8396990722202E925D7CCC2364C23F8E1B5414FCA425C3952E4C0395113ECC14` |

Lokalizacja: `.live-experiments/E-018-scout-universe-live/`. Katalog jest
ignorowany przez Git, ponieważ zawiera pełne prompty i odpowiedzi. Nie zawiera
klucza API.

## 5. Odrzucone zalążki — filtr jest obserwowalny

Model jawnie odrzucił:

1. identyczne tablice rejestracyjne — jedna odpowiedź o czytelności i
   standaryzacji;
2. boil-water notice — krótka procedura, nie uniwersum artykułów;
3. karty hotelowe przy telefonach — jedno wyjaśnienie fizyczne;
4. cały świat bez gotówki od jutra — model uznał, że gałęzie schodzą do znanej
   historii o inkluzji; to odrzucenie jest dyskusyjne i pokazuje ryzyko zbyt
   ostrego filtra;
5. pracownicy airport lost-and-found — jeden dobry reportaż/portret, nie wiele
   osobnych pytań badawczych.

## 6. Wszystkie pomysły live i drogi artykułowe

Poniższe są pomysłami i hipotezami Scouta, nie zweryfikowanymi faktami.

### 6.1 Suspicion as Default — kolejność replayu: 1; ranking +5

**Pytanie:** co zmienia się, gdy instytucje najpierw zakładają oszustwo, błąd
lub nadużycie, a uczciwa większość musi dowodzić niewinności?

**Osie:** asymetria ryzyka instytucji; koszt administracyjny; modele ryzyka;
procedura prawna; zaufanie społeczne.

**Napięcia:** kontrola realnych nadużyć kontra koszt fałszywych podejrzeń;
natychmiastowa automatyczna odmowa kontra powolne ludzkie odwołanie;
przejrzystość procedury kontra ryzyko jej obchodzenia.

**Osobne artykuły:**

- jak chargeback uczynił sprzedawcę domyślnie podejrzanym;
- ile prior authorization kosztuje w dniach odmowy i ludzkiej pracy;
- dlaczego administracja podatkowa wybiera kontrole za pomocą risk scores;
- jak hotel check-in i lotnisko zamieniły zwykłą tożsamość w rytuał podejrzenia.

**Ryzyko upadku:** wszystkie drogi mogą zejść do jednego znanego argumentu o
nierówności i nieufności wobec biednych.

### 6.2 The Uninsurable World — kolejność replayu: 2; ranking +5

**Pytanie:** co zastępuje prywatne ubezpieczenie, kiedy ryzyko staje się zbyt
skorelowane, częste albo politycznie nieakceptowalne do wyceny?

**Osie:** nieruchomość i kredyt; finanse publiczne; budowanie i adaptacja;
wzajemna pomoc; odpowiedzialność prawna.

**Napięcia:** cena odpowiadająca ryzyku kontra dostępność domu; publiczne
ratowanie kontra prywatny zysk; wycofanie z ryzyka kontra potrzeba pozostania.

**Osobne artykuły:**

- co dzieje się w regionie, gdy ubezpieczyciel wycofuje się przed katastrofą;
- jak insurer of last resort zmienia się z zapory w największego gracza;
- czy rynek hipotek może istnieć bez standardowej polisy;
- kiedy wspólnotowe pule ryzyka działają lepiej od ubezpieczyciela.

**Ryzyko upadku:** temat może skurczyć się do bieżących tekstów o Kalifornii i
Florydzie zamiast badać ogólny mechanizm nieubezpieczalności.

### 6.3 The Afterlife of Abandoned Infrastructure — kolejność replayu: 3; ranking +4

**Pytanie:** kto dziedziczy koszty, ryzyko, pamięć i użyteczność kopalni, tam,
kabli, fabryk oraz oprogramowania, gdy pierwotny właściciel już ich nie chce?

**Osie:** własność i odpowiedzialność; skażenie; pamięć instytucjonalna;
ponowne użycie i nieformalna okupacja; zabezpieczenie finansowe.

**Napięcia:** prawo do odejścia kontra trwały obowiązek; bezpieczne zamknięcie
kontra ponowne użycie; koszt dziś kontra ryzyko przez dziesięciolecia.

**Osobne artykuły:**

- dlaczego osierocone szyby naftowe pozostają po zniknięciu spółek;
- jak bezpiecznie mapować i zamykać porzucone kopalnie;
- dlaczego stare korytarze kolejowe wracają jako ścieżki, granice i spory;
- co znaczy porzucona infrastruktura w świecie niewspieranego oprogramowania.

**Ryzyko upadku:** łatwo zamienić temat w galerię ruin zamiast badać mechanizm
porzucenia i przechodzenia obowiązków.

### 6.4 The Standard Human Body — kolejność replayu: 4; ranking -1

**Pytanie:** co dzieje się, gdy przedmioty, bezpieczeństwo i badania buduje się
wokół standardowego ciała, do którego realni ludzie pasują tylko częściowo?

**Osie:** inżynieria bezpieczeństwa; normy i regulacje; projektowanie i rynek;
badania kliniczne; codzienne wykluczenie.

**Napięcia:** standaryzacja kontra zmienność ciał; kontrolowany test kontra
ochrona osób spoza próbki; „specjalne dostosowanie” kontra normalna różnorodność.

**Osobne artykuły:**

- droga od męskiego crash-test dummy do modelu ciała w ciąży;
- jak badania dawki uwzględniają masę ciała i metabolizm;
- dlaczego PPE nadal pasuje do wąskiego zakresu sylwetek;
- co się dzieje, gdy ergonomia jednego kraju staje się globalnym standardem.

**Ryzyko upadku:** może powstać lista znanych przypadków biasu bez artykułu o
tym, jak standardowe ciało jest wytwarzane i utrwalane.

### 6.5 The Last Human in the Loop — kolejność replayu: 5; ranking -2

**Pytanie:** co dzieje się z pracą, odpowiedzialnością i jakością, gdy system
automatyczny jest gotowym produktem tylko dlatego, że ukryci ludzie obsługują
wyjątki?

**Osie:** proces pracy; odpowiedzialność prawna; interface design; ekonomia
błędu; pamięć organizacyjna.

**Napięcia:** redukcja kosztu kontra osąd człowieka; named accountability kontra
rozproszona decyzja; marketing pełnej automatyzacji kontra operacyjna potrzeba
ukrytej pracy.

**Osobne artykuły:**

- jak naprawdę wygląda praca zdalnego operatora pojazdu autonomicznego;
- ukryta praca uwalniania płatności zatrzymanej przez model fraudowy;
- dlaczego szpitale używają skrybów do rzekomo automatycznej dokumentacji AI;
- jak moderacja treści stała się kolejką obsługi wyjątków.

**Ryzyko upadku:** temat może stać się ogólną krytyką hype'u AI i outsourcingu
do niedopłacanych pracowników.

### 6.6 The Quality of Recycled Materials — kolejność replayu: 6; ranking -2

**Pytanie:** co dzieje się z produkcją, handlem i pracą odpadową, gdy recykling
nie daje stabilnego surowca, lecz zmienną i zanieczyszczoną mieszankę?

**Osie:** nauka o materiałach; logistyka i mieszanie; praca nieformalna; handel
globalny; projektowanie opakowań.

**Napięcia:** wysoka czystość kontra koszt sortowania; lokalny recykling kontra
globalny handel jakością; jednolity produkt kontra zmienny surowiec.

**Osobne artykuły:**

- jak papiernie wyceniają i mieszają bele makulatury;
- jak reguły czystości importu zmieniają globalny handel odpadami;
- dlaczego chemia baterii komplikuje sortowanie do recyklingu;
- kto naprawdę wie, co znajduje się w beli plastiku.

**Ryzyko upadku:** temat może skończyć jako znany tekst „recykling jest brudny”,
bez osobnej ekonomii jakości materiału.

## 7. Ręczna ocena jakości

Ocena była nieslepa i służy kalibracji, nie jest pomiarem statystycznym.

| Temat | pole artykułów | siła wejścia dla czytelnika | oryginalność konfiguracji | główne ryzyko |
|---|---|---|---|---|
| Suspicion as Default | bardzo duże | bardzo duża | wysoka | jedna teza o nierówności |
| The Uninsurable World | bardzo duże | bardzo duża | wysoka | bieżący news klimatyczny |
| Afterlife of Abandoned Infrastructure | bardzo duże | duża | bardzo wysoka | estetyka ruin |
| Standard Human Body | duże | bardzo duża | średnia | lista znanych przypadków |
| Last Human in the Loop | duże | duża | średnia/wysoka | ogólny tekst o AI hype |
| Quality of Recycled Materials | duże | średnia | wysoka | „recycling is broken” |

Wniosek: E-018 jest materialnie lepsze od E-016. Nie dowodzi jeszcze, że Scout
jest „wymaxowany”: wszystkie sześć odpowiedzi miało identyczne liczebności
anatomii (5/3/3/4/4), co może oznaczać formatowe wypełnianie. Jakość jest
nierówna, a trzy tematy mogą zejść do znanych debat.

## 8. V2 kontra badany V3

V2 pozostawało tylko do odczytu.

| Wymiar | V2 | E-016 / stary V3 | E-018 i stan po naprawie |
|---|---|---|---|
| aktywny prompt | 437 linii, 3 781 słów, 22 437 znaków | skrócona wersja tej samej doktryny | 242 linie, 1 287 słów, 9 283 znaki |
| jednostka tematu | zwykły obiekt/procedura/moment | dwa typy: belief/system | dowolne duże uniwersum artykułowe |
| generowanie | głównie recall i anty-cliché | to samo, z wymuszonym systemem | prywatna nadprodukcja przez wiele silników pomysłu |
| głębia | precedensy, skala, liczba wątków | identyczne pola łatwo się wyrównują | osie, napięcia, gałęzie, różne mechanizmy i dowody |
| mały temat | mógł przejść jako system/procedura | boil-water notice przeszedł | model sam odrzucił boil-water notice |
| ranking | `most/least_written`, `richest/thinnest` | najlepszy względnie nawet gdy całość słaba | najbogatsze uniwersum, compelling, original, collapse risk |
| dowód live | historyczne działanie, brak nowego śladu w tym eksperymencie | transport PASS, jakość FAIL | raw live 6 tematów; post-live system prompt nadal wymaga rewalidacji |

SHA-256 promptu V2: `F61A658DE4DDD4941546DC107D3061BD336883A3BEF7122BAC1CC765A80650A3`.
V2 było skuteczniejsze operacyjnie od V3 przed SSE, bo potrafiło przechodzić
dalej. E-018 po raz pierwszy pokazuje przewagę jakościową V3 na samym Scoucie,
ale jeszcze nie przewagę całego potoku.

## 9. Ważne ograniczenie: live użył starego system promptu

User prompt E-018 mówił wprost, że temat nie musi być systemem. System prompt
live nadal brzmiał jednak jak Scout „hidden systems, incentives and decisions
behind ordinary things”. Wszystkie sześć wyników da się z tego powodu czytać
jako systemowe. Po live system prompt zmieniono na otwarty wynalazca tematów z
nauki, historii, ekonomii, kultury, pracy, technologii i ludzkiego życia.

Ta korekta ma dowód offline, lecz nie ma nowego dowodu live. Nie wolno mieszać
jej z wynikiem E-018 ani twierdzić, że live potwierdził pełną różnorodność.

## 10. Przekroczenie limitu etapu

Deklarowany cap Scouta wynosił 0,04 USD, a wynik kosztował 0,049298 USD —
przekroczenie o 0,009298 USD. Rezerwacja była atomowa, ale `max_tokens` nie
wynikał z kwoty; settlement zastąpił rezerwację wyższym kosztem. Jest to nowy
kontrprzykład P0 dla „atomowego budżetu”.

Uprząż Scout-only oblicza teraz przed dispatch konserwatywny najgorszy koszt z
bajtów wejścia, limitu wyjścia i cennika. Przy aktualnym suficie tokenów odmówi
przed siecią, bo samo maksymalne wyjście przekracza 0,04 USD. Test zawiera
zarówno ujemną odmowę, jak i dodatni przypadek z małym sufitem.

Nie jest to jeszcze globalna gwarancja, że każde wywołanie w całym V3 ma
`max_tokens` wyprowadzony z rezerwacji. Karta N-028 pozostaje otwarta dla
warstwy wspólnej.

## 11. Budżet po E-018 i decyzja stop

| Zakres | znane/estymowane | `UNKNOWN` | konserwatywna ekspozycja | limit |
|---|---:|---:|---:|---:|
| Anthropic | 1,39803400 | 0,00 | 1,39803400 | 5,00 |
| DeepSeek | 0,10671270 | 4,90 | 5,00671270 | 5,00 |
| **globalnie** | **1,50474670** | **4,90** | **6,40474670** | **10,00** |

Globalnie pozostaje 3,59525330 USD, ale sublimit DeepSeek został
konserwatywnie przekroczony o 0,00671270 USD. Dlatego nie wykonano i nie wolno
wykonywać kolejnego live/API do rekoncyliacji starego `UNKNOWN` albo jawnej
zmiany budżetu przez właściciela. Brak kolejnego live nie jest unikaniem testu,
lecz wynikiem wykrytej w live bramki bezpieczeństwa.

## 12. Naprawy po wyniku

- nowy kontrakt `scout@3` przechowuje pełną anatomię pomysłu;
- usunięto wymóg systemu, procedury i zwykłego przedmiotu;
- usunięto magiczne 20 oraz późniejszy arbitralny próg 5 dróg;
- kod odróżnia pytanie, mechanizm drogi i potrzebną rodzinę dowodu;
- finalista sam wykonuje `note_test` i podaje `fatal_weakness`;
- portfel musi użyć więcej niż jednego sposobu wymyślania, gdy ma co najmniej
  dwa tematy;
- ranking względny działa dopiero po bezwzględnej zaporze przed oczywistą notką;
- usunięto około 250 linii martwego snapshotu starego Scouta i dwie martwe
  stałe system/precedens;
- fixture’y pełnego replayu, rewizji i obu harnessów przeszły na nowy kontrakt;
- Scout-only ma dokładnie jeden call, zero retry, brak browsera/Substacka oraz
  predispatch worst-case cap.

## 13. Werdykt

Scout V3 nie jest już ograniczony do systemów ani do drobnych ciekawostek. Jeden
live wygenerował sześć rzeczywistych pól redakcyjnych i jawnie odrzucił
boil-water notice jako notkę. To jest wyraźna poprawa jakości wobec E-016 i
architektury V2.

Nie jest to jeszcze dowód pełnego sukcesu. Otwarty pozostaje live z nowym system
promptem, różnorodność poza tematami systemowymi, ryzyko formatowego wypełniania
identycznych liczebności oraz globalne związanie realnego kosztu z limitem.
Następny płatny test jest zablokowany budżetowo; następna praca może być tylko
offline albo po rekoncyliacji dostawcy.
