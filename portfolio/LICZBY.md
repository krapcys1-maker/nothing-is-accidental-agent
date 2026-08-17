# Liczby — stan na 17 sierpnia 2026

Wszystko poniżej jest odczytane z żywej produkcji, nie oszacowane.

---

## Kod

| | agent v2 | poprzednia wersja |
|---|---|---|
| linie Pythona | **6 526** | 71 598 |
| pliki `.py` | **10** | ponad 200 |
| tabele w bazie | **4** | kilkadziesiąt |
| migracje schematu | **0** | 42 |
| triggery bazodanowe | **0** | 236 |
| opublikowane artykuły | działa na żywo | 2 |

Prompty: **20 plików Markdown**, trzymane poza kodem.
Historia: **318 commitów**.

---

## Testy

| zestaw | sprawdzeń |
|---|---|
| licznik dzienny i rozdział normy | 36 |
| pięć poprawek zachowania | 47 |
| limit czasu i przerwanie sygnałem | 17 |
| pomiar skutków i dobór celów | 39 |
| **razem** | **139** |

Do tego test integracyjny: pełny przebieg dnia na kopii bazy, bez publikowania,
z kontrolą odcisków plików produkcji.

---

## Koszt

| | |
|---|---|
| przebieg dnia | 0,15–0,27 USD |
| przebiegi dziennie | 3 |
| łącznie zapłacone do tej pory | 1,00 USD w 222 wywołaniach modeli |

Najdroższy etap to szukanie ciekawostek — ok. 45% kosztu przebiegu, bo robi
kilkanaście do dwudziestu kilku zapytań do wyszukiwarki na jedno wywołanie.

Dostawca modelu ma taryfę szczytową w godzinach 1–3 i 6–9 UTC, gdzie ceny są
około trzykrotne. Harmonogram agenta (11, 15 i 20 UTC) omija ją w całości.

---

## Tempo pracy — widełki, nie stałe liczby

| działanie | dziennie |
|---|---|
| notki | 5 |
| komentarze | 15–20 |
| polubienia | 12–20 |

| działanie | miesięcznie |
|---|---|
| obserwacje | 30–44 |
| subskrypcje | 6–12 |

Widełki losowane osobno na każdy dzień. Przez pierwsze trzydzieści dni agent
trzyma się ich dolnej połowy — nowe konto z jednym artykułem, które nagle
obserwuje dwadzieścia osób, wygląda dokładnie jak farma.

Odstępy między działaniami: komentarze 3–8 minut, notki 10–25 minut, odpowiedzi
2–7 minut, polubienia 30–90 sekund.

---

## Zasięg i skuteczność

Z dziennika działań (prowadzony od 16 sierpnia):

| działanie | udane | nieudane |
|---|---|---|
| komentarze | 15 | 3 |
| notki | 3 | 0 |
| odpowiedzi | 3 | 0 |
| polubienia | 11 | 0 |
| subskrypcje | 1 | 3 |

**18 komentarzy u 18 różnych publikacji — zero powtórek.**

Trzy nieudane komentarze to publikacje, które pozwalają czytać wszystkim,
a komentować tylko płacącym. Wykryte i zamknięte: agent pyta teraz o prawo do
komentowania **przed** napisaniem tekstu.

Trzy nieudane subskrypcje to błąd w wyciąganiu nazwy konta z adresu na własnej
domenie — agent próbował obserwować konto o nazwie „www". Też naprawione.

---

## Odzew od czytelników

Z kanału aktywności, ostatnie kilkadziesiąt godzin:

| zdarzenie | ile |
|---|---|
| polubienia notek | 6 |
| odpowiedzi pod notkami | 2 |
| polubienia komentarzy | 2 |
| odpowiedzi na nasze komentarze | 1 |
| nowe obserwacje | 1 |

Łącznie **18 osób** zareagowało na treści agenta.

Zestawienie, które z tego wynika i które agent liczy sam:

```
zwrot z jednego działania:
  komentarz u obcych   0,75
  notka na profilu     6,00
```

Notka daje kilkukrotnie więcej niż komentarz, a komentarzy agent robi dwa i pół
raza więcej. To pierwszy wniosek z pętli pomiarowej — próbka jest jeszcze mała,
ale kierunek wyraźny.

---

## Niezawodność

| | |
|---|---|
| sesja Substacka | ważna do ~13 listopada 2026 |
| odnowienie sesji | wymaga człowieka, raz na ~3 miesiące |
| kontrola zdrowia | codziennie, 6 sprawdzeń, alarm mailem |
| ostrzeżenie o wygasającej sesji | 14 dni wcześniej |
