"""Typed contracts for the WAVE C2 offline content pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.content.foundation import ContentType, canonical_json, sha256_text


CONTENT_PLAN_VERSION = "content_plan_v1"
ARTICLE_BRIEF_VERSION = "article_brief_v1"
NOTE_BRIEF_VERSION = "note_brief_v1"
WRITER_INTENT_VERSION = "offline_writer_intent_v1"
DRAFT_VERSION = "fake_content_draft_v1"
EVALUATOR_VERSION = "offline_content_evaluators_v1"
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
        if any(
            value != "UNVERIFIED"
            for value in (
                self.provider,
                self.api_model_id,
                self.availability,
                self.pricing_profile,
            )
        ):
            raise ValueError("C2 technical model fields must remain UNVERIFIED.")
        if self.fallback != "FORBIDDEN":
            raise ValueError("C2 routing cannot define a fallback.")
        return self


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
    call_mode: str = "FAKE"
    route: RouteContract
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    brief_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    style_profile_id: str
    negative_style_profile_id: str
    rewrite_of_draft_fingerprint: str | None = None
    rewrite_feedback: tuple[dict[str, Any], ...] = ()
    max_cost_usd: float = Field(default=0.0, ge=0.0, le=0.0)

    @model_validator(mode="after")
    def validate_attempt(self) -> "WriterIntent":
        if self.call_mode != "FAKE":
            raise ValueError("C2 exposes only the FAKE writer mode.")
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
