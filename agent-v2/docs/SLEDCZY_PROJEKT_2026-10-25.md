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
