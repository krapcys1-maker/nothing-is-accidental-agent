# N-021 — wiązanie ID publikacji z treścią

- **Status:** `OPEN`
- **Ustalenie:** A-099
- **Zakres:** wynik browsera, `content_items`, metryki i sygnały

## Hipoteza

Jeżeli dokładne ID potwierdzone przez adapter zostanie zwrócone w typowanym
wyniku i zapisane w tej samej ścieżce co status `PUBLISHED`, wszystkie późniejsze
snapshoty i sygnały będą jednoznacznie związane z artykułem.

## Testy wymagane

- fixture potwierdzenia zwraca `external_id` i canonical URL;
- `mark_published` odmawia statusu bez potwierdzonego ID;
- ten sam ID nie może należeć do dwóch treści;
- pomiar po restarcie znajduje rekord po ID, nie podobieństwie tytułu;
- błąd zapisu ID pozostawia publikację do rekoncyliacji, nie fałszywe `PUBLISHED`.

## Kryterium końca

Każdy rekord `content_items.status='PUBLISHED'` ma dokładne zewnętrzne ID,
canonical URL i referencję próby publikacji.

