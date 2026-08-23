# E-020 — live discovery i ręczny audyt źródeł

**Data:** 2026-08-21  
**Status:** `TRANSPORT_SCHEMA_PASS; MANUAL_OPERATIONAL_FAIL; SOURCE_SET_PARTIAL; FETCH_NOT_RUN`  
**Zakres:** wyłącznie discovery wybranej drogi `Afterlife/orphaned well`  
**Model:** normalny routing V3, `deepseek-v4-pro`; bez override modelu  
**Substack:** zero sesji, odczytu, szkicu, zapisu, publikacji i innych mutacji

## 1. Pytanie badawcze i warunek zaliczenia

Czy normalne discovery V3, otrzymawszy dokładną drogę, mechanizm, potrzebny
dowód i drugi akt, potrafi w jednym logicznym callu znaleźć mały, dostępny i
autorytatywny korpus źródeł do pytania:

> How does an orphaned oil well become a public problem decades after the
> company that drilled it disappears?

Zaliczenie wymagało jednocześnie:

1. nie więcej niż 8 wyszukiwań;
2. prawdziwych URL-i pochodzących z wyników narzędzia, nie z pamięci modelu;
3. co najmniej dwóch dokumentów pierwotnych i dwóch źródeł wyjaśniających
   mechanizm;
4. pełnego tekstu bez loginu;
5. materiału na główny mechanizm i drugi akt;
6. ręcznej kontroli każdego kandydata przed fetch i kolejnym segmentem.

Zielony JSON nie był wystarczającym dowodem. Przekroczenie limitu narzędzia lub
zawyżenie jakości źródła oznacza ręczny FAIL i zatrzymanie potoku.

## 2. Preflight bez dispatchu

Pierwszy preflight wykrył, że lokalny `.env` przechowuje historyczne nazwy
`DEEPSEEK_API_KEY` i `ANTHROPIC_API_KEY`, podczas gdy izolowany V3 wymaga
prefiksów `AGENT_V3_*`. Zakończył się przed dispatch, bez rezerwacji i bez
kosztu. Wartości przypisano wyłącznie w pamięci procesu uruchamiającego test;
nie wypisano ich i nie zmieniono `.env`.

Status próby: `PREFLIGHT_REFUSAL_PASS; NO_DISPATCH; COST_0`.

## 3. Dokładny przebieg live

| Własność | Wynik |
|---|---|
| logiczne calle | 1 |
| retry | 0 |
| czas | 136,016 s |
| tokeny wejścia | 153 385 |
| tokeny wyjścia | 7 360 |
| wywołania `web_search` | **22** |
| koszt | **0,115807 USD KNOWN** |
| wyników URL z narzędzia | 17 |
| kandydatów w raw JSON | 10 |
| kandydatów po exact-URL filter | 8 |
| błędów kontraktu JSON | 0 |
| publicznych fetchy runtime | 0 |
| kontaktów z Substackiem | 0 |

Runner zapisał `pass=true`, ponieważ kontrolował liczbę logicznych calli,
koszt, schemat i exact URL, lecz nie miał postwarunku na faktyczną liczbę
wyszukiwań. Ręczna ocena zmienia werdykt segmentu na FAIL: 22 > 8.

## 4. Reprodukcja i hashe

Pełne system prompt, user prompt oraz raw response znajdują się w pliku:

`.live-experiments/E-019b-scout-route-depth-live/model-captures.json`

Wynik segmentu i księga calla:

`.live-experiments/E-019b-scout-route-depth-live/segment-discovery-result.json`

| Artefakt | SHA-256 |
|---|---|
| system prompt | `b12b84cde976d9a1ed2b3938be7e63f6b1479a7d816105d0c413be1556cc4135` |
| user prompt | `37666dbeb2ede417190bf90fe31481143b45b176a96b48ccc68037c779ce3ce9` |
| raw response | `9197733b77884c376c9c1b6c3379e7798764e5b8a96143fb80bdcbda8a13b648` |

Capture nie zawiera klucza API. Prompt zachowuje dokładne pytanie, mechanizm
`legal disappearance`, rodziny dowodu i drugi akt o kopalniach oraz Superfund.

## 5. Wszystkie źródła zwrócone przez model

| # | Kandydat raw | Po exact URL | Ręczna kontrola | Korekta oceny |
|---:|---|---|---|---|
| 1 | Cornell/LII, 42 U.S.C. § 15907 | KEEP | dostępny; definicja, koszty, programy i dochodzenie odpowiedzialnych stron | pierwotny dokument prawa na niepierwotnym hoście; `PRIMARY_RECORD_MIRROR`, nie origin publisher |
| 2 | California Public Law, PRC § 3206.3 | KEEP | dostępny mirror; rejestr orphan wells, szacunek kosztu i harmonogram | pierwotny tekst na mirrorze; model błędnie spłaszcza rolę hosta |
| 3 | GAO-18-250 | KEEP | dostępny i trafny | mocny origin-primary audit; odpowiedzialność BLM, liczby i luka danych |
| 4 | GAO-10-245 | KEEP | dostępny i trafny | mocny origin-primary audit mechanizmu bond → federal dollars |
| 5 | OSMRE Abandoned Mine Lands | KEEP | dostępny i trafny | mocny origin-primary drugi akt; publiczny fundusz i liczby |
| 6 | Carbon Tracker, *Billion Dollar Orphans* | KEEP | landing page dostępny, pełny report wymaga bezpłatnego loginu | SUPPORTING; nie spełnia literalnie wymogu pełnego źródła bez loginu |
| 7 | Alberta Orphan Well Association, Fiscal Responsibility | KEEP | dostępny | origin-primary wyłącznie dla własnego finansowania i kosztów organizacji |
| 8 | EPA Superfund PRP Manual w archiwum GPO | DROP | proponowany URL nie był dokładnym wynikiem narzędzia | rozsądny kandydat drugiego aktu, ale prawidłowo odrzucony przez exact-URL gate |
| 9 | GAO-09-656 przez UNT Digital Library | KEEP | ręczne otwarcie nie powiodło się | mirror strony raportu; nie wolno liczyć jako zweryfikowane źródło przed fetch |
| 10 | Elementa, peer-reviewed orphan-well article | DROP | proponowany URL nie był dokładnym wynikiem narzędzia | prawidłowo odrzucony przez exact-URL gate |

### Co model zrobił dobrze

- utrzymał dokładną drogę artykułu zamiast wrócić do całego uniwersum;
- znalazł cztery różne rodziny dowodu: prawo, audyty kosztów i bonds, program
  wykonawczy oraz drugi akt kopalniany;
- GAO-18-250, GAO-10-245 i OSMRE rzeczywiście testują mechanizm;
- exact-URL filter odrzucił dwa adresy, których narzędzie nie potwierdziło;
- nie użył Substacka ani runtime fetch.

### Co nie przechodzi ręcznej kontroli

- 22 wyszukiwania mimo jawnego maksimum 8;
- licznik `7/2 primary` miesza dokument pierwotny z autorytetem hosta i zawyża
  jakość mirrorów;
- jeden z ośmiu zachowanych URL-i nie otworzył się w ręcznej próbie;
- jeden zachowany report wymaga loginu do pełnej treści;
- model nie znalazł kilku silniejszych i nowszych źródeł urzędowych, które
  ręczny benchmark znalazł bez problemu.

## 6. Ręczny benchmark brakujących źródeł

Ręczna publiczna kontrola read-only znalazła cztery bardziej bezpośrednie
źródła, których E-020 nie wybrało:

| Źródło | Co wnosi ponad raw E-020 |
|---|---|
| BLM, *Protecting Taxpayers and Communities from Orphaned Oil and Gas Wells on Public Lands* (2024) | bieżące definicje statusów, 9 781 idled wells, ryzyko podatnika, nowe minimalne bonds 150/500 tys. USD |
| GAO-19-615 | 89 nowych orphaned wells, ok. 46 mln USD potencjalnego kosztu, 84% bonds prawdopodobnie za niskich; czysty mechanizm finansowy |
| DOI State Orphaned Wells Program | aktualny program stanowy i ok. 4,2 mld USD środków |
| DOI FY2025 Annual Report to Congress | 4,677 mld USD alokacji i ok. 1,85 mld USD rozdystrybuowanych do końca FY2025 |

To nie dowodzi, że zestaw E-020 jest bezużyteczny. Dowodzi, że nie jest jeszcze
„świetny”: ma wystarczający rdzeń do dalszego researchu, ale gorszy dobór
bieżącego origin-primary materialu niż ręczny baseline.

## 7. Przyczyna przekroczenia limitu

Oficjalny kontrakt DeepSeek `/responses` obsługuje `web_search`, ale nie opisuje
parametru `max_uses`; serwerowa auto-kontynuacja ma własny limit dziesięciu
rund. Liczba elementów `web_search_call` nie musi być równa liczbie rund i w
E-020 osiągnęła 22. Zdanie w prompcie nie było limitem wykonawczym.

DeepSeek udostępnia ten sam model również przez oficjalny interfejs zgodny z
Anthropic. Oficjalna implementacja DeepSeek Harness wysyła tam narzędzie
`web_search_20250305` z polem `max_uses`. Naprawa po E-020 przenosi tylko
transport discovery na ten interfejs; provider i `deepseek-v4-pro` pozostają
bez zmian. Niezależny postwarunek runtime ma zapisać znany koszt i FAIL, jeśli
dostawca mimo wszystko przekroczy limit.

Źródła kontraktu technicznego:

- `https://api-docs.deepseek.com/guides/responses_api`;
- `https://api-docs.deepseek.com/guides/anthropic_api`;
- `https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/web/web-search-deepseek/src/provider.ts`.

## 8. Werdykt

| Granica | Werdykt |
|---|---|
| transport i pełne usage | PASS |
| routing i zero retry | PASS |
| JSON `discovery@1` | PASS |
| exact URL provenance | PASS 8/10 |
| limit wyszukiwań | **FAIL 22/8** |
| dostęp bez loginu | PARTIAL/FAIL |
| rozróżnienie hosta pierwotnego i mirrora | FAIL |
| pokrycie mechanizmu | PASS |
| aktualny origin-primary benchmark | PARTIAL/FAIL |
| zgoda na fetch | **NIE** |

Końcowy status E-020 to `MANUAL_FAIL`. Pipeline zatrzymano przed fetch,
classify, synthesis, write i Notes.

## 9. Budżet po rozliczeniu

E-020 kosztowało 0,115807 USD KNOWN. Po zwolnieniu rezerwacji 0,30 USD:

- DeepSeek KNOWN: 0,26258270 USD;
- DeepSeek UNKNOWN: 4,90 USD;
- konserwatywna ekspozycja DeepSeek: 5,16258270 USD;
- wszystkie koszty KNOWN/EST.: 1,66061670 USD;
- konserwatywna ekspozycja całych badań: 6,56061670/10 USD;
- pozostały globalny margines: 3,43938330 USD.

## 10. Następny eksperyment

Nie uruchamiać fetch na tym zestawie. Najpierw:

1. twarde `max_uses` bez zmiany modelu;
2. postwarunek liczby narzędzi z rozliczeniem znanego kosztu jako FAIL;
3. jawne odróżnienie dokumentu pierwotnego od origin publisher/mirrora i
   dostępności pełnego tekstu;
4. testy offline oraz pełna regresja;
5. jeden kontrolowany live replay discovery i ponowna ręczna kontrola każdego
   URL-a;
6. dopiero po ręcznym PASS osobny segment fetch.

