# N-017 — nieznany koszt i retry modelu

## Metryka

- **Ustalenie:** A-086, wykryte przez E-007
- **Status:** FIXED_OFFLINE; LIVE_REPLAY_OPEN
- **Start/zakończenie offline:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** klasyfikacja błędów transportu modelu, koszt `UNKNOWN`,
  rezerwacja, retry i rekoncyliacja
- **V2:** wyłącznie odczyt; zakaz zapisu

## Dowód problemu

Live-test DeepSeek zakończył syntezę wyjątkiem `RemoteProtocolError: peer closed
connection without sending complete message body (incomplete chunked read)`.
Żądanie dotarło do dostawcy, lecz klient nie otrzymał kompletnej odpowiedzi.
V3 zapisało wywołanie jako `ok=0`, `cost_usd=0`, `price_verified=0`, a normalna
konfiguracja uznaje każdy `httpx.TransportError` za przejściowy i może wykonać
retry. Nie ma dowodu, że pierwsza próba nie została naliczona.

Eksport dostawcy dostarczył później kontrdowodu: w godzinie testu dwa żądania
Pro miały łącznie 7830/6788 tokenów. Po odjęciu kompletnej recenzji synteza
miała 3038/3307 i koszt 0,00855294 USD. Zapisane zero było więc fałszywe.

## Hipoteza naprawy

Jeżeli adapter rozdzieli błąd **przed wysłaniem** od błędu **po rozpoczęciu
odpowiedzi**, ten drugi otrzyma trwały stan `COST_UNKNOWN`, zatrzyma automatyczne
retry i zachowa nierozliczoną rezerwację, to proces nie będzie przedstawiał
nieznanego kosztu jako zera ani ryzykował podwójnego naliczenia.

## Plan kontrdowodów

1. `ConnectError` przed wysłaniem może być bezpiecznie ponowiony.
2. `ReadTimeout`, `ReadError`, `RemoteProtocolError` i niepełny body po dispatch
   nie są automatycznie ponawiane.
3. Tabela `calls` rozróżnia koszt równy zero od kosztu nieznanego.
4. Nierozliczona próba zachowuje rezerwację i blokuje kolejne wywołanie tego
   dostawcy w danym eksperymencie.
5. Rekoncyliacja może atomowo ustawić koszt albo zwolnić rezerwację bez
   nadpisywania historii.
6. Restart procesu zachowuje blokadę i nie zamienia `UNKNOWN` na sukces.

## Implementacja V3

- `calls.cost_status` rozróżnia `RESERVED`, `KNOWN` i `UNKNOWN`;
- `reserved_usd`, `provider_request_id` i `reconciled_at` zachowują ślad
  ekspozycji oraz późniejszego rozliczenia;
- rezerwacja powstaje i jest commitowana przed dispatch zarówno dla tekstu,
  jak i obrazu;
- tylko `ConnectError`, `ConnectTimeout` i `PoolTimeout` sprzed dispatch mogą
  zostać automatycznie ponowione;
- błędy odczytu, niepełny protokół, 429/5xx i błędy nierozpoznane przechodzą do
  `UNKNOWN` bez retry;
- `RESERVED/UNKNOWN` blokuje następne wywołanie tego dostawcy również po
  ponownym otwarciu SQLite;
- limity liczą znany koszt plus zachowaną rezerwację, więc `UNKNOWN` nie jest
  zerem budżetowym;
- `reconcile_unknown_call()` rozlicza próbę dokładnie raz, wymaga odnośnika do
  dowodu i atomowo zwalnia rezerwację;
- podsumowanie przebiegu i alarm pokazują liczbę nierozliczonych prób oraz
  zachowaną ekspozycję.

## Wyniki

`tests/test_model_call_accounting.py`: 7/7 metod PASS. Kontrtesty obejmują:

1. `RemoteProtocolError` bez retry, `UNKNOWN` i rezerwację po restarcie;
2. bezpieczne ponowienie `ConnectError` przy jednej trwałej rezerwacji;
3. wyczerpane błędy połączenia jako znane zero;
4. jednokrotną, atomową rekoncyliację 0,00855294 USD i zwolnienie blokady;
5. fail-closed dla błędów odczytu/protokołu;
6. różnicę między rzeczywistym zerem i kosztem nieznanym w schemacie.
7. blokadę obrazu o stałej cenie, gdy nie mieści się w pozostałym budżecie.

Testy sąsiednie: zapis wywołań 16/16, doba i budżet 14/14, cennik 4/4 PASS.
Sieć i koszt dodatkowy: 0 USD. V2: tylko odczyt.

## Ograniczenie dowodu

Nie wykonano ponownego płatnego wywołania tylko po to, aby sztucznie odtworzyć
awarię transportu. Dodatnia rekoncyliacja adaptera ma dowód offline, a prawdziwy
przypadek kosztowy pochodzi z E-007. Automatyczne pobieranie request-level bill
z API dostawców pozostaje osobnym zadaniem; do tego czasu nieznany stan blokuje
dostawcę fail-closed.

## Rollback

Zmiana schematu musi być addytywna. Cofnięcie aktywnego adaptera nie może usuwać
informacji o nierozliczonej próbie ani zwalniać jej rezerwacji.
