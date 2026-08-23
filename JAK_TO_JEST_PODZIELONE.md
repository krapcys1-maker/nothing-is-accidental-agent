# Co gdzie stoi — mapa dla wracającego po przerwie

Ten plik istnieje, bo nazwy się mylą.

> **Zmiana z 23 sierpnia 2026.** Gałąź `v2-test` już nie istnieje — została
> wmergowana w `main` i usunięta razem z pięćdziesięcioma trzema innymi przy
> porządkach. Jej treść żyje w `main`; spis wszystkich usuniętych gałęzi
> z numerami commitów stoi w [`docs/GALEZIE_USUNIETE_2026-08-23.md`](docs/GALEZIE_USUNIETE_2026-08-23.md).
>
> **Kopia testowa na serwerze została** — nadal stoi w `~/nia-v2-test`
> ze znacznikiem `TO_JEST_KOPIA_TESTOWA` i nadal odmawia publikacji. Zmieniło
> się tylko to, że nie jest już osobną gałęzią.

## Dwa katalogi na serwerze, jedna gałąź

| | produkcja | kopia testowa |
|---|---|---|
| gdzie stoi | `~/nothing-is-accidental-agent` | `~/nia-v2-test` |
| gałąź | `main` | `main` |
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
14 zestawów testów — tyle było **wtedy**; dziś jest ich 43. Cokolwiek
stanie się dalej, ten punkt powrotu zostaje.

## Reszta orientacji

- **`agent-v2/JAK_WROCIC.md`** — dostęp do serwera, drogi awaryjne, co
  zmienialiśmy w systemie i po co. Na serwerze wskazuje na to
  `~/PRZECZYTAJ_MNIE.txt`.
- **`agent-v2/PROGRESS.md`** — księga prac: co zbudowane, co otwarte, dziennik.
- **`archiwum/`** — stary agent (~40 000 linii, 42 migracje, dwa artykuły).
  Tylko do czytania. Nie wskrzeszamy.

## Gałęzie — posprzątane 23 sierpnia 2026

Leżało tu ~55 gałęzi po starym agencie (`dev/*`, `codex/*`, `stage3/*`,
`prec5/*`). **Usunięte.** Na zdalnym repozytorium jest dziś jedna gałąź:
`main`.

Sprawdzone przed usunięciem, nie po: 52 z 54 były wmergowane w `main`, więc
ich commity żyją w historii głównej gałęzi; dwie pozostałe miały tagi
archiwalne wskazujące na te same commity. Spis wszystkich, z numerami commitów
i informacją gdzie każda przetrwała, stoi w
[`docs/GALEZIE_USUNIETE_2026-08-23.md`](docs/GALEZIE_USUNIETE_2026-08-23.md).

Odzyskanie dowolnej: `git checkout -b <nazwa> <sha>`.

Tagi zostają jako punkty powrotu — `v1`, `v2`, `archive/*` oraz
`prototyp-gpt-2026-08`.
