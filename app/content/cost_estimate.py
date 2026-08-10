"""Offline worst-case cost of one controlled ARTICLE execution.

Every number here is derived: the token ceilings come from the limits this
repository actually enforces, and the rates come from the owner-verified
catalogue.  Nothing is a round figure someone picked.

"Worst case" means every ceiling is spent in full: the maximum input the limit
allows plus the maximum output the limit allows, at the standard rate of the
family the role is bound to.  Caching, web search and fast mode are disabled for
C5 and therefore contribute nothing — which is exactly why a non-zero count for
any of them has to fail closed rather than be priced as free.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import quantize_usd
from app.model_routing.catalogue import (
    CATALOGUE_BY_FAMILY,
    CatalogueEntry,
)
from app.model_routing.contracts import (
    LogicalModelRole,
    ModelPricingProfile,
    ROLE_FAMILY,
)

_PER_MILLION = Decimal("1000000")

# The writer ceilings this repository enforces today (app/content/writer.py):
# how much prompt is actually sent, how wide the context window must be, and how
# much output may come back.  Input and context are different numbers, and the
# gate compares against context — so both are recorded here rather than derived.
ARTICLE_WRITER_MAX_INPUT_TOKENS = 8_000
ARTICLE_WRITER_MAX_CONTEXT_TOKENS = 16_000
ARTICLE_WRITER_MAX_OUTPUT_TOKENS = 2_048

# The plan and review roles read the same frozen Research Package and emit a
# compact structured document, so they share the writer's window with a smaller
# output ceiling.
ARTICLE_PLAN_MAX_INPUT_TOKENS = 8_000
ARTICLE_PLAN_MAX_CONTEXT_TOKENS = 16_000
ARTICLE_PLAN_MAX_OUTPUT_TOKENS = 1_024
ARTICLE_REVIEWER_MAX_INPUT_TOKENS = 8_000
ARTICLE_REVIEWER_MAX_CONTEXT_TOKENS = 16_000
ARTICLE_REVIEWER_MAX_OUTPUT_TOKENS = 1_024


@dataclass(frozen=True)
class RoleEnvelope:
    """The token budget one role is allowed to spend and must be able to use."""

    max_input_tokens: int
    max_context_tokens: int
    max_output_tokens: int

    @property
    def qualification_input_tokens(self) -> int:
        """The largest prompt that still fits the window beside a full answer.

        A qualification probe declares this, because what the run has to prove
        is that the model accepts the whole window this role may occupy — not
        merely the smaller prompt the probe happens to send.
        """
        return self.max_context_tokens - self.max_output_tokens


ROLE_ENVELOPES: dict[LogicalModelRole, RoleEnvelope] = {
    LogicalModelRole.ARTICLE_PLAN: RoleEnvelope(
        ARTICLE_PLAN_MAX_INPUT_TOKENS,
        ARTICLE_PLAN_MAX_CONTEXT_TOKENS,
        ARTICLE_PLAN_MAX_OUTPUT_TOKENS,
    ),
    LogicalModelRole.ARTICLE_WRITER: RoleEnvelope(
        ARTICLE_WRITER_MAX_INPUT_TOKENS,
        ARTICLE_WRITER_MAX_CONTEXT_TOKENS,
        ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
    ),
    LogicalModelRole.ARTICLE_REVIEWER: RoleEnvelope(
        ARTICLE_REVIEWER_MAX_INPUT_TOKENS,
        ARTICLE_REVIEWER_MAX_CONTEXT_TOKENS,
        ARTICLE_REVIEWER_MAX_OUTPUT_TOKENS,
    ),
}

# Retained as the (input, output) spend ceilings used for costing.
ROLE_CEILINGS: dict[LogicalModelRole, tuple[int, int]] = {
    role: (envelope.max_input_tokens, envelope.max_output_tokens)
    for role, envelope in ROLE_ENVELOPES.items()
}


@dataclass(frozen=True)
class RoleCostEstimate:
    role: LogicalModelRole
    technical_model_id: str
    pricing_ref: str
    max_input_tokens: int
    max_output_tokens: int
    input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_usd: Decimal
    attempts: int = 1

    @property
    def worst_case_usd(self) -> Decimal:
        return quantize_usd(
            self.total_usd * Decimal(self.attempts), label="role worst case",
        )


def _standard_profile(entry: CatalogueEntry, *, at: str) -> ModelPricingProfile:
    """The one profile effective at ``at``; a promotion never quietly persists."""
    effective = [item for item in entry.pricing if item.is_effective_at(at)]
    if len(effective) != 1:
        raise ValueError(
            f"{entry.technical_model_id} has {len(effective)} price lists "
            f"effective at {at}; exactly one is required for an estimate."
        )
    return effective[0]


def estimate_role_cost(
    role: LogicalModelRole,
    *,
    at: str,
    max_input_tokens: int | None = None,
    max_output_tokens: int | None = None,
    attempts: int = 1,
) -> RoleCostEstimate:
    entry = CATALOGUE_BY_FAMILY[ROLE_FAMILY[role]]
    profile = _standard_profile(entry, at=at)
    assert profile.prices is not None
    ceilings = ROLE_CEILINGS.get(role, (0, 0))
    inputs = max_input_tokens if max_input_tokens is not None else ceilings[0]
    outputs = max_output_tokens if max_output_tokens is not None else ceilings[1]
    dimensions = profile.prices.as_decimal_mapping()
    input_cost = Decimal(inputs) / _PER_MILLION * dimensions["input_per_mtok"]
    output_cost = Decimal(outputs) / _PER_MILLION * dimensions["output_per_mtok"]
    return RoleCostEstimate(
        role=role,
        technical_model_id=entry.technical_model_id,
        pricing_ref=profile.pricing_ref,
        max_input_tokens=inputs,
        max_output_tokens=outputs,
        input_cost_usd=quantize_usd(input_cost, label="input"),
        output_cost_usd=quantize_usd(output_cost, label="output"),
        total_usd=quantize_usd(input_cost + output_cost, label="role total"),
        attempts=attempts,
    )


def estimate_qualification_cost(role: LogicalModelRole, *, at: str) -> RoleCostEstimate:
    """One bootstrap probe, capped by the widest budget it may declare."""
    envelope = ROLE_ENVELOPES[role]
    return estimate_role_cost(
        role,
        at=at,
        max_input_tokens=envelope.qualification_input_tokens,
        max_output_tokens=envelope.max_output_tokens,
    )


@dataclass(frozen=True)
class ControlledArticleCostEstimate:
    at: str
    qualification: tuple[RoleCostEstimate, ...]
    plan: RoleCostEstimate
    writer: RoleCostEstimate
    reviewer: RoleCostEstimate

    @property
    def qualification_total_usd(self) -> Decimal:
        return quantize_usd(
            sum(
                (item.worst_case_usd for item in self.qualification),
                Decimal("0"),
            ),
            label="qualification total",
        )

    @property
    def execution_total_usd(self) -> Decimal:
        return quantize_usd(
            self.plan.worst_case_usd
            + self.writer.worst_case_usd
            + self.reviewer.worst_case_usd,
            label="execution total",
        )

    @property
    def total_usd(self) -> Decimal:
        return quantize_usd(
            self.qualification_total_usd + self.execution_total_usd,
            label="controlled article worst case",
        )


def estimate_controlled_article_cost(
    *, at: str, writer_attempts: int = 2,
) -> ControlledArticleCostEstimate:
    """Worst case for one ARTICLE: bootstrap plus plan, writer and review.

    ``writer_attempts=2`` reflects the durable two-attempt writer lifecycle
    (first draft plus the single permitted rewrite), which is the most this
    pipeline can spend on one content item.
    """
    return ControlledArticleCostEstimate(
        at=at,
        qualification=tuple(
            estimate_qualification_cost(role, at=at)
            for role in (
                LogicalModelRole.ARTICLE_PLAN,
                LogicalModelRole.ARTICLE_WRITER,
                LogicalModelRole.ARTICLE_REVIEWER,
            )
        ),
        plan=estimate_role_cost(LogicalModelRole.ARTICLE_PLAN, at=at),
        writer=estimate_role_cost(
            LogicalModelRole.ARTICLE_WRITER, at=at, attempts=writer_attempts,
        ),
        reviewer=estimate_role_cost(LogicalModelRole.ARTICLE_REVIEWER, at=at),
    )
