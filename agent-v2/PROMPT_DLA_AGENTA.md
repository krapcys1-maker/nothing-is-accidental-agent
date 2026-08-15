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

Ma być **w pełni autonomiczny** — bez zgód wewnętrznych. Ale **nic nie wychodzi
na zewnątrz**: publikacja, komentarz i polubienie nie istnieją w kodzie
i nie powstaną bez osobnej decyzji właściciela.

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
3. **DeepSeek do pracy mechanicznej** — ocena wykonalności tematu i klasyfikacja
   źródeł. Claude tam, gdzie błąd kosztuje cały łańcuch: skaut, dyskoveria,
   synteza, pisanie, recenzja. Klucze do obu są w `agent-v2/.env`.
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

- **prompt skauta** — działa, ale zbiega do `gov.uk` i produkuje dwanaście
  tematów pod rząd o brytyjskich przepisach. **Wymuś różnorodność w kodzie**:
  przed wysłaniem promptu podaj listę domen i krajów z ostatnich pięciu tematów
  z zakazem powtórzenia. Prompt już raz dostał polecenie „różnicuj" i zbiegł.
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
