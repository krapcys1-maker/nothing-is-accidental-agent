# Audyt alarmu „Agent robi mniej, niż deklaruje" — 2026-08-24

**Alarm:** `alarm.py:wolumeny()`, wysłany 2026-08-24 07:08 UTC.
**Wywołujące liczby (7 dni, próg alarmowy 60%):** komentarz 46%, restack 57%.
Dodatkowo poniżej 100%, ale nad progiem: notka 63%, polubienie 70%.

**Metoda:** cztery niezależne śledztwa (jedno na kategorię) plus adwersarialna
weryfikacja każdego wniosku drugim agentem, który miał za zadanie go obalić, nie
potwierdzić. Wszystkie cztery wnioski przetrwały: 3× `CONFIRMED`, 1× `PLAUSIBLE`
(z korektą skali, nie kierunku).

## Wniosek zbiorczy

**Jeden mechanizm tłumaczy większość niedoboru w trzech z czterech kategorii.**
Blok `notki()` w `run.py` usypiał między notkami bez sprawdzenia zegara przebiegu
— systemd ubijał proces SIGTERM-em w środku snu, zanim dojdzie do PÓŹNIEJSZYCH
bloków dnia (komentarze, dyskusje, polubienia, restacki). Bot sam to
zdiagnozował i częściowo naprawił dziś w nocy, commit `dfc1e95a` („Agent zasypiał
na 90 minut, mając 20 minut do końca przebiegu"). Po tej naprawie żaden kolejny
przebieg nie padł tym samym błędem.

**Druga, mniejsza przyczyna: błąd POMIARU, nie działania.** Blok „dyskusje"
(komentowanie cudzych notek) czerpie z tego samego budżetu co komentarze, ale
loguje się jako `rodzaj="odpowiedz"` — kategoria bez normy w
`config.normy_dzienne()`, więc niewidoczna dla alarmu.

## Per kategoria

### komentarz — 46% → realnie ~67%, artefakt pomiaru

`run.py:531` (blok „dyskusje") ciągnie z `na_teraz["komentarze"]`, ale woła
`browser.wystaw_odpowiedz()` zamiast `wystaw_komentarz()`. `wystaw_odpowiedz`
zawsze zapisuje `dopisz_wynik("odpowiedz", ...)` (`browser.py:1853`), niezależnie
od przekazanego kontekstu. `normy_dzienne()` nie ma klucza `"odpowiedz"`.

Sprawdzone na żywym dzienniku: z 21 udanych wpisów `odpowiedz` w oknie 7 dni,
**15 niesie pola bloku dyskusje** (`skad`, `komentarzy_przed`, `reakcje_celu` —
dodaje je wyłącznie `opis_celu()` wołane w tym bloku). Policzone razem:
32 (komentarz) + 15 (dyskusje pod etykietą odpowiedz) = 47 z normy 70 → **67%**,
powyżej progu 60%. Weryfikator potwierdził arytmetykę i wykluczył trzecie źródło
tych pól oraz podwójne liczenie (dyskusje ciągną z INNEJ puli kandydatów — notek,
nie artykułów). Drugorzędnie: prawdziwe ucinanie czasu w tych blokach też
wystąpiło kilka razy w tygodniu (dowód: 15 linii `[czas] ...` w journalctl) —
realny, ale mniejszy czynnik.

**Klasyfikacja: BUG POMIARU.** Nie wymaga zmiany zachowania bota — wymaga, żeby
dyskusje dostały własną normę albo własną kategorię w dzienniku.

### restack — 57%, mieszane

- **~3 z 7 dni okna: artefakt rozruchu.** Blok restacków nie istniał w kodzie do
  wieczora 19.08 (commit `088e8803`). Norma liczona wstecz zakłada funkcję, która
  jeszcze nie chodziła.
- **~5 z 15 przebiegów po wdrożeniu: ten sam bug co notki** (SIGTERM w
  `notki()`/sen, proces ginie zanim dotrze do restacków). Naprawiony `dfc1e95a`
  — od 23.08 wszystkie przebiegi docierają do bloku.
- **0%: brak kandydatów.** Każdy przebieg, który dotarł do bloku, widział 5–6
  kandydatów notek do podania dalej.
- Jeden wpis `restack` w dzienniku (22:44:20, 19.08) nie odpowiada żadnemu
  przebiegowi serwisu — prawdopodobnie działanie ręczne właściciela (por.
  `project-nia-konto-reczne` w pamięci).

### notka — 63%, ten sam bug + luka wciąż żywa

Ten sam SIGTERM-w-`notki()`: w oknie 7 dni **4 przebiegi FAILED** + weryfikator
doliczył **3 kolejne STALE** (zawieszone na SIGKILL, w tym jeden zablokował
zamek `agent.lock` i skasował CAŁY następny zaplanowany przebieg — „Inny
przebieg już działa. Kończę bez zmian"). Razem **7 uszkodzonych przebiegów w
oknie 7 dni**, nie 4–5, jak podał pierwszy raport.

**Luka, która NADAL istnieje po naprawie `dfc1e95a`:** naprawiono sen MIĘDZY
notkami (`rytm()`), ale `ZWLOKA_PRZED_NOTKAMI` — losowe opóźnienie PRZED
pierwszą notką (`run.py:423-425`, goły `time.sleep(ile)`) — wciąż nie sprawdza
`zostal_czas()`. To ono zabiło jedyną zaplanowaną notkę w przebiegu z 19.08
(zabity 14,5 min w 34-minutową zwłokę).

Drobniejszy, nieszkodliwy czynnik: `zmiesci_sie()` świadomie przycina notki,
gdy nie starczy czasu na wszystkie (działa zgodnie z zamysłem) — potwierdzony
1 przypadek. Kandydaci notek odrzucani jako duplikaty przed publikacją też nie
zostawiają śladu w dzienniku (ani sukces, ani porażka) — analogiczny artefakt
pomiaru jak przy komentarzach.

### polubienie — 70%, silniejsza wersja tego samego bugu

**To nie jest sufit podaży w kanale** — tam, gdzie blok dobiegł końca, realizował
niemal zawsze 100% żądania (`5/5`, `4/4`, `3/3`...). Weryfikator policzył
niezależnie: w oknie 7 dni **7 z 23 przebiegów zginęło**, nie 4, zanim/w trakcie
realizacji polubień — część ze śladem SIGTERM, część **bez żadnego tracebacku**
(prawdopodobny SIGKILL, możliwe źródło: twardy limit pamięci cgroup — NIE
zweryfikowane, wymaga sprawdzenia jednostki systemd). Jeden z tych przebiegów
(STALE, id 18) zablokował zamek na ~16h i skasował kolejny zaplanowany przebieg
w całości.

## Co jest już naprawione, a co nie

| | stan |
|---|---|
| sen MIĘDZY notkami bez sprawdzenia zegara | naprawione `dfc1e95a`, 2026-08-23 |
| `ZWLOKA_PRZED_NOTKAMI` (sen PRZED pierwszą notką) bez sprawdzenia zegara | **wciąż żywe** |
| możliwy SIGKILL bez tracebacku (limit pamięci?) | **nie zweryfikowane** — wymaga sprawdzenia jednostki systemd (`MemoryMax`, `RuntimeMaxSec`) wobec `config.LIMIT_CZASU_PRZEBIEGU_S=9000` |
| dyskusje logują się jako „odpowiedz" zamiast własnej/liczonej kategorii | **wciąż żywe** — fałszywe alarmy na kategorii komentarz mogą się powtórzyć |

## Czego NIE zmieniłem

Zero kodu, zero wdrożenia. To wyłącznie diagnoza — zgodnie z zamrożeniem
przyjętym dziś wcześniej. Dwie sprawy kwalifikują się do tej samej kategorii co
naprawiona wcześniej dziś usterka obserwacji (aktywnie tnie działanie bota, nie
kwestia gustu): `ZWLOKA_PRZED_NOTKAMI` i weryfikacja limitu pamięci. Reszta to
kwestia pomiaru, nie działania, i może poczekać do końca zamrożenia.
