# METRICS_LOG

## Cel

Dziennik metryk publikacji i eksperymentu. Rejestruje wzrost konta „Nothing Is Accidental" oraz koszt i nakład człowieka. Część metryk Substack udostępnia wprost (subskrybenci, wyświetlenia, polubienia, komentarze, restacki), część trzeba **estymować** — Substack nie daje twardej atrybucji „profil → subskrypcja" ani „subskrypcja z konkretnej Note/komentarza". Każda estymacja jest oznaczana jako estymacja. Źródło prawdy dla danych maszynowych: tabela `metrics_daily` (kolumna `is_estimated`).

## Zasady

- Wpis dzienny (lub w dniu, gdy zbierane są metryki).
- Dane pewne oddzielone od estymacji (kolumna/oznaczenie `est`).
- Bez sekretów; bez danych osobowych czytelników.
- Koszt jednego subskrybenta = koszt API w okresie / liczba nowych subskrybentów (oznacz jako estymację, gdy mianownik mały).

## Szablon wpisu (dzienny)

```markdown
### [YYYY-MM-DD]
- **Konto:** nothing_is_accidental
- **Subskrybenci:** N (Δ +/-)
- **Obserwujący:** N
- **Wyświetlenia:** N
- **Otwarcia (newsletter):** N / %
- **Kliknięcia:** N
- **Polubienia:** N
- **Komentarze:** N
- **Restacki:** N
- **Wejścia na profil:** N (est., jeśli szacowane)
- **Źródła ruchu:** np. Notes / komentarze / search / recommendations (opis)
- **Konwersja profil → subskrypcja:** % (EST — Substack nie podaje wprost)
- **Koszt 1 subskrybenta:** USD (EST)
- **Czas pracy człowieka:** ~N min (spójne z HUMAN_INTERVENTIONS)
- **Uwagi:** anomalie, braki danych, zmiany UI utrudniające zbiór metryk
```

## Tabela zbiorcza (opcjonalna, do szybkiego przeglądu)

| Data | Subskr. | Δ | Wyśw. | Polub. | Koment. | Restacki | Wejścia profil (est) | Koszt/sub (est) | Czas człowieka |
|------|---------|---|-------|--------|---------|----------|----------------------|-----------------|----------------|
| — | — | — | — | — | — | — | — | — | — |

---

## Wpisy

_(brak — metryki pojawią się po starcie zbierania danych; w MVP-0 nie zbieramy metryk z Substacka)_
