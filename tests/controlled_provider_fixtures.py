"""Fake registry data for the controlled-provider content flow.

Every provider, model ID, price and capability here is synthetic.  Real model
IDs, real prices and real availability stay UNVERIFIED in this project; nothing
in this module may be read as a claim about a real provider catalogue.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.model_routing import (
    AvailabilityState,
    CapabilityDeclaration,
    CapabilityVerificationState,
    CatalogueCandidate,
    LogicalModelRole,
    ModelFamily,
    ModelPricingProfile,
    PriceDimensions,
    PricingVerificationState,
    QualificationReport,
    QualificationState,
    RolePolicy,
)
from app.llm.anthropic_provider_contract import (
    FABLE_5_MODEL_ID,
    FableRetentionAcceptance,
    RETENTION_SCOPE_CONTENT,
    inference_config_for_role,
)

TS = "2026-08-09T09:00:00.000000+00:00"
PRICE_KEYS = (
    "input_per_mtok",
    "output_per_mtok",
    "cache_read_per_mtok",
    "cache_write_per_mtok",
    "web_search_per_1k",
)
# Deliberately arbitrary synthetic amounts, distinct per dimension so a wrong
# dimension in the cost formula cannot pass unnoticed.
FAKE_PRICES = {
    "input_per_mtok": "2",
    "output_per_mtok": "7",
    "cache_read_per_mtok": "0.5",
    "cache_write_per_mtok": "1.25",
    "web_search_per_1k": "4",
}
ROLE_FAMILY_FOR_TESTS = {
    LogicalModelRole.TOPIC_GENERATION: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_RESEARCH: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_PLAN: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_WRITER: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_REVIEWER: ModelFamily.OPUS,
    LogicalModelRole.NOTE_WRITER: ModelFamily.SONNET,
    LogicalModelRole.COMMENT_WRITER: ModelFamily.SONNET,
}


def prices(overrides: dict[str, str] | None = None) -> PriceDimensions:
    values = dict(FAKE_PRICES)
    values.update(overrides or {})
    return PriceDimensions.from_mapping(values)


def ceiling(value: str = "50") -> PriceDimensions:
    return PriceDimensions.from_mapping({key: value for key in PRICE_KEYS})


@dataclass(frozen=True)
class SeededModel:
    registry_id: str
    provider: str
    family: ModelFamily
    logical_version: str
    technical_model_id: str
    pricing_ref: str
    capability_ref: str
    qualification_ref: str


def seed_role_policy(
    storage,
    role: LogicalModelRole = LogicalModelRole.ARTICLE_WRITER,
    *,
    price_ceiling: PriceDimensions | None = None,
    min_context_tokens: int = 10_000,
    min_output_tokens: int = 1_000,
) -> RolePolicy:
    policy = RolePolicy(
        role=role,
        allowed_family=ROLE_FAMILY_FOR_TESTS[role],
        policy_version="fake-content-policy-v1",
        capability_verification_state=CapabilityVerificationState.VERIFIED,
        require_structured_response=True,
        min_context_tokens=min_context_tokens,
        min_output_tokens=min_output_tokens,
        pricing_verification_state=PricingVerificationState.VERIFIED,
        price_ceiling=price_ceiling or ceiling(),
    )
    storage.upsert_model_role_policy(policy)
    return policy


def seed_model(
    storage,
    *,
    version: str = "1",
    family: ModelFamily = ModelFamily.OPUS,
    provider: str = "fake-provider",
    price_overrides: dict[str, str] | None = None,
    pricing_ref: str | None = None,
    price_state: PricingVerificationState = PricingVerificationState.VERIFIED,
    capability_state: CapabilityVerificationState = CapabilityVerificationState.VERIFIED,
    max_context_tokens: int = 40_000,
    max_output_tokens: int = 8_000,
    qualification: QualificationState = QualificationState.PASS,
    availability: AvailabilityState = AvailabilityState.AVAILABLE,
    technical_model_id_override: str | None = None,
) -> SeededModel:
    """Register one fully evidenced fake candidate and return its identities."""
    slug = f"{family.value.lower()}-{version.replace('.', '-')}"
    reference_slug = slug if provider == "fake-provider" else f"{provider.lower()}-{slug}"
    technical_model_id = technical_model_id_override or f"fake-{provider}-{slug}"
    resolved_pricing_ref = pricing_ref or f"price-{reference_slug}-v1"
    model = storage.register_model_candidate(
        CatalogueCandidate(
            provider=provider,
            family=family,
            logical_version=version,
            technical_model_id=technical_model_id,
            availability_state=availability,
            pricing_ref=resolved_pricing_ref,
            discovered_at=TS,
            catalogue_ref="fake-content-catalogue-v1",
        )
    )
    verified_price = price_state is PricingVerificationState.VERIFIED
    storage.register_model_pricing_profile(
        ModelPricingProfile(
            pricing_ref=resolved_pricing_ref,
            provider=provider,
            technical_model_id=technical_model_id,
            verification_state=price_state,
            currency="USD",
            unit="fake_usd_per_mtok__web_search_per_1k",
            prices=prices(price_overrides) if verified_price else None,
            verified_at=TS if verified_price else None,
        )
    )
    verified_capability = (
        capability_state is CapabilityVerificationState.VERIFIED
    )
    capability_ref = f"caps-{reference_slug}-v1"
    storage.record_model_capabilities(
        model.registry_id,
        CapabilityDeclaration(
            capability_ref=capability_ref,
            verification_state=capability_state,
            structured_response=True if verified_capability else None,
            max_context_tokens=max_context_tokens if verified_capability else None,
            max_output_tokens=max_output_tokens if verified_capability else None,
            verified_at=TS if verified_capability else None,
        ),
    )
    qualification_ref = f"qual-{reference_slug}-{qualification.value.lower()}"
    if qualification is not QualificationState.UNQUALIFIED:
        storage.record_model_qualification(
            QualificationReport(
                qualification_ref=qualification_ref,
                model_registry_id=model.registry_id,
                state=qualification,
                suite_version="fake-content-suite-v1",
                fixture_set_ref="fake-content-fixtures-v1",
                result_payload={"outcome": qualification.value},
                evaluated_at=TS,
            )
        )
    return SeededModel(
        registry_id=model.registry_id,
        provider=provider,
        family=family,
        logical_version=version,
        technical_model_id=technical_model_id,
        pricing_ref=resolved_pricing_ref,
        capability_ref=capability_ref,
        qualification_ref=qualification_ref,
    )


def seed_active_article_writer(
    storage,
    *,
    version: str = "1",
    price_overrides: dict[str, str] | None = None,
    pricing_ref: str | None = None,
    reason: str = "fake qualification pass",
) -> SeededModel:
    """Policy + candidate + evidence + promotion for the ARTICLE_WRITER role."""
    seed_role_policy(storage, LogicalModelRole.ARTICLE_WRITER)
    model = seed_model(
        storage,
        version=version,
        family=ModelFamily.OPUS,
        price_overrides=price_overrides,
        pricing_ref=pricing_ref,
    )
    storage.promote_best_model(LogicalModelRole.ARTICLE_WRITER, reason=reason)
    return model


def seed_active_provider_role(
    storage,
    *,
    role: LogicalModelRole,
    technical_model_id: str,
    provider: str = "ANTHROPIC",
    version: str = "0.0.1",
):
    """Seed one exact active role authority for an offline production-path test."""
    active = storage.get_active_model_for_role(role)
    if active is not None:
        if (
            active.provider != provider
            or active.technical_model_id != technical_model_id
        ):
            raise AssertionError(
                f"Existing {role.value} fixture authority disagrees with the test intent."
            )
        return active
    seed_role_policy(storage, role)
    model = seed_model(
        storage,
        version=version,
        family=ROLE_FAMILY_FOR_TESTS[role],
        provider=provider,
        technical_model_id_override=technical_model_id,
    )
    storage.promote_best_model(
        role,
        reason=f"offline {role.value} provider-contract fixture",
    )
    return model


def approve_content_provider_execution(
    storage,
    *,
    job_id: str,
    model: SeededModel,
    account_id: str = "nothing_is_accidental",
    role: str = "ARTICLE_WRITER",
    max_output_tokens: int = 8192,
    cap_usd: str = "1.000000",
    approved_by: str = "test-owner",
    approved_at: str = "2026-01-01T00:00:00.000000+00:00",
    expires_at: str = "2099-01-01T00:00:00.000000+00:00",
) -> str:
    """One durable single-use L1 authorisation for one paid ARTICLE job."""
    acceptance_ref = None
    approval_ref = f"approval-{job_id}"
    if model.technical_model_id == FABLE_5_MODEL_ID:
        acceptance_ref = f"retention-{job_id}"
        existing = storage.conn.execute(
            "SELECT 1 FROM fable_retention_acceptances WHERE acceptance_ref=?",
            (acceptance_ref,),
        ).fetchone()
        if existing is None:
            storage.record_fable_retention_acceptance(FableRetentionAcceptance(
                acceptance_ref=acceptance_ref,
                scope=RETENTION_SCOPE_CONTENT,
                approval_ref=approval_ref,
                request_identity=job_id,
                provider=model.provider,
                technical_model_id=model.technical_model_id,
                provider_policy_ref="fake://anthropic/fable-5/retention",
                accepted_by="fake-owner-fixture",
                accepted_at=approved_at,
                expires_at=expires_at,
            ))
    return storage.record_content_provider_approval(
        approval_ref=approval_ref,
        job_id=job_id,
        account_id=account_id,
        role=role,
        model_registry_id=model.registry_id,
        provider=model.provider,
        technical_model_id=model.technical_model_id,
        pricing_ref=model.pricing_ref,
        max_output_tokens=max_output_tokens,
        cap_usd=cap_usd,
        approved_by=approved_by,
        approved_at=approved_at,
        expires_at=expires_at,
        retention_acceptance_ref=acceptance_ref,
        inference_config=inference_config_for_role(role),
    )
