"""PRE-C5: VERIFIED ANTHROPIC CATALOGUE & CONTROLLED ARTICLE LIVE ROOT.

Everything here is offline.  Fake SDK factories, fake callers, temporary SQLite
databases.  No network, no real SDK call, no browser, no publication, no cost.

The catalogue identities and prices used below are the owner-verified snapshot;
the point of most of these tests is that knowing them changes nothing about
whether a model may run.  Qualification stays a separate, separately approved
fact, and the technical caller stays unreachable until every part of the chain
is frozen, approved and effective.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import sqlite3

import pytest

from app.content.cost_estimate import (
    ROLE_ENVELOPES,
    estimate_controlled_article_cost,
    estimate_role_cost,
)
from app.content.foundation import ContentExecutionMode, ContentStatus, ContentType
from app.content.provider_roles import (
    CONTENT_ROLE_INTENT_KIND,
    RoleProviderError,
    RoleProviderResponse,
    RoleUsage,
    assert_role_binding_ready,
    content_role_binding_intent_id,
    evaluate_role_response,
)
from app.core.clock import FixedClock
from app.llm.anthropic_controlled_adapter import (
    ControlledAdapterError,
    ControlledAnthropicAdapter,
    ControlledProviderRawResponse,
    ControlledProviderRequest,
    assert_no_disabled_feature_usage,
    assert_returned_model_identity,
    describe_runtime_shape,
)
from app.llm.anthropic_provider_contract import (
    FABLE_5_MODEL_ID,
    FableRetentionAcceptance,
    RETENTION_SCOPE_QUALIFICATION,
)
from app.model_routing import (
    LogicalModelRole,
    ModelFamily,
    QualificationState,
    RoutingError,
)
from app.model_routing.catalogue import (
    FABLE_5,
    OPUS_5,
    OWNER_VERIFIED_CATALOGUE,
    SONNET_5,
    SONNET_PROMO_UNTIL,
)
from app.model_routing.qualification import (
    ControlledQualificationError,
    QualificationApproval,
    QualificationProbeResponse,
    QualificationProbeUsage,
)
from app.model_routing.role_bootstrap import owner_approved_role_policy
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import ContentFoundationError
from app.storage.db import (
    ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    VERIFIED_CATALOGUE_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0028_to_0029,
    migrate_0029_to_0030,
)
from app.storage.repositories import SqliteStorage
from tests.controlled_provider_fixtures import (
    approve_content_provider_execution,
    SeededModel,
)
from tests.test_prec5_controlled_provider_provenance import (
    ProvenanceFakeWriter,
    _prepare,
    _run,
    ROOT,
)
from tests.test_e3_evidence_research import NOW


BEFORE_PROMO_END = "2026-08-15T00:00:00.000000+00:00"
AFTER_PROMO_END = "2026-09-15T00:00:00.000000+00:00"
APPROVED_AT = "2026-08-10T00:00:00.000000+00:00"
EXPIRES_AT = "2099-01-01T00:00:00.000000+00:00"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture
def catalogue_storage(tmp_path):
    path = tmp_path / "catalogue.db"
    initialize_database(path)
    value = SqliteStorage.open(path)
    try:
        yield value
    finally:
        value.close()


def _register(storage):
    return storage.register_owner_verified_catalogue(verified_by="owner-test")


def _entry_for(storage, family: ModelFamily):
    row = storage.conn.execute(
        "SELECT * FROM model_registry WHERE family=? AND provider='ANTHROPIC'",
        (family.value,),
    ).fetchone()
    assert row is not None
    return row


def _approval(
    storage,
    *,
    role: LogicalModelRole,
    family: ModelFamily,
    pricing_ref: str | None = None,
    request_id: str = "qual-1",
    cap: str = "1",
    approved_at: str = APPROVED_AT,
    expires_at: str = EXPIRES_AT,
    registry_id: str | None = None,
    technical_model_id: str | None = None,
) -> QualificationApproval:
    row = _entry_for(storage, family)
    envelope = ROLE_ENVELOPES[role]
    resolved_model_id = technical_model_id or str(row["technical_model_id"])
    acceptance_ref = None
    if resolved_model_id == FABLE_5_MODEL_ID:
        acceptance_ref = f"retention-{request_id}"
        if storage._get_fable_retention_acceptance(acceptance_ref) is None:
            storage.record_fable_retention_acceptance(FableRetentionAcceptance(
                acceptance_ref=acceptance_ref,
                scope=RETENTION_SCOPE_QUALIFICATION,
                approval_ref=f"approval-{request_id}",
                request_identity=request_id,
                provider="ANTHROPIC",
                technical_model_id=FABLE_5_MODEL_ID,
                provider_policy_ref="fake://anthropic/fable-5/retention",
                accepted_by="fake-owner-fixture",
                accepted_at=approved_at,
                expires_at=expires_at,
            ))
    return QualificationApproval(
        approval_ref=f"approval-{request_id}",
        request_id=request_id,
        logical_role=role,
        model_registry_id=registry_id or str(row["registry_id"]),
        provider="ANTHROPIC",
        technical_model_id=resolved_model_id,
        pricing_ref=pricing_ref or str(row["pricing_ref"]),
        max_input_tokens=envelope.qualification_input_tokens,
        max_output_tokens=envelope.max_output_tokens,
        cap_usd=Decimal(cap),
        approved_by="owner-test",
        approved_at=approved_at,
        expires_at=expires_at,
        retention_acceptance_ref=acceptance_ref,
    )


def _probe(model_id: str, *, ok: bool = True, **usage) -> QualificationProbeResponse:
    counts = {"input_tokens": 900, "output_tokens": 120}
    counts.update(usage)
    return QualificationProbeResponse(
        returned_model_id=model_id,
        structured_response_ok=ok,
        usage=QualificationProbeUsage(**counts),
    )


class CountingQualificationCaller:
    """A fake probe caller that records how often it was reached."""

    def __init__(self, response_factory):
        self._factory = response_factory
        self.calls = 0

    def __call__(self, approval):
        self.calls += 1
        return self._factory(approval)


def _qualify(
    storage,
    *,
    role: LogicalModelRole,
    family: ModelFamily,
    request_id: str,
    ok: bool = True,
    now=None,
    **probe_kwargs,
):
    """Approve and execute one fake controlled qualification."""
    approval = _approval(
        storage, role=role, family=family, request_id=request_id,
    )
    storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(
        lambda item: _probe(item.technical_model_id, ok=ok, **probe_kwargs)
    )
    outcome = storage.execute_controlled_qualification(
        approval, caller=caller, now=now,
    )
    return approval, outcome, caller


def _activate_article_roles(storage, *, now=None):
    """Full bootstrap: policies, qualification, promotion for the three roles."""
    _register(storage)
    activated = {}
    for index, role in enumerate((
        LogicalModelRole.ARTICLE_PLAN,
        LogicalModelRole.ARTICLE_WRITER,
        LogicalModelRole.ARTICLE_REVIEWER,
    )):
        storage.upsert_model_role_policy(owner_approved_role_policy(role))
        family = {
            LogicalModelRole.ARTICLE_PLAN: ModelFamily.OPUS,
            LogicalModelRole.ARTICLE_WRITER: ModelFamily.FABLE,
            LogicalModelRole.ARTICLE_REVIEWER: ModelFamily.OPUS,
        }[role]
        row = _entry_for(storage, family)
        if str(row["current_qualification_state"]) != "PASS":
            _qualify(
                storage, role=role, family=family,
                request_id=f"qual-{role.value.lower()}-{index}", now=now,
            )
        storage.promote_best_model(role, reason="controlled qualification pass")
        activated[role] = _entry_for(storage, family)
    return activated


def _seeded(row) -> SeededModel:
    return SeededModel(
        registry_id=str(row["registry_id"]), provider=str(row["provider"]),
        family=ModelFamily(str(row["family"])),
        logical_version=str(row["logical_version"]),
        technical_model_id=str(row["technical_model_id"]),
        pricing_ref=str(row["pricing_ref"]),
        capability_ref=str(row["current_capability_ref"]),
        qualification_ref=str(row["current_qualification_ref"]),
    )


# ---------------------------------------------------------------------------
# Catalogue identity and pricing
# ---------------------------------------------------------------------------

def test_catalogue_carries_the_owner_verified_identities(catalogue_storage):
    models = _register(catalogue_storage)
    identities = {
        (m.family.value, m.logical_version, m.technical_model_id, m.provider)
        for m in models
    }
    assert identities == {
        ("FABLE", "5", "claude-fable-5", "ANTHROPIC"),
        ("OPUS", "5", "claude-opus-5", "ANTHROPIC"),
        ("SONNET", "5", "claude-sonnet-5", "ANTHROPIC"),
    }
    # A logical role never names a technical ID.
    for entry in OWNER_VERIFIED_CATALOGUE:
        assert not any(
            character.isdigit() for character in entry.family.value
        )


def test_catalogue_registration_never_implies_qualification(catalogue_storage):
    models = _register(catalogue_storage)
    assert {m.qualification_state for m in models} == {
        QualificationState.UNQUALIFIED
    }
    assert {m.lifecycle_state.value for m in models} == {"CANDIDATE"}
    evidence = catalogue_storage.conn.execute(
        "SELECT source,prompt_caching,fast_mode,server_web_tools,batch_api,"
        "provider_fallback_api,inference_geography,service_tier_request,"
        "expected_response_inference_geo,expected_response_service_tier "
        "FROM model_catalogue_evidence"
    ).fetchall()
    assert len(evidence) == 3
    for row in evidence:
        assert row["source"] == "OWNER_VERIFIED_PROVIDER_DOCUMENTATION"
        assert row["inference_geography"] == "global"
        assert row["service_tier_request"] == "standard_only"
        assert row["expected_response_inference_geo"] == "global"
        assert row["expected_response_service_tier"] == "standard"
        assert (
            row["prompt_caching"], row["fast_mode"], row["server_web_tools"],
            row["batch_api"], row["provider_fallback_api"],
        ) == (0, 0, 0, 0, 0)


def test_01_real_catalogue_entry_without_qualification_cannot_be_promoted(
    catalogue_storage,
):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    outcome = catalogue_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="unqualified catalogue entry",
    )
    assert outcome.status.value == "BLOCKED"
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
        catalogue_storage.freeze_content_writer_model_binding(
            job_id="job-x", content_type=ContentType.ARTICLE,
        )


def test_12_a_locally_fixtured_pass_cannot_qualify_a_real_model(catalogue_storage):
    """SQL floor: catalogue evidence forces the controlled path."""
    from app.model_routing import QualificationReport

    _register(catalogue_storage)
    row = _entry_for(catalogue_storage, ModelFamily.FABLE)
    with pytest.raises(sqlite3.IntegrityError, match="controlled qualification"):
        catalogue_storage.record_model_qualification(
            QualificationReport(
                qualification_ref="hand-written-pass",
                model_registry_id=str(row["registry_id"]),
                state=QualificationState.PASS,
                suite_version="local", fixture_set_ref="local",
                result_payload={"outcome": "PASS"},
                evaluated_at=APPROVED_AT,
            )
        )


@pytest.mark.parametrize("at,expected_ref", [
    (BEFORE_PROMO_END, "anthropic-sonnet-5-promotional-until-2026-08-31"),
    (AFTER_PROMO_END, "anthropic-sonnet-5-standard-from-2026-09-01"),
])
def test_sonnet_promotional_price_never_outlives_its_window(at, expected_ref):
    effective = [item for item in SONNET_5.pricing if item.is_effective_at(at)]
    assert len(effective) == 1
    assert effective[0].pricing_ref == expected_ref
    promotional = SONNET_5.pricing[0]
    assert promotional.effective_until == SONNET_PROMO_UNTIL
    assert promotional.is_effective_at(AFTER_PROMO_END) is False


def test_05_expired_pricing_blocks_a_new_binding(catalogue_storage):
    """A frozen binding may not be minted against an expired promotion."""
    _register(catalogue_storage)
    storage = catalogue_storage
    storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.NOTE_WRITER)
        if False else owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    row = _entry_for(storage, ModelFamily.SONNET)
    promo_ref = "anthropic-sonnet-5-promotional-until-2026-08-31"
    with pytest.raises(sqlite3.IntegrityError, match="not effective at binding time"):
        storage.conn.execute(
            "INSERT INTO model_intent_bindings (intent_kind,intent_id,role,"
            "model_registry_id,provider,family,logical_version,"
            "technical_model_id,pricing_ref,qualification_ref,capability_ref,"
            "activation_decision_fingerprint,fallback_policy,bound_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "content_writer", "expired:content_writer", "NOTE_WRITER",
                str(row["registry_id"]), "ANTHROPIC", "SONNET", "5",
                "claude-sonnet-5", promo_ref, "q", "c", "0" * 64, "FORBIDDEN",
                AFTER_PROMO_END,
            ),
        )
    storage.conn.rollback()


# ---------------------------------------------------------------------------
# Controlled qualification bootstrap
# ---------------------------------------------------------------------------

def test_13_controlled_qualification_pass_makes_a_model_eligible(catalogue_storage):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    approval, outcome, caller = _qualify(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="qual-pass",
    )
    assert caller.calls == 1
    assert outcome.outcome == "PASS"
    assert outcome.cost_usd == Decimal("0.015000")  # 900@10 + 120@50 per MTok
    row = _entry_for(catalogue_storage, ModelFamily.FABLE)
    assert row["current_qualification_state"] == "PASS"
    stored = catalogue_storage.conn.execute(
        "SELECT source FROM model_qualification_results WHERE qualification_ref=?",
        (outcome.qualification_ref,),
    ).fetchone()
    assert stored["source"] == "CONTROLLED_LIVE"
    promotion = catalogue_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="qualified",
    )
    assert promotion.status.value == "PROMOTED"


def test_12b_qualification_fail_leaves_the_model_unusable(catalogue_storage):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    _, outcome, _ = _qualify(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="qual-fail", ok=False,
    )
    assert outcome.outcome == "FAIL"
    assert catalogue_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="failed",
    ).status.value == "BLOCKED"


def test_07_missing_qualification_approval_blocks_the_caller(catalogue_storage):
    _register(catalogue_storage)
    approval = _approval(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="never-approved",
    )
    caller = CountingQualificationCaller(
        lambda item: _probe(item.technical_model_id)
    )
    with pytest.raises(ControlledQualificationError) as excinfo:
        catalogue_storage.execute_controlled_qualification(
            approval, caller=caller,
        )
    assert excinfo.value.code == "QUALIFICATION_APPROVAL_MISSING"
    assert caller.calls == 0


def test_08_expired_qualification_approval_blocks_the_caller(catalogue_storage):
    _register(catalogue_storage)
    approval = _approval(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="expired",
        approved_at="2026-01-01T00:00:00.000000+00:00",
        expires_at="2026-01-02T00:00:00.000000+00:00",
    )
    catalogue_storage.record_model_qualification_approval(approval)
    caller = CountingQualificationCaller(
        lambda item: _probe(item.technical_model_id)
    )
    with pytest.raises(ControlledQualificationError) as excinfo:
        catalogue_storage.execute_controlled_qualification(approval, caller=caller)
    assert excinfo.value.code == "QUALIFICATION_APPROVAL_EXPIRED"
    assert caller.calls == 0


def test_09_a_qualification_approval_cannot_be_replayed(catalogue_storage):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    approval, _, _ = _qualify(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="replay",
    )
    caller = CountingQualificationCaller(
        lambda item: _probe(item.technical_model_id)
    )
    with pytest.raises(ControlledQualificationError) as excinfo:
        catalogue_storage.execute_controlled_qualification(approval, caller=caller)
    # The durable run is now the first guard; either refusal proves the same
    # thing, which is that this request never reaches a caller twice.
    assert excinfo.value.code in {
        "QUALIFICATION_RUN_ALREADY_EXISTS",
        "QUALIFICATION_APPROVAL_ALREADY_CONSUMED",
    }
    assert caller.calls == 0


def test_11_a_qualification_approval_for_another_registry_id_is_blocked(
    catalogue_storage,
):
    _register(catalogue_storage)
    fable = _entry_for(catalogue_storage, ModelFamily.FABLE)
    approval = _approval(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="wrong-registry",
    )
    catalogue_storage.record_model_qualification_approval(approval)
    opus = _entry_for(catalogue_storage, ModelFamily.OPUS)
    impostor = QualificationApproval(
        **{
            **{
                "approval_ref": approval.approval_ref,
                "request_id": approval.request_id,
                "logical_role": approval.logical_role,
                "provider": approval.provider,
                "pricing_ref": approval.pricing_ref,
                "max_input_tokens": approval.max_input_tokens,
                "max_output_tokens": approval.max_output_tokens,
                "cap_usd": approval.cap_usd,
                "approved_by": approval.approved_by,
                "approved_at": approval.approved_at,
                "expires_at": approval.expires_at,
            },
            "model_registry_id": str(opus["registry_id"]),
            "technical_model_id": "claude-opus-5",
        }
    )
    caller = CountingQualificationCaller(
        lambda item: _probe(item.technical_model_id)
    )
    with pytest.raises(ControlledQualificationError) as excinfo:
        catalogue_storage.execute_controlled_qualification(impostor, caller=caller)
    assert excinfo.value.code in {
        "QUALIFICATION_APPROVAL_TARGET_MISMATCH",
        "QUALIFICATION_MODEL_IDENTITY_MISMATCH",
    }
    assert caller.calls == 0
    assert str(fable["registry_id"]) != str(opus["registry_id"])


def test_15_qualification_returned_model_mismatch_never_passes(catalogue_storage):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    approval = _approval(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id="wrong-model",
    )
    catalogue_storage.record_model_qualification_approval(approval)
    outcome = catalogue_storage.execute_controlled_qualification(
        approval, caller=lambda item: _probe("claude-opus-5"),
    )
    assert outcome.outcome == "NEEDS_VERIFICATION"
    assert outcome.failure_kind == "RETURNED_MODEL_MISMATCH"
    assert outcome.qualification_ref is None
    row = _entry_for(catalogue_storage, ModelFamily.FABLE)
    assert row["current_qualification_state"] == "UNQUALIFIED"


@pytest.mark.parametrize("usage_kwargs,expected", [
    ({"cache_read_tokens": 10}, "UNEXPECTED_CACHE_USAGE"),
    ({"cache_write_tokens": 10}, "UNEXPECTED_CACHE_USAGE"),
    ({"web_search_requests": 1}, "UNEXPECTED_WEB_SEARCH_USAGE"),
])
def test_19_20_disabled_feature_usage_is_never_free(
    catalogue_storage, usage_kwargs, expected,
):
    _register(catalogue_storage)
    catalogue_storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_WRITER)
    )
    _, outcome, _ = _qualify(
        catalogue_storage, role=LogicalModelRole.ARTICLE_WRITER,
        family=ModelFamily.FABLE, request_id=f"feat-{expected.lower()}",
        **usage_kwargs,
    )
    assert outcome.outcome == "NEEDS_VERIFICATION"
    assert outcome.failure_kind == expected
    # The usage was priced, not silently treated as zero.
    assert outcome.cost_usd > Decimal("0")


# ---------------------------------------------------------------------------
# Adapter: identity, fallback, disabled features
# ---------------------------------------------------------------------------

def test_adapter_never_reads_a_secret_before_the_execution_boundary():
    calls = {"secret": 0, "sdk": 0, "caller": 0}

    def secret():
        calls["secret"] += 1
        return "fake-key"

    def factory(*, api_key, max_retries, timeout):
        calls["sdk"] += 1
        assert max_retries == 0
        return object()

    def caller(client, request):
        calls["caller"] += 1
        return ControlledProviderRawResponse(
            returned_model_id=request.technical_model_id, text="{}",
            input_tokens=10, output_tokens=5, cache_read_tokens=0,
            cache_write_tokens=0, web_search_requests=0,
            stop_reason="end_turn", provider_request_id="fake",
        )

    adapter = ControlledAnthropicAdapter(
        api_key_provider=secret, sdk_factory=factory, caller=caller,
    )
    assert calls == {"secret": 0, "sdk": 0, "caller": 0}
    request = ControlledProviderRequest(
        technical_model_id="claude-fable-5", system_prompt="s",
        user_prompt="u", max_output_tokens=64, timeout_seconds=5.0,
    )
    raw = adapter.execute(request)
    assert calls == {"secret": 1, "sdk": 1, "caller": 1}
    assert raw.returned_model_id == "claude-fable-5"


def test_16_adapter_disables_every_provider_fallback_and_extra_feature():
    shape = describe_runtime_shape()
    assert shape["fallback_policy"] == "FORBIDDEN"
    assert shape["provider_fallback_api"] is False
    assert shape["batch_api"] is False
    assert shape["prompt_caching"] is False
    assert shape["fast_mode"] is False
    assert shape["server_web_search"] is False
    assert shape["server_web_fetch"] is False
    assert shape["us_only_inference"] is False
    assert shape["inference_geo_request"] == "global"
    assert shape["service_tier_request"] == "standard_only"
    assert shape["expected_response_inference_geo"] == "global"
    assert shape["expected_response_service_tier"] == "standard"
    assert shape["sdk_max_retries"] == 0
    assert shape["application_max_retries"] == 0


def test_15b_returned_model_identity_gate_refuses_another_model():
    assert_returned_model_identity(
        requested_model_id="claude-fable-5", returned_model_id="claude-fable-5",
    )
    with pytest.raises(ControlledAdapterError) as excinfo:
        assert_returned_model_identity(
            requested_model_id="claude-fable-5",
            returned_model_id="claude-opus-5",
        )
    assert excinfo.value.code == "RETURNED_MODEL_MISMATCH"


@pytest.mark.parametrize("kwargs,code", [
    ({"cache_read_tokens": 1}, "UNEXPECTED_CACHE_USAGE"),
    ({"cache_write_tokens": 1}, "UNEXPECTED_CACHE_USAGE"),
    ({"web_search_requests": 1}, "UNEXPECTED_WEB_SEARCH_USAGE"),
])
def test_21_22_disabled_feature_usage_is_refused_at_the_adapter(kwargs, code):
    base = {
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "web_search_requests": 0,
    }
    base.update(kwargs)
    with pytest.raises(ControlledAdapterError) as excinfo:
        assert_no_disabled_feature_usage(**base)
    assert excinfo.value.code == code


def test_30_a_secret_less_adapter_never_reaches_its_caller():
    caller_calls = {"n": 0}

    def caller(client, request):  # pragma: no cover - must never run
        caller_calls["n"] += 1
        raise AssertionError("the caller must not be reachable")

    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: None,
        sdk_factory=lambda **_: object(),
        caller=caller,
    )
    with pytest.raises(ControlledAdapterError) as excinfo:
        adapter.execute(ControlledProviderRequest(
            technical_model_id="claude-fable-5", system_prompt="s",
            user_prompt="u", max_output_tokens=16, timeout_seconds=1.0,
        ))
    assert excinfo.value.code == "ADAPTER_SECRET_UNAVAILABLE"
    assert caller_calls["n"] == 0
    assert adapter.caller_calls == 0


# ---------------------------------------------------------------------------
# ARTICLE_PLAN / ARTICLE_REVIEWER role seam
# ---------------------------------------------------------------------------


class CatalogueFakeWriter(ProvenanceFakeWriter):
    """Fable-priced fake writer with a C5-shaped usage report."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen_pricing_refs = []

    def limits_for(self, content_type):
        from app.content.contracts import WriterLimits
        from app.content.cost_estimate import ROLE_ENVELOPES

        envelope = ROLE_ENVELOPES[LogicalModelRole.ARTICLE_WRITER]
        return WriterLimits(
            max_input_tokens=envelope.max_input_tokens,
            max_context_tokens=envelope.max_context_tokens,
            max_output_tokens=envelope.max_output_tokens,
            # The derived per-attempt worst case for Fable 5 at these ceilings.
            max_cost_usd=0.1824,
            timeout_seconds=5.0,
        )

    def write(self, request):
        from app.content.contracts import WriterSuccess, WriterUsage
        from app.content.writer import FakeContentWriter

        self.calls += 1
        route = request.intent.route
        self.seen_models.append(route.api_model_id)
        self.seen_pricing_refs.append(route.pricing_profile)
        return WriterSuccess(
            draft=FakeContentWriter().write(request).draft,
            provider=route.provider,
            route_key=route.route_key,
            api_model_id=route.api_model_id,
            usage=WriterUsage(
                input_tokens=1200, output_tokens=800,
                cache_read_tokens=0, cache_write_tokens=0,
                estimated_cost_usd=0.0,
            ),
            stop_reason="end_turn",
            provider_request_id="fake-catalogue-request",
        )


def _role_provenance(storage, job_id, role):
    return storage.load_content_role_provenance(job_id=job_id, role=role)


def _ready(storage, job_id, role, *, now=BEFORE_PROMO_END, **overrides):
    loaded = _role_provenance(storage, job_id, role)
    loaded.update(overrides)
    return assert_role_binding_ready(
        job_id=job_id, role=role, binding=loaded["binding"],
        model=loaded["model"], pricing=loaded["pricing"],
        capability=loaded["capability"], qualification=loaded["qualification"],
        now=now,
    )


def test_14_plan_and_reviewer_bind_opus_and_survive_promotion(catalogue_storage):
    _activate_article_roles(catalogue_storage)
    plan = catalogue_storage.freeze_content_role_model_binding(
        job_id="job-roles", role=LogicalModelRole.ARTICLE_PLAN,
    )
    review = catalogue_storage.freeze_content_role_model_binding(
        job_id="job-roles", role=LogicalModelRole.ARTICLE_REVIEWER,
    )
    assert plan.technical_model_id == "claude-opus-5"
    assert review.technical_model_id == "claude-opus-5"
    assert plan.family is ModelFamily.OPUS
    # Independent bindings, not one shared row.
    assert plan.intent_id != review.intent_id
    assert plan.intent_id == content_role_binding_intent_id(
        "job-roles", LogicalModelRole.ARTICLE_PLAN,
    )
    # A later promotion cannot move this execution.
    again = catalogue_storage.freeze_content_role_model_binding(
        job_id="job-roles", role=LogicalModelRole.ARTICLE_PLAN,
    )
    assert again == plan


def test_23_25_role_provenance_mismatch_blocks_before_any_caller(catalogue_storage):
    from dataclasses import replace

    _activate_article_roles(catalogue_storage)
    binding = catalogue_storage.freeze_content_role_model_binding(
        job_id="job-mismatch", role=LogicalModelRole.ARTICLE_PLAN,
    )
    for overrides, code in (
        ({"binding": None}, "CONTENT_ROLE_BINDING_MISSING"),
        (
            {"binding": replace(binding, technical_model_id="claude-opus-4")},
            "CONTENT_ROLE_REGISTRY_IDENTITY_DRIFT",
        ),
        (
            {"binding": replace(binding, family=ModelFamily.FABLE)},
            "CONTENT_ROLE_FAMILY_MISMATCH",
        ),
        (
            {"binding": replace(binding, logical_version="9")},
            "CONTENT_ROLE_REGISTRY_IDENTITY_DRIFT",
        ),
        ({"pricing": None}, "CONTENT_ROLE_PRICING_REF_MISMATCH"),
        ({"capability": None}, "CONTENT_ROLE_CAPABILITY_REF_MISMATCH"),
        ({"qualification": None}, "CONTENT_ROLE_QUALIFICATION_REF_MISMATCH"),
    ):
        with pytest.raises(RoleProviderError) as excinfo:
            _ready(
                catalogue_storage, "job-mismatch",
                LogicalModelRole.ARTICLE_PLAN, **overrides,
            )
        assert excinfo.value.code == code


def test_26_reviewer_authority_is_independent_of_the_writer(catalogue_storage):
    """The reviewer's model comes from its own binding, not from the draft."""
    _activate_article_roles(catalogue_storage)
    catalogue_storage.freeze_content_writer_model_binding(
        job_id="job-independent", content_type=ContentType.ARTICLE,
    )
    catalogue_storage.freeze_content_role_model_binding(
        job_id="job-independent", role=LogicalModelRole.ARTICLE_REVIEWER,
    )
    writer = catalogue_storage.get_frozen_model_binding(
        intent_kind="content_writer", intent_id="job-independent:content_writer",
    )
    reviewer = catalogue_storage.get_frozen_model_binding(
        intent_kind=CONTENT_ROLE_INTENT_KIND,
        intent_id="job-independent:ARTICLE_REVIEWER",
    )
    assert writer is not None and reviewer is not None
    assert writer.technical_model_id == "claude-fable-5"
    assert reviewer.technical_model_id == "claude-opus-5"
    assert writer.model_registry_id != reviewer.model_registry_id


def test_role_execution_settles_from_the_frozen_profile(catalogue_storage):
    _activate_article_roles(catalogue_storage)
    catalogue_storage.freeze_content_role_model_binding(
        job_id="job-settle", role=LogicalModelRole.ARTICLE_PLAN,
    )
    authority = _ready(
        catalogue_storage, "job-settle", LogicalModelRole.ARTICLE_PLAN,
    )
    execution = evaluate_role_response(
        authority=authority, run_id="run-1", content_id=1,
        response=RoleProviderResponse(
            returned_model_id="claude-opus-5",
            payload={"angle": "a"},
            usage=RoleUsage(input_tokens=2000, output_tokens=400),
        ),
    )
    assert execution.outcome == "SUCCESS"
    # 2000 @ 5/MTok + 400 @ 25/MTok
    assert execution.cost_usd == Decimal("0.020000")


def test_23b_role_returned_model_mismatch_is_never_a_success(catalogue_storage):
    _activate_article_roles(catalogue_storage)
    catalogue_storage.freeze_content_role_model_binding(
        job_id="job-wrongmodel", role=LogicalModelRole.ARTICLE_REVIEWER,
    )
    authority = _ready(
        catalogue_storage, "job-wrongmodel", LogicalModelRole.ARTICLE_REVIEWER,
    )
    execution = evaluate_role_response(
        authority=authority, run_id="run-1", content_id=1,
        response=RoleProviderResponse(
            returned_model_id="claude-fable-5", payload={"verdict": "ok"},
            usage=RoleUsage(input_tokens=100, output_tokens=10),
        ),
    )
    assert execution.outcome == "NEEDS_VERIFICATION"
    assert execution.failure_kind == "RETURNED_MODEL_MISMATCH"


def test_role_execution_row_requires_its_frozen_binding(catalogue_storage):
    _activate_article_roles(catalogue_storage)
    catalogue_storage.freeze_content_role_model_binding(
        job_id="job-sqlfloor", role=LogicalModelRole.ARTICLE_PLAN,
    )
    with pytest.raises(sqlite3.IntegrityError):
        catalogue_storage.conn.execute(
            "INSERT INTO role_provider_executions (execution_ref,job_id,run_id,"
            "content_id,logical_role,binding_intent_id,model_registry_id,"
            "provider,technical_model_id,returned_model_id,pricing_ref,"
            "pricing_profile_fingerprint,qualification_ref,capability_ref,"
            "outcome,failure_kind,input_tokens,output_tokens,cache_read_tokens,"
            "cache_write_tokens,web_search_requests,cost_usd,result_json,"
            "result_fingerprint,created_at) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "forged", "job-sqlfloor", "run", 1, "ARTICLE_PLAN",
                "job-sqlfloor:ARTICLE_PLAN", "model-forged", "ANTHROPIC",
                "claude-opus-5", "claude-opus-5", "p", "a" * 64, "q", "c",
                "SUCCESS", None, 0, 0, 0, 0, 0, "0.000000", "{}", "b" * 64,
                APPROVED_AT,
            ),
        )
    catalogue_storage.conn.rollback()


# ---------------------------------------------------------------------------
# Writer seam: only the frozen binding may choose the model
# ---------------------------------------------------------------------------

def test_17_18_no_override_can_replace_the_frozen_writer_model(
    storage, settings, account, monkeypatch,
):
    """Neither a route override nor an environment model may reroute a run."""
    from tests.controlled_provider_fixtures import seed_active_article_writer

    monkeypatch.setenv("ANTHROPIC_MODEL_QUALITY", "claude-opus-5")
    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare(storage, account, suffix="override")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )
    writer = ProvenanceFakeWriter()
    summary = _run(
        storage, settings, lease, owner, writer,
        route_override=__import__(
            "app.content.contracts", fromlist=["RouteContract"],
        ).RouteContract(
            content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
            logical_model_name="FABLE", config_version="hand-written",
            config_fingerprint="c" * 64, provider="attacker",
            api_model_id="attacker-model", availability="CONFIGURED",
            pricing_profile="attacker-pricing",
        ),
    )
    assert writer.calls == 0
    assert summary.block_code == (
        "CONTENT_CONTROLLED_PROVIDER_ROUTE_OVERRIDE_FORBIDDEN"
    )

    # Without the override the same environment variable changes nothing.
    request2, lease2, owner2 = _prepare(storage, account, suffix="override2")
    approve_content_provider_execution(
        storage, job_id=request2.job_id, model=model, account_id=account.id,
    )
    writer2 = ProvenanceFakeWriter()
    _run(storage, settings, lease2, owner2, writer2)
    assert writer2.seen_models == [model.technical_model_id]


def test_07b_a_paid_attempt_without_an_approval_never_reaches_the_writer(
    storage, settings, account,
):
    from tests.controlled_provider_fixtures import seed_active_article_writer

    seed_active_article_writer(storage)
    request, lease, owner = _prepare(storage, account, suffix="noapproval")
    writer = ProvenanceFakeWriter()
    with pytest.raises(ContentFoundationError) as excinfo:
        _run(storage, settings, lease, owner, writer)
    assert "CONTENT_APPROVAL_MISSING" in str(excinfo.value)
    assert writer.calls == 0


def test_10_an_approval_for_another_model_blocks_the_writer(
    storage, settings, account,
):
    from tests.controlled_provider_fixtures import seed_active_article_writer, seed_model

    model = seed_active_article_writer(storage)
    other = seed_model(storage, version="9", pricing_ref="price-other-v1")
    request, lease, owner = _prepare(storage, account, suffix="othermodel")
    storage.conn.execute(
        "UPDATE model_registry SET lifecycle_state='ACTIVE',"
        "current_qualification_state='PASS' WHERE registry_id=?",
        (other.registry_id,),
    )
    storage.conn.commit()
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=other, account_id=account.id,
    )
    writer = ProvenanceFakeWriter()
    with pytest.raises(ContentFoundationError) as excinfo:
        _run(storage, settings, lease, owner, writer)
    assert "CONTENT_APPROVAL_TARGET_MISMATCH" in str(excinfo.value)
    assert writer.calls == 0
    assert model.technical_model_id != other.technical_model_id


def test_08b_an_expired_content_approval_blocks_the_writer(
    storage, settings, account,
):
    from tests.controlled_provider_fixtures import seed_active_article_writer

    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare(storage, account, suffix="expiredapproval")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
        approved_at="2026-01-01T00:00:00.000000+00:00",
        expires_at="2026-01-02T00:00:00.000000+00:00",
    )
    writer = ProvenanceFakeWriter()
    with pytest.raises(ContentFoundationError) as excinfo:
        _run(storage, settings, lease, owner, writer)
    assert "CONTENT_APPROVAL_EXPIRED" in str(excinfo.value)
    assert writer.calls == 0


# ---------------------------------------------------------------------------
# Positive offline flow
# ---------------------------------------------------------------------------

def test_20_positive_full_article_flow_offline(catalogue_storage, settings, account):
    """catalogue -> qualification -> activation -> approval -> plan/writer/review."""
    storage = catalogue_storage
    activated = _activate_article_roles(storage)
    writer_model = _seeded(activated[LogicalModelRole.ARTICLE_WRITER])
    assert writer_model.technical_model_id == "claude-fable-5"

    request, lease, owner = _prepare(storage, account, suffix="fullflow")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=writer_model,
        account_id=account.id,
    )

    # The pipeline opens the durable run first; ARTICLE_PLAN then executes
    # inside that run, exactly as a real C5 execution would order it.
    run_id = f"content-run:{request.job_id}"
    storage.initialize_content_run_for_job(
        request.job_id, owner, lease.job.execution_generation, run_id,
        clock=FixedClock(NOW),
    )

    # ARTICLE_PLAN on Opus 5, frozen and settled from its own profile.
    storage.freeze_content_role_model_binding(
        job_id=request.job_id, role=LogicalModelRole.ARTICLE_PLAN,
    )
    plan_authority = _ready(
        storage, request.job_id, LogicalModelRole.ARTICLE_PLAN,
    )
    assert plan_authority.technical_model_id == "claude-opus-5"
    content_id = int(storage.conn.execute(
        "SELECT id FROM content_items WHERE job_id=?", (request.job_id,),
    ).fetchone()[0])
    plan_execution = evaluate_role_response(
        authority=plan_authority, run_id=run_id, content_id=content_id,
        response=RoleProviderResponse(
            returned_model_id="claude-opus-5",
            payload={"angle": "hidden mechanism", "structure": ["a", "b"]},
            usage=RoleUsage(input_tokens=3000, output_tokens=500),
        ),
    )
    storage.record_role_provider_execution(plan_execution)
    assert plan_execution.outcome == "SUCCESS"

    # ARTICLE_WRITER on Fable 5, through the existing durable pipeline.
    fake_writer = CatalogueFakeWriter()
    summary = _run(storage, settings, lease, owner, fake_writer)
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert fake_writer.seen_models == ["claude-fable-5"]

    # ARTICLE_REVIEWER on Opus 5, independent of the writer.
    storage.freeze_content_role_model_binding(
        job_id=request.job_id, role=LogicalModelRole.ARTICLE_REVIEWER,
    )
    review_authority = _ready(
        storage, request.job_id, LogicalModelRole.ARTICLE_REVIEWER,
    )
    review_execution = evaluate_role_response(
        authority=review_authority, run_id=run_id, content_id=content_id,
        response=RoleProviderResponse(
            returned_model_id="claude-opus-5",
            payload={"verdict": "PASS", "findings": []},
            usage=RoleUsage(input_tokens=4000, output_tokens=300),
        ),
    )
    storage.record_role_provider_execution(review_execution)
    assert review_authority.technical_model_id == "claude-opus-5"
    assert review_execution.outcome == "SUCCESS"

    # Every paid step settled from its own frozen authority.
    settled = storage.conn.execute(
        "SELECT cost_usd FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchall()
    assert len(settled) == 1
    roles = storage.conn.execute(
        "SELECT logical_role,technical_model_id,cost_usd,outcome "
        "FROM role_provider_executions WHERE job_id=? ORDER BY logical_role",
        (request.job_id,),
    ).fetchall()
    assert [r["logical_role"] for r in roles] == [
        "ARTICLE_PLAN", "ARTICLE_REVIEWER",
    ]
    assert {r["technical_model_id"] for r in roles} == {"claude-opus-5"}
    assert {r["outcome"] for r in roles} == {"SUCCESS"}

    # The approval was consumed exactly once and cannot authorise anything else.
    approval_row = storage.conn.execute(
        "SELECT consumed_at,purpose FROM content_provider_approvals WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    assert approval_row["consumed_at"] is not None
    assert approval_row["purpose"] == "CONTROLLED_ARTICLE_EXECUTION"

    # Two controlled qualifications, not three: ARTICLE_PLAN and
    # ARTICLE_REVIEWER share one Opus registry entry, and a model is qualified
    # once rather than once per role that happens to use it.
    runs = storage.conn.execute(
        "SELECT technical_model_id,outcome FROM model_qualification_runs "
        "ORDER BY technical_model_id"
    ).fetchall()
    assert [(r["technical_model_id"], r["outcome"]) for r in runs] == [
        ("claude-fable-5", "PASS"), ("claude-opus-5", "PASS"),
    ]
    assert storage.conn.execute(
        "SELECT count(*) FROM model_qualification_results WHERE source='CONTROLLED_LIVE'"
    ).fetchone()[0] == 2


# ---------------------------------------------------------------------------
# Cost estimate, migration, inertness
# ---------------------------------------------------------------------------

def test_16b_worst_case_cost_is_derived_from_real_limits_and_rates():
    estimate = estimate_controlled_article_cost(at=BEFORE_PROMO_END)
    # Fable 5: 8000 in @10 + 2048 out @50 = 0.08 + 0.1024 = 0.1824 per attempt
    assert estimate.writer.total_usd == Decimal("0.182400")
    assert estimate.writer.attempts == 2
    assert estimate.writer.worst_case_usd == Decimal("0.364800")
    # Opus 5: 8000 in @5 + 1024 out @25 = 0.04 + 0.0256 = 0.0656
    assert estimate.plan.total_usd == Decimal("0.065600")
    assert estimate.reviewer.total_usd == Decimal("0.065600")
    # A probe may declare the whole window: Opus 14976 in + 1024 out twice,
    # plus Fable 13952 in + 2048 out once.
    assert estimate.qualification[0].total_usd == Decimal("0.100480")
    assert estimate.qualification[1].total_usd == Decimal("0.241920")
    assert estimate.qualification_total_usd == Decimal("0.442880")
    assert estimate.execution_total_usd == Decimal("0.496000")
    assert estimate.total_usd == Decimal("0.938880")
    assert all(
        item.technical_model_id in {"claude-opus-5", "claude-fable-5"}
        for item in estimate.qualification
    )


def test_sonnet_role_estimate_switches_profile_at_the_expiry_boundary():
    before = estimate_role_cost(
        LogicalModelRole.ARTICLE_WRITER, at=BEFORE_PROMO_END,
    )
    assert before.pricing_ref.startswith("anthropic-fable-5")
    # Sonnet's own promotional window is the one that moves.
    promo = [p for p in SONNET_5.pricing if p.effective_until][0]
    standard = [p for p in SONNET_5.pricing if p.effective_from][0]
    assert promo.is_effective_at(BEFORE_PROMO_END) is True
    assert promo.is_effective_at(AFTER_PROMO_END) is False
    assert standard.is_effective_at(BEFORE_PROMO_END) is False
    assert standard.is_effective_at(AFTER_PROMO_END) is True
    assert promo.prices.input_per_mtok == Decimal("2.000000")
    assert standard.prices.input_per_mtok == Decimal("3.000000")


def test_migration_0029_is_forward_only_explicit_and_idempotent(tmp_path, capsys):
    import scripts.migrate_schema_0029 as cli

    assert RUNTIME_SCHEMA_VERSION != VERIFIED_CATALOGUE_SCHEMA_VERSION
    path = tmp_path / "upgrade-0029.db"
    initialize_database(
        path, through=CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    )
    assert cli.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == (
        CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION
    )
    result = migrate_0028_to_0029(path)
    assert result.applied_migrations == (VERIFIED_CATALOGUE_SCHEMA_VERSION,)
    assert migrate_0028_to_0029(path).idempotent is True
    assert cli.main(["--db-path", str(path), "--confirm-0028-to-0029"]) == 0
    assert "idempotent=true" in capsys.readouterr().out

    provider_contract = migrate_0029_to_0030(path)
    assert provider_contract.applied_migrations == (
        ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,
    )

    opened = SqliteStorage.open(path)
    try:
        assert opened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert opened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        triggers = {
            row[0] for row in opened.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        # New floors plus every rebuilt dependent trigger.
        assert {
            "model_intent_bindings_pricing_validity",
            "model_catalogue_evidence_contract",
            "model_qualification_approvals_contract",
            "model_qualification_runs_reserve_contract",
            "model_qualification_runs_settle_once",
            "model_qualification_runs_settle_envelope",
            "model_capability_declarations_real_model_needs_controlled_run",
            "content_provider_approvals_contract",
            "role_provider_executions_contract",
            "model_qualification_results_real_model_needs_controlled_run",
            "model_registry_current_evidence_contract",
            "model_role_activations_contract_insert",
            "model_role_activations_contract_update",
            "content_writer_intents_controlled_provider_binding",
        } <= triggers
    finally:
        opened.close()


def test_offline_modes_remain_registry_free_and_free_of_charge(
    storage, settings, account,
):
    from app.content.writer import FakeContentWriter

    request, lease, owner = _prepare(
        storage, account, suffix="stilloffline",
        mode=ContentExecutionMode.OFFLINE_PIPELINE,
    )
    summary = _run(storage, settings, lease, owner, FakeContentWriter())
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.cost_usd == pytest.approx(0.0)
    for table in (
        "model_intent_bindings", "content_provider_approvals",
        "role_provider_executions", "model_qualification_runs",
        "content_provider_cost_settlements",
    ):
        assert storage.conn.execute(
            f"SELECT count(*) FROM {table}"
        ).fetchone()[0] == 0


def test_real_article_composition_root_is_still_unreachable():
    """The seam exists; the supported root still refuses a real ARTICLE call."""
    from app.content.routing import (
        RealContentWriterUnavailable,
        resolve_real_content_writer,
    )
    from app.content.contracts import RouteContract

    route = RouteContract(
        content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
        logical_model_name="FABLE", config_version="v", config_fingerprint="a" * 64,
        provider="ANTHROPIC", api_model_id="claude-fable-5",
        availability="CONFIGURED", pricing_profile="anthropic-fable-5-standard-2026-08",
        logical_version="5", model_registry_id="m", qualification_ref="q",
        capability_ref="c",
    )
    with pytest.raises(RealContentWriterUnavailable):
        resolve_real_content_writer(route)
    assert FABLE_5.technical_model_id == "claude-fable-5"
    assert OPUS_5.technical_model_id == "claude-opus-5"
