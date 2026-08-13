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
from app.llm.anthropic_provider_contract import (
    ARTICLE_RESEARCH_INFERENCE_CONFIG,
    AnthropicInferenceConfig,
    inference_config_from_payload,
)
from app.research.cost_estimator import (
    estimate_no_search_call_usd,
    estimate_worst_case_search_call_usd,
)
from app.research.evidence import MAX_CANONICAL_CHARS
from app.research.output_contract import CONSERVATIVE_CHARS_PER_TOKEN, MAX_SOURCES


_SCHEMA = "durable_research_intent_v3"
_PIPELINE_VERSION = "single_research_pipeline_v2"
# v3 (2026-07-18): jawny kontrakt rozmiaru odpowiedzi — limity liczności i długości
# każdego pola w prompcie + deterministyczna walidacja (app/research/output_contract.py).
# Zamrożone intenty v2 pozostają fail-closed nieobsługiwane przez ten worker.
_PROMPT_CONTRACT_VERSION = "anthropic_research_single_v3"
# E3: tryb evidence — synteza WYŁĄCZNIE z zatwierdzonego lokalnego canonical
# evidence (zero web search, zero Fetchu). Osobna wersja kontraktu promptu
# jest częścią fingerprintowanej domeny intentu.
EVIDENCE_PROMPT_CONTRACT_VERSION = "anthropic_research_evidence_v1"
_PROVIDER_STAGE = "research"

# --- E3: zamknięty kontrakt evidence_input_v1 (pinowany testami; zmiana = nowa
# decyzja i nowa wersja). Limity są WYWIEDZIONE z istniejących kontraktów:
#   * MAX_EVIDENCE_RETRIEVALS == output_contract.MAX_SOURCES (6) — górna granica
#     liczby źródeł jednej Research Card;
#   * MAX_EVIDENCE_CHARS_PER_RETRIEVAL == evidence.MAX_CANONICAL_CHARS (100000)
#     — istniejący sufit E1 pojedynczego kanonu (egzekwowany też CHECK-iem 0016);
#   * MAX_EVIDENCE_TOTAL_CHARS — iloczyn obu powyższych (sufit corpusu).
EVIDENCE_INPUT_VERSION = "evidence_input_v1"
MAX_EVIDENCE_RETRIEVALS = MAX_SOURCES
MAX_EVIDENCE_CHARS_PER_RETRIEVAL = MAX_CANONICAL_CHARS
MAX_EVIDENCE_TOTAL_CHARS = MAX_EVIDENCE_RETRIEVALS * MAX_EVIDENCE_CHARS_PER_RETRIEVAL
# Pinowany budżet znaków promptu POZA corpusem (system + instrukcje kontraktu
# v1 + pytanie/niche/guidance/nagłówki dokumentów). Test kontraktowy dowodzi,
# że realny szablon promptu evidence z polami na granicach mieści się w tym
# budżecie. Przeliczenie znaki->tokeny używa ISTNIEJĄCEJ konserwatywnej stałej
# output_contract.CONSERVATIVE_CHARS_PER_TOKEN (3.5 znaka/token).
EVIDENCE_PROMPT_OVERHEAD_CHARS = 8000
_SHA256_HEX_CHARS = frozenset("0123456789abcdef")

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
DEFAULT_REQUEST_MAX_TOKENS = 8192


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


def _sha256_hex_text(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) != 64 or any(char not in _SHA256_HEX_CHARS for char in text):
        raise DurableExecutionIntentError(
            f"{field} must be 64 lowercase hex characters.",
            code="EVIDENCE_INPUT_INVALID",
        )
    return text


def _evidence_input(raw: object) -> dict[str, object]:
    """Validate the closed evidence_input_v1 contract; returns the canonical dict."""

    def _reject(detail: str) -> DurableExecutionIntentError:
        return DurableExecutionIntentError(detail, code="EVIDENCE_INPUT_INVALID")

    if not isinstance(raw, Mapping) or set(raw) != {"version", "retrievals", "limits"}:
        raise _reject(
            "evidence_input must contain exactly version, retrievals and limits."
        )
    if raw["version"] != EVIDENCE_INPUT_VERSION:
        raise _reject("evidence_input version is unsupported.")
    limits = raw["limits"]
    if not isinstance(limits, Mapping) or set(limits) != {
        "max_retrievals", "max_chars_per_retrieval", "max_total_chars",
    }:
        raise _reject(
            "evidence_input.limits must contain exactly max_retrievals, "
            "max_chars_per_retrieval and max_total_chars."
        )
    if (
        limits["max_retrievals"] != MAX_EVIDENCE_RETRIEVALS
        or limits["max_chars_per_retrieval"] != MAX_EVIDENCE_CHARS_PER_RETRIEVAL
        or limits["max_total_chars"] != MAX_EVIDENCE_TOTAL_CHARS
    ):
        raise _reject(
            "evidence_input.limits must equal the closed evidence_input_v1 limits."
        )
    retrievals_raw = raw["retrievals"]
    if not isinstance(retrievals_raw, list) or not retrievals_raw:
        raise _reject("evidence_input.retrievals must be a non-empty array.")
    if len(retrievals_raw) > MAX_EVIDENCE_RETRIEVALS:
        raise _reject(
            f"evidence_input.retrievals exceeds the closed maximum of "
            f"{MAX_EVIDENCE_RETRIEVALS} retrievals."
        )
    retrievals: list[dict[str, object]] = []
    seen_ids: set[int] = set()
    total_chars = 0
    for index, entry in enumerate(retrievals_raw):
        label = f"evidence_input.retrievals[{index}]"
        if not isinstance(entry, Mapping) or set(entry) != {
            "retrieval_id", "canonical_sha256", "canonical_chars",
        }:
            raise _reject(
                f"{label} must contain exactly retrieval_id, canonical_sha256 "
                "and canonical_chars."
            )
        retrieval_id = _integer(
            entry["retrieval_id"], field=f"{label}.retrieval_id", minimum=1,
        )
        if retrieval_id in seen_ids:
            raise _reject(f"{label}.retrieval_id duplicates an earlier entry.")
        seen_ids.add(retrieval_id)
        canonical_sha256 = _sha256_hex_text(
            entry["canonical_sha256"], field=f"{label}.canonical_sha256",
        )
        canonical_chars = _integer(
            entry["canonical_chars"], field=f"{label}.canonical_chars", minimum=1,
        )
        if canonical_chars > MAX_EVIDENCE_CHARS_PER_RETRIEVAL:
            raise _reject(
                f"{label}.canonical_chars exceeds the per-retrieval limit of "
                f"{MAX_EVIDENCE_CHARS_PER_RETRIEVAL} characters."
            )
        total_chars += canonical_chars
        retrievals.append({
            "retrieval_id": retrieval_id,
            "canonical_sha256": canonical_sha256,
            "canonical_chars": canonical_chars,
        })
    if total_chars > MAX_EVIDENCE_TOTAL_CHARS:
        raise _reject(
            f"evidence corpus of {total_chars} characters exceeds the closed "
            f"total limit of {MAX_EVIDENCE_TOTAL_CHARS} characters."
        )
    return {
        "version": EVIDENCE_INPUT_VERSION,
        "retrievals": retrievals,
        "limits": {
            "max_retrievals": MAX_EVIDENCE_RETRIEVALS,
            "max_chars_per_retrieval": MAX_EVIDENCE_CHARS_PER_RETRIEVAL,
            "max_total_chars": MAX_EVIDENCE_TOTAL_CHARS,
        },
    }


def evidence_input_payload(
    retrievals: list[tuple[int, str, int]],
) -> dict[str, object]:
    """Build one canonical evidence_input_v1 payload from (id, sha256, chars)."""
    return _evidence_input({
        "version": EVIDENCE_INPUT_VERSION,
        "retrievals": [
            {
                "retrieval_id": retrieval_id,
                "canonical_sha256": canonical_sha256,
                "canonical_chars": canonical_chars,
            }
            for retrieval_id, canonical_sha256, canonical_chars in retrievals
        ],
        "limits": {
            "max_retrievals": MAX_EVIDENCE_RETRIEVALS,
            "max_chars_per_retrieval": MAX_EVIDENCE_CHARS_PER_RETRIEVAL,
            "max_total_chars": MAX_EVIDENCE_TOTAL_CHARS,
        },
    })


def evidence_input_total_chars(evidence_input: Mapping[str, object]) -> int:
    """Frozen corpus size in characters, straight from the validated intent."""
    retrievals = evidence_input["retrievals"]
    assert isinstance(retrievals, list)
    return sum(int(entry["canonical_chars"]) for entry in retrievals)


def evidence_forwarded_context_tokens(evidence_input: Mapping[str, object]) -> int:
    """Deterministic, conservative chars->input-tokens contract for evidence.

    Uses the frozen corpus size plus the pinned prompt-overhead budget divided
    by the EXISTING conservative constant (3.5 chars/token, output_contract).
    """
    total_chars = evidence_input_total_chars(evidence_input) + EVIDENCE_PROMPT_OVERHEAD_CHARS
    return math.ceil(total_chars / CONSERVATIVE_CHARS_PER_TOKEN)


def _cost_projection(
    *,
    profile: Mapping[str, str],
    max_web_searches: int,
    max_tokens: int,
    evidence_input: Mapping[str, object] | None = None,
) -> tuple[str, str]:
    if evidence_input is not None:
        # E3: pełny input evidence wchodzi do projekcji przez ISTNIEJĄCY
        # kontrakt no-search (jawny człon input_per_mtok + margines >= 50%).
        estimate = estimate_no_search_call_usd(
            SimpleNamespace(pricing=dict(profile)),
            max_output_tokens=max_tokens,
            forwarded_context_tokens=evidence_forwarded_context_tokens(evidence_input),
        )
    else:
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
    inference_config: AnthropicInferenceConfig
    evidence_input: dict[str, object] | None = None
    force_re_research: bool = False

    @classmethod
    def from_settings(
        cls, *, settings: Settings, account_id: str, topic_id: int,
        cap_usd: object, max_web_searches: object, question: object,
        niche: object, max_tokens: object = DEFAULT_REQUEST_MAX_TOKENS,
        required_depth: object = "standard",
        pricing_prices: Mapping[str, object] | None = None,
        pricing_profile_id: object = SENTINEL_PRICING_PROFILE_ID,
        pricing_profile_version: object = SENTINEL_PRICING_PROFILE_VERSION,
        pricing_currency: object = REQUIRED_CURRENCY,
        pricing_unit: object = REQUIRED_UNIT,
        guidance: object = (
            "Prefer primary sources; separate fact from interpretation; flag uncertainty."
        ),
        evidence_input: Mapping[str, object] | None = None,
        force_re_research: object = False,
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
        evidence = None if evidence_input is None else _evidence_input(evidence_input)
        if evidence is not None and bounded_searches != 0:
            raise DurableExecutionIntentError(
                "evidence research requires max_web_searches=0.",
                code="EVIDENCE_REQUIRES_ZERO_SEARCHES",
            )
        if not isinstance(force_re_research, bool):
            raise DurableExecutionIntentError(
                "force_re_research must be a boolean.",
                code="INVALID_FORCE_RE_RESEARCH",
            )
        # A durable re-research is only ever a frozen-evidence re-synthesis: it
        # forces a new run past the completed-card gate without any new web
        # search or fetch.  It is refused for search-based fresh research.
        if force_re_research and evidence is None:
            raise DurableExecutionIntentError(
                "force_re_research is only supported for evidence re-research.",
                code="FORCE_RE_RESEARCH_REQUIRES_EVIDENCE",
            )
        projected, pessimistic = _cost_projection(
            profile=profile,
            max_web_searches=bounded_searches,
            max_tokens=bounded_tokens,
            evidence_input=evidence,
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
            prompt_contract_version=(
                EVIDENCE_PROMPT_CONTRACT_VERSION
                if evidence is not None
                else _PROMPT_CONTRACT_VERSION
            ),
            max_retries=0,
            inference_config=ARTICLE_RESEARCH_INFERENCE_CONFIG,
            evidence_input=evidence,
            force_re_research=force_re_research,
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
            "flags", "stage", "prompt_input", "inference_config",
        }
        if set(payload) not in (expected, expected | {"evidence_input"}):
            raise DurableExecutionIntentError("durable execution intent has unsupported or missing fields.")
        if payload["schema"] != _SCHEMA or payload["workflow"] != "RESEARCH" or payload["mode"] != "single":
            raise DurableExecutionIntentError("durable execution intent schema/workflow/mode is invalid.")
        flags = payload["flags"]
        if (
            not isinstance(flags, Mapping)
            or set(flags) != {"force_re_research"}
            or not isinstance(flags["force_re_research"], bool)
        ):
            raise DurableExecutionIntentError("durable execution intent flags are invalid.")
        force_re_research = bool(flags["force_re_research"])
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
        evidence = (
            _evidence_input(payload["evidence_input"])
            if "evidence_input" in payload
            else None
        )
        if evidence is not None and max_web_searches != 0:
            raise DurableExecutionIntentError(
                "evidence research requires max_web_searches=0.",
                code="EVIDENCE_REQUIRES_ZERO_SEARCHES",
            )
        if force_re_research and evidence is None:
            raise DurableExecutionIntentError(
                "force_re_research is only supported for evidence re-research.",
                code="FORCE_RE_RESEARCH_REQUIRES_EVIDENCE",
            )
        expected_projected, expected_pessimistic = _cost_projection(
            profile=profile,
            max_web_searches=max_web_searches,
            max_tokens=max_tokens,
            evidence_input=evidence,
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
        if (evidence is not None) != (
            prompt_contract_version == EVIDENCE_PROMPT_CONTRACT_VERSION
        ):
            raise DurableExecutionIntentError(
                "evidence_input and the evidence prompt contract version must "
                "appear together.",
                code="EVIDENCE_PROMPT_CONTRACT_MISMATCH",
            )
        retries = _integer(payload["max_retries"], field="max_retries", minimum=0)
        try:
            inference_config = inference_config_from_payload(
                payload["inference_config"], expected_role="ARTICLE_RESEARCH",
            )
        except ValueError as exc:
            raise DurableExecutionIntentError(
                "durable research inference config is invalid.",
                code="INFERENCE_CONFIG_MISMATCH",
            ) from exc
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
            inference_config=inference_config,
            evidence_input=evidence,
            force_re_research=force_re_research,
        )

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
            "inference_config": self.inference_config.payload(),
            "flags": {"force_re_research": self.force_re_research},
        }
        if self.evidence_input is not None:
            payload["evidence_input"] = {
                "version": self.evidence_input["version"],
                "retrievals": [
                    dict(entry) for entry in self.evidence_input["retrievals"]
                ],
                "limits": dict(self.evidence_input["limits"]),
            }
        return payload

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
        expected_prompt_contract = (
            EVIDENCE_PROMPT_CONTRACT_VERSION
            if self.evidence_input is not None
            else _PROMPT_CONTRACT_VERSION
        )
        return (
            self.provider == "anthropic"
            and self.pipeline_version == _PIPELINE_VERSION
            and self.prompt_contract_version == expected_prompt_contract
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
    return frozen_execution_intent_json(payload)[1]


def canonical_execution_intent_json(intent_payload: Mapping[str, object]) -> str:
    """The exact fingerprint preimage encoding of one canonical intent payload."""
    return json.dumps(
        intent_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def frozen_execution_intent_json(payload: Mapping[str, object]) -> tuple[str, str]:
    """Return (canonical intent JSON, its SHA-256 fingerprint) for one payload.

    The JSON string is the literal preimage of the fingerprint; the durable
    EVIDENCE_RESEARCH approval stores it verbatim, and the SQLite floor
    recomputes the hash from the stored text (0019).
    """
    canonical = canonicalize_durable_research_payload(payload)
    intent = canonical["execution_intent"]
    assert isinstance(intent, dict)
    encoded = canonical_execution_intent_json(intent)
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()
