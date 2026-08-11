"""P2-1: production topic/research roots share one frozen Anthropic contract.

All tests use temporary SQLite databases and fake SDK objects.  They cannot
reach a network, a real provider account, publication, or a billable boundary.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentType,
)
from app.core.clock import FixedClock
from app.llm.anthropic_controlled_adapter import (
    ControlledAdapterError,
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
)
from app.llm.anthropic_provider_contract import (
    CANONICAL_ANTHROPIC_REQUEST_CONTRACT,
)
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.base import LLMProviderError
from app.model_routing import LogicalModelRole
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import (
    ARTICLE_RESEARCH_PROVIDER_INTENT_KIND,
    TOPIC_GENERATION_PROVIDER_INTENT_KIND,
    JobDispatcher,
)
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import ResearchUnknownProviderError
from tests.test_e3_evidence_research import (
    NOW,
    _approve as approve_research,
    _evidence_payload,
    _open_flags as open_research_flags,
    _pricing_profile as research_pricing_profile,
    _real_settings as research_real_settings,
    _topic,
)
from tests.test_prec5_e3_content_lineage import (
    CLAIM,
    _card_id,
    _job as research_job,
    _proceed_response,
    _seed_corpus,
)
from tests.test_topic_generation_runtime import (
    NOW as TOPIC_NOW,
    _prepare as prepare_topic,
    _response as topic_response,
)
from tests.test_topics_anthropic_client import _configure_durable_topic_attempt


class _Messages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeAnthropicModule:
    class APIError(Exception):
        pass

    def __init__(self, response):
        self.messages = _Messages(response)
        self.sdk_calls: list[dict] = []

    def Anthropic(self, **kwargs):
        self.sdk_calls.append(kwargs)
        return SimpleNamespace(messages=self.messages)


def _usage(*, input_tokens=100, output_tokens=80):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=0),
        output_tokens_details=SimpleNamespace(thinking_tokens=0),
        inference_geo="global",
        service_tier="standard",
    )


@pytest.mark.parametrize(
    "contract",
    [
        None,
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, provider="OTHER"),
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, inference_geo="us"),
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, service_tier="auto"),
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, fallback_policy="ALLOWED"),
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, application_retries=1),
        replace(CANONICAL_ANTHROPIC_REQUEST_CONTRACT, sdk_retries=1),
    ],
)
def test_incomplete_or_drifted_contract_stops_before_sdk_and_final_caller(contract):
    sdk_calls = 0
    caller_calls = 0

    def sdk_factory(**_kwargs):
        nonlocal sdk_calls
        sdk_calls += 1
        return object()

    def caller(_client, _request):
        nonlocal caller_calls
        caller_calls += 1
        raise AssertionError("final caller must not run")

    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "offline-key",
        sdk_factory=sdk_factory,
        caller=caller,
    )
    with pytest.raises(ControlledAdapterError):
        adapter.execute(ControlledProviderRequest(
            technical_model_id="model",
            system_prompt="system",
            user_prompt="prompt",
            max_output_tokens=10,
            timeout_seconds=1,
            provider_contract=contract,
        ))
    assert sdk_calls == 0
    assert caller_calls == 0


def test_topic_returned_model_mismatch_is_not_accepted(monkeypatch, account):
    response = SimpleNamespace(
        model="other-model",
        id="fake-topic-mismatch",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=topic_response(0.95))],
        usage=_usage(),
    )
    fake_module = _FakeAnthropicModule(response)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_module)
    client = _configure_durable_topic_attempt(
        AnthropicLLMClient("offline-key", "topics-model")
    )

    with pytest.raises(LLMProviderError) as caught:
        client.generate_and_score_topics(account, 1)
    assert "RETURNED_MODEL_MISMATCH" in str(caught.value)
    assert caught.value.usage is not None
    assert len(fake_module.messages.calls) == 1


def test_research_returned_model_mismatch_is_not_accepted():
    response = SimpleNamespace(
        model="other-model",
        id="fake-research-mismatch",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="{}")],
        usage=_usage(),
    )
    fake_module = _FakeAnthropicModule(response)
    client = AnthropicResearchClient("offline-key", "research-model")
    client.requires_durable_provider_context = False

    with pytest.raises(ResearchUnknownProviderError) as caught:
        client._call_anthropic(
            client._new_anthropic_client(fake_module),
            "prompt",
            tools=None,
            max_tokens=100,
        )
    assert "RETURNED_MODEL_MISMATCH" in str(caught.value)
    assert caught.value.usage is not None
    assert len(fake_module.messages.calls) == 1


def test_topic_production_composition_uses_binding_and_exact_request_contract(
    monkeypatch, settings, storage, account,
):
    real, intent, job = prepare_topic(
        settings, storage, account, key="p2-contract", count=1,
    )
    response = SimpleNamespace(
        model=intent.model,
        id="fake-topic-message",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=topic_response(0.95))],
        usage=_usage(),
    )
    fake_module = _FakeAnthropicModule(response)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_module)

    policy = PolicyEngine(real, storage, FixedClock(TOPIC_NOW))
    dispatcher = JobDispatcher(
        settings=real,
        storage=storage,
        policy=policy,
        clock=FixedClock(TOPIC_NOW),
    )
    worker = Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner="p2-topic-worker",
        lease_seconds=120,
        heartbeat_interval_seconds=5,
        heartbeat_startup_timeout_seconds=5,
        heartbeat_shutdown_timeout_seconds=5,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=FixedClock(TOPIC_NOW),
    )

    assert worker.run_once().status is WorkerIterationStatus.DONE
    binding = storage.get_frozen_model_binding(
        intent_kind=TOPIC_GENERATION_PROVIDER_INTENT_KIND,
        intent_id=job.id,
    )
    assert binding is not None
    assert binding.role is LogicalModelRole.TOPIC_GENERATION
    assert binding.provider == "ANTHROPIC"
    assert binding.technical_model_id == intent.model
    assert binding.fallback_policy == "FORBIDDEN"
    assert fake_module.sdk_calls == [{
        "api_key": "test-only-key",
        "max_retries": 0,
        "timeout": float(intent.timeout_seconds),
    }]
    assert len(fake_module.messages.calls) == 1
    request = fake_module.messages.calls[0]
    assert request["model"] == binding.technical_model_id
    assert request["inference_geo"] == "global"
    assert request["service_tier"] == "standard_only"
    assert request["extra_headers"] == {"Idempotency-Key": f"{job.id}:topics:1"}
    assert "tools" not in request


def test_article_research_smoke_persists_lineage_and_prepares_content(
    monkeypatch, settings, storage, account,
):
    real = research_real_settings(settings)
    profile = research_pricing_profile(real)
    topic = _topic(storage, account, "p2-contract")
    retrievals = _seed_corpus(storage, account)
    payload, intent = _evidence_payload(
        real, account, topic, retrievals, cap=1.0, pricing_profile=profile,
    )
    job = storage.enqueue_job(research_job(account, topic, "p2-contract", payload))
    open_research_flags(storage)
    approve_research(storage, job.id, account)

    response = SimpleNamespace(
        model=intent.model,
        id="fake-research-message",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=_proceed_response())],
        usage=_usage(input_tokens=240, output_tokens=180),
    )
    fake_module = _FakeAnthropicModule(response)
    monkeypatch.setattr(
        "app.research.anthropic_client.AnthropicResearchClient._import_anthropic",
        lambda _self: fake_module,
    )

    # This duplicates the production JobDispatcher/Worker composition while the
    # final provider boundary remains a deterministic in-memory SDK fake.
    from tests.test_e3_evidence_research import _worker

    result = _worker(real, storage, lease_owner="p2-research-worker").run_once()
    assert result.status is WorkerIterationStatus.DONE
    binding = storage.get_frozen_model_binding(
        intent_kind=ARTICLE_RESEARCH_PROVIDER_INTENT_KIND,
        intent_id=job.id,
    )
    assert binding is not None
    assert binding.role is LogicalModelRole.ARTICLE_RESEARCH
    assert binding.provider == "ANTHROPIC"
    assert binding.technical_model_id == intent.model
    assert binding.fallback_policy == "FORBIDDEN"
    assert fake_module.sdk_calls == [{
        "api_key": "test-only-key",
        "max_retries": 0,
        "timeout": float(intent.timeout_seconds),
    }]
    assert len(fake_module.messages.calls) == 1
    request = fake_module.messages.calls[0]
    assert request["model"] == binding.technical_model_id
    assert request["inference_geo"] == "global"
    assert request["service_tier"] == "standard_only"
    assert request["extra_headers"] == {"Idempotency-Key": f"{job.id}:research:1"}
    assert "tools" not in request

    card_id = int(_card_id(storage, job))
    card = storage.get_research_card(card_id)
    assert card.publication_recommendation.value == "PROCEED"
    lineage = storage.conn.execute(
        "SELECT * FROM evidence_source_lineage WHERE research_card_id=?",
        (card_id,),
    ).fetchall()
    assert len(lineage) == 3
    assert {row["research_job_id"] for row in lineage} == {job.id}

    prepared = storage.prepare_content_job(ContentPreparationRequest(
        job_id="p2-content-from-research",
        idempotency_key="p2-content-from-research",
        account_id=account.id,
        research_card_id=card_id,
        content_type=ContentType.ARTICLE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    ), clock=FixedClock(NOW))
    assert len(prepared.frozen_input.evidence_items) == 3
    assert {item.claim_text for item in prepared.frozen_input.evidence_items} == {CLAIM}
