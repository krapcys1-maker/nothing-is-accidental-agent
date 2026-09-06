# Rozumowanie DeepSeeka — pomiar, który obalił zalecenie audytu

6 września 2026. Zewnętrzny audyt wskazał to jako **największą nietkniętą
dźwignię kosztową**: ~9 USD miesięcznie, 22–30% budżetu październikowego.
Sprawdziłem. Dźwignia istnieje, ale **nie da się jej pociągnąć bez straty**.

## Co było prawdą w zarzucie

`llm._call_deepseek` wysyłał `model`, `max_tokens`, `messages` — i nic więcej.
DeepSeek na `chat/completions` **rozumuje domyślnie**. Jedyne pokrętło, jakie
konto miało (`config.DEEPSEEK_EFFORT`), trafia wyłącznie do `/responses`, czyli
do pięciu etapów z wyszukiwaniem. Pozostałe dziewiętnaście nie widziało go
nigdy. Zdanie z `KOSZT_2026-09-05.md` („DeepSeek ma jedno wspólne
`DEEPSEEK_EFFORT=low` — już najniższe") było dla nich nieprawdziwe.

## Co było nieprawdą — i to zmienia zalecenie

Audyt twierdził, że domyślnie jest `reasoning_effort: high`, i zalecał
przestawić etapy wyboru na `low`. **Zapytałem API zamiast dokumentacji.**
To samo pytanie, `deepseek-v4-flash`, cztery warianty:

| ustawienie | wyjście | z tego rozumowanie | odpowiedź |
|---|---|---|---|
| brak parametru (jak było) | 53 | 42 | poprawna |
| `disabled` | **10** | 0 | poprawna |
| `low` | 91 | 80 | poprawna |
| `high` | 121 | 110 | poprawna |

**Domyślne ustawienie nie jest `high` — jest niższe niż `low`.** DeepSeek
dobiera wysiłek sam. Zalecane `low` byłoby **droższe** niż stan dzisiejszy.

## Prawdziwy test: pięć powtórzeń na prawdziwym prompcie `cele`

12 celów z żywego korpusu, prompt 6 308 znaków:

| wariant | wyjście śr. | USD/wyw. | wybranych celów | zgodność z „dziś" |
|---|---|---|---|---|
| dziś | 11 721 | 0,0077 | 2,4 (2–3) | — |
| `low` | 13 507 | **0,0089** | 2,2 (2–3) | **5 / 5** |
| `disabled` | **719** | **0,0005** | **5,6 (3–7)** | **0 / 5** |

`disabled` jest **16 razy tańsze na etapie** i wybiera **ponad dwa razy więcej
celów**, nie zgadzając się z bazą ani razu na pięć prób.

## Dlaczego to i tak nie jest oszczędność

82 wywołania `cele` na 7 dni, koszt wyjścia `comment` 0,0044 USD:

| pozycja | USD / 7 dni |
|---|---|
| oszczędność na etapie `cele` | **+0,60** |
| 262 dodatkowe cele, z czego połowa zagadana | **−0,58** |
| **bilans** | **+0,02** |

Zero. A cele są przy tym gorsze. Przy stu procentach zagadanych celów bilans
wychodzi **−0,56 USD tygodniowo**, czyli wyłączenie rozumowania byłoby
**droższe** niż jego zostawienie.

## Co zrobiłem

Zbudowałem przełącznik `config.DEEPSEEK_MYSLENIE` (per etap) i wpiąłem go
w `_call_deepseek`. **Tablica jest pusta**, więc konto zachowuje się dokładnie
tak jak dotąd; pierwsza asercja w teście pilnuje właśnie tego. Etap wejdzie do
tablicy dopiero wtedy, gdy pomiar pokaże, że jego decyzja się nie zmienia.

## Czego nie zmierzyłem

Etapów, które **piszą**: `comment`, `restack`, `bank`, `forma`, `synthesis`,
`note_tani`. Tam „ta sama decyzja" nie jest miarą — trzeba porównać teksty,
a to osobny eksperyment. `comment` to największa pozycja wyjścia w całym
rachunku (1,29 USD / 7 dni, 293 wywołania) i jako jedyny jest wart tej pracy.
`note_tani` pisze notki i tego bym nie ruszał bez bardzo mocnego powodu.

## Wniosek dla następnej sesji

Dźwignia była prawdziwa, ale **znak był odwrotny, niż wskazywał audyt**:
zalecane `low` kosztuje więcej, a jedyne tanie ustawienie psuje wybór.
Koszt sprawdzenia: około 0,10 USD i dwadzieścia minut. Koszt uwierzenia
audytowi na słowo: dwa razy więcej płatnych komentarzy o gorszych celach.
