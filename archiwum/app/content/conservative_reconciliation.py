"""Typed owner adjudication for ambiguous historical CONTENT provider effects."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class ConservativeReconciliationError(RuntimeError):
    """Fail-closed refusal of a conservative owner adjudication."""


class ConservativeSourceType(str, Enum):
    PROVIDER_ATTEMPT = "PROVIDER_ATTEMPT"
    ROLE_EXECUTION = "ROLE_EXECUTION"


class ConservativeResolution(str, Enum):
    CONSERVATIVE_MAX_CHARGED = "CONSERVATIVE_MAX_CHARGED"


CONSERVATIVE_EVIDENCE_KIND = "OWNER_CONSERVATIVE_ADJUDICATION"
CONSERVATIVE_APPROVAL_SCHEMA = "conservative_content_reconciliation_approval_v1"
CONSERVATIVE_AUDIT_SCHEMA = "conservative_content_reconciliation_audit_v1"


class ConservativeReconciliationRecord(BaseModel):
    reconciliation_id: str
    source_type: ConservativeSourceType
    source_identity: str
    job_id: str
    content_id: int | None
    run_id: str | None
    provider: str
    model: str
    previous_status: str
    resolution: ConservativeResolution
    reserved_amount_usd: Decimal
    conservative_cost_usd: Decimal
    actual_cost_usd: None = None
    evidence_kind: str
    reason: str
    approved_by: str
    approved_at: str
    approval_fingerprint: str
    created_at: str
    audit_fingerprint: str


class ConservativeReconciliationPlan(BaseModel):
    record: ConservativeReconciliationRecord
    approval_json: str
    audit_json: str
    existing: bool = False
    idempotent: bool = False


class ConservativeCostSummary(BaseModel):
    actual_known_cost_usd: Decimal
    conservative_adjudicated_cost_usd: Decimal
    unresolved_provider_exposure_usd: Decimal
    effective_budget_spend_usd: Decimal


def canonical_approval_instant(value: str | datetime) -> str:
    """Require an explicit UTC owner timestamp and preserve microsecond identity."""

    if isinstance(value, str):
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConservativeReconciliationError(
                "approved_at must be an ISO-8601 UTC timestamp."
            ) from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ConservativeReconciliationError(
            "approved_at must be an ISO-8601 UTC timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ConservativeReconciliationError("approved_at must use UTC.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
