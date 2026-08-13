"""C5 provider contract freeze: every case is fake, offline and temp-DB only."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.content.contracts import (
    WriterCallMode,
    WriterFailure,
    WriterFailureKind,
    WriterUsage,
)
from app.content.foundation import ContentStatus, ContentType, canonical_json, sha256_text
from app.content.provider_roles import RoleProviderResponse, RoleUsage, evaluate_role_response
from app.content.writer import ProviderReadyContentWriter
from app.llm.anthropic_controlled_adapter import (
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
)
from app.llm.anthropic_provider_contract import (
    ARTICLE_WRITER_INFERENCE_CONFIG,
    FABLE_5_MODEL_ID,
    FableRetentionAcceptance,
    RETENTION_SCOPE_QUALIFICATION,
)
from app.model_routing import LogicalModelRole, ModelFamily
from app.model_routing.catalogue import FABLE_5
from app.model_routing.qualification import (
    ControlledQualificationError,
    QualificationProbeResponse,
    QualificationProbeUsage,
)
from app.model_routing.role_bootstrap import owner_approved_role_policy
from app.ports.storage import ContentFoundationError
from app.storage.db import (
    ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,
    VERIFIED_CATALOGUE_SCHEMA_VERSION,
    database_schema_versions,
    connect,
    initialize_database,
    migrate_0029_to_0030,
)
from app.storage.repositories import SqliteStorage
from tests.controlled_provider_fixtures import approve_content_provider_execution
from tests.test_content_pipeline_c3 import ScriptedCaller, run_provider
from tests.test_prec5_controlled_provider_provenance import _prepare, _run
from tests.test_prec5_verified_catalogue_live_root import (
    APPROVED_AT,
    EXPIRES_AT,
    CatalogueFakeWriter,
    CountingQualificationCaller,
    _activate_article_roles,
    _approval,
    _entry_for,
    _register,
    _seeded,
)

NOW = "2026-08-10T12:00:00.000000+00:00"


@pytest.fixture
def contract_storage(tmp_path: Path):
    path = tmp_path / "provider-contract.db"
    initialize_database(path)
    storage = SqliteStorage.open(path)
    try:
        yield storage
    finally:
        storage.close()


@pytest.fixture
def fable_contract_storage(tmp_path: Path):
    """Historical 0030 floor used only to reproduce frozen Fable evidence."""
    path = tmp_path / "historical-fable-contract.db"
    initialize_database(path, through=ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION)
    storage = SqliteStorage(connect(path))
    try:
        yield storage
    finally:
        storage.close()


class CapturingMessages:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        usage = SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            server_tool_use=None,
            inference_geo="global",
            service_tier="standard",
        )
        return SimpleNamespace(
            model=self.model_id,
            content=(SimpleNamespace(type="text", text="{}"),),
            usage=usage,
            stop_reason="end_turn",
            id="fake-sdk-response",
        )


@pytest.mark.parametrize("model_id", ["claude-opus-5", "claude-fable-5"])
def test_controlled_adapter_sends_explicit_global_and_standard_only(model_id):
    messages = CapturingMessages(model_id)
    client = SimpleNamespace(messages=messages)
    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "fake-secret",
        sdk_factory=lambda **_kwargs: client,
    )
    raw = adapter.execute(ControlledProviderRequest(
        technical_model_id=model_id,
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=128,
        timeout_seconds=5.0,
        inference_config=ARTICLE_WRITER_INFERENCE_CONFIG,
    ))
    assert adapter.caller_calls == len(messages.calls) == 1
    assert messages.calls[0]["inference_geo"] == "global"
    assert messages.calls[0]["service_tier"] == "standard_only"
    assert raw.inference_geo == "global"
    assert raw.service_tier == "standard"


def test_workspace_and_environment_defaults_cannot_override_frozen_request(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_INFERENCE_GEO", "us")
    monkeypatch.setenv("ANTHROPIC_SERVICE_TIER", "auto")
    messages = CapturingMessages("claude-opus-5")
    client = SimpleNamespace(
        messages=messages,
        default_inference_geo="us",
        priority_available=True,
    )
    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "fake-secret",
        sdk_factory=lambda **_kwargs: client,
    )

    adapter.execute(ControlledProviderRequest(
        technical_model_id="claude-opus-5",
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=128,
        timeout_seconds=5.0,
        inference_config=ARTICLE_WRITER_INFERENCE_CONFIG,
    ))

    assert len(messages.calls) == 1
    assert messages.calls[0]["inference_geo"] == "global"
    assert messages.calls[0]["service_tier"] == "standard_only"


def test_content_anthropic_root_cannot_drop_frozen_request_parameters():
    messages = CapturingMessages(FABLE_5_MODEL_ID)
    client = SimpleNamespace(messages=messages)
    prompt = SimpleNamespace(system="system", user="user")
    request = SimpleNamespace(
        intent=SimpleNamespace(route=SimpleNamespace(api_model_id=FABLE_5_MODEL_ID)),
        context=SimpleNamespace(
            limits=SimpleNamespace(max_output_tokens=256, timeout_seconds=5.0)
        ),
    )
    raw = ProviderReadyContentWriter._default_caller(client, prompt, request)
    assert len(messages.calls) == 1
    assert messages.calls[0]["inference_geo"] == "global"
    assert messages.calls[0]["service_tier"] == "standard_only"
    assert raw.usage.inference_geo == "global"
    assert raw.usage.service_tier == "standard"


def _ready_qualification(storage, request_id: str):
    _register(storage)
    return _approval(
        storage,
        role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE,
        request_id=request_id,
    )


@pytest.mark.parametrize(
    ("usage_overrides", "failure_kind"),
    [
        ({"inference_geo": "us", "service_tier": "standard"},
         "RETURNED_INFERENCE_GEO_MISMATCH"),
        ({"inference_geo": "global", "service_tier": "priority"},
         "RETURNED_SERVICE_TIER_MISMATCH"),
    ],
)
def test_returned_provenance_mismatch_is_durable_and_never_replayed(
    fable_contract_storage, usage_overrides, failure_kind,
):
    contract_storage = fable_contract_storage
    approval = _ready_qualification(contract_storage, f"prov-{failure_kind}")
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda item: QualificationProbeResponse(
        returned_model_id=item.technical_model_id,
        structured_response_ok=True,
        usage=QualificationProbeUsage(
            input_tokens=900,
            output_tokens=120,
            **usage_overrides,
        ),
        stop_reason="end_turn",
    ))
    outcome = contract_storage.execute_controlled_qualification(
        approval, caller=caller,
    )
    assert caller.calls == 1
    assert outcome.outcome == "NEEDS_VERIFICATION"
    assert outcome.failure_kind == failure_kind
    assert outcome.usage is not None
    assert outcome.cost_usd == Decimal("0.015000")
    replay = CountingQualificationCaller(lambda _item: pytest.fail("replay"))
    with pytest.raises(ControlledQualificationError):
        contract_storage.execute_controlled_qualification(approval, caller=replay)
    assert replay.calls == 0


def test_returned_optional_provenance_can_confirm_global_standard(fable_contract_storage):
    contract_storage = fable_contract_storage
    approval = _ready_qualification(contract_storage, "prov-legal")
    contract_storage.record_model_qualification_approval(approval)
    outcome = contract_storage.execute_controlled_qualification(
        approval,
        caller=lambda item: QualificationProbeResponse(
            returned_model_id=item.technical_model_id,
            structured_response_ok=True,
            usage=QualificationProbeUsage(
                input_tokens=900,
                output_tokens=120,
                inference_geo="global",
                service_tier="standard",
            ),
            stop_reason="end_turn",
        ),
    )
    assert outcome.outcome == "PASS"


def test_missing_fable_retention_acceptance_blocks_before_effect(fable_contract_storage):
    contract_storage = fable_contract_storage
    approved = _ready_qualification(contract_storage, "retention-missing")
    approval = replace(approved, retention_acceptance_ref=None)
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda _item: pytest.fail("caller reached"))
    with pytest.raises(ControlledQualificationError) as excinfo:
        contract_storage.execute_controlled_qualification(approval, caller=caller)
    assert excinfo.value.code == "FABLE_RETENTION_ACCEPTANCE_MISSING"
    assert caller.calls == 0
    assert contract_storage.conn.execute(
        "SELECT count(*) FROM model_qualification_runs WHERE request_id=?",
        (approval.request_id,),
    ).fetchone()[0] == 0


def test_matching_fake_retention_acceptance_reaches_next_gate(fable_contract_storage):
    contract_storage = fable_contract_storage
    approval = _ready_qualification(contract_storage, "retention-match")
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda item: QualificationProbeResponse(
        returned_model_id=item.technical_model_id,
        structured_response_ok=False,
        usage=QualificationProbeUsage(input_tokens=10, output_tokens=5),
    ))
    outcome = contract_storage.execute_controlled_qualification(
        approval, caller=caller,
    )
    assert caller.calls == 1
    assert outcome.outcome == "FAIL"
    assert outcome.failure_kind == "STRUCTURED_RESPONSE_REJECTED"


def test_retention_evidence_for_another_request_is_rejected(fable_contract_storage):
    contract_storage = fable_contract_storage
    approved = _ready_qualification(contract_storage, "retention-target")
    wrong_ref = "retention-other-request"
    contract_storage.record_fable_retention_acceptance(FableRetentionAcceptance(
        acceptance_ref=wrong_ref,
        scope=RETENTION_SCOPE_QUALIFICATION,
        approval_ref=approved.approval_ref,
        request_identity="another-request",
        provider="ANTHROPIC",
        technical_model_id=FABLE_5_MODEL_ID,
        provider_policy_ref="fake://anthropic/fable-5/retention",
        accepted_by="fake-owner",
        accepted_at="2026-08-01T00:00:00.000000+00:00",
        expires_at=EXPIRES_AT,
    ))
    approval = replace(approved, retention_acceptance_ref=wrong_ref)
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda _item: pytest.fail("caller reached"))
    with pytest.raises(ControlledQualificationError) as excinfo:
        contract_storage.execute_controlled_qualification(approval, caller=caller)
    assert excinfo.value.code == "FABLE_RETENTION_ACCEPTANCE_TARGET_MISMATCH"
    assert caller.calls == 0


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "OTHER"},
        {"technical_model_id": "claude-opus-5"},
    ],
)
def test_retention_evidence_for_another_provider_or_model_is_invalid(change):
    values = dict(
        acceptance_ref="invalid-retention",
        scope=RETENTION_SCOPE_QUALIFICATION,
        approval_ref="approval-invalid",
        request_identity="invalid",
        provider="ANTHROPIC",
        technical_model_id=FABLE_5_MODEL_ID,
        provider_policy_ref="fake://anthropic/fable-5/retention",
        accepted_by="fake-owner",
        accepted_at=APPROVED_AT,
        expires_at=EXPIRES_AT,
    )
    values.update(change)
    with pytest.raises(ValueError):
        FableRetentionAcceptance(**values)


def test_expired_retention_evidence_blocks_before_effect(fable_contract_storage):
    contract_storage = fable_contract_storage
    seeded = _ready_qualification(contract_storage, "retention-expired-seed")
    approved = replace(
        seeded,
        approval_ref="approval-retention-expired",
        request_id="retention-expired",
        retention_acceptance_ref=None,
    )
    expired_ref = "retention-expired-exact"
    contract_storage.record_fable_retention_acceptance(FableRetentionAcceptance(
        acceptance_ref=expired_ref,
        scope=RETENTION_SCOPE_QUALIFICATION,
        approval_ref=approved.approval_ref,
        request_identity=approved.request_id,
        provider="ANTHROPIC",
        technical_model_id=FABLE_5_MODEL_ID,
        provider_policy_ref="fake://anthropic/fable-5/retention",
        accepted_by="fake-owner",
        accepted_at="2026-08-01T00:00:00.000000+00:00",
        expires_at="2026-08-09T00:00:00.000000+00:00",
    ))
    approval = replace(approved, retention_acceptance_ref=expired_ref)
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda _item: pytest.fail("caller reached"))
    with pytest.raises(ControlledQualificationError) as excinfo:
        contract_storage.execute_controlled_qualification(
            approval, caller=caller, now=datetime.fromisoformat(NOW),
        )
    assert excinfo.value.code == "FABLE_RETENTION_ACCEPTANCE_EXPIRED"
    assert caller.calls == 0


def test_fable_refusal_is_terminal_preserves_decimal_cost_and_never_qualifies(
    fable_contract_storage,
):
    contract_storage = fable_contract_storage
    approval = _ready_qualification(contract_storage, "fable-refusal")
    contract_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(lambda item: QualificationProbeResponse(
        returned_model_id=item.technical_model_id,
        structured_response_ok=True,
        usage=QualificationProbeUsage(
            input_tokens=900,
            output_tokens=120,
            inference_geo="global",
            service_tier="standard",
        ),
        stop_reason="refusal",
        provider_request_id="fake-refusal",
    ))
    outcome = contract_storage.execute_controlled_qualification(
        approval, caller=caller,
    )
    assert caller.calls == 1
    assert outcome.outcome == "FAIL"
    assert outcome.failure_kind == "PROVIDER_REFUSAL"
    assert outcome.cost_usd == Decimal("0.015000")
    assert contract_storage.conn.execute(
        "SELECT count(*) FROM model_capability_declarations "
        "WHERE model_registry_id=? AND verification_state='VERIFIED'",
        (approval.model_registry_id,),
    ).fetchone()[0] == 0
    second = CountingQualificationCaller(lambda _item: pytest.fail("second call"))
    with pytest.raises(ControlledQualificationError):
        contract_storage.execute_controlled_qualification(approval, caller=second)
    assert second.calls == 0


def test_provider_ready_writer_maps_http_success_refusal_without_retry(storage, account):
    caller = ScriptedCaller(stop_reason="refusal")
    request, _, _, summary, writer, factory, _ = run_provider(
        storage,
        account,
        content_type=ContentType.ARTICLE,
        suffix="fable-refusal",
        caller=caller,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == WriterFailureKind.PROVIDER_REFUSAL.value
    assert caller.calls == writer.caller_calls == len(factory.calls) == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["usages"]) == 1
    assert state["results"][0]["stop_reason"] == "refusal"


class ReturnedProvenanceCaller(ScriptedCaller):
    def __init__(self, *, inference_geo: str, service_tier: str):
        super().__init__()
        self.inference_geo = inference_geo
        self.service_tier = service_tier

    def __call__(self, client, prompt, request):
        raw = super().__call__(client, prompt, request)
        return replace(
            raw,
            usage=raw.usage.model_copy(update={
                "inference_geo": self.inference_geo,
                "service_tier": self.service_tier,
            }),
        )


@pytest.mark.parametrize(
    ("inference_geo", "service_tier"),
    [("us", "standard"), ("global", "priority")],
)
def test_content_returned_provenance_mismatch_is_uncertain_without_retry(
    storage, account, inference_geo, service_tier,
):
    caller = ReturnedProvenanceCaller(
        inference_geo=inference_geo, service_tier=service_tier,
    )
    request, _, _, summary, writer, factory, _ = run_provider(
        storage,
        account,
        content_type=ContentType.ARTICLE,
        suffix=f"provenance-{inference_geo}-{service_tier}",
        caller=caller,
    )
    assert summary.status is ContentStatus.NEEDS_VERIFICATION
    assert summary.block_code == WriterFailureKind.UNCERTAIN_STATE.value
    assert caller.calls == writer.caller_calls == len(factory.calls) == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["usages"]) == 1
    assert state["attempts"][0]["status"] == "SETTLED"


class PaidRefusalWriter(CatalogueFakeWriter):
    call_mode = WriterCallMode.CONTROLLED_PROVIDER

    def write(self, request):
        self.calls += 1
        route = request.intent.route
        self.seen_models.append(route.api_model_id)
        return WriterFailure(
            kind=WriterFailureKind.PROVIDER_REFUSAL,
            provider=route.provider,
            route_key=route.route_key,
            api_model_id=route.api_model_id,
            usage=WriterUsage(
                input_tokens=1200,
                output_tokens=800,
                inference_geo="global",
                service_tier="standard",
                estimated_cost_usd=0.0,
            ),
            stop_reason="refusal",
            provider_request_id="fake-paid-refusal",
            detail="provider refusal",
        )


def test_paid_content_refusal_preserves_frozen_cost_and_stops_after_one_call(
    contract_storage, settings, account,
):
    activated = _activate_article_roles(contract_storage)
    model = _seeded(activated[LogicalModelRole.ARTICLE_WRITER])
    request, lease, owner = _prepare(
        contract_storage, account, suffix="paid-refusal",
    )
    approve_content_provider_execution(
        contract_storage,
        job_id=request.job_id,
        model=model,
        account_id=account.id,
    )
    writer = PaidRefusalWriter()
    summary = _run(contract_storage, settings, lease, owner, writer)
    assert writer.calls == 1
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == "PROVIDER_REFUSAL"
    settlement = contract_storage.conn.execute(
        "SELECT cost_usd FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    assert settlement is not None
    assert settlement["cost_usd"] == "0.026000"
    assert contract_storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0] == 1


def test_opus_content_does_not_require_fable_retention_acceptance(
    contract_storage, settings, account,
):
    activated = _activate_article_roles(contract_storage)
    model = _seeded(activated[LogicalModelRole.ARTICLE_WRITER])
    request, lease, owner = _prepare(
        contract_storage, account, suffix="content-retention-missing",
    )
    contract_storage.record_content_provider_approval(
        approval_ref=f"approval-{request.job_id}",
        job_id=request.job_id,
        account_id=account.id,
        role=LogicalModelRole.ARTICLE_WRITER,
        model_registry_id=model.registry_id,
        provider=model.provider,
        technical_model_id=model.technical_model_id,
        pricing_ref=model.pricing_ref,
        max_output_tokens=8192,
        cap_usd="1.000000",
        approved_by="fake-owner",
        approved_at="2026-01-01T00:00:00.000000+00:00",
        expires_at=EXPIRES_AT,
        retention_acceptance_ref=None,
        inference_config=ARTICLE_WRITER_INFERENCE_CONFIG,
    )
    writer = CatalogueFakeWriter()
    summary = _run(contract_storage, settings, lease, owner, writer)
    assert writer.calls == 1
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert contract_storage.conn.execute(
        "SELECT cost_usd FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0] == "0.026000"


def test_role_response_provenance_and_refusal_are_not_success(contract_storage):
    activated = _activate_article_roles(contract_storage)
    contract_storage.freeze_content_role_model_binding(
        job_id="role-contract", role=LogicalModelRole.ARTICLE_PLAN,
    )
    provenance = contract_storage.load_content_role_provenance(
        job_id="role-contract", role=LogicalModelRole.ARTICLE_PLAN,
    )
    from app.content.provider_roles import assert_role_binding_ready
    authority = assert_role_binding_ready(
        job_id="role-contract",
        role=LogicalModelRole.ARTICLE_PLAN,
        binding=provenance["binding"],
        model=provenance["model"],
        pricing=provenance["pricing"],
        capability=provenance["capability"],
        qualification=provenance["qualification"],
        now=NOW,
    )
    mismatch = evaluate_role_response(
        authority=authority,
        run_id="fake-run",
        content_id=1,
        response=RoleProviderResponse(
            returned_model_id=authority.technical_model_id,
            payload={"plan": "x"},
            usage=RoleUsage(
                input_tokens=10,
                output_tokens=5,
                inference_geo="global",
                service_tier="priority",
            ),
        ),
    )
    assert mismatch.outcome == "NEEDS_VERIFICATION"
    refusal = evaluate_role_response(
        authority=authority,
        run_id="fake-run",
        content_id=1,
        response=RoleProviderResponse(
            returned_model_id=authority.technical_model_id,
            payload={"refusal": True},
            usage=RoleUsage(
                input_tokens=10,
                output_tokens=5,
                inference_geo="global",
                service_tier="standard",
            ),
            stop_reason="refusal",
        ),
    )
    assert refusal.outcome == "FAILURE"
    assert refusal.failure_kind == "PROVIDER_REFUSAL"


def test_0030_is_explicit_forward_only_and_idempotent(tmp_path, capsys):
    import scripts.migrate_schema_0030 as cli

    path = tmp_path / "0030.db"
    initialize_database(path, through=VERIFIED_CATALOGUE_SCHEMA_VERSION)
    conn = connect(path)
    old_storage = SqliteStorage(conn)
    candidate = FABLE_5.candidate()
    model = old_storage.register_model_candidate(candidate)
    for profile in FABLE_5.pricing:
        old_storage.register_model_pricing_profile(profile)
    payload = FABLE_5.evidence_payload(model.registry_id)
    payload["runtime_shape"] = {
        "inference_geography": "GLOBAL_DEFAULT",
        "fast_mode": False,
        "prompt_caching": False,
        "server_web_tools": False,
        "batch_api": False,
        "provider_fallback_api": False,
    }
    evidence_json = canonical_json(payload)
    conn.execute(
        "INSERT INTO model_catalogue_evidence (evidence_ref,model_registry_id,"
        "provider,technical_model_id,source,verified_by,verified_at,"
        "inference_geography,fast_mode,prompt_caching,server_web_tools,"
        "batch_api,provider_fallback_api,notes,evidence_json,"
        "evidence_fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            payload["evidence_ref"], model.registry_id, candidate.provider,
            FABLE_5.technical_model_id, "OWNER_VERIFIED_PROVIDER_DOCUMENTATION",
            "fake-owner", payload["verified_at"], "GLOBAL_DEFAULT", 0, 0, 0,
            0, 0, FABLE_5.notes, evidence_json, sha256_text(evidence_json), NOW,
        ),
    )
    conn.commit()
    conn.close()
    assert cli.main(["--db-path", str(path)]) == 2
    assert "--confirm-0029-to-0030 is required" in capsys.readouterr().err
    first = migrate_0029_to_0030(path)
    second = migrate_0029_to_0030(path)
    assert first.applied_migrations == (ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,)
    assert second.idempotent is True
    assert cli.main([
        "--db-path", str(path), "--confirm-0029-to-0030",
    ]) == 0
    assert database_schema_versions(path)[-1] == ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION
    conn = connect(path)
    row = conn.execute(
        "SELECT inference_geography,service_tier_request,evidence_json,"
        "evidence_fingerprint FROM model_catalogue_evidence"
    ).fetchone()
    assert row["inference_geography"] == "global"
    assert row["service_tier_request"] == "standard_only"
    assert row["evidence_fingerprint"] == sha256_text(row["evidence_json"])
    assert json.loads(row["evidence_json"])["runtime_shape"] == {
        "batch_api": False,
        "expected_response_inference_geo": "global",
        "expected_response_service_tier": "standard",
        "fast_mode": False,
        "inference_geography": "global",
        "prompt_caching": False,
        "provider_fallback_api": False,
        "server_web_tools": False,
        "service_tier_request": "standard_only",
    }
    conn.close()


def test_c5_decimal_cost_and_us_counterfactual_are_evidence_only():
    qualification = Decimal("0.442880")
    execution = Decimal("0.496000")
    global_standard = qualification + execution
    assert global_standard == Decimal("0.938880")
    assert global_standard * Decimal("1.1") == Decimal("1.0327680")
