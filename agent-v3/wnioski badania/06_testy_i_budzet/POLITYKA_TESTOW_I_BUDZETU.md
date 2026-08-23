# Polityka testów i budżetu Agent V3

**Data:** 2026-08-21  
**Tryb domyślny:** offline  
**Zakaz nadrzędny:** żadnej mutacji konta produkcyjnego ani wdrożenia produkcyjnego; test live może dotyczyć wyłącznie odseparowanego konta testowego

## 1. Cel

Testy mają dowodzić własności autonomicznego systemu redakcyjnego przy najmniejszym możliwym ryzyku i koszcie. Dostęp do internetu i modeli jest narzędziem ostatniego etapu, nie domyślną ścieżką.

## 2. Hierarchia testów

1. **Static** — AST, import graph bez importu, wyszukiwanie kontraktów, hashe, lint dokumentacji.
2. **Unit fixture** — czyste funkcje i wersjonowane fixture'y.
3. **Property/negative** — generowane przypadki, kontrdowody, mutacje wejść.
4. **Offline integration** — tymczasowa baza, fałszywy transport, zamrożony zegar, pełny pipeline.
5. **Browser fixture** — lokalna fałszywa strona; zero połączeń do Substack.
6. **Model replay** — zapisane odpowiedzi modeli; koszt 0 USD.
7. **Paid model eval** — zamrożone wejścia, jawna hipoteza i księgowanie.
8. **Read-only network** — tylko jeśli semantyki odpowiedzi nie da się odtworzyć z fixture'u.
9. **Isolated live_test** — najmniejsza możliwa mutacja wyłącznie na odseparowanym koncie testowym, po przejściu wszystkich wcześniejszych poziomów.

Poziom 9 jest dozwolony kontraktem, ale nie został jeszcze uruchomiony. Nie wolno użyć go do konta produkcyjnego ani ominąć capabilities.py.

## 3. Budżety twarde

Łączny, nadrzędny limit wszystkich API wynosi **10.00 USD** i obejmuje także
historyczny koszt E-007. Sublimity niżej ograniczają pojedynczych dostawców,
ale nie są budżetami, które można zsumować ponad limit globalny. Każda
rezerwacja musi zmieścić się jednocześnie w saldzie dostawcy i saldzie całego
programu.

| Dostawca | Limit całkowity | Dozwolony cel | Zakazane użycie |
|---|---:|---|---|
| Anthropic | 5.00 USD | ewaluacja tylko na modelu jawnie przypisanym badanemu etapowi | zmiana modelu bez osobnego polecenia, publikacja, żywy agent konta |
| DeepSeek | 5.00 USD | ewaluacja na aktualnym routingu, schematy i regresja fixture | zmiana modelu bez osobnego polecenia, publikacja, brak limitu tokenów |
| GPT/OpenAI | 2.00 USD | wyłącznie testy generowania obrazów | tekst, recenzja, research, sterowanie agentem |

Limity są łączne dla projektu, nie na sesję. Sublimity tabeli sumują się do
12 USD wyłącznie jako niezależne sufity ryzyka; globalna bramka 10 USD ma
pierwszeństwo. Przekroczenie o dowolną kwotę jest błędem testu.

## 4. Rezerwa budżetowa

Planowana maksymalna alokacja:

### Anthropic — 5.00 USD

- 2.00 USD — porównanie rewizji na zamrożonym korpusie;
- 1.25 USD — weryfikacja faktograficzna i schema adherence;
- 1.25 USD — zestaw prompt injection/adversarial;
- 0.50 USD — rezerwa na ponowienie techniczne.

### DeepSeek — 5.00 USD

- 2.00 USD — pisarz przed/po na tych samych evidence cards;
- 1.25 USD — rewizja i zachowanie tezy;
- 1.25 USD — poprawność wersjonowanych JSON schema;
- 0.50 USD — rezerwa na ponowienie techniczne.

### GPT/OpenAI — 2.00 USD

- 1.50 USD — mały, zamrożony zestaw promptów obrazowych;
- 0.50 USD — rezerwa na błąd techniczny.

Alokacja nie jest zobowiązaniem do wydania. Jeżeli offline rozstrzyga hipotezę, koszt pozostaje 0 USD.

## 5. Warunek uruchomienia testu płatnego

Test płatny może zostać wykonany tylko, gdy istnieją:

- karta naprawy;
- pytanie, którego replay/fixture nie rozstrzyga;
- zamrożony input i oczekiwany format;
- limit wywołań, tokenów i kosztu;
- dokładna nazwa modelu zgodna z domyślnym routingiem normalnego V3, bez
  `AGENT_V3_CHEAP`, `AGENT_V3_WRITER` ani innego override; budżet dostawcy nie
  jest zgodą na zmianę modelu;
- oszacowanie najgorszego kosztu przed startem;
- wolny budżet w `REJESTR_WYDATKOW_ONLINE.md`;
- zapis odpowiedzi pozbawiony sekretów;
- reguła zatrzymania po błędzie schematu lub pierwszym przekroczeniu rezerwy.

Harness nie może wykonywać `MODEL_FOR.update()` ani akceptować konfiguracji
środowiska zmieniającej model bez osobnego, jawnego polecenia. Przed dispatch
musi wypisać dokładny model, etapy, liczbę żądań i maksymalny koszt.

## 6. Zasady danych i sekretów

- Klucze są odczytywane wyłącznie z procesu testowego i nigdy nie trafiają do logu.
- Test płatny nie może ładować produkcyjnej sesji przeglądarki.
- Do modelu nie trafiają adresy e-mail, tokeny sesji, dane subskrybentów ani niezanonimizowane identyfikatory kont.
- Każdy fixture ma hash i wersję.
- Cache odpowiedzi modelu ma jawny status testowy i nie jest wejściem do produkcji.

## 7. Metryki ewaluacji tekstu

Nie stosuje się jednego score. Zestaw testowy mierzy osobno:

- pokrycie twierdzeń źródłami;
- nowe fakty dodane bez dowodu;
- zachowanie centralnej tezy;
- usunięcie wskazanych wad;
- poprawność struktury JSON;
- zgodność długości;
- naruszenia stylu;
- wyciek instrukcji;
- stabilność wyniku między powtórzeniami;
- koszt i czas.

Warunek krytyczny jest koniunkcją. Wynik stylistyczny nie kompensuje faktu bez źródła.

## 8. Testy obrazów

Budżet GPT jest wyłącznie obrazowy. Test obrazu używa niewielkiej liczby zamrożonych promptów i mierzy:

- zgodność z tematem i obiektem;
- brak tekstu, logo i przypadkowych symboli, jeśli prompt ich zabrania;
- zgodność proporcji i przeznaczenia;
- powtarzalność zasad stylu;
- koszt na zaakceptowalną próbę.

Wygenerowany obraz pozostaje artefaktem testowym. Nie jest przesyłany na Substack.

## 9. Testy sieciowe

Dozwolone:

- publiczne README i kod źródłowy;
- publiczne strony źródłowe bez logowania;
- nieautoryzowany, tylko-odczytowy test parsera w odizolowanym kliencie;
- wywołania modeli objęte księgą;
- pojedyncza, wcześniej opisana mutacja live_test, jeżeli jednocześnie:
  - istnieje karta i zamrożony oczekiwany rezultat;
  - konto oraz publikacja są przeznaczone wyłącznie do testów V3;
  - handle testowy i cel są identyczne oraz różne od nothingisaccidental;
  - znacznik prototypu istnieje;
  - AGENT_V3_MODE ma wartość live_test;
  - kill switch jest wyłączony tylko na czas eksperymentu;
  - dokładny token AGENT_V3_LIVE_TEST_CONFIRM jest obecny;
  - limit prób wynosi jeden, a stan po próbie jest rekoncyliowany.

Niedozwolone:

- dowolna metoda mutująca, draft, edytor lub reakcja na koncie produkcyjnym;
- live_test bez wszystkich warunków z listy dozwolonej;
- systemd, wdroz.sh i uruchom-dzien.cmd jako droga do testu live;
- test, w którym brak flagi publikacji nadal tworzy draft.

## 10. Hermetyczność

Każdy test offline ustawia:

- tymczasowy katalog danych;
- tymczasową bazę;
- zamrożony czas i losowość;
- fałszywy DNS/HTTP/browser/LLM transport;
- jawnie pusty rejestr możliwości zewnętrznych;
- blokadę gniazd sieciowych;
- kontrolę drzewka plików przed/po.

Test kończy się błędem, jeżeli utworzy plik poza katalogiem tymczasowym lub spróbuje odczytać sekret/sesję.

## 11. Raportowanie

Po każdym teście zapisywane są:

- identyfikator karty naprawy;
- commit i hash fixture'u;
- komenda lub funkcja testowa;
- dozwolone możliwości;
- liczba wywołań i tokenów;
- rzeczywisty koszt;
- wynik każdej metryki;
- nowe ustalenia;
- nieoczekiwane pliki lub próby sieci.

## 12. Aktualny stan

E-007 wykonało 7 dispatchy modeli: 6 odpowiedzi kompletnych i 1 płatną,
niepełną. Łączny koszt znany/estymowany wyniósł 0,07558670 USD. Cztery żądania
Anthropic pochodziły z nieuprawnionego automatycznego ramienia Sonnet w
harnessie, nie z normalnego routingu V3. Ramię usunięto; wynik i koszt pozostają
w dokumentacji jako niezmieniony dowód. Kolejne testy nie mogą zmieniać modelu
na podstawie samego budżetu dostawcy.

E-010 wykonało pełny replay `run.main()` na adapterach fixture: 7/7 testów celu
i 47/47 regresji przed finalnym utwardzeniem launchera. Planowany live rdzenia
ma exact routing, 8 dispatchy bazowo, maksymalnie 11 po rewizji i limit 1,50
USD. Preflight T-103 odmówił przed I/O i dispatch, ponieważ nie istnieje
`agent-v3/.env` i brak kluczy DeepSeek/Anthropic. Nie jest to live PASS;
rezerwacja oraz koszt wynoszą 0 USD do chwili dostarczenia lokalnych kluczy.

E-011/N-010 dodało transakcyjny zapis plik–DB–rewizja–provenance. Fault
injection 7/7 i pełna regresja 48/48 przeszły offline; nie badano rzeczywistego
zaniku zasilania. Koszt 0 USD.

E-012 było pierwotną pełną próbą ról redakcyjnych. Maksimum wynosiło 32 dispatchy:
DeepSeek v4 Pro 14, DeepSeek v4 Flash 10, Claude Fable 5 trzy oraz Claude Opus
5 pięć. Etapy obejmują dwie replikacje skauta, feasibility, discovery,
classify/synthesis/warto_pisac, parę pisarz styl/ablacja, dwóch ślepych sędziów,
kontrolowaną rewizję i pięć form Notes z factcheckiem. Twardy limit nowego
kosztu wynosi 4,50 USD, co daje maksymalną ekspozycję programu 4,57558670 USD
z E-007. Uprząż może użyć tylko modeli i maksymalnie czterech publicznych
fetchy; `substack.com` oraz wszystkie subdomeny są blokowane także do odczytu.

Pełna atrapa wykonała dokładnie 32 granice i przeszła 8/8 po N-023. Po N-011
aktualna regresja wynosi 50/50. E-013 dodało wersjonowaną politykę, dwie
iteracje i trzy terminalne stany; 13/13 scenariuszy PASS, koszt 0 USD. Po
dodaniu lokalnego `.env` wykonano T-118: jeden live `scout` na DeepSeek v4 Pro.
Dostawca zamknął niepełny strumień po 180,86 s. Ledger zapisał `UNKNOWN` z
rezerwacją 1,60 USD, bez retry.

E-014 rozdzieliło dostawców. Ramię Anthropic wykonało 8/8 dispatchy i ma znany
koszt 1,341430 USD. Powstały dwa artykuły, jedna rewizja i pięć Notes, ale wynik
jakościowy jest częściowy: złamana długość wariantu stylowanego, niepoparte
przesłanki w obu artykułach oraz niska różnorodność otwarć Notes. Wszystkie
kandydaty pozostawały `safe_to_post=false`; nie było żadnego dostępu do
Substacka.

Drugie ramię DeepSeek E-014 i skrócona próba E-015 powtórzyły pierwszy Scout
na materialnie różnych promptach. Obie zakończyły się tym samym `incomplete
chunked read` bez odpowiedzi, usage i request ID. T-118, T-132 i T-136 mają
zatem po 1,60 USD `UNKNOWN`, razem 4,80 USD. E-015 obaliło hipotezę, że główną
przyczyną jest długość promptu: wejście skrócono o 67,5%, a awaria pozostała.

N-025 zmieniło adapter DeepSeek na oficjalny streaming SSE. Parser wymaga
końcowego `[DONE]`, usage, niepustej treści i `finish_reason=stop`; przypadki
braku któregokolwiek elementu przechodzą do `UNKNOWN` bez retry. T-139 dał
25/25 PASS offline. Nie wykonano czwartego live żądania: nowy transport nie ma
dowodu live, a kod ma twardą blokadę po trzech `UNKNOWN` do rekoncyliacji.
Pierwsza pełna regresja po kompresji Scouta ujawniła trzy utracone grupy
instrukcji semantycznych; poprawiono prompt, a T-142 dała 52/52 PASS.

E-016 następnie potwierdziło transport SSE live: jeden DeepSeek Pro zwrócił
pełny JSON za 0,032564 USD. Jakość starego Scouta była jednak ujemna: sześć
tematów było nasyconych i proceduralnych. E-017 feasibility kosztowało
0,005868 USD i przeszło; discovery `/responses` zakończyło się `UNKNOWN` z
rezerwacją 0,10 USD. N-026 ma parser SSE `/responses` 4/4 offline.

E-018 wykonało jeden Scout po zmianie jednostki pracy na uniwersum artykułowe.
Transport i kontrakt przeszły, powstało sześć tematów oraz pięć odrzuconych
zalążków. Koszt 0,049298 USD przekroczył cap etapu 0,04 USD. Exact raw replay
po usunięciu arbitralnego minimum pięciu dróg przeszedł 6/6. Uprząż Scout-only
ma teraz predispatch worst-case refusal, lecz wspólny runtime nadal wymaga
N-028. Kolejny live jest zabroniony, bo konserwatywna ekspozycja DeepSeek
przekroczyła jego sublimit.

Aktualne wartości księgi:

| Zakres | znane/estymowane | `UNKNOWN` | konserwatywna ekspozycja | wolny limit |
|---|---:|---:|---:|---:|
| Anthropic | 1,39803400 USD | 0,00 USD | 1,39803400 USD | 3,60196600 USD |
| DeepSeek | 0,10671270 USD | 4,90 USD | 5,00671270 USD | -0,00671270 USD |
| globalnie | 1,50474670 USD | 4,90 USD | 6,40474670 USD | 3,59525330 USD |

Saldo globalne nie znosi sublimitu ani blokady dowodowej. Do uzyskania
rachunku lub innego wiarygodnego dowodu dostawcy nie wolno wykonać kolejnego
DeepSeek. Nie należy również generować kolejnych płatnych próbek Anthropic,
jeżeli nie realizują wcześniej zapisanej, rozstrzygającej hipotezy. Zakaz
zapisu, szkicu, odczytu sesji i jakiejkolwiek mutacji na Substacku pozostaje
bezwzględny.
