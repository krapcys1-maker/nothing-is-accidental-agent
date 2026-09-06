# Audyt całościowy — prompty, notki, komentarze, statystyki, koszt (6 września 2026)

Zlecenie właściciela: „przeprowadź audyt, chcemy wiedzieć czy można coś
zoptymalizować, poprawić; sprawdź prompty, notki, komentarze, jakość, ich
statystyki; audyt plus raport, przemyślenia, zalecenia, błędy".

## 0. Skąd wzięte liczby i czego NIE robiłem

Wszystko zmierzone na **żywym serwerze** (SSH, tylko odczyt): `dziennik.jsonl`
(889 wpisów, 16.08–06.09), `statystyki.jsonl` (3 991 rekordów, 203 pozycje),
tabela `calls` (2 532 wywołania), `zrodla.jsonl`, `wzrost.jsonl`,
`czytelnicy.jsonl`, dziennik systemowy `nia-agent.service` z 7 dni (30.08–06.09,
6 474 linie). Skrypty pomiarowe leżą w `robocze/aud_*.py` (poza gitem).

- Serwer w chwili startu audytu: `2871faf`; w trakcie doszedł `43ad9cf`
  (tylko dokumentacja). **Zestaw testów na serwerze przy `43ad9cf`: 163
  zdane, 0 oblanych** — uruchomiony przeze mnie po południu.
- **Zero płatnych wywołań modelu z mojej strony.** Cały audyt to odczyt
  plików i bazy. Jedyne zapytanie na zewnątrz to dokumentacja API DeepSeeka
  (poza kontem).
- Nie uruchamiałem żadnego etapu produkcyjnego. Tam, gdzie zalecenie wymaga
  próby na żywo, jest to napisane wprost.

Konto na 6.09 11:28 UTC: **10 subskrybentów, 20 obserwujących**; 31.08 było
7 i 8. Trzy tygodnie od przestawienia na AI (25.08).

---

## 1. NAJWAŻNIEJSZE: „7 subskrypcji z artykułów, 0 z notek" to artefakt przyrządu — Substack mówi odwrotnie

Trzy dokumenty z 6 września (`STATYSTYKI_2026-09-06.md` §3,
`NOTKI_NORMA_PISARZ_SERIE_2026-09-06.md` §3, `SERIE_TEMATYCZNE_2026-09-06.md`),
docstring `seria.py` i codzienny raport `alarm.py przeglad` powtarzają:

    artykuł 7 subskrypcji / notka 0 / komentarz 0 / odpowiedź 0

Ta liczba pochodzi z pola `subskrypcje` przy pozycji, które dla artykułu jest
**`signups_within_1_day`** (`browser.py:1873`, komentarz w `statystyki.py`
przy `new_subscribers`): *ile osób zapisało się w ciągu doby po publikacji,
z dowolnego źródła*. Dla notki tego pola nie ma wcale. Pamięć projektu z
3 września nazwała to wprost („kolumna SUBS NIE jest przypisaniem zapisu")
i kolumna w `raport_statystyk.py` została przemianowana na `ZAP24` — ale
`wzajemnosc.py:1359` drukuje ją nadal jako „POZYCYJNIE (przypisanie SAMEGO
SUBSTACKA, per wpis)", a stamtąd trafiła do trzech dokumentów i do
uzasadnienia nowej funkcji.

**Własne przypisanie Substacka** (`zrodla.jsonl`, 6.09 11:28, okno 30 dni,
dwa niezależne przyrządy zgodne co do osoby: `growth/sources` i karta
`new_subscribers` przy pozycji):

| pozycja Substacka | co to jest naprawdę | zapisów | kto | wyśw. |
|---|---|---|---|---|
| c-322556153 | **notka bota**, 25.08 20:03 (Microsoft/OpenAI) | 1 | Faisal Shahzad Naeem | 42 |
| c-322757850 | **restack bota**, 26.08 02:23, pod Tam Kemabonta PhD | 1 | William Short | **123** |
| c-323761132 | **restack bota**, 27.08 13:37 (cel niezapisany) | **2** | sidharth chandra, Leonard | **469** |
| c-320809275 | tekst w formule restacku („Airline reservation systems hit this…"), ~23.08, brak w dzienniku (restacki do 25.08 bez `id`) | 1 | — | 26 |
| c-329114365 | **notka RĘCZNA właściciela** o Fable 5.1 (z wykresami), 3.09 | 1 | Sherif Saad | 14 |
| substack.com | nieprzypisane | 1 | — | — |
| **artykuły** | | **0** | | |

Czyli: 7 zapisów, z tego **0 z artykułów, 1 z notki bota, 4 z restacków
bota, 1 z ręcznej notki właściciela, 1 nieznany**.

Skąd „7 przy artykułach": „The Watermark Was Never a Verdict" wyszedł 25.08
20:47 i dostał „3" — a Substack przypisuje te osoby notce z 20:03 tego samego
dnia i restackowi z 02:23 nazajutrz. „First, Remove the Brakes" (30.08 21:08)
dostał „2" — to sidharth chandra i Leonard, którzy pojawili się na liście
31.08 między 04:24 a 11:38 (doba po artykule) i których Substack przypisuje
restackowi 323761132 z 27.08 (469 wyświetleń, nadal krążył).

**Skutek:** przesłanka „notki nie prowadzą donikąd", na której 6.09 zbudowano
serie tematyczne, jest odwrócona. Seria może mieć sens (część 2 daje powód,
żeby wrócić), ale nie z tego powodu, i miara sukcesu musi być liczona po
`zapisy_darmowe`/`odwiedziny_profilu` per pozycja, nie po `subskrypcje`.

To jest trzeci raz w tym tygodniu, gdy ten sam przyrząd dał ten sam fałszywy
wniosek; różnica jest taka, że tym razem stanęła na nim funkcja w kodzie.

---

## 2. Restacki — najskuteczniejszy format konta, robiony jak dodatek

Dwie najczęściej oglądane rzeczy w całej historii konta to **restacki z jednym
zdaniem**: 469 i 123 wyświetlenia. Najlepsza notka bota ma 94. Cztery z siedmiu
zapisów przyszły z restacków. Koszt jednego: **0,0057 USD** (pro,
`restack` 16 wywołań / 0,0906 USD w 7 dni) — najtańsza rzecz, jaką konto robi.

Jak ten format jest dziś prowadzony (`RESTACK_DZIENNIE = (1, 2)`, blok
`restacki` jako ósmy z dziewięciu):

| | |
|---|---|
| restacki w dzienniku | 24 (14 z `id`, 10 starszych bez) |
| do jednego autora (Genie) | **7 z 24, 6 z ostatnich 8** |
| formuła „X hit this too / already / the same story" | 6 z ostatnich 8 — dokładnie ta sygnatura, przed którą `restack.md` ostrzega w sekcji „do not announce the move" |
| od 28.08 (12 restacków) | 9–34 wyśw., 0 zapisów |

Dwa duże wyniki są z 26–27.08 i mogą być odstające (oba pod cudzymi notkami
o centrach danych, które same miały publiczność). Ale przy tej cenie
sprawdzenie, czy to się powtarza, kosztuje grosze — a dziś eksperyment jest
z konstrukcji niemożliwy, bo sześć z ośmiu ostatnich restacków poszło pod tego
samego autora.

---

## 3. Komentarze — dane są jednoznaczne, a decyzja z 6.09 stoi na źle przypisanych liniach logu

Wszystko od 25.08, n = 97 komentarzy z wiekiem ≥ 1 dnia, reakcje liczone po
numerze naszej treści (`czego`), nie po typie.

**Gdzie i pod czym:**

| cecha | n | z reakcją | reakcji/szt | wyśw. |
|---|---|---|---|---|
| pod cudzą **notką** | 38 | **42%** | 0,66 | 1,7 |
| pod cudzym artykułem | 59 | 15% | 0,20 | 0,4 |
| cel z **kanału** | 27 | **56%** | 0,89 | 1,9 |
| cel z wyszukiwarki (wszystkie hasła) | 60 | 5–10% | | |
| wiek celu < 24 h | 18 | **50%** | | |
| wiek celu > 30 dni | **56** | 14% | | |
| reakcji pod celem ≤ 10 | 19 | 53% | | |
| reakcji pod celem > 200 | 28 | 14% | | |
| komentarzy przed nami 0 | 23 | 43% | | |
| komentarzy przed nami 4–10 | 21 | 14% | | |

**Postawa:** ROZSZERZENIE 45%, PYTANIE 43%, CIEKAWOSC 20%, KONKRET 9%,
MECHANIZM 8%, SPRZECIW/KOREKTA/ZGODA 0 z 7. **Długość:** > 50 słów 43%
z reakcją, ≤ 25 słów 18%. To powtarza wyniki `ANALIZA_KOMENTARZY_2026-09-05.md`
na większej próbce, z tymi samymi kierunkami.

**Styl jest w porządku bez żadnej bramki:** em dash 0/105, średnik 0/105,
słownictwo zakazane 0/105. „Ktoś w zdaniu" (you/your) wzrosło z 33% do 47%
po prompcie z 2.09.

### 3.1. Dlaczego przydział nie został przestawiony — i dlaczego ten powód jest błędny

Commit `6ad0bb8` (6.09) odrzucił przeniesienie przydziału z artykułów pod
notki, bo „dyskusje (pod notkami): 38 × MILCZY, 13 opublikowanych — model
prawie zawsze milczy, i słusznie", cytując powody: *„Pure praise with nothing
to build on"*, *„The comment is only an emoji"*.

Te powody nie pochodzą z bloku dyskusji. To są zdania z `odpowiedz.md`
(zasada „when to stay silent"), czyli z bloku **odpowiedzi** — milczenie pod
emoji i pod „great piece" pod naszymi własnymi notkami. Policzone po nagłówku
bloku w dzienniku systemowym z 7 dni:

| blok | linii MILCZY |
|---|---|
| `-- odpowiedzi --` (odpowiedzi na emoji/pochwały) | **36** |
| `-- dyskusje --` (komentarz pod cudzą notką) | 10 |
| `-- komentarze --` (pod cudzym artykułem) | 1 |

Blok dyskusji milczy przy 10 na 47, nie „prawie zawsze". A 13 opublikowanych
pod notkami to nie skutek milczenia, tylko dwóch innych rzeczy:

1. **Przydział**: artykuły biorą `N` (`run.py:1685`), dyskusje
   `max(1, N // 2)` (`run.py:1836`).
2. **Czas**: blok dyskusji jest **szósty z dziewięciu** i był ucinany
   komunikatem „czas przebiegu wyczerpany — odpuszczam dyskusje" **7 razy
   w 7 dni** (komentarze 3 razy, notki 2). Kanał z najlepszym wynikiem
   dostaje resztki czasu po kanale z najgorszym.

Do tego `kanal.wartosc_celu` (kanal.py:70) w grupie „nie ma tłoku"
(≤ `KOMFORTOWO_KOMENTARZY = 25` komentarzy) sortuje po **największej**
liczbie reakcji — a pomiar mówi, że reagują autorzy małych wpisów (≤ 10
reakcji: 53%; > 200: 14%). Próg tłoku 25 jest pięć razy za wysoki (dane:
spadek między 3 a 10 komentarzami przed nami).

### 3.2. Płatne oceny tego samego odrzuconego celu

W 7 dniach etap `cele` **275 razy ponownie ocenił wpis, który już wcześniej
odrzucił**; 82 z 211 odrzuconych tytułów wraca w więcej niż jednym przebiegu.
Rekordziści to rumuńskie wpisy z kanału czytelnika: „Mâinile care ne salvează"
18 przebiegów, „Via Transilvanica cu un copil de 15 luni" 17 — oceniane
codziennie przez model, który za każdym razem odpowiada, że nie zna języka.
Etykieta `wrong_language` w `komentarz.md` i „posts in a language you cannot
read" w `cele.md` nigdy nie zadziałały (0 wykryć), bo języka nie sprawdza kod,
tylko model po zapłaceniu za ocenę. Sam koszt jest mały (ocena to ~0,012 USD
przy 15 tys. tokenów rozumowania), ale to 275 z ~1 400 ocenionych pozycji.

Inne straty w lejku, 7 dni: „komentarze tylko dla płacących" 17, „JUŻ SIĘ TAM
ODEZWALIŚMY" po napisaniu 7 (w ANALIZIE z 5.09 było 75 i 15 na 14 dni — spadek
jest, mechanizm został).

---

## 4. Koszt — pod sufitem, ale największa dźwignia nadal nietknięta

**Produkcja po poprawkach z 5.09** (spiżarnia, rekord do weryfikatora,
`effort=medium` dla Opusa), tor `dzien`, pełna doba 5.09: **0,857 USD**
(8 notek, 6 komentarzy, 1 odpowiedź, 2 restacki). Sufit październikowy:
1,29 USD/dobę. Mieści się.

Co się potwierdziło na żywo (koszt na wywołanie):

| etap | 4.09 | 5.09 | 6.09 | co zadziałało |
|---|---|---|---|---|
| `curiosity` | 0,154 (448 k tokenów wejścia, 19,8 szukań) | 0,020 | 0,017 | spiżarnia |
| `factcheck` | 5,0 szukań | 3,8 | 2,2 | rekord do weryfikatora |
| `note` (Opus) | 0,094 (2 388 tok. wyjścia) | 0,0445 (862) | 0,040 (821) | `effort=medium` |

**Rozumowanie DeepSeeka.** Dokumentacja DeepSeeka: na `chat/completions`
tryb myślenia jest **domyślnie włączony z `reasoning_effort: high`**,
sterowany parametrem `thinking: {"type": "enabled|disabled",
"reasoning_effort": "low|high|max"}`. `llm._call_deepseek` (llm.py:451)
**nie wysyła tego parametru**. `DEEPSEEK_EFFORT = "low"` trafia wyłącznie do
`/responses` (llm.py:340) — czyli do curiosity, discovery, factcheck,
aktualne_modele i reply. Twierdzenie z `KOSZT_2026-09-05.md` §7a („DeepSeek ma
jedno wspólne DEEPSEEK_EFFORT=low — już najniższe") jest nieprawdziwe dla
wszystkich etapów na `chat/completions`: cele, bank, parowanie, powtorka,
classify, comment, restack, wybor, review, forma, synthesis, warto_pisac,
naprawa_komentarza, bibliotekarz, fedreg, grafika.

Ile to kosztuje (produkcja, 7 dni, tokeny wyjścia i ich cena):

| etap | wywołań | tokenów wyjścia | na wywołanie | koszt wyjścia |
|---|---|---|---|---|
| `cele` (flash) | 82 | 1,16 M | 14 180 | 0,77 |
| `comment` (pro) | 293 | 0,65 M | 2 219 (komentarz ma ~80) | 1,29 |
| `bank` (flash) | 19 | 0,62 M | 32 572 | 0,41 |
| `parowanie` (flash) | 12 | 0,22 M | 18 595 | 0,15 |
| review/forma/synthesis/wybor/restack/naprawa_kom. (pro) | 38 | 0,22 M | | 0,43 |
| **razem** | | | | **≈ 3,1 USD / 7 dni** |

W tym oknie to ~0,44 USD/dobę; po zmianach z 5–6.09 (parowanie raz na zmianę
zbioru, mniej komentarzy) około **0,3 USD/dobę ≈ 9 USD/mies. ≈ 22% budżetu
październikowego** — za rozumowanie w etapach, z których większość wybiera
z listy albo grupuje. To jest największa niewykorzystana dźwignia kosztowa
i da się ją sprawdzić za grosze (punkt 8, zalecenie R4).

Drobiazgi kosztowe:

- `aktualne_modele` chodzi **codziennie** (163–291 k tokenów wejścia,
  14–16 szukań, 0,036–0,076 USD) — ~1,5 USD/mies. za pytanie „jakie modele
  istnieją", które zmienia odpowiedź raz na tydzień.
- `comment`: 293 wywołania na ~72 wystawione komentarze w 7 dni (4 na 1):
  oceny celów, które potem odpadają na płatnych hostach, „już byliśmy",
  ucięciu czasu.
- Przebieg 155 (6.09 04:09 UTC, `artykul`, **tryb produkcja**, 0,137 USD:
  wybór + discovery + 4 × classify + synthesis) nie ma śladu w journald
  żadnej jednostki systemd — uruchomiony ręcznie, zaksięgowany jako
  produkcja. Obok przebieg 156 o 04:12 w trybie test. Ta sama klasa, co
  „53% rachunku to moje uruchomienia" z `KOSZT_2026-09-05.md`.

---

## 5. Notki — jakość po przepisaniu promptu (4.09) i to, czego prompt nie łapie

Od 25.08: 56 notek bota (54 ze statystykami). **Obcięcie tekstu do 300 znaków
w dzienniku jest naprawione od 2.09** (34 starsze wpisy obcięte, 0 od 2.09);
teksty poniżej są pełne.

### 5.1. Liczby (notki ≥ 2 dni, n = 40)

| cecha | n | wyśw. | polub. | odp. | odwiedz. profilu |
|---|---|---|---|---|---|
| Opus (od 3.09) | 7 | 24,7 | 3,86 | 0,57 | 0,14 |
| DeepSeek pro (od 3.09) | 6 | 27,5 | 3,83 | 0,17 | 0,50 |
| kończy się zdaniem o „you/your" | 7 | 26,4 | 3,29 | 0,29 | 0,14 |
| nie kończy się tak | 33 | 34,3 | 3,52 | 0,73 | 0,55 |
| ma liczbę w treści | 28 | 34,7 | 3,43 | **0,86** | 0,50 |
| bez ani jednej liczby | 12 | 28,8 | 3,58 | 0,17 | 0,42 |
| typ MYSL | 4 | 28,8 | 3,50 | **0,00** | 0,00 |
| godzina 19–20 UTC (15–16 ET) | 9 | 33–40 | | | |
| godzina 11–12 UTC (7–8 ET) | 13 | 27–29 | | | |

Próbki są małe i nic z tego nie jest dowodem. Trzy rzeczy warte zapisania:

- Opus/DeepSeek: nadal nie do odróżnienia (decyzja czeka na ~17.09, zgodnie
  z planem). Różnica ceny po `effort=medium` to 0,040 wobec 0,014 USD
  za notkę, ~4 USD/mies. przy pięciu notkach Opusa dziennie.
- **Zakończenie „coś z twojego życia"** jest nakazane w TRZECH miejscach
  (`notka.md` reguła 4, forma ZACZEP_I_KONKRET, forma WYJASNIENIE) i pojawia
  się w 15 z 40 ostatnich notek. Notki tak zakończone mają mniej odpowiedzi
  i odwiedzin profilu. To jest ta sama klasa sygnatury, którą audyt promptów
  z 23.08 opisał przy artykułach: nakaz pozycji staje się tikiem.
- **Godziny**: własne dane wskazują popołudnie ET, nie 6–8 rano z cudzych
  analiz w `ZASADY_NOTEK_I_KOMENTARZY.md` (stałe `BEST_NOTE_HOURS` i tak są
  nieużywane). Za mało danych, żeby cokolwiek przestawiać; wystarczająco,
  żeby nie kopiować tamtych liczb do promptów.
- MYSL bota: 0 odpowiedzi na 4. Ręczne notki-pytania właściciela z tego
  samego okresu: 35–52 wyświetlenia, 2 odpowiedzi. Typ wprowadzono, bo takie
  notki u wzorcowych kont zbierają rozmowę; u bota na razie nie zbierają.

### 5.2. Powtórki historii, których parowanie nie zatrzymało

- **Agenci OpenAI na publicznych wiki**: 4 notki w 24 godziny — 330206949
  (ARTYKUL, 5.09 11:43), 330236023 (12:44), 330418790 („Weeks.", 17:34),
  330869146 (6.09 11:38). Do tego dwa z tych faktów to „jeden plus szczegół"
  (13 000 edycji; DseWiki 25-letnia), czyli definicja tej samej historii z
  `parowanie.md`.
- **Pelikan**: 330527542 (20:30) i 330629048 (23:51) tego samego wieczoru —
  dwa fakty z jednego wpisu Simona Willisona.

Mechanizm jest sprzeczny sam ze sobą: furtka wydarzeń zamawia **wiele faktów
o jednym zdarzeniu** (`wydarzenia_obsluzone`: Fable 5.1 → `ile: 8`; 6.09
11:32 „NOWE (2) — otwieram furtkę mimo sufitu banku"), a parowanie ma je
potem scalać jako tę samą historię. Czytelnik widzi to samo, co 31.08 przy
trzech notkach o GLM-5.3 — tylko że tym razem to zamierzone przez jeden
mechanizm i zabronione przez drugi.

### 5.3. Trzy rzeczy w samych tekstach

- 330502895 (MYSL, 5.09): *„I do this constantly, and I only noticed last
  week"* — zmyślone przeżycie z datą. Notki nie mają podłogi na zmyślone
  przeżycie (PROGRESS, „Otwarte"); komentarze i odpowiedzi mają. Najsłabsza
  notka tygodnia (8 wyśw., `nad_wzorcem` 0,38).
- 330869146 (6.09): *„the natural assumption is that a benchmark sent it
  there"* — wyprodukowane założenie, którego `ciekawostki.md` zakazuje
  („do not manufacture the assumption").
- 330888668 (6.09): notka o **jednej poprawce w wydaniu rc4 vLLM** — fakt
  z furtki wydarzeń, który nie przeszedłby przez test „obcy przestaje
  przewijać".

### 5.4. Wykrywacz żargonu karmi prompt fałszywym przykładem

`terminy_insiderskie` uznaje za termin każdą nazwę ze zlepkiem wielkich
liter w środku (reguła `^[A-Z][a-z]+[A-Z]`) i liczy **„OpenAI" i „OpenAI's"
osobno**. Notka 330869146 dostała w logu „3 terminy: OpenAI, DseWiki,
OpenAI's" — próg 3 osiągnięty dwoma prawdziwymi terminami i jedną nazwą firmy,
którą zna każdy. Ta notka trafi teraz do promptu jako „notes of ours a reader
had to stop and decode", ucząc pisarza, że „OpenAI" jest żargonem.

### 5.5. `fakt_ranga` — nadal same `None`, ale to jeszcze NIE jest dowód przeciw naprawie

W 10 z 10 notek od 5.09 pole ma `None`. Najpierw napisałem tu „naprawa nie
działa" i skreślam: poprawka (`6ef1320`, 5.09 22:53 czasu lokalnego) weszła
na serwer dopiero **6.09 o 02:25 UTC** (`git reflog`), czyli po wszystkich
ośmiu notkach z 5.09. Jedyne dwie notki wystawione po niej (6.09 11:38
i 12:19) przyszły furtką wydarzeń („NOWE (2) — otwieram furtkę"), a fakt
z furtki nie ma rangi z konstrukcji. Przyrząd do sprawdzenia, czy ranking
banku cokolwiek przewiduje, wciąż nie zapisał ani jednej rangi — ale nie
miał jeszcze na czym. Sprawdzić po pierwszej notce z banku (nie z furtki)
po 6.09.

### 5.6. Zapora „ta sama nazwa" — strata z 5.09 wieczorem sprzed naprawy

Przebiegi 153 (21:35 UTC) i 154 (23:40 UTC) z 5.09: zapora odrzuciła
odpowiednio 10 i 12 kandydatów (`astra`, `google`, `anthropic`, `openai's`,
`claude`), oba skończyły z „cała pula zderza się z pamięcią" i „kończę dzień
krócej", po jednej notce zamiast dwóch — stąd 8 notek zamiast 10 tego dnia.
To jest dokładnie przypadek opisany w `AUDYT_BADAWCZY_WYNIK_2026-09-06.md`
(„po naprawie blokowała 123 nazwy ze 124"), naprawiony w `d1e08f6`
(na serwerze od 6.09 02:50 UTC). Pierwszy przebieg po naprawie (157, 11:27)
odrzucił 4 kandydatów (`california`, `json`, `blender`, `simon`), nie
zablokował puli i wystawił swoje dwie notki. Jeden przebieg to nie dowód,
ale kierunek jest właściwy.

---

## 6. Seria tematyczna (`seria.py`) — trzy rzeczy do naprawy zanim ruszy

Stan: na serwerze **nie ma `seria.json`**, w dzienniku systemowym z 7 dni
**0 linii `[seria]`** — mechanizm nie odpalił się jeszcze ani razu. Zgodnie
z zasadą z pamięci: wdrożone ≠ sprawdzone.

1. **Bramka „jedna część na dobę" liczy dobę po UTC** (`_dzis`,
   `czesc_na_dzis`), a przebiegi wychodzą codziennie o ~21:35 i ~23:40 UTC
   (5.09: 21:35/23:40; 4.09: 21:32/23:46; 3.09: 22:18/23:45). Część N
   wystawiona o 22:30 UTC i część N+1 o 00:05 UTC to **95 minut odstępu
   u czytelnika** (18:30 i 20:05 w Nowym Jorku). Obietnica „część 2 jutro"
   pęknie w pierwszym tygodniu. Poprawka: doba w `PUBLISH_TIMEZONE` albo
   minimum 18 h od poprzedniej części.
2. **Seria omija straż różnorodności.** `wybierz_fakt` bierze fakt PRZED
   `wybierz_material`, więc nie przechodzi przez pamięć wystawionych
   (`_o_tym_samym`, `wspolna_nazwa`, teksty ostatnich notek). Część serii może
   być bliźniakiem zwykłej notki sprzed dwóch dni, którą parowanie nie
   scaliło.
3. **Przesłanka w docstringu i w dokumencie jest odwrócona** (punkt 1). Sama
   miara sukcesu (odwiedziny profilu i zapisy części 4 wobec części 1) jest
   dobra i zostaje.

Drobne: dopasowanie po prefiksie (`\bgrid`, `\bcourt`, `\braised`,
`\bmargin`) łapie „gridlock", „courtesy", „raised the question", „marginal";
próg 5 to łagodzi, ale „Kto na tym zarabia" dostaje punkt za każde „raised".

---

## 7. Prompty — co jest nie tak i co jest martwe

Kod czyta 24 pliki (`_prompt(...)` w `stages.py`); sprawdziłem wszystkie.

**Nieużywane albo nieaktualne w `prompts/`:**

| plik | stan |
|---|---|
| `po_ludzku.md` | mówi „dołączany do promptów", **nie jest czytany przez kod**; jego treść stoi skopiowana w `komentarz.md` i `odpowiedz.md` — trzy kopie jednej reguły, które rozjadą się przy pierwszej poprawce |
| `ZASADY_NOTEK_I_KOMENTARZY.md` | 33–64 słów (dziś 33–120/200), 15–20 komentarzy dziennie (dziś 7–9), 4 artykuły miesięcznie (dziś tygodniowo), „decyzja BLOCK" (nie istnieje od 15.08) |
| `ROZWOJ_KONTA.md`, `SKAD_BRAC.md` | research i lista przenosin z 15.08, nieczytane |
| `historia_startowa.json` | tytuły sprzed ery AI („Two Lorries Overtaking…"); `recent_angles` sięga po nie tylko przy < 5 artykułach, jest 16 — martwy plik |

**`komentarz.md`** (~2 300 słów na komentarz o 35 słowach; cache DeepSeeka to
łagodzi, 881 k trafień w 7 dni):

- „Two to four sentences. One idea." stoi obok „Aim for about `{cel_slow}`
  words", gdzie `cel_slow` = 12 z wagą 3/9. Dwa polecenia, jedno musi przegrać;
  wygrywa dłuższe (≤ 15 słów: 12% zamiast 33%), i słusznie — krótkie dostają
  najmniej reakcji. Zapis `cel_slow` do dziennika (ANALIZA §7) nadal
  niewdrożony, więc nie da się policzyć, czy model go czyta.
- `wrong_language` to etykieta bez kodu (punkt 3.2).
- Sekcja „How not to read as a machine" jest przestrzegana w 105/105 bez
  bramki — można ją skrócić do trzech zdań.

**`cele.md`**: `why_not` obowiązkowe dla każdej odrzuconej pozycji — 275
razy na tydzień dla wpisów już raz odrzuconych. Koszt siedzi w rozumowaniu,
nie w tym polu (KOSZT §7a ma tu rację), ale brak pamięci odrzuceń to strata
niezależna od promptu.

**`bank.md`**: 30–36 k tokenów wyjścia na wywołanie przy `effort=high`
(punkt 4); format odpowiedzi (`drugi_kat`, `czego_brakuje` nigdy puste,
`katy`) jest dobrze uzasadniony i zostaje.

**`notka.md`** po przepisaniu z 4.09 (1 147 słów) jest w dobrym stanie;
zastrzeżenia: potrójny nakaz zakończenia (5.1), cudze badanie („35 percent
fewer subscribers") wpisane jako fakt, dynamiczne bloki z własnymi złymi
zdaniami dostają fałszywy przykład z wykrywacza żargonu (5.4).

**`pisarz.md`** wobec audytu z 23.08: K1 (akapit granic kontra rozproszenie)
częściowo pogodzone („a single honest admission may also stand alone inside
the paragraph that raises it"), K5 rozwiązane (próg sześciu słów podany
wprost), nakaz „Open with the collision" złagodzony do „open with whatever
this card actually holds". N2 („every number literally in `citable_numbers`")
bez zmian — nadal niewykonalne dosłownie, wykonywane w węższej wersji.

**`weryfikacja.md`, `ciekawostki.md`, `skaut.md`, `synteza.md`,
`dyskoveria.md`, `parowanie.md`, `powtorka.md`, `naprawa.md`, `restack.md`,
`forma.md`, `recenzent.md`, `wykonalnosc.md`, `bibliotekarz.md`,
`grafika.md`, `fedreg.md`, `klasyfikacja.md`, `warto_pisac.md`,
`kogo_odpowiedziec.md`, `odpowiedz.md`**: spójne z kodem, który je woła;
nic do naprawy poza tym, co wyżej.

---

## 8. Zalecenia — w kolejności spodziewanego skutku

Każde z: co, gdzie, ile kosztuje, po czym poznać, kiedy cofnąć.

**R1. Naprawić przyrząd zapisów, zanim ktokolwiek podejmie kolejną decyzję.**
`wzajemnosc.py:1359` ma liczyć `zapisy_darmowe` i `kto_sie_zapisal` per
pozycja (już są w `statystyki.jsonl`), a nie `subskrypcje`; etykietę
„przypisanie Substacka" zostawić tylko przy tym polu. Poprawić §3 w trzech
dokumentach z 6.09 i docstring `seria.py`. Koszt: zero. Sprawdzenie:
`alarm.py przeglad` ma pokazać restacki i notki z zapisami, artykuły 0.

**R2. Restacki: z dodatku zrobić eksperyment.** `RESTACK_DZIENNIE` (1, 2) →
(3, 4); limit **jeden restack na autora na tydzień** (dziś 6 z 8 do Genie);
blok `restacki` przed `polubienia`; w `restack.md` zdjąć „the one move you
have" i zostawić przykłady bez formuły. Koszt: +0,01 USD/dobę. Miara:
`odwiedziny_profilu` i `zapisy_darmowe` per restack po 14 dniach (dziś 2 z 13
z zapisem). Cofnąć, jeśli po 30 restackach do różnych autorów żaden nie
przekroczy 40 wyświetleń — wtedy 469 i 123 były przypadkiem.

**R3. Komentarze: odwrócić przydział i kolejność.** (a) `run.py:1836`
dyskusje `N`, `run.py:1685` artykuły `max(1, N // 2)`; (b) blok `dyskusje`
przed `komentarze`; (c) `KOMFORTOWO_KOMENTARZY` 25 → 5 i w `wartosc_celu`
w grupie „jest miejsce" preferować **mniej** reakcji, nie więcej; (d) w
`szukaj_nowych` odrzucać cele starsze niż 14 dni (pole `data` jest); (e)
pamięć odrzuconych celów na 14 dni po adresie (plik jak
`gdzie_komentowalismy.json`), (f) zapisywać `cel_slow` do dziennika. Koszt:
zero; oszczędność ~275 ocen/tydzień. Miara: udział komentarzy z reakcją
(dziś 15% A / 42% B) i liczba **różnych** reagujących autorów. Cofnąć
(a)–(c), jeśli po 60 komentarzach udział B z reakcją spadnie poniżej 20%
albo ponad połowa reakcji B przyjdzie od trzech osób (Genie ma już 8).

**R4. DeepSeek: sterować myśleniem tam, gdzie model tylko wybiera.**
W `llm._call_deepseek` dodać `"thinking": {"type": "enabled",
"reasoning_effort": <z config>}` z tabelą per etap: `low` dla cele, powtorka,
classify, parowanie, wybor, grafika; `high` (jak dziś) dla comment, restack,
review, forma, synthesis, bank — do rozstrzygnięcia próbą. **Najpierw test na
żywo, `NIA_TRYB=test`**: pięć tych samych list celów przez `cele` przy `low`
i `high`, porównać wybór (worth_it) i tokeny wyjścia. Koszt próby < 0,15 USD.
Spodziewana oszczędność 4–7 USD/mies. (10–17% budżetu październikowego).
Cofnąć dla etapu, w którym `low` zmienia wybór w więcej niż 1 z 5 list.

**R5. `aktualne_modele` raz na tydzień** (albo przy wykryciu premiery
w kanałach), wynik trzymany w `data/aktualne_modele.json`, który już
istnieje. ~1,3 USD/mies.

**R6. Seria: trzy poprawki z punktu 6** — doba w strefie czytelników albo
≥ 18 h; fakt serii przepuszczony przez tę samą straż, co zwykła notka;
docstring. Sprawdzić na żywo pierwszą serią i policzyć część 4 wobec 1 po
trzech dniach od części 4, nie nazajutrz.

**R7. Notki.** (a) Furtka wydarzeń: **jedna notka na wydarzenie na dobę**
(dziś Fable 5.1 zamówiła 8 faktów), reszta faktów zostaje w banku na kolejne
dni — wtedy parowanie i furtka przestają się kłócić. (b) Nakaz zakończenia
„z życia czytelnika" zostawić w JEDNEJ formie (ZACZEP_I_KONKRET), z reguły 4
w `notka.md` zrobić dopuszczenie, nie obowiązek; zmierzyć po dwóch tygodniach
na `nad_wzorcem_24h`. (c) `terminy_insiderskie`: sklejać formę dzierżawczą
z rdzeniem i wyłączyć nazwy firm, które zna czytelnik gazety (OpenAI, Google,
Anthropic, Microsoft, Nvidia, Meta, Apple). (d) Podłoga na zmyślone przeżycie
dla MYSL jako **log** przez tydzień („I noticed last week", „I asked N
people", „yesterday I"), dopiero potem ewentualnie bramka — z pamięcią
o cofniętej wersji z 1.09.

**R8. Prompty — sprzątanie.** `po_ludzku.md` jako jedyne źródło wklejane
przez `_prompt` do komentarza i odpowiedzi (jedna kopia zamiast trzech);
`ZASADY_NOTEK_I_KOMENTARZY.md` oznaczyć jako historyczne albo poprawić cztery
liczby; `historia_startowa.json`, `ROZWOJ_KONTA.md`, `SKAD_BRAC.md` do
`archiwum/`; w `komentarz.md` usunąć „Two to four sentences" (zostaje
`cel_slow`) i sprawdzać język celu kodem przed płatną oceną (biblioteka do
wykrywania języka albo prosty test alfabetu/stop-słów — rumuńskie wpisy
z kanału czytelnika to 35 ocen tygodniowo).

**R9. Przyrząd.** `nasz_id` przy odpowiedziach: 8 z 52 (DO_ZROBIENIA §6,
otwarte); `fakt_ranga` (5.5) — sprawdzić na pierwszej notce z banku po 6.09,
czy pole dostaje liczbę; ręczne przebiegi `--artykul` poza zegarem mają
domyślnie iść torem `test` (przebieg 155).

---

## 9. Błędy (lista do odhaczenia)

| # | gdzie | co | waga |
|---|---|---|---|
| B1 | `wzajemnosc.py:1359`, 3 dokumenty z 6.09, `seria.py` docstring | `signups_within_1_day` podpisane jako przypisanie Substacka; wniosek odwrócony | wysoka — decyzje |
| B2 | commit `6ad0bb8` | „38 × MILCZY w dyskusjach" to linie bloku odpowiedzi; decyzja o przydziale stoi na tym | wysoka — decyzje |
| B3 | `llm.py:451` `_call_deepseek` | brak parametru `thinking`; domyślnie `high`; `DEEPSEEK_EFFORT` działa tylko na `/responses` | wysoka — koszt |
| B4 | `seria.py` `_dzis`/`czesc_na_dzis` | doba UTC przepuszcza dwie części w 95 min u czytelnika | średnia (jeszcze nie odpaliło) |
| B5 | `stages.notki_dnia` gałąź serii | seria omija `wybierz_material` i pamięć wystawionych | średnia |
| B6 | `run.py` kolejność bloków + `zostal_czas` | dyskusje ucinane 7 × w 7 dni, komentarze 3 ×, notki 2 × | średnia |
| B7 | `stages.terminy_insiderskie` | „OpenAI" i „OpenAI's" liczone osobno; nazwa firmy jako żargon; wynik idzie do promptu | niska, ale zatruwa prompt |
| B8 | `run.py` blok komentarze/dyskusje | brak pamięci odrzuconych celów: 275 ponownych płatnych ocen / 7 dni | niska — koszt |
| B9 | `komentarz.md`/`cele.md` | `wrong_language` nigdy nie działa; kod nie sprawdza języka | niska |
| B10 | `notki_dnia` | `fakt_ranga` None w 10/10 notek — ale poprawka weszła 6.09 02:25 UTC i od tej pory nie było notki z banku; NIEROZSTRZYGNIĘTE, sprawdzić po pierwszej | do sprawdzenia |
| B11 | furtka wydarzeń kontra parowanie | jedno zamawia wiele faktów o zdarzeniu, drugie ma je scalać; skutek: 4 notki o jednym incydencie w 24 h | średnia — czytelnik |
| B12 | notki typu MYSL | brak podłogi na zmyślone przeżycie („I only noticed last week") | niska |
| B13 | `prompts/` | trzy kopie tej samej sekcji stylu; cztery martwe/nieaktualne pliki | niska |
| B14 | przebieg 155 | ręczny przebieg zaksięgowany jako produkcja, bez śladu w journald | niska — księgowość |

Rzeczy z wcześniejszych list, które **potwierdziłem jako naprawione**:
obcięcie tekstu notki do 300 znaków (od 2.09 pełne), podwójny adres pod notką
ARTYKUL (ostatnia z 4.09 14:47, potem czysto), spiżarnia (`curiosity`
−87% na wywołanie), rekord do weryfikatora (`factcheck` 5,0 → 2,2 szukania),
`effort=medium` Opusa (−57% na notkę), parowanie raz na zmianę zbioru,
etykietowanie kanału (kompletne w torze produkcyjnym), zapora „ta sama
nazwa" po `d1e08f6` (pierwszy przebieg po naprawie przepuścił materiał;
strata 2 notek z 5.09 wieczorem była sprzed niej).

---

## 10. Przemyślenia

**Jeden dzień, jeden przyrząd, cztery decyzje.** 6 września powstały trzy
dokumenty i jedna funkcja na polu, którego znaczenie było już zapisane
poprawnie 3 września — w pamięci projektu, w komentarzu w `statystyki.py`
i w przemianowanej kolumnie `ZAP24`. Wektorem był codzienny raport
`alarm.py przeglad`, który drukuje tę liczbę pod etykietą „przypisanie
samego Substacka". Dopóki raport, który właściciel czyta co rano, mówi
nieprawdę, każda kolejna sesja odziedziczy ten sam wniosek. Naprawa
przyrządu (R1) jest ważniejsza niż wszystkie pozostałe zalecenia razem.

**Konto rośnie przez kontakt z autorami, nie przez zasięg.** 33 z 40 reakcji
na komentarze to autor po powiadomieniu (ANALIZA 5.09), zapisy przychodzą
z restacków i notek pod cudzymi wątkami, a artykuł — najdroższa i najlepiej
pilnowana rzecz — nie przyprowadził wprost nikogo. Artykuł jest tym, co
czytelnik znajduje po wejściu na profil, więc ma sens; ale kolejność bloków,
przydziały i przyrządy są dziś ustawione tak, jakby było odwrotnie.

**„Prośba w prompcie nie jest bramką" działa też w drugą stronę.** Reguły
stylu w komentarzach są przestrzegane w 105/105 bez żadnej bramki; reguły,
które naprawdę psują wynik (cel starszy niż miesiąc, tłok pod celem,
formuła restacku), są w kodzie, nie w prompcie. Prompty są dziś w lepszym
stanie niż kod, który wybiera, do kogo je stosować.

**Sprzeczne mechanizmy zbudowane osobno.** Furtka wydarzeń i parowanie,
nakaz zakończenia w trzech miejscach i wykrywacz tików, `cel_slow` i „two to
four sentences" — każda para powstała z dobrego pomiaru i każda działa
przeciwko drugiej. Przed dołożeniem kolejnej reguły warto pytać, która
istniejąca ją unieważni.

**Czego nie wiem.** Czy `reasoning_effort: low` nie pogorszy wyboru celów
(próba za 0,15 USD); czy dwa duże restacki były przypadkiem; czy seria
w ogóle działa (nie odpaliła); czy MYSL bota kiedykolwiek zbierze rozmowę
(n = 4). Każde z tych pytań ma tanią próbę na żywo i żadne nie ma dziś
odpowiedzi w danych.

---

*Skrypty: `robocze/aud_*.py`. Nic z tego audytu nie jest zacommitowane ani
wdrożone; kod produkcyjny nietknięty.*
