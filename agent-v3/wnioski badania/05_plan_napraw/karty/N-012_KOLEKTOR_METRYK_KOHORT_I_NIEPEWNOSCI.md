# N-012 — kolektor metryk, kohort i niepewności

- **Status:** `OPEN`
- **Ustalenia:** A-008–A-011, A-052, A-072, A-099
- **Zakres:** `editorial.py`, pomiary, sygnały, snapshoty i pamięć wyników

## Hipoteza

Jeżeli każda treść ma dokładne zewnętrzne ID, snapshoty są pobierane w stałych
horyzontach, a wynik jest porównywany tylko z właściwą kohortą, to pamięć może
uczyć się bez utożsamiania zasięgu z jakością.

## Reuse

Zachować tabele `content_items`, `metric_snapshots`, `audience_signals`, funkcje
pomiarowe i raport alarmu. Ujednolicić ich identyfikatory i semantykę.

## Testy wymagane

- publikacja przenosi dokładne external ID do `content_items`;
- snapshot 1H/24H/7D trafia do tej samej treści;
- brak metryki pozostaje `NULL`, nie zerem;
- baseline rozdziela rodzaj treści, wiek i horyzont;
- mała próba nie aktywuje reguły, a rollback cofa szkodliwą obserwację.

## Kryterium końca

Każda aktywna obserwacja ma próbę, efekt, kontrprzykład, ważność i możliwy
automatyczny rollback.

