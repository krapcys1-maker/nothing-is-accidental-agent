"""Boundary evidence for the single USD ROUND_HALF_UP contract."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.core.money import quantize_usd, sum_usd
from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import ModelUsage, Run, RunStatus, WorkflowType
from app.research import cost_estimator
from app.research.cost_estimator import estimate_staged_research_cost_usd, estimate_with_retries
from app.workflows.research.pipeline import ResearchRunSummary, _current_run_cost


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.0000004", "0.000000"),
        ("0.0000005", "0.000001"),
        ("0.0000006", "0.000001"),
        ("0.0000015", "0.000002"),
        ("0.1234565", "0.123457"),
        ("0.1234575", "0.123458"),
    ],
)
def test_usd_boundary_is_decimal_string_round_half_up(raw, expected):
    assert quantize_usd(raw) == quantize_usd(expected)


def test_components_are_summed_before_the_single_contract_boundary():
    components = ("0.0000005", "0.0000005", "0.0000005")

    assert sum_usd(components) == quantize_usd("0.0000015") == quantize_usd("0.000002")
    assert sum(quantize_usd(value) for value in components) == quantize_usd("0.000003")


@pytest.mark.parametrize(
    ("base", "expected"),
    [("0.1234565", 0.123457), ("0.1234575", 0.123458)],
)
def test_estimator_uses_the_same_half_up_boundary(base, expected):
    assert estimate_with_retries(float(base), 0) == expected


def test_usage_tracker_rounds_cache_read_cache_write_and_web_together(settings, storage):
    pricing = {
        "input_per_mtok": 0.0,
        "output_per_mtok": 0.0,
        "cache_read_per_mtok": 0.0000005,
        "cache_write_per_mtok": 0.0000005,
        "web_search_per_1k": 0.0005,
    }
    tracker = UsageTracker(replace(settings, pricing=pricing), storage)

    assert tracker.estimate_cost(Usage(
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
        web_search_requests=1,
    )) == 0.000002


def test_storage_and_research_cost_cache_store_canonical_usage(settings, storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(
        id="money-cache", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.DRY_RUN,
    ))

    for _ in range(2):
        storage.add_model_usage(ModelUsage(
            run_id="money-cache", provider="fake", model="fake", task="research",
            estimated_cost_usd=0.0000005, dry_run=True,
        ))

    stored = storage.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage WHERE run_id=? ORDER BY id", ("money-cache",),
    ).fetchall()
    assert [row[0] for row in stored] == [0.000001, 0.000001]
    assert storage.get_run("money-cache").cost_usd == 0.000002


@pytest.mark.parametrize(
    ("source_count", "expected"),
    [(2, 0.000001), (3, 0.000002)],
)
def test_staged_estimator_aggregates_raw_per_source_before_rounding(
        settings, monkeypatch, source_count, expected):
    pricing = dict(settings.pricing)
    pricing.update({
        "input_per_mtok": 0.0,
        "output_per_mtok": 0.0,
        "web_search_per_1k": 0.0005,
    })
    monkeypatch.setattr(
        cost_estimator, "_EXPECTED_PER_SEARCH_TOKEN_COST_USD", Decimal("0"),
    )

    estimates = estimate_staged_research_cost_usd(
        replace(settings, pricing=pricing),
        discovery_max_searches=0,
        discovery_max_tokens=0,
        expected_source_count=source_count,
        max_web_searches_per_source=1,
        extraction_max_tokens=0,
        synthesize_max_tokens=0,
        forwarded_context_tokens=0,
    )

    # One source displays as 0.000001, but the active staged aggregation must
    # use the pre-boundary 0.0000005 value rather than multiplying that display.
    assert estimates["extraction_per_source"].expected_usd == 0.000001
    assert estimates["extraction_total"].expected_usd == expected
    assert estimates["total"].expected_usd == expected


def test_pipeline_current_run_cost_uses_decimal_ledger_aggregation(settings, storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(
        id="money-pipeline-total", account_id=account.id,
        workflow=WorkflowType.RESEARCH, status=RunStatus.DRY_RUN,
    ))
    for value in (0.1, 0.2):
        storage.add_model_usage(ModelUsage(
            run_id="money-pipeline-total", provider="fake", model="fake", task="research",
            estimated_cost_usd=value, dry_run=True,
        ))

    assert _current_run_cost(storage, "money-pipeline-total") == 0.3


def test_cli_summary_compares_canonical_cost_and_cap(capsys):
    from scripts import run_capped_research

    summary = ResearchRunSummary(
        run_id="canonical-cli", account_id="account", topic_id=1,
        dry_run=True, cost_usd=0.1 + 0.2,
    )
    run_capped_research._print_result(summary, 0.3, 0.3, max_web_searches=0)

    output = capsys.readouterr().out
    assert "OK, w limicie" in output
    assert "PRZEKROCZONY" not in output
