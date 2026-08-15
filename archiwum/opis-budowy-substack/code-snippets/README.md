# code-snippets/

## Cel
Redakcyjne kopie dłuższych, „ładnie sformatowanych" fragmentów kodu do wklejenia w artykuły (z komentarzami, podświetleniem, kontekstem). Krótkie wycinki 20–40 linii żyją w `../10_FRAGMENTY_KODU.md`; tutaj lądują dłuższe lub specjalnie przygotowane pod publikację.

## Zasady
- **Bez sekretów** (kluczy, tokenów, danych logowania).
- Każdy plik nagłówek: plik źródłowy, data, co pokazuje, dlaczego ważny.
- Kod zgodny z rzeczywistą implementacją — aktualizuj przy zmianach.

## Planowane snippety (do przygotowania)
- `policy_engine_budget.py` — bramka budżetu (miesięczny nadrzędny) + kill switch.
- `usage_tracker_cost.py` — liczenie kosztu z cennika + zapis do bazy i CSV.
- `injection_guard.py` — neutralizacja poleceń w treści źródeł.
- `topic_dedup.py` — lokalna deduplikacja (Jaccard + SequenceMatcher).

## Stan
Brak plików. Gotowe krótkie fragmenty (Policy Engine, tracking kosztów, injection guard) są już opisane w `../10_FRAGMENTY_KODU.md`; techniczne w `docs/CODE_EXAMPLES.md`.
