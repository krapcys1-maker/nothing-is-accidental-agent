"""Controlled composition root for exact-model role authority.

This module grants no authority by construction.  It applies the owner policy,
asks the existing promotion lifecycle to select an eligible qualified model,
then freezes that exact active decision for one durable execution intent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.model_routing.contracts import (
    FrozenModelBinding,
    LogicalModelRole,
    PromotionStatus,
    RoutingError,
)
from app.model_routing.role_bootstrap import (
    ANTHROPIC_PROVIDER,
    OPUS_5_MODEL_ID,
    owner_approved_role_policy,
)


@dataclass(frozen=True)
class ExactRoleActivationRequest:
    role: LogicalModelRole
    intent_kind: str
    intent_id: str
    provider: str = ANTHROPIC_PROVIDER
    technical_model_id: str = OPUS_5_MODEL_ID
    reason: str = "owner-approved exact-model activation"


def activate_and_bind_exact_role(
    storage: object,
    request: ExactRoleActivationRequest,
    *,
    now: datetime | None = None,
) -> FrozenModelBinding:
    """Apply policy -> promote -> verify exact active model -> freeze binding."""

    if request.role not in {
        LogicalModelRole.TOPIC_GENERATION,
        LogicalModelRole.ARTICLE_RESEARCH,
    }:
        raise RoutingError(
            "ROLE_ACTIVATION_UNSUPPORTED",
            "This root activates only TOPIC_GENERATION or ARTICLE_RESEARCH.",
        )
    policy = owner_approved_role_policy(request.role)
    if (
        request.provider != policy.allowed_provider
        or request.technical_model_id != policy.allowed_technical_model_id
    ):
        raise RoutingError(
            "EXACT_MODEL_AUTHORITY_MISMATCH",
            "The requested provider/model is outside the owner-approved policy.",
        )
    storage.upsert_model_role_policy(policy, now=now)
    promotion = storage.promote_best_model(request.role, reason=request.reason, now=now)
    if promotion.status is PromotionStatus.BLOCKED:
        raise RoutingError(
            "ROLE_ACTIVATION_BLOCKED",
            ",".join(promotion.reasons) or "No eligible exact model.",
        )
    active = storage.get_active_model_for_role(request.role)
    if active is None or (
        active.provider != request.provider
        or active.technical_model_id != request.technical_model_id
    ):
        raise RoutingError(
            "ACTIVE_EXACT_MODEL_MISMATCH",
            "Promotion did not produce the requested exact active model.",
        )
    binding = storage.freeze_model_for_intent(
        request.role,
        intent_kind=request.intent_kind,
        intent_id=request.intent_id,
        now=now,
    )
    if (
        binding.provider != request.provider
        or binding.technical_model_id != request.technical_model_id
        or binding.fallback_policy != "FORBIDDEN"
    ):
        raise RoutingError(
            "FROZEN_EXACT_MODEL_MISMATCH",
            "The frozen binding is not the approved exact no-fallback model.",
        )
    return binding
