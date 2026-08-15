"""Stage 3 content package.

Wave C1 remains the durable lifecycle foundation. Wave C2 adds the deterministic
planner/evaluation pipeline. Wave C3 adds a provider-ready writer boundary that
is exercised only with fake callers and SDKs. Wave C4 adds an offline,
provider-independent decision boundary: human-required results remain
``PENDING_APPROVAL`` and eligible autonomous results become ``APPROVED`` or
``REJECTED``. No real-provider composition root, browser, approval UI or
publication adapter is exposed.
"""

from app.content.foundation import (
    CONTENT_EXECUTION,
    CONTENT_INPUT_SCHEMA_VERSION,
    CONTENT_OUTPUT_SCHEMA_VERSION,
    CONTENT_PROVIDER_STAGE,
    ContentCallIntent,
    ContentEvaluation,
    ContentEvaluationKind,
    ContentEvaluationStatus,
    ContentExecutionMode,
    ContentInitialization,
    ContentInitializationFaultPoint,
    ContentItem,
    ContentPreparationRequest,
    ContentRun,
    ContentStatus,
    ContentTransitionResult,
    ContentType,
    FrozenContentInput,
    FrozenEvidenceItem,
    canonical_json,
    canonicalize_content_job_payload,
    content_job_payload,
    sha256_text,
)

__all__ = [
    "CONTENT_EXECUTION",
    "CONTENT_INPUT_SCHEMA_VERSION",
    "CONTENT_OUTPUT_SCHEMA_VERSION",
    "CONTENT_PROVIDER_STAGE",
    "ContentCallIntent",
    "ContentEvaluation",
    "ContentEvaluationKind",
    "ContentEvaluationStatus",
    "ContentExecutionMode",
    "ContentInitialization",
    "ContentInitializationFaultPoint",
    "ContentItem",
    "ContentPreparationRequest",
    "ContentRun",
    "ContentStatus",
    "ContentTransitionResult",
    "ContentType",
    "FrozenContentInput",
    "FrozenEvidenceItem",
    "canonical_json",
    "canonicalize_content_job_payload",
    "content_job_payload",
    "sha256_text",
]
