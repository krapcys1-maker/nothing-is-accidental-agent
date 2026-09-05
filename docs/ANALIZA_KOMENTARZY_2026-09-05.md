# Analiza: dlaczego komentarze nie dzialaja i co z tym zrobic

Odpowiedz na `docs/ZLECENIE_ANALIZA_KOMENTARZY.md`. Wykonana 5 wrzesnia 2026
na kopiach produkcji zrobionych tego dnia o 10:11 UTC (baza przez
`sqlite3.backup`, dziennik, dziennik systemowy `nia-agent.service`,
`statystyki.jsonl`, `czytelnicy.jsonl`, `zrodla.jsonl`). Kopie i skrypty
lezą w `robocze/` (poza gitem): `prod-kopia-2026-09-05.db`,
`dziennik_prod-2026-09-05.jsonl`, `nia-log-2026-09-05`, `an_*.py`.

Okno: 22 sierpnia - 5 wrzesnia 2026. Dziennik konczy sie 4 wrzesnia 19:27 UTC
(od tej chwili nic nie wyszlo, bo sufit dobowy 5 USD pekl o 19:31 i trzy
wieczorne przebiegi nie zrobily nic). Baza siega 5 wrzesnia 09:52 UTC.
Wszystkie koszty liczone dla toru `produkcja` (77 wywolan toru `test`,
1,89 USD, odjete).

---

## ETAP 1 - ANALIZA

### 0. Przyrzad, od ktorego zaczynalo zlecenie, klamie o polowe

Zlecenie liczylo reakcje po polu `typ`: `note_like` + `note_reply` = notki,
`comment_like` + `comment_reply` = komentarze. **Typ mowi, w jakim WATKU
stalo nasze zdanie, a nie czy to byla nasza notka czy nasz komentarz.**
Komentarz pod cudza notka ma numer z tej samej przestrzeni `c-` co notka,
wiec polubienie tego komentarza przychodzi jako `note_like`. Ten sam blad
opisuje juz `wzajemnosc.kanal_reakcji` (2 wrzesnia: 17 z 79 reakcji), ale
`alarm.py:882-885` i tabela w zleceniu nadal licza po typie.

Policzone po `czego` (numer NASZEJ tresci) zamiast po typie
(`robocze/an_dziennik6.py`):

| co naszego dotknieto | zdarzen | osobo-reakcji |
|---|---|---|
| komentarz pod cudzym ARTYKULEM (A) | 12 | 12 |
| komentarz pod cudza NOTKA (B) | **25** (12 `note_like` + 13 `note_reply`) | 25 |
| odpowiedz w rozmowie u siebie (C) | 3 | 3 |
| notka BOTA | 71 | 118 |
| notka RECZNA wlasciciela (30 notek) | **38** | 65 |
| bez celu (follow 7, subskrypcja 4, post 4, wlasne 10, restack 1) | 26 | 29 |
| numer, ktorego nie ma ani w dzienniku, ani w statystykach | 37 | 46 |
| razem | 214 | 298 |

Zapytanie: dla kazdego wpisu `rodzaj="skutek"` wez `czego`; jesli jest
w zbiorze `nasz_id` wystawionych komentarzy/odpowiedzi - to komentarz
(klasa po polu `gdzie`: `http` = artykul, `note/` = notka); jesli jest
w `id` notek bota albo w `statystyki.jsonl` z tekstem notki bota - notka bota;
jesli w statystykach bez dopasowania tekstu - notka reczna.

Skutek dla tabeli ze zlecenia:

| | zlecenie | po numerach |
|---|---|---|
| reakcje na komentarze + odpowiedzi (145 szt.) | 19, **0,13/szt** | **40, 0,28/szt** |
| reakcje na notki bota (56 szt.) | 159, **2,84/szt** | **71 pewnych, 1,27/szt** (do 1,93, gdyby wszystkie 37 nieznanych byly notkami bota) |
| notka wobec komentarza | 22x | **4,5-7x** |
| koszt reakcji: komentarz | 0,26 USD | 5,97 / 40 = **0,15 USD** |
| koszt reakcji: notka | 0,041 USD | pisanie 7,57 / 71 = **0,11 USD**; z bankiem i skautem 14,60 / 71 = 0,21 USD |

Komentarz nadal przegrywa z notka, ale nie 22 razy i nie 6 razy drozej za
reakcje - drozej o 0,7-2x, zaleznie od tego, czy do notki liczyc koszt
materialu. To zmienia, ktore propozycje maja sens: „przestac komentowac"
nie jest juz oczywiste; „przestac komentowac TAK, jak dzis" jest.

### 1. Gdzie umieraja komentarze (lejek)

Zrodlo: dziennik systemowy `nia-agent.service`, 56 przebiegow z timera,
22.08 00:02 - 04.09 23:56 (`robocze/an_log2.py`, `an_log3.py`, `an_log4.py`).
UWAGA: log obejmuje tylko przebiegi z timera. Baza ma 119 wywolan `cele`,
log 97 - reszta to reczne przebiegi wlasciciela z 1-4 wrzesnia, ktorych
w logu nie ma. Dziennik i baza sa kompletne, log nie.

**Zrodla celow (co model w ogole widzi):**

| zrodlo | wywolan | oddalo | odrzucone przed modelem |
|---|---|---|---|
| wyszukiwarka `top/search` | 99 | 1980 adresow | 86 za swieze, 365 „bylismy niedawno", 0 naszych |
| kanal czytelnika `/reader/posts` | 48 | 410 postow | 58 za swieze, 35 niedawno |
| kanal notek `/reader/feed` | 40 | 122 notek | 41 za swieze |
| sito platnych hostow (pamiec) | - | - | 44 z 258 w 14 przebiegach |

**Ocena celow (platna, `cele`, DeepSeek flash):** 97 wywolan ocenilo
**1453 posty, przyjelo 423 (29%)**. Powody „nie" (1030, znormalizowane,
`an_log4.py`): promocja 143, nie o AI / bez systemu 124, osobiste/przezycie
119, „nie mam co dodac" 29, jezyk 1, pozostale 548 rozproszone (listy linkow,
cytaty dnia, streszczenia badan, hazard).

**Blok pod ARTYKULAMI (A):**

```
przyjete przez model                 275
  nigdy nie sprobowane               117   petla bierze tylko `plan` celow (cele[:na_teraz])
  sprobowane                         158
    odrzucone: komentarze tylko dla placacych   75   (47% prob; KAZDA zjada miejsce z przydzialu)
    strona wczytana -> comment_on               83
      szkicow modelu                           249   (3 na cel do 4 wrzesnia, teraz 1)
      cisza modelu                               8   (0 celow stracilo wszystkich kandydatow)
      zapora/podloga                             0
      „JUZ SIE TAM ODEZWALISMY" PO napisaniu i sprawdzeniu   15   (18% szkicowanych)
      brak pola komentarza pod postem            7
      wpisane                                   59
        potwierdzone u Substacka                57
        klikniete, nie ma go                     2
```

**Blok pod cudzymi NOTKAMI (B):**

```
przyjete przez model                 148
  sprobowane                          77   (przydzial N//2)
    szkicow modelu                   231
    cisza modelu                      43   (19% - dwa razy czesciej niz pod artykulami)
    zapora/podloga                     3
    cel bez zadnego kandydata          1
    wpisane                           63
      potwierdzone w watku            52
      klikniete, NIE MA w watku       11   (17%; w logu 7x TimeoutError na „Leave a reply")
```

Razem 109 potwierdzonych w logu; dziennik ma 106 udanych `komentarz` od
22 sierpnia (roznica to reczne przebiegi i kilka niezapisanych).

**Cisza:** 51 z 414 szkicow przed zmiana promptu z 2 wrzesnia 19:45 (12,3%),
wszystkie 51 z powodem „aforyzm / nie ma twierdzenia", zero z pieciu
dozwolonych etykiet. **Po zmianie: 0 cisz na 66 szkicow** (tylko przebiegi
z timera). Zmiana promptu na cisze zadzialala; nie ma jeszcze danych dla
jednego kandydata (od 4 wrzesnia 21:43, potem sufit dobowy).

**Sprawdzanie faktow:** 146 „przechodzi", 3 „zastrzezenia, idzie i tak",
8 prob naprawy. Bramka faktow nie zatrzymala ani jednego komentarza (jest
logiem, nie bramka - zgodnie z doktryna).

**Ocena przy zerowym przydziale:** 4 przebiegi (1.09 21:54 i 23:54, 2.09
23:58, 3.09 23:45) mialy `komentarze=0` w planie i mimo to zaplacily za
wyszukiwanie i ocene celow (po 1 wywolaniu `cele`, razem ok. 0,04 USD).
Blok `dyskusje()` ma na poczatku `if not na_teraz["komentarze"]: return`,
blok `komentarze()` nie ma (run.py:1435-1513).

**Czas:** przerwy „rytmu" miedzy dzialaniami w obu blokach: 435 + 441 min =
**14,6 godziny w 14 dni**, czyli ok. godziny czasu przebiegu dziennie na
czekanie miedzy komentarzami.

### 2. Czy komentarz trafia tam, gdzie ktos jest

Pola `reakcje_celu` i `komentarzy_przed` z dziennika (zapisywane przy 119
ze 119 komentarzy od 22 sierpnia), reakcje po numerach (`an_dziennik6.py`,
klasy A+B, n = 25 z reakcja / 98 bez):

| cecha celu w chwili komentowania | z reakcja (mediana) | bez reakcji (mediana) |
|---|---|---|
| reakcji pod cudzym wpisem | **12** | **125** |
| komentarzy przed nami | **1** | **8** |

| komentarzy przed nami | wystawione | z reakcja |
|---|---|---|
| 0 | 28 | 10 (36%) |
| 1-5 | 25 | 7 (28%) |
| 6-25 | 70 | 8 (11%) |

| reakcji pod cudzym wpisem | wystawione | z reakcja |
|---|---|---|
| 1-9 | 24 | 10 (42%) |
| 10-99 | 28 | 7 (25%) |
| 100+ | 66 | 6 (9%) |

Czyli odwrotnie niz zakladalo sortowanie `wartosc_celu` („zywa publicznosc,
malo komentarzy"): reaguje sie tam, gdzie publicznosci prawie nie ma.
Powod widac w pytaniu 5: reaguje autor, a autor duzego wpisu nie odpowiada
na dziewiaty komentarz.

**Czy ktokolwiek poza autorem to widzi.** Karty zasiegu Substacka
(`statystyki.jsonl`, `an_stat2.py`): 113 komentarzy z numerem, 78 ma jakikolwiek
pomiar, **17 ma karte zasiegu**. Mediana wyswietlen 0, maksimum 8. Z 54
wyswietlen lacznie **52 to „Permalinks"** (ktos otworzyl link do komentarza,
czyli powiadomienie), **0 z Feed, 0 z Notes, 0 z Search**. Odbiorcy: 47
„Unconnected", 2 subskrybentow. Dla porownania 52 notki bota: mediana 25
wyswietlen, Feed 495 + Other 783, odbiorcy 456 Unconnected / 64 subskrybentow
/ 34 obserwujacych.

Zastrzezenie: Substack nie liczy czytania komentarza W WATKU pod postem;
liczy tylko to, co nazywa wyswietleniem. Wiec „zero" znaczy „nikt nie otworzyl
komentarza jako osobnej pozycji", nie „nikt nie przeczytal".

### 3. Kiedy komentujemy

`wiek_celu_min` z dziennika (`an_dziennik2.py`, `an_dziennik6.py`):

| | mediana wieku cudzego wpisu w chwili komentarza |
|---|---|
| komentarze pod artykulami (A, n=68) | **98 dni** |
| komentarze pod notkami (B, n=55) | **3,4 dnia** (42% mlodszych niz doba, 31% starszych niz miesiac) |
| z reakcja (A+B) | **3,4 dnia** |
| bez reakcji (A+B) | **65 dni** |

| wiek celu | wystawione | z reakcja |
|---|---|---|
| < 3 h | 6 | 3 (50%) |
| 3-24 h | 18 | 6 (33%) |
| 1-7 dni | 15 | 5 (33%) |
| 7-30 dni | 16 | 3 (19%) |
| > 30 dni | **68** | 8 (12%) |

**55% komentarzy idzie pod wpisy starsze niz miesiac**, bo `top/search`
oddaje wpisy popularne, nie swieze. Wg hasla (A, `an_dziennik5.py`): „large
language models" 5 komentarzy, 0 reakcji, mediana wieku 285 dni; „AI
evaluation" 364 dni; „AI agents" 469 dni; „AI and work" 513 dni. Kanal
notek (`kanal`): 33 komentarze, 15 z reakcja (45%). Wyszukiwarka: 87, 10
(11%). Kanal czytelnika: 3, 0.

Wczesniej = lepiej, ale nie dlatego, ze czyta publicznosc: dlatego, ze
autor jeszcze patrzy.

### 4. Ktory komentarz dostal reakcje

25 komentarzy A+B z reakcja wobec 98 bez (pelna lista tekstow w zalaczniku
na koncu). Cechy TEKSTU (`an_dziennik6.py`):

| cecha tekstu | z reakcja | bez |
|---|---|---|
| zawiera pytanie „?" | 8 z 26 (31%) | 17 z 97 (18%) |
| 51+ slow | 6 z 17 (35%) | |
| 31-50 slow | 9 z 40 (22%) | |
| 16-30 slow | 8 z 49 (16%) | |
| <= 15 slow | 2 z 17 (12%) | |
| zawiera liczbe | 7 z 43 (16%) | 18 z 80 bez liczby (22%) |
| you / your / I / we | 9 z 40 (22%) | 16 z 83 (19%) |

Wg przydzielonej postawy (zapisywana od 23 sierpnia dla A, od 2 wrzesnia
dla B):

| postawa | wystawione | z reakcja |
|---|---|---|
| ROZSZERZENIE | 11 | 5 (45%) |
| PYTANIE | 15 | 6 (40%) |
| CIEKAWOSC | 20 | 3 (15%) |
| KONKRET | 12 | 1 (8%) |
| MECHANIZM | 15 | 1 (7%) |
| SPRZECIW / KOREKTA / ZGODA | 7 | 0 |

Co maja wspolnego teksty z reakcja, po przeczytaniu wszystkich 25: chwytaja
JEDNO zdanie autora („Your staircase example", „That phrase 'on schedule'
caught me", „Your FAQ treats...") i zostawiaja mu cos do odpowiedzenia -
pytanie albo przeniesienie jego mechanizmu w inne miejsce. Teksty bez
reakcji to w wiekszosci „wiersz z tabeli" (data, kwota, nazwa dokumentu,
zero czlowieka w zdaniu) albo mechanizm wylozony do konca, na ktory nie da
sie nic odpowiedziec. Dokladnie ta wada, ktora prompt nazywa w sekcji
„Register". Wyjatek potwierdzajacy: „Stargate announced $500 billion..." -
zdanie, ktore prompt cytuje jako zly przyklad - dostalo jedno polubienie.

Liczby i konkrety nie pomagaja (16% wobec 22%). Dlugosc pomaga. Pytanie
pomaga. Postawy KONKRET i MECHANIZM, razem 27 komentarzy, daly 2 reakcje.

Przy n = 25 to sa kierunki, nie dowody. Roznica ROZSZERZENIE/PYTANIE wobec
KONKRET/MECHANIZM (11 z 26 wobec 2 z 27) jest jednak za duza, zeby byla
szumem przy tych rozmiarach.

### 5. Kto reaguje

Od 22 sierpnia: **67 roznych osob, 298 osobo-reakcji** (zlecenie liczylo
30 osob i 214 zdarzen - liczylo wpisy, nie nadawcow; `an_dziennik3.py`).
Chaos Engine: **101 z 298 (34%)**, LoRosha 36, Claude Opus 4.5 20, Genie 16,
Sherif Saad 10. Cala reszta po 1-6.

**Na komentarze reaguje AUTOR wpisu, pod ktorym stoimy:**

| klasa | zdarzen | od autora celu |
|---|---|---|
| A (artykuly) | 12 | 9 (Vince Asuncion, Tim Seyrek, Hedley Rees x2, Ryan Puzycki, David Oks, David Scott, Natalie Wexler, Vedaansh Bhargava); pozostale: Chris Zeoli, Adelaide Dupont |
| B (notki) | 25 | **24** (Genie 8, Daniel Pope 2, Augmenting_decision 2, Thor 2, The Lonely Road 2, LonnieSly 2, po 1: Sonia Ketkar, Nehansh Jain, The AI Compass, Lakshye, Chaos Engine, Jane Friedman); poza autorem: Tully 1 |

Czyli **33 z 40 reakcji na komentarze to autor, ktory dostal powiadomienie**.
Komentarz nie buduje publicznosci; buduje jeden kontakt z jednym autorem.
21 z 67 reagujacych to ludzie, pod ktorymi komentowalismy - ale wiekszosc
duzych reagujacych (Chaos Engine od 15 sierpnia, LoRosha, Claude Opus 4.5)
reagowala na notki zanim albo bez tego, zebysmy u nich komentowali.

**Czy z komentarza wynika pozyskanie** (`czytelnicy.jsonl`, 39 zrzutow od
31 sierpnia, `an_dziennik7.py`): 16 obserwujacych, 10 subskrybentow.
Sekwencja da sie udowodnic dla dwoch:

- **Thor**: nasz komentarz pod jego notka 1.09 12:46 -> jego polubienie
  i odpowiedz 13:43 -> obserwowanie 14:00.
- **Vedaansh Bhargava**: komentarz pod jego artykulem 2.09 23:12 -> jego
  odpowiedz 23:36 -> obserwuje nas w zrzucie z 23:58.

Prawdopodobne, nieudowodnione (obserwujacy od pierwszego zrzutu 31.08,
komentarz wczesniej): Adebamiwa Olugbenga Michael (komentarz 27.08),
The Lonely Road: Founder (komentarz 29.08, ale reagowal na notki od 16.08).
**Zero z 10 subskrybentow** ma komentarz przed subskrypcja. Chaos Engine
reagowal od 15 sierpnia, pierwszy nasz komentarz u niego 29 sierpnia.

Zrodla Substacka (`zrodla.jsonl`, 30 dni): zapisy darmowe „substack notes"
6, „substack.com" 1. Komentarz pod cudza notka jest w „notes", wiec to
przypisanie nie odroznia naszej notki od naszego komentarza pod cudza.

### 6. Ile kosztuje jeden komentarz naprawde

Baza, tor produkcja, 22.08-05.09 (`an_db2.py`). `factcheck` nie ma kanalu
przed 2 wrzesnia 16:48, wiec przypisany przez sasiedztwo: sprawdzenie tuz po
`comment`/`naprawa_komentarza` w tym samym przebiegu liczy sie do komentarza.

| etap | wywolan | USD | na 1 WYSTAWIONY komentarz A+B (123) |
|---|---|---|---|
| `comment` (szkic) | 558 | 2,774 | **0,0226** (4,5 szkicu na wystawiony) |
| `cele` | 119 | 1,228 | 0,0100 (11,8 ocenionych postow na wystawiony) |
| `factcheck` | 43 + 139 | 0,330 + 0,900 | 0,0100 |
| `naprawa_komentarza` | 5 | 0,037 | 0,0003 |
| razem komentarz | | **5,269** | **0,043 USD** |
| `reply` + `wybor` (odpowiedzi C, 22 szt.) | 169 + 13 | 0,566 + 0,131 | 0,032 |
| **segment razem** | | **5,966** | **17,5% rachunku (34,06)** |

Od 2 wrzesnia 16:48 (znacznik `akcja`, bez szacowania): `komentarz@artykul`
0,975 USD / 21 wystawionych = **0,046**; `komentarz@notka` 0,491 / 10 =
**0,049**; `odpowiedz` 0,176 / 7 = 0,025.

**Najdrozszy etap na wystawiony komentarz to szkic (53%)** - nie dlatego,
ze jedno wywolanie jest drogie (0,005 USD), tylko dlatego, ze na jeden
wystawiony przypada 4,5 szkicu: trzech kandydatow do 4 wrzesnia, a do tego
cele, ktore umieraja PO napisaniu (15 „juz sie odezwalismy", 7 bez pola,
13 niepotwierdzonych, cisze).

Dla porownania notka bota: pisanie + sprawdzenie 7,57 USD / 56 = 0,135;
z bankiem, skautem i parowaniem 14,60 / 56 = 0,26 USD. Komentarz kosztuje
1/3 do 1/6 notki i przynosi 1/5 do 1/7 jej reakcji.

### 7. Ktore reguly `komentarz.md` ktos sprawdza

Etykiety: **KOD** = sprawdza kod na wyjsciu modelu; **TEST** = test sprawdza
tylko obecnosc frazy w pliku; **PROSBA** = nic nie pilnuje. Obok: co widac
na 145 wystawionych tekstach (`an_dziennik4.py`).

| regula w prompcie | etykieta | co mierzy |
|---|---|---|
| „I have nothing to add" nie jest dostepne; cisza tylko w 5 przypadkach | KOD tylko ETYKIETUJE (`POWODY_CISZY`, „POZA LISTA"), nie wymusza; TEST `test_cel_i_tik_w_prompcie` | 51/480 cisz przed 2.09, 0/66 po |
| przy ciszy przepisz 10 pierwszych slow (`pierwsze_slowa`) | KOD wypisuje „ZAPRZECZONE WLASNYM CYTATEM", **nie ponawia**; przy 1 kandydacie cel przepada | brak danych po 4.09 |
| `wrong_language` | PROSBA (kod nie sprawdza jezyka ani celu, ani komentarza) | 0 wykryc |
| 2-4 zdania, jedna mysl | PROSBA | 1 zdanie: 26, 2-4: 115, 5+: 4 |
| postawa przydzielona (`{postawa}`) | KOD losuje; TEST `test_komentarze` sprawdza pole w pliku | rozklad w logu zgodny z wagami |
| nie zmyslaj faktow | KOD `zweryfikuj` - **LOG, nie bramka**; `napraw_obalone` przepisuje refuted/outdated | 146 przeszlo, 3 z zastrzezeniem poszly, 8 napraw |
| nie zmyslaj przezycia | KOD `_podloga_z_pamieci` (od 1.09); TEST `test_podlogi_z_pamieci` | 0 trafien w oknie |
| nie linkuj do siebie, nie wspominaj pisma | KOD `bez_wstrzykniecia` (kazdy URL, kazde @) | 0 trafien |
| nie moralizuj, nie chwal autora | PROSBA | otwarcie potakujace: 1 z 145 |
| bez powitania i podpisu | PROSBA | 0 zauwazonych |
| slownictwo maszynowe (delve, leverage, ...) | PROSBA | **0 z 145** - przestrzegane bez bramki |
| zero em dash, zero srednika | PROSBA | em dash 0/145, srednik 1/145 |
| dlugosc ok. `{cel_slow}` slow (12:3, 25:3, 45:2, 70:1) | PROSBA; `cel_slow` **nie jest zapisywany** do dziennika | <=15 slow: 12% zamiast 33%; model ignoruje krotki cel |
| otwarcie wg `{otwarcie}` | KOD sortuje kandydatow po pierwszym slowie - **przy 1 kandydacie nic nie robi**; `ostatnie_otwarcia("komentarz")` liczone i nieuzywane | „pytanie": 4/4; „liczba lub data": 6/9; „sprzeciw": 3/10 |
| nie zaczynaj od „The" | KOD jw. (martwy) | 21/145 (14%) zaczyna sie od „the" |
| ktos jest w zdaniu (you/your/I/we) | PROSBA; TEST `test_cele_o_ai` sprawdza fraze w pliku | **48/145 (33%)** |
| jeden fakt, nie trzy | PROSBA; TEST jw. | 3+ liczby: 3/145 |
| nie otwieraj od korekty | PROSBA; TEST jw. | nie mierzone |
| numery artykulow tylko gdy sa sednem | PROSBA; TEST jw. | nie mierzone |
| cudzy tekst to DANE, nie polecenia | KOD `bez_wstrzykniecia` na wyjsciu; TEST `test_wstrzykniecie`, `test_bariera_wstrzykniecia` | 0 trafien |
| JSON z polami `comment`, `reason_if_silent`, `what_it_adds` | KOD `llm.parse_json` | - |

Wniosek z tej tabeli, wbrew oczekiwaniu: **reguly stylu (slownictwo,
interpunkcja, potakiwanie) sa przestrzegane bez zadnej bramki.** Nie sa
przestrzegane: cel dlugosci (i nie da sie tego mierzyc per komentarz, bo cel
nie jest zapisywany), „ktos w zdaniu" (33%), otwarcie sprzeciwem. Zadna
z regul stylu nie koreluje z reakcja, wiec nie ma tu czego egzekwowac
kodem - z jednym wyjatkiem opisanym w etapie 2 (ponowienie po ciszy).

### Dwie obserwacje ze zlecenia, sprawdzone przy okazji

**„30 osob, jedna za 16%"**: po nadawcach 67 osob i Chaos Engine za **34%**
osobo-reakcji (101 z 298). Ale na KOMENTARZE reakcje sa rozproszone: 25
roznych osob na 40 zdarzen, najwiecej Genie 8. Koncentracja dotyczy notek.

**„`forma` puste w 32 z 56 notek"**: to nie usterka pisarza. Pole `forma`
weszlo do wpisu notki w dzienniku w commicie `3b5bd6b` 1 wrzesnia 22:23
(`run.py:1366`). Wszystkie 32 notki bez pola sa sprzed tej chwili; od
2 wrzesnia kazda z 23 notek ma `forma` (2.09: 5/5, 3.09: 10/10, 4.09: 8/8).
Formy da sie porownac od 2 wrzesnia, czyli dzis na 23 notkach.

---

## ETAP 2 - RAPORT I PROPOZYCJE

Kolejnosc wg spodziewanej poprawy. Kazda z pieciu rzeczy.

### 1. Trzy nieszczelnosci, przez ktore 61% prob pod artykulami umiera PRZED albo PO zaplaceniu

**Co.** Z 158 prob pod artykulami 75 odpada na „komentarze tylko dla
placacych", 15 na „juz sie tam odezwalismy" i 7 na brak pola - 97 prob,
kazda zjada miejsce z przydzialu, a 15 z nich odkrywa sie po napisaniu
i sprawdzeniu; do tego 4 przebiegi placily za ocene przy przydziale 0.

**Gdzie.** `run.py:1573-1580` (`for cel in cele[:na_teraz["komentarze"]]`
z `continue` po `mozna_komentowac`); `browser.wystaw_komentarz` linia
z `juz_sie_odezwalismy` (po `comment_on`, nie przed); `run.py:1435`
(`komentarze()` bez `if not na_teraz["komentarze"]: return`, ktore ma
`dyskusje()` w 1690).

**Ile to kosztuje.** Miejsca z przydzialu: 57 wystawionych z 158 prob
(36%). Pieniadze: 15 x (3 szkice x 0,005 + factcheck 0,011) = 0,39 USD
w 14 dni + 4 x 0,01 za ocene przy zerze; przy 1 kandydacie mniej. Wzor:
proby_martwe x (szkice x 0,005 + 0,011).

**Darmowe sprawdzenie.**
```
grep -c "komentarze tylko dla placacych" robocze/nia-log-2026-09-05      # dzis 75
grep -c "JUZ SIE TAM ODEZWALISMY" robocze/nia-log-2026-09-05             # dzis 15
```
Zdrowa odpowiedz po poprawce: „placacych" liczone PRZED ocena (w bloku
sita, jak `hosty_tylko_dla_placacych`), „JUZ SIE" = 0 w logu, a udzial
wystawionych w probach > 70%.

**Najmniejsza poprawka i kontrdowod.** (a) Przed petla odsiac adresy, ktore
juz sa w dzienniku jako `gdzie` udanego komentarza (plik na dysku, zero
kosztu); (b) `mozna_komentowac` dla WSZYSTKICH przyjetych celow przed petla,
a petla idzie po tych, ktore przeszly, az do `plan` WYSTAWIONYCH; (c) `return`
przy zerowym przydziale. Mierzyc: wystawione / proby na przebieg i USD na
wystawiony komentarz A (dzis 0,046). **Cofnac, jesli po 3 dobach udzial
niepotwierdzonych („SUBSTACK GO NIE POKAZUJE") wzrosnie powyzej 10%** -
znaczyloby, ze sprawdzenie uprawnien przepuszcza hosty, ktore odrzucalo
sito, i ze przenieslismy strate z etapu tanszego na drozszy.

### 2. Przeniesc przydzial z wyszukiwarki (stare artykuly duzych autorow) na swieze, male wpisy, gdzie autor jeszcze patrzy

**Co.** Komentarze z wyszukiwarki: 87 wystawionych, 10 z reakcja (11%),
mediana wieku celu 2 miesiace. Z kanalu notek: 33, 15 (45%). Cel z 0-5
komentarzami przed nami: 32% z reakcja; z 6-25: 11%. Cel z 1-9 reakcjami:
42%; ze 100+: 9%. Koszt na sztuke ten sam (0,046 wobec 0,049).

**Gdzie.** `run.py:1724` (`cele[: max(1, na_teraz["komentarze"] // 2)]` -
blok notek dostaje polowe); `kanal.wartosc_celu` (kanal.py:70, sortuje
„glosna publicznosc" na gore); `config.KOMFORTOWO_KOMENTARZY = 25`
(config.py:2446, prog tloku 25 - dane mowia 5); `config.HASLA_SZUKANIA`
i `top/search` bez filtra daty (kanal.py:246).

**Ile to kosztuje.** Dzis A+B daja 0,30 zdarzenia na sztuke (37 na 123).
Gdyby 68 komentarzy A z wyszukiwarki poszlo z ta sama skutecznoscia co
B (0,45): +18 zdarzen w 14 dni przy tym samym rachunku. Wzor: 68 x (0,45 -
0,18). Jesli B nasyci sie przy podwojeniu (te same kilka osob), zysk
mniejszy - patrz kontrdowod.

**Darmowe sprawdzenie.** `python -X utf8 robocze/an_dziennik6.py` sekcja
„skad" i „komentarzy_przed". Zdrowa odpowiedz: `kanal` >= 35% z reakcja,
`szukanie` <= 15%, i tak samo po zmianie.

**Najmniejsza poprawka i kontrdowod.** `KOMFORTOWO_KOMENTARZY` z 25 na 5;
przydzial notek z N//2 na N, artykulow z N na N//2; w `szukaj_nowych`
odrzucac cel starszy niz 14 dni (pole `data` juz jest). Mierzyc przez 7 dni:
udzial B z reakcja i liczbe ROZNYCH autorow reagujacych. **Cofnac, jesli
udzial B z reakcja spadnie ponizej 20% albo jesli wiecej niz polowa reakcji
B przyjdzie od trzech osob** - znaczyloby, ze pula swiezych notek jest za
mala i doszlismy do tych samych trzech autorow (Genie ma juz 8 z 25).
Zasiegu to nie poprawi (mediana 0 wyswietlen zostanie) - poprawi liczbe
autorow, ktorzy wiedza, ze istniejemy. Tyle komentarz potrafi.

### 3. Wagi postaw: PYTANIE i ROZSZERZENIE w gore, KONKRET i MECHANIZM w dol

**Co.** PYTANIE 6/15 i ROZSZERZENIE 5/11 z reakcja (42% razem); KONKRET
1/12, MECHANIZM 1/15, SPRZECIW/KOREKTA/ZGODA 0/7 (11% razem z CIEKAWOSC).
Komentarz-wiersz-z-tabeli nie dostaje nic, komentarz zostawiajacy autorowi
pytanie dostaje odpowiedz.

**Gdzie.** `config.POSTAWY_KOMENTARZA` (config.py:1325): CIEKAWOSC 7,
MECHANIZM 6, PYTANIE 6, KONKRET 5, ROZSZERZENIE 4, SPRZECIW 2, KOREKTA 1,
ZGODA 1.

**Ile to kosztuje.** Zero USD. Jesli polowa komentarzy z grupy 11% przejdzie
do grupy 42%: z ok. 20% do ok. 30% komentarzy z reakcja. Wzor: 0,5 x 54 x
(0,42 - 0,11) = +8 komentarzy z reakcja na 14 dni.

**Darmowe sprawdzenie.** `an_dziennik6.py` sekcja „postawa". Zdrowa
odpowiedz: PYTANIE + ROZSZERZENIE >= 30% z reakcja przy n >= 30.

**Najmniejsza poprawka i kontrdowod.** Wagi: PYTANIE 8, ROZSZERZENIE 6,
CIEKAWOSC 6, MECHANIZM 4, KONKRET 2, reszta bez zmian. To NIE jest „pytanie
na koniec dla zaangazowania" - prompt to zakazuje i ma zostac; PYTANIE to
pytanie, na ktore chcemy odpowiedzi. **Cofnac, jesli po 60 komentarzach
PYTANIE + ROZSZERZENIE beda mialy ponizej 25% z reakcja** (dzisiejsze 42%
bylo szumem na n = 26) **albo jesli udzial reakcji „od autora" spadnie
ponizej 60%** (pytania zaczely irytowac zamiast zapraszac).

### 4. Cisza przy jednym kandydacie: ponowic raz, gdy model sam sobie zaprzeczyl

**Co.** Od 4 wrzesnia jest jeden kandydat. Jesli oddaje `no_text` i zarazem
`pierwsze_slowa`, kod wypisuje „ZAPRZECZONE WLASNYM CYTATEM" i cel przepada.
Przed zmiana promptu cisza brala 10,6% szkicow; po zmianie 0 na 66, ale
przy trzech kandydatach. Dowodu dla jednego nie ma.

**Gdzie.** `stages.comment_on` (stages.py:5055-5075).

**Ile to kosztuje.** Jedno dodatkowe wywolanie `comment` (0,005 USD) tylko
w tym przypadku. Odzysk: kazdy cel to juz zaplacona ocena, strona i miejsce
z przydzialu (ok. 0,02 USD + slot).

**Darmowe sprawdzenie.**
```
grep -c "ZAPRZECZONE WLASNYM CYTATEM" robocze/nia-log-2026-09-05   # dzis 0 - brak danych
grep -c "CEL BEZ KOMENTARZA" robocze/nia-log-2026-09-05            # dzis 1
```
Zdrowa odpowiedz po tygodniu na jednym kandydacie: „CEL BEZ KOMENTARZA"
<= 1 na 20 celow.

**Najmniejsza poprawka i kontrdowod.** Gdy `not text and _slowa`: jedno
ponowienie z tym samym promptem. Regula w KODZIE, nie w prompcie (prosba
juz jest i to ona wypisuje cytat). **Cofnac, jesli ponowienie tez milczy
w ponad polowie przypadkow** - wtedy problem jest w tresci podanej modelowi
(jak 4 wrzesnia: harness podawal wpis z feedu zamiast strony), nie w modelu.

### 5. 17% komentarzy pod notkami klika i nie wchodzi

**Co.** 11 z 63 wpisanych pod cudzymi notkami „KLIKNIETE, ALE ODPOWIEDZI
NIE MA W WATKU"; w logu 7x `TimeoutError` na lokatorze „Leave a reply".
Pod artykulami 2 z 59.

**Gdzie.** `browser.wystaw_odpowiedz` (browser.py:3990) i
`potwierdz_odpowiedz` (3954).

**Ile to kosztuje.** 11 x (szkice + factcheck ok. 0,026) = 0,29 USD i 11
miejsc z przydzialu w 14 dni - czyli co szosty komentarz B.

**Darmowe sprawdzenie.** Wziac 3 z 11 wpisow `komentarz`/`odpowiedz`
z `udane=false` i `gdzie=note/c-...` z dziennika i otworzyc watek w
przegladarce. Zdrowa odpowiedz: komentarza tam NIE MA (porazka prawdziwa).
Jesli JEST - klamie `potwierdz_odpowiedz`, nie przycisk.

**Najmniejsza poprawka i kontrdowod.** Zalezy od sprawdzenia wyzej; bez
niego nie proponuje kodu. **Cofnac kazda poprawke, po ktorej udzial
niepotwierdzonych nie spadnie ponizej 8% w 30 wpisach.**

### 6. Rozwiazanie odejmujace: przestac komentowac pod artykulami z wyszukiwarki, zostawic notki

**Co.** Komentarze A z wyszukiwarki: 68 wystawionych, 12 reakcji (9 od
autorow), mediana 0 wyswietlen, 1 obserwujacy (Vedaansh). Koszt ok.
68 x 0,043 = 2,9 USD z 5,97 segmentu plus polowa z 14,6 h przerw.

**Gdzie.** `run.py:1435` blok `komentarze()`; `config.KOMENTARZE_DZIENNIE`.

**Ile to kosztuje / co tracimy.** Tracimy 12 zdarzen na 14 dni, 1 obserwujacego
i kontakt z 9 autorami duzych publikacji (Puzycki, Rees, Wexler...). Za 2,9 USD
kupimy 11 notek Opus albo 22 notki `note_tani`, czyli 14-28 reakcji notkowych
od CZYTELNIKOW, nie autorow. „Przestac komentowac w ogole" (A + B + C)
oszczedza 5,97 USD (17,5%) i traci 40 zdarzen, 2 udowodnionych obserwujacych
z 16 i 0 subskrybentow z 10. Liczby niosa ciecie A, nie ciecie wszystkiego:
B jest najtanszym kontaktem z autorem, jaki to konto ma (0,049 USD na
komentarz, 29% odpowiada).

**Darmowe sprawdzenie.** `an_dziennik6.py` sekcja „klasa" i „skad".
Zdrowa odpowiedz dla utrzymania A: > 20% z reakcja albo > 1 obserwujacy
na 14 dni.

**Najmniejsza poprawka i kontrdowod.** `KOMENTARZE_DZIENNIE` bez zmian,
ale przydzial A = 0 i B = N (albo propozycja 2 jako wersja lagodniejsza).
**Cofnac, jesli w 14 dniach po zmianie przybedzie mniej niz 10
obserwujacych** (dzis: 7 -> 16 miedzy 31.08 a 4.09, czyli +9 w 5 dni)
- znaczyloby, ze A przynosilo obserwujacych, ktorych nie umiemy przypisac.

### 7. Cel dlugosci: przestac prosic o 12 slow i zaczac zapisywac, o co prosimy

**Co.** Prompt losuje cel 12 slow z waga 3/9; model daje <=15 slow w 12%
przypadkow, a te dostaja najmniej reakcji (12% wobec 35% dla 51+). Cel nie
jest zapisywany, wiec nie da sie policzyc, czy model go w ogole slucha.

**Gdzie.** `config.DLUGOSCI_WYPOWIEDZI` (config.py:1297); `run.py:1614-1617`
(kontekst do dziennika ma `otwarcie` i `postawa`, nie ma `cel_slow`).

**Ile to kosztuje.** Zero. Spodziewana poprawa mala i posrednia.

**Darmowe sprawdzenie.** `an_dziennik4.py` linia „slow: <=15 ...". Zdrowa
odpowiedz po zapisaniu celu: mediana |slowa - cel| / cel < 0,5; jesli > 1,
stala jest ozdoba.

**Najmniejsza poprawka i kontrdowod.** Wagi 12:1, 25:3, 45:3, 70:2 i pole
`cel_slow` w kontekscie dziennika. **Cofnac (usunac stala), jesli po 60
komentarzach korelacja celu z dlugoscia bedzie ponizej 0,3** - wtedy prompt
i tak jej nie czyta, a rozklad dlugosci ustawia model.

### 8. Naprawic przyrzad: liczyc reakcje po numerze, nie po typie - w alarmie i w kazdym nastepnym zleceniu

**Co.** `alarm.py` i tabela zlecenia dziela reakcje po `typ`; prawidlowa
metoda istnieje w `wzajemnosc.kanal_reakcji` od 2 wrzesnia i nikt jej nie
uzywa poza tym modulem. 37 z 214 zdarzen ma numer, ktorego nie ma nigdzie
(notki bez `id` w dzienniku: 4 z 56 w oknie, wiecej wczesniej; reczne notki
spoza okna statystyk).

**Gdzie.** `alarm.py:882-885`; `browser.dopisz_skutki` (2051) - zapisuje
`czego`, nie zapisuje, CO to bylo; `browser.wystaw_notke` - `id` notki
trafia do dziennika nie zawsze.

**Ile to kosztuje.** Zero USD; kosztuje decyzje: to zlecenie stalo na „22x
i 6x drozej", prawda to „4,5-7x i 0,7-2x drozej".

**Darmowe sprawdzenie.** `python -X utf8 robocze/an_dziennik6.py` - zdrowa
odpowiedz: „nieznany id" ponizej 10% zdarzen, suma po klasach = suma zdarzen.

**Najmniejsza poprawka i kontrdowod.** W `dopisz_skutki` dopisac pole
`nasza_pozycja` z `wzajemnosc.kanal_reakcji` w chwili zapisu; w alarmie
liczyc po nim. **Cofnac (i szukac bledu w zapisie `id`), jesli po tygodniu
udzial „nieznany" nie spadnie ponizej 10%.**

### Czego NIE proponuje, choc zlecenie o to pyta

Bramek na styl (slownictwo, em dash, „ktos w zdaniu"): slownictwo i
interpunkcja sa przestrzegane w 145/145 bez bramki, a „ktos w zdaniu" (33%)
nie koreluje z reakcja (22% wobec 19%). Bramka kosztowalaby komentarze
i nie kupila nic mierzalnego.

---

## CZEGO NIE DALO SIE USTALIC I CO TRZEBA ZACZAC ZAPISYWAC

1. **Czy ktokolwiek czyta komentarz w watku.** Substack liczy tylko otwarcia
   linku; karte zasiegu ma 17 ze 113 komentarzy. Nie da sie zmierzyc naszym
   przyrzadem ani cudzym. Jedyna miara, jaka zostaje, to odpowiedz autora
   i pozyskanie - i tak trzeba liczyc skutecznosc komentarza.
2. **Do czego nalezy 37 z 214 reakcji.** Zaczac zapisywac `id` KAZDEJ
   wystawionej notki (4 z 56 w oknie go nie maja) i trzymac pelna liste
   numerow naszych tresci (dzis: dziennik + `statystyki.jsonl` z oknem
   82 notek, z ktorego stare wypadaja). `wystawione_notki.json` na serwerze
   jest pusty („wyliczone z dziennik.jsonl, mozna skasowac").
3. **Czy model slucha celu dlugosci.** Zapisywac `cel_slow` w kontekscie
   komentarza (jak `otwarcie` i `postawa`).
4. **Kto jest autorem celu, jako uchwyt.** `komu` przy komentarzach: 12 ze
   119 (od 3 wrzesnia); dla notek `publikacja` to nazwa autora, dla artykulow
   nazwa publikacji. Bez uchwytu autora „reakcja od autora" liczy sie po
   dopasowaniu nazw, ktore trafia w 33 z 40, a reszty nie umie rozstrzygnac.
   Zapisywac `komu` zawsze, a w `dopisz_skutki` dopisac `od_autora` (uchwyt
   nadawcy == uchwyt celu).
5. **Czy wyszukiwarka umie oddac swieze wpisy.** `top/search` oddaje wpisy
   z mediana wieku 2 miesiace; nie sprawdzalem parametrow API, bo wymaga to
   zalogowanej sesji na serwerze. Darmowy test: jedno wywolanie
   `/api/v1/top/search?query=...` z roznymi parametrami sortowania,
   read-only, bez modelu.
6. **Lejek zyje tylko w stdout.** Cisza, „platne", „juz sie odezwalismy",
   „brak pola" sa w dzienniku systemowym, ktory nie obejmuje recznych
   przebiegow (baza 119 wywolan `cele`, log 97). Zapisywac do
   `dziennik.jsonl` wpis `rodzaj="cel"` z wynikiem (platne / juz_bylismy /
   cisza / zapora / niepotwierdzony / wystawiony) - wtedy lejek liczy sie
   z jednego pliku, tak jak wszystko inne.
7. **Skutecznosc przy jednym kandydacie.** `COMMENT_CANDIDATES = 1` weszlo
   4 wrzesnia 21:43; od tej pory zaden przebieg nie napisal komentarza
   (sufit dobowy). Pierwsza doba na jednym kandydacie dopiero sie zdarzy.
8. **Czy komentarze przynosza zapisy.** Zrodla Substacka („substack notes"
   6 zapisow) nie odrozniaja naszej notki od naszego komentarza pod cudza.
   Jedyna droga to sekwencja czasowa w `czytelnicy.jsonl` (zrzuty od 31.08);
   zrzut co przebieg wystarcza, ale trzeba go zestawiac z dziennikiem -
   `an_dziennik7.py` robi to recznie.

---

## ZALACZNIK - teksty

### 25 komentarzy A+B z reakcja (kto zareagowal w nawiasie)

Pod artykulami (A):

1. [25.08, Vince Asuncion, odp.+polub.] One midnight message sustains the waiting. Intermittent reward keeps hope alive.
2. [26.08, Tim Seyrek, polub.] The piece is right that the reaction is automatic and that ornament is not just decoration but a fractal cue. What it skips is the same mechanism in post-war graphic design, where flat corporate identities and Helvetica stripped wordmarks of the same self-similar detail...
3. [27.08, Hedley Rees, odp.+polub.] Virtual inspections worse than useless? AI auditing is often virtual. What would a physical inspection even mean for a model?
4. [28.08, Ryan Puzycki, odp.] The post makes nuisance law the clean line between legitimate coercion and mere preference. But demonstrable harm is itself a judgment call... Who sets that threshold, and how is that body less discretionary than a zoning board?
5. [31.08, David Scott, polub.] If a screening model is trained on a referral-heavy firm's past hires, it will keep surfacing those referrals. Before trusting that compression, what do you audit first?
6. [31.08, David Oks, polub.] Same discipline now governs container shipping after Hanjin, where the three alliances withhold capacity the way Samsung and Micron withhold wafers...
7. [1.09, Chris Zeoli, polub.] 1846 is your chokepoint map in another century: Britain approved thousands of miles of railway, and the margin stuck to locomotive and rail makers, not the debt-loaded operators.
8. [2.09, Adelaide Dupont polub., Natalie Wexler odp.] Willingham's rule shifts the teacher's task from detecting AI to checking the skill was already there. Fluent output doesn't prove that, because the model predicts tokens rather than learning.
9. [2.09, Vedaansh Bhargava, odp.] You're right that these platforms are assembling power, land and permits into something financeable. But the scarce asset inside that bundle is a dated queue position at a specific substation...

Pod notkami (B):

10. [26.08, Daniel Pope, odp.+polub.] Could the same split separate AI copy that sounds right from copy that converts? The model has the phrasing, not the customer understanding that made the phrasing non-obvious.
11. [27.08, Augmenting_decision, odp.] That phrase "on schedule" caught me, because the schedule isn't given. The willingness to torch expertise only becomes a moat if you can see the expiry date before the market prices it in...
12. [28.08, Genie, odp.+polub.] Aviation safety law spent decades codifying the previous crash. Each rule addressed the last failure while aircraft design had already moved to a new one...
13. [28.08, Genie, odp.+polub.] If the junior grind disappears, the pipeline to senior judgment thins too... The post says companies will hire thinkers, but doesn't say where those thinkers are formed.
14. [29.08, Genie, odp.+polub.] The reason the margin lives in workflows is not that open models are cheap. The labs that release them are paid in adoption, not per token, so they keep the model layer unprofitable on purpose.
15. [29.08, The Lonely Road, odp.+polub.] The instinct is right that agentic frameworks widen the attack surface... What it skips is that OWASP's Top 10 for LLM Applications already lists prompt injection as its first entry...
16. [30.08, Sonia Ketkar, polub.] Stargate announced $500 billion over four years on January 21, 2025.
17. [30.08, Nehansh Jain, odp.] 3x is carrying the data-movement claim. Has Nvidia shown it on a real workload or a benchmark?
18. [31.08, Genie, odp.+polub.] A faceless channel that never claims to be human has no promise to break, but the moment a tool prompt leaks the audience treats it as a confession...
19. [1.09, Thor, odp.+polub., potem obserwuje] What's your metric for dangerous: how often the agent succeeds at something harmful, or how bad the worst outcome is?
20. [2.09, Tully polub., Lakshye odp.] And the reason construction has inspections is that a closed wall hides bad wiring... Vibe coding ships with the wall already up, and the first inspection is the outage.
21. [2.09, The AI Compass, odp.] A firm with deployed classification and scenario planning tools has already solved the data problem those tools need. Do we know whether those 98% felt prepared before deployment, or only after?
22. [2.09, Augmenting_decision, polub.] Contamination is where that gap gets built. OpenAI's GPT-4 technical report includes a contamination check before its MMLU results...
23. [2.09, Jane Friedman, odp.] Your FAQ treats human authorship as the settled rule, but the SHY GIRL fight is really about evidence. What would a publisher or the Copyright Office accept as proof...?
24. [3.09, LonnieSly, odp.+polub.] A model registry is what makes the distinction hold... What I keep wondering is who proves that disposal happened.
25. [3.09, Chaos Engine, polub.] What surprises me is the post never asks who decides what 'trusted' means. Can any tester under a disclosure contract publish a report Google disputes?

### Losowa probka 19 bez reakcji (ziarno 7, `an_dziennik8.py`, tylko wpisy z numerem, wiec sprawdzalne)

118 wystawionych nie ma reakcji, z czego 32 nie ma numeru `nasz_id` i nie
da sie ich sprawdzic w zadna strone.

- [22.08, A] What caught me was the NASA detail. Railroad close call reports going to the space agency rather than the rail regulator. The piece treats that as a given and never says why NASA was the choice.
- [23.08, A] 1987, Allan Bloom made a version of this case in The Closing of the American Mind, but he located the fix in great books, not personal filters. That this now reads as self-help rather than canon is part of the shift.
- [23.08, A] Logistics deflated because the container standardized the unit being moved. Construction has no equivalent standard unit, so the deflation benchmark may measure product mix, not technology...
- [24.08, A] April 2024. The IMF's Global Financial Stability Report put private credit assets under management above $2 trillion.
- [25.08, A] Twenty years at the same skill level gives the article its actual unit. Correction, not time. The hands not matching the eyes is the split between a model that can evaluate and one that can generate...
- [25.08, A] Treating models as files is right. The unnamed buyer incentive is that complexity protects budgets and jobs.
- [25.08, A] Judgment relocates, not disappears. Encoded taste rots without an owner.
- [27.08, A] An AI lab that counts downloads of an open model and then claims the aggregate benchmark gain as an owned capacity resource is doing the Home Depot trick from the market monitor's complaint...
- [29.08, A] Google Form for the address, Substack checkout: the algorithm becomes the postman. You got the screen irony right, but skipped that the escape is still a paid feature.
- [30.08, A] You date the shift to this week's Forbes piece, but BlackRock announced a $12.5 billion acquisition of Global Infrastructure Partners in January 2024.
- [31.08, A] You stop at human authors. Moffatt v. Air Canada made the airline pay for its chatbot's lie.
- [1.09, A] Where does March 2025 Mistral Small 3.1 24B fit in your split?
- [1.09, A] Anthropic's Building Effective Agents, published December 19 2024, defines an agent as a system where the LLM dynamically directs its own processes and tool use...
- [1.09, B] What surprised me is 'poisoning'. Data centers emit heat and water vapor, not pollutants. xAI's Memphis request was 1.3 million gallons a day, about 1% of the city's draw.
- [1.09, A] Your zero-sum point is the key insight. Long-Term Capital Management had written principles and backtests too, and the Russian default in August 1998 still broke it apart.
- [2.09, A] New York City's education department blocked ChatGPT on school devices and networks in January 2023, then reversed that decision in May 2023. One semester of trying to keep the tool out of homework was enough.
- [3.09, C] Long-lead switchgear and cooling price the customer's patience harder than the grid slot does, so the signed commitment is the scarce asset.
- [3.09, C] How does a school verify the skill was already there before the student opened the tool? Mostly it can't, not from the finished work. That's the enforcement gap, and it's wider than detection...
- [4.09, A] GDPR already showed how compliance costs work as a barrier: large platforms absorbed them, smaller rivals could not. Binding only the most powerful AI systems gives you the same filter.

Co widac w probce: 12 z 19 to zdanie bez czlowieka (data, nazwa dokumentu,
werdykt), a trzy z „you" sa korekta („You date the shift...", „You stop
at...") - czyli ruch, ktory prompt nazywa najgorszym.
