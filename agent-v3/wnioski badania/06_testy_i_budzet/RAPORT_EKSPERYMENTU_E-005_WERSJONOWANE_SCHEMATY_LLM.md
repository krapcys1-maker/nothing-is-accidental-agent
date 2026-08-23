# E-005 — wersjonowane i zamknięte kontrakty odpowiedzi LLM

## Abstrakt

Eksperyment badał, czy poprawny składniowo, lecz niepełny albo semantycznie
sprzeczny JSON modelu może sterować etapem Agent V3. Stan bazowy używał parsera,
który wycinał fragment między pierwszą i ostatnią klamrą, oraz lokalnych,
nierównych kontroli. Nie wykrywał duplikatów kluczy, `NaN`, tekstu obok obiektu,
nadmiarowych pól ani wielu naruszeń zależnych od wartości innych pól.

Zrekonstruowano wszystkie 22 wykonywalne granice model–kod i utworzono 22
zamknięte kontrakty w wersji 1. Każdy ma identyfikator
`nazwa@wersja:hash_struktury`, rekurencyjną walidację oraz trwały wynik PASS/FAIL
w SQLite. Parser dopuszcza wyłącznie jeden obiekt JSON, ewentualnie w dokładnym
fence Markdown. Błędna weryfikacja nie daje zgody na publikację, a błędny wybór
komentarzy kończy się autonomicznym milczeniem. Karta syntezy i mechanizmy z
banku dowodów używają jednego kształtu.

Test celu uzyskał 11/11 metod i 94/94 podtesty, a finalna regresja 40/40 plików
offline. Status wyniku to `FIXED_OFFLINE; LIVE_CONTRACT_OPEN`. Nie wykonano
sieci, modeli, przeglądarki, publikacji ani wdrożenia. Koszt online: 0.00 USD.

## 1. Pytania badawcze

**RQ1.** Czy każda odpowiedź modelu przechodząca do logiki sterującej ma jawny,
wersjonowany kontrakt?

**RQ2.** Czy parser odrzuca dane, które tylko zawierają JSON, ale nie są
dokładnie jednym obiektem JSON?

**RQ3.** Czy wymagane pola, typy, enumy, zakresy, pola nadmiarowe oraz zależności
warunkowe są sprawdzane przed odczytem przez downstream?

**RQ4.** Czy awaria kontraktu pozostawia trwały ślad odrębny od sukcesu
transportu modelu i prowadzi do bezpiecznego stanu autonomicznego?

**RQ5.** Czy różne źródła tej samej karty redakcyjnej tworzą identyczny kształt
danych?

## 2. Ustalenia bazowe

- **A-018:** odpowiedzi modeli nie miały centralnej walidacji schematu;
- **A-038:** `parallel_mechanisms` z syntezy i banku notatek miały dwa niezgodne
  kształty;
- w `stages.py` istniały 22 punkty parsowania;
- 21 plików promptów żądało JSON-u, lecz kontrakt nie miał identyfikatora;
- jeden cel kosztowy `factcheck` obsługiwał dwa różne kształty: wyszukanie faktów
  oraz końcową weryfikację;
- błąd końcowej weryfikacji był zamieniany na `safe_to_post=True`, a błąd wyboru
  komentarzy na arbitralny wybór najstarszego elementu.

Rekonstrukcja skorygowała też zakres backlogu: **A-052** dotyczy semantyki
metryki i niepewności, nie odpowiedzi LLM. Zostało przeniesione z N-008 do
N-012; zamykanie go tym eksperymentem byłoby pozorne.

## 3. Hipotezy i kryteria falsyfikacji

**H1 — zupełność granicy.** Wszystkie aktywne punkty tekst modelu → obiekt
sterujący przechodzą przez jeden helper i wskazują zarejestrowany kontrakt.
Kontrdowodem jest drugi bezpośredni `llm.parse_json` albo literal kontraktu spoza
rejestru.

**H2 — zamknięta struktura.** Dla każdego kontraktu brak pola korzenia, błędny
typ lub nadmiarowe pole zostaje odrzucone. Kontrdowodem jest przyjęcie choć
jednej takiej mutacji poprawnego przykładu.

**H3 — ścisły JSON.** Proza przed/po obiekcie, tablica w korzeniu, duplikat
klucza, `NaN` i niedomknięty fence są błędami. Kontrdowodem jest odzyskanie z
nich obiektu przez parser.

**H4 — bezpieczny skutek błędu.** Niedostępna lub wadliwa weryfikacja nie może
dać zgody na publikację; wadliwa selekcja nie może wybrać obiektu zastępczego.
Kontrdowodem jest `safe_to_post=True` albo niepusta lista wyboru.

**H5 — kanoniczna karta.** Mechanizm równoległy ma pola `domain`,
`how_it_matches` i opcjonalne `origin`; starsze `mechanism`/`z_banku` są
odrzucane. Karta awaryjna zawiera wszystkie kanoniczne kolekcje.

## 4. Inwentarz kontraktów

| Kontrakt | ID wersji 1 | Funkcja |
|---|---|---|
| `review` | `review@1:10c87d43dbae` | recenzja faktów |
| `forma` | `forma@1:018945e26d14` | audyt formy artykułu |
| `write` | `write@1:7c5b10e775a7` | szkic artykułu |
| `revise` | `revise@1:a278fd0d4a08` | rewizja szkicu |
| `wybor` | `wybor@1:11de77dae08f` | wybór komentarzy |
| `reply` | `reply@1:6eaae2d2c891` | odpowiedź pod własnym tekstem |
| `grafika` | `grafika@1:9b865112d0c1` | brief obrazu |
| `cele` | `cele@1:0590c7751e1b` | wybór celów dyskusji |
| `curiosity` | `curiosity@1:8732691f4152` | fakty do notek |
| `note` | `note@1:e5e36d001544` | pojedyncza notka |
| `restack` | `restack@1:1915ada729d7` | decyzja i zdanie restacku |
| `fact_search` | `fact_search@1:846a0ddd685d` | fakty pomocnicze |
| `verification` | `verification@1:092d3c88e017` | końcowa weryfikacja tekstu |
| `comment` | `comment@1:28777af169d4` | komentarz do cudzego tekstu |
| `synthesis` | `synthesis@1:7889424abff8` | karta dowodowa |
| `classify` | `classify@1:a9767c65a87e` | klasyfikacja źródła |
| `discovery` | `discovery@1:39ed7b006562` | lista dokumentów |
| `feasibility` | `feasibility@1:76f46c2ee31c` | wykonalność tematów |
| `scout` | `scout@1:b37096bb7727` | kandydaci tematów |
| `bibliotekarz` | `bibliotekarz@1:f601a9689d7c` | grupowanie mechanizmów |
| `warto_pisac` | `warto_pisac@1:3e1a5818d78e` | bramka wartości tematu |
| `fedreg` | `fedreg@1:1f7066804e2c` | kandydaci z dokumentu FedReg |

Identyfikator jest liczony deterministycznie z nazwy, jawnej wersji i
kanonicznego hasha struktury. Dwa kontrakty `fact_search` i `verification`
zachowują osobne ID mimo wspólnej etykiety kosztowej `factcheck`.

## 5. Projekt implementacji

### 5.1. Parser składniowy

`llm.parse_json()` wykonuje dokładnie jedno `json.loads`. Opcjonalny fence musi
obejmować całą odpowiedź i mieć etykietę pustą albo `json`. Hook obiektów
odrzuca powtórzony klucz, a `parse_constant` odrzuca `NaN` i nieskończoności.
Korzeń inny niż słownik kończy się błędem. Parser nie wycina ani nie naprawia
fragmentów odpowiedzi.

### 5.2. Walidator kontraktów

`model_contracts.py` definiuje mały walidator rekurencyjny dla obiektów, tablic,
stringów, booli, liczb całkowitych, skończonych liczb, enumów i wartości null.
Obiekty są domyślnie zamknięte. `bool` nie przechodzi jako liczba, mimo takiej
relacji typów w Pythonie. Reguły niemożliwe do wyrażenia samą strukturą obejmują
między innymi indeksy tablic, pola zależne od rodzaju scouta, uzasadnienie ciszy
i treść źródła przy obalonym twierdzeniu.

### 5.3. Jedna granica wykonawcza

`stages._model_json()` najpierw parsuje, potem waliduje i dopiero zwraca obiekt.
Analiza AST wymusza dokładnie jeden bezpośredni parser — wewnątrz helpera — oraz
22 wywołania nazwanych kontraktów pokrywające cały rejestr. Kod nie wnioskuje
schematu z nazwy modelu ani dostawcy.

### 5.4. Trwała telemetria

Tabela `model_contract_checks` zapisuje `run_id`, czas, cel kosztowy, pełny
`contract_id`, wynik i skrócony błąd. Sukces transportu API oraz sukces
kontraktu są zatem osobnymi faktami. Także błąd parsera otrzymuje identyfikator
oczekiwanego kontraktu.

### 5.5. Semantyka fail-closed

Niepoprawna końcowa weryfikacja zwraca `verification_available=False` i
`safe_to_post=False`. Niepoprawna selekcja komentarzy zwraca pustą listę, więc
agent autonomicznie milczy zamiast wykonywać losowy fallback. Pozostałe etapy
albo zatrzymują daną ścieżkę, albo używają jawnie oznaczonego mechanicznego
fallbacku danych, który nie udaje wyniku modelu.

### 5.6. Jeden kształt karty

Wpisy dokładane z banku używają `how_it_matches` i
`origin="evidence_bank"`. Wynik modelu może użyć `origin="synthesis"` albo
pominąć to pole. Stary kształt jest odrzucany. `fallback_card()` zawiera pustą
listę `parallel_mechanisms`, aby każda wewnętrzna karta miała ten sam zestaw pól
funkcjonalnych; prywatne `_fallback` jest metadanym kodu, nie polem modelu.

## 6. Metoda eksperymentu

Testy używały stałych obiektów, kontrolowanych mutacji poprawnych przykładów,
analizy AST, tymczasowej bazy SQLite oraz atrap `llm.call`. Nie wykonywały
transportu dostawcy. Dla każdego z 22 kontraktów sprawdzono przykład dodatni,
brak pola, błędny typ i nadmiarowe pole. Dodatkowe kontrdowody objęły parser,
zakres liczbowy, typ `bool`, zależności warunkowe, telemetrię, kanoniczną kartę
oraz dwa krytyczne fallbacki.

Bezpieczna regresja uruchamia każdy plik w osobnym procesie, projektowym
`.venv/Scripts/python.exe`, z korzenia repozytorium i z
`PYTHONIOENCODING=utf-8`. Wyłączono wyłącznie platformowy `test_czas.py` oraz
cały katalog `tests/platne`.

## 7. Chronologia prób

### Próba 1 — rejestr i kontrdowody

Pierwsza wersja testu uzyskała 10/10 metod PASS. Obejmowała 22 poprawne
przykłady, trzy mutacje każdego schematu, parser, reguły warunkowe, analizę AST,
SQLite oraz kanoniczny mechanizm równoległy.

### Próba 2 — pierwsza szeroka regresja

Pierwsza regresja po włączeniu walidatora dała 37/40 plików PASS. Trzy testy
historyczne (`bibliotekarz`, `restack`, `safe_fetch`) podawały celowo skrócone
odpowiedzi modelu, które nie spełniały rzeczywistych promptów. Naprawiono
wyłącznie fixture'y przez uzupełnienie pól niezależnych od badanych własności;
nie poluzowano kontraktów. Testy celowane uzyskały odpowiednio 10/10, 8/8,
26/26 i 19/19, a szeroka regresja 40/40.

### Próba 3 — kontrola po zielonym wyniku

Przegląd stanów awaryjnych ujawnił, że sama walidacja nie wystarczy, jeżeli
wyjątek jest później zamieniany na zgodę lub arbitralną decyzję. Zmieniono
weryfikację i selekcję na fail-closed, dodano hash struktury do ID oraz test
telemetrii. Test celu uzyskał 11/11 metod. Następnie uzupełniono kanoniczne pole
`parallel_mechanisms` w mechanicznej karcie awaryjnej i ponownie uzyskano 11/11
oraz 94/94 podtesty.

### Próba 4 — błędy uprzęży końcowej

Pierwsza komenda końcowa wskazała nieistniejące środowisko
`agent-v3/.venv`; test nie wystartował. Kolejny przebieg z korzenia, ale bez
wymuszenia UTF-8, dał 27/40 z powodu konsoli CP1252. Próba uruchomienia plików
bezpośrednio z katalogu V3 dała 4/40, ponieważ Python ustawił ścieżkę importu na
`tests`, podczas gdy historyczne testy oczekują korzenia repozytorium. Oba
wyniki są nieważne jako ocena kodu, lecz zachowane jako wynik metody.

Miarodajna komenda z korzenia repozytorium, projektowym interpreterem i UTF-8
dała 40/40 plików PASS.

## 8. Wyniki

| Własność | Kontrdowód | Wynik offline |
|---|---|---|
| pokrycie granic | AST: parser i wszystkie nazwy kontraktów | 22/22 |
| schematy dodatnie | minimalny poprawny obiekt | 22/22 |
| brak pola korzenia | mutacja każdego kontraktu | 22/22 odrzucone |
| błędny typ korzenia | mutacja każdego kontraktu | 22/22 odrzucone |
| nadmiarowe pole | mutacja każdego kontraktu | 22/22 odrzucone |
| ścisły parser | prose, array, duplicate, NaN, fence | wszystkie odrzucone |
| liczby | bool i wartość poza zakresem | odrzucone |
| zależności | review, comment, scout, verification | odrzucone |
| telemetria | PASS i FAIL w tymczasowej SQLite | trwałe, różne wyniki |
| karta | kształt kanoniczny i stary | nowy przyjęty, stary odrzucony |
| fail-closed | awaria weryfikacji i selekcji | brak zgody, brak wyboru |
| test celu | unittest | 11/11; 94/94 podtesty |
| regresja | bezpieczny korpus | 40/40 plików PASS |

## 9. Zagrożenia trafności i ograniczenia

- Testy dowodzą zachowania walidatora wobec kontrolowanych obiektów, nie
  częstości zgodnych odpowiedzi prawdziwych modeli.
- Hash obejmuje strukturę schematu, ale nie kod dodatkowych reguł warunkowych.
  Każda semantyczna zmiana reguły `custom` wymaga ręcznego podniesienia wersji;
  pominięcie tego obowiązku byłoby niewykrywalne przez sam hash.
- Kontrakt jest wersjonowany po stronie wykonawczej i telemetrii. Prompt nie
  wysyła `contract_id` jako pola odpowiedzi; dryf promptu będzie bezpiecznie
  odrzucony, ale może obniżyć dostępność etapu.
- Walidacja typów i spójności lokalnej nie dowodzi prawdziwości treści. Pełny
  łańcuch źródło–fragment–twierdzenie–zdanie pozostaje zakresem N-009.
- Nie wszystkie ograniczenia długości i liczebności z promptów są częścią
  schematów. Część nadal realizują osobne bramki i przycięcia downstream.
- Trwały FAIL pokazuje naruszenie, lecz nie ma jeszcze zagregowanej polityki
  alarmu, retry według wersji ani automatycznej migracji starszych wyników.
- Nie wykonano testu live z Anthropic ani DeepSeek, więc status nie dowodzi
  zgodności formatowania konkretnych modeli z wersją 1.

## 10. Odciski artefaktów po zmianie

- `model_contracts.py`: `c9499c3ed9f6a61ad80b6eb8b9ccd8ef9fbc378d212e9c38b2fbe68d3faaced6`;
- `llm.py`: `92bcf7fdf780dbc1ae63d240d2d983a64923ce2e0317016bb0898ffe35be509c`;
- `stages.py`: `f2f7ed99109551e1bd318a36bc23a466efa4e724a1e859c7ba4ec6dc27a879b3`;
- `run.py`: `19bbb488a43e37f79a24a259104f278a6afdf02f1934573a50c26271b07b5304`;
- `db.py`: `ddf68ac249fbea2dd4c0e58026ec55439282a6163ecfa7ead6af9b7646654480`;
- `tests/test_model_contracts.py`: `87032146d9e7b4873ce96ace70d1026188f2f3dd0f9da7e6431227be3cfc7fc4`;
- `tests/test_bibliotekarz_bramka.py`: `e79454dc91abcad34861f95e113ef7756de680aed2e9dca23f6bfc9a10c464f2`;
- `tests/test_restack.py`: `a03464393b5112dd6059e0fa845432481dae081a569be4617c096489e2d8b81e`;
- `tests/test_safe_fetch.py`: `a67403e973210f084a51133b1019e7b9b561afe295717f037077a67fab968f09`.

## 11. Koszt i efekty zewnętrzne

- Anthropic: 0.00 USD;
- DeepSeek: 0.00 USD;
- GPT/OpenAI: 0.00 USD;
- DNS/HTTP/TLS: brak;
- przeglądarka: brak;
- konta i mutacje zewnętrzne: brak;
- publikacja, wdrożenie i produkcja: brak;
- `agent-v2`: wyłącznie odczyt stanu Git, bez zapisu.

## 12. Wniosek

A-018 i A-038 mają obecnie wykonywalne kontrdowody offline. Poprawny składniowo
obiekt nie steruje już etapem bez zgodności z konkretną wersją, różne źródła
karty nie tworzą dwóch dialektów, a najgroźniejsze błędy kontraktu nie są
zamieniane na zgodę ani arbitralną akcję. Następną warstwą wiarygodności jest
N-009: pochodzenie każdej treści faktograficznej. Test live może później zbadać
dostępność formatów u dostawców, ale nie jest potrzebny do uznania dowodu
fail-closed. Uzasadniony status to `FIXED_OFFLINE; LIVE_CONTRACT_OPEN`, nie
gotowość produkcyjna.
