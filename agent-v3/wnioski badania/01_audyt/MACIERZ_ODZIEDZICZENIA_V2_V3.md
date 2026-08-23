# Macierz odziedziczenia V2 → V3

**Cel:** nie projektować ponownie mechanizmu, który już istnieje  
**Zasada:** `agent-v2` jest wyłącznie materiałem odczytowym; wszystkie przyszłe
zmiany dotyczą tylko V3

## Wynik ilościowy

Porównanie ścieżek wykazało 99 plików obecnych w obu wersjach. Dwadzieścia
dziewięć jest bajtowo identycznych. Jedenaście głównych modułów ma te same
nazwy i role; V3 dodaje siedem modułów kontraktowych:
`capabilities.py`, `editorial.py`, `model_contracts.py`, `mutation_ledger.py`,
`operational_day.py`, `provenance.py` i `safe_fetch.py`.

| Moduł | V2 linii | V3 linii | Dodane/usunięte linie | Decyzja reuse |
|---|---:|---:|---:|---|
| `alarm.py` | 536 | 567 | +52/-21 | zachować kontrole, podłączyć nowy stan |
| `browser.py` | 2305 | 2738 | +616/-183 | zachować adapter, domknąć ledger i ID |
| `config.py` | 1553 | 1616 | +92/-29 | zachować polityki, wydzielić wersjonowane kontrakty |
| `db.py` | 203 | 583 | +390/-10 | migrować istniejący model, nie tworzyć nowej bazy od zera |
| `gates.py` | 514 | 518 | +8/-4 | zachować bramki, dodać ważności i semantyczne dowody |
| `kanal.py` | 295 | 295 | 0/0 | reuse bez przepisywania |
| `kopia_subskrybentow.py` | 125 | 125 | +2/-2 | zachować walidator CSV, rozwiązać autonomię operacyjną |
| `llm.py` | 543 | 640 | +169/-72 | zachować routing, atomizować rezerwację i request ID |
| `run.py` | 1145 | 1409 | +403/-139 | zachować orkiestrację, wydzielić maszynę stanów |
| `stages.py` | 3025 | 3139 | +390/-276 | zachować etapy, opakować typami i transakcją |
| `style.py` | 106 | 106 | 0/0 | reuse, lecz profile włączyć do manifestu V3 |

## Prompty

Z 27 wspólnych plików promptów/materiałów 21 jest bajtowo identycznych. V3
zmienia przede wszystkim `klasyfikacja.md`, `pisarz.md`, `recenzent.md`,
`skaut.md` i `synteza.md` oraz dodaje `redaktor.md`. Oznacza to, że praca nad
głosem ma ewoluować na istniejącym materiale. Nie ma podstaw do tworzenia
nowego kompletu ról.

## Mapa pracy: reuse przed zmianą

| Karta V3 | Co już istnieje | Minimalne rozszerzenie V3 | Czego nie robić |
|---|---|---|---|
| N-004 | pełny `run.py`, etapy i dziesiątki fixture'ów V2/V3 | adaptery fixture, zegar i trwały replay | osobny demonstracyjny agent |
| N-010 | `stages.save`, `articles`, pliki Markdown, `content_items` | prepare/commit/rollback i jedno ID artefaktu | nowy format artykułu |
| N-011 | review, forma, gates, revise i decyzja jakości | pętla stanów z limitem iteracji i kwarantanną | zewnętrzna bramka akceptacji |
| N-012 | `editorial.py`, pomiary, alarm i dziennik zdarzeń | kanoniczne ID, horyzonty i kohorty | jeden globalny score |
| N-013 | korpus, dwa profile, prompty formatów | manifest głosu, profile gatunków, wspólna rubryka | nowa marka od zera |
| N-014 | `_prompt`, filtry i kontrakty JSON | typowane dane i zapora przed pierwszym bajtem | blacklistę kolejnych fraz |
| N-015 | istniejące testy promptów i płatne porównania | zamrożony korpus, rubryka i asercje | ocenę bez kryterium maszynowego |
| N-018 | timery, lock przebiegu i preflight V2 | immutable bundle, migracje, shadow/canary | kopiowanie `reset --hard` i celu V2 |
| N-019 | ledger publikacji i ID szkicu | osobny ledger zapisu szkicu | traktowanie draftu i publikacji jako jednej mutacji |
| N-020 | `calls.RESERVED` i limity | transakcyjne check-and-reserve | poleganie wyłącznie na locku `run.py` |
| N-021 | dokładne ID z `potwierdz_artykul` | przenieść ID do `content_items` i metryk | ponowne zgadywanie po tytule |

## Elementy bezpieczne do inspiracji z V2

- harmonogramy i uzasadnienie okien czasowych;
- wykrywanie trwającego przebiegu przed operacją release;
- importowy smoke test modułów;
- selektory oraz procedury potwierdzające skutki;
- istniejące kontrprzykłady tekstów, rytmu i kosztu.

## Elementy V2, których nie kopiować wykonawczo

- produkcyjny handle, sesję, `.env`, bazę i katalog danych;
- `git reset --hard` jako rollback;
- bezpośrednie `--wyslij` w unitach systemd;
- fail-open i liczenie kliknięcia jako sukcesu;
- ręczne migracje `ALTER TABLE` bez wersji;
- opisy wymagające pozamaszynowego zatwierdzenia treści.

Wniosek: V3 jest ewolucją V2 z warstwą dowodową. Największą oszczędnością nie
jest kopiowanie całych plików, lecz zachowanie działających etapów i dokładanie
do nich brakującej własności jednym testem na raz.

