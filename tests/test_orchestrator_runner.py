"""Testy bezpieczeństwa app/orchestrator/runner.py (P0-3, docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md)."""
from __future__ import annotations

import pytest

from app.orchestrator.runner import run_research


def test_run_research_force_real_is_blocked():
    """P0-3: 'python -m app.main run-research --real' (force_real=True) wołał
    przestarzały, jednoetapowy pipeline przez klienta zbudowanego BEZ max_web_searches
    (brak max_uses -> nieograniczona liczba web searchy w jednym wywołaniu) i bez capu
    kosztu per-run. Musi się zatrzymać PRZED zbudowaniem czegokolwiek (nawet przed
    load_settings()), nie tylko przed samym wywołaniem API."""
    with pytest.raises(RuntimeError, match="run_capped_research"):
        run_research(topic_id=1, force_real=True)
