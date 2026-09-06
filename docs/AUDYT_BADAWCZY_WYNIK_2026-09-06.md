# Audyt badawczy (S/M/Q) — co z tego wyszło

Audyt zrobiony na **czystym bocie**, nie na naszym drzewie. Przerobiony punkt
po punkcie 5–6 września 2026, każdy sprawdzony na żywej produkcji przed
tknięciem kodu.

Serwer po całości: `82a427a`, zestaw na serwerze **158 zdanych / 0 oblanych**.

## Naprawione (9)

| punkt | co było, zmierzone na produkcji |
|---|---|
| **Q5** | Siedem artykułów z rzędu (9–15) wyrzuciło **cały opłacony materiał**. Bank stanął na 299 fragmentach 25 sierpnia; każda z tych kart niosła 7–8 źródeł. Przyczyna w sygnaturze: `_napisz_i_zapisz` nie dostawało `evidence`. |
| **Q2** | 50 notek napisanych, 40 wystawionych — **6 straconych spaliło 6 faktów**. Pięć ścieżek oddaje teraz fakt do puli. |
| **Q7** | Do pisarza notek szło **27 pól** wpisu banku, w tym `powod` z **tekstem wcześniejszej notki** — a prompt mówi „background you may draw on". Biała lista 12 pól. |
| **Q11** | Straż powtórek artykułu widziała **5 z 15**. Wśród widocznych: „The Guardrails Were Off on Purpose" i „…Because That Was the Test". |
| **S2** | Przebieg artykułu 77 kosztował **1,5918 USD przy suficie 1,60** — osiem tysięcznych zapasu. Osobny sufit 2,20. |
| **M6** | Druga runda dyskoverii liczyła sztuki, nie rekordy. Komentarz „tak samo jak w run.py" kłamał. |
| **M1** (artykuł) | Weryfikator dostawał **sam tytuł**, mimo pełnej karty dowodowej. |
| **R11** | Pisarz dostawał niepobrany fakt bez słowa wyjaśnienia. |
| **Q1** | Zamknięte przez `oznacz_uzyty` (B6). Kontrola audytu: „opublikowane, a nadal nowy: **0**". |

## Zmierzone jako niedotyczące nas (9)

| punkt | dlaczego |
|---|---|
| **M1** (koszt) | Audyt: „≈0,8 USD/dobę, większa pozycja niż pisanie". Zmierzone: **0,24 USD/dobę, 9,2% rachunku**, 4,3–5,5 rundy. Własny próg audytu (≤6 rund, <25%) spełniony. |
| **M2** | `COMMENT_CANDIDATES` już jest 1 (świadomie, `0e8f2bb`). Otwarcia różnicuje osiem losowanych `{otwarcie}`. Kontrdowód audytu sprawdzony: udział najczęstszego pierwszego słowa **spadł** 16,9% → 11,8%. |
| **M5** | Mechanizm „co jest aktualne" zbudowano pod listę modeli — a **nasza nisza to modele** (zmiana właściciela z 25 sierpnia). Plik zawiera 24 modele z laboratoriami i datami. |
| **Q3** | W 14 dniach **jedna** notka odpadła na długości i miała **66 słów**, czyli była ponad SUFITEM. Zero strat na podłodze 33. |
| **Q4** | Zrobione: `poprawka = None if note_type == "MYSL"`. |
| **Q6** | **48 z 48** odpowiedzi w 14 dni jest pod notkami, zero pod artykułami. Kryterium audytu: „blisko zera = niski priorytet". |
| **Q8** | Audyt zakłada niszę nie-AI. Nasza **jest** AI. W drugą stronę też czysto: jedyne dwie wzmianki o starej niszy („shampoo") to celowe **kontrprzykłady**, m.in. „stara reguła… żeby nikt jej nie przywrócił". |
| **Q9** | Produkcja ma **13 kanałów**, nie 0. |
| **Q10** | Audyt sam: „w produkcji 0, bo ścieżka nie jest na zegarze". |

## M7 — rozstrzygnięte pomiarem, zostaje `high`

Jedna karta, dwa razy ten sam artykuł, `high` kontra `medium`. Pełny zapis
w [M7_WYSILEK_PISARZA_2026-09-06.md](M7_WYSILEK_PISARZA_2026-09-06.md).

| | high | medium |
|---|---|---|
| `write` wyjście | 13 714 | 7 066 |
| `write` koszt | 0,8535 USD | **0,5210 USD** |
| uwag bramek | 6 | 6 |
| **przekonań** | **6** | **5** |

Wejście identyczne co do 7 tokenów — cała różnica jest w wyjściu, więc audyt
ma rację, że skracanie promptu nic tu nie da.

Kryterium audytu („medium ma więcej uwag ALBO mniej beatów → zostaje high")
wskazuje `high`: uwagi remis 6:6, ale przekonań 5 wobec 6. Czytanie zgadza się
z liczbą — `medium` zaczyna akapitem rozbiegowym zamiast od mechanizmu.

Odrzucona oszczędność: 0,33 USD na artykuł, 1,33 USD miesięcznie, ~3% budżetu
październikowego.

## Co znalazłem POZA audytem, i co było ważniejsze

1. **Zapora „ta sama nazwa" rozbrajała się tym, przed czym broniła.** `glm53`
   miał 3 wystąpienia przy progu 2 — te same trzy notki z 31 sierpnia, które
   kazały ją napisać, przekroczyły próg i ją wyłączyły.
2. **A po naprawie blokowała 123 nazwy ze 124** — złapane na żywo: przebieg 154
   miał przydział 3 notek, wydał 1, odrzucając `astra`, `google`, `claude`,
   `anthropic`. Drugi mianownik z korpusu źródeł (206 tematów) rozróżnia:
   `claude` 4,4% źródeł, `glm53` 1,9%.
3. **`fakt_ranga` było ZAWSZE puste** — 18 wpisów w dzienniku, 18× `None`.
   Przyrząd zbudowany, żeby zmierzyć, czy ranking banku cokolwiek przewiduje.
4. **`.gitignore` zjadał cały plik testu** — wzorzec `*klucz*` połykał
   `test_klucz_przed_wywolaniem.py`, którego nigdy nie było w repozytorium.
5. **Sześć testów czytało żywy dziennik**, więc dawały inny wynik na każdej
   maszynie. Pod dwoma z nich ukrywały się usterki z punktu 1.

## Wzorzec, który wrócił pięć razy jednego dnia

Niepełna atrapa `stages` podnosi `AttributeError`, `blok()` go połyka, objaw
wygląda jak „etap się nie wykonał". Trzy klasy `AtrapaStages` mają teraz
`__getattr__`, które **wypisuje** nazwę brakującej metody przed `raise` — bo to
wyjątek bywa połykany, a wydruk nie.

## I trzy razy pomyliłem się tak samo

Trzy liczby w `docs/KOSZT_2026-09-05.md` musiałem skreślić: średnia 2,60
USD/dobę, „największa dźwignia" o `curiosity`, „przyrząd ślepy na 33%".
Wszystkie **policzone poprawnie**, wszystkie prowadzące do złego wniosku, bo
okno pomiaru nie pokrywało się z oknem zmian. Kolejność zapisana tam na
przyszłość: najpierw `git log -S`, potem pomiar w oknach, i osobno odsiać
własne uruchomienia.
