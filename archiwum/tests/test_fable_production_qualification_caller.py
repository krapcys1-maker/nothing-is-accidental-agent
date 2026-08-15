"""Offline contract tests for the production ARTICLE_WRITER qualification caller.

Every transport and SDK object in this file is fake.  Every database is new in
``tmp_path``.  No test reads a secret or opens ``data/agent.db``.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.llm.anthropic_controlled_adapter import ControlledAnthropicAdapter
from app.llm.anthropic_provider_contract import (
    FABLE_5_MODEL_ID,
    OPUS_5_MODEL_ID,
)
from app.model_routing import LogicalModelRole
from app.model_routing.catalogue import OPUS_5
from app.model_routing.production_qualification import (
    OPUS_PRODUCTION_QUALIFICATION_CONTRACT,
    OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON,
    OPUS_QUALIFICATION_PROMPT,
    OPUS_QUALIFICATION_PROMPT_SHA256,
    OPUS_QUALIFICATION_PROMPT_VERSION,
    QUALIFICATION_EXPECTED_RESPONSE_JSON,
    QUALIFICATION_PROMPT,
    QUALIFICATION_PROMPT_SHA256,
    QUALIFICATION_PROMPT_VERSION,
    QUALIFICATION_TIMEOUT_SECONDS,
    ProductionOpusQualificationCaller,
    execute_opus_production_qualification,
    qualification_prompt_bytes,
    qualification_prompt_fingerprint,
    validate_qualification_response,
)
from app.model_routing.qualification import (
    ControlledQualificationError,
    QualificationApproval,
)
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage


NOW = datetime.fromisoformat("2026-08-10T17:05:00.000000+00:00")
APPROVED_AT = "2026-08-10T17:00:00.000000+00:00"
EXPIRES_AT = "2026-08-11T17:00:00.000000+00:00"
APPROVAL_REF = "opus5-qualification-approval-test-001"
REQUEST_ID = "opus5-qualification-request-test-001"


class FakeMessages:
    def __init__(
        self,
        *,
        text: str = OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON,
        returned_model_id: str = OPUS_5_MODEL_ID,
        input_tokens: int = 900,
        output_tokens: int = 120,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        web_search_requests: int = 0,
        inference_geo: str | None = "global",
        service_tier: str | None = "standard",
        stop_reason: str | None = "end_turn",
        error: BaseException | None = None,
    ) -> None:
        self.text = text
        self.returned_model_id = returned_model_id
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.web_search_requests = web_search_requests
        self.inference_geo = inference_geo
        self.service_tier = service_tier
        self.stop_reason = stop_reason
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        usage = SimpleNamespace(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_input_tokens=self.cache_read_tokens,
            cache_creation_input_tokens=self.cache_write_tokens,
            server_tool_use=(
                None
                if self.web_search_requests == 0
                else SimpleNamespace(web_search_requests=self.web_search_requests)
            ),
            inference_geo=self.inference_geo,
            service_tier=self.service_tier,
        )
        return SimpleNamespace(
            model=self.returned_model_id,
            content=(SimpleNamespace(type="text", text=self.text),),
            usage=usage,
            stop_reason=self.stop_reason,
            id="fake-qualification-response",
        )


class FakeSdkFactory:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(messages=self.messages)


def _open_storage(path: Path) -> SqliteStorage:
    initialize_database(path)
    return SqliteStorage.open(path)


def _seed_exact_authority(
    storage: SqliteStorage,
    *,
    cap_usd: str = "0.120960",
    approved_at: str = APPROVED_AT,
    expires_at: str = EXPIRES_AT,
) -> QualificationApproval:
    model = storage.register_owner_verified_catalogue(
        entries=(OPUS_5,),
        verified_by="owner:krapcys1-maker",
        now=NOW,
    )[0]
    approval = QualificationApproval(
        approval_ref=APPROVAL_REF,
        request_id=REQUEST_ID,
        logical_role=LogicalModelRole.ARTICLE_WRITER,
        model_registry_id=model.registry_id,
        provider="ANTHROPIC",
        technical_model_id=OPUS_5_MODEL_ID,
        pricing_ref=OPUS_5.default_pricing_ref,
        max_input_tokens=13952,
        max_output_tokens=2048,
        cap_usd=Decimal(cap_usd),
        approved_by="owner:krapcys1-maker",
        approved_at=approved_at,
        expires_at=expires_at,
    )
    storage.record_model_qualification_approval(approval, now=NOW)
    return approval


@pytest.fixture
def exact_authority(tmp_path: Path):
    path = tmp_path / "opus-production-qualification.db"
    storage = _open_storage(path)
    approval = _seed_exact_authority(storage)
    try:
        yield storage, path, approval
    finally:
        storage.close()


def _execute(storage, approval, messages: FakeMessages):
    factory = FakeSdkFactory(messages)
    outcome = execute_opus_production_qualification(
        storage,
        approval,
        api_key_provider=lambda: "fake-secret",
        sdk_factory=factory,
        now=NOW,
    )
    return outcome, factory


def test_historical_fable_prompt_remains_frozen_and_opus_has_new_identity():
    assert QUALIFICATION_PROMPT_VERSION == "fable_production_qualification_prompt_v1"
    assert QUALIFICATION_PROMPT_SHA256 == (
        "adb5893381a99c9007740533b6f8b6e10d1a5b4604808134cba4cf949bfbacc8"
    )
    assert qualification_prompt_fingerprint() == QUALIFICATION_PROMPT_SHA256
    assert qualification_prompt_bytes() == QUALIFICATION_PROMPT.encode("utf-8")
    assert len(qualification_prompt_bytes()) == 372
    assert OPUS_QUALIFICATION_PROMPT_VERSION == "opus_production_qualification_prompt_v1"
    assert OPUS_QUALIFICATION_PROMPT_SHA256 != QUALIFICATION_PROMPT_SHA256
    assert OPUS_QUALIFICATION_PROMPT_SHA256 == __import__("hashlib").sha256(
        OPUS_QUALIFICATION_PROMPT.encode("utf-8")
    ).hexdigest()


def test_validator_accepts_only_the_exact_typed_challenge_object():
    reordered = (
        '{"structured_response":true,'
        '"contract_version":"opus_production_qualification_prompt_v1",'
        '"challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1"}'
    )
    assert validate_qualification_response(
        f"  {reordered}\n", stop_reason="end_turn",
        contract=OPUS_PRODUCTION_QUALIFICATION_CONTRACT,
    ) is True


@pytest.mark.parametrize(
    ("text", "stop_reason"),
    [
        ("", "end_turn"),
        ("PASS", "end_turn"),
        ("```json\n" + OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON + "\n```", "end_turn"),
        ("{", "end_turn"),
        ('{"challenge":"wrong","contract_version":"opus_production_qualification_prompt_v1","structured_response":true}', "end_turn"),
        ('{"challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1","contract_version":"opus_production_qualification_prompt_v1"}', "end_turn"),
        ('{"challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1","contract_version":"opus_production_qualification_prompt_v1","structured_response":false}', "end_turn"),
        ('{"challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1","contract_version":"opus_production_qualification_prompt_v1","structured_response":1}', "end_turn"),
        (OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON[:-1] + ',"extra":1}', "end_turn"),
        ('{"challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1","challenge":"NIA-OPUS-QUALIFICATION-CHALLENGE-V1","contract_version":"opus_production_qualification_prompt_v1","structured_response":true}', "end_turn"),
        (OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, "refusal"),
        (OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, "max_tokens"),
    ],
)
def test_validator_rejects_malformed_ambiguous_refused_or_truncated_response(
    text,
    stop_reason,
):
    assert validate_qualification_response(
        text,
        stop_reason=stop_reason,
        contract=OPUS_PRODUCTION_QUALIFICATION_CONTRACT,
    ) is False


def test_production_caller_builds_exact_frozen_request(exact_authority):
    _, _, approval = exact_authority
    messages = FakeMessages()
    factory = FakeSdkFactory(messages)
    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "fake-secret",
        sdk_factory=factory,
    )
    caller = ProductionOpusQualificationCaller(adapter)

    response = caller(approval)

    assert caller.caller_calls == len(factory.calls) == len(messages.calls) == 1
    assert factory.calls[0]["max_retries"] == 0
    assert factory.calls[0]["timeout"] == QUALIFICATION_TIMEOUT_SECONDS
    request = messages.calls[0]
    assert request["model"] == approval.technical_model_id
    assert request["max_tokens"] == approval.max_output_tokens == 2048
    assert request["system"] == ""
    assert request["messages"] == [{"role": "user", "content": OPUS_QUALIFICATION_PROMPT}]
    assert request["inference_geo"] == "global"
    assert request["service_tier"] == "standard_only"
    for forbidden in ("tools", "cache_control", "metadata", "betas"):
        assert forbidden not in request
    assert response.structured_response_ok is True
    assert response.returned_model_id == OPUS_5_MODEL_ID
    assert response.usage.inference_geo == "global"
    assert response.usage.service_tier == "standard"


def test_supported_root_happy_path_preserves_policy_and_does_not_activate(
    exact_authority,
):
    storage, _, approval = exact_authority
    policy_before = dict(storage.conn.execute(
        "SELECT * FROM model_role_policies WHERE role='ARTICLE_WRITER'"
    ).fetchone())

    outcome, factory = _execute(storage, approval, FakeMessages())

    assert outcome.outcome == "PASS"
    assert outcome.failure_kind is None
    assert outcome.cost_usd == Decimal("0.007500")
    assert outcome.usage is not None
    assert outcome.usage.input_tokens == 900
    assert outcome.usage.output_tokens == 120
    assert len(factory.calls) == 1
    assert storage.conn.execute(
        "SELECT consumed_at IS NOT NULL FROM model_qualification_approvals"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT outcome FROM model_qualification_runs"
    ).fetchone()[0] == "PASS"
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_qualification_results WHERE state='PASS'"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_capability_declarations "
        "WHERE verification_state='VERIFIED'"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_role_activations"
    ).fetchone()[0] == 0
    policy_after = dict(storage.conn.execute(
        "SELECT * FROM model_role_policies WHERE role='ARTICLE_WRITER'"
    ).fetchone())
    assert policy_after == policy_before
    assert policy_after["capability_verification_state"] == "UNVERIFIED"
    assert policy_after["pricing_verification_state"] == "UNVERIFIED"


@pytest.mark.parametrize(
    ("messages", "outcome", "failure_kind"),
    [
        (FakeMessages(text="{"), "FAIL", "STRUCTURED_RESPONSE_REJECTED"),
        (FakeMessages(text=""), "FAIL", "STRUCTURED_RESPONSE_REJECTED"),
        (FakeMessages(text="PASS"), "FAIL", "STRUCTURED_RESPONSE_REJECTED"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, stop_reason="max_tokens"), "FAIL", "STRUCTURED_RESPONSE_REJECTED"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, stop_reason="refusal"), "FAIL", "PROVIDER_REFUSAL"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, returned_model_id=FABLE_5_MODEL_ID), "NEEDS_VERIFICATION", "RETURNED_MODEL_MISMATCH"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, inference_geo="us"), "NEEDS_VERIFICATION", "RETURNED_INFERENCE_GEO_MISMATCH"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, service_tier="priority"), "NEEDS_VERIFICATION", "RETURNED_SERVICE_TIER_MISMATCH"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, input_tokens=13953), "NEEDS_VERIFICATION", "INPUT_CEILING_EXCEEDED"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, output_tokens=2049), "NEEDS_VERIFICATION", "OUTPUT_CEILING_EXCEEDED"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, cache_read_tokens=1), "NEEDS_VERIFICATION", "UNEXPECTED_CACHE_USAGE"),
        (FakeMessages(text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON, web_search_requests=1), "NEEDS_VERIFICATION", "UNEXPECTED_WEB_SEARCH_USAGE"),
    ],
)
def test_response_and_usage_failures_terminalize_once(
    tmp_path,
    messages,
    outcome,
    failure_kind,
):
    storage = _open_storage(tmp_path / f"{failure_kind}.db")
    try:
        approval = _seed_exact_authority(storage)
        result, factory = _execute(storage, approval, messages)
        assert len(factory.calls) == len(messages.calls) == 1
        assert result.outcome == outcome
        assert result.failure_kind == failure_kind
        row = storage.conn.execute(
            "SELECT outcome,failure_kind,input_tokens,output_tokens,cost_usd "
            "FROM model_qualification_runs"
        ).fetchone()
        assert row["outcome"] == outcome
        assert row["failure_kind"] == failure_kind
        assert row["input_tokens"] == messages.input_tokens
        assert row["output_tokens"] == messages.output_tokens
        assert row["cost_usd"] is not None
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM model_role_activations"
        ).fetchone()[0] == 0
        expected_results = 0 if outcome == "NEEDS_VERIFICATION" else 1
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM model_qualification_results"
        ).fetchone()[0] == expected_results
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM model_capability_declarations"
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_cost_over_cap_is_settled_from_frozen_usage(tmp_path):
    storage = _open_storage(tmp_path / "over-cap.db")
    try:
        approval = _seed_exact_authority(storage, cap_usd="0.001000")
        outcome, _ = _execute(storage, approval, FakeMessages())
        assert outcome.outcome == "NEEDS_VERIFICATION"
        assert outcome.failure_kind == "COST_CAP_EXCEEDED"
        assert outcome.cost_usd == Decimal("0.007500")
        row = storage.conn.execute(
            "SELECT input_tokens,output_tokens,cost_usd FROM model_qualification_runs"
        ).fetchone()
        assert tuple(row) == (900, 120, "0.007500")
    finally:
        storage.close()


def test_provider_exception_preserves_unknown_terminal_state_without_retry(tmp_path):
    storage = _open_storage(tmp_path / "provider-exception.db")
    try:
        approval = _seed_exact_authority(storage)
        messages = FakeMessages(error=TimeoutError("fake timeout"))
        factory = FakeSdkFactory(messages)
        with pytest.raises(TimeoutError, match="fake timeout"):
            execute_opus_production_qualification(
                storage,
                approval,
                api_key_provider=lambda: "fake-secret",
                sdk_factory=factory,
                now=NOW,
            )
        assert len(factory.calls) == len(messages.calls) == 1
        row = storage.conn.execute(
            "SELECT outcome,failure_kind,input_tokens,output_tokens,cost_usd "
            "FROM model_qualification_runs"
        ).fetchone()
        assert tuple(row) == (
            "NEEDS_VERIFICATION",
            "CALLER_RESULT_UNKNOWN",
            None,
            None,
            None,
        )
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM model_qualification_results"
        ).fetchone()[0] == 0
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM model_capability_declarations"
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_missing_or_expired_durable_authority_never_reaches_transport(tmp_path):
    missing = _open_storage(tmp_path / "missing.db")
    expired = _open_storage(tmp_path / "expired.db")
    try:
        model = missing.register_owner_verified_catalogue(
            entries=(OPUS_5,), verified_by="owner-test", now=NOW
        )[0]
        absent = QualificationApproval(
            approval_ref=APPROVAL_REF,
            request_id=REQUEST_ID,
            logical_role=LogicalModelRole.ARTICLE_WRITER,
            model_registry_id=model.registry_id,
            provider="ANTHROPIC",
            technical_model_id=OPUS_5_MODEL_ID,
            pricing_ref=OPUS_5.default_pricing_ref,
            max_input_tokens=13952,
            max_output_tokens=2048,
            cap_usd=Decimal("0.120960"),
            approved_by="owner-test",
            approved_at=APPROVED_AT,
            expires_at=EXPIRES_AT,
        )
        expired_approval = _seed_exact_authority(
            expired,
            approved_at="2026-08-10T00:00:00.000000+00:00",
            expires_at="2026-08-10T16:00:00.000000+00:00",
        )
        for storage, approval in ((missing, absent), (expired, expired_approval)):
            messages = FakeMessages()
            factory = FakeSdkFactory(messages)
            with pytest.raises(ControlledQualificationError):
                execute_opus_production_qualification(
                    storage,
                    approval,
                    api_key_provider=lambda: "fake-secret",
                    sdk_factory=factory,
                    now=NOW,
                )
            assert len(factory.calls) == len(messages.calls) == 0
            assert storage.conn.execute(
                "SELECT COUNT(*) FROM model_qualification_runs"
            ).fetchone()[0] == 0
    finally:
        missing.close()
        expired.close()


@pytest.mark.parametrize(
    "change",
    [
        {"technical_model_id": FABLE_5_MODEL_ID},
        {"pricing_ref": "another-price"},
        {"request_id": "another-request"},
    ],
)
def test_changed_authority_identity_is_rejected_before_transport(
    exact_authority,
    change,
):
    storage, _, approval = exact_authority
    changed = replace(approval, **change)
    messages = FakeMessages()
    factory = FakeSdkFactory(messages)
    with pytest.raises(ControlledQualificationError):
        execute_opus_production_qualification(
            storage,
            changed,
            api_key_provider=lambda: "fake-secret",
            sdk_factory=factory,
            now=NOW,
        )
    assert len(factory.calls) == len(messages.calls) == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_qualification_runs"
    ).fetchone()[0] == 0


def test_consumed_approval_and_restart_never_make_a_second_call(tmp_path):
    path = tmp_path / "restart.db"
    storage = _open_storage(path)
    approval = _seed_exact_authority(storage)
    first_messages = FakeMessages()
    first, first_factory = _execute(storage, approval, first_messages)
    assert first.outcome == "PASS"
    assert len(first_factory.calls) == len(first_messages.calls) == 1
    storage.close()

    reopened = SqliteStorage.open(path)
    try:
        second_messages = FakeMessages()
        second_factory = FakeSdkFactory(second_messages)
        with pytest.raises(ControlledQualificationError):
            execute_opus_production_qualification(
                reopened,
                approval,
                api_key_provider=lambda: "fake-secret",
                sdk_factory=second_factory,
                now=NOW,
            )
        assert len(second_factory.calls) == len(second_messages.calls) == 0
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM model_qualification_runs"
        ).fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            reopened.conn.execute(
                "UPDATE model_qualification_runs SET outcome='IN_FLIGHT' "
                "WHERE request_id=?",
                (REQUEST_ID,),
            )
    finally:
        if reopened.conn.in_transaction:
            reopened.conn.rollback()
        reopened.close()
