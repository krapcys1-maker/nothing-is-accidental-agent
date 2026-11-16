# E24: wzór restacka (16.11.2026)

Decyzja właściciela z 16.11.2026: test nowego wzoru restacków ma ruszyć od razu, bez czekania na ocenę zmian z 13.11
(zaplanowaną na 27.11). Pełna analiza, z której to wynika: `robocze/ANALIZA_PRZYROSTU_NIE_FABLE.md`.

**Data wdrożenia: patrz „Wdrożenie” na końcu.**

## Dlaczego

- Od 7.09 restacki drugiego konta dały 18 zapisów przypisanych przez Substack na 257 restacków: 7,0 na 100 (95%: 4,2–11,1).
  Nasze: 1 na 136, czyli 0,74 na 100 (0,01–4,1). Przedziały się nie pokrywają. To jedyna różnica między kontami poza szumem.
- Zasięg restacka: mediana 19–20 wyświetleń u nich, 10 u nas (19.10–12.11). Autor odpowiada na 31% ich restacków i na 12% naszych.
- Nasz restack to dopisek recenzenta: 36 słów, jeden akapit, otwarcia „The useful…”, „Worth noting…”. Ich restack to samodzielna
  mini-notka: 56 słów, 2–3 akapity, imię autora, stanowisko.
- Zwiększenie liczby restacków z 13.11 (3–4 dziennie) nie zmienia wzoru, więc mnoży treść o wskaźniku 0,74 na 100.

## Co się zmienia

Eksperyment przeplatany `wzor_restacka` (`config.EKSPERYMENTY`), 50/50, 17.11–28.12.2026.

| | ramię „off” (jak dotąd) | ramię „on” |
|---|---|---|
| polecenie | `prompts/restack.md` | `prompts/restack_glos.md` |
| komunikat systemowy | `stages.RESTACK_SYSTEM` | `stages.RESTACK_SYSTEM_GLOS` |
| kształt | dopisek do 40 słów | trzy akapity po jednym zdaniu, prośba o 60 słów |
| limit w kodzie | `RESTACK_MAX_SLOW` = 40 | `RESTACK_MAX_SLOW_GLOS` = 75 |
| treść | uwaga do notki | własna myśl zrozumiała bez oryginału, jeden konkret z notki z imieniem autora, stanowisko w pierwszej osobie |
| model | etap `restack` (bez zmian) | etap `restack` (bez zmian) |

W obu ramionach bez zmian: zapora na cudzym tekście i na naszym, podłogi „zmyślone przeżycie” i „nieistniejące badanie”, fakty tylko
z widocznej notki, odmowa przy cudzym nieszczęściu, limit działań u autora, liczba restacków na dobę, dobór celów.
Nowe polecenie dodatkowo każe odmówić przy liście, zbiorówce, notce o postępowaniu nazwanej osoby i notce nie o AI.

**Los jest stały dla notki.** Kluczem jest odcisk notki bez etykiety wieku (`browser._odcisk_notki`, przekazywany w polu `odcisk`),
a ramię nie zależy od dnia (`stages.ramie(..., staly_los=True)`). Ta sama notka dostaje to samo ramię w każdym przebiegu, więc notka
odrzucona w „on” nie wyjdzie później w „off”. Pierwsza wersja liczyła hasz z całego tekstu kontenera razem z wiekiem („2h”) i licznikami,
czyli losowała od nowa co przebieg (wykrył to przegląd).

**Imię autora tylko, gdy jest pewne.** W ramieniu „on” imię trafia do publicznego tekstu. Pole `autor` to pierwszy odsyłacz do profilu
w kontenerze notki, a przy pozycji „X restacked” może to być X. Gdy nagłówek notki nie zawiera tej nazwy albo mówi o restacku,
polecenie nie dostaje nazwy i pisze „this note”.

**Odporność na kształt odpowiedzi modelu (tylko „on”).** Prawdziwy znak nowej linii w polu JSON, lista zdań zamiast napisu i dosłowne
`\n` są sprowadzane do akapitów; pole innego typu oznacza brak tekstu, nie publikację.

Pamięć głosu (`stages.pamiec_glosu`) nie miesza ramion, jak w E23: `restack_glos.md` widzi tylko restacki ramienia „on”,
`restack.md` wszystkie pozostałe.

Dziennik zapisuje ramię w polu `eksperymenty.wzor_restacka` i tekst restacka do 600 znaków (było 300). Odmowa w logu przebiegu
niesie ramię (`pomijam [wzor on]: …`). Wpisywanie tekstu w okno restacku ma jawny limit czasu 120 s (domyślne 30 s mogło nie wystarczyć
na ok. 500 znaków).

To jest **paczka** (długość, układ, głos). Jeśli wygra, rozkładamy ją na składniki osobnym testem.

## Próba na sucho (16.11, serwer, tryb testowy, nic nie wyszło)

12 prawdziwych notek z kanału z 13–16.11, model produkcyjny etapu `restack`. Wyniki obok siebie: `robocze/PROBA_NA_SUCHO_RESTACKI_E24.md`.

1. Pierwsza wersja polecenia („45–65 słów w 2–3 akapitach”): 9 tekstów, 8 z nich 81–103 słowa, czyli ponad limit. Prośba o długość
   nie działała. Do wdrożenia się nie nadawała.
2. Wersja „dokładnie trzy akapity po jednym zdaniu, 60 słów; ponad 70 przepada” ze wzorem JSON: 8 restacków z 12, 52–68 słów,
   wszystkie w trzech akapitach i w limicie; 4 odmowy.
3. Wersja ostateczna (po przeglądzie: bez pola `mechanism_named`, z zakazem „I noticed / I saw…”): 6 restacków z 12, 48–68 słów,
   wszystkie w limicie; 6 odmów (lista repozytoriów, lista książek, zbiorówka grantów, niesprawdzalna wiadomość o nazwanej osobie,
   opinia o założycielu, hasłowa notka promocyjna).
4. Uboczne ustalenie o starym wzorze: 4 z 12 jego tekstów miały 41–45 słów i zostały odrzucone przez limit 40. Stary wzór traci
   w ten sposób część restacków. Nie zmieniam tego w trakcie eksperymentu, bo przesunęłoby ramię odniesienia.

Koszt wszystkich prób: 60 wywołań, ok. 0,009 USD (księga `calls`, tryb testowy).

## Reguła decyzji (zapisana przed startem)

Przyrząd: `python agent-v2/eksperymenty.py --rodzaj restack --pole eksperyment:wzor_restacka`. Liczy restacki z numerem i pomiarem
po 72 godzinach, odejmuje tło tygodnia i podaje dla ramienia „on” wobec „off”: `n`, `stosunek` z `przedzial_95`, `zaang_na_100`
(polubienia, odpowiedzi i restacki na 100 wyświetleń) oraz `wykrywalny_efekt`.

1. **Miara główna:** `stosunek` (wyświetlenia po 72 h wobec tła tygodnia, „on” do „off”) z przedziałem 95%.
2. **Miara pomocnicza:** `zaang_na_100` w obu ramionach.
3. **Miara kontrolna:** liczba zrealizowanych restacków w ramionach (`n` „on” wobec `n` „off”). Los jest 50/50 po notkach,
   więc `n_on / n_off` mówi wprost, czy nowy wzór częściej odpada (odmowa modelu, limit słów, podłogi).

Ocena po **55 dojrzałych restackach na ramię** albo 28.12.2026, zależnie co pierwsze. Przy 3–4 restackach dziennie to ok. 5 tygodni.

- **Przyjąć „on” jako zasadę:** `stosunek` co najmniej 1,25, dolna granica przedziału powyżej 1, `zaang_na_100` nie niższe niż w „off”.
- **Odrzucić „on”:** górna granica przedziału poniżej 1 albo `n_on / n_off` poniżej 0,5 (wzór zjada miejsca w dobie).
- **Inaczej:** bez rozstrzygnięcia; nie przedłużać bez nowej decyzji właściciela.

Pierwsza wersja tej reguły mówiła o „ilorazie średnich geometrycznych” i „odsetku restacków z odpowiedzią”. Przyrząd tych dwóch liczb
nie podaje (wykrył to przegląd), więc reguła stoi teraz na tym, co naprawdę liczy.

**Moc, uczciwie.** Przy rozrzucie logarytmu wyświetleń ok. 0,5 i 55 restackach na ramię test wykryje stosunek ok. 1,3 (moc 80%).
Zapisów ten test nie rozstrzygnie: przy dotychczasowym wskaźniku spodziewamy się 0–1 zapisu na ramię. Sprawdzian zbiorczy poza testem:
co najmniej 4 zapisy przypisane restackom ramienia „on” na 200 sztuk wyklucza dotychczasowy wskaźnik (szansa przypadku ok. 7%).

## Co to zmienia w ocenie z 27.11

Zmiana z 13.11 (krótsze notki, restacki 3–4 dziennie) była oceniana m.in. liczbą restacków i przyrostem. Od wdrożenia E24 połowa
restacków ma nowy wzór, więc wynik 27.11 dla restacków opisuje mieszankę. Notek to nie dotyczy.

## Znane ograniczenia

- `co_dziala.py` i `redaktor.py` liczą eksperymenty na notkach, więc pokażą „wzor_restacka (trwa): notek w ramionach 0”, tak jak
  dla `maniera_komentarza`. To nie jest wynik eksperymentu; wynik daje przyrząd z reguły decyzji.
- Kod nie pilnuje liczby akapitów ani zdań. Mierzymy, nie blokujemy.
- Podłoga „zmyślone przeżycie” odrzuca „I noticed / saw / asked / tried”. Polecenie tego zakazuje, ale odrzucenia w „on” mogą być częstsze;
  pokaże to miara kontrolna i log odmów z ramieniem.
- Po 28.12 pamięć głosu `restack.md` dalej pomija stare wpisy ramienia „on”.

## Czego test nie dowodzi przed wdrożeniem

- Że okno „Restack with a note” przyjmuje podział na akapity. `pole.type` wpisuje `\n` jako Enter; w edytorze notek daje to nowy akapit,
  w oknie restacku nikt tego jeszcze nie sprawdził. Dowodem będzie pierwszy żywy restack ramienia „on”: tekst na profilu ma mieć trzy
  akapity, a dziennik numer notki (`id`).
- Że pole `autor` z kanału to autor notki, a nie osoba, która ją podała dalej. Sito w kodzie obejmuje przypadek „X restacked” w nagłówku;
  pierwsze żywe restacki „on” trzeba przeczytać pod tym kątem.
- Że model na produkcji trzyma długość tak jak w próbie. Miarą jest log `pomijam [wzor on]: zdanie ma N slow przy limicie 75`.

## Wycofanie

Usunąć wpis `wzor_restacka` z `config.EKSPERYMENTY` (jedna linia): wszystkie restacki wracają do `restack.md` i limitu 40.

## Dowody

- `tests/test_wzor_restacka.py`: 66 sprawdzeń (polecenie i komunikat w każdym ramieniu, limity z obu stron progu, akapity i kształt
  odpowiedzi modelu, podłogi i zapora w ramieniu „on”, sito imienia autora, okno dat, udział, stałość losu dla notki, niezależność od E13,
  pamięć głosu bez mieszania ramion). Test pracuje na pustym katalogu danych, nie na żywym dzienniku.
- Mutacje `robocze/analiza_fable/mutacje_e24_po_przegladzie.py`: 48 mutantów, wszystkie zabite przy zielonej bazie.
- Przegląd niezależny (16.11): 5 znalezisk potwierdzonych i 5 prawdopodobnych; poprawione w kodzie albo opisane wyżej jako ograniczenia.
- Testy strukturalne `test_bariera_wstrzykniecia.py` (127/0) i `test_martwe_sygnaly.py` (59/8, te same 8 co przed zmianą).
- `tests/test_restack.py`: 23 zdane, 3 oblane, tak samo jak przed zmianą (sekcja 9 o formułce w otwarciu jest czerwona w bazie).

## Wdrożenie

Niewdrożone i nienałożone na repozytorium. To propozycja z analizy 16.11.2026; wdrożeniem zajmuje się kto inny (decyzja właściciela).
Pliki leżą w `robocze/e24_propozycja/`, patrz `CZYTAJ.md`.
