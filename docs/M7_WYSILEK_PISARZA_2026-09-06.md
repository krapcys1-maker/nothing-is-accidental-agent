# M7: `high` czy `medium` przy pisarzu artykułu — rozstrzygnięte

Audyt: „Pisarz artykułu: 0,76 USD, z czego wejście to około jednej ósmej.
Dźwignią jest głębokość myślenia… **nie zmieniać na ślepo**."

Kryterium ustalone **przed** pomiarem, przez audyt: *„Uwagi bramek i beaty na
150 słów na obu wersjach; jeśli wersja medium ma więcej uwag albo mniej beatów,
zostaje high."*

## Jak to zrobiłem

Jedna karta dowodowa (`--do-karty`, temat: Gemini 3.8 Flash Cyber i program
Fairwind), z niej **dwa razy ten sam artykuł** przez `--z-karty`, raz
`EFFORT["write"] = high`, raz `medium`. Wszystko w **odizolowanych katalogach**
z kopią bazy — bo `_napisz_i_zapisz` wstawia wiersz do `articles`, a straż
powtórek czyta od 6 września całą tę tabelę, więc dwa eksperymentalne artykuły
o Gemini **spaliłyby ten temat** dla wtorkowego artykułu.

Okładki pominięte (~0,04 USD × 2) — nie mają wpływu na tekst.

Produkcja po wszystkim: **15 artykułów, tyle samo co przed**. Zero nowych
plików w katalogu artykułów.

## Pieniądze

| etap | high | medium |
|---|---|---|
| `write` — wejście | 16 777 | 16 770 |
| `write` — **wyjście** | **13 714** | **7 066** |
| `write` — koszt | **0,8535 USD** | **0,5210 USD** |
| cały przebieg | 0,9632 USD | 0,6213 USD |

Wejście identyczne co do 7 tokenów — potwierdza to, co audyt mówi wprost:
**skracanie promptu nic tu nie da**, cała różnica jest w wyjściu.

Oszczędność: **0,33 USD na artykuł, 39% na samym pisarzu.** Przy jednym
artykule tygodniowo to **1,33 USD miesięcznie**, czyli około 3% budżetu
40 USD obowiązującego od października.

## Jakość — kryterium audytu

| miara | high | medium |
|---|---|---|
| uwag bramek (zarzutów) | 6 | 6 |
| **przekonań w tekście** | **6** | **5** |
| słów | 1196 | 1142 |
| jedno przekonanie co N słów | **199** | **228** |

Próg bramki to 150 słów — **obie wersje go nie osiągają**, `medium` wyraźniej.

Zarzuty wspólne (5): `CALY_MATERIAL_STARY`, `UWAGA_O_WIEKU` (właściwości karty,
identyczne dla obu), `CZYTELNIK_NIEPRZYLAPANY`, `FAKT_BEZ_POKRYCIA`,
`GESTOSC_BEATOW`.

Różnica jednego zarzutu po każdej stronie:
- tylko `high`: **`BRAK_ESKALACJI`** — najmocniejszy fakt idzie tym samym tonem
  co szczegół proceduralny;
- tylko `medium`: **`BUDZET_ZASTRZEZEN`** — dwa zastrzeżenia przy budżecie
  jednego, oba tą samą frazą „My reading".

## Jakość — co widać po przeczytaniu

`high` zaczyna od samej rzeczy: *„Google's most capable cybersecurity model is
not the one it sells"* — i domyka pierwszy akapit pointą *„the better tool is
the one you cannot pay for"*.

`medium` zaczyna od rozbiegu: *„For about a decade the arrangement between
frontier AI labs and the rest of us has been simple…"* — i dochodzi do tezy
dopiero w drugim akapicie. To dokładnie ten rozbieg, którego prompty zakazują
gdzie indziej („Start with the mechanism itself, no preamble").

## Decyzja: ZOSTAJE `high`

Kryterium audytu wskazuje `high` jednoznacznie — `medium` ma **mniej beatów**
(5 wobec 6). Czytanie zgadza się z liczbą: słabsze otwarcie i podwójne
zastrzeżenie tą samą frazą.

**Uczciwie o wadze tego dowodu:** to jeden artykuł na wersję, z jednej karty, na
jednym temacie. Różnica to jedno przekonanie i jedno otwarcie. Gdyby stawka
była większa niż 1,33 USD miesięcznie, ta próbka nie wystarczyłaby na decyzję.
Przy tej stawce — wystarcza, bo kryterium było ustalone z góry i wskazuje
w jedną stronę.

**Nic nie zmieniam w kodzie.** `EFFORT["write"] = "high"` zostaje.

## Dwie rzeczy do zapisania osobno

**1. Mój pierwszy przyrząd porównawczy dał dobrą odpowiedź z fałszywych
danych.** Szukał uwag wzorcem `[NAZWA]`, a `stages.save` zapisuje je jako
`'gate': 'NAZWA'` — więc dla `high` znalazł **zero** uwag przy sześciu
faktycznych i ogłosił „zostaje high", bo `medium` miało rzekomo jedną więcej.
Werdykt wyszedł ten sam co po naprawie, ale **z zupełnie innego powodu**.
Gdybym mu zaufał, miałbym rację przez przypadek. Liczył też „beaty" jako
akapity, podczas gdy bramka `GESTOSC_BEATOW` liczy przekonania i sama podaje
wynik.

**2. Koszt dwóch przebiegów pisarza (1,58 USD) NIE jest w księgach konta.**
Obliczenia szły przeciwko kopii bazy w katalogu tymczasowym, żeby nie spalić
tematu — więc pieniądze są na rachunku u dostawcy, ale nie w naszej tabeli
`calls`. Sama karta (0,3077 USD) jest zapisana normalnie, w trybie testowym.
Cały eksperyment: **1,89 USD**.
