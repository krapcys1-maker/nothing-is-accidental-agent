"""Frozen Anthropic request, response-provenance and retention contract.

The values in this module are runtime authority, not configurable defaults.
Every controlled Anthropic transport imports them directly, so an environment
or workspace setting cannot widen the request to US inference or Priority Tier.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.clock import parse_authority_instant
from app.model_routing.contracts import fingerprint

ANTHROPIC_PROVIDER = "ANTHROPIC"
CONTROLLED_INFERENCE_GEO = "global"
CONTROLLED_SERVICE_TIER = "standard_only"
EXPECTED_RETURNED_INFERENCE_GEO = "global"
EXPECTED_RETURNED_SERVICE_TIER = "standard"
FALLBACK_POLICY = "FORBIDDEN"
APPLICATION_MAX_RETRIES = 0
SDK_MAX_RETRIES = 0

FABLE_5_MODEL_ID = "claude-fable-5"
OPUS_5_MODEL_ID = "claude-opus-5"
FABLE_RETENTION_REQUIREMENT = "30_DAY_RETENTION_ACCEPTED"
RETENTION_SCOPE_QUALIFICATION = "CONTROLLED_LIVE_QUALIFICATION"
RETENTION_SCOPE_CONTENT = "CONTROLLED_ARTICLE_EXECUTION"
RETENTION_SCOPES = frozenset({
    RETENTION_SCOPE_QUALIFICATION,
    RETENTION_SCOPE_CONTENT,
})


@dataclass(frozen=True)
class AnthropicRequestContract:
    """Every request-time field that may not fall back to an SDK default."""

    provider: str
    inference_geo: str
    service_tier: str
    fallback_policy: str
    application_retries: int
    sdk_retries: int


CANONICAL_ANTHROPIC_REQUEST_CONTRACT = AnthropicRequestContract(
    provider=ANTHROPIC_PROVIDER,
    inference_geo=CONTROLLED_INFERENCE_GEO,
    service_tier=CONTROLLED_SERVICE_TIER,
    fallback_policy=FALLBACK_POLICY,
    application_retries=APPLICATION_MAX_RETRIES,
    sdk_retries=SDK_MAX_RETRIES,
)


def returned_provenance_mismatch(
    *, inference_geo: str | None, service_tier: str | None,
) -> str | None:
    """Classify provider-returned provenance when the API supplies it.

    ``None`` is not fabricated into evidence: request-time parameters remain
    authoritative when a particular response omits either optional usage field.
    """
    if (
        inference_geo is not None
        and inference_geo != EXPECTED_RETURNED_INFERENCE_GEO
    ):
        return "RETURNED_INFERENCE_GEO_MISMATCH"
    if (
        service_tier is not None
        and service_tier != EXPECTED_RETURNED_SERVICE_TIER
    ):
        return "RETURNED_SERVICE_TIER_MISMATCH"
    return None


@dataclass(frozen=True)
class FableRetentionAcceptance:
    """One owner acceptance of Fable's provider-published retention condition.

    The evidence is deliberately scoped to one approval and one request/job.
    It is never a global switch and cannot authorize another provider or model.
    """

    acceptance_ref: str
    scope: str
    approval_ref: str
    request_identity: str
    provider: str
    technical_model_id: str
    provider_policy_ref: str
    accepted_by: str
    accepted_at: str
    expires_at: str
    requirement: str = FABLE_RETENTION_REQUIREMENT

    def __post_init__(self) -> None:
        for field in (
            "acceptance_ref", "approval_ref", "request_identity", "provider",
            "technical_model_id", "provider_policy_ref", "accepted_by",
            "accepted_at", "expires_at",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Retention acceptance requires {field}.")
        if self.scope not in RETENTION_SCOPES:
            raise ValueError("Retention acceptance has an unsupported scope.")
        if self.requirement != FABLE_RETENTION_REQUIREMENT:
            raise ValueError("Retention acceptance requirement is not exact.")
        if self.provider != ANTHROPIC_PROVIDER:
            raise ValueError("Fable retention acceptance requires ANTHROPIC.")
        if self.technical_model_id != FABLE_5_MODEL_ID:
            raise ValueError("Retention acceptance is only defined for Fable 5.")
        if self.expires_at <= self.accepted_at:
            raise ValueError("Retention acceptance must expire after acceptance.")

    def payload(self) -> dict[str, Any]:
        return {
            "acceptance_ref": self.acceptance_ref,
            "scope": self.scope,
            "approval_ref": self.approval_ref,
            "request_identity": self.request_identity,
            "provider": self.provider,
            "technical_model_id": self.technical_model_id,
            "requirement": self.requirement,
            "provider_policy_ref": self.provider_policy_ref,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "expires_at": self.expires_at,
        }

    def evidence_fingerprint(self) -> str:
        return fingerprint(self.payload())


def retention_acceptance_mismatch(
    *,
    technical_model_id: str,
    provider: str,
    scope: str,
    approval_ref: str,
    request_identity: str,
    current_ts: str,
    acceptance: FableRetentionAcceptance | None,
) -> str | None:
    """Return the exact pre-effect refusal reason for a Fable request."""
    if technical_model_id != FABLE_5_MODEL_ID:
        return None
    if acceptance is None:
        return "FABLE_RETENTION_ACCEPTANCE_MISSING"
    if (
        acceptance.provider != provider
        or acceptance.technical_model_id != technical_model_id
        or acceptance.scope != scope
        or acceptance.approval_ref != approval_ref
        or acceptance.request_identity != request_identity
    ):
        return "FABLE_RETENTION_ACCEPTANCE_TARGET_MISMATCH"
    if acceptance.requirement != FABLE_RETENTION_REQUIREMENT:
        return "FABLE_RETENTION_ACCEPTANCE_REQUIREMENT_MISMATCH"
    accepted_at = parse_authority_instant(acceptance.accepted_at)
    expires_at = parse_authority_instant(acceptance.expires_at)
    current_at = parse_authority_instant(current_ts)
    if accepted_at is None or expires_at is None or current_at is None:
        return "FABLE_RETENTION_ACCEPTANCE_TIMESTAMP_INVALID"
    if accepted_at > current_at:
        return "FABLE_RETENTION_ACCEPTANCE_NOT_YET_EFFECTIVE"
    if expires_at <= current_at:
        return "FABLE_RETENTION_ACCEPTANCE_EXPIRED"
    return None
