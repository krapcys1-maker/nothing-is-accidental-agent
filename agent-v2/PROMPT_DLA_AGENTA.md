# Prompt dla nowego agenta

Skopiuj wszystko poniżej linii do nowej sesji.

---

Budujesz **nowego agenta Substacka od zera** w katalogu `agent-v2/`
w `C:\Users\user\Desktop\agent project`.

**Zanim napiszesz pierwszą linijkę, przeczytaj w tej kolejności:**
`KTORY_JEST_KTORY.md` → `agent-v2/START_TUTAJ.md` → `agent-v2/ARCHITEKTURA.md`
→ `agent-v2/PROGRESS.md` → `agent-v2/prompts/SKAD_BRAC.md`.

W repo jest też `archiwum/` — poprzedni agent. **Tylko do czytania.** Kopiujesz
z niego to, co udowodnione, i nic więcej. Nie uruchamiasz go, nie naprawiasz,
nie ulepszasz.

## Co budujesz

Agent prowadzący Substacka „Nothing Is Accidental" — teksty wyjaśniające ukryte
systemy, bodźce i decyzje za zwyczajnymi rzeczami. Łańcuch: temat → źródła →
pobranie → synteza → artykuł → recenzja → zapis. Jeden proces, po kolei.

## Autonomia — to jest zmiana wobec poprzedniej wersji

**Agent ma być w pełni autonomiczny.** Uruchamiasz jedno polecenie i on sam
wybiera temat, szuka źródeł, pobiera, syntetyzuje, pisze, ocenia i zapisuje.
**Zero pytań do człowieka po drodze.**

Poprzedni agent był budowany odwrotnie — pod model „człowiek zatwierdza każdą
akcję". Zgoda jednorazowa na generowanie tematów, osobna na dyskoverię, osobna
na każde pobranie, osobna na treść, każda z terminem ważności i odciskiem
intencji. To jest połowa złożoności, która go zabiła, i **właściciel tego nie
chce**.

**Jedyna granica: nic nie wychodzi na zewnątrz.** Publikacja, komentarz
i polubienie nie istnieją w kodzie i nie powstaną bez osobnej decyzji
właściciela. Póki ich nie ma, „w pełni autonomiczny" znaczy: sam robi artykuł
do szuflady.

## Gdzie to ma działać

**Docelowo: serwer.** Agent ma chodzić sam, uruchamiany z harmonogramu
(cron/systemd), bez nikogo przy klawiaturze.

**Do testów: ten komputer.** Windows 11, Python w `.venv`. **Musi dać się
uruchomić lokalnie przez cały czas budowy** — inaczej nie zrobisz testów live
po każdym etapie, a to jest wymóg numer jeden.

Praktycznie znaczy to:

- **żadnych ścieżek absolutnych** w kodzie — wszystko względem katalogu projektu
- **żadnych założeń o Windows** — bez `powershell`, bez `C:\`, bez backslashy
  w ścieżkach; używaj `pathlib`
- **jedno polecenie uruchamiające**, to samo lokalnie i na serwerze
- konfiguracja **wyłącznie ze zmiennych środowiskowych** (`.env` lokalnie,
  zmienne systemowe na serwerze) — nigdy z pliku, który istnieje tylko na
  jednym z tych komputerów
- **bez interaktywnych promptów** — agent na serwerze nie ma komu odpowiedzieć
- logi na `stdout`, żeby harmonogram serwera je przechwycił

## Który model za co odpowiada

Klucze do obu dostawców są w `agent-v2/.env`.

| etap | model | dlaczego tak |
|---|---|---|
| skaut tematów | **Claude Opus** | zły temat psuje cały łańcuch i kosztuje ~0,90 USD, zanim się o tym dowiesz |
| ocena wykonalności tematu | **DeepSeek** | tani odsiew **przed** drogim krokiem; błąd kosztuje grosze |
| dyskoveria źródeł | **Claude Opus** | wymaga wyszukiwania po stronie dostawcy, DeepSeek tego nie ma |
| pobranie stron | — | zwykły HTTP, żadnego modelu |
| klasyfikacja źródeł | **DeepSeek** | mechaniczne, dużo wywołań, prosta decyzja |
| synteza dowodów | **Claude Opus** | ocena, co dowody naprawdę potwierdzają |
| pisanie | **Claude Opus** | to jest produkt |
| recenzja | **Claude Opus** | to jest bramka jakości |

Zasada: **DeepSeek tam, gdzie błąd kosztuje jedno tanie wywołanie. Claude tam,
gdzie błąd kosztuje cały łańcuch albo jakość tekstu.**

## Budżet złożoności — twarde liczby

| | limit |
|---|---|
| pliki `.py` w `agent-v2/` | **10** |
| tabele w bazie | **4** |
| warstwy między `run.py` a wywołaniem modelu | **1** |

**Zabronione bez pytania właściciela:** migracje, triggery, zgody, dzierżawy,
kolejka zadań, trwałe intencje, odciski, deklaracje zdolności, kwalifikacje
modeli, rezerwacje przed wywołaniem, rekoncyliacja, bramka spokoju, limity
w `CHECK`-ach.

Poprzedni agent zbudował to wszystko: ~40 000 linii, 2 817 testów, 236
triggerów, 42 migracje. Efekt: dwa artykuły i warstwa, w której szósta z rzędu
poprawka tworzyła szósty z rzędu nowy problem. **Ty masz to zrobić w dziesięciu
plikach.**

Jeśli sięgasz po którąkolwiek z zakazanych rzeczy — zatrzymaj się i powiedz
właścicielowi, **jakiej konkretnej straty ona zapobiega**.

## Jak pracować: etap → live → popraw → następny

**Po napisaniu każdego etapu uruchamiasz go na żywo, zanim napiszesz następny.**

Poprzedni agent zostawił testy live na koniec i miał 2 817 zielonych testów na
atrapach w chwili, gdy produkcja się wywracała. Atrapa reviewera zawsze zwraca
poprawny JSON. Atrapa dostawcy nigdy nie ma timeoutu. Atrapa internetu nigdy
nie zwraca strony blokady botów. Wszystkie trzy zdarzyły się naprawdę.

Testy pisz tylko dwóch rodzajów:
- **kontradowodowe** — teksty, które MUSZĄ zostać odrzucone (masz 19 gotowych)
- **zgodności** — porównują dwa niezależne miejsca: prompt kontra walidator,
  termin kontra sufit tokenów, stała kontra schemat (masz 3 gotowe)

Nie pisz testów na atrapach. Jeśli piszesz atrapę, zapytaj siebie, czy opisuje
świat, czy Twoje wyobrażenie o nim.

## Pieniądze — nie przepalaj

Budowa i testy: **bez limitu** (`AGENT_V2_NO_LIMIT=1`), żeby Cię nie hamować.
Działający agent: **5 USD/dzień, 40 USD/miesiąc**.

Ale „bez limitu" nie znaczy „bez głowy". Zasady, każda z realnej straty:

1. **Nie płać dwa razy za to samo.** Testując etap N, użyj **zapisanego wyniku**
   etapu N−1 z bazy albo z pliku, nie uruchamiaj go ponownie.
2. **Przed każdym płatnym wywołaniem sprawdź warunki, które decydują, czy może
   się udać.** Jedno zaniedbanie tej zasady kosztowało 0,85 USD na
   eksperymencie, który był niemożliwy od pierwszej sekundy.
3. **DeepSeek do pracy mechanicznej** — tabela podziału wyżej.
4. **Najtańszy krok, który różnicuje hipotezy, robisz pierwszy.** Generowanie
   tematów kosztuje 0,10 USD, dyskoveria 0,70. Jeśli podejrzewasz problem
   z tematami, nie diagnozuj go pełnym przebiegiem za 1,40.
5. **Loguj każde wywołanie**: dostawca, model, tokeny, koszt, cel.

Dla orientacji: cały łańcuch artykułu kosztował **~1,41 USD**.

## Co bierzesz ze starego — tylko udowodnione

**Udowodnione na produkcji, bierz bez wahania:**

| co | dowód |
|---|---|
| **styl pisania** — `instrukcja dla pisania artykulow/` + korpus `data/style-references/articles/article_style_samples_v1.txt` + mechanika z `archiwum/app/content/style_examples.py` | dwa artykuły, które właściciel uznał za dobre |
| prompt pisarza (warstwa rzemiosła) | jw. |
| reviewer v3 + rozliczanie zdań | przepuścił dobry artykuł 9/9, blokował zmyślone twierdzenia |
| dziewięć ewaluacji | jw. |
| podłogi porównujące z **korpusem**, nie z alfabetem | naprawione po 20 fałszywych alarmach |
| wykrywanie blokad hostów po frazach odmowy | złapało 3 realne odmowy przy pierwszym przebiegu |
| polityka dopuszczania źródeł | dała karty `PROCEED` |
| 19 testów kontradowodowych | znalazły realną lukę przy pierwszym uruchomieniu |
| zmierzone liczby (16 ms/token, ~118 tokenów/segment, koszty etapów) | z 19 rozliczonych przebiegów |

**Bierz, ale napraw przed użyciem:**

- **prompt skauta** — działa, ale jest **przedokręcony i to jest mój błąd**.

  Kazałem skautowi nazywać instytucję i dokument w samym pytaniu. Skutek:
  wyszukiwanie ograniczyło się do tego, co skaut potrafił wymienić z pamięci,
  i zbiegło do `gov.uk` — dwanaście tematów pod rząd o brytyjskich przepisach.

  **Dyskoveria przeszukuje cały internet i tak ma zostać.** Nie ma i nie ma
  być listy dozwolonych serwisów.

  Prawdziwy wymóg jest znacznie słabszy i tylko taki wpisz: **w gotowym
  korpusie przynajmniej dwa źródła mają być dokumentem pierwotnym** — czymś,
  co samo jest zapisem, a nie omówieniem cudzego zapisu. Rejestr, sprawozdanie,
  norma, orzeczenie, dane, oświadczenie firmy o sobie, praca naukowa. Może to
  być cokolwiek i skądkolwiek.

  Powód jest jeden i praktyczny: reviewer blokuje zdanie twierdzące fakt bez
  pokrycia, więc korpus z samych blogów daje artykuł, który nie może powiedzieć
  nic konkretnego. To jest wymóg **na wynik dyskoverii**, nie na sposób
  formułowania pytania.

  Dodatkowo trzymaj w kodzie prostą regułę różnorodności: **żaden nowy temat
  nie może celować w tę samą domenę, co któryś z pięciu poprzednich.** Tyle
  wystarczy; nie potrzeba list krajów ani rodzin instytucji.
- **kontrakt rozmiaru karty** — pomysł dobry, liczby wyprowadź od nowa
  i trzymaj **w jednym miejscu**, razem z promptem, który ich pilnuje.

**Nie bierz w ogóle:** wszystkiego z listy zakazanej wyżej.

## Git — żeby się nie posypało

- pracujesz **tylko na `main`**, bez gałęzi; to jest projekt jednoosobowy
- **commituj po każdym skończonym etapie**, nie raz na koniec dnia
- wiadomość commita mówi **co i dlaczego**, nie „wip" ani „fix"
- **nigdy `push --force`**, nigdy `reset --hard` na czymś wypchniętym
- **nie dotykasz `archiwum/`** — ani jednego pliku
- przed commitem sprawdź `git status`, żeby nie wciągnąć bazy ani `.env`
- `.env` i `data/` są w `.gitignore` — **zweryfikuj** przez
  `git check-ignore -v agent-v2/.env` zanim cokolwiek wypchniesz
- historia starych gałęzi jest zabezpieczona tagami `archive/*`; nie ruszaj ich

## Księga prac

**Po każdym skończonym etapie aktualizujesz `agent-v2/PROGRESS.md`**: co działa,
co nie, ile kosztowało, co dalej. To jedyne miejsce, z którego następna sesja
dowie się, gdzie jesteś.

## Czego właściciel oczekuje

Powiedział to wprost:

> „wolę żeby to było prostsze ale działało niż tak jak jest teraz"
> „nie chcę już przepalać dziesiątek dolarów na nic"
> „mają być live testy robione, bo ostatnio na koniec zostawiliśmy i powstało gówno"

Prostota ponad kompletność. Działanie ponad elegancję. Dowód ponad obietnicę.
**Jeśli jakaś warstwa nie zapobiegła realnej stracie — nie buduj jej.**

Zacznij od przeczytania czterech dokumentów, potem powiedz właścicielowi, co
zamierzasz zbudować jako pierwsze i ile to będzie kosztować.
