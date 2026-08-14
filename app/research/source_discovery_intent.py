"""Closed durable contract for the A1 phase of ARTICLE_RESEARCH."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from app.llm.anthropic_provider_contract import (
    ARTICLE_RESEARCH_INFERENCE_CONFIG,
    AnthropicInferenceConfig,
    inference_config_from_payload,
)

SOURCE_DISCOVERY_EXECUTION = "article_research_source_discovery_v1"
SOURCE_DISCOVERY_INTENT_VERSION = "source_discovery_intent_v1"
_KEYS = {
    "version", "account_id", "topic_id", "provider", "model", "max_results",
    "max_output_tokens", "cap_usd", "max_retries", "fallback_policy", "fingerprint",
    "inference_config",
}
_PAYLOAD_KEYS = {"account_id", "topic_id", "dry_run", "execution", "execution_intent"}


class SourceDiscoveryIntentError(ValueError):
    pass


def _fingerprint(raw: dict[str, Any]) -> str:
    domain = {key: raw[key] for key in sorted(_KEYS - {"fingerprint"})}
    encoded = json.dumps(domain, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceDiscoveryIntent:
    version: str
    account_id: str
    topic_id: int
    provider: str
    model: str
    max_results: int
    max_output_tokens: int
    cap_usd: str
    max_retries: int
    fallback_policy: str
    inference_config: AnthropicInferenceConfig
    fingerprint: str

    @classmethod
    def build(cls, *, account_id: str, topic_id: int, max_results: int = 6,
              max_output_tokens: int = 8192, cap_usd: str = "1.000000") -> "SourceDiscoveryIntent":
        raw: dict[str, Any] = {
            "version": SOURCE_DISCOVERY_INTENT_VERSION,
            "account_id": account_id,
            "topic_id": topic_id,
            "provider": "anthropic",
            "model": "claude-opus-5",
            "max_results": max_results,
            "max_output_tokens": max_output_tokens,
            "cap_usd": cap_usd,
            "max_retries": 0,
            "fallback_policy": "FORBIDDEN",
            "inference_config": ARTICLE_RESEARCH_INFERENCE_CONFIG.payload(),
        }
        raw["fingerprint"] = _fingerprint(raw)
        return cls.from_payload(raw)

    @classmethod
    def from_payload(cls, raw: Any) -> "SourceDiscoveryIntent":
        if not isinstance(raw, dict) or set(raw) != _KEYS:
            raise SourceDiscoveryIntentError("source-discovery intent has invalid fields")
        if raw["version"] != SOURCE_DISCOVERY_INTENT_VERSION:
            raise SourceDiscoveryIntentError("source-discovery intent version is unsupported")
        if raw["provider"] != "anthropic" or raw["model"] != "claude-opus-5":
            raise SourceDiscoveryIntentError("source discovery requires exact Anthropic Opus 5")
        if raw["max_retries"] != 0 or raw["fallback_policy"] != "FORBIDDEN":
            raise SourceDiscoveryIntentError("source discovery forbids retry and fallback")
        try:
            inference_config = inference_config_from_payload(
                raw["inference_config"], expected_role="ARTICLE_RESEARCH",
            )
        except ValueError as exc:
            raise SourceDiscoveryIntentError(
                "source-discovery inference config mismatch"
            ) from exc
        if not isinstance(raw["topic_id"], int) or isinstance(raw["topic_id"], bool) or raw["topic_id"] < 1:
            raise SourceDiscoveryIntentError("topic_id is invalid")
        if not isinstance(raw["max_results"], int) or not 1 <= raw["max_results"] <= 6:
            raise SourceDiscoveryIntentError("max_results is outside [1, 6]")
        if raw["max_output_tokens"] != 8192:
            raise SourceDiscoveryIntentError("A1 output envelope must be 8192")
        if raw["cap_usd"] not in {
            "0.300000", "0.500000", "0.600000", "1.000000",
        }:
            raise SourceDiscoveryIntentError(
                "A1 cap must use the current 0.600000 USD envelope or a supported "
                "historical 0.300000/0.500000/1.000000 USD envelope"
            )
        if raw["fingerprint"] != _fingerprint(raw):
            raise SourceDiscoveryIntentError("source-discovery fingerprint mismatch")
        return cls(**{**raw, "inference_config": inference_config})

    def as_payload(self) -> dict[str, Any]:
        return {**self.__dict__, "inference_config": self.inference_config.payload()}


def canonicalize_source_discovery_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise SourceDiscoveryIntentError("source-discovery job payload has invalid fields")
    if payload["dry_run"] is not False or payload["execution"] != SOURCE_DISCOVERY_EXECUTION:
        raise SourceDiscoveryIntentError("source-discovery execution/mode is invalid")
    intent = SourceDiscoveryIntent.from_payload(payload["execution_intent"])
    if payload["account_id"] != intent.account_id or payload["topic_id"] != intent.topic_id:
        raise SourceDiscoveryIntentError("source-discovery job identity mismatch")
    return {**payload, "execution_intent": intent.as_payload()}
