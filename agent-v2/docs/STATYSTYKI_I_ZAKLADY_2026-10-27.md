# Statystyki NIE jako produktu i ksiega zakladow (27.10.2026)

Decyzja wlasciciela 27.10.2026: „NIE nie jest tylko botem testowym do pozniejszych wdrozen dla NIA" — ma miec **pelen zestaw
statystyk** jako samodzielny produkt, a sledczy, ktory rozkminia i moze sie mylic, ma byc **rozliczany z trafnosci**. Ten dokument
opisuje trzy rzeczy: raport `co_dziala.py`, ksiege zakladow `zaklady.py` i eksperyment E22 (dlugosc notek serii) wraz z regula
decyzji spisana PRZED startem.

## 1. Raport `co_dziala.py`

Jeden raport z jednego dziennika notek, liczony tymi samymi miarami co karta wynikow i `eksperymenty.py` (zasieg po 72 h, tlo
tygodnia, bootstrap 95%, ziarno stale). Dziala wylacznie na danych NIE (`config.DATA_DIR`), tylko do odczytu; zapisuje
`data/obserwatorium/co_dziala.md` i `.json` oraz jedna linie na dobe w `data/co_dziala.jsonl` (historia do trendow).
Uruchamia go zegar obserwatorium (`obserwatorium.py zbierz --raport`), a recznie:

    python agent-v2/co_dziala.py                  # na ekran, epoka od 26.10.2026
    python agent-v2/co_dziala.py --od 2026-09-28  # dluzsza historia (wiecej notek, wiecej mocy)
    python agent-v2/co_dziala.py --zapisz

| sekcja | pytanie | zrodlo |
|---|---|---|
| Wnioski | co robic czesciej, rzadziej, a gdzie dowodow brak | z tabel ponizej, tylko przy werdykcie z przedzialu 95% |
| 1. Formaty | czy seria / rozkmina / MYSL / promocja / rozliczenie bija zwykla notke z banku | dziennik + `statystyki.po_godzinach(72)` |
| 2. Wymiary | kat serii, kategoria historii, pozycja w serii, dlugosc, pora, dzien tygodnia, typ, forma, model, styk, pytanie na koncu | te same wiersze |
| 3. Najlepsze | osiem najczesciej czytanych notek epoki z formatem i katem | te same wiersze |
| 4. Eksperymenty | kazdy wpis `config.EKSPERYMENTY` ze statusem i ramionami; E22 po SERIACH | dziennik (`eksperymenty`) |
| 5. Koszt | koszt tematu, notki i 1000 wyswietlen wedlug formatu; gdzie ida pieniadze (7 i 28 dni) | baza `calls` (tryb produkcja) |
| 6. Sprawdzenie faktow | ile notek mialo obalone twierdzenie, ile naprawiono, ile zastrzezen | pole `fc` w dzienniku od 27.10.2026 |
| 7. Potok | sledztw, notek wyprodukowanych i wydanych, kolejka: czeka / wygaslo / pominiete | `sledztwa.jsonl`, `przeslania.json`, dziennik |
| 8. Wzrost | subskrybenci netto, wyswietlenia, odwiedziny profilu, koszt: 7 i 28 dni | `dni_NIE.json` obserwatorium |
| Zaklady | ksiega zgadywan: trafienia z przedzialem, Brier, kalibracja | `zaklady.jsonl` |
| 10. Czujnik | przebicia „co klika teraz" w AI-Substackach | `co_klika.jsonl` |

**Definicje.** Epoka = od 26.10.2026 (start serii sledczej obok banku). Tlo tygodnia liczone ze WSZYSTKICH notek od 28.09.2026
(`eksperymenty.odejmij_tlo`), zeby tydzien nie udawal zmiany. Odbior = (odwiedziny profilu + 5 x zapisy przypisane) na 100
wyswietlen. Format wynika z `przeslanie_id` (seria / rozkmina po numerze przebiegu ze `sledztwa.jsonl`; `-rozliczenie`) albo z `typ`
(MYSL, ARTYKUL = promocja). Notka z zerem wyswietlen po 72 h wypada z porownania `eksperymenty.wiersze`; raport liczy ja osobno.

**Werdykt z NIEZALEZNYCH JEDNOSTEK (przeglad 27.10).** Cztery notki jednej serii (jedna historia, jedno wywolanie modelu) nie sa
niezalezne, a notki jednej doby dziela tlo i los eksperymentow losowanych na dobe. Dlatego `tabela()` robi bootstrap 95% po KLASTRACH
(seria albo doba publikacji), a nie po notkach — wzor `ci_klastrow`, to samo ziarno co `eksperymenty`. Bootstrap po notkach daje przy
silnym efekcie serii przedzial wyraznie wezszy (test przypina: 0,78-1,40 wobec 0,61-1,89 na tych samych danych) i falszywe „lepiej". Werdykt
pada od 6 niezaleznych jednostek w grupie i w odniesieniu (`MIN_KLASTROW`); 12 notek z trzech serii to „za malo danych". Porownania z roznych
okresow dostaja ostrzezenie, a „Wnioski" robia z nich „WSKAZANIE (nie dowod)" zamiast „PISAC CZESCIEJ". Koszt na 1000 wyswietlen liczony tylko
z serii dojrzalych (wszystkie notki 72 h), koszt tematu bez wywolan ksiegi zakladow (`zaklady_*` chodza pod numerem przebiegu sledztwa), notka
rozliczajaca nie jest notka serii. Okna kosztu to pelne doby do wczoraj; kubelki godzin sa calkowite (12:30 UTC to kubelek 12-16).

**Uczciwie o mocy.** Konto ma mediane kilkunastu wyswietlen na notke i odchylenie logarytmu ok. 0,4-0,5, wiec przy 10-12 notkach
w grupie wykrywalna roznica to ok. +50%. Raport dlatego (1) nie wydaje werdyktu ponizej 10 notek w grupie i w odniesieniu, (2) przy kazdej
grupie bez dowodu podaje, jaki efekt bylby wykrywalny, (3) oznacza porownania z roznych okresow. Tabele wymiarow to MAPA, gdzie szukac
(wymiary sie nakladaja: seria jest dluzsza niz bank, rozkmina wychodzi o innej porze) — dowodem jest tylko eksperyment przeplatany.
Sedziowie LLM zasiegu nie przewiduja (pomiar 28.09.2026), wiec wszystko tu liczy konto, nie ocena modelu.

**Pierwsze odczyty na zywych danych (kopia z 27.10.2026, epoka od 28.09, 62 notki):** mediana 10 wyswietlen; zadna roznica miedzy formatami,
dlugosciami, porami, typami ani modelami nie wychodzi poza przedzial ufnosci (wykrywalne dopiero ok. +40-50%). To jest stan wyjscia, nie
wada raportu: seria sledcza ma w epoce dopiero cztery notki, wiec pierwszy sensowny odczyt formatow wypada ok. 9.11.2026 (ocena pakietu
z 25.10).

## 2. Ksiega zakladow `zaklady.py`

Rozkmina jest wartoscia tylko wtedy, gdy ktos liczy, ile razy trafila. Modul robi trzy rzeczy, po jednym tanim wywolaniu Flasha:

1. **Wyciag** — z notek serii (sledztwo, rozkmina, MYSL), ktore JUZ WYSZLY (doba po ostatniej notce serii, liczona od PRAWDZIWEGO teraz, okno
   8 dni), model wskazuje najwyzej dwa sprawdzalne zgadywania: cytat z notki, zdanie samodzielne, co je obali, od kiedy i do kiedy mozna
   rozstrzygnac, jak prawdopodobne wydaje sie mu samemu (z tego liczymy kalibracje). Kod pilnuje: numer notki z listy, tresc, DATY W OKNIE
   (jutro .. 400 dni, co najmniej 14 dni na sprawdzenie), **zaklad musi WYNIKAC Z NOTKI** (cytat stoi w niej prawie slowo w slowo, a nazwy
   wlasne zakladu — OpenAI, GPT-7 — sa w tekstach grupy; inaczej odpada z logiem, bo konto nie moze miec przypisanego zgadywania, ktorego
   nie bylo), zero cen akcji, wycen i kapitalizacji (jakikolwiek czasownik; „market share" przechodzi), dedupe po nazwach wlasnych i slowach tresci
   (rozne firmy o tym samym szkielecie zdania to NIE dubel). Notka liczy sie raz, takze gdy dala zero zakladow; dwie nieudane proby wyciagu
   (blad modelu, brak JSON-a) tez ja zamykaja.
2. **Sprawdzenie** — zaklad po `check_from`, nie czesciej niz co 6 dni, najwyzej trzy na przebieg, wyszukiwarka (Flash z siecia).
   **Rozstrzygniecie („trafiony", „chybiony") wymaga adresu, ktory wyszukiwarka naprawde zwrocila w tym wywolaniu** (`llm.call(collect_urls=)`)
   i niepustego dowodu, ktory przeszedl zapore wstrzykniec (`stages.bez_wstrzykniecia`); bez adresu zaklad zostaje otwarty, bez dowodu jest
   „niejasny". Kazda proba zostawia slad, takze nieudana: po bledzie obowiazuje ten sam odstep 6 dni, a trzy bledy albo dwa „niejasny" = nie do
   rozstrzygniecia (inaczej wadliwy zaklad wracalby co przebieg i zjadal miejsce reszcie). Po `check_by` nierozstrzygniety zaklad wygasa — ale
   WYGASLE NIE ZNIKAJA ZE STATYSTYK: pudla zwykle nie maja adresu rozstrzygajacego (brak zdarzenia nie ma strony), wiec sama liczba rozstrzygnietych
   zawyzalaby celnosc. Raport podaje tez odsetek trafien przy wygaslych liczonych jako chybione (dolna granica) i ile z nich model uznal za niespelnione.
3. **Rozliczenie** — rozstrzygniety zaklad dostaje notke („zgadywalismy X, wyszlo Y — mylilismy sie w tym, jak myslelismy"), ktora idzie
   zwykla kolejka serii (`rodzaj` ROZLICZENIE, tekst gotowy, sprawdzenie faktow w sieci przy publikacji, jak u kazdej notki serii).
   Najwyzej jedna na 3 dni i tylko gdy w kolejce czeka mniej niz dwa wpisy, zeby nie zjadac miejsca nowym sledztwom. Tekst notki przechodzi zapore
   wstrzykniec jak kazda notka serii, a do tego: zero linku, domeny, wzmianki, hashtagu i emoji, 15-170 slow; nieudana notka zostawia slad
   (`rozliczenie_blad`), po trzech probach zaklad czeka, a w jednym przebiegu idzie nastepny kandydat, wiec jeden zepsuty nie zaglodzi reszty.

**Gdzie chodzi.** `artykul_z_puli._zaklady_przy_okazji` — w `finally` po zegarowym przebiegu sledztwa (13:10 UTC), wiec sledztwo ma pierwsze
prawo do kolejki. Bez `--wyslij` tylko liczy (zero wywolan modelu, zero zapisow). Proby reczne (`--z-sledztwa`, `--historia`) ksiegi nie ruszaja.
Wylacznik: `config.ZAKLADY_WLACZONE`. Awaria ksiegi nigdy nie wywala sledztwa. Zadnej nowej jednostki systemd.

**Stan** to dziennik zdarzen `data/zaklady.jsonl` (tylko dopisywanie): `zaklad`, `wyciag`, `sprawdzenie`, `rozliczenie_w_kolejce`.

**Zmierzone na zywo, wyciag (kopia danych, 27.10.2026).** Na 15 testowych seriach z rozkmina model bez wymogu cytatu znalazl 1 zaklad i pominal
dwa wyrazne („Our bet: Tesla nadal sprzedaje FSD pod ta nazwa za rok"), bo prompt kazal terminowi miescic sie w 150 dniach; po poszerzeniu terminu
do 400 dni oba wyciagniete poprawnie. Wymog cytatu i nazw wlasnych dodany po przegladzie kodu (agent wykazal, ze zaklad o „GPT-7" przeszedlby z notki
o zupelnie innej firmie).

**Koszt.** Zmierzone na zywo (kopia danych, 27.10.2026): wyciag z serii 0,0005-0,0016 USD; sprawdzenie zakladu 0,0045 USD (3-4 szukania);
notka rozliczajaca 0,0006 USD. Razem rzedu 1-3 centow na dobe. Probe na zakladach o znanym wyniku („GPT-5 do konca sierpnia 2025" — trafiony,
„skladany iPhone do konca 2025" — chybiony) ksiega rozstrzygnela poprawnie, z adresami z wyszukiwania, a notki rozliczajace byly rzeczowe.

**Statystyki ksiegi.** Odsetek trafien z przedzialem Wilsona 95%, wynik Briera (0 idealnie, 0,25 = rzut moneta), kalibracja w trzech
przedzialach pewnosci. Przy mniej niz 10 rozstrzygnieciach raport pisze wprost, ze to szum. Zaklady maja terminy rzedu tygodni, wiec pierwsze
rozstrzygniecia ksiegi z prawdziwych serii spodziewane sa w listopadzie.

## 3. E22 — dlugosc notek serii (regula decyzji przed startem)

Notki serii sa dluzsze (50-110 slow, w praktyce ok. 90) niz notki drugiego konta i krotka notka z E17 byla wtedy zasada dla banku. Czy rozkmina
potrzebuje tego miejsca, trzeba sprawdzic, nie zakladac. Ramie dostaje CALA SERIE (cztery notki pisze jedno wywolanie), los po numerze przebiegu
(`stages.ramie("dlugosc_serii", run_id)`), od 29.10 do 3.12.2026 (ok. 18 serii na ramie, ok. 70 notek):

- `on` — prosba o „usually 30-60 words, a guide and not a cap";
- `off` — jak dotad, „usually 50-110 words".

**Analiza po seriach**, nie po notkach: notki jednej serii nie sa niezalezne, a bootstrap po notkach dawalby przedzial za waski i falszywe
werdykty (test ma na to kontrdowod). Werdykt dopiero od 6 serii na ramie, przedzial 95%.

**Regula decyzji (3.12.2026):** `on` „lepiej" (dolny kraniec przedzialu > 1) -> krotka wskazowka staje sie domyslna; „gorzej" -> zostaje 50-110;
„brak dowodu" -> zostaje 50-110, a raport podaje najmniejszy wykrywalny efekt. Nic nie jest zmieniane w trakcie. Ramie jest w dzienniku
(`eksperymenty.dlugosc_serii`), wiec ocena nie wymaga zadnego dodatkowego zbierania.

## 4. Pole `fc` w dzienniku notek

`stages.skrot_weryfikacji` zapisuje przy kazdej wystawionej notce: liczbe twierdzen, ile obalonych / niepotwierdzonych, czy tekst naprawiono,
czy byly zastrzezenia, czy sprawdzenie nie doszlo do skutku. Od 27.10.2026. Sprawdzenie faktow przy publikacji nadal jest logiem i naprawa, nie
bramka — `fc` tylko pozwala policzyc, ile ono robi w praktyce (sekcja 6 raportu).

## 5. Artykul tygodnia z lekkiego stanu i rozkminy (zgoda wlasciciela 27.10.2026)

Do tej pory artykul ze sledztwa pisal tylko ciezki tor (poziom L/XL, ksiega pytan, rekordy pierwotne), a lekki tor i rozkmina, ktore chodza
codziennie, nie mialy jak go uniesc — tydzien szedl artykulem z puli. Teraz drugi stopien wyboru kandydata (`artykul_z_puli._kandydat_lekki`,
po `_kandydat_ze_sledztwa`, przed pula; wylacznik `config.ARTYKUL_Z_LEKKIEGO`):

1. **Stan** lekkiego sledztwa albo rozkminy z ostatnich 5 dni, produkcyjny (`--wyslij`, tryb nie-test), bez wczesniejszego artykulu, co najmniej
   dwa katy, co najmniej 10 potwierdzonych twierdzen z 5 serwisow. Teze dostaje najwyzej 4 najnowsze stany (jedno tanie wywolanie na stan, ok. 0,005 USD).
2. **Teza** (`sledztwo.teza_artykulu`, prompt `teza_artykulu.md`): jedno zdanie, NASZ pogląd, z numerami faktow ZA, PRZECIW, kontekstu, warunkiem
   pomylki i tytulem roboczym. **KOD wymaga** co najmniej trzech faktow ZA od co najmniej DWOCH NIEZALEZNYCH wydawcow
   (`sledztwo.wydawcy_niezalezni`), numerow z karty i warunku pomylki. Wydawca to domena rejestrowana, z wyjatkami po przegladzie nr 2: platformy
   wielu autorow (substack.com, github.io, medium.com, blogspot.com ... = pelny host), serwisy kont (github.com/org, x.com/konto; twitter = x),
   domeny jednego koncernu (google.com + blog.google + deepmind.google = jedno), agregatory (Yahoo Finance, feed Euronext) nie sa wydawca,
   glosy i wpisy cennika nie liczą sie, wszystkie twierdzenia interesowanej strony razem (VENDOR_CLAIM albo klasa PRIMARY spoza rejestrow) to jeden „aktor” — chyba ze jej domena niesie
   tez fakty neutralne w ocenianym zestawie (wtedy to ta sama strona i dostaje klucz domeny: FACT+VENDOR_CLAIM z jednego adresu to jeden wydawca),
   sekcje serwisow kont (huggingface.co/blog, github.com/features) to host, nie konto, rodziny obejmuja google.* / amazon.* / *.google, hosting amazonaws.com
   to pelny host, a wynik nie zalezy od kolejnosci faktow (dluzsze teksty porownywane pierwsze), a przedruk tego samego
   fragmentu pod innym hostem (85% slow mniejszego tekstu w wiekszym) liczy sie raz. Prompt drukuje przy kazdym fakcie TEN SAM klucz wydawcy,
   ktory liczy kod. Pusta teza modelu albo brak dwoch wydawcow = brak artykulu z tego
   stanu (uczciwe „w tym tygodniu nie ma co argumentowac"), wraca pula.
3. **Wybor:** rozkmina przed zwyklym sledztwem, potem liczba niezaleznych wydawcow pod teza, liczba faktow ZA, swiezosc.
4. **Karta dla pisarza zawezona do tezy** (`_zawez_do_tezy`): zostaja fakty ZA, PRZECIW i kontekst, liczby z ich zrodel, zastrzezenia WSKAZANE PRZEZ MODEL TEZY
   (pole `unsettled`, numery U1.. sprawdzane przez kod; filtr slow gubil wlasne i przepuszczal cudze), notki serii oparte na tych faktach i JEDNO
   przeczucie najblizsze tezie (jako „our guess, not a fact"). Pierwsza proba z cala karta
   rozlala artykul o czynszu za IPO Anthropic na PHP, Kimi i wybory — na pojedynczych zrodlach; zawezona karta dala artykul o jednej tezie z czterema
   wydawcami (Reuters przez Euronext, TechCrunch, WSJ, Futurism), sprzeciwem (retencja 900%), warunkiem pomylki i scenariuszami z nazwanymi zalozeniami.
   Prompt pisarza (`pisarz.md`) dostaje teze jako `investigation_finding` i pierwsza `editorial_hypotheses` z dowodami za, przeciw i „co obali".

Pytanie badania w karcie pisarza to sama teza; hipotezy badania, mechanizmy rownolegle (`parallel_mechanisms`), wynik sprawdzenia karty
(`sprawdzenie_karty`) i sciezka pliku nie przechodza, a daty zrodel (`source_dates`) sa liczone z twierdzen tezy (bez dat z przyszlosci; stare zrodla
dostaja uwage z kodu; gdy zaden fakt tezy nie ma daty, pole znika i artykul idzie bez stopki z data, a nie z datami cudzych historii). Zastrzezenia: model
widzi do 12 nieustalonych, 4 sprzecznosci i 6 watpliwosci karty. Przeglad nr 2 (27.10.2026, 4 kierunki +
sceptycy) potwierdzil 11 znalezisk, a przeglad nr 3 (poprawek, 48 agentow) kolejne 11 (m.in. firma rozbijana na „aktora” i domene, zaleznosc od kolejnosci
faktow, sekcje serwisow jako konta, dziury w rodzinach domen): 2 powazne (rozlew przez te pola i niezaleznosc liczona po domenie) i uwagi czytelnikow (przeczucie moglo stac na
samych uwagach; temat uwagi byl rozstrzygany kontekstem NASZEGO tekstu). Wszystkie naprawione, 25 mutantow zabitych.

Zmierzone na zywo (kopia danych, 27.10.2026): wybor tezy z trzech stanow 0,015 USD, artykul na Fable 0,48-0,75 USD (1700-2300 slow). Cadence bez zmian:
najwyzej jeden artykul na ~6 dni (`ile_artykulow`), wiec pierwszy artykul z rozkminy wypada we wtorek 3.11.2026 14:10 UTC (dzisiejszy 27.10 omija limit, bo
artykul z 25.10 jest sprzed dwoch dni).

## 5b. Uwagi czytelnikow jako ziarna przeczuc rozkminy

`sledztwo.uwagi_czytelnikow`: pula `pytania_czytelnikow.json` (zbierana od tygodni z odpowiedzi do nas, dotad tylko dla skauta bankowego) daje korpusowi
rozkminy do trzech najswiezszych tresciwych uwag (8-70 slow, 21 dni), z kanalu „czytelnik" i znacznikiem „nie fakt". Filtr: bez adresow, wzmianek,
cudzych polecen (`stages.bez_wstrzykniecia`), bez zaczepek do nas („co myslisz?", „probowales?"), bez uwag bez zwiazku z AI (skargi na platforme),
bez autorow; do pozycji idzie tylko kontekst („said under our post: ..."). Prompt wyboru przeczuc mowi, ze to tylko iskra: nie cytat, nie odpowiedz,
nie fakt, a przeczucie dalej wymaga co najmniej dwoch pozycji z roznych historii — sama uwaga go nie zalozy (kod liczy tylko pozycje spoza kanalu
„czytelnik": przeczucie bez dwoch takich pozycji odpada, a prog trzech pozycji rozkminy tez ich nie liczy). Temat uwagi rozstrzyga jej WLASNY tekst:
uwaga bez slowa o AI odpada nawet pod naszym tekstem o AI. Zmierzone na prawdziwej puli (28 wpisow):
przechodza 1-3 uwagi, wiec to sygnal rzadki, ale darmowy.

## 5c. Czego nie zrobiono (i dlaczego)

- **Podlaczenie czujnika do wyboru tematu:** dopiero po 3-4 tygodniach dziennika `co_klika.jsonl` (ekstrapolacja z danych, nie z intuicji).
- **Notka-zapowiedz artykulu z tezy:** artykul tygodnia ma juz swoje notki promujace (`typ` ARTYKUL); osobnej nie dodajemy.

## 5d. Czujnik „co klika” w praktyce (kontrola wieczorna 27.10.2026)

- **Kiedy pierwszy raz zywo.** Czujnik woła wylacznie korpus rozkminy, a brama rozkminy (`ROZKMINA_CO_DNI = 3`, okno liczone co do godziny) widziala
  reczna rozkmine 506 z 26.10 18:48 UTC, wiec zegarowa rozkmina 27.10 14:44 UTC wyszla kodem 1 przed jakimkolwiek wywolaniem modelu. Pierwsza zegarowa
  rozkmina (i pierwszy zapis `co_klika.jsonl`) wypada 30.10 ok. 14:45 UTC. Proba czujnika na katalogu tymczasowym (20 s, bez zapisu do `data/`):
  3 przebicia, pieciu nowych hostow czyta sie poprawnie (14-23 wpisy), po prostu bez swiezych przebic.
- **Etykieta kanalu.** Do 27.10 wieczorem nazwa kanalu brala pierwszy czlon adresu, wiec `newsletter.semianalysis.com`,
  `newsletter.maartengrootendorst.com` i `newsletter.pragmaticengineer.com` zlewaly sie w jeden kanal „Substack newsletter” (a `magazine.sebastianraschka.com`
  nazywal sie „magazine”); liczba roznych serwisow pod przeczuciem (`serwisy`) jest czescia jego wyniku. `sledztwo._nazwa_publikacji` bierze nazwe
  domeny (`semianalysis`), a dla `*.substack.com` pierwszy czlon; test pilnuje, ze zadne dwie publikacje z listy nie dziela nazwy.

- **Pisarz serii widzi sprzecznosci karty (audyt wieczorny).** Dwie z notek rozkminy z 26.10 mialy w kolejce teze, ktorej wlasna karta wprost przeczyla:
  szeroka baza klientow Anthropic (11 900 / 1 900 / 250) przeczy tezie o „waskim strumieniu renty” (506-1), a „profilowanie jest wiekszym ryzykiem”
  jest nieudowodnione (506-4) — ale pisarz serii dostawal z karty tylko `not_established`, nie `contradictions`. Teraz `sledztwo._nieustalone_do_serii` daje mu
  trzy listy z etykieta rodzaju (6 nieustalonych / 4 sprzecznosci „the evidence cuts against a claim or hunch” / 4 watpliwe, do 360 znakow), sekcja promptu
  nazywa sie „What our sources did not settle, or contradicted”, a regula 9 szablonow `seria_lekka.md` i `rozkmina_seria.md` mowi: dowod moze pokonac
  przeczucie — nalezy napisac, co mu przeczy, albo wziac inna mysl; nie wolno podawac sprzecznego jako przeslanki ani twierdzic mocniej niz zrodlo
  („reportedly”, „at least in part”). To prosba w prompcie, nie bramka (zgodnie z decyzja wlasciciela o notkach bez bramek tekstu); sprawdzenie faktow w
  sieci przy publikacji zostaje. **Czego ta zmiana NIE zalatwia:** (a) fakt, ktory pisarz juz widzial jako potwierdzony (Artificial Analysis: luka otwarte-vs-
  zamkniete 12 -> 3 pkt po wydaniu wag, 506-3), a mimo to napisal „wagi to wczorajsza wiadomosc” — to blad rozumowania, nie brak danych; (b) sprzecznosc
  z INNYM sledztwem lub z naszymi juz opublikowanymi notkami (506-2 „AI nie znalazlo bledu” przeczylo osi czasu Wiz z karty 499 i notce 499-1) —
  pisarz widzi tylko karte swojej historii i naglowki ostatnich notek, wiec to wymagaloby osobnego sprawdzenia z dziennikiem (kolejna decyzja, nie ta zmiana).
  Proba zywa na zapisanej karcie 506 (Flash, 0,007 USD): seria uzyla szerokiej bazy klientow zamiast tezy o „waskiej rencie”.
- **Reczna redakcja kolejki 27.10 15:38 UTC.** Pieciu oczekujacych notek (499-5, 506-1..4) nie dalo sie puscic: audyt 3 soczewkami (wiernosc, spojnosc z
  14 dniami opublikowanych, oznaczenie spekulacji) znalazl wzmocnione zrodla („known for years” zamiast „at least in part”, „mass” dopisane do cytatu
  Fundacji PHP, „deliberately”), wymyslonego „partnera”, analogie z patentami, teze o „waskim” strumieniu przy 250 / 1 900 / 11 900 klientach w tym samym
  zdaniu, i sprzecznosc 506-2 z naszymi opublikowanymi 499-1 i 499-4. Teksty przepisano recznie (zachowano glos i dlugosc), sprawdzilo je dwoch
  sceptykow na notke; oryginaly leza w polu `redakcja_reczna.oryginal` wpisu kolejki, kopia pliku w `data/przeslania.json.przed-redakcja-27-10`.

## 5e. Spojnosc notki serii z naszymi opublikowanymi (27.10.2026 wieczorem, zgoda wlasciciela: „ok niech tak bedzie”)

**Po co.** Notki serii leza w kolejce kilka dni, a pisarz widzi tylko karte swojego sledztwa. Sprawdzenie faktow szuka w SIECI, wiec tez nie widzi tego, co
w miedzyczasie wyszlo pod naszym nazwiskiem. 506-2 przeczyla opublikowanym 499-1 i 499-4 i zadna bramka tego nie mogla zlapac. Nowy modul
`agent-v2/spojnosc.py` pyta DZIENNIKA, w chwili publikacji, na aktualnym stanie. Wlaczone dla notek z przeslania (seria lekka, gleboki tor, rozkmina);
zwykle notki z banku i MYSL jej nie dostaja (`stages.note(sprawdz_spojnosc=...)`, ustawia `notki_dnia`). Przelacznik `config.SPOJNOSC_Z_DZIENNIKIEM`.

**Kolejnosc krokow, kazdy tanszy od nastepnego:**
1. **Kod** wybiera z dziennika z ostatnich 21 dni udane notki powiazane z nowa (wspolne slowa tresci, wspolna liczba liczy sie za dwa, prog 3), najwyzej 12;
   restacki, nieudane, duplikaty i ta sama tresc odpadaja. Dziennik czytany po `\n` i z `errors="replace"` (U+2028 w notce albo jeden zly bajt nie
   wylaczaja sprawdzenia). Brak kandydatow = ZERO wywolan modelu.
2. **Flash z myslenie** (`spojnosc`, wysilek `low`) wskazuje najwyzej 3 pary i CYTUJE obie strony. Odpowiedz bez listy `findings` to NIE „nic nie ma”, tylko brak
   odpowiedzi (`nie_sprawdzone`); pusta lista jest uczciwym `czysto`. Powtorzona para zajmuje jedno miejsce.
3. **Kod sprawdza cytaty doslownie** (wielkosc liter, cudzyslowy i spacje bez znaczenia, 3-40 slow). Cytat spoza tekstu zabija znalezisko PRZED platnym
   potwierdzeniem — model, ktory wymysli sprzecznosc, jest tu zlapany bez kosztu.
4. **Opus 5.5** (`spojnosc_potwierdz`) dostaje PELNE obie notki (bez uzasadnienia pierwszego czytelnika — zakotwiczenie), dzisiejsza date, material z jakiego
   powstala nowa notka (rekord) i — na poczatku — to, co sprawdzenie w sieci powiedzialo o niej przed chwila; ocenia CONTRADICTION / UPDATE / CONSISTENT oraz
   ktora strone popiera material (NEW / EARLIER / NEITHER). Fakt zmienny w czasie (liczba, cena, status) rozni sie od starszej notki = UPDATE, nie sprzecznosc.
   Odpowiedz o zlym ksztalcie (brak `pairs`, para bez oceny, numeracja od zera, werdykt spoza trzech) = brak odpowiedzi. Przy odmowie Opusa (klasyfikatory „cyber”,
   nasze historie bywaja o lukach), zlym JSON-ie, zlym ksztalcie albo awarii potwierdza Flash z myslenie (`spojnosc_potwierdz_zapas`); po PIERWSZEJ odmowie
   kolejne potwierdzenia tego przebiegu ida od razu do zapasu. Gdy zawiodly oba, stan to `nie_sprawdzone`, nigdy `czysto`.

**Co z wynikiem (nie jest bramka — decyzja wlasciciela, nic nie blokuje publikacji).**
- CONTRADICTION i material popiera wczesniejsza notke albo nie rozstrzyga → zarzut `refuted` „nasza wlasna notka z <data> mowi: ...” idzie do TEJ SAMEJ naprawy co
  obalony fakt (`stages.napraw_obalone`, jedna proba, wspolny sufit przebiegu, `naprawa.md`: popraw zdanie tak, zeby zgadzalo sie z tym, co juz wyszlo).
- **Tekst czysty w sieci nie moze zostac zamieniony na obalony.** `napraw_obalone` przyjmuje naprawe mimo nowych zarzutow z sieci, bo zaklada, ze oryginal byl
  obalony; przy samej sprzecznosci tak nie jest. Dlatego, gdy oryginal nie mial zarzutow z sieci, a siec obala naprawiony tekst albo nie dala rady go sprawdzic,
  naprawa jest ODRZUCONA i wychodzi oryginal (`fc.spojnosc.powod_odrzucenia`: `siec` / `siec_nie_sprawdzona`).
- Potem naprawiony tekst jest sprawdzany PONOWNIE wobec dziennika (Flash, Opus tylko jesli cos wskaze). Sprzecznosc stoi dalej i naprawa nie poprawiala faktu z sieci
  → naprawa ODRZUCONA (`powod_odrzucenia`: `dziennik`), wychodzi oryginal. Poprawiala tez obalony fakt z sieci → zostaje (falsz z sieci jest gorszy), a zapis mowi, ze
  sprzecznosc stoi.
- CONTRADICTION, ale REKORD popiera NOWA notke → bez naprawy (nie przepisujemy tekstu wbrew zrodlom), tylko zapis `nowa_lepsza`. To bylaby kandydatka do
  sprostowania wczesniejszej notki — swiadomie poza ta zmiana.
- UPDATE i CONSISTENT → `czysto`.

**Zapis.** `fc.spojnosc` w dzienniku notek serii: `stan` (wylaczone / brak_kandydatow / czysto / nowa_lepsza / sprzecznosc / nie_sprawdzone), liczba kandydatow,
znalezisk i sprzecznosci, `naprawiona`, `stoi`, `naprawa_odrzucona`, `powod_odrzucenia`, kto potwierdzil oraz — gdy cos znaleziono — `szczegoly` (do trzech cytatow
po 160 znakow: co sie zderzylo, z notka z jakiego dnia, i czy materialem wygral nowy czy stary). `fc.obalonych` zostaje miara FAKTOW z sieci, a `fc.naprawiona` NIE
liczy naprawy samej sprzecznosci (ta ma `fc.spojnosc.naprawiona`) — `co_dziala` liczy „naprawionych” jako podzbior „z obalonym”.

**Koszt (oszacowany z ksiegi, NIE zmierzony na produkcji — pierwsze przebiegi dadza liczby).** Flash z myslenie (`low`; domyslna glebokosc to 10-26 tys. tokenow
wyjscia, `low` ok. polowy) rzedu 0,003-0,01 USD na sprawdzenie; Opus 5.5 ok. 0,05 USD tylko gdy cytaty przejda krok 3. Najgorszy przypadek na jedna notke (cytaty OK,
Opus odmawia, naprawa, ponowne sprawdzenia): ok. 9 platnych wywolan, z czego tylko Flash i jedna naprawa to realny koszt, a odmowy Opusa ksieguja sie po 0 USD.
Do 90 notek serii miesiecznie: rzad 0,3-1 USD (Flash) plus Opus przy kilku przypadkach. Etapy ida do grupy kosztu „sprawdzenie faktow i naprawa” w `co_dziala`.

**Czego to NIE lapie.** (a) Bledu rozumowania w obrebie jednej notki (prawdziwe fakty, zly wniosek — 506-3). (b) Sprzecznosci z notka spoza okna kandydatow
(starszej niz 21 dni albo o innym temacie slowami; prog to wspolne slowa i liczby, nie znaczenie). (c) Sprzecznosci z naszymi ARTYKULAMI (dziennik trzyma tylko
tytul). (d) Sprzecznosci miedzy dwiema notkami z tej samej, jeszcze niewydanej serii — pierwsza wydana staje sie punktem odniesienia dla nastepnych. (e) Gdy
nowa notka ma racje, a wczesniejsza byla bledna — tylko zapis, bez sprostowania. (f) Naprawa SAMEGO faktu z sieci (bez sprzecznosci w oryginale) nie jest
ponownie porownywana z dziennikiem, wiec `fc.spojnosc.stan` opisuje tekst sprzed tej naprawy. (g) Ponowne sprawdzenie po naprawie to swieze, losowe wykrycie:
potwierdzona KAZDA pozostala sprzecznosc (takze inna niz pierwotna) odrzuca naprawe, co moze zostawic oryginal ze sprzecznoscia — skutek lagodny (to samo, co brak sprawdzenia).

**Testy.** `tests/test_spojnosc.py` (135 asercji, bez sieci), 99 mutantow (`robocze/mutacje_spojnosc.py`, poza repozytorium): 98 zabitych, 1 rownowazny (jawne sprawdzenie
„`pairs` jest lista” dubluje „kazda para ma ocene”). Przeglad niezalezny 27.10 (6 kierunkow, 34 znaleziska, 16 zweryfikowanych sceptykami) znalazl m.in. odpowiedzi o zlym
ksztalcie liczone jako `czysto`, naprawe przyjmowana mimo ze siec obala nowy tekst, czerwony `tests/test_glos_i_routing.py` i zaniezony koszt myslenia Flasha — wszystko poprawione.

## 6. Pliki

- `agent-v2/zaklady.py`, `agent-v2/co_dziala.py`; prompty `agent-v2/prompts/zaklady_*.md`; budowniczowie w `stages.py`
  (`prompt_zakladow_wyciag`, `prompt_zakladu_sprawdzenia`, `prompt_zakladu_notki`); stale w `config.py` (`ZAKLADY_*`, `DLUGOSC_SERII`).
- Testy: `tests/test_zaklady.py` (54), `tests/test_co_dziala.py` (42), E22 i `fc` w `tests/test_seria_lekka.py` (sekcje 7-8) i
  `tests/test_notki_sledcze.py`.
- Proby na kopii danych: `robocze/zaklady_proba.py`, `robocze/zaklady_proba2.py` (nie w repozytorium).
