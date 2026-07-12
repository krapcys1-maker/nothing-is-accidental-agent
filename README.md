# Nothing Is Accidental Agent

Lokalny (local-first) agent AI budowany do autonomicznego prowadzenia publikacji Substack „Nothing Is Accidental" — wybór tematów, research z dowodami, pisanie, ocena jakości, publikacja, interakcje i pętla strategii — w twardych limitach budżetu i z pełnym audytem każdej decyzji, kosztu, błędu i interwencji człowieka.

## Source of Truth

The only authoritative architecture and implementation documents are:

- `MASTER_ARCHITECTURE.md`
- `IMPLEMENTATION_ROADMAP.md`
- `CURRENT_PROJECT_STATE.md`

All other historical plans and audits are archived in `docs/archive/superseded_plans/` and must not be used as implementation guidance.

Obowiązujące dodatkowo (logi, nie plany): `docs/DECISIONS.md` (rejestr ADR), `docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md`, `docs/HUMAN_INTERVENTIONS.md`, `docs/COSTS.csv`, `docs/RESEARCH_LOG.md` oraz kronika redakcyjna `opis-budowy-substack/` (materiał do serii artykułów). Podręcznik stylu pisania: `instrukcja dla pisania artykulow/`.

## Stan projektu (skrót — pełny obraz w CURRENT_PROJECT_STATE.md)

- Zbudowane i przetestowane: konfiguracja, SQLite+migracje, Policy Engine (budżety, kill-switch), księgowanie kosztów, pipeline tematów z deduplikacją, etapowy research A1/A2/B z wznawialnością po restarcie, deterministyczna bramka jakości, injection guard, diagnostyka odpowiedzi. **139 testów, wszystkie offline.**
- Niezbudowane: scheduler/kolejka, artykuły/Notes, approval/autonomia, publikacja (Playwright), interakcje, analityka, panel.
- Zero publikacji na Substacku; realny koszt dotąd: ~0,50 USD z limitu 40 USD/mies.

## Uruchomienie

```bash
pip install -e .[dev]           # + .[llm] tylko do realnych wywołań API
python -m pytest                # 139 testów, bez sieci
python -m app.main run-topics --count 6      # dry_run (zero kosztu)
python -m app.main run-research              # dry_run (zero kosztu)
# realny research: WYŁĄCZNIE scripts/run_capped_research.py (pre-flight, capy,
# --estimate-only); wymaga każdorazowej zgody właściciela na wydatek
python scripts/run_capped_research.py --topic-id 2 --estimate-only
```

Konfiguracja: `.env` (sekrety, modele — patrz `.env.example`) + `config/*.yaml` (limity, wagi, konta). Domyślnie `DRY_RUN=true`.

## Ważne zasady

- Nie wpisuj hasła do Substacka nigdzie — logowanie zawsze ręczne w osobnym profilu przeglądarki.
- Każde płatne lub publikujące uruchomienie wymaga osobnej, jawnej zgody właściciela.
- Repozytorium jest PRIVATE (ADR-021); jawność AI reguluje ADR-018.
