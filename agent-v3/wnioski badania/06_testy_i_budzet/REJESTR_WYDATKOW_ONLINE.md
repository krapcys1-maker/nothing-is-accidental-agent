# Rejestr wydatków online Agent V3

**Waluta:** USD  
**Zasada:** każda pozycja jest dopisywana przed i po wywołaniu; brak wpisu oznacza brak zgody procesu testowego na koszt

## Saldo

| Dostawca | Limit | Wydano | Zarezerwowano | Pozostało |
|---|---:|---:|---:|---:|
| Anthropic | 5.00 | 0.00 | 0.00 | 5.00 |
| DeepSeek | 5.00 | 0.00 | 0.00 | 5.00 |
| GPT/OpenAI — tylko obrazy | 2.00 | 0.00 | 0.00 | 2.00 |
| **Razem** | **12.00** | **0.00** | **0.00** | **12.00** |

## Dziennik transakcji

| ID | Data/czas | Karta naprawy | Dostawca/model | Cel | Limit wywołania | Koszt rzeczywisty | Status | Artefakt |
|---|---|---|---|---|---:|---:|---|---|
| — | 2026-08-21 | dokumentacja | — | audyt lokalny i kwerenda publicznego kodu | 0.00 | 0.00 | zakończony | `../07_dziennik_badan/DZIENNIK_BADAN.md` |

## Reguła aktualizacji

1. Przed wywołaniem dopisz pozycję ze statusem `RESERVED` i najgorszym kosztem.
2. Odejmij rezerwację od dostępnego salda.
3. Po odpowiedzi wpisz koszt rzeczywisty i status `COMPLETED`, `FAILED_BILLED` albo `FAILED_UNBILLED`.
4. Zachowaj identyfikator odpowiedzi dostawcy tylko w lokalnym artefakcie testowym, bez klucza API.
5. Jeżeli koszt nie jest znany, wpisz `UNKNOWN`, zablokuj dalsze wywołania dostawcy i nie traktuj go jako 0.
