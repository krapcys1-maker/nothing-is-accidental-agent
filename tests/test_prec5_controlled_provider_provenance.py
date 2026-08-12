"""PRE-C5: CONTROLLED PROVIDER PROVENANCE & PRICING AUTHORITY.

Every test here is offline.  Fake registry data, fake writers, synthetic token
counts, temporary SQLite databases only.  No network, no SDK, no real provider,
no real model ID, no real price, no production database.

What this file has to prove is narrow and adversarial: that a paid content
attempt cannot happen unless a durable registry binding was frozen for exactly
this execution, that nothing between freeze and settlement may substitute a
different model or a different price list, and that the technical caller is
genuinely unreachable when any of that is missing.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from app.content.contracts import (
    RouteContract,
    WriterCallMode,
    WriterLimits,
    WriterSuccess,
    WriterUsage,
)
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline
from app.content.provenance import (
    CONTENT_WRITER_INTENT_KIND,
    ControlledProviderProvenanceError,
    assert_controlled_provider_binding_ready,
    content_writer_binding_intent_id,
)
from app.content.routing import route_from_frozen_model_binding
from app.content.writer import FakeContentWriter
from app.core.clock import FixedClock
from app.model_routing import (
    LogicalModelRole,
    ModelFamily,
    PricingVerificationState,
    QualificationState,
    RoutingError,
)
from app.policies.policy_engine import PolicyEngine
from app.storage.db import (
    CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    canonical_migration_versions,
    database_schema_versions,
    initialize_database,
    migrate_0027_to_0028,
)
from app.storage.repositories import SqliteStorage
from tests.c2_fixtures import seed_c2_research
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    ground_every_segment_in_package,
)
from tests.controlled_provider_fixtures import (
    approve_content_provider_execution,
    seed_active_article_writer,
    seed_model,
    seed_role_policy,
)
from tests.test_e3_evidence_research import NOW


ROOT = Path(__file__).resolve().parents[1]
# 1200 input at 2/Mtok (0.002400) + 800 output at 7/Mtok (0.005600)
# + 400 cache-read at 0.5/Mtok (0.000200) + 200 cache-write at 1.25/Mtok
# (0.000250), all from the fake frozen profile.
EXPECTED_COST = Decimal("0.008450")


def test_writer_limits_accept_five_minute_timeout_and_reject_longer():
    limits = WriterLimits(
        max_input_tokens=8_000,
        max_context_tokens=16_000,
        max_output_tokens=2_048,
        max_cost_usd=0.05,
        timeout_seconds=300.0,
    )
    assert limits.timeout_seconds == 300.0
    with pytest.raises(ValueError):
        WriterLimits(
            max_input_tokens=8_000,
            max_context_tokens=16_000,
            max_output_tokens=2_048,
            max_cost_usd=0.05,
            timeout_seconds=300.001,
        )


# ---------------------------------------------------------------------------
# Shared paid-execution harness
# ---------------------------------------------------------------------------

class ProvenanceFakeWriter:
    """A CONTROLLED_PROVIDER caller that reports tokens and never a price."""

    call_mode = WriterCallMode.CONTROLLED_PROVIDER

    def __init__(self, *, self_reported_cost: float = 0.0, max_output_tokens=2_048):
        self.self_reported_cost = self_reported_cost
        self.max_output_tokens = max_output_tokens
        self.calls = 0
        self.seen_models: list[str] = []
        self.seen_pricing_refs: list[str] = []

    def limits_for(self, content_type):
        return WriterLimits(
            max_input_tokens=8_000, max_context_tokens=16_000,
            max_output_tokens=self.max_output_tokens, max_cost_usd=0.05,
            timeout_seconds=5.0,
        )

    def preflight(self, _request):
        return None

    def write(self, request):
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
                cache_read_tokens=400, cache_write_tokens=200,
                estimated_cost_usd=self.self_reported_cost,
            ),
            stop_reason="end_turn",
            provider_request_id="fake-provenance-request",
        )


def _prepare(storage, account, *, suffix, mode=None, lease_seconds=300):
    seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id=f"prov-{suffix}", idempotency_key=f"prov-{suffix}",
        account_id=account.id,
        research_card_id=int(
            storage.conn.execute(
                "SELECT MAX(id) FROM research_cards"
            ).fetchone()[0]
        ),
        content_type=ContentType.ARTICLE,
        execution_mode=mode or ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="ARTICLE_STYLE_PROFILE_V1",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"prov-owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, lease_seconds, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, lease, owner


def _run(storage, settings, lease, owner, writer, *, clock=None, **kwargs):
    resolved = clock or FixedClock(NOW)
    return run_offline_content_pipeline(
        lease.job, storage=storage, clock=resolved, lease_owner=owner,
        project_root=ROOT, policy=PolicyEngine(settings, storage, resolved),
        writer=writer, lease_seconds=600,
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
        **kwargs,
    )


def _run_paid(storage, settings, account, *, suffix, writer, seed=True,
              approve=True, **kwargs):
    model = seed_active_article_writer(storage) if seed else None
    request, lease, owner = _prepare(storage, account, suffix=suffix)
    if approve:
        model = model or _active_article_model(storage)
        if model is not None:
            approve_content_provider_execution(
                storage, job_id=request.job_id, model=model,
                account_id=account.id,
            )
    summary = _run(storage, settings, lease, owner, writer, **kwargs)
    return request, summary


def _active_article_model(storage):
    """The currently promoted ARTICLE_WRITER entry, as a fixture record."""
    from tests.controlled_provider_fixtures import SeededModel

    row = storage.conn.execute(
        "SELECT m.* FROM model_role_activations a "
        "JOIN model_registry m ON m.registry_id=a.model_registry_id "
        "WHERE a.role='ARTICLE_WRITER'",
    ).fetchone()
    if row is None:
        return None
    return SeededModel(
        registry_id=str(row["registry_id"]), provider=str(row["provider"]),
        family=ModelFamily(str(row["family"])),
        logical_version=str(row["logical_version"]),
        technical_model_id=str(row["technical_model_id"]),
        pricing_ref=str(row["pricing_ref"]),
        capability_ref=str(row["current_capability_ref"]),
        qualification_ref=str(row["current_qualification_ref"]),
    )


def _binding(storage, job_id):
    return storage.get_frozen_model_binding(
        intent_kind=CONTENT_WRITER_INTENT_KIND,
        intent_id=content_writer_binding_intent_id(job_id),
    )


def _intent_from_binding(storage, binding, *, job_id="prov-unit", attempt_no=1):
    """Build a durable-shaped paid intent from one frozen binding."""
    from app.content.contracts import WriterIntent

    route = route_from_frozen_model_binding(
        binding, content_type=ContentType.ARTICLE,
    )
    return WriterIntent(
        intent_id=f"{job_id}:writer:{attempt_no}",
        job_id=job_id, run_id=f"{job_id}-run", content_id=1,
        account_id="nothing_is_accidental", content_type=ContentType.ARTICLE,
        attempt_no=attempt_no, call_mode=WriterCallMode.CONTROLLED_PROVIDER,
        route=route,
        plan_fingerprint="1" * 64, brief_sha256="2" * 64,
        frozen_input_sha256="3" * 64, evidence_manifest_sha256="4" * 64,
        style_profile_id="ARTICLE_STYLE_PROFILE_V1",
        negative_style_profile_id="ARTICLE_NEGATIVE_STYLE_PROFILE_V1",
        prompt_fingerprint="5" * 64,
        limits=WriterLimits(
            max_input_tokens=8_000, max_context_tokens=16_000,
            max_output_tokens=2_048, max_cost_usd=0.05, timeout_seconds=5.0,
        ),
    )


@pytest.fixture
def routing_storage(tmp_path):
    path = tmp_path / "provenance.db"
    initialize_database(path)
    value = SqliteStorage.open(path)
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def frozen(routing_storage):
    """One promoted fake model with a binding frozen for one fake job."""
    model = seed_active_article_writer(routing_storage)
    binding = routing_storage.freeze_content_writer_model_binding(
        job_id="prov-unit", content_type=ContentType.ARTICLE,
    )
    return model, binding


def _provenance(storage, binding, **overrides):
    loaded = storage.load_controlled_provider_provenance(
        job_id=binding.intent_id.rsplit(":", 1)[0]
    )
    assert loaded is not None
    return replace(loaded, **overrides) if overrides else loaded


# ---------------------------------------------------------------------------
# 1-16 — the gate refuses every incomplete or contradictory provenance
# ---------------------------------------------------------------------------

def test_01_controlled_provider_without_a_frozen_binding_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, None)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_BINDING_MISSING"


def test_02_route_without_registry_id_cannot_even_be_constructed(frozen, routing_storage):
    """The four provenance fields are all-or-nothing on the route itself."""
    _, binding = frozen
    with pytest.raises(ValueError, match="complete provenance"):
        RouteContract(
            content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
            logical_model_name="FABLE", config_version="v1",
            config_fingerprint="a" * 64, provider=binding.provider,
            api_model_id=binding.technical_model_id, availability="CONFIGURED",
            pricing_profile=binding.pricing_ref,
            logical_version=binding.logical_version,
            qualification_ref=binding.qualification_ref,
            capability_ref=binding.capability_ref,
        )


def test_02b_paid_intent_without_any_registry_provenance_is_blocked():
    """A merely 'configured' paid route no longer validates at all."""
    from app.content.contracts import WriterIntent

    route = RouteContract(
        content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
        logical_model_name="FABLE", config_version="v1",
        config_fingerprint="a" * 64, provider="fake-provider",
        api_model_id="fake-model", availability="CONFIGURED",
        pricing_profile="fake-pricing",
    )
    assert route.is_provider_configured is True
    assert route.is_registry_qualified is False
    with pytest.raises(ValueError, match="registry provenance"):
        WriterIntent(
            intent_id="x:writer:1", job_id="x", run_id="r", content_id=1,
            account_id="a", content_type=ContentType.ARTICLE, attempt_no=1,
            call_mode=WriterCallMode.CONTROLLED_PROVIDER, route=route,
            plan_fingerprint="1" * 64, brief_sha256="2" * 64,
            frozen_input_sha256="3" * 64, evidence_manifest_sha256="4" * 64,
            style_profile_id="s", negative_style_profile_id="n",
            prompt_fingerprint="5" * 64,
            limits=WriterLimits(
                max_input_tokens=10, max_context_tokens=10,
                max_output_tokens=10, max_cost_usd=0.01, timeout_seconds=1.0,
            ),
        )


def test_03_unknown_registry_entry_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    other = seed_model(routing_storage, version="9", family=ModelFamily.OPUS)
    loaded = _provenance(routing_storage, binding)
    stranger = routing_storage.conn.execute(
        "SELECT * FROM model_registry WHERE registry_id=?", (other.registry_id,),
    ).fetchone()
    swapped = replace(
        loaded, model=SqliteStorage._registered_model_from_row(stranger),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, swapped)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_REGISTRY_ENTRY_UNKNOWN"


def test_04_wrong_role_is_blocked(routing_storage):
    seed_role_policy(routing_storage, LogicalModelRole.NOTE_WRITER)
    seed_model(routing_storage, version="1", family=ModelFamily.SONNET)
    routing_storage.promote_best_model(
        LogicalModelRole.NOTE_WRITER, reason="fake note pass",
    )
    note_binding = routing_storage.freeze_model_for_intent(
        LogicalModelRole.NOTE_WRITER,
        intent_kind=CONTENT_WRITER_INTENT_KIND,
        intent_id=content_writer_binding_intent_id("prov-unit"),
    )
    # The route builder refuses before anything else can consume it.
    with pytest.raises(Exception, match="wrong content role"):
        route_from_frozen_model_binding(
            note_binding, content_type=ContentType.ARTICLE,
        )


def test_05_wrong_family_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding)
    mismatched = replace(
        provenance, binding=replace(binding, family=ModelFamily.SONNET),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, mismatched)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_FAMILY_MISMATCH"


def test_06_wrong_logical_version_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding)
    drifted = replace(provenance, binding=replace(binding, logical_version="99"))
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, drifted)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_LOGICAL_VERSION_MISMATCH"


def test_07_wrong_provider_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding)
    drifted = replace(
        provenance, binding=replace(binding, provider="other-fake-provider"),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, drifted)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_PROVIDER_MISMATCH"


def test_08_wrong_api_model_id_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding)
    drifted = replace(
        provenance,
        binding=replace(binding, technical_model_id="fake-some-other-model"),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, drifted)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_API_MODEL_ID_MISMATCH"


def test_09_missing_pricing_profile_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding, pricing=None)
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, provenance)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_PRICING_MISSING"


def test_10_a_different_pricing_reference_is_blocked(frozen, routing_storage):
    """Same numbers, different identity: still the wrong authority."""
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    twin = seed_model(
        routing_storage, version="2", pricing_ref="price-identical-numbers",
    )
    other_profile = routing_storage.conn.execute(
        "SELECT * FROM model_pricing_profiles WHERE pricing_ref=?",
        (twin.pricing_ref,),
    ).fetchone()
    provenance = _provenance(
        routing_storage, binding,
        pricing=SqliteStorage._model_pricing_from_row(other_profile),
    )
    assert provenance.pricing is not None
    assert (
        provenance.pricing.prices == _provenance(
            routing_storage, binding,
        ).pricing.prices
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, provenance)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_PRICING_REF_MISMATCH"


def test_11_unverified_pricing_is_blocked(routing_storage):
    seed_role_policy(routing_storage)
    model = seed_model(
        routing_storage, version="1",
        price_state=PricingVerificationState.UNVERIFIED,
    )
    # Promotion itself already refuses an unverified price list.
    outcome = routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="unverified pricing",
    )
    assert outcome.status.value == "BLOCKED"
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
        routing_storage.freeze_content_writer_model_binding(
            job_id="prov-unit", content_type=ContentType.ARTICLE,
        )
    assert model.pricing_ref


def test_12_unqualified_model_cannot_be_frozen(routing_storage):
    seed_role_policy(routing_storage)
    seed_model(
        routing_storage, version="1", qualification=QualificationState.UNQUALIFIED,
    )
    assert routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="unqualified",
    ).status.value == "BLOCKED"
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
        routing_storage.freeze_content_writer_model_binding(
            job_id="prov-unit", content_type=ContentType.ARTICLE,
        )


def test_13_failed_qualification_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding)
    assert provenance.qualification is not None
    failed = replace(
        provenance,
        qualification=replace(
            provenance.qualification, state=QualificationState.FAIL,
        ),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, failed)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_QUALIFICATION_NOT_PASS"


def test_14_qualification_of_another_model_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    stranger = seed_model(routing_storage, version="3")
    provenance = _provenance(routing_storage, binding)
    assert provenance.qualification is not None
    borrowed = replace(
        provenance,
        qualification=replace(
            provenance.qualification,
            qualification_ref=stranger.qualification_ref,
        ),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, borrowed)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_QUALIFICATION_REF_MISMATCH"


def test_15_missing_capability_declaration_is_blocked(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    provenance = _provenance(routing_storage, binding, capability=None)
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, provenance)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_CAPABILITY_MISSING"


def test_16_capability_of_another_model_and_envelope_mismatch_are_blocked(
    frozen, routing_storage,
):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    stranger = seed_model(routing_storage, version="4")
    provenance = _provenance(routing_storage, binding)
    assert provenance.capability is not None
    borrowed = replace(
        provenance,
        capability=replace(
            provenance.capability, capability_ref=stranger.capability_ref,
        ),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, borrowed)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_CAPABILITY_REF_MISMATCH"

    tiny = replace(
        provenance,
        capability=replace(provenance.capability, max_output_tokens=8),
    )
    with pytest.raises(ControlledProviderProvenanceError) as excinfo:
        assert_controlled_provider_binding_ready(intent, tiny)
    assert excinfo.value.code == "CONTROLLED_PROVIDER_CAPABILITY_ENVELOPE_EXCEEDED"


# ---------------------------------------------------------------------------
# 17-18 — reachability of the technical caller
# ---------------------------------------------------------------------------

def test_17_blocked_provenance_never_reaches_the_provider_caller(
    storage, settings, account,
):
    """No registry at all: the paid pipeline stops before any writer call."""
    writer = ProvenanceFakeWriter()
    request, summary = _run_paid(
        storage, settings, account, suffix="no-registry", writer=writer,
        seed=False,
    )
    assert writer.calls == 0
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == "ACTIVE_MODEL_MISSING"
    assert storage.conn.execute(
        "SELECT count(*) FROM content_writer_intents WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0


def test_17b_capability_envelope_gap_blocks_before_the_caller(
    storage, settings, account,
):
    """A registry exists, but this attempt exceeds the frozen envelope."""
    seed_role_policy(storage)
    seed_model(storage, version="1", max_output_tokens=1_024)
    storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="small envelope",
    )
    writer = ProvenanceFakeWriter(max_output_tokens=4_096)
    _, summary = _run_paid(
        storage, settings, account, suffix="envelope", writer=writer, seed=False,
    )
    assert writer.calls == 0
    assert summary.block_code == "CONTROLLED_PROVIDER_CAPABILITY_ENVELOPE_EXCEEDED"


def test_18_valid_frozen_binding_makes_the_caller_reachable(
    storage, settings, account,
):
    model = seed_active_article_writer(storage)
    writer = ProvenanceFakeWriter()
    request, summary = _run_paid(
        storage, settings, account, suffix="reachable", writer=writer, seed=False,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert writer.calls == 1
    # The caller was handed exactly the frozen technical identity.
    assert writer.seen_models == [model.technical_model_id]
    assert writer.seen_pricing_refs == [model.pricing_ref]
    binding = _binding(storage, request.job_id)
    assert binding is not None
    assert binding.model_registry_id == model.registry_id


# ---------------------------------------------------------------------------
# 19-22 — the frozen binding survives promotion, repricing and restart
# ---------------------------------------------------------------------------

def test_19_promotion_after_freeze_does_not_change_the_existing_intent(
    routing_storage,
):
    old = seed_active_article_writer(routing_storage, version="1")
    binding = routing_storage.freeze_content_writer_model_binding(
        job_id="prov-unit", content_type=ContentType.ARTICLE,
    )
    new = seed_model(routing_storage, version="2", pricing_ref="price-fable-2-v1")
    promotion = routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="n+1 qualified",
    )
    assert promotion.new_model_registry_id == new.registry_id
    again = routing_storage.freeze_content_writer_model_binding(
        job_id="prov-unit", content_type=ContentType.ARTICLE,
    )
    assert again == binding
    assert again.model_registry_id == old.registry_id
    assert again.technical_model_id == old.technical_model_id
    assert again.pricing_ref == old.pricing_ref


def test_20_pricing_change_after_freeze_does_not_change_the_existing_intent(
    routing_storage, frozen,
):
    """A new price is a new pricing_ref; the frozen ref keeps its numbers."""
    model, binding = frozen
    provenance = _provenance(routing_storage, binding)
    assert provenance.pricing is not None
    before = provenance.pricing.prices

    # The append-only profile table makes in-place repricing impossible.
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        routing_storage.conn.execute(
            "UPDATE model_pricing_profiles SET input_per_mtok='999.000000' "
            "WHERE pricing_ref=?", (model.pricing_ref,),
        )
    routing_storage.conn.rollback()

    seed_model(
        routing_storage, version="2", pricing_ref="price-repriced-v1",
        price_overrides={"input_per_mtok": "40"},
    )
    routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="repriced n+1",
    )
    after = _provenance(routing_storage, binding)
    assert after.pricing is not None
    assert after.pricing.pricing_ref == model.pricing_ref
    assert after.pricing.prices == before


def test_21_a_new_intent_after_promotion_receives_the_new_active_selection(
    routing_storage,
):
    old = seed_active_article_writer(routing_storage, version="1")
    first = routing_storage.freeze_content_writer_model_binding(
        job_id="job-old", content_type=ContentType.ARTICLE,
    )
    new = seed_model(routing_storage, version="2", pricing_ref="price-fable-2-v1")
    routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="promote n+1",
    )
    second = routing_storage.freeze_content_writer_model_binding(
        job_id="job-new", content_type=ContentType.ARTICLE,
    )
    assert first.model_registry_id == old.registry_id
    assert second.model_registry_id == new.registry_id
    assert second.pricing_ref == new.pricing_ref
    assert first.pricing_ref != second.pricing_ref


def test_22_restart_and_rewrite_keep_the_same_model_and_pricing(
    storage, settings, account,
):
    """Both attempts of one execution read one binding, across a promotion."""
    old = seed_active_article_writer(storage, version="1")
    request, lease, owner = _prepare(storage, account, suffix="restart")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=old, account_id=account.id,
    )

    class RewriteThenPassWriter(ProvenanceFakeWriter):
        def write(self, request):
            result = super().write(request)
            if request.intent.attempt_no == 1:
                # Force a rewrite by returning a draft that fails the gate.
                weak = result.draft.model_copy(update={
                    "body": "A vague system did something important.",
                    "evidence_ids_used": (), "style_ok": False,
                    "brief_compliant": False,
                })
                return result.model_copy(update={"draft": weak})
            return result

    writer = RewriteThenPassWriter()
    # A promotion lands after the execution has already frozen its binding.
    storage.freeze_content_writer_model_binding(
        job_id=request.job_id, content_type=ContentType.ARTICLE,
    )
    seed_model(storage, version="2", pricing_ref="price-fable-2-v1")
    storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="mid-execution promotion",
    )
    _run(storage, settings, lease, owner, writer)

    assert writer.calls >= 1
    assert set(writer.seen_models) == {old.technical_model_id}
    assert set(writer.seen_pricing_refs) == {old.pricing_ref}
    persisted = storage.conn.execute(
        "SELECT DISTINCT api_model_id,pricing_profile FROM content_writer_intents "
        "WHERE job_id=?", (request.job_id,),
    ).fetchall()
    assert {(row[0], row[1]) for row in persisted} == {
        (old.technical_model_id, old.pricing_ref)
    }


# ---------------------------------------------------------------------------
# 23 — provider failure never reroutes
# ---------------------------------------------------------------------------

def test_23_provider_failure_never_selects_another_model(routing_storage, frozen):
    from app.model_routing import ModelRoutingService

    _, binding = frozen
    service = ModelRoutingService(routing_storage)
    with pytest.raises(RoutingError) as excinfo:
        service.runtime_failure(binding, error_code="PROVIDER_5XX")
    assert excinfo.value.code == "RUNTIME_FALLBACK_FORBIDDEN"

    seed_model(routing_storage, version="2", pricing_ref="price-fable-2-v1")
    routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="after failure",
    )
    unchanged = _binding(routing_storage, "prov-unit")
    assert unchanged == binding


def test_23b_paid_provider_failure_does_not_retry_on_another_model(
    storage, settings, account,
):
    from app.content.contracts import WriterFailure, WriterFailureKind

    model = seed_active_article_writer(storage)

    class FailingWriter(ProvenanceFakeWriter):
        def write(self, request):
            self.calls += 1
            route = request.intent.route
            self.seen_models.append(route.api_model_id)
            return WriterFailure(
                kind=WriterFailureKind.PROVIDER_5XX, provider=route.provider,
                route_key=route.route_key, api_model_id=route.api_model_id,
                usage=None, detail="fake 5xx", uncertain=False,
            )

    writer = FailingWriter()
    request, summary = _run_paid(
        storage, settings, account, suffix="failure", writer=writer, seed=False,
    )
    assert summary.status is ContentStatus.FAILED
    assert writer.seen_models == [model.technical_model_id]
    assert storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# 24 — the durable v3-shaped intent table refuses a contradictory binding
# ---------------------------------------------------------------------------

def test_24_intent_table_refuses_a_contradictory_binding(
    storage, settings, account,
):
    """SQL, not Python, is the last line: raw inserts are refused too."""
    seed_active_article_writer(storage)
    request, summary = _run_paid(
        storage, settings, account, suffix="sqlfloor",
        writer=ProvenanceFakeWriter(), seed=False,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    row = storage.conn.execute(
        "SELECT * FROM content_writer_intents WHERE job_id=? AND attempt_no=1",
        (request.job_id,),
    ).fetchone()
    columns = [key for key in row.keys()]
    values = {key: row[key] for key in columns}

    def _insert(**overrides):
        payload = dict(values)
        payload.update(overrides)
        payload["intent_id"] = f"{payload['intent_id']}-clone"
        payload["attempt_no"] = 2
        payload["intent_fingerprint"] = "f" * 64
        placeholders = ",".join("?" for _ in columns)
        storage.conn.execute(
            f"INSERT INTO content_writer_intents ({','.join(columns)}) "
            f"VALUES ({placeholders})",
            tuple(payload[key] for key in columns),
        )

    for overrides in (
        {"api_model_id": "fake-substituted-model"},
        {"provider": "other-fake-provider"},
        {"pricing_profile": "price-substituted-v1"},
    ):
        with pytest.raises(sqlite3.IntegrityError):
            _insert(**overrides)
        storage.conn.rollback()

    # The intent JSON must agree with the binding too, not just the columns.
    payload = json.loads(str(values["intent_json"]))
    payload["route"]["model_registry_id"] = "model-substituted"
    with pytest.raises(sqlite3.IntegrityError):
        _insert(intent_json=json.dumps(payload, sort_keys=True))
    storage.conn.rollback()


def test_24b_a_frozen_binding_can_never_be_removed_or_rewritten(
    storage, settings, account,
):
    """The binding a paid attempt depends on is append-only in SQL."""
    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare(storage, account, suffix="nobinding")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )
    summary = _run(storage, settings, lease, owner, ProvenanceFakeWriter())
    assert summary.status is ContentStatus.PENDING_APPROVAL
    binding_id = content_writer_binding_intent_id(request.job_id)
    assert storage.conn.execute(
        "SELECT count(*) FROM model_intent_bindings WHERE intent_id=?",
        (binding_id,),
    ).fetchone()[0] == 1

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "DELETE FROM model_intent_bindings WHERE intent_id=?", (binding_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE model_intent_bindings SET technical_model_id='swapped' "
            "WHERE intent_id=?", (binding_id,),
        )
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT count(*) FROM model_intent_bindings WHERE intent_id=?",
        (binding_id,),
    ).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# 25-27 — usage, settlement and a single pricing authority
# ---------------------------------------------------------------------------

def test_25_usage_identity_equals_the_frozen_binding_identity(
    storage, settings, account,
):
    model = seed_active_article_writer(storage)
    request, summary = _run_paid(
        storage, settings, account, suffix="usage-id",
        writer=ProvenanceFakeWriter(), seed=False,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    usage = storage.conn.execute(
        "SELECT provider,model,dry_run,estimated_cost_usd FROM model_usage "
        "WHERE run_id=?", (summary.run_id,),
    ).fetchall()
    assert len(usage) == 1
    assert usage[0]["provider"] == model.provider
    assert usage[0]["model"] == model.technical_model_id
    assert usage[0]["dry_run"] == 0


def test_26_settlement_pricing_identity_equals_the_frozen_pricing_identity(
    storage, settings, account,
):
    model = seed_active_article_writer(storage)
    request, summary = _run_paid(
        storage, settings, account, suffix="settle",
        writer=ProvenanceFakeWriter(), seed=False,
    )
    settlement = storage.conn.execute(
        "SELECT * FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    assert settlement is not None
    assert settlement["pricing_ref"] == model.pricing_ref
    assert settlement["model_registry_id"] == model.registry_id
    assert settlement["technical_model_id"] == model.technical_model_id
    assert settlement["qualification_ref"] == model.qualification_ref
    assert settlement["capability_ref"] == model.capability_ref
    assert settlement["currency"] == "USD"
    # The cost is the registry price list applied to the reported tokens.
    assert Decimal(str(settlement["cost_usd"])) == EXPECTED_COST
    assert summary.cost_usd == pytest.approx(float(EXPECTED_COST))
    profile = storage.conn.execute(
        "SELECT profile_fingerprint FROM model_pricing_profiles WHERE pricing_ref=?",
        (model.pricing_ref,),
    ).fetchone()
    assert settlement["pricing_profile_fingerprint"] == profile[0]


def test_27_a_second_pricing_authority_cannot_price_the_same_attempt(
    storage, settings, account,
):
    """The caller's own cost claim is refused rather than silently trusted."""
    seed_active_article_writer(storage)
    writer = ProvenanceFakeWriter(self_reported_cost=0.99)
    request, summary = _run_paid(
        storage, settings, account, suffix="two-authorities", writer=writer,
        seed=False,
    )
    assert writer.calls == 1
    assert summary.block_code == "CONTENT_PROVIDER_SELF_REPORTED_COST_FORBIDDEN"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_cost_settlements"
    ).fetchone()[0] == 0


def test_27b_paid_usage_without_a_settlement_is_refused_by_sql(
    storage, settings, account,
):
    """Booking a paid cost while skipping the settlement is a SQL failure."""
    from app.models import JobExecutionContext, JobKind, ModelUsage

    model = seed_active_article_writer(storage)
    request, lease, owner = _prepare(storage, account, suffix="nosettle")
    approve_content_provider_execution(
        storage, job_id=request.job_id, model=model, account_id=account.id,
    )

    def stop_after_start(name):
        if name == "WRITER_ATTEMPT_STARTED":
            raise RuntimeError("stop before the caller books usage")

    with pytest.raises(RuntimeError, match="stop before the caller"):
        _run(
            storage, settings, lease, owner, ProvenanceFakeWriter(),
            fault_point=stop_after_start,
        )
    attempt = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=?", (request.job_id,),
    ).fetchone()
    assert attempt["status"] == "REQUEST_STARTED"
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_cost_settlements"
    ).fetchone()[0] == 0

    binding = _binding(storage, request.job_id)
    assert binding is not None
    execution = JobExecutionContext(
        job_id=request.job_id, lease_owner=owner,
        run_id=f"content-run:{request.job_id}", clock=FixedClock(NOW),
        fence_token=lease.job.execution_generation, kind=JobKind.CONTENT,
        workflow=lease.job.workflow,
    )
    with pytest.raises(sqlite3.IntegrityError, match="frozen pricing settlement"):
        storage.add_job_model_usage(
            execution,
            ModelUsage(
                run_id=execution.run_id, provider=binding.provider,
                model=binding.technical_model_id, task="content_draft",
                input_tokens=1200, output_tokens=800,
                estimated_cost_usd=0.0084, dry_run=False,
                request_id=str(attempt["request_id"]),
            ),
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0


def test_27c_settlement_naming_another_profile_is_refused_by_sql(
    storage, settings, account,
):
    seed_active_article_writer(storage)
    request, summary = _run_paid(
        storage, settings, account, suffix="wrongprofile",
        writer=ProvenanceFakeWriter(), seed=False,
    )
    other = seed_model(storage, version="7", pricing_ref="price-elsewhere-v1")
    row = storage.conn.execute(
        "SELECT * FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    assert row is not None
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE content_provider_cost_settlements SET pricing_ref=? "
            "WHERE job_id=?", (other.pricing_ref, request.job_id),
        )
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT pricing_ref FROM content_provider_cost_settlements WHERE job_id=?",
        (request.job_id,),
    ).fetchone()[0] != other.pricing_ref


# ---------------------------------------------------------------------------
# 28 — concurrency and stale state never mix two models
# ---------------------------------------------------------------------------

def test_28_concurrent_freezes_of_one_execution_agree_on_one_binding(tmp_path):
    import threading

    path = tmp_path / "concurrent.db"
    initialize_database(path)
    setup = SqliteStorage.open(path)
    try:
        seed_active_article_writer(setup, version="1")
    finally:
        setup.close()

    results: list[object] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        local = SqliteStorage.open(path)
        try:
            barrier.wait(timeout=10)
            results.append(
                local.freeze_content_writer_model_binding(
                    job_id="shared-job", content_type=ContentType.ARTICLE,
                )
            )
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            local.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    assert len(results) == 4
    assert len({item.model_registry_id for item in results}) == 1
    assert len({item.pricing_ref for item in results}) == 1
    assert len({item.technical_model_id for item in results}) == 1


def test_28b_a_promotion_between_resolve_and_freeze_cannot_mix_identities(
    routing_storage,
):
    """One binding row is written atomically from one registry snapshot."""
    old = seed_active_article_writer(routing_storage, version="1")
    new = seed_model(routing_storage, version="2", pricing_ref="price-fable-2-v1")
    routing_storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="promote before freeze",
    )
    binding = routing_storage.freeze_content_writer_model_binding(
        job_id="mixed", content_type=ContentType.ARTICLE,
    )
    # Whatever it selected, every field belongs to the same registry entry.
    assert binding.model_registry_id == new.registry_id
    assert binding.technical_model_id == new.technical_model_id
    assert binding.pricing_ref == new.pricing_ref
    assert binding.pricing_ref != old.pricing_ref

    # And SQL refuses a hand-built mixed binding outright.
    with pytest.raises(sqlite3.IntegrityError, match="exact active qualified model"):
        routing_storage.conn.execute(
            "INSERT INTO model_intent_bindings (intent_kind,intent_id,role,"
            "model_registry_id,provider,family,logical_version,technical_model_id,"
            "pricing_ref,qualification_ref,capability_ref,"
            "activation_decision_fingerprint,fallback_policy,bound_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                CONTENT_WRITER_INTENT_KIND, "mixed-manual", "ARTICLE_WRITER",
                new.registry_id, new.provider, "FABLE", new.logical_version,
                new.technical_model_id,
                old.pricing_ref,  # the other model's price list
                new.qualification_ref, new.capability_ref,
                "0" * 64, "FORBIDDEN", "2026-08-09T10:00:00.000000+00:00",
            ),
        )
    routing_storage.conn.rollback()


# ---------------------------------------------------------------------------
# Migration and inertness
# ---------------------------------------------------------------------------

def test_migration_0028_is_forward_only_explicit_and_idempotent(tmp_path, capsys):
    import scripts.migrate_schema_0028 as cli

    assert CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION in canonical_migration_versions()
    path = tmp_path / "upgrade-0028.db"
    initialize_database(path, through=MODEL_FAMILY_ROUTING_SCHEMA_VERSION)
    assert database_schema_versions(path)[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION

    assert cli.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION

    result = migrate_0027_to_0028(path)
    assert result.applied_migrations == (
        CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    )
    assert migrate_0027_to_0028(path).idempotent is True
    assert cli.main(["--db-path", str(path), "--confirm-0027-to-0028"]) == 0
    assert "idempotent=true" in capsys.readouterr().out
    from app.storage.db import (
        migrate_0028_to_0029,
        migrate_0029_to_0030,
        migrate_0030_to_0031,
        migrate_0031_to_0032,
        migrate_0032_to_0033,
        migrate_0033_to_0034,
        migrate_0034_to_0035,
        migrate_0035_to_0036,
        migrate_0036_to_0037,
        migrate_0037_to_0038,
    )

    migrate_0028_to_0029(path)
    migrate_0029_to_0030(path)
    migrate_0030_to_0031(path)
    migrate_0031_to_0032(path)
    migrate_0032_to_0033(path)
    migrate_0033_to_0034(path)
    migrate_0034_to_0035(path)
    migrate_0035_to_0036(path)
    migrate_0036_to_0037(path)
    migrate_0037_to_0038(path)

    opened = SqliteStorage.open(path)
    try:
        assert opened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert opened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        triggers = {
            row[0] for row in opened.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert {
            "content_writer_intents_controlled_provider_binding",
            "content_writer_attempts_controlled_provider_binding",
            "content_provider_cost_settlements_contract",
            "model_usage_controlled_provider_settlement",
        } <= triggers
        # 0027's own contracts are untouched.
        assert {
            "content_writer_intents_stable_role_contract",
            "model_intent_bindings_contract",
        } <= triggers
        assert opened.conn.execute(
            "SELECT count(*) FROM content_provider_cost_settlements"
        ).fetchone()[0] == 0
    finally:
        opened.close()


def test_offline_content_modes_are_untouched_by_the_provenance_gate(
    storage, settings, account,
):
    """FAKE stays registry-free, costs nothing and needs no settlement."""
    request, lease, owner = _prepare(
        storage, account, suffix="offline",
        mode=ContentExecutionMode.OFFLINE_PIPELINE,
    )
    summary = _run(storage, settings, lease, owner, FakeContentWriter())
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.cost_usd == pytest.approx(0.0)
    assert storage.conn.execute(
        "SELECT count(*) FROM model_intent_bindings"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_cost_settlements"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0


def test_a_paid_execution_refuses_a_hand_written_route_override(
    storage, settings, account,
):
    """The legacy route key can never become a second source of a model."""
    seed_active_article_writer(storage)
    _, lease, owner = _prepare(storage, account, suffix="override")
    writer = ProvenanceFakeWriter()
    summary = _run(
        storage, settings, lease, owner, writer,
        route_override=RouteContract(
            content_type=ContentType.ARTICLE, route_key="FABLE_5_ARTICLE",
            logical_model_name="FABLE", config_version="hand-written",
            config_fingerprint="c" * 64, provider="attacker-provider",
            api_model_id="attacker-model", availability="CONFIGURED",
            pricing_profile="attacker-pricing",
        ),
    )
    assert writer.calls == 0
    assert summary.block_code == (
        "CONTENT_CONTROLLED_PROVIDER_ROUTE_OVERRIDE_FORBIDDEN"
    )


def test_real_provider_composition_root_stays_unavailable(frozen, routing_storage):
    """This wave prepares the seam; it does not open live access."""
    from app.content.routing import (
        RealContentWriterUnavailable,
        resolve_real_content_writer,
    )

    _, binding = frozen
    route = route_from_frozen_model_binding(
        binding, content_type=ContentType.ARTICLE,
    )
    assert route.is_registry_qualified is True
    with pytest.raises(RealContentWriterUnavailable):
        resolve_real_content_writer(route)


def test_settlement_arithmetic_is_decimal_end_to_end(frozen, routing_storage):
    _, binding = frozen
    intent = _intent_from_binding(routing_storage, binding)
    authority = assert_controlled_provider_binding_ready(
        intent, _provenance(routing_storage, binding),
    )
    cost = authority.settle(
        WriterUsage(
            input_tokens=1200, output_tokens=800,
            cache_read_tokens=400, cache_write_tokens=200,
        )
    )
    assert isinstance(cost, Decimal)
    assert cost == EXPECTED_COST
    # Every dimension is priced, including the ones a content attempt cannot use.
    with_search = authority.settle(
        WriterUsage(input_tokens=0, output_tokens=0), web_search_requests=250,
    )
    assert with_search == Decimal("1.000000")
    assert authority.settle(WriterUsage(input_tokens=0, output_tokens=0)) == (
        Decimal("0.000000")
    )
