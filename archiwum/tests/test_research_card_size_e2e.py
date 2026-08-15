"""Fake durable E2E kontraktu rozmiaru Research Card (fala 2026-07-18).

Prawdziwy Worker -> JobDispatcher -> run_research_pipeline -> parser -> schema ->
storage -> usage -> settlement na TYMCZASOWYCH bazach; provider zastąpiony
wstrzykniętym fake callerem (zero sieci, zero SDK, zero kosztu).

Scenariusze: A realistyczny sukces, B sukces dokładnie na granicach kontraktu,
C przekroczenie długości pola, D ucięcie (stop_reason=max_tokens),
E kontrakty typów (supports_claim=true, raw number w citable_numbers).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

import app.scheduler.dispatcher as dispatcher_module
from app.core.clock import FixedClock
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.llm.base import Usage
from app.models import JobStatus, RunStatus, Topic, TopicStatus
from app.model_routing import LogicalModelRole
from app.policies.policy_engine import PolicyEngine
from app.research import output_contract as oc
from app.research.anthropic_client import AnthropicResearchClient
from app.research.diagnostics import diagnostics_dir
from app.research.durable_intent import DurableResearchExecutionIntent
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from tests.conftest import write_approved_pricing_profile
from tests.controlled_provider_fixtures import seed_active_provider_role
from tests.test_research_card_size_contract import (
    _json,
    _max_payload,
    _realistic_payload,
)
from tests.test_wave0b_durable_provider import _operation_job, _topic

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def _real_settings(settings):
    from app.core.config import REAL_PROVIDER_PRICING_KEYS

    return replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-only-key",
        model_quality="size-contract-model",
        research_timeout_seconds=31,
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def _enqueue_durable_job(real_settings, storage, account, topic, *, key, max_tokens):
    profile_id, pricing_path = write_approved_pricing_profile(
        real_settings.project_root,
        model=real_settings.model_quality,
        prices=dict(real_settings.pricing),
    )
    pricing_profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real_settings.model_quality,
    )
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real_settings, account_id=account.id, topic_id=int(topic.id),
        cap_usd=1.0, max_web_searches=1,
        question=topic.question or topic.title, niche=account.niche,
        max_tokens=max_tokens,
        pricing_prices=pricing_profile.prices,
        pricing_profile_id=pricing_profile.profile_id,
        pricing_profile_version=pricing_profile.version,
        pricing_currency=pricing_profile.currency,
        pricing_unit=pricing_profile.unit,
    )
    payload = {
        "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single",
        "max_cost_usd": intent.cap_usd, "execution_intent": intent.as_payload(),
    }
    job = storage.enqueue_job(_operation_job(
        account, topic, key, key, cap=1.0, payload=payload,
    ))
    seed_active_provider_role(
        storage,
        role=LogicalModelRole.ARTICLE_RESEARCH,
        technical_model_id=intent.model,
    )
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="size-contract-e2e", now=NOW)
    return job


def _run_worker_once(real_settings, storage, monkeypatch, fake_provider):
    calls: list[str] = []

    def counted_provider(plan):
        calls.append("provider")
        return fake_provider(plan)

    def fake_client(*args, **kwargs):
        return AnthropicResearchClient(*args, caller=counted_provider, **kwargs)

    monkeypatch.setattr(dispatcher_module, "AnthropicResearchClient", fake_client)
    clock = FixedClock(NOW)
    policy = PolicyEngine(real_settings, storage, clock)
    dispatcher = JobDispatcher(
        settings=real_settings, storage=storage, policy=policy, clock=clock,
    )
    worker = Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner="size-contract-worker", lease_seconds=120,
        heartbeat_interval_seconds=1, heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real_settings.db_path),
        clock=clock,
    )
    return worker.run_once(), calls


def _ledger(storage, job_id, run_id):
    attempts = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=? ORDER BY attempt_no",
        (job_id,),
    ).fetchall()
    usage_count = storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (run_id,),
    ).fetchone()[0]
    reconciliations = storage.conn.execute(
        "SELECT count(*) FROM reconciliation_events",
    ).fetchone()[0]
    return [row["status"] for row in attempts], usage_count, reconciliations


def _assert_settled_exact_once(storage, job_id, run_id):
    statuses, usage_count, reconciliations = _ledger(storage, job_id, run_id)
    assert statuses == ["SETTLED"]
    assert usage_count == 1
    assert reconciliations == 0


# --- A. Realistyczny sukces --------------------------------------------------------


def test_e2e_a_realistic_success(settings, storage, account, monkeypatch):
    real_settings = _real_settings(settings)
    topic = _topic(storage, account, "size-a")
    job = _enqueue_durable_job(
        real_settings, storage, account, topic,
        key="size-e2e-a", max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    payload = _realistic_payload()
    payload["confidence_score"] = 0.72
    payload["source_quality_score"] = 0.65

    def provider(_plan):
        return _json(payload), Usage(
            input_tokens=16000, output_tokens=2727, web_search_requests=1,
            thinking_tokens=900,
        ), "end_turn"

    result, calls = _run_worker_once(real_settings, storage, monkeypatch, provider)
    assert result.status is WorkerIterationStatus.DONE
    assert calls == ["provider"]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.DONE
    run_id = job_row.run_id
    assert storage.get_run(run_id).status is RunStatus.SUCCESS
    assert storage.get_research_run(run_id).status.value == "COMPLETE"
    cards = storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (int(topic.id),),
    ).fetchone()[0]
    assert cards == 1
    _assert_settled_exact_once(storage, job.id, run_id)


# --- B. Maksymalny sukces dokładnie na granicach kontraktu -------------------------


def test_e2e_b_maximal_payload_success_without_truncation(
        settings, storage, account, monkeypatch):
    real_settings = _real_settings(settings)
    topic = _topic(storage, account, "size-b")
    job = _enqueue_durable_job(
        real_settings, storage, account, topic,
        key="size-e2e-b", max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    raw = _json(_max_payload())
    assert len(raw) == oc.MAX_CORRECT_PAYLOAD_CHARS
    # Symulowany profil: nawet payload na granicach + najgorszy zmierzony narzut
    # mieści się poniżej wybranego max_tokens (to jest sedno doboru 6000).
    simulated_output = (
        oc.ESTIMATED_MAX_PAYLOAD_TOKENS + oc.HIDDEN_OUTPUT_OVERHEAD_TOKENS
    )
    assert simulated_output < oc.RESEARCH_CARD_MAX_TOKENS

    def provider(_plan):
        return raw, Usage(
            input_tokens=16000, output_tokens=simulated_output,
            web_search_requests=1, thinking_tokens=oc.HIDDEN_OUTPUT_OVERHEAD_TOKENS,
        ), "end_turn"

    result, calls = _run_worker_once(real_settings, storage, monkeypatch, provider)
    assert result.status is WorkerIterationStatus.DONE
    assert calls == ["provider"]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.DONE
    run_id = job_row.run_id
    assert storage.get_run(run_id).status is RunStatus.SUCCESS
    assert storage.get_research_run(run_id).status.value == "COMPLETE"
    cards = storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (int(topic.id),),
    ).fetchone()[0]
    assert cards == 1
    _assert_settled_exact_once(storage, job.id, run_id)


# --- C. Kompletny JSON z jednym polem ponad limit ----------------------------------


def test_e2e_c_field_over_budget_fails_closed_with_settlement(
        settings, storage, account, monkeypatch):
    real_settings = _real_settings(settings)
    topic = _topic(storage, account, "size-c")
    job = _enqueue_durable_job(
        real_settings, storage, account, topic,
        key="size-e2e-c", max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    payload = _realistic_payload()
    payload["main_mechanism"] = "x" * (oc.MAX_MAIN_MECHANISM_CHARS + 1)

    def provider(_plan):
        return _json(payload), Usage(
            input_tokens=16000, output_tokens=2900, web_search_requests=1,
        ), "end_turn"

    result, calls = _run_worker_once(real_settings, storage, monkeypatch, provider)
    assert result.status is WorkerIterationStatus.FAILED
    assert calls == ["provider"]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    run_id = job_row.run_id
    run = storage.get_run(run_id)
    assert run.status is RunStatus.FAILED
    assert "size_contract" in (run.error or "")
    assert "main_mechanism" in (run.error or "")
    assert storage.get_research_run(run_id).status.value == "FAILED"
    cards = storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (int(topic.id),),
    ).fetchone()[0]
    assert cards == 0
    _assert_settled_exact_once(storage, job.id, run_id)
    assert next(
        t for t in storage.list_topics(account.id) if t.id == topic.id
    ).status is TopicStatus.SELECTED


# --- D. Ucięcie: stop_reason=max_tokens --------------------------------------------


def test_e2e_d_truncation_fails_closed_and_records_thinking_tokens(
        settings, storage, account, monkeypatch):
    real_settings = _real_settings(settings)
    topic = _topic(storage, account, "size-d")
    job = _enqueue_durable_job(
        real_settings, storage, account, topic,
        key="size-e2e-d", max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    truncated_prefix = _json(_realistic_payload())[:500]

    def provider(_plan):
        return truncated_prefix, Usage(
            input_tokens=16381, output_tokens=3155, web_search_requests=1,
            thinking_tokens=1900,
        ), "max_tokens"

    result, calls = _run_worker_once(real_settings, storage, monkeypatch, provider)
    assert result.status is WorkerIterationStatus.FAILED
    assert calls == ["provider"]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    run_id = job_row.run_id
    run = storage.get_run(run_id)
    assert run.status is RunStatus.FAILED
    # ResearchTruncatedError, nie parse error: parser nie czytał niepełnego JSON-a.
    assert "truncated" in (run.error or "")
    assert "size_contract" not in (run.error or "")
    assert "json_syntax" not in (run.error or "")
    assert storage.get_research_run(run_id).status.value == "FAILED"
    cards = storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (int(topic.id),),
    ).fetchone()[0]
    assert cards == 0
    _assert_settled_exact_once(storage, job.id, run_id)

    diag = diagnostics_dir(real_settings.data_dir, run_id) / "SINGLE_raw_response.txt"
    assert diag.exists()
    content = diag.read_text(encoding="utf-8")
    assert "thinking_tokens: 1900" in content
    assert "stop_reason: max_tokens" in content


# --- E. Kontrakty typów ------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "expected_error_marker"),
    [
        pytest.param(
            lambda p: p["sources"][0].__setitem__("supports_claim", True),
            "supports_claim", id="supports-claim-boolean"),
        pytest.param(
            lambda p: p.__setitem__("citable_numbers", [42, "3 percent"]),
            "citable_numbers", id="citable-raw-number"),
    ],
)
def test_e2e_e_type_contract_violations_fail_closed(
        settings, storage, account, monkeypatch, mutate, expected_error_marker):
    real_settings = _real_settings(settings)
    topic = _topic(storage, account, f"size-e-{expected_error_marker}")
    job = _enqueue_durable_job(
        real_settings, storage, account, topic,
        key=f"size-e2e-e-{expected_error_marker}",
        max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    payload = _realistic_payload()
    mutate(payload)

    def provider(_plan):
        return json.dumps(payload, separators=(",", ":")), Usage(
            input_tokens=16000, output_tokens=2700, web_search_requests=1,
        ), "end_turn"

    result, calls = _run_worker_once(real_settings, storage, monkeypatch, provider)
    assert result.status is WorkerIterationStatus.FAILED
    assert calls == ["provider"]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    run_id = job_row.run_id
    run = storage.get_run(run_id)
    assert run.status is RunStatus.FAILED
    assert expected_error_marker in (run.error or "")
    cards = storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (int(topic.id),),
    ).fetchone()[0]
    assert cards == 0
    _assert_settled_exact_once(storage, job.id, run_id)
