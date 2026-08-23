# N-010 — transakcyjny zapis artykułu

- **Status:** `FIXED_OFFLINE; POWER_LOSS_NOT_PROVEN`
- **Ustalenia:** A-013, A-041, A-042, A-055
- **Zakres:** wyłącznie V3; plik artykułu, uwagi, `articles`, `content_items`,
  rewizje i graf pochodzenia

## Hipoteza

Jeżeli wszystkie artefakty jednego artykułu mają stabilne `article_id` przed
zapisem, pliki powstają przez prepare+atomic replace, a SQLite zatwierdza
odwołania dopiero po gotowych plikach, to awaria w dowolnym punkcie pozostawi
albo kompletny artefakt, albo stan jawnie odzyskiwalny.

## Reuse

Zachować `stages.save()`, format Markdown, tabelę `articles`, `content_items`,
`article_revisions` i finalizację provenance. Nie projektować nowego formatu
tekstu ani nowej bazy.

## Testy wymagane

1. Fault injection po każdym zapisie pliku i przed każdym commitem.
2. Rewizja musi od początku dostać właściwe `article_id`.
3. Restart rozpoznaje przygotowany, zatwierdzony i osierocony artefakt.
4. Brak grafu lub niezgodny hash blokuje commit.
5. Pełny replay N-004 przechodzi bez resztek w `data/`.

## Kryterium końca

Nie istnieje osiągalny stan „plik bez rekordu”, „rekord bez pliku”, rewizja bez
artykułu ani opublikowany rekord bez finalnego grafu.

## Wynik E-011

- stary zapis po wymuszonym błędzie inserta zostawiał dwa finalne pliki i zero
  rekordów — T-105;
- nowy prepare/intent/transaction/recovery przeszedł 7/7 metod, w tym dziesięć
  punktów fault injection, śmierć procesu przed i po commicie, tamper oraz
  idempotentne ponowienie — T-106;
- rewizja i `content_items` dostają właściwe `article_id` wewnątrz tej samej
  transakcji;
- regresja sąsiednia PASS, a pełna regresja po N-010: 48/48 w 46,683 s,
  `data/` bez zmian — T-107/T-109.

Nie badano zaniku zasilania i trwałości wpisu katalogowego po `os.replace` na
rzeczywistym systemie plików. Pełny raport:
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-011_TRANSAKCYJNY_ZAPIS_ARTYKULU.md`.
