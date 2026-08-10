"""Provider-ready seam for the two ARTICLE support roles.

The C2 planner is deterministic: it reads a frozen Research Package and derives
a plan without any model.  Calling that "Opus" would be false, so this module
adds the smallest honest boundary instead — a role-scoped provider execution
that produces a *structured* Article Plan / Angle, or an *independent* review,
under exactly the same provenance rules the writer already obeys.

One durable record type serves both roles rather than two parallel subsystems.
Everything that decides what runs comes from the frozen registry binding for
``<job_id>:<ROLE>``; nothing here consults configuration, environment, a CLI
flag or the legacy route key.

This wave ships the seam and the fail-closed gate.  It ships no real caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.content.foundation import canonical_json, sha256_text
from app.core.money import quantize_usd
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
    RegisteredModel,
    ROLE_FAMILY,
)

CONTENT_ROLE_INTENT_KIND = "content_role"
SUPPORTED_CONTENT_ROLES = (
    LogicalModelRole.ARTICLE_PLAN,
    LogicalModelRole.ARTICLE_REVIEWER,
)
_PER_MILLION = Decimal("1000000")
_PER_THOUSAND = Decimal("1000")


class RoleProviderError(RuntimeError):
    """A typed fail-closed refusal in front of a role provider caller."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def content_role_binding_intent_id(job_id: str, role: LogicalModelRole) -> str:
    if not isinstance(job_id, str) or not job_id.strip():
        raise RoleProviderError(
            "CONTENT_ROLE_JOB_ID_INVALID", "A role binding requires a job ID.",
        )
    return f"{job_id.strip()}:{role.value}"


@dataclass(frozen=True)
class RoleUsage:
    """Token counts a role caller reported. Never a self-priced cost."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_search_requests: int = 0


@dataclass(frozen=True)
class RoleProviderResponse:
    """The closed shape any role caller may return."""

    returned_model_id: str
    payload: dict[str, Any]
    usage: RoleUsage
    stop_reason: str | None = None
    provider_request_id: str | None = None


class RoleProviderCaller(Protocol):
    """Future technical boundary; this wave injects fake callers only."""

    def __call__(
        self,
        *,
        binding: FrozenModelBinding,
        role: LogicalModelRole,
        request_payload: dict[str, Any],
    ) -> RoleProviderResponse: ...


@dataclass(frozen=True)
class RoleProviderAuthority:
    """The single resolved authority for one role execution."""

    job_id: str
    role: LogicalModelRole
    binding_intent_id: str
    model_registry_id: str
    provider: str
    technical_model_id: str
    pricing_ref: str
    pricing_profile_fingerprint: str
    qualification_ref: str
    capability_ref: str
    prices: PriceDimensions

    def settle(self, usage: RoleUsage) -> Decimal:
        dimensions = self.prices.as_decimal_mapping()
        total = (
            Decimal(usage.input_tokens) / _PER_MILLION
            * dimensions["input_per_mtok"]
            + Decimal(usage.output_tokens) / _PER_MILLION
            * dimensions["output_per_mtok"]
            + Decimal(usage.cache_read_tokens) / _PER_MILLION
            * dimensions["cache_read_per_mtok"]
            + Decimal(usage.cache_write_tokens) / _PER_MILLION
            * dimensions["cache_write_per_mtok"]
            + Decimal(usage.web_search_requests) / _PER_THOUSAND
            * dimensions["web_search_per_1k"]
        )
        return quantize_usd(total, label=f"{self.role.value} cost")


@dataclass(frozen=True)
class RoleProviderExecution:
    """One durable, append-only role execution with full provenance."""

    execution_ref: str
    job_id: str
    run_id: str
    content_id: int
    role: LogicalModelRole
    authority: RoleProviderAuthority
    returned_model_id: str | None
    outcome: str
    failure_kind: str | None
    usage: RoleUsage
    cost_usd: Decimal
    payload: dict[str, Any]

    @property
    def canonical_cost(self) -> str:
        return format(
            quantize_usd(self.cost_usd, label="role execution cost"), ".6f",
        )

    def result_payload(self) -> dict[str, Any]:
        return {
            "execution_ref": self.execution_ref,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "content_id": self.content_id,
            "logical_role": self.role.value,
            "binding_intent_id": self.authority.binding_intent_id,
            "model_registry_id": self.authority.model_registry_id,
            "provider": self.authority.provider,
            "technical_model_id": self.authority.technical_model_id,
            "returned_model_id": self.returned_model_id,
            "pricing_ref": self.authority.pricing_ref,
            "qualification_ref": self.authority.qualification_ref,
            "capability_ref": self.authority.capability_ref,
            "outcome": self.outcome,
            "failure_kind": self.failure_kind,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cache_read_tokens": self.usage.cache_read_tokens,
                "cache_write_tokens": self.usage.cache_write_tokens,
                "web_search_requests": self.usage.web_search_requests,
            },
            "cost_usd": self.canonical_cost,
            "payload": self.payload,
        }

    def result_fingerprint(self) -> str:
        return sha256_text(canonical_json(self.result_payload()))


def assert_role_binding_ready(
    *,
    job_id: str,
    role: LogicalModelRole,
    binding: FrozenModelBinding | None,
    model: RegisteredModel | None,
    pricing: ModelPricingProfile | None,
    capability: CapabilityDeclaration | None,
    qualification: QualificationReport | None,
    now: str,
) -> RoleProviderAuthority:
    """Admit one role execution, or refuse before any caller exists."""
    if role not in SUPPORTED_CONTENT_ROLES:
        raise RoleProviderError(
            "CONTENT_ROLE_UNSUPPORTED",
            f"{role.value} is not an ARTICLE support role.",
        )
    if binding is None:
        raise RoleProviderError(
            "CONTENT_ROLE_BINDING_MISSING",
            f"No frozen binding exists for {role.value}.",
        )
    if binding.intent_kind != CONTENT_ROLE_INTENT_KIND:
        raise RoleProviderError(
            "CONTENT_ROLE_BINDING_KIND_MISMATCH",
            "A binding frozen for another subsystem cannot run this role.",
        )
    if binding.intent_id != content_role_binding_intent_id(job_id, role):
        raise RoleProviderError(
            "CONTENT_ROLE_BINDING_INTENT_MISMATCH",
            "The frozen binding belongs to a different job or role.",
        )
    if binding.role is not role:
        raise RoleProviderError(
            "CONTENT_ROLE_ROLE_MISMATCH", "The frozen binding names another role.",
        )
    if binding.family is not ROLE_FAMILY[role]:
        raise RoleProviderError(
            "CONTENT_ROLE_FAMILY_MISMATCH",
            f"{role.value} requires the {ROLE_FAMILY[role].value} family.",
        )
    if binding.fallback_policy != "FORBIDDEN":
        raise RoleProviderError(
            "CONTENT_ROLE_FALLBACK_FORBIDDEN",
            "A role binding cannot declare a runtime fallback.",
        )
    if model is None or model.registry_id != binding.model_registry_id:
        raise RoleProviderError(
            "CONTENT_ROLE_REGISTRY_ENTRY_UNKNOWN",
            "The frozen registry entry could not be resolved.",
        )
    if (
        model.provider != binding.provider
        or model.technical_model_id != binding.technical_model_id
        or model.logical_version != binding.logical_version
    ):
        raise RoleProviderError(
            "CONTENT_ROLE_REGISTRY_IDENTITY_DRIFT",
            "The registry entry no longer matches the frozen identity.",
        )
    if qualification is None or (
        qualification.qualification_ref != binding.qualification_ref
    ):
        raise RoleProviderError(
            "CONTENT_ROLE_QUALIFICATION_REF_MISMATCH",
            "Qualification evidence is missing or issued under another ref.",
        )
    if qualification.model_registry_id != binding.model_registry_id:
        raise RoleProviderError(
            "CONTENT_ROLE_QUALIFICATION_MODEL_MISMATCH",
            "Qualification evidence belongs to a different registry entry.",
        )
    if qualification.state is not QualificationState.PASS:
        raise RoleProviderError(
            "CONTENT_ROLE_QUALIFICATION_NOT_PASS",
            f"Frozen qualification state is {qualification.state.value}.",
        )
    if capability is None or capability.capability_ref != binding.capability_ref:
        raise RoleProviderError(
            "CONTENT_ROLE_CAPABILITY_REF_MISMATCH",
            "Capability evidence is missing or issued under another ref.",
        )
    if capability.verification_state is not CapabilityVerificationState.VERIFIED:
        raise RoleProviderError(
            "CONTENT_ROLE_CAPABILITY_UNVERIFIED",
            "Frozen capability evidence is not VERIFIED.",
        )
    if pricing is None or pricing.pricing_ref != binding.pricing_ref:
        raise RoleProviderError(
            "CONTENT_ROLE_PRICING_REF_MISMATCH",
            "A pricing profile other than the frozen one was supplied.",
        )
    if pricing.verification_state is not PricingVerificationState.VERIFIED:
        raise RoleProviderError(
            "CONTENT_ROLE_PRICING_UNVERIFIED",
            "Frozen pricing is UNVERIFIED and cannot settle a role execution.",
        )
    if (
        pricing.provider != binding.provider
        or pricing.technical_model_id != binding.technical_model_id
    ):
        raise RoleProviderError(
            "CONTENT_ROLE_PRICING_MODEL_MISMATCH",
            "Frozen pricing was approved for a different provider or model.",
        )
    if pricing.prices is None:
        raise RoleProviderError(
            "CONTENT_ROLE_PRICING_INCOMPLETE",
            "Frozen pricing does not carry every priced dimension.",
        )
    # A frozen intent keeps its own price for its own lifecycle; what an expired
    # profile may not do is price a role execution that has not started yet.
    if not pricing.is_effective_at(now):
        raise RoleProviderError(
            "CONTENT_ROLE_PRICING_EXPIRED",
            "The frozen pricing profile is not effective at execution time.",
        )
    return RoleProviderAuthority(
        job_id=job_id,
        role=role,
        binding_intent_id=binding.intent_id,
        model_registry_id=binding.model_registry_id,
        provider=binding.provider,
        technical_model_id=binding.technical_model_id,
        pricing_ref=binding.pricing_ref,
        pricing_profile_fingerprint=pricing.contract_fingerprint(),
        qualification_ref=binding.qualification_ref,
        capability_ref=binding.capability_ref,
        prices=pricing.prices,
    )


def evaluate_role_response(
    *,
    authority: RoleProviderAuthority,
    run_id: str,
    content_id: int,
    response: RoleProviderResponse,
) -> RoleProviderExecution:
    """Classify one role response without ever trusting the caller's claims."""
    usage = response.usage
    outcome = "SUCCESS"
    failure_kind: str | None = None
    if response.returned_model_id != authority.technical_model_id:
        # The provider answered as a different model. That is never a normal
        # success and never a reason to try another model.
        outcome, failure_kind = "NEEDS_VERIFICATION", "RETURNED_MODEL_MISMATCH"
    elif usage.cache_read_tokens or usage.cache_write_tokens:
        outcome, failure_kind = "NEEDS_VERIFICATION", "UNEXPECTED_CACHE_USAGE"
    elif usage.web_search_requests:
        outcome, failure_kind = "NEEDS_VERIFICATION", "UNEXPECTED_WEB_SEARCH_USAGE"
    elif not isinstance(response.payload, dict) or not response.payload:
        outcome, failure_kind = "FAILURE", "SCHEMA_VALIDATION"
    return RoleProviderExecution(
        execution_ref=f"{authority.job_id}:{authority.role.value}",
        job_id=authority.job_id,
        run_id=run_id,
        content_id=content_id,
        role=authority.role,
        authority=authority,
        returned_model_id=response.returned_model_id,
        outcome=outcome,
        failure_kind=failure_kind,
        usage=usage,
        cost_usd=authority.settle(usage),
        payload=dict(response.payload) if isinstance(response.payload, dict) else {},
    )
