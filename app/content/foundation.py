"""Typed, deterministic contracts for the Stage 3 durable content foundation.

There is intentionally no generation logic in this module.  Its only job is to
make a content input, execution and future paid-call intent canonical,
hash-addressed and safe to persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONTENT_EXECUTION = "durable_content_foundation_v1"
CONTENT_CALL_EXECUTION = "durable_content_call_v1"
CONTENT_PROVIDER_STAGE = "content_draft"
CONTENT_INPUT_SCHEMA_VERSION = "content_input_v1"
CONTENT_OUTPUT_SCHEMA_VERSION = "content_output_v1"
CONTENT_PROMPT_VERSION_PLACEHOLDER = "pending_c2"
CONTENT_STYLE_VERSION_PLACEHOLDER = "pending_c2"
ARTICLE_BRIEF_PLACEHOLDER = {"state": "PENDING_C2"}
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


def canonical_json(value: Any) -> str:
    """Return the one accepted JSON representation, rejecting NaN/Infinity."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Value must be finite, canonical JSON data.") from exc


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ContentContractError(ValueError):
    """A content payload or immutable contract is malformed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class ContentType(str, Enum):
    ARTICLE = "ARTICLE"
    NOTE = "NOTE"


class ContentStatus(str, Enum):
    """Closed Stage 3 lifecycle; publishing states are intentionally absent."""

    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    REVISE = "REVISE"
    SKIPPED = "SKIPPED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    FAILED = "FAILED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class ContentExecutionMode(str, Enum):
    """CONTENT jobs are held from the ordinary queue and claimed only by id."""

    FOUNDATION_ONLY = "FOUNDATION_ONLY"
    OFFLINE_PIPELINE = "OFFLINE_PIPELINE"


class ContentInitializationFaultPoint(str, Enum):
    AFTER_CONTENT_INSERT = "AFTER_CONTENT_INSERT"
    AFTER_FROZEN_INPUT_INSERT = "AFTER_FROZEN_INPUT_INSERT"
    AFTER_EVIDENCE_INSERTS = "AFTER_EVIDENCE_INSERTS"
    AFTER_JOB_INSERT = "AFTER_JOB_INSERT"
    BEFORE_PREPARATION_COMMIT = "BEFORE_PREPARATION_COMMIT"
    AFTER_RUN_INSERT = "AFTER_RUN_INSERT"
    AFTER_CONTENT_RUN_INSERT = "AFTER_CONTENT_RUN_INSERT"
    AFTER_JOB_RUN_ATTACH = "AFTER_JOB_RUN_ATTACH"
    BEFORE_EXECUTION_SNAPSHOT_RECHECK = "BEFORE_EXECUTION_SNAPSHOT_RECHECK"
    BEFORE_RUN_INITIALIZATION_COMMIT = "BEFORE_RUN_INITIALIZATION_COMMIT"


class ContentEvaluationKind(str, Enum):
    FACT = "FACT"
    STYLE = "STYLE"
    GROWTH = "GROWTH"


class ContentEvaluationStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class ContentPreparationRequest(BaseModel):
    """Owner-independent identity of one frozen content preparation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=300)
    account_id: str = Field(min_length=1, max_length=200)
    research_card_id: int = Field(gt=0)
    content_type: ContentType
    execution_mode: ContentExecutionMode = ContentExecutionMode.FOUNDATION_ONLY
    max_attempts: int = Field(default=3, ge=2, le=10)
    input_schema_version: str = Field(
        default=CONTENT_INPUT_SCHEMA_VERSION, min_length=1, max_length=100,
    )
    output_schema_version: str = Field(
        default=CONTENT_OUTPUT_SCHEMA_VERSION, min_length=1, max_length=100,
    )
    prompt_version: str = Field(
        default=CONTENT_PROMPT_VERSION_PLACEHOLDER, min_length=1, max_length=100,
    )
    style_guide_version: str = Field(
        default=CONTENT_STYLE_VERSION_PLACEHOLDER, min_length=1, max_length=200,
    )
    article_brief_placeholder: dict[str, Any] = Field(
        default_factory=lambda: dict(ARTICLE_BRIEF_PLACEHOLDER),
    )

    @model_validator(mode="after")
    def validate_controlled_strings(self) -> "ContentPreparationRequest":
        for name in (
            "job_id", "idempotency_key", "account_id", "input_schema_version",
            "output_schema_version", "prompt_version", "style_guide_version",
        ):
            value = getattr(self, name)
            if value != value.strip() or any(ord(ch) < 32 for ch in value):
                raise ValueError(f"{name} must be a trimmed controlled string.")
        canonical_json(self.article_brief_placeholder)
        return self


class FrozenEvidenceItem(BaseModel):
    """One claim→source→excerpt→retrieval edge frozen for fact audit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int = Field(ge=0)
    account_id: str = Field(min_length=1)
    topic_id: int = Field(gt=0)
    research_run_id: str = Field(min_length=1)
    research_job_id: str = Field(min_length=1)
    research_card_id: int = Field(gt=0)
    confirmed_claim_id: str = Field(min_length=1)
    confirmed_claim_ordinal: int = Field(ge=0)
    claim_text: str = Field(min_length=1)
    claim_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_id: int = Field(gt=0)
    source_id: int = Field(gt=0)
    source_url: str = Field(min_length=1)
    source_url_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_claim_text: str = Field(min_length=1)
    source_claim_sha256: str = Field(pattern=_SHA256_PATTERN)
    excerpt_id: int = Field(gt=0)
    excerpt_text: str = Field(min_length=1)
    excerpt_sha256: str = Field(pattern=_SHA256_PATTERN)
    retrieval_id: int = Field(gt=0)
    requested_url_sha256: str = Field(pattern=_SHA256_PATTERN)
    final_url_sha256: str = Field(pattern=_SHA256_PATTERN)
    canonical_sha256: str = Field(pattern=_SHA256_PATTERN)
    lineage_fingerprint: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_hashes_and_claim_identity(self) -> "FrozenEvidenceItem":
        expected = {
            "claim_sha256": sha256_text(self.claim_text),
            "source_url_sha256": sha256_text(self.source_url),
            "source_claim_sha256": sha256_text(self.source_claim_text),
            "excerpt_sha256": sha256_text(self.excerpt_text),
        }
        for field, digest in expected.items():
            if getattr(self, field) != digest:
                raise ValueError(f"{field} does not match its persisted preimage.")
        return self


class FrozenContentInput(BaseModel):
    """Immutable snapshot whose hash is the content intent's primary fence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_id: int = Field(gt=0)
    account_id: str = Field(min_length=1)
    research_card_id: int = Field(gt=0)
    content_type: ContentType
    input_schema_version: str = Field(min_length=1)
    output_schema_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    style_guide_version: str = Field(min_length=1)
    article_brief_placeholder_json: str
    article_brief_placeholder_sha256: str = Field(pattern=_SHA256_PATTERN)
    research_card_snapshot_json: str
    evidence_manifest_json: str
    evidence_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_snapshot_json: str
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    evidence_items: tuple[FrozenEvidenceItem, ...]
    created_at: datetime

    @model_validator(mode="after")
    def validate_preimages(self) -> "FrozenContentInput":
        pairs = (
            (self.article_brief_placeholder_json, self.article_brief_placeholder_sha256),
            (self.evidence_manifest_json, self.evidence_manifest_sha256),
            (self.input_snapshot_json, self.input_sha256),
        )
        for preimage, digest in pairs:
            if canonical_json(json.loads(preimage)) != preimage:
                raise ValueError("Frozen JSON preimages must use canonical serialization.")
            if sha256_text(preimage) != digest:
                raise ValueError("Frozen JSON hash does not match its preimage.")
        if canonical_json(json.loads(self.research_card_snapshot_json)) != self.research_card_snapshot_json:
            raise ValueError("Research Card snapshot must use canonical serialization.")
        manifest = json.loads(self.evidence_manifest_json)
        if manifest != [item.model_dump(mode="json") for item in self.evidence_items]:
            raise ValueError("Evidence rows do not equal the frozen manifest.")
        if [item.ordinal for item in self.evidence_items] != list(range(len(self.evidence_items))):
            raise ValueError("Evidence ordinals must be contiguous from zero.")
        return self


class ContentItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(gt=0)
    account_id: str
    research_card_id: int = Field(gt=0)
    content_type: ContentType
    status: ContentStatus
    job_id: str
    run_id: str | None = None
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    intent_key: str = Field(pattern=_SHA256_PATTERN)
    reason_code: str | None = None
    final_result: dict[str, Any] | None = None
    score: float | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_score(self) -> "ContentItem":
        if self.score is not None and (
            not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0
        ):
            raise ValueError("Content score must be finite and between 0 and 1.")
        return self


class ContentRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    content_id: int = Field(gt=0)
    job_id: str
    account_id: str
    research_card_id: int = Field(gt=0)
    workflow: ContentType
    input_sha256: str = Field(pattern=_SHA256_PATTERN)
    status: ContentStatus
    reason_code: str | None = None
    final_result: dict[str, Any] | None = None
    score: float | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


@dataclass(frozen=True)
class ContentInitialization:
    content: ContentItem
    frozen_input: FrozenContentInput
    job_created: bool
    run: ContentRun | None = None


@dataclass(frozen=True)
class ContentTransitionResult:
    content: ContentItem
    run: ContentRun
    idempotent: bool


class ContentCallIntent(BaseModel):
    """Immutable pre-network contract; C1 never executes a real provider call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str = Field(min_length=1, max_length=200)
    job_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    content_id: int = Field(gt=0)
    account_id: str = Field(min_length=1, max_length=200)
    research_card_id: int = Field(gt=0)
    content_type: ContentType
    stage: str = Field(default=CONTENT_PROVIDER_STAGE, min_length=1, max_length=100)
    frozen_input_sha256: str = Field(pattern=_SHA256_PATTERN)
    article_brief_sha256: str = Field(pattern=_SHA256_PATTERN)
    evidence_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    pricing_profile_id: str = Field(min_length=1, max_length=200)
    pricing_profile_version: str = Field(min_length=1, max_length=100)
    pricing_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    max_input_tokens: int = Field(gt=0)
    max_context_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    web_searches: int = Field(default=0, ge=0, le=0)
    max_retries: int = Field(default=0, ge=0, le=0)
    attempt_no: int = Field(default=1, ge=1, le=1)
    prompt_version: str = Field(min_length=1, max_length=100)
    style_guide_version: str = Field(min_length=1, max_length=200)
    output_schema_version: str = Field(min_length=1, max_length=100)
    max_cost_usd: float = Field(gt=0)
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_limits(self) -> "ContentCallIntent":
        if self.stage != CONTENT_PROVIDER_STAGE:
            raise ValueError(f"Content provider stage must be {CONTENT_PROVIDER_STAGE}.")
        if self.max_input_tokens > self.max_context_tokens:
            raise ValueError("max_input_tokens cannot exceed max_context_tokens.")
        if not math.isfinite(self.max_cost_usd):
            raise ValueError("max_cost_usd must be finite.")
        if self.expires_at <= self.created_at:
            raise ValueError("Content call intent must expire after it is created.")
        return self

    def payload(self) -> dict[str, Any]:
        return {
            "execution": CONTENT_CALL_EXECUTION,
            "intent_id": self.intent_id,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "content_id": self.content_id,
            "account_id": self.account_id,
            "research_card_id": self.research_card_id,
            "content_type": self.content_type.value,
            "stage": self.stage,
            "frozen_input_sha256": self.frozen_input_sha256,
            "article_brief_sha256": self.article_brief_sha256,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "provider": self.provider,
            "model": self.model,
            "pricing_profile_id": self.pricing_profile_id,
            "pricing_profile_version": self.pricing_profile_version,
            "pricing_fingerprint": self.pricing_fingerprint,
            "max_input_tokens": self.max_input_tokens,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "web_searches": self.web_searches,
            "max_retries": self.max_retries,
            "attempt_no": self.attempt_no,
            "prompt_version": self.prompt_version,
            "style_guide_version": self.style_guide_version,
            "output_schema_version": self.output_schema_version,
            "max_cost_usd": format(self.max_cost_usd, ".6f"),
            "expires_at": _timestamp(self.expires_at),
        }

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class ContentEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int | None = Field(default=None, gt=0)
    content_id: int = Field(gt=0)
    account_id: str
    job_id: str
    run_id: str
    kind: ContentEvaluationKind
    audit_version: str = Field(min_length=1, max_length=100)
    status: ContentEvaluationStatus
    score: float | None = Field(default=None, ge=0, le=1)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


def content_job_payload(
    *,
    account_id: str,
    research_card_id: int,
    content_id: int,
    content_type: ContentType,
    frozen_input_sha256: str,
    evidence_manifest_sha256: str,
    intent_key: str,
    execution_mode: ContentExecutionMode = ContentExecutionMode.FOUNDATION_ONLY,
) -> dict[str, Any]:
    payload = {
        "execution": CONTENT_EXECUTION,
        "execution_mode": execution_mode.value,
        "account_id": account_id,
        "research_card_id": research_card_id,
        "content_id": content_id,
        "content_type": content_type.value,
        "frozen_input_sha256": frozen_input_sha256,
        "evidence_manifest_sha256": evidence_manifest_sha256,
        "intent_key": intent_key,
        "provider_enabled": False,
    }
    return canonicalize_content_job_payload(payload)


def canonicalize_content_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "execution",
        "execution_mode",
        "account_id",
        "research_card_id",
        "content_id",
        "content_type",
        "frozen_input_sha256",
        "evidence_manifest_sha256",
        "intent_key",
        "provider_enabled",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ContentContractError(
            "CONTENT_PAYLOAD_SHAPE_INVALID",
            "content foundation payload must contain the exact v1 field set.",
        )
    if payload.get("execution") != CONTENT_EXECUTION:
        raise ContentContractError(
            "CONTENT_EXECUTION_UNSUPPORTED", "unsupported content execution contract.",
        )
    try:
        execution_mode = ContentExecutionMode(payload.get("execution_mode"))
    except (TypeError, ValueError) as exc:
        raise ContentContractError(
            "CONTENT_EXECUTION_MODE_UNSUPPORTED",
            "content execution mode is not supported.",
        ) from exc
    if payload.get("provider_enabled") is not False:
        raise ContentContractError(
            "CONTENT_PROVIDER_FORBIDDEN", "CONTENT jobs cannot enable a real provider.",
        )
    try:
        ContentType(payload.get("content_type"))
    except (TypeError, ValueError) as exc:
        raise ContentContractError(
            "CONTENT_TYPE_INVALID", "content_type must be ARTICLE or NOTE.",
        ) from exc
    if not isinstance(payload.get("research_card_id"), int) or payload["research_card_id"] <= 0:
        raise ContentContractError("CONTENT_CARD_INVALID", "research_card_id must be positive.")
    if not isinstance(payload.get("content_id"), int) or payload["content_id"] <= 0:
        raise ContentContractError("CONTENT_ID_INVALID", "content_id must be positive.")
    if not isinstance(payload.get("account_id"), str) or not payload["account_id"].strip():
        raise ContentContractError("CONTENT_ACCOUNT_INVALID", "account_id must be non-empty.")
    for field in ("frozen_input_sha256", "evidence_manifest_sha256", "intent_key"):
        value = payload.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            raise ContentContractError(
                "CONTENT_HASH_INVALID", f"{field} must be a lowercase SHA-256.",
            )
    canonical_json(payload)
    return dict(payload)


def _timestamp(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        return normalized.strftime("%Y-%m-%d %H:%M:%S.%f")
    return normalized.strftime("%Y-%m-%d %H:%M:%S")
