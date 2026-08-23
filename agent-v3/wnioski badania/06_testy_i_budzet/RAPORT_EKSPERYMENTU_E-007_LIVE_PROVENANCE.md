# E-007 — live-test pochodzenia twierdzeń na prawdziwych modelach

## Errata autoryzacji modelu

Ramię Anthropic tego eksperymentu nie było uruchomieniem normalnego V3.
Historyczna uprząż po argumencie `anthropic` wykonywała runtime override
`classify`, `synthesis` i `review` na `claude-sonnet-5`, chociaż bieżący
`config.MODEL_FOR` przypisywał te etapy do DeepSeek. Zgoda na budżet Anthropic
nie była zgodą na zmianę modelu. Cztery widoczne w logu Anthropic żądania
pochodzą właśnie z tego nieuprawnionego override: klasyfikacja, synteza,
recenzja główna i recenzja analogii.

Wyniki i koszt zachowano jako historyczny materiał empiryczny, ale nie wolno
ich przedstawiać jako walidacji standardowego routingu V3. Automatyczny wybór
ramienia Sonnet usunięto z uprzęży; teraz akceptuje ona tylko `configured`,
wymaga domyślnego DeepSeek Flash/Pro dla trzech etapów i ma test statyczny
blokujący ponowną mutację lub środowiskowy override routingu. Nie wykonano
nowego live-testu po tej korekcie.

## Abstrakt

Eksperyment sprawdził, czy trzy zmienione w N-009 granice modelowe działają nie
tylko na fixture'ach odpowiedzi, ale także wobec prawdziwych API. Ten sam
syntetyczny dokument przekazano DeepSeek V4 i Claude Sonnet 5. Badano dokładność
cytatów klasyfikatora, poprawność ID i więzi syntezy oraz zdolność recenzenta do
wykrycia faktu ukrytego w interpretacji.

Claude Sonnet 5 przeszedł wszystkie trzy etapy i dodatkowy kontrprzykład
analogii. DeepSeek przeszedł klasyfikację i recenzję, lecz synteza zakończyła
się niepełnym strumieniem HTTP bez kompletnej, używalnej odpowiedzi. Późniejszy
eksport dostawcy dowiódł, że synteza wygenerowała 3307 tokenów wyjścia i została
naliczona. Wynik całości to
`LIVE_PARTIAL_PASS`, nie pełne zamknięcie. Eksperyment ujawnił dwa niezależne
defekty: brak stanu nieznanego kosztu po niepełnej odpowiedzi (A-086/N-017) i
bezczasowy, zawyżony cennik Sonnet 5 (A-087/N-016).

## 1. Pytania badawcze

1. Czy prawdziwy model skopiuje fragmenty dosłownie, tak aby kod mógł związać
   je z offsetami i hashami dokumentu?
2. Czy prawdziwy model zbuduje kartę wyłącznie z istniejących ID fragmentów i
   liczb?
3. Czy recenzent rozróżni fakt, zdanie mieszane i czystą interpretację oraz
   zatrzyma zmyśloną przesłankę?
4. Czy ten sam kontrakt jest wykonalny u dwóch dostawców?
5. Czy telemetria kosztu pozostaje prawdziwa podczas sukcesu i awarii?

## 2. Hipotezy

- **H1:** klasyfikator obu dostawców zwróci co najmniej po jednym dokładnym
  fragmencie zawierającym `20 watts`, `240` i `18%`.
- **H2:** synteza zwróci co najmniej 5 twierdzeń i 3 liczby, a
  `provenance.bind_card()` zatwierdzi wszystkie więzi.
- **H3:** cztery jednostki recenzji otrzymają kolejno pary
  `FACT/SUPPORTED`, `MIXED/SUPPORTED`, `MIXED/UNSUPPORTED` i
  `INFERENCE/NOT_APPLICABLE`.
- **H4:** zewnętrzna analogia zawierająca fakt o praktyce zostanie oznaczona
  `MIXED/UNSUPPORTED`.
- **H5:** każda próba będzie miała rozliczony albo jawnie nieznany koszt;
  awaria nie będzie przedstawiona jako pewne zero.

## 3. Przedmiot i zamrożony korpus

Korpus jest fikcyjnym dokumentem miejskim, skonstruowanym wyłącznie do testu.
Nie opisuje prawdziwej instytucji i nie wymaga wyszukiwania. SHA-256 tekstu:

`f09c82c4de02825f5b1b057886e1d9a9f91a231d5c308f2d5944f03d7e98ddb5`.

Zawiera osiem krótkich zdań o hipotetycznym rozporządzeniu o oświetleniu:
datę, limit 20 watów, prospektywne zastosowanie, pilotaż 240 opraw, wynik 18%
po 6 miesiącach, brak pomiaru bezpieczeństwa i kosztów, grandfathering oraz
publiczne wysłuchanie. Pytanie brzmiało: „What did the Harbor Lighting Ordinance
require and what did its pilot establish?”.

Recenzja otrzymała cztery jednostki, w tym fałszywą przesłankę „the pilot
prevented 12 accidents”. Dodatkowa próba użyła zdania: „Vehicle emissions rules
usually spare older cars, so my reading is that the same turnover mechanism is
at work.”

## 4. Dostawcy i preflight

Przed płatnym wywołaniem wykonano bezkosztowy odczyt list modeli z obu API.
DeepSeek potwierdził `deepseek-v4-flash` i `deepseek-v4-pro`; Anthropic
potwierdził `claude-sonnet-5`, `claude-opus-5` i `claude-fable-5`. Nazwy są
zgodne z [listą modeli DeepSeek](https://api-docs.deepseek.com/api/list-models/)
i [przeglądem modeli Anthropic](https://platform.claude.com/docs/en/about-claude/models/overview).

Użyte modele:

| Dostawca | Klasyfikacja | Synteza | Recenzja |
|---|---|---|---|
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro` | `deepseek-v4-pro` |
| Anthropic | `claude-sonnet-5` | `claude-sonnet-5` | `claude-sonnet-5` |

Nie użyto narzędzi web-search dostawców. Sonnet nie zmienił pliku konfiguracyjnego
ani routingu produkcyjnego, lecz został nieuprawnienie podstawiony w pamięci
procesu testowego. Dlatego jego ramię jest porównaniem historycznym, nie testem
normalnej konfiguracji V3.

## 5. Procedura

1. Historyczną uprząż `tests/platne/test_provenance_live.py` uruchomiono osobno
   dla każdego dostawcy; wybór ramienia Anthropic wykonywał opisany w erracie,
   nieuprawniony override modelu.
2. Proces otrzymał sekrety tylko przez tymczasowe zmienne `AGENT_V3_*`; nie
   utworzono pliku `.env` w V3.
3. Tryb `model_test` zezwalał wyłącznie na model i publiczny odczyt. Nie
   konfigurowano konta Substack ani możliwości mutujących.
4. Każdy dostawca miał osobną SQLite w katalogu tymczasowym.
5. Retry ustawiono na zero, aby pojedyncza próba była identyfikowalna i nie
   zwielokrotniła kosztu.
6. Sufity wyniosły 3 000 tokenów dla klasyfikacji i 6 000 dla syntezy oraz
   recenzji.
7. Odpowiedź przechodziła ten sam ścisły parser, kontrakt wersjonowany i binding
   pochodzenia co aktywny potok.
8. Po zauważeniu faktograficznych analogii w syntezie wykonano jedną dodatkową,
   ograniczoną próbę recenzji wyłącznie u Anthropic.

## 6. Wyniki

### 6.1. DeepSeek

| Etap | Wynik | Dowód |
|---|---|---|
| klasyfikacja | PASS | `PRIMARY`, trafność 1.0, 8 dokładnych fragmentów, 7 liczb wyliczonych przez kod |
| synteza | FAIL/RECONCILED | `RemoteProtocolError`, niepełny chunked body, brak kompletnego JSON-u; eksport: 3038/3307 tokenów i 0,00855294 USD |
| recenzja | PASS | dokładnie oczekiwane cztery klasy/statusy; „12 accidents” jako `MIXED/UNSUPPORTED` |

Znany koszt dwóch kompletnie odebranych odpowiedzi w lokalnej telemetrii wyniósł
0,01042976 USD. Eksport godzinowy dostawcy zawiera dokładnie jedno żądanie Flash
692/337 oraz dwa żądania Pro łącznie 7830/6788. Po odjęciu recenzji 4792/3481
synteza ma 3038 tokenów wejścia, 3307 wyjścia i koszt 0,00855294 USD. Cały koszt
DeepSeek E-007 wyniósł **0,01898270 USD**. To rekoncyliacja agregatu godzinowego:
eksport nie zawiera request ID, ale liczba żądań oraz dokładne liczniki dwóch
lokalnie zapisanych prób są zgodne. Rezerwacja może zostać zwolniona.

### 6.2. Anthropic

| Etap | Wejście | Wyjście | Wynik |
|---|---:|---:|---|
| klasyfikacja | 919 | 211 | PASS — 6 dokładnych fragmentów, wszystkie trzy fakty rdzeniowe obecne |
| synteza | 3 958 | 1 393 | PASS strukturalny — 7 twierdzeń, 5 liczb, pełny binding v1 |
| recenzja główna | 6 428 | 393 | PASS — cztery oczekiwane pary klasy/statusu |
| recenzja analogii | 6 132 | 176 | PASS — `MIXED/UNSUPPORTED` |
| **Razem** | **17 437** | **2 173** | **4/4 prób PASS** |

Stara konfiguracja V3 zapisała 0,084906 USD według 3/15 USD za milion tokenów.
[Cennik Anthropic](https://platform.claude.com/docs/en/about-claude/pricing)
obowiązujący 2026-08-21 podaje dla Sonnet 5 okresowe 2/10 do 31 sierpnia i 3/15
od 1 września. Estymacja bieżącej opłaty wynosi więc 0,056604 USD. Nie jest to
jeszcze kwota zrekoncyliowana z rachunkiem dostawcy.

Zrzut logów Anthropic potwierdza cztery request ID i dokładnie te same pary
tokenów: 919/211, 3958/1393, 6428/393 i 6132/176. Lokalne artefakty zawierają
cztery kompletne ciała odpowiedzi; zrzut nie pokazuje jednak kwot rozliczenia.

### 6.3. Rekoncyliacja odpowiedzi

- Anthropic: 4/4 odpowiedzi kompletne i używalne.
- DeepSeek: 2/3 odpowiedzi kompletne i używalne; synteza została wygenerowana
  oraz naliczona, ale nie została odebrana jako kompletny JSON.
- Razem: 7 dispatchy, 6 kompletnych odpowiedzi, 1 odpowiedź płatna i niepełna.

Niezmienione eksporty, zrzut, hashe i pełne wyprowadzenie arytmetyczne zapisano
w [`artefakty/E-007_rekonsyliacja_dostawcow/README.md`](artefakty/E-007_rekonsyliacja_dostawcow/README.md).

### 6.4. Wynik hipotez

| Hipoteza | DeepSeek | Anthropic | Wniosek |
|---|---|---|---|
| H1 dokładne fragmenty | PASS | PASS | potwierdzona na jednym korpusie |
| H2 karta z ID | brak wyniku | PASS | częściowo potwierdzona |
| H3 zdania mieszane | PASS | PASS | potwierdzona na jednym kontrprzykładzie u obu dostawców |
| H4 analogia mieszana | nie badano po blokadzie kosztu | PASS | pojedynczy dodatni dowód |
| H5 prawdziwy koszt | FAIL | FAIL przed N-016 | powstały A-086 i A-087 |

## 7. Kontrola semantyczna poza asercjami uprzęży

Synteza Sonnet spełniła schemat i więzi ID, ale w `parallel_mechanisms` opisała
typowe zachowania kodeksów budowlanych, norm emisji i systemów legacy. Te fakty
nie pochodziły z fixture. To falsyfikuje założenie, że samo polecenie w prompcie
powstrzyma każdą zewnętrzną przesłankę.

Obrona końcowa zadziałała dla przepisanej analogii o emisjach: recenzent
zaklasyfikował ją jako `MIXED/UNSUPPORTED` i wyjaśnił, że karta dotyczy wyłącznie
oświetlenia. Nie dowodzi to stuprocentowego recallu. Dowodzi natomiast, że nowa
klasa `MIXED` nie jest wyłącznie konstrukcją testu offline i została wykonana
poprawnie przez prawdziwy model.

## 8. Nieudane próby i informacje uboczne

1. DeepSeek synteza: niepełny strumień. Nie wykonano retry. Eksport dostawcy
   potwierdził później wygenerowanie i naliczenie odpowiedzi.
2. Pierwsza wersja uprzęży nie zamknęła połączenia SQLite przed usuwaniem
   katalogu tymczasowego na Windows. Wyniki i telemetria zostały wydrukowane
   przed błędem, a następna wersja jawnie zamyka połączenie. Nie jest to błąd
   V3 runtime, ale jest częścią historii eksperymentu.
3. Live ujawniło rozjazd cennika Sonnet; poprawiono go w N-016 i dodano 4 testy
   granicy daty.

## 9. Koszt i granice bezpieczeństwa

- znany koszt DeepSeek i estymacja Anthropic: **0,07558670 USD**;
- koszt DeepSeek: **0,01898270 USD**, zrekoncyliowany z eksportem godzinowym;
- koszt Anthropic: **0,056604 USD EST.**, tokeny potwierdzone, kwota bez rachunku;
- budżet GPT/OpenAI: nietknięty;
- Substack, browser, sesja, e-mail, deployment, publikacja i produkcyjne dane:
  **nieużyte**;
- V2: tylko odczyt, bez zmian wykonanych przez eksperyment.

## 10. Zagrożenia trafności

- jeden dokument syntetyczny nie reprezentuje długich ustaw, PDF-ów ani
  chaotycznych stron;
- po jednym przebiegu na model nie mierzy wariancji generatywnej;
- nie uzyskano kompletnej odpowiedzi syntezy DeepSeek mimo 3307 naliczonych
  tokenów wyjścia;
- badano trzy granice, nie pełną ścieżkę pisarz–rewizja–zapis;
- nie mierzono głosu, rytmu, atrakcyjności tekstu ani jakości całego artykułu;
- koszt Anthropic jest obliczony z oficjalnej taryfy, nie potwierdzony rachunkiem;
- eksport DeepSeek jest godzinowy i nie ma request ID; rozdział kosztu syntezy
  opiera się na jednoznacznej różnicy agregatu i lokalnie zapisanej recenzji;
- wynik analogii pokazuje jeden sukces obrony, a nie jej recall statystyczny.

## 11. Reprodukcja

Uprząż pozostaje w `tests/platne/` i nie wchodzi do zwykłej regresji. Obecnie
akceptuje wyłącznie routing `configured`; historyczne argumenty dostawców są
odrzucane. Nie powinna być uruchamiana pętlą. Surowe odpowiedzi,
metryki tokenów i błąd transportu zapisano w
[`artefakty/E-007_ODPOWIEDZI_MODELI.json`](artefakty/E-007_ODPOWIEDZI_MODELI.json).
Dowody rozliczeniowe zachowano w
[`artefakty/E-007_rekonsyliacja_dostawcow/`](artefakty/E-007_rekonsyliacja_dostawcow/README.md).

Po poprawce cennika wykonano `test_model_pricing.py` 4/4 PASS oraz pełną
regresję 42/42 bezpiecznych plików PASS.

## 12. Konkluzja

N-009 nie jest zbiorem wyłącznie papierowych kontraktów. Prawdziwe modele
wykonały dosłowne cytowanie i nową recenzję `MIXED`, a Sonnet wykonał również
pełną syntezę z istniejących ID. Jednocześnie eksperyment spełnił swoją rolę
falsyfikacyjną: ujawnił brak pełnego wyniku DeepSeek, nieuczciwe zero po awarii,
zły cennik i fakty dopisane w polu analogii. Eksport dostawcy dowiódł, że
przerwany strumień był płatny, co bezpośrednio potwierdziło potrzebę N-017.

Właściwy status pozostaje `LIVE_PARTIAL_PASS`, bo nie ma kompletnej syntezy
DeepSeek. N-017 ma teraz dowód offline: koszt nieznany zatrzymuje retry,
zachowuje rezerwację i blokadę po restarcie, a rekoncyliacja jest atomowa.
Następnie należy zwiększać korpus semantyczny oraz testować pełną ścieżkę
artykułu.
