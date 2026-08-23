# E-002 — trwały ledger mutacji i potwierdzeń Agent V3

## Streszczenie

Eksperyment badał, czy V3 potrafi odróżnić zamiar, trwałą rezerwację, wysłanie mutacji, potwierdzony skutek i wynik niepewny, a po awarii lub restarcie nie wykonać automatycznego duplikatu. Dodano trwały ledger SQLite, atomową rezerwację klucza idempotencji, maszynę stanów, odzyskiwanie przerwanych prób, dokładne potwierdzanie obiektów i kwarantannę całej warstwy mutującej po `UNKNOWN`. Rdzeń ledgeru przeszedł 16/16 testów, test serii restacków 17/17, test granicy komentarza 19/19, a końcowa regresja 37/37 bezpiecznych plików. Nie wykonano sieci, modeli ani mutacji zewnętrznej. Koszt: 0 USD.

## 1. Pytania badawcze

1. Czy rezerwacja jest widoczna z drugiego połączenia przed kliknięciem?
2. Czy restart przed i po `dispatch` prowadzi do różnych, bezpiecznych stanów?
3. Czy `PENDING`, `UNKNOWN` i `CONFIRMED` blokują duplikat tej samej intencji?
4. Czy niepewna próba blokuje także inną mutację, zamiast pozwolić serii działać dalej?
5. Czy sukces może zostać zapisany bez referencji potwierdzającej ze źródła?
6. Czy liczniki dnia, historia celu i pamięć promocji zmieniają się dopiero po potwierdzeniu?
7. Czy artykuł można błędnie uznać za opublikowany na podstawie podobnego tytułu?

## 2. Hipotezy

- H1: atomowy zapis `PENDING` przed `dispatch` uniemożliwi równoległą lub restartową rezerwację tej samej intencji;
- H2: restart przed `dispatch` zakończy próbę jako `FAILED`, a restart po `dispatch` jako `UNKNOWN`;
- H3: `CONFIRMED` będzie wymagać niepustej `source_ref` uzyskanej po `dispatch`;
- H4: pierwsze `UNKNOWN` zakończy bieżącą serię i podda kwarantannie wszystkie kolejne mutacje;
- H5: liczniki i pamięć operacyjna będą odzwierciedlały wyłącznie wyniki potwierdzone;
- H6: dokładne ID szkicu oraz dokładny tytuł zastąpią podobieństwo tytułu przy potwierdzaniu artykułu.

## 3. Model stanu

| Stan | Znaczenie | Czy wolno ponowić automatycznie? |
|---|---|---|
| `PENDING` | rezerwacja istnieje, `dispatch` jeszcze nierozstrzygnięty | nie |
| `FAILED` | błąd wystąpił przed utrwalonym `dispatch` | tak, jako następna sekwencja |
| `UNKNOWN` | `dispatch` utrwalono, lecz brak jednoznacznego dowodu skutku | nie; globalna kwarantanna mutacji |
| `CONFIRMED` | źródło potwierdziło stan przez `source_ref` | nie dla tej samej intencji |

`source_ref` oznacza rzeczywiste ID obiektu, gdy platforma je ujawnia, albo wersjonowaną referencję potwierdzonego stanu interfejsu, gdy operacja nie ma dostępnego ID. Brak stabilnej referencji nie jest sukcesem.

## 4. Klucz idempotencji

Klucz jest SHA-256 kanonicznego, wersjonowanego obiektu zawierającego konto testowe, rodzaj działania, cel i SHA-256 treści. Nie zawiera czasu ani identyfikatora procesu. Dla tego samego klucza `PENDING`, `UNKNOWN` i `CONFIRMED` są stanami blokującymi. Dodatkowo dowolne nierozstrzygnięte `PENDING` lub `UNKNOWN` blokuje rezerwację innej mutacji, aby nie kontynuować działania po utracie wiedzy o stanie świata.

## 5. Implementacja badana

- `db.py` tworzy tabelę `mutation_attempts` i indeks po kluczu oraz sekwencji;
- `mutation_ledger.py` zapewnia `reserve`, `dispatch`, `confirm`, `unknown`, `fail` i `recover_pending`;
- `reserve` używa `BEGIN IMMEDIATE`, więc sprawdzenie i zapis są jedną sekcją krytyczną;
- `run.py` wywołuje odzyskiwanie dopiero po zdobyciu wyłącznego zamka procesu;
- przerwane `PENDING` bez `dispatched_at` staje się `FAILED`; z `dispatched_at` staje się `UNKNOWN`;
- browser rezerwuje próbę przed każdą mutacją, a `dispatch` utrwala bezpośrednio przed mutującym kliknięciem;
- `run.py` kończy dalsze mutacje dnia po dowolnej reprezentacji `UNKNOWN`;
- liczniki odpowiedzi, notek i komentarzy oraz historia celu są aktualizowane tylko dla `wyslane=True`; rytm obserwacji i subskrypcji tylko dla `zrobione=True`.

## 6. Rodzaje potwierdzeń

| Działanie | Referencja potwierdzająca | Wynik bez referencji |
|---|---|---|
| artykuł | dokładne ID bieżącego szkicu widoczne w opublikowanym obiekcie, dokładny tytuł i data | `UNKNOWN` |
| notka | ID obiektu odnalezionego po dokładnej próbce treści | `UNKNOWN` |
| komentarz | ID komentarza ze źródła | `UNKNOWN` |
| odpowiedź | ID odpowiedzi lub komentarza ze źródła | `UNKNOWN` |
| restack | ID obiektu restacku ze źródła | `UNKNOWN` |
| polubienie | wersjonowana referencja zmiany `aria-pressed`/stanu przycisku | `UNKNOWN` i koniec serii |
| obserwacja/subskrypcja | wersjonowana referencja zniknięcia właściwego przycisku | `UNKNOWN` |
| ustawienie konta | brak stabilnego ID lub wersji | zawsze `UNKNOWN`; brak fałszywego sukcesu |

## 7. Metoda testowa

Testy używały wyłącznie tymczasowych baz SQLite, atrap transportu i statycznej inspekcji kodu. Testy źródłowych ID pracowały na zamrożonych obiektach JSON. Serie przeglądarkowe zastąpiono atrapami elementów i zegara. Pełna regresja użyła projektowego `.venv` i `PYTHONIOENCODING=utf-8`.

Końcowy korpus obejmował 37 plików offline. Wyłączono `tests/test_czas.py`, ponieważ bada semantykę sygnałów i aktywną usługę systemd, podczas gdy usługi V3 są celowo unieruchomione w prototypie, oraz dziewięć plików `tests/platne`. `test_pobieranie.py` po inspekcji włączono: jego transport jest całkowicie zastąpiony atrapą.

## 8. Wyniki

| Miara | Wynik |
|---|---:|
| Testy maszyny stanów i potwierdzeń | 16/16 PASS |
| Testy pętli restacku po dodaniu kontrprzykładu `UNKNOWN` | 17/17 PASS |
| Test bezpieczeństwa prototypu | 14/14 PASS |
| Testy obserwacji | 34/34 PASS |
| Testy pola komentarza i wyjątku po dispatch | 19/19 PASS |
| Test zapisu wywołań i migracji kolumn | 16/16 PASS |
| Końcowa bezpieczna regresja | 37/37 plików PASS |
| Dokumenty badawcze / uszkodzone linki wykonywalne | 34 / 0 |
| Pliki Python objęte kompilacją zmian | 4/4 PASS |
| Wywołania modeli | 0 |
| Połączenia sieciowe | 0 |
| Mutacje zewnętrzne | 0 |
| Koszt | 0.00 USD |

## 9. Nieudane próby i korekty protokołu

Pierwsze uruchomienie czterech testów sąsiednich bez wymuszonego UTF-8 zakończyło `test_obserwacje.py` błędem `UnicodeEncodeError` po poprawnych wcześniejszych asercjach. Powtórzenie z `PYTHONIOENCODING=utf-8` przeszło. Błąd został sklasyfikowany jako wada protokołu środowiskowego, nie wynik badanej logiki.

Pierwsza szeroka komenda miała błędny wzorzec wyłączeń dla separatorów Windows. Uruchomiła 38 plików: 37 przeszło, a `test_czas.py` uzyskał 10 asercji poprawnych i 4 błędne. Błędy wynikały z oczekiwania aktywnego `TimeoutStartSec` w celowo unieruchomionym pliku usługi oraz z testu prawdziwego sygnału procesu. Ten przebieg nie został uznany za końcową regresję.

Ta sama pomyłka uruchomiła `test_pobieranie.py`, który przeszedł 14/14. Inspekcja wykazała, że jego transport jest atrapą; wcześniejsza etykieta „sieciowy” była nieaktualna. Następny przebieg 36/36 był poprawny dla ówczesnej listy, po czym test pobierania świadomie przywrócono. Ostateczny jawny zestaw uzyskał 37/37.

## 10. Zagrożenia trafności i ograniczenia

- Testy nie dowodzą zgodności selektorów ani nieoficjalnych endpointów z aktualnym interfejsem Substacka.
- Referencje UI dla polubienia, obserwacji i subskrypcji potwierdzają stan, ale nie są ID operacji platformy.
- Parsery ID zagnieżdżonych obiektów zostały zbadane na fixture'ach, nie na dodatnim teście live.
- Globalna kwarantanna po `UNKNOWN` zapobiega kolejnym mutacjom, ale automatyczna rekoncyliacja źródłowa `UNKNOWN` jest jeszcze osobnym otwartym zakresem.
- Ustawienie konta bez stabilnej referencji zawsze przechodzi do `UNKNOWN`; kod nie udaje sukcesu, ale ta ścieżka nie jest jeszcze operacyjnie użyteczna.
- Pełny replay scout–publikacja pozostaje otwarty w N-004.

## 11. Wniosek

H1–H6 utrzymano offline dla badanego korpusu. N-005 spełnia kryterium `FIXED_OFFLINE`: V3 nie uznaje samego kliknięcia za sukces, przechowuje próbę przed mutacją, rozróżnia awarię przed i po `dispatch`, nie ponawia wyniku niepewnego i nie zwiększa liczników bez potwierdzenia. Dodatni kontrakt live oraz automatyczna rekoncyliacja `UNKNOWN` pozostają otwarte i nie są implikowane przez wynik offline.
