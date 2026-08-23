# N-011 — autonomiczna rewizja i kwarantanna

- **Status:** `FIXED_OFFLINE; LIVE_REVISION_OPEN; POLICY_CALIBRATION_OPEN`
- **Ustalenia:** A-019, A-020, A-036, A-064, A-065
- **Zakres:** decyzja jakości, iteracje rewizji i stany artykułu V3

## Hipoteza

Wersjonowana maszyna stanów z ważnością uwag, ograniczoną liczbą rewizji i
pełną kontrolą po każdej zmianie potrafi autonomicznie wybrać tylko jeden wynik:
`READY_AUTONOMOUS`, `QUARANTINED_EVIDENCE` albo `QUARANTINED_EDITORIAL`.

## Reuse

Zachować `review`, `ocen_forme`, `deterministic_floors`, `revise` i
`quality_decision`. Zmienić orkiestrację i semantykę stanów, nie pisać nowego
recenzenta.

## Testy wymagane

- fakt bez pokrycia nie może być uznany za drobną uwagę;
- każda rewizja ponownie uruchamia wszystkie bramki i provenance;
- brak poprawy lub regresja kończy się autonomiczną kwarantanną;
- limit iteracji nie może prowadzić do publikacji przez fallback;
- tekst czysty przechodzi bez zbędnej rewizji.

## Kryterium końca

Aktywny kontrakt nie zawiera `NEEDS_REVIEW`, a każda końcowa decyzja jest
maszynowa, reprodukowalna i zapisana z wersją polityki.

## Wynik E-013

- polityka `autonomous-editorial@1` ma pełny SHA-256 kontraktu bramek, wag,
  reakcji i limitu dwóch iteracji;
- końcowe stany to wyłącznie `READY_AUTONOMOUS`,
  `QUARANTINED_EVIDENCE` i `QUARANTINED_EDITORIAL`;
- każdy rewrite ponawia review, formę, deterministyczne bramki i provenance;
- `NO_IMPROVEMENT`, `REGRESSION`, `LIMIT_REACHED` i awaria nie mają fallbacku
  do publikacji;
- długość według głębokości jest wykonywalną bramką;
- 13/13 testów N-011, pełny replay 7/7, testy sąsiednie oraz 50/50 pełnej
  regresji PASS; `data/` bez zmian.

Wagi polityki nie są jeszcze skalibrowane na reprezentatywnym korpusie, a
prawdziwy Fable nie wykonał rewizji, ponieważ T-118 pozostaje `UNKNOWN` 1,60
USD. Pełny raport:
`../../06_testy_i_budzet/RAPORT_EKSPERYMENTU_E-013_AUTONOMICZNA_REWIZJA_I_KWARANTANNA.md`.
