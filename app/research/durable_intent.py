"""Schema-aware durable execution intent for the single real-research worker."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import SimpleNamespace
from typing import Mapping

from app.core.config import REAL_PROVIDER_PRICING_KEYS, Settings
from app.core.money import decimal_from, quantize_usd
from app.core.pricing import (
    REQUIRED_CURRENCY,
    REQUIRED_UNIT,
    PricingConfigError,
    pricing_contract_fingerprint,
)
from app.research.cost_estimator import estimate_worst_case_search_call_usd


_SCHEMA = "durable_research_intent_v3"
_PIPELINE_VERSION = "single_research_pipeline_v2"
# v3 (2026-07-18): jawny kontrakt rozmiaru odpowiedzi — limity liczności i długości
# każdego pola w prompcie + deterministyczna walidacja (app/research/output_contract.py).
# Zamrożone intenty v2 pozostają fail-closed nieobsługiwane przez ten worker.
_PROMPT_CONTRACT_VERSION = "anthropic_research_single_v3"
_PROVIDER_STAGE = "research"

# Sentinel pricing-profile identity for non-authoritative paths (dry-run estimation,
# legacy tests).  Real paid enqueue MUST override these with an approved, versioned
# profile resolved from app.core.pricing; the sentinel never authorizes a real call.
SENTINEL_PRICING_PROFILE_ID = "unversioned-adhoc"
SENTINEL_PRICING_PROFILE_VERSION = "0"

# Closed max_tokens contract for the durable request output cap (LA-01-C).  The
# lower bound keeps a controlled acceptance from freezing a nonsensically small
# value; the upper bound is the approved provider ceiling.  The default matches
# the historical synthesis cap and stays available for the ordinary flow, while a
# controlled acceptance may freeze a lower value explicitly.
MIN_REQUEST_MAX_TOKENS = 256
MAX_REQUEST_MAX_TOKENS = 8192
DEFAULT_REQUEST_MAX_TOKENS = 3000


class DurableExecutionIntentError(ValueError):
    """The persisted durable payload is incomplete or semantically inconsistent."""

    def __init__(
        self,
        detail: str,
        *,
        code: str = "MALFORMED_DURABLE_V2_PAYLOAD",
    ) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _money(value: object, *, field: str, allow_zero: bool = False) -> str:
    if isinstance(value, bool):
        raise DurableExecutionIntentError(f"{field} must be a decimal amount, not bool.")
    try:
        amount = decimal_from(value, label=field)
    except ValueError as exc:
        raise DurableExecutionIntentError(f"{field} must be a finite decimal amount.") from exc
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise DurableExecutionIntentError(f"{field} must be finite and {qualifier}.")
    canonical = quantize_usd(amount, label=field)
    if not allow_zero and canonical == 0:
        raise DurableExecutionIntentError(
            f"{field} is below 0.000001 USD after ROUND_HALF_UP canonicalization."
        )
    return format(canonical, ".6f")


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DurableExecutionIntentError(f"{field} must be an integer.")
    if not math.isfinite(float(value)) or int(value) != value or int(value) < minimum:
        raise DurableExecutionIntentError(f"{field} must be an integer >= {minimum}.")
    return int(value)


def _bounded_max_tokens(value: object, *, field: str = "max_tokens") -> int:
    """Persistence-level max_tokens guard: integral value within the provider bound.

    Integral floats (e.g. ``3000.0``) remain accepted so equivalent JSON numeric
    forms do not change request identity; the CLI applies a stricter integer-only
    contract before this is ever reached.
    """
    parsed = _integer(value, field=field, minimum=1)
    if parsed < MIN_REQUEST_MAX_TOKENS or parsed > MAX_REQUEST_MAX_TOKENS:
        raise DurableExecutionIntentError(
            f"{field} {parsed} is outside the approved provider bound "
            f"[{MIN_REQUEST_MAX_TOKENS}, {MAX_REQUEST_MAX_TOKENS}].",
            code="MAX_TOKENS_OUT_OF_RANGE",
        )
    return parsed


def validate_cli_max_tokens(value: object) -> int:
    """Strict CLI/operator contract for --max-tokens (LA-01-C): integer, in range.

    Rejects bool and float outright (no silent truncation), then applies the same
    approved provider bound that request identity enforces.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise DurableExecutionIntentError(
            "max_tokens must be a plain integer (no float, no bool).",
            code="MAX_TOKENS_NOT_INTEGER",
        )
    return _bounded_max_tokens(value, field="max_tokens")


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DurableExecutionIntentError(f"{field} must be a non-empty string.")
    # The canonical value is also the one passed to the prompt builder.  That
    # makes harmless JSON/whitespace representation changes non-semantic while
    # preventing the caller from later using a different mutable table value.
    return " ".join(value.split())


def controlled_research_job_id(operation_key: object) -> str:
    """Return the durable job identity shared by enqueue and controlled execution."""
    canonical_key = _text(operation_key, field="operation_key")
    idempotency_key = f"real-research:{canonical_key}"
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return f"real-research-{digest}"


def controlled_session_contract(
    operation_key: object,
    *,
    job_id: object | None = None,
) -> dict[str, object]:
    """Build the deterministic, durable ownership fence for one logical operation.

    The values are identities/fences rather than credentials.  Determinism lets an
    idempotent enqueue and the later controlled wrapper independently derive the
    same complete contract without an ambient or in-memory hand-off.
    """
    canonical_key = _text(operation_key, field="operation_key")
    expected_job_id = (
        controlled_research_job_id(canonical_key)
        if job_id is None
        else _text(job_id, field="expected_job_id")
    )
    canonical_job_id = controlled_research_job_id(canonical_key)
    if expected_job_id != canonical_job_id:
        raise DurableExecutionIntentError(
            "expected_job_id is inconsistent with operation_key.",
            code="CONTROLLED_SESSION_IDENTITY_MISMATCH",
        )
    session_id = hashlib.sha256(
        f"controlled-live-session:{canonical_key}".encode("utf-8")
    ).hexdigest()[:32]
    worker_fence = hashlib.sha256(
        f"controlled-live-worker:{expected_job_id}:{session_id}".encode("utf-8")
    ).hexdigest()[:32]
    return {
        "session_id": session_id,
        "operation_key": canonical_key,
        "expected_job_id": expected_job_id,
        "expected_request_id": f"{expected_job_id}:{_PROVIDER_STAGE}:1",
        "expected_attempt_no": 1,
        "worker_execution_token": f"controlled-live:{session_id}:{worker_fence}",
    }


def _text_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise DurableExecutionIntentError(f"{field} must be an array of non-empty strings.")
    return [_text(item, field=f"{field}[{index}]") for index, item in enumerate(value)]


def _pricing_profile(pricing: Mapping[str, object]) -> dict[str, str]:
    if set(pricing) != set(REAL_PROVIDER_PRICING_KEYS):
        raise DurableExecutionIntentError("pricing_profile must contain exactly the real-provider price keys.")
    return {
        key: _money(pricing[key], field=f"pricing_profile.{key}", allow_zero=True)
        for key in REAL_PROVIDER_PRICING_KEYS
    }


def _pricing_fingerprint(
    *,
    profile_id: str,
    version: str,
    model: str,
    currency: str,
    unit: str,
    profile: Mapping[str, str],
) -> str:
    try:
        return pricing_contract_fingerprint(
            profile_id=profile_id,
            version=version,
            model=model,
            currency=currency,
            unit=unit,
            prices=profile,
        )
    except PricingConfigError as exc:
        raise DurableExecutionIntentError(
            "pricing contract cannot be fingerprinted."
        ) from exc


def _cost_projection(
    *,
    profile: Mapping[str, str],
    max_web_searches: int,
    max_tokens: int,
) -> tuple[str, str]:
    estimate = estimate_worst_case_search_call_usd(
        SimpleNamespace(pricing=dict(profile)),
        max_web_searches=max_web_searches,
        max_output_tokens=max_tokens,
    )
    return (
        _money(estimate.subtotal_usd, field="projected_cost_usd", allow_zero=True),
        _money(estimate.total_usd, field="pessimistic_cost_usd", allow_zero=True),
    )


@dataclass(frozen=True)
class DurableResearchExecutionIntent:
    account_id: str
    topic_id: int
    prompt_input: dict[str, object]
    stage: str
    cap_usd: str
    provider: str
    model: str
    max_tokens: int
    max_web_searches: int
    timeout_seconds: int
    pricing_profile: dict[str, str]
    pricing_fingerprint: str
    pricing_profile_id: str
    pricing_profile_version: str
    pricing_currency: str
    pricing_unit: str
    projected_cost_usd: str
    pessimistic_cost_usd: str
    pipeline_version: str
    prompt_contract_version: str
    max_retries: int

    @classmethod
    def from_settings(
        cls, *, settings: Settings, account_id: str, topic_id: int,
        cap_usd: object, max_web_searches: object, question: object,
        niche: object, max_tokens: object = 3000, required_depth: object = "standard",
        pricing_prices: Mapping[str, object] | None = None,
        pricing_profile_id: object = SENTINEL_PRICING_PROFILE_ID,
        pricing_profile_version: object = SENTINEL_PRICING_PROFILE_VERSION,
        pricing_currency: object = REQUIRED_CURRENCY,
        pricing_unit: object = REQUIRED_UNIT,
        guidance: object = (
            "Prefer primary sources; separate fact from interpretation; flag uncertainty."
        ),
    ) -> "DurableResearchExecutionIntent":
        # Real paid enqueue passes the approved profile's prices/id/version; other
        # callers fall back to settings pricing with the non-authoritative sentinel.
        source_prices = settings.pricing if pricing_prices is None else pricing_prices
        profile = _pricing_profile(source_prices)
        model = _text(settings.model_quality, field="model")
        profile_id = _text(pricing_profile_id, field="pricing_profile_id")
        profile_version = _text(
            pricing_profile_version, field="pricing_profile_version",
        )
        currency = _text(pricing_currency, field="pricing_currency")
        unit = _text(pricing_unit, field="pricing_unit")
        bounded_tokens = _bounded_max_tokens(max_tokens, field="max_tokens")
        bounded_searches = _integer(
            max_web_searches, field="max_web_searches", minimum=0,
        )
        projected, pessimistic = _cost_projection(
            profile=profile,
            max_web_searches=bounded_searches,
            max_tokens=bounded_tokens,
        )
        return cls(
            account_id=_text(account_id, field="account_id"),
            topic_id=_integer(topic_id, field="topic_id", minimum=1),
            prompt_input={
                "question": _text(question, field="prompt_input.question"),
                "niche": _text_list(niche, field="prompt_input.niche"),
                "required_depth": _text(
                    required_depth, field="prompt_input.required_depth",
                ),
                "guidance": _text(guidance, field="prompt_input.guidance"),
            },
            stage=_PROVIDER_STAGE,
            cap_usd=_money(cap_usd, field="cap_usd"),
            provider="anthropic",
            model=model,
            max_tokens=bounded_tokens,
            max_web_searches=bounded_searches,
            timeout_seconds=_integer(settings.research_timeout_seconds, field="timeout_seconds", minimum=1),
            pricing_profile=profile,
            pricing_fingerprint=_pricing_fingerprint(
                profile_id=profile_id,
                version=profile_version,
                model=model,
                currency=currency,
                unit=unit,
                profile=profile,
            ),
            pricing_profile_id=profile_id,
            pricing_profile_version=profile_version,
            pricing_currency=currency,
            pricing_unit=unit,
            projected_cost_usd=projected,
            pessimistic_cost_usd=pessimistic,
            pipeline_version=_PIPELINE_VERSION,
            prompt_contract_version=_PROMPT_CONTRACT_VERSION,
            max_retries=0,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "DurableResearchExecutionIntent":
        expected = {
            "schema", "account_id", "topic_id", "workflow", "mode", "cap_usd", "provider",
            "model", "max_tokens", "max_web_searches", "timeout_seconds", "pricing_profile",
            "pricing_fingerprint", "pricing_profile_id", "pricing_profile_version",
            "pricing_currency", "pricing_unit", "projected_cost_usd",
            "pessimistic_cost_usd",
            "pipeline_version", "prompt_contract_version", "max_retries",
            "flags", "stage", "prompt_input",
        }
        if set(payload) != expected:
            raise DurableExecutionIntentError("durable execution intent has unsupported or missing fields.")
        if payload["schema"] != _SCHEMA or payload["workflow"] != "RESEARCH" or payload["mode"] != "single":
            raise DurableExecutionIntentError("durable execution intent schema/workflow/mode is invalid.")
        flags = payload["flags"]
        if flags != {"force_re_research": False}:
            raise DurableExecutionIntentError("durable execution intent flags are invalid.")
        if payload["stage"] != _PROVIDER_STAGE:
            raise DurableExecutionIntentError("durable execution intent stage is invalid.")
        prompt_raw = payload["prompt_input"]
        if not isinstance(prompt_raw, Mapping) or set(prompt_raw) != {
            "question", "niche", "required_depth", "guidance",
        }:
            raise DurableExecutionIntentError(
                "prompt_input must contain exactly question, niche, required_depth and guidance."
            )
        prompt_input = {
            "question": _text(prompt_raw["question"], field="prompt_input.question"),
            "niche": _text_list(prompt_raw["niche"], field="prompt_input.niche"),
            "required_depth": _text(
                prompt_raw["required_depth"], field="prompt_input.required_depth",
            ),
            "guidance": _text(prompt_raw["guidance"], field="prompt_input.guidance"),
        }
        profile_raw = payload["pricing_profile"]
        if not isinstance(profile_raw, Mapping):
            raise DurableExecutionIntentError("pricing_profile must be an object.")
        profile = _pricing_profile(profile_raw)
        pricing_profile_id = _text(payload["pricing_profile_id"], field="pricing_profile_id")
        pricing_profile_version = _text(
            payload["pricing_profile_version"], field="pricing_profile_version",
        )
        pricing_currency = _text(payload["pricing_currency"], field="pricing_currency")
        pricing_unit = _text(payload["pricing_unit"], field="pricing_unit")
        model = _text(payload["model"], field="model")
        fingerprint = _text(payload["pricing_fingerprint"], field="pricing_fingerprint")
        if fingerprint != _pricing_fingerprint(
            profile_id=pricing_profile_id,
            version=pricing_profile_version,
            model=model,
            currency=pricing_currency,
            unit=pricing_unit,
            profile=profile,
        ):
            raise DurableExecutionIntentError(
                "pricing fingerprint does not match the complete frozen contract."
            )
        max_tokens = _bounded_max_tokens(payload["max_tokens"], field="max_tokens")
        max_web_searches = _integer(
            payload["max_web_searches"], field="max_web_searches", minimum=0,
        )
        expected_projected, expected_pessimistic = _cost_projection(
            profile=profile,
            max_web_searches=max_web_searches,
            max_tokens=max_tokens,
        )
        projected = _money(
            payload["projected_cost_usd"],
            field="projected_cost_usd",
            allow_zero=True,
        )
        pessimistic = _money(
            payload["pessimistic_cost_usd"],
            field="pessimistic_cost_usd",
            allow_zero=True,
        )
        if (projected, pessimistic) != (expected_projected, expected_pessimistic):
            raise DurableExecutionIntentError(
                "persisted cost projections do not match frozen pricing and limits."
            )
        pipeline_version = _text(payload["pipeline_version"], field="pipeline_version")
        prompt_contract_version = _text(payload["prompt_contract_version"], field="prompt_contract_version")
        retries = _integer(payload["max_retries"], field="max_retries", minimum=0)
        return cls(
            account_id=_text(payload["account_id"], field="account_id"),
            topic_id=_integer(payload["topic_id"], field="topic_id", minimum=1),
            prompt_input=prompt_input,
            stage=_PROVIDER_STAGE,
            cap_usd=_money(payload["cap_usd"], field="cap_usd"),
            provider=_text(payload["provider"], field="provider"),
            model=model,
            max_tokens=max_tokens,
            max_web_searches=max_web_searches,
            timeout_seconds=_integer(payload["timeout_seconds"], field="timeout_seconds", minimum=1),
            pricing_profile=profile,
            pricing_fingerprint=fingerprint,
            pricing_profile_id=pricing_profile_id,
            pricing_profile_version=pricing_profile_version,
            pricing_currency=pricing_currency,
            pricing_unit=pricing_unit,
            projected_cost_usd=projected,
            pessimistic_cost_usd=pessimistic,
            pipeline_version=pipeline_version,
            prompt_contract_version=prompt_contract_version,
            max_retries=retries,
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "account_id": self.account_id,
            "topic_id": self.topic_id,
            "prompt_input": {
                "question": self.prompt_input["question"],
                "niche": list(self.prompt_input["niche"]),
                "required_depth": self.prompt_input["required_depth"],
                "guidance": self.prompt_input["guidance"],
            },
            "stage": self.stage,
            "workflow": "RESEARCH",
            "mode": "single",
            "cap_usd": self.cap_usd,
            "provider": self.provider,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "max_web_searches": self.max_web_searches,
            "timeout_seconds": self.timeout_seconds,
            "pricing_profile": dict(self.pricing_profile),
            "pricing_fingerprint": self.pricing_fingerprint,
            "pricing_profile_id": self.pricing_profile_id,
            "pricing_profile_version": self.pricing_profile_version,
            "pricing_currency": self.pricing_currency,
            "pricing_unit": self.pricing_unit,
            "projected_cost_usd": self.projected_cost_usd,
            "pessimistic_cost_usd": self.pessimistic_cost_usd,
            "pipeline_version": self.pipeline_version,
            "prompt_contract_version": self.prompt_contract_version,
            "max_retries": self.max_retries,
            "flags": {"force_re_research": False},
        }

    def as_research_plan(self):
        """Build the provider plan solely from this persisted canonical snapshot."""
        from app.research.base import ResearchPlan

        return ResearchPlan(
            topic_id=self.topic_id,
            account_id=self.account_id,
            question=str(self.prompt_input["question"]),
            niche=list(self.prompt_input["niche"]),
            required_depth=str(self.prompt_input["required_depth"]),
            guidance=str(self.prompt_input["guidance"]),
        )

    def runtime_pricing(self) -> dict[str, float]:
        return {key: float(value) for key, value in self.pricing_profile.items()}

    def is_supported_by_current_worker(self) -> bool:
        """Whether the snapshot is executable by this single-provider worker."""
        return (
            self.provider == "anthropic"
            and self.pipeline_version == _PIPELINE_VERSION
            and self.prompt_contract_version == _PROMPT_CONTRACT_VERSION
            and self.max_retries == 0
        )


def canonicalize_durable_research_payload(payload: Mapping[str, object]) -> dict[str, object]:
    required = {
        "account_id", "topic_id", "dry_run", "execution", "mode", "max_cost_usd",
        "execution_intent",
    }
    if "execution_intent" not in payload:
        raise DurableExecutionIntentError(
            "durable real job payload is missing execution_intent.",
            code="MISSING_EXECUTION_INTENT",
        )
    allowed = required | {"controlled_session"}
    if set(payload) not in (required, allowed):
        raise DurableExecutionIntentError("durable real job payload has unsupported or missing fields.")
    if payload["execution"] != "durable_provider_v2":
        raise DurableExecutionIntentError(
            "durable real job requires execution=durable_provider_v2.",
            code="UNSUPPORTED_EXECUTION_CONTRACT",
        )
    if payload["dry_run"] is not False or payload["mode"] != "single":
        raise DurableExecutionIntentError("durable real job execution contract is invalid.")
    raw_intent = payload["execution_intent"]
    if not isinstance(raw_intent, Mapping):
        raise DurableExecutionIntentError("durable real job execution_intent must be an object.")
    intent = DurableResearchExecutionIntent.from_payload(raw_intent)
    account_id = _text(payload["account_id"], field="account_id")
    topic_id = _integer(payload["topic_id"], field="topic_id", minimum=1)
    cap = _money(payload["max_cost_usd"], field="max_cost_usd")
    if (account_id, topic_id, cap) != (intent.account_id, intent.topic_id, intent.cap_usd):
        raise DurableExecutionIntentError("payload identity/cap must match execution_intent.")
    result = {
        "account_id": account_id,
        "topic_id": topic_id,
        "dry_run": False,
        "execution": "durable_provider_v2",
        "mode": "single",
        "max_cost_usd": cap,
        "execution_intent": intent.as_payload(),
    }
    if "controlled_session" in payload:
        raw_session = payload["controlled_session"]
        if not isinstance(raw_session, Mapping) or set(raw_session) != {
            "session_id",
            "operation_key",
            "expected_job_id",
            "expected_request_id",
            "expected_attempt_no",
            "worker_execution_token",
        }:
            raise DurableExecutionIntentError(
                "controlled_session must contain the complete ownership contract."
            )
        session = {
            "session_id": _text(raw_session["session_id"], field="controlled_session.session_id"),
            "operation_key": _text(
                raw_session["operation_key"], field="controlled_session.operation_key",
            ),
            "expected_job_id": _text(
                raw_session["expected_job_id"], field="controlled_session.expected_job_id",
            ),
            "expected_request_id": _text(
                raw_session["expected_request_id"],
                field="controlled_session.expected_request_id",
            ),
            "expected_attempt_no": _integer(
                raw_session["expected_attempt_no"],
                field="controlled_session.expected_attempt_no",
                minimum=1,
            ),
            "worker_execution_token": _text(
                raw_session["worker_execution_token"],
                field="controlled_session.worker_execution_token",
            ),
        }
        if session["expected_attempt_no"] != 1:
            raise DurableExecutionIntentError(
                "controlled_session expected_attempt_no must be exactly 1."
            )
        expected_request_id = (
            f"{session['expected_job_id']}:{intent.stage}:{session['expected_attempt_no']}"
        )
        if session["expected_request_id"] != expected_request_id:
            raise DurableExecutionIntentError(
                "controlled_session request identity is inconsistent."
            )
        result["controlled_session"] = session
    return result


def durable_execution_intent_fingerprint(payload: Mapping[str, object]) -> str:
    """Return the stable fingerprint of every persisted paid-request input.

    The outer payload is canonicalized first, so JSON key order, equivalent
    numeric forms and insignificant surrounding whitespace cannot alter the
    result.  The nested ``execution_intent`` is intentionally the entire
    fingerprint domain: it carries provider/model/limits/pricing/cap/workflow,
    mode, durable prompt inputs, provider stage, prompt/pipeline versions, and
    request-affecting flags.  The prompt and system-message implementation is
    versioned by ``prompt_contract_version``; no mutable account/topic value is
    consulted by the durable worker after enqueue.
    """
    canonical = canonicalize_durable_research_payload(payload)
    intent = canonical["execution_intent"]
    encoded = json.dumps(intent, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
