# Rozstrzygnięcie: czy to, co budujemy, ma sens — 2 września 2026

Stan, na którym to stoi: produkcja `main` `426d9ea`; gałąź `pamiec/oszacowania`
`d7b3fb7`; brief właściciela z liczbami zmierzonymi na produkcji; kopia lokalnej
bazy `agent-v2.db` (wywołania do 25 sierpnia 17:50 UTC — nie produkcja);
materiał `docs/PACZKA_DLA_MODELU_2026-09-02.md`; pomoc Substacka. Bez serwera,
bez zapisu do `agent-v2/data/`, bez ani jednego wywołania modelu. Liczby z kopii
bazy są oznaczone jako takie; wszystko, czego nie dało się zmierzyć stąd, stoi
w sekcji 8 jako dokładne zapytanie dla drugiego agenta.

---

## 0. Werdykt

**Warstwa pamięci w obecnym kształcie optymalizuje nie tę rzecz i nie jest w
stanie niczego się nauczyć. Zabić ją jako sterownik, zostawić jako przyrząd.**
Mierzy odpowiedzi na komentarze (4 na 125), a przy takiej bazowej próg 12
obserwacji na wariant daje „wiem" co drugi raz na zerze z czystego przypadku
(sekcja 2). Wynik, który liczy, nie ma zmierzonego związku z jedyną rzeczą,
o którą chodzi — czytelnikiem.

Głębiej i ważniej: **cała konstrukcja stoi na tabeli „artykuł 7 subskrypcji /
notki 0 / komentarze 0" (`DOKTRYNA.md:191-195`), która porównuje trzy różne
przyrządy pomiarowe.** Subskrypcje „z artykułu" to pole `signups_within_1_day`,
czyli zapisy w dobie po wysyłce (`browser.py:1476-1478`); subskrypcje „z notki"
to kliknięcia w przycisk z karty interakcji notki (`statystyki.py:60-70`), którego
pod komentarzem na cudzym poście nie ma wcale; a 21 z 69 komentarzy nie ma
żadnej karty zasięgu i wchodzi z zerem. Z tej tabeli wyprowadzono zdanie
„subskrypcje przynoszą artykuły" (`DOKTRYNA.md:200-203`), z niego decyzję, że
komentarze i notki mierzy się odpowiedziami, a z tego warstwę pamięci. Konto
nie widzi własnego lejka, i to jest to jedno miejsce (sekcja 6).

**Żadna rekomendacja niżej nie zmniejsza liczby publikacji.** Żadna nie dodaje
bramki. Żadna nie rusza trzech blokad; jedną proponuję zawęzić tak, żeby
przestała zabijać własne notki promujące (sekcja 7).

---

## 1. Co liczby mówią naprawdę — od tego zaczynam

### 1a. Trzy przyrządy w jednej tabeli

| kanał | skąd liczba „subskrypcje" | co naprawdę liczy |
|---|---|---|
| artykuł | `stats.signups_within_1_day` z `/api/v1/post_management/published` (`browser.py:1476-1478`) | nowe zapisy w ciągu doby po wysyłce; rodzina pól w eksporcie Substacka to `signups_within_1_day`, `disables_within_1_day`, `subscriptions_within_1_day`, `unsubscribes_within_1_day` — wypisania nie da się przypisać do strony wpisu, więc to okno czasowe |
| notka | karta `interactions` z `/api/v1/note_stats/c-ID`, tytuł „Subscribe" (`statystyki.py:60-70`, docstring 28-31: „czytamy WYLACZNIE z karty interactions") | zapisy wykonane z widoku samej notki |
| komentarz pod cudzym artykułem | brak kart (`statystyki.py:260-266`: „Z 52 naszych komentarzy 37 mialo sama karte podgladu"; `wzajemnosc.py:866-869`: 16 z 63 bez kart, przy 0 z 6 artykułów i 0 z 47 notek) | nic; w tabeli stoi zero |

Pomoc Substacka opisuje pole per post jako „Free subscription: The number of
people who subscribed to your publication from that post", ale nazwa pola w
API mówi „w ciągu doby". Rozstrzyga tylko test na produkcji (zapytanie 8.D).
Jest jeden tani sygnał, że to okno: **„Artykuł z ośmioma wyświetleniami dał
trzech subskrybentów"** (`DOKTRYNA.md:197-198`). Trzech na ośmiu oglądających
to 37 procent konwersji z wyświetlenia. Nieprawdopodobne jako ścieżka,
oczywiste jako okno: wtorek 14:00 UTC wychodzi artykuł, tego samego dnia
wychodzi pięć notek i kilkanaście komentarzy, a każdy, kto zapisał się do
środy, jest „z artykułu".

Wniosek nie brzmi „artykuł nie przynosi subskrypcji". Brzmi: **nie wiemy, co je
przynosi, a tabela udaje, że wiemy.** Osobowe przypisanie, które istnieje
w kodzie (`wzajemnosc.kanaly()`, `wzajemnosc.py:850-860`), mówi to wprost:
z 19 czytelników datowalnych jest 5 i „żadnej z nich nie poprzedza w dzienniku
żaden nasz kontakt"; 4 z 19 miało kontakt z treścią, 7 samo zdarzenie
pozyskania, 8 bez śladu (docstring modułu, pkt 3).

### 1b. 23 odpowiedzi pod notkami — nie wiadomo, ile z nich to nasze

Pod artykułem „odpowiedzi" to `comment_count + child_comment_count`
(`browser.py:1469-1472`), czyli z naszymi odpowiedziami włącznie. Pod notką
liczba idzie z karty interakcji albo z `note.reply_count`
(`statystyki.py:268-281`), a doktryna każe odpowiadać każdemu poniżej progu
(`stages.py:545-551`, `config.ODPOWIADAJ_WSZYSTKIM_DO`). Notka z 9
odpowiedziami (`PACZKA`, wiersz 253) może być pięcioma cudzymi i czterema
naszymi. Stosunek 6:1 (a na sztukę 13,6:1) jest zawyżony o nieznany ułamek.
Zapytanie 8.C.

### 1c. Komentarze pod artykułami i pod notkami leżą w jednym worku

Kod robi dwa bloki: pod cudzymi artykułami (`run.py:1410-1422`) i pod cudzymi
notkami (`run.py:1518-1530`, `rodzaj="komentarz"`), z własnym uzasadnieniem:
„Komentarz pod artykulem czyta kilka osob; sensowna uwaga pod zywa notka trafia
do calego watku" (`run.py:1496-1500`). Brief podaje jedną liczbę dla obu.
Pierwsze mają karty zasięgu rzadko, drugie zawsze. Zanim ktokolwiek uzna
„komentarz jest słabszy", trzeba to rozdzielić (zapytanie 8.B). Moja
hipoteza: różnica 13,6:1 to w większości różnica **miejsca** (kanał notek
kontra sekcja komentarzy pod artykułem, gdzie nasza mediana czasu do reakcji to
5,6 h wobec 0,4 h), nie tekstu.

### 1d. Reagujący nie przychodzą z hostów, u których komentujemy

`run.py:748-752`: „62 z 69 reagujacych nie ma w historii naszych komentarzy
zadnego hosta"; hostów, którzy sami zareagowali, jest 7 z 69. Sto kilkadziesiąt
komentarzy u około stu hostów dało siedmiu reagujących hostów. Reszta
zetknięć (polubienia, odpowiedzi, restacki naszych treści) przyszła z kanału
notek. To jest jedyna zmierzona przesłanka o tym, co buduje zetknięcie — i mówi
„notki".

### 1e. Co widać w samym materiale (69 komentarzy, 30 notek)

Policzone skryptem na `PACZKA_DLA_MODELU_2026-09-02.md`, kryteria redakcyjne:
PYTANIE = ostatnie zdanie zostawia hostowi pytanie; KOREKTA = orzeka o tekście
hosta (skips, overstates, hard to square, push back); DOPOWIEDZENIE = dorzuca
cudzy fakt bez orzekania o tekście; WERDYKT = teza o mechanizmie bez pytania
i bez odniesienia do tekstu.

| grupa | n | odpowiedzi | polubienia | mediana słów |
|---|---|---|---|---|
| PYTANIE | 12 | **2** | 2 | 24 |
| KOREKTA | 15 | 0 | 1 | 36 |
| DOPOWIEDZENIE | 15 | 1 | 4 | 28 |
| WERDYKT | 27 | 1 | 8 | 25 |

Cztery komentarze z odpowiedzią mają medianę 21 słów, 65 bez odpowiedzi — 27.
Wśród 22 komentarzy z ostatnich trzech dni 18 ma zaimek „you/I" (instrukcja
z `komentarz.md:152-154` działa), ale zero odpowiedzi — są za świeże, żeby
cokolwiek orzec (próg dojrzałości 3 dni z gałęzi jest tu słuszny). Jedenaście
z 69 komentarzy ma ponad 300 znaków i w materiale są urwane; przy 25–36 słowach
mediany to nie „dwa do czterech zdań" z instrukcji (`komentarz.md:27`), tylko
akapit.

Notki: siedem z 30 ma odpowiedzi, mediana wyświetleń notki z odpowiedzią 45,
bez odpowiedzi 20. Notki z „you/your" (13) zebrały 15 odpowiedzi, pozostałe
(17) osiem. Sześć notek spoza AI (prawo konsumenckie, szampon; wiek 8–9 dni,
sprzed przestawienia) — 113 wyświetleń, 2 odpowiedzi. Notka o 87
wyświetleniach (Ox Alpha) dostała zero odpowiedzi: wyświetlenia nie są miarą,
i `stages.co_zadzialalo` (6279-6300) słusznie ich nie liczy.

### 1f. Koszty (kopia bazy, produkcja, 25 sierpnia — dzień przestawienia)

| etap | wywołań | USD | średnio | uwaga |
|---|---|---|---|---|
| `curiosity` (fakty do banku, DeepSeek flash z wyszukiwaniem) | 22 | 2,25 | 0,102 | 348 tys. tokenów wejścia i 18 wyszukań na wywołanie |
| `write` (artykuł, Fable) | 3 | 1,96 | 0,655 | |
| `note` (Opus) | 13 | 0,73 | 0,056 | |
| `discovery` | 3 | 0,56 | 0,185 | |
| `factcheck` | 16 | 0,17 | 0,010 | |
| `comment` (DeepSeek pro) | 6 | 0,056 | 0,009 | trzy warianty na komentarz (`config.COMMENT_CANDIDATES = 3`) |

Jeden opublikowany komentarz = 3 × 0,0093 + sprawdzenie 0,0103 ≈ **0,038 USD**
(plus ułamek centa na `cele`). Jedna notka = 0,056 + 0,010 ≈ **0,066 USD** bez
udziału w szukaniu faktów. Miesiąc przy pełnym rytmie z doktryny (570
komentarzy, 150 notek, 4,3 artykułu, jedno szukanie faktów dziennie): 21,7 +
9,9 + 6,0 + 3–4 + ~2 (odpowiedzi, ranking banku, aktualne modele) ≈ **42–44
USD**. Sufit to 40. Przy realnym wykonaniu (notki 2,75 dziennie, komentarze
15–19) wychodzi 35–38. Trzecia blokada (budżet) jest więc w zasięgu ostatnich
dni miesiąca bez żadnej nowej funkcji. Zapytanie 8.A rozstrzyga na produkcji.

---

## 2. Pytanie 1 — czy warstwa pamięci jest teraz właściwą rzeczą

**Zabić jako sterownik. Nie „odłożyć": odłożenie zakłada, że kiedyś ruszy w tym
kształcie, a nie ruszy.**

Trzy liczby, każda osobno wystarcza:

1. **Próg 12 nie odróżnia niczego od niczego.** Wynik warstwy to odpowiedzi
   (`oszacowania.py:64`, `GLOWNY_WYNIK = "odpowiedzi"`). Bazowa: 4 na 125
   wystawionych (3,2 %) albo 4 na 69 zmierzonych (5,8 %). Przy 5,8 %
   prawdopodobieństwo zera odpowiedzi w 12 dojrzałych obserwacjach wynosi
   0,942¹² = **0,49**. Co drugi wariant uznany za „wiem" pokaże 0/12 z czystego
   przypadku, a moduł zapisze to jako znaną wartość zero. Żeby odróżnić 3 % od
   9 % (trzykrotną różnicę) przy mocy 80 %, trzeba ~245 obserwacji na wariant;
   5,8 % od 17 % — ~125. Przy 18 komentarzach dziennie i wagach z
   `config.py:1106-1163` (suma 32) CIEKAWOSC dostaje 3,9 komentarza na dobę:
   32–63 dni. KOREKTA (waga 1): 0,56 na dobę, **220–440 dni**. To przy stu
   procentach łączalności z pomiarem, której do 1 września nie było (55 ze 121
   bez `nasz_id`, `browser.py:3526-3536`).
2. **Wynik nie jest celem.** W całym `oszacowania.py` słowo „subskrypcja" nie
   występuje. Warstwa dostraja wagi postaw pod odpowiedzi na komentarze, a
   jedyna zmierzona przesłanka o zetknięciach (1d) mówi, że zetknięcia idą
   z notek. Nawet idealnie działająca warstwa optymalizowałaby kanał, którego
   związku z czytelnikiem nikt nie zmierzył — i nie może zmierzyć, dopóki
   przyrząd z 1a stoi.
3. **Dźwignia jest z góry zamknięta.** `wagi_postaw()` (`oszacowania.py:339-385`)
   nie jest wołana nigdzie poza testem; tryb obserwacyjny jest włączony; a wagi
   KOREKTY i ZGODY są stałą redakcyjną, której właściciel nie chce
   optymalizować (słusznie). Zostają cztery postawy do modulacji o ±50 %
   w oknie, które dziś ma cztery doby. To nie jest system uczący, to tablica.

**Co z gałęzi zostaje i jest dobre:** format oszacowania jako komplet
(`_oszacowanie`, 137-172: licznik, mianownik, okno, wiek, `wiem`, powód,
dowody), rachunek strat (`_zbierz`, 199-231), zasada „przeliczaj, nie
przechowuj" i próg dojrzałości 3 dni. To wchodzi do projektu z sekcji 4 jako
przyrząd raportujący, pod inne pytania i inne wyniki. `raport()` na końcu
przebiegu (`run.py` na gałęzi, 2688-2706) też zostaje — jako log.

**Sygnał, po którym zmieniłbym zdanie** (którykolwiek):
- zapytanie 8.B pokaże, że komentarze pod cudzymi notkami dostają odpowiedź
  w ≥ 15 % przypadków — wtedy 12 obserwacji niesie ~2 odpowiedzi i rachunek
  postawa → odpowiedź ma sens dla TEGO bloku;
- tabela źródeł Substacka (8.E) pokaże, że „Substack trackbacks" (wejścia
  z cudzych postów i komentarzy) przyprowadzają odwiedziny albo zapisy —
  wtedy komentarz ma zmierzony cel i wolno go pod niego stroić;
- wolumen wzrośnie pięciokrotnie, na co nie pozwala ani regulamin, ani
  doktryna, więc tego sygnału nie będzie.

---

## 3. Pytanie 2 — co ten bot ma optymalizować

**Nie odpowiedzi na wypowiedź. Czytelnika poprzedzonego kontaktem, a zanim
takich będzie dość — ludzi, którzy dotknęli naszej treści, na dolara.**

Trzy miary, wszystkie z danych, które już leżą na dysku, zero wywołań modelu:

1. **Czytelnik → co go poprzedziło** (miara główna, tygodniowa). Dla każdego
   nowego uchwytu między dwoma zrzutami `czytelnicy.jsonl`: ostatni nasz
   kontakt z tą osobą w dzienniku (jej reakcja `skutek` z `uchwyty`, nasz
   komentarz pod jej tekstem — `komu`/`publikacja`, nasze polubienie,
   obserwacja) i kanał tego kontaktu. To jest dokładnie `wzajemnosc.kanaly()`
   — dziś 5 datowalnych z 19, zero poprzedzonych. Ta liczba jest mała i ma
   być mała; jest jedyną, która mierzy cel. Rośnie z zrzutami (co przebieg,
   `wzajemnosc.py:ZRZUT_STARSZY_NIZ_DNI` docstring: siedem na 31 godzin) i
   z polem `uchwyty` dodanym 1 września (`browser.py:1770-1784`).
2. **Dotknięci na dolara** (miara prowadząca, dzienna). Liczba RÓŻNYCH osób
   z `skutek` o `typ` w `KONTAKT_Z_TRESCIA` (`wzajemnosc.py:98-104`) w oknie
   7 dni, dzielona przez koszt z `calls` w tym oknie, osobno dla notek,
   komentarzy pod notkami, komentarzy pod artykułami, odpowiedzi. Bazowa jest
   dziesięciokrotnie wyższa niż odpowiedzi (69 osób w tydzień), więc da się
   z niej cokolwiek odczytać w dwa–trzy tygodnie, a nie w dwieście dni.
   Osoba liczy się raz, więc ten sam wierny czytelnik klikający pięć
   polubień nie zawyża.
3. **Tabela źródeł Substacka** (miara kontrolna, dzienny zrzut). Pomoc
   Substacka: „Top sources shows where visitors came from and how many
   subscribed", a wśród źródeł „Substack trackbacks: These readers arrived at
   your content via a link on someone else's Substack, for example in a post,
   comment, or their homepage sidebar" oraz „Substack other: ... a profile
   page, their inbox, or a direct message". To jest przypisanie, którego bot
   nie umie zrobić sam i którego nie czyta, choć panel liczy je za darmo.
   Czytanie własnego panelu własną sesją jest w doktrynie dozwolone
   (`kopia_subskrybentow.py:32-36`); adres bierze się z XHR panelu, nie
   zgaduje (tamże, 27-31).

Czego przestać używać jako celu: wyświetleń (87 → 0 odpowiedzi) i odpowiedzi
na komentarze (4 na 125, niemierzalne pod artykułami). Odpowiedzi zostają
w raporcie jako jedna z reakcji, nie jako cel.

---

## 4. Pytanie 3 — system uczenia się od zera

Nazwa robocza: **księga → miara → przydział → dane w prompcie**. Cztery
warstwy, jedna więcej niż na gałęzi, i to ta czwarta jest nowa: uczenie nie
dotyka zdań w instrukcjach, tylko dokłada do nich dowody.

### 4.1. Zasady, które wynikają z ograniczeń

- Bot uczy się **gdzie, kiedy i ile**, nigdy **co powiedzieć**. Treść zostaje
  przy modelu i redakcyjnych stałych; uczenie zmienia wyłącznie przydział.
- Każdy przydział ma **podłogę** (nic nie schodzi do zera) i **maksymalny
  krok** (20 % na tydzień). „Nie wiem" znaczy „bez zmian". Zero bramek.
- **Przeliczaj, nie przechowuj** (z gałęzi): każdą liczbę liczy kod z surowych
  zapisów przy każdym przebiegu. Jedyny trwały ślad to wiersz `decyzja`
  w dzienniku z migawką (`oszacowania.migawka`, 388-401), który mówi, dlaczego
  przydział był taki, a nie inny.
- **Dane zamiast próśb**: instrukcje dostają nasze własne zmierzone przykłady,
  nie nowe reguły. Tak działa już `bank.md:12-30` z `{co_zadzialalo}`
  (`stages.py:6279-6380`) i `notka.md:91-100` z `{ostatnie_otwarcia_json}` —
  ta druga zmiana zdjęła dwie trzecie rachunku za notki (`stages.py:2166-2177`).
  To jedyna forma zmiany promptu, jaką ten system ma prawo wykonać sam.
- Zero dodatkowych wywołań modelu. Wszystko poniżej to JSONL i arytmetyka.

### 4.2. Co bot zapisuje (księga)

Dziś: `dziennik.jsonl` (działania i skutki), `statystyki.jsonl` (pomiary
pozycji), `czytelnicy.jsonl` (zrzuty), `wzrost.jsonl`, `calls` w bazie.
Dokładam pola, nie pliki:

| do wpisu | pole | skąd, koszt |
|---|---|---|
| `komentarz` | `miejsce`: `artykul` / `notka` | już rozróżnialne po `gdzie` (`note/c-…`), ma być jawne |
| `komentarz` | `wielkosc_hosta` | kod już zna wielkość hostów (`run.py:740-742`: mediana ~5300), ma ją zapisać przy komentarzu |
| `komentarz` | `sasiedzi`: uchwyty innych komentujących w wątku | wątek i tak jest pobierany do `read_pages`/`potwierdz_komentarz`; jedna lista więcej; bez tego nigdy nie połączymy czytelnika z wątkiem, z którego przyszedł |
| `komentarz` | `koszt_usd` łańcucha | suma `calls` między dwoma działaniami tego przebiegu, albo znacznik działania w `llm.call` |
| każde działanie | `wariant_przydzialu` | z jakiego przydziału (udział, hasło, slot) wyszło — żeby dało się policzyć wynik przydziału |
| dzień | `zrodla.jsonl`: tabela źródeł Substacka | jeden odczyt panelu dziennie własną sesją |

Rekord `skutek` już ma `typ`, `kto`, `uchwyty`, `czego`, `kiedy_zdarzenia`
(`browser.py:1769-1784`) — to jest surowiec dla obu miar z sekcji 3.

### 4.3. Co z tego liczy (miara)

Na końcu każdego przebiegu, jak `oszacowania.raport()` na gałęzi, w tym samym
formacie „licznik / mianownik / wiem / powód / straty":

1. **czytelnik → poprzedzający kontakt** (tygodniowo; `wzajemnosc.kanaly`),
2. **miejsce → dotknięci na dolara** (artykuł-komentarz, notka-komentarz,
   własna notka, odpowiedź),
3. **hasło szukania → dotknięci** (`skad: "szukanie: …"` już jest w dzienniku,
   `run.py:opis_celu`),
4. **host → dotknięcia i ciąg dalszy** (czy host odpowiedział, polubił,
   zaobserwował; ilu `sasiedzi` stało się reagującymi albo czytelnikami),
5. **slot dnia → wyświetlenia notki** (z gałęzi, `pory_dnia`, wynik
   wyświetlenia — jedyne pytanie, gdzie wyświetlenia są właściwą miarą, bo
   pytamy o zasięg pory, nie o wartość tekstu),
6. **koszt na dotkniętego** per rodzaj (z `calls`).

Każde z progiem dojrzałości 3 dni i minimum obserwacji liczonym **z bazowej**,
nie stałą 12: minimum = tyle, żeby oczekiwana liczba zdarzeń wynosiła ≥ 5
(przy 28 % dotknięć to 18 obserwacji, przy 5 % odpowiedzi — 100). To zamyka
usterkę z sekcji 2 pkt 1 bez zmiany filozofii gałęzi.

### 4.4. Co z tym robi (przydział) — dokładnie te pokrętła i żadne inne

| pokrętło | dziś | jak się uczy | podłoga / sufit |
|---|---|---|---|
| udział komentarzy pod notkami w dziennym przydziale | sztywno: N pod artykułami (`run.py:1410`) + N/2 pod notkami (`run.py:1518`) | dotknięci na dolara per miejsce | 30–70 % |
| kolejność hostów | znani na koniec (`kanal.py:147-152`), powrót nie wcześniej niż po 4 dniach (`config.ODSTEP_DNI_NA_PUBLIKACJE`) | hosty z ciągiem dalszym (odpowiedź, polubienie, obserwacja) idą PRZED nowymi, po odczekaniu tych samych 4 dni; hosty bez reakcji po dwóch wizytach — na koniec | 4 dni zostają; nowi ≥ 40 % puli |
| hasła szukania | 5 z 7 losowo (`kanal.py:228`) | wagi z dotkniętych per hasło | każde hasło ≥ 10 % |
| slot dnia dla notek | po równo na 5 przebiegów | wagi z wyświetleń per slot | każdy slot ≥ 1 notka, gdy przydział ≥ 5 |
| kogo obserwować i subskrybować | poziom 0: reagujący (`run.py:746-749`) | bez zmian — to już działa na skutku | |

Właściciel dostaje z tego dokładnie to, o co pytał w `opis_celu`
(`run.py`): „czy komentarz jako piąty wraca częściej niż jako pięćdziesiąty
i które hasła przynoszą rozmowy" — pole `komentarzy_przed` jest zapisywane od
dawna i nikt go nie czyta.

### 4.5. Jak zmienia własne instrukcje w `prompts/`

Nie zmienia ich. `stages._prompt` (63-65) czyta plik z dysku i wypełnia
`{pola}`. Uczenie dostaje **jedno nowe pole w trzech plikach**, wypełniane
przez kod z dziennika i statystyk:

- `komentarz.md` — `{co_zadzialalo_komentarze}`: trzy nasze komentarze
  z reakcją i trzy bez, z miejscem i tym, ilu było przed nami. Lustro
  `bank.md`. Dziś model pisze komentarz, nie wiedząc, jak wyglądały te, które
  ktoś podjął.
- `cele.md` — `{hosty_z_ciagiem_dalszym}`: lista publikacji, gdzie ktoś nam
  odpowiedział. `cele.md:71-76` już mówi „returning to a publication we have
  been in before is good"; ma dostać listę, do której to zdanie się odnosi.
- `kogo_odpowiedziec.md` / skaut — `{pytania_czytelnikow}` już istnieje
  (`stages.zbierz_pytania`, `run.py:1140-1143`). Bez zmian.

Reguła twarda: **pole danych dokleja dowody, nigdy nie przepisuje zdania.**
Usunięcie pliku `data/nauka.json` przywraca prompt dokładnie taki, jaki leży
w gicie. Prompt przepisywany modelem odpada z trzech powodów: kosztuje
wywołania, dryfuje bez śladu i omija stałe redakcyjne, które właściciel wpisał
prozą właśnie po to, żeby ich nikt nie optymalizował.

### 4.6. Czego bot nie może o sobie zmieniać — i dlaczego

- **Trzech blokad** (`stages.py:3292-3334`, `3219-3237`, budżet w `llm.py`) —
  bronią przed czymś, czego pomiar nie widzi.
- **Wag postaw, długości, otwarć, form i typów notek** (`config.py:1106-1163`,
  `DLUGOSCI_WYPOWIEDZI`, `OTWARCIA`, `NOTE_FORMS`, `NOTE_MIX_*`) — to nie są
  hipotezy skuteczności, tylko podpis, którego nie wolno mieć: optymalizator
  odpowiedzi nauczyłby się jednej formy i jednej długości w tydzień, a jednolita
  forma jest tym, po czym czytelnik poznaje maszynę (`komentarz.md:34-37`).
- **Wolumenów dziennych i odstępów** (`KOMENTARZE_DZIENNIE`, `LAJKI_DZIENNIE`,
  `ODSTEPY`, `ODSTEP_DNI_NA_PUBLIKACJE`, cichych dni) — to granica regulaminu,
  nie parametr. Uczenie rozdziela przydział, nigdy go nie powiększa.
- **Zakazów z instrukcji**: brak linków do siebie, brak wzmianki o własnej
  publikacji (`komentarz.md:68-69`), brak natychmiastowego odwzajemniania
  (`DOKTRYNA.md §4, §8`), zasada nieudawania człowieka i niezaprzeczania
  (`DOKTRYNA.md §9`). Optymalizator dotknięć nauczyłby się linkować w tydzień
  i miałby rację w każdej liczbie.
- **Własnego przyrządu**: definicji miar, progów dojrzałości, sposobu
  przypisania. Uczący, który może edytować linijkę, zrobi tak, żeby linijka
  się zgadzała.

### 4.7. Kolejność i czas

1. **Tydzień 1, bez modelu**: pola z 4.2, tabela źródeł, raport z 4.3 na końcu
   przebiegu, zapytania z sekcji 8 wykonane. Przydziały bez zmian.
2. **Tydzień 3–4**: pierwsze pokrętło, które ma dość danych — udział miejsc
   (dwa warianty, ~9 komentarzy dziennie na wariant, dotknięcia ~28 %:
   po 120 na wariant w 13 dni). Reszta mówi „nie wiem" i ma tak mówić.
3. **Miesiąc 2–3**: hasła i hosty. Slot dnia dla notek prawdopodobnie dopiero
   po 40 dniach (5 notek dziennie na 4 sloty, rozrzut wyświetleń duży).
4. **Nigdy**: postawy, forma, długość, tożsamość.

Koszt: 0 USD w wywołaniach. Kilka kilobajtów dziennie na dysku.

---

## 5. Pytanie 4 — co jest stratą pieniędzy

Odpowiedź wprost: **komentarze nie są tą stratą.** 125 komentarzy to 3,75–4,75
USD; to najtańsza jednostka w systemie i jedyna, która dociera do autorów
cudzych tekstów (7 z 69 reagujących to hosty). Zostają w liczbie. Zmienia się
tylko, gdzie idą (sekcja 4.4) — i to dopiero po zapytaniu 8.B.

Strata jest gdzie indziej, i wszędzie jest tego samego rodzaju: **płacimy za
rzecz, której nikt potem nie używa.**

| pozycja | liczba | co odciąć / co zostawić |
|---|---|---|
| szukanie faktów do banku (`curiosity`) | 0,10 USD za wywołanie, 14,5 wyszukania; bank wygasa w tydzień, 26 z 58 pozycji bez rangi (`DOKTRYNA` rozb. 6-7), „58 z 69 pozycji lezalo nieuzytych" (`stages.py:1268-1272`) | limit 1/dobę już jest na main (`SZUKANIE_BANKU_NA_DOBE`). Zostaje: partia 8 faktów na dobę przy zużyciu 5 (`CURIOSITY_BATCH = 8`), z siedmiodniowym terminem — ok. 40 % zakupionego materiału wygasa nieużyte. Termin ważności faktu wydłużyć albo partię zmniejszyć do 5. Nie zmniejsza to liczby notek. |
| decyzja „co dodamy" (`cele`) | 0,0045 USD za wywołanie; zapisywana i **nigdy niepodawana modelowi** (`DO_ZROBIENIA.md` poz. 1, audyt GPT 6.4; `run.py:1422` i `1527` podają inny słownik) | to nie pieniądze, to jakość: bot pisze komentarz nie wiedząc, za co wybrał ten post. Dwie linie w `run.py`. |
| komentarze pod cudzymi artykułami bez kart zasięgu | 21 z 69 (30 %) niemierzalne; mediana czasu do reakcji 5,6 h | nie odcinać z powodu wyniku — wynik jest niewidoczny. Rozstrzygnie 8.B. Jeśli i tam zero, przesunąć udział pod notki, gdzie pomiar istnieje. |
| komentarze bez `nasz_id` | 55 ze 121 do 1 września | naprawione na main (`browser.py:3526-3536`). Sprawdzić udział po 1 września (8.I). |
| artykuł pisany trzy razy | 8,38 zamiast 2,12 USD | naprawione doktryną (nic nie blokuje). |
| notki promujące artykuł | 3 z 6 zabite własną zaporą (`DOKTRYNA` rozb. 2) | to jedyna treść, która prowadzi do jedynej rzeczy z mierzalną konwersją; patrz sekcja 7. |
| notki poza AI | 6 z 30 zmierzonych: 113 wyświetleń, 2 odpowiedzi | już nie powstają; z pomiaru wyrzucone (`co_zadzialalo`, 6296-6320). |
| `aktualne_modele` | 0,034 USD, 10 wyszukań, przy każdym szukaniu faktów | ok. 1 USD miesięcznie; zostaje — bez niego notka nazwie nieistniejący model. |

Co zostawić mimo słabego wyniku i dlaczego: **odpowiedzi pod własnymi
notkami** (0,02 USD, jedyne miejsce, gdzie toczy się rozmowa i skąd idzie 4 z
19 kontaktów z treścią), **polubienia i obserwacje** (zero wywołań modelu;
jedyna droga do „poziomu 0" celów), **artykuł tygodniowo** (właściciel tak
zdecydował w doktrynie; audyt GPT K1 twierdzi, że wymaganie brzmiało
„miesięcznie" — to sprzeczność dwóch poleceń właściciela, nie usterka kodu,
i do rozstrzygnięcia przez niego).

Rachunek miesięczny z 1f mówi, że przy pełnym rytmie sufit 40 USD pęka około
28. dnia. Jeśli produkcja to potwierdzi (8.A), pierwsze cięcie to partia
faktów, nie komentarze.

---

## 6. Pytanie 5 — gdzie konstrukcja jest źle pomyślana

**Jedno miejsce: przyrząd, który mierzy skutek, jest zbudowany z trzech
niezgodnych definicji, a wszystkie decyzje o celu wyprowadzono z jego
odczytu.**

Łańcuch, wiersz po wierszu:

1. `browser.py:1476-1478` bierze `signups_within_1_day` jako „subskrypcje
   przypisane do TEGO wpisu — jedyna liczba w calym API, ktora wiaze
   subskrybenta z konkretna trescia". Nazwa pola mówi „w ciągu doby".
2. `statystyki.py:28-31, 60-70` bierze subskrypcje notki wyłącznie z karty
   interakcji, czyli z kliknięć w widoku notki. Komentarz pod cudzym postem
   takiego widoku nie ma; komentarz pod cudzym artykułem nie ma nawet karty
   (`statystyki.py:260-266`).
3. `wzajemnosc.py:911-935` zestawia to w jednej tabeli `pozycyjnie` — z
   uczciwym `bez_zasiegu`, ale bez rozróżnienia definicji.
4. `DOKTRYNA.md:191-203` czyta z tej tabeli: „subskrypcje przynoszą artykuły,
   i każda zmiana, która utrudnia wyjście artykułu, kosztuje najwięcej", z
   dowodem „artykuł z ośmioma wyświetleniami dał trzech subskrybentów".
5. `config.py` na gałęzi (blok `OSZACOWANIA_*`) i `oszacowania.py:64` przyjmują,
   że komentarz mierzy się odpowiedziami, bo subskrypcji z niego „nie ma".
6. Brief do tego rozstrzygnięcia pyta: „125 komentarzy dało 4 odpowiedzi i 0
   subskrypcji — co odciąć".

Każde ogniwo jest lokalnie poprawne i uczciwie opisane w kodzie. Fałsz powstaje
na styku: **zero pod komentarzami jest zerem przyrządu, nie zerem zjawiska**, a
siódemka pod artykułami jest siódemką okna czasowego, do którego wpadają
także zapisy przyprowadzone przez notki i komentarze. To ten sam rodzaj błędu,
co „Substack zdjął przycisk Follow" (`DOKTRYNA.md:222-227`): prawdziwy pomiar,
fałszywy wniosek, wniosek w trzech dokumentach, dokumenty cytujące się
nawzajem. Tamten kosztował dziewięć dni obserwacji. Ten kosztuje kierunek całej
warstwy uczenia.

Naprawa nie wymaga modelu: (1) test definicji (8.D), (2) tabela źródeł
Substacka (8.E), (3) osobowe przypisanie, które już jest, plus pole `sasiedzi`
(4.2). Dopóki to nie stoi, każde „co optymalizować" jest zgadywaniem, także moje
z sekcji 3 — z tą różnicą, że moje miary liczą ludzi, a nie kliknięcia w
przycisk, którego nie ma.

Drugie miejsce, gdybym musiał je nazwać, jest sprzecznością dwóch poleceń
właściciela, nie wadą projektu: `ROZWOJ_KONTA.md:42-46, 71` mówi, że
rekomendacje (78 % darmowych zapisów u cytowanych autorów) wymagają czytania
3–5 publikacji przez tygodnie; `kanal.py:214-224` mówi „Wlasciciel postawil
sprawe jasno: agent ma szukac nowych kont, a nie komentowac wciaz u tych
samych", a kod pcha znanych hostów na koniec (`kanal.py:147-152`). Wynik: 125
komentarzy, około stu hostów, 17 komentarzy na 17 hostach po odsianiu
(`PAMIEC_I_NAPRAWA`, 4a), siedmiu reagujących hostów. Pokrętło „kolejność
hostów" z 4.4 godzi obie rzeczy bez zmiany wolumenu: nowi zostają większością,
ale host, który raz odpowiedział, nie ląduje na końcu listy.

---

## 7. Trzy blokady — nie ruszam, jedną zawężam

Nie proponuję żadnego nowego sprawdzenia. `bramki.py` (przyrząd z AST) pokazuje
na main dokładnie cztery miejsca ustawiające `safe_to_post` na fałsz: zapora
(`stages.py:2286`, `3909`), podłoga z pamięci (`3930`) i `zweryfikuj` (`3464`,
gdzie `not blokujace` jest logiem). Zgadza się z doktryną.

Jedno zawężenie, i nazywam, którą blokadę dotyka: **zaporę przeciw
wstrzyknięciu.** Trzy z sześciu notek promujących artykuł padły na niej, bo
model sam wpisał adres własnego artykułu, a zapora widzi każdy `https://`
(`stages.py:3311-3312`; `DOKTRYNA` rozb. 2). Notka promująca jest jedyną treścią
prowadzącą do jedynej rzeczy z mierzalną konwersją. Zawężenie: adres własnej
publikacji (`config.SUBSTACK_HANDLE` w domenie) nie jest wstrzyknięciem — kod
go wycina z tekstu modelu i dokleja swój, jak i tak robi dwie linie dalej
(`stages.py:2263-2270`). Co się psuje, gdy tej zapory zabraknie w tym jednym
przypadku: nic, bo cudzy tekst nie ma jak wstrzyknąć naszego własnego adresu
z korzyścią dla siebie. Co się psuje, gdy zostanie jak jest: połowa promocji
artykułu. Ile publikacji rocznie to zabija dziś: przy tygodniowym artykule
i trzech notkach promujących — około 75 notek rocznie. Nowe sprawdzenie nie
powstaje; istniejące przestaje strzelać do swoich.

---

## 8. Zapytania na produkcję — dla drugiego agenta

Wszystko czyta się z `agent-v2/data/` i z bazy; nic nie zapisuje. Nazwy pól
z kodu na main: dziennik — `rodzaj`, `kiedy`, `udane`, `gdzie`, `nasz_id`,
`postawa`, `otwarcie`, `publikacja`, `skad`, `komentarzy_przed`,
`reakcje_celu`, `wiek_celu_min`, `tekst`, `komu`, `typ`, `forma`, `id`;
`skutek` — `typ`, `kto`, `uchwyty`, `czego`, `ilu`, `kiedy_zdarzenia`;
statystyki — `rodzaj`, `id`, `wyswietlenia`, `polubienia`, `odpowiedzi`,
`restacki`, `subskrypcje`, `obserwacje`, `ma_karty_zasiegu`, `wystawione`,
`zmierzone`. Pierwsze trzy rekordy każdego rodzaju obejrzeć przed uruchomieniem,
bo część pól doszła 1 września.

**8.A. Wydatki od 25 sierpnia, produkcja, per etap i per model** (SQL):

```sql
SELECT c.purpose, COUNT(*), ROUND(SUM(c.cost_usd),4), ROUND(AVG(c.cost_usd),4),
       ROUND(AVG(c.tokens_in)), SUM(c.web_searches)
  FROM calls c LEFT JOIN runs r ON r.id = c.run_id
 WHERE c.at >= '2026-08-25' AND COALESCE(r.tryb,'produkcja') = 'produkcja'
 GROUP BY c.purpose ORDER BY 3 DESC;
SELECT substr(c.at,1,10) d, ROUND(SUM(c.cost_usd),4) FROM calls c
  LEFT JOIN runs r ON r.id = c.run_id
 WHERE c.at >= '2026-08-25' AND COALESCE(r.tryb,'produkcja') = 'produkcja'
 GROUP BY d ORDER BY d;
```
Po co: rozstrzyga 1f (czy sufit 40 pęka) i sekcję 5 (gdzie idą pieniądze).

**8.B. Komentarze pod artykułami kontra pod notkami — z pomiarem** (python):

```python
import json, statistics
D = [json.loads(l) for l in open("agent-v2/data/dziennik.jsonl", encoding="utf-8") if l.strip()]
S = {}
for l in open("agent-v2/data/statystyki.jsonl", encoding="utf-8"):
    if l.strip():
        w = json.loads(l)
        if w.get("rodzaj") == "komentarz": S[str(w.get("id"))] = w   # ostatni pomiar wygrywa
kom = [w for w in D if w.get("rodzaj") == "komentarz" and w.get("udane") and str(w.get("kiedy",""))[:10] >= "2026-08-25"]
for miejsce, f in (("pod notka", lambda w: str(w.get("gdzie","")).startswith("note/c-")),
                   ("pod artykulem", lambda w: not str(w.get("gdzie","")).startswith("note/c-"))):
    grupa = [w for w in kom if f(w)]
    z = [S[str(w.get("nasz_id"))] for w in grupa if str(w.get("nasz_id")) in S]
    print(miejsce, "wystawione", len(grupa), "z pomiarem", len(z),
          "z kartami", sum(1 for s in z if s.get("ma_karty_zasiegu")),
          "odpowiedzi", sum(int(s.get("odpowiedzi") or 0) for s in z),
          "polubienia", sum(int(s.get("polubienia") or 0) for s in z),
          "z jakakolwiek reakcja", sum(1 for s in z if (s.get("odpowiedzi") or s.get("polubienia") or s.get("restacki"))))
```
Po co: 1c, sygnał z sekcji 2, pokrętło „udział miejsc" z 4.4.

**8.C. Ile z 23 odpowiedzi pod notkami jest naszych** (API własną sesją):
dla każdego `id` z dziennika (`rodzaj == "notka"`, `udane`) pobrać wątek tą
samą drogą, którą robi to `browser.nieodpowiedziane()`, i policzyć odpowiedzi
z `handle != config.SUBSTACK_HANDLE` oraz liczbę różnych `handle`. Wypisać:
notek, odpowiedzi cudzych, naszych, różnych osób, ile osób odpowiedziało pod
więcej niż jedną notką.

**8.D. Test definicji `signups_within_1_day`**: dla każdego artykułu z
`/api/v1/post_management/published` wziąć `post_date` i
`stats.signups_within_1_day`; z `agent-v2/data/kopie/subskrybenci-*.csv`
(kolumna `Start date`) i ze zrzutów `czytelnicy.jsonl` policzyć nowych
subskrybentów w oknie [post_date, post_date + 24 h]. Jeśli liczby są równe dla
każdego artykułu — pole jest oknem czasowym i tabela z §11 doktryny nie mówi
tego, co jej przypisano. Jeśli `signups` jest mniejsze niż nowi w oknie —
pole jest ścieżkowe i doktryna stoi.

**8.E. Tabela źródeł Substacka**: w panelu Stats → Traffic („Top sources")
i Growth podejrzeć XHR, którym strona pobiera źródła (nie zgadywać adresu —
`kopia_subskrybentow.py:27-36`), odczytać własną sesją za ostatnie 30 dni:
odwiedziny i zapisy per źródło (Direct, Email, Substack onboarding, Substack
other, Substack trackbacks, Direct to App). Zapisać adres i jeden zrzut
odpowiedzi do `docs/`. To jest jedyne przypisanie źródła, jakie istnieje.

**8.F. Reagujący — kim są**: z `skutek` (typ w `wzajemnosc.KONTAKT_Z_TRESCIA`)
zbiór różnych `uchwyty`; ilu z nich to hosty z `gdzie_komentowalismy.json`
(równość uchwytu z kluczem publikacji, jak `run.kogo_juz_dotknelismy`); ilu
jest w ostatnim zrzucie `czytelnicy.jsonl`; ilu reagowało ≥ 2 razy. Podać
trzy liczby i listę tych ≥ 2 — to są kandydaci na „3–5 publikacji" z
`ROZWOJ_KONTA.md`.

**8.G. Hasło szukania → reakcje**: z dziennika `skad` („szukanie: X" /
„kanal czytelnika") zgrupować komentarze i zsumować z 8.B `odpowiedzi +
polubienia` per hasło. Podać n i sumę dla każdego z 7 haseł.

**8.H. Host → komentarze i reakcje**: grupować po `publikacja`; ile hostów ma
≥ 2 komentarze; reakcje przy pierwszym i przy kolejnych komentarzach u tego
samego hosta.

**8.I. Pokrycie `nasz_id` po naprawie**: udział wpisów `komentarz`, `udane`,
z `nasz_id` nie w ("", "-1", None), per dzień od 1 września.

**8.J. Bank — ile zakupionego wygasło**: z `indeks_kandydatow.json` liczba
pozycji po terminie i nieużytych od 25 sierpnia; zestawić z liczbą wywołań
`curiosity` w tym czasie (z 8.A).

---

## 9. Czego nie zweryfikowałem i co może mnie obalić

- Definicja `signups_within_1_day`. Pomoc Substacka opisuje pole per post jako
  „from that post"; nazwa i rodzina pól mówią „w dobie". Jeśli 8.D pokaże, że
  to ścieżka, sekcja 6 traci pierwsze ogniwo — ale nie drugie i trzecie
  (subskrypcje z notki i brak kart pod komentarzami zostają niezgodne z nią).
- Ile z 23 odpowiedzi pod notkami to nasze (8.C). Nawet gdyby połowa, notki
  zostają lepszym miejscem rozmowy niż komentarze.
- Koszty od 25 sierpnia liczę z cen w `config.PRICING` i z jednego dnia w kopii
  bazy; produkcja może być tańsza o cache albo droższa o wydarzenia.
- Nie czytałem `norma.py`, `alarm.py`, `artykul_z_puli.py` w całości ani
  `pisarz.md`, `skaut.md` poza początkiem. Nic z rozstrzygnięcia na nich nie
  stoi.
- Nie wykonałem ani jednego przebiegu i nie widziałem produkcyjnego dziennika;
  lokalny ma 589 bajtów. Wszystkie liczby o dzienniku pochodzą z komentarzy
  w kodzie, które je zmierzyły (`browser.py`, `run.py`, `wzajemnosc.py`), i z
  briefu.
