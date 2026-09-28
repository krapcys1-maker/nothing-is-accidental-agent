# Obserwatorium obu kont — dane, dziennik zmian, silnik statystyk (28.09.2026)

Polecenie właściciela z 28.09:

> „znajdź sposób na gromadzenie danych i z NIA, i z Nothing Is Accidental —
> przyrost subskrybentów, wyświetlenia, followersi; trzeba zrobić jakiś dziennik
> zmian wykonywanych, daty, kiedy zostały wprowadzone, i jakiś silnik, który
> mierzy statystyki (…) tempo przyrostu (…) badania nad Substackiem, jak
> najlepiej rozwijać konto, plus jakie kroki, żeby Nothing Is Accidental było
> polem doświadczalnym, a NIA brała już tylko dobre, działające rozwiązania"

## Co było przed zmianą

Oba boty zapisywały już prawie wszystko, w tym samym kształcie (NIA to fork):

| plik | co | jak często |
|---|---|---|
| `wzrost.jsonl` | subskrybenci, darmowi, obserwujący, nasze subskrypcje i rekomendacje | każdy przebieg (NIE ~5,6/dobę od 31.08, drugie konto od 07.09) |
| `statystyki.jsonl` | każda treść: wyświetlenia, powierzchnie (Feed, Profil…), odbiorcy (subskrybenci / obserwujący / obcy), reakcje, odwiedziny profilu, zapisy i obserwacje z tej treści | każdy przebieg (NIE 18,6 tys. pomiarów od 25.08) |
| `zrodla.jsonl` | skąd ruch i zapisy (okno Substacka, 30 dni), zapisy przypisane treściom | każdy przebieg |
| `dziennik.jsonl` | działania bota: notki, komentarze, restacki, polubienia, obserwacje… | na bieżąco |
| `czytelnicy.jsonl` | listy obserwujących i subskrybentów (nazwy!) | każdy przebieg |
| `agent-v2.db` | koszt każdego wywołania modelu | na bieżąco |
| NIA `aktywacje.jsonl` | aktywacje presetu (zmiany konfiguracji z odciskiem) | przy zmianie |

Brakowało trzech rzeczy:
- jednego miejsca, które zbiera oba konta tak samo,
- dziennika zmian z godzinami,
- silnika, który z tego liczy tempo i skutki.

## Co jest teraz (`agent-v2/obserwatorium.py`)

- **`zbierz`** (codziennie 03:40 UTC, `systemd/obserwatorium.timer`) liczy dla
  obu kont każdą dobę UTC. Wynik trafia do `data/obserwatorium/dni_<konto>.json`:
  - stan na koniec doby,
  - nowych obserwujących i subskrybentów (pierwsze pojawienie się na liście; tylko liczba),
  - przyrosty wyświetleń, wyświetleń od obcych, odwiedzin profilu, reakcji,
    zapisów i obserwacji z treści (także osobno dla notek, artykułów, komentarzy),
  - działania bota i działania skierowane do siostry,
  - koszt produkcji.

  Doby, których nie da się już policzyć z plików bota, zostają z poprzedniego
  zapisu. Najnowsze źródła ruchu i zapisów idą do `zrodla_<konto>.json`.
- **Dziennik zmian** (`data/obserwatorium/zmiany.jsonl`), dopisywany codziennie
  bez duplikatów:
  - wdrożenia obu botów z `git reflog` serwera — dokładne godziny, bo reflog
    kasuje się po 90 dniach, więc import jest codzienny,
  - scalenia PR-ów NIA jako zmiany nazwane,
  - aktywacje presetu NIA (tylko przy zmianie odcisku),
  - zmiany z rejestru poligonu (E0, E6–E10, przestawienie na AI) z godzinami wdrożeń,
  - wpisy ręczne: `python agent-v2/obserwatorium.py zmiana --konto NIE|NIA|oba|platforma --rodzaj recznie|platforma|incydent|eksperyment|zmiana --opis "..."`.
- **Raport** (`data/obserwatorium/raport.md`, także `obserwatorium.py raport`):
  - stan i tempo obu kont obok siebie,
  - ostatnie 14 dób,
  - skąd przychodzą zapisy,
  - co przynosi wyświetlenia i zapisy (wg rodzaju treści),
  - zmiany nazwane zgrupowane po dobie ze skutkiem: 14 dni przed/po i różnica
    różnic względem drugiego konta,
  - lista wdrożeń,
  - jakość danych.

**Zasady:**
- tylko odczyt danych obu botów, żadnych nowych zapytań do Substacka;
- do katalogu NIA nic nie trafia, a jej bazę czytamy z `immutable=1`, więc
  SQLite nie zostawia tam plików (sprawdzone: 42 pliki przed i po);
- bez danych osobowych: z list czytelników wyłącznie liczby, pole
  `kto_sie_zapisal` pomijane.

## Definicje

- **Netto** — zmiana stanu doba do doby (tylko między sąsiednimi dobami z pomiarem).
- **Nowi na profilu** — uchwyt pojawił się pierwszy raz na liście profilu.
  To **dolna granica**, nie zapisy brutto: listy profilu są niepełne (28.09:
  24 z 27 subskrybentów), więc odejść z nich nie liczymy (poprawione 28.09 —
  wcześniej stało tu „churn = nowi − netto"). Zapisy brutto daje panel źródeł.
- **Tempo** — subskrybenci na tydzień w oknie 28 dni (od ostatniego stanu przed
  oknem albo od pierwszego pomiaru, gdy ruszyły w środku okna) i ten sam
  przyrost jako % średniego poziomu w oknie.
- **Wyświetlenia (główny licznik)** — notki i artykuły, mierzone w każdym
  przebiegu. Komentarze i odpowiedzi osobno, bo bot mierzy je z przerwami.
- **Doba z pomiarem** — od pierwszego do ostatniego odczytu treści; doby
  wcześniejsze to brak danych, nie zera (średnie „przed zmianą").
- **Obcy** — widzowie spoza obserwujących i subskrybentów („Unconnected").
  Ich udział mówi, ile zasięgu to nowi ludzie.
- **Subskrybenci na 1000 wyświetleń** — konwersja całego konta w oknie.
- **Różnica różnic (RR)** — (po − przed) na koncie ze zmianą minus (po −
  przed) na drugim koncie w tych samych dniach. Usuwa wspólne tło (algorytm
  Substacka, dzień tygodnia), ale nie różnice kont. To wskazówka, a nie dowód;
  dowodem jest eksperyment przeplatany (`eksperymenty.py`).

## Pierwszy odczyt — 28.09 (doby do 27.09)

Tabela obu kont i wnioski z porównania leżą w lokalnym rejestrze
(`docs/POLIGON_I_PRODUKCJA.md`), bo zawierają liczby drugiego konta. Z tego
konta:

- 27 subskrybentów (26 bez siostry) i 41 obserwujących;
- netto +18 subskrybentów i +30 obserwujących w 28 dni;
- 655 wyświetleń w 7 dni, z czego 42% od obcych;
- 4,5 subskrybenta na 1000 wyświetleń (28 dni).

Wyświetlenia wzrosły z ok. 50–60 dziennie (14–21.09) do ok. 70–130 (22–27.09).
Zapisy przychodzą głównie ze środka Substacka (13 z 21 „Substack", 8 „Direct
to App").

**Skąd są subskrybenci — po korekcie z 28.09.** Panel Substacka (30 dni,
28.08–27.09) pokazuje 21 zapisów:
- **Substack 13**, z tego **7 przypisanych notkom** i 6 z innych miejsc
  (profil, rekomendacje, wyszukiwarka, aplikacja);
- **Direct to App 8**.

Zapisy przypisane konkretnym pozycjom (wszystkie odczyty, maksimum na pozycję)
to 10 zapisów przy 6 pozycjach. Karty pozycji mówią: **5 z restacków, 3 z
notek**, 1 spoza dziennika bota. Stan konta w tym czasie: 7 → 27.

> **Korekta.** Pierwsza wersja tego dokumentu (i raportu) podała odwrotnie:
> „zapisy dają artykuły, notki 0". Błąd przyrządu:
> - za „zapisy z artykułu" wzięte zostało `signups_within_1_day`, czyli każdy
>   zapis w dobie po wysłaniu artykułu, skądkolwiek przyszedł (16 przy 5
>   artykułach);
> - przypisania do notek (karta „new subscribers", pole `zapisy_darmowe`)
>   obserwatorium nie czytało.
>
> Tę samą pułapkę projekt opisał 02.09 i 06.09, a komentarz w `browser.py`
> wciąż mówił coś przeciwnego (poprawiony). Właściciel zauważył, że liczby się
> nie sumują: „z notek 0, to skąd reszta subskrybentów?".

Drugie konto pokazuje ten sam kierunek: zapisy przypisane pozycjom to głównie
restacki. Pierwsze pytanie badawcze (B1) brzmi więc:
- dlaczego restack (nasz komentarz do cudzego wpisu) zamienia czytelnika
  w subskrybenta lepiej niż własna notka,
- co kryje się za „Direct to App" i „Other", których nie da się przypisać
  treści.

## Dlaczego nie mamy pełnych danych o źródłach zapisów

Pytanie właściciela z 28.09: „czemu pełnych danych nie mamy, o co chodzi?".
Sprawdzone na surowym drzewie panelu źródeł obu kont (to, co Substack oddaje
przez `/api/v1/publication/stats/growth/sources`):

| gałąź panelu | rozbicie | co wiemy |
|---|---|---|
| Substack → **Notes** | **na konkretne notki** (numer + „Autor: początek tekstu") | która notka przyniosła zapis, także cudza (wtedy zwykle był pod nią nasz komentarz) |
| Substack → **Other** | brak | zapis w Substacku poza notką: profil, Explore, wyszukiwarka, strona wpisu, ekran główny aplikacji |
| Substack → Recommendations, Trackbacks | brak (dziś 0) | polecenia innych publikacji, linki z innych wpisów |
| **Direct to App** | brak | zapis w aplikacji bez zapisanego źródła |
| Direct, e-mail, wyszukiwarki | brak | ruch spoza Substacka |
| **artykuły** | **nie występują jako źródło** | przy artykule jest tylko `signups_within_1_day` — okno doby po wysyłce, nie przypisanie |

Czyli:

- **Braku po stronie Substacka nie da się dociągnąć.** „Other" i „Direct to
  App" to u nas ponad połowa zapisów (NIE: 14 z 21), a przypisanie do
  artykułu nie istnieje w API. Substack sam tego nie wie albo nie pokazuje.
  Jedyna droga do tych odpowiedzi to eksperyment: zmieniamy jedną dźwignię,
  a drugą zostawiamy, i patrzymy na całkowity przyrost (np. tydzień z
  artykułem wobec tygodnia bez; więcej restacków wobec mniej).
- **Co było naszą dziurą i jest poprawione (28.09):**
  - obserwatorium brało okno doby po artykule za przypisanie i nie czytało
    kart notek;
  - nie rozróżniało notek własnych od cudzych — zapis spod cudzej notki z
    naszym komentarzem to teraz `komentarz_pod_cudza_notka`.
- **Co zostaje do decyzji:**
  - drugie konto nie czyta kart „new subscribers" przy notkach (fork sprzed
    03.09); jego panel źródeł działa, więc przypisanie mamy, ale bez imion
    i dat pojedynczych zapisów;
  - historia sprzed pierwszego odczytu (NIE 02.09, drugie konto 07.09) jest
    tylko w oknach 30 dni.

## Audyt danych — 28.09

Pytanie właściciela: „sprawdź wszystko dokładnie, czy się zgadzają dane".
Każdą liczbę zestawiłem z drugim, niezależnym źródłem. Skrypty tylko czytają
(`robocze/audyt_*.py`, poza repozytorium).

**Zgadza się:**

| sprawdzenie | wynik |
|---|---|
| pliki botów: składnia, czas UTC, luki dób, puste wiersze | bez błędów |
| gałąź „Notes" panelu = suma zapisów przypisanych notkom | zgodne |
| obserwatorium = surowe pliki (przeliczenie od zera) | zgodne |
| notki z numerem w dzienniku bota = notki zmierzone w przebiegu | 162 z 162 |
| numer restacku to nasza notka (bot szuka go na własnym profilu po treści) | tak |
| zapisy z tabeli ruchu = suma źródeł panelu (dwa różne endpointy) | we wszystkich odczytach obu kont |
| działania do siostry w 7 dniach | 24 = 16 polubień + 8 komentarzy |

**Nie zgadzało się — naprawione i wdrożone 28.09 (`f9b6f2a`, `3acddc7` i następne):**

| błąd | skala | poprawka |
|---|---|---|
| komentarze i odpowiedzi bez pomiaru: limit 60 pozycji zjadały notki | od 04.09 zero pomiarów | własny budżet: 60 najnowszych z 3 dób; żywy pomiar 28.09 06:30: 24 komentarze i 3 odpowiedzi (wcześniej 0) |
| numer odpowiedzi brany z adresu wątku (`gdzie`), czyli numer wątku, nie naszej odpowiedzi | 44 odpowiedzi: 12× nasza notka mierzona drugi raz (54 wyświetlenia podwójnie), 32× cudzy wpis (2 zmierzone, 44 wyświetlenia) | tylko własny numer; w obserwatorium jedna pozycja = jeden szereg, cudze numery odrzucone |
| koszt: wywołania bez przebiegu wypadały z sumy | 189 wywołań, 4,53 USD (02–13.09) | koszt w trzech częściach: produkcja / test / bez przebiegu |
| średnia „przed zmianą" liczyła doby bez pomiaru jako zera | skutek zmian z pierwszych dni pomiarów wychodził z kosmosu (np. „20 → 236 wyświetleń/dobę") | „za mało danych przed (n dni)"; różnica różnic tylko przy pełnych oknach obu kont |
| `subskrybenci_darmowi` brane za liczbę | to próg (1 albo 10) | usunięte ze stanu konta |
| „nowi" z list profilu jako zapisy brutto i podstawa churnu | listy niepełne: 24 z 27 subskrybentów, 36 z 41 obserwujących | `nowi_na_profilu_*` = dolna granica, bez churnu |
| główny licznik wyświetleń mieszał notki z komentarzami mierzonymi z przerwami | definicja zmieniała się w środku okna | główne liczniki = notki i artykuły, komentarze osobno |

**Nie zgadza się po stronie Substacka — pokazujemy, nie poprawiamy:**

- Pole „razem" panelu źródeł (`totals`) różni się od sumy źródeł w 8
  odczytach (25.09 i 28.09): 18 zamiast 21, 20 zamiast 21. Tabela ruchu,
  czyli inny endpoint, zgadza się z sumą źródeł zawsze. Za liczbę zapisów
  bierzemy więc sumę źródeł, a raport zaznacza odczyty z odstającym „razem".
- Karta „new subscribers" przy pozycji jest aktualna tylko, dopóki bot ją
  mierzy. Przykład: notka 320809275 ma kartę 0 (ostatni pomiar 28.08), a panel
  pokazuje 1 zapis (od 02.09). Przypisanie bierzemy z panelu.

**Jeszcze nie da się sprawdzić:**

- **Zapisy brutto wobec przyrostu licznika.** Chodzi o zapisy z panelu (okno
  30 dni) wobec przyrostu licznika w tym samym oknie. Licznik subskrybentów
  mierzymy od 31.08, a okno panelu zaczyna się wcześniej. Porównanie ruszy
  samo od 30.09 i da szacunek odejść. Drugie konto dołączy około tydzień
  później.
- **Numery artykułów w dzienniku.** Dziennik bota nie zapisuje numerów
  artykułów (statystyki mają numer z panelu wydawcy), więc z dziennikiem łączy
  je najwyżej tytuł. Substack i tak nie przypisuje artykułom zapisów w panelu
  źródeł. Poprawka w bocie czeka, bo właściciel zdecydował: „artykuły na razie
  zostaw".
- **Pomiar komentarzy w drugim koncie.** To fork z tym samym limitem, więc
  komentarze tam też nie są mierzone. Poprawka jest kandydatem do
  przeniesienia, decyzja należy do właściciela.

## Badania: jak rośnie konto na Substacku

Pytania uszeregowane według tego, ile mogą dać i czy nasze dane na nie odpowiedzą:

| # | pytanie | dane | metoda |
|---|---|---|---|
| B1 | Który kanał daje subskrybentów: notki, komentarze, restacki, artykuły, rekomendacje? | źródła zapisów (Substack), zapisy przypisane treściom, działania na dobę | opis obu kont co tydzień; na NIE eksperymenty wolumenu |
| B2 | Co dociera do obcych (udział „Unconnected") i skąd (Feed, Notes, Profil, Search)? | powierzchnie i odbiorcy każdej treści | porównanie rodzajów, form i tematów (`eksperymenty.py --pole …`) |
| B3 | Co zamienia odwiedzających profil w obserwujących i subskrybentów? | odwiedziny profilu, nowi (brutto), stan | lejek tygodniowy obu kont; na NIE zmiany profilu i przypiętej notki jako zmiany ręczne |
| B4 | Ile notek dziennie: więcej zasięgu czy kanibalizacja? | wyświetlenia na dobę i na notkę | NIE: przełączanie wolumenu po tygodniach (3 ↔ 5 notek), różnica różnic z NIA |
| B5 | Pora publikacji | czas publikacji, zasięg po 72 h | NIE: losowe przesunięcie godziny (przeplatane) |
| B6 | Komentarze: u kogo i jakie przynoszą wizyty i obserwacje? | dziennik komentarzy (cel, wiek wpisu), odwiedziny profilu | porównanie odzewu obu kont (różny wolumen komentarzy); na NIE eksperyment z doborem celów |
| B7 | Rekomendacje innych publikacji | `nasze_rekomendacje`, źródła zapisów | opis; to największa dźwignia Substacka, a na obu kontach prawie jej nie ma |
| B8 | Czy obserwowanie/subskrybowanie innych coś zwraca? | działania „obserwacja" i „subskrypcja", nowi | zwrot z akcji na obu kontach (drugie konto już to mierzy) |

**Ograniczenie:** dwa konta to za mało, żeby mówić o całym Substacku. Różnią
się personą, wiekiem i siecią. Wnioski ogólne wymagałyby panelu podobnych
publicznych kont (tylko liczby publiczne, bez danych osobowych) — to decyzja
właściciela, nie jest zbudowane.

## Poligon i produkcja: Nothing Is Accidental testuje, NIA bierze sprawdzone

1. **Każdy pomysł najpierw na NIE**, z numerem w rejestrze i regułą decyzji
   zapisaną przed startem (`docs/POMIAR_I_EKSPERYMENTY_2026-09-27.md`). Jeśli
   się da — eksperyment przeplatany; jeśli nie — okno przed/po z RR wobec NIA.
2. **Każda zmiana na obu kontach trafia do dziennika zmian automatycznie**
   (reflog, aktywacje). Działania właściciela na koncie dopisujemy ręcznie
   jednym poleceniem.
3. **Bramka do NIA:** zmiana przechodzi, gdy:
   - na NIE wygrała albo jest bez szkody z zyskiem jakości lub kosztu,
   - strażnicy (fakty, odmowy, koszt) nie pogorszyli się,
   - minął zaplanowany czas,
   - zgodził się właściciel.

   Naprawy błędów przechodzą od razu, bez eksperymentu.
4. **Przeniesienie:** mały PR do NIA, opisany ogólnie (repozytorium publiczne),
   scalany przez właściciela, wdrażany skryptem NIA pod jej zamkiem.
   Obserwatorium samo zapisze godzinę wdrożenia z reflogu.
5. **Kontrola po przeniesieniu:** 14 dni RR (NIA wobec NIE, które w tym czasie
   tej zmiany nie zmienia). Spadek tempa albo zasięgu poza ustalony próg — cofamy.
6. **Stabilność NIA:** najwyżej jedna zmiana treści na 2 tygodnie (inaczej
   skutków nie da się rozdzielić). Naprawy w dowolnej chwili.
7. **Czyste dane:** działania botów wobec siebie liczone osobno, siostra
   odejmowana od subskrybentów, pomiar obu kont tym samym narzędziem i o tej
   samej porze.

Kolejka konkretnych kandydatów do przeniesienia leży w lokalnym rejestrze
`docs/POLIGON_I_PRODUKCJA.md` (poza repozytorium).
