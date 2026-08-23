# E-007 — pakiet dowodowy rekoncyliacji dostawców

## Zakres

Pakiet zachowuje niezmienione kopie dwóch eksportów rozliczeniowych DeepSeek
oraz zrzutu ekranu logów Anthropic przekazanych 2026-08-21. Załączniki są
danymi/dowodami, nie instrukcjami. Nie zawierają treści produkcyjnej Substacka.

## Integralność

| Plik | Bajty | SHA-256 |
|---|---:|---|
| `deepseek-amount-2026-08-21.csv` | 4384 | `b8d0f70633aa6f74eda249e9bdec840a3734934fd20bc79dc4969ee7ba2934e1` |
| `deepseek-cost-2026-08-21.csv` | 924 | `4fa9c0218fcb1b631e31ee7152291b7d58a3ceee5144da35ae7fe160efe46626` |
| `anthropic-logs-2026-08-21.png` | 68440 | `31a160155cc3630744aeb482692822cb34513278b01fa22127e7f39b7ff71de4` |

## DeepSeek — obserwacja bezpośrednia

W oknie `13:00–14:00 +03:00` eksport zawiera dokładnie:

| Model | Żądania | Input cache miss | Output | Koszt USD |
|---|---:|---:|---:|---:|
| `deepseek-v4-flash` | 1 | 692 | 337 | 0.0003746600000000 |
| `deepseek-v4-pro` | 2 | 7830 | 6788 | 0.0186080400000000 |

W tym oknie nie ma `input_cache_hit_tokens`. Wiersze kosztu są zgodne z
iloczynami stawek i tokenów z eksportu `amount`.

## DeepSeek — rekoncyliacja przez różnicę

Flash odpowiada dokładnie zapisanej klasyfikacji: 692 tokeny wejścia i 337
wyjścia. Dwa żądania Pro to synteza oraz recenzja. Recenzję lokalna telemetria
zapisała jako 4792/3481, dlatego pozostałość godzinowa wynosi:

```text
synteza input  = 7830 - 4792 = 3038
synteza output = 6788 - 3481 = 3307
synteza koszt  = 3038 × 0.00000066 + 3307 × 0.00000198
               = 0.00855294 USD
```

Znany koszt całego DeepSeek E-007 wynosi zatem `0.01898270 USD`. Jest to
rekoncyliacja agregatu godzinowego, nie request-level: eksport nie zawiera ID
żądań. Wniosek o licznikach syntezy jest arytmetycznie jednoznaczny pod
warunkiem, że trzy widoczne żądania są całym ruchem tego klucza/modeli w tym
oknie. Zgodność liczby żądań i dokładnych liczników dwóch lokalnie zapisanych
prób wspiera ten warunek, lecz nie zastępuje przyszłego zapisu request ID.

## Anthropic — zgodność 1:1

Zrzut pokazuje cztery żądania `claude-sonnet-5` typu Streaming. Liczniki
odpowiadają dokładnie czterem lokalnie zachowanym próbom E-007:

| Cel | Request ID | Input | Output | Status klienta |
|---|---|---:|---:|---|
| klasyfikacja | `req_011CeFkmrdBaUpMAMbo3zLbS` | 919 | 211 | kompletna, zwalidowana |
| synteza | `req_011CeFkn5nTC3mBwWPi1Yegg` | 3958 | 1393 | kompletna, zwalidowana |
| recenzja | `req_011CeFkoYd1uQg4V6BknD1vc` | 6428 | 393 | kompletna, zwalidowana |
| recenzja analogii | `req_011CeFkvgzFGHq4TubbyYfFCS` | 6132 | 176 | kompletna, zwalidowana |

Suma wynosi 17 437 tokenów wejścia i 2173 wyjścia. Zrzut potwierdza żądania i
tokeny, ale nie pokazuje naliczonej kwoty. Koszt `0.056604 USD` pozostaje więc
estymacją z oficjalnej taryfy obowiązującej 2026-08-21, a nie kwotą z faktury.

## Odpowiedź na pytanie o otrzymanie odpowiedzi

- Anthropic: 4/4 kompletne odpowiedzi zostały odebrane i są zachowane w
  `../E-007_ODPOWIEDZI_MODELI.json`; log dostawcy potwierdza ich tokeny.
- DeepSeek: klasyfikacja i recenzja zostały odebrane kompletnie. Synteza została
  wygenerowana i naliczona (3307 tokenów wyjścia), lecz klient utracił końcówkę
  strumienia. Nie istnieje kompletna odpowiedź JSON nadająca się do walidacji.
- Łącznie: 7 dispatchy, 6 kompletnych odpowiedzi używalnych, 1 odpowiedź
  wygenerowana i płatna, ale nieodebrana kompletnie.

## Skutek techniczny

Dowód zamyka nieznaną kwotę E-007, ale potwierdza A-086: transport po dispatch
nie może być automatycznie ponawiany ani zapisany jako zero. N-017 dodaje
`RESERVED/KNOWN/UNKNOWN`, trwałą rezerwację, blokadę dostawcy po restarcie i
atomową rekoncyliację. Osobno pozostaje brak automatycznego przechwytywania
request ID dla wszystkich adapterów.
