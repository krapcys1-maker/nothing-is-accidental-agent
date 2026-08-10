"""The one gate a CONTROLLED_PROVIDER content attempt must pass.

Being technically configured is not authorization.  A paid content attempt is
admissible only when a durable registry binding was frozen for exactly this
intent, and every field the attempt will use — provider, technical model ID,
pricing profile, qualification evidence and capability evidence — is the one
that binding named.

The same object also carries the single pricing authority for that attempt.
``app.core.pricing`` (the operator-approved YAML profiles) stays authoritative
for RESEARCH and TOPIC_GENERATION; a controlled content attempt is settled
exclusively from the registry profile its frozen binding points at, so one
attempt can never be priced by two competing sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.content.contracts import WriterCallMode, WriterIntent, WriterUsage
from app.content.foundation import ContentType
from app.core.money import decimal_from, quantize_usd
from app.model_routing.contracts import (
    CapabilityDeclaration,
    CapabilityVerificationState,
    FrozenModelBinding,
    LogicalModelRole,
    ModelPricingProfile,
    PriceDimensions,
    PricingVerificationState,
    QualificationReport,
    QualificationState,
    ROLE_FAMILY,
    RegisteredModel,
)

# Every content writer intent freezes its model under this one binding kind, so
# a binding minted for another subsystem can never satisfy a content attempt.
CONTENT_WRITER_INTENT_KIND = "content_writer"

# The one purpose a durable L1 approval may carry for a paid ARTICLE run.
# There is deliberately no global "live enabled" switch anywhere in this
# contract: authorisation is per job, per model, per price, per cap, once.
CONTENT_APPROVAL_PURPOSE = "CONTROLLED_ARTICLE_EXECUTION"

CONTENT_TYPE_ROLE: dict[ContentType, LogicalModelRole] = {
    ContentType.ARTICLE: LogicalModelRole.ARTICLE_WRITER,
    ContentType.NOTE: LogicalModelRole.NOTE_WRITER,
}

_PER_MILLION = Decimal("1000000")
_PER_THOUSAND = Decimal("1000")


def content_writer_binding_intent_id(job_id: str) -> str:
    """One binding per content execution, shared by both writer attempts.

    Keying this by ``job_id`` rather than by the per-attempt writer intent ID is
    deliberate: a promotion landing between the first attempt and the rewrite
    must not be able to change the model half-way through one execution.
    """
    if not isinstance(job_id, str) or not job_id.strip():
        raise ControlledProviderProvenanceError(
            "CONTROLLED_PROVIDER_JOB_ID_INVALID",
            "A content writer binding requires a non-empty job ID.",
        )
    return f"{job_id.strip()}:{CONTENT_WRITER_INTENT_KIND}"


class ControlledProviderProvenanceError(RuntimeError):
    """A typed fail-closed refusal in front of the technical provider caller."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ControlledProviderProvenance:
    """The durable registry evidence read back for one frozen intent."""

    binding: FrozenModelBinding
    model: RegisteredModel
    pricing: ModelPricingProfile | None
    capability: CapabilityDeclaration | None
    qualification: QualificationReport | None


@dataclass(frozen=True)
class ControlledProviderAuthority:
    """Everything one admitted paid attempt may use, resolved exactly once.

    Nothing here is re-resolved later: the caller, the usage record and the cost
    settlement all read this object, so they cannot disagree about which model
    ran or which price list applies.
    """

    intent_id: str
    binding_intent_id: str
    role: LogicalModelRole
    model_registry_id: str
    provider: str
    technical_model_id: str
    logical_version: str
    pricing_ref: str
    pricing_profile_fingerprint: str
    qualification_ref: str
    capability_ref: str
    activation_decision_fingerprint: str
    currency: str
    unit: str
    prices: PriceDimensions

    def settle(self, usage: WriterUsage, *, web_search_requests: int = 0) -> Decimal:
        """Price one usage record from the frozen profile, in Decimal only."""
        if isinstance(web_search_requests, bool) or web_search_requests < 0:
            raise ControlledProviderProvenanceError(
                "CONTROLLED_PROVIDER_USAGE_INVALID",
                "Web search request count must be a non-negative integer.",
            )
        dimensions = self.prices.as_decimal_mapping()
        total = (
            decimal_from(usage.input_tokens) / _PER_MILLION
            * dimensions["input_per_mtok"]
            + decimal_from(usage.output_tokens) / _PER_MILLION
            * dimensions["output_per_mtok"]
            + decimal_from(usage.cache_read_tokens) / _PER_MILLION
            * dimensions["cache_read_per_mtok"]
            + decimal_from(usage.cache_write_tokens) / _PER_MILLION
            * dimensions["cache_write_per_mtok"]
            + decimal_from(web_search_requests) / _PER_THOUSAND
            * dimensions["web_search_per_1k"]
        )
        return quantize_usd(total, label="controlled provider content cost")

    def settlement_for(
        self,
        *,
        request_id: str,
        attempt_no: int,
        usage: WriterUsage,
        web_search_requests: int = 0,
    ) -> "ControlledProviderSettlement":
        """Build the durable proof that this attempt used this exact profile."""
        return ControlledProviderSettlement(
            request_id=request_id,
            intent_id=self.intent_id,
            attempt_no=attempt_no,
            binding_intent_id=self.binding_intent_id,
            model_registry_id=self.model_registry_id,
            provider=self.provider,
            technical_model_id=self.technical_model_id,
            pricing_ref=self.pricing_ref,
            pricing_profile_fingerprint=self.pricing_profile_fingerprint,
            qualification_ref=self.qualification_ref,
            capability_ref=self.capability_ref,
            currency=self.currency,
            unit=self.unit,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            web_search_requests=web_search_requests,
            cost_usd=self.settle(usage, web_search_requests=web_search_requests),
        )


@dataclass(frozen=True)
class ControlledProviderSettlement:
    """One paid attempt priced by exactly one approved registry profile."""

    request_id: str
    intent_id: str
    attempt_no: int
    binding_intent_id: str
    model_registry_id: str
    provider: str
    technical_model_id: str
    pricing_ref: str
    pricing_profile_fingerprint: str
    qualification_ref: str
    capability_ref: str
    currency: str
    unit: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_search_requests: int
    cost_usd: Decimal

    @property
    def canonical_cost(self) -> str:
        return format(quantize_usd(self.cost_usd, label="settlement cost"), ".6f")


def _refuse(code: str, detail: str) -> None:
    raise ControlledProviderProvenanceError(code, detail)


def assert_controlled_provider_binding_ready(
    intent: WriterIntent,
    provenance: ControlledProviderProvenance | None,
) -> ControlledProviderAuthority:
    """Admit one paid attempt, or refuse before any provider caller exists.

    Every comparison is an identity comparison.  Two pricing profiles carrying
    the same numbers are still two different authorities, and only the frozen
    one may settle this attempt.
    """
    if intent.call_mode is not WriterCallMode.CONTROLLED_PROVIDER:
        _refuse(
            "CONTROLLED_PROVIDER_MODE_REQUIRED",
            "This gate admits only a CONTROLLED_PROVIDER writer intent.",
        )
    route = intent.route
    if provenance is None:
        _refuse(
            "CONTROLLED_PROVIDER_BINDING_MISSING",
            "No frozen registry binding exists for this writer intent.",
        )
    assert provenance is not None
    binding = provenance.binding
    model = provenance.model

    if binding.intent_kind != CONTENT_WRITER_INTENT_KIND:
        _refuse(
            "CONTROLLED_PROVIDER_BINDING_KIND_MISMATCH",
            "A binding frozen for another subsystem cannot run content.",
        )
    if binding.intent_id != content_writer_binding_intent_id(intent.job_id):
        _refuse(
            "CONTROLLED_PROVIDER_BINDING_INTENT_MISMATCH",
            "The frozen binding belongs to a different content execution.",
        )

    expected_role = CONTENT_TYPE_ROLE[intent.content_type]
    if binding.role is not expected_role or route.logical_role is not expected_role:
        _refuse(
            "CONTROLLED_PROVIDER_ROLE_MISMATCH",
            f"{intent.content_type.value} requires logical role {expected_role.value}.",
        )
    if (
        binding.family is not ROLE_FAMILY[expected_role]
        or route.model_family is not binding.family
        or model.family is not binding.family
    ):
        _refuse(
            "CONTROLLED_PROVIDER_FAMILY_MISMATCH",
            "Frozen family disagrees with the role policy or the registry entry.",
        )

    # The route persisted in the intent must repeat the binding exactly. The
    # legacy versioned route key is never consulted for any of this.
    if not route.is_registry_qualified:
        _refuse(
            "CONTROLLED_PROVIDER_REGISTRY_PROVENANCE_MISSING",
            "A paid content route requires complete registry provenance.",
        )
    for label, left, right in (
        ("REGISTRY_ID", route.model_registry_id, binding.model_registry_id),
        ("LOGICAL_VERSION", route.logical_version, binding.logical_version),
        ("PROVIDER", route.provider, binding.provider),
        ("API_MODEL_ID", route.api_model_id, binding.technical_model_id),
        ("PRICING_REF", route.pricing_profile, binding.pricing_ref),
        ("QUALIFICATION_REF", route.qualification_ref, binding.qualification_ref),
        ("CAPABILITY_REF", route.capability_ref, binding.capability_ref),
    ):
        if left != right:
            _refuse(
                f"CONTROLLED_PROVIDER_{label}_MISMATCH",
                f"Durable route {label.lower()} disagrees with the frozen binding.",
            )

    # The registry entry the binding names must still be the same entry. A
    # later promotion mints a different registry_id, so this cannot silently
    # follow a newer model.
    if model.registry_id != binding.model_registry_id:
        _refuse(
            "CONTROLLED_PROVIDER_REGISTRY_ENTRY_UNKNOWN",
            "The frozen registry entry could not be resolved.",
        )
    if (
        model.provider != binding.provider
        or model.technical_model_id != binding.technical_model_id
        or model.logical_version != binding.logical_version
    ):
        _refuse(
            "CONTROLLED_PROVIDER_REGISTRY_IDENTITY_DRIFT",
            "The registry entry no longer matches the frozen technical identity.",
        )

    qualification = provenance.qualification
    if qualification is None:
        _refuse(
            "CONTROLLED_PROVIDER_QUALIFICATION_MISSING",
            "The frozen qualification reference resolves to no evidence.",
        )
    assert qualification is not None
    if qualification.qualification_ref != binding.qualification_ref:
        _refuse(
            "CONTROLLED_PROVIDER_QUALIFICATION_REF_MISMATCH",
            "Qualification evidence was issued under a different reference.",
        )
    if qualification.model_registry_id != binding.model_registry_id:
        _refuse(
            "CONTROLLED_PROVIDER_QUALIFICATION_MODEL_MISMATCH",
            "Qualification evidence belongs to a different registry entry.",
        )
    if qualification.state is not QualificationState.PASS:
        _refuse(
            "CONTROLLED_PROVIDER_QUALIFICATION_NOT_PASS",
            f"Frozen qualification state is {qualification.state.value}.",
        )

    capability = provenance.capability
    if capability is None:
        _refuse(
            "CONTROLLED_PROVIDER_CAPABILITY_MISSING",
            "The frozen capability reference resolves to no declaration.",
        )
    assert capability is not None
    if capability.capability_ref != binding.capability_ref:
        _refuse(
            "CONTROLLED_PROVIDER_CAPABILITY_REF_MISMATCH",
            "Capability evidence was issued under a different reference.",
        )
    if capability.verification_state is not CapabilityVerificationState.VERIFIED:
        _refuse(
            "CONTROLLED_PROVIDER_CAPABILITY_UNVERIFIED",
            "Frozen capability evidence is not VERIFIED.",
        )
    if (
        capability.max_output_tokens is None
        or intent.limits.max_output_tokens > capability.max_output_tokens
        or capability.max_context_tokens is None
        or intent.limits.max_context_tokens > capability.max_context_tokens
    ):
        _refuse(
            "CONTROLLED_PROVIDER_CAPABILITY_ENVELOPE_EXCEEDED",
            "The attempt limits exceed the frozen capability envelope.",
        )

    pricing = provenance.pricing
    if pricing is None:
        _refuse(
            "CONTROLLED_PROVIDER_PRICING_MISSING",
            "The frozen pricing reference resolves to no profile.",
        )
    assert pricing is not None
    if pricing.pricing_ref != binding.pricing_ref:
        _refuse(
            "CONTROLLED_PROVIDER_PRICING_REF_MISMATCH",
            "A pricing profile other than the frozen one was supplied.",
        )
    if pricing.verification_state is not PricingVerificationState.VERIFIED:
        _refuse(
            "CONTROLLED_PROVIDER_PRICING_UNVERIFIED",
            "Frozen pricing is UNVERIFIED and cannot settle a paid attempt.",
        )
    if (
        pricing.provider != binding.provider
        or pricing.technical_model_id != binding.technical_model_id
    ):
        _refuse(
            "CONTROLLED_PROVIDER_PRICING_MODEL_MISMATCH",
            "Frozen pricing was approved for a different provider or model.",
        )
    if pricing.prices is None:
        _refuse(
            "CONTROLLED_PROVIDER_PRICING_INCOMPLETE",
            "Frozen pricing does not carry every priced dimension.",
        )
    assert pricing.prices is not None

    if binding.fallback_policy != "FORBIDDEN" or route.fallback != "FORBIDDEN":
        _refuse(
            "CONTROLLED_PROVIDER_FALLBACK_FORBIDDEN",
            "A content binding cannot declare a runtime fallback.",
        )
    if intent.limits.max_cost_usd <= 0.0:
        _refuse(
            "CONTROLLED_PROVIDER_COST_CAP_REQUIRED",
            "A paid attempt requires a positive declared cost cap.",
        )

    return ControlledProviderAuthority(
        intent_id=intent.intent_id,
        binding_intent_id=binding.intent_id,
        role=expected_role,
        model_registry_id=binding.model_registry_id,
        provider=binding.provider,
        technical_model_id=binding.technical_model_id,
        logical_version=binding.logical_version,
        pricing_ref=binding.pricing_ref,
        pricing_profile_fingerprint=pricing.contract_fingerprint(),
        qualification_ref=binding.qualification_ref,
        capability_ref=binding.capability_ref,
        activation_decision_fingerprint=binding.activation_decision_fingerprint,
        currency=pricing.currency,
        unit=pricing.unit,
        prices=pricing.prices,
    )
