# E-006 — wykonywalne pochodzenie twierdzeń i cytowań

## Abstrakt

Eksperyment badał, czy Agent V3 potrafi dowieść drogi od finalnego zdania do
konkretnej wersji pobranego dokumentu. Stan bazowy przechowywał fragmenty jako
stringi, twierdzenia jako tekst z URL-em, a liczby uznawał za dozwolone, jeżeli
ten sam token występował gdziekolwiek w serializowanej karcie. Recenzja nie
sprawdzała kompletności pokrycia zdań i zwalniała całe zdanie oznaczone jako
inferencja, nawet gdy zawierało faktograficzną przesłankę. `unused_evidence`
było kopią całego korpusu.

Dodano moduł `provenance.py`, deterministyczne ID dokumentów, fragmentów, liczb,
twierdzeń, jednostek zdaniowych i cytowań, kontrolę cytatów verbatim, trzy
kontrakty modelowe v2, klasę `MIXED`, bijekcyjne pokrycie recenzji oraz osiem
znormalizowanych tabel relacji. Użycie i lista źródeł są wyliczane z finalnego
ledgeru, nie deklarowane przez pisarza. Historyczne karty bez wersji pochodzenia
nie trafiają do banku.

Test celu uzyskał 19/19 metod i 8/8 podtestów; razem z testem kontraktów 30/30
metod oraz 102/102 podtesty. Finalna regresja uzyskała 41/41 plików offline.
Status: `FIXED_OFFLINE; SEMANTIC_LIVE_OPEN`. Nie wykonano sieci, modeli,
przeglądarki, publikacji ani wdrożenia. Koszt online: 0.00 USD.

## 1. Pytania badawcze

**RQ1.** Czy dokładna wersja dokumentu i każdy zaakceptowany fragment mają
tożsamość wyliczalną ponownie z treści?

**RQ2.** Czy model może wprowadzić fragment, liczbę, twierdzenie lub jednostkę
zdaniową, której nie ma w wejściowym grafie?

**RQ3.** Czy recenzja obejmuje każdą jednostkę finalnego tekstu dokładnie raz i
czy zdanie mieszane zachowuje obowiązek dowodowy dla faktograficznej części?

**RQ4.** Czy liczba w finalnym tekście wskazuje nie tylko wartość w karcie, ale
konkretny fragment i twierdzenie wspierające konkretną jednostkę?

**RQ5.** Czy bank i lista cytowań odzwierciedlają faktyczne użycie finalnej
wersji, a graf pozostaje trwały w SQLite?

## 2. Ustalenia bazowe

- **A-015:** `unused_evidence` zawierało wszystkie fragmenty i liczby;
- **A-016:** tabela `sources` kończyła ślad na pobraniu dokumentu;
- **A-035:** pojedyncza klasa `INFERENCE` mogła ukryć fakt w zdaniu mieszanym;
- **A-039:** bramka liczb traktowała cyfry z całego JSON-u karty, w tym URL-e i
  metadane, jako korpus źródłowy;
- kod nie sprawdzał, czy fragment klasyfikatora jest dosłownym podciągiem
  pobranego tekstu;
- recenzent miał zwrócić każde zdanie, ale kod nie porównywał wyniku z pełnym
  zestawem wejściowym;
- synteza kopiowała URL i excerpt, więc zgodny kształt nie dowodził, że para
  rzeczywiście pochodzi z tego samego dokumentu.

## 3. Model pochodzenia

Aktywny graf ma wersję 1 i następującą drogę:

`citation_id → document_id → fragment_id → claim_id → sentence_id`

Relacje przechowywane są również w kierunku użytecznym do zapytań: zdanie
wskazuje twierdzenia, twierdzenie wskazuje fragmenty, fragment wskazuje dokument,
a cytowanie wskazuje użyty dokument.

### 3.1. Tożsamości

- `document_id = H(final_url, SHA256(extracted_text))`;
- `fragment_id = H(document_id, start, end, SHA256(fragment_text))`;
- `number_id = H(fragment_id, ordinal, local_offset, exact_value)`;
- `claim_id = H(claim_text, sorted(fragment_ids))`;
- `sentence_id = H(ordinal, exact_sentence_unit)`;
- `citation_id = H(SHA256(final_body), document_id)`.

Prefix i wersja są częścią każdego ID. Hash identyfikatora ma 24 znaki
szesnastkowe; pełne SHA-256 treści dokumentu i fragmentu pozostaje zapisane
osobno.

### 3.2. Tabele

| Tabela | Węzeł lub relacja |
|---|---|
| `provenance_documents` | dokument, URL i hash tekstu |
| `provenance_fragments` | fragment, dokument, offsety i hash |
| `article_claims` | twierdzenie artykułu i stan użycia |
| `claim_fragments` | twierdzenie → fragment |
| `article_numbers` | liczba → twierdzenie → fragment |
| `article_sentences` | jednostka, kolejność, klasa i support status |
| `sentence_claims` | zdanie → twierdzenie |
| `article_citations` | cytowanie → użyty dokument |

Osobna tabela `provenance_checks` zapisuje PASS/FAIL wiązania kontekstowego.
Sukces schematu JSON i sukces relacji pozostają dwoma odrębnymi faktami.

## 4. Hipotezy i falsyfikacja

**H1 — treść adresowalna.** Zmiana tekstu pod tym samym URL-em zmienia
`document_id`; identyczne wejście daje identyczny wynik. Kontrdowodem jest
kolizja w kontrolowanych przykładach albo niestabilność ponownego wyliczenia.

**H2 — fragment verbatim.** Każdy fragment musi zgadzać się z tekstem pod
zapisanymi offsetami, hashem i ID. Kontrdowodem jest przyjęcie parafrazy,
zmienionego cache albo niezgodnych offsetów.

**H3 — zamknięte referencje.** Synteza wskazuje wyłącznie istniejące
`fragment_id` i `number_id`; liczba wskazuje claim zawierający jej fragment.
Kontrdowodem jest przyjęcie obcego ID albo liczby związanej z innym claimem.

**H4 — kompletna recenzja.** Zwrócone `sentence_id` są bijekcją zbioru
przygotowanego przez kod. Kontrdowodem jest przyjęcie braku, duplikatu lub
obcego ID.

**H5 — fakt w zdaniu mieszanym.** `MIXED` używa `SUPPORTED`/`UNSUPPORTED` tak
samo jak `FACT`; `INFERENCE` i `PROSE` muszą mieć `NOT_APPLICABLE` i pusty
zestaw claims. Kontrdowodem jest przyjęcie `MIXED/NOT_APPLICABLE` albo
`SUPPORTED` bez claim ID.

**H6 — liczba ma pełną drogę.** Korpus liczb składa się tylko z
`citable_numbers.value`, a użyta wartość musi wskazywać claim przypisany do tej
samej wspieranej jednostki. Kontrdowodem jest przejście cyfry obecnej wyłącznie
w URL-u albo wartość związana z innym claimem.

**H7 — użycie jest pochodne.** Fragment jest użyty tylko wtedy, gdy wspiera
claim przypisany do wspieranej jednostki finalnego tekstu. Kontrdowodem jest
obecność użytego fragmentu w banku lub cytowanie dokumentu bez użytego claimu.

## 5. Implementacja

### 5.1. Dokument i klasyfikacja

Po bezpiecznym fetchu kod nadaje ID finalnemu URL-owi i wydobytemu tekstowi;
kolumny `sources.document_id` i `content_sha256` zachowują związek z etapem
pobrania. Klasyfikator nadal wybiera cytaty, ale `fragments_from_excerpts()`
wymaga dokładnego podciągu. Jedna parafraza unieważnia wynik klasyfikacji tego
dokumentu. Liczby nie są już polem modelu: kod wydobywa je wyłącznie z przyjętych
fragmentów.

Przy każdym późniejszym odczycie evidence ponownie sprawdzane są hash dokumentu,
ID dokumentu, offsety, tekst i hash fragmentu oraz kompletny inwentarz liczb.
Lokalnie zmieniony cache nie odzyskuje ważności przez zachowanie starego ID.

### 5.2. Synteza v2

`synthesis@2:f645785b0e42` zwraca dla claimu `fragment_ids`, a dla liczby
`number_id` i `claim_index`. Kod sprawdza zakres, istnienie i to, czy fragment
liczby należy do wskazanego claimu. Dopiero potem nadaje `claim_id` oraz odtwarza
fragmenty, dokumenty i URL-e. Model nie zwraca własnego `claim_id`.

`classify@2:d3db16cb598f` nie ma pola `numbers`; dzięki temu prompt i kontrakt
nie utrzymują martwego, modelowego inwentarza.

### 5.3. Recenzja v2 i `MIXED`

Kod dzieli finalne body przed wywołaniem modelu. Jednostki mają offsety,
ordinal i `sentence_id`; prompt otrzymuje JSON z tym kompletnym zbiorem.
`review@2:93ac578fc2b2` zwraca każdą jednostkę dokładnie raz, klasę, status
support, `claim_ids` i uzasadnienie.

Klasa `MIXED` oznacza jednostkę zawierającą faktograficzną przesłankę oraz
interpretację. Nie może użyć `NOT_APPLICABLE`. Lista `unsupported_facts` nie
jest już drugim, redundantnym polem modelu — kod wylicza ją z jednego ledgeru.

### 5.4. Liczby, finalizacja i bank

`gates.numbers_outside_corpus()` nie serializuje karty. Dopuszcza tylko dokładne
wartości z `citable_numbers`. Dodatkowa bramka `LICZBA_BEZ_LANCUCHA` wymaga, aby
liczba była związana z claimem wspierającym tę samą jednostkę zdaniową.

Po finalnej rewizji kod wylicza `used_claim_ids`, `used_number_ids`,
`used_fragment_ids`, `citations`, `sentence_ledger` i `unused_evidence`.
Lista Sources korzysta z `citations`, a więc tylko z użytych dokumentów. Bank
czyta jedynie nieużyte fragmenty kart o aktywnej wersji pochodzenia. Historyczne
etykiety bez dowodu są pomijane fail-closed.

### 5.5. Zapis

Przed pierwszym insertem graf jest ponownie walidowany: unikalność ID, hashe
fragmentów, referencje dokumentów, claims, liczb, zdań i dokładny zbiór cytowań.
Dopiero wtedy relacje trafiają do ośmiu tabel. Zmiana cytowania po finalizacji
zostaje odrzucona przed zapisem.

## 6. Metoda eksperymentu

Testy używały dwóch dosłownych fragmentów kontrolowanego dokumentu, atrap
odpowiedzi modeli, mutacji cache, tymczasowych baz SQLite i statycznej kontroli
promptów. Nie wykonywały DNS, HTTP ani API modeli.

Korpus kontrdowodu obejmował stabilność i czułość ID, cytat/parafrazę, liczby
wydobywane z fragmentu, obce ID, zły claim index, niekompletny inwentarz,
zmieniony cache, brak/duplikat zdania, `MIXED`, obcy claim, cyfrę tylko w URL,
liczbę z innego claimu, użyte i nieużyte fragmenty, historyczny bank, PASS/FAIL
telemetrii, osiem tabel oraz rewalidację grafu przed zapisem.

Regresja uruchamiała 41 zwykłych plików w osobnych procesach z korzenia repo,
projektowym `.venv` i `PYTHONIOENCODING=utf-8`. Wyłączono wyłącznie
platformowy `test_czas.py` oraz katalog `tests/platne`.

## 7. Chronologia prób

### Próba 1 — pierwsze kontrdowody

Pierwszy test N-009 uzyskał 14/14 metod i 8/8 podtestów. Obejmował ID,
dosłowność, wiązanie karty, kompletność recenzji, `MIXED`, liczby, użycie i
osiem tabel.

### Próba 2 — oczekiwany dryf kontraktów N-008

Kompilacja siedmiu modułów przeszła. Test kontraktów uzyskał 10 PASS i cztery
porażki/podporażki: fixture’y nadal miały pola v1 dla review i classify,
oczekiwały `synthesis@1`, a statyczna asercja zakładała numer linii parsera.
Zmieniono fixture’y na jawne v2 i asercję na własność „dokładnie jeden parser”.
Powtórzenie: 11/11 metod i 94/94 podtesty.

### Próba 3 — regresja sąsiednia

Pierwszy zestaw siedmiu plików uzyskał 5/7 PASS. `test_pobieranie` szukał starej
formy przypisania `entry["url"]`, a `test_martwe_sygnaly` wymagał dawnej
redundancji `sentences` plus `unsupported_facts`. Zmieniono wyłącznie statyczne
asercje na nowe własności: zapis wersji dokumentu i jeden bijekcyjny ledger.
Powtórzenie: 17/17 oraz 35/35 PASS.

### Próba 4 — bank i granice etapów

Dodano dodatnie przejście synteza→review z dwoma wpisami PASS w
`provenance_checks` oraz kontrdowód wykluczenia historycznego banku. Test celu
wzrósł kolejno do 15/15 i 16/16. Pierwsza szeroka regresja po integracji:
41/41 plików PASS.

### Próba 5 — kontrola po zielonej regresji

Przegląd cache ujawnił brak ponownego przeliczenia treści po nadaniu ID.
Dodano pełną rewalidację dokumentu, fragmentów i liczb; test celu 17/17.
Następnie zapis otrzymał walidację całego grafu; test 18/18. Ostatni test objął
skrót, dziesiętną liczbę i offsety sentence splittera; wynik 19/19.

Kompilacja siedmiu modułów przeszła. Łączny zestaw provenance i kontraktów:
30/30 metod, 102/102 podtesty. Finalna szeroka regresja: 41/41 plików PASS.

## 8. Wyniki

| Własność | Kontrdowód | Wynik offline |
|---|---|---|
| dokument | stabilność i zmiana treści | stabilny/czuły ID |
| fragment | cytat vs parafraza | cytat przyjęty, parafraza odrzucona |
| cache | zmieniony tekst i brak liczby | oba odrzucone |
| synteza | obcy fragment/number, zły claim | wszystkie odrzucone |
| recenzja | brak, duplikat, obcy sentence/claim | wszystkie odrzucone |
| zdanie mieszane | `MIXED/UNSUPPORTED` | błąd faktograficzny |
| liczba z metadanych | `2026` tylko w URL-u | poza korpusem |
| liczba z innego claimu | poprawna wartość, zła relacja | `LICZBA_BEZ_LANCUCHA` |
| unused | jeden użyty, jeden nieużyty fragment | właściwy podział |
| bank historyczny | karta bez wersji + karta v1 | tylko v1 przyjęta |
| cytowania | finalny użyty document ID | dokładny zbiór |
| trwałość | osiem tabel i relacje | wszystkie zapisane |
| tamper przed SQLite | zmieniony document citation | odrzucony, 0 insertów |
| test celu | unittest | 19/19; 8/8 podtestów |
| kontrakty + cel | pytest | 30/30; 102/102 podtesty |
| regresja | bezpieczny korpus | 41/41 plików PASS |

## 9. Zagrożenia trafności i ograniczenia

- `document_id` identyfikuje tekst po ekstrakcji, nie surowe bajty HTML/PDF.
  Zmiana niewidoczna dla ekstraktora nie zmieni ID.
- Identyczny cytat występujący wielokrotnie wiąże się z pierwszym offsetem.
- Sentence splitter jest deterministyczną heurystyką angielskiej interpunkcji.
  Obsługuje badane skróty, liczby dziesiętne i granice akapitów, ale nie jest
  pełnym parserem językowym. Nietypowy skrót może zwiększyć lub zmniejszyć
  jednostkę; nie pozwala jednak modelowi pominąć jednostki już utworzonej.
- `MIXED` zamyka strukturalną lukę, lecz poprawność semantycznej klasyfikacji i
  zgodność claimu ze zdaniem nadal zależą od recenzenta modelowego. Test offline
  dowodzi kontraktu fail-closed, nie trafności modelu na dowolnym tekście.
- Dokładne porównanie liczb celowo nie normalizuje `68%` do `68 percent` ani
  `2,989,787` do `2989787`. Zmiana formatu daje odmowę, nie fałszywą zgodę.
- Lista Sources jest artykułowa, nie ma w treści inline markerów każdego zdania.
  Dokładna relacja sentence→claim→fragment→document istnieje w SQLite i karcie.
- Osiem tabel nie ma deklaratywnych foreign keys; spójność egzekwuje walidator
  przed zapisem. Bezpośredni zapis SQL poza aktywną ścieżką może ją ominąć.
- Historyczne karty są pomijane przez bank, co obniża dostępny stary korpus, ale
  nie pozwala recyklingować materiału o fałszywej etykiecie.
- Zapis pliku i bazy nie jest jeszcze jedną transakcją; to osobny zakres N-010.
- Nie wykonano testu live modeli. Zgodność formatu i jakość klasyfikacji
  semantycznej na żywym korpusie pozostają otwarte.

## 10. Odciski artefaktów po zmianie

- `provenance.py`: `473d6d97d425a665bbd9dd1aa5298d729c58dcca07b6b794ff2a151d65fd36f5`;
- `db.py`: `ca4cfdd4f9927fd1c69ccf08a38a709afa9fba963dae3b22e37a2628a0bac5a5`;
- `model_contracts.py`: `cc22e0a2a068c0c762bc5ed05fb0fdc157448d3c0790a4289f3d608ffeb4424d`;
- `stages.py`: `5af228ba4b28b8408de071e3b07c63048a42727995601b0bf1704db2b517b81b`;
- `run.py`: `b37924f86efd2ab2906a32d723b4c2abc02f032e3ef2fea83eaa863e5d353144`;
- `gates.py`: `451e061ccb0d34e9c7d708199c7de7131785bdd140ed6e99d4dec84f0dc5546a`;
- `editorial.py`: `b84cddc963eab4456be5bbd6fc030307220eaadae307330b5660657b118253dd`;
- `prompts/klasyfikacja.md`: `6fc8ba17dddb9274a877887f28d906231af06e78d72b37505ef17a82eb0a33b6`;
- `prompts/synteza.md`: `87f5a446a5796a41d56843854b4b5636603919a7aa7852602652f98f3510cf8d`;
- `prompts/pisarz.md`: `c79e4cba061b005d5c08b3a0ec7daf46e2754b5bf0f2bab360184ae26e65551e`;
- `prompts/recenzent.md`: `f1cf7a5c63616dafeaf38be28c46714b58ef8876ed8872e44dbfade685909229`;
- `tests/test_provenance.py`: `939c7c140cb315a9b0fe12e7345765758b4810be6fde7307dafc8a4d5a349277`;
- `tests/test_model_contracts.py`: `2b2abfab757aef85499f35bb4d9ba4ee779fd207bfb53057ee3edc5841cb74ce`;
- `tests/test_pobieranie.py`: `037bdc09a777b46a74e27462a4c054c957826bfc570ed746bb99c69f8f6ef7ed`;
- `tests/test_martwe_sygnaly.py`: `893b6803a8702854367e01246e3b253823a40138d61cd786e7fc88610fa8c59d`.

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

A-015, A-016 i A-039 mają bezpośrednie kontrdowody offline. A-035 ma zamkniętą
lukę strukturalną: kompletność jest wymuszana przez ID, a `MIXED` nie jest
zwolnione z dowodu. Trafność semantyczna modelowego rozpoznania faktu pozostaje
osobnym pytaniem empirycznym, dlatego wynik nie otrzymuje statusu gotowości
produkcyjnej. Dla nowego materiału V3 może odtworzyć graf od zdania do wersji
dokumentu i odróżnić użycie od samej obecności w researchu. Uzasadniony status
to `FIXED_OFFLINE; SEMANTIC_LIVE_OPEN`.
