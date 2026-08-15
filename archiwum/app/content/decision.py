"""Typed, provider-independent contracts for the WAVE C4 decision boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.content.foundation import ContentStatus, ContentType, canonical_json, sha256_text


CONTENT_DECISION_SCHEMA_VERSION = "content_decision_v1"


class ContentDecisionActor(str, Enum):
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    AUTONOMOUS = "AUTONOMOUS"


class ContentDecisionOutcome(str, Enum):
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE_INPUT = "STALE_INPUT"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


@dataclass(frozen=True)
class ContentDecisionPlan:
    """One immutable PolicyEngine result ready for fenced persistence.

    ``input`` is the complete canonical preimage used by the decision.  It
    includes the current durable account policy, content/draft identity, exact
    evaluations and the current versioned threshold configuration.
    """

    decision_id: str
    content_id: int
    account_id: str
    job_id: str
    run_id: str
    draft_id: int
    draft_fingerprint: str
    content_type: ContentType
    autonomy_level: str
    account_mode: str
    actor: ContentDecisionActor
    outcome: ContentDecisionOutcome
    reason_code: str
    lifecycle_status: ContentStatus
    policy_version: str
    threshold: float
    score: float | None
    input: dict[str, Any]
    input_fingerprint: str
    decision_fingerprint: str

    @classmethod
    def build(
        cls,
        *,
        content_id: int,
        account_id: str,
        job_id: str,
        run_id: str,
        draft_id: int,
        draft_fingerprint: str,
        content_type: ContentType,
        autonomy_level: str,
        account_mode: str,
        actor: ContentDecisionActor,
        outcome: ContentDecisionOutcome,
        reason_code: str,
        lifecycle_status: ContentStatus,
        policy_version: str,
        threshold: float,
        score: float | None,
        input: dict[str, Any],
    ) -> "ContentDecisionPlan":
        input_fingerprint = sha256_text(canonical_json(input))
        decision_id = f"content-decision:{content_id}:{draft_fingerprint}:{input_fingerprint}"
        payload = {
            "schema_version": CONTENT_DECISION_SCHEMA_VERSION,
            "decision_id": decision_id,
            "content_id": content_id,
            "account_id": account_id,
            "job_id": job_id,
            "run_id": run_id,
            "draft_id": draft_id,
            "draft_fingerprint": draft_fingerprint,
            "content_type": content_type.value,
            "autonomy_level": autonomy_level,
            "account_mode": account_mode,
            "actor": actor.value,
            "outcome": outcome.value,
            "reason_code": reason_code,
            "lifecycle_status": lifecycle_status.value,
            "policy_version": policy_version,
            "threshold": threshold,
            "score": score,
            "input_fingerprint": input_fingerprint,
        }
        return cls(
            decision_id=decision_id,
            content_id=content_id,
            account_id=account_id,
            job_id=job_id,
            run_id=run_id,
            draft_id=draft_id,
            draft_fingerprint=draft_fingerprint,
            content_type=content_type,
            autonomy_level=autonomy_level,
            account_mode=account_mode,
            actor=actor,
            outcome=outcome,
            reason_code=reason_code,
            lifecycle_status=lifecycle_status,
            policy_version=policy_version,
            threshold=threshold,
            score=score,
            input=input,
            input_fingerprint=input_fingerprint,
            decision_fingerprint=sha256_text(canonical_json(payload)),
        )

    def decision_payload(self) -> dict[str, Any]:
        return {
            "schema_version": CONTENT_DECISION_SCHEMA_VERSION,
            "decision_id": self.decision_id,
            "content_id": self.content_id,
            "account_id": self.account_id,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "draft_id": self.draft_id,
            "draft_fingerprint": self.draft_fingerprint,
            "content_type": self.content_type.value,
            "autonomy_level": self.autonomy_level,
            "account_mode": self.account_mode,
            "actor": self.actor.value,
            "outcome": self.outcome.value,
            "reason_code": self.reason_code,
            "lifecycle_status": self.lifecycle_status.value,
            "policy_version": self.policy_version,
            "threshold": self.threshold,
            "score": self.score,
            "input_fingerprint": self.input_fingerprint,
        }

    def as_stale(self, *, reason_code: str) -> "ContentDecisionPlan":
        """Return a durable fail-closed observation for a changed preimage."""
        return ContentDecisionPlan.build(
            content_id=self.content_id,
            account_id=self.account_id,
            job_id=self.job_id,
            run_id=self.run_id,
            draft_id=self.draft_id,
            draft_fingerprint=self.draft_fingerprint,
            content_type=self.content_type,
            autonomy_level=self.autonomy_level,
            account_mode=self.account_mode,
            actor=ContentDecisionActor.AUTONOMOUS,
            outcome=ContentDecisionOutcome.STALE_INPUT,
            reason_code=reason_code,
            lifecycle_status=ContentStatus.NEEDS_VERIFICATION,
            policy_version=self.policy_version,
            threshold=self.threshold,
            score=self.score,
            input={
                **self.input,
                "stale_against_input_fingerprint": self.input_fingerprint,
            },
        )
