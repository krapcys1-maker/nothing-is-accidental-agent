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

- Zbudowane i przetestowane offline: konfiguracja, SQLite z **13 migracjami** (ostatnia `0013`), Policy Engine, kolejka/worker, ledger provider attempt oraz durable single-research `durable_provider_v2`. Kontrakt requestu utrwala kanoniczny snapshot wejść promptu, parametrów providera i stage; `max_tokens` z intentu jest tą samą wartością dla requestu, estymaty, polityki i rezerwacji. Każda kwota USD przechodzi przez `Decimal(str(value))`, obliczenia `Decimal` i jedno końcowe `ROUND_HALF_UP` do sześciu miejsc; staged aggregation, policy, cache, reservation i CLI nie podejmują decyzji na float. Settlement porównuje tę samą postać, a przekroczenie rezerwacji zapisuje usage, przechodzi do `NEEDS_RECONCILIATION` i blokuje sukces oraz attempt #2. **894 testy, wszystkie offline.**
- WAVE 0B ma status **`APPROVED WITH P2 — READY FOR CHECKPOINT`** po niezależnym końcowym review; nie jest jeszcze `CLOSED`, ponieważ commit checkpointu nie został wykonany. Etap 1 pozostaje `BLOCKED`; `durable_provider_v1` jest historyczny i fail-closed; aktywny jest jeden durable paid-execution flow `durable_provider_v2` z `durable_research_intent_v2`. Live API jest **ZABRONIONE**.
- Niezbudowane: durable realne A1/A2/B, realne resume i operator reconciliation, artykuły/Notes, approval/autonomia, publikacja (Playwright), interakcje, analityka i panel.
- Zero publikacji na Substacku; realny koszt dotąd: ~0,50 USD z limitu 40 USD/mies.

## Uruchomienie

```bash
pip install -e .[dev]           # + .[llm] tylko do realnych wywołań API
python -m pytest                # 894 testy, bez sieci
python scripts/run_test_partitions.py --parts 4 --verify  # pełne SHA-256 node ID
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
