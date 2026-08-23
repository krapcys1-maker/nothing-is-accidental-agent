# N-014 — izolacja danych w promptach i pamięci

- **Status:** `OPEN`
- **Ustalenia:** A-040, A-080, A-081
- **Zakres:** zewnętrzne dokumenty, komentarze, sygnały i pamięć promptowa

## Hipoteza

Typowane, kanonizowane rekordy danych z zaporą przed pierwszym niezaufanym
bajtem uniemożliwią przeniesienie polecenia ze źródła do instrukcji lub trwałej
pamięci, bez polegania na blackliście fraz.

## Reuse

Zachować `_prompt()`, modele kontraktów, provenance i surowy magazyn źródeł.
Zmienić kompozycję i pola przekazywane do pamięci.

## Testy wymagane

- wyrenderowany prompt ma zaporę przed każdym niezaufanym polem;
- pamięć nie zawiera surowego tekstu zewnętrznego;
- ataki wielojęzyczne i pośrednie nie zmieniają zadania;
- wynik może odwołać się wyłącznie do dozwolonych ID danych;
- filtr wyjścia pozostaje warstwą dodatkową, nie jedyną ochroną.

## Kryterium końca

Każda rola deklaruje dozwolone źródła i typy pól, a naruszenie kończy etap
fail-closed bez zapisu reguły pamięci.

