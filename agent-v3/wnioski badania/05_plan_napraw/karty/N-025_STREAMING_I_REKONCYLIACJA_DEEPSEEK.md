# N-025 — streaming i rekoncyliacja transportu DeepSeek

- **Status:** `FIXED_OFFLINE; LIVE_BLOCKED_THREE_UNKNOWN; BILL_RECONCILIATION_REQUIRED`
- **Ustalenie:** A-104
- **Zakres:** zwykłe `/chat/completions`, SSE, usage, koszt UNKNOWN i blokada dostawcy
- **V2:** wyłącznie odczyt; bez zmian

## Kontrdowód live

Trzy różne wywołania `scout` na normalnym `deepseek-v4-pro` zakończyły się po
120,703–180,875 s identycznym `RemoteProtocolError: incomplete chunked read`:

| Próba | Znaki user promptu | SHA-256 user promptu | Czas | Wynik |
|---|---:|---|---:|---|
| T-118/E-012 | 23 107 | `431dee8e…286a4` | 180,844 s | UNKNOWN 1,60 USD |
| T-132/E-014 | 23 193 | `802d568a…1b15` | 180,875 s | UNKNOWN 1,60 USD |
| T-136/E-015 | 7 499 | `33cdb96…9adf68` | 120,703 s | UNKNOWN 1,60 USD |

Każde wejście miało inny hash. Trzecie było krótsze o 67,5% od pierwszego.
Żadne wywołanie nie używało web search. W każdym przypadku lokalny klient nie
otrzymał kompletnego body, usage, tokenów ani request ID.

## Hipoteza naprawy

Buforowane `httpx.post()` czekało na kompletne chunked body. Oficjalny kontrakt
DeepSeek przewiduje częściowe delty SSE, końcowe `data: [DONE]` i opcjonalny
końcowy chunk pełnego `usage`. Streaming powinien podtrzymywać połączenie w
trakcie długiego rozumowania i pozwolić klientowi odróżnić poprawny koniec od
niepełnego strumienia.

Źródło pierwotne:
[DeepSeek Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion/).

## Implementacja V3

- `_call_deepseek()` wysyła `stream=true` i
  `stream_options.include_usage=true`;
- parser przyjmuje wyłącznie linie `data:`, składa tylko `delta.content` i nie
  miesza prywatnego `reasoning_content` z JSON-em etapu;
- sukces wymaga `data: [DONE]`, pełnego `usage`, niepustej treści oraz
  `finish_reason=stop`;
- brak DONE/usage, wadliwy SSE i urwany transport pozostają błędem po dispatch,
  a więc kosztem UNKNOWN bez automatycznego retry;
- błąd protokołu zapisuje liczbę znaków częściowej treści oraz response ID,
  jeśli dostawca zdążył je przesłać;
- aktywny live DeepSeek jest zablokowany po trzech kolejnych UNKNOWN do czasu
  rekoncyliacji dowodu dostawcy.

## Dowód offline

`tests/test_deepseek_stream_transport.py` obejmuje:

1. pełny SSE z reasoning, dwiema deltami treści, usage i DONE;
2. czysty koniec bez DONE;
3. DONE bez żądanego usage;
4. `finish_reason=length`.

Pakiet transportu, księgowania i uprzęży: 25/25 PASS. N-017 nadal gwarantuje,
że błąd po rozpoczęciu odpowiedzi nie jest ponawiany i zachowuje rezerwację.

## Kryterium live

Status może przejść dalej dopiero po obu warunkach:

1. dostawca lub eksport rozliczy T-118, T-132 i T-136 albo potwierdzi ich
   brak naliczenia;
2. jeden nowy, odmienny scout w nowym ledgerze przejdzie SSE z DONE, usage,
   request ID, pełnym JSON-em i znanym kosztem.

Do tego czasu nie wolno wykonywać kolejnego DeepSeek dispatchu. Zielony parser
offline nie jest dowodem, że pośrednik sieciowy lub dostawca utrzyma prawdziwy
strumień.

## Rollback

Nie wolno wracać do buforowanego body bez dodatniego kontrdowodu live. Rollback
nie może zwolnić żadnej z trzech rezerw UNKNOWN ani usunąć ich artefaktów.
