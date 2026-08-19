# Co gdzie stoi — mapa dla wracającego po przerwie

Ten plik istnieje, bo nazwy się mylą. Katalog **`agent-v2/`** to *obecny,
działający bot*, a gałąź **`v2-test`** to *eksperyment z bankiem researchu*.
To dwie różne rzeczy i „v2" znaczy w nich co innego.

## Dwie gałęzie, dwa światy

| | `main` | `v2-test` |
|---|---|---|
| co to jest | **PRODUKCJA** — bot, który publikuje na żywo | **EKSPERYMENT** — bank researchu, bibliotekarz, styl grafik |
| gdzie stoi na serwerze | `~/nothing-is-accidental-agent` | `~/nia-v2-test` |
| kto to uruchamia | `nia-agent.timer` (11:20, 19:20, 23:40 UTC) | wyłącznie ręcznie |
| baza | `~/nothing-is-accidental-agent/agent-v2/data/agent-v2.db` | `~/nia-v2-test/agent-v2/data/agent-v2.db` |
| czy publikuje | **tak, na żywo** | **nie — kod odmawia** |
| punkt powrotu | tag `v1` = commit `57c9496` | — |

**Bazy nie mogą się pomylić.** `config.DATA_DIR` wyprowadza się z położenia
`config.py`, więc osobny klon dostaje osobną bazę, osobne artykuły i osobne
pliki stanu automatycznie. Nie ma zmiennej środowiskowej, którą można zapomnieć
ustawić.

## Dlaczego kopia testowa nie może opublikować

W `run.py` stoi `odmow_publikacji_z_kopii()`. Jeśli obok `config.py` leży plik
**`TO_JEST_KOPIA_TESTOWA`**, to `--wyslij` kończy przebieg odmową. Produkcja
tego pliku nie ma i działa normalnie.

To nie jest ostrożność na wyrost: wystarczy raz dopisać `--wyslij` z pamięci
mięśniowej i eksperyment wyjdzie na żywe konto, czego nie da się cofnąć.

## Jak wrócić do stanu sprzed eksperymentów

```
git checkout v1
```

Tag `v1` wskazuje commit `57c9496` — pięć artykułów, publikacja bez człowieka,
14 zestawów testów. Cokolwiek stanie się na `v2-test`, ten punkt zostaje.

## Reszta orientacji

- **`agent-v2/JAK_WROCIC.md`** — dostęp do serwera, drogi awaryjne, co
  zmienialiśmy w systemie i po co. Na serwerze wskazuje na to
  `~/PRZECZYTAJ_MNIE.txt`.
- **`agent-v2/PROGRESS.md`** — księga prac: co zbudowane, co otwarte, dziennik.
- **`archiwum/`** — stary agent (~40 000 linii, 42 migracje, dwa artykuły).
  Tylko do czytania. Nie wskrzeszamy.

## Uwaga o starych gałęziach

Na zdalnym repozytorium leży ~55 gałęzi po starym agencie (`dev/*`, `codex/*`,
`stage3/*`, `prec5/*` i podobne). Nic z nich nie korzysta. Zostały, bo ich
kasowanie to decyzja właściciela, nie moja — ale przy szukaniu czegokolwiek
warto wiedzieć, że aktualne są **tylko** `main` i `v2-test`.
