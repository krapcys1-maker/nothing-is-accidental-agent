# Analiza całego konta — 7 września 2026

Zlecenie właściciela: *„na koncie zrobiła się monotonia, jak na tablicy
ogłoszeń, wszystko wrzucane jakby z automatu; subskrybentów nie przybywa, stoi
wszystko w miejscu mimo naszych działań"*.

Wszystko zmierzone na żywym serwerze. Gdzie coś jest wrażeniem, a nie pomiarem,
piszę to wprost.

## 1. Stan konta

| | 31.08 | 07.09 |
|---|---|---|
| subskrybenci | 9 | **10** |
| obserwujący | 11 | **20** |

Obserwujący rośli do 5 września i **od trzech dni stoją**. Subskrybenci: **+1
w osiem dni**.

Praca w tym samym tygodniu:

```
44 notki · 71 komentarzy · 69 polubień · 11 odpowiedzi · 8 restacków
5 subskrypcji · 4 obserwacje
```

Dużo pracy, prawie zero wyniku. To jest prawdziwy problem, nie wrażenie.

## 2. Czego NIE trzeba poprawiać

Sprawdziłem to najpierw, żeby nie naprawiać rzeczy działającej. Na **60
notkach ery AI** (od 25 sierpnia):

- **60 różnych otwarć, zero powtórzonych**
- wzorzec „jedno słowo. To tyle, ile…" tylko w **7%**
- rotacja form działa: każda notka dnia ma inną formę
- „ktoś w zdaniu" (`you/your`) w 20% pierwszych zdań — nie za dużo

**Styl nie jest monotonny.** Wrażenie bierze się skądinąd.

## 3. Gdzie monotonia naprawdę jest

Bank kandydatów, 131 wolnych faktów:

| | ile |
|---|---|
| **tylko branża** — ceny, modele, benchmarki, firmy | **92 (70%)** |
| **o świecie** — ludzie, szkoła, sąd, praca, zdrowie | **8 (6%)** |
| jedno i drugie | 27 |

Przykłady branżowe: *„AI pricing and what you pay per token"*, *„the speed of
your AI responses"*, *„open-weight models"*. O świecie: *„face recognition and
your child's classroom"*, *„the self-driving car in your city"*.

**Ośmiu jest tych drugich na 131.** To jest ta tablica ogłoszeń.

## 4. Przyczyna — i nie leży tam, gdzie się wydawało

Lista dziedzin (`DZIEDZINY_CIEKAWOSTEK`) **jest zbalansowana**: 46 pozycji, z
tego 20 wprost o świecie — leki, diagnostyka, klimat, zawody, sądy, szkoły,
nadzór. Losujemy pięć na szukanie, więc powinno wychodzić pół na pół.

Nie wychodzi, bo w tym samym prompcie stoi **drugie, mocniejsze źródło tematu**:

| co model dostaje | ile znaków |
|---|---|
| zaczyn z kanałów — konkretne, datowane nagłówki branżowe | **2201** |
| dziedziny — abstrakcyjne opisy obszarów | **315** |

Siedem razy więcej miejsca i konkret zamiast abstrakcji. Do tego dwa zdania w
samym prompcie pchały w tę samą stronę:

- *„Work the grid, but work it **ON THE WEEK'S SUBJECTS**"*
- opis pola `domain`: *„the part of the AI stack, **industry** or public record"*

Trzy rzeczy naraz. Lista dziedzin nie miała szans.

## 5. Co zmieniłem

**Kodem, bo tylko to jest gwarancją** — „prośba w prompcie nie jest bramką":

`ZACZYN_CO_DRUGIE_SZUKANIE = True`. **Co druga doba szuka bez zaczynu z
kanałów.** Wtedy siatka dziedzin nie ma z czym przegrać, bo nie ma
konkurencji. Parzystość liczona z doby, więc deterministyczna i odtwarzalna z
dziennika. Cofnięcie: `False`.

**W prompcie, jako dodatek, nie rozwiązanie:**
- siatka nie jest już podporządkowana bieżączce; stoi wymóg, że **co najmniej
  połowa** zwróconych faktów ma pochodzić z obszaru, którego nagłówki tygodnia
  nie tknęły
- opis `domain` dopuszcza miejsce w świecie: klinikę, klasę, sąd, pracę, ulicę,
  rachunek, który ktoś płaci

## 6. Czego NIE zmieniłem, choć kusiło

**Miksu typów notek.** Dwie godziny wcześniej wypadła z niego MYSL — bo miała
zero odwiedzin profilu na pięciu notkach. Ale to właśnie te dwie notki są
jedynym, co konto opublikowało, co nie brzmi jak tablica ogłoszeń:

> *„A half-typed question is sitting in the box, and you've just deleted it to
> write a tidier version before hitting enter. I do this constantly, and I only
> noticed last week."*

Cofanie tej decyzji na tej samej pięcioelementowej próbce byłoby miotaniem się,
a nie decyzją. **Zapisuję jako pytanie otwarte.** Za dwa tygodnie, przy nowym
składzie tematów, próbka coś powie.

## 7. Co zostaje do rozważenia

**Restacki.** Dwie najlepiej oglądane rzeczy w historii konta to restacki
z jednym zdaniem: **469 i 123 wyświetlenia**, przy najlepszej notce 94. Koszt
jednego: 0,006 USD. Robimy 1–2 dziennie, jako ósmy blok z dziewięciu.

Zastrzeżenie, którego nie pomijam: oba duże wyniki są z 26–27 sierpnia, a
wszystkie restacki od 28 sierpnia mają 9–34 wyświetlenia i zero zapisów.
Dwanaście kolejnych obserwacji przeczy dwóm pierwszym. Więc to jest kandydat
na próbę, a nie pewna dźwignia.

## 8. Po czym poznać, że zmiana zadziałała

Nie po zasięgu notek — audyt z 3 września wykazał, że reakcje nie odróżniają
dobrej notki od bełkotu (3,2 wobec 3,0 wobec 3,1).

Po **składzie banku**. Dziś 70% branża, 6% świat. Za tydzień ten sam pomiar
powinien pokazać przesunięcie; jeśli nie pokaże, zmiana nie zadziałała i trzeba
szukać dalej, a nie tłumaczyć.
