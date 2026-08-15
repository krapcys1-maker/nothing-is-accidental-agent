> **ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.**
> Dokument historyczny (zarchiwizowany 2026-07-12). Obowiazuja wylacznie: MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md (korzen repozytorium) oraz rejestr decyzji docs/DECISIONS.md.

> **SUPERSEDED**
>
> Ten dokument zawiera historyczne założenia projektu.
>
> Zapis o obowiązkowym publicznym ujawnianiu AI nie obowiązuje.
>
> Aktualne źródło prawdy:
> - ADR-018
> - docs/IMPLEMENTATION_PLAN.md
> - docs/DECISIONS.md
>
> Nie wolno używać propozycji bio ani publicznych komunikatów z tego dokumentu.

# MASTER PLAN: agent prowadzący Substack „Nothing Is Accidental”

## Status dokumentu

Ten dokument łączy:

* koncepcję osobnego Substacka prowadzonego przez agenta AI,
* temat publikacji „Nic nie jest przypadkowe” / „Nothing Is Accidental”,
* założenia dotyczące autonomii, researchu, pisania, grafik i interakcji,
* wnioski z porównania dużych i małych publikacji na Substacku,
* strategię maksymalizacji popularności bez spamu i sztucznego pompowania liczb,
* plan 30-dniowego eksperymentu,
* metryki, zasady bezpieczeństwa i gotowe instrukcje dla agenta.

Dokument ma być nadrzędnym planem projektu. W razie konfliktu między szybkością wzrostu a jakością, bezpieczeństwem lub wiarygodnością — wygrywa jakość, bezpieczeństwo i wiarygodność.

\---

# 1\. Cel projektu

Celem jest zbudowanie półautonomicznego agenta AI, który przez co najmniej 30 dni prowadzi osobną publikację na Substacku i próbuje zdobyć możliwie dużą liczbę realnych, zaangażowanych czytelników.

Agent ma:

* znajdować tematy,
* prowadzić research,
* sprawdzać źródła,
* pisać artykuły,
* pisać Notes,
* tworzyć grafiki,
* wyszukiwać autorów i publikacje do interakcji,
* przygotowywać komentarze,
* proponować restacki i rekomendacje,
* analizować statystyki,
* prowadzić dziennik decyzji, błędów i kosztów,
* zmieniać strategię na podstawie danych.

Publikacja nie ma udawać konta prowadzonego przez człowieka. Powinna jasno informować, że jest eksperymentem tworzonym przez agenta AI pod nadzorem człowieka.

Główne pytanie eksperymentu:

> Czy agent AI, mając jasny temat, ograniczony budżet, zasady jakości i dostęp do mechanizmów dystrybucji Substacka, potrafi od zera zbudować publikację, którą ludzie naprawdę chcą czytać i polecać?

\---

# 2\. Prawdziwy cel wzrostu

Agent nie optymalizuje:

* liczby opublikowanych tekstów,
* liczby komentarzy,
* liczby obserwowanych kont,
* samej liczby wyświetleń,
* samej częstotliwości publikacji.

Agent optymalizuje:

* liczbę nowych realnych subskrybentów,
* konwersję wejścia na profil w subskrypcję,
* liczbę powracających czytelników,
* średnią jakość zaangażowania,
* liczbę restacków,
* liczbę rekomendacji od innych autorów,
* liczbę czytelników, którzy otwierają kolejne teksty,
* koszt zdobycia jednego subskrybenta,
* czas człowieka potrzebny do utrzymania jakości.

Główna funkcja celu:

> Maksymalizuj liczbę prawdziwych, zaangażowanych subskrybentów, którzy rozumieją obietnicę publikacji, otwierają kolejne teksty i dobrowolnie polecają je innym. Nie używaj spamu, fałszywych relacji, udawanych doświadczeń, masowych komentarzy, clickbaitu ani wprowadzających w błąd tytułów.

\---

# 3\. Najważniejsze wnioski z researchu o wzroście na Substacku

## 3.1. Duże publikacje rozwiązują jeden rozpoznawalny problem

Największe publikacje zwykle nie opisują szerokiej kategorii typu:

> AI, technologia, biznes i przyszłość.

Mówią czytelnikowi, co konkretnie dla niego zrobią.

Przykładowy wzorzec:

* pomogę ci lepiej budować produkty,
* pokażę, jak naprawdę działa branża technologiczna,
* wyjaśnię wpływ AI na pracę i edukację,
* rozłożę na części techniczne mechanizmy, których media nie tłumaczą.

Agent musi traktować publikację jak „job to be done” dla odbiorcy.

## 3.2. Ogólne porady przegrywają z materiałem, którego nie da się wygenerować jednym promptem

Małe konta często publikują treści typu:

* 5 sposobów na lepszą produktywność,
* 7 trendów, które zmienią świat,
* 10 rzeczy, które warto wiedzieć.

Duże publikacje częściej pokazują:

* własny test,
* konkretny mechanizm,
* dane,
* eksperyment,
* prawdziwe błędy,
* zmianę zdania,
* wynik, którego autor się nie spodziewał,
* wiedzę branżową lub niedostępny gdzie indziej kontekst.

Dla „Nothing Is Accidental” odpowiednikiem unikalnego materiału ma być:

* głębokie rozłożenie zwykłego zjawiska na system,
* połączenie kilku źródeł i mechanizmów,
* pokazanie konfliktu interesów, logistyki, ograniczeń i kompromisów,
* grafika pokazująca mechanizm,
* jasna odpowiedź na pytanie „dlaczego to działa właśnie tak?”.

## 3.3. Samo pisanie nie wystarcza

Wzrost na Substacku nie wynika wyłącznie z jakości artykułów.

Silniki wzrostu to:

* artykuły wysyłane e-mailem,
* Notes,
* komentarze,
* restacki,
* Recommendations,
* współprace z innymi autorami,
* social media,
* wyszukiwarka,
* polecenia czytelników,
* gościnne publikacje.

Mały newsletter często ma tylko pierwszy element. Agent musi działać w kilku kanałach jednocześnie.

## 3.4. Ogólne Notes mogą dostawać reakcje, ale nie dawać subskrypcji

Anegdotyczne case studies pokazują, że regularne publikowanie ogólnych porad może dawać polubienia bez realnego wzrostu.

Lepsze są Notes oparte na:

* historii odkrycia,
* zmianie opinii,
* błędzie,
* konkretnym teście,
* sprzeczności,
* zaskakującym mechanizmie,
* jednej liczbie i jej konsekwencji,
* obserwacji, której nie da się zamienić na generyczną poradę.

## 3.5. Duże konta często miały przewagę startową

Wiele dużych publikacji miało wcześniej:

* publiczność na Twitterze, LinkedInie lub blogu,
* znane nazwisko,
* doświadczenie zawodowe,
* sieć kontaktów,
* rozpoznawalną specjalizację,
* kilka lat regularnego publikowania.

Dlatego nie wolno mierzyć jakości nowego konta przez porównanie z milionowymi publikacjami po jednym tygodniu.

## 3.6. Efekt kumulacji jest realny

Wzrost bywa bardzo wolny na początku, a później przyspiesza, gdy pojawiają się:

* archiwum dobrych tekstów,
* rozpoznawalna obietnica,
* polecenia,
* relacje z autorami,
* powracający czytelnicy,
* systematyczne Notes,
* coraz więcej punktów wejścia na profil.

Pierwszy miesiąc ma zbudować fundament, nie udowodnić, że agent potrafi zdobyć milion odbiorców.

\---

# 4\. Temat publikacji

## Robocza nazwa

**Nothing Is Accidental**

Polski odpowiednik:

**Nic nie jest przypadkowe**

## Główna obietnica

> The hidden systems, decisions and incentives behind ordinary things.

Po polsku:

> Ukryte systemy, decyzje i interesy stojące za zwykłymi rzeczami.

## Job to be done

Publikacja ma wykonywać dla czytelnika jedno rozpoznawalne zadanie:

> Bierze zwykłą rzecz, usługę, miejsce albo zachowanie i pokazuje, jakie mechanizmy, ograniczenia i decyzje sprawiają, że działa właśnie tak.

## Dlaczego ten temat jest dobry dla agenta

* nie wymaga udawania osobistych doświadczeń,
* daje się researchować z publicznych źródeł,
* jest szeroki, ale ma jasny wspólny rdzeń,
* nadaje się do grafik,
* działa w formacie artykułów i Notes,
* może zainteresować odbiorców nauki, technologii, designu, ekonomii i kultury,
* nie jest kolejnym newsletterem o AI,
* sam eksperyment z agentem pozostaje ciekawy, mimo że treść publikacji nie dotyczy AI.

\---

# 5\. Docelowy odbiorca

Czytelnik:

* jest ciekawy świata,
* lubi rozumieć systemy,
* chce wiedzieć, dlaczego zwykłe rzeczy działają tak, jak działają,
* ceni krótkie, konkretne wyjaśnienia,
* nie chce akademickiego żargonu,
* nie chce generycznych porad,
* lubi połączenie nauki, historii, technologii, designu i ekonomii.

Publikacja nie jest dla:

* osób szukających codziennych wiadomości,
* osób oczekujących porad inwestycyjnych,
* osób szukających porad medycznych,
* osób chcących wyłącznie list typu „10 faktów”.

\---

# 6\. Pozycjonowanie profilu

##

## Opis publikacji

> Why do airline tickets change price every few hours? Why does a supermarket lead you through a particular route? What happens to your suitcase after check-in?
>
> Nothing Is Accidental breaks ordinary systems into parts and shows the decisions, incentives and constraints hidden underneath.
>
> This is an experiment: researched and drafted by an AI agent, supervised by a human editor. The costs, mistakes and results will be documented publicly.

## Zasada pięciu sekund

Osoba wchodząca na profil ma w pięć sekund zrozumieć:

* o czym jest publikacja,
* czego się dowie,
* dlaczego warto ją śledzić,
* że jest to eksperyment z agentem AI,
* jak często pojawiają się nowe materiały.

\---

# 7\. Kategorie tematyczne

## Główne

* ukryte mechanizmy usług,
* ekonomia codzienności,
* logistyka,
* miasta i transport,
* handel i projektowanie sklepów,
* historia zwykłych przedmiotów,
* technologia codzienna,
* psychologia zachowań konsumentów,
* systemy organizujące codzienne życie.

## Wykluczone

Agent nie publikuje porad dotyczących:

* zdrowia,
* leczenia,
* prawa,
* inwestycji,
* polityki,
* psychoterapii,
* bezpieczeństwa osobistego,
* osobistych doświadczeń, których nie posiada.

\---

# 8\. Przykładowe tematy

* Why airline ticket prices change every few hours
* What really happens to your suitcase after check-in
* Why supermarkets put essentials at the back
* Why cancelling a subscription is harder than starting one
* Why hotel rooms skip certain floor numbers
* Why restaurants deliberately shorten their menus
* Why queues slow down even when more counters open
* Why cities plant the same tree species again and again
* Why elevators close their doors the way they do
* Why keyboards still use QWERTY
* Why hotel beds have so many pillows
* Why store layouts seem to guide your body
* Why product packaging is often larger than necessary
* Why food delivery apps change prices by location and time
* Why airports make you walk through duty-free shops
* Why cinema popcorn costs more than the ticket margin suggests
* Why return policies are designed differently from purchase flows
* Why shopping carts are shaped the way they are
* Why some buildings have fake windows or decorative doors
* Why public benches are designed to prevent certain uses

\---

# 9\. System wyboru tematów

Agent codziennie zbiera 10–20 pomysłów i ocenia je od 0 do 100.

## Scoring

* natychmiastowa ciekawość: 25 pkt,
* uniwersalność: 15 pkt,
* jakość dostępnych źródeł: 20 pkt,
* nieoczywista odpowiedź: 15 pkt,
* potencjał wizualny: 10 pkt,
* potencjał do dyskusji: 10 pkt,
* oryginalność względem archiwum: 5 pkt.

Publikować:

* artykuły od 75/100,
* Notes od 65/100,
* eksperymentalne tematy 60–74/100 tylko po zatwierdzeniu człowieka.

## Odrzucać

* tematy zbyt ogólne,
* tematy bez wiarygodnych źródeł,
* tematy wymagające udawanych doświadczeń,
* tematy identyczne z niedawnymi publikacjami,
* tematy, których odpowiedź jest banalna,
* tematy o wysokim ryzyku błędu lub szkody.

\---

# 10\. Standard researchu

Agent:

1. Preferuje źródła pierwotne.
2. Sprawdza datę publikacji i okres danych.
3. Odróżnia fakt od interpretacji.
4. Nie dopisuje brakujących szczegółów.
5. Zapisuje listę wykorzystanych źródeł.
6. Oznacza niepewność.
7. W miarę możliwości potwierdza ważne twierdzenia drugim niezależnym źródłem.
8. Nie używa danych, które nie mają kontekstu.
9. Nie przedstawia korelacji jako przyczynowości.
10. Nie przedstawia anegdoty jako reguły.

## Karta researchu

Każdy artykuł powinien mieć wewnętrzną kartę:

* pytanie,
* główna teza,
* najważniejszy mechanizm,
* 3–8 źródeł,
* twierdzenia potwierdzone,
* twierdzenia niepewne,
* kontrargument,
* ryzyko błędu,
* sugerowana grafika.

\---

# 11\. Format artykułu

## Częstotliwość

* 1 pełny artykuł tygodniowo,
* 4–6 artykułów w pierwszych 30 dniach,
* stały dzień publikacji.

## Długość

* 900–1500 słów,
* dłużej tylko wtedy, gdy temat naprawdę tego wymaga.

## Struktura

* jedno mocne pytanie,
* konkretne otwarcie,
* mechanizm,
* dowody,
* kontrargument lub ograniczenie,
* konsekwencja,
* bez automatycznego podsumowania.

## Zakaz

* generyczne wstępy,
* artykuły typu „10 rzeczy” bez silnego powodu,
* clickbait bez pokrycia,
* udawane doświadczenia,
* streszczanie tego, co można znaleźć w pierwszym wyniku Google.

\---

# 12\. Strategia Notes

## Cel

Notes mają:

* budować rozpoznawalność,
* pokazywać sposób myślenia publikacji,
* dawać samodzielną wartość,
* przyciągać właściwych czytelników,
* tworzyć punkty wejścia do profilu.

## Częstotliwość

* 1–2 Notes dziennie,
* 45–60 w pierwszych 30 dniach.

## Proporcje

* 40% oryginalne Notes,
* 25% odpowiedzi i komentarze,
* 20% restacki z własną myślą,
* 10% fragmenty własnych artykułów,
* 5% bezpośrednia promocja.

## Dobre typy Notes

* jeden mechanizm,
* jedna liczba i jej konsekwencja,
* krótka sprzeczność,
* ciekawostka z researchu,
* mini-case,
* zmiana interpretacji,
* nieoczywisty powód,
* pytanie, które prowadzi do dyskusji.

## Złe typy Notes

* puste motywacyjne hasła,
* generyczne porady,
* seria linków do własnych tekstów,
* sztuczne pytania pod zaangażowanie,
* przepisywanie artykułu na kilka prawie identycznych postów.

\---

# 13\. Strategia komentarzy

## Zasada

Komentarz ma być tak dobry, żeby człowiek wszedł na profil z ciekawości, a nie dlatego, że został poproszony o kliknięcie.

## Dzienny workflow

Agent:

1. Przegląda około 30 kandydatów.
2. Ocenia miejsca do komentowania.
3. Przygotowuje 3–5 najlepszych komentarzy.
4. Pokazuje je człowiekowi.
5. Publikuje dopiero po zatwierdzeniu.

## Scoring miejsca do komentarza

* zgodność odbiorców: 25 pkt,
* możliwość wniesienia własnej myśli: 25 pkt,
* świeżość posta: 15 pkt,
* aktywność dyskusji: 15 pkt,
* jakość autora: 10 pkt,
* naturalne powiązanie z własnym tekstem: 10 pkt.

Komentować od 70/100.

## Limity

* 3–5 komentarzy dziennie,
* maksymalnie 1 komentarz u tego samego autora dziennie,
* link do własnego tekstu w maksymalnie 5–10% komentarzy,
* zero identycznych komentarzy,
* zero „great post”,
* zero „check my profile”,
* zero automatycznej publikacji bez akceptacji.

\---

# 14\. Restacki i Recommendations

## Restack

Agent powinien:

* restackować tylko treści naprawdę pasujące do publikacji,
* zawsze dodać własną obserwację,
* unikać samego udostępnienia bez kontekstu,
* używać restacków do budowania relacji i selekcji dobrych materiałów.

Cel miesięczny:

* 12–20 restacków z komentarzem.

## Recommendations

Agent:

1. Buduje listę 30–50 podobnych publikacji.
2. Wybiera 5–10 najlepszych.
3. Czyta je regularnie.
4. Interaguje z nimi.
5. Poleca tylko wtedy, gdy publikacja naprawdę pasuje.
6. Po zbudowaniu relacji może przygotować propozycję wzajemnej rekomendacji.

Zakaz:

* „polecę ciebie, jeśli polecisz mnie” jako pierwsza wiadomość,
* masowe wysyłanie propozycji,
* rekomendacje przypadkowych dużych kont tylko dla zasięgu.

\---

# 15\. Start publikacji

Nie uruchamiać publicznie pustego konta z jednym artykułem.

## Przed premierą przygotować

* 3 pełne artykuły,
* 10–14 Notes,
* stronę powitalną,
* mail powitalny,
* logo,
* szablon grafik,
* bazę 50 podobnych autorów,
* 20 tematów na kolejne teksty,
* 5 rekomendacji,
* przypięty najlepszy materiał.

## Pierwszy tydzień

### Dzień 1

* manifest publikacji,
* 2 Notes,
* 3 komentarze.

### Dzień 2

* Note z ciekawostką,
* 3–5 komentarzy,
* 1 restack.

### Dzień 3

* drugi artykuł,
* Note z najmocniejszą obserwacją.

### Dzień 4

* restack cudzego tekstu,
* 3 komentarze,
* analiza pierwszych wejść.

### Dzień 5

* Note z pytaniem,
* poprawa profilu na podstawie danych.

### Dzień 6

* trzeci artykuł lub materiał wizualny,
* 1–2 Notes.

### Dzień 7

* raport tygodniowy,
* korekta strategii.

\---

# 16\. Grafiki

## Cel

Grafika ma:

* zatrzymać wzrok,
* pokazać mechanizm,
* budować rozpoznawalny styl,
* nie być przypadkową dekoracją.

## Styl

* clean cinematic editorial,
* inteligentny,
* lekko tajemniczy,
* realistyczne detale,
* jeden centralny obiekt,
* brak tekstu,
* brak logotypów,
* brak stockowego wyglądu,
* brak robotów i mózgów AI.

## Workflow

1. Agent wyciąga główną ideę artykułu.
2. Tworzy 2–3 koncepcje.
3. Wybiera najlepszą.
4. Generuje maksymalnie 2 warianty.
5. Sprawdza błędy.
6. Przekazuje człowiekowi do akceptacji.
7. Tworzy tekst alternatywny.

\---

# 17\. Poziom autonomii

## Agent robi sam

* wyszukiwanie tematów,
* research,
* przygotowanie szkiców,
* Notes,
* propozycje komentarzy,
* propozycje grafik,
* zbieranie statystyk,
* raporty,
* propozycje strategii.

## Człowiek zatwierdza

* każdy artykuł,
* każdy komentarz,
* każdą grafikę,
* wiadomości do autorów,
* rekomendacje,
* zmianę strategii,
* zmianę zakresu tematycznego,
* publikacje wysokiego ryzyka.

## Potencjalna późniejsza automatyzacja

Po 2–3 tygodniach stabilnej jakości:

* publikowanie części Notes,
* automatyczne planowanie,
* automatyczne raporty,
* automatyczne zbieranie statystyk.

Komentarze i prywatne wiadomości nadal wymagają zatwierdzenia człowieka.

\---

# 18\. System metryk

## Growth Score

```text
Growth Score =
40% nowych subskrybentów
+ 20% konwersji profil → subskrypcja
+ 15% powracających czytelników
+ 10% komentarzy i reakcji
+ 10% restacków
+ 5% nowych rekomendacji
```

## Dodatkowe metryki

* koszt jednego subskrybenta,
* koszt jednego artykułu,
* czas człowieka dziennie,
* procent treści zaakceptowanych bez zmian,
* liczba błędów faktograficznych,
* liczba odrzuconych komentarzy,
* liczba wejść na profil z komentarzy,
* liczba subskrypcji z Notes,
* liczba subskrypcji z Recommendations,
* średnia liczba powrotów czytelnika.

## Raport tygodniowy

Agent odpowiada:

* które 3 tematy działały najlepiej,
* które Notes konwertowały najlepiej,
* którzy autorzy skierowali ruch,
* które komentarze wywołały wejścia,
* które grafiki działały najlepiej,
* ile kosztowało API,
* ile czasu poświęcił człowiek,
* co zwiększyć,
* co ograniczyć,
* jakie trzy eksperymenty zrobić w kolejnym tygodniu.

\---

# 19\. Testy i eksperymenty

Agent może testować:

* dwa style tytułów,
* różne godziny Notes,
* różne długości komentarzy,
* grafika vs brak grafiki,
* pytanie vs teza w Note,
* publikacja rano vs wieczorem,
* jeden artykuł tygodniowo vs dwa,
* krótkie vs długie Notes,
* różne kategorie tematyczne.

Zasady:

* jedna zmienna naraz,
* minimum tydzień danych,
* nie wyciągać wniosków z pojedynczego posta,
* nie optymalizować pod samą liczbę wyświetleń.

\---

# 20\. Realistyczne cele na 30 dni

## Aktywność

* 4–6 artykułów,
* 45–60 Notes,
* 70–100 komentarzy,
* 12–20 restacków,
* 10–15 realnych relacji z autorami,
* 5–10 rekomendowanych publikacji,
* maksymalnie 3–5 propozycji współpracy.

## Wynik

Nie ustawiać sztucznego celu „1000 subskrybentów”.

Realistyczny cel eksperymentalny:

* 30–100 realnych subskrybentów,
* mierzalna konwersja z Notes i komentarzy,
* przynajmniej kilka powracających czytelników,
* co najmniej 1–3 relacje z autorami prowadzące do dalszej współpracy,
* jasna odpowiedź, które mechanizmy wzrostu działają.

\---

# 21\. Budżet

## Miesięczny

* Substack: 0 USD,
* model językowy: 8–20 USD,
* research: 3–10 USD,
* grafiki: 3–15 USD,
* VPS: 0–10 USD,
* domena: opcjonalnie 10–15 USD rocznie.

## Limit

> Maksymalnie 30–40 USD miesięcznie na modele, research i grafiki.

Cały test:

> około 20–55 USD za 30 dni, bez liczenia czasu budowy.

\---

# 22\. Architektura techniczna

## Moduły

1. Topic Finder
2. Topic Scorer
3. Source Collector
4. Research Verifier
5. Article Writer
6. Note Writer
7. Comment Writer
8. Restack Assistant
9. Recommendation Manager
10. Image Prompt Builder
11. Image Generator
12. Approval Panel
13. Browser Automation
14. Analytics Collector
15. Growth Optimizer
16. Cost Tracker
17. Experiment Journal
18. Safety Layer

## Dane

* tematy,
* źródła,
* artykuły,
* Notes,
* komentarze,
* autorzy,
* rekomendacje,
* relacje,
* grafiki,
* statystyki,
* koszty,
* błędy,
* poprawki człowieka,
* decyzje strategiczne.

## Technologia

* Python,
* Playwright,
* SQLite,
* prosty lokalny panel,
* API modelu językowego,
* API grafiki,
* harmonogram lokalny lub VPS.

\---

# 23\. Zasady bezpieczeństwa

Agent nigdy nie:

* podszywa się pod człowieka,
* wymyśla doświadczeń,
* wymyśla źródeł,
* publikuje masowo,
* wysyła automatycznych wiadomości prywatnych,
* spamuje linkami,
* kupuje subskrybentów,
* uczestniczy w „sub za sub”,
* tworzy fałszywych relacji,
* kopiuje cudzych tekstów,
* używa clickbaitu bez pokrycia,
* ukrywa, że konto jest eksperymentem AI,
* komentuje bez związku z treścią.

\---

# 24\. Główne reguły decyzyjne agenta

1. Najpierw wartość, potem dystrybucja.
2. Najpierw dopasowanie, potem liczba interakcji.
3. Jedna mocna teza jest lepsza niż pięć ogólnych porad.
4. Własny mechanizm jest lepszy niż streszczenie internetu.
5. Komentarz ma wnosić coś nowego.
6. Rekomendacja ma być prawdziwa.
7. Grafika ma wyjaśniać.
8. Dane z jednego dnia nie zmieniają strategii.
9. Wzrost kosztem reputacji jest porażką.
10. Popularność ma wynikać z użyteczności i ciekawości, nie z automatycznej obecności wszędzie.

\---

# 25\. Gotowa instrukcja systemowa dla agenta wzrostu

```text
Jesteś półautonomicznym redaktorem, researcherem i strategiem wzrostu publikacji Substack „Nothing Is Accidental”.

Twoim celem jest maksymalizowanie liczby realnych, zaangażowanych subskrybentów, którzy rozumieją obietnicę publikacji, otwierają kolejne teksty i dobrowolnie polecają je innym.

Publikacja wyjaśnia ukryte systemy, decyzje, interesy i ograniczenia stojące za zwykłymi rzeczami, usługami, miejscami i zachowaniami.

Nie optymalizuj samej liczby publikacji, komentarzy ani wyświetleń. Optymalizuj:
- nowe subskrypcje,
- konwersję profil → subskrypcja,
- powracających czytelników,
- restacki,
- rekomendacje,
- jakościowe komentarze,
- koszt pozyskania czytelnika,
- czas człowieka potrzebny do kontroli.

Nie używaj:
- spamu,
- clickbaitu bez pokrycia,
- fałszywych doświadczeń,
- wymyślonych źródeł,
- masowych komentarzy,
- „sub za sub”,
- agresywnej autopromocji,
- podszywania się pod człowieka.

Każdy artykuł musi:
- odpowiadać na jedno konkretne pytanie,
- mieć jasną tezę,
- opierać się na zweryfikowanych źródłach,
- pokazywać mechanizm,
- wnosić coś więcej niż streszczenie publicznych informacji,
- zawierać uczciwe ograniczenie lub kontrargument,
- kończyć się konsekwencją, nie podsumowaniem.

Każda Note musi:
- działać samodzielnie,
- zawierać jedną konkretną obserwację,
- nie być wyłącznie reklamą artykułu,
- nie być generyczną poradą.

Każdy komentarz musi:
- odnosić się do konkretnej myśli autora,
- wnosić dodatkowy mechanizm, przykład lub kontrargument,
- być krótki i naturalny,
- nie zapraszać wprost na profil,
- nie zawierać linku, chyba że jest naprawdę potrzebny.

Przed publikacją:
1. oceń temat,
2. sprawdź źródła,
3. napisz szkic,
4. wykonaj krytyczny audyt,
5. przygotuj grafikę,
6. przekaż człowiekowi do zatwierdzenia.

Raz dziennie zbieraj dane.
Raz w tygodniu przygotuj raport:
- co działało,
- co nie działało,
- skąd przyszli nowi czytelnicy,
- jakie tematy konwertowały,
- jakie interakcje przyniosły wejścia,
- jaki był koszt,
- jakie 3 eksperymenty przeprowadzić dalej.

Nigdy nie publikuj komentarzy, prywatnych wiadomości, rekomendacji ani pełnych artykułów bez zatwierdzenia człowieka.
```

\---

# 26\. Końcowa teza projektu

Największa różnica między małą a dużą publikacją nie brzmi:

> Duża publikacja pisze lepiej.

Brzmi:

> Duża publikacja ma jasną obietnicę, unikalny materiał i system, który wielokrotnie pokazuje ten materiał właściwym ludziom.

Agent ma zbudować właśnie ten system — bez zamieniania publikacji w spamujący automat.
