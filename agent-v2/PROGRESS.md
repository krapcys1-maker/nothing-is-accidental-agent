# agent-v2 — księga prac

Jedna strona, aktualizowana po każdym skończonym etapie. Czytaj od góry.

---

## Stan: DZIAŁA. Osiem przebiegów pod rząd zakończonych artykułem.

```bash
python agent-v2/run.py
```

Jedno polecenie, zero pytań do człowieka, artykuł w `data/articles/`.

| etap | model | typowy koszt |
|---|---|---|
| skaut tematów | DeepSeek v4-pro | $0,004 |
| ocena wykonalności | DeepSeek v4-flash | $0,003 |
| dyskoveria źródeł | DeepSeek v4-pro (`/responses` + `web_search`) | $0,04 |
| pobranie | HTTP | 0 |
| klasyfikacja i wyciąg | DeepSeek v4-flash | $0,01 |
| synteza — karta dowodowa | DeepSeek v4-pro | $0,007 |
| **pisanie** | **Claude Fable 5** | **$0,53** |
| recenzja — rozliczanie zdań | DeepSeek v4-pro | $0,01 |
| zapis | SQLite + `.md` | 0 |

**Przebieg: $0,44–0,76** (z Fable'em). Na Opusie było $0,21–0,25, przed
przejściem na DeepSeeka $1,10–1,92.

## Budżet złożoności

| | limit | jest |
|---|---|---|
| pliki `.py` | 10 | **7** |
| tabele | 4 | **4** |
| warstwy do modelu | 1 | **1** (`llm.py`) |

Prompty to pliki `.md`. Zero migracji, triggerów, zgód, kolejek.

## Decyzje właściciela

1. **Nic nie blokuje artykułu.** Cztery bramki zgłaszają uwagi; tekst zawsze
   trafia do szuflady.
2. **Po zrobionym researchu artykuł musi powstać.** Synteza pada → karta
   składana z dowodów bez modelu. Pisarz pada → powtórka na Opusie. Recenzja
   pada → zapis bez niej. Wszystkie trzy sprawdzone.
3. **Pisarz ma swobodę interpretacji.** Fakt wymaga pokrycia; analogia
   i argument nie są faktem, mają być tylko widoczne jako myśl autora.
4. **Skaut nie nazywa instytucji w pytaniu** — to był powód dwunastu tematów
   pod rząd o `gov.uk`.
5. **Fable 5 pisze**, DeepSeek robi całą resztę.
6. **Nic nie wychodzi na zewnątrz.** Publikacja i komentarze nie istnieją.
   Hasła do Substacka wpisuje właściciel; plik z nimi jest w `.gitignore`.

## Osiem ostatnich przebiegów

| przebieg | koszt | słów | źródła | uwagi | tytuł |
|---|---|---|---|---|---|
| 37 | $0,2358 | 1221 | 6/6 | 0 | The Bumps at the Corner Are a Curb in Disguise |
| 38 | $0,2214 | 1220 | 3/6 | 2 | The Square on the Toothpaste Tube… |
| 40 | $0,2082 | 1205 | 3/5 | 2 | The Tag Is Not Talking to You |
| 41 | $0,2503 | 1166 | 3/5 | 0 | The Cap That Won't Let Go… (Opus) |
| 42 | $0,5399 | 1091 | — | 0 | The Cap That Won't Let Go (Fable, A/B) |
| 43 | $0,7633 | 1067 | 1/6 | 0 | The Number on Your Orange… |
| 44 | $0,7511 | 1105 | 6/10 | 1 | The Egg Aisle Is a Legal Document |
| 45 | $0,4436 | 1093 | 6/10 | 3 | The Arrow on Your Fuel Gauge… |

Długość ustabilizowała się w celu (1067–1105) po zmianie promptu i przejściu na
Fable'a; wcześniej ciążyła ku 1220.

## Co złapały testy live

- **Konsola Windows cp1252** wywalała agenta na polskich znakach.
- **Wyszukiwarka bez `max_uses`**: 31 rund zamiast 8, koszt kwadratowy — każda
  runda przesyła całą rozmowę od nowa. Najdroższy błąd tego dnia.
- **Filtr adresów otwierał się przy braku danych** zamiast zamykać i przepuścił
  dziesięć zmyślonych URL-i.
- **Sufity tokenów wpisane obok kontraktu** zamiast liczone z niego: prompt
  klasyfikacji prosił o 8400 znaków przy suficie na 5250.
- **Recenzja ucięta na 28 764 tokenach** — DeepSeek rozumuje obficie.
- **Mój własny próg trafności** wyrzucił najlepsze źródło liczbowe.
- **Dwa miejsca liczyły to samo** (czy liczba jest w korpusie) i dały różne
  odpowiedzi. Duplikat skasowany.
- **Plik z hasłem do Substacka** leżał w repo nieignorowany — jeden `git add -A`
  od wypchnięcia na GitHuba. Historia czysta, nigdy nie trafił do commita.

## Sprawdzone i odrzucone

- **Haiku 4.5 i Sonnet 5 do dyskoverii**: nie wywołują wyszukiwania w ogóle,
  wypisują adresy z pamięci. Także po jawnym nakazie w prompcie.
- **Opus 5 do dyskoverii**: działa, ale nieprzewidywalny kosztowo — te same
  8 wyszukiwań dały raz 52 767, a raz 285 759 tokenów wejścia ($0,46 i $1,65).
- **`tool_choice={"type":"web_search"}` na DeepSeeku**: zapętla model, szuka
  bez końca i nigdy nie tworzy bloku `message`. Musi być `"auto"`.

## Zamówione przez właściciela, jeszcze niezbudowane

- **Grafiki do artykułów.** Artykuły na Substacku mają obrazy, więc potrzebne
  będzie generowanie i dołączanie grafiki. Do zrobienia na końcu, po notkach
  i komentarzach.
- **Samodzielne wyszukiwanie postów do komentowania.** Agent ma sam znajdować
  posty — także pod dużymi kontami i pod postami z wieloma komentarzami, żeby
  wchodzić w dyskusje, z których ktoś może trafić na nasz profil. Dziś czyta
  tylko podane adresy.
- ~~**Bramka dowodowa dla komentarzy.**~~ ZAMKNIĘTE. Komentarze, notki
  i odpowiedzi zbierają fakty przed pisaniem i weryfikują to, co napisały.

- **`test_integracja` odpala PŁATNY pełny przebieg dnia.** Po podniesieniu
  odstępów między notkami do 45–90 minut chodzi godzinami i pali pieniądze na
  API. Trzeba mu podmienić `config.ODSTEPY` na czas testu, tak jak podmienia
  `OKNO_PUBLIKACJI_ET`. Do tego czasu jest pomijany, więc pełny przebieg dnia
  NIE jest pokryty testem.
- **0020 stoi na jednym źródle.** Bramka `WASKA_PODSTAWA` to teraz zgłasza, ale
  nie naprawia. Klasyfikacja odrzuca materiał nie na temat (w tym przebiegu
  39 480 znaków z `law.cornell.edu`) i słusznie — brakuje kroku, który po
  takim odsiewie DOSZUKA źródeł zamiast pisać z jednego.

## Otwarte

- **Notki nie maja podlogi na zmyslone przezycie.** Podloga byla nalozona i
  cofnieta 1 wrzesnia: obejmowala wszystkie piec typow zamiast samego MYSL,
  `VAGUE_STUDY` blokowal zdania nazywajace zrodlo, pismo i date, a `config.py`
  w ksztalcie OBSERWACJA wprost zamawia pierwsza osobe, ktora ta sama bramka
  odrzuca. Przy `NOTE_CANDIDATES = 1` notka dnia przepadala bez sladu.
- **`zakwestionuj_promocje` jest kodem nieosiagalnym.** Warunek przywrocony
  swiadomie 1 wrzesnia. Cena znana: 25/26 sierpnia falsz o „The Watermark Was
  Never a Verdict" wyszedl w swiat, bo artykul zostal w kolejce. Bez warunku
  KAZDY powod odrzucenia notki kasowal artykul na stale, takze bez `--wyslij`.
- **`co_dodamy` ginie w drodze do promptu** — `stages.comment_on` je czyta,
  `run.py` nie przekazuje w zadnym z dwoch miejsc.
- **`restackuj_w_kanale` zapisuje `udane=True` bez potwierdzenia**, a lokator
  polubien nie ma `exact=True`. Oba nietkniete swiadomie: nikt nie zmierzyl na
  zywo, jak Substack nazywa te stany, a zla bramka wylaczylaby funkcje CICHO.
- **Skuteczność pobrań waha się od 1/6 do 6/6.** Martwe adresy (404) i blokady
  botów. Częściowo zaadresowane szukaniem dziesięciu źródeł zamiast sześciu.
- **Stawki DeepSeeka niepotwierdzone** — każde takie wywołanie ma w bazie
  `price_verified = 0`. Do sprawdzenia na fakturze.
- **19 testów kontradowodowych z archiwum** — nieprzeniesione. Podłogi
  sprawdzone doraźnie na spreparowanym tekście i łapią.
- **Powtarzalność TEMATÓW ARTYKUŁÓW przy długim działaniu** — reguła „żadnej
  domeny z ostatnich pięciu" istnieje, ale nie była testowana na dłuższej serii.
  Dla notek problem jest zamknięty (`data/zuzyte_fakty.json`), dla artykułów nie.
- **Publikacja artykułu na Substacku** — jedyna zdolność z listy właściciela,
  która nie została zbudowana. Wstrzymana świadomie: przed pierwszym artykułem
  jest jeszcze ustawienie wyłączające czytelnikom sprawdzanie AI oraz grafiki.
- **Odpowiedzi pod ARTYKUŁAMI i pod naszymi komentarzami u innych** — dziś
  `nieodpowiedziane()` chodzi tylko po naszych notkach.

## Dziennik

### 2026-09-01 — audyt pieciu agentow: naprawy okazaly sie szkodliwe, kontrola je zlapala

Pelny zapis: `docs/AUDYT_PIECIU_AGENTOW_2026-09-01.md`.

Audyt prowadzony dwuetapowo, maksymalnie piecioma agentami naraz: najpierw
naprawy, potem **niezalezna kontrola kazdej naprawy przez innego agenta**.
19 znalezisk potwierdzonych, 0 falszywych — ale kontrola wykryla **7 szkod
wprowadzonych przez same naprawy** i to jest glowny wynik.

Najostrzejsze: wpisy porazek dolozone do dziennika zaczely na zawsze skreslac
hosty przy NASZEJ awarii (timeout, padnieta sesja), a lista martwych hostow
nie miala okna czasowego i domykala petle — zdjecie z listy wymagalo udanego
komentarza, ktorego zapora nie pozwalala sprobowac. Osobno: podloga w `note()`
plus zdjecie warunku przy promocji dawaly razem jedno „I noticed" kasujace
artykul z kolejki NA STALE, z pustym powodem, przy zerze platnych wywolan,
a dziennik pisal „(sprawdzenie faktow)".

Trzy razy w tej sesji test przechodzil na kodzie martwym, bo odwzorowywal
WYOBRAZENIE wywolania, nie produkcje. Stad dwie reguly, ktore weszly na stale:
**zadnych asercji po tresci zrodla** (`"..." in ZRODLO` przechodzi takze na
kodzie martwym) i **kontrdowod musi byc ODTWORZONY, nie opisany** — kazdy nowy
test uruchamiany na pliku z `git show HEAD:...`, z prawdziwymi liczbami.

Zamkniete m.in.: potwierdzanie polubien zamiast zakladania, hamulec per blok
(byl globalny i gasil blok dyskusji, ktory daje 23 z 29 wypowiedzi), odwrocony
bodziec w `norma.py` (zero dzialan dawalo 100%, piec dzialan 80%), bariera
wstrzykniecia w `odpowiedz.md`, ktora pilnowala pustego miejsca, oraz fakt
wracajacy do puli PO petli zamiast w jej srodku (cztery „kolejne proby" braly
ten sam fakt).

Dwie poprawki **cofniete swiadomie** — patrz „Otwarte".


### 2026-08-19 — galaz v2-test: bank, bibliotekarz, Fable do notek
*(Galaz wmergowana w `main` i usunieta 23 sierpnia przy porzadkach — tresc zyje w `main`. Kopia testowa na serwerze `~/nia-v2-test` ZOSTALA, ze znacznikiem `TO_JEST_KOPIA_TESTOWA` i z odmowa publikacji.)*
Eksperyment odciety od produkcji: klon `~/nia-v2-test`, wlasna baza (DATA_DIR
wywodzi sie z polozenia config.py, wiec dzieli sie sam), plik-znacznik
`TO_JEST_KOPIA_TESTOWA` odbiera prawo do `--wyslij`. Produkcja stoi na `main`
w `~/nothing-is-accidental-agent`. Punkt powrotu: tag `v1` = `57c9496`.

**Bibliotekarz dziala.** Za $0,0597 wyciagnal z 134 zaplaconych, nigdy
nieczytanych fragmentow trzy mechanizmy laczace cztery dziedziny. Najlepszy:
zegar bezpieczenstwa startuje przy przekroczeniu granicy (otwarcie, autoryzacja,
zmiana pierwszenstwa), nie przy powstaniu rzeczy — laczy szampon, dystrybutor
paliwa i zolte swiatlo. Model PROPONUJE, kod WERYFIKUJE: grupa przechodzi tylko
przy >=2 roznych dziedzinach. Bramka udowodniona kontrdowodem 8/8.

**Dyskoveria zostaje na pro.** Trzy ramiona po trzy pytania. Flash w ZERO na
szesc prob nie wystawil koncowego JSON-a — raz padl calkiem, reszte uratowala
sciezka awaryjna. Podniesienie effort na `high` pogorszylo sprawe (27 i 34
wyszukiwania zamiast 22 i 26). To nie jest kwestia jakosci, tylko niezawodnosci
etapu chodzacego codziennie bez nadzoru.

**Notki przechodza do Fable.** A/B na tym samym materiale: Fable pisze wyraznie
lepiej, +$12,16 miesiecznie przy pieciu dziennie. Dotad bylo odwrotnie niz
powinno — najdrozszy model pisal artykuly, ktore NIE napedzaja wzrostu.

**Bank notek** rozdziela pisanie od publikowania. Wyjecie znaczy notke OD RAZU:
przy awarii wolimy stracic notke niz wystawic dwa razy.

**Styl okladek zmieniony.** Pierwsze dwa naglowki byly jasnym przedmiotem na
jasnym tle — gustowne w pelnym rozmiarze, niewidoczne jako miniatura. Teraz
ciemniejsze tlo, przedmiot na dwie trzecie kadru, slady zuzycia (bez rys panel
czyta sie jak render, a render jak dekoracja).

### 2026-08-19 — dwa bledy warte zapamietania
Test bibliotekarza NADPISAL baze testowa kopia produkcji w trakcie, gdy pisalo
do niej inne ramie pomiaru. Logi ocalaly, zapisy kosztow nie.

Porownanie KOSZTOW w A/B dyskoverii jest skazone: trzy ramiona dostaly te same
pytania po kolei, wiec pozniejsze trafialy w cache DeepSeeka. Porownanie
JAKOSCI tym nie jest dotkniete.

Trzeci: raportowalem, ze notki z banku daja zero wynikow. To byl blad w moim
tescie — `note()` oddaje `{"type","candidates"}`, a test czytal nieistniejacy
klucz `note`. Sciezka dzialala.


### 2026-08-19 — trzy przebiegi testowe: naprawa wad zamieniła się w formułę
Właściciel dał zielone światło na maksymalnie trzy pełne przebiegi, po jednym,
z oceną każdego przed następnym. Wykorzystane wszystkie trzy.

Wady artykułu o szamponie (0016) zniknęły: akapit o granicach zszedł z ⅓ tekstu
do jednego, zniknęła narracja z researchu i powtarzanie mechanizmu. Ale 0017
i 0019 czytane obok siebie mają **identyczny szkielet** — ten sam drogowskaz
przed paralelami, dokładnie trzy paralele, akapit o granicach zapowiedziany
meta-zdaniem, zamknięcie „sprawdź to u siebie".

To nie był przypadek. Tak stało w `pisarz.md`: „End by turning the mechanism
back on something the reader can check for themselves" i „Two or three such
turns". Model wykonywał polecenie za każdym razem tak samo. **Wady treści
zostały wymienione na wadę formy**, a powtarzalna forma zdradza maszynę
dokładnie tak samo jak powtarzana treść.

Naprawa tym samym mechanizmem, co przy notkach (`NOTE_FORM`): ruch końcowy
losowany z sześciu wariantów, szerokość drugiego aktu z 1–3 paraleli. Do tego
zakaz drogowskazu przed paralelami i zakaz zapowiadania akapitu o granicach.

Trzeci przebieg (0020 „The Fossil of a Vote", `POWROT_DO_ZACZEPU`, 2 paralele,
$0,7796) wyszedł najlepszy z serii i pierwszy z **zerem uwag z bramek**. Dwie
paralele nie są katalogiem, tylko podziałem: kontener morski to standard
fizyczny, psuje się przez zamrożenie; sygnalizator to konwencja, psuje się
przez rozpad. Ten podział tłumaczy fakt z materiału — 43 z 44 standardów
z 1939 się zmieniły, kolor nie. „A recognition convention improves by refusing
to."

### 2026-08-19 — pisarz zacytował własną instrukcję
W 0020 wyszło „in the simplest sentence that is still true" — dokładnie tak,
jak stało w `pisarz.md`. Czytelnik tego nie rozpozna, ale to echo polecenia,
nie zdanie z myślenia, a wracając w kolejnych tekstach staje się podpisem
maszyny.

Bramka `FRAZA_Z_INSTRUKCJI` porównuje ciągi sześciu słów z całym promptem.
Utrzymuje się sama, gdy prompt się zmieni, i ma efekt uboczny, którego nie
planowałem: **zakazany przykład wpisany do promptu staje się wzorcem
wykrywania**. Puszczona wstecz złapała w 0016 frazę „this article began life as
an answer to" — czyli dokładnie to, czego prompt zabraniał, zacytowane z zakazu.

Druga bramka, `WASKA_PODSTAWA`, liczy odrębne serwisy pod potwierdzonymi
twierdzeniami. 0020 miał **jeden**, mimo że pobranie udało się 4 razy na 6.
Obie są uwagami, nie blokadami — `verdict` nadal zawsze zwraca `SAVED`.


### 2026-08-15 — pierwszy komentarz, pierwsza notka, pierwsza odpowiedź NA ŻYWO
Trzy zdolności potwierdzone u Substacka, nie z kliknięcia: komentarz pod
„A Witness That Cannot Testify" (`comment_count` 1), notka o datach przydatności
na profilu, odpowiedź w wątku pod naszą notką sprzed miesiąca.

Cztery błędy, które to odsłoniło, wszystkie naprawione:

1. **Kliknięcie to nie dowód.** `wyslane=True` znaczyło „kliknąłem przycisk".
   Sprawdzenie po tekście strony dało fałszywy alarm w drugą stronę — komentarz
   naprawdę wisiał, a `inner_text` go nie widział. Teraz każda publikacja jest
   potwierdzana przez API. Agent bez człowieka nie ma komu zgłosić, że nie
   wyszło.
2. **Zaszyty angielski interfejs.** Selektor szukał „What's on your mind?",
   a ten sam profil otworzył się po polsku. Teraz szukamy po strukturze.
3. **Substack tłumaczy cudze treści.** Odpowiedź Anglika wyświetlała się po
   polsku; agent czytający stronę odpisałby po polsku komuś, kto pisał po
   angielsku. Treści bierzemy wyłącznie z API.
4. **Notki nie miały skąd brać dowodów.** `note()` istniało, ale nikt go nie
   wołał i wymagało materiału, którego nikt nie dostarczał. Doszło
   `znajdz_ciekawostki()`.

Dzień notek: pięć sztuk, 15/15 zweryfikowanych, **$0,0497** — czyli $1,49
miesięcznie za pięć notek dziennie.

**Zmiana progu po uwadze właściciela.** Pierwsza wersja weryfikacji wymagała,
by KAŻDE twierdzenie było potwierdzone, i zabiła dwie z trzech kandydatur nie
za fałsz, tylko za tezę o motywach. Właściciel: „nie ograniczaj go za bardzo…
ludzie też nieraz piszą głupoty, to nie jest zabronione". Próg blokuje teraz
wyłącznie fakt OBALONY przez źródło. Sprawdzone na kontrdowodach: zmyślone
badanie ze Stanfordu ginie, fałszywa przyczyna upadku Osborne'a ginie, czysta
teza o motywach przechodzi.

### 2026-08-15 — trzy przebiegi z Fable'em, ratunek dyskoverii zadziałał
Przebieg 45: dyskoveria zapętliła się (22 wyszukiwania bez odpowiedzi),
ratunek wybrał z 10 już znalezionych adresów drugim wywołaniem, przebieg
dojechał do artykułu z 7 źródłami pierwotnymi. To była ostatnia ścieżka
awaryjna testowana wyłącznie offline.

Przebieg 43: recenzja padła na suficie tokenów, artykuł został zapisany
z adnotacją — reguła „artykuł musi powstać" potwierdzona na żywo.

### 2026-08-15 — Fable 5 wygrał A/B z Opusem
Na identycznej karcie dowodowej (przywiązana nakrętka): Opus 1204 słowa
i więcej głosu, Fable 1127 słów i **wyłapanie, że przepis jest węższy niż jego
popularne streszczenie** — dotyczy tylko Załącznika C, a nakrętki metalowe
z plastikową uszczelką są jawnie wyłączone. Opus tego nie zauważył.

### 2026-08-15 — DeepSeek v4 przejmuje wszystko poza pisaniem
Przebieg z $1,10 na $0,24. DeepSeek ma server-side `web_search` przez
`/responses`, co zdejmuje z Opusa najdroższy i najbardziej nieprzewidywalny etap.

### 2026-08-15 — pierwszy artykuł, cały łańcuch
Temat „The Bag Of Salad That Puffs Up" → „The Additive With No Number".
Karta dowodowa sama obaliła założenie tematu.

### 2026-08-15 — audyt planu przed budową
Warstwa jakości do przeniesienia „w całości" miała 4 220 linii, 22 pary
zdublowanych liczb i udokumentowany w kodzie przypadek dwóch bramek
zaprzeczających sobie. Napisana od nowa: cztery bramki, żadna nie blokuje.
