"""Production callers for controlled Anthropic qualification boundaries.

This module deliberately does not own authority or lifecycle.  The supported
entrypoint always delegates to ``SqliteStorage.execute_controlled_qualification``
first; that repository method consumes the durable approval and reserves the
``IN_FLIGHT`` run atomically before this caller may reach Anthropic.

Importing or constructing these objects performs no network I/O and reads no
secret.  The API key provider and SDK are resolved lazily by the existing
``ControlledAnthropicAdapter`` at the already-audited provider boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.llm.anthropic_controlled_adapter import (
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
    ControlledSdkFactory,
    ControlledTechnicalCaller,
)
from app.llm.anthropic_provider_contract import (
    ANTHROPIC_PROVIDER,
    inference_config_for_role,
)
from app.model_routing.catalogue import FABLE_5, OPUS_5, CatalogueEntry
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


@dataclass(frozen=True)
class ProductionQualificationContract:
    """One frozen local probe contract bound to an owner-verified model."""

    logical_role: LogicalModelRole
    catalogue_entry: CatalogueEntry
    prompt_version: str
    challenge: str
    mismatch_code: str
    max_input_tokens: int
    max_output_tokens: int
    require_source_discovery: bool = False

    @property
    def expected_response(self) -> dict[str, object]:
        return {
            "challenge": self.challenge,
            "contract_version": self.prompt_version,
            "structured_response": True,
        }

    @property
    def expected_response_json(self) -> str:
        return json.dumps(
            self.expected_response,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    @property
    def prompt(self) -> str:
        source_discovery_instruction = (
            "Use the web_search tool exactly once before answering. Find one "
            "authoritative source about hidden dependencies in fragile systems.\n"
            if self.require_source_discovery else ""
        )
        return (
            f"Qualification contract: {self.prompt_version}\n"
            f"{source_discovery_instruction}"
            "Return exactly one JSON object and no other text.\n"
            "Do not use Markdown or code fences. Do not add, remove, or rename fields.\n"
            "Copy every value exactly, including case.\n"
            f"{self.expected_response_json}"
        )


FABLE_PRODUCTION_QUALIFICATION_CONTRACT = ProductionQualificationContract(
    logical_role=LogicalModelRole.ARTICLE_WRITER,
    catalogue_entry=FABLE_5,
    prompt_version=QUALIFICATION_PROMPT_VERSION,
    challenge=QUALIFICATION_CHALLENGE,
    mismatch_code="FABLE_PRODUCTION_QUALIFICATION_CONTRACT_MISMATCH",
    max_input_tokens=13_952,
    max_output_tokens=2_048,
)
OPUS_PRODUCTION_QUALIFICATION_CONTRACT = ProductionQualificationContract(
    logical_role=LogicalModelRole.ARTICLE_WRITER,
    catalogue_entry=OPUS_5,
    prompt_version="opus_production_qualification_prompt_v1",
    challenge="NIA-OPUS-QUALIFICATION-CHALLENGE-V1",
    mismatch_code="OPUS_PRODUCTION_QUALIFICATION_CONTRACT_MISMATCH",
    max_input_tokens=13_952,
    max_output_tokens=2_048,
)
OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT = ProductionQualificationContract(
    logical_role=LogicalModelRole.ARTICLE_RESEARCH,
    catalogue_entry=OPUS_5,
    prompt_version="opus_article_research_qualification_prompt_v1",
    challenge="NIA-OPUS-ARTICLE-RESEARCH-QUALIFICATION-V1",
    mismatch_code="OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT_MISMATCH",
    max_input_tokens=23_808,
    max_output_tokens=8_192,
    require_source_discovery=True,
)

# Historical public names remain byte-identical aliases for the Fable probe
# that was actually executed.  They must never be rebound to the Opus switch.
QUALIFICATION_EXPECTED_RESPONSE_JSON = (
    FABLE_PRODUCTION_QUALIFICATION_CONTRACT.expected_response_json
)
QUALIFICATION_PROMPT = FABLE_PRODUCTION_QUALIFICATION_CONTRACT.prompt
QUALIFICATION_PROMPT_SHA256 = hashlib.sha256(
    QUALIFICATION_PROMPT.encode("utf-8")
).hexdigest()

OPUS_QUALIFICATION_PROMPT_VERSION = OPUS_PRODUCTION_QUALIFICATION_CONTRACT.prompt_version
OPUS_QUALIFICATION_CHALLENGE = OPUS_PRODUCTION_QUALIFICATION_CONTRACT.challenge
OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON = (
    OPUS_PRODUCTION_QUALIFICATION_CONTRACT.expected_response_json
)
OPUS_QUALIFICATION_PROMPT = OPUS_PRODUCTION_QUALIFICATION_CONTRACT.prompt
OPUS_QUALIFICATION_PROMPT_SHA256 = hashlib.sha256(
    OPUS_QUALIFICATION_PROMPT.encode("utf-8")
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
    contract: ProductionQualificationContract = FABLE_PRODUCTION_QUALIFICATION_CONTRACT,
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
    expected = contract.expected_response
    if type(payload) is not dict or set(payload) != set(expected):
        return False
    return (
        type(payload["challenge"]) is str
        and payload["challenge"] == contract.challenge
        and type(payload["contract_version"]) is str
        and payload["contract_version"] == contract.prompt_version
        and type(payload["structured_response"]) is bool
        and payload["structured_response"] is True
    )


def _assert_production_qualification_contract(
    approval: QualificationApproval,
    contract: ProductionQualificationContract,
) -> None:
    expected = {
        "logical_role": contract.logical_role,
        "provider": ANTHROPIC_PROVIDER,
        "technical_model_id": contract.catalogue_entry.technical_model_id,
        "pricing_ref": contract.catalogue_entry.default_pricing_ref,
        "max_input_tokens": contract.max_input_tokens,
        "max_output_tokens": contract.max_output_tokens,
        "max_retries": 0,
        "fallback_policy": "FORBIDDEN",
        "require_source_discovery": contract.require_source_discovery,
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
        "require_source_discovery": approval.require_source_discovery,
    }
    mismatches = [key for key in expected if actual[key] != expected[key]]
    if mismatches:
        raise ControlledQualificationError(
            contract.mismatch_code,
            "The production qualification root refuses changed fields: "
            + ", ".join(sorted(mismatches)),
        )


class ProductionQualificationCaller:
    """Map the frozen Anthropic transport response into qualification evidence."""

    def __init__(
        self,
        adapter: ControlledAnthropicAdapter,
        contract: ProductionQualificationContract,
    ) -> None:
        self._adapter = adapter
        self._contract = contract

    @property
    def caller_calls(self) -> int:
        return self._adapter.caller_calls

    def __call__(self, approval: QualificationApproval) -> QualificationProbeResponse:
        _assert_production_qualification_contract(approval, self._contract)
        raw = self._adapter.execute(ControlledProviderRequest(
            technical_model_id=approval.technical_model_id,
            system_prompt="",
            user_prompt=self._contract.prompt,
            # The transport receives the exact approved ceiling.  A later
            # smaller operational limit must be a separately reviewed change.
            max_output_tokens=approval.max_output_tokens,
            timeout_seconds=QUALIFICATION_TIMEOUT_SECONDS,
            inference_config=inference_config_for_role(approval.logical_role),
            tools=(
                ({
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 1,
                },)
                if self._contract.require_source_discovery else None
            ),
        ))
        return QualificationProbeResponse(
            # Identity and provenance come from provider metadata carried by
            # the transport, never from text generated by the model.
            returned_model_id=raw.returned_model_id,
            structured_response_ok=validate_qualification_response(
                raw.text,
                stop_reason=raw.stop_reason,
                contract=self._contract,
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
            source_discovery_ok=(
                raw.web_search_requests >= 1
                and raw.structured_web_search_results >= 1
            ) if self._contract.require_source_discovery else False,
        )


class ProductionFableQualificationCaller(ProductionQualificationCaller):
    """Historical Fable caller retained for immutable audit reproducibility."""

    def __init__(self, adapter: ControlledAnthropicAdapter) -> None:
        super().__init__(adapter, FABLE_PRODUCTION_QUALIFICATION_CONTRACT)


class ProductionOpusQualificationCaller(ProductionQualificationCaller):
    """Current ARTICLE_WRITER qualification caller for Opus."""

    def __init__(self, adapter: ControlledAnthropicAdapter) -> None:
        super().__init__(adapter, OPUS_PRODUCTION_QUALIFICATION_CONTRACT)


class ProductionOpusArticleResearchQualificationCaller(ProductionQualificationCaller):
    """Qualification caller for the 32k ARTICLE_RESEARCH web-search boundary."""

    def __init__(self, adapter: ControlledAnthropicAdapter) -> None:
        super().__init__(adapter, OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT)


def _execute_production_qualification(
    storage: ControlledQualificationStorage,
    approval: QualificationApproval,
    *,
    contract: ProductionQualificationContract,
    api_key_provider: Callable[[], str | None],
    sdk_factory: ControlledSdkFactory | None = None,
    technical_caller: ControlledTechnicalCaller | None = None,
    now: datetime | None = None,
) -> QualificationOutcome:
    _assert_production_qualification_contract(approval, contract)
    adapter = ControlledAnthropicAdapter(
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        caller=technical_caller,
    )
    caller = ProductionQualificationCaller(adapter, contract)
    return storage.execute_controlled_qualification(
        approval,
        caller=caller,
        now=now,
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

    return _execute_production_qualification(
        storage,
        approval,
        contract=FABLE_PRODUCTION_QUALIFICATION_CONTRACT,
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        technical_caller=technical_caller,
        now=now,
    )


def execute_opus_production_qualification(
    storage: ControlledQualificationStorage,
    approval: QualificationApproval,
    *,
    api_key_provider: Callable[[], str | None],
    sdk_factory: ControlledSdkFactory | None = None,
    technical_caller: ControlledTechnicalCaller | None = None,
    now: datetime | None = None,
) -> QualificationOutcome:
    """Current ARTICLE_WRITER root; tests inject only the final transport."""

    return _execute_production_qualification(
        storage,
        approval,
        contract=OPUS_PRODUCTION_QUALIFICATION_CONTRACT,
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        technical_caller=technical_caller,
        now=now,
    )


def execute_opus_article_research_production_qualification(
    storage: ControlledQualificationStorage,
    approval: QualificationApproval,
    *,
    api_key_provider: Callable[[], str | None],
    sdk_factory: ControlledSdkFactory | None = None,
    technical_caller: ControlledTechnicalCaller | None = None,
    now: datetime | None = None,
) -> QualificationOutcome:
    """Qualify exact Opus 5 for ARTICLE_RESEARCH and structured web search."""

    return _execute_production_qualification(
        storage,
        approval,
        contract=OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT,
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        technical_caller=technical_caller,
        now=now,
    )


__all__ = [
    "FABLE_PRODUCTION_QUALIFICATION_CONTRACT",
    "OPUS_PRODUCTION_QUALIFICATION_CONTRACT",
    "OPUS_ARTICLE_RESEARCH_QUALIFICATION_CONTRACT",
    "OPUS_QUALIFICATION_CHALLENGE",
    "OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON",
    "OPUS_QUALIFICATION_PROMPT",
    "OPUS_QUALIFICATION_PROMPT_SHA256",
    "OPUS_QUALIFICATION_PROMPT_VERSION",
    "QUALIFICATION_CHALLENGE",
    "QUALIFICATION_EXPECTED_RESPONSE_JSON",
    "QUALIFICATION_PROMPT",
    "QUALIFICATION_PROMPT_SHA256",
    "QUALIFICATION_PROMPT_VERSION",
    "QUALIFICATION_TIMEOUT_SECONDS",
    "ProductionOpusQualificationCaller",
    "ProductionOpusArticleResearchQualificationCaller",
    "ProductionQualificationCaller",
    "ProductionQualificationContract",
    "ProductionFableQualificationCaller",
    "execute_fable_production_qualification",
    "execute_opus_production_qualification",
    "execute_opus_article_research_production_qualification",
    "qualification_prompt_bytes",
    "qualification_prompt_fingerprint",
    "validate_qualification_response",
]
