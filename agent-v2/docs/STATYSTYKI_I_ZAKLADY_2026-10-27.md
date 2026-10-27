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
   glosy i wpisy cennika nie liczą sie, wszystkie twierdzenia interesowanej strony (VENDOR_CLAIM) razem to jeden „aktor", a przedruk tego samego
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
(`sprawdzenie_karty`) i sciezka pliku nie przechodza, a daty zrodel (`source_dates`) sa liczone z twierdzen tezy. Przeglad nr 2 (27.10.2026, 4 kierunki +
sceptycy) potwierdzil 11 znalezisk: 2 powazne (rozlew przez te pola i niezaleznosc liczona po domenie) i uwagi czytelnikow (przeczucie moglo stac na
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

## 6. Pliki

- `agent-v2/zaklady.py`, `agent-v2/co_dziala.py`; prompty `agent-v2/prompts/zaklady_*.md`; budowniczowie w `stages.py`
  (`prompt_zakladow_wyciag`, `prompt_zakladu_sprawdzenia`, `prompt_zakladu_notki`); stale w `config.py` (`ZAKLADY_*`, `DLUGOSC_SERII`).
- Testy: `tests/test_zaklady.py` (54), `tests/test_co_dziala.py` (42), E22 i `fc` w `tests/test_seria_lekka.py` (sekcje 7-8) i
  `tests/test_notki_sledcze.py`.
- Proby na kopii danych: `robocze/zaklady_proba.py`, `robocze/zaklady_proba2.py` (nie w repozytorium).
