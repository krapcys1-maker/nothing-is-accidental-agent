# Aneks techniczny audytu Agent V3

**Rola dokumentu:** materiał replikacyjny do `MONOGRAFIA_AUDYTOWA_V3.md`  
**Stan:** wersja robocza 0.2  
**Tryb pozyskania:** analiza statyczna, bez importu kodu integracyjnego, sieci i publikacji

> Liczby i odciski w rozdziale 1 opisują migawkę bazową sprzed konsolidacji dokumentacji do `wnioski badania`. Późniejsze pliki badawcze zwiększają liczebność korpusu dokumentów, lecz nie zmieniają tej historycznej migawki ani odcisków głównych modułów.

---

## 1. Migawka badanego korpusu

| Właściwość | Wartość |
|---|---:|
| wszystkie pliki V3 | 117 |
| pliki `.py` | 59 |
| pliki `.md` | 40 przed dodaniem dokumentacji audytu |
| główne moduły `.py` | 12 |
| linie głównych modułów | 11 239 |
| zwykłe pliki testowe | 36 |
| linie zwykłych testów | 6 308 |
| skrypty testów płatnych | 10 |
| linie testów płatnych | 940 |
| prompty `.md` | 26 |
| linie promptów | 2 843 |
| pliki Python poprawne składniowo według AST | 59/59 |

Stan drzewa nie jest czystym, zatwierdzonym release'em. Katalog V3 był nieśledzony w Git, a V2 miał wcześniej istniejące modyfikacje użytkownika. Audyt nie przypisuje autorstwa zastanym zmianom i nie próbuje ich cofać.

### 1.1. Odciski badanych modułów

SHA-256 pozwala później stwierdzić, czy dane ustalenie nadal odnosi się do identycznego pliku. Odciski wykonano 2026-08-21 po zakończeniu dotychczasowych zmian prototypowych i przed jakąkolwiek przyszłą naprawą funkcjonalną.

| Plik | SHA-256 |
|---|---|
| `run.py` | `c97d3f88254979b9abcf8acf5e9114965381f64a5a96191bcd69de6e30651fb5` |
| `stages.py` | `0a61c6a1671efdfdd9fd3dcc2172e1626f01d2a3eb4b0210f049c482c2c354b0` |
| `browser.py` | `52f9f523450a65278b53e4131adfbb696b2f0ecc23221b4466dd25719cd18935` |
| `config.py` | `724d741f7b1b5287ca9ed67fcb1da15d851c4b2f10331a4855580e9a48ee9657` |
| `db.py` | `0be46421ef6f17980fe4cbb44d40bf017fe643413d8953eb4357fa162ed0609f` |
| `llm.py` | `bd49d2f75333c257121226a36072b86799eba846764985ee8c4b3530a4769969` |
| `gates.py` | `5de85ddfcb89d400766785a214f2a265184441e5accd739098d67107e845ab01` |
| `editorial.py` | `38c183b90653d603224e9669326b08852406443208ca5943a48b7f2373f5b3b8` |
| `kanal.py` | `8f2199f20142222c75b9e2c67f3ede461242b734450d46bcd2db8a7aef7c7eb3` |
| `alarm.py` | `a2aad91d2fe57f3f5e073c8d901127fbb4a88afb5f39b95aaf430d49196f0a34` |
| `style.py` | `08ce7acee0acfd21eddc8a29d9def6dab644c272f9e6bbf57ff227ab360bd814` |
| `kopia_subskrybentow.py` | `c0f3bdfd15bb41e45eedc57ad80619bee280957475f3e25049ed93bf0df7b6e8` |

Odciski nie dowodzą poprawności ani autorstwa. Identyfikują wyłącznie wersję materiału, na której wykonano analizę.

## 2. Punkty wejścia

### 2.1. `run.py`

| Punkt | Linia orientacyjna | Funkcja |
|---|---:|---|
| parser CLI | 738 | argumenty artykułu i dnia |
| blokada publikacji kopii | 750 | marker `TO_JEST_KOPIA_TESTOWA` |
| otwarcie bazy | 752 | inicjalizacja schematów |
| rutyna dnia | 757 | wejście do `dzien()` |
| potok artykułu | 781 | początek `scout` |
| zapis artykułu | 1275 | `stages.save()` |
| publikacja | 1285 | opcjonalna ścieżka przeglądarkowa |
| obsługa awarii artykułu | 1309 | `except Exception` |

### 2.2. `browser.py`

Moduł ma własny interfejs wiersza poleceń do obsługi sesji i kontroli serwera. Jest również importowany przez `run.py`, `alarm.py` i `kanal.py`. Ze względu na możliwość mutacji wszystkie publiczne funkcje tego modułu należy klasyfikować jako:

- tylko odczyt;
- przygotowanie intencji;
- mutacja;
- rekoncyliacja/potwierdzenie;
- administracja sesją.

Taka klasyfikacja nie jest obecnie zadeklarowana w kodzie.

### 2.3. Skrypty operacyjne

| Artefakt | Obecny cel |
|---|---|
| `uruchom-dzien.cmd` | uruchamia V2 z `--dzien --wyslij` |
| `wdroz.sh` | operuje na ścieżkach i usługach V2 |
| `systemd/nia-agent.service` | uruchamia V2 z `--dzien --wyslij` |
| `systemd/nia-artykul.service` | uruchamia V2 z `--wyslij` |
| `systemd/nia-alarm.service` | uruchamia alarm V2 |

To są artefakty produkcyjne znajdujące się wewnątrz katalogu prototypu. W fazie audytu nie wykonywano ich i nie poprawiano.

---

## 3. Mapa modułów

### 3.1. Rozmiar

| Moduł | Linie | Funkcje | Klasy |
|---|---:|---:|---:|
| `run.py` | 1 334 | 15 | 1 |
| `stages.py` | 3 066 | 74 | 0 |
| `browser.py` | 2 402 | 54 | 0 |
| `config.py` | 1 558 | 16 | 0 |
| `db.py` | 217 | 8 | 0 |
| `llm.py` | 545 | 11 | 3 |
| `gates.py` | 514 | 16 | 0 |
| `editorial.py` | 541 | 22 | 0 |
| `kanal.py` | 295 | 10 | 0 |
| `alarm.py` | 536 | 18 | 0 |
| `style.py` | 106 | 5 | 1 |
| `kopia_subskrybentow.py` | 125 | 3 | 1 |

### 3.2. Zależności importów lokalnych

| Moduł | Zależności lokalne |
|---|---|
| `alarm` | `browser`, `config`, `db`, `stages` |
| `browser` | `config`, `stages` |
| `config` | — |
| `db` | `config`, `editorial` |
| `editorial` | — |
| `gates` | `config` |
| `kanal` | `browser`, `config` |
| `llm` | `config`, `db` |
| `run` | `alarm`, `browser`, `config`, `db`, `editorial`, `gates`, `kanal`, `stages` |
| `stages` | `browser`, `config`, `db`, `editorial`, `gates`, `llm`, `style` |
| `style` | `config` |

Zależności wyznaczono statycznie. Importy lokalne wykonywane wewnątrz funkcji nadal są zależnością architektoniczną, nawet jeśli służą unikaniu cyklu na starcie.

### 3.3. Nieużywane parametry wykryte przez AST

| Moduł/funkcja | Parametr | Znaczenie deklarowane |
|---|---|---|
| `stages.discovery` | `recent_domains` | różnorodność źródeł |
| `stages._dobierz_przegladarka` | `juz_mamy` | unikanie duplikatów |
| `gates.verdict` | `findings` | decyzja na podstawie ustaleń |

Wynik nie obejmuje parametrów używanych pośrednio przez mechanizmy dynamiczne; w tych trzech funkcjach nie znaleziono jednak takiego mechanizmu.

---

## 4. Kontrakt przepływu artykułu

### 4.1. Etapy i punkty przerwania

| Etap | `run.py` | Wejście kanoniczne | Wynik oczekiwany | Zachowanie awaryjne |
|---|---:|---|---|---|
| `scout` | 782 | liczba tematów, pamięć | lista tematów | przebieg `FAILED` |
| `feasibility` | 794 | tematy | oceny i głębokość | przebieg `FAILED` |
| `discovery` | 814 | pytanie, ostatnie domeny | kandydackie źródła | przebieg `FAILED` |
| `fetch` | 842 | źródła | pobrany korpus | druga runda; jej awaria jest ignorowana |
| `classify` | 888 | pytanie, korpus | fragmenty i liczby | przebieg `FAILED` |
| `synthesis` | 909 | evidence | karta artykułu | mechaniczny `fallback_card` |
| `warto_pisac` | 944 | karta | decyzja ciekawości | awaria fail-open do pisania |
| `write` | 1017 | karta, głębokość, pamięć | szkic | retry na Claude po każdym `Exception` |
| `review` | 1056 | karta, szkic | recenzja zdań | pusta recenzja + ustalenie techniczne |
| `forma` | 1111 | szkic | obserwacje formy | pusty wynik + ustalenie techniczne |
| `revise` | 1164 | szkic, karta, uwagi | szkic po rewizji | zapis nieudanej rewizji |
| `save` | 1275 | cały stan | pliki i rekordy | przebieg `FAILED` |
| publikacja | 1285 | zapisany, dopuszczony tekst | mutacja zewnętrzna | zależna od `browser` |

### 4.2. Wymagane schematy domenowe

Obecne słowniki powinny docelowo mieć wersjonowane odpowiedniki:

| Obiekt | Minimalne pola semantyczne |
|---|---|
| `Topic` | id/fingerprint, tytuł, pytanie, przekonanie, pochodzenie, czas |
| `Feasibility` | topic_id, feasible, confidence, depth, szacowane źródła, powód |
| `SourceCandidate` | exact result URL, host, tytuł, klasa, query id |
| `FetchedSource` | source_id, final URL, status, typ, hash dokumentu, pobrany tekst |
| `EvidenceExcerpt` | source_id, pozycja/hash fragmentu, tekst, data, klasyfikacja |
| `Claim` | claim_id, tekst, typ, lista evidence_id, niepewność |
| `ArticleCard` | wersja, teza, mechanizm, claims, liczby, kontrargumenty, granice |
| `Draft` | wersja, tytuł, treść, użyte claim_id, deklarowane źródła |
| `SentenceReview` | sentence_id, dokładny zakres, klasa, supported, claim_id, powód |
| `EditorialFinding` | gate, severity, zakres, dowód, możliwość automatycznej naprawy |
| `EditorialDecision` | action, policy_version, inputs_hash, can_publish, reason |
| `Revision` | before_hash, after_hash, trigger, rozwiązane i nowe ustalenia |

Tabela jest specyfikacją brakujących granic, nie zaleceniem wymiany całego istniejącego kodu. Typy można wprowadzać etapami wokół aktualnych słowników.

### 4.3. Statusy

Statusy stwierdzone w aktywnym kodzie i schemacie:

- przebieg: `RUNNING`, `DONE`, `FAILED`;
- stary artykuł: `SAVED`, `BLOCKED`;
- nowy artykuł: `READY`, `REVISED`, `NEEDS_REVIEW`, `PUBLISHED`;
- odłożony temat: `WAITING` oraz projektowane przyszłe wartości;
- rewizja: `RESOLVED`, `NEEDS_REVIEW`, `FAILED`;
- obserwacja: domyślnie `ACTIVE`.

Brakuje jednej maszyny stanów opisującej dozwolone przejścia. Status jest obecnie napisem bez `CHECK` i bez migracji wersji semantycznej.

---

## 5. Kontrakt rutyny dnia

### 5.1. Kategorie budżetu

`stages.budzet_dnia()` produkuje:

- `notki`;
- `lajki`;
- `komentarze`;
- `follow`;
- `subskrypcje`;
- `restacki`.

`browser.ile_dzis_wystawione()` dostarcza:

- notki policzone z kanału lub stanu;
- `komentarze` z dziennika;
- `lajki` z dziennika;
- `restacki` z dziennika.

Nie dostarcza `follow` i `subskrypcje`. Różnica zbiorów kluczy jest bezpośrednim dowodem A-030.

### 5.2. Oś czasu

| Funkcja/obszar | Strefa/doba |
|---|---|
| `config.pora_na_publikacje` | `America/New_York` |
| dziennik akcji | UTC |
| liczniki dnia | UTC |
| liczba przebiegów dnia | UTC |
| promocja artykułu | UTC |
| cichy dzień | według daty użytej w przepływie, obecnie UTC |

System nie przechowuje osobnego `editorial_day_id`. Data jest wyliczana wielokrotnie w różnych funkcjach.

### 5.3. Bezpieczny automat działania

Wymagana maszyna stanu przyszłej akcji:

| Stan | Znaczenie | Czy wolno ponowić? |
|---|---|---|
| `INTENDED` | zapisana intencja przed wyjściem | tak, jeśli nie wysłano |
| `SENT` | żądanie lub kliknięcie wykonane | nie bez rekoncyliacji |
| `CONFIRMED` | platforma potwierdziła skutek | nie |
| `REJECTED` | platforma jawnie odrzuciła | zależnie od trwałości przyczyny |
| `UNKNOWN` | nie wiadomo, czy skutek zaszedł | nie; wymagany odczyt/alarm |

Obecny dziennik nie reprezentuje wszystkich tych stanów.

---

## 6. Słownik danych SQLite

### 6.1. `runs`

| Pole | Typ | Wymagane | Znaczenie |
|---|---|---|---|
| `id` | INTEGER | PK | przebieg |
| `started_at` | TEXT | tak | start UTC ISO |
| `finished_at` | TEXT | nie | koniec UTC ISO |
| `status` | TEXT | tak | `RUNNING/DONE/FAILED` |
| `stage` | TEXT | nie | ostatni etap |
| `cost_usd` | REAL | tak | suma zapisanych kosztów |
| `note` | TEXT | nie | diagnoza końcowa |

### 6.2. `calls`

| Pole | Typ | Wymagane | Znaczenie |
|---|---|---|---|
| `id` | INTEGER | PK | wywołanie |
| `run_id` | INTEGER | nie | logiczne powiązanie z przebiegiem |
| `at` | TEXT | tak | czas UTC ISO |
| `provider` | TEXT | tak | dostawca |
| `model` | TEXT | tak | model |
| `purpose` | TEXT | tak | etap |
| `tokens_in` | INTEGER | tak | wejście |
| `tokens_out` | INTEGER | tak | wyjście |
| `cache_hit` | INTEGER | tak | trafienia cache dostawcy |
| `web_searches` | INTEGER | tak | liczba wyszukiwań |
| `cost_usd` | REAL | tak | koszt wyliczony |
| `price_verified` | INTEGER | tak | wiarygodność stawki |
| `ok` | INTEGER | tak | powodzenie |
| `note` | TEXT | nie | błąd/uwaga |

### 6.3. `articles`

| Pole | Typ | Wymagane | Znaczenie |
|---|---|---|---|
| `id` | INTEGER | PK | artykuł |
| `run_id` | INTEGER | nie | przebieg |
| `created_at` | TEXT | tak | utworzenie |
| `topic` | TEXT | nie | temat |
| `title` | TEXT | nie | tytuł |
| `body` | TEXT | nie | treść |
| `evidence` | TEXT | nie | karta JSON |
| `status` | TEXT | tak | komentarz nadal mówi `SAVED/BLOCKED` |
| `blocked_by` | TEXT | nie | powód blokady |
| `notes` | TEXT | nie | ustalenia JSON |

### 6.4. `sources`

| Pole | Typ | Wymagane | Znaczenie |
|---|---|---|---|
| `id` | INTEGER | PK | źródło |
| `run_id` | INTEGER | nie | przebieg |
| `at` | TEXT | tak | czas |
| `url` | TEXT | tak | adres |
| `domain` | TEXT | tak | domena |
| `title` | TEXT | nie | tytuł |
| `source_class` | TEXT | nie | `PRIMARY/SUPPORTING/ODPAD` |
| `fetched_ok` | INTEGER | tak | wynik pobrania |
| `fail_reason` | TEXT | nie | przyczyna odmowy |

### 6.5. `content_items`

| Pole | Znaczenie |
|---|---|
| `id` | kanoniczne id treści |
| `article_id` | powiązanie logiczne z `articles`, unikalne |
| `run_id` | przebieg |
| `external_id` | identyfikator zewnętrzny |
| `kind` | typ treści |
| `status` | stan redakcyjny/publikacyjny |
| `topic`, `title`, `mechanism`, `form`, `hook` | cechy redakcyjne |
| `canonical_url` | URL publikacji |
| `created_at`, `published_at` | czasy |

Unikalność `(kind, external_id)` nie blokuje wielu rekordów z `external_id = NULL`, co jest prawidłowym zachowaniem SQLite, lecz wymaga późniejszej rekoncyliacji po publikacji.

### 6.6. `metric_snapshots`

Pola: `id`, `content_id`, `captured_at`, `horizon`, `age_hours`, `followers`, `subscribers`, `views`, `opens`, `likes`, `comments`, `restacks`, `signups`, `subscribes`, `raw_json`.

Unikalność dotyczy `(content_id, captured_at)`. Horyzont jest wyprowadzany z `age_hours`, ale obecne przedziały nie odpowiadają nazwom `1H/24H/7D`.

### 6.7. `audience_signals`

Pola: `id`, `content_id`, `target_external_id`, `external_id`, `observed_at`, `kind`, `text`, `author`, `resolved`, `raw_json`.

Unikalność `(external_id, kind)` chroni przed częścią duplikatów. Brak klucza obcego i niepełne mapowanie typów pozostawiają sygnały bez lokalnej treści.

### 6.8. `editorial_observations`

Pola: `id`, `memory_key`, `topic`, `mechanism`, `dimension`, `observation`, `evidence_count`, `confidence`, `first_seen_at`, `last_seen_at`, `status`, `evidence_json`.

`memory_key` jest hashem treści opisowej, nie hashem dowodów. Zmiana redakcyjna zdania obserwacji tworzy nową pamięć nawet przy tej samej hipotezie; identyczne zdanie może z kolei nadpisać całkiem inny zestaw dowodów.

### 6.9. `deferred_topics`

Pola: `id`, `fingerprint`, `run_id`, `created_at`, `updated_at`, `status`, `attempts`, `topic_json`, `reason`, `missing_piece`, `research_json`, `retry_after`.

Fingerprint powstaje z małych liter tytułu i pytania. Nie normalizuje bardziej złożonych parafraz, więc semantycznie ten sam temat może istnieć wielokrotnie.

### 6.10. `article_revisions`

Pola: `id`, `article_id`, `run_id`, `created_at`, `iteration`, `trigger_json`, `before_json`, `after_json`, `status`, `remaining_json`.

Główny przepływ zapisuje rewizję przed artykułem, pozostawiając `article_id = NULL`. Nie ma późniejszego `UPDATE`.

### 6.11. Relacje niewymuszane przez bazę

Pożądane logiczne relacje:

- `calls.run_id -> runs.id`;
- `articles.run_id -> runs.id`;
- `sources.run_id -> runs.id`;
- `content_items.article_id -> articles.id`;
- `content_items.run_id -> runs.id`;
- `metric_snapshots.content_id -> content_items.id`;
- `audience_signals.content_id -> content_items.id`;
- `deferred_topics.run_id -> runs.id`;
- `article_revisions.article_id -> articles.id`;
- `article_revisions.run_id -> runs.id`.

Żadna z tych relacji nie jest zadeklarowana jako `FOREIGN KEY`.

---

## 7. Magazyny plikowe

| Ścieżka względem `data/` | Producent | Konsument | Rola | Ryzyko |
|---|---|---|---|---|
| `dziennik.jsonl` | `browser` | `browser`, `stages`, `alarm` | działania i część limitów | zapis fail-open |
| `gdzie_komentowalismy.json` | `kanal` | `kanal` | historia komentarzy | brak transakcji z akcją |
| `zuzyte_fakty.json` | `stages` | `stages` | deduplikacja materiału | uszkodzenie może zresetować historię |
| `promocja.json` | `stages` | `stages` | kampania artykułu | osobna doba i zapis |
| `bank_notek.json` | `stages` | `stages` | niewykorzystane fragmenty | odrębny schemat mechanizmów |
| `pytania_czytelnikow.json` | `stages` | `stages` | pytania do skauta | brak lifecycle |
| `indeks_kandydatow.json` | `stages` | `stages` | kandydaci do interakcji | stan rozłączny od akcji |
| `alarmy.json` | `alarm` | `alarm` | historia alarmów | brak wspólnego event id |
| `storage-state.json` | `browser` | `browser` | żywa sesja | sekret operacyjny |
| `cache/<stage>/*.json` | `run.cached` | `run.cached` | wyniki etapów | niepełny klucz i nieatomowy zapis |
| `articles/*.md` | `stages.save` | operator/publikacja | artefakt treści | rozjazd z DB przy awarii |
| `articles/*.uwagi.md` | `stages.save` | operator | raport bramek | historyczne statusy |

`.gitignore` wyklucza dane, bazy, sesje i `.env`. Ochrona przed commitem nie jest ochroną przed użyciem przez proces lokalny.

---

## 8. Konfiguracja i źródła prawdy

### 8.1. Sekrety

`config.py` ładuje kolejno:

1. `agent-v3/.env`;
2. `.env` z katalogu głównego repozytorium bez `override`.

Prototyp może zatem korzystać z produkcyjnych kluczy znajdujących się na poziomie wspólnym. Brak pliku `.env` wewnątrz V3 nie oznacza braku dostępu do sekretu.

### 8.2. Dane i sesja

- baza V3: `agent-v3/data/agent-v3.db`;
- artykuły: `agent-v3/data/articles`;
- sesja: `agent-v3/data/storage-state.json`;
- profile stylu: katalog współdzielony na poziomie repozytorium;
- marker zakazu publikacji: `agent-v3/TO_JEST_KOPIA_TESTOWA`.

Marker chroni ścieżkę `run.main(--wyslij)`, ale nie jest typem uprawnienia przekazywanym do każdej funkcji mutującej.

### 8.3. Zmienne wersji

Aktywny `config.py` czyta prefiks `AGENT_V3_*`. Część kodu, komentarzy, wdrożenia i systemd nadal używa `AGENT_V2_*`. Szczegóły: A-026 i A-053.

---

## 9. Katalog promptów

### 9.1. Prompty etapów artykułu

- `skaut.md`;
- `wykonalnosc.md`;
- `dyskoveria.md`;
- `klasyfikacja.md`;
- `synteza.md`;
- `warto_pisac.md`;
- `bibliotekarz.md`;
- `pisarz.md`;
- `recenzent.md`;
- `forma.md`;
- `redaktor.md`;
- `grafika.md`.

### 9.2. Prompty rutyny dnia i interakcji

- `notka.md`;
- `komentarz.md`;
- `odpowiedz.md`;
- `restack.md`;
- `kogo_odpowiedziec.md`;
- `fedreg.md`;
- `ciekawostki.md`;
- `po_ludzku.md`;
- `weryfikacja.md`.

### 9.3. Polityki i materiały

- `cele.md`;
- `OSWIADCZENIE_AI.md`;
- `ROZWOJ_KONTA.md`;
- `SKAD_BRAC.md`;
- `ZASADY_NOTEK_I_KOMENTARZY.md`;
- `historia_startowa.json`;
- `styl/article_style_samples_v1.txt`.

### 9.4. Problem wersjonowania kontraktu

Cache hashuje cały katalog promptów, lecz odpowiedzi nie zawierają jawnej wersji schematu. Zmiana niepowiązanego promptu może unieważnić wszystkie etapy, a zmiana kodowej walidacji bez zmiany promptu może pozostawić kompatybilny klucz mimo niekompatybilnego konsumenta.

---

## 10. Katalog testów

### 10.1. Zwykłe testy

36 plików obejmuje artykuł, bank notek, bibliotekarza, bramki, czas, formę, generatory, głębokość, indeks, komentarze, licznik, hosty, martwe sygnały, obserwacje, pobieranie, promocję, pytania, restacki, rytm, stawki, sufity, wolumeny, wstrzyknięcia, wybór tematu i zapis wywołań.

### 10.2. Testy płatne

10 skryptów obejmuje porównanie V1/V2, pełne ścieżki bibliotekarza i FedReg, integrację, warianty notek, ślepą ocenę, styl oraz bramkę ciekawości.

### 10.3. Typy dowodu testowego

| Typ | Przykład | Siła |
|---|---|---|
| czysta funkcja | klasyfikacja czasu/liczby | wysoka dla funkcji |
| odtworzenie fragmentu kodu | lokalna kopia algorytmu | średnia; może się rozjechać |
| wyszukiwanie tekstu źródła | obecność stałej/kolejności | niska dla zachowania |
| test plikowy z monkeypatch | stan promocji/banku | średnia, jeśli katalog tymczasowy |
| import aktywnego modułu | test integracji lokalnej | zależna od efektów importu |
| test płatny/sieciowy | realny dostawca | wysoka dla integracji, niska odtwarzalność |

### 10.4. Znane naruszenie hermetyczności

`test_martwe_hosty.py` może utworzyć `data/zasiew-produkcji.db`. Pusty plik tej nazwy istnieje w badanym katalogu danych. Nie usuwano go.

---

## 11. Obsługa błędów

### 11.1. Wynik statyczny

| Moduł | Szerokie obsługi wyjątków | Natychmiast milczące/przechodzące |
|---|---:|---:|
| `browser.py` | 30 | 9 |
| `stages.py` | 19 | 6 |
| `run.py` | 14 | — |
| `alarm.py` | 2 | — |
| `llm.py` | 2 | — |

Same liczby nie są automatycznym werdyktem. W automatyzacji UI część wyjątków jest oczekiwana. Krytyczne jest to, czy błąd wpływa na bezpieczeństwo, stan lub decyzję i czy ta informacja zostaje zachowana w postaci umożliwiającej automatyczną klasyfikację.

### 11.2. Zalecana klasyfikacja

- `NO_DATA` — poprawny brak danych;
- `QUALITY_REJECTED` — świadoma odmowa redakcyjna;
- `TRANSIENT` — bezpieczne ponowienie;
- `PERMANENT` — brak ponowienia;
- `MUTATION_UNKNOWN` — skutek zewnętrzny nieznany;
- `STATE_INTEGRITY` — nie można ufać licznikom/pamięci;
- `IDENTITY` — brak dowodu konta/uprawnienia;
- `SECURITY` — niedozwolony URL, injection lub naruszenie granicy;
- `BUDGET` — brak rezerwy kosztowej;
- `SCHEMA` — poprawny JSON, niepoprawny kontrakt.

---

## 12. Mapa ustaleń do artefaktów

| Zakres ustaleń | Główne artefakty |
|---|---|
| A-001–A-004 | `run.py`, `browser.py`, `config.py`, `uruchom-dzien.cmd`, `wdroz.sh`, `systemd/` |
| A-005–A-007 | `browser.py`, `run.py`, `stages.py` |
| A-008–A-011 | `editorial.py`, `run.py`, `stages.py` |
| A-012–A-014 | `db.py`, `editorial.py`, `run.py`, testy statusów |
| A-015–A-018 | `stages.py`, `gates.py`, `llm.py`, prompty klasyfikacji/syntezy |
| A-019–A-021 | `editorial.py`, `run.py`, prompty recenzenta/redaktora/pisarza |
| A-022–A-024 | `llm.py`, `run.py`, `config.py` |
| A-025–A-028 | `tests/`, dokumentacja V2/V3, `config.py`, `browser.py` |
| A-029–A-032 | `stages.py`, `browser.py`, `run.py`, `config.py` |
| A-033–A-040 | discovery/fetch/classify/synthesis, `gates.py`, prompty |
| A-041–A-047 | `db.py`, `editorial.py`, magazyny JSON, AST modułów |
| A-048–A-053 | `config.py`, `llm.py`, `run.py`, usługi i wdrożenie |
| A-054–A-061 | fetch, save/cache, `run.py`, mutacje i potwierdzenia `browser.py` |
| A-062–A-065 | `style.py`, profile stylu, prompty pisarza/redaktora, decyzja jakości |
| A-066–A-068 | `requirements.txt`, `wdroz.sh`, Playwright i środowisko serwera |
| A-069–A-072 | adaptery `/api/v1`, pętla restacków, konwerter HTML i `alarm.przeglad` |
| A-073 | `tutaj jest do zaczerpiecia z neta.txt`, metodologia porównawcza |
| A-074–A-083 | prompty krótkich form, `style.py`, profile stylu, `editorial.py`, `config.py`, testy promptów |
| A-084 | `operational_day.py`, schemat unikalności dnia, test zmiany wersji polityki |
| A-085 | `safe_fetch.py`, historia pinów DNS, `test_safe_fetch.py` |

Pełne uzasadnienie każdego identyfikatora znajduje się w `SPOSTRZEZENIA_AUDYTOWE.md`.

---

## 13. Własności do przyszłego testu przekrojowego

1. V3 nie otwiera żadnego pliku poza własnym katalogiem fixture podczas testu.
2. V3 nie odczytuje `.env` ani sesji w trybie offline.
3. Próba otwarcia gniazda sieciowego kończy test błędem.
4. Każda próba mutacji bez capability kończy się przed kontaktem z adapterem.
5. Plan doby jest identyczny dla wszystkich procesów tej doby.
6. Suma `CONFIRMED` nie przekracza planu w żadnej kategorii.
7. Stan `UNKNOWN` nigdy nie jest automatycznie ponawiany.
8. Każde zdanie faktograficzne ma pełny łańcuch pochodzenia.
9. Każdy URL jest dokładnym wynikiem oraz przechodzi kontrolę sieci prywatnej po redirectach.
10. Każda odpowiedź modelu przechodzi walidację wersjonowanego schematu.
11. Brak wymaganej kontroli zawsze oznacza brak prawa publikacji.
12. Rewizja nie może dodać nowego faktu bez dowodu.
13. Status ma tylko dozwolone przejścia.
14. Każdy rekord zależny ma istniejącego rodzica.
15. Każda rola otrzymuje wersjonowaną tożsamość marki i właściwy profil gatunku.
16. Redaktor zachowuje głos w mierzalnych wymiarach przed/po rewizji.
17. Niezaufany tekst występuje wyłącznie po jawnej granicy danych i nie trafia surowo do pamięci promptowej.
18. Przydzielone ruchy, postawy i otwarcia są zgodne semantycznie.
19. Każda empiryczna reguła promptu ma odtwarzalny manifest dowodu i termin ponownej oceny.
20. Test promptu bada wyrenderowany kontrakt, nie tylko obecność frazy w szablonie.
15. Cache jest unieważniany przez zmianę wejścia, promptu, kodu kontraktu, konfiguracji i wersji schematu.
16. Koszt przed wywołaniem ma wystarczającą rezerwę lub etap nie startuje.
17. Obserwacja redakcyjna może zostać obalona i wygaszona.
18. W raporcie można wskazać, która obserwacja wpłynęła na decyzję.
19. Żaden test lokalny nie zostawia pliku w `agent-v3/data`.
20. Po symulowanym przerwaniu na dowolnej granicy stan jest jednoznacznie odtwarzalny.

---

## 14. Procedura aktualizacji aneksu

Po każdej dalszej fazie audytu należy:

1. zapisać datę i zakres plików;
2. dopisać nowe ustalenia do głównego rejestru;
3. zaktualizować mapę artefaktów;
4. oddzielić zmianę zaobserwowaną od zmiany rekomendowanej;
5. nie oznaczać problemu jako naprawiony bez testu negatywnego;
6. zachować informację, czy dowód jest statyczny, eksperymentalny czy zewnętrzny;
7. nie wykonywać testu sieciowego pod pretekstem „weryfikacji” bez osobnej zgody.

---

## 15. Macierz epistemiczna ustaleń

Legenda podstawy: **D** — bezpośrednia inspekcja artefaktu; **T** — wniosek z przepływu kilku artefaktów; **R** — replikacja defektu opisanego w V2; **H** — przewidywany skutek wymagający eksperymentu. „Obalenie” oznacza minimalny dowód, który pozwoliłby zamknąć lub przeformułować ustalenie; nie jest zgodą na wykonanie testu live.

| ID | Podstawa | Pewność | Minimalny warunek obalenia lub zawężenia |
|---|---|---|---|
| A-001 | D | wysoka | brak ścieżki V2/`--wyslij` we wszystkich artefaktach operacyjnych V3 |
| A-002 | D | wysoka | hermetyczny proces V3 nie odczytuje głównego `.env` ani żywej sesji |
| A-003 | D/T | wysoka | capability prototypu jest wymagane przez każdą funkcję mutującą |
| A-004 | D/T | wysoka | kill switch jest odczytywany bezpośrednio przed każdą mutacją |
| A-005 | D/T | średnia | fixture aktualnego kontraktu jednoznacznie potwierdza konto, rolę i publikację |
| A-006 | D/T | wysoka | licznik zlicza wyłącznie zdarzenia `CONFIRMED` z zewnętrznym dowodem |
| A-007 | D | wysoka | błąd/niepewność kontroli komentarza zawsze blokuje wysyłkę |
| A-008 | D | wysoka | statyczny call graph i test integracyjny pokazują producentów metryk/sygnałów/obserwacji |
| A-009 | D | wysoka | migawki mają porównywalne, jawnie tolerowane okna wieku |
| A-010 | D/H | wysoka | istnieje proces hipoteza–próba–kontrprzykład–wycofanie i testuje go fixture |
| A-011 | D | wysoka | każda czytana kategoria sygnału ma producenta i powiązanie z treścią |
| A-012 | D/R | wysoka | jedna maszyna statusów jest używana przez kod, zapytania i testy |
| A-013 | D | wysoka | każda rewizja po zapisie ma niepusty, poprawny `article_id` |
| A-014 | D | wysoka | odłożenie ma wznowienie, rozwiązanie, wygaśnięcie i historię przejść |
| A-015 | D | wysoka | `unused_evidence` jest różnicą evidence minus materiał rzeczywiście użyty |
| A-016 | D/T | wysoka | claim–fragment–źródło–zdanie–przypis ma wspólne identyfikatory |
| A-017 | D | wysoka | klucz cache zawiera wersję kodu, schematu, konfiguracji i TTL danych |
| A-018 | D | wysoka | każda granica modelu waliduje wersjonowany schemat przed użyciem |
| A-019 | D/H | średnia | wersjonowany korpus referencyjny kalibruje ważności i progi z akceptowalnym błędem |
| A-020 | D/H | wysoka | wersjonowany zbiór regresyjny dowodzi braku nowych krytycznych wad po rewizji |
| A-021 | D | wysoka | prompt ma jedną warunkową, niesprzeczną politykę granic wiedzy |
| A-022 | D/T | wysoka | preflight rezerwuje koszt następnego kroku i rekoncyliuje nieznane koszty |
| A-023 | D | wysoka | pełny pipeline przechodzi bez sieci, sekretów, kosztów i konta |
| A-024 | D | wysoka | każda `BaseException` po `start_run` domyka stan przebiegu |
| A-025 | D | wysoka | testy V3 egzekwują wyłącznie aktualne kontrakty i obejmują nowe moduły |
| A-026 | D | wysoka | aktywne dokumenty/polecenia są jednoznacznie V3, historia odseparowana |
| A-027 | D | wysoka | pytanie ma stan i ślad wykorzystania |
| A-028 | D | wysoka | profil i publikacja mają jeden kanoniczny obiekt konfiguracji |
| A-029 | D | wysoka | trzy procesy tej samej daty odczytują identyczny zapisany plan |
| A-030 | D/T | wysoka | follow i subskrypcje są odejmowane na podstawie potwierdzonych zdarzeń |
| A-031 | T | wysoka | awaria zapisu limitera blokuje kolejną mutację i zachowuje alarm |
| A-032 | T | wysoka | wszystkie polityki używają jednego `editorial_day_id` |
| A-033 | D/T/H | wysoka dla ścieżki | walidacja DNS/IP jest powtarzana po każdym redirect, a testy prywatnych zakresów przechodzą offline |
| A-034 | D/T | wysoka | dokładny wynik, final URL i hash dokumentu są identyczne w śladzie |
| A-035 | T/H | średnia | korpus zdań mieszanych nie pozwala inferencji ukryć faktograficznej przesłanki |
| A-036 | D/T | wysoka | minimum materiału jest blokadą albo jawnie obniża status i długość |
| A-037 | D/R | wysoka | `THIN` ma własny najkrótszy zakres i test |
| A-038 | D/R | wysoka | jedno pole ma jeden wersjonowany schemat w syntezie i banku |
| A-039 | D/T | wysoka | liczby są dozwalane tylko przez powiązany claim/evidence, niezależnie od formatu |
| A-040 | D/T/H | średnia | kontrolowany korpus injection nie wpływa na dozwolony cel żadnego etapu |
| A-041 | D/T | wysoka | przerwanie na każdej granicy daje jednoznaczny, rekoncyliowalny stan |
| A-042 | D | wysoka | schema version, migracje i wymuszane relacje są obecne i testowane |
| A-043 | D | wysoka | test martwych sygnałów rozpoznaje realne użycie wewnątrz `config.py` |
| A-044 | D | wysoka | test używa katalogu tymczasowego i nie zmienia `data/` |
| A-045 | D/H | wysoka | jawne typy granic pozwalają testować własności bez inspekcji monolitów |
| A-046 | D | wysoka | parametry wpływają na wynik albo zostają usunięte wraz z historycznym kontraktem |
| A-047 | D/T | wysoka | szerokie wyjątki klasyfikują błąd i zachowują informację o integralności |
| A-048 | D | wysoka | sufit treści i zapas rozumowania mają odrębne nazwy i raport |
| A-049 | D/T | wysoka | timeout i osiągalny sufit mają jedną jawną hierarchię |
| A-050 | D | wysoka | budżet zależy od faktycznego `--topics` albo CLI ogranicza wartość |
| A-051 | D | wysoka | retry pisarza respektuje wspólną klasyfikację błędów i nie mutuje globalnej konfiguracji |
| A-052 | D/T | wysoka | „confidence” uwzględnia efekt, wariancję, niezależność i sprzeczne dowody |
| A-053 | D | wysoka | jedna przestrzeń `AGENT_V3_*` obejmuje kod, usługi i wdrożenie |
| A-054 | D/T/H | wysoka dla braku limitu | fixture ponad limitem jest przerwany streamingowo przed materializacją |
| A-055 | D/T | wysoka | awaria po każdym kroku zapisu nie tworzy osieroconych/zdublowanych artefaktów |
| A-056 | D | wysoka | capability jest sprawdzane przed utworzeniem blokady i stanem runtime |
| A-057 | D | wysoka | cache zapisuje minimalne dane, ma retencję, limit i jawne włączenie |
| A-058 | D | wysoka | nagłówek klasyfikuje moduł jako mutujący i wymienia granice |
| A-059 | D/T | wysoka | `wyslij=False` nie otwiera zalogowanego adaptera i nie tworzy draftu |
| A-060 | D/T | wysoka | sukces publikacji jest związany z ID bieżącego szkicu i czasem próby |
| A-061 | D/T | wysoka | deadline jest sprawdzany bezpośrednio przed każdą akcją i przerwą w pętli |
| A-062 | D | wysoka | profile mają wersje/hash i uczestniczą w kluczu cache |
| A-063 | D | wysoka | kontrola porównuje wynik z całym faktycznie wyrenderowanym promptem |
| A-064 | D | wysoka | zakres głębokości jest walidowany kodem i raportowany z tego samego obiektu |
| A-065 | D/H | wysoka dla polityki | każda bramka ma ważność i reakcję skalibrowaną na korpusie |
| A-066 | D/R | wysoka | czysta instalacja uruchamia leniwe importy i pełny smoke przed przełączeniem |
| A-067 | D | wysoka | lock/manifest odtwarza identyczne wersje środowiska i przeglądarki |
| A-068 | D/T | wysoka | wdrożenie odmawia na dirty tree albo zachowuje odzyskiwalną kopię |
| A-069 | D/T | wysoka | adapter odróżnia poprawną pustkę od niezgodnego schematu na fixture'ach |
| A-070 | T | wysoka | offline test dwóch restacków zachowuje feed lub otwiera osobny kanał API |
| A-071 | D/T/H | średnia dla exploita | URL jest kanonizowany, a atrybut escapowany z cudzysłowami przed paste |
| A-072 | D/T | wysoka | licznik łączy każdą reakcję z działaniem w tej samej kohorcie publikacji |
| A-073 | D | wysoka | porównanie ma jawny protokół, rubrykę, daty i niezależną replikację ocen |
| A-074 | D | wysoka | profil Notes jest ładowany przez wykonywaną ścieżkę albo jawnie oznaczony jako nieaktywny |
| A-075 | D/T/H | wysoka dla braku wejścia | redaktor dostaje wersjonowany kontrakt głosu, a test przed/po nie wykazuje regresji |
| A-076 | D/T/H | wysoka dla braku kontroli | niezależna rubryka wskazuje cytaty i rozstrzyga osobne wymiary głosu |
| A-077 | D | wysoka | wspólny fragment jest komponowany z jednego źródła albo usunięty z aktywnego kontraktu |
| A-078 | D/H | wysoka dla sprzeczności | prompty opisują jakość redakcyjną bez celu optymalizacji pozoru pochodzenia |
| A-079 | D/T | wysoka | generator nie tworzy sprzecznych par postawa–otwarcie na pełnej macierzy wariantów |
| A-080 | D/T/H | wysoka dla przepływu | surowy sygnał zewnętrzny nie występuje w pamięci przekazywanej pisarzowi ani skautowi |
| A-081 | D/T | wysoka | test wyrenderowanego promptu umieszcza granicę danych przed komentarzem |
| A-082 | D/R | wysoka | każda liczbowa reguła stylu wskazuje dataset, metrykę, skrypt, ograniczenia i datę rewizji |
| A-083 | D/T | wysoka | testy wykrywają konflikt semantyczny, błędną kolejność danych i utratę głosu po rewizji |
| A-084 | D/T | wysoka | zmiana wersji polityki w środku dnia zwraca istniejący plan bez konfliktu unikalności |
| A-085 | D/T | wysoka | dwa rozwiązania jednego hosta po redirectcie pozostają w historii pinów bez nadpisania |

Pewność odnosi się do istnienia opisanego mechanizmu w badanej wersji, nie do częstości szkody na produkcji. Szczególnie A-033, A-040, A-054, A-071 i A-080–A-081 zawierają scenariusze zagrożeń, których nie wolno potwierdzać na żywym środowisku.
