from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading

import pytest

from app.content.contracts import RouteContract
from app.content.foundation import ContentType
from app.content.routing import route_from_frozen_model_binding
from app.model_routing import (
    AvailabilityState,
    CapabilityDeclaration,
    CapabilityVerificationState,
    CatalogueCandidate,
    LifecycleState,
    LogicalModelRole,
    ModelFamily,
    ModelPricingProfile,
    ModelRoutingService,
    ModelVersion,
    PriceDimensions,
    PricingVerificationState,
    PromotionStatus,
    QualificationReport,
    QualificationState,
    RolePolicy,
    RoutingAuditEventType,
    RoutingError,
)
from app.storage.db import (
    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    canonical_migration_versions,
    database_schema_versions,
    initialize_database,
    migrate_0026_to_0027,
)
from app.storage.repositories import SqliteStorage


TS = "2026-08-09T12:00:00.000000+00:00"
PRICE_KEYS = (
    "input_per_mtok",
    "output_per_mtok",
    "cache_read_per_mtok",
    "cache_write_per_mtok",
    "web_search_per_1k",
)


def _prices(value: str = "5") -> PriceDimensions:
    return PriceDimensions.from_mapping({key: value for key in PRICE_KEYS})


def _policy(
    storage: SqliteStorage,
    role: LogicalModelRole = LogicalModelRole.ARTICLE_WRITER,
    *,
    ceiling: PriceDimensions | None = None,
    structured: bool = True,
    context: int = 10_000,
    output: int = 2_000,
) -> RolePolicy:
    family = {
        LogicalModelRole.TOPIC_GENERATION: ModelFamily.SONNET,
        LogicalModelRole.ARTICLE_RESEARCH: ModelFamily.OPUS,
        LogicalModelRole.ARTICLE_PLAN: ModelFamily.OPUS,
        LogicalModelRole.ARTICLE_WRITER: ModelFamily.FABLE,
        LogicalModelRole.ARTICLE_REVIEWER: ModelFamily.OPUS,
        LogicalModelRole.NOTE_WRITER: ModelFamily.SONNET,
        LogicalModelRole.COMMENT_WRITER: ModelFamily.SONNET,
    }[role]
    policy = RolePolicy(
        role=role,
        allowed_family=family,
        policy_version="fake-policy-v1",
        capability_verification_state=CapabilityVerificationState.VERIFIED,
        require_structured_response=structured,
        min_context_tokens=context,
        min_output_tokens=output,
        pricing_verification_state=PricingVerificationState.VERIFIED,
        price_ceiling=ceiling or _prices("10"),
    )
    storage.upsert_model_role_policy(policy)
    return policy


def _candidate(
    storage: SqliteStorage,
    version: str,
    *,
    family: ModelFamily = ModelFamily.FABLE,
    provider: str = "fake-provider",
    technical_model_id: str | None = "__AUTO__",
    availability: AvailabilityState = AvailabilityState.AVAILABLE,
    price_state: PricingVerificationState = PricingVerificationState.VERIFIED,
    price_values: PriceDimensions | None = None,
    capability_state: CapabilityVerificationState = CapabilityVerificationState.VERIFIED,
    structured: bool = True,
    max_context: int = 20_000,
    max_output: int = 4_000,
    qualification: QualificationState = QualificationState.PASS,
) -> str:
    slug = f"{family.value.lower()}-{version.replace('.', '-') }"
    api_id = f"fake-{slug}" if technical_model_id == "__AUTO__" else technical_model_id
    pricing_ref = f"price-{provider}-{slug}" if api_id else None
    item = CatalogueCandidate(
        provider=provider,
        family=family,
        logical_version=version,
        technical_model_id=api_id,
        availability_state=availability,
        pricing_ref=pricing_ref,
        discovered_at=TS,
        catalogue_ref="fake-catalogue-v1",
    )
    model = storage.register_model_candidate(item)
    if pricing_ref is not None:
        storage.register_model_pricing_profile(
            ModelPricingProfile(
                pricing_ref=pricing_ref,
                provider=provider,
                technical_model_id=api_id,
                verification_state=price_state,
                currency="USD",
                unit="fake-usd-per-mtok",
                prices=(price_values or _prices())
                if price_state is PricingVerificationState.VERIFIED else None,
                verified_at=TS
                if price_state is PricingVerificationState.VERIFIED else None,
            )
        )
    storage.record_model_capabilities(
        model.registry_id,
        CapabilityDeclaration(
            capability_ref=f"caps-{provider}-{slug}-{capability_state.value.lower()}",
            verification_state=capability_state,
            structured_response=structured
            if capability_state is CapabilityVerificationState.VERIFIED else None,
            max_context_tokens=max_context
            if capability_state is CapabilityVerificationState.VERIFIED else None,
            max_output_tokens=max_output
            if capability_state is CapabilityVerificationState.VERIFIED else None,
            verified_at=TS
            if capability_state is CapabilityVerificationState.VERIFIED else None,
        ),
    )
    if qualification is not QualificationState.UNQUALIFIED:
        storage.record_model_qualification(
            QualificationReport(
                qualification_ref=f"qual-{provider}-{slug}-{qualification.value.lower()}",
                model_registry_id=model.registry_id,
                state=qualification,
                suite_version="fake-regression-suite-v1",
                fixture_set_ref="fake-fixtures-v1",
                result_payload={"outcome": qualification.value},
                evaluated_at=TS,
            )
        )
    return model.registry_id


@pytest.fixture
def storage(tmp_path: Path):
    path = tmp_path / "model-routing.db"
    initialize_database(path)
    value = SqliteStorage.open(path)
    try:
        yield value
    finally:
        value.close()


def test_model_version_order_is_numeric_not_naive_string_order():
    versions = [ModelVersion.parse(value) for value in ("5.2", "6", "5", "5.1")]
    assert [value.canonical for value in sorted(versions)] == ["5", "5.1", "5.2", "6"]
    assert ModelVersion.parse("5.0").canonical == "5"


@pytest.mark.parametrize("role,family", [
    (LogicalModelRole.TOPIC_GENERATION, ModelFamily.SONNET),
    (LogicalModelRole.ARTICLE_RESEARCH, ModelFamily.OPUS),
    (LogicalModelRole.ARTICLE_PLAN, ModelFamily.OPUS),
    (LogicalModelRole.ARTICLE_WRITER, ModelFamily.FABLE),
    (LogicalModelRole.ARTICLE_REVIEWER, ModelFamily.OPUS),
    (LogicalModelRole.NOTE_WRITER, ModelFamily.SONNET),
    (LogicalModelRole.COMMENT_WRITER, ModelFamily.SONNET),
])
def test_persisted_target_role_family_map_is_version_independent(storage, role, family):
    policy = storage.get_model_role_policy(role)
    assert policy is not None
    assert policy.allowed_family is family
    assert not any(character.isdigit() for character in role.value)
    assert policy.fallback_policy == "FORBIDDEN"
    assert policy.pricing_verification_state is PricingVerificationState.UNVERIFIED
    stored = storage.conn.execute(
        "SELECT policy_fingerprint FROM model_role_policies WHERE role=?",
        (role.value,),
    ).fetchone()[0]
    assert stored == policy.policy_fingerprint()


def test_unknown_role_and_family_block_fail_closed(storage):
    with pytest.raises(RoutingError, match="UNKNOWN_ROLE"):
        storage.promote_best_model("FABLE_5_ARTICLE", reason="must block")
    with pytest.raises(RoutingError, match="UNKNOWN_FAMILY"):
        storage.list_role_policies_for_family("MYSTERY")
    with pytest.raises(RoutingError, match="UNKNOWN_MODEL"):
        ModelRoutingService(storage).qualify_candidate(
            "does-not-exist",
            runner=FakeQualificationRunner(QualificationState.PASS),
            fixtures={"local": True},
        )


def test_candidate_without_technical_api_id_blocks(storage):
    _policy(storage)
    model_id = _candidate(storage, "5", technical_model_id=None)
    result = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="test")
    assert result.status is PromotionStatus.BLOCKED
    assert storage.get_registered_model(model_id).lifecycle_state is LifecycleState.CANDIDATE


def test_unverified_availability_blocks(storage):
    _policy(storage)
    _candidate(storage, "5", availability=AvailabilityState.UNVERIFIED)
    assert storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="test"
    ).status is PromotionStatus.BLOCKED


def test_unverified_pricing_blocks(storage):
    _policy(storage)
    _candidate(storage, "5", price_state=PricingVerificationState.UNVERIFIED)
    assert storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="test"
    ).status is PromotionStatus.BLOCKED


def test_any_single_price_dimension_above_role_ceiling_blocks(storage):
    _policy(storage, ceiling=_prices("10"))
    high = PriceDimensions.from_mapping({
        **{key: "1" for key in PRICE_KEYS},
        "output_per_mtok": "10.000001",
    })
    _candidate(storage, "5", price_values=high)
    assert storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="test"
    ).status is PromotionStatus.BLOCKED


def test_missing_required_capability_blocks(storage):
    _policy(storage, structured=True)
    _candidate(storage, "5", structured=False)
    assert storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="test"
    ).status is PromotionStatus.BLOCKED


@pytest.mark.parametrize("state", [QualificationState.UNQUALIFIED, QualificationState.FAIL])
def test_nonpassing_qualification_blocks(storage, state):
    _policy(storage)
    _candidate(storage, "5", qualification=state)
    assert storage.promote_best_model(
        LogicalModelRole.ARTICLE_WRITER, reason="test"
    ).status is PromotionStatus.BLOCKED


def test_qualified_candidate_is_eligible_and_promoted(storage):
    _policy(storage)
    model_id = _candidate(storage, "5")
    outcome = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="fake pass")
    assert outcome.status is PromotionStatus.PROMOTED
    assert outcome.new_model_registry_id == model_id
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER).registry_id == model_id


def test_n_plus_one_pass_promotes_but_fail_and_expensive_versions_do_not(storage):
    _policy(storage, ceiling=_prices("10"))
    v5 = _candidate(storage, "5")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="baseline")
    v51 = _candidate(storage, "5.1")
    promoted = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="qualified n+1")
    assert promoted.old_model_registry_id == v5
    assert promoted.new_model_registry_id == v51
    _candidate(storage, "5.2", qualification=QualificationState.FAIL)
    _candidate(storage, "6", price_values=_prices("10.000001"))
    unchanged = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="recheck")
    assert unchanged.status is PromotionStatus.NO_CHANGE
    assert unchanged.new_model_registry_id == v51


def test_candidate_from_other_family_cannot_be_selected(storage):
    _policy(storage)
    _candidate(storage, "99", family=ModelFamily.SONNET)
    outcome = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="wrong family")
    assert outcome.status is PromotionStatus.BLOCKED
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER) is None


def test_promotion_is_idempotent_and_audit_is_persistent(storage):
    _policy(storage)
    model_id = _candidate(storage, "5")
    first = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="first")
    second = storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="second")
    assert first.status is PromotionStatus.PROMOTED
    assert second.status is PromotionStatus.NO_CHANGE
    audit = storage.list_model_routing_audit(LogicalModelRole.ARTICLE_WRITER)
    assert len(audit) == 1
    assert audit[0].new_model_registry_id == model_id
    assert audit[0].event_type is RoutingAuditEventType.PROMOTION
    raw = storage.conn.execute("SELECT * FROM model_routing_audit").fetchone()
    assert raw["new_technical_model_id"] == "fake-fable-5"
    assert raw["new_pricing_ref"]
    assert raw["qualification_ref"]
    assert raw["capability_ref"]


def test_concurrent_promotions_create_one_coherent_active_selection(tmp_path):
    path = tmp_path / "concurrent-routing.db"
    initialize_database(path)
    setup = SqliteStorage.open(path)
    _policy(setup)
    _candidate(setup, "5")
    setup.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="baseline")
    newest = _candidate(setup, "5.1")
    setup.close()

    barrier = threading.Barrier(2)
    outcomes = []
    errors = []

    def promote() -> None:
        local = SqliteStorage.open(path)
        try:
            barrier.wait(timeout=5)
            outcomes.append(local.promote_best_model(
                LogicalModelRole.ARTICLE_WRITER, reason="concurrent"
            ))
        except BaseException as exc:  # evidence collected by the parent assertion
            errors.append(exc)
        finally:
            local.close()

    threads = [threading.Thread(target=promote) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    assert sorted(value.status.value for value in outcomes) == ["NO_CHANGE", "PROMOTED"]
    check = SqliteStorage.open(path)
    try:
        assert check.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER).registry_id == newest
        assert check.conn.execute(
            "SELECT count(*) FROM model_role_activations WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == 1
        assert check.conn.execute(
            "SELECT count(*) FROM model_routing_audit WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == 2  # baseline plus exactly one N+1 promotion
    finally:
        check.close()


def test_restart_preserves_active_selection(tmp_path):
    path = tmp_path / "restart-routing.db"
    initialize_database(path)
    first = SqliteStorage.open(path)
    _policy(first)
    selected = _candidate(first, "5")
    first.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="before restart")
    first.close()
    reopened = SqliteStorage.open(path)
    try:
        assert reopened.get_active_model_for_role(
            LogicalModelRole.ARTICLE_WRITER
        ).registry_id == selected
    finally:
        reopened.close()


def test_historical_intent_stays_frozen_and_new_intent_gets_promoted_model(storage):
    _policy(storage)
    old_model = _candidate(storage, "5")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="old active")
    old_binding = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER,
        intent_kind="CONTENT_WRITER",
        intent_id="intent-A",
    )
    new_model = _candidate(storage, "5.1")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="new active")
    old_again = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER,
        intent_kind="CONTENT_WRITER",
        intent_id="intent-A",
    )
    new_binding = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER,
        intent_kind="CONTENT_WRITER",
        intent_id="intent-B",
    )
    assert old_binding.model_registry_id == old_model
    assert old_again == old_binding
    assert new_binding.model_registry_id == new_model
    routed = route_from_frozen_model_binding(
        new_binding, content_type=ContentType.ARTICLE,
    )
    assert routed.logical_role is LogicalModelRole.ARTICLE_WRITER
    assert routed.model_family is ModelFamily.FABLE
    assert routed.logical_version == "5.1"
    assert routed.api_model_id == new_binding.technical_model_id
    assert routed.route_key == "FABLE_5_ARTICLE"  # compatibility only
    called = []
    result = ModelRoutingService(storage).execute_frozen_intent(
        intent_kind="CONTENT_WRITER",
        intent_id="intent-A",
        caller=lambda binding: called.append(binding.technical_model_id) or "failed-again",
    )
    assert result == "failed-again"
    assert called == [old_binding.technical_model_id]


def test_active_model_losing_qualification_is_blocked_for_new_intents(storage):
    _policy(storage)
    model_id = _candidate(storage, "5")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="active")
    old = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER, intent_kind="CONTENT_WRITER", intent_id="old"
    )
    storage.record_model_qualification(QualificationReport(
        qualification_ref="qual-withdrawn",
        model_registry_id=model_id,
        state=QualificationState.FAIL,
        suite_version="fake-regression-suite-v2",
        fixture_set_ref="fake-fixtures-v2",
        result_payload={"outcome": "FAIL"},
        evaluated_at=TS,
    ))
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_NO_LONGER_ELIGIBLE"):
        storage.freeze_model_for_intent(
            LogicalModelRole.ARTICLE_WRITER,
            intent_kind="CONTENT_WRITER",
            intent_id="new",
        )
    assert storage.get_frozen_model_binding(
        intent_kind="CONTENT_WRITER", intent_id="old"
    ) == old


def test_runtime_provider_failure_never_promotes_or_falls_back(storage):
    _policy(storage)
    old = _candidate(storage, "5")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="active")
    binding = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER, intent_kind="CONTENT_WRITER", intent_id="failed"
    )
    service = ModelRoutingService(storage)
    with pytest.raises(RoutingError, match="RUNTIME_FALLBACK_FORBIDDEN"):
        service.runtime_failure(binding, error_code="PROVIDER_503")
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER).registry_id == old
    assert len(storage.list_model_routing_audit(LogicalModelRole.ARTICLE_WRITER)) == 1


def test_unqualified_model_never_reaches_technical_caller(storage):
    _policy(storage)
    _candidate(storage, "5", qualification=QualificationState.UNQUALIFIED)
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="must block")
    calls = []
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
        ModelRoutingService(storage).execute_new_intent(
            LogicalModelRole.ARTICLE_WRITER,
            intent_kind="CONTENT_WRITER",
            intent_id="never-called",
            caller=lambda binding: calls.append(binding.technical_model_id),
        )
    assert calls == []


def test_depromotion_blocks_new_intents_but_preserves_existing_binding(storage):
    _policy(storage)
    active = _candidate(storage, "5")
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason="active")
    frozen = storage.freeze_model_for_intent(
        LogicalModelRole.ARTICLE_WRITER, intent_kind="CONTENT_WRITER", intent_id="old"
    )
    events = storage.deprecate_registered_model(active, reason="qualification withdrawn")
    assert len(events) == 1
    assert events[0].event_type is RoutingAuditEventType.DEMOTION
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER) is None
    with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
        storage.freeze_model_for_intent(
            LogicalModelRole.ARTICLE_WRITER, intent_kind="CONTENT_WRITER", intent_id="new"
        )
    assert storage.get_frozen_model_binding(
        intent_kind="CONTENT_WRITER", intent_id="old"
    ) == frozen


@dataclass
class FakeCatalogue:
    candidates: tuple[CatalogueCandidate, ...]

    def discover(self):
        return self.candidates


@dataclass
class FakeQualificationRunner:
    state: QualificationState

    def qualify(self, model, fixtures):
        assert fixtures == {"local": True}
        return QualificationReport(
            qualification_ref=f"runner-{model.registry_id}-{self.state.value.lower()}",
            model_registry_id=model.registry_id,
            state=self.state,
            suite_version="fake-runner-v1",
            fixture_set_ref="fixture-set-v1",
            result_payload={"state": self.state.value},
            evaluated_at=TS,
        )


def test_fake_discovery_only_registers_candidate_and_fake_qualification_auto_promotes(storage):
    _policy(storage)
    api_id = "fake-fable-5"
    candidate = CatalogueCandidate(
        provider="fake-provider",
        family=ModelFamily.FABLE,
        logical_version="5",
        technical_model_id=api_id,
        availability_state=AvailabilityState.AVAILABLE,
        pricing_ref="discovery-price",
        discovered_at=TS,
        catalogue_ref="fake-catalogue-source",
    )
    service = ModelRoutingService(storage)
    registered = service.ingest_catalogue(FakeCatalogue((candidate,)))[0]
    assert registered.lifecycle_state is LifecycleState.CANDIDATE
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER) is None
    storage.register_model_pricing_profile(ModelPricingProfile(
        pricing_ref="discovery-price", provider="fake-provider",
        technical_model_id=api_id,
        verification_state=PricingVerificationState.VERIFIED,
        currency="USD", unit="fake", prices=_prices(), verified_at=TS,
    ))
    storage.record_model_capabilities(registered.registry_id, CapabilityDeclaration(
        capability_ref="discovery-caps",
        verification_state=CapabilityVerificationState.VERIFIED,
        structured_response=True, max_context_tokens=20_000,
        max_output_tokens=4_000, verified_at=TS,
    ))
    _, outcomes = service.qualify_candidate(
        registered.registry_id,
        runner=FakeQualificationRunner(QualificationState.PASS),
        fixtures={"local": True},
    )
    writer = next(item for item in outcomes if item.role is LogicalModelRole.ARTICLE_WRITER)
    assert writer.status is PromotionStatus.PROMOTED
    assert storage.get_active_model_for_role(LogicalModelRole.ARTICLE_WRITER).registry_id == registered.registry_id


def test_stable_content_role_is_explicit_and_wrong_family_is_rejected():
    route = RouteContract(
        content_type=ContentType.ARTICLE,
        route_key="FABLE_5_ARTICLE",
        logical_model_name="historical compatibility label",
        config_version="content_routes_v1",
        config_fingerprint="a" * 64,
    )
    assert route.logical_role is LogicalModelRole.ARTICLE_WRITER
    assert route.model_family is ModelFamily.FABLE
    with pytest.raises(ValueError, match="family"):
        RouteContract(
            content_type=ContentType.ARTICLE,
            route_key="FABLE_5_ARTICLE",
            logical_model_name="bad",
            logical_role=LogicalModelRole.ARTICLE_WRITER,
            model_family=ModelFamily.SONNET,
            config_version="bad",
            config_fingerprint="b" * 64,
        )


def test_0027_is_forward_only_explicit_idempotent_and_preserves_legacy_route_schema(tmp_path):
    assert MODEL_FAMILY_ROUTING_SCHEMA_VERSION in canonical_migration_versions()
    path = tmp_path / "upgrade-0027.db"
    initialize_database(path, through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION)
    result = migrate_0026_to_0027(path)
    assert result.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)
    assert migrate_0026_to_0027(path).idempotent is True
    assert database_schema_versions(path)[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
    conn = sqlite3.connect(path)
    try:
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='content_writer_intents'"
        ).fetchone()[0]
        assert "FABLE_5_ARTICLE" in sql and "SONNET_5_NOTE" in sql
        assert conn.execute("SELECT count(*) FROM model_role_policies").fetchone()[0] == 7
        assert conn.execute(
            "SELECT count(*) FROM model_registry"
        ).fetchone()[0] == 0
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='content_writer_intents_stable_role_contract'"
        ).fetchone()[0]
        assert "ARTICLE_WRITER" in trigger_sql and "FABLE" in trigger_sql
        assert "NOTE_WRITER" in trigger_sql and "SONNET" in trigger_sql
    finally:
        conn.close()


def test_0027_cli_requires_exact_confirmation(tmp_path, capsys):
    import scripts.migrate_schema_0027 as migration_cli

    path = tmp_path / "cli-0027.db"
    initialize_database(path, through=CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION)
    assert migration_cli.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION
    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0026-to-0027",
    ]) == 0
    assert "0026_controlled_provider_content -> 0027_model_family_routing" in capsys.readouterr().out
