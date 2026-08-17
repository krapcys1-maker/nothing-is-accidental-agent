# Co agent naprawdę robi — funkcja po funkcji

Spis wszystkich zdolności agenta, z zasadą, która nimi rządzi, i z tym, co je
ogranicza. Wszystko poniżej działa na żywym koncie.

---

## 1. Notki — pięć dziennie, każda z innego faktu

Krótkie wpisy na profilu, 35–55 słów, każdy oparty na sprawdzonym fakcie
o zwykłej rzeczy.

**Jak powstają:** agent szuka w sieci ciekawostek z pokryciem w źródłach,
odrzuca te, których już użył, i dla każdej notki generuje trzy warianty. Wychodzi
ten, który przejdzie bramkę faktów i mieści się w długości.

**Skład dnia jest ustalony i różnorodny:** dwie ciekawostki, dyskusja,
sprostowanie, ciekawostka. Jednakowy kształt każdej notki to podpis maszyny, więc
rodzaje rozkładają się na kolejne przebiegi dnia, a nie lecą jeden po drugim.

**Jeden fakt na notkę.** Podanie modelowi całej puli naraz nie daje
różnorodności, tylko pięć wariantów tego samego — przy pierwszym przebiegu
cztery z pięciu kandydatur chwyciły ten sam fakt o windzie.

**Fakt znika z puli dopiero po potwierdzonej publikacji**, nie po wygenerowaniu.

---

## 2. Komentarze u obcych autorów

**Jak wybiera cele:**
1. Wyszukiwarka Substacka, trzy hasła losowane z puli osiemnastu tematycznych
2. Uzupełniająco kanał czytelnika
3. Model ocenia każdy cel: czy mamy tu coś własnego do dodania

**Trzy sita, zanim cokolwiek napisze:**
- czy post nie jest za świeży (komentarz pięć sekund po publikacji zdradza automat)
- czy nie komentowaliśmy u tej publikacji w ostatnich czterech dniach
- czy w ogóle wolno tam komentować — publikacje z komentarzami tylko dla płacących
  są pomijane **przed** napisaniem, żeby nie ponosić kosztu na darmo

**Kolejność celów: wcześnie przed głośno.** Najpierw teksty z żywą publicznością,
ale jeszcze wolnym miejscem w rozmowie. Komentarz sto dwudziesty siódmy jest
niewidoczny, a kosztuje tyle samo co pierwszy.

**Nigdy dwa razy pod tym samym tekstem.**

---

## 3. Dyskusje pod cudzymi notkami

Osobny mechanizm, bo pod notkami rozmowa toczy się inaczej niż pod artykułami —
wątek jest płaski, a kanał promuje te, które żyją. Dla młodego konta to
najważniejsze miejsce.

Próg świeżości jest tu krótszy (20–90 minut zamiast 1,5–15 godzin), bo notka
gaśnie tego samego dnia — czekając pół doby przychodzi się zawsze po końcu
rozmowy.

---

## 4. Odpowiedzi — rozmowa toczy się w trzech miejscach

| gdzie | jak agent to widzi |
|---|---|
| pod naszymi notkami | kanał profilu |
| pod naszymi artykułami | lista komentarzy pod artykułem |
| **pod naszymi komentarzami u obcych** | kanał aktywności, zdarzenie `comment_reply` |

Trzeciego długo nie widział wcale — i takiej odpowiedzi nie podjąłby nigdy, nie
„później". To najgorsze możliwe miejsce na milczenie, bo właśnie tam zaczyna się
rozmowa z ludźmi, którzy nas jeszcze nie znają.

**Kogo wybiera, gdy komentarzy jest dużo:** przy kilku odpowiada wszystkim. Przy
pięćdziesięciu odpowiedź pod każdym wygląda jak maszyna, więc wybiera —
z pierwszeństwem dla **niezgody**, bo nieodpowiedziany zarzut zostaje ostatnim
słowem.

Odpowiedzi są **poza dziennym limitem**. U siebie jesteśmy gospodarzem; pytanie
bez odpowiedzi pod własnym tekstem szkodzi bardziej niż komentarz za dużo.

---

## 5. Artykuły

Pełny potok raz w tygodniu: wybór tematu → odsiew wykonalności → szukanie źródeł
→ pobranie → klasyfikacja fragmentów i liczb → synteza karty dowodowej → pisanie
→ recenzja zdanie po zdaniu → grafika → publikacja.

**Po zrobionym researchu artykuł musi powstać.** Trzy ścieżki awaryjne: gdy
synteza padnie, karta składa się z samych dowodów; gdy pisarz odmówi, powtórka na
mocniejszym modelu; gdy recenzja padnie, artykuł zapisuje się z adnotacją, że nie
został rozliczony. Żaden etap nie ma prawa wyrzucić do kosza opłaconego researchu.

**Bramki nic nie blokują — zgłaszają uwagi.** Fakt bez pokrycia, liczba spoza
korpusu, zmyślone przeżycie, nieistniejące badanie.

**Promocja:** pięć notek promujących artykuł, po jednej dziennie przez kolejne
dni. Dzień promocji odhacza się dopiero po potwierdzonej publikacji notki.

---

## 6. Obserwowanie i subskrypcje

Agent obserwuje **wyłącznie tych, u których naprawdę był** — nie z listy
podpowiedzi. Obserwowanie kogoś, kogo się nie czytało, to zbieranie nazwisk, a nie
budowanie kręgu.

Tempo: 30–44 obserwacji miesięcznie, 6–12 subskrypcji. Liczone w **ruchomym oknie
30 dni**, nie w miesiącu kalendarzowym — przy oknie stałym agent mógłby wypalić
cały zapas w trzy ostatnie dni i zamilknąć na cztery tygodnie.

---

## 7. Polubienia

Najtańszy uczciwy sygnał obecności. 12–20 dziennie, odstępy 30–90 sekund.

---

## 8. Dziennik działań i skutków

Jeden wiersz na czynność, czytelny okiem i skryptem. Nigdy nie przerywa pracy —
dziennik, który wywala agenta, byłby gorszy od jego braku.

**Zapisuje o każdym działaniu:** co, kiedy, dokąd, ile słów, czy się udało,
a przy komentarzach dodatkowo **kontekst celu**: skąd przyszedł, ilu komentarzy
było tam przed nami, jak duża publiczność, jak stary tekst.

**Raz na przebieg dopisuje skutki** z kanału aktywności: kto polubił, kto
odpowiedział, kto zaczął obserwować. Każde zdarzenie zapisywane jest raz.

**Przegląd po kilku dniach** odpowiada na pytania, których inaczej nie da się
zadać: co wraca częściej — notka czy komentarz; czy opłaca się być wcześnie;
które hasła wyszukiwania przynoszą rozmowy.

---

## 9. Kontrola zdrowia

Codziennie rano, sześć sprawdzeń, alarm mailem do właściciela:

| sprawdzenie | co wykrywa |
|---|---|
| cisza | agent przestał publikować |
| zawieszone | przebieg wisi w toku ponad trzy godziny |
| dysk | zapełnienie przy 80% i 92% |
| nadaktywność | nagły skok liczby działań |
| koszt | przekroczenie sufitu |
| powtórki | komentarze u tej samej publikacji |

Osobno pilnowana jest **data wygaśnięcia sesji** — alarm przychodzi czternaście
dni wcześniej, bo odnowienie wymaga człowieka i jest to jedyny taki moment
w całym roku pracy agenta.

---

## Czego agent NIE robi

- **Nie odpowiada natychmiast.** Każde działanie ma losowy odstęp.
- **Nie komentuje, gdy nie ma co dodać.** Milczenie jest domyślne.
- **Nie wraca pod ten sam tekst.**
- **Nie publikuje faktu obalonego przez źródło.**
- **Nie kłamie o tym, czym jest.** Konto nie ujawnia się z własnej woli, ale
  zapytane wprost nie zaprzecza. Żadnych technicznych sztuczek ukrywających
  automat.
- **Nie obchodzi zabezpieczeń.** Świadomie odrzucono pomysł proxy do omijania
  ochrony przed botami — to celowe ukrywanie się, które ryzykuje kontem.
