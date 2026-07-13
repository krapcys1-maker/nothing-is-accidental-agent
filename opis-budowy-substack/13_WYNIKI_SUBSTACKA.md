# 13 — WYNIKI SUBSTACKA

## Cel pliku
Chronologiczny zapis metryk publikacji: subskrybenci, obserwujący, otwarcia, kliknięcia, komentarze, polubienia, restacki, wejścia na profil, konwersja, źródła ruchu, najlepsze artykuły/Notes/komentarze. Źródło prawdy: tabela `metrics_daily` + `docs/METRICS_LOG.md`. Metryki, których Substack nie udostępnia, oznaczamy jako **estymacja** (`is_estimated`).

## Szablon wpisu dziennego
```markdown
### [YYYY-MM-DD]
- Subskrybenci (total / +delta):
- Obserwujący:
- Odsłony / otwarcia / kliknięcia:
- Komentarze / polubienia / restacki:
- Wejścia na profil:
- Konwersja (est.):
- Źródła ruchu:
- Uwagi:
```

## Szablon rankingu (tygodniowy)
```markdown
### Najlepsze w tygodniu <YYYY-Www>
- Artykuł: <tytuł> — <metryka>
- Note: <treść/skrót> — <metryka>
- Komentarz: <gdzie> — <metryka>
```

---

## Stan: brak danych (publikacja jeszcze nie ruszyła)
Na 2026-07-11 **nie opublikowano żadnej treści** (ADR-005: brak publikacji w MVP-0). Nie ma więc żadnych metryk. Poniżej **tabela bazowa (baseline)** do wypełnienia w dniu startu publikacji oraz lista metryk, które będą zbierane automatycznie vs ręcznie.

## Baseline (do wypełnienia w dniu startu — „dzień 0")
| Metryka | Dzień 0 | Uwaga |
|---|---|---|
| Subskrybenci | — | stan konta przed startem eksperymentu |
| Obserwujący | — | |
| Opublikowane artykuły | 0 | |
| Opublikowane Notes | 0 | |
| Opublikowane komentarze | 0 | |

## Co będzie zbierane automatycznie vs ręcznie
- **Automatycznie** (gdy powstanie `MetricsCollector`, Etap 5, tolerancyjny na błędy): subskrybenci, obserwujący, odsłony, polubienia, komentarze, restacki, wejścia na profil — o ile Substack je udostępnia w UI.
- **Estymowane / ręczne:** konwersja „profil → subskrypcja", „subskrypcje z Notes/komentarzy" — Substack nie daje pełnej atrybucji; oznaczane `is_estimated=1`, uzupełniane ręcznie tam, gdzie trzeba.

## Kontrakt metryk (PLANNED)

`followers`, `free subscribers`, `paid subscribers` i `engaged subscribers` są różnymi liczbami. Follow nie jest subskrypcją i nie będzie tak raportowany. Metryka per content item, estymowana atrybucja i weekly strategy należą do Etapu 7; każda nieobserwowalna atrybucja dostanie `is_estimated=true`, metodę i ograniczenia danych. Szczegóły: `docs/CONTENT_AND_GROWTH_BLUEPRINT.md`.

Pełny raport Fable dodaje jako **PLANNED** dashboard i E1–E10; nie daje jeszcze żadnego wyniku ani danych NIA. [OF], [TW], [AN] i [WN] w źródle pozostają rozdzielone, a follows nigdy nie są prezentowane jako subskrypcje.

## Rankingi (do wypełniania od pierwszego tygodnia publikacji)
- Najlepsze artykuły — po odsłonach / subskrypcjach / komentarzach.
- Najlepsze Notes — po reakcjach / restackach.
- Najlepsze komentarze — po odpowiedziach / wejściach na profil.

## Powiązania
- `docs/METRICS_LOG.md` (źródło), `12_EKSPERYMENTY.md`, `09_KOSZTY.md` (koszt/subskrybenta), `14_WNIOSKI_CZASTKOWE.md`

## [2026-07-13] Maintenance Etapu 1 nie dodaje wyniku publicznego

Zweryfikowane offline `maintain --once/--poll` porządkuje wyłącznie lokalne lease i stale runy. Nie uruchamia workera, nie wykonuje researchu, nie publikuje ani nie zbiera metryk, więc nie zmienia baseline’u: nadal 0 artykułów, 0 Notes, 0 komentarzy i brak danych NIA. One-shot oraz poll są VERIFIED OFFLINE; usługa schedulera systemowego pozostaje NOT_STARTED. Polityka okien redakcyjnych została później zweryfikowana offline, nadal bez publicznego działania; API live i działania paid/browser/public nie zostały uruchomione. Koszt: 0 USD.

## [2026-07-13] Harmonogram jobów nie jest wynikiem Substacka

Polityka okien redakcyjnych zapisuje jedynie przyszłą lokalną decyzję jako UTC w kolejce i odmawia jobowi prawa do claimu przed jego czasem. Nie wykonuje dispatchu, researchu, API, publikacji, komentarza ani odczytu metryk. Baseline publiczny pozostaje bez zmian: 0 artykułów, 0 Notes, 0 komentarzy i brak danych NIA. Polityka i eligibility są VERIFIED OFFLINE; usługa systemowa i końcowa akceptacja restartu są NOT_STARTED; paid/browser/public pozostają BLOCKED. Koszt: 0 USD.
