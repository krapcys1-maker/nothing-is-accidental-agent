# Modele i wyszukiwanie — 13 września 2026

Przegląd konta na prośbę właściciela: „czy wszystko jest ok, czy wychodzą notki,
komentarze" plus „wyszedł DeepSeek V4.1 Flash, może warto zmienić" i „może warto
dopisać coś, żeby automatycznie zmieniało się na nowe modele".

## 1. Konto wychodzi zgodnie z planem

Dziennik działań, 3–13 września, udane/nieudane:

| dzień | notki | komentarze | odpowiedzi | restacki | polubienia |
|---|---|---|---|---|---|
| 09-03 | 10/0 | 8/0 | 4/0 | 1/0 | 10/0 |
| 09-06 | 6/0 | 7/3 | 0/0 | 1/0 | 12/0 |
| 09-08 | 3/0 | 7/0 | 0/0 | 1/0 | 10/0 |
| 09-10 | 3/0 | 8/0 | 2/0 | 2/0 | 12/0 |
| 09-12 | 3/0 | 9/0 | 4/0 | 1/0 | 12/0 |

Spadek notek do trzech od 7 września to decyzja właściciela (commit `cbe5d2c`),
nie awaria. Porażek pięć w jedenaście dni.

## 2. DeepSeek podmienił modele pod naszymi nazwami

Z dokumentacji DeepSeeka, sprawdzone 13 września:

- **10 września 04:00 UTC** wyszedł V4.1 Flash pod nazwą `deepseek-flash`.
  V4 Flash wycofany; nazwa `deepseek-v4-flash` „tymczasowo" trafia do V4.1 Flash,
  bez daty końca.
- **14 września 04:00 UTC** wszystkie wywołania `deepseek-v4-pro` trafiają do
  V4.1 Flash po cenie Flash, aż wyjdzie V4.1 Pro.
- `GET /models` zwraca dziś dwie pozycje: `deepseek-flash`, `deepseek-v4-pro`.

Konto trzy dni chodziło na V4.1 Flash, nie wiedząc o tym.

## 3. V4.1 Flash nie ma wyszukiwania — i to przeszło niezauważone

Żywa próba, to samo pytanie wymagające świeżej wiedzy:

| model | `tool_choice` | wyszukiwań | wynik |
|---|---|---|---|
| deepseek-flash | auto | 0 | pusta odpowiedź, 4000 tokenów wyjścia |
| deepseek-flash | required | 0 | udawane znaczniki `<search_web>` w tekście |
| deepseek-v4-pro | auto | 17 | poprawna odpowiedź |
| deepseek-v4-pro | required | 12 | poprawna odpowiedź |

Skutek na produkcji, tabela `calls`, przed i po 10.09 04:00 UTC:

| etap | przed: wywołań z wyszukiwaniem | po |
|---|---|---|
| factcheck | 170 z 238 | 0 z 38 |
| curiosity | 15 z 44 | 0 z 5 |
| aktualne_modele | 6 z 6 | 0 z 5 |

Etap `factcheck` to na produkcji `stages.zweryfikuj`: weryfikacja faktów
w notkach, komentarzach, poprawkach i artykułach przed publikacją. Przez trzy
dni sprawdzała tekst pamięcią modelu, a nie siecią. Średni koszt spadł z 1,18 do 0,12 centa — dziesięć
razy taniej, bo model nic nie czytał. Nic nie alarmowało, bo każde wywołanie
kończyło się sukcesem. Lista modeli dla pisarza (`aktualne_modele.json`) stała
od 9 września.

Od 14 września to samo spotkałoby odpowiedzi i odkrywanie źródeł do artykułu.

## 4. Czym zastąpić wyszukiwanie

Prompt `stages.sprawdz_fakty` (ta sama rodzina zadania co `zweryfikuj`:
fakty z adresami, bez pamięci), prawdziwy post z korpusu
(„The Epoch Brief — September 12, 2026"):

| wariant | wyszukiwań | koszt | faktów | adresów z wyszukiwarki |
|---|---|---|---|---|
| Claude Haiku 4.5 | 3 | $0,0623 | 8 | 7 z 8 |
| Claude Sonnet 5 | 3 | $0,3131 | 0 | — |
| DeepSeek V4 Pro (13.09) | 7 | $0,0546 | 8 | 6 z 8 |

Haiku daje jakość starego V4 Pro za tę samą cenę. Sonnet pięć razy drożej
i nie oddał JSON-a.

Odkrywanie źródeł do artykułu, prawdziwa funkcja `stages.discovery`, Haiku z
`web_search_20250305`: 6 wyszukiwań, 46 wyników, 4 źródła po filtrze, $0,0917.
DeepSeek V4 Pro dawał tu 17 wyszukiwań za $0,154 i do dziesięciu źródeł.
Sierpniowa notatka „Haiku nie szuka przy tym prompcie" dotyczyła narzędzia
`web_search_20260209`, którego na Haiku nie ma. Opus odpada z liczb: kosztował
tu od $0,46 do $1,65, a przebieg artykułu ma sufit $2,20 przy samym pisaniu
Fable $0,66. **Ryzyko na wtorek 15 września:** cztery źródła z jednej domeny
to mało; przebieg ma drugą rundę dyskoverii przy chudym korpusie.

## 5. Co zmienione

- `DEEPSEEK = "deepseek-flash"`; stara nazwa zostaje w cenniku dla historii.
- **Wyszukiwanie po zdolności, nie po etapie** (`config.szuka_naprawde`,
  `llm.call`). Wywołanie z `web_search=True`, którego model nie szuka, idzie do
  Haiku 4.5. To samo wywołanie bez sieci zostaje na
  tanim modelu etapu — także odkrywanie źródeł do artykułu. Limit wyszukiwań
  na etap: fakty 3, ciekawostki 3, lista modeli 4, odpowiedzi 2, odkrywanie 8.
- **Cennik:** V4.1 Flash 0,15 / 0,60 / 0,003 poza szczytem; `deepseek-v4-flash`
  po stawce V4.1 od 10.09; `deepseek-v4-pro` po stawce V4.1 od 14.09 04:00 UTC.
  Szczyt tylko od poniedziałku do piątku — tak mówi cennik; kod liczył go też
  w weekend. Opłata za wyszukiwanie dla każdego modelu Claude (była tylko dla
  Opusa i Sonneta). Model spoza cennika dostaje stawkę rodziny z `verified: False`
  zamiast `KeyError` po opłaconym wywołaniu.
- **`nowe_modele.py` — automatyczna zamiana.** Raz na dobę: lista od dostawców,
  następca w tej samej rodzinie, próba odpowiedzi, zapis do
  `data/wybor_modeli.json`, zastosowanie od razu. Dla modeli DeepSeeka, które
  dziś nie szukają, codzienna próba wyszukiwania — gdy znów zaczną, wywołania
  z siecią wrócą do nich same. Bez przeskoku między rodzinami, bez wersji
  preview, bez zamiany na starszą wersję, dopóki obecna odpowiada, bez decyzji
  na pustej liście. Każda płatna próba przechodzi przez `_preflight`.
- Testy: `test_wyszukiwanie_przekierowane.py` (31), `test_nowe_modele.py` (41).
  Pierwsze uruchomienie drugiego złapało błąd w module: próby omijały
  `DRY_RUN`, bo `_preflight` go przepuszcza.

## 6. Koszt i ryzyko

Haiku do faktów to około 12 wywołań na dobę po ~6 centów, czyli **+0,70 USD na
dobę**. Etapy Pro od 14 września tanieją czterokrotnie, co oddaje ~0,17.
Netto około +0,55 USD na dobę przy zwykłej dobie ~0,50.

We wrześniu sufit dobowy to 5,00 USD, więc zmiana się mieści. **Od 1 października
sufit miesięczny spada do 40 USD** (~1,29 na dobę) i doba z Haiku plus wtorkowy
artykuł może go dotykać. Decyzja właściciela: zostawić sprawdzanie faktów na
Haiku, zmniejszyć limit wyszukiwań do 2 albo podnieść sufit październikowy.

Od 14 września komentarze, odpowiedzi, rozbiór i restacki dostaną V4.1 Flash
zamiast V4 Pro — to decyzja DeepSeeka, nie nasza. Przeniesienie ich na Claude
kosztowałoby kilka razy więcej; nie zrobione.
