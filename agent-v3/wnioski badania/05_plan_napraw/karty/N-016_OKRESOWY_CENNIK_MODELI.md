# N-016 — okresowy cennik modeli

## Metryka

- **Ustalenie:** A-087, wykryte przez E-007
- **Status:** `FIXED_OFFLINE; BILL_RECONCILIATION_OPEN`
- **Start:** 2026-08-21
- **Gałąź:** `codex/agent-v3-gpt`
- **Zakres V3:** taryfa Anthropic, kalkulator kosztu i test granicy daty
- **V2:** wyłącznie odczyt; zakaz zapisu

## Stan przed

`config.PRICING` wycenia Claude Sonnet 5 na 3 USD za milion tokenów wejścia i
15 USD za milion tokenów wyjścia. Oficjalny cennik Anthropic odczytany
2026-08-21 podaje taryfę promocyjną 2/10 do 2026-08-31 włącznie i taryfę 3/15
od 2026-09-01. Cztery wywołania E-007 zostały przez V3 zaksięgowane jako
0,084906 USD, podczas gdy bieżąca taryfa daje estymację 0,056604 USD.

## Hipoteza i kontrdowód

Jeżeli taryfa Sonnet 5 stanie się funkcją czasu UTC z jawną granicą
2026-09-01T00:00:00Z, kalkulator ma zwrócić 2/10 sekundę przed granicą i 3/15
dokładnie na granicy. Kontrdowodem jest ta sama cena po obu stronach granicy
albo wynik E-007 inny niż 0,056604 USD dla 17 437 tokenów wejścia i 2 173
tokenów wyjścia.

## Plan

1. Zachować oba okresy taryfowe w kodzie zamiast nadpisywać historię.
2. Wybrać taryfę na podstawie świadomego `datetime` UTC.
3. Skierować `llm._cost()` przez funkcję okresową także dla Anthropic.
4. Oznaczyć stawkę jako oficjalną estymację, ale nie jako potwierdzoną fakturą.
5. Dodać test przed, na i po granicy oraz odtworzenie kosztu E-007.
6. Uruchomić bezpieczną regresję offline.

## Odciski przed zmianą

- `config.py`: `d1fab9bbfd0216eb7046b7aa0bfd4d1bdb38a741c84a657f6b63b407e8226dcd`;
- `llm.py`: `92bcf7fdf780dbc1ae63d240d2d983a64923ce2e0317016bb0898ffe35be509c`.

## Dowody po zmianie

- `stawka_anthropic()` wymaga świadomego czasu i zachowuje dwie taryfy Sonnet
  5: 2/10 przed 2026-09-01T00:00:00Z oraz 3/15 od tej granicy;
- `llm._cost()` nie czyta już dla Anthropic bezczasowego wiersza tabeli;
- stawka Sonnet ma `verified=False`, ponieważ źródłem jest oficjalny cennik,
  lecz rachunek konta nie został jeszcze zrekoncyliowany;
- `test_model_pricing.py`: **4/4 PASS**;
- finalna regresja po zmianie: **42/42 bezpiecznych plików PASS**;
- odtworzony koszt czterech wywołań Anthropic E-007: **0,056604 USD** według
  bieżącego cennika zamiast **0,084906 USD** zapisanych przez starą taryfę.

Odciski po zmianie:

- `config.py`: `519fcf9d8b109b775c1a6c6abe1970c5d143576dc5d9ec7b09e39619467434bf`;
- `llm.py`: `1cc38174e6053d67813dda2ce12fc479622cc0726208e0d4211fc733f8444db5`;
- `tests/test_model_pricing.py`:
  `2e0c299b5bf69e17eb5ee7304078fcc3cc48dd8bce02f19d2407c6f1e6972bf8`.

Pełny ślad wykrycia znajduje się w
[`RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md`](../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-007_LIVE_PROVENANCE.md).
