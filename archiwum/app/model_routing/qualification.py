"""Controlled qualification: the one bootstrap that may precede PASS.

A model that is published, priced and reachable is still *unqualified* for this
project.  Knowing its ID proves nothing about whether it returns the structured
output this pipeline requires.  The only thing that can establish that is one
real request — and that request is exactly the thing this wave must not make.

So this module builds the seam and leaves it unexecuted:

* a durable one-time L1 approval binding role, registry entry, technical model,
  pricing ref, token ceilings, cost cap, expiry and single-use state;
* a fail-closed executor that consumes the approval atomically, calls exactly
  one caller with ``max_retries=0`` and no fallback, and settles the cost from
  the frozen pricing profile;
* an outcome of ``PASS`` / ``FAIL`` / ``NEEDS_VERIFICATION`` that is written
  once and never rewritten.

Capability evidence is derived from what the run actually observed, not from
documentation: a PASS records the output ceiling the model was asked for and
demonstrably honoured, which is a lower bound rather than a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Protocol

from app.core.money import quantize_usd
from app.llm.anthropic_provider_contract import returned_provenance_mismatch
from app.model_routing.contracts import (
    LogicalModelRole,
    ModelPricingProfile,
    PriceDimensions,
    PricingVerificationState,
    QualificationState,
    RegisteredModel,
    RoutingError,
    fingerprint,
)

QUALIFICATION_PURPOSE = "CONTROLLED_LIVE_QUALIFICATION"
CONTROLLED_LIVE_QUALIFICATION_SOURCE = "CONTROLLED_LIVE"
_PER_MILLION = Decimal("1000000")
_PER_THOUSAND = Decimal("1000")


class ControlledQualificationError(RuntimeError):
    """A typed fail-closed refusal on the qualification bootstrap path."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class QualificationApproval:
    """One human decision authorising exactly one qualification request."""

    approval_ref: str
    request_id: str
    logical_role: LogicalModelRole
    model_registry_id: str
    provider: str
    technical_model_id: str
    pricing_ref: str
    max_input_tokens: int
    max_output_tokens: int
    cap_usd: Decimal
    approved_by: str
    approved_at: str
    expires_at: str
    retention_acceptance_ref: str | None = None
    purpose: str = QUALIFICATION_PURPOSE
    max_retries: int = 0
    fallback_policy: str = "FORBIDDEN"
    require_source_discovery: bool = False

    def __post_init__(self) -> None:
        if self.purpose != QUALIFICATION_PURPOSE:
            raise ControlledQualificationError(
                "QUALIFICATION_PURPOSE_INVALID",
                "This approval authorises only a controlled qualification.",
            )
        if self.max_retries != 0 or self.fallback_policy != "FORBIDDEN":
            raise ControlledQualificationError(
                "QUALIFICATION_SAFETY_POLICY_INVALID",
                "A qualification request permits no retry and no fallback.",
            )
        if self.expires_at <= self.approved_at:
            raise ControlledQualificationError(
                "QUALIFICATION_APPROVAL_WINDOW_INVALID",
                "An approval must expire after it was granted.",
            )
        if self.cap_usd <= 0:
            raise ControlledQualificationError(
                "QUALIFICATION_CAP_INVALID",
                "A qualification approval requires a positive cost cap.",
            )
        if not isinstance(self.require_source_discovery, bool):
            raise ControlledQualificationError(
                "QUALIFICATION_SOURCE_DISCOVERY_INVALID",
                "Source-discovery qualification requirement must be boolean.",
            )

    @property
    def canonical_cap(self) -> str:
        return format(quantize_usd(self.cap_usd, label="qualification cap"), ".6f")

    def payload(self) -> dict[str, Any]:
        return {
            "approval_ref": self.approval_ref,
            "request_id": self.request_id,
            "logical_role": self.logical_role.value,
            "model_registry_id": self.model_registry_id,
            "provider": self.provider,
            "technical_model_id": self.technical_model_id,
            "pricing_ref": self.pricing_ref,
            "purpose": self.purpose,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "cap_usd": self.canonical_cap,
            "max_retries": self.max_retries,
            "fallback_policy": self.fallback_policy,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "retention_acceptance_ref": self.retention_acceptance_ref,
            "require_source_discovery": self.require_source_discovery,
        }

    def approval_fingerprint(self) -> str:
        return fingerprint(self.payload())


def _token_count(value: object, *, field: str) -> int:
    """A token count is a non-negative integer, and nothing else."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlledQualificationError(
            "QUALIFICATION_USAGE_INVALID",
            f"{field} must be an integer token count.",
        )
    if value < 0:
        raise ControlledQualificationError(
            "QUALIFICATION_USAGE_INVALID",
            f"{field} cannot be negative.",
        )
    return value


@dataclass(frozen=True)
class QualificationProbeUsage:
    """Token counts a qualification caller reported. Never a self-priced cost."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_search_requests: int = 0
    inference_geo: str | None = None
    service_tier: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "input_tokens", "output_tokens", "cache_read_tokens",
            "cache_write_tokens", "web_search_requests",
        ):
            _token_count(getattr(self, field), field=field)


@dataclass(frozen=True)
class QualificationProbeResponse:
    """The closed shape a qualification caller may return."""

    returned_model_id: str
    structured_response_ok: bool
    usage: QualificationProbeUsage
    stop_reason: str | None = None
    provider_request_id: str | None = None
    detail: str = ""
    source_discovery_ok: bool = False


class QualificationCaller(Protocol):
    """Technical boundary injected only after durable consume+reservation.

    The production Fable implementation and its supported composition root live
    in ``app.model_routing.production_qualification``.  Tests may still inject
    fakes, but transport construction is not authority and never owns lifecycle.
    """

    def __call__(
        self, approval: QualificationApproval,
    ) -> QualificationProbeResponse: ...


@dataclass(frozen=True)
class QualificationOutcome:
    request_id: str
    approval_ref: str
    model_registry_id: str
    logical_role: LogicalModelRole
    provider: str
    technical_model_id: str
    returned_model_id: str | None
    pricing_ref: str
    pricing_profile_fingerprint: str
    outcome: str
    failure_kind: str | None
    usage: QualificationProbeUsage | None
    cost_usd: Decimal | None
    qualification_ref: str | None
    observed_max_output_tokens: int | None
    observed_max_context_tokens: int | None
    structured_response_ok: bool
    source_discovery_ok: bool
    provider_request_id: str | None = None
    stop_reason: str | None = None

    @property
    def canonical_cost(self) -> str | None:
        """``None`` means the cost is unknown — never that it was zero."""
        if self.cost_usd is None:
            return None
        return format(quantize_usd(self.cost_usd, label="qualification cost"), ".6f")

    @property
    def state(self) -> QualificationState | None:
        if self.outcome == "PASS":
            return QualificationState.PASS
        if self.outcome == "FAIL":
            return QualificationState.FAIL
        return None

    def payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "approval_ref": self.approval_ref,
            "model_registry_id": self.model_registry_id,
            "logical_role": self.logical_role.value,
            "provider": self.provider,
            "technical_model_id": self.technical_model_id,
            "returned_model_id": self.returned_model_id,
            "pricing_ref": self.pricing_ref,
            "pricing_profile_fingerprint": self.pricing_profile_fingerprint,
            "outcome": self.outcome,
            "failure_kind": self.failure_kind,
            "usage": None if self.usage is None else {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cache_read_tokens": self.usage.cache_read_tokens,
                "cache_write_tokens": self.usage.cache_write_tokens,
                "web_search_requests": self.usage.web_search_requests,
                "inference_geo": self.usage.inference_geo,
                "service_tier": self.usage.service_tier,
            },
            "cost_usd": self.canonical_cost,
            "qualification_ref": self.qualification_ref,
            "observed_max_output_tokens": self.observed_max_output_tokens,
            "observed_max_context_tokens": self.observed_max_context_tokens,
            "structured_response_ok": self.structured_response_ok,
            "source_discovery_ok": self.source_discovery_ok,
            "provider_request_id": self.provider_request_id,
            "stop_reason": self.stop_reason,
        }

    def result_fingerprint(self) -> str:
        return fingerprint(self.payload())


def price_qualification_usage(
    prices: PriceDimensions, usage: QualificationProbeUsage,
) -> Decimal:
    """Decimal-only settlement from the frozen profile, never from the caller."""
    dimensions = prices.as_decimal_mapping()
    total = (
        Decimal(usage.input_tokens) / _PER_MILLION * dimensions["input_per_mtok"]
        + Decimal(usage.output_tokens) / _PER_MILLION * dimensions["output_per_mtok"]
        + Decimal(usage.cache_read_tokens) / _PER_MILLION
        * dimensions["cache_read_per_mtok"]
        + Decimal(usage.cache_write_tokens) / _PER_MILLION
        * dimensions["cache_write_per_mtok"]
        + Decimal(usage.web_search_requests) / _PER_THOUSAND
        * dimensions["web_search_per_1k"]
    )
    return quantize_usd(total, label="controlled qualification cost")


def evaluate_qualification_probe(
    *,
    approval: QualificationApproval,
    model: RegisteredModel,
    pricing: ModelPricingProfile,
    response: QualificationProbeResponse,
) -> QualificationOutcome:
    """Turn one probe into a durable outcome without ever trusting the caller.

    Three things can only end in ``NEEDS_VERIFICATION``: a response naming
    another model, usage for a feature the request never enabled, and a cost
    that cannot be priced from the frozen profile.  None of them is a normal
    failure, because each means the durable record and the real charge may have
    diverged.
    """
    if pricing.verification_state is not PricingVerificationState.VERIFIED:
        raise ControlledQualificationError(
            "QUALIFICATION_PRICING_UNVERIFIED",
            "A qualification run cannot settle against unverified pricing.",
        )
    if pricing.prices is None or pricing.pricing_ref != approval.pricing_ref:
        raise ControlledQualificationError(
            "QUALIFICATION_PRICING_REF_MISMATCH",
            "The settlement profile is not the approved one.",
        )
    if (
        model.registry_id != approval.model_registry_id
        or model.technical_model_id != approval.technical_model_id
        or model.provider != approval.provider
    ):
        raise ControlledQualificationError(
            "QUALIFICATION_MODEL_IDENTITY_MISMATCH",
            "The registry entry is not the approved one.",
        )

    usage = response.usage
    cost = price_qualification_usage(pricing.prices, usage)
    failure_kind: str | None = None
    outcome = "PASS"

    if response.returned_model_id != approval.technical_model_id:
        outcome, failure_kind = "NEEDS_VERIFICATION", "RETURNED_MODEL_MISMATCH"
    elif usage.cache_read_tokens or usage.cache_write_tokens:
        # C5 never enables prompt caching. Cache usage means the request that
        # actually ran was not the request that was approved.
        outcome, failure_kind = "NEEDS_VERIFICATION", "UNEXPECTED_CACHE_USAGE"
    elif usage.web_search_requests and not approval.require_source_discovery:
        outcome, failure_kind = "NEEDS_VERIFICATION", "UNEXPECTED_WEB_SEARCH_USAGE"
    elif mismatch := returned_provenance_mismatch(
        inference_geo=usage.inference_geo,
        service_tier=usage.service_tier,
    ):
        outcome, failure_kind = "NEEDS_VERIFICATION", mismatch
    elif usage.input_tokens > approval.max_input_tokens:
        outcome, failure_kind = "NEEDS_VERIFICATION", "INPUT_CEILING_EXCEEDED"
    elif usage.output_tokens > approval.max_output_tokens:
        outcome, failure_kind = "NEEDS_VERIFICATION", "OUTPUT_CEILING_EXCEEDED"
    elif cost > quantize_usd(approval.cap_usd, label="approved cap"):
        outcome, failure_kind = "NEEDS_VERIFICATION", "COST_CAP_EXCEEDED"
    elif response.stop_reason == "refusal":
        outcome, failure_kind = "FAIL", "PROVIDER_REFUSAL"
    elif not response.structured_response_ok:
        outcome, failure_kind = "FAIL", "STRUCTURED_RESPONSE_REJECTED"
    elif approval.require_source_discovery and (
        not response.source_discovery_ok or usage.web_search_requests < 1
    ):
        outcome, failure_kind = "FAIL", "SOURCE_DISCOVERY_CAPABILITY_REJECTED"

    qualification_ref = (
        None if outcome == "NEEDS_VERIFICATION"
        else f"controlled-qual-{approval.request_id}"
    )
    # What the run demonstrates is that the model ACCEPTED this token budget and
    # answered inside it. The budget is therefore the honest observed envelope;
    # the probe's own small usage is not, since a short answer proves nothing
    # about the ceiling the model tolerates.
    observed_output = (
        approval.max_output_tokens if outcome == "PASS" else None
    )
    observed_context = (
        approval.max_input_tokens + approval.max_output_tokens
        if outcome == "PASS" else None
    )
    return QualificationOutcome(
        request_id=approval.request_id,
        approval_ref=approval.approval_ref,
        model_registry_id=approval.model_registry_id,
        logical_role=approval.logical_role,
        provider=approval.provider,
        technical_model_id=approval.technical_model_id,
        returned_model_id=response.returned_model_id,
        pricing_ref=approval.pricing_ref,
        pricing_profile_fingerprint=pricing.contract_fingerprint(),
        outcome=outcome,
        failure_kind=failure_kind,
        usage=usage,
        cost_usd=cost,
        qualification_ref=qualification_ref,
        observed_max_output_tokens=observed_output,
        observed_max_context_tokens=observed_context,
        structured_response_ok=response.structured_response_ok,
        source_discovery_ok=response.source_discovery_ok,
        provider_request_id=response.provider_request_id,
        stop_reason=response.stop_reason,
    )


def qualification_result_payload(outcome: QualificationOutcome) -> Mapping[str, Any]:
    """The evidence body persisted alongside a PASS/FAIL registry transition."""
    return {
        "source": CONTROLLED_LIVE_QUALIFICATION_SOURCE,
        "request_id": outcome.request_id,
        "approval_ref": outcome.approval_ref,
        "outcome": outcome.outcome,
        "failure_kind": outcome.failure_kind,
        "returned_model_id": outcome.returned_model_id,
        "cost_usd": outcome.canonical_cost,
        "structured_response_ok": outcome.structured_response_ok,
        "source_discovery_ok": outcome.source_discovery_ok,
    }


def reservation_payload(
    approval: QualificationApproval, *, external_effect_started_at: str,
) -> Mapping[str, Any]:
    """The durable record written BEFORE the provider boundary is crossed.

    Its whole purpose is to survive a timeout or a crash: after reopen this row
    proves that a request for this exact approval may already have been issued.
    """
    return {
        "request_id": approval.request_id,
        "approval_ref": approval.approval_ref,
        "model_registry_id": approval.model_registry_id,
        "logical_role": approval.logical_role.value,
        "provider": approval.provider,
        "technical_model_id": approval.technical_model_id,
        "pricing_ref": approval.pricing_ref,
        "outcome": "IN_FLIGHT",
        "external_effect_started_at": external_effect_started_at,
    }


def unknown_result_outcome(
    *,
    approval: QualificationApproval,
    pricing: ModelPricingProfile,
    failure_kind: str,
) -> QualificationOutcome:
    """An execution whose result never came back.

    Usage and cost stay ``None``.  The provider may well have served this
    request, so recording zero usage at zero cost would assert something nobody
    established.
    """
    return QualificationOutcome(
        request_id=approval.request_id,
        approval_ref=approval.approval_ref,
        model_registry_id=approval.model_registry_id,
        logical_role=approval.logical_role,
        provider=approval.provider,
        technical_model_id=approval.technical_model_id,
        returned_model_id=None,
        pricing_ref=approval.pricing_ref,
        pricing_profile_fingerprint=pricing.contract_fingerprint(),
        outcome="NEEDS_VERIFICATION",
        failure_kind=failure_kind,
        usage=None,
        cost_usd=None,
        qualification_ref=None,
        observed_max_output_tokens=None,
        observed_max_context_tokens=None,
        structured_response_ok=False,
        source_discovery_ok=False,
        provider_request_id=None,
        stop_reason=None,
    )
