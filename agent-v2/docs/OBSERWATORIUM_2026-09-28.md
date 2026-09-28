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
- **Nowi (brutto)** — uchwyt pojawił się pierwszy raz. Churn = nowi − netto.
- **Tempo** — % subskrybentów na tydzień w oknie 28 dni, od ostatniego stanu
  przed oknem (albo od pierwszego pomiaru, gdy ruszyły w środku okna).
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

Wyświetlenia wzrosły z ok. 50–60 dziennie (14–21.09) do ok. 90–130 (22–27.09).
Zapisy przychodzą głównie ze środka Substacka (13 z 21 „Substack", 8 „Direct
to App").

**Najważniejsze na start: zapisy dają artykuły, zasięg dają notki.** W 28
dniach:
- artykuły: 78 wyświetleń, **11 zapisów** przypisanych przez Substack;
- notki: 3860 wyświetleń, **0 zapisów** i 0 obserwacji przypisanych.

Drugie konto pokazuje ten sam wzór. To potwierdza pomiar z 06.09 („notki dały 0
subskrypcji, wszystkie z artykułów") i jest pierwszym pytaniem badawczym (B1):
czy notka działa pośrednio (profil → artykuł → zapis), czy artykuły trzeba
pisać częściej.

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
