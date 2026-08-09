"""Offline model-family routing and qualification core.

This package intentionally replaces the unused ``app.llm.model_router`` for
new, registry-backed routing.  It has no provider catalogue adapter and never
performs network I/O on its own.
"""

from app.model_routing.contracts import (
    AvailabilityState,
    CapabilityDeclaration,
    CapabilityVerificationState,
    CatalogueCandidate,
    FrozenModelBinding,
    LifecycleState,
    LogicalModelRole,
    ModelFamily,
    ModelPricingProfile,
    ModelVersion,
    PriceDimensions,
    PricingVerificationState,
    PromotionOutcome,
    PromotionStatus,
    QualificationReport,
    QualificationState,
    RegisteredModel,
    RolePolicy,
    RoutingAuditEvent,
    RoutingAuditEventType,
    RoutingError,
)
from app.model_routing.service import (
    ModelCatalogueSource,
    ModelQualificationRunner,
    ModelRoutingService,
    TechnicalModelCaller,
)

__all__ = [
    "AvailabilityState",
    "CapabilityDeclaration",
    "CapabilityVerificationState",
    "CatalogueCandidate",
    "FrozenModelBinding",
    "LifecycleState",
    "LogicalModelRole",
    "ModelCatalogueSource",
    "ModelFamily",
    "ModelPricingProfile",
    "ModelQualificationRunner",
    "ModelRoutingService",
    "ModelVersion",
    "PriceDimensions",
    "PricingVerificationState",
    "PromotionOutcome",
    "PromotionStatus",
    "QualificationReport",
    "QualificationState",
    "RegisteredModel",
    "RolePolicy",
    "RoutingAuditEvent",
    "RoutingAuditEventType",
    "RoutingError",
    "TechnicalModelCaller",
]
