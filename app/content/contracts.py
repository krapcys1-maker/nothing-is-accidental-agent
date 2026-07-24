"""Typed contracts shared by the offline C2 and provider-ready C3 writers."""
from __future__ import annotations

from enum import Enum
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.content.foundation import (
    ContentType,
    FrozenEvidenceItem,
    canonical_json,
    sha256_text,
)


CONTENT_PLAN_VERSION = "content_plan_v1"
ARTICLE_BRIEF_VERSION = "article_brief_v1"
NOTE_BRIEF_VERSION = "note_brief_v1"
WRITER_INTENT_VERSION = "provider_ready_writer_intent_v1"
DRAFT_VERSION = "content_draft_v2"
EVALUATOR_VERSION = "offline_content_evaluators_v1"
WRITER_PROMPT_VERSION = "content_writer_prompt_v1"
WRITER_RESULT_VERSION = "content_writer_result_v1"
ARTICLE_STYLE_PROFILE_ID = "ARTICLE_STYLE_PROFILE_V1"
ARTICLE_NEGATIVE_STYLE_PROFILE_ID = "ARTICLE_NEGATIVE_STYLE_PROFILE_V1"
NOTES_STYLE_PROFILE_ID = "NOTES_STYLE_PROFILE_V1_PROVISIONAL"


class PipelineDecision(str, Enum):
    PASS = "PASS"
    REWRITE_ONCE = "REWRITE_ONCE"
    BLOCK = "BLOCK"


class EvaluationType(str, Enum):
    EVIDENCE_COVERAGE = "EVIDENCE_COVERAGE"
    UNSUPPORTED_CLAIMS = "UNSUPPORTED_CLAIMS"
    BRAND_TOPIC_POLICY = "BRAND_TOPIC_POLICY"
    STYLE_PROFILE = "STYLE_PROFILE"
    NEGATIVE_STYLE_PROFILE = "NEGATIVE_STYLE_PROFILE"
    CONTENT_TYPE_LENGTH = "CONTENT_TYPE_LENGTH"
    FAKE_PERSONAL_EXPERIENCE = "FAKE_PERSONAL_EXPERIENCE"
    TITLE_HOOK_ALIGNMENT = "TITLE_HOOK_ALIGNMENT"
    BRIEF_COMPLIANCE = "BRIEF_COMPLIANCE"


class WriterCallMode(str, Enum):
    FAKE = "FAKE"
    PROVIDER_READY_OFFLINE = "PROVIDER_READY_OFFLINE"
    CONTROLLED_PROVIDER = "CONTROLLED_PROVIDER"


class WriterFailureKind(str, Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    MISSING_PRICING = "MISSING_PRICING"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    RATE_LIMIT = "RATE_LIMIT"
    PROVIDER_5XX = "PROVIDER_5XX"
    AUTH_PERMISSION = "AUTH_PERMISSION"
    INVALID_REQUEST = "INVALID_REQUEST"
    TRUNCATION = "TRUNCATION"
    PARSE_ERROR = "PARSE_ERROR"
    SCHEMA_VALIDATION = "SCHEMA_VALIDATION"
    UNSUPPORTED_ROUTE = "UNSUPPORTED_ROUTE"
    STALE_FENCE = "STALE_FENCE"
    UNCERTAIN_STATE = "UNCERTAIN_STATE"
    UNKNOWN_PROVIDER = "UNKNOWN_PROVIDER"


class RouteContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content_type: ContentType
    route_key: str
    logical_model_name: str
    config_version: str
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = "UNVERIFIED"
    api_model_id: str = "UNVERIFIED"
    availability: str = "UNVERIFIED"
    pricing_profile: str = "UNVERIFIED"
    fallback: str = "FORBIDDEN"

    @model_validator(mode="after")
    def validate_closed_route(self) -> "RouteContract":
        expected = {
            ContentType.ARTICLE: "FABLE_5_ARTICLE",
            ContentType.NOTE: "SONNET_5_NOTE",
        }[self.content_type]
        if self.route_key != expected:
            raise ValueError(f"{self.content_type.value} requires route {expected}.")
        if self.fallback != "FORBIDDEN":
            raise ValueError("Content routing cannot define a fallback.")
        if self.availability not in {"UNVERIFIED", "CONFIGURED"}:
            raise ValueError(
                "Route availability is a configuration status, not a live claim."
            )
        if any(not value.strip() for value in (
            self.provider,
            self.api_model_id,
            self.pricing_profile,
        )):
            raise ValueError("Technical route fields cannot be blank.")
        return self

    @property
    def configuration_status(self) -> str:
        technical = (self.provider, self.api_model_id, self.pricing_profile)
        if (
            all(value == "UNVERIFIED" for value in technical)
            and self.availability == "UNVERIFIED"
        ):
            return "UNVERIFIED"
        if (
            all(value != "UNVERIFIED" for value in technical)
            and self.availability == "CONFIGURED"
        ):
            return "CONFIGURED"
        return "INCOMPLETE"

    @property
    def is_provider_configured(self) -> bool:
        return self.configuration_status == "CONFIGURED"


class ContentPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = CONTENT_PLAN_VERSION
    content_id: int = Field(gt=0)
    account_id: str
    research_card_id: int = Field(gt=0)
    content_type: ContentType
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    route: RouteContract
    central_thesis: str
    answer_question: str
    narrative_angle: str
    target_reader: str
    evidence_ids: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    brand_topic_policy: str = "PASS"

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class ArticleBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = ARTICLE_BRIEF_VERSION
    content_type: ContentType = ContentType.ARTICLE
    working_title: str
    central_thesis: str
    answer_question: str
    narrative_angle: str
    target_reader: str
    concrete_opening: str
    argument_structure: tuple[str, ...]
    required_facts: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    counterargument_or_limitation: str
    ending: str
    min_words: int = Field(ge=100)
    max_words: int = Field(gt=100)
    style_profile_id: str = ARTICLE_STYLE_PROFILE_ID
    negative_style_profile_id: str = ARTICLE_NEGATIVE_STYLE_PROFILE_ID
    forbidden_claims: tuple[str, ...]
    brand_topic_policy: str = "PASS"

    @model_validator(mode="after")
    def validate_length(self) -> "ArticleBrief":
        if self.max_words <= self.min_words:
            raise ValueError("Article maximum must exceed minimum.")
        return self


class NoteBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = NOTE_BRIEF_VERSION
    content_type: ContentType = ContentType.NOTE
    main_point: str
    format: str
    hook: str
    evidence_ids: tuple[str, ...]
    opinion_label: str | None = None
    min_words: int = Field(ge=20)
    max_words: int = Field(gt=20)
    tone: str
    style_profile_id: str = NOTES_STYLE_PROFILE_ID
    negative_style_profile_id: str = ARTICLE_NEGATIVE_STYLE_PROFILE_ID
    forbidden_claims: tuple[str, ...]
    brand_topic_policy: str = "PASS"

    @model_validator(mode="after")
    def validate_evidence_or_opinion(self) -> "NoteBrief":
        if not self.evidence_ids and self.opinion_label != "OPINION":
            raise ValueError("Note must carry frozen evidence or an explicit OPINION label.")
        if self.max_words <= self.min_words:
            raise ValueError("Note maximum must exceed minimum.")
        return self


ContentBrief = ArticleBrief | NoteBrief


class WriterLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_input_tokens: int = Field(gt=0)
    max_context_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_cost_usd: float = Field(ge=0.0)
    timeout_seconds: float = Field(gt=0.0, le=30.0)

    @model_validator(mode="after")
    def validate_limits(self) -> "WriterLimits":
        if self.max_input_tokens > self.max_context_tokens:
            raise ValueError("Writer input token limit cannot exceed context limit.")
        if not math.isfinite(self.max_cost_usd) or not math.isfinite(
            self.timeout_seconds
        ):
            raise ValueError("Writer cost and timeout limits must be finite.")
        return self


class WriterPolicyConstraints(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brand_topic_policy: str = "PASS"
    fallback: str = "FORBIDDEN"
    web_searches: int = Field(default=0, ge=0, le=0)
    forbid_fictional_personal_experience: bool = True
    forbid_public_build_information: bool = True

    @model_validator(mode="after")
    def validate_closed_policy(self) -> "WriterPolicyConstraints":
        if self.brand_topic_policy != "PASS":
            raise ValueError("Writer requires a passing brand-topic policy.")
        if self.fallback != "FORBIDDEN":
            raise ValueError("Writer fallback must remain forbidden.")
        if not (
            self.forbid_fictional_personal_experience
            and self.forbid_public_build_information
        ):
            raise ValueError("C3 identity and public-build protections are mandatory.")
        return self


class WriterContext(BaseModel):
    """All durable, evidence-bounded inputs consumed by one writer attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: ContentPlan
    brief: ContentBrief
    research_card: dict[str, Any]
    frozen_evidence: tuple[FrozenEvidenceItem, ...]
    style_profile: str
    negative_style_profile: str
    policy: WriterPolicyConstraints
    limits: WriterLimits

    @model_validator(mode="after")
    def validate_context(self) -> "WriterContext":
        if not self.style_profile.strip() or not self.negative_style_profile.strip():
            raise ValueError("Writer style profiles cannot be empty.")
        if self.plan.content_type is not self.brief.content_type:
            raise ValueError("Writer plan and brief content types disagree.")
        if int(self.research_card.get("id", 0)) != self.plan.research_card_id:
            raise ValueError("Writer Research Card identity disagrees with the plan.")
        allowed_ids = set(self.brief.evidence_ids)
        observed_ids = {item.confirmed_claim_id for item in self.frozen_evidence}
        if not observed_ids or not observed_ids.issubset(allowed_ids):
            raise ValueError(
                "Writer context contains missing or out-of-brief evidence."
            )
        if self.plan.route.fallback != self.policy.fallback:
            raise ValueError("Writer route and policy fallback disagree.")
        if self.brief.brand_topic_policy != self.policy.brand_topic_policy:
            raise ValueError("Writer brief and brand policy disagree.")
        if self.brief.style_profile_id not in {
            ARTICLE_STYLE_PROFILE_ID,
            NOTES_STYLE_PROFILE_ID,
        }:
            raise ValueError("Writer brief uses an unsupported style profile.")
        return self


class WriterPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = WRITER_PROMPT_VERSION
    system: str
    user: str

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class WriterIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = WRITER_INTENT_VERSION
    intent_id: str
    job_id: str
    run_id: str
    content_id: int = Field(gt=0)
    account_id: str
    content_type: ContentType
    attempt_no: int = Field(ge=1, le=2)
    call_mode: WriterCallMode = WriterCallMode.FAKE
    route: RouteContract
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    brief_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    style_profile_id: str
    negative_style_profile_id: str
    prompt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    limits: WriterLimits
    rewrite_of_draft_fingerprint: str | None = None
    rewrite_feedback: tuple[dict[str, Any], ...] = ()

    @model_validator(mode="after")
    def validate_attempt(self) -> "WriterIntent":
        if self.call_mode in {
            WriterCallMode.FAKE,
            WriterCallMode.PROVIDER_READY_OFFLINE,
        } and self.limits.max_cost_usd != 0.0:
            raise ValueError("Offline writer modes require an exact zero cost cap.")
        if (
            self.call_mode is WriterCallMode.CONTROLLED_PROVIDER
            and self.limits.max_cost_usd <= 0.0
        ):
            raise ValueError("Controlled provider mode requires a positive cost cap.")
        if (
            self.call_mode is WriterCallMode.CONTROLLED_PROVIDER
            and not self.route.is_provider_configured
        ):
            raise ValueError("Controlled writer intent requires a configured route.")
        if (
            self.call_mode is WriterCallMode.FAKE
            and self.route.configuration_status != "UNVERIFIED"
        ):
            raise ValueError("Fake writer intent cannot claim provider configuration.")
        if self.attempt_no == 1 and (
            self.rewrite_of_draft_fingerprint is not None or self.rewrite_feedback
        ):
            raise ValueError("First attempt cannot be a rewrite.")
        if self.attempt_no == 2 and self.rewrite_of_draft_fingerprint is None:
            raise ValueError("Second attempt must identify the first draft.")
        return self

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class FakeDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = DRAFT_VERSION
    attempt_no: int = Field(ge=1, le=2)
    route_key: str
    title: str
    body: str
    evidence_ids_used: tuple[str, ...]
    unsupported_claims: tuple[str, ...] = ()
    personal_experience: bool = False
    style_ok: bool = True
    brief_compliant: bool = True
    rewrite_of_draft_fingerprint: str | None = None

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class ProviderDraftPayload(BaseModel):
    """Strict provider output before durable attempt/route fields are attached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    evidence_ids_used: tuple[str, ...]
    unsupported_claims: tuple[str, ...] = ()
    personal_experience: bool = False
    style_ok: bool = True
    brief_compliant: bool = True


class WriterUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_cost(self) -> "WriterUsage":
        if not math.isfinite(self.estimated_cost_usd):
            raise ValueError("Writer usage cost must be finite.")
        return self


class WriterSuccess(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = WRITER_RESULT_VERSION
    status: Literal["SUCCESS"] = "SUCCESS"
    draft: FakeDraft
    provider: str
    route_key: str
    api_model_id: str | None = None
    usage: WriterUsage
    stop_reason: str | None = None
    provider_request_id: str | None = None

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


class WriterFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = WRITER_RESULT_VERSION
    status: Literal["FAILURE"] = "FAILURE"
    kind: WriterFailureKind
    provider: str
    route_key: str
    api_model_id: str | None = None
    usage: WriterUsage | None = None
    stop_reason: str | None = None
    provider_request_id: str | None = None
    detail: str
    uncertain: bool = False

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return sha256_text(self.canonical_preimage())


WriterResult = WriterSuccess | WriterFailure


class WriterRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: WriterIntent
    context: WriterContext
    prompt: WriterPrompt

    @model_validator(mode="after")
    def validate_request(self) -> "WriterRequest":
        intent = self.intent
        context = self.context
        if (
            context.plan.content_id != intent.content_id
            or context.plan.account_id != intent.account_id
            or context.plan.content_type is not intent.content_type
            or context.plan.route != intent.route
            or context.plan.fingerprint() != intent.plan_fingerprint
            or context.plan.frozen_input_sha256 != intent.frozen_input_sha256
            or context.plan.evidence_manifest_sha256
            != intent.evidence_manifest_sha256
            or context.brief.style_profile_id != intent.style_profile_id
            or context.brief.negative_style_profile_id
            != intent.negative_style_profile_id
            or context.limits != intent.limits
            or self.prompt.fingerprint() != intent.prompt_fingerprint
        ):
            raise ValueError("Writer request disagrees with its durable intent.")
        return self

    @property
    def brief(self) -> ContentBrief:
        return self.context.brief

    @property
    def frozen_evidence(self) -> tuple[FrozenEvidenceItem, ...]:
        return self.context.frozen_evidence

    @property
    def style_profile(self) -> str:
        return self.context.style_profile

    @property
    def negative_style_profile(self) -> str:
        return self.context.negative_style_profile

    @property
    def max_cost_usd(self) -> float:
        return self.context.limits.max_cost_usd


class DraftEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_type: EvaluationType
    evaluator_version: str = EVALUATOR_VERSION
    result: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    findings: tuple[dict[str, Any], ...] = ()
    draft_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: PipelineDecision

    @model_validator(mode="after")
    def validate_result(self) -> "DraftEvaluation":
        if self.result not in {"PASS", "FAIL"}:
            raise ValueError("Evaluation result must be PASS or FAIL.")
        if self.result == "PASS" and self.decision is not PipelineDecision.PASS:
            raise ValueError("Passing evaluation must have PASS decision.")
        if self.result == "FAIL" and self.decision is PipelineDecision.PASS:
            raise ValueError("Failed evaluation cannot have PASS decision.")
        return self
