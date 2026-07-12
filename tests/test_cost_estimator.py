"""Testy kalibrowanego estymatora kosztu — dokumentuje i pilnuje incydentu z
2026-07-11 (docs/ERRORS_AND_FAILURES.md): pierwotny pre-flight szacunek 0.095 USD
wobec realnego kosztu 0.25 USD (błąd ~+163%, potwierdzone w konsoli Anthropic).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.research.cost_estimator import (
    MIN_SAFETY_MARGIN,
    estimate_no_search_call_usd,
    estimate_worst_case_search_call_usd,
)

# Cennik zgodny z REALNYM .env projektu (nie z arbitralnego fixture'u w conftest.py) —
# kalibracja w cost_estimator.py jest oparta na TYCH konkretnych stawkach.
_REAL_PRICING = {
    "input_per_mtok": 1.00,
    "output_per_mtok": 5.00,
    "cache_read_per_mtok": 0.10,
    "cache_write_per_mtok": 1.25,
    "web_search_per_1k": 10.00,
}

_HISTORICAL_OLD_ESTIMATE_USD = 0.095  # ówczesny (wadliwy) pre-flight szacunek, 2026-07-11
_HISTORICAL_REAL_COST_USD = 0.25      # potwierdzone w konsoli Anthropic (0.21 tokeny + 0.04 search)


@pytest.fixture
def real_pricing_settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        project_root=tmp_path, data_dir=data_dir, db_path=data_dir / "agent.db",
        costs_csv_path=tmp_path / "COSTS.csv", pricing=dict(_REAL_PRICING),
    )


# --- Regresja: incydent 2026-07-11 (temat #2 "suitcase", run 1b649314-...) ---

def test_historical_old_estimate_underestimated_real_cost():
    """Dokumentuje fakt historyczny: 0.095 USD < 0.25 USD (błąd ~+163%)."""
    assert _HISTORICAL_OLD_ESTIMATE_USD < _HISTORICAL_REAL_COST_USD
    ratio = _HISTORICAL_REAL_COST_USD / _HISTORICAL_OLD_ESTIMATE_USD
    assert ratio == pytest.approx(2.63, abs=0.01)


def test_new_estimator_would_not_have_cleared_the_failed_run(real_pricing_settings):
    """Dla DOKŁADNIE tych samych parametrów co nieudany run (max_uses=6,
    max_tokens=3000) nowy estymator NIE MOŻE zwrócić wartości <= realnego kosztu —
    inaczej powtórzylibyśmy błąd underestymacji, który doprowadził do incydentu."""
    e = estimate_worst_case_search_call_usd(
        real_pricing_settings, max_web_searches=6, max_output_tokens=3000)
    assert e.total_usd >= _HISTORICAL_REAL_COST_USD
    assert e.total_usd < _HISTORICAL_REAL_COST_USD * 5  # sanity: nie absurdalnie zawyżony


def test_new_estimator_exceeds_old_flawed_cap(real_pricing_settings):
    """Nowy estymator dla parametrów nieudanego runu musi przekraczać stary,
    wadliwy sufit (0.095 USD) — inaczej nic by się realnie nie zmieniło."""
    e = estimate_worst_case_search_call_usd(
        real_pricing_settings, max_web_searches=6, max_output_tokens=3000)
    assert e.total_usd > _HISTORICAL_OLD_ESTIMATE_USD


# --- Właściwości estymatora ---

def test_estimate_scales_with_max_web_searches(real_pricing_settings):
    low = estimate_worst_case_search_call_usd(real_pricing_settings, max_web_searches=2)
    high = estimate_worst_case_search_call_usd(real_pricing_settings, max_web_searches=8)
    assert high.total_usd > low.total_usd


def test_safety_margin_applied(real_pricing_settings):
    e = estimate_worst_case_search_call_usd(
        real_pricing_settings, max_web_searches=4, max_output_tokens=1200, safety_margin=0.50)
    assert e.total_usd == pytest.approx(e.subtotal_usd * 1.5, rel=1e-6)


def test_safety_margin_below_minimum_rejected(real_pricing_settings):
    too_low = MIN_SAFETY_MARGIN - 0.01
    with pytest.raises(ValueError):
        estimate_worst_case_search_call_usd(
            real_pricing_settings, max_web_searches=4, safety_margin=too_low)
    with pytest.raises(ValueError):
        estimate_no_search_call_usd(
            real_pricing_settings, max_output_tokens=2000, safety_margin=too_low)


def test_no_search_call_has_zero_search_fee(real_pricing_settings):
    e = estimate_no_search_call_usd(
        real_pricing_settings, max_output_tokens=2200, forwarded_context_tokens=2500)
    assert e.search_fee_usd == 0.0


def test_negative_inputs_rejected(real_pricing_settings):
    with pytest.raises(ValueError):
        estimate_worst_case_search_call_usd(real_pricing_settings, max_web_searches=-1)
    with pytest.raises(ValueError):
        estimate_no_search_call_usd(real_pricing_settings, max_output_tokens=-1)


# --- Projekcja: dwuetapowe podejście vs jednoetapowe, parametry zalecane po incydencie ---

def test_two_stage_projection_cheaper_than_single_call_worst_case(real_pricing_settings):
    single_call = estimate_worst_case_search_call_usd(
        real_pricing_settings, max_web_searches=6, max_output_tokens=3000)
    stage_a = estimate_worst_case_search_call_usd(
        real_pricing_settings, max_web_searches=4, max_output_tokens=1200)
    stage_b = estimate_no_search_call_usd(
        real_pricing_settings, max_output_tokens=2200, forwarded_context_tokens=2500)
    combined = stage_a.total_usd + stage_b.total_usd
    assert combined < single_call.total_usd
