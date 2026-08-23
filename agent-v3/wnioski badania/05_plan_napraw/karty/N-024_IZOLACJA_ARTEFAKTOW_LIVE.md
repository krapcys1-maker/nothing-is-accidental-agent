# N-024 — izolacja lokalnych artefaktów live

- **Status:** `FIXED_OFFLINE`
- **Ustalenie:** A-103
- **Zakres:** lokalne sekrety i `.live-experiments/` wyłącznie w V3

## Kontrdowód

T-125: `.env` był ignorowany przez nadrzędną regułę, ale pełny `result.json`
E-012 nie był. Artefakt ma pełne prompty i może mieć surowe odpowiedzi, więc nie
jest bezpiecznym domyślnym kandydatem do commitu.

## Zmiana

Lokalny `.gitignore` ignoruje dokładnie `.env` i `.live-experiments/`. Nie
usuwa dowodu z dysku i nie zmienia zapisu harnessu.

## Dowód

T-126: obie ścieżki przechodzą `git check-ignore`; skan dokładnych wartości
kluczy daje zero trafień poza `.env`; artefakt T-118 zachowuje SHA-256
`323FA3E264FFAD4E6A9F9D92A80531373F08DB05F966A2B87C350D1EDCECB59C`.

## Ograniczenie

Ignorowanie nie jest szyfrowaniem ani polityką retencji. Lokalny operator nadal
musi chronić katalog roboczy i kopie zapasowe.
