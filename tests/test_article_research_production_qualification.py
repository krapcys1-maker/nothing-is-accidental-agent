"""Offline tests for the production ARTICLE_RESEARCH qualification root."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.llm.anthropic_controlled_adapter import ControlledProviderRawResponse
from app.model_routing.catalogue import OPUS_5
from app.model_routing.contracts import LogicalModelRole
from app.model_routing.production_qualification import (
    OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT,
    execute_opus_article_research_production_qualification,
)
from app.model_routing.qualification import QualificationApproval
from app.model_routing.role_activation import (
    ExactRoleActivationRequest,
    activate_and_bind_exact_role,
)
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage


NOW = datetime.fromisoformat("2026-08-12T12:00:00+00:00")


def test_research_qualification_proves_32k_structured_search_and_activates(tmp_path: Path):
    path = tmp_path / "research-qualification.db"
    initialize_database(path)
    storage = SqliteStorage.open(path)
    calls: list[object] = []
    try:
        model = storage.register_owner_verified_catalogue(
            entries=(OPUS_5,), verified_by="owner:test", now=NOW,
        )[0]
        approval = QualificationApproval(
            approval_ref="research-qualification-approval",
            request_id="research-qualification-request",
            logical_role=LogicalModelRole.ARTICLE_RESEARCH,
            model_registry_id=model.registry_id,
            provider="ANTHROPIC",
            technical_model_id="claude-opus-5",
            pricing_ref=OPUS_5.default_pricing_ref,
            max_input_tokens=23_808,
            max_output_tokens=8_192,
            cap_usd=Decimal("1.000000"),
            approved_by="owner:test",
            approved_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(minutes=30)).isoformat(),
            require_source_discovery=True,
        )
        storage.record_model_qualification_approval(approval, now=NOW)

        def caller(_client, request):
            calls.append(request)
            return ControlledProviderRawResponse(
                returned_model_id="claude-opus-5",
                text=OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT.expected_response_json,
                input_tokens=200,
                output_tokens=80,
                cache_read_tokens=0,
                cache_write_tokens=0,
                web_search_requests=1,
                stop_reason="end_turn",
                provider_request_id="provider-research-qualification",
                inference_geo="global",
                service_tier="standard",
                structured_web_search_results=1,
            )

        outcome = execute_opus_article_research_production_qualification(
            storage,
            approval,
            api_key_provider=lambda: "fake-secret",
            sdk_factory=lambda **_kwargs: SimpleNamespace(),
            technical_caller=caller,
            now=NOW,
        )
        assert outcome.outcome == "PASS"
        assert outcome.source_discovery_ok is True
        assert len(calls) == 1
        request = calls[0]
        assert request.max_output_tokens == 8_192
        assert request.tools == ({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 1,
        },)

        capability = storage.conn.execute(
            "SELECT * FROM model_capability_declarations "
            "WHERE capability_ref='controlled-caps-research-qualification-request'"
        ).fetchone()
        assert capability["max_context_tokens"] == 32_000
        assert capability["max_output_tokens"] == 8_192
        assert capability["source_discovery"] == 1

        binding = activate_and_bind_exact_role(
            storage,
            ExactRoleActivationRequest(
                role=LogicalModelRole.ARTICLE_RESEARCH,
                intent_kind="article_research_provider",
                intent_id="research-qualification-activation-test",
            ),
            now=NOW,
        )
        assert binding.provider == "ANTHROPIC"
        assert binding.technical_model_id == "claude-opus-5"
        assert binding.fallback_policy == "FORBIDDEN"
    finally:
        storage.close()


def test_research_qualification_rejects_usage_without_structured_search_result(
    tmp_path: Path,
):
    path = tmp_path / "research-qualification-no-result.db"
    initialize_database(path)
    storage = SqliteStorage.open(path)
    try:
        model = storage.register_owner_verified_catalogue(
            entries=(OPUS_5,), verified_by="owner:test", now=NOW,
        )[0]
        approval = QualificationApproval(
            approval_ref="research-no-result-approval",
            request_id="research-no-result-request",
            logical_role=LogicalModelRole.ARTICLE_RESEARCH,
            model_registry_id=model.registry_id,
            provider="ANTHROPIC",
            technical_model_id="claude-opus-5",
            pricing_ref=OPUS_5.default_pricing_ref,
            max_input_tokens=23_808,
            max_output_tokens=8_192,
            cap_usd=Decimal("1.000000"),
            approved_by="owner:test",
            approved_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(minutes=30)).isoformat(),
            require_source_discovery=True,
        )
        storage.record_model_qualification_approval(approval, now=NOW)
        outcome = execute_opus_article_research_production_qualification(
            storage,
            approval,
            api_key_provider=lambda: "fake-secret",
            sdk_factory=lambda **_kwargs: SimpleNamespace(),
            technical_caller=lambda _client, _request: ControlledProviderRawResponse(
                returned_model_id="claude-opus-5",
                text=OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT.expected_response_json,
                input_tokens=200,
                output_tokens=80,
                cache_read_tokens=0,
                cache_write_tokens=0,
                web_search_requests=1,
                stop_reason="end_turn",
                provider_request_id="provider-no-result",
                inference_geo="global",
                service_tier="standard",
                structured_web_search_results=0,
            ),
            now=NOW,
        )
        assert outcome.outcome == "FAIL"
        assert outcome.failure_kind == "SOURCE_DISCOVERY_CAPABILITY_REJECTED"
        assert storage.conn.execute(
            "SELECT count(*) FROM model_capability_declarations"
        ).fetchone()[0] == 0
    finally:
        storage.close()
