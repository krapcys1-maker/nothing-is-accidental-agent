# E-023 — niepełny stream przed discovery i wada trace requestu

**Data:** 2026-08-21 21:32 +03:00  
**Status:** `STOPPED_FAIL_CLOSED; COST_UNKNOWN; FIRST_REQUEST_INCOMPLETE; SELECTOR_NOT_RUN; NO_RETRY`  
**Model:** normalny `deepseek-v4-pro`; bez zmiany providera ani routingu  
**Zakres:** wyłącznie discovery; Scout i feasibility z zaakceptowanego cache  
**Substack:** zero sesji, odczytu, szkicu, zapisu, publikacji i mutacji

## 1. Cel

E-023 miało sprawdzić poprawkę po E-022: bounded web search z
`max_uses=8`, a następnie beznarzędziowy selektor widzący tylko raw draft i
URL-e faktycznie zwrócone przez bieżącą sesję. Było to jedno logiczne zadanie,
ale dwa jawne provider requests tego samego modelu. Oba miały trafić do pełnego
trace.

Przed dispatch:

- 72/72 testów celu PASS;
- 56/56 pełnej regresji PASS w 58,480 s;
- retry=0;
- predispatch worst case poniżej 0,30 USD;
- rezerwacja 0,30 USD;
- fetch, classify, synthesis, writer, Notes i Substack poza zakresem.

## 2. Wynik live

Pierwszy request urwał się po około 7 sekundach podczas odbioru streamu:

```text
RemoteProtocolError: peer closed connection without sending complete message body
(incomplete chunked read)
```

Nie powstała finalna wiadomość, usage, lista wyników wyszukiwania ani raw JSON.
Selector nie wystartował. Normalny runner zakończył przebieg statusem `FAILED`
na etapie `discovery`. Nie było retry.

| Miara | Wynik |
|---|---:|
| logiczne calle | 1 |
| request 1 bounded search | wysłany, stream niepełny |
| request 2 exact-URL selector | 0, nie wystartował |
| usage | brak |
| koszt znany | brak |
| rezerwacja zachowana | 0,30 USD `UNKNOWN` |
| public fetches runtime | 0 |
| Substack | 0 |

Artefakty:

- `.live-experiments/E-019b-scout-route-depth-live/model-captures.json`,
  ordinal 5;
- `.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json`.

Capture zachował pełny outer system/user prompt i ich hashe, błąd oraz czas.
Nie ma response hash, ponieważ nie było kompletnej odpowiedzi.

## 3. Rozliczenie kosztu

Żądanie zostało wysłane, lecz dostawca nie zwrócił usage. Wpis 0 USD byłby
nieuprawnionym założeniem. Całe 0,30 USD pozostaje `UNKNOWN` i blokuje kolejny
request DeepSeek do czasu rekoncyliacji.

Po błędzie wykonano tylko bezpłatne, read-only `GET /user/balance`. O 21:34
+03:00 odpowiedź wskazała dostępność konta i 24,95 USD topped-up balance.
Nie istniał snapshot bezpośrednio sprzed E-023, a endpoint nie pokazuje historii
per request, więc pojedyncza wartość nie pozwala wyliczyć kosztu tej próby.
Nie zapisano ani nie wyświetlono klucza API.

Kolejny bezpłatny snapshot po poleceniu kontynuacji pokazał 24,92 USD. Spadek
o 0,03 USD jest zgodny z możliwością opóźnionego zaksięgowania E-023, ale nie
identyfikuje requestu i nie wyklucza innego użycia konta. Oficjalna dokumentacja
kieruje po szczegóły per API key do eksportu strony Usage. Dostępna przeglądarka
nie miała sesji, a Chrome ani rozszerzenie nie były podłączone. E-023 pozostaje
zatem `UNKNOWN` 0,30 USD; nowy snapshot nie jest arbitralnie traktowany jako
rekoncyliacja 0,03 USD.

Po E-023 konserwatywnie:

- DeepSeek KNOWN: 0,33877270 USD;
- historyczne DeepSeek UNKNOWN: 4,90 USD;
- E-023 UNKNOWN: 0,30 USD;
- DeepSeek exposure: 5,53877270 USD;
- wszystkie KNOWN/EST.: 1,73680670 USD;
- globalna ekspozycja: 6,93680670/10 USD;
- globalny margines: 3,06319330 USD.

## 4. Nowa wada obserwowalności A-129

`provider_request_count` w wyniku E-023 wyniósł 0, chociaż stack trace i wpis
`UNKNOWN` dowodzą wysłanego pierwszego requestu. Przyczyna: provider trace był
dopisywany dopiero po `get_final_message()`. Niepełny body przerywał funkcję
wcześniej.

Naprawa offline tworzy wpis `DISPATCH_STARTED` przed oczekiwaniem na body.
Sukces zmienia go na `COMPLETED_WITH_USAGE`; wyjątek bez usage na
`FAILED_WITHOUT_FINAL_USAGE`. Ta sama zasada obejmuje drugi exact-URL selector.
Kontrtest urwanego streamu przechodzi. Po zmianie testy celu przeszły 73/73 w
2,948 s, a pełna bezpieczna regresja 56/56 w 58,215 s. Oba przebiegi używały
fixture, kill switcha i dry-run; kosztowały 0 USD i nie miały dostępu do
Substacka. Historyczny capture E-023 pozostaje niezmieniony jako dowód wady;
nie jest po fakcie przepisywany na pozornie lepszy.

Końcowy checker T-191 potwierdził: 94/94 plików Python parsuje się do AST,
3/3 widoczne pliki JSON są poprawne, 56/56 linków względnych istnieje,
A-001–A-129 i T-001–T-190 są ciągłe, chronione hashe V2 zgadzają się 3/3,
skan kodu i dokumentacji (z wyłączeniem `.env`, artefaktów live i temp) nie
znalazł sekretów, a `git diff --check` nie zgłosił błędu.

## 5. Wniosek

E-023 nie ocenia jakości source setu ani exact-URL selectora, bo nie dotarło do
tych granic. Dowodzi natomiast, że fail-closed i księgowanie `UNKNOWN` działają,
oraz ujawniało nieprawdziwy licznik requestów w warstwie badawczej. Pipeline
pozostaje zatrzymany przed fetch i wszystkimi etapami tworzenia treści.
