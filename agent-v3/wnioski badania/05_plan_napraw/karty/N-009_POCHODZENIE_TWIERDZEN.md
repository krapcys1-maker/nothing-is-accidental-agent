# N-009 — pochodzenie źródło–fragment–twierdzenie–zdanie

## Metryka

- **Ustalenia:** A-015, A-016, A-035, A-039
- **Status:** `FIXED_OFFLINE; LIVE_PARTIAL_PASS; DEEPSEEK_SYNTHESIS_OPEN`
- **Start:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** dokumenty, fragmenty, twierdzenia, liczby, jednostki zdaniowe,
  cytowania, trwały ledger pochodzenia, prompty syntezy/recenzji, bramki i testy
- **V2:** wyłącznie odczyt; zakaz zapisu

## Stan przed

- pobrany dokument ma URL i tekst, ale nie ma stabilnego ID wersji treści;
- klasyfikator zwraca fragmenty jako stringi, a kod nie sprawdza, czy są
  dosłownym podciągiem dokumentu;
- twierdzenie syntezy niesie skopiowany fragment i URL, bez ID fragmentu;
- liczba nie wskazuje fragmentu ani twierdzenia;
- recenzent może pominąć zdanie bez wykrycia przez kod;
- pojedyncza klasa `INFERENCE` może ukryć faktograficzną przesłankę zdania
  mieszanego;
- bramka liczb serializuje całą kartę, więc cyfra w URL-u lub metadanych może
  uprawomocnić identyczny token w artykule;
- `unused_evidence` jest kopią wszystkich fragmentów i liczb, bez porównania z
  finalnym artykułem.

## Hipoteza

Jeżeli dokument i każdy dosłowny fragment otrzymają deterministyczne ID,
synteza będzie mogła wskazać wyłącznie istniejące ID fragmentów i liczb,
recenzja dostanie przygotowany przez kod pełny zestaw jednostek zdaniowych i
zwróci ID twierdzeń także dla klasy `MIXED`, a finalizacja wyliczy użycie z tego
ledgeru, to zapisany artykuł będzie miał wykonywalny łańcuch:

`citation_id → document_id → fragment_id → claim_id → sentence_id`.

Kontrdowodem jest przyjęcie fragmentu nieobecnego dosłownie w dokumencie,
nieistniejącego ID, pominięcie lub duplikacja jednostki zdaniowej, uznanie
zdania mieszanego za kategorię zwolnioną z dowodu, przyjęcie liczby występującej
tylko w metadanych albo oznaczenie użytego fragmentu jako niewykorzystany.

## Projektowany kontrakt

1. `document_id` zależy od wersji finalnego URL-u i SHA-256 tekstu.
2. `fragment_id` zależy od dokumentu, offsetów i dokładnego tekstu.
3. Fragment modelu musi być dosłownym podciągiem pobranego tekstu.
4. Liczby są wydobywane deterministycznie z zatwierdzonych fragmentów, nie z
   komentarza klasyfikatora.
5. Synteza wskazuje `fragment_ids`; kod nadaje `claim_id` i odtwarza URL-e.
6. Każda liczba wskazuje `number_id`, `claim_index`, fragment i finalne
   twierdzenie.
7. Kod dzieli artykuł na ponumerowane jednostki przed recenzją.
8. Recenzent zwraca każdą jednostkę dokładnie raz. `FACT` i `MIXED` podlegają
   temu samemu wymaganiu dowodowemu.
9. `SUPPORTED` bez istniejącego `claim_id` jest niemożliwe.
10. Dopuszczalny korpus liczb składa się wyłącznie z `citable_numbers.value`.
11. `unused_evidence` zawiera tylko fragmenty bez dojścia do wspieranego zdania
    finalnej wersji.
12. Lista źródeł artykułu powstaje z faktycznie użytych dokumentów.
13. Znormalizowane tabele SQLite zachowują każdy element i relację łańcucha.
14. Brak pełnej recenzji lub zerwany łańcuch prowadzi autonomicznie do rewizji,
    alarmu albo kwarantanny, nigdy do zgody przez fallback.

## Plan testów kontrdowodu

- stabilność ID oraz zmiana `document_id` po zmianie treści;
- odrzucenie fragmentu parafrazowanego i akceptacja dokładnego cytatu;
- odrzucenie zmyślonego `fragment_id`, `number_id` i niespójnego
  `claim_index`;
- kompletność, unikalność i dozwolone ID recenzji;
- `MIXED` bez pokrycia trafia do uwag faktograficznych;
- cyfra obecna tylko w URL-u lub metadanych nie przechodzi bramki;
- liczba związana z innym twierdzeniem daje `LICZBA_BEZ_LANCUCHA`;
- użyty fragment nie trafia do banku, nieużyty trafia;
- źródła i wszystkie relacje są zapisane w tymczasowej SQLite;
- pełna bezpieczna regresja pozostaje zielona.

## Rollback

Nowe tabele i pola są addytywne. Wyłączenie aktywnej integracji nie może usuwać
już zapisanego ledgeru. Powrót do kart bez ID jest dozwolony wyłącznie jako
odczyt historyczny; aktywny potok nie może cicho syntetyzować brakujących więzi
z samego URL-u.

## Odciski przed zmianą

- `db.py`: `ddf68ac249fbea2dd4c0e58026ec55439282a6163ecfa7ead6af9b7646654480`;
- `model_contracts.py`: `c9499c3ed9f6a61ad80b6eb8b9ccd8ef9fbc378d212e9c38b2fbe68d3faaced6`;
- `stages.py`: `f2f7ed99109551e1bd318a36bc23a466efa4e724a1e859c7ba4ec6dc27a879b3`;
- `run.py`: `19bbb488a43e37f79a24a259104f278a6afdf02f1934573a50c26271b07b5304`;
- `gates.py`: `5de85ddfcb89d400766785a214f2a265184441e5accd739098d67107e845ab01`;
- `editorial.py`: `38c183b90653d603224e9669326b08852406443208ca5943a48b7f2373f5b3b8`;
- `prompts/klasyfikacja.md`: `8e9ac59ab9ff4e33cdf8ce5c8db588dfb80d4b40cc7bd6ab74ed237c15b16362`;
- `prompts/synteza.md`: `ac41cfc165ba5010c5713c1d35c2a92bf937a4e97aa539284b349669f82bc15a`;
- `prompts/recenzent.md`: `606b9d47077171b14ae0fd1b0311a5d2cd5a682c0704232156d8827b708b602d`.

## Dowody po zmianie

### Implementacja

- `provenance.py` nadaje deterministyczne identyfikatory dokumentom,
  fragmentom, liczbom, twierdzeniom, jednostkom zdaniowym i cytowaniom;
- fragment jest przyjmowany tylko jako dokładny podciąg dokumentu, a przed
  użyciem cache kod ponownie sprawdza treść, offsety, skróty oraz pełny
  inwentarz liczb;
- `synthesis@2:f645785b0e42` wskazuje `fragment_ids` i `number_id`, natomiast
  kod wiąże te odwołania z kanonicznymi obiektami;
- `review@2:93ac578fc2b2` zwraca dokładnie jeden rekord dla każdej jednostki
  przygotowanej przez kod, obsługuje `MIXED` i wskazuje `claim_ids`;
- `classify@2:d3db16cb598f` nie tworzy już listy liczb — liczby wydobywa kod z
  zaakceptowanych fragmentów;
- `unused_evidence`, cytowania i lista źródeł są wyliczane z finalnego grafu,
  a nie kopiowane z wejścia;
- osiem znormalizowanych tabel SQLite przechowuje dokumenty, fragmenty,
  twierdzenia, liczby, zdania, cytowania i relacje;
- aktywny zapis ponownie waliduje cały graf i odmawia zapisu po jego
  manipulacji;
- historyczne karty bez `provenance_version=1` nie trafiają do nowego banku
  fragmentów.

### Testy

- test celu `test_provenance.py`: **19/19 metod i 8/8 podtestów PASS**;
- test kontraktów: **11/11 metod i 94/94 podtesty PASS**;
- połączony kontrdowód N-008/N-009: **30/30 metod i 102/102 podtesty PASS**;
- regresja sąsiednia ujawniła dwie nieaktualne asercje historyczne; po
  dostosowaniu fixture do nowego kontraktu `test_pobieranie.py` uzyskał
  **17/17**, a `test_martwe_sygnaly.py` **35/35**;
- finalna regresja offline: **41/41 bezpiecznych plików PASS**;
- nie użyto sieci, modeli, przeglądarki, sesji ani produkcyjnego katalogu
  danych; koszt: **0.00 USD**.

### Odciski po zmianie

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
- `tests/test_provenance.py`: `939c7c140cb315a9b0fe12e7345765758b4810be6fde7307dafc8a4d5a349277`.

Pełny projekt eksperymentu, chronologia prób, zagrożenia trafności i
ograniczenia dowodu znajdują się w
[`RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md`](../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-006_POCHODZENIE_TWIERDZEN.md).

### Ograniczenie statusu

Dowód zamyka własność strukturalną offline. E-007 potwierdziło na prawdziwych
modelach dokładne fragmenty i recenzję klas `FACT`, `MIXED` oraz `INFERENCE`;
Sonnet wykonał również syntezę z ID. DeepSeek nie dostarczył kompletnej
odpowiedzi syntezy, a pojedynczy korpus nie mierzy recallu semantycznego.
Dlatego status nie jest `CLOSED`. Pełne wyniki live opisuje
[`RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md`](../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md).
