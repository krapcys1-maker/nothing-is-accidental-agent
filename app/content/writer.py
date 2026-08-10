"""Fake and provider-ready writers behind one typed, fail-closed boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import importlib
import json
import math
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from app.content.contracts import (
    ArticleBrief,
    FakeDraft,
    ProviderDraftPayload,
    WriterCallMode,
    WriterFailure,
    WriterFailureKind,
    WriterLimits,
    WriterPrompt,
    WriterRequest,
    WriterResult,
    WriterSuccess,
    WriterUsage,
)
from app.content.foundation import ContentType
from app.llm.anthropic_provider_contract import (
    CONTROLLED_INFERENCE_GEO,
    CONTROLLED_SERVICE_TIER,
    returned_provenance_mismatch,
)


_SDK_MAX_RETRIES = 0


class FakeWriterScenario(str, Enum):
    PASS = "PASS"
    REWRITE_THEN_PASS = "REWRITE_THEN_PASS"
    ALWAYS_REWRITE = "ALWAYS_REWRITE"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    PERSONAL_EXPERIENCE = "PERSONAL_EXPERIENCE"


@dataclass(frozen=True)
class ProviderRawResponse:
    text: str
    usage: WriterUsage
    stop_reason: str | None
    provider_request_id: str | None
    api_model_id: str


class ContentWriterCaller(Protocol):
    def __call__(
        self,
        client: object,
        prompt: WriterPrompt,
        request: WriterRequest,
    ) -> ProviderRawResponse: ...


class ContentWriterSdkFactory(Protocol):
    def __call__(
        self,
        *,
        api_key: str,
        max_retries: int,
        timeout: float,
    ) -> object: ...


class WriterPort(Protocol):
    @property
    def call_mode(self) -> WriterCallMode: ...

    def limits_for(self, content_type: ContentType) -> WriterLimits: ...

    def preflight(self, request: WriterRequest) -> WriterFailure | None: ...

    def write(self, request: WriterRequest) -> WriterResult: ...


def _fake_limits(content_type: ContentType) -> WriterLimits:
    if content_type is ContentType.ARTICLE:
        return WriterLimits(
            max_input_tokens=8_000,
            max_context_tokens=16_000,
            max_output_tokens=2_048,
            max_cost_usd=0.0,
            timeout_seconds=1.0,
        )
    return WriterLimits(
        max_input_tokens=4_000,
        max_context_tokens=8_000,
        max_output_tokens=512,
        max_cost_usd=0.0,
        timeout_seconds=1.0,
    )


class FakeContentWriter:
    """Technical fixture only; it is not a real article or quality sample."""

    call_mode = WriterCallMode.FAKE

    def __init__(self, scenario: FakeWriterScenario = FakeWriterScenario.PASS) -> None:
        self.scenario = scenario
        self.requests: list[WriterRequest] = []

    def limits_for(self, content_type: ContentType) -> WriterLimits:
        return _fake_limits(content_type)

    def preflight(self, _request: WriterRequest) -> None:
        return None

    def write(self, request: WriterRequest) -> WriterSuccess:
        self.requests.append(request)
        attempt_no = request.intent.attempt_no
        needs_rewrite = (
            self.scenario is FakeWriterScenario.ALWAYS_REWRITE
            or (
                self.scenario is FakeWriterScenario.REWRITE_THEN_PASS
                and attempt_no == 1
            )
        )
        evidence_ids = tuple(
            item.confirmed_claim_id for item in request.context.frozen_evidence
        )
        facts = [
            item.claim_text.rstrip(".")
            for item in request.context.frozen_evidence
        ]
        if isinstance(request.context.brief, ArticleBrief):
            brief = request.context.brief
            title = brief.working_title
            paragraphs = [
                f"A small visible outcome raises a larger question: {brief.answer_question}",
                f"The durable research card points to this thesis: {brief.central_thesis}",
            ]
            for index in range(6):
                fact = facts[index % len(facts)]
                paragraphs.append(
                    f"Frozen evidence {index + 1} supports a bounded part of the mechanism: "
                    f"{fact}. The point is not that one fact explains everything, but that "
                    "the same decision path keeps shaping the ordinary result."
                )
            paragraphs.extend([
                f"A serious limit remains: {brief.counterargument_or_limitation}",
                "Seen this way, the ordinary result is not accidental. It is the visible "
                "edge of a system of incentives, constraints, and prior choices.",
            ])
            body = "\n\n".join(paragraphs)
        else:
            brief = request.context.brief
            title = brief.hook
            fact = facts[0]
            body = (
                f"{brief.hook}\n\n"
                f"The frozen evidence records one useful fact: {fact}. "
                f"{brief.main_point} That does not prove a universal rule; "
                "it identifies the specific mechanism worth noticing. The visible "
                "price is therefore the end of a decision chain, not a complete "
                "description of what the buyer must pay."
            )
        style_ok = not needs_rewrite
        brief_compliant = not needs_rewrite
        if needs_rewrite:
            body = "A vague system did something important. More detail is needed."
        unsupported: tuple[str, ...] = ()
        personal = False
        if self.scenario is FakeWriterScenario.UNSUPPORTED_CLAIM:
            unsupported = ("An unsupported invented market statistic.",)
            body += " An invented market statistic proves the conclusion."
        if self.scenario is FakeWriterScenario.PERSONAL_EXPERIENCE:
            personal = True
            body += " I remember discussing this with my family on a trip."
        draft = FakeDraft(
            attempt_no=attempt_no,
            route_key=request.intent.route.route_key,
            title=title,
            body=body,
            evidence_ids_used=evidence_ids if not needs_rewrite else (),
            unsupported_claims=unsupported,
            personal_experience=personal,
            style_ok=style_ok,
            brief_compliant=brief_compliant,
            rewrite_of_draft_fingerprint=request.intent.rewrite_of_draft_fingerprint,
        )
        return WriterSuccess(
            draft=draft,
            provider="fake-content-writer",
            route_key=request.intent.route.route_key,
            api_model_id=None,
            usage=WriterUsage(input_tokens=0, output_tokens=0),
            stop_reason="LOCAL_FAKE",
        )


class ProviderReadyContentWriter:
    """Anthropic-shaped adapter with no reachable production composition root.

    SDK creation is lazy.  Configuration and secret checks happen before the
    factory is called.  One ``write`` invocation makes at most one caller call,
    and both SDK retries and application retries are fixed at zero.
    """

    call_mode = WriterCallMode.PROVIDER_READY_OFFLINE

    def __init__(
        self,
        *,
        api_key_provider: Callable[[], str | None],
        limits_by_type: dict[ContentType, WriterLimits],
        sdk_factory: ContentWriterSdkFactory | None = None,
        caller: ContentWriterCaller | None = None,
        expected_provider: str = "anthropic",
    ) -> None:
        if set(limits_by_type) != {ContentType.ARTICLE, ContentType.NOTE}:
            raise ValueError("Provider writer requires ARTICLE and NOTE limits.")
        for limits in limits_by_type.values():
            if limits.max_cost_usd != 0.0:
                raise ValueError(
                    "C3 provider-ready offline limits must cost exactly zero."
                )
            if not math.isfinite(limits.timeout_seconds):
                raise ValueError("Provider writer timeout must be finite.")
        if not expected_provider.strip():
            raise ValueError("Expected provider cannot be blank.")
        self._api_key_provider = api_key_provider
        self._limits_by_type = dict(limits_by_type)
        self._sdk_factory = sdk_factory or self._default_sdk_factory
        self._caller = caller or self._default_caller
        self._expected_provider = expected_provider
        self._validated_api_key: str | None = None
        self.caller_calls = 0

    def limits_for(self, content_type: ContentType) -> WriterLimits:
        return self._limits_by_type[content_type]

    @staticmethod
    def _failure(
        request: WriterRequest,
        kind: WriterFailureKind,
        detail: str,
        *,
        usage: WriterUsage | None = None,
        stop_reason: str | None = None,
        provider_request_id: str | None = None,
        uncertain: bool = False,
    ) -> WriterFailure:
        route = request.intent.route
        return WriterFailure(
            kind=kind,
            provider=route.provider,
            route_key=route.route_key,
            api_model_id=(
                None if route.api_model_id == "UNVERIFIED" else route.api_model_id
            ),
            usage=usage,
            stop_reason=stop_reason,
            provider_request_id=provider_request_id,
            detail=detail,
            uncertain=uncertain,
        )

    def preflight(self, request: WriterRequest) -> WriterFailure | None:
        route = request.intent.route
        if route.route_key not in {"FABLE_5_ARTICLE", "SONNET_5_NOTE"}:
            return self._failure(
                request,
                WriterFailureKind.UNSUPPORTED_ROUTE,
                "Logical writer route is unsupported.",
            )
        if route.provider == "UNVERIFIED" or route.api_model_id == "UNVERIFIED":
            return self._failure(
                request,
                WriterFailureKind.MISSING_CONFIGURATION,
                "Provider or technical model ID is not configured.",
            )
        if route.pricing_profile == "UNVERIFIED":
            return self._failure(
                request,
                WriterFailureKind.MISSING_PRICING,
                "Writer pricing profile is not configured.",
            )
        if route.availability != "CONFIGURED":
            return self._failure(
                request,
                WriterFailureKind.PROVIDER_UNAVAILABLE,
                "Writer provider availability is not configured.",
            )
        if route.provider != self._expected_provider:
            return self._failure(
                request,
                WriterFailureKind.UNSUPPORTED_ROUTE,
                "Configured provider is unsupported by this adapter.",
            )
        try:
            value = self._api_key_provider()
        except Exception:
            value = None
        if not isinstance(value, str) or not value.strip():
            self._validated_api_key = None
            return self._failure(
                request,
                WriterFailureKind.MISSING_CONFIGURATION,
                "Required provider secret is unavailable.",
            )
        self._validated_api_key = value
        return None

    @staticmethod
    def _usage_from_object(value: object | None) -> WriterUsage | None:
        if isinstance(value, WriterUsage):
            return value
        if value is None:
            return None
        try:
            return WriterUsage(
                input_tokens=int(getattr(value, "input_tokens")),
                output_tokens=int(getattr(value, "output_tokens")),
                cache_read_tokens=int(
                    getattr(value, "cache_read_input_tokens", 0) or 0
                ),
                cache_write_tokens=int(
                    getattr(value, "cache_creation_input_tokens", 0) or 0
                ),
                inference_geo=getattr(value, "inference_geo", None),
                service_tier=getattr(value, "service_tier", None),
                estimated_cost_usd=float(
                    getattr(value, "estimated_cost_usd", 0.0) or 0.0
                ),
            )
        except (TypeError, ValueError, AttributeError, ValidationError):
            return None

    def _map_exception(
        self, request: WriterRequest, exc: Exception,
    ) -> WriterFailure:
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        usage = self._usage_from_object(getattr(exc, "usage", None))
        stop_reason = getattr(exc, "stop_reason", None)
        raw_id = getattr(exc, "request_id", None)
        common = {
            "usage": usage,
            "stop_reason": stop_reason,
            "provider_request_id": raw_id if isinstance(raw_id, str) else None,
        }
        if name == "APITimeoutError":
            return self._failure(
                request, WriterFailureKind.TIMEOUT,
                "Provider request timed out.", uncertain=True, **common,
            )
        if name == "APIConnectionError":
            return self._failure(
                request, WriterFailureKind.NETWORK,
                "Provider connection failed.", uncertain=True, **common,
            )
        if status == 429 or name == "RateLimitError":
            return self._failure(
                request, WriterFailureKind.RATE_LIMIT,
                "Provider rate limit rejected the request.", **common,
            )
        if status in {401, 403} or name in {
            "AuthenticationError", "PermissionDeniedError",
        }:
            return self._failure(
                request, WriterFailureKind.AUTH_PERMISSION,
                "Provider authentication or permission failed.", **common,
            )
        if status in {400, 404, 422} or name in {
            "BadRequestError", "NotFoundError", "UnprocessableEntityError",
        }:
            return self._failure(
                request, WriterFailureKind.INVALID_REQUEST,
                "Provider rejected the request contract.", **common,
            )
        if isinstance(status, int) and 500 <= status <= 599:
            return self._failure(
                request, WriterFailureKind.PROVIDER_5XX,
                "Provider returned a server error.", **common,
            )
        return self._failure(
            request, WriterFailureKind.UNKNOWN_PROVIDER,
            "Provider failed with an unclassified error.",
            uncertain=True, **common,
        )

    def write(self, request: WriterRequest) -> WriterResult:
        blocked = self.preflight(request)
        if blocked is not None:
            return blocked
        assert self._validated_api_key is not None
        limits = request.context.limits
        try:
            client = self._sdk_factory(
                api_key=self._validated_api_key,
                max_retries=_SDK_MAX_RETRIES,
                timeout=limits.timeout_seconds,
            )
            self.caller_calls += 1
            raw = self._caller(client, request.prompt, request)
        except Exception as exc:
            return self._map_exception(request, exc)
        if not isinstance(raw, ProviderRawResponse):
            return self._failure(
                request,
                WriterFailureKind.SCHEMA_VALIDATION,
                "Provider caller returned an unsupported response contract.",
            )
        if raw.api_model_id != request.intent.route.api_model_id:
            # A response naming another model is not a schema problem to be
            # retried; it means the request that ran was not the request that
            # was authorised, and a charge may already exist for it. Marking it
            # uncertain routes the execution to NEEDS_VERIFICATION instead of a
            # clean failure, and never to a second model.
            return self._failure(
                request,
                WriterFailureKind.UNCERTAIN_STATE,
                "Provider response model disagrees with the durable route; "
                "runtime fallback is forbidden.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                uncertain=True,
            )
        if raw.usage.cache_read_tokens or raw.usage.cache_write_tokens:
            # Prompt caching is disabled for controlled execution. Cache usage
            # therefore describes a request this project did not make, and its
            # real cost cannot be derived from the frozen contract.
            return self._failure(
                request,
                WriterFailureKind.UNCERTAIN_STATE,
                "Provider reported cache usage while prompt caching is disabled.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                uncertain=True,
            )
        provenance_mismatch = returned_provenance_mismatch(
            inference_geo=raw.usage.inference_geo,
            service_tier=raw.usage.service_tier,
        )
        if provenance_mismatch is not None:
            return self._failure(
                request,
                WriterFailureKind.UNCERTAIN_STATE,
                f"Provider response provenance mismatch: {provenance_mismatch}.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                uncertain=True,
            )
        if raw.usage.estimated_cost_usd != 0.0:
            return self._failure(
                request,
                WriterFailureKind.SCHEMA_VALIDATION,
                "C3 fake provider usage must cost exactly zero.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
            )
        if raw.stop_reason in {"max_tokens", "length", "truncated"}:
            return self._failure(
                request,
                WriterFailureKind.TRUNCATION,
                "Provider output was truncated.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
            )
        if raw.stop_reason == "refusal":
            return self._failure(
                request,
                WriterFailureKind.PROVIDER_REFUSAL,
                "Provider returned a refusal instead of application content.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
            )
        try:
            decoded = json.loads(raw.text)
        except (TypeError, json.JSONDecodeError):
            return self._failure(
                request,
                WriterFailureKind.PARSE_ERROR,
                "Provider output was not valid JSON.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
            )
        try:
            payload = ProviderDraftPayload.model_validate(decoded)
            allowed = set(request.context.brief.evidence_ids)
            if not set(payload.evidence_ids_used).issubset(allowed):
                raise ValueError("Provider draft referenced evidence outside the brief.")
            draft = FakeDraft(
                attempt_no=request.intent.attempt_no,
                route_key=request.intent.route.route_key,
                rewrite_of_draft_fingerprint=(
                    request.intent.rewrite_of_draft_fingerprint
                ),
                **payload.model_dump(),
            )
        except (ValidationError, ValueError, TypeError):
            return self._failure(
                request,
                WriterFailureKind.SCHEMA_VALIDATION,
                "Provider draft failed the closed output schema.",
                usage=raw.usage,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
            )
        return WriterSuccess(
            draft=draft,
            provider=request.intent.route.provider,
            route_key=request.intent.route.route_key,
            api_model_id=request.intent.route.api_model_id,
            usage=raw.usage,
            stop_reason=raw.stop_reason,
            provider_request_id=raw.provider_request_id,
        )

    @staticmethod
    def _default_sdk_factory(
        *, api_key: str, max_retries: int, timeout: float,
    ) -> object:  # pragma: no cover - production root remains unreachable in C3
        anthropic = importlib.import_module("anthropic")
        return anthropic.Anthropic(
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
        )

    @staticmethod
    def _default_caller(
        client: object,
        prompt: WriterPrompt,
        request: WriterRequest,
    ) -> ProviderRawResponse:  # pragma: no cover - no real C3 invocation
        message = client.messages.create(
            model=request.intent.route.api_model_id,
            max_tokens=request.context.limits.max_output_tokens,
            system=prompt.system,
            messages=[{"role": "user", "content": prompt.user}],
            inference_geo=CONTROLLED_INFERENCE_GEO,
            service_tier=CONTROLLED_SERVICE_TIER,
            timeout=request.context.limits.timeout_seconds,
        )
        text = "".join(
            getattr(block, "text", "")
            for block in getattr(message, "content", ())
            if getattr(block, "type", "") == "text"
        )
        usage = getattr(message, "usage", None)
        return ProviderRawResponse(
            text=text,
            usage=WriterUsage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                cache_read_tokens=int(
                    getattr(usage, "cache_read_input_tokens", 0) or 0
                ),
                cache_write_tokens=int(
                    getattr(usage, "cache_creation_input_tokens", 0) or 0
                ),
                inference_geo=getattr(usage, "inference_geo", None),
                service_tier=getattr(usage, "service_tier", None),
                estimated_cost_usd=0.0,
            ),
            stop_reason=getattr(message, "stop_reason", None),
            provider_request_id=getattr(message, "id", None),
            api_model_id=str(
                getattr(message, "model", request.intent.route.api_model_id)
            ),
        )
