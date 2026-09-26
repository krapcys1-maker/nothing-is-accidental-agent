# Nothing Is Accidental: prosty język, charakter i lekki humor

Próby na rzeczywistym API DeepSeek Flash, 26 września 2026.

## Co sprawdzałem

Notka i komentarz mają pomóc osobie spoza branży zrozumieć coś trudnego. Oceniam pięć rzeczy: czy wiadomo, o czym jest tekst; czy wyjaśnia krok między przyczyną a skutkiem; czy obywa się bez niepotrzebnego żargonu; czy brzmi jak rozmowa i ma lekkość; czy uproszczenie zachowuje sens faktów. To moja ocena redakcyjna próbek, nie badanie z udziałem czytelników ani dowód stałej jakości wszystkich przyszłych publikacji.

Materiały wejściowe to sprawdzone streszczenia źródeł technicznych, a nie zmyślone wiadomości. Komentarze powstawały w warunkach testowych pod tymi streszczeniami; nie są odpowiedziami zamieszczonymi pod prawdziwymi postami na Substacku. Odpowiedzi modeli zapisano bez ręcznego upiększania.

| Temat | Co czytelnik powinien zrozumieć | Źródło |
|---|---|---|
| Pamięć podręczna modelu | Co można wykorzystać ponownie podczas pisania odpowiedzi i dlaczego zajmuje to pamięć. | [Hugging Face — How caching works](https://huggingface.co/docs/transformers/main/en/cache_explanation) |
| Mieszanka ekspertów | Dlaczego można wykonywać mniej obliczeń, a nadal potrzebować dużo pamięci. | [Hugging Face — Mixture of Experts Explained](https://huggingface.co/blog/moe) |
| Odpowiadanie z dokumentów | Jak wyszukanie fragmentów dostarcza modelowi materiału bez ponownego uczenia go. | [Cloudflare — AutoRAG, opis z kwietnia 2025](https://blog.cloudflare.com/introducing-autorag-on-cloudflare/) |
| Kwantyzacja | Dlaczego mniej dokładny zapis liczb oszczędza zasoby i co trzeba sprawdzić w jakości odpowiedzi. | [Hugging Face — Quantization concepts](https://huggingface.co/docs/transformers/quantization/concept_guide) |
| Uprawnienia agenta | Różnica między zmniejszaniem ryzyka złej decyzji a ograniczaniem możliwych szkód. | [Anthropic — How we contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude) |

## Co nie działało

W początkowej notce model wyjaśniał termin „token”, ale zaraz wprowadzał „intermediate key/value representations from the attention layers”. Czytelnik otrzymywał następne pojęcia do rozszyfrowania. Końcówki często zmieniały się w raport o brakujących pomiarach, choć tekst nie stawiał ilościowej tezy wymagającej takich pomiarów.

Samo dopisanie „pisz naturalnie” dało za mało. Komentarze nadal zaczynały się od ogólników o ważnym rozróżnieniu i przechodziły do języka dokumentacji. Niektóre lżejsze porównania z kolei za mocno upraszczały fakty. W jednej próbie komentarz sugerował stały koszt kolejnego kroku po dodaniu pamięci podręcznej; w innej notka porównała ograniczone uprawnienia do wiertarki obracającej się w jedną stronę, choć taka wiertarka nadal może uszkodzić ścianę. Tych przykładów nie uznaję za udane wyjaśnienia.

## Co zmieniłem

- Główne instrukcje systemowe notek i komentarzy wprost określają czytelnika bez przygotowania technicznego i rozmowny, lekko dowcipny ton.
- Prompty pisarskie proszą o konkretną czynność i jej skutek, bez konieczności podawania nazw wszystkich elementów technologii.
- Humor ma wynikać z obserwacji, krótkiej uwagi lub trafnego porównania. Nie ma obowiązkowego żartu ani obowiązkowej puenty.
- Końcowa instrukcja po materiale źródłowym przypomina: wyjaśnij komuś pytającemu „ale co to właściwie znaczy?”. To pomaga nie przejmować żargonu ze źródła.
- Rozbiór materiału odróżnia brak pomiaru wielkości korzyści od braku samego mechanizmu. Opis ponownego użycia obliczeń nie staje się „tylko założeniem” dlatego, że nie podano benchmarku.
- Zostaje pogłębianie sprawy: przyczyna, kompromis, skutek, interes stron albo istotne pytanie. Nie ma obowiązku zmieścić wszystkich tych elementów w każdym komentarzu.

Artykuły nadal pisze Fable. Krótkie formy pozostają na DeepSeek Flash. Nie dodaję nowego płatnego etapu redakcyjnego do codziennego działania; testy porównawcze są jednorazowe. Nie zmieniam harmonogramu ani liczby publikacji.

## Jak przebiegał test

Najpierw porównałem kolejne instrukcje na tych samych sześciu przypadkach. Następnie dodałem cztery przypadki z dwóch innych tematów. W próbach notek rzeczywiście wykonywał się rozbiór materiału, a jego odpowiedź trafiała do pisarza. To nie była ręcznie przygotowana analiza udająca wynik modelu.

Po wdrożeniu uruchomiłem również całe funkcje tworzenia notki i komentarza, z kontrolą faktów i możliwością naprawy. Te funkcje kończą na szkicu; test nie wywołuje publikowania. Przekazany wyżej materiał został wyszukany i przeczytany podczas tego audytu. Nie był to test automatycznego wyboru tematów ani pobierania całego feedu.

Ważna obserwacja: kontrola faktów nie ocenia, czy tekst brzmi profesorsko. Komentarz zaczynający od „int8 zamiast float32” może być poprawny, a nadal źle dobrany do zwykłego czytelnika. Dlatego oceniałem także sam tekst, zamiast utożsamiać przejście weryfikatora z udanym głosem.

## Pełne zapisy

- [Pierwsza próba](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/before.json>)
- [Pierwsze doprecyzowanie](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/revision-one.json>)
- [Przepracowany prompt pisarski](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/revision-two.json>)
- [Próba po zmianie głównej instrukcji](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/release.json>)
- [Pierwsza pełna ścieżka z kontrolą faktów](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/full.json>)
- [Wszystkie aktualne prompty](<C:/Users/user/Desktop/agent project/agent-v2/docs/PELNE_PROMPTY_GLOSU.md>)


## Wynik końcowy

**39 przypadków pisania, 69 rzeczywistych wywołań DeepSeek Flash, 21 wyszukiwań odnotowanych przez klienta modeli.** Koszt zapisany w liczniku: **0.144862 USD** (około 0.14 USD). Stawki nie są potwierdzone fakturą; to szacunek. Wszystkie siedem przebiegów testowych zakończyło się `DONE`.

Siedem przypadków przeszło przez całe funkcje tworzenia tekstu z kontrolą faktów. Jeden wywołał naprawę. Pierwsza naprawa poprawiła fakt, ale ponownie wprowadziła język specjalistyczny. Zmieniłem więc także `naprawa.md`: poprawka ma wyjaśniać związek przyczynowy zwykłymi słowami i zachować pozostałe zdania, zamiast dokładać liczby i nazwy z publikacji naukowej. Następnie odtworzyłem ten sam wykryty błąd. Nowa naprawa oraz ponowna weryfikacja były rzeczywistymi, płatnymi wywołaniami; wcześniejszy zarzut odtworzono z zapisanego wyniku. Poprawka została przyjęta bez nowych zarzutów weryfikatora.

**Wdrożenie:** pięć plików potwierdzonych na serwerze 26 września o 11:31 UTC, bez różnic względem sprawdzanych wersji. Siedem uruchomionych plików testowych zakończyło się kodem 0. Harmonogram produkcyjny pozostał włączony; żaden z testów audytu nie wywołał publikowania.

Moja ocena: notki wyraźnie lepiej tłumaczą mechanizm, a w części komentarzy pojawił się lżejszy ton. Humor pozostaje nierówny i nie każda próbka zasługuje na publikację. Najbardziej przystępna końcowa notka dotyczy odpowiadania z dokumentów. W komentarzu o ekspertach pozostały słowa „router” i „token”; po naprawie komentarza o kwantyzacji nadal można skrócić długie zdanie. W notce o pamięci podręcznej zdanie „nothing crosses into tomorrow’s chat” jest za szerokie jako opis produktu — sam mechanizm nie przesądza, co aplikacja zachowuje między rozmowami. Weryfikator nie zatrzymał tego zdania. **Przejście kontroli nie jest automatycznym potwierdzeniem idealnego głosu ani wszystkich uproszczeń.**

## Końcowe teksty z pełnej ścieżki — bez ręcznej redakcji

Konto pisze po angielsku. Poniżej oryginalne odpowiedzi modeli.

### cache_note

> Imagine writing a sentence with a rule: before adding each new word, you must re-read everything you've written so far before choosing the next one. That's roughly how a language model generates text. Here's the trick that makes it bearable: while it reads back, it saves its working notes about each earlier word. The official name is a KV cache. When the next word comes along, the model pulls out those saved notes instead of doing all that work again. Each new word adds a new note, so the pile grows, and a longer conversation means more memory held in reserve. There are variants that cap the pile or let the oldest notes drop off. Notice what this is not: a memory of you. It holds notes for the current piece of text, not a finished answer, and nothing crosses into tomorrow's chat. The model is skimming its own work, one step behind itself.

### experts_comment

> The bit I'd underline: the router saves work, not space. Fewer experts run per token, so generation can speed up, but in the standard setup all of them still sit in memory — like keeping the whole staff on the payroll and calling only two into the room. And those experts aren't little chatbots with job titles.

### documents_note

> You know how a smart assistant can feel weirdly out of date? A technique called retrieval-augmented generation patches that. When you ask a question, the system first searches your documents for the relevant bits — split into chunks, turned into numbers, stored for search — then hands those chunks to the model along with your question. The model answers using text it never trained on. Updated files get picked up in the background. It's like giving a brilliant friend a stack of your notes before they answer. That won't make every answer correct, but it gives the model something current to work from.

### quantization_comment

> Smaller numbers don't run faster on their own — they take up less room, and that part is guaranteed. The speed can arrive anyway, though: when a model spends its time fetching weights instead of doing arithmetic, a smaller format means less to fetch, and models stored that way have run much faster on chips with no native way to multiply the smaller format. Rounding every weight is a bit like rounding every price on a long receipt: usually invisible, occasionally the total drifts.

Dane: [końcowa próba pełnych etapów](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/recheck.json>), [powtórzona naprawa](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/repair.json>), [koszty i przebiegi](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/summary.json>), [weryfikacja serwera](<C:/Users/user/Desktop/agent project/agent-v2/data/voice-natural-20260926/final-verification.json>).
