# Serie tematyczne — co zbudowałem i po czym poznać, czy działa

Zbudowane 6 września 2026. Moduł `agent-v2/seria.py`, haki w `stages.py`
i `run.py`, test `agent-v2/tests/test_seria_tematyczna.py` (49 asercji).

## Po co, jedną liczbą

    artykuł      7 subskrypcji
    notka        0
    komentarz    0
    odpowiedź    0

Notki robią zasięg — 32,6 wyświetlenia średnio, zero pozycji z zerem — który
**nie prowadzi donikąd.** Pojedyncza notka nie daje nikomu powodu, żeby wrócić.
„Część 2 jutro" daje. To jedyny mechanizm, jakiego to konto nie próbowało,
a który uderza dokładnie w tę słabość.

## Jak to działa

Cztery notki o jednym temacie, **jedna na dobę**, jawnie ponumerowane, ostatnia
zamyka serię. Znacznik stoi w ostatnim wierszu notki:

    Where the electricity goes — 2/4

**Temat wybiera bank, nie plan.** Pierwsza wersja miała brać temat z listy
i czekać na materiał. Zmierzone na żywym banku (129 wolnych faktów): temat
wybrany z góry potrafi nie mieć **ani jednego** pasującego faktu, więc seria
albo czekałaby w nieskończoność, albo wydała część nie na temat. Jest więc
odwrotnie: seria zaczyna się wyłącznie na temacie, który bank wyżywi na
wszystkie cztery części. Dziś taki temat jest **jeden**.

| temat | faktów powyżej progu |
|---|---|
| Prąd i data centre | **4** — wystarczy |
| Prawo i sądy | 2 |
| AI w szkole | 1 |
| AI w medycynie | 1 |
| AI w pracy | 0 |
| Kto na tym zarabia | 0 |

## Próg dopasowania — sprawdzony na treści, nie na liczbach

Pierwsze punktowanie (luźne słowa kluczowe) dawało **ładne liczby i bezsensowną
treść**: temat „AI w pracy" dostawał cztery fakty, z czego dwa o tej samej
aukcji upadłościowej Spirit Airlines. Każdy punktował dokładnie 3.

Przy progu 5 wszystkie cztery odpadają, a wszystko, co naprawdę jest na temat,
zostaje. **Progi 4, 5 i 6 dają identyczny wynik** — to płaskowyż, więc cięcie
nie jest dobrane pod jeden zbiór.

Trafienie w `domain` liczy 3 punkty, w treść 1. Powód: `domain` to własna
etykieta banku, 127 różnych wartości na 131 faktów — jako kategoria
bezużyteczna, jako **opis** mocniejsza niż samo zdanie faktu.

## Dwie rzeczy, które mogłyby to cicho zepsuć — i co je pilnuje

**1. Zapis przy pisaniu zamiast po publikacji.** `notki_dnia` nie zapisuje
niczego. Gdyby zapisywał, przebieg bez `--wyslij` zaczynałby prawdziwą serię,
której część pierwsza nigdy by nie wyszła — czytelnik dostałby serię
zaczynającą się od części drugiej. To ta sama wada, która przy faktach
kasowała materiał, a przy artykule zjadała dni promocji.

**2. Ten sam fakt dwa razy.** Test to złapał, a czytanie kodu nie: stan
zapisywał tekst faktu **obcięty do 200 znaków**, a porównanie szło z pełnym
tekstem z banku, więc nigdy się nie zgadzały i część 2 wzięła dokładnie ten
sam fakt co część 1. Na produkcji byłoby to częściowo zamaskowane, bo
opublikowany fakt znika z banku — ale zamaskowane to nie naprawione.

## Czego ta zmiana NIE robi

- Nie zmniejsza liczby notek. Seria zajmuje **jeden slot z dziesięciu**.
- Nie kosztuje więcej. Część serii to zwykła notka, tym samym pisarzem.
- Nie zmienia tego, skąd biorą się fakty. Bank nadal jest w 98,5% newsowy;
  seria tylko **wybiera z niego to, co układa się w temat**.

## Po czym poznać, czy działa — i po czym NIE

**Miarą są odwiedziny profilu i subskrypcje.** Nie polubienia: audyt
z 3 września wykazał, że reakcje nie odróżniają dobrej notki od bełkotu
(3,2 wobec 3,0 wobec 3,1 — płasko).

Punkt odniesienia, zmierzony na notkach mających co najmniej dwa dni:

| | odwiedziny profilu / notkę | subskrypcje |
|---|---|---|
| notka bez zaczepu | 0,61 | 0 |
| notka newsowa | 0,50 | 0 |

Seria ma sens, jeśli **część 4 ma więcej odwiedzin niż część 1** — to znaczy,
że ktoś wrócił. Jedna seria to cztery punkty pomiarowe, czyli za mało; wniosek
dopiero po dwóch–trzech seriach, czyli około 20 września.

Uwaga na pułapkę, w którą wpadłem dziś jedenaście razy: **notka zbiera zasięg
przez trzy dni** (1 dzień 7,1 wyświetlenia, 3 dni 28,5, 6 dni 54,0). Część 4
porównana z częścią 1 nazajutrz po publikacji pokaże spadek, którego nie ma.
