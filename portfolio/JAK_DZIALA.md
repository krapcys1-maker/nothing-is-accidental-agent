# Jak agent jest zbudowany — dla kogoś, kto chce zajrzeć głębiej

Dokument techniczny. Jeśli szukasz opisu projektu, zacznij od
[PROJEKT.md](PROJEKT.md); jeśli listy zdolności — [FUNKCJE.md](FUNKCJE.md).

---

## Przebieg dnia, krok po kroku

```
systemd timer                     3× dziennie, losowy poślizg do 25 min
   │
   ▼
zamek na pliku                    dwa przebiegi naraz = dwa razy ta sama treść
   │
   ▼
budżet dnia                       losowany z widełek, osobno na każdy dzień
   │
   ▼
ile już dziś poszło               notki — pytamy SUBSTACKA
                                  komentarze i polubienia — z dziennika,
                                  bo Substack ich nie oddaje
   │
   ▼
ile przebiegów zostało            dzielimy resztę przez przebiegi, które
                                  JESZCZE dziś będą, nie przez wszystkie
   │
   ▼
┌──────────────────────────────────────────────────────┐
│  1. odpowiedzi        (poza limitem — jesteśmy       │
│                        gospodarzem u siebie)          │
│  2. notki                                             │
│  3. komentarze u obcych                               │
│  4. dyskusje pod cudzymi notkami                      │
│  5. obserwowanie nowych autorów                       │
│  6. polubienia                                        │
└──────────────────────────────────────────────────────┘
   każdy blok w osobnym try — padnięty nie zabiera reszty
   przed każdym działaniem: czy został czas do końca przebiegu
   │
   ▼
zamknięcie przebiegu + kontrola sesji
```

---

## Dlaczego przez przeglądarkę, a nie przez API

Substack nie udostępnia publicznego API do publikowania. Agent pracuje więc tak,
jak pracowałby człowiek — przez zalogowaną przeglądarkę — i czyta te same
wewnętrzne endpointy, których używa interfejs Substacka.

**Trzy odkrycia, które ukształtowały tę warstwę:**

**Kliknięcie nie jest dowodem.** Przycisk klika się zawsze; treść nie zawsze
dochodzi. Po każdym działaniu agent pyta Substacka, czy naprawdę tam wisi.

**Interfejs idzie za językiem przeglądarki.** Selektory po angielskich napisach
padają, gdy interfejs wyświetli się po polsku. Elementy znajdowane są po
strukturze, a przyciski po kilku wariantach nazwy naraz.

**Substack TŁUMACZY cudze treści w HTML-u.** Komentarz napisany po angielsku
wyświetla się po polsku, jeśli taka jest przeglądarka. Odpowiedź po polsku komuś,
kto pisał po angielsku, byłaby kompromitacją — więc treść cudzą agent bierze
wyłącznie z API, gdzie `body` jest oryginałem, a osobne pole mówi, w jakim języku
powstała.

---

## Cztery tabele i dwa pliki — cały stan agenta

| tabela | co trzyma |
|---|---|
| `runs` | przebiegi: kiedy, status, na jakim etapie, koszt |
| `calls` | każde wywołanie modelu: tokeny, koszt, etap |
| `articles` | gotowe artykuły |
| `sources` | źródła zebrane do artykułów |

Poza bazą, celowo, dwa pliki w formacie czytelnym okiem:

- **dziennik działań** (`dziennik.jsonl`) — jeden wiersz na czynność i na skutek
- **zużyte fakty** i **historia komentarzy** — żeby nie powtarzać się ani nie
  wracać do tych samych ludzi

Bazy nie ma po co pytać o rzeczy, które wie Substack. Dlatego licznik dzienny
pyta o notki **jego**, a nie własnego zapisu: po restarcie własna księgowość
kłamie, a Substack wie na pewno.

---

## Jak agent chroni się przed samym sobą

**Zamek na pliku.** Harmonogram odpali agenta o stałej godzinie niezależnie od
tego, czy poprzedni przebieg się skończył. Zamek trzyma system plików, więc
zabicie procesu zwalnia go samo — nie zostaje zakleszczenie do ręcznego
odblokowania.

**Tryb sprawdzenia jest naprawdę suchy.** Osobne sito przed każdym z siedmiu
działań widocznych publicznie. Wcześniej tryb testowy blokował wywołania modeli,
ale nie przeglądarkę — i dwa polubienia poszły na żywo podczas „suchego" testu.

**Sygnał zostawia ślad.** `SIGTERM` podnosi wyjątek, więc przerwany przebieg
zapisuje się jako nieudany z powodem, zamiast zniknąć bez śladu i wisieć
w bazie jako trwający.

**Przebieg pilnuje własnego zegara.** Kończy dzień krócej, zamiast dać się
przeciąć w połowie wpisywania komentarza.

**Nieudany przebieg nie zabiera slotu.** Kolejne widzą, że zostało ich mniej,
i dobierają więcej — dzień nadrabia się sam zamiast zostać niedomknięty.

---

## Czas i strefy

Agent **nie wie, w jakim kraju stoi serwer** i to jest celowe. Wewnątrz wszystko
liczy się w UTC, a godziny publikacji w strefie **czytelników**. Dzięki temu
przeniesienie serwera nie zmienia niczego, a zmiany czasu po obu stronach
Atlantyku — europejska pod koniec października, amerykańska tydzień później —
obsługuje biblioteka stref, nie nasz kod.

Wpisanie na sztywno „jesteśmy w CEST" tworzy błąd, który wybucha dokładnie
w tym tygodniu różnicy.

---

## Dobór modeli

Model dobierany jest **do etapu**, nie jeden do wszystkiego:

| etap | model | dlaczego |
|---|---|---|
| szukanie ciekawostek | tańszy z wyszukiwaniem w sieci | dużo zapytań, prosta robota |
| sprawdzanie faktów | tańszy z wyszukiwaniem | to samo |
| pisanie notek i komentarzy | mocniejszy | tu decyduje jakość zdania |
| pisanie artykułów | najmocniejszy | najdroższy etap, najwyższa stawka |

Sprawdzone i **odrzucone**: dwa modele w ogóle nie wywoływały wyszukiwania, tylko
wypisywały adresy z pamięci. Trzeci był nieprzewidywalny kosztowo — $0,46 i $1,65
przy tych samych ośmiu zapytaniach.

---

## Testowanie

**Kontrdowód w każdym teście.** Test sprawdza też, czy wykrywa błąd, który ma
wykrywać: liczy po staremu i wymaga innego wyniku. Test przechodzący na zepsutym
kodzie daje fałszywy spokój, czyli jest gorszy niż jego brak.

**Bez atrap tam, gdzie da się bez nich.** Test przerwania przebiegu uruchamia
prawdziwy proces i wysyła mu prawdziwy `SIGTERM`.

**Test integracyjny na kopii bazy** robi pełny przebieg bez publikowania
i pilnuje odcisków plików produkcji. Ten mechanizm złapał dwie usterki, których
nikt nie szukał — przebieg w trybie sprawdzenia po cichu zużywał pulę faktów
i zjadał dni promocji artykułu.

---

## Wdrożenie

Skrypt wdrożeniowy:
1. odmawia wdrożenia, gdy trwa przebieg (pyta o to zamek, nie listę procesów)
2. wciąga nową wersję
3. sprawdza, czy moduły wstają i czy konfiguracja jest kompletna
4. sprawdza, czy sesja żyje i czy to właściwe konto
5. przy niepowodzeniu cofa się do poprzedniej wersji jednym poleceniem

---

## Znane ograniczenia

- Odnowienie sesji Substacka wymaga człowieka raz na ~3 miesiące (logowanie przez
  link na e-mail). To jedyny moment, w którym agent nie jest samodzielny.
- Wyszukiwanie faktów to ~45% kosztu przebiegu i potrafi zwrócić rozważania
  zamiast danych.
- Pula dyskusji pod cudzymi notkami jest za wąska.
- Agent pracuje siedem dni w tygodniu w równym rytmie — ludzie mają dni, w których
  milczą.
