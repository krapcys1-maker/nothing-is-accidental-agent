# N-004 — hermetyczny test fundamentu

## Metryka

- **Ustalenia:** A-023, A-044, A-059, A-098
- **Status:** FULL_PIPELINE_FIXED_OFFLINE; LIVE_BLOCKED_MISSING_CREDENTIALS
- **Start:** 2026-08-21
- **Baza:** codex/agent-v3-gpt, commit 57a9474362b8fa6d120027aa54afe1a918b65b0f
- **Zakres V3:** tests/test_prototype_safety.py i rejestr wyników
- **V2:** brak zmian i brak uruchamiania testów V2

## Hipoteza

Test z pustym rejestrem możliwości, kontrdowodem zamiast przeglądarki i konfiguracją badaną w podprocesie wykryje próbę sieci, przejęcie sekretu oraz zdalny draft przy wyslij=False. Kontrdowodem jest przejście testu po celowym złamaniu dowolnego z tych kontraktów.

## Stan przed

Brak testu centralnych możliwości, izolacji ogólnych sekretów i dowodu, że wyslij=False nie uruchamia przeglądarki. Pełny adapter fixture potoku redakcyjnego jeszcze nie istnieje; ta karta obejmuje fundament, nie całą jakość redakcyjną.

## Test kontrdowodu

- macierz możliwości i dynamiczny kill switch;
- twarda odmowa dla celu produkcyjnego;
- podmienione podlacz_sie nie może zostać wywołane w podglądzie;
- brak aktywnych odwołań wykonawczych V3 do V2;
- zero sieci, sesji i kosztu.

## Minimalna zmiana i rollback

Standardowa biblioteka unittest, pliki tylko w katalogu tymczasowym, żadnego API. Rollback usuwa jeden plik testowy.

## Dowody po zmianie

- test_prototype_safety.py zawiera 14 testów i używa wyłącznie unittest, podprocesów oraz katalogu tymczasowego;
- atrapa przeglądarki jest kontrdowodem: każde jej wywołanie kończy test błędem;
- pierwszy przebieg wykrył błąd kodowania CP1252, drugi jego drugi wariant; trzeci przeszedł 13/13;
- po rozszerzeniu o znacznik i nazwę sesji wynik wynosi 14/14 PASS;
- pełna bezpieczna regresja w projektowym środowisku: 35/35 plików PASS;
- wyłączono jawnie test sieciowy, test sygnałów Linuxa i katalog płatny;
- drzewo agent-v3/data przed i po teście odmowy CLI jest identyczne;
- koszt online: 0 USD.

Odcisk testu: ca47adc151ff779522904ba23514df1b4e17c85317d8782420466b936baf1da4.

## Wynik

Fundament hermetyczności został dowiedziony w pierwszej części karty. Poniższy
E-010 rozstrzyga później także hipotezę pełnego potoku fixture; akapit ten opisuje
historyczny wynik sprzed E-010, a nie bieżący status.

## Wynik E-010 — pełny replay

`pipeline_replay.run_fixture()` uruchamia zwykłe `run.main()` i prawdziwe
funkcje etapów. Zastępuje tylko transport modelu oraz publiczny fetch. Dodatnia
ścieżka przechodzi scout→feasibility→discovery→fetch→4×classify→synthesis→
warto_pisac→write→review→forma→bramki→provenance→lokalny save. Ujemna awaria
`write` zapisuje `FAILED/write` i nie tworzy artykułu.

- T-097: brak adaptera odtworzony jako `ModuleNotFoundError`;
- T-098: 1/2 przez błąd selektora artykuł/`.uwagi.md` w uprzęży;
- T-099: 7/7 PASS po korekcie;
- T-100: bezpieczeństwo 14/14, provenance 19/19, kontrakty 11/11;
- T-101: pełna regresja 47/47, `data/` bez zmiany hashy;
- T-103: prawdziwy preflight launchera odmówił przed workspace i dispatch,
  ponieważ brak obu kluczy API.
- T-104: finalna regresja po utwardzeniu launchera 47/47, `data/` bez zmian.

Launcher rdzenia ma exact routing, 8 dispatchy bazowo, maksymalnie 11 po
rewizji i twardy limit 1,50 USD. Nie importuje `browser`, nie ma `--wyslij` i
dopuszcza wyłącznie model oraz zamrożony publiczny fetch. Live nie został
wykonany: `agent-v3/.env` nie istnieje. Pełny raport:
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-010_PELNY_REPLAY_POTOKU.md`.

## Errata E-012 — prawdziwy loader stylu

Pierwotna atrapa E-010 podmieniała loader stylu i maskowała A-102: surowy hash
CRLF na Windows nie zgadzał się z pinem LF, więc normalny pisarz nie był
osiągalny. N-023 kanonizuje wyłącznie końce linii przed hashem. N-004 nie
podmienia już `style.load_examples/load_profiles`; T-114 ponownie przechodzi
7/7 na prawdziwym loaderze. Aktualna pełna regresja po N-010/N-023 wynosi 49/49
(T-117). Dowód jakości prawdziwego pisarza pozostaje otwarty do live E-012.
