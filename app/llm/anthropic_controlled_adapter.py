"""Anthropic composition adapter for controlled ARTICLE execution.

This module can build a real client.  Controlled ARTICLE composition roots still
refuse a real execution.  The separately reviewed Fable qualification module
now composes this transport only behind the durable approval/run lifecycle; its
tests inject a fake factory and never make a real request.

The adapter exists so that the C5 decision is a decision about *authorisation*,
not about writing provider code under time pressure.

Fixed properties, none of them configurable at call time:

* the technical model ID comes from the frozen binding and nowhere else — not
  from settings, not from the environment, not from a CLI flag, not from the
  legacy route key, not from the caller's own suggestion;
* ``max_retries=0`` on the SDK and no application-level retry;
* no provider Fallback API, no Batch API, no fast mode, no prompt caching, no
  server-side web search or fetch;
* explicit ``inference_geo="global"`` and
  ``service_tier="standard_only"`` on every request;
* the secret is read at the final execution boundary only, never at import;
* the returned model identity is checked against the requested one.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
from typing import Any, Callable, Mapping, Protocol

from app.llm.anthropic_provider_contract import (
    ANTHROPIC_PROVIDER,
    APPLICATION_MAX_RETRIES as CONTRACT_APPLICATION_MAX_RETRIES,
    AnthropicRequestContract,
    CANONICAL_ANTHROPIC_REQUEST_CONTRACT,
    CONTROLLED_INFERENCE_GEO,
    CONTROLLED_SERVICE_TIER,
    EXPECTED_RETURNED_INFERENCE_GEO,
    EXPECTED_RETURNED_SERVICE_TIER,
    FALLBACK_POLICY,
    SDK_MAX_RETRIES as CONTRACT_SDK_MAX_RETRIES,
)

SDK_MAX_RETRIES = CONTRACT_SDK_MAX_RETRIES
APPLICATION_MAX_RETRIES = CONTRACT_APPLICATION_MAX_RETRIES
INFERENCE_GEOGRAPHY = CONTROLLED_INFERENCE_GEO
SERVICE_TIER = CONTROLLED_SERVICE_TIER

# Every provider feature C5 runs without. They are listed explicitly so that a
# future change is a visible edit here rather than an implicit default.
DISABLED_PROVIDER_FEATURES: Mapping[str, bool] = {
    "fast_mode": False,
    "prompt_caching": False,
    "server_web_search": False,
    "server_web_fetch": False,
    "batch_api": False,
    "provider_fallback_api": False,
    "us_only_inference": False,
}


class ControlledAdapterError(RuntimeError):
    """A typed fail-closed refusal before or around a provider call."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ControlledProviderRequest:
    """One fully frozen request. Nothing here may be widened at call time."""

    technical_model_id: str
    system_prompt: str
    user_prompt: str
    max_output_tokens: int
    timeout_seconds: float
    provider_contract: AnthropicRequestContract | None = (
        CANONICAL_ANTHROPIC_REQUEST_CONTRACT
    )
    tools: tuple[Mapping[str, Any], ...] | None = None
    extra_headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.technical_model_id.strip():
            raise ControlledAdapterError(
                "ADAPTER_MODEL_ID_MISSING",
                "A controlled request requires the frozen technical model ID.",
            )
        if self.max_output_tokens <= 0:
            raise ControlledAdapterError(
                "ADAPTER_OUTPUT_LIMIT_INVALID",
                "A controlled request requires a positive output ceiling.",
            )
        if (
            not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0.0
        ):
            raise ControlledAdapterError(
                "ADAPTER_TIMEOUT_INVALID",
                "A controlled request requires a finite positive timeout.",
            )
        if self.tools is not None and any(
            not isinstance(tool, Mapping) for tool in self.tools
        ):
            raise ControlledAdapterError(
                "ADAPTER_TOOLS_INVALID",
                "Controlled provider tools must be explicit mappings.",
            )
        if self.extra_headers is not None and any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.extra_headers.items()
        ):
            raise ControlledAdapterError(
                "ADAPTER_HEADERS_INVALID",
                "Controlled provider headers must be string mappings.",
            )


@dataclass(frozen=True)
class ControlledProviderRawResponse:
    """Exactly what the adapter is willing to carry back."""

    returned_model_id: str
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_search_requests: int
    stop_reason: str | None
    provider_request_id: str | None
    inference_geo: str | None = None
    service_tier: str | None = None
    thinking_tokens: int = 0
    structured_web_search_results: int = 0


class ControlledSdkFactory(Protocol):
    def __call__(
        self, *, api_key: str, max_retries: int, timeout: float,
    ) -> object: ...


class ControlledTechnicalCaller(Protocol):
    def __call__(
        self, client: object, request: ControlledProviderRequest,
    ) -> ControlledProviderRawResponse: ...


def _default_sdk_factory(
    *, api_key: str, max_retries: int, timeout: float,
) -> object:  # pragma: no cover - requires separately authorised real execution
    anthropic = importlib.import_module("anthropic")
    return anthropic.Anthropic(
        api_key=api_key, max_retries=max_retries, timeout=timeout,
    )


def _default_caller(
    client: object, request: ControlledProviderRequest,
) -> ControlledProviderRawResponse:  # pragma: no cover - real boundary
    contract = request.provider_contract
    if contract is None:  # validated by execute; defensive for direct tests
        raise ControlledAdapterError(
            "ADAPTER_PROVIDER_CONTRACT_MISSING",
            "The canonical Anthropic provider contract is required.",
        )
    kwargs: dict[str, Any] = dict(
        model=request.technical_model_id,
        max_tokens=request.max_output_tokens,
        system=request.system_prompt,
        messages=[{"role": "user", "content": request.user_prompt}],
        inference_geo=contract.inference_geo,
        service_tier=contract.service_tier,
        timeout=request.timeout_seconds,
    )
    if request.tools:
        kwargs["tools"] = [dict(tool) for tool in request.tools]
    if request.extra_headers:
        kwargs["extra_headers"] = dict(request.extra_headers)
    message = client.messages.create(**kwargs)
    usage = getattr(message, "usage", None)
    content = tuple(getattr(message, "content", ()) or ())
    text = "".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    )
    structured_web_search_results = 0
    for block in content:
        if getattr(block, "type", "") != "web_search_tool_result":
            continue
        for result in tuple(getattr(block, "content", ()) or ()):
            if getattr(result, "type", "") == "web_search_result":
                structured_web_search_results += 1
    return ControlledProviderRawResponse(
        returned_model_id=str(getattr(message, "model", "")),
        text=text,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        ),
        web_search_requests=int(
            getattr(
                getattr(usage, "server_tool_use", None), "web_search_requests", 0,
            ) or 0
        ),
        inference_geo=getattr(usage, "inference_geo", None),
        service_tier=getattr(usage, "service_tier", None),
        stop_reason=getattr(message, "stop_reason", None),
        provider_request_id=getattr(message, "id", None),
        thinking_tokens=int(
            getattr(
                getattr(getattr(message, "usage", None), "output_tokens_details", None),
                "thinking_tokens",
                0,
            ) or 0
        ),
        structured_web_search_results=structured_web_search_results,
    )


def assert_canonical_provider_contract(
    contract: AnthropicRequestContract | None,
) -> AnthropicRequestContract:
    """Fail before SDK construction when any frozen request field is absent/drifts."""
    if contract is None:
        raise ControlledAdapterError(
            "ADAPTER_PROVIDER_CONTRACT_MISSING",
            "The canonical Anthropic provider contract is required.",
        )
    checks = (
        (contract.provider, ANTHROPIC_PROVIDER, "ADAPTER_PROVIDER_MISMATCH"),
        (
            contract.inference_geo,
            CONTROLLED_INFERENCE_GEO,
            "ADAPTER_INFERENCE_GEO_UNSUPPORTED",
        ),
        (
            contract.service_tier,
            CONTROLLED_SERVICE_TIER,
            "ADAPTER_SERVICE_TIER_UNSUPPORTED",
        ),
        (contract.fallback_policy, FALLBACK_POLICY, "ADAPTER_FALLBACK_FORBIDDEN"),
        (
            contract.application_retries,
            APPLICATION_MAX_RETRIES,
            "ADAPTER_APPLICATION_RETRIES_FORBIDDEN",
        ),
        (
            contract.sdk_retries,
            SDK_MAX_RETRIES,
            "ADAPTER_SDK_RETRIES_FORBIDDEN",
        ),
    )
    for actual, expected, code in checks:
        if actual != expected:
            raise ControlledAdapterError(
                code,
                f"Canonical Anthropic request field must equal {expected!r}.",
            )
    return contract


class ControlledAnthropicAdapter:
    """Lazy, single-shot, frozen-identity Anthropic boundary."""

    provider = "ANTHROPIC"

    def __init__(
        self,
        *,
        api_key_provider: Callable[[], str | None],
        sdk_factory: ControlledSdkFactory | None = None,
        caller: ControlledTechnicalCaller | None = None,
    ) -> None:
        self._api_key_provider = api_key_provider
        self._sdk_factory = sdk_factory or _default_sdk_factory
        self._caller = caller or _default_caller
        self.caller_calls = 0

    @staticmethod
    def disabled_features() -> Mapping[str, bool]:
        return dict(DISABLED_PROVIDER_FEATURES)

    def execute(
        self, request: ControlledProviderRequest,
    ) -> ControlledProviderRawResponse:
        """Make at most one call and refuse a response from another model."""
        contract = assert_canonical_provider_contract(request.provider_contract)
        try:
            secret = self._api_key_provider()
        except Exception as exc:  # a broken secret source is not a soft failure
            raise ControlledAdapterError(
                "ADAPTER_SECRET_UNAVAILABLE",
                "The provider secret could not be resolved.",
            ) from exc
        if not isinstance(secret, str) or not secret.strip():
            raise ControlledAdapterError(
                "ADAPTER_SECRET_UNAVAILABLE",
                "The provider secret is unavailable at the execution boundary.",
            )
        client = self._sdk_factory(
            api_key=secret,
            max_retries=contract.sdk_retries,
            timeout=request.timeout_seconds,
        )
        self.caller_calls += 1
        raw = self._caller(client, request)
        if not isinstance(raw, ControlledProviderRawResponse):
            raise ControlledAdapterError(
                "ADAPTER_RESPONSE_CONTRACT_INVALID",
                "The technical caller returned an unsupported response shape.",
            )
        return raw


def assert_returned_model_identity(
    *, requested_model_id: str, returned_model_id: str,
) -> None:
    """The one gate that makes provider-side rerouting detectable.

    A provider answering as another model is not a success to be retried on yet
    another model; it is a divergence between what was authorised and what ran.
    """
    if returned_model_id != requested_model_id:
        raise ControlledAdapterError(
            "RETURNED_MODEL_MISMATCH",
            f"requested {requested_model_id!r} but the response names "
            f"{returned_model_id!r}; runtime fallback is forbidden.",
        )


def assert_no_disabled_feature_usage(
    *,
    cache_read_tokens: int,
    cache_write_tokens: int,
    web_search_requests: int,
) -> None:
    """Usage for a feature the request never enabled is never free usage."""
    if cache_read_tokens or cache_write_tokens:
        raise ControlledAdapterError(
            "UNEXPECTED_CACHE_USAGE",
            "prompt caching is disabled for C5, so cache usage is unaccounted.",
        )
    if web_search_requests:
        raise ControlledAdapterError(
            "UNEXPECTED_WEB_SEARCH_USAGE",
            "server web search is disabled for C5, so this usage is unaccounted.",
        )


def describe_runtime_shape() -> dict[str, Any]:
    """The exact runtime shape the owner-verified catalogue was priced against."""
    return {
        "provider": ControlledAnthropicAdapter.provider,
        "inference_geo_request": INFERENCE_GEOGRAPHY,
        "service_tier_request": SERVICE_TIER,
        "expected_response_inference_geo": EXPECTED_RETURNED_INFERENCE_GEO,
        "expected_response_service_tier": EXPECTED_RETURNED_SERVICE_TIER,
        "sdk_max_retries": SDK_MAX_RETRIES,
        "application_max_retries": APPLICATION_MAX_RETRIES,
        "fallback_policy": "FORBIDDEN",
        **DISABLED_PROVIDER_FEATURES,
    }
