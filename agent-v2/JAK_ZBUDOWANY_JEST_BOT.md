# Nothing Is Accidental — pełna dokumentacja techniczna agenta

**Wersja dokumentu:** 2026-08-20
**Stan opisywany:** commit na `main`, wdrożony na produkcji
**Cel dokumentu:** z tego pliku ma dać się odtworzyć całego bota od zera.

Dokument opisuje **stan faktyczny**, nie zamierzony. Wszędzie, gdzie kod robi
coś innego, niż mówi jego nazwa albo komentarz, jest to napisane wprost i
oznaczone jako **WADA** albo **DECYZJA OTWARTA**.

---

## 1. Mandat i ograniczenia

Agent prowadzi anglojęzycznego Substacka **„Nothing Is Accidental"**, który
wyjaśnia ukryte systemy, bodźce i decyzje stojące za zwykłymi rzeczami.

Ograniczenia postawione przez właściciela przy starcie v2:

| ograniczenie | stan faktyczny | ocena |
|---|---|---|
| maksimum 10 plików `.py` | **11 plików**, 10 171 wierszy | **przekroczone** — patrz §2.1 |
| 4 tabele w bazie | 4 (`runs`, `calls`, `articles`, `sources`) | dotrzymane |
| jedna warstwa abstrakcji | jedna (`llm.py`) | dotrzymane |
| brak migracji, brak kolejek | brak; schemat z `CREATE TABLE IF NOT EXISTS` | dotrzymane |
| jedno polecenie uruchamiające | `python agent-v2/run.py` | dotrzymane |
| 100% autonomii, zero pytań do człowieka | brak interaktywnych promptów | dotrzymane |

**Zasady właściciela, które mają moc nadrzędną nad kodem:**

1. **Nic nie blokuje artykułu.** Gdy temat przeszedł odsiew, a research jest
   opłacony, artykuł MA powstać. Bramki oddają uwagi do przeczytania, nie
   werdykty. `gates.verdict()` zwraca zawsze `SAVED`.
2. **Konto nie ujawnia, że jest AI** (anonimowa marka redakcyjna), ale **nigdy
   nie kłamie zapytane wprost** i nie stosuje technicznego omijania wykrywania.
3. **Serwisy odmawiające automatom są respektowane.** Żadnych proxy
   rezydencjalnych, żadnego obchodzenia blokad.
4. **Żadnych sekretów w repozytorium.** Repo jest publiczne; `.env` i `data/`
   są w `.gitignore`.

---

## 2. Architektura

### 2.1. Pliki źródłowe

```
agent-v2/
  run.py                1 073   rozdzielnik: ścieżka artykułu i ścieżka dnia
  stages.py             2 972   wszystkie etapy myślowe (57 funkcji)
  browser.py            2 314   cała styczność z Substackiem (45 funkcji)
  config.py             1 545   jedyne źródło stałych (152 stałe)
  llm.py                  533   JEDYNA warstwa dostępu do modeli
  gates.py                514   bramki jakości (16 nazw)
  alarm.py                491   kontrola sesji, zdrowia, alarm do właściciela
  kanal.py                295   pamięć o cudzych publikacjach
  db.py                   203   schemat i zapis
  kopia_subskrybentow.py  125   eksport listy subskrybentów
  style.py                106   korpus stylu dla pisarza
```

**WADA (§1):** plików jest jedenaście, nie dziesięć. Najbliższe usunięciu są
`style.py` (106 wierszy, wołane tylko z `stages.py`) i
`kopia_subskrybentow.py` (125 wierszy, narzędzie odpalane ręcznie, nie część
przebiegu). Scalenie któregokolwiek przywróciłoby zgodność z mandatem.

### 2.2. Kto od kogo zależy

```
run.py ──┬─> stages.py ──┬─> llm.py ──> (DeepSeek | Anthropic | OpenAI)
         │               ├─> gates.py
         │               ├─> style.py
         │               └─> db.py
         ├─> browser.py ──> Playwright ──> Chrome ──> Substack
         ├─> kanal.py
         └─> alarm.py
```

Reguła: **`stages.py` nigdy nie dotyka przeglądarki, `browser.py` nigdy nie
woła modelu.** Wyjątek udokumentowany: `browser.restackuj_w_kanale` przyjmuje
funkcję decyzyjną jako argument, więc decyzja zostaje w `stages`.

### 2.3. Prompty

25 plików w `agent-v2/prompts/`, 2 709 wierszy. Największe: `skaut.md` (359),
`pisarz.md` (229), `odpowiedz.md` (183), `komentarz.md` (170), `notka.md` (160).

Cztery pliki to **materiał referencyjny wklejany do innych promptów**, nie
prompty same w sobie: `ZASADY_NOTEK_I_KOMENTARZY.md`, `SKAD_BRAC.md`,
`ROZWOJ_KONTA.md`, `OSWIADCZENIE_AI.md`.

Prompty są ładowane przez `stages._prompt(nazwa, **pola)`, które robi
`str.format` — dlatego **każdy nawias klamrowy w treści JSON-a musi być
podwojony** (`{{"klucz": ...}}`).

---

## 3. Model danych

### 3.1. Baza (SQLite, `data/agent-v2.db`)

Schemat powstaje przy każdym starcie z `CREATE TABLE IF NOT EXISTS`. Brak
migracji: nowe kolumny dokłada `db._dopisz_brakujace_kolumny` przez
`PRAGMA table_info` + `ALTER TABLE ADD COLUMN`.

```sql
runs      id, started_at, finished_at, status(RUNNING|DONE|FAILED),
          stage, cost_usd, note
calls     id, run_id, at, provider, model, purpose,
          tokens_in, tokens_out, cache_hit, web_searches,
          cost_usd, price_verified, ok, note
articles  id, run_id, created_at, topic, title, body,
          evidence(JSON), status, blocked_by, notes(JSON)
sources   id, run_id, at, url, domain, title,
          source_class(PRIMARY|SUPPORTING|ODPAD), fetched_ok, fail_reason
```

**WADA:** `articles.status` przyjmuje wyłącznie `SAVED` (6 wierszy na 6), a
`blocked_by` jest zawsze `NULL`, bo `gates.verdict` nie blokuje. Kolumny są
pozostałością po projekcie, w którym bramki blokowały.

**Krytyczna pułapka w `db.record_call`.** Funkcja wstawia **tylko te kolumny,
które ktoś naprawdę podał**:

```python
keys = [k for k in (
    "run_id", "provider", "model", "purpose", "tokens_in", "tokens_out",
    "cache_hit", "web_searches", "cost_usd", "price_verified", "ok", "note",
) if k in fields]
```

Powód jest niebanalny i kosztował okładkę artykułu 0025. Wcześniej lista była
stała, a brakujące pola szły jako `fields.get(k)`, czyli **jawny NULL**.
SQL-owy `DEFAULT 0` wtedy nie działa — wchodzi tylko wtedy, gdy kolumny w
`INSERT` nie ma wcale. Po dodaniu kolumny `cache_hit NOT NULL DEFAULT 0` każde
wywołanie, które jej nie podało, kończyło się `IntegrityError`. Skutki:

- grafika **nigdy** nie mogła się zapisać, więc nigdy nie powstawała,
- ścieżka zapisu **nieudanego** wywołania wywracała się na tym samym, więc
  awaria dostawcy przychodziła do logu jako awaria bazy.

Dowód niezależny: w 591 wywołaniach kolumna `ok` miała wartość 1 **w 591
przypadkach**. Nigdy nie zapisaliśmy nieudanego wywołania, choć wiemy, że
padały.

### 3.2. Pliki na dysku (`agent-v2/data/`, w `.gitignore`)

| plik | zawartość | klasyfikowany | przycinany |
|---|---|---|---|
| `agent-v2.db` | baza (patrz wyżej) | — | nie |
| `indeks_kandydatow.json` | kandydaci na notki | **tak, bramka na wejściu** | nie |
| `zuzyte_fakty.json` | fakty już wykorzystane | nie | nie |
| `promocja.json` | kolejka notek promujących | nie | **nie, także wyczerpane** |
| `gdzie_komentowalismy.json` | gdzie i kiedy komentowaliśmy | nie | efektywnie tak (reguła 4 dni po dacie) |
| `dziennik.jsonl` | każde działanie, jeden JSON na wiersz | nie | nie |
| `articles/NNNN-slug.md` | treść artykułu | — | nie |
| `articles/NNNN-slug.uwagi.md` | uwagi bramek | — | nie |
| `articles/NNNN-slug.png` | okładka | — | nie |
| `cache/<etap>.json` | wynik etapu dla `--use-cache` | — | nie |
| `storage-state.json` | **sesja Substacka** — sekret | — | nie |
| `agent.lock` | zamek `flock`/`msvcrt` | — | — |

**DECYZJA OTWARTA:** klasyfikacja istnieje **wyłącznie na wejściu** (bramka
kandydata, klasyfikacja źródeł). Nic nigdy nie wraca do materiału już
zapisanego. Po każdej zmianie kryteriów — a 20 sierpnia zmieniły się dwa razy —
w indeksie zostaje materiał przyjęty według starych reguł.

---

## 4. Warstwa modeli (`llm.py`)

### 4.1. Dostawcy i role

21 ról, 3 dostawcy. Rola → model ustawia `config.MODEL_FOR`:

| rola | model | co robi |
|---|---|---|
| `scout` | deepseek-v4-pro | wymyśla tematy artykułów |
| `feasibility` | deepseek-v4-flash | ocenia wykonalność i głębokość |
| `discovery` | deepseek-v4-pro | szuka źródeł w sieci (najdroższa pozycja) |
| `classify` | deepseek-v4-flash | PRIMARY / SUPPORTING / ODPAD |
| `synthesis` | deepseek-v4-pro | składa kartę dowodową |
| `warto_pisac` | deepseek-v4-pro | bramka ciekawości przed pisarzem |
| `write` | **claude-fable-5** | pisze artykuł |
| `review` | deepseek-v4-pro | rozlicza każde zdanie z kartą |
| `forma` | deepseek-v4-pro | obserwuje formę (beaty, eskalacja) |
| `grafika` | deepseek-v4-flash | wybiera przedmiot na okładkę |
| `obraz` | **gpt-image-1.5** | generuje okładkę |
| `note` | **claude-opus-5** | pisze notkę |
| `curiosity` | deepseek-v4-flash | szuka faktów na notki |
| `comment` / `reply` | deepseek-v4-pro | komentarze i odpowiedzi |
| `factcheck` | deepseek-v4-flash | sprawdza fakty przed wysłaniem |
| `cele` | deepseek-v4-flash | wybiera, gdzie warto się odezwać |
| `restack` | deepseek-v4-pro | decyduje o podaniu dalej |
| `bibliotekarz` | deepseek-v4-pro | grupuje resztki researchu po mechanizmie |

### 4.2. Co robi `llm.call`

```
_preflight(purpose, conn, run_id)      # wyłącznik, limit przebiegu, sufit dzienny
  ↓
budowa żądania wg dostawcy             # DeepSeek / Anthropic / OpenAI
  ↓
wywołanie z ponowieniami
  ↓
db.record_call(...)                    # ZAWSZE, także przy błędzie
  ↓
zwrot tekstu
```

Kluczowe: **koszt liczy się w jednym miejscu**. `_cost()` bierze stawkę z
`config.PRICING`, mnoży przez mnożnik godzinowy DeepSeeka i osobno wycenia
tokeny z cache.

```python
MNOZNIK_SZCZYT = 2.0          # godziny UTC {1,2,3,6,7,8,9}
MNOZNIK_POZA_SZCZYTEM = 1.0
```

**Pułapka historyczna:** `stawka_deepseek` nie zwracała klucza `"cache"`, więc
`_cost` sięgał po `price["in"]` i wyceniał tokeny z cache **45× za drogo**.

### 4.3. Sufity tokenów

`config.MAX_TOKENS` per rola. Dwie wartości wyznaczone doświadczalnie:

```python
"review": 48000        # recenzja rozlicza KAŻDE zdanie; przy 28 764 ucięło
"forma":  24000
THINKING_HEADROOM_TOKENS = 28000   # DeepSeek-pro rozumuje 16-19k niezależnie
                                   # od treści; wcześniejsze 16000 = zero marginesu
```

---

## 5. Ścieżka artykułu

Uruchomienie: `python agent-v2/run.py [--wyslij] [--use-cache] [--stop-after ETAP]`

Etapy: `scout → feasibility → discovery → fetch → classify → synthesis →
warto_pisac → write → review → forma`, po nich bramki, zapis, opcjonalnie
grafika i publikacja.

### 5.1. `scout` — wymyślanie tematów

Wejście: liczba tematów, historia naszych tematów, **pytania czytelników**
zebrane spod naszych notek i artykułów.

Prompt narzuca **dwa rodzaje tematu**:

- **`BROKEN_BELIEF`** — czytelnik trzyma przekonanie, które zapis obala.
  Wymagane pola: `broken_belief` (zdanie zaczynające się „Everyone assumes"),
  `why_they_believe_it`.
- **`SYSTEM_UNDER_TEST`** — system, który zaraz zostanie wystawiony na próbę.
  Wymagane: `the_moment`, `open_outcome`, `governing_record`.

Powód istnienia drugiego rodzaju jest mechaniczny, nie estetyczny: **luka
informacyjna z definicji się nasyca**. Loewenstein pisze wprost, że po zdobyciu
wystarczającej ilości informacji ciekawość spada. Pismo złożone z samych pytań
zamkniętych produkuje czytelników zaspokojonych i odchodzących.

Pola wspólne dla obu rodzajów:

- **`already_written`** — lista tego, co model sądzi, że już o tym napisano.
  Używamy jego pamięci **przeciw niemu**: „wszyscy wierzą X o zwykłym
  przedmiocie, a X jest nieprawdą" to nie wgląd, tylko **gatunek z kanonem**
  (zraszacze, chusteczki „flushable", mydło antybakteryjne, data na lekach).
  Model podaje je pierwsze, bo są najczęściej opisane — a **dostępność jest
  odwrotnością sygnału, którego szukamy**.
- **`scale`** — `ONE_PERSON` / `A_PLACE` / `AN_INDUSTRY` / `A_COUNTRY`.
- **`precedents`** — udokumentowane awarie: `{when, what_happened, what_changed}`.
- **`threads`** — osobne pytania, każde z własnymi dokumentami.
- **`ranking`** (na poziomie odpowiedzi, nie tematu) — wymuszony wybór:
  po trzy indeksy w `most_written_about`, `least_written_about`, `richest`,
  `thinnest`.

**Dlaczego wymuszony wybór.** Listy bezwzględne model **wyrównuje**. Zmierzone:
każdy temat dostał dokładnie trzy znane teksty i dokładnie sześć wątków (w
kolejnym przebiegu: dwa i pięć). Oba sygnały spadły do stałej — ta sama wada co
samooceny wracające zawsze 1.0. **Oceny bezwzględnej da się wyrównać,
wymuszonego porównania nie.**

Kod (`stages.scout`) liczy z tego:

```python
t["nosny"]            = ma_przekonanie or ma_stawke
t["nasycony"]         = ile_juz_napisano >= config.NASYCENIE_OD_ILU   # 2
t["ile_precedensow"]  = len([p for p in precedents if _precedens_ok(p)])
t["duzy_zasieg"]      = scale in config.ZASIEGI_ARTYKULOWE   # AN_INDUSTRY, A_COUNTRY
t["na_artykul"]       = ile_precedensow >= 2 and duzy_zasieg
t["pozycja"]          = +2/-2 za ranking świeżości, +1/-1 za bogactwo
```

`_precedens_ok` wymaga **trzech rzeczy naraz**: zdarzenia (≥5 słów), daty
(`\d{3,4}`) i skutku (≥3 słowa, nie zaczynającego się od zaprzeczenia). Powód:
regulamin ma być **blizną**. Zdarzenie, po którym nic się nie zmieniło, to
anegdota — ciekawa, ale nie ona niesie tysiąc słów.

Kolejność: `nośny → na_artykuł → własny ranking → świeżość → wątki`.

### 5.2. `feasibility` — czy da się to udokumentować

Wejście: lista tematów. Wyjście na temat: `feasible`, `confidence`,
`expected_primary_sources`, `depth` (`RICH`/`SINGLE`/`THIN`), `parallels`.

`depth` steruje długością artykułu:

```python
DLUGOSC_WG_GLEBOKOSCI = {
    "RICH":   {"cel": 1075, "min": 900, "max": 1250},
    "SINGLE": {"cel": 650,  "min": 480, "max": 820},
}
```

`RICH` osiąga się na dwa sposoby: dwie nazwane paralele **albo** trzy i więcej
osobnych wątków. Drugi sposób dołożono 20 sierpnia, bo głębokość była mierzona
**wyłącznie poziomo** i temat idący głęboko w jednym miejscu dostawał `THIN`.

**WADA:** `feasible` było prawdziwe w 6 ocenach na 6. Przyczyna leżała w
kodzie: gdy żaden temat nie przechodził, `pick_topic` **rzucał wyjątek i cały
przebieg umierał** — wbrew zasadzie, że bramki zgłaszają. Naprawione: przy
zerze przechodzących bierzemy najlepszy z odrzuconych i zapisujemy
`mimo_odrzucenia`.

### 5.3. `pick_topic` — wybór jednego tematu

```python
kolejnosc = (nosny, artykulowy, wlasny_ranking, swiezy, watki,
             waga_glebokosci, confidence, expected_primary_sources)
```

**WADA HISTORYCZNA, naprawiona 20 sierpnia:** pierwszym kluczem było
`ma_przekonanie`. Temat oklepany ma **z definicji** najostrzejsze „everyone
assumes" — bo dokładnie dlatego został oklepany. Ranking wybierał więc kanon
mythbustingu z konstrukcji. Dodatkowo `ma_stawke` nie było w rankingu wcale,
więc tematy drugiego rodzaju, stawiane przez skauta na czele, wracały na dół.

### 5.4. `discovery` — szukanie źródeł

Najdroższa pozycja w całym systemie: **29,4% wydatków**, średnio 170 633 tokeny
wejścia na wywołanie, bo cała rozmowa wraca w każdej rundzie narzędziowej.
DeepSeek-pro z włączonym wyszukiwaniem.

### 5.5. `fetch` — pobieranie

`trafilatura` do HTML, `pypdf` do PDF-ów (dodane, gdy okazało się, że część
„niedostępnych" źródeł to po prostu PDF-y). Serwisy odmawiające automatom są
respektowane — 403 i frazy odmowy trafiają do `sources.fail_reason`, a host
ląduje na liście martwych, **z wyjątkiem** awarii spowodowanych PDF-em.

Próg: `MIN_ZRODEL_DO_PISANIA = 4`. Poniżej idzie druga runda.

### 5.6. `classify` → `synthesis` — karta dowodowa

Klasyfikacja: `PRIMARY` / `SUPPORTING` / `ODPAD` plus `relevance` (0–1).
`relevance` służy **wyłącznie do sortowania, bez progu** — dlatego ściśnięta
skala (zmierzone 0,75–0,95) nadal daje poprawną kolejność i **nie jest wadą**.

Synteza produkuje kartę:

```json
{"working_thesis", "main_mechanism",
 "confirmed_claims": [{"claim", "evidence", "url"}],
 "citable_numbers": [{"value", "means", "url"}],
 "parallel_mechanisms": [{"domain", "how_it_matches"}],
 "uncertain_claims", "contradictions", "not_established"}
```

Karta jest **jedynym** materiałem pisarza. Czego nie ma w karcie, tego nie
wolno stwierdzić jako faktu.

### 5.7. `warto_pisac` — bramka ciekawości

Model obserwuje pięć rzeczy i **cytuje dowód z karty**; werdykt składa **kod**.

| droga do `PISZ` | warunek |
|---|---|
| A — złamane przekonanie | przekonanie + 2 z 3 filarów (decydent, odczuwalna liczba, druga dziedzina) |
| B — nierozstrzygnięty wynik | otwarty wynik + **spisana reguła** + nazwany decydent |

Werdykty: `PISZ`, `DOLOZ` (szukaj pary w banku fragmentów), `ODLOZ`.

Warunek oddzielający drogę B od wróżenia jest jeden i twardy: karta musi nieść
spisaną regułę. Kod odrzuca też odpowiedź **zaprzeczającą sobie w pierwszych
słowach** („nic tego nie rozstrzyga, po prostu nikt tego nie zapisał") — to
opis luki w naszej wiedzy, nie stawki. Siatka `_ZAPRZECZENIE` kotwiczy na
**początku** zdania, więc poprawna reguła ze słowem „nothing" w środku
przechodzi.

### 5.8. `write` — pisanie

Model: **Claude Fable 5**. Wejście: karta, długość z głębokości, korpus stylu,
**losowany ruch końcowy** (jeden z sześciu) i **losowana liczba paraleli**.

Losowanie jest zabezpieczeniem, nie ozdobą. Po naprawie wad treści dwa kolejne
artykuły wyszły z **identycznym szkieletem**, bo prompt go zamawiał. Wniosek:
**powtarzalna forma zdradza maszynę tak samo jak powtarzana treść.**

Sześć zakazów w `pisarz.md`, każdy wyprowadzony z konkretnej wady artykułu 0025:

1. nie wydawaj tego samego twierdzenia dwa razy,
2. najmocniejszy fakt nie w tonie przypisu,
3. wnioskowanie znacz **strukturą zdania**, nie formułką,
4. nie obwieszczaj własnej powściągliwości,
5. każda liczba niesie źródło w swoim zdaniu,
6. niewiadome pojedynczo, tam gdzie powstają.

**Świadomie NIE ma zakazów nakazujących pozycję** (lede z liczbą, przyłapanie
czytelnika na 25–40%, trzy przyspieszające akapity końcowe). Reguła zakazująca
usuwa wadę i zostawia przestrzeń otwartą; reguła nakazująca pozycję wypełnia ją
jedną odpowiedzią i po dziesięciu tekstach **sama staje się podpisem maszyny**.

### 5.9. `review` i `forma` — dwa niezależne spojrzenia

`review` rozlicza **każde zdanie** z kartą: `FACT` / `INFERENCE` / `PROSE`,
plus `supported`. Wnioskowanie i opinia **nigdy** nie mogą oblać — tylko fakt
stwierdzony bez pokrycia.

**Pułapka naprawiona 20 sierpnia:** czytaliśmy wyłącznie zbiorczą listę
`unsupported_facts`, czyli ufaliśmy, że model poprawnie przepisze własny wynik
w drugie miejsce. Teraz kod składa z **obu źródeł** — listy i pola `supported`.

`forma` to **osobne wywołanie, celowo**. Recenzent ma chronić wnioskowanie
przed zgłoszeniem, a ta bramka liczy m.in. zastrzeżenia; złączone tępiłyby się
nawzajem.

**Pułapka promptu, złapana dopiero na żywym modelu:** pierwsza wersja kazała
przejść artykuł zdanie po zdaniu. Model oddał **47 „beatów" na 1097 słów** — po
jednym na zdanie. Testy tego nie wykryły, bo obserwację podawałem w nich
ręcznie: sprawdzały **kod, nie prompt**. Poprawka to zmiana pytania: „czytelnik
opowiada o tekście znajomemu przez minutę — w co teraz wierzy". Lista powstaje
przed szukaniem cytatów i przechodzi test scalania dwa razy.

---

## 6. Bramki jakości (`gates.py`)

**Szesnaście, żadna nie blokuje.** Wszystkie zgłaszają uwagi, które lądują w
`articles.notes` i w pliku `.uwagi.md` obok artykułu.

### 6.1. Dwanaście deterministycznych (zero kosztu)

| bramka | co łapie |
|---|---|
| `ZMYSLONE_PRZEZYCIE` | czasowniki doświadczenia („I stood", „last week I") |
| `NIEISTNIEJACE_BADANIE` | „according to a recent study" bez nazwania |
| `LICZBA_SPOZA_KORPUSU` | liczba, której nie ma w karcie |
| `FRAZA_Z_INSTRUKCJI` | pisarz zacytował własny prompt (6-wyrazowe ciągi) |
| `ZAPOWIEDZ_GRANIC` | akapit o granicach zapowiada sam siebie |
| `WASKA_PODSTAWA` | artykuł stoi na jednym serwisie |
| `BUDZET_ZASTRZEZEN` | więcej niż jedno „moim zdaniem" |
| `OBWIESZCZONA_POWSCIAGLIWOSC` | „nie zmyślę tego" |
| `ZAKAZANE_OTWARCIE` | „Turn over…", „Next time you…" |
| `STATYSTYKA_BEZ_ZRODLA` | liczba + niby-źródło w jednym zdaniu |
| `NIEWIADOME_NA_KONCU` | zbiorcza lista granic w ostatniej trzeciej |
| `ODCISK_FORMY` | ten sam szkielet co któryś z czterech poprzednich |

`ODCISK_FORMY` pilnuje **samej naprawy**: skoro dokładamy kilkanaście reguł
kształtu, ktoś musi patrzeć, czy kształt nie zrobił się jeden. Porównuje sześć
zgrubnych cech (otwarcie, liczba w otwarciu, pozycja pierwszego „your", akapit
granic, liczba akapitów, długość); pięć zgodnych na sześć daje uwagę.

### 6.2. Cztery „model obserwuje, kod rozstrzyga"

| bramka | co łapie |
|---|---|
| `GESTOSC_BEATOW` | mniej niż jedno nowe przekonanie na 150 słów |
| `BRAK_ESKALACJI` | najmocniejszy fakt w tonie przypisu |
| `CZYTELNIK_NIEPRZYLAPANY` | nigdzie zwrotu do TEGO czytelnika z konkretem |
| `OTWARCIE_ZNANE` | pierwszy akapit stoi na tym, co czytelnik już wie |

Model oddaje **wyłącznie cytaty i tak/nie**. Liczenie, dzielenie i szukanie
pozycji robi kod, bo arytmetyki modelu nie da się sprawdzić, a cytat da się
znaleźć w tekście.

Pozycje **liczymy i pokazujemy** (`pozycja_w_tekscie`), ale **nie są wadą** —
to świadoma różnica wobec playbooka właściciela.

---

## 7. Ścieżka dnia

`python agent-v2/run.py --dzien [--wyslij]`

### 7.1. Budżet dnia

`stages.budzet_dnia` losuje z widełek — **stała liczba dziennie wygląda jak
robot**, bo człowiek nie ma normy. Przez pierwszy miesiąc (`ROZBIEG_DNI`)
górna połowa widełek jest ścinana.

Widełki po przeglądzie na własnych danych (20 sierpnia):

| | zmierzone | było | jest |
|---|---|---|---|
| notki | 3,0/dzień | 5 | **5** |
| komentarze | 7,0 | 15–20 | **8–12** |
| lajki | 9,6 | 12–20 | **10–16** |
| restacki | 0,4 | 2–4 | **1–2** |
| obserwacje | **0,0** | 30–44/mies | **20–30/mies** |
| subskrypcje | ~0,8 | 6–12/mies | **6–12/mies** |

### 7.2. Kolejność bloków — decyduje o tym, co się w ogóle wydarzy

```
odpowiedzi → notki → obserwowanie → subskrypcje → komentarze → dyskusje
          → polubienia → restacki
```

**WADA NAPRAWIONA:** zegar przebiegu sprawdzają bloki od odpowiedzi po
subskrypcje; lajki i restacki nie patrzą na niego wcale. Gdy czas się kończył,
wypadały dokładnie te bloki, które były wobec zegara **uczciwe** — a
obserwowanie stało **za** komentarzami, czyli za jedynym blokiem potrafiącym
zjeść cały budżet czasu. Skutek zmierzony: **zero obserwacji przez pięć dni**
przy budżecie 30–44 miesięcznie. Blok nie chodził w ogóle.

### 7.3. Tempo

```python
ODSTEPY = {"notka": (2700, 5400),      # 45-90 min
           "komentarz": (180, 480),
           "odpowiedz": (120, 420),
           "lajk": (30, 90),
           "restack": (600, 1800)}     # 10-30 min
OKNO_PUBLIKACJI_ET = (6, 22)           # czas CZYTELNIKÓW, nie właściciela
```

Okno siedzi w kodzie, nie w harmonogramie — zegar można przestawić, a ręczne
uruchomienie i tak by go ominęło.

**WADA NAPRAWIONA:** odstęp restacków stał na końcu ciała pętli, a warunek
wyjścia sprawdza się na górze następnego obrotu — więc agent po wykonaniu normy
spał 10–30 minut z otwartą przeglądarką. Odstęp stoi teraz **przed** kolejnym
restackiem. Zweryfikowane na produkcji: 79 ms między „podane dalej 1/1"
a „dzień zamknięty".

### 7.4. Promocja artykułu

Trzy notki na artykuł, po jednej dziennie, **najświeższy artykuł pierwszy**
(`reversed(kolejka)`). Jedna notka promująca **na dobę łącznie**, nie na
artykuł — wcześniej warunek „promowany dziś" tylko pomijał wiersz, więc trzy
przebiegi dziennie mogły dać trzy notki promujące różnych tekstów.

---

## 8. Styk z Substackiem (`browser.py`)

Playwright + Chrome z zapisaną sesją (`storage-state.json`). **Nie ma API do
publikacji** — wszystko przez interfejs.

### 8.1. Wykorzystywane endpointy (do czytania, nie pisania)

```
/api/v1/posts?limit=N                    nasze artykuły
/api/v1/posts/{slug}                     cudzy post + write_comment_permissions
/api/v1/reader/feed?tab=for-you          kanał czytelnika
/api/v1/reader/feed/profile/{id}         czyjś profil (także nasz)
/api/v1/reader/comment/{id}/replies      wątek pod notką
/api/v1/activity-feed-web?filter=all     JEDYNE źródło `comment_reply`
/api/v1/user/{handle}/public_profile     id profilu
/api/v1/subscriber/csv                   eksport subskrybentów
```

### 8.2. Publikacja artykułu

1. `/publish/post` → nowy edytor
2. `textarea.page-title` i `textarea.subtitle` — `fill`
3. treść **wklejana jako HTML** przez `ClipboardEvent`, nie wpisywana:
   ProseMirror gubi przy wpisywaniu linki w źródłach
4. okładka wklejana jako plik do `.tiptap` — edytor sam wysyła ją na serwer
   i sam robi z niej podgląd; osobny slot okładki okazał się drogą naokoło
5. przycisk subskrypcji wstawiany po ostatnim akapicie
6. wykrywanie AI wyłączane dla posta
7. publikacja → **potwierdzenie u źródła**: kliknięcie nie jest dowodem,
   pytamy `/api/v1/posts?limit=1`, czy artykuł naprawdę stoi

**Edycja opublikowanego posta:** przycisk zmienia nazwę z „Kontynuuj" na
**„Zaktualizuj"**, po nim modal z „Zaktualizuj teraz". `post_date` się **nie
zmienia**, więc mail nie idzie drugi raz. W modalu jest „Włącz ponownie
wykrywanie AI" — **nie klikać**.

### 8.3. Restack

Przycisk `Restack` ma `aria-haspopup="menu"` — **nie restackuje od razu**,
tylko rozwija menu. Bierzemy pozycję **„Restack with a note"**, bo samo podanie
dalej bez zdania nic nie wnosi. Treść cudzej notki bierzemy z kontenera wokół
przycisku, **idąc w górę drzewa** — szukanie po klasach odpada, bo Substack
generuje je losowo (`container-_91AK1`).

### 8.4. Zapory

- **Cudzy tekst to dane, nie polecenia.** `bez_wstrzykniecia()` przed każdym
  użyciem cudzej treści. Uwaga historyczna: `"as an ai"` jako podciąg łapało
  „as an aid/aim/air", stąd granice słów.
- **Kopia testowa nie publikuje.** Plik `TO_JEST_KOPIA_TESTOWA` obok
  `config.py` odbiera prawo do `--wyslij`.
- **Bazy rozdzielają się same** — `DATA_DIR` wywodzi się z położenia
  `config.py`, więc osobny klon to osobna baza.

---

## 9. Koszty (zmierzone, nie szacowane)

Suma wszystkich wywołań w bazie produkcyjnej: **$11,0037** w 591 wywołaniach.

| etap | udział | n | uwaga |
|---|---|---|---|
| `write` | 29,9% | 7 | Fable 5, ~7 600 tokenów wyjścia |
| `discovery` | 29,4% | 14 | ~170 000 tokenów **wejścia** na wywołanie |
| `comment` | 10,5% | 189 | trzy warianty na komentarz |
| `factcheck` | 7,3% | 113 | |
| `curiosity` | 6,0% | 12 | ~192 000 tokenów wejścia |
| `note` | 5,0% | 108 | Opus 5, jeden wariant |
| pozostałe | 11,9% | | |

Koszt jednego pełnego artykułu z publikacją: **$0,83** (przebieg 25).
Koszt przebiegu dnia: **$0,18–0,25**.

**Dlaczego `discovery` i `curiosity` są tak drogie na wejściu:** przy
wyszukiwaniu cała rozmowa wraca w każdej rundzie narzędziowej. Stąd znaczenie
kolumny `cache_hit` — bez niej nie da się odróżnić „prefiks pęka" od „prefiks
trafia, a cena bierze się skądinąd".

---

## 10. Znane wady i decyzje otwarte

| rzecz | stan |
|---|---|
| jedenaście plików `.py` zamiast dziesięciu | **wada**, §2.1 |
| `articles.status` zawsze `SAVED`, `blocked_by` zawsze `NULL` | pozostałość po projekcie z blokowaniem |
| `feasible` zawsze `True` | odsiew nie odrzuca; naprawiony crash, ale sygnał nadal bez wartości |
| `threads` i `already_written` wyrównane do stałej | obchodzone wymuszonym wyborem, nie naprawione u źródła |
| `BEST_NOTE_HOURS` i pochodne nieużywane | **nasze własne źródła się nie zgadzają** — config mówi 6–8 ET, research z 18 sierpnia 19:00–22:00 UTC |
| brak przeglądu materiału już zapisanego | klasyfikacja tylko na wejściu |
| kolejność bloku komentarzy | trzy warianty + factcheck płacone **zanim** sprawdzimy, czy pod postem jest pole komentarza |
| czytelnicy wracają do OSOBY | ADR-018 czyni konto anonimowym; substytut = rozpoznawalna metoda |
| dwie zerowe bazy i trzy kopie `.przed-*` w `data/` | śmieci |

---

## 11. Jak odtworzyć bota od zera

1. **Konto i sesja.** Zalogować się ręcznie w Chrome na serwerze (jest VNC +
   noVNC pod `nia-vnc`/`nia-novnc`), zapisać `storage-state.json`.
2. **Środowisko.** Python 3.12, `pip install -r requirements.txt`
   (playwright, trafilatura, pypdf, anthropic, requests), `playwright install chromium`.
3. **Sekrety.** `.env` z `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY`, `SUBSTACK_HANDLE`. Nigdy do repo.
4. **Baza.** Powstaje sama przy pierwszym `db.connect()`.
5. **Sprawdzenie bez wydawania pieniędzy:**
   `for t in agent-v2/tests/test_*.py; do python "$t"; done` — 35 zestawów,
   950 asercji, wszystkie darmowe i żaden nie dotyka produkcji.
6. **Pierwszy przebieg na sucho:** `python agent-v2/run.py --stop-after scout`.
7. **Pełny przebieg bez publikacji:** `python agent-v2/run.py`.
8. **Publikacja:** dopiero `--wyslij`.
9. **Harmonogram:** `nia-agent.timer` (systemd), `OnCalendar` 11:20 / 19:20 /
   23:40 UTC, `RandomizedDelaySec=1500`, `Persistent=true`.

---

## 12. Zasada, która rządzi całą resztą

**Model obserwuje, kod rozstrzyga.**

Oceny liczbowe modelu degenerują się do jednej wartości — sprawdzone trzy razy
na trzy różne sposoby: samooceny wracały zawsze 1.0, liczba wątków zawsze
sześć, liczba znanych tekstów zawsze trzy. Dlatego pytamy o rzeczy
**sprawdzalne**: cytat, który da się znaleźć w tekście, listę, którą da się
policzyć, wymuszone porównanie, którego nie da się wyrównać. Arytmetykę,
pozycje i progi liczy kod.

Drugą zasadą jest **kontrdowód w każdym teście**: test musi umieć wykryć także
zachowanie **sprzed** poprawki. Test, który tego nie umie, nie jest dowodem, że
poprawka była potrzebna — jest lustrem.
