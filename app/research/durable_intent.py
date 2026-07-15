"""Schema-aware durable execution intent for the single real-research worker."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

from app.core.config import REAL_PROVIDER_PRICING_KEYS, Settings
from app.core.money import decimal_from, quantize_usd


_SCHEMA = "durable_research_intent_v2"
_PIPELINE_VERSION = "single_research_pipeline_v2"
_PROMPT_CONTRACT_VERSION = "anthropic_research_single_v2"
_PROVIDER_STAGE = "research"


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


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DurableExecutionIntentError(f"{field} must be a non-empty string.")
    # The canonical value is also the one passed to the prompt builder.  That
    # makes harmless JSON/whitespace representation changes non-semantic while
    # preventing the caller from later using a different mutable table value.
    return " ".join(value.split())


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


def _pricing_fingerprint(profile: Mapping[str, str]) -> str:
    canonical = json.dumps(dict(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    pipeline_version: str
    prompt_contract_version: str
    max_retries: int

    @classmethod
    def from_settings(
        cls, *, settings: Settings, account_id: str, topic_id: int,
        cap_usd: object, max_web_searches: object, question: object,
        niche: object, max_tokens: object = 3000, required_depth: object = "standard", guidance: object = (
            "Prefer primary sources; separate fact from interpretation; flag uncertainty."
        ),
    ) -> "DurableResearchExecutionIntent":
        profile = _pricing_profile(settings.pricing)
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
            model=_text(settings.model_quality, field="model"),
            max_tokens=_integer(max_tokens, field="max_tokens", minimum=1),
            max_web_searches=_integer(max_web_searches, field="max_web_searches", minimum=0),
            timeout_seconds=_integer(settings.research_timeout_seconds, field="timeout_seconds", minimum=1),
            pricing_profile=profile,
            pricing_fingerprint=_pricing_fingerprint(profile),
            pipeline_version=_PIPELINE_VERSION,
            prompt_contract_version=_PROMPT_CONTRACT_VERSION,
            max_retries=0,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "DurableResearchExecutionIntent":
        expected = {
            "schema", "account_id", "topic_id", "workflow", "mode", "cap_usd", "provider",
            "model", "max_tokens", "max_web_searches", "timeout_seconds", "pricing_profile",
            "pricing_fingerprint", "pipeline_version", "prompt_contract_version", "max_retries",
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
        fingerprint = _text(payload["pricing_fingerprint"], field="pricing_fingerprint")
        if fingerprint != _pricing_fingerprint(profile):
            raise DurableExecutionIntentError("pricing fingerprint does not match the persisted profile.")
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
            model=_text(payload["model"], field="model"),
            max_tokens=_integer(payload["max_tokens"], field="max_tokens", minimum=1),
            max_web_searches=_integer(payload["max_web_searches"], field="max_web_searches", minimum=0),
            timeout_seconds=_integer(payload["timeout_seconds"], field="timeout_seconds", minimum=1),
            pricing_profile=profile,
            pricing_fingerprint=fingerprint,
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
    expected = {
        "account_id", "topic_id", "dry_run", "execution", "mode", "max_cost_usd",
        "execution_intent",
    }
    if "execution_intent" not in payload:
        raise DurableExecutionIntentError(
            "durable real job payload is missing execution_intent.",
            code="MISSING_EXECUTION_INTENT",
        )
    if set(payload) != expected:
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
    return {
        "account_id": account_id,
        "topic_id": topic_id,
        "dry_run": False,
        "execution": "durable_provider_v2",
        "mode": "single",
        "max_cost_usd": cap,
        "execution_intent": intent.as_payload(),
    }


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
