# agent-v2 — księga prac

Jedna strona, aktualizowana po każdym skończonym etapie. Czytaj od góry.

---

## Stan: DZIAŁA. Osiem przebiegów pod rząd zakończonych artykułem.

```bash
python agent-v2/run.py
```

Jedno polecenie, zero pytań do człowieka, artykuł w `data/articles/`.

| etap | model | typowy koszt |
|---|---|---|
| skaut tematów | DeepSeek v4-pro | $0,004 |
| ocena wykonalności | DeepSeek v4-flash | $0,003 |
| dyskoveria źródeł | DeepSeek v4-pro (`/responses` + `web_search`) | $0,04 |
| pobranie | HTTP | 0 |
| klasyfikacja i wyciąg | DeepSeek v4-flash | $0,01 |
| synteza — karta dowodowa | DeepSeek v4-pro | $0,007 |
| **pisanie** | **Claude Fable 5** | **$0,53** |
| recenzja — rozliczanie zdań | DeepSeek v4-pro | $0,01 |
| zapis | SQLite + `.md` | 0 |

**Przebieg: $0,44–0,76** (z Fable'em). Na Opusie było $0,21–0,25, przed
przejściem na DeepSeeka $1,10–1,92.

## Budżet złożoności

| | limit | jest |
|---|---|---|
| pliki `.py` | 10 | **7** |
| tabele | 4 | **4** |
| warstwy do modelu | 1 | **1** (`llm.py`) |

Prompty to pliki `.md`. Zero migracji, triggerów, zgód, kolejek.

## Decyzje właściciela

1. **Nic nie blokuje artykułu.** Cztery bramki zgłaszają uwagi; tekst zawsze
   trafia do szuflady.
2. **Po zrobionym researchu artykuł musi powstać.** Synteza pada → karta
   składana z dowodów bez modelu. Pisarz pada → powtórka na Opusie. Recenzja
   pada → zapis bez niej. Wszystkie trzy sprawdzone.
3. **Pisarz ma swobodę interpretacji.** Fakt wymaga pokrycia; analogia
   i argument nie są faktem, mają być tylko widoczne jako myśl autora.
4. **Skaut nie nazywa instytucji w pytaniu** — to był powód dwunastu tematów
   pod rząd o `gov.uk`.
5. **Fable 5 pisze**, DeepSeek robi całą resztę.
6. **Nic nie wychodzi na zewnątrz.** Publikacja i komentarze nie istnieją.
   Hasła do Substacka wpisuje właściciel; plik z nimi jest w `.gitignore`.

## Osiem ostatnich przebiegów

| przebieg | koszt | słów | źródła | uwagi | tytuł |
|---|---|---|---|---|---|
| 37 | $0,2358 | 1221 | 6/6 | 0 | The Bumps at the Corner Are a Curb in Disguise |
| 38 | $0,2214 | 1220 | 3/6 | 2 | The Square on the Toothpaste Tube… |
| 40 | $0,2082 | 1205 | 3/5 | 2 | The Tag Is Not Talking to You |
| 41 | $0,2503 | 1166 | 3/5 | 0 | The Cap That Won't Let Go… (Opus) |
| 42 | $0,5399 | 1091 | — | 0 | The Cap That Won't Let Go (Fable, A/B) |
| 43 | $0,7633 | 1067 | 1/6 | 0 | The Number on Your Orange… |
| 44 | $0,7511 | 1105 | 6/10 | 1 | The Egg Aisle Is a Legal Document |
| 45 | $0,4436 | 1093 | 6/10 | 3 | The Arrow on Your Fuel Gauge… |

Długość ustabilizowała się w celu (1067–1105) po zmianie promptu i przejściu na
Fable'a; wcześniej ciążyła ku 1220.

## Co złapały testy live

- **Konsola Windows cp1252** wywalała agenta na polskich znakach.
- **Wyszukiwarka bez `max_uses`**: 31 rund zamiast 8, koszt kwadratowy — każda
  runda przesyła całą rozmowę od nowa. Najdroższy błąd tego dnia.
- **Filtr adresów otwierał się przy braku danych** zamiast zamykać i przepuścił
  dziesięć zmyślonych URL-i.
- **Sufity tokenów wpisane obok kontraktu** zamiast liczone z niego: prompt
  klasyfikacji prosił o 8400 znaków przy suficie na 5250.
- **Recenzja ucięta na 28 764 tokenach** — DeepSeek rozumuje obficie.
- **Mój własny próg trafności** wyrzucił najlepsze źródło liczbowe.
- **Dwa miejsca liczyły to samo** (czy liczba jest w korpusie) i dały różne
  odpowiedzi. Duplikat skasowany.
- **Plik z hasłem do Substacka** leżał w repo nieignorowany — jeden `git add -A`
  od wypchnięcia na GitHuba. Historia czysta, nigdy nie trafił do commita.

## Sprawdzone i odrzucone

- **Haiku 4.5 i Sonnet 5 do dyskoverii**: nie wywołują wyszukiwania w ogóle,
  wypisują adresy z pamięci. Także po jawnym nakazie w prompcie.
- **Opus 5 do dyskoverii**: działa, ale nieprzewidywalny kosztowo — te same
  8 wyszukiwań dały raz 52 767, a raz 285 759 tokenów wejścia ($0,46 i $1,65).
- **`tool_choice={"type":"web_search"}` na DeepSeeku**: zapętla model, szuka
  bez końca i nigdy nie tworzy bloku `message`. Musi być `"auto"`.

## Zamówione przez właściciela, jeszcze niezbudowane

- **Grafiki do artykułów.** Artykuły na Substacku mają obrazy, więc potrzebne
  będzie generowanie i dołączanie grafiki. Do zrobienia na końcu, po notkach
  i komentarzach.
- **Samodzielne wyszukiwanie postów do komentowania.** Agent ma sam znajdować
  posty — także pod dużymi kontami i pod postami z wieloma komentarzami, żeby
  wchodzić w dyskusje, z których ktoś może trafić na nasz profil. Dziś czyta
  tylko podane adresy.
- **Bramka dowodowa dla komentarzy.** Artykuły mają pokrycie w pobranych
  dokumentach, komentarze piszą z pamięci modelu. Przed jakąkolwiek publikacją
  automatyczną trzeba to domknąć — publiczny komentarz z błędnym faktem jest
  nieodwracalny.

## Otwarte

- **Skuteczność pobrań waha się od 1/6 do 6/6.** Martwe adresy (404) i blokady
  botów. Częściowo zaadresowane szukaniem dziesięciu źródeł zamiast sześciu.
- **Stawki DeepSeeka niepotwierdzone** — każde takie wywołanie ma w bazie
  `price_verified = 0`. Do sprawdzenia na fakturze.
- **19 testów kontradowodowych z archiwum** — nieprzeniesione. Podłogi
  sprawdzone doraźnie na spreparowanym tekście i łapią.
- **Powtarzalność tematów przy długim działaniu** — reguła „żadnej domeny
  z ostatnich pięciu" istnieje, ale nie była testowana na dłuższej serii.
- **Notki i komentarze nie istnieją** i nie powstaną bez osobnej decyzji.

## Dziennik

### 2026-08-15 — trzy przebiegi z Fable'em, ratunek dyskoverii zadziałał
Przebieg 45: dyskoveria zapętliła się (22 wyszukiwania bez odpowiedzi),
ratunek wybrał z 10 już znalezionych adresów drugim wywołaniem, przebieg
dojechał do artykułu z 7 źródłami pierwotnymi. To była ostatnia ścieżka
awaryjna testowana wyłącznie offline.

Przebieg 43: recenzja padła na suficie tokenów, artykuł został zapisany
z adnotacją — reguła „artykuł musi powstać" potwierdzona na żywo.

### 2026-08-15 — Fable 5 wygrał A/B z Opusem
Na identycznej karcie dowodowej (przywiązana nakrętka): Opus 1204 słowa
i więcej głosu, Fable 1127 słów i **wyłapanie, że przepis jest węższy niż jego
popularne streszczenie** — dotyczy tylko Załącznika C, a nakrętki metalowe
z plastikową uszczelką są jawnie wyłączone. Opus tego nie zauważył.

### 2026-08-15 — DeepSeek v4 przejmuje wszystko poza pisaniem
Przebieg z $1,10 na $0,24. DeepSeek ma server-side `web_search` przez
`/responses`, co zdejmuje z Opusa najdroższy i najbardziej nieprzewidywalny etap.

### 2026-08-15 — pierwszy artykuł, cały łańcuch
Temat „The Bag Of Salad That Puffs Up" → „The Additive With No Number".
Karta dowodowa sama obaliła założenie tematu.

### 2026-08-15 — audyt planu przed budową
Warstwa jakości do przeniesienia „w całości" miała 4 220 linii, 22 pary
zdublowanych liczb i udokumentowany w kodzie przypadek dwóch bramek
zaprzeczających sobie. Napisana od nowa: cztery bramki, żadna nie blokuje.
