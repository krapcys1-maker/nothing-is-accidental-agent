# Audyt prototypu `agent-v3` i decyzja, co przejąć do `agent-v2`

**Data:** 2026-08-23 · **Zamówienie:** „v3 jest jedynie prototypem i tak go traktuj — sprawdź, czy coś jest tam wartościowego, co moglibyśmy przejąć do v2".

---

## 0. Metoda

Osiem agentów przeszło osiem obszarów v3 (potok tematyczny, bezpieczeństwo, fetch i pochodzenie,
kontrakty modeli, baza i księgowość, warstwa redakcyjna, infrastruktura testowa, ryzyka),
dziewiąty złożył werdykt inżynierski, weryfikując 21 twierdzeń w źródle. **Ja zweryfikowałem
osobiście dziewięć twierdzeń nośnych** — te, na których stoją decyzje „brać / nie brać".
Wszystko, co niżej podaję jako ustalenie, otworzyłem i sprawdziłem.

Jedno sprostowanie do werdyktu agenta, żeby nie powielać błędu: agent napisał, że w momencie
wywołania bramki `LICZBA_SPOZA_KORPUSU` karta *„nie zawiera ani jednego znaku tekstu
źródłowego"*. To jest przesada — `confirmed_claims[].evidence` to dosłowne fragmenty ze źródeł
i one w karcie **są**. Prawdziwa jest wersja słabsza i nadal poważna: w karcie brakuje
`unused_evidence` (dopisywane 34 wiersze później), a korpus jest zanieczyszczony polami
pisanymi przez model. Reszta jego ustaleń wytrzymała czytanie źródła.

---

## 1. Czym v3 właściwie jest

Nie jest wariantem v2. Jest **laboratorium**:

| | v2 | v3 |
|---|---|---|
| kod produkcyjny | 17 246 w. | ~19 400 w. |
| testy | 3 900 w. | ~11 500 w. + 1 500 w. płatnych |
| dokumentacja badawcza | — | ~13 200 w. w `wnioski badania/` |
| moduły, których nie ma po drugiej stronie | — | **13** |
| eksperymenty live z zapisem | — | 10 katalogów, 3,7 MB |
| rejestr | — | A-001–A-130, N-001–N-028, E-007–E-024 |

Trzy fakty, które zmieniają sposób czytania tego wszystkiego:

**Większość prototypu nie istnieje w gicie.** Sprawdziłem pięć nowych modułów:
`provenance.py`, `capabilities.py`, `model_contracts.py`, `safe_fetch.py` — **nie ma ich
w `HEAD`**; `editorial.py` jest. Commit nazywa się „snapshot autonomous prototype", ale
snapshot objął ułamek. Cokolwiek stąd bierzemy, bierzemy z drzewa roboczego jednego dysku.

**v3 nigdy nie napisał artykułu z prawdziwego tematu.** Katalogi
`.live-experiments/*/data/articles` są puste. Najdroższy udany eksperyment (E-014, 1,34 USD)
pisał o „Harbor Lighting Ordinance" w „Fixture City" ze źródłami na `fixture.invalid`.
To dowodzi, że **okablowanie trzyma** — i to jest realna wartość — ale nie dowodzi niczego
o tekście.

**v3 jest dziś zamurowany własnymi mechanizmami.** DeepSeek zablokowany do rekoncyliacji
kosztu, której żadna ścieżka runtime nie wykonuje (`reconcile_unknown_call` nie ma wywołania
poza testami). Bramka predispatch odmawia własnej dyskoverii. Polityka jakości wymaga **zera
uwag** do publikacji. Prototyp, który miał być w pełni autonomiczny, stoi na trzech
fail-closed bez klucza.

**Ocena.** Wartość v3 jest **realna, ale skoncentrowana**. Cztery pomysły warte są całego
tego wysiłku. Reszta z trzydziestu tysięcy wierszy to albo aparatura badawcza (dobra tam,
gdzie jest), albo warstwa bezpieczeństwa zaprojektowana pod scenariusz, którego v2 nie ma
(osobne konto testowe).

---

## 2. Najważniejsze: v3 rozwiązał problem miałkich tematów — i wiemy, dlaczego v2 go miał

To jest jedyne odkrycie w v3, które samo uzasadnia jego istnienie.

### 2.1. Kształt „przedmiot z oznaczeniem" nie był zachowaniem modelu. Był specyfikacją.

Wczoraj napisałem, że v2 produkuje 18 tematów o jednym kształcie i że nic tego nie pilnuje.
To było **za łagodne**. v3 pokazuje, że v2 tego kształtu **żądał**, w trzech miejscach naraz:

- `agent-v2/prompts/skaut.md:31-39` — zjawisko musi być jednym z trzech: *„an object …
  a procedure the reader has been put through … a moment everybody watched happen"*.
  Nic poza tym nie jest dopuszczone.
- `agent-v2/prompts/skaut.md:186-187` — *„Condition three is the whole guard, **and it is
  not negotiable**"*: musi istnieć spisana procedura.
- `agent-v2/stages.py:2172-2174` — kod domyka to, czego prompt zażądał:
  `na_artykul = ile_precedensow >= 2 and duzy_zasieg`. A precedens-bliznę, czyli „przepis
  powstał, bo ktoś zginął", mają z natury tematy regulacyjne.

Ironia jest w tym samym pliku: `skaut.md:10-15` **sam nazywa gatunek do unikania** —
zraszacze, flushable wipes, karta hotelowa — a dwadzieścia wierszy dalej zamawia dokładnie
ten sam kształt. To jest zamknięte koło i v3 je przecina.

### 2.2. Co zrobił v3

`agent-v3/prompts/skaut.md:1-5`, pierwsze zdanie:

> *a topic does not have to be a system, a procedure or an ordinary object. It may begin with
> economics, work, science, history, culture, identity, technology, power, a counterfactual,
> a conflict or a human experience.*

Zmieniła się **jednostka pracy**. v2 zamawia jeden temat = jeden artykuł. v3 zamawia
**uniwersum artykułowe**: *„a compelling open territory that can produce many genuinely
different excellent articles without padding"*. Kalibracja przez dwa przykłady: bańka AI jako
właściwy rozmiar, boil-water notice jako kontrprzykład.

Kontrakt zamiast `(kind, broken_belief, precedents, scale, threads)`:

```
central_question · mode (WOLNY string, nie enum) · why_fascinating · reader_entry_point
obvious_coverage · underexplored_connections
dimensions[]     {name, question_opened, why_independent}
tensions[]       {force_a, force_b, why_unresolved}
open_branches[]  {possibility, logic, what_would_change_our_mind}
article_routes[] {question, distinct_engine, evidence_needed}
note_test · fatal_weakness · discarded_seeds[]
```

Trzy rzeczy w tym kontrakcie są mądrzejsze, niż wyglądają:

1. **`discarded_seeds`** — model musi pokazać, co odrzucił. *„so the filter is observable"*.
   To jest „model obserwuje, kod rozstrzyga" zastosowane do samego wymyślania.
2. **`mode` nie jest enumem** — *„These are idea tools, not an exhaustive enum. Do not force
   the topic into a category."* v2 miał binarne `BROKEN_BELIEF|SYSTEM_UNDER_TEST` i to
   właśnie ta binarność wtłaczała wszystko w przedmioty.
3. **`article_routes` z `distinct_engine`** — uniwersum jest rezerwuarem, a research dostaje
   **jedno wąskie pytanie**, nie parasol. Bez tego szerszy temat byłby pogorszeniem.

Prompt jest przy tym **krótszy**: 241 wierszy wobec 436.

I kod to weryfikuje (`agent-v3/stages.py:2645-2712`): liczy osie, napięcia, gałęzie, drogi,
unikatowe mechanizmy i unikatowe rodzaje dowodu, sprawdza `note_test`, a na poziomie portfela
odrzuca listę, w której wszystkie tematy mają jeden `mode` (*„portfolio używa tylko jednego
sposobu wymyślania"*).

### 2.3. Dowód — mocny, ale n=1, i z jednym zastrzeżeniem, które sam sprawdziłem

Ten sam model, ten sam routing, dwa kontrakty:

| | stary kontrakt (E-016) | nowy kontrakt (E-018) |
|---|---|---|
| koszt | 0,032564 USD | 0,049298 USD |
| wynik | boil-water notice, fraud score przy zwrocie, ocena sanitarna, przejazd na czerwonym, zakres wycofania partii, jeden respirator | Suspicion as Default · The Uninsurable World · The Afterlife of Abandoned Infrastructure · The Standard Human Body · The Last Human in the Loop · The Quality of Recycled Materials |
| ocena kodu | **6/6 nasyconych** | 6 pól redakcyjnych |
| odrzucone jawnie | — | boil-water notice, karta hotelowa przy telefonie, identyczne tablice rejestracyjne |

Nowy skaut **sam odrzucił kanon, który v2 produkuje od osiemnastu tematów**. To jest
najmocniejszy pojedynczy dowód w całym prototypie.

**Zastrzeżenie, które zweryfikowałem osobiście.** W `.live-experiments/E-018-scout-universe-live/model-captures.json`
pole `system` brzmi dosłownie:

> *„You are a topic scout for the English-language Substack 'Nothing Is Accidental', **which
> explains the hidden systems, incentives and decisions behind ordinary things.**"*

To jest **stary system prompt v2**. Czyli tańsza połowa naprawy — sześć wierszy
`SCOUT_SYSTEM` — nigdy nie została wysłana do modelu. Interpretacja jest dwustronna
i uczciwie trzeba podać obie: **wzmacnia** wniosek o promptcie użytkownika (model wyszedł poza
kanon *mimo* systemowego zdania każącego mu opisywać „ordinary things"), ale **osłabia** tezę
o pełnej różnorodności, bo wszystkie sześć wyników nadal da się przeczytać jako tematy
systemowe.

**Drugie zastrzeżenie:** wyrównywanie formatowe nie zniknęło, tylko zmieniło nazwy. Na live
wszystkie sześć tematów miało identyczną anatomię 5/3/3/4/4. Kod v3 nie mierzy więc bogactwa —
mierzy podłogę. A detektor martwych sygnałów, który v3 **ma w pliku**, przestał być wołany
w skaucie.

**Trzecie:** temat z E-018 przeszedł dalej i został ręcznie odrzucony w dyskoverii **trzy
razy z rzędu** (E-020, E-021, E-022), a E-023 zgubiło 0,30 USD bez wyniku. Szerszy temat
nie znaczy automatycznie lepszy research — i dlatego wybór drogi jest częścią portu, nie
dodatkiem.

---

## 3. BRAĆ — ranking

Wszystko poniżej mieści się w istniejących plikach v2. **Zero nowych plików, zero nowych
tabel, zero migracji** — z jednym wyjątkiem, oznaczonym.

| # | co | naprawia w v2 | koszt | mandat |
|---|---|---|---|---|
| 1 | dedupe indeksów rankingu skauta + waga wg pozycji | jedyny niewyrównywalny sygnał skauta jest dziś artefaktem | ~25 w. | OK |
| 2 | **kontrakt tematu: `skaut.md` v3 + `SCOUT_SYSTEM` v3 + warstwa zgodności, BEZ `raise`** | **główny ból** | +14 w. netto + prompt | OK |
| 3 | feasibility per droga + `selected_route_index` + `research_context` | bez tego #2 jest pogorszeniem | ~115 w., 3 pliki | OK |
| 4 | `style.canonical_bytes` — hash po normalizacji CRLF | **v2 jest dziś zepsute lokalnie** | **1 wiersz** | OK |
| 5 | `LICZBA_SPOZA_KORPUSU`: kolejność + biała lista (własna implementacja) | bramka nie widzi połowy materiału | ~25 w., 3 pliki | OK |
| 6 | dosłowność fragmentów + liczby wyprowadzane KODEM w `classify` | model podaje „liczby źródłowe" z pamięci | ~12 w. | OK |
| 7 | potwierdzenie lajka i restacka, prawdziwe `udane` | zatruty licznik dzienny | ~55 w. | OK |
| 8 | kill switch jako PLIK, sprawdzany w `naprawde_wyslac` | dziś `KILL_SWITCH=true` dalej lajkuje i restackuje | ~18 w. | OK |
| 9 | `_preflight` dla wszystkich modeli | cichy 401 na `FABLE`/`DEEPSEEK_PRO` | ~5 w. | OK |
| 10 | księgowanie znanego `usage` przy `Truncated`/refusal | do 1,88 USD zapisane jako 0,00 | ~8 w. | OK |
| 11 | transport SSE dla DeepSeeka | `incomplete chunked read` — w v3 kosztowało 4,80 USD ekspozycji | ~110 w. | OK |
| 12 | silnik replayu → `agent-v2/tests/replay.py` | jedyny tani sposób zweryfikowania #2 | ~180 w. + fixture'y | plik testowy |
| 13 | `redaktor.md` + wąska pętla rewizji (tylko bramki faktograficzne, 1 iteracja) | 9/15 artykułów wyszło z `FAKT_BEZ_POKRYCIA` | ~70 w. + prompt | OK |
| 14 | degradacja `RICH` bez `parallels` | martwa obietnica z wczorajszego raportu | ~16 w. | OK |
| 15 | `ODLOZ` → tabela `deferred_topics` | licznik „ile razy lejek nie dał tematu" | +1 tabela | **łamie 4→5** |

### Pięć rzeczy najpilniejszych, z planem

#### #4 — korpus stylu (jeden wiersz, a v2 jest dziś zepsute)

Zmierzone przeze mnie na pliku produkcyjnym:

```
agent-v2/prompts/styl/article_style_samples_v1.txt
  sekwencji CRLF:        226
  sha256(surowe bajty):  0b05cefa6701e644…
  sha256(po CRLF -> LF): d4e4e6bf928421d6…
  config.STYLE_CORPUS_SHA256 = d4e4e6bf928421d6…   <-- dokładnie ta druga
```

`style.load_examples()` hashuje **surowe bajty** (`style.py:57`), więc rzuca `StyleError`
przy każdym uruchomieniu na tym dysku. To nie jest teoria: dokumentacja v2 zapisuje przebieg
13 jako `FAILED` na etapie `write` z **$0,3855 zapłacone**, powód
`StyleError: korpus stylu nie zgadza się z przypiętym hashem`. Ta wada zabiła opłacony
research raz i jest nadal otwarta.

Naprawa jest w v3 (`agent-v3/style.py:44-52`, `canonical_bytes`) i sprowadza się do
znormalizowania końców linii przed policzeniem skrótu. **Jeden wiersz.**
Test z kontrdowodem: ten sam korpus zapisany raz z CRLF i raz z LF musi dać ten sam skrót,
a korpus z podmienionym słowem — inny.

#### #1 — ranking skauta

`agent-v2/stages.py:2189-2201`: `indeksy()` filtruje wyłącznie zakres, a pętla dodaje punkty
**za każde wystąpienie**. Ranking `[0,0,0]` daje tematowi 0 aż `+6`. A komentarz w tym samym
pliku (`stages.py:2176-2184`) nazywa ten ranking **jedynym sygnałem, którego model nie umie
wyrównać** — i właśnie ten sygnał jest dziś artefaktem tego, czy model powtórzył indeks.

Naprawa: deduplikacja plus waga malejąca z pozycją na liście. Kontrdowód: ranking `[2,1,0]`
musi dać `pozycja[2] > pozycja[1] > pozycja[0]`; przed naprawą wszystkie trzy równe.

#### #2 — kontrakt tematu

**Pliki:** podmiana `agent-v2/prompts/skaut.md`; `stages.py:22-25` (`SCOUT_SYSTEM`)
i `2093-2175` (ciało pętli); pięć nowych stałych w `config.py`, trzy do usunięcia
(`PRECEDENSOW_NA_ARTYKUL`, `ZASIEGI_ARTYKULOWE`, `NASYCENIE_OD_ILU`).
**Wielkość:** netto **+14 wierszy** kodu. Prompt krótszy o 195 wierszy.
**Koszt:** wejście −3,3 tys. tokenów, wyjście +8,4 tys. → **+0,017 USD na artykuł (~+2%)**.
`MAX_TOKENS["scout"] = 31 600` wystarcza.

Trzy rzeczy obowiązkowe, inaczej port zaszkodzi:

1. **Podmienić `SCOUT_SYSTEM`.** To nie jest opcja. Sześć wierszy w `stages.py:22-25` nadal
   mówi *„explains the hidden systems, incentives and decisions behind ordinary things"* —
   czyli zamawia dokładnie ten gatunek, którego się pozbywamy. I to jest jedyna część,
   której live nigdy nie testował (§2.3).
2. **Zamienić każdy `raise ValueError` na degradację.** v3 rzuca dla całego portfela, gdy
   jeden temat z sześciu nie spełnia progów (`agent-v3/stages.py:2708-2712`), a
   `llm.py` ma `max_retries=0` — jeden słaby temat oznacza zapłacony call i brak artykułu.
   To jest wprost sprzeczne z zasadą v2 „nic nie blokuje artykułu". Temat poniżej progu ma
   dostać `na_artykul=False` i wylądować na końcu kolejki, tak jak v2 już robi.
   *(Osobno: pętla ponowień skauta z wczorajszego raportu zostaje — ale jako „zamów drugą
   listę za 2 centy", nie jako „zabij przebieg".)*
3. **Warstwa zgodności**, bo `run.py:803` czyta `topic["question"]`:
   `question ← central_question`, `kind ← mode`, `already_written ← obvious_coverage`,
   `threads ← [pytania dróg]`. Bez tego `KeyError`.

**Usunąć przy porcie:** blok `### Editorial memory` i `{editorial_memory_json}`
(`agent-v3/prompts/skaut.md:162`) — ciągnie za sobą `editorial.py` i sześć tabel, a na
prawdziwej bazie v3 zwraca `published_content_n: 0` i puste listy.

**Zostawić WOŁANY detektor martwych sygnałów** z nową listą pól
(`ile_osi, ile_napiec, ile_galezi, ile_watkow, ile_mechanizmow, ile_rodzajow_dowodu`).
v3 go odłączył i to był błąd — na jedynym live wszystkie sześć tematów miało identyczną
anatomię, czyli sygnał wyrównał się dokładnie tak jak stare siedem ocen.

#### #3 — wybór drogi artykułowej

Bez tego #2 jest **pogorszeniem**: szersze uniwersum wysłane do dyskoverii jako jedno pytanie
parasolowe rozjeżdża research na cztery strony — i to jest dokładnie to, co v3 zaobserwował
w E-020/021/022.

`feasibility` dostaje `article_routes` i musi wskazać `selected_route_index`; `pick_topic`
rozpakowuje drogę, ustawia `topic["universe_question"]` i **podmienia `topic["question"]` na
pytanie drogi**. Punkt styku jest jeden i bezpieczny (`run.py:803, 851, 875, 896, 901`).

Dwa szczegóły z danych live: głębokość **wybranej drogi** musi stać w kluczu sortowania
**przed** rankingiem uniwersum (inaczej runtime wybiera drogę SINGLE mimo trzech dostępnych
RICH — zdarzyło się w E-019), a `MAX_TOKENS["feasibility"]` trzeba przeliczyć **od liczby
dróg**, nie od liczby tematów.

#### #5 — ożywienie `LICZBA_SPOZA_KORPUSU`

Dwie zmiany, obie w v2, żadna nie wymaga kodu z v3:

1. **Przesunąć `card["unused_evidence"]` z `run.py:1114` nad `run.py:1080`.** Dziś bramka
   wykonuje się 34 wiersze przed tym, jak do karty trafi materiał z odrzuconych źródeł.
2. **Korpus z jawnej białej listy**, nie z `json.dumps(card)`: `citable_numbers[].value`
   (stokenizowane), `confirmed_claims[].evidence`, `confirmed_claims[].claim`, `excerpts`
   i `numbers` z `evidence`. Nie wchodzą: `url`, `note`, `ocena_ciekawosci`.

**Nie kopiować implementacji v3** — jest wadliwa: `agent-v3/gates.py:113-119` porównuje
surowy string `"7°C (45°F)"` z tokenem `"7"`, więc zgłasza jako spoza korpusu liczby, które
w korpusie są. Bierzemy sam regex tokenizera i piszemy resztę u siebie. Wyłączenia obowiązkowe
(liczebniki 1–12, lata 1800–2100), inaczej dostaniemy kilkanaście fałszywych alarmów zamiast
kilku uwag.

---

## 4. NIE BRAĆ

Rzeczy, które wyglądają atrakcyjnie, a przeniesione zaszkodzą.

**`editorial.quality_decision` i kwarantanny.** `agent-v3/editorial.py:260-267`:
`can_publish = (action == "READY_AUTONOMOUS")`, a `READY_AUTONOMOUS` wymaga `count == 0` —
**zera uwag**. To nie jest polityka jakości, to jest wyłącznik produkcji. Do tego
`_gate_policy` kwarantannuje **każdą nieznaną nazwę bramki**, więc dopisanie jednej podłogi
regexowej zatrzymuje agenta. Bierzemy pomysł (waga per bramka), nie kod.

**`mutation_ledger.py` z tabelami `mutation_attempts` / `action_budget_reservations`.**
Jeden stan `UNKNOWN` kwarantannuje **wszystkie** dalsze mutacje konta, a `recover_pending`
po restarcie zamienia `PENDING` w `UNKNOWN` — więc restart tego nie odblokowuje i nie ma
ścieżki ręcznej. Zamiennik za jeden wiersz: `zapisz_w_dzienniku("publikacja_start", …)`
**przed** kliknięciem i sprawdzenie tego wpisu na starcie następnego przebiegu.

**`reserve_model_budget` z blokadą dostawcy.** `agent-v3/db.py:633`:
`reserved = min(remaining, round(remaining, 6))` — rezerwuje **całe pozostałe saldo**. To nie
jest cap kosztu pojedynczego wywołania, tylko globalny muteks. A `provider_has_unresolved_cost`
blokuje dostawcę bez automatycznego wyjścia — v3 stoi dziś na tym zablokowany. Wziąć wyłącznie
pomysł trzech stanów kosztu (`KNOWN`/`RESERVED`/`UNKNOWN`) jako jedną kolumnę.

**`capabilities.py` jako plik.** `_require_isolated_target` porównuje handle celu z handle'em
konta testowego i **zakazuje handle'a produkcyjnego**. v2 ma jedno konto i ono JEST produkcją —
zakaz celu produkcyjnego byłby zakazem działania. Przenieść ideę (jedno sito przed transportem,
czytane dynamicznie), nie plik. To jest pozycja #8 w tabeli.

**`provenance.persist_article_lineage` i osiem tabel grafu dowodowego.** Podwojenie schematu
za graf, którego nikt nie odpytuje — w samym v3 jest jeden `INSERT` i **zero `SELECT`** poza
testami. Pomysł (kod nadaje identyfikatory, model może tylko wybrać istniejący fragment) jest
dobry i wraca w pozycji #6 tabeli, w wersji za dwanaście wierszy.

**`PinnedDNSBackend` z `safe_fetch.py`.** Grzebanie w prywatnym `transport._pool` httpx —
plik sam to przyznaje — plus przypięcie `httpcore==1.0.9` i nowy handshake TLS na każdy hop.
Dla bota czytającego `.gov` to pas bezpieczeństwa w fotelu przykręconym do podłogi. Z całego
`safe_fetch` bierzemy politykę redirectów, odrzucenie adresów prywatnych i limit rozmiaru
odpowiedzi (~60 wierszy, pozycja #16 w pełnej liście).

**`prompts/dyskoveria.md` z v3 w całości.** Zweryfikowałem: wiersze 55-57 i 68 mają wpisane
na sztywno `SECOND_ACT (the mine/Superfund parallel)` i polecenie o „Superfund URL" — czyli
treść jednego eksperymentu (orphaned-well, E-019) zaszytą w prompcie dla **każdego** tematu.
To jest zwykły przeciek fixtura, nie pomysł. Bierzemy sam blok `{research_context}`.

**`model_contracts.py` w całości (519 w.) z `allow_extra=False`.** W v3 nikt nie łapie
`ContractError` poza dwoma miejscami — jedno nadmiarowe pole od pisarza zabije artykuł. Jeśli
brać, to wąsko: pięć pól czytanych przez decyzje skauta, ~40 wierszy.

**`operational_days` jako tabela.** Cała wartość trwałego planu — że trzy przebiegi widzą ten
sam budżet — jest za darmo w deterministycznym ziarnie z daty. A zamrożony plan oznacza, że
podniesienie limitu w `config.py` nie zadziała do końca doby i nic o tym nie powie.

**`systemd/`, `wdroz.sh`, `TO_JEST_KOPIA_TESTOWA`.** Jednostki celowo martwe, `wdroz.sh`
kończy `exit 64`, a znacznik ma w v3 **odwrotną semantykę** niż w v2.

**`unittest` jako framework.** Silnik replayu to zwykłe funkcje; tylko warstwa asercji używa
unittest i przepisuje się na `sprawdz()` jeden do jednego.

---

## 5. Stanowisko: przenosić części, nie promować v3

Warunki, po których zmieniłbym zdanie, są konkretne i **żaden nie jest dziś spełniony**:

1. **Trzy artykuły z realnych tematów**, od skauta do zapisanego pliku, ocenione ślepo
   przeciw trzem artykułom v2. Dziś: zero.
2. **`quality_decision` przekalibrowane** tak, że ≥50% realnych artykułów v2 dostaje
   `can_publish=True`. Dziś wymaga zera uwag.
3. **Automatyczna ścieżka wyjścia z każdego stanu blokującego** (`UNKNOWN`, kwarantanna
   dostawcy, kwarantanna mutacji) bez udziału człowieka — to jest warunek konieczny dla celu
   100% autonomii. Dziś: trzy pułapki bez klucza.
4. **Cały katalog w gicie** i zielona regresja na tym drzewie. Dziś cztery z pięciu
   sprawdzonych modułów nie istnieją w `HEAD`.
5. **Pełny przebieg dnia** — notki, komentarze, restacki — pokryty testem. v3 rozwiązał
   połowę tej dziury (ścieżka artykułu), drogą tę samą, którą proponuję przenieść.

Do tego argument, który waży najwięcej: **wartość v3 mieści się w ~450 wierszach w istniejących
plikach v2 i nie łamie mandatu.** Promowanie 31 000 wierszy po to, żeby dostać cztery pomysły,
byłoby wymianą działającej produkcji na laboratorium, które dziś nie potrafi wyprodukować
artykułu.

---

## 6. Czego v3 **nie** naprawił, choć miał okazję

Sprawdziłem, czy v3 poprawił trzy wady pisarza z wczorajszego raportu. **Nie poprawił żadnej** —
`prompts/pisarz.md` jest przeniesiony niemal bez zmian:

| wada | v2 | v3 |
|---|---|---|
| „One paragraph. Not two, not three." vs „Put each unknown where it arises, alone." | w. 118 i 200 | **w. 123 i 205 — nadal obie** |
| kotwica „the two articles … run 1048 and 1101 words, and neither felt short" wysyłana też przy celu 650 | w. 6 | **w. 6, identycznie** |
| `{min_words}` przekazywane przez kod, nieobecne w prompcie | tak | **tak** |

v3 dołożył do tego promptu `{editorial_memory_json}`, ale sprzeczności nie zauważył. Wniosek
praktyczny: **naprawa promptu pisarza to nadal robota do zrobienia w v2 i nie ma jej skąd
przejąć.** To jest pozycja #5 z wczorajszego raportu i nic tu nie zmienia.

---

## 7. Kolejność

**Dziś, niezależnie od wszystkiego:** #4 (korpus stylu, jeden wiersz — v2 jest zepsute
lokalnie i już raz to kosztowało 0,39 USD).

**Jedna operacja, razem:** #1 → #2 → #3. To jest naprawa miałkich tematów. Rozdzielone nie mają
sensu: #2 bez #3 rozjeżdża research, #2 bez #1 zostawia wybór tematu przypadkowej kolejności
JSON-a, a wtedy pomiar mierzy szum.

**Zaraz potem:** #12 (replay) — bo to jedyny sposób sprawdzenia #2 bez płacenia za każdy
przebieg, i bo domyka największą niepokrytą część systemu, którą dokumentacja v2 sama nazywa.

**Potem porządki:** #5, #6, #9, #10, #7, #8.

**Osobno, po pomiarze:** #13 (`redaktor.md`). To jest trzecia opcja, której v2 nigdy nie
miał — dziś artykuł można tylko **zapisać z uwagami** albo (teoretycznie) **zablokować**.
Rewizja daje **naprawę**. Ale wchodzi wąsko: tylko bramki faktograficzne, jedna iteracja,
powrót do oryginału gdy rewizja nie poprawi, i `verdict()` nadal zwraca SAVED.

**Tryb wdrożenia dla #2, i to nie jest formalność:** trzy do pięciu przebiegów z zapisem
pełnych odpowiedzi skauta, ślepa ocena sześciu tematów z każdego przebiegu, dopiero potem
decyzja. To jest **hipoteza z n=1**, nie udowodniona naprawa — a jedyny live użył starego
system promptu.
