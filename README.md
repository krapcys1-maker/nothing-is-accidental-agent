# Nothing Is Accidental Agent — pakiet architektury V1

Pliki:

- `ARCHITECTURE.md` — pełna architektura wstępna,
- `config/accounts.example.yaml` — profile kont i tryby pracy,
- `config/growth_policy.example.yaml` — cele, limity i zasady wzrostu,
- `.env.example` — ustawienia lokalne bez sekretów,
- `IMPLEMENTATION_PROMPT.md` — pierwszy prompt do Claude Code/Cowork.

## Najważniejsze założenia

- lokalne uruchomienie bez zewnętrznego serwera,
- Anthropic API jako jedyny silnik językowy i researchowy,
- Playwright jako deterministyczny adapter przeglądarki,
- SQLite w MVP,
- obsługa wielu kont,
- tryb FULL_PUBLICATION i COMMENT_ONLY,
- architektura gotowa na późniejszy serwer/chmurę,
- obowiązkowe limity antyspamowe i wyłącznik bezpieczeństwa.

## Ważne

Nie wpisuj hasła do Substacka do `.env`.
Zaloguj każde konto ręcznie w osobnym profilu Playwright.
