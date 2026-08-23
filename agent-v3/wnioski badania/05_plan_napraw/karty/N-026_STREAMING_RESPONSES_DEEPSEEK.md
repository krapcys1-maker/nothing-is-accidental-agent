# N-026 — streaming `/responses` DeepSeek

- **Status:** `FIXED_OFFLINE; LIVE_DISCOVERY_BLOCKED_BUDGET`
- **Ustalenie:** A-108
- **Zakres:** discovery z web search przez `/responses`

## Kontrdowód

E-017 wykonało jedno normalne discovery. Buforowane body zostało przerwane po
60,750 s bez JSON-u, usage i request ID. Rezerwacja 0,10 USD pozostaje
`UNKNOWN`, bez retry.

## Naprawa

Adapter `/responses` czyta SSE, wymaga kompletnego zdarzenia końcowego i usage,
składa tekst odpowiedzi oraz zachowuje fail-closed dla niepełnego strumienia.

## Dowód i ograniczenie

Parser `/responses`: 4/4 PASS offline. Sąsiedni `/chat/completions`: 4/4 PASS.
Dodatni live discovery nie został wykonany, ponieważ konserwatywna ekspozycja
DeepSeek przekroczyła 5 USD. Zielony parser nie jest dowodem żywej integracji.

## Kryterium zamknięcia

Po rekoncyliacji budżetu jeden normalnie routowany discovery musi zakończyć
SSE z treścią, usage, znanym kosztem, pełnym kontraktem źródeł i bez retry.
