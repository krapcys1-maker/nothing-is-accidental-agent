"""Closed, provider-agnostic contracts for model-family routing.

No provider model name is parsed to discover a family or version.  Both are
explicit catalogue data, while ``ModelVersion`` supplies the deterministic
ordering used by promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from app.core.config import REAL_PROVIDER_PRICING_KEYS


class LogicalModelRole(str, Enum):
    TOPIC_GENERATION = "TOPIC_GENERATION"
    ARTICLE_RESEARCH = "ARTICLE_RESEARCH"
    ARTICLE_PLAN = "ARTICLE_PLAN"
    ARTICLE_WRITER = "ARTICLE_WRITER"
    ARTICLE_REVIEWER = "ARTICLE_REVIEWER"
    NOTE_WRITER = "NOTE_WRITER"
    COMMENT_WRITER = "COMMENT_WRITER"


class ModelFamily(str, Enum):
    SONNET = "SONNET"
    OPUS = "OPUS"
    FABLE = "FABLE"


ROLE_FAMILY: Mapping[LogicalModelRole, ModelFamily] = MappingProxyType({
    LogicalModelRole.TOPIC_GENERATION: ModelFamily.SONNET,
    LogicalModelRole.ARTICLE_RESEARCH: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_PLAN: ModelFamily.OPUS,
    LogicalModelRole.ARTICLE_WRITER: ModelFamily.FABLE,
    LogicalModelRole.ARTICLE_REVIEWER: ModelFamily.OPUS,
    LogicalModelRole.NOTE_WRITER: ModelFamily.SONNET,
    LogicalModelRole.COMMENT_WRITER: ModelFamily.SONNET,
})


class AvailabilityState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PricingVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class CapabilityVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class QualificationState(str, Enum):
    UNQUALIFIED = "UNQUALIFIED"
    PASS = "PASS"
    FAIL = "FAIL"


class LifecycleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class PromotionStatus(str, Enum):
    PROMOTED = "PROMOTED"
    NO_CHANGE = "NO_CHANGE"
    BLOCKED = "BLOCKED"


class RoutingAuditEventType(str, Enum):
    PROMOTION = "PROMOTION"
    DEMOTION = "DEMOTION"


class RoutingError(RuntimeError):
    """A typed fail-closed refusal at the routing boundary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,7}$")
_MAX_VERSION_COMPONENT = 999_999_999
_PRICE_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, order=True)
class ModelVersion:
    """Deterministic numeric version ordering independent of provider IDs."""

    components: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.components:
            raise RoutingError("MODEL_VERSION_INVALID", "Version cannot be empty.")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > _MAX_VERSION_COMPONENT
            for value in self.components
        ):
            raise RoutingError(
                "MODEL_VERSION_INVALID",
                "Version components must be bounded non-negative integers.",
            )
        if len(self.components) > 1 and self.components[-1] == 0:
            raise RoutingError(
                "MODEL_VERSION_NOT_CANONICAL",
                "Trailing zero components must be removed.",
            )

    @classmethod
    def parse(cls, raw: object) -> "ModelVersion":
        if not isinstance(raw, str) or not _VERSION_RE.fullmatch(raw.strip()):
            raise RoutingError(
                "MODEL_VERSION_INVALID",
                "Logical version must contain only numeric dot-separated components.",
            )
        values = [int(part, 10) for part in raw.strip().split(".")]
        while len(values) > 1 and values[-1] == 0:
            values.pop()
        return cls(tuple(values))

    @property
    def canonical(self) -> str:
        return ".".join(str(value) for value in self.components)

    @property
    def storage_key(self) -> str:
        return ".".join(f"{value:09d}" for value in self.components)


def _text(value: object, *, field: str, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RoutingError("MODEL_CONTRACT_INVALID", f"{field} must be non-empty text.")
    return value.strip()


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise RoutingError("MODEL_PRICING_INVALID", f"{field} cannot be bool.")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise RoutingError(
            "MODEL_PRICING_INVALID", f"{field} must be a finite decimal amount."
        ) from exc
    if not amount.is_finite() or amount < 0:
        raise RoutingError(
            "MODEL_PRICING_INVALID", f"{field} must be finite and non-negative."
        )
    return amount.quantize(_PRICE_QUANTUM)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def utc_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class PriceDimensions:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cache_read_per_mtok: Decimal
    cache_write_per_mtok: Decimal
    web_search_per_1k: Decimal

    def __post_init__(self) -> None:
        for key, value in self.as_decimal_mapping().items():
            object.__setattr__(self, key, _decimal(value, field=key))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "PriceDimensions":
        if set(raw) != set(REAL_PROVIDER_PRICING_KEYS):
            raise RoutingError(
                "MODEL_PRICING_INVALID",
                "Pricing must contain every input/output/cache/search dimension.",
            )
        return cls(**{key: _decimal(raw[key], field=key) for key in raw})

    def as_decimal_mapping(self) -> dict[str, Decimal]:
        return {
            "input_per_mtok": self.input_per_mtok,
            "output_per_mtok": self.output_per_mtok,
            "cache_read_per_mtok": self.cache_read_per_mtok,
            "cache_write_per_mtok": self.cache_write_per_mtok,
            "web_search_per_1k": self.web_search_per_1k,
        }

    def as_storage_mapping(self) -> dict[str, str]:
        return {
            key: format(_decimal(value, field=key), ".6f")
            for key, value in self.as_decimal_mapping().items()
        }

    def is_within(self, ceiling: "PriceDimensions") -> bool:
        return all(
            value <= ceiling.as_decimal_mapping()[key]
            for key, value in self.as_decimal_mapping().items()
        )


@dataclass(frozen=True)
class ModelPricingProfile:
    pricing_ref: str
    provider: str
    technical_model_id: str
    verification_state: PricingVerificationState
    currency: str
    unit: str
    prices: PriceDimensions | None
    verified_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pricing_ref", _text(self.pricing_ref, field="pricing_ref"))
        object.__setattr__(self, "provider", _text(self.provider, field="provider"))
        object.__setattr__(
            self,
            "technical_model_id",
            _text(self.technical_model_id, field="technical_model_id"),
        )
        object.__setattr__(self, "currency", _text(self.currency, field="currency"))
        object.__setattr__(self, "unit", _text(self.unit, field="unit"))
        if self.verification_state is PricingVerificationState.VERIFIED:
            if self.prices is None or not self.verified_at:
                raise RoutingError(
                    "MODEL_PRICING_INVALID",
                    "Verified pricing requires all dimensions and verified_at.",
                )
        elif self.prices is not None or self.verified_at is not None:
            raise RoutingError(
                "MODEL_PRICING_INVALID",
                "Unverified pricing cannot carry verified dimensions or timestamp.",
            )

    def payload(self) -> dict[str, Any]:
        return {
            "pricing_ref": self.pricing_ref,
            "provider": self.provider,
            "technical_model_id": self.technical_model_id,
            "verification_state": self.verification_state.value,
            "currency": self.currency,
            "unit": self.unit,
            "prices": None if self.prices is None else self.prices.as_storage_mapping(),
            "verified_at": self.verified_at,
        }

    def contract_fingerprint(self) -> str:
        return fingerprint(self.payload())


@dataclass(frozen=True)
class CapabilityDeclaration:
    capability_ref: str
    verification_state: CapabilityVerificationState
    structured_response: bool | None
    max_context_tokens: int | None
    max_output_tokens: int | None
    verified_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "capability_ref", _text(self.capability_ref, field="capability_ref")
        )
        if self.verification_state is CapabilityVerificationState.VERIFIED:
            if (
                not isinstance(self.structured_response, bool)
                or isinstance(self.max_context_tokens, bool)
                or not isinstance(self.max_context_tokens, int)
                or self.max_context_tokens <= 0
                or isinstance(self.max_output_tokens, bool)
                or not isinstance(self.max_output_tokens, int)
                or self.max_output_tokens <= 0
                or not self.verified_at
            ):
                raise RoutingError(
                    "MODEL_CAPABILITY_INVALID",
                    "Verified capability declarations require explicit positive envelopes.",
                )
        elif any(value is not None for value in (
            self.structured_response,
            self.max_context_tokens,
            self.max_output_tokens,
            self.verified_at,
        )):
            raise RoutingError(
                "MODEL_CAPABILITY_INVALID",
                "Unverified capabilities cannot carry verified claims.",
            )

    def payload(self) -> dict[str, Any]:
        return {
            "capability_ref": self.capability_ref,
            "verification_state": self.verification_state.value,
            "structured_response": self.structured_response,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "verified_at": self.verified_at,
        }

    def contract_fingerprint(self) -> str:
        return fingerprint(self.payload())


@dataclass(frozen=True)
class CatalogueCandidate:
    provider: str
    family: ModelFamily
    logical_version: str
    technical_model_id: str | None
    availability_state: AvailabilityState
    pricing_ref: str | None
    discovered_at: str
    catalogue_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, field="provider"))
        version = ModelVersion.parse(self.logical_version)
        object.__setattr__(self, "logical_version", version.canonical)
        object.__setattr__(
            self,
            "technical_model_id",
            _text(self.technical_model_id, field="technical_model_id", allow_none=True),
        )
        object.__setattr__(
            self, "pricing_ref", _text(self.pricing_ref, field="pricing_ref", allow_none=True)
        )
        object.__setattr__(
            self, "discovered_at", _text(self.discovered_at, field="discovered_at")
        )
        object.__setattr__(
            self, "catalogue_ref", _text(self.catalogue_ref, field="catalogue_ref")
        )

    @property
    def version(self) -> ModelVersion:
        return ModelVersion.parse(self.logical_version)

    @property
    def registry_id(self) -> str:
        identity = fingerprint({
            "provider": self.provider,
            "family": self.family.value,
            "logical_version": self.logical_version,
        })
        return f"model-{identity[:32]}"


@dataclass(frozen=True)
class QualificationReport:
    qualification_ref: str
    model_registry_id: str
    state: QualificationState
    suite_version: str
    fixture_set_ref: str
    result_payload: Mapping[str, Any]
    evaluated_at: str
    source: str = "LOCAL_FIXTURE"

    def __post_init__(self) -> None:
        for field_name in (
            "qualification_ref",
            "model_registry_id",
            "suite_version",
            "fixture_set_ref",
            "evaluated_at",
            "source",
        ):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field=field_name)
            )
        if self.source != "LOCAL_FIXTURE":
            raise RoutingError(
                "QUALIFICATION_SOURCE_FORBIDDEN",
                "This offline wave accepts only LOCAL_FIXTURE qualification evidence.",
            )
        if self.state is QualificationState.UNQUALIFIED:
            raise RoutingError(
                "QUALIFICATION_RESULT_INVALID",
                "A completed qualification run must end in PASS or FAIL.",
            )

    def payload(self) -> dict[str, Any]:
        return {
            "qualification_ref": self.qualification_ref,
            "model_registry_id": self.model_registry_id,
            "state": self.state.value,
            "suite_version": self.suite_version,
            "fixture_set_ref": self.fixture_set_ref,
            "result_payload": dict(self.result_payload),
            "evaluated_at": self.evaluated_at,
            "source": self.source,
        }

    def result_fingerprint(self) -> str:
        return fingerprint(self.payload())


@dataclass(frozen=True)
class RolePolicy:
    role: LogicalModelRole
    allowed_family: ModelFamily
    policy_version: str
    capability_verification_state: CapabilityVerificationState
    require_structured_response: bool | None
    min_context_tokens: int | None
    min_output_tokens: int | None
    pricing_verification_state: PricingVerificationState
    price_ceiling: PriceDimensions | None
    qualification_required: bool = True
    fallback_policy: str = "FORBIDDEN"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "policy_version", _text(self.policy_version, field="policy_version")
        )
        expected = ROLE_FAMILY[self.role]
        if self.allowed_family is not expected:
            raise RoutingError(
                "ROLE_FAMILY_POLICY_INVALID",
                f"{self.role.value} requires the declared {expected.value} family.",
            )
        if self.fallback_policy != "FORBIDDEN" or not self.qualification_required:
            raise RoutingError(
                "ROLE_SAFETY_POLICY_INVALID",
                "Qualification is mandatory and fallback must be FORBIDDEN.",
            )
        if self.capability_verification_state is CapabilityVerificationState.VERIFIED:
            if (
                not isinstance(self.require_structured_response, bool)
                or isinstance(self.min_context_tokens, bool)
                or not isinstance(self.min_context_tokens, int)
                or self.min_context_tokens <= 0
                or isinstance(self.min_output_tokens, bool)
                or not isinstance(self.min_output_tokens, int)
                or self.min_output_tokens <= 0
            ):
                raise RoutingError(
                    "ROLE_CAPABILITY_POLICY_INVALID",
                    "Verified role capabilities require explicit positive envelopes.",
                )
        elif any(value is not None for value in (
            self.require_structured_response,
            self.min_context_tokens,
            self.min_output_tokens,
        )):
            raise RoutingError(
                "ROLE_CAPABILITY_POLICY_INVALID",
                "Unverified role capability policy cannot carry requirements.",
            )
        if self.pricing_verification_state is PricingVerificationState.VERIFIED:
            if self.price_ceiling is None:
                raise RoutingError(
                    "ROLE_PRICING_POLICY_INVALID",
                    "Verified role pricing policy requires every dimension ceiling.",
                )
        elif self.price_ceiling is not None:
            raise RoutingError(
                "ROLE_PRICING_POLICY_INVALID",
                "Unverified role pricing policy cannot carry a cost ceiling.",
            )

    def payload(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "allowed_family": self.allowed_family.value,
            "policy_version": self.policy_version,
            "capability_verification_state": self.capability_verification_state.value,
            "require_structured_response": self.require_structured_response,
            "min_context_tokens": self.min_context_tokens,
            "min_output_tokens": self.min_output_tokens,
            "pricing_verification_state": self.pricing_verification_state.value,
            "price_ceiling": (
                None if self.price_ceiling is None
                else self.price_ceiling.as_storage_mapping()
            ),
            "qualification_required": self.qualification_required,
            "fallback_policy": self.fallback_policy,
        }

    def policy_fingerprint(self) -> str:
        return fingerprint(self.payload())


@dataclass(frozen=True)
class RegisteredModel:
    registry_id: str
    provider: str
    family: ModelFamily
    logical_version: str
    technical_model_id: str | None
    availability_state: AvailabilityState
    pricing_ref: str | None
    capability_ref: str | None
    qualification_state: QualificationState
    qualification_ref: str | None
    lifecycle_state: LifecycleState
    discovered_at: str
    created_at: str
    verified_at: str | None
    qualified_at: str | None
    catalogue_ref: str

    @property
    def version(self) -> ModelVersion:
        return ModelVersion.parse(self.logical_version)


@dataclass(frozen=True)
class FrozenModelBinding:
    intent_kind: str
    intent_id: str
    role: LogicalModelRole
    model_registry_id: str
    provider: str
    family: ModelFamily
    logical_version: str
    technical_model_id: str
    pricing_ref: str
    qualification_ref: str
    capability_ref: str
    activation_decision_fingerprint: str
    fallback_policy: str
    bound_at: str


@dataclass(frozen=True)
class PromotionOutcome:
    role: LogicalModelRole
    status: PromotionStatus
    old_model_registry_id: str | None
    new_model_registry_id: str | None
    decision_fingerprint: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingAuditEvent:
    event_id: str
    event_type: RoutingAuditEventType
    role: LogicalModelRole
    old_model_registry_id: str | None
    new_model_registry_id: str | None
    decision_fingerprint: str
    reason: str
    occurred_at: str
    policy_decision: Mapping[str, Any]


def parse_role(value: object) -> LogicalModelRole:
    try:
        return value if isinstance(value, LogicalModelRole) else LogicalModelRole(str(value))
    except (TypeError, ValueError) as exc:
        raise RoutingError("UNKNOWN_ROLE", f"Unknown logical role: {value!r}.") from exc


def parse_family(value: object) -> ModelFamily:
    try:
        return value if isinstance(value, ModelFamily) else ModelFamily(str(value))
    except (TypeError, ValueError) as exc:
        raise RoutingError("UNKNOWN_FAMILY", f"Unknown model family: {value!r}.") from exc


def candidate_eligibility_reasons(
    *,
    policy: RolePolicy,
    model: RegisteredModel,
    pricing: ModelPricingProfile | None,
    capability: CapabilityDeclaration | None,
) -> tuple[str, ...]:
    """Return every deterministic fail-closed reason for one candidate."""
    reasons: list[str] = []
    if policy.fallback_policy != "FORBIDDEN":
        reasons.append("FALLBACK_POLICY_NOT_FORBIDDEN")
    if model.family is not policy.allowed_family:
        reasons.append("FAMILY_NOT_ALLOWED")
    if model.lifecycle_state is LifecycleState.DEPRECATED:
        reasons.append("MODEL_DEPRECATED")
    if not model.technical_model_id:
        reasons.append("TECHNICAL_MODEL_ID_MISSING")
    if model.availability_state is not AvailabilityState.AVAILABLE:
        reasons.append("AVAILABILITY_NOT_VERIFIED_AVAILABLE")
    if policy.pricing_verification_state is not PricingVerificationState.VERIFIED:
        reasons.append("ROLE_PRICING_POLICY_UNVERIFIED")
    if pricing is None or pricing.verification_state is not PricingVerificationState.VERIFIED:
        reasons.append("PRICING_UNVERIFIED")
    elif (
        pricing.provider != model.provider
        or pricing.technical_model_id != model.technical_model_id
    ):
        reasons.append("PRICING_MODEL_MISMATCH")
    elif policy.price_ceiling is None or pricing.prices is None:
        reasons.append("PRICING_CONTRACT_INCOMPLETE")
    elif not pricing.prices.is_within(policy.price_ceiling):
        reasons.append("ROLE_COST_ENVELOPE_EXCEEDED")
    if (
        policy.capability_verification_state
        is not CapabilityVerificationState.VERIFIED
    ):
        reasons.append("ROLE_CAPABILITY_POLICY_UNVERIFIED")
    if (
        capability is None
        or capability.verification_state is not CapabilityVerificationState.VERIFIED
    ):
        reasons.append("CAPABILITY_UNVERIFIED")
    elif policy.capability_verification_state is CapabilityVerificationState.VERIFIED:
        if (
            policy.require_structured_response
            and not capability.structured_response
        ):
            reasons.append("REQUIRED_STRUCTURED_RESPONSE_MISSING")
        if (
            policy.min_context_tokens is None
            or capability.max_context_tokens is None
            or capability.max_context_tokens < policy.min_context_tokens
        ):
            reasons.append("REQUIRED_CONTEXT_ENVELOPE_MISSING")
        if (
            policy.min_output_tokens is None
            or capability.max_output_tokens is None
            or capability.max_output_tokens < policy.min_output_tokens
        ):
            reasons.append("REQUIRED_OUTPUT_ENVELOPE_MISSING")
    if model.qualification_state is QualificationState.UNQUALIFIED:
        reasons.append("QUALIFICATION_UNQUALIFIED")
    elif model.qualification_state is QualificationState.FAIL:
        reasons.append("QUALIFICATION_FAILED")
    elif not model.qualification_ref:
        reasons.append("QUALIFICATION_REFERENCE_MISSING")
    return tuple(reasons)
