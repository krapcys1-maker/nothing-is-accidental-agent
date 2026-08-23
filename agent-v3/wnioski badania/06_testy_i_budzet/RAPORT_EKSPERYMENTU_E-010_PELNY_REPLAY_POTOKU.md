# E-010 — pełny hermetyczny replay potoku V3 i preflight live

## Abstrakt

Eksperyment sprawdził otwartą część N-004: czy normalna orkiestracja
`run.main()` potrafi przejść od scouta do lokalnego zapisu artykułu na dwóch
hermetycznych adapterach — modelu i publicznego fetchu — bez skróconej,
równoległej implementacji potoku. Dodatni replay wykonał wszystkie etapy,
12 walidacji kontraktów i pełny graf provenance, zapisując jeden artykuł
`READY`. Ujemny replay utrwalił awarię `write` jako `runs.FAILED`, bez artykułu
i bez przejścia do platformy. Test celu ma wynik 7/7, testy sąsiednie 44/44
metod, a pełna regresja przed utwardzeniem launchera 47/47 plików. Hashe
`agent-v3/data` nie zmieniły się.

Przygotowano również kontrolowany launcher prawdziwych modeli z limitem 1,50
USD. Rzeczywisty preflight 2026-08-21 odmówił przed utworzeniem katalogu i
przed dispatch, ponieważ `agent-v3/.env` nie istnieje, a proces nie ma kluczy
DeepSeek ani Anthropic. Nie wykonano API ani Substacka; koszt E-010 wynosi 0 USD.

## 1. Pytanie i hipotezy

Pytanie główne: czy jedna normalna ścieżka wykonawcza V3 przechodzi kolejno
przez research, redakcję, bramki, provenance i zapis, zachowując hermetyczność?

- **H1:** replay wywołuje prawdziwe `run.main()` oraz prawdziwe funkcje
  `stages`, a nie kopię orkiestracji przygotowaną wyłącznie dla testu.
- **H2:** jedynymi zastąpionymi efektami są odpowiedzi LLM i publiczny fetch;
  SQLite, cache, kontrakty, bramki, provenance i zapis pliku są prawdziwe.
- **H3:** dodatnia ścieżka wykonuje scout, feasibility, discovery, fetch,
  4×classify, synthesis, warto_pisac, write, review i forma, po czym zapisuje
  dokładnie jeden lokalny artykuł.
- **H4:** wymuszona awaria `write` kończy run jako `FAILED/write`, bez artykułu,
  przeglądarki i mutacji zdalnej.
- **H5:** launcher live odmawia przed I/O, gdy brakuje kluczy, aktywny jest
  dry-run, routing odbiega od normalnego V3 albo limit przekracza 1,50 USD.

## 2. Środowisko i granice

- Windows, projektowa `.venv`, wymuszone UTF-8;
- zwykły `run.main()` z argumentem `--topics 1`, bez `--wyslij`;
- tymczasowe `data`, SQLite, cache i katalog artykułów;
- cztery zamrożone dokumenty, dokładne URL-e i literalne fragmenty;
- fixture capability dopuszcza tylko atrapę `PUBLIC_WEB_READ`;
- fixture modeli zwraca wersjonowane odpowiedzi dla normalnych nazw etapów;
- jawne sprawdzenie, że moduł `browser` nie został zaimportowany;
- brak Substacka, sesji, publicznej sieci i prawdziwych modeli w replayu offline.

## 3. Stan przed i kontrdowody

T-097 uruchomił test przed istnieniem adaptera. Import zakończył się
`ModuleNotFoundError: No module named 'pipeline_replay'`, co dowiodło dokładnie
otwartego zakresu karty N-004.

Pierwszy dodatni przebieg po implementacji przeszedł potok, lecz końcowa asercja
policzyła dwa pliki `.md`: artykuł i jego `.uwagi.md`. T-098 zakończył się 1/2,
ponieważ metryka artefaktów nie rozróżniała produktu od notatek wewnętrznych.
Selektor został zawężony; nie zmieniono kodu produkcyjnej orkiestracji.

## 4. Implementacja replayu

1. `pipeline_replay.run_fixture()` przekierowuje ścieżki danych do katalogu
   tymczasowego i uruchamia normalne `run.main()`.
2. Adapter LLM ma zamrożone odpowiedzi dla scout/feasibility/discovery,
   klasyfikuje cztery dokładne fragmenty, buduje kartę z prawdziwych ID nadanych
   przez `provenance`, a review wiąże każdą jednostkę zdaniową z istniejącym
   `claim_id`.
3. Adapter fetch akceptuje wyłącznie cztery URL-e fixture. Prawdziwe
   `stages.fetch()` nadal zapisuje requested/final URL, redirecty, IP, hash i
   `document_id`.
4. Prawdziwe kontrakty, bramki, `finalize_card()`, `persist_article_lineage()`,
   cache, `stages.save()` oraz `editorial.register_article()` pozostają aktywne.
5. Ujemny parametr `fail_purpose="write"` rzuca wyjątek dokładnie na granicy
   modelu; zwykła obsługa `run.main()` zapisuje błąd i kończy bez artefaktu.

## 5. Launcher prawdziwego rdzenia

`tests/platne/test_full_pipeline_live.py` zamraża etapy wejściowe
scout/feasibility/discovery/fetch, a prawdziwym modelom przekazuje redakcyjny
rdzeń na identycznym korpusie:

| Etap | Model | Bazowe dispatchy |
|---|---|---:|
| classify | `deepseek-v4-flash` | 4 |
| synthesis | `deepseek-v4-pro` | 1 |
| write | `claude-fable-5` | 1 |
| review | `deepseek-v4-pro` | 1 |
| forma | `deepseek-v4-pro` | 1 |

Jeżeli bramki zażądają rewizji, dopuszczone są jeszcze `revise` na Fable oraz
druga para review/forma na Pro: maksymalnie 11 dispatchy. Limit całego runu jest
obniżany do 1,50 USD. Runtime dopuszcza wyłącznie `MODEL_CALL` i fixture’owy
`PUBLIC_WEB_READ`; nie ma argumentu `--wyslij`, importu `browser`, dostępu do
sesji ani capability Substacka. Routing jest porównywany przed próbą i po niej;
żaden `MODEL_FOR.update` ani zapis do `MODEL_FOR[...]` nie istnieje w launcherze.

## 6. Wyniki

| Test | Wynik | Dowód |
|---|---|---|
| T-097 | ERROR zgodnie ze stanem przed | brak modułu pełnego replayu |
| T-098 | 1/2, błąd uprzęży | artykuł i `.uwagi.md` policzone jako dwa produkty |
| T-099 | 7/7 PASS | dodatni i ujemny full replay oraz pięć własności preflightu |
| T-100 | 14/14 + 19/19 + 11/11 PASS | bezpieczeństwo, provenance i kontrakty |
| T-101 | 47/47 plików PASS | pełna regresja; `data/` bez zmiany hashy |
| T-102 | BLOCKED przed API | `.env` nie istnieje; oba wymagane klucze niewidoczne |
| T-103 | odmowa PASS | exit 1, dokładne brakujące klucze, workspace nie powstał, 0 dispatchy |
| T-104 | 47/47 plików PASS | finalna regresja po utwardzeniu launchera w 42,801 s; `data/` bez zmian |

Odciski nowych artefaktów po implementacji:

| Plik | SHA-256 |
|---|---|
| `pipeline_replay.py` | `F66FC689888414878E289CA6AE735AB1D34A60D1862B83F4CA60F1A446F4E795` |
| `tests/test_full_pipeline_replay.py` | `280B581657F4994AF9E558DD7AEE0880078D3BC1F00EFF624D4E89C35863D8E9` |
| `tests/platne/test_full_pipeline_live.py` | `C593A096F56A36819A949305D20D99B50969A827A36C0940B6913C32E2B193EB` |

Hashe opisują dokładny kod zweryfikowany finalną regresją T-104.

## 7. Trafność i ograniczenia

Replay offline dowodzi normalnej orkiestracji, stanów awarii i spójności grafu,
ale odpowiedzi fixture nie dowodzą jakości ani zgodności prawdziwych modeli.
Launcher live świadomie zamraża scout, feasibility, discovery i fetch, więc
planowana próba sprawdzi redakcyjny rdzeń modeli, nie aktualną jakość wyszukiwania
publicznej sieci. E-007 pozostaje częściowym dowodem trzech granic modeli.

T-102/T-103 nie są live PASS. Dowodzą jedynie, że brak poświadczeń zatrzymuje
proces przed kosztem i I/O. Aby rozstrzygnąć live, użytkownik musi umieścić
klucze `AGENT_V3_DEEPSEEK_API_KEY` oraz `AGENT_V3_ANTHROPIC_API_KEY` w lokalnym
`agent-v3/.env`. Kluczy nie należy wklejać do rozmowy ani dokumentacji.

### Errata E-012/T-113

Pierwotny replay E-010 podmieniał `style.load_examples()` i
`style.load_profiles()` fixturem. Z tego powodu nie wykrył, że surowy hash
korpusu na checkoutcie Windows różni się od pinu wyłącznie przez CRLF/LF i
normalny pisarz kończy się przed dispatch. E-012 ujawniło A-102. N-023 dodało
kanonizację końców linii przed hashem, a adapter N-004 przestał podmieniać
loader stylu. Po tej korekcie replay ponownie przeszedł 7/7 na prawdziwym
loaderze, a pełna regresja T-117 wyniosła 49/49. Historyczne hashe T-104 powyżej
pozostają odciskami pierwotnej próby, nie aktualnego kodu.

## 8. Wniosek

N-004 otrzymuje status `FULL_PIPELINE_FIXED_OFFLINE;
LIVE_BLOCKED_MISSING_CREDENTIALS`. Pełny replay nie jest już otwartą hipotezą
offline. Dowód prawdziwego API pozostaje obowiązkowy i ma gotowy, limitowany
launcher, lecz nie został sfabrykowany przy braku poświadczeń. Substack nie był
użyty w żadnej próbie.
