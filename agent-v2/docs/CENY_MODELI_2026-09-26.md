# Ceny nowych modeli przy zamianie — 26.09.2026

Polecenie właściciela: „napraw, żeby sprawdzało, jakie ma ceny model, jak zamienia,
albo niech zamienia 1:1 — dla obu botów” i „przetestuj na żywo wszystko, żadnego
zgadywania”.

## Co było nie tak

Oba boty same przechodzą na nowszą wersję modelu w tej samej rodzinie (NIE:
`nowe_modele.py`, drugi bot: `wersje_modeli.py`). Następca nie ma wpisu w cenniku,
a dostawcy **nie podają cen** w liście modeli (`GET /models` Anthropic, OpenAI
i DeepSeeka zwraca same nazwy).

| bot | jak liczył następcę | przykład | cena u dostawcy |
|---|---|---|---|
| NIE | stawka rodziny 1:1 | `claude-opus-5-5` jak Opus 5: 5 / 25 USD za mln tokenów | 4 / 20 |
| drugi bot | **podwójna** stawka poprzednika | `claude-opus-5-5` 10 / 50, `gpt-6-sol` 8 / 40 | 4 / 20 i 2 / 10 |

U drugiego bota księgi pokazywały 2,5–4 razy więcej, niż modele kosztowały, więc
miesięczny sufit kończył się przed końcem miesiąca. W NIE przy okazji
wyszło, że `claude-sonnet-5` stał w cenniku po 3/15 — zapowiedziana na 1 września
podwyżka nie weszła, cena to 2/10.

## Skąd cena — sprawdzone 26.09.2026

- **Anthropic:** `https://platform.claude.com/docs/en/about-claude/pricing.md`
  (markdown). Opus 5.5: 4 USD wejście, 20 wyjście, cache 0,20 (0,05 wejścia);
  Opus 5: 5/25, cache 0,50; Sonnet 5: 2/10; Fable 5.1: 10/50, cache 0,25.
- **OpenAI:** `https://developers.openai.com/api/docs/pricing`, tryb standardowy,
  krótki kontekst. `gpt-6-sol`: 2 / cache 0,20 / 10; `gpt-5.6-sol`: 4 / 0,40 / 20
  (tabela Daybreak); `gpt-6-astra`: 10 / 1 / 50.
- **Nie z pośrednika.** OpenRouter podawał tego dnia `gpt-5.6-sol` po 2/10, a OpenAI
  po 4/20 — lista pośrednika nie jest cennikiem dostawcy.

## Co się zmieniło (oba boty, ta sama zasada)

1. `cennik_dostawcy.py` czyta oficjalną stronę dostawcy zwykłym GET, sprawdza nagłówek
   tabeli (przestawione kolumny = odmowa, nie pomyłka) i wiarygodność liczb
   (wejście < wyjście, cache ≤ wejście, nie 10× dalej od poprzednika). DeepSeeka
   (taryfa szczytowa) i modeli obrazów nie czyta — dla nich 1:1.
2. Przy zamianie cena następcy jest sprawdzana **przed** płatną próbą i zapisywana
   w stanie zamian; każdy start procesu ją odczytuje.
3. Gdy cennika nie da się odczytać — **1:1 jak poprzednik**, nigdy podwójnie.
4. Następca droższy o ponad 25% (wejście + wyjście) **nie wchodzi sam** — zostaje
   obecny model, a log mówi, że decyzja należy do właściciela.
5. Zamiany zrobione wcześniej dostają cenę przy najbliższym dziennym sprawdzeniu
   (darmowy GET, bez ponownej próby modelu).
6. Cenniki uzupełnione ręcznie o modele już używane (Opus 5.5, GPT-6 sol, Sonnet 5)
   i stawki cache Claude.

Darmowe testy nie chodzą do sieci (`config.W_TESCIE`); pierwsza wersja pobrała w teście
prawdziwy cennik — złapane przy pierwszym uruchomieniu.

## Testy na żywo (26.09.2026, serwer produkcyjny, bez płatnych wywołań)

NIE, po wdrożeniu `809b67b`:

- cennik pobrany z serwera przez nowy kod: Opus 5.5 4/0,20/20, Opus 5 5/0,50/25,
  Sonnet 5 2/0,20/10, Fable 5.1 10/0,25/50, GPT-6 sol 2/0,20/10, GPT-5.6 sol 4/0,40/20;
- produkcyjny `config.stawka_modelu` liczy Opus 5.5 po 4/20: 10 tys. wejścia i 2 tys.
  wyjścia = 0,080 USD (było 0,100);
- brak zamian czekających na decyzję.

Drugi bot dostał tę samą poprawkę w swoim repozytorium (wdrożona 27.09 o 00:01 UTC)
i przeszedł ten sam test na żywo: cennik pobrany z serwera, stawki modeli w użyciu
według dostawcy, raport wersji bez zmian.
