# Mapa działania Agent V3

**Stan opisany:** prototyp z 2026-08-21, przed systematyczną serią napraw  
**Cel dokumentu:** krótko i precyzyjnie wyjaśnić, co agent robi, gdzie zapisuje stan i gdzie obecny kod rozmija się z pełną autonomią redakcyjną

## 1. System w jednym zdaniu

Agent V3 ma dwa główne przebiegi: tworzenie artykułu oraz codzienne prowadzenie konta. Łączy modele językowe, deterministyczne bramki, SQLite, pliki JSON/JSONL/Markdown i automatyzację przeglądarki.

## 2. Moduły i odpowiedzialności

| Moduł | Rola rzeczywista | Najważniejsza granica |
|---|---|---|
| `run.py` | orkiestracja artykułu i dnia, status przebiegu, limity czasu, decyzja o publikacji | miesza sterowanie potokiem z polityką operacyjną |
| `stages.py` | scout, wybór tematu, discovery, fetch, klasyfikacja, synteza, pisanie, recenzja, rewizja, notki i komentarze | bardzo duży moduł; kontrakty są słownikami |
| `browser.py` | wszystkie operacje zewnętrzne na Substack, odczyt stron/API i dziennik aktywności | `wyslij=False` nie oznacza braku mutacji |
| `llm.py` | dostęp do dostawców modeli, retry, parsowanie JSON, koszt | schematy odpowiedzi nie są formalnie walidowane |
| `gates.py` | deterministyczne kontrole tekstu | większość ustaleń redukuje się do liczby uwag |
| `db.py` | tabele `runs`, `calls`, `articles`, `sources` | brak pełnego wersjonowania i relacji integralności |
| `editorial.py` | prototyp pamięci treści, metryk, sygnałów, obserwacji, odłożeń i rewizji | tabele istnieją, lecz większość nie ma producentów danych |
| `config.py` | modele, ceny, tokeny, czas, limity, ścieżki i polityki | część konfiguracji nie odpowiada zachowaniu wykonawczemu |
| `kanal.py` | pamięć cudzych publikacji i wybór celów interakcji | stan poza główną transakcją |
| `alarm.py` | zdrowie sesji, przegląd zdarzeń i alarmowanie | nie jest globalnym mechanizmem bezpieczeństwa |
| `style.py` | ładowanie korpusu stylu i kontrola integralności | integralność obejmuje tylko część warstw głosu |

## 3. Ścieżka artykułu

Obecny przebieg można odtworzyć następująco:

1. `run.py` rozpoczyna rekord `runs`.
2. `stages.scout` tworzy kandydatów tematów z promptu, pytań i pamięci.
3. `stages.pick_topic` oraz `stages.feasibility` wybierają temat i głębokość.
4. `stages.discovery` generuje i filtruje adresy źródeł.
5. `stages.fetch` pobiera treści przez klienta HTTP lub przeglądarkę.
6. `stages.classify` wyciąga materiał dowodowy.
7. `stages.synthesis` buduje kartę twierdzeń, liczb, granic i inferencji.
8. `stages.warto_pisac` rozstrzyga `PISZ`, `DOLOZ` albo `ODLOZ`.
9. `stages.write` tworzy draft z kartą i pamięcią redakcyjną.
10. `stages.review`, `stages.ocen_forme` i `gates.py` tworzą uwagi.
11. `stages.revise` może wykonać ograniczoną poprawkę i ponowną kontrolę.
12. `stages.save` zapisuje artykuł, uwagi i rekord w bazie.
13. `stages.grafika` może przygotować prompt/grafikę.
14. `browser.py` wypełnia edytor i może publikować.
15. `run.py` próbuje potwierdzić wynik i kończy status przebiegu.

### Główne przerwania kontraktu

- `ODLOZ` ma niepełny cykl powrotu;
- minima researchu częściej ostrzegają niż blokują;
- inferencja może przenieść ukryty fakt bez źródła;
- karta syntezy ma więcej niż jeden schemat;
- rewizja nie zawsze jest prawidłowo związana z artykułem;
- `NEEDS_REVIEW` jest pozostałością niezgodną z pełną autonomią — docelowo zastępuje ją automatyczna kwarantanna;
- zapis do pliku, bazy i świata zewnętrznego nie jest jedną transakcją;
- publikacja jest potwierdzana podobieństwem tytułu zamiast ID próby.

## 4. Ścieżka dnia

`run.py:dzien` wykonuje bloki:

1. odpowiedzi pod własnymi treściami;
2. publikowanie Notes;
3. komentarze pod cudzymi postami;
4. dyskusje pod cudzymi Notes;
5. obserwowanie profili;
6. subskrypcje publikacji;
7. polubienia;
8. restacki.

Każdy blok ma własny wybór kandydatów, część filtrów modelowych i część potwierdzeń platformy. Dzienny budżet jest jednak losowany ponownie w przebiegach, follow/subskrypcje nie są poprawnie odejmowane, a awaria dziennika może wyzerować widoczny stan. Raport dnia potrafi liczyć próbę zamiast potwierdzonego działania.

## 5. Model danych

### Rdzeń `db.py`

- `runs` — przebiegi i status;
- `calls` — wywołania modeli i koszty;
- `articles` — zapisane teksty;
- `sources` — znalezione/pobrane źródła.

### Prototyp `editorial.py`

- `content_items` — treści i cechy;
- `metric_snapshots` — pomiary w czasie;
- `audience_signals` — jakościowe sygnały odbioru;
- `editorial_observations` — ostrożne wnioski/reguły;
- `deferred_topics` — tematy odłożone;
- `article_revisions` — wersje przed/po i powody rewizji.

Struktura pokazuje właściwy kierunek, lecz sam schemat nie tworzy pamięci. Brakuje pełnego kolektora, kohort, stabilnych horyzontów i procesu aktywacji/wycofywania reguł.

## 6. Model stanu plikowego

Poza SQLite agent zapisuje m.in.:

- cache etapów;
- dziennik JSONL;
- pamięć miejsc komentarzy;
- użyte fakty i promocje;
- bank notek i kandydatów;
- pytania czytelników;
- pliki artykułów i uwag;
- stan sesji przeglądarki.

Te magazyny nie mają wspólnej transakcji. Uszkodzenie lub opóźnienie jednego z nich może sprawić, że następny przebieg zobaczy inny świat niż baza.

## 7. Model kosztu

Każde wywołanie modelu jest kierowane przez `llm.py`, które próbuje policzyć tokeny i koszt. W obecnym modelu limit częściej sprawdza koszt już poniesiony niż rezerwuje koszt następnego kroku. Konfiguracja effort, timeoutów i sufitów tokenów ma kilka rozbieżności. Docelowo potrzebny jest ledger z rezerwacją, rozliczeniem i stanem nieznanego kosztu.

## 8. Model bezpieczeństwa

Istnieją marker kopii, kill switch, `wyslij`, rozdzielenie browser/stages oraz część kontroli konta. Nie tworzą one pełnej granicy. Szczególnie:

- skrypty V3 nadal potrafią wskazać V2;
- wspólny `.env` i sesja mogą dać prototypowi żywe uprawnienia;
- kill switch nie obejmuje wszystkich mutacji;
- `wyslij=False` może zmienić zdalny draft;
- część potwierdzeń zależy od nieoficjalnych endpointów;
- URL pobierany z decyzji modelu może prowadzić do sieci prywatnej.

Docelowy model to rejestr możliwości z domyślnym zakazem, egzekwowany bezpośrednio przed każdą operacją zewnętrzną.

## 9. Docelowa maszyna autonomiczna

Docelowy cykl nie ma stanu oczekiwania na akceptację. Ma stany dowodowe:

`CANDIDATE -> RESEARCHED -> DRAFTED -> CHECKED -> REVISED -> READY_AUTONOMOUS -> PUBLISH_ATTEMPTED -> PUBLISHED_CONFIRMED -> MEASURED -> LEARNED`

Odgałęzienia:

- brak materiału -> `DEFERRED`;
- wada dowodowa -> `QUARANTINED_EVIDENCE`;
- wada redakcyjna po limicie rewizji -> `QUARANTINED_EDITORIAL`;
- timeout po mutacji -> `OUTCOME_UNKNOWN`;
- brak możliwości -> `BLOCKED_CAPABILITY`;
- błąd techniczny -> `FAILED_TECHNICAL`.

Pełna specyfikacja znajduje się w `../05_plan_napraw/SPECYFIKACJA_PELNEJ_AUTONOMII.md`.

## 10. Wniosek

Największą wartością V3 jest już istniejący, wieloetapowy rdzeń. Największym brakiem jest niespójność dowodów między etapami. Naprawa powinna zachować sekwencję redakcyjną i kolejno ujednolicić możliwości, stan, pochodzenie, rewizję, pomiar i uczenie.
