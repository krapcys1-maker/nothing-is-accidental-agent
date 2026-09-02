# Naprawa zamiast cięcia + warstwa oszacowań — 1 września 2026

**Nic z tego nie jest wdrożone.** Serwer chodzi na `3b5bd6b`. Do obejrzenia razem.

---

## 1. Skąd to się wzięło

O 19:46 poszła w świat notka 327559609 — po tym, jak **nasze własne sprawdzenie
faktów ją obaliło**:

```
! OBALONE: Nuro logged thirty times the takeovers of Zoox under the same regulator.
ZASTRZEZENIA (notka i tak idzie): ...
```

Notka podaje własne liczby: Nuro 646 mil między przejęciami, Zoox 60 682.
**60 682 / 646 = 93,9.** Notka mówi „thirty". Pomyłka o czynnik trzy, w notce
**typu SPROSTOWANIE i formy LICZBA** — czyli konto poprawiające publicznie cudze
liczby opublikowało własną złą.

To nie była usterka, tylko cena reguły: *nic się nie blokuje* i *nic się nie
wycina*. Przy tych dwóch zostaje jedno wyjście — puścić. Właściciel wybrał
trzecie: **naprawić**, notki nie kasować.

---

## 2. Co zbudowane — naprawa

`stages.napraw_obalone()` + `prompts/naprawa.md`. Model dostaje własny tekst,
zarzut i materiał dowodowy, i oddaje to samo zdanie prawdziwe.

**Naprawiamy wyłącznie `refuted` i `outdated`.** To najważniejsza granica w całej
funkcji. Naprawa pracuje materiałem z pola `what_the_source_says`, a przy
`unverified` tego pola z definicji nie ma — kazać modelowi „poprawić"
twierdzenie, którego nikt nie obalił, bo nikt go nie znalazł, znaczy kazać mu
**wymyślić liczbę, która przejdzie sprawdzenie**. Byłby to fałsz mocniejszy od
naprawianego, bo powstały *po* weryfikacji i przez nią uwiarygodniony.

Naprawiony tekst przechodzi **tę samą ścieżkę co oryginał**: zapory
(wstrzyknięcie, podłogi z pamięci), długość, ponowne sprawdzenie faktów. Gdy
wypadnie gorzej albo tak samo — zostaje oryginał. Jedna próba, sufit
`NAPRAW_NA_PRZEBIEG = 4`.

Dwie pułapki, które wyszły dopiero przy pisaniu:

- **Link promocyjny nie idzie do naprawy.** Kod dokleja do notki promującej
  adres własnego artykułu *swoim* kodem, bo „model potrafi przekręcić URL".
  Oddanie mu całości do przepisania cofałoby tamtą decyzję tylnymi drzwiami.
  Dodatkowo długość notki mierzy się *przed* doklejeniem adresu, więc
  sprawdzanie naprawy razem z linkiem porównywałoby liczbę z sufitem policzonym
  dla czegoś innego.
- **Komentarz nie ma widełek długości i mieć nie ma** — `prompts/komentarz.md`
  mówi wprost, że odpowiedź ma prawo mieć osiem słów albo siedemdziesiąt.
  Pilnujemy więc czegoś węższego: naprawa ma zostać **tym samym** komentarzem
  (±50% długości).

Test: `tests/test_naprawa_zamiast_ciecia.py` — 33 asercje, w tym scenariusz
„samo `unverified` → **zero** wywołań modelu" (atrapa rzuca przy każdym).

---

## 3. Co zbudowane — pamięć

`agent-v2/oszacowania.py`. Po krytyce GPT rozdzielone na **trzy** warstwy, nie dwie:

```
zdarzenie    "komentarz 4718, postawa CIEKAWOSC, 0 odpowiedzi, 9 dni"
oszacowanie  "CIEKAWOSC: 1 na 7, ale próg to 12 — NIE WIEM"
decyzja      wagi postaw (dziś: bez zmian, tryb obserwacyjny)
```

**Nie przechowujemy zdań.** Każde oszacowanie liczy się od nowa z surowych
zapisów, więc nowe dane unieważniają wniosek same — nie powstaje trwałe zdanie
w rodzaju historii z przyciskiem Follow.

**Ale to nie znaczy, że oszacowanie nie może skłamać.** Napisałem wczoraj, że
„przeliczana opinia nie ma jak skłamać" i to było za mocne: rachunek
deterministyczny daje **powtarzalność, nie prawdę**. Każda z dróg fałszu ma
własne zabezpieczenie i własny przypadek testowy:

| droga fałszu | zabezpieczenie |
|---|---|
| brakujący identyfikator | liczone i pokazywane jako `bez_id` |
| świeże zero brane za ostateczne | `OSZACOWANIA_DOJRZALOSC_DNI = 3` |
| porównanie treści różnego wieku | wspólne pasmo wieku |
| mała próba | `MIN_NA_WARIANT = 12`, **na wariant**, nie na sumę |
| zmiana tematyki konta | `PRZESTAWIENIE_KONTA` + okno 60 dni |
| pętla zwrotna | `PODLOGA_EKSPLORACJI = 0.35` |
| **zmienne uboczne** | **NIE UMIEMY — powiedziane wprost w raporcie** |

Ostatni wiersz jest najważniejszy. Komentarz pod dużym kontem dostaje odpowiedź
częściej niż pod małym, a postawy nie są losowane równomiernie po wielkości
hosta. Różnica między postawami może być w całości różnicą między hostami.

**Stałe redakcyjne nie są hipotezami.** `wagi_postaw()` istnieje, ale w trybie
obserwacyjnym zwraca wagi bez zmian. Gdy tryb zostanie wyłączony, modulacja jest
ograniczona do ±50%, nigdy do zera, i **nie dotyka wariantów oznaczonych „nie
wiem"**. KOREKTA i ZGODA są niskie dlatego, że „wieczny korygujący i potakiwacz
to ta sama wada z dwóch stron" — to decyzja o tym, czym jest to pismo, a nie
twierdzenie do obalenia liczbą odpowiedzi. Optymalizator puszczony luzem
nauczyłby się zaczepiać i miałby rację w każdej liczbie osobno.

Test: `tests/test_oszacowania.py` — 26 asercji.

---

## 4. Co pamięć od razu znalazła — i to jest cenniejsze od niej samej

### 4a. 43 udane komentarze nie dają się połączyć z wynikiem

```
komentarzy w dzienniku: 121
z polem `nasz_id`:       66
BEZ:                     55   — w tym 43 UDANE
```

Przyczyna: `browser.potwierdz_odpowiedz` pobierała z API cały wątek, zamieniała
go **z powrotem na napis** przez `json.dumps` i sprawdzała, czy nasz tekst gdzieś
w nim jest. Numer leżał w tej samej odpowiedzi — przepuszczony przez `dumps`
przestawał być danymi i stawał się literami.

Skutek dla pomiaru: po odsianiu niedojrzałych zostało **17 komentarzy na 17
różnych hostach**, po jednym. Pytanie „gdzie nikt nam nigdy nie odpowiada" nie
mogło dojrzeć **nigdy**, choć dane fizycznie istniały. I szła tędy *większość*
pracy — `wystaw_odpowiedz` obsługuje komentarze pod cudzymi notkami, a tych jest
więcej niż pod artykułami.

Naprawione: funkcja oddaje numer, jak `potwierdz_komentarz`. **Potwierdzenie nie
zależy od numeru** — gdy treść jest, a numeru brak, oddaje `-1`, nie `None`.
Inaczej lepszy pomiar byłby kupiony za fałszywy dowód przeciw hostowi, a to
zdanie kasuje host na zawsze.

Test: `tests/test_nasz_id_pod_notka.py` — 20 asercji.

### 4b. Zdanie uzasadniające wagę CIEKAWOSCI przestało być prawdziwe

`config.py` mówi: *„Jedyny komentarz, który dostał odpowiedź (1 z 27), zaczynał
się od »What surprised me is« — ciekawość, nie korekta. Stąd ona jest
najcięższa."*

Dziś, na 54 połączalnych komentarzach, odpowiedzi są **trzy** i rozłożone na
**trzy różne postawy**: MECHANIZM 1/14, CIEKAWOSC 1/13, PYTANIE 1/8. Waga 7 stoi
na pomiarze, który już tego nie mówi. Do decyzji — zostawić jako regułę
redakcyjną (obronioną osobno) czy przepisać uzasadnienie.

### 4c. Użyteczne okno ma dziś cztery dni

Od progu dojrzałości (3 dni) do przestawienia konta (7 dni wstecz). Stąd „nie
wiem" wszędzie — i to jest poprawna odpowiedź, nie usterka.

---

## 5. Stan

| | |
|---|---|
| testy | **110 zdanych / 2 oblane** (oba tylko Windows: brak `playwright`, brak `SIGTERM`) |
| wdrożone | **nie** — serwer na `3b5bd6b` |
| notka 327559609 | zostaje, zgodnie z decyzją |

**Niewpięte celowo:** `oszacowania.py` nie jest wołane z `run.py`. Moduł liczy
i raportuje na żądanie; czy raport ma wchodzić do logu przebiegu — do wspólnej
decyzji jutro.
