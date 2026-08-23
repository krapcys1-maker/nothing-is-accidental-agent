# N-008 — wersjonowane schematy odpowiedzi LLM

## Metryka

- **Ustalenia:** A-018, A-038
- **Status:** FIXED_OFFLINE; LIVE_CONTRACT_OPEN
- **Start:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** parser JSON, wszystkie 22 granice odpowiedzi modeli, karta
  syntezy, baza telemetrii kontraktów, testy i dokumentacja
- **V2:** wyłącznie odczyt; zakaz zapisu

## Korekta zakresu

Pierwotny rejestr przypisał N-008 także A-052. Rekonstrukcja wykazała, że A-052
opisuje błędną nazwę i interpretację przedziału liczebności obserwacji, a nie
schemat odpowiedzi modelu. Zostaje przeniesione do N-012, gdzie powstaje model
metryk, kohort i niepewności. Zamknięcie go tutaj byłoby zmianą etykiety bez
naprawy modelu statystycznego.

## Stan przed

- `llm.parse_json()` wycina tekst od pierwszej do ostatniej klamry i uruchamia
  `json.loads`, bez kontroli duplikatów kluczy, `NaN`, tekstu obok obiektu,
  wymaganych pól, typów, enumów i nadmiarowych pól;
- `stages.py` ma 22 miejsca parsowania oraz nierówne kontrole lokalne;
- 21 promptów deklaruje JSON, ale kontrakty nie mają identyfikatora wersji;
- cel `factcheck` zwraca dwa różne schematy, więc walidacji nie można wiązać
  wyłącznie z nazwą celu kosztowego;
- synteza modelu i paralela z banku notatek mają różne nazwy pola znaczenia;
- poprawny składniowo, lecz błędny obiekt może przejść z domyślną pustką.

## Hipoteza

Jeżeli każdy z 22 punktów parsowania wskaże jawny `contract_id`, parser dopuści
wyłącznie jeden skończony obiekt JSON bez duplikatów, a rekurencyjny walidator
sprawdzi wymagane pola, typy, enumy, zakresy i nadmiarowe pola, to żaden poprawny
składniowo, lecz strukturalnie błędny wynik modelu nie zmieni decyzji downstream
przez cichy fallback wartości domyślnej.

Kontrdowodem jest brakujące, błędnie typowane albo nadmiarowe pole przyjęte dla
któregokolwiek kontraktu; `NaN`, duplikat klucza lub tekst poza JSON-em przyjęty
przez parser; albo pozostawione bez walidacji wywołanie `llm.parse_json`.

## Projektowany kontrakt

1. Każdy schemat ma stabilną nazwę i dodatnią wersję.
2. Korzeń odpowiedzi jest dokładnie jednym obiektem JSON.
3. Markdown fence jest tolerowany, lecz prose przed/po obiekcie nie.
4. Duplikaty kluczy i niestandardowe stałe JSON są odrzucane.
5. `bool` nie jest akceptowany jako `int`/`number`.
6. Obiekty są zamknięte na nieznane pola, chyba że kontrakt jawnie stanowi
   inaczej.
7. Pola warunkowe mają walidację zależną od wartości dyskryminatora.
8. Wynik walidacji wraz z `contract_id` i błędem trafia do osobnej telemetrii.
9. Kod po walidacji może dodać pola wewnętrzne, ale model nie może ich podać.
10. `parallel_mechanisms` ma jeden kanoniczny kształt niezależnie od źródła.

## Plan testów kontrdowodu

- poprawny minimalny przykład przechodzi dla każdego kontraktu;
- dla każdego kontraktu odrzucane jest brakujące pole korzenia, zły typ i
  nadmiarowe pole;
- parser odrzuca duplikat, `NaN`, tablicę w korzeniu i prose poza JSON-em;
- pole warunkowe scouta, odpowiedzi i recenzji jest egzekwowane;
- `fact_search` i `verification` pozostają dwoma kontraktami mimo wspólnego celu
  kosztowego `factcheck`;
- każde wykonywalne parsowanie w `stages.py` używa centralnego helpera;
- telemetria rejestruje PASS i FAIL z właściwą wersją;
- paralela z banku używa `how_it_matches`, nie osobnego `mechanism`;
- pełna bezpieczna regresja pozostaje zielona.

## Rollback

Walidator można odłączyć od wywołań, ale nie należy usuwać rejestru wersji ani
historii kontroli. Zmiana schematu wymaga nowej wersji; ciche poluzowanie
istniejącej wersji jest zabronione.

## Odciski przed zmianą

- `llm.py`: `711c9517c0db5a3889768e48645b7a21d9b0758482a4828d42c29657083a3e6e`;
- `stages.py`: `6d2233cd2f32603768df70d5682127a022dec3abb542a6deeb88db4e977472af`;
- `run.py`: `aa4254c25a1b1a6fa28087fd12beed83feaa41ef703917eda493906f3563d3f5`;
- `db.py`: `51dfe30016892bd5d90e2ed3c81d5997f4e5682e7fbb321c4e45929c7667b8fd`;
- `editorial.py`: `38c183b90653d603224e9669326b08852406443208ca5943a48b7f2373f5b3b8`;
- `prompts/synteza.md`: `ac41cfc165ba5010c5713c1d35c2a92bf937a4e97aa539284b349669f82bc15a`.

## Dowody po zmianie

### Implementacja

- `model_contracts.py` zawiera 22 zamknięte schematy w wersji 1, reguły
  warunkowe i deterministyczny identyfikator `nazwa@wersja:hash_struktury`;
- `llm.parse_json()` przyjmuje tylko jeden obiekt JSON i odrzuca prozę,
  tablice w korzeniu, duplikaty, `NaN` oraz niedomknięte lub obce fence'y;
- `stages._model_json()` jest jedyną wykonywalną granicą parsera, waliduje przed
  użyciem i zapisuje PASS/FAIL do `model_contract_checks`;
- wszystkie 22 miejsca parsowania wskazują jawny kontrakt; `fact_search` i
  `verification` pozostają rozdzielone mimo wspólnego celu `factcheck`;
- awaria weryfikacji ustawia `safe_to_post=False`, a awaria wyboru zwraca pustą
  listę; oba fallbacki pozostają w pełni autonomiczne i fail-closed;
- synteza, bank dowodów i karta mechaniczna używają kanonicznego pola
  `parallel_mechanisms`.

### Wyniki

- test celu: 11/11 metod i 94/94 podtesty PASS;
- dla każdego kontraktu: poprawny przykład PASS, brak pola, błędny typ i
  nadmiarowe pole odrzucone;
- analiza AST: 22/22 granice pokryte, jeden bezpośredni parser wyłącznie w
  helperze;
- pierwsza szeroka regresja: 37/40 plików, trzy historyczne fixture'y
  niezgodne z pełnymi promptami; poprawiono fixture'y bez poluzowania schematu;
- finalna szeroka regresja: 40/40 bezpiecznych plików offline PASS;
- koszt online: 0.00 USD; brak sieci, modeli, przeglądarki, publikacji i
  wdrożenia;
- pełna chronologia, także nieważne próby uprzęży, znajduje się w E-005 i
  rejestrze testów.

### Odciski po zmianie

- `model_contracts.py`: `c9499c3ed9f6a61ad80b6eb8b9ccd8ef9fbc378d212e9c38b2fbe68d3faaced6`;
- `llm.py`: `92bcf7fdf780dbc1ae63d240d2d983a64923ce2e0317016bb0898ffe35be509c`;
- `stages.py`: `f2f7ed99109551e1bd318a36bc23a466efa4e724a1e859c7ba4ec6dc27a879b3`;
- `run.py`: `19bbb488a43e37f79a24a259104f278a6afdf02f1934573a50c26271b07b5304`;
- `db.py`: `ddf68ac249fbea2dd4c0e58026ec55439282a6163ecfa7ead6af9b7646654480`;
- `tests/test_model_contracts.py`: `87032146d9e7b4873ce96ace70d1026188f2f3dd0f9da7e6431227be3cfc7fc4`.

### Otwarte ograniczenia

Hash obejmuje strukturę, nie kod reguł warunkowych; semantyczna zmiana wymaga
ręcznego podniesienia wersji. Testy offline nie dowodzą częstości poprawnych
odpowiedzi konkretnych modeli. Walidacja formatu nie dowodzi prawdziwości
treści — pełny łańcuch źródło–fragment–twierdzenie–zdanie należy do N-009.

**Raport:**
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-005_WERSJONOWANE_SCHEMATY_LLM.md`.
