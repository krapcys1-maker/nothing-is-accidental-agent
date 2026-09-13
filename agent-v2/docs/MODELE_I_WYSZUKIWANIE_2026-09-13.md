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
- **V4 Pro zostaje.** Ogłoszenie z 10 września zapowiadało przekierowanie
  `deepseek-v4-pro` na V4.1 Flash od 14 września 04:00 UTC. Cennik i dziennik
  zmian mówią dziś co innego: „In response to user demand, we have decided to
  continue providing API services for DeepSeek V4 Pro after September 14, 2026,
  with the billing method remaining unchanged". Samo ogłoszenie nie zostało
  poprawione, więc tego dnia dwie strony DeepSeeka mówiły dwie różne rzeczy.
- `GET /models` zwraca dziś dwie pozycje: `deepseek-flash`, `deepseek-v4-pro`.

Konto trzy dni chodziło na V4.1 Flash, nie wiedząc o tym.

**Sprostowanie tego samego dnia.** Pierwsza wersja naprawy (`ce64519`) uwierzyła
ogłoszeniu i wpisała Pro przekierowanie rozliczeń oraz utratę wyszukiwania od
14 września. Od jutra liczyłaby etapy Pro ponad cztery razy za tanio, a ich
wyszukiwania wysyłała na Haiku. Wyszło przy żywym teście weryfikacji faktów,
który sam znalazł nową notę DeepSeeka. Poprawione przed wejściem w życie.

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

Odpowiedzi i odkrywanie źródeł do artykułu chodzą na `deepseek-v4-pro`, który
szuka i zostaje, więc ich to nie dotknęło.

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

Zapas na wypadek, gdyby V4 Pro też stracił narzędzie — odkrywanie źródeł do
artykułu, prawdziwa funkcja `stages.discovery`, Haiku z `web_search_20250305`:
6 wyszukiwań, 46 wyników, 4 źródła po filtrze, $0,0917. DeepSeek V4 Pro dawał
tu 17 wyszukiwań za $0,154 i do dziesięciu źródeł, więc dopóki szuka, zostaje.
Sierpniowa notatka „Haiku nie szuka przy tym prompcie" dotyczyła narzędzia
`web_search_20260209`, którego na Haiku nie ma. Opus odpada z liczb: kosztował
tu od $0,46 do $1,65, a przebieg artykułu ma sufit $2,20 przy samym pisaniu
Fable $0,66.

## 5. Co zmienione

- `DEEPSEEK = "deepseek-flash"`; stara nazwa zostaje w cenniku dla historii.
- **Wyszukiwanie po zdolności, nie po etapie** (`config.szuka_naprawde`,
  `llm.call`). Wywołanie z `web_search=True`, którego model nie szuka, idzie do
  Haiku 4.5. To samo wywołanie bez sieci zostaje na tanim modelu etapu.
  Dziś przekierowane są fakty, ciekawostki i lista modeli; odpowiedzi
  i odkrywanie źródeł zostają na szukającym V4 Pro. Limit wyszukiwań Haiku na
  etap: fakty 3, ciekawostki 3, lista modeli 4, odpowiedzi 2, odkrywanie 8.
- **Cennik:** V4.1 Flash 0,15 / 0,60 / 0,003 poza szczytem; `deepseek-v4-flash`
  po stawce V4.1 od 10.09; `deepseek-v4-pro` bez zmian.
  Szczyt tylko od poniedziałku do piątku — tak mówi cennik; kod liczył go też
  w weekend. Opłata za wyszukiwanie dla każdego modelu Claude (była tylko dla
  Opusa i Sonneta). Model spoza cennika dostaje stawkę rodziny z `verified: False`
  zamiast `KeyError` po opłaconym wywołaniu.
- **`nowe_modele.py` — automatyczna zamiana.** Raz na dobę: lista od dostawców,
  następca w tej samej rodzinie, próba odpowiedzi, zapis do
  `data/wybor_modeli.json`, zastosowanie od razu. Codzienna próba wyszukiwania
  na każdym modelu DeepSeeka w użyciu: gdy model zacznie szukać, wywołania
  z siecią wrócą do niego same; gdy przestanie, pójdą do Haiku już
  w następnym przebiegu, zamiast po cichu przez trzy dni. Bez przeskoku między
  rodzinami, bez wersji preview, bez zamiany na starszą wersję, dopóki obecna
  odpowiada, bez decyzji na pustej liście. Każda płatna próba przechodzi przez
  `_preflight`.
- Testy: `test_wyszukiwanie_przekierowane.py` (33), `test_nowe_modele.py` (43).
  Pierwsze uruchomienie drugiego złapało błąd w module: próby omijały
  `DRY_RUN`, bo `_preflight` go przepuszcza.

## 6. Koszt i ryzyko

Haiku do faktów to około 12 wywołań na dobę po ~6 centów, czyli **+0,70 USD na
dobę** przy zwykłej dobie ~0,50. Próba wyszukiwania na V4 Pro dokłada ~3 centy
na dobę.

We wrześniu sufit dobowy to 5,00 USD, więc zmiana się mieści. **Od 1 października
sufit miesięczny spada do 40 USD** (~1,29 na dobę) i doba z Haiku plus wtorkowy
artykuł może go dotykać. Decyzja właściciela: zostawić sprawdzanie faktów na
Haiku, zmniejszyć limit wyszukiwań do 2 albo podnieść sufit październikowy.

DeepSeek zapowiada „wygaszanie" V4 Pro i przejście na V4.1 Pro, bez daty.
Kiedy ten nastąpi, `nowe_modele.py` przestawi rolę Pro sam, a próba wyszukiwania
zdecyduje, czy wywołania z siecią zostaną na DeepSeeku.
