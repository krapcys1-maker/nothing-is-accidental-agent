# Nothing Is Accidental — autonomiczny agent prowadzący publikację na Substacku

Agent, który sam prowadzi konto redakcyjne: pisze notki, komentuje u obcych
autorów, odpowiada na reakcje, obserwuje nowych ludzi i publikuje artykuły.
Chodzi z harmonogramu na własnym serwerze, kilka razy dziennie, **bez ani jednego
pytania do człowieka**.

Publikacja tłumaczy, dlaczego zwykłe rzeczy wyglądają tak, jak wyglądają — jaka
decyzja, przepis albo interes za nimi stoi. Notka o tym, że amerykański znak stop
jest jedynym ośmiokątnym znakiem w kraju, bo norma federalna przypisuje ten
kształt wyłącznie jemu i ma być rozpoznawalny, gdy śnieg zasłoni napis.

---

## Ograniczenie, które ukształtowało cały projekt

Pierwsza wersja tego agenta miała **71 598 linii Pythona**, 2 817 testów, 236
triggerów bazodanowych i 42 migracje schematu. Wyprodukowała **dwa artykuły**.
Przewracała się na własnej infrastrukturze: kolejkach zadań, trwałych intencjach,
dzierżawach, kwalifikacjach modeli.

Druga wersja powstała z twardym budżetem złożoności, ustalonym **przed**
napisaniem pierwszej linijki:

| | limit | stan faktyczny |
|---|---|---|
| pliki `.py` | maksimum 10 | 10 |
| tabele w bazie | maksimum 4 | 4 |
| warstwy abstrakcji między harmonogramem a wywołaniem modelu | maksimum 1 | 1 |
| migracje, triggery, kolejki zadań, trwałe intencje | **zakazane** | brak |

**6 526 linii zamiast 71 598.** Ten sam zakres, jedenaście razy mniej kodu.

Osobna zasada, wyniesiona z pierwszej wersji: *jedna liczba mieszka w jednym
miejscu*. Gdy naprawdę musi stać w dwóch — jak limit czasu przebiegu, który
występuje w konfiguracji i w pliku usługi systemd — pilnuje tego test, który
porównuje oba i przewraca się przy rozjeździe.

---

## Jak to działa

```
  harmonogram (systemd) ──► przebieg dnia ──┬─► odpowiedzi na rozmowy
   3× dziennie, losowy                      ├─► notki z faktów ze źródłami
   poślizg do 25 min                        ├─► komentarze u obcych
                                            ├─► dyskusje pod cudzymi notkami
                                            ├─► obserwowanie nowych autorów
                                            └─► polubienia

  każde działanie ──► potwierdzenie U ŹRÓDŁA ──► dziennik działań i skutków
```

Agent nie ma własnego API — Substack żadnego publicznie nie udostępnia. Pracuje
przez **prawdziwą przeglądarkę** z zalogowaną sesją, sterowaną przez Playwright,
i czyta wewnętrzne endpointy, których używa sam interfejs Substacka.

### Trzy zasady, na których stoi całość

**1. Rzeczywistość jest źródłem prawdy, nie własna księgowość.**
Kliknięcie przycisku nie jest dowodem publikacji. Po każdym działaniu agent pyta
Substacka, czy treść naprawdę tam wisi — i dopiero wtedy uznaje je za wykonane.
Dzięki temu restart w połowie przebiegu nie powoduje, że ta sama notka wychodzi
drugi raz.

**2. Milczenie jest domyślne.**
Agent komentuje tylko wtedy, gdy ma coś własnego do dodania. W testowym
przebiegu odmówił skomentowania trzech postów, uzasadniając: *„post to osobiste
odczucie, nie ma z czym dyskutować"*, *„sam tytuł powtórzony jako treść"*.
Wyrabianie normy kosztem sensu jest gorsze niż nic.

**3. Fakt bez pokrycia nie wychodzi.**
Każda treść przechodzi przez sprawdzenie w sieci. Blokuje wyłącznie twierdzenie
**obalone przez źródło** — teza, analogia i interpretacja przechodzą, bo ludzie
też mają prawo do zdania. Podczas jednego przebiegu bramka zatrzymała komentarz,
bo źródła zaprzeczyły twierdzeniu o biciu monet przez władczynię z VII wieku.

---

## Problemy, które trzeba było naprawdę rozwiązać

### Cloudflare rozróżnia sposób, w jaki pytasz

Zapytanie `fetch()` z poziomu strony, z adresu centrum danych → **403**.
To samo zapytanie jako zwykła nawigacja przeglądarki → **200**.

Cała warstwa odczytu API musiała przejść z `fetch` na nawigację. To nie jest
obchodzenie zabezpieczeń: agent jest zalogowany jako właściciel konta i czyta
własne dane. Po prostu wygląda wtedy jak człowiek, którym w sensie uprawnień
jest.

### Odcisk przeglądarki bezgłowej nie przechodzi przy publikowaniu

Chromium w trybie headless czyta bez problemu, ale przy publikowaniu jest
odrzucany. Rozwiązaniem był **prawdziwy Chrome na wirtualnym ekranie**, do
którego agent podłącza się przez protokół debugowania. Ta sama przeglądarka,
której używa człowiek — tylko bez monitora.

### Sesja jest związana z adresem, z którego powstała

Sesja założona na komputerze domowym jest odrzucana przy publikowaniu z serwera.
Musi powstać **na serwerze**. Że to logowanie wymaga człowieka (Substack wysyła
link na e-mail), zbudowany został zdalny pulpit przez tunel SSH — właściciel
loguje się raz na trzy miesiące i to jedyny moment, w którym agent potrzebuje
człowieka.

### Nie wyglądać jak automat

To był najtrudniejszy wymóg, bo karą nie jest komunikat o błędzie, tylko cichy
spadek zasięgu, którego agent nigdy nie zauważy.

- **Widełki zamiast stałych liczb.** 15–20 komentarzy dziennie, nie 17. Człowiek
  nie ma normy: raz przeczyta pół kanału, raz nic. Losowane osobno na każdy dzień.
- **Odstępy dobrane do czynności.** Między komentarzami 3–8 minut, między
  notkami 10–25. Piętnaście polubień w półtorej minuty to nie jest czytanie.
- **Nie komentujemy świeżych treści.** Odpowiedź pięć sekund po cudzej notce
  zdradza automat, zanim ktokolwiek przeczyta jej treść. Progi są inne dla
  artykułu (1,5–15 h) i dla notki (20–90 min), bo te dwie rzeczy żyją w innym
  tempie.
- **Nigdy dwa razy pod tym samym tekstem.** Drugi komentarz pod postem, gdzie
  nikt nie odpowiedział, to najczytelniejszy podpis bota, jaki można zostawić.
- **Cztery dni odstępu przed powrotem do tej samej publikacji.** Człowiek nie
  czyta wszystkiego, co ktoś wypuszcza.

### Nie kręcić się wśród tych samych ludzi

Kanał czytelnika pokazuje wyłącznie to, co już znamy — konto zamknięte w takim
kręgu nie rośnie. Agent używa wyszukiwarki Substacka z rotującej puli osiemnastu
haseł tematycznych i sięga po autorów spoza kręgu.

Efekt zmierzony na produkcji: **18 komentarzy u 18 różnych publikacji, zero
powtórek.**

### Wybierać wcześnie, nie głośno

Pierwsza wersja doboru celów sortowała malejąco po zaangażowaniu — czyli im
większy tłok, tym wyżej. Wyszukiwarka oddawała posty ze średnio 45 komentarzami,
jeden ze 126. **Komentarz sto dwudziesty siódmy jest niewidoczny**, a kosztuje
tyle samo co pierwszy.

Sortowanie zostało odwrócone: najpierw teksty, które mają żywą publiczność, ale
jeszcze wolne miejsce w rozmowie.

---

## Pętla, która pozwala się poprawiać

Agent prowadzi **dziennik działań** — jeden wiersz na czynność, czytelny okiem
i skryptem. Zapisuje nie tylko co zrobił, ale co wiedział o celu w chwili
pisania: skąd go miał, **ilu komentarzy było tam przed nim**, jak duża
publiczność, jak stary tekst.

Raz na przebieg dopisuje **skutki** — kto polubił, kto odpowiedział, kto zaczął
obserwować. Dzięki temu przegląd po kilku dniach odpowiada na pytania, których
inaczej nikt nie umiałby zadać:

```
zwrot z jednego działania:
  komentarz u obcych   0.75
  notka na profilu     6.00

czy opłaca się być wcześnie:
  wcześnie (≤25 komentarzy)   wróciło 2/2  (100%)
  w tłoku                      wróciło 0/2  (0%)

skąd przyszedł cel, który odpowiedział:
  szukanie: zoning         2/2
  szukanie: hidden fees    0/2
```

To jest różnica między agentem, który działa, a agentem, który się poprawia.

---

## Testowanie kontrdowodem

Każdy test sprawdza także, **czy w ogóle wykrywa błąd, który ma wykrywać**. Liczy
po staremu i wymaga, żeby wynik był inny. Test przechodzący na zepsutym kodzie
jest gorszy od braku testu, bo daje fałszywy spokój.

Testy integracyjne robią pełny przebieg na **kopii bazy** i pilnują odcisków
plików produkcji. Ten mechanizm złapał dwie usterki, których nikt nie szukał:
przebieg w trybie sprawdzenia po cichu zużywał pulę faktów i zjadał dni promocji
artykułu — obie rzeczy odhaczały się przy *wygenerowaniu* treści, nie przy jej
publikacji.

**139 sprawdzeń w czterech zestawach.**

---

## Odporność na awarie

- **Zamek na pliku** — dwa przebiegi naraz to dwa razy ta sama treść, czego nie
  da się cofnąć. Zamek trzyma system plików, więc zabicie procesu zwalnia go sam.
- **Każdy blok osobno** — padnięte komentarze nie zabierają ze sobą notek. Dzień
  częściowo udany jest lepszy niż przerwany w połowie.
- **Przebieg pilnuje własnego zegara** — kończy dzień krócej, zamiast dać się
  przeciąć w połowie wpisywania komentarza.
- **Sygnał zostawia ślad** — `SIGTERM` podnosi wyjątek, więc przerwany przebieg
  zapisuje się jako nieudany z powodem, zamiast zniknąć bez śladu.
- **Kontrola zdrowia** raz dziennie: cisza, zawieszone przebiegi, dysk,
  nadaktywność, koszt, powtórki. Alarm idzie mailem do właściciela.
- **Wdrożenie z cofnięciem** — skrypt odmawia wdrożenia w trakcie przebiegu,
  sprawdza, czy nowa wersja wstaje i czy sesja żyje, a przy niepowodzeniu wraca
  do poprzedniej wersji jednym poleceniem.

---

## Liczby

| | |
|---|---|
| kod | 6 526 linii, 10 plików `.py`, 4 tabele |
| prompty | 20 plików Markdown, poza kodem |
| testy | 139 sprawdzeń, każde z kontrdowodem |
| historia | 318 commitów |
| koszt | ~0,15–0,27 USD za przebieg, 3 przebiegi dziennie |
| tempo | 15–20 komentarzy i 5 notek dziennie, widełki losowane |
| zasięg | 18 komentarzy u 18 różnych publikacji, zero powtórek |

---

## Z czego zbudowany

**Python** · **Playwright** (prawdziwy Chrome przez protokół debugowania) ·
**SQLite** · **systemd** (usługi jednorazowe i zegary) · **Xvfb + VNC**
(wirtualny ekran i zdalny pulpit przez tunel SSH) · **DeepSeek** i **Claude**
(model dobierany do etapu — tańszy do wyszukiwania faktów, mocniejszy do pisania)
· **gpt-image** (grafiki do artykułów)

---

## Czego jeszcze nie rozwiązałem

Uczciwie, bo to też część obrazu:

- **Pula dyskusji pod cudzymi notkami jest za wąska.** Kanał oddaje ich garść,
  a wyszukiwarka na tych hasłach zwraca prawie same artykuły. Skrócenie progu
  świeżości pomogło, ale nie wystarczy — potrzebne jest inne źródło.
- **Wyszukiwanie faktów to 45% kosztu przebiegu** i potrafi zwrócić rozważania
  zamiast danych, co oznacza zapłacone i wyrzucone wywołanie.
- **Agent pracuje siedem dni w tygodniu w równym rytmie.** Ludzie mają dni,
  w których milczą. To ostatni wyraźny sygnał automatu, który został.
