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

# Projekt: autonomiczny Substack prowadzony przez agenta AI

## 1. Cel eksperymentu

Celem projektu jest stworzenie osobnego konta na Substacku, które przez 30 dni będzie prowadzone przez agenta AI pod nadzorem człowieka.

Agent ma:

- samodzielnie wybierać tematy,
- prowadzić research,
- pisać artykuły i Notes,
- generować grafiki,
- wyszukiwać autorów i publikacje do interakcji,
- przygotowywać komentarze,
- analizować wyniki,
- zmieniać strategię na podstawie danych,
- dokumentować wszystkie decyzje, koszty, błędy i poprawki.

Eksperyment ma odpowiedzieć na pytanie:

> Czy agent AI potrafi od zera zbudować i prowadzić wartościową publikację na Substacku, jeśli dostanie jasny temat, budżet, zasady i ograniczony nadzór człowieka?

To nie ma być konto udające człowieka. Publikacja powinna jasno informować, że jest tworzona przez agenta AI pod opieką redaktora.

---

## 2. Główny temat publikacji

### Robocza nazwa

**Nic nie jest przypadkowe**

### Główna obietnica

Publikacja wyjaśnia ukryte mechanizmy stojące za zwykłymi rzeczami, usługami, miejscami i decyzjami, które spotykamy każdego dnia.

Każdy tekst bierze jeden konkretny temat i odpowiada na pytanie:

> Dlaczego to działa właśnie tak?

### Przykładowe tematy

- Dlaczego supermarket ustawia produkty w określonej kolejności?
- Skąd bierze się cena biletu lotniczego?
- Co dzieje się z walizką po odprawie?
- Dlaczego kolejki stoją, mimo że część kas jest otwarta?
- Jak projektuje się przyciski w windach?
- Dlaczego restauracje skracają menu?
- Czemu hotele dają tyle poduszek?
- Jak naprawdę działa prognoza pogody?
- Dlaczego miasta sadzą konkretne gatunki drzew?
- Co sprawia, że rezygnacja z abonamentu jest trudniejsza niż zapis?
- Jak powstał kod kreskowy i dlaczego zmienił handel?
- Dlaczego klawiatura QWERTY wygląda właśnie tak?
- Co stoi za numeracją pokoi hotelowych?
- Dlaczego przejścia dla pieszych mają taki układ?
- Jak działa system cen w kinie, hotelu albo samolocie?

### Zakres tematyczny

Agent może pisać o:

- projektowaniu usług,
- ekonomii codzienności,
- psychologii zachowań,
- logistyce,
- miastach,
- transporcie,
- handlu,
- produktach,
- historii przedmiotów,
- technologii używanej na co dzień,
- systemach, które organizują codzienne życie.

### Tematy wykluczone

Agent nie powinien samodzielnie publikować porad dotyczących:

- zdrowia,
- leczenia,
- inwestycji,
- prawa,
- polityki,
- psychoterapii,
- bezpieczeństwa osobistego,
- osobistych doświadczeń, których nie posiada.

---

## 3. Pozycjonowanie publikacji

### Proponowane bio

> Publikacja o ukrytych systemach stojących za zwykłymi rzeczami. Research i szkice tworzy agent AI, a człowiek pilnuje faktów, jakości i granic eksperymentu.

### Proponowany opis publikacji

> Dlaczego bilety lotnicze zmieniają cenę co kilka godzin? Czemu supermarket prowadzi Cię określoną trasą? Co dzieje się z walizką po odprawie?
>
> „Nic nie jest przypadkowe” rozkłada codzienne systemy na części i pokazuje, jakie decyzje, mechanizmy i kompromisy kryją się pod powierzchnią.
>
> Publikacja jest eksperymentem: tworzy ją agent AI pod nadzorem człowieka. Wszystkie koszty, błędy i wyniki zostaną później opisane na „Chaos Engine”.

### Alternatywne nazwy

Polskie:

- Ukryty mechanizm
- Pod powierzchnią
- Jak to naprawdę działa
- Zwykłe rzeczy, dziwne zasady

Angielskie:

- Nothing Is Accidental
- Under the Surface
- The Hidden System
- Why It Works That Way
- Ordinary Machinery

---

## 4. Poziom autonomii

Projekt powinien zaczynać jako półautomatyczny.

### Agent może robić samodzielnie

- wyszukiwać tematy,
- prowadzić research,
- oceniać jakość źródeł,
- tworzyć kalendarz publikacji,
- pisać szkice artykułów,
- pisać Notes,
- przygotowywać tytuły i podtytuły,
- tworzyć prompty do grafik,
- generować grafiki,
- wyszukiwać publikacje i autorów,
- przygotowywać komentarze,
- analizować statystyki,
- prowadzić dziennik działań,
- proponować zmiany strategii.

### Człowiek zatwierdza

- każdy artykuł przed publikacją,
- każdy komentarz,
- każdy link promocyjny,
- kontakt z innymi autorami,
- zmianę tematyki,
- zmianę tonu publikacji,
- zmianę zasad działania,
- treści o podwyższonym ryzyku,
- grafiki zawierające ludzi, marki, tekst lub elementy mogące wprowadzać w błąd.

### Co można później zautomatyzować

Po 2–3 tygodniach, jeśli jakość będzie stabilna:

- publikowanie części Notes,
- publikowanie wcześniej zatwierdzonych typów grafik,
- automatyczne planowanie wpisów,
- automatyczne zbieranie statystyk,
- automatyczne przygotowanie cotygodniowego raportu.

---

## 5. Główny workflow agenta

### A. Wyszukiwanie tematów

Agent codziennie:

1. Przegląda źródła i publikacje.
2. Zbiera 10–20 potencjalnych tematów.
3. Nadaje im ocenę od 0 do 100.
4. Odrzuca tematy:
   - zbyt ogólne,
   - zbyt słabo udokumentowane,
   - zbyt podobne do ostatnich publikacji,
   - wymagające osobistego doświadczenia,
   - obarczone ryzykiem błędu.

### Proponowany scoring

- zgodność z tematyką publikacji: 25 pkt,
- dostępność wiarygodnych źródeł: 25 pkt,
- ciekawość i zaskoczenie: 20 pkt,
- potencjał na dobrą grafikę: 10 pkt,
- potencjał na Notes i komentarze: 10 pkt,
- oryginalność względem poprzednich tekstów: 10 pkt.

### B. Research

Agent:

1. Preferuje źródła pierwotne.
2. Sprawdza daty.
3. Oddziela fakt od interpretacji.
4. Nie dopisuje brakujących szczegółów.
5. Zapisuje listę wykorzystanych źródeł.
6. Oznacza elementy niepewne.
7. Tworzy krótką kartę researchu.

### C. Pisanie artykułu

Agent:

1. Ustala tezę.
2. Ustala najważniejszy mechanizm.
3. Wybiera sposób otwarcia.
4. Pisze pierwszy szkic.
5. Przeprowadza osobny audyt.
6. Poprawia tekst.
7. Przygotowuje gotową wersję do publikacji.

### D. Grafika

Agent:

1. Wyciąga główną ideę artykułu.
2. Przygotowuje 2–3 koncepcje wizualne.
3. Generuje grafikę.
4. Sprawdza:
   - zgodność z tekstem,
   - brak przypadkowych napisów,
   - brak fałszywych logotypów,
   - brak błędnej anatomii,
   - spójność z identyfikacją publikacji.
5. Pokazuje grafikę człowiekowi do zatwierdzenia.

### E. Dystrybucja

Po publikacji agent:

- tworzy 2–4 Notes na bazie artykułu,
- przygotowuje krótką zajawkę,
- znajduje publikacje, pod którymi temat może naturalnie pasować,
- przygotowuje komentarze,
- unika nachalnej promocji.

### F. Analiza

Raz dziennie agent zapisuje:

- liczbę odsłon,
- liczbę subskrypcji,
- liczbę reakcji,
- liczbę komentarzy,
- liczbę wejść na profil,
- źródła ruchu,
- najlepiej działające tematy,
- czas człowieka,
- koszt API,
- błędy i odrzucone treści.

---

## 6. Strategia treści na 30 dni

### Artykuły

- 1 pełny artykuł tygodniowo,
- 4–5 artykułów w miesiącu,
- długość około 900–1600 słów.

### Notes

- 1–2 Notes dziennie,
- 30–60 miesięcznie,
- każda Note ma jedną własną myśl,
- bez pustych motywacyjnych zakończeń,
- bez sztucznego promowania profilu.

### Komentarze

- 3–5 dobrych komentarzy dziennie,
- tylko pod treściami naprawdę związanymi z tematyką,
- maksymalnie 1 komentarz u jednego autora dziennie,
- link do własnego tekstu najwyżej w 10% komentarzy,
- każdy komentarz zatwierdzany przez człowieka.

### Proporcje tematów

- 30% ukryte mechanizmy usług i handlu,
- 20% miasta i transport,
- 20% historia codziennych przedmiotów,
- 15% zachowania konsumentów,
- 10% logistyka,
- 5% eksperymentalne tematy spoza głównego zakresu.

---

## 7. Styl wizualny

### Kierunek

- nowoczesny styl redakcyjny,
- lekko filmowy,
- elegancki,
- prosty,
- bez tandetnego science fiction,
- bez robotów,
- bez mózgów AI,
- bez przypadkowych stockowych ludzi,
- bez napisów wewnątrz obrazu.

### Przykładowa instrukcja wizualna

> Create a clean cinematic editorial image explaining the hidden system behind an ordinary object, service or place. Use a minimal composition, strong visual hierarchy, realistic details, subtle diagrams or layered mechanisms, restrained color palette, no text, no logos, no robots, no AI brains, no stock-photo look. The image should feel intelligent, curious and slightly mysterious.

### Format

- artykuł: szeroka grafika pozioma,
- Notes: prosta grafika lub detal,
- social media: osobny wariant pionowy,
- każdy obraz powinien mieć tekst alternatywny.

---

## 8. Zasady bezpieczeństwa i jakości

Agent nigdy nie powinien:

- podszywać się pod człowieka,
- wymyślać doświadczeń,
- wymyślać cytatów,
- tworzyć fałszywych źródeł,
- publikować masowo komentarzy,
- automatycznie wysyłać wiadomości prywatnych,
- publikować treści wysokiego ryzyka bez akceptacji,
- używać identycznych komentarzy,
- publikować komentarzy bez związku z treścią,
- naśladować konkretnego autora,
- generować agresywnej autopromocji,
- ukrywać, że publikacja jest eksperymentem AI.

---

## 9. Co mierzyć

### Wyniki publikacji

- liczba subskrybentów,
- liczba obserwujących,
- liczba odsłon,
- wejścia na profil,
- konwersja wejście → subskrypcja,
- otwarcia newslettera,
- kliknięcia,
- reakcje,
- restacki,
- komentarze.

### Wyniki agenta

- liczba przygotowanych treści,
- liczba zaakceptowanych treści,
- liczba odrzuconych treści,
- liczba poprawek człowieka,
- koszt jednego artykułu,
- koszt jednego subskrybenta,
- czas człowieka dziennie,
- liczba błędów faktograficznych,
- liczba błędów wizualnych,
- liczba razy, gdy agent musiał zostać zatrzymany.

### Cel eksperymentu

Nie ustawiać sztucznego celu typu „100 subskrybentów”.

Najważniejsze pytania:

- Czy agent potrafi utrzymać spójną publikację?
- Czy jego treści interesują ludzi?
- Czy potrafi sam poprawiać strategię?
- Ile nadzoru nadal potrzebuje?
- Ile kosztuje zdobycie jednego czytelnika?
- Co robi lepiej od człowieka?
- Gdzie bez człowieka sobie nie radzi?

---

## 10. Budżet

### Szacowany koszt miesięczny

- Substack: 0 USD,
- model językowy: 8–20 USD,
- research i wyszukiwanie: 3–10 USD,
- generowanie grafik: 3–15 USD,
- VPS: 0–10 USD,
- domena: opcjonalnie 10–15 USD rocznie.

### Realistyczny budżet 30-dniowego testu

> 20–55 USD bez liczenia czasu budowy systemu.

### Limit bezpieczeństwa

Ustawić miesięczny limit API:

> maksymalnie 30–40 USD na modele, research i grafiki.

---

## 11. Minimalna architektura techniczna

### Moduły

1. Topic Finder
2. Source Collector
3. Research Verifier
4. Article Writer
5. Note Writer
6. Comment Writer
7. Image Prompt Builder
8. Image Generator
9. Approval Panel
10. Substack Browser Automation
11. Analytics Collector
12. Experiment Journal
13. Cost Tracker
14. Safety Rules

### Dane przechowywane przez system

- lista tematów,
- historia artykułów,
- historia Notes,
- historia komentarzy,
- lista autorów,
- lista źródeł,
- odrzucone treści,
- zaakceptowane treści,
- statystyki,
- koszty,
- poprawki człowieka,
- błędy,
- decyzje strategiczne.

### Sugerowana technologia

- Python,
- Playwright do obsługi przeglądarki,
- SQLite lub JSON na początek,
- prosty panel lokalny,
- API modelu językowego,
- API modelu graficznego,
- harmonogram lokalny lub VPS.

---

## 12. Plan budowy

### Etap 1 — ręczny prototyp

- agent wybiera temat,
- agent robi research,
- agent pisze artykuł,
- agent generuje grafikę,
- człowiek publikuje wszystko ręcznie.

### Etap 2 — półautomat

- panel do zatwierdzania,
- historia treści,
- generowanie Notes,
- wyszukiwanie autorów,
- propozycje komentarzy,
- automatyczne zbieranie statystyk.

### Etap 3 — kontrolowana autonomia

- automatyczne planowanie publikacji,
- automatyczne publikowanie wybranych Notes,
- samodzielna korekta strategii,
- cotygodniowy raport,
- nadal ręczna akceptacja komentarzy i artykułów.

### Etap 4 — eksperyment 30-dniowy

- start publikacji,
- codzienna praca agenta,
- pełne logowanie,
- cotygodniowa analiza,
- końcowy raport.

---

## 13. Materiał końcowy na „Chaos Engine”

Po zakończeniu eksperymentu powstanie artykuł:

# Dałem agentowi AI 30 dni, 40 dolarów i własny Substack

### Proponowany podtytuł

Nie pozwoliłem mu pisać o AI. Miał zbudować newsletter o ukrytych mechanizmach codzienności. Oto koszty, błędy i wyniki.

### Co powinien zawierać artykuł

- założenia,
- architekturę,
- screeny,
- koszty,
- liczbę publikacji,
- liczbę subskrybentów,
- reakcje czytelników,
- błędy,
- odrzucone teksty,
- czas człowieka,
- przykłady komentarzy,
- grafiki,
- sytuacje, w których agent zawiódł,
- sytuacje, w których był lepszy od człowieka,
- wnioski dotyczące autonomicznych twórców.

---

## 14. Gotowy prompt do rozpoczęcia budowy

```text
Chcę zbudować półautonomicznego agenta prowadzącego osobną publikację na Substacku przez 30 dni.

Publikacja ma nazywać się roboczo „Nic nie jest przypadkowe” i wyjaśniać ukryte mechanizmy stojące za zwykłymi rzeczami, usługami, miejscami i decyzjami.

Agent ma:
- znajdować tematy,
- prowadzić research,
- sprawdzać źródła,
- pisać artykuły,
- pisać Substack Notes,
- generować grafiki,
- wyszukiwać autorów i publikacje,
- przygotowywać komentarze,
- analizować statystyki,
- prowadzić dziennik kosztów, błędów i decyzji,
- proponować zmiany strategii.

Na początku człowiek zatwierdza:
- każdy artykuł,
- każdy komentarz,
- każdą wiadomość do innego autora,
- każdą grafikę,
- każdą zmianę strategii.

Nie chcę pełnej autonomii od pierwszego dnia.

System powinien być zbudowany w Pythonie, z Playwrightem, lokalnym panelem zatwierdzania, prostą bazą SQLite i osobnymi modułami dla researchu, pisania, grafik, komentarzy, analityki i logowania.

Przygotuj:
1. architekturę systemu,
2. strukturę folderów,
3. modele danych,
4. przepływy pracy,
5. zasady bezpieczeństwa,
6. plan wdrożenia etapami,
7. listę ryzyk,
8. plan testów,
9. estymację kosztów,
10. wersję MVP, którą można uruchomić lokalnie.

Nie zaczynaj od pisania kodu. Najpierw przedstaw kompletny plan techniczny i wskaż elementy, które wymagają decyzji.
```
