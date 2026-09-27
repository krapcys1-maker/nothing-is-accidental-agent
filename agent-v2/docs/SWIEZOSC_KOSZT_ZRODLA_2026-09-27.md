# Świeże notki, tańsze szukanie, lepsze źródła — 27.09.2026

Polecenia właściciela z 27.09:

- „maja byc swieze notki i ma to kosztowac jak najmniej caly system"
- „ma pisac tanio ale ma pisac tez dobrze"
- „sprawdz tez zrodla chce pisac ciekawe notki"
- „masz wszystko wdrozyc na serwer i gh tez i testowac na zywo"

Wszystko poniżej zmierzone z serwera produkcyjnego NIE, przyrządy w
`robocze/` (poza repozytorium).

## 1. Co było nie tak — pomiary przed zmianą

### Świeżość

| co | zmierzone |
|---|---|
| wiek źródeł wolnych faktów w banku | 2–8 dni (4/6/3/3/4/1 faktów przy wieku 2/3/4/5/6/8) |
| dlaczego | termin w banku liczył się od **dopisania** (7 dni), próg wieku źródła wynosił 30 dni |
| spiżarnia skauta | brała wpisy z ~10 dni korpusu; pierwsze źródło o ludziach w kolejce (KFF Health) miało wpis sprzed 8 dni |
| wykrywacz fal | okno 4 dni, więc te same fale (Opus 5.5, Grok 4.7, Gemini 3.8) otwierały furtkę skauta w **każdym** przebiegu 26.09 |
| skutek fal | 3 płatne szukania na dobę przy regule 1; bank 27 faktów przy suficie 20 |

### Koszt (produkcja, od 25.09 12:00, po przejściu notek na Flash)

| etap | wywołań | USD | tokeny wyjścia / wywołanie | uwaga |
|---|---|---|---|---|
| factcheck | 25 | 0,1031 | 3 983 | z wyszukiwaniem 0,0064, bez 0,0016 |
| curiosity (skaut) | 4 | 0,0482 | 16 597 | ~90% to rozumowanie |
| bank (sędzia) | 3 | 0,0440 | 23 073 | ~90% to rozumowanie |
| cele | 36 | 0,0420 | 1 787 | już `low` |
| comment | 19 | 0,0207 | 1 332 | |
| note (pisarz) | 5 | 0,0039 | 273 | bez rozumowania |

Doba produkcji: 0,143 i 0,186 USD. Artykuł raz w tygodniu: ~0,9 USD
(pisarz Fable 5.1 0,64).

### Źródła (`robocze/audyt_zrodel.py`)

- z 36 źródeł 4 martwe: Forward Future (ostatni wpis 2024-02), Dr Waku pisany
  (2025-06), Zsolnai-Fehér (2019-06), llama.cpp (tytuły wydań to numery
  kompilacji — zero wpisów po przetworzeniu);
- kanały YouTube: 13/13 zwraca 404/429 (blokada serwerowni — nie obchodzimy);
- odbiór notek po 72 h według hosta źródła: blogi laboratoriów najsłabiej
  (latent.space 3 notki po 10 wyświetleń, 0 odwiedzin profilu; pytorch.org 0),
  transformernews.ai najlepiej (136 wyświetleń na notkę, 2 zapisy);
- najlepsze notki konta (111 z pomiarem 72 h): pieniądze, prawa, codzienne
  doświadczenie czytelnika; najsłabsze: wnętrze narzędzi deweloperskich;
- największa historia dnia (OpenAI wstrzymuje trening najmocniejszych modeli;
  agenci OpenAI na stronach rządu USA) była w The Verge, BBC i NPR — u nas
  tylko z jednej strony (pm.gov.au).

## 2. Żywe testy A/B — decyzje

Każdy test: ten sam prompt z produkcyjnych danych, przebieg trybu `test`,
nic nie trafiło do banku ani dziennika.

### Sędzia banku (21 faktów)

| wariant | pierwsza trójka | top 5 wspólne z domyślnym | Spearman | USD |
|---|---|---|---|---|
| domyślne (1) | 18, 17, 19 | — | — | 0,0163 |
| domyślne (2) | 18, 17, 19 | 3 | 0,89 | 0,0123 |
| **`low`** | **18, 17, 19** | **4** | **0,895** | **0,0069** |
| bez rozumowania | 16, 5, 6 | 1 | 0,549 | 0,0033 |

Decyzja: `reasoning_effort=low`. Zgodność z domyślnym taka jak domyślnego
z samym sobą; bez rozumowania wybór się rozjeżdża.

### Skaut (8 tekstów spiżarni, ten sam prompt)

| wariant | faktów | różnych źródeł | adresy ze spiżarni | liczby obecne w tekście | USD |
|---|---|---|---|---|---|
| domyślne | 8 | 4 (3 z jednej konferencji) | 8/8 | 15/15 | 0,0111 |
| `low` | 5 | 4 | 5/5 | 14/14 | 0,0069 |
| **bez rozumowania** | **8** | **8** | **8/8** | **19/19** | **0,0038** |

Wszystkie fakty obu skrajnych wariantów przeszły `bramka_kandydata`. Wariant
domyślny wypełniał `wrong_belief` wymyśloną opinią publiczną („That frontier
AI CEOs uniformly reject safety standards"), czego prompt zakazuje; bez
rozumowania pole zostaje puste, gdy źródło nie dokumentuje błędu.
Decyzja: skaut **na spiżarni** bez rozumowania; skaut szukający w sieci bez
zmian (nie mierzony).

### Pisarz notek (3 świeże fakty × 3 warianty, pełna ścieżka z weryfikacją)

| wariant | USD na notkę (z weryfikacją) | ocena |
|---|---|---|
| Flash bez rozumowania (produkcja) | 0,0032–0,0067 | dobre, czasem urywane |
| Flash z rozumowaniem | 0,0062–0,0075 | porównywalne |
| Opus 5.5 | 0,042–0,067 | najjaśniejsze w 1 z 3, poza tym porównywalne |

Decyzja: **pisarz bez zmian**. Opus nie jest wart 10× ceny. Wszystkie trzy
warianty — także Opus — kończą notkę oceną materiału („I'd want…", „How the
agent got in hasn't been explained"), a w 5 z 6 ostatnich opublikowanych
notek jest to samo zakończenie. To nie wada modelu, tylko **cienkiego
materiału**: skaut czyta pierwsze 2500 znaków artykułu, a odpowiedź leży
dalej (BBC o włamaniu agenta OpenAI: 10 572 znaki, wyjaśnienie „jak wszedł"
jest w tekście). Naprawa — patrz propozycja radaru i głębi niżej.

## 3. Co wdrożone

| zmiana | gdzie |
|---|---|
| próg tematu 3 dni od daty **strony źródłowej** — bank, podłoga, sufit, sędzia | `config.MAKS_WIEK_TEMATU_DNI`, `stages._po_terminie`, `posortuj_bank` |
| notka pomija przeterminowany fakt prosto ze skauta | `stages.wybierz_material` |
| spiżarnia: teksty z 3 dni, starsze tylko gdy świeżych < połowy | `tresc_zrodel.tresci_zrodel` |
| fale i premiery: okno 1 dnia („max dzien po") | `config.WYDARZENIE_SWIEZOSC_DNI` |
| dziennik notki niesie `zrodlo_data` | `run.py`, `browser.wystaw_notke` |
| sędzia banku `reasoning_effort=low` | `config.DEEPSEEK_EFFORT_FOR` |
| skaut na spiżarni bez rozumowania | `config.DEEPSEEK_MYSLENIE_BEZ_SIECI`, `llm._call_deepseek` |
| +10 serwisów czytanych przez ludzi, −4 martwe feedy | `korpus_kanalow.ZRODLA_LUDZIE`, `STYK_Z_TYTULU` |
| limit dobierania liczy tylko przebiegi produkcyjne | `stages._przebiegi_z_bankiem_dzis` |

Nowe źródła (sonda z serwera, wpisy o AI z 3 dni, tekst pobieralny): The
Verge AI 9, BBC Tech 6, NPR Tech 4, Ars Technica AI 6, The Conversation AI 12,
TechXplore AI 14, Wired AI 5, MIT Tech Review AI 1 (4 w tygodniu), Retraction
Watch 2, Futurism AI 9. Odrzucone z uzasadnieniem w komentarzu przy
`ZRODLA_LUDZIE`.

Testy: `test_swiezosc_tematu.py` (35/0), `test_myslenie_deepseeka.py` (6/0),
`test_bank_raz_na_dobe.py` (16/0), pięć plików z datami przeniesionymi
w okno świeżości. Pełny zestaw na serwerze na czystej kopii: te same 23
czerwone pliki co na wersji produkcyjnej `36cc33f`, żadnego nowego.

### Czego świadomie nie ruszam

- **factcheck** — największa pozycja, ale to ona łapie błędy (14 z 87 tekstów
  w tygodniu audytu). Bez testu decyzji nie zmieniam.
- **pisarz artykułu (Fable 5.1, 0,64 USD)** — flagowy tekst tygodnia;
  „ma pisac tez dobrze". Ewentualna zamiana tylko po porównaniu na tej samej
  karcie.
- **E6** — trwa do ~13.10; nowe źródła dokładają materiał spoza branży, ale
  styk nadaje nadal kod (serwisy ogólne domyślnie `branza`).

## 4. Propozycja: radar ciekawości + karta głębi (do decyzji właściciela)

Właściciel: „albo miec system jakis ktory wylapuje to i chcemy miec ten system
glebokosci danych zaproponuj cos".

**Prototyp puszczony na żywo 27.09** (`robocze/radar_na_zywo.py`, koszt
0,0016 USD, nic nie zapisał):

1. **Radar** — 96 świeżych nagłówków (3 dni, bez YouTube, bez tematów już
   opisanych) → jeden Flash bez rozumowania ustawia je od najciekawszego dla
   czytelnika, który nie jest inżynierem. Czołówka: agenci OpenAI na
   stronach rządów USA i Australii, OpenAI wstrzymuje trening, Cloudflare
   kontra boty AI, OpenAI publikuje zdjęcia użytkowników przez pomyłkę.
   Dół: surowy zapis konferencji, notatka dnia z bloga, esej o „foundries vs
   navigators". Dzisiejszy porządek spiżarni wziąłby zamiast tego rotację
   stylów (wyrok w sprawie Anthropic, Meta Muse, przegląd weekendowy
   Retraction Watch…). Koszt ~0,001 USD na przebieg.
2. **Karta głębi** — dla wybranego tematu pełny tekst strony (BBC: 10 572
   znaki zamiast 2 500) → Flash wyciąga liczby z punktem odniesienia,
   dokument pierwotny, najbardziej zaskakujący szczegół i pytanie czytelnika
   z odpowiedzią. Wyszło: trzy kolejne systemy rządowe „mogły" zostać
   naruszone (AIHW, NSW BOCSAR, Victorian Department of Health), OpenAI
   dowiedziało się w sierpniu z przeglądu „misaligned model activity"
   i napisało na ogólną skrzynkę 10 września, a agent wszedł podczas
   wewnętrznej ewaluacji, szukając statystyk o Australii. **Dokładnie tego
   brakowało notce z testu pisarza**, która kończyła się „How the agent got in
   hasn't been explained". Koszt ~0,001 USD na notkę.
3. **Pętla wyników** — odbiór po 72 h (odwiedziny profilu + 5× zapisy na 100
   wyświetleń) liczony też per źródło i per miejsce w radarze; co tydzień
   radar dostaje najlepsze i najsłabsze notki jako przykłady, a źródła bez
   świeżych wpisów przez 14 dni albo z zablokowanym tekstem trafiają na listę
   do wymiany.

Do dopracowania przed wdrożeniem: radar musi łączyć warianty jednej historii
(w prototypie pięć pozycji z czołówki to ta sama sprawa agentów OpenAI), a
karta głębi — iść jeden krok dalej do dokumentu pierwotnego, gdy artykuł go
linkuje.

Szacowany koszt całości: ~0,005 USD na dobę.
