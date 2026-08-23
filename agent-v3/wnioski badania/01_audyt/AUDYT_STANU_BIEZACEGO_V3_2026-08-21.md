# Audyt stanu bieżącego Agent V3 — 2026-08-21

**Przedmiot:** aktualne drzewo robocze `agent-v3` po fundamentach N-001–N-011,
N-016/N-017, N-019/N-020 i N-023–N-028  
**Tryb bazowy:** statyczny i offline; aneks wykonawczy E-014–E-018 użył modeli
bez Substacka, przeglądarki, deploymentu i publikacji  
**Gałąź:** `codex/agent-v3-gpt`  
**Wniosek gotowości:** `NOT_READY`, ale `PROTOTYPE_SAFELY_INERT`

## 1. Pytania badawcze

1. Co V3 rzeczywiście już odziedziczyło i rozwinęło, a czego nie trzeba budować
   ponownie?
2. Które własności są udowodnione testem offline, które tylko częściowo live, a
   które pozostają deklaracją?
3. Czy aktualne granice mutacji, kosztu, stanu redakcyjnego i promocji są
   wystarczające dla pełnej autonomii?
4. Jaki minimalny zestaw pracy pozwoli kolejnemu agentowi naprawiać V3 bez
   naruszenia V2 i bez projektowania systemu od zera?

## 2. Materiał i metoda

Audyt objął:

- wszystkie główne moduły Python, 27 plików promptów/aktywnych materiałów oraz
  katalogi testów, danych, systemd i dokumentacji;
- 22 aktywne granice `llm.call()` oraz centralny rejestr schematów;
- wszystkie znalezione granice sieciowe i mutujące w `browser.py`, `llm.py`,
  `safe_fetch.py` i `alarm.py`;
- przepływ artykułu od wyboru tematu do zapisu, rewizji i publikacji;
- bieżący ledger mutacji, dobę operacyjną, budżet modeli, graf pochodzenia i
  pamięć redakcyjną;
- porównanie 99 wspólnych ścieżek V2/V3 wyłącznie przez odczyt;
- kompletność kart napraw, instrukcji testów i drogi późniejszej promocji.

Fakty odczytano z kodu i plików. Hipotezę wyścigu kosztowego sprawdzono
kontrdowodem z dwoma połączeniami SQLite. Nie użyto żadnego zewnętrznego
transportu. Szczegółowa metoda i ograniczenia znajdują się w
`../07_dziennik_badan/METODOLOGIA_I_REPRODUKCJA.md`.

## 3. Migawka ilościowa

Migawka wejściowa przed dopisaniem bieżącej dokumentacji:

| Obszar | Wielkość |
|---|---:|
| wszystkie pliki V3 | 208 |
| pliki Python V3 | 74 |
| główne moduły Python | 17 |
| pliki testowe Python | 55: 44 offline i 11 płatnych |
| pliki promptów i materiałów w `prompts/` | 28 |
| aktywne granice odpowiedzi modelu | 22 |
| wspólne ścieżki V2/V3 | 99 |
| wspólne pliki bajtowo identyczne | 29 |
| ustalenia historycznej migawki przed E-014/E-015 | 103: P0=22, P1=67, P2=14 |

Liczby plików w tym akapicie są historyczną migawką audytu przed E-011/E-012;
nie należy ich używać jako bieżącego inwentarza. A-102 dopisano później po
wykonawczej symulacji pełnego live, a A-103 po kontroli raw artefaktu. Po zapisaniu audytu, 22 kart napraw,
instrukcji następnego agenta i testu
niezmienności routingu drzewo ma 223 pliki: 75 Python, 91 Markdown, 45 głównych
plików `test_*.py` oraz 11 skryptów Python w `tests/platne/` (jeden nie zaczyna
się od `test_`). Katalog badawczy zawiera 60 dokumentów Markdown. Zmiana tych
liczb jest oczekiwanym skutkiem samej dokumentacji i jednego testu offline, nie
nowej funkcji produktu.

Największe moduły pozostają monolityczne: `stages.py` ma 3140 linii,
`browser.py` 2738, `config.py` 1616, a `run.py` 1397. To argument za
wydzielaniem kontraktów wokół istniejących etapów, nie za przepisywaniem
potoku.

## 4. Co jest już zrobione

### 4.1. Istniejący produktowy rdzeń

V3 ma działające elementy fabryki treści: scouting, feasibility, discovery,
bezpieczny fetch, klasyfikację, syntezę, kartę dowodową, pisarza, recenzenta,
obserwację formy, deterministyczne bramki, jedną autonomiczną rewizję, zapis,
generowanie krótkich formatów i adapter platformowy. Jest to rozwinięcie V2.

### 4.2. Fundament bezpieczeństwa prototypu

- domyślny tryb `fixture` nie ma żadnej capability;
- sekrety są nazwane prefiksem V3 i nie są czytane w fixture;
- cel produkcyjny jest bezwarunkowo odrzucany;
- `wyslij=False` dla publikacji kończy się przed sesją i przeglądarką;
- systemd i `wdroz.sh` są celowo nieuruchamialne;
- V3 nie wykonuje kodu V2.

### 4.3. Dowody i kontrakty

- 22/22 granice modeli przechodzą przez wersjonowany schemat;
- graf dokument–fragment–twierdzenie–zdanie–cytowanie jest utrwalany i
  rewalidowany;
- bezpieczny fetch waliduje scheme, publiczny unicast, DNS, redirecty, rozmiar
  i dokładny dokument;
- ledger rozróżnia intencję, dispatch, wynik potwierdzony i `UNKNOWN`;
- doba redakcyjna i wolumen mutacji są transakcyjnie zamrożone;
- koszt po możliwym dispatch nie staje się zerem ani cichym retry.

### 4.4. Dowód live o ograniczonym zakresie

E-007 wykonał siedem wywołań modeli: sześć kompletnych odpowiedzi i jedną
płatną, niepełną syntezę DeepSeek. Sonnet przeszedł klasyfikację, syntezę i
recenzję; DeepSeek klasyfikację i recenzję. Łączny znany/estymowany koszt wyniósł
0,07558670 USD. Sonnet był runtime override harnessu, nie częścią normalnego
routingu V3; wybór nie miał osobnej autoryzacji modelu i został zablokowany w
bieżącej uprzęży. Nie był to test pełnego artykułu ani platformy.

### 4.5. Aneks wykonawczy E-014/E-015

Izolowane ramię Anthropic wykonało 8/8 planowanych granic. Fable napisał dwie
wersje artykułu na tej samej karcie (z profilem stylu i po ablacji) oraz usunął
wstrzyknięte fałszywe zdanie o 12 wypadkach bez innych zmian w tekście. Opus
wygenerował pięć form Notes. Znany koszt wyniósł 1,341430 USD.

Dowód jest mieszany, a nie bezwarunkowo dodatni. Wariant stylowany miał 817
słów przy kontrakcie `RICH` 900–1250; oba artykuły dodały faktycznie brzmiące
przesłanki nieobecne w zamrożonej karcie; forma `ODWROCENIE` nie zrealizowała
semantycznie briefu, a trzy Notes zaczęły się od tych samych trzech słów.
Różnica stylu pochodzi z jednej pary, więc nie pozwala na wniosek przyczynowy.
Brak ramienia DeepSeek oznacza także brak live review, form-review, ślepych
sędziów i fact-checku Notes. Każdy kandydat pozostał `safe_to_post=false`.

DeepSeek Pro trzy razy nie dostarczył nawet odpowiedzi Scouta: T-118, T-132 i
T-136 użyły materialnie różnych promptów, a trzecia próba skróciła wejście z
23 193 do 7 499 znaków. Każda skończyła się `incomplete chunked read` bez
usage, request ID i odpowiedzi. To nowy P0 A-104. Trzy rezerwy po 1,60 USD są
traktowane jako 4,80 USD `UNKNOWN`.

N-025 zastąpiło buforowany transport DeepSeek parserem oficjalnego SSE.
Sukces wymaga teraz treści, końcowego usage, `finish_reason=stop` i znacznika
`[DONE]`; brak któregokolwiek elementu pozostaje `UNKNOWN` i bez retry. Testy
offline przeszły 25/25. Nie jest to dowód live naprawy transportu. Kod blokuje
czwartą próbę DeepSeek do rekoncyliacji rachunku i odzyskania sublimitu.

### 4.6. Aneks wykonawczy E-016–E-018 — Scout

E-016 po raz pierwszy potwierdziło live pełny transport SSE Scouta DeepSeek:
2 197/15 714 tokenów, 247,062 s i 0,032564 USD. Treściowo stara architektura
zawiodła: sześć tematów było nasyconych, miało identyczną liczbę wątków, a
boil-water notice przeszło jako artykuł.

E-017 feasibility przeszło za 0,005868 USD. Discovery `/responses` powtórzyło
niepełny chunked read i zachowało 0,10 USD `UNKNOWN`; N-026 ma SSE 4/4 offline.

E-018 zmieniło jednostkę Scouta z obiektu/systemu na otwarte uniwersum
artykułowe. Jeden DeepSeek Pro zwrócił sześć tematów oraz pięć odrzuconych
zalążków; model sam odrzucił boil-water notice jako notkę. Transport i schemat
przeszły, a exact raw replay po usunięciu arbitralnego progu pięciu dróg dał
6/6. Live nadal użył starego system promptu kotwiczącego w systemach; jego
otwarta wersja ma tylko dowód offline.

Koszt E-018 0,049298 USD przekroczył cap etapu 0,04 USD. N-028 naprawia
predispatch worst-case w Scout-only, ale wspólny runtime pozostaje otwarty.
Finalna zwykła regresja T-160 wynosi 55/55.

## 5. Co pozostaje otwarte

### 5.1. Blokery P0

N-004, N-019, N-020 i N-010 mają obecnie dowody offline; nie są już otwartymi
wadami w badanym modelu fixture. Live N-004/E-012 i rzeczywisty zanik zasilania
N-010 pozostają nieudowodnione.

N-011 ma obecnie dowód offline: dwie iteracje, pełne rechecki, brak
`NEEDS_REVIEW` i terminalna kwarantanna. Kalibracja polityki oraz live model
pozostają otwarte, ale historyczna ścieżka fallbacku została usunięta.

1. Wspólny runtime może rozliczyć więcej niż zarezerwowany cap; lokalna ochrona
   Scout-only nie zamyka A-112/N-028.
2. Discovery `/responses` ma tylko dowód SSE offline, a cztery pozycje kosztowe
   pozostają nierozliczone — A-104/A-108, N-025/N-026.
3. Nie istnieje release-grade migracja ani niemutowalny artefakt — N-018.
4. Odnowienie sesji i kopia jedynego nieodtwarzalnego aktywa nie są autonomiczne
   — A-100/N-022.

### 5.2. Blokery redakcyjne P1

- redaktor nie otrzymuje tego samego kontraktu głosu co pisarz;
- profile Notes i krótkich formatów nie są wykonawczo wersjonowane;
- surowe sygnały zewnętrzne mogą trafiać do trwałej pamięci promptowej;
- prompt odpowiedzi stawia zaporę po części niezaufanych danych;
- testy promptów badają głównie frazy i placeholdery, nie semantykę;
- kolektor kohort, metryk i uczenia nie jest domknięty;
- dokładne ID opublikowanego artykułu ginie przed `content_items` — A-099;
- profile głosu są poza bundle i bez hashy loadera — A-094.

### 5.3. Operacje i testy

Katalog offline jest dobrze odseparowany od katalogu płatnego. Starsze skrypty
płatne nadal nie mają wspólnej izolacji i nie są automatyczną bramką release.
E-010 i E-012 mają własne ścisłe launchery, tymczasową bazę, maszynowe kryteria
i fail-closed preflight. E-014 dodało trzynasty skrypt płatny z osobnymi
ramionami dostawców. Anthropic zakończył 8/8; DeepSeek ma trzy stare próby
Scouta oraz discovery w stanie `UNKNOWN`, a E-016/E-018 ukończone live Scouty.
Łączna konserwatywna ekspozycja programu wynosi
6,40474670 USD, w tym 4,90 USD nierozliczone. Po zmianie kontraktu Scouta
finalna zwykła regresja T-160 wynosi 55/55.

## 6. Kontrdowód wyścigu kosztowego

Warunki: dwa wątki, dwa połączenia do jednej tymczasowej bazy, jeden `run_id`,
`RUN_LIMIT_USD=0.25`, brak sieci. Oba wątki wyliczyły rezerwację przed zapisem i
zsynchronizowano je barierą.

| Wynik | Wartość |
|---|---:|
| rezerwacja procesu 1 | 0,25 USD |
| rezerwacja procesu 2 | 0,25 USD |
| końcowa ekspozycja | 0,50 USD |
| skonfigurowany limit | 0,25 USD |

Wynik obala hipotezę, że samo trwałe `calls.RESERVED` wystarcza do ochrony
limitu. Rezerwacja jest trwała, lecz check-and-insert nie jest atomowy.

## 7. Odpowiedź: co wykorzystać z V2

Nie budować ponownie:

- orkiestracji `run.py` i etapów `stages.py`;
- promptów bazowych, korpusu stylu i mechaniki krótkich formatów;
- adaptera platformowego i jego selektorów;
- historycznych testów zachowania, rytmu i treści;
- schematu `runs/calls/articles/sources` jako materiału migracyjnego;
- wiedzy operacyjnej z timerów i preflightu V2.

Trzeba je opakować kontraktami V3: transakcją, typami, fixture replayem,
ledgerem, wersją schematu i maszynową decyzją. Dokładna macierz znajduje się w
`MACIERZ_ODZIEDZICZENIA_V2_V3.md`.

## 8. Kolejność dalszej pracy

1. N-019 — `FIXED_OFFLINE`, ledger zdalnego szkicu przed pierwszym bajtem.
2. N-020 — atomowość `FIXED_OFFLINE`, lecz cap faktyczny ponownie otwarty przez
   A-112/N-028.
3. N-004 — pełny replay fixture 7/7; pełny live nadal nieudowodniony i obecnie
   zablokowany przez limit i rekoncyliację DeepSeek, nie brak kluczy.
4. N-010 — `FIXED_OFFLINE`, transakcyjny zapis; power loss nieudowodniony.
5. N-023 — `FIXED_OFFLINE`, kanoniczny pin stylu; pisarz live nieudowodniony.
6. N-011 — `FIXED_OFFLINE`; pojedyncza live rewizja usunęła kontrolowany fałsz,
   lecz pełne rechecki DeepSeek nie wystartowały.
7. N-027/N-028 — dalsze kontrprzykłady Scouta i wspólny cap wyłącznie offline.
8. N-025/N-026 — zrekoncyliować 4,90 USD `UNKNOWN`; dopiero potem osobno
   potwierdzić discovery SSE i poprawiony system prompt Scouta.
9. N-015/N-013 — semantyczne testy, prawdziwość przesłanek pisarza,
   różnorodność Notes i wersjonowany głos.
10. N-014 — izolacja niezaufanych danych.
11. N-012/N-021 — dokładne ID publikacji, snapshoty, kohorty i uczenie.
12. N-018/N-022 — release bundle, migracje i autonomiczne wymagania operacyjne.

Każdy krok ma najpierw użyć istniejącego mechanizmu V2/V3, następnie dodać
kontrdowód i minimalną zmianę wyłącznie w V3.

## 9. Granice wniosku

Audyt nie dowodzi zgodności z aktualnym UI Substacka, jakości pełnego artykułu
na wielu tematach ani zachowania kilku procesów na docelowym serwerze. E-014
bada jeden materiał i nie ma live recenzji DeepSeek. E-018 dowodzi działania
transportu i jednego portfela Scouta, ale nie poprawionego system promptu ani
stabilnej jakości w wielu replikacjach. Dowody obejmują konkretne ścieżki kodu,
fault injection, odtworzony wyścig SQLite i ograniczone odpowiedzi live. Żaden
wynik nie upoważnia do zdjęcia blokad prototypu.
