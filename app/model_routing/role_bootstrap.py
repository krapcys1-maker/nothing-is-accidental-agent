"""Owner-approved role policies derived from the verified catalogue.

A role policy is the project's own envelope, not a provider fact.  Two of its
parts are derived rather than invented:

* the price ceiling is exactly the highest published rate of the family the
  role is bound to, so today's verified catalogue passes and any future model
  that is more expensive is blocked until a human raises the ceiling;
* the capability minimums are exactly the token ceilings this repository already
  enforces for that role, so a model that cannot accept them is not eligible.

Nothing here promotes or qualifies anything.
"""
from __future__ import annotations

from decimal import Decimal

from app.content.cost_estimate import ROLE_ENVELOPES
from app.model_routing.catalogue import CATALOGUE_BY_FAMILY
from app.model_routing.contracts import (
    CapabilityVerificationState,
    LogicalModelRole,
    PriceDimensions,
    PricingVerificationState,
    ROLE_FAMILY,
    RolePolicy,
    RoutingError,
)

ROLE_POLICY_VERSION = "owner_approved_role_policy_v1"


def family_price_ceiling(role: LogicalModelRole) -> PriceDimensions:
    """The highest verified rate per dimension across the family's profiles."""
    entry = CATALOGUE_BY_FAMILY[ROLE_FAMILY[role]]
    ceilings: dict[str, Decimal] = {}
    for profile in entry.pricing:
        if profile.prices is None:
            continue
        for key, value in profile.prices.as_decimal_mapping().items():
            current = ceilings.get(key)
            ceilings[key] = value if current is None or value > current else current
    if not ceilings:
        raise RoutingError(
            "ROLE_PRICE_CEILING_UNAVAILABLE",
            f"No verified price list exists for {role.value}.",
        )
    return PriceDimensions.from_mapping(ceilings)


def owner_approved_role_policy(role: LogicalModelRole) -> RolePolicy:
    """Build the verified policy for one ARTICLE support/writer role."""
    if role not in ROLE_ENVELOPES:
        raise RoutingError(
            "ROLE_POLICY_UNSUPPORTED",
            f"{role.value} has no approved ARTICLE token envelope yet.",
        )
    envelope = ROLE_ENVELOPES[role]
    return RolePolicy(
        role=role,
        allowed_family=ROLE_FAMILY[role],
        policy_version=ROLE_POLICY_VERSION,
        capability_verification_state=CapabilityVerificationState.VERIFIED,
        require_structured_response=True,
        # The model must accept the whole window this role may occupy.
        min_context_tokens=envelope.max_context_tokens,
        min_output_tokens=envelope.max_output_tokens,
        pricing_verification_state=PricingVerificationState.VERIFIED,
        price_ceiling=family_price_ceiling(role),
    )
