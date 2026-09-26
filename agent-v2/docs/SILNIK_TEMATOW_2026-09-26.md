# Silnik ciekawych tematów — skąd je brać, po czym poznać, jak podać

26 września 2026. Zlecenie właściciela: zbadać, skąd bot ma brać ciekawe tematy,
skąd ma wiedzieć, że są ciekawe, i jak układać notki, żeby zaciekawiały.
Uzupełnia `agent-v2/docs/PLAN_WZROSTU_2026-09-26.md` (tam punkt 7, „E6").

**Oznaczenia:** [B] badanie naukowe · [A] ankieta instytutu · [S] Substack o sobie ·
[D] analiza danych platformy przez firmę zewnętrzną, bez recenzji · [N] nasze
pomiary i nasz kod.

**Ograniczenie:** polityka sieci środowiska blokowała otwieranie stron, więc źródła
zewnętrzne czytałem przez wyszukiwarkę (fragmenty i streszczenia). Adresy RSS i API
poniżej pochodzą z dokumentacji znalezionej w wyszukiwarce i **każdy trzeba sprawdzić
na żywo na serwerze** (tytuł feedu i data ostatniego wpisu), zgodnie z regułą przy
`korpus_kanalow.ZRODLA`.

> **SPROSTOWANIE, 26 września 2026, później tego samego dnia.** Mechanizm 3
> z rozdziału 1 („szukanie: model idzie tam, gdzie łatwo udokumentować") jest
> nietrafny. Gdy spiżarnia nie jest pusta, skaut w ogóle nie szuka
> (`web_search = not _tresc` w `stages.znajdz_ciekawostki`). Pracuje na ośmiu
> tekstach z naszych feedów, najwyżej dwóch z jednego źródła, a 22 z 25 feedów
> to branża. To spiżarnia daje „91% z czterech blogów". Krok 2 z rozdziału 6
> (styk z cytatem od modelu) zastępuje prostsza wersja: styk przychodzi ze
> źródła, a model go nie deklaruje. Krok 3 (limit hosta) jest niepotrzebny.
> Stan obecny, projekt, koszty i kolejność są w `WYBOR_TEMATOW_2026-09-26.md`.

---

## Najkrócej

1. **Nudne tematy biorą się z kodu, nie z modelu.** Pięć mechanizmów pcha bota
   w branżę: źródła (prawie same blogi techniczne), kolejka banku (fakty z kanałów
   zawsze pierwsze), szukanie (model idzie tam, gdzie łatwo udokumentować), brak
   sygnału popytu i miara „co zadziałało" oparta na polubieniach. [N]
2. **Ciekawe jest to, co jest nowe i jednocześnie zrozumiałe** (Silvia), i to,
   o czym czytelnik coś już wie, ale nie wszystko (Kang, Loewenstein). Bot dziś
   zakłada czytelnika, który „nic nie wie" — czyli lewy, najmniej ciekawy koniec
   krzywej. [B]
3. **Źródła:** trzeba dodać kanały o tym, gdzie AI trafia w życie ludzi: praca,
   zdrowie, szkoła i dzieci, pieniądze i oszustwa, prawo i sądy, produkty na ekranie.
   Są darmowe feedy i API: NBER, FTC, CourtListener, LegiScan, Census, FDA, arXiv
   cs.CY, bazy incydentów i spraw sądowych. [N] [B] [A]
4. **Po czym poznać, że temat jest ciekawy:** połączenie trzech rzeczy — punkt styku
   z życiem czytelnika (sprawdzany w kodzie), sygnał popytu (Wikipedia, GDELT, Google
   Trends) i nasze własne wyniki per rodzina tematów. Sam model tego nie przewidzi:
   na 17 681 testach nagłówków czyste LLM było ledwie lepsze od losowania; działa
   dopiero LLM jako wstępna ocena plus uczenie się z prawdziwych wyników. [B]
5. **Mierzyć trzeba co innego:** polubienia nie mają związku z zapisami (korelacja
   −0,03 na 17 000 notek), a u nas reakcje nie odróżniają dobrej notki od bełkotu.
   Miarą ma być odwiedziny profilu i zapisy na 100 wyświetleń po 72 h. [D] [N]
6. **Notka:** pierwsze zdanie nazywa rzecz prostymi słowami i z właściwą dawką
   konkretu (ani mgła, ani stos szczegółów); jeden mechanizm wyjaśniony przez coś
   z codzienności; na końcu, jeśli dowód na to pozwala, co to zmienia dla czytelnika
   albo co już z tym robiono. Proste słowa wygrały w ponad 30 000 eksperymentów. [B]

---

## 1. Dlaczego bot dziś bierze nudne tematy — pięć mechanizmów w kodzie

| # | mechanizm | gdzie w kodzie | skutek |
|---|---|---|---|
| 1 | **Źródła.** 25 feedów i kanały YouTube; prawie wszystkie to blogi firm, wydania bibliotek, strony awarii i podcasty branżowe. O ludziach piszą właściwie tylko AI Incident Database, Komisja UE i częściowo Transformer. | `korpus_kanalow.ZRODLA`, `KANALY` | 91% faktów z 4 blogów (pomiar 8.09) |
| 2 | **Kolejka banku.** Kandydaci są sortowani `(not z_kanalu, ranga)`: fakt z kanału zawsze idzie przed faktem spoza kanałów, bez względu na rangę. Komentarz przy kodzie: „Próg właściciela: trzy czwarte materiału z kanałów". | `stages.wez_kandydatow` (ok. l. 8940) | kanały = branża, więc branża ma pierwszeństwo |
| 3 | **Szukanie.** Model szuka tam, gdzie łatwo znaleźć fakt z dokumentem, czyli w prasie technicznej. Trzy pomiary: prośby w prompcie tego nie zmieniają. | `stages.znajdz_ciekawostki`, `prompts/ciekawostki.md` | bank: 70% branża, 6% świat |
| 4 | **Brak sygnału popytu.** Ranking banku robi model „z własnych przekonań o tym, co ludzie lubią"; nic z zewnątrz nie mówi, czym ludzie się teraz interesują. | `stages.posortuj_bank`, `prompts/bank.md` | ranking = gust modelu |
| 5 | **Zła miara sukcesu.** `co_zadzialalo` mierzy polubienia + 3 × odpowiedzi; wyświetleń, odwiedzin profilu i zapisów nie liczy. | `stages.co_zadzialalo` (l. 9243) | bot uczy się rzeczy niezwiązanych z zapisami |

Do tego prompt notki (`prompts/notka.md`) zakłada czytelnika, który „knows nothing
about this particular technology" — to najmniej ciekawy punkt krzywej ciekawości
(punkt 2.2).

**Skutek widać w seriach:** 6.09 bank wyżywiłby serię tylko o prądzie i data centre
(4 fakty); „prawo i sądy" miały 2, „AI w szkole" 1, „AI w medycynie" 1, „AI w pracy"
i „kto na tym zarabia" po 0 (`docs/SERIE_TEMATYCZNE_2026-09-06.md`). [N]

**Decyzja właściciela zostaje:** trzy czwarte materiału z kanałów. Zmieniamy to,
co jest kanałem — dochodzą kanały o ludziach — a nie samą regułę.

---

## 2. Co jest ciekawe — co mówią badania

### 2.1. Zainteresowanie = nowość + zrozumiałość
Zainteresowanie rodzi się z dwóch ocen: czy coś jest nowe lub złożone i czy da się
to zrozumieć. Zrozumiałość działa dopiero przy wysokiej nowości; w eksperymentach
najciekawsze było to, co jednocześnie bardziej złożone i bardziej zrozumiałe (Silvia,
Current Directions in Psychological Science, 2008). [B]
**Reguła:** temat musi mieć jedną nową rzecz i jedno wyjaśnienie, które czytelnik
chwyci. Samo „nowe" bez wyjaśnienia (wydanie biblioteki) i samo „zrozumiałe" bez
nowości (ogólnik) nie ciekawią.

### 2.2. Ciekawość = luka przy częściowej wiedzy
Ciekawość to odczuwana luka w wiedzy (Loewenstein, Psychological Bulletin, 1994).
Jest najmniejsza przy „nie mam pojęcia" i przy „wiem na pewno", największa pośrodku;
ludzie płacą czasem za odpowiedź i lepiej ją pamiętają (Kang i in., Psychological
Science, 2009). [B]
**Reguła:** zaczynaj od czegoś, co czytelnik widział: napis „Thinking…" w chatbocie,
skan twarzy na lotnisku, alert w szpitalu, cena subskrypcji. Nie od czegoś, czego
nigdy nie widział (przycinanie warstw).

### 2.3. Po co ludzie w ogóle chcą wiedzieć
Informacji szuka się, żeby lepiej działać, żeby poprawić nastrój i żeby lepiej
rozumieć świat (Sharot i Sunstein, Nature Human Behaviour, 2020). [B] Informacja
o sobie jest lepiej zapamiętywana — efekt odniesienia do siebie, 129 badań, d≈0,45
(Symons i Johnson, 1997). [B] O udostępnieniu decyduje to, co tekst mówi o mnie
i moich relacjach (Scholz i in., PNAS 2017). [B]

### 2.4. Luka newsowa: piszący i czytelnicy chcą czego innego
Na 20 serwisach w 7 krajach dziennikarze stawiali na politykę i gospodarkę,
a czytelnicy klikali sport, kryminał, rozrywkę i pogodę (Boczkowski i Mitchelstein,
The News Gap, MIT Press 2013). [B] W ponad 30 000 eksperymentach Washington Post
i Upworthy czytelnicy wybierali prostsze nagłówki (d=0,55), a zawodowi piszący nie
mieli tej preferencji wcale (d=0,07) (Shulman i in., Science Advances 2024). [B]
**Wniosek:** nasz bank (70% branży) to luka newsowa w czystej postaci. Model ma gust
piszącego o AI, nie czytającego.

### 2.5. Wartości newsowe jako etykiety
Zaktualizowana lista wartości newsowych obejmuje m.in. znaczenie dla odbiorcy
(relevance), skalę (magnitude), zaskoczenie, ciąg dalszy (follow-up), udostępnialność,
konflikt, złe i dobre wiadomości (Harcup i O'Neill, Journalism Studies 2017). [B]
Z tych etykiet kod może liczyć „ciąg dalszy" (sprawa sądowa idzie dalej, nowe dane
w tej samej ankiecie) — to naturalny materiał na serie.

### 2.6. Emocje i ton
- Negatywne słowa podnoszą klikalność nagłówka (+2,3% na słowo w testach Upworthy;
  smutek silniej niż gniew i strach) (Robertson i in., 2023). [B]
- W tych samych testach Upworthy więcej słów pozytywnych obniżało klikalność,
  a intensywniejszy emocjonalnie język ją podnosił; branżowe porady często myliły
  kierunek efektu (Banerjee i Urminsky, Marketing Science 2025). [B]
- Ale na Facebooku negatywne posty mediów mają o 15% mniej polubień i 13% mniej
  komentarzy (6 mln postów, 97 mediów, 6 krajów, w tym Polska). Klikalność nagłówka
  to nie to samo co reakcje w kanale. [B]
- Historie o rozwiązaniach dawały czytelnikom więcej poczucia wiedzy i sprawczości
  i były chętniej udostępniane (Curry i Hammonds, 2014); przegląd 19 badań: poprawiają
  emocje odbiorców (McIntyre i Lough, 2023). [B]
**Reguła:** stawka i skutki tak, czarnowidztwo nie; tam, gdzie dowód pozwala, pokazać,
co już z problemem robiono.

---

## 3. Skąd brać tematy — źródła według punktu styku

Punkt styku to miejsce, w którym zwykły czytelnik spotyka AI. Każde źródło niżej
jest darmowe; część wymaga darmowego klucza. **Wszystkie do sprawdzenia na żywo.**

| styk | źródło | co daje | dostęp |
|---|---|---|---|
| **praca** | NBER, nowe working papers | pomiary wpływu AI na pracę, płace, zatrudnienie | RSS: `https://www.nber.org/papers.rss`; program Labor Studies: `https://www.nber.org/programs/ls/papers.rss` |
| praca | Stanford Digital Economy Lab, „Canaries" | zatrudnienie młodych (22–25 lat) w zawodach narażonych na AI: −13% względem innych, dane ADP; tablica aktualizowana (ostatnio sierpień 2026) | strona z tablicą i PDF |
| praca | Census Bureau, BTOS | co dwa tygodnie: odsetek firm używających AI (17–20%, w firmach 250+ 37%, w informacji 39,7%) | komunikaty prasowe i dane BTOS |
| praca | Gallup | 52% pracowników używa AI w pracy (II kw. 2026), 15% codziennie | raporty kwartalne |
| praca | Anthropic Economic Index | do czego ludzie używają Claude w pracy (raporty I, III, VI 2026) | raporty + dataset `Anthropic/EconomicIndex` na Hugging Face (twierdzenia firmy o sobie) |
| **zdrowie** | Pew Research Center | 34% dorosłych używa chatbotów w sprawach zdrowia, a co czwarty dorosły do oceny objawów | raporty; RSS do sprawdzenia |
| zdrowie | FDA, lista urządzeń medycznych z AI | ponad 1000 dopuszczonych urządzeń; lista aktualizowana (16.06.2026) | lista do pobrania; tworzona przez szukanie słów, więc niepełna |
| **szkoła i dzieci** | RAND, panele edukacyjne | 54% uczniów i 53% nauczycieli używa AI w szkole; uczniowie boją się fałszywych oskarżeń o ściąganie | raporty |
| szkoła i dzieci | Common Sense Media | 72% nastolatków użyło „towarzysza AI", 13% codziennie (NORC, n=1060) | raporty |
| **pieniądze i oszustwa** | FTC | działania wobec firm AI, oszustwa, ochrona konsumentów | RSS: `https://www.ftc.gov/feeds/press-release.xml` i `.../press-release-consumer-protection.xml` |
| **prawo i sądy** | CourtListener | pozwy wobec firm AI (prawa autorskie, szkody), alerty na zapytania | REST API v4, alerty e-mail/webhook; klucz |
| prawo i sądy | baza spraw z „halucynacjami" AI (Damien Charlotin) | 2079 orzeczeń, w których sąd stwierdził zmyślone przez AI cytaty; rośnie co tydzień | strona z bazą |
| prawo i sądy | LegiScan | projekty ustaw o AI we wszystkich stanach USA, pełnotekstowo | API, darmowy klucz, 30 000 zapytań/mies. |
| prawo i sądy | Federal Register, Komisja UE | przepisy federalne i unijne | już w kodzie (`fedreg`, „Komisja UE") |
| **szkody** | AI Incident Database, OECD AI Incidents Monitor | wypadki i szkody z udziałem AI; OECD skanuje 150 000 źródeł newsowych | AIID już w kodzie; OECD: dane na oecd.ai |
| **nauka o ludziach** | arXiv cs.CY (komputery i społeczeństwo), cs.HC (interakcja człowiek–komputer) | badania o wpływie AI na ludzi, zanim trafią do prasy | RSS: `https://rss.arxiv.org/rss/cs.CY`, `.../cs.HC` (puste w weekendy) |
| **ekran** | strony zmian produktów (ChatGPT, Claude, Gemini) i ich cenniki | co się zmienia dla użytkownika | część już jest (OpenAI news) |

**Jak to wpiąć, żeby prośba nie była jedyną bramką** (szczegóły w punkcie 6):
nowe źródła jako osobna grupa `ZRODLA_LUDZIE` w `korpus_kanalow.py`, liczona jako
kanał w regule „3/4 z kanałów"; pole `styk` przy każdym fakcie; limit 2 faktów
z jednego hosta w partii; kwota co najmniej 1 z 3 notek dziennie spoza `branza`.

**Źródła techniczne zostają.** Wydanie modelu czy biblioteki jest dobrym tematem, gdy
ma punkt styku (np. zmiana, którą użytkownik zobaczy na ekranie). Bez punktu styku
jest tematem dla inżynierów, których wśród naszych czytelników prawie nie ma.

---

## 4. Po czym bot ma poznać, że temat jest ciekawy

### 4.1. Sam model tego nie przewidzi
- Na 17 681 testach nagłówków Upworthy czyste metody LLM (prompt, embeddingi,
  dostrojony Llama-3-8B) wybierały zwycięski nagłówek ledwie lepiej niż losowo.
  Wygrało dopiero połączenie: przewidywanie LLM jako start plus bandyta (UCB), który
  uczy się z prawdziwych kliknięć — lepsze od testu A/B, od samego bandyty i od
  samego LLM, zwłaszcza przy małym ruchu (Ye, Yoganarasimhan, Zheng, LOLA,
  Marketing Science 2025). [B]
- LLM trafnie przewiduje kierunek efektów w eksperymentach sondażowych (r=0,85 na
  70 eksperymentach, 105 165 osób; Hewitt i in., 2024), ale to inna rzecz niż
  przewidzenie, która konkretna notka chwyci. [B]
- Nawet przy pełnych danych wielkość kaskady na Twitterze da się przewidzieć tylko
  częściowo (R² < 0,5) (Martin i in., WWW 2016). [B] Wczesna popularność dobrze
  przewiduje późniejszą (Szabo i Huberman, CACM 2010; Cheng i in., WWW 2014). [B]

**Wniosek:** model ma dawać wstępną ocenę, kod ma się uczyć z wyników, a część
sukcesu zawsze będzie losowa. Stąd sygnały niżej i uczenie w 4.4.

### 4.2. Sygnały popytu z zewnątrz (darmowe)

| sygnał | co mierzy | dowód, że działa | pułapka |
|---|---|---|---|
| **Wikipedia, wyświetlenia artykułów** (Wikimedia Analytics API, od 2015, dziennie; także lista najczęściej czytanych) | czym ludzie się teraz interesują, np. skok wyświetleń „Deepfake" albo „Character.ai" | aktywność w Wikipedii przewidywała wyniki kasowe filmów przed premierą (Mestyán i in., PLOS ONE 2013) [B] | globalne i anglojęzyczne; skok może mieć przyczynę spoza AI |
| **Google Trends** (oficjalne API alfa od 24.07.2025, dostęp po zgłoszeniu; spójna skala, 5 lat, do 48 h wstecz) | wzrost wyszukiwań, pytania pokrewne | poprawia „prognozę teraźniejszości" (Choi i Varian, 2012) [B] | replikacja: słabszy efekt w nowszych danych; Google Flu Trends ponad dwukrotnie zawyżał (Lazer i in., Science 2014) [B] |
| **GDELT DOC 2.0** (TimelineVol: udział tematu w globalnym pokryciu newsów, co 15 min/godz./dzień; ostatnie 3 miesiące) | czy media o tym teraz mówią (ciąg dalszy, skala) | wartości newsowe (Harcup i O'Neill) [B] | media ≠ czytelnicy (luka newsowa) |
| **Hacker News** (Algolia API, bez klucza, punkty i komentarze) | nowość wśród technicznych | — | to gust inżynierów, czyli dokładnie nasz dzisiejszy błąd; tylko jako sygnał nowości |
| **Reddit** (publiczne RSS `/r/X/.rss`, `search.rss?q=`) | o co pytają zwykli ludzie (np. nauczyciele, pielęgniarki, użytkownicy ChatGPT) | — | RSS bez liczby głosów; komercyjne API wymaga umowy (od V 2024) — lekko albo wcale |
| **Ankiety** (Pew, Gallup, RAND, Common Sense) | co ludzi naprawdę obchodzi w AI: praca, zdrowie, dzieci, prywatność | rzetelne próby [A] | wolne (raz na miesiące), ale każde wydanie to pretekst do notki |

### 4.3. Sygnały z naszego konta — zmienić miarę
- Polubienia nie mają związku z zapisami: korelacja rang −0,03 na 17 000 notek
  z danymi o konwersji (WriteStack). [D]
- U nas reakcje nie odróżniają dobrej notki od bełkotu (3,2 / 3,0 / 3,1, audyt 3.09). [N]
- Jedynym widocznym krokiem przed subskrypcją są odwiedziny profilu; typ MYSL miał
  ich zero na pięć notek i dlatego wypadł (7.09). [N]
- Substack przypisuje zapisy do konkretnych notek (`growth/sources`, pole `noteId`). [N]

**Nowa miara w `co_zadzialalo`:** odwiedziny profilu i zapisy na 100 wyświetleń,
po 72 godzinach (wcześniej notka nie dojrzała). Polubienia tylko jako opis.

### 4.4. Jak łączyć sygnały — ocena w kodzie, model jako obserwator

Zgodnie z zasadą „model obserwuje, kod rozstrzyga":

**Model odpowiada na pytania z dowodem, nie na oceny w skali** (przy etapie banku):
1. Gdzie zwykły czytelnik to spotyka? Zacytuj zdanie z materiału. (→ `styk`)
2. Co czytelnik już o tym wie albo widział? (→ środek krzywej ciekawości)
3. Co jest tu nowe, w jednym zdaniu?
4. Czy da się to wyjaśnić w dwóch zdaniach bez żargonu? (próba, nie deklaracja)

**Kod liczy wynik kandydata:**
- `styk` z listy (praca, zdrowie, szkoła i dzieci, pieniądze i oszustwa, prawo
  i sądy, ekran, branża) — potwierdzony cytatem; bez cytatu = `branza`;
- świeżość (`source_date`, już jest `swiezosc_faktu`);
- popyt: czy temat ma skok w Wikipedii lub GDELT w ostatnich 7 dniach (tak/nie,
  bez udawanej precyzji);
- ranga z wymuszonego rankingu modelu (już jest);
- różnorodność: limit hostów i rotacja rodzin (już jest wykrywanie bliźniaków).

**Uczenie się (bandyta na rodzinach tematów):** przy 3 notkach dziennie (~90 na
miesiąc) nie da się uczyć na pojedynczych notkach. Uczymy się na **rodzinach** (6–7
wartości `styk`). Dla każdej rodziny kod trzyma liczbę odwiedzin profilu i wyświetleń
z ostatnich 30 dni, losuje rodzinę proporcjonalnie do szansy, że jest najlepsza
(Thompson sampling), i zostawia co najmniej 1 notkę na 3 dni na rodzinę słabiej
zbadaną. To jest dokładnie układ z LOLA: model daje start, prawdziwe wyniki go
poprawiają. Ta sama rodzina metod (bandyci) od lat dobiera artykuły w serwisach
newsowych (Li, Chu, Langford, Schapire, WWW 2010). [B] Uczciwie: przy naszym ruchu wyraźny sygnał pojawi się po 4–8 tygodniach.

---

## 5. Jak układać notkę, żeby zaciekawiła

### 5.1. Co mówią badania o otwarciu
- **Proste słowa wygrywają:** w ponad 30 000 eksperymentów czytelnicy wybierali
  prostsze nagłówki i głębiej je czytali (Shulman i in., Science Advances 2024). [B]
- **Właściwa dawka konkretu:** metaanaliza 8977 testów — gdy nagłówek jest zbyt
  mglisty, więcej konkretu pomaga; gdy zbyt szczegółowy, szkodzi. Najlepszy jest
  „tyle informacji, ile trzeba" (Aubin Le Quéré i Matias, Scientific Reports 2025). [B]
- **Bez zagadek:** nagłówki-pytania i zapowiedzi dawały mniej zaangażowania niż
  streszczenie (Scacco i Muddiman, 2020). [B] U nas: „Zero." bez rzeczownika
  (audyt 3.09). [N]
- **Emocja tak, słodycz nie:** intensywniejszy emocjonalnie język zwiększał kliknięcia,
  więcej słów pozytywnych je zmniejszało; porady branżowe często myliły kierunek
  efektu (Banerjee i Urminsky, 2025). [B]

### 5.2. Co mówią badania o środku i końcu
- **Narracja** zwiększa zrozumienie, zainteresowanie i zapamiętanie u laików
  (Dahlstrom, PNAS 2014). [B]
- **Konkretny język** daje poczucie, że piszący wie, o czym mówi, i słucha; wystarcza
  zmiana jednego słowa (Packard i Berger, JCR 2021). [B]
- **Pytanie przed odpowiedzią** poprawia zapamiętanie, nawet gdy czytelnik odpowie
  źle (Richland, Kornell, Kao, 2009) [B] — dlatego pytanie po fakcie, w środku, a nie
  jako otwarcie.
- **Skutek dla czytelnika albo rozwiązanie** na końcu, gdy dowód na to pozwala
  (Sharot i Sunstein; Curry i Hammonds). [B]

### 5.3. Co mówią dane Substacka (tylko jako hipotezy)
- Notki z linkiem mają mniej polubień (mediana 2 zamiast 4), ale ~3× więcej zapisów
  na polubienie (655 056 notek). [D]
- Najkrótsze notki (<100 znaków) mają najsłabszy zasięg i najlepszą konwersję na
  notkę, ale 89,7% z nich nie daje żadnego zapisu. [D] Długość nie jest dźwignią;
  u nas forma WYJAŚNIENIE (178 słów) okazała się jaśniejsza niż skrót do 56 słów
  (test 4.09). [N]
- Notka, która mówi, dla kogo jest publikacja („is for people who [pragnienie, nie
  temat]" + 2–3 konkrety), konwertuje, gdy czytelnik nie wie, co dostanie. [D] Dobre
  jako przypięta notka na profilu.

### 5.4. Szkielety do losowania (opcje, nie szablony)
Doktryna mówi: nakazy stają się podpisem. Dlatego to są **opcje**, losowane jak dziś
`NOTE_FORM_MIX`, a nie stały układ:

| szkielet | kiedy | przebieg |
|---|---|---|
| **Ekran** | czytelnik coś widzi w aplikacji | co widzisz → co się naprawdę dzieje → dlaczego to ważne |
| **Rachunek** | chodzi o pieniądze | co płacisz albo tracisz → dokąd to idzie → co z tego wynika |
| **Twoje życie** | praca, szkoła, zdrowie | liczba z badania → mechanizm → co to zmienia dla ciebie |
| **Rozwiązanie** | ktoś coś naprawił | problem → co zrobili i jak → czego to nie załatwia |
| **Ciąg dalszy** | sprawa się toczy | co było → co nowego → co dalej |

### 5.5. Przykłady z naszego banku — zła i dobra rama
Fakty poniżej pochodzą z `sto_tematow.json`; przed publikacją przechodzą zwykłą
weryfikację.

1. **Dobry punkt styku — lotnisko.** Fakt: skan twarzy TSA jest dobrowolny, ale
   w testach Algorithmic Justice League (2025) tylko ok. 1% podróżnych usłyszało, że
   może odmówić, a 74% o tym nie wiedziało. Rama inżynierska: „audyt procedur opt-out
   w systemach rozpoznawania twarzy". Rama czytelnika: kolejka do kontroli, w której
   stoi, i zdanie, którego nikt mu nie powie.
2. **Fałszywy punkt styku — „twój rachunek".** Bank ma kilka faktów o tym, że tokeny
   „myślenia" są liczone jako wyjście i podnoszą rachunek. To prawda dla płacących
   za API, nie dla użytkownika subskrypcji ChatGPT. Pytanie „gdzie zwykły czytelnik
   to spotyka? zacytuj" złapie to od razu: odpowiedź brzmi „na fakturze API", więc
   `styk = branza`. To jest powód, dla którego `styk` ma sprawdzać kod z cytatem,
   a nie model z przekonania.
3. **Historia z datą — szpital.** Fakt z 2021: niezależna walidacja modelu sepsy Epic
   dała AUC 0,63, dużo gorzej niż deklarował producent. Doktryna pozwala na historię,
   jeśli data jest widoczna i jest częścią tezy („tak to wyglądało, oto co z tego
   wyszło"). Rama czytelnika: alarm w karcie pacjenta, który może przyjść za późno.

### 5.6. Konkretne zmiany w promptach
- `prompts/notka.md`: zamiast „They know nothing about this particular technology"
  → „They use AI tools or live with their effects, but have never looked under this
  particular part." (środek krzywej ciekawości zamiast lewego ogona).
- `prompts/notka.md`, zakaz zamiast nakazu: „Open with the thing itself, in words
  a reader could repeat. A bare number, a question or a teaser is not an opening."
- `prompts/notka.md`, warunkowo: „If the evidence shows where this lands for
  a reader (a screen they use, a bill they pay, their work, school, health or
  rights), say it plainly once. Don't invent one when it doesn't."
- `prompts/bank.md` i `prompts/ciekawostki.md`: cztery pytania z punktu 4.4 i pole
  `styk` z cytatem.

---

## 6. Projekt w kodzie — kolejność

| krok | co | gdzie | koszt |
|---|---|---|---|
| 1 | Sprawdzić na żywo nowe źródła (tytuł, data ostatniego wpisu), dopisać sprawne jako `ZRODLA_LUDZIE`; liczyć je jako kanał w regule 3/4 | `korpus_kanalow.py`, `stages.wez_kandydatow` | 0 USD |
| 2 | Pole `styk` z cytatem w wyniku szukania i w banku; kod sprawdza wartość z listy, bez cytatu = `branza` | `prompts/ciekawostki.md`, `stages.dopisz_kandydatow` | 0 USD (to samo wywołanie) |
| 3 | Limit 2 faktów z hosta w partii przy zapisie do banku | `stages.dopisz_kandydatow` | 0 USD |
| 4 | Kwota: min. 1 z 3 notek dziennie spoza `branza`; gdy brak, log | `stages.wez_kandydatow` | 0 USD |
| 5 | Nowa miara: odwiedziny profilu i zapisy na 100 wyświetleń po 72 h, zbiorczo per `styk` | `stages.co_zadzialalo`, `statystyki.py` | 0 USD |
| 6 | Sygnał popytu: Wikipedia + GDELT, raz na dobę, flaga „skok w 7 dni" | `korpus_kanalow.py` (bez nowego pliku) | 0 USD |
| 7 | Bandyta na rodzinach `styk` z minimalnym udziałem dla słabo zbadanych | `stages.wez_kandydatow` | 0 USD |
| 8 | Zmiany promptów z 5.6 | `prompts/notka.md`, `bank.md`, `ciekawostki.md` | 0 USD |

Kroki 1–5 dają większość efektu; 6–7 po dwóch tygodniach danych.

### Jak zmierzymy (E6)
Dwa tygodnie przed i po, na poligonie. Progi zapisane z góry:
- **podaż:** ≥ 40% faktów w banku z `styk` ≠ `branza` (dziś ~6%); ≥ 8 hostów na
  35 faktów (dziś 7);
- **odbiór:** odwiedziny profilu na 100 wyświetleń po 72 h nie niższe niż w punkcie
  wyjścia; mediana wyświetleń po 72 h nie niższa o więcej niż 20%;
- **decyzja:** oba spełnione → zmiana idzie do NIA; niejasne → kolejne 2 tygodnie;
  gorsze → cofamy i szukamy dalej.

Przy ~42 notkach w dwa tygodnie wykryjemy tylko duże różnice. To uczciwe ograniczenie,
nie powód, żeby nie mierzyć.

---

## 7. Czego nie robić

- **Nie gonić oburzenia.** Negatywność podnosi kliknięcia w nagłówek, ale w kanale
  obniża polubienia i komentarze, a atak na „obcą grupę" psuje zaufanie potrzebne
  do subskrypcji.
- **Nie brać gustu inżynierów za gust czytelników** (Hacker News, blogi firm).
- **Nie ufać samemu modelowi w przewidywaniu**, co chwyci (LOLA).
- **Nie uczyć się na pojedynczych notkach** — tylko na rodzinach tematów.
- **Nie pobierać Reddita przez API komercyjnie** bez umowy; RSS lekko albo wcale.
- **Nie wymyślać punktu styku**, gdy dowód go nie daje (przykład z tokenami myślenia).

---

## 8. Źródła

### Co jest ciekawe
- [B] Silvia 2008, Interest—The Curious Emotion: https://journals.sagepub.com/doi/10.1111/j.1467-8721.2008.00548.x
- [B] Loewenstein 1994, The psychology of curiosity: https://doi.org/10.1037/0033-2909.116.1.75
- [B] Kang i in. 2009: https://journals.sagepub.com/doi/abs/10.1111/j.1467-9280.2009.02402.x
- [B] Sharot, Sunstein 2020: https://www.nature.com/articles/s41562-019-0793-1
- [B] Symons, Johnson 1997: https://pubmed.ncbi.nlm.nih.gov/9136641/
- [B] Scholz i in. 2017: https://www.pnas.org/doi/10.1073/pnas.1615259114
- [B] Boczkowski, Mitchelstein, The News Gap: https://mitpress.mit.edu/9780262528269/the-news-gap/
- [B] Harcup, O'Neill 2017: https://eprints.whiterose.ac.uk/id/eprint/95423/
- [B] Robertson i in. 2023: https://www.nature.com/articles/s41562-023-01538-4
- [B] Banerjee, Urminsky 2025: https://pubsonline.informs.org/doi/10.1287/mksc.2021.0018
- [B] Negatywne posty na Facebooku, 2025: https://arxiv.org/abs/2507.19300
- [B] Curry, Hammonds 2014 (ENP/SJN): https://mediaengagement.org/wp-content/uploads/2014/06/ENP_SJN-report.pdf
- [B] McIntyre, Lough 2023: https://journals.sagepub.com/doi/10.1177/07395329231187622

### Budowa notki i nagłówka
- [B] Shulman i in. 2024, Reading dies in complexity: https://www.science.org/doi/10.1126/sciadv.adn2555
- [B] Aubin Le Quéré, Matias 2025, When curiosity gaps backfire: https://www.nature.com/articles/s41598-024-81575-9
- [B] Gligorić i in. 2023: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0281682
- [B] Scacco, Muddiman 2020: https://journals.sagepub.com/doi/abs/10.1177/1461444819863408
- [B] Dahlstrom 2014: https://www.pnas.org/doi/10.1073/pnas.1320645111
- [B] Packard, Berger 2021: https://academic.oup.com/jcr/article/47/5/787/5873524
- [B] Richland, Kornell, Kao 2009: https://learninglab.uchicago.edu/Pre-Testing_files/RichlandKornellKao.pdf
- [D] WriteStack: polubienia a zapisy https://thewritingedge.substack.com/p/top-5-note-templates-that-convert · długość https://thewritingedge.substack.com/p/i-found-the-exact-length-for-the · linki https://thewritingedge.substack.com/p/how-to-make-urls-in-your-notes-convert

### Przewidywanie i uczenie się
- [B] Ye, Yoganarasimhan, Zheng, LOLA: https://pubsonline.informs.org/doi/10.1287/mksc.2024.0990
- [B] Hewitt i in. 2024: https://ai4pb.stanford.edu/projects/predicting-results-of-social-science-experiments-using-large-language-models
- [B] Martin i in. 2016: https://arxiv.org/abs/1602.01013
- [B] Szabo, Huberman 2010: https://dl.acm.org/doi/10.1145/1787234.1787254
- [B] Cheng i in. 2014: https://arxiv.org/abs/1403.4608
- [B] Li, Chu, Langford, Schapire 2010: https://dblp.org/rec/conf/www/LiCLS10.html
- [B] Mestyán, Yasseri, Kertész 2013: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0071226
- [B] Choi, Varian 2012: https://onlinelibrary.wiley.com/doi/10.1111/j.1475-4932.2012.00809.x
- [B] Lazer i in. 2014: https://www.science.org/doi/10.1126/science.1248506

### Źródła tematów i sygnały
- NBER RSS: https://www.nber.org/papers.rss
- arXiv RSS (instrukcja): https://info.arxiv.org/help/rss.html
- FTC RSS: https://www.ftc.gov/news-events/stay-connected/ftc-rss-feeds
- CourtListener API: https://www.courtlistener.com/help/api/rest/
- LegiScan API: https://legiscan.com/legiscan
- Census BTOS: https://www.census.gov/programs-surveys/btos.html
- FDA, AI-enabled devices: https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-enabled-medical-devices
- Baza spraw z halucynacjami AI: https://www.damiencharlotin.com/hallucinations/
- OECD AI Incidents Monitor: https://oecd.ai/en/incidents-methodology
- Stanford „Canaries": https://digitaleconomy.stanford.edu/project/indicators/canaries-dashboard/
- Anthropic Economic Index (dataset): https://huggingface.co/datasets/Anthropic/EconomicIndex
- [A] Gallup, AI w pracy: https://www.gallup.com/699797/indicator-artificial-intelligence.aspx
- [A] RAND, AI w szkołach: https://www.rand.org/pubs/research_reports/RRA4180-1.html
- [A] Common Sense Media, towarzysze AI: https://www.commonsensemedia.org/research/talk-trust-and-trade-offs-how-and-why-teens-use-ai-companions
- [A] Pew, zdrowie i chatboty: https://www.pewresearch.org/science/2026/08/25/from-diagnoses-to-treatments-why-americans-use-ai-chatbots-for-health/
- Google Trends API (alfa): https://developers.google.com/search/apis/trends
- Wikimedia Analytics API: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
- GDELT DOC 2.0: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- Hacker News Algolia API: https://hn.algolia.com/api
