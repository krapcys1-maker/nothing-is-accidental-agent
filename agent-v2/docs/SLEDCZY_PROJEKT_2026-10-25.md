# Dziennikarz śledczy — projekt systemu (25.10.2026)

Cel właściciela: konto, które przy **każdym** temacie myśli jak dziennikarz śledczy —
samo znajduje największe sprawy w AI, bada je głęboko, zadaje własne, niebanalne pytania,
wyciąga wyraziste wnioski i robi z tego serię angażujących notek i artykuł. Tanio i dobrze:
większość pracy na DeepSeek V4.1 Flash, Sonnet 5.5 albo Opus 5.5 tylko tam, gdzie trzeba
myśleć. Konkretne historie (PHP2Shell, NextDC, Kimi K3.1 Pro) służą do sprawdzania
systemu, nie do strojenia go pod nie.

## Przepływ i kto za co odpowiada

| # | Etap | Co robi | Kto | Koszt (szac.) |
|---|---|---|---|---|
| 0 | Korpus | ok. 400 nagłówków z RSS/YouTube, darmowe | kod | 0 |
| 1 | Kandydaci | radar (ciekawość świeżych nagłówków) + detektor dużych historii (te same sprawy w 4 dniach) → scalanie | Flash, kod | < 0,003 |
| 2 | Wybór | kategoria + nazwy własne → dołączanie z korpusu → zasięg bez przedruków, z YouTube → wynik = zasięg^0,7 × waga kategorii × kara za powtórkę dziedziny | Flash, kod | < 0,002 |
| 3 | Plan śledztwa | ogólny schemat myślenia: co nowego, łańcuch skutków dla grup, co blokuje, wielkie pytanie, smaczek → pytania badawcze konkretne dla historii | **do rozstrzygnięcia próbą** (Flash z myśleniem / Sonnet 5.5 / Opus 5.5) | 0,005–0,05 |
| 4 | Pytania | pytanie główne + podpytania + pytania planu + typowe dla premiery + dokument pierwotny | Flash, kod | < 0,002 |
| 5 | Zbieranie | źródła historii, wątki Hacker News (opinie), cennik OpenRouter (premiera), dyskoweria dokumentów pierwotnych z wyszukiwaniem | kod, Flash z siecią | ok. 0,01 |
| 6 | Klasyfikacja | trafność, klasa źródła, dosłowne cytaty (kod sprawdza, że są w dokumencie) | Flash | ok. 0,02 |
| 7 | Dogrywka | do 3 rund wyszukiwania na otwarte pytania; pusta runda → następne pytanie | Flash z siecią | ok. 0,02 |
| 8 | Karta i nowość | potwierdzone twierdzenia z cytatami; czy zestawienie źródeł coś ustaliło | Flash (+ myślenie) | ok. 0,02 |
| 9 | Kąty serii | 4–5 kątów z zestawu typu (śledztwo / premiera), hak, nasze zdanie z założeniem | **do rozstrzygnięcia** (Opus 5.5 / Sonnet 5.5 / Flash); zapas Flash przy odmowie | 0,01–0,10 |
| 10 | Notki | jedna notka z kąta, 40–65 słów, do 3 dziennie; sprawdzenie faktów i poprawka | **do rozstrzygnięcia** (Opus / Sonnet / Flash); fakty i poprawka Flash | 0,005–0,06 za notkę |
| 11 | Artykuł | pełne śledztwo raz na 6 dni, „Our conclusion” + „What this could lead to” | Fable 5.1 jak dotąd (w testach pomijany) | ok. 0,45 |
| 12 | Pomiar | laboratorium: tempo, dawka→skutek, kąty i kategorie serii | kod | 0 |

## Zasady jakości (stałe, niezależne od tematu)

- **Duży temat**: liczy się zasięg (ilu niezależnych wydawców), nie miejsce w radarze;
  przedruk = jeden wydawca; ta sama dziedzina dwa razy z rzędu dostaje karę.
- **Ciekawość**: plan stawia pytania, których nagłówki nie odpowiadają — schemat jest
  ogólny, pytania konkretne dla historii; badanie szuka na nie odpowiedzi.
- **Głębia**: dokument pierwotny za każdym twierdzeniem instytucji; głosy ludzi jako
  opinie; dogrywka nie kończy się na pierwszej pustej rundzie.
- **Wyrazistość**: kąty analizy mają zdanie i nazwane założenie; werdykt (także „to
  wygląda na AGI z matmy”) jest dozwolony; granica jedna — fakty tylko z karty.
- **Bez powtórek**: notka zna kąty tej historii, które już wyszły; MYSL idzie poziom wyżej.

## Jak wybieramy modele (próba porównawcza 25.10)

Na trzech prawdziwych historiach różnego rodzaju z dzisiejszego korpusu (premiera
modelu, sprawa bezpieczeństwa i AI, trzecia z innej dziedziny), na kopii danych, bez
artykułu: research raz na historię (Flash); plan z trzech modeli; kąty z trzech modeli na
tej samej karcie; notki trzech pisarzy na tych samych kątach. Ocena ślepa: niezależni
sędziowie dostają warianty bez nazw modeli, w losowej kolejności, z kartą faktów, i oceniają
wgląd i ciekawość, konkret, wyrazistość wniosków, wierność faktom i to, czy chce się
czytać dalej. Na każdym etapie bierzemy **najtańszy model w granicach ok. 10% najlepszego
wyniku** — chyba że różnica w wierności faktom przemawia za droższym. Osobny krytyk
researchu ocenia każdą historię: czy plan pytał o to, co ważne, czy badanie na to
odpowiedziało, jakich dokumentów brakuje i co dodałby dobry dziennikarz AI.

Wyniki i decyzje: sekcja poniżej (dopisywana po próbie).

## Wyniki porównania modeli (25.10, czytane ręcznie)

- **Plan śledztwa**: Sonnet 5.5 planował jak Opus za 1/3 ceny; Flash bez myślenia pytał zbyt
  technicznie. Plan idzie na Sonnecie, a zapasem jest DeepSeek Flash Z MYŚLENIEM. W próbie fali 1
  zapas dał 11 konkretnych, ciekawych pytań (zarzut z nagłówka, sprzęt potrzebny do uruchomienia,
  precedensy, smaczek cenowy, wielkie pytanie w obie strony), gdy Sonnetowi zabrakło soczewek NEW i BIG.
- **Kąty serii**: haki porównywalne u trzech modeli; Opus 5.5 zostaje (najlepszy rdzeń i werdykt).
- **Notki serii**: Opus najlepszy (60–65 słów, dowcip, werdykt), Sonnet solidny, Flash za długi
  (70–84 słowa) i z błędami wierności, których fact-check nie złapał. Decyzja D1: wszystkie
  notki serii pisze Opus, do czasu próby Flasha z myśleniem.

## Fala 1 (25.10.2026): co weszło i co pokazała próba

Specyfikacja całości: `robocze/proby_25_10/SPEC_SLEDCZY.md` (lokalnie), kontrakt wdrożenia:
`robocze/proby_25_10/KONTRAKT_FALA1.md`. Weszło:

- **Plan redaktora** (`sledztwo_plan.py`): 12 soczewek (co nowego, jak to działa, twierdzenie
  kontra pomiar, liczby, skutki, władza, praktyka, ludzie, precedens, wielkie pytanie, smaczek,
  termin), walidacja kodem (pytanie musi nazywać tę historię, test podmiany wobec szablonów
  i 6 ostatnich planów, dowód i miejsce), dokumenty pierwotne do zdobycia, starszy redaktor
  (do 3 luk i 2 rund dogrywki).
- **Księga pytań** (`research.deepen(pytania=...)`): status każdego pytania z cytatem
  sprawdzanym kodem, jedna runda na otwarte pytanie, pościg za dokumentem pierwotnym, długie
  dokumenty układane według słów pytania.
- **Karta śledcza**: do 16 twierdzeń, każde sprawdzone dosłownie w swoim źródle, klasy źródeł
  nadawane kodem (PRIMARY tylko dla strony autora historii z jej kluczem, INDEPENDENT dla
  ewaluatorów, LISTING, VOICE, reszta SECONDARY).
- **Kąty**: jedna tabela `KATY`, rdzeń historii (`sedno`) z werdyktem bez asekuracji, kandydaci
  ponad liczbę notek, skład i kolejność wybiera kod, uczciwy hak sprawdzany kodem (liczby
  przywiązane do encji i dowodu, warunki, podpis źródła), poziom tematu decyduje o liczbie notek.
- **Notki**: pierwsze zdanie po bramce haka, bramka notki, wierność wobec twierdzeń kąta przed
  fact-checkiem; nieudana notka serii daje próbę kąta i zwykłą notkę w tym miejscu. MYSL idzie
  obok serii (inne historie z rankingu), bez cyfr, bez nazw serii, w głosie „we”.
- **Artykuł** tylko z zegara tygodniowego, najpierw z zapisanego śledztwa (≤5 dni, poziom L/XL,
  ≥10 twierdzeń z ≥4 hostów, ≥2 rekordy pierwotne, ≥6 odpowiedzi w księdze, werdykt z dowodami),
  potem z puli; nigdy w trybie testu.

Próba na kopii danych (historia o premierze otwartego modelu, bez artykułu):

| Etap | Koszt | Uwagi z ręcznego czytania |
|---|---|---|
| plan | 0,055 USD | Sonnet bez wymaganych soczewek → zapas DeepSeek z myśleniem, 11 dobrych pytań |
| dokumenty | 0,015 USD | 4 nazwane, 2 zdobyte (strona autora, ewaluator) |
| księga + krytyk | 0,084 USD | 15 pytań, 0 pełnych, 12 częściowych odpowiedzi — uczciwie; wyszukiwarka często daje strony-agregatory |
| karta | 0,016 USD | 15 twierdzeń dosłownie w źródle; w tej próbie bez kluczy historii (naprawione) |
| kąty | 0,47 → 0,28 USD | druga runda Opusa przy samej luce w składzie (naprawione: kandydaci + runda tylko przy za małej puli) |
| notki serii | ok. 0,05–0,10 USD na notkę | poprawka Opusa przy każdej złamanej regule |

Błędy wyłapane przez próbę i naprawione tego samego dnia: zapas z feedu przy 403 przerywał się
na pierwszym nieczytelnym kluczu; księga odrzucała odpowiedzi z identyfikatorem w innym
kształcie; karta nie dostawała kluczy historii (żadne źródło nie mogło być PRIMARY); sprawdzanie
wierności zgłaszało nasze własne zdanie („puentę”) jako fakt bez pokrycia; bramka liczb czytała
„$2.00/million” jako 2 miliony; bramka notki dostawała ubogi kontekst (nie widziała nazw modeli);
reguła objaśnień zargonu AI odrzucała notkę z werdyktem. Do następnej fali: jakość wyszukiwania
(strony-agregatory jako jedyne źródło liczby), cytowanie źródła pierwotnego zamiast agregatora,
gdy fakt stoi w obu, pierwsze zdanie notki „jak to działa”, które definiuje zamiast zaskakiwać.

## Zwrot z 25.10 wieczorem: lekkie śledztwo jest domyślne

Polecenie właściciela po pierwszej serii z ciężkiego toru (dolary za temat, a notki nie lepsze od
pierwszego posta o sprawie): **fakty o wybranym temacie mają być znalezione, a resztę — tło, mechanizm,
porównania, konsekwencje, odważny sąd — ma dać model ze swojej wiedzy i kreatywności; ma być ciekawie i
tanio (centy za notkę), bez sztywnych limitów długości i bez dodatkowych sprawdzeń poza faktami przy
publikacji.**

Domyślny tor (`config.SLEDZTWO_TRYB = "lekkie"`, `artykul_z_puli._badanie_lekkie`):

1. historia z radaru → brief (jedno pytanie) → źródła historii + głosy z HN + cennik;
2. klasyfikacja i **dwie** rundy starego `research.deepen` (sufit 0,06 USD) z szerokim pytaniem
   („co się stało, dokumenty i pomiary, głosy ludzi, koszt, co komplikuje nagłówek”);
3. karta faktów (`stages.synthesis`, `sprawdz_karte`);
4. **jedno** wywołanie `sledztwo.seria_lekka` (DeepSeek Flash z myśleniem, `prompts/seria_lekka.md`):
   2–5 notek z karty (liczba z bogactwa karty), fakty tylko z ponumerowanej listy, reszta z wiedzy
   modelu, głos „we”, każda notka sama, pierwsze zdanie zatrzymuje scrollowanie; widełki 40–85 słów to
   wskazówka, nie sufit;
5. rekord PRZED kolejką; do kolejki wchodzą gotowe teksty (`gotowy_tekst`), a `stages.note` publikuje je
   przez to samo sprawdzenie faktów w sieci i naprawę co zawsze — bez pisarza i bez bramek tekstu.

Ciężki tor (plan soczewek, księga pytań, krytyk, dokumenty, poziomy L/XL, kąty z hipotezami) zostaje pod
`--gleboko` — do badania pod artykuł, na żądanie. Stare kąty w kolejce i ciężki tor piszą notki na Flashu z
myśleniem (`notka_przeslania*`), nie na Opusie.

Próba na trzech świeżych tematach z różnych działów (polityka/deepfake, bezpieczeństwo/Tesla FSD i
śmiertelny wypadek, prywatność/profile w ChatGPT) plus sześć kart zapisanych wcześniej:

| Temat | Koszt całości | Seria | Fact-check 5 notek |
|---|---|---|---|
| deepfake żony premiera Hiszpanii | 0,084 USD | 0,004 | 0,035 |
| Tesla FSD, pieszy na I-80 | 0,094 USD | 0,006 | 0,044 |
| profile psychologiczne w ChatGPT (1 źródło) | 0,082 USD | 0,002 | 0,048 |

Czytanie ręczne: notki dają to, czego pierwszy post nie dał — etykieta AI jako osłona prawna zamiast
ostrzeżenia, liczba wyświetleń, której nie da się sprawdzić, wypadek, w którym nie wiadomo, który
uderzenie zabiło, „31 notatek na osobę to strona, nie teczka”. Wyłapane i naprawione w prompcie: polskie
słowo z opisu kąta przeciekło do notki; nazwisko bez roli; dopowiedziane szczegóły sceny („nieoświetlone
pobocze”). Zostaje do decyzji: artykuł tygodnia z lekkiego stanu (dziś reguła §5 wymaga ksiąg i poziomów
ciężkiego toru, więc artykuł idzie z puli).
