"""LA-01-C: configurable, bounded, invariant max_tokens across the whole flow."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.models import Topic, TopicStatus
from app.research.anthropic_client import AnthropicResearchClient
from app.research.cost_estimator import estimate_worst_case_search_call_usd
from app.research.durable_intent import (
    DEFAULT_REQUEST_MAX_TOKENS,
    MAX_REQUEST_MAX_TOKENS,
    MIN_REQUEST_MAX_TOKENS,
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    validate_cli_max_tokens,
)

from tests.conftest import write_approved_pricing_profile

MODEL = "dry-run-fake"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _real_settings(settings):
    from app.core.config import REAL_PROVIDER_PRICING_KEYS
    return replace(
        settings, dry_run=False, model_quality=MODEL, anthropic_api_key="test-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def _topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Max tokens topic", question="Why?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _enqueue(monkeypatch, storage, account, real_settings, *, extra):
    from scripts import run_capped_research
    profile_id, _ = write_approved_pricing_profile(real_settings.project_root, model=MODEL)
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: real_settings)
    argv = ["--topic-id", "1", "--real", "--operation-key", "maxtok", "--pricing-profile", profile_id, *extra]
    code = run_capped_research.main(argv)
    return code


def _persisted_intent(storage) -> DurableResearchExecutionIntent:
    row = storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id LIKE 'real-research-%'").fetchone()
    payload = json.loads(row["payload_json"])
    return DurableResearchExecutionIntent.from_payload(payload["execution_intent"])


# 11. CLI accepts a value lower than the default
def test_cli_accepts_lower_value():
    assert validate_cli_max_tokens(512) == 512
    assert 512 < DEFAULT_REQUEST_MAX_TOKENS


# 12 + 13 + 14. persisted == provider == projection for an explicit lower value
def test_lower_value_is_persisted_and_flows_to_provider_and_projection(monkeypatch, settings, storage, account):
    real = _real_settings(settings)
    _topic(storage, account)
    assert _enqueue(monkeypatch, storage, account, real, extra=["--max-tokens", "800"]) == 0
    intent = _persisted_intent(storage)
    assert intent.max_tokens == 800                                        # persisted
    client = AnthropicResearchClient(
        real.anthropic_api_key, real.model_quality, max_retries=0, timeout_seconds=60,
        max_web_searches=intent.max_web_searches, research_max_tokens=intent.max_tokens,
    )
    assert client._research_max_tokens == 800                              # provider receives identical
    priced = replace(real, pricing=intent.runtime_pricing())
    low = estimate_worst_case_search_call_usd(priced, max_web_searches=1, max_output_tokens=800)
    high = estimate_worst_case_search_call_usd(priced, max_web_searches=1, max_output_tokens=3000)
    assert low.output_cost_usd < high.output_cost_usd                      # projection uses the value


# 16. omitting the flag persists the approved default
def test_missing_flag_persists_default(monkeypatch, settings, storage, account):
    real = _real_settings(settings)
    _topic(storage, account)
    assert _enqueue(monkeypatch, storage, account, real, extra=[]) == 0
    assert _persisted_intent(storage).max_tokens == DEFAULT_REQUEST_MAX_TOKENS


# 17. zero / negative / too-large / float are rejected by the closed contract
@pytest.mark.parametrize("bad", [0, -1, MIN_REQUEST_MAX_TOKENS - 1, MAX_REQUEST_MAX_TOKENS + 1])
def test_out_of_range_rejected(bad):
    with pytest.raises(DurableExecutionIntentError):
        validate_cli_max_tokens(bad)


def test_float_and_bool_rejected():
    with pytest.raises(DurableExecutionIntentError, match="integer"):
        validate_cli_max_tokens(3000.0)
    with pytest.raises(DurableExecutionIntentError, match="integer"):
        validate_cli_max_tokens(True)


# 17b. the durable intent itself refuses an out-of-bound persisted value
def test_intent_rejects_out_of_bound_persisted_value(settings, account):
    real = replace(settings, model_quality=MODEL)
    with pytest.raises(DurableExecutionIntentError, match="provider bound"):
        DurableResearchExecutionIntent.from_settings(
            settings=real, account_id=account.id, topic_id=1, cap_usd=0.5, max_web_searches=1,
            question="Why?", niche=account.niche, max_tokens=MAX_REQUEST_MAX_TOKENS + 1,
        )


# 18. a real subprocess of the canonical CLI rejects a bad --max-tokens end-to-end
def test_subprocess_cli_rejects_bad_max_tokens():
    result = subprocess.run(
        [sys.executable, "scripts/run_capped_research.py",
         "--topic-id", "1", "--real", "--operation-key", "x", "--max-tokens", "0"],
        cwd=_PROJECT_ROOT, capture_output=True, text=True,
        env={**_subprocess_env()},
    )
    assert result.returncode != 0
    assert "max_tokens" in (result.stdout + result.stderr)


def _subprocess_env() -> dict:
    import os
    env = dict(os.environ)
    env["NIA_TEST_MODE"] = "1"
    return env
