# Content & Growth Blueprint — Nothing Is Accidental

> **Status: strategic integration only.**
>
> Pełny, niemodyfikowany w sensie merytorycznym snapshot materiału Fable jest w [FABLE_GROWTH_EDITORIAL_REPORT.md](research/FABLE_GROWTH_EDITORIAL_REPORT.md). Ten blueprint go nie dubluje: rozdziela decyzje od propozycji i mapuje je na etapy. Nie jest specyfikacją wykonawczą ani potwierdzeniem wdrożenia.

## Statusy i granice

| Status | Znaczenie w tym dokumencie |
|---|---|
| **DECIDED** | decyzja już przyjęta w ADR; nie oznacza kodu |
| **PROPOSED** | kierunek z raportu Fable, wymagający przyszłego zadania/projektu |
| **PLANNED** | przypisane do etapu roadmapy, nadal bez implementacji |
| **DEFERRED** | świadomie odłożone; brak daty ani implementacji |
| **IMPLEMENTED** | **brak pozycji** — dokumentacja ani konfiguracja zamiaru nie są wdrożeniem |

Nie uruchamia się stąd modeli, API, publikacji ani innych działań zewnętrznych. Szacunki kosztów z raportu są **COST ESTIMATES — UNVALIDATED**: wymagają osobnej walidacji na realnym `model_usage`; wspólny obecny cennik FAST/QUALITY nie jest cennikiem produkcyjnym per model.

## Tożsamość, konta i prawo do SKIP

- **DECIDED — tożsamość NIA:** anonimowa marka redakcyjna o ukrytych systemach, bodźcach i decyzjach stojących za codziennymi rzeczami. Nie ma proaktywnego disclosure AI, fikcyjnej osoby, biografii ani doświadczeń; pytania o tożsamość otrzymują `NO_REPLY` (ADR-018).
- **DECIDED — izolacja kont:** NIA i publiczny build log mają odrębne `account_id`, głos, diversity memory, strategię i metryki. Transfer materiału między kontami wymaga jawnej decyzji człowieka (ADR-034).
- **DECIDED — SKIP:** harmonogram tworzy kandydatów, nie obowiązek publikacji. Negatywna bramka kończy się `SKIP` z reason code i bez automatycznej treści zastępczej (ADR-033).

Minimalne reason codes: `INSUFFICIENT_EVIDENCE`, `WEAK_THESIS`, `DUPLICATE_ANGLE`, `STYLE_REPETITION`, `REPUTATIONAL_RISK`, `LOW_EDITORIAL_VALUE`, `QUALITY_GATE_REJECTED`.

## Mapowanie pełnego raportu Fable na roadmapę

| Sekcja pełnego raportu | Status integracji | Docelowy etap / granica |
|---|---|---|
| 1. Executive summary | PROPOSED | kierunek strategiczny; nie zmienia bieżącej kadencji ani polityki |
| 2. Różnice: konta rosnące vs stojące | PROPOSED | Etap 7: hipotezy do oceny na własnych danych, nie fakty operacyjne |
| 3. Strategia 0–1000+ | PROPOSED | Etapy 6–7; dopiero po danych konta i właściwym poziomie autonomii |
| 4. Growth flywheel | PROPOSED | Etapy 3, 6 i 7; Research Card pozostaje warunkiem evidence, nie automatycznym powodem publikacji |
| 5. A1–A9, N1–N16, K1–K8 | PLANNED | Etap 3: artykuły oraz lokalne/dry-run Notes; Etap 6: publiczne Notes i komentarze |
| 6. Model routing | PROPOSED | Etap 3/7; osobne zadanie po walidacji kosztu i bez automatycznego fallbacku płatnego |
| 7. Audyt instrukcji pisania | PROPOSED | Etap 3; obecny podręcznik pozostaje nietkniętym źródłem do modularizacji |
| 8. Modularna architektura stylu | PLANNED | Etap 3: factual constitution, voice profile, format module, Article Brief, diversity memory, fact/style/growth audit |
| 9. Inspiracje i repertuar NIA | PROPOSED | Etap 3: funkcje stylistyczne, nigdy imitacja fraz, historii czy metafor autorów |
| 10. Metryki i E1–E10 | PLANNED | Etap 7: metryki per content item, `is_estimated`, eksperymenty i weekly strategy |
| 11. Granice autonomii | DECIDED | ADR-017/018; egzekwowanie Policy i publiczne operacje należą do Etapu 6 |
| 12. Zmiany do roadmapy | PLANNED | rozłożone na Etapy 2, 3, 6 i 7; nie tworzą zadania wstecznego dla Etapu 1 |
| 13. MUST / SHOULD / MAY | PROPOSED | kolejność kandydatów po spełnieniu zależności etapów; MUST nie znaczy wdrożone |
| 14. Plan bez kodowania | DEFERRED | wymaga osobnej zgody właściciela; nie uruchomiono go w tej integracji |
| 15. Pięć ryzyk wzrostowych | PROPOSED | ryzyka do monitorowania w Etapie 7, bez zmiany bieżącej polityki |
| 16. Lista źródeł researchu | MIXED / reference | pozostaje tylko w raporcie; [OF]/[TW]/[AN]/[WN] zachowują swoje znaczenie |

## Zakres etapów

### Etap 2 — evidence i research

**PLANNED:** fetch/evidence excerpt dla cytowalnych faktów; jest to warunek przyszłych formatów komentarzy K1 i K7. Nie zmienia ani nie zastępuje zdefiniowanego zakresu Etapu 2.

### Etap 3 — content pipeline, wyłącznie lokalnie/dry-run

**PLANNED:** modular prompt system; Article Brief; A1–A9; lokalne/dry-run N1–N16; fact audit; style audit; growth audit; SEO/discovery metadata oraz diversity memory.

- Format A7 jest dozwolony wyłącznie dla prawdziwych, zatwierdzonych eksperymentów związanych z tematyką NIA. Nie ujawnia prowadzenia konta przez agenta i nie tworzy doświadczeń fikcyjnych.
- Factual constitution jest nadrzędny wobec voice, formatu i growth.
- Diversity memory proponuje historię ostatnich 10 publikacji per typ: `opening_type`, `argument_architecture`, `tone`, `humor_level`, `example_domain`, `heading_count`, `ending_type`, `anchor_metaphors`, `format_id`.
- **PROPOSED:** deterministyczne ograniczenia powtórzeń z raportu są kandydatem do projektu Etapu 3; nie istnieją dziś w kodzie ani bazie.

### Etap 6 — operacje publiczne

**PLANNED:** wybór i publikowanie Notes, K1–K8, replies, restacki, rekomendacje, antyspam oraz `NO_REPLY` w granicach Policy i poziomu autonomii.

- Publiczna rekomendacja jest endorsementem marki i wymaga właściwej bramki.
- Zakazane pozostają DM, masowy follow, follow-back automation, sub-for-sub oraz odpowiedź na agresywną krytykę bez eskalacji.
- **PROPOSED:** limit ≤40% Notes z linkiem jest propozycją raportu, nie aktywną konfiguracją.

### Etap 7 — analytics i strategy loop

**PLANNED:** osobne `followers`, `free_subscribers`, `paid_subscribers` i `engaged_subscribers`; metryki konta i per content item; estymowana atrybucja z `is_estimated`; E1–E10; weekly strategy i optymalizacja parametrów.

- Follow nie jest subskrypcją (ADR-035).
- `n < 30 = SIGNAL, NOT PROOF`.
- Eksperyment zmienia jedną zmienną; nie może obchodzić evidence, fact audit, granic autonomii ani `SKIP`.

## Rejestr decyzji i brak wdrożeń

- **ADR-032:** modular editorial system — DECIDED jako kierunek, PLANNED od Etapu 3.
- **ADR-033:** right to SKIP — DECIDED jako zasada, egzekwowanie PLANNED.
- **ADR-034:** isolation NIA/build log — DECIDED jako granica danych i tożsamości, trwała obsługa danych PLANNED.
- **ADR-035:** followers/subscribers separate — DECIDED jako definicja, kolektor i raportowanie PLANNED w Etapie 7.
- **ADR-036:** Notes generation Stage 3 / public Notes Stage 6 — DECIDED jako podział zakresu, implementacja PLANNED.

Nie ma tu deklaracji `IMPLEMENTED`: nie powstały moduły promptów, YAML formatów, `series_diversity_memory`, generatorzy treści, audyty contentu, SEO metadata, routing contentu, kolektor metryk, atrybucja, eksperymenty, publiczne Notes, komentarze ani rekomendacje.
