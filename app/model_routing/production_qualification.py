"""Production caller for the one controlled Fable qualification boundary.

This module deliberately does not own authority or lifecycle.  The supported
entrypoint always delegates to ``SqliteStorage.execute_controlled_qualification``
first; that repository method consumes the durable approval and reserves the
``IN_FLIGHT`` run atomically before this caller may reach Anthropic.

Importing or constructing these objects performs no network I/O and reads no
secret.  The API key provider and SDK are resolved lazily by the existing
``ControlledAnthropicAdapter`` at the already-audited provider boundary.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.content.cost_estimate import ROLE_ENVELOPES
from app.llm.anthropic_controlled_adapter import (
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
    ControlledSdkFactory,
    ControlledTechnicalCaller,
)
from app.llm.anthropic_provider_contract import (
    ANTHROPIC_PROVIDER,
    FABLE_5_MODEL_ID,
)
from app.model_routing.catalogue import FABLE_5
from app.model_routing.contracts import LogicalModelRole
from app.model_routing.qualification import (
    ControlledQualificationError,
    QualificationApproval,
    QualificationCaller,
    QualificationOutcome,
    QualificationProbeResponse,
    QualificationProbeUsage,
)


QUALIFICATION_PROMPT_VERSION = "fable_production_qualification_prompt_v1"
QUALIFICATION_CHALLENGE = "NIA-FABLE-QUALIFICATION-CHALLENGE-V1"
QUALIFICATION_TIMEOUT_SECONDS = 30.0

_EXPECTED_RESPONSE = {
    "challenge": QUALIFICATION_CHALLENGE,
    "contract_version": QUALIFICATION_PROMPT_VERSION,
    "structured_response": True,
}
QUALIFICATION_EXPECTED_RESPONSE_JSON = json.dumps(
    _EXPECTED_RESPONSE,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
)
QUALIFICATION_PROMPT = (
    f"Qualification contract: {QUALIFICATION_PROMPT_VERSION}\n"
    "Return exactly one JSON object and no other text.\n"
    "Do not use Markdown or code fences. Do not add, remove, or rename fields.\n"
    "Copy every value exactly, including case.\n"
    f"{QUALIFICATION_EXPECTED_RESPONSE_JSON}"
)
QUALIFICATION_PROMPT_SHA256 = hashlib.sha256(
    QUALIFICATION_PROMPT.encode("utf-8")
).hexdigest()


class ControlledQualificationStorage(Protocol):
    """The already-existing durable orchestration required by the root."""

    def execute_controlled_qualification(
        self,
        approval: QualificationApproval,
        *,
        caller: QualificationCaller,
        now: datetime | None = None,
    ) -> QualificationOutcome: ...


def qualification_prompt_bytes() -> bytes:
    """Return the exact versioned user-prompt bytes sent to the transport."""

    return QUALIFICATION_PROMPT.encode("utf-8")


def qualification_prompt_fingerprint() -> str:
    """Stable SHA-256 identity of the exact qualification prompt bytes."""

    return hashlib.sha256(qualification_prompt_bytes()).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate response field: {key}")
        value[key] = item
    return value


def validate_qualification_response(
    text: object,
    *,
    stop_reason: str | None,
) -> bool:
    """Validate the probe without prose judgment or another model.

    Whitespace around the single JSON value is harmless.  Everything inside
    the object is exact: no duplicate, missing or additional fields, exact
    string challenges, and a real JSON boolean rather than ``1`` or ``"true"``.
    Refusal and truncation fail even if their partial text happens to parse.
    """

    if stop_reason in {"refusal", "max_tokens", "length", "truncated"}:
        return False
    if not isinstance(text, str) or not text.strip():
        return False
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if type(payload) is not dict or set(payload) != set(_EXPECTED_RESPONSE):
        return False
    return (
        type(payload["challenge"]) is str
        and payload["challenge"] == QUALIFICATION_CHALLENGE
        and type(payload["contract_version"]) is str
        and payload["contract_version"] == QUALIFICATION_PROMPT_VERSION
        and type(payload["structured_response"]) is bool
        and payload["structured_response"] is True
    )


def _assert_fable_qualification_contract(approval: QualificationApproval) -> None:
    envelope = ROLE_ENVELOPES[LogicalModelRole.ARTICLE_WRITER]
    expected = {
        "logical_role": LogicalModelRole.ARTICLE_WRITER,
        "provider": ANTHROPIC_PROVIDER,
        "technical_model_id": FABLE_5_MODEL_ID,
        "pricing_ref": FABLE_5.default_pricing_ref,
        "max_input_tokens": envelope.qualification_input_tokens,
        "max_output_tokens": envelope.max_output_tokens,
        "max_retries": 0,
        "fallback_policy": "FORBIDDEN",
    }
    actual = {
        "logical_role": approval.logical_role,
        "provider": approval.provider,
        "technical_model_id": approval.technical_model_id,
        "pricing_ref": approval.pricing_ref,
        "max_input_tokens": approval.max_input_tokens,
        "max_output_tokens": approval.max_output_tokens,
        "max_retries": approval.max_retries,
        "fallback_policy": approval.fallback_policy,
    }
    mismatches = [key for key in expected if actual[key] != expected[key]]
    if mismatches:
        raise ControlledQualificationError(
            "FABLE_PRODUCTION_QUALIFICATION_CONTRACT_MISMATCH",
            "The production Fable qualification root refuses changed fields: "
            + ", ".join(sorted(mismatches)),
        )


class ProductionFableQualificationCaller:
    """Map the frozen Anthropic transport response into qualification evidence."""

    def __init__(self, adapter: ControlledAnthropicAdapter) -> None:
        self._adapter = adapter

    @property
    def caller_calls(self) -> int:
        return self._adapter.caller_calls

    def __call__(self, approval: QualificationApproval) -> QualificationProbeResponse:
        _assert_fable_qualification_contract(approval)
        raw = self._adapter.execute(ControlledProviderRequest(
            technical_model_id=approval.technical_model_id,
            system_prompt="",
            user_prompt=QUALIFICATION_PROMPT,
            # The transport receives the exact approved ceiling.  A later
            # smaller operational limit must be a separately reviewed change.
            max_output_tokens=approval.max_output_tokens,
            timeout_seconds=QUALIFICATION_TIMEOUT_SECONDS,
        ))
        return QualificationProbeResponse(
            # Identity and provenance come from provider metadata carried by
            # the transport, never from text generated by the model.
            returned_model_id=raw.returned_model_id,
            structured_response_ok=validate_qualification_response(
                raw.text,
                stop_reason=raw.stop_reason,
            ),
            usage=QualificationProbeUsage(
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cache_read_tokens=raw.cache_read_tokens,
                cache_write_tokens=raw.cache_write_tokens,
                web_search_requests=raw.web_search_requests,
                inference_geo=raw.inference_geo,
                service_tier=raw.service_tier,
            ),
            stop_reason=raw.stop_reason,
            provider_request_id=raw.provider_request_id,
        )


def execute_fable_production_qualification(
    storage: ControlledQualificationStorage,
    approval: QualificationApproval,
    *,
    api_key_provider: Callable[[], str | None],
    sdk_factory: ControlledSdkFactory | None = None,
    technical_caller: ControlledTechnicalCaller | None = None,
    now: datetime | None = None,
) -> QualificationOutcome:
    """Supported production composition root; authority remains in storage.

    No provider object is invoked before the repository has validated and
    consumed the exact durable approval and reserved its run.  Tests inject a
    fake SDK/transport; a later real call requires a separate owner decision.
    """

    _assert_fable_qualification_contract(approval)
    adapter = ControlledAnthropicAdapter(
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        caller=technical_caller,
    )
    caller = ProductionFableQualificationCaller(adapter)
    return storage.execute_controlled_qualification(
        approval,
        caller=caller,
        now=now,
    )


__all__ = [
    "QUALIFICATION_CHALLENGE",
    "QUALIFICATION_EXPECTED_RESPONSE_JSON",
    "QUALIFICATION_PROMPT",
    "QUALIFICATION_PROMPT_SHA256",
    "QUALIFICATION_PROMPT_VERSION",
    "QUALIFICATION_TIMEOUT_SECONDS",
    "ProductionFableQualificationCaller",
    "execute_fable_production_qualification",
    "qualification_prompt_bytes",
    "qualification_prompt_fingerprint",
    "validate_qualification_response",
]
